//! Real SQLite snapshots and one serialized, coalescing blocking worker.

use crate::game::amount::{MAX_SAFE_JSON_INTEGER, SafeU64};
use crate::game::clock::UPDATE_QUANTUM_NANOS;
use crate::health::{HealthSnapshot, PersistenceFailure, PersistenceHealth};
use crate::runtime::{RuntimeHandle, RuntimeView};
use crate::snapshot::{SNAPSHOT_VERSION, SnapshotError, SnapshotV1};
use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags, TransactionBehavior};
use sha2::{Digest, Sha256};
use std::error::Error;
use std::fmt;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::thread::{self, JoinHandle};
use std::time::Duration;
use tokio::sync::oneshot;
use tokio::task::JoinHandle as AsyncJoinHandle;

pub const DEFAULT_SNAPSHOT_INTERVAL: Duration = Duration::from_secs(30);
pub const DEFAULT_BUSY_TIMEOUT: Duration = Duration::from_millis(100);
const DEFAULT_ROW: &str = "default";
const SCHEMA_VERSION: i64 = 1;
const CREATE_SNAPSHOT_TABLE: &str = "
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
    )
";
const UPSERT_SNAPSHOT: &str = "
    INSERT INTO game_snapshot (
        slot, snapshot_version, revision, capture_sequence, payload, checksum
    ) VALUES ('default', ?1, ?2, ?3, ?4, ?5)
    ON CONFLICT(slot) DO UPDATE SET
        snapshot_version = excluded.snapshot_version,
        revision = excluded.revision,
        capture_sequence = excluded.capture_sequence,
        payload = excluded.payload,
        checksum = excluded.checksum
";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LoadOrigin {
    FreshInitialized,
    Restored,
}

#[derive(Clone, Debug)]
pub struct StoredSnapshot {
    pub snapshot: SnapshotV1,
    pub capture_sequence: u64,
    pub origin: LoadOrigin,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StorageError {
    OpenFailed,
    InvalidDatabase,
    IoFailed,
    UnsupportedSchemaVersion,
    InvalidSchema,
    InvalidMetadata,
    WrongStoragePrimitive,
    UnsupportedSnapshotVersion,
    InvalidChecksum,
    ChecksumMismatch,
    Snapshot(SnapshotError),
    DatabaseBusy,
    TransactionFailed,
    DurabilityFailure,
    StaleCapture,
    SequenceConflict,
    SequenceExhausted,
}

impl fmt::Display for StorageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::OpenFailed => "database open failed",
            Self::InvalidDatabase => "database format is invalid",
            Self::IoFailed => "database filesystem operation failed",
            Self::UnsupportedSchemaVersion => "unsupported database schema version",
            Self::InvalidSchema => "database snapshot schema is invalid",
            Self::InvalidMetadata => "snapshot row metadata is invalid",
            Self::WrongStoragePrimitive => "snapshot row has the wrong SQLite primitive",
            Self::UnsupportedSnapshotVersion => "unsupported snapshot row version",
            Self::InvalidChecksum => "snapshot checksum encoding is invalid",
            Self::ChecksumMismatch => "snapshot checksum mismatch",
            Self::Snapshot(error) => return write!(formatter, "invalid snapshot: {error}"),
            Self::DatabaseBusy => "database remains busy",
            Self::TransactionFailed => "snapshot transaction failed",
            Self::DurabilityFailure => "database durability configuration failed",
            Self::StaleCapture => "stale snapshot capture was rejected",
            Self::SequenceConflict => "snapshot capture sequence conflicts with committed state",
            Self::SequenceExhausted => "snapshot capture sequence exhausted its safe range",
        })
    }
}

impl Error for StorageError {}

impl From<SnapshotError> for StorageError {
    fn from(error: SnapshotError) -> Self {
        Self::Snapshot(error)
    }
}

