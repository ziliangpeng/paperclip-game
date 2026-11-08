//! Exact fixed-point values and bounded transport integers.

use num_bigint::{BigInt, Sign};
use serde::de::Error as _;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use std::cmp::Ordering;
use std::error::Error;
use std::fmt;
use std::ops::{Add, Sub};

const FRACTION_DIGITS: usize = 18;
const MAX_CANONICAL_BYTES: usize = 16 * 1024;
pub const MAX_SAFE_JSON_INTEGER: u64 = 9_007_199_254_740_991;

/// An exact signed value represented as `mantissa * 10^-18`.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct Amount {
    mantissa: BigInt,
}

impl Amount {
    pub fn zero() -> Self {
        Self::default()
    }

    pub fn from_i128(value: i128) -> Self {
        Self::from_mantissa(BigInt::from(value) * decimal_scale())
    }

    /// Construct directly on the exact 10^-18 grid.
    pub fn from_mantissa(mantissa: BigInt) -> Self {
        Self { mantissa }
    }

    pub fn mantissa(&self) -> &BigInt {
        &self.mantissa
    }

    pub fn is_zero(&self) -> bool {
        self.mantissa == BigInt::from(0)
    }

    pub fn is_negative(&self) -> bool {
        self.mantissa.sign() == Sign::Minus
    }

    pub fn multiply_integer(&self, multiplier: &BigInt) -> Self {
        Self::from_mantissa(&self.mantissa * multiplier)
    }

    /// Quantize an exact rational to the grid, toward zero.
    pub fn quantize_ratio(numerator: &BigInt, denominator: &BigInt) -> Result<Self, QuantizeError> {
        if *denominator == BigInt::from(0) {
            return Err(QuantizeError::ZeroDenominator);
        }
        Ok(Self::from_mantissa(
            (numerator * decimal_scale()) / denominator,
        ))
    }

    pub fn min(self, other: Self) -> Self {
        if self <= other { self } else { other }
    }

    pub fn max(self, other: Self) -> Self {
        if self >= other { self } else { other }
    }

    pub fn parse(text: &str) -> Result<Self, AmountParseError> {
        if text.len() > MAX_CANONICAL_BYTES {
            return Err(AmountParseError::ResourceLimit);
        }
        if text.is_empty() || !text.is_ascii() {
            return Err(AmountParseError::InvalidCanonical);
        }

        let (negative, unsigned) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text),
        };
        let mut parts = unsigned.split('.');
        let whole = parts.next().ok_or(AmountParseError::InvalidCanonical)?;
        let fraction = parts.next();
        if parts.next().is_some()
            || whole.is_empty()
            || !whole.bytes().all(|byte| byte.is_ascii_digit())
            || (whole.len() > 1 && whole.starts_with('0'))
        {
            return Err(AmountParseError::InvalidCanonical);
        }

        let fraction = match fraction {
            Some(value)
                if !value.is_empty()
                    && value.len() <= FRACTION_DIGITS
                    && value.bytes().all(|byte| byte.is_ascii_digit())
                    && !value.ends_with('0') =>
            {
                value
            }
            Some(_) => return Err(AmountParseError::InvalidCanonical),
            None => "",
        };

        let mut digits = String::with_capacity(whole.len() + FRACTION_DIGITS);
        digits.push_str(whole);
        digits.push_str(fraction);
        for _ in fraction.len()..FRACTION_DIGITS {
            digits.push('0');
        }
        let mut mantissa =
            BigInt::parse_bytes(digits.as_bytes(), 10).ok_or(AmountParseError::InvalidCanonical)?;
        if negative {
            if mantissa == BigInt::from(0) {
                return Err(AmountParseError::InvalidCanonical);
            }
            mantissa = -mantissa;
        }
        Ok(Self { mantissa })
    }

    pub fn to_canonical_string(&self) -> String {
        self.to_string()
    }

    pub fn nonnegative(self) -> Result<NonNegativeAmount, AmountDomainError> {
        NonNegativeAmount::new(self)
    }

    pub fn integral(self) -> Result<IntegralAmount, AmountDomainError> {
        IntegralAmount::new(self)
    }
}

fn decimal_scale() -> BigInt {
    BigInt::from(10u8).pow(FRACTION_DIGITS as u32)
}

