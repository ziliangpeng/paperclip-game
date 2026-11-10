use paperclip_game::api::{GameView, serve};
use paperclip_game::game::amount::Amount;
use paperclip_game::game::state::GameState;
use paperclip_game::health::PersistenceHealth;
use paperclip_game::runtime::{GameRuntime, ProcessStatus, RuntimeHandle, RuntimeView};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::io::{BufReader, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use tokio::sync::oneshot;

const BOUND: Duration = Duration::from_secs(5);
const MAX_EVENT_BYTES: usize = 64 * 1024;

struct TestServer {
    address: SocketAddr,
    handle: RuntimeHandle,
    initial_game: GameState,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<thread::JoinHandle<Result<(), String>>>,
}

impl TestServer {
    fn start(configure: impl FnOnce(&mut GameState) + Send + 'static) -> Self {
        let (address_tx, address_rx) = mpsc::sync_channel(0);
        let (shutdown_tx, shutdown_rx) = oneshot::channel();
        let server = thread::spawn(move || {
            let executor = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2)
                .enable_all()
                .build()
                .map_err(|_| "test Tokio runtime failed".to_owned())?;
            executor.block_on(async {
                let seed = GameRuntime::start().map_err(|_| "seed game failed".to_owned())?;
                let mut state = seed.handle().view().game;
                seed.shutdown()
                    .await
                    .map_err(|_| "seed game shutdown failed".to_owned())?;
                configure(&mut state);
                let initial_game = state.clone();
                let game = GameRuntime::start_from_snapshot(state, 0)
                    .map_err(|_| "test game failed".to_owned())?;
                let handle = game.handle();
                let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
                    .await
                    .map_err(|_| "test listener failed".to_owned())?;
                let address = listener.local_addr().unwrap();
                let health = PersistenceHealth::unconfigured_for_testing(Duration::from_secs(30));
                address_tx
                    .send((address, handle.clone(), initial_game))
                    .map_err(|_| "test readiness receiver stopped".to_owned())?;
                serve(listener, game, health, async {
                    let _ = shutdown_rx.await;
                })
                .await
                .map_err(|error| error.to_string())
            })
        });
        let (address, handle, initial_game) = address_rx
            .recv_timeout(BOUND)
            .expect("bounded real-server readiness");
        Self {
            address,
            handle,
            initial_game,
            shutdown: Some(shutdown_tx),
            thread: Some(server),
        }
    }

    fn stop(mut self) {
        self.shutdown_inner().expect("real server stops cleanly");
    }

    fn shutdown_inner(&mut self) -> Result<(), String> {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
        match self.thread.take() {
            Some(handle) => handle.join().map_err(|_| "server panicked".to_owned())?,
            None => Ok(()),
        }
    }
}

impl Drop for TestServer {
    fn drop(&mut self) {
        let _ = self.shutdown_inner();
    }
}

fn line(reader: &mut BufReader<TcpStream>) -> std::io::Result<Option<String>> {
    let mut bytes = Vec::new();
    let mut byte = [0_u8; 1];
    while bytes.len() < 16 * 1024 {
        match reader.read(&mut byte)? {
            0 => return Ok(None),
            1 => {
                bytes.push(byte[0]);
                if byte[0] == b'\n' {
                    return Ok(Some(String::from_utf8(bytes).unwrap()));
                }
            }
            _ => unreachable!(),
        }
    }
    panic!("bounded HTTP/SSE line exceeded 16 KiB")
}

#[derive(Debug)]
struct SseEvent {
    name: String,
    id: String,
    view: GameView,
    raw: Value,
}

struct SseClient {
    reader: BufReader<TcpStream>,
    pending: Vec<u8>,
    ended: bool,
}

