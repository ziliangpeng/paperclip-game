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
import re
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
        self._frame_context: dict[str, Any] | None = None
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
            receive_size = min(64 * 1024, max(4096, size - len(self.buffer)))
            try:
                chunk = self.socket.recv(receive_size)
            except TimeoutError as error:
                if self._frame_context is not None:
                    note = {"component": "WebSocket._exact", **self._frame_context,
                            "requestedExactSize": size, "requestedReceiveChunkSize": receive_size,
                            "bufferedByteArrayLength": len(self.buffer)}
                    if self._frame_context["phase"] == "payload":
                        note["pendingPayloadPrefixHex"] = bytes(self.buffer[:64]).hex()
                    error.add_note("CDP timeout context: " +
                                   json.dumps(note, sort_keys=True, separators=(",", ":")))
                raise
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
            # A new header cannot inherit metadata from an earlier frame.
            context: dict[str, Any] = {"phase": "header", "frameFin": None,
                                       "frameOpcode": None, "declaredPayloadLength": None,
                                       "incompleteFrameIdentity": "unknown"}
            self._frame_context = context
            first, second = self._exact(2)
            fin, opcode = bool(first & 0x80), first & 0x0F
            assert not second & 0x80, "server CDP frames must not be masked"
            context["frameFin"], context["frameOpcode"] = fin, opcode
            size = second & 0x7F
            if size == 126:
                context["phase"] = "extended-length"
                size = struct.unpack("!H", self._exact(2))[0]
            elif size == 127:
                context["phase"] = "extended-length"
                size = struct.unpack("!Q", self._exact(8))[0]
            assert size <= 8 * 1024 * 1024, "bounded CDP message"
            context["declaredPayloadLength"] = size
            context["phase"] = "payload"
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
        self.page_endpoint = url
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
            try:
                message = self.websocket.receive(remaining)
            except TimeoutError as error:
                observed = time.monotonic()
                note = {"component": "Cdp.call", "outgoingMethod": method,
                        "outgoingCommandId": command_id, "providedTimeoutSeconds": timeout,
                        "receiveBudgetProvidedSeconds": remaining,
                        "deadlineMonotonicSeconds": deadline,
                        "deadlineReached": observed >= deadline,
                        "callElapsedSeconds": round(observed - (deadline - timeout), 6),
                        "remainingDeadlineBudgetSeconds": round(deadline - observed, 6),
                        "pageEndpoint": self.page_endpoint,
                        "unfinishedResponseOrEventIdentity": "unknown"}
                error.add_note("CDP timeout context: " +
                               json.dumps(note, sort_keys=True, separators=(",", ":")))
                raise
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
        wait_for(lambda: page.evaluate("""({
            url: document.URL,
            rootPresent: document.documentElement !== null,
            readyState: document.readyState
        })"""), lambda value: value["url"] == self.origin + path
            and value["rootPresent"] and value["readyState"] != "loading",
            "real target DOM initialized before returning page")
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
        self.fixture_frames: list[dict[str, Any] | tuple[str, int, bytes]] | None = None
        self.fixture_connections = 0
        self.fixture_sent: list[threading.Event] = []
        self.fixture_release: list[threading.Event] = []
        self.fixture_close = threading.Event()
        self.fixture_get_gate = threading.Event()
        self.fixture_get_delivered = threading.Event()
        self.fixture_get_body: bytes | None = None
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
                    self.finite(200, state.fixture_get_body if state.fixture_get_body is not None
                    else json_bytes(first), "application/json")
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
                    assert len(state.command_records) <= 12000
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
                record["responseBodyHex"] = response_body.hex()
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
                if isinstance(frame, tuple):
                    run_id, event_revision, data = frame
                else:
                    run_id, event_revision = frame["run_id"], frame["revision"]
                    data = json_bytes(frame)
                event = (f"id: {run_id}:{event_revision}\n"
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
      headlineText: document.getElementById('lifetime-clips').textContent,
      headlineTooltip: document.getElementById('lifetime-clips').title,
      unsold: document.getElementById('unsold-clips').dataset.canonical,
      unused: document.getElementById('unused-clips').dataset.canonical,
      funds: document.getElementById('funds').dataset.canonical,
      wire: document.getElementById('wire').dataset.canonical,
      spool: document.getElementById('wire-spool-length').dataset.canonical,
      wireQuote: document.getElementById('wire-quote').dataset.canonical,
      price: document.getElementById('price-per-clip').dataset.canonical,
      marketingLevel: document.getElementById('marketing-level').dataset.canonical,
      demand: document.getElementById('demand').dataset.canonical,
      demandValue: document.getElementById('demand').value,
      demandVisible: document.getElementById('demand').textContent,
      demandTooltip: document.getElementById('demand').title,
      demandRow: document.getElementById('demand').closest('tr').textContent,
      marketingCost: document.getElementById('marketing-cost').dataset.canonical,
      clipsSold: document.getElementById('clips-sold').dataset.canonical,
      income: document.getElementById('income').dataset.canonical,
      lastSaleRevenue: document.getElementById('last-sale-revenue').dataset.canonical,
      trust: document.getElementById('trust').dataset.canonical,
      processors: document.getElementById('processors').dataset.canonical,
      memory: document.getElementById('memory').dataset.canonical,
      computingHidden: document.getElementById('computational-resources').hidden,
      autoClippersHidden: document.getElementById('auto-clippers-panel').hidden,
      autoClippers: document.getElementById('auto-clippers').dataset.canonical,
      autoClipperCost: document.getElementById('auto-clipper-cost').dataset.canonical,
      autoClipperCostText: document.getElementById('auto-clipper-cost').textContent,
      autoClipperRate: document.getElementById('auto-clipper-rate').dataset.canonical,
      autoClipperRateText: document.getElementById('auto-clipper-rate').textContent,
      consoleMessages: [...document.querySelectorAll('#console-messages > li')].map(line => line.textContent),
      status: document.getElementById('command-status').textContent,
      button: document.getElementById('make-paperclip').textContent,
      controls: [...document.querySelectorAll('button')].map(button => ({id:button.id, disabled:button.disabled, ariaDisabled:button.getAttribute('aria-disabled')})),
      disabled: document.getElementById('make-paperclip').disabled,
      ariaDisabled: document.getElementById('make-paperclip').getAttribute('aria-disabled'),
      focus: document.activeElement && document.activeElement.id
    })""")


def stock_ledger_visible(value: dict[str, Any], clips: int, wire: str) -> bool:
    if value.get("viewState") != "ready":
        return False
    sold = int(value["clipsSold"])
    remaining = clips - sold
    # In this scope sales move Unsold into Sold. Unused remains equal to
    # Lifetime; there is no AutoClipper purchase or other consumer of it.
    return (0 <= sold <= clips and value["lifetime"] == value["unused"] == str(clips) and
            value["unsold"] == str(remaining) and value["wire"] == wire)


def wait_dom(page: Cdp, expression: str, expected: Any, description: str, timeout: float = 10) -> Any:
    return wait_for(lambda: page.evaluate(expression), lambda value: value == expected,
                    description, timeout)


def exact_command(record: dict[str, Any], kind: str = "make_paperclip") -> dict[str, Any]:
    body = record["json"]
    assert record["method"] == "POST" and record["path"] == "/api/game/commands"
    assert record["contentType"] == "application/json"
    assert set(body) == {"command_id", "type", "arguments"}
    assert body["type"] == kind and body["arguments"] == {}
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


def assert_only_wire_quote_can_advance(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Allow market time and fully accounted sales, not fixture resource writes."""
    from decimal import Decimal

    api.assert_production({"game": actual}, actual["wire"], actual["lifetime_clips"], actual)
    unchanged = dict(expected)
    unchanged["wire_quote"] = actual["wire_quote"]
    sold_delta = Decimal(actual["clips_sold"]) - Decimal(expected["clips_sold"])
    assert sold_delta >= 0, (actual, expected)
    if sold_delta:
        # These checkpoints precede every Price/Marketing action. Production is
        # frozen, so only integer inventory and the server's two-clip batches at
        # .25 are admissible. Partial batches can occur only when stock empties.
        assert expected["price_per_clip"] == "0.25" and expected["demand"] == "3.2"
        assert sold_delta == Decimal(expected["unsold_clips"]) - Decimal(actual["unsold_clips"])
        assert sold_delta == sold_delta.to_integral_value()
        assert Decimal("0") <= Decimal(actual["unsold_clips"]) <= Decimal(expected["unsold_clips"])
        revenue_delta = Decimal(actual["income"]) - Decimal(expected["income"])
        funds_delta = Decimal(actual["funds"]) - Decimal(expected["funds"])
        assert revenue_delta == funds_delta == sold_delta * Decimal("0.25")
        if Decimal(actual["unsold_clips"]) == 0:
            last_batch = Decimal(sold_delta % 2 or 2)
        else:
            assert sold_delta % 2 == 0, (actual, expected)
            last_batch = Decimal("2")
        assert Decimal(actual["last_sale_revenue"]) == last_batch * Decimal("0.25")
        for field in ("unsold_clips", "clips_sold", "funds", "income", "last_sale_revenue"):
            unchanged[field] = actual[field]
    assert actual == unchanged, (actual, unchanged)


def checkpoint_sale_controls(template: dict[str, Any]) -> dict[str, Any]:
    """Deterministic controls on private dictionaries; never mutate real UI/server state."""
    from copy import deepcopy

    before = deepcopy(template)
    before.update({"lifetime_clips": "2", "unsold_clips": "2", "unused_clips": "2",
                   "wire": "998", "funds": "0", "clips_sold": "0", "income": "0",
                   "last_sale_revenue": "0"})
    no_sale = deepcopy(before)
    no_sale["wire_quote"] = "21"
    assert_only_wire_quote_can_advance(no_sale, before)
    sale = deepcopy(no_sale)
    sale.update({"unsold_clips": "0", "clips_sold": "2",
                 "funds": "0.5", "income": "0.5", "last_sale_revenue": "0.5"})
    assert_only_wire_quote_can_advance(sale, before)

    def rejected(changed: dict[str, Any]) -> bool:
        try:
            assert_only_wire_quote_can_advance(changed, before)
        except AssertionError:
            return True
        raise AssertionError("checkpoint guard accepted a deliberately wrong mutation")

    wrong_money = deepcopy(sale)
    wrong_money["funds"] = "0.51"
    wrong_unrelated = deepcopy(sale)
    wrong_unrelated["auto_clippers"] = "1"
    return {"noSaleAccepted": True, "genuineTwoClipSaleAccepted": True,
            "wrongFundsRejected": rejected(wrong_money),
            "wrongUnrelatedStateRejected": rejected(wrong_unrelated)}



