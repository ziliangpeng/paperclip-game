#!/usr/bin/env python3
# owner: issue-43-A; trigger: requests/finish; purpose: independent exponent-1.1 native/reference replay.
"""Two-phase PCG-026 sweep requests and independently derived reference tables.

`requests DIRECTORY` emits deterministic requests only. A real build must run
`m2_c01_evaluator::native_processor_reference_sweep` against those requests.
`finish DIRECTORY SWEEP_OUTPUT PLATFORM` parses that actual output (or its
NATIVE_C01 lines), recomputes the curve with Decimal, and refuses any mismatch.
"""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, getcontext, localcontext
from fractions import Fraction
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct

SCHEMA = "m2-c01-processor-references-v1"
EXPONENT = Decimal(11) / Decimal(10)
PRECISION = 160
RELATIVE_BUDGET = Decimal(2) ** Decimal(-48)
GRID = Decimal(10) ** -18
UPPER = 1 << 923
HEX64 = lambda x: f"{x:016x}"


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_sha(path):
    return digest_bytes(Path(path).read_bytes())


def write_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        before = path.read_bytes()
        path.write_bytes(payload)
        assert path.read_bytes() == payload
        return digest_bytes(before), digest_bytes(payload)
    path.write_bytes(payload)
    assert path.read_bytes() == payload
    return None, digest_bytes(payload)


def float_bits(value):
    return HEX64(struct.unpack(">Q", struct.pack(">d", value))[0])


def from_bits(bits):
    return struct.unpack(">d", struct.pack(">Q", int(bits, 16)))[0]


def decimal_float(bits):
    return Decimal.from_float(from_bits(bits))


def scaled_to_amount(value):
    negative = value < 0
    magnitude = abs(int(value))
    text = str(magnitude).rjust(19, "0")
    result = ("-" if negative else "") + text[:-18] + "." + text[-18:]
    return result.rstrip("0").rstrip(".") if "." in result else result


def parse_amount(text):
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("-")
    whole, dot, fractional = text.partition(".")
    return sign * int(whole + (fractional or "").ljust(18, "0")[:18])


def trunc_grid(value):
    # Decimal multiplication honors context precision; the Amount contract
    # instead converts the exact binary dyadic ratio once. Do integer math here.
    numerator, denominator = value.as_integer_ratio()
    magnitude = (abs(numerator) * 10 ** 18) // denominator
    return magnitude if numerator >= 0 else -magnitude


def curve(value):
    """Reference index 11/10 only; never substitutes G02's 23/20 exponent."""
    if value == 1:
        return Decimal(0), Decimal(1), Decimal(0)
    logarithm = value.log10()
    power = value ** EXPONENT
    alternate = (value.ln() * EXPONENT).exp()
    assert abs(power - alternate) <= Decimal("1e-140") * power, (value, power, alternate)
    return logarithm, power, logarithm * power + value - 1


def error_metrics(exact, bits):
    if exact == 0:
        return str(Decimal(0)) if bits == HEX64(0) else None
    error = abs((decimal_float(bits) - exact) / exact)
    return format(error, "E")


