//! Strict snapshot payloads with explicit 1/2 -> 3 migration.
//!
//! Payload format versions and SQLite schema versions are independent concepts.
//! Current capture always emits version 3; supported historical V1/V2 payloads
//! retain their whole legacy state before current-format revalidation.

use crate::game::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use crate::game::clock::ClockState;
use crate::game::economy::refresh_demand;
use crate::game::evaluator::DECISION_LIMIT;
use crate::game::rng::{GameRng, RngStateError};
use crate::game::state::{GameState, ProState};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::error::Error;
use std::fmt;

pub const SNAPSHOT_VERSION: u8 = 3;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub snapshot_version: u8,
    pub revision: SafeU64,
    pub pro: ProSnapshot,
    pub clock: ClockSnapshot,
    pub rng_state: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProSnapshot {
    pub lifetime_clips: NonNegativeAmount,
    pub unsold_clips: NonNegativeAmount,
    pub unused_clips: NonNegativeAmount,
    pub wire: NonNegativeAmount,
    pub funds: Amount,
    pub wire_spool_length: NonNegativeAmount,
    pub wire_quote: Amount,
    pub price_per_clip: Amount,
    pub marketing_level: IntegralAmount,
    pub marketing_effectiveness: Amount,
    pub demand_boost: Amount,
    pub prestige_u: IntegralAmount,
    pub demand: NonNegativeAmount,
    pub clips_sold: NonNegativeAmount,
    pub income: Amount,
    pub last_sale_revenue: Amount,
    pub wire_base_price: Amount,
    pub wire_price_counter: SafeU64,
    pub wire_purchase_count: SafeU64,
    pub wire_inactivity_ticks: SafeU64,
    pub trust: IntegralAmount,
    pub processors: IntegralAmount,
    pub memory: IntegralAmount,
    pub computing_hidden: bool,
    pub projects_hidden: bool,
    pub auto_clipper_revealed: bool,
    pub auto_clippers: IntegralAmount,
    pub auto_clipper_cost: Amount,
    pub auto_clipper_rate: NonNegativeAmount,
    pub auto_clipper_production_accumulator: NonNegativeAmount,
    pub console_messages: [String; 5],
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct SnapshotV2 {
    snapshot_version: u8,
    revision: SafeU64,
    pro: ProSnapshotV2,
    clock: ClockSnapshot,
    rng_state: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct ProSnapshotV2 {
    lifetime_clips: NonNegativeAmount,
    unsold_clips: NonNegativeAmount,
    unused_clips: NonNegativeAmount,
    wire: NonNegativeAmount,
    funds: Amount,
    wire_spool_length: NonNegativeAmount,
    wire_quote: Amount,
    price_per_clip: Amount,
    marketing_level: IntegralAmount,
    marketing_effectiveness: Amount,
    demand_boost: Amount,
    prestige_u: IntegralAmount,
    demand: NonNegativeAmount,
    clips_sold: NonNegativeAmount,
    income: Amount,
    last_sale_revenue: Amount,
    wire_base_price: Amount,
    wire_price_counter: SafeU64,
    wire_purchase_count: SafeU64,
    wire_inactivity_ticks: SafeU64,
    trust: IntegralAmount,
    processors: IntegralAmount,
    memory: IntegralAmount,
    computing_hidden: bool,
    projects_hidden: bool,
    auto_clipper_revealed: bool,
    auto_clippers: IntegralAmount,
    auto_clipper_cost: Amount,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClockSnapshot {
    pub update_count: SafeU64,
    pub fast_phase: u8,
    pub second_phase: u8,
    pub slow_phase: u16,
    pub combat_remainder_nanos: u32,
    pub combat_pulses: SafeU64,
}

#[derive(Clone, Debug)]
pub struct RecoveredSnapshot {
    pub state: GameState,
    pub revision: u64,
}

#[derive(Deserialize)]
struct VersionEnvelope {
    snapshot_version: u8,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SnapshotV1 {
    snapshot_version: u8,
    revision: SafeU64,
    pro: ProSnapshotV1,
    clock: ClockSnapshot,
    rng_state: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ProSnapshotV1 {
    lifetime_clips: NonNegativeAmount,
    unsold_clips: NonNegativeAmount,
    unused_clips: NonNegativeAmount,
    wire: NonNegativeAmount,
    funds: Amount,
    wire_spool_length: NonNegativeAmount,
    wire_quote: Amount,
    price_per_clip: Amount,
    marketing_level: IntegralAmount,
    trust: IntegralAmount,
    processors: IntegralAmount,
    memory: IntegralAmount,
    computing_hidden: bool,
    projects_hidden: bool,
    auto_clipper_revealed: bool,
    auto_clippers: IntegralAmount,
    auto_clipper_cost: Amount,
}

impl Snapshot {
    pub fn capture(state: &GameState, revision: u64) -> Result<Self, SnapshotError> {
        let snapshot = Self {
            snapshot_version: SNAPSHOT_VERSION,
            revision: SafeU64::new(revision).map_err(|_| SnapshotError::IntegerOutOfRange)?,
            pro: ProSnapshot::from_state(&state.pro),
            clock: ClockSnapshot::from_state(&state.clock)?,
            rng_state: state.rng_state_hex(),
        };
        debug_assert_eq!(state.rng_state_hex(), snapshot.rng_state);
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn to_canonical_bytes(&self) -> Result<Vec<u8>, SnapshotError> {
        self.validate()?;
        serde_json::to_vec(self).map_err(|_| SnapshotError::EncodingFailed)
    }

    pub fn from_canonical_bytes(bytes: &[u8]) -> Result<Self, SnapshotError> {
        let text = std::str::from_utf8(bytes).map_err(|_| SnapshotError::InvalidUtf8)?;
        let envelope: VersionEnvelope = serde_json::from_str(text).map_err(classify_json_error)?;
        match envelope.snapshot_version {
            1 => {
                let legacy: SnapshotV1 = decode_strict_canonical(text)?;
                upgrade_v1(legacy)
            }
            2 => {
                let legacy: SnapshotV2 = decode_strict_canonical(text)?;
                upgrade_v2(legacy)
            }
            3 => {
                let snapshot: Self = decode_strict_canonical(text)?;
                snapshot.validate()?;
                Ok(snapshot)
            }
            _ => Err(SnapshotError::UnsupportedSnapshotVersion),
        }
    }

    pub fn restore(&self) -> Result<RecoveredSnapshot, SnapshotError> {
        self.validate()?;
        let clock = self.clock.to_state()?;
        let rng = GameRng::import_hex(&self.rng_state).map_err(map_rng_error)?;
        Ok(RecoveredSnapshot {
            state: GameState::from_snapshot_parts(self.pro.to_state()?, clock, rng),
            revision: self.revision.get(),
        })
    }

    fn validate(&self) -> Result<(), SnapshotError> {
        if self.snapshot_version != SNAPSHOT_VERSION {
            return Err(SnapshotError::UnsupportedSnapshotVersion);
        }
        self.clock.to_state()?;
        GameRng::import_hex(&self.rng_state).map_err(map_rng_error)?;
        let state = self.pro.to_state()?;
        validate_current_pro(&state)
    }
}

fn decode_strict_canonical<T: DeserializeOwned + Serialize>(
    text: &str,
) -> Result<T, SnapshotError> {
    let decoded: T = serde_json::from_str(text).map_err(classify_json_error)?;
    let canonical = serde_json::to_vec(&decoded).map_err(|_| SnapshotError::EncodingFailed)?;
    if canonical != text.as_bytes() {
        return Err(SnapshotError::NonCanonicalPayload);
    }
    Ok(decoded)
}

fn upgrade_v1(legacy: SnapshotV1) -> Result<Snapshot, SnapshotError> {
    let original = legacy.pro.to_state_partial()?;
    let pro = ProSnapshot::from_state(&original);
    upgrade_parts(legacy.revision, pro, legacy.clock, legacy.rng_state)
}

fn upgrade_v2(legacy: SnapshotV2) -> Result<Snapshot, SnapshotError> {
    let original = legacy.pro.to_state_partial()?;
    let pro = ProSnapshot::from_state(&original);
    upgrade_parts(legacy.revision, pro, legacy.clock, legacy.rng_state)
}

fn upgrade_parts(
    revision: SafeU64,
    mut pro: ProSnapshot,
    clock: ClockSnapshot,
    rng_state: String,
) -> Result<Snapshot, SnapshotError> {
    let mut state = pro.to_state()?;
    refresh_demand(&mut state).map_err(|_| SnapshotError::DomainViolation)?;
    pro.demand = state.demand;
    let snapshot = Snapshot {
        snapshot_version: SNAPSHOT_VERSION,
        revision,
        pro,
        clock,
        rng_state,
    };
    snapshot.validate()?;
    Ok(snapshot)
}

impl ProSnapshotV1 {
    fn to_state_partial(&self) -> Result<ProState, SnapshotError> {
        for count in [
            &self.marketing_level,
            &self.trust,
            &self.processors,
            &self.memory,
            &self.auto_clippers,
        ] {
            if count.amount().is_negative() {
                return Err(SnapshotError::DomainViolation);
            }
        }
        // Migration additions are initialized only after every old field is copied.
        let mut state = ProState::fresh();
        state.lifetime_clips = self.lifetime_clips.clone();
        state.unsold_clips = self.unsold_clips.clone();
        state.unused_clips = self.unused_clips.clone();
        state.wire = self.wire.clone();
        state.funds = self.funds.clone();
        state.wire_spool_length = self.wire_spool_length.clone();
        state.wire_quote = self.wire_quote.clone();
        state.price_per_clip = self.price_per_clip.clone();
        state.marketing_level = self.marketing_level.clone();
        state.trust = self.trust.clone();
        state.processors = self.processors.clone();
        state.memory = self.memory.clone();
        state.computing_hidden = self.computing_hidden;
        state.projects_hidden = self.projects_hidden;
        state.auto_clipper_revealed = self.auto_clipper_revealed;
        state.auto_clippers = self.auto_clippers.clone();
        state.auto_clipper_cost = self.auto_clipper_cost.clone();
        state.clips_sold = NonNegativeAmount::zero();
        state.income = Amount::zero();
        state.last_sale_revenue = Amount::zero();
        Ok(state)
    }
}

impl ProSnapshotV2 {
    fn to_state_partial(&self) -> Result<ProState, SnapshotError> {
        Ok(ProState {
            lifetime_clips: self.lifetime_clips.clone(),
            unsold_clips: self.unsold_clips.clone(),
            unused_clips: self.unused_clips.clone(),
            wire: self.wire.clone(),
            funds: self.funds.clone(),
            wire_spool_length: self.wire_spool_length.clone(),
            wire_quote: self.wire_quote.clone(),
            price_per_clip: self.price_per_clip.clone(),
            marketing_level: self.marketing_level.clone(),
            marketing_effectiveness: self.marketing_effectiveness.clone(),
            demand_boost: self.demand_boost.clone(),
            prestige_u: self.prestige_u.clone(),
            demand: self.demand.clone(),
            clips_sold: self.clips_sold.clone(),
            income: self.income.clone(),
            last_sale_revenue: self.last_sale_revenue.clone(),
            wire_base_price: self.wire_base_price.clone(),
            wire_price_counter: self.wire_price_counter,
            wire_purchase_count: self.wire_purchase_count,
            wire_inactivity_ticks: self.wire_inactivity_ticks,
            trust: self.trust.clone(),
            processors: self.processors.clone(),
            memory: self.memory.clone(),
            computing_hidden: self.computing_hidden,
            projects_hidden: self.projects_hidden,
            auto_clipper_revealed: self.auto_clipper_revealed,
            auto_clippers: self.auto_clippers.clone(),
            auto_clipper_cost: self.auto_clipper_cost.clone(),
            ..ProState::fresh()
        })
    }
}

impl ProSnapshot {
    fn from_state(state: &ProState) -> Self {
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
            marketing_effectiveness: state.marketing_effectiveness.clone(),
            demand_boost: state.demand_boost.clone(),
            prestige_u: state.prestige_u.clone(),
            demand: state.demand.clone(),
            clips_sold: state.clips_sold.clone(),
            income: state.income.clone(),
            last_sale_revenue: state.last_sale_revenue.clone(),
            wire_base_price: state.wire_base_price.clone(),
            wire_price_counter: state.wire_price_counter,
            wire_purchase_count: state.wire_purchase_count,
            wire_inactivity_ticks: state.wire_inactivity_ticks,
            trust: state.trust.clone(),
            processors: state.processors.clone(),
            memory: state.memory.clone(),
            computing_hidden: state.computing_hidden,
            projects_hidden: state.projects_hidden,
            auto_clipper_revealed: state.auto_clipper_revealed,
            auto_clippers: state.auto_clippers.clone(),
            auto_clipper_cost: state.auto_clipper_cost.clone(),
            auto_clipper_rate: state.auto_clipper_rate.clone(),
            auto_clipper_production_accumulator: state.auto_clipper_production_accumulator.clone(),
            console_messages: state.console_messages.clone(),
        }
    }

    fn to_state(&self) -> Result<ProState, SnapshotError> {
        Ok(ProState {
            lifetime_clips: self.lifetime_clips.clone(),
            unsold_clips: self.unsold_clips.clone(),
            unused_clips: self.unused_clips.clone(),
            wire: self.wire.clone(),
            funds: self.funds.clone(),
            wire_spool_length: self.wire_spool_length.clone(),
            wire_quote: self.wire_quote.clone(),
            price_per_clip: self.price_per_clip.clone(),
            marketing_level: self.marketing_level.clone(),
            marketing_effectiveness: self.marketing_effectiveness.clone(),
            demand_boost: self.demand_boost.clone(),
            prestige_u: self.prestige_u.clone(),
            demand: self.demand.clone(),
            clips_sold: self.clips_sold.clone(),
            income: self.income.clone(),
            last_sale_revenue: self.last_sale_revenue.clone(),
            wire_base_price: self.wire_base_price.clone(),
            wire_price_counter: self.wire_price_counter,
            wire_purchase_count: self.wire_purchase_count,
            wire_inactivity_ticks: self.wire_inactivity_ticks,
            trust: self.trust.clone(),
            processors: self.processors.clone(),
            memory: self.memory.clone(),
            computing_hidden: self.computing_hidden,
            projects_hidden: self.projects_hidden,
            auto_clipper_revealed: self.auto_clipper_revealed,
            auto_clippers: self.auto_clippers.clone(),
            auto_clipper_cost: self.auto_clipper_cost.clone(),
            auto_clipper_rate: self.auto_clipper_rate.clone(),
            auto_clipper_production_accumulator: self.auto_clipper_production_accumulator.clone(),
            console_messages: self.console_messages.clone(),
        })
    }
}

fn validate_current_pro(state: &ProState) -> Result<(), SnapshotError> {
    for count in [
        &state.marketing_level,
        &state.trust,
        &state.processors,
        &state.memory,
        &state.auto_clippers,
        &state.prestige_u,
    ] {
        if count.amount().is_negative() {
            return Err(SnapshotError::DomainViolation);
        }
    }
    // A legal producer purchase always reveals. Actual output and its partial-
    // second accumulator cannot exceed the whole request for the stored count.
    // Wire==0 says nothing about historical output and is deliberately unrelated.
    if (state.auto_clippers.amount() > &Amount::zero() && !state.auto_clipper_revealed)
        || state.auto_clipper_rate.amount() > state.auto_clippers.amount()
        || state.auto_clipper_production_accumulator.amount() > state.auto_clippers.amount()
    {
        return Err(SnapshotError::DomainViolation);
    }
    // These are conserved ledgers, not disjoint physical inventories: production
    // increments all three, then sales transfer Unsold into ClipsSold.
    // Equivalent to Unsold + ClipsSold == Lifetime, using checked nonnegative
    // arithmetic rather than overflow-prone fixed-width addition.
    let expected_sold = state
        .lifetime_clips
        .checked_sub(&state.unsold_clips)
        .map_err(|_| SnapshotError::DomainViolation)?;
    if state.unused_clips != state.lifetime_clips
        || state.unsold_clips > state.unused_clips
        || state.clips_sold > state.lifetime_clips
        || expected_sold != state.clips_sold
    {
        #[cfg(test)]
        eprintln!(
            "snapshot production invariant: unused={} lifetime={} unsold={} sold={}",
            state.unused_clips, state.lifetime_clips, state.unsold_clips, state.clips_sold
        );
        return Err(SnapshotError::DomainViolation);
    }
    if state.auto_clipper_cost < Amount::from_i128(5)
        || state.console_messages.iter().any(|message| {
            message.len() > 256 || !message.is_ascii() || message.chars().any(char::is_control)
        })
    {
        return Err(SnapshotError::DomainViolation);
    }
    if state.price_per_clip <= Amount::zero()
        || state.wire_base_price <= Amount::zero()
        || state.wire_quote <= Amount::zero()
        || state.wire_quote.clone().integral().is_err()
        || state.marketing_effectiveness < Amount::zero()
        || state.demand_boost < Amount::zero()
        || state.income.is_negative()
        || state.last_sale_revenue.is_negative()
    {
        #[cfg(test)]
        eprintln!(
            "snapshot scalar domain: price={} base={} quote={} effectiveness={} boost={} income={} last={}",
            state.price_per_clip,
            state.wire_base_price,
            state.wire_quote,
            state.marketing_effectiveness,
            state.demand_boost,
            state.income,
            state.last_sale_revenue
        );
        return Err(SnapshotError::DomainViolation);
    }
    if state.wire_base_price
        >= Amount::from_mantissa(
            num_bigint::BigInt::from(DECISION_LIMIT as u64) * Amount::from_i128(1).mantissa(),
        )
    {
        return Err(SnapshotError::DomainViolation);
    }
    let mut expected = state.clone();
    refresh_demand(&mut expected).map_err(|_| SnapshotError::DomainViolation)?;
    if expected.demand != state.demand || expected.marketing_cost().is_none() {
        #[cfg(test)]
        eprintln!(
            "snapshot derived mismatch: demand={} expected={} level={}",
            state.demand, expected.demand, state.marketing_level
        );
        return Err(SnapshotError::DomainViolation);
    }
    Ok(())
}

impl ClockSnapshot {
    fn from_state(state: &ClockState) -> Result<Self, SnapshotError> {
        Ok(Self {
            update_count: SafeU64::new(state.update_count())
                .map_err(|_| SnapshotError::IntegerOutOfRange)?,
            fast_phase: state.fast_phase(),
            second_phase: state.second_phase(),
            slow_phase: state.slow_phase(),
            combat_remainder_nanos: state.combat_remainder_nanos(),
            combat_pulses: SafeU64::new(state.combat_pulses())
                .map_err(|_| SnapshotError::IntegerOutOfRange)?,
        })
    }

    fn to_state(&self) -> Result<ClockState, SnapshotError> {
        ClockState::from_snapshot_parts(
            self.update_count.get(),
            self.fast_phase,
            self.second_phase,
            self.slow_phase,
            self.combat_remainder_nanos,
            self.combat_pulses.get(),
        )
        .map_err(|_| SnapshotError::InvalidClockState)
    }
}

fn classify_json_error(error: serde_json::Error) -> SnapshotError {
    let message = error.to_string();
    if message.starts_with("unknown field") {
        SnapshotError::UnknownField
    } else if message.starts_with("duplicate field") {
        SnapshotError::DuplicateField
    } else if message.starts_with("missing field") {
        SnapshotError::MissingField
    } else if message.contains("canonical Amount exceeds the decode limit") {
        SnapshotError::ResourceLimit
    } else if message.contains("invalid canonical Amount") {
        SnapshotError::NonCanonicalAmount
    } else if message.contains("integer exceeds the JSON-safe range") {
        SnapshotError::IntegerOutOfRange
    } else if message.contains("Amount must be nonnegative")
        || message.contains("Amount must be integral")
    {
        SnapshotError::DomainViolation
    } else if message.starts_with("invalid type:") {
        SnapshotError::WrongPrimitive
    } else if error.classify() == serde_json::error::Category::Data {
        SnapshotError::InvalidValue
    } else {
        SnapshotError::MalformedJson
    }
}

fn map_rng_error(error: RngStateError) -> SnapshotError {
    match error {
        RngStateError::UnsupportedVersion => SnapshotError::UnsupportedRngVersion,
        RngStateError::InvalidEncoding | RngStateError::InvalidWordPosition => {
            SnapshotError::InvalidRngState
        }
    }
}

/// Stable sanitized classes. Decode errors and source payloads are deliberately not retained.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SnapshotError {
    EncodingFailed,
    IntegerOutOfRange,
    InvalidUtf8,
    MalformedJson,
    UnknownField,
    DuplicateField,
    MissingField,
    WrongPrimitive,
    InvalidValue,
    NonCanonicalPayload,
    NonCanonicalAmount,
    ResourceLimit,
    DomainViolation,
    UnsupportedSnapshotVersion,
    UnsupportedRngVersion,
    InvalidRngState,
    InvalidClockState,
}

impl fmt::Display for SnapshotError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::EncodingFailed => "snapshot encoding failed",
            Self::IntegerOutOfRange => "snapshot integer exceeds its safe range",
            Self::InvalidUtf8 => "snapshot payload is not UTF-8",
            Self::MalformedJson => "snapshot payload is malformed JSON",
            Self::UnknownField => "snapshot contains an unknown field",
            Self::DuplicateField => "snapshot contains a duplicate field",
            Self::MissingField => "snapshot is missing a required field",
            Self::WrongPrimitive => "snapshot field has the wrong JSON primitive",
            Self::InvalidValue => "snapshot field has an invalid value",
            Self::NonCanonicalPayload => "snapshot payload is not canonical JSON",
            Self::NonCanonicalAmount => "snapshot contains a non-canonical Amount",
            Self::ResourceLimit => "snapshot exceeds the documented decode resource limit",
            Self::DomainViolation => "snapshot field violates its numeric domain",
            Self::UnsupportedSnapshotVersion => "unsupported snapshot version",
            Self::UnsupportedRngVersion => "unsupported RNG state version",
            Self::InvalidRngState => "invalid RNG continuation state",
            Self::InvalidClockState => "logical clock fields are inconsistent",
        })
    }
}

