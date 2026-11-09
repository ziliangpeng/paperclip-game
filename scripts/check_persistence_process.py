#!/usr/bin/env python3
# owner: paperclip-game CI
# trigger: pull requests, main pushes, and local persistence process verification
# purpose: prove real SQLite readiness failures, crash loss bounds, and safe repeated startup
"""Bounded real-process checks for the Issue #10 persistence service."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import http.client
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any, Callable

import check_api_process as api


def launch(
    binary: Path, database: Path, temporary: Path, label: str
) -> tuple[api.Process, int, api.Client]:
    port = api.free_port()
    stdout_path = temporary / f"{label}.stdout"
    stderr_path = temporary / f"{label}.stderr"
    stdout = stdout_path.open("wb")
    stderr = stderr_path.open("wb")
    try:
        process = api.start_ready(
            binary,
            ["--listen-addr", f"127.0.0.1:{port}", "--database-path", str(database)],
            port,
            temporary,
            stdout,
            stderr,
        )
    finally:
        stdout.close()
        stderr.close()
    return process, port, api.Client(port)


def check_logs(process: api.Process, port: int, temporary: Path, label: str) -> None:
    assert (temporary / f"{label}.stdout").read_bytes() == b""
    startup = (temporary / f"{label}.stderr").read_text()
    assert startup == f"paperclip-game: listening on http://127.0.0.1:{port}\n"
    assert "SELECT" not in startup and "payload" not in startup
    assert process.process.returncode is not None, "process must have been reaped"


def stop_checked(
    process: api.Process, client: api.Client, port: int, temporary: Path, label: str
) -> None:
    client.close()
    process.stop()
    check_logs(process, port, temporary, label)



STORED_PRO_FIELDS = {
    "lifetime_clips", "unsold_clips", "unused_clips", "wire", "funds",
    "wire_spool_length", "wire_quote", "price_per_clip", "marketing_level",
    "marketing_effectiveness", "demand_boost", "prestige_u", "demand",
    "clips_sold", "income", "last_sale_revenue", "wire_base_price",
    "wire_price_counter", "wire_purchase_count", "wire_inactivity_ticks",
    "trust", "processors", "memory", "computing_hidden", "projects_hidden",
    "auto_clipper_revealed", "auto_clippers", "auto_clipper_cost",
}
INTERNAL_PRO_FIELDS = {
    "marketing_effectiveness", "demand_boost", "prestige_u", "wire_base_price",
    "wire_price_counter", "wire_purchase_count", "wire_inactivity_ticks",
}


def assert_stored_pro(pro: dict[str, Any]) -> dict[str, Any]:
    """Validate stored authority and return its exact public projection.

    Marketing cost is intentionally derived from the stored level and is not
    duplicated in ProSnapshot. The remaining internal parameters stay private
    to storage rather than being silently admitted into the public View.
    """
    assert set(pro) == STORED_PRO_FIELDS
    for field in ("wire_price_counter", "wire_purchase_count", "wire_inactivity_ticks"):
        value = pro[field]
        assert type(value) is int and 0 <= value <= api.SAFE_INTEGER
    for field in ("marketing_effectiveness", "demand_boost", "wire_base_price"):
        value = pro[field]
        assert isinstance(value, str) and re.fullmatch(
            r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", value
        )
    assert Decimal(pro["wire_base_price"]) > 0
    assert isinstance(pro["prestige_u"], str) and re.fullmatch(
        r"0|[1-9][0-9]*", pro["prestige_u"]
    )
    public = {key: value for key, value in pro.items() if key not in INTERNAL_PRO_FIELDS}
    supplied = {key: public[key] for key in api.ECONOMIC_VIEW_FIELDS if key != "marketing_cost"}
    api.assert_production(
        {"game": public}, public["wire"], public["lifetime_clips"], supplied,
        stored_model=True,
    )
    return public


AMOUNT_SCALE = 10**18
TEMPORAL_PRO_FIELDS = {
    "unsold_clips", "funds", "wire_quote", "clips_sold", "income",
    "last_sale_revenue", "wire_base_price", "wire_price_counter",
    "wire_inactivity_ticks",
}


def amount_mantissa(value: str) -> int:
    """Exact cents/mill units on the common 10^-18 Amount grid; never float."""
    sign = -1 if value.startswith("-") else 1
    unsigned = value.removeprefix("-")
    whole, separator, fraction = unsigned.partition(".")
    assert whole.isascii() and whole.isdigit()
    assert not separator or (fraction.isascii() and fraction.isdigit() and len(fraction) <= 18)
    return sign * (int(whole) * AMOUNT_SCALE + int(fraction.ljust(18, "0") or "0"))


def assert_public_sales_between_events(
    before: dict[str, str], after: dict[str, str], expected_makes: int = 0
) -> None:
    """Only real clock progress and observed production separate checkpoints.

    No business purchases are issued in these intervals. ``expected_makes``
    counts already accepted real ``make_paperclip`` commands (0 or 1 here),
    never client-granted resources. Price
    stays .25 and Marketing level 1, so each nonempty request offers exactly
    two whole clips and the available stock in this suite never exceeds two.
    """
    allowed = {
        "lifetime_clips", "unused_clips", "wire", "unsold_clips", "funds",
        "wire_quote", "clips_sold", "income", "last_sale_revenue",
    }
    different = {key: (before[key], after[key]) for key in before
                 if key not in allowed and before[key] != after[key]}
    assert not different, ("non-temporal public state changed", different)
    assert type(expected_makes) is int and expected_makes in (0, 1)
    for field, delta in (
        ("lifetime_clips", expected_makes),
        ("unused_clips", expected_makes),
        ("wire", -expected_makes),
    ):
        assert amount_mantissa(after[field]) - amount_mantissa(before[field]) == delta * AMOUNT_SCALE
    assert before["price_per_clip"] == "0.25" and before["marketing_level"] == "1"
    assert before["demand"] == "3.2" == after["demand"]
    old_sold = amount_mantissa(before["clips_sold"])
    new_sold = amount_mantissa(after["clips_sold"])
    sold_delta = new_sold - old_sold
    assert 0 <= sold_delta <= 2 * AMOUNT_SCALE and sold_delta % AMOUNT_SCALE == 0
    assert type(expected_makes) is int and expected_makes in (0, 1)
    unsold = amount_mantissa(before["unsold_clips"]) + expected_makes * AMOUNT_SCALE - sold_delta
    assert unsold == amount_mantissa(after["unsold_clips"])
    price = amount_mantissa(before["price_per_clip"])
    revenue = sold_delta * price // AMOUNT_SCALE
    assert sold_delta * price % AMOUNT_SCALE == 0
    assert amount_mantissa(after["income"]) == amount_mantissa(before["income"]) + revenue
    assert amount_mantissa(after["funds"]) == amount_mantissa(before["funds"]) + revenue
    if sold_delta == 0:
        assert after["last_sale_revenue"] == before["last_sale_revenue"]
    else:
        # With at most two available whole clips, one response may be two
        # sales or one larger sale; either last-revenue value is source-valid.
        assert amount_mantissa(after["last_sale_revenue"]) in {price, 2 * price}


def validate_clock(clock: dict[str, Any]) -> None:
    for key in ("update_count", "combat_pulses"):
        assert type(clock[key]) is int and 0 <= clock[key] <= api.SAFE_INTEGER
    for key in ("fast_phase", "second_phase", "slow_phase", "combat_remainder_nanos"):
        assert type(clock[key]) is int and clock[key] >= 0
    update = clock["update_count"]
    assert clock["fast_phase"] == update % 10
    assert clock["second_phase"] == update % 100
    assert clock["slow_phase"] == update % 250
    assert clock["combat_pulses"] == update * 5 // 8
    assert clock["combat_remainder_nanos"] == update * 10_000_000 % 16_000_000


def fast_phases_between(before: dict[str, Any], after: dict[str, Any]) -> int:
    before_clock, after_clock = before["clock"], after["clock"]
    validate_clock(before_clock)
    validate_clock(after_clock)
    assert after_clock["update_count"] >= before_clock["update_count"]
    # ClockState.advance produces fast_due at every multiple of ten updates.
    return after_clock["update_count"] // 10 - before_clock["update_count"] // 10


def assert_rng_continuation(before: str, after: str, phases: int) -> None:
    """Exact independent stream-position check, without printing seed material."""
    prior, later = bytes.fromhex(before), bytes.fromhex(after)
    assert len(prior) == len(later) == 57 and prior[0] == later[0] == 1
    # Seed and stream never change through restoration or logical advancement.
    assert prior[1:41] == later[1:41], "RNG seed or stream was reinitialized on restore"
    prior_position = int.from_bytes(prior[41:], "big")
    later_position = int.from_bytes(later[41:], "big")
    assert 0 <= prior_position < 1 << 68 and 0 <= later_position < 1 << 68
    # advance_fast_phase consumes Wire and sales next_u64 calls. rand_chacha's
    # next_u64 consumes two next_u32 calls (rand_chacha 0.10.0 + rand_core).
    expected = (prior_position + 4 * phases) % (1 << 68)
    assert later_position == expected, (prior_position, later_position, expected, phases)


def assert_snapshot_continuation(
    before: dict[str, Any], after: dict[str, Any], label: str, expected_makes: int = 0
) -> None:
    """Compare snapshots around idle process activity, including private state.

    A restart may allow real logical phases while serving the restored world;
    it must not infer unsaved commands or offline sales. Those processes alone
    cannot reproduce a generic persistent byte equality test after G02.
    """
    assert after["revision"] >= before["revision"], label
    assert after["sequence"] >= before["sequence"], label
    assert type(expected_makes) is int and expected_makes in (0, 1)
    before_public = assert_stored_pro(before["pro"])
    after_public = assert_stored_pro(after["pro"])
    phases = fast_phases_between(before, after)
    assert_rng_continuation(before["rng_state"], after["rng_state"], phases)
    different = {
        key: (before["pro"][key], after["pro"][key])
        for key in STORED_PRO_FIELDS - TEMPORAL_PRO_FIELDS - {
            "lifetime_clips", "unused_clips", "wire"
        }
        if before["pro"][key] != after["pro"][key]
    }
    assert not different, (label, "fields changed without a producer/business command", different)
    # Concrete production and its Wire consumption, as well as sale changes,
    # share one public projection checker with live View observations below.
    if phases == 0 and expected_makes == 0:
        # No economic opportunity or explicit production: preserve the former
        # exact whole-Pro and whole-RNG assertions, including private fields.
        assert after["pro"] == before["pro"], (label, "non-temporal updates cannot alter Pro")
    else:
        assert_public_sales_between_events(before_public, after_public, expected_makes)
    base = amount_mantissa(before["pro"]["wire_base_price"])
    inactivity = before["pro"]["wire_inactivity_ticks"]
    for _ in range(phases):
        inactivity += 1
        if inactivity > 250 and base > 15 * AMOUNT_SCALE:
            base = base * 999 // 1000
            inactivity = 0
    assert inactivity <= api.SAFE_INTEGER
    assert amount_mantissa(after["pro"]["wire_base_price"]) == base, (label, "Wire decay")
    assert after["pro"]["wire_inactivity_ticks"] == inactivity, (label, "Wire inactivity")
    increment = after["pro"]["wire_price_counter"] - before["pro"]["wire_price_counter"]
    assert 0 <= increment <= phases, (label, "more reprices than logical phases")
    if increment == 0:
        assert after["pro"]["wire_quote"] == before["pro"]["wire_quote"], label
    assert amount_mantissa(after["pro"]["wire_quote"]) > 0
    assert amount_mantissa(after["pro"]["wire_quote"]) % AMOUNT_SCALE == 0


def assert_view_matches_stored(
    pro: dict[str, Any], view: dict[str, Any], expected_makes: int = 0
) -> None:
    """A public observation after a stored checkpoint, allowing only clock sales.

    This is intentionally not equality with an older View: the raw RNG and
    logical phase counter checks belong to assert_snapshot_continuation.
    """
    api.assert_view_schema(view)
    before = assert_stored_pro(pro)
    after = dict(view["game"])
    # ProSnapshot stores level, not this one derived public display field.
    after.pop("marketing_cost")
    assert_public_sales_between_events(before, after, expected_makes)

def read_snapshot(database: Path) -> dict[str, Any]:
    # Only call this for a known-valid database. Startup corruption is tested
    # against original bytes without allowing SQLite to mutate the source file.
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        schema = connection.execute("PRAGMA user_version").fetchone()[0]
        # Product storage is now schema/snapshot 2. Historical V1 input is
        # migrated by the application and remains covered by its strict tests.
        assert schema == 2
        rows = connection.execute(
            "SELECT slot, snapshot_version, revision, capture_sequence, payload, checksum "
            "FROM game_snapshot"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1 and rows[0][0] == "default"
    _, version, revision, sequence, payload, checksum = rows[0]
    assert version == 2
    assert type(revision) is int and 0 <= revision <= api.SAFE_INTEGER
    assert type(sequence) is int and 0 <= sequence <= api.SAFE_INTEGER
    raw_payload = payload.encode("utf-8")
    snapshot = api.checked_json(raw_payload)
    assert set(snapshot) == {"snapshot_version", "revision", "pro", "clock", "rng_state"}
    assert type(snapshot["snapshot_version"]) is int and snapshot["snapshot_version"] == 2
    assert type(snapshot["revision"]) is int and snapshot["revision"] == revision
    assert_stored_pro(snapshot["pro"])
    assert set(snapshot["clock"]) == {
        "update_count", "fast_phase", "second_phase", "slow_phase",
        "combat_remainder_nanos", "combat_pulses",
    }
    assert len(snapshot["rng_state"]) == 114
    assert all(character in "0123456789abcdef" for character in snapshot["rng_state"])
    assert json.dumps(snapshot, separators=(",", ":")).encode() == raw_payload
    assert hashlib.sha256(raw_payload).hexdigest() == checksum
    return {
        "revision": revision,
        "sequence": sequence,
        "pro": snapshot["pro"],
        "clock": snapshot["clock"],
        "rng_state": snapshot["rng_state"],
    }


def wait_for_health(
    client: api.Client,
    expected_status: int,
    timeout: float,
    predicate: Callable[[dict[str, Any]], bool] = lambda health: True,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, raw = client.get("/api/health/ready")
        if status == expected_status:
            health = api.checked_json(raw)
            if predicate(health):
                return api.assert_ready(client, expected_status)
        time.sleep(0.02)
    raise AssertionError(f"health did not reach {expected_status} within {timeout}s")


def wait_for_update(client: api.Client, update_count: int, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view = api.checked_json(client.get()[1])
        if view["clock"]["update_count"] >= update_count:
            return view
        time.sleep(0.01)
    raise AssertionError("authoritative game clock stopped while SQLite was blocked")


def check_corrupt_startup(binary: Path, temporary: Path) -> None:
    database = temporary / "corrupt.sqlite3"
    original = b"existing-corrupt-game-not-for-reset"
    database.write_bytes(original)
    completed = subprocess.run(
        [str(binary), "--listen-addr", "127.0.0.1:0", "--database-path", str(database)],
        cwd=temporary,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 1, completed.returncode
    assert completed.stdout == b""
    assert completed.stderr == b"paperclip-game: persistence startup failed: database format is invalid\n"
    assert str(database).encode() not in completed.stderr
    assert database.read_bytes() == original
    for suffix in ("-journal", "-shm", "-wal"):
        assert not Path(str(database) + suffix).exists()
    print("process startup: corrupt existing database failed closed with sanitized diagnostics")


def check_sqlite_fault_and_health(binary: Path, temporary: Path) -> None:
    database = temporary / "fault.sqlite3"
    process, port, client = launch(binary, database, temporary, "fault")
    blocker = None
    try:
        assert client.get("/api/health/live") == (200, b'{"status":"ok"}')
        initial_health = api.assert_ready(client)
        assert initial_health["live"] is True
        assert initial_health["last_committed_revision"] == 0
        before_health_mutation = api.checked_json(client.get()[1])
        # Hold a real observer open without consuming its updates throughout the
        # existing SQLite busy window. Snapshot health and writer progress must
        # not depend on this observer draining its bounded queue.
        delayed_observer = api.SseClient(port)
        observer_initial = delayed_observer.read_event()
        assert observer_initial is not None
        # Use an actual unsupported method against health; no command is admitted.
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("POST", "/api/health/ready", body=b'{"actor":"forbidden-world"}')
        response = connection.getresponse()
        method_body = response.read()
        connection.close()
        assert response.status == 405, method_body
        after_health_mutation = api.checked_json(client.get()[1])
        assert after_health_mutation["game"] == before_health_mutation["game"]
        assert after_health_mutation["run_id"] == before_health_mutation["run_id"]

        blocker = sqlite3.connect(database, timeout=0.1)
        blocker.execute("BEGIN IMMEDIATE")
        deadline = 40
        degraded_health = wait_for_health(client, 503, deadline)
        assert degraded_health["live"] is True
        assert degraded_health["ready"] is False
        assert degraded_health["last_failure_code"] == "database_busy"
        assert degraded_health["last_committed_revision"] == 0
        assert degraded_health["latest_captured_revision"] > 0
        assert degraded_health["last_committed_revision"] < degraded_health["latest_captured_revision"]
        assert degraded_health["current_attempt"] >= 1
        assert degraded_health["phase"] in ("retrying", "degraded")

        before = api.checked_json(client.get()[1])
        applied = client.make("process-sql-busy-live-command")
        assert applied[0] == 200 and api.checked_json(applied[1])["status"] == "applied"
        after = wait_for_update(client, before["clock"]["update_count"] + 2, 2)
        assert after["game"]["wire"] == "999"
        assert after["game"]["lifetime_clips"] == "1"
        assert api.assert_ready(client, 503)["live"] is True
        delayed_observer.close()

        blocker.execute("ROLLBACK")
        blocker.close()
        blocker = None
        # Usually the same bounded retry completes. If it exhausted attempts
        # during a slow test host, the next 30-second capture may recover instead.
        recovered = wait_for_health(
            client,
            200,
            35,
            lambda health: health["last_committed_sequence"] is not None
            and health["last_committed_sequence"] >= 1,
        )
        assert recovered["last_failure_code"] is None
        assert recovered["current_attempt"] == 0
        assert recovered["consecutive_failures"] == 0
        assert recovered["snapshot_overdue"] is False
        # Reconnect is the recovery path after the delayed observer was closed
        # or disconnected; it must start from the complete current state.
        resynchronized = api.SseClient(port)
        baseline = resynchronized.read_event()
        assert baseline is not None
        assert baseline["revision"] >= observer_initial["revision"]
        assert baseline["game"]["lifetime_clips"] == "1"
        post_stop_view = api.checked_json(client.get()[1])
        stop_checked(process, client, port, temporary, "fault")
        saved = read_snapshot(database)
        assert_view_matches_stored(saved["pro"], post_stop_view)
        assert saved["revision"] >= recovered["last_committed_revision"]
        resynchronized.close()
        print("process health: active SSE + real SQLite busy/503 continued; valid commit/final stop restored storage")
    finally:
        if blocker is not None:
            blocker.execute("ROLLBACK")
            blocker.close()
        client.close()
        process.force_stop()


def check_real_kill_and_repeated_restart(binary: Path, temporary: Path) -> None:
    database = temporary / "crash.sqlite3"
    run_ids = []
    first, first_port, first_client = launch(binary, database, temporary, "crash-save")
    try:
        saved_command = first_client.make("crash-saved-command")
        assert saved_command[0] == 200
        saved_view = api.checked_json(first_client.get()[1])
        run_ids.append(saved_view["run_id"])
        stop_checked(first, first_client, first_port, temporary, "crash-save")
    finally:
        first_client.close()
        first.force_stop()
    saved = read_snapshot(database)
    assert_view_matches_stored(saved["pro"], saved_view)

    second, second_port, second_client = launch(binary, database, temporary, "crash-loss")
    try:
        restored_second = api.checked_json(second_client.get()[1])
        run_ids.append(restored_second["run_id"])
        assert restored_second["run_id"] != saved_view["run_id"]
        assert_view_matches_stored(saved["pro"], restored_second)
        unsaved = second_client.make("crash-unsaved-command")
        assert unsaved[0] == 200 and api.checked_json(unsaved[1])["status"] == "applied"
        assert api.checked_json(second_client.get()[1])["game"]["lifetime_clips"] == "2"
        # The ordinary 30-second publisher has not captured the later command.
        assert read_snapshot(database) == saved
        second_client.close()
        second.force_stop()  # Real Child.kill()/wait(); not a simulated shutdown.
        assert second.process.returncode != 0
        check_logs(second, second_port, temporary, "crash-loss")
    finally:
        second_client.close()
        second.force_stop()

    time.sleep(0.2)  # Actual process downtime; no offline catch-up is allowed.
    third, third_port, third_client = launch(binary, database, temporary, "crash-restore")
    try:
        restored_third = api.checked_json(third_client.get()[1])
        run_ids.append(restored_third["run_id"])
        assert restored_third["run_id"] != restored_second["run_id"]
        assert_view_matches_stored(saved["pro"], restored_third), "the unsaved command must roll back"
        # A new process has no old retry map: clients may resynchronize/reissue.
        replayed = third_client.make("crash-unsaved-command")
        assert replayed[0] == 200 and api.checked_json(replayed[1])["status"] == "applied"
        third_view = api.checked_json(third_client.get()[1])
        assert third_view["game"]["lifetime_clips"] == "2"
        assert third_view["game"]["wire"] == "998"
        stop_checked(third, third_client, third_port, temporary, "crash-restore")
    finally:
        third_client.close()
        third.force_stop()
    committed_third = read_snapshot(database)
    assert_view_matches_stored(committed_third["pro"], third_view)
    # The resend is one genuinely accepted manual production, not a clock
    # effect or fabricated resource. Its production/wire deltas stay exact.
    assert_snapshot_continuation(
        saved, committed_third, "kill/replay after actual downtime", expected_makes=1
    )

    fourth, fourth_port, fourth_client = launch(binary, database, temporary, "crash-restore-again")
    try:
        restored_fourth = api.checked_json(fourth_client.get()[1])
        run_ids.append(restored_fourth["run_id"])
        assert_view_matches_stored(committed_third["pro"], restored_fourth)
        assert api.assert_ready(fourth_client)["ready"] is True
        stop_checked(fourth, fourth_client, fourth_port, temporary, "crash-restore-again")
    finally:
        fourth_client.close()
        fourth.force_stop()
    committed_fourth = read_snapshot(database)
    assert_snapshot_continuation(committed_third, committed_fourth, "fourth restart continuation")
    assert len(set(run_ids)) == len(run_ids)
    print("process crash: real SIGKILL rolled back only unsaved state; resend/repeated restart/new run_ids passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    arguments = parser.parse_args()
    binary = arguments.binary.resolve()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="paperclip-game-persistence-check-") as temporary_name:
        temporary = Path(temporary_name)
        check_corrupt_startup(binary, temporary)
        check_sqlite_fault_and_health(binary, temporary)
        check_real_kill_and_repeated_restart(binary, temporary)
    print(f"persistence process checks passed in {time.perf_counter() - started:.3f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, OSError, sqlite3.Error, subprocess.SubprocessError, http.client.HTTPException):
        # Keep failures fatal while preserving their exact source assertion.
        # A collapsed bare AssertionError cannot expose safe-to-view state or
        # distinguish the protected rollback and continuation checkpoints.
        traceback.print_exc()
        sys.exit(1)
