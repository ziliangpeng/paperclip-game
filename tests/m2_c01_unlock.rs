use paperclip_game::game::amount::{Amount, NonNegativeAmount};
use paperclip_game::game::economy::{
    COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE, computational_resources_unlock_condition,
    observe_computational_resources,
};
use paperclip_game::game::state::{GameState, ProState};
use paperclip_game::persistence::SnapshotStore;
use paperclip_game::runtime::GameRuntime;
use paperclip_game::snapshot::{SNAPSHOT_VERSION, Snapshot};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new() -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "paperclip-game-m2-c01-test-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated M2-C01 test directory");
        Self(path)
    }

    fn database(&self) -> PathBuf {
        self.0.join("state.sqlite3")
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn fresh_state() -> GameState {
    let executor = tokio::runtime::Runtime::new().expect("create test Tokio runtime");
    executor.block_on(async {
        let runtime = GameRuntime::start().expect("start fresh authoritative game");
        let state = runtime.handle().view().game;
        runtime.shutdown().await.expect("stop fresh game");
        state
    })
}

fn positive(text: &str) -> NonNegativeAmount {
    Amount::parse(text).unwrap().nonnegative().unwrap()
}

fn configure_route(
    state: &mut ProState,
    lifetime: &str,
    unsold: &str,
    funds: &str,
    quote: &str,
    wire: &str,
) {
    state.lifetime_clips = positive(lifetime);
    state.unused_clips = positive(lifetime);
    state.unsold_clips = positive(unsold);
    state.clips_sold = state
        .lifetime_clips
        .checked_sub(&state.unsold_clips)
        .expect("fixture Unsold cannot exceed Lifetime");
    state.funds = Amount::parse(funds).unwrap();
    state.wire_quote = Amount::parse(quote).unwrap();
    state.wire = positive(wire);
}

#[test]
fn exact_unlock_rule_table_covers_every_or_route_and_comparison_boundary() {
    let template = fresh_state().pro;
    let cases = [
        (
            "below Lifetime with every stranded conjunct false",
            "1999",
            "10",
            "100",
            "20",
            "10",
            false,
        ),
        (
            "exactly 2000 is independently sufficient",
            "2000",
            "10",
            "100",
            "20",
            "10",
            true,
        ),
        (
            "above 2000 remains sufficient",
            "2000.000000000000000001",
            "10",
            "100",
            "20",
            "10",
            true,
        ),
        (
            "just below 2000 cannot use the Lifetime route",
            "1999.999999999999999999",
            "1",
            "20",
            "20",
            "1",
            false,
        ),
        (
            "all stranded conjuncts unlock below 2000",
            "1999",
            "0",
            "0",
            "20",
            "0",
            true,
        ),
        (
            "Unsold 1 blocks the stranded route",
            "1999",
            "1",
            "0",
            "20",
            "0",
            false,
        ),
        (
            "positive sub-one Unsold satisfies its strict comparison",
            "1999",
            "0.999999999999999999",
            "0",
            "20",
            "0",
            true,
        ),
        (
            "Funds equal to the current quote blocks the stranded route",
            "1999",
            "0",
            "20",
            "20",
            "0",
            false,
        ),
        (
            "Funds immediately below the current quote satisfy their comparison",
            "1999",
            "0",
            "19.999999999999999999",
            "20",
            "0",
            true,
        ),
        (
            "Funds above the current quote block the stranded route",
            "1999",
            "0",
            "20.000000000000000001",
            "20",
            "0",
            false,
        ),
        (
            "Wire 1 blocks the stranded route",
            "1999",
            "0",
            "0",
            "20",
            "1",
            false,
        ),
        (
            "positive sub-one Wire satisfies its strict comparison",
            "1999",
            "0",
            "0",
            "20",
            "0.999999999999999999",
            true,
        ),
        (
            "each stranded conjunct is required: Unsold false",
            "1999",
            "1",
            "19",
            "20",
            "0.5",
            false,
        ),
        (
            "each stranded conjunct is required: Funds false",
            "1999",
            "0.5",
            "20",
            "20",
            "0.5",
            false,
        ),
        (
            "each stranded conjunct is required: Wire false",
            "1999",
            "0.5",
            "19",
            "20",
            "1",
            false,
        ),
        (
            "the Lifetime OR route ignores all three stranded failures",
            "2000",
            "1",
            "20",
            "20",
            "1",
            true,
        ),
        (
            "the stranded OR route does not require Lifetime 2000",
            "0",
            "0",
            "0",
            "20",
            "0",
            true,
        ),
    ];
    for (label, lifetime, unsold, funds, quote, wire, expected) in cases {
        let mut state = template.clone();
        configure_route(&mut state, lifetime, unsold, funds, quote, wire);
        assert_eq!(
            computational_resources_unlock_condition(&state),
            expected,
            "{label}"
        );
        assert_eq!(state.trust.to_string(), "2", "{label}: fresh Trust");
        assert_eq!(
            state.processors.to_string(),
            "1",
            "{label}: fresh Processor"
        );
        assert_eq!(state.memory.to_string(), "1", "{label}: fresh Memory");
    }
}

#[test]
fn first_observation_is_atomic_and_latched_without_relock_or_duplicate_feedback() {
    let mut state = fresh_state().pro;
    configure_route(&mut state, "1999", "1", "20", "20", "1");
    let before = state.clone();
    observe_computational_resources(&mut state);
    assert_eq!(state, before);

    configure_route(&mut state, "1999", "0", "19", "20", "0");
    observe_computational_resources(&mut state);
    assert!(!state.computing_hidden && !state.projects_hidden);
    assert_eq!(
        state.console_messages[4],
        COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE
    );
    assert_eq!(
        state
            .console_messages
            .iter()
            .filter(|message| *message == COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE)
            .count(),
        1
    );
    let unlocked = state.clone();

    // Once visible, neither false source conditions nor repeated observations
    // can clear the latch again or append another transition announcement.
    configure_route(&mut state, "1", "1", "100", "20", "1000");
    state.funds = Amount::from_i128(100);
    for _ in 0..8 {
        observe_computational_resources(&mut state);
        assert!(!state.computing_hidden && !state.projects_hidden);
        assert_eq!(state.console_messages, unlocked.console_messages);
    }
}

fn assert_recovered_state(expected: &GameState, actual: &GameState) {
    assert_eq!(actual.pro, expected.pro);
    assert_eq!(actual.clock, expected.clock);
    assert_eq!(actual.rng_state_hex(), expected.rng_state_hex());
}

fn roundtrip(snapshot: &Snapshot) -> GameState {
    assert_eq!(snapshot.snapshot_version, SNAPSHOT_VERSION);
    let bytes = snapshot.to_canonical_bytes().unwrap();
    Snapshot::from_canonical_bytes(&bytes)
        .unwrap()
        .restore()
        .unwrap()
        .state
}

#[test]
fn real_sqlite_pre_and_post_transition_snapshots_restore_complete_latched_state() {
    let directory = TestDirectory::new();
    let mut before = fresh_state();
    configure_route(&mut before.pro, "1999", "1999", "100", "20", "1");
    before.pro.income = Amount::parse("12.34").unwrap();
    before.pro.clips_sold = NonNegativeAmount::zero();
    before.pro.console_messages = std::array::from_fn(|index| {
        if index == 3 {
            "Pre-transition M1 feedback.".to_owned()
        } else {
            String::new()
        }
    });
    let before_snapshot = Snapshot::capture(&before, 41).unwrap();
    let path = directory.database();
    let (store, stored) = SnapshotStore::open_or_initialize(&path, &before_snapshot).unwrap();
    assert_recovered_state(&before, &stored.snapshot.restore().unwrap().state);
    drop(store);
    let (_, stored) = SnapshotStore::open_or_initialize(&path, &before_snapshot).unwrap();
    let mut before_restored = stored.snapshot.restore().unwrap().state;
    assert_recovered_state(&before, &before_restored);
    observe_computational_resources(&mut before_restored.pro);
    assert_recovered_state(&before, &before_restored);

    // This is a pure persistence fixture, not a claim of public state injection.
    // The separate runtime/API/browser cases execute the actual crossing paths.
    let mut after = before.clone();
    configure_route(&mut after.pro, "2000", "2000", "100", "20", "0");
    observe_computational_resources(&mut after.pro);
    assert!(!after.pro.computing_hidden && !after.pro.projects_hidden);
    let after_snapshot = Snapshot::capture(&after, 42).unwrap();
    let (mut store, _) = SnapshotStore::open_or_initialize(&path, &before_snapshot).unwrap();
    store.commit(1, &after_snapshot).unwrap();
    drop(store);

    let (_, stored) = SnapshotStore::open_or_initialize(&path, &before_snapshot).unwrap();
    assert_eq!(stored.capture_sequence, 1);
    assert_eq!(stored.snapshot.restore().unwrap().revision, 42);
    let mut after_restored = roundtrip(&stored.snapshot);
    assert_recovered_state(&after, &after_restored);
    assert_eq!(after_restored.pro.trust.to_string(), "2");
    assert_eq!(after_restored.pro.processors.to_string(), "1");
    assert_eq!(after_restored.pro.memory.to_string(), "1");
    assert_eq!(
        after_restored
            .pro
            .console_messages
            .iter()
            .filter(|message| *message == COMPUTATIONAL_RESOURCES_UNLOCK_MESSAGE)
            .count(),
        1
    );
    let exact_restored = after_restored.clone();
    for _ in 0..4 {
        observe_computational_resources(&mut after_restored.pro);
        assert_recovered_state(&exact_restored, &after_restored);
    }
    // Capture, serialization and restore never advance a clock or the RNG and
    // consequently cannot create offline production or a second announcement.
    assert_eq!(after_restored.clock, after.clock);
    assert_eq!(after_restored.rng_state_hex(), after.rng_state_hex());
    assert_eq!(after_restored.pro.lifetime_clips, positive("2000"));
}
