//! Typed persistence health without host paths, SQL text, payloads or raw I/O errors.

use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, Instant};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PersistencePhase {
    Ready,
    Saving,
    Retrying,
    Degraded,
    Stopped,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PersistenceFailure {
    DatabaseBusy,
    OpenFailed,
    SchemaFailure,
    InvalidSnapshot,
    ChecksumMismatch,
    TransactionFailed,
    CommitOutcomeUnknown,
    StaleCapture,
    SequenceConflict,
    ResourceLimit,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HealthSnapshot {
    pub live: bool,
    pub ready: bool,
    pub phase: PersistencePhase,
    pub last_committed_revision: Option<u64>,
    pub last_committed_sequence: Option<u64>,
    pub latest_captured_revision: Option<u64>,
    pub latest_captured_sequence: Option<u64>,
    pub write_in_progress: bool,
    pub pending_snapshot: bool,
    pub current_attempt: u32,
    pub consecutive_failures: u32,
    pub last_failure: Option<PersistenceFailure>,
    pub approximate_unsaved_elapsed: Option<Duration>,
    pub expected_loss_window: Duration,
    pub snapshot_overdue: bool,
}

#[derive(Debug)]
struct HealthState {
    live: bool,
    ready: bool,
    phase: PersistencePhase,
    last_committed_revision: Option<u64>,
    last_committed_sequence: Option<u64>,
    latest_captured_revision: Option<u64>,
    latest_captured_sequence: Option<u64>,
    write_in_progress: bool,
    pending_snapshot: bool,
    current_attempt: u32,
    consecutive_failures: u32,
    last_failure: Option<PersistenceFailure>,
    last_commit_time: Option<Instant>,
    snapshot_interval: Duration,
}

/// A cheap cloneable projection. The mutex never covers SQLite or JSON work.
#[derive(Clone, Debug)]
pub struct PersistenceHealth {
    inner: std::sync::Arc<Mutex<HealthState>>,
}

impl PersistenceHealth {
    pub fn new(
        snapshot_interval: Duration,
        committed_revision: u64,
        committed_sequence: u64,
    ) -> Self {
        Self {
            inner: std::sync::Arc::new(Mutex::new(HealthState {
                live: true,
                ready: true,
                phase: PersistencePhase::Ready,
                last_committed_revision: Some(committed_revision),
                last_committed_sequence: Some(committed_sequence),
                latest_captured_revision: Some(committed_revision),
                latest_captured_sequence: Some(committed_sequence),
                write_in_progress: false,
                pending_snapshot: false,
                current_attempt: 0,
                consecutive_failures: 0,
                last_failure: None,
                last_commit_time: Some(Instant::now()),
                snapshot_interval,
            })),
        }
    }

    pub fn snapshot(&self) -> HealthSnapshot {
        let state = self.lock();
        let approximate_unsaved_elapsed = state.last_commit_time.map(|then| then.elapsed());
        let snapshot_overdue = approximate_unsaved_elapsed
            .is_some_and(|elapsed| elapsed > state.snapshot_interval.saturating_mul(2));
        HealthSnapshot {
            live: state.live,
            ready: state.ready && !snapshot_overdue,
            phase: if snapshot_overdue && state.phase == PersistencePhase::Ready {
                PersistencePhase::Degraded
            } else {
                state.phase
            },
            last_committed_revision: state.last_committed_revision,
            last_committed_sequence: state.last_committed_sequence,
            latest_captured_revision: state.latest_captured_revision,
            latest_captured_sequence: state.latest_captured_sequence,
            write_in_progress: state.write_in_progress,
            pending_snapshot: state.pending_snapshot,
            current_attempt: state.current_attempt,
            consecutive_failures: state.consecutive_failures,
            last_failure: state.last_failure,
            approximate_unsaved_elapsed,
            expected_loss_window: state.snapshot_interval,
            snapshot_overdue,
        }
    }

    pub(crate) fn captured(&self, revision: u64, sequence: u64) {
        let mut state = self.lock();
        state.latest_captured_revision = Some(revision);
        state.latest_captured_sequence = Some(sequence);
        state.pending_snapshot = true;
    }

    pub(crate) fn pending_taken(&self) {
        self.lock().pending_snapshot = false;
    }

    pub(crate) fn write_started(&self, attempt: u32, retrying: bool) {
        let mut state = self.lock();
        state.write_in_progress = true;
        state.current_attempt = attempt;
        state.phase = if retrying {
            PersistencePhase::Retrying
        } else {
            PersistencePhase::Saving
        };
        state.ready = !retrying;
    }

    pub(crate) fn write_failed(
        &self,
        failure: PersistenceFailure,
        will_retry: bool,
        next_attempt: u32,
    ) {
        let mut state = self.lock();
        state.last_failure = Some(failure);
        state.consecutive_failures = state.consecutive_failures.saturating_add(1);
        state.current_attempt = if will_retry { next_attempt } else { 0 };
        state.write_in_progress = will_retry;
        state.ready = false;
        state.phase = if will_retry {
            PersistencePhase::Retrying
        } else {
            PersistencePhase::Degraded
        };
    }

    pub(crate) fn committed(&self, revision: u64, sequence: u64) {
        let mut state = self.lock();
        state.last_committed_revision = Some(revision);
        state.last_committed_sequence = Some(sequence);
        state.last_commit_time = Some(Instant::now());
        state.write_in_progress = false;
        state.current_attempt = 0;
        state.consecutive_failures = 0;
        state.last_failure = None;
        state.ready = true;
        state.phase = PersistencePhase::Ready;
    }

    pub(crate) fn stopped(&self) {
        let mut state = self.lock();
        state.live = false;
        state.ready = false;
        state.phase = PersistencePhase::Stopped;
        state.write_in_progress = false;
        state.pending_snapshot = false;
        state.current_attempt = 0;
    }

    fn lock(&self) -> MutexGuard<'_, HealthState> {
        self.inner.lock().unwrap_or_else(|error| error.into_inner())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_projection_tracks_pending_retry_overdue_recovery_and_stop() {
        let health = PersistenceHealth::new(Duration::from_secs(30), 4, 7);
        health.captured(9, 8);
        assert!(health.snapshot().pending_snapshot);
        health.pending_taken();
        health.write_started(1, false);
        assert_eq!(health.snapshot().phase, PersistencePhase::Saving);
        health.write_failed(PersistenceFailure::DatabaseBusy, true, 2);
        let retry = health.snapshot();
        assert!(!retry.ready);
        assert_eq!(retry.phase, PersistencePhase::Retrying);
        assert_eq!(retry.current_attempt, 2);
        assert_eq!(retry.last_committed_revision, Some(4));
        assert_eq!(retry.latest_captured_revision, Some(9));
        health.write_failed(PersistenceFailure::DatabaseBusy, false, 3);
        let failed = health.snapshot();
        assert_eq!(failed.current_attempt, 0);
        assert!(!failed.write_in_progress);
        assert!(failed.live);
        health.committed(9, 8);
        assert!(health.snapshot().ready);

        health.lock().last_commit_time = Instant::now().checked_sub(Duration::from_secs(90));
        let overdue = health.snapshot();
        assert!(overdue.snapshot_overdue);
        assert!(!overdue.ready);
        assert_eq!(overdue.phase, PersistencePhase::Degraded);
        assert!(overdue.approximate_unsaved_elapsed.is_some_and(|elapsed| {
            (Duration::from_secs(90)..Duration::from_secs(91)).contains(&elapsed)
        }));
        health.committed(10, 9);
        assert!(!health.snapshot().snapshot_overdue);
        health.stopped();
        assert!(!health.snapshot().live);
        assert_eq!(health.snapshot().last_committed_revision, Some(10));
    }
}
