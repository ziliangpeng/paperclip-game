//! Locked deterministic binary64 evaluation for G02 demand powers and Wire sine.
//!
//! Dependency and accuracy selection: `libm 0.2.16`, default features disabled,
//! `force-soft-floats` enabled. Unit tests replay independently generated
//! high-precision references. Integer decisions use the domain and margins
//! established by that research, never host `powf`/`sin`.

use super::amount::{Amount, IntegralAmount, NonNegativeAmount, SafeU64};
use num_bigint::BigInt;
use std::error::Error;
use std::fmt;

/// Integer floor/ceil decisions are committed only below this exact 2^50 bound.
pub const DECISION_LIMIT: f64 = 1_125_899_906_842_624.0;
const TWO52: u64 = 1_u64 << 52;
#[cfg(test)]
const TWO53: u64 = 1_u64 << 53;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EvaluatorError {
    InvalidDomain,
    NonFinite,
    OutsideDecisionDomain,
    /// Capacity may remain legal while the finite Processor curve cannot
    /// represent the requested new count. PCG-026 requires this distinct case.
    OutsideProcessorDomain,
}

impl fmt::Display for EvaluatorError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::InvalidDomain => "evaluator input is outside its mathematical domain",
            Self::NonFinite => "evaluator produced a non-finite result",
            Self::OutsideDecisionDomain => {
                "evaluator result cannot prove the required integer decision"
            }
            Self::OutsideProcessorDomain => {
                "processor count exceeds the supported creativity evaluator domain"
            }
        })
    }
}

impl Error for EvaluatorError {}

/// A reduced positive rational retains formula meaning until the named conversion.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExactRatio {
    numerator: BigInt,
    denominator: BigInt,
}

impl ExactRatio {
    pub fn new(numerator: BigInt, denominator: BigInt) -> Result<Self, EvaluatorError> {
        if numerator < BigInt::from(0u8) || denominator <= BigInt::from(0u8) {
            return Err(EvaluatorError::InvalidDomain);
        }
        let divisor = gcd(&numerator, &denominator);
        Ok(Self {
            numerator: numerator / &divisor,
            denominator: denominator / divisor,
        })
    }

    pub fn numerator(&self) -> &BigInt {
        &self.numerator
    }

    pub fn denominator(&self) -> &BigInt {
        &self.denominator
    }

    pub fn is_zero(&self) -> bool {
        self.numerator == BigInt::from(0u8)
    }

    pub fn is_at_most_one(&self) -> bool {
        self.numerator <= self.denominator
    }

    /// Exact nearest-binary64 conversion, ties to even, including subnormals.
    pub fn to_f64(&self) -> Result<f64, EvaluatorError> {
        if self.is_zero() {
            return Ok(0.0);
        }
        positive_ratio_to_f64(&self.numerator, &self.denominator)
    }
}

fn gcd(left: &BigInt, right: &BigInt) -> BigInt {
    let mut a = left.clone();
    let mut b = right.clone();
    while b != BigInt::from(0u8) {
        let remainder = &a % &b;
        a = b;
        b = remainder;
    }
    if a == BigInt::from(0u8) {
        BigInt::from(1u8)
    } else {
        a
    }
}

fn bit_length(value: &BigInt) -> i64 {
    i64::try_from(value.bits()).expect("BigInt bit length fits i64 in allocated state")
}

fn compare_shifted(numerator: &BigInt, denominator: &BigInt, shift: i64) -> std::cmp::Ordering {
    if shift >= 0 {
        numerator.cmp(&(denominator << usize::try_from(shift).expect("nonnegative shift")))
    } else {
        (numerator << usize::try_from(-shift).expect("negative shift magnitude")).cmp(denominator)
    }
}

/// Return round-to-nearest-even of `numerator / denominator / 2^shift`.
fn rounded_dyadic(numerator: &BigInt, denominator: &BigInt, shift: i64) -> BigInt {
    let (scaled_numerator, scaled_denominator) = if shift >= 0 {
        (
            numerator.clone(),
            denominator << usize::try_from(shift).expect("nonnegative shift"),
        )
    } else {
        (
            numerator << usize::try_from(-shift).expect("negative shift magnitude"),
            denominator.clone(),
        )
    };
    let mut quotient = &scaled_numerator / &scaled_denominator;
    let remainder = &scaled_numerator % &scaled_denominator;
    let twice_remainder = &remainder * 2u8;
    if twice_remainder > scaled_denominator
        || (twice_remainder == scaled_denominator
            && &quotient % BigInt::from(2u8) == BigInt::from(1u8))
    {
        quotient += 1u8;
    }
    quotient
}

