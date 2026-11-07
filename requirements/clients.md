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
