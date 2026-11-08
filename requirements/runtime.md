# Runtime, Concurrency and Persistence

## 1. Authoritative State — CONFIRMED

- The in-memory game state on the server is the sole authoritative runtime state.
- Browsers and Agents may only submit intent; they cannot submit "computed new resource totals" for the server to trust.
- Every Command is revalidated against the current state when it is actually executed, rather than trusting whether a button is disabled.
- Client observations may be stale; staleness alone is not a system error.
- A Command that remains legal under the current state must not be rejected categorically merely because the observed version is stale.
- Global time must not be rolled back because of network concurrency or multiple clients.

## 2. Real-Time Simulation — CONFIRMED

- The world advances continuously whenever the game server is running normally.
- Advancement is unaffected by whether any web page, SSE connection, or Agent is online.
- The world does not pause while a Human or Agent thinks, and no Agent time budget is provided.
- There are no turns, no "advance one step after receiving a Command" model, and no public interface for players to step the game manually.
- Tests may drive tick advancement in the pure engine, but that is not a production API or player capability.
- A server crash or downtime is not part of normal online real-time operation; recovery rules are described below.

## 3. Concurrent Command Semantics — CONFIRMED

Any number of clients may issue network requests to the same game simultaneously, but state changes must have a well-defined order.

The following must be guaranteed:

- No lost updates;
- Validation and state application are atomic;
- Multiple requests cannot use the same stale state to consume the same resource repeatedly;
- Two Commands that are both legal may both execute and are not mutually exclusive merely because they come from different clients;
- When resources are sufficient for only one purchase, two purchases must not both succeed;
- The first execution result of a Command reflects the state at the time it is actually executed;
- During the current process lifetime, idempotent retries of the same logical Command must not apply state changes more than once; the crash recovery window is covered by Section 7;
- Simulation ticks and Commands must not concurrently modify the same state without constraints.

Operations may be chaotic, but state updates must not be.

### Recommended Implementation — PROPOSED

- Each game has an explicit `GameRuntime` that owns its `GameState`, avoiding mutable module-level global state; HTTP handlers do not modify GameState directly.
- Each Runtime uses one command queue and a single writer to serialize Commands and ticks.
- Command deduplication, subscriptions, and persistence internally use the game ID as their boundary; V1 only wires up `default`, and this does not authorize building a multi-instance Registry or management features.
- The first version is single-process and uses neither distributed locks nor a cross-process actor framework.

### `command_id` Retry Contract — PROPOSED

A client-generated `command_id` is recommended to express logical Command identity and implement the runtime idempotence requirement above; see `clients.md` for the specific result, conflict, and testing language. The specific fields and their binding to terminal results are PROPOSED and do not change the CONFIRMED state-application baseline in the preceding section.

## 4. Current Instance Model — CONFIRMED

- The first version runs only one game, with internal ID `default`.
- Users and Agents do not need to select an instance; external requests automatically map to `default`.
- Opening a new page does not create or reset a game.
- No product functionality is provided to create, list, delete, or switch among multiple instances.
- The current sole game is uniformly identified internally by `game_id = default`.

### Explicit Non-Goals — CONFIRMED

The current scope does not include GameRegistry multi-instance management, a lobby, management UI for multiple simulation loops, or distributed instance scheduling.

## 5. Technology Stack — CONFIRMED

- Rust stable
- Axum
- Tokio
- Serde
- SQLite
- SSE for server-to-client state streaming
- Native HTML, CSS, and JavaScript, with no frontend build chain in the first version

Python may be used for Agent clients, research, or analysis, but a second authoritative game server in Python will not be built.

## 6. Online Persistence — CONFIRMED

- Persist periodic full snapshots; zero data loss is not a goal.
- The initial default save interval is **30 seconds**; this is an infrastructure parameter for this project, not a value from the original game.
- A snapshot must represent a logically consistent state and must not be saved partially in a way that leaves resource values inconsistent with one another.
- A snapshot must contain all state needed to continue simulation, including internal timers, accumulators, random state, and progression, not merely UI numbers.
- SQLite writes must use transactions to guarantee snapshot atomicity.
- A best effort additional save may be performed during normal shutdown, but this is not a crash guarantee.
- Loss of approximately the last save interval's worth of progress is acceptable during operation.

### Save Scheduling Implementation — PROPOSED

Saving must not disrupt online simulation by holding the game writer for an extended period or performing uncontrolled blocking I/O. The specific snapshot capture and asynchronous write mechanism will be determined in the corresponding engineering Issue and verified with tests.

## 7. Crash and Recovery — CONFIRMED