impl SseClient {
    fn connect(address: SocketAddr, last_event_id: Option<&str>) -> Self {
        let mut stream = TcpStream::connect_timeout(&address, BOUND).unwrap();
        stream.set_read_timeout(Some(BOUND)).unwrap();
        stream.set_write_timeout(Some(BOUND)).unwrap();
        let last = last_event_id
            .map(|value| format!("Last-Event-ID: {value}\r\n"))
            .unwrap_or_default();
        write!(
            stream,
            "GET /api/game/stream HTTP/1.1\r\nHost: {address}\r\nAccept: text/event-stream\r\n{last}\r\n"
        )
        .unwrap();
        let mut reader = BufReader::new(stream);
        let status = line(&mut reader).unwrap().unwrap();
        assert_eq!(status, "HTTP/1.1 200 OK\r\n");
        let mut headers = BTreeMap::new();
        loop {
            let value = line(&mut reader).unwrap().unwrap();
            if value == "\r\n" {
                break;
            }
            let (name, value) = value.split_once(':').unwrap();
            headers.insert(name.to_ascii_lowercase(), value.trim().to_owned());
        }
        assert_eq!(headers["content-type"], "text/event-stream");
        assert_eq!(headers["cache-control"], "no-store, no-transform");
        assert_eq!(headers["transfer-encoding"], "chunked");
        Self {
            reader,
            pending: Vec::new(),
            ended: false,
        }
    }

    fn next(&mut self) -> Option<SseEvent> {
        loop {
            if let Some(split) = self.pending.windows(2).position(|window| window == b"\n\n") {
                let raw: Vec<_> = self.pending.drain(..split + 2).collect();
                return Some(Self::decode(&raw));
            }
            if self.ended {
                assert!(self.pending.is_empty(), "no truncated terminal SSE frame");
                return None;
            }
            let size_line = line(&mut self.reader).unwrap()?;
            let size = usize::from_str_radix(size_line.trim(), 16).unwrap();
            if size == 0 {
                self.ended = true;
                loop {
                    let trailer = line(&mut self.reader).unwrap();
                    if trailer.is_none() || trailer.as_deref() == Some("\r\n") {
                        break;
                    }
                }
                continue;
            }
            assert!(
                self.pending.len() + size <= MAX_EVENT_BYTES,
                "each test accumulator is explicitly bounded"
            );
            let mut chunk = vec![0; size];
            self.reader.read_exact(&mut chunk).unwrap();
            self.pending.extend_from_slice(&chunk);
            let mut ending = [0_u8; 2];
            self.reader.read_exact(&mut ending).unwrap();
            assert_eq!(&ending, b"\r\n");
        }
    }

    fn decode(raw: &[u8]) -> SseEvent {
        let text = std::str::from_utf8(raw).unwrap();
        let mut name = None;
        let mut id = None;
        let mut data = Vec::new();
        for line in text.lines() {
            if let Some(value) = line.strip_prefix("event:") {
                name = Some(value.trim_start().to_owned());
            } else if let Some(value) = line.strip_prefix("id:") {
                id = Some(value.trim_start().to_owned());
            } else if let Some(value) = line.strip_prefix("data:") {
                data.push(value.strip_prefix(' ').unwrap_or(value));
            }
        }
        let data = data.join("\n");
        let raw: Value = serde_json::from_str(&data).expect("one complete JSON frame");
        let view: GameView = serde_json::from_str(&data).expect("complete typed GameView");
        SseEvent {
            name: name.expect("named full-view event"),
            id: id.expect("run/revision event ID"),
            view,
            raw,
        }
    }

    fn next_revision(&mut self, minimum: u64) -> SseEvent {
        for _ in 0..64 {
            let event = self.next().expect("bounded live stream update");
            if event.view.revision.get() >= minimum {
                return event;
            }
        }
        panic!("bounded SSE observation did not reach revision {minimum}")
    }
}

impl Drop for SseClient {
    fn drop(&mut self) {
        let _ = self.reader.get_ref().shutdown(Shutdown::Both);
    }
}

fn assert_event(event: &SseEvent) {
    assert_eq!(event.name, "game_view");
    assert_eq!(
        event.id,
        format!("{}:{}", event.view.run_id, event.view.revision.get())
    );
    assert_eq!(event.raw["schema_version"], 1);
    for forbidden in ["process", "rng", "rng_state", "persistence", "retry"] {
        assert!(
            event.raw.get(forbidden).is_none(),
            "no {forbidden} interior"
        );
    }
    assert!(event.view.revision.get() <= 9_007_199_254_740_991);
    assert!(event.view.clock.update_count.get() <= 9_007_199_254_740_991);
}

