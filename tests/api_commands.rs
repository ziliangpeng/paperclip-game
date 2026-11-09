use paperclip_game::api::{GameView, MAX_COMMAND_BODY_BYTES, MAX_COMMAND_ID_BYTES, serve};
use paperclip_game::game::amount::{Amount, IntegralAmount, NonNegativeAmount};
use paperclip_game::game::state::GameState;
use paperclip_game::health::PersistenceHealth;
use paperclip_game::runtime::GameRuntime;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use tokio::sync::oneshot;

const READINESS: Duration = Duration::from_secs(5);

struct TestServer {
    address: SocketAddr,
    shutdown: Option<oneshot::Sender<()>>,
    thread: Option<thread::JoinHandle<Result<(), String>>>,
}

impl TestServer {
    fn start() -> Self {
        Self::start_with_state(|_| {})
    }

    fn start_with_state(configure: impl FnOnce(&mut GameState) + Send + 'static) -> Self {
        let (address_tx, address_rx) = mpsc::sync_channel(0);
        let (shutdown_tx, shutdown_rx) = oneshot::channel();
        let handle = thread::spawn(move || {
            let runtime = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2)
                .enable_all()
                .build()
                .map_err(|_| "test Tokio runtime failed".to_owned())?;
            runtime.block_on(async {
                let seed = GameRuntime::start().map_err(|_| "test seed game failed".to_owned())?;
                let mut state = seed.handle().view().game;
                seed.shutdown()
                    .await
                    .map_err(|_| "test seed shutdown failed".to_owned())?;
                configure(&mut state);
                let game = GameRuntime::start_from_snapshot(state, 0)
                    .map_err(|_| "test game failed".to_owned())?;
                let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
                    .await
                    .map_err(|_| "test listener failed".to_owned())?;
                let address = listener
                    .local_addr()
                    .map_err(|_| "no test address".to_owned())?;
                address_tx
                    .send(address)
                    .map_err(|_| "test readiness receiver stopped".to_owned())?;
                let health = PersistenceHealth::unconfigured_for_testing(Duration::from_secs(30));
                serve(listener, game, health, async {
                    let _ = shutdown_rx.await;
                })
                .await
                .map_err(|error| error.to_string())
            })
        });
        let address = address_rx
            .recv_timeout(READINESS)
            .expect("bounded real-server readiness");
        Self {
            address,
            shutdown: Some(shutdown_tx),
            thread: Some(handle),
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct HttpResponse {
    status: u16,
    body: Vec<u8>,
}

impl HttpResponse {
    fn json(&self) -> Value {
        serde_json::from_slice(&self.body).expect("actual HTTP JSON body")
    }

    fn view(&self) -> GameView {
        serde_json::from_slice(&self.body).expect("statically typed actual GameView")
    }
}

fn request(address: SocketAddr, method: &str, path: &str, body: &[u8]) -> HttpResponse {
    let mut stream = TcpStream::connect_timeout(&address, READINESS)
        .expect("connect to actual listening server");
    stream.set_read_timeout(Some(READINESS)).unwrap();
    stream.set_write_timeout(Some(READINESS)).unwrap();
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: {address}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )
    .expect("write actual HTTP headers");
    stream.write_all(body).expect("write actual HTTP body");
    let mut raw = Vec::new();
    stream
        .read_to_end(&mut raw)
        .expect("read actual bounded HTTP response");
    let split = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .expect("HTTP header terminator");
    let headers = std::str::from_utf8(&raw[..split]).expect("HTTP headers are ASCII/UTF-8");
    let mut lines = headers.split("\r\n");
    let status = lines
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok())
        .expect("HTTP status line");
    assert!(
        lines.any(|line| line.eq_ignore_ascii_case("connection: close")),
        "test client requested a finite response"
    );
    HttpResponse {
        status,
        body: raw[split + 4..].to_vec(),
    }
}

fn get(address: SocketAddr) -> HttpResponse {
    request(address, "GET", "/api/game/view", &[])
}

fn post(address: SocketAddr, body: impl AsRef<[u8]>) -> HttpResponse {
    request(address, "POST", "/api/game/commands", body.as_ref())
}

