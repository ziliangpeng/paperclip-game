#!/usr/bin/env python3
"""Independent high-precision Issue 15 demand/sine table generation and analysis."""
from __future__ import annotations
from decimal import Decimal, getcontext, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import struct
import sys

getcontext().prec = 100
D = Decimal
ONE = D(1)
EXPONENT = D("1.15")
COEFFICIENT = D("0.7")
REL_BUDGET = D(2) ** D(-48)
SINE_BUDGET = D(2) ** D(-48)
DECISION_LIMIT = D(2) ** D(50)


def arctan_reciprocal(integer: int) -> Decimal:
    x = D(1) / D(integer)
    x2 = x * x
    term = x
    total = term
    n = 0
    while True:
        n += 1
        term *= -x2
        addition = term / D(2 * n + 1)
        total += addition
        if abs(addition) < D("1e-98"):
            return total


def compute_pi() -> Decimal:
    return 16 * arctan_reciprocal(5) - 4 * arctan_reciprocal(239)


PI = compute_pi()
HALF_PI = PI / 2


def sin_cos_reduced(value: Decimal) -> tuple[Decimal, Decimal]:
    half_turns = int((value / HALF_PI + D("0.5")).to_integral_value(rounding=ROUND_FLOOR))
    y = value - D(half_turns) * HALF_PI
    assert abs(y) <= HALF_PI / 2 + D("1e-95")
    y2 = y * y
    sin_term = y
    cos_term = ONE
    sin_value = sin_term
    cos_value = cos_term
    for n in range(1, 45):
        sin_term *= -y2 / D((2 * n) * (2 * n + 1))
        cos_term *= -y2 / D((2 * n - 1) * (2 * n))
        sin_value += sin_term
        cos_value += cos_term
    quadrant = half_turns % 4
    if quadrant == 0:
        return sin_value, cos_value
    if quadrant == 1:
        return cos_value, -sin_value
    if quadrant == 2:
        return -sin_value, -cos_value
    return -cos_value, sin_value


def sine(value: Decimal) -> Decimal:
    return sin_cos_reduced(value)[0]


def power(value: Decimal) -> Decimal:
    primary = value ** EXPONENT
    # Decimal's own ln/exp composition independently reaches the same interval.
    alternate = (value.ln() * EXPONENT).exp()
    assert abs(primary - alternate) <= D("1e-92") * max(ONE, abs(primary))
    return primary


def dec(value: Decimal, digits: str = ".70g") -> str:
    return format(value, digits)


def bits(value: float) -> str:
    return f"{struct.unpack('>Q', struct.pack('>d', value))[0]:016x}"


def from_bits(text: str) -> float:
    return struct.unpack(">d", struct.pack(">Q", int(text, 16)))[0]


def exact_float(value: float) -> Decimal:
    return D.from_float(value)