fn request(address: SocketAddr, method: &str, path: &str, body: &[u8]) -> (u16, Vec<u8>) {
    let mut stream = TcpStream::connect_timeout(&address, BOUND).unwrap();
    stream.set_read_timeout(Some(BOUND)).unwrap();
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )
    .unwrap();
    stream.write_all(body).unwrap();
    let mut raw = Vec::new();
    stream.take(1024 * 1024).read_to_end(&mut raw).unwrap();
    let split = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .unwrap();
    let headers = std::str::from_utf8(&raw[..split]).unwrap();
    let status = headers.split_whitespace().nth(1).unwrap().parse().unwrap();
    (status, raw[split + 4..].to_vec())
}

fn get(address: SocketAddr) -> GameView {
    let (status, raw) = request(address, "GET", "/api/game/view", &[]);
    assert_eq!(status, 200);
    serde_json::from_slice(&raw).unwrap()
}

fn command_receipt(address: SocketAddr, id: &str) -> (u16, u64) {
    let body = serde_json::to_vec(&json!({
        "command_id": id,
        "type": "make_paperclip",
        "arguments": {}
    }))
    .unwrap();
    let (status, raw) = request(address, "POST", "/api/game/commands", &body);
    if status != 200 {
        return (status, 0);
    }
    let result: Value = serde_json::from_slice(&raw).unwrap();
    assert_eq!(result["status"], "applied");
    let revision = result["revision"].as_u64().unwrap();
    assert!(revision <= 9_007_199_254_740_991);
    (status, revision)
}

fn command(address: SocketAddr, id: &str) -> u16 {
    command_receipt(address, id).0
}

fn wait_for_updates(address: SocketAddr, minimum: u64) {
    let deadline = std::time::Instant::now() + BOUND;
    while get(address).clock.update_count.get() < minimum {
        assert!(
            std::time::Instant::now() < deadline,
            "bounded backlog setup"
        );
        thread::yield_now();
    }
}

fn extreme_state(state: &mut GameState) {
    state.pro.funds = Amount::parse("-41117.99").unwrap();
    state.pro.price_per_clip = Amount::parse("0.000000000000000001").unwrap();
    state.pro.wire_quote =
        Amount::parse("30000000000000000000000000000000000000000000000000000001").unwrap();
    state.pro.marketing_level = Amount::parse("9000").unwrap().integral().unwrap();
    state.pro.demand_boost = Amount::zero();
    paperclip_game::game::economy::refresh_demand(&mut state.pro).unwrap();
}

fn assert_one_command_effect(view: &GameView) {
    assert_eq!(view.game.wire.to_string(), "999");
    for clips in [
        &view.game.lifetime_clips,
        &view.game.unsold_clips,
        &view.game.unused_clips,
    ] {
        assert_eq!(clips.to_string(), "1");
    }
}

fn assert_extremes(view: &GameView) {
    assert_eq!(view.game.funds.to_string(), "-41117.99");
    assert_eq!(view.game.price_per_clip.to_string(), "0.000000000000000001");
    assert_eq!(view.game.marketing_level.to_string(), "9000");
    assert_eq!(view.game.demand.to_string(), "0");
    let expected_cost = Amount::from_i128(100)
        .multiply_integer(&num_bigint::BigInt::from(2u8).pow(8_999))
        .to_string();
    assert_eq!(view.game.marketing_cost.to_string(), expected_cost);
    assert_eq!(
        view.game.wire_quote.to_string(),
        "30000000000000000000000000000000000000000000000000000001"
    );
    assert_eq!(view.game.lifetime_clips.to_string(), "0");
    assert_eq!(view.game.unsold_clips.to_string(), "0");
    assert_eq!(view.game.unused_clips.to_string(), "0");
}