def raw_counter_frame(view: dict[str, Any], field: str, token: str) -> tuple[str, int, bytes]:
    """Alter one actual JSON number token, preserving the whole wire View/event ID."""
    container = view["clock"] if field == "update_count" else view
    assert field in {"revision", "schema_version", "update_count"}
    assert type(container[field]) is int
    old_number = f'"{field}":{container[field]}'.encode()
    new_number = f'"{field}":{token}'.encode()
    assert re.fullmatch(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+|[eE][+-]?[0-9]+)?", token.encode())
    data = json_bytes(view)
    assert data.count(old_number) == 1
    data = data.replace(old_number, new_number)
    decoded = json.loads(data)
    changed = decoded["clock"]["update_count"] if field == "update_count" else decoded[field]
    assert isinstance(changed, (int, float)) and not isinstance(changed, bool)
    return view["run_id"], view["revision"], data


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
      const {makePaperclipCommand, postMakePaperclip, createCommand, postGameCommand} = await import('/static/commands.js');
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
      const closedKinds = ["buy_wire", "lower_price", "raise_price", "buy_marketing", "buy_auto_clipper"];
      let closedRejected = 0;
      for (const kind of closedKinds) {
        const command = createCommand(kind, 'browser-business-' + kind);
        if (Object.keys(command).sort().join() !== 'arguments,command_id,type') throw new Error('business envelope field closure');
        for (const field of ["funds", "cost", "count"]) {
          let rejected = false;
          try {
            await postGameCommand({...command, arguments: {[field]: "1"}}, {fetch: () => { fetches += 1; throw new Error('must not fetch'); }});
          } catch (error) {
            rejected = error instanceof TypeError && error.message === 'only a closed, empty-argument game command is accepted';
          }
          if (!rejected) throw new Error('business argument rejection: ' + kind + '/' + field);
          closedRejected += 1;
        }
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
      return {badEnvelopes: bad.length, closedRejected, invalidIds: 3, fetches, oversizeRejected: true,
        wrongContentTypeRejected: true, invalidAppliedShapeRejected: true,
        timeoutBounded: true, timeoutRetainsRetry: true};
    })()""")
    assert result == {"badEnvelopes": 8, "closedRejected": 15, "invalidIds": 3, "fetches": 0,
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
    assert structure["fakeControls"] == 0
    assert structure["buttons"] == ["Make Paperclip", "Lower Price", "Raise Price", "Buy Marketing", "Buy Wire", "Buy AutoClipper"]
    assert structure["amountsOutsideLive"] and structure["statusLive"] == "polite" and structure["statusAtomic"] == "true"
    assert structure["labels"] and abs(structure["contrast"] - 21) < 1e-9 and abs(structure["buttonContrast"] - 21) < 1e-9, structure
    assert structure["computingHidden"] and structure["autoHidden"]
    for forbidden in ("Feed", "Teach", "Clad", "Debug", "Reset", "New world"):
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
    for _ in range(4):
        page.key("keyDown", "Tab", "Tab", 9)
        page.key("keyUp", "Tab", "Tab", 9)
        focused.append(page.evaluate("document.activeElement.id"))
    assert focused[4:] == ["make-paperclip", "lower-price", "raise-price", "buy-marketing", "buy-wire"], focused
    page.evaluate("document.getElementById('make-paperclip').focus()")


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
            api.assert_production(current, "998", "2", current["game"])
            remaining_wire = int(current["game"]["wire"])
            for index in range(remaining_wire):
                status, response_body = public.make(f"m1-startup-stock-{index}")
                assert status == 200, (index, status, response_body)
            exhausted = api.checked_json(public.get()[1])
            api.assert_production(exhausted, "0", "1000", exhausted["game"])
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


def run_business_flow(browser: Browser, state: ProxyState, agent: api.Client,
                      page1: Cdp, page2: Cdp) -> dict[str, Any]:
    """Genuine native controls, production, stochastic sales and procurement."""
    from decimal import Decimal, localcontext
    import time as clock

    started = clock.monotonic()
    labels = {"make_paperclip": "Make Paperclip", "buy_wire": "Buy Wire",
              "buy_marketing": "Buy Marketing", "lower_price": "Lower Price",
              "raise_price": "Raise Price"}
    rejection_text = {
        "insufficient_funds": "not enough Funds at the current server quote/cost",
        "price_at_minimum": "price is already at its minimum",
    }

    def current() -> dict[str, Any]:
        view = api.checked_json(agent.get()[1])
        api.assert_production(view, view["game"]["wire"],
                              view["game"]["lifetime_clips"], view["game"])
        return view

    def wait_feedback(page: Cdp, kind: str, record: dict[str, Any]) -> None:
        body = record["response_body"]
        revision = body["revision"]
        assert type(revision) is int
        if body["status"] == "applied":
            if kind == "make_paperclip":
                message = (f"Server applied the command at revision {revision}. "
                           "Displayed resources come from the newest full server View.")
            else:
                message = (f"Server applied {labels[kind]} at revision {revision}. "
                           "Resources come from the newest complete server View.")
        else:
            assert body["status"] == "rule_rejected"
            message = f"Server rejected {labels[kind]}: {rejection_text[body['reason']]}. This request made no resource change."
        wait_for(lambda: dom_state(page), lambda value:
                 value["status"] == message and int(value["revision"]) >= revision,
                 f"native {kind} feedback and server View")

    def press(kind: str, page: Cdp = page1, expected_status: int = 200,
              allow_drop: bool = False) -> dict[str, Any]:
        count = len(state.command_records)
        page.call("Page.bringToFront")
        page.evaluate(f"document.getElementById({kind.replace('_', '-')!r}).focus()")
        page.press("Enter")
        record = wait_commands(state, count + 1)[-1]
        exact_command(record, kind)
        wait_for(lambda: record.get("response_body"), lambda value: isinstance(value, dict),
                 f"actual {kind} response")
        assert record["response_status"] == expected_status and record["forwarded"] == 1, record
        assert set(record["response_body"]) == ({"status", "revision", "reason"}
            if expected_status == 422 else {"status", "revision"})
        if expected_status == 200:
            assert record["response_body"]["status"] == "applied"
        else:
            assert record["response_body"]["status"] == "rule_rejected"
        if record["dropped"]:
            assert allow_drop and expected_status == 200, record
        else:
            wait_feedback(page, kind, record)
        return record

    def assert_both_pages(predicate: Callable[[dict[str, Any]], bool], description: str) -> None:
        for page in (page1, page2):
            wait_for(lambda page=page: dom_state(page), predicate, description)

    demand_presentations = []

    def assert_public_demand(raw: str, price: str, level: str, label: str) -> dict[str, str]:
        # Independently scale the exact canonical string; no browser rounding or
        # dataset-only assertion substitutes for reading the visible unit/value.
        with localcontext() as context:
            context.prec = len(raw) + 20
            # Preserve the exact digits while applying canonical trailing-zero formatting.
            scaled = format((Decimal(raw) * 10).normalize(), "f")
        integer, dot, fraction = scaled.partition(".")
        visible = f"{int(integer):,}{dot}{fraction}%"
        assert_both_pages(lambda value: value["price"] == price and
                          value["marketingLevel"] == level and
                          value["demand"] == raw and value["demandValue"] == raw and
                          value["demandVisible"] == visible and
                          value["demandTooltip"] == visible and
                          "".join(value["demandRow"].split()) == f"PublicDemand{visible}",
                          f"actual {label} raw and visible Public Demand on both pages")
        record = {"case": label, "rawDemand": raw, "price": price,
                  "marketingLevel": level, "visibleDemand": visible}
        demand_presentations.append(record)
        return record

    def replay_rejection(record: dict[str, Any]) -> None:
        count = len(state.command_records)
        connection = http.client.HTTPConnection("127.0.0.1", browser.origin_port, timeout=8)
        try:
            connection.request("POST", "/api/game/commands", body=record["raw"],
                               headers={"Content-Type": record["contentType"]})
            response = connection.getresponse()
            raw = response.read(16 * 1024 + 1)
            assert len(raw) <= 16 * 1024 and response.status == 422
        finally:
            connection.close()
        duplicate = wait_commands(state, count + 1)[-1]
        assert duplicate["raw"] == record["raw"] and duplicate["json"] == record["json"]
        assert duplicate["forwarded"] == record["forwarded"] == 1
        assert duplicate["response_status"] == record["response_status"] == 422
        assert api.checked_json(raw) == duplicate["response_body"] == record["response_body"]
        assert raw.hex() == duplicate["responseBodyHex"] == record["responseBodyHex"]

    # No Funds are preloaded. At empty stock there can be no sales revenue, so
    # both purchases are genuine server-side insufficient_funds rejections.
    assert current()["game"]["lifetime_clips"] == "0"
    assert_both_pages(lambda value: value.get("viewState") == "ready" and
                      value["lifetime"] == "0" and value["wire"] == "1000",
                      "loaded genuine business command forms before first activation")
    # Only read all Demand DOM fields after the established readiness gate:
    # an unset dataset canonical is deliberately absent from dom_state JSON.
    # Initial raw demand 3.2 is a different contract from its visible 32%.
    assert_public_demand("3.2", "0.25", "1", "initial")
    failed_wire = press("buy_wire", page1, 422)
    failed_marketing = press("buy_marketing", page2, 422)
    for record in (failed_wire, failed_marketing):
        assert record["response_body"]["reason"] == "insufficient_funds"
        replay_rejection(record)

    # A held lower form cannot duplicate its ID; the other page can independently
    # raise the price. The eventual serialized lower+raise restores .25 exactly.
    initial = current()["game"]
    state.hold_commands = True
    state.command_release.clear()
    count = len(state.command_records)
    page1.evaluate("document.getElementById('lower-price').focus()")
    page1.press("Enter")
    first_held = wait_commands(state, count + 1)[-1]
    exact_command(first_held, "lower_price")
    wait_for(lambda: dom_state(page1), lambda value:
             next(button for button in value["controls"]
                  if button["id"] == "lower-price")["ariaDisabled"] == "true",
             "independent lower-price pending")
    page1.press("Enter", repeat_too=True)
    settle_dom(page1)
    assert len(state.command_records) == count + 1
    page2.evaluate("document.getElementById('raise-price').focus()")
    page2.press("Enter")
    second_held = wait_commands(state, count + 2)[-1]
    exact_command(second_held, "raise_price")
    assert first_held["json"]["command_id"] != second_held["json"]["command_id"]
    assert next(button for button in dom_state(page2)["controls"]
                if button["id"] == "buy-wire")["ariaDisabled"] == "false"
    state.hold_commands = False
    state.command_release.set()
    for record, page, kind in ((first_held, page1, "lower_price"),
                               (second_held, page2, "raise_price")):
        wait_for(lambda record=record: record.get("response_body"),
                 lambda value: isinstance(value, dict), "real released business response")
        assert record["response_status"] == 200 and record["forwarded"] == 1
        exact_command(record, kind)
        wait_feedback(page, kind, record)
    expected_revision = max(first_held["response_body"]["revision"],
                            second_held["response_body"]["revision"])
    assert_both_pages(lambda value: value["price"] == "0.25" and
                      value["demand"] == initial["demand"] and
                      int(value["revision"]) >= expected_revision,
                      "serialized price cancellation on both pages")

    # Isolate visible price transitions after preserving the held/cancel checks.
    # These are two real zero-argument commands, not local price/demand fixtures.
    lower_records = [press("lower_price", page1)]
    lower_price_state = current()["game"]
    assert lower_price_state["price_per_clip"] == "0.24"
    assert_public_demand(lower_price_state["demand"], "0.24", "1", "lowered price")
    raise_records = [press("raise_price", page2)]
    assert_public_demand("3.2", "0.25", "1", "raised price")

    # Two actual Make commands precede exactly 998 additional public API commands.
    press("make_paperclip", page1)
    press("make_paperclip", page2)
    before_production = current()["game"]
    assert before_production["wire"] == "998"
    production_uids = 0

    def produce(count: int) -> None:
        nonlocal production_uids
        assert 1 <= count <= 1000 and production_uids + count <= 9000
        for _ in range(count):
            uid = f"native-business-production-{production_uids}"
            status, body = agent.make(uid)
            assert status == 200 and api.checked_json(body)["status"] == "applied"
            production_uids += 1

    produce(int(before_production["wire"]))
    assert production_uids == 998
    produced = wait_for(current, lambda view: view["game"]["lifetime_clips"] == "1000",
                        "the initial 1000 actual player-made clips", timeout=20)
    assert produced["game"]["wire"] == "0"
    assert_both_pages(lambda value: stock_ledger_visible(value, 1000, "0"),
                      "both pages reflect actual production and any real sales")
    print("native commerce: 2 native + 998 API production commands, Wire exhausted", flush=True)

    lower_records.extend(press("lower_price") for _ in range(21))
    assert_both_pages(lambda value: value["price"] == "0.04" and value["marketingCost"] == "100",
                      "21 genuine lower-price commands on both pages")
    for _ in range(3):
        lower_records.append(press("lower_price"))
    minimum = press("lower_price", expected_status=422)
    assert minimum["response_body"]["reason"] == "price_at_minimum"
    assert_both_pages(lambda value: value["price"] == "0.01" and value["demand"] == "80",
                      "exact minimum price and Demand on both pages")
    assert_public_demand("80", "0.01", "1", "minimum price")
    raise_records.extend(press("raise_price") for _ in range(3))
    assert_both_pages(lambda value: value["price"] == "0.04",
                      "native raise-price controls return to the working price")
    assert_public_demand("20", "0.04", "1", "working price")

    # With zero purchases Wire base never grows: initial 20 plus +/-6 and ceiling
    # gives a first-price upper budget of 26. Every dollar comes from real sales.
    funded = wait_for(current, lambda view:
                       Decimal(view["game"]["funds"]) >= Decimal("26") and
                       Decimal(view["game"]["income"]) > 0 and
                       int(view["game"]["clips_sold"]) > 0,
                       "genuine stochastic sales fund the first Wire quote", timeout=120)
    print(f"native commerce: real sales Funds={funded['game']['funds']} sold={funded['game']['clips_sold']}", flush=True)

    wire_purchases = 0
    wire_charges: list[str] = []
    same_uuid_wire_retries = 0

    def buy_wire() -> None:
        nonlocal wire_purchases, same_uuid_wire_retries
        before = current()["game"]
        if wire_purchases == 0:
            state.drop_next_response = True
        receipt = press("buy_wire", page1, allow_drop=wire_purchases == 0)
        if wire_purchases == 0:
            # The first accepted response is really dropped after the server applied
            # it. The same native form then repeats the exact original opaque ID/bytes.
            assert receipt["dropped"] and receipt["forwarded"] == 1
            wait_for(lambda: page1.evaluate("document.getElementById('buy-wire').textContent"),
                     lambda value: value == "Retry Buy Wire", "real native Wire retry feedback")
            wait_for(lambda: page1.evaluate("document.getElementById('command-status').textContent"),
                     lambda value: "unknown network outcome" in value and "no local credit" in value,
                     "unknown Wire outcome does not grant local credit")
            duplicate = press("buy_wire", page1)
            assert duplicate["raw"] == receipt["raw"]
            assert duplicate["responseBodyHex"] == receipt["responseBodyHex"]
            assert duplicate["response_body"] == receipt["response_body"]
            same_uuid_wire_retries += 1
            receipt = duplicate
        after = wait_for(current, lambda view:
                         int(view["game"]["wire"]) == int(before["wire"]) + 1000,
                         "exactly one purchased spool, never one per retry")
        sale_delta = Decimal(after["game"]["income"]) - Decimal(before["income"])
        charge = Decimal(before["funds"]) + sale_delta - Decimal(after["game"]["funds"])
        assert charge > 0 and charge == int(charge)
        assert charge <= Decimal("26" if wire_purchases == 0 else "27")
        wire_purchases += 1
        wire_charges.append(str(charge))
        assert after["game"]["lifetime_clips"] == str(1000 + production_uids - 998)
        print(f"native commerce: spool={wire_purchases} charge={charge} "
              f"server quote before={before['wire_quote']} after={after['game']['wire_quote']}", flush=True)

    buy_wire()
    assert_both_pages(lambda value: stock_ledger_visible(value, 1000, "1000"),
                      "first real spool reaches two independently sourced SSE pages")

    # The bounded purchasing policy retains a $13 reserve per new spool; this is
    # not a command argument. The server alone chooses every executable quote/cost.
    rounds = 0
    while Decimal(current()["game"]["funds"]) < Decimal("100"):
        rounds += 1
        assert rounds <= 20 and wire_purchases <= 8, "bounded native production/procurement loop"
        snapshot = current()["game"]
        assert Decimal(snapshot["price_per_clip"]) == Decimal("0.04")
        available_wire = int(snapshot["wire"])
        if available_wire:
            assert available_wire <= 1000
            produce(available_wire)
            expected_lifetime = 1000 + production_uids - 998
            wait_for(current, lambda view: view["game"]["lifetime_clips"] == str(expected_lifetime),
                     "complete public production batch", timeout=20)
            print(f"native commerce: {production_uids} additional API makes; total clips={expected_lifetime}", flush=True)
            continue
        potential = Decimal(snapshot["funds"]) + Decimal(snapshot["unsold_clips"]) * Decimal("0.04")
        if potential >= Decimal("100"):
            print(f"native commerce: selling current inventory toward Marketing; Funds={snapshot['funds']} "
                  f"Unsold={snapshot['unsold_clips']} sold={snapshot['clips_sold']}", flush=True)
            wait_for(current, lambda view: Decimal(view["game"]["funds"]) >= Decimal("100"),
                     "existing real inventory can fund Marketing without another spool", timeout=180)
        else:
            latest = wait_for(current, lambda view:
                               Decimal(view["game"]["funds"]) >= Decimal("100") or
                               Decimal(view["game"]["funds"]) >= Decimal(view["game"]["wire_quote"]) + Decimal("13"),
                               "actual sales accumulate the next procurement reserve", timeout=120)
            if Decimal(latest["game"]["funds"]) < Decimal("100"):
                buy_wire()

    marketing_before = current()["game"]
    assert Decimal(marketing_before["funds"]) >= Decimal("100")
    marketing_receipt = press("buy_marketing", page2)
    marketing_after = wait_for(current, lambda view: view["game"]["marketing_level"] == "2",
                               "the first real Marketing purchase")
    sale_delta = Decimal(marketing_after["game"]["income"]) - Decimal(marketing_before["income"])
    marketing_charge = Decimal(marketing_before["funds"]) + sale_delta - Decimal(marketing_after["game"]["funds"])
    assert marketing_charge == Decimal("100")
    assert Decimal(marketing_after["game"]["demand"]) > Decimal(marketing_before["demand"])
    assert marketing_after["game"]["demand"] == "22"
    assert_public_demand("22", "0.04", "2", "Marketing level 2")
    assert_both_pages(lambda value: value["marketingLevel"] == "2" and
                      value["marketingCost"] == "200" and
                      value["demand"] == marketing_after["game"]["demand"],
                      "actual Marketing level 2, cost and Demand on both pages")

    final = current()
    assert final["game"]["wire_spool_length"] == "1000"
    assert final["game"]["lifetime_clips"] == str(1000 + production_uids - 998)
    assert int(final["game"]["wire"]) == wire_purchases * 1000 - (production_uids - 998)
    assert Decimal(final["game"]["funds"]) + Decimal("100") + sum(map(Decimal, wire_charges)) == Decimal(final["game"]["income"])
    assert Decimal(final["game"]["clips_sold"]) > 0
    assert Decimal(final["game"]["last_sale_revenue"]) > 0
    assert same_uuid_wire_retries == 1
    assert len(state.stream_baselines) >= 2 and not state.errors, state.errors[:10]
    return {
        "nativeControls": ["make_paperclip", "lower_price", "raise_price", "buy_wire", "buy_marketing"],
        "productionThroughNativeUI": 2, "additionalProductionThroughPublicAPI": production_uids,
        "finalLifetimeClips": final["game"]["lifetime_clips"],
        "independentPending": True, "rejectedOriginalUuidByteReplays": 2,
        "acceptedWireOriginalUuidBrowserRetry": True, "wirePurchases": wire_purchases,
        "wireChargesFromFundsAndIncome": wire_charges,
        "salesFundedMarketing": True, "marketingCharge": str(marketing_charge),
        # The independently held lower/raise pair each applied once. Include
        # that successful lower in the count as well as the later 24 lowers.
        "lowerApplications": len(lower_records) + 1, "raiseApplications": len(raise_records) + 1,
        "priceMinimumRejections": 1, "clipsSold": final["game"]["clips_sold"],
        "income": final["game"]["income"], "funds": final["game"]["funds"],
        "wireRemaining": final["game"]["wire"], "price": final["game"]["price_per_clip"],
        "demand": final["game"]["demand"], "marketingCost": final["game"]["marketing_cost"],
        "publicDemandPresentation": demand_presentations,
        "twoIndependentPages": True, "nativeCommandCountThroughProxy": len(state.command_records),
        "durationSeconds": round(clock.monotonic() - started, 3),
    }


def run_autoclipper_native_evidence(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """G03 public Controls only; never use a server-state write or debug fixture."""
    from decimal import Decimal
    import time as clock
    import check_persistence_process as stored

    with isolated_r2_browser(binary, executable, version, "m1-g03-autoclipper") as case:
        browser: Browser = case["browser"]
        state: ProxyState = case["state"]
        agent: api.Client = case["client"]
        database: Path = case["database"]
        # Bind this same public run to the exact canonical M1 entry. The normal
        # initial V3 row is read-only evidence, never a state injection.
        entry_stored = stored.read_snapshot(database)
        assert entry_stored["revision"] == 0 and entry_stored["sequence"] == 0
        assert all(value == 0 for value in entry_stored["clock"].values())
        assert entry_stored["pro"]["wire_base_price"] == "20"
        assert entry_stored["pro"]["wire_price_counter"] == 0
        assert entry_stored["pro"]["wire_purchase_count"] == 0
        assert entry_stored["pro"]["wire_inactivity_ticks"] == 0
        assert entry_stored["pro"]["marketing_effectiveness"] == "1"
        assert entry_stored["pro"]["demand_boost"] == "1"
        assert entry_stored["pro"]["prestige_u"] == "0"
        assert entry_stored["pro"]["auto_clipper_production_accumulator"] == "0"
        entry_game = stored.assert_stored_pro(entry_stored["pro"])
        entry_game["marketing_cost"] = "100"
        api.assert_production({"game": entry_game}, "1000", "0")

        page1, context1, target1 = browser.new_page("/")
        page2, context2, target2 = browser.new_page("/")
        assert context1 != context2
        started = clock.monotonic()
        labels = {"buy_auto_clipper": "Buy AutoClipper", "buy_wire": "Buy Wire",
                  "buy_marketing": "Buy Marketing", "lower_price": "Lower Price",
                  "raise_price": "Raise Price"}

        def current() -> dict[str, Any]:
            return api.checked_json(agent.get()[1])

        def public(kind: str, command_id: str) -> dict[str, Any]:
            status, raw = agent.post(json_bytes({
                "command_id": command_id, "type": kind, "arguments": {},
            }))
            body = api.checked_json(raw)
            assert status == 200 and body["status"] == "applied", (kind, status, body)
            return body

        def press(page: Cdp, kind: str, expected_status: int = 200) -> dict[str, Any]:
            count = len(state.command_records)
            page.call("Page.bringToFront")
            page.evaluate(f"document.getElementById({kind.replace('_', '-')!r}).focus()")
            page.press("Enter")
            record = wait_commands(state, count + 1)[-1]
            exact_command(record, kind)
            wait_for(lambda: record.get("response_body"), lambda value: isinstance(value, dict),
                     f"actual {kind} response")
            assert record["response_status"] == expected_status and record["forwarded"] == 1, record
            body = record["response_body"]
            revision = body["revision"]
            if expected_status == 200:
                message = (f"Server applied {labels[kind]} at revision {revision}. "
                           "Resources come from the newest complete server View.")
            else:
                assert body["reason"] == "insufficient_funds"
                message = (f"Server rejected {labels[kind]}: not enough Funds at the current "
                           "server quote/cost. This request made no resource change.")
            wait_for(lambda: dom_state(page), lambda value:
                     value["status"] == message and int(value["revision"]) >= revision,
                     f"native {kind} terminal feedback")
            return record

        def both(predicate: Callable[[dict[str, Any]], bool], description: str) -> None:
            for page in (page1, page2):
                def ready_and_matching(page: Cdp = page) -> bool:
                    value = dom_state(page)
                    return value.get("viewState") == "ready" and predicate(value)
                wait_for(ready_and_matching, bool, description)

        def close_page(page: Cdp, target: str) -> None:
            assert browser.browser_connection is not None
            browser.browser_connection.call("Target.closeTarget", {"targetId": target})
            browser.pages.remove(page)
            page.close()

        # Fresh legal manual play: no Wire or Marketing command is sent before reveal.
        both(lambda value: value.get("viewState") == "ready" and value["autoClippersHidden"] and
             value["autoClippers"] == "0" and value["autoClipperCost"] == "5",
             "fresh hidden AutoClippers on two pages")
        # Browser startup may allow real online Wire-quote movement. No other M1
        # entry field may move before the first legal player command.
        assert_only_wire_quote_can_advance(current()["game"], copy.deepcopy(entry_game))
        for index in range(1000):
            status, body = agent.make(f"g03-manual-{index}")
            assert status == 200 and api.checked_json(body)["status"] == "applied"
        # Legal price controls raise demand without Wire or Marketing purchases.
        # Keep the real first reveal inside its bounded stochastic window rather
        # than injecting RNG, extending the timeout, or writing Funds directly.
        for index in range(21):
            public("lower_price", f"g03-working-price-{index}")
        first_crossing = wait_for(current, lambda view:
            Decimal(view["game"]["funds"]) >= Decimal("5") and
            view["game"]["auto_clipper_revealed"] is True,
            "actual first Funds>=5 reveal through stochastic sales", timeout=45)
        assert first_crossing["game"]["wire"] == "0"
        assert first_crossing["game"]["marketing_level"] == "1"
        assert first_crossing["game"]["auto_clippers"] == "0"
        assert first_crossing["game"]["auto_clipper_cost"] == "5"
        both(lambda value: value["autoClippersHidden"] is False and
             value["autoClippers"] == "0" and value["autoClipperCost"] == "5" and
             "AutoClippers revealed: Funds reached $5." in value["consoleMessages"] and
             len(value["consoleMessages"]) == 5,
             "actual first reveal/stored initial price on both native pages")

        before = current()["game"]
        first = press(page1, "buy_auto_clipper")
        after = wait_for(current, lambda view: view["game"]["auto_clippers"] == "1",
                         "first real AutoClipper purchase")["game"]
        charge = (Decimal(before["funds"]) + Decimal(after["income"]) -
                  Decimal(before["income"]) - Decimal(after["funds"]))
        assert charge == Decimal("5") and after["auto_clipper_cost"] == "6.1"
        assert after["wire"] == "0" and after["auto_clipper_rate"] == "0"
        latched_below_five = Decimal(after["funds"]) < Decimal("5")
        both(lambda value: value["autoClippers"] == "1" and
             value["autoClipperCost"] == "6.1" and value["autoClipperCostText"] == "6.10" and
             value["consoleMessages"][-1] == "AutoClipper 1 purchased.",
             "first stored successor 6.1 and 6.10 presentation on both pages")

        # The same legal $0.04 price now replenishes Funds through real sales;
        # there is still no Funds setter or caller-selected server outcome.
        wait_for(current, lambda view: Decimal(view["game"]["funds"]) >= Decimal("6.1"),
                 "legal sales fund successor 6.1", timeout=90)
        before_second = current()["game"]
        second = press(page2, "buy_auto_clipper")
        after_second = wait_for(current, lambda view: view["game"]["auto_clippers"] == "2",
                                "distinct successor AutoClipper purchase")["game"]
        second_charge = (Decimal(before_second["funds"]) + Decimal(after_second["income"]) -
                         Decimal(before_second["income"]) - Decimal(after_second["funds"]))
        assert second_charge == Decimal("6.1")
        assert after_second["auto_clipper_cost"] == "6.21"
        both(lambda value: value["autoClippers"] == "2" and
             value["autoClipperCost"] == "6.21" and
             value["consoleMessages"][-1] == "AutoClipper 2 purchased.",
             "second stored successor on both native pages")

        # Full Views and real sales continue while the native feedback settles.
        # The second purchase may therefore become affordable before a third.
        # Reject only at a real below-current-cost point rather than assume it.
        before_rejection = current()["game"]
        assert after_second["auto_clippers"] == "2"
        assert after_second["auto_clipper_cost"] == "6.21"
        assert (Decimal(before_rejection["funds"]) <
                Decimal(before_rejection["auto_clipper_cost"])), before_rejection
        below_cost_rejection = press(page2, "buy_auto_clipper", 422)
        after_rejection = current()["game"]
        assert after_rejection["auto_clippers"] == "2"
        assert after_rejection["auto_clipper_cost"] == "6.21"
        assert after_rejection["lifetime_clips"] == before_rejection["lifetime_clips"]
        assert after_rejection["wire"] == "0"
        assert (Decimal(after_rejection["funds"]) - Decimal(before_rejection["funds"]) ==
                Decimal(after_rejection["income"]) - Decimal(before_rejection["income"]))
        assert after_rejection["console_messages"] == before_rejection["console_messages"]

        # Terminal same-ID replay through the same real proxy/server returns the
        # original receipt after the later purchase and does not create producer 3.
        connection = http.client.HTTPConnection("127.0.0.1", browser.origin_port, timeout=8)
        try:
            connection.request("POST", "/api/game/commands", body=first["raw"],
                               headers={"Content-Type": first["contentType"]})
            response = connection.getresponse()
            replay_raw = response.read(16 * 1024 + 1)
            assert response.status == first["response_status"] == 200
        finally:
            connection.close()
        replay = wait_commands(state, len(state.command_records))[-1]
        assert replay["raw"] == first["raw"] and replay_raw.hex() == first["responseBodyHex"]
        assert replay["response_body"] == first["response_body"]
        post_replay = current()["game"]
        assert post_replay["auto_clippers"] == "2" and post_replay["auto_clipper_cost"] == "6.21"

        # Issue17 integrated exit: real native Price commands also occur after
        # reveal. Restore the proven working price before subsequent procurement.
        post_reveal_lower = press(page1, "lower_price")
        post_reveal_lower_view = wait_for(current, lambda view:
            view["game"]["price_per_clip"] == "0.03", "post-reveal native lower Price")
        assert post_reveal_lower_view["game"]["auto_clipper_cost"] == "6.21"
        both(lambda value: value["price"] == "0.03" and
             value["demand"] == post_reveal_lower_view["game"]["demand"] and
             value["autoClippers"] == "2" and value["autoClipperCost"] == "6.21",
             "post-reveal lower Price and exact Demand on both server-fed pages")
        post_reveal_raise = press(page2, "raise_price")
        post_reveal_raise_view = wait_for(current, lambda view:
            view["game"]["price_per_clip"] == "0.04", "post-reveal native raise Price")
        assert post_reveal_raise_view["game"]["demand"] == "20"
        both(lambda value: value["price"] == "0.04" and value["demand"] == "20" and
             value["autoClippers"] == "2" and value["autoClipperCost"] == "6.21",
             "working Price restored through the other anonymous page")

        first_wire_before = wait_for(current, lambda view:
            Decimal(view["game"]["funds"]) >= Decimal("26"),
            "legal sales fund the first Wire spool after reveal", timeout=120)["game"]
        first_wire = press(page1, "buy_wire")
        first_wire_after = wait_for(current, lambda view: Decimal(view["game"]["wire"]) >= Decimal("900"),
                                    "first legal post-reveal spool")["game"]
        wire_charge = (Decimal(first_wire_before["funds"]) + Decimal(first_wire_after["income"]) -
                       Decimal(first_wire_before["income"]) - Decimal(first_wire_after["funds"]))
        assert Decimal("0") < wire_charge <= Decimal("26")
        assert first_wire_after["auto_clipper_cost"] == "6.21"
        assert first_wire_after["auto_clippers"] == "2"

        # Physically close both targets and the Agent connection. No browser or
        # SSE client exists during the bounded real-server production interval.
        close_page(page1, target1)
        close_page(page2, target2)
        agent.close()
        disconnected = api.Client(case["port"])
        disconnected_before = api.checked_json(disconnected.get()[1])
        disconnected.close()
        clock.sleep(2.2)
        disconnected = api.Client(case["port"])
        disconnected_after = api.checked_json(disconnected.get()[1])
        disconnected.close()
        seconds = (disconnected_after["clock"]["update_count"] // 100 -
                   disconnected_before["clock"]["update_count"] // 100)
        disconnected_update_delta = (disconnected_after["clock"]["update_count"] -
                                       disconnected_before["clock"]["update_count"])
        assert seconds >= 2 and disconnected_update_delta > 0, (disconnected_before, disconnected_after)
        # The reference follows every owned 10 ms tick, including partial
        # whole-second windows; it is not an arbitrary integer production cap.
        expected_tick_production = Decimal(disconnected_update_delta) * Decimal("0.02")
        produced = (Decimal(disconnected_after["game"]["lifetime_clips"]) -
                    Decimal(disconnected_before["game"]["lifetime_clips"]))
        assert produced == expected_tick_production, {
            "before": disconnected_before, "after": disconnected_after,
            "expectedTickProduction": str(expected_tick_production),
            "disconnectedUpdateDelta": disconnected_update_delta,
        }
        assert Decimal(disconnected_before["game"]["wire"]) - Decimal(disconnected_after["game"]["wire"]) == produced
        assert disconnected_after["game"]["auto_clipper_rate"] == "2"
        agent = api.Client(case["port"])
        page1, context1, target1 = browser.new_page("/")
        page2, context2, target2 = browser.new_page("/")
        assert context1 != context2
        both(lambda value: value["autoClippers"] == "2" and value["autoClipperCost"] == "6.21" and
             value["autoClipperRate"] == "2" and value["runId"] == disconnected_after["run_id"],
             "two fresh pages recover producer/rate after a zero-client interval")

        # Fund initial Marketing only after the permanent reveal. Use public
        # Make commands to convert each current spool, as in the proven G02 flow.
        wire_purchases = 1
        procurement_trace = []
        production_stock_race_rejections = 0
        for _ in range(12):
            commerce = current()["game"]
            procurement_trace.append({"funds": commerce["funds"], "wire": commerce["wire"],
                                      "unsold": commerce["unsold_clips"], "wirePurchases": wire_purchases})
            if Decimal(commerce["funds"]) >= Decimal("100"):
                break
            available_wire = int(Decimal(commerce["wire"]))
            # This exact decimal-derived count is only the maximum whole
            # one-Wire Make commands; sub-one stock grants no manual clip.
            if available_wire > 0:
                for index in range(available_wire):
                    status, body = agent.make(f"g03-more-{wire_purchases}-{index}")
                    decoded = api.checked_json(body)
                    if status == 422 and decoded.get("reason") == "insufficient_wire":
                        # AutoClippers legally consumed stock while this public
                        # batch was in flight. Stop at the actual stock boundary;
                        # any other status or rejection remains a hard failure.
                        assert decoded["status"] == "rule_rejected"
                        production_stock_race_rejections += 1
                        break
                    assert status == 200 and decoded["status"] == "applied", (index, status, decoded)
                continue
            commerce = current()["game"]
            potential = (Decimal(commerce["funds"]) +
                         Decimal(commerce["unsold_clips"]) * Decimal(commerce["price_per_clip"]))
            if potential >= Decimal("100"):
                # Existing legal inventory can fund Marketing without another
                # spool; merely wait for actual sales instead of spending to 13.
                wait_for(current, lambda view: Decimal(view["game"]["funds"]) >= Decimal("100"),
                         "existing inventory funds Marketing without another spool", timeout=180)
                break
            wait_for(current, lambda view:
                     Decimal(view["game"]["funds"]) >= Decimal("100") or
                     Decimal(view["game"]["funds"]) >= Decimal(view["game"]["wire_quote"]) + Decimal("13"),
                     "bounded sale-funded Marketing procurement at the current server quote", timeout=120)
            commerce = current()["game"]
            if Decimal(commerce["funds"]) < Decimal("100"):
                press(page1, "buy_wire")
                wire_purchases += 1
        else:
            raise AssertionError(f"bounded G03 Marketing funding did not reach 100: {procurement_trace}")

        before_marketing = current()["game"]
        assert Decimal(before_marketing["funds"]) >= Decimal("100")
        marketing = press(page2, "buy_marketing")
        after_marketing = wait_for(current, lambda view: view["game"]["marketing_level"] == "2",
                                   "initial Marketing only after AutoClipper reveal")["game"]
        marketing_charge = (Decimal(before_marketing["funds"]) + Decimal(after_marketing["income"]) -
                            Decimal(before_marketing["income"]) - Decimal(after_marketing["funds"]))
        assert marketing_charge == Decimal("100")
        both(lambda value: value["marketingLevel"] == "2" and value["marketingCost"] == "200" and
             value["autoClippers"] == "2" and value["autoClipperCost"] == "6.21" and
             len(value["consoleMessages"]) == 5,
             "G03 five-line console and shared Marketing/AutoClipper state")

        # Issue17 AC4: commit a genuine M1 world, then accept a later legal
        # command which is deliberately not saved before a real SIGKILL.
        marketing_revision = marketing["response_body"]["revision"]
        commit_sequence_before_wait = api.assert_ready(agent)["last_committed_sequence"]
        assert commit_sequence_before_wait is not None
        committed_health = stored.wait_for_health(
            agent, 200, 40,
            lambda health: health["last_committed_revision"] is not None and
            health["last_committed_revision"] >= marketing_revision and
            health["last_committed_sequence"] is not None and
            health["last_committed_sequence"] > commit_sequence_before_wait)
        assert committed_health["last_committed_sequence"] is not None
        unsaved_lower = press(page1, "lower_price")
        unsaved_revision = unsaved_lower["response_body"]["revision"]
        assert unsaved_revision > committed_health["last_committed_revision"]
        pre_crash = current()
        assert pre_crash["game"]["price_per_clip"] == "0.03"
        assert pre_crash["game"]["marketing_level"] == "2"
        assert pre_crash["revision"] >= unsaved_revision
        old_run = pre_crash["run_id"]
        agent.close()
        old_backend = case["backendOwner"]
        old_backend.force_stop()
        crash_exit = old_backend.process.poll()
        assert crash_exit != 0, "owned server really crashed without graceful final save"

        # Read only the last committed V3 row after the process is dead. No
        # pre-crash state write or snapshot edit participates in this test.
        saved = stored.read_snapshot(database)
        assert saved["revision"] < unsaved_revision
        assert saved["revision"] < pre_crash["revision"]
        assert saved["pro"]["auto_clippers"] == "2"
        assert saved["pro"]["auto_clipper_cost"] == "6.21"
        assert saved["pro"]["auto_clipper_revealed"] is True
        assert saved["pro"]["marketing_level"] == "2"
        assert saved["pro"]["price_per_clip"] == "0.04"
        assert Decimal("0") <= Decimal(saved["pro"]["auto_clipper_rate"]) <= Decimal("2")
        assert len(saved["pro"]["console_messages"]) == 5

        downtime_started = clock.monotonic()
        clock.sleep(1.2)  # Bounded real downtime; no logical clock may backfill it.
        downtime_seconds = clock.monotonic() - downtime_started
        restart_started = clock.monotonic()
        new_out = (case["temporary"] / "g03-restart.stdout").open("wb")
        new_err = (case["temporary"] / "g03-restart.stderr").open("wb")
        with new_out, new_err:
            replacement = api.start_ready(binary, case["backendArguments"], case["port"],
                                          case["temporary"], new_out, new_err)
        case["backendOwner"] = replacement
        case["backendProcess"] = replacement.process
        agent = api.Client(case["port"])
        recovered = current()
        restart_observation_seconds = clock.monotonic() - restart_started
        update_delta = recovered["clock"]["update_count"] - saved["clock"]["update_count"]
        assert update_delta >= 0
        assert update_delta <= 5_000, "bounded recovered online-tick reference"
        # The real downtime exceeds a second and cannot be counted among updates
        # observed since this restart began. Auto production below checks exact continuation.
        assert Decimal(update_delta) * Decimal("0.01") <= Decimal(str(restart_observation_seconds)) + Decimal("0.25")

        # Replay only online updates after restoration. The stored partial second
        # continues exactly, and each ordinary G01 Wire gate/request is observed.
        expected_lifetime = Decimal(saved["pro"]["lifetime_clips"])
        expected_wire = Decimal(saved["pro"]["wire"])
        expected_accumulator = Decimal(saved["pro"]["auto_clipper_production_accumulator"])
        expected_rate = Decimal(saved["pro"]["auto_clipper_rate"])
        expected_production = Decimal("0")
        tick_request = Decimal("0.02")  # two producers / 100 updates per second
        for tick_offset in range(1, update_delta + 1):
            actual = min(tick_request, expected_wire) if expected_wire >= Decimal("1") else Decimal("0")
            expected_production += actual
            expected_lifetime += actual
            expected_wire -= actual
            expected_accumulator += actual
            if (saved["clock"]["update_count"] + tick_offset) % 100 == 0:
                expected_rate = expected_accumulator
                expected_accumulator = Decimal("0")
        assert Decimal(recovered["game"]["auto_clipper_rate"]) == expected_rate
        assert recovered["revision"] - saved["revision"] == update_delta
        assert Decimal(recovered["game"]["lifetime_clips"]) == expected_lifetime
        assert Decimal(recovered["game"]["wire"]) == expected_wire
        assert recovered["run_id"] != old_run
        assert recovered["game"]["auto_clippers"] == "2"
        assert recovered["game"]["auto_clipper_cost"] == "6.21"
        assert recovered["game"]["auto_clipper_revealed"] is True
        assert recovered["game"]["price_per_clip"] == saved["pro"]["price_per_clip"] == "0.04"
        assert recovered["game"]["marketing_level"] == saved["pro"]["marketing_level"] == "2"
        both(lambda value: value["runId"] == recovered["run_id"] and value["autoClippers"] == "2" and
             value["autoClipperCost"] == "6.21" and value["price"] == "0.04" and
             value["marketingLevel"] == "2" and
             value["consoleMessages"] == saved["pro"]["console_messages"],
             "new-run browser resync adopts the last committed M1 View, not the unsaved command")
        agent.close()

        # A later ordinary stop is only a readback device for exact RNG/timer
        # continuation; it does not replace the SIGKILL recovery proof above.
        replacement.stop()
        recovered_saved = stored.read_snapshot(database)
        recovery_phases = stored.fast_phases_between(saved, recovered_saved)
        stored.assert_rng_continuation(saved["rng_state"], recovered_saved["rng_state"], recovery_phases)
        assert recovered_saved["pro"]["auto_clippers"] == "2"
        assert recovered_saved["pro"]["auto_clipper_cost"] == "6.21"
        assert recovered_saved["pro"]["auto_clipper_revealed"] is True
        assert recovered_saved["pro"]["marketing_level"] == "2"
        assert recovered_saved["pro"]["price_per_clip"] == "0.04"

        def typed_receipt(record: dict[str, Any], kind: str) -> dict[str, Any]:
            return {"command": exact_command(record, kind),
                    "httpStatus": record["response_status"],
                    "response": record["response_body"]}

        result = {
            "m1PlayableIntegration": "current M1 prefix only; no M2/full-game claim",
            "canonicalM1Entry": entry_game,
            "entrySnapshotRevision": entry_stored["revision"],
            "freshLegalManualCommands": 1000,
            "firstRevealBeforeSuccessfulWireOrMarketing": True,
            "preRevealWirePurchases": 0,
            "preRevealMarketingLevel": "1",
            "firstFundsObserved": first_crossing["game"]["funds"],
            "firstRevealPublicView": first_crossing,
            "typedM1Receipts": {
                "firstAutoClipper": typed_receipt(first, "buy_auto_clipper"),
                "secondAutoClipper": typed_receipt(second, "buy_auto_clipper"),
                "belowCostRejection": typed_receipt(below_cost_rejection, "buy_auto_clipper"),
                "postRevealLowerPrice": typed_receipt(post_reveal_lower, "lower_price"),
                "postRevealRaisePrice": typed_receipt(post_reveal_raise, "raise_price"),
                "firstReplacementWire": typed_receipt(first_wire, "buy_wire"),
                "initialMarketing": typed_receipt(marketing, "buy_marketing"),
                "unsavedPostCommitLowerPrice": typed_receipt(unsaved_lower, "lower_price")},
            "firstCharge": str(charge), "firstStoredSuccessor": after["auto_clipper_cost"],
            "firstReceiptRevision": first["response_body"]["revision"],
            "belowCurrentCostRejected": True,
            "belowCurrentCostCase": {"count": after_rejection["auto_clippers"],
                "fundsBefore": before_rejection["funds"], "storedCost": before_rejection["auto_clipper_cost"],
                "fundsAfter": after_rejection["funds"], "storedCostAfter": after_rejection["auto_clipper_cost"]},
            "permanentRevealBelowFive": latched_below_five,
            "secondCharge": str(second_charge), "secondStoredSuccessor": after_second["auto_clipper_cost"],
            "secondReceiptRevision": second["response_body"]["revision"],
            "firstTerminalUuidReplay": "original bytes/revision, no third producer",
            "twoAnonymousPagesAndCanonicalCostDisplay": "6.1 stored / 6.10 shown; 6.21 unchanged",
            "postRevealPriceActions": {
                "lowerReceiptRevision": post_reveal_lower["response_body"]["revision"],
                "lowerPrice": post_reveal_lower_view["game"]["price_per_clip"],
                "lowerDemand": post_reveal_lower_view["game"]["demand"],
                "raiseReceiptRevision": post_reveal_raise["response_body"]["revision"],
                "restoredPrice": post_reveal_raise_view["game"]["price_per_clip"],
                "restoredDemand": post_reveal_raise_view["game"]["demand"],
                "twoPageServerViewFeedback": True},
            "firstPostRevealWireCharge": str(wire_charge),
            "zeroClientSeconds": seconds, "zeroClientProduced": str(produced),
            "zeroClientTickUpdates": disconnected_update_delta,
            "zeroClientExpectedTickProduction": str(expected_tick_production),
            "zeroClientRate": disconnected_after["game"]["auto_clipper_rate"],
            "wirePurchasesAfterReveal": wire_purchases,
            "marketingProcurementTrace": procurement_trace,
            "boundedManualAutomaticStockRaceRejections": production_stock_race_rejections,
            "initialMarketingAfterReveal": {"charge": str(marketing_charge),
                "revision": marketing["response_body"]["revision"], "level": "2"},
            "fiveLineConsole": saved["pro"]["console_messages"],
            "snapshotVersion": 3,
            "recoveredRunIdChanged": True,
            "recoveryStoredCountCostReveal": ["2", "6.21", True],
            "recoveryOnlyOnlineProduction": str(expected_production),
            "realSigkillCrashRecovery": {
                "crashExit": crash_exit,
                "committedRevision": saved["revision"],
                "unsavedLowerReceiptRevision": unsaved_revision,
                "preCrashRevision": pre_crash["revision"],
                "savedPrice": saved["pro"]["price_per_clip"],
                "unsavedPrice": pre_crash["game"]["price_per_clip"],
                "recoveredPrice": recovered["game"]["price_per_clip"],
                "savedMarketingLevel": saved["pro"]["marketing_level"],
                "recoveredMarketingLevel": recovered["game"]["marketing_level"],
                "downtimeSeconds": round(downtime_seconds, 3),
                "restartObservationSeconds": round(restart_observation_seconds, 3),
                "onlineUpdateDelta": update_delta,
                "rngContinuationFastPhases": recovery_phases,
                "lastCommitOnly": True, "noOfflineBackfill": True,
                "dedupAcrossCrashClaimed": False},
            "savedRate": saved["pro"]["auto_clipper_rate"],
            "recoveredRate": recovered["game"]["auto_clipper_rate"],
            "expectedRecoveredRate": str(expected_rate),
            "noOfflineBackfillOrLevelZeroRecompute": True,
            "finalAuthoritativeRecoveredPublicView": recovered,
            "durationSeconds": round(clock.monotonic() - started, 3),
        }
    return {**result, "browser": version, "realBackend": True,
            "chromeExit": case["chromeExit"], "backendExit": case["backendExit"],
            "prefundedOrClientAuthority": False}


def run_business_native_evidence(binary: Path, executable: str, version: str) -> dict[str, Any]:
    with isolated_r2_browser(binary, executable, version, "m1-g02-business") as case:
        browser: Browser = case["browser"]
        page1, context1, _ = browser.new_page("/")
        page2, context2, _ = browser.new_page("/")
        assert context1 != context2
        result = run_business_flow(browser, case["state"], case["client"], page1, page2)
    return {**result, "browser": version, "realBackend": True,
            "chromeExit": case["chromeExit"], "backendExit": case["backendExit"],
            "prefundedOrClientAuthority": False}


def run_main_ui(browser: Browser, state: ProxyState, backend_port: int, page1: Cdp, page2: Cdp) -> dict[str, Any]:
    check_assets_and_negative_commands(page1, browser.origin_port)
    def page_with_observed_server_quote(page: Cdp) -> dict[str, Any] | None:
        def real_view() -> dict[str, Any]:
            client = api.Client(backend_port)
            try:
                view = api.checked_json(client.get()[1])
                # The real initial stock is fixed; only the live Wire quote is temporal.
                api.assert_production(view, "1000", "0", view["game"])
                return view
            finally:
                client.close()
        before = real_view()
        candidate = dom_state(page)
        if candidate.get("viewState") != "ready":
            return None
        after = real_view()
        observed_quotes = {before["game"]["wire_quote"], after["game"]["wire_quote"]}
        # The clock cannot be paused. Bind the DOM to a genuinely read server
        # quote in the API/DOM/API window, never to an invented numeric range.
        if candidate.get("wireQuote") not in observed_quotes:
            return None
        if candidate.get("runId") != before["run_id"] or before["run_id"] != after["run_id"]:
            return None
        return {**candidate, "observedServerWireQuotes": sorted(observed_quotes)}
    first = wait_for(lambda: page_with_observed_server_quote(page1), bool,
                     "page one baseline and actual server Wire quote")
    second = wait_for(lambda: page_with_observed_server_quote(page2), bool,
                      "page two baseline and actual server Wire quote")
    assert first["runId"] == second["runId"] and first["lifetime"] == second["lifetime"] == "0"
    initial_client = api.Client(backend_port)
    initial_view = api.checked_json(initial_client.get()[1])
    initial_client.close()
    assert initial_view["run_id"] == first["runId"]
    assert_only_wire_quote_can_advance(initial_view["game"], {
        "auto_clipper_cost": "5", "auto_clipper_revealed": False, "auto_clippers": "0",
        "auto_clipper_rate": "0", "console_messages": ["", "", "", "", ""],
        "computing_hidden": True, "funds": "0", "lifetime_clips": "0",
        "demand": "3.2", "marketing_cost": "100", "clips_sold": "0",
        "income": "0", "last_sale_revenue": "0", "marketing_level": "1", "memory": "1", "price_per_clip": "0.25",
        "processors": "1", "projects_hidden": True, "trust": "2",
        "unsold_clips": "0", "unused_clips": "0", "wire": "1000",
        "wire_quote": "20", "wire_spool_length": "1000",
    })
    for baseline in (first, second):
        assert baseline["headlineText"] == "0" and baseline["headlineTooltip"] == "0"
        assert baseline["unsold"] == baseline["unused"] == "0"
        assert baseline["funds"] == "0" and baseline["wire"] == "1000"
        assert baseline["spool"] == "1000"
        assert baseline["wireQuote"] in baseline["observedServerWireQuotes"]
        assert baseline["price"] == "0.25" and baseline["marketingLevel"] == "1"
        assert baseline["trust"] == "2" and baseline["processors"] == baseline["memory"] == "1"
        assert baseline["computingHidden"] and baseline["autoClippersHidden"]
        assert baseline["autoClippers"] == "0" and baseline["autoClipperCost"] == "5"
    check_accessibility_and_keyboard_order(page1)

    # The focused native button is activated with Enter. Repeat keydown cannot
    # create a second command, and a held request cannot change local balances.
    state.hold_commands = True
    state.command_release.clear()
    page1.press("Enter", repeat_too=True)
    records = wait_commands(state, 1)
    first_command = exact_command(records[0])
    pending = wait_for(lambda: dom_state(page1), lambda value: value["ariaDisabled"] == "true" and not value["disabled"] and "pending" in value["status"].lower(), "visible pending")
    assert pending["lifetime"] == pending["unsold"] == pending["unused"] == "0"
    assert pending["funds"] == "0" and pending["wire"] == "1000"
    assert pending["headlineText"] == "0" and pending["focus"] == "make-paperclip"
    page1.press("Enter")
    settle_dom(page1)
    assert len(state.command_records) == 1, "pending activation is deduplicated without losing focus"
    state.command_release.set()
    def first_clip_rendered(value: dict[str, Any]) -> bool:
        return (stock_ledger_visible(value, 1, "999") and
                value["headlineText"] == value["headlineTooltip"] == "1")
    first_applied = wait_for(lambda: dom_state(page1),
                             lambda value: first_clip_rendered(value) and "applied" in value["status"],
                             "page one applied View and all three ledgers")
    first_shared = wait_for(lambda: dom_state(page2), first_clip_rendered,
                            "page two observes page one's exact three-ledger update")
    assert first_applied["runId"] == first_shared["runId"] == initial_view["run_id"]
    after_one_client = api.Client(backend_port)
    after_one = api.checked_json(after_one_client.get()[1])
    after_one_client.close()
    assert after_one["run_id"] == initial_view["run_id"]
    api.assert_production(after_one, "999", "1", after_one["game"])
    # A genuine sale may follow the applied frame before this newer API read.
    # First account for exactly one manual production, then prove any sale.
    before_post_production_sales = {**initial_view["game"], "lifetime_clips": "1",
                                     "unsold_clips": "1", "unused_clips": "1", "wire": "999"}
    assert_only_wire_quote_can_advance(after_one["game"], before_post_production_sales)
    assert after_one["game"]["wire"] == "999"
    for field in ("wire_spool_length", "price_per_clip", "marketing_level",
                  "trust", "processors", "memory", "auto_clippers", "auto_clipper_cost"):
        assert after_one["game"][field] == initial_view["game"][field], field
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
        wait_for(lambda page=page: dom_state(page),
                 lambda value: (stock_ledger_visible(value, 2, "998") and
                                value["headlineText"] == value["headlineTooltip"] == "2" and
                                value["runId"] == initial_view["run_id"]),
                 "two-page second command convergence")

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
        wait_for(lambda page=page: dom_state(page), lambda value: stock_ledger_visible(value, 5, "995"), "simultaneous Agent/browser convergence")
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
    wait_for(lambda: dom_state(page1), lambda value: stock_ledger_visible(value, 6, "994"), "SSE after dropped applied response")
    page1.press("Enter")
    retry_records = wait_commands(state, before_retry_count + 2)
    replay = retry_records[-1]
    assert replay["raw"] == dropped["raw"] and exact_command(replay)["command_id"] == retry_command["command_id"]
    wait_for(lambda: dom_state(page1), lambda value: stock_ledger_visible(value, 6, "994") and "applied" in value["status"], "same-ID retry no duplicate effect")
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

    # Unsupported actions remain closed. Use the #9 explicitly supported
    # existing-key/unsupported-action 409 path rather than inventing a fake
    # executable future command.
    conflict_status, conflict_body = agent_client.post(json_bytes({
        "command_id": retry_command["command_id"], "type": "unsupported_action", "arguments": {},
    }))
    assert conflict_status == 409 and conflict_body == b'{"status":"conflict"}'
    after_api_conflict = api.checked_json(agent_client.get()[1])
    assert after_api_conflict["game"]["lifetime_clips"] == "6"
    assert agent_client.make(retry_command["command_id"]) == (dropped["response_status"], json_bytes(dropped["response_body"]))

    # Issue17 actual shared-world contention: every client observes one legal
    # remaining Wire, but only one of two native pages plus the Agent can apply.
    for index in range(993):
        status, body = agent_client.make(f"m1-ui-exhaust-{index}")
        assert status == 200, (index, status, body)
    contention_entry = api.checked_json(agent_client.get()[1])
    assert contention_entry["game"]["wire"] == "1"
    assert contention_entry["game"]["lifetime_clips"] == "999"

    state.hold_commands = True
    state.command_release.clear()
    contention_index = len(state.command_records)
    page1.evaluate("document.getElementById('make-paperclip').focus()")
    page1.call("Page.bringToFront")
    page1.press("Enter")
    page2.evaluate("document.getElementById('make-paperclip').focus()")
    page2.call("Page.bringToFront")
    page2.press("Space")
    browser_contenders = wait_commands(state, contention_index + 2)[contention_index:]
    agent_contender_result: list[Any] = []
    def contend_for_last_wire() -> None:
        agent_contender_result.append(agent_client.make("m1-ui-one-wire-agent-rival"))
    agent_contender_thread = threading.Thread(target=contend_for_last_wire)
    agent_contender_thread.start()
    state.hold_commands = False
    state.command_release.set()
    agent_contender_thread.join(timeout=8)
    assert not agent_contender_thread.is_alive() and len(agent_contender_result) == 1
    agent_contender_status, agent_contender_raw = agent_contender_result[0]
    agent_contender_body = api.checked_json(agent_contender_raw)
    assert agent_contender_status in (200, 422)
    if agent_contender_status == 200:
        assert agent_contender_body["status"] == "applied"
        assert type(agent_contender_body["revision"]) is int

    contention_receipts = []
    browser_rejections = []
    for page, label, record in zip((page1, page2), ("page1", "page2"), browser_contenders):
        command = exact_command(record)
        wait_for(lambda record=record: record.get("response_body"),
                 lambda value: isinstance(value, dict), "real one-Wire rival response")
        assert record["forwarded"] == 1 and record["response_status"] in (200, 422), record
        body = record["response_body"]
        revision = body["revision"]
        if record["response_status"] == 200:
            assert body["status"] == "applied"
            message = (f"Server applied the command at revision {revision}. "
                       "Displayed resources come from the newest full server View.")
        else:
            assert body["status"] == "rule_rejected" and body["reason"] == "insufficient_wire"
            message = ("Server rejected the command: not enough Wire. "
                       "This request made no resource change.")
            browser_rejections.append(record)
        wait_for(lambda page=page, message=message, revision=revision: dom_state(page),
                 lambda value: value["status"] == message and int(value["revision"]) >= revision,
                 f"{label} typed one-Wire terminal feedback")
        contention_receipts.append({"client": label, "command_id": command["command_id"],
                                    "httpStatus": record["response_status"], "body": body})
    contention_receipts.append({"client": "structured Agent",
                                "command_id": "m1-ui-one-wire-agent-rival",
                                "httpStatus": agent_contender_status,
                                "body": agent_contender_body})
    assert sorted(receipt["httpStatus"] for receipt in contention_receipts) == [200, 422, 422]
    assert all(record["response_body"]["reason"] == "insufficient_wire"
               for record in browser_rejections)
    if agent_contender_status == 422:
        assert agent_contender_body["status"] == "rule_rejected"
        assert agent_contender_body["reason"] == "insufficient_wire"
    assert len(browser_rejections) >= 1

    # All views converge to the one serial authoritative result. No stale page or
    # rejected command invents a positive resource delta.
    both_stock = lambda value: value.get("viewState") == "ready" and stock_ledger_visible(value, 1000, "0")
    for page in (page1, page2):
        wait_for(lambda page=page: dom_state(page), both_stock,
                 "two-page one-Wire contender convergence")
    exhausted = api.checked_json(agent_client.get()[1])
    assert exhausted["game"]["wire"] == "0" and exhausted["game"]["lifetime_clips"] == "1000"

    # A rejected command ID replays its exact original terminal receipt only.
    rejection_record = browser_rejections[0]
    rejected_id = exact_command(rejection_record)["command_id"]
    assert agent_client.make(rejected_id) == (
        422, json_bytes(rejection_record["response_body"]))
    after_rejection = api.checked_json(agent_client.get()[1])
    assert_only_wire_quote_can_advance(after_rejection["game"], exhausted["game"])
    assert after_rejection["game"]["wire"] == "0"
    assert after_rejection["game"]["lifetime_clips"] == "1000"
    agent_client.close()

    return {"commandsThroughUIProxy": len(state.command_records), "twoPageConvergedClips": "1000",
            "firstManualCommand": {"lifetime": "0->1", "unsold": "0->1", "unused": "0->1",
                                   "wire": "1000->999", "funds": after_one["game"]["funds"], "headline": "0->1"},
            "pendingGrantedNothing": True, "serverAndBothPagesMatched": True,
            "agentAppliedCommands": 994 + int(agent_contender_status == 200),
            "sameIdRetryAppliedOnce": True,
            "realRuleRejections": 2, "apiConflicts": 1, "typedProxyConflicts": 1,
            "oneWireContention": {
                "entryWire": contention_entry["game"]["wire"],
                "entryLifetime": contention_entry["game"]["lifetime_clips"],
                "receipts": contention_receipts, "appliedCommands": 1,
                "insufficientWireReceipts": 2, "rejectedIdReplayBodyIdentical": True,
                "twoPagesAndAgentConverged": True},
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
      const numericResponseCases = [['applied_float','{{"status":"applied","revision":7.0}}'],['applied_exponent','{{"status":"applied","revision":7e0}}'],['rejected_float','{{"status":"rule_rejected","revision":8.0,"reason":"insufficient_wire"}}'],['rejected_exponent','{{"status":"rule_rejected","revision":8e0,"reason":"insufficient_wire"}}']];
      const numericResponseResults = {{}};
      for (const [name, body] of numericResponseCases) {{
        const events = [];
        const runner = new MakePaperclipCommandRunner(event => events.push(event), {{fetch: () => response(body)}});
        const outcome = await runner.run();
        if (outcome.kind !== 'invalid_response' || runner.pending || !runner.retryAvailable ||
            events.map(event => event.kind).join(',') !== 'pending,invalid_response') {{
          throw new Error('noncanonical transport integer accepted: ' + name);
        }}
        numericResponseResults[name] = {{...outcome, pending: runner.pending, retry: runner.retryAvailable}};
      }}
      const assertNumericTokenRejected = (text) => {{
        let error = null;
        try {{ module.parseTransportJson(text); }} catch (caught) {{ error = caught; }}
        if (!error || !(error instanceof TypeError) || error.constructor.name !== 'ResponseValidationError') {{
          throw new Error('raw integer token validation: ' + String(error));
        }}
      }};
      assertNumericTokenRejected('{{"revision":7.0}}');
      assertNumericTokenRejected('{{"revision":7e0}}');
      if (module.parseTransportJson('7') !== 7) throw new Error('native integer source support');
      const quotedControl = {{"note":"literal 7.0 and 7e0 and -0 text","large_amount_as_string":"90071992547409930000000000000000000000000000000000001","revision":7}};
      const quotedParsed = module.parseTransportJson(JSON.stringify(quotedControl));
      if (quotedParsed.note !== quotedControl.note || quotedParsed.revision !== 7 ||
          quotedParsed.large_amount_as_string !== quotedControl.large_amount_as_string ||
          BigInt(quotedParsed.large_amount_as_string) !== BigInt(quotedControl.large_amount_as_string)) {{
        throw new Error('quoted transport text was reinterpreted as a number');
      }}
      const nativeParse = JSON.parse;
      let missingSourceError = null;
      try {{
        // Synchronous fault injection only; no event can run before restoration.
        JSON.parse = (text, reviver) => nativeParse(text, (key, value) => reviver(key, value));
        try {{ module.parseTransportJson('{{"revision":7}}'); }} catch (caught) {{ missingSourceError = caught; }}
      }} finally {{ JSON.parse = nativeParse; }}
      if (!missingSourceError || !(missingSourceError instanceof TypeError) ||
          missingSourceError.constructor.name !== 'ResponseValidationError' || JSON.parse !== nativeParse) {{
        throw new Error('unsupported JSON source metadata did not fail closed');
      }}
      outcomes.numericSourceValidation = {{responses: numericResponseResults, acceptedInteger: 7,
        rejectedRawTokens: ['7.0', '7e0'], quotedTextUnchanged: true, missingSourceRejected: true}};
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
    numeric = result["numericSourceValidation"]
    assert set(numeric["responses"]) == {"applied_float", "applied_exponent", "rejected_float", "rejected_exponent"}
    assert all(outcome["kind"] == "invalid_response" for outcome in numeric["responses"].values())
    assert numeric["acceptedInteger"] == 7 and numeric["quotedTextUnchanged"] is True
    assert numeric["missingSourceRejected"] is True and numeric["rejectedRawTokens"] == ["7.0", "7e0"]
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
      const demandPercentChecks = [
        ['3.2', '32%'], ['3.52', '35.2%'], ['22', '220%'], ['80', '800%'],
        ['0.000000000000000001', '0.00000000000000001%'],
        ['9007199254740993', '90,071,992,547,409,930%'],
      ];
      for (const [raw, expected] of demandPercentChecks) {
        check(display.formatDemandPercent(raw) === expected, 'exact Public Demand percent ' + raw);
      }
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
      return {checks: checks.length, invalidRejected: invalid.length,
        demandPercentChecks: demandPercentChecks.length,
        capRejected: capReason === 'non-canonical Amount'};
    })()""")
    assert result["invalidRejected"] == 19 and result["capRejected"] is True, result
    assert result["demandPercentChecks"] == 6, result
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
            "demand": "9007199254740993", "marketing_cost": "9007199254740994",
            "clips_sold": "9007199254740995", "income": "0.000000000000000001",
            "last_sale_revenue": "0.123",
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
        "demand": "9007199254740993",
        "marketing-cost": "9007199254740994",
        "clips-sold": "9007199254740995",
        "income": "0.000000000000000001",
        "last-sale-revenue": "0.123",
    }
    for element, canonical in expected.items():
        actual = amount(element)
        assert actual["canonical"] == canonical, (element, actual)
        if element == "demand":
            # Raw canonical demand is independent of the exact percent display.
            # Arbitrary-precision integer math preserves >2^53 without a float shortcut.
            assert actual["display"] == actual["title"] == f"{int(canonical) * 10:,}%", actual
        elif element == "funds":
            assert actual["display"] == "-41,117.99"
            assert actual["title"] == canonical, actual
        else:
            assert actual["display"].replace(",", "").removesuffix(".00") == canonical, (element, actual)
            assert actual["title"] == canonical, actual
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
                         "version": version, "temporary": temporary, "port": port,
                         "database": temporary / "owned.sqlite3", "backendOwner": process,
                         "backendArguments": ["--listen-addr", f"127.0.0.1:{port}",
                                              "--database-path", str(temporary / "owned.sqlite3")],
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
            active_backend = info.get("backendOwner", process)
            if active_backend is not None:
                if active_backend.process.poll() is None:
                    active_backend.stop()
                info["backendExit"] = active_backend.process.poll()
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
        result["checkpointSaleControls"] = checkpoint_sale_controls(template["game"])
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
        assert first_probe["upstreamStatus"] == 200, first_probe
        assert_only_wire_quote_can_advance(first_probe["upstreamBody"]["game"], template["game"])
        result["realJsonWithParameters"] = {"dom": positive_get, "record": first_probe}

        # A valid server JSON body under JSONP is not accepted as the initial View.
        # Withhold the real SSE HTTP response so `onopen` cannot overwrite this rejection.
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
        wait_for(lambda: retry,
            lambda value: value.get("forwarded") == 1 and value.get("response_status") == 200 and
                value.get("dropped") is False and "injectedResponse" not in value and
                isinstance(value.get("response_body"), dict) and
                value["response_body"].get("status") == "applied" and
                type(value["response_body"].get("revision")) is int,
            "complete genuine same-ID/body backend response")
        applied = wait_for(lambda: dom_state(page),
            lambda value: value.get("lifetime") == "2" and value.get("wire") == "998" and
                int(value.get("revision", -1)) >= retry["response_body"]["revision"] and
                value.get("status") == (
                    f"Server applied the command at revision {retry['response_body']['revision']}. "
                    "Displayed resources come from the newest full server View."
                ), "real same-ID/body retry")
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
        assert_only_wire_quote_can_advance(api.checked_json(client.get()[1])["game"], after_retry_game)
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
        assert_only_wire_quote_can_advance(state.get_record["body"]["game"], after_retry_game)
        assert state.get_record["delivered"] is False
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
        assert_only_wire_quote_can_advance(api.checked_json(client.get()[1])["game"], after_retry_game)
        result["lateMalformedGet"] = {"upstreamCaptured": state.get_record["body"]["game"],
            "baseline": baseline, "failureText": failed_get, "heldRealFrame": True,
            "failedDom": failed_dom, "recoveredDom": recovered, "recoveredText": connection,
            "realRevisionBeforeRecovery": before_revision, "realRevisionAfterRecovery": int(recovered["revision"])}
        # Each raw counter response is rejected with zero backend dispatch, then
        # the removed fault permits a genuine same-ID/body retry and a real View.
        numeric_command_cases = [
            ("applied_float", 200, b'{"status":"applied","revision":7.0}'),
            ("applied_exponent", 200, b'{"status":"applied","revision":7e0}'),
            ("rejected_float", 422, b'{"status":"rule_rejected","revision":8.0,"reason":"insufficient_wire"}'),
            ("rejected_exponent", 422, b'{"status":"rule_rejected","revision":8e0,"reason":"insufficient_wire"}'),
        ]
        numeric_command_results = []
        for name, http_status, response_body in numeric_command_cases:
            before_game = api.checked_json(client.get()[1])["game"]
            expected_lifetime = int(before_game["lifetime_clips"]) + 1
            expected_wire = int(before_game["wire"]) - 1
            state.next_command_response = {"body": response_body, "content_type": "application/json",
                                          "status": http_status}
            attempt_number = len(state.command_records) + 1
            page.evaluate("document.getElementById('make-paperclip').focus()")
            page.press("Enter")
            wait_commands(state, attempt_number)
            rejected_record = state.command_records[-1]
            rejected_dom = wait_for(lambda: dom_state(page),
                lambda value: "response could not be validated" in value.get("status", "") and
                    value.get("button") == "Retry Make Paperclip", "raw noncanonical command rejection: " + name)
            exact_rejected = exact_command(rejected_record)
            assert rejected_record["forwarded"] == 0 and rejected_record["injectedResponse"] is True
            assert rejected_record["response_status"] == http_status, rejected_record
            assert rejected_record["responseContentType"] == "application/json"
            assert exact_rejected["type"] == "make_paperclip" and exact_rejected["arguments"] == {}
            assert rejected_record["raw"].decode() == json.dumps(exact_rejected, separators=(",", ":"))
            assert rejected_dom["ariaDisabled"] == "false" and rejected_dom["disabled"] is False
            assert rejected_dom["focus"] == "make-paperclip" and rejected_dom["viewState"] == "ready"
            assert int(rejected_dom["lifetime"]) == expected_lifetime - 1
            assert int(rejected_dom["wire"]) == expected_wire + 1
            assert "revision 7" not in rejected_dom["status"] and "revision 8" not in rejected_dom["status"]
            assert_only_wire_quote_can_advance(api.checked_json(client.get()[1])["game"], before_game)

            page.evaluate("document.getElementById('make-paperclip').focus()")
            page.press("Enter")
            wait_commands(state, attempt_number + 1)
            genuine_record = wait_for(lambda: state.command_records[attempt_number],
                lambda value: value.get("forwarded") == 1 and value.get("response_status") == 200 and
                    isinstance(value.get("response_body"), dict) and "injectedResponse" not in value,
                "complete genuine backend POST response after " + name)
            assert genuine_record["raw"] == rejected_record["raw"]
            assert genuine_record["json"] == rejected_record["json"]
            assert exact_command(genuine_record) == exact_rejected
            assert genuine_record["forwarded"] == 1 and "injectedResponse" not in genuine_record
            assert genuine_record["response_status"] == 200
            genuine_receipt = genuine_record["response_body"]
            assert genuine_receipt["status"] == "applied" and type(genuine_receipt["revision"]) is int
            recovered_dom = wait_for(lambda: dom_state(page),
                lambda value: value.get("lifetime") == str(expected_lifetime) and
                    value.get("wire") == str(expected_wire) and
                    int(value.get("revision", -1)) >= genuine_receipt["revision"] and
                    f"revision {genuine_receipt['revision']}" in value.get("status", ""),
                "genuine retry and later complete View after " + name)
            server_game = api.checked_json(client.get()[1])["game"]
            assert server_game["lifetime_clips"] == str(expected_lifetime)
            assert server_game["wire"] == str(expected_wire)
            numeric_command_results.append({"case": name, "injectedHttpStatus": http_status,
                "responseBodyHex": response_body.hex(), "zeroForwardRecord": exact_rejected,
                "invalidDom": rejected_dom, "serverGameBefore": before_game,
                "serverUnchangedAfterInvalid": True,
                "genuineRetry": {"exactSameIdAndRawBody": True, "forwarded": 1,
                                 "receipt": genuine_receipt, "domAfterRealView": recovered_dom},
                "serverGameAfterRetry": server_game})
        result["r3NumericCommandBoundaries"] = {
            "controls": "four actual UI requests, finite HTTP numeric-source faults, then four genuine same-ID/body retries",
            "cases": numeric_command_results,
            "finalServerGame": api.checked_json(client.get()[1])["game"],
        }

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


