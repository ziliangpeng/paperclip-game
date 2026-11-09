use paperclip_game::game::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use paperclip_game::health::{PersistenceHealth, PersistencePhase};
use paperclip_game::persistence::{
    DEFAULT_SNAPSHOT_INTERVAL, LoadOrigin, PersistenceWorker, SnapshotStore, StorageError,
    WorkerOptions,
};
use paperclip_game::snapshot::{Snapshot, SnapshotError};
use paperclip_game::startup::{self, StartupSnapshot};
use rusqlite::{Connection, OpenFlags};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

type TextMutation = (&'static str, SnapshotError, fn(&str) -> String);
type PathMutation = (&'static str, StorageError, fn(&Path));

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new() -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "paperclip-game-persistence-test-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated persistence test directory");
        Self(path)
    }

    fn database(&self) -> PathBuf {
        self.0.join("state.sqlite3")
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn open(path: &Path) -> StartupSnapshot {
    startup::load_or_initialize(path).expect("open valid persistence fixture")
}

fn snapshot(startup: &StartupSnapshot, revision: u64) -> Snapshot {
    state_snapshot(&startup.state, revision)
}

fn state_snapshot(state: &paperclip_game::game::state::GameState, revision: u64) -> Snapshot {
    Snapshot::capture(state, revision).unwrap()
}

fn changed_snapshot(startup: &StartupSnapshot, revision: u64, funds: &str) -> Snapshot {
    changed_state_snapshot(&startup.state, revision, funds)
}

fn changed_state_snapshot(
    state: &paperclip_game::game::state::GameState,
    revision: u64,
    funds: &str,
) -> Snapshot {
    let mut state = state.clone();
    state.pro.funds = Amount::parse(funds).unwrap();
    Snapshot::capture(&state, revision).unwrap()
}

fn payload(path: &Path) -> String {
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    connection
        .query_row("SELECT payload FROM game_snapshot", [], |row| row.get(0))
        .unwrap()
}

fn row_types(path: &Path) -> Vec<(String, String)> {
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let mut statement = connection
        .prepare("PRAGMA table_info(game_snapshot)")
        .unwrap();
    statement
        .query_map([], |row| Ok((row.get(1)?, row.get(2)?)))
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap()
}

fn digest(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(64);
    for byte in Sha256::digest(bytes) {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 15)]));
    }
    output
}

fn replace_payload(path: &Path, candidate: &str) {
    let connection = Connection::open(path).unwrap();
    connection
        .execute(
            "UPDATE game_snapshot SET payload = ?1, checksum = ?2 WHERE slot = 'default'",
            rusqlite::params![candidate, digest(candidate.as_bytes())],
        )
        .unwrap();
}

fn directory_names(path: &Path) -> Vec<String> {
    let mut names = std::fs::read_dir(path)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    names.sort();
    names
}

fn directory_bytes(path: &Path) -> std::collections::BTreeMap<String, Vec<u8>> {
    std::fs::read_dir(path)
        .unwrap()
        .map(|entry| {
            let entry = entry.unwrap();
            (
                entry.file_name().to_string_lossy().into_owned(),
                std::fs::read(entry.path()).unwrap(),
            )
        })
        .collect()
}

#[cfg(unix)]
struct PermissionRestorer {
    directory: PathBuf,
    directory_permissions: std::fs::Permissions,
    files: Vec<(PathBuf, std::fs::Permissions)>,
}

#[cfg(unix)]
impl PermissionRestorer {
    fn new(directory: &TestDirectory) -> Self {
        let files = std::fs::read_dir(&directory.0)
            .unwrap()
            .map(|entry| {
                let path = entry.unwrap().path();
                let permissions = std::fs::metadata(&path).unwrap().permissions();
                (path, permissions)
            })
            .collect();
        Self {
            directory_permissions: std::fs::metadata(&directory.0).unwrap().permissions(),
            directory: directory.0.clone(),
            files,
        }
    }

    fn make_read_only(&self) {
        use std::os::unix::fs::PermissionsExt;

        // Only this test's freshly-created files/directory are changed.
        for (path, _) in &self.files {
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o444)).unwrap();
        }
        std::fs::set_permissions(&self.directory, std::fs::Permissions::from_mode(0o555)).unwrap();
    }
}

#[cfg(unix)]
impl Drop for PermissionRestorer {
    fn drop(&mut self) {
        let _ = std::fs::set_permissions(&self.directory, self.directory_permissions.clone());
        for (path, permissions) in &self.files {
            let _ = std::fs::set_permissions(path, permissions.clone());
        }
    }
}

fn assert_rejected_without_mutation(
    directory: &TestDirectory,
    initial: &Snapshot,
    expected: StorageError,
) {
    let path = directory.database();
    let before = std::fs::read(&path).unwrap();
    let files_before = directory_names(&directory.0);
    let error = SnapshotStore::open_or_initialize(&path, initial)
        .expect_err("invalid existing database must fail closed");
    assert_eq!(error, expected);
    assert_eq!(std::fs::read(&path).unwrap(), before);
    assert_eq!(directory_names(&directory.0), files_before);
    assert!(!error.to_string().contains(path.to_str().unwrap()));
}