- On startup, load the last successfully committed `default` snapshot; on first startup, create the initial game.
- Resume real-time operation after restoring from a snapshot.
- Do not backfill production, sales, or other progress for the downtime.
- Recovery may roll back Commands and state that had not yet been saved.
- Preservation of deduplication records across crashes is not guaranteed; after reconnecting, clients must reread server state and must not assume that pre-crash commits remain valid.

The CONFIRMED runtime idempotence above does not include crash recovery within the unpersisted window and does not guarantee exactly-once behavior across crashes. If `command_id` is adopted, its result binding is likewise not guaranteed to survive that window.

### Revision and Recovery — PROPOSED

Use an increasing `revision` to identify state order within a single server run, and generate a `run_id` for each process run:

- Within the same `run_id`, clients must not allow a late lower revision to overwrite a higher revision;
- When `run_id` changes, clients must first accept the recovered full snapshot before comparing revisions again.

The specific fields and encoding will be fixed by the API Issue.

## 8. Subsequent Implementation Details — PROPOSED / OPEN

Specific tick constants, scheduling lag handling, numeric representation, state serialization schema, and SQLite file layout will be defined in the corresponding design Issues. They must not use vague product semantics as a reason to change the CONFIRMED behavior of "continuous online advancement, no backfill after a crash".

### Numeric Representation — PROPOSED

This proposal defines the cross-milestone representation boundary. It does not claim that irrational functions have exact finite values, select an unverified crate, or authorize another gameplay deviation. Each owning implementation Issue must state its fields' concrete types, units, ranges, rounding points, serialized forms, and approximation evidence before adding them to authoritative state.

#### Exact state families and the field-domain matrix

`Amount` is a signed exact decimal fixed-point value `m * 10^-18`, where `m` is an arbitrary-precision integer. It has no game-value magnitude cap: `2^53+1`, values beyond `u128`, and the exact `3e55` universe total are representable together with one additional unit. Addition, subtraction, comparison, minimum, maximum, and multiplication by an integer are exact. Semantic constructors distinguish signed, nonnegative, and integral values; a nonnegative ledger cannot become negative through an unchecked conversion. Multiplication or division that leaves the grid requires an explicit rounding mode and returns an error on an invalid domain instead of producing a non-finite value. Runtime #8 chooses and locks the actual backend only after checking current API, license, MSRV, correctness, and measured behavior; this proposal fixes the semantic contract, not a crate/version.

Checked native integers are appropriate only for structural fields with a documented source bound or a checked rate-times-horizon bound. They never wrap, saturate, or silently widen a lossy transport value. Populations, demand, Fibonacci/`nextTrust` targets, Honor, fractional facility levels, and other values that can exceed a fixed word or require fractions or signedness use `Amount` or a more specific semantic type, not a blanket `u64`/`i128`. A transient exact rational numerator/denominator may be used to preserve a ratio until a defined request or comparison; it is not required to become a second persistent economic encoding.

