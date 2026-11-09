// Native application wiring: server Views are the only resource authority.

import {GameViewSynchronizer, assertCompleteGameView, parseTransportJson} from "/static/stream.js";
import {GameCommandRunner, readBoundedJson} from "/static/commands.js";
import {renderView} from "/static/view-model.js";

const commandStatus = document.getElementById("command-status");
const connectionStatus = document.getElementById("connection-status");
let renderQueued = false;
let readyAnnounced = false;
let source = null;
let streamToken = null;
let initialFrame = true;
let restartTimer = null;
let invalidViewDiagnostic = false;

function setCommandStatus(kind, message) {
  if (commandStatus.textContent !== message) commandStatus.textContent = message;
  commandStatus.dataset.kind = kind;
}

function setConnectionStatus(message) {
  if (connectionStatus.textContent !== message) connectionStatus.textContent = message;
}

const synchronizer = new GameViewSynchronizer((view, decision) => {
  if (renderQueued) return;
  renderQueued = true;
  queueMicrotask(() => {
    renderQueued = false;
    // Read the newest complete View, not a captured intermediate frame.
    renderView(document, synchronizer.current);
    // Only actually presenting an accepted View clears this diagnosis.
    invalidViewDiagnostic = false;
    if (decision === "adopted-new-run") {
      setConnectionStatus("Connected to the current server run.");
    } else {
      setConnectionStatus("Newest accepted server View displayed.");
    }
    if (!readyAnnounced) {
      readyAnnounced = true;
      setCommandStatus("ready", "Ready. Each control sends one closed command to the server.");
    }
  });
});

const COMMANDS = [
  ["command-form", "make-paperclip", "make_paperclip", "Make Paperclip"],
  ["buy-wire-form", "buy-wire", "buy_wire", "Buy Wire"],
  ["lower-price-form", "lower-price", "lower_price", "Lower Price"],
  ["raise-price-form", "raise-price", "raise_price", "Raise Price"],
  ["buy-marketing-form", "buy-marketing", "buy_marketing", "Buy Marketing"],
];
const controls = [];

function updateControls() {
  for (const {button, form, runner, label} of controls) {
    // Focus is retained. Pending is explicit feedback, never local resource authority.
    button.setAttribute("aria-disabled", String(runner.pending));
    button.textContent = runner.pending ? "Sending…" :
      runner.retryAvailable ? `Retry ${label}` : label;
    form.setAttribute("aria-busy", String(runner.pending));
  }
}

for (const [formId, buttonId, type, label] of COMMANDS) {
  const form = document.getElementById(formId);
  const button = document.getElementById(buttonId);
  button.setAttribute("aria-describedby", "command-status");
  const runner = new GameCommandRunner(type, (outcome) => {
    readyAnnounced = true;
    switch (outcome.kind) {
      case "pending":
        setCommandStatus("pending", type === "make_paperclip" ? "Command pending. The page has not changed any resources." : `${label} is pending. The page has not changed any resources.`);
        break;
      case "applied":
        const appliedMessage = type === "make_paperclip" ?
          `Server applied the command at revision ${outcome.revision}. Displayed resources come from the newest full server View.` :
          `Server applied ${label} at revision ${outcome.revision}. Resources come from the newest complete server View.`;
        setCommandStatus("ready", appliedMessage);
        break;
      case "rule_rejected": {
        const reasons = {
          insufficient_wire: "not enough Wire",
          insufficient_funds: "not enough Funds at the current server quote/cost",
          price_at_minimum: "price is already at its minimum",
          numeric_decision_domain: "the finite integer-decision domain was exceeded",
          numeric_evaluation_rejected: "numeric evaluation rejected the input",
          counter_limit: "a checked counter reached its limit",
          resource_limit: "the explicit evaluation resource limit was reached",
          invalid_state: "the game state is invalid",
        };
        const reason = type === "make_paperclip" ?
          (outcome.reason === "insufficient_wire" ? "not enough Wire" : "the current game rule rejected it") :
          (reasons[outcome.reason] ?? "the current game rule rejected it");
        const rejection = type === "make_paperclip" ?
          `Server rejected the command: ${reason}. This request made no resource change.` :
          `Server rejected ${label}: ${reason}. This request made no resource change.`;
        setCommandStatus("error", rejection);
        break;
      }
      case "conflict":
        setCommandStatus("error", type === "make_paperclip" ? "Command ID conflict. The server did not apply this request. Activate again to start a new command." : `${label} had a command ID conflict. Activate again to start a new command.`);
        break;
      case "network_error":
        setCommandStatus("error", type === "make_paperclip" ? "Network outcome is unknown. Retry sends the same command ID. No local resource credit was given." : `${label} has an unknown network outcome. Retry sends the same command ID; no local credit was given.`);
        break;
      case "unavailable":
        setCommandStatus("error", type === "make_paperclip" ? "The server is temporarily unavailable and the outcome is not known. Retry sends the same command ID." : `${label} has an unknown outcome while the server is unavailable. Retry sends the same command ID.`);
        break;
      case "invalid_response":
        setCommandStatus("error", type === "make_paperclip" ? "The server response could not be validated and the outcome is unknown. Retry sends the same command ID." : `${label} has an unknown outcome after an invalid server response. Retry sends the same command ID.`);
        break;
      case "schema_error":
        setCommandStatus("error", type === "make_paperclip" ? "The server rejected an invalid command envelope. Activate again to create a new valid command." : `${label} had an invalid command envelope. No request was applied.`);
        break;
      case "unknown_command":
        setCommandStatus("error", type === "make_paperclip" ? "The server does not support this command. No resource change was reported." : `The server does not support ${label}. No resource change was reported.`);
        break;
      default:
        setCommandStatus("error", type === "make_paperclip" ? "This browser could not create a secure command ID. No request was sent." : `${label} could not create a secure command ID. No request was sent.`);
    }
    updateControls();
  });
  controls.push({form, button, runner, label});
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void runner.run();
  });
  button.addEventListener("keydown", (event) => {
    if (event.repeat && (event.key === "Enter" || event.key === " ")) event.preventDefault();
  });
}
updateControls();

