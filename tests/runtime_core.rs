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
