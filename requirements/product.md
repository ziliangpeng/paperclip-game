# Product Requirements

## 1. Product Vision — CONFIRMED

Build a reimplementation of Universal Paperclips in which the server is the sole authoritative source of state.

- The game world is advanced continuously by the server.
- Web pages, human harnesses, and one or more Agents are all merely clients.
- Clients send actions and receive state for observation; clients do not own the game rules.
- The project's ultimate goal is a complete gameplay clone, not merely a paperclip-themed button demo.

## 2. Full Scope and Incremental Delivery — CONFIRMED

### Full clone

Full clone means a **complete and faithful reproduction of the original game's high-level and mid-level game design, content, and gameplay experience**.

The following must be preserved:

- The original game's major stages, progression, and ending;
- The design relationships among resources, actions, production, sales, automation, upgrades, and unlocks;
- The gameplay embodied by the initial state, major economic values, growth curves, and balance;
- The core strategic trade-offs, pacing, and key feedback;
- All major mechanics that allow players to experience the original game's complete progression.

The complete game will be delivered incrementally through multiple playable Milestones. Each Milestone:

- Must implement a genuine subset of the final game;
- Must not use invented simplified rules as placeholders and then treat the simplification as clone acceptance;
- Until the complete feature inventory has been implemented, may only be called an interim version and must not be described as a completed full clone.

### Inspired game — Future direction

New games inspired by the original, additional mechanics, or gameplay not found in the original must not be planned until the complete gameplay clone is finished. They are outside the acceptance scope of the current clone.

## 3. Official Reference — CONFIRMED

The primary reference is the official page and the game content it loads normally:

- `https://www.decisionproblem.com/paperclips/index2.html`

On the initial check on 2026-11-07, the page loaded its main game script with the `?v3` parameter. Wikis, videos, memories, and other materials may only assist understanding; the official reference takes precedence when game designs conflict.

The official reference is used to determine gameplay; line-by-line porting of its JavaScript is not required.

## 4. Gameplay Fidelity Boundaries — CONFIRMED

### Retain

- The original game design and gameplay experience;
- Resource relationships, action effects, major unlocks, and progression;
- Rules of the economy that have material gameplay significance;
- Stage content and strategic choices.

### Not required to retain

- The internal organization of JavaScript variables, modules, and the DOM;
- The specific scheduling order of multiple `setInterval` calls;
- Timer throttling in background tabs;
- Floating-point mantissas, rounding differences with no gameplay significance, or browser numeric side effects;
- Unauthorized behavior such as modifying variables through DevTools, using negative internal parameters, or directly calling internal functions;
- Resource validation that relies solely on DOM `disabled` states;
- The `localStorage` format, refresh rollback, and state divergence across multiple browser tabs;
- Random number sequences or per-tick floating-point trajectories identical to those of the original browser version.

This means:

- No bit-for-bit, pixel-for-bit, or original-JavaScript state-trajectory differential comparisons will be performed;
- Values and formulas that have gameplay significance must still preserve the original design and must not be replaced with a different balance on the grounds that they are "implementation details";
- Suspected original bugs that would affect product design must first be classified and recorded; implementation Agents must not decide to make silent changes themselves;
- The server must handle unauthorized inputs and concurrency correctly rather than replicate client-trust flaws.

### Partial-battery brownout — CONFIRMED behavior deviation (2026-11-07)

For a power update, let `S` be generated power, `D` be power demand, and `B` be stored energy available before that update, all expressed on a consistent authoritative time base. This rule concerns `S < D` during autonomous terrestrial play, before space disables the terrestrial power loop.

**Observed official source.** When stored energy is positive but insufficient to cover `D-S`, `main.js:2981-2999` consumes the remaining storage and computes the partial-brownout factor as `(2S+B-D)/D`. Once storage is exhausted, it computes `S/D`. The source expression has a discontinuity at exhaustion, can produce a negative factor, and can jump upward when it switches to the empty-storage branch. This is source evidence, not the desired implementation rule.

**Confirmed implementation difference.** When `S < D`:

1. If `B >= D-S`, the base performance factor is `1` and storage covers the deficit.
2. If `0 < B < D-S`, the base performance factor for that last partial-cover update is `(S+B)/D`, and the remaining stored energy is consumed. Within this branch the factor is naturally between 0 and 1.
3. When stored energy is exhausted, use `S/D`.

