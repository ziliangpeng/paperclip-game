# Official Gameplay Feature Inventory

## 1. Authority and scope

This inventory records the official gameplay content and high-/mid-level relationships needed to plan and accept the complete reimplementation. It does not copy or execute the official JavaScript, and it does not turn incidental browser implementation details into product requirements.

The detailed documents below are semantics-bearing requirements. `data/gameplay-inventory.json` is their machine-checkable feature index and source-binding map; it does not duplicate every rule or replace the prose. Stable coverage IDs are planning handles, not an API schema or a requirement to preserve internal JavaScript structure.

The ultimate acceptance target remains the whole game in [Product Requirements](./product.md). Finishing this inventory establishes reference completeness only; it does not freeze M1, create an implementation task, or authorize gameplay implementation.

## 2. Pinned public reference snapshot

The primary entry point is <https://www.decisionproblem.com/paperclips/index2.html>. The inventory was captured on 2026-11-07 from that page and the four gameplay scripts it normally loads. The authoritative source URLs and SHA-256 hashes are recorded in [the machine-readable inventory index](./data/gameplay-inventory.json).

SHA-256 identifies the reviewed snapshot, not a promise that the live public page will remain unchanged. A later reference change requires a separately reviewed inventory update. Official raw captures used during research are not copied into this repository. Public references, factual official IDs, behavior summaries, formulas that affect gameplay, and file/line locators are retained as evidence.

The complete `projects` array contains **96 project definitions in actual insertion order**, including the alphanumeric IDs `project10b` and `project40b`. Numeric-only extraction is incorrect: `project17` precedes `project16`, and `project34`, `project70`, and `project35` precede `project27`. The HTML contains **61 active inline click handlers**, **51 distinct called targets**, and **17 commented-out handlers**. Of the called targets, **48 have implementations and three are undefined legacy names**.

## 3. Inventory documents

| Document | Required coverage |
|---|---|
| [Actions and state](./gameplay-actions.md) | Player commands, batch/control variants, meaningful resources, stage-specific panels and feedback, non-click controls, and deliberately excluded legacy affordances |
| [Projects](./gameplay-projects.md) | `PRJ-001` through `PRJ-096`, official order, costs, visibility triggers, effects, repeatability, dependencies, lifecycle, and alternate-path projects |
| [Progression](./gameplay-progression.md) | Initial state, three clip ledgers, business and demand, computation and strategic resources, transitions, autonomous Earth, space progress, universal goals, endings, and resets |
| [Combat and endgame](./gameplay-combat-endgame.md) | Probe state and production, exploration and attrition, active combat, Drifters and Honor, narrative choice, both completion conditions, prestige, and teardown/credits |

`ACT-*` identifies a player action, `CTL-*` a non-click control, `UI-*` relevant information or panel behavior, `PROG-*` a progression/economic capability, and `PRJ-*` an official project. Combat and endgame documents define their domain-specific prefixes. Repeated references to one ID describe the same capability; they are not separate deliverables.

Every required feature has a stable ID in the data index. An **exclusion** is different: it is a documented source observation that must not silently become a new mechanic or acceptance obligation. Every active official handler either maps to a required feature or has an explicit exclusion. All 96 official projects are behaviorally covered; they are not optional based on subjective importance.

## 4. Complete progression spine

1. **Human-supervised manufacturing and business.** Manual clips consume wire and feed lifetime production, sellable inventory, and spendable unused-clip capital as distinct ledgers. Funds buy wire, marketing, and automation. Sales respond stochastically to price, marketing, and demand, constrained by stock.
2. **Trust-constrained self-modification and strategic growth.** Computation unlocks through production or economic deadlock. Processor/memory allocation produces operations; projects unlock Creativity and progressively more complex production, quantum, investment, trust, tournament, and Yomi systems. The complete project tree provides the route to autonomous release; no M1 division is inferred here.
3. **Autonomous Earth.** Releasing the HypnoDrones removes the Human business/manufacturing path and changes the resource economy. Earth matter, acquired matter, wire production, factories, power, drones, and swarm computation form a new coupled system. Disassembly, recovery, power constraints, Swarm Work/Think allocation, gifts, Boredom, and Disorganization are part of this progression rather than isolated panels.
4. **Space and probes.** Space entry has explicit prerequisites and conversion/refund effects. Probe Trust buys allocation points; probe stats control exploration, replication, infrastructure production, hazard losses, value drift, and combat behavior. Yomi and Honor participate in probe progression. Production continues according to authoritative server time, not client attention.
5. **Universal achievement and endings.** Universal achievement has two source-grounded completion conditions, and **Driftwar is not a mandatory completion gate**. Universal achievement (milestone track 15), reaching the Emperor's Accept/Reject choice, and finishing the Reject credits (flag 20) are separate endpoints. Acceptance must not substitute one for the other.
6. **Alternative completion and reset paths.** Accept offers the Universe Next Door and Universe Within prestige paths. Reject performs the staged teardown, final manual-clip sequence, and credits. Quantum Temporal Reversion is a separately inventoried return path. Xavier Re-initialization is an allocation reset, not equivalent to a prestige restart.

Independent phase flags and project prerequisites, not the milestone message number alone, control actual availability. Detailed state transitions and cross-system dependencies live in the two system documents above.

## 5. Fidelity classification

### Required gameplay and experience

