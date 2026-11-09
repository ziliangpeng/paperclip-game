//! Pure public projection of an immutable runtime snapshot.

use crate::game::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use crate::game::clock::ClockState;
use crate::game::state::ProState;
use crate::health::{HealthSnapshot, PersistenceFailure, PersistencePhase};
use crate::runtime::RuntimeView;
use serde::{Deserialize, Serialize};
use std::error::Error;
use std::fmt;

pub const GAME_VIEW_SCHEMA_VERSION: u64 = 1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GameView {
    pub schema_version: SafeU64,
    pub run_id: String,
    pub revision: SafeU64,
    pub clock: ClockView,
    pub game: ProductionView,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HealthView {
    pub live: bool,
    pub ready: bool,
    pub phase: PersistencePhase,
    pub last_committed_revision: Option<SafeU64>,
    pub last_committed_sequence: Option<SafeU64>,
    pub latest_captured_revision: Option<SafeU64>,
    pub latest_captured_sequence: Option<SafeU64>,
    pub pending_snapshot_count: u8,
    pub write_in_progress: bool,
    pub current_attempt: u32,
    pub consecutive_failures: u32,
    pub snapshot_overdue: bool,
    pub last_failure_code: Option<PersistenceFailure>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClockView {
    pub update_count: SafeU64,
    pub fast_phase: u8,
    pub second_phase: u8,
    pub slow_phase: u16,
    pub combat_remainder_nanos: u32,
    pub combat_pulses: SafeU64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProductionView {
    pub lifetime_clips: NonNegativeAmount,
    pub unsold_clips: NonNegativeAmount,
    pub unused_clips: NonNegativeAmount,
    pub wire: NonNegativeAmount,
    pub funds: Amount,
    pub wire_spool_length: NonNegativeAmount,
    pub wire_quote: Amount,
    pub price_per_clip: Amount,
    pub marketing_level: IntegralAmount,
    pub demand: NonNegativeAmount,
    pub marketing_cost: Amount,
    pub clips_sold: NonNegativeAmount,
    pub income: Amount,
    pub last_sale_revenue: Amount,
    pub trust: IntegralAmount,
    pub processors: IntegralAmount,
    pub memory: IntegralAmount,
    pub computing_hidden: bool,
    pub projects_hidden: bool,
    pub auto_clipper_revealed: bool,
    pub auto_clippers: IntegralAmount,
    pub auto_clipper_cost: Amount,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ViewLimitError;

impl fmt::Display for ViewLimitError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a public counter exceeded the checked JSON integer range")
    }
}

impl Error for ViewLimitError {}

impl GameView {
    /// Clone only public logical fields. This performs no RNG draw, retry-table
    /// access, persistence access, clock advancement, or game mutation.
    pub fn from_runtime(snapshot: &RuntimeView) -> Result<Self, ViewLimitError> {
        Ok(Self {
            schema_version: SafeU64::new(GAME_VIEW_SCHEMA_VERSION).map_err(|_| ViewLimitError)?,
            run_id: snapshot.run_id.clone(),
            revision: SafeU64::new(snapshot.revision).map_err(|_| ViewLimitError)?,
            clock: ClockView::try_from(&snapshot.game.clock)?,
            game: ProductionView::try_from(&snapshot.game.pro)?,
        })
    }
}

impl HealthView {
    fn checked_counter(value: Option<u64>) -> Result<Option<SafeU64>, ViewLimitError> {
        value
            .map(|value| SafeU64::new(value).map_err(|_| ViewLimitError))
            .transpose()
    }
}

impl TryFrom<HealthSnapshot> for HealthView {
    type Error = ViewLimitError;

    fn try_from(health: HealthSnapshot) -> Result<Self, Self::Error> {
        Ok(Self {
            live: health.live,
            ready: health.ready,
            phase: health.phase,
            last_committed_revision: Self::checked_counter(health.last_committed_revision)?,
            last_committed_sequence: Self::checked_counter(health.last_committed_sequence)?,
            latest_captured_revision: Self::checked_counter(health.latest_captured_revision)?,
            latest_captured_sequence: Self::checked_counter(health.latest_captured_sequence)?,
            pending_snapshot_count: u8::from(health.pending_snapshot),
            write_in_progress: health.write_in_progress,
            current_attempt: health.current_attempt,
            consecutive_failures: health.consecutive_failures,
            snapshot_overdue: health.snapshot_overdue,
            last_failure_code: health.last_failure,
        })
    }
}

impl TryFrom<&ClockState> for ClockView {
    type Error = ViewLimitError;

    fn try_from(clock: &ClockState) -> Result<Self, Self::Error> {
        Ok(Self {
            update_count: SafeU64::new(clock.update_count()).map_err(|_| ViewLimitError)?,
            fast_phase: clock.fast_phase(),
            second_phase: clock.second_phase(),
            slow_phase: clock.slow_phase(),
            combat_remainder_nanos: clock.combat_remainder_nanos(),
            combat_pulses: SafeU64::new(clock.combat_pulses()).map_err(|_| ViewLimitError)?,
        })
    }
}

impl TryFrom<&ProState> for ProductionView {
    type Error = ViewLimitError;

    fn try_from(state: &ProState) -> Result<Self, Self::Error> {
        Ok(Self {
            lifetime_clips: state.lifetime_clips.clone(),
            unsold_clips: state.unsold_clips.clone(),
            unused_clips: state.unused_clips.clone(),
            wire: state.wire.clone(),
            funds: state.funds.clone(),
            wire_spool_length: state.wire_spool_length.clone(),
            wire_quote: state.wire_quote.clone(),
            price_per_clip: state.price_per_clip.clone(),
            marketing_level: state.marketing_level.clone(),
            demand: state.demand.clone(),
            marketing_cost: state.marketing_cost().ok_or(ViewLimitError)?,
            clips_sold: state.clips_sold.clone(),
            income: state.income.clone(),
            last_sale_revenue: state.last_sale_revenue.clone(),
            trust: state.trust.clone(),
            processors: state.processors.clone(),
            memory: state.memory.clone(),
            computing_hidden: state.computing_hidden,
            projects_hidden: state.projects_hidden,
            auto_clipper_revealed: state.auto_clipper_revealed,
            auto_clippers: state.auto_clippers.clone(),
            auto_clipper_cost: state.auto_clipper_cost.clone(),
        })
    }
}
