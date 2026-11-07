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
