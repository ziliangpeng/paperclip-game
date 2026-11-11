#!/usr/bin/env python3
"""Real Chrome/HTTP/SSE/SQLite evidence for #43-A Trust and allocation."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_api_process as api  # noqa: E402
import check_persistence_process as stored  # noqa: E402


def run(binary: Path, executable: str, version: str) -> dict[str, Any]:
    from browser_m2_c01 import load_m1_harness
    import browser_m2_c01 as unlock

    m1 = load_m1_harness()
    with m1.isolated_r2_browser(binary, executable, version, "m2-c01-award") as case:
        page, _, _ = case["browser"].new_page("/")
        state = case["state"]
        agent: api.Client = case["client"]
        started = time.monotonic()
        fresh = unlock.current(agent)
        assert fresh["game"]["computing_hidden"] is True
        assert fresh["game"]["available_trust"] == "0"
        assert fresh["game"]["next_trust_target"] == "3000"
        assert fresh["game"]["standard_ops"] == fresh["game"]["temporary_ops"] == "0"
        assert fresh["game"]["standard_ops_capacity"] == "1000"
        locked_dom = unlock.wait_dom(m1, page, lambda value: value.get("viewState") == "ready" and
                                     value["computingHidden"], "fresh #43-A native lock")
        assert locked_dom["availableTrust"] == "0" and locked_dom["standardOpsCapacity"] == "1000"
        for button_id, kind in (("add-processor", "add_processor"), ("add-memory", "add_memory")):
            hidden_controls = page.evaluate(f"""(() => {{
              const button = document.getElementById('{button_id}');
              return {{hidden: !!button.closest('[hidden]'), disabled: button.disabled,
                      text: button.textContent, type: button.type}};
            }})()""")
            assert hidden_controls == {"hidden": True, "disabled": False, "text":
                                      "Add Processor" if kind == "add_processor" else "Add Memory",
                                      "type": "submit"}, hidden_controls

        # Reach 2,000 exactly through public production/sales, just as #42 did.
        # Price buys never grant Trust or Ops; only actual clip counts cross 1,000.
        unlock.makes(agent, "award-initial-spool", 1000)
        for index in range(21):
            unlock.public(agent, "lower_price", f"award-initial-price-{index}")
        unlock.wait_current(m1, agent, lambda view: Decimal(view["game"]["funds"]) >= Decimal("26") and
                            view["game"]["computing_hidden"] is True, "award real funded pre-unlock stock")
        unlock.public(agent, "buy_wire", "award-first-replacement-wire")
        unlock.makes(agent, "award-second-spool", 999)
        assert unlock.current(agent)["game"]["lifetime_clips"] == "1999"
        native_unlock = unlock.native_make(m1, page, state)
        two_thousand = unlock.wait_current(m1, agent, lambda view:
            view["game"]["lifetime_clips"] == "2000" and not view["game"]["computing_hidden"],
            "native production unlock before allocation")
        base = two_thousand["game"]
        assert (base["trust"], base["processors"], base["memory"], base["available_trust"]) == ("2", "1", "1", "0"), base
        assert base["next_trust_target"] == "3000" and base["standard_ops"] == base["temporary_ops"] == "0"
        unlocked_dom = unlock.wait_dom(m1, page, lambda value: value["trust"] == "2" and
                                       not value["computingHidden"] and value["availableTrust"] == "0",
                                       "actual native 2000 unlock before first Trust award")

        def native_allocate(kind: str, button_id: str, key: str) -> dict[str, Any]:
            count = len(state.command_records)
            page.call("Page.bringToFront")
            page.evaluate(f"document.getElementById('{button_id}').focus()")
            page.press(key)
            record = m1.wait_commands(state, count + 1)[-1]
            m1.exact_command(record, kind)
            m1.wait_for(lambda: record.get("response_body"), lambda value: isinstance(value, dict),
                        f"native #43-A {kind} response")
            assert record["forwarded"] == 1 and record["response_status"] == 200, record
            assert record["response_body"]["status"] == "applied"
            assert set(record["json"]) == {"command_id", "type", "arguments"}
            assert record["json"]["arguments"] == {}
            return record

        def cross(target: int, successor: int, trust: str, processors: str, memory: str) -> dict[str, Any]:
            # Tickets change no game values; only serialized public production
            # can move Lifetime. Replenish each actually needed public spool.
            before = unlock.current(agent)
            remaining = target - int(before["game"]["lifetime_clips"])
            assert remaining >= 1, (target, before["game"])
            purchases = 0
            while int(before["game"]["wire"]) < remaining:
                unlock.wait_current(m1, agent, lambda view:
                    Decimal(view["game"]["funds"]) >= Decimal(view["game"]["wire_quote"]),
                    f"real Funds cover spool {purchases + 1} before {target}")
                unlock.public(agent, "buy_wire", f"award-wire-{target}-{purchases}")
                purchases += 1
                before = unlock.current(agent)
            assert int(before["game"]["wire"]) >= remaining
            unlock.makes(agent, f"award-before-{target}", remaining - 1)
            prior = unlock.current(agent)
            assert prior["game"]["lifetime_clips"] == str(target - 1)
            assert prior["game"]["next_trust_target"] == str(target)
            assert all(f"Trust target {target} reached" not in message
                       for message in prior["game"]["console_messages"])
            stream = api.SseClient(case["port"])
            assert stream.read_event() is not None
            record = unlock.native_make(m1, page, state)
            revision = record["response_body"]["revision"]
            frame = stream.next_revision(revision)
            game = frame["game"]
            message = f"Trust target {target} reached: +1 Trust; Processor/Memory capacity increased."
            assert game["lifetime_clips"] == str(target)
            assert (game["trust"], game["available_trust"]) == (trust, "1")
            assert (game["processors"], game["memory"]) == (processors, memory)
            assert game["next_trust_target"] == str(successor)
            assert game["console_messages"].count(message) == 1
            assert game["standard_ops"] == game["temporary_ops"] == "0"
            dom = unlock.wait_dom(m1, page, lambda value: value["trust"] == trust and
                                  value["nextTrustTarget"] == str(successor) and
                                  message in value["consoleMessages"],
                                  f"native {target} Trust announcement")
            for field, name in (("lifetime_clips", "lifetime"), ("trust", "trust"),
                                ("available_trust", "availableTrust"), ("next_trust_target", "nextTrustTarget"),
                                ("processors", "processors"), ("memory", "memory"),
                                ("standard_ops", "standardOps"), ("temporary_ops", "temporaryOps"),
                                ("standard_ops_capacity", "standardOpsCapacity")):
                assert dom[name] == game[field], (target, field, name)
            assert unlock.current(agent)["game"]["console_messages"].count(message) == 1
            stream.close()
            return {"request": record["json"], "response": record["response_body"],
                    "message": message, "sse": frame, "dom": dom, "target": target}

        first = cross(3000, 5000, "3", "1", "1")
        p_record = native_allocate("add_processor", "add-processor", "Enter")
        after_p = unlock.wait_current(m1, agent, lambda view:
            view["game"]["processors"] == "2" and view["game"]["memory"] == "1",
            "native actual Processor purchase")
        assert (after_p["game"]["trust"], after_p["game"]["available_trust"],
                after_p["game"]["next_trust_target"]) == ("3", "0", "5000")
        assert after_p["game"]["standard_ops_capacity"] == "1000"
        page_p = unlock.wait_dom(m1, page, lambda value: value["processors"] == "2" and
                                 value["availableTrust"] == "0", "native P=2/available=0 display")
        assert page_p["memory"] == "1" and page_p["standardOps"] == page_p["temporaryOps"] == "0"

        # A successful Processor allocation is replayed even now that capacity is
        # full. A conflicting type may never turn this cached success into Memory.
        same_status, same_raw = agent.post(p_record["raw"])
        same = api.checked_json(same_raw)
        assert same_status == 200 and same == p_record["response_body"], (same_status, same)
        conflict_payload = dict(p_record["json"])
        conflict_payload["type"] = "add_memory"
        conflict_status, conflict_raw = agent.post(json.dumps(conflict_payload, separators=(",", ":")).encode())
        conflict = api.checked_json(conflict_raw)
        assert conflict_status == 409 and conflict == {"status": "conflict"}, (conflict_status, conflict)
        still_allocated = unlock.current(agent)
        assert (still_allocated["game"]["processors"], still_allocated["game"]["memory"]) == ("2", "1")
        full_status, full_raw = agent.post(json.dumps({
            "command_id": "award-capacity-rejection", "type": "add_processor", "arguments": {},
        }, separators=(",", ":")).encode())
        full = api.checked_json(full_raw)
        assert full_status == 422 and full["reason"] == "trust_capacity_full", full

        second = cross(5000, 8000, "4", "2", "1")
        crossing_sse = second["sse"]
        expected_announcement = second["message"]
        dom_crossing = second["dom"]
        m_record = native_allocate("add_memory", "add-memory", "Space")
        after_m = unlock.wait_current(m1, agent, lambda view: view["game"]["memory"] == "2",
                                     "native actual Memory purchase")
        assert (after_m["game"]["trust"], after_m["game"]["processors"],
                after_m["game"]["memory"], after_m["game"]["available_trust"]) == ("4", "2", "2", "0")
        assert (after_m["game"]["standard_ops"], after_m["game"]["temporary_ops"],
                after_m["game"]["standard_ops_capacity"]) == ("0", "0", "2000")
        crossing_game = after_m["game"]
        page_m = unlock.wait_dom(m1, page, lambda value: value["memory"] == "2" and
                                 value["standardOpsCapacity"] == "2000" and value["availableTrust"] == "0",
                                 "native M=2/capacity 2000 display")
        assert page_m["standardOps"] == page_m["temporaryOps"] == "0"
        assert page_m["focus"] == "add-memory"

        # Real graceful-stop commit, no offline progress, and actual process restart.
        agent.close()
        old_backend = case["backendOwner"]
        old_backend.stop()
        saved = stored.read_snapshot(case["database"], availability_values={
            "computing_hidden": False, "projects_hidden": False,
        })
        pro = saved["pro"]
        assert (pro["trust"], pro["processors"], pro["memory"]) == ("4", "2", "2")
        assert (pro["next_trust_target"], pro["trust_target_predecessor"]) == ("8000", "5000")
        assert pro["creativity_speed"] == "1.645271921560140793", pro["creativity_speed"]
        assert pro["standard_ops"] == pro["temporary_ops"] == "0"
        assert pro["lifetime_clips"] == "5000"
        assert pro["console_messages"].count(expected_announcement) == 1
        new_out = (case["temporary"] / "award-restart.stdout").open("wb")
        new_err = (case["temporary"] / "award-restart.stderr").open("wb")
        with new_out, new_err:
            replacement = api.start_ready(binary, case["backendArguments"], case["port"],
                                          case["temporary"], new_out, new_err)
        case["backendOwner"] = replacement
        case["backendProcess"] = replacement.process
        agent = api.Client(case["port"])
        recovered = unlock.current(agent)
        assert recovered["run_id"] != crossing_sse["run_id"]
        for field in ("lifetime_clips", "trust", "available_trust", "next_trust_target",
                      "processors", "memory", "standard_ops", "temporary_ops", "standard_ops_capacity"):
            assert recovered["game"][field] == crossing_game[field], field
        assert recovered["game"]["console_messages"] == crossing_game["console_messages"]
        page.call("Page.reload", {"ignoreCache": True})
        recovered_dom = unlock.wait_dom(m1, page, lambda value: value.get("runId") == recovered["run_id"] and
                                        value["trust"] == "4" and value["nextTrustTarget"] == "8000",
                                        "native refreshed recovered Trust/allocation", timeout=15)
        assert recovered_dom["consoleMessages"].count(expected_announcement) == 1
        assert recovered_dom["standardOpsCapacity"] == "2000"
        unlock.public(agent, "raise_price", "award-post-recovery-continuation")
        continued = unlock.current(agent)
        assert continued["game"]["console_messages"].count(expected_announcement) == 1
        assert continued["game"]["trust"] == "4" and continued["game"]["next_trust_target"] == "8000"
        agent.close()
        replacement.stop()
        final_saved = stored.read_snapshot(case["database"], availability_values={
            "computing_hidden": False, "projects_hidden": False,
        })
        assert final_saved["pro"]["creativity_speed"] == pro["creativity_speed"]
        assert final_saved["pro"]["standard_ops"] == final_saved["pro"]["temporary_ops"] == "0"
        assert final_saved["pro"]["console_messages"].count(expected_announcement) == 1
        result = {
            "status": "pass", "publicStateInjection": False,
            "freshLocked": {"native": locked_dom["computingHidden"], "capacity": "1000"},
            "unlockReceipt": native_unlock["response_body"],
            "allocations": [
                {"type": p_record["json"]["type"], "request": p_record["json"], "response": p_record["response_body"],
                 "processors": "2", "memory": "1", "availableTrust": "0"},
                {"type": m_record["json"]["type"], "request": m_record["json"], "response": m_record["response_body"],
                 "processors": "2", "memory": "2", "availableTrust": "0", "standardOpsCapacity": "2000"},
            ],
            "sameProcessReplay": True, "conflictingRetryRejected": True, "capacityRejection": full,
            "trustCrossing": {"lifetime": "5000", "trust": "4", "next": "8000",
                               "announcement": expected_announcement, "sseRevision": crossing_sse["revision"],
                               "domRevision": dom_crossing["revision"], "duplicateAnnouncements": 0},
            "restart": {"v4": saved["snapshot_version"], "savedSpeed": pro["creativity_speed"],
                        "restoredSpeed": final_saved["pro"]["creativity_speed"], "trust": "4",
                        "next": "8000", "predecessor": "5000", "offlineOps": "0", "secondAward": False},
            "durationSeconds": round(time.monotonic() - started, 3),
        }
    return {**result, "browser": version, "realBackend": True,
            "chromeExit": case["chromeExit"], "backendExit": case["backendExit"]}
