# Testing and Acceptance Strategy

## 1. Principles — CONFIRMED

- Tests derive from requirements, risks, and Acceptance Criteria, not from a pursuit of magic coverage percentages.
- Every Issue must define its verification method, and every PR must provide corresponding evidence.
- Critical paths should have extensive targeted positive and negative tests, sequence tests, and concurrency tests, rather than low-value assertions that repeat implementation descriptions.
- Tests must not be deleted, assertions weakened, or quality gates changed to make an implementation pass.
- Pure engine tests may advance ticks directly; production gameplay and the Agent API have no pause or step capability.
- Integration tests that require real time must be bounded and must not use long `sleep` calls to simulate every rule.

## 2. Layered Matrix

| Layer | Concerns That Must Be Covered |
|---|---|
| Rule unit tests | Initial state, resource changes, boundaries, invalid input, unlocks, and numeric limits |
| State sequence tests | Different orderings of Commands and ticks, long progression, and state-machine reachability |
| Property-based tests | No duplicate execution, lost updates, or violations of resource invariants across large operation sequences |
| Concurrency tests | Multiple clients competing for the same resource, simultaneously legal commands, tick-command races, and retry deduplication |
| API contract tests | Command/View schemas, error reasons, unknown actions, unknown-field policy, and the adopted retry/idempotence contract |
| SSE tests | Initial snapshot, update ordering, disconnection and reconnection, late Views, resynchronization after crash recovery, and isolation from old Views |
| Persistence tests | Snapshot completeness and atomicity, recovery, no backfill, the loss window, and repeated startup |
| Gameplay scenario tests | Reaching the current Milestone's actual exit criteria from a specified initial state |
| Browser E2E | Clicks only send requests, server state is displayed, refresh does not roll back, and two pages share the game |
| Long simulation and stability | Economic chains and state machines do not deadlock or produce illegal states during medium- and long-term operation |

Each Issue requires only the layers relevant to its risks; not every PR must mechanically execute every layer. Milestone acceptance must include the corresponding end-to-end gameplay scenario.

## 3. Rule and Numeric Verification — CONFIRMED

- The original game is a game-design reference; bit-for-bit differential comparisons of individual ticks, floating-point mantissas, or random sequences are not required.
- Initial resources, action effects, unlock relationships, and major economic balance are verified through gameplay scenarios and inspectable rules.
- If an implementation chooses to change numeric representation, it must demonstrate that meaningful gameplay outcomes are unchanged.
- Random tests use controlled random sources to reproduce failures, but production rules are not required to produce the same random sequence as the original browser version.

## 4. Concurrency and Persistence Focus — CONFIRMED / PROPOSED

At least the following repeatable scenarios must be established; cases marked PROPOSED validate the selected protocol rather than elevating proposed field names to user-confirmed requirements:

1. Two clients compete for resources simultaneously, and only Commands that can actually be afforded succeed;
2. **CONFIRMED state baseline**: Within the current process, concurrent and sequential idempotent retries of the same logical Command apply state changes at most once; verification must not merely count HTTP successes;
3. **PROPOSED `command_id` contract**: Retries with the same key and same arguments share the first terminal result; the same key with different arguments produces a Conflict without damaging the existing binding; retry behavior after rule rejection is consistent with the documentation;
4. After many Commands and ticks, the state equals the result of applying them in a well-defined order, with no lost update;
5. Simulation continues during saves without producing partially written snapshots;
6. Make changes after a snapshot and then simulate a crash; recovery restores the last successful snapshot and does not backfill offline progress;
7. After reconnecting, clients accept the recovered state and do not allow a pre-crash View to overwrite the new server state;
8. Simulation continues to advance when there are no browser or SSE connections.

## 5. UI Acceptance — CONFIRMED

- Verify semantic structure, key buttons, and the correctness of server state.
- Use two independent pages to verify shared state and concurrent actions.
- Screenshots may assist human or Agent observation of best effort visuals, but no strict pixel-perfect gate is used.
- Future different UIs must reuse the same public View/Command semantics rather than duplicate the rules.