impl PersistenceFailure {
    fn from_storage(error: StorageError) -> Self {
        match error {
            StorageError::DatabaseBusy => Self::DatabaseBusy,
            StorageError::OpenFailed | StorageError::IoFailed | StorageError::InvalidDatabase => {
                Self::OpenFailed
            }
            StorageError::UnsupportedSchemaVersion
            | StorageError::InvalidSchema
            | StorageError::InvalidMetadata
            | StorageError::WrongStoragePrimitive
            | StorageError::DurabilityFailure => Self::SchemaFailure,
            StorageError::InvalidChecksum | StorageError::ChecksumMismatch => {
                Self::ChecksumMismatch
            }
            StorageError::Snapshot(SnapshotError::ResourceLimit) => Self::ResourceLimit,
            StorageError::Snapshot(_) | StorageError::UnsupportedSnapshotVersion => {
                Self::InvalidSnapshot
            }
            StorageError::StaleCapture => Self::StaleCapture,
            StorageError::SequenceConflict | StorageError::SequenceExhausted => {
                Self::SequenceConflict
            }
            StorageError::TransactionFailed => Self::TransactionFailed,
        }
    }
}

#[derive(Clone)]
struct PreparedSnapshot {
    sequence: u64,
    revision: u64,
    update_count: u64,
    payload: String,
    checksum: String,
}

impl PreparedSnapshot {
    fn new(sequence: u64, snapshot: &SnapshotV1) -> Result<Self, StorageError> {
        SafeU64::new(sequence).map_err(|_| StorageError::SequenceExhausted)?;
        let payload = snapshot.to_canonical_bytes()?;
        let checksum = sha256_hex(&payload);
        let payload = String::from_utf8(payload).map_err(|_| SnapshotError::EncodingFailed)?;
        let revision = snapshot.revision.get();
        let update_count = snapshot.clock.update_count.get();
        Ok(Self {
            sequence,
            revision,
            update_count,
            payload,
            checksum,
        })
    }
}

#[derive(Debug)]
pub struct SnapshotStore {
    connection: Connection,
    last_sequence: u64,
    last_revision: u64,
    last_checksum: String,
}

impl SnapshotStore {
    /// Existing bytes are validated through a read-only connection before any
    /// schema/durability mutation. Only nonexistent or zero-length files are fresh.
    pub fn open_or_initialize(
        path: &Path,
        initial: &SnapshotV1,
    ) -> Result<(Self, StoredSnapshot), StorageError> {
        let metadata = match std::fs::symlink_metadata(path) {
            Ok(metadata) => Some(metadata),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(_) => return Err(StorageError::IoFailed),
        };
        let fresh = metadata.as_ref().is_none_or(|metadata| metadata.len() == 0);
        if fresh {
            if metadata.is_none()
                && let Some(parent) = path.parent()
                && !parent.as_os_str().is_empty()
            {
                std::fs::create_dir_all(parent).map_err(|_| StorageError::IoFailed)?;
            }
            Self::initialize_fresh(path, initial)
        } else {
            Self::open_valid_existing(path)
        }
    }

    fn initialize_fresh(
        path: &Path,
        initial: &SnapshotV1,
    ) -> Result<(Self, StoredSnapshot), StorageError> {
        let prepared = PreparedSnapshot::new(0, initial)?;
        let mut connection = open_writable(path, true)?;
        configure_durability(&connection)?;
        let inserted = (|| -> Result<(), StorageError> {
            let transaction = connection
                .transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(map_transaction_error)?;
            transaction
                .pragma_update(None, "user_version", SCHEMA_VERSION)
                .map_err(map_transaction_error)?;
            transaction
                .execute(CREATE_SNAPSHOT_TABLE, [])
                .map_err(map_transaction_error)?;
            insert_prepared(&transaction, &prepared)?;
            transaction.commit().map_err(map_transaction_error)?;
            Ok(())
        })();
        // Fresh initialization has no prior game. Never substitute another game.
        inserted?;
        let checksum = prepared.checksum.clone();
        let store = Self {
            connection,
            last_sequence: 0,
            last_revision: prepared.revision,
            last_checksum: checksum,
        };
        Ok((
            store,
            StoredSnapshot {
                snapshot: initial.clone(),
                capture_sequence: 0,
                origin: LoadOrigin::FreshInitialized,
            },
        ))
    }

