use num_bigint::BigInt;
use paperclip_game::game::evaluator::{
    ExactRatio, creativity_speed_ratio, creativity_speed_ratio_stages, processor_domain_upper,
    processor_speed_to_amount,
};
use serde::Deserialize;
use sha2::{Digest, Sha256};

const REFERENCE_SHA256: &str = "d969e73bbf934df2a02bf31e84ee950ab0d921599fa70c8959ed5be2c53cd25b";
const REFERENCE_BYTES: &[u8] = include_bytes!("data/m2-c01-evaluator/references.json");
const GENERATOR_BYTES: &[u8] = include_bytes!("generate_m2_c01_references.py");
const EVALUATOR_BYTES: &[u8] = include_bytes!("../src/game/evaluator.rs");
const REQUEST_BYTES: &[u8] = include_bytes!("data/m2-c01-evaluator/sweep.requests");
const NATIVE_BYTES: &[u8] = include_bytes!("data/m2-c01-evaluator/sweep.native");
const GENERATION_BYTES: &[u8] = include_bytes!("data/m2-c01-evaluator/generation.json");

#[derive(Deserialize)]
struct Table {
    schema_version: String,
    exponent_numerator: u8,
    exponent_denominator: u8,
    domain_upper_exact: String,
    relative_error_budget: String,
    stages: Vec<Stage>,
    conversions: Vec<Conversion>,
    amount: Vec<AmountCase>,
    provenance: Provenance,
}

#[derive(Deserialize)]
struct Provenance {
    generator_sha256: String,
    evaluator_sha256: String,
    requests_sha256: String,
    native_sweep_sha256: String,
    method: String,
}

#[derive(Deserialize)]
struct Stage {
    id: String,
    kind: String,
    input_numerator: String,
    input_denominator: String,
    expected_error: Option<String>,
    input_float_bits: Option<String>,
    expected_stage_bits: Option<StageBits>,
    expected_amount: Option<String>,
    adjacent_integer_relation: Option<String>,
    reference_floor_grid_integer: Option<serde_json::Value>,
    reference_ceil_grid_integer: Option<serde_json::Value>,
    quantization_only_after_final_composite: Option<bool>,
    candidate_relative_budget: Option<String>,
}

#[derive(Deserialize)]
struct StageBits {
    input: String,
    log10: String,
    power: String,
    composite: String,
}

#[derive(Deserialize)]
struct Conversion {
    id: String,
    input_numerator: String,
    input_denominator: String,
    expected_error: Option<String>,
    expected_input_bits: Option<String>,
}

#[derive(Deserialize)]
struct AmountCase {
    id: String,
    input_bits: String,
    expected_error: Option<String>,
    expected_amount: Option<String>,
}

fn bigint(text: &str) -> BigInt {
    BigInt::parse_bytes(text.as_bytes(), 10).expect("reference BigInt")
}

fn bits(text: &str) -> u64 {
    u64::from_str_radix(text, 16).expect("reference f64 bits")
}

fn hexdigest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn assert_error<T: std::fmt::Debug>(actual: Result<T, impl std::fmt::Debug>, expected: &str) {
    assert_eq!(format!("{:?}", actual.unwrap_err()), expected);
}

