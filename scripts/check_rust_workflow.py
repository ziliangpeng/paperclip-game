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


PROCESS_CANARY = "do-not-echo-this-ci-value"


MAX_OUTPUT_BYTES = 1024 * 1024
NATIVE_PHASES = (
    {
        "probe": "api",
        "script": "scripts/check_api_process.py",
        "command": "python3 -B scripts/check_api_process.py target/debug/paperclip-game --repo .",
    },
    {
        "probe": "persistence",
        "script": "scripts/check_persistence_process.py",
        "command": "python3 -B scripts/check_persistence_process.py target/debug/paperclip-game",
    },
)
PUBLIC_SUFFIX = (
    "python3 -B scripts/check_public_hygiene.py",
    "python3 -B scripts/validate_inventory.py requirements/data/gameplay-inventory.json",
    "python3 -B scripts/validate_execution_plan.py requirements/data/execution-plan.json",
    "python3 -B scripts/validate_execution_plan.py requirements/data/execution-plan.json --self-test",
)
EARLY_GUARDS = (
    "python3 -B scripts/check_rust_workflow.py --workflow .github/workflows/rust.yml",
    "python3 -B scripts/check_public_hygiene.py --self-test",
)
PHASE_LINE_ROLES = (
    "errexit initialization",
    "stdout file allocation",
    "stderr file allocation",
    "owned cleanup trap",
    "exit-capture shell mode",
    "separate stdout/stderr probe redirection",
    "probe status capture",
    "errexit restoration",
    "bounded output guard",
)


def expected_phase_lines(phase: dict[str, str]) -> list[str]:
    probe = phase["probe"]
    return [
        "set -e",
        f'{probe}_stdout="$(mktemp)"',
        f'{probe}_stderr="$(mktemp)"',
        f"trap 'rm -f \"${probe}_stdout\" \"${probe}_stderr\"' EXIT",
        "set +e",
        f'{phase["command"]} > "${probe}_stdout" 2> "${probe}_stderr"',
        "status=$?",
        "set -e",
        f'python3 -B scripts/check_rust_workflow.py check-process-output '
        f'--stdout "${probe}_stdout" --stderr "${probe}_stderr" '
        f'--probe-status "$status" --probe {probe}',
    ]


def _process_steps(steps: list[Step], script: str) -> list[Step]:
    return [step for step in steps if step.run and script in step.run]


def _process_contract_finding(probe: str, detail: str) -> Finding:
    return Finding("workflow-process-contract", f"{probe}: {detail}")


