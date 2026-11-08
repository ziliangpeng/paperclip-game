#!/usr/bin/env python3
# owner: paperclip-game CI
# trigger: pull requests, main pushes, and local browser stream verification
# purpose: execute the native EventSource client in a fresh isolated real browser
# Bounded real-browser SSE/reconnect/recovery checks using only this task's client.

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import check_api_process as api


HARNESS = r'''<!doctype html>
<meta charset="utf-8">
<title>native stream harness</title>
<pre id="status">running</pre>
<script type="module">
import {
  GameViewSynchronizer, addAmount, assertCompleteGameView, ceilAmount,
  compareAmount, formatAmount, parseAmount,
} from "/static/stream.js";

const output = document.querySelector("#status");
const runIds = new Set();
let firstRun = null;
let preCrash = null;
let recoveredBaseline = null;
let current = null;
let actualOldGet = null;
let actualOldGetDecision = null;
let delayedGetToken = null;
let delayedGetPromise = null;
let oldGetChecked = false;
let opens = 0;
let initialFrames = 0;
let presentations = 0;
let readySent = false;
let finished = false;
const checks = [];

function check(condition, label) {
  if (!condition) throw new Error(label);
  checks.push(label);
}

function retainedFullView(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function healthyOldGetRace(decision, before, after, callbacksBefore, callbacksAfter) {
  return decision === "stale-source" && retainedFullView(before, after) &&
    Number.isSafeInteger(callbacksBefore) && callbacksBefore === callbacksAfter;
}

async function fail(error) {
  if (finished) return;
  finished = true;
  output.textContent = JSON.stringify({status: "fail", error: String(error), checks});
  try { await fetch("/old-get-checked", {method: "POST", body: "{}"}); } catch {}
  try { await fetch("/report", {method: "POST", body: output.textContent}); } catch {}
}

const synchronizer = new GameViewSynchronizer((view, decision) => {
  current = view;
  presentations += 1;
  runIds.add(view.run_id);
  if (firstRun === null) firstRun = view.run_id;
  if (runIds.size === 1 && view.game.lifetime_clips === "20" && !readySent) {
    preCrash = structuredClone(view);
    readySent = true;
    delayedGetToken = synchronizer.requestView();
    // Request the real current public View from the old backend. The test proxy
    // captures its response and deliberately does not deliver it yet.
    delayedGetPromise = fetch("/api/game/view").then(async (response) => {
      if (response.status !== 200) throw new Error(`old GET status ${response.status}`);
      const view = assertCompleteGameView(await response.json());
      return {status: response.status, view};
    }).catch((error) => ({error: String(error)}));
    void fetch("/ready-to-crash", {method: "POST", body: "{}"});
  }
  if (firstRun !== null && preCrash !== null && recoveredBaseline === null &&
      runIds.size === 2 && decision === "adopted-new-run" &&
      view.run_id !== firstRun) {
    // This is the actual initial SSE baseline adoption for the recovered run.
    // The proxy now holds later transport updates until the old-GET race check.
    recoveredBaseline = structuredClone(view);
    void verifyDelayedOldGet();
  }
  if (oldGetChecked && firstRun !== null && recoveredBaseline !== null &&
      runIds.size === 2 && current.run_id !== firstRun &&
      current.game.lifetime_clips === "1") {
    void finish();
  }
});

async function verifyDelayedOldGet() {
  try {
    if (delayedGetPromise === null || delayedGetToken === null) {
      throw new Error("real old GET was not issued");
    }
    // Release only after the recovered initial SSE baseline was adopted.
    const release = await fetch("/release-old-get", {method: "POST", body: "{}"});
    if (release.status !== 200) throw new Error(`GET release status ${release.status}`);
    const actual = await delayedGetPromise;
    if (actual.error) throw new Error(actual.error);
    actualOldGet = actual.view;
    check(actual.status === 200, "real old backend HTTP status 200");
    check(actualOldGet.run_id === firstRun, "actual held HTTP body is from old run");
    check(actualOldGet.game.lifetime_clips === "20", "actual old HTTP command state captured");
    check(recoveredBaseline.run_id !== actualOldGet.run_id, "recovered run differs from actual old GET");
    check(recoveredBaseline.revision < preCrash.revision, "recovered initial revision is lower in this fixture");
    check(retainedFullView(current, recoveredBaseline), "no later presentation raced recovered baseline");

    const before = structuredClone(current);
    const callbacksBefore = presentations;
    actualOldGetDecision = synchronizer.acceptGet(delayedGetToken, actualOldGet);
    check(actualOldGetDecision === "stale-source", "actual held old backend GET returns stale-source");
    check(healthyOldGetRace(actualOldGetDecision, before, current, callbacksBefore, presentations),
      "actual held old backend GET has no presentation or state effect");

    // Negative control: retimestamping this exact real HTTP body into the new
    // epoch would wrongly re-adopt the old run. The health predicate must fail.
    let badPresentations = 0;
    const badModel = new GameViewSynchronizer(() => { badPresentations += 1; });
    const badOldStream = badModel.openStream();
    badModel.acceptStreamInitial(badOldStream, structuredClone(actualOldGet));
    const badNewStream = badModel.openStream();
    badModel.acceptStreamInitial(badNewStream, structuredClone(recoveredBaseline));
    const wrongEpochToken = badModel.requestView();
    const badBefore = structuredClone(badModel.current);
    const badCallbacksBefore = badPresentations;
    const badDecision = badModel.acceptGet(wrongEpochToken, structuredClone(actualOldGet));
    check(!healthyOldGetRace(badDecision, badBefore, badModel.current,
      badCallbacksBefore, badPresentations), "known-bad re-epoch old HTTP grant is detected");
    check(badDecision === "adopted-new-run" && badModel.current.run_id === firstRun &&
      badPresentations > badCallbacksBefore, "negative control demonstrates forbidden replacement");
    check(retainedFullView(current, recoveredBaseline), "negative control cannot mutate live recovered state");

    oldGetChecked = true;
    const checked = await fetch("/old-get-checked", {method: "POST", body: JSON.stringify({
      oldGetStatus: actual.status, decision: actualOldGetDecision,
    })});
    if (checked.status !== 200) throw new Error(`old GET checked status ${checked.status}`);
  } catch (error) {
    await fail(error);
  }
}

async function finish() {
  if (finished) return;
  finished = true;
  try {
    check(formatAmount(parseAmount("30000000000000000000000000000000000000000000000000000001").scaled) ===
      "30000000000000000000000000000000000000000000000000000001", "3e55+1 exact BigInt");
    check(compareAmount("9007199254740993", "9007199254740992") === 1, "2^53+1 exact compare");
    check(addAmount("0.000000000000000001", "-0.000000000000000001") === "0", "tiny signed exact add");
    check(ceilAmount("0.000000000000000001") === "1", "tiny positive ceiling");
    check(ceilAmount("-0.000000000000000001") === "0", "tiny signed ceiling");
    let rejected = false;
    try { parseAmount("1.0"); } catch { rejected = true; }
    check(rejected, "known-bad non-canonical Amount rejected");
    const complete = structuredClone(current);
    delete complete.game.wire;
    rejected = false;
    try { assertCompleteGameView(complete); } catch { rejected = true; }
    check(rejected, "known-bad incomplete full View rejected");
    const negativeWire = structuredClone(current);
    negativeWire.game.wire = "-1";
    rejected = false;
    try { assertCompleteGameView(negativeWire); } catch { rejected = true; }
    check(rejected, "known-bad negative Wire rejected");
    const fractionalTrust = structuredClone(current);
    fractionalTrust.game.trust = "2.5";
    rejected = false;
    try { assertCompleteGameView(fractionalTrust); } catch { rejected = true; }
    check(rejected, "known-bad fractional Trust rejected");
    const interior = structuredClone(current);
    interior.rng_state = "forbidden";
    rejected = false;
    try { assertCompleteGameView(interior); } catch { rejected = true; }
    check(rejected, "known-bad interior RNG field rejected");

    let modelPresentations = 0;
    const model = new GameViewSynchronizer(() => { modelPresentations += 1; });
    const oldStream = model.openStream();
    check(model.acceptStreamInitial(oldStream, structuredClone(preCrash)) === "adopted-new-run",
      "adopted pre-crash baseline");
    const newStream = model.openStream();
    check(model.acceptStreamInitial(newStream, structuredClone(recoveredBaseline)) === "adopted-new-run",
      "adopted recovered lower revision");
    check(modelPresentations === 2, "fixture callback counts two real baselines");
    const beforeOldStream = modelPresentations;
    check(model.acceptStreamUpdate(oldStream, structuredClone(preCrash)) === "stale-source",
      "actual old stream rejected");
    check(modelPresentations === beforeOldStream, "old stream causes no presentation callback");

    const beforeEqual = structuredClone(model.current);
    const equalCallbacksBefore = modelPresentations;
    const conflictingEqual = structuredClone(beforeEqual);
    conflictingEqual.game.lifetime_clips = beforeEqual.game.lifetime_clips === "1" ? "2" : "1";
    check(model.acceptStreamUpdate(newStream, conflictingEqual) === "equal",
      "equal revision is presentation-idempotent");
    check(modelPresentations === equalCallbacksBefore,
      "equal revision has no second presentation callback");
    check(retainedFullView(model.current, beforeEqual),
      "equal revision retains previous full conflicting state");
    check(model.current.run_id === recoveredBaseline.run_id, "recovered run remains authoritative");
    const report = {status: "pass", checks, opens, initialFrames, presentations,
      firstRun, recoveredRun: current.run_id, preCrashRevision: preCrash.revision,
      recoveredBaselineRevision: recoveredBaseline.revision,
      actualOldGetStatus: 200, actualOldGetDecision, oldGetChecked,
      expectedProxyCounts: {requests: 1, backendCaptured: 1, released: 1}};
    output.textContent = JSON.stringify(report);
    await fetch("/report", {method: "POST", body: JSON.stringify(report)});
  } catch (error) {
    await fail(error);
  }
}

const source = new EventSource("/api/game/stream");
let token = null;
let initial = true;
source.onopen = () => {
  token = synchronizer.openStream();
  opens += 1;
  initial = true;
};
source.addEventListener("game_view", (event) => {
  const wasInitial = initial;
  try {
    const view = assertCompleteGameView(JSON.parse(event.data));
    if (event.lastEventId !== `${view.run_id}:${view.revision}`) throw new Error("bad event ID");
    const decision = wasInitial ? synchronizer.acceptStreamInitial(token, view)
      : synchronizer.acceptStreamUpdate(token, view);
    initial = false;
    if (wasInitial && decision !== "stale-source") initialFrames += 1;
  } catch (error) {
    void fail(error);
  }
});
setTimeout(() => {
  if (!finished) void fail(new Error("browser scenario timeout"));
}, 20000);
</script>'''
# This fixture is not the product UI and retains no stream history.