#[test]
fn real_http_initial_updates_reconnect_last_event_id_and_exact_get_parity() {
    // SSE-DISCONNECT-RECONNECT: browser-like and structured-Agent real clients.
    let server = TestServer::start(extreme_state);
    let mut browser = SseClient::connect(server.address, None);
    let initial = browser.next().unwrap();
    assert_event(&initial);
    assert_extremes(&initial.view);
    let current_get = get(server.address);
    assert_eq!(current_get.run_id, initial.view.run_id);
    assert_extremes(&current_get);

    let mut agent = SseClient::connect(server.address, Some("not-a-retained-cursor"));
    let agent_initial = agent.next().unwrap();
    assert_event(&agent_initial);
    assert_extremes(&agent_initial.view);
    wait_for_updates(
        server.address,
        initial
            .view
            .clock
            .update_count
            .get()
            .max(agent_initial.view.clock.update_count.get())
            + 5,
    );
    let (status, command_revision) = command_receipt(server.address, "sse-one");
    assert_eq!(status, 200);
    let older_browser = browser.next().unwrap();
    assert_event(&older_browser);
    assert_eq!(older_browser.view.run_id, initial.view.run_id);
    assert!(older_browser.view.revision.get() > initial.view.revision.get());
    assert!(older_browser.view.revision.get() < command_revision);
    assert_extremes(&older_browser.view);
    let older_agent = agent.next().unwrap();
    assert_event(&older_agent);
    assert_eq!(older_agent.view.run_id, agent_initial.view.run_id);
    assert!(older_agent.view.revision.get() < command_revision);
    assert_extremes(&older_agent.view);

    // Writer responses precede post-turn watch publication. The older full
    // views above satisfy the rejected baseline+1 barrier, while only a frame
    // at/after the actual response revision proves this command's effects.
    let updated = browser.next_revision(command_revision);
    assert_event(&updated);
    assert_eq!(updated.view.run_id, initial.view.run_id);
    assert_one_command_effect(&updated.view);
    assert_eq!(updated.view.game.funds.to_string(), "-41117.99");
    let agent_updated = agent.next_revision(command_revision);
    assert_event(&agent_updated);
    assert_eq!(agent_updated.view.run_id, initial.view.run_id);
    assert_one_command_effect(&agent_updated.view);
    let get_after = get(server.address);
    assert_eq!(get_after.game, updated.view.game);

    let run = initial.view.run_id.clone();
    let old_id = initial.id.clone();
    drop(browser);
    drop(agent);
    assert_eq!(command(server.address, "sse-disconnected"), 200);
    for last_event_id in [None, Some(old_id.as_str()), Some("9007199254740993:broken")] {
        let mut reconnected = SseClient::connect(server.address, last_event_id);
        let baseline = reconnected.next().unwrap();
        assert_event(&baseline);
        assert_eq!(baseline.view.run_id, run);
        assert!(baseline.view.revision.get() >= updated.view.revision.get());
        assert_eq!(baseline.view.game.lifetime_clips.to_string(), "2");
        assert!(baseline.view.revision.get() != 0);
        assert!(
            reconnected.next().is_some(),
            "later live frames remain valid"
        );
    }

    let (status, javascript) = request(server.address, "GET", "/static/stream.js", &[]);
    assert_eq!(status, 200);
    let javascript = String::from_utf8(javascript).unwrap();
    assert!(javascript.contains("export class GameViewSynchronizer"));
    server.stop();
}

#[test]
fn delayed_real_observer_gets_complete_coalesced_frames_or_disconnect_then_baseline() {
    // SSE-DISCONNECT-RECONNECT / SSE-SAME-RUN-ORDERING: actual delayed socket.
    let server = TestServer::start(|state| {
        state.pro.wire = Amount::parse("1000").unwrap().nonnegative().unwrap();
    });
    let run = server.handle.view().run_id.clone();
    let mut slow = SseClient::connect(server.address, None);
    let initial = slow.next().unwrap();
    for index in 0..60 {
        assert_eq!(command(server.address, &format!("rapid-{index}")), 200);
    }
    thread::sleep(Duration::from_millis(25));
    let current = get(server.address);
    let mut previous = initial.view.revision.get();
    let mut frames = 0;
    while frames < 64 {
        match slow.next() {
            Some(event) => {
                assert_event(&event);
                assert!(event.view.revision.get() > previous);
                assert_eq!(event.view.run_id, run);
                previous = event.view.revision.get();
                frames += 1;
                if previous >= current.revision.get() {
                    break;
                }
            }
            None => break,
        }
    }
    assert!(frames <= 64, "bounded test observation");

    let mut reconnected = SseClient::connect(server.address, Some(&current.run_id));
    let baseline = reconnected.next().unwrap();
    assert_eq!(baseline.view.run_id, run);
    assert!(baseline.view.revision.get() >= current.revision.get());
    assert_eq!(baseline.view.game.lifetime_clips.to_string(), "60");
    assert_eq!(command(server.address, "writer-after-slow-observer"), 200);
    assert_eq!(get(server.address).game.lifetime_clips.to_string(), "61");
    server.stop();
}

