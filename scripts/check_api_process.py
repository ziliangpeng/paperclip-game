#!/usr/bin/env python3
# owner: paperclip-game CI
# trigger: pull requests, main pushes, and local API process verification
# purpose: prove real process startup, HTTP commands/retry, and safe shutdown
"""Bounded process-level checks for the Issue #9 public HTTP service."""

from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

SAFE_INTEGER = 9_007_199_254_740_991
EXPECTED_FORBIDDEN = (
    "paperclip-game: configuration error: unknown or forbidden argument; "
    "only --listen-addr and --database-path are supported\n"
)
EXPECTED_INVALID_LISTENER = (
    "paperclip-game: configuration error: invalid value for --listen-addr; "
    "expected a numeric IP address and port\n"
)


def checked_json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def assert_production(view: dict[str, Any], wire: str, clips: str) -> None:
    game = view["game"]
    expected = {
        "lifetime_clips": clips,
        "unsold_clips": clips,
        "unused_clips": clips,
        "wire": wire,
        "funds": "0",
        "wire_spool_length": "1000",
        "wire_quote": "20",
        "price_per_clip": "0.25",
        "marketing_level": "1",
        "trust": "2",
        "processors": "1",
        "memory": "1",
        "computing_hidden": True,
        "projects_hidden": True,
        "auto_clipper_revealed": False,
        "auto_clippers": "0",
        "auto_clipper_cost": "5",
    }
    assert game == expected, (game, expected)


HEALTH_FIELDS = {
    "consecutive_failures",
    "current_attempt",
    "last_committed_revision",
    "last_committed_sequence",
    "last_failure_code",
    "latest_captured_revision",
    "latest_captured_sequence",
    "live",
    "pending_snapshot_count",
    "phase",
    "ready",
    "snapshot_overdue",
    "write_in_progress",
}


def assert_ready(client: Client, expected_status: int = 200) -> dict[str, Any]:
    status, raw = client.get("/api/health/ready")
    assert status == expected_status, (status, raw)
    health = checked_json(raw)
    assert set(health) == HEALTH_FIELDS
    assert isinstance(health["live"], bool)
    assert isinstance(health["ready"], bool)
    assert health["ready"] is (expected_status == 200)
    assert health["phase"] in {"unconfigured", "ready", "saving", "retrying", "degraded", "stopped"}
    for field in (
        "last_committed_revision",
        "last_committed_sequence",
        "latest_captured_revision",
        "latest_captured_sequence",
    ):
        value = health[field]
        assert value is None or (type(value) is int and 0 <= value <= SAFE_INTEGER)
    assert type(health["pending_snapshot_count"]) is int and health["pending_snapshot_count"] in (0, 1)
    assert isinstance(health["write_in_progress"], bool)
    assert type(health["current_attempt"]) is int and health["current_attempt"] >= 0
    assert type(health["consecutive_failures"]) is int and health["consecutive_failures"] >= 0
    assert isinstance(health["snapshot_overdue"], bool)
    assert health["last_failure_code"] is None or health["last_failure_code"] in {
        "database_busy", "open_failed", "schema_failure", "invalid_snapshot",
        "checksum_mismatch", "transaction_failed", "commit_outcome_unknown",
        "stale_capture", "sequence_conflict", "resource_limit",
    }
    return health


def assert_view_schema(view: dict[str, Any]) -> None:
    assert set(view) == {"schema_version", "run_id", "revision", "clock", "game"}
    assert view["schema_version"] == 1
    assert isinstance(view["run_id"], str) and len(view["run_id"]) == 32
    assert isinstance(view["revision"], int) and 0 <= view["revision"] <= SAFE_INTEGER
    clock = view["clock"]
    assert set(clock) == {
        "update_count",
        "fast_phase",
        "second_phase",
        "slow_phase",
        "combat_remainder_nanos",
        "combat_pulses",
    }
    for field in ("update_count", "combat_pulses"):
        assert isinstance(clock[field], int) and 0 <= clock[field] <= SAFE_INTEGER
    for field in (
        "fast_phase",
        "second_phase",
        "slow_phase",
        "combat_remainder_nanos",
    ):
        assert isinstance(clock[field], int)
    assert_production(view, "1000", "0")


