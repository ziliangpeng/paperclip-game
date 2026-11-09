//! Fail-closed state acquisition before the authoritative runtime starts.

use crate::game::rng::GameRng;
use crate::game::state::GameState;
use crate::persistence::{LoadOrigin, SnapshotStore, StorageError};
use crate::snapshot::{Snapshot, SnapshotError};
use std::error::Error;
use std::fmt;
use std::path::Path;

#[derive(Debug)]
pub struct StartupSnapshot {
    pub state: GameState,
    pub revision: u64,
    pub capture_sequence: u64,
    pub origin: LoadOrigin,
    pub store: SnapshotStore,
}

/// The fresh candidate is never applied when an existing row is restored. Every
/// process still obtains fresh entropy later for its independent opaque run id.
pub fn load_or_initialize(path: &Path) -> Result<StartupSnapshot, StartupError> {
    let fresh = GameState::fresh(GameRng::from_entropy().map_err(StartupError::Entropy)?);
    let fresh = Snapshot::capture(&fresh, 0).map_err(StartupError::Snapshot)?;
    let (store, stored) =
        SnapshotStore::open_or_initialize(path, &fresh).map_err(StartupError::Storage)?;
    let recovered = stored.snapshot.restore().map_err(StartupError::Snapshot)?;
    Ok(StartupSnapshot {
        state: recovered.state,
        revision: recovered.revision,
        capture_sequence: stored.capture_sequence,
        origin: stored.origin,
        store,
    })
}

#[derive(Debug)]
pub enum StartupError {
    Entropy(getrandom::Error),
    Snapshot(SnapshotError),
    Storage(StorageError),
}

impl fmt::Display for StartupError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Entropy(_) => "operating-system entropy is unavailable",
            Self::Snapshot(_) => "validated snapshot could not be restored",
            Self::Storage(error) => {
                return write!(formatter, "persistence startup failed: {error}");
            }
        })
    }
}

impl Error for StartupError {}
