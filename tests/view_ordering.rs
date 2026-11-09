use paperclip_game::api::GameView;
use paperclip_game::view_sync::{ViewDecision, ViewSynchronizer};
use serde_json::{Value, json};

fn view(run_id: &str, revision: u64, clips: &str) -> GameView {
    serde_json::from_value(view_json(run_id, revision, clips))
        .expect("complete typed test GameView")
}

fn view_json(run_id: &str, revision: u64, clips: &str) -> Value {
    json!({
        "schema_version": 1,
        "run_id": run_id,
        "revision": revision,
        "clock": {
            "update_count": revision,
            "fast_phase": 0,
            "second_phase": 0,
            "slow_phase": 0,
            "combat_remainder_nanos": 0,
            "combat_pulses": 0
        },
        "game": {
            "lifetime_clips": clips,
            "unsold_clips": clips,
            "unused_clips": clips,
            "wire": "999",
            "funds": "-41117.99",
            "demand": "3.2",
            "marketing_cost": "100",
            "clips_sold": "0",
            "income": "0",
            "last_sale_revenue": "0",
            "wire_spool_length": "1000",
            "wire_quote": "30000000000000000000000000000000000000000000000000000001",
            "price_per_clip": "0.000000000000000001",
            "marketing_level": "9007199254740993",
            "trust": "2",
            "processors": "1",
            "memory": "1",
            "computing_hidden": true,
            "projects_hidden": true,
            "auto_clipper_revealed": false,
            "auto_clippers": "0",
            "auto_clipper_cost": "5"
        }
    })
}

#[test]
fn same_run_ordering_covers_stream_get_lower_higher_and_equal_without_repeated_effects() {
    // SSE-SAME-RUN-ORDERING: healthy and known-bad delivery sequences.
    let mut client = ViewSynchronizer::default();
    let stream = client.open_stream();
    assert_eq!(
        client.accept_stream_initial(stream, view("R1", 12, "12")),
        ViewDecision::AdoptedNewRun
    );
    let get = client.request_view();
    assert_eq!(
        client.accept_stream_update(stream, view("R1", 11, "11")),
        ViewDecision::IgnoredLowerRevision
    );
    assert_eq!(
        client.current().unwrap().game.lifetime_clips.to_string(),
        "12"
    );
    assert_eq!(client.presentation_count(), 1);

    assert_eq!(
        client.accept_get(get, view("R1", 13, "13")),
        ViewDecision::Applied
    );
    assert_eq!(client.presentation_count(), 2);
    let before_equal = client.current().unwrap().clone();
    assert_eq!(
        client.accept_stream_update(stream, view("R1", 13, "999")),
        ViewDecision::EqualPresentationOnly
    );
    assert_eq!(client.current(), Some(&before_equal));
    assert_eq!(client.presentation_count(), 2);

    assert_eq!(
        client.accept_stream_update(stream, view("R1", 14, "14")),
        ViewDecision::Applied
    );
    assert_eq!(client.presentation_count(), 3);

    let newer_stream = client.open_stream();
    assert_eq!(
        client.accept_stream_update(stream, view("R1", 99, "99")),
        ViewDecision::IgnoredStaleSource
    );
    assert_eq!(
        client.accept_stream_initial(newer_stream, view("R1", 12, "12")),
        ViewDecision::IgnoredLowerRevision
    );
    assert_eq!(
        client.accept_stream_update(newer_stream, view("R1", 15, "15")),
        ViewDecision::Applied
    );
    assert_eq!(client.current().unwrap().revision.get(), 15);
}

#[test]
fn recovered_lower_revision_baseline_invalidates_old_run_streams_and_gets() {
    // SSE-RECOVERED-RUN-RESYNC: an older recovered full view is authoritative.
    let mut client = ViewSynchronizer::default();
    let old_stream = client.open_stream();
    assert_eq!(
        client.accept_stream_initial(old_stream, view("before-crash", 100, "100")),
        ViewDecision::AdoptedNewRun
    );
    let old_get = client.request_view();
    let reopened = client.open_stream();
    let recovered = view("recovered", 40, "40");
    assert_eq!(
        client.accept_stream_initial(reopened, recovered.clone()),
        ViewDecision::AdoptedNewRun
    );
    assert_eq!(client.current(), Some(&recovered));
    assert_eq!(client.presentation_count(), 2);

    for decision in [
        client.accept_stream_update(old_stream, view("before-crash", 101, "101")),
        client.accept_get(old_get, view("before-crash", 102, "102")),
        client.accept_stream_initial(reopened, view("before-crash", 103, "103")),
    ] {
        assert_eq!(decision, ViewDecision::IgnoredStaleSource);
        assert_eq!(client.current(), Some(&recovered));
    }
    assert_eq!(client.presentation_count(), 2);
    assert_eq!(
        client.accept_stream_update(reopened, view("recovered", 39, "39")),
        ViewDecision::IgnoredLowerRevision
    );
    assert_eq!(
        client.accept_stream_update(reopened, view("recovered", 41, "41")),
        ViewDecision::Applied
    );
}

