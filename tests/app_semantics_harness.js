"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : Boolean(force);
    if (enabled) this.values.add(value); else this.values.delete(value);
    return enabled;
  }
}

class Element {
  constructor(id = "") {
    this.id = id;
    this.dataset = {};
    this.listeners = new Map();
    this.classList = new ClassList();
    this.style = {};
    this.hidden = false;
    this.value = "";
    this.checked = false;
    this.textContent = "";
    this.innerHTML = "";
  }
  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }
  emit(type, extra = {}) {
    for (const listener of this.listeners.get(type) || []) {
      listener({ target: this, ...extra });
    }
  }
  setAttribute(name, value) { this[name] = String(value); }
  querySelector() { return null; }
  focus() { document.activeElement = this; }
}

const ids = [
  "asOfLabel", "cadenceLabel", "qualityValue", "qualityBar", "modelCount",
  "benchmarkCount", "familyCount", "observationCount", "coverageValue",
  "providerFilter", "familyFilter", "presetSelect", "harnessFilter",
  "runBenchmarkFilter", "sortSelect", "harnessFilterWrap",
  "runBenchmarkFilterWrap", "searchInput", "availableOnly", "showCatalog",
  "activeFilters", "presetHint", "coverageNote", "matrixHead", "matrixBody",
  "matrixView", "matrixScroll", "matrixTools", "matrixNavigationStatus",
  "benchmarkJump", "matrixHome", "cardsView", "emptyState", "spotlightGrid", "spotlightSection",
  "atlasLegend", "publicEvidenceSection", "publicEvidenceToggle", "publicEvidenceBody", "publicEvidenceCount",
  "publicEvidenceList", "publicAliasLedger", "runsView", "runTableFrame",
  "runTableHead", "runTableBody", "runCardsView", "runEmptyState",
  "runCountLabel", "atlasViewSwitcher", "runViewSwitcher", "matrixTitle",
  "footerStatus", "freshnessPill", "dataLink", "detailDrawer", "drawerBackdrop",
  "drawerContent", "toast", "resetFilters", "emptyReset", "runEmptyReset",
  "closeDrawer", "themeToggle",
];
const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
const matrixSubtitle = new Element("matrixSubtitle");
const modeTabs = ["atlas", "runs"].map((mode) => {
  const element = new Element(`mode-${mode}`);
  element.dataset.mode = mode;
  return element;
});
const atlasTabs = ["matrix", "cards"].map((view) => {
  const element = new Element(`atlas-${view}`);
  element.dataset.view = view;
  return element;
});
const runTabs = ["table", "cards"].map((view) => {
  const element = new Element(`runs-${view}`);
  element.dataset.runView = view;
  return element;
});
const densityButtons = ["compact", "standard"].map((density) => {
  const element = new Element(`density-${density}`);
  element.dataset.matrixDensity = density;
  return element;
});
const documentListeners = new Map();
const document = {
  activeElement: null,
  documentElement: new Element("html"),
  getElementById(id) { return elements[id] || (elements[id] = new Element(id)); },
  querySelector(selector) {
    return selector === "#matrix .section-subtitle" ? matrixSubtitle : null;
  },
  querySelectorAll(selector) {
    if (selector === ".mode-tab") return modeTabs;
    if (selector === ".view-tab[data-view]") return atlasTabs;
    if (selector === ".view-tab[data-run-view]") return runTabs;
    if (selector === "[data-matrix-density]") return densityButtons;
    if (selector === ".stat-card") return [];
    return [];
  },
  addEventListener(type, listener) {
    const listeners = documentListeners.get(type) || [];
    listeners.push(listener);
    documentListeners.set(type, listeners);
  },
};

function documentClick(target) {
  for (const listener of documentListeners.get("click") || []) listener({ target });
}

