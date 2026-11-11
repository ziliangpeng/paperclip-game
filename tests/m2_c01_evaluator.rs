use num_bigint::BigInt;
use paperclip_game::game::amount::{IntegralAmount, NonNegativeAmount};
use paperclip_game::game::evaluator::{
    EvaluatorError, ExactRatio, creativity_speed, creativity_speed_ratio,
    creativity_speed_ratio_stages, processor_domain_upper, processor_speed_to_amount,
};

fn ratio(numerator: BigInt, denominator: u8) -> ExactRatio {
    ExactRatio::new(numerator, BigInt::from(denominator)).unwrap()
}

#[test]
fn exact_domain_special_points_and_outward_rejection_are_explicit() {
    for invalid in [
        ratio(BigInt::from(0u8), 1),
        ratio(BigInt::from(1u8), 2),
        ratio(BigInt::from(3u8), 2),
    ] {
        assert_eq!(
            creativity_speed_ratio(&invalid),
            Err(EvaluatorError::InvalidDomain)
        );
    }
    let one = creativity_speed(&IntegralAmount::from_i128(1)).unwrap();
    assert_eq!(one, NonNegativeAmount::zero());
    let one_stages = creativity_speed_ratio_stages(&ratio(BigInt::from(1u8), 1)).unwrap();
    assert_eq!(one_stages.binary_input.to_bits(), 1.0_f64.to_bits());
    assert_eq!(one_stages.log10.to_bits(), 0);
    assert_eq!(one_stages.power.to_bits(), 1.0_f64.to_bits());
    assert_eq!(one_stages.composite.to_bits(), 0);

    let upper = processor_domain_upper();
    let upper_stages = creativity_speed_ratio_stages(&ratio(upper.clone(), 1)).unwrap();
    assert!(upper_stages.binary_input.is_finite());
    assert!(upper_stages.log10.is_finite());
    assert!(upper_stages.power.is_finite());
    assert!(upper_stages.composite.is_finite());
    assert!(upper_stages.composite > 0.0);
    let upper_speed = creativity_speed_ratio(&ratio(upper.clone(), 1)).unwrap();
    assert!(!upper_speed.amount().is_zero());
    assert_eq!(
        creativity_speed_ratio(&ratio(&upper + BigInt::from(1u8), 1)),
        Err(EvaluatorError::OutsideProcessorDomain)
    );
    eprintln!(
        "Processor domain accepted upper=2^923, composite={:?}, Amount digits={}; upper+1 rejected before conversion",
        upper_stages.composite,
        upper_speed.to_string().len()
    );
}

#[test]
fn exact_p_conversion_covers_binary53_and_ties_to_even() {
    for (exact, expected) in [
        (9_007_199_254_740_993_u128, 9_007_199_254_740_992.0_f64),
        (9_007_199_254_740_995_u128, 9_007_199_254_740_996.0_f64),
    ] {
        let stages = creativity_speed_ratio_stages(&ratio(BigInt::from(exact), 1)).unwrap();
        assert_eq!(stages.binary_input.to_bits(), expected.to_bits(), "{exact}");
    }
}

#[test]
fn final_amount_conversion_is_one_exact_dyadic_toward_zero_step() {
    assert_eq!(
        processor_speed_to_amount(0.0).unwrap(),
        NonNegativeAmount::zero()
    );
    assert_eq!(
        processor_speed_to_amount(5e-324).unwrap(),
        NonNegativeAmount::zero()
    );
    for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        assert_eq!(
            processor_speed_to_amount(invalid),
            Err(EvaluatorError::NonFinite)
        );
    }
    assert_eq!(
        processor_speed_to_amount(-1.0),
        Err(EvaluatorError::InvalidDomain)
    );

    let grid = 1e-18_f64;
    let below = f64::from_bits(grid.to_bits() - 1);
    let above = f64::from_bits(grid.to_bits() + 1);
    assert_eq!(
        processor_speed_to_amount(below).unwrap(),
        NonNegativeAmount::zero()
    );
    assert_eq!(
        processor_speed_to_amount(grid).unwrap().to_string(),
        "0.000000000000000001"
    );
    assert_eq!(
        processor_speed_to_amount(above).unwrap().to_string(),
        "0.000000000000000001"
    );

    let decimal = 0.1_f64;
    let below = f64::from_bits(decimal.to_bits() - 1);
    assert_eq!(
        processor_speed_to_amount(decimal).unwrap().to_string(),
        "0.100000000000000005"
    );
    assert_eq!(
        processor_speed_to_amount(below).unwrap().to_string(),
        "0.099999999999999991"
    );
}

