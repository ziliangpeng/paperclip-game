use super::*;
use crate::game::amount::Amount;
use crate::game::rng::GameRng;
use crate::game::state::GameState;
use crate::health::PersistenceFailure;
use crate::runtime::{CommandTestGate, MonotonicClock, RuntimeHandle};
use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::sync::{Notify, oneshot};
use tokio::task::JoinHandle;
use tokio::time::timeout;

const TEST_TIMEOUT: Duration = Duration::from_secs(5);

struct TestClock {
    now: Mutex<Instant>,
    wake: Notify,
}

impl TestClock {
    fn new() -> Self {
        Self {
            now: Mutex::new(Instant::now()),
            wake: Notify::new(),
        }
    }

    fn advance(&self, amount: Duration) {
        let mut now = self.now.lock().unwrap();
        *now = now.checked_add(amount).unwrap();
        drop(now);
        self.wake.notify_one();
    }
}

impl MonotonicClock for Arc<TestClock> {
    fn now(&self) -> Instant {
        *self.now.lock().unwrap()
    }

    fn wait_until(&self, _deadline: Instant) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
        Box::pin(self.wake.notified())
    }
}

struct TestServer {
    address: SocketAddr,
    handle: RuntimeHandle,
    state: ApiState,
    shutdown: Option<oneshot::Sender<()>>,
    shutdown_requested: Option<oneshot::Receiver<()>>,
    task: JoinHandle<Result<(), ServerError>>,
}

impl TestServer {
    fn start(state: GameState, gate: Arc<CommandTestGate>, clock: Arc<TestClock>) -> Self {
        Self::start_with_health(
            state,
            gate,
            clock,
            PersistenceHealth::unconfigured_for_testing(Duration::from_secs(30)),
        )
    }

    fn start_with_health(
        state: GameState,
        gate: Arc<CommandTestGate>,
        clock: Arc<TestClock>,
        health: PersistenceHealth,
    ) -> Self {
        let runtime = GameRuntime::start_with_test_gate(clock, state, gate).unwrap();
        let handle = runtime.handle();
        let state = ApiState::new(handle.clone(), health);
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let listener = TcpListener::from_std(listener).unwrap();
        let (shutdown, stopped) = oneshot::channel();
        let (shutdown_requested, observing_shutdown) = oneshot::channel();
        let task = tokio::spawn(serve_with_state(
            listener,
            runtime,
            state.clone(),
            async {
                let _ = stopped.await;
            },
            Some(shutdown_requested),
        ));
        Self {
            address,
            handle,
            state,
            shutdown: Some(shutdown),
            shutdown_requested: Some(observing_shutdown),
            task,
        }
    }

    fn initiate_shutdown(&mut self) {
        let _ = self.shutdown.take().unwrap().send(());
    }

    async fn wait_shutdown_requested(&mut self) {
        timeout(TEST_TIMEOUT, self.shutdown_requested.take().unwrap())
            .await
            .expect("production serve requests runtime shutdown")
            .expect("shutdown observation channel remains available");
    }

    async fn wait_stopped(self) {
        timeout(TEST_TIMEOUT, self.task)
            .await
            .expect("server stops within bound")
            .expect("server task does not panic")
            .expect("runtime, drain, publication and listener stop cleanly");
    }

    async fn stop(mut self) {
        self.initiate_shutdown();
        self.wait_stopped().await;
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct HttpResponse {
    status: u16,
    body: Vec<u8>,
}

impl HttpResponse {
    fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap()
    }
}

fn blocking_request(address: SocketAddr, method: &str, path: &str, body: &[u8]) -> HttpResponse {
    let mut stream = TcpStream::connect_timeout(&address, TEST_TIMEOUT).unwrap();
    stream.set_read_timeout(Some(TEST_TIMEOUT)).unwrap();
    stream.set_write_timeout(Some(TEST_TIMEOUT)).unwrap();
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )
    .unwrap();
    stream.write_all(body).unwrap();
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).unwrap();
    let split = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .unwrap();
    let headers = std::str::from_utf8(&raw[..split]).unwrap();
    let status = headers
        .split("\r\n")
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse().ok())
        .unwrap();
    HttpResponse {
        status,
        body: raw[split + 4..].to_vec(),
    }
}

