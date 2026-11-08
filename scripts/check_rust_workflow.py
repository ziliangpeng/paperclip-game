#!/usr/bin/env python3
# owner: paperclip-game maintainers
# trigger: Rust workflow validation and workflow-control changes
# purpose: Check native CI command, action, and bootstrap process contracts.

"""Validate the bounded, known YAML shape of the native Rust workflow.

This is a standard-library structural checker, not a general YAML or shell parser.
It accepts the mapping/literal-block forms used by the project workflow, rejects
unsupported ambiguous Cargo shell forms, and never executes workflow commands.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

MAX_WORKFLOW_BYTES = 256 * 1024
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"
EXPECTED_CARGO = [
    ["cargo", "fmt", "--check"],
    ["cargo", "check", "--locked", "--all-targets"],
    ["cargo", "clippy", "--locked", "--all-targets", "--", "-D", "warnings"],
    ["cargo", "test", "--locked", "--all-targets"],
    ["cargo", "build", "--locked"],
]


@dataclass
class Step:
    job: str
    line: int
    run: str | None = None
    uses: str | None = None
    condition: str | None = None
    continue_on_error: str | None = None
    with_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(value: str) -> str:
    value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_steps(text: str) -> tuple[list[Step], list[Finding]]:
    """Extract steps from jobs.*.steps using only the supported YAML layout."""
    lines = text.splitlines()
    findings: list[Finding] = []
    try:
        jobs_start = next(i for i, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        return [], [Finding("workflow-structure", "missing top-level jobs mapping")]

    jobs_end = next(
        (i for i in range(jobs_start + 1, len(lines))
         if lines[i] and not lines[i].startswith(" ")),
        len(lines),
    )
    job_starts = [
        i for i in range(jobs_start + 1, jobs_end)
        if _indent(lines[i]) == 2 and re.match(r"  [A-Za-z0-9_-]+:\s*$", lines[i])
    ]
    steps: list[Step] = []
    for job_number, job_start in enumerate(job_starts):
        job = lines[job_start].strip()[:-1]
        job_end = job_starts[job_number + 1] if job_number + 1 < len(job_starts) else jobs_end
        step_headers = [
            i for i in range(job_start + 1, job_end)
            if _indent(lines[i]) == 4 and lines[i].strip() == "steps:"
        ]
        if len(step_headers) > 1:
            findings.append(Finding("workflow-structure", f"job {job} has multiple steps mappings"))
            continue
        if not step_headers:
            continue
        steps_start = step_headers[0]
        starts = [
            i for i in range(steps_start + 1, job_end)
            if _indent(lines[i]) == 6 and lines[i].lstrip().startswith("- ")
        ]
        for number, start in enumerate(starts):
            end = starts[number + 1] if number + 1 < len(starts) else job_end
            step = Step(job=job, line=start + 1)
            first = lines[start].lstrip()[2:]
            if first.startswith("if:"):
                step.condition = _scalar(first[3:])
            elif first.startswith("continue-on-error:"):
                step.continue_on_error = _scalar(first[len("continue-on-error:"):])
            field_lines = range(start + 1, end)
            i = start + 1
            while i < end:
                line = lines[i]
                if _indent(line) != 8 or not line.strip() or line.lstrip().startswith("#"):
                    i += 1
                    continue
                match = re.match(r" {8}([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$", line)
                if not match:
                    i += 1
                    continue
                key, raw_value = match.group(1), match.group(2) or ""
                if key == "run" and raw_value in {"|", "|-", "|+"}:
                    body: list[str] = []
                    i += 1
                    while i < end and (not lines[i].strip() or _indent(lines[i]) >= 10):
                        body.append(lines[i][10:] if len(lines[i]) >= 10 else "")
                        i += 1
                    step.run = "\n".join(body)
                    continue
                if key == "run":
                    step.run = _scalar(raw_value)
                elif key == "uses":
                    step.uses = _scalar(raw_value)
                elif key == "if":
                    step.condition = _scalar(raw_value)
                elif key == "continue-on-error":
                    step.continue_on_error = _scalar(raw_value)
                elif key == "with":
                    i += 1
                    while i < end and (not lines[i].strip() or _indent(lines[i]) >= 10):
                        nested = re.match(r" {10}([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
                        if nested:
                            step.with_values[nested.group(1)] = _scalar(nested.group(2))
                        i += 1
                    continue
                i += 1
            steps.append(step)
    if not steps:
        findings.append(Finding("workflow-structure", "no job steps found in supported YAML layout"))
    return steps, findings


def _permissions(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line == "permissions:")
    except StopIteration:
        return None
    result: dict[str, str] = {}
    for line in lines[start + 1:]:
        if line and not line.startswith(" "):
            break
        match = re.match(r" {2}([A-Za-z0-9_-]+):\s*([^#\s]+)", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _shell_tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _check_cargo(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    commands: list[list[str]] = []
    for step in steps:
        if step.run is None:
            continue
        native_in_step = False
        for line in step.run.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                tokens = _shell_tokens(line)
            except ValueError:
                if re.search(r"\bcargo\b", line):
                    findings.append(Finding("workflow-cargo-syntax", f"unparseable Cargo shell at line {step.line}"))
                continue
            if not tokens or "cargo" not in tokens:
                continue
            native_in_step = True
            if tokens[0] != "cargo":
                findings.append(Finding("workflow-cargo-syntax", f"Cargo is not the executable at line {step.line}"))
                continue
            if any(token in {";", "&&", "||", "|", "&"} for token in tokens):
                findings.append(Finding("workflow-cargo-syntax", f"chained Cargo shell is not allowed at line {step.line}"))
                continue
            if tokens != ["cargo", "--version"]:
                commands.append(tokens)
        if native_in_step:
            nonempty = [line for line in step.run.splitlines() if line.strip() and not line.lstrip().startswith("#")]
            if step.condition is not None:
                findings.append(Finding("workflow-cargo-condition", f"Cargo step at line {step.line} has a condition"))
            if step.continue_on_error not in {None, "false"}:
                findings.append(Finding("workflow-step-failure", f"Cargo step at line {step.line} suppresses step failure"))
            if len(nonempty) != 1 and commands and commands[-1] in EXPECTED_CARGO:
                findings.append(Finding("workflow-cargo-syntax", f"required Cargo step at line {step.line} must be one simple command"))
        if re.search(r"\bcargo\b", step.run) and re.search(r"(?:2>\s*/dev/null|2>&1)", step.run):
            findings.append(Finding("workflow-cargo-syntax", f"Cargo output/status suppression at line {step.line}"))
    if commands != EXPECTED_CARGO:
        mismatch = next(
            (i for i, pair in enumerate(zip(commands, EXPECTED_CARGO)) if pair[0] != pair[1]),
            min(len(commands), len(EXPECTED_CARGO)),
        )
        findings.append(Finding(
            "workflow-cargo-contract",
            f"Cargo command contract mismatch at index {mismatch}; "
            f"required sequence has {len(EXPECTED_CARGO)} commands, observed {len(commands)}",
        ))
    return findings


def _check_actions(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    uses = [step.uses for step in steps if step.uses]
    for expected in (CHECKOUT, SETUP_PYTHON):
        if uses.count(expected) != 1:
            findings.append(Finding("workflow-action-pin", f"required action {expected.split('@')[0]} is missing, duplicated, or not exactly pinned"))
    for step in steps:
        if not step.uses:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})", step.uses)
        if not match:
            findings.append(Finding("workflow-action-pin", f"action at line {step.line} is not pinned to a full commit SHA"))
    checkouts = [step for step in steps if step.uses == CHECKOUT]
    for step in checkouts:
        if step.with_values.get("persist-credentials") != "false":
            findings.append(Finding("workflow-checkout-credentials", "checkout must disable persisted credentials"))
        if step.with_values.get("fetch-depth") != "1":
            findings.append(Finding("workflow-checkout-depth", "checkout must retain the bounded depth of 1"))
    for step in (step for step in steps if step.uses == SETUP_PYTHON):
        if step.with_values.get("python-version") != "3.14":
            findings.append(Finding("workflow-python-version", "setup-python must select Python 3.14"))
        if step.with_values.get("check-latest") != "false":
            findings.append(Finding("workflow-python-version", "setup-python must not select an unreviewed latest patch"))
    return findings


def _check_process(steps: list[Step]) -> list[Finding]:
    candidates = [step for step in steps if step.run and "target/debug/paperclip-game" in step.run]
    if len(candidates) != 1:
        return [Finding("workflow-process-contract", f"expected one native process guard, found {len(candidates)}")]
    step = candidates[0]
    body = step.run or ""
    errors: list[str] = []
    if step.condition is not None:
        errors.append("process guard must be unconditional")
    if step.continue_on_error not in {None, "false"}:
        errors.append("process guard must propagate step failure")
    if re.search(r"2>&1|\|\|\s*true|^\s*exit\s+0\s*$", body, re.MULTILINE):
        errors.append("merged streams, ignored status, or unconditional success is forbidden")
    for variable in ("stdout_file", "stderr_file"):
        if f'{variable}="$(mktemp)"' not in body:
            errors.append(f"{variable} must have its own mktemp output")
    helper = re.compile(
        r"capture_process\(\)\s*\{\s*"
        r"set \+e\s*"
        r'timeout\s+([1-9][0-9]*)s\s+target/debug/paperclip-game\s+"\$@"\s*'
        r'>\s*"\$stdout_file"\s+2>\s*"\$stderr_file"\s*'
        r"captured_status=\$\?\s*"
        r"set -e\s*\}",
        re.MULTILINE,
    )
    helper_match = helper.search(body)
    if not helper_match or int(helper_match.group(1)) > 60:
        errors.append("capture helper must separate streams, time out, capture $?, and restore set -e")

    cases = [
        ("capture_process", "1", "$expected_not_initialized", ("data/paperclip.sqlite3",)),
        ("capture_process --listen-addr 127.0.0.1:3100 --database-path data/bootstrap-smoke.sqlite3", "1", "$expected_not_initialized", ("data/bootstrap-smoke.sqlite3",)),
        ('capture_process --database-path "$sentinel_db" --pause 1', "2", "$expected_forbidden", ()),
        ("capture_process --listen-addr do-not-echo-this-ci-value", "2", "$expected_invalid_listener", ("data/paperclip.sqlite3", "data/bootstrap-smoke.sqlite3")),
    ]
    lines = [line.strip() for line in body.splitlines()]
    call_indexes = [i for i, line in enumerate(lines) if line.startswith("capture_process")]
    for call, status, expected_error, absent_paths in cases:
        try:
            index = lines.index(call)
        except ValueError:
            errors.append(f"missing process case for status {status} and {expected_error}")
            continue
        next_call = next((i for i in call_indexes if i > index), len(lines))
        segment = lines[index + 1:next_call]
        required = [
            f'test "$captured_status" -eq {status}',
            'test ! -s "$stdout_file"',
            f'test "$(cat "$stderr_file")" = "{expected_error}"',
        ]
        required.extend(f"test ! -e {path}" for path in absent_paths)
        for assertion in required:
            if assertion not in segment:
                errors.append(f"process case at line {index + 1} lacks assertion: {assertion}")
    for required in (
        "printf '%s' 'original-database-bytes' > \"$sentinel_db\"",
        'sentinel_before="$(cksum "$sentinel_db")"',
        'test "$(cksum "$sentinel_db")" = "$sentinel_before"',
        'test ! -e "${sentinel_db}-journal"',
        'test ! -e "${sentinel_db}-shm"',
        'test ! -e "${sentinel_db}-wal"',
    ):
        if required not in lines:
            errors.append(f"missing sentinel invariant: {required}")
    if re.search(r"^\s*(?:echo|printf)\b.*do-not-echo-this-ci-value", body, re.MULTILINE):
        errors.append("invalid-listener canary must not be printed")
    return [Finding("workflow-process-contract", message) for message in errors]


def validate_document(text: str) -> list[Finding]:
    findings: list[Finding] = []
    permissions = _permissions(text)
    if re.search(r"^ {4}permissions:", text, re.MULTILINE):
        findings.append(Finding("workflow-permissions", "job-level permission overrides are not supported by this contract"))
    if permissions is None or permissions.get("contents") != "read" or any(
        value not in {"read", "none"} for value in permissions.values()
    ):
        findings.append(Finding("workflow-permissions", "top-level permissions must be explicit and read-only with contents: read"))
    steps, parse_findings = parse_steps(text)
    findings.extend(parse_findings)
    if steps:
        findings.extend(_check_actions(steps))
        findings.extend(_check_cargo(steps))
        findings.extend(_check_process(steps))
    return findings


def _read_workflow(path: Path) -> str:
    with path.open("rb") as source:
        raw = source.read(MAX_WORKFLOW_BYTES + 1)
    if len(raw) > MAX_WORKFLOW_BYTES:
        raise ValueError("workflow exceeds the 256 KiB bound")
    if b"\0" in raw:
        raise ValueError("workflow contains a NUL byte")
    return raw.decode("utf-8")


def check_path(path: Path) -> int:
    try:
        text = _read_workflow(path)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Workflow validation failed: [workflow-read] {error}", file=sys.stderr)
        return 1
    findings = validate_document(text)
    if findings:
        print("Workflow validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"- [{finding.code}] {finding.message}", file=sys.stderr)
        print(f"{len(findings)} contract finding(s)", file=sys.stderr)
        return 1
    print("Workflow validation passed: action pins, read-only permissions, five Cargo commands, and four native process cases")
    print("Limits: bounded project YAML/shell shapes; the checker does not execute workflow commands")
    return 0


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("self-test mutation did not match exactly once")
    return text.replace(old, new, 1)


def _mutations(healthy: str) -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []

    def add(name: str, old: str, new: str, code: str) -> None:
        cases.append((name, _replace_once(healthy, old, new), code))

    add("unlocked-check", "run: cargo check --locked --all-targets", "run: cargo check --all-targets", "workflow-cargo-contract")
    add("unlocked-test", "run: cargo test --locked --all-targets", "run: cargo test --all-targets", "workflow-cargo-contract")
    add("unlocked-build", "run: cargo build --locked", "run: cargo build", "workflow-cargo-contract")
    add("ignored-test-status", "run: cargo test --locked --all-targets", "run: cargo test --locked --all-targets || true", "workflow-cargo-syntax")
    add("fake-cargo", "run: cargo test --locked --all-targets", "run: echo cargo test --locked --all-targets", "workflow-cargo-syntax")
    add("cargo-output-suppression", "run: cargo test --locked --all-targets", "run: cargo test --locked --all-targets 2>/dev/null", "workflow-cargo-syntax")
    add(
        "malformed-extra-cargo",
        "      - name: Check real bootstrap process contracts",
        "      - name: Additional malformed Cargo shell\n        run: cargo test --locked --all-targets \"\n\n      - name: Check real bootstrap process contracts",
        "workflow-cargo-syntax",
    )
    add(
        "canary-printf",
        "          capture_process --listen-addr do-not-echo-this-ci-value",
        "          printf '%s\\n' 'do-not-echo-this-ci-value'\n          capture_process --listen-addr do-not-echo-this-ci-value",
        "workflow-process-contract",
    )
    add(
        "canary-echo",
        "          capture_process --listen-addr do-not-echo-this-ci-value",
        "          echo 'do-not-echo-this-ci-value'\n          capture_process --listen-addr do-not-echo-this-ci-value",
        "workflow-process-contract",
    )
    add(
        "manifest-skip",
        "      - name: Test all Rust targets against the committed lockfile\n        run:",
        "      - name: Test all Rust targets against the committed lockfile\n        if: hashFiles('Cargo.toml') != ''\n        run:",
        "workflow-cargo-condition",
    )
    add(
        "ignored-cargo-step",
        "      - name: Test all Rust targets against the committed lockfile\n        run:",
        "      - name: Test all Rust targets against the committed lockfile\n        continue-on-error: true\n        run:",
        "workflow-step-failure",
    )
    add(
        "job-write-permissions",
        "  rust:\n",
        "  rust:\n    permissions: write-all\n",
        "workflow-permissions",
    )
    add(
        "wrong-python-version",
        'python-version: "3.14"',
        'python-version: "3.13"',
        "workflow-python-version",
    )
    add(
        "missing-test",
        "      - name: Test all Rust targets against the committed lockfile\n        run: cargo test --locked --all-targets\n\n",
        "",
        "workflow-cargo-contract",
    )
    add(
        "missing-fmt",
        "      - name: Check Rust formatting\n        run: cargo fmt --check\n\n",
        "",
        "workflow-cargo-contract",
    )
    swapped = _replace_once(healthy, "run: cargo check --locked --all-targets", "run: cargo __ORDER_PROBE__")
    swapped = _replace_once(swapped, "run: cargo clippy --locked --all-targets -- -D warnings", "run: cargo check --locked --all-targets")
    swapped = _replace_once(swapped, "run: cargo __ORDER_PROBE__", "run: cargo clippy --locked --all-targets -- -D warnings")
    cases.append(("reordered-check", swapped, "workflow-cargo-contract"))
    add("merged-process-streams", '> "$stdout_file" 2> "$stderr_file"', '> "$stdout_file" 2>&1', "workflow-process-contract")
    add("swallowed-process-status", "captured_status=$?", "captured_status=0", "workflow-process-contract")
    add(
        "disabled-process-status-assertion",
        'capture_process\n          test "$captured_status" -eq 1',
        'capture_process\n          test 0 -eq 0',
        "workflow-process-contract",
    )
    add("missing-sentinel-sidecar", 'test ! -e "${sentinel_db}-wal"', 'test ! -e "$sentinel_db"', "workflow-process-contract")
    add("floating-checkout", CHECKOUT, "actions/checkout@main", "workflow-action-pin")
    add("floating-python", SETUP_PYTHON, "actions/setup-python@v7", "workflow-action-pin")
    add("checkout-credentials", "persist-credentials: false", "persist-credentials: true", "workflow-checkout-credentials")
    add("write-permissions", "contents: read", "contents: write", "workflow-permissions")
    return cases


def self_test(script: Path, workflow: Path) -> int:
    try:
        healthy = _read_workflow(workflow)
        cases = _mutations(healthy)
        with tempfile.TemporaryDirectory(prefix="rust-workflow-self-test-") as temporary:
            root = Path(temporary)
            healthy_path = root / "healthy.yml"
            healthy_path.write_text(healthy, encoding="utf-8")
            expected_details = {
                "canary-printf": "invalid-listener canary must not be printed",
                "canary-echo": "invalid-listener canary must not be printed",
                "malformed-extra-cargo": "unparseable Cargo shell",
                "cargo-output-suppression": "Cargo output/status suppression",
            }
            fixtures = [("healthy", healthy_path, 0, None, "healthy", None)]
            for name, text, code in cases:
                path = root / f"{name}.yml"
                path.write_text(text, encoding="utf-8")
                fixtures.append((name, path, 1, code, "mutation", expected_details.get(name)))
            invalid_utf8 = root / "invalid-utf8.yml"
            invalid_utf8.write_bytes(b"\xff")
            oversized = root / "oversized.yml"
            oversized.write_bytes(b" " * (MAX_WORKFLOW_BYTES + 1))
            for name, path in (
                ("missing-input", root / "missing.yml"),
                ("invalid-utf8-input", invalid_utf8),
                ("oversized-input", oversized),
            ):
                fixtures.append((name, path, 1, "workflow-read", "bad-input", None))
            failures: list[str] = []
            rejected = 0
            bad_inputs = 0
            for name, path, expected_status, code, kind, detail in fixtures:
                completed = subprocess.run(
                    [sys.executable, "-B", str(script), "--workflow", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                combined = completed.stdout + completed.stderr
                if completed.returncode != expected_status:
                    failures.append(f"{name}: expected exit {expected_status}, observed {completed.returncode}")
                elif code is not None and f"[{code}]" not in combined:
                    failures.append(f"{name}: expected diagnostic {code}")
                elif detail is not None and detail not in combined:
                    failures.append(f"{name}: expected diagnostic detail was missing")
                elif code is None:
                    if completed.returncode != 0:
                        failures.append(f"{name}: healthy fixture was rejected")
                elif kind == "mutation":
                    rejected += 1
                else:
                    bad_inputs += 1
        if failures:
            print("Workflow self-test failed:", file=sys.stderr)
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            return 1
        print(f"Workflow self-test passed: 1 healthy fixture, {rejected} rejected mutations, and {bad_inputs} rejected bad inputs through the real CLI")
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        print(f"Workflow self-test harness failed: {type(error).__name__}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, default=Path(__file__).resolve().parents[1] / ".github/workflows/rust.yml")
    parser.add_argument("--self-test", action="store_true", help="exercise healthy and mutated private fixture copies through the real CLI")
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        return self_test(Path(__file__).resolve(), arguments.workflow)
    return check_path(arguments.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