impl Error for SnapshotError {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::amount::MAX_SAFE_JSON_INTEGER;
    use crate::game::clock::UPDATE_QUANTUM_NANOS;
    use crate::game::conversion::convert_one_wire;
    use crate::game::economy::{advance_auto_clippers, advance_fast_phase};

    fn rich_state() -> GameState {
        let mut rng = GameRng::from_test_seed([0x5au8; 32]);
        rng.next_u32();
        rng.next_u64();
        let mut partial = [0u8; 13];
        rng.fill_bytes(&mut partial);
        let mut state = GameState::fresh(rng);
        state.pro.lifetime_clips = Amount::parse(
            "30000000000000000000000000000000000000000000000000000001.000000000000000001",
        )
        .unwrap()
        .nonnegative()
        .unwrap();
        state.pro.clips_sold = Amount::parse("42.5").unwrap().nonnegative().unwrap();
        state.pro.unsold_clips = state
            .pro
            .lifetime_clips
            .checked_sub(&state.pro.clips_sold)
            .unwrap();
        state.pro.unused_clips = Amount::parse(
            "30000000000000000000000000000000000000000000000000000001.000000000000000001",
        )
        .unwrap()
        .nonnegative()
        .unwrap();
        state.pro.wire = Amount::parse("9007199254740995")
            .unwrap()
            .nonnegative()
            .unwrap();
        state.pro.funds = Amount::parse("-0.000000000000000001").unwrap();
        state.pro.wire_spool_length = NonNegativeAmount::zero();
        state.pro.wire_quote = Amount::from_i128(20);
        state.pro.price_per_clip = Amount::parse("6.21").unwrap();
        state.pro.marketing_level = Amount::parse("302").unwrap().integral().unwrap();
        state.pro.trust = IntegralAmount::from_i128(0);
        state.pro.processors = IntegralAmount::from_i128(2);
        state.pro.memory = IntegralAmount::from_i128(3);
        state.pro.computing_hidden = false;
        state.pro.projects_hidden = false;
        state.pro.auto_clipper_revealed = true;
        state.pro.auto_clippers = IntegralAmount::from_i128(7);
        state.pro.auto_clipper_cost = Amount::parse("6.21").unwrap();
        state.pro.auto_clipper_rate = Amount::parse("1.5").unwrap().nonnegative().unwrap();
        state.pro.auto_clipper_production_accumulator =
            Amount::parse("0.25").unwrap().nonnegative().unwrap();
        state.pro.console_messages = std::array::from_fn(|index| {
            if index == 4 {
                "AutoClipper 7 purchased.".to_owned()
            } else {
                String::new()
            }
        });
        state.pro.income = Amount::parse("456.789").unwrap();
        state.pro.last_sale_revenue = Amount::parse("3.002").unwrap();
        state.pro.wire_base_price = Amount::parse("19.876543210123456789").unwrap();
        state.pro.wire_price_counter = SafeU64::new(17).unwrap();
        state.pro.wire_purchase_count = SafeU64::new(9).unwrap();
        state.pro.wire_inactivity_ticks = SafeU64::new(231).unwrap();
        state.pro.marketing_effectiveness = Amount::parse("1.125").unwrap();
        state.pro.demand_boost = Amount::parse("1.25").unwrap();
        state.pro.prestige_u = IntegralAmount::from_i128(7);
        refresh_demand(&mut state.pro).unwrap();
        state.clock = ClockState::from_snapshot_parts(251, 1, 51, 1, 14_000_000, 156).unwrap();
        state
    }