This explicitly authorized deviation preserves the intended supply/storage/production relationship while avoiding the suspected source defect. It is not a silent simplification and must never be rewritten as the old source expression or as a clamp of that expression. Other separately inventoried rules, including Momentum and space disabling this power loop, remain applicable.

Acceptance tests must cover exact full-cover and last-partial-cover transitions, exhaustion, nonnegative bounded partial-brownout output, and the downstream resource effects. The original source anomaly and this deviation are also indexed in the gameplay inventory so that a later fidelity review cannot mistake the difference for an accidental regression.

### Reject final Wire remainder — CONFIRMED behavior deviation (2026-11-07)

**Observed official source.** The normal Make Paperclip button is disabled when `wire < 1` (`main.js:1150-1153`), and `clipClick` only changes wire and the three clip ledgers under `wire >= 1` (`main.js:2326-2362`). Reject credit advancement requires Memory disassembly and exactly `wire == 0` (`main.js:4518-4550`), after automatic production has been dismantled. A positive sub-one Wire remainder can therefore leave the visible final-manual-conversion path unable to reach the credit gate. The source also increments `finalClips` before checking wire validity; that pre-validation side effect is an implementation defect, not a resource award or a supported click-counting rule.

**Confirmed implementation difference and scope.** Only during Reject's final manual conversion stage (source state `dismantle >= 4`, after automatic production is removed):

1. A command with `wire > 0` is valid even when `wire < 1`.
2. For each accepted command, let `amount = min(1, wire)`. Subtract that amount from wire, consuming all remaining wire when it is below one, and add the **same amount** to lifetime clips, sellable inventory, and unused-clip capital.
3. Increment the accepted-final-conversion counter once. Zero-wire commands produce no resource and do not increment this counter, and negative outputs or negative wire are forbidden.

Ordinary manual manufacturing outside this narrowly scoped final Reject stage is unchanged. The exact-zero credit gate is retained; no zero-wire command or shared epsilon satisfies it. The separate below-one universal-exhaustion gate is also unchanged. This intentional fractional remainder is not merely a floating-point precision relaxation.

**Reason and required evidence.** The deviation permits genuine final conversion of the whole positive remainder, avoids a teardown-created ending softlock, and preserves the original all-wire-consumed meaning rather than abandoning residual wire. Acceptance must cover an ordinary full-wire command, a sub-one command updating all three ledgers by the same fractional amount and reaching exact zero, zero-wire rejection without counter/resource changes, fraction-before-final-stage rejection, and credits advancing only when Memory is disassembled and wire is exactly zero. Concurrent/repeated command handling must preserve those invariants, and accepted-conversion-count feedback must remain one per successful final command.

## 5. Clients and Operators — CONFIRMED

- Humans, Agents, and other programs all use the same kind of Command/View interaction.
- The game server does not know the operator type; Commands contain no `actor` identity field.
- There is no current player, Human/Agent turn, or control handoff process.
- Multiple Humans, multiple Agents, and multiple web pages may all send Commands to the same game simultaneously.
- Observing without sending Commands is natural behavior and requires no special server role.
- Thinking, reasoning, or hesitation by any client does not pause the world.
- The same current state and the same Command produce the same rule outcome regardless of their source.

## 6. First Web UI — CONFIRMED

The first UI is a **best effort visual clone** of the original:

- Preserve the minimalist black-and-white style, main panels, buttons, information hierarchy, and browsing experience as much as possible;
- Allow players familiar with the original to recognize and operate it naturally;
- Pixel-perfect fidelity is not required;
- The DOM, CSS, event bindings, and static assets are not required to match the official files;
- Pixel-by-pixel screenshot equality is not a merge gate;
- The UI only displays server state and sends Commands; it does not advance the game locally or compute authoritative game state.

Different UIs, dashboards, monitoring, and debugging views may be designed later, but the current scope must not be expanded prematurely.

## 7. Final Acceptance Principles — CONFIRMED

Full clone may be declared complete only when all of the following conditions are met:

1. Every item in the [official feature inventory](./gameplay-inventory.md) has been mapped to completed Milestones;
2. The game can progress from the original initial state through the original major stages to the ending;
3. Core resources, strategies, progression, and gameplay experience preserve the original design;
4. All critical behavior has layered executable verification;
5. Throughout the entire process, the server remains the sole authority over state and preserves real-time simulation semantics.
