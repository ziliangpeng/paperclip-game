#!/usr/bin/env python3
"""Real-Chrome Issue #12 verification for the native public game page."""
from __future__ import annotations

import argparse
import base64
import copy
from contextlib import contextmanager
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
from typing import Any, Callable, Iterator
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
        try:
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
        except BaseException:
            # The caller cannot close a Browser whose constructor did not
            # return. Release this instance's own Chrome before propagating.
            self.close()
            raise

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
        # Explicit finite response faults. None is the ordinary real-backend path.
        self.next_command_response: dict[str, Any] | None = None
        self.next_get_response: dict[str, Any] | None = None
        self.get_override_delivered = threading.Event()
        self.get_override_records: list[dict[str, Any]] = []
        self.hold_first_stream = False
        self.first_stream_captured = threading.Event()
        self.first_stream_release = threading.Event()
        self.gate_stream_after_baseline: int | None = None
        self.real_stream_held = threading.Event()
        self.real_stream_gate = threading.Event()
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
                   cache_control: str | None = None, nosniff: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            if nosniff:
                self.send_header("X-Content-Type-Options", nosniff)
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
                    content_type: str | None = None) -> tuple[int, bytes, str, str | None, str | None]:
            client = http.client.HTTPConnection("127.0.0.1", state.backend_port, timeout=8)
            try:
                headers = {}
                if content_type:
                    headers["Content-Type"] = content_type
                client.request(method, path, body=body, headers=headers)
                response = client.getresponse()
                raw = response.read(2 * 1024 * 1024 + 1)
                assert len(raw) <= 2 * 1024 * 1024, "bounded proxy response"
                return (response.status, raw,
                        response.getheader("Content-Type") or "application/octet-stream",
                        response.getheader("Cache-Control"),
                        response.getheader("X-Content-Type-Options"))
            finally:
                client.close()

        def fault_view_response(self, status: int, raw: bytes, kind: str,
                                cache: str | None, nosniff: str | None) -> bool:
            if self.path != "/api/game/view" or state.next_get_response is None:
                return False
            override = state.next_get_response
            state.next_get_response = None
            body = raw if override.get("body") is None else override["body"]
            assert isinstance(body, bytes) and len(body) <= 16 * 1024
            state.get_override_records.append({
                "upstreamStatus": status, "upstreamBody": json.loads(raw),
                "upstreamContentType": kind, "upstreamCacheControl": cache,
                "upstreamNosniff": nosniff,
                "injectedContentType": override["content_type"],
                "injectedBodyLength": len(body),
            })
            assert len(state.get_override_records) <= 50
            self.finite(status, body, override["content_type"], cache, nosniff)
            state.get_override_delivered.set()
            return True

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
                    status, raw, kind, cache, nosniff = self.backend("GET", self.path, body)
                    state.get_record = {"status": status, "body": json.loads(raw),
                                        "delivered": False}
                    state.get_captured.set()
                    assert state.get_release.wait(12), "bounded held real GET"
                    state.get_record["delivered"] = True
                    if self.fault_view_response(status, raw, kind, cache, nosniff):
                        return
                    self.finite(status, raw, kind, cache, nosniff)
                    return
                status, raw, kind, cache, nosniff = self.backend("GET", self.path, body)
                if self.fault_view_response(status, raw, kind, cache, nosniff):
                    return
                self.finite(status, raw, kind, cache, nosniff)
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
            if state.hold_first_stream:
                state.first_stream_captured.set()
                assert state.first_stream_release.wait(12), "bounded initial SSE request gate"
                state.hold_first_stream = False
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

                    if (state.gate_stream_after_baseline == connection_number
                            and initial_lines is None):
                        state.gate_stream_after_baseline = None
                        state.real_stream_held.set()
                        assert state.real_stream_gate.wait(12), "bounded real SSE gate"
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
                override = state.next_command_response
                state.next_command_response = None
                if override is not None:
                    response_body = override["body"]
                    assert isinstance(response_body, bytes) and len(response_body) <= 16 * 1024 + 1
                    record["response_status"] = override.get("status", 200)
                    record["responseContentType"] = override["content_type"]
                    record["injectedResponse"] = True
                    self.finite(record["response_status"], response_body, override["content_type"])
                    return
                if state.conflict_next:
                    state.conflict_next = False
                    record["response_status"] = 409
                    self.finite(409, b'{"status":"conflict"}', "application/json")
                    return
                status, response_body, kind, cache, nosniff = self.backend(
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
                self.finite(status, response_body, kind, cache, nosniff)
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
        assert response.getheader("X-Content-Type-Options") == "nosniff", path
        if path == "/static/stream.js":
            assert response.getheader("Cache-Control") == "no-cache"
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


def drain_render_tasks(page: Cdp) -> None:
    """Drain queued Render/MutationObserver work, never wait on guessed sleeps."""
    page.evaluate("new Promise(resolve => queueMicrotask(() => queueMicrotask(() => resolve(true))))")


def run_startup_feedback_and_cleanup(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """Actual pre-baseline command orderings and failed-constructor ownership."""
    with tempfile.TemporaryDirectory(prefix="paperclip-native-ui-startup-") as temporary_name:
        temporary = Path(temporary_name)
        backend_port = api.free_port()
        database = temporary / "startup.sqlite3"
        state = ProxyState(backend_port)
        # Only this isolated startup proxy delays physical transport delivery.
        state.stream_release = threading.Event()
        state.stream_started = threading.Event()
        state.stream_release.set()
        BaseHandler = proxy_handler(state)

        class StartupHandler(BaseHandler):
            def stream(self) -> None:
                state.stream_started.set()
                assert state.stream_release.wait(12), "bounded real initial-stream gate"
                super().stream()

        proxy = Proxy(("127.0.0.1", 0), StartupHandler)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        origin = f"http://127.0.0.1:{proxy.server_address[1]}"
        process = None
        browser = None
        out = (temporary / "startup.stdout").open("wb")
        err = (temporary / "startup.stderr").open("wb")
        result: dict[str, Any] = {"browser": version}
        owner = None
        assigned = None
        try:
            process = api.start_ready(binary, ["--listen-addr", f"127.0.0.1:{backend_port}",
                                                "--database-path", str(database)],
                                      backend_port, temporary, out, err)
            browser = Browser(executable, temporary, origin)
            healthy, healthy_context, healthy_target = browser.new_page("/")
            healthy_view = wait_for(
                lambda: dom_state(healthy),
                lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "0"
                and value.get("wire") == "1000" and value["status"].startswith("Ready."),
                "ordinary no-action startup Ready")
            assert healthy_view["runId"] and healthy_view["ariaDisabled"] == "false"
            result["ordinaryStartup"] = healthy_view
            assert browser.browser_connection is not None
            browser.browser_connection.call("Target.closeTarget", {"targetId": healthy_target})
            browser.pages.remove(healthy)
            healthy.close()

            def activate_before_baseline() -> Cdp:
                state.hold_next_get = True
                state.get_captured.clear()
                state.get_release.clear()
                state.stream_started.clear()
                state.stream_release.clear()
                page, _, _ = browser.new_page("/")
                wait_dom(page, "document.getElementById('make-paperclip').getAttribute('aria-disabled')", "false", "startup module initialized")
                assert state.get_captured.wait(8), "real initial GET body captured"
                assert state.stream_started.wait(8), "real initial EventSource gated"
                page.evaluate("""(() => {
                  window.startupStatusHistory = [];
                  window.startupStatusObserver = new MutationObserver(() => {
                    window.startupStatusHistory.push(document.getElementById('command-status').textContent);
                  });
                  window.startupStatusObserver.observe(document.getElementById('command-status'),
                    {childList: true, characterData: true, subtree: true});
                  document.getElementById('make-paperclip').focus();
                  return true;
                })()""")
                page.press("Enter")
                return page

            # A: a valid first View hydrates 0/1000 while the exact POST stays held.
            state.hold_commands = True
            state.command_release.clear()
            pending_page = activate_before_baseline()
            wait_commands(state, 1)
            pending = wait_for(lambda: dom_state(pending_page),
                               lambda value: "pending" in value["status"].lower() and value["ariaDisabled"] == "true",
                               "early held pending")
            assert pending["viewState"] == "loading" and pending.get("lifetime") is None and pending.get("wire") is None
            assert pending["focus"] == "make-paperclip" and pending["button"] == "Sending…" and not pending["disabled"]
            state.stream_release.set()
            state.get_release.set()
            after_pending = wait_for(
                lambda: dom_state(pending_page),
                lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "0" and value.get("wire") == "1000",
                "baseline released while command remains held")
            drain_render_tasks(pending_page)
            pending_history = list(pending_page.evaluate("window.startupStatusHistory"))
            assert pending_history == [pending["status"]], pending_history
            assert "pending" in after_pending["status"].lower() and after_pending["ariaDisabled"] == "true"
            assert after_pending["button"] == "Sending…" and after_pending["focus"] == "make-paperclip"
            assert all(not message.startswith("Ready.") for message in pending_history)
            state.command_release.set()
            state.hold_commands = False
            after_release = wait_for(
                lambda: dom_state(pending_page),
                lambda value: value.get("lifetime") == "1" and value.get("wire") == "999" and "applied" in value["status"],
                "released exact command applies once")
            assert after_release["ariaDisabled"] == "false" and after_release["focus"] == "make-paperclip"
            result["pendingBeforeBaseline"] = {
                "afterFirstView": after_pending, "mutationHistory": pending_history,
                "afterReleasedPost": after_release,
            }

            # B: actual applied receipt arrives before either initial View transport.
            applied_page = activate_before_baseline()
            wait_commands(state, 2)
            early_applied = wait_for(lambda: dom_state(applied_page),
                                     lambda value: value.get("viewState") == "loading" and "applied" in value["status"],
                                     "actual applied receipt before baseline")
            assert early_applied.get("lifetime") is None and early_applied.get("wire") is None
            assert state.command_records[1]["response_status"] == 200
            state.stream_release.set()
            state.get_release.set()
            after_applied = wait_for(
                lambda: dom_state(applied_page),
                lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "2" and value.get("wire") == "998",
                "coherent View after applied receipt")
            drain_render_tasks(applied_page)
            applied_history = list(applied_page.evaluate("window.startupStatusHistory"))
            applied_revision = state.command_records[1]["response_body"]["revision"]
            assert f"applied the command at revision {applied_revision}." in after_applied["status"]
            assert any("applied" in message for message in applied_history)
            assert all(not message.startswith("Ready.") for message in applied_history)
            result["appliedBeforeBaseline"] = {"afterFirstView": after_applied, "mutationHistory": applied_history}

            # C: convert real stock through the public Agent API, then receive a true
            # insufficient-wire 422 on a third fresh page before its first View.
            public = api.Client(backend_port)
            current = api.checked_json(public.get()[1])
            api.assert_production(current, "998", "2")
            remaining_wire = int(current["game"]["wire"])
            for index in range(remaining_wire):
                status, response_body = public.make(f"m1-startup-stock-{index}")
                assert status == 200, (index, status, response_body)
            exhausted = api.checked_json(public.get()[1])
            api.assert_production(exhausted, "0", "1000")
            public.close()
            rejected_page = activate_before_baseline()
            wait_commands(state, 3)
            early_rejection = wait_for(lambda: dom_state(rejected_page),
                                       lambda value: value.get("viewState") == "loading" and "not enough Wire" in value["status"],
                                       "real exhausted-stock 422 before baseline")
            assert early_rejection.get("lifetime") is None and early_rejection.get("wire") is None
            assert state.command_records[2]["response_status"] == 422
            assert state.command_records[2]["response_body"]["status"] == "rule_rejected"
            assert state.command_records[2]["response_body"]["reason"] == "insufficient_wire"
            state.stream_release.set()
            state.get_release.set()
            after_rejection = wait_for(
                lambda: dom_state(rejected_page),
                lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "1000" and value.get("wire") == "0",
                "authoritative exhausted View after 422")
            drain_render_tasks(rejected_page)
            rejection_history = list(rejected_page.evaluate("window.startupStatusHistory"))
            assert "not enough Wire" in after_rejection["status"]
            assert after_rejection["focus"] == "make-paperclip" and after_rejection["ariaDisabled"] == "false"
            assert any("not enough Wire" in message for message in rejection_history)
            assert all(not message.startswith("Ready.") for message in rejection_history)
            result["ruleRejectedBeforeBaseline"] = {
                "afterFirstView": after_rejection, "mutationHistory": rejection_history,
                "structuredAgentApplied": remaining_wire, "agentDrainedStock": True,
            }
            envelopes = [exact_command(record) for record in state.command_records]
            assert len(envelopes) == 3 and len({body["command_id"] for body in envelopes}) == 3
            assert all(record["forwarded"] == 1 and not record["dropped"] for record in state.command_records)
            assert not state.errors, state.errors[:10]
            result["exactStartupEnvelopes"] = len(envelopes)
            result["proxyErrors"] = state.errors

            # Separate failed PROFILE/process from the healthy browser above.
            failed_directory = temporary / "failed-constructor"
            failed_directory.mkdir()

            class InjectedVersionFailure(Browser):
                def http_json(self, path: str) -> Any:
                    nonlocal owner
                    owner = self
                    raise TimeoutError("injected CDP /json/version failure")
            constructor_error = None
            try:
                assigned = InjectedVersionFailure(executable, failed_directory, "http://127.0.0.1:9")
            except TimeoutError as error:
                constructor_error = str(error)
            assert constructor_error == "injected CDP /json/version failure"
            assert assigned is None, "constructor could not complete; caller cleanup is unavailable"
            assert owner is not None and owner.port > 0
            failed_child = owner.process
            # Crucially, no owner.close() has run before this observable assertion.
            failed_child_status = failed_child.poll()
            assert failed_child_status is not None, "constructor itself must terminate its owned Chrome"
            result["injectedConstructorCleanup"] = {
                "errorPreserved": constructor_error, "realDevToolsPortAssigned": True,
                "callerAssignmentIsNone": assigned is None, "childExitedBeforeFallback": True,
            }
            live_browser_process = browser.process
            browser.close()
            assert live_browser_process.poll() is not None
            browser = None
            result["healthyChromeClosed"] = True
            process.stop()
            result["backendProcessEnded"] = process.process.poll() is not None
            assert result["backendProcessEnded"]
            return result
        finally:
            state.command_release.set()
            state.get_release.set()
            state.stream_release.set()
            # Failed-test fallback cannot make the earlier poll observation pass.
            if assigned is not None:
                assigned.close()
            elif owner is not None and owner.process.poll() is None:
                owner.close()
            if browser is not None:
                browser.close()
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=5)
            if process is not None and process.process.poll() is None:
                process.stop()
            out.close()
            err.close()


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
    # The rejection response can arrive before the last successful command's
    # SSE View. A response is not the global render order; wait for both the
    # actual rejection feedback and the corresponding authoritative DOM state.
    wait_for(lambda: dom_state(page1), lambda value: value["lifetime"] == "1000" and value["wire"] == "0" and "not enough Wire" in value["status"],
             "rejection feedback after last successful full View")
    rejected_id = exact_command(rejection_record)["command_id"]
    assert agent_client.make(rejected_id) == (422, json_bytes(rejection_record["response_body"]))
    after_rejection = api.checked_json(agent_client.get()[1])
    assert after_rejection["game"] == exhausted["game"]
    agent_client.close()

    return {"commandsThroughUIProxy": len(state.command_records), "twoPageConvergedClips": "1000",
            "agentAppliedCommands": 995, "sameIdRetryAppliedOnce": True,
            "realRuleRejections": 1, "apiConflicts": 1, "typedProxyConflicts": 1,
            "allUIEnvelopesExact": all(exact_command(record) for record in state.command_records)}



def check_response_boundaries(page: Cdp, closed_port: int) -> dict[str, Any]:
    """Native-Chrome response boundaries; synthetic Responses are explicit here."""
    result = page.evaluate(f"""(async () => {{
      const module = await import('/static/commands.js');
      const {{makePaperclipCommand, postMakePaperclip, readBoundedJson, MakePaperclipCommandRunner}} = module;
      if (Object.hasOwn(module, 'ResponseValidationError')) throw new Error('validation class must remain private');
      const headers = {{"Content-Type": "application/json"}};
      const command = makePaperclipCommand('response-validation-fixed-id');
      const response = (body, contentType = 'application/json') => new Response(body, {{status: 200, headers: {{"Content-Type": contentType}}}});
      const outcomes = {{}};
      const accepted = ['application/json', ' Application/JSON ; charset=UTF-8 ', 'application/json;charset=utf-8'];
      for (const contentType of accepted) {{
        const outcome = await postMakePaperclip(command, {{fetch: () => response('{{"status":"applied","revision":4}}', contentType)}});
        if (outcome.kind !== 'applied' || outcome.revision !== 4) throw new Error('valid JSON media rejected: ' + contentType);
      }}
      const rejected = ['application/jsonp', 'application/json-not-json', 'application/json-sequence',
        'application/json2', 'application/json...', 'application/json,application/json',
        'application/json, application/json; charset=utf-8', 'text/plain', '', 'application/json; charset=utf-8,application/json'];
      for (const contentType of rejected) {{
        const outcome = await postMakePaperclip(command, {{fetch: () => response('{{"status":"applied","revision":7}}', contentType)}});
        if (outcome.kind !== 'invalid_response') throw new Error('invalid JSON media accepted: ' + contentType);
      }}
      outcomes.mediaTypes = {{accepted: accepted.length, rejected: rejected.length}};
      const invalidBodies = [
        ['malformed', '{{bad json'], ['empty', ''],
        ['invalidUtf8', new Uint8Array([123, 34, 120, 34, 58, 255, 125])],
        ['oversize', new Uint8Array(16385)], ['nullBody', null],
      ];
      const bodyCases = {{}};
      for (const [name, body] of invalidBodies) {{
        let error = null;
        try {{ await readBoundedJson(response(body)); }} catch (caught) {{ error = caught; }}
        if (!error || !(error instanceof TypeError) || error.constructor.name !== 'ResponseValidationError') {{
          throw new Error('validation type: ' + name + ' ' + String(error));
        }}
        if (name === 'oversize' && error.message !== 'oversized command response') throw new Error('oversize message changed');
        if (name === 'nullBody' && error.message !== 'empty command response') throw new Error('null body message changed');
        const events = [];
        const runner = new MakePaperclipCommandRunner(event => events.push(event), {{fetch: () => response(body)}});
        const outcome = await runner.run();
        bodyCases[name] = {{...outcome, command: undefined, retry: runner.retryAvailable,
          pending: runner.pending, events: events.map(event => event.kind)}};
        if (outcome.kind !== 'invalid_response' || !runner.retryAvailable || runner.pending ||
            events.map(event => event.kind).join(',') !== 'pending,invalid_response') {{
          throw new Error('invalid response lifecycle: ' + name + ' ' + JSON.stringify(bodyCases[name]));
        }}
        const retryEvents = [];
        const retry = new MakePaperclipCommandRunner(event => retryEvents.push(event), {{fetch: () => response(body)}});
        const first = await retry.run();
        const retryBody = retry.retryCommand;
        if (first.kind !== 'invalid_response' || !retry.retryAvailable || !retryBody) throw new Error('missing invalid retry');
        const posted = JSON.stringify(retryBody);
        if (Object.keys(retryBody).join(',') !== 'command_id,type,arguments' ||
            retryBody.type !== 'make_paperclip' || Object.keys(retryBody.arguments).length !== 0 ||
            JSON.stringify(retryBody) !== posted) throw new Error('immutable exact command retry');
        const real = await postMakePaperclip(retryBody, {{fetch: () => response('{{"status":"applied","revision":8}}')}});
        if (real.kind !== 'applied' || JSON.stringify(retryBody) !== posted) throw new Error('retry payload normalization');
      }}
      outcomes.invalidBodies = bodyCases;
      const wrongShape = await postMakePaperclip(command, {{fetch: () => response('null')}});
      if (wrongShape.kind !== 'invalid_response') throw new Error('valid JSON wrong shape');
      const bodyStream = new ReadableStream({{start(controller) {{controller.error(new TypeError('native-body-read-failure'));}}}});
      const readRunner = new MakePaperclipCommandRunner(() => {{}}, {{fetch: () => response(bodyStream)}});
      outcomes.bodyReadFailure = await readRunner.run();
      if (outcomes.bodyReadFailure.kind !== 'network_error' || !readRunner.retryAvailable || readRunner.pending) {{
        throw new Error('body read is not response validation: ' + JSON.stringify(outcomes.bodyReadFailure));
      }}
      const network = new MakePaperclipCommandRunner(() => {{}}, {{
        timeoutMs: 2000,
        fetch: (url, options) => globalThis.fetch('http://127.0.0.1:{closed_port}/unreachable', {{signal: options.signal}}),
      }});
      outcomes.realFetchFailure = await network.run();
      if (outcomes.realFetchFailure.kind !== 'network_error' || !network.retryAvailable || network.pending) {{
        throw new Error('real network failure classification: ' + JSON.stringify(outcomes.realFetchFailure));
      }}
      const sent = [];
      let attempt = 0;
      const retryEvents = [];
      const retry = new MakePaperclipCommandRunner(event => retryEvents.push(event), {{fetch: (url, options) => {{
        sent.push(options.body);
        attempt += 1;
        if (attempt === 1) throw new TypeError('native-fetch-rejection-control');
        return response('{{"status":"applied","revision":9}}');
      }}}});
      const first = await retry.run();
      if (!retry.retryAvailable) throw new Error('network retry unavailable');
      const second = await retry.run();
      outcomes.retry = {{first: first.kind, second: second.kind, attempts: attempt,
        commandId: retryEvents[0].command.command_id,
        sameBytes: sent[0] === sent[1], envelope: sent[0], retry: retry.retryAvailable,
        events: retryEvents.map(event => event.kind)}};
      if (first.kind !== 'network_error' || second.kind !== 'applied' || attempt !== 2 ||
          sent[0] !== sent[1] || retry.retryAvailable ||
          retryEvents.map(event => event.kind).join(',') !== 'pending,network_error,pending,applied') {{
        throw new Error('same-body network retry: ' + JSON.stringify(outcomes.retry));
      }}
      return outcomes;
    }})()""")
    assert result["mediaTypes"] == {"accepted": 3, "rejected": 10}, result["mediaTypes"]
    assert set(result["invalidBodies"]) == {"malformed", "empty", "invalidUtf8", "oversize", "nullBody"}, result
    assert result["bodyReadFailure"]["kind"] == "network_error"
    assert "native-body-read-failure" in result["bodyReadFailure"]["message"]
    expected_retry = {"command_id": result["retry"]["commandId"], "type": "make_paperclip", "arguments": {}}
    assert isinstance(expected_retry["command_id"], str) and expected_retry["command_id"]
    assert result["retry"]["sameBytes"] is True
    assert result["retry"]["envelope"] == json.dumps(expected_retry, separators=(",", ":")), result["retry"]
    return result


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


@contextmanager
def isolated_r2_browser(binary: Path, executable: str, version: str, label: str) -> Iterator[dict[str, Any]]:
    """An owned real backend, fresh SQLite file, proxy and real Chrome process."""
    with tempfile.TemporaryDirectory(prefix=f"paperclip-{label}-") as temporary_name:
        temporary = Path(temporary_name)
        port = api.free_port()
        state = ProxyState(port)
        proxy, proxy_thread = start_proxy(state)
        process = None
        browser = None
        client = None
        info: dict[str, Any] = {}
        out = (temporary / "backend.stdout").open("wb")
        err = (temporary / "backend.stderr").open("wb")
        try:
            process = api.start_ready(binary, ["--listen-addr", f"127.0.0.1:{port}",
                                                "--database-path", str(temporary / "owned.sqlite3")],
                                      port, temporary, out, err)
            client = api.Client(port)
            browser = Browser(executable, temporary, f"http://127.0.0.1:{proxy.server_address[1]}")
            info.update({"state": state, "browser": browser, "client": client,
                         "version": version, "temporary": temporary,
                         "chromeProcess": browser.process, "backendProcess": process.process})
            yield info
            assert not state.errors, state.errors[:10]
        finally:
            state.command_release.set()
            state.get_release.set()
            state.first_stream_release.set()
            state.real_stream_gate.set()
            state.fixture_get_gate.set()
            state.fixture_close.set()
            for release in state.fixture_release:
                release.set()
            if browser is not None:
                browser.close()
                info["chromeExit"] = info["chromeProcess"].poll()
                assert info["chromeExit"] == 0, info
            proxy.shutdown()
            proxy.server_close()
            proxy_thread.join(timeout=5)
            assert not proxy_thread.is_alive()
            if client is not None:
                client.close()
            if process is not None:
                process.stop()
                info["backendExit"] = info["backendProcess"].poll()
                assert info["backendExit"] is not None, info
            out.close()
            err.close()


def run_r2_response_and_get(binary: Path, executable: str, version: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    with isolated_r2_browser(binary, executable, version, "native-r2-responses") as case:
        state: ProxyState = case["state"]
        browser: Browser = case["browser"]
        client: api.Client = case["client"]
        template = api.checked_json(client.get()[1])
        assert template["game"]["lifetime_clips"] == "0" and template["game"]["wire"] == "1000"
        state.get_override_delivered.clear()
        module = check_response_boundaries(browser.new_page("/")[0], api.free_port())
        result["module"] = module
        # Ordinary MIME parameters remain a healthy real GET and real upstream JSON.
        state.next_get_response = {"content_type": " Application/JSON ; charset=UTF-8 ", "body": None}
        positive_page = browser.new_page("/")[0]
        positive_get = wait_for(lambda: dom_state(positive_page),
            lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "0" and value.get("wire") == "1000",
            "real JSON View with ordinary parameters")
        assert len(state.get_override_records) == 1
        first_probe = state.get_override_records[0]
        assert first_probe["upstreamStatus"] == 200 and first_probe["upstreamBody"]["game"] == template["game"], first_probe
        result["realJsonWithParameters"] = {"dom": positive_get, "record": first_probe}

        # A valid server JSON body under JSONP is not accepted as the initial View.
        # Withhold its real native-SSE event terminator so the rejection is observable.
        state.get_override_delivered.clear()
        state.next_get_response = {"content_type": "application/jsonp", "body": None}
        state.hold_first_stream = True
        state.first_stream_captured.clear()
        state.first_stream_release.clear()
        page, context, target = browser.new_page("/")
        assert state.get_override_delivered.wait(8), "initial wrong-MIME response reached client"
        assert state.first_stream_captured.wait(8), "real native SSE request captured"
        blocked = wait_for(lambda: {**dom_state(page), "connection": page.evaluate("document.getElementById('connection-status').textContent")},
            lambda value: value.get("viewState") == "loading" and value.get("lifetime") is None and
                "waiting for a live server baseline" in value["connection"],
            "observable initial wrong-MIME rejection")
        state.first_stream_release.set()
        healthy = wait_for(lambda: dom_state(page),
            lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "0" and value.get("wire") == "1000",
            "real SSE baseline after rejected full View")
        result["rejectedInitialJsonpGet"] = {"beforeRealBaseline": blocked, "afterRealBaseline": healthy}

        page.evaluate("document.getElementById('make-paperclip').focus()")
        page.press("Enter")
        wait_commands(state, 1)
        healthy_command = wait_for(lambda: dom_state(page),
            lambda value: value.get("lifetime") == "1" and value.get("wire") == "999" and "Server applied" in value.get("status", ""),
            "genuine first UI command")
        assert state.command_records[0]["forwarded"] == 1 and "injectedResponse" not in state.command_records[0]
        before_game = api.checked_json(client.get()[1])["game"]
        assert before_game["lifetime_clips"] == "1" and before_game["wire"] == "999", before_game

        # Exact original adversarial wire input: finite JSONP HTTP 200, no backend write.
        fake_body = b'{"status":"applied","revision":7}'
        state.next_command_response = {"body": fake_body, "content_type": "application/jsonp"}
        page.evaluate("document.getElementById('make-paperclip').focus()")
        page.press("Enter")
        wait_commands(state, 2)
        rejected = state.command_records[1]
        wrong = wait_for(lambda: dom_state(page),
            lambda value: "response could not be validated" in value.get("status", ""), "visible JSONP rejection")
        assert rejected["forwarded"] == 0 and rejected["response_status"] == 200
        assert rejected["responseContentType"] == "application/jsonp" and rejected["injectedResponse"] is True
        assert "response_body" not in rejected
        assert wrong["lifetime"] == "1" and wrong["wire"] == "999" and wrong["ariaDisabled"] == "false"
        assert wrong["button"] == "Retry Make Paperclip" and "revision 7" not in wrong["status"]
        assert "SyntaxError" not in wrong["status"] and "{bad" not in wrong["status"]
        after_game = api.checked_json(client.get()[1])["game"]
        assert after_game == before_game, (before_game, after_game)
        result["actualUiJsonpRejection"] = {"request": exact_command(rejected), "httpStatus": 200,
            "responseContentType": "application/jsonp", "responseBody": fake_body.decode(),
            "forwarded": 0, "dom": wrong, "serverUnchanged": True}

        # The only induced failure is removed; a real user retry must hit the backend once.
        page.evaluate("document.getElementById('make-paperclip').focus()")
        page.press("Enter")
        wait_commands(state, 3)
        retry = state.command_records[2]
        assert retry["raw"] == rejected["raw"] and retry["json"] == rejected["json"]
        assert retry["raw"].decode() == json.dumps(rejected["json"], separators=(",", ":"))
        assert set(retry["json"]) == {"command_id", "type", "arguments"}
        applied = wait_for(lambda: dom_state(page),
            lambda value: value.get("lifetime") == "2" and value.get("wire") == "998" and
                int(value.get("revision", -1)) >= retry["response_body"]["revision"], "real same-ID/body retry")
        assert retry["forwarded"] == 1 and "injectedResponse" not in retry
        assert applied["status"] == (f"Server applied the command at revision {retry['response_body']['revision']}. "
            "Displayed resources come from the newest full server View.")
        after_retry_game = api.checked_json(client.get()[1])["game"]
        assert after_retry_game["lifetime_clips"] == "2" and after_retry_game["wire"] == "998"
        result["sameIntentRetry"] = {"request": exact_command(retry), "identicalToRejected": True,
            "forwarded": 1, "serverRevision": retry["response_body"]["revision"], "dom": applied}

        # Real HTTP response-body failures use the real POST and proxy, but no backend mutation.
        body_faults = [
            ("malformed", b'{bad json', "application/json; charset=utf-8"),
            ("empty", b"", "application/json"),
            ("invalidUtf8", bytes([123, 34, 120, 34, 58, 255, 125]), "application/json"),
            ("oversize", b" " * 16385, "application/json"),
        ]
        http_outcomes = {}
        for name, body, content_type in body_faults:
            state.next_command_response = {"body": body, "content_type": content_type}
            outcome = page.evaluate(f"""(async () => {{
              const {{makePaperclipCommand, MakePaperclipCommandRunner}} = await import('/static/commands.js');
              const events = [];
              const runner = new MakePaperclipCommandRunner(event => events.push(event), {{fetch: globalThis.fetch, timeoutMs: 2000}});
              const outcome = await runner.run();
              return {{outcome, kind: outcome.kind, retry: runner.retryAvailable, pending: runner.pending,
                events: events.map(event => event.kind), commandId: runner.retryCommand?.command_id}};
            }})()""")
            record = state.command_records[-1]
            assert outcome["kind"] == "invalid_response" and outcome["retry"] is True and outcome["pending"] is False, (name, outcome)
            assert outcome["events"] == ["pending", "invalid_response"] and isinstance(outcome["commandId"], str), (name, outcome)
            assert record["forwarded"] == 0 and record["json"]["command_id"] == outcome["commandId"]
            assert record["injectedResponse"] is True and record["responseContentType"] == content_type
            expected_http_body = {"command_id": outcome["commandId"], "type": "make_paperclip", "arguments": {}}
            assert record["json"] == expected_http_body
            assert exact_command(record) == expected_http_body
            assert record["raw"].decode() == json.dumps(expected_http_body, separators=(",", ":"))
            http_outcomes[name] = outcome
        assert api.checked_json(client.get()[1])["game"] == after_retry_game
        result["realHttpInvalidBodies"] = http_outcomes

        # Malformed real GET arrives after a real baseline for the same two-real-UI-command world.
        state.hold_next_get = True
        state.get_captured.clear()
        state.get_release.clear()
        state.next_get_response = {"body": b'{bad json', "content_type": "application/json"}
        late_page, late_context, late_target = browser.new_page("/")
        assert state.get_captured.wait(8), "actual backend GET captured"
        baseline = wait_for(lambda: dom_state(late_page),
            lambda value: value.get("viewState") == "ready" and value.get("lifetime") == "2" and value.get("wire") == "998",
            "real two-command late-GET baseline")
        assert state.gate_stream_after_baseline is None
        state.gate_stream_after_baseline = state.stream_connections
        assert baseline["lifetime"] == "2" and baseline["wire"] == "998"
        assert state.get_record["body"]["game"] == after_retry_game and state.get_record["delivered"] is False
        state.get_release.set()
        failed_get = wait_for(lambda: late_page.evaluate("document.getElementById('connection-status').textContent"),
            lambda value: "waiting for a live server baseline" in value, "visible delayed malformed GET", timeout=8)
        assert state.real_stream_held.wait(8), "real subsequent SSE frame held before recovery"
        failed_dom = dom_state(late_page)
        assert failed_dom["lifetime"] == "2" and failed_dom["wire"] == "998" and failed_dom["viewState"] == "ready", failed_dom
        before_revision = int(failed_dom["revision"])
        state.real_stream_gate.set()
        recovered = wait_for(lambda: dom_state(late_page),
            lambda value: value.get("lifetime") == "2" and value.get("wire") == "998" and
                int(value.get("revision", -1)) >= before_revision + 3,
            "three real later SSE revisions", timeout=12)
        connection = late_page.evaluate("document.getElementById('connection-status').textContent")
        assert connection == "Newest accepted server View displayed.", connection
        assert api.checked_json(client.get()[1])["game"] == after_retry_game
        result["lateMalformedGet"] = {"upstreamCaptured": state.get_record["body"]["game"],
            "baseline": baseline, "failureText": failed_get, "heldRealFrame": True,
            "failedDom": failed_dom, "recoveredDom": recovered, "recoveredText": connection,
            "realRevisionBeforeRecovery": before_revision, "realRevisionAfterRecovery": int(recovered["revision"])}
    return {**result, "browser": version, "chromeExit": case["chromeExit"], "backendExit": case["backendExit"]}


def run_r2_connection_lifecycle(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """Real native EventSource with explicit complete-View fixture wire input."""
    with isolated_r2_browser(binary, executable, version, "native-r2-connection") as case:
        state: ProxyState = case["state"]
        browser: Browser = case["browser"]
        template = api.checked_json(case["client"].get()[1])
        run_id = "r2-native-eventsource-lifecycle"
        good1 = fixture_view(template, run_id, 1, {})
        bad2 = fixture_view(template, run_id, 2, {"funds": "1.0"})
        good2 = fixture_view(template, run_id, 2, {
            "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22", "wire": "978",
        })
        bad3 = fixture_view(template, run_id, 3, {"funds": "1.0"})
        lower1 = fixture_view(template, run_id, 1, {})
        equal2 = fixture_view(template, run_id, 2, {
            "lifetime_clips": "999", "unsold_clips": "999", "unused_clips": "999", "wire": "1",
        })
        good3 = fixture_view(template, run_id, 3, {
            "lifetime_clips": "23", "unsold_clips": "23", "unused_clips": "23", "wire": "977",
        })
        pure_views = [fixture_view(template, run_id, revision, {
            "lifetime_clips": "23", "unsold_clips": "23", "unused_clips": "23", "wire": "977",
        }) for revision in range(4, 54)]
        state.fixture_frames = [good1, bad2, good2, bad3, lower1, equal2, good3, *pure_views]
        state.fixture_sent = [threading.Event() for _ in state.fixture_frames]
        state.fixture_release = [threading.Event() for _ in state.fixture_frames]
        page = browser.new_page("/")[0]
        assert state.fixture_sent[0].wait(8), "real EventSource sent first complete fixture"
        baseline = wait_for(lambda: dom_state(page),
            lambda value: value.get("revision") == "1" and value.get("viewState") == "ready", "good revision 1")
        state.fixture_release[0].set()
        assert state.fixture_sent[1].wait(8)
        invalid2 = wait_for(lambda: page.evaluate("document.getElementById('connection-status').textContent"),
            lambda value: "invalid server View" in value, "invalid same-run revision 2")
        assert dom_state(page) == baseline, dom_state(page)
        state.fixture_release[1].set()
        assert state.fixture_sent[2].wait(8)
        recovered = wait_for(lambda: dom_state(page),
            lambda value: value.get("revision") == "2" and value.get("lifetime") == "22" and value.get("wire") == "978",
            "valid same-run revision 2 after invalid frame")
        recovered_text = page.evaluate("document.getElementById('connection-status').textContent")
        stream_held = not state.fixture_release[2].is_set() and state.fixture_connections == 1
        assert recovered_text == "Newest accepted server View displayed.", recovered_text
        assert stream_held is True, "observe DOM before releasing/closing the physical fixture stream"
        page.evaluate("""(() => {
          window.r2CommandMutations = 0;
          window.r2ConnectionHistory = [];
          new MutationObserver(records => { window.r2CommandMutations += records.length; })
            .observe(document.getElementById('command-status'), {childList: true, characterData: true, subtree: true});
          new MutationObserver(() => window.r2ConnectionHistory.push(document.getElementById('connection-status').textContent))
            .observe(document.getElementById('connection-status'), {childList: true, characterData: true, subtree: true});
        })()""")
        result: dict[str, Any] = {"transport": "real native EventSource over CDP-attached Chrome",
            "authority": "explicit typed complete-View fixtures from a genuine server template, not production commands",
            "goodInvalidGood": {"before": baseline, "invalidText": invalid2,
            "recoveredDom": recovered, "recoveredText": recovered_text, "streamHeld": stream_held}}

        # A higher bad View, then stale GET/lower/equal Views, must retain its diagnostic.
        state.fixture_release[2].set()
        assert state.fixture_sent[3].wait(8)
        bad3_text = wait_for(lambda: page.evaluate("document.getElementById('connection-status').textContent"),
            lambda value: "invalid server View" in value, "bad higher View diagnostic")
        state.fixture_get_gate.set()
        assert state.fixture_get_delivered.wait(8), "delayed valid GET really delivered"
        settle_dom(page)
        assert page.evaluate("document.getElementById('connection-status').textContent") == bad3_text
        stale_get_retained = dom_state(page)
        assert stale_get_retained["revision"] == "2" and stale_get_retained["lifetime"] == "22"
        inert = []
        for index in (4, 5):
            state.fixture_release[index - 1].set()
            assert state.fixture_sent[index].wait(8)
            settle_dom(page)
            snapshot = dom_state(page)
            assert snapshot["revision"] == "2" and snapshot["lifetime"] == "22" and snapshot["wire"] == "978", snapshot
            assert page.evaluate("document.getElementById('connection-status').textContent") == bad3_text
            inert.append({"wireRevision": state.fixture_frames[index]["revision"], "dom": snapshot})
        result["diagnosticsRetained"] = {"errorText": bad3_text, "staleGetDom": stale_get_retained,
                                          "ignoredLowerAndEqual": inert}

        state.fixture_release[5].set()
        assert state.fixture_sent[6].wait(8)
        recovered3 = wait_for(lambda: dom_state(page),
            lambda value: value.get("revision") == "3" and value.get("lifetime") == "23" and value.get("wire") == "977",
            "valid higher recovery after ignored lower/equal")
        assert page.evaluate("document.getElementById('connection-status').textContent") == "Newest accepted server View displayed."
        state.fixture_release[6].set()
        for index, frame in enumerate(pure_views, start=7):
            assert state.fixture_sent[index].wait(8), f"bounded fixture frame {index}"
            wait_dom(page, "document.documentElement.dataset.revision", str(frame["revision"]), "pure View-only tick")
            state.fixture_release[index].set()
        final_page = page.evaluate("""({commandMutations: window.r2CommandMutations,
          connectionHistory: window.r2ConnectionHistory, revision: document.documentElement.dataset.revision})""")
        assert final_page["commandMutations"] == 0, final_page
        assert final_page["connectionHistory"] == [
            "An invalid server View was ignored; the last valid View is retained.",
            "Newest accepted server View displayed.",
        ], final_page
        assert final_page["revision"] == "53"
        result["deduplication"] = {"validPureViewFrames": 50, **final_page, "recoveredDom": recovered3}
        result["completeFixtureWireInputs"] = len(state.fixture_frames)
        state.fixture_close.set()
    return {**result, "browser": version, "chromeExit": case["chromeExit"], "backendExit": case["backendExit"]}


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
    startup_result = run_startup_feedback_and_cleanup(binary, executable, version)
    print(f"native UI: first-View feedback and constructor-failure cleanup passed: {startup_result}")
    response_result = run_r2_response_and_get(binary, executable, version)
    print("NATIVE_R2_RESPONSE_EVIDENCE=" + json.dumps(response_result, separators=(",", ":")))
    lifecycle_result = run_r2_connection_lifecycle(binary, executable, version)
    print("NATIVE_R2_LIFECYCLE_EVIDENCE=" + json.dumps(lifecycle_result, separators=(",", ":")))
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
                "startup": startup_result, "main": main_result,
                "numericOrdering": numeric_result, "recovery": recovery_result,
                "durationSeconds": round(time.perf_counter() - started, 3),
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