#[test]
fn real_sqlite_full_row_commit_and_repeated_restore_do_not_reapply_progress() {
    let directory = TestDirectory::new();
    let path = directory.database();
    let mut startup = open(&path);
    assert_eq!(startup.origin, LoadOrigin::FreshInitialized);
    assert_eq!(startup.revision, 0);
    let original_payload = payload(&path);
    assert_eq!(
        Snapshot::from_canonical_bytes(original_payload.as_bytes()).unwrap(),
        snapshot(&startup, 0)
    );
    let expected = changed_snapshot(&startup, 2, "9007199254740993.000000000000000001");
    startup.store.commit(1, &expected).unwrap();
    drop(startup);

    for repetition in 0..2 {
        let restored = open(&path);
        assert_eq!(restored.origin, LoadOrigin::Restored);
        assert_eq!(restored.revision, 2);
        assert_eq!(restored.capture_sequence, 1);
        assert_eq!(
            restored.state.pro.funds.to_string(),
            "9007199254740993.000000000000000001"
        );
        assert_eq!(snapshot(&restored, 2), expected, "repetition {repetition}");
        assert_eq!(
            payload(&path).as_bytes(),
            expected.to_canonical_bytes().unwrap().as_slice()
        );
    }
    let connection = Connection::open_with_flags(&path, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    let user_version: i64 = connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .unwrap();
    assert_eq!(user_version, 3);
    let payload_type: String = connection
        .query_row("SELECT typeof(payload) FROM game_snapshot", [], |row| {
            row.get(0)
        })
        .unwrap();
    let revision_type: String = connection
        .query_row("SELECT typeof(revision) FROM game_snapshot", [], |row| {
            row.get(0)
        })
        .unwrap();
    assert_eq!(
        (payload_type.as_str(), revision_type.as_str()),
        ("text", "integer")
    );
    assert!(row_types(&path).iter().all(|(_, kind)| kind != "REAL"));
    assert_eq!(DEFAULT_SNAPSHOT_INTERVAL, Duration::from_secs(30));
    eprintln!(
        "real SQLite: current schema 3, TEXT/INTEGER row, two identical restores, no progression replay"
    );
}

#[test]
fn strict_stored_payload_negative_table_preserves_existing_raw_database() {
    let mutations: [TextMutation; 8] = [
        (
            "unsupported snapshot",
            SnapshotError::UnsupportedSnapshotVersion,
            |text: &str| text.replacen("\"snapshot_version\":3", "\"snapshot_version\":4", 1),
        ),
        ("duplicate", SnapshotError::DuplicateField, |text: &str| {
            text.replacen(
                "\"snapshot_version\":3",
                "\"snapshot_version\":3,\"snapshot_version\":3",
                1,
            )
        }),
        ("unknown", SnapshotError::UnknownField, |text: &str| {
            text.replacen(
                "{\"snapshot_version\"",
                "{\"unknown\":0,\"snapshot_version\"",
                1,
            )
        }),
        ("missing", SnapshotError::MissingField, |text: &str| {
            text.replacen("\"fast_phase\":0,", "", 1)
        }),
        (
            "wrong primitive",
            SnapshotError::WrongPrimitive,
            |text: &str| text.replacen("\"funds\":\"0\"", "\"funds\":0", 1),
        ),
        (
            "noncanonical Amount",
            SnapshotError::NonCanonicalAmount,
            |text: &str| text.replacen("\"funds\":\"0\"", "\"funds\":\"-0\"", 1),
        ),
        (
            "clock relation",
            SnapshotError::InvalidClockState,
            |text: &str| text.replacen("\"fast_phase\":0", "\"fast_phase\":1", 1),
        ),
        ("malformed", SnapshotError::MalformedJson, |text: &str| {
            text[..text.len() - 1].to_owned()
        }),
    ];
    for (label, expected, mutate) in mutations {
        let directory = TestDirectory::new();
        let path = directory.database();
        let startup = open(&path);
        let initial = snapshot(&startup, 0);
        let candidate = mutate(&String::from_utf8(initial.to_canonical_bytes().unwrap()).unwrap());
        drop(startup);
        replace_payload(&path, &candidate);
        assert_rejected_without_mutation(&directory, &initial, StorageError::Snapshot(expected));
        eprintln!("stored payload negative case {label}: {expected:?}");
    }

    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let initial = snapshot(&startup, 0);
    let mut uppercase = initial.clone();
    uppercase.rng_state = uppercase.rng_state.to_uppercase();
    drop(startup);
    replace_payload(&path, &serde_json::to_string(&uppercase).unwrap());
    assert_rejected_without_mutation(
        &directory,
        &initial,
        StorageError::Snapshot(SnapshotError::InvalidRngState),
    );
}

fn r1_corrupt_autoclipper_snapshot(startup: &StartupSnapshot, impossible_rate: bool) -> Snapshot {
    let mut invalid = snapshot(startup, 1);
    invalid.pro.auto_clippers = IntegralAmount::from_i128(1);
    invalid.pro.auto_clipper_revealed = impossible_rate;
    invalid.pro.auto_clipper_cost = Amount::parse("6.1").unwrap();
    invalid.pro.auto_clipper_rate = if impossible_rate {
        NonNegativeAmount::from_i128(999).unwrap()
    } else {
        NonNegativeAmount::zero()
    };
    invalid
}

fn r1_assert_autoclipper_corruption_fails_store_and_startup(impossible_rate: bool) {
    let commit_directory = TestDirectory::new();
    let commit_path = commit_directory.database();
    let mut startup = open(&commit_path);
    let good = snapshot(&startup, 0);
    let invalid = r1_corrupt_autoclipper_snapshot(&startup, impossible_rate);
    let raw = String::from_utf8(serde_json::to_vec(&invalid).unwrap()).unwrap();
    assert_eq!(
        Snapshot::from_canonical_bytes(raw.as_bytes()),
        Err(SnapshotError::DomainViolation)
    );
    let good_payload = payload(&commit_path);
    assert_eq!(
        startup.store.commit(1, &invalid),
        Err(StorageError::Snapshot(SnapshotError::DomainViolation))
    );
    assert_eq!(payload(&commit_path), good_payload);
    assert_eq!(startup.store.last_revision(), 0);
    assert_eq!(startup.store.last_sequence(), 0);
    drop(startup);
    let reopened = open(&commit_path);
    assert_eq!(reopened.capture_sequence, 0);
    assert_eq!(reopened.revision, 0);
    assert_eq!(reopened.state.pro.auto_clippers.to_string(), "0");
    assert!(!reopened.state.pro.auto_clipper_revealed);
    assert_eq!(state_snapshot(&reopened.state, 0), good);
    drop(reopened);

    let startup_directory = TestDirectory::new();
    let startup_path = startup_directory.database();
    let startup = open(&startup_path);
    let initial = snapshot(&startup, 0);
    let invalid = r1_corrupt_autoclipper_snapshot(&startup, impossible_rate);
    drop(startup);
    replace_payload(
        &startup_path,
        &String::from_utf8(serde_json::to_vec(&invalid).unwrap()).unwrap(),
    );
    assert_rejected_without_mutation(
        &startup_directory,
        &initial,
        StorageError::Snapshot(SnapshotError::DomainViolation),
    );
    eprintln!(
        "R1 strict V3/store/startup rejected {} without changing the last good row",
        if impossible_rate {
            "stored rate above producer count"
        } else {
            "hidden producer"
        }
    );
}

#[test]
fn r1_hidden_producer_fails_decode_commit_and_startup_without_losing_good_row() {
    r1_assert_autoclipper_corruption_fails_store_and_startup(false);
}

#[test]
fn r1_impossible_latest_second_rate_fails_decode_commit_and_startup_without_losing_good_row() {
    r1_assert_autoclipper_corruption_fails_store_and_startup(true);
}

#[test]
fn checksum_metadata_utf8_and_schema_faults_are_explicit_and_non_mutating() {
    let mutations: [PathMutation; 7] = [
        (
            "checksum mismatch",
            StorageError::ChecksumMismatch,
            |path: &Path| {
                let connection = Connection::open(path).unwrap();
                connection
                    .execute("UPDATE game_snapshot SET checksum = ?1", ["0".repeat(64)])
                    .unwrap();
            },
        ),
        (
            "checksum uppercase",
            StorageError::InvalidChecksum,
            |path: &Path| {
                let connection = Connection::open(path).unwrap();
                connection
                    .execute("UPDATE game_snapshot SET checksum = upper(checksum)", [])
                    .unwrap();
            },
        ),
        (
            "unsupported schema",
            StorageError::UnsupportedSchemaVersion,
            |path: &Path| {
                Connection::open(path)
                    .unwrap()
                    .pragma_update(None, "user_version", 4)
                    .unwrap();
            },
        ),
        (
            "unsupported row version",
            StorageError::Snapshot(SnapshotError::UnsupportedSnapshotVersion),
            |path: &Path| {
                let connection = Connection::open(path).unwrap();
                connection
                    .pragma_update(None, "ignore_check_constraints", true)
                    .unwrap();
                connection
                    .execute("UPDATE game_snapshot SET snapshot_version = 3", [])
                    .unwrap();
                let future =
                    payload(path).replacen("\"snapshot_version\":3", "\"snapshot_version\":4", 1);
                replace_payload(path, &future);
            },
        ),
        (
            "REAL revision",
            StorageError::WrongStoragePrimitive,
            |path: &Path| {
                Connection::open(path)
                    .unwrap()
                    .execute("UPDATE game_snapshot SET revision = 0.5", [])
                    .unwrap();
            },
        ),
        (
            "negative sequence",
            StorageError::InvalidMetadata,
            |path: &Path| {
                let connection = Connection::open(path).unwrap();
                connection
                    .pragma_update(None, "ignore_check_constraints", true)
                    .unwrap();
                connection
                    .execute("UPDATE game_snapshot SET capture_sequence = -1", [])
                    .unwrap();
            },
        ),
        ("missing row", StorageError::InvalidSchema, |path: &Path| {
            Connection::open(path)
                .unwrap()
                .execute("DELETE FROM game_snapshot", [])
                .unwrap();
        }),
    ];
    for (label, expected, mutation) in mutations {
        let directory = TestDirectory::new();
        let path = directory.database();
        let startup = open(&path);
        let initial = snapshot(&startup, 0);
        drop(startup);
        mutation(&path);
        assert_rejected_without_mutation(&directory, &initial, expected);
        eprintln!("stored metadata negative case {label}: {expected:?}");
    }

    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let initial = snapshot(&startup, 0);
    drop(startup);
    let invalid_utf8 = [0xff, 0xfe];
    let connection = Connection::open(&path).unwrap();
    connection
        .execute(
            "UPDATE game_snapshot SET payload = CAST(?1 AS TEXT), checksum = ?2",
            rusqlite::params![&invalid_utf8[..], digest(&invalid_utf8)],
        )
        .unwrap();
    drop(connection);
    assert_rejected_without_mutation(
        &directory,
        &initial,
        StorageError::Snapshot(SnapshotError::InvalidUtf8),
    );

    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let initial = snapshot(&startup, 0);
    let new_payload = changed_snapshot(&startup, 1, "1");
    drop(startup);
    replace_payload(
        &path,
        &String::from_utf8(new_payload.to_canonical_bytes().unwrap()).unwrap(),
    );
    assert_rejected_without_mutation(&directory, &initial, StorageError::InvalidMetadata);
}

#[test]
fn corrupt_non_sqlite_and_empty_files_follow_distinct_fail_closed_paths() {
    let source_directory = TestDirectory::new();
    let source = open(&source_directory.database());
    let initial = snapshot(&source, 0);
    drop(source);

    let corrupt = TestDirectory::new();
    let corrupt_path = corrupt.database();
    std::fs::write(&corrupt_path, b"not-a-sqlite-database-sentinel").unwrap();
    assert_rejected_without_mutation(&corrupt, &initial, StorageError::InvalidDatabase);

    let empty = TestDirectory::new();
    let empty_path = empty.database();
    std::fs::write(&empty_path, []).unwrap();
    let loaded = open(&empty_path);
    assert_eq!(loaded.origin, LoadOrigin::FreshInitialized);
    assert_eq!(loaded.revision, 0);

    let sidecar_sets: [&[&str]; 4] = [
        &["-wal"],
        &["-shm"],
        &["-journal"],
        &["-wal", "-shm", "-journal"],
    ];
    for main_exists in [false, true] {
        for suffixes in sidecar_sets {
            let orphaned = TestDirectory::new();
            let path = orphaned.database();
            if main_exists {
                std::fs::write(&path, []).unwrap();
            }
            for suffix in suffixes {
                let mut sidecar = path.as_os_str().to_os_string();
                sidecar.push(suffix);
                let bytes = if *suffix == "-wal" {
                    Vec::new()
                } else {
                    format!("original {suffix} sentinel").into_bytes()
                };
                std::fs::write(sidecar, bytes).unwrap();
            }
            let before = directory_bytes(&orphaned.0);
            let error = SnapshotStore::open_or_initialize(&path, &initial)
                .expect_err("any known existing sidecar forbids fresh initialization");
            assert_eq!(
                error,
                StorageError::InvalidDatabase,
                "main_exists={main_exists}, suffixes={suffixes:?}"
            );
            assert_eq!(
                directory_bytes(&orphaned.0),
                before,
                "preserved main_exists={main_exists}, suffixes={suffixes:?}"
            );
            assert!(!error.to_string().contains(path.to_str().unwrap()));
        }
    }
}

#[cfg(unix)]
#[test]
fn dangling_and_directory_sidecars_fail_closed_without_new_world_creation() {
    let directory = TestDirectory::new();
    let source = open(&directory.database());
    let initial = snapshot(&source, 0);
    drop(source);
    for main_exists in [false, true] {
        for kind in ["dangling", "directory"] {
            let fixture = TestDirectory::new();
            let path = fixture.database();
            if main_exists {
                std::fs::write(&path, []).unwrap();
            }
            let mut sidecar = path.as_os_str().to_os_string();
            sidecar.push(if kind == "dangling" { "-wal" } else { "-shm" });
            if kind == "dangling" {
                std::os::unix::fs::symlink("never-created-target.sqlite3", &sidecar).unwrap();
            } else {
                std::fs::create_dir(&sidecar).unwrap();
            }
            let before = directory_names(&fixture.0);
            let error = SnapshotStore::open_or_initialize(&path, &initial)
                .expect_err("a dangling symlink/directory is not an empty database location");
            assert_eq!(error, StorageError::InvalidDatabase);
            assert_eq!(directory_names(&fixture.0), before, "{kind}");
            if main_exists {
                assert_eq!(std::fs::read(&path).unwrap(), b"");
            } else {
                assert!(!path.exists());
            }
            if kind == "dangling" {
                assert_eq!(
                    std::fs::read_link(&sidecar).unwrap(),
                    PathBuf::from("never-created-target.sqlite3")
                );
                assert!(!fixture.0.join("never-created-target.sqlite3").exists());
            } else {
                assert_eq!(std::fs::read_dir(&sidecar).unwrap().count(), 0);
            }
            assert!(!error.to_string().contains(path.to_str().unwrap()));
        }
    }
}

#[cfg(unix)]
#[test]
fn real_filesystem_io_rejection_preserves_the_committed_row_and_original_bytes() {
    let uid = std::process::Command::new("id")
        .arg("-u")
        .output()
        .expect("query the actual Unix runtime uid");
    assert!(uid.status.success());
    let uid = String::from_utf8(uid.stdout)
        .unwrap()
        .trim()
        .parse::<u32>()
        .expect("numeric Unix runtime uid");
    assert_ne!(uid, 0, "root would bypass the real permission fault");
    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let committed = changed_snapshot(&startup, 1, "9007199254740993.000000000000000001");
    let replacement = snapshot(&startup, 0);
    let mut store = startup.store;
    store.commit(1, &committed).unwrap();
    drop(store);
    let before = directory_bytes(&directory.0);
    let permissions = PermissionRestorer::new(&directory);
    permissions.make_read_only();
    let precondition = std::fs::write(directory.0.join("must-not-be-created"), b"")
        .expect_err("the real UID must be unable to write into the read-only fixture");
    assert_eq!(precondition.kind(), std::io::ErrorKind::PermissionDenied);

    let error = SnapshotStore::open_or_initialize(&path, &replacement)
        .expect_err("the real OS permissions must reject writable SQLite access");
    assert!(
        matches!(&error, StorageError::OpenFailed | StorageError::IoFailed),
        "unexpected typed I/O rejection: {error:?}"
    );
    assert!(!error.to_string().contains(path.to_str().unwrap()));
    drop(permissions);
    assert_eq!(directory_bytes(&directory.0), before);
    eprintln!(
        "real Unix uid {uid}, readonly directory/file rejection {error:?}; exact old bytes preserved"
    );

    let restored = open(&path);
    assert_eq!(restored.origin, LoadOrigin::Restored);
    assert_eq!(restored.revision, 1);
    assert_eq!(restored.capture_sequence, 1);
    assert_eq!(snapshot(&restored, 1), committed);
    assert_eq!(
        payload(&path).as_bytes(),
        committed.to_canonical_bytes().unwrap().as_slice()
    );
}

#[test]
fn real_transaction_trigger_and_busy_faults_leave_old_then_new_complete_rows() {
    let directory = TestDirectory::new();
    let path = directory.database();
    let mut startup = open(&path);
    let old = changed_snapshot(&startup, 1, "1");
    startup.store.commit(1, &old).unwrap();
    let new = changed_snapshot(&startup, 2, "2");
    let old_payload = String::from_utf8(old.to_canonical_bytes().unwrap()).unwrap();
    let new_payload = String::from_utf8(new.to_canonical_bytes().unwrap()).unwrap();

    let connection = Connection::open(&path).unwrap();
    connection
        .execute_batch(
            "CREATE TRIGGER reject_snapshot_update BEFORE UPDATE ON game_snapshot
             BEGIN SELECT RAISE(ABORT, 'fixture rejection'); END;",
        )
        .unwrap();
    assert_eq!(
        startup.store.commit(2, &new),
        Err(StorageError::TransactionFailed)
    );
    assert_eq!(payload(&path), old_payload);
    connection
        .execute("DROP TRIGGER reject_snapshot_update", [])
        .unwrap();
    startup.store.commit(2, &new).unwrap();
    assert_eq!(payload(&path), new_payload);

    let blocker = Connection::open(&path).unwrap();
    blocker.execute_batch("BEGIN IMMEDIATE").unwrap();
    let later = changed_snapshot(&startup, 3, "3");
    assert_eq!(
        startup.store.commit(3, &later),
        Err(StorageError::DatabaseBusy)
    );
    assert_eq!(payload(&path), new_payload);
    blocker.execute_batch("ROLLBACK").unwrap();
    startup.store.commit(3, &later).unwrap();
    assert_eq!(
        payload(&path).as_bytes(),
        later.to_canonical_bytes().unwrap().as_slice()
    );

    assert_eq!(
        startup.store.commit(2, &old),
        Err(StorageError::StaleCapture)
    );
    assert_eq!(
        startup.store.commit(4, &old),
        Err(StorageError::StaleCapture)
    );
    assert_eq!(
        startup.store.commit(3, &new),
        Err(StorageError::SequenceConflict)
    );
    assert_eq!(
        payload(&path).as_bytes(),
        later.to_canonical_bytes().unwrap().as_slice()
    );
    eprintln!(
        "atomic SQL matrix: trigger rollback, busy rollback, committed replacement, stale/sequence guards all preserved one complete row"
    );
}

fn wait_until(mut predicate: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while !predicate() {
        assert!(Instant::now() < deadline, "bounded worker wait expired");
        std::thread::sleep(Duration::from_millis(2));
    }
}

fn worker_options(max_attempts: u32) -> WorkerOptions {
    WorkerOptions {
        max_attempts,
        initial_backoff: Duration::from_millis(30),
        maximum_backoff: Duration::from_millis(30),
    }
}

#[test]
fn real_blocked_sqlite_write_coalesces_latest_and_recovers_with_bounded_health() {
    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let state = startup.state.clone();
    let health = PersistenceHealth::new(DEFAULT_SNAPSHOT_INTERVAL, 0, 0);
    let observer = health.clone();
    let worker = PersistenceWorker::start(startup.store, health, worker_options(20)).unwrap();
    let blocker = Connection::open(&path).unwrap();
    blocker.execute_batch("BEGIN IMMEDIATE").unwrap();

    worker.submit(state_snapshot(&state, 1)).unwrap();
    wait_until(|| observer.snapshot().write_in_progress);
    for revision in 2..=4 {
        let capture = changed_state_snapshot(&state, revision, &revision.to_string());
        assert_eq!(worker.submit(capture).unwrap(), revision);
    }
    wait_until(|| !observer.snapshot().ready);
    let degraded = observer.snapshot();
    assert!(degraded.live);
    assert_eq!(degraded.last_committed_revision, Some(0));
    assert_eq!(degraded.latest_captured_revision, Some(4));
    assert_eq!(degraded.latest_captured_sequence, Some(4));
    assert!(degraded.pending_snapshot || degraded.write_in_progress);
    assert!(!format!("{degraded:?}").contains(path.to_str().unwrap()));

    blocker.execute_batch("ROLLBACK").unwrap();
    wait_until(|| observer.snapshot().last_committed_sequence == Some(4));
    let recovered = observer.snapshot();
    assert!(recovered.ready);
    assert_eq!(recovered.last_committed_revision, Some(4));
    assert_eq!(recovered.consecutive_failures, 0);
    assert_eq!(recovered.last_failure, None);
    worker.shutdown().unwrap();
    let final_payload = payload(&path);
    assert!(final_payload.contains("\"revision\":4"));
    assert!(final_payload.contains("\"funds\":\"4\""));
    assert!(!final_payload.contains("\"funds\":\"2\""));
    eprintln!(
        "async queue: real SQLite busy, 1 in-flight + latest slot, revisions 2/3 superseded by 4, degraded then committed/ready"
    );
}

#[test]
fn terminal_failure_keeps_world_health_live_and_next_capture_can_recover() {
    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let state = startup.state.clone();
    let health = PersistenceHealth::new(DEFAULT_SNAPSHOT_INTERVAL, 0, 0);
    let observer = health.clone();
    let worker = PersistenceWorker::start(startup.store, health, worker_options(1)).unwrap();
    let blocker = Connection::open(&path).unwrap();
    blocker.execute_batch("BEGIN IMMEDIATE").unwrap();
    worker.submit(state_snapshot(&state, 1)).unwrap();
    wait_until(|| observer.snapshot().phase == PersistencePhase::Degraded);
    let failed = observer.snapshot();
    assert!(failed.live);
    assert!(!failed.ready);
    assert!(!failed.write_in_progress);
    assert_eq!(failed.last_committed_revision, Some(0));
    assert_eq!(failed.latest_captured_revision, Some(1));
    assert_eq!(failed.consecutive_failures, 1);
    assert!(!format!("{failed:?}").contains(path.to_str().unwrap()));

    blocker.execute_batch("ROLLBACK").unwrap();
    worker.submit(state_snapshot(&state, 2)).unwrap();
    wait_until(|| observer.snapshot().last_committed_revision == Some(2));
    assert!(observer.snapshot().ready);
    let stopped = worker.shutdown().unwrap();
    assert!(!stopped.live);
    assert!(!stopped.ready);
    assert_eq!(stopped.last_committed_revision, Some(2));
}

#[test]
fn normal_shutdown_joins_and_commits_latest_pending_full_snapshot() {
    let directory = TestDirectory::new();
    let path = directory.database();
    let startup = open(&path);
    let state = startup.state.clone();
    let health = PersistenceHealth::new(DEFAULT_SNAPSHOT_INTERVAL, 0, 0);
    let worker = PersistenceWorker::start(startup.store, health, worker_options(2)).unwrap();
    worker.submit(state_snapshot(&state, 9)).unwrap();
    let stopped = worker.shutdown().unwrap();
    assert_eq!(stopped.last_committed_revision, Some(9));
    assert_eq!(stopped.last_committed_sequence, Some(1));
    assert_eq!(stopped.phase, PersistencePhase::Stopped);
    let restored = open(&path);
    assert_eq!(restored.revision, 9);
    assert_eq!(restored.capture_sequence, 1);
}

fn legacy_v1_bytes(snapshot: &Snapshot) -> Vec<u8> {
    assert_eq!(snapshot.snapshot_version, 3);
    let mut historical = String::from_utf8(snapshot.to_canonical_bytes().unwrap()).unwrap();
    historical = historical.replacen("\"snapshot_version\":3", "\"snapshot_version\":1", 1);
    let p = &snapshot.pro;
    for (name, value) in [
        (
            "marketing_effectiveness",
            serde_json::to_string(&p.marketing_effectiveness).unwrap(),
        ),
        (
            "demand_boost",
            serde_json::to_string(&p.demand_boost).unwrap(),
        ),
        ("prestige_u", serde_json::to_string(&p.prestige_u).unwrap()),
        ("demand", serde_json::to_string(&p.demand).unwrap()),
        ("clips_sold", serde_json::to_string(&p.clips_sold).unwrap()),
        ("income", serde_json::to_string(&p.income).unwrap()),
        (
            "last_sale_revenue",
            serde_json::to_string(&p.last_sale_revenue).unwrap(),
        ),
        (
            "wire_base_price",
            serde_json::to_string(&p.wire_base_price).unwrap(),
        ),
        (
            "wire_price_counter",
            serde_json::to_string(&p.wire_price_counter).unwrap(),
        ),
        (
            "wire_purchase_count",
            serde_json::to_string(&p.wire_purchase_count).unwrap(),
        ),
        (
            "wire_inactivity_ticks",
            serde_json::to_string(&p.wire_inactivity_ticks).unwrap(),
        ),
        (
            "auto_clipper_rate",
            serde_json::to_string(&p.auto_clipper_rate).unwrap(),
        ),
        (
            "auto_clipper_production_accumulator",
            serde_json::to_string(&p.auto_clipper_production_accumulator).unwrap(),
        ),
        (
            "console_messages",
            serde_json::to_string(&p.console_messages).unwrap(),
        ),
    ] {
        let member = format!(",\"{name}\":{value}");
        assert_eq!(
            historical.matches(&member).count(),
            1,
            "history member {name}"
        );
        historical = historical.replacen(&member, "", 1);
    }
    historical.into_bytes()
}

fn actual_legacy_state() -> Snapshot {
    let bootstrap = TestDirectory::new();
    let startup = open(&bootstrap.database());
    let mut snapshot = state_snapshot(&startup.state, 77);
    // A valid historical-state fixture, not additional product mutation APIs.
    snapshot.pro.lifetime_clips = NonNegativeAmount::from_i128(8).unwrap();
    snapshot.pro.unsold_clips = NonNegativeAmount::from_i128(8).unwrap();
    snapshot.pro.unused_clips = NonNegativeAmount::from_i128(8).unwrap();
    snapshot.pro.wire = NonNegativeAmount::from_i128(992).unwrap();
    snapshot.clock.update_count = SafeU64::new(1).unwrap();
    snapshot.clock.fast_phase = 1;
    snapshot.clock.second_phase = 1;
    snapshot.clock.slow_phase = 1;
    snapshot.clock.combat_remainder_nanos = 10_000_000;
    snapshot.clock.combat_pulses = SafeU64::new(0).unwrap();
    Snapshot::from_canonical_bytes(&snapshot.to_canonical_bytes().unwrap()).unwrap()
}

fn write_actual_schema_one(directory: &TestDirectory, snapshot: &Snapshot, extra: &str) -> Vec<u8> {
    // Exact table definition from base c4ce301:src/persistence.rs:26-38.
    let historical = String::from_utf8(legacy_v1_bytes(snapshot)).unwrap();
    let connection = Connection::open(directory.database()).unwrap();
    connection
        .execute_batch(
            "PRAGMA user_version = 1;
         PRAGMA journal_mode = WAL;
         PRAGMA synchronous = FULL;
         CREATE TABLE game_snapshot (
             slot TEXT PRIMARY KEY CHECK (slot = 'default'),
             snapshot_version INTEGER NOT NULL CHECK (snapshot_version = 1),
             revision INTEGER NOT NULL CHECK (
                 revision >= 0 AND revision <= 9007199254740991
             ),
             capture_sequence INTEGER NOT NULL CHECK (
                 capture_sequence >= 0 AND capture_sequence <= 9007199254740991
             ),
             payload TEXT NOT NULL,
             checksum TEXT NOT NULL CHECK (length(checksum) = 64)
         );",
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO game_snapshot (
             slot, snapshot_version, revision, capture_sequence, payload, checksum
         ) VALUES ('default', 1, 77, 3, ?1, ?2)",
            rusqlite::params![historical, digest(historical.as_bytes())],
        )
        .unwrap();
    connection.execute_batch(extra).unwrap();
    drop(connection);
    std::fs::read(directory.database()).unwrap()
}

fn legacy_v2_bytes(snapshot: &Snapshot) -> Vec<u8> {
    let p = &snapshot.pro;
    let mut historical = String::from_utf8(snapshot.to_canonical_bytes().unwrap()).unwrap();
    historical = historical.replacen("\"snapshot_version\":3", "\"snapshot_version\":2", 1);
    for (name, value) in [
        (
            "auto_clipper_rate",
            serde_json::to_string(&p.auto_clipper_rate).unwrap(),
        ),
        (
            "auto_clipper_production_accumulator",
            serde_json::to_string(&p.auto_clipper_production_accumulator).unwrap(),
        ),
        (
            "console_messages",
            serde_json::to_string(&p.console_messages).unwrap(),
        ),
    ] {
        let member = format!(",\"{name}\":{value}");
        assert_eq!(historical.matches(&member).count(), 1);
        historical = historical.replacen(&member, "", 1);
    }
    historical.into_bytes()
}

fn write_actual_schema_two(directory: &TestDirectory, snapshot: &Snapshot) {
    let historical = String::from_utf8(legacy_v2_bytes(snapshot)).unwrap();
    let connection = Connection::open(directory.database()).unwrap();
    connection
        .execute_batch(
            "PRAGMA user_version = 2;
         PRAGMA journal_mode = WAL;
         PRAGMA synchronous = FULL;
         CREATE TABLE game_snapshot (
             slot TEXT PRIMARY KEY CHECK (slot = 'default'),
             snapshot_version INTEGER NOT NULL CHECK (snapshot_version = 2),
             revision INTEGER NOT NULL CHECK (
                 revision >= 0 AND revision <= 9007199254740991
             ),
             capture_sequence INTEGER NOT NULL CHECK (
                 capture_sequence >= 0 AND capture_sequence <= 9007199254740991
             ),
             payload TEXT NOT NULL,
             checksum TEXT NOT NULL CHECK (length(checksum) = 64)
         );",
        )
        .unwrap();
    connection
        .execute(
            "INSERT INTO game_snapshot (
             slot, snapshot_version, revision, capture_sequence, payload, checksum
         ) VALUES ('default', 2, 77, 3, ?1, ?2)",
            rusqlite::params![historical, digest(historical.as_bytes())],
        )
        .unwrap();
}