## 6. Review and Merge Evidence

The Issue/PR process, independent Agent Review, blocking/non-blocking criteria, and automatic Merge mechanical gates are governed uniformly by `AGENTS.md` in the repository root. This file explains which test evidence can demonstrate the requirements; it does not create a separate conflicting process.


## 7. Numeric Representation Evidence — PROPOSED

The implementing Issues must distinguish exact representation behavior from approximation of a mathematical function. Zero error applies to exact operations on the selected representation; it is not a claim that logarithms, non-integer powers, or sine produce exact finite decimals. Python or another high-precision model may be an independent test oracle, never a production backend or played-game evidence. Documentation, crate metadata, and arithmetic proxies must not be reported as native crate execution, browser verification, or completed scenarios.

### Exact arithmetic and grammar

1. Test canonical `Amount` parse/format and mantissa round trips for zero, signed values, `10^-18`, values below one, `2^53+1`, `3e55+1`, and values beyond fixed 128-bit words. Reject every non-canonical class in `clients.md`, including trailing newline, negative zero, exponent syntax, trailing fractional zero, 19 fractional digits, and a JSON number where a string is required. Test the documented resource guard explicitly without treating it as a magnitude clamp.
2. Use an independent exact-rational reference for addition, subtraction, comparison, minimum/maximum, integer multiplication, directed quantization, and long randomized sequences. There is zero tolerance for these operations. Test that nonnegative and integral semantic constructors reject invalid signs/fractions and that fixed-width candidates never wrap or saturate.
3. Prove the ordinary conversion board: the `Wire >= 1` gate precedes `min(request, Wire)`; fractional automatic production and stock caps conserve the exact actual amount across Wire and all three ledgers; a full cap reaches exact zero by subtraction. Include `0.999` ordinary rejection, exact one, request above/below stock, and positive remainders.
4. Separately prove the CONFIRMED final Reject rule at ordinary full Wire, `0.25`, and `10^-18`: `min(1, Wire)` updates all three ledgers exactly, reaches zero, and increments the accepted counter once. Zero Wire changes nothing, and two contending final commands cannot recreate or double-consume Wire. Test that `Wire = 10^-18` satisfies the separate universal below-one predicate but does not satisfy exact-zero credits.
5. Exercise exact decimal constants and money vectors: `3e55`, `6e27`, `5e27`, `5e31`, `1e22`, stored AutoClipper cost `5 -> 6.1 -> 6.21`, `20 - 6.1 = 13.9`, and rejected `4.99` against stored cost `5`. Equal-cost affordability, first reveal, snapshots, and retries must not recompute level zero or lose a unit above `2^53`. Preserve source mill/cent/dollar floors at the correct stage rather than copying binary64 cent/mill loss.
6. Include exact signed Honor, Operations, negative/zero residues, unbounded `nextTrust`/Fibonacci comparisons, fractional populations, and positive sub-one stocks. No test may introduce an epsilon or silently clamp a negative or tiny valid value.

### Operation-specific quantization and approximation