#[test]
fn generated_native_and_high_precision_processor_references_replay_on_every_host() {
    assert_eq!(
        hexdigest(REFERENCE_BYTES),
        REFERENCE_SHA256,
        "update the locked SHA only after a real independent regeneration"
    );
    let table: Table = serde_json::from_slice(REFERENCE_BYTES).unwrap();
    let generation: serde_json::Value = serde_json::from_slice(GENERATION_BYTES).unwrap();
    assert_eq!(table.schema_version, "m2-c01-processor-references-v1");
    assert_eq!(
        (table.exponent_numerator, table.exponent_denominator),
        (11, 10),
        "never confuse the Processor exponent with G02 23/20"
    );
    assert_eq!(
        table.domain_upper_exact,
        processor_domain_upper().to_string()
    );
    assert_eq!(
        table.relative_error_budget,
        "3.552713678800500929355621338E-15"
    );
    assert_eq!(
        table.provenance.generator_sha256,
        hexdigest(GENERATOR_BYTES)
    );
    assert_eq!(
        table.provenance.evaluator_sha256,
        hexdigest(EVALUATOR_BYTES)
    );
    assert_eq!(table.provenance.requests_sha256, hexdigest(REQUEST_BYTES));
    assert_eq!(
        table.provenance.native_sweep_sha256,
        hexdigest(NATIVE_BYTES)
    );
    assert_eq!(generation["references_sha256"], REFERENCE_SHA256);
    assert!(
        table
            .provenance
            .method
            .contains("actual native production stages")
    );
    assert!(table.provenance.method.contains("independent ln*11/10"));

    let native_text = std::str::from_utf8(NATIVE_BYTES).unwrap();
    assert!(
        native_text
            .lines()
            .all(|line| line.starts_with("NATIVE_C01 "))
    );
    assert_eq!(
        native_text.lines().count(),
        REQUEST_BYTES.iter().filter(|byte| **byte == b'\n').count()
    );
    let request_operations: Vec<String> = native_text
        .lines()
        .map(|line| {
            let mut fields = line.split_whitespace();
            let prefix = fields.by_ref().take(2).collect::<Vec<_>>().join(" ");
            let field_count = if prefix == "NATIVE_C01 amount" { 1 } else { 2 };
            let suffix = fields.take(field_count).collect::<Vec<_>>().join(" ");
            format!("{prefix} {suffix}")
        })
        .collect();
    for (index, request) in std::str::from_utf8(REQUEST_BYTES)
        .unwrap()
        .lines()
        .enumerate()
    {
        let request: serde_json::Value = serde_json::from_str(request).unwrap();
        let op = request["op"].as_str().unwrap();
        let expected = if op == "amount" {
            format!("NATIVE_C01 amount {}", request["bits"].as_str().unwrap())
        } else {
            format!(
                "NATIVE_C01 {op} {} {}",
                request["numerator"].as_str().unwrap(),
                request["denominator"].as_str().unwrap()
            )
        };
        assert_eq!(
            request_operations[index], expected,
            "native request order is immutable"
        );
    }

    let mut valid = 0;
    let mut indeterminate = 0;
    let mut seeded_classes = std::collections::BTreeSet::new();
    let mut saw_upper = false;
    let mut saw_upper_rejection = false;
    let mut saw_p2 = false;
    let mut saw_ties = false;
    for row in &table.stages {
        let input = ExactRatio::new(bigint(&row.input_numerator), bigint(&row.input_denominator));
        if let Some(expected) = &row.expected_error {
            let observed = input.and_then(|input| creativity_speed_ratio_stages(&input));
            assert_error(observed, expected);
            if row.id == "domain-above-1" {
                saw_upper_rejection = expected == "OutsideProcessorDomain";
            }
            continue;
        }
        valid += 1;
        let input = input.unwrap();
        let stages = creativity_speed_ratio_stages(&input)
            .unwrap_or_else(|error| panic!("{}: {error:?}", row.id));
        let repeat = creativity_speed_ratio_stages(&input).unwrap();
        let expected = row.expected_stage_bits.as_ref().unwrap();
        assert_eq!(
            stages.binary_input.to_bits(),
            bits(&expected.input),
            "{}",
            row.id
        );
        assert_eq!(stages.log10.to_bits(), bits(&expected.log10), "{}", row.id);
        assert_eq!(stages.power.to_bits(), bits(&expected.power), "{}", row.id);
        assert_eq!(
            stages.composite.to_bits(),
            bits(&expected.composite),
            "{}",
            row.id
        );
        assert_eq!(repeat.binary_input.to_bits(), stages.binary_input.to_bits());
        assert_eq!(repeat.log10.to_bits(), stages.log10.to_bits());
        assert_eq!(repeat.power.to_bits(), stages.power.to_bits());
        assert_eq!(repeat.composite.to_bits(), stages.composite.to_bits());
        assert_eq!(
            stages.binary_input.to_bits(),
            bits(row.input_float_bits.as_ref().unwrap())
        );
        let amount = processor_speed_to_amount(stages.composite).unwrap();
        assert_eq!(
            amount.to_string(),
            row.expected_amount.as_ref().unwrap().as_str(),
            "{}",
            row.id
        );
        assert_eq!(
            amount,
            creativity_speed_ratio(&input).unwrap(),
            "{}",
            row.id
        );
        assert_eq!(
            processor_speed_to_amount(repeat.composite),
            Ok(amount.clone())
        );
        assert_eq!(row.quantization_only_after_final_composite, Some(true));
        assert_eq!(
            row.candidate_relative_budget.as_deref(),
            Some(table.relative_error_budget.as_str())
        );
        if row.adjacent_integer_relation.as_deref() == Some("indeterminate") {
            indeterminate += 1;
            assert!(row.reference_floor_grid_integer.is_some());
            assert!(row.reference_ceil_grid_integer.is_some());
        }
        if row.kind == "seeded-mantissa-exponent-remainder" {
            seeded_classes.insert(row.id.rsplit("-e").next().unwrap().to_string());
        }
        if row.id == "domain-on" {
            saw_upper = true;
            assert!(stages.composite.is_finite());
        }
        if row.id == "small-2" {
            saw_p2 = true;
            // Exact input gives .886 ... grid units; the truncated binary native
            // Amount is .793 .... These are different stages, not hidden rounding.
            assert_eq!(amount.to_string(), "1.645271921560140793");
            let reference = row
                .reference_floor_grid_integer
                .as_ref()
                .unwrap()
                .as_str()
                .unwrap()
                .parse::<u64>()
                .unwrap();
            assert_eq!(reference, 1_645_271_921_560_140_886);
            assert_eq!(
                row.adjacent_integer_relation.as_deref(),
                Some("indeterminate")
            );
        }
        if row.kind == "binary53-tie" {
            saw_ties = true;
        }
    }
    assert_eq!(valid, 384);
    assert!(saw_upper && saw_upper_rejection && saw_p2 && saw_ties);
    assert_eq!(
        seeded_classes.len(),
        10,
        "every denominator-10 exponent remainder class"
    );
    assert_eq!(
        indeterminate, valid,
        "the conservative continuous bound and fine grid do not fabricate integer decisions"
    );

    for row in &table.conversions {
        let input = ExactRatio::new(bigint(&row.input_numerator), bigint(&row.input_denominator));
        if let Some(expected) = &row.expected_error {
            let actual = input.and_then(|input| input.to_f64()).map(drop);
            assert_error(actual, expected);
        } else {
            let value = input.unwrap().to_f64().unwrap();
            assert_eq!(
                value.to_bits(),
                bits(row.expected_input_bits.as_ref().unwrap()),
                "{}",
                row.id
            );
        }
    }

    for row in &table.amount {
        let continuous = f64::from_bits(bits(&row.input_bits));
        let actual = processor_speed_to_amount(continuous);
        if let Some(expected) = &row.expected_error {
            assert_error(actual, expected);
        } else {
            let actual = actual.unwrap();
            assert_eq!(
                actual.to_string(),
                row.expected_amount.as_deref().unwrap(),
                "{}",
                row.id
            );
            assert_eq!(processor_speed_to_amount(continuous), Ok(actual));
        }
    }
    assert_eq!(
        table.amount.len(),
        30,
        "below/on/above real and decimal grid boundaries"
    );
}
