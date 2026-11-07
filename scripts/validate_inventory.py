#!/usr/bin/env python3
# owner: paperclip-game maintainers
# trigger: required gameplay-inventory verification
# purpose: validate stable feature IDs and source bindings against the official snapshot.

"""Validate the gameplay inventory without importing or executing official code."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse


ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
REQUIRED_SOURCE_FILENAMES = ("index2.html", "globals.js", "combat.js", "projects.js", "main.js")
PROJECT_COVERAGE_IDS = tuple(f"PRJ-{position:03d}" for position in range(1, 97))
PROJECT_PATTERN = re.compile(r"\bvar\s+(project\w+)\s*=\s*\{")
PROJECT_PUSH_PATTERN = re.compile(r"projects\.push\((project\w+)\)")
FUNCTION_PATTERN = re.compile(r"([A-Za-z_$][\w$]*)\((.*)\)")


def mask_javascript_non_code(source: str) -> str:
    """Mask comments and quoted content for structural matching, without executing JavaScript."""
    result = list(source)
    quote: str | None = None
    index = 0
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if quote is not None:
            if char not in "\r\n":
                result[index] = " "
            if char == "\\":
                if index + 1 < len(source):
                    if next_char not in "\r\n":
                        result[index + 1] = " "
                    index += 2
                else:
                    index += 1
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"`":
            quote = char
            result[index] = " "
            index += 1
            continue
        if char == "/" and next_char in ("/", "*"):
            line_comment = next_char == "/"
            result[index] = " "
            result[index + 1] = " "
            index += 2
            while index < len(source):
                char = source[index]
                next_char = source[index + 1] if index + 1 < len(source) else ""
                if line_comment and char in "\r\n":
                    break
                if char not in "\r\n":
                    result[index] = " "
                if not line_comment and char == "*" and next_char == "/":
                    result[index + 1] = " "
                    index += 2
                    break
                index += 1
            continue
        index += 1
    return "".join(result)


class InlineHandlerParser(HTMLParser):
    """Collect active inline handlers while ignoring handlers in HTML comments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.handlers: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for event, expression in attrs:
            if not event.lower().startswith("on"):
                continue
            match = FUNCTION_PATTERN.fullmatch(expression or "")
            arguments = []
            if match:
                raw_arguments = match.group(2).strip()
                arguments = [part.strip() for part in raw_arguments.split(",") if part.strip()]
            self.handlers.append(
                {
                    "tag": tag,
                    "dom_id": values.get("id"),
                    "event": event,
                    "function_name": match.group(1) if match else None,
                    "arguments": arguments,
                    "line": self.getpos()[0],
                }
            )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("The inventory root must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional private copy of the pinned public reference files for source comparison",
    )
    args = parser.parse_args()
    data = load_json(args.inventory)
    root = Path(__file__).resolve().parents[1]
    errors: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    features = data.get("features", [])
    exclusions = data.get("exclusions", [])
    bindings = data.get("source_bindings", {})
    project_bindings = bindings.get("projects", [])
    html_bindings = bindings.get("html_handlers", [])
    for label, rows in (("features", features), ("exclusions", exclusions)):
        if not isinstance(rows, list) or not rows:
            errors.append(f"{label} must be a non-empty array")
    for label, rows in (("projects", project_bindings), ("html_handlers", html_bindings)):
        if not isinstance(rows, list) or not rows:
            errors.append(f"source_bindings.{label} must be a non-empty array")

    def unique_index(label: str, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for position, row in enumerate(rows, 1):
            identifier = row.get("id")
            if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
                errors.append(f"{label}[{position}] has an invalid stable ID: {identifier!r}")
                continue
            if identifier in result:
                errors.append(f"Duplicate {label} ID: {identifier}")
            result[identifier] = row
        return result

    feature_index = unique_index("features", features)
    exclusion_index = unique_index("exclusions", exclusions)
    overlap = set(feature_index) & set(exclusion_index)
    if overlap:
        errors.append(f"Features and exclusions overlap: {sorted(overlap)}")
    targets = feature_index | exclusion_index

    document_cache: dict[Path, str] = {}
    for row in features + exclusions:
        identifier = row.get("id", "<missing>")
        document = row.get("document")
        if not isinstance(document, str) or not document.endswith(".md"):
            errors.append(f"{identifier} must reference a repository-relative Markdown document")
            continue
        relative = Path(document)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"{identifier} has an unsafe document path: {document}")
            continue
        document_path = root / relative
        if document not in document_cache:
            if not document_path.is_file():
                errors.append(f"Missing document for {identifier}: {document}")
                document_cache[document_path] = ""
            else:
                document_cache[document_path] = document_path.read_text(encoding="utf-8")
        text = document_cache[document_path]
        if not re.search(rf"(?<![A-Za-z0-9-]){re.escape(identifier)}(?![A-Za-z0-9-])", text):
            errors.append(f"{identifier} is absent from {document}")
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            errors.append(f"{identifier} has no human-readable name")
        if row in exclusions and (
            not isinstance(row.get("reason"), str) or not row["reason"].strip()
        ):
            errors.append(f"Exclusion {identifier} has no nonblank reason")

    snapshot = data.get("reference_snapshot", {})
    files = snapshot.get("files", [])
    file_names = [item.get("name") for item in files]
    if (
        len(files) != len(REQUIRED_SOURCE_FILENAMES)
        or set(file_names) != set(REQUIRED_SOURCE_FILENAMES)
        or len(file_names) != len(set(file_names))
    ):
        errors.append(
            "The reference snapshot must contain exactly these five unique files: "
            + ", ".join(REQUIRED_SOURCE_FILENAMES)
        )
    for item in files:
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
            errors.append(f"Invalid reference hash for {item.get('name')!r}")
        if urlparse(item.get("url", "")).scheme != "https":
            errors.append(f"Reference URL must use HTTPS for {item.get('name')!r}")

    for kind, rows in (("projects", project_bindings), ("html_handlers", html_bindings)):
        identifiers = [row.get("official_id" if kind == "projects" else "handler_id") for row in rows]
        if len(identifiers) != len(set(identifiers)):
            errors.append(f"Duplicate official {kind} bindings")
        coverage = [row.get("coverage_id") for row in rows]
        missing = sorted({identifier for identifier in coverage if identifier not in targets})
        if missing:
            errors.append(f"Dangling {kind} coverage IDs: {missing}")
        if None in coverage:
            errors.append(f"Unbound official {kind} coverage")
    for row in project_bindings:
        if row.get("coverage_id") in exclusion_index:
            errors.append(f"Project {row.get('official_id')} cannot be excluded from behavioral coverage")
    if [row.get("coverage_id") for row in project_bindings] != list(PROJECT_COVERAGE_IDS):
        errors.append("Project coverage must be exactly PRJ-001 through PRJ-096 in official array order")

    coverage_aliases = data.get("coverage_aliases", [])
    alias_index = unique_index("coverage_aliases", coverage_aliases)
    for alias_id, row in alias_index.items():
        if alias_id in targets:
            errors.append(f"Alias {alias_id} duplicates a feature or exclusion")
        canonical_targets = row.get("targets", [])
        if not isinstance(canonical_targets, list):
            errors.append(f"Alias {alias_id} targets must be an array")
            canonical_targets = []
        for target_id in canonical_targets:
            if target_id not in feature_index:
                errors.append(f"Alias {alias_id} has non-canonical target {target_id}")
            if target_id == alias_id:
                errors.append(f"Alias {alias_id} targets itself")
        for family in row.get("families", []):
            if not family.endswith("-*") or not any(feature_id.startswith(family[:-1]) for feature_id in feature_index):
                errors.append(f"Alias {alias_id} has an empty feature-family reference: {family}")
        documents = row.get("documents", [])
        if not canonical_targets and not row.get("families"):
            errors.append(f"Alias {alias_id} has no target or feature family")
        if not documents:
            errors.append(f"Alias {alias_id} has no trace document")
        found_in_document = False
        for document in documents:
            relative = Path(document)
            if relative.is_absolute() or ".." in relative.parts or not document.endswith(".md"):
                errors.append(f"Alias {alias_id} has an unsafe document path")
                continue
            document_path = root / relative
            if not document_path.is_file():
                errors.append(f"Alias {alias_id} references missing document {document}")
                continue
            text = document_path.read_text(encoding="utf-8")
            document_cache[document_path] = text
            if re.search(rf"(?<![A-Za-z0-9-]){re.escape(alias_id)}(?![A-Za-z0-9-])", text):
                found_in_document = True
        if documents and not found_in_document:
            errors.append(f"Alias {alias_id} is absent from its trace documents")

    if args.source_dir:
        for item in files:
            if item.get("name") not in REQUIRED_SOURCE_FILENAMES:
                continue
            candidate = args.source_dir / item["name"]
            if not candidate.is_file():
                errors.append(f"Missing source snapshot file: {item['name']}")
                continue
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                errors.append(f"Source hash differs for {item['name']}; review the new upstream snapshot")
        project_path = args.source_dir / "projects.js"
        html_path = args.source_dir / "index2.html"
        if project_path.is_file():
            source = mask_javascript_non_code(project_path.read_text(encoding="utf-8"))
            declarations = PROJECT_PATTERN.findall(source)
            pushes = PROJECT_PUSH_PATTERN.findall(source)
            expected = [row.get("official_id") for row in project_bindings]
            if declarations != pushes:
                errors.append("Official project declarations no longer match projects.push order")
            if declarations != expected:
                errors.append("Project bindings differ from the official definition/order set")
        if html_path.is_file():
            source_parser = InlineHandlerParser()
            source_parser.feed(html_path.read_text(encoding="utf-8"))
            actual = source_parser.handlers
            expected = html_bindings
            if len(actual) != len(expected):
                errors.append(f"HTML handler count differs: source={len(actual)}, bindings={len(expected)}")
            for position, (observed, bound) in enumerate(zip(actual, expected), 1):
                expected_handler_id = f"HTML-{position:03d}"
                if bound.get("handler_id") != expected_handler_id:
                    errors.append(f"Handler {position} must have stable ID {expected_handler_id}")
                for field in ("tag", "dom_id", "event", "function_name", "arguments", "line"):
                    if observed[field] != bound.get(field):
                        errors.append(f"{expected_handler_id} differs for {field}: {observed[field]!r} != {bound.get(field)!r}")

    for path, content in document_cache.items():
        if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", content):
            errors.append(f"Non-English CJK content found in {path.relative_to(root)}")

    if errors:
        print("Inventory validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        f"Inventory validation passed: {len(features)} features, {len(exclusions)} exclusions, "
        f"{len(project_bindings)} projects, {len(html_bindings)} HTML handlers, {len(coverage_aliases)} aliases"
        + ("; pinned source snapshot verified" if args.source_dir else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