def find_browser(explicit: str | None) -> str | None:
    if explicit:
        return shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    candidates = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    )
    return next((path for path in candidates if Path(path).is_file()), None)


class State:
    def __init__(self, backend_port: int) -> None:
        self.backend_port = backend_port
        self.condition = threading.Condition()
        self.stream_count = 0
        self.last_event_ids: list[str | None] = []
        self.stream_diagnostics: list[dict[str, Any]] = []
        self.ready_to_crash = threading.Event()
        self.game_view_get_requests = 0
        self.game_view_get_backend_captured = 0
        self.game_view_get_released = 0
        self.game_view_get_captured = threading.Event()
        self.release_game_view_get = threading.Event()
        self.old_get_checked_count = 0
        self.old_get_checked = threading.Event()
        self.allow_new_stream_updates = threading.Event()
        self.report: dict[str, Any] | None = None
        self.reported = threading.Event()


def proxy_handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def finite(self, raw: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def do_GET(self) -> None:
            if self.path == "/":
                self.finite(HARNESS.encode(), "text/html; charset=utf-8")
            elif self.path == "/static/stream.js":
                client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=5)
                try:
                    client.request("GET", self.path)
                    response = client.getresponse()
                    assert response.status == 200
                    self.finite(response.read(128 * 1024), "text/javascript; charset=utf-8")
                finally:
                    client.close()
            elif self.path == "/api/game/view":
                self.delayed_game_view()
            elif self.path == "/api/game/stream":
                self.stream()
            else:
                self.send_error(404)

        def delayed_game_view(self) -> None:
            with state.condition:
                state.game_view_get_requests += 1
                assert state.game_view_get_requests == 1, "at most one delayed browser GET"
            client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=5)
            try:
                # The driver waits for this real old-backend response before it
                # kills the process. Only task-proxy delivery is delayed.
                client.request("GET", "/api/game/view")
                response = client.getresponse()
                assert response.status == 200, "actual old backend HTTP status"
                assert response.getheader("Content-Type") == "application/json"
                body = response.read(64 * 1024 + 1)
                assert len(body) <= 64 * 1024, "bounded real HTTP body"
                with state.condition:
                    state.game_view_get_backend_captured += 1
                    assert state.game_view_get_backend_captured == 1
                    state.game_view_get_captured.set()
                    state.condition.notify_all()
                assert state.release_game_view_get.wait(25), "bounded held GET release"
                # Deliver the exact response captured from the old backend,
                # after the browser's recovered initial baseline adoption.
                self.finite(body, "application/json")
                with state.condition:
                    state.game_view_get_released += 1
                    assert state.game_view_get_released == 1
                    state.condition.notify_all()
            finally:
                client.close()

        def stream(self) -> None:
            with state.condition:
                state.stream_count += 1
                assert state.stream_count <= 16, "bounded browser reconnect attempts"
                number = state.stream_count
                state.last_event_ids.append(self.headers.get("Last-Event-ID"))
                state.condition.notify_all()
            client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=8)
            diagnostic: dict[str, Any] = {"number": number, "last_event_id": self.headers.get("Last-Event-ID")}
            state.stream_diagnostics.append(diagnostic)
            try:
                headers = {"Accept": "text/event-stream"}
                last = self.headers.get("Last-Event-ID")
                if last is not None:
                    headers["Last-Event-ID"] = last
                client.request("GET", self.path, headers=headers)
                response = client.getresponse()
                diagnostic["backend_status"] = response.status
                if response.status != 200:
                    self.send_error(502)
                    return
                diagnostic["browser_response"] = 200
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store, no-transform")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                events = 0
                while True:
                    line = response.readline(64 * 1024 + 1)
                    if not line:
                        break
                    diagnostic["bytes"] = diagnostic.get("bytes", 0) + len(line)
                    self.wfile.write(f"{len(line):X}\r\n".encode() + line + b"\r\n")
                    self.wfile.flush()
                    if line in (b"\n", b"\r\n"):
                        events += 1
                        if number == 1 and events == 1:
                            break
                        if number >= 3 and events == 1 and not state.old_get_checked.is_set():
                            # Freeze only proxy delivery after the new initial
                            # baseline. The backend writer keeps advancing.
                            diagnostic["baseline_delivery_held"] = True
                            assert state.allow_new_stream_updates.wait(25), "bounded baseline hold"
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionError, OSError, http.client.HTTPException) as error:
                diagnostic["error"] = f"{type(error).__name__}: {error}"
            finally:
                diagnostic["finished"] = True
                assert len(state.stream_diagnostics) <= 16, "bounded stream diagnostics"
                client.close()

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            assert 0 <= length <= 64 * 1024
            raw = self.rfile.read(length)
            if self.path == "/ready-to-crash":
                state.ready_to_crash.set()
                self.finite(b"{}", "application/json")
            elif self.path == "/release-old-get":
                with state.condition:
                    assert state.game_view_get_requests == 1
                    assert state.game_view_get_backend_captured == 1
                    assert state.game_view_get_released == 0
                    state.release_game_view_get.set()
                    state.condition.notify_all()
                self.finite(b"{}", "application/json")
            elif self.path == "/old-get-checked":
                with state.condition:
                    assert state.game_view_get_released == 1
                    state.old_get_checked_count += 1
                    assert state.old_get_checked_count == 1
                    state.old_get_checked.set()
                    state.allow_new_stream_updates.set()
                    state.condition.notify_all()
                self.finite(b"{}", "application/json")
            elif self.path == "/report":
                state.report = json.loads(raw)
                state.reported.set()
                self.finite(b"{}", "application/json")
            else:
                self.send_error(404)

    return Handler