fn command(id: &str) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "command_id": id,
        "type": "make_paperclip",
        "arguments": {}
    }))
    .unwrap()
}

fn assert_fresh_view(response: &HttpResponse) -> GameView {
    assert_eq!(response.status, 200);
    let raw = response.json();
    let object = raw.as_object().unwrap();
    assert_eq!(
        object.keys().map(String::as_str).collect::<BTreeSet<_>>(),
        ["clock", "game", "revision", "run_id", "schema_version"]
            .into_iter()
            .collect()
    );
    assert_eq!(object["schema_version"], 1);
    assert!(object["revision"].as_u64().unwrap() <= 9_007_199_254_740_991);
    assert_eq!(object["run_id"].as_str().unwrap().len(), 32);
    assert_eq!(
        object["game"]
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>(),
        [
            "auto_clipper_cost",
            "auto_clipper_rate",
            "auto_clipper_revealed",
            "auto_clippers",
            "clips_sold",
            "computing_hidden",
            "console_messages",
            "demand",
            "funds",
            "income",
            "last_sale_revenue",
            "lifetime_clips",
            "marketing_cost",
            "marketing_level",
            "memory",
            "price_per_clip",
            "processors",
            "projects_hidden",
            "trust",
            "unsold_clips",
            "unused_clips",
            "wire",
            "wire_quote",
            "wire_spool_length",
        ]
        .into_iter()
        .collect()
    );
    for field in [
        "lifetime_clips",
        "unsold_clips",
        "unused_clips",
        "wire",
        "funds",
        "wire_spool_length",
        "wire_quote",
        "price_per_clip",
        "marketing_cost",
        "demand",
        "clips_sold",
        "income",
        "last_sale_revenue",
        "marketing_level",
        "trust",
        "processors",
        "memory",
        "auto_clippers",
        "auto_clipper_cost",
        "auto_clipper_rate",
    ] {
        assert!(
            object["game"][field].is_string(),
            "{field} must be exact text"
        );
    }
    assert_eq!(
        object["game"]["console_messages"],
        json!(["", "", "", "", ""]),
        "fresh five-line console history"
    );
    let view = response.view();
    assert_eq!(view.game.wire.to_string(), "1000");
    assert_eq!(view.game.funds.to_string(), "0");
    assert_eq!(view.game.lifetime_clips.to_string(), "0");
    assert_eq!(view.game.unsold_clips.to_string(), "0");
    assert_eq!(view.game.unused_clips.to_string(), "0");
    assert_eq!(view.game.wire_spool_length.to_string(), "1000");
    assert_eq!(view.game.wire_quote.to_string(), "20");
    assert_eq!(view.game.price_per_clip.to_string(), "0.25");
    assert_eq!(view.game.marketing_cost.to_string(), "100");
    assert_eq!(view.game.demand.to_string(), "3.2");
    assert_eq!(view.game.clips_sold.to_string(), "0");
    assert_eq!(view.game.income.to_string(), "0");
    assert_eq!(view.game.last_sale_revenue.to_string(), "0");
    assert_eq!(view.game.marketing_level.to_string(), "1");
    assert_eq!(view.game.trust.to_string(), "2");
    assert_eq!(view.game.processors.to_string(), "1");
    assert_eq!(view.game.memory.to_string(), "1");
    assert!(view.game.computing_hidden);
    assert!(view.game.projects_hidden);
    assert!(!view.game.auto_clipper_revealed);
    assert_eq!(view.game.auto_clippers.to_string(), "0");
    assert_eq!(view.game.auto_clipper_cost.to_string(), "5");
    assert_eq!(view.game.auto_clipper_rate.to_string(), "0");
    assert_eq!(
        view.game.console_messages,
        std::array::from_fn(|_| String::new())
    );
    view
}