    fn assert_same_state(left: &GameState, right: &GameState) {
        assert_eq!(left.pro, right.pro);
        assert_eq!(left.clock, right.clock);
        assert_eq!(left.rng_state_hex(), right.rng_state_hex());
    }

    #[test]
    fn complete_v3_roundtrip_restores_exact_state_and_uninterrupted_continuation() {
        let original = rich_state();
        let before_capture = original.rng_state_hex();
        let snapshot = Snapshot::capture(&original, MAX_SAFE_JSON_INTEGER).unwrap();
        assert_eq!(original.rng_state_hex(), before_capture);
        let encoded = snapshot.to_canonical_bytes().unwrap();
        assert_eq!(encoded, snapshot.to_canonical_bytes().unwrap());
        assert_eq!(original.rng_state_hex(), before_capture);
        let decoded = Snapshot::from_canonical_bytes(&encoded).unwrap();
        let recovered = decoded.restore().unwrap();
        assert_eq!(recovered.revision, MAX_SAFE_JSON_INTEGER);
        assert_same_state(&original, &recovered.state);
        for expected in [
            "9007199254740995",
            "0.000000000000000001",
            "30000000000000000000000000000000000000000000000000000001",
        ] {
            assert!(
                String::from_utf8(encoded.clone())
                    .unwrap()
                    .contains(expected)
            );
        }

        let mut uninterrupted = original.clone();
        let mut restored = recovered.state;
        for _ in 0..20 {
            assert_eq!(
                uninterrupted.clock.advance(),
                restored.clock.advance(),
                "partial-phase clock continuation diverged"
            );
            assert_eq!(
                convert_one_wire(&mut uninterrupted.pro),
                convert_one_wire(&mut restored.pro)
            );
            assert_eq!(uninterrupted.rng.next_u64(), restored.rng.next_u64());
            assert_eq!(uninterrupted.rng.next_u32(), restored.rng.next_u32());
            let mut left = [0u8; 29];
            let mut right = [0u8; 29];
            uninterrupted.rng.fill_bytes(&mut left);
            restored.rng.fill_bytes(&mut right);
            assert_eq!(left, right);
            assert_same_state(&uninterrupted, &restored);
        }
        eprintln!(
            "complete snapshot: exact tiny/huge/signed Amounts, clock 251->271, partial-byte RNG and ledger continuation matched"
        );
    }