fn positive_ratio_to_f64(numerator: &BigInt, denominator: &BigInt) -> Result<f64, EvaluatorError> {
    let mut exponent = bit_length(numerator) - bit_length(denominator);
    if compare_shifted(numerator, denominator, exponent).is_lt() {
        exponent -= 1;
    }
    if exponent >= -1022 {
        let mut significand = rounded_dyadic(numerator, denominator, exponent - 52);
        if significand == BigInt::from(TWO52 << 1) {
            significand = BigInt::from(TWO52);
            exponent += 1;
        }
        if exponent > 1023 {
            return Err(EvaluatorError::NonFinite);
        }
        let fraction = (&significand - BigInt::from(TWO52))
            .to_str_radix(10)
            .parse::<u64>()
            .map_err(|_| EvaluatorError::NonFinite)?;
        let bits = (u64::try_from(exponent + 1023).expect("normal exponent") << 52) | fraction;
        return Ok(f64::from_bits(bits));
    }
    let significand = rounded_dyadic(numerator, denominator, -1074);
    let significand = significand
        .to_str_radix(10)
        .parse::<u64>()
        .map_err(|_| EvaluatorError::NonFinite)?;
    // Subnormal rounding can produce the minimum normal, which has the same bits.
    Ok(f64::from_bits(significand))
}

fn amount_to_f64(value: &Amount) -> Result<f64, EvaluatorError> {
    if value.is_negative() {
        return Err(EvaluatorError::InvalidDomain);
    }
    let parsed = value
        .to_canonical_string()
        .parse::<f64>()
        .map_err(|_| EvaluatorError::NonFinite)?;
    if !parsed.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    Ok(parsed)
}

/// Exact upper endpoint of the conservative Processor evaluator domain.
///
/// This is a numerical domain, not a gameplay cap. For P>=1 the real
/// `log10(P)*P^1.1+P-1` curve is strictly increasing. High-precision boundary
/// evaluation proves `R(2^923)*(1+2^-48) < f64::MAX`, while `R(2^924)` itself
/// exceeds that finite range. Exact integers above this endpoint are rejected
/// before conversion with `OutsideProcessorDomain`, as PCG-026 requires.
pub const PROCESSOR_DOMAIN_MAX_EXPONENT: usize = 923;

