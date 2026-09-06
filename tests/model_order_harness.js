"use strict";
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const root = path.resolve(__dirname, "..");
function load(file, end, exports) {
  const elements = {};
  const sandbox = {
    document: {getElementById: id => elements[id] ||= {value:"", innerHTML:"", textContent:"", hidden:false, style:{}, dataset:{}, classList:{add(){},remove(){},toggle(){}}, setAttribute(){}, querySelector(){return null;}}, querySelectorAll:()=>[], querySelector:()=>null},
    console, Map, Set, Date, Intl, URL, URLSearchParams,
  };
  vm.createContext(sandbox);
  const source = fs.readFileSync(path.join(root, file), "utf8");
  assert(source.includes(end), "test seam is missing");
  vm.runInContext(source.replace(end, `globalThis.api = {${exports}};`), sandbox);
  return sandbox.api;
}
const app = load("app.js", "  boot();", "state, normalise, buildRuntimeIndexes, filteredModels, filteredRuns, resetFilters");
const directory = load("models.js", "  bindEvents();\n  loadData().then(applyData).catch(showLoadError);", "state, normaliseModel, filteredModels, resetFilters");
assert.strictEqual(app.state.sort, "recommended");
assert.strictEqual(directory.state.sort, "recommended");
const models = [
  {id:"other", name:"A other", provider:"Other", displayOrder:2, release:"2026-09-04", status:"active", scores:{"terminal-bench-science":{value:99}}},
  {id:"fable", name:"B Fable", provider:"Anthropic", displayOrder:1, release:"2026-09-01", status:"active"},
  {id:"gpt", name:"C GPT", provider:"OpenAI", displayOrder:0, release:"2026-09-03", status:"active"},
];
const raw = {models, benchmarks:[{id:"terminal-bench-science", evaluationMode:"system", metric:"accuracy"}], runs: models.map((model, i) => ({id:model.id, modelId:model.id, modelName:model.name, benchmarkId:"terminal-bench-science", metric:"accuracy", value:100-i, cost:1+i, observedAt:model.release, subjectType:"system"}))};
app.state.data = app.normalise(raw);
app.state.indexes = app.buildRuntimeIndexes(app.state.data);
app.state.preset = "all";
directory.state.models = models.map(directory.normaliseModel);
const ids = rows => Array.from(rows, row => row.id);
for (const surface of [app, directory]) {
  assert.deepStrictEqual(ids(surface.filteredModels()), ["gpt", "fable", "other"]);
  surface.state.sort = "name";
  assert.deepStrictEqual(ids(surface.filteredModels()), ["other", "fable", "gpt"]);
  surface.state.sort = "recent";
  assert.deepStrictEqual(ids(surface.filteredModels()), ["other", "gpt", "fable"]);
}
app.state.sort = "coverage";
assert.strictEqual(app.filteredModels()[0].id, "other");
app.state.mode = "runs";
app.state.sort = "recommended";
assert.deepStrictEqual(ids(app.filteredRuns()), ["gpt", "fable", "other"]);
for (const sort of ["score-desc", "cost", "run-recent", "name"]) {
  app.state.sort = sort;
  assert.strictEqual(app.filteredRuns()[0].id, "other", `${sort} was overridden by preference`);
}
app.resetFilters();
assert.strictEqual(app.state.sort, "recommended");
directory.resetFilters();
assert.strictEqual(directory.state.sort, "recommended");

// Exercise the exact generated payload: normalization must preserve displayOrder.
const real = JSON.parse(fs.readFileSync(path.join(root, "data/derived/site.json"), "utf8"));
const featured = JSON.parse(fs.readFileSync(path.join(root, "data/presentation/model-order.json"), "utf8")).featured_models;
app.state.data = app.normalise(real);
app.state.indexes = app.buildRuntimeIndexes(app.state.data);
app.state.preset = "all";
app.state.sort = "recommended";
app.state.runBenchmark = "terminal-bench-science";
directory.state.models = real.catalogModels.map(directory.normaliseModel);
directory.state.sort = "recommended";
assert.deepStrictEqual(ids(app.filteredModels()).slice(0, featured.length), featured);
assert.deepStrictEqual(ids(directory.filteredModels()).slice(0, featured.length), featured);
assert.deepStrictEqual(Array.from(new Set(app.filteredRuns().map(row => row.modelId))).slice(0, featured.length), featured);
console.log("Presentation preference, historical fallback and explicit sorts passed on all three views.");
