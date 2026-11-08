#!/usr/bin/env python3
# owner: paperclip-game maintainers
# trigger: Rust workflow and pre-push public artifact validation
# purpose: Check tracked and candidate public files without private source inputs.

"""Check public-path, language, whitespace, and generated-artifact violations.

This is a bounded UTF-8/public-file heuristic, not a comprehensive secret, capture,
private-hostname, or cross-platform path classifier.
"""

from __future__ import annotations

import re
from pathlib import Path
import subprocess
import sys

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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        candidates = candidate_files(root)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, UnicodeError) as error:
        print(f"Public hygiene validation failed: {error}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for relative in candidates:
        path = root / relative
        if error := artifact_error(relative):
            errors.append(f"{relative}: {error}")
            continue
        if CJK.search(relative):
            errors.append(f"{relative}: non-English CJK filename")
        if path.is_symlink() or not path.is_file():
            errors.append(f"{relative}: public candidate is not a regular readable file")
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{relative}: public candidate must be readable UTF-8 text")
            continue

        if CJK.search(text):
            errors.append(f"{relative}: non-English CJK content")
        if PRIVATE_PATH.search(text):
            errors.append(f"{relative}: private absolute path or file URL")
        if SECRET.search(text):
            errors.append(f"{relative}: credential-shaped content")
        for number, line in enumerate(text.split("\n"), start=1):
            if line.endswith((" ", "\t", "\r")):
                errors.append(f"{relative}:{number}: trailing whitespace")

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


if __name__ == "__main__":
    raise SystemExit(main())
