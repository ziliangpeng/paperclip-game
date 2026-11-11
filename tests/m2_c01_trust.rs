use num_bigint::BigInt;
use paperclip_game::game::amount::{Amount, IntegralAmount, NonNegativeAmount};
use paperclip_game::game::economy::{
    EconomyError, add_memory, add_processor, observe_trust_targets,
};
use paperclip_game::game::evaluator::{creativity_speed, processor_domain_upper};
use paperclip_game::game::state::{GameState, ProState};
use paperclip_game::runtime::GameRuntime;
use paperclip_game::snapshot::{SNAPSHOT_VERSION, Snapshot};

fn positive(text: &str) -> NonNegativeAmount {
    Amount::parse(text).unwrap().nonnegative().unwrap()
}

fn whole(value: &IntegralAmount) -> BigInt {
    value.amount().mantissa() / Amount::from_i128(1).mantissa()
}

fn integral(value: BigInt) -> IntegralAmount {
    Amount::from_i128(1)
        .multiply_integer(&value)
        .integral()
        .unwrap()
}

fn fresh_state() -> GameState {
    let executor = tokio::runtime::Runtime::new().expect("test Tokio runtime");
    executor.block_on(async {
        let runtime = GameRuntime::start().expect("fresh runtime");
        let state = runtime.handle().view().game;
        runtime.shutdown().await.expect("fresh runtime shutdown");
        state
    })
}

fn set_lifetime(pro: &mut ProState, value: &str) {
    pro.lifetime_clips = positive(value);
    pro.unused_clips = positive(value);
    pro.unsold_clips = positive(value);
    pro.clips_sold = NonNegativeAmount::zero();
}

fn unlocked(pro: &mut ProState, trust: i128) {
    pro.computing_hidden = false;
    pro.projects_hidden = false;
    pro.trust = IntegralAmount::from_i128(trust);
}

#[test]
fn exact_target_table_multi_crossings_replays_and_fixed_words() {
    let mut state = fresh_state();
    set_lifetime(&mut state.pro, "2999");
    let before = state.pro.clone();
    observe_trust_targets(&mut state.pro).unwrap();
    observe_trust_targets(&mut state.pro).unwrap();
    assert_eq!(state.pro, before);
    assert_eq!(state.pro.next_trust_target.to_string(), "3000");
    assert_eq!(state.pro.trust_target_predecessor.to_string(), "2000");

    set_lifetime(&mut state.pro, "3000");
    observe_trust_targets(&mut state.pro).unwrap();
    assert_eq!(state.pro.trust.to_string(), "3");
    assert_eq!(state.pro.trust_target_predecessor.to_string(), "3000");
    assert_eq!(state.pro.next_trust_target.to_string(), "5000");
    assert!(state.pro.console_messages[4].contains("3000 reached"));

    // One direct update catches up 5000/8000/13000 in order, without aggregation.
    set_lifetime(&mut state.pro, "13000");
    observe_trust_targets(&mut state.pro).unwrap();
    assert_eq!(state.pro.trust.to_string(), "6");
    assert_eq!(state.pro.next_trust_target.to_string(), "21000");
    assert_eq!(state.pro.trust_target_predecessor.to_string(), "13000");
    let messages = state.pro.console_messages.join("\n");
    for target in [
        "Trust target 3000 reached",
        "Trust target 5000 reached",
        "Trust target 8000 reached",
        "Trust target 13000 reached",
    ] {
        assert_eq!(messages.matches(target).count(), 1, "{messages}");
    }
    let ordered = state.pro.console_messages.clone();
    assert!(ordered[1].contains("3000 reached"));
    assert!(ordered[2].contains("5000 reached"));
    assert!(ordered[3].contains("8000 reached"));
    assert!(ordered[4].contains("13000 reached"));
    let after = state.pro.clone();
    observe_trust_targets(&mut state.pro).unwrap();
    observe_trust_targets(&mut state.pro).unwrap();
    assert_eq!(state.pro, after);

    for huge in [
        "9007199254740993",
        "340282366920938463463374607431768211457",
    ] {
        let mut state = fresh_state();
        set_lifetime(&mut state.pro, huge);
        observe_trust_targets(&mut state.pro).unwrap();
        // Independent exact reference state for this observation.
        let exact_lifetime = BigInt::parse_bytes(huge.as_bytes(), 10).unwrap();
        let one = BigInt::from(1u8);
        let mut predecessor = BigInt::from(2000u16);
        let mut target = BigInt::from(3000u16);
        let mut awards = BigInt::from(0u8);
        while target <= exact_lifetime {
            awards += &one;
            let successor = &predecessor + &target;
            predecessor = target;
            target = successor;
        }
        assert_eq!(whole(&state.pro.next_trust_target), target);
        assert_eq!(whole(&state.pro.trust_target_predecessor), predecessor);
        assert_eq!(whole(&state.pro.trust), awards + 2u8);
        assert!(whole(&state.pro.next_trust_target) > exact_lifetime);
        let repeated = state.pro.clone();
        observe_trust_targets(&mut state.pro).unwrap();
        assert_eq!(state.pro, repeated);
    }
}