    fn open_valid_existing(path: &Path) -> Result<(Self, StoredSnapshot), StorageError> {
        // SQLite may create WAL index files even for SQLITE_OPEN_READ_ONLY. Validate
        // a private byte copy so rejected existing paths remain completely untouched.
        let validation_copy = ReadOnlyValidationCopy::new(path)?;
        let read_only = Connection::open_with_flags(
            validation_copy.database_path(),
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )
        .map_err(|_| StorageError::OpenFailed)?;
        let stored = validate_read_only(&read_only)?;
        drop(read_only);
        drop(validation_copy);

        let connection = open_writable(path, false)?;
        configure_durability(&connection)?;
        let checksum = sha256_hex(
            &stored
                .snapshot
                .to_canonical_bytes()
                .map_err(StorageError::Snapshot)?,
        );
        let store = Self {
            connection,
            last_sequence: stored.capture_sequence,
            last_revision: stored.snapshot.revision.get(),
            last_checksum: checksum,
        };
        Ok((store, stored))
    }

    pub fn commit(&mut self, sequence: u64, snapshot: &SnapshotV1) -> Result<(), StorageError> {
        let prepared = PreparedSnapshot::new(sequence, snapshot)?;
        self.commit_prepared(&prepared)
    }

    fn commit_prepared(&mut self, prepared: &PreparedSnapshot) -> Result<(), StorageError> {
        if prepared.sequence < self.last_sequence {
            return Err(StorageError::StaleCapture);
        }
        if prepared.sequence == self.last_sequence {
            if prepared.checksum == self.last_checksum {
                return Ok(());
            }
            return Err(StorageError::SequenceConflict);
        }
        if prepared.revision < self.last_revision {
            return Err(StorageError::StaleCapture);
        }

        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(map_transaction_error)?;
        insert_prepared(&transaction, prepared)?;
        transaction.commit().map_err(map_transaction_error)?;
        self.last_sequence = prepared.sequence;
        self.last_revision = prepared.revision;
        self.last_checksum.clone_from(&prepared.checksum);
        Ok(())
    }

    pub fn last_sequence(&self) -> u64 {
        self.last_sequence
    }

    pub fn last_revision(&self) -> u64 {
        self.last_revision
    }
}

static VALIDATION_COPY_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug)]
struct ReadOnlyValidationCopy {
    directory: std::path::PathBuf,
    database: std::path::PathBuf,
}

impl ReadOnlyValidationCopy {
    fn new(source: &Path) -> Result<Self, StorageError> {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let mut sequence = 0u32;
        let directory = loop {
            if sequence >= 100 {
                return Err(StorageError::IoFailed);
            }
            let counter = VALIDATION_COPY_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let candidate = std::env::temp_dir().join(format!(
                "paperclip-game-readonly-validation-{}-{unique}-{counter}",
                std::process::id()
            ));
            match std::fs::create_dir(&candidate) {
                Ok(()) => break candidate,
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    sequence += 1;
                }
                Err(_) => return Err(StorageError::IoFailed),
            }
        };
        let database = directory.join("snapshot.sqlite3");
        let copy = Self {
            directory,
            database,
        };
        copy.populate(source)?;
        Ok(copy)
    }

    fn populate(&self, source: &Path) -> Result<(), StorageError> {
        std::fs::copy(source, &self.database).map_err(|_| StorageError::IoFailed)?;
        copy_sidecar(source, &self.database, "-wal")?;
        copy_sidecar(source, &self.database, "-shm")?;
        Ok(())
    }

    fn database_path(&self) -> &Path {
        &self.database
    }
}