async function fetchCurrentView() {
  const token = synchronizer.requestView();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort("View request timeout"), 8_000);
  try {
    const response = await fetch("/api/game/view", {
      cache: "no-store", credentials: "same-origin", signal: controller.signal,
    });
    if (response.status !== 200) throw new Error(`View HTTP status ${response.status}`);
    const contentType = response.headers.get("Content-Type") ?? "";
    const mediaType = contentType.split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "application/json" || contentType.includes(",")) {
      throw new Error("invalid View content type");
    }
    const view = assertCompleteGameView(await readBoundedJson(response));
    // Adoption, not HTTP success or an ignored lower/equal View, owns recovery text.
    synchronizer.acceptGet(token, view);
  } catch (error) {
    if (!invalidViewDiagnostic) {
      setConnectionStatus("The current View request failed or arrived too late; waiting for a live server baseline.");
    }
  } finally {
    clearTimeout(timeout);
  }
}

function restartStream() {
  if (restartTimer !== null) return;
  restartTimer = setTimeout(() => {
    restartTimer = null;
    connectStream();
  }, 25);
}

function connectStream() {
  if (source !== null) source.close();
  const currentSource = new EventSource("/api/game/stream");
  source = currentSource;
  initialFrame = true;
  currentSource.onopen = () => {
    if (source !== currentSource) return;
    streamToken = synchronizer.openStream();
    initialFrame = true;
    if (!invalidViewDiagnostic) {
      setConnectionStatus("Live server connection open; receiving complete Views.");
    }
  };
  currentSource.onerror = () => {
    if (source === currentSource) {
      if (!invalidViewDiagnostic) {
        setConnectionStatus("Live connection interrupted; the browser will reconnect without resetting the game.");
      }
    }
  };
  currentSource.addEventListener("game_view", (event) => {
    if (source !== currentSource) return;
    const wasInitial = initialFrame;
    let decision;
    try {
      const view = assertCompleteGameView(parseTransportJson(event.data));
      if (event.lastEventId !== `${view.run_id}:${view.revision}`) {
        throw new TypeError("invalid game_view event ID");
      }
      const token = streamToken;
      if (token === null) return;
      decision = wasInitial ? synchronizer.acceptStreamInitial(token, view) :
        synchronizer.acceptStreamUpdate(token, view);
      initialFrame = false;
    } catch (error) {
      // Ignore a malformed complete frame and retain the last good View. The
      // next valid full frame can restore this stream without local synthesis.
      invalidViewDiagnostic = true;
      setConnectionStatus("An invalid server View was ignored; the last valid View is retained.");
      return;
    }
    if (wasInitial && decision === "stale-source") {
      // An initial GET may have adopted the run and advanced the local epoch
      // before this physical stream opened. Reconnect once at the current
      // epoch instead of leaving its valid frames without an active token.
      restartStream();
    } else if (decision === "unexpected-run") {
      // Only an initial physical-connection baseline may adopt another run.
      restartStream();
    }
  });
}

void fetchCurrentView();
connectStream();
