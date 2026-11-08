# paperclip-game

A server-authoritative, continuously running real-time reimplementation of Universal Paperclips.

## Documentation

- [Product and engineering requirements](requirements/README.md)
- [Agent development workflow](AGENTS.md)

## Run the current API service

```sh
cargo build --locked
target/debug/paperclip-game
```

The default listener is `127.0.0.1:3000`. Only these process overrides are accepted:

```sh
target/debug/paperclip-game \
  --listen-addr 127.0.0.1:3000 \
  --database-path data/paperclip.sqlite3
```

Invalid options, nonnumeric listener addresses, and missing option values exit with a configuration error. Listener addresses are numeric IP addresses and ports; hostnames are not resolved. On Unix, `SIGINT` and `SIGTERM` trigger graceful HTTP/runtime shutdown. Graceful stop closes runtime admission, drains every already accepted command through the ordinary bounded writer turns, and joins tracked terminal-result publication before returning. Issue #10 then offers the final coherent writer view to the bounded best-effort persistence worker and joins it. This is an ordinary-stop persistence guarantee, not crash zero-loss or cross-process exactly-once behavior.

`--database-path` selects the real SQLite persistence file (default `data/paperclip.sqlite3`). A nonexistent or empty file, with none of the SQLite `-wal`, `-shm`, or `-journal` sidecars present, initializes schema version 1, WAL, `synchronous=FULL`, and one committed `default` full-snapshot row. Known sidecars already present at such a location cause sanitized startup failure before any creation or mutation, including when they are zero-length, dangling symlinks, or directories. Before an existing database is opened writable, its main database and available WAL/SHM/journal files are copied into private owner-writable temporary storage. Only SQLite internal recovery on that copy, read-only commands, and strict row validation happen before the source can be opened writable; genuine hot rollback journals therefore recover the previous complete committed row without mutating rejected source files. Valid existing rows and actual SQLite-emitted sidecars still restore normally. A valid existing row restores the complete current logical state, revision, exact `Amount` strings, clock/phase/remainder state, and RNG stream. Each process still generates a new opaque `run_id`, starts with zero lag debt and empty retry records, and performs no offline production, sales, timer, or RNG catch-up. Existing invalid or unsupported data fails startup before the listener; it is never silently reset, quarantined, deleted, or overwritten.

The runtime observes coherent writer views and captures approximately every 30 logical seconds (3,000 fixed 10 ms updates), then every normal shutdown performs a final best-effort capture after the accepted-command/publication drain. A single worker outside the game writer owns SQLite work: at most one in-flight write plus one replaceable latest full snapshot. Busy/error retries use a bounded busy timeout, three attempts, and bounded exponential backoff. Each attempted row replacement is atomic and contains deterministic snapshot-v1 JSON `TEXT`, checked integer revision/sequence metadata, and a SHA-256 checksum. Normal-stop capture is not a crash zero-loss claim; after a crash, changes after the latest committed snapshot may roll back. Clients must resynchronize after restart and have no cross-process idempotency guarantee.

## HTTP contract

### GET `/`

Serves the semantic native browser page for the same default game. Its ES modules, stylesheet, and #11 synchronizer are compile-time allowlisted assets under `/static/`; no public filesystem directory, user-supplied asset path, framework build, or server-side Python renderer is involved. HTML, CSS, and JavaScript receive their corresponding UTF-8 MIME types and `X-Content-Type-Options: nosniff`.

The current page exposes only the genuinely implemented Make Paperclip command. Native Enter/Space activation, pending/rejected/conflict/ambiguous-outcome feedback, a polite command status, and full-View rendering do not create a client economy. Ambiguous manual retries retain the exact same opaque command ID and body. Resources render only after the #11 synchronizer accepts complete Views. Business, Wire, and current AutoClipper/computing fields are readouts only; unimplemented feature controls and actor/world/reset/debug selectors remain absent.

### GET `/api/game/view`

Returns a complete, statically typed public `GameView`. Its top-level fields are:

- `schema_version`: JSON integer `1`;
- `run_id`: opaque 32-character process identifier;
- `revision`: checked JSON integer from zero through `2^53-1`;
- `clock`: logical update/cadence counters;
- `game`: all currently implemented public M1 production state.

Every `Amount` is serialized as a canonical ASCII decimal JSON string, preserving `10^-18`, values beyond `2^53`, and larger exact values without a JSON float. Views are cloned projections of one runtime snapshot. They contain no RNG state, retry records, process lag/health, database path, or mutable references. GET does not advance the logical clock, execute a command, grant production, or draw random numbers.

### GET `/api/game/stream`

Returns `text/event-stream` with `Cache-Control: no-store, no-transform`. Every `game_view` event contains one complete `GameView` in the same statically typed JSON encoding as GET `/api/game/view`. Its SSE `id` is `<run_id>:<revision>`. There are no JSON patches, retained replay events, actor/game selectors, WebSockets, command inputs, or heartbeat-driven simulation.

