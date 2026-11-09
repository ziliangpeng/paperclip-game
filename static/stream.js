// Full-view browser synchronization for the default authoritative game.
// Amount authority and display never pass through Number or parseFloat.

// The same source check is used by command, HTTP and native SSE consumers.
// The command boundary supplies its private validation type; stream.js remains
// self-contained for the standalone native-stream harness.
const JSON_INTEGER_SOURCE = /^-?(?:0|[1-9][0-9]*)$/;

export function parseTransportJson(text, ValidationError = TypeError) {
  return JSON.parse(text, (_key, value, context) => {
    if (typeof value !== "number") return value;
    if (!context || typeof context.source !== "string" ||
        !JSON_INTEGER_SOURCE.test(context.source.trim()) || !Number.isSafeInteger(value)) {
      throw new ValidationError("invalid JSON integer response");
    }
    return value;
  });
}

const VIEW_FIELDS = ["clock", "game", "revision", "run_id", "schema_version"];
const CLOCK_FIELDS = [
  "combat_pulses", "combat_remainder_nanos", "fast_phase", "second_phase",
  "slow_phase", "update_count",
];
const GAME_FIELDS = [
  "auto_clipper_cost", "auto_clipper_revealed", "auto_clippers", "clips_sold",
  "computing_hidden", "demand", "funds", "income", "last_sale_revenue",
  "lifetime_clips", "marketing_cost", "marketing_level", "memory",
  "price_per_clip", "processors", "projects_hidden", "trust", "unsold_clips",
  "unused_clips", "wire", "wire_quote", "wire_spool_length",
];
const AMOUNT_FIELDS = [
  "auto_clipper_cost", "auto_clippers", "clips_sold", "demand", "funds",
  "income", "last_sale_revenue", "lifetime_clips", "marketing_cost",
  "marketing_level", "memory", "price_per_clip", "processors", "trust",
  "unsold_clips", "unused_clips", "wire", "wire_quote", "wire_spool_length",
];
const BOOLEAN_FIELDS = [
  "auto_clipper_revealed", "computing_hidden", "projects_hidden",
];
const NONNEGATIVE_FIELDS = [
  "clips_sold", "demand", "lifetime_clips", "unsold_clips", "unused_clips",
  "wire", "wire_spool_length",
];
const INTEGRAL_FIELDS = [
  "auto_clippers", "marketing_level", "memory", "processors", "trust",
];
const AMOUNT_PATTERN = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{0,17}[1-9])?$/;
const MAX_AMOUNT_CHARACTERS = 1_048_576;

function hasExactFields(value, fields) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function validCounter(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export function assertCompleteGameView(view) {
  if (!hasExactFields(view, VIEW_FIELDS) || view.schema_version !== 1 ||
      typeof view.run_id !== "string" || view.run_id.length === 0 ||
      view.run_id.length > 128 || /[\u0000-\u001f\u007f]/.test(view.run_id) ||
      !validCounter(view.revision) || !hasExactFields(view.clock, CLOCK_FIELDS) ||
      !CLOCK_FIELDS.every((field) => validCounter(view.clock[field])) ||
      !hasExactFields(view.game, GAME_FIELDS)) {
    throw new TypeError("invalid complete GameView");
  }
  const amounts = new Map(AMOUNT_FIELDS.map((field) => [field, parseAmount(view.game[field]).scaled]));
  for (const field of NONNEGATIVE_FIELDS) {
    if (amounts.get(field) < 0n) throw new TypeError("negative nonnegative Amount");
  }
  for (const field of INTEGRAL_FIELDS) {
    if (amounts.get(field) % (10n ** 18n) !== 0n) throw new TypeError("fractional integral Amount");
  }
  for (const field of BOOLEAN_FIELDS) {
    if (typeof view.game[field] !== "boolean") throw new TypeError("invalid GameView flag");
  }
  return view;
}

export function parseAmount(amount) {
  if (typeof amount !== "string" || amount.length > MAX_AMOUNT_CHARACTERS ||
      !AMOUNT_PATTERN.test(amount) || amount === "-0") {
    throw new TypeError("non-canonical Amount");
  }
  const negative = amount.startsWith("-");
  const unsigned = negative ? amount.slice(1) : amount;
  const [integer, fraction = ""] = unsigned.split(".");
  const digits = integer + fraction.padEnd(18, "0");
  const scaled = BigInt(digits);
  return { negative, scaled: negative ? -scaled : scaled };
}

export function formatAmount(value) {
  const scaled = typeof value === "bigint" ? value : parseAmount(value).scaled;
  const negative = scaled < 0n;
  const digits = (negative ? -scaled : scaled).toString().padStart(19, "0");
  const integer = digits.slice(0, -18).replace(/^0+(?=[0-9])/, "");
  const fraction = digits.slice(-18).replace(/0+$/, "");
  return `${negative ? "-" : ""}${integer}${fraction ? `.${fraction}` : ""}`;
}

export function compareAmount(left, right) {
  const a = parseAmount(left).scaled;
  const b = parseAmount(right).scaled;
  return a < b ? -1 : a > b ? 1 : 0;
}

export function addAmount(left, right) {
  return formatAmount(parseAmount(left).scaled + parseAmount(right).scaled);
}

export function ceilAmount(amount) {
  const scaled = parseAmount(amount).scaled;
  const unit = 10n ** 18n;
  let quotient = scaled / unit;
  if (scaled > 0n && scaled % unit !== 0n) quotient += 1n;
  return quotient.toString();
}

// Tokens are connection-local bookkeeping, not actor credentials or command IDs.
// Only openStream() changes the active stream. A newly adopted run invalidates
// every token from an older local epoch.
export class GameViewSynchronizer {
  constructor(onPresentation = () => {}) {
    this.current = null;
    this.epoch = 0;
    this.nextGeneration = 0;
    this.activeStream = null;
    this.onPresentation = onPresentation;
  }

  openStream() {
    this.nextGeneration += 1;
    this.activeStream = { generation: this.nextGeneration, epoch: this.epoch };
    return this.activeStream;
  }

  requestView() {
    return { epoch: this.epoch };
  }

  acceptStreamInitial(token, view) {
    return this.#acceptStream(token, view, true);
  }

  acceptStreamUpdate(token, view) {
    return this.#acceptStream(token, view, false);
  }

  acceptGet(token, view) {
    assertCompleteGameView(view);
    if (token.epoch !== this.epoch) return "stale-source";
    return this.#accept(view, true, null);
  }

  #acceptStream(token, view, initial) {
    assertCompleteGameView(view);
    if (this.activeStream === null ||
        token.generation !== this.activeStream.generation) return "stale-source";
    if (this.current !== null && view.run_id === this.current.run_id) {
      return this.#accept(view, false, token);
    }
    if (!initial || token.epoch !== this.epoch) {
      return initial ? "stale-source" : "unexpected-run";
    }
    return this.#accept(view, true, token);
  }

  #accept(view, newRunAllowed, streamToken) {
    if (this.current !== null && view.run_id === this.current.run_id) {
      if (view.revision < this.current.revision) return "ignored-lower";
      if (view.revision === this.current.revision) return "equal";
      this.current = view;
      this.onPresentation(view, "applied");
      return "applied";
    }
    if (!newRunAllowed) return "unexpected-run";
    this.current = view;
    this.epoch += 1;
    if (streamToken === null) this.activeStream = null;
    this.onPresentation(view, "adopted-new-run");
    return "adopted-new-run";
  }
}