class HarnessServer(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def wait_streams(state: State, count: int) -> None:
    deadline = time.monotonic() + 15
    with state.condition:
        while state.stream_count < count:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "browser stream connection count"
            state.condition.wait(remaining)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--browser", default=os.environ.get("PAPERCLIP_BROWSER"))
    parser.add_argument("--require-browser", action="store_true")
    args = parser.parse_args()
    browser = find_browser(args.browser)
    if browser is None:
        message = "real-browser stream evidence NOT EXECUTED: no supported Chrome/Chromium found"
        if args.require_browser:
            raise AssertionError(message)
        print(message)
        return 0
    version = subprocess.run([browser, "--version"], capture_output=True, text=True,
                             timeout=10, check=True).stdout.strip()
    print(f"real browser: {version}")
    binary = args.binary.resolve()
    old_process: api.Process | None = None
    replacements: list[api.Process] = []
    browser_process: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="paperclip-game-browser-stream-") as temporary_name:
        temporary = Path(temporary_name)
        database = temporary / "browser.sqlite3"
        backend_port = api.free_port()
        state = State(backend_port)
        proxy = HarnessServer(("127.0.0.1", 0), proxy_handler(state))
        proxy.daemon_threads = True
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        out = (temporary / "old.stdout").open("wb")
        err = (temporary / "old.stderr").open("wb")
        try:
            arguments = ["--listen-addr", f"127.0.0.1:{backend_port}", "--database-path", str(database)]
            old_process = api.start_ready(binary, arguments, backend_port, temporary, out, err)
            profile = temporary / "fresh-browser-profile"
            profile.mkdir()
            browser_process = subprocess.Popen([
                browser, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-background-networking", "--disable-component-update",
                "--disable-extensions", "--no-first-run", "--incognito",
                f"--user-data-dir={profile}",
                "--host-resolver-rules=MAP * 127.0.0.1, EXCLUDE localhost",
                f"http://127.0.0.1:{proxy.server_address[1]}/",
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def drive_recovery() -> None:
                try:
                    wait_streams(state, 2)
                    client = api.Client(backend_port)
                    for index in range(20):
                        status, body = client.make(f"browser-recovery-{index}")
                        assert status == 200, (status, body)
                    assert state.ready_to_crash.wait(15), "browser observed pre-crash state"
                    assert api.checked_json(client.get()[1])["game"]["lifetime_clips"] == "20"
                    assert state.game_view_get_captured.wait(15), "real old backend GET captured"
                    assert state.game_view_get_requests == 1
                    assert state.game_view_get_backend_captured == 1
                    assert state.game_view_get_released == 0
                    client.close()
                    old_process.force_stop()
                    new_out = (temporary / "new.stdout").open("wb")
                    new_err = (temporary / "new.stderr").open("wb")
                    with new_out, new_err:
                        replacements.append(api.start_ready(
                            binary, arguments, backend_port, temporary, new_out, new_err))
                    assert state.old_get_checked.wait(20), "real delayed browser GET checked"
                    assert state.game_view_get_released == 1
                    assert state.old_get_checked_count == 1
                    new_client = api.Client(backend_port)
                    status, body = new_client.make("browser-recovery-19")
                    assert status == 200, (status, body)
                    new_view = api.checked_json(new_client.get()[1])
                    assert new_view["game"]["lifetime_clips"] == "1"
                    state.stream_diagnostics.append({"replacement_run": new_view["run_id"],
                                                     "replacement_revision": new_view["revision"]})
                    new_client.close()
                except BaseException as error:
                    state.report = {"status": "fail", "error": f"driver: {type(error).__name__}: {error}"}
                    state.reported.set()

            driver = threading.Thread(target=drive_recovery, daemon=True)
            driver.start()
            assert state.reported.wait(35), "bounded real-browser completion"
            driver.join(timeout=2)
            report = state.report
            assert report is not None
            diagnostics = {"report": report, "streams": state.stream_diagnostics[-12:]}
            assert report.get("status") == "pass", json.dumps(diagnostics)[:6000]
            assert len(state.last_event_ids) >= 3
            assert state.last_event_ids[0] is None
            assert state.last_event_ids[1] and state.last_event_ids[1].count(":") == 1
            assert state.last_event_ids[2] and state.last_event_ids[2].count(":") == 1
            assert state.last_event_ids[1].split(":", 1)[0] == report["firstRun"]
            assert state.last_event_ids[2].split(":", 1)[0] == report["firstRun"]
            assert state.game_view_get_requests == 1
            assert state.game_view_get_backend_captured == 1
            assert state.game_view_get_released == 1
            assert state.old_get_checked_count == 1
            assert report["actualOldGetStatus"] == 200
            assert report["actualOldGetDecision"] == "stale-source"
            assert report["oldGetChecked"] is True
            assert replacements
            print(f"browser EventSource: same-run reconnect + recovered-run resync passed: {report}")
            print("real delayed browser HTTP: requests=1 backend_captured=1 released=1; decision=stale-source; callbacks/state retained")
        finally:
            if browser_process is not None:
                browser_process.terminate()
                try:
                    browser_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    browser_process.kill()
                    browser_process.wait(timeout=5)
            # Wake every bounded task-owned proxy wait during teardown, then
            # close the browser/backend sockets. No held fetch survives cleanup.
            state.release_game_view_get.set()
            state.allow_new_stream_updates.set()
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=5)
            for process in replacements:
                process.stop()
            if old_process is not None:
                old_process.force_stop()
            out.close()
            err.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.SubprocessError, http.client.HTTPException) as error:
        print(f"browser stream check failed: {type(error).__name__}: {error}", file=os.sys.stderr)
        raise SystemExit(1)