Every new or reconnected HTTP connection immediately receives a full current baseline before later updates. The server subscribes to the writer's existing watch before capturing that baseline, avoiding both a capture gap and an accidental repeat of the initial frame. Later writer observations may coalesce to the latest complete view. Each connection has one observer task and a bounded queue of **8 complete immutable JSON frames**, in addition to the watch's single latest source slot. The observer uses `try_send`, never waits for client capacity, and disconnects that stream when its queue is full or its HTTP receiver closes. A slow or dropped observer therefore cannot backpressure writer ticks, legal commands, snapshot capture, or lifecycle processing. Reconnection is the resynchronization policy after lag; it obtains a fresh full baseline rather than replaying a gap.

`Last-Event-ID` is accepted only as opaque reconnect metadata supplied by normal clients. It is not a retained-history cursor, replay request, exactly-once command identity, resource-reset instruction, actor credential, or game control. Initial/baseline behavior is identical without it, with a previous ID, or with an arbitrary value. Arrival order across independent SSE/GET connections is not a global order.

The native synchronizer is exported as `paperclip_game::view_sync::ViewSynchronizer`; the browser equivalent and exact `Amount` helpers are available from `GET /static/stream.js`. Their local ordering contract is:

- Call `openStream()` for every physical connection, including an EventSource `open` after automatic reconnect. Only the most recently opened local stream generation may publish. Older streams cannot re-adopt a run.
- GET tokens belong to the local run epoch in which the request was issued. A response delayed across a new-run baseline is stale.
- Within one run, lower revisions are ignored, higher revisions apply, and equal revisions are presentation-idempotent without another game effect.
- Only an initial stream frame or current-epoch GET may adopt a different `run_id`. That one complete baseline applies even when recovery makes its revision lower than the cached run's revision. It invalidates earlier stream/GET tokens; subsequent frames use same-run ordering again. A non-initial run switch on one connection is invalid.
- Browser views are validated as complete static objects before acceptance. `Amount` strings remain strings or exact signed 18-digit-scaled `BigInt` values for comparison, arithmetic, ceiling, and display. JavaScript `Number`/`parseFloat` conversion of an Amount is not used.

The external `SIGINT`/`SIGTERM` shutdown future first notifies this live host-owned stream state. All observer tasks close and active responses drain at most their already queued complete frames before terminating. The existing accepted-command drain, retry publication join, final coherent snapshot, and SQLite worker join then run in their original order. No public stream-shutdown or debug endpoint exists from this internal state.

### GET `/api/health/live`

While the HTTP service is serving, returns 200 with exactly `{ "status": "ok" }`. Failure of snapshot readiness does not pause, rewind, recreate, or stop the authoritative game. Other HTTP methods receive 405 and do not mutate game state.

### GET `/api/health/ready`

Returns a fixed, statically typed JSON projection with these fields: `live`, `ready`, `phase`, `last_committed_revision`, `last_committed_sequence`, `latest_captured_revision`, `latest_captured_sequence`, `pending_snapshot_count`, `write_in_progress`, `current_attempt`, `consecutive_failures`, `snapshot_overdue`, and `last_failure_code`. Revision/sequence counters are nullable checked safe JSON integers; absent values are `null`, not a fabricated zero. `pending_snapshot_count` is zero or one for the coalesced pending slot and excludes the single in-flight write. Failure codes are closed enum strings, never free-form backend messages.

A healthy initialized persistence pipeline returns 200 with `ready=true`. A post-start write error or overdue checkpoint returns 503 with `ready=false`, while the same live runtime continues ticks and commands. A valid commit can restore 200. `snapshot_overdue` is based on the runtime's published logical update count: no committed checkpoint for more than two snapshot intervals (6,000 updates). Host suspension, downtime, and wall-clock jumps do not manufacture logical progress. Pure transport tests without a configured store use the explicit `unconfigured` phase and never represent a validated production restore. These routes expose no actor/world selector, resource input, SQL, file path, payload, RNG, retry record, or private error string.

### POST `/api/game/commands`

The current closed action enum contains only `make_paperclip`, which takes an empty argument object:

```json
{
  "command_id": "client-generated-id",
  "type": "make_paperclip",
  "arguments": {}
}
```

A valid command consumes exactly one Wire at actual writer execution and increments lifetime clips, unsold clips, and unused clips by one. If less than one Wire remains, the writer returns a rule rejection without mutating resources or revision. Clients cannot supply a clip count, Amount, resource total, computed cost, actor/world selector, game ID, observed revision, time, seed, pause/debug control, or arbitrary setter. Stale observations alone do not reject a legal command.

#### Input bounds and normalization