#[test]
fn old_new_connections_late_get_and_noninitial_run_switch_cannot_take_authority() {
    let mut client = ViewSynchronizer::default();
    let initial = client.open_stream();
    assert_eq!(
        client.accept_stream_initial(initial, view("R1", 7, "7")),
        ViewDecision::AdoptedNewRun
    );
    let old_get = client.request_view();

    let superseded = client.open_stream();
    let active = client.open_stream();
    assert_eq!(
        client.accept_stream_initial(superseded, view("R2", 1, "1")),
        ViewDecision::IgnoredStaleSource
    );
    assert_eq!(
        client.accept_stream_update(active, view("other-run", 100, "100")),
        ViewDecision::IgnoredUnexpectedRun
    );
    assert_eq!(client.current().unwrap().run_id, "R1");

    // A GET issued in this epoch may establish a new baseline; all previously
    // issued traffic then becomes stale, including the formerly active stream.
    let current_get = client.request_view();
    assert_eq!(
        client.accept_get(current_get, view("R2", 2, "2")),
        ViewDecision::AdoptedNewRun
    );
    assert_eq!(
        client.accept_get(old_get, view("R2", 200, "200")),
        ViewDecision::IgnoredStaleSource
    );
    assert_eq!(
        client.accept_stream_update(active, view("R2", 3, "3")),
        ViewDecision::IgnoredStaleSource
    );
    assert_eq!(
        client.current().unwrap().game.lifetime_clips.to_string(),
        "2"
    );

    let same_epoch_get = client.request_view();
    let adoption = client.request_view();
    assert_eq!(
        client.accept_get(adoption, view("R3", 1, "1")),
        ViewDecision::AdoptedNewRun
    );
    assert_eq!(
        client.accept_get(same_epoch_get, view("R3", 999, "999")),
        ViewDecision::IgnoredStaleSource
    );
}

#[test]
fn complete_view_deserialization_rejects_bad_frames_and_preserves_exact_numeric_strings() {
    let healthy = view_json("run", 9_007_199_254_740_991, "0");
    let parsed: GameView = serde_json::from_value(healthy.clone()).unwrap();
    assert_eq!(parsed.revision.get(), 9_007_199_254_740_991);
    assert_eq!(parsed.game.funds.to_string(), "-41117.99");
    assert_eq!(
        parsed.game.price_per_clip.to_string(),
        "0.000000000000000001"
    );
    assert_eq!(parsed.game.marketing_level.to_string(), "9007199254740993");
    assert_eq!(parsed.game.marketing_cost.to_string(), "100");
    assert_eq!(parsed.game.demand.to_string(), "3.2");
    assert_eq!(parsed.game.clips_sold.to_string(), "0");
    assert_eq!(parsed.game.income.to_string(), "0");
    assert_eq!(parsed.game.last_sale_revenue.to_string(), "0");
    assert_eq!(
        parsed.game.wire_quote.to_string(),
        "30000000000000000000000000000000000000000000000000000001"
    );

    let cases = [
        ("missing full View field", {
            let mut bad = healthy.clone();
            bad.as_object_mut().unwrap().remove("clock");
            bad
        }),
        ("unknown persistence interior", {
            let mut bad = healthy.clone();
            bad["persistence"] = json!({"interior": true});
            bad
        }),
        ("JSON number Amount", {
            let mut bad = healthy.clone();
            bad["game"]["funds"] = json!(1.0);
            bad
        }),
        ("non-canonical Amount", {
            let mut bad = healthy.clone();
            bad["game"]["funds"] = json!("1.0");
            bad
        }),
        ("unsafe revision", {
            let mut bad = healthy.clone();
            bad["revision"] = json!(9_007_199_254_740_992_u64);
            bad
        }),
        ("partial game", {
            let mut bad = healthy.clone();
            bad["game"].as_object_mut().unwrap().remove("wire");
            bad
        }),
    ];
    for (label, bad) in cases {
        assert!(serde_json::from_value::<GameView>(bad).is_err(), "{label}");
    }
}