def requests(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    tests = []
    ids = set()

    def stage(identifier, numerator, denominator=1, kind="seeded"):
        assert identifier not in ids, identifier
        ids.add(identifier)
        entries.append({"op": "stages", "numerator": str(numerator), "denominator": str(denominator)})
        tests.append({"id": identifier, "kind": kind, "index": len(entries) - 1,
                      "input_numerator": str(numerator), "input_denominator": str(denominator)})

    for n in range(1, 65):
        stage(f"small-{n}", n)
    for exponent in [2, 3, 5, 10, 20, 50, 100, 150, 200, 250, 277, 278]:
        stage(f"decimal-power-{exponent}", 10 ** exponent)
    for exponent in [1, 2, 3, 4, 5, 9, 10, 19, 20, 31, 32, 51, 52, 53, 54,
                     63, 64, 99, 100, 127, 128, 199, 200, 255, 256, 399, 400,
                     511, 512, 767, 768, 900, 901, 910, 911, 912, 913, 914,
                     915, 916, 917, 918, 919, 920, 921, 922, 923]:
        stage(f"binary-power-{exponent}", 1 << exponent)
    for offset in [-2, -1, 0, 1, 2, 3, 4, 5, 6, 7]:
        stage(f"binary53-{offset:+d}", (1 << 53) + offset, kind="binary53-tie")
    for offset in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
        stage(f"binary54-{offset}", (1 << 54) + offset, kind="binary53-tie")
    for numerator, denominator in [(0, 1), (-1, 1), (1, 2), (3, 2), (2, 0), (2, -1)]:
        stage(f"invalid-{numerator}-{denominator}", numerator, denominator, kind="nonpositive-nonintegral")
    for offset, label in [(-2, "below-2"), (-1, "below-1"), (0, "on"), (1, "above-1")]:
        stage(f"domain-{label}", UPPER + offset, kind="domain-boundary")

    # Decimal mantissa plus power-of-two exponent is independent of host floats.
    state = 0xC01A11
    eligible = [e for e in range(0, 872) if e % 10 in range(10)]
    for index in range(240):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        mantissa = 10 ** 15 + state * 2_097_153 + index
        mantissa += mantissa % 10
        exponent = eligible[(index * 37 + 11) % len(eligible)]
        numerator = mantissa << exponent
        stage(f"seeded-{index:03d}-e{exponent % 10}", numerator,
              kind="seeded-mantissa-exponent-remainder")

    def direct(identifier, numerator, denominator=1, kind="conversion"):
        entries.append({"op": "convert", "numerator": str(numerator), "denominator": str(denominator)})
        tests.append({"id": identifier, "kind": kind, "index": len(entries) - 1,
                      "input_numerator": str(numerator), "input_denominator": str(denominator)})

    for exponent in [307, 308, 309, 400, 1000]:
        direct(f"conversion-10e{exponent}", 10 ** exponent)
    for numerator, denominator in [(1, 2), (3, 2), (-1, 4), (7, 3), (2, 0)]:
        direct(f"conversion-{numerator}-{denominator}", numerator, denominator,
               kind="conversion-nonintegral-nonfinite")

    def amount(identifier, bits, kind="grid"):
        entries.append({"op": "amount", "bits": HEX64(bits)})
        tests.append({"id": identifier, "kind": kind, "index": len(entries) - 1, "input_bits": HEX64(bits)})

    for identifier, value in [("zero", 0.0), ("min-subnormal", 5e-324), ("one", 1.0),
                                ("one-tenth", 0.1), ("max", float.fromhex("0x1.fffffffffffffp+1023"))]:
        base_bits = struct.unpack(">Q", struct.pack(">d", value))[0]
        for offset, label in [(-1, "below"), (0, "on"), (1, "above")]:
            if base_bits + offset >= 0:
                amount(f"{identifier}-{label}", base_bits + offset)
    for identifier, value in [("grid-1", GRID), ("grid-2", 2 * GRID),
                                ("grid-17", 17 * GRID), ("grid-big", Decimal("1e100"))]:
        bits = struct.unpack(">Q", struct.pack(">d", float(value)))[0]
        for offset, label in [(-1, "below"), (0, "on"), (1, "above")]:
            amount(f"{identifier}-{label}", bits + offset)
    for identifier, bits in [("positive-infinity", 0x7ff0000000000000),
                              ("negative-infinity", 0xfff0000000000000),
                              ("nan", 0x7ff8000000000000),
                              ("negative", 0xbff0000000000000)]:
        amount(identifier, bits, kind="negative-nonfinite")

    request_bytes = ("".join(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
                            for entry in entries)).encode()
    request_before, request_after = write_bytes(directory / "sweep.requests", request_bytes)
    tests_path = directory / "sweep.index.json"
    write_bytes(tests_path, (json.dumps(tests, indent=2, sort_keys=True) + "\n").encode())
    metadata = {
        "schema_version": SCHEMA, "precision_digits": PRECISION,
        "exponent_numerator": 11, "exponent_denominator": 10,
        "domain": {"lower": 1, "upper_exact": str(UPPER), "upper_expression": "2^923",
                   "meaning": "conservative finite-evaluator test domain"},
        "seed": state, "request_count": len(entries),
        "generator_file": "tests/generate_m2_c01_references.py",
        "generator_sha256": file_sha(Path(__file__).resolve()),
        "evaluator_file": "src/game/evaluator.rs", "evaluator_sha256": file_sha(directory.parent.parent.parent / "src/game/evaluator.rs"),
        "requests_file": "sweep.requests", "requests_sha256": request_after,
        "requests_before_sha256": request_before, "requests_idempotent": request_before == request_after,
        "coverage": {
            "small_integers_1_64": 64, "seeded_samples": 240,
            "binary53_and_ties_even": True, "domain_boundary": True,
            "wide_mantissa_exponent_and_all_denominator10_remainder_classes": True,
            "below_on_above_grid": True, "negative_nonfinite_nonintegral": True,
            "cumulative_exact_to_composite_error_bound": True,
            "explicit_source_indeterminate_floor_or_ceiling_relation": True,
            "native_repeated_bit_amount_identity": True,
        },
    }
    write_bytes(directory / "generation.json", (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
    print(f"REQUESTS {directory} count={len(entries)} sha256={request_after}")


def native_lines(payload):
    result = []
    for raw in payload.decode().splitlines():
        if raw.startswith("NATIVE_C01 "):
            result.append(raw)
    assert result, "no actual native output rows"
    return result


def parse_native(lines):
    parsed = []
    for line in lines:
        fields = line.split()
        assert fields[:2] == ["NATIVE_C01", fields[1]], fields
        op = fields[1]
        if op in ("stages", "convert"):
            assert fields[4] in ("OK", "ERR"), fields
            row = {"op": op, "numerator": fields[2], "denominator": fields[3]}
            if fields[4] == "OK":
                if op == "stages":
                    assert len(fields) == 10, fields
                    row.update({"bits": fields[5:9], "amount": fields[9]})
                else:
                    assert len(fields) == 6, fields
                    row.update({"bits": fields[5]})
            else:
                assert len(fields) == 6, fields
                row.update({"error": fields[5]})
            parsed.append(row)
        elif op == "amount":
            assert fields[3] in ("OK", "ERR"), fields
            row = {"op": op, "bits": fields[2]}
            if fields[3] == "OK":
                assert len(fields) == 5, fields
                row.update({"amount": fields[4]})
            else:
                assert len(fields) == 5, fields
                row.update({"error": fields[4]})
            parsed.append(row)
        else:
            raise AssertionError(fields)
    return parsed


def finish(directory, sweep_output, platform):
    directory = Path(directory).resolve()
    native_bytes = Path(sweep_output).read_bytes()
    lines = native_lines(native_bytes)
    parsed = parse_native(lines)
    tests = json.loads((directory / "sweep.index.json").read_text()
                       if (directory / "sweep.index.json").exists() else
                       (directory / "requests").read_text() if (directory / "requests").exists() else "[]")
    metadata = json.loads((directory / "generation.json").read_text())
    assert len(parsed) == metadata["request_count"], (len(parsed), metadata["request_count"])

    with localcontext() as context:
        context.prec = PRECISION
        stage_rows, conversion_rows, amount_rows = [], [], []
        audit = {"maximum_relative_error": {"exact_input_to_binary_input": Decimal(0),
                 "exact_input_to_log10": Decimal(0), "exact_input_to_power": Decimal(0),
                 "exact_input_to_composite": Decimal(0), "binary_input_to_composite": Decimal(0)},
                 "valid_stage_count": 0, "determinate_count": 0, "indeterminate_count": 0,
                 "combined_error_bound_violations": 0}
        max_ids = {key: None for key in audit["maximum_relative_error"]}

        for test, native in zip(tests, parsed):
            if test is None:
                continue
            if test.get("input_numerator") is not None and native["op"] == "convert":
                numerator, denominator = int(test["input_numerator"]), int(test["input_denominator"])
                if denominator == 0:
                    expected = "InvalidDomain"
                else:
                    exact = Fraction(numerator, denominator)
                    expected = ("InvalidDomain" if exact < 0 else
                                "NonFinite" if abs(exact.numerator) > (1 << 1024) * abs(exact.denominator)
                                else None)
                row = {key: test[key] for key in ["id", "kind", "input_numerator", "input_denominator"]}
                if expected is not None and native.get("error") == expected:
                    row["expected_error"] = expected
                    row["native_error"] = native["error"]
                elif "error" in native:
                    row["native_error"] = native["error"]
                    row["expected_input_bits"] = None
                else:
                    bits = float_bits(float(numerator / denominator)) if denominator else None
                    # Evaluate from exact integers; Fraction->float is correctly rounded on giant ints.
                    bits = float_bits(float(exact))
                    assert native["bits"] == bits, (test, native, bits)
                    row["expected_input_bits"] = bits
                    row["native_input_bits"] = native["bits"]
                conversion_rows.append(row)
                continue

            if native["op"] == "amount":
                bits = test["input_bits"]
                row = {"id": test["id"], "kind": test["kind"], "input_bits": bits}
                numeric = from_bits(bits)
                if not math.isfinite(numeric):
                    assert native.get("error") == "NonFinite", (test, native)
                    row.update({"expected_error": "NonFinite", "native_error": native["error"]})
                elif numeric < 0:
                    assert native.get("error") == "InvalidDomain", (test, native)
                    row.update({"expected_error": "InvalidDomain", "native_error": native["error"]})
                else:
                    continuous = decimal_float(bits)
                    grid = trunc_grid(continuous)
                    expected = scaled_to_amount(grid)
                    assert native.get("amount") == expected, (test, native, expected)
                    row.update({"exact_continuous_decimal": format(continuous, "E"),
                                "rounded_grid_integer": grid, "native_grid_integer": str(parse_amount(native["amount"])),
                                "expected_amount": expected, "native_amount": native["amount"]})
                amount_rows.append(row)
                continue

            assert native["op"] == "stages", (test, native)
            row = {key: test[key] for key in ["id", "kind", "input_numerator", "input_denominator"]}
            numerator, denominator = int(test["input_numerator"]), int(test["input_denominator"])
            if denominator == 0:
                assert native.get("error") == "InvalidDomain", (test, native)
                row.update({"expected_error": "InvalidDomain", "native_error": native["error"]})
                stage_rows.append(row)
                continue
            exact = Fraction(numerator, denominator)
            expected_error = "InvalidDomain" if exact.denominator != 1 or exact < 1 else (
                "OutsideProcessorDomain" if exact > UPPER else None)
            if expected_error is not None:
                assert native.get("error") == expected_error, (test, native, expected_error)
                row.update({"expected_error": expected_error, "native_error": native["error"]})
                stage_rows.append(row)
                continue
            assert "error" not in native, (test, native)
            exact_value = Decimal(exact.numerator)
            input_bits = float_bits(float(exact.numerator))
            assert native["bits"][0] == input_bits, (test, native, input_bits)
            logarithm, power, composite = curve(exact_value)
            binary = decimal_float(input_bits)
            binary_logarithm, binary_power, binary_composite = curve(binary)
            native_values = [decimal_float(bits) for bits in native["bits"]]
            stage_exact = [exact_value, logarithm, power, composite]
            binary_exact = [binary, binary_logarithm, binary_power, binary_composite]
            row.update({
                "input_float_bits": input_bits,
                "reference": {"input": format(exact_value, "E"),
                              "log10": format(logarithm, "E"), "power": format(power, "E"),
                              "composite": format(composite, "E")},
                "binary_input_reference_composite": format(binary_composite, "E"),
                "expected_stage_bits": dict(zip(["input", "log10", "power", "composite"], native["bits"])),
                "native_stage_bits": dict(zip(["input", "log10", "power", "composite"], native["bits"])),
                "native_amount": native["amount"],
                "relative_error": {},
                "native_stage_composite_relative_error": {},
                "candidate_relative_budget": format(RELATIVE_BUDGET, "E"),
            })
            for key, exact_stage, binary_stage, numeric, bits in zip(
                    ["input", "log10", "power", "composite"], stage_exact, binary_exact, native_values, native["bits"]):
                if exact_stage == 0:
                    exact_error = Decimal(0) if bits == HEX64(0) else None
                else:
                    exact_error = abs((numeric - exact_stage) / exact_stage)
                if binary_stage == 0:
                    binary_error = Decimal(0) if bits == HEX64(0) else None
                else:
                    binary_error = abs((numeric - binary_stage) / binary_stage)
                if exact_error is None or binary_error is None:
                    raise AssertionError((test["id"], key, bits, exact_error, binary_error))
                bound = RELATIVE_BUDGET
                assert exact_error <= bound and binary_error <= bound, (test["id"], key, exact_error, binary_error)
                row["relative_error"][key] = format(exact_error, "E")
                row["native_stage_composite_relative_error"][key] = format(binary_error, "E")
                metric = "exact_input_to_binary_input" if key == "input" else (
                    "exact_input_to_composite" if key == "composite" else f"exact_input_to_{key}")
                if exact_error > audit["maximum_relative_error"][metric]:
                    audit["maximum_relative_error"][metric] = exact_error
                    max_ids[metric] = test["id"]
                if key == "composite":
                    if binary_error > audit["maximum_relative_error"]["binary_input_to_composite"]:
                        audit["maximum_relative_error"]["binary_input_to_composite"] = binary_error
                        max_ids["binary_input_to_composite"] = test["id"]
                    actual_grid = trunc_grid(numeric)
                    expected_amount = scaled_to_amount(actual_grid)
                    assert native["amount"] == expected_amount, (test, native, expected_amount)
                    exact_grid_value = composite * 10 ** 18
                    floor = int(exact_grid_value.to_integral_value(rounding=ROUND_FLOOR))
                    ceil = int(exact_grid_value.to_integral_value(rounding=ROUND_CEILING))
                    nearest = min(abs(exact_grid_value - floor), abs(exact_grid_value - ceil))
                    error_bound = abs(binary_composite * 10 ** 18) * RELATIVE_BUDGET
                    relation = "determinate" if nearest > error_bound else "indeterminate"
                    combined_error = abs(composite - Decimal(parse_amount(native["amount"])) * GRID)
                    combined_bound = abs(composite) * RELATIVE_BUDGET + GRID
                    if combined_error > combined_bound:
                        audit["combined_error_bound_violations"] += 1
                    assert combined_error <= combined_bound, (test["id"], combined_error, combined_bound)
                    row.update({
                        "expected_amount": expected_amount, "native_grid_integer": str(parse_amount(native["amount"])),
                        "reference_floor_grid_integer": str(floor), "reference_ceil_grid_integer": str(ceil),
                        "reference_composite_grid_value": format(exact_grid_value, "E"),
                        "nearest_grid_distance": format(nearest, "E"),
                        "continuous_error_bound_grid_units": format(error_bound, "E"),
                        "adjacent_integer_relation": relation, "qualify_safe": nearest > error_bound,
                        "quantization_only_after_final_composite": True,
                        "exact_speed_minus_amount_absolute_error": format(combined_error, "E"),
                        "combined_error_bound": format(combined_bound, "E"),
                    })
                    audit[f"{relation}_count"] += 1
            audit["valid_stage_count"] += 1
            stage_rows.append(row)

        assert audit["valid_stage_count"] > 250
        assert audit["indeterminate_count"] > 0, "P2/near-grid coverage must be exposed, not hidden"
        # This deliberately may be all-indeterminate under the conservative
        # 2^-48 bound and 1e-18 grid; no safe integer decision is fabricated.
        assert any(row["id"] == "domain-on" and "error" not in row for row in stage_rows)
        assert any(row["id"] == "domain-above-1" and row.get("expected_error") == "OutsideProcessorDomain" for row in stage_rows)
        assert any(row["id"] == "small-2" and row.get("adjacent_integer_relation") == "indeterminate" for row in stage_rows)

    provenance = {
        "generator_file": "tests/generate_m2_c01_references.py",
        "generator_sha256": file_sha(Path(__file__).resolve()),
        "evaluator_file": "src/game/evaluator.rs", "evaluator_sha256": file_sha(directory.parent.parent.parent / "src/game/evaluator.rs"),
        "requests_file": "sweep.requests", "requests_sha256": file_sha(directory / "sweep.requests"),
        "native_sweep_file": "sweep.native", "native_sweep_sha256": digest_bytes(("\n".join(lines) + "\n").encode()),
        "native_observation": platform,
        "native_output_sha256": digest_bytes(native_bytes),
        "method": "Decimal log10, direct m^11/10, independent ln*11/10 cross-check; actual native production stages; exact binary64 dyadic grid quantization",
        "precision_work": PRECISION,
        "error_work": "uniform double candidate budget; exact dyadic comparison where applicable",
    }
    references = {
        "schema_version": SCHEMA, "precision_digits": PRECISION,
        "exponent_numerator": 11, "exponent_denominator": 10,
        "relative_error_budget": format(RELATIVE_BUDGET, "E"),
        "domain_upper_exact": str(UPPER), "domain_upper_expression": "2^923",
        "stages": stage_rows, "conversions": conversion_rows, "amount": amount_rows,
        "coverage": metadata["coverage"], "provenance": provenance,
    }
    reference_bytes = (json.dumps(references, indent=2, sort_keys=True) + "\n").encode()
    native_before, native_after = write_bytes(directory / "sweep.native", ("\n".join(lines) + "\n").encode())
    reference_before, reference_after = write_bytes(directory / "references.json", reference_bytes)
    audit_out = {key: format(value, "E") for key, value in audit["maximum_relative_error"].items()}
    generation = dict(metadata)
    generation.update({
        "references_file": "references.json", "references_sha256": reference_after,
        "native_sweep_file": "sweep.native", "native_sweep_sha256": provenance["native_sweep_sha256"],
        "native_observation": platform, "native_output_sha256": provenance["native_output_sha256"],
        "maximum_relative_error": audit_out, "maximum_error_sample_ids": max_ids,
        "valid_stages": audit["valid_stage_count"], "determinate_count": audit["determinate_count"],
        "indeterminate_count": audit["indeterminate_count"],
        "combined_error_bound_violations": audit["combined_error_bound_violations"],
        "requests_idempotent": True, "references_before_sha256": reference_before,
        "references_idempotent": reference_before == reference_after,
    })
    write_bytes(directory / "generation.json", (json.dumps(generation, indent=2, sort_keys=True) + "\n").encode())
    print(f"FINISH valid={audit['valid_stage_count']} refs={reference_after} native={native_after}")
    print(f"MAX_ERRORS {json.dumps(audit_out, sort_keys=True)}")
    print(f"RELATION determinate={audit['determinate_count']} indeterminate={audit['indeterminate_count']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("requests", "finish"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("sweep_output", type=Path, nargs="?")
    parser.add_argument("platform", nargs="?", default="unspecified")
    args = parser.parse_args()
    if args.mode == "requests":
        assert args.sweep_output is None
        requests(args.directory)
    else:
        assert args.sweep_output is not None, "finish requires raw native sweep output"
        finish(args.directory, args.sweep_output, args.platform)


if __name__ == "__main__":
    main()