def demand_inputs() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    fixed = [
        "0", "0.000000000000000001", "0.01", "0.25", "0.7", "0.999999999999999999",
        "1", "1.000000000000000001", "1.0000000000000002", "1.000000000000001", "1.01",
        "1.363", "2", "3.2", "10", "13.333333333333333333", "16", "26.666666666666666667",
        "80", "100", "1000", "1000000", "1000000000000", "1000000000000000000",
        "1e50", "1e100", "1e200", "1e250", "1e260", "1e262", "1e264", "1e266", "1e267",
        "1e268", "1e269", "1e300",
    ]
    rows.extend((f"fixed-{index:02d}", value) for index, value in enumerate(fixed))
    for index, margin in enumerate(["0.01", "0.05", "0.06", "0.07", "0.08", "0.25", "1", "6.21"]):
        price = D(margin)
        for level in [1, 2, 3, 10, 30]:
            demand = D("0.8") / price * (D("1.1") ** (level - 1))
            rows.append((f"rational-margin-{margin}-level-{level}", dec(demand)))
    for index, integer in enumerate([1, 2, 3, 4, 5, 7, 10, 19, 20, 46, 100, 1000, 1000000]):
        target = D(integer)
        demand = (target / COEFFICIENT) ** (ONE / EXPONENT)
        rows.append((f"integer-boundary-{integer}", dec(demand)))
    for zoom in range(-8, 9):
        factor = ONE + D(zoom) * (D(2) ** D(-48))
        demand = (D(46) / COEFFICIENT) ** (ONE / EXPONENT) * factor
        rows.append((f"near-46-zoom-{zoom:+d}", dec(demand)))
    decision_demand = (DECISION_LIMIT / COEFFICIENT) ** (ONE / EXPONENT)
    rows.append(("decision-limit", dec(decision_demand)))
    for zoom in [-4, -3, -2, -1, 1, 2, 3, 4]:
        factor = ONE + D(zoom) * (D(2) ** D(-48))
        rows.append((f"decision-limit-zoom-{zoom:+d}", dec(decision_demand * factor)))
    seed = 0x6A09E667F3BCC909
    for index in range(160):
        seed = (seed * 6364136223846793005 + 1442695040888963407) % (1 << 128)
        mantissa = seed % 9_000_000_000_000_000 + 1_000_000_000_000_000
        exponent = (seed >> 84) % 272 - 6
        value = D(mantissa).scaleb(exponent - 15)
        rows.append((f"seeded-{index:03d}", dec(value)))
    return rows


