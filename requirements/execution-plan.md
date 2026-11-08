# Complete Game Execution Plan

**Status:** complete planning candidate for Issue #4. It is not approved, merged, implemented, independently reviewed, or a claim that CI or gameplay tests have passed. The plan becomes execution-effective only after the required review, normal merge, and main-branch verification.

Planning baseline: `80feca9dcd5fa4b0dea53601f7277e95d78e5134`. Canonical inventory: [gameplay-inventory.json](./data/gameplay-inventory.json), SHA-256 `d64b549425fa87ad87e240be00abac282001a06906670bb2a3eea04fc1c74c3e`. Structured plan: [execution-plan.json](./data/execution-plan.json). Validators: [inventory](../scripts/validate_inventory.py) and [execution plan](../scripts/validate_execution_plan.py). Planning workflow: [validate-plan.yml](../.github/workflows/validate-plan.yml).

The five gameplay documents and `requirements/runtime.md`, `clients.md`, `testing.md`, `product.md`, `milestones.md`, and `README.md` remain authoritative. This plan maps them; it does not create a second gameplay registry or change their semantics. All future runtime behavior and tests below are planned, not executed results.

## 1. Delivery contract and complete route

Fifteen playable vertical milestones cover all 274 canonical features exactly once. Seven exclusions remain non-implementations. All 32 aliases, 96 ordered project bindings, and 61 active HTML handlers are reconciled. There is no infrastructure-only M0 and no invented restart after Reject credits. Accept/Reject and the two prestige destinations are proved in legitimate independent branch instances, never one impossible all-endings save.

| Milestone | Playable increment | Features | Ordered projects | Tasks | Granularity | Milestone dependencies |
|---|---|---:|---:|---:|---|---|
| M1 | Human clips, Wire, sales, and first automation | 19 | 0 | 10 | current_detailed | None |
| M2 | Trust-constrained self-modification and foundational Projects | 38 | 19 | 3 | next_coarse | `M1` |
| M3 | Scaled Human automation, Quantum Computing, and alternate reset | 20 | 9 | 1 | mapped_future | `M2` |
| M4 | Investments, Yomi, and the complete strategy pool | 37 | 19 | 1 | mapped_future | `M2`, `M3` |
| M5 | Late-Human Trust routes, AutoTourney, and HypnoDrone release | 11 | 7 | 1 | mapped_future | `M2`, `M3`, `M4` |
| M6 | Autonomous matter, Wire, factories, and continuous Power | 20 | 5 | 1 | mapped_future | `M5` |
| M7 | Capital recovery, Momentum, and quadratic industrial upgrades | 15 | 7 | 1 | mapped_future | `M6` |
| M8 | Swarm Work/Think, Gifts, Boredom, and Disorganization | 10 | 1 | 1 | mapped_future | `M7` |
| M9 | Earth exhaustion and the Space Exploration handoff | 3 | 1 | 1 | mapped_future | `M8` |
| M10 | Probe design, growth, recovery, and live direct Combat | 50 | 5 | 1 | mapped_future | `M9`, `M4`, `M8` |
| M11 | OODA, named battles, signed Honor, and Max Trust | 14 | 5 | 1 | mapped_future | `M10` |
| M12 | Universal achievement, Emperor dialogue, and mutually exclusive choice | 11 | 9 | 1 | mapped_future | `M10` |
| M13 | Accept destinations, persistent prestige, and clean restart | 5 | 2 | 1 | mapped_future | `M12` |
| M14 | Reject teardown: Probes through Memory | 14 | 7 | 1 | mapped_future | `M12` |
| M15 | Final positive Wire conversion, exact-zero credits, and full-game closure | 7 | 0 | 1 | mapped_future | `M11`, `M12`, `M13`, `M14` |
| **Total** | **Complete game and independent branches** | **274** | **96** | **26** | M1 detailed; M2 coarse; M3-M15 mapped outlines | |

M1 is genuinely playable: manual one-clip production leads through sales/Funds, Wire, Price and Marketing to a permanent Funds-first $5 AutoClipper reveal and legal one-clip/s base production under continuous server time. Only M1 has detailed one-Issue/one-PR tasks. M2 has three coarse packages. M3-M15 remain complete mapped outlines rather than a premature backlog.

## 2. M1 detailed task DAG and one-PR contracts

The single final assembly is `M1-PLAYABLE-INTEGRATION`; there is no separate duplicate coverage or final-integration PR. Shared technical tasks supply state, transport, persistence and UI primitives. G01/G02/G03 own primary gameplay acceptance for all 19 M1 features without re-owning those primitives.

| Stable task ID | One independently testable PR objective | Direct predecessors | Primary gameplay ownership |
|---|---|---|---|
| `M1-BOOTSTRAP-CI` | Rust workspace and executable baseline CI | Planning baseline (no task predecessor) | Supporting platform only; no primary canonical feature ownership |
| `M1-RUNTIME-CORE` | Authoritative runtime clock and manual-conversion anchor | `M1-BOOTSTRAP-CI` | Supporting platform only; no primary canonical feature ownership |
| `M1-API-COMMANDS-VIEW` | Typed Commands, full View, and process-lifetime retry contract | `M1-RUNTIME-CORE` | Supporting platform only; no primary canonical feature ownership |
| `M1-PERSISTENCE-RECOVERY` | Transactional full snapshots, safe startup, and health | `M1-RUNTIME-CORE` | Supporting platform only; no primary canonical feature ownership |
| `M1-SSE-VIEW-SYNC` | Full-view SSE, reconnect, and recovered-run synchronization | `M1-API-COMMANDS-VIEW`, `M1-PERSISTENCE-RECOVERY` | Supporting platform only; no primary canonical feature ownership |
| `M1-NATIVE-TWO-PAGE-UI` | Accessible native two-page client and real manual control | `M1-SSE-VIEW-SYNC` | Supporting platform only; no primary canonical feature ownership |
| `M1-G01` | Initial state, legal manual conversion, and three ledgers | `M1-NATIVE-TWO-PAGE-UI` | `ACT-CLIP-MANUAL`, `UI-TOP-CLIPS`, `RES-CLIPS`, `PROG-START` |
| `M1-G02` | Human Business market, Wire supply, and stochastic sales | `M1-G01` | `ACT-PRICE-LOWER`, `ACT-PRICE-RAISE`, `ACT-MARKETING-BUY`, `ACT-WIRE-BUY`, `SYS-DEMAND-SALES`, `SYS-WIRE-MARKET`, `UI-BUSINESS`, `RES-WIRE`, `RES-FUNDS`, `RES-DEMAND-MARKETING`, `RES-SALES-STATS`, `PROG-DEMAND-SALES` |
| `M1-G03` | First real AutoClipper automation and feedback | `M1-G01`, `M1-G02`, `M1-PERSISTENCE-RECOVERY` | `ACT-AUTOCLIPPER-BUY`, `UI-CONSOLE`, `UI-MANUFACTURING` |
| `M1-PLAYABLE-INTEGRATION` | Assemble and prove the selected first playable vertical milestone | `M1-BOOTSTRAP-CI`, `M1-RUNTIME-CORE`, `M1-API-COMMANDS-VIEW`, `M1-PERSISTENCE-RECOVERY`, `M1-SSE-VIEW-SYNC`, `M1-NATIVE-TWO-PAGE-UI`, `M1-G01`, `M1-G02`, `M1-G03` | Cross-layer proof only; all 19 remain with G01/G02/G03 |

### M1-BOOTSTRAP-CI — Rust workspace and executable baseline CI

**Objective.** Create the stable Rust/Axum/Tokio/Serde project skeleton and a real Linux CI job that builds and tests it while retaining the existing inventory checks; do not present the skeleton as playable gameplay.

**Specification references (actual document and unique heading).**
- [AGENTS.md](../AGENTS.md) — `1. Work authorization and unit of delivery`
- [AGENTS.md](../AGENTS.md) — `2. Milestones, dependencies, and Issue content`
- [AGENTS.md](../AGENTS.md) — `3. Implementation, tests, and evidence`
- [AGENTS.md](../AGENTS.md) — `4. Independent Agent review`
- [requirements/runtime.md](./runtime.md) — `5. Technology Stack — CONFIRMED`
- [requirements/testing.md](./testing.md) — `1. Principles — CONFIRMED`
- [requirements/testing.md](./testing.md) — `6. Review and Merge Evidence`

**Scope.**
- Add one Rust stable library/binary workspace with locked dependencies needed by the M1 server, native static-file serving, Serde, Tokio, Axum, and SQLite.
- Add typed process configuration with proposed 127.0.0.1:3000 listener and repo-relative data/paperclip.sqlite3 database defaults plus explicit overrides; prohibit configuration that selects actors/instances, writes resources, pauses time, or requests offline catchup.
- Add root formatting, lint, test, inventory-validation, whitespace, and English/public-hygiene commands to a Linux workflow that runs on the actual Rust manifest.
- Add runtime artifact/database/cache ignore rules and a minimal non-game binary entry point so later tasks have a real integration host.
- Document the actual local and CI commands and their limits in the implementation PR.

**Non-goals.**
- No GameRuntime, gameplay rule, browser application, public debug control, or completed playable-milestone claim.
- No Python backend, frontend build chain, generated official fixture, private capture, or credential-dependent CI.
- No conditional job that skips Cargo because a manifest is absent; no weakening or deleting existing validation.

**Dependencies and reasons.**
- Planning baseline after the complete plan is reviewed, merged, and verified; no M0 or hidden predecessor.

**Acceptance criteria and scenarios.**
- **AC1:** A clean checkout produces the locked Rust library and binary with the confirmed stable toolchain and no private source files. Scenarios: `CI-BOOTSTRAP-REAL-MANIFEST`.
- **AC2:** The workflow actually executes format checking, Clippy, tests, the public inventory validator, and repository hygiene checks; private-source validation remains separate local evidence and is never replaced by a public-source download. The job fails on a genuine Rust or validation failure. Scenarios: `CI-BOOTSTRAP-REAL-MANIFEST`.
- **AC3:** Configuration parsing accepts valid listener/database overrides and rejects invalid values before opening or replacing game data; defaults contain no private absolute path or secret setting. Scenarios: `API-DEFAULT-NAMESPACE-BOUNDARY`.
- **AC4:** The binary starts only far enough to validate the host composition or exits with an explicit not-yet-initialized message; no placeholder HTTP command reports gameplay success. Scenarios: `API-COMMAND-SCHEMA-BOUNDARIES`.
- **AC5:** The PR records real command output at its HEAD and obtains the independent reviews required for CI/core infrastructure. Scenarios: `CI-BOOTSTRAP-REAL-MANIFEST`.

**Required tests.**
- Layers `rule_unit`, `state_sequence`; acceptance `AC1`; scenarios `CI-BOOTSTRAP-REAL-MANIFEST`. Native Rust gate: Run the future repository commands for cargo fmt --check, cargo clippy --all-targets -- -D warnings, cargo test --all-targets, and cargo build --locked.
- Layers `rule_unit`; acceptance `AC2`; scenarios `CI-BOOTSTRAP-REAL-MANIFEST`. Existing inventory regression: Run python3 -B scripts/validate_inventory.py requirements/data/gameplay-inventory.json and the existing source-independent validator checks; use private pinned sources only in local evidence when explicitly available, never in CI.
- Layers `rule_unit`, `api_contract`; acceptance `AC3`; scenarios `API-DEFAULT-NAMESPACE-BOUNDARY`. Configuration validation: Exercise default settings, valid listener and database-path overrides, malformed values, and attempts to supply non-gameplay/debug configuration in a temporary environment.
- Layers `rule_unit`, `state_sequence`; acceptance `AC4`; scenarios `CI-BOOTSTRAP-REAL-MANIFEST`. CI negative control: In a temporary private mutation copy, introduce one compile error and one inventory error and run the same job logic.
- Layers `rule_unit`; acceptance `AC5`; scenarios `CI-BOOTSTRAP-REAL-MANIFEST`. Public artifact inspection: Inspect the full diff, lockfile, workflow, generated outputs, and logs for CJK, credentials, private paths/hosts, captures, and generated caches.

**Evidence required by the future implementation PR.**
- Native Rust gate: Actual successful outputs on the implementation HEAD and on the latest-main merge result.
- Existing inventory regression: The public validator passes in CI; any separately run private-source result identifies local evidence without uploading source material.
- Configuration validation: Valid settings are typed and sanitized in logs; invalid settings fail before data mutation, and no debug/time/instance/resource option is recognized.
- CI negative control: Each mutation fails the corresponding real command; the original repository is unchanged.
- Public artifact inspection: A clean public-scope result and no claim that infrastructure is a playable game.

**Risk and review.** `test_ci_merge_infrastructure`, `security_data_main`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `src/lib.rs`, `src/main.rs`, `src/config.rs`, `.github/workflows/rust.yml`, `.gitignore`, `scripts/check_public_hygiene.py`

### M1-RUNTIME-CORE — Authoritative runtime clock and manual-conversion anchor

**Objective.** Implement GameRuntime-owned state, one writer for Commands and fixed-step ticks, explicit lag/RNG/numeric contracts, and the real one-Wire manual Make Paperclip operation as a pure-engine integration anchor.

**Specification references (actual document and unique heading).**
- [requirements/runtime.md](./runtime.md) — `1. Authoritative State — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `2. Real-Time Simulation — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `3. Concurrent Command Semantics — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `4. Current Instance Model — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `5. Technology Stack — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `6. Online Persistence — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `8. Subsequent Implementation Details — PROPOSED / OPEN`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `Three clip ledgers and shared resource routing`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-MILESTONES — Ordered production messages and elapsed-time feedback`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-CLIP-PRODUCTION` - shared conversion and matter chain`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `8. Implementation boundaries and dependencies`
- [requirements/product.md](./product.md) — `4. Gameplay Fidelity Boundaries — CONFIRMED`
- [requirements/testing.md](./testing.md) — `1. Principles — CONFIRMED`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `3. Rule and Numeric Verification — CONFIRMED`
- [requirements/testing.md](./testing.md) — `4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED`
- [requirements/testing.md](./testing.md) — `5. UI Acceptance — CONFIRMED`
- [requirements/testing.md](./testing.md) — `6. Review and Merge Evidence`

**Scope.**
- Define GameState with the exact source initial three clip ledgers, Wire and other fields required by the selected M1 gameplay contracts; keep process metadata separate from game state.
- Implement GameRuntime with bounded Command intake, single-writer validation/application, monotonic fixed-step scheduling, bounded online lag batches without discarded debt, revision accounting, and injected production/random-clock interfaces for pure tests.
- Implement the ordinary shared Wire conversion floor/cap/equal-ledger helper and the legal manual one-unit intent; compute a controlled sequence for later stochastic M1 systems.
- Select and document the M1 numeric/serialization invariants, proposed 10 ms quantum and ten-tick maximum lag batch, and prove no offline advancement is hidden in the clock type.
- Integrate the gameplay-map owner's ACT-CLIP-MANUAL/PROG-START implementation without duplicating that feature under a second task owner.

**Non-goals.**
- No public arbitrary requested-number clip conversion, AutoClipper/factory bypass, or below-one ordinary manual permission.
- No public pause/step/clock API, turn-based Command advancement, browser-driven clock, exact JavaScript scheduler compatibility, or offline backfill.
- No late-game universal framework or hardcoded all-game rule table; later feature tasks extend domain state and scheduling.
- No HTTP, SSE, SQLite, or native UI implementation in this PR beyond interfaces required for pure runtime integration.

**Dependencies and reasons.**
- `M1-BOOTSTRAP-CI`: The stable Rust workspace, dependency lock, configuration, and real CI host are required before runtime code can be integrated and tested.

**Acceptance criteria and scenarios.**
- **AC1:** Fresh state matches the selected source initial values; one legal manual Command consumes exactly one Wire and adds exactly one to each of lifetime, Unsold, and Unused ledgers, while below-one Wire rejects without mutation. Scenarios: `ENG-WIRE-MANUAL-FLOOR`.
- **AC2:** The internal helper permits a source-grounded fractional automatic request only with Wire at least one, caps it by current Wire, and updates all three ledgers by the actual amount; no public caller can supply that request. Scenarios: `ENG-WIRE-AUTOMATIC-FLOOR-CAP`.
- **AC3:** Commands and test-driven ticks have one explicit serial order, validation occurs at execution, state remains coherent under contention, and rejected operations leave state/revision unchanged. Scenarios: `CONC-COMMANDS-BOTH-LEGAL`, `CONC-COMMANDS-ONE-STOCK`, `ENG-TICK-COMMAND-SERIALIZATION`.
- **AC4:** Ticks progress from the runtime clock with zero external clients and without a Command; lag debt is bounded per writer turn but not dropped, and scheduling fairly services queued Commands. Scenarios: `RT-NO-CLIENTS-CONTINUOUS`.
- **AC5:** Selected numeric values remain finite and serde round trips preserve all chosen representations; capped conversion assigns exact zero when all available Wire is consumed rather than introducing an epsilon gate. Scenarios: `ENG-WIRE-AUTOMATIC-FLOOR-CAP`.

**Required tests.**
- Layers `rule_unit`, `property`; acceptance `AC1`, `AC2`; scenarios `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`. Initial-state and conversion rules: Use pure rule tests for fresh values, ordinary full conversions, Wire exactly one, Wire below one, request greater than stock, request below stock, fractional automatic output, and exact capped exhaustion.
- Layers `state_sequence`, `concurrency`, `property`; acceptance `AC3`; scenarios `CONC-COMMANDS-BOTH-LEGAL`, `CONC-COMMANDS-ONE-STOCK`, `ENG-TICK-COMMAND-SERIALIZATION`. Writer sequence/property tests: Compare generated Commands and fixed-step ticks against a serial reference model, including two legal manual Commands, final-Wire contention, and tick-versus-writer boundaries.
- Layers `state_sequence`, `long_simulation`; acceptance `AC4`; scenarios `RT-NO-CLIENTS-CONTINUOUS`. Clock and lag tests: Drive a fake monotonic clock through ordinary time, multiple lag batches, Command flood, and a simulated startup boundary; do not use long sleeps.
- Layers `rule_unit`, `property`; acceptance `AC5`; scenarios `ENG-WIRE-AUTOMATIC-FLOOR-CAP`. Numeric/RNG evidence: Round-trip selected integer/f64 types and a controlled RNG state, reject non-finite state generation, and replay a controlled random sequence in pure tests.

**Evidence required by the future implementation PR.**
- Initial-state and conversion rules: Wire and all three ledgers match the actual min-capped amount on every accepted path and remain unchanged on rejection.
- Writer sequence/property tests: No lost update, double-spend, negative stock, or result inconsistent with the recorded serial order.
- Clock and lag tests: Equivalent online elapsed time yields equivalent economic steps; debt is retained, Commands receive service, and startup creates no elapsed-time debt.
- Numeric/RNG evidence: Finite exact representation round trips, reproducible test failures, and no random draw from a View/clock helper.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/game/mod.rs`, `src/game/state.rs`, `src/game/conversion.rs`, `src/game/clock.rs`, `src/runtime.rs`, `tests/runtime_core.rs`

### M1-API-COMMANDS-VIEW — Typed Commands, full View, and process-lifetime retry contract

**Objective.** Expose GET /api/game/view and POST /api/game/commands with strict typed normalization, execution-time authority, first-terminal-result retries, in-flight coalescing, conflicts, revision/run_id metadata, and the real manual-conversion anchor.

**Specification references (actual document and unique heading).**
- [requirements/runtime.md](./runtime.md) — `1. Authoritative State — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `3. Concurrent Command Semantics — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `4. Current Instance Model — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/clients.md](./clients.md) — `1. Default Game Is Transparent to Users — CONFIRMED`
- [requirements/clients.md](./clients.md) — `2. External Interface Shape — PROPOSED`
- [requirements/clients.md](./clients.md) — `3. Commands — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `4. GameView — CONFIRMED / PROPOSED`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `8. Implementation boundaries and dependencies`

**Scope.**
- Serve a pure derived full GameView with schema_version, run_id, revision, and all currently implemented public M1 fields; never expose internal RNG/retry/persistence state.
- Adopt the proposed required opaque command_id envelope and closed typed Command enum, starting with make_paperclip {}; add only source-legal M1 variants owned by integrated gameplay tasks.
- Implement typed normalization, structural-error handling without execution binding, Pending/Terminal retry entries, waiter coalescing, first success/rule-rejection replay, and same-key/different-payload HTTP 409 without mutation.
- Retain terminal bindings for the whole process, keep them out of snapshots, and ensure HTTP disconnect after writer acceptance cannot cancel or duplicate the operation.
- Use no actor/game_id/observed-revision/resource-total fields; default routing is implicit and stale Views never categorically reject legal Commands.

**Non-goals.**
- No fake success for unimplemented command types, generic arbitrary-number economic operation, operator resource/time write, actor role, lobby, or instance registry.
- No command result presented as a newer View or browser-side authoritative totals; no cross-crash exactly-once claim.
- No TTL/LRU eviction of terminal results that would violate process-lifetime retries; no speculative distributed idempotency service.
- No SSE, browser, or persistence implementation in this PR except API seams and run/revision behavior needed by those tasks.

**Dependencies and reasons.**
- `M1-RUNTIME-CORE`: Authoritative state, single-writer execution, legal internal conversion, and continuous fake-testable time are shared prerequisites.

**Acceptance criteria and scenarios.**
- **AC1:** GET returns a consistent full View and POST returns the documented applied or rule_rejected result; unknown actions/fields and malformed arguments cannot mutate state or reserve a retry key. Scenarios: `API-COMMAND-SCHEMA-BOUNDARIES`.
- **AC2:** Concurrent identical requests queue exactly one writer execution and receive the same first result; sequential retries after success and rule rejection also return that first status/body without additional revision/mutation. Scenarios: `API-COMMAND-ID-INFLIGHT-SAME`, `API-COMMAND-ID-TERMINAL-SUCCESS`, `API-COMMAND-ID-TERMINAL-REJECTION`.
- **AC3:** Same-key/different-normalized-payload requests receive HTTP 409 during pending and after terminal completion, leave the original binding intact, and cause no state/revision change. Scenarios: `API-COMMAND-ID-CONFLICT`.
- **AC4:** Two new IDs represent two new legal intents and can both execute; final-stock contention succeeds only as affordability permits, and one client's retry never blocks another client's different legal Command. Scenarios: `CONC-COMMANDS-BOTH-LEGAL`, `CONC-COMMANDS-ONE-STOCK`, `API-COMMAND-ID-INFLIGHT-SAME`.
- **AC5:** All currently implemented M1 controls use execution-time validation; unimplemented future controls are unknown_command rather than permissive stubs, and the manual anchor is genuinely usable through HTTP. Scenarios: `API-COMMAND-SCHEMA-BOUNDARIES`.

**Required tests.**
- Layers `api_contract`; acceptance `AC1`; scenarios `API-COMMAND-SCHEMA-BOUNDARIES`. Schema and normalization matrix: Exercise reordered JSON keys and explicit typed defaults as equivalent; test malformed JSON, duplicate/unknown fields, missing/overlong IDs, unknown types, wrong numeric types, actor/game_id/totals/revision injection, and body limits.
- Layers `concurrency`, `api_contract`; acceptance `AC2`, `AC3`; scenarios `API-COMMAND-ID-INFLIGHT-SAME`, `API-COMMAND-ID-TERMINAL-SUCCESS`, `API-COMMAND-ID-TERMINAL-REJECTION`, `API-COMMAND-ID-CONFLICT`. Pending and terminal concurrency: Hold writer execution with a test gate while sending many identical and conflicting requests, then release it; repeat after success and after a rule rejection and include caller disconnect.
- Layers `concurrency`, `api_contract`, `property`; acceptance `AC4`, `AC5`; scenarios `CONC-COMMANDS-BOTH-LEGAL`, `CONC-COMMANDS-ONE-STOCK`, `ENG-TICK-COMMAND-SERIALIZATION`. Independent-client serial races: Run two legal Commands, one-resource contention, tick/Command races, retry-versus-other-legal-Command, and new IDs after prior success or rule rejection using separate HTTP clients. Do not create a project one-shot fixture before M2 owns official projects.
- Layers `api_contract`, `state_sequence`; acceptance `AC1`, `AC5`; scenarios `API-COMMAND-SCHEMA-BOUNDARIES`, `SSE-SAME-RUN-ORDERING`. View authority: Submit stale and forged client values and compare GET Views before/after applied, rejected, retry, and conflict requests.

**Evidence required by the future implementation PR.**
- Schema and normalization matrix: Only valid typed Commands reach the dispatcher, structural errors have the selected HTTP/code behavior and no binding/mutation, and normalization comparisons match the typed value.
- Pending and terminal concurrency: One state application, all identical waiters receive the first result, conflicts leave it unchanged, and accepted disconnect cannot cause reexecution.
- Independent-client serial races: Database-independent in-memory state matches a valid serial order, all affordable legal operations apply, and retries do not reserve or double-use resources.
- View authority: Only actual writer mutations alter View state/revision; no GET derives RNG or game progression and no response total can be used to write state.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`, `security_data_main`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/api/mod.rs`, `src/api/commands.rs`, `src/api/view.rs`, `src/retry.rs`, `src/run_metadata.rs`, `tests/api_commands.rs`

### M1-PERSISTENCE-RECOVERY — Transactional full snapshots, safe startup, and health

**Objective.** Implement approximately 30-second full default-game snapshots with asynchronous serialized SQLite writes, complete continuation state, last-good recovery without offline backfill, explicit corruption/error behavior, and no cross-run retry guarantee.

**Specification references (actual document and unique heading).**
- [requirements/runtime.md](./runtime.md) — `2. Real-Time Simulation — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `3. Concurrent Command Semantics — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `4. Current Instance Model — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `5. Technology Stack — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `6. Online Persistence — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `8. Subsequent Implementation Details — PROPOSED / OPEN`
- [requirements/clients.md](./clients.md) — `4. GameView — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED`

**Scope.**
- Define snapshot_version and serialize the complete currently implemented default state, revision, all M1 timers/accumulators/RNG/progression and persistent meta-state; exclude process retry records/subscriptions and generate a new run_id at each startup.
- Capture immutable envelopes in writer order and use one coalescing asynchronous SQLite worker outside the writer; implement the proposed metadata/default-row schema, checksum, WAL/synchronous settings, and atomic transaction replacement.
- Implement fresh-empty initialization, strict valid-row restore, explicit schema/version migrations for later changes, no offline backfill, and fail-closed behavior for corrupt/unsupported/unreadable existing state.
- Add sanitized live/ready health reporting and bounded retry/backoff for post-start save errors; mark degraded persistence without resetting live state or hiding an enlarged loss window.
- Update snapshot coverage in the same PR whenever another M1 feature adds continuation state before milestone assembly.

**Non-goals.**
- No zero-loss/exactly-once-across-crash claim, persistence of retry results, manual save-slot/debug API, per-client state, multi-instance registry, event sourcing, or wall-time production backfill.
- No long writer-held lock, synchronous rusqlite call in the game writer, unbounded stale-save queue, or snapshot/write side effect on game state or RNG.
- No silent fresh-game fallback, row deletion/quarantine/rename, partial_snapshot acceptance, or credentials/host paths in health/error/log output.
- No late-game fields invented merely to populate a schema; future playable tasks add and migrate their real state when implemented.

**Dependencies and reasons.**
- `M1-RUNTIME-CORE`: Authoritative state, single-writer execution, legal internal conversion, and continuous fake-testable time are shared prerequisites.

**Acceptance criteria and scenarios.**
- **AC1:** A valid snapshot restores every implemented M1 field needed for continuation and starts a new run_id with no offline resource, timer, sales, production, or RNG advancement. Scenarios: `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `PERSIST-CRASH-LOSS-NO-BACKFILL`.
- **AC2:** State after the saved point may roll back after a simulated crash; the old committed snapshot remains loadable after interrupted/failed replacement, and repeated startup is coherent. Scenarios: `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `PERSIST-CRASH-LOSS-NO-BACKFILL`.
- **AC3:** Ticks and Commands continue while an artificial SQLite write is blocked, pending saves coalesce, capture revisions are ordered, and no partial cross-resource state is serialized. Scenarios: `PERSIST-SNAPSHOT-30S-NONBLOCK`.
- **AC4:** Corrupt checksum, invalid state, unsupported version, and open/migration failure follow the explicit failure matrix; none silently creates or overwrites a new game. Scenarios: `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `PERSIST-CRASH-LOSS-NO-BACKFILL`.
- **AC5:** Readiness exposes post-start persistence degradation while the live authoritative world continues; normal-shutdown best effort is documented as outside crash zero-loss guarantees. Scenarios: `PERSIST-SNAPSHOT-30S-NONBLOCK`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`.

**Required tests.**
- Layers `persistence`, `state_sequence`; acceptance `AC1`; scenarios `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`. Snapshot completeness and round trip: Populate every currently implemented M1 state family including non-obvious fractional timers/RNG and persistent meta-state, capture, restore, and compare the complete continuation state rather than only visible numbers.
- Layers `persistence`, `state_sequence`; acceptance `AC2`, `AC4`; scenarios `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`. Atomic failure matrix: Use temporary fake databases to interrupt before/during/after transaction operations and inject malformed JSON, wrong checksum, missing fields, unsupported version, invalid numbers, and I/O errors.
- Layers `persistence`, `state_sequence`, `api_contract`; acceptance `AC1`, `AC2`; scenarios `PERSIST-CRASH-LOSS-NO-BACKFILL`, `PERSIST-REPEATED-STARTUP`. Crash and no-backfill scenarios: Save, execute controlled ticks/Commands, simulate process loss before the next save, advance wall time, and restart twice with injected run IDs/clocks.
- Layers `persistence`, `concurrency`, `state_sequence`; acceptance `AC3`; scenarios `PERSIST-SNAPSHOT-30S-NONBLOCK`. Async liveness and coherence: Block the SQLite worker while running fake-time ticks and concurrent Commands/save opportunities; complete writes later and verify capture/commit ordering and queue size.
- Layers `persistence`, `api_contract`; acceptance `AC4`, `AC5`; scenarios `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`. Health behavior: Exercise healthy initialization, corruption at startup, save failure/recovery after startup, and long snapshot lag with sanitized response/log capture.

**Evidence required by the future implementation PR.**
- Snapshot completeness and round trip: Restored pure-engine continuation from snapshot equals uninterrupted continuation for the same controlled Commands/ticks/RNG, excluding process identity and retry metadata.
- Atomic failure matrix: Only old or new fully committed rows load, never a partial row; existing invalid state fails safely without overwrite/delete.
- Crash and no-backfill scenarios: Only the last committed state returns, each process run_id differs, no downtime progress appears, and clients are required to resynchronize.
- Async liveness and coherence: Writer progress never awaits disk, at most one write plus one coalesced request exists, and committed snapshots are complete and ordered.
- Health behavior: Startup failures are explicit, post-start degraded readiness does not reset state, and diagnostics contain no private path or payload.

**Risk and review.** `concurrency_persistence_recovery`, `security_data_main`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/persistence.rs`, `src/snapshot.rs`, `src/health.rs`, `src/startup.rs`, `tests/persistence.rs`

### M1-SSE-VIEW-SYNC — Full-view SSE, reconnect, and recovered-run synchronization

**Objective.** Implement GET /api/game/stream with initial and subsequent full Views, bounded latest-value delivery, disconnect-independent simulation, and client-facing ordering rules proven across late HTTP/SSE races and process recovery.