Preserve resource identities and conversions, meaningful costs and formulas, stochastic distributions and dependencies, production growth, availability gates, stage handoffs, strategic allocation/trade-offs, both completion conditions, narrative/named feedback, reset/prestige distinctions, and the ability to traverse all inventoried paths. Browser random number sequences need not match, but changing a distribution or probability is not excused as an implementation detail.

### Deliberately excluded source observations

- Feed, Teach, and Clad are reserved Swarm controls with no function definitions or active status assignments in this capture. Bored/Entertain and Disorganized/Synchronize are actual behavior. The three undefined controls are explicitly indexed as exclusions instead of becoming invented mechanics.
- Commented save slots, Reset, prestige-reset, debug/cheat, and legacy battle-report controls are not active gameplay or a request for developer tools.
- The live combat model is the canvas simulation with its documented linear `probeCombat` offense contributions. The large territory-loss and `probeCombat^1.7` alternative and associated old reporting are commented legacy, not a second live combat mechanic.
- Exact `setInterval` scheduling, background-tab throttling, DOM-only validation, initial CSS paint, numeric formatting, floating-point tails, browser RNG sequences, `localStorage`, multibrowser divergence, and storage/save omissions are excluded by [Product Requirements](./product.md). The new server must preserve meaningful game behavior while satisfying its own authoritative real-time and persistence contracts.
- The omitted `probeHarv` save field, unrestored active battles, and similar source-save defects are not intended progression. They do not justify omitting probe state from the new server's snapshots. Exact zero-boundary and disabled-versus-function inconsistencies are recorded as implementation artifacts, not balance changes invented for this clone.

### CONFIRMED deviation: partial-battery brownout

`SYS-POWER-PARTIAL-BROWNOUT` preserves both sides of an explicit behavior difference approved on 2026-11-07. In the source's last partial-cover update (`S < D` and `0 < B < D-S`), `main.js:2981-2999` computes `(2S+B-D)/D`; once storage is exhausted it uses `S/D`. That produces a discontinuity and possible negative factor, followed by an upward jump on the empty-storage branch.

This implementation instead uses a base factor of `1` when storage covers the deficit, `(S+B)/D` for the last partial-cover update while consuming remaining stored energy, and `S/D` once exhausted. The reason is to preserve the intended supply/storage/production relationship without copying the suspected source defect. This is **CONFIRMED product behavior**, not an open interpretation or an agent-chosen balance change. [Product Requirements](./product.md) provides the normative rules and the required boundary tests; the detailed power inventory records the affected systems.

These classifications follow the already approved product fidelity boundary; they do not create new games, simplified placeholders, debug tools, or a requirement to reproduce defects.

## 6. Open and downstream decisions

No known high-/mid-level gameplay category is left as an unexplained catch-all at this inventory's fidelity boundary. Future disputes about a source fact or intended product scope must still use `needs-decision` and a requirements update; implementation workers must not silently resolve them.

### CONFIRMED deviation: Reject final Wire remainder

The official normal button disables manual Paperclip below one Wire (`main.js:1150-1153`), while Reject credits require Memory disassembly and exactly zero Wire (`main.js:4518-4550`). With automatic production already removed, a positive sub-one remainder can therefore strand the ending. The source's pre-validation increment of `finalClips` is a defect, not a resource rule.

**CONFIRMED behavior deviation (2026-11-07):** only in Reject's final manual stage (`dismantle >= 4`), any positive Wire accepts one final conversion command. It produces `min(1, Wire)`, adds that same amount to lifetime clips, sellable inventory, and unused-clip capital, consumes the remaining Wire, and increments the accepted-conversion counter once. Zero Wire is rejected with no resource or counter change; ordinary manual manufacturing and the separate below-one universal-exhaustion predicate are unchanged. The exact-zero credit gate remains exact.

The reason is to convert the actual final remainder and avoid a teardown-created softlock without discarding it as unusable. [Product Requirements](./product.md) owns the normative scope and required tests for full/sub-one/zero Wire, all three ledgers, valid-click counting, stage gating, and concurrency.

The following are downstream planning or engineering work, not permission to start coding:

- #4 must assign each required feature to a playable Milestone, define entry/exit scenarios and dependencies, and keep exclusions explicit.
- Issue acceptance must separately identify universal achievement, narrative choice, prestige restart, credits completion, and allocation reset where applicable.
- The simulation timestep and protocol representation must follow [Runtime](./runtime.md) and [Clients and API](./clients.md), preserving economic time semantics without copying browser timers.
- Best-effort classic presentation, stochastic behavior, and executable tests require meaningful design evidence; they do not require pixel equality or a bit-for-bit browser trace.

## 7. Executable coverage verification

Run the standard-library-only structural and source-binding check from the repository root:

```sh
python3 -B scripts/validate_inventory.py requirements/data/gameplay-inventory.json
```

For the issue's source-grounded evidence, run the same command with `--source-dir` pointing to a private capture whose filenames match the pinned reference manifest. The check verifies those files' SHA-256 hashes, parses active HTML handlers without executing scripts, and compares ordered project declarations and `projects.push(...)` entries against the source bindings. It also checks unique stable IDs, required documentation, CJK absence, unbound references, duplicate source bindings, and inappropriate project exclusions.

This verifies defined coverage relationships; it cannot by itself prove every prose summary's semantics. Independent reviewers must cross-check the detailed documents against the pinned official sources, with particular attention to project order/effects, resource conversions, active combat, both completion conditions, both prestige paths, and excluded legacy behavior.