const runs = [
  {
    id: "direct-model-only",
    modelId: "acme/model@1",
    modelName: "Acme Model",
    benchmarkId: "direct-bench",
    harnessId: "model-only",
    subjectType: "model",
    value: 90,
  },
  {
    id: "harness-inferred-system",
    modelId: "acme/model@1",
    modelName: "Acme Model",
    benchmarkId: "direct-bench",
    harnessId: "agent-loop",
    value: 80,
    notes: "harness-marker",
  },
];
for (let index = 0; index < 61; index += 1) {
  runs.push({
    id: `system-tail-${index}`,
    modelId: "acme/model@1",
    modelName: "Acme Model",
    benchmarkId: "system-bench",
    harnessId: "model-only",
    subjectType: "model",
    value: index,
    notes: `tail-marker-${index}`,
  });
}

const fixture = {
  meta: { status: "curated", asOf: "2026-08-28" },
  models: [{ id: "acme/model@1", name: "Acme Model", provider: "Acme", status: "active" }],
  benchmarks: [
    { id: "direct-bench", name: "Direct Bench", evaluationMode: "direct", metric: "score", displayPriority: 20 },
    { id: "system-bench", name: "System Bench", evaluationMode: "system", metric: "score", displayPriority: 10 },
    { id: "arena-text", name: "Arena Text", evaluationMode: "direct", metric: "arena_score_bt", displayPriority: 30 },
  ],
  harnesses: [
    { id: "model-only", name: "Model only", kind: "model" },
    { id: "agent-loop", name: "Agent loop", kind: "coding-agent" },
  ],
  runs,
  publicEvidence: [
    {
      id: "helm-accuracy-mean",
      canonicalModelId: "acme/model@1",
      benchmarkId: "helm-mean-score",
      metricId: "score",
      value: 0.8,
      unit: "fraction",
      sourceId: "helm-capabilities",
      protocol: { harness: "helm", table: "Accuracy", direction: "higher" },
    },
    {
      id: "helm-efficiency-mean",
      canonicalModelId: "acme/model@1",
      benchmarkId: "helm-mean-score",
      metricId: "score",
      value: 42,
      unit: "count",
      sourceId: "helm-capabilities",
      protocol: { harness: "helm", table: "Efficiency", direction: "lower" },
    },
    {
      id: "helm-prompt-tokens",
      canonicalModelId: "acme/model@1",
      benchmarkId: "helm-mean-score",
      metricId: "prompt-tokens",
      value: 1234,
      unit: "count",
      sourceId: "helm-capabilities",
      protocol: { harness: "helm", table: "Efficiency", direction: "lower" },
    },
    {
      id: "arena-old-source-name",
      canonicalModelId: "acme/model@1",
      benchmarkId: "arena-text",
      metricId: "elo",
      value: 1450,
      unit: "elo",
      sourceId: "lmarena-hf-dataset",
      protocol: { harness: "arena-human-preference", rating_method: "bradley-terry" },
    },
  ],
  presets: [],
  sources: [],
};

const storage = new Map();
const context = {
  console,
  document,
  navigator: { clipboard: { writeText: async () => {} } },
  localStorage: {
    getItem(key) { return storage.get(key) || null; },
    setItem(key, value) { storage.set(key, String(value)); },
  },
  fetch: async () => ({ ok: true, json: async () => fixture }),
  requestAnimationFrame(callback) { callback(); },
  setTimeout,
  clearTimeout,
  URL,
};
context.window = context;