| Field family | Authoritative representation and unit | Operation, rounding, and transport requirements |
|---|---|---|
| Three clip ledgers, Wire/supply, Available/Acquired/Found/Total Matter | Nonnegative `Amount`; Total Matter is an exact decimal constant | Capped transfers, equal clip-ledger increments, exhaustion comparisons, and refunds are exact on the grid. No epsilon or zero clamp. Canonical strings on View/SSE/snapshot. |
| Funds, dollar prices/costs/bills, margin, Wire base/quote, investment cash, Yomi, and signed Honor | `Amount`, with nonnegative or integral restrictions where the rule requires them; Honor remains signed | Charge the stored current price, preserve mill/cent/dollar source floors in their stated units and order, and keep exact affordability, grants, losses, and negative values. Canonical strings. |
| Demand, multipliers, sale size, stored derived rates, standard/temporary Ops and fade, Creativity/counter/speed | Semantic `Amount` values except separately bounded integer counters | Exact decimal factors remain exact; irrational evaluation follows the approximation contract below. Division by zero is a guarded domain case, never serialized infinity. |
| Quantum phase, chip waves, signed sinusoidal sums, overflow `Q/B/D` | Integer quantum/update phase; `Amount` for fixed-scale clock and accountable Ops/accumulators; transient evaluator outputs follow explicit conversion | Evaluate sine deterministically, bound the sum before `ceil`, and keep `ceil(Q/D)` exact on its defined positive domain. Restore phase/accumulator state without binary64 accumulated clock drift. |
| Investment bankroll, stock prices/amounts/totals/profit, upgrade thresholds/costs, risk/strategy choices and tournament scores | Integral `Amount` for stock/cash/profit/Yomi/costs; `Amount` for thresholds; checked bounded counts and enums | Preserve exact integer budget/reserve arithmetic, deposit whole-dollar floor, signed profit, automatic stock progression, and source upgrade floors. No client-supplied balance or arbitrary trade size. |
| Human/probe Trust and traits, Processor/Memory, project uses, offers, strategy/chip selection, AutoClipper/MegaClipper/Marketing and structural facility levels, tournament payoff counters | Checked signed/native integers only inside proved bounds; enumerations for closed choices; integral `Amount` for unbounded thresholds/costs | Arithmetic is checked. If a counter has no sound fixed-word bound, use an integral `Amount` instead. JSON integers only within the safe bound in `clients.md`. |
| `nextTrust`, Fibonacci terms, unbounded populations, demand, cumulative production/loss/grant totals | Integral or nonnegative `Amount` as appropriate | Exact addition and comparison beyond fixed words; canonical decimal strings rather than JSON numbers. |
| Fixed simulation time and process cadence | Checked `u64` update counter at 10 ms, small integer phase counters and integer-nanosecond lag debt | No floating time. Logical update/phase/remainder state is snapshotted; process lag debt is not. All transported integers stay within `2^53-1` or use an exact string semantic type. |
| Fractional probe/drifter populations, descendants, spawn/hazard/partial accumulators, probe-built fractional facilities | Nonnegative `Amount`; loss/transfer identities remain exact at the chosen operation boundary | Do not floor populations to whole individuals or erase a positive remainder with an epsilon. Growth/loss approximation and quantization require reachable-domain proof. |
| Terrestrial Power supply `S`, demand `D`, stored energy `B`, capacity, `powMod`, Momentum, and derived factors | Exact `Amount` state; a ratio may remain an exact transient rational until application | The CONFIRMED partial-battery Power deviation and its ordinary surrounding Power rules are unchanged. Quantizing `S/D` or `(S+B)/D` is not universally safe; see the factor caveat below. |
| Swarm drone count, Work/Think setting, gifts, gift bits/rate/countdown, boredom/disorganization | Integral `Amount` or a checked counter only with a proof; `Amount` for accumulated fractional state | `ln(1)=0`; zero/one/fractional valid world counts are not globally rejected. An undefined derived countdown may be `null`, without resetting underlying progress/gifts. |
| Combat populations, `unitSize`, casualties, Deaths, battle clocks/names/latches | Exact `Amount` for populations/transfers and checked bounded counters for structural fields | Each side's loss and cumulative totals use that side's value with no shared-variable mutation or zero-clamped casualty loss. Honor changes remain exact and signed. |
| Combat positions, velocities, grid membership, and frame phase | A finite, bounded continuous representation selected by the M10 owner after outcome-coupling verification | These values help determine encounters and casualties; they are not automatically render-only. The active battle must round-trip bit-exactly, and the owner must bound collision/outcome effects before choosing an approximate representation. |
| Ending stages, dismantle phase, accepted-final-conversion count, prestige U/S | Checked small/native integers with documented bounds | Final Reject consumes `min(1, Wire)` exactly and updates all three clip ledgers by that same amount; the separate exact-zero credit gate is unchanged. |
| RNG state | Fixed-width words and a specified deterministic game PRNG | Serialize as lowercase hexadecimal, restore game-determined continuation, and never consume RNG while rendering View/clock data. Original browser stream equality is not promised. |
| `run_id`, `revision`, schema/snapshot versions, retry identity | Opaque `run_id` string, checked `revision <= 2^53-1`, bounded integer versions and retry metadata | Checked increments and conversions only. Process retry records and lag debt are excluded from game snapshots. |

The design constants `3e55`, `6e27`, `5e27`, `5e31`, and `1e22` are exact decimal literals, not the nearest source-binary64 values. The initial stored AutoClipper price is exactly `5`; successful purchases store successors `6.1`, then `6.21`, without evaluating the successor formula at level zero on restore. UI grouping, decimal places, suffixes, and progress-bar widths are presentation only and do not change these stored meanings.

#### Quantization is an operation-local proof, not a global tolerance

Exact ledger addition/subtraction, comparisons, whole transfers, integer multiplication, and source `floor`/`ceil`/`round` in their stated units must not pass through binary64. Source `Math.round` rounds halves toward positive infinity, including for signed intermediate values. For the nonnegative gift example, `log10(10^5) * 0.5 = 2.5` therefore produces `3`, not ties-to-even `2`.