    #[test]
    fn r1_snapshot_rejects_hidden_producer_without_normalizing_it() {
        let mut invalid = Snapshot::capture(&rich_state(), 1).expect("healthy fixture");
        invalid.pro.auto_clippers = IntegralAmount::from_i128(1);
        invalid.pro.auto_clipper_revealed = false;
        invalid.pro.auto_clipper_rate = NonNegativeAmount::zero();
        invalid.pro.auto_clipper_cost = Amount::parse("6.1").unwrap();
        let bytes = serde_json::to_vec(&invalid).unwrap();
        assert_eq!(
            Snapshot::from_canonical_bytes(&bytes),
            Err(SnapshotError::DomainViolation)
        );
        assert_eq!(
            invalid.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
        assert_eq!(invalid.pro.auto_clipper_cost.to_string(), "6.1");
        assert!(!invalid.pro.auto_clipper_revealed);
    }

    #[test]
    fn r1_snapshot_rejects_rate_above_count_and_keeps_valid_zero_and_prepurchase() {
        let mut invalid = Snapshot::capture(&rich_state(), 1).expect("healthy fixture");
        invalid.pro.auto_clippers = IntegralAmount::from_i128(1);
        invalid.pro.auto_clipper_revealed = true;
        invalid.pro.auto_clipper_rate = NonNegativeAmount::from_i128(999).unwrap();
        invalid.pro.auto_clipper_cost = Amount::parse("6.1").unwrap();
        let bytes = serde_json::to_vec(&invalid).unwrap();
        assert_eq!(
            Snapshot::from_canonical_bytes(&bytes),
            Err(SnapshotError::DomainViolation)
        );
        assert_eq!(
            invalid.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );

        let mut bad_accumulator = Snapshot::capture(&rich_state(), 1).unwrap();
        bad_accumulator.pro.auto_clippers = IntegralAmount::from_i128(1);
        bad_accumulator.pro.auto_clipper_rate = NonNegativeAmount::zero();
        bad_accumulator.pro.auto_clipper_production_accumulator =
            NonNegativeAmount::from_i128(2).unwrap();
        assert_eq!(
            Snapshot::from_canonical_bytes(&serde_json::to_vec(&bad_accumulator).unwrap()),
            Err(SnapshotError::DomainViolation)
        );

        // Zero producers hidden or pre-purchase revealed are valid. Stored cost
        // remains independent of a producer-level formula on restoration.
        let fresh = GameState::fresh(GameRng::from_test_seed([92u8; 32]));
        let mut pre_purchase = Snapshot::capture(&fresh, 0).unwrap();
        pre_purchase.pro.auto_clipper_revealed = true;
        let bytes = pre_purchase.to_canonical_bytes().unwrap();
        let restored = Snapshot::from_canonical_bytes(&bytes)
            .unwrap()
            .restore()
            .unwrap();
        assert!(restored.state.pro.auto_clipper_revealed);
        assert_eq!(restored.state.pro.auto_clippers.to_string(), "0");
        assert_eq!(restored.state.pro.auto_clipper_rate.to_string(), "0");
        assert_eq!(
            restored
                .state
                .pro
                .auto_clipper_production_accumulator
                .to_string(),
            "0"
        );
        assert_eq!(restored.state.pro.auto_clipper_cost.to_string(), "5");
    }

    #[test]
    fn clock_restore_table_accepts_exact_and_rejects_every_redundant_relation() {
        for update in [0, 1, 2, 7, 8, 249, 250, 251, MAX_SAFE_JSON_INTEGER] {
            let fast = (update % 10) as u8;
            let second = (update % 100) as u8;
            let slow = (update % 250) as u16;
            let remainder = ((u128::from(update) * UPDATE_QUANTUM_NANOS) % 16_000_000) as u32;
            let pulses = ((u128::from(update) * 5) / 8) as u64;
            let clock =
                ClockState::from_snapshot_parts(update, fast, second, slow, remainder, pulses)
                    .unwrap();
            assert_eq!(clock.update_count(), update);
            assert_eq!(clock.fast_phase(), fast);
            assert_eq!(clock.second_phase(), second);
            assert_eq!(clock.slow_phase(), slow);
            assert_eq!(clock.combat_remainder_nanos(), remainder);
            assert_eq!(clock.combat_pulses(), pulses);
            for (label, candidate) in [
                (
                    "fast",
                    (fast.wrapping_add(1), second, slow, remainder, pulses),
                ),
                (
                    "second",
                    (fast, second.wrapping_add(1), slow, remainder, pulses),
                ),
                (
                    "slow",
                    (fast, second, slow.wrapping_add(1), remainder, pulses),
                ),
                (
                    "remainder",
                    (fast, second, slow, remainder.wrapping_add(1), pulses),
                ),
                (
                    "pulses",
                    (fast, second, slow, remainder, pulses.wrapping_add(1)),
                ),
            ] {
                assert!(
                    ClockState::from_snapshot_parts(
                        update,
                        candidate.0,
                        candidate.1,
                        candidate.2,
                        candidate.3,
                        candidate.4,
                    )
                    .is_err(),
                    "accepted inconsistent {label} at update {update}"
                );
            }
        }
        for update in [MAX_SAFE_JSON_INTEGER + 1, u64::MAX] {
            assert!(ClockState::from_snapshot_parts(update, 0, 0, 0, 0, 0).is_err());
        }
        assert_eq!(UPDATE_QUANTUM_NANOS, 10_000_000);
        eprintln!(
            "clock negative table: all five redundant fields rejected at 0/1/2/7/8/249/250/251/2^53-1"
        );
    }

    #[test]
    fn strict_json_and_domain_negative_table_has_stable_typed_errors() {
        let base = Snapshot::capture(&rich_state(), MAX_SAFE_JSON_INTEGER).unwrap();
        let canonical = String::from_utf8(base.to_canonical_bytes().unwrap()).unwrap();
        let replace = |needle: &str, replacement: &str| {
            assert!(canonical.contains(needle), "missing fixture text {needle}");
            canonical.replacen(needle, replacement, 1)
        };
        let unsupported_version = replace("\"snapshot_version\":3", "\"snapshot_version\":4");
        let duplicate = replace(
            "\"snapshot_version\":3",
            "\"snapshot_version\":3,\"snapshot_version\":3",
        );
        let duplicate_nested = replace(
            "\"funds\":\"-0.000000000000000001\"",
            "\"funds\":\"0\",\"funds\":\"0\"",
        );
        let unknown = replace(
            "{\"snapshot_version\"",
            "{\"unknown\":0,\"snapshot_version\"",
        );
        let unknown_nested = replace("\"pro\":{", "\"pro\":{\"unknown\":0,");
        let missing = replace("\"fast_phase\":1,", "");
        let wrong_amount = replace("\"funds\":\"-0.000000000000000001\"", "\"funds\":0");
        let wrong_bool = replace("\"computing_hidden\":false", "\"computing_hidden\":1");
        let negative_wire = replace("\"wire\":\"9007199254740995\"", "\"wire\":\"-1\"");
        let fractional_count = replace(
            "\"marketing_level\":\"302\"",
            "\"marketing_level\":\"1.000000000000000001\"",
        );
        let unsafe_revision = replace(
            "\"revision\":9007199254740991",
            "\"revision\":9007199254740992",
        );
        let bad_fast = replace("\"fast_phase\":1", "\"fast_phase\":2");
        let bad_remainder = replace(
            "\"combat_remainder_nanos\":14000000",
            "\"combat_remainder_nanos\":16000000",
        );
        let bad_pulses = replace("\"combat_pulses\":156", "\"combat_pulses\":155");
        let numeric_rate = replace("\"auto_clipper_rate\":\"1.5\"", "\"auto_clipper_rate\":1.5");
        let negative_rate = replace(
            "\"auto_clipper_rate\":\"1.5\"",
            "\"auto_clipper_rate\":\"-1\"",
        );
        let short_console = replace(
            "\"console_messages\":[\"\",\"\",\"\",\"\",\"AutoClipper 7 purchased.\"]",
            "\"console_messages\":[\"\",\"\"]",
        );
        let control_console = replace("AutoClipper 7 purchased.", "AutoClipper 7 purchased\\n.");
        let noncanonical_zero = replace("\"funds\":\"-0.000000000000000001\"", "\"funds\":\"-0\"");
        let noncanonical_fraction = replace(
            "\"price_per_clip\":\"6.21\"",
            "\"price_per_clip\":\"6.210\"",
        );
        let noncanonical_exponent = replace(
            "\"price_per_clip\":\"6.21\"",
            "\"price_per_clip\":\"621e-2\"",
        );
        let resource_limit = replace(
            "\"funds\":\"-0.000000000000000001\"",
            &format!("\"funds\":\"1{}\"", "2".repeat(16 * 1024)),
        );
        let mut bad_rng_version = base.clone();
        bad_rng_version.rng_state.replace_range(0..2, "02");
        let bad_rng_version = serde_json::to_string(&bad_rng_version).unwrap();
        let mut uppercase_rng = base.clone();
        uppercase_rng.rng_state = uppercase_rng.rng_state.to_uppercase();
        let uppercase_rng = serde_json::to_string(&uppercase_rng).unwrap();
        let mut short_rng = base.clone();
        short_rng.rng_state.pop();
        let short_rng = serde_json::to_string(&short_rng).unwrap();
        let noncanonical_json = format!(" {canonical}");
        let malformed = canonical[..canonical.len() - 1].to_owned();

        for (label, input, expected) in [
            (
                "unsupported version",
                unsupported_version,
                SnapshotError::UnsupportedSnapshotVersion,
            ),
            ("top duplicate", duplicate, SnapshotError::DuplicateField),
            (
                "nested duplicate",
                duplicate_nested,
                SnapshotError::DuplicateField,
            ),
            ("top unknown", unknown, SnapshotError::UnknownField),
            (
                "nested unknown",
                unknown_nested,
                SnapshotError::UnknownField,
            ),
            ("missing", missing, SnapshotError::MissingField),
            (
                "wrong Amount primitive",
                wrong_amount,
                SnapshotError::WrongPrimitive,
            ),
            (
                "wrong bool primitive",
                wrong_bool,
                SnapshotError::WrongPrimitive,
            ),
            (
                "negative nonnegative",
                negative_wire,
                SnapshotError::DomainViolation,
            ),
            (
                "fractional integral",
                fractional_count,
                SnapshotError::DomainViolation,
            ),
            (
                "unsafe revision",
                unsafe_revision,
                SnapshotError::IntegerOutOfRange,
            ),
            ("bad fast phase", bad_fast, SnapshotError::InvalidClockState),
            (
                "bad remainder",
                bad_remainder,
                SnapshotError::InvalidClockState,
            ),
            ("bad pulses", bad_pulses, SnapshotError::InvalidClockState),
            (
                "negative zero",
                noncanonical_zero,
                SnapshotError::NonCanonicalAmount,
            ),
            (
                "trailing fraction zero",
                noncanonical_fraction,
                SnapshotError::NonCanonicalAmount,
            ),
            (
                "exponent Amount",
                noncanonical_exponent,
                SnapshotError::NonCanonicalAmount,
            ),
            (
                "JSON-number auto rate",
                numeric_rate,
                SnapshotError::WrongPrimitive,
            ),
            (
                "negative auto rate",
                negative_rate,
                SnapshotError::DomainViolation,
            ),
            (
                "short console history",
                short_console,
                SnapshotError::InvalidValue,
            ),
            (
                "console control character",
                control_console,
                SnapshotError::DomainViolation,
            ),
            (
                "Amount resource guard",
                resource_limit,
                SnapshotError::ResourceLimit,
            ),
            (
                "bad RNG version",
                bad_rng_version,
                SnapshotError::UnsupportedRngVersion,
            ),
            (
                "uppercase RNG",
                uppercase_rng,
                SnapshotError::InvalidRngState,
            ),
            ("short RNG", short_rng, SnapshotError::InvalidRngState),
            (
                "noncanonical JSON",
                noncanonical_json,
                SnapshotError::NonCanonicalPayload,
            ),
            ("truncated JSON", malformed, SnapshotError::MalformedJson),
        ] {
            let error = Snapshot::from_canonical_bytes(input.as_bytes())
                .expect_err(&format!("accepted invalid fixture: {label}"));
            assert_eq!(error, expected, "wrong class for {label}");
            assert!(
                !error.to_string().contains(&canonical),
                "payload leaked for {label}"
            );
            eprintln!("strict snapshot case {label}: {expected:?}");
        }
        assert_eq!(
            Snapshot::from_canonical_bytes(&[0xff, 0xfe]),
            Err(SnapshotError::InvalidUtf8)
        );
        for primitive in ["null", "true", "1", "[]", "{}"] {
            assert!(Snapshot::from_canonical_bytes(primitive.as_bytes()).is_err());
        }
        let mut bad_cost = base.clone();
        bad_cost.pro.auto_clipper_cost = Amount::from_i128(0);
        assert_eq!(
            bad_cost.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
        let mut bad_message = base.clone();
        bad_message.pro.console_messages[4] = "x".repeat(257);
        assert_eq!(
            bad_message.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
        for field in 0..5 {
            let mut invalid = base.clone();
            let count = match field {
                0 => &mut invalid.pro.marketing_level,
                1 => &mut invalid.pro.trust,
                2 => &mut invalid.pro.processors,
                3 => &mut invalid.pro.memory,
                _ => &mut invalid.pro.auto_clippers,
            };
            *count = IntegralAmount::from_i128(-1);
            assert_eq!(
                invalid.to_canonical_bytes(),
                Err(SnapshotError::DomainViolation)
            );
        }
    }

    #[test]
    fn version_one_migration_retains_state_and_continues_identically() {
        // V1 predates every G02 sales/Wire-modifier field. A valid fixture has
        // all production still Unsold; later migration must not infer missing sales.
        let mut original = rich_state();
        original.pro.auto_clipper_rate = NonNegativeAmount::zero();
        original.pro.auto_clipper_production_accumulator = NonNegativeAmount::zero();
        original.pro.console_messages = std::array::from_fn(|_| String::new());
        original.pro.unsold_clips = original.pro.lifetime_clips.clone();
        original.pro.clips_sold = NonNegativeAmount::zero();
        original.pro.income = Amount::zero();
        original.pro.last_sale_revenue = Amount::zero();
        original.pro.marketing_effectiveness = Amount::from_i128(1);
        original.pro.demand_boost = Amount::from_i128(1);
        original.pro.prestige_u = IntegralAmount::from_i128(0);
        original.pro.wire_base_price = Amount::from_i128(20);
        original.pro.wire_price_counter = SafeU64::new(0).unwrap();
        original.pro.wire_purchase_count = SafeU64::new(0).unwrap();
        original.pro.wire_inactivity_ticks = SafeU64::new(0).unwrap();
        original.pro.wire_quote = Amount::from_i128(17);
        refresh_demand(&mut original.pro).unwrap();
        let current = Snapshot::capture(&original, 77).unwrap();
        let original_pro = ProSnapshotV1 {
            lifetime_clips: current.pro.lifetime_clips.clone(),
            unsold_clips: current.pro.unsold_clips.clone(),
            unused_clips: current.pro.unused_clips.clone(),
            wire: current.pro.wire.clone(),
            funds: current.pro.funds.clone(),
            wire_spool_length: current.pro.wire_spool_length.clone(),
            wire_quote: current.pro.wire_quote.clone(),
            price_per_clip: current.pro.price_per_clip.clone(),
            marketing_level: current.pro.marketing_level.clone(),
            trust: current.pro.trust.clone(),
            processors: current.pro.processors.clone(),
            memory: current.pro.memory.clone(),
            computing_hidden: current.pro.computing_hidden,
            projects_hidden: current.pro.projects_hidden,
            auto_clipper_revealed: current.pro.auto_clipper_revealed,
            auto_clippers: current.pro.auto_clippers.clone(),
            auto_clipper_cost: current.pro.auto_clipper_cost.clone(),
        };
        let v1 = SnapshotV1 {
            snapshot_version: 1,
            revision: current.revision,
            pro: original_pro,
            clock: current.clock.clone(),
            rng_state: current.rng_state.clone(),
        };
        let migrated = Snapshot::from_canonical_bytes(&serde_json::to_vec(&v1).unwrap()).unwrap();
        assert_eq!(migrated.snapshot_version, 3);
        assert_eq!(migrated.pro.lifetime_clips, current.pro.lifetime_clips);
        assert_eq!(migrated.pro.funds, current.pro.funds);
        assert_eq!(migrated.pro.wire_quote, current.pro.wire_quote);
        assert_eq!(migrated.pro.wire_quote.to_string(), "17");
        assert_eq!(migrated.rng_state, current.rng_state);
        assert_eq!(migrated.pro.clips_sold, NonNegativeAmount::zero());
        assert_eq!(migrated.pro.income, Amount::zero());
        assert_eq!(migrated.pro.marketing_effectiveness, Amount::from_i128(1));
        assert_eq!(migrated.pro.wire_base_price, Amount::from_i128(20));
        assert_eq!(migrated.pro.wire_price_counter.get(), 0);

        let mut uninterrupted = original;
        let mut restored = migrated.restore().unwrap().state;
        for _ in 0..20 {
            advance_fast_phase(&mut uninterrupted).unwrap();
            advance_fast_phase(&mut restored).unwrap();
            assert_same_state(&uninterrupted, &restored);
        }
        assert_eq!(restored.clock, uninterrupted.clock);
        assert!(restored.pro.clips_sold > NonNegativeAmount::zero());
        assert!(restored.pro.income > Amount::zero());
        assert!(restored.pro.last_sale_revenue > Amount::zero());
        assert_eq!(restored.pro.wire_inactivity_ticks.get(), 20);
        assert!(format!("{:?}", SnapshotError::DomainViolation).contains("DomainViolation"));
    }

    #[test]
    fn version_two_migration_preserves_stored_autoclipper_authority_without_backfill() {
        let original = rich_state();
        let current = Snapshot::capture(&original, 92).unwrap();
        let canonical = String::from_utf8(current.to_canonical_bytes().unwrap()).unwrap();
        let additions = format!(
            ",\"auto_clipper_rate\":{},\"auto_clipper_production_accumulator\":{},\"console_messages\":{}",
            serde_json::to_string(&current.pro.auto_clipper_rate).unwrap(),
            serde_json::to_string(&current.pro.auto_clipper_production_accumulator).unwrap(),
            serde_json::to_string(&current.pro.console_messages).unwrap()
        );
        assert!(canonical.contains(&additions));
        let legacy = canonical
            .replacen("\"snapshot_version\":3", "\"snapshot_version\":2", 1)
            .replacen(&additions, "", 1);
        let migrated = Snapshot::from_canonical_bytes(legacy.as_bytes()).unwrap();
        assert_eq!(migrated.snapshot_version, 3);
        // Deliberately inconsistent with a level-7 successor: restoration must
        // charge/retain the stored price, never reconstruct from producer level.
        assert_eq!(migrated.pro.auto_clippers.to_string(), "7");
        assert_eq!(migrated.pro.auto_clipper_cost.to_string(), "6.21");
        assert!(migrated.pro.auto_clipper_revealed);
        assert_eq!(migrated.pro.auto_clipper_rate, NonNegativeAmount::zero());
        assert_eq!(
            migrated.pro.console_messages,
            std::array::from_fn(|_| String::new())
        );
        assert_eq!(
            migrated.pro.auto_clipper_production_accumulator,
            NonNegativeAmount::zero()
        );
        assert_eq!(migrated.pro.lifetime_clips, original.pro.lifetime_clips);

        let restored = migrated.restore().unwrap().state;
        let reopened = Snapshot::from_canonical_bytes(&migrated.to_canonical_bytes().unwrap())
            .unwrap()
            .restore()
            .unwrap()
            .state;
        assert_same_state(&restored, &reopened);
        let mut left = restored;
        let mut right = reopened;
        advance_auto_clippers(&mut left, true).unwrap();
        advance_auto_clippers(&mut right, true).unwrap();
        assert_same_state(&left, &right);
        assert_eq!(left.pro.auto_clipper_rate.to_string(), "0.07");
        eprintln!(
            "G03 v2 migration: count 7/stored 6.21/reveal retained; no legacy rate/messages/offline gain inferred"
        );
    }

    #[test]
    fn nondefault_v3_economy_continuation_is_identical_after_restore() {
        let original = rich_state();
        let snapshot = Snapshot::capture(&original, 88).unwrap();
        let encoded = snapshot.to_canonical_bytes().unwrap();
        let mut restored = Snapshot::from_canonical_bytes(&encoded)
            .unwrap()
            .restore()
            .unwrap()
            .state;
        let mut uninterrupted = original.clone();
        assert_same_state(&uninterrupted, &restored);
        assert_eq!(restored.pro.clips_sold.to_string(), "42.5");
        assert_eq!(restored.pro.income.to_string(), "456.789");
        assert_eq!(restored.pro.last_sale_revenue.to_string(), "3.002");
        assert_eq!(
            restored.pro.wire_base_price.to_string(),
            "19.876543210123456789"
        );
        assert_eq!(restored.pro.wire_price_counter.get(), 17);
        assert_eq!(restored.pro.wire_purchase_count.get(), 9);
        assert_eq!(restored.pro.wire_inactivity_ticks.get(), 231);
        assert!(restored.pro.demand > NonNegativeAmount::from_i128(100).unwrap());
        for _ in 0..250 {
            let left = uninterrupted.clock.advance().unwrap();
            let right = restored.clock.advance().unwrap();
            assert_eq!(left, right);
            if left.fast_due {
                advance_fast_phase(&mut uninterrupted).unwrap();
                advance_fast_phase(&mut restored).unwrap();
            }
            assert_same_state(&uninterrupted, &restored);
        }
        assert!(
            restored.pro.clips_sold
                > NonNegativeAmount::new(Amount::parse("42.5").unwrap()).unwrap()
        );
        assert!(restored.pro.income > Amount::parse("456.789").unwrap());
        assert!(restored.pro.last_sale_revenue > Amount::zero());
        assert!(restored.pro.wire_inactivity_ticks.get() < 20);
    }

    #[test]
    fn current_conservation_rejects_vanished_clips_and_accepts_a_conserved_ledger() {
        let healthy = Snapshot::capture(&rich_state(), 11).unwrap();
        let canonical = healthy.to_canonical_bytes().unwrap();
        Snapshot::from_canonical_bytes(&canonical)
            .unwrap()
            .restore()
            .unwrap();
        let mut vanished = healthy;
        vanished.pro.unsold_clips = NonNegativeAmount::zero();
        vanished.pro.clips_sold = NonNegativeAmount::zero();
        assert_eq!(
            vanished.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
    }

    #[test]
    fn migrated_payloads_still_reject_unknown_tampering_and_crossfield_damage() {
        let mut current = Snapshot::capture(&rich_state(), 11).unwrap();
        current.pro.unsold_clips = current
            .pro
            .lifetime_clips
            .add_exact(&NonNegativeAmount::from_i128(1).unwrap());
        assert_eq!(
            current.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
        let mut current = Snapshot::capture(&rich_state(), 11).unwrap();
        current.pro.demand = NonNegativeAmount::from_i128(1).unwrap();
        assert_eq!(
            current.to_canonical_bytes(),
            Err(SnapshotError::DomainViolation)
        );
    }
}
