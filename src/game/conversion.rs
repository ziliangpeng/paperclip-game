//! Shared ordinary Wire-to-clip conversion.

use super::amount::{Amount, NonNegativeAmount};
use super::state::ProState;
use num_bigint::BigInt;
use std::error::Error;
use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ConversionError {
    InsufficientWire,
    InvalidRequest,
    ZeroDenominator,
}

impl fmt::Display for ConversionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InsufficientWire => {
                formatter.write_str("ordinary conversion requires at least one Wire")
            }
            Self::InvalidRequest => {
                formatter.write_str("conversion request must be positive after quantization")
            }
            Self::ZeroDenominator => formatter.write_str("conversion request denominator is zero"),
        }
    }
}

impl Error for ConversionError {}

/// Internal source-formula boundary. No public command supplies this ratio.
pub(crate) fn convert_wire_ratio(
    state: &mut ProState,
    numerator: &BigInt,
    denominator: &BigInt,
) -> Result<NonNegativeAmount, ConversionError> {
    // The ordinary Wire gate deliberately precedes formula/quantization work.
    if state.wire < NonNegativeAmount::from_i128(1).expect("one is nonnegative") {
        return Err(ConversionError::InsufficientWire);
    }
    if *denominator == BigInt::from(0) {
        return Err(ConversionError::ZeroDenominator);
    }
    let requested = Amount::quantize_ratio(numerator, denominator)
        .map_err(|_| ConversionError::ZeroDenominator)?
        .nonnegative()
        .map_err(|_| ConversionError::InvalidRequest)?;
    if requested.amount().is_zero() {
        return Err(ConversionError::InvalidRequest);
    }

    let actual = std::cmp::min(requested, state.wire.clone());
    let remaining_wire = state
        .wire
        .checked_sub(&actual)
        .map_err(|_| ConversionError::InvalidRequest)?;
    let lifetime = state.lifetime_clips.add_exact(&actual);
    let unsold = state.unsold_clips.add_exact(&actual);
    let unused = state.unused_clips.add_exact(&actual);

    state.wire = remaining_wire;
    state.lifetime_clips = lifetime;
    state.unsold_clips = unsold;
    state.unused_clips = unused;
    Ok(actual)
}

pub(crate) fn convert_one_wire(state: &mut ProState) -> Result<NonNegativeAmount, ConversionError> {
    convert_wire_ratio(state, &BigInt::from(1), &BigInt::from(1))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::amount::Amount;

    fn state_with_wire(text: &str) -> ProState {
        let mut state = ProState::fresh();
        state.wire = Amount::parse(text).unwrap().nonnegative().unwrap();
        state
    }

    fn request(
        state: &mut ProState,
        numerator: i128,
        denominator: i128,
    ) -> Result<String, ConversionError> {
        convert_wire_ratio(state, &BigInt::from(numerator), &BigInt::from(denominator))
            .map(|actual| actual.to_string())
    }

    fn assert_ledgers(state: &ProState, expected: &str) {
        assert_eq!(state.lifetime_clips.to_string(), expected);
        assert_eq!(state.unsold_clips.to_string(), expected);
        assert_eq!(state.unused_clips.to_string(), expected);
    }

    #[test]
    fn capped_request_conserves_the_same_actual_amount_everywhere() {
        let mut state = state_with_wire("5");
        assert_eq!(request(&mut state, 10, 1), Ok("5".to_owned()));
        assert_eq!(state.wire.to_string(), "0");
        assert_ledgers(&state, "5");
    }

    #[test]
    fn fractional_automatic_request_keeps_exact_remainder() {
        let mut state = state_with_wire("1");
        assert_eq!(request(&mut state, 1, 5), Ok("0.2".to_owned()));
        assert_eq!(state.wire.to_string(), "0.8");
        assert_ledgers(&state, "0.2");
    }

    #[test]
    fn negative_table_below_one_wire_rejects_before_request_evaluation_without_mutation() {
        for (wire, numerator, denominator) in [
            ("0.5", 1, 5),
            ("0.999", 1, 0),
            ("0.000000000000000001", -10, 1),
        ] {
            let mut state = state_with_wire(wire);
            let before = state.clone();
            assert_eq!(
                request(&mut state, numerator, denominator),
                Err(ConversionError::InsufficientWire)
            );
            assert_eq!(state, before);
        }
    }

    #[test]
    fn negative_table_invalid_requests_never_clamp_to_a_grant() {
        for (numerator, denominator, expected) in [
            (0, 1, ConversionError::InvalidRequest),
            (-1, 1, ConversionError::InvalidRequest),
            (
                1,
                10_000_000_000_000_000_000i128,
                ConversionError::InvalidRequest,
            ),
            (1, 0, ConversionError::ZeroDenominator),
        ] {
            let mut state = state_with_wire("1");
            let before = state.clone();
            assert_eq!(request(&mut state, numerator, denominator), Err(expected));
            assert_eq!(state, before);
        }
    }

    #[test]
    fn one_wire_is_the_exact_ordinary_boundary() {
        let mut state = state_with_wire("1");
        assert_eq!(convert_one_wire(&mut state).unwrap().to_string(), "1");
        assert_eq!(state.wire, NonNegativeAmount::zero());
        assert_ledgers(&state, "1");
        let before = state.clone();
        assert_eq!(
            convert_one_wire(&mut state),
            Err(ConversionError::InsufficientWire)
        );
        assert_eq!(state, before);
    }

    #[test]
    fn non_grid_request_is_quantized_before_not_after_the_cap() {
        let mut state = state_with_wire("1");
        assert_eq!(
            request(&mut state, 2, 3),
            Ok("0.666666666666666666".to_owned())
        );
        assert_eq!(state.wire.to_string(), "0.333333333333333334");
        assert_ledgers(&state, "0.666666666666666666");

        let mut capped = state_with_wire("1.000000000000000001");
        assert_eq!(
            request(&mut capped, 3, 2),
            Ok("1.000000000000000001".to_owned())
        );
        assert_eq!(capped.wire, NonNegativeAmount::zero());
        assert_ledgers(&capped, "1.000000000000000001");
    }

    #[test]
    fn quantization_error_is_bounded_per_request_and_accumulates_linearly() {
        let mut state = state_with_wire("5");
        for _ in 0..3 {
            assert_eq!(
                request(&mut state, 2, 3),
                Ok("0.666666666666666666".to_owned())
            );
        }
        assert_eq!(state.wire.to_string(), "3.000000000000000002");
        assert_ledgers(&state, "1.999999999999999998");
        // Three requests lose less than three quanta from the exact total 2;
        // the capped conserved transfer itself has zero additional rounding.
        assert_eq!(
            &Amount::from_i128(2) - state.lifetime_clips.amount(),
            Amount::parse("0.000000000000000002").unwrap()
        );
    }
}