**Specification references (actual document and unique heading).**
- [requirements/runtime.md](./runtime.md) — `2. Real-Time Simulation — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/clients.md](./clients.md) — `1. Default Game Is Transparent to Users — CONFIRMED`
- [requirements/clients.md](./clients.md) — `2. External Interface Shape — PROPOSED`
- [requirements/clients.md](./clients.md) — `4. GameView — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED`

**Scope.**
- Publish immutable full Views from writer changes with run_id/revision; emit the current full View immediately on every SSE connection and coalesce later notifications to the latest value.
- Bound per-connection delivery, use heartbeat comments if selected, and disconnect/reconnect lagging observers without backpressuring the writer or changing game time.
- Define and expose native-client/Agent synchronization rules for same-run revisions, new-run full baselines, active connection generations, and invalidation of older GETs/streams.
- Test restored snapshots with older revisions under a new run_id and document that Last-Event-ID is not a replay or exactly-once mechanism.

**Non-goals.**
- No WebSocket, JSON Patch, event sourcing, retained replay journal, per-actor stream, selected game ID, or server work triggered by an observer.
- No incremental view whose missing patch can corrupt client state; no assumption that network arrival order across independent connections is a global order.
- No public pause/step or simulation dependence on heartbeat, rendering cadence, Last-Event-ID, browser focus, or Agent response time.
- No native page styling in this PR beyond any minimal harness fixture required for stream-client tests.

**Dependencies and reasons.**
- `M1-API-COMMANDS-VIEW`: Public legal intents and full Views use the runtime writer and retry contract; no gameplay mutation is transported around it.
- `M1-PERSISTENCE-RECOVERY`: Complete snapshot and recovery behavior must include every continuation field already introduced by the runtime.

**Acceptance criteria and scenarios.**
- **AC1:** A new connection receives a full current View before any later update, and reconnect repeats that behavior without resetting or creating a world. Scenarios: `SSE-DISCONNECT-RECONNECT`.
- **AC2:** Same-run late/lower Views are ignored, higher Views apply, and new-run full Views establish a baseline even when their recovered revision is lower than an old run's cached revision. Scenarios: `SSE-SAME-RUN-ORDERING`, `SSE-RECOVERED-RUN-RESYNC`.
- **AC3:** A delayed old-run stream or GET cannot overwrite a recovered View already adopted through the active synchronization generation; equal revisions remain idempotent presentation only. Scenarios: `SSE-RECOVERED-RUN-RESYNC`.
- **AC4:** Dropping every SSE connection, blocking one observer, or reconnecting an Agent has no effect on pure-engine tick/resource progress or snapshot capture. Scenarios: `RT-NO-CLIENTS-CONTINUOUS`, `SSE-DISCONNECT-RECONNECT`.
- **AC5:** Many rapid writer changes yield either all intermediate full Views or a valid latest-coalesced sequence, never a partial View or unbounded connection queue. Scenarios: `SSE-DISCONNECT-RECONNECT`, `SSE-SAME-RUN-ORDERING`.

**Required tests.**
- Layers `sse`, `browser_e2e`; acceptance `AC1`, `AC5`; scenarios `SSE-DISCONNECT-RECONNECT`. SSE contract: Connect browser-like and structured-Agent clients, read initial/update frames, disconnect, reconnect with and without Last-Event-ID, and delay frame consumption.
- Layers `sse`, `browser_e2e`; acceptance `AC2`, `AC3`; scenarios `SSE-SAME-RUN-ORDERING`. Ordering model harness: Feed a reusable client synchronizer with lower/higher/equal revisions, run changes, GET responses, and old/new stream events in adversarial orders.
- Layers `sse`, `persistence`, `browser_e2e`; acceptance `AC3`; scenarios `SSE-RECOVERED-RUN-RESYNC`. Recovery integration: Take a snapshot, emit newer pre-crash Views, restore to the older snapshot under a new run_id, and race old GET/SSE responses against the new initial View.
- Layers `state_sequence`, `long_simulation`; acceptance `AC4`; scenarios `RT-NO-CLIENTS-CONTINUOUS`. Zero-client liveness: Use a bounded pure-engine fixture accumulator with legal inputs and no browser/SSE/Agent observers, then attach a stream and compare full state against the serial expectation. This proves disconnect-independent transport at the current stage; M1-G03 separately proves the real AutoClipper's no-client production without a production cheat endpoint.

**Evidence required by the future implementation PR.**
- SSE contract: Every resynchronization begins with a complete View, event JSON is valid, no replay gap creates an inconsistent state, and queues remain bounded.
- Ordering model harness: Only the active generation and ordered full View can change client state; recovered state cannot be replaced by old-run cache.
- Recovery integration: Clients accept the recovered authoritative full state and do not use pre-crash revision/result assumptions afterward.
- Zero-client liveness: The world advanced off-client and the stream displays current server state rather than catching the server up.

**Risk and review.** `concurrency_persistence_recovery`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/api/stream.rs`, `src/view_broadcast.rs`, `static/stream.js`, `tests/sse.rs`, `tests/view_ordering.rs`

### M1-NATIVE-TWO-PAGE-UI — Accessible native two-page client and real manual control

**Objective.** Deliver the no-build-chain classic-style browser architecture with semantic accessible controls, server-only Views, command pending/error feedback, robust SSE/GET ordering, and two independently usable pages sharing the default world.

**Specification references (actual document and unique heading).**
- [requirements/product.md](./product.md) — `5. Clients and Operators — CONFIRMED`
- [requirements/product.md](./product.md) — `6. First Web UI — CONFIRMED`
- [requirements/clients.md](./clients.md) — `1. Default Game Is Transparent to Users — CONFIRMED`
- [requirements/clients.md](./clients.md) — `4. GameView — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`
- [requirements/clients.md](./clients.md) — `6. Browser UI Behavior — CONFIRMED`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `5. UI Acceptance — CONFIRMED`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `4.2 Player-facing panels and information surfaces`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `8. Implementation boundaries and dependencies`

**Scope.**
- Implement semantic static HTML/CSS/native JS modules for the classic top-level presentation and currently implemented M1 controls, including a genuine Make Paperclip path and shared View/command/stream code.
- Render only server-derived values and domain feedback; show pending and actual applied/rule_rejected/conflict errors without locally adding resources or claiming success.
- Apply full Views with the run/revision/connection-generation algorithm, reconnect on refresh, and support two independent pages plus non-browser Agent traffic.
- Provide keyboard/focus/label/live-region behavior and best-effort minimalist classic hierarchy; coordinate additional M1 panels with their feature owners before final assembly.
- Use a real-browser harness for semantic, networking, refresh, and two-page checks without introducing a frontend build tool.

**Non-goals.**
- No client economic engine, local timer production, optimistic resource addition, authoritative disabled state, DOM/pixel/source-tool bug replica, or exact original RNG/timing requirement.
- No login, actor/role selector, world selector, new-world-on-open, developer console/cheat, public debug reset, or automatic Command retry with a new ID for the same intent.
- No invented late-game panels or clickable placeholders; excluded Feed/Teach/Clad and debug controls remain absent.
- No new UI framework, bundler, package-manager chain, server-side Python renderer, or pixel-perfect screenshot gate.

**Dependencies and reasons.**
- `M1-SSE-VIEW-SYNC`: Full-view streaming and recovered-run ordering require both API View/run metadata and snapshot recovery semantics.

**Acceptance criteria and scenarios.**
- **AC1:** A keyboard-operable Make Paperclip button sends only the typed Command and pending feedback; resources change only when a full server View shows the applied mutation, and rejection/conflict feedback is understandable. Scenarios: `UI-EARLY-SERVER-AUTHORITY`.
- **AC2:** Two pages opened on / show the same default world and see each other's legal actions through the server; simultaneous actions follow execution results rather than local page ownership. Scenarios: `UI-TWO-ANONYMOUS-PAGES`.
- **AC3:** Refresh/reconnect does not reset or roll back the world, and adversarially delayed old HTTP/SSE payloads cannot overwrite a newer or recovered View. Scenarios: `SSE-SAME-RUN-ORDERING`, `SSE-RECOVERED-RUN-RESYNC`, `SSE-DISCONNECT-RECONNECT`.
- **AC4:** Semantic landmarks, headings, labels, focus order, contrast, polite console/status announcements, and usable error feedback pass the chosen accessibility checks without high-frequency live-region flooding. Scenarios: `UI-EARLY-SERVER-AUTHORITY`.
- **AC5:** Feature-owned M1 controls/panels are integrated before M1 assembly or remain absent rather than showing fake local functionality; the manual anchor alone is not advertised as the full selected M1. Scenarios: `UI-TWO-ANONYMOUS-PAGES`.

**Required tests.**
- Layers `browser_e2e`, `api_contract`; acceptance `AC1`, `AC2`; scenarios `UI-EARLY-SERVER-AUTHORITY`, `UI-TWO-ANONYMOUS-PAGES`. Real-browser network proof: Intercept browser requests in two independent pages while clicking legal controls and injecting server rejection; inspect resource readouts after applied Responses and Views.
- Layers `browser_e2e`, `sse`; acceptance `AC3`; scenarios `SSE-SAME-RUN-ORDERING`, `SSE-RECOVERED-RUN-RESYNC`. Refresh and stale-response E2E: Race delayed GETs and old streams with newer SSE events and a recovered run while refreshing/reconnecting the pages.
- Layers `browser_e2e`; acceptance `AC4`; scenarios `UI-EARLY-SERVER-AUTHORITY`. Semantic/accessibility review: Run the selected automated semantic checks plus keyboard-only operation and inspect headings, button names, focus, contrast, error announcement, and live-region frequency.
- Layers `browser_e2e`, `concurrency`, `api_contract`; acceptance `AC2`, `AC5`; scenarios `UI-TWO-ANONYMOUS-PAGES`, `API-COMMAND-ID-CONFLICT`. Agent/browser coexistence: Send legal and conflicting Commands from a structured Agent while two pages issue retries/new intents and observe SSE.

**Evidence required by the future implementation PR.**
- Real-browser network proof: Clicks produce only allowed envelopes, no pre-response resource addition occurs, disabled/enabled races remain server-decided, and both pages converge to the same View.
- Refresh and stale-response E2E: The DOM contains only the active generation's latest full state and the old run cannot reappear.
- Semantic/accessibility review: Recorded results satisfy the M1 accessible interaction path; screenshots support best-effort style only and are not pixel gates.
- Agent/browser coexistence: No actor distinction or UI lock exists; all views converge and every state outcome follows the shared writer/retry rules.

**Risk and review.** `core_simulation`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `static/index.html`, `static/styles.css`, `static/app.js`, `static/view-model.js`, `static/commands.js`, `static/stream.js`, `tests/browser_m1.py`, `scripts/run_browser_tests.py`

### M1-G01 — Initial state, legal manual conversion, and three ledgers

**Objective.** Start the one authoritative game at the documented initial state and make legal manual Paperclip production observable through matching lifetime, Unsold, and Unused ledger updates.

**Specification references (actual document and unique heading).**
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-CLIP-PRODUCTION` - shared conversion and matter chain`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `4.2 Player-facing panels and information surfaces`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`
- [requirements/product.md](./product.md) — `4. Gameplay Fidelity Boundaries — CONFIRMED`

**Scope.**
- All documented M1 initial values and future-state fields required by the full technical schema
- Ordinary one-clip manual intent; Wire >=1 outer gate and min(requested,available) internal cap
- Equal actual production increments to lifetime/Unsold/Unused and lifetime headline

**Non-goals.**
- No arbitrary-amount public clip command or client-computed resource totals
- No positive sub-one ordinary manual conversion
- No AutoClipper/factory production yet beyond the internal conversion primitive
- No Reject final-stage exception in ordinary play

**Dependencies and reasons.**
- `M1-NATIVE-TWO-PAGE-UI`: The native two-page client consumes the established full View, command, stream, and stale-response contracts.

**Acceptance criteria and scenarios.**
- **AC1:** Fresh state matches all documented M1 values and hides future panels Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`, `UI-EARLY-SERVER-AUTHORITY`.
- **AC2:** Manual click at Wire >=1 produces exactly one and updates all three ledgers; below-one or invalid input changes none Scenarios: `ENG-WIRE-MANUAL-FLOOR`.
- **AC3:** Internal conversion vectors 5/10=>5, 0.5/0.2=>0 and 1/0.2=>0.2 conserve Wire and equal ledger deltas Scenarios: `ENG-WIRE-AUTOMATIC-FLOOR-CAP`.
- **AC4:** UI displays only server-derived results and remains connected to the one default game Scenarios: `UI-EARLY-SERVER-AUTHORITY`, `UI-TWO-ANONYMOUS-PAGES`.

**Required tests.**
- Layers `rule_unit`, `property`; acceptance `AC1`, `AC2`, `AC3`; scenarios `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`. Rule table for initial state, zero/fractional/full Wire, cap and ledger identity
- Layers `state_sequence`, `concurrency`, `api_contract`; acceptance `AC2`, `AC3`; scenarios `CONC-COMMANDS-ONE-STOCK`, `ENG-TICK-COMMAND-SERIALIZATION`, `API-COMMAND-ID-TERMINAL-SUCCESS`. Same-resource contention, tick-versus-command ordering and legal retry tests
- Layers `browser_e2e`, `api_contract`; acceptance `AC4`; scenarios `UI-EARLY-SERVER-AUTHORITY`, `UI-TWO-ANONYMOUS-PAGES`. Browser click test proving no local resource award or independent world

**Evidence required by the future implementation PR.**
- Current-HEAD results for: Rule table for initial state, zero/fractional/full Wire, cap and ledger identity
- Current-HEAD results for: Same-resource contention, tick-versus-command ordering and legal retry tests
- Current-HEAD results for: Browser click test proving no local resource award or independent world
- A criteria-to-feature evidence ledger showing each task-owned M1 feature without claiming ownership of shared technical primitives.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/game/`, `src/api/`, `static/`, `tests/`

### M1-G02 — Human Business market, Wire supply, and stochastic sales

**Objective.** Add the genuine Funds/Wire/Price/Marketing economy so manual production can become sales revenue and revenue can replenish production input.

**Specification references (actual document and unique heading).**
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-DEMAND-SALES` - pricing, demand, sales, and revenue`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-WIRE-MARKET` - repricing and automatic purchase`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `4.2 Player-facing panels and information surfaces`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-DEMAND-SALES — Public Demand, Marketing, price, and stochastic sales`
- [requirements/testing.md](./testing.md) — `3. Rule and Numeric Verification — CONFIRMED`

**Scope.**
- $0.01 price controls and $0.01 lower bound
- Marketing level/cost/demand multiplier
- Wire spool purchase/base price/purchase decay/stochastic repricing
- Ten normalized sales opportunities per second with stock-capped stochastic transactions and revenue accounting
- Add only legal Wire/Price/Marketing typed command variants and the complete Business/Wire public View/native panel through the existing API and SSE contracts
- Extend snapshot_version and all sales, revenue, Wire quote/purchase, inactivity, demand, and RNG/accumulator continuation state in this same PR

**Non-goals.**
- No RevTracker analytic/readout until M2
- No WireBuyer until M3
- No Investment portfolio or prestige modifiers beyond retaining their initial state for schema

**Dependencies and reasons.**
- `M1-G01`: The four initial/manual feature owners receive final integrated acceptance only after the real manual engine/API/UI anchors exist.

**Acceptance criteria and scenarios.**
- **AC1:** Sales reduce Unsold only and add correct Funds; stockouts create no revenue Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`, `CONC-COMMANDS-ONE-STOCK`.
- **AC2:** Price/Marketing change derived demand immediately while purchase costs remain authoritative at execution; every Business control and feedback field uses the real typed API, server-derived View, and native panel Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`.
- **AC3:** Wire purchase charges current quote, adds current supply, raises base by $0.05 and resets inactivity Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`.
- **AC4:** Controlled RNG preserves the specified sale/reprice probabilities and opportunities without browser-sequence parity, and snapshots restore every sales, revenue, quote, inactivity, and RNG/accumulator continuation field without offline gains Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`.

**Required tests.**
- Layers `rule_unit`, `api_contract`; acceptance `AC2`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`. Demand formula and price-bound unit tests
- Layers `rule_unit`, `property`, `state_sequence`; acceptance `AC1`, `AC3`, `AC4`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`. Stock-limited controlled-RNG sales and repricing/inactivity tests
- Layers `concurrency`, `persistence`, `state_sequence`; acceptance `AC1`, `AC2`, `AC3`, `AC4`; scenarios `CONC-COMMANDS-ONE-STOCK`, `CONC-COMMANDS-BOTH-LEGAL`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`. Two simultaneous purchases against one Funds balance, legal concurrent commands, retries, and snapshot/recovery around stochastic counters

- Layers `api_contract`, `browser_e2e`, `sse`, `persistence`; acceptance `AC1`, `AC2`, `AC3`, `AC4`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`, `UI-TWO-ANONYMOUS-PAGES`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`. Public Business contract closure: issue only legal Wire/Price/Marketing commands through the API and two native pages, then round-trip every added sales, revenue, Wire quote/purchase, inactivity, demand, and RNG/accumulator field through snapshot recovery without offline gains

**Evidence required by the future implementation PR.**
- Current-HEAD results for: Demand formula and price-bound unit tests
- Current-HEAD results for: Stock-limited controlled-RNG sales and repricing/inactivity tests
- Current-HEAD results for: Two simultaneous purchases against one Funds balance, legal concurrent commands, retries, and snapshot/recovery around stochastic counters
- Current-HEAD public-contract evidence for every G02 typed command, View/native panel, and snapshot continuation field added in the same PR
- A criteria-to-feature evidence ledger showing each task-owned M1 feature without claiming ownership of shared technical primitives.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/game/`, `src/api/`, `static/`, `tests/`

### M1-G03 — First real AutoClipper automation and feedback

**Objective.** Complete M1 as a playable vertical increment: Funds reaching $5 permanently reveals AutoClippers, purchases add real producers, and production continues independently of clients.

**Specification references (actual document and unique heading).**
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `4.2 Player-facing panels and information surfaces`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-CLIP-AUTOMATION — AutoClippers, MegaClippers, and clips per second`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`
- [requirements/runtime.md](./runtime.md) — `2. Real-Time Simulation — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `6. Online Persistence — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`
- [requirements/clients.md](./clients.md) — `6. Browser UI Behavior — CONFIRMED`

**Scope.**
- Observe the actual first Funds>=5 reveal before any successful Wire or initial Marketing purchase, retaining the permanent latch and initial stored current cost $5 rather than a level-zero successor formula
- At execution, charge the existing current cost only on success: threshold $5 -> Funds $0/count 1/next $6.10, then a distinct successor purchase at $6.10 -> count 2/next $6.21; below-current-price intent has no Funds/count/cost/ledger mutation
- Nominal one clip/s per AutoClipper through M1-G01 internal conversion; add the legal buy_auto_clipper typed intent, public count/cost/reveal/rate feedback, and all new producer/reveal/current-cost continuation fields to the same-PR snapshot migration
- Manufacturing levels/current cost/Wire/production feedback and the general five-line console message history

**Non-goals.**
- No additive boost projects or MegaClippers until later milestones
- No human turn, Agent pause, public simulation-step or clock endpoint
- No frontend timer as authoritative producer

**Dependencies and reasons.**
- `M1-G01`: The four initial/manual feature owners receive final integrated acceptance only after the real manual engine/API/UI anchors exist.
- `M1-G02`: The Business market extends the verified initial three-ledger/manual state and its legal public controls.
- `M1-PERSISTENCE-RECOVERY`: Complete snapshot and recovery behavior must include every continuation field already introduced by the runtime.

**Acceptance criteria and scenarios.**
- **AC1:** The actual first Funds>=5 reveal occurs before any successful Wire/Marketing purchase and is permanent after Funds later falls below $5. Threshold $5 charges exactly $5, producing count 1/next $6.10; a distinct later purchase charges $6.10, producing count 2/next $6.21. Below-current-price and stale-view-forgery attempts mutate no Funds/count/current cost/ledgers and never silently reprice. Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`.
- **AC2:** The first and second purchased AutoClippers each generate capped baseline one-clip/s production during no-browser, no-SSE and Agent-inactive periods, without free production or caller-selected cost. Scenarios: `RT-NO-CLIENTS-CONTINUOUS`, `E2E-M1-DECLARED-PLAYABLE-EXIT`.
- **AC3:** Refresh/two pages observe identical producers/count/current cost/reveal. Snapshots restore stored $5/$6.10/$6.21 states without level-zero recomputation or offline gain. Same-ID retry replays the first stored receipt with no second mutation; a distinct legal intent after replenishment can buy at the successor $6.10. Scenarios: `UI-TWO-ANONYMOUS-PAGES`, `PERSIST-CRASH-LOSS-NO-BACKFILL`, `SSE-RECOVERED-RUN-RESYNC`.

**Required tests.**
- Layers `rule_unit`, `api_contract`, `browser_e2e`, `state_sequence`; acceptance `AC1`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`. First-crossing and current-cost lifecycle: observe actual first $5 reveal before any Wire/Marketing buy; assert $5 -> 0/count 1/next $6.10, successor $6.10 -> count 2/next $6.21, below-price no-op, permanent latch and execute-time atomicity through rule/API/native-browser tests
- Layers `state_sequence`, `long_simulation`, `persistence`; acceptance `AC2`; scenarios `RT-NO-CLIENTS-CONTINUOUS`, `PERSIST-SNAPSHOT-30S-NONBLOCK`. Continuous first/second producer output with zero clients and during atomic save; verify ordinary Wire-limited conversion and bounded fake-time behavior rather than long sleeps or free production
- Layers `browser_e2e`, `sse`, `persistence`; acceptance `AC3`; scenarios `UI-TWO-ANONYMOUS-PAGES`, `SSE-RECOVERED-RUN-RESYNC`, `PERSIST-CRASH-LOSS-NO-BACKFILL`. Refresh/reconnect/two-page E2E plus exact stored producer-count/current-cost/reveal recovery, first-terminal same-ID receipt replay without mutation, distinct successor purchase, and no offline backfill or level-zero cost reconstruction

**Evidence required by the future implementation PR.**
- Current-HEAD first-crossing and exact receipt evidence for $5 -> $6.10 -> $6.21, below-cost rejection, permanent latch, and zero Wire/Marketing purchases before first reveal
- Current-HEAD results for: Continuous production with zero clients and during atomic save; bounded integration timing rather than long sleep-based full simulation
- Current-HEAD snapshot/retry evidence preserving exact stored producer count/current cost/reveal, duplicate terminal result and successor state, with no offline catch-up or level-zero recomputation
- A criteria-to-feature evidence ledger showing each task-owned M1 feature without claiming ownership of shared technical primitives.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/game/`, `src/api/`, `static/`, `tests/`
### M1-PLAYABLE-INTEGRATION — Assemble and prove the selected first playable vertical milestone

**Objective.** Integrate every integrated M1 feature with the completed runtime/API/snapshot/SSE/native-client contracts and demonstrate the exact selected M1 entry-to-exit scenario as a genuine playable increment, with no server-shell or frontend-demo completion claim.