impl Drop for ReadOnlyValidationCopy {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.directory);
    }
}

fn copy_sidecar(source: &Path, destination: &Path, suffix: &str) -> Result<(), StorageError> {
    let mut source = source.as_os_str().to_os_string();
    source.push(suffix);
    let mut destination = destination.as_os_str().to_os_string();
    destination.push(suffix);
    match std::fs::copy(source, destination) {
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(StorageError::IoFailed),
    }
}

fn open_writable(path: &Path, create: bool) -> Result<Connection, StorageError> {
    let mut flags = OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX;
    if create {
        flags |= OpenFlags::SQLITE_OPEN_CREATE;
    }
    Connection::open_with_flags(path, flags).map_err(|_| StorageError::OpenFailed)
}

fn configure_durability(connection: &Connection) -> Result<(), StorageError> {
    let journal: String = connection
        .query_row("PRAGMA journal_mode = WAL", [], |row| row.get(0))
        .map_err(|_| StorageError::DurabilityFailure)?;
    if !journal.eq_ignore_ascii_case("wal") {
        return Err(StorageError::DurabilityFailure);
    }
    connection
        .pragma_update(None, "synchronous", "FULL")
        .map_err(|_| StorageError::DurabilityFailure)?;
    connection
        .busy_timeout(DEFAULT_BUSY_TIMEOUT)
        .map_err(|_| StorageError::DurabilityFailure)
}

fn validate_read_only(connection: &Connection) -> Result<StoredSnapshot, StorageError> {
    connection
        .query_row("PRAGMA schema_version", [], |_| Ok(()))
        .map_err(|_| StorageError::InvalidDatabase)?;
    let schema_version: i64 = connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(|_| StorageError::InvalidDatabase)?;
    if schema_version != SCHEMA_VERSION {
        return Err(StorageError::UnsupportedSchemaVersion);
    }

    let raw_rows = (|| -> Result<Vec<Vec<RawValue>>, rusqlite::Error> {
        let mut statement = connection.prepare(
            "SELECT slot, snapshot_version, revision, capture_sequence, payload, checksum
             FROM game_snapshot",
        )?;
        let rows = statement.query_map([], |row| {
            (0..6)
                .map(|index| row.get_ref(index).map(RawValue::from))
                .collect::<Result<Vec<_>, _>>()
        })?;
        rows.collect()
    })()
    .map_err(|_| StorageError::InvalidSchema)?;
    if raw_rows.len() != 1 {
        return Err(StorageError::InvalidSchema);
    }
    let row = &raw_rows[0];
    if !matches!(&row[0], RawValue::Text(slot) if slot == DEFAULT_ROW.as_bytes()) {
        return Err(StorageError::InvalidMetadata);
    }
    let snapshot_version = metadata_integer(&row[1])?;
    if snapshot_version != i64::from(SNAPSHOT_VERSION) {
        return Err(StorageError::UnsupportedSnapshotVersion);
    }
    let revision = metadata_integer(&row[2])? as u64;
    let capture_sequence = metadata_integer(&row[3])? as u64;
    let payload = match &row[4] {
        RawValue::Text(payload) => payload.as_slice(),
        _ => return Err(StorageError::WrongStoragePrimitive),
    };
    let checksum = match &row[5] {
        RawValue::Text(checksum) => {
            std::str::from_utf8(checksum).map_err(|_| StorageError::InvalidChecksum)?
        }
        _ => return Err(StorageError::WrongStoragePrimitive),
    };
    if checksum.len() != 64
        || !checksum
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(StorageError::InvalidChecksum);
    }
    if sha256_hex(payload) != *checksum {
        return Err(StorageError::ChecksumMismatch);
    }
    let snapshot = SnapshotV1::from_canonical_bytes(payload).map_err(StorageError::Snapshot)?;
    if snapshot.snapshot_version != SNAPSHOT_VERSION || snapshot.revision.get() != revision {
        return Err(StorageError::InvalidMetadata);
    }
    Ok(StoredSnapshot {
        snapshot,
        capture_sequence,
        origin: LoadOrigin::Restored,
    })
}

