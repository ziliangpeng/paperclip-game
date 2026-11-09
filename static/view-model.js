// Presentation-only formatting and rendering for complete server Views.
// Domain values remain canonical strings; no local economy exists here.

import {assertCompleteGameView, formatAmount, parseAmount} from "/static/stream.js";

function splitCanonical(amount) {
  const canonical = formatAmount(amount);
  const negative = canonical.startsWith("-");
  const unsigned = negative ? canonical.slice(1) : canonical;
  const [integer, fraction = ""] = unsigned.split(".");
  return {negative, integer, fraction};
}

function groupInteger(integer) {
  return integer.replace(/\B(?=([0-9]{3})+(?![0-9]))/g, ",");
}

export function formatAmountForDisplay(amount, {currency = false, group = true} = {}) {
  const {negative, integer, fraction} = splitCanonical(amount);
  const whole = group ? groupInteger(integer) : integer;
  const decimals = currency ? fraction.padEnd(2, "0") : fraction;
  return `${negative ? "-" : ""}${whole}${decimals ? `.${decimals}` : ""}`;
}

export function formatDemandPercent(amount) {
  const scaled = formatAmount(parseAmount(amount).scaled * 10n);
  return `${formatAmountForDisplay(scaled)}%`;
}

export function createViewModel(view) {
  assertCompleteGameView(view);
  const model = {};
  for (const [field, raw] of Object.entries(view.game)) {
    if (typeof raw === "string") {
      const currency = ["funds", "wire_quote", "price_per_clip", "auto_clipper_cost", "income", "last_sale_revenue", "marketing_cost"].includes(field);
      model[field] = {
        canonical: formatAmount(raw),
        display: formatAmountForDisplay(raw, {currency}),
      };
    }
  }
  model.demand.display = formatDemandPercent(view.game.demand);
  return {
    amounts: model,
    runId: view.run_id,
    revision: view.revision,
    computingHidden: view.game.computing_hidden,
    autoClippersRevealed: view.game.auto_clipper_revealed,
    consoleMessages: view.game.console_messages,
  };
}

const ELEMENT_FIELDS = {
  lifetime_clips: "lifetime-clips",
  unsold_clips: "unsold-clips",
  unused_clips: "unused-clips",
  funds: "funds",
  wire: "wire",
  wire_spool_length: "wire-spool-length",
  wire_quote: "wire-quote",
  price_per_clip: "price-per-clip",
  marketing_level: "marketing-level",
  demand: "demand",
  marketing_cost: "marketing-cost",
  clips_sold: "clips-sold",
  income: "income",
  last_sale_revenue: "last-sale-revenue",
  trust: "trust",
  processors: "processors",
  memory: "memory",
  auto_clippers: "auto-clippers",
  auto_clipper_cost: "auto-clipper-cost",
  auto_clipper_rate: "auto-clipper-rate",
};

export function renderView(document, view) {
  const model = createViewModel(view);
  for (const [field, elementId] of Object.entries(ELEMENT_FIELDS)) {
    const element = document.getElementById(elementId);
    const amount = model.amounts[field];
    if (element.dataset.canonical !== amount.canonical) {
      // Only presentation runs when the exact server value actually changed.
      element.value = amount.canonical;
      element.dataset.canonical = amount.canonical;
      element.textContent = amount.display;
      element.title = field === "demand" ? amount.display : amount.canonical;
    }
  }
  document.getElementById("computational-resources").hidden = model.computingHidden;
  document.getElementById("auto-clippers-panel").hidden = !model.autoClippersRevealed;
  const consoleLines = document.querySelectorAll("#console-messages > li");
  model.consoleMessages.forEach((message, index) => { consoleLines[index].textContent = message; });
  document.documentElement.dataset.viewState = "ready";
  document.documentElement.dataset.runId = model.runId;
  document.documentElement.dataset.revision = String(model.revision);
  return model;
}
