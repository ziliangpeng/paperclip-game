use paperclip_game::game::amount::{Amount, NonNegativeAmount};
use paperclip_game::game::economy;
use paperclip_game::game::state::GameState;
use paperclip_game::runtime::GameRuntime;
use paperclip_game::snapshot::Snapshot;
use std::time::Duration;
use tokio::time::timeout;

fn positive(value: &str) -> NonNegativeAmount {
    Amount::parse(value).unwrap().nonnegative().unwrap()
}

async fn advanced_fresh_state() -> GameState {
    let runtime = GameRuntime::start().expect("fresh production runtime");
    let handle = runtime.handle();
    let mut views = handle.subscribe();
    let advanced = timeout(Duration::from_secs(4), async {
        loop {
            let current = views.borrow().clone();
            if current.game.clock.update_count() >= 137 {
                return current;
            }
            views.changed().await.expect("online writer stays alive");
        }
    })
    .await
    .expect("bounded real ticks establish a nondefault timer/RNG fixture");
    runtime.shutdown().await.expect("stop fixture runtime");
    advanced.game
}

fn restore_exact(
    state: &GameState,
    revision: u64,
    label: &str,
) -> paperclip_game::snapshot::RecoveredSnapshot {
    let before_pro = state.pro.clone();
    let before_clock = state.clock.clone();
    let before_rng = state.rng_state_hex();
    let snapshot = Snapshot::capture(state, revision).expect("capture valid M1 V3 state");
    let encoded = snapshot.to_canonical_bytes().expect("canonical V3 bytes");

    // Snapshot transport/restoration itself is not online time and must never
    // infer offline production or another logical tick.
    let recovered = Snapshot::from_canonical_bytes(&encoded)
        .unwrap_or_else(|error| panic!("decode {label}: {error}"))
        .restore()
        .unwrap_or_else(|error| panic!("restore {label}: {error}"));
    assert_eq!(recovered.revision, revision);
    assert_eq!(recovered.state.pro, before_pro, "{label} ProState");
    assert_eq!(recovered.state.clock, before_clock, "{label} clock");
    assert_eq!(recovered.state.rng_state_hex(), before_rng, "{label} RNG");
    assert_eq!(state.clock.update_count(), before_clock.update_count());
    assert_eq!(state.rng_state_hex(), before_rng);
    recovered
}

#[tokio::test]
async fn m1_v3_restores_both_stored_successors_without_backfill_or_recompute() {
    let mut state = advanced_fresh_state().await;
    assert!(state.clock.update_count() >= 137);
    assert!(!state.pro.auto_clipper_revealed);
    assert_eq!(state.pro.auto_clippers.to_string(), "0");
    assert_eq!(state.pro.auto_clipper_cost.to_string(), "5");

    // Pure fixture only: exact threshold funds are supplied here, never through
    // a public/production write. The actual purchase is the legal economy rule.
    state.pro.funds = Amount::from_i128(5);
    assert_eq!(state.pro.auto_clipper_cost, Amount::from_i128(5));
    economy::buy_auto_clipper(&mut state.pro).expect("exact first stored-cost purchase");
    assert_eq!(state.pro.funds, Amount::zero());
    assert_eq!(state.pro.auto_clippers.to_string(), "1");
    assert_eq!(state.pro.auto_clipper_cost.to_string(), "6.1");
    assert!(state.pro.auto_clipper_revealed);

    // Explicitly labeled snapshot-only valid continuation-domain fields. Other
    // suites independently prove how actual online ticks derive these values.
    state.pro.auto_clipper_rate = positive("0.75");
    state.pro.auto_clipper_production_accumulator = positive("0.25");
    let first = restore_exact(&state, 41, "6.10 successor");
    assert_eq!(first.state.pro.auto_clippers.to_string(), "1");
    assert_eq!(first.state.pro.auto_clipper_cost.to_string(), "6.1");
    assert_eq!(first.state.pro.auto_clipper_rate.to_string(), "0.75");
    assert_eq!(
        first
            .state
            .pro
            .auto_clipper_production_accumulator
            .to_string(),
        "0.25"
    );
    assert_eq!(first.state.clock.update_count(), state.clock.update_count());
    assert!(first.state.pro.auto_clipper_revealed);

    let mut restored = first.state;
    restored.pro.funds = Amount::from_i128(20);
    economy::buy_auto_clipper(&mut restored.pro).expect("exact distinct successor purchase");
    assert_eq!(restored.pro.funds.to_string(), "13.9");
    assert_eq!(restored.pro.auto_clippers.to_string(), "2");
    assert_eq!(restored.pro.auto_clipper_cost.to_string(), "6.21");
    restored.pro.auto_clipper_rate = positive("1.5");
    restored.pro.auto_clipper_production_accumulator = positive("0.5");
    let second = restore_exact(&restored, 42, "6.21 successor");
    assert_eq!(second.state.pro.auto_clippers.to_string(), "2");
    assert_eq!(second.state.pro.auto_clipper_cost.to_string(), "6.21");
    assert_eq!(second.state.pro.auto_clipper_rate.to_string(), "1.5");
    assert_eq!(
        second
            .state
            .pro
            .auto_clipper_production_accumulator
            .to_string(),
        "0.5"
    );
    assert_eq!(second.state.clock, restored.clock);
    assert_eq!(second.state.rng_state_hex(), restored.rng_state_hex());
    assert!(second.state.pro.auto_clipper_revealed);

    // Retry receipt tables remain process-local by contract. In particular this
    // V3 roundtrip makes no exactly-once-across-crash or dedup-survival claim.
    eprintln!(
        "PERSIST-CRASH-LOSS-NO-BACKFILL snapshot fixture: real clock {} and exact RNG preserved at 1/6.10 and 2/6.21; no tick added by restore; real SIGKILL/downtime is covered separately",
        second.state.clock.update_count()
    );
}