A stored computed price or `>=` threshold may round up to the `10^-18` grid when that preserves the specified policy. For an **exactly computed** formula value, a grid ledger satisfies `ledger >= formula` if and only if it satisfies `ledger >= ceil_grid(formula)`. That equivalence must not be claimed when approximation error can cross the same grid boundary; the owner must either preserve the exact comparison or specify and test the near-boundary result. Other comparison directions require their own direction proof.

For a production, consumption, growth, or loss formula whose final accountable request is not grid-representable, the default is to quantize that **computed request** toward zero at the stated boundary, then apply `min(request, stock)`, and only then perform the exact conserved transfer. Do not truncate the conserved transfer itself after the cap. Whole-number transfers are never quantized. Accumulator increments follow the same operation-specific proof rather than a blanket rule.

This policy has a required reachability qualification. Truncating `S/D`, `(S+B)/D`, a tiny growth factor, or another positive intermediate to `10^-18` can produce zero when the exact value is below the grid, and can materially alter production at sufficiently large denominators or populations. It is therefore incorrect to assert globally that the stored factor is zero if and only if `S == 0`. Before fixing its state schema, M6 must prove its reachable ratio bounds or retain an exact rational/ordered calculation through comparison and final request construction. M10 owes the equivalent proof for tiny growth/loss rates. Other owners must show that quantization does not erase a gameplay-significant positive rate or decision; where no proof exists, they must refine the operation precision through their requirements process rather than call the difference a third approved deviation. Exact conservation still applies to whatever actual request is accepted, and a positive stock as small as `10^-18` remains nonzero until a rule consumes it.

Every quantized operation documents its per-update absolute or relative error and its accumulation over the owner's tested sequence. No universal epsilon answers approximate equality, affordability, exhaustion, or exact-zero questions.

#### Deterministic approximation and domain guards

Non-integer powers, logarithms, and sine use one deterministic, platform-independent binary64 evaluator. The first real consumer is the owning M1-G02/#15 implementation for demand powers and Wire sine; later owners reuse that contract. That implementation must select and lock a real dependency/version only after checking its API, license, MSRV, determinism, accuracy, and experiments. This requirements proposal does not preselect a crate or treat documentation/metadata as native execution evidence.

For each formula, the owner defines valid inputs, deterministic correctly rounded or exact-dyadic conversion of exact arguments, function composition, finite output range, and a verified error bound against higher-precision references. The candidate default for a valid nonzero composite result outside cancellation/near-zero regions is relative error at most `2^-48`, plus the subsequent explicit grid quantization. Exact points and near-zero regions need separate rules: `ln(1)=0`, logarithms require positive inputs, sine at exact zero is zero, and a nonzero relative bound is meaningless at an exact zero. Sine and formulas with cancellation require an absolute output-error bound that is sufficient for the subsequent comparison or rounding decision. Inputs and results that are non-finite or outside the verified domain are rejected as invariant/domain errors; they are never clamped and cannot silently serialize as `null`.

An integer `floor`/`ceil`/`round` of an approximate result must equal the higher-precision reference integer wherever the reference's distance from the rounding boundary exceeds the total absolute error. A specific owner may permit a `+/-1` result only inside that documented near-boundary region; it must not generalize sampled margins into a theorem for unbounded inputs. Exact special cases are constructed explicitly where they affect ties or progression: fresh Creativity speed is `1`, Xavier and one-processor recomputation produce `0`, two processors produce the positive approximation of `log10(P)*P^1.1 + P - 1`, and exact powers of ten are recognized for gift rounding.

A division-by-zero comparison may be reordered only under a proved domain. For Creativity, with nonnegative effective speed `ss`, the source countdown can use the guarded form `ss > 0 && counter*ss >= 400`; zero speed remains pending rather than dividing. The ordinary/fractional award branch is separately selected by its source threshold. No global `d >= 2` or positive-population invariant is invented. Valid zero, one, and fractional counts remain valid. M8 must classify zero/one/pending-award Swarm behavior from source intent before implementing gift edge cases; a `null` zero-rate view cannot reset gifts, gift bits, flags, or tiny remainders.