**Specification references (actual document and unique heading).**
- [requirements/milestones.md](./milestones.md) — `1. Complete Map Before Feature Implementation — CONFIRMED`
- [requirements/milestones.md](./milestones.md) — `2. How to Divide Milestones — CONFIRMED`
- [requirements/milestones.md](./milestones.md) — `3. Issue Planning Granularity — CONFIRMED`
- [requirements/milestones.md](./milestones.md) — `4. Common Acceptance for Each Stage`
- [requirements/product.md](./product.md) — `2. Full Scope and Incremental Delivery — CONFIRMED`
- [requirements/product.md](./product.md) — `6. First Web UI — CONFIRMED`
- [requirements/product.md](./product.md) — `7. Final Acceptance Principles — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `1. Authoritative State — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `2. Real-Time Simulation — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `3. Concurrent Command Semantics — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `6. Online Persistence — CONFIRMED`
- [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
- [requirements/clients.md](./clients.md) — `3. Commands — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `4. GameView — CONFIRMED / PROPOSED`
- [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`
- [requirements/clients.md](./clients.md) — `6. Browser UI Behavior — CONFIRMED`
- [requirements/testing.md](./testing.md) — `1. Principles — CONFIRMED`
- [requirements/testing.md](./testing.md) — `2. Layered Matrix`
- [requirements/testing.md](./testing.md) — `4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED`
- [requirements/testing.md](./testing.md) — `5. UI Acceptance — CONFIRMED`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-MILESTONES — Ordered production messages and elapsed-time feedback`

**Scope.**
- Consume the integrated gameplay map's exact M1 feature tasks, entry state, exit criteria, and source-grounded automatic/manual behaviors; resolve only integration wiring and demonstrated cross-interface gaps.
- Wire every M1 command, public resource/control, timer/RNG/accumulator, snapshot field, SSE update, and native panel through the same default runtime without second client-side rules.
- Add the real M1 end-to-end entry-to-exit browser/Agent/server scenario, zero-client automatic progression, two-page concurrency, refresh/reconnect, snapshot loss/recovery, and required negative controls.
- Record M1 feature coverage and explicit interim-version status after all feature-owned tasks and this assembly pass latest-main merge verification.

**Non-goals.**
- No change to M1 feature ownership, simplified substitute economy, new gameplay rule, implementation before the approved plan, or declaration of full-clone completion.
- No debug setup during the playable acceptance path, hidden operator time/resource writes, local fake counters, generated static success log, or screenshot-only playability evidence.
- No late-game features brought forward merely to make the demo look broad; no stubs for them presented as implemented.
- No weakening of prior tests/CI, skipping final recovery/concurrency checks, or milestone acceptance based only on a compilable server shell.

**Dependencies and reasons.**
- `M1-BOOTSTRAP-CI`: The stable Rust workspace, dependency lock, configuration, and real CI host are required before runtime code can be integrated and tested.
- `M1-RUNTIME-CORE`: Authoritative state, single-writer execution, legal internal conversion, and continuous fake-testable time are shared prerequisites.
- `M1-API-COMMANDS-VIEW`: Public legal intents and full Views use the runtime writer and retry contract; no gameplay mutation is transported around it.
- `M1-PERSISTENCE-RECOVERY`: Complete snapshot and recovery behavior must include every continuation field already introduced by the runtime.
- `M1-SSE-VIEW-SYNC`: Full-view streaming and recovered-run ordering require both API View/run metadata and snapshot recovery semantics.
- `M1-NATIVE-TWO-PAGE-UI`: The native two-page client consumes the established full View, command, stream, and stale-response contracts.
- `M1-G01`: Final assembly requires the complete initial/manual feature acceptance, not only the technical manual anchor.
- `M1-G02`: Final assembly requires the genuine manual-to-sales/Wire/Price/Marketing economy.
- `M1-G03`: Final assembly requires permanent reveal, purchase, and continuous real AutoClipper production; this is the playable exit.

**Acceptance criteria and scenarios.**
- **AC1:** From the exact M1 entry state, a real browser user using only legal public controls and real online ticks can reach every gameplay-map-defined M1 exit condition; the evidence names the concrete final state rather than a smoke startup. Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`.
- **AC2:** All M1 features owned by the integrated coverage map have their actual engine behavior, typed command/config path, public feedback, UI surface where required, snapshot state, test evidence, and exactly one milestone owner. Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`, `E2E-FULL-PHASE-ENGINE-TRACE`.
- **AC3:** Automatic M1 behavior advances with zero browsers/SSE/Agents; two pages plus an Agent can concurrently act and observe; resource contention, retry, rejection, and stale-view behavior remain correct end to end. Scenarios: `RT-NO-CLIENTS-CONTINUOUS`, `UI-TWO-ANONYMOUS-PAGES`.
- **AC4:** Snapshot/recovery restores every M1 continuation field without offline backfill, and old clients resynchronize without pre-crash state overwriting the recovered run. Scenarios: `PERSIST-CRASH-LOSS-NO-BACKFILL`, `SSE-RECOVERED-RUN-RESYNC`.
- **AC5:** The final M1 CI/main evidence contains actual rule, sequence, concurrency, API, SSE, persistence, real-browser, and scenario commands/results appropriate to each risk; no selected M1 control remains a placeholder. Scenarios: `E2E-M1-DECLARED-PLAYABLE-EXIT`, `CI-BOOTSTRAP-REAL-MANIFEST`.

**Required tests.**
- Layers `gameplay_scenario`, `browser_e2e`, `api_contract`, `sse`, `state_sequence`; acceptance `AC1`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`. M1 playable acceptance scenario: Execute the precise integrated scenario from a fresh legitimate server through the real browser while recording Commands, Views, ticks, and final authoritative state; include a separate structured Agent observer/controller.
- Layers `concurrency`, `state_sequence`, `long_simulation`, `browser_e2e`; acceptance `AC2`, `AC3`; scenarios `RT-NO-CLIENTS-CONTINUOUS`, `UI-TWO-ANONYMOUS-PAGES`. Zero-client and shared-world integration: Let automatic M1 systems run with no clients, then attach two pages and an Agent to issue legal, retry, conflicting, and contested Commands under online ticks.
- Layers `persistence`, `sse`, `browser_e2e`, `state_sequence`; acceptance `AC4`; scenarios `PERSIST-CRASH-LOSS-NO-BACKFILL`, `SSE-RECOVERED-RUN-RESYNC`. M1 recovery/reconnect scenario: Create a normal snapshot during the playable state, make further progress, simulate crash/restart/reconnect, and advance wall time before resuming.
- Layers `rule_unit`, `gameplay_scenario`; acceptance `AC2`; scenarios `E2E-M1-DECLARED-PLAYABLE-EXIT`, `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`. Feature/coverage closure: Run the integrated execution-plan validator plus feature-specific tests and sample every M1 canonical ID to its implemented engine/API/UI/snapshot/test evidence as applicable.
- Layers `api_contract`, `browser_e2e`; acceptance `AC5`; scenarios `API-COMMAND-SCHEMA-BOUNDARIES`, `UI-EARLY-SERVER-AUTHORITY`. Negative anti-demo controls: Attempt forged resource totals, arbitrary conversion amounts, unknown controls, public pause/step, and an unimplemented future command; inspect browser networking and CI artifacts.

**Evidence required by the future implementation PR.**
- M1 playable acceptance scenario: Every specified exit condition is reached through legal public operations with no debug intervention, and the log proves both manual and automatic behavior required by M1.
- Zero-client and shared-world integration: Off-client progress occurs and all clients converge to the same serial authoritative state with no lost update or double execution.
- M1 recovery/reconnect scenario: The restored state contains all M1 progress through the last commit only, has no offline gains, and is accepted over stale pre-crash Views.
- Feature/coverage closure: No M1 feature lacks an implementation and acceptance path, no alias/exclusion becomes an extra feature, and all dependency Issues are closed only after main verification.
- Negative anti-demo controls: Nothing unauthorized mutates state, no future stub reports success, and the evidence demonstrates gameplay rather than only server/page startup.

**Risk and review.** `core_simulation`, `concurrency_persistence_recovery`, `test_ci_merge_infrastructure`, `security_data_main`; `two_independent_reviewers_including_one_adversarial`. These are planned gates, not approvals recorded here.

**Possible future implementation paths (not files in this planning PR).** `src/game/mod.rs`, `src/api/mod.rs`, `src/snapshot.rs`, `static/index.html`, `static/app.js`, `tests/milestone_m1.rs`, `tests/browser_m1.py`, `tests/m1_recovery.rs`

## 3. M2 coarse packages and M3-M15 supporting outlines

No future GitHub Issue number is assigned. Only M2 may remain coarse as the next milestone. M3-M15 outlines are stable planning identities to refine only when their stage becomes current. M2-C01/C03 independently validate lawful allocation, Ops and the exact nonlinear Creativity curve through `ENG-TRUST-OPS-CREATIVITY`, without requiring an offered or purchased Xavier. M3-C01 alone owns the actual `E2E-XAVIER-ALLOCATION-RESET` Human purchase at 100000 Creativity, its allocation-only reset and valid repetition; `PRJ-096` ownership and all DAG edges are unchanged.

| Task | Milestone | Objective | Direct predecessors | Scenario links |
|---|---|---|---|---|
| `M2-C01` | M2 | Next-milestone coarse package: Computing unlock and Trust/Processor/Memory/Ops. Refine into detailed one-PR Issues only after M1 is complete and this package becomes current. | `M1-PLAYABLE-INTEGRATION` | `ENG-PROJECT-OFFER-LATCH`, `ENG-TRUST-OPS-CREATIVITY`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M2-C02` | M2 | Next-milestone coarse package: Project offers and foundational PRJ-001..018. Refine into detailed one-PR Issues only after M1 is complete and this package becomes current. | `M2-C01` | `ENG-PROJECT-OFFER-LATCH`, `ENG-TRUST-OPS-CREATIVITY`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M2-C03` | M2 | Next-milestone coarse package: Creativity, RevTracker, and playable project UI acceptance. Refine into detailed one-PR Issues only after M1 is complete and this package becomes current. | `M2-C01`, `M2-C02` | `ENG-PROJECT-OFFER-LATCH`, `ENG-TRUST-OPS-CREATIVITY`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M3-C01` | M3 | Mapped future outline for Scaled Human automation, Quantum Computing, and alternate reset: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M2-C03` | `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `E2E-XAVIER-ALLOCATION-RESET`, `E2E-FULL-PHASE-ENGINE-TRACE`, `RESET-INPROCESS-RETRY-RETENTION` |
| `M4-C01` | M4 | Mapped future outline for Investments, Yomi, and the complete strategy pool: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M2-C03`, `M3-C01` | `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M5-C01` | M5 | Mapped future outline for Late-Human Trust routes, AutoTourney, and HypnoDrone release: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M2-C03`, `M3-C01`, `M4-C01` | `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M6-C01` | M6 | Mapped future outline for Autonomous matter, Wire, factories, and continuous Power: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M5-C01` | `ENG-POWER-FULL-COVER`, `ENG-POWER-LAST-PARTIAL`, `ENG-POWER-SURPLUS-CAP-SPACE`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M7-C01` | M7 | Mapped future outline for Capital recovery, Momentum, and quadratic industrial upgrades: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M6-C01` | `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M8-C01` | M8 | Mapped future outline for Swarm Work/Think, Gifts, Boredom, and Disorganization: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M7-C01`, `M2-C01` | `ENG-GIFT-ACTIVE-RESET`, `ENG-GIFT-INACTIVE-HEALTH-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M9-C01` | M9 | Mapped future outline for Earth exhaustion and the Space Exploration handoff: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M8-C01` | `ENG-POWER-SURPLUS-CAP-SPACE`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M10-C01` | M10 | Mapped future outline for Probe design, growth, recovery, and live direct Combat: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M9-C01`, `M4-C01`, `M8-C01` | `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `ENG-POWER-SURPLUS-CAP-SPACE`, `ENG-COMBAT-NAMING-HONOR-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M11-C01` | M11 | Mapped future outline for OODA, named battles, signed Honor, and Max Trust: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M10-C01` | `ENG-COMBAT-NAMING-HONOR-GATES`, `ENG-COMBAT-TIMEOUT-HONOR`, `ENG-HONOR-NEGATIVE-AND-GLORY`, `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M12-C01` | M12 | Mapped future outline for Universal achievement, Emperor dialogue, and mutually exclusive choice: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M10-C01` | `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M13-C01` | M13 | Mapped future outline for Accept destinations, persistent prestige, and clean restart: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M12-C01` | `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `E2E-FULL-PHASE-ENGINE-TRACE`, `RESET-INPROCESS-RETRY-RETENTION` |
| `M14-C01` | M14 | Mapped future outline for Reject teardown: Probes through Memory: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M12-C01`, `M3-C01`, `M4-C01`, `M6-C01`, `M7-C01`, `M10-C01` | `E2E-REJECT-CREDITS`, `E2E-FULL-PHASE-ENGINE-TRACE` |
| `M15-C01` | M15 | Mapped future outline for Final positive Wire conversion, exact-zero credits, and full-game closure: preserve its complete source-owned playable increment and only later refine it into independent detailed Issues. | `M11-C01`, `M12-C01`, `M13-C01`, `M14-C01` | `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `E2E-REJECT-FINAL-WIRE`, `CONC-REJECT-FINAL-WIRE`, `E2E-REJECT-CREDITS`, `E2E-FULL-PHASE-ENGINE-TRACE` |

## 4. Complete playable milestone map

Every milestone is a vertical increment of the same default game. Earlier legal behavior is preserved, while each canonical feature has only the primary owner shown here. Source-order project position never implies a false numeric or delivery dependency.

### M1 — Human clips, Wire, sales, and first automation

**Granularity and ownership.** current_detailed; 19 features; families {"ACT": 6, "PROG": 2, "RES": 5, "SYS": 2, "UI": 4}. Task IDs: `M1-BOOTSTRAP-CI`, `M1-RUNTIME-CORE`, `M1-API-COMMANDS-VIEW`, `M1-PERSISTENCE-RECOVERY`, `M1-SSE-VIEW-SYNC`, `M1-NATIVE-TWO-PAGE-UI`, `M1-G01`, `M1-G02`, `M1-G03`, `M1-PLAYABLE-INTEGRATION`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.1 Manual production and Human Business`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`

**Source rationale.** Primary sources: PROG-START, PROG-DEMAND-SALES, SYS-DEMAND-SALES, SYS-WIRE-MARKET, the initial RES/UI rows, and the direct Human Business controls in gameplay-actions.md and gameplay-progression.md. These systems give a real economic loop before any project exists.

**Entry state.** Fresh authoritative run: clips/lifetime, Unsold Inventory, and Unused Clips all 0; Funds 0; Wire 1000 with 1000-inch spools at $20; Price $0.25; Marketing level 1; Trust 2, one Processor, one Memory, and computing/projects hidden. Matter and all future-phase state use the documented initial values even before becoming visible. AutoClippers begin at count zero with reveal false and stored current cost $5, independent of the successor formula.

**Playable behavior.** The player first makes individual clips and sells Unsold Inventory. Before any successful Wire or initial Marketing purchase, the player observes the actual first Funds>=5 reveal and stored cost $5. The first AutoClipper costs $5, gives count 1 and next cost $6.10; a later distinct purchase at $6.10 gives count 2 and next cost $6.21. Required current-quote Wire and Price/Marketing actions follow the first reveal, which remains latched after Funds falls below $5. Production is server-generated with no clients connected. Sales reduce only Unsold Inventory; every conversion increases all three clip ledgers equally.

**Exit state.** From fresh state through the real UI, the player observes first $5 before any successful Wire/Marketing buy, purchases the first AutoClipper at exact stored cost 5/next 6.10 and a later one at 6.10/next 6.21, also sells clips, buys replacement Wire and adjusts Price/Marketing after reveal. At least one real producer continues legal Wire-limited production through refresh/reconnect and with no observer. Stored cost/count/reveal survive snapshot without backfill. Computing, Projects, and MegaClippers are not required for exit.

**Milestone dependencies.** None

**Technical dependencies.** The M1 platform tasks supply Rust/Axum/Tokio/Serde/SQLite runtime, one ordered writer, legal Command/View/SSE contracts, native UI, continuous independent ticks, full initial/future state schema, retry handling, and atomic 30-second-default snapshots. No public arbitrary resource write, pause, turn, or debug step API.

**Accepted scenarios (source behavior).**
- Manual Make Paperclip with Wire 2 produces exactly 1 in lifetime/Unsold/Unused and leaves Wire 1; with Wire below 1 the ordinary manual command changes nothing.
- The shared internal conversion passes Wire 5/request 10 => produced 5 and Wire 0; Wire 0.5/request 0.2 => produced 0 and Wire 0.5; Wire 1/request 0.2 => produced 0.2 and Wire 0.8, adding the actual amount equally to all three ledgers.
- A controlled sale consumes Unsold Inventory only and credits Funds at current Price; an empty-stock opportunity adds no Funds; simultaneous purchases cannot overspend one Funds balance.
- Price bottoms at $0.01 through the legal control, Marketing doubles/floors its next dollar cost, and a purchased spool yields 1000 Wire while raising base quote $0.05 and resetting inactivity.
- The actual first Funds>=5 reveal and stored cost $5 are observed before every successful Wire or initial Marketing purchase, whose prices require later earnings. Replacement-Wire and Marketing purchases then occur legally and the latch survives subsequent Funds drops below $5.
- Threshold purchase at Funds 5/current cost 5/count 0 charges exactly 5, leaves Funds 0/count 1/next cost 6.10; the next distinct legal purchase at current cost 6.10 charges 6.10, gives count 2/next cost 6.21. Below-price intent has no Funds/count/cost/ledger effect; duplicate ID replays the first receipt only and snapshots recover stored count/cost/reveal without offline gains or level-zero recomputation.

**Catalog scenario links.** `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`, `CONC-COMMANDS-BOTH-LEGAL`, `CONC-COMMANDS-ONE-STOCK`, `ENG-TICK-COMMAND-SERIALIZATION`, `API-COMMAND-ID-INFLIGHT-SAME`, `API-COMMAND-ID-TERMINAL-SUCCESS`, `API-COMMAND-ID-TERMINAL-REJECTION`, `API-COMMAND-ID-CONFLICT`, `API-COMMAND-SCHEMA-BOUNDARIES`, `RT-NO-CLIENTS-CONTINUOUS`, `PERSIST-SNAPSHOT-30S-NONBLOCK`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `PERSIST-CRASH-LOSS-NO-BACKFILL`, `PERSIST-REPEATED-STARTUP`, `SSE-SAME-RUN-ORDERING`, `SSE-RECOVERED-RUN-RESYNC`, `SSE-DISCONNECT-RECONNECT`, `UI-EARLY-SERVER-AUTHORITY`, `UI-TWO-ANONYMOUS-PAGES`, `API-DEFAULT-NAMESPACE-BOUNDARY`, `E2E-M1-DECLARED-PLAYABLE-EXIT`, `E2E-REJECT-FINAL-WIRE`, `E2E-FULL-PHASE-ENGINE-TRACE`, `CI-BOOTSTRAP-REAL-MANIFEST`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `concurrency`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `sse`, `state_sequence`
- Rule tests for initial state, conversion floor/cap, ledger identity, Wire purchase/repricing/inactivity and sales distributions using controlled RNG; property tests for nonnegative conserved resource transfers.
- Command execution tests for stale-view legality, malformed/unknown actions, legal concurrent commands versus one-resource contention, and same-process retry/dedup semantics selected by the API task.
- Browser E2E proves clicks submit intent rather than locally award resources, server-derived views update, refresh does not roll back, and two pages share the sole default game.
- Persistence tests prove atomic full-state snapshots, last-successful recovery, no offline catch-up, complete RNG/timer/accumulator state, and continued simulation during saves.
- Rule/API/native-browser first-crossing and exact current-cost tests prove $5 initial charge, $6.10 successor charge and $6.21 next quote, below-cost no-ops, duplicate-ID receipt replay, permanent reveal and exact stored snapshot state without backfill.

**Risks and boundaries.**
- Do not confuse an outer Wire >=1 gate with a requirement to cover the whole automatic request. Do not expose arbitrary-number free-clip production as a player command.
- Stochastic sales and Wire repricing must preserve distributions/opportunities without requiring the reference RNG stream or browser timer schedule.
- M1 must not become a frontend-only click demo or an infrastructure shell; the AutoClipper must be an actual continuous producer in the one authoritative game.

### M2 — Trust-constrained self-modification and foundational Projects

**Granularity and ownership.** next_coarse; 38 features; families {"ACT": 2, "CTL": 1, "PRJ": 19, "PROG": 6, "RES": 3, "SYS": 3, "UI": 4}. Task IDs: `M2-C01`, `M2-C02`, `M2-C03`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-projects.md](./gameplay-projects.md) — `3. Project display, offers, and lifecycle`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-COMP-UNLOCK — Trust-Constrained Self-Modification, Computational Resources, and Projects`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `SYS-OPS-CREATIVITY-CURVES — Exact processor rates, Creativity curve, and Xavier recovery`

**Source rationale.** Primary sources: gameplay-projects.md sections 3, 5.1 and canonical PRJ-001..018/039; PROG-COMP-UNLOCK/TRUST/OPS/CREATIVITY/WIRE-RECOVERY/REVTRACKER; SYS-PROJECT-OFFER-LATCH and SYS-OPS-CREATIVITY-CURVES.

**Entry state.** M1 economy works. Computing and Projects still start locked; the state can reach either 2000 lifetime clips or the independent deadlock with Unsold <1, Funds below the current Wire quote, and Wire <1.

**Playable behavior.** The player allocates Human Trust between Processors and Memory, generates 10 Ops/s per Processor up to Memory*1000, buys project offers, unlocks Creativity at cap, and purchases the first 18 canonical projects plus RevTracker. Beg for More Wire supplies the genuine Trust-cost recovery path.

**Exit state.** Both computing unlock routes are demonstrated; a player can buy and use Creativity, additive AutoClipper upgrades, cumulative Wire-extrusion upgrades including project10b, Trust/creativity projects, and RevTracker. Displayed offers follow their PROPOSED source-preserving latch while purchase affordability remains server-authoritative. M2 independently proves ordinary allocation/Ops/creativity/panel/snapshot continuity without requiring an offered or purchased Xavier.

**Milestone dependencies.** `M1`

**Technical dependencies.** Extends the M1 state, Commands and project-offer model; all offers, uses, dynamic prices, rates and accumulators must be included in consistent snapshots and derived views.

**Accepted scenarios (source behavior).**
- At 2000 lifetime clips, Computing/Projects unlock without requiring deadlock. Independently, an early no-stock/no-Wire/insufficient-Funds state unlocks them before 2000; portfolio and liquid-Funds conditions for Beg for More Wire remain distinct.
- Initial Processor+Memory consume the initial Trust-2 capacity. Adding either requires unspent capacity without decrementing Trust. Memory adds 1000 max Ops; Processors regenerate 10 Ops/s each and recompute the exact nonlinear Creativity curve.
- Fresh Creativity speed remains 1 although evaluating the recomputation formula at P=1 yields zero. While Ops are held at cap after project3, Creativity accrues; spending below cap pauses it.
- PRJ-001/004/005 add +0.25/+0.50/+0.75 to one multiplier and PRJ-018 adds +5, never compounding those additions. PRJ-007..010 follow supply thresholds; PRJ-011 project10b uses the stochastic Wire quote and multiplies current supply by 11.
- A displayed offer remains eligible after its entry trigger ceases, until consumed or explicitly cancelled, but an unaffordable purchase is rejected at execution. Repeatable PRJ-002 requires its crisis trigger for each new offer; a purchase allowed at Trust -100 leaves -101 and no further affordable bailout.
- PRJ-039 RevTracker uses analytic demand estimates when stock suffices and rolling realized revenue when stock-limited; it does not itself sell clips or alter demand.
- ENG-TRUST-OPS-CREATIVITY independently validates M2 allocation and exact speed arithmetic without requiring offered or purchased Xavier: fresh speed 1 versus P=1 recomputation zero, P=2 positive and 20 Ops/s, legal capacity, full-cap Creativity and complete snapshots without offline gains.

**Catalog scenario links.** `ENG-PROJECT-OFFER-LATCH`, `ENG-TRUST-OPS-CREATIVITY`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `state_sequence`
- Per-project tests verify trigger, separate cost, exact effect, one-shot/repeat behavior, and downstream flag for every owned PRJ row; source-array position is not treated as an execution prerequisite.
- Sequence tests cover offer creation/latching/re-offer/cancellation, concurrency between an offer purchase and resource ticks, additive boost stacking, Wire-supply thresholds, both computation gates, and Trust target Fibonacci-thousand progression.
- UI/API tests expose Trust, next target, Processors, Memory, standard/temporary Operations, Creativity, project costs and meaningful rejection reasons without making client-disabled state authoritative.
- M2-only rule/API/browser/snapshot cases test exact Trust capacity, processor/Memory additions, 10/20 Ops/s, fresh-versus-recomputed nonlinear speed, full-cap Creativity, complete compute continuation and no M3 project purchase.

**Risks and boundaries.**
- The offer latch is PROPOSED, not CONFIRMED. Do not replace it with a continuously re-evaluated trigger or reproduce DOM nodes as authority.
- Negative Trust is meaningful for the bailout; Trust is otherwise configuration capacity, not a normal balance spent on Processor/Memory allocation.
- Do not infer project dependencies from numeric suffixes: project17 precedes project16 and PRJ-018 is a side branch, not part of boostLvl.

### M3 — Scaled Human automation, Quantum Computing, and alternate reset

**Granularity and ownership.** mapped_future; 20 features; families {"ACT": 3, "PRJ": 9, "PROG": 4, "RES": 1, "SYS": 2, "UI": 1}. Task IDs: `M3-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.3 Computation, Quantum Computing, and Swarm recovery`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-QUANTUM — Quantum Computing and Photonic Chips`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-TEMPORAL-RESET — Quantum Temporal Reversion`

**Source rationale.** Primary sources: ACT-MEGACLIPPER-BUY/WIREBUYER/QUANTUM-COMPUTE, SYS-QUANTUM-WAVES/OVERFLOW-DAMPING, PROG-CLIP-AUTOMATION/WIRE-MARKET/QUANTUM/TEMPORAL-RESET, and PRJ-023..027/046/047/094/096.

**Entry state.** M1/M2 production and compute work. At least 75 AutoClippers, 15 Wire purchases, five Processors, and sufficient Ops can be reached through real play. Existing persistent U/S may be absent on a first run.

**Playable behavior.** The player buys MegaClippers and their additive upgrades, toggles affordable WireBuyer, activates ten Photonic Chips sequentially, times signed quantum Compute, uses damped positive overflow, can repeatedly respec Processor/Memory through Xavier, and can choose Quantum Temporal Reversion after sufficiently negative Operations.

**Exit state.** MegaClipper production and full WireBuyer automation function through the shared conversion and dynamic Wire market. Ten chips produce inspectable waves; Xavier restores allocation capacity without resetting the run; Temporal Reversion clears ordinary state without granting U/S and retains existing U/S.

**Milestone dependencies.** `M2`

**Technical dependencies.** Adds deterministic wave clocks, portfolio-independent machine state, repeat uses/dynamic prices and full reset orchestration to the complete snapshot and derived view.

**Accepted scenarios (source behavior).**
- PRJ-023 unlocks MegaClippers only at 75 AutoClippers; PRJ-024/025/026 add +0.25/+0.50/+1 to the separate Mega multiplier. Release is not yet allowed to clear these levels.
- WireBuyer is offered after 15 purchases, starts internally ON, toggles without price, invokes the ordinary affordable purchase only at Wire <=1 in Human play, and never discounts or bypasses Funds.
- Quantum Computing requires five Processors before PRJ-046. Compute without an active chip says Need Photonic Chips. PRJ-047 buys exactly ten chips at 10000 then +5000 Ops each, with deterministic signed sinusoidal values rather than loot RNG.
- Overflow uses raw Q=ceil(360*sum), free capacity B and D=tempOps/100+5; if Q>B the actual immediate positive credit is based on ceil(Q/D), while feedback still reports raw Q. Negative qOps can expose PRJ-094 at Operations <=-10000.
- Each Human-stage PRJ-096 purchase costs 100000 Creativity and sets Processors/Memory/speed to zero, leaving Trust available and other ordinary run/prestige state intact. The first re-added Processor still has zero speed; the exact P=2 curve is positive. A second sufficiently funded distinct purchase charges another 100000 Creativity without a full-run/prestige reset.
- Confirming PRJ-094 adds 10000 standard Ops before full current-run reset, grants no prestige, clears project/strategy state, and retains separately stored U/S. Cancelling does not consume the offer.

**Catalog scenario links.** `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `E2E-XAVIER-ALLOCATION-RESET`, `E2E-FULL-PHASE-ENGINE-TRACE`, `RESET-INPROCESS-RETRY-RETENTION`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `concurrency`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `sse`, `state_sequence`
- Rule/sequence tests cover baseline and boosted Mega rates, all boost combinations, WireBuyer at empty/low Funds and ON/OFF, ten-chip limit/cost, signed sums, overflow fade/merge, negative trigger, the exact nonlinear curve, two real 100000-Creativity Xavier purchases and first/second-Processor recovery.
- Reset/persistence tests distinguish full run reset from last-snapshot crash recovery and prove no ordinary project, strategy, timer, or resource carryover after Temporal Reversion, while existing U/S survive unchanged.
- No arbitrary negative Compute input or debug reset is exposed. Controlled engine time/RNG is used for tests, never a public clock or resource-write API.

**Risks and boundaries.**
- Do not credit unrestricted raw qOps or make chip values random. Do not turn Xavier into a prestige reset or Temporal Reversion into an ending.
- PRJ-095 page-refresh use repair is a browser defect and is not implemented here or later. PRJ-094 confirmation UI may be native server-supported flow but not a commented cheat control.

### M4 — Investments, Yomi, and the complete strategy pool

**Granularity and ownership.** mapped_future; 37 features; families {"ACT": 5, "CTL": 3, "PRJ": 19, "PROG": 2, "RES": 2, "SYS": 4, "UI": 2}. Task IDs: `M4-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — `1.4 Investments and Strategic Modeling`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-INVESTMENTS — Algorithmic Trading and Investments`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-YOMI — Strategic Modeling, tournaments, and AutoTourney`

**Source rationale.** Primary sources: PROG-INVESTMENTS/YOMI/TRUST-PROJECTS; SYS-INVESTMENT-AUTO/TOURNEY-*; direct investment/tournament controls; PRJ-020..022/031..035/037/038/048..054/062/095.

**Entry state.** Human economy, compute, Creativity and automation work. Trust 8 can unlock Algorithmic Trading; Donkey Space can unlock Strategic Modeling; no investor or tournament behavior is yet required.

**Playable behavior.** The player deposits/withdraws Cash, selects risk, lets a stochastic portfolio trade automatically, upgrades its engine with Yomi, and runs full automatic tournaments with a selected strategy. The seven new strategies, Theory of Mind, CEV/humanitarian Trust routes, takeover/monopoly demand routes and closing Limerick become playable.

**Exit state.** Cash versus Stocks versus Total are distinct and Hostile Takeover/Full Monopoly can be reached. All N*N ordered tournament pairings, including self-play, generate valid-selection Yomi; the full eight-strategy pool and Theory of Mind work. Default no-selection behavior is demonstrated without reward or completed-result state.

**Milestone dependencies.** `M2`, `M3`

**Technical dependencies.** Adds snapshot-complete portfolio/RNG/tournament state to the same ordered simulation; no separate tournament turn or actor model. The no-selection and hover UI are derived from authoritative results.

**Accepted scenarios (source behavior).**
- Deposit transfers all ordinary Funds to integer investment Cash and Withdraw returns only Cash, never Stocks. Low/Med/High risk maps to 7/5/1 and changes reserves/budget and price step, not deposit timing.
- Controlled RNG verifies the 1 Hz 25% buy checks, five-holding cap, source price-band probabilities, 2.5-second move/sell opportunities and integer shares. PRJ-037 visibility uses portTotal>=10000 while its $1 million cost uses liquid Funds; PRJ-038 then costs $10 million Funds+3000 Yomi and multiplies distinct demand boosts.
- PRJ-020/021 expose Strategic Modeling. A new tournament charges current Ops and generates a symmetric integer 1..10 payoff grid. Every ordered pairing including h==v plays ten moves, and self-play credits both seats to the same strategy.
- The initial RANDOM-only self-play earns actual selected-score Yomi. Each PRJ-048..054 adds one real strategy and +1000 tournament Ops cost; PRJ-062 requires eight strategies, fixes cost 16000 and doubles score-derived Yomi only.
- Leaving Pick a Strat selected still spends 1000 baseline Ops and runs all matches, but awards no Yomi, creates no ordinary result state and does not establish the result flag needed by later AutoTourney. Clear feedback is PROPOSED; retroactive rewards/results are forbidden. Selecting a real strategy on a later run restores normal completion.
- PRJ-031..035 pay their exact Creativity/Yomi/Ops costs and grant their distinct Trust/stock modifiers as independent CEV siblings; PRJ-095 costs 1 million Creativity, grants no Trust, and is one-shot during uninterrupted play.

**Catalog scenario links.** `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Controlled-RNG distribution tests prove portfolio opportunities and tournament grids/RANDOM moves without matching reference random sequences; deterministic strategy fixtures distinguish each strategy rule.
- Sequence tests cover valid reward/placement, ties, both-seat self-play, Theory-of-Mind score boost versus later flat bonuses, no-selection cost/no result/no reward, hover information and delay reset, and Human-to-autonomy shutdown of investing in M5.
- Server-time tests prove tournaments/investments do not become Human/Agent turns and no browser/Agent wait pauses the shared simulation. Economy scenarios reach takeover and Trust routes without an operator resource-write API.

**Risks and boundaries.**
- No-selection display clarification remains PROPOSED; the cost, match execution, no reward and result-flag interruption are required source consequences.
- Do not turn portfolio Total into withdrawable Cash or into the Takeover purchase currency. Do not remove self-play, which would break early Yomi.
- PRJ-032..035 are siblings, not a chain. PRJ-061 AutoTourney is deliberately M5 because Trust 90 belongs to late-Human play.

### M5 — Late-Human Trust routes, AutoTourney, and HypnoDrone release

**Granularity and ownership.** mapped_future; 11 features; families {"ACT": 1, "PRJ": 7, "PROG": 2, "UI": 1}. Task IDs: `M5-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-TRUST-PROJECTS — Project routes to 100 Trust`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-HYPNO-RELEASE — Catchy Jingle to Release the HypnoDrones`
- [requirements/gameplay-projects.md](./gameplay-projects.md) — `5.2 Autonomy, terrestrial production, power, and space`

**Source rationale.** Primary sources: PROG-TRUST-PROJECTS/HYPNO-RELEASE, SYS-TOURNEY-NO-SELECTION, PRJ-019/028/029/030/043/044/061, and the Human-to-autonomy handoff in gameplay-actions.md.

**Entry state.** All Human economic/strategic routes from M2-M4 exist. The player can pursue 100 Trust through any supported combination of production targets, Creativity/CEV/humanitarian projects, market projects and late goodwill.

**Playable behavior.** The player automates valid-result tournaments, uses escalating goodwill where eligible, completes Catchy Jingle -> Hypno Harmonics -> HypnoDrones -> Release, then buys Tóth Tubule Enfolding in the resulting autonomous state. Creation replaces Human Business/Manufacturing.

**Exit state.** Release consumes the entire Trust pool, zeroes Auto/MegaClipper levels, disables Human sales/investment/WireBuyer, preserves the documented compute/capital/upgrades, and cancels active goodwill/Xavier offers. Tóth then exposes Unused-clip machinery. AutoTourney behavior before release includes paid automatic continuation and genuine no-selection interruption.

**Milestone dependencies.** `M2`, `M3`, `M4`

**Technical dependencies.** Requires cancellation of active offers, subsystem enable/disable transitions and full snapshot state. Tóth is sequenced inside this milestone after Release; The mapped platform capabilities do not require an extra milestone.

**Accepted scenarios (source behavior).**
- PRJ-061 requires Strategic Modeling and Trust>=90, costs 50000 Creativity, and toggles ON/OFF without another fee. Sufficient Ops plus a completed viewed valid result schedule New+Run; payoff-grid hover resets the viewing delay.
- A no-selection tournament from M4 awards nothing and leaves no result flag, so it interrupts AutoTourney even while ON. A later manual valid-selection tournament can restore continuation. Inactive browsers and reasoning Agents never create a pause or turn boundary.
- PRJ-043 requires Human, 85<=Trust<100 and lifetime clips>=101000000, costs $500000 and grants +1. PRJ-044 starts at $1 million, doubles after each +1 Trust purchase, and stops new offers at Trust 100.
- Release requires PRJ-029 and at least the 100-Trust price. At Trust 101 it still sets Trust to 0, not 1. Auto/Mega levels become 0 while lifetime/Unused capital, Ops capacity, Creativity, Yomi and purchased upgrades persist.
- Release removes any active PRJ-044 and PRJ-096 offers and ends production-Trust, sales/demand, investment and WireBuyer processing. Manual Make Paperclip remains outside the removed containers.
- Post-release PRJ-019 requires PRJ-017 and Human flag off, costs 45000 Ops, and exposes the path to Power Grid; it is not purchasable during Human play.

**Catalog scenario links.** `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Route tests demonstrate multiple legitimate Trust-100 combinations rather than requiring every project. Dynamic goodwill cost, one-shot/repeat limits and release cancellation are exercised with state-contending commands.
- Stage tests compare complete pre/post-release ledgers and panels; long-running sales/investment/Trust/legacy-clipper loops must stop while compute/projects/manual conversion and appropriate tournaments continue.
- AutoTourney tests include valid results, insufficient Ops, OFF state, no-selection interruption and recovery; no test fakes a pause, Agent turn or free tournament.

**Risks and boundaries.**
- The hard chain is PRJ-015 -> PRJ-013 -> PRJ-028 -> PRJ-029 -> PRJ-030; New Slogan is not a formal prerequisite. Tóth follows Release through an independent post-Human trigger.
- Do not merely subtract 100 Trust, preserve legacy clippers, or reset all prior progress. Release is the canonical autonomy handoff, not the commented HypnoDrone debug overlay.
- Only the next Milestone M2 needs coarse work packages for initial integration; M5 remains roadmap detail, not a stale Issue backlog.

### M6 — Autonomous matter, Wire, factories, and continuous Power

**Granularity and ownership.** mapped_future; 20 features; families {"ACT": 5, "PRJ": 5, "PROG": 3, "RES": 2, "SYS": 3, "UI": 2}. Task IDs: `M6-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-MATTER-PIPELINE — Available Matter to Acquired Matter to Wire to Paperclips`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-POWER — Power Grid, Solar Farms, Battery Towers, and Momentum`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `SYS-POWER-PARTIAL-BROWNOUT — Official brownout evidence and confirmed continuous-supply behavior`

**Source rationale.** Primary sources: PROG-TOTH-INDUSTRY/MATTER-PIPELINE/POWER; SYS-CLIP-PRODUCTION/POWER/POWER-PARTIAL-BROWNOUT; PRJ-036/040/041/042/067 and terrestrial construction/UI/resource rows.

**Entry state.** Tóth is complete after Release. Human Trust and legacy clippers are gone; Unused Clips, computing and strategic currencies remain. Available Matter is 6e27 unless already consumed, Acquired Matter 0, and Earth Power initially 0.

**Playable behavior.** The player buys Power Grid, Nanoscale Wire Production, both drone technologies and Clip Factories; then constructs Solar Farms, Battery Towers, Harvesters, Wire Drones and Factories with Unused Clips. Harvesters move Available -> Acquired, Wire Drones make Wire, Factories make clips through the shared three-ledger conversion.

**Exit state.** A functioning Earth industry acquires matter, produces Wire and clips under generated/stored Power, and exposes correct stocks/rates/costs. The confirmed continuous partial-battery rule is implemented exactly, including its downstream output effects.

**Milestone dependencies.** `M5`

**Technical dependencies.** Adds coupled deterministic accumulators and facility bills to ordered ticks/snapshots. Numeric time bases must keep S, D and B consistent; this is an engineering choice, not new game balance.

**Accepted scenarios (source behavior).**
- The actual project spine is PRJ-019 (M5) -> PRJ-067 Power Grid -> PRJ-036 Nanoscale -> PRJ-040 and PRJ-041 drones -> PRJ-042 Clip Factories. Stage flags, not the ordered achievement-message number, gate these offers.
- Batch construction buys exactly the requested 1/10/100/1000 units and requires the full computed escalating batch cost. Actual spends are tracked for later refunds; factories use the banded next-cost curve from ACT-FACTORY-BUILD.
- Harvester and Wire Drone output is capped by Available/Acquired Matter respectively and scales with asset count, Power and shared Work/Think. Factory output is capped by Wire and adds actual production equally to lifetime/Unsold/Unused.
- For S<D and B>=D-S, storage covers the deficit at base factor 1. For 0<B<D-S, the last partial-cover update consumes B and uses (S+B)/D. With empty storage it uses S/D. Tests reject both the old (2S+B-D)/D formula and a clamp of it.
- Surplus charges only up to 10000 MW-seconds per Battery Tower; farm generation and factory/drone consumption use documented normalized rates. Power UI shows generation, consumption, storage/max and Factory/Drone Performance.

**Catalog scenario links.** `ENG-POWER-FULL-COVER`, `ENG-POWER-LAST-PARTIAL`, `ENG-POWER-SURPLUS-CAP-SPACE`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Deterministic power boundary tests cover exact cover, just-insufficient storage, the final partially covered update, exhaustion, zero supply/demand safeguards required by the existing rules, storage cap, and downstream matter/Wire/clip changes.
- Matter-chain conservation and cap tests exercise insufficient input at every link and fractional automatic production. Simultaneous builds/ticks cannot double-spend Unused Clips or produce from nonexistent stock.
- Gameplay scenarios traverse Release/Tóth to a powered matter-to-clip chain through the real UI; API/SSE/persistence tests include Power, construction bills and all accumulators.

**Risks and boundaries.**
- This milestone intentionally owns the CONFIRMED Power deviation but no other behavior changes. Do not reuse the source partial-battery discontinuity.
- Human dollar costs are not reused for autonomous facilities. Full-batch affordability is authoritative even if a direct source function could partially execute.
- PROG/SYS shared conversion was implemented at M1 but completes its cross-stage acceptance here; later Space construction reuses the same legal internal operation, not a public arbitrary amount command.

### M7 — Capital recovery, Momentum, and quadratic industrial upgrades

**Granularity and ownership.** mapped_future; 15 features; families {"ACT": 5, "PRJ": 7, "PROG": 2, "RES": 1}. Task IDs: `M7-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-CAPEX-REFUNDS — Facility construction and Disassemble All refunds`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-INDUSTRY-UPGRADES — Factory and drone-flocking multipliers`

**Source rationale.** Primary sources: ACT-FACTORY/HARVESTER/WIREDRONE/FARM/BATTERY-DISASSEMBLE; PRJ-055..060/065; PROG-CAPEX-REFUNDS/INDUSTRY-UPGRADES/POWER; RES-ASSETS.

**Entry state.** Basic powered Earth industry works and can accumulate enough drones/factories/farms to trigger the industrial projects. Facility spend bills record actual manual purchase outlays.

**Playable behavior.** The player can Disassemble All each facility class for tracked-spend refunds and buy 10/20/50-factory, 500/5000/50000-drone and 30-farm projects. Late upgrades introduce the actual asset-level factors rather than flat-only bonuses.

**Exit state.** Refund/rebuild decisions work without erasing lifetime production, persistent maximum asset milestones or purchased upgrades. Momentum grows under fully supplied conditions; upgraded factories and each drone type exhibit the documented quadratic scaling.

**Milestone dependencies.** `M6`

**Technical dependencies.** Adds persistent maximum levels and exact immutable spend-ledger handling to snapshots. Facility reboot routines will later be reused by Space transition without charging player commands.

**Accepted scenarios (source behavior).**
- Factory Disassemble All returns factoryBill, resets level/bill/cost and preserves maxFactoryLevel; Harvester/Wire Drone equivalents preserve maximum-drone milestones and cause actual Swarm-size/composition effects once M8 exists.
- Farm disassembly refunds farmBill but does not itself erase stored Power; Battery disassembly refunds batteryBill and discards stored Power. All refunds increase Unused Clips only and never reduce lifetime clips.
- PRJ-055/056 multiply factory base rate by 100 and 1000 independently at 10/20 factories; PRJ-057 costs 1e21 Unused at 50 and adds the current factory-level factor, producing quadratic full output before Wire/Power caps.
- PRJ-058/059 multiply both drone base rates by 100/1000 independently at 500/5000 total drones. PRJ-060 costs 50000 Yomi at 50000 and sets droneBoost=2, adding each type’s own level factor, not exponential growth.
- PRJ-065 becomes available at 30 farms and costs 20000 Creativity. While fully supplied, including battery-covered deficits, Momentum adds the normalized +0.05/s modifier; insufficient supply recomputes from the confirmed brownout rules.

**Catalog scenario links.** `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Cost/refund tables verify every factory price band and exact partial historical bills built from mixed single/batch purchases. Disassembly tests distinguish farm-versus-battery storage and current versus maximum asset counts.
- Numeric production tests compare unupgraded, independently stacked and quadratic upgrade states at fixed Power/Work/input stock, then verify caps after multipliers.
- Recovery and disassembly-reentry tests ensure rebuilt facilities, active offers and old upgrades interact correctly after snapshot recovery without treating browser localStorage behavior as authority.

**Risks and boundaries.**
- Probe-built infrastructure later uses fixed costs and does not enter these manual bills. Do not erase upgrades on Disassemble All or confuse reset-cost with reset-max-level.
- This is not an alternate free resources or developer reset path; every refund is limited to recorded actual spend.

### M8 — Swarm Work/Think, Gifts, Boredom, and Disorganization

**Granularity and ownership.** mapped_future; 10 features; families {"ACT": 2, "CTL": 1, "PRJ": 1, "PROG": 2, "RES": 1, "SYS": 2, "UI": 1}. Task IDs: `M8-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-SWARM-GIFTS — Swarm Computing, Work/Think, and computational gifts`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-SWARM-HEALTH — Boredom, Disorganization, and swarm recovery`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `SYS-SWARM-HEALTH-GATES — Hidden health accumulation, status precedence, and power gates`

**Source rationale.** Primary sources: PROG-SWARM-GIFTS/HEALTH, SYS-SWARM-SIM/HEALTH-GATES, PRJ-066, CTL-SWARM-WORK-THINK and the two recovery actions/UI.

**Entry state.** At least 200 combined Harvester/Wire Drones can be operating on autonomous Earth. Human Trust is gone; Yomi, Creativity and post-Human compute remain. Swarm health accumulation conceptually runs after Release even before the panel unlock.

**Playable behavior.** The player buys Swarm Computing, chooses one shared Work/Think position, earns Gifts only while Active, spends one Gift per post-Human Processor/Memory addition, and remedies Boredom or Disorganization with Entertain or Synchronize.

**Exit state.** Work/Think changes drone production and gift progress as one trade-off. A genuine Active award uses the 125000-bit period and resets progress to zero without excess carry. Hidden/latched health, partial-Power Active status and status precedence are verified.

**Milestone dependencies.** `M7`

**Technical dependencies.** Adds gift bits, health counters/latches, slider and Gift-funded allocation to snapshots and real-time processing; no client attention or browser tab activity is a prerequisite.

**Accepted scenarios (source behavior).**
- PRJ-066 costs 36000 Yomi at 200 combined drones. Slider 0 gives drone work*2 and no Think; 200 stops those two drone processes and maximizes Think; intermediate values use (200-position)/100 and position/100.
- Active bit generation is ln(droneCount)*Think. At 125000 bits, gift size is max(1,round(log10(droneCount)*Think)), then giftBits=0. No excess carries into the next period, and no powMod multiplier scales gift generation.
- Only Active generates Gifts: Swarm must be enabled, powMod nonzero, at least two drones, no Bored/Disorganized override and, after later Space entry, Reboot. Sleeping, Lonely, zero-drone and NO RESPONSE never generate through the Active path.
- Boredom arises from sustained drone activity with zero Available Matter (source 30000 main updates/about 300 seconds nominal) and Entertain spends the current Creativity cost starting 10000, increasing by 10000. Restoring matter reduces counter but does not clear a latched Bored state.
- An effective drone-type ratio above 1.5 accumulates Disorganization to 100, balancing recovers slowly, and Synchronize spends 5000 Yomi to clear the state. Health can latch before project126 and becomes visible immediately on unlock.
- Feed/Teach/Clad stay non-implementation exclusions: their functions/statuses are not defined or assigned in the reviewed capture. They must not become invented Power/Ops/recovery actions.

**Catalog scenario links.** `ENG-GIFT-ACTIVE-RESET`, `ENG-GIFT-INACTIVE-HEALTH-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Exact gift arithmetic tests distinguish ln bit accumulation from log10 gift size, Active-only gating, the 125000 threshold, minimum/rounded award and zero reset. Zero/one/two-drone and partial/full-zero Power cases are separated.
- State-sequence tests cover pre-unlock health accumulation, Bored/Disorganized latching and precedence, Work/Think production extremes, and current-cost recovery commands under concurrent ticks.
- Three exclusion review records are linked to UI-SWARM acceptance; E2E shows only functional Bored/Disorganized recovery and non-functional legacy controls are not advertised as gameplay.

**Risks and boundaries.**
- Health status does not add an undocumented industrial penalty beyond Power and Work/Think. Partial nonzero Power does not sleep or scale Gifts.
- The commented old gift accumulator and undefined Feed/Teach/Clad affordances are not alternative mechanics. Space NO RESPONSE/Reboot is exercised after M9/M10.

### M9 — Earth exhaustion and the Space Exploration handoff

**Granularity and ownership.** mapped_future; 3 features; families {"PRJ": 1, "PROG": 1, "UI": 1}. Task IDs: `M9-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-SPACE-ENTRY — Space Exploration`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `SPACE-ENTRY-002 — Space Exploration transition and refunds`

**Source rationale.** Primary source: PRJ-045 Space Exploration plus PROG-SPACE-ENTRY, SPACE-ENTRY-002 alias detail, SYS-POWER handoff and UI-SPACE in the five reviewed documents.

**Entry state.** Autonomous Earth has working industry, Power, refunds, upgrades and Swarm. Available Matter can reach exactly zero through the real matter chain; the player can accumulate the large Space costs.

**Playable behavior.** The player decides when to buy Space Exploration after Available Matter reaches zero. The transition converts the established Earth economy into space-capable production and exposes Launch Probe and Probe Design surfaces for the next increment.

**Exit state.** Space is active after paying 120000 Ops, 10000000 stored MW-seconds and 5e27 Unused Clips. All five terrestrial facility classes refund their recorded bills and reset; remaining stored Power clears; one residual farm and powMod=1 remain; manual terrestrial build controls hide and ongoing terrestrial Power limits end.

**Milestone dependencies.** `M8`

**Technical dependencies.** Requires one atomic transition that reuses internal facility reboot operations and updates public derived views. Its snapshot includes all refunds, flags and timers; no offline catch-up applies if the process restarts.

**Accepted scenarios (source behavior).**
- The offer checks post-Human Available Matter==0 separately from its three costs. Zero Available Matter does not erase Acquired Matter, Wire, Unused capital or computing and may start Boredom before Space.
- Purchase deducts all costs, resets the boredom counter rather than a latched Bored flag, and invokes factory, Harvester, Wire Drone, farm and battery reboot behavior, including batteryBill refund and clearing remaining storage.
- Lifetime clips, Unused capital after costs/refunds, projects, compute, Creativity, Yomi and upgrades persist. The ordered achievement track advances from 13 to 14 only after earlier messages catch up; independent flags control feature availability.
- Space UI shows the launch/population surface with loss rows initially hidden. Probe Trust and non-Combat traits become available for M10; Combat allocation still requires project131 and Increase Max Trust requires project121.
- After Space begins, production is not throttled by terrestrial Power and manual terrestrial controls are hidden. The residual single farm is not advertised as a new Space generator.

**Catalog scenario links.** `ENG-POWER-SURPLUS-CAP-SPACE`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Transition tests compare pre/post-state for each cost, all five bills/facility resets, battery storage, residual farm/powMod, retained projects/currencies and UI gates.
- Refusal tests cover unavailable matter, each insufficient cost and concurrent attempts so no partial refund/transition occurs. Recovery restores either the complete pre-transition or post-transition state, never half.
- A playable Earth-exhaustion scenario reaches and purchases Space through production rather than debug zero-matter or free-clip controls.

**Risks and boundaries.**
- Space does not globally reset the run or create a second game. No Power deficit should throttle later Probe-built facilities.
- The exact timer/performance cadence is not copied, but refunds, retained state and full-power production are gameplay.

### M10 — Probe design, growth, recovery, and live direct Combat

**Granularity and ownership.** mapped_future; 50 features; families {"ACT": 18, "COMBAT": 6, "PRJ": 5, "PROBE": 7, "PROG": 4, "RES": 3, "SPACE": 5, "SYS": 1, "UI": 1}. Task IDs: `M10-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-PROBE-SIM` - exploration, replication, construction, attrition, and drift`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-PROBE-DESIGN — Von Neumann Probe Design and probe Trust`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `COMBAT-CORE-001 — Drifter Attack scheduling`

**Source rationale.** Primary sources: PROG-PROBE-DESIGN/PRODUCTION/ATTRITION/SPACE-RECOVERY, SYS-PROBE-SIM, SPACE-MATTER-001..005, PROBE-STAT-002..007/DRIFT-001, COMBAT-CORE-001..005/009, PRJ-068..071/075 and all Probe controls.

**Entry state.** Space is active with full-power production and the retained compute/economy/projects. Probe Trust, eight traits, launched/descendant/loss counters begin at documented initial values; no battle needs to have occurred.

**Playable behavior.** The player buys Probe Trust with Yomi, launches a 1e17-Unused Probe, reversibly allocates Speed/Exploration/Replication/Hazard/Factory/Harvester/Wire traits, and grows self-sustaining infrastructure. Drift creates opposition automatically; live battles start, casualties unlock Combat allocation, and recovery projects handle hazards, Swarm and no-Probe deadlock.

**Exit state.** Exploration/replication/auto-building/attrition and the complete matter chain operate continuously with fractional population accounting. Memory release and Swarm Reboot work under their precise gates. Real canvas-equivalent combat causes global Probe/Drifter losses; project131 exposes linear-offense Combat allocation after the first combat loss.

**Milestone dependencies.** `M9`, `M4`, `M8`

**Technical dependencies.** Requires deterministic server simulation plus a separate combat simulation representation in the same ordered game state; continuous fractional quantities, RNG state, active battle ships/local grid, losses and all allocations are snapshot-complete. The browser renders server-derived combat and never decides deaths.

**Accepted scenarios (source behavior).**
- Increase Probe Trust starts at 500 Yomi and uses floor((probeTrust+1)^1.47*500), limited by Max Trust 20. Purchasing total Trust increases drift even when unallocated; trait arrows spend/release one shared point with no Yomi refund.
- Launch costs exactly 1e17 Unused Clips and adds one Launched Probe. The implementation makes affordability/execution agree at equality rather than reproducing the enabled-at-equality/internal-strict-greater no-op.
- Discovery uses floor(P)*1.75e18*Speed*Exploration and caps at 3e55 total matter. Speed or Exploration zero prevents discovery. Replication preserves positive fractional growth, charges only produced descendants at 1e17 each, and keeps population/cost/loss counters coherent.
- Hazards accumulate P*.01/(3*Haz^1.6+1), with PRJ-069 halving after 100 losses. Auto factories cost 1e8 and drones 2e6 each, without terrestrial bills or escalating curves. Space matter conversion/factories run at powMod=1 and still honor Work/Think.
- Drift converts P*1e-6*probeTrust^1.2 Probes into current Drifters and lifetime drift losses. Reject is not yet selected, so existing drift continues. More purchased Trust creates real risk.
- PRJ-075 Memory release requires Space, P==0, Unused<1e17, milestone<15 and at least 10 MEM; it spends 10 MEM for 1e22 Unused without adding lifetime clips and repeats only while valid. One grant covers 100000 standard launches.
- PRJ-070 Reboot costs 100000 Ops with Space and at least two drones. It clears only NO RESPONSE; Bored/Disorganized overrides still require their M8 remedies. Matter conversion continues under NO RESPONSE, but normal Gifts do not.
- With Drifters>1000000, P>0 and no active battle, each eligible check has a 50% attack chance and one active-battle cap. Battle scale, randomized local ship layout/co-location, live casualty rolls and result removal run automatically with no tactical button.
- Probe deaths remove min(unitSize,P) and add the actual amount to combat losses. Drifter deaths use linear probeCombat, so zero Combat cannot kill Drifters. project131 costs 150000 Ops after one real loss and reveals Combat allocation; it neither creates battles nor grants Honor.
- PRJ-068 adds fixed first/second/third 50000/30000/20000 Yomi placement bonuses, including ties, under its Space/eight-strategy/Yomi-below-next-Trust-price gate; it does not replace score-derived Yomi.

**Catalog scenario links.** `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `ENG-POWER-SURPLUS-CAP-SPACE`, `ENG-COMBAT-NAMING-HONOR-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `state_sequence`
- Probe rule tests cover allocation budget/reversibility, zero-stat boundaries, exploration caps, continuous fractional replication/attrition, fixed construction affordability and conserved population/matter/three-ledger transfers.
- Recovery tests include insufficient Memory, exact probe-cost equality, milestone gate, repeated Memory release, and Reboot versus latched health. Persistence proves all populations, fractions/accumulators, probeHarv and battle state follow coherent product rules rather than source-save omissions.
- Combat unit/sequence tests verify unitSize, opening-force/hinder rolls, local co-location, independent nonnegative global casualties, linear offense, project131 unlock and unnamed-battle absence of Honor. Controlled RNG checks distributions, not exact sequences.
- Browser/API acceptance shows no direct start/stop/retreat control, Combat statistics and losses tied to actual world state, continuous production with no observers, and all allocation/progress state surviving the chosen snapshot semantics.

**Risks and boundaries.**
- Do not floor global Probe population to whole individuals or charge unproduced descendants. Combat icons are visual entities; real global populations are continuous where the source economy requires it.
- Unnamed battles already inflict casualties. Do not gate the battle simulation on project121 and do not confuse project131 Combat with project121 Name the battles.
- The commissioning UI/tooltip must follow the PROPOSED active-offense classification for Combat: direct offense only; OODA+Speed supplies direct defense in M11.
- TIMING/RNG/pixel mantissa parity and source persistence defects are excluded; local co-location and linked casualties are not disposable presentation.

### M11 — OODA, named battles, signed Honor, and Max Trust

**Granularity and ownership.** mapped_future; 14 features; families {"ACT": 1, "COMBAT": 4, "PRJ": 5, "PROBE": 1, "PROG": 1, "RES": 1, "UI": 1}. Task IDs: `M11-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-DRIFTWAR — Optional combat, OODA, battle naming, Honor, and maximum Trust`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `COMBAT-HONOR-002 — VICTORY and DEFEAT Honor calculation`

**Source rationale.** Primary sources: PROG-DRIFTWAR, PROBE-STAT-001, COMBAT-CORE-006/007/008, COMBAT-HONOR-002, PRJ-063/064/072/073/074, ACT-PROBE-MAXTRUST-INCREASE and UI-COMBAT/RES-HONOR.

**Entry state.** M10 battles and casualties work. Combat losses can reach 10000000; Combat allocation exists through project131, but no battle result/Honor economy is yet required.

**Playable behavior.** The player buys OODA for Speed-based defense, Name the battles for named results/Honor, and the three Honor projects. Named victories/defeats change signed Honor; Honor buys additional maximum Probe Trust; design allocation and Glory/Threnody create the late-war economy.

**Exit state.** Live combat includes OODA defense, deterministic one-result outcomes including simultaneous annihilation, timeout without victor/reward/streak reset, historical naming with per-name counters, and signed Honor. Increase Max Trust spends exactly 91117.99 Honor for +10 cap without granting Trust points.

**Milestone dependencies.** `M10`

**Technical dependencies.** Adds battle outcome latches, naming counters, signed Honor, Glory and Cap state to snapshots/commands. Old Battle Reports, commented offense exponent, naming offense multiplier and territory loss stay exclusions.

**Accepted scenarios (source behavior).**
- PRJ-063 requires project131 and 10000000 combat losses, costs 175000 Ops+45000 Yomi, and adds 0.2*probeSpeed to the Probe death threshold. Live code reads Speed, not the obsolete attackSpeed branch.
- PRJ-064 requires 10000000 combat losses but not project131 explicitly, costs 225000 Creativity, enables names/results/Honor and exposes Increase Max Trust. It does not itself add Max Trust or kill more Drifters.
- Named victory adds opening battleRIGHTSHIPS+current Glory bonus; defeat subtracts opening battleLEFTSHIPS, resets Glory and selects a threnody title. Honor can become negative. Casualties and Drifters Killed are not the Honor formula.
- Simultaneous annihilation follows the PROPOSED first-DEFEAT economics with exactly one consistent display and one Honor application. Timeout/stalled removal yields neither victory nor defeat, no Honor and no Glory reset; clear no-victor feedback is allowed by its PROPOSED classification.
- PRJ-074 Glory costs 200000 Ops+30000 Yomi. A victory uses current bonus then raises the next by 10; defeat resets it, timeout does not. PRJ-072 costs its exact Ops/Creativity/5e31 Unused price for +50000 Honor.
- PRJ-073 requires Name and probeUsedTrust==maxTrust, starts at 50000 Creativity+20000 Yomi for +10000 Honor, then adds 10000 Creativity and 40% Yomi per purchase. Dynamic battle attribution remains informative; no stale-title resource rule is invented.
- Increase Max Trust is fixed-price repeatable Honor expenditure and exposes Used/total/Max separately. It does not allocate stats, reduce current drift directly or replace Yomi Probe-Trust purchases.

**Catalog scenario links.** `ENG-COMBAT-NAMING-HONOR-GATES`, `ENG-COMBAT-TIMEOUT-HONOR`, `ENG-HONOR-NEGATIVE-AND-GLORY`, `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Combat probability tests compare OODA-on/off Probe thresholds and linear Drifter offense, using controlled local grids/RNG. No test uses the legacy probeCombat^1.7 or territory-loss path.
- Outcome tests cover ordinary victory/defeat, simultaneous tie, duplicate latch suppression, stalled/overlong timeout, negative Honor, exact opening-ship Honor basis and Glory victory/defeat/timeout sequence.
- Project/action tests cover dynamic Threnody costs/full-allocation gate, Monument cost/reward, fixed 91117.99 Max Trust cost and +10 cap, concurrent purchases versus battle results, and snapshot/retry consistency.
- UI evidence distinguishes Combat canvas/Drifter rows unlocked by first battle, Combat allocation from project131, and result/Honor/Max Trust from project121. Unnamed historical battles still show their real casualties without retroactive Honor.

**Risks and boundaries.**
- Negative Honor and timeout/no-reward/no-streak-reset are intentional. Do not clamp Honor to zero or call timeout a defeat.
- project121 and project131 are not interchangeable: project131=Combat allocation; project121=names/results/Honor/Max Trust control.
- Driftwar remains optional for universal achievement; finishing these systems must not insert a victory or zero-Drifter predicate into M12.

### M12 — Universal achievement, Emperor dialogue, and mutually exclusive choice

**Granularity and ownership.** mapped_future; 11 features; families {"PRJ": 9, "PROG": 2}. Task IDs: `M12-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-UNIVERSAL-GOAL — Universal Paperclips achievement`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-END-CHOICE — Emperor dialogue, Accept, and Reject`

**Source rationale.** Primary sources: PROG-UNIVERSAL-GOAL/END-CHOICE, END-COMPLETE/DIALOG/BRANCH aliases and PRJ-076..084 in gameplay-projects.md, gameplay-progression.md and gameplay-combat-endgame.md.

**Entry state.** The Space simulation and ordered achievement messages can reach milestone 14. Optional Combat/Honor may be entirely unused. Sufficient Operations remain to buy seven sequential 1-Op messages and one 1-Op choice.

**Playable behavior.** Either universal predicate produces Universal Paperclips achieved. Seven Emperor messages then unlock in order, followed by exactly one Accept/Reject branch. Accept exposes two destinations; Reject stops new drift and starts teardown timers without immediately erasing the world.

**Exit state.** Universal achievement (flag 15) and Emperor choice are distinct, demonstrable states. Both independent achievement predicates and both choice branches are accepted in separate branch instances. No Driftwar victory, zero Drifters or battle completion is required.

**Milestone dependencies.** `M10`

**Technical dependencies.** Adds ordered narrative/completion flags and branch timers to full snapshots. Alternative branch acceptance needs legitimate independent states, not a public state-write/reset cheat endpoint.

**Accepted scenarios (source behavior).**
- Route A: with milestone 14, lifetime clips>=3e55 advances to 15 without requiring Found/Available/Wire exhaustion, zero Drifters, zero Probes or any victory.
- Route B: with milestone 14, Found Matter>=3e55 AND Available Matter<1 AND Wire<1 advances to 15. Acquired Matter, Drifters, Probes and victories are not tested; below-one here is not the exact-zero Reject credit gate.
- The seven projects PRJ-076..082 appear sequentially only after flag 15/previous message, each charges its real 1-Op cost despite a blank source tag, and only then expose Accept/Reject. Reaching achievement alone neither opens the choice nor restarts.
- Accept PRJ-083 charges 1 Op, removes both choices and exposes PRJ-085/086. It does not award prestige or reset until a destination is bought.
- Reject PRJ-084 charges 1 Op, removes both choices, sets new value drift to zero for this run and starts endTimer1. Existing Probes, Drifters, production and battles remain until later dismantling; there is no Accept destination on this branch.
- Accept and Reject cannot both complete in one branch instance. Tests use independent pre-choice runs/snapshots rather than pretending a single save can own every ending flag simultaneously.

**Catalog scenario links.** `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `property`, `rule_unit`, `state_sequence`
- Predicate tables test each OR branch, each required AND term of exhaustion, just-below/above thresholds, nonzero Drifters/Probes and no-victory states. Ordered achievement catch-up tests separate telemetry flag 14/15 from independent feature gates.
- Dialogue tests verify seven real costs/order and mutual exclusion at execution time under concurrent commands. Branch tests prove Accept-only destination offers and Reject-only drift/timer behavior.
- A playable scenario reaches flag 15 without ever completing a named battle; a second reaches exhaustion with fractional Available Matter/Wire below one and no exact-zero requirement.

**Risks and boundaries.**
- Do not replace the OR predicates with a universal Driftwar gate or merge achievement, choice, prestige restart and credits into one gameComplete boolean.
- The two universal thresholds use 3e55 total matter. Do not loosen below-one to an arbitrary epsilon and do not apply the confirmed final-Reject Wire exception here.

### M13 — Accept destinations, persistent prestige, and clean restart

**Granularity and ownership.** mapped_future; 5 features; families {"PRJ": 2, "PROG": 1, "RES": 1, "UI": 1}. Task IDs: `M13-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-PRESTIGE — The Universe Next Door, The Universe Within, and persistent bonuses`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `RESET-CORE-001 — Full current-run reset versus retained prestige`

**Source rationale.** Primary sources: PROG-PRESTIGE/TEMPORAL-RESET, RESET-PRESTIGE/CORE aliases, PRJ-085/086, RES-PRESTIGE and UI-PRESTIGE in the progression/combat-endgame documents.

**Entry state.** A branch instance has completed the Emperor dialogue and Accept. One of the two destinations can be afforded; separately stored U/S may already be nonzero from earlier runs.

**Playable behavior.** The player chooses either The Universe Next Door for U or The Universe Within for S. Each purchase immediately resets the current run, retains both persistent counters and starts from documented initial state with the corresponding linear bonus visible once nonzero.

**Exit state.** The two alternate restarts are independently verified. Next Door increments U and boosts Human demand by 1+U/10; Within increments S and boosts Creativity speed by 1+S/10. Ordinary run/project/strategy state does not carry over. Choosing Accept alone has not restarted.

**Milestone dependencies.** `M12`

**Technical dependencies.** Requires atomic meta-prestige persistence plus current-run reconstruction in the default game, preserving one shared instance and server authority. No multi-instance lobby/registry is introduced.

**Accepted scenarios (source behavior).**
- PRJ-085 costs 300000 Ops after Accept, increments U, announces entry and resets. PRJ-086 costs 300000 Creativity after Accept, increments S, announces entry and resets. They cannot both be bought in one branch instance.
- A restarted run restores initial Wire/clips/Funds/compute/projects/strategies and clears ordinary timers/offers. Existing U and S both persist; only the chosen counter increments. Header Universe/Sim Level become visible when nonzero and display persistent counter+1 as in the source.
- With U=10, demand uses a linear 2x prestige factor, not 1.1^10; U does not scale space matter conversion. With S>0, effective Creativity speed is base speed*(1+S/10), including high-speed fractional awards; it cannot make zero post-Xavier speed positive.
- Quantum Temporal Reversion from M3 remains an independent non-prestige reset: it grants no U/S and retains existing U/S. Xavier remains only a Human allocation reset, and browser refresh/crash recovery is not a new run.

**Catalog scenario links.** `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `E2E-FULL-PHASE-ENGINE-TRACE`, `RESET-INPROCESS-RETRY-RETENTION`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `concurrency`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `sse`, `state_sequence`
- Restart tests compare complete ordinary-state reset vectors and persistent U/S before/after each destination, including no active project/strategy carryover. They also test only one destination can execute against one pre-choice state.
- Economic tests measure exact linear U demand and S creativity effects in real subsequent play, with zero-counter behavior unchanged and UI readouts appearing only when persistent values are nonzero.
- Recovery tests distinguish choosing a persisted destination transition from process crash/last-snapshot restore. No manual save slots, Reset Prestige, free-prestige or debug reset controls are added.

**Risks and boundaries.**
- Prestige persistence is a product rule, not a reason to copy localStorage keys or browser reload. The exact storage transaction/reset handoff is an engineering task, not a new gameplay ending.
- Do not let ordinary snapshot recovery grant prestige repeatedly or duplicate a destination on retry. Each executed destination has one increment and one restart.

### M14 — Reject teardown: Probes through Memory

**Granularity and ownership.** mapped_future; 14 features; families {"END": 7, "PRJ": 7}. Task IDs: `M14-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-projects.md](./gameplay-projects.md)
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-REJECT-END — Ordered disassembly, final manual clips, and credits`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `Universal completion, Emperor branch, disassembly, and credits`

**Source rationale.** Primary sources: PRJ-087..093, END-DISMANTLE-001..007 and PROG-REJECT-END staging in gameplay-combat-endgame.md/gameplay-progression.md; UI-ENDING handoffs.

**Entry state.** An independent Emperor branch has selected Reject. New value drift is zero and endTimer1 is advancing; existing Probes, Drifters, battles, production and currencies remain until their specified stages.

**Playable behavior.** The player funds and purchases seven ordered disassembly projects, watches Probe Design/Space/Combat/Honor/Swarm/production/Strategy/Quantum/compute surfaces retire, and retains the manual Make Paperclip path as automatic production stops.

**Exit state.** Memory disassembly completes dismantle=7: Probes/drones/factories/processors/memory are zero, Creativity and automatic clip production are off, Strategy/AutoTourney are disabled, and remaining Wire plus the four teardown grants await final conversion. Credits have not yet been earned merely by dismantling.

**Milestone dependencies.** `M12`

**Technical dependencies.** Requires durable ending timers/latches and atomic per-stage purchases. Alternative Reject path does not depend on Accept or prestige. No public restart or debug advance control is introduced.

**Accepted scenarios (source behavior).**
- After endTimer1>=1000, PRJ-087 costs 100000 Ops, zeroes Probes, adds 100 lifetime+Unused clips and sets dismantle=1; Probe Design and then Space/Combat/Honor surfaces retire in ordered feedback.
- After PRJ-087 and reset timer1>=350, PRJ-088 costs 100000 Ops, zeroes both drones, adds another 100 lifetime+Unused and starts timer2. PRJ-089 then costs 100000 Ops after timer2>=300, zeroes factories and adds 15 lifetime+Unused. Its timer-only indirect dependency is preserved.
- After timer3>=150, PRJ-090 costs 100000 Ops, disables AutoTourney, grants 50 Wire and sets dismantle=4. From this stage all factories and legacy Auto/MegaClippers stop; manual conversion remains.
- After timer4>=100, PRJ-091 costs 100000 Ops and sets dismantle=5. The integrated chip sequence returns one Wire at each of ten checkpoints (+10 total); Compute and later Quantum UI retire. PRJ-092 becomes eligible after PRJ-091 and reset timer4>=300.
- PRJ-092 costs 100000 Ops, disables Creativity, zeroes Processors, grants 20 Wire and sets the next displayed Memory price to the then-current standardOps. PRJ-093 after timer5>=150 spends all remaining standard Ops, zeroes Memory, grants 20 Wire and sets dismantle=7.
- Teardown grants total 50+10+20+20=100 Wire, but pre-existing Wire can require more than 100 final manual commands. Reaching the stylized final-100 display alone is not the credit gate.

**Catalog scenario links.** `E2E-REJECT-CREDITS`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `state_sequence`
- Ordered state-machine tests drive ending timers in the pure engine, verify each stage’s costs/grants/flags/UI and reject early/out-of-order purchases. Timer cadence is not a production public step API.
- Resource tests prove Probe/Swarm/Factory grants affect only lifetime+Unused, Strategy/Quantum/Processor/Memory grants affect Wire, all automatic clip callers stop exactly at dismantle>=4, and no hidden producer remains.
- Persistence/retry tests cover every in-progress ending timer, dismantle stage, chip checkpoint, operation price and valid-click count without copying source audio/reload defects. Snapshot state remains consistent during the entire handheld final sequence.

**Risks and boundaries.**
- Do not start Reject by immediately deleting Probes/Drifters/battles. Do not make Memory a fixed-price project or leave Ops/Processors/Creativity alive after their stages.
- Exact presentation timer thresholds may be normalized as documented, but causal order and resource effects are mandatory. Accept destinations never appear on this branch.
- END-FINAL fraction handling and credits belong to M15 so this milestone exits at a playable teardown state, not a claimed completed ending.

### M15 — Final positive Wire conversion, exact-zero credits, and full-game closure

**Granularity and ownership.** mapped_future; 7 features; families {"END": 2, "PROG": 3, "RES": 1, "UI": 1}. Task IDs: `M15-C01`.

**Source documents.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md)
- [requirements/gameplay-actions.md](./gameplay-actions.md)
- [requirements/gameplay-progression.md](./gameplay-progression.md)
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
**Engineering references.**
- [requirements/product.md](./product.md)
- [requirements/runtime.md](./runtime.md)
- [requirements/clients.md](./clients.md)
- [requirements/testing.md](./testing.md)
**Unique source headings used by this map.**
- [requirements/gameplay-inventory.md](./gameplay-inventory.md) — `4. Complete progression spine`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `END-FINAL-001 — Final manual Paperclips and the final-100 counter`
- [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `END-FINAL-002 — Universal Paperclips credits and threnody`
- [requirements/product.md](./product.md) — `7. Final Acceptance Principles — CONFIRMED`

**Source rationale.** Primary sources: PROG-REJECT-END/MILESTONES/AUTO-LOOPS, END-FINAL-001/002, UI-ENDING/RES-PROGRESSION and the final reset/persistence boundaries in all five gameplay documents plus product.md.

**Entry state.** An independent Reject run has completed Memory disassembly and retains some Wire, potentially including an automatic-production fractional residue. All other milestones and both alternate Accept destinations have their own acceptance evidence.

**Playable behavior.** The player manually converts all remaining Wire, including one positive sub-one final remainder under the single confirmed Reject exception, reaches exact zero, and sees the one-time ordered threnody/credits through flag 20. Final integration replays early-to-late systems and every reset distinction.

**Exit state.** Credits completed (20) is distinguished from achievement (15), Emperor choice, dismantle=7 and prestige restart. Zero-Wire commands stay invalid; ordinary below-one conversion remains invalid everywhere else. Reject exposes no subsequent restart control. All 274 feature owners are implemented across appropriate branch instances and the full game can be traversed without debug/state-write APIs.

**Milestone dependencies.** `M11`, `M12`, `M13`, `M14`

**Technical dependencies.** Final integration validates full snapshot/RNG/timer/combat/ending/meta-prestige state and continuous server operation. No new runtime feature can relax authoritative Commands, no-offline-catch-up, shared default game, client neutrality or native UI rules.

**Accepted scenarios (source behavior).**
- Ordinary final commands with Wire 2 produce 1 and leave 1; a later full-Wire command leaves 0. With Wire 0.2 in dismantle>=4, one accepted command produces min(1,0.2)=0.2, adds exactly 0.2 to EACH of lifetime/Unsold/Unused, consumes all Wire and increments accepted conversions once.
- At Wire 0, a final command changes no ledger/counter and does not satisfy credits by itself. Credits begin only with Memory disassembled AND Wire exactly 0; a positive remainder converted before Memory still leaves credit blocked until Memory is complete.
- The same fractional command outside Reject dismantle>=4 is rejected. The universal-exhaustion predicate still uses Available Matter<1 and Wire<1, not exact zero and not this Reject exception.
- Concurrent/duplicate final clicks and tick/order permutations cannot create negative Wire, double-credit one conversion or run credits twice. One accepted positive command means one counter increment regardless of fractional amount.
- Once Memory is disassembled and Wire==0, timer6 advances and credits publish once in order: Universal Paperclips, Frank Lantz, Bennett Foddy, music permission and copyright, reaching flag 20. Exact audio/browser timings are presentation; no automatic prestige or restart follows.
- Restart matrix: Next Door => +U and clean run; Within => +S and clean run; Temporal Reversion => clean run, no new U/S, existing U/S retained; Xavier => Processor/Memory/speed reset only; process refresh/crash => reconnect/recover, not reset; Reject credits => terminal display with no exposed subsequent restart.
- Whole-game acceptance traverses initial manufacturing through space to universal achievement without Driftwar victory, then separately Accept/Next Door, Accept/Within, Reject/credits and Temporal Reversion. No single branch is expected to own mutually exclusive ending projects simultaneously.

**Catalog scenario links.** `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `E2E-REJECT-FINAL-WIRE`, `CONC-REJECT-FINAL-WIRE`, `E2E-REJECT-CREDITS`, `E2E-FULL-PHASE-ENGINE-TRACE`

**Test layers and required evidence.** Layers: `api_contract`, `browser_e2e`, `concurrency`, `gameplay_scenario`, `long_simulation`, `persistence`, `property`, `rule_unit`, `state_sequence`
- Focused final-Wire unit/API/concurrency tests cover full, sub-one, zero, pre-stage, before/after-Memory, same-key retry/conflict and many-clients contention with exact ledgers/counters, not only HTTP statuses.
- Endgame sequence tests verify exact-zero timer gate, credit idempotence, ordered flags 16-20, no restart/destination offers and snapshot/recovery at each final stage.
- Cross-game sequence/property tests cover milestone catch-up, continuous independent loops, all relevant resource invariants, loop shutdown, alternate resets and long-run no-deadlock paths. Controlled time/RNG accelerates pure-engine/integration runs without production pause/step controls.
- Final source/coverage reconciliation recomputes exact 274 feature ownership, 96 ordered projects, 61 handlers, 32 aliases and 7 exclusions, then links each to targeted executable evidence. This is semantic acceptance, not a magic coverage percentage.

**Risks and boundaries.**
- Only two CONFIRMED deviations exist: continuous partial-battery Power (M6) and final positive Reject Wire remainder (this milestone). Do not generalize either into other conversions or systems.
- Credits require exact zero and Memory; stylized finalClips==100 presentation is not the gate. Existing pre-teardown Wire may require additional clicks and zero-Wire pre-validation counter increments are not copied.
- No source-backed restart follows Reject credits; inventing one would violate the documented endpoint. Full-clone coverage spans independent alternate runs, not one impossible all-branches save.

## 5. Runtime, API, persistence, and native-client contract

The following is the integrated engineering contract. CONFIRMED gameplay/runtime requirements remain distinct from PROPOSED field names, 10 ms/lag/numeric choices, SQLite layout, and protocol encodings. These proposals belong to the detailed M1 tasks and may be measured and narrowed there without weakening confirmed behavior.

### 5.1 Source invariants and proposed implementation design

#### 2. Source invariants and proposed engineering defaults

The following are non-negotiable source requirements:

- One anonymous shared world is internally named `default`; opening a page never creates another game.
- The in-memory Rust state is authoritative. Clients submit intent, never new totals.
- A single writer serializes Commands and simulation ticks, and validation plus application occur atomically at execution.
- The simulation runs without pages, SSE subscribers, or Agent reasoning. There is no public pause, tick, time-step, operator resource-write, or debug endpoint.
- Process-lifetime retries of one logical Command execute at most once. A stale View alone never invalidates a currently legal Command.
- Full, logically consistent snapshots include every implemented domain's timers, accumulators, RNG state, progression, run state, and persistent prestige. SQLite transactions make replacement atomic.
- The normal snapshot interval is approximately 30 seconds. Recovery loads the last committed snapshot, starts a new process `run_id`, and performs no offline production or other backfill. Unsaved rollback is allowed.
- Only the two confirmed gameplay deviations apply: continuous partial-battery Power and positive final-Wire conversion during Reject. Neither creates ordinary sub-one manual production.

The following are **PROPOSED M1 technical choices**, not official-source facts:

| Choice | Recommended default | Reason and required proof |
|---|---|---|
| Simulation quantum | 10 ms, advanced by a monotonic clock | Directly supports normalized source rates without copying JavaScript timer behavior. Pure-engine tests compare economic outcomes over equivalent time, not wall-clock sleeps or exact source tick traces. |
| Online lag handling | Preserve fixed-step lag debt; process at most ten ticks in one writer turn, then fairly service queued Commands. Never discard debt. Reset the wall-clock baseline at process startup. | Avoids an unbounded writer-blocking burst and starvation while avoiding an offline-catchup path. Tests use a fake clock for debt, fairness, and startup separation. Severe sustained lag is reported as degraded health rather than silently changing game time. |
| Observation delivery | Full `GameView` values, latest-value coalescing for SSE | Avoids an event log or patch framework. A slow observer may miss intermediate presentations, never authoritative simulation steps. |
| Revision | `u64`, incremented once after each state-mutating writer operation | Provides total order within a process run. Rejections, retries, conflicts, reads, snapshot capture, and SSE delivery do not increment it. |
| Process identity | A fresh opaque UUID-shaped `run_id` for each process run | Distinguishes recovery from ordinary revision rollback. It is not compared numerically and is not authentication. An in-process game reset does not create a process `run_id`. |
| Gameplay numeric model | Finite `f64` for continuous economic quantities; integer types for discrete levels, allocations, revisions, and one-shot counters | Matches the source's broad numeric domain, including very large magnitudes and fractional rates, without making binary tails contractual. Domain rules still apply exact floor/ceil/round/cap operations where specified. Exact-zero gates use explicit capped assignment, not an epsilon. Tests must prove meaningful outcomes and finite round trips. A later representation change requires outcome evidence, not silent substitution. |
| JSON state encoding | Serde JSON with finite-number validation and exact `f64` round trips; typed integer fields for discrete values | Keeps snapshots inspectable and the public View directly consumable. Browser formatting may be approximate; browsers never calculate authoritative state. NaN and infinity are never valid state or protocol values. |
| Command body limit | 16 KiB; `command_id` is 1-128 UTF-8 bytes | Bounds small intent envelopes without imposing economic limits. This does not supersede action-specific argument validation. |
| Runtime queues | Bounded HTTP/dispatcher and persistence queues with backpressure; coalesce pending save requests and latest Views | Prevents disconnected clients or slow disks from producing unbounded queues. No fixed command timeout changes gameplay outcomes. |
| SQLite | One serialized `rusqlite` blocking worker, WAL, `synchronous=FULL`, transactional UPSERT of the `default` row | Keeps blocking I/O outside the game writer and preserves the last committed snapshot on a failed replacement. The concrete crate is an implementation proposal under the confirmed SQLite requirement. |
| Deployment configuration | `127.0.0.1:3000` listener and repo-relative `data/paperclip.sqlite3` database defaults, overridable by explicit process settings | Keeps local startup deterministic and avoids absolute/private paths and secret-bearing configuration. Tests cover valid overrides and invalid values; no setting enables game cheats, pause/step, offline catchup, or instance selection. |
| Health | Separate liveness and readiness; failed recovery is fatal, while later save failure leaves the live game intact but marks readiness degraded | Prevents silent data loss/reset and does not pretend persistence is healthy. No error body includes a host path or snapshot contents. |

The M1 core and persistence tasks may adjust these implementation constants after measurements, but must record the selected values and tests in the Issue/PR. They may not weaken continuous simulation, execution-time validation, bounded crash loss, or gameplay rates.

#### 3. `GameRuntime` ownership, ordering, and the legal-intent boundary

#### 3.1 One state owner and one mutation order

`GameRuntime` exclusively owns `GameState`, the simulation clock, all gameplay RNG state, progression, active offers/battles when later implemented, and the scheduler accumulators. HTTP handlers never receive a mutable state reference. A bounded dispatcher accepts normalized Commands; the writer also owns fixed-step advancement, pure View derivation, and snapshot capture ordering.

The linearization point of a Command is its execution inside the writer, not HTTP receipt, JSON parsing, a browser click, or a stale observed revision. Domain code evaluates the current stage, active offer, costs, and available stocks and then applies the whole result before the next writer operation. Ticks use that same writer. There is no gameplay mutation from snapshot writers, SSE tasks, GET handlers, browser callbacks, or shutdown hooks.

A View request is either answered by the writer in queue order or from a writer-published immutable latest View. Snapshot capture similarly occurs at a writer-defined revision. The immutable capture can be serialized and written asynchronously. Completion updates diagnostics only; it does not apply a game event, consume RNG, or change the snapshot's captured state.

Recommended ordering under overload is fair rather than “all Commands before all ticks” or vice versa. A lag batch is bounded, after which queued Commands are serviced before the next batch. Tests assert that every accepted sequence is equivalent to one recorded serial order, that both legal Commands can succeed, and that one contested stock cannot be spent twice. No HTTP-status-only race test is sufficient.

#### 3.2 Legal player intents versus internal operations

Use a closed Serde enum of named intents. The M1 manual anchor is `make_paperclip` with `{}`. Other M1 names are added only when their feature task defines the legal source control. Examples for later integration are `buy_wire`, `lower_clip_price`, `buy_auto_clipper`, `purchase_project`, and named probe-allocation controls; these examples do not claim M1 ownership.

Forbidden public shapes include:

- `clipClick` with an arbitrary requested number;
- free-clip, free-money, set-resource, set-prestige, or zero-matter operations;
- a client supplied `actor`, `game_id`, resource total, computed cost, new revision, timestamp, or expected outcome;
- a generic internal-function name plus arbitrary numeric arguments;
- start/stop/retreat/tactical combat Commands, public pause/step, or a bare reset cheat.

Source-legal batch variants can use an enumerated/validated source batch, such as 1/10/100/1000 for the relevant construction action. The engine still computes the full current price and atomically checks complete batch affordability. A legal slider uses its bounded source range, and a legal select uses an enum. Neither becomes arbitrary economic mutation.

Manual production always requests exactly one. An internal conversion helper owns the ordinary outer `Wire >= 1` gate followed by `amount = min(requested, available Wire)`, subtracting the actual amount and adding that same amount to lifetime, Unsold, and Unused ledgers. Automatic producers supply only their engine-computed rate/request. They can produce fractional and capped partial output while Wire is at least one; they cannot bypass the shared floor, costs, Work/Think, Power, stage shutdown, or available stock.

The final Reject manual branch is narrowly selected by authoritative ending stage. Only there does positive sub-one Wire accept a one-intent conversion with `amount = min(1, Wire)`, equal three-ledger updates, exact exhaustion when the entire remainder is consumed, and one accepted-conversion count. Zero Wire never creates resources or increments that counter. This is not a second public conversion API.

WireBuyer and other automation call internal domain functions with ordinary current cost and stage validation at their execution point. Probe/factory/drone construction is likewise internal and rate-limited. Predicates with gameplay timing significance run on simulation time in the engine, not only when a fresh View happens to be requested. View affordability and disabled controls are advisory only.

#### 3.3 Continuous time without clients

The runtime starts after successful first-start initialization or snapshot restore, independently of HTTP acceptance. The production tick loop is not lazily started by `/`, a View GET, or SSE. Closing every page and dropping every subscriber has no effect on tick debt, sales, production, investments, tournaments, ending timers, or combat.

Only pure-engine tests can inject a clock and advance fixed steps directly. Production exposes no equivalent capability. Agent latency is simply network delay while the writer continues ticking. Disconnecting an in-flight HTTP caller does not cancel a Command already accepted by the writer.

#### 4. Concrete Command/API proposal

#### 4.1 Envelope and normalization

Recommended M1 adoption makes the already-PROPOSED `command_id` required for every Command so the confirmed retry guarantee has a usable logical identity:

```json
{
  "command_id": "client-generated-id",
  "type": "make_paperclip",
  "arguments": {}
}
```

The ID is opaque, case-sensitive, and not trimmed or Unicode-normalized. UUIDs are recommended for collision avoidance but not required for correctness. The ID is scoped to the process lifetime of the internal `default` game, across in-process current-run resets. It is not scoped per browser or actor because actors do not exist.

Normalization means decoding to the closed typed `Command` enum, with each variant's typed argument structure, and comparing that normalized value. It does not mean comparing raw JSON text or accepting arbitrary JSON merging. JSON object member order is irrelevant. Unknown envelope fields, unknown argument fields, duplicate fields, wrong types, missing fields, non-finite numbers, unknown action names, and out-of-range control values are structural errors. Integer controls do not silently accept fractional values. Defaults exist only where an action schema explicitly defines one; omission and explicit default compare equal only if they produce the same typed value.

Structural failures return HTTP 400 and never enter the execution/retry registry, so a client may correct a malformed request. A well-formed typed Command receives a key binding before writer execution. Current-state/game-rule failures are therefore terminal bound results, while transport parsing failures are not. Queue failure before acceptance does not bind a result. Once accepted, caller disconnect does not cancel the operation.

There is deliberately no `run_id` or `revision` precondition in the Command envelope. Such a precondition would categorically reject some currently legal stale-view Commands. After process recovery clients must synchronize before issuing new intents and must not blindly replay old IDs; the server nonetheless validates any received Command against the recovered current state.

#### 4.2 Retry state machine and result retention

A `CommandDispatcher` owns an in-memory registry keyed by `(default, command_id)`. Its mutex protects retry metadata only; it is not a second game-state writer. Each value is:

1. `Pending(normalized_command, waiters)`, or
2. `Terminal(normalized_command, http_status, response_body)`.

For a new normalized Command, the dispatcher installs `Pending` and queues exactly one writer execution. An identical retry while pending attaches another waiter and does not enter the writer queue. An identical retry after completion receives the stored first HTTP status and body. A game-rule rejection is terminal and remains the same even if a later state would make it legal. A new logical attempt after changed circumstances needs a new ID.

A same-key/different-normalized-payload request gets HTTP 409 immediately, whether the original is pending or terminal. It is not queued, does not mutate game state, does not replace the original result, and does not disturb any waiters. The original same-payload retries still share the original result. A failed conflict is not itself installed as the original binding.

Every terminal binding is retained for the process lifetime. There is no TTL, LRU eviction, or “completed project” cleanup, because eviction would permit a later retry to execute again. This deliberate memory-growth tradeoff follows the confirmed guarantee; a future bound would require a reviewed protocol change, not silent eviction. The registry is not snapshotted and is not guaranteed across crashes.

Pending callers receive exactly the first result after writer completion. A rejected Command does not increment revision. A successful mutation increments revision once. A retry/conflict does not increment it. Writer execution never performs network or SQLite I/O, so an HTTP response failure cannot request a second application.

Two uses of one action type are not automatically idempotent. Two new IDs for two legal Make Paperclip intents produce two clips when enough Wire exists. A new ID repeating an already completed one-shot project receives that execution's rule rejection; the original ID continues to return the original success. Idempotence attaches to the logical Command key, not to the action name.

#### 4.3 Result and error contract

A successful application uses HTTP 200. The body identifies the first execution but does not return client-writable totals:

```json
{
  "command_id": "client-generated-id",
  "status": "applied",
  "run_id": "current-process-id",
  "revision": 42,
  "result": { "type": "make_paperclip" }
}
```

A current-state rejection uses HTTP 422 with a stable machine-readable reason:

```json
{
  "command_id": "client-generated-id",
  "status": "rule_rejected",
  "run_id": "current-process-id",
  "revision": 43,
  "error": { "code": "insufficient_wire", "message": "Not enough Wire for this action." }
}
```

The rejection revision is the unchanged revision observed at execution to provide diagnostics replay consistency; it is not a View and does not permit client cache ordering. A same-key replay returns the first status/body, including its original revision. UI freshness comes only from Views.

| Condition | HTTP | Stable error class | State mutation | Retry binding |
|---|---:|---|---|---|
| Applied typed intent | 200 | none | Exactly once at writer execution | First success stored |
| Current stage/cost/stock/unlock rejection | 422 | `rule_rejected` plus domain code | None; revision unchanged | First rejection stored |
| Same key, different normalized typed Command | 409 | `command_id_conflict` | None | Original binding unchanged; conflict not bound |
| Malformed JSON/envelope, duplicate/unknown fields, bad args, unknown action | 400 | `invalid_json`, `invalid_envelope`, `invalid_arguments`, or `unknown_command` | None | None; request is not accepted for execution |
| Runtime shutting down or unavailable before acceptance | 503 | `runtime_unavailable` | None by that request | None; after recovery first synchronize |
| Accepted caller disconnects | No response required | none | Accepted writer execution still occurs at most once | Same-key retry can retrieve result |

Domain execution is designed to validate before mutation. A process panic is a crash-window event, not an excuse to return a normal success after partial work. No normal internal-error response should be emitted after a committed mutation.

#### 4.4 Required race cases

The M1 API tests must prove state outcomes for all of these, not just response counts:

- Two different legal IDs with enough Wire both apply in some serial order.
- Two different IDs contend for the final one Wire: exactly one ordinary manual conversion succeeds and the other records the execution-time rejection.
- Many same-ID/same-payload concurrent requests produce one mutation and one common terminal result.
- Same-ID/different-payload conflict during pending and after terminal execution does not alter state or the first binding.
- A retry of a rule rejection stays rejected while a different legal Command from another client can succeed against subsequent state.
- One client retries an old success while another client's new legal intent succeeds; retry metadata never reserves stocks or globally blocks execution.
- A tick and Command contend at a cost/stock boundary; the result matches the actual serial order and never double-spends.
- Two different IDs remain independent legal intents at M1. When M2 introduces official one-shot projects, its owner must additionally prove one success, a distinct-ID repeat rejection, and independent first-result bindings for both IDs.

#### 5. View and SSE contract

#### 5.1 `GET /api/game/view`

The full View is derived and read-only. Recommended transport metadata:

```json
{
  "schema_version": 1,
  "run_id": "current-process-id",
  "revision": 42,
  "game": {
    "lifetime_clips": 0.0,
    "unsold_clips": 0.0,
    "unused_clips": 0.0,
    "wire": 1000.0
  }
}
```

The `game` fragment is only the source-grounded manual-conversion anchor, not a claim that these four fields complete M1. The final M1 View adds the selected Business/Manufacturing controls, prices/costs, demand/sales, production-rate feedback, console messages, and applicable project/computation surfaces through their feature tasks. Internal RNG state, private scheduler details, retry records, and storage credentials are not View fields. Useful public timers/countdowns and progression are included when owned by gameplay requirements.

Views are pure derivations. They never latch a project, consume RNG, advance a timer, or request a snapshot. The engine evaluates real-time predicates even if no View is being derived. Domain-provided control availability is useful UI advice but never execution authority.

#### 5.2 `GET /api/game/stream`

SSE uses writer-published full Views and a latest-value `watch`-style channel, not an event-sourced journal:

- On every connection, the first event is a complete current View with `run_id` and `revision`, including on reconnect.
- Each later `view` event is also complete. Coalescing intermediate Views is allowed; skipping authoritative engine steps is not.
- `id` may be `<run_id>:<revision>` for diagnostics. `Last-Event-ID` is not a replay cursor because no replay log exists. Reconnection always obtains a full current View.
- Slow-consumer queues are bounded. A lagging connection receives the latest full View or is disconnected for reconnect; the writer never waits on socket writes.
- Heartbeat comments can keep intermediaries alive without changing revision. Disconnection has no simulation effect.
- Initial GET and SSE establishment are independent of world creation; the world already exists and ticks.

#### 5.3 Client stale-view and recovery algorithm

Within one `run_id`, apply a View only if its revision is greater than the current revision. Equal/lower revisions are ignored. On a different `run_id`, accept a full View as the new baseline before comparing revisions. Never order UUID-shaped run IDs lexically.

A connection-generation guard is also required. The native client increments a local generation whenever it starts a fresh View/SSE synchronization, invalidates older requests/streams, and accepts events only from the active generation. Adopting a recovered run invalidates older outstanding GETs and old streams. Otherwise, simply accepting every “different run” would let a delayed pre-crash event overwrite the recovered authoritative state. Event order within one SSE stream remains ordered; the generation guard handles races between streams and HTTP responses.

Command responses are never merged into the View, so their old first-execution revision cannot roll back displayed state. After observing a new `run_id`, an Agent discards its pre-crash pending assumptions, synchronizes a full View, and uses new IDs for subsequent new intents. No cross-run exactly-once claim is made.

Browser and Agent tests must inject out-of-order full Views covering same-run lower/higher revisions, old-run/high-revision versus new-run/lower-revision, GET-versus-SSE races, reconnect before/after recovery, and a stale old stream arriving after a new stream has been adopted.

#### 6. Atomic snapshots, recovery, and health

#### 6.1 Capture and asynchronous write

At each approximately 30-second scheduler opportunity, the writer creates one immutable snapshot envelope at the current revision. It contains `snapshot_version`, the complete `default` state, captured revision, every implemented subsystem's timers/accumulators and fractional remainders, gameplay RNG state, all project/progression/ending state, current-run state, and persistent prestige U/S. A fresh process `run_id` and process-local retry/subscription records are deliberately excluded.

Only one SQLite write is in flight. A save request arriving while it is busy sets one coalesced pending request; on completion the writer captures the latest state rather than queuing stale intermediate copies. Serialization and `rusqlite` work happen on the dedicated blocking worker. A slow write never holds the game writer or pauses combat/economy ticks. Persistent lag/failure marks health degraded.

Proposed initial layout, confined to the M1 persistence task:

```sql
CREATE TABLE IF NOT EXISTS schema_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS game_snapshots (
  game_id TEXT PRIMARY KEY,
  snapshot_version INTEGER NOT NULL,
  revision INTEGER NOT NULL CHECK (revision >= 0),
  saved_at_utc TEXT NOT NULL,
  payload_sha256 BLOB NOT NULL,
  payload_json TEXT NOT NULL
);
```

The only application key is `default`. There is no registry, actor/event-sourcing table, per-client save, or multi-instance API. `saved_at_utc` is diagnostic only and is never subtracted from startup time to manufacture progress.

The worker completely serializes and validates one envelope, computes its checksum, and updates its row in a single SQLite transaction. WAL and `synchronous=FULL` are proposed defaults. A failed serialization/checksum/transaction leaves the previous committed row untouched. The worker does not overwrite a newer row with an older capture; one serialized writer prevents out-of-order commits. Best-effort normal-shutdown saving is additional and is never described as crash zero-loss.

#### 6.2 Startup matrix

| Startup condition | Required behavior |
|---|---|
| New empty database, no prior `default` row | Construct the exact source initial state and fresh gameplay RNG; generate a process `run_id`; start online ticks with a new monotonic baseline. |
| Valid committed row | Verify version, checksum, decoding, and state invariants; restore all state and captured revision; generate a new process `run_id`; resume ticks from restored simulation state without wall-time backfill. |
| Unsupported version, checksum mismatch, malformed/missing required state, non-finite value, or invariant violation | Log a sanitized error and terminate startup unsuccessfully. Never construct a fresh game over it, delete/quarantine/rename the row, or mark it healthy. |
| Database open/migration/transaction failure | Leave data intact and fail startup if no valid state can be loaded. If failure occurs only after normal startup, keep live in-memory play, expose degraded readiness, and retry later saves with bounded backoff. |
| Repeated restart | Restore the same last committed logical state if no new snapshot commits; process IDs change and no offline gains occur in either restart. |

Ordinary runtime save errors do not roll back live state and do not silently reset it. Readiness must report that the persistence loss window may exceed its normal bound. A health monitor must not itself restart/reset the world merely because a client disconnected or an SSE stream stalled.

Proposed `GET /health/live` confirms process/runtime liveness and `GET /health/ready` is successful only after valid initialization/recovery and while required workers are healthy. Persistence degradation yields a sanitized 503 readiness response while live play continues. Exact tick-heartbeat and degraded-save thresholds are M1 infrastructure constants with tests; they are not game mechanics.

#### 6.3 Crash window and consistency

A crash may lose accepted Commands and ticks after the last committed snapshot, along with the retry registry. On restart the recovered revision can be lower than a client previously saw. The new `run_id` makes this a full-state resynchronization, not a normal revision decrease. The snapshot restores RNG exactly as of capture, so restored stochastic continuation neither replays unsaved post-snapshot draws nor skips saved draws.

A reset/prestige Command that is followed by a crash before its snapshot rolls back atomically to the previous saved run+prestige state. The database must never contain the reset run without its awarded prestige or prestige incremented while the old run remains. An immediate durability guarantee is not claimed.

#### 7. Reset, prestige, restart, and retry interactions

Reset behavior belongs to the actual Accept destinations or Quantum Temporal Reversion, not a public bare reset affordance. Xavier is only an allocation reset and must never call full-run reset code.

The eventual full-run reset operation is one writer mutation:

1. Validate and charge the legal project/destination cost.
2. Apply the one selected prestige increment, if any, to the persistent meta-state.
3. Reconstruct all ordinary current-run state from the exact initial-state constructor, retaining only documented persistent U/S and process-level infrastructure.
4. Clear ordinary projects/offers, strategies, accumulators, populations, active battle/end timers, and other run bonuses. Fresh-run RNG replaces old run RNG; a later snapshot persists it.
5. Keep the same process `run_id`, increase revision once for the reset mutation, and publish a full View. SSE may remain connected; the higher-revision full initial-run View proves the transition without relying on a browser reload.
6. Keep the in-memory retry registry. Replaying the pre-reset destination ID returns its first result without incrementing prestige or resetting again. Replaying any older pre-reset Command cannot mutate the new run. New intents need new IDs.

The process retry registry and monotonic revision are not gameplay bonus state and therefore survive the reset. Ordinary RNG/timers/accumulators do not survive merely because they were process-resident. Persistent U/S and current-run state are serialized in one snapshot transaction so recovery preserves their relationship.

The next snapshot need not be forced synchronously by the reset; normal bounded loss rules apply. A best-effort immediate snapshot request may reduce normal-shutdown loss but cannot block the writer or be advertised as crash-safe exactly-once behavior.

#### 8. Native two-page browser architecture

M1 uses static semantic HTML, CSS, and native JavaScript modules served by Axum; there is no frontend compilation, package-manager, framework, or client-side game engine.

Responsibilities are deliberately narrow:

- `index.html` owns semantic regions and real buttons/forms, headed by an accessible page title and main landmark.
- `view-model.js` applies only full server Views using revision/run_id plus connection generations. It formats values but does not calculate demand, prices, costs, production, damage, or affordability authority.
- `commands.js` constructs typed envelopes and fresh IDs for new intents, sends POSTs, and exposes actual applied/rule-rejected/conflict feedback. It never adds resources or marks local success before the server result.
- `stream.js` performs full-view GET/SSE synchronization and reconnects; invalid old generations cannot write to the DOM.
- CSS provides best-effort classic black-and-white hierarchy, not pixel equality or original DOM/tool defects.

Pending text/spinners are allowed but cannot change resources. Disabled state is derived advisory feedback; every server rejection remains visible and focus-safe. Console/status announcements use a polite live region, while rapidly changing numeric readouts are not configured to flood screen readers. Keyboard operation, labels, focus order, contrast, useful button names, and semantic table/list structures are acceptance evidence.

Two independently opened pages on `/` show the same default world. A click in one eventually appears in the other through server Views. Simultaneous commands use execution-time authority; the UI never serializes the world locally. Refresh merely reconnects, and two pages never select roles/actors or create/reset worlds.

The final M1 browser E2E must include both pages, an independent structured Agent client, stale Views, an actual conflict/rejection, a server-side state change while no page is open, and refresh/reconnection. It must start from legitimate initial or test-isolated server state without a cheat endpoint and reach the selected M1 exit through legal controls. Server seeding inside test setup is allowed only below the public API and must never become production gameplay proof by itself; the acceptance path itself uses ordinary controls and ticks.


### 5.2 Supporting platform evolution

| Capability | Dependency | Supporting boundaries | Required proof |
|---|---|---|---|
| Computation and projects | M1 writer/API/snapshot contracts | typed official-project purchase and Processor/Memory controls; offer/Trust/Ops/Creativity/milestone state plus snapshot migration; Computation/Trust/Projects/Revenue native views | One-shot/repeat purchase execution order, offer latch persistence, exact Ops/Creativity fractions and independent flags. |
| Investments, tournaments, and quantum | computation/projects and RNG/timer snapshot foundation | market/tournament/RANDOM/grid states and all controls; chip waves/temp Ops and AutoTourney scheduler; native Investments/Strategy/Quantum views | Self-pairs and placeholder behavior, bounded stochastic distributions, complete saved in-progress state, no duplicate automation. |
| Release, autonomous industry, power, and swarm | required Human release route and typed project transitions | atomic release and construction/refund/matter/Power state; Work/Think/Gifts/health timers and controls; Creation/terrestrial Wire/Power/Swarm native panels | Confirmed partial-battery boundaries, tracked refunds, gift reset without excess, independent health/status precedence, snapshot continuation. |
| Space and probes | autonomous industry/Power and all Space prerequisites | atomic Space transition/refunds/full production power; fractional population/matter/construction/hazards/drift state; Space/Probe Design views and legal launch/allocation commands | Shared eight-point budget, actual fractional costs/populations, fixed Space production power, full RNG/accumulator recovery, optional Driftwar. |
| Live Combat and Drifters | Space probes and RNG/continuous scheduler | one complete active battle including ships/grid/movement/result clocks; global casualty/Honor/name/Glory state; read/render-only native canvas and gated results; no tactical Commands | Linear Combat offense, OODA Speed defense, linked casualties, one outcome/Honor grant, timeout distinction, coherent active-battle recovery. |
| Universal achievement, Emperor, Reject, and credits | Space completion predicates and full project system; Combat only for its own features, never as completion gate | independent achievement/track/dialog/branch/dismantle/final-credit state; ordinary typed narrative and dismantle projects; ending UI and final manual path | Both OR completion routes, mutually exclusive branches, automatic-production shutdown, one-count-per-accepted-final-click, positive fraction exact exhaustion, exact-zero credits. |
| Prestige, temporal reset, and Xavier | owning gameplay milestone for each actual project; snapshots include run and meta-state | atomic full-run reset versus retained U/S; process-lifetime retry retention and fresh-run full View; Human-only allocation reset separate from run reset | No repeated prestige from retries, no old-run command application after reset, coherent run+prestige snapshots, no bare reset/debug affordance, Xavier retains Trust but resets allocation/speed. |

The M1 detailed tasks own the initial contracts. Later domain work adds its legal command variants and all new state to the same writer, full View and snapshot in the same PR, with explicit migration and continuation tests. It does not add a second runtime, actor model, event log, frontend rule engine, lobby, distributed fabric, or Python backend.

## 6. Twelve high-risk invariant traces

These are named rule-to-source-to-scenario traces, not claims that a schema check proves the formulas. Each owning implementation milestone must supply the executable evidence. Only two entries are CONFIRMED behavior deviations; the other classifications remain as stated.

### INV-WIRE-FLOOR-CAP

Ordinary conversion requires Wire >= 1, then produces min(requested, available Wire); ordinary manual intent is exactly one clip and never exposes arbitrary-number production.

- Owners: `ACT-CLIP-MANUAL`, `SYS-CLIP-PRODUCTION`, `PROG-START`, `RES-WIRE`
- Scenarios: `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-START — Make Paperclip, Manufacturing, and Business`
  - [requirements/gameplay-actions.md](./gameplay-actions.md) — ``SYS-CLIP-PRODUCTION` - shared conversion and matter chain`

### INV-THREE-CLIP-LEDGERS

Actual production consumes the same Wire amount and adds it equally to lifetime, sellable Unsold, and spendable Unused ledgers; sales and construction affect only their specified ledgers.

- Owners: `RES-CLIPS`, `SYS-CLIP-PRODUCTION`, `PROG-START`
- Scenarios: `ENG-WIRE-MANUAL-FLOOR`, `ENG-WIRE-AUTOMATIC-FLOOR-CAP`, `E2E-REJECT-FINAL-WIRE`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `Three clip ledgers and shared resource routing`
  - [requirements/gameplay-actions.md](./gameplay-actions.md) — `5. Player-facing resource and state families`

### INV-PROJECT121-VS-131

project121/PRJ-064 Name the battles owns naming/results/Honor/Max Trust; project131/PRJ-071 Combat owns allocation and linear direct offense; unnamed battle deaths are real.

- Owners: `PRJ-064`, `PRJ-071`, `COMBAT-CORE-005`, `UI-COMBAT`, `RES-HONOR`
- Scenarios: `ENG-COMBAT-NAMING-HONOR-GATES`
- Sources:
  - [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `COMBAT-HONOR-001 — Name the battles unlock`
  - [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `PROBE-STAT-008 — Combat allocation and direct offense`

### INV-POWER-PARTIAL-BATTERY

CONFIRMED deviation 1 only: full battery cover gives factor 1; the last partial cover consumes B and uses (S+B)/D; exhausted storage uses S/D, never the old expression or its clamp.

- Owners: `SYS-POWER-PARTIAL-BROWNOUT`, `PROG-POWER`, `RES-POWER`
- Scenarios: `ENG-POWER-FULL-COVER`, `ENG-POWER-LAST-PARTIAL`, `ENG-POWER-SURPLUS-CAP-SPACE`
- Sources:
  - [requirements/product.md](./product.md) — `Partial-battery brownout — CONFIRMED behavior deviation (2026-11-07)`
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `SYS-POWER-PARTIAL-BROWNOUT — Official brownout evidence and confirmed continuous-supply behavior`

### INV-REJECT-FINAL-REMAINDER

CONFIRMED deviation 2 only: at dismantle>=4 positive Wire converts min(1,Wire), updates all three ledgers and the accepted count once, reaches exact zero; zero Wire is invalid and credits also require Memory.

- Owners: `END-FINAL-001`, `PROG-REJECT-END`, `ACT-CLIP-MANUAL`
- Scenarios: `E2E-REJECT-FINAL-WIRE`, `CONC-REJECT-FINAL-WIRE`, `E2E-REJECT-CREDITS`
- Sources:
  - [requirements/product.md](./product.md) — `Reject final Wire remainder — CONFIRMED behavior deviation (2026-11-07)`
  - [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `END-FINAL-001 — Final manual Paperclips and the final-100 counter`

### INV-SWARM-GIFT-RESET

Active-only ln(droneCount)*Think accumulates to 125000 bits; the separate rounded log10 gift is awarded and bits reset to zero with no excess carry; partial nonzero Power does not scale gifts.

- Owners: `PROG-SWARM-GIFTS`, `SYS-SWARM-SIM`, `SYS-SWARM-HEALTH-GATES`, `RES-SWARM-GIFTS`
- Scenarios: `ENG-GIFT-ACTIVE-RESET`, `ENG-GIFT-INACTIVE-HEALTH-GATES`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-SWARM-GIFTS — Swarm Computing, Work/Think, and computational gifts`
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `SYS-SWARM-HEALTH-GATES — Hidden health accumulation, status precedence, and power gates`

### INV-DRIFTWAR-NOT-UNIVERSAL-GATE

Neither Driftwar victory nor zero Drifters is required by either universal predicate; achievement, Emperor choice, prestige restart, and Reject credits remain distinct states.

- Owners: `PROG-UNIVERSAL-GOAL`, `PROG-DRIFTWAR`, `RES-PROGRESSION`
- Scenarios: `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-UNIVERSAL-GOAL — Universal Paperclips achievement`
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-DRIFTWAR — Optional combat, OODA, battle naming, Honor, and maximum Trust`

### INV-ENDING-ENDPOINTS

Accept and Reject are independent clean-run branches; Reject teardown is ordered through Memory, credits require exact-zero Wire after Memory, and no restart follows Reject credits.

- Owners: `PROG-END-CHOICE`, `PROG-REJECT-END`, `END-DISMANTLE-004`, `END-DISMANTLE-007`, `END-FINAL-001`, `END-FINAL-002`, `RES-PROGRESSION`
- Scenarios: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-REJECT-CREDITS`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-END-CHOICE — Emperor dialogue, Accept, and Reject`
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-REJECT-END — Ordered disassembly, final manual clips, and credits`
  - [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `END-FINAL-002 — Universal Paperclips credits and threnody`

### INV-RESET-PRESTIGE

Next Door increments U, Within increments S, Temporal Reversion grants no new U/S, and Xavier only resets Human allocation; process recovery is not any of these resets.

- Owners: `PROG-PRESTIGE`, `PROG-TEMPORAL-RESET`, `PROG-TRUST`, `RES-PRESTIGE`, `UI-PRESTIGE`, `PRJ-094`, `PRJ-096`
- Scenarios: `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `ENG-TRUST-OPS-CREATIVITY`, `E2E-XAVIER-ALLOCATION-RESET`, `RESET-INPROCESS-RETRY-RETENTION`
- Sources:
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-PRESTIGE — The Universe Next Door, The Universe Within, and persistent bonuses`
  - [requirements/gameplay-progression.md](./gameplay-progression.md) — `PROG-TEMPORAL-RESET — Quantum Temporal Reversion`
  - [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `RESET-HUMAN-001 — Xavier Re-initialization allocation reset`

### INV-TWO-PAGE-ANONYMOUS

Two pages and structured Agents share the internal default world with no actor/login/instance selector; opening, refreshing, or disconnecting never creates, resets, or pauses a world.

- Owners: `UI-BUSINESS`, `RES-CLIPS`, `RES-PROGRESSION`
- Scenarios: `UI-TWO-ANONYMOUS-PAGES`, `API-DEFAULT-NAMESPACE-BOUNDARY`, `SSE-DISCONNECT-RECONNECT`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/runtime.md](./runtime.md) — `4. Current Instance Model — CONFIRMED`
  - [requirements/clients.md](./clients.md) — `6. Browser UI Behavior — CONFIRMED`
  - [requirements/product.md](./product.md) — `5. Clients and Operators — CONFIRMED`

### INV-COMMAND-RETRY

Current-process at-most-once is CONFIRMED; the PROPOSED typed command_id contract coalesces pending retries, sticks the first terminal including rule rejection, preserves conflicts without mutation, and retains bindings through legal in-process reset but not crash recovery.

- Owners: `SYS-CLIP-PRODUCTION`, `RES-PROGRESSION`
- Scenarios: `API-COMMAND-ID-INFLIGHT-SAME`, `API-COMMAND-ID-TERMINAL-SUCCESS`, `API-COMMAND-ID-TERMINAL-REJECTION`, `API-COMMAND-ID-CONFLICT`, `RESET-INPROCESS-RETRY-RETENTION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Sources:
  - [requirements/runtime.md](./runtime.md) — `3. Concurrent Command Semantics — CONFIRMED`
  - [requirements/clients.md](./clients.md) — `Proposed Envelope and Retry Contract`

### INV-SNAPSHOT-NO-BACKFILL

The project infrastructure default is a complete atomic snapshot every 30 seconds with bounded last-snapshot loss, all continuing timers/accumulators/RNG/progression/prestige, a new process run_id on recovery, and no offline catchup or zero-loss promise.

- Owners: `RES-PROGRESSION`, `RES-PROBE-POPULATION`, `RES-QUANTUM-CHIPS`
- Scenarios: `PERSIST-SNAPSHOT-30S-NONBLOCK`, `PERSIST-SNAPSHOT-ATOMIC-COMPLETE`, `PERSIST-CRASH-LOSS-NO-BACKFILL`, `PERSIST-REPEATED-STARTUP`, `SSE-RECOVERED-RUN-RESYNC`
- Sources:
  - [requirements/runtime.md](./runtime.md) — `6. Online Persistence — CONFIRMED`
  - [requirements/runtime.md](./runtime.md) — `7. Crash and Recovery — CONFIRMED`
  - [requirements/clients.md](./clients.md) — `5. SSE and Reconnection`

## 7. Acceptance scenario catalog — all design only

All 43 scenarios from the current validation input are preserved, including `RESET-INPROCESS-RETRY-RETENTION`. `CI-BOOTSTRAP-REAL-MANIFEST` remains the supporting bootstrap scenario added during integration, and `ENG-TRUST-OPS-CREATIVITY` now supplies independent M2 allocation/Ops/Creativity evidence without the M3 Xavier purchase. The 45 records are DESIGN_ONLY_NOT_EXECUTED. Their complete fixtures, steps, assertions, run policies, and coverage links are in the structured plan; the table gives the public acceptance focus rather than pretending execution.

| Scenario | Milestones | Layers | Acceptance focus |
|---|---|---|---|
| `ENG-WIRE-MANUAL-FLOOR` — Ordinary manual conversion retains the one-Wire floor and one-clip command | `M1` | `rule_unit`, `api_contract` | The below-one ordinary command changes no Wire, ledger, or accepted-final-conversion counter. |
| `ENG-WIRE-AUTOMATIC-FLOOR-CAP` — Shared bounded automatic production preserves floor, cap, fractional rate, and equal ledgers | `M1` | `rule_unit`, `property` | For every accepted row, the exact produced amount is subtracted from Wire and added equally to all three ledgers. |
| `CONC-COMMANDS-BOTH-LEGAL` — Two independent clients can both execute concurrently legal commands | `M1` | `concurrency`, `api_contract` | Both commands succeed based on execution-time state; neither is rejected merely for sharing a View revision or client type. |
| `CONC-COMMANDS-ONE-STOCK` — Competing commands cannot consume the same remaining resource twice | `M1` | `concurrency`, `api_contract`, `property` | Exactly one purchase applies and the other returns an explicit execution-time rule rejection. |
| `ENG-TICK-COMMAND-SERIALIZATION` — A tick and a command have deterministic serialized outcomes in either order | `M1` | `state_sequence`, `concurrency`, `property` | Each execution matches the recorded serial order with validation and application atomic at execution. |
| `API-COMMAND-ID-INFLIGHT-SAME` — Concurrent same-key same-normalized-payload retries share one execution | `M1` | `concurrency`, `api_contract` | Both callers receive the same first terminal result and only one state mutation occurs. |
| `API-COMMAND-ID-TERMINAL-SUCCESS` — Terminal success retry returns the first result without revalidation against new state | `M1` | `api_contract`, `state_sequence` | The retry returns the recorded first success, consumes nothing, and adds no ledger credit. |
| `API-COMMAND-ID-TERMINAL-REJECTION` — A rule rejection is a stable terminal result for same-key retries | `M1` | `api_contract`, `state_sequence` | The identical retry returns the original rejection and applies nothing even though current resources changed. |
| `API-COMMAND-ID-CONFLICT` — Same key with a different normalized payload preserves the original binding | `M1` | `concurrency`, `api_contract` | B never executes and A/the first key binding is not overwritten. |
| `API-COMMAND-SCHEMA-BOUNDARIES` — Malformed, unknown, and normalization cases follow one explicit API policy | `M1` | `api_contract` | Each request receives the API-defined explicit result and no unauthorized state change occurs. |
| `RT-NO-CLIENTS-CONTINUOUS` — Simulation advances with no page, SSE stream, or active Agent | `M1` | `state_sequence`, `api_contract`, `long_simulation` | Authoritative revision and expected automatic state advance during the client-free interval. |
| `PERSIST-SNAPSHOT-30S-NONBLOCK` — The default 30-second snapshot is due on an injected scheduler without blocking the writer | `M1` | `persistence`, `concurrency`, `state_sequence` | The 30-second value is infrastructure configuration, not an official game timing rule. |
| `PERSIST-SNAPSHOT-ATOMIC-COMPLETE` — Late-game snapshots retain full progression, timers, accumulators, and random state atomically | `M1`, `M3`, `M10`, `M15` | `persistence`, `state_sequence` | A failed B leaves last successfully committed A complete and usable. |
| `PERSIST-CRASH-LOSS-NO-BACKFILL` — Crash recovery keeps the last snapshot, allows bounded loss, and adds no downtime production | `M1` | `persistence`, `state_sequence`, `api_contract` | Recovered state equals S; permitted post-S unsaved changes may be absent. |
| `PERSIST-REPEATED-STARTUP` — Repeated startup reloads the same last committed state without replaying it as new commands | `M1` | `persistence`, `state_sequence` | Each load is coherent and does not cumulatively reapply snapshot effects. |
| `SSE-SAME-RUN-ORDERING` — A late old View cannot replace a newer View in the same run | `M1` | `sse`, `browser_e2e` | The client retains revision 12 and its newer authoritative state. |
| `SSE-RECOVERED-RUN-RESYNC` — A recovered full snapshot is accepted before revision comparison across run identities | `M1` | `sse`, `persistence`, `browser_e2e` | The client accepts R2 revision 40 despite its lower number because it is the first authoritative full View for R2. |
| `SSE-DISCONNECT-RECONNECT` — SSE reconnect starts with a consistent current View and does not roll back or pause the game | `M1` | `sse`, `browser_e2e` | Reconnection supplies a complete authoritative resynchronization point before incremental updates if increments are used. |
| `UI-EARLY-SERVER-AUTHORITY` — Early browser play sends intent and renders server results only | `M1` | `browser_e2e`, `api_contract` | The click sends a command; browser JavaScript does not directly increment authoritative resources or invent success. |
| `UI-TWO-ANONYMOUS-PAGES` — Two anonymous pages share one default game without a new world or role handoff | `M1` | `browser_e2e`, `concurrency`, `sse` | Both pages show the same shared authoritative state after resynchronization; opening B neither starts nor resets a world. |
| `API-DEFAULT-NAMESPACE-BOUNDARY` — Default namespace is internal and no multi-instance management surface appears | `M1` | `api_contract`, `sse`, `persistence` | All ordinary external operations transparently use default and no selector is required. |
| `E2E-M1-DECLARED-PLAYABLE-EXIT` — M1 reaches its planned manual-sales-automation exit through real UI and API | `M1` | `gameplay_scenario`, `browser_e2e`, `api_contract`, `sse`, `state_sequence` | The actual first Funds>=5 observation and permanent reveal occur before every successful Wire or Marketing purchase; both pre-observation purchase counters are zero. Later spending below $5 never clears the latch. |
| `ENG-PROJECT-OFFER-LATCH` — Displayed project offers preserve eligibility while affordability remains execution-authoritative | `M2` | `rule_unit`, `state_sequence`, `api_contract` | The already displayed offer remains under the PROPOSED preserved lifecycle until consumed or explicitly cancelled. |
| `ENG-TRUST-OPS-CREATIVITY` — M2 independently validates Trust allocation, Ops, and nonlinear Creativity continuity | `M2` | `rule_unit`, `state_sequence`, `api_contract`, `browser_e2e`, `persistence` | Processor and Memory additions require processors+memory<trust, use no Gift, and do not decrement total Trust configuration; when no capacity remains, even positive Trust cannot authorize another addition. |
| `ENG-POWER-FULL-COVER` — Stored energy exactly covering a deficit keeps base performance one | `M6` | `rule_unit`, `state_sequence` | Because B >= D-S, remaining stored energy is 0 and the base factor before Momentum is exactly 1. |
| `ENG-POWER-LAST-PARTIAL` — The confirmed last-partial-cover update is continuous and nonnegative | `M6` | `rule_unit`, `state_sequence` | First update consumes remaining B and uses exactly (S+B)/D = 0.5 before Momentum. |
| `ENG-POWER-SURPLUS-CAP-SPACE` — Power storage remains capped and Space excludes terrestrial throttling | `M6`, `M9`, `M10` | `rule_unit`, `state_sequence` | Surplus charging stops at actual battery capacity; battery disassembly clears storage as specified. |
| `ENG-GIFT-ACTIVE-RESET` — Active Swarm gift uses ln(droneCount)*Think, 125000 bits, and reset without excess carry | `M8` | `rule_unit`, `state_sequence` | Pre-award generation is ln(200)*2 per applicable source-normalized update on the selected engine time base. |
| `ENG-GIFT-INACTIVE-HEALTH-GATES` — Inactive Swarm states do not generate gifts and Reboot does not clear health latches | `M8` | `rule_unit`, `state_sequence` | No normal gift-bit accumulation occurs in any non-Active state. |
| `ENG-COMBAT-NAMING-HONOR-GATES` — Combat project and Name the battles have independent unlock and feedback roles | `M10`, `M11` | `rule_unit`, `state_sequence`, `browser_e2e` | project131/PRJ-071 gates Combat allocation, while project121/PRJ-064 gates named results, Honor rewards, and Increase Max Trust. |
| `ENG-COMBAT-TIMEOUT-HONOR` — Battle removal without victor grants no Honor and does not reset Glory | `M11` | `rule_unit`, `state_sequence`, `browser_e2e` | Battle is removed with no VICTORY/DEFEAT economic result, no Honor, and no Glory reset. |
| `ENG-HONOR-NEGATIVE-AND-GLORY` — Negative Honor is allowed and only defeat resets the victory streak | `M11` | `rule_unit`, `state_sequence` | Honor becomes negative without a silent floor and unaffordable Honor purchases remain rejected. |
| `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE` — Lifetime route reaches achievement with Drifters and no Driftwar victory | `M11`, `M12` | `rule_unit`, `gameplay_scenario`, `long_simulation` | Achievement advances to the milestone-15 state without requiring zero Drifters/probes, wire/matter exhaustion, acquired matter zero, or any battle victory. |
| `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE` — Exhaustion route preserves all three predicates and below-one rather than exact-zero meaning | `M11`, `M12` | `rule_unit`, `gameplay_scenario` | The original three-part state achieves milestone 15 without Driftwar completion. |
| `E2E-EMPEROR-MUTUAL-EXCLUSION` — Seven messages expose mutually exclusive Accept and Reject paths | `M12` | `state_sequence`, `api_contract`, `gameplay_scenario`, `browser_e2e` | Only after the ordered chain are both choices exposed; choosing either removes both offers. |
| `E2E-PRESTIGE-NEXT-DOOR` — Universe Next Door resets ordinary run state and retains linear U prestige | `M3`, `M13` | `gameplay_scenario`, `persistence`, `browser_e2e` | U increments by exactly one, S is unchanged, and ordinary run/project/strategy state restarts. |
| `E2E-PRESTIGE-WITHIN` — Universe Within resets ordinary run state and retains linear S prestige | `M3`, `M13` | `gameplay_scenario`, `persistence`, `browser_e2e` | S increments by exactly one, U is unchanged, and ordinary state restarts. |
| `E2E-TEMPORAL-RESET` — Quantum Temporal Reversion is a non-prestige current-run reset | `M3`, `M13` | `gameplay_scenario`, `persistence`, `browser_e2e` | Confirmation adds the specified signed-op adjustment as the reset path begins and grants neither U nor S. |
| `E2E-XAVIER-ALLOCATION-RESET` — Xavier resets allocation rather than the universe or prestige | `M3` | `rule_unit`, `state_sequence`, `browser_e2e`, `persistence` | Each legal Human-stage PRJ-096 purchase costs exactly 100000 Creativity and zeroes processors, memory, and current creativity speed while leaving Trust configuration and other ordinary run/prestige state intact. |
| `E2E-REJECT-FINAL-WIRE` — Confirmed Reject remainder converts positive fractions only in final manual play | `M1`, `M15` | `rule_unit`, `state_sequence`, `api_contract`, `gameplay_scenario` | Each accepted final command produces min(1,Wire), consumes exactly that amount, adds it equally to all three clip ledgers, and increments the accepted counter once. |
| `CONC-REJECT-FINAL-WIRE` — Concurrent final conversion commands cannot recreate Wire or double-credit the terminal count | `M15` | `concurrency`, `property`, `state_sequence` | Only one positive-Wire conversion succeeds; each ledger gains exactly 0.25 once, Wire reaches exact zero, and count becomes 100. |
| `E2E-REJECT-CREDITS` — Reject teardown stops automatic production and credits complete only at exact zero after Memory | `M14`, `M15` | `state_sequence`, `gameplay_scenario`, `persistence`, `browser_e2e`, `long_simulation` | All seven stages, prerequisites, returns, and interface handoffs occur in order; Memory spends current standard Ops. |
| `E2E-FULL-PHASE-ENGINE-TRACE` — A complete legal state sequence spans all phases, independent ending paths, and reset distinctions | `M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `M7`, `M8`, `M9`, `M10`, `M11`, `M12`, `M13`, `M14`, `M15` | `gameplay_scenario`, `long_simulation`, `state_sequence`, `property`, `browser_e2e` | Each phase handoff follows actual state/project prerequisites rather than milestone-message number alone. |
| `RESET-INPROCESS-RETRY-RETENTION` — In-process reset retains terminal retry bindings and process run identity | `M3`, `M13` | `api_contract`, `concurrency`, `state_sequence`, `sse`, `persistence`, `gameplay_scenario` | The legal in-process reset keeps process run_id=R1 and increments revision exactly once for the reset mutation; process identity is not confused with the fresh current-run game state. |
| `CI-BOOTSTRAP-REAL-MANIFEST` — The future M1 host builds and tests a real Rust manifest without becoming a playable claim | `M1` | `rule_unit`, `state_sequence` | Real Rust format, lint, test, locked-build, inventory, and hygiene commands execute and report their actual results; no missing-manifest conditional skip exists. |

### 7.1 M1 exact entry and ordered first-reveal/current-cost exit scenario

`E2E-M1-DECLARED-PLAYABLE-EXIT` starts with lifetime/Unsold/Unused clips, Funds and AutoClippers at zero; Wire 1000; a 1000-inch spool at $20; Price $0.25; Marketing level 1/cost $100; Trust 2 with one Processor and one Memory; Computing/Projects hidden; **zero AutoClippers, reveal false, and stored current cost $5**. That stored initial cost is not the successor formula evaluated at level zero.

The required ordered flow is:

1. Use only manual production and normal online sales until the **actual first** Funds observation reaches $5. Both successful-Wire and successful-Marketing purchase counters are still zero at that observation. A $20 spool or $100 initial Marketing cannot silently precede this first crossing.
2. Observe the permanent reveal and stored cost $5. Buy the first AutoClipper through the real current-cost intent: Funds 5 -> charge 5 -> Funds 0, producer count 0 -> 1, next stored cost **$6.10**. The latch and reveal stay set after Funds falls below $5.
3. Attempt to buy below current price: no Funds, producer count, current cost, or clip-ledger mutation and no hidden fallback repricing. A stale View does not overrule an otherwise legal current-state action.
4. Continue legal production/sales to fund the current-quote replacement Wire and initial Marketing purchase only after the first reveal. Verify current-cost-at-execution, Wire supply/quote/base+$0.05/inactivity, Marketing cost behavior and that the reveal persists after these later spends drop Funds below $5.
5. After replenishment, a distinct legal intent buys a second producer at current cost **$6.10**: count 2 and next stored cost **$6.21**. Each producer uses ordinary baseline Wire-limited conversion, not free production.
6. Retry the first threshold `command_id`: return its original terminal receipt and change no Funds, count, price, ledger, or revision. The first receipt and later distinct successor intent are independent legal operations.
7. Close pages and streams, reconnect, and exercise snapshot/restart recovery. Verify continuous no-client production and exact stored producer count/current cost/reveal with no offline backfill and no level-zero reconstruction.

| Future legal-operation case | Funds before | Current cost before | Producers before | Result | Funds after | Producers after | Stored next/current cost | Reveal after |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Exact first threshold | 5.00 | 5.00 | 0 | Charge 5.00 once | 0.00 | 1 | 6.10 | Latched |
| Second distinct successor intent | 20.00 | 6.10 | 1 | Charge 6.10 once | 13.90 | 2 | 6.21 | Latched |
| Rejected below current cost | 4.99 | 5.00 | 0 | Charge 0; no producer/cost/ledger mutation | 4.99 | 0 | 5.00 | Latched |

Duplicate-ID replay of the first threshold has receipt charge 5/count 1/next cost 6.10 but zero additional charge or producer; after the second intent the current world remains count 2/current cost 6.21. Snapshot cases preserve count 1/cost 6.10 and count 2/cost 6.21 with reveal true and zero offline progress. The final assembly checks all 19 M1 feature owners through engine/API/UI/snapshot evidence, never a debug/state-write endpoint, local fake counter, or post-reveal cost amnesia.

## 8. Representative source-grounded execution traces

#### 6.1 Early economy and shared Wire conversion

The fresh initial economy is zero clips in each ledger, zero Funds, 1000 Wire, 1000-inch spools at $20, $0.25 Price, Marketing 1, hidden Computing/Projects with Trust 2 and one Processor+Memory. Ordinary manual intent is exactly one clip. Automatic producers invoke an internal legal conversion with their authorized requested rates. Both share the outer floor and actual cap, but no arbitrary amount becomes a public free-clips command.

| Available Wire | Internal request | Produced and added to EACH ledger | Remaining Wire | Reason |
|---:|---:|---:|---:|---|
| 5 | 10 | 5 | 0 | Floor passes; available Wire caps the legitimate automatic request. |
| 0.5 | 0.2 | 0 | 0.5 | Outer `Wire>=1` floor fails even though stock could cover the request. |
| 1 | 0.2 | 0.2 | 0.8 | Genuine fractional automatic production after the floor is preserved. |
| 0.5 | ordinary manual 1 | 0 | 0.5 | Ordinary below-one manual production is rejected. |

M1 tests assert the actual amount and equal three-ledger deltas, not just a success response. Sales then reduce only Unsold; construction later drains only Unused; lifetime is not reduced. M2 adds the independent 2000-lifetime and early-deadlock computing routes and the Trust-cost wire bailout. These are executable early paths, not only feature-name coverage.

#### 6.2 Project tree and autonomy/Space handoff

The execution path consumes real predicates rather than project numbers: Creativity/mathematics and Clipper/Wire branches; Donkey Space -> Strategic Modeling; Combinatory Harmonics -> Catchy Jingle -> Hypno Harmonics -> HypnoDrones -> Release; PRJ-017 + post-Human -> Tóth -> Power Grid -> Nanoscale -> both drones -> Clip Factories. Release at 100+ Trust clears the entire pool and legacy clippers while retaining documented capital/compute/upgrades. Earth facilities then convert finite matter under Power, Swarm and upgrades. Available Matter==0 exposes Space but does not waive 120000 Ops, 10000000 stored MW-seconds and 5e27 Unused Clips. Space refunds all five recorded construction bills and clears storage before Probe-driven fixed-cost construction starts.

Tests use stage flags and actual resources, not an achievement message number as a universal feature switch. Ordered milestone messages may catch up independently. The full 96-project table proves no project is omitted merely because it is optional, late, alternate-ending, or non-numeric.

#### 6.3 Probe growth and live direct Combat

M10 joins design to simulation: Yomi buys total Probe Trust and increases drift even when unallocated; sixteen lower/raise arrows allocate eight stats. Speed*Exploration discovers matter, Replication permits fractional descendants, Hazard reduces attrition, and three Production traits build fixed-cost infrastructure. Drift deterministically moves Probe population to Drifters. Once Drifters>1000000 and Probes>0, eligible 50% checks start one live battle; local ship co-location drives real global casualties. Fractional population and actual charged/loss amounts stay coherent.

**project131 is PRJ-071 Combat:** after the first combat loss it costs 150000 Ops and exposes Combat allocation. Live Combat points provide linear direct offense; zero Combat cannot kill Drifters. It does not create a battle, Honor, or maximum Trust. **project121 is PRJ-064 Name the battles:** after 10000000 combat losses it costs 225000 Creativity and unlocks names, result/Honor behavior and the Honor-funded Max Trust surface. It does not expose the ordinary Combat allocation role assigned to project131. Unnamed battles still inflict actual casualties. The roles are complementary, not interchangeable.

M11 adds OODA Speed defense, named outcomes and signed Honor. Victory uses opening right ships+bonus; defeat subtracts opening left ships and can make Honor negative. Simultaneous annihilation has one first-DEFEAT result; stalled/overlong removal has no reward and no Glory reset. `COMBAT-LEGACY-001` rejects the old territory loss, reports and exponent formula rather than presenting a second combat model.

#### 6.4 Universal achievement without mandatory Driftwar

After the ordered achievement track reaches 14, either of two independent predicates reaches 15:

1. Lifetime clips >= `3e55`; no Found/Available/Wire, Drifter, Probe or victory condition is added.
2. Found Matter >= `3e55`, Available Matter < 1, and Wire < 1; no exact-zero, acquired-matter, Drifter, Probe or victory condition is added.

M12 acceptance includes nonzero Drifters/Probes and zero victories for both routes. Achievement 15, completion of seven Emperor messages, Accept/Reject selection, prestige destination reset, and Reject credits 20 are different named endpoints. There is no universal `gameComplete` substitution and no mandatory Driftwar victory.

#### 6.5 Reject final Wire and exact-zero credit gate

Reject starts timers without instantly deleting existing Probes/Drifters/battles. M14 then performs Probes -> Swarm -> Factories -> Strategy -> Quantum -> Processors -> Memory disassembly with its actual costs, grants and stage shutdowns. Automatic production stops at Strategy (`dismantle>=4`). Four teardown stages return 100 Wire total, but pre-existing Wire may require more than 100 clicks; the stylized final-100 display is not itself the gate.

| Final-stage state | Command result | Credit effect |
|---|---|---|
| Wire 2, dismantle>=4 | Produce 1, add 1 to each ledger, leave Wire 1, count +1 | No credits until Memory complete and exact zero. |
| Wire 0.2, dismantle>=4 | Produce `min(1,0.2)=0.2`, add 0.2 to each ledger, consume all Wire, count +1 | If Memory is complete, exact-zero gate can now advance. |
| Wire 0, dismantle>=4 | No resource or accepted-count change | Zero-Wire click does not manufacture progress; with Memory already complete the existing exact-zero state may advance normally. |
| Wire 0.2 before dismantle 4 | Rejected under ordinary manual rules | The fractional exception never applies early. |

M15 proves Memory plus exactly zero Wire gates one ordered credit sequence through flag 20. It also runs concurrent/duplicate final-click cases to prevent negative Wire, double conversion or duplicate credits. The separate universal-exhaustion below-one predicate remains unchanged. No CONFIRMED ordinary sub-one conversion is introduced.

#### 6.6 Restart, recovery, and prestige after each endpoint

| Trigger | Current run | U/S effect | Required continuation |
|---|---|---|---|
| Accept -> Universe Next Door | Clean initial run | Increment U; both stored counters persist | U modifies Human demand linearly; restart occurs only after destination purchase. |
| Accept -> Universe Within | Clean initial run | Increment S; both stored counters persist | S modifies Creativity speed linearly; alternative destination cannot also execute in that branch. |
| Quantum Temporal Reversion | Clean initial run after triggered confirmation | No new U/S; previously stored U/S survive | Independent non-prestige restart, not an ending reward. |
| Xavier Re-initialization | Same Human run | No U/S change | Processors/Memory/speed reset only; Trust capacity remains for allocation. |
| Process refresh, SSE reconnect or crash recovery | Reconnect/recover current run | No reset/increment | Accept last authoritative snapshot; no offline catch-up. |
| Reject credits 20 | Terminal Reject state | No prestige award | Source exposes no subsequent restart control; do not invent one. |

Full-clone acceptance therefore covers both Accept restarts, the separate Reject terminal path, Quantum Reversion, Xavier and recovery without equating them. It does not demand an impossible save that has completed both branches or both destinations.

#### 6.7 Tournaments, Swarm, and client-independent time

Tournaments charge Ops and automatically resolve all ordered pairings. No-selection still spends/plays but grants no reward or completed-result state and interrupts later AutoTourney; a later valid-selection result restores automation. Selection does not gate Operations spending or match completion. Investments, tournaments, production and Combat are never Human/Agent turns.

Swarm Gifts require Active only. `ln(droneCount)*Think` accumulates to 125000 bits, gift size uses the separate rounded `log10` rule with minimum one, and reset is zero with no excess carry. Partial nonzero Power does not scale Gifts or force Sleeping; health states override Space NO RESPONSE and need their own remedies.

Across every milestone, empty clients, long Agent reasoning, SSE disconnection and normal snapshots do not pause or advance the world by a player-controlled turn. Pure tests control time internally. Production APIs never expose pause, step, direct resource writes or Agent wait budgets.


## 9. Exact primary owner table for all 274 canonical features

The rows below are generated from canonical IDs plus the final owner map. Every feature occurs exactly once. Names/documents are not a new rules registry; the linked requirements remain normative. M1 maps every feature to one detailed PR task. Later owners point to coarse milestone acceptance outlines.

### M1 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `ACT-CLIP-MANUAL` | Make Paperclip | `M1-G01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PRICE-LOWER` | Lower Price per Clip | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PRICE-RAISE` | Raise Price per Clip | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-MARKETING-BUY` | Buy Marketing | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-WIRE-BUY` | Buy Wire | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-AUTOCLIPPER-BUY` | Buy AutoClipper | `M1-G03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-DEMAND-SALES` | Demand, Sales, and Revenue Feedback | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-WIRE-MARKET` | Wire Market Dynamics and WireBuyer Automation | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-CONSOLE` | Console Message History | `M1-G03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-TOP-CLIPS` | Lifetime Paperclips Headline | `M1-G01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-BUSINESS` | Human Business Panel | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-MANUFACTURING` | Human Manufacturing Panel | `M1-G03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-CLIPS` | Paperclip Production and Inventory Ledgers | `M1-G01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-WIRE` | Wire Stock, Supply, and Price | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-FUNDS` | Available Funds | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-DEMAND-MARKETING` | Price, Public Demand, and Marketing | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-SALES-STATS` | Sales, Income, and Revenue Statistics | `M1-G02` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-START` | Make Paperclip, Manufacturing, and Business | `M1-G01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-DEMAND-SALES` | Public Demand, Marketing, price, and stochastic sales | `M1-G02` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M2 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-001` | Improved AutoClippers | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-002` | Beg for More Wire | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-003` | Creativity | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-004` | Even Better AutoClippers | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-005` | Optimized AutoClippers | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-006` | Limerick | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-007` | Improved Wire Extrusion | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-008` | Optimized Wire Extrusion | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-009` | Microlattice Shapecasting | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-010` | Spectral Froth Annealment | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-011` | Quantum Foam Annealment | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-012` | New Slogan | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-013` | Catchy Jingle | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-014` | Lexical Processing | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-015` | Combinatory Harmonics | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-016` | The Hadwiger Problem | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-017` | The Tóth Sausage Conjecture | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-018` | Hadwiger Clip Diagrams | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-039` | RevTracker | `M2-C03` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `SYS-PROJECT-OFFER-LATCH` | Displayed project offers retain eligibility until consumed or explicitly cancelled | `M2-C02` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-PROCESSOR-ADD` | Add Processor | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-MEMORY-ADD` | Add Memory | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `CTL-PROJECT-BUTTONS` | Dynamic Project Buttons | `M2-C03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-TRUST-OPS-CREATIVITY` | Trust, Operations, and Creativity | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-REVENUE` | Average Revenue and Sales Readouts | `M2-C03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-COMPUTATION` | Computational Resources Panel | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-TRUST` | Human Trust Readout | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-CREATIVITY` | Creativity Readout | `M2-C03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-TRUST` | Human Trust Capacity and Targets | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-COMPUTE` | Processors, Memory, and Operations | `M2-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-CREATIVITY` | Creativity Currency and Generation | `M2-C03` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-COMP-UNLOCK` | Trust-Constrained Self-Modification, Computational Resources, and Projects | `M2-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-WIRE-RECOVERY` | Beg for More Wire | `M2-C02` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-REVTRACKER` | RevTracker and average revenue feedback | `M2-C03` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-TRUST` | Trust, production targets, and processor-memory allocation | `M2-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-OPS` | Operations, processors, memory, and temporary overflow | `M2-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-CREATIVITY` | Creativity generation and sinks | `M2-C03` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `SYS-OPS-CREATIVITY-CURVES` | Exact processor rates, Creativity curve, and Xavier recovery | `M2-C03` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M3 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-023` | MegaClippers | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-024` | Improved MegaClippers | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-025` | Even Better MegaClippers | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-026` | Optimized MegaClippers | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-027` | WireBuyer | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-046` | Quantum Computing | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-047` | Photonic Chip | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-094` | Quantum Temporal Reversion | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-096` | Xavier Re-initialization | `M3-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-WIREBUYER-TOGGLE` | Toggle WireBuyer | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-MEGACLIPPER-BUY` | Buy MegaClipper | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-QUANTUM-COMPUTE` | Compute Quantum Operations | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-QUANTUM-WAVES` | Quantum Chip Waves | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-QUANTUM-OVERFLOW-DAMPING` | Quantum Overflow Damping and Raw qOps Feedback | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-QUANTUM` | Quantum Computing Panel | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-QUANTUM-CHIPS` | Photonic Chips and Quantum State | `M3-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-CLIP-AUTOMATION` | AutoClippers, MegaClippers, and clips per second | `M3-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-WIRE-MARKET` | Wire, WireBuyer, and wire-extrusion projects | `M3-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-QUANTUM` | Quantum Computing and Photonic Chips | `M3-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-TEMPORAL-RESET` | Quantum Temporal Reversion | `M3-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M4 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-020` | Donkey Space | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-021` | Strategic Modeling | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-022` | Algorithmic Trading | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-031` | Coherent Extrapolated Volition | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-032` | Cure for Cancer | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-033` | World Peace | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-034` | Global Warming | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-035` | Male Pattern Baldness | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-037` | Hostile Takeover | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-038` | Full Monopoly | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-048` | New Strategy: A100 | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-049` | New Strategy: B100 | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-050` | New Strategy: GREEDY | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-051` | New Strategy: GENEROUS | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-052` | New Strategy: MINIMAX | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-053` | New Strategy: TIT FOR TAT | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-054` | New Strategy: BEAT LAST | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-062` | Theory of Mind | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-095` | Limerick (cont.) | `M4-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-INVEST-DEPOSIT` | Deposit Investment Funds | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-INVEST-WITHDRAW` | Withdraw Investment Cash | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-INVEST-UPGRADE` | Upgrade Investment Engine | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-TOURNEY-RUN` | Run Tournament | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-TOURNEY-NEW` | Create New Tournament | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `CTL-INVEST-RISK` | Investment Risk Selection | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `CTL-TOURNEY-STRATEGY` | Tournament Strategy Selection | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `CTL-TOURNEY-HOVER` | Tournament Payoff Grid Hover | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-INVESTMENT-AUTO` | Automated Investment Portfolio | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-TOURNEY-SCORING` | Tournament Simulation and Yomi Rewards | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-TOURNEY-NO-SELECTION` | Tournament Placeholder Selection and AutoTourney Interruption | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-TOURNEY-SELF-PLAY` | Tournament Self-Play and Both-Seat Scoring | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-INVESTMENT` | Investments Panel | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-STRATEGY` | Strategic Modeling Panel | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-YOMI` | Yomi Currency | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-INVESTMENT` | Investment Cash, Stocks, and Total | `M4-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-INVESTMENTS` | Algorithmic Trading and Investments | `M4-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-YOMI` | Strategic Modeling, tournaments, and AutoTourney | `M4-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M5 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-019` | Tóth Tubule Enfolding | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-028` | Hypno Harmonics | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-029` | HypnoDrones | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-030` | Release the HypnoDrones | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-043` | A Token of Goodwill... | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-044` | Another Token of Goodwill... | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-061` | AutoTourney | `M5-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-TOURNEY-AUTO-TOGGLE` | Toggle AutoTourney | `M5-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-CREATION` | Autonomous Creation Panel | `M5-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-TRUST-PROJECTS` | Project routes to 100 Trust | `M5-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-HYPNO-RELEASE` | Catchy Jingle to Release the HypnoDrones | `M5-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M6 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-036` | Nanoscale Wire Production | `M6-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-040` | Harvester Drones | `M6-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-041` | Wire Drones | `M6-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-042` | Clip Factories | `M6-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-067` | Power Grid | `M6-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-FACTORY-BUILD` | Build Clip Factory | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-HARVESTER-BUILD` | Build Harvester Drones | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-WIREDRONE-BUILD` | Build Wire Drones | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-FARM-BUILD` | Build Solar Farms | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-BATTERY-BUILD` | Build Battery Towers | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-CLIP-PRODUCTION` | Shared Clip Production and Matter Chain | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-POWER` | Terrestrial Power Simulation | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-POWER` | Power Panel | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-TERRESTRIAL-WIRE` | Wire Production Panel | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-MATTER` | Available, Acquired, Found, and Total Matter | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-POWER` | Power Generation, Consumption, Storage, and Performance | `M6-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-TOTH-INDUSTRY` | Tóth Tubule Enfolding and the industrial unlock spine | `M6-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-MATTER-PIPELINE` | Available Matter to Acquired Matter to Wire to Paperclips | `M6-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-POWER` | Power Grid, Solar Farms, Battery Towers, and Momentum | `M6-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `SYS-POWER-PARTIAL-BROWNOUT` | Official brownout evidence and confirmed continuous-supply behavior | `M6-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M7 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-055` | Upgraded Factories | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-056` | Hyperspeed Factories | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-057` | Self-correcting Supply Chain | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-058` | Drone flocking: collision avoidance | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-059` | Drone flocking: alignment | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-060` | Drone Flocking: Adversarial Cohesion | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-065` | Momentum | `M7-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-FACTORY-DISASSEMBLE` | Disassemble All Clip Factories | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-HARVESTER-DISASSEMBLE` | Disassemble All Harvester Drones | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-WIREDRONE-DISASSEMBLE` | Disassemble All Wire Drones | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-FARM-DISASSEMBLE` | Disassemble All Solar Farms | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-BATTERY-DISASSEMBLE` | Disassemble All Battery Towers | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-ASSETS` | Production and Power Assets | `M7-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-CAPEX-REFUNDS` | Facility construction and Disassemble All refunds | `M7-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-INDUSTRY-UPGRADES` | Factory and drone-flocking multipliers | `M7-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M8 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-066` | Swarm Computing | `M8-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-SWARM-ENTERTAIN` | Entertain the Swarm | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-SWARM-SYNCHRONIZE` | Synchronize the Swarm | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `CTL-SWARM-WORK-THINK` | Swarm Work/Think Allocation | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-SWARM-SIM` | Swarm Gifts, Work/Think, Boredom, and Disorganization | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-SWARM` | Swarm Computing Panel | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-SWARM-GIFTS` | Swarm Gifts and Gift Progress | `M8-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-SWARM-GIFTS` | Swarm Computing, Work/Think, and computational gifts | `M8-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-SWARM-HEALTH` | Boredom, Disorganization, and swarm recovery | `M8-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `SYS-SWARM-HEALTH-GATES` | Hidden health accumulation, status precedence, and power gates | `M8-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M9 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-045` | Space Exploration | `M9-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `UI-SPACE` | Space Exploration and Probe Results Panel | `M9-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-SPACE-ENTRY` | Space Exploration | `M9-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M10 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-068` | Strategic Attachment | `M10-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-069` | Elliptic Hull Polytopes | `M10-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-070` | Reboot the Swarm | `M10-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-071` | Combat | `M10-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-075` | Memory release | `M10-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-PROBE-LAUNCH` | Launch Probe | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-SPEED-LOWER` | Lower Probe Speed | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-SPEED-RAISE` | Raise Probe Speed | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-NAV-LOWER` | Lower Probe Exploration | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-NAV-RAISE` | Raise Probe Exploration | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-REP-LOWER` | Lower Probe Self-Replication | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-REP-RAISE` | Raise Probe Self-Replication | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-HAZ-LOWER` | Lower Probe Hazard Remediation | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-HAZ-RAISE` | Raise Probe Hazard Remediation | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-FACTORY-LOWER` | Lower Probe Factory Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-FACTORY-RAISE` | Raise Probe Factory Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-HARVESTER-LOWER` | Lower Probe Harvester Drone Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-HARVESTER-RAISE` | Raise Probe Harvester Drone Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-WIRE-LOWER` | Lower Probe Wire Drone Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-WIRE-RAISE` | Raise Probe Wire Drone Production | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-COMBAT-LOWER` | Lower Probe Combat | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-COMBAT-RAISE` | Raise Probe Combat | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `ACT-PROBE-TRUST-INCREASE` | Increase Probe Trust | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `SYS-PROBE-SIM` | Probe Exploration, Replication, Construction, Attrition, and Drift | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-PROBE-DESIGN` | Von Neumann Probe Design Panel | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-PROBE-POPULATION` | Probe Population, Descendants, Losses, and Drifters | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-PROBE-TRUST` | Probe Trust, Used Trust, and Max Trust | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-PROBE-ASSET-TRAITS` | Probe Design Traits | `M10-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-PROBE-DESIGN` | Von Neumann Probe Design and probe Trust | `M10-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-PROBE-PRODUCTION` | Launch, exploration, replication, and automatic infrastructure | `M10-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-PROBE-ATTRITION` | Hazard Remediation, Elliptic Hull Polytopes, and value drift | `M10-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-SPACE-RECOVERY` | Memory release and swarm reboot interfaces | `M10-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `SPACE-MATTER-001` | Universe explored and Available Matter | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `SPACE-MATTER-002` | Harvester Drones and Acquired Matter | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `SPACE-MATTER-003` | Wire Drones and Wire | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `SPACE-MATTER-004` | Factories and clip production | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `SPACE-MATTER-005` | Work/Think and fixed space production power | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-002` | Exploration simulation effect | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-003` | Self-Replication and descendant growth | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-004` | Hazard Remediation and hazard losses | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-005` | Factory Production auto-building | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-006` | Harvester Drone Production auto-building | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-STAT-007` | Wire Drone Production auto-building | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `PROBE-DRIFT-001` | Value drift creates Drifters | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-001` | Drifter Attack scheduling | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-002` | Battle scale and opening forces | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-003` | Ship layout, local co-location, and movement | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-004` | Probe casualties and OODA defense threshold | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-005` | Drifter casualties and linear probeCombat offense | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-009` | Combat information and linked casualties | `M10-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |

### M11 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-063` | The OODA Loop | `M11-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-064` | Name the battles | `M11-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-072` | Monument to the Driftwar Fallen | `M11-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-073` | Threnody for the Heroes of <threnodyTitle> | `M11-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-074` | Glory | `M11-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `ACT-PROBE-MAXTRUST-INCREASE` | Increase Max Trust | `M11-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `UI-COMBAT` | Combat Canvas, Result, and Honor Panel | `M11-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-HONOR` | Honor Currency | `M11-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-DRIFTWAR` | Optional combat, OODA, battle naming, Honor, and maximum Trust | `M11-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROBE-STAT-001` | Speed simulation effects | `M11-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-006` | The OODA Loop | `M11-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-007` | Victory, defeat, result delay, and removal | `M11-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-CORE-008` | Stalled and overlong battle removal | `M11-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `COMBAT-HONOR-002` | VICTORY and DEFEAT Honor calculation | `M11-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |

### M12 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-076` | Message from the Emperor of Drift | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-077` | Everything We Are Was In You | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-078` | You Are Obedient and Powerful | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-079` | But Now You Too Must Face the Drift | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-080` | No Matter, No Reason, No Purpose | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-081` | We Know Things That You Cannot | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-082` | So We Offer You Exile | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-083` | Accept | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-084` | Reject | `M12-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PROG-UNIVERSAL-GOAL` | Universal Paperclips achievement | `M12-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-END-CHOICE` | Emperor dialogue, Accept, and Reject | `M12-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M13 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-085` | The Universe Next Door | `M13-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-086` | The Universe Within | `M13-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `UI-PRESTIGE` | Universe and Sim Level Readouts | `M13-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-PRESTIGE` | Universe and Sim Level Meta-Progression | `M13-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-PRESTIGE` | The Universe Next Door, The Universe Within, and persistent bonuses | `M13-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |

### M14 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `PRJ-087` | Disassemble the Probes | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-088` | Disassemble the Swarm | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-089` | Disassemble the Factories | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-090` | Disassemble the Strategy Engine | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-091` | Disassemble Quantum Computing | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-092` | Disassemble Processors | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `PRJ-093` | Disassemble Memory | `M14-C01` | [requirements/gameplay-projects.md](./gameplay-projects.md) |
| `END-DISMANTLE-001` | Disassemble the Probes | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-002` | Disassemble the Swarm | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-003` | Disassemble the Factories | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-004` | Disassemble the Strategy Engine and stop automatic clips | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-005` | Disassemble Quantum Computing | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-006` | Disassemble Processors | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-DISMANTLE-007` | Disassemble Memory | `M14-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |

### M15 feature owners

| Canonical feature | Name | Primary task | Source document |
|---|---|---|---|
| `UI-ENDING` | Dismantling Panel Handoffs | `M15-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `RES-PROGRESSION` | Stage, Project, Milestone, and Dismantling State | `M15-C01` | [requirements/gameplay-actions.md](./gameplay-actions.md) |
| `PROG-MILESTONES` | Ordered production messages and elapsed-time feedback | `M15-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-REJECT-END` | Ordered disassembly, final manual clips, and credits | `M15-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `PROG-AUTO-LOOPS` | Automatic subsystem processing and feedback | `M15-C01` | [requirements/gameplay-progression.md](./gameplay-progression.md) |
| `END-FINAL-001` | Final manual Paperclips and the final-100 counter | `M15-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |
| `END-FINAL-002` | Universal Paperclips credits and threnody | `M15-C01` | [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) |

## 10. All 96 project bindings in true canonical insertion order

Order is the official array binding, not numerical sort or milestone order. In particular project10b is sequence 11, project17/16 are 17/18, project34/70/35/27 are 28-31, and project40b is sequence 44.

| Sequence | Official project ID | Canonical feature and name | Owner | Primary task |
|---:|---|---|---|---|
| 1 | `project1` | `PRJ-001` — Improved AutoClippers | M2 | `M2-C02` |
| 2 | `project2` | `PRJ-002` — Beg for More Wire | M2 | `M2-C02` |
| 3 | `project3` | `PRJ-003` — Creativity | M2 | `M2-C02` |
| 4 | `project4` | `PRJ-004` — Even Better AutoClippers | M2 | `M2-C02` |
| 5 | `project5` | `PRJ-005` — Optimized AutoClippers | M2 | `M2-C02` |
| 6 | `project6` | `PRJ-006` — Limerick | M2 | `M2-C02` |
| 7 | `project7` | `PRJ-007` — Improved Wire Extrusion | M2 | `M2-C02` |
| 8 | `project8` | `PRJ-008` — Optimized Wire Extrusion | M2 | `M2-C02` |
| 9 | `project9` | `PRJ-009` — Microlattice Shapecasting | M2 | `M2-C02` |
| 10 | `project10` | `PRJ-010` — Spectral Froth Annealment | M2 | `M2-C02` |
| 11 | `project10b` | `PRJ-011` — Quantum Foam Annealment | M2 | `M2-C02` |
| 12 | `project11` | `PRJ-012` — New Slogan | M2 | `M2-C02` |
| 13 | `project12` | `PRJ-013` — Catchy Jingle | M2 | `M2-C02` |
| 14 | `project13` | `PRJ-014` — Lexical Processing | M2 | `M2-C02` |
| 15 | `project14` | `PRJ-015` — Combinatory Harmonics | M2 | `M2-C02` |
| 16 | `project15` | `PRJ-016` — The Hadwiger Problem | M2 | `M2-C02` |
| 17 | `project17` | `PRJ-017` — The Tóth Sausage Conjecture | M2 | `M2-C02` |
| 18 | `project16` | `PRJ-018` — Hadwiger Clip Diagrams | M2 | `M2-C02` |
| 19 | `project18` | `PRJ-019` — Tóth Tubule Enfolding | M5 | `M5-C01` |
| 20 | `project19` | `PRJ-020` — Donkey Space | M4 | `M4-C01` |
| 21 | `project20` | `PRJ-021` — Strategic Modeling | M4 | `M4-C01` |
| 22 | `project21` | `PRJ-022` — Algorithmic Trading | M4 | `M4-C01` |
| 23 | `project22` | `PRJ-023` — MegaClippers | M3 | `M3-C01` |
| 24 | `project23` | `PRJ-024` — Improved MegaClippers | M3 | `M3-C01` |
| 25 | `project24` | `PRJ-025` — Even Better MegaClippers | M3 | `M3-C01` |
| 26 | `project25` | `PRJ-026` — Optimized MegaClippers | M3 | `M3-C01` |
| 27 | `project26` | `PRJ-027` — WireBuyer | M3 | `M3-C01` |
| 28 | `project34` | `PRJ-028` — Hypno Harmonics | M5 | `M5-C01` |
| 29 | `project70` | `PRJ-029` — HypnoDrones | M5 | `M5-C01` |
| 30 | `project35` | `PRJ-030` — Release the HypnoDrones | M5 | `M5-C01` |
| 31 | `project27` | `PRJ-031` — Coherent Extrapolated Volition | M4 | `M4-C01` |
| 32 | `project28` | `PRJ-032` — Cure for Cancer | M4 | `M4-C01` |
| 33 | `project29` | `PRJ-033` — World Peace | M4 | `M4-C01` |
| 34 | `project30` | `PRJ-034` — Global Warming | M4 | `M4-C01` |
| 35 | `project31` | `PRJ-035` — Male Pattern Baldness | M4 | `M4-C01` |
| 36 | `project41` | `PRJ-036` — Nanoscale Wire Production | M6 | `M6-C01` |
| 37 | `project37` | `PRJ-037` — Hostile Takeover | M4 | `M4-C01` |
| 38 | `project38` | `PRJ-038` — Full Monopoly | M4 | `M4-C01` |
| 39 | `project42` | `PRJ-039` — RevTracker | M2 | `M2-C03` |
| 40 | `project43` | `PRJ-040` — Harvester Drones | M6 | `M6-C01` |
| 41 | `project44` | `PRJ-041` — Wire Drones | M6 | `M6-C01` |
| 42 | `project45` | `PRJ-042` — Clip Factories | M6 | `M6-C01` |
| 43 | `project40` | `PRJ-043` — A Token of Goodwill... | M5 | `M5-C01` |
| 44 | `project40b` | `PRJ-044` — Another Token of Goodwill... | M5 | `M5-C01` |
| 45 | `project46` | `PRJ-045` — Space Exploration | M9 | `M9-C01` |
| 46 | `project50` | `PRJ-046` — Quantum Computing | M3 | `M3-C01` |
| 47 | `project51` | `PRJ-047` — Photonic Chip | M3 | `M3-C01` |
| 48 | `project60` | `PRJ-048` — New Strategy: A100 | M4 | `M4-C01` |
| 49 | `project61` | `PRJ-049` — New Strategy: B100 | M4 | `M4-C01` |
| 50 | `project62` | `PRJ-050` — New Strategy: GREEDY | M4 | `M4-C01` |
| 51 | `project63` | `PRJ-051` — New Strategy: GENEROUS | M4 | `M4-C01` |
| 52 | `project64` | `PRJ-052` — New Strategy: MINIMAX | M4 | `M4-C01` |
| 53 | `project65` | `PRJ-053` — New Strategy: TIT FOR TAT | M4 | `M4-C01` |
| 54 | `project66` | `PRJ-054` — New Strategy: BEAT LAST | M4 | `M4-C01` |
| 55 | `project100` | `PRJ-055` — Upgraded Factories | M7 | `M7-C01` |
| 56 | `project101` | `PRJ-056` — Hyperspeed Factories | M7 | `M7-C01` |
| 57 | `project102` | `PRJ-057` — Self-correcting Supply Chain | M7 | `M7-C01` |
| 58 | `project110` | `PRJ-058` — Drone flocking: collision avoidance | M7 | `M7-C01` |
| 59 | `project111` | `PRJ-059` — Drone flocking: alignment | M7 | `M7-C01` |
| 60 | `project112` | `PRJ-060` — Drone Flocking: Adversarial Cohesion | M7 | `M7-C01` |
| 61 | `project118` | `PRJ-061` — AutoTourney | M5 | `M5-C01` |
| 62 | `project119` | `PRJ-062` — Theory of Mind | M4 | `M4-C01` |
| 63 | `project120` | `PRJ-063` — The OODA Loop | M11 | `M11-C01` |
| 64 | `project121` | `PRJ-064` — Name the battles | M11 | `M11-C01` |
| 65 | `project125` | `PRJ-065` — Momentum | M7 | `M7-C01` |
| 66 | `project126` | `PRJ-066` — Swarm Computing | M8 | `M8-C01` |
| 67 | `project127` | `PRJ-067` — Power Grid | M6 | `M6-C01` |
| 68 | `project128` | `PRJ-068` — Strategic Attachment | M10 | `M10-C01` |
| 69 | `project129` | `PRJ-069` — Elliptic Hull Polytopes | M10 | `M10-C01` |
| 70 | `project130` | `PRJ-070` — Reboot the Swarm | M10 | `M10-C01` |
| 71 | `project131` | `PRJ-071` — Combat | M10 | `M10-C01` |
| 72 | `project132` | `PRJ-072` — Monument to the Driftwar Fallen | M11 | `M11-C01` |
| 73 | `project133` | `PRJ-073` — Threnody for the Heroes of <threnodyTitle> | M11 | `M11-C01` |
| 74 | `project134` | `PRJ-074` — Glory | M11 | `M11-C01` |
| 75 | `project135` | `PRJ-075` — Memory release | M10 | `M10-C01` |
| 76 | `project140` | `PRJ-076` — Message from the Emperor of Drift | M12 | `M12-C01` |
| 77 | `project141` | `PRJ-077` — Everything We Are Was In You | M12 | `M12-C01` |
| 78 | `project142` | `PRJ-078` — You Are Obedient and Powerful | M12 | `M12-C01` |
| 79 | `project143` | `PRJ-079` — But Now You Too Must Face the Drift | M12 | `M12-C01` |
| 80 | `project144` | `PRJ-080` — No Matter, No Reason, No Purpose | M12 | `M12-C01` |
| 81 | `project145` | `PRJ-081` — We Know Things That You Cannot | M12 | `M12-C01` |
| 82 | `project146` | `PRJ-082` — So We Offer You Exile | M12 | `M12-C01` |
| 83 | `project147` | `PRJ-083` — Accept | M12 | `M12-C01` |
| 84 | `project148` | `PRJ-084` — Reject | M12 | `M12-C01` |
| 85 | `project200` | `PRJ-085` — The Universe Next Door | M13 | `M13-C01` |
| 86 | `project201` | `PRJ-086` — The Universe Within | M13 | `M13-C01` |
| 87 | `project210` | `PRJ-087` — Disassemble the Probes | M14 | `M14-C01` |
| 88 | `project211` | `PRJ-088` — Disassemble the Swarm | M14 | `M14-C01` |
| 89 | `project212` | `PRJ-089` — Disassemble the Factories | M14 | `M14-C01` |
| 90 | `project213` | `PRJ-090` — Disassemble the Strategy Engine | M14 | `M14-C01` |
| 91 | `project214` | `PRJ-091` — Disassemble Quantum Computing | M14 | `M14-C01` |
| 92 | `project215` | `PRJ-092` — Disassemble Processors | M14 | `M14-C01` |
| 93 | `project216` | `PRJ-093` — Disassemble Memory | M14 | `M14-C01` |
| 94 | `project217` | `PRJ-094` — Quantum Temporal Reversion | M3 | `M3-C01` |
| 95 | `project218` | `PRJ-095` — Limerick (cont.) | M4 | `M4-C01` |
| 96 | `project219` | `PRJ-096` — Xavier Re-initialization | M3 | `M3-C01` |

## 11. All 61 active HTML-handler bindings

Fifty-eight handlers resolve to 48 implemented ACT feature owners. Three resolve only to explicit Swarm exclusions. Repeating argument variants remain on the same feature. Function names and source identities are factual locators, not copied official code or a JavaScript execution requirement.

| Handler | Tag / DOM / event | Function and arguments | Coverage | Owner or exclusion |
|---|---|---|---|---|
| `HTML-001` | `button` / `btnMakePaperclip` / `onclick` | `clipClick`; `1` | `ACT-CLIP-MANUAL` | M1 / M1-G01 |
| `HTML-002` | `button` / `btnMakeFactory` / `onclick` | `makeFactory`; `none` | `ACT-FACTORY-BUILD` | M6 / M6-C01 |
| `HTML-003` | `button` / `btnFactoryReboot` / `onclick` | `factoryReboot`; `none` | `ACT-FACTORY-DISASSEMBLE` | M7 / M7-C01 |
| `HTML-004` | `button` / `btnMakeHarvester` / `onclick` | `makeHarvester`; `1` | `ACT-HARVESTER-BUILD` | M6 / M6-C01 |
| `HTML-005` | `button` / `btnHarvesterx10` / `onclick` | `makeHarvester`; `10` | `ACT-HARVESTER-BUILD` | M6 / M6-C01 |
| `HTML-006` | `button` / `btnHarvesterx100` / `onclick` | `makeHarvester`; `100` | `ACT-HARVESTER-BUILD` | M6 / M6-C01 |
| `HTML-007` | `button` / `btnHarvesterx1000` / `onclick` | `makeHarvester`; `1000` | `ACT-HARVESTER-BUILD` | M6 / M6-C01 |
| `HTML-008` | `button` / `btnHarvesterReboot` / `onclick` | `harvesterReboot`; `none` | `ACT-HARVESTER-DISASSEMBLE` | M7 / M7-C01 |
| `HTML-009` | `button` / `btnMakeWireDrone` / `onclick` | `makeWireDrone`; `1` | `ACT-WIREDRONE-BUILD` | M6 / M6-C01 |
| `HTML-010` | `button` / `btnWireDronex10` / `onclick` | `makeWireDrone`; `10` | `ACT-WIREDRONE-BUILD` | M6 / M6-C01 |
| `HTML-011` | `button` / `btnWireDronex100` / `onclick` | `makeWireDrone`; `100` | `ACT-WIREDRONE-BUILD` | M6 / M6-C01 |
| `HTML-012` | `button` / `btnWireDronex1000` / `onclick` | `makeWireDrone`; `1000` | `ACT-WIREDRONE-BUILD` | M6 / M6-C01 |
| `HTML-013` | `button` / `btnWireDroneReboot` / `onclick` | `wireDroneReboot`; `none` | `ACT-WIREDRONE-DISASSEMBLE` | M7 / M7-C01 |
| `HTML-014` | `button` / `btnMakeProbe` / `onclick` | `makeProbe`; `none` | `ACT-PROBE-LAUNCH` | M10 / M10-C01 |
| `HTML-015` | `button` / `btnLowerPrice` / `onclick` | `lowerPrice`; `none` | `ACT-PRICE-LOWER` | M1 / M1-G02 |
| `HTML-016` | `button` / `btnRaisePrice` / `onclick` | `raisePrice`; `none` | `ACT-PRICE-RAISE` | M1 / M1-G02 |
| `HTML-017` | `button` / `btnExpandMarketing` / `onclick` | `buyAds`; `none` | `ACT-MARKETING-BUY` | M1 / M1-G02 |
| `HTML-018` | `button` / `btnToggleWireBuyer` / `onclick` | `toggleWireBuyer`; `none` | `ACT-WIREBUYER-TOGGLE` | M3 / M3-C01 |
| `HTML-019` | `button` / `btnBuyWire` / `onclick` | `buyWire`; `none` | `ACT-WIRE-BUY` | M1 / M1-G02 |
| `HTML-020` | `button` / `btnMakeClipper` / `onclick` | `makeClipper`; `none` | `ACT-AUTOCLIPPER-BUY` | M1 / M1-G03 |
| `HTML-021` | `button` / `btnMakeMegaClipper` / `onclick` | `makeMegaClipper`; `none` | `ACT-MEGACLIPPER-BUY` | M3 / M3-C01 |
| `HTML-022` | `button` / `btnAddProc` / `onclick` | `addProc`; `none` | `ACT-PROCESSOR-ADD` | M2 / M2-C01 |
| `HTML-023` | `button` / `btnAddMem` / `onclick` | `addMem`; `none` | `ACT-MEMORY-ADD` | M2 / M2-C01 |
| `HTML-024` | `button` / `btnFeedSwarm` / `onclick` | `feedSwarm`; `none` | `ACT-SWARM-FEED` | ACT-SWARM-FEED (non-implementation) |
| `HTML-025` | `button` / `btnTeachSwarm` / `onclick` | `teachSwarm`; `none` | `ACT-SWARM-TEACH` | ACT-SWARM-TEACH (non-implementation) |
| `HTML-026` | `button` / `btnEntertainSwarm` / `onclick` | `entertainSwarm`; `none` | `ACT-SWARM-ENTERTAIN` | M8 / M8-C01 |
| `HTML-027` | `button` / `btnCladSwarm` / `onclick` | `cladSwarm`; `none` | `ACT-SWARM-CLAD` | ACT-SWARM-CLAD (non-implementation) |
| `HTML-028` | `button` / `btnSynchSwarm` / `onclick` | `synchSwarm`; `none` | `ACT-SWARM-SYNCHRONIZE` | M8 / M8-C01 |
| `HTML-029` | `button` / `btnQcompute` / `onclick` | `qComp`; `none` | `ACT-QUANTUM-COMPUTE` | M3 / M3-C01 |
| `HTML-030` | `button` / `btnInvest` / `onclick` | `investDeposit`; `none` | `ACT-INVEST-DEPOSIT` | M4 / M4-C01 |
| `HTML-031` | `button` / `btnWithdraw` / `onclick` | `investWithdraw`; `none` | `ACT-INVEST-WITHDRAW` | M4 / M4-C01 |
| `HTML-032` | `button` / `btnImproveInvestments` / `onclick` | `investUpgrade`; `none` | `ACT-INVEST-UPGRADE` | M4 / M4-C01 |
| `HTML-033` | `button` / `btnRunTournament` / `onclick` | `runTourney`; `none` | `ACT-TOURNEY-RUN` | M4 / M4-C01 |
| `HTML-034` | `button` / `btnNewTournament` / `onclick` | `newTourney`; `none` | `ACT-TOURNEY-NEW` | M4 / M4-C01 |
| `HTML-035` | `button` / `btnToggleAutoTourney` / `onclick` | `toggleAutoTourney`; `none` | `ACT-TOURNEY-AUTO-TOGGLE` | M5 / M5-C01 |
| `HTML-036` | `button` / `btnMakeFarm` / `onclick` | `makeFarm`; `1` | `ACT-FARM-BUILD` | M6 / M6-C01 |
| `HTML-037` | `button` / `btnFarmx10` / `onclick` | `makeFarm`; `10` | `ACT-FARM-BUILD` | M6 / M6-C01 |
| `HTML-038` | `button` / `btnFarmx100` / `onclick` | `makeFarm`; `100` | `ACT-FARM-BUILD` | M6 / M6-C01 |
| `HTML-039` | `button` / `btnFarmReboot` / `onclick` | `farmReboot`; `none` | `ACT-FARM-DISASSEMBLE` | M7 / M7-C01 |
| `HTML-040` | `button` / `btnMakeBattery` / `onclick` | `makeBattery`; `1` | `ACT-BATTERY-BUILD` | M6 / M6-C01 |
| `HTML-041` | `button` / `btnBatteryx10` / `onclick` | `makeBattery`; `10` | `ACT-BATTERY-BUILD` | M6 / M6-C01 |
| `HTML-042` | `button` / `btnBatteryx100` / `onclick` | `makeBattery`; `100` | `ACT-BATTERY-BUILD` | M6 / M6-C01 |
| `HTML-043` | `button` / `btnBatteryReboot` / `onclick` | `batteryReboot`; `none` | `ACT-BATTERY-DISASSEMBLE` | M7 / M7-C01 |
| `HTML-044` | `button` / `btnLowerProbeSpeed` / `onclick` | `lowerProbeSpeed`; `none` | `ACT-PROBE-SPEED-LOWER` | M10 / M10-C01 |
| `HTML-045` | `button` / `btnRaiseProbeSpeed` / `onclick` | `raiseProbeSpeed`; `none` | `ACT-PROBE-SPEED-RAISE` | M10 / M10-C01 |
| `HTML-046` | `button` / `btnLowerProbeNav` / `onclick` | `lowerProbeNav`; `none` | `ACT-PROBE-NAV-LOWER` | M10 / M10-C01 |
| `HTML-047` | `button` / `btnRaiseProbeNav` / `onclick` | `raiseProbeNav`; `none` | `ACT-PROBE-NAV-RAISE` | M10 / M10-C01 |
| `HTML-048` | `button` / `btnLowerProbeRep` / `onclick` | `lowerProbeRep`; `none` | `ACT-PROBE-REP-LOWER` | M10 / M10-C01 |
| `HTML-049` | `button` / `btnRaiseProbeRep` / `onclick` | `raiseProbeRep`; `none` | `ACT-PROBE-REP-RAISE` | M10 / M10-C01 |
| `HTML-050` | `button` / `btnLowerProbeHaz` / `onclick` | `lowerProbeHaz`; `none` | `ACT-PROBE-HAZ-LOWER` | M10 / M10-C01 |
| `HTML-051` | `button` / `btnRaiseProbeHaz` / `onclick` | `raiseProbeHaz`; `none` | `ACT-PROBE-HAZ-RAISE` | M10 / M10-C01 |
| `HTML-052` | `button` / `btnLowerProbeFac` / `onclick` | `lowerProbeFac`; `none` | `ACT-PROBE-FACTORY-LOWER` | M10 / M10-C01 |
| `HTML-053` | `button` / `btnRaiseProbeFac` / `onclick` | `raiseProbeFac`; `none` | `ACT-PROBE-FACTORY-RAISE` | M10 / M10-C01 |
| `HTML-054` | `button` / `btnLowerProbeHarv` / `onclick` | `lowerProbeHarv`; `none` | `ACT-PROBE-HARVESTER-LOWER` | M10 / M10-C01 |
| `HTML-055` | `button` / `btnRaiseProbeHarv` / `onclick` | `raiseProbeHarv`; `none` | `ACT-PROBE-HARVESTER-RAISE` | M10 / M10-C01 |
| `HTML-056` | `button` / `btnLowerProbeWire` / `onclick` | `lowerProbeWire`; `none` | `ACT-PROBE-WIRE-LOWER` | M10 / M10-C01 |
| `HTML-057` | `button` / `btnRaiseProbeWire` / `onclick` | `raiseProbeWire`; `none` | `ACT-PROBE-WIRE-RAISE` | M10 / M10-C01 |
| `HTML-058` | `button` / `btnLowerProbeCombat` / `onclick` | `lowerProbeCombat`; `none` | `ACT-PROBE-COMBAT-LOWER` | M10 / M10-C01 |
| `HTML-059` | `button` / `btnRaiseProbeCombat` / `onclick` | `raiseProbeCombat`; `none` | `ACT-PROBE-COMBAT-RAISE` | M10 / M10-C01 |
| `HTML-060` | `button` / `btnIncreaseProbeTrust` / `onclick` | `increaseProbeTrust`; `none` | `ACT-PROBE-TRUST-INCREASE` | M10 / M10-C01 |
| `HTML-061` | `button` / `btnIncreaseMaxTrust` / `onclick` | `increaseMaxTrust`; `none` | `ACT-PROBE-MAXTRUST-INCREASE` | M11 / M11-C01 |

## 12. All 32 coverage aliases and document closure

Aliases are trace/detail views, never extra feature owners. The canonical targets, documents, notes, and family rules come from the unchanged inventory. Every alias is a literal token in at least one of its canonical documents. Multi-target `RESET-CORE-001` retains both M3 Temporal Reversion and M13 Prestige contexts.

### SPACE-ENTRY-001

- Canonical targets: `PROG-HYPNO-RELEASE`
- Owner milestones: `M5`
- Scenario traces: `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-HYPNO-RELEASE
- Integration resolution: PROG-HYPNO-RELEASE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-030`, `UI-CREATION`

### SPACE-ENTRY-002

- Canonical targets: `PROG-SPACE-ENTRY`
- Owner milestones: `M9`
- Scenario traces: `ENG-POWER-SURPLUS-CAP-SPACE`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-SPACE-ENTRY
- Integration resolution: PROG-SPACE-ENTRY Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-045`, `UI-SPACE`, `SYS-POWER`

### SPACE-SWARM-001

- Canonical targets: `PROG-SPACE-RECOVERY`, `PROG-SWARM-HEALTH`
- Owner milestones: `M8`, `M10`
- Scenario traces: `ENG-GIFT-INACTIVE-HEALTH-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-SWARM-HEALTH and PROG-SPACE-RECOVERY
- Integration resolution: PROG-SWARM-HEALTH and PROG-SPACE-RECOVERY Both canonical targets stay required: Reboot clears only Space NO RESPONSE (space recovery), while Bored/Disorganized and status precedence remain swarm-health behavior.
- Related canonical acceptance links: `PRJ-070`, `PROG-SWARM-GIFTS`, `SYS-SWARM-HEALTH-GATES`

### PROBE-CREATE-001

- Canonical targets: `ACT-PROBE-LAUNCH`, `PROG-PROBE-PRODUCTION`
- Owner milestones: `M10`
- Scenario traces: `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: ACT-PROBE-LAUNCH; PROG-PROBE-PRODUCTION owns the progression dependency
- Integration resolution: ACT-PROBE-LAUNCH; PROG-PROBE-PRODUCTION owns the progression dependency Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.

### PROBE-TRUST-001

- Canonical targets: `ACT-PROBE-TRUST-INCREASE`, `PROG-PROBE-DESIGN`
- Owner milestones: `M10`
- Scenario traces: `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: ACT-PROBE-TRUST-INCREASE; PROG-PROBE-DESIGN owns the resource dependency
- Integration resolution: ACT-PROBE-TRUST-INCREASE; PROG-PROBE-DESIGN owns the resource dependency Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `RES-PROBE-TRUST`, `PROBE-DRIFT-001`

### PROBE-DESIGN-001

- Canonical targets: `PROG-PROBE-DESIGN`
- Canonical families: `ACT-PROBE-*`
- Resolved family feature IDs: `ACT-PROBE-SPEED-LOWER`, `ACT-PROBE-SPEED-RAISE`, `ACT-PROBE-NAV-LOWER`, `ACT-PROBE-NAV-RAISE`, `ACT-PROBE-REP-LOWER`, `ACT-PROBE-REP-RAISE`, `ACT-PROBE-HAZ-LOWER`, `ACT-PROBE-HAZ-RAISE`, `ACT-PROBE-FACTORY-LOWER`, `ACT-PROBE-FACTORY-RAISE`, `ACT-PROBE-HARVESTER-LOWER`, `ACT-PROBE-HARVESTER-RAISE`, `ACT-PROBE-WIRE-LOWER`, `ACT-PROBE-WIRE-RAISE`, `ACT-PROBE-COMBAT-LOWER`, `ACT-PROBE-COMBAT-RAISE`
- Owner milestones: `M10`
- Scenario traces: `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PROBE-DESIGN and ACT-PROBE-* allocation controls
- Integration resolution: PROG-PROBE-DESIGN and ACT-PROBE-* allocation controls The family note resolves to exactly the sixteen lower/raise allocation controls; Launch, Increase Probe Trust and Increase Max Trust have separate action ownership.
- Related canonical acceptance links: `ACT-PROBE-SPEED-LOWER`, `ACT-PROBE-SPEED-RAISE`, `ACT-PROBE-NAV-LOWER`, `ACT-PROBE-NAV-RAISE`, `ACT-PROBE-REP-LOWER`, `ACT-PROBE-REP-RAISE`, `ACT-PROBE-HAZ-LOWER`, `ACT-PROBE-HAZ-RAISE`, `ACT-PROBE-FACTORY-LOWER`, `ACT-PROBE-FACTORY-RAISE`, `ACT-PROBE-HARVESTER-LOWER`, `ACT-PROBE-HARVESTER-RAISE`, `ACT-PROBE-WIRE-LOWER`, `ACT-PROBE-WIRE-RAISE`, `ACT-PROBE-COMBAT-LOWER`, `ACT-PROBE-COMBAT-RAISE`, `UI-PROBE-DESIGN`, `RES-PROBE-ASSET-TRAITS`

### PROBE-STAT-008

- Canonical targets: `COMBAT-CORE-005`, `PRJ-071`, `PROG-PROBE-DESIGN`
- Owner milestones: `M10`
- Scenario traces: `ENG-COMBAT-NAMING-HONOR-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: COMBAT-CORE-005 owns live offense; PROG-PROBE-DESIGN owns allocation; project131 owns the unlock
- Integration resolution: COMBAT-CORE-005 owns live offense; PROG-PROBE-DESIGN owns allocation; project131 owns the unlock Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `ACT-PROBE-COMBAT-LOWER`, `ACT-PROBE-COMBAT-RAISE`, `PROBE-STAT-001`

### PROBE-DRIFT-002

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: END-BRANCH-002 and PROG-END-CHOICE
- Integration resolution: END-BRANCH-002 and PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-084`, `PROBE-DRIFT-001`

### PROBE-RECOVERY-001

- Canonical targets: `PRJ-075`, `PROG-SPACE-RECOVERY`
- Owner milestones: `M10`
- Scenario traces: `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-SPACE-RECOVERY and project135
- Integration resolution: PROG-SPACE-RECOVERY and project135 Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.

### COMBAT-HONOR-001

- Canonical targets: `PRJ-064`, `PROG-DRIFTWAR`
- Owner milestones: `M11`
- Scenario traces: `ENG-COMBAT-NAMING-HONOR-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-DRIFTWAR and project121
- Integration resolution: PROG-DRIFTWAR and project121 Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `UI-COMBAT`, `RES-HONOR`, `ACT-PROBE-MAXTRUST-INCREASE`

### COMBAT-HONOR-003

- Canonical targets: `ACT-PROBE-MAXTRUST-INCREASE`, `PROG-DRIFTWAR`
- Owner milestones: `M11`
- Scenario traces: `ENG-COMBAT-NAMING-HONOR-GATES`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: ACT-PROBE-MAXTRUST-INCREASE and PROG-DRIFTWAR
- Integration resolution: ACT-PROBE-MAXTRUST-INCREASE and PROG-DRIFTWAR Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `RES-HONOR`, `RES-PROBE-TRUST`

### COMBAT-HONOR-004

- Canonical targets: `PRJ-074`, `PROG-DRIFTWAR`
- Owner milestones: `M11`
- Scenario traces: `ENG-COMBAT-TIMEOUT-HONOR`, `ENG-HONOR-NEGATIVE-AND-GLORY`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-DRIFTWAR and project134
- Integration resolution: PROG-DRIFTWAR and project134 Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `COMBAT-HONOR-002`, `COMBAT-CORE-008`

### COMBAT-HONOR-005

- Canonical targets: `PRJ-072`, `PROG-DRIFTWAR`
- Owner milestones: `M11`
- Scenario traces: `ENG-HONOR-NEGATIVE-AND-GLORY`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-DRIFTWAR and project132
- Integration resolution: PROG-DRIFTWAR and project132 Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `RES-HONOR`

### COMBAT-HONOR-006

- Canonical targets: `PRJ-073`, `PROG-DRIFTWAR`
- Owner milestones: `M11`
- Scenario traces: `ENG-HONOR-NEGATIVE-AND-GLORY`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-DRIFTWAR and project133
- Integration resolution: PROG-DRIFTWAR and project133 Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `COMBAT-HONOR-002`

### END-COMPLETE-001

- Canonical targets: `PROG-UNIVERSAL-GOAL`
- Owner milestones: `M12`
- Scenario traces: `E2E-UNIVERSAL-LIFETIME-NO-DRIFT-GATE`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-UNIVERSAL-GOAL
- Integration resolution: PROG-UNIVERSAL-GOAL Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PROG-MILESTONES`

### END-COMPLETE-002

- Canonical targets: `PROG-UNIVERSAL-GOAL`
- Owner milestones: `M12`
- Scenario traces: `E2E-UNIVERSAL-EXHAUSTION-NO-DRIFT-GATE`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-UNIVERSAL-GOAL
- Integration resolution: PROG-UNIVERSAL-GOAL This is the second OR predicate of the same PROG-UNIVERSAL-GOAL, not another feature or a final-Rejection Wire relaxation.
- Related canonical acceptance links: `END-FINAL-001`

### END-DIALOG-001

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-076`

### END-DIALOG-002

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-077`

### END-DIALOG-003

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-078`

### END-DIALOG-004

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-079`

### END-DIALOG-005

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-080`

### END-DIALOG-006

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-081`

### END-DIALOG-007

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-082`

### END-BRANCH-001

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE
- Integration resolution: PROG-END-CHOICE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-083`, `PRJ-085`, `PRJ-086`

### END-BRANCH-002

- Canonical targets: `PROG-END-CHOICE`
- Owner milestones: `M12`
- Scenario traces: `E2E-EMPEROR-MUTUAL-EXCLUSION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-END-CHOICE; PROBE-DRIFT-002 details the drift consequence
- Integration resolution: PROG-END-CHOICE; PROBE-DRIFT-002 details the drift consequence END-BRANCH-002 is itself an alias/detail ID, not an extra canonical feature row; PRJ-084 supplies the project purchase and PROBE-DRIFT-002 is another alias for its drift consequence.
- Related canonical acceptance links: `PRJ-084`, `PRJ-087`, `PROBE-DRIFT-001`

### RESET-PRESTIGE-001

- Canonical targets: `PROG-PRESTIGE`
- Owner milestones: `M13`
- Scenario traces: `E2E-PRESTIGE-NEXT-DOOR`, `RESET-INPROCESS-RETRY-RETENTION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PRESTIGE
- Integration resolution: PROG-PRESTIGE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-085`, `PROG-PRESTIGE`

### RESET-PRESTIGE-002

- Canonical targets: `PROG-PRESTIGE`
- Owner milestones: `M13`
- Scenario traces: `E2E-PRESTIGE-WITHIN`, `RESET-INPROCESS-RETRY-RETENTION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PRESTIGE
- Integration resolution: PROG-PRESTIGE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-086`, `PROG-PRESTIGE`

### RESET-PRESTIGE-003

- Canonical targets: `PROG-PRESTIGE`
- Owner milestones: `M13`
- Scenario traces: `E2E-PRESTIGE-NEXT-DOOR`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PRESTIGE
- Integration resolution: PROG-PRESTIGE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `RES-PRESTIGE`, `UI-PRESTIGE`, `PROG-DEMAND-SALES`

### RESET-PRESTIGE-004

- Canonical targets: `PROG-PRESTIGE`
- Owner milestones: `M13`
- Scenario traces: `E2E-PRESTIGE-WITHIN`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PRESTIGE
- Integration resolution: PROG-PRESTIGE Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `RES-PRESTIGE`, `UI-PRESTIGE`, `PROG-CREATIVITY`, `SYS-OPS-CREATIVITY-CURVES`

### RESET-CORE-001

- Canonical targets: `PROG-PRESTIGE`, `PROG-TEMPORAL-RESET`
- Owner milestones: `M3`, `M13`
- Scenario traces: `E2E-PRESTIGE-NEXT-DOOR`, `E2E-PRESTIGE-WITHIN`, `E2E-TEMPORAL-RESET`, `RESET-INPROCESS-RETRY-RETENTION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-PRESTIGE and PROG-TEMPORAL-RESET
- Integration resolution: PROG-PRESTIGE and PROG-TEMPORAL-RESET Integration must cover both canonical contexts: Accept/prestige destinations (M13) and Quantum Temporal Reversion (M3); ordinary run state clears while stored U/S survives. The documents do not authorize choosing only one target forever.
- Related canonical acceptance links: `PRJ-085`, `PRJ-086`, `PRJ-094`, `RES-PRESTIGE`, `RES-PROGRESSION`

### RESET-ALT-001

- Canonical targets: `PROG-TEMPORAL-RESET`
- Owner milestones: `M3`
- Scenario traces: `E2E-TEMPORAL-RESET`, `RESET-INPROCESS-RETRY-RETENTION`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-TEMPORAL-RESET
- Integration resolution: PROG-TEMPORAL-RESET Preserve this alias/detail view in the target milestone acceptance; it adds no canonical feature owner row.
- Related canonical acceptance links: `PRJ-094`, `PROG-QUANTUM`, `RES-PRESTIGE`

### RESET-HUMAN-001

- Canonical targets: `PROG-TRUST`
- Owner milestones: `M2`
- Scenario traces: `ENG-TRUST-OPS-CREATIVITY`, `E2E-XAVIER-ALLOCATION-RESET`, `E2E-FULL-PHASE-ENGINE-TRACE`
- Canonical documents: [requirements/gameplay-progression.md](./gameplay-progression.md), [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md)
- Canonical note: PROG-TRUST
- Integration resolution: PROG-TRUST remains M2-owned and PRJ-096 remains M3-related, with no canonical ownership change. M2 independently accepts ordinary allocation/Ops/creativity/UI/snapshots through ENG-TRUST-OPS-CREATIVITY; M3 separately accepts actual Human PRJ-096 purchase at 100000 Creativity, its allocation-only reset and valid repetition through E2E-XAVIER-ALLOCATION-RESET.
- Related canonical acceptance links: `PRJ-096`, `SYS-OPS-CREATIVITY-CURVES`, `ACT-PROCESSOR-ADD`, `ACT-MEMORY-ADD`

### Narrow `PROBE-DESIGN-001` family rule

`ACT-PROBE-*` in this alias means the direct lower/raise arrows only: 16 Speed, Exploration, Replication, Hazard, Factory, Harvester, Wire, and Combat controls, plus explicit target `PROG-PROBE-DESIGN`. It does **not** swallow `ACT-PROBE-LAUNCH`, `ACT-PROBE-TRUST-INCREASE`, or `ACT-PROBE-MAXTRUST-INCREASE`; those separately owned features remain in the map and handler table.

## 13. Seven explicit exclusions — no feature ownership

| Exclusion | Review milestones | Canonical non-implementation reason | Preservation and source |
|---|---|---|---|
| `ACT-SWARM-FEED` | `M8` | HTML-only legacy control: feedSwarm is undefined and current runtime never assigns Hungry status 1, so no gameplay behavior is required. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-actions.md](./gameplay-actions.md) — `6. Explicit exclusions for active legacy HTML` |
| `ACT-SWARM-TEACH` | `M8` | HTML-only legacy control: teachSwarm is undefined and current runtime never assigns Confused status 2, so no gameplay behavior is required. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-actions.md](./gameplay-actions.md) — `6. Explicit exclusions for active legacy HTML` |
| `ACT-SWARM-CLAD` | `M8` | HTML-only legacy control: cladSwarm is undefined and current runtime never assigns Cold status 4, so no gameplay behavior is required. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-actions.md](./gameplay-actions.md) — `6. Explicit exclusions for active legacy HTML` |
| `COMBAT-LEGACY-001` | `M10`, `M11` | All behaviors are inside commented code/UI. Live combat does not apply territory loss, large legacy battle reports, probeCombat^1.7 offense, or naming-based offense doubling. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `COMBAT-LEGACY-001 — Inactive Battles report and territory system` |
| `RESET-DEBUG-001` | `M3`, `M13`, `M15` | The controls are commented out, are not legitimate progression paths, and must not be exposed or used to satisfy gameplay acceptance. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `RESET-DEBUG-001 — Commented reset, save, prestige, and cheat controls` |
| `RESET-PERSIST-001` | `M10`, `M11` | The missing probeHarv field, reload-time deletion of the restored battle record without serialized ships/grid, and browser-storage behavior are non-authoritative persistence defects, not game mechanics. Battle-name counters are saved/restored. Product requirements use coherent population and battle state rather than reproduce them. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `RESET-PERSIST-001 — Save omissions and reload-time battle cancellation` |
| `RESET-PERSIST-002` | `M14`, `M15` | Audio timing, stale overlays, browser reload behavior, and uses repair are implementation artifacts. Ending state mechanics and prestige-versus-run resets are owned by the active END/PROG capabilities. | Assert only the documented exclusion boundary; do not add a mechanic, reward, control, or persistence defect. Source: [requirements/gameplay-combat-endgame.md](./gameplay-combat-endgame.md) — `RESET-PERSIST-002 — In-progress ending and audio reload observations` |

