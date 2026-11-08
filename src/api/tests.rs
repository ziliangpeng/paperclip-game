use super::*;
use crate::game::amount::Amount;
use crate::game::rng::GameRng;
use crate::game::state::GameState;
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
    shutdown: Option<oneshot::Sender<()>>,
    task: JoinHandle<Result<(), ServerError>>,
}

impl TestServer {
    fn start(state: GameState, gate: Arc<CommandTestGate>, clock: Arc<TestClock>) -> Self {
        let runtime = GameRuntime::start_with_test_gate(clock, state, gate).unwrap();
        let handle = runtime.handle();
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let listener = TcpListener::from_std(listener).unwrap();
        let (shutdown, stopped) = oneshot::channel();
        let task = tokio::spawn(serve(listener, runtime, async {
            let _ = stopped.await;
        }));
        Self {
            address,
            handle,
            shutdown: Some(shutdown),
            task,
        }
    }

    async fn stop(mut self) {
        let _ = self.shutdown.take().unwrap().send(());
        timeout(TEST_TIMEOUT, self.task)
            .await
            .expect("server stops within bound")
            .expect("server task does not panic")
            .expect("runtime and listener stop cleanly");
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
    tokio::task::spawn_blocking(move || {
        let mut stream = TcpStream::connect_timeout(&address, TEST_TIMEOUT).unwrap();
        stream.set_write_timeout(Some(TEST_TIMEOUT)).unwrap();
        write!(
            stream,
            "POST /api/game/commands HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        )
        .unwrap();
        stream.write_all(&body).unwrap();
        // Drop the real socket without reading an HTTP response.
    })
    .await
    .unwrap();
    timeout(TEST_TIMEOUT, gate.wait_entered(1))
        .await
        .expect("accepted writer operation is independent of the disconnected response");

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
