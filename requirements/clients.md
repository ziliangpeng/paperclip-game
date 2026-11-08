# Clients, Commands and State Streaming

## 1. Default Game Is Transparent to Users — CONFIRMED

- Users enter the current sole game by opening `/`.
- Users do not need to know about `game_id`, `default`, instance selectors, or invitation codes.
- Multiple web pages connect to the same game by default.
- Browser URLs, Command bodies, and SSE connections do not require users to select a game ID.

Internally, mapping still uses `default` to preserve the boundary for future extension.

## 2. External Interface Shape — PROPOSED

The following interfaces without instance IDs are recommended:

```http
GET  /api/game/view
POST /api/game/commands
GET  /api/game/stream
```

- Commands use ordinary HTTP POST;
- State streaming uses SSE;
- WebSocket is not currently needed;
- Specific JSON schemas will be fixed in the corresponding API Issue.

Future multiple instances may add an addressing scheme at the entry layer without requiring the instance concept to be exposed to current users.

## 3. Commands — CONFIRMED / PROPOSED

### Confirmed Semantics

- A Command expresses intent and does not submit client-computed authoritative state.
- It contains no Human/Agent `actor`.
- It contains no `game_id` that users are required to select.
- Resources and unlock conditions are validated at execution time.
- A stale observation does not automatically cause failure; failure must be based on the actual current state and an explicit rule reason.
- During the current process lifetime, idempotent retries of the same logical Command must not apply state changes more than once; the crash window is handled according to the runtime recovery rules.
- No special Agent API may modify time or write resources directly.

### Proposed Envelope and Retry Contract

A client-generated `command_id` is recommended to express logical Command identity; this field name and encoding are not a CONFIRMED product interface and will be fixed by the corresponding API Issue.

```json
{
  "command_id": "client-generated-id",
  "type": "action-name",
  "arguments": {}
}
```

If this scheme is adopted, the baseline contract is:

- The scope is the current process lifetime of the `default` game;
- Concurrent retries with the same key and the same normalized Command payload share a single execution and must not apply state changes more than once;
- After completion, a retry with the same key and same arguments returns the first recorded terminal result rather than executing again against the new state;
- A game-rule validation failure is also a retrievable terminal result; retrying with the same key and same arguments returns the same rejection result, and a new intent must use a new key;
- The same key with a different payload returns an explicit Conflict error (HTTP 409 is recommended); the subsequent request that causes a conflict must not apply state changes, and the first accepted payload and existing key binding remain unchanged;
- Preservation of that result across the crash recovery window is not guaranteed; after recovery, clients first synchronize current state and then decide on new actions;
- The API Issue must define the concrete implementation and tests for malformed requests, concurrent in-flight retries, result binding, and normalized payloads.

Action names, argument limits, response schemas, and error codes are explicit work items for the corresponding API Issues.

## 4. GameView — CONFIRMED / PROPOSED

- Clients receive a view of server state suitable for observation, not a writable server-side internal object.
- The UI and structured Agents may use the same public View.
- The View is derived from authoritative state and does not create a second set of rules in the browser.
- Presentation preferences are not stored in core state merely because multiple UIs may exist in the future.

The View is recommended to carry `revision` and `run_id`; an initial connection may receive a full snapshot followed by updates.

## 5. SSE and Reconnection

### Confirmed Semantics

- Both browsers and Agents can observe state updates.
- Disconnection of a server-to-client connection does not affect the game clock.
- After reconnecting, a client must be able to obtain a consistent current state.
- A late HTTP response or old SSE event must not overwrite a newer View already known to the client.
- Crash recovery may return the server to an earlier game state; clients must accept the recovered authoritative state and resynchronize, rather than overwrite it with a pre-crash cache.

### Proposed Ordering Metadata

An increasing `revision` and a distinct `run_id` for each process run are recommended to implement the semantics above:

- Within the same `run_id`, discard late old Views by revision;
- When `run_id` changes, first accept the recovered full snapshot before comparing revisions again;
- The specific fields and encoding are consistent with the Revision and Recovery PROPOSED subsection in `runtime.md` and will be fixed by the API Issue.

While state is small in the first version, the full public View may be sent directly rather than prematurely building a complex JSON Patch or event-sourcing framework; if state size later demonstrates a need for an incremental protocol, it will be reviewed separately.

## 6. Browser UI Behavior — CONFIRMED