#[test]
fn beyond_five_awards_retain_each_trust_increment_and_latest_five_messages() {
    let mut state = fresh_state();
    set_lifetime(&mut state.pro, "34000");
    observe_trust_targets(&mut state.pro).unwrap();
    assert_eq!(state.pro.trust.to_string(), "8"); // 6 targets: 3000..34000
    assert_eq!(state.pro.next_trust_target.to_string(), "55000");
    assert_eq!(state.pro.trust_target_predecessor.to_string(), "34000");
    let messages = state.pro.console_messages.join("\n");
    assert!(!messages.contains("Trust target 3000 reached"));
    for present in [
        "Trust target 5000 reached",
        "Trust target 8000 reached",
        "Trust target 13000 reached",
        "Trust target 21000 reached",
        "Trust target 34000 reached",
    ] {
        assert_eq!(messages.matches(present).count(), 1);
    }
    // Exactly six awards, but the pre-existing five-line surface holds only five.
    assert_eq!(state.pro.console_messages.len(), 5);
}

#[test]
fn strict_allocation_capacity_benefits_and_outward_domain_are_atomic() {
    let mut locked = fresh_state().pro;
    let before = locked.clone();
    assert_eq!(
        add_processor(&mut locked),
        Err(EconomyError::ComputationLocked)
    );
    assert_eq!(
        add_memory(&mut locked),
        Err(EconomyError::ComputationLocked)
    );
    assert_eq!(locked, before);

    let mut state = fresh_state().pro;
    unlocked(&mut state, 4);
    assert_eq!(state.creativity_speed.to_string(), "1");
    add_processor(&mut state).unwrap();
    assert_eq!(state.trust.to_string(), "4");
    assert_eq!(state.processors.to_string(), "2");
    assert_eq!(state.memory.to_string(), "1");
    assert_eq!(state.available_trust_capacity().to_string(), "1");
    assert_eq!(state.standard_ops_capacity().unwrap().to_string(), "1000");
    assert_eq!(
        state.creativity_speed,
        creativity_speed(&IntegralAmount::from_i128(2)).unwrap()
    );
    assert_ne!(state.creativity_speed.to_string(), "1");
    let processor_speed = state.creativity_speed.clone();

    add_memory(&mut state).unwrap();
    assert_eq!(state.trust.to_string(), "4");
    assert_eq!(state.processors.to_string(), "2");
    assert_eq!(state.memory.to_string(), "2");
    assert_eq!(state.available_trust_capacity().to_string(), "0");
    assert_eq!(state.standard_ops_capacity().unwrap().to_string(), "2000");
    assert_eq!(state.creativity_speed, processor_speed);
    assert_eq!(
        state.console_messages[4],
        "Memory added, max operations increased."
    );
    let full = state.clone();
    assert_eq!(
        add_processor(&mut state),
        Err(EconomyError::TrustCapacityFull)
    );
    assert_eq!(add_memory(&mut state), Err(EconomyError::TrustCapacityFull));
    assert_eq!(state, full);

    let mut fresh = fresh_state().pro;
    unlocked(&mut fresh, 2);
    let fresh_before = fresh.clone();
    assert_eq!(
        add_processor(&mut fresh),
        Err(EconomyError::TrustCapacityFull)
    );
    assert_eq!(add_memory(&mut fresh), Err(EconomyError::TrustCapacityFull));
    assert_eq!(fresh, fresh_before);

    // Legacy arbitrary-precision P remains loadable. A capacity-legal new P above
    // the finite evaluator endpoint has its own error before any field changes.
    let upper = processor_domain_upper();
    let mut outward = fresh_state().pro;
    unlocked(&mut outward, 0);
    outward.trust = integral(&upper + 2u8);
    outward.processors = integral(upper.clone());
    outward.memory = IntegralAmount::from_i128(1);
    outward.creativity_speed = positive("1");
    let outward_before = outward.clone();
    assert_eq!(
        add_processor(&mut outward),
        Err(EconomyError::ProcessorEvaluatorDomain)
    );
    assert_eq!(outward, outward_before);
    // Memory does not invoke the Processor curve and can use the remaining capacity.
    add_memory(&mut outward).unwrap();
    assert_eq!(outward.memory.to_string(), "2");
    assert_eq!(outward.trust, outward_before.trust);
    assert_eq!(outward.processors, outward_before.processors);
    assert_eq!(outward.creativity_speed, outward_before.creativity_speed);
    assert_eq!(outward.available_trust_capacity().to_string(), "0");
}