#[test]
fn p2_is_positive_and_repeated_p_is_bit_and_amount_identical() {
    let input = ratio(BigInt::from(2u8), 1);
    let stages = creativity_speed_ratio_stages(&input).unwrap();
    let speed = creativity_speed_ratio(&input).unwrap();
    assert!(stages.composite > 0.0);
    assert!(!speed.amount().is_zero());
    assert!(stages.composite > 1.645271 && stages.composite < 1.645272);
    for _ in 0..1000 {
        let repeated = creativity_speed_ratio_stages(&input).unwrap();
        assert_eq!(
            repeated.binary_input.to_bits(),
            stages.binary_input.to_bits()
        );
        assert_eq!(repeated.log10.to_bits(), stages.log10.to_bits());
        assert_eq!(repeated.power.to_bits(), stages.power.to_bits());
        assert_eq!(repeated.composite.to_bits(), stages.composite.to_bits());
        assert_eq!(creativity_speed_ratio(&input).unwrap(), speed);
    }
    eprintln!(
        "P2 native L={:?} Q={:?} R={:?} Amount={speed}",
        stages.log10, stages.power, stages.composite
    );
}

/// Opt-in host observation: parse generator requests and call only the real
/// production evaluator, so the subsequent Decimal reference run cannot use a
/// private numeric substitute. Output is a path-free canonical NATIVE_C01 table.
#[test]
#[ignore = "large native observation; standard mac/Linux replay is references_replay"]
fn native_processor_reference_sweep() {
    use paperclip_game::game::evaluator::{ProcessorSpeedStages, processor_domain_upper};
    use std::fs;
    use std::path::Path;

    let path = std::env::var_os("C01_SWEEP_REQUESTS")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/data/m2-c01-evaluator/sweep.requests")
        });
    let body = fs::read_to_string(path).expect("read deterministic native requests");
    assert!(processor_domain_upper() > BigInt::from(1u8));
    let print_stages = |stages: ProcessorSpeedStages| {
        let amount = processor_speed_to_amount(stages.composite).expect("finite native Amount");
        for _ in 0..2 {
            let repeated = processor_speed_to_amount(stages.composite).unwrap();
            assert_eq!(
                repeated, amount,
                "Amount conversion is idempotent across repeats"
            );
        }
        print!(
            " OK {:016x} {:016x} {:016x} {:016x} {}",
            stages.binary_input.to_bits(),
            stages.log10.to_bits(),
            stages.power.to_bits(),
            stages.composite.to_bits(),
            amount
        );
    };
    for (index, line) in body.lines().enumerate() {
        let row: serde_json::Value = serde_json::from_str(line).expect("request JSON");
        let operation = row["op"].as_str().unwrap();
        match operation {
            "stages" | "convert" => {
                let numerator =
                    BigInt::parse_bytes(row["numerator"].as_str().unwrap().as_bytes(), 10)
                        .expect("request BigInt numerator");
                let denominator =
                    BigInt::parse_bytes(row["denominator"].as_str().unwrap().as_bytes(), 10)
                        .expect("request BigInt denominator");
                print!("NATIVE_C01 {operation} {numerator} {denominator}");
                let input = ExactRatio::new(numerator, denominator);
                match operation {
                    "stages" => match input.and_then(|input| creativity_speed_ratio_stages(&input))
                    {
                        Ok(stages) => print_stages(stages),
                        Err(error) => print!(" ERR {error:?}"),
                    },
                    "convert" => match input.and_then(|input| input.to_f64()) {
                        Ok(input) => {
                            let bits = input.to_bits();
                            print!(" OK {bits:016x}");
                        }
                        Err(error) => print!(" ERR {error:?}"),
                    },
                    _ => unreachable!(),
                }
            }
            "amount" => {
                let bits = u64::from_str_radix(row["bits"].as_str().unwrap(), 16).unwrap();
                let input = f64::from_bits(bits);
                print!("NATIVE_C01 amount {bits:016x}");
                match processor_speed_to_amount(input) {
                    Ok(amount) => {
                        let previous = amount.clone();
                        for _ in 0..1000 {
                            assert_eq!(processor_speed_to_amount(input), Ok(previous.clone()));
                        }
                        print!(" OK {amount}");
                    }
                    Err(error) => print!(" ERR {error:?}"),
                }
            }
            unknown => panic!("unsupported native operation {unknown} at request {index}"),
        }
        println!();
    }
}