#[derive(Debug)]
enum RawValue {
    Null,
    Integer(i64),
    Real,
    Text(Vec<u8>),
    Blob,
}

impl From<ValueRef<'_>> for RawValue {
    fn from(value: ValueRef<'_>) -> Self {
        match value {
            ValueRef::Null => Self::Null,
            ValueRef::Integer(value) => Self::Integer(value),
            ValueRef::Real(_) => Self::Real,
            ValueRef::Text(value) => Self::Text(value.to_vec()),
            ValueRef::Blob(_) => Self::Blob,
        }
    }
}

fn metadata_integer(value: &RawValue) -> Result<i64, StorageError> {
    match value {
        RawValue::Integer(value)
            if *value >= 0
                && u64::try_from(*value).unwrap_or(u64::MAX) <= MAX_SAFE_JSON_INTEGER =>
        {
            Ok(*value)
        }
        RawValue::Integer(_) => Err(StorageError::InvalidMetadata),
        _ => Err(StorageError::WrongStoragePrimitive),
    }
}

fn insert_prepared(
    transaction: &rusqlite::Transaction<'_>,
    prepared: &PreparedSnapshot,
) -> Result<(), StorageError> {
    let revision = i64::try_from(prepared.revision).map_err(|_| StorageError::InvalidMetadata)?;
    let sequence = i64::try_from(prepared.sequence).map_err(|_| StorageError::SequenceExhausted)?;
    let changed = transaction
        .execute(
            UPSERT_SNAPSHOT,
            rusqlite::params![
                i64::from(SNAPSHOT_VERSION),
                revision,
                sequence,
                prepared.payload,
                prepared.checksum
            ],
        )
        .map_err(map_transaction_error)?;
    if changed != 1 {
        return Err(StorageError::TransactionFailed);
    }
    Ok(())
}

fn map_transaction_error(error: rusqlite::Error) -> StorageError {
    if error.sqlite_error_code().is_some_and(|code| {
        matches!(
            code,
            rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked
        )
    }) {
        StorageError::DatabaseBusy
    } else {
        StorageError::TransactionFailed
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(64);
    for byte in digest {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    output
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct WorkerOptions {
    pub max_attempts: u32,
    pub initial_backoff: Duration,
    pub maximum_backoff: Duration,
}

impl Default for WorkerOptions {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            initial_backoff: Duration::from_millis(50),
            maximum_backoff: Duration::from_millis(200),
        }
    }
}

struct QueueState {
    pending: Option<PreparedSnapshot>,
    next_sequence: u64,
    newest_revision: u64,
    closing: bool,
}

struct SharedQueue {
    state: Mutex<QueueState>,
    wake: Condvar,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SubmitError {
    Snapshot(SnapshotError),
    StaleCapture,
    SequenceExhausted,
    WorkerClosed,
    InvalidWorkerOptions,
}

impl fmt::Display for SubmitError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Snapshot(_) => "snapshot capture could not be encoded",
            Self::StaleCapture => "out-of-order snapshot capture was rejected",
            Self::SequenceExhausted => "snapshot sequence exhausted its safe range",
            Self::WorkerClosed => "persistence worker is closed",
            Self::InvalidWorkerOptions => "persistence worker options are invalid",
        })
    }
}

impl Error for SubmitError {}

impl From<SnapshotError> for SubmitError {
    fn from(error: SnapshotError) -> Self {
        Self::Snapshot(error)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkerStartError {
    InvalidOptions,
    ThreadSpawnFailed,
}

impl fmt::Display for WorkerStartError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::InvalidOptions => "persistence worker options are invalid",
            Self::ThreadSpawnFailed => "persistence worker thread could not start",
        })
    }
}

impl Error for WorkerStartError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkerShutdownError {
    WorkerPanicked,
}

