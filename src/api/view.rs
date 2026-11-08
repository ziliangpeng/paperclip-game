//! Pure public projection of an immutable runtime snapshot.

use crate::game::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use crate::game::clock::ClockState;
use crate::game::state::ProState;
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
            game: ProductionView::from(&snapshot.game.pro),
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

impl From<&ProState> for ProductionView {
    fn from(state: &ProState) -> Self {
        Self {
            lifetime_clips: state.lifetime_clips.clone(),
            unsold_clips: state.unsold_clips.clone(),
            unused_clips: state.unused_clips.clone(),
            wire: state.wire.clone(),
            funds: state.funds.clone(),
            wire_spool_length: state.wire_spool_length.clone(),
            wire_quote: state.wire_quote.clone(),
            price_per_clip: state.price_per_clip.clone(),
            marketing_level: state.marketing_level.clone(),
            trust: state.trust.clone(),
            processors: state.processors.clone(),
            memory: state.memory.clone(),
            computing_hidden: state.computing_hidden,
            projects_hidden: state.projects_hidden,
            auto_clipper_revealed: state.auto_clipper_revealed,
            auto_clippers: state.auto_clippers.clone(),
            auto_clipper_cost: state.auto_clipper_cost.clone(),
        }
    }
}