#[test]
fn zero_client_progress_then_stream_matches_serial_engine_expectation() {
    // RT-NO-CLIENTS-CONTINUOUS: no clients exist during authoritative progress.
    let server = TestServer::start(|_| {});
    thread::sleep(Duration::from_millis(60));
    assert_eq!(server.handle.view().process.applied_commands, 0);
    let mut attached = SseClient::connect(server.address, None);
    let observed = attached.next().unwrap();
    assert!(observed.view.clock.update_count.get() > 0);
    assert_eq!(observed.view.revision, observed.view.clock.update_count);

    let expected = GameView::from_runtime(&RuntimeView {
        game: server.initial_game.clone(),
        revision: 0,
        run_id: observed.view.run_id.clone(),
        process: ProcessStatus::default(),
    })
    .unwrap();
    assert_eq!(observed.view.game, expected.game);
    let updates = observed.view.clock.update_count.get();
    assert_eq!(observed.view.clock.fast_phase, (updates % 10) as u8);
    assert_eq!(observed.view.clock.second_phase, (updates % 100) as u8);
    assert_eq!(observed.view.clock.slow_phase, (updates % 250) as u16);
    assert_eq!(observed.view.clock.combat_pulses.get(), updates * 5 / 8);
    assert_eq!(
        u128::from(observed.view.clock.combat_remainder_nanos),
        (u128::from(updates) * 10_000_000) % 16_000_000
    );
    server.stop();
    // This is transport independence at the current stage, not M1-G03 evidence.
}

#[test]
fn active_stream_does_not_prevent_bounded_true_server_shutdown() {
    let server = TestServer::start(|_| {});
    let handle = server.handle.clone();
    let mut active = SseClient::connect(server.address, None);
    let initial = active.next().unwrap();
    let revision_before_stop = handle.view().revision;
    server.stop();
    assert!(handle.view().revision >= revision_before_stop);
    let expected_end = initial.view.run_id;
    while let Some(event) = active.next() {
        assert_eq!(event.view.run_id, expected_end);
    }
}

#[cfg(unix)]
mod recovery {
    use super::*;
    use paperclip_game::view_sync::{ViewDecision, ViewSynchronizer};
    use std::path::{Path, PathBuf};
    use std::process::{Child, Command, Stdio};
    use std::time::{SystemTime, UNIX_EPOCH};

    struct TestDatabase(PathBuf);