fn connect_active_stream(address: SocketAddr) -> TcpStream {
    let mut stream = TcpStream::connect_timeout(&address, TEST_TIMEOUT).unwrap();
    stream.set_read_timeout(Some(TEST_TIMEOUT)).unwrap();
    stream.set_write_timeout(Some(TEST_TIMEOUT)).unwrap();
    write!(
        stream,
        "GET /api/game/stream HTTP/1.1\r\nHost: {address}\r\nAccept: text/event-stream\r\n\r\n"
    )
    .unwrap();
    let mut headers = Vec::new();
    let mut byte = [0_u8; 1];
    while headers.len() < 16 * 1024 && !headers.ends_with(b"\r\n\r\n") {
        stream.read_exact(&mut byte).unwrap();
        headers.push(byte[0]);
    }
    assert!(headers.ends_with(b"\r\n\r\n"));
    assert!(
        String::from_utf8(headers)
            .unwrap()
            .starts_with("HTTP/1.1 200 OK\r\n")
    );
    stream
}

async fn request(
    address: SocketAddr,
    method: &'static str,
    path: &'static str,
    body: Vec<u8>,
) -> HttpResponse {
    tokio::task::spawn_blocking(move || blocking_request(address, method, path, &body))
        .await
        .unwrap()
}

async fn get(address: SocketAddr) -> HttpResponse {
    request(address, "GET", "/api/game/view", Vec::new()).await
}

async fn post(address: SocketAddr, body: Vec<u8>) -> HttpResponse {
    request(address, "POST", "/api/game/commands", body).await
}

fn command(id: &str) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "command_id": id,
        "type": "make_paperclip",
        "arguments": {}
    }))
    .unwrap()
}

fn conflict(id: &str) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "command_id": id,
        "type": "unsupported_future_action",
        "arguments": {}
    }))
    .unwrap()
}

fn state_with_wire(wire: &str) -> GameState {
    let mut state = GameState::fresh(GameRng::from_test_seed([7_u8; 32]));
    state.pro.wire = Amount::parse(wire).unwrap().nonnegative().unwrap();
    state
}

fn fixture() -> (TestServer, Arc<CommandTestGate>, Arc<TestClock>) {
    let gate = Arc::new(CommandTestGate::default());
    let clock = Arc::new(TestClock::new());
    let server = TestServer::start(state_with_wire("2"), Arc::clone(&gate), Arc::clone(&clock));
    (server, gate, clock)
}