async function main() {
  const appPath = process.argv[2];
  vm.runInNewContext(fs.readFileSync(appPath, "utf8"), context, { filename: appPath });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  assert.strictEqual(elements.runTableBody.innerHTML, "", "atlas mode must not build the hidden run table");
  assert.strictEqual(elements.runCardsView.innerHTML, "", "atlas mode must not build hidden run cards");
  assert(
    elements.matrixBody.innerHTML.includes('data-benchmark="helm-mean-score--efficiency-score"'),
    "legacy HELM Efficiency/score row collided with Accuracy/score",
  );
  assert(
    !elements.matrixBody.innerHTML.includes('data-benchmark="helm-mean-score--prompt-tokens"'),
    "token telemetry leaked into the Atlas matrix",
  );
  assert(
    elements.matrixBody.innerHTML.includes('data-benchmark="arena-text"') && !elements.matrixBody.innerHTML.includes('data-benchmark="arena-text--elo"'),
    "legacy Arena source field was not mapped into the Bradley-Terry headline metric",
  );
  assert.strictEqual(elements.matrixView.dataset.density, "compact", "matrix must default to the compact density");
  assert(
    elements.matrixHead.innerHTML.indexOf('data-benchmark-col="system-bench"') < elements.matrixHead.innerHTML.indexOf('data-benchmark-col="direct-bench"'),
    "displayPriority did not control the stable left-to-right benchmark order",
  );
  assert(
    elements.matrixHead.innerHTML.indexOf('data-benchmark-col="direct-bench"') < elements.matrixHead.innerHTML.indexOf('data-benchmark-col="helm-mean-score--efficiency-score"'),
    "a secondary public metric slice inherited priority and displaced canonical columns",
  );
  assert(elements.benchmarkJump.innerHTML.includes("System Bench"), "benchmark quick navigation was not populated");
  assert.strictEqual(elements.publicEvidenceBody.hidden, true, "evidence audit details must default to collapsed");
  assert.strictEqual(elements.publicEvidenceList.innerHTML, "", "collapsed evidence audit eagerly rendered its representative rows");
  assert(elements.publicEvidenceCount.textContent.includes("个来源"), "collapsed evidence summary omitted source count");
  assert.strictEqual(elements.publicEvidenceToggle["aria-expanded"], "false", "collapsed audit toggle has incorrect accessibility state");

  elements.publicEvidenceToggle.emit("click");
  assert.strictEqual(elements.publicEvidenceBody.hidden, false, "audit toggle did not reveal the evidence body");
  assert.strictEqual(elements.publicEvidenceToggle["aria-expanded"], "true", "expanded audit toggle has incorrect accessibility state");
  assert(
    elements.publicEvidenceList.innerHTML.includes("telemetry · 仅证据"),
    "excluded telemetry disappeared from the inspectable evidence ledger",
  );

  densityButtons.find((button) => button.dataset.matrixDensity === "standard").emit("click");
  assert.strictEqual(elements.matrixView.dataset.density, "standard", "density switch did not update matrix layout state");
  assert.strictEqual(storage.get("fmb-matrix-density"), "standard", "density preference was not persisted");

  modeTabs.find((tab) => tab.dataset.mode === "runs").emit("click");
  assert(!elements.runTableBody.innerHTML.includes("direct-model-only"), "System Runs leaked a model-only row");
  assert(elements.runTableBody.innerHTML.includes("harness-inferred-system"), "agent harness row was not inferred as system");
  assert(elements.runTableBody.innerHTML.includes("system-tail-0"), "system benchmark row was not inferred as system");
  assert.strictEqual((elements.runTableBody.innerHTML.match(/class="run-row"/g) || []).length, 50);
  assert(elements.runTableBody.innerHTML.includes('data-run-page="1"'), "bounded table page has no next-page control");
  assert.strictEqual(elements.runCardsView.innerHTML, "", "table view must not synchronously build run cards");
  assert.strictEqual(elements.runCountLabel.textContent, "1–50 / 62");

  runTabs.find((tab) => tab.dataset.runView === "cards").emit("click");
  assert.strictEqual(elements.runTableBody.innerHTML, "", "card view must release the hidden run table rows");
  assert.strictEqual((elements.runCardsView.innerHTML.match(/class="run-card"/g) || []).length, 50);
  assert(!elements.runCardsView.innerHTML.includes("direct-model-only"), "run cards leaked a model-only row");

  elements.searchInput.value = "system-tail-60";
  elements.searchInput.emit("input");
  assert(elements.runCardsView.innerHTML.includes("system-tail-60"), "search did not reach a row beyond the first page");
  assert.strictEqual((elements.runCardsView.innerHTML.match(/class="run-card"/g) || []).length, 1);

  documentClick({
    closest(selector) {
      if (selector === "a") return null;
      if (selector === "[data-run]") return { dataset: { run: "system-tail-60" } };
      return null;
    },
  });
  assert(elements.drawerContent.innerHTML.includes("tail-marker-60"), "filtered system row detail is not reachable");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
