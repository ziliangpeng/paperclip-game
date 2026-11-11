#!/usr/bin/env python3
"""Real-Chrome #42 unlock and #43-A public projection/capacity verification."""
from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

# Reuse the project's actual process and isolated-browser harnesses. This module
# opens only fresh anonymous browser profiles and fresh owned temporary databases.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_api_process as api  # noqa: E402
import check_persistence_process as stored  # noqa: E402


ANNOUNCEMENT = "Trust-Constrained Self-Modification"


def load_m1_harness() -> Any:
    path = Path(__file__).resolve().with_name("browser_m1.py")
    spec = importlib.util.spec_from_file_location("paperclip_browser_m1_for_m2_c01", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current(client: api.Client) -> dict[str, Any]:
    view = api.checked_json(client.get()[1])
    availability = {
        "computing_hidden": view["game"]["computing_hidden"],
        "projects_hidden": view["game"]["projects_hidden"],
    }
    api.assert_view_schema(view, availability_values=availability)
    assert availability["computing_hidden"] == availability["projects_hidden"]
    return view


def public(client: api.Client, kind: str, command_id: str) -> dict[str, Any]:
    status, raw = client.post(json.dumps({
        "command_id": command_id, "type": kind, "arguments": {},
    }, separators=(",", ":")).encode())
    body = api.checked_json(raw)
    assert status == 200 and body["status"] == "applied", (kind, status, body)
    return body


def makes(client: api.Client, label: str, count: int) -> None:
    for index in range(count):
        status, raw = client.make(f"{label}-{index}")
        body = api.checked_json(raw)
        assert status == 200 and body["status"] == "applied", (label, index, status, body)


def announcement_count(view: dict[str, Any]) -> int:
    return view["game"]["console_messages"].count(ANNOUNCEMENT)


def assert_unlocked_view(view: dict[str, Any], lifetime: str, wire: str) -> None:
    game = view["game"]
    assert game["lifetime_clips"] == lifetime, game
    assert game["wire"] == wire, game
    assert game["computing_hidden"] is False and game["projects_hidden"] is False, game
    assert (game["trust"], game["processors"], game["memory"]) == ("2", "1", "1"), game
    assert announcement_count(view) == 1, game["console_messages"]


def wait_dom(m1: Any, page: Any, predicate: Callable[[dict[str, Any]], bool],
             description: str, timeout: float = 10) -> dict[str, Any]:
    return m1.wait_for(lambda: m1.dom_state(page), predicate, description, timeout=timeout)


def wait_current(m1: Any, client: api.Client, predicate: Callable[[dict[str, Any]], bool],
                 description: str, timeout: float = 120) -> dict[str, Any]:
    return m1.wait_for(lambda: current(client), predicate, description, timeout=timeout)


def assert_native_unlock(dom: dict[str, Any], view: dict[str, Any], lifetime: str,
                         wire: str) -> None:
    game = view["game"]
    assert dom["viewState"] == "ready"
    assert dom["runId"] == view["run_id"]
    assert dom["computingHidden"] is False
    assert (dom["trust"], dom["processors"], dom["memory"]) == ("2", "1", "1")
    assert dom["lifetime"] == lifetime and dom["wire"] == wire
    assert dom["consoleMessages"] == game["console_messages"]
    assert dom["consoleMessages"].count(ANNOUNCEMENT) == 1


def native_make(m1: Any, page: Any, state: Any) -> dict[str, Any]:
    count = len(state.command_records)
    page.call("Page.bringToFront")
    page.evaluate("document.getElementById('make-paperclip').focus()")
    page.press("Enter")
    record = m1.wait_commands(state, count + 1)[-1]
    m1.exact_command(record, "make_paperclip")
    m1.wait_for(lambda: record.get("response_body"), lambda value: isinstance(value, dict),
                "actual M2-C01 native Make response")
    assert record["forwarded"] == 1 and record["response_status"] == 200, record
    assert record["response_body"]["status"] == "applied", record
    return record


def run_lifetime_route(m1: Any, binary: Path, executable: str, version: str) -> dict[str, Any]:
    with m1.isolated_r2_browser(binary, executable, version, "m2-c01-lifetime") as case:
        browser = case["browser"]
        state = case["state"]
        agent: api.Client = case["client"]
        page, _, _ = browser.new_page("/")
        started = time.monotonic()
        fresh = current(agent)
        assert fresh["game"]["computing_hidden"] is True
        assert fresh["game"]["projects_hidden"] is True
        assert (fresh["game"]["trust"], fresh["game"]["processors"],
                fresh["game"]["memory"]) == ("2", "1", "1")
        wait_dom(m1, page, lambda dom: dom.get("viewState") == "ready" and
                 dom["computingHidden"] and dom["trust"] == "2" and
                 dom["processors"] == dom["memory"] == "1", "fresh locked native panel")

        # This route cannot use the stranded shortcut: before the replacement spool,
        # selling the entire 1,000-clip inventory at $0.04 yields at least $40,
        # above the maximum $26 initial-base current Wire quote. Wire=1 then keeps
        # the route locked at exactly 1,999 until the native crossing Command.
        makes(agent, "m2-c01-lifetime-initial", 1000)
        for index in range(21):
            public(agent, "lower_price", f"m2-c01-lifetime-price-{index}")
        funded = wait_current(m1, agent, lambda view:
                              Decimal(view["game"]["funds"]) >= Decimal("26") and
                              view["game"]["computing_hidden"] is True,
                              "actual sales fund Wire without an early stranded unlock")
        assert Decimal(funded["game"]["unsold_clips"]) > 0
        public(agent, "buy_wire", "m2-c01-lifetime-replacement-wire")
        makes(agent, "m2-c01-lifetime-second-spool", 999)
        before = current(agent)
        assert before["game"]["lifetime_clips"] == "1999"
        assert before["game"]["wire"] == "1"
        assert before["game"]["computing_hidden"] is True
        assert before["game"]["projects_hidden"] is True
        assert before["game"]["console_messages"].count(ANNOUNCEMENT) == 0
        before_dom = wait_dom(m1, page, lambda dom: dom.get("lifetime") == "1999" and
                              dom["wire"] == "1" and dom["computingHidden"] and
                              ANNOUNCEMENT not in dom["consoleMessages"],
                              "native page genuinely locked at 1999 with Wire 1")

        # Commit and recover the actual pre-transition world before issuing the
        # crossing Command. This is a separate legal restart, not a state fixture.
        agent.close()
        pre_backend = case["backendOwner"]
        pre_backend.stop()
        pre_saved = stored.read_snapshot(case["database"])
        assert pre_saved["pro"]["computing_hidden"] is True
        assert pre_saved["pro"]["projects_hidden"] is True
        assert pre_saved["pro"]["lifetime_clips"] == "1999"
        assert pre_saved["pro"]["wire"] == "1"
        assert pre_saved["pro"]["console_messages"].count(ANNOUNCEMENT) == 0
        pre_restart_started = time.monotonic()
        pre_out = (case["temporary"] / "m2-c01-pre-restart.stdout").open("wb")
        pre_err = (case["temporary"] / "m2-c01-pre-restart.stderr").open("wb")
        with pre_out, pre_err:
            pre_replacement = api.start_ready(binary, case["backendArguments"], case["port"],
                                              case["temporary"], pre_out, pre_err)
        case["backendOwner"] = pre_replacement
        case["backendProcess"] = pre_replacement.process
        pre_restart_observation_seconds = time.monotonic() - pre_restart_started
        agent = api.Client(case["port"])
        before_recovered = current(agent)
        assert before_recovered["run_id"] != before["run_id"]
        assert before_recovered["game"]["lifetime_clips"] == "1999"
        assert before_recovered["game"]["wire"] == "1"
        assert before_recovered["game"]["computing_hidden"] is True
        assert before_recovered["game"]["projects_hidden"] is True
        assert before_recovered["game"]["console_messages"].count(ANNOUNCEMENT) == 0
        pre_update_delta = (before_recovered["clock"]["update_count"] -
                            pre_saved["clock"]["update_count"])
        assert 0 <= pre_update_delta <= 5000
        assert Decimal(pre_update_delta) * Decimal("0.01") <= Decimal(
            str(pre_restart_observation_seconds)) + Decimal("0.25")
        before_dom = wait_dom(m1, page, lambda dom:
                              dom.get("runId") == before_recovered["run_id"] and
                              dom.get("lifetime") == "1999" and dom["wire"] == "1" and
                              dom["computingHidden"] and
                              ANNOUNCEMENT not in dom["consoleMessages"],
                              "native pre-transition recovery remains locked", timeout=15)
        before = before_recovered

        stream = api.SseClient(case["port"])
        stream_initial = stream.read_event()
        assert stream_initial is not None
        assert stream_initial["game"]["computing_hidden"] is True
        commands_before_crossing = len(state.command_records)
        receipt = native_make(m1, page, state)
        revision = receipt["response_body"]["revision"]
        crossing_sse = stream.next_revision(revision)
        assert_unlocked_view(crossing_sse, "2000", "0")
        after = wait_current(m1, agent, lambda view: view["game"]["lifetime_clips"] == "2000" and
                             view["game"]["computing_hidden"] is False,
                             "HTTP GET observes the exact native 2000 crossing")
        assert_unlocked_view(after, "2000", "0")
        after_dom = wait_dom(m1, page, lambda dom: dom.get("lifetime") == "2000" and
                             dom["wire"] == "0" and not dom["computingHidden"] and
                             dom["consoleMessages"].count(ANNOUNCEMENT) == 1,
                             "native Computational Resources unlock at 2000")
        assert_native_unlock(after_dom, after, "2000", "0")
        for server_view in (crossing_sse, after):
            assert server_view["game"]["trust"] == after_dom["trust"]
            assert server_view["game"]["processors"] == after_dom["processors"]
            assert server_view["game"]["memory"] == after_dom["memory"]
        # Rendering the SSE transition emits no unlock/project/resource Command.
        m1.settle_dom(page)
        records = list(state.command_records[commands_before_crossing:])
        assert len(records) == 1 and records[0]["json"]["type"] == "make_paperclip", records

        old_run = after["run_id"]
        page.call("Page.reload", {"ignoreCache": True})
        refreshed = wait_dom(m1, page, lambda dom: dom.get("runId") == old_run and
                             dom.get("lifetime") == "2000" and not dom["computingHidden"] and
                             dom["consoleMessages"].count(ANNOUNCEMENT) == 1,
                             "same-run native refresh retains unlock and one message")
        assert_native_unlock(refreshed, after, "2000", "0")
        assert len(state.command_records) == commands_before_crossing + 1
        stream.close()
        reconnect = api.SseClient(case["port"], f"{old_run}:{revision}")
        reconnected = reconnect.read_event()
        assert reconnected is not None
        assert_unlocked_view(reconnected, "2000", "0")
        assert reconnected["game"]["console_messages"] == after["game"]["console_messages"]
        reconnect.close()

        # A normal graceful stop commits the actual unlocked world. Restart is a
        # recovery/readback device; no database edit or snapshot fixture is used.
        agent.close()
        old_backend = case["backendOwner"]
        old_backend.stop()
        saved = stored.read_snapshot(case["database"], availability_values={"computing_hidden": False, "projects_hidden": False})
        saved_pro = saved["pro"]
        assert saved_pro["computing_hidden"] is False and saved_pro["projects_hidden"] is False
        assert saved_pro["console_messages"].count(ANNOUNCEMENT) == 1
        assert saved_pro["lifetime_clips"] == saved_pro["unused_clips"] == "2000"
        assert saved_pro["wire"] == "0"
        assert (saved_pro["trust"], saved_pro["processors"], saved_pro["memory"]) == ("2", "1", "1")
        assert Decimal(saved_pro["unsold_clips"]) + Decimal(saved_pro["clips_sold"]) == Decimal("2000")
        pre_recovery_phases = stored.fast_phases_between(pre_saved, saved)
        stored.assert_rng_continuation(pre_saved["rng_state"], saved["rng_state"],
                                       pre_recovery_phases)
        downtime_started = time.monotonic()
        time.sleep(1.2)
        downtime_seconds = time.monotonic() - downtime_started
        restart_started = time.monotonic()
        new_out = (case["temporary"] / "m2-c01-restart.stdout").open("wb")
        new_err = (case["temporary"] / "m2-c01-restart.stderr").open("wb")
        with new_out, new_err:
            replacement = api.start_ready(binary, case["backendArguments"], case["port"],
                                          case["temporary"], new_out, new_err)
        case["backendOwner"] = replacement
        case["backendProcess"] = replacement.process
        restart_observation_seconds = time.monotonic() - restart_started
        agent = api.Client(case["port"])
        recovered = current(agent)
        assert recovered["run_id"] != old_run
        assert_unlocked_view(recovered, "2000", "0")
        assert recovered["game"]["console_messages"] == saved_pro["console_messages"]
        update_delta = recovered["clock"]["update_count"] - saved["clock"]["update_count"]
        assert 0 <= update_delta <= 5000
        assert Decimal(update_delta) * Decimal("0.01") <= Decimal(
            str(restart_observation_seconds)) + Decimal("0.25")
        recovered_dom = wait_dom(m1, page, lambda dom: dom.get("runId") == recovered["run_id"] and
                                 dom.get("lifetime") == "2000" and not dom["computingHidden"] and
                                 dom["consoleMessages"].count(ANNOUNCEMENT) == 1,
                                 "native new-run recovery adopts saved unlock", timeout=15)
        assert_native_unlock(recovered_dom, recovered, "2000", "0")
        # One later legal Command proves continuation; it cannot announce again.
        continued_receipt = public(agent, "raise_price", "m2-c01-post-recovery-continuation")
        continued = current(agent)
        assert continued["game"]["price_per_clip"] == "0.05"
        assert announcement_count(continued) == 1
        assert continued["game"]["computing_hidden"] is False
        assert continued["game"]["projects_hidden"] is False
        agent.close()
        replacement.stop()
        final_saved = stored.read_snapshot(case["database"], availability_values={"computing_hidden": False, "projects_hidden": False})
        phases = stored.fast_phases_between(saved, final_saved)
        stored.assert_rng_continuation(saved["rng_state"], final_saved["rng_state"], phases)
        assert final_saved["pro"]["console_messages"].count(ANNOUNCEMENT) == 1
        assert final_saved["pro"]["lifetime_clips"] == "2000"
        assert final_saved["pro"]["price_per_clip"] == "0.05"
        result = {
            "route": "lifetime_clips >= 2000",
            "freshLocked": {"api": fresh["game"]["computing_hidden"],
                            "native": before_dom["computingHidden"]},
            "preTransition": {"lifetime": before["game"]["lifetime_clips"],
                              "wire": before["game"]["wire"], "revision": before["revision"]},
            "preTransitionRecovery": {"savedRevision": pre_saved["revision"],
                                      "recoveredRevision": before_recovered["revision"],
                                      "remainedLocked": True, "runIdChanged": True,
                                      "onlineUpdateDelta": pre_update_delta,
                                      "restartObservationSeconds": round(pre_restart_observation_seconds, 3),
                                      "verifiedRngFastPhases": pre_recovery_phases},
            "nativeCrossing": {"receipt": receipt["response_body"],
                               "request": receipt["json"], "domRevision": after_dom["revision"],
                               "sseRevision": crossing_sse["revision"]},
            "refreshContinuity": True,
            "renderGeneratedUnlockCommands": 0,
            "recovery": {"runIdChanged": True, "savedRevision": saved["revision"],
                         "recoveredRevision": recovered["revision"],
                         "continuedReceiptRevision": continued_receipt["revision"],
                         "onlineUpdateDelta": update_delta,
                         "downtimeSeconds": round(downtime_seconds, 3),
                         "restartObservationSeconds": round(restart_observation_seconds, 3),
                         "offlineProduction": "0", "secondAnnouncement": False,
                         "verifiedRngFastPhases": phases},
            "noProjectOfferOrPurchase": True,
            "allocationScope": "implemented by #43-A native controls exercised in stranded route",
            "durationSeconds": round(time.monotonic() - started, 3),
        }
    return {**result, "browser": version, "realBackend": True,
            "chromeExit": case["chromeExit"], "backendExit": case["backendExit"],
            "publicStateInjection": False}


def run_stranded_route(m1: Any, binary: Path, executable: str, version: str) -> dict[str, Any]:
    with m1.isolated_r2_browser(binary, executable, version, "m2-c01-stranded") as case:
        browser = case["browser"]
        agent: api.Client = case["client"]
        page, _, _ = browser.new_page("/")
        started = time.monotonic()
        wait_dom(m1, page, lambda dom: dom.get("viewState") == "ready" and
                 dom["computingHidden"], "fresh stranded-route native lock")
        makes(agent, "m2-c01-stranded-initial", 1000)
        for index in range(24):
            public(agent, "lower_price", f"m2-c01-stranded-price-{index}")
        # The working $0.01 price accelerates real stock liquidation. Any early
        # higher-price sales are also legal; the assertion below reads the actual
        # Funds/current-quote relation rather than assuming a fixed revenue total.
        unlocked = wait_current(m1, agent, lambda view:
                                Decimal(view["game"]["lifetime_clips"]) < Decimal("2000") and
                                Decimal(view["game"]["unsold_clips"]) < Decimal("1") and
                                Decimal(view["game"]["funds"]) < Decimal(view["game"]["wire_quote"]) and
                                Decimal(view["game"]["wire"]) < Decimal("1") and
                                view["game"]["computing_hidden"] is False,
                                "actual public sales reach the independent stranded route")
        assert_unlocked_view(unlocked, "1000", "0")
        dom = wait_dom(m1, page, lambda value: value.get("lifetime") == "1000" and
                       value["wire"] == "0" and value["unsold"] == "0" and
                       not value["computingHidden"] and
                       value["consoleMessages"].count(ANNOUNCEMENT) == 1,
                       "native Computational Resources unlock through stranded route")
        assert_native_unlock(dom, unlocked, "1000", "0")
        stream = api.SseClient(case["port"])
        baseline = stream.read_event()
        assert baseline is not None
        assert_unlocked_view(baseline, "1000", "0")
        assert baseline["game"]["console_messages"] == unlocked["game"]["console_messages"]
        stream.close()
        control_ids = [button["id"] for button in dom["controls"]]
        assert not any("project" in control for control in control_ids), control_ids
        assert "add-processor" in control_ids and "add-memory" in control_ids, control_ids
        allocation_receipts = []
        for kind, button_id, key in (("add_processor", "add-processor", "Enter"),
                                     ("add_memory", "add-memory", "Space")):
            before = current(agent)
            command_count = len(case["state"].command_records)
            page.call("Page.bringToFront")
            page.evaluate(f"document.getElementById('{button_id}').focus()")
            page.press(key)
            record = m1.wait_commands(case["state"], command_count + 1)[-1]
            m1.exact_command(record, kind)
            m1.wait_for(lambda: record.get("response_body"), lambda value: isinstance(value, dict),
                        f"actual #43-A native {kind} rejection")
            assert record["forwarded"] == 1 and record["response_status"] == 422, record
            assert record["response_body"]["reason"] == "trust_capacity_full", record
            assert record["json"] == {"command_id": record["json"]["command_id"], "type": kind, "arguments": {}}
            rejected_dom = wait_dom(m1, page, lambda value: "capacity" in value["status"].lower(),
                                    f"native {kind} capacity rejection feedback")
            after = current(agent)
            for field in ("trust", "available_trust", "next_trust_target", "processors", "memory",
                          "standard_ops", "temporary_ops", "standard_ops_capacity"):
                assert after["game"][field] == before["game"][field], (kind, field)
                assert rejected_dom[{"trust": "trust", "available_trust": "availableTrust",
                                     "next_trust_target": "nextTrustTarget", "processors": "processors",
                                     "memory": "memory", "standard_ops": "standardOps",
                                     "temporary_ops": "temporaryOps", "standard_ops_capacity": "standardOpsCapacity"}[field]] == after["game"][field], field
            allocation_receipts.append({"request": record["json"], "response": record["response_body"]})
        result = {
            "route": "Unsold < 1 AND Funds < current Wire quote AND Wire < 1",
            "lifetime": unlocked["game"]["lifetime_clips"],
            "unsold": unlocked["game"]["unsold_clips"],
            "funds": unlocked["game"]["funds"],
            "wireQuote": unlocked["game"]["wire_quote"],
            "wire": unlocked["game"]["wire"],
            "apiSseNativeAnnouncementCount": 1,
            "browserRevision": dom["revision"],
            "apiRevision": unlocked["revision"],
            "allocationButtonsPresent": True,
            "nativeCapacityRejection": allocation_receipts,
            "noProjectOfferOrPurchase": True,
            "durationSeconds": round(time.monotonic() - started, 3),
        }
    return {**result, "browser": version, "realBackend": True,
            "chromeExit": case["chromeExit"], "backendExit": case["backendExit"],
            "publicStateInjection": False}


def run(binary: Path, executable: str, version: str) -> dict[str, Any]:
    """Registered by browser_m1.main after all unchanged M1 checks complete."""
    m1 = load_m1_harness()
    lifetime = run_lifetime_route(m1, binary, executable, version)
    stranded = run_stranded_route(m1, binary, executable, version)
    result = {
        "status": "pass",
        "scope": "M2-C01-A unlock plus #43-A public fields/rejections; not full-phase completion",
        "browser": version,
        "lifetimeRoute": lifetime,
        "strandedRoute": stranded,
        "browserRevisionEvidence": {
            "lifetime": lifetime["nativeCrossing"]["domRevision"],
            "stranded": stranded["browserRevision"],
        },
    }
    print("NATIVE_M2_C01_UNLOCK_EVIDENCE=" + json.dumps(result, separators=(",", ":")), flush=True)
    return result
