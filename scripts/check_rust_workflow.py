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
RUSTUP_COMMAND = "rustup toolchain install stable --profile minimal --component rustfmt,clippy"
TOOL_VERSIONS_COMMAND = "rustup show active-toolchain\nrustc --version\ncargo --version\npython3 --version"
EXPECTED_CARGO = [
    ["cargo", "fmt", "--check"],
    ["cargo", "check", "--locked", "--all-targets"],
    ["cargo", "clippy", "--locked", "--all-targets", "--", "-D", "warnings"],
    ["cargo", "test", "--locked", "--all-targets"],
    ["cargo", "build", "--locked"],
]


STEP_METADATA_KEYS = {"name", "run", "uses", "with", "if", "continue-on-error", "shell"}
STEP_WITH_KEYS = {"fetch-depth", "persist-credentials", "python-version", "check-latest"}


@dataclass
class Step:
    job: str
    line: int
    run: str | None = None
    uses: str | None = None
    condition: str | None = None
    continue_on_error: str | None = None
    shell: str | None = None
    with_values: dict[str, str] = field(default_factory=dict)
    unsupported_metadata: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _metadata_parts(token: str) -> tuple[str, str] | None:
    """Read one plain or quoted step key and its raw scalar value."""
    token = token.strip()
    if len(token) >= 2 and token[0] in {'"', "'"}:
        quote = token[0]
        end = token.find(quote, 1)
        if end <= 1 or end + 1 >= len(token) or token[end + 1] != ":":
            return None
        candidate = token[1:end]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
            return None
        return candidate, token[end + 2:].lstrip()
    match = re.fullmatch(r"(<<|[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?", token)
    return (match.group(1), match.group(2) or "") if match else None


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
         if lines[i] and not lines[i].startswith((" ", "#"))),
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
            i = start
            while i < end:
                if i == start:
                    token = lines[start].lstrip()[2:]
                    line_number = start + 1
                else:
                    line = lines[i]
                    if _indent(line) != 8 or not line.strip() or line.lstrip().startswith("#"):
                        i += 1
                        continue
                    token = line.strip()
                    line_number = i + 1
                metadata = _metadata_parts(token)
                if metadata is None:
                    findings.append(Finding("workflow-step-contract", f"unsupported step metadata structure at line {line_number}"))
                    i += 1
                    continue
                key, raw_value = metadata
                if key not in STEP_METADATA_KEYS:
                    step.unsupported_metadata.append(key)
                    findings.append(Finding("workflow-step-contract", f"unsupported step metadata {key} at line {line_number}"))
                    i += 1
                    continue
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
                elif key == "shell":
                    step.shell = _scalar(raw_value)
                    if step.shell not in {"bash", "sh"}:
                        step.unsupported_metadata.append(key)
                        findings.append(Finding("workflow-step-contract", f"unsupported custom shell at line {line_number}"))
                elif key == "if":
                    step.condition = _scalar(raw_value)
                elif key == "continue-on-error":
                    step.continue_on_error = _scalar(raw_value)
                elif key == "with":
                    i += 1
                    while i < end and (not lines[i].strip() or _indent(lines[i]) >= 10):
                        if not lines[i].strip() or lines[i].lstrip().startswith("#"):
                            i += 1
                            continue
                        nested = re.match(r" {10}([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
                        if not nested or nested.group(1) not in STEP_WITH_KEYS:
                            findings.append(Finding("workflow-step-contract", f"unsupported nested action input at line {i + 1}"))
                        else:
                            step.with_values[nested.group(1)] = _scalar(nested.group(2))
                        i += 1
                    continue
                i += 1
            if step.shell is not None and step.run is None:
                findings.append(Finding("workflow-step-contract", f"shell is supported only on run steps at line {step.line}"))
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
        if line and not line.startswith((" ", "#")):
            break
        match = re.fullmatch(r" {2}([A-Za-z0-9_-]+):\s*([^#\s]+)\s*(?:#.*)?", line)
        if match:
            result[match.group(1)] = match.group(2)
        elif line.strip() and not line.lstrip().startswith("#"):
            # Preserve unsupported non-comment content as an invalid entry instead of dropping it.
            result["<unsupported-permission-entry>"] = "unsupported"
    return result


def _check_root_metadata_contract(text: str) -> list[Finding]:
    """Apply the two bounded root-metadata contracts shared by both workflows."""
    root_keys: list[str] = []
    for line in text.splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        parts = _metadata_parts(line)
        if parts is None:
            spaced_key = re.match(r"""^((?:defaults|permissions|"defaults"|"permissions"|'defaults'|'permissions'))\s+:""", line)
            if spaced_key:
                parts = _metadata_parts(spaced_key.group(1) + ":" + line[spaced_key.end():])
        if parts is not None:
            root_keys.append(parts[0])
    findings: list[Finding] = []
    if "defaults" in root_keys:
        findings.append(Finding(
            "workflow-default-shell",
            "unsupported top-level defaults, including defaults.run.shell; use only supported per-step bash/sh",
        ))
    if root_keys.count("permissions") > 1:
        findings.append(Finding(
            "workflow-permissions",
            "duplicate top-level permissions blocks; declare exactly one read-only permissions mapping",
        ))
    return findings


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
            if tokens == ["cargo", "shell"]:
                findings.append(Finding("workflow-cargo-contract", f"Cargo shell metadata is not allowed at line {step.line}"))
            if tokens != ["cargo", "--version"]:
                commands.append(tokens)
        if native_in_step:
            nonempty = [line for line in step.run.splitlines() if line.strip() and not line.lstrip().startswith("#")]
            if step.unsupported_metadata:
                findings.append(Finding("workflow-cargo-contract", f"unsupported execution metadata cannot hide the Cargo command at line {step.line}"))
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
    action_positions = [
        [index for index, step in enumerate(steps) if step.uses == expected]
        for expected in (CHECKOUT, SETUP_PYTHON)
    ]
    first_run = next((index for index, step in enumerate(steps) if step.run is not None), None)
    if all(len(positions) == 1 for positions in action_positions):
        checkout_position, setup_position = (positions[0] for positions in action_positions)
        if first_run is None or not checkout_position < setup_position < first_run:
            findings.append(Finding("workflow-action-contract", "checkout then setup-python must precede every run step"))
    for step in steps:
        if not step.uses:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})", step.uses)
        if step.condition is not None or step.continue_on_error not in {None, "false"}:
            findings.append(Finding("workflow-action-contract", f"action step at line {step.line} must be unconditional and propagate failure"))
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


def _check_rust_bootstrap(steps: list[Step]) -> list[Finding]:
    findings: list[Finding] = []
    positions: list[int] = []
    for label, command in (
        ("stable Rust setup", RUSTUP_COMMAND),
        ("exact tool version recording", TOOL_VERSIONS_COMMAND),
    ):
        matches = [step for step in steps if step.run and step.run.strip() == command]
        if len(matches) != 1:
            findings.append(Finding("workflow-bootstrap-contract", f"{label} must appear exactly once"))
            continue
        step = matches[0]
        positions.append(steps.index(step))
        if step.unsupported_metadata:
            findings.append(Finding("workflow-bootstrap-contract", f"unsupported execution metadata cannot hide {label} at line {step.line}"))
        if step.condition is not None or step.continue_on_error not in {None, "false"}:
            findings.append(Finding("workflow-bootstrap-contract", f"bootstrap step at line {step.line} must be unconditional and propagate failure"))
    setup_positions = [index for index, step in enumerate(steps) if step.uses == SETUP_PYTHON]
    first_cargo = next((index for index, step in enumerate(steps) if step.run and step.run.strip() == "cargo fmt --check"), None)
    if len(positions) == 2 and len(setup_positions) == 1:
        if (
            positions != sorted(positions)
            or positions[0] < setup_positions[0]
            or first_cargo is None
            or positions[1] > first_cargo
        ):
            findings.append(Finding("workflow-bootstrap-contract", "stable setup and ordered version recording must follow setup-python and precede Cargo"))
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
    "python3 -B scripts/check_rust_workflow.py check-controls-workflow --workflow .github/workflows/workflow-controls.yml",
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


