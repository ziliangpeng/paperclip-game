#!/usr/bin/env python3
"""Real-Chrome Issue #12 verification for the native public game page."""
from __future__ import annotations

import argparse
import base64
import copy
from collections import deque
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Reuse the project's real process/public API client without a second API model.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_api_process as api  # noqa: E402
from check_browser_stream import find_browser  # noqa: E402



class WebSocket:
    """Minimal RFC6455 client for loopback CDP; no package/browser profile data."""

    def __init__(self, url: str) -> None:
        parsed = urlsplit(url)
        assert parsed.scheme == "ws" and parsed.hostname == "127.0.0.1"
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
        self.buffer = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{parsed.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
        self.socket.sendall(request)
        response = self._until_headers()
        assert response.startswith(b"HTTP/1.1 101"), response[:200]
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        assert b"Sec-WebSocket-Accept: " + expected in response, response[:500]

    def _until_headers(self) -> bytes:
        while b"\r\n\r\n" not in self.buffer:
            assert len(self.buffer) <= 64 * 1024
            chunk = self.socket.recv(4096)
            assert chunk
            self.buffer.extend(chunk)
        end = self.buffer.index(b"\r\n\r\n") + 4
        response = bytes(self.buffer[:end])
        del self.buffer[:end]
        return response

    def _exact(self, size: int) -> bytes:
        while len(self.buffer) < size:
            chunk = self.socket.recv(min(64 * 1024, max(4096, size - len(self.buffer))))
            if not chunk:
                raise EOFError("CDP websocket closed")
            self.buffer.extend(chunk)
        value = bytes(self.buffer[:size])
        del self.buffer[:size]
        return value

    def _frame(self, opcode: int, payload: bytes = b"") -> None:
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", size)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header + mask + masked)

    def send(self, value: dict[str, Any]) -> None:
        self._frame(1, json.dumps(value, separators=(",", ":")).encode())

    def receive(self, timeout: float = 10) -> dict[str, Any]:
        self.socket.settimeout(timeout)
        fragments = bytearray()
        while True:
            first, second = self._exact(2)
            fin, opcode = bool(first & 0x80), first & 0x0F
            assert not second & 0x80, "server CDP frames must not be masked"
            size = second & 0x7F
            if size == 126:
                size = struct.unpack("!H", self._exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._exact(8))[0]
            assert size <= 8 * 1024 * 1024, "bounded CDP message"
            payload = self._exact(size)
            if opcode == 8:
                raise EOFError("CDP close frame")
            if opcode == 9:
                self._frame(10, payload)
                continue
            if opcode == 10:
                continue
            if opcode != 0:
                fragments = bytearray()
            fragments.extend(payload)
            assert len(fragments) <= 8 * 1024 * 1024
            if fin:
                assert opcode in (0, 1, 2)
                return json.loads(fragments)

    def close(self) -> None:
        try:
            self._frame(8)
        except OSError:
            pass
        self.socket.close()


class Cdp:
    def __init__(self, url: str) -> None:
        self.websocket = WebSocket(url)
        self.next_id = 1
        # A bounded diagnostic buffer, never an unbounded protocol journal.
        self.events: deque[dict[str, Any]] = deque(maxlen=2000)

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 12) -> dict[str, Any]:
        command_id = self.next_id
        self.next_id += 1
        self.websocket.send({"id": command_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"bounded CDP call: {method}"
            message = self.websocket.receive(remaining)
            if message.get("id") != command_id:
                if "method" in message:
                    self.events.append(message)
                continue
            if "error" in message:
                raise AssertionError(f"CDP {method}: {message['error']}")
            return message.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
            "userGesture": False,
        })
        if "exceptionDetails" in result:
            raise AssertionError(f"browser evaluation: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def key(self, kind: str, key: str, code: str, virtual: int, repeat: bool = False) -> None:
        parameters = {
            "type": kind,
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": virtual,
            "nativeVirtualKeyCode": virtual,
            "autoRepeat": repeat,
        }
        if kind == "keyDown" and key in ("Enter", " "):
            # Match real browser text-producing Enter/Space key events. CDP
            # keyDown without text does not perform native button activation.
            parameters["text"] = "\r" if key == "Enter" else " "
            parameters["unmodifiedText"] = parameters["text"]
        self.call("Input.dispatchKeyEvent", parameters)

    def press(self, key: str, repeat_too: bool = False) -> None:
        code, virtual = ("Enter", 13) if key == "Enter" else ("Space", 32)
        wire_key = "Enter" if key == "Enter" else " "
        self.key("keyDown", wire_key, code, virtual)
        if repeat_too:
            self.key("keyDown", wire_key, code, virtual, repeat=True)
        self.key("keyUp", wire_key, code, virtual)

    def close(self) -> None:
        self.websocket.close()


def wait_for(function: Callable[[], Any], predicate: Callable[[Any], bool] = bool,
             description: str = "condition", timeout: float = 10) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while True:
        last = function()
        if predicate(last):
            return last
        assert time.monotonic() < deadline, f"timeout waiting for {description}: {last!r}"
        time.sleep(0.025)


class Browser:
    def __init__(self, executable: str, temporary: Path, origin: str) -> None:
        self.origin = origin
        self.origin_port = int(urlsplit(origin).port)
        self.process: subprocess.Popen[bytes] | None = None
        self.pages: list[Cdp] = []
        self.browser_connection: Cdp | None = None
        profile = temporary / "fresh-native-ui-profile"
        profile.mkdir()
        self.process = subprocess.Popen([
            executable, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-component-update", "--disable-extensions", "--no-first-run",
            "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
            "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
            f"--user-data-dir={profile}", "about:blank",
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        active_port = profile / "DevToolsActivePort"
        def port_text() -> str | None:
            try:
                return active_port.read_text().splitlines()[0]
            except (FileNotFoundError, IndexError):
                return None
        port = int(wait_for(port_text, description="isolated CDP port"))
        self.port = port
        version = self.http_json("/json/version")
        self.browser_connection = Cdp(version["webSocketDebuggerUrl"])

    def http_json(self, path: str) -> Any:
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            client.request("GET", path)
            response = client.getresponse()
            assert response.status == 200
            body = response.read(1024 * 1024 + 1)
            assert len(body) <= 1024 * 1024
            return json.loads(body)
        finally:
            client.close()

    def new_page(self, path: str = "/") -> tuple[Cdp, str, str]:
        assert self.browser_connection is not None
        context = self.browser_connection.call("Target.createBrowserContext")
        context_id = context["browserContextId"]
        target = self.browser_connection.call("Target.createTarget", {
            "url": self.origin + path, "browserContextId": context_id,
        })
        target_id = target["targetId"]
        def endpoint() -> str | None:
            for item in self.http_json("/json/list"):
                if item.get("id") == target_id:
                    return item.get("webSocketDebuggerUrl")
            return None
        url = wait_for(endpoint, description="new anonymous page CDP endpoint")
        page = Cdp(url)
        self.pages.append(page)
        page.call("Page.enable")
        page.call("Runtime.enable")
        page.call("Network.enable", {"maxTotalBufferSize": 2_000_000, "maxResourceBufferSize": 256_000})
        page.call("Page.bringToFront")
        return page, context_id, target_id

    def close(self) -> None:
        for page in self.pages:
            page.close()
        if self.browser_connection is not None:
            self.browser_connection.close()
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


class ProxyState:
    def __init__(self, backend_port: int) -> None:
        self.backend_port = backend_port
        self.lock = threading.Lock()
        self.command_records: list[dict[str, Any]] = []
        self.command_arrived = threading.Condition(self.lock)
        self.hold_commands = False
        self.command_release = threading.Event()
        self.drop_next_response = False
        self.conflict_next = False
        self.hold_next_get = False
        self.get_captured = threading.Event()
        self.get_release = threading.Event()
        self.get_record: dict[str, Any] | None = None
        self.fixture_frames: list[dict[str, Any]] | None = None
        self.fixture_connections = 0
        self.fixture_sent: list[threading.Event] = []
        self.fixture_release: list[threading.Event] = []
        self.fixture_close = threading.Event()
        self.fixture_get_gate = threading.Event()
        self.fixture_get_delivered = threading.Event()
        self.stream_baselines: list[dict[str, Any]] = []
        self.stream_connections = 0
        self.drop_first_stream = False
        self.errors: list[str] = []


def json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def proxy_handler(state: ProxyState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def finite(self, status: int, body: bytes, content_type: str,
                   cache_control: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self.close_connection = True

        def bounded_body(self) -> bytes:
            length_text = self.headers.get("Content-Length", "0")
            assert length_text.isascii() and length_text.isdigit()
            length = int(length_text)
            assert 0 <= length <= 64 * 1024
            return self.rfile.read(length)

        def backend(self, method: str, path: str, body: bytes | None = None,
                    content_type: str | None = None) -> tuple[int, bytes, str, str | None]:
            client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=8)
            try:
                headers = {}
                if content_type:
                    headers["Content-Type"] = content_type
                client.request(method, path, body=body, headers=headers)
                response = client.getresponse()
                raw = response.read(2 * 1024 * 1024 + 1)
                assert len(raw) <= 2 * 1024 * 1024, "bounded proxy response"
                return response.status, raw, response.getheader("Content-Type") or "application/octet-stream", response.getheader("Cache-Control")
            finally:
                client.close()

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            try:
                if self.path == "/api/game/stream" and state.fixture_frames is not None:
                    self.fixture_stream()
                    return
                if self.path == "/api/game/stream":
                    self.stream()
                    return
                if self.path == "/api/game/view" and state.fixture_frames is not None:
                    first = state.fixture_frames[0]
                    # Deliberately deliver the old GET only after the high frame.
                    assert state.fixture_get_gate.wait(8), "fixture high-view GET barrier"
                    self.finite(200, json_bytes(first), "application/json")
                    state.fixture_get_delivered.set()
                    return
                body = self.bounded_body()
                if self.path == "/api/game/view" and state.hold_next_get:
                    state.hold_next_get = False
                    status, raw, kind, cache = self.backend("GET", self.path, body)
                    state.get_record = {"status": status, "body": json.loads(raw),
                                        "delivered": False}
                    state.get_captured.set()
                    assert state.get_release.wait(12), "bounded held real GET"
                    state.get_record["delivered"] = True
                    self.finite(status, raw, kind, cache)
                    return
                status, raw, kind, cache = self.backend("GET", self.path, body)
                self.finite(status, raw, kind, cache)
            except (AssertionError, OSError, http.client.HTTPException) as error:
                state.errors.append(f"GET {self.path}: {type(error).__name__}: {error}")
                try:
                    self.send_error(502)
                except OSError:
                    pass

        def stream(self) -> None:
            state.stream_connections += 1
            connection_number = state.stream_connections
            assert state.stream_connections <= 32, "bounded stream connections"
            client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=8)
            try:
                headers = {"Accept": "text/event-stream"}
                last = self.headers.get("Last-Event-ID")
                if last is not None:
                    headers["Last-Event-ID"] = last
                client.request("GET", self.path, headers=headers)
                response = client.getresponse()
                if response.status != 200:
                    self.send_error(502)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store, no-transform")
                self.send_header("Connection", "close")
                self.end_headers()
                initial_lines: list[bytes] = []
                initial_size = 0
                while True:
                    line = response.readline(64 * 1024 + 1)
                    assert len(line) <= 64 * 1024, "bounded SSE line"
                    if not line:
                        assert initial_lines is None or not initial_lines, "no partial initial SSE event"
                        break
                    self.wfile.write(line)
                    self.wfile.flush()
                    if initial_lines is not None:
                        initial_size += len(line)
                        assert initial_size <= 64 * 1024, "bounded initial SSE event"
                        if line in (b"\n", b"\r\n"):
                            data = [item for item in initial_lines if item.startswith(b"data:")]
                            assert len(data) == 1
                            baseline = json.loads(data[0].removeprefix(b"data:").strip())
                            assert baseline["schema_version"] == 1
                            state.stream_baselines.append(baseline)
                            assert len(state.stream_baselines) <= 32, "bounded baseline diagnostics"
                            initial_lines = None
                            if state.drop_first_stream and connection_number == 1:
                                state.drop_first_stream = False
                                break
                        else:
                            initial_lines.append(line)
            except (BrokenPipeError, ConnectionError, OSError, http.client.HTTPException):
                # Ordinary disconnect/reconnect/recovery is not a failed check.
                pass
            finally:
                self.close_connection = True
                client.close()

        def do_POST(self) -> None:
            if self.path != "/api/game/commands":
                self.send_error(404)
                return
            try:
                raw = self.bounded_body()
                with state.command_arrived:
                    record = {"method": "POST", "path": self.path, "raw": raw,
                              "contentType": self.headers.get("Content-Type"),
                              "json": json.loads(raw), "forwarded": 0, "dropped": False}
                    state.command_records.append(record)
                    assert len(state.command_records) <= 2000
                    state.command_arrived.notify_all()
                if state.hold_commands:
                    assert state.command_release.wait(10), "bounded command barrier"
                if state.conflict_next:
                    state.conflict_next = False
                    record["response_status"] = 409
                    self.finite(409, b'{"status":"conflict"}', "application/json")
                    return
                status, response_body, kind, cache = self.backend(
                    "POST", self.path, raw, self.headers.get("Content-Type"))
                record["response_status"] = status
                record["response_body"] = json.loads(response_body)
                record["forwarded"] += 1
                if state.drop_next_response:
                    state.drop_next_response = False
                    record["dropped"] = True
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.finite(status, response_body, kind, cache)
            except (AssertionError, ValueError, OSError, http.client.HTTPException) as error:
                state.errors.append(f"POST command: {type(error).__name__}: {error}")
                try:
                    self.send_error(502)
                except OSError:
                    pass

        def fixture_stream(self) -> None:
            state.fixture_connections += 1
            assert state.fixture_connections == 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store, no-transform")
            self.send_header("Connection", "close")
            self.end_headers()
            assert state.fixture_frames is not None
            for index, frame in enumerate(state.fixture_frames):
                view = frame
                data = json_bytes(view)
                event = (f"id: {view['run_id']}:{view['revision']}\n"
                         f"event: game_view\ndata: ").encode() + data + b"\n\n"
                self.wfile.write(event)
                self.wfile.flush()
                state.fixture_sent[index].set()
                # The driver releases frames after observing actual DOM state.
                assert state.fixture_release[index].wait(12), "bounded fixture frame"
            assert state.fixture_close.wait(25), "bounded fixture close"
            self.close_connection = True

    return Handler


class Proxy(ThreadingHTTPServer):
    daemon_threads = True
    def handle_error(self, request: Any, client_address: Any) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def start_proxy(state: ProxyState) -> tuple[Proxy, threading.Thread]:
    proxy = Proxy(("127.0.0.1", 0), proxy_handler(state))
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    return proxy, thread


def wait_commands(state: ProxyState, count: int, timeout: float = 8) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    with state.command_arrived:
        while len(state.command_records) < count:
            remaining = deadline - time.monotonic()
            assert remaining > 0, (len(state.command_records), count)
            state.command_arrived.wait(remaining)
        return state.command_records[:count]


def dom_state(page: Cdp) -> dict[str, Any]:
    return page.evaluate("""({
      runId: document.documentElement.dataset.runId,
      revision: document.documentElement.dataset.revision,
      viewState: document.documentElement.dataset.viewState,
      lifetime: document.getElementById('lifetime-clips').dataset.canonical,
      wire: document.getElementById('wire').dataset.canonical,
      status: document.getElementById('command-status').textContent,
      button: document.getElementById('make-paperclip').textContent,
      disabled: document.getElementById('make-paperclip').disabled,
      ariaDisabled: document.getElementById('make-paperclip').getAttribute('aria-disabled'),
      focus: document.activeElement && document.activeElement.id
    })""")


def wait_dom(page: Cdp, expression: str, expected: Any, description: str, timeout: float = 10) -> Any:
    return wait_for(lambda: page.evaluate(expression), lambda value: value == expected,
                    description, timeout)


def exact_command(record: dict[str, Any]) -> dict[str, Any]:
    body = record["json"]
    assert record["method"] == "POST" and record["path"] == "/api/game/commands"
    assert record["contentType"] == "application/json"
    assert set(body) == {"command_id", "type", "arguments"}
    assert body["type"] == "make_paperclip" and body["arguments"] == {}
    assert isinstance(body["command_id"], str) and 0 < len(body["command_id"].encode()) <= 128
    assert not any(ord(character) < 32 or ord(character) == 127 for character in body["command_id"])
    return body


def fixture_view(template: dict[str, Any], run_id: str, revision: int,
                 changes: dict[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(template)
    view["run_id"] = run_id
    view["revision"] = revision
    view["clock"]["update_count"] = revision * 100
    view["game"].update(changes)
    return view


def check_assets_and_negative_commands(page: Cdp, port: int) -> None:
    client = api.Client(port)
    expected = {
        "/": "text/html; charset=utf-8",
        "/static/styles.css": "text/css; charset=utf-8",
        "/static/app.js": "text/javascript; charset=utf-8",
        "/static/view-model.js": "text/javascript; charset=utf-8",
        "/static/commands.js": "text/javascript; charset=utf-8",
        "/static/stream.js": "text/javascript; charset=utf-8",
    }
    for path, kind in expected.items():
        client.connection.request("GET", path)
        response = client.connection.getresponse()
        assert response.status == 200, (path, response.status)
        assert response.getheader("Content-Type") == kind, (path, response.getheader("Content-Type"))
        body = response.read(256 * 1024 + 1)
        assert len(body) <= 256 * 1024
    for path in ("/static/../Cargo.toml", "/static/index.html%00", "/src/main.rs", "/favicon.ico"):
        status, _ = client.get(path)
        assert status == 404, (path, status)
    client.close()

    # Exercise the command factory and closed-envelope guard in the page itself.
    result = page.evaluate("""(async () => {
      const {makePaperclipCommand, postMakePaperclip} = await import('/static/commands.js');
      const id = 'browser-negative-fixed-id';
      const good = makePaperclipCommand(id);
      if (JSON.stringify(good) !== '{"command_id":"browser-negative-fixed-id","type":"make_paperclip","arguments":{}}') throw new Error('bad exact envelope');
      const bad = [
        {...good, amount: '1'}, {...good, actor: 'human'}, {...good, world: 'default'},
        {...good, timestamp: 1}, {...good, arguments: {count: 1}}, {...good, type: 'debug_reset'},
        {...good, revision: 1}, {...good, client_command_id: id}
      ];
      let fetches = 0;
      for (const command of bad) {
        let rejected = false;
        try { await postMakePaperclip(command, {fetch: () => { fetches += 1; throw new Error('must not fetch'); }}); }
        catch (error) { rejected = error instanceof TypeError && error.message === 'only a typed make_paperclip command is accepted'; }
        if (!rejected) throw new Error('envelope negative guard did not reject designated field');
      }
      for (const invalidId of ['', 'bad\\u0000id', 'x'.repeat(129)]) {
        let rejected = false;
        try { makePaperclipCommand(invalidId); } catch (error) { rejected = error instanceof TypeError && error.message === 'invalid opaque command ID'; }
        if (!rejected) throw new Error('command id guard');
      }
      const headers = {"Content-Type": "application/json"};
      let oversizeReason = null;
      try {
        await postMakePaperclip(good, {fetch: () => new Response(new Uint8Array(16385), {status: 200, headers})});
      } catch (error) { oversizeReason = error.message; }
      if (oversizeReason !== 'oversized command response') throw new Error('designated response allocation guard');
      const wrongType = await postMakePaperclip(good, {fetch: () => new Response('{}', {status: 200, headers: {"Content-Type": "text/plain"}})});
      if (wrongType.kind !== 'invalid_response') throw new Error('response content type guard');
      const invalidShape = await postMakePaperclip(good, {fetch: () => new Response('{"status":"applied"}', {status: 200, headers})});
      if (invalidShape.kind !== 'invalid_response') throw new Error('typed applied response shape guard');
      const {MakePaperclipCommandRunner} = await import('/static/commands.js');
      const timeoutRunner = new MakePaperclipCommandRunner(() => {}, {
        timeoutMs: 5,
        fetch: (url, options) => new Promise((resolve, reject) => {
          options.signal.addEventListener('abort', () => reject(new Error(String(options.signal.reason))), {once: true});
        })
      });
      const started = performance.now();
      const timeoutOutcome = await timeoutRunner.run();
      const timeoutElapsed = performance.now() - started;
      if (timeoutOutcome.kind !== 'network_error' || !timeoutRunner.retryAvailable || timeoutElapsed > 2000) {
        throw new Error('bounded pending fetch/same-intent retry guard: ' + JSON.stringify({kind: timeoutOutcome.kind, retry: timeoutRunner.retryAvailable, timeoutElapsed}));
      }
      return {badEnvelopes: bad.length, invalidIds: 3, fetches, oversizeRejected: true,
        wrongContentTypeRejected: true, invalidAppliedShapeRejected: true,
        timeoutBounded: true, timeoutRetainsRetry: true};
    })()""")
    assert result == {"badEnvelopes": 8, "invalidIds": 3, "fetches": 0,
                      "oversizeRejected": True, "wrongContentTypeRejected": True,
                      "invalidAppliedShapeRejected": True, "timeoutBounded": True,
                      "timeoutRetainsRetry": True}, result


def check_accessibility_and_keyboard_order(page: Cdp) -> None:
    structure = page.evaluate("""(() => {
      const ids = ['lifetime-clips','unsold-clips','unused-clips','funds','wire'];
      const headings = [...document.querySelectorAll('h1,h2,h3')].map(h => ({level: Number(h.tagName.slice(1)), text: h.textContent.trim(), hidden: !!h.closest('[hidden]')}));
      const style = getComputedStyle(document.body);
      const buttonStyle = getComputedStyle(document.getElementById('make-paperclip'));
      const luminance = rgb => {
        const channels = rgb.match(/[0-9]+/g).slice(0,3).map(v => Number(v) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
        return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
      };
      const contrast = (a,b) => {
        const high = Math.max(luminance(a), luminance(b)); const low = Math.min(luminance(a), luminance(b));
        return (high + .05) / (low + .05);
      };
      return {
        header: document.querySelectorAll('body > header').length,
        nav: document.querySelectorAll('body > nav[aria-label]').length,
        main: document.querySelectorAll('body > main').length,
        footer: document.querySelectorAll('body > footer').length,
        headings, fakeControls: document.querySelectorAll('[role=button]:not(button), div[onclick], span[onclick]').length,
        buttons: [...document.querySelectorAll('button')].map(b => b.textContent.trim()),
        amountsOutsideLive: ids.every(id => document.getElementById(id).closest('[aria-live]') === null),
        statusLive: document.getElementById('command-status').getAttribute('aria-live'),
        statusAtomic: document.getElementById('command-status').getAttribute('aria-atomic'),
        labels: document.querySelectorAll('th[scope=row]').length >= 8,
        contrast: contrast(style.color, style.backgroundColor),
        buttonContrast: contrast(buttonStyle.color, buttonStyle.backgroundColor),
        forbidden: [...document.querySelectorAll('button,input,select,textarea')].map(e => e.textContent || e.name).join(' '),
        computingHidden: document.getElementById('computational-resources').hidden,
        autoHidden: document.getElementById('auto-clippers-panel').hidden,
      };
    })()""")
    assert structure["header"] == structure["nav"] == structure["main"] == structure["footer"] == 1
    visible = [heading for heading in structure["headings"] if not heading["hidden"]]
    assert visible[0]["level"] == 1 and all(h["level"] <= previous + 1 for h, previous in zip(visible[1:], [h["level"] for h in visible[:-1]]))
    assert structure["fakeControls"] == 0 and structure["buttons"] == ["Make Paperclip"]
    assert structure["amountsOutsideLive"] and structure["statusLive"] == "polite" and structure["statusAtomic"] == "true"
    assert structure["labels"] and abs(structure["contrast"] - 21) < 1e-9 and abs(structure["buttonContrast"] - 21) < 1e-9, structure
    assert structure["computingHidden"] and structure["autoHidden"]
    for forbidden in ("Feed", "Teach", "Clad", "Debug", "Reset", "New world", "Buy Wire", "Buy Auto"):
        assert forbidden not in structure["forbidden"]
    ax = page.call("Accessibility.getFullAXTree")["nodes"]
    roles = {node.get("role", {}).get("value") for node in ax if not node.get("ignored")}
    assert {"banner", "navigation", "main", "contentinfo", "button"}.issubset(roles), roles

    tab_order = page.evaluate("""(() => {
      if (document.activeElement) document.activeElement.blur();
      document.dispatchEvent(new KeyboardEvent('keyup', {key:'Tab'}));
      return document.activeElement.tagName;
    })()""")
    assert tab_order == "BODY"
    focused = []
    for _ in range(5):
        page.key("keyDown", "Tab", "Tab", 9)
        page.key("keyUp", "Tab", "Tab", 9)
        focused.append(page.evaluate("document.activeElement.id || document.activeElement.textContent.trim()"))
    assert focused[0] == "Skip to game controls", focused
    assert focused[1:4] == ["Production", "Business", "Manufacturing"], focused
    assert focused[4] == "make-paperclip", focused


def run_main_ui(browser: Browser, state: ProxyState, backend_port: int, page1: Cdp, page2: Cdp) -> dict[str, Any]:
    check_assets_and_negative_commands(page1, browser.origin_port)
    first = wait_for(lambda: dom_state(page1), lambda value: value.get("viewState") == "ready", "page one baseline")
    second = wait_for(lambda: dom_state(page2), lambda value: value.get("viewState") == "ready", "page two baseline")
    assert first["runId"] == second["runId"] and first["lifetime"] == second["lifetime"] == "0"
    check_accessibility_and_keyboard_order(page1)

    # The focused native button is activated with Enter. Repeat keydown cannot
    # create a second command, and a held request cannot change local balances.
    state.hold_commands = True
    state.command_release.clear()
    page1.press("Enter", repeat_too=True)
    records = wait_commands(state, 1)
    first_command = exact_command(records[0])
    pending = wait_for(lambda: dom_state(page1), lambda value: value["ariaDisabled"] == "true" and not value["disabled"] and "pending" in value["status"].lower(), "visible pending")
    assert pending["lifetime"] == "0" and pending["wire"] == "1000" and pending["focus"] == "make-paperclip"
    page1.press("Enter")
    settle_dom(page1)
    assert len(state.command_records) == 1, "pending activation is deduplicated without losing focus"
    state.command_release.set()
    wait_for(lambda: dom_state(page1), lambda value: value["lifetime"] == "1" and value["wire"] == "999" and "applied" in value["status"], "page one applied View")
    wait_for(lambda: dom_state(page2), lambda value: value["lifetime"] == "1" and value["wire"] == "999", "page two observes page one")
    assert records[0]["response_status"] == 200 and records[0]["response_body"]["status"] == "applied"
    assert page1.evaluate("document.activeElement.id") == "make-paperclip"

    # Space on the other page is a new intent with a new opaque ID.
    page2.evaluate("document.getElementById('make-paperclip').focus()")
    page2.call("Page.bringToFront")
    page2.press("Space", repeat_too=True)
    records = wait_commands(state, 2)
    second_command = exact_command(records[1])
    assert second_command["command_id"] != first_command["command_id"]
    for page in (page1, page2):
        wait_for(lambda page=page: dom_state(page), lambda value: value["lifetime"] == "2" and value["wire"] == "998", "two-page second command convergence")

    # Two held browser commands and a structured-Agent command race through the
    # ordinary public API. There is no actor, first-page lock, or local winner.
    state.hold_commands = True
    state.command_release.clear()
    page1.evaluate("document.getElementById('make-paperclip').focus()")
    page1.call("Page.bringToFront")
    page1.press("Enter")
    page2.evaluate("document.getElementById('make-paperclip').focus()")
    page2.call("Page.bringToFront")
    page2.press("Space")
    held = wait_commands(state, 4)[2:4]
    agent_client = api.Client(backend_port)
    agent_result: list[Any] = []
    def agent_make() -> None:
        agent_result.append(agent_client.make("m1-ui-structured-agent-simultaneous"))
    agent_thread = threading.Thread(target=agent_make)
    agent_thread.start()
    state.command_release.set()
    agent_thread.join(timeout=8)
    assert not agent_thread.is_alive() and agent_result[0][0] == 200, agent_result
    for record in held:
        exact_command(record)
    assert len({record["json"]["command_id"] for record in held}) == 2
    for page in (page1, page2):
        wait_for(lambda page=page: dom_state(page), lambda value: value["lifetime"] == "5" and value["wire"] == "995", "simultaneous Agent/browser convergence")
    agent_view = api.checked_json(agent_client.get()[1])
    assert agent_view["game"]["lifetime_clips"] == "5" and agent_view["game"]["wire"] == "995"

    # Accepted/disconnected is ambiguous. The first command really applies;
    # manual retry sends the same bytes and server replay does not apply twice.
    state.drop_next_response = True
    state.hold_commands = False
    page1.evaluate("document.getElementById('make-paperclip').focus()")
    page1.call("Page.bringToFront")
    before_retry_count = len(state.command_records)
    page1.press("Enter")
    retry_records = wait_commands(state, before_retry_count + 1)
    dropped = retry_records[-1]
    retry_command = exact_command(dropped)
    wait_for(lambda: dom_state(page1), lambda value: "Network outcome is unknown" in value["status"] and value["button"] == "Retry Make Paperclip" and not value["disabled"], "ambiguous retry feedback")
    assert dropped["forwarded"] == 1 and dropped["dropped"] and dropped["response_status"] == 200
    wait_for(lambda: dom_state(page1), lambda value: value["lifetime"] == "6" and value["wire"] == "994", "SSE after dropped applied response")
    page1.press("Enter")
    retry_records = wait_commands(state, before_retry_count + 2)
    replay = retry_records[-1]
    assert replay["raw"] == dropped["raw"] and exact_command(replay)["command_id"] == retry_command["command_id"]
    wait_for(lambda: dom_state(page1), lambda value: value["lifetime"] == "6" and value["wire"] == "994" and "applied" in value["status"], "same-ID retry no duplicate effect")
    assert replay["response_body"] == dropped["response_body"]

    # A typed proxy conflict exercises product feedback while the subsequent
    # actual API conflict below checks the #9 immutable binding itself.
    state.conflict_next = True
    conflict_index = len(state.command_records)
    page1.press("Enter")
    conflict = wait_commands(state, conflict_index + 1)[-1]
    exact_command(conflict)
    assert conflict["forwarded"] == 0 and conflict["response_status"] == 409
    wait_for(lambda: dom_state(page1), lambda value: "Command ID conflict" in value["status"], "understandable conflict feedback")
    assert dom_state(page1)["lifetime"] == "6"

    # No new typed executable intent exists beyond make_paperclip. Use the #9
    # explicitly supported existing-key/unsupported-action 409 path rather than
    # inventing a fake future command or claiming a new intent type exists.
    conflict_status, conflict_body = agent_client.post(json_bytes({
        "command_id": retry_command["command_id"], "type": "unsupported_action", "arguments": {},
    }))
    assert conflict_status == 409 and conflict_body == b'{"status":"conflict"}'
    after_api_conflict = api.checked_json(agent_client.get()[1])
    assert after_api_conflict["game"]["lifetime_clips"] == "6"
    assert agent_client.make(retry_command["command_id"]) == (dropped["response_status"], json_bytes(dropped["response_body"]))

    # Stock exhaustion is a real writer rejection, not a DOM disabled gate.
    for index in range(994):
        status, body = agent_client.make(f"m1-ui-exhaust-{index}")
        assert status == 200, (index, status, body)
    exhausted = api.checked_json(agent_client.get()[1])
    assert exhausted["game"]["wire"] == "0" and exhausted["game"]["lifetime_clips"] == "1000"
    rejection_index = len(state.command_records)
    page1.press("Enter")
    rejection_record = wait_commands(state, rejection_index + 1)[-1]
    assert rejection_record["response_status"] == 422 and rejection_record["response_body"]["reason"] == "insufficient_wire"
    wait_for(lambda: dom_state(page1), lambda value: "not enough Wire" in value["status"] and "no resource change" in value["status"], "real rejection feedback")
    assert dom_state(page1)["lifetime"] == "1000" and dom_state(page1)["wire"] == "0"
    rejected_id = exact_command(rejection_record)["command_id"]
    assert agent_client.make(rejected_id) == (422, json_bytes(rejection_record["response_body"]))
    after_rejection = api.checked_json(agent_client.get()[1])
    assert after_rejection["game"] == exhausted["game"]
    agent_client.close()

    return {"commandsThroughUIProxy": len(state.command_records), "twoPageConvergedClips": "1000",
            "agentAppliedCommands": 995, "sameIdRetryAppliedOnce": True,
            "realRuleRejections": 1, "apiConflicts": 1, "typedProxyConflicts": 1,
            "allUIEnvelopesExact": all(exact_command(record) for record in state.command_records)}



def check_numeric_helpers(page: Cdp, worktree: Path) -> dict[str, Any]:
    result = page.evaluate("""(async () => {
      const amount = await import('/static/stream.js');
      const display = await import('/static/view-model.js');
      const {parseAmount, formatAmount, compareAmount, addAmount, ceilAmount} = amount;
      const checks = [];
      const check = (condition, label) => { if (!condition) throw new Error(label); checks.push(label); };
      check(parseAmount('0.000000000000000001').scaled === 1n, '1e-18 scaled BigInt');
      check(parseAmount('-0.000000000000000001').scaled === -1n, 'signed 1e-18 scaled BigInt');
      check(formatAmount(parseAmount('9007199254740993').scaled) === '9007199254740993', '2^53+1 round trip');
      check(formatAmount(parseAmount('30000000000000000000000000000000000000000000000000000001').scaled) === '30000000000000000000000000000000000000000000000000000001', '3e55+1 round trip');
      check(formatAmount(parseAmount('340282366920938463463374607431768211457').scaled) === '340282366920938463463374607431768211457', 'beyond u128 round trip');
      check(compareAmount('9007199254740993', '9007199254740992') === 1, '2^53 exact comparison');
      check(addAmount('0.000000000000000001', '-0.000000000000000001') === '0', 'signed tiny exact add');
      check(addAmount('340282366920938463463374607431768211456', '1') === '340282366920938463463374607431768211457', 'unbounded exact add');
      check(ceilAmount('0.000000000000000001') === '1', 'tiny positive ceiling');
      check(ceilAmount('-0.000000000000000001') === '0', 'tiny signed ceiling');
      check(ceilAmount('1.001') === '2', 'fraction ceiling');
      check(ceilAmount('-1.001') === '-1', 'negative fraction ceiling');
      check(display.formatAmountForDisplay('6.1', {currency: true}) === '6.10', 'currency minimum two digits');
      check(display.formatAmountForDisplay('6.331', {currency: true}) === '6.331', 'no cent rounding');
      check(display.formatAmountForDisplay('-41117.99', {currency: true}) === '-41,117.99', 'signed currency grouping');
      const invalid = ['', '-0', '+1', '01', '1.0', '.5', '1.', '1e3', ' 1', '1 ', '1\\n',
        '\\uFF11\\uFF12', 'NaN', 'Infinity', '0.0000000000000000000', '1.2345678901234567890',
        '1,000', 1, '1.000000000000000000'];
      for (const value of invalid) {
        let reason = null;
        try { parseAmount(value); } catch (error) { reason = error.message; }
        check(reason === 'non-canonical Amount', 'designated noncanonical rejection ' + String(value));
      }
      let capReason = null;
      try { parseAmount('1'.repeat(1048577)); } catch (error) { capReason = error.message; }
      check(capReason === 'non-canonical Amount', 'explicit character/allocation guard');
      return {checks: checks.length, invalidRejected: invalid.length, capRejected: capReason === 'non-canonical Amount'};
    })()""")
    assert result["invalidRejected"] == 19 and result["capRejected"] is True, result
    # Authority/display modules contain no numeric conversion calls; safe
    # integer predicates for bounded protocol counters remain legitimate.
    for relative in ("static/app.js", "static/commands.js", "static/view-model.js", "static/stream.js"):
        source = (worktree / relative).read_text()
        assert "parseFloat(" not in source and "Number(" not in source, relative
    return result


def settle_dom(page: Cdp) -> None:
    page.evaluate("new Promise(resolve => setTimeout(() => resolve(true), 75))")


def run_numeric_and_ordering(browser: Browser, state: ProxyState, template: dict[str, Any],
                             page: Cdp, worktree: Path) -> dict[str, Any]:
    run_id = "native-numeric-fixture-run"
    frames = [
        fixture_view(template, run_id, 1, {}),
        fixture_view(template, run_id, 2, {
            "lifetime_clips": "0", "unsold_clips": "0", "unused_clips": "0",
            "wire": "0", "funds": "0", "auto_clipper_revealed": True,
            "auto_clipper_cost": "6.1", "computing_hidden": False,
        }),
        fixture_view(template, run_id, 3, {
            "lifetime_clips": "9007199254740993",
            "unsold_clips": "30000000000000000000000000000000000000000000000000000001",
            "unused_clips": "340282366920938463463374607431768211457",
            "wire": "0.000000000000000001", "funds": "-41117.99",
            "auto_clipper_revealed": True, "auto_clipper_cost": "6.1",
            "computing_hidden": False, "marketing_level": "0", "trust": "0",
            "processors": "0", "memory": "0",
        }),
        fixture_view(template, run_id, 4, {
            "auto_clipper_revealed": True, "auto_clipper_cost": "6.331",
            "computing_hidden": False,
        }),
        fixture_view(template, run_id, 20, {
            "lifetime_clips": "20", "unsold_clips": "20", "unused_clips": "20",
            "wire": "980", "auto_clipper_revealed": True, "auto_clipper_cost": "6.331",
            "computing_hidden": False,
        }),
        fixture_view(template, run_id, 19, {
            "lifetime_clips": "19", "unsold_clips": "19", "unused_clips": "19",
            "wire": "981", "auto_clipper_revealed": True, "auto_clipper_cost": "6.331",
            "computing_hidden": False,
        }),
        fixture_view(template, run_id, 20, {
            "lifetime_clips": "999", "unsold_clips": "999", "unused_clips": "999",
            "wire": "1", "auto_clipper_revealed": True, "auto_clipper_cost": "6.331",
            "computing_hidden": False,
        }),
        fixture_view(template, run_id, 21, {
            "lifetime_clips": "21", "funds": "1.0", "auto_clipper_revealed": True,
            "computing_hidden": False,
        }),
        fixture_view(template, run_id, 22, {
            "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22",
            "wire": "978", "funds": "0", "auto_clipper_revealed": True,
            "auto_clipper_cost": "6.331", "computing_hidden": False,
        }),
    ]
    state.fixture_frames = frames
    state.fixture_sent = [threading.Event() for _ in frames]
    state.fixture_release = [threading.Event() for _ in frames]
    page.call("Page.reload", {"ignoreCache": True})

    def amount(element: str) -> dict[str, Any]:
        return page.evaluate(f"""(() => {{ const e = document.getElementById({element!r});
          return {{canonical: e.dataset.canonical, display: e.textContent, title: e.title}}; }})()""")

    assert state.fixture_sent[0].wait(8), "fixture baseline sent"
    wait_dom(page, "document.documentElement.dataset.revision", "1", "fixture baseline")
    page.evaluate("""(() => { window.nativeLiveMutations = 0;
      window.nativeLiveObserver = new MutationObserver(records => { window.nativeLiveMutations += records.length; });
      window.nativeLiveObserver.observe(document.getElementById('command-status'), {childList: true, characterData: true, subtree: true});
      return true; })()""")
    state.fixture_release[0].set()

    assert state.fixture_sent[1].wait(8)
    wait_dom(page, "document.documentElement.dataset.revision", "2", "exact zero fixture")
    assert amount("lifetime-clips") == {"canonical": "0", "display": "0", "title": "0"}
    assert amount("funds")["display"] == "0.00"
    assert amount("auto-clipper-cost") == {"canonical": "6.1", "display": "6.10", "title": "6.1"}
    assert page.evaluate("document.getElementById('computational-resources').hidden") is False
    assert page.evaluate("document.getElementById('auto-clippers-panel').hidden") is False
    state.fixture_release[1].set()

    assert state.fixture_sent[2].wait(8)
    wait_dom(page, "document.documentElement.dataset.revision", "3", "extreme Amount DOM fixture")
    expected = {
        "lifetime-clips": "9007199254740993",
        "unsold-clips": "30000000000000000000000000000000000000000000000000000001",
        "unused-clips": "340282366920938463463374607431768211457",
        "wire": "0.000000000000000001",
        "funds": "-41117.99",
    }
    for element, canonical in expected.items():
        actual = amount(element)
        assert actual["canonical"] == canonical and actual["title"] == canonical, (element, actual)
        if element == "funds":
            assert actual["display"] == "-41,117.99"
        else:
            assert actual["display"].replace(",", "") == canonical, (element, actual)
    state.fixture_release[2].set()

    assert state.fixture_sent[3].wait(8)
    wait_dom(page, "document.documentElement.dataset.revision", "4", "unrounded stored cost")
    assert amount("auto-clipper-cost") == {"canonical": "6.331", "display": "6.331", "title": "6.331"}
    state.fixture_release[3].set()

    assert state.fixture_sent[4].wait(8)
    wait_dom(page, "document.documentElement.dataset.revision", "20", "newest full View before old GET")
    state.fixture_get_gate.set()
    assert state.fixture_get_delivered.wait(8), "old GET actually delivered after high DOM"
    settle_dom(page)
    assert dom_state(page)["revision"] == "20" and dom_state(page)["lifetime"] == "20"
    state.fixture_release[4].set()

    # Delayed lower and conflicting equal frames are both presentation-inert.
    assert state.fixture_sent[5].wait(8)
    settle_dom(page)
    assert dom_state(page)["revision"] == "20" and dom_state(page)["lifetime"] == "20"
    state.fixture_release[5].set()
    assert state.fixture_sent[6].wait(8)
    settle_dom(page)
    assert dom_state(page)["revision"] == "20" and dom_state(page)["lifetime"] == "20"
    state.fixture_release[6].set()

    # A structurally complete but noncanonical Amount frame has its designated
    # failure and cannot replace the last good production-like DOM.
    assert state.fixture_sent[7].wait(8)
    settle_dom(page)
    assert dom_state(page)["revision"] == "20" and dom_state(page)["lifetime"] == "20"
    assert page.evaluate("document.getElementById('connection-status').textContent.includes('invalid server View')")
    state.fixture_release[7].set()
    assert state.fixture_sent[8].wait(8)
    wait_dom(page, "document.documentElement.dataset.revision", "22", "valid full View after bad frame")
    assert dom_state(page)["lifetime"] == "22" and dom_state(page)["wire"] == "978"
    state.fixture_release[8].set()

    numeric = check_numeric_helpers(page, worktree)
    live_mutations = page.evaluate("""(() => { window.nativeLiveObserver.disconnect();
      const count = window.nativeLiveMutations; delete window.nativeLiveObserver;
      delete window.nativeLiveMutations; return count; })()""")
    assert live_mutations == 0, "View-only rendering does not flood the polite command live region"
    state.fixture_close.set()
    return {"completeFixtureViews": len(frames), "numericHelperChecks": numeric["checks"],
            "noncanonicalRejected": numeric["invalidRejected"] + 1,
            "staleLowerAndEqualFramesIgnored": 2, "badFullViewsIgnored": 1,
            "delayedOldGetDeliveredAfterHighDom": True,
            "liveRegionMutationsDuringEightViews": live_mutations}


def run_recovery(binary: Path, temporary: Path, browser: Browser) -> dict[str, Any]:
    port = api.free_port()
    database = temporary / "recovery.sqlite3"
    state = ProxyState(port)
    proxy, proxy_thread = start_proxy(state)
    origin = f"http://127.0.0.1:{proxy.server_address[1]}"
    old_origin = browser.origin
    page = None
    old_process = None
    replacement = None
    out = (temporary / "recovery-old.stdout").open("wb")
    err = (temporary / "recovery-old.stderr").open("wb")
    try:
        arguments = ["--listen-addr", f"127.0.0.1:{port}", "--database-path", str(database)]
        old_process = api.start_ready(binary, arguments, port, temporary, out, err)
        baseline_count = len(state.stream_baselines)
        state.drop_first_stream = True
        browser.origin = origin
        page, context_id, _ = browser.new_page("/")
        wait_for(lambda: dom_state(page), lambda value: value.get("viewState") == "ready", "old-run initial UI")
        # The proxy closes after the first complete initial frame. EventSource's
        # ordinary automatic second physical connection gives the old run a
        # real reconnect interval before the crash race, matching #11 timing.
        wait_for(lambda: state.stream_connections >= 2 and len(state.stream_baselines) >= 2,
                 description="old-run physical reconnect", timeout=10)
        wait_for(lambda: dom_state(page), lambda value: int(value.get("revision", "0")) >= state.stream_baselines[1]["revision"],
                 "old-run second baseline", timeout=10)
        agent = api.Client(port)
        for index in range(20):
            status, body = agent.make(f"native-ui-recovery-{index}")
            assert status == 200, (status, body)
        pre_crash = api.checked_json(agent.get()[1])
        agent.close()
        before_refresh = wait_for(lambda: dom_state(page), lambda value: value.get("lifetime") == "20", "recovery pre-crash page")
        state.hold_next_get = True
        state.get_captured.clear()
        state.get_release.clear()
        page.call("Page.reload", {"ignoreCache": True})
        assert state.get_captured.wait(8), "actual old-run GET captured"
        same_run_refresh = wait_for(lambda: dom_state(page), lambda value: value.get("lifetime") == "20", "refresh retains shared world")
        assert same_run_refresh["runId"] == before_refresh["runId"]
        assert state.get_record is not None and not state.get_record["delivered"]
        assert state.get_record["body"]["run_id"] == before_refresh["runId"]
        old_process.force_stop()
        old_process = None
        new_out = (temporary / "recovery-new.stdout").open("wb")
        new_err = (temporary / "recovery-new.stderr").open("wb")
        with new_out, new_err:
            replacement = api.start_ready(binary, arguments, port, temporary, new_out, new_err)
        recovered = wait_for(lambda: dom_state(page), lambda value: value.get("runId") not in (None, before_refresh["runId"]) and value.get("lifetime") == "0", "recovered lower-revision browser baseline", timeout=15)
        assert len(state.stream_baselines) > baseline_count
        new_run_baselines = [baseline for baseline in state.stream_baselines[baseline_count:]
                             if baseline["run_id"] == recovered["runId"]]
        assert new_run_baselines, state.stream_baselines[-12:]
        recovery_baseline = new_run_baselines[0]
        assert recovery_baseline["revision"] < state.get_record["body"]["revision"], {
            "old": state.get_record["body"]["revision"], "recovered": recovery_baseline["revision"],
            "recentBaselines": state.stream_baselines[-12:]}
        assert int(recovered["revision"]) >= recovery_baseline["revision"]
        state.get_release.set()
        wait_for(lambda: state.get_record["delivered"], description="old GET release", timeout=8)
        settle_dom(page)
        after_old_get = dom_state(page)
        assert after_old_get["runId"] == recovered["runId"] and after_old_get["lifetime"] == "0"
        # Process-lifetime retry history is intentionally empty after recovery;
        # a new current command uses the ordinary public API, never a reset UI.
        new_agent = api.Client(port)
        status, body = new_agent.make("native-ui-recovery-0")
        assert status == 200 and api.checked_json(body)["status"] == "applied"
        new_view = api.checked_json(new_agent.get()[1])
        new_agent.close()
        assert new_view["game"]["lifetime_clips"] == "1" and new_view["run_id"] == recovered["runId"]
        wait_for(lambda: dom_state(page), lambda value: value.get("lifetime") == "1" and value.get("runId") == recovered["runId"], "post-recovery live command")
        return {"realSigkillRecovery": True, "recoveredRevisionLower": True,
                "refreshKeptRun": True, "delayedOldGetAfterRecovery": "stale/no DOM effect",
                "postRecoveryCommandVisible": True}
    finally:
        browser.origin = old_origin
        state.get_release.set()
        state.fixture_close.set()
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=5)
        if replacement is not None:
            replacement.stop()
        if old_process is not None:
            old_process.force_stop()
        out.close()
        err.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--browser", default=os.environ.get("PAPERCLIP_BROWSER"))
    parser.add_argument("--require-browser", action="store_true")
    args = parser.parse_args()
    executable = find_browser(args.browser)
    if executable is None:
        message = "real native UI browser evidence NOT EXECUTED: no Chrome/Chromium found"
        if args.require_browser:
            raise AssertionError(message)
        print(message)
        return 0
    version = subprocess.run([executable, "--version"], capture_output=True, text=True,
                             timeout=10, check=True).stdout.strip()
    print(f"real browser: {version}")
    binary = args.binary.resolve()
    worktree = Path(__file__).resolve().parent.parent
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="paperclip-native-ui-browser-") as temporary_name:
        temporary = Path(temporary_name)
        main_port = api.free_port()
        database = temporary / "native-ui.sqlite3"
        state = ProxyState(main_port)
        proxy, proxy_thread = start_proxy(state)
        origin = f"http://127.0.0.1:{proxy.server_address[1]}"
        process = None
        browser = None
        out = (temporary / "main.stdout").open("wb")
        err = (temporary / "main.stderr").open("wb")
        try:
            process = api.start_ready(binary, ["--listen-addr", f"127.0.0.1:{main_port}",
                                                "--database-path", str(database)],
                                      main_port, temporary, out, err)
            initial_client = api.Client(main_port)
            template = api.checked_json(initial_client.get()[1])
            initial_client.close()
            browser = Browser(executable, temporary, origin)
            page1, context1, _ = browser.new_page("/")
            page2, context2, target2 = browser.new_page("/")
            assert context1 != context2, "independent anonymous browser contexts"
            print("native UI: two independent browser contexts opened on /")
            main_result = run_main_ui(browser, state, main_port, page1, page2)
            print(f"native UI: two-page/command/accessibility checks passed: {main_result}")
            numeric_result = run_numeric_and_ordering(browser, state, template, page2, worktree)
            print(f"native UI: exact Amount DOM and ordering fixtures passed: {numeric_result}")
            assert browser.browser_connection is not None
            browser.browser_connection.call("Target.closeTarget", {"targetId": target2})
            browser.pages.remove(page2)
            page2.close()
            recovery_result = run_recovery(binary, temporary, browser)
            print(f"native UI: real refresh/reconnect/recovery passed: {recovery_result}")
            assert not state.errors, state.errors[:10]
            summary = {
                "status": "pass", "browser": version, "independentBrowserContexts": 2,
                "main": main_result, "numericOrdering": numeric_result,
                "recovery": recovery_result, "durationSeconds": round(time.perf_counter() - started, 3),
            }
            print("NATIVE_UI_BROWSER_SUMMARY=" + json.dumps(summary, separators=(",", ":")))
            return 0
        finally:
            if browser is not None:
                browser.close()
            state.command_release.set()
            state.get_release.set()
            state.fixture_close.set()
            state.fixture_get_gate.set()
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=5)
            if process is not None:
                process.stop()
            out.close()
            err.close()


if __name__ == "__main__":
    raise SystemExit(main())