- The HTTP request-body allocation limit is **4,096 bytes**. This is a corruption/allocation guard, not a game-value cap.
- `command_id` is a required, nonempty JSON string of at most **128 UTF-8 bytes**. Control characters are rejected. Escaped and literal forms of the same decoded string identify the same key.
- IDs are opaque: no trimming, case folding, Unicode normalization, client-actor interpretation, or hash truncation is applied.
- All envelope fields are required. Unknown or duplicate envelope fields, wrong JSON primitives, malformed JSON, invalid UTF-8, duplicate object keys at any arguments depth, and nonempty `make_paperclip` arguments are structural errors.
- JSON object order and insignificant whitespace do not change the normalized command payload. The closed `make_paperclip` action has no optional or defaulted numeric arguments.

Malformed input never allocates an internal execution ID, reserves a retry key, or mutates game state. The only internal numeric IDs are separately allocated by checked process-local monotonic allocation.

#### HTTP results and process-lifetime retry behavior

| Meaning | HTTP status | Body shape |
|---|---:|---|
| Command applied | 200 | `{ "status": "applied", "revision": N }` |
| Execution-time game-rule rejection | 422 | `{ "status": "rule_rejected", "revision": N, "reason": "insufficient_wire" }` |
| Malformed/invalid command structure | 400 | `{ "status": "schema_error", "reason": "..." }` |
| Unsupported action for a new key | 404 | `{ "status": "unknown_command" }` |
| Existing key with a different normalized payload | 409 | `{ "status": "conflict" }` |
| Request body above 4,096 bytes | 413 | `{ "status": "schema_error", "reason": "body_too_large" }` |
| Bounded queue/runtime unavailable | 503 | `{ "status": "unavailable", "reason": "..." }` |

The exact decoded ID string is the process-lifetime retry map key. Equal normalized payloads with one key have one pending owner; concurrent callers wait for that same writer application. Once terminal, the original HTTP status and serialized body are retained and replayed unchanged even after later ticks or other commands. Success and rule rejection are both terminal. There is no TTL/LRU eviction during the process.

A different normalized payload using an existing key receives 409 while pending and after terminal. It does not overwrite the original binding or execute. For an existing binding, a structurally valid but unsupported action therefore conflicts (409); for a new key the same action is `unknown_command` (404). A structurally invalid new payload is rejected (400) before key lookup, leaving any original binding intact without reinterpretation as a new action.

Once the runtime queue accepts a command, its writer wait runs independently of the HTTP response future. A disconnect may discard the response but cannot cancel the accepted operation or cause its retry to apply twice. Queue rejection before acceptance does not bind the key. Retry records and bindings are process-local only; no exactly-once guarantee crosses a crash or restart.

## Verification

```sh
cargo fmt --check
cargo check --locked --all-targets
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --all-targets
cargo build --locked
python3 -B scripts/check_api_process.py target/debug/paperclip-game --repo .
python3 -B scripts/check_persistence_process.py target/debug/paperclip-game
python3 -B scripts/check_browser_stream.py target/debug/paperclip-game --require-browser
python3 -B scripts/run_browser_tests.py target/debug/paperclip-game --require-browser
```

The Rust suites include duplicate/unknown-field and primitive negative tables, real HTTP client/socket/SSE checks, browser-compatible native synchronization models, deterministic real-writer gates for in-flight coalescing and conflicts, terminal success/rejection replay, final-stock contention, accepted disconnect behavior, exact Amount view fixtures, independent-client writes, strict snapshot/clock/RNG checks, real SQLite rollback/busy/coalescing failures, per-sidecar fail-closed initialization, fake-time 30-second publication, and logical-clock readiness recovery. Real process recovery races captured pre-crash views against a lower-revision recovered baseline. The browser checker executes the new native EventSource module in an isolated Chrome/Chromium profile and covers same-run reconnect, crash/recovery resync, exact BigInt operations, and known-bad frames/sources; it does not read a personal browser profile or execute captured upstream JavaScript. A Unix-only fixture checks actual permission denial under a verified non-root runtime UID, restores permissions through a guard, and compares the original files and complete old row; root or another privilege bypass fails that precondition rather than being counted as an injected fault. A separate real child is killed after the production transaction's UPSERT but before COMMIT, and recovery/recommit proves old then new complete rows. The API process checker starts the default and explicit listeners, performs 1,000 distinct legal writes, reaches a real stock-exhaustion rejection, checks terminal replay/conflict and health, verifies SSE reconnect plus `SIGTERM` with an active stream, and protects existing-data sentinels. The persistence process checker injects a real SQLite busy transaction, observes 503 while game progress continues, requires a valid commit to restore 200, rejects corrupt startup without source changes, and uses actual process `kill`/`wait` for bounded rollback and repeated-restart evidence.

## Current limits

Issue #10 implements schema-v1 snapshots and observational persistence health. Later logical fields require explicit versioned migrations in the same PR that introduces those fields; no later-game state, unrestricted save/debug command, multi-instance registry, per-actor database, automated production and other feature packs (#14-#16), or full playable integration (#17) is implemented by this issue. The native UI does not advertise those future feature panels or claim complete M1 gameplay. Unsupported actions are never accepted placeholders.