async fn wait_for_registration(state: &ApiState, expected: usize) {
    timeout(TEST_TIMEOUT, async {
        while state.retry.registered_count() < expected || state.retry.tracked_count() < expected {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap_or_else(|_| panic!("{expected} accepted commands are registered and tracked"));
}

async fn disconnect_after_registration(server: &TestServer, id: &str, expected: usize) {
    let address = server.address;
    let body = command(id);
    let disconnected = tokio::task::spawn_blocking(move || {
        let mut stream = TcpStream::connect_timeout(&address, TEST_TIMEOUT).unwrap();
        stream.set_write_timeout(Some(TEST_TIMEOUT)).unwrap();
        write!(
            stream,
            "POST /api/game/commands HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        )
        .unwrap();
        stream.write_all(&body).unwrap();
        // Hold the socket while the test observes the shared production state.
        stream
    })
    .await
    .unwrap();
    wait_for_registration(&server.state, expected).await;
    // Retry registration and completion-tracker ownership are both established.
    drop(disconnected);
}

async fn wait_for_revision(handle: &RuntimeHandle, revision: u64) {
    timeout(TEST_TIMEOUT, async {
        loop {
            let view = handle.view();
            if view.revision >= revision {
                return;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("writer view reaches the required applied revision");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn inflight_same_key_coalesces_and_pending_conflict_cannot_overwrite() {
    let (server, gate, clock) = fixture();
    let mut waiters = Vec::new();
    for _ in 0..12 {
        let address = server.address;
        waiters.push(tokio::spawn(post(address, command("inflight"))));
    }
    timeout(TEST_TIMEOUT, gate.wait_entered(1))
        .await
        .expect("one actual writer execution reaches the gate");

    let conflict_response = post(server.address, conflict("inflight")).await;
    assert_eq!(conflict_response.status, 409);
    let while_pending = get(server.address).await;
    assert_eq!(while_pending.json()["game"]["wire"], "2");
    assert_eq!(while_pending.json()["game"]["lifetime_clips"], "0");

    gate.release();
    let mut responses = Vec::new();
    for waiter in waiters {
        responses.push(timeout(TEST_TIMEOUT, waiter).await.unwrap().unwrap());
    }
    assert_eq!(responses[0].status, 200);
    assert!(responses.windows(2).all(|pair| pair[0] == pair[1]));
    let first = responses[0].clone();
    assert_eq!(first.json()["revision"], 1);
    let after = get(server.address).await;
    assert_eq!(after.json()["game"]["wire"], "1");
    assert_eq!(after.json()["game"]["lifetime_clips"], "1");

    clock.advance(Duration::from_millis(10));
    timeout(TEST_TIMEOUT, async {
        loop {
            if server.handle.view().game.clock.update_count() == 1 {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    assert_eq!(post(server.address, command("inflight")).await, first);
    assert_eq!(post(server.address, conflict("inflight")).await.status, 409);
    assert_eq!(
        post(server.address, command("other-legal")).await.status,
        200
    );
    let final_view = server.handle.view();
    assert_eq!(final_view.game.pro.wire.to_string(), "0");
    assert_eq!(final_view.game.pro.lifetime_clips.to_string(), "2");
    assert_eq!(final_view.revision, 3);
    server.stop().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn final_stock_contention_and_rule_rejection_both_replay_first_terminal_results() {
    let gate = Arc::new(CommandTestGate::default());
    let clock = Arc::new(TestClock::new());
    let mut state = state_with_wire("1");
    state.pro.funds = Amount::zero();
    let server = TestServer::start(state, Arc::clone(&gate), clock);
    let a = tokio::spawn(post(server.address, command("winner")));
    timeout(TEST_TIMEOUT, gate.wait_entered(1)).await.unwrap();
    let b = tokio::spawn(post(server.address, command("one-stock")));
    let a_retry = tokio::spawn(post(server.address, command("winner")));
    gate.release();

    let a = timeout(TEST_TIMEOUT, a).await.unwrap().unwrap();
    let b = timeout(TEST_TIMEOUT, b).await.unwrap().unwrap();
    let a_retry = timeout(TEST_TIMEOUT, a_retry).await.unwrap().unwrap();
    assert_eq!(a.status, 200);
    assert_eq!(a_retry, a);
    assert_eq!(b.status, 422);
    assert_eq!(b.json()["status"], "rule_rejected");
    assert_eq!(b.json()["reason"], "insufficient_wire");
    assert_eq!(b.json()["revision"], 1);
    assert_eq!(post(server.address, command("one-stock")).await, b);
    assert_eq!(
        post(server.address, conflict("one-stock")).await.status,
        409
    );

    let new_rejection = post(server.address, command("another-rejection")).await;
    assert_eq!(
        new_rejection.status, 422,
        "a different ID is independently serviced"
    );
    assert_eq!(
        post(server.address, command("another-rejection")).await,
        new_rejection
    );
    assert_eq!(
        post(server.address, command("winner")).await,
        a,
        "terminal success replays after the original command would be unaffordable"
    );
    let view = server.handle.view();
    assert_eq!(view.game.pro.wire.to_string(), "0");
    assert_eq!(view.game.pro.lifetime_clips.to_string(), "1");
    assert_eq!(view.game.pro.unsold_clips.to_string(), "1");
    assert_eq!(view.game.pro.unused_clips.to_string(), "1");
    assert_eq!(view.game.pro.funds.to_string(), "0");
    assert_eq!(view.revision, 1);
    server.stop().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn accepted_socket_disconnect_still_completes_once_and_retry_gets_terminal_result() {
    let (server, gate, _clock) = fixture();
    let address = server.address;
    let body = command("disconnect");
    let disconnected = tokio::task::spawn_blocking(move || {
        let mut stream = TcpStream::connect_timeout(&address, TEST_TIMEOUT).unwrap();
        stream.set_write_timeout(Some(TEST_TIMEOUT)).unwrap();
        write!(
            stream,
            "POST /api/game/commands HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        )
        .unwrap();
        stream.write_all(&body).unwrap();
        // Keep the real client connection open until the actual writer gate
        // proves that the typed command was accepted by the runtime queue.
        stream
    })
    .await
    .unwrap();
    timeout(TEST_TIMEOUT, gate.wait_entered(1))
        .await
        .expect("accepted writer operation reaches the real execution gate");
    // Acceptance is now established independently of socket write completion.
    // Disconnect before starting the retry and before releasing the writer.
    drop(disconnected);

    let retry = tokio::spawn(post(server.address, command("disconnect")));
    assert!(
        timeout(Duration::from_millis(100), gate.wait_entered(2))
            .await
            .is_err(),
        "a retry coalesces rather than enqueueing a second writer operation"
    );
    gate.release();
    let first_observed = timeout(TEST_TIMEOUT, retry).await.unwrap().unwrap();
    assert_eq!(first_observed.status, 200);
    assert_eq!(first_observed.json()["revision"], 1);
    assert_eq!(
        post(server.address, command("disconnect")).await,
        first_observed
    );
    let view = server.handle.view();
    assert_eq!(view.game.pro.wire.to_string(), "1");
    assert_eq!(view.game.pro.lifetime_clips.to_string(), "1");
    assert_eq!(view.game.pro.unsold_clips.to_string(), "1");
    assert_eq!(view.game.pro.unused_clips.to_string(), "1");
    assert_eq!(view.revision, 1);
    server.stop().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn production_serve_drains_21_accepted_disconnected_commands_before_return() {
    let gate = Arc::new(CommandTestGate::default());
    let clock = Arc::new(TestClock::new());
    let mut server = TestServer::start(state_with_wire("1000"), Arc::clone(&gate), clock);
    for index in 0..21 {
        disconnect_after_registration(&server, &format!("accepted-{index}"), index + 1).await;
    }
    timeout(TEST_TIMEOUT, gate.wait_entered(1))
        .await
        .expect("one accepted command is local pending at the real writer");
    let active_stream = connect_active_stream(server.address);
    assert_eq!(server.state.retry.registered_count(), 21);
    assert_eq!(server.state.retry.tracked_count(), 21);
    let state = server.state.clone();
    let handle = server.handle.clone();

    // Exercise the exact serve_with_state path used by public serve, including
    // runtime admission close and the final accepted-publication join.
    server.initiate_shutdown();
    server.wait_shutdown_requested().await;
    gate.release();
    server.wait_stopped().await;
    let active_stream = active_stream;
    let mut terminal_sse = Vec::new();
    active_stream
        .take(64 * 1024)
        .read_to_end(&mut terminal_sse)
        .expect("active SSE reaches EOF during accepted-command drain");
    assert!(
        terminal_sse
            .windows(b"game_view".len())
            .any(|window| window == b"game_view")
    );

    let outcomes: Vec<_> = (0..21)
        .map(|index| {
            let id = format!("accepted-{index}");
            let (status, body) = state
                .retry
                .terminal_status_body(&id)
                .unwrap_or_else(|| panic!("{id} published before serve returned"));
            (index, status, body)
        })
        .collect();
    for (index, status, body) in outcomes {
        assert_eq!(status, 200, "accepted command {index} must not be lost");
        assert_eq!(
            String::from_utf8(body).unwrap(),
            format!("{{\"status\":\"applied\",\"revision\":{}}}", index + 1)
        );
    }
    assert_eq!(state.retry.registered_count(), 21);
    assert_eq!(
        state.retry.tracked_count(),
        0,
        "publication tasks are joined"
    );
    let first = state.retry.terminal_status_body("accepted-0").unwrap();
    assert_eq!(state.retry.terminal_status_body("accepted-0"), Some(first));
    let view = handle.view();
    assert_eq!(view.revision, 21);
    assert_eq!(view.game.pro.wire.to_string(), "979");
    assert_eq!(view.game.pro.lifetime_clips.to_string(), "21");
    assert_eq!(view.game.pro.unsold_clips.to_string(), "21");
    assert_eq!(view.game.pro.unused_clips.to_string(), "21");
    assert!(view.process.command_batches >= 2);
    assert_eq!(view.process.max_commands_in_turn, 16);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn queue_full_503_does_not_bind_key_and_tracked_drain_allows_later_success() {
    let gate = Arc::new(CommandTestGate::default());
    let clock = Arc::new(TestClock::new());
    let server = TestServer::start(state_with_wire("1000"), Arc::clone(&gate), clock);
    let running = tokio::spawn(post(server.address, command("running")));
    timeout(TEST_TIMEOUT, gate.wait_entered(1)).await.unwrap();
    wait_for_registration(&server.state, 1).await;

    let queued: Vec<_> = (0..crate::runtime::COMMAND_QUEUE_CAPACITY)
        .map(|index| tokio::spawn(post(server.address, command(&format!("queued-{index}")))))
        .collect();
    wait_for_registration(&server.state, 1 + crate::runtime::COMMAND_QUEUE_CAPACITY).await;
    let overflow = post(server.address, command("overflow-key")).await;
    assert_eq!(overflow.status, 503);
    assert_eq!(
        overflow.json(),
        json!({"status":"unavailable", "reason":"queue_full"})
    );
    assert!(
        server
            .state
            .retry
            .terminal_status_body("overflow-key")
            .is_none(),
        "pre-acceptance failure must not reserve a retry entry"
    );

    gate.release();
    assert_eq!(
        timeout(TEST_TIMEOUT, running)
            .await
            .unwrap()
            .unwrap()
            .status,
        200
    );
    for response in queued {
        assert_eq!(
            timeout(TEST_TIMEOUT, response)
                .await
                .unwrap()
                .unwrap()
                .status,
            200
        );
    }
    let rebound = post(server.address, command("overflow-key")).await;
    assert_eq!(rebound.status, 200);
    assert_eq!(post(server.address, command("overflow-key")).await, rebound);
    wait_for_revision(&server.handle, 66).await;
    let view = server.handle.view();
    assert_eq!(view.game.pro.wire.to_string(), "934");
    assert_eq!(view.game.pro.lifetime_clips.to_string(), "66");
    assert_eq!(view.game.pro.unused_clips.to_string(), "66");
    server.stop().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn health_routes_expose_typed_failures_without_mutating_or_stopping_the_world() {
    let gate = Arc::new(CommandTestGate::default());
    gate.release();
    let clock = Arc::new(TestClock::new());
    let health = PersistenceHealth::new(Duration::from_secs(30), 0, 0);
    let server = TestServer::start_with_health(
        state_with_wire("2"),
        Arc::clone(&gate),
        Arc::clone(&clock),
        health.clone(),
    );
    let live = get(server.address).await;
    assert_eq!(live.status, 200);
    let live = request(server.address, "GET", "/api/health/live", Vec::new()).await;
    assert_eq!(live.status, 200);
    assert_eq!(live.body, br#"{"status":"ok"}"#);

    let ready = request(server.address, "GET", "/api/health/ready", Vec::new()).await;
    assert_eq!(ready.status, 200);
    let ready_json = ready.json();
    let mut fields = ready_json
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect::<Vec<_>>();
    fields.sort_unstable();
    assert_eq!(
        fields,
        [
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
        ]
    );
    assert_eq!(ready_json["phase"], "ready");
    assert_eq!(ready_json["last_committed_revision"], 0);
    assert_eq!(ready_json["last_committed_sequence"], 0);
    assert_eq!(ready_json["latest_captured_revision"], 0);
    assert_eq!(ready_json["pending_snapshot_count"], 0);
    assert_eq!(ready_json["last_failure_code"], Value::Null);
    assert!(!ready.body.is_empty());
    let printed = String::from_utf8(ready.body).unwrap();
    for forbidden in [
        "SELECT",
        "INSERT",
        "sqlite3",
        "rng_state",
        "payload",
        "retry",
    ] {
        assert!(!printed.contains(forbidden));
    }

    // A coalesced pending snapshot is distinct from the one in-flight write.
    health.captured(1, 1, 0);
    assert_eq!(
        request(server.address, "GET", "/api/health/ready", Vec::new())
            .await
            .json()["pending_snapshot_count"],
        1
    );
    health.pending_taken();
    health.write_started(1, false);
    let saving = request(server.address, "GET", "/api/health/ready", Vec::new())
        .await
        .json();
    assert_eq!(saving["pending_snapshot_count"], 0);
    assert_eq!(saving["write_in_progress"], true);
    health.write_failed(PersistenceFailure::DatabaseBusy, true, 2);
    let failed = request(server.address, "GET", "/api/health/ready", Vec::new()).await;
    assert_eq!(failed.status, 503);
    let failed = failed.json();
    assert_eq!(failed["phase"], "retrying");
    assert_eq!(failed["ready"], false);
    assert_eq!(failed["live"], true);
    assert_eq!(failed["current_attempt"], 2);
    assert_eq!(failed["last_failure_code"], "database_busy");
    assert_eq!(failed["last_committed_revision"], 0);
    assert_eq!(failed["latest_captured_revision"], 1);

    let applied = post(server.address, command("health-does-not-stop-world")).await;
    assert_eq!(applied.status, 200);
    clock.advance(Duration::from_millis(10));
    timeout(TEST_TIMEOUT, async {
        loop {
            if server.handle.view().game.clock.update_count() == 1 {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    let live_view = server.handle.view();
    assert_eq!(live_view.game.pro.wire.to_string(), "1");
    assert_eq!(live_view.game.pro.lifetime_clips.to_string(), "1");
    assert!(live_view.process.lag_debt_nanos == 0);

    health.committed(1, 1, 1);
    let healthy = request(server.address, "GET", "/api/health/ready", Vec::new()).await;
    assert_eq!(healthy.status, 200);
    let healthy = healthy.json();
    assert_eq!(healthy["current_attempt"], 0);
    assert_eq!(healthy["consecutive_failures"], 0);
    assert_eq!(healthy["last_failure_code"], Value::Null);
    health.observe(6_001);
    assert!(!health.snapshot().snapshot_overdue);
    health.observe(6_002);
    let overdue = request(server.address, "GET", "/api/health/ready", Vec::new()).await;
    assert_eq!(overdue.status, 503);
    assert_eq!(overdue.json()["snapshot_overdue"], true);
    health.committed(2, 2, 6_002);
    assert_eq!(
        request(server.address, "GET", "/api/health/ready", Vec::new())
            .await
            .status,
        200
    );

    let before = server.handle.view();
    for path in ["/api/health/live", "/api/health/ready"] {
        let response = request(
            server.address,
            "POST",
            path,
            br#"{"actor":"other-world","game_id":"forbidden"}"#.to_vec(),
        )
        .await;
        assert_eq!(response.status, 405);
    }
    let after = server.handle.view();
    assert_eq!(after.revision, before.revision);
    assert_eq!(after.game.pro, before.game.pro);
    assert_eq!(after.game.clock, before.game.clock);
    assert_eq!(after.game.rng_state_hex(), before.game.rng_state_hex());
    assert!(live_view.process.lag_debt_nanos == 0);
    server.stop().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn real_view_preserves_huge_tiny_and_zero_amounts_without_exposing_internal_state() {
    let gate = Arc::new(CommandTestGate::default());
    gate.release();
    let clock = Arc::new(TestClock::new());
    let mut state = GameState::fresh(GameRng::from_test_seed([11_u8; 32]));
    state.pro.funds = Amount::parse("0.000000000000000001").unwrap();
    state.pro.price_per_clip = Amount::parse("9007199254740993").unwrap();
    state.pro.wire_quote =
        Amount::parse("30000000000000000000000000000000000000000000000000000001").unwrap();
    let server = TestServer::start(state, gate, clock);
    let rng_before = server.handle.view().game.rng_state_hex();
    let run_before = server.handle.view().run_id.clone();

    let first = get(server.address).await;
    assert_eq!(first.status, 200);
    let raw = first.json();
    assert_eq!(raw["game"]["funds"], "0.000000000000000001");
    assert_eq!(raw["game"]["price_per_clip"], "9007199254740993");
    assert_eq!(
        raw["game"]["wire_quote"],
        "30000000000000000000000000000000000000000000000000000001"
    );
    assert_eq!(raw["game"]["lifetime_clips"], "0");
    assert_eq!(raw["game"]["unsold_clips"], "0");
    assert_eq!(raw["game"]["unused_clips"], "0");
    assert!(raw.get("rng").is_none());
    assert!(raw.get("retry").is_none());
    assert!(raw.get("process").is_none());
    assert!(raw.get("database_path").is_none());
    assert!(raw["schema_version"].is_u64());
    assert!(raw["revision"].is_u64());
    assert!(raw["clock"]["update_count"].is_u64());
    for amount in ["funds", "price_per_clip", "wire_quote", "lifetime_clips"] {
        assert!(raw["game"][amount].is_string());
    }

    let second = get(server.address).await;
    assert_eq!(second, first, "fake-clock pure views are byte-stable");
    let after = server.handle.view();
    assert_eq!(after.game.rng_state_hex(), rng_before);
    assert_eq!(after.run_id, run_before);
    assert_eq!(after.revision, 0);
    assert_eq!(after.game.pro.lifetime_clips.to_string(), "0");
    server.stop().await;
}