impl fmt::Display for WorkerShutdownError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::WorkerPanicked => {
                formatter.write_str("persistence worker terminated unexpectedly")
            }
        }
    }
}

impl Error for WorkerShutdownError {}

/// The observer canonicalizes complete writer views, locks a tiny latest-slot,
/// and returns. A dedicated thread owns every blocking SQLite call.
pub struct PersistenceWorker {
    shared: Arc<SharedQueue>,
    health: PersistenceHealth,
    thread: Option<JoinHandle<()>>,
}

impl PersistenceWorker {
    pub fn start(
        mut store: SnapshotStore,
        health: PersistenceHealth,
        options: WorkerOptions,
    ) -> Result<Self, WorkerStartError> {
        if options.max_attempts == 0 || options.maximum_backoff < options.initial_backoff {
            return Err(WorkerStartError::InvalidOptions);
        }
        let shared = Arc::new(SharedQueue {
            state: Mutex::new(QueueState {
                pending: None,
                next_sequence: store.last_sequence(),
                newest_revision: store.last_revision(),
                closing: false,
            }),
            wake: Condvar::new(),
        });
        let worker_shared = Arc::clone(&shared);
        let worker_health = health.clone();
        let thread = thread::Builder::new()
            .name("paperclip-sqlite-writer".to_owned())
            .spawn(move || {
                worker_loop(&mut store, worker_shared, worker_health, options);
            })
            .map_err(|_| WorkerStartError::ThreadSpawnFailed)?;
        Ok(Self {
            shared,
            health,
            thread: Some(thread),
        })
    }

    pub fn submit(&self, snapshot: SnapshotV1) -> Result<u64, SubmitError> {
        let revision = snapshot.revision.get();
        let update_count = snapshot.clock.update_count.get();
        // Encoding and digest work occurs before taking the queue mutex.
        let payload = snapshot.to_canonical_bytes()?;
        let encoded = PreparedSnapshot {
            sequence: 0,
            revision,
            update_count,
            checksum: sha256_hex(&payload),
            payload: String::from_utf8(payload).map_err(|_| SnapshotError::EncodingFailed)?,
        };
        let sequence = {
            let mut queue = lock_queue(&self.shared);
            if queue.closing {
                return Err(SubmitError::WorkerClosed);
            }
            if revision < queue.newest_revision {
                return Err(SubmitError::StaleCapture);
            }
            let next = queue
                .next_sequence
                .checked_add(1)
                .filter(|value| *value <= MAX_SAFE_JSON_INTEGER)
                .ok_or(SubmitError::SequenceExhausted)?;
            let mut prepared = encoded;
            prepared.sequence = next;
            queue.next_sequence = next;
            queue.newest_revision = revision;
            // Replacing an unsent full snapshot is safe; the in-flight write is untouched.
            queue.pending = Some(prepared);
            // Keep queue/health order coherent while never holding this lock over I/O.
            self.health.captured(revision, next, update_count);
            next
        };
        self.shared.wake.notify_one();
        Ok(sequence)
    }

    pub fn health(&self) -> HealthSnapshot {
        self.health.snapshot()
    }

    /// Bounded best effort: finish the in-flight transaction and latest pending
    /// snapshot (including configured retries), then join the sole SQL thread.
    pub fn shutdown(mut self) -> Result<HealthSnapshot, WorkerShutdownError> {
        {
            let mut queue = lock_queue(&self.shared);
            queue.closing = true;
        }
        self.shared.wake.notify_one();
        let result = self
            .thread
            .take()
            .expect("shutdown owns the worker thread")
            .join()
            .map_err(|_| WorkerShutdownError::WorkerPanicked);
        self.health.stopped();
        result.map(|()| self.health.snapshot())
    }
}

impl Drop for PersistenceWorker {
    fn drop(&mut self) {
        if self.thread.is_some() {
            lock_queue(&self.shared).closing = true;
            self.shared.wake.notify_one();
        }
    }
}

