//! Detached logical game state; process-local metadata lives in the runtime.

use super::amount::{Amount, IntegralAmount, NonNegativeAmount};
use super::clock::ClockState;
use super::rng::GameRng;
use num_bigint::BigInt;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProState {
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

impl ProState {
    /// Current Marketing cost in whole dollars, exactly derived from its stored level.
    /// The level is already persisted; keeping the derived cost avoids a second
    /// authority that could disagree after recovery.
    pub fn marketing_cost(&self) -> Option<Amount> {
        let unit = Amount::from_i128(1);
        let level = self.marketing_level.amount().mantissa() / unit.mantissa();
        if level < BigInt::from(1u8) {
            return None;
        }
        let mut exponent = level - BigInt::from(1u8);
        let mut power = BigInt::from(1u8);
        let mut base = BigInt::from(2u8);
        while exponent > BigInt::from(0u8) {
            if &exponent % BigInt::from(2u8) == BigInt::from(1u8) {
                power *= &base;
            }
            exponent /= BigInt::from(2u8);
            if exponent > BigInt::from(0u8) {
                base = &base * &base;
            }
        }
        Some(Amount::from_i128(100).multiply_integer(&power))
    }

    pub(crate) fn fresh() -> Self {
        Self {
            lifetime_clips: NonNegativeAmount::zero(),
            unsold_clips: NonNegativeAmount::zero(),
            unused_clips: NonNegativeAmount::zero(),
            wire: NonNegativeAmount::from_i128(1_000).expect("valid initial Wire"),
            funds: Amount::zero(),
            wire_spool_length: NonNegativeAmount::from_i128(1_000).expect("valid initial spool"),
            wire_quote: Amount::from_i128(20),
            price_per_clip: Amount::parse("0.25").expect("valid initial clip price"),
            marketing_level: IntegralAmount::from_i128(1),
            trust: IntegralAmount::from_i128(2),
            processors: IntegralAmount::from_i128(1),
            memory: IntegralAmount::from_i128(1),
            computing_hidden: true,
            projects_hidden: true,
            auto_clipper_revealed: false,
            auto_clippers: IntegralAmount::from_i128(0),
            auto_clipper_cost: Amount::from_i128(5),
        }
    }
}

#[derive(Clone, Debug)]
pub struct GameState {
    pub pro: ProState,
    pub clock: ClockState,
    pub(crate) rng: GameRng,
}

impl GameState {
    pub(crate) fn fresh(rng: GameRng) -> Self {
        Self {
            pro: ProState::fresh(),
            clock: ClockState::fresh(),
            rng,
        }
    }

    pub(crate) fn from_snapshot_parts(pro: ProState, clock: ClockState, rng: GameRng) -> Self {
        Self { pro, clock, rng }
    }

    /// Read-only observation never advances the game RNG stream.
    pub fn rng_state_hex(&self) -> String {
        self.rng.export_hex()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fresh_state_matches_every_selected_m1_initial_value() {
        let state = ProState::fresh();
        assert_eq!(state.lifetime_clips.to_string(), "0");
        assert_eq!(state.unsold_clips.to_string(), "0");
        assert_eq!(state.unused_clips.to_string(), "0");
        assert_eq!(state.funds.to_string(), "0");
        assert_eq!(state.wire.to_string(), "1000");
        assert_eq!(state.wire_spool_length.to_string(), "1000");
        assert_eq!(state.wire_quote.to_string(), "20");
        assert_eq!(state.price_per_clip.to_string(), "0.25");
        assert_eq!(state.marketing_level.to_string(), "1");
        assert_eq!(
            state.marketing_cost().map(|cost| cost.to_string()),
            Some("100".to_owned())
        );
        assert_eq!(state.trust.to_string(), "2");
        assert_eq!(state.processors.to_string(), "1");
        assert_eq!(state.memory.to_string(), "1");
        assert!(state.computing_hidden);
        assert!(state.projects_hidden);
        assert!(!state.auto_clipper_revealed);
        assert_eq!(state.auto_clippers.to_string(), "0");
        assert_eq!(state.auto_clipper_cost.to_string(), "5");
    }

    #[test]
    fn initial_auto_clipper_price_is_stored_not_recomputed() {
        let state = ProState::fresh();
        assert_eq!(state.auto_clippers.to_string(), "0");
        assert_eq!(state.auto_clipper_cost.to_string(), "5");
        assert_ne!(state.auto_clipper_cost, Amount::parse("6.1").unwrap());
        assert_ne!(state.auto_clipper_cost, Amount::parse("6.21").unwrap());
    }
}
