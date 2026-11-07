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
