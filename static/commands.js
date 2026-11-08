// Strict public command transport for the default game.
// No command result is a View or a source of resource mutations.

const COMMAND_TYPE = "make_paperclip";
const MAX_COMMAND_ID_BYTES = 128;
const MAX_RESPONSE_BYTES = 16 * 1024;

// Validation failures are distinct from failures to obtain or read a Response.
class ResponseValidationError extends TypeError {}
const textEncoder = new TextEncoder();

function hasExactFields(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

export function createCommandId() {
  if (globalThis.crypto === undefined || typeof globalThis.crypto.randomUUID !== "function") {
    throw new Error("secure browser command IDs are unavailable");
  }
  return globalThis.crypto.randomUUID();
}

export function makePaperclipCommand(commandId) {
  if (typeof commandId !== "string" || commandId.length === 0 ||
      textEncoder.encode(commandId).length > MAX_COMMAND_ID_BYTES ||
      /[\u0000-\u001f\u007f]/.test(commandId)) {
    throw new TypeError("invalid opaque command ID");
  }
  return Object.freeze({
    command_id: commandId,
    type: COMMAND_TYPE,
    arguments: Object.freeze({}),
  });
}

export async function readBoundedJson(response) {
  if (response.body === null) throw new ResponseValidationError("empty command response");
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        await reader.cancel("command response limit");
        throw new ResponseValidationError("oversized command response");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(body));
  } catch (error) {
    throw new ResponseValidationError("invalid JSON response");
  }
}

function validRevision(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function parseOutcome(httpStatus, payload) {
  if (httpStatus === 200 && hasExactFields(payload, ["status", "revision"]) &&
      payload.status === "applied" && validRevision(payload.revision)) {
    return {kind: "applied", revision: payload.revision};
  }
  if (httpStatus === 422 && hasExactFields(payload, ["status", "revision", "reason"]) &&
      payload.status === "rule_rejected" && validRevision(payload.revision) &&
      ["insufficient_wire", "conversion_rejected", "conflicting_retry"].includes(payload.reason)) {
    return {kind: "rule_rejected", revision: payload.revision, reason: payload.reason};
  }
  if (httpStatus === 409 && hasExactFields(payload, ["status"]) && payload.status === "conflict") {
    return {kind: "conflict"};
  }
  if (httpStatus === 503 && hasExactFields(payload, ["status", "reason"]) &&
      payload.status === "unavailable" && ["queue_full", "runtime_closed"].includes(payload.reason)) {
    return {kind: "unavailable", reason: payload.reason};
  }
  if (httpStatus === 400 && hasExactFields(payload, ["status", "reason"]) &&
      payload.status === "schema_error" && typeof payload.reason === "string") {
    return {kind: "schema_error", reason: payload.reason};
  }
  if (httpStatus === 404 && hasExactFields(payload, ["status"]) && payload.status === "unknown_command") {
    return {kind: "unknown_command"};
  }
  return {kind: "invalid_response"};
}

export async function postMakePaperclip(command, options = {}) {
  // Callers can only provide this closed command shape. No Amount, quantity,
  // timestamp, actor, world, observed revision, or resource field is accepted.
  if (!hasExactFields(command, ["command_id", "type", "arguments"]) ||
      command.type !== COMMAND_TYPE || !hasExactFields(command.arguments, [])) {
    throw new TypeError("only a typed make_paperclip command is accepted");
  }
  const checked = makePaperclipCommand(command.command_id);
  const fetchFunction = options.fetch ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs ?? 10_000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort("command timeout"), timeoutMs);
  try {
    const response = await fetchFunction("/api/game/commands", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(checked),
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    });
    const contentType = response.headers.get("Content-Type") ?? "";
    const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "application/json" || contentType.includes(",")) {
      return {kind: "invalid_response"};
    }
    return parseOutcome(response.status, await readBoundedJson(response));
  } finally {
    clearTimeout(timeout);
  }
}

export class MakePaperclipCommandRunner {
  constructor(onChange = () => {}, options = {}) {
    this.onChange = onChange;
    this.options = options;
    this.pending = false;
    this.retryCommand = null;
  }

  get retryAvailable() {
    return this.retryCommand !== null;
  }

  async run() {
    if (this.pending) return {kind: "pending"};
    let command;
    try {
      command = this.retryCommand ?? makePaperclipCommand(createCommandId());
    } catch (error) {
      const outcome = {kind: "local_error", message: String(error)};
      this.onChange(outcome);
      return outcome;
    }
    this.retryCommand = null;
    this.pending = true;
    this.onChange({kind: "pending", command});
    let outcome;
    try {
      outcome = await postMakePaperclip(command, this.options);
    } catch (error) {
      outcome = {kind: error instanceof ResponseValidationError ? "invalid_response" : "network_error", message: String(error)};
    }
    if (["network_error", "unavailable", "invalid_response"].includes(outcome.kind)) {
      // The accepted/disconnected window is ambiguous. Only an explicit later
      // activation retries, and it sends the exact same ID and normalized body.
      this.retryCommand = command;
    }
    this.pending = false;
    this.onChange({...outcome, command, retryAvailable: this.retryAvailable});
    return outcome;
  }
}
