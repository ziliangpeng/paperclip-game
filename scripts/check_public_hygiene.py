#!/usr/bin/env python3
# owner: paperclip-game maintainers
# trigger: Rust workflow and pre-push public artifact validation
# purpose: Check tracked and candidate public files without private source inputs.

"""Check public-path, language, whitespace, and generated-artifact violations.

This is a bounded UTF-8/public-file heuristic, not a comprehensive secret, capture,
private-hostname, or cross-platform path classifier.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

CJK = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u31a0-\u31ff"
    r"\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af"
    r"\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef"
    r"\U00020000-\U0002FA1F]"
)
PRIVATE_PATH = re.compile(
    r"(?:/(?:Users|home)/[^/\s\"']+(?=$|[\s/\"'])|/tmp/(?:agents)/|file:(?://))",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9_-]{16,}|"
    r"[\"']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
    r"[\"']?\s*(?:=|:)\s*"
    r"(?:[\"'][^\"']+[\"']|[^\s,}\]()\\'\"][^\s,}\]()]*(?=$|[\s,}\]])))",
    re.IGNORECASE,
)
PRIVATE_INPUT_NAMES = {".env", "id_rsa", "id_ecdsa", "id_ed25519"}
PRIVATE_INPUT_SUFFIXES = {".pem", ".p12", ".pfx"}
DATABASE_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".sqlite3",
    ".sqlite3-journal",
    ".sqlite3-shm",
    ".sqlite3-wal",
)


def candidate_files(root: Path) -> list[str]:
    """List versioned files plus unignored candidates without walking outside the repo."""
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=root,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError("could not enumerate public repository files")
    return [
        item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def artifact_error(relative: str) -> str | None:
    path = Path(relative)
    lowered = path.name.lower()
    if any(part in {"target", "__pycache__"} for part in path.parts):
        return "generated build/cache directory must not be published"
    if lowered.endswith((".pyc", ".pyo") + DATABASE_SUFFIXES):
        return "generated database or bytecode artifact must not be published"
    if (
        lowered in PRIVATE_INPUT_NAMES
        or path.suffix.lower() in PRIVATE_INPUT_SUFFIXES
        or ".env." in lowered
        or lowered.endswith(".env")
    ):
        return "private input must not be published or read by this check"
    return None


def validate_repository(root: Path) -> int:
    try:
        candidates = candidate_files(root)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError) as error:
        print(f"Public hygiene validation failed: {error}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for relative in candidates:
        path = root / relative
        display_relative = "<credential-shaped path>" if SECRET.search(relative) else relative
        if error := artifact_error(relative):
            errors.append(f"{display_relative}: {error}")
            continue
        if CJK.search(relative):
            errors.append(f"{display_relative}: non-English CJK filename")
        if path.is_symlink() or not path.is_file():
            errors.append(f"{display_relative}: public candidate is not a regular readable file")
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{display_relative}: public candidate must be readable UTF-8 text")
            continue

        if CJK.search(text):
            errors.append(f"{display_relative}: non-English CJK content")
        if PRIVATE_PATH.search(text):
            errors.append(f"{display_relative}: private absolute path or file URL")
        if SECRET.search(text):
            errors.append(f"{display_relative}: credential-shaped content")
        for number, line in enumerate(text.split("\n"), start=1):
            if line.endswith((" ", "\t", "\r")):
                errors.append(f"{display_relative}:{number}: trailing whitespace")

    if errors:
        print("Public hygiene validation failed;", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print(f"{len(errors)} finding(s); offending values are not echoed", file=sys.stderr)
        return 1

    print(f"Public hygiene validation passed: {len(candidates)} candidate UTF-8 files")
    print("Scope: tracked and unignored candidates; CR/LF whitespace, CJK text/filenames, private paths, common credential shapes, and generated artifacts")
    print("Limits: bounded heuristics; no comprehensive secret/capture classification, private-host semantics, or Windows/UNC path detection")
    print("Private captures and optional private-source comparisons are not inputs")
    return 0


def _self_test_cases() -> list[dict[str, object]]:
    """Build benign and synthetic bad inputs without literal credential fixtures."""
    github_value = "gh" + "p_" + ("A" * 24)
    generic_name = "api" + "_key"
    generic_value = "synthetic-" + "credential-value"
    generic_shape = f'{generic_name} = "{generic_value}"\n'.encode()
    github_shape = (github_value + "\n").encode()
    private_path = "/" + "Users" + "/fixture"
    file_url = "file:" + "//fixture/private"
    private_bytes = b"\xff" + b"synthetic-private-input-canary"
    cjk_text = f"prefix {chr(0x4E2D)} suffix\n".encode()
    cjk_filename = f"note-{chr(0x4E2D)}.txt"
    return [
        {
            "name": "healthy-source-shapes",
            "relative": "healthy.py",
            "data": b"pattern = re.compile(value)\nconfigured = settings.get(\"public_mode\")\n",
            "diagnostic": None,
        },
        {
            "name": "cjk-content",
            "relative": "cjk.txt",
            "data": cjk_text,
            "diagnostic": "non-English CJK content",
        },
        {
            "name": "cjk-filename",
            "relative": cjk_filename,
            "data": b"ordinary text\n",
            "diagnostic": "non-English CJK filename",
        },
        {
            "name": "credential-shaped-filename-whitespace",
            "relative": "gh" + "p_" + ("A" * 24) + ".txt ",
            "data": b"placeholder " + bytes((10,)),
            "diagnostic": "trailing whitespace",
            "canary": "gh" + "p_" + ("A" * 24) + ".txt ",
        },
        {
            "name": "credential-shaped-filename-non-utf8",
            "relative": "gh" + "p_" + ("A" * 24) + ".txt",
            "data": b"\xff",
            "diagnostic": "public candidate must be readable UTF-8 text",
            "canary": "gh" + "p_" + ("A" * 24) + ".txt",
        },
        {
            "name": "private-path",
            "relative": "path.txt",
            "data": (private_path + "\n").encode(),
            "diagnostic": "private absolute path or file URL",
            "canary": private_path,
        },
        {
            "name": "file-url",
            "relative": "url.txt",
            "data": (file_url + "\n").encode(),
            "diagnostic": "private absolute path or file URL",
            "canary": file_url,
        },
        {
            "name": "github-credential-shape",
            "relative": "credential.txt",
            "data": github_shape,
            "diagnostic": "credential-shaped content",
            "canary": github_value,
        },
        {
            "name": "generic-credential-shape",
            "relative": "credential-config.txt",
            "data": generic_shape,
            "diagnostic": "credential-shaped content",
            "canary": generic_value,
        },
        {
            "name": "dot-env-before-decode",
            "relative": ".env",
            "data": private_bytes,
            "diagnostic": "private input must not be published or read by this check",
            "canary": "synthetic-private-input-canary",
        },
        {
            "name": "environment-file-before-decode",
            "relative": "config.env.production",
            "data": private_bytes,
            "diagnostic": "private input must not be published or read by this check",
            "canary": "synthetic-private-input-canary",
        },
        {
            "name": "database-artifact",
            "relative": "state.sqlite3-wal",
            "data": b"synthetic database placeholder\n",
            "diagnostic": "generated database or bytecode artifact must not be published",
        },
        {
            "name": "bytecode-artifact",
            "relative": "module.pyc",
            "data": b"\x00\xff",
            "diagnostic": "generated database or bytecode artifact must not be published",
        },
        {
            "name": "generated-directory",
            "relative": "target/output.txt",
            "data": b"synthetic build output\n",
            "diagnostic": "generated build/cache directory must not be published",
        },
        {
            "name": "crlf-whitespace",
            "relative": "crlf.txt",
            "data": b"first line\r\nsecond line\r\n",
            "diagnostic": "trailing whitespace",
        },
        {
            "name": "non-utf8",
            "relative": "binary.txt",
            "data": private_bytes,
            "diagnostic": "public candidate must be readable UTF-8 text",
            "canary": "synthetic-private-input-canary",
            "expect_relative_diagnostic": True,
        },
        {
            "name": "symbolic-link",
            "relative": "shortcut.txt",
            "link_target": "notes.txt",
            "diagnostic": "public candidate is not a regular readable file",
        },
    ]


def _fixture_run(arguments: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(root / "unused-home"),
        "XDG_CONFIG_HOME": str(root / "unused-config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        arguments,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )


def self_test(script: Path) -> int:
    """Run the actual CLI against isolated synthetic mini-Git repositories."""
    failures: list[str] = []
    healthy = 0
    rejected = 0
    try:
        source = script.read_bytes()
        cases = _self_test_cases()
        with tempfile.TemporaryDirectory(prefix="public-hygiene-self-test-") as temporary:
            base = Path(temporary)
            for case in cases:
                name = str(case["name"])
                root = base / name
                scripts = root / "scripts"
                scripts.mkdir(parents=True)
                fixture_script = scripts / script.name
                fixture_script.write_bytes(source)
                (root / "notes.txt").write_bytes(b"ordinary public text\n")
                relative = str(case["relative"])
                candidate = root / relative
                if "link_target" in case:
                    candidate.symlink_to(str(case["link_target"]))
                else:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.write_bytes(case["data"])
                initialized = _fixture_run(["git", "init", "--quiet"], root)
                staged = _fixture_run(["git", "add", "--all"], root) if initialized.returncode == 0 else initialized
                if initialized.returncode != 0 or staged.returncode != 0:
                    failures.append(f"{name}: mini-Git fixture setup failed")
                    continue
                completed = _fixture_run([sys.executable, "-B", str(fixture_script)], root)
                diagnostic = case["diagnostic"]
                expected_status = 0 if diagnostic is None else 1
                combined = completed.stdout + completed.stderr
                if completed.returncode != expected_status:
                    failures.append(f"{name}: expected exit {expected_status}, observed {completed.returncode}")
                    continue
                if diagnostic is not None and str(diagnostic) not in completed.stderr:
                    failures.append(f"{name}: expected diagnostic class was missing")
                    continue
                canary = case.get("canary")
                if canary is not None and str(canary) in combined:
                    failures.append(f"{name}: offending value was echoed")
                    continue
                if case.get("expect_relative_diagnostic") and relative not in completed.stderr:
                    failures.append(f"{name}: ordinary relative diagnostic path was missing")
                    continue
                if diagnostic is None:
                    healthy += 1
                else:
                    rejected += 1
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError, ValueError) as error:
        print(f"Public hygiene self-test harness failed: {type(error).__name__}", file=sys.stderr)
        return 2
    if failures:
        print("Public hygiene self-test failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Public hygiene self-test passed: {healthy} healthy fixture and {rejected} rejected synthetic cases through the real CLI")
    print("Synthetic fixtures are isolated mini-Git repositories; offending values are not echoed")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return validate_repository(Path(__file__).resolve().parents[1])
    if arguments == ["--self-test"]:
        return self_test(Path(__file__).resolve())
    print("Usage: check_public_hygiene.py [--self-test]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