fn worker_loop(
    store: &mut SnapshotStore,
    shared: Arc<SharedQueue>,
    health: PersistenceHealth,
    options: WorkerOptions,
) {
    loop {
        let job = {
            let mut queue = lock_queue(&shared);
            while queue.pending.is_none() && !queue.closing {
                queue = shared
                    .wake
                    .wait(queue)
                    .unwrap_or_else(|error| error.into_inner());
            }
            match queue.pending.take() {
                Some(job) => {
                    health.pending_taken();
                    job
                }
                None if queue.closing => break,
                None => continue,
            }
        };

        for attempt in 1..=options.max_attempts {
            health.write_started(attempt, attempt > 1);
            match store.commit_prepared(&job) {
                Ok(()) => {
                    health.committed(job.revision, job.sequence, job.update_count);
                    break;
                }
                Err(error) => {
                    let will_retry = attempt < options.max_attempts;
                    health.write_failed(
                        PersistenceFailure::from_storage(error),
                        will_retry,
                        attempt.saturating_add(1),
                    );
                    if !will_retry {
                        break;
                    }
                    let shift = attempt.saturating_sub(1).min(31);
                    let backoff = options
                        .initial_backoff
                        .saturating_mul(1u32 << shift)
                        .min(options.maximum_backoff);
                    thread::sleep(backoff);
                }
            }
        }
    }
}

fn lock_queue(shared: &SharedQueue) -> MutexGuard<'_, QueueState> {
    shared
        .state
        .lock()
        .unwrap_or_else(|error| error.into_inner())
}

const UPDATES_PER_SNAPSHOT: u64 =
    (DEFAULT_SNAPSHOT_INTERVAL.as_nanos() / UPDATE_QUANTUM_NANOS) as u64;

#[derive(Debug)]
pub enum RuntimePersistenceStartError {
    NoRuntime,
    Worker(WorkerStartError),
}

impl fmt::Display for RuntimePersistenceStartError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::NoRuntime => "runtime persistence must start inside a Tokio runtime",
            Self::Worker(_) => "persistence worker initialization failed",
        })
    }
}

impl Error for RuntimePersistenceStartError {}

#[derive(Debug)]
pub enum RuntimePersistenceError {
    Capture(SnapshotError),
    Submit(SubmitError),
    WorkerShutdown(WorkerShutdownError),
    PublisherTaskEnded,
}

impl fmt::Display for RuntimePersistenceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Capture(_) => "final snapshot capture failed",
            Self::Submit(error) => {
                return write!(formatter, "final snapshot was not queued: {error}");
            }
            Self::WorkerShutdown(_) => "persistence worker shutdown failed",
            Self::PublisherTaskEnded => "snapshot publisher terminated unexpectedly",
        })
    }
}

impl Error for RuntimePersistenceError {}

/// Owns the asynchronous observer and SQLite worker for one ordinary runtime.
/// The caller supplies the final view only after the API's accepted-work drain.
pub struct RuntimePersistence {
    health: PersistenceHealth,
    final_view: Option<oneshot::Sender<RuntimeView>>,
    publisher: Option<AsyncJoinHandle<Result<HealthSnapshot, RuntimePersistenceError>>>,
}

impl RuntimePersistence {
    pub fn start(
        runtime: &RuntimeHandle,
        store: SnapshotStore,
        committed_revision: u64,
        committed_sequence: u64,
    ) -> Result<Self, RuntimePersistenceStartError> {
        let executor = tokio::runtime::Handle::try_current()
            .map_err(|_| RuntimePersistenceStartError::NoRuntime)?;
        let mut views = runtime.subscribe();
        let initial_update_count = views.borrow_and_update().game.clock.update_count();
        let health = PersistenceHealth::new_at_update(
            DEFAULT_SNAPSHOT_INTERVAL,
            committed_revision,
            committed_sequence,
            initial_update_count,
        );
        let worker = PersistenceWorker::start(store, health.clone(), WorkerOptions::default())
            .map_err(RuntimePersistenceStartError::Worker)?;
        let (final_view, final_receiver) = oneshot::channel();
        let publisher = executor.spawn(run_snapshot_publisher(
            views,
            worker,
            health.clone(),
            final_receiver,
            initial_update_count,
        ));
        Ok(Self {
            health,
            final_view: Some(final_view),
            publisher: Some(publisher),
        })
    }