1. For every rounded operation, record input domain, unit, direction, reference formula, and downstream comparison/transfer. Prove exact-threshold/ceil-grid equivalence only when evaluation is exact or approximation error cannot cross the boundary. Distinguish quantization of a computed request from the subsequent exact capped transfer.
2. Include adversarial small-ratio and large-denominator cases where truncating a positive factor to `10^-18` would erase it. M6 must provide reachable Power-ratio bounds or demonstrate its exact-rational/ordered alternative; M10 must do the same for tiny growth/loss. A test or argument that assumes `S/D == 0` implies `S == 0` across an unproved domain is invalid. Quantized accumulators need an explicit per-operation and sequence error bound.
3. Before the first transcendental consumer merges, run the selected deterministic evaluator on supported platforms against higher-precision tables for demand powers and Wire sine. Bind crate/version, license, MSRV, determinism and accuracy probes to that implementation HEAD; do not rely on this documentation PR as that evidence. Later owners extend tables to their own formulas and ranges.
4. Use both relative and absolute error as applicable. The candidate `2^-48` relative composite budget applies only to verified nonzero, non-cancellation domains. Cover exact zeros, `ln(1)=0`, invalid logarithm inputs, near-zero sine/cancellation, finite-output limits, and rejection of non-finite inputs/results. Show that no invalid result becomes JSON `null` or mutates state.
5. Verify integer floor/ceil/round outcomes wherever reference distance from the integer boundary exceeds the total absolute error. Identify any specifically permitted near-boundary `+/-1` cases instead of extrapolating sample margins to all inputs. Required special vectors include fresh Creativity speed `1`, Xavier and one-processor speed `0`, two-processor positive speed approximately `1.645271921560140886...`, the guarded zero-speed countdown, and gift `log10(10^5)*0.5 = 2.5 -> 3` (not ties-to-even `2`).
6. Test valid zero/one/fractional counts without imposing a global positive-population or `d >= 2` constraint. M8 must show zero-rate countdown display and pending-award behavior without spuriously resetting gift progress, gifts, or flags. M10 must test collision/grid movement effects on casualties before selecting combat geometry precision, preserve active battle state bit-exactly, and keep population loss/Deaths and signed Honor exact.

### Time, transport, and recovery

1. Fake-clock tests cover equivalent elapsed-time outcomes, fair Commands between batches of at most ten updates, saturated-debt health, startup with zero debt, and the 16 ms remainder sequence. For example, `30.004 s` of ordinary debt produces exactly 3,000 updates and carries 4 ms. Test both sides of Runtime #8's selected discontinuity bound: ordinary gaps retain debt; discontinuities reset the baseline without catch-up and expose the health event. No sleeps, production pause/step endpoint, or persisted lag debt substitutes for this evidence.
2. Snapshot round trips cover every implemented logical family, including tiny fractions, large integers beyond `2^53`, negative signed values, complete phase/remainder accumulators, RNG hex, latches, and active combat when present. Restored continuation equals uninterrupted continuation for the same legal inputs; it does not reproduce the original browser RNG stream and performs no downtime production. Restarts use a new `run_id` and no elapsed-debt baseline.
3. Inject unsupported versions, checksum mismatch, malformed JSON, missing/unknown/duplicate fields, wrong JSON primitives, non-canonical values, out-of-range integers, and cross-field violations. Each fails closed with the previous committed row intact. Prove first numeric snapshot version 1 never accepts f64 ledgers and later added fields use explicit retained-progress migrations. SQLite has no `REAL` game-value path.
4. API schema tests prove static `Amount` strings and safe bounded integers. Reject arbitrary Amount/time/resource commands, and for integer controls reject `1.0`, `1e0`, string, boolean, fraction, and overflow inputs before retry binding or mutation. Argument-free deposit/withdraw still acts only on server balances; batch/slider controls remain within their typed ranges.
5. SSE/reconnect and browser/Agent tests preserve strings exactly for `2^53+1`, `3e55+1`, `10^-18`, zero, and signed Honor. Native-browser tests exercise string/`BigInt` parsing, comparison, ceiling, and digit-exact display and check that `Number`/`parseFloat` is not used for authority or displayed Amount values. A visual-only bar projection cannot affect state or numeric text.
6. Long legal-state sequences mix Commands, production, purchases, ticks, retries, saves, and restarts under controlled RNG. Compare a serial exact-reference model for conservation, nonnegative/domain invariants, complete atomic state, and absence of duplicate application. Tests never call a collection or rendering helper that drops hidden progression/RNG/latch state.

All 45 catalog scenarios retain their existing design status until their real owning implementations execute them. This requirements PR supplies future test obligations, not native runtime or gameplay evidence.