impl fmt::Display for Amount {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.is_zero() {
            return formatter.write_str("0");
        }
        let negative = self.is_negative();
        let absolute = if negative {
            -&self.mantissa
        } else {
            self.mantissa.clone()
        };
        let digits = absolute.to_str_radix(10);
        if negative {
            formatter.write_str("-")?;
        }
        if digits.len() <= FRACTION_DIGITS {
            formatter.write_str("0.")?;
            for _ in digits.len()..FRACTION_DIGITS {
                formatter.write_str("0")?;
            }
            let trimmed = digits.trim_end_matches('0');
            formatter.write_str(trimmed)
        } else {
            let split = digits.len() - FRACTION_DIGITS;
            let (whole, fraction) = digits.split_at(split);
            formatter.write_str(whole)?;
            let fraction = fraction.trim_end_matches('0');
            if !fraction.is_empty() {
                write!(formatter, ".{fraction}")?;
            }
            Ok(())
        }
    }
}

impl Ord for Amount {
    fn cmp(&self, other: &Self) -> Ordering {
        self.mantissa.cmp(&other.mantissa)
    }
}

impl PartialOrd for Amount {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl<'b> Add<&'b Amount> for &Amount {
    type Output = Amount;

    fn add(self, rhs: &'b Amount) -> Self::Output {
        Amount::from_mantissa(&self.mantissa + &rhs.mantissa)
    }
}

impl<'b> Sub<&'b Amount> for &Amount {
    type Output = Amount;

    fn sub(self, rhs: &'b Amount) -> Self::Output {
        Amount::from_mantissa(&self.mantissa - &rhs.mantissa)
    }
}

impl Serialize for Amount {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_canonical_string())
    }
}

impl<'de> Deserialize<'de> for Amount {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let text = String::deserialize(deserializer)?;
        Self::parse(&text).map_err(D::Error::custom)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmountParseError {
    InvalidCanonical,
    ResourceLimit,
}

impl fmt::Display for AmountParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidCanonical => formatter.write_str("invalid canonical Amount"),
            Self::ResourceLimit => formatter.write_str("canonical Amount exceeds the decode limit"),
        }
    }
}

impl Error for AmountParseError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmountDomainError {
    Negative,
    Fractional,
}

impl fmt::Display for AmountDomainError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Negative => formatter.write_str("Amount must be nonnegative"),
            Self::Fractional => formatter.write_str("Amount must be integral"),
        }
    }
}

impl Error for AmountDomainError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum QuantizeError {
    ZeroDenominator,
}

impl fmt::Display for QuantizeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroDenominator => formatter.write_str("rational denominator is zero"),
        }
    }
}

impl Error for QuantizeError {}

#[derive(Clone, Debug, Default, Eq, Ord, PartialEq, PartialOrd)]
pub struct NonNegativeAmount(Amount);

impl NonNegativeAmount {
    pub fn new(value: Amount) -> Result<Self, AmountDomainError> {
        if value.is_negative() {
            Err(AmountDomainError::Negative)
        } else {
            Ok(Self(value))
        }
    }

    pub fn from_i128(value: i128) -> Result<Self, AmountDomainError> {
        Self::new(Amount::from_i128(value))
    }

    pub fn zero() -> Self {
        Self(Amount::zero())
    }

    pub fn amount(&self) -> &Amount {
        &self.0
    }

    pub fn into_amount(self) -> Amount {
        self.0
    }

    pub fn add_exact(&self, other: &Self) -> Self {
        Self(&self.0 + &other.0)
    }

    pub fn checked_sub(&self, other: &Self) -> Result<Self, AmountDomainError> {
        Self::new(&self.0 - &other.0)
    }

    pub fn parse(text: &str) -> Result<Self, String> {
        Amount::parse(text)
            .map_err(|error| error.to_string())?
            .nonnegative()
            .map_err(|error| error.to_string())
    }
}

impl fmt::Display for NonNegativeAmount {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

impl Serialize for NonNegativeAmount {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        self.0.serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for NonNegativeAmount {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        Amount::deserialize(deserializer)?
            .nonnegative()
            .map_err(D::Error::custom)
    }
}

#[derive(Clone, Debug, Default, Eq, Ord, PartialEq, PartialOrd)]
pub struct IntegralAmount(Amount);

impl IntegralAmount {
    pub fn new(value: Amount) -> Result<Self, AmountDomainError> {
        if &value.mantissa % decimal_scale() == BigInt::from(0) {
            Ok(Self(value))
        } else {
            Err(AmountDomainError::Fractional)
        }
    }

    pub fn from_i128(value: i128) -> Self {
        Self(Amount::from_i128(value))
    }

