//! Typed persistence health without host paths, SQL text, payloads or raw I/O errors.

use crate::game::clock::UPDATE_QUANTUM_NANOS;
use serde::{Deserialize, Serialize};
use std::sync::{Mutex, MutexGuard};
use std::time::Duration;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PersistencePhase {
    Unconfigured,
    Ready,
    Saving,
    Retrying,
    Degraded,
    Stopped,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
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
    last_commit_update: Option<u64>,
    latest_observed_update: Option<u64>,
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
        Self::new_at_update(snapshot_interval, committed_revision, committed_sequence, 0)
    }

    pub fn new_at_update(
        snapshot_interval: Duration,
        committed_revision: u64,
        committed_sequence: u64,
        initial_update_count: u64,
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
                last_commit_update: Some(initial_update_count),
                latest_observed_update: Some(initial_update_count),
                snapshot_interval,
            })),
        }
    }

    /// Explicit state for pure transport fixtures that have no configured store.
    /// Production startup does not use this constructor.
    pub fn unconfigured_for_testing(snapshot_interval: Duration) -> Self {
        Self {
            inner: std::sync::Arc::new(Mutex::new(HealthState {
                live: true,
                ready: false,
                phase: PersistencePhase::Unconfigured,
                last_committed_revision: None,
                last_committed_sequence: None,
                latest_captured_revision: None,
                latest_captured_sequence: None,
                write_in_progress: false,
                pending_snapshot: false,
                current_attempt: 0,
                consecutive_failures: 0,
                last_failure: None,
                last_commit_update: None,
                latest_observed_update: None,
                snapshot_interval,
            })),
        }
    }

    pub fn snapshot(&self) -> HealthSnapshot {
        let state = self.lock();
        let unsaved_updates = state
            .latest_observed_update
            .zip(state.last_commit_update)
            .map(|(observed, committed)| observed.saturating_sub(committed));
        let approximate_unsaved_elapsed = unsaved_updates.map(logical_duration);
        let update_tolerance = u64::try_from(
            (state.snapshot_interval.as_nanos() / UPDATE_QUANTUM_NANOS)
                .saturating_mul(2)
                .min(u128::from(u64::MAX)),
        )
        .unwrap_or(u64::MAX);
        // Overdue follows only the real runtime's published logical updates.
        // Downtime, host suspension and wall-clock jumps create no game progress.
        let snapshot_overdue = unsaved_updates.is_some_and(|updates| updates > update_tolerance);
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

    pub(crate) fn observe(&self, update_count: u64) {
        let mut state = self.lock();
        state.latest_observed_update = Some(
            state
                .latest_observed_update
                .map_or(update_count, |previous| previous.max(update_count)),
        );
    }

    pub(crate) fn captured(&self, revision: u64, sequence: u64, update_count: u64) {
        let mut state = self.lock();
        state.latest_captured_revision = Some(revision);
        state.latest_captured_sequence = Some(sequence);
        state.latest_observed_update = Some(
            state
                .latest_observed_update
                .map_or(update_count, |previous| previous.max(update_count)),
        );
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
        if retrying {
            state.ready = false;
        }
        // A fresh attempt after a degraded save stays unready until a real
        // commit clears the previous failure; healthy in-flight saves stay ready.
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

    pub(crate) fn committed(&self, revision: u64, sequence: u64, update_count: u64) {
        let mut state = self.lock();
        state.last_committed_revision = Some(revision);
        state.last_committed_sequence = Some(sequence);
        state.last_commit_update = Some(update_count);
        state.latest_observed_update = Some(
            state
                .latest_observed_update
                .map_or(update_count, |previous| previous.max(update_count)),
        );
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

fn logical_duration(updates: u64) -> Duration {
    let nanos = u128::from(updates) * UPDATE_QUANTUM_NANOS;
    Duration::new(
        u64::try_from(nanos / 1_000_000_000).unwrap_or(u64::MAX),
        u32::try_from(nanos % 1_000_000_000).unwrap_or(0),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_tracks_pending_retry_logical_overdue_recovery_and_stop() {
        let health = PersistenceHealth::new_at_update(Duration::from_secs(30), 4, 7, 100);
        health.captured(9, 8, 150);
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
        health.write_started(1, false);
        assert!(!health.snapshot().ready, "recovery requires a real commit");
        health.committed(9, 8, 150);
        assert!(health.snapshot().ready);

        health.observe(6_150);
        assert!(!health.snapshot().snapshot_overdue);
        health.observe(6_151);
        let overdue = health.snapshot();
        assert!(overdue.snapshot_overdue);
        assert!(!overdue.ready);
        assert_eq!(overdue.phase, PersistencePhase::Degraded);
        assert_eq!(
            overdue.approximate_unsaved_elapsed,
            Some(Duration::from_millis(60_010))
        );
        health.committed(10, 9, 6_151);
        assert!(!health.snapshot().snapshot_overdue);
        health.stopped();
        assert!(!health.snapshot().live);
        assert_eq!(health.snapshot().last_committed_revision, Some(10));

        let unconfigured = PersistenceHealth::unconfigured_for_testing(Duration::from_secs(30));
        let unavailable = unconfigured.snapshot();
        assert!(!unavailable.ready);
        assert_eq!(unavailable.phase, PersistencePhase::Unconfigured);
        assert_eq!(unavailable.last_committed_revision, None);
        assert_eq!(unavailable.latest_captured_revision, None);
        assert!(!unavailable.snapshot_overdue);
    }
}