def sine_counters() -> list[str]:
    counters = list(range(0, 257))
    counters += [10**k + delta for k in range(1, 16) for delta in [-2, -1, 0, 1, 2]]
    counters += [2**k + delta for k in [16, 24, 32, 40, 48, 52, 53] for delta in [-1, 0, 1] if 0 <= 2**k + delta < 2**53]
    for multiple in list(range(1, 129)) + [1000, 10000, 100000, 1000000, 10**9, 10**12]:
        nearest = int((D(multiple) * HALF_PI).to_integral_value(rounding=ROUND_HALF_EVEN))
        counters.extend(max(0, nearest + delta) for delta in [-2, -1, 0, 1, 2])
    seed = 0xBB67AE8584CAA73B
    for _ in range(220):
        seed = (seed * 2862933555777941757 + 3037000493) % (1 << 128)
        counters.append(seed % (2**53))
    return sorted({str(value) for value in counters if 0 <= value < 2**53}, key=int)


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in {"requests", "finish"}:
        raise SystemExit("usage: generate_references.py requests|finish DIRECTORY SWEEP_OUTPUT")
    mode, directory_text, sweep_name = sys.argv[1:]
    directory = Path(directory_text)
    directory.mkdir(parents=True, exist_ok=True)
    demand = demand_inputs()
    counters = sine_counters()
    if mode == "requests":
        # Internal cross-checks of the independent algorithms themselves.
        assert abs(PI - D("3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798")) < D("1e-96")
        assert sine(D(0)) == 0
        assert abs(sine(HALF_PI) - 1) < D("1e-95")
        assert power(D(1)) == 1
        request_lines: list[str] = []
        for _label, text in demand:
            value = float(text)
            if value > 1:
                request_lines.append(f"pow {bits(value)}")
                request_lines.append(f"powr {bits(value)}")
        for text in counters:
            request_lines.append(f"sin {bits(float(int(text)))}")
        (directory / "sweep.requests").write_text("\n".join(request_lines) + "\n")
        summary = {"demand_input_rows": len(demand), "sine_input_rows": len(counters), "requests": len(request_lines), "pi": dec(PI)}
        (directory / "generation.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
        return

    output_path = Path(sweep_name)
    outputs: dict[tuple[str, str], str] = {}
    for line in output_path.read_text().splitlines():
        operation, input_hex, output_hex = line.split()
        key = (operation, input_hex)
        # Distinct exact decimal rows may share one correctly rounded binary64 input.
        # Repeated native observations must still be bit-identical.
        if key in outputs:
            assert outputs[key] == output_hex
        outputs[key] = output_hex

    demand_rows = []
    maximum_relative = D(0)
    maximum_relative_id = None
    maximum_power_ulp = 0.0
    rounding_differences = []
    for label, text in demand:
        exact_input = D(text)
        input_float = float(text)
        if input_float <= 1:
            # Production's exact special branch needs no evaluator.
            continue
        input_hex = bits(input_float)
        direct_pow_hex = outputs[("pow", input_hex)]
        pow_hex = outputs[("powr", input_hex)]
        pow_float = from_bits(pow_hex)
        composite_float = 0.7 * pow_float
        float_input_decimal = exact_float(input_float)
        reference_pow_float_input = power(float_input_decimal)
        reference_pow_exact_input = power(exact_input)
        reference_composite_float_input = COEFFICIENT * reference_pow_float_input
        reference_composite_exact_input = COEFFICIENT * reference_pow_exact_input
        actual_composite_decimal = exact_float(composite_float)
        absolute_error = abs(actual_composite_decimal - reference_composite_float_input) if math.isfinite(composite_float) else None
        relative_error = absolute_error / abs(reference_composite_float_input) if absolute_error is not None and reference_composite_float_input != 0 else None
        conversion_error = abs(actual_composite_decimal - reference_composite_exact_input) if math.isfinite(composite_float) else None
        reference_floor = int(reference_composite_exact_input.to_integral_value(rounding=ROUND_FLOOR))
        candidate_floor = math.floor(composite_float) if math.isfinite(composite_float) else None
        nearest_integer = reference_composite_exact_input.to_integral_value(rounding=ROUND_HALF_EVEN)
        integer_margin = abs(reference_composite_exact_input - nearest_integer)
        if relative_error is not None and relative_error > maximum_relative:
            maximum_relative = relative_error
            maximum_relative_id = label
        if math.isfinite(pow_float):
            maximum_power_ulp = max(maximum_power_ulp, abs(pow_float - float(reference_pow_float_input)) / math.ulp(pow_float))
        row = {
            "id": label,
            "exact_input_decimal": text,
            "input_hex": input_hex,
            "direct_pow_output_hex": direct_pow_hex,
            "pow_output_hex": pow_hex,
            "composite_output_hex": bits(composite_float),
            "reference_pow_at_binary_input": dec(reference_pow_float_input),
            "reference_composite_at_binary_input": dec(reference_composite_float_input),
            "reference_composite_at_exact_input": dec(reference_composite_exact_input),
            "absolute_error": dec(absolute_error) if absolute_error is not None else None,
            "relative_error": dec(relative_error) if relative_error is not None else None,
            "total_error_against_exact_input": dec(conversion_error) if conversion_error is not None else None,
            "within_2^-48_relative_budget": relative_error is not None and relative_error <= REL_BUDGET,
            "reference_floor": None if reference_floor is None else str(reference_floor),
            "candidate_floor": None if candidate_floor is None else str(candidate_floor),
            "decision_domain": candidate_floor is not None and reference_composite_float_input < DECISION_LIMIT,
            "exact_reference_integer_margin": dec(integer_margin),
        }
        demand_rows.append(row)
        if candidate_floor != reference_floor and row["decision_domain"]:
            rounding_differences.append(row["id"])

    wire_rows = []
    maximum_sine_error = D(0)
    maximum_sine_id = None
    sine_by_counter: dict[str, tuple[float, Decimal]] = {}
    for text in counters:
        counter = int(text)
        input_float = float(counter)
        input_hex = bits(input_float)
        sin_hex = outputs[("sin", input_hex)]
        sin_float = from_bits(sin_hex)
        reference_sin = sine(D(counter))
        actual_sin = exact_float(sin_float)
        error = abs(actual_sin - reference_sin)
        if error > maximum_sine_error:
            maximum_sine_error = error
            maximum_sine_id = text
        ref_composite = 6 * reference_sin
        nearest = ref_composite.to_integral_value(rounding=ROUND_HALF_EVEN)
        row = {
            "counter": text,
            "input_hex": input_hex,
            "sin_output_hex": sin_hex,
            "reference_sin": dec(reference_sin),
            "absolute_error": dec(error),
            "within_2^-48_absolute_budget": error <= SINE_BUDGET,
            "six_sine_integer_margin": dec(abs(ref_composite - nearest)),
        }
        wire_rows.append(row)
        sine_by_counter[text] = (sin_float, reference_sin)

    quote_rows = []
    quote_differences = []
    bases = ["20", "19.98", "20.05", "15", "14.999999999999999999", "15.000000000000000001", "0.000000000000000001", "123456.789", "562949953421311.9", "562949953421312.1", "900719925474099.1"]
    quote_counters = [str(value) for value in list(range(0, 33)) + [100, 1000, 1000000, 2**32, 2**48, 2**53 - 1]]
    for counter in quote_counters:
        sin_float, reference_sin = sine_by_counter[counter]
        for base in bases:
            exact_base = D(base)
            base_float = float(base)
            reference_quote_exact = exact_base + 6 * reference_sin
            reference_quote_binary_base = exact_float(base_float) + 6 * reference_sin
            candidate_composite = base_float + 6.0 * sin_float
            reference_ceil = int(reference_quote_exact.to_integral_value(rounding=ROUND_CEILING))
            candidate_ceil = math.ceil(candidate_composite)
            nearest = reference_quote_exact.to_integral_value(rounding=ROUND_HALF_EVEN)
            row = {
                "counter": counter,
                "base": base,
                "base_hex": bits(base_float),
                "candidate_composite_hex": bits(candidate_composite),
                "reference_quote_at_exact_input": dec(reference_quote_exact),
                "reference_quote_at_binary_base": dec(reference_quote_binary_base),
                "reference_ceil": reference_ceil,
                "candidate_ceil": candidate_ceil,
                "exact_reference_integer_margin": dec(abs(reference_quote_exact - nearest)),
            }
            quote_rows.append(row)
            if candidate_ceil != reference_ceil:
                quote_differences.append({"counter": counter, "base": base})

    summary = {
        "schema_version": 1,
        "reference_precision_decimal_digits": 100,
        "pi_from_machin_formula": dec(PI),
        "evaluator": {
            "crate": "libm", "version": "0.2.16", "default_features": False,
            "features": ["force-soft-floats"],
            "pow_api": "m*2^k reduction with libm::pow(m, 1.15) * libm::pow(2, r) and libm::scalbn", "sine_api": "libm::sin(counter_as_f64)",
        },
        "budgets": {"nonzero_composite_relative": "2^-48", "sine_absolute": "2^-48"},
        "native_sweep_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "demand_rows": demand_rows,
        "wire_rows": wire_rows,
        "quote_rows": quote_rows,
        "summary": {
            "demand_rows": len(demand_rows),
            "wire_rows": len(wire_rows),
            "quote_rows": len(quote_rows),
            "maximum_relative_error": dec(maximum_relative),
            "maximum_relative_error_row": maximum_relative_id,
            "maximum_relative_ulp_estimate": maximum_power_ulp,
            "all_finite_demand_rows_within_relative_budget": all(row["within_2^-48_relative_budget"] for row in demand_rows if row["relative_error"] is not None),
            "maximum_total_relative_error_including_input_conversion": dec(max((D(row["total_error_against_exact_input"]) / abs(D(row["reference_composite_at_exact_input"])) for row in demand_rows if row["total_error_against_exact_input"] is not None), default=D(0))),
            "outside_decision_domain_rows": sum(not row["decision_domain"] for row in demand_rows),
            "demand_rounding_differences": rounding_differences,
            "maximum_sine_absolute_error": dec(maximum_sine_error),
            "maximum_sine_error_counter": maximum_sine_id,
            "all_wire_rows_within_absolute_budget": all(row["within_2^-48_absolute_budget"] for row in wire_rows),
            "quote_rounding_differences": quote_differences,
        },
    }
    (directory / "references.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["summary"], indent=2))


if __name__ == "__main__":
    main()
