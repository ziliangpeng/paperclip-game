// Native application wiring: server Views are the only resource authority.

import {GameViewSynchronizer, assertCompleteGameView, parseTransportJson} from "/static/stream.js";
import {MakePaperclipCommandRunner, readBoundedJson} from "/static/commands.js";
import {renderView} from "/static/view-model.js";

const form = document.getElementById("command-form");
const button = document.getElementById("make-paperclip");
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
      setCommandStatus("ready", "Ready. Make Paperclip sends one typed command to the server.");
    }
  });
});

function updateControls() {
  // Keep focus during pending. The runner rejects duplicate activation; this
  // ARIA state is feedback only and never represents Wire affordability.
  button.setAttribute("aria-disabled", String(runner.pending));
  button.textContent = runner.pending ? "Sending…" :
    runner.retryAvailable ? "Retry Make Paperclip" : "Make Paperclip";
  form.setAttribute("aria-busy", String(runner.pending));
}

const runner = new MakePaperclipCommandRunner((outcome) => {
  // Any command outcome supersedes the one-time initial generic Ready message.
  // Read-only transport recovery remains free to announce the first good View.
  readyAnnounced = true;
  switch (outcome.kind) {
    case "pending":
      setCommandStatus("pending", "Command pending. The page has not changed any resources.");
      break;
    case "applied":
      setCommandStatus("ready", `Server applied the command at revision ${outcome.revision}. Displayed resources come from the newest full server View.`);
      break;
    case "rule_rejected": {
      const reason = outcome.reason === "insufficient_wire" ?
        "not enough Wire" : "the current game rule rejected it";
      setCommandStatus("error", `Server rejected the command: ${reason}. This request made no resource change.`);
      break;
    }
    case "conflict":
      setCommandStatus("error", "Command ID conflict. The server did not apply this request. Activate again to start a new command.");
      break;
    case "network_error":
      setCommandStatus("error", "Network outcome is unknown. Retry sends the same command ID. No local resource credit was given.");
      break;
    case "unavailable":
      setCommandStatus("error", "The server is temporarily unavailable and the outcome is not known. Retry sends the same command ID.");
      break;
    case "invalid_response":
      setCommandStatus("error", "The server response could not be validated and the outcome is unknown. Retry sends the same command ID.");
      break;
    case "schema_error":
      setCommandStatus("error", "The server rejected an invalid command envelope. Activate again to create a new valid command.");
      break;
    case "unknown_command":
      setCommandStatus("error", "The server does not support this command. No resource change was reported.");
      break;
    case "local_error":
      setCommandStatus("error", "This browser could not create a secure command ID. No request was sent.");
      break;
    default:
      setCommandStatus("error", "Command outcome is unknown. No local resource credit was given.");
  }
  updateControls();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void runner.run();
});
button.addEventListener("keydown", (event) => {
  // Preserve native Enter/Space activation while suppressing auto-repeat clicks.
  if (event.repeat && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
  }
});
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
