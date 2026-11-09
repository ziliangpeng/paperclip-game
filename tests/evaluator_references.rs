use num_bigint::BigInt;
use paperclip_game::game::amount::{Amount, SafeU64};
use paperclip_game::game::evaluator::{
    EvaluatorError, ExactRatio, normalized_power, sale_request, wire_quote,
};
use serde::Deserialize;
use sha2::{Digest, Sha256};

const REFERENCES: &[u8] = include_bytes!("data/g02-evaluator/references.json");
const REFERENCE_SHA256: &str = "b0a044a9bdf18cef468297a920aee9dfd027bb4838a6355e16ee35881cdbf7d3";

#[derive(Debug, Deserialize)]
struct ReferenceTable {
    demand_rows: Vec<DemandRow>,
    wire_rows: Vec<SineRow>,
    quote_rows: Vec<QuoteRow>,
}

#[derive(Debug, Deserialize)]
struct DemandRow {
    id: String,
    exact_input_decimal: String,
    input_hex: String,
    pow_output_hex: String,
    composite_output_hex: String,
    // Exact decimal strings preserve arbitrarily large reference integers.
    // Only the decision-domain subset is converted to bounded u64 values.
    reference_floor: Option<String>,
    candidate_floor: Option<String>,
    decision_domain: bool,
    exact_reference_integer_margin: String,
}

#[derive(Debug, Deserialize)]
struct SineRow {
    counter: String,
    sin_output_hex: String,
}

#[derive(Debug, Deserialize)]
struct QuoteRow {
    counter: String,
    base: String,
    candidate_composite_hex: String,
    reference_ceil: i128,
    candidate_ceil: i128,
    exact_reference_integer_margin: String,
}

fn bits(text: &str) -> u64 {
    u64::from_str_radix(text, 16).unwrap()
}

/// Preserve all decimal digits and exponents from the independent generator.
fn decimal_ratio(text: &str) -> ExactRatio {
    let (mantissa, exponent) = text
        .split_once(['e', 'E'])
        .map_or((text, 0), |(left, right)| {
            (left, right.parse::<i32>().unwrap())
        });
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    assert!(!whole.is_empty());
    assert!(whole.bytes().all(|byte| byte.is_ascii_digit()));
    assert!(fraction.bytes().all(|byte| byte.is_ascii_digit()));
    let digits = format!("{whole}{fraction}");
    let mut numerator = BigInt::parse_bytes(digits.as_bytes(), 10).unwrap();
    let mut denominator = BigInt::from(10u8).pow(fraction.len() as u32);
    if exponent >= 0 {
        numerator *= BigInt::from(10u8).pow(exponent as u32);
    } else {
        denominator *= BigInt::from(10u8).pow((-exponent) as u32);
    }
    ExactRatio::new(numerator, denominator).unwrap()
}

#[test]
fn generated_high_precision_table_locks_native_bits_and_integer_margins() {
    assert_eq!(
        format!("{:x}", Sha256::digest(REFERENCES)),
        REFERENCE_SHA256
    );
    let table: ReferenceTable = serde_json::from_slice(REFERENCES).unwrap();
    assert_eq!(table.demand_rows.len(), 252);
    assert_eq!(table.wire_rows.len(), 591);
    assert_eq!(table.quote_rows.len(), 429);
    let mut in_domain = 0;
    let mut allowed_demand_boundary = 0;
    let mut allowed_quote_boundary = 0;

    for row in &table.demand_rows {
        let input = f64::from_bits(bits(&row.input_hex));
        let expected_power = bits(&row.pow_output_hex);
        let power = normalized_power(input);
        if expected_power == 0x7ff0_0000_0000_0000 {
            assert_eq!(power, Err(EvaluatorError::NonFinite), "{}", row.id);
        } else {
            assert_eq!(power.unwrap().to_bits(), expected_power, "{}", row.id);
            assert_eq!(
                (power.unwrap() * 0.7).to_bits(),
                bits(&row.composite_output_hex),
                "{} composite",
                row.id
            );
        }
        let actual = sale_request(&decimal_ratio(&row.exact_input_decimal));
        if row.decision_domain {
            in_domain += 1;
            let floor = actual.unwrap_or_else(|error| panic!("{} rejected: {error}", row.id));
            let reference = row
                .reference_floor
                .as_ref()
                .unwrap()
                .parse::<u64>()
                .unwrap();
            if floor != reference {
                assert_eq!(
                    floor,
                    row.candidate_floor
                        .as_ref()
                        .unwrap()
                        .parse::<u64>()
                        .unwrap()
                );
                assert!(floor.abs_diff(reference) <= 1, "{} floor", row.id);
                assert!(
                    row.exact_reference_integer_margin
                        .parse::<f64>()
                        .unwrap()
                        .abs()
                        <= 0.004,
                    "{} is not inside the named integer-decision margin: {}",
                    row.id,
                    row.exact_reference_integer_margin
                );
                allowed_demand_boundary += 1;
            }
        } else {
            assert!(
                matches!(
                    actual,
                    Err(EvaluatorError::OutsideDecisionDomain | EvaluatorError::NonFinite)
                ),
                "{} was not rejected",
                row.id
            );
        }
    }

    for row in &table.wire_rows {
        let counter = SafeU64::new(row.counter.parse::<u64>().unwrap()).unwrap();
        assert_eq!(
            libm::sin(counter.get() as f64).to_bits(),
            bits(&row.sin_output_hex),
            "sine counter {}",
            row.counter
        );
    }

    for (index, row) in table.quote_rows.iter().enumerate() {
        let base = Amount::parse(&row.base).unwrap();
        let counter = SafeU64::new(row.counter.parse::<u64>().unwrap()).unwrap();
        let input = base.to_canonical_string().parse::<f64>().unwrap();
        let composite = input + 6.0 * libm::sin(counter.get() as f64);
        assert_eq!(
            composite.to_bits(),
            bits(&row.candidate_composite_hex),
            "quote {index}"
        );
        let actual = wire_quote(&base, counter);
        if composite > 0.0 && composite < 1_125_899_906_842_624.0 {
            let actual = actual.unwrap_or_else(|error| panic!("quote {index}: {error}"));
            assert_eq!(i128::from(actual), row.candidate_ceil, "quote {index}");
            if actual as i128 != row.reference_ceil {
                assert!((actual as i128 - row.reference_ceil).abs() <= 1);
                assert!(
                    row.exact_reference_integer_margin
                        .parse::<f64>()
                        .unwrap()
                        .abs()
                        <= 0.25,
                    "quote {index} exceeded the documented boundary"
                );
                allowed_quote_boundary += 1;
            }
        } else {
            assert!(actual.is_err(), "unsafe quote {index} was accepted");
        }
    }

    assert_eq!(in_domain, 93);
    assert_eq!(allowed_demand_boundary, 8);
    assert_eq!(allowed_quote_boundary, 10);
    eprintln!(
        "locked evaluator native trace: {in_domain} decision-domain demand rows, {allowed_demand_boundary} demand boundary rows, {allowed_quote_boundary} quote boundary rows; all other ordinary integer rows exact"
    );
}