#[test]
fn v4_restore_retains_stored_speed_targets_and_ops_without_recompute() {
    let mut state = fresh_state();
    unlocked(&mut state.pro, 4);
    add_processor(&mut state.pro).unwrap();
    state.pro.memory = IntegralAmount::from_i128(2);
    state.pro.next_trust_target = IntegralAmount::from_i128(5_000);
    state.pro.trust_target_predecessor = IntegralAmount::from_i128(3_000);
    let expected_speed = state.pro.creativity_speed.clone();
    assert_ne!(expected_speed.to_string(), "1");
    state.pro.standard_ops = positive("1500");
    state.pro.temporary_ops = positive("20.000000000000000001");
    let snapshot = Snapshot::capture(&state, 7).unwrap();
    assert_eq!(SNAPSHOT_VERSION, 4);
    let encoded = snapshot.to_canonical_bytes().unwrap();
    let restored = Snapshot::from_canonical_bytes(&encoded)
        .unwrap()
        .restore()
        .unwrap();
    assert_eq!(restored.revision, 7);
    assert_eq!(restored.state.pro, state.pro);
    assert_eq!(restored.state.clock, state.clock);
    assert_eq!(restored.state.rng_state_hex(), state.rng_state_hex());
    assert_eq!(restored.state.pro.creativity_speed, expected_speed);
    assert_eq!(restored.state.pro.standard_ops.to_string(), "1500");
    assert_eq!(
        restored.state.pro.temporary_ops.to_string(),
        "20.000000000000000001"
    );

    // Only the continuous P=1 zero is relevant here; multiplying it by zero
    // cannot make it positive. This is not a prestige or Xavier implementation.
    let zero = creativity_speed(&IntegralAmount::from_i128(1)).unwrap();
    assert_eq!(
        zero.amount().multiply_integer(&BigInt::from(0u8)),
        Amount::zero()
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn direct_production_crossing_three_thousand_awards_without_another_intent() {
    use paperclip_game::runtime::{Command, CommandId};

    let seed = GameRuntime::start().unwrap();
    let mut initial = seed.handle().view().game;
    seed.shutdown().await.unwrap();
    set_lifetime(&mut initial.pro, "2999");
    initial.pro.wire = NonNegativeAmount::from_i128(1).unwrap();
    initial.pro.computing_hidden = false;
    initial.pro.projects_hidden = false;
    let runtime = GameRuntime::start_from_snapshot(initial, 0).unwrap();
    let handle = runtime.handle();
    let crossing = handle
        .execute(Command::make_paperclip(CommandId::new(1).unwrap()))
        .await
        .unwrap();
    assert_eq!(crossing.result, Ok(()));
    let state = handle.view().game;
    assert_eq!(state.pro.lifetime_clips.to_string(), "3000");
    assert_eq!(state.pro.wire.to_string(), "0");
    assert_eq!(
        state.pro.trust.to_string(),
        "3",
        "production itself must cross the first new cursor"
    );
    assert_eq!(state.pro.next_trust_target.to_string(), "5000");
    assert_eq!(state.pro.trust_target_predecessor.to_string(), "3000");
    assert!(state.pro.console_messages[4].contains("Trust target 3000 reached"));
    runtime.shutdown().await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn runtime_command_tick_retry_and_restore_deduplicate_awards_and_allocation() {
    use paperclip_game::runtime::{Command, CommandId};

    let seed = GameRuntime::start().unwrap();
    let mut state = seed.handle().view().game;
    seed.shutdown().await.unwrap();
    set_lifetime(&mut state.pro, "3000");
    unlocked(&mut state.pro, 2);
    state.pro.funds = Amount::from_i128(100);
    let runtime = GameRuntime::start_from_snapshot(state, 0).unwrap();
    let handle = runtime.handle();
    let crossing = handle
        .execute(Command::raise_price(CommandId::new(101).unwrap()))
        .await
        .unwrap();
    assert_eq!(crossing.result, Ok(()));
    let after_crossing = handle.view().game;
    assert_eq!(after_crossing.pro.trust.to_string(), "3");
    assert_eq!(after_crossing.pro.next_trust_target.to_string(), "5000");
    assert_eq!(
        after_crossing.pro.trust_target_predecessor.to_string(),
        "3000"
    );
    assert_eq!(
        after_crossing
            .pro
            .console_messages
            .iter()
            .filter(|message| message.contains("Trust target 3000 reached"))
            .count(),
        1
    );

    let p_id = CommandId::new(102).unwrap();
    let add_p = handle.execute(Command::add_processor(p_id)).await.unwrap();
    assert_eq!(add_p.result, Ok(()));
    let after_p = handle.view().game;
    assert_eq!(after_p.pro.processors.to_string(), "2");
    assert_eq!(after_p.pro.trust.to_string(), "3");
    assert_eq!(after_p.pro.available_trust_capacity().to_string(), "0");
    let add_p_replay = handle.execute(Command::add_processor(p_id)).await.unwrap();
    assert_eq!(
        add_p_replay, add_p,
        "retry replays success even after capacity is full"
    );
    let after_replay = handle.view().game;
    assert_eq!(after_replay.pro.processors.to_string(), "2");
    assert_eq!(after_replay.pro.trust.to_string(), "3");
    assert_eq!(
        after_replay.pro.next_trust_target,
        after_p.pro.next_trust_target
    );
    assert_eq!(
        after_replay
            .pro
            .console_messages
            .iter()
            .filter(|message| message.contains("Trust target 3000 reached"))
            .count(),
        1
    );
    runtime.shutdown().await.unwrap();

    // Actual V4 serialization/recovery keeps cursor, speed and console history.
    let stored = Snapshot::capture(&after_replay, add_p.revision).unwrap();
    let recovered = Snapshot::from_canonical_bytes(&stored.to_canonical_bytes().unwrap())
        .unwrap()
        .restore()
        .unwrap();
    let restarted = GameRuntime::start_from_snapshot(recovered.state, recovered.revision).unwrap();
    let restarted_handle = restarted.handle();
    let continuation = restarted_handle
        .execute(Command::lower_price(CommandId::new(103).unwrap()))
        .await
        .unwrap();
    assert_eq!(continuation.result, Ok(()));
    let continued = restarted_handle.view().game;
    assert_eq!(continued.pro.trust.to_string(), "3");
    assert_eq!(continued.pro.processors.to_string(), "2");
    assert_eq!(continued.pro.memory.to_string(), "1");
    assert_eq!(continued.pro.next_trust_target.to_string(), "5000");
    assert_eq!(continued.pro.trust_target_predecessor.to_string(), "3000");
    assert_eq!(
        continued.pro.creativity_speed,
        after_replay.pro.creativity_speed
    );
    assert_eq!(
        continued
            .pro
            .console_messages
            .iter()
            .filter(|message| message.contains("Trust target 3000 reached"))
            .count(),
        1
    );
    restarted.shutdown().await.unwrap();
}

fn v3_payload_without_c01_fields(snapshot: &Snapshot) -> Vec<u8> {
    let text = String::from_utf8(snapshot.to_canonical_bytes().unwrap()).unwrap();
    let pro = &snapshot.pro;
    let additions = format!(
        "\"memory\":\"{}\",\"next_trust_target\":\"{}\",\"trust_target_predecessor\":\"{}\",\"creativity_speed\":\"{}\",\"standard_ops\":\"{}\",\"temporary_ops\":\"{}\",",
        pro.memory,
        pro.next_trust_target,
        pro.trust_target_predecessor,
        pro.creativity_speed,
        pro.standard_ops,
        pro.temporary_ops,
    );
    let legacy = format!("\"memory\":\"{}\",", pro.memory);
    assert!(text.contains(&additions));
    text.replacen("\"snapshot_version\":4", "\"snapshot_version\":3", 1)
        .replacen(&additions, &legacy, 1)
        .into_bytes()
}

#[test]
fn v3_migration_retains_old_p_and_progress_and_initializes_only_c01_defaults() {
    let mut state = fresh_state();
    unlocked(&mut state.pro, 77);
    state.pro.processors = IntegralAmount::from_i128(9);
    state.pro.memory = IntegralAmount::from_i128(11);
    set_lifetime(&mut state.pro, "13000");
    state.pro.creativity_speed = positive("0.75");
    state.pro.standard_ops = positive("1000");
    state.pro.temporary_ops = positive("2");
    let current = Snapshot::capture(&state, 42).unwrap();
    let legacy = v3_payload_without_c01_fields(&current);
    let migrated = Snapshot::from_canonical_bytes(&legacy).unwrap();
    assert_eq!(migrated.snapshot_version, 4);
    assert_eq!(migrated.revision.get(), 42);
    let restored = migrated.restore().unwrap().state;
    // Old progress and P/M/Trust are verbatim; C01 cursor/speed/Ops are defaults.
    assert_eq!(restored.pro.trust.to_string(), "77");
    assert_eq!(restored.pro.processors.to_string(), "9");
    assert_eq!(restored.pro.memory.to_string(), "11");
    assert_eq!(restored.pro.lifetime_clips.to_string(), "13000");
    assert_eq!(restored.pro.next_trust_target.to_string(), "3000");
    assert_eq!(restored.pro.trust_target_predecessor.to_string(), "2000");
    assert_eq!(restored.pro.creativity_speed.to_string(), "1");
    assert_eq!(restored.pro.standard_ops.to_string(), "0");
    assert_eq!(restored.pro.temporary_ops.to_string(), "0");
    assert!(!restored.pro.computing_hidden);
    assert!(!restored.pro.projects_hidden);
    assert_eq!(restored.pro.console_messages, state.pro.console_messages);
    // No target observation or offline Ops was inferred by migration itself.
    assert_ne!(restored.pro.trust_target_predecessor.to_string(), "8000");
}