class Client:
    def __init__(self, port: int) -> None:
        self.connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)

    def close(self) -> None:
        self.connection.close()

    def get(self, path: str = "/api/game/view") -> tuple[int, bytes]:
        self.connection.request("GET", path)
        response = self.connection.getresponse()
        return response.status, response.read()

    def post(self, body: bytes) -> tuple[int, bytes]:
        self.connection.request(
            "POST",
            "/api/game/commands",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        return response.status, response.read()

    def make(self, command_id: str) -> tuple[int, bytes]:
        return self.post(
            json.dumps(
                {
                    "command_id": command_id,
                    "type": "make_paperclip",
                    "arguments": {},
                },
                separators=(",", ":"),
            ).encode()
        )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class Process:
    def __init__(
        self,
        binary: Path,
        arguments: list[str],
        cwd: Path,
        stdout: Any,
        stderr: Any,
    ) -> None:
        self.process = subprocess.Popen(
            [str(binary), *arguments],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
        status = self.process.wait(timeout=5)
        assert status == 0, f"graceful shutdown returned {status}"

    def force_stop(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)


def start_ready(binary: Path, arguments: list[str], port: int, cwd: Path, out: Any, err: Any) -> Process:
    process = Process(binary, arguments, cwd, out, err)
    deadline = time.monotonic() + 8
    try:
        while time.monotonic() < deadline:
            if process.process.poll() is not None:
                raise AssertionError(f"server exited before readiness: {process.process.returncode}")
            client = Client(port)
            try:
                status, _ = client.get()
                if status == 200:
                    client.close()
                    return process
            except (ConnectionError, OSError, http.client.HTTPException):
                pass
            finally:
                client.close()
            time.sleep(0.05)
        raise AssertionError("server did not become ready within 8 seconds")
    except BaseException:
        process.force_stop()
        raise


def drain_stock(client: Client) -> None:
    first = client.make("process-first-command")
    assert first[0] == 200 and checked_json(first[1])["status"] == "applied"
    for index in range(999):
        status, body = client.make(f"process-stock-{index}")
        assert status == 200, (index, status, body)
    view = checked_json(client.get()[1])
    assert_production(view, "0", "1000")

    replay = client.make("process-first-command")
    assert replay == first, (replay, first)
    after_replay = checked_json(client.get()[1])
    assert_production(after_replay, "0", "1000")

    rejection = client.make("process-after-stock")
    assert rejection[0] == 422
    rejection_body = checked_json(rejection[1])
    assert rejection_body["status"] == "rule_rejected"
    assert rejection_body["reason"] == "insufficient_wire"
    assert rejection_body["revision"] >= after_replay["revision"]
    assert client.make("process-after-stock") == rejection

    before_conflict = checked_json(client.get()[1])
    conflict = client.post(
        b'{"command_id":"process-first-command","type":"unsupported_action","arguments":{}}'
    )
    assert conflict == (409, b'{"status":"conflict"}')
    after_conflict = checked_json(client.get()[1])
    assert after_conflict["game"] == before_conflict["game"]
    assert after_conflict["run_id"] == before_conflict["run_id"]
    assert client.make("process-first-command") == first
    print("process HTTP: 1,000 distinct writes, terminal replay, rejection replay, and 409 passed")


def remove_owned_database(database: Path) -> None:
    # The caller first proves absence and then creates this exact test database.
    # Only its known SQLite artifacts are removed, never a directory or glob.
    for suffix in ("", "-journal", "-shm", "-wal"):
        Path(str(database) + suffix).unlink(missing_ok=True)


def run_invalid_checks(binary: Path, cwd: Path, sentinel: Path) -> None:
    sentinel.write_bytes(b"original-database-bytes")
    before = sentinel.read_bytes()
    cases = [
        (
            ["--database-path", str(sentinel), "--pause", "1"],
            2,
            EXPECTED_FORBIDDEN,
        ),
        (
            ["--listen-addr", "do-not-echo-this-ci-value"],
            2,
            EXPECTED_INVALID_LISTENER,
        ),
    ]
    for arguments, expected_status, expected_stderr in cases:
        completed = subprocess.run(
            [str(binary), *arguments],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        assert completed.returncode == expected_status, completed.returncode
        assert completed.stdout == b""
        assert completed.stderr.decode() == expected_stderr
        assert b"do-not-echo-this-ci-value" not in completed.stderr
        assert sentinel.read_bytes() == before
        for suffix in ("-journal", "-shm", "-wal"):
            assert not Path(str(sentinel) + suffix).exists()
    print("process configuration: invalid flags/listener sanitized; sentinel unchanged")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    binary = args.binary.resolve()
    repo = args.repo.resolve()
    default_db = repo / "data/paperclip.sqlite3"
    explicit_db = repo / "data/bootstrap-smoke.sqlite3"
    assert not default_db.exists()
    assert not explicit_db.exists()
    run_started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="paperclip-game-process-check-") as temporary:
        temp = Path(temporary)
        sentinel = temp / "bootstrap-sentinel.sqlite3"
        run_invalid_checks(binary, repo, sentinel)

        # Verify the untouched production default 127.0.0.1:3000 without adding
        # an operator/debug option. The subsequent explicit listener uses a
        # bounded free-port fixture so independent runs do not collide.
        default_out = (temp / "default.stdout").open("wb")
        default_err = (temp / "default.stderr").open("wb")
        with default_out, default_err:
            default = start_ready(binary, [], 3000, repo, default_out, default_err)
            try:
                client = Client(3000)
                status, body = client.get()
                assert status == 200
                initial = checked_json(body)
                assert_view_schema(initial)
                assert client.get("/api/health/live") == (200, b'{"status":"ok"}')
                ready = assert_ready(client)
                assert ready["live"] is True
                assert ready["snapshot_overdue"] is False
                after_live = checked_json(client.get()[1])
                assert after_live["run_id"] == initial["run_id"]
                assert after_live["clock"]["update_count"] >= initial["clock"]["update_count"]
                assert after_live["revision"] >= initial["revision"]
                assert after_live["game"] == initial["game"]
                client.close()
            finally:
                default.stop()
            assert default_db.is_file(), "fresh host must initialize its configured SQLite file"
            assert default_out.name and Path(default_out.name).read_bytes() == b""
            startup = Path(default_err.name).read_text()
            assert startup == "paperclip-game: listening on http://127.0.0.1:3000\n"
            remove_owned_database(default_db)

        port = free_port()
        explicit_out = (temp / "explicit.stdout").open("wb")
        explicit_err = (temp / "explicit.stderr").open("wb")
        with explicit_out, explicit_err:
            explicit = start_ready(
                binary,
                [
                    "--listen-addr",
                    f"127.0.0.1:{port}",
                    "--database-path",
                    "data/bootstrap-smoke.sqlite3",
                ],
                port,
                repo,
                explicit_out,
                explicit_err,
            )
            try:
                client = Client(port)
                status, body = client.get()
                assert status == 200
                initial = checked_json(body)
                assert_view_schema(initial)
                drain_stock(client)
                client.close()
            finally:
                explicit.stop()
            assert Path(explicit_out.name).read_bytes() == b""
            startup = Path(explicit_err.name).read_text()
            assert startup == f"paperclip-game: listening on http://127.0.0.1:{port}\n"
            assert explicit_db.is_file(), "normal shutdown must leave its committed snapshot"
            remove_owned_database(explicit_db)

    elapsed = time.perf_counter() - run_started
    print(f"process service checks passed in {elapsed:.3f}s; real persistence initialized and cleaned")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        print(f"process check failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