| Formula / first owner | Domain and exact endpoints | Required approximation and decision evidence |
|---|---|---|
| M1-G02 sale size `floor(0.7 * demand^1.15)` | Exact positive demand and a documented finite range | Candidate nonzero relative budget `2^-48`; prove floor equality outside the total-error integer margin and specify any permitted near-boundary `+/-1`. |
| M1-G02 Wire quote `ceil(base + 6*sin(counter))` | Exact `Amount` base and integer counter; finite quote | Bound sine absolutely, including near zero and periodic extrema; prove the source ceiling outside the integer margin and reject non-finite results. |
| M2 Creativity `log10(P)*P^1.1 + P - 1` and guarded counter/awards | Integer `P >= 1`; fresh speed `1`, `P=1` and Xavier speed `0` exact; `P=2` approximately `1.645271921560140886` | Candidate relative budget only where the composite result is separated from zero/cancellation; explicit `ss > 0` guard and exact grid/branch behavior outside it. |
| M3 `3^3.5/1000` fade and quantum signed sine sum | Exact integer phase/counters and bounded active-chip state | Evaluate constants once under a fixed rule, quantize at a named boundary, and bound the summed absolute error before `Q = ceil(360*sum)` and exact `ceil(Q/D)`. |
| M4 investment upgrade floor; M10 probe-Trust/hazard/drift powers | Nonnegative integer levels/traits and exact decimal coefficients; nonnegative populations | Use per-owner verified ranges and integer margins, then explicit ceil/truncate/floor policy; do not turn sampled margins into unbounded guarantees or erase tiny populations. |
| M6 facility prices `(L+1)^p*c` and Power ratios | Valid construction levels; `Amount` `S/D/B` with `D > 0` only where the source division is defined | Prices use per-level approximation plus explicit ceil-grid policy without unsupported exact-comparator claims. Power ratios stay exact-rational/ordered unless quantization has a reachable-domain proof. |
| M8 `ln(d)*Think` gift accumulation and `log10(d)*Think` award | Guard by actual Active/domain state; `ln(1)=0`, slider zero has no positive rate, and no global `d >= 2` invariant | Bound nonzero logarithm accumulation, recognize exact powers of ten for gift halves, preserve source half-toward-positive-infinity behavior, and classify zero/one/pending-award source cases before implementation. |
| M10 combat movement/grid/casualty coupling | Finite positions/velocities/grid/phase with source bounds and active RNG state | No default render-only exemption. Compare deterministic representations on collision/casualty sequences, set outcome/error limits, and snapshot the selected state bit-exactly. |

Normalized logical state contains no NaN or infinity. Rejecting an invalid evaluator result does not authorize deleting an otherwise valid snapshot or game. Display-only `null` is reserved for an explicitly undefined derived value such as a zero-rate countdown.

#### Snapshot and authoritative encoding boundary

The first numeric `snapshot_version = 1` must already encode every `Amount` as the canonical decimal string in `clients.md`; no f64-ledger era or guessed migration is permitted. Later milestones version newly added fields with explicit tested migrations. A complete snapshot preserves fractional populations, timers, phase/remainder accumulators, RNG, latches, progression/prestige, and active battle state; process-local lag debt is deliberately excluded.

The payload is deterministic canonical JSON stored as SQLite `TEXT`; game values do not occupy SQLite `REAL` or numeric columns. Revision/version metadata use checked representable `INTEGER` conversions. Unsupported versions, checksum mismatch, missing/unknown fields, wrong primitive types, non-canonical numbers, and cross-field invariant failures reject the candidate without resetting it. A failed restore or replacement leaves the last good committed row intact, creates no automatic world deletion or offline advancement, and starts no replacement default world.

### Simulation Time Base — PROPOSED

The simulation advances in fixed 10 ms updates. This quantum is semantic, not a cosmetic tuning knob: automatic-request gates, partial-stock rules, per-update accumulators, and progression thresholds depend on it. Slower 100 ms, 1 s, and 2.5 s cadences use integer phase counters; the 16 ms combat cadence uses an exact integer remainder accumulator. Original independent JavaScript interval drift and background throttling are not reproduced.

Online lag is integer-nanosecond debt. One writer turn executes at most ten updates and then fairly services queued Commands. Ordinary debt is never discarded; sustained overload exposes degraded health rather than silently changing game time. Logical cadence state is snapshotted, while lag debt itself is process-local and never serialized because restoring it would manufacture offline advancement.

Rust host clocks differ on whether suspend counts as elapsed time. Runtime #8 must select and test one fixed host-discontinuity bound with a fake clock. A single observed gap above that bound resets the clock baseline without catch-up and records a health event; smaller gaps retain debt. A candidate default of 60 seconds is PROPOSED input for #8, not an approved constant in this document. Restart generates a fresh `run_id`, restores the latest good logical state and accumulator/RNG positions, and begins with zero lag debt and no downtime production. Browser/SSE/Agent disconnection never pauses the world, and no public Agent, UI, operator, pause, step, arbitrary-resource, or arbitrary-time command is added.