- A click only sends a Command; it does not directly modify authoritative resources in JavaScript.
- Pending feedback may follow a click, but success must not be faked by adding resources locally.
- A disabled button merely reflects server state; the server must still validate independently.
- Two pages may operate the same game and see the same world; users are not required to log in or select a role.
- Refreshing the UI merely reconnects and does not trigger save rollback.
- Visual acceptance of the first version uses a best effort original style rather than DOM or pixel-level equivalence.


## 7. Numeric Field Encoding — PROPOSED

The schema statically determines every field's type. There is no generic `{type, value}` number protocol and no conversion of an economic value through a browser `Number` merely to make JSON convenient.

### Canonical `Amount` strings

Every `Amount` in a View, SSE event, or snapshot is a JSON string containing one whole ASCII decimal value:

```text
amount = [ "-" ] integer [ "." fraction ]
integer = "0" / nonzero-digit *digit
fraction = 1*18digit
```

The last fractional digit must be nonzero. The canonical zero is `"0"`. Valid examples include `"6.21"`, `"-41117.99"`, `"0.000000000000000001"`, and `"9007199254740993"`. Reject `""`, `"-0"`, `"+1"`, `"01"`, `"1.0"`, `".5"`, `"1."`, exponents, separators, non-ASCII digits, leading/trailing whitespace, `NaN`, infinities, more than 18 fractional digits, and JSON numbers in `Amount` positions. Nonnegative constructors reject a leading minus, and integral constructors reject a fraction. Decoders must match the entire post-JSON-decoding string, not an accepting prefix or a platform-specific decimal syntax.

A parser may have a generous documented character/allocation limit as a corruption and denial-of-service guard. That limit is not a game-value ceiling and must justify ample headroom above accepted state sizes; values beyond `3e55` scale and one additional unit are not clipped, rounded, or saturated to make them fit. Hitting the guard is an explicit decode/resource failure, never a silent value substitution. Snapshot decoding fails closed and leaves the last good committed state untouched.

### Bounded integers, RNG, and derived displays

A bounded counter transported as a JSON integer has a documented range no greater than `2^53-1`; `revision` uses checked increments within that bound. Values without such a bound use their semantic exact encoding rather than an overflowing JSON integer. RNG words are never exposed for client authority and are serialized in snapshots as fixed-width lowercase hexadecimal strings. An explicitly undefined derived display, such as a zero-rate gift countdown, may be `null`; this is not a serialization of NaN or infinity and changes no underlying state.

Views and SSE frames carry identical field encodings, and SSE `id` may be the string `"<run_id>:<revision>"`. Reconnect sends a complete current View, so it cannot gain or lose numeric precision relative to an earlier full View. A browser or Agent must validate `run_id`/revision before accepting state as described above; numeric string equality alone does not establish freshness.

### Commands and consumer arithmetic

No public Command accepts an arbitrary `Amount`, an authoritative total, a computed cost, or a resource/time setter. The canonical controls are closed typed intents. Argument-free investment deposit/withdraw operations act on the server's current balance; fixed construction batches and Work/Think allocations use named choices or explicitly bounded integer ranges. When an integer parameter is used, it must be an in-range JSON integer: `1.0`, `1e0`, `"1"`, `true`, fractions, and out-of-range values are rejected. Unknown or duplicate fields and wrong primitive types fail structural decoding before retry binding or game mutation. Existing retry and execution-time validation semantics remain unchanged.

The native browser parses canonical strings into sign, integer digits, and fractional padding and uses `BigInt` (or an equivalent exact scaled-integer implementation) for comparison, arithmetic, ceiling, and displayed values. Agents use `BigInt`, arbitrary-precision integers, decimal types, or equivalent exact language types. `Number()`/`parseFloat` on an `Amount` is forbidden for authority, comparison, affordability, or displayed values. A separately identified progress-bar width or other visual-only projection may be approximate, but cannot feed back into displayed numeric meaning or state.

### Persistence transport boundary

Snapshot payload JSON uses the same static strings, bounded integers, and hexadecimal RNG words. It is serialized deterministically and stored as SQLite `TEXT`; no economic field is stored as SQLite `REAL` or reconstructed through a SQL numeric JSON function. Unsupported versions, checksum failures, malformed JSON, missing or unknown fields, duplicate fields, wrong primitives, non-canonical values, or cross-field invariant failures are rejected without overwriting, deleting, or silently replacing the previous good game. Explicit version migrations apply only to documented later fields with retained-progress proof.