    impl TestDatabase {
        fn new() -> Self {
            let unique = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "paperclip-game-sse-recovery-{}-{unique}.sqlite3",
                std::process::id()
            ));
            assert!(!path.exists());
            Self(path)
        }
    }

    impl Drop for TestDatabase {
        fn drop(&mut self) {
            for suffix in ["", "-journal", "-shm", "-wal"] {
                let mut path = self.0.as_os_str().to_os_string();
                path.push(suffix);
                let _ = std::fs::remove_file(path);
            }
        }
    }

    struct TestProcess {
        child: Child,
        address: SocketAddr,
    }

    impl TestProcess {
        fn start(database: &Path) -> Self {
            let reservation = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let address = reservation.local_addr().unwrap();
            drop(reservation);
            let mut child = Command::new(env!("CARGO_BIN_EXE_paperclip-game"))
                .args([
                    "--listen-addr",
                    &address.to_string(),
                    "--database-path",
                    database.to_str().unwrap(),
                ])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            let deadline = std::time::Instant::now() + BOUND;
            loop {
                assert!(child.try_wait().unwrap().is_none(), "server stays running");
                if TcpStream::connect_timeout(&address, Duration::from_millis(20)).is_ok() {
                    break;
                }
                assert!(
                    std::time::Instant::now() < deadline,
                    "bounded process startup"
                );
                thread::sleep(Duration::from_millis(10));
            }
            Self { child, address }
        }

        fn crash(&mut self) {
            self.child.kill().unwrap();
            assert!(!self.child.wait().unwrap().success());
        }

        fn stop(&mut self) {
            if self.child.try_wait().unwrap().is_none() {
                let status = Command::new("kill")
                    .args(["-TERM", &self.child.id().to_string()])
                    .status()
                    .unwrap();
                assert!(status.success());
            }
            let deadline = std::time::Instant::now() + BOUND;
            loop {
                if let Some(status) = self.child.try_wait().unwrap() {
                    assert!(status.success(), "graceful process exit");
                    return;
                }
                assert!(std::time::Instant::now() < deadline, "bounded SIGTERM stop");
                thread::sleep(Duration::from_millis(10));
            }
        }
    }

    impl Drop for TestProcess {
        fn drop(&mut self) {
            if self.child.try_wait().unwrap().is_none() {
                let _ = self.child.kill();
            }
            let _ = self.child.wait();
        }
    }

    #[test]
    fn real_crash_recovery_races_actual_old_stream_and_get_against_new_baseline() {
        // SSE-RECOVERED-RUN-RESYNC: real SQLite, SIGKILL, restart, and resend.
        let database = TestDatabase::new();
        let mut old = TestProcess::start(&database.0);
        let mut old_stream = SseClient::connect(old.address, None);
        let old_initial = old_stream.next().unwrap();
        let mut client = ViewSynchronizer::default();
        let old_generation = client.open_stream();
        assert_eq!(
            client.accept_stream_initial(old_generation, old_initial.view.clone()),
            ViewDecision::AdoptedNewRun
        );
        for index in 0..20 {
            assert_eq!(command(old.address, &format!("recover-retry-{index}")), 200);
        }
        let delayed_get = client.request_view();
        let old_get = get(old.address);
        assert_eq!(old_get.run_id, old_initial.view.run_id);
        assert_eq!(old_get.game.lifetime_clips.to_string(), "20");
        let old_update = old_stream.next_revision(old_get.revision.get() + 1);
        assert_eq!(old_update.view.game.lifetime_clips.to_string(), "20");
        old.crash();

        let mut recovered = TestProcess::start(&database.0);
        let mut new_stream = SseClient::connect(recovered.address, None);
        let new_initial = new_stream.next().unwrap();
        assert_ne!(new_initial.view.run_id, old_initial.view.run_id);
        assert_eq!(new_initial.view.game.lifetime_clips.to_string(), "0");
        assert_eq!(new_initial.view.game.wire.to_string(), "1000");
        assert!(new_initial.view.revision.get() < old_update.view.revision.get());
        let new_generation = client.open_stream();
        assert_eq!(
            client.accept_stream_initial(new_generation, new_initial.view.clone()),
            ViewDecision::AdoptedNewRun
        );

        // These are actual captured pre-crash HTTP/SSE full views, delivered
        // only after the recovered process baseline has been adopted.
        assert_eq!(
            client.accept_stream_update(old_generation, old_update.view.clone()),
            ViewDecision::IgnoredStaleSource
        );
        assert_eq!(
            client.accept_get(delayed_get, old_get),
            ViewDecision::IgnoredStaleSource
        );
        assert_eq!(client.current(), Some(&new_initial.view));
        let presentations = client.presentation_count();
        assert_eq!(
            client.accept_stream_update(new_generation, new_initial.view.clone()),
            ViewDecision::EqualPresentationOnly
        );
        assert_eq!(client.presentation_count(), presentations);

        // No pre-crash retry map is restored. The same logical retry is a new
        // legal intent after current-state synchronization, not exactly-once.
        assert_eq!(command(recovered.address, "recover-retry-19"), 200);
        let reapplied = get(recovered.address);
        assert_eq!(reapplied.run_id, new_initial.view.run_id);
        assert_eq!(reapplied.game.lifetime_clips.to_string(), "1");
        assert_eq!(reapplied.game.wire.to_string(), "999");
        recovered.stop();
        for _ in 0..64 {
            if new_stream.next().is_none() {
                return;
            }
        }
        panic!("active recovered SSE ended within the bounded frame drain");
    }
}