BROWSER_COMMAND = "python3 -B scripts/check_browser_stream.py target/debug/paperclip-game --require-browser"


def _check_browser_contract(steps: list[Step]) -> list[Finding]:
    matches = [step for step in steps if step.run and "scripts/check_browser_stream.py" in step.run]
    if len(matches) != 1:
        return [Finding(
            "workflow-browser-contract",
            f"expected one real browser stream step with --require-browser, found {len(matches)}",
        )]
    findings: list[Finding] = []
    step = matches[0]
    if step.unsupported_metadata:
        findings.append(Finding("workflow-browser-contract", f"custom interpreter, merge, or unknown metadata cannot hide the browser phase at line {step.line}"))
    if step.run.strip() != BROWSER_COMMAND:
        findings.append(Finding(
            "workflow-browser-contract",
            "browser stream must execute the real native binary with the non-optional --require-browser flag",
        ))
    if step.condition is not None or step.continue_on_error not in {None, "false"}:
        findings.append(Finding("workflow-browser-contract", "browser stream phase must be unconditional and propagate failure"))
    persistence_positions = [index for index, item in enumerate(steps) if item.run and "scripts/check_persistence_process.py" in item.run]
    public_positions = [index for index, item in enumerate(steps) if item.run and item.run.strip() in PUBLIC_SUFFIX]
    browser_position = steps.index(step)
    if persistence_positions and public_positions:
        if browser_position != persistence_positions[0] + 1 or browser_position >= min(public_positions):
            findings.append(Finding("workflow-browser-contract", "browser stream must run immediately after persistence and before public validation"))
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
        if (len(matches) != 1 or first_cargo is None or matches[0] >= first_cargo
                or steps[matches[0]].condition is not None
                or steps[matches[0]].continue_on_error not in {None, "false"}):
            findings.append(Finding(
                "workflow-public-contract",
                "workflow and hygiene self-tests must run before the native Cargo gates",
            ))
    return findings


REQUIRED_RUST_JOB_METADATA = {"name", "runs-on", "timeout-minutes", "env", "steps"}