pub fn processor_domain_upper() -> BigInt {
    BigInt::from(1u8) << PROCESSOR_DOMAIN_MAX_EXPONENT
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ProcessorSpeedStages {
    pub binary_input: f64,
    pub log10: f64,
    pub power: f64,
    pub composite: f64,
}

/// Evaluate x^1.1 after exact m*2^e reduction. The 11/10 exponent here is
/// independent of the G02 23/20 `normalized_power` implementation below.
pub fn normalized_processor_power(input: f64) -> Result<f64, EvaluatorError> {
    if !input.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if input < 1.0 {
        return Err(EvaluatorError::InvalidDomain);
    }
    let input_bits = input.to_bits();
    let exponent = ((input_bits >> 52) & 0x7ff) as i32 - 1023;
    let mantissa = f64::from_bits((input_bits & ((1_u64 << 52) - 1)) | (1023_u64 << 52));
    let turns = exponent.div_euclid(10);
    let remainder = exponent.rem_euclid(10);
    let integer_exponent = 11 * turns + 11 * remainder / 10;
    let fractional_exponent = (11 * remainder % 10) as f64 / 10.0;
    let reduced = libm::pow(mantissa, 1.1) * libm::pow(2.0, fractional_exponent);
    let output = libm::scalbn(reduced, integer_exponent);
    if !output.is_finite() || output <= 0.0 {
        return if output.is_finite() {
            Err(EvaluatorError::InvalidDomain)
        } else {
            Err(EvaluatorError::NonFinite)
        };
    }
    Ok(output)
}

fn evaluate_processor_curve(input: f64) -> Result<ProcessorSpeedStages, EvaluatorError> {
    if !input.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if input < 1.0 {
        return Err(EvaluatorError::InvalidDomain);
    }
    let log10 = libm::log10(input);
    if !log10.is_finite() || log10 < 0.0 {
        return if log10.is_finite() {
            Err(EvaluatorError::InvalidDomain)
        } else {
            Err(EvaluatorError::NonFinite)
        };
    }
    let power = normalized_processor_power(input)?;
    let product = log10 * power;
    if !product.is_finite() || product < 0.0 {
        return if product.is_finite() {
            Err(EvaluatorError::InvalidDomain)
        } else {
            Err(EvaluatorError::NonFinite)
        };
    }
    let with_processor = product + input;
    if !with_processor.is_finite() || with_processor < 0.0 {
        return if with_processor.is_finite() {
            Err(EvaluatorError::InvalidDomain)
        } else {
            Err(EvaluatorError::NonFinite)
        };
    }
    let composite = with_processor - 1.0;
    if !composite.is_finite() || composite < 0.0 {
        return if composite.is_finite() {
            Err(EvaluatorError::InvalidDomain)
        } else {
            Err(EvaluatorError::NonFinite)
        };
    }
    Ok(ProcessorSpeedStages {
        binary_input: input,
        log10,
        power,
        composite,
    })
}

/// Exact-P domain gate and named binary64 stages for independent native tests.
/// The real game Command supplies only the server's stored integral counter.
pub fn creativity_speed_ratio_stages(
    input: &ExactRatio,
) -> Result<ProcessorSpeedStages, EvaluatorError> {
    if input.denominator() != &BigInt::from(1u8) || input.numerator() < &BigInt::from(1u8) {
        return Err(EvaluatorError::InvalidDomain);
    }
    if input.numerator() > &processor_domain_upper() {
        return Err(EvaluatorError::OutsideProcessorDomain);
    }
    if input.numerator() == &BigInt::from(1u8) {
        // Pure one-Processor recomputation is exactly zero. Fresh speed 1 is
        // constructed separately by state initialization, never conflated here.
        return Ok(ProcessorSpeedStages {
            binary_input: 1.0,
            log10: 0.0,
            power: 1.0,
            composite: 0.0,
        });
    }
    let binary_input = input.to_f64()?;
    evaluate_processor_curve(binary_input)
}

/// Convert the final finite continuous result exactly once to the Amount grid.
/// No logarithm/power/composition stage uses this quantization.
pub fn processor_speed_to_amount(continuous: f64) -> Result<NonNegativeAmount, EvaluatorError> {
    if !continuous.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if continuous < 0.0 {
        return Err(EvaluatorError::InvalidDomain);
    }
    let bits = continuous.to_bits();
    let encoded_exponent = ((bits >> 52) & 0x7ff) as i32;
    let fraction = bits & ((1_u64 << 52) - 1);
    let (significand, exponent) = if encoded_exponent == 0 {
        (fraction, -1074)
    } else {
        (fraction | (1_u64 << 52), encoded_exponent - 1023 - 52)
    };
    if significand == 0 {
        return Ok(NonNegativeAmount::zero());
    }
    let (numerator, denominator) = if exponent >= 0 {
        (
            BigInt::from(significand)
                << usize::try_from(exponent).expect("nonnegative f64 exponent"),
            BigInt::from(1u8),
        )
    } else {
        (
            BigInt::from(significand),
            BigInt::from(1u8)
                << usize::try_from(-exponent).expect("negative f64 exponent magnitude"),
        )
    };
    Amount::quantize_ratio(&numerator, &denominator)
        .map_err(|_| EvaluatorError::InvalidDomain)?
        .nonnegative()
        .map_err(|_| EvaluatorError::InvalidDomain)
}

pub fn creativity_speed_ratio(input: &ExactRatio) -> Result<NonNegativeAmount, EvaluatorError> {
    let stages = creativity_speed_ratio_stages(input)?;
    processor_speed_to_amount(stages.composite)
}

pub fn creativity_speed(processors: &IntegralAmount) -> Result<NonNegativeAmount, EvaluatorError> {
    let scale = Amount::from_i128(1).mantissa().clone();
    let numerator = processors.amount().mantissa() / scale;
    let input = ExactRatio::new(numerator, BigInt::from(1u8))?;
    creativity_speed_ratio(&input)
}

/// Evaluate x^1.15 after an exact m*2^e reduction into the measured domain.
pub fn normalized_power(input: f64) -> Result<f64, EvaluatorError> {
    if !input.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if input < 1.0 {
        return Err(EvaluatorError::InvalidDomain);
    }
    let input_bits = input.to_bits();
    let exponent = ((input_bits >> 52) & 0x7ff) as i32 - 1023;
    let mantissa = f64::from_bits((input_bits & ((1_u64 << 52) - 1)) | (1023_u64 << 52));
    let turns = exponent.div_euclid(20);
    let remainder = exponent.rem_euclid(20);
    let integer_exponent = 23 * turns + 23 * remainder / 20;
    let fractional_exponent = (23 * remainder % 20) as f64 / 20.0;
    let reduced = libm::pow(mantissa, 1.15) * libm::pow(2.0, fractional_exponent);
    let output = libm::scalbn(reduced, integer_exponent);
    if !output.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    Ok(output)
}

/// Source sale request `floor(0.7 * demand^1.15)` under the verified <2^50 domain.
pub fn sale_request(demand: &ExactRatio) -> Result<u64, EvaluatorError> {
    if demand.is_zero() {
        return Err(EvaluatorError::InvalidDomain);
    }
    if demand.is_at_most_one() {
        // For 0<D<1, D^1.15<D. At D=1 the value is 0.7. Both floors are zero.
        return Ok(0);
    }
    let input = demand.to_f64()?;
    // nearest(D>1) may equal one; that is the documented correctly rounded boundary.
    let power = normalized_power(input)?;
    let composite = 0.7 * power;
    if !composite.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if composite < 0.0 {
        return Err(EvaluatorError::InvalidDomain);
    }
    if composite >= DECISION_LIMIT {
        return Err(EvaluatorError::OutsideDecisionDomain);
    }
    let request = libm::floor(composite);
    if request < 0.0 || request >= DECISION_LIMIT {
        return Err(EvaluatorError::OutsideDecisionDomain);
    }
    // <2^50 guarantees an exact bounded JSON-safe integer after floor.
    Ok(request as u64)
}

/// Source Wire quote `ceil(base + 6*sin(counter))` in its verified finite domain.
pub fn wire_quote(base: &Amount, counter: SafeU64) -> Result<u64, EvaluatorError> {
    let base = amount_to_f64(base)?;
    let sine = libm::sin(counter.get() as f64);
    if !sine.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    let composite = base + 6.0 * sine;
    if !composite.is_finite() {
        return Err(EvaluatorError::NonFinite);
    }
    if composite <= 0.0 || composite >= DECISION_LIMIT {
        return Err(EvaluatorError::OutsideDecisionDomain);
    }
    let quote = libm::ceil(composite);
    if quote <= 0.0 || quote > DECISION_LIMIT {
        return Err(EvaluatorError::OutsideDecisionDomain);
    }
    Ok(quote as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ratio(numerator: u128, denominator: u128) -> ExactRatio {
        ExactRatio::new(BigInt::from(numerator), BigInt::from(denominator)).unwrap()
    }

    #[test]
    fn exact_ratio_conversion_covers_ties_subnormals_and_overflow() {
        for (numerator, denominator, expected) in [
            (32_u128, 10_u128, 3.2_f64),
            (1, 10, 0.1),
            (9_007_199_254_740_993, 1, 9_007_199_254_740_992.0),
            (9_007_199_254_740_995, 1, 9_007_199_254_740_996.0),
            (1, 1_u128 << 52, 2_f64.powi(-52)),
        ] {
            let actual = ratio(numerator, denominator).to_f64().unwrap();
            assert_eq!(
                actual.to_bits(),
                expected.to_bits(),
                "{numerator}/{denominator}"
            );
        }
        let midpoint = ExactRatio::new(BigInt::from(TWO53 + 1), BigInt::from(TWO53)).unwrap();
        assert_eq!(midpoint.to_f64().unwrap(), 1.0);
        let smallest = ExactRatio::new(BigInt::from(1u8), BigInt::from(1u8) << 1074).unwrap();
        assert_eq!(smallest.to_f64().unwrap().to_bits(), 1);
        let zero_tie = ExactRatio::new(BigInt::from(1u8), BigInt::from(1u8) << 1075).unwrap();
        assert_eq!(zero_tie.to_f64().unwrap().to_bits(), 0);
        let above_zero_tie =
            ExactRatio::new(BigInt::from((1u128 << 53) + 1), BigInt::from(1u8) << 1128).unwrap();
        assert_eq!(above_zero_tie.to_f64().unwrap().to_bits(), 1);
    }

    #[test]
    fn negative_domain_table_rejects_bad_ratios_and_nonfinite_results() {
        assert_eq!(
            ExactRatio::new(BigInt::from(1u8), BigInt::from(0u8)),
            Err(EvaluatorError::InvalidDomain)
        );
        assert_eq!(
            ExactRatio::new(BigInt::from(-1), BigInt::from(1u8)),
            Err(EvaluatorError::InvalidDomain)
        );
        assert_eq!(
            sale_request(&ratio(0, 1)),
            Err(EvaluatorError::InvalidDomain)
        );
        assert_eq!(normalized_power(f64::NAN), Err(EvaluatorError::NonFinite));
        assert_eq!(
            normalized_power(f64::INFINITY),
            Err(EvaluatorError::NonFinite)
        );
        assert_eq!(normalized_power(0.5), Err(EvaluatorError::InvalidDomain));
        assert_eq!(normalized_power(1.0e300), Err(EvaluatorError::NonFinite));
    }

    #[test]
    fn source_sale_and_quote_boundaries_are_deterministic() {
        assert_eq!(sale_request(&ratio(8, 7)), Ok(0));
        assert_eq!(sale_request(&ratio(1, 1)), Ok(0));
        assert_eq!(sale_request(&ratio(16, 5)), Ok(2));
        assert_eq!(sale_request(&ratio(80, 1)), Ok(108));
        assert_eq!(
            sale_request(&ratio(1_000_000_000_000_000_000, 1)),
            Err(EvaluatorError::OutsideDecisionDomain)
        );
        assert_eq!(
            wire_quote(&Amount::from_i128(20), SafeU64::new(1).unwrap()),
            Ok(26)
        );
        assert_eq!(
            wire_quote(&Amount::from_i128(20), SafeU64::new(3).unwrap()),
            Ok(21)
        );
        assert_eq!(
            wire_quote(&Amount::from_i128(0), SafeU64::new(4).unwrap()),
            Err(EvaluatorError::OutsideDecisionDomain)
        );
        assert_eq!(
            wire_quote(
                &Amount::parse("9007199254740993").unwrap(),
                SafeU64::new(0).unwrap(),
            ),
            Err(EvaluatorError::OutsideDecisionDomain)
        );
    }

    #[test]
    fn normalized_power_has_direct_native_reference_and_repeated_bit_identity() {
        let expected = 0x400e7ad5c74b0d74_u64;
        for _ in 0..100 {
            assert_eq!(normalized_power(3.2).unwrap().to_bits(), expected);
        }
        assert_eq!(libm::sin(0.0).to_bits(), 0);
        assert_eq!(libm::sin(4.0).to_bits(), 0xbfe837b9dddc1eae);
    }

    #[test]
    fn processor_raw_composition_rejects_nonfinite_stages_without_domain_bypass() {
        let next_dyadic = libm::scalbn(1.0, 924);
        assert!(normalized_processor_power(next_dyadic).unwrap().is_finite());
        assert_eq!(
            evaluate_processor_curve(next_dyadic),
            Err(EvaluatorError::NonFinite)
        );
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(
                evaluate_processor_curve(invalid),
                Err(EvaluatorError::NonFinite)
            );
            assert_eq!(
                normalized_processor_power(invalid),
                Err(EvaluatorError::NonFinite)
            );
        }
        assert_eq!(
            evaluate_processor_curve(0.5),
            Err(EvaluatorError::InvalidDomain)
        );
    }
}