#[test]
fn actual_schema_two_migration_retains_stored_autoclipper_price_count_and_reveal() {
    let directory = TestDirectory::new();
    let mut expected = actual_legacy_state();
    expected.pro.funds = Amount::parse("13.9").unwrap();
    expected.pro.auto_clipper_revealed = true;
    expected.pro.auto_clippers = IntegralAmount::from_i128(2);
    // This stored value is intentionally not recomputed from level two.
    expected.pro.auto_clipper_cost = Amount::parse("6.21").unwrap();
    write_actual_schema_two(&directory, &expected);

    let first = open(&directory.database());
    assert_eq!(first.origin, LoadOrigin::Migrated);
    assert_eq!(state_snapshot(&first.state, 77), expected);
    assert_eq!(first.state.pro.funds.to_string(), "13.9");
    assert_eq!(first.state.pro.auto_clippers.to_string(), "2");
    assert_eq!(first.state.pro.auto_clipper_cost.to_string(), "6.21");
    assert!(first.state.pro.auto_clipper_revealed);
    assert_eq!(first.state.pro.auto_clipper_rate, NonNegativeAmount::zero());
    assert_eq!(
        first.state.pro.console_messages,
        std::array::from_fn(|_| String::new())
    );
    assert_eq!(first.state.pro.lifetime_clips.to_string(), "8");
    assert!(payload(&directory.database()).starts_with("{\"snapshot_version\":3,"));
    let first_bytes = std::fs::read(directory.database()).unwrap();
    let connection = Connection::open(directory.database()).unwrap();
    let versions: (i64, i64, i64) = connection
        .query_row(
            "SELECT snapshot_version, revision, capture_sequence FROM game_snapshot",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(versions, (3, 77, 3));
    let schema: i64 = connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .unwrap();
    assert_eq!(schema, 3);
    drop(connection);

    let second = open(&directory.database());
    assert_eq!(second.origin, LoadOrigin::Restored);
    assert_eq!(state_snapshot(&second.state, 77), expected);
    assert_eq!(std::fs::read(directory.database()).unwrap(), first_bytes);
    eprintln!(
        "G03 actual schema 2 migration: retained exact count 2/stored 6.21/reveal/Funds 13.9; zero inferred production; repeat open restored V3 byte-identically"
    );
}

#[test]
fn actual_schema_one_migration_is_complete_idempotent_and_has_no_inferred_sales() {
    let directory = TestDirectory::new();
    let expected = actual_legacy_state();
    write_actual_schema_one(&directory, &expected, "");
    let first = open(&directory.database());
    assert_eq!(first.origin, LoadOrigin::Migrated);
    assert_eq!(first.revision, 77);
    assert_eq!(first.capture_sequence, 3);
    assert_eq!(first.state.pro.lifetime_clips.to_string(), "8");
    assert_eq!(first.state.pro.wire.to_string(), "992");
    assert_eq!(first.state.rng_state_hex(), expected.rng_state);
    assert_eq!(first.state.pro.clips_sold.to_string(), "0");
    assert_eq!(first.state.pro.income, Amount::zero());
    assert_eq!(first.state.pro.funds, Amount::zero());
    assert_eq!(first.state.pro.last_sale_revenue, Amount::zero());
    assert_eq!(first.state.pro.wire_base_price.to_string(), "20");
    assert_eq!(first.state.pro.wire_price_counter.get(), 0);
    assert_eq!(first.state.pro.wire_purchase_count.get(), 0);
    assert_eq!(first.state.pro.wire_inactivity_ticks.get(), 0);
    assert_eq!(first.state.clock.update_count(), 1);
    assert_eq!(state_snapshot(&first.state, 77), expected);
    let first_bytes = std::fs::read(directory.database()).unwrap();
    let upgraded = payload(&directory.database());
    assert!(upgraded.starts_with("{\"snapshot_version\":3,"));
    let connection = Connection::open(directory.database()).unwrap();
    let versions: (i64, i64, i64) = connection
        .query_row(
            "SELECT snapshot_version, revision, capture_sequence FROM game_snapshot",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert_eq!(versions, (3, 77, 3));
    let schema: i64 = connection
        .query_row("PRAGMA user_version", [], |r| r.get(0))
        .unwrap();
    assert_eq!(schema, 3);
    drop(connection);
    for _ in 0..2 {
        let restored = open(&directory.database());
        assert_eq!(restored.origin, LoadOrigin::Restored);
        assert_eq!(restored.capture_sequence, 3);
        assert_eq!(state_snapshot(&restored.state, 77), expected);
        assert_eq!(std::fs::read(directory.database()).unwrap(), first_bytes);
    }
    eprintln!(
        "actual schema 1 migration: retained revision 77, clock 1, RNG, eight produced clips and no offline sales; version 3 repeat opens byte-identical"
    );
}

#[test]
fn legacy_tampering_and_migration_transaction_failure_leave_original_bytes_unchanged() {
    let expected = actual_legacy_state();
    for case in ["unknown-field", "migration-ddl-conflict"] {
        let directory = TestDirectory::new();
        let extra = if case == "migration-ddl-conflict" {
            "CREATE TABLE game_snapshot_migration_source (slot TEXT);"
        } else {
            ""
        };
        let before = write_actual_schema_one(&directory, &expected, extra);
        if case == "unknown-field" {
            let historical = String::from_utf8(legacy_v1_bytes(&expected)).unwrap();
            let tampered = historical.replacen("\"pro\":{", "\"pro\":{\"private_marker\":0,", 1);
            replace_payload(&directory.database(), &tampered);
        }
        let before = if case == "unknown-field" {
            std::fs::read(directory.database()).unwrap()
        } else {
            before
        };
        let error =
            SnapshotStore::open_or_initialize(&directory.database(), &expected).unwrap_err();
        match case {
            "unknown-field" => {
                assert_eq!(error, StorageError::Snapshot(SnapshotError::UnknownField))
            }
            _ => assert_eq!(error, StorageError::TransactionFailed),
        }
        assert_eq!(
            std::fs::read(directory.database()).unwrap(),
            before,
            "{case}"
        );
        assert!(
            !payload(&directory.database()).contains("snapshot_version\":3"),
            "{case}"
        );
        if case == "migration-ddl-conflict" {
            let connection = Connection::open(directory.database()).unwrap();
            connection
                .execute_batch("DROP TABLE game_snapshot_migration_source;")
                .unwrap();
            drop(connection);
            let restored = open(&directory.database());
            assert_eq!(restored.origin, LoadOrigin::Migrated);
            assert_eq!(state_snapshot(&restored.state, 77), expected);
        }
        eprintln!(
            "legacy rejection {case}: typed, original DB bytes unchanged; cleanup permits legitimate migration"
        );
    }
}

const CRASH_DATABASE_ENV: &str = "PAPERCLIP_GAME_TEST_CRASH_DATABASE";
const CRASH_MODE_ENV: &str = "PAPERCLIP_GAME_TEST_CRASH_MODE";

#[test]
fn crash_store_child_entrypoint() {
    let Some(database) = std::env::var_os(CRASH_DATABASE_ENV) else {
        return;
    };
    let mode = std::env::var(CRASH_MODE_ENV).expect("crash fixture mode");
    let database = PathBuf::from(database);
    let marker = database.with_extension("committed");
    let mut startup = open(&database);
    let old = changed_snapshot(&startup, 1, "1");
    startup.store.commit(1, &old).unwrap();
    let new = changed_snapshot(&startup, 2, "2");

    let marker_staging = marker.with_extension("committed.tmp");
    if mode == "after" {
        startup.store.commit(2, &new).unwrap();
        std::fs::write(&marker_staging, new.to_canonical_bytes().unwrap()).unwrap();
    } else {
        assert_eq!(mode, "before");
        // Capturing does not write SQLite. Revision 2 deliberately stays unsaved.
        std::fs::write(&marker_staging, old.to_canonical_bytes().unwrap()).unwrap();
    }
    // Publish visibility only after the complete canonical payload is written.
    // write + rename in the same fixture directory makes exists() a ready signal.
    std::fs::rename(&marker_staging, &marker).unwrap();
    // A real child process remains alive with the SQLite connection open until SIGKILL.
    loop {
        std::thread::park();
    }
}

struct CrashChild(std::process::Child);

impl Drop for CrashChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn wait_for_commit_marker(marker: &Path, child: &mut std::process::Child) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while !marker.exists() {
        if let Some(status) = child.try_wait().unwrap() {
            panic!("crash fixture child exited before commit: {status}");
        }
        assert!(
            Instant::now() < deadline,
            "bounded crash child wait expired"
        );
        std::thread::sleep(Duration::from_millis(2));
    }
}

#[test]
fn real_process_sigkill_before_and_after_commit_recovers_only_complete_rows() {
    for (mode, expected_revision) in [("before", 1), ("after", 2)] {
        let directory = TestDirectory::new();
        let database = directory.0.join(format!("{mode}.sqlite3"));
        let marker = database.with_extension("committed");
        let child = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "crash_store_child_entrypoint", "--nocapture"])
            .env(CRASH_DATABASE_ENV, &database)
            .env(CRASH_MODE_ENV, mode)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .unwrap();
        let mut child = CrashChild(child);
        wait_for_commit_marker(&marker, &mut child.0);
        let expected_bytes = std::fs::read(&marker).unwrap();
        let expected = Snapshot::from_canonical_bytes(&expected_bytes).unwrap();

        child.0.kill().expect("send actual child process kill");
        let status = child.0.wait().expect("reap killed crash fixture child");
        assert!(!status.success());
        assert!(marker.exists());

        let restored = open(&database);
        assert_eq!(restored.origin, LoadOrigin::Restored);
        assert_eq!(restored.revision, expected_revision);
        assert_eq!(restored.capture_sequence, expected_revision);
        let expected_state = expected.restore().unwrap();
        assert_eq!(restored.state.pro, expected_state.state.pro);
        assert_eq!(restored.state.clock, expected_state.state.clock);
        assert_eq!(
            restored.state.rng_state_hex(),
            expected_state.state.rng_state_hex()
        );
        assert_eq!(payload(&database).as_bytes(), expected_bytes);
        eprintln!(
            "physical crash case {mode}: real child process killed after commit {expected_revision}; exact complete row recovered from on-disk SQLite/WAL"
        );
    }
}