def _check_native_processes(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    phase_positions: dict[str, int] = {}
    for phase in NATIVE_PHASES:
        probe = phase["probe"]
        candidates = _process_steps(steps, phase["script"])
        if len(candidates) != 1:
            findings.append(_process_contract_finding(probe, f"expected one native phase, found {len(candidates)}"))
            continue
        step = candidates[0]
        phase_positions[probe] = steps.index(step)
        if step.condition is not None or step.continue_on_error not in {None, "false"}:
            findings.append(_process_contract_finding(probe, "native phase must be unconditional and propagate failure"))
        actual_lines = [line.strip() for line in (step.run or "").splitlines() if line.strip()]
        expected_lines = expected_phase_lines(phase)
        if actual_lines != expected_lines:
            mismatch = next(
                (
                    index
                    for index, pair in enumerate(zip(actual_lines, expected_lines))
                    if pair[0] != pair[1]
                ),
                min(len(actual_lines), len(expected_lines)),
            )
            if mismatch < len(PHASE_LINE_ROLES):
                detail = f"output wiring mismatch at {PHASE_LINE_ROLES[mismatch]}"
            else:
                detail = "unexpected additional commands after the bounded output guard"
            findings.append(_process_contract_finding(probe, detail))

    if len(phase_positions) == len(NATIVE_PHASES):
        build_positions = [
            index for index, step in enumerate(steps)
            if step.run and step.run.strip() == "cargo build --locked"
        ]
        api_position = phase_positions["api"]
        persistence_position = phase_positions["persistence"]
        public_positions = [
            index for index, step in enumerate(steps)
            if step.run and step.run.strip() in PUBLIC_SUFFIX
        ]
        if (
            len(build_positions) != 1
            or api_position != persistence_position - 1
            or api_position <= build_positions[0]
            or not public_positions
            or persistence_position >= min(public_positions)
        ):
            findings.append(_process_contract_finding(
                "native phases",
                "API then persistence must follow locked build and precede public validation",
            ))
    return findings


def _check_public_validators(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    positions: list[int] = []
    for command in PUBLIC_SUFFIX:
        matches = [index for index, step in enumerate(steps) if step.run and step.run.strip() == command]
        if len(matches) != 1:
            findings.append(Finding(
                "workflow-public-contract",
                f"expected exactly one public validation command ending {command.rsplit('/', 1)[-1]}",
            ))
            continue
        index = matches[0]
        step = steps[index]
        if step.condition is not None or step.continue_on_error not in {None, "false"}:
            findings.append(Finding("workflow-public-contract", "public validators must be unconditional and propagate failure"))
        positions.append(index)
    if positions != sorted(positions):
        findings.append(Finding("workflow-public-contract", "public validators must retain their original order"))

    first_cargo = next(
        (index for index, step in enumerate(steps) if step.run and "cargo fmt --check" in step.run),
        None,
    )
    for command in EARLY_GUARDS:
        matches = [index for index, step in enumerate(steps) if step.run and step.run.strip() == command]
        if len(matches) != 1 or first_cargo is None or matches[0] >= first_cargo:
            findings.append(Finding(
                "workflow-public-contract",
                "workflow and hygiene self-tests must run before the native Cargo gates",
            ))
    return findings


def validate_document(text: str) -> list[Finding]:
    findings: list[Finding] = []
    permissions = _permissions(text)
    if permissions is None or permissions.get("contents") != "read" or any(
        value not in {"read", "none"} for value in permissions.values()
    ):
        findings.append(Finding("workflow-permissions", "top-level permissions must be explicit and read-only with contents: read"))
    if re.search(r"^ {4}permissions:", text, re.MULTILINE):
        findings.append(Finding("workflow-permissions", "job-level permission overrides are not supported by this contract"))
    steps, parse_findings = parse_steps(text)
    findings.extend(parse_findings)
    if steps:
        findings.extend(_check_actions(steps))
        findings.extend(_check_cargo(steps))
        findings.extend(_check_native_processes(steps))
        findings.extend(_check_public_validators(steps))
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
        print(f"Workflow validation failed: [workflow-read] {type(error).__name__}", file=sys.stderr)
        return 1
    findings = validate_document(text)
    if findings:
        print("Workflow validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"- [{finding.code}] {finding.message}", file=sys.stderr)
        print(f"{len(findings)} contract finding(s)", file=sys.stderr)
        return 1
    print("Workflow validation passed: action pins, five Cargo gates, API/persistence output contracts, and public validators")
    print("Limits: bounded workflow and process-output evidence only; no universal shell or secret classification")
    return 0


def _bounded_output_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise OSError("not a regular file")
    with path.open("rb") as source:
        raw = source.read(MAX_OUTPUT_BYTES + 1)
    if len(raw) > MAX_OUTPUT_BYTES:
        raise OSError("output exceeds byte bound")
    return raw


def _output_findings(stdout: Path, stderr: Path, status: str, probe: str) -> tuple[int, list[Finding]]:
    if probe not in {"api", "persistence"}:
        return 2, [Finding("workflow-input", "probe identity must be api or persistence")]
    if not re.fullmatch(r"-?[0-9]+", status):
        return 2, [Finding("workflow-input", "probe status must be an integer")]
    decimal_digits = status[1:] if status.startswith("-") else status
    if len(decimal_digits) > 3:
        return 2, [Finding("workflow-input", "probe status is outside the supported range")]
    numeric_status = int(status)
    if not -255 <= numeric_status <= 255:
        return 2, [Finding("workflow-input", "probe status is outside the supported range")]
    try:
        outputs = {
            "stdout": _bounded_output_file(stdout),
            "stderr": _bounded_output_file(stderr),
        }
    except OSError:
        return 2, [Finding(
            "workflow-io",
            "both output files must be readable, regular, non-symlink files within the byte bound",
        )]
    findings: list[Finding] = []
    channels = [
        channel for channel, content in outputs.items()
        if PROCESS_CANARY.encode() in content
    ]
    if channels:
        findings.append(Finding(
            "workflow-process-output",
            "synthetic canary found in captured " + " and ".join(channels),
        ))
    if numeric_status != 0:
        findings.append(Finding("workflow-process-exit", "native probe returned nonzero status"))
    return (1 if findings else 0), findings


def check_process_output(stdout: Path, stderr: Path, status: str, probe: str) -> int:
    exit_code, findings = _output_findings(stdout, stderr, status, probe)
    if findings:
        print("Process output validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"- [{finding.code}] {finding.message}", file=sys.stderr)
        return exit_code
    print(f"Probe output validation passed for {probe}: two bounded channels checked and status is zero")
    print("Scope: raw captured bytes only; no output, paths, or secret values are displayed")
    return 0


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("self-test mutation did not match exactly once")
    return text.replace(old, new, 1)


def _step_block(document: str, title: str) -> str:
    marker = f"      - name: {title}\n"
    start = document.index(marker)
    next_step = document.find("\n      - name:", start + len(marker))
    return document[start:] if next_step < 0 else document[start:next_step + 1]


def _base_mutations(healthy: str) -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []

    def add(name: str, old: str, new: str, code: str) -> None:
        cases.append((name, _replace_once(healthy, old, new), code))

    add("unlocked-check", "run: cargo check --locked --all-targets", "run: cargo check --all-targets", "workflow-cargo-contract")
    add("unlocked-test", "run: cargo test --locked --all-targets", "run: cargo test --all-targets", "workflow-cargo-contract")
    add("unlocked-build", "run: cargo build --locked", "run: cargo build", "workflow-cargo-contract")
    add("ignored-test-status", "run: cargo test --locked --all-targets", "run: cargo test --locked --all-targets || true", "workflow-cargo-syntax")
    add("fake-cargo", "run: cargo test --locked --all-targets", "run: echo cargo test --locked --all-targets", "workflow-cargo-syntax")
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
    add("job-write-permissions", "  rust:\n", "  rust:\n    permissions: write-all\n", "workflow-permissions")
    add("wrong-python-version", 'python-version: "3.14"', 'python-version: "3.13"', "workflow-python-version")
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
    add("floating-checkout", CHECKOUT, "actions/checkout@main", "workflow-action-pin")
    add("floating-python", SETUP_PYTHON, "actions/setup-python@v7", "workflow-action-pin")
    add("checkout-credentials", "persist-credentials: false", "persist-credentials: true", "workflow-checkout-credentials")
    add("write-permissions", "contents: read", "contents: write", "workflow-permissions")
    add("cargo-output-suppression", "run: cargo test --locked --all-targets", "run: cargo test --locked --all-targets 2>/dev/null", "workflow-cargo-syntax")
    add(
        "malformed-extra-cargo",
        "      - name: Capture real API process contracts",
        "      - name: Additional malformed Cargo shell\n        run: cargo test --locked --all-targets \"\n\n      - name: Capture real API process contracts",
        "workflow-cargo-syntax",
    )
    return cases


def _mutations(healthy: str) -> list[tuple[str, str, str]]:
    cases = _base_mutations(healthy)
    blocks = {
        "api": _step_block(healthy, "Capture real API process contracts"),
        "persistence": _step_block(healthy, "Capture real persistence process contracts"),
    }

    def change(name: str, probe: str, old: str, new: str) -> None:
        updated = _replace_once(blocks[probe], old, new)
        cases.append((name, healthy.replace(blocks[probe], updated, 1), "workflow-process-contract"))

    api = "python3 -B scripts/check_api_process.py target/debug/paperclip-game --repo ."
    persistence = "python3 -B scripts/check_persistence_process.py target/debug/paperclip-game"
    change("api-merged-channels", "api", '> "$api_stdout" 2> "$api_stderr"', '> "$api_stdout" 2>&1')
    change("api-flipped-output-bindings", "api", '> "$api_stdout" 2> "$api_stderr"', '> "$api_stderr" 2> "$api_stdout"')
    change("api-missing-stderr-binding", "api", ' 2> "$api_stderr"', "")
    change("api-raw-output-display", "api", "--probe api", "--probe api\n          cat \"$api_stderr\"")
    change(
        "api-status-not-captured",
        "api",
        'python3 -B scripts/check_api_process.py target/debug/paperclip-game --repo . > "$api_stdout" 2> "$api_stderr"\n          status=$?',
        f'{api} > "$api_stdout" 2> "$api_stderr"\n          status=0',
    )
    api_contract = (
        'python3 -B scripts/check_rust_workflow.py check-process-output --stdout "$api_stdout" '
        '--stderr "$api_stderr" --probe-status "$status" --probe api'
    )
    early_block = _replace_once(blocks["api"], api_contract + "\n", "")
    early_block = early_block.replace("          set +e\n", "          set +e\n          " + api_contract + "\n", 1)
    cases.append(("api-check-before-probe", healthy.replace(blocks["api"], early_block, 1), "workflow-process-contract"))
    change("persistence-status-ignored", "persistence", ' 2> "$persistence_stderr"', ' 2> "$persistence_stderr" || true')
    change(
        "persistence-guard-flipped-files",
        "persistence",
        '--stdout "$persistence_stdout" --stderr "$persistence_stderr"',
        '--stdout "$persistence_stderr" --stderr "$persistence_stdout"',
    )
    change("persistence-swallowed-status", "persistence", "status=$?", "status=0")
    change("persistence-raw-output-display", "persistence", "--probe persistence", "--probe persistence\n          cat \"$persistence_stdout\"")
    cases.append(("missing-api-phase", healthy.replace(blocks["api"], "", 1), "workflow-process-contract"))
    cases.append(("missing-persistence-phase", healthy.replace(blocks["persistence"], "", 1), "workflow-process-contract"))
    reversed_document = healthy.replace(blocks["api"] + blocks["persistence"], blocks["persistence"] + blocks["api"], 1)
    cases.append(("native-phase-order-reversed", reversed_document, "workflow-process-contract"))
    change("wrong-process-target", "api", "target/debug/paperclip-game", "target/debug/other-tool")
    cases.append((
        "missing-plan-guard",
        healthy.replace(_step_block(healthy, "Validate the complete execution plan"), "", 1),
        "workflow-public-contract",
    ))
    return cases


def _run_cli(arguments: list[str], timeout: float = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _case_result(name: str, expected: int, code: str | None, detail: str | None, completed: subprocess.CompletedProcess[str]) -> tuple[bool, dict[str, object]]:
    output = completed.stdout + completed.stderr
    passed = completed.returncode == expected
    if code is not None:
        passed = passed and f"[{code}]" in output
    if detail is not None:
        passed = passed and detail in output
    record = {
        "name": name,
        "expected_exit": expected,
        "actual_exit": completed.returncode,
        "expected_code": code,
        "code_observed": code is None or f"[{code}]" in output,
        "detail_observed": detail is None or detail in output,
        "passed": passed,
    }
    return passed, record


def _static_self_test(script: Path, workflow: Path, root: Path) -> tuple[int, list[dict[str, object]]]:
    healthy = _read_workflow(workflow)
    fixtures = [("healthy-workflow", healthy, 0, None)]
    expected_details = {
        "malformed-extra-cargo": "unparseable Cargo shell",
        "cargo-output-suppression": "Cargo output/status suppression",
        "api-merged-channels": "separate stdout/stderr probe redirection",
        "api-flipped-output-bindings": "separate stdout/stderr probe redirection",
        "api-missing-stderr-binding": "separate stdout/stderr probe redirection",
        "api-status-not-captured": "probe status capture",
        "persistence-swallowed-status": "probe status capture",
        "persistence-guard-flipped-files": "bounded output guard",
        "api-raw-output-display": "unexpected additional commands",
        "persistence-raw-output-display": "unexpected additional commands",
        "native-phase-order-reversed": "must follow locked build and precede public validation",
        "missing-plan-guard": "public",
    }
    for name, text, code in _mutations(healthy):
        fixtures.append((name, text, 1, code))
    results: list[dict[str, object]] = []
    for name, text, expected, code in fixtures:
        path = root / f"{name}.yml"
        path.write_text(text, encoding="utf-8")
        completed = _run_cli([sys.executable, "-B", str(script), "--workflow", str(path)])
        passed, record = _case_result(name, expected, code, expected_details.get(name), completed)
        record["kind"] = "healthy-workflow" if expected == 0 else "workflow-mutation"
        results.append(record)
        if not passed:
            return 1, results
    for name, raw in (("missing-input", None), ("invalid-utf8-input", b"\xff"), ("oversized-input", b" " * (MAX_WORKFLOW_BYTES + 1))):
        path = root / f"{name}.yml"
        if raw is not None:
            path.write_bytes(raw)
        completed = _run_cli([sys.executable, "-B", str(script), "--workflow", str(path)])
        passed, record = _case_result(name, 1, "workflow-read", None, completed)
        record["kind"] = "bad-input"
        results.append(record)
        if not passed:
            return 1, results
    return 0, results


def _runtime_self_test(script: Path, root: Path) -> tuple[int, list[dict[str, object]]]:
    results: list[dict[str, object]] = []
    case_number = 0

    def check(
        name: str,
        stdout: Path,
        stderr: Path,
        status: str,
        expected: int,
        code: str | None,
        detail: str | None = None,
        auxiliary_code: str | None = None,
        forbid_status_echo: bool = False,
    ) -> bool:
        nonlocal case_number
        case_number += 1
        completed = _run_cli([
            sys.executable, "-B", str(script), "check-process-output",
            "--stdout", str(stdout), "--stderr", str(stderr),
            "--probe-status", status, "--probe", "api",
        ])
        passed, record = _case_result(name, expected, code, detail, completed)
        combined = completed.stdout + completed.stderr
        if auxiliary_code is not None:
            passed = passed and auxiliary_code in combined
            record["auxiliary_code_observed"] = auxiliary_code in combined
        if forbid_status_echo:
            passed = passed and "Traceback" not in combined and str(script) not in combined and status not in combined
            record["no_traceback_checker_path_or_full_status"] = all(
                value not in combined for value in ("Traceback", str(script), status)
            )
        if PROCESS_CANARY in combined:
            passed = False
            record["literal_leaked"] = True
        record["kind"] = "runtime-output"
        results.append(record)
        return passed

    healthy_out = root / "healthy.stdout"
    healthy_err = root / "healthy.stderr"
    healthy_out.write_text("paperclip HTTP writes passed\n", encoding="utf-8")
    healthy_err.write_text("paperclip-game: listening on http://127.0.0.1:3000\n", encoding="utf-8")

    def variant(
        name: str,
        out: bytes,
        err: bytes,
        status: str,
        expected: int,
        code: str | None,
        detail: str | None = None,
        auxiliary_code: str | None = None,
    ) -> bool:
        out_path = root / f"{name}.stdout"
        err_path = root / f"{name}.stderr"
        out_path.write_bytes(out)
        err_path.write_bytes(err)
        return check(name, out_path, err_path, status, expected, code, detail, auxiliary_code)

    if not check("runtime-healthy", healthy_out, healthy_err, "0", 0, None):
        return 1, results
    if not variant("runtime-stdout-canary", PROCESS_CANARY.encode(), b"ordinary\n", "0", 1, "workflow-process-output", "captured stdout"):
        return 1, results
    if not variant("runtime-stderr-canary", b"ordinary\n", PROCESS_CANARY.encode(), "0", 1, "workflow-process-output", "captured stderr"):
        return 1, results
    if not variant("runtime-both-canary", PROCESS_CANARY.encode(), PROCESS_CANARY.encode(), "0", 1, "workflow-process-output", "stdout and stderr"):
        return 1, results
    if not variant("runtime-reconstructed-canary", b"prefix " + PROCESS_CANARY.encode(), b"", "0", 1, "workflow-process-output", "captured stdout"):
        return 1, results
    if not variant("runtime-flipped-binding", b"", PROCESS_CANARY.encode(), "0", 1, "workflow-process-output", "captured stderr"):
        return 1, results
    if not variant("runtime-nonzero", b"native failure\n", b"", "1", 1, "workflow-process-exit", "nonzero status"):
        return 1, results
    if not variant("runtime-nonzero-with-canary", b"", PROCESS_CANARY.encode(), "7", 1, "workflow-process-exit", "nonzero status", "[workflow-process-output]"):
        return 1, results
    missing = root / "missing.stdout"
    if not check("runtime-missing-stdout", missing, healthy_err, "0", 2, "workflow-io", "readable, regular"):
        return 1, results
    if not check("runtime-missing-stderr", healthy_out, root / "missing.stderr", "0", 2, "workflow-io", "readable, regular"):
        return 1, results
    if not check("runtime-directory-stdout", root, healthy_err, "0", 2, "workflow-io", "regular"):
        return 1, results
    if not check("runtime-directory-stderr", healthy_out, root, "0", 2, "workflow-io", "regular"):
        return 1, results
    link_target = root / "ordinary.txt"
    link_target.write_text("ordinary\n", encoding="utf-8")
    symlink = root / "symlink.stdout"
    symlink.symlink_to(link_target.name)
    if not check("runtime-symlink-stdout", symlink, healthy_err, "0", 2, "workflow-io", "non-symlink"):
        return 1, results
    if not variant("runtime-oversized", b"x" * (MAX_OUTPUT_BYTES + 1), b"", "0", 2, "workflow-io", "byte bound"):
        return 1, results
    if not check("runtime-invalid-status", healthy_out, healthy_err, PROCESS_CANARY, 2, "workflow-input", "integer"):
        return 1, results
    if not check("runtime-negative-status", healthy_out, healthy_err, "-1", 1, "workflow-process-exit", "nonzero status"):
        return 1, results
    if not check("runtime-long-decimal-status", healthy_out, healthy_err, "9" * 5000, 2, "workflow-input", "outside the supported range", forbid_status_echo=True):
        return 1, results
    return 0, results


def self_test(script: Path, workflow: Path) -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="runtime-output-self-test-") as temporary:
            root = Path(temporary)
            static_status, static_results = _static_self_test(script, workflow, root)
            runtime_status, runtime_results = _runtime_self_test(script, root)
        results = static_results + runtime_results
        for record in results:
            state = "PASS" if record["passed"] else "FAIL"
            print(f"{state} {record['kind']} {record['name']} expected={record['expected_exit']} actual={record['actual_exit']}")
        if static_status != 0 or runtime_status != 0:
            print("Runtime-output self-test failed", file=sys.stderr)
            return 1
        workflow_rejections = sum(record["kind"] == "workflow-mutation" for record in static_results)
        bad_inputs = sum(record["kind"] == "bad-input" for record in static_results)
        runtime_rejections = sum(record["actual_exit"] != 0 for record in runtime_results)
        print(
            f"Runtime-output self-test passed: 1 healthy workflow, {workflow_rejections} rejected workflow mutations, "
            f"{bad_inputs} rejected read errors, 1 healthy output case, {runtime_rejections} rejected output cases"
        )
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        print(f"Runtime-output self-test harness failed: {type(error).__name__}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["check-process-output"])
    parser.add_argument("--workflow", type=Path, default=Path(__file__).resolve().parents[1] / ".github/workflows/rust.yml")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--stdout", type=Path)
    parser.add_argument("--stderr", type=Path)
    parser.add_argument("--probe-status")
    parser.add_argument("--probe", choices=["api", "persistence"])
    arguments = parser.parse_args(argv)
    if arguments.command == "check-process-output":
        if arguments.stdout is None or arguments.stderr is None or arguments.probe_status is None or arguments.probe is None:
            print("Process output validation failed: [workflow-input] two channels, status, and probe identity are required", file=sys.stderr)
            return 2
        return check_process_output(arguments.stdout, arguments.stderr, arguments.probe_status, arguments.probe)
    if arguments.stdout is not None or arguments.stderr is not None or arguments.probe_status is not None or arguments.probe is not None:
        print("Workflow validation failed: [workflow-input] process-output arguments require check-process-output", file=sys.stderr)
        return 2
    if arguments.self_test:
        return self_test(Path(__file__).resolve(), arguments.workflow)
    return check_path(arguments.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
