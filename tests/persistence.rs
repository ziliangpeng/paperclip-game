use paperclip_game::game::amount::Amount;
use paperclip_game::health::{PersistenceHealth, PersistencePhase};
use paperclip_game::persistence::{
    DEFAULT_SNAPSHOT_INTERVAL, LoadOrigin, PersistenceWorker, SnapshotStore, StorageError,
    WorkerOptions,
};
use paperclip_game::snapshot::{SnapshotError, SnapshotV1};
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

fn snapshot(startup: &StartupSnapshot, revision: u64) -> SnapshotV1 {
    state_snapshot(&startup.state, revision)
}

fn state_snapshot(state: &paperclip_game::game::state::GameState, revision: u64) -> SnapshotV1 {
    SnapshotV1::capture(state, revision).unwrap()
}

fn changed_snapshot(startup: &StartupSnapshot, revision: u64, funds: &str) -> SnapshotV1 {
    changed_state_snapshot(&startup.state, revision, funds)
}

fn changed_state_snapshot(
    state: &paperclip_game::game::state::GameState,
    revision: u64,
    funds: &str,
) -> SnapshotV1 {
    let mut state = state.clone();
    state.pro.funds = Amount::parse(funds).unwrap();
    SnapshotV1::capture(&state, revision).unwrap()
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

fn assert_rejected_without_mutation(
    directory: &TestDirectory,
    initial: &SnapshotV1,
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
        SnapshotV1::from_canonical_bytes(original_payload.as_bytes()).unwrap(),
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
    assert_eq!(user_version, 1);
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
        "real SQLite: schema v1, TEXT/INTEGER row, two identical restores, no progression replay"
    );
}

#[test]
fn strict_stored_payload_negative_table_preserves_existing_raw_database() {
    let mutations: [TextMutation; 8] = [
        (
            "unsupported snapshot",
            SnapshotError::UnsupportedSnapshotVersion,
            |text: &str| text.replacen("\"snapshot_version\":1", "\"snapshot_version\":2", 1),
        ),
        ("duplicate", SnapshotError::DuplicateField, |text: &str| {
            text.replacen(
                "\"snapshot_version\":1",
                "\"snapshot_version\":1,\"snapshot_version\":1",
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
                    .pragma_update(None, "user_version", 2)
                    .unwrap();
            },
        ),
        (
            "unsupported row version",
            StorageError::UnsupportedSnapshotVersion,
            |path: &Path| {
                let connection = Connection::open(path).unwrap();
                connection
                    .pragma_update(None, "ignore_check_constraints", true)
                    .unwrap();
                connection
                    .execute("UPDATE game_snapshot SET snapshot_version = 2", [])
                    .unwrap();
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

    if mode == "after" {
        startup.store.commit(2, &new).unwrap();
        std::fs::write(&marker, new.to_canonical_bytes().unwrap()).unwrap();
    } else {
        assert_eq!(mode, "before");
        // Capturing does not write SQLite. Revision 2 deliberately stays unsaved.
        std::fs::write(&marker, old.to_canonical_bytes().unwrap()).unwrap();
    }
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
        let expected = SnapshotV1::from_canonical_bytes(&expected_bytes).unwrap();

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