def run_r3_raw_counters_and_diagnostic(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """Actual JSON wire grammar and stream-diagnostic ownership in native Chrome."""
    with isolated_r2_browser(binary, executable, version, "native-r3-raw-counters") as case:
        state: ProxyState = case["state"]
        browser: Browser = case["browser"]
        client: api.Client = case["client"]
        template = api.checked_json(client.get()[1])
        get_controls = []
        for label, raw_token in [("canonical_integer", None), ("revision_1_0", "1.0"), ("revision_1e0", "1e0")]:
            raw_frame = raw_counter_frame(template, "revision", raw_token) if raw_token is not None else None
            state.next_get_response = {"body": raw_frame[2] if raw_frame is not None else None,
                                       "content_type": "application/json"}
            state.hold_next_get = True
            state.get_captured.clear()
            state.get_release.clear()
            state.get_override_delivered.clear()
            state.hold_first_stream = True
            state.first_stream_captured.clear()
            state.first_stream_release.clear()
            state.real_stream_held.clear()
            state.real_stream_gate.clear()
            state.gate_stream_after_baseline = state.stream_connections + 1
            page, context, target = browser.new_page("/")
            assert state.get_captured.wait(8), "genuine backend View captured: " + label
            assert state.first_stream_captured.wait(8), "native SSE HTTP held before headers: " + label
            if label == "canonical_integer":
                state.get_release.set()
                assert state.get_override_delivered.wait(8), "healthy upstream View delivered"
                healthy = wait_for(lambda: dom_state(page),
                    lambda value: value["viewState"] == "ready" and value["lifetime"] == "0" and
                        value["wire"] == "1000" and value["runId"] == template["run_id"],
                    "healthy integer GET")
                get_record = {"case": label, "genuineUpstream": state.get_override_records[-1],
                    "domBeforeRealStream": healthy}
                baseline_count = len(state.stream_baselines)
                state.first_stream_release.set()
                native_find = wait_for(
                    lambda: state.stream_baselines[-1] if len(state.stream_baselines) > baseline_count else {},
                    lambda value: value.get("run_id") == template["run_id"] and type(value.get("revision")) is int and
                        value.get("game", {}).get("lifetime_clips") == "0" and value.get("game", {}).get("wire") == "1000",
                    "real full View for healthy GET control", timeout=12)
                healthy_sse = wait_for(lambda: dom_state(page),
                    lambda value: value["viewState"] == "ready" and value["lifetime"] == "0" and
                        int(value["revision"]) >= native_find["revision"], "healthy after GET SSE", timeout=10)
                assert state.real_stream_held.wait(12), "healthy native next frame physically held"
                get_record["actualIntegerBaseline"] = native_find
                get_record["domAfterRealStream"] = healthy_sse
                get_controls.append(get_record)
            else:
                page.evaluate("""(() => {
                  window.r3GetHistory = [];
                  const status = document.getElementById('connection-status');
                  window.r3GetObserver = new MutationObserver(() => window.r3GetHistory.push(status.textContent));
                  window.r3GetObserver.observe(status, {childList: true, characterData: true, subtree: true});
                })()""")
                state.get_release.set()
                assert state.get_override_delivered.wait(8), "raw counter HTTP response delivered: " + label
                rejected_history = wait_for(lambda: page.evaluate("window.r3GetHistory.slice()"),
                    lambda history: any("waiting for a live server baseline" in item for item in history),
                    "actual malformed numeric GET observation: " + label)
                rejected_dom = dom_state(page)
                assert rejected_dom["viewState"] == "loading" and rejected_dom.get("lifetime") is None
                assert rejected_dom.get("revision") is None and rejected_dom.get("runId") in (None, "")
                assert all("Connected to the current server run" not in item for item in rejected_history)
                state.first_stream_release.set()
                baseline_count = len(state.stream_baselines)
                native_baseline = wait_for(
                    lambda: state.stream_baselines[-1] if len(state.stream_baselines) > baseline_count else {},
                    lambda value: value.get("run_id") == template["run_id"] and
                        type(value.get("revision")) is int and value["revision"] >= 1 and
                        value.get("game", {}).get("lifetime_clips") == "0" and value.get("game", {}).get("wire") == "1000",
                    "actual integer full View after rejected GET: " + label, timeout=12)
                recovered_dom = wait_for(lambda: dom_state(page),
                    lambda value: value["viewState"] == "ready" and value.get("lifetime") == "0" and
                        value.get("wire") == "1000" and value.get("runId") == template["run_id"] and
                        value.get("revision") is not None and int(value["revision"]) >= native_baseline["revision"],
                    "native View adoption after rejected GET: " + label)
                assert state.real_stream_held.wait(12), "healthy native frame physically held after rejected GET"
                held_history = page.evaluate("window.r3GetHistory.slice()")
                assert held_history.count("Connected to the current server run.") == 1, held_history
                assert not any("Newest accepted server View displayed" in item for item in held_history), held_history
                before_advance = int(recovered_dom["revision"])
                state.real_stream_gate.set()
                advanced = wait_for(lambda: dom_state(page),
                    lambda value: value["viewState"] == "ready" and value.get("revision") is not None and int(value["revision"]) > before_advance,
                    "legitimate later View after malformed numeric GET", timeout=12)
                recovered_history = page.evaluate("window.r3GetHistory.slice()")
                assert recovered_history.count("Newest accepted server View displayed.") == 1, recovered_history
                assert all("invalid server View" not in item for item in recovered_history), recovered_history
                get_controls.append({"case": label, "rawToken": raw_token,
                    "responseSha256": hashlib.sha256(raw_frame[2]).hexdigest(),
                    "responseLength": len(raw_frame[2]), "injectedHttpStatus": 200,
                    "httpBeforeStreamOpen": True, "rejectedDom": rejected_dom,
                    "connectionHistory": recovered_history,
                    "firstActualIntegerBaseline": native_baseline,
                    "firstRecoveredDom": recovered_dom, "physicalStreamHeld": True,
                    "legitimateLaterIntegerDom": advanced,
                    "serverGame": api.checked_json(client.get()[1])["game"]})
            # Let the held next healthy frame go, then close only this owned target.
            state.real_stream_gate.set()
            browser.browser_connection.call("Target.closeTarget", {"targetId": target})
            browser.pages.remove(page)
            page.close()
        state.gate_stream_after_baseline = None
        state.real_stream_gate.set()

        run_id = "r3-counter-lifecycle-quoted-7.0-and-7e0"
        good1 = fixture_view(template, run_id, 1, {})
        bad2 = fixture_view(template, run_id, 2, {"funds": "1.0"})
        good2 = fixture_view(template, run_id, 2, {
            "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22", "wire": "978",
        })
        counter_specs = [(3, "revision", "3.0"), (4, "revision", "4e0"),
            (5, "schema_version", "1.0"), (6, "schema_version", "1e0"),
            (7, "update_count", "1.0"), (8, "update_count", "1e0")]
        counter_frames = []
        for revision, field, token in counter_specs:
            whole = fixture_view(template, run_id, revision, {
                "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22", "wire": "978",
            })
            frame = raw_counter_frame(whole, field, token)
            counter_frames.append(frame)
        recovery = fixture_view(template, run_id, 9, {
            "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22", "wire": "978",
        })
        state.fixture_frames = [good1, bad2, good2, *counter_frames, recovery]
        state.fixture_get_body = b'{bad json'
        state.fixture_get_gate.clear()
        state.fixture_get_delivered.clear()
        state.fixture_sent = [threading.Event() for _ in state.fixture_frames]
        state.fixture_release = [threading.Event() for _ in state.fixture_frames]
        page = browser.new_page("/")[0]
        assert state.fixture_sent[0].wait(8), "R3 healthy fixture baseline"
        baseline = wait_for(lambda: dom_state(page),
            lambda value: value.get("revision") == "1" and value.get("viewState") == "ready", "R3 valid baseline")
        page.evaluate("""(() => {
          window.r3History = [];
          const status = document.getElementById('connection-status');
          window.r3Observer = new MutationObserver(() => window.r3History.push(status.textContent));
          window.r3Observer.observe(status, {childList: true, characterData: true, subtree: true});
        })()""")
        state.fixture_release[0].set()
        assert state.fixture_sent[1].wait(8), "invalid SSE actually sent"
        invalid_text = wait_for(lambda: page.evaluate("document.getElementById('connection-status').textContent"),
            lambda value: "invalid server View" in value, "R3 invalid SSE diagnostic")
        assert dom_state(page) == baseline
        state.fixture_get_gate.set()
        assert state.fixture_get_delivered.wait(8), "real malformed GET delivered"
        settle_dom(page)
        bad_get_history = page.evaluate("window.r3History.slice()")
        assert bad_get_history == [invalid_text], bad_get_history
        assert all("waiting for a live server baseline" not in item for item in bad_get_history)
        assert dom_state(page) == baseline
        assert_only_wire_quote_can_advance(api.checked_json(client.get()[1])["game"], template["game"])
        state.fixture_release[1].set()
        assert state.fixture_sent[2].wait(8)
        recovered2 = wait_for(lambda: dom_state(page),
            lambda value: value["revision"] == "2" and value["lifetime"] == "22" and value["wire"] == "978",
            "valid View after malformed GET")
        recovery_history = page.evaluate("window.r3History.slice()")
        stream_held = state.fixture_connections == 1 and not state.fixture_release[2].is_set()
        assert stream_held is True
        assert recovery_history == [invalid_text, "Newest accepted server View displayed."], recovery_history

        raw_cases = []
        for frame_index, (revision, field, token) in enumerate(counter_specs, start=3):
            state.fixture_release[frame_index - 1].set()
            assert state.fixture_sent[frame_index].wait(8), f"R3 raw numeric SSE frame {frame_index}"
            settle_dom(page)
            snapshot = dom_state(page)
            assert snapshot["revision"] == "2" and snapshot["lifetime"] == "22" and snapshot["wire"] == "978"
            assert snapshot["viewState"] == "ready" and snapshot["runId"] == run_id
            assert page.evaluate("document.getElementById('connection-status').textContent.includes('invalid server View')")
            frame = counter_frames[frame_index - 3]
            raw_cases.append({"field": field, "token": token, "canonicalEventId": f"{frame[0]}:{frame[1]}",
                "rawBodySha256": hashlib.sha256(frame[2]).hexdigest(), "rawBodyHex": frame[2].hex(),
                "retainedDom": snapshot, "physicalStreamHeld": not state.fixture_release[frame_index].is_set()})
        final_index = len(state.fixture_frames) - 1
        state.fixture_release[final_index - 1].set()
        assert state.fixture_sent[final_index].wait(8)
        recovered_final = wait_for(lambda: dom_state(page),
            lambda value: value["revision"] == "9" and value["lifetime"] == "22" and value["wire"] == "978",
            "higher valid View after raw numeric SSE")
        final_history = page.evaluate("window.r3History.slice()")
        stream_held_final = state.fixture_connections == 1 and not state.fixture_release[final_index].is_set()
        assert stream_held_final is True
        assert final_history == [invalid_text, "Newest accepted server View displayed.",
                                 invalid_text, "Newest accepted server View displayed."], final_history
        numeric_result = {"badAmountSseThenMalformedGet": {
            "invalidText": invalid_text, "afterGetHistory": bad_get_history,
            "afterGetDom": baseline, "recoveredDom": recovered2,
            "afterRecoveryHistory": recovery_history, "diagnosticErasedByBadGet": False,
            "physicalStreamHeld": stream_held, "serverGame": api.checked_json(client.get()[1])["game"]},
            "rawNumericSse": raw_cases, "validHigherView": recovered_final,
            "fullHistoryBeforeRealBackend": final_history, "physicalStreamHeldAtFinal": stream_held_final}
        state.fixture_release[final_index].set()
        state.fixture_frames = None
        state.fixture_close.set()
        actual_baseline = wait_for(lambda: dom_state(page),
            lambda value: value["runId"] == template["run_id"] and value["viewState"] == "ready" and
                value["lifetime"] == "0" and value["wire"] == "1000", "real backend View after fixtures", timeout=12)
        assert_only_wire_quote_can_advance(api.checked_json(client.get()[1])["game"], template["game"])
        state.hold_commands = True
        state.command_release.clear()
        page.evaluate("document.getElementById('make-paperclip').focus()")
        page.press("Enter")
        wait_commands(state, 1)
        pending = wait_for(lambda: dom_state(page),
            lambda value: "Command pending" in value["status"] and value["ariaDisabled"] == "true" and
                value["disabled"] is False and value["focus"] == "make-paperclip", "owned real command pending")
        state.hold_commands = False
        state.command_release.set()
        actual_command = wait_for(lambda: state.command_records[0],
            lambda value: value.get("forwarded") == 1 and value.get("response_status") == 200 and
                isinstance(value.get("response_body"), dict) and value["response_body"].get("status") == "applied",
            "real post-fixture command completion")
        genuine = wait_for(lambda: dom_state(page),
            lambda value: value["lifetime"] == "1" and value["wire"] == "999" and
                int(value["revision"]) >= actual_command["response_body"]["revision"] and
                f"revision {actual_command['response_body']['revision']}" in value["status"],
            "real command and real newest View after numeric/lifecycle controls")
        server_game = api.checked_json(client.get()[1])["game"]
        assert server_game["lifetime_clips"] == "1" and server_game["wire"] == "999"
        assert not state.errors, state.errors[:10]
        numeric_result["postRecoveryRealBackendCommand"] = {"before": actual_baseline, "pending": pending,
            "request": exact_command(actual_command), "sameCanonicalEnvelope": True, "forwarded": 1,
            "receipt": actual_command["response_body"], "dom": genuine, "serverGame": server_game}
        numeric_result["genuineBackendBeforeFixturesWasUnchanged"] = template["game"]
    return {"moduleAndTransport": "shared commands.js parser for native command/GET/EventSource",
            "realRawGetControls": get_controls,
            "fixtureAuthority": "explicit transport bytes, not server commands or resource credits", **numeric_result,
            "browser": version, "chromeExit": case["chromeExit"], "backendExit": case["backendExit"]}


class PhysicalReconnectState(ProxyState):
    """Raw transport gates and real accepted-View observations for reconnect."""

    def __init__(self, backend_port: int, template: dict[str, Any]):
        super().__init__(backend_port)
        self.run_id = "maintained-native-reconnect"
        self.good1 = fixture_view(template, self.run_id, 1, {})
        self.good2 = fixture_view(template, self.run_id, 2, {
            "lifetime_clips": "22", "unsold_clips": "22", "unused_clips": "22", "wire": "978"})
        bad_revision = raw_counter_frame(self.good2, "revision", "2.0")
        self.invalid2_wire = physical_event_bytes(*bad_revision)
        self.invalid2_body = bad_revision[2]
        self.good3 = fixture_view(template, self.run_id, 3, {
            "lifetime_clips": "23", "unsold_clips": "23", "unused_clips": "23", "wire": "977"})
        self.invalid3_wire = physical_event_bytes(self.run_id, 999, json_bytes(self.good3))
        self.good4 = fixture_view(template, self.run_id, 4, {
            "lifetime_clips": "24", "unsold_clips": "24", "unused_clips": "24", "wire": "976"})
        self.equal2 = fixture_view(template, self.run_id, 2, {
            "lifetime_clips": "999", "unsold_clips": "999", "unused_clips": "999", "wire": "1"})
        self.pure = fixture_view(template, self.run_id, 90, {"lifetime_clips": "777"})
        self.get_started = threading.Event()
        self.get_release = threading.Event()
        self.get_delivered = threading.Event()
        self.get_body = b"{bad json"
        self.release_invalid2 = threading.Event()
        self.release_good2 = threading.Event()
        self.release_invalid3 = threading.Event()
        self.close_connection1 = threading.Event()
        self.connection2_started = threading.Event()
        self.release_equal2 = threading.Event()
        self.release_lower1 = threading.Event()
        self.release_pure = threading.Event()
        self.release_good3 = threading.Event()
        self.close_connection2 = threading.Event()
        self.connection3_started = threading.Event()
        self.release_good4 = threading.Event()
        self.close_connection3 = threading.Event()
        self.connections: list[dict[str, Any]] = []

    def release_all(self) -> None:
        for value in self.__dict__.values():
            if isinstance(value, threading.Event):
                value.set()


def physical_event_bytes(run_id: str, event_revision: int, data: bytes,
                         event_name: str = "game_view") -> bytes:
    assert len(data) <= 64 * 1024
    return (f"id: {run_id}:{event_revision}\nevent: {event_name}\ndata: ").encode() + data + b"\n\n"


def physical_reconnect_handler(state: PhysicalReconnectState) -> type[BaseHTTPRequestHandler]:
    class Handler(proxy_handler(state)):
        """Reuses genuine asset/backend/POST transport; only raw SSE/GET faults differ."""

        def do_GET(self) -> None:
            if self.path != "/api/game/stream" and self.path != "/api/game/view":
                return super().do_GET()
            if self.path != "/api/game/stream":
                if state.get_started.is_set():
                    return super().do_GET()
                try:
                    state.get_started.set()
                    assert state.get_release.wait(20), "bounded physical-reconnect delayed GET"
                    self.finite(200, state.get_body, "application/json")
                    state.get_delivered.set()
                except (AssertionError, OSError, http.client.HTTPException) as error:
                    state.errors.append(f"GET {self.path}: {type(error).__name__}: {error}")
                finally:
                    self.close_connection = True
                return
            try:
                number = state.fixture_connections + 1
                assert number <= 3, "unexpected extra physical EventSource connection"
                state.fixture_connections = number
                connection = {"number": number, "lastEventId": self.headers.get("Last-Event-ID"),
                              "openedAt": time.time()}
                state.connections.append(connection)
                if number == 2:
                    state.connection2_started.set()
                elif number == 3:
                    state.connection3_started.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store, no-transform")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.flush()
                connection["headersAt"] = time.time()
                if number == 1:
                    self.send_wire(physical_event_bytes(state.run_id, 1, json_bytes(state.good1)),
                                   state.release_invalid2, connection, "good1")
                    self.send_wire(state.invalid2_wire, state.release_good2, connection,
                                   "invalid2_raw_revision_2.0")
                    self.send_wire(physical_event_bytes(state.run_id, 2, json_bytes(state.good2)),
                                   state.release_invalid3, connection, "good2")
                    self.send_wire(state.invalid3_wire, state.close_connection1, connection,
                                   "invalid3_bad_event_id")
                    connection["closedWithoutAcceptedReplacement"] = True
                    return
                if number == 2:
                    # A real open is observable before any potential replacement View.
                    assert state.release_equal2.wait(20), "hold connection2 before replacement"
                    self.send_wire(physical_event_bytes(state.run_id, 2, json_bytes(state.equal2)),
                                   state.release_lower1, connection, "equal2_conflicting_ignored")
                    self.send_wire(physical_event_bytes(state.run_id, 1, json_bytes(state.good1)),
                                   state.release_pure, connection, "lower1_ignored")
                    self.send_wire(physical_event_bytes(state.run_id, 90, json_bytes(state.pure),
                                                        event_name="message"),
                                   state.release_good3, connection, "unnamed_pure_view_ignored")
                    self.send_wire(physical_event_bytes(state.run_id, 3, json_bytes(state.good3)),
                                   state.close_connection2, connection, "good3_real_recovery")
                    return
                assert state.release_good4.wait(20), "hold healthy reconnect before replacement"
                self.send_wire(physical_event_bytes(state.run_id, 4, json_bytes(state.good4)),
                               state.close_connection3, connection, "good4_healthy_reconnect")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except (AssertionError, OSError, http.client.HTTPException) as error:
                state.errors.append(f"GET {self.path}: {type(error).__name__}: {error}")
                try:
                    self.send_error(502)
                except OSError:
                    pass
            finally:
                self.close_connection = True

        def send_wire(self, wire: bytes, release: threading.Event,
                      connection: dict[str, Any], label: str) -> None:
            self.wfile.write(wire)
            self.wfile.flush()
            connection.setdefault("sent", []).append({
                "label": label, "sha256": hashlib.sha256(wire).hexdigest(),
                "hex": wire.hex(), "at": time.time()})
            assert release.wait(20), "bounded physical-reconnect frame gate: " + label

    return Handler


def physical_reconnect_dom(page: Cdp, state: PhysicalReconnectState) -> dict[str, Any]:
    result = page.evaluate("""({
      runId: document.documentElement.dataset.runId,
      revision: document.documentElement.dataset.revision,
      viewState: document.documentElement.dataset.viewState,
      lifetime: document.getElementById('lifetime-clips').dataset.canonical,
      wire: document.getElementById('wire').dataset.canonical,
      connection: document.getElementById('connection-status').textContent,
      streams: (window.__maintainedReconnectStreams || []).map((stream, index) => ({
        index, readyState: stream.readyState, url: stream.url})),
      streamEvents: window.__maintainedReconnectEvents || [],
      history: window.__maintainedConnectionHistory || [],
      revisionHistory: window.__maintainedRevisionHistory || []
    })""")
    result["physicalConnections"] = [
        {key: value for key, value in item.items() if key != "sent"}
        for item in state.connections
    ]
    result["sentCounts"] = [len(item.get("sent", [])) for item in state.connections]
    return result


def physical_reconnect_page(browser: Browser, origin: str) -> Cdp:
    assert browser.browser_connection is not None
    context = browser.browser_connection.call("Target.createBrowserContext")["browserContextId"]
    target = browser.browser_connection.call("Target.createTarget", {
        "url": "about:blank", "browserContextId": context})["targetId"]
    url = wait_for(lambda: next((item.get("webSocketDebuggerUrl")
                                for item in browser.http_json("/json/list")
                                if item.get("id") == target), None),
                   description="instrumented native physical-reconnect CDP")
    page = Cdp(url)
    browser.pages.append(page)
    page.call("Page.enable")
    page.call("Runtime.enable")
    page.call("Network.enable", {"maxTotalBufferSize": 2_000_000, "maxResourceBufferSize": 256_000})
    # Observation only. Reflect constructs and returns the actual native EventSource.
    # No synthetic event, dispatchEvent, EventSource replacement or client label rewrite.
    page.call("Page.addScriptToEvaluateOnNewDocument", {"source": r"""
      (() => {
        const Native = window.EventSource;
        window.__maintainedReconnectStreams = [];
        window.__maintainedReconnectEvents = [];
        window.EventSource = new Proxy(Native, {
          construct(target, args) {
            const stream = Reflect.construct(target, args);
            const index = window.__maintainedReconnectStreams.length;
            window.__maintainedReconnectStreams.push(stream);
            const record = type => window.__maintainedReconnectEvents.push({
              index, type, readyState: stream.readyState, at: performance.now()});
            stream.addEventListener('open', () => record('open'));
            stream.addEventListener('error', () => record('error'));
            record('constructed');
            return stream;
          }
        });
      })();
    """})
    page.call("Page.navigate", {"url": origin + "/"})
    return page


def run_physical_reconnect_lifecycle(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """A rejected View retains diagnosis until accepted presentation across a real reconnect."""
    invalid = "An invalid server View was ignored; the last valid View is retained."
    accepted = "Newest accepted server View displayed."
    opened = "Live server connection open; receiving complete Views."
    interrupted = "Live connection interrupted; the browser will reconnect without resetting the game."
    result: dict[str, Any] = {"browser": version,
                              "transport": "real backend/Chrome/native EventSource through raw-byte proxy"}
    with tempfile.TemporaryDirectory(prefix="paperclip-native-physical-reconnect-") as temporary_name:
        temporary = Path(temporary_name)
        backend_port = api.free_port()
        database = temporary / "owned.sqlite3"
        out = (temporary / "backend.stdout").open("wb")
        err = (temporary / "backend.stderr").open("wb")
        backend = None
        browser = None
        proxy = None
        proxy_thread = None
        client = api.Client(backend_port)
        try:
            backend = api.start_ready(binary.resolve(), ["--listen-addr", f"127.0.0.1:{backend_port}",
                                                         "--database-path", str(database)],
                                      backend_port, temporary, out, err)
            template = api.checked_json(client.get()[1])
            state = PhysicalReconnectState(backend_port, template)
            proxy = Proxy(("127.0.0.1", 0), physical_reconnect_handler(state))
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()
            origin = f"http://127.0.0.1:{proxy.server_address[1]}"
            browser = Browser(executable, temporary, origin)
            page = physical_reconnect_page(browser, origin)
            assert state.get_started.wait(8)
            baseline = wait_for(lambda: physical_reconnect_dom(page, state),
                                lambda value: value.get("revision") == "1" and value.get("viewState") == "ready",
                                "native physical-reconnect real good1")
            assert len(state.connections) == 1 and baseline["streams"][0]["readyState"] == 1
            page.evaluate("""(() => {
              window.__maintainedConnectionHistory = [];
              window.__maintainedRevisionHistory = [];
              const status = document.getElementById('connection-status');
              new MutationObserver(() => window.__maintainedConnectionHistory.push(status.textContent))
                .observe(status, {childList: true, characterData: true, subtree: true});
              new MutationObserver(() => window.__maintainedRevisionHistory
                .push(document.documentElement.dataset.revision))
                .observe(document.documentElement, {attributes: true,
                  attributeFilter: ['data-revision']});
            })()""")

            # Separate held-stream invalid SSE then malformed GET, then genuine good2.
            state.release_invalid2.set()
            invalid_initial = wait_for(lambda: physical_reconnect_dom(page, state),
                                       lambda value: value["connection"] == invalid and value["revision"] == "1",
                                       "raw 2.0 SSE diagnosis while baseline retained")
            state.get_release.set()
            assert state.get_delivered.wait(8)
            settle_dom(page)
            after_get = physical_reconnect_dom(page, state)
            assert after_get["revision"] == "1" and after_get["lifetime"] == "0"
            assert after_get["history"] == [invalid], after_get
            assert len(state.connections) == 1 and after_get["streams"][0]["readyState"] == 1
            state.release_good2.set()
            recovered2 = wait_for(lambda: physical_reconnect_dom(page, state),
                                  lambda value: value["revision"] == "2" and value["lifetime"] == "22"
                                  and value["wire"] == "978" and value["connection"] == accepted,
                                  "genuine good2 accepted on the still-held stream")
            assert recovered2["history"] == [invalid, accepted], recovered2
            assert recovered2["revisionHistory"] == ["2"]
            assert len(state.connections) == 1 and not state.close_connection1.is_set()
            result["rawInvalidDelayedGetGood2HeldStream"] = {
                "rawInvalidBodyHex": state.invalid2_body.hex(),
                "rawInvalidBodySha256": hashlib.sha256(state.invalid2_body).hexdigest(),
                "delayedMalformedGetHex": state.get_body.hex(),
                "baseline": baseline, "invalid": invalid_initial, "afterGet": after_get,
                "acceptedGood2": recovered2, "physicalStreamHeldOpen": True,
                "good2AcceptedExactlyOnce": True,
            }

            # Reject the event ID, then separately close the physical socket through the proxy.
            state.release_invalid3.set()
            before_close = wait_for(lambda: physical_reconnect_dom(page, state),
                                    lambda value: value["connection"] == invalid and value["revision"] == "2",
                                    "wrong Event Id rejected before physical close")
            state.close_connection1.set()
            assert state.connection2_started.wait(10), "native automatic second physical connection"

            def second_open(value: dict[str, Any]) -> bool:
                events = value["streamEvents"]
                return (len(value["streams"]) == 1 and value["streams"][0]["index"] == 0
                        and len(state.connections) == 2 and len(value["streams"]) == 1
                        and value["streams"][0]["readyState"] == 1
                        and any(event["type"] == "error" for event in events)
                        and len([event for event in events if event["type"] == "open"]) >= 2
                        and events[-1]["type"] == "open"
                        and value["sentCounts"] == [4, 0]
                        and value["revisionHistory"] == ["2"])

            before_replacement = wait_for(lambda: physical_reconnect_dom(page, state), second_open,
                                         "second real open before any replacement frame", timeout=12)
            # A generic error/open here is the healthy expectation's specific old-bug failure.
            assert before_replacement["connection"] == invalid, {
                "expected": invalid, "afterPhysicalErrorOpenBeforeReplacement": before_replacement}
            assert before_replacement["lifetime"] == "22" and before_replacement["wire"] == "978"
            assert before_replacement["history"] == [invalid, accepted, invalid], before_replacement
            assert state.connections[1]["lastEventId"] == state.run_id + ":999"
            result["diagnosisAcrossSecondPhysicalConnection"] = {
                "invalidEventIdFrameHex": state.invalid3_wire.hex(), "beforeClose": before_close,
                "afterErrorOpenBeforeAnyReplacement": before_replacement,
                "acceptedReplacementPresentBeforeErasureCheck": False,
                "diagnosticRetainedUntilAcceptedView": True,
                "sameJavaScriptNativeEventSource": True,
                "physicalConnections": 2,
            }

            for label, gate in (("equal2", state.release_equal2),
                                ("lower1", state.release_lower1),
                                ("unnamedPureView", state.release_pure)):
                gate.set()
                settle_dom(page)
                ignored = physical_reconnect_dom(page, state)
                assert ignored["revision"] == "2" and ignored["lifetime"] == "22"
                assert ignored["wire"] == "978" and ignored["connection"] == invalid
                assert ignored["revisionHistory"] == ["2"]
                result[label] = ignored
            state.release_good3.set()
            recovered3 = wait_for(lambda: physical_reconnect_dom(page, state),
                                  lambda value: value["revision"] == "3" and value["lifetime"] == "23"
                                  and value["wire"] == "977" and value["connection"] == accepted,
                                  "actual accepted good3 recovery after physical reconnect")
            assert recovered3["revisionHistory"] == ["2", "3"]
            assert recovered3["history"] == [invalid, accepted, invalid, accepted], recovered3
            result["acceptedGood3Recovery"] = recovered3

            # Generic error/open must still work after accepted presentation cleared the flag.
            state.close_connection2.set()
            assert state.connection3_started.wait(10)
            healthy = wait_for(lambda: physical_reconnect_dom(page, state),
                               lambda value: len(value["physicalConnections"]) == 3
                               and value["connection"] == opened and value["revision"] == "3"
                               and value["sentCounts"] == [4, 4, 0],
                               "healthy reconnect open after accepted presentation", timeout=12)
            assert healthy["history"][-2:] == [interrupted, opened], healthy
            assert len(healthy["streams"]) == 1 and healthy["streams"][0]["index"] == 0
            assert state.connections[2]["lastEventId"] == state.run_id + ":3"
            state.release_good4.set()
            healthy4 = wait_for(lambda: physical_reconnect_dom(page, state),
                                lambda value: value["revision"] == "4" and value["lifetime"] == "24"
                                and value["wire"] == "976" and value["connection"] == accepted,
                                "valid good4 accepted on healthy third connection")
            assert healthy4["history"] == [invalid, accepted, invalid, accepted,
                                           interrupted, opened, accepted], healthy4
            assert healthy4["revisionHistory"] == ["2", "3", "4"]
            assert not state.command_records, "transport fixtures must never be commands/economic credits"
            backend_after = api.checked_json(client.get()[1])
            assert backend_after["game"]["lifetime_clips"] == template["game"]["lifetime_clips"]
            assert backend_after["game"]["wire"] == template["game"]["wire"]
            assert backend_after["run_id"] == template["run_id"]
            result["healthyReconnectControl"] = {"beforeGood4": healthy, "acceptedGood4": healthy4}
            result["physicalConnections"] = state.connections
            result["acceptedRevisionHistory"] = healthy4["revisionHistory"]
            assert [item["number"] for item in state.connections] == [1, 2, 3]
            assert not state.errors, state.errors
            result["backendResourceAuthority"] = {
                "fixtureValuesAreNotBackendCredits": True,
                "forwardedCommands": 0,
                "lifetimeClips": backend_after["game"]["lifetime_clips"],
                "wire": backend_after["game"]["wire"],
            }
            result["status"] = "pass"
            result["proxyErrors"] = state.errors
            state.close_connection3.set()
            return result
        finally:
            if "state" in locals():
                state.release_all()
            if browser is not None:
                browser.close()
                result["chromeExit"] = browser.process.poll()
            if proxy is not None:
                proxy.shutdown()
                proxy.server_close()
            if proxy_thread is not None:
                proxy_thread.join(timeout=5)
                result["proxyThreadStopped"] = not proxy_thread.is_alive()
            client.close()
            if backend is not None:
                backend.stop()
                result["backendExit"] = backend.process.poll()
            out.close()
            err.close()
            result["backendStdoutHex"] = (temporary / "backend.stdout").read_bytes().hex()
            result["backendStderrHex"] = (temporary / "backend.stderr").read_bytes().hex()


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
    physical_result = run_physical_reconnect_lifecycle(binary, executable, version)
    assert (physical_result["chromeExit"], physical_result["backendExit"],
            physical_result["proxyThreadStopped"]) == (0, 0, True), physical_result
    print("NATIVE_R4_PHYSICAL_RECONNECT_EVIDENCE=" + json.dumps(physical_result, separators=(",", ":")))
    response_result = run_r2_response_and_get(binary, executable, version)
    print("NATIVE_R2_RESPONSE_EVIDENCE=" + json.dumps(response_result, separators=(",", ":")))
    lifecycle_result = run_r2_connection_lifecycle(binary, executable, version)
    print("NATIVE_R2_LIFECYCLE_EVIDENCE=" + json.dumps(lifecycle_result, separators=(",", ":")))
    r3_result = run_r3_raw_counters_and_diagnostic(binary, executable, version)
    print("NATIVE_R3_COUNTER_DIAGNOSTIC_EVIDENCE=" + json.dumps(r3_result, separators=(",", ":")))
    business_result = run_business_native_evidence(binary, executable, version)
    assert (business_result["chromeExit"], business_result["backendExit"]) == (0, 0)
    print("NATIVE_G02_BUSINESS_EVIDENCE=" + json.dumps(business_result, separators=(",", ":")))
    autoclipper_result = run_autoclipper_native_evidence(binary, executable, version)
    assert (autoclipper_result["chromeExit"], autoclipper_result["backendExit"]) == (0, 0)
    print("NATIVE_G03_AUTOCLIPPER_EVIDENCE=" + json.dumps(autoclipper_result, separators=(",", ":")))
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
                "g02NativeBusiness": business_result,
                "g03NativeAutoClipper": autoclipper_result,
                "r3CounterDiagnostic": r3_result,
                "physicalReconnectLifecycle": physical_result,
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
