#!/usr/bin/env python3
# owner: paperclip-game maintainers
# trigger: execution-plan and inventory verification
# purpose: validate canonical coverage, task DAG, references, and planning hygiene without game execution
"""Validate the complete execution plan and prove its structural guards.

Normal mode is read-only and uses only the Python standard library. It never imports
or executes game JavaScript. --self-test writes only isolated temporary copies.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote

BASE = "80feca9dcd5fa4b0dea53601f7277e95d78e5134"
INV_SHA = "d64b549425fa87ad87e240be00abac282001a06906670bb2a3eea04fc1c74c3e"
MID_ORDER = [f"M{i}" for i in range(1, 16)]
EXPECTED_FEATURES = dict(zip(MID_ORDER, [19, 38, 20, 37, 11, 20, 15, 10, 3, 50, 14, 11, 5, 14, 7]))
EXPECTED_M1_TASKS = {
    "M1-BOOTSTRAP-CI", "M1-RUNTIME-CORE", "M1-API-COMMANDS-VIEW",
    "M1-PERSISTENCE-RECOVERY", "M1-SSE-VIEW-SYNC", "M1-NATIVE-TWO-PAGE-UI",
    "M1-G01", "M1-G02", "M1-G03", "M1-PLAYABLE-INTEGRATION",
}
EXPECTED_M2_TASKS = {"M2-C01", "M2-C02", "M2-C03"}
EXPECTED_SCENARIOS = {
    "ENG-WIRE-MANUAL-FLOOR", "ENG-WIRE-AUTOMATIC-FLOOR-CAP",
    "CONC-COMMANDS-BOTH-LEGAL", "CONC-COMMANDS-ONE-STOCK",
    "ENG-TICK-COMMAND-SERIALIZATION", "API-COMMAND-ID-INFLIGHT-SAME",
    "API-COMMAND-ID-TERMINAL-SUCCESS", "API-COMMAND-ID-TERMINAL-REJECTION",
    "API-COMMAND-ID-CONFLICT", "API-COMMAND-SCHEMA-BOUNDARIES",
    "RT-NO-CLIENTS-CONTINUOUS", "PERSIST-SNAPSHOT-30S-NONBLOCK",
    "PERSIST-SNAPSHOT-ATOMIC-COMPLETE", "PERSIST-CRASH-LOSS-NO-BACKFILL",
    "PERSIST-REPEATED-STARTUP", "SSE-SAME-RUN-ORDERING",
    "SSE-RECOVERED-RUN-RESYNC", "SSE-DISCONNECT-RECONNECT",
    "UI-EARLY-SERVER-AUTHORITY", "UI-TWO-ANONYMOUS-PAGES",
    "API-DEFAULT-NAMESPACE-BOUNDARY", "E2E-M1-DECLARED-PLAYABLE-EXIT",
    "ENG-PROJECT-OFFER-LATCH", "ENG-TRUST-OPS-CREATIVITY", "ENG-POWER-FULL-COVER", "ENG-POWER-LAST-PARTIAL",
    "ENG-POWER-SURPLUS-CAP-SPACE", "ENG-GIFT-ACTIVE-RESET",
    "ENG-GIFT-INACTIVE-HEALTH-GATES", "ENG-COMBAT-NAMING-HONOR-GATES",
    "ENG-COMBAT-TIMEOUT-HONOR", "ENG-HONOR-NEGATIVE-AND-GLORY",
    "E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE", "E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE",
    "E2E-EMPEROR-MUTUAL-EXCLUSION", "E2E-PRESTIGE-NEXT-DOOR",
    "E2E-PRESTIGE-WITHIN", "E2E-TEMPORAL-RESET", "E2E-XAVIER-ALLOCATION-RESET",
    "E2E-REJECT-FINAL-WIRE", "CONC-REJECT-FINAL-WIRE", "E2E-REJECT-CREDITS",
    "E2E-FULL-PHASE-ENGINE-TRACE", "RESET-INPROCESS-RETRY-RETENTION",
    "CI-BOOTSTRAP-REAL-MANIFEST",
}
EXPECTED_INVARIANTS = {
    "INV-WIRE-FLOOR-CAP", "INV-THREE-CLIP-LEDGERS", "INV-PROJECT121-VS-131",
    "INV-POWER-PARTIAL-BATTERY", "INV-REJECT-FINAL-REMAINDER",
    "INV-SWARM-GIFT-RESET", "INV-DRIFTWAR-NOT-UNIVERSAL-GATE",
    "INV-ENDING-ENDPOINTS", "INV-RESET-PRESTIGE", "INV-TWO-PAGE-ANONYMOUS",
    "INV-COMMAND-RETRY", "INV-SNAPSHOT-NO-BACKFILL",
}
LAYERS = {
    "rule_unit", "state_sequence", "property", "concurrency", "api_contract",
    "sse", "persistence", "gameplay_scenario", "browser_e2e", "long_simulation",
}
RISKS = {
    "core_simulation", "concurrency_persistence_recovery",
    "test_ci_merge_infrastructure", "security_data_main",
}
TWO_REVIEW = "two_independent_reviewers_including_one_adversarial"
ROOT_KEYS = {
    "schema_version", "status", "inventory", "planning_baseline", "documents",
    "milestones", "feature_owners", "tasks", "exclusion_traces", "alias_traces",
    "source_binding_owners", "scenario_catalog", "invariants", "technical_contract",
    "unresolved_source_conflicts",
}
INVENTORY_KEYS = {
    "path", "schema_version", "sha256", "feature_count", "exclusion_count",
    "alias_count", "project_binding_count", "html_handler_binding_count",
    "project_bindings_sha256", "html_handlers_sha256", "coverage_aliases_sha256",
}
MILESTONE_KEYS = {
    "id", "name", "granularity", "entry", "playable", "exit",
    "depends_on_milestones", "features", "task_ids", "scenario_ids", "test_layers",
    "spec_refs", "source_documents", "engineering_references", "source_rationale",
    "technical_dependencies", "accepted_scenarios", "testing_evidence", "risks",
    "feature_family_counts",
}
TASK_KEYS = {
    "id", "milestone_id", "detail", "title", "objective", "spec_refs", "scope",
    "non_goals", "depends_on", "scenario_ids", "acceptance_criteria", "required_tests",
    "evidence_requirements", "risk_flags", "review_requirement", "suggested_paths",
}
SCENARIO_KEYS = {
    "id", "title", "status", "milestone_ids", "layers", "spec_refs",
    "canonical_coverage_ids", "run_policy", "fixture", "steps", "assertions",
}
MILESTONE_ID = re.compile(r"^M[1-9][0-9]*$")
TASK_ID = re.compile(r"^M[1-9][0-9]*-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
AC_ID = re.compile(r"^AC[1-9][0-9]*$")
CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
PRIVATE_PATH = re.compile(
    "(?:" + re.escape("/" + "Users" + "/") + r"[^\s/]+/|"
    + re.escape("/" + "tmp" + "/" + "agents" + "/") + "|"
    + re.escape("/" + "home" + "/") + r"[^\s/]+/|"
    + re.escape("file" + "://" ) + "|" + re.escape("victor" + ".peng") + ")"
)
SECRET = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\s*=\s*['\"][^'\"]+['\"]|"
    r"Bearer\s+[A-Za-z0-9_-]{16,})",
    re.IGNORECASE,
)
PLACEHOLDERS = ("gameplay" + "-map.", "OWNING" + "_MILESTONE")


class InputError(Exception):
    pass


def load_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputError("duplicate JSON object key")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except InputError:
        raise
    except Exception as exc:
        raise InputError(type(exc).__name__) from None


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_path(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def relationship_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha_bytes(payload)


def duplicates(values):
    return sorted(key for key, count in collections.Counter(values).items() if count > 1)


def token(text: str, value: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(value)}(?![A-Za-z0-9-])", text) is not None


def obj(value):
    return value if isinstance(value, dict) else {}


def arr(value):
    return value if isinstance(value, list) else []


class Checker:
    def __init__(self, root: Path, plan_path: Path, private_source_dir: Path | None = None):
        self.root = root.resolve()
        self.plan_path = plan_path
        self.private_source_dir = private_source_dir
        self.errors: list[tuple[str, str]] = []
        self.doc_text: dict[str, str] = {}
        self.headings: dict[str, list[str]] = {}
        self.narrative = ""
        self.stats = {}
        self.feature_map = {}
        self.exclusion_map = {}
        self.alias_map = {}
        self.owner_map = {}
        self.owner_task = {}
        self.task_map = {}
        self.milestone_map = {}
        self.scenario_map = {}

    def e(self, code: str, where: str, message: str):
        self.errors.append((code, f"{where}: {message}"))

    def require(self, condition, code: str, where: str, message: str):
        if not condition:
            self.e(code, where, message)

    def exact(self, value, keys, code: str, where: str, optional=()):
        if not isinstance(value, dict):
            self.e(code, where, "expected object")
            return False
        expected = set(keys) | set(optional)
        if set(value) != expected and not (optional and set(value) == set(keys)):
            missing = sorted(set(keys) - set(value))
            extra = sorted(set(value) - expected)
            self.e(code, where, f"closed fields differ; missing={missing}, extra={extra}")
            return False
        return True

    def string(self, value, code: str, where: str, blank_ok=False):
        good = isinstance(value, str) and (blank_ok or bool(value.strip()))
        self.require(good, code, where, "expected nonblank string" if not blank_ok else "expected string")
        return value if isinstance(value, str) else ""

    def strings(self, value, code: str, where: str, nonempty=True, unique=False):
        good = isinstance(value, list) and (not nonempty or bool(value)) and all(
            isinstance(item, str) and item.strip() for item in value
        )
        self.require(good, code, where, "expected string array" + (" (nonempty)" if nonempty else ""))
        values = value if isinstance(value, list) else []
        if unique:
            self.require(not duplicates(values), code, where, "array entries must be unique")
        return values

    def integer(self, value, expected, code: str, where: str):
        self.require(type(value) is int and value == expected, code, where, f"expected integer {expected}, not bool/other type")

    def safe_document(self, value, code="E_SPEC_DOCUMENT", allow_agents=True):
        if not isinstance(value, str) or "\x00" in value:
            self.e(code, "document", "expected repository-relative Markdown path")
            return None
        decoded = value
        for _ in range(2):
            decoded = unquote(decoded)
        path = Path(decoded)
        permitted = decoded.startswith("requirements/") or (allow_agents and decoded == "AGENTS.md")
        if path.is_absolute() or ".." in path.parts or path.suffix != ".md" or not permitted:
            self.e(code, decoded if "\x00" not in decoded else "document", "unsafe or disallowed document")
            return None
        candidate = self.root / path
        try:
            candidate.resolve().relative_to(self.root)
        except ValueError:
            self.e(code, decoded, "document escapes repository root")
            return None
        if not candidate.is_file():
            self.e(code, decoded, "document does not exist")
            return None
        if decoded not in self.doc_text:
            try:
                self.doc_text[decoded] = candidate.read_text(encoding="utf-8")
            except Exception:
                self.e(code, decoded, "document is not readable UTF-8")
                return None
            self.headings[decoded] = [
                re.sub(r"^#{1,6}\s+", "", line).strip()
                for line in self.doc_text[decoded].splitlines()
                if re.match(r"^#{1,6}\s+", line)
            ]
        return decoded

    def spec_ref(self, value, where: str):
        if not self.exact(value, {"document", "heading"}, "E_SPEC_REFERENCE", where):
            return
        loaded = self.safe_document(value.get("document"))
        if not loaded:
            return
        heading = value.get("heading")
        self.string(heading, "E_SPEC_HEADING", where)
        if isinstance(heading, str):
            count = self.headings[loaded].count(heading)
            self.require(count == 1, "E_SPEC_HEADING", where, f"heading occurs {count} times in {loaded}; exact unique match required")

    def spec_refs(self, value, where: str, nonempty=True):
        # spec_refs are objects, not strings; use a separate type check to avoid confusing diagnostics.
        if not isinstance(value, list) or (nonempty and not value):
            self.e("E_SPEC_REFERENCE", where, "expected nonempty reference array" if nonempty else "expected reference array")
            return []
        for index, ref in enumerate(value):
            self.spec_ref(ref, f"{where}[{index}]")
        return value

    def graph(self, ids, edges, baseline_ids, milestone=False):
        prefix = "E_MILESTONE" if milestone else "E_DEP"
        clean = {tid: [] for tid in ids}
        for tid, values in edges.items():
            if tid not in ids:
                self.e(prefix + "_UNKNOWN", tid, "graph node is not in the declared set")
                continue
            if not isinstance(values, list) or duplicates(values):
                self.e(prefix + "_DUPLICATE", tid, "dependency array is invalid or duplicated")
                continue
            for dep in values:
                if not isinstance(dep, str):
                    self.e(prefix + "_UNKNOWN", tid, "dependency must be a string ID")
                elif dep == tid:
                    self.e(prefix + "_SELF", tid, "self dependency")
                elif dep not in ids:
                    self.e(prefix + "_UNKNOWN", tid, f"unknown dependency {dep}")
                else:
                    clean[tid].append(dep)
        indegree = {tid: len(clean[tid]) for tid in ids}
        dependents = {tid: [] for tid in ids}
        for tid, values in clean.items():
            for dep in values:
                dependents[dep].append(tid)
        queue = collections.deque(tid for tid in ids if indegree[tid] == 0)
        seen = []
        while queue:
            current = queue.popleft()
            seen.append(current)
            for nxt in dependents[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        self.require(len(seen) == len(ids), prefix + ("_DAG" if milestone else "_CYCLE"), "graph", "dependency cycle including any disconnected component")
        roots = [tid for tid in ids if not edges.get(tid)]
        if milestone:
            self.require(roots == ["M1"], "E_MILESTONE_DAG", "graph", "M1 must be the only dependency-free milestone")
            baseline_ids = ["M1"]
        self.require(bool(baseline_ids) and all(tid in ids for tid in baseline_ids), "E_BASELINE", "baseline", "unblocked IDs must exist")
        reachable = set(tid for tid in baseline_ids if tid in ids)
        changed = True
        while changed:
            changed = False
            for tid in ids:
                if tid not in reachable and clean[tid] and all(dep in reachable for dep in clean[tid]):
                    reachable.add(tid)
                    changed = True
        for tid in sorted(set(ids) - reachable):
            self.e("E_MILESTONE_DAG" if milestone else "E_REACHABILITY", tid, "no forward path from baseline")
        if not milestone:
            for tid in ids:
                if tid not in baseline_ids and not edges.get(tid):
                    self.e("E_REACHABILITY", tid, "non-baseline task has an empty dependency set")
        self.stats["milestone_edges" if milestone else "dependency_edges"] = sum(len(v) for v in clean.values())

    def ancestors(self, mid, cache):
        if mid in cache:
            return cache[mid]
        seen = set()
        stack = list(arr(self.milestone_map.get(mid, {}).get("depends_on_milestones")))
        while stack:
            current = stack.pop()
            if current in seen or current not in self.milestone_map:
                continue
            seen.add(current)
            stack.extend(arr(self.milestone_map[current].get("depends_on_milestones")))
        cache[mid] = seen
        return seen

    def validate_inventory(self, inventory, raw_bytes):
        self.require(isinstance(inventory, dict), "E_INVENTORY_BINDING", "inventory", "root must be object")
        declared = obj(self.plan.get("inventory"))
        self.exact(declared, INVENTORY_KEYS, "E_INVENTORY_BINDING", "inventory")
        self.require(declared.get("path") == "requirements/data/gameplay-inventory.json", "E_INVENTORY_BINDING", "inventory.path", "literal canonical path required")
        self.integer(declared.get("schema_version"), 1, "E_INVENTORY_SCHEMA", "inventory.schema_version")
        actual_hash = sha_bytes(raw_bytes)
        self.require(actual_hash == INV_SHA, "E_INVENTORY_SHA", "inventory", "canonical raw bytes differ from trusted baseline")
        self.require(declared.get("sha256") == actual_hash, "E_INVENTORY_SHA", "inventory.sha256", "declared hash differs from actual canonical bytes")
        features = arr(inventory.get("features"))
        exclusions = arr(inventory.get("exclusions"))
        aliases = arr(inventory.get("coverage_aliases"))
        bindings = obj(inventory.get("source_bindings"))
        projects = arr(bindings.get("projects"))
        handlers = arr(bindings.get("html_handlers"))
        for key, value in {
            "feature_count": len(features), "exclusion_count": len(exclusions),
            "alias_count": len(aliases), "project_binding_count": len(projects),
            "html_handler_binding_count": len(handlers),
        }.items():
            self.integer(declared.get(key), value, "E_INVENTORY_BINDING", "inventory." + key)
        for key, value in {
            "project_bindings_sha256": relationship_hash(projects),
            "html_handlers_sha256": relationship_hash(handlers),
            "coverage_aliases_sha256": relationship_hash(aliases),
        }.items():
            self.require(declared.get(key) == value, "E_INVENTORY_BINDING", "inventory." + key, "canonical relationship hash differs")
        self.integer(inventory.get("schema_version"), 1, "E_INVENTORY_SCHEMA", "canonical.schema_version")
        canonical_ids = []
        for index, row in enumerate(features):
            if not self.exact(row, {"id", "name", "document"}, "E_INVENTORY_BINDING", f"features[{index}]"):
                continue
            fid = row.get("id")
            if isinstance(fid, str):
                canonical_ids.append(fid)
                self.feature_map[fid] = row
            self.string(row.get("name"), "E_INVENTORY_BINDING", f"features[{index}].name")
            self.safe_document(row.get("document"), "E_INVENTORY_BINDING")
        for index, row in enumerate(exclusions):
            if not self.exact(row, {"id", "name", "reason", "document"}, "E_INVENTORY_BINDING", f"exclusions[{index}]"):
                continue
            xid = row.get("id")
            if isinstance(xid, str):
                self.exclusion_map[xid] = row
            self.string(row.get("reason"), "E_INVENTORY_BINDING", f"exclusions[{index}].reason")
            self.safe_document(row.get("document"), "E_INVENTORY_BINDING")
        self.require(not duplicates(canonical_ids), "E_FEATURE_SET", "canonical.features", "IDs must be unique")
        cset, eset = set(self.feature_map), set(self.exclusion_map)
        self.require(not (cset & eset), "E_EXCLUSION_BOUNDARY", "canonical", "features and exclusions overlap")
        for index, row in enumerate(aliases):
            if not self.exact(row, {"id", "targets", "documents", "note"}, "E_ALIAS_TARGET", f"coverage_aliases[{index}]", optional=("families",)):
                continue
            aid = row.get("id")
            if isinstance(aid, str):
                self.alias_map[aid] = row
            self.string(row.get("note"), "E_ALIAS_TARGET", f"alias {aid}.note")
            targets = arr(row.get("targets"))
            for target in targets:
                self.require(target in cset, "E_ALIAS_TARGET", f"alias {aid}", f"noncanonical target {target}")
            families = arr(row.get("families"))
            for family in families:
                prefix = family[:-1] if isinstance(family, str) and family.endswith("-*") else ""
                self.require(bool(prefix) and any(fid.startswith(prefix) for fid in cset), "E_ALIAS_FAMILY", f"alias {aid}", f"empty/bad family {family}")
            found = False
            for document in self.strings(row.get("documents"), "E_ALIAS_DOCUMENT", f"alias {aid}.documents"):
                loaded = self.safe_document(document, "E_ALIAS_DOCUMENT")
                if loaded and token(self.doc_text[loaded], str(aid)):
                    found = True
            self.require(found, "E_ALIAS_DOCUMENT", f"alias {aid}", "alias is absent as a literal token in its canonical documents")
        # Canonical source relationship checks run even if the raw hash also changed.
        expected_projects = [f"PRJ-{i:03d}" for i in range(1, 97)]
        self.require([obj(row).get("coverage_id") for row in projects] == expected_projects, "E_PROJECT_BINDING", "canonical.projects", "must be PRJ-001..096 in true insertion order")
        official = [obj(row).get("official_id") for row in projects]
        self.require(not duplicates(official), "E_PROJECT_BINDING", "canonical.projects", "official IDs must be unique")
        for row in projects:
            cid = obj(row).get("coverage_id")
            self.require(cid in cset, "E_PROJECT_BINDING", f"project {obj(row).get('official_id')}", f"unknown or excluded coverage {cid}")
        for index, row in enumerate(handlers, 1):
            expected = f"HTML-{index:03d}"
            self.require(obj(row).get("handler_id") == expected, "E_HANDLER_BINDING", f"handlers[{index}]", "stable ordered handler ID required")
            cid = obj(row).get("coverage_id")
            self.require(cid in cset | eset, "E_HANDLER_BINDING", expected, f"unknown coverage {cid}")
        self.stats.update({"features": len(features), "exclusions": len(exclusions), "aliases": len(aliases), "projects": len(projects), "html_handlers": len(handlers)})

    def validate_milestones_and_tasks(self):
        milestones = arr(self.plan.get("milestones"))
        ids = [obj(row).get("id") for row in milestones]
        for value in duplicates(ids):
            self.e("E_MILESTONE_DUPLICATE", str(value), "duplicate milestone ID")
        self.require(ids == MID_ORDER, "E_MILESTONE_ID", "milestones", "exact contiguous M1..M15 array required")
        for row in milestones:
            mid = obj(row).get("id", "?")
            if isinstance(mid, str):
                self.milestone_map[mid] = row
        expected_granularity = {mid: ("current_detailed" if mid == "M1" else "next_coarse" if mid == "M2" else "mapped_future") for mid in MID_ORDER}
        for index, row in enumerate(milestones):
            mid = obj(row).get("id", f"row{index}")
            if not self.exact(row, MILESTONE_KEYS, "E_MILESTONE_CONTRACT", str(mid)):
                continue
            for field in ("name", "entry", "playable", "exit", "source_rationale", "technical_dependencies"):
                self.string(row.get(field), "E_MILESTONE_CONTRACT", f"{mid}.{field}")
            self.require(row.get("granularity") == expected_granularity.get(mid), "E_DETAIL_GRANULARITY", str(mid), "wrong detail granularity")
            for field in ("source_documents", "engineering_references", "accepted_scenarios", "testing_evidence", "risks"):
                self.strings(row.get(field), "E_MILESTONE_CONTRACT", f"{mid}.{field}")
            for field in ("source_documents", "engineering_references"):
                for document in arr(row.get(field)):
                    self.safe_document(document)
            self.spec_refs(row.get("spec_refs"), f"{mid}.spec_refs")
            layers = self.strings(row.get("test_layers"), "E_TEST_LAYER", f"{mid}.test_layers", unique=True)
            self.require(set(layers) <= LAYERS, "E_TEST_LAYER", str(mid), "unknown test layer")
            self.require({"rule_unit", "state_sequence", "api_contract", "gameplay_scenario", "browser_e2e"} <= set(layers), "E_TEST_LAYER", str(mid), "required playable milestone layers are missing")
            deps = self.strings(row.get("depends_on_milestones"), "E_MILESTONE_DAG", f"{mid}.depends_on_milestones", nonempty=(mid != "M1"), unique=True)
            self.require(not deps if mid == "M1" else bool(deps), "E_MILESTONE_DAG", str(mid), "M1 root / later nonempty dependency required")
        milestone_edges = {mid: arr(self.milestone_map.get(mid, {}).get("depends_on_milestones")) for mid in ids if isinstance(mid, str)}
        self.graph(ids, milestone_edges, ["M1"], milestone=True)
        self.require(milestone_edges.get("M12") == ["M10"], "E_COMPLETION_GATE", "M12", "Driftwar/M11 must not become a universal-achievement gate")
        self.require(milestone_edges.get("M14") == ["M12"], "E_BRANCH_DEPENDENCY", "M14", "Reject must not depend on Accept/M13")
        self.require(set(milestone_edges.get("M15", [])) == {"M11", "M12", "M13", "M14"}, "E_BRANCH_DEPENDENCY", "M15", "full acceptance must join independent combat/universal/Accept/Reject evidence")
        # Tasks and complete closed task schema.
        tasks = arr(self.plan.get("tasks"))
        self.require(isinstance(self.plan.get("tasks"), list), "E_TASK_SCHEMA", "tasks", "expected task array")
        task_ids = []
        for index, row in enumerate(tasks):
            tid = obj(row).get("id")
            if isinstance(tid, str):
                task_ids.append(tid)
                if tid in self.task_map:
                    self.e("E_TASK_DUPLICATE", tid, "duplicate task ID")
                else:
                    self.task_map[tid] = row
        self.require(len(tasks) == 26 and not duplicates(task_ids), "E_TASK_SET", "tasks", "exactly 26 unique current+future task records required")
        self.require({tid for tid in task_ids if tid.startswith("M1-")} == EXPECTED_M1_TASKS, "E_TASK_SET", "M1", "ten integrated detailed tasks required")
        self.require({tid for tid in task_ids if tid.startswith("M2-")} == EXPECTED_M2_TASKS, "E_TASK_SET", "M2", "three actual coarse packages required")
        self.require(all(any(tid == f"{mid}-C01" for tid in task_ids) for mid in MID_ORDER[2:]), "E_TASK_SET", "future", "one mapped outline per M3-M15 is required")
        for index, row in enumerate(tasks):
            tid = obj(row).get("id", f"row{index}")
            if not self.exact(row, TASK_KEYS, "E_TASK_SCHEMA", str(tid)):
                continue
            mid = row.get("milestone_id")
            self.require(isinstance(tid, str) and TASK_ID.fullmatch(tid), "E_TASK_ID", str(tid), "invalid stable task ID")
            self.require(mid in self.milestone_map and isinstance(tid, str) and tid.startswith(str(mid) + "-"), "E_TASK_MILESTONE", str(tid), "task prefix/milestone mismatch")
            detailed = mid == "M1"
            self.require(row.get("detail") == ("detailed" if detailed else "coarse"), "E_DETAIL_GRANULARITY", str(tid), "wrong detail value")
            self.string(row.get("title"), "E_TASK_FIELD", f"{tid}.title")
            objective = self.string(row.get("objective"), "E_TASK_FIELD", f"{tid}.objective")
            if not detailed:
                self.require(not re.search(r"(?:Blocked by:\s*|Issue\s+)#\d+", objective), "E_FUTURE_ISSUE_ID", str(tid), "no future GitHub issue identity")
            self.spec_refs(row.get("spec_refs"), f"{tid}.spec_refs")
            self.strings(row.get("scope"), "E_TASK_FIELD", f"{tid}.scope")
            # Dependencies are checked after every task ID has been collected.
            scenario_ids = self.strings(row.get("scenario_ids"), "E_SCENARIO_REFERENCE", f"{tid}.scenario_ids", unique=True)
            for sid in scenario_ids:
                self.require(sid in self.scenario_map, "E_SCENARIO_REFERENCE", str(tid), f"unknown scenario {sid}")
            acceptance = arr(row.get("acceptance_criteria"))
            tests = arr(row.get("required_tests"))
            if detailed:
                self.strings(row.get("non_goals"), "E_TASK_ACCEPTANCE_FIELD", f"{tid}.non_goals")
                self.require(bool(acceptance), "E_TASK_ACCEPTANCE_FIELD", str(tid), "detailed acceptance criteria required")
                ac_seen = []
                for pos, criterion in enumerate(acceptance):
                    where = f"{tid}.acceptance_criteria[{pos}]"
                    if not self.exact(criterion, {"id", "statement", "scenario_ids"}, "E_TASK_ACCEPTANCE_FIELD", where):
                        continue
                    acid = criterion.get("id")
                    if isinstance(acid, str):
                        ac_seen.append(acid)
                    self.require(isinstance(acid, str) and AC_ID.fullmatch(acid), "E_TASK_ACCEPTANCE_FIELD", where, "invalid acceptance ID")
                    self.string(criterion.get("statement"), "E_TASK_ACCEPTANCE_FIELD", where + ".statement")
                    for sid in self.strings(criterion.get("scenario_ids"), "E_SCENARIO_REFERENCE", where + ".scenario_ids", unique=True):
                        self.require(sid in self.scenario_map, "E_SCENARIO_REFERENCE", where, f"unknown scenario {sid}")
                self.require(not duplicates(ac_seen), "E_ACCEPTANCE_DUPLICATE", str(tid), "duplicate acceptance ID")
                self.require(bool(tests), "E_TASK_TEST_COVERAGE", str(tid), "required tests are missing")
                covered = []
                for pos, test in enumerate(tests):
                    where = f"{tid}.required_tests[{pos}]"
                    if not self.exact(test, {"layers", "acceptance_ids", "method", "scenario_ids"}, "E_TASK_TEST_COVERAGE", where):
                        continue
                    tls = self.strings(test.get("layers"), "E_TEST_LAYER", where + ".layers", unique=True)
                    self.require(bool(tls) and set(tls) <= LAYERS, "E_TEST_LAYER", where, "unknown/empty test layer")
                    aids = self.strings(test.get("acceptance_ids"), "E_TASK_TEST_COVERAGE", where + ".acceptance_ids", unique=True)
                    covered.extend(aids)
                    self.require(set(aids) <= set(ac_seen), "E_TASK_TEST_COVERAGE", where, "test names an unknown acceptance ID")
                    self.string(test.get("method"), "E_TASK_TEST_COVERAGE", where + ".method")
                    for sid in self.strings(test.get("scenario_ids"), "E_SCENARIO_REFERENCE", where + ".scenario_ids", unique=True):
                        self.require(sid in self.scenario_map, "E_SCENARIO_REFERENCE", where, f"unknown scenario {sid}")
                for acid in ac_seen:
                    self.require(acid in covered, "E_TASK_TEST_COVERAGE", str(tid), f"acceptance {acid} has no required test")
                self.strings(row.get("evidence_requirements"), "E_TASK_ACCEPTANCE_FIELD", f"{tid}.evidence_requirements")
                risks = self.strings(row.get("risk_flags"), "E_RISK_FLAG", f"{tid}.risk_flags", unique=True)
                self.require(bool(risks) and set(risks) <= RISKS, "E_RISK_FLAG", str(tid), "unknown/empty detailed risk flags")
                self.require(row.get("review_requirement") == TWO_REVIEW, "E_REVIEW_REQUIREMENT", str(tid), "high-risk M1 route requires two independent reviewers including adversarial")
                for path in self.strings(row.get("suggested_paths"), "E_TASK_ACCEPTANCE_FIELD", f"{tid}.suggested_paths"):
                    decoded = unquote(path)
                    p = Path(decoded)
                    self.require(not p.is_absolute() and ".." not in p.parts, "E_PUBLIC_PRIVATE_PATH", str(tid), "unsafe suggested path")
            else:
                empty_fields = ("non_goals", "acceptance_criteria", "required_tests", "evidence_requirements", "risk_flags", "suggested_paths")
                self.require(all(row.get(field) == [] for field in empty_fields), "E_COARSE_CONTRACT", str(tid), "future package contains detail-only fields")
                self.require(row.get("review_requirement") == "deferred_until_detailed_issue", "E_COARSE_CONTRACT", str(tid), "coarse review is deferred until refinement")
                self.require(set(scenario_ids) == set(arr(self.milestone_map.get(mid, {}).get("scenario_ids"))), "E_TASK_SCENARIO", str(tid), "coarse task scenarios must mirror its milestone")
            for sid in scenario_ids:
                scenario = self.scenario_map.get(sid, {})
                self.require(mid in arr(scenario.get("milestone_ids")), "E_SCENARIO_RECIPROCITY", str(tid), f"scenario {sid} does not reciprocally include {mid}")
        task_edges = {}
        for row in tasks:
            tid = obj(row).get("id")
            self.require(isinstance(obj(row).get("depends_on"), list), "E_TASK_FIELD", f"{tid}.depends_on", "expected dependency array of objects")
            deps = arr(obj(row).get("depends_on"))
            values = []
            for pos, dep in enumerate(deps):
                where = f"{tid}.depends_on[{pos}]"
                if not self.exact(dep, {"task_id", "reason"}, "E_TASK_FIELD", where):
                    continue
                self.string(dep.get("reason"), "E_TASK_FIELD", where + ".reason")
                if isinstance(dep.get("task_id"), str):
                    values.append(dep["task_id"])
            task_edges[tid] = values
        baseline = obj(self.plan.get("planning_baseline"))
        self.exact(baseline, {"id", "commit", "unblocked_task_ids"}, "E_BASELINE", "planning_baseline")
        self.string(baseline.get("id"), "E_BASELINE", "planning_baseline.id")
        self.require(baseline.get("commit") == BASE, "E_BASELINE", "planning_baseline.commit", "verified base differs")
        baseline_ids = self.strings(baseline.get("unblocked_task_ids"), "E_BASELINE", "planning_baseline.unblocked_task_ids", unique=True)
        self.require(baseline_ids == ["M1-BOOTSTRAP-CI"], "E_BASELINE", "planning_baseline", "only the real bootstrap task is unblocked")
        self.graph(task_ids, task_edges, baseline_ids)
        cache = {}
        for row in tasks:
            tid = obj(row).get("id")
            mid = obj(row).get("milestone_id")
            for dep in task_edges.get(tid, []):
                if dep not in self.task_map:
                    continue
                dep_mid = obj(self.task_map[dep]).get("milestone_id")
                self.require(dep_mid == mid or dep_mid in self.ancestors(mid, cache), "E_CROSS_MILESTONE", str(tid), f"dependency {dep} is not in the same or declared predecessor milestone")
        # Milestone task sets and scenarios are exact mirrors.
        for mid, row in self.milestone_map.items():
            expected_tasks = [tid for tid in task_ids if obj(self.task_map.get(tid)).get("milestone_id") == mid]
            self.require(arr(row.get("task_ids")) == expected_tasks, "E_MILESTONE_TASK_SET", str(mid), "task_ids must exactly mirror task milestone owners in stable order")
            expected_scenarios = [sid for sid, scenario in self.scenario_map.items() if mid in arr(scenario.get("milestone_ids"))]
            self.require(set(arr(row.get("scenario_ids"))) == set(expected_scenarios), "E_SCENARIO_RECIPROCITY", str(mid), "scenario set is not the exact reciprocal catalog set")
            self.require(not duplicates(arr(row.get("scenario_ids"))), "E_SCENARIO_RECIPROCITY", str(mid), "duplicate scenario reference")
            self.require(any({"gameplay_scenario", "browser_e2e"} <= set(arr(self.scenario_map[sid].get("layers"))) for sid in arr(row.get("scenario_ids")) if sid in self.scenario_map), "E_PLAYABLE_SCENARIO", str(mid), "no linked gameplay+browser acceptance scenario")
        self.stats.update({"tasks": len(tasks), "m1_detailed_tasks": sum(1 for row in tasks if obj(row).get("milestone_id") == "M1"), "coarse_tasks": sum(1 for row in tasks if obj(row).get("milestone_id") != "M1")})

    def validate_owners_exclusions_aliases_bindings(self):
        owners = arr(self.plan.get("feature_owners"))
        owner_ids = []
        for index, row in enumerate(owners):
            if not self.exact(row, {"feature_id", "milestone_id", "owning_task_id"}, "E_FEATURE_OWNER_SCHEMA", f"feature_owners[{index}]"):
                continue
            fid, mid, tid = row.get("feature_id"), row.get("milestone_id"), row.get("owning_task_id")
            if isinstance(fid, str):
                owner_ids.append(fid)
            if fid in self.exclusion_map:
                self.e("E_EXCLUSION_OWNER", str(fid), "exclusion cannot be a primary feature owner")
            if fid not in self.feature_map:
                self.e("E_FEATURE_UNKNOWN", str(fid), "unknown/noncanonical feature owner")
                continue
            if fid in self.owner_map:
                self.e("E_FEATURE_DUPLICATE", str(fid), "multiple primary owners")
                continue
            self.owner_map[fid] = mid
            self.owner_task[fid] = tid
            self.require(mid in self.milestone_map, "E_MILESTONE_REFERENCE", str(fid), "unknown milestone owner")
            task = obj(self.task_map.get(tid))
            self.require(bool(task) and task.get("milestone_id") == mid, "E_FEATURE_TASK_OWNER", str(fid), "primary task must exist in the same milestone")
            if mid == "M1":
                self.require(tid in {"M1-G01", "M1-G02", "M1-G03"}, "E_FEATURE_TASK_OWNER", str(fid), "M1 feature must resolve explicitly to its gameplay-owner PR task")
            else:
                self.require(task.get("detail") == "coarse", "E_COARSE_CONTRACT", str(fid), "future ownership must remain coarse")
        for fid in sorted(set(self.feature_map) - set(owner_ids)):
            self.e("E_FEATURE_OMITTED", fid, "no primary owner")
        for fid in duplicates(owner_ids):
            self.e("E_FEATURE_DUPLICATE", fid, "duplicate owner row")
        self.require(len(owners) == 274 and set(owner_ids) == set(self.feature_map), "E_FEATURE_SET", "feature_owners", "exact canonical one-owner set required")
        for mid, row in self.milestone_map.items():
            expected = [fid for fid in owner_ids if self.owner_map.get(fid) == mid]
            declared = self.strings(row.get("features"), "E_FEATURE_SET", f"{mid}.features", unique=True)
            self.require(declared == expected, "E_FEATURE_OWNER_SET", str(mid), "feature list must mirror exact primary owners in canonical order")
            self.require(len(expected) == EXPECTED_FEATURES.get(mid), "E_MILESTONE_FEATURE_COUNT", str(mid), f"expected {EXPECTED_FEATURES.get(mid)} features")
            families = dict(sorted(collections.Counter(fid.split("-", 1)[0] for fid in expected).items()))
            self.require(row.get("feature_family_counts") == families, "E_MILESTONE_FAMILY_COUNT", str(mid), "family count mismatch")
        self.stats["feature_totals_by_milestone"] = {mid: sum(1 for fid, owner in self.owner_map.items() if owner == mid) for mid in MID_ORDER}
        # Seven exclusions remain separate non-implementation traces.
        traces = arr(self.plan.get("exclusion_traces"))
        trace_ids = []
        for index, row in enumerate(traces):
            if not self.exact(row, {"id", "review_milestone_ids", "spec_ref", "preservation"}, "E_EXCLUSION_SCHEMA", f"exclusion_traces[{index}]"):
                continue
            xid = row.get("id")
            if isinstance(xid, str):
                trace_ids.append(xid)
            if xid not in self.exclusion_map:
                self.e("E_EXCLUSION_UNKNOWN", str(xid), "unknown exclusion or canonical feature")
                continue
            self.require(not duplicates(self.strings(row.get("review_milestone_ids"), "E_EXCLUSION_TRACE", f"{xid}.review_milestone_ids")), "E_EXCLUSION_TRACE", str(xid), "duplicate review milestones")
            self.require(set(arr(row.get("review_milestone_ids"))) <= set(self.milestone_map) and bool(arr(row.get("review_milestone_ids"))), "E_EXCLUSION_TRACE", str(xid), "review milestones must be known and nonempty")
            ref = obj(row.get("spec_ref"))
            self.require(ref.get("document") == self.exclusion_map[xid].get("document"), "E_EXCLUSION_TRACE", str(xid), "wrong canonical exclusion document")
            self.spec_ref(ref, str(xid) + ".spec_ref")
            self.string(row.get("preservation"), "E_EXCLUSION_TRACE", f"{xid}.preservation")
        self.require(set(trace_ids) == set(self.exclusion_map), "E_EXCLUSION_OMITTED", "exclusion_traces", "exact seven canonical exclusions required")
        self.require(not duplicates(trace_ids), "E_EXCLUSION_DUPLICATE", "exclusion_traces", "duplicate exclusion trace")
        # All aliases resolve through actual targets and the narrow family qualifier.
        alias_traces = arr(self.plan.get("alias_traces"))
        alias_ids = []
        for index, row in enumerate(alias_traces):
            if not self.exact(row, {"id", "milestone_ids", "scenario_ids", "resolved_family_feature_ids", "related_feature_ids", "resolution_note"}, "E_ALIAS_SCHEMA", f"alias_traces[{index}]"):
                continue
            aid = row.get("id")
            if isinstance(aid, str):
                alias_ids.append(aid)
            if aid not in self.alias_map:
                self.e("E_ALIAS_UNKNOWN", str(aid), "unknown alias")
                continue
            canonical = self.alias_map[aid]
            expected_family = []
            for family in arr(canonical.get("families")):
                if family == "ACT-PROBE-*":
                    expected_family.extend(fid for fid in self.feature_map if fid.startswith("ACT-PROBE-") and (fid.endswith("-LOWER") or fid.endswith("-RAISE")))
                elif isinstance(family, str) and family.endswith("-*") and any(fid.startswith(family[:-1]) for fid in self.feature_map):
                    expected_family.extend(fid for fid in self.feature_map if fid.startswith(family[:-1]))
                else:
                    self.e("E_ALIAS_FAMILY", str(aid), f"empty/bad family {family}")
            resolved_family = self.strings(row.get("resolved_family_feature_ids"), "E_ALIAS_FAMILY", f"{aid}.resolved_family_feature_ids", nonempty=False, unique=True)
            self.require(resolved_family == expected_family, "E_ALIAS_FAMILY", str(aid), "family expansion differs; direct-arrow family is exactly 16, not all 19 prefix matches")
            related = self.strings(row.get("related_feature_ids"), "E_ALIAS_TARGET", f"{aid}.related_feature_ids", nonempty=False, unique=True)
            self.require(set(related) <= set(self.feature_map), "E_ALIAS_TARGET", str(aid), "related feature must be canonical")
            target_features = list(arr(canonical.get("targets"))) + expected_family
            expected_mids = sorted({self.owner_map.get(fid) for fid in target_features if fid in self.owner_map}, key=lambda mid: MID_ORDER.index(mid) if mid in MID_ORDER else 999)
            self.require(arr(row.get("milestone_ids")) == expected_mids, "E_ALIAS_OWNER", str(aid), "owner milestones differ from actual target/family owners")
            scenarios = self.strings(row.get("scenario_ids"), "E_SCENARIO_REFERENCE", f"{aid}.scenario_ids", unique=True)
            covered = set()
            for sid in scenarios:
                scenario = self.scenario_map.get(sid)
                self.require(scenario is not None, "E_SCENARIO_REFERENCE", str(aid), f"unknown scenario {sid}")
                covered.update(arr(obj(scenario).get("milestone_ids")))
            self.require(set(expected_mids) <= covered, "E_ALIAS_SCENARIO", str(aid), "scenario union does not cover all target/family owners")
            self.string(row.get("resolution_note"), "E_ALIAS_TRACE", f"{aid}.resolution_note")
        self.require(set(alias_ids) == set(self.alias_map), "E_ALIAS_OMITTED", "alias_traces", "exact 32 canonical aliases required")
        self.require(not duplicates(alias_ids), "E_ALIAS_DUPLICATE", "alias_traces", "duplicate alias trace")
        self.require(sum(len(arr(row.get("targets"))) for row in self.alias_map.values()) == 44 and len({target for row in self.alias_map.values() for target in arr(row.get("targets"))}) == 22, "E_ALIAS_SET", "canonical aliases", "44 explicit edges / 22 distinct targets required")
        # Ordered project and handler owners.
        owners_by_source = obj(self.plan.get("source_binding_owners"))
        self.exact(owners_by_source, {"projects", "html_handlers"}, "E_INVENTORY_BINDING", "source_binding_owners")
        projects = arr(owners_by_source.get("projects"))
        canonical_projects = arr(obj(self.inventory.get("source_bindings")).get("projects"))
        self.require(len(projects) == len(canonical_projects), "E_PROJECT_BINDING", "source_binding_owners.projects", "binding count mismatch")
        for index, (row, source) in enumerate(zip(projects, canonical_projects), 1):
            if not self.exact(row, {"source_sequence", "official_id", "feature_id", "milestone_id"}, "E_PROJECT_BINDING", f"project row {index}"):
                continue
            cid = obj(source).get("coverage_id")
            self.require(row.get("source_sequence") == index and row.get("official_id") == obj(source).get("official_id") and row.get("feature_id") == cid, "E_PROJECT_BINDING", f"project row {index}", "canonical identity/order differs")
            self.require(row.get("milestone_id") == self.owner_map.get(cid), "E_PROJECT_BINDING", f"project row {index}", "primary owner differs")
        handlers = arr(owners_by_source.get("html_handlers"))
        canonical_handlers = arr(obj(self.inventory.get("source_bindings")).get("html_handlers"))
        self.require(len(handlers) == len(canonical_handlers), "E_HANDLER_BINDING", "source_binding_owners.html_handlers", "binding count mismatch")
        for index, (row, source) in enumerate(zip(handlers, canonical_handlers), 1):
            if not self.exact(row, {"handler_id", "coverage_id", "milestone_id", "exclusion_id"}, "E_HANDLER_BINDING", f"handler row {index}"):
                continue
            cid = obj(source).get("coverage_id")
            self.require(row.get("handler_id") == obj(source).get("handler_id") and row.get("coverage_id") == cid, "E_HANDLER_BINDING", f"handler row {index}", "canonical identity differs")
            if cid in self.exclusion_map:
                self.require(row.get("milestone_id") is None and row.get("exclusion_id") == cid, "E_HANDLER_EXCLUSION", f"handler row {index}", "excluded handler became implementation")
            else:
                self.require(row.get("milestone_id") == self.owner_map.get(cid) and row.get("exclusion_id") is None, "E_HANDLER_BINDING", f"handler row {index}", "feature owner differs")

    def validate_source_lifecycles(self):
        # Source-specific lifecycle checks use explicit future legal-operation oracles, not a game-rule engine.
        scenario = obj(self.scenario_map.get("E2E-M1-DECLARED-PLAYABLE-EXIT"))
        fixture = obj(scenario.get("fixture"))
        initial = obj(fixture.get("initial_state"))
        for field, expected in (("funds", 0), ("auto_clippers", 0), ("auto_clipper_current_cost", 5.0), ("auto_clipper_reveal_latch", False)):
            self.require(initial.get(field) == expected, "E_AUTOCLIPPER_COST", "E2E-M1.initial_state", f"{field} must be {expected}")
        expected_cases = [
            {"case": "exact_threshold_first_purchase", "funds_before": 5.0, "current_cost_before": 5.0, "producer_count_before": 0, "accepted": True, "charge": 5.0, "funds_after": 0.0, "producer_count_after": 1, "current_cost_after": 6.1, "reveal_after": True},
            {"case": "successor_second_distinct_purchase", "funds_before": 20.0, "current_cost_before": 6.1, "producer_count_before": 1, "accepted": True, "charge": 6.1, "funds_after": 13.9, "producer_count_after": 2, "current_cost_after": 6.21, "reveal_after": True},
            {"case": "rejected_below_current_price", "funds_before": 4.99, "current_cost_before": 5.0, "producer_count_before": 0, "accepted": False, "charge": 0.0, "funds_after": 4.99, "producer_count_after": 0, "current_cost_after": 5.0, "reveal_after": True},
        ]
        case_fields = set(expected_cases[0])
        cases = arr(fixture.get("auto_clipper_cost_cases"))
        self.require(len(cases) == 3, "E_AUTOCLIPPER_COST", "E2E-M1.auto_clipper_cost_cases", "threshold, successor, and rejected rows are required")
        for index, expected in enumerate(expected_cases):
            row = cases[index] if index < len(cases) else None
            where = f"E2E-M1.auto_clipper_cost_cases[{index}]"
            if not self.exact(row, case_fields, "E_AUTOCLIPPER_COST", where):
                continue
            for field, expected_value in expected.items():
                actual = row.get(field)
                if field in {"accepted", "reveal_after"}:
                    good = actual is expected_value
                elif field == "case":
                    good = actual == expected_value and isinstance(actual, str)
                else:
                    good = actual == expected_value and isinstance(actual, (int, float)) and not isinstance(actual, bool)
                self.require(good, "E_AUTOCLIPPER_COST", where + "." + field, f"expected {expected_value!r}, got {actual!r}")
        retry = obj(fixture.get("retry_expectation"))
        retry_expected = {"command_id": "first-auto-threshold", "receipt_charge": 5.0, "receipt_producer_count": 1, "receipt_next_cost": 6.1, "additional_charge": 0.0, "additional_producer_count": 0, "producer_count_after": 2, "current_cost_after": 6.21}
        self.exact(retry, set(retry_expected), "E_AUTOCLIPPER_COST", "E2E-M1.retry_expectation")
        for field, expected in retry_expected.items():
            self.require(retry.get(field) == expected, "E_AUTOCLIPPER_COST", "E2E-M1.retry_expectation." + field, f"expected {expected!r}")
        snapshots = arr(fixture.get("snapshot_expectations"))
        expected_snapshots = [(1, 6.1), (2, 6.21)]
        self.require(len(snapshots) == 2, "E_AUTOCLIPPER_COST", "E2E-M1.snapshot_expectations", "stored count/cost/reveal rows for both purchases are required")
        for index, (count, cost) in enumerate(expected_snapshots):
            row = obj(snapshots[index] if index < len(snapshots) else None)
            self.require(row.get("producer_count") == count and row.get("current_cost") == cost and row.get("reveal") is True and row.get("offline_progress") == 0, "E_AUTOCLIPPER_COST", f"E2E-M1.snapshot_expectations[{index}]", "stored count/cost/reveal and no backfill must be exact")
        expected_ops = [
            "start_fresh_default_server_and_open_two_anonymous_pages_plus_one_agent",
            "produce_and_sell_manually_until_first_funds_5_with_zero_successful_wire_or_marketing_purchases_before_observation",
            "observe_first_funds_5_reveal_and_stored_cost_5_before_any_wire_or_marketing_purchase",
            "purchase_first_auto_clipper_at_stored_cost_5_charge_5_count_1_next_cost_6_10",
            "attempt_below_current_cost_and_verify_no_funds_count_cost_or_ledger_mutation",
            "fund_current_quote_wire_and_initial_marketing_after_first_reveal_and_verify_permanent_latch_after_funds_fall_below_5",
            "purchase_second_auto_clipper_with_distinct_intent_at_current_cost_6_10_count_2_next_cost_6_21",
            "retry_first_threshold_command_id_and_receive_first_terminal_receipt_without_mutation",
            "close_pages_and_streams_then_reconnect_and_snapshot_restart_to_verify_no_pause_backfill_or_fork",
        ]
        actual_ops = [obj(step).get("op") for step in arr(scenario.get("steps"))]
        self.require(actual_ops == expected_ops, "E_AUTOCLIPPER_COST", "E2E-M1.steps", "first reveal/first purchase must precede Wire/Marketing; successor, rejected, retry, and no-backfill steps remain ordered")
        # M2 owns ordinary compute; only M3 owns the actual Xavier purchase, and the alias retains both contexts.
        xavier = obj(self.scenario_map.get("E2E-XAVIER-ALLOCATION-RESET"))
        cpu = obj(self.scenario_map.get("ENG-TRUST-OPS-CREATIVITY"))
        self.require(xavier.get("milestone_ids") == ["M3"], "E_STAGE_SCENARIO", "E2E-XAVIER-ALLOCATION-RESET.milestone_ids", "actual Xavier purchase is M3 only")
        self.require(cpu.get("milestone_ids") == ["M2"], "E_STAGE_SCENARIO", "ENG-TRUST-OPS-CREATIVITY.milestone_ids", "independent compute acceptance is M2 only")
        m2 = obj(self.milestone_map.get("M2"))
        m3 = obj(self.milestone_map.get("M3"))
        self.require("E2E-XAVIER-ALLOCATION-RESET" not in arr(m2.get("scenario_ids")), "E_STAGE_SCENARIO", "M2.scenario_ids", "M2 cannot require the M3 project purchase")
        self.require("ENG-TRUST-OPS-CREATIVITY" in arr(m2.get("scenario_ids")), "E_STAGE_SCENARIO", "M2.scenario_ids", "M2 independent compute scenario is required")
        self.require("E2E-XAVIER-ALLOCATION-RESET" in arr(m3.get("scenario_ids")), "E_STAGE_SCENARIO", "M3.scenario_ids", "M3 must retain actual Xavier acceptance")
        for tid in ("M2-C01", "M2-C02", "M2-C03"):
            task = obj(self.task_map.get(tid))
            self.require("ENG-TRUST-OPS-CREATIVITY" in arr(task.get("scenario_ids")) and "E2E-XAVIER-ALLOCATION-RESET" not in arr(task.get("scenario_ids")), "E_STAGE_SCENARIO", tid + ".scenario_ids", "all M2 mirrors use independent compute, never the M3 purchase")
        reset = next((row for row in arr(self.plan.get("alias_traces")) if obj(row).get("id") == "RESET-HUMAN-001"), {})
        self.require(reset.get("scenario_ids") == ["ENG-TRUST-OPS-CREATIVITY", "E2E-XAVIER-ALLOCATION-RESET", "E2E-FULL-PHASE-ENGINE-TRACE"], "E_STAGE_SCENARIO", "RESET-HUMAN-001.scenario_ids", "alias retains independent M2 compute and actual M3 project contexts")
        self.require("PRJ-096" in arr(reset.get("related_feature_ids")) and self.owner_map.get("PRJ-096") == "M3" and self.owner_task.get("PRJ-096") == "M3-C01", "E_STAGE_SCENARIO", "RESET-HUMAN-001/PRJ-096", "primary Xavier ownership cannot drift")
        steps_text = json.dumps(cpu.get("steps"), ensure_ascii=False)
        self.require("purchase_Xavier" not in steps_text, "E_STAGE_SCENARIO", "ENG-TRUST-OPS-CREATIVITY.steps", "M2 arithmetic must not call purchase_Xavier")
        xavier_charges = [obj(step).get("creativity_spent") for step in arr(xavier.get("steps")) if "creativity_spent" in obj(step)]
        self.require(xavier_charges == [100000, 100000], "E_STAGE_SCENARIO", "E2E-XAVIER-ALLOCATION-RESET.steps", "two real Human-stage purchases each cost 100000 Creativity")

    def validate_scenarios_invariants_technical(self):
        # Invariant records always connect canonical owners to relevant scenario and source evidence.
        records = arr(self.plan.get("invariants"))
        ids = []
        for index, row in enumerate(records):
            if not self.exact(row, {"id", "requirement", "owner_feature_ids", "scenario_ids", "spec_refs"}, "E_INVARIANT_SCHEMA", f"invariants[{index}]"):
                continue
            iid = row.get("id")
            if isinstance(iid, str):
                ids.append(iid)
            self.string(row.get("requirement"), "E_INVARIANT_SCHEMA", f"{iid}.requirement")
            owners = self.strings(row.get("owner_feature_ids"), "E_INVARIANT_SCHEMA", f"{iid}.owner_feature_ids", unique=True)
            self.require(set(owners) <= set(self.feature_map), "E_INVARIANT_SCHEMA", str(iid), "invariant owners must be canonical features")
            required_mids = {self.owner_map.get(fid) for fid in owners}
            covered = set()
            for sid in self.strings(row.get("scenario_ids"), "E_SCENARIO_REFERENCE", f"{iid}.scenario_ids", unique=True):
                scenario = self.scenario_map.get(sid)
                self.require(scenario is not None, "E_SCENARIO_REFERENCE", str(iid), f"unknown scenario {sid}")
                covered.update(arr(obj(scenario).get("milestone_ids")))
            self.require(required_mids <= covered, "E_INVARIANT_SCENARIO", str(iid), "scenario union does not cover all owner milestones")
            self.spec_refs(row.get("spec_refs"), f"{iid}.spec_refs")
        self.require(set(ids) == EXPECTED_INVARIANTS, "E_INVARIANT_SET", "invariants", "exact twelve required invariant IDs")
        self.require(not duplicates(ids), "E_INVARIANT_SET", "invariants", "duplicate invariant ID")
        technical = obj(self.plan.get("technical_contract"))
        self.exact(technical, {"status", "confirmed", "proposed", "later_platform_sequencing", "verification_status"}, "E_TECHNICAL_CONTRACT", "technical_contract")
        self.string(technical.get("status"), "E_TECHNICAL_CONTRACT", "technical_contract.status")
        self.strings(technical.get("confirmed"), "E_TECHNICAL_CONTRACT", "technical_contract.confirmed")
        for index, row in enumerate(arr(technical.get("proposed"))):
            self.exact(row, {"choice", "default", "proof"}, "E_TECHNICAL_CONTRACT", f"technical_contract.proposed[{index}]")
            for field in ("choice", "default", "proof"):
                self.string(obj(row).get(field), "E_TECHNICAL_CONTRACT", f"technical_contract.proposed[{index}].{field}")
        self.require(len(arr(technical.get("proposed"))) == 7, "E_TECHNICAL_CONTRACT", "technical_contract.proposed", "seven explicit engineering-choice rows required")
        self.require(len(arr(technical.get("later_platform_sequencing"))) == 7, "E_TECHNICAL_CONTRACT", "technical_contract.later_platform_sequencing", "seven platform capability rows required")
        for index, row in enumerate(arr(technical.get("later_platform_sequencing"))):
            where = f"technical_contract.later_platform_sequencing[{index}]"
            self.exact(row, {"capability", "depends_on", "supporting_boundaries", "proof"}, "E_TECHNICAL_CONTRACT", where)
            self.string(obj(row).get("capability"), "E_TECHNICAL_CONTRACT", where + ".capability")
            self.string(obj(row).get("depends_on"), "E_TECHNICAL_CONTRACT", where + ".depends_on")
            self.string(obj(row).get("proof"), "E_TECHNICAL_CONTRACT", where + ".proof")
            self.strings(row.get("supporting_boundaries") if isinstance(row, dict) else None, "E_TECHNICAL_CONTRACT", where + ".supporting_boundaries", unique=True)
        status = obj(technical.get("verification_status"))
        self.exact(status, {"game_implementation_exists", "cargo_browser_sqlite_game_tests_executed", "planning_cli", "github_actions", "required_followup"}, "E_TECHNICAL_CONTRACT", "technical_contract.verification_status")
        for field in ("game_implementation_exists", "cargo_browser_sqlite_game_tests_executed"):
            self.require(status.get(field) is False, "E_EXECUTION_STATUS", f"technical_contract.verification_status.{field}", "candidate must not claim an existing game or executed game tests")
        for field in ("planning_cli", "github_actions", "required_followup"):
            self.string(status.get(field), "E_EXECUTION_STATUS", f"technical_contract.verification_status.{field}")

    def validate_scenarios(self):
        scenarios = arr(self.plan.get("scenario_catalog"))
        ids = []
        for index, row in enumerate(scenarios):
            if not self.exact(row, SCENARIO_KEYS, "E_SCENARIO_SCHEMA", f"scenario_catalog[{index}]", optional=("notes",)):
                continue
            sid = row.get("id")
            if isinstance(sid, str):
                ids.append(sid)
                if sid in self.scenario_map:
                    self.e("E_SCENARIO_DUPLICATE", sid, "duplicate scenario ID")
                else:
                    self.scenario_map[sid] = row
            self.string(row.get("title"), "E_SCENARIO_SCHEMA", f"{sid}.title")
            self.require(row.get("status") == "DESIGN_ONLY_NOT_EXECUTED", "E_SCENARIO_STATUS", str(sid), "planned scenario cannot claim execution")
            mids = self.strings(row.get("milestone_ids"), "E_SCENARIO_SCHEMA", f"{sid}.milestone_ids", unique=True)
            self.require(bool(mids) and set(mids) <= set(MID_ORDER), "E_SCENARIO_REFERENCE", str(sid), "unknown/empty milestone set")
            layers = self.strings(row.get("layers"), "E_TEST_LAYER", f"{sid}.layers", unique=True)
            self.require(bool(layers) and set(layers) <= LAYERS, "E_TEST_LAYER", str(sid), "unknown/empty test layers")
            self.spec_refs(row.get("spec_refs"), f"{sid}.spec_refs")
            coverage = self.strings(row.get("canonical_coverage_ids"), "E_SCENARIO_COVERAGE", f"{sid}.canonical_coverage_ids", nonempty=False, unique=True)
            self.require(set(coverage) <= set(self.feature_map) | set(self.alias_map), "E_SCENARIO_COVERAGE", str(sid), "unknown coverage ID or exclusion presented as feature")
            self.string(row.get("run_policy"), "E_SCENARIO_SCHEMA", f"{sid}.run_policy")
            self.require(isinstance(row.get("fixture"), dict), "E_SCENARIO_SCHEMA", str(sid), "fixture must be object")
            fixture = obj(row.get("fixture"))
            for field in ("public_resource_write_api", "public_pause_step_api", "public_bare_reset_api"):
                if field in fixture:
                    self.require(fixture[field] is False, "E_FIXTURE_AUTHORITY", f"{sid}.fixture.{field}", "no production cheat/pause/reset fixture capability")
            self.require(isinstance(row.get("steps"), list) and bool(row.get("steps")), "E_SCENARIO_SCHEMA", str(sid), "steps must be nonempty array")
            self.strings(row.get("assertions"), "E_SCENARIO_SCHEMA", f"{sid}.assertions")
            if "notes" in row:
                self.string(row.get("notes"), "E_SCENARIO_SCHEMA", f"{sid}.notes")
        for sid in duplicates(ids):
            self.e("E_SCENARIO_DUPLICATE", sid, "duplicate scenario row")
        self.require(len(ids) == len(EXPECTED_SCENARIOS) and set(ids) == EXPECTED_SCENARIOS, "E_SCENARIO_SET", "scenario_catalog", "complete unique planned scenario ID set required")

    def public_file(self, path: Path, private_lines: set[str]):
        try:
            relative = path.resolve().relative_to(self.root)
            text = path.read_text(encoding="utf-8")
        except Exception:
            self.e("E_PUBLIC_DOCUMENT", str(path.name), "missing/unreadable candidate file")
            return ""
        label = str(relative)
        self.require(not CJK.search(text), "E_PUBLIC_CJK", label, "non-English CJK content")
        self.require(not PRIVATE_PATH.search(text), "E_PUBLIC_PRIVATE_PATH", label, "private absolute path or machine/user identifier")
        self.require(not SECRET.search(text), "E_PUBLIC_SECRET", label, "credential-shaped content")
        for marker in PLACEHOLDERS:
            self.require(marker not in text, "E_PLACEHOLDER", label, "unresolved integration placeholder")
        if any(line.strip() in private_lines for line in text.splitlines()):
            self.e("E_PUBLIC_RAW_SOURCE", label, "identical long private/source line")
        if path.suffix == ".md":
            for target in LINK.findall(text):
                target = target.strip().split()[0].strip("<>")
                if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                decoded = target.split("#", 1)[0]
                for _ in range(2):
                    decoded = unquote(decoded)
                if not decoded:
                    continue
                candidate_path = Path(decoded)
                if candidate_path.is_absolute():
                    self.e("E_LINK_UNSAFE", label, "absolute Markdown target")
                    continue
                # Ordinary ../ links are valid only when their resolved target stays in this repository.
                candidate = path.parent / candidate_path
                try:
                    candidate.resolve().relative_to(self.root)
                except ValueError:
                    self.e("E_LINK_UNSAFE", label, "link escapes repository root")
                    continue
                if not candidate.exists():
                    self.e("E_LINK_MISSING", label, "missing local Markdown link target")
        return text

    def validate_public(self):
        documents = obj(self.plan.get("documents"))
        self.exact(documents, {"narrative", "milestone_summary", "requirements_index"}, "E_DOCUMENT_SCHEMA", "documents")
        expected = {"narrative": "requirements/execution-plan.md", "milestone_summary": "requirements/milestones.md", "requirements_index": "requirements/README.md"}
        self.require(documents == expected, "E_DOCUMENT_SCHEMA", "documents", "three real public Markdown paths required")
        private_lines = set()
        if self.private_source_dir:
            try:
                names = ("index2.html", "globals.js", "projects.js", "main.js", "combat.js")
                for name in names:
                    path = self.private_source_dir / name
                    if path.is_file():
                        for line in path.read_text(encoding="utf-8").splitlines():
                            if len(line.strip()) >= 100:
                                private_lines.add(line.strip())
            except Exception:
                self.e("E_INPUT", "private-source-dir", "unreadable optional private input")
        files = [self.root / documents.get(field, expected[field]) for field in expected]
        files += [self.root / "requirements/data/execution-plan.json", self.root / "scripts/validate_execution_plan.py", self.root / ".github/workflows/validate-plan.yml"]
        texts = {}
        for path in files:
            texts[str(path)] = self.public_file(path, private_lines)
        self.narrative = texts.get(str(self.root / expected["narrative"]), "")
        for fid in self.feature_map:
            self.require(f"`{fid}`" in self.narrative, "E_NARRATIVE_FEATURE", "execution-plan.md", f"missing readable feature ID {fid}")
        for xid, row in self.exclusion_map.items():
            self.require(f"`{xid}`" in self.narrative, "E_NARRATIVE_EXCLUSION", "execution-plan.md", f"missing exclusion {xid}")
            self.require(row.get("reason") in self.narrative, "E_NARRATIVE_EXCLUSION", "execution-plan.md", f"missing canonical exclusion reason for {xid}")
        for aid, row in self.alias_map.items():
            self.require(token(self.narrative, aid), "E_NARRATIVE_ALIAS", "execution-plan.md", f"missing readable alias token {aid}")
        for row in arr(obj(self.inventory.get("source_bindings")).get("projects")):
            official = obj(row).get("official_id")
            self.require(f"`{official}`" in self.narrative, "E_NARRATIVE_PROJECT", "execution-plan.md", f"missing official project {official}")
        for row in arr(obj(self.inventory.get("source_bindings")).get("html_handlers")):
            hid = obj(row).get("handler_id")
            self.require(f"`{hid}`" in self.narrative, "E_NARRATIVE_HANDLER", "execution-plan.md", f"missing handler {hid}")
        for iid in EXPECTED_INVARIANTS:
            self.require(token(self.narrative, iid), "E_NARRATIVE_INVARIANT", "execution-plan.md", f"missing invariant {iid}")
        for phrase in ("5 | 10 | 5 | 0", "0.5 | 0.2 | 0 | 0.5", "1 | 0.2 | 0.2 | 0.8", "project131 is PRJ-071 Combat", "project121 is PRJ-064 Name the battles", "no subsequent restart control"):
            self.require(phrase in self.narrative, "E_NARRATIVE_INVARIANT", "execution-plan.md", "missing high-risk readable trace")

    def run(self, plan, inventory, raw_bytes):
        self.plan = plan if isinstance(plan, dict) else {}
        self.inventory = inventory if isinstance(inventory, dict) else {}
        self.exact(plan, ROOT_KEYS, "E_ROOT_SCHEMA", "execution-plan")
        self.integer(obj(plan).get("schema_version"), 1, "E_SCHEMA_VERSION", "schema_version")
        self.require(obj(plan).get("status") == "COMPLETE_PLANNING_CANDIDATE_PENDING_REVIEW_AND_MERGE", "E_EXECUTION_STATUS", "status", "plan must remain a review/merge candidate")
        self.require(obj(plan).get("unresolved_source_conflicts") == [], "E_SOURCE_CONFLICT", "unresolved_source_conflicts", "unresolved source ambiguity blocks this plan")
        self.validate_inventory(self.inventory, raw_bytes)
        self.validate_scenarios()
        self.validate_milestones_and_tasks()
        self.validate_owners_exclusions_aliases_bindings()
        self.validate_source_lifecycles()
        self.validate_scenarios_invariants_technical()
        self.validate_public()
        self.stats["milestones"] = len(arr(plan.get("milestones"))) if isinstance(plan, dict) else 0
        self.stats["scenarios"] = len(arr(plan.get("scenario_catalog"))) if isinstance(plan, dict) else 0
        return self.errors


def redact(text: str) -> str:
    text = PRIVATE_PATH.sub("<private-path>", text)
    text = SECRET.sub("<redacted>", text)
    return text[:4000]


def run_cli(args) -> int:
    try:
        plan = load_json(args.plan)
        root = args.repo_root.resolve() if args.repo_root else Path(__file__).resolve().parents[1]
        inventory_path = root / "requirements/data/gameplay-inventory.json"
        raw = inventory_path.read_bytes()
        inventory = load_json(inventory_path)
        if args.private_source_dir:
            for name in ("index2.html", "globals.js", "projects.js", "main.js", "combat.js"):
                (args.private_source_dir / name).read_text(encoding="utf-8")
    except (InputError, OSError, ValueError) as exc:
        print("E_INPUT: unreadable input, malformed JSON, or duplicate object key")
        return 2
    checker = Checker(root, args.plan, args.private_source_dir)
    try:
        errors = checker.run(plan, inventory, raw)
    except (OSError, UnicodeError, TypeError, ValueError, KeyError, IndexError) as exc:
        # Expected malformed shapes must become deterministic validation errors, never tracebacks.
        print(f"E_VALIDATION_INTERNAL: guarded malformed-input failure ({type(exc).__name__})")
        return 1
    if errors:
        print("Execution plan validation failed (structural checks):")
        for code, locator in errors:
            print(f"- {code}: {redact(locator)}")
        return 1
    print("Execution plan structural validation passed; structural validation only, not gameplay semantics, runtime, CI, or independent approval")
    print(json.dumps(checker.stats, sort_keys=True))
    return 0


# ------------------------- isolated real-CLI self-test -------------------------

def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_plan(case_dir: Path, plan, function):
    path = case_dir / "requirements/data/execution-plan.json"
    value = copy.deepcopy(plan)
    function(value)
    write_json(path, value)


def mutate_inventory(case_dir: Path, inventory, function, reserialize=True):
    path = case_dir / "requirements/data/gameplay-inventory.json"
    value = copy.deepcopy(inventory)
    function(value)
    if reserialize:
        write_json(path, value)
    else:
        path.write_text(value, encoding="utf-8")


def append_text(path: Path, value: str):
    path.write_text(path.read_text(encoding="utf-8") + value, encoding="utf-8")


def duplicate_members_in_text(text):
    """Accept duplicate-key JSON while proving which object-local keys repeat."""
    found = []
    def inspect_pairs(pairs):
        seen = set()
        result = {}
        for key, value in pairs:
            if key in seen:
                found.append(key)
            seen.add(key)
            result[key] = value
        return result
    json.loads(text, object_pairs_hook=inspect_pairs)
    return found


def inject_duplicate_member(case_dir, kind):
    """Create valid JSON with a same-object duplicate and independently prove it."""
    if kind == "plan_root":
        path = case_dir / "requirements/data/execution-plan.json"
        text = path.read_text(encoding="utf-8")
        text = text.replace("{\n", '{\n  "schema_version": 1,\n', 1)
        expected_key = "schema_version"
    elif kind == "task_id":
        path = case_dir / "requirements/data/execution-plan.json"
        text = path.read_text(encoding="utf-8")
        anchor = '      "id": "M1-BOOTSTRAP-CI",'
        replacement = anchor + '\n      "id": "M1-BOOTSTRAP-CI",'
        if text.count(anchor) != 1:
            raise ValueError("task duplicate anchor is not unique")
        text = text.replace(anchor, replacement, 1)
        expected_key = "id"
    elif kind == "inventory_source_binding":
        path = case_dir / "requirements/data/gameplay-inventory.json"
        text = path.read_text(encoding="utf-8")
        anchor = '"official_id": "project1",'
        replacement = anchor + '\n        "official_id": "project1",'
        if text.count(anchor) != 1:
            raise ValueError("inventory source-binding anchor is not unique")
        text = text.replace(anchor, replacement, 1)
        expected_key = "official_id"
    else:
        raise ValueError("unknown duplicate-pair kind")
    found = duplicate_members_in_text(text)
    if expected_key not in found:
        raise ValueError("fixture did not create the required same-object duplicate member")
    path.write_text(text, encoding="utf-8")
    return [expected_key]


def self_test_cases():
    """Return declarative real subprocess mutations; none touches the original checkout."""
    cases = []
    def case(name, exit_code, classes, mutation=None, raw=False):
        cases.append({"name": name, "expected_exit": exit_code, "classes": classes, "mutation": mutation, "raw": raw})
    def p(name, classes, fn):
        case(name, 1, classes, ("plan", fn))
    def i(name, classes, fn):
        case(name, 1, classes, ("inventory", fn))
    def text(name, classes, rel, extra):
        case(name, 1, classes, ("text", (rel, extra)))
    case("valid-control", 0, [])
    case("duplicate-json-root-member", 2, ["E_INPUT"], ("duplicate_pair", "plan_root"))
    case("duplicate-json-task-id-member", 2, ["E_INPUT"], ("duplicate_pair", "task_id"))
    case("duplicate-json-inventory-source-binding-member", 2, ["E_INPUT"], ("duplicate_pair", "inventory_source_binding"))
    p("depends-on-not-array", ["E_TASK_FIELD"], lambda x: x["tasks"][0].update(depends_on="not-an-array"))
    p("alias-family-not-array", ["E_ALIAS_FAMILY"], lambda x: next(a for a in x["alias_traces"] if a["id"] == "SPACE-ENTRY-001").update(resolved_family_feature_ids="not-an-array"))
    p("platform-sequencing-null-row", ["E_TECHNICAL_CONTRACT"], lambda x: x["technical_contract"]["later_platform_sequencing"].__setitem__(0, None))
    p("verification-status-unexpected-key", ["E_TECHNICAL_CONTRACT"], lambda x: x["technical_contract"]["verification_status"].update(unexpectedCamelCase=True))
    case("malformed-inventory-json", 2, ["E_INPUT"], ("bad_inventory", None))
    p("schema-version-bool", ["E_SCHEMA_VERSION"], lambda x: x.update(schema_version=True))
    p("unknown-root-key", ["E_ROOT_SCHEMA"], lambda x: x.update(aliases=[]))
    p("inventory-path", ["E_INVENTORY_BINDING"], lambda x: x["inventory"].update(path="requirements/data/other.json"))
    p("inventory-schema", ["E_INVENTORY_SCHEMA"], lambda x: x["inventory"].update(schema_version=2))
    p("inventory-hash", ["E_INVENTORY_SHA"], lambda x: x["inventory"].update(sha256="0" * 64))
    p("inventory-count", ["E_INVENTORY_BINDING"], lambda x: x["inventory"].update(feature_count=273))
    p("project-relationship-hash", ["E_INVENTORY_BINDING"], lambda x: x["inventory"].update(project_bindings_sha256="0" * 64))
    p("alias-relationship-hash", ["E_INVENTORY_BINDING"], lambda x: x["inventory"].update(coverage_aliases_sha256="0" * 64))
    p("base-commit", ["E_BASELINE"], lambda x: x["planning_baseline"].update(commit="0" * 40))
    p("duplicate-feature-owner", ["E_FEATURE_DUPLICATE"], lambda x: x["feature_owners"].append(copy.deepcopy(x["feature_owners"][0])))
    p("omitted-feature-owner", ["E_FEATURE_OMITTED"], lambda x: x["feature_owners"].pop(0))
    p("unknown-feature-owner", ["E_FEATURE_UNKNOWN"], lambda x: x["feature_owners"][0].update(feature_id="ACT-NOT-REAL"))
    p("wildcards-not-owners", ["E_FEATURE_UNKNOWN"], lambda x: x["feature_owners"][0].update(feature_id="ACT-*"))
    p("exclusion-not-feature", ["E_EXCLUSION_OWNER", "E_FEATURE_UNKNOWN"], lambda x: x["feature_owners"][0].update(feature_id="ACT-SWARM-FEED"))
    p("unknown-owner-milestone", ["E_MILESTONE_REFERENCE"], lambda x: x["feature_owners"][0].update(milestone_id="M99"))
    p("noncontiguous-milestones", ["E_MILESTONE_ID"], lambda x: x["milestones"][2].update(id="M4"))
    p("duplicate-milestones", ["E_MILESTONE_DUPLICATE", "E_MILESTONE_ID"], lambda x: x["milestones"].append(copy.deepcopy(x["milestones"][1])))
    for field in ("entry", "playable", "exit"):
        p("empty-" + field, ["E_MILESTONE_CONTRACT"], lambda x, field=field: x["milestones"][0].update({field: "  "}))
    p("milestone-task-set-mismatch", ["E_MILESTONE_TASK_SET"], lambda x: x["milestones"][0]["task_ids"].pop())
    p("milestone-cycle", ["E_MILESTONE_DAG"], lambda x: x["milestones"][1].update(depends_on_milestones=["M15"]))
    p("milestone-disconnect", ["E_MILESTONE_DAG"], lambda x: x["milestones"][3].update(depends_on_milestones=[]))
    p("task-cycle", ["E_DEP_CYCLE"], lambda x: next(t for t in x["tasks"] if t["id"] == "M1-RUNTIME-CORE")["depends_on"].append({"task_id": "M1-PLAYABLE-INTEGRATION", "reason": "mutation"}))
    p("disconnected-empty-task", ["E_REACHABILITY"], lambda x: next(t for t in x["tasks"] if t["id"] == "M4-C01").update(depends_on=[]))
    p("disconnected-cycle", ["E_DEP_CYCLE"], lambda x: (next(t for t in x["tasks"] if t["id"] == "M4-C01").update(depends_on=[{"task_id": "M5-C01", "reason": "mutation"}]), next(t for t in x["tasks"] if t["id"] == "M5-C01").update(depends_on=[{"task_id": "M4-C01", "reason": "mutation"}])))
    p("unknown-dependency", ["E_DEP_UNKNOWN"], lambda x: x["tasks"][0]["depends_on"].append({"task_id": "M9-NO-SUCH", "reason": "mutation"}))
    p("self-dependency", ["E_DEP_SELF"], lambda x: x["tasks"][1]["depends_on"].append({"task_id": x["tasks"][1]["id"], "reason": "mutation"}))
    p("duplicate-dependency", ["E_DEP_DUPLICATE"], lambda x: x["tasks"][1]["depends_on"].append(copy.deepcopy(x["tasks"][1]["depends_on"][0])))
    p("cross-milestone-forward-dep", ["E_CROSS_MILESTONE"], lambda x: next(t for t in x["tasks"] if t["id"] == "M1-G01")["depends_on"].append({"task_id": "M2-C01", "reason": "mutation"}))
    p("future-fake-detail", ["E_DETAIL_GRANULARITY"], lambda x: next(t for t in x["tasks"] if t["id"] == "M3-C01").update(detail="detailed"))
    p("future-assigned-issue", ["E_FUTURE_ISSUE_ID"], lambda x: next(t for t in x["tasks"] if t["id"] == "M3-C01").update(objective="Blocked by: #123"))
    p("milestone-scenario-reciprocity", ["E_SCENARIO_RECIPROCITY"], lambda x: x["milestones"][5]["scenario_ids"].remove("E2E-FULL-PHASE-ENGINE-TRACE"))
    p("catalog-scenario-reciprocity", ["E_SCENARIO_RECIPROCITY"], lambda x: next(s for s in x["scenario_catalog"] if s["id"] == "E2E-FULL-PHASE-ENGINE-TRACE")["milestone_ids"].remove("M6"))
    p("coarse-task-scenario-reciprocity", ["E_TASK_SCENARIO"], lambda x: next(t for t in x["tasks"] if t["id"] == "M7-C01")["scenario_ids"].remove("E2E-FULL-PHASE-ENGINE-TRACE"))
    p("unknown-risk", ["E_RISK_FLAG"], lambda x: x["tasks"][0]["risk_flags"].append("unknown"))
    p("unknown-layer", ["E_TEST_LAYER"], lambda x: x["milestones"][0]["test_layers"].append("unknown"))
    p("duplicate-acceptance-id", ["E_ACCEPTANCE_DUPLICATE"], lambda x: x["tasks"][1]["acceptance_criteria"][1].update(id=x["tasks"][1]["acceptance_criteria"][0]["id"]))
    p("acceptance-without-test", ["E_TASK_TEST_COVERAGE"], lambda x: x["tasks"][1]["required_tests"].pop(0))
    p("m1-full-contract-required", ["E_TASK_ACCEPTANCE_FIELD"], lambda x: x["tasks"][0].update(non_goals=[]))
    p("m1-feature-needs-gameplay-owner", ["E_FEATURE_TASK_OWNER"], lambda x: next(o for o in x["feature_owners"] if o["feature_id"] == "ACT-CLIP-MANUAL").update(owning_task_id="M1-RUNTIME-CORE"))
    p("missing-heading", ["E_SPEC_HEADING"], lambda x: x["tasks"][0]["spec_refs"][0].update(heading="No such heading"))
    p("doc-traversal", ["E_SPEC_DOCUMENT"], lambda x: x["tasks"][0]["spec_refs"][0].update(document="requirements/../AGENTS.md"))
    text("missing-markdown-link", ["E_LINK_MISSING"], "requirements/execution-plan.md", "\n[missing](./no-such-file.md)\n")
    text("encoded-traversal-link", ["E_LINK_UNSAFE"], "requirements/execution-plan.md", "\n[escape](%2e%2e/%2e%2e/outside.md)\n")
    text("absolute-link", ["E_LINK_UNSAFE"], "requirements/execution-plan.md", "\n[absolute](/tmp/example.md)\n")
    text("private-path", ["E_PUBLIC_PRIVATE_PATH"], "requirements/execution-plan.md", "\n" + "/" + "Users" + "/private/file.md\n")
    text("private-path-readme", ["E_PUBLIC_PRIVATE_PATH"], "requirements/README.md", "\n" + "/" + "tmp" + "/" + "agents" + "/private/result.md\n")
    text("public-cjk", ["E_PUBLIC_CJK"], "requirements/execution-plan.md", "\n\u8ba1\n")
    case("public-japanese-kana", 1, ["E_PUBLIC_CJK"], ("text_codepoint", ("requirements/execution-plan.md", 0x30A2)))
    case("public-korean-hangul", 1, ["E_PUBLIC_CJK"], ("text_codepoint", ("requirements/execution-plan.md", 0xAC00)))
    text("secret-shape", ["E_PUBLIC_SECRET"], "requirements/README.md", "\napi_key = \"synthetic-not-a-credential\"\n")
    case("raw-long-line", 1, ["E_PUBLIC_RAW_SOURCE"], ("raw_line", None))
    case("missing-private-source-input", 2, ["E_INPUT"], ("missing_sources", None))
    p("alias-trace-omitted", ["E_ALIAS_OMITTED"], lambda x: x["alias_traces"].pop(0))
    p("alias-trace-duplicated", ["E_ALIAS_DUPLICATE"], lambda x: x["alias_traces"].append(copy.deepcopy(x["alias_traces"][0])))
    p("alias-owner-wrong", ["E_ALIAS_OWNER"], lambda x: next(a for a in x["alias_traces"] if a["id"] == "PROBE-TRUST-001").update(milestone_ids=["M11"]))
    def all19(x):
        a = next(a for a in x["alias_traces"] if a["id"] == "PROBE-DESIGN-001")
        a["resolved_family_feature_ids"] = [f["id"] for f in json.loads((Path(__file__).resolve().parents[1] / "requirements/data/gameplay-inventory.json").read_text())["features"] if f["id"].startswith("ACT-PROBE-")]
    p("family-expansion-19-is-wrong", ["E_ALIAS_FAMILY"], all19)
    i("family-empty-in-canonical", ["E_ALIAS_FAMILY"], lambda x: next(a for a in x["coverage_aliases"] if a["id"] == "PROBE-DESIGN-001").update(families=[]))
    i("alias-bad-target", ["E_ALIAS_TARGET"], lambda x: next(a for a in x["coverage_aliases"] if a["id"] == "PROBE-TRUST-001").update(targets=["ACT-NOT-REAL"]))
    i("alias-document-token-drift", ["E_ALIAS_DOCUMENT"], lambda x: x.update(coverage_aliases=[dict(a, documents=["requirements/gameplay-projects.md"]) if a["id"] == "PROBE-DESIGN-001" else a for a in x["coverage_aliases"]]))
    p("project-order-drift", ["E_PROJECT_BINDING"], lambda x: x["source_binding_owners"]["projects"][0].update(official_id=x["source_binding_owners"]["projects"][1]["official_id"]))
    i("sourcebound-project-excluded", ["E_PROJECT_BINDING"], lambda x: x["source_bindings"]["projects"][0].update(coverage_id="ACT-SWARM-FEED"))
    i("sourcebound-project-unknown", ["E_PROJECT_BINDING"], lambda x: x["source_bindings"]["projects"][1].update(coverage_id="PRJ-NOT-REAL"))
    i("sourcebound-handler-unknown", ["E_HANDLER_BINDING"], lambda x: x["source_bindings"]["html_handlers"][0].update(coverage_id="ACT-NOT-REAL"))
    p("excluded-handler-implementation", ["E_HANDLER_EXCLUSION"], lambda x: next(h for h in x["source_binding_owners"]["html_handlers"] if h["exclusion_id"] is not None).update(milestone_id="M8", exclusion_id=None))
    p("required-invariant-omitted", ["E_INVARIANT_SET"], lambda x: x["invariants"].pop(0))
    p("unknown-scenario-reference", ["E_SCENARIO_REFERENCE"], lambda x: x["alias_traces"][0]["scenario_ids"].append("NO-SUCH-SCENARIO"))
    p("duplicate-scenario", ["E_SCENARIO_DUPLICATE", "E_SCENARIO_SET"], lambda x: x["scenario_catalog"].append(copy.deepcopy(x["scenario_catalog"][0])))
    p("scenario-cannot-claim-pass", ["E_SCENARIO_STATUS"], lambda x: x["scenario_catalog"][0].update(status="PASSED"))
    p("scenario-no-cheat-fixture", ["E_FIXTURE_AUTHORITY"], lambda x: x["scenario_catalog"][0]["fixture"].update(public_resource_write_api=True))
    p("scenario-unknown-coverage", ["E_SCENARIO_COVERAGE"], lambda x: x["scenario_catalog"][0]["canonical_coverage_ids"].append("NO-SUCH-COVERAGE"))
    p("driftwar-universal-forbidden", ["E_COMPLETION_GATE"], lambda x: x["milestones"][11].update(depends_on_milestones=["M10", "M11"]))
    p("reject-accept-independent", ["E_BRANCH_DEPENDENCY"], lambda x: x["milestones"][13].update(depends_on_milestones=["M12", "M13"]))
    p("m15-branch-join-required", ["E_BRANCH_DEPENDENCY"], lambda x: x["milestones"][14].update(depends_on_milestones=["M11", "M12", "M14"]))
    text("narrative-feature-omitted", ["E_NARRATIVE_FEATURE"], "requirements/execution-plan.md", "")
    # The preceding case uses a special removal mutation below.
    cases.pop()
    case("narrative-feature-omitted", 1, ["E_NARRATIVE_FEATURE"], ("remove_text", ("requirements/execution-plan.md", "`ACT-CLIP-MANUAL`")))
    case("narrative-handler-omitted", 1, ["E_NARRATIVE_HANDLER"], ("remove_text", ("requirements/execution-plan.md", "`HTML-061`")))
    case("narrative-invariant-omitted", 1, ["E_NARRATIVE_INVARIANT"], ("remove_text", ("requirements/execution-plan.md", "INV-COMMAND-RETRY")))
    text("placeholder-narrative", ["E_PLACEHOLDER"], "requirements/execution-plan.md", "\nOWNING" + "_MILESTONE\n")
    p("placeholder-task", ["E_PLACEHOLDER"], lambda x: x["tasks"][0].update(objective=x["tasks"][0]["objective"] + " gameplay" + "-map.m1.unresolved"))
    p("coarse-over-detailed", ["E_COARSE_CONTRACT"], lambda x: next(t for t in x["tasks"] if t["id"] == "M3-C01").update(non_goals=["fake current detail"]))
    p("wrong-container-types", ["E_TASK_SCHEMA"], lambda x: x.update(tasks={}))
    p("autoclipper-cost-lifecycle", ["E_AUTOCLIPPER_COST"], lambda x: next(s for s in x["scenario_catalog"] if s["id"] == "E2E-M1-DECLARED-PLAYABLE-EXIT")["fixture"]["auto_clipper_cost_cases"][0].update(current_cost_after=6.0))
    p("xavier-m2-dependency-cycle", ["E_STAGE_SCENARIO"], lambda x: next(s for s in x["scenario_catalog"] if s["id"] == "E2E-XAVIER-ALLOCATION-RESET")["milestone_ids"].insert(0, "M2"))
    # Valid JSON with hostile nested shapes must fail safely through the explicit guarded fallback.
    p("nested-task-milestone-list", ["E_VALIDATION_INTERNAL"], lambda x: x["tasks"][0].update(milestone_id=["M1"]))
    p("nested-owner-feature-dict", ["E_VALIDATION_INTERNAL"], lambda x: x["feature_owners"][0].update(feature_id={"invalid": 1}))
    p("nested-milestone-layers", ["E_VALIDATION_INTERNAL"], lambda x: x["milestones"][0].update(test_layers=[{"layer": "rule_unit"}]))
    p("nested-milestone-id", ["E_VALIDATION_INTERNAL"], lambda x: x["milestones"][0].update(id={"invalid": 1}))
    i("nested-canonical-alias-target-object", ["E_VALIDATION_INTERNAL"], lambda x: x["coverage_aliases"][0].update(targets=[{"invalid": 1}]))
    return cases


def run_self_test(args) -> int:
    script = Path(__file__).resolve()
    source_root = script.parents[1]
    try:
        valid_plan = load_json(args.plan)
        valid_inventory = load_json(source_root / "requirements/data/gameplay-inventory.json")
    except (InputError, OSError):
        print("SELF-TEST HARNESS FAILURE: cannot read valid public control")
        return 1
    results = []
    harness_failures = []
    with tempfile.TemporaryDirectory(prefix="validate-execution-plan-") as temporary:
        temp_root = Path(temporary)
        fixture = temp_root / "fixture"
        try:
            shutil.copytree(source_root / "requirements", fixture / "requirements")
            (fixture / "scripts").mkdir(parents=True)
            for name in ("validate_execution_plan.py", "validate_inventory.py"):
                shutil.copy2(source_root / "scripts" / name, fixture / "scripts" / name)
            shutil.copy2(source_root / "AGENTS.md", fixture / "AGENTS.md")
            (fixture / ".github/workflows").mkdir(parents=True)
            shutil.copy2(source_root / ".github/workflows/validate-plan.yml", fixture / ".github/workflows/validate-plan.yml")
            write_json(fixture / "requirements/data/execution-plan.json", valid_plan)
            # Preserve canonical exact bytes, not a reserialization hash accident.
            shutil.copy2(source_root / "requirements/data/gameplay-inventory.json", fixture / "requirements/data/gameplay-inventory.json")
        except OSError as exc:
            print(f"SELF-TEST HARNESS FAILURE: {type(exc).__name__} while preparing isolated fixture")
            return 1
        cases = self_test_cases()
        for number, spec in enumerate(cases, 1):
            case_dir = temp_root / f"case-{number:03d}"
            try:
                shutil.copytree(fixture, case_dir)
                plan_path = case_dir / "requirements/data/execution-plan.json"
                mutation = spec["mutation"]
                private_arg = []
                duplicate_proof = None
                if mutation:
                    kind, payload = mutation
                    if kind == "plan":
                        mutate_plan(case_dir, valid_plan, payload)
                    elif kind == "inventory":
                        mutate_inventory(case_dir, valid_inventory, payload)
                    elif kind == "text":
                        rel, extra = payload
                        append_text(case_dir / rel, extra)
                    elif kind == "text_codepoint":
                        rel, codepoint = payload
                        append_text(case_dir / rel, "\n" + chr(codepoint) + "\n")
                    elif kind == "remove_text":
                        rel, needle = payload
                        path = case_dir / rel
                        path.write_text(path.read_text(encoding="utf-8").replace(needle, ""), encoding="utf-8")
                    elif kind == "duplicate_pair":
                        duplicate_proof = inject_duplicate_member(case_dir, payload)
                    elif kind == "bad_inventory":
                        (case_dir / "requirements/data/gameplay-inventory.json").write_text("{not json", encoding="utf-8")
                    elif kind == "missing_sources":
                        synthetic = case_dir / "missing-private-source"
                        synthetic.mkdir()
                        private_arg = ["--private-source-dir", str(synthetic)]
                    elif kind == "raw_line":
                        synthetic = case_dir / "synthetic-private-source"
                        synthetic.mkdir()
                        line = "synthetic-long-line-" + "x" * 130
                        for name in ("index2.html", "globals.js", "projects.js", "main.js", "combat.js"):
                            (synthetic / name).write_text(line + "\n", encoding="utf-8")
                        append_text(case_dir / "requirements/execution-plan.md", "\n" + line + "\n")
                        private_arg = ["--private-source-dir", str(synthetic)]
                    else:
                        raise ValueError("unknown mutation harness kind")
                command = [sys.executable, "-B", str(script), str(plan_path), "--repo-root", str(case_dir)] + private_arg
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
                completed = subprocess.run(command, cwd=case_dir, env=env, capture_output=True, text=True, timeout=25, check=False)
                output = completed.stdout + completed.stderr
                classes = sorted(set(re.findall(r"E_[A-Z_]+", output)))
                missing = [code for code in spec["classes"] if code not in classes]
                passed = completed.returncode == spec["expected_exit"] and not missing and "Traceback (most recent call last)" not in output
                if spec["expected_exit"] == 0:
                    passed = passed and "structural validation passed" in output
                result = {
                    "case": spec["name"], "expected_exit": spec["expected_exit"],
                    "actual_exit": completed.returncode, "required_classes": spec["classes"],
                    "actual_classes": classes, "missing_classes": missing,
                    "traceback": "Traceback (most recent call last)" in output,
                    "passed": passed,
                }
                if duplicate_proof:
                    result["verified_duplicate_members"] = duplicate_proof
                results.append(result)
                print(f"{spec['name']}: exit={completed.returncode} expected={spec['expected_exit']} classes={classes} missing={missing} traceback={result['traceback']} {'PASS' if passed else 'FAIL'}")
                if duplicate_proof:
                    print(f"{spec['name']}: verified_duplicate_members={duplicate_proof}")
                if not passed:
                    print(redact(output))
            except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
                harness_failures.append({"case": spec["name"], "kind": type(exc).__name__})
                print(f"{spec['name']}: SELF-TEST HARNESS FAILURE {type(exc).__name__}")
        # Failure-injection of the evaluator itself: valid input must not satisfy an intentional nonzero/class expectation.
        valid_dir = temp_root / "harness-valid"
        shutil.copytree(fixture, valid_dir)
        for label, expected_exit, expected_classes in (("unexpected-pass", 1, ["E_DEP_CYCLE"]), ("class-mismatch", 1, ["E_NOT_A_REAL_CLASS"])):
            command = [sys.executable, "-B", str(script), str(valid_dir / "requirements/data/execution-plan.json"), "--repo-root", str(valid_dir)]
            try:
                completed = subprocess.run(command, cwd=valid_dir, capture_output=True, text=True, timeout=25, check=False)
                output = completed.stdout + completed.stderr
                classes = sorted(set(re.findall(r"E_[A-Z_]+", output)))
                mutant_would_pass = completed.returncode == expected_exit and all(code in classes for code in expected_classes) and "Traceback (most recent call last)" not in output
                detector_pass = not mutant_would_pass
                results.append({"case": "harness-" + label, "expected_exit": "detector must reject", "actual_exit": completed.returncode, "required_classes": expected_classes, "actual_classes": classes, "passed": detector_pass})
                print(f"harness-{label}: detector={'PASS' if detector_pass else 'FAIL'} (valid control cannot satisfy fake negative expectation)")
                if not detector_pass:
                    harness_failures.append({"case": "harness-" + label, "kind": "unexpected evaluator pass"})
            except (OSError, subprocess.SubprocessError) as exc:
                harness_failures.append({"case": "harness-" + label, "kind": type(exc).__name__})
    failed = [row for row in results if not row["passed"]]
    negative = [row for row in results if isinstance(row["expected_exit"], int) and row["expected_exit"] != 0]
    summary = {
        "status": "PASS" if not failed and not harness_failures else "FAIL",
        "case_count": len(results), "valid_controls": 1,
        "intentional_nonzero_cases": len(negative),
        "actual_nonzero_cases": sum(1 for row in negative if isinstance(row["actual_exit"], int) and row["actual_exit"] != 0),
        "harness_detector_cases": 2,
        "failed_cases": [row["case"] for row in failed], "harness_failures": harness_failures,
    }
    print("SELF_TEST_SUMMARY " + json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--repo-root", type=Path, help="Optional isolated repository root (self-test/private use)")
    parser.add_argument("--private-source-dir", type=Path, help="Optional local-only static long-line comparison; never required by CI")
    parser.add_argument("--self-test", action="store_true", help="Run the real CLI against isolated temporary mutations")
    args = parser.parse_args(argv)
    if args.self_test and args.repo_root:
        print("E_INPUT: --self-test uses its own isolated root and does not accept --repo-root")
        return 2
    return run_self_test(args) if args.self_test else run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