    pub fn health(&self) -> PersistenceHealth {
        self.health.clone()
    }

    pub async fn shutdown(
        mut self,
        final_view: RuntimeView,
    ) -> Result<HealthSnapshot, RuntimePersistenceError> {
        if let Some(sender) = self.final_view.take() {
            let _ = sender.send(final_view);
        }
        self.publisher
            .take()
            .expect("runtime persistence owns one publisher")
            .await
            .map_err(|_| RuntimePersistenceError::PublisherTaskEnded)?
    }
}

async fn run_snapshot_publisher(
    mut views: tokio::sync::watch::Receiver<RuntimeView>,
    worker: PersistenceWorker,
    health: PersistenceHealth,
    mut final_view: oneshot::Receiver<RuntimeView>,
    initial_update_count: u64,
) -> Result<HealthSnapshot, RuntimePersistenceError> {
    // Subscribe/read synchronously in start(), not on this task's first poll.
    // Otherwise fast fake time can finish the first interval before observation.
    let mut last_update = initial_update_count;
    let mut updates_since_save = 0_u64;
    let final_view = loop {
        tokio::select! {
            biased;
            requested = &mut final_view => {
                break requested.unwrap_or_else(|_| views.borrow_and_update().clone());
            }
            changed = views.changed() => {
                if changed.is_err() {
                    break views.borrow_and_update().clone();
                }
                let view = views.borrow_and_update().clone();
                let update_count = view.game.clock.update_count();
                health.observe(update_count);
                let new_updates = update_count.saturating_sub(last_update);
                last_update = update_count;
                updates_since_save = updates_since_save.saturating_add(new_updates);
                if updates_since_save >= UPDATES_PER_SNAPSHOT {
                    if let Err(error) = capture_and_submit(&worker, &view) {
                        note_capture_failure(&health, &error);
                    }
                    updates_since_save = 0;
                }
            }
        }
    };
    let captured = capture_and_submit(&worker, &final_view);
    if let Err(error) = &captured {
        note_capture_failure(&health, error);
    }
    let stopped = worker
        .shutdown()
        .map_err(RuntimePersistenceError::WorkerShutdown);
    match (captured, stopped) {
        (Err(error), _) => Err(error),
        (Ok(_), Err(error)) => Err(error),
        (Ok(_), Ok(health)) => Ok(health),
    }
}

fn capture_and_submit(
    worker: &PersistenceWorker,
    view: &RuntimeView,
) -> Result<u64, RuntimePersistenceError> {
    let snapshot =
        SnapshotV1::capture(&view.game, view.revision).map_err(RuntimePersistenceError::Capture)?;
    worker
        .submit(snapshot)
        .map_err(RuntimePersistenceError::Submit)
}

fn note_capture_failure(health: &PersistenceHealth, error: &RuntimePersistenceError) {
    let failure = match error {
        RuntimePersistenceError::Capture(_) => PersistenceFailure::InvalidSnapshot,
        RuntimePersistenceError::Submit(SubmitError::StaleCapture) => {
            PersistenceFailure::StaleCapture
        }
        RuntimePersistenceError::Submit(SubmitError::SequenceExhausted) => {
            PersistenceFailure::SequenceConflict
        }
        RuntimePersistenceError::Submit(_) => PersistenceFailure::CommitOutcomeUnknown,
        RuntimePersistenceError::WorkerShutdown(_)
        | RuntimePersistenceError::PublisherTaskEnded => PersistenceFailure::TransactionFailed,
    };
    health.write_failed(failure, false, 0);
}