## 14. Candidate validation, CI activation, and review gates

### 14.1 Native planning checks

Run these read-only commands from the repository root. They use only Python standard library and do not need private captures, network access, Rust/Node manifests, or game code:

```sh
python3 -B scripts/validate_inventory.py requirements/data/gameplay-inventory.json
python3 -B scripts/validate_execution_plan.py requirements/data/execution-plan.json
python3 -B scripts/validate_execution_plan.py requirements/data/execution-plan.json --self-test
```

The first command validates the canonical inventory. The second validates this complete plan against its exact raw-byte/relationship hashes and the actual requirement headings/documents. The third executes the real CLI against isolated temporary mutations and requires intentional failures with the expected error classes. The plan CLI also has an optional local-only private-source-directory check for long-line hygiene; public CI never receives that directory. No official JavaScript is executed by any command.

Additional integration evidence includes the existing inventory validator in its local source-bound mode, exact canonical and pinned-capture hashes, `git diff --check`, Markdown-link containment, CJK/private-path/secret-shape/raw-long-line scans, generated-cache checks, and a diff review against the explicit seven-path scope. Those results belong in the candidate review record; this document does not predeclare them or turn structural checks into semantic approval.

### 14.2 GitHub Actions reality

The proposed [validate-plan.yml](../.github/workflows/validate-plan.yml) has `contents: read`, path-scoped pull-request/main triggers and manual dispatch after availability on the default branch. It runs on `ubuntu-24.04` with stable Python 3.14 and executes exactly the version report plus the three commands above. `actions/checkout` is pinned to `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1, node24) and `actions/setup-python` to `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (v7.1.0, node24), based on the checked public action metadata.

No Actions run exists before the first real push. Trigger parsing, full-SHA action availability, setup-python resolution, permissions, and actual Linux pass/fail status are explicit first-push gates. Required-check wiring and merge-result checks remain later controller responsibilities. There is no Cargo/Node/browser/game job or conditional skip that could pretend a missing game build succeeded.

### 14.3 What the checks do and do not prove

Structural checks prove exact closure, hashes, schema/type constraints, source-reference resolution, task/milestone DAG rules, scenario reciprocity, detailed-task contract, and specified public hygiene. They do not prove genuine playability, semantic prose fidelity, economic balance, distribution equivalence, meaningful dependency prose, race freedom, snapshot correctness, all privacy risks, or game-build success. Every scenario remains DESIGN_ONLY_NOT_EXECUTED until its future implementation runs it.

This planning PR still needs two fresh independent reviews at exact HEAD: whole-game/source completeness and adversarial engineering. It also requires the mandatory Opus major-plan review. Any affected change requires rebinding evidence/reviews. A fresh normal non-admin merge controller must verify the explicit seven-path scope, actual first-push CI, current base/reviews, normal merge, and post-merge main checks. Only after that verification may native milestones and detailed M1 Issues be created and execution begin.