#[test]
fn computational_unlock_sse_get_and_reconnect_share_one_authoritative_transition() {
    let server = TestServer::start(|state| {
        state.pro.lifetime_clips =
            paperclip_game::game::amount::NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.unsold_clips =
            paperclip_game::game::amount::NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.unused_clips =
            paperclip_game::game::amount::NonNegativeAmount::from_i128(1_999).unwrap();
        state.pro.wire = paperclip_game::game::amount::NonNegativeAmount::from_i128(1).unwrap();
        state.pro.funds = Amount::from_i128(100);
    });
    let mut first_stream = SseClient::connect(server.address, None);
    let initial = first_stream.next().unwrap();
    assert_event(&initial);
    assert_eq!(initial.view.game.lifetime_clips.to_string(), "1999");
    assert!(initial.view.game.computing_hidden && initial.view.game.projects_hidden);

    let (status, crossing_revision) = command_receipt(server.address, "m2-c01-sse-crossing");
    assert_eq!(status, 200);
    let crossing = first_stream.next_revision(crossing_revision);
    assert_event(&crossing);
    assert_eq!(crossing.view.game.lifetime_clips.to_string(), "2000");
    assert_eq!(crossing.view.game.wire.to_string(), "0");
    assert!(!crossing.view.game.computing_hidden && !crossing.view.game.projects_hidden);
    assert_eq!(crossing.view.game.trust.to_string(), "2");
    assert_eq!(crossing.view.game.processors.to_string(), "1");
    assert_eq!(crossing.view.game.memory.to_string(), "1");
    assert_eq!(
        crossing
            .view
            .game
            .console_messages
            .iter()
            .filter(|message| {
                *message == paperclip_game::game::economy::COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE
            })
            .count(),
        1
    );
    let transition_messages = crossing.view.game.console_messages.clone();
    let transition_event_id = crossing.id.clone();
    drop(first_stream);

    let mut reconnect = SseClient::connect(server.address, Some(&transition_event_id));
    let baseline = reconnect.next().unwrap();
    assert_event(&baseline);
    assert!(!baseline.view.game.computing_hidden && !baseline.view.game.projects_hidden);
    assert_eq!(baseline.view.game.console_messages, transition_messages);
    let current_get = get(server.address);
    assert_eq!(current_get.run_id, baseline.view.run_id);
    assert!(!current_get.game.computing_hidden && !current_get.game.projects_hidden);
    assert_eq!(current_get.game.console_messages, transition_messages);
    assert_eq!(current_get.game.trust, baseline.view.game.trust);
    assert_eq!(current_get.game.processors, baseline.view.game.processors);
    assert_eq!(current_get.game.memory, baseline.view.game.memory);

    // The repeat is rejected at empty Wire and cannot partially mutate or announce.
    let repeat = command_receipt(server.address, "m2-c01-sse-repeat");
    assert_eq!(repeat.0, 422);
    wait_for_updates(server.address, current_get.clock.update_count.get() + 20);
    let later_get = get(server.address);
    assert_eq!(later_get.game.console_messages, transition_messages);
    let later = reconnect.next_revision(later_get.revision.get());
    assert_event(&later);
    assert!(!later.view.game.computing_hidden && !later.view.game.projects_hidden);
    assert_eq!(later.view.game.console_messages, transition_messages);
    assert_eq!(
        later
            .view
            .game
            .console_messages
            .iter()
            .filter(|message| {
                *message == paperclip_game::game::economy::COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE
            })
            .count(),
        1
    );
    server.stop();
}