    pub fn amount(&self) -> &Amount {
        &self.0
    }
}

impl fmt::Display for IntegralAmount {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

impl Serialize for IntegralAmount {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        self.0.serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for IntegralAmount {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        Amount::deserialize(deserializer)?
            .integral()
            .map_err(D::Error::custom)
    }
}

/// A checked unsigned integer that stays exactly representable in JSON clients.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct SafeU64(u64);

impl SafeU64 {
    pub fn new(value: u64) -> Result<Self, BoundedIntegerError> {
        if value <= MAX_SAFE_JSON_INTEGER {
            Ok(Self(value))
        } else {
            Err(BoundedIntegerError::AboveJsonSafeRange)
        }
    }

    pub fn get(self) -> u64 {
        self.0
    }

    pub fn checked_add(self, increment: u64) -> Result<Self, BoundedIntegerError> {
        let value = self
            .0
            .checked_add(increment)
            .ok_or(BoundedIntegerError::Overflow)?;
        Self::new(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BoundedIntegerError {
    AboveJsonSafeRange,
    Overflow,
}

impl fmt::Display for BoundedIntegerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::AboveJsonSafeRange => formatter.write_str("integer exceeds the JSON-safe range"),
            Self::Overflow => formatter.write_str("integer addition overflow"),
        }
    }
}

impl Error for BoundedIntegerError {}

impl Serialize for SafeU64 {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_u64(self.0)
    }
}

impl<'de> Deserialize<'de> for SafeU64 {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        Self::new(u64::deserialize(deserializer)?).map_err(D::Error::custom)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn huge(text: &str) -> BigInt {
        BigInt::parse_bytes(text.as_bytes(), 10).expect("valid test integer")
    }

    #[test]
    fn canonical_roundtrips_cover_huge_tiny_and_signed_values() {
        for text in [
            "0",
            "0.000000000000000001",
            "9007199254740993",
            "340282366920938463463374607431768211457",
            "30000000000000000000000000000000000000000000000000000001",
            "-41117.99",
            "-0.000000000000000001",
            "6.21",
            "0.2",
            "1000",
        ] {
            let amount = Amount::parse(text).expect("canonical test value");
            assert_eq!(amount.to_canonical_string(), text);
            assert_eq!(Amount::from_mantissa(amount.mantissa().clone()), amount);
            assert_eq!(
                serde_json::to_string(&amount).unwrap(),
                format!("\"{text}\"")
            );
            assert_eq!(
                serde_json::from_str::<Amount>(&format!("\"{text}\"")).unwrap(),
                amount
            );
        }
    }

    #[test]
    fn negative_table_rejects_malformed_canonical_strings_and_wrong_json_primitives() {
        for invalid in [
            "",
            "-0",
            "-0.000000000000000000",
            "+1",
            "01",
            "1.",
            "1.0",
            ".5",
            "1e-18",
            "NaN",
            "Infinity",
            " 1",
            "1 ",
            "1\n",
            "١",
            "1_000",
            "0.0000000000000000001",
            "0.1000000000000000000",
            "1.230",
            "1.2.3",
        ] {
            assert_eq!(
                Amount::parse(invalid),
                Err(AmountParseError::InvalidCanonical),
                "wrong category for {invalid:?}"
            );
            eprintln!("negative Amount canonical case {invalid:?}: InvalidCanonical");
        }
        for json in ["1", "1.0", "true", "null", "[]", "{}"] {
            let error = serde_json::from_str::<Amount>(json).unwrap_err();
            assert_eq!(error.classify(), serde_json::error::Category::Data);
            assert!(
                error.to_string().starts_with("invalid type:"),
                "wrong Serde category for {json}: {error}"
            );
            eprintln!("negative Amount JSON case {json}: Data/invalid type");
        }
    }

    #[derive(Debug, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct TypedAmount {
        amount: Amount,
    }

