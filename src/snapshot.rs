//! Strict, deterministic snapshot version 1 for the complete current logical state.

use crate::game::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use crate::game::clock::ClockState;
use crate::game::rng::{GameRng, RngStateError};
use crate::game::state::{GameState, ProState};
use serde::{Deserialize, Serialize};
use std::error::Error;
use std::fmt;

pub const SNAPSHOT_VERSION: u8 = 1;

/// Every current `GameState` field has one statically typed representation.
/// Process-local run identity, lag debt, retry records and subscriptions are absent.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotV1 {
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
    pub trust: IntegralAmount,
    pub processors: IntegralAmount,
    pub memory: IntegralAmount,
    pub computing_hidden: bool,
    pub projects_hidden: bool,
    pub auto_clipper_revealed: bool,
    pub auto_clippers: IntegralAmount,
    pub auto_clipper_cost: Amount,
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

impl SnapshotV1 {
    pub fn capture(state: &GameState, revision: u64) -> Result<Self, SnapshotError> {
        let snapshot = Self {
            snapshot_version: SNAPSHOT_VERSION,
            revision: SafeU64::new(revision).map_err(|_| SnapshotError::IntegerOutOfRange)?,
            pro: ProSnapshot::from_state(&state.pro),
            clock: ClockSnapshot::from_state(&state.clock)?,
            rng_state: state.rng_state_hex(),
        };
        // A read-only capture must never advance or otherwise mutate the RNG.
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
        let snapshot: Self = serde_json::from_str(text).map_err(classify_json_error)?;
        snapshot.validate()?;
        let canonical = serde_json::to_vec(&snapshot).map_err(|_| SnapshotError::EncodingFailed)?;
        if canonical != bytes {
            return Err(SnapshotError::NonCanonicalPayload);
        }
        Ok(snapshot)
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
        self.pro.validate()?;
        self.clock.to_state()?;
        GameRng::import_hex(&self.rng_state).map_err(map_rng_error)?;
        Ok(())
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

    fn validate(&self) -> Result<(), SnapshotError> {
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
        Ok(())
    }

    fn to_state(&self) -> Result<ProState, SnapshotError> {
        self.validate()?;
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
            trust: self.trust.clone(),
            processors: self.processors.clone(),
            memory: self.memory.clone(),
            computing_hidden: self.computing_hidden,
            projects_hidden: self.projects_hidden,
            auto_clipper_revealed: self.auto_clipper_revealed,
            auto_clippers: self.auto_clippers.clone(),
            auto_clipper_cost: self.auto_clipper_cost.clone(),
        })
    }
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

    fn rich_state() -> GameState {
        let mut rng = GameRng::from_test_seed([0x5au8; 32]);
        rng.next_u32();
        rng.next_u64();
        let mut partial = [0u8; 13];
        rng.fill_bytes(&mut partial);
        let mut state = GameState::fresh(rng);
        state.pro.lifetime_clips = Amount::parse("9007199254740993")
            .unwrap()
            .nonnegative()
            .unwrap();
        state.pro.unsold_clips = Amount::parse("0.000000000000000001")
            .unwrap()
            .nonnegative()
            .unwrap();
        state.pro.unused_clips =
            Amount::parse("30000000000000000000000000000000000000000000000000000001")
                .unwrap()
                .nonnegative()
                .unwrap();
        state.pro.wire = Amount::parse("9007199254740995")
            .unwrap()
            .nonnegative()
            .unwrap();
        state.pro.funds = Amount::parse("-0.000000000000000001").unwrap();
        state.pro.wire_spool_length = NonNegativeAmount::zero();
        state.pro.wire_quote = Amount::parse("-41117.99").unwrap();
        state.pro.price_per_clip = Amount::parse("6.21").unwrap();
        state.pro.marketing_level = Amount::parse("340282366920938463463374607431768211457")
            .unwrap()
            .integral()
            .unwrap();
        state.pro.trust = IntegralAmount::from_i128(0);
        state.pro.processors = IntegralAmount::from_i128(2);
        state.pro.memory = IntegralAmount::from_i128(3);
        state.pro.computing_hidden = false;
        state.pro.projects_hidden = false;
        state.pro.auto_clipper_revealed = true;
        state.pro.auto_clippers = IntegralAmount::from_i128(7);
        state.pro.auto_clipper_cost = Amount::parse("6.21").unwrap();
        state.clock = ClockState::from_snapshot_parts(251, 1, 51, 1, 14_000_000, 156).unwrap();
        state
    }

    fn assert_same_state(left: &GameState, right: &GameState) {
        assert_eq!(left.pro, right.pro);
        assert_eq!(left.clock, right.clock);
        assert_eq!(left.rng_state_hex(), right.rng_state_hex());
    }

    #[test]
    fn complete_v1_roundtrip_restores_exact_state_and_uninterrupted_continuation() {
        let original = rich_state();
        let before_capture = original.rng_state_hex();
        let snapshot = SnapshotV1::capture(&original, MAX_SAFE_JSON_INTEGER).unwrap();
        assert_eq!(original.rng_state_hex(), before_capture);
        let encoded = snapshot.to_canonical_bytes().unwrap();
        assert_eq!(encoded, snapshot.to_canonical_bytes().unwrap());
        assert_eq!(original.rng_state_hex(), before_capture);
        let decoded = SnapshotV1::from_canonical_bytes(&encoded).unwrap();
        let recovered = decoded.restore().unwrap();
        assert_eq!(recovered.revision, MAX_SAFE_JSON_INTEGER);
        assert_same_state(&original, &recovered.state);
        for expected in [
            "9007199254740993",
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
        let base = SnapshotV1::capture(&rich_state(), MAX_SAFE_JSON_INTEGER).unwrap();
        let canonical = String::from_utf8(base.to_canonical_bytes().unwrap()).unwrap();
        let replace = |needle: &str, replacement: &str| {
            assert!(canonical.contains(needle), "missing fixture text {needle}");
            canonical.replacen(needle, replacement, 1)
        };
        let unsupported_version = replace("\"snapshot_version\":1", "\"snapshot_version\":2");
        let duplicate = replace(
            "\"snapshot_version\":1",
            "\"snapshot_version\":1,\"snapshot_version\":1",
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
            "\"marketing_level\":\"340282366920938463463374607431768211457\"",
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
            let error = SnapshotV1::from_canonical_bytes(input.as_bytes())
                .expect_err(&format!("accepted invalid fixture: {label}"));
            assert_eq!(error, expected, "wrong class for {label}");
            assert!(
                !error.to_string().contains(&canonical),
                "payload leaked for {label}"
            );
            eprintln!("strict snapshot case {label}: {expected:?}");
        }
        assert_eq!(
            SnapshotV1::from_canonical_bytes(&[0xff, 0xfe]),
            Err(SnapshotError::InvalidUtf8)
        );
        for primitive in ["null", "true", "1", "[]", "{}"] {
            assert!(SnapshotV1::from_canonical_bytes(primitive.as_bytes()).is_err());
        }
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
}