def _check_job_contract(text: str, job_id: str = "rust") -> list[Finding]:
    """Bound this issue's one unconditional Rust job and its root metadata.

    Only the dedicated rust job is a supported actor. Any if/needs, auxiliary
    job, unknown metadata shape, or merge/alias construct is rejected rather
    than evaluated as a GitHub expression. Comments and nested step content do
    not participate in root job metadata extraction.
    """
    if job_id not in {"rust", "controls"}:
        raise ValueError("unsupported required job identity")
    findings: list[Finding] = []
    lines = text.splitlines()
    try:
        jobs_start = next(index for index, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        return [Finding("workflow-job-contract", "missing required top-level jobs mapping")]

    rust_job = False
    rust_seen = False
    job_count = 0
    metadata_keys: set[str] = set()
    for number, line in enumerate(lines[jobs_start + 1:], start=jobs_start + 2):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped and _indent(line) == 0:
            break
        if re.match(r" {2}\S.*:\s*$", line):
            job_count += 1
            if line == f"  {job_id}:" or line.startswith(f"  {job_id}: #"):
                if rust_seen:
                    findings.append(Finding("workflow-job-contract", f"duplicate required {job_id} job at line {number}"))
                rust_seen = True
                rust_job = True
                metadata_keys = set()
            else:
                find_detail = f"unexpected additional job in the single required {job_id} workflow at line {number}"
                findings.append(Finding("workflow-job-contract", find_detail))
                rust_job = False
            continue
        if not rust_job or not stripped or stripped.startswith("#"):
            continue
        if _indent(line) != 4:
            continue
        match = re.match(r" {4}([A-Za-z0-9_-]+):(?:\s|$)", line)
        if not match:
            findings.append(Finding(
                "workflow-job-contract",
                f"unsupported root metadata structure at line {number}; quoted and merge forms must declare the current known keys only",
            ))
            continue
        key = match.group(1)
        if key in {"if", "needs"}:
            findings.append(Finding(
                "workflow-job-contract",
                f"required {job_id} job cannot use conditional/dependent {key} at line {number}; the full required job must execute",
            ))
            continue
        if key not in REQUIRED_RUST_JOB_METADATA:
            findings.append(Finding(
                "workflow-job-contract",
                f"unexpected root job metadata at line {number}; only name, runs-on, timeout-minutes, env, steps are allowed",
            ))
            continue
        if key in metadata_keys:
            findings.append(Finding("workflow-job-contract", f"duplicate root metadata key {key} at line {number}"))
        metadata_keys.add(key)
    if not rust_seen or job_count != 1:
        findings.append(Finding(
            "workflow-job-contract",
            f"workflow must contain exactly one unique unconditional {job_id} job; conditional prerequisites and helper-job escapes are not supported",
        ))
    missing = REQUIRED_RUST_JOB_METADATA - metadata_keys
    if rust_seen and missing:
        findings.append(Finding(
            "workflow-job-contract",
            f"required root metadata is incomplete for the dedicated {job_id} job: " + ", ".join(sorted(missing)),
        ))
    return findings


CONTROL_PATHS = (
    ".github/workflows/rust.yml",
    ".github/workflows/workflow-controls.yml",
    "scripts/check_rust_workflow.py",
    "scripts/check_public_hygiene.py",
)
CONTROLS_COMMANDS = (
    "python3 --version",
    "python3 -B scripts/check_rust_workflow.py --workflow .github/workflows/rust.yml",
    "python3 -B scripts/check_rust_workflow.py --self-test",
    "python3 -B scripts/check_public_hygiene.py",
    "python3 -B scripts/check_public_hygiene.py --self-test",
    "python3 -B scripts/check_rust_workflow.py check-controls-workflow --workflow .github/workflows/workflow-controls.yml",
)
CONTROLS_WORKFLOW_CHECK = "python3 -B scripts/check_rust_workflow.py check-controls-workflow --workflow .github/workflows/workflow-controls.yml"


def _trigger_lines(text: str) -> list[str] | None:
    """Return the sole top-level on block, excluding its declaration."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == "on:"]
    if len(starts) != 1:
        return None
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines))
         if lines[index] and not lines[index].startswith((" ", "#"))),
        len(lines),
    )
    return lines[start + 1:end]


def _trigger_list_value(text: str, parent: str, key: str) -> list[str] | None:
    """Read one bounded list from on.pull_request/push, never from job steps."""
    lines = _trigger_lines(text)
    if lines is None:
        return None
    in_parent = False
    in_key = False
    values: list[str] = []
    found_parent = False
    found_key = False
    for line in lines:
        if line == f"  {parent}:":
            if found_parent:
                return None
            found_parent = True
            in_parent = True
            in_key = False
            continue
        indentation = _indent(line)
        stripped = line.strip()
        if indentation == 2 and re.match(r"  [A-Za-z0-9_-]+:", line):
            in_parent = False
            in_key = False
            continue
        if not in_parent or not stripped or stripped.startswith("#"):
            continue
        if indentation == 4 and re.match(r" {4}[A-Za-z0-9_-]+:", line):
            if stripped == f"{key}:":
                if found_key:
                    return None
                found_key = True
                in_key = True
                values = []
            else:
                in_key = False
            continue
        if in_key and stripped.startswith("- "):
            if indentation != 6 or not line.startswith("      - "):
                return None
            values.append(_scalar(stripped[2:]))
            continue
        if in_key and indentation < 6:
            break
    return values if found_parent and found_key else None


def _check_rust_triggers(text: str) -> list[Finding]:
    findings: list[Finding] = []
    trigger_lines = _trigger_lines(text)
    if trigger_lines is None:
        return [Finding("workflow-rust-trigger-contract", "Rust document must contain exactly one top-level on block")]
    current_trigger: str | None = None
    current_field: str | None = None
    trigger_names: list[str] = []
    allowed_nested = {
        "pull_request": set(),
        "push": {"branches"},
        "workflow_dispatch": set(),
    }
    for line in trigger_lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        root = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
        if root:
            current_trigger = root.group(1)
            current_field = None
            trigger_names.append(current_trigger)
            continue
        nested = re.fullmatch(r"    ([A-Za-z0-9_-]+):", line)
        if nested:
            current_field = nested.group(1)
            if current_trigger not in allowed_nested or nested.group(1) not in allowed_nested[current_trigger]:
                findings.append(Finding("workflow-rust-trigger-contract", f"unsupported Rust trigger metadata {nested.group(1)}"))
            continue
        if re.fullmatch(r"      - .+", line) and current_trigger == "push" and current_field == "branches":
            continue
        findings.append(Finding("workflow-rust-trigger-contract", "unsupported Rust trigger structure; sequence entries are only allowed under push.branches"))
    if trigger_names != ["pull_request", "push", "workflow_dispatch"]:
        findings.append(Finding("workflow-rust-trigger-contract", "Rust triggers must be exactly pull_request, push, and workflow_dispatch"))
    if _trigger_list_value(text, "push", "branches") != ["main"]:
        findings.append(Finding("workflow-rust-trigger-contract", "push must target exactly the main branch through branches"))
    return findings


def _check_controls_document(text: str) -> list[Finding]:
    findings = _check_root_metadata_contract(text)
    findings.extend(_check_job_contract(text, job_id="controls"))
    trigger_lines = _trigger_lines(text)
    if trigger_lines is None:
        findings.append(Finding("workflow-controls-contract", "controls document must contain exactly one top-level on block"))
    else:
        current_trigger: str | None = None
        trigger_names: list[str] = []
        allowed_nested = {
            "pull_request": {"paths"},
            "push": {"paths", "branches"},
            "workflow_dispatch": set(),
        }
        for line in trigger_lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            root = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
            if root:
                current_trigger = root.group(1)
                trigger_names.append(current_trigger)
                continue
            nested = re.fullmatch(r"    ([A-Za-z0-9_-]+):", line)
            if nested:
                if current_trigger not in allowed_nested or nested.group(1) not in allowed_nested[current_trigger]:
                    findings.append(Finding("workflow-controls-contract", f"unsupported controls trigger metadata {nested.group(1)}"))
                continue
            if re.fullmatch(r"      - .+", line) and current_trigger != "workflow_dispatch":
                continue
            findings.append(Finding("workflow-controls-contract", "unsupported controls trigger structure"))
        if trigger_names != ["pull_request", "push", "workflow_dispatch"]:
            findings.append(Finding("workflow-controls-contract", "controls triggers must be exactly pull_request, push, and workflow_dispatch"))
        if _trigger_list_value(text, "pull_request", "paths") != list(CONTROL_PATHS):
            findings.append(Finding("workflow-controls-contract", "pull_request must have exactly the four required control paths"))
        if _trigger_list_value(text, "push", "paths") != list(CONTROL_PATHS):
            findings.append(Finding("workflow-controls-contract", "push on main must have exactly the four required control paths"))
        if _trigger_list_value(text, "push", "branches") != ["main"]:
            findings.append(Finding("workflow-controls-contract", "push must target exactly the main branch"))
    permissions = _permissions(text)
    if permissions is None or permissions.get("contents") != "read" or any(
        value not in {"read", "none"} for value in permissions.values()
    ):
        findings.append(Finding("workflow-permissions", "controls permissions must be read-only with contents: read"))
    steps, parse_findings = parse_steps(text)
    findings.extend(parse_findings)
    if steps:
        findings.extend(_check_actions(steps))
        commands = [step.run.strip() for step in steps if step.run is not None]
        if commands != list(CONTROLS_COMMANDS):
            findings.append(Finding("workflow-controls-contract", "controls command sequence or required self-check invocation is incorrect"))
        for step in steps:
            if step.condition is not None or step.continue_on_error not in {None, "false"}:
                findings.append(Finding("workflow-controls-contract", f"controls step at line {step.line} must be unconditional and propagate failure"))
    return findings


def check_controls_path(path: Path) -> int:
    try:
        text = _read_workflow(path)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Controls workflow validation failed: [workflow-read] {type(error).__name__}", file=sys.stderr)
        return 1
    findings = _check_controls_document(text)
    if findings:
        print("Controls workflow validation failed:", file=sys.stderr)
        for finding in findings:
            print(f"- [{finding.code}] {finding.message}", file=sys.stderr)
        print(f"{len(findings)} contract finding(s)", file=sys.stderr)
        return 1
    print("Controls workflow validation passed: one unconditional controls job, exact command and trigger contracts")
    print("Limits: the dedicated controls document shape; no universal YAML or GitHub expression evaluator")
    return 0


def validate_document(text: str) -> list[Finding]:
    findings: list[Finding] = _check_root_metadata_contract(text)
    findings.extend(_check_job_contract(text))
    findings.extend(_check_rust_triggers(text))
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
        findings.extend(_check_rust_bootstrap(steps))
        findings.extend(_check_cargo(steps))
        findings.extend(_check_native_processes(steps))
        findings.extend(_check_browser_contract(steps))
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
    if not re.fullmatch(r"[0-9]+", status):
        return 2, [Finding("workflow-input", "probe status must be a non-negative integer")]
    decimal_digits = status
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
    plan_guard = "        run: python3 -B scripts/validate_execution_plan.py requirements/data/execution-plan.json --self-test"
    add(
        "comment-job-if",
        plan_guard,
        plan_guard + "\n# comments do not end a YAML mapping\n    if: ${{ false }}",
        "workflow-job-contract",
    )
    add(
        "comment-job-needs-helper",
        plan_guard,
        plan_guard + "\n# comments do not end a YAML mapping\n    needs: disabled-prerequisite\n"
        "  disabled-prerequisite:\n    runs-on: ubuntu-24.04\n    if: ${{ false }}\n    steps:\n      - run: \"true\"",
        "workflow-job-contract",
    )
    add(
        "comment-permissions-write",
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n# comments do not end a YAML mapping\n  actions: write",
        "workflow-permissions",
    )
    add(
        "comment-last-step-if",
        plan_guard,
        plan_guard + "\n# comments do not end a YAML mapping\n        if: ${{ false }}",
        "workflow-public-contract",
    )
    cargo_test_header = "      - name: Test all Rust targets against the committed lockfile\n"
    add(
        "step-cargo-quoted-if",
        cargo_test_header + "        run:",
        cargo_test_header + "        \"if\": ${{ false }}\n        run:",
        "workflow-cargo-condition",
    )
    add(
        "step-cargo-inline-quoted-if",
        cargo_test_header + "        run: cargo test --locked --all-targets",
        "      - \"if\": ${{ false }}\n        name: Test all Rust targets against the committed lockfile\n        run: cargo test --locked --all-targets",
        "workflow-cargo-condition",
    )
    browser_header = "      - name: Check real browser stream and recovery contracts\n"
    add(
        "step-browser-merge-if",
        browser_header + "        run:",
        browser_header + "        <<: {\"if\": false}\n        run:",
        "workflow-browser-contract",
    )
    add(
        "step-browser-quoted-continue",
        browser_header + "        run:",
        browser_header + "        \"continue-on-error\": true\n        run:",
        "workflow-browser-contract",
    )
    add(
        "step-browser-custom-noop-shell",
        browser_header + "        run:",
        browser_header + "        shell: bash -c 'exit 0' {0}\n        run:",
        "workflow-browser-contract",
    )
    add(
        "step-cargo-custom-noop-shell",
        cargo_test_header + "        run:",
        cargo_test_header + "        shell: bash -c 'exit 0' {0}\n        run:",
        "workflow-cargo-contract",
    )
    add(
        "step-unknown-field",
        "      - name: Record actual tool versions\n        run: |",
        "      - name: Record actual tool versions\n        timeout-minutes: 1\n        run: |",
        "workflow-step-contract",
    )
    add(
        "early-workflow-check-if-false",
        "      - name: Check bootstrap workflow contract\n        run:",
        "      - name: Check bootstrap workflow contract\n        if: ${{ false }}\n        run:",
        "workflow-public-contract",
    )
    add(
        "early-hygiene-selftest-continue",
        "      - name: Prove public hygiene guard mutations fail\n        run:",
        "      - name: Prove public hygiene guard mutations fail\n        continue-on-error: true\n        run:",
        "workflow-public-contract",
    )
    add(
        "early-controls-check-if-false",
        "      - name: Check controls workflow document\n        run:",
        "      - name: Check controls workflow document\n        if: ${{ false }}\n        run:",
        "workflow-public-contract",
    )
    add(
        "setup-python-if-false",
        "      - name: Select stable Python 3.14\n        uses:",
        "      - name: Select stable Python 3.14\n        if: ${{ false }}\n        uses:",
        "workflow-action-contract",
    )
    add(
        "checkout-continue-on-error",
        "      - name: Check out the triggering revision\n        uses:",
        "      - name: Check out the triggering revision\n        continue-on-error: true\n        uses:",
        "workflow-action-contract",
    )
    rustup_block = _step_block(healthy, "Install stable Rust components")
    versions_block = _step_block(healthy, "Record actual tool versions")
    checkout_block = _step_block(healthy, "Check out the triggering revision")
    setup_block = _step_block(healthy, "Select stable Python 3.14")
    fmt_block = _step_block(healthy, "Check Rust formatting")
    add(
        "rustup-if-false",
        "      - name: Install stable Rust components\n        run:",
        "      - name: Install stable Rust components\n        if: ${{ false }}\n        run:",
        "workflow-bootstrap-contract",
    )
    add(
        "rustup-continue-on-error",
        "      - name: Install stable Rust components\n        run:",
        "      - name: Install stable Rust components\n        continue-on-error: true\n        run:",
        "workflow-bootstrap-contract",
    )
    cases.append(("rustup-removed", healthy.replace(rustup_block, "", 1), "workflow-bootstrap-contract"))
    add("rustup-clippy-removed", RUSTUP_COMMAND, "rustup toolchain install stable --profile minimal --component rustfmt", "workflow-bootstrap-contract")
    cases.append(("versions-removed", healthy.replace(versions_block, "", 1), "workflow-bootstrap-contract"))
    cases.append(("checkout-setup-swapped", _replace_once(healthy, checkout_block + setup_block, setup_block + checkout_block), "workflow-action-contract"))
    without_checkout = healthy.replace(checkout_block, "", 1)
    cases.append((
        "checkout-moved-after-early-guards",
        _replace_once(without_checkout, fmt_block, checkout_block + fmt_block),
        "workflow-action-contract",
    ))
    without_setup = healthy.replace(setup_block, "", 1)
    cases.append((
        "setup-moved-after-early-guards",
        _replace_once(without_setup, fmt_block, setup_block + fmt_block),
        "workflow-action-contract",
    ))
    add(
        "versions-quoted-if",
        "      - name: Record actual tool versions\n        run:",
        "      - name: Record actual tool versions\n        \"if\": ${{ false }}\n        run:",
        "workflow-bootstrap-contract",
    )
    cases.append((
        "bootstrap-steps-swapped",
        _replace_once(healthy, rustup_block + versions_block, versions_block + rustup_block),
        "workflow-bootstrap-contract",
    ))
    cases.append((
        "bootstrap-duplicate-rustup",
        _replace_once(healthy, rustup_block, rustup_block + rustup_block),
        "workflow-bootstrap-contract",
    ))
    add(
        "bootstrap-custom-noop-shell",
        "      - name: Install stable Rust components\n        run:",
        "      - name: Install stable Rust components\n        shell: bash -c 'exit 0' {0}\n        run:",
        "workflow-bootstrap-contract",
    )
    add(
        "shell-on-action-step",
        "      - name: Check out the triggering revision\n        uses:",
        "      - name: Check out the triggering revision\n        shell: bash\n        uses:",
        "workflow-step-contract",
    )
    trigger_code = "workflow-rust-trigger-contract"
    add("trigger-remove-pull-request", "  pull_request:\n", "", trigger_code)
    add("trigger-push-staging-only", "      - main\n", "      - staging\n", trigger_code)
    add("trigger-remove-push", "  push:\n    branches:\n      - main\n", "", trigger_code)
    add("trigger-remove-dispatch", "  workflow_dispatch:\n", "", trigger_code)
    add("trigger-pr-path-limit", "  pull_request:\n", "  pull_request:\n    paths:\n      - README.md\n", trigger_code)
    add("trigger-pr-branch-limit", "  pull_request:\n", "  pull_request:\n    branches:\n      - main\n", trigger_code)
    add("trigger-extra-schedule", "  workflow_dispatch:\n", "  workflow_dispatch:\n  schedule:\n    - cron: '0 0 * * *'\n", trigger_code)
    add("trigger-push-extra-branch", "      - main\n", "      - main\n      - staging\n", trigger_code)
    add("trigger-extra-release", "  workflow_dispatch:\n", "  release:\n    types:\n      - published\n  workflow_dispatch:\n", trigger_code)
    add("trigger-duplicate-pull-request", "  pull_request:\n", "  pull_request:\n  pull_request:\n", trigger_code)
    add("trigger-push-tags", "    branches:\n      - main\n", "    branches:\n      - main\n    tags:\n      - v1.0.0\n", trigger_code)
    add("trigger-push-paths", "    branches:\n      - main\n", "    branches:\n      - main\n    paths:\n      - '*.rs'\n", trigger_code)
    add("trigger-duplicate-push-branches", "    branches:\n      - main\n", "    branches:\n      - main\n    branches:\n      - main\n", trigger_code)
    add("trigger-pr-types", "  pull_request:\n", "  pull_request:\n    types:\n      - opened\n", trigger_code)
    add("trigger-dispatch-inputs", "  workflow_dispatch:\n\npermissions:", "  workflow_dispatch:\n    inputs:\n      reason:\n        required: false\n\npermissions:", trigger_code)
    on_block = "on:\n  pull_request:\n  push:\n    branches:\n      - main\n  workflow_dispatch:\n"
    add("trigger-duplicate-top-level-on", on_block, on_block + "\n" + on_block, trigger_code)
    add("trigger-missing-on", on_block, "", trigger_code)
    cases.extend([
        (
            "global-default-noop-shell",
            healthy + "\ndefaults:\n  run:\n    shell: bash -c 'exit 0' {0}\n",
            "workflow-default-shell",
        ),
        (
            "global-default-bash-shell",
            healthy + "\ndefaults:\n  run:\n    shell: bash\n",
            "workflow-default-shell",
        ),
        (
            "global-default-inline-mapping",
            healthy + '\n"defaults": {"run": {"shell": "bash"}}\n',
            "workflow-default-shell",
        ),
        (
            "permissions-duplicate-write",
            healthy + "\npermissions:\n  contents: write\n",
            "workflow-permissions",
        ),
        (
            "permissions-duplicate-read",
            healthy + "\npermissions:\n  contents: read\n",
            "workflow-permissions",
        ),
    ])
    add("trigger-pr-direct-event-sequence", "  pull_request:\n", "  pull_request:\n      - opened\n", trigger_code)
    cases.append((
        "global-default-spaced-key",
        healthy + "\ndefaults :\n  run:\n    shell: bash -c 'exit 0' {0}\n",
        "workflow-default-shell",
    ))

    for suffix, entry in (
        ("double-quoted", '  "actions": write'),
        ("single-quoted", "  'actions': write"),
        ("space-before-colon", "  actions : write"),
    ):
        cases.append((
            f"permissions-actions-write-{suffix}",
            _replace_once(
                healthy,
                "permissions:\n  contents: read\n",
                "permissions:\n  contents: read\n" + entry + "\n",
            ),
            "workflow-permissions",
        ))
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
    browser_title = "Check real browser stream and recovery contracts"
    browser_block = _step_block(healthy, browser_title)
    cases.append(("missing-browser-phase", healthy.replace(browser_block, "", 1), "workflow-browser-contract"))
    cases.append(("browser-missing-required-flag", _replace_once(healthy, browser_block, _replace_once(browser_block, " --require-browser", "")), "workflow-browser-contract"))
    cases.append((
        "browser-continue-on-error",
        _replace_once(
            healthy,
            f"      - name: {browser_title}\n        run:",
            f"      - name: {browser_title}\n        continue-on-error: true\n        run:",
        ),
        "workflow-browser-contract",
    ))
    cases.append((
        "browser-order-reversed",
        healthy.replace(blocks["persistence"] + browser_block, browser_block + blocks["persistence"], 1),
        "workflow-browser-contract",
    ))
    cases.append((
        "job-condition-false",
        _replace_once(healthy, "  rust:\n", "  rust:\n    if: ${{ false }}\n"),
        "workflow-job-contract",
    ))
    cases.append((
        "job-pr-condition",
        _replace_once(healthy, "  rust:\n", "  rust:\n    if: ${{ github.event_name != 'pull_request' }}\n"),
        "workflow-job-contract",
    ))
    cases.append((
        "job-skipped-dependency",
        _replace_once(
            healthy,
            "  rust:\n",
            "  disabled-prerequisite:\n"
            "    runs-on: ubuntu-24.04\n"
            "    if: ${{ false }}\n"
            "    steps:\n"
            "      - run: \"true\"\n"
            "  rust:\n"
            "    needs: disabled-prerequisite\n",
        ),
        "workflow-job-contract",
    ))
    cases.append((
        "job-quoted-if-key",
        _replace_once(healthy, "    name: Stable Rust, public hygiene, and planning guards\n", "    name: Stable Rust, public hygiene, and planning guards\n    \"if\": ${{ false }}\n"),
        "workflow-job-contract",
    ))
    cases.append((
        "job-merge-metadata",
        _replace_once(healthy, "  rust:\n", "  rust:\n    <<: {\"if\": false}\n"),
        "workflow-job-contract",
    ))
    cases.append((
        "job-matrix-metadata",
        _replace_once(healthy, "  rust:\n", "  rust:\n    strategy:\n      matrix:\n        runner: [ubuntu-24.04]\n"),
        "workflow-job-contract",
    ))
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


def _controls_fixtures(healthy: str) -> list[dict[str, object]]:
    def case(name: str, document: str, code: str | None, detail: str | None) -> dict[str, object]:
        return {
            "name": name,
            "document": document,
            "expected_exit": 1 if code is not None else 0,
            "expected_detail": detail,
            "expected_code": code,
        }

    fixtures = [case("controls-healthy", healthy, None, None)]
    healthy_comments = _replace_once(healthy, "jobs:\n", "jobs:\n  # helper:\n")
    healthy_comments = _replace_once(
        healthy_comments,
        "  contents: read",
        "  contents: read\n# a root comment does not end permissions or jobs",
    )
    healthy_comments = _replace_once(
        healthy_comments,
        "  push:\n",
        "# a root comment does not end the on block\n  push:\n",
    )
    fixtures.append(case("controls-healthy-comments", healthy_comments, None, None))
    controls_version_step = "      - name: Record actual Python version\n        run: python3 --version\n"
    fixtures.append(case(
        "controls-healthy-simple-bash-shell",
        _replace_once(healthy, controls_version_step, "      - name: Record actual Python version\n        shell: bash\n        run: python3 --version\n"),
        None,
        None,
    ))
    fixtures.append(case(
        "controls-healthy-simple-sh-shell",
        _replace_once(healthy, controls_version_step, "      - name: Record actual Python version\n        shell: sh\n        run: python3 --version\n"),
        None,
        None,
    ))

    def add(name: str, old: str, new: str, code: str, detail: str | None = None) -> None:
        fixtures.append(case(name, _replace_once(healthy, old, new), code, detail))

    add("controls-job-if-false", "  controls:\n", "  controls:\n    if: ${{ false }}\n", "workflow-job-contract", "conditional/dependent if")
    add(
        "controls-skipped-dependency",
        "  controls:\n",
        "  disabled-prerequisite:\n"
        "    runs-on: ubuntu-24.04\n"
        "    if: ${{ false }}\n"
        "    steps:\n"
        "      - run: \"true\"\n"
        "  controls:\n"
        "    needs: disabled-prerequisite\n",
        "workflow-job-contract",
        "conditional/dependent needs",
    )
    add(
        "controls-quoted-job-if",
        "    name: Workflow and public hygiene self-tests\n",
        "    name: Workflow and public hygiene self-tests\n    \"if\": ${{ false }}\n",
        "workflow-job-contract",
        "quoted and merge forms",
    )
    add(
        "controls-custom-noop-shell",
        "      - name: Prove public hygiene mutations fail\n        run: python3 -B scripts/check_public_hygiene.py --self-test\n",
        "      - name: Prove public hygiene mutations fail\n        shell: bash -c 'exit 0' {0}\n        run: python3 -B scripts/check_public_hygiene.py --self-test\n",
        "workflow-step-contract",
        "shell",
    )

    def remove_trigger_path(trigger: str, relative_path: str) -> str:
        before, marker, after = healthy.partition(f"  {trigger}:\n")
        item = f"      - {relative_path}\n"
        if not marker or item not in after:
            raise RuntimeError("controls trigger fixture did not match")
        return before + after.replace(item, "", 1)

    def extra_trigger_path(trigger: str) -> str:
        before, marker, after = healthy.partition(f"  {trigger}:\n")
        if not marker:
            raise RuntimeError("controls trigger fixture did not match")
        return before + after.replace("    paths:\n", "    paths:\n      - src/lib.rs\n", 1)

    for trigger in ("pull_request", "push"):
        for path_name, relative_path in zip(("rust", "controls", "scanner", "hygiene"), CONTROL_PATHS):
            fixtures.append(case(
                f"controls-remove-{trigger}-{path_name}-path",
                remove_trigger_path(trigger, relative_path),
                "workflow-controls-contract",
                "four required control paths",
            ))
        fixtures.append(case(
            f"controls-extra-{trigger}-path",
            extra_trigger_path(trigger),
            "workflow-controls-contract",
            "four required control paths",
        ))

    pull_request_block = "  pull_request:\n    paths:\n" + "".join(
        f"      - {path}\n" for path in CONTROL_PATHS
    )
    push_block = "  push:\n    branches:\n      - main\n    paths:\n" + "".join(
        f"      - {path}\n" for path in CONTROL_PATHS
    )
    without_pr = healthy.replace(pull_request_block, "", 1)
    fixtures.append(case("controls-remove-pull-request-trigger", without_pr, "workflow-controls-contract", "pull_request must"))
    fixtures.append(case("controls-remove-push-trigger", healthy.replace(push_block, "", 1), "workflow-controls-contract", "push"))
    fixtures.append(case(
        "controls-remove-workflow-dispatch",
        healthy.replace("  workflow_dispatch:\n", "", 1),
        "workflow-controls-contract",
        "exactly pull_request, push, and workflow_dispatch",
    ))
    add(
        "controls-add-pull-request-branch-filter",
        "  pull_request:\n",
        "  pull_request:\n    branches:\n      - main\n",
        "workflow-controls-contract",
        "unsupported controls trigger metadata",
    )
    add(
        "controls-extra-trigger",
        "  workflow_dispatch:\n",
        "  workflow_dispatch:\n  schedule:\n    - cron: '0 0 * * *'\n",
        "workflow-controls-contract",
        "exactly pull_request, push, and workflow_dispatch",
    )
    fake_root_trigger = without_pr + "pull_request:\n    paths:\n" + "".join(
        f"      - {path}\n" for path in CONTROL_PATHS
    )
    fixtures.append(case("controls-fake-root-pull-request", fake_root_trigger, "workflow-controls-contract", "pull_request must"))
    add("controls-remove-push-main", "      - main\n", "      - staging\n", "workflow-controls-contract", "exactly the main branch")
    add(
        "controls-remove-validation-step",
        "      - name: Check controls workflow document\n        run: python3 -B scripts/check_rust_workflow.py check-controls-workflow --workflow .github/workflows/workflow-controls.yml\n",
        "",
        "workflow-controls-contract",
        "required self-check invocation",
    )
    add(
        "controls-continue-guard",
        "      - name: Prove workflow contract mutations fail\n        run: python3 -B scripts/check_rust_workflow.py --self-test\n",
        "      - name: Prove workflow contract mutations fail\n        continue-on-error: true\n        run: python3 -B scripts/check_rust_workflow.py --self-test\n",
        "workflow-controls-contract",
        "unconditional and propagate failure",
    )
    add(
        "controls-setup-condition",
        "      - name: Select stable Python 3.14\n        uses: actions/setup-python@",
        "      - name: Select stable Python 3.14\n        if: ${{ false }}\n        uses: actions/setup-python@",
        "workflow-action-contract",
        "unconditional and propagate failure",
    )
    add(
        "controls-checkout-continue-on-error",
        "      - name: Check out the triggering revision\n        uses: actions/checkout@",
        "      - name: Check out the triggering revision\n        continue-on-error: true\n        uses: actions/checkout@",
        "workflow-action-contract",
        "unconditional and propagate failure",
    )
    add("controls-floating-checkout", CHECKOUT, "actions/checkout@main", "workflow-action-pin", "full commit SHA")
    add(
        "controls-inline-quoted-step-if",
        "      - name: Prove workflow contract mutations fail\n        run: python3 -B scripts/check_rust_workflow.py --self-test",
        "      - \"if\": ${{ false }}\n        name: Prove workflow contract mutations fail\n        run: python3 -B scripts/check_rust_workflow.py --self-test",
        "workflow-controls-contract",
        "unconditional and propagate failure",
    )
    add(
        "controls-unknown-step-field",
        "      - name: Check controls workflow document\n        run:",
        "      - name: Check controls workflow document\n        timeout-minutes: 1\n        run:",
        "workflow-step-contract",
        "unsupported step metadata timeout-minutes",
    )
    add(
        "controls-selfcheck-condition",
        "      - name: Check controls workflow document\n        run:",
        "      - name: Check controls workflow document\n        if: ${{ false }}\n        run:",
        "workflow-controls-contract",
        "unconditional and propagate failure",
    )
    add(
        "controls-quoted-checkout-continue",
        "      - name: Check out the triggering revision\n        uses:",
        "      - name: Check out the triggering revision\n        \"continue-on-error\": true\n        uses:",
        "workflow-action-contract",
        "unconditional and propagate failure",
    )
    controls_selfcheck = "        run: python3 -B scripts/check_rust_workflow.py check-controls-workflow --workflow .github/workflows/workflow-controls.yml"
    add(
        "controls-comment-job-if",
        controls_selfcheck,
        controls_selfcheck + "\n# comments do not end a YAML mapping\n    if: ${{ false }}",
        "workflow-job-contract",
        "conditional/dependent if",
    )
    add(
        "controls-comment-permissions-write",
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n# comments do not end a YAML mapping\n  actions: write",
        "workflow-permissions",
        "read-only",
    )
    reordered = _replace_once(
        healthy,
        "        run: python3 -B scripts/check_rust_workflow.py --workflow .github/workflows/rust.yml",
        "        run: python3 -B scripts/check_rust_workflow.py __ORDER_PROBE__",
    )
    reordered = _replace_once(
        reordered,
        "        run: python3 -B scripts/check_rust_workflow.py --self-test",
        "        run: python3 -B scripts/check_rust_workflow.py --workflow .github/workflows/rust.yml",
    )
    reordered = _replace_once(
        reordered,
        "        run: python3 -B scripts/check_rust_workflow.py __ORDER_PROBE__",
        "        run: python3 -B scripts/check_rust_workflow.py --self-test",
    )
    fixtures.append(case("controls-reordered-validation-steps", reordered, "workflow-controls-contract", "command sequence"))
    checkout_block = _step_block(healthy, "Check out the triggering revision")
    setup_block = _step_block(healthy, "Select stable Python 3.14")
    selfcheck_block = _step_block(healthy, "Check controls workflow document")
    fixtures.append(case(
        "controls-checkout-setup-swapped",
        _replace_once(healthy, checkout_block + setup_block, setup_block + checkout_block),
        "workflow-action-contract",
        "precede every run step",
    ))
    without_checkout = healthy.replace(checkout_block, "", 1)
    fixtures.append(case(
        "controls-checkout-moved-to-end",
        _replace_once(without_checkout, selfcheck_block, selfcheck_block + checkout_block),
        "workflow-action-contract",
        "precede every run step",
    ))
    without_setup = healthy.replace(setup_block, "", 1)
    fixtures.append(case(
        "controls-setup-moved-to-end",
        _replace_once(without_setup, selfcheck_block, selfcheck_block + setup_block),
        "workflow-action-contract",
        "precede every run step",
    ))
    fixtures.append(case(
        "controls-global-default-noop-shell",
        healthy + "\ndefaults:\n  run:\n    shell: true {0}\n",
        "workflow-default-shell",
        "top-level defaults",
    ))
    fixtures.append(case(
        "controls-permissions-duplicate-read",
        healthy + "\npermissions:\n  contents: read\n",
        "workflow-permissions",
        "duplicate top-level permissions",
    ))
    fixtures.append(case(
        "controls-permissions-spaced-duplicate",
        healthy + '\n"permissions" : {"contents": "write"}\n',
        "workflow-permissions",
        "duplicate top-level permissions",
    ))

    for suffix, entry in (
        ("double-quoted", '  "actions": write'),
        ("single-quoted", "  'actions': write"),
        ("space-before-colon", "  actions : write"),
    ):
        fixtures.append(case(
            f"controls-permissions-actions-write-{suffix}",
            _replace_once(
                healthy,
                "permissions:\n  contents: read\n",
                "permissions:\n  contents: read\n" + entry + "\n",
            ),
            "workflow-permissions",
            "read-only",
        ))
    return fixtures


def _controls_self_test(script: Path, workflow: Path, root: Path) -> int:
    if not workflow.exists():
        print("Controls self-test failed: [workflow-read] missing controls document", file=sys.stderr)
        return 1
    healthy = _read_workflow(workflow)
    fixtures = _controls_fixtures(healthy)
    controls_directory = root / ".github" / "workflows"
    controls_directory.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    passed = 0
    rejected = 0
    for case in fixtures:
        name = case["name"]
        document = case["document"]
        expected_exit = case["expected_exit"]
        expected_detail = case["expected_detail"]
        path = root / f"{name}.yml"
        path.write_text(document, encoding="utf-8")
        completed = _run_cli([
            sys.executable,
            "-B",
            str(script),
            "check-controls-workflow",
            "--workflow",
            str(path),
        ])
        output = completed.stdout + completed.stderr
        expected_code = case["expected_code"]
        passed_case = completed.returncode == expected_exit
        if expected_detail is not None and expected_exit != 0:
            passed_case = passed_case and expected_detail in output
        if expected_code is not None and expected_exit != 0:
            passed_case = passed_case and f"[{expected_code}]" in output
        if expected_exit == 0 and passed_case:
            passed += 1
        elif passed_case:
            rejected += 1
        else:
            failures.append(name)
        print(f"{'PASS' if passed_case else 'FAIL'} controls-validation {name}: expected={expected_exit} actual={completed.returncode} code={expected_code or 'healthy'}")
    if failures:
        print("Controls self-test failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"Controls document self-test passed: {passed} healthy document and {rejected} rejected mutations")
    return 0


def _static_self_test(script: Path, workflow: Path, root: Path) -> tuple[int, list[dict[str, object]]]:
    healthy = _read_workflow(workflow)
    column_zero_comments = _replace_once(
        healthy,
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n# a root comment does not end permissions",
    )
    column_zero_comments = _replace_once(
        column_zero_comments,
        "    runs-on: ubuntu-24.04",
        "# a root comment does not end jobs\n    runs-on: ubuntu-24.04",
    )
    literal_job_text = _replace_once(
        healthy,
        "      - name: Check Rust formatting\n",
        "      - name: Record harmless literal step text\n"
        "        run: |\n"
        "          printf \"%s\\n\" \"    if: not-job-metadata\" \"  helper: not-a-job\"\n\n"
        "      - name: Check Rust formatting\n",
    )
    version_header = "      - name: Record actual tool versions\n        run: |"
    healthy_bash_versions = _replace_once(healthy, version_header, "      - name: Record actual tool versions\n        shell: bash\n        run: |")
    healthy_sh_versions = _replace_once(healthy, version_header, "      - name: Record actual tool versions\n        shell: sh\n        run: |")
    healthy_bash_cargo = _replace_once(
        healthy,
        "      - name: Test all Rust targets against the committed lockfile\n        run:",
        "      - name: Test all Rust targets against the committed lockfile\n        shell: bash\n        run:",
    )
    healthy_quoted_shells = _replace_once(
        healthy,
        "      - name: Install stable Rust components\n        run:",
        "      - shell: \"bash\"\n        name: Install stable Rust components\n        run:",
    )
    healthy_quoted_shells = _replace_once(
        healthy_quoted_shells,
        version_header,
        "      - name: Record actual tool versions\n        shell: 'sh'\n        run: |",
    )
    fixtures = [
        ("healthy-workflow", healthy, 0, None),
        ("healthy-trigger-comment", _replace_once(healthy, "on:\n", "on:\n  # Keep the required native PR, main, and manual triggers.\n"), 0, None),
        (
            "healthy-trigger-whitespace-and-root-comment",
            _replace_once(
                _replace_once(healthy, "on:\n", "on:\n\n"),
                "  workflow_dispatch:\n\npermissions:",
                "  workflow_dispatch:\n# schedule: comment only, not a trigger\n\npermissions:",
            ),
            0,
            None,
        ),
        ("healthy-job-comment", _replace_once(healthy, "  rust:\n", "  rust:\n    # if: ${{ false }}\n"), 0, None),
        ("healthy-jobs-list-comment-colon", _replace_once(healthy, "jobs:\n", "jobs:\n  # if:\n"), 0, None),
        ("healthy-jobs-list-helper-comment-colon", _replace_once(healthy, "jobs:\n", "jobs:\n  # helper:\n"), 0, None),
        ("healthy-column-zero-comments", column_zero_comments, 0, None),
        ("healthy-terminal-comment", healthy + "# harmless terminal comment\n", 0, None),
        (
            "healthy-inline-run",
            _replace_once(
                healthy,
                "      - name: Check Rust formatting\n        run: cargo fmt --check",
                "      - run: cargo fmt --check\n        name: Check Rust formatting",
            ),
            0,
            None,
        ),
        (
            "healthy-nested-env-if-name",
            _replace_once(healthy, "      CARGO_TERM_COLOR: never", "      CARGO_TERM_COLOR: never\n      if: nested-env-data-not-job-condition"),
            0,
            None,
        ),
        ("healthy-step-literal-job-looking-text", literal_job_text, 0, None),
        ("healthy-simple-bash-shell-noncargo", healthy_bash_versions, 0, None),
        ("healthy-simple-sh-shell-noncargo", healthy_sh_versions, 0, None),
        ("healthy-simple-bash-shell-cargo", healthy_bash_cargo, 0, None),
        ("healthy-inline-and-quoted-shells", healthy_quoted_shells, 0, None),
    ]
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
        "missing-browser-phase": "--require-browser",
        "browser-missing-required-flag": "--require-browser",
        "browser-continue-on-error": "unconditional",
        "browser-order-reversed": "immediately after persistence",
        "job-condition-false": "cannot use conditional/dependent if",
        "job-pr-condition": "cannot use conditional/dependent if",
        "job-skipped-dependency": "cannot use conditional/dependent needs",
        "job-quoted-if-key": "quoted and merge forms",
        "job-merge-metadata": "quoted and merge forms",
        "job-matrix-metadata": "unexpected root job metadata",
        "missing-plan-guard": "public",
        "comment-job-if": "conditional/dependent if",
        "comment-job-needs-helper": "conditional/dependent needs",
        "comment-permissions-write": "read-only",
        "comment-last-step-if": "public validators must be unconditional",
        "step-cargo-quoted-if": "has a condition",
        "step-cargo-inline-quoted-if": "has a condition",
        "step-browser-merge-if": "cannot hide the browser phase",
        "step-browser-quoted-continue": "unconditional",
        "step-browser-custom-noop-shell": "cannot hide the browser phase",
        "step-cargo-custom-noop-shell": "cannot hide the Cargo command",
        "step-unknown-field": "unsupported step metadata timeout-minutes",
        "early-workflow-check-if-false": "workflow and hygiene self-tests",
        "early-hygiene-selftest-continue": "workflow and hygiene self-tests",
        "early-controls-check-if-false": "workflow and hygiene self-tests",
        "setup-python-if-false": "unconditional and propagate failure",
        "checkout-continue-on-error": "unconditional and propagate failure",
        "rustup-if-false": "must be unconditional and propagate failure",
        "rustup-continue-on-error": "must be unconditional and propagate failure",
        "rustup-removed": "stable Rust setup must appear exactly once",
        "rustup-clippy-removed": "stable Rust setup must appear exactly once",
        "versions-removed": "exact tool version recording must appear exactly once",
        "checkout-setup-swapped": "precede every run step",
        "checkout-moved-after-early-guards": "precede every run step",
        "setup-moved-after-early-guards": "precede every run step",
        "versions-quoted-if": "must be unconditional and propagate failure",
        "bootstrap-steps-swapped": "ordered version recording",
        "bootstrap-duplicate-rustup": "stable Rust setup must appear exactly once",
        "bootstrap-custom-noop-shell": "cannot hide stable Rust setup",
        "shell-on-action-step": "only on run steps",
        "trigger-remove-pull-request": "exactly pull_request",
        "trigger-remove-push": "exactly pull_request",
        "trigger-remove-dispatch": "exactly pull_request",
        "trigger-extra-schedule": "exactly pull_request",
        "trigger-extra-release": "exactly pull_request",
        "trigger-duplicate-pull-request": "exactly pull_request",
        "trigger-push-staging-only": "exactly the main branch",
        "trigger-push-extra-branch": "exactly the main branch",
        "trigger-duplicate-push-branches": "exactly the main branch",
        "trigger-pr-path-limit": "metadata paths",
        "trigger-pr-branch-limit": "metadata branches",
        "trigger-pr-types": "metadata types",
        "trigger-push-tags": "metadata tags",
        "trigger-push-paths": "metadata paths",
        "trigger-dispatch-inputs": "metadata inputs",
        "trigger-duplicate-top-level-on": "exactly one top-level on block",
        "trigger-missing-on": "exactly one top-level on block",
        "global-default-noop-shell": "top-level defaults",
        "global-default-bash-shell": "top-level defaults",
        "global-default-inline-mapping": "top-level defaults",
        "global-default-spaced-key": "top-level defaults",
        "permissions-duplicate-write": "duplicate top-level permissions",
        "permissions-duplicate-read": "duplicate top-level permissions",
        "permissions-actions-write-double-quoted": "read-only",
        "permissions-actions-write-single-quoted": "read-only",
        "permissions-actions-write-space-before-colon": "read-only",
        "trigger-pr-direct-event-sequence": "unsupported Rust trigger structure",
    }
    expected_auxiliary_codes = {
        "step-cargo-custom-noop-shell": ["workflow-step-contract"],
        "step-browser-custom-noop-shell": ["workflow-step-contract"],
        "bootstrap-custom-noop-shell": ["workflow-step-contract"],
    }
    for name, text, code in _mutations(healthy):
        fixtures.append((name, text, 1, code))
    results: list[dict[str, object]] = []
    for name, text, expected, code in fixtures:
        path = root / f"{name}.yml"
        path.write_text(text, encoding="utf-8")
        completed = _run_cli([sys.executable, "-B", str(script), "--workflow", str(path)])
        passed, record = _case_result(name, expected, code, expected_details.get(name), completed)
        auxiliary_codes = expected_auxiliary_codes.get(name, [])
        if auxiliary_codes:
            output = completed.stdout + completed.stderr
            observed = {auxiliary: f"[{auxiliary}]" in output for auxiliary in auxiliary_codes}
            passed = passed and all(observed.values())
            record["auxiliary_codes_observed"] = observed
            record["passed"] = passed
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
        record["passed"] = passed
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
    if not check("runtime-padded-zero-status", healthy_out, healthy_err, "000", 0, None):
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
    for name, status in (
        ("runtime-negative-status", "-1"),
        ("runtime-negative-seven-status", "-7"),
        ("runtime-negative-boundary-status", "-255"),
        ("runtime-negative-zero-status", "-0"),
        ("runtime-negative-zero-padded-status", "-000"),
    ):
        if not check(name, healthy_out, healthy_err, status, 2, "workflow-input", "non-negative integer", forbid_status_echo=True):
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
            controls_status = _controls_self_test(script, Path(__file__).resolve().parents[1] / ".github/workflows/workflow-controls.yml", root)
        results = static_results + runtime_results
        for record in results:
            state = "PASS" if record["passed"] else "FAIL"
            print(f"{state} {record['kind']} {record['name']} expected={record['expected_exit']} actual={record['actual_exit']}")
        if static_status != 0 or runtime_status != 0 or controls_status != 0:
            print("Runtime-output self-test failed", file=sys.stderr)
            return 1
        healthy_workflows = sum(record["kind"] == "healthy-workflow" for record in static_results)
        workflow_rejections = sum(record["kind"] == "workflow-mutation" for record in static_results)
        bad_inputs = sum(record["kind"] == "bad-input" for record in static_results)
        runtime_rejections = sum(record["actual_exit"] != 0 for record in runtime_results)
        healthy_outputs = sum(record["actual_exit"] == 0 for record in runtime_results)
        print(
            f"Runtime-output self-test passed: {healthy_workflows} healthy workflows, {workflow_rejections} rejected workflow mutations, "
            f"{bad_inputs} rejected read errors, {healthy_outputs} healthy output cases, {runtime_rejections} rejected output cases"
        )
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        print(f"Runtime-output self-test harness failed: {type(error).__name__}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["check-process-output", "check-controls-workflow"])
    parser.add_argument("--workflow", type=Path, default=Path(__file__).resolve().parents[1] / ".github/workflows/rust.yml")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--stdout", type=Path)
    parser.add_argument("--stderr", type=Path)
    parser.add_argument("--probe-status")
    parser.add_argument("--probe", choices=["api", "persistence"])
    arguments = parser.parse_args(argv)
    if arguments.command == "check-controls-workflow":
        if any(value is not None for value in (arguments.stdout, arguments.stderr, arguments.probe_status, arguments.probe)):
            print("Controls workflow validation failed: [workflow-input] process-output arguments do not belong here", file=sys.stderr)
            return 2
        return check_controls_path(arguments.workflow)
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
