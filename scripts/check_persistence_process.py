#!/usr/bin/env python3
# owner: paperclip-game CI
# trigger: pull requests, main pushes, and local persistence process verification
# purpose: prove real SQLite readiness failures, crash loss bounds, and safe repeated startup
"""Bounded real-process checks for the Issue #10 persistence service."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
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


def read_snapshot(database: Path) -> dict[str, Any]:
    # Only call this for a known-valid database. Startup corruption is tested
    # against original bytes without allowing SQLite to mutate the source file.
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        schema = connection.execute("PRAGMA user_version").fetchone()[0]
        assert schema == 1
        rows = connection.execute(
            "SELECT slot, snapshot_version, revision, capture_sequence, payload, checksum "
            "FROM game_snapshot"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1 and rows[0][0] == "default"
    _, version, revision, sequence, payload, checksum = rows[0]
    assert version == 1
    assert type(revision) is int and 0 <= revision <= api.SAFE_INTEGER
    assert type(sequence) is int and 0 <= sequence <= api.SAFE_INTEGER
    raw_payload = payload.encode("utf-8")
    snapshot = api.checked_json(raw_payload)
    assert set(snapshot) == {"snapshot_version", "revision", "pro", "clock", "rng_state"}
    assert type(snapshot["snapshot_version"]) is int and snapshot["snapshot_version"] == 1
    assert type(snapshot["revision"]) is int and snapshot["revision"] == revision
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
        assert saved["pro"] == post_stop_view["game"]
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
    assert saved["pro"] == saved_view["game"]

    second, second_port, second_client = launch(binary, database, temporary, "crash-loss")
    try:
        restored_second = api.checked_json(second_client.get()[1])
        run_ids.append(restored_second["run_id"])
        assert restored_second["run_id"] != saved_view["run_id"]
        assert restored_second["game"] == saved["pro"]
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
        assert restored_third["game"] == saved["pro"], "the unsaved command must roll back"
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
    assert committed_third["pro"] == third_view["game"]
    assert committed_third["rng_state"] == saved["rng_state"]

    fourth, fourth_port, fourth_client = launch(binary, database, temporary, "crash-restore-again")
    try:
        restored_fourth = api.checked_json(fourth_client.get()[1])
        run_ids.append(restored_fourth["run_id"])
        assert restored_fourth["game"] == committed_third["pro"]
        assert api.assert_ready(fourth_client)["ready"] is True
        stop_checked(fourth, fourth_client, fourth_port, temporary, "crash-restore-again")
    finally:
        fourth_client.close()
        fourth.force_stop()
    committed_fourth = read_snapshot(database)
    assert committed_fourth["pro"] == committed_third["pro"]
    assert committed_fourth["rng_state"] == committed_third["rng_state"]
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
    except (AssertionError, OSError, sqlite3.Error, subprocess.SubprocessError, http.client.HTTPException) as error:
        print(f"persistence process check failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