#[test]
fn negative_table_rejects_every_bad_shape_without_binding_or_game_mutation() {
    let server = TestServer::start();
    let initial = assert_fresh_view(&get(server.address));
    let id = "negative-table-key";
    let mut cases: Vec<(&str, Vec<u8>, u16, &str)> = vec![
        ("malformed JSON", br#"{"command_id":"#.to_vec(), 400, "invalid_command_structure"),
        ("trailing JSON", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":{}} true"#.to_vec(), 400, "invalid_command_structure"),
        ("missing ID", br#"{"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("empty ID", br#"{"command_id":"","type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_id"),
        ("control ID", br#"{"command_id":"bad\nid","type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_id"),
        ("numeric ID", br#"{"command_id":1,"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("boolean ID", br#"{"command_id":true,"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("null ID", br#"{"command_id":null,"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("array ID", br#"{"command_id":[],"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("object ID", br#"{"command_id":{},"type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("duplicate top ID", br#"{"command_id":"negative-table-key","command_id":"other","type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("duplicate type", br#"{"command_id":"negative-table-key","type":"make_paperclip","type":"make_paperclip","arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("duplicate arguments", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":{},"arguments":{}}"#.to_vec(), 400, "invalid_command_structure"),
        ("unknown top field", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":{},"private-marker":"do-not-echo"}"#.to_vec(), 400, "invalid_command_structure"),
        ("array arguments", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":[]}"#.to_vec(), 400, "invalid_arguments"),
        ("null arguments", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":null}"#.to_vec(), 400, "invalid_arguments"),
        ("scalar arguments", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":1}"#.to_vec(), 400, "invalid_arguments"),
        ("nested unknown field", br#"{"command_id":"negative-table-key","type":"make_paperclip","arguments":{"debug":true}}"#.to_vec(), 400, "invalid_arguments"),
        ("unknown action", br#"{"command_id":"negative-table-key","type":"future_action","arguments":{}}"#.to_vec(), 404, "unknown_command"),
        ("nested duplicate keys", br#"{"command_id":"negative-table-key","type":"future_action","arguments":{"nested":{"x":1,"x":2}}}"#.to_vec(), 400, "invalid_command_structure"),
        ("direct duplicate argument keys", br#"{"command_id":"negative-table-key","type":"future_action","arguments":{"x":1,"x":2}}"#.to_vec(), 400, "invalid_command_structure"),
    ];
    cases.push(("overlong ID", serde_json::to_vec(&json!({"command_id":"é".repeat(MAX_COMMAND_ID_BYTES),"type":"make_paperclip","arguments":{}})).unwrap(), 400, "invalid_command_id"));
    for (label, value) in [
        ("integer count", "1"),
        ("fractional float count", "1.0"),
        ("exponent count", "1e0"),
        ("string count", "\"1\""),
        ("boolean count", "true"),
        ("fractional count", "1.5"),
        ("negative count", "-1"),
        ("overflow count", "9007199254740992"),
        ("word overflow", "18446744073709551616"),
        ("arbitrary Amount string", "\"9007199254740993\""),
        ("arbitrary sub-one Amount", "\"0.000000000000000001\""),
    ] {
        let raw = format!(
            "{{\"command_id\":\"{id}\",\"type\":\"make_paperclip\",\"arguments\":{{\"count\":{value}}}}}"
        );
        cases.push((label, raw.into_bytes(), 400, "invalid_arguments"));
    }
    for field in [
        "amount",
        "result_total",
        "resource",
        "cost",
        "wire",
        "funds",
        "actor",
        "world",
        "game_id",
        "observed_revision",
        "revision",
        "time",
        "seed",
        "pause",
        "debug",
        "requested_clips",
    ] {
        let raw = format!(
            "{{\"command_id\":\"{id}\",\"type\":\"make_paperclip\",\"arguments\":{{\"{field}\":1}}}}"
        );
        cases.push((field, raw.into_bytes(), 400, "invalid_arguments"));
    }
    cases.push((
        "invalid UTF-8",
        vec![b'{', b'"', 0xff, b'"', b':', b'1', b'}'],
        400,
        "invalid_utf8",
    ));
    cases.push((
        "body limit",
        vec![b' '; MAX_COMMAND_BODY_BYTES + 1],
        413,
        "body_too_large",
    ));

    for (name, body, expected_status, expected) in cases {
        let response = post(server.address, body);
        assert_eq!(response.status, expected_status, "case: {name}");
        let body = response.json();
        if expected_status == 404 {
            assert_eq!(body["status"], "unknown_command", "case: {name}");
        } else {
            assert_eq!(body["status"], "schema_error", "case: {name}");
            assert_eq!(body["reason"], expected, "case: {name}");
        }
        assert!(!String::from_utf8_lossy(&response.body).contains("do-not-echo"));
        eprintln!(
            "negative table / {name}: HTTP {} / {}",
            response.status, body
        );
    }
    let after = get(server.address).view();
    assert_eq!(
        after.game, initial.game,
        "all invalid inputs are non-mutating"
    );
    assert_eq!(after.run_id, initial.run_id);

    let accepted = post(server.address, command(id));
    assert_eq!(accepted.status, 200, "no invalid case reserved the key");
    let final_view = get(server.address).view();
    assert_eq!(final_view.game.wire.to_string(), "999");
    assert_eq!(final_view.game.lifetime_clips.to_string(), "1");
    server.stop();
}

#[test]
fn normalized_terminal_replay_is_immutable_and_conflicts_preserve_the_binding() {
    let server = TestServer::start();
    let initial = assert_fresh_view(&get(server.address));
    let first = post(
        server.address,
        br#"{"arguments":{},"type":"make_paperclip","command_id":"stable-key"}"#,
    );
    assert_eq!(first.status, 200);
    assert_eq!(first.json()["status"], "applied");

    let other = post(server.address, command("different-new-intent"));
    assert_eq!(other.status, 200);
    let later = get(server.address).view();
    assert!(later.revision.get() > first.json()["revision"].as_u64().unwrap());
    assert_eq!(later.run_id, initial.run_id);
    let reordered = post(
        server.address,
        b"{ \"type\" : \"make_paperclip\", \"command_id\" : \"stable-key\", \"arguments\" : { } }",
    );
    assert_eq!(
        reordered, first,
        "same typed payload replays first bytes/status"
    );

    let unsupported = post(
        server.address,
        br#"{"command_id":"stable-key","type":"future_action","arguments":{}}"#,
    );
    assert_eq!(unsupported.status, 409);
    assert_eq!(unsupported.json(), json!({"status":"conflict"}));
    let malformed = post(
        server.address,
        br#"{"command_id":"stable-key","type":"make_paperclip","arguments":{"count":1.0}}"#,
    );
    assert_eq!(
        malformed.status, 400,
        "invalid new shape precedes key lookup"
    );
    assert_eq!(post(server.address, command("stable-key")), first);

    let view = get(server.address).view();
    assert_eq!(view.game.lifetime_clips.to_string(), "2");
    assert_eq!(view.game.unsold_clips.to_string(), "2");
    assert_eq!(view.game.unused_clips.to_string(), "2");
    assert_eq!(view.game.wire.to_string(), "998");
    assert_eq!(post(server.address, command("stable-key")), first);
    server.stop();
}

#[test]
fn independent_http_clients_apply_two_legal_intents_and_coalesce_retries() {
    let server = TestServer::start();
    thread::scope(|scope| {
        let a = scope.spawn(|| post(server.address, command("client-a")));
        let b = scope.spawn(|| post(server.address, command("client-b")));
        assert_eq!(a.join().unwrap().status, 200);
        assert_eq!(b.join().unwrap().status, 200);
    });
    let after_two = get(server.address).view();
    assert_eq!(after_two.game.wire.to_string(), "998");
    assert_eq!(after_two.game.lifetime_clips.to_string(), "2");

    let responses = thread::scope(|scope| {
        let mut workers = Vec::new();
        for _ in 0..12 {
            workers.push(scope.spawn(|| post(server.address, command("client-a"))));
        }
        workers
            .into_iter()
            .map(|worker| worker.join().unwrap())
            .collect::<Vec<_>>()
    });
    assert!(responses.windows(2).all(|pair| pair[0] == pair[1]));
    let final_view = get(server.address).view();
    assert_eq!(final_view.game.wire.to_string(), "998");
    assert_eq!(final_view.game.lifetime_clips.to_string(), "2");
    assert_eq!(final_view.game.unsold_clips.to_string(), "2");
    assert_eq!(final_view.game.unused_clips.to_string(), "2");
    server.stop();
}

#[test]
fn auto_clipper_commands_charge_stored_cost_replay_and_reject_tampering() {
    fn auto_command(id: &str) -> Vec<u8> {
        serde_json::to_vec(&json!({
            "command_id": id,
            "type": "buy_auto_clipper",
            "arguments": {}
        }))
        .unwrap()
    }

    let first_server = TestServer::start_with_state(|state| {
        state.pro.wire = NonNegativeAmount::zero();
        state.pro.funds = Amount::from_i128(5);
        state.pro.auto_clipper_revealed = true;
    });
    let first = post(first_server.address, auto_command("first-auto-threshold"));
    assert_eq!(first.status, 200);
    assert_eq!(first.json(), json!({"status":"applied","revision":1}));
    let first_view = get(first_server.address).view();
    assert_eq!(first_view.game.funds, Amount::zero());
    assert_eq!(first_view.game.auto_clippers.to_string(), "1");
    assert_eq!(first_view.game.auto_clipper_cost.to_string(), "6.1");
    assert_eq!(first_view.game.auto_clipper_rate.to_string(), "0");
    assert_eq!(first_view.game.wire, NonNegativeAmount::zero());
    assert_eq!(first_view.game.lifetime_clips, NonNegativeAmount::zero());
    assert_eq!(
        get(first_server.address).json()["game"]["auto_clipper_cost"],
        "6.1"
    );
    eprintln!("G03 real HTTP exact threshold: 5 charged, Funds 0/count 1/next canonical 6.1");

    let successor_server = TestServer::start_with_state(|state| {
        state.pro.wire = NonNegativeAmount::zero();
        state.pro.funds = Amount::from_i128(20);
        state.pro.auto_clipper_revealed = true;
        state.pro.auto_clippers = IntegralAmount::from_i128(1);
        state.pro.auto_clipper_cost = Amount::parse("6.1").unwrap();
    });
    let successor = post(
        successor_server.address,
        auto_command("second-auto-successor"),
    );
    assert_eq!(successor.status, 200);
    let successor_view = get(successor_server.address).view();
    assert_eq!(successor_view.game.funds.to_string(), "13.9");
    assert_eq!(successor_view.game.auto_clippers.to_string(), "2");
    assert_eq!(successor_view.game.auto_clipper_cost.to_string(), "6.21");
    assert_eq!(
        successor_view.game.lifetime_clips,
        NonNegativeAmount::zero()
    );
    eprintln!("G03 real HTTP successor: 20-6.1=13.9/count 2/next canonical 6.21");

    let rejected_server = TestServer::start_with_state(|state| {
        state.pro.wire = NonNegativeAmount::zero();
        state.pro.funds = Amount::parse("4.99").unwrap();
        state.pro.auto_clipper_revealed = true;
    });
    let before = get(rejected_server.address).view();
    let rejection = post(rejected_server.address, auto_command("below-auto-cost"));
    assert_eq!(rejection.status, 422);
    assert_eq!(rejection.json()["reason"], "insufficient_funds");
    assert_eq!(
        post(rejected_server.address, auto_command("below-auto-cost")),
        rejection
    );
    let after = get(rejected_server.address).view();
    assert_eq!(after.game.funds.to_string(), "4.99");
    assert_eq!(after.game.lifetime_clips, before.game.lifetime_clips);
    assert_eq!(after.game.unsold_clips, before.game.unsold_clips);
    assert_eq!(after.game.unused_clips, before.game.unused_clips);
    assert_eq!(after.game.wire, before.game.wire);
    assert_eq!(after.game.auto_clippers, before.game.auto_clippers);
    assert_eq!(after.game.auto_clipper_cost, before.game.auto_clipper_cost);
    assert_eq!(after.game.auto_clipper_rate, before.game.auto_clipper_rate);
    assert!(after.game.auto_clipper_revealed);
    assert_eq!(after.game.console_messages, before.game.console_messages);

    // The replay of the original threshold command remains byte-identical even
    // after other independent servers and commands have run; no second charge.
    assert_eq!(
        post(first_server.address, auto_command("first-auto-threshold")),
        first
    );
    assert_eq!(
        get(first_server.address)
            .view()
            .game
            .auto_clippers
            .to_string(),
        "1"
    );

    for bad_arguments in [
        json!({"cost":"5"}),
        json!({"funds":"5"}),
        json!({"count":1}),
        json!({"price":5.0}),
    ] {
        let id = format!("auto-forgery-{}", bad_arguments);
        let response = post(
            rejected_server.address,
            serde_json::to_vec(&json!({
                "command_id": id,
                "type": "buy_auto_clipper",
                "arguments": bad_arguments,
            }))
            .unwrap(),
        );
        assert_eq!(response.status, 400);
        assert_eq!(response.json()["reason"], "invalid_arguments");
        // Structural forgery never binds its ID; the legal empty intent can
        // subsequently bind and receive the ordinary below-cost rejection.
        let legal = post(rejected_server.address, auto_command(&id));
        assert_eq!(legal.status, 422);
        assert_eq!(legal.json()["reason"], "insufficient_funds");
    }

    first_server.stop();
    successor_server.stop();
    rejected_server.stop();
}

#[test]
fn closed_business_commands_and_original_key_retries_use_real_rules() {
    let server = TestServer::start();
    let initial = assert_fresh_view(&get(server.address));
    for (kind, expected_status, expected_result) in [
        ("lower_price", 200, "applied"),
        ("raise_price", 200, "applied"),
        ("buy_wire", 422, "rule_rejected"),
        ("buy_marketing", 422, "rule_rejected"),
    ] {
        let id = format!("business-{kind}");
        let raw = serde_json::to_vec(&json!({"command_id":id,"type":kind,"arguments":{}})).unwrap();
        let first = post(server.address, &raw);
        assert_eq!(first.status, expected_status, "{kind}");
        assert_eq!(first.json()["status"], expected_result, "{kind}");
        if expected_status == 422 {
            assert_eq!(first.json()["reason"], "insufficient_funds");
            assert!(first.json()["revision"].is_u64());
        }
        let reordered = post(
            server.address,
            format!(r#"{{ "type" : "{kind}", "command_id" : "{id}", "arguments" : {{ }} }}"#),
        );
        assert_eq!(reordered, first, "terminal original-ID retry: {kind}");
        let conflicting = post(
            server.address,
            serde_json::to_vec(&json!({"command_id":id,"type":"make_paperclip","arguments":{}}))
                .unwrap(),
        );
        assert_eq!(conflicting.status, 409);
        assert_eq!(conflicting.json(), json!({"status":"conflict"}));

        let bad_id = format!("business-bad-{kind}");
        let bad = post(
            server.address,
            serde_json::to_vec(
                &json!({"command_id":bad_id,"type":kind,"arguments":{"cost":"20","funds":"100"}}),
            )
            .unwrap(),
        );
        assert_eq!(bad.status, 400);
        assert_eq!(bad.json()["reason"], "invalid_arguments");
        let good = post(
            server.address,
            serde_json::to_vec(&json!({"command_id":bad_id,"type":kind,"arguments":{}})).unwrap(),
        );
        assert_eq!(
            good.status, expected_status,
            "bad shape must not bind {kind}"
        );
        assert_eq!(good.json()["status"], expected_result);
        if expected_status == 422 {
            assert_eq!(good.json()["reason"], "insufficient_funds");
        }
    }
    let later = get(server.address).view();
    assert_eq!(later.run_id, initial.run_id);
    assert_eq!(later.game.price_per_clip.to_string(), "0.25");
    assert_eq!(later.game.funds, Amount::zero());
    assert_eq!(later.game.wire.to_string(), "1000");
    assert_eq!(later.game.marketing_level.to_string(), "1");
    for iteration in 0..70 {
        let response = post(server.address, serde_json::to_vec(&json!({"command_id":format!("price-boundary-{iteration}"),"type":"lower_price","arguments":{}})).unwrap());
        // Unique-ID command names intentionally use the same source action.
        if response.status != 200 {
            assert_eq!(response.status, 422);
            assert_eq!(response.json()["status"], "rule_rejected");
            assert_eq!(response.json()["reason"], "price_at_minimum");
            break;
        }
    }
    let at_floor = get(server.address).view();
    assert_eq!(at_floor.game.price_per_clip.to_string(), "0.01");
    server.stop();
}
