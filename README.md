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

Invalid options, nonnumeric listener addresses, and missing option values exit with a configuration error. Listener addresses are numeric IP addresses and ports; hostnames are not resolved. On Unix, `SIGINT` and `SIGTERM` trigger graceful HTTP/runtime shutdown. Graceful stop closes runtime admission, drains every already accepted command through the ordinary bounded writer turns, and joins tracked terminal-result publication before returning. This is an in-memory normal-stop guarantee, not crash persistence or cross-process exactly-once behavior.

`--database-path` is only the validated configuration seam for Issue #10. The current service does not initialize SQLite, create that file, restore a snapshot, or claim cross-process durability. Each process starts an in-memory game, a new `run_id`, and a real-time writer that advances without clients.

## HTTP contract

### GET `/api/game/view`

Returns a complete, statically typed public `GameView`. Its top-level fields are:

- `schema_version`: JSON integer `1`;
- `run_id`: opaque 32-character process identifier;
- `revision`: checked JSON integer from zero through `2^53-1`;
- `clock`: logical update/cadence counters;
- `game`: all currently implemented public M1 production state.

Every `Amount` is serialized as a canonical ASCII decimal JSON string, preserving `10^-18`, values beyond `2^53`, and larger exact values without a JSON float. Views are cloned projections of one runtime snapshot. They contain no RNG state, retry records, process lag/health, database path, or mutable references. GET does not advance the logical clock, execute a command, grant production, or draw random numbers.

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
```

The Rust suites include duplicate/unknown-field and primitive negative tables, real HTTP client/socket checks, deterministic real-writer gates for in-flight coalescing and conflicts, terminal success/rejection replay, final-stock contention, accepted disconnect behavior, exact Amount view fixtures, and independent-client writes. The process checker additionally starts the default and explicit listeners, performs 1,000 distinct legal writes, reaches a real stock-exhaustion rejection, checks terminal replay/conflict, verifies `SIGTERM`, and protects existing-data sentinels.

## Current limits

Issue #9 implements only the two HTTP routes above. SQLite persistence/snapshot recovery (#10), SSE (#11), browser UI (#12), automated production and other feature packs (#14-#16), and full playable integration (#17) remain separate work. Unsupported actions are never accepted placeholders.
