use paperclip_game::game::amount::Amount;
use paperclip_game::runtime::{Command, CommandId, GameRuntime};
use std::time::Duration;
use tokio::time::timeout;

#[tokio::test]
async fn real_clock_advances_without_clients_and_manual_intent_stays_closed() {
    let runtime = GameRuntime::start().expect("production runtime starts");
    let handle = runtime.handle();
    let initial = handle.view();
    assert_fresh_state(&initial);
    assert_eq!(initial.revision, 0);
    assert_eq!(initial.game.clock.update_count(), 0);
    assert_eq!(initial.process.lag_debt_nanos, 0);

    let initial_rng = initial.game.rng_state_hex();
    let mut views = handle.subscribe();
    let observed = timeout(Duration::from_secs(3), async {
        loop {
            let current = views.borrow().clone();
            if current.game.clock.update_count() >= 3 {
                return current;
            }
            views.changed().await.expect("real writer stays alive");
        }
    })
    .await
    .expect("real monotonic clock drives bounded test progress");
    assert!(observed.revision >= 3);
    assert_eq!(observed.game.rng_state_hex(), initial_rng);
    assert_eq!(observed.game.pro.lifetime_clips.to_string(), "0");
    assert_eq!(observed.game.pro.unsold_clips.to_string(), "0");
    assert_eq!(observed.game.pro.unused_clips.to_string(), "0");
    assert_eq!(observed.game.pro.funds.to_string(), "0");
    assert_eq!(observed.game.pro.wire.to_string(), "1000");

    let receipt = handle
        .execute(Command::make_paperclip(
            CommandId::new(1).expect("safe command id"),
        ))
        .await
        .expect("open command queue");
    assert_eq!(receipt.result, Ok(()));
    assert!(receipt.revision >= 4);
    let view = handle.view();
    assert_eq!(view.game.pro.wire.to_string(), "999");
    assert_eq!(view.game.pro.lifetime_clips.to_string(), "1");
    assert_eq!(view.game.pro.unsold_clips.to_string(), "1");
    assert_eq!(view.game.pro.unused_clips.to_string(), "1");
    assert_eq!(view.game.rng_state_hex(), initial_rng);
    runtime.shutdown().await.expect("clean writer shutdown");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn real_clock_two_autoclippers_advance_without_browser_or_sse() {
    use paperclip_game::game::amount::{IntegralAmount, NonNegativeAmount};

    let seed = GameRuntime::start().unwrap();
    let mut state = seed.handle().view().game;
    seed.shutdown().await.unwrap();
    state.pro.auto_clippers = IntegralAmount::from_i128(2);
    state.pro.auto_clipper_revealed = true;
    state.pro.auto_clipper_cost = Amount::parse("6.21").unwrap();
    state.pro.wire = NonNegativeAmount::from_i128(50).unwrap();
    let runtime = GameRuntime::start_from_snapshot(state, 0).unwrap();
    let handle = runtime.handle();
    let initial = handle.view();
    assert_eq!(initial.revision, 0);

    // This is a runtime watch used by the test, not HTTP, SSE, or a browser.
    // No public client exists while real monotonic time advances the producer.
    let mut views = handle.subscribe();
    let observed = timeout(Duration::from_secs(4), async {
        loop {
            let current = views.borrow().clone();
            if current.game.clock.update_count() >= 200 {
                return current;
            }
            views.changed().await.expect("real writer stays alive");
        }
    })
    .await
    .unwrap();
    let expected = Amount::quantize_ratio(
        &(num_bigint::BigInt::from(observed.game.clock.update_count()) * 2u8),
        &num_bigint::BigInt::from(100u8),
    )
    .unwrap()
    .nonnegative()
    .unwrap();
    assert_eq!(observed.game.pro.lifetime_clips, expected);
    assert_eq!(observed.game.pro.unused_clips, expected);
    assert_eq!(
        observed.game.pro.wire,
        NonNegativeAmount::new(&Amount::from_i128(50) - expected.amount()).unwrap()
    );
    assert_eq!(observed.game.pro.auto_clipper_rate.to_string(), "2");
    assert_eq!(
        observed
            .game
            .pro
            .unsold_clips
            .add_exact(&observed.game.pro.clips_sold),
        observed.game.pro.lifetime_clips
    );
    assert_eq!(observed.process.applied_commands, 0);
    eprintln!(
        "RT-NO-CLIENTS-CONTINUOUS G03: real server, zero browser/SSE/Commands; tick-exact expected lifetime={} at update={}",
        observed.game.pro.lifetime_clips,
        observed.game.clock.update_count()
    );
    runtime.shutdown().await.unwrap();
}

#[test]
fn negative_table_rejects_unsafe_public_command_ids() {
    use paperclip_game::game::amount::BoundedIntegerError;

    for value in [9_007_199_254_740_992, u64::MAX] {
        assert_eq!(
            CommandId::new(value).err(),
            Some(BoundedIntegerError::AboveJsonSafeRange)
        );
        eprintln!("unsafe public command ID {value}: AboveJsonSafeRange");
    }
}

fn assert_fresh_state(view: &paperclip_game::runtime::RuntimeView) {
    let state = &view.game.pro;
    assert_eq!(state.lifetime_clips.to_string(), "0");
    assert_eq!(state.unsold_clips.to_string(), "0");
    assert_eq!(state.unused_clips.to_string(), "0");
    assert_eq!(state.funds.to_string(), "0");
    assert_eq!(state.wire.to_string(), "1000");
    assert_eq!(state.wire_spool_length.to_string(), "1000");
    assert_eq!(state.wire_quote.to_string(), "20");
    assert_eq!(state.price_per_clip.to_string(), "0.25");
    assert_eq!(state.marketing_level.to_string(), "1");
    assert_eq!(state.trust.to_string(), "2");
    assert_eq!(state.processors.to_string(), "1");
    assert_eq!(state.memory.to_string(), "1");
    assert!(state.computing_hidden);
    assert!(state.projects_hidden);
    assert!(!state.auto_clipper_revealed);
    assert_eq!(state.auto_clippers.to_string(), "0");
    assert_eq!(state.auto_clipper_cost.to_string(), "5");
}