    #[test]
    fn negative_table_rejects_unknown_and_duplicate_typed_keys() {
        for (json, expected_prefix) in [
            (r#"{"amount":"1","extra":"0"}"#, "unknown field `extra`"),
            (r#"{"amount":"1","amount":"2"}"#, "duplicate field `amount`"),
        ] {
            let error = serde_json::from_str::<TypedAmount>(json).unwrap_err();
            assert_eq!(error.classify(), serde_json::error::Category::Data);
            assert!(error.to_string().starts_with(expected_prefix), "{error}");
            eprintln!("negative typed Amount case {json}: {expected_prefix}");
        }
        assert_eq!(
            serde_json::from_str::<TypedAmount>(r#"{"amount":"1"}"#)
                .unwrap()
                .amount,
            Amount::from_i128(1)
        );
    }

    #[test]
    fn negative_table_resource_guard_is_explicit_not_a_game_value_cap() {
        let accepted = format!("1{}", "2".repeat(MAX_CANONICAL_BYTES - 1));
        assert_eq!(
            Amount::parse(&accepted).unwrap().to_canonical_string(),
            accepted
        );
        let rejected = format!("1{}", "2".repeat(MAX_CANONICAL_BYTES));
        assert_eq!(
            Amount::parse(&rejected),
            Err(AmountParseError::ResourceLimit)
        );
    }

    #[test]
    fn arithmetic_is_exact_without_tolerance_or_fixed_word_limits() {
        let universe_plus_one =
            Amount::parse("30000000000000000000000000000000000000000000000000000001").unwrap();
        let universe =
            Amount::parse("30000000000000000000000000000000000000000000000000000000").unwrap();
        assert_eq!(&universe_plus_one - &universe, Amount::from_i128(1));
        let quantum = Amount::parse("0.000000000000000001").unwrap();
        assert_eq!(
            &universe + &quantum,
            Amount::parse(
                "30000000000000000000000000000000000000000000000000000000.000000000000000001"
            )
            .unwrap()
        );
        assert!(Amount::from_mantissa(huge(&"9".repeat(80))) > universe);
        assert_eq!(
            Amount::from_i128(-7).multiply_integer(&BigInt::from(-3)),
            Amount::from_i128(21)
        );
    }

    #[test]
    fn negative_table_rejects_negative_and_fractional_semantic_domains() {
        assert_eq!(
            Amount::from_i128(-1).nonnegative(),
            Err(AmountDomainError::Negative)
        );
        assert_eq!(
            Amount::parse("1.000000000000000001").unwrap().integral(),
            Err(AmountDomainError::Fractional)
        );
        let negative_json = serde_json::from_str::<NonNegativeAmount>("\"-1\"").unwrap_err();
        assert_eq!(negative_json.classify(), serde_json::error::Category::Data);
        assert!(
            negative_json
                .to_string()
                .starts_with("Amount must be nonnegative")
        );
        eprintln!("negative nonnegative JSON case: AmountDomainError::Negative");
        let fractional_json =
            serde_json::from_str::<IntegralAmount>("\"0.000000000000000001\"").unwrap_err();
        assert_eq!(
            fractional_json.classify(),
            serde_json::error::Category::Data
        );
        assert!(
            fractional_json
                .to_string()
                .starts_with("Amount must be integral")
        );
        eprintln!("fractional integral JSON case: AmountDomainError::Fractional");
        assert_eq!(IntegralAmount::from_i128(-4).to_string(), "-4");
    }
    #[test]
    fn directed_ratio_quantization_is_toward_zero() {
        let positive = Amount::quantize_ratio(&BigInt::from(2), &BigInt::from(3)).unwrap();
        assert_eq!(positive.to_string(), "0.666666666666666666");
        let negative = Amount::quantize_ratio(&BigInt::from(-2), &BigInt::from(3)).unwrap();
        assert_eq!(negative.to_string(), "-0.666666666666666666");
        let negative_tiny =
            Amount::quantize_ratio(&BigInt::from(-1), &huge("10000000000000000000")).unwrap();
        assert_eq!(negative_tiny, Amount::zero());
        assert_eq!(
            Amount::quantize_ratio(&BigInt::from(1), &BigInt::from(0)),
            Err(QuantizeError::ZeroDenominator)
        );
    }

    #[test]
    fn generated_sequences_match_an_independent_i128_reference() {
        let mut seed = 0x4d59_5df4_d0f3_3173u128;
        for _ in 0..2_000 {
            seed = seed
                .wrapping_mul(0x2360_ed05_1fc6_5da4_4385_df64_9fcc_f645)
                .wrapping_add(1);
            let left = (seed as i128) % 1_000_000_000_000_000_000_000_000i128;
            seed = seed
                .wrapping_mul(0x2360_ed05_1fc6_5da4_4385_df64_9fcc_f645)
                .wrapping_add(1);
            let right = (seed as i128) % 1_000_000_000_000_000_000_000_000i128;
            let a = Amount::from_mantissa(BigInt::from(left));
            let b = Amount::from_mantissa(BigInt::from(right));
            assert_eq!((&a + &b).mantissa(), &BigInt::from(left + right));
            assert_eq!((&a - &b).mantissa(), &BigInt::from(left - right));
            assert_eq!(a.cmp(&b), left.cmp(&right));
            assert_eq!(
                a.clone().min(b.clone()).mantissa(),
                &BigInt::from(left.min(right))
            );
            assert_eq!(
                a.clone().max(b.clone()).mantissa(),
                &BigInt::from(left.max(right))
            );
            assert_eq!(
                a.multiply_integer(&BigInt::from(-17)).mantissa(),
                &BigInt::from(left * -17)
            );
        }
    }

    #[test]
    fn native_big_amount_arithmetic_and_performance_probe() {
        let started = std::time::Instant::now();
        let original =
            Amount::parse("30000000000000000000000000000000000000000000000000000001").unwrap();
        let quantum = Amount::parse("0.000000000000000001").unwrap();
        let mut value = original.clone();
        for _ in 0..10_000 {
            value = &value + &quantum;
        }
        assert_eq!(
            value,
            &original + &Amount::parse("0.00000000000001").unwrap()
        );
        for _ in 0..10_000 {
            value = &value - &quantum;
        }
        assert_eq!(value, original);
        eprintln!(
            "Amount native probe: 10000 large additions and 10000 exact subtractions in {:?}",
            started.elapsed()
        );
    }

    #[test]
    fn generated_ratio_quantization_matches_an_independent_i128_reference() {
        const GRID: i128 = 1_000_000_000_000_000_000;
        let mut seed = 0x7265_2c19u128;
        for _ in 0..2_000 {
            seed = seed
                .wrapping_mul(0x2360_ed05_1fc6_5da4_4385_df64_9fcc_f645)
                .wrapping_add(1);
            let numerator = (seed as i128) % 1_000_000_000_000_000_000i128;
            seed = seed
                .wrapping_mul(0x2360_ed05_1fc6_5da4_4385_df64_9fcc_f645)
                .wrapping_add(1);
            let denominator = (seed as i128).abs() % 1_000_000_000 + 1;
            let expected = numerator * GRID / denominator;
            let actual =
                Amount::quantize_ratio(&BigInt::from(numerator), &BigInt::from(denominator))
                    .unwrap();
            assert_eq!(actual.mantissa(), &BigInt::from(expected));
        }
    }

    #[test]
    fn negative_table_rejects_invalid_bounded_json_integers() {
        assert_eq!(
            SafeU64::new(MAX_SAFE_JSON_INTEGER).unwrap().get(),
            MAX_SAFE_JSON_INTEGER
        );
        for input in [MAX_SAFE_JSON_INTEGER + 1, u64::MAX] {
            assert_eq!(
                SafeU64::new(input),
                Err(BoundedIntegerError::AboveJsonSafeRange)
            );
            eprintln!("unsafe JSON integer {input}: AboveJsonSafeRange");
        }
        assert_eq!(SafeU64::new(5).unwrap().checked_add(7).unwrap().get(), 12);
        for increment in [1, u64::MAX] {
            let expected = if increment == 1 {
                BoundedIntegerError::AboveJsonSafeRange
            } else {
                BoundedIntegerError::Overflow
            };
            assert_eq!(
                SafeU64::new(MAX_SAFE_JSON_INTEGER)
                    .unwrap()
                    .checked_add(increment),
                Err(expected)
            );
            eprintln!("illegal SafeU64 increment {increment}: {expected:?}");
        }
        let encoded = serde_json::to_string(&SafeU64::new(MAX_SAFE_JSON_INTEGER).unwrap()).unwrap();
        assert_eq!(encoded, MAX_SAFE_JSON_INTEGER.to_string());
        assert_eq!(
            serde_json::from_str::<SafeU64>(&encoded).unwrap().get(),
            MAX_SAFE_JSON_INTEGER
        );
        for invalid in ["1.0", "1e0", "\"1\"", "true"] {
            let error = serde_json::from_str::<SafeU64>(invalid).unwrap_err();
            assert_eq!(error.classify(), serde_json::error::Category::Data);
            assert!(error.to_string().starts_with("invalid type:"), "{error}");
            eprintln!("invalid SafeU64 type {invalid}: Data/invalid type");
        }
        let negative = serde_json::from_str::<SafeU64>("-1").unwrap_err();
        assert_eq!(negative.classify(), serde_json::error::Category::Data);
        assert!(
            negative.to_string().starts_with("invalid value:"),
            "{negative}"
        );
        eprintln!("negative SafeU64: Data/invalid value");
        let unsafe_range = serde_json::from_str::<SafeU64>("9007199254740992").unwrap_err();
        assert_eq!(unsafe_range.classify(), serde_json::error::Category::Data);
        assert!(
            unsafe_range
                .to_string()
                .starts_with("integer exceeds the JSON-safe range")
        );
        eprintln!("out-of-range SafeU64: AboveJsonSafeRange");
    }
}
