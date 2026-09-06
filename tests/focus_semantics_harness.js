"use strict";
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const elements = {};
const element = id => elements[id] ||= { innerHTML:"", textContent:"", hidden:false, value:"", dataset:{}, style:{}, classList:{add(){},remove(){},toggle(){}}, setAttribute(){}, querySelector(){return null;} };
const sandbox = {
  document: {getElementById:element, querySelectorAll:()=>[], querySelector:()=>null},
  console, Map, Set, Date, Intl, URL, URLSearchParams,
};
vm.createContext(sandbox);
const script = fs.readFileSync(process.argv[2], "utf8").replace("  boot();", "  globalThis.testAPI = { state, normalise, normaliseEvidence, buildRuntimeIndexes, filteredBenchmarks, filteredRuns, renderMatrix, render, modelMarkup, chooseEvidence, scoreTint, heatRanges, FOCUS };");
vm.runInContext(script, sandbox);
const a = sandbox.testAPI;
assert.strictEqual(a.FOCUS.science.ids[0], "terminal-bench-science");
assert.strictEqual(a.FOCUS.core.ids[0], "terminal-bench-science");
const percent = {id:"percent",metric:"accuracy",unit:"%",direction:"higher"};
const alpha = markup => Number(markup.match(/--score-tint:([0-9.]+)/)?.[1]);
for (const value of [null, undefined, "", NaN]) assert.strictEqual(a.scoreTint({value},percent), "");
assert(alpha(a.scoreTint({value:0},percent)) < alpha(a.scoreTint({value:30},percent)));
assert(alpha(a.scoreTint({value:30},percent)) < alpha(a.scoreTint({value:100},percent)));
assert.strictEqual(a.scoreTint({value:30},percent), a.scoreTint({value:0.3},{...percent,unit:"fraction"}));
const rank = {id:"rank",metric:"rank",unit:"rank",direction:"lower"};
const ranges = a.heatRanges([1,10].map(value => ({benchmark:rank,entry:{value}})));
assert(alpha(a.scoreTint({value:1},rank,ranges)) > alpha(a.scoreTint({value:10},rank,ranges)));
assert.strictEqual(a.scoreTint({value:1},{...rank,metric:"other"},ranges), "", "different metrics share an unbounded color scale");
assert(!a.scoreTint({value:5},rank,a.heatRanges([{benchmark:rank,entry:{value:5}}])).includes("NaN"));
assert.strictEqual(a.normaliseEvidence({value:null,rawValue:0}).value, null, "an unconfirmed source zero became a score");
const raw = {
  models: [{id:"m", name:"Frontier M", provider:"Maker", status:"active", sourceIds:["model-source"], scores: {
    "livebench-amps-hard": {value:98, status:"reported", sourceUrl:"https://example.org/subtest"},
    "ale-bench": {value:2000,status:"reported", sourceUrl:"https://example.org/ale"}
  }}],
  benchmarks: [
    {id:"gpqa-diamond",metric:"accuracy"},
    {id:"agents-last-exam",evaluationMode:"system"},
    {id:"ale-bench",metric:"performance",unit:"score",evaluationMode:"system"},
    {id:"livebench",metric:"Global average"},
    {id:"livebench-amps-hard",metric:"amps-hard"},
    {id:"irrelevant",metric:"score"}
  ],
  sources:[{id:"model-source",url:"https://example.org/model"}],
  runs:[
    {id:"ale16",modelId:"m",benchmarkId:"ale-bench",metric:"performance",sourceId:"src-ale-bench",value:2000,subjectType:"system",protocol:{view:"all",self_refine_iterations:16}},
    {id:"ale1",modelId:"m",benchmarkId:"ale-bench",metric:"performance",sourceId:"src-ale-bench",value:1300,subjectType:"system",protocol:{view:"all",self_refine_iterations:1}},
    {id:"unrelated",modelId:"m",benchmarkId:"irrelevant",value:90,subjectType:"system"},
  ],
};
a.state.data = a.normalise(raw); a.state.indexes = a.buildRuntimeIndexes(a.state.data);
a.state.preset="all";
assert(a.filteredBenchmarks().some(b=>b.id==="agents-last-exam"), "core omitted ALE");
assert(!a.filteredBenchmarks().some(b=>b.id==="irrelevant"), "focus leaked unrelated bench");
a.state.focus="all";
a.renderMatrix();
const liveCell = elements.matrixBody.innerHTML.match(/<td[^>]*data-benchmark-group="livebench"[^>]*>[\s\S]*?<\/td>/)?.[0];
assert(liveCell && !liveCell.includes(">98<"), "LiveBench subtask impersonated total");
assert(elements.matrixBody.innerHTML.includes('href="https://example.org/ale"'), "score source missing");
assert(elements.matrixBody.innerHTML.includes('--score-tint:'), "matrix lacks score backgrounds");
assert(a.modelMarkup(a.state.data.models[0]).includes('href="https://example.org/model"'), "official model link missing");
a.state.mode="runs"; a.state.focus="or";
assert(a.filteredRuns().some(r=>r.id==="ale16"), "summary omitted SR16");
assert(!a.filteredRuns().some(r=>r.id==="ale1"), "summary mixed refine budgets");
assert(!a.filteredRuns().some(r=>r.id==="unrelated"), "no preset bypassed focus");
a.render();
assert(elements.runTableBody.innerHTML.includes('--score-tint:'), "system table lacks score backgrounds");
a.state.allConfigurations=true;
assert(a.filteredRuns().some(r=>r.id==="ale1"), "full configurations lost history");
const chosen=a.chooseEvidence([
 {sourceId:"src-ale-bench",value:9999,protocol:{view:"short",self_refine_iterations:1}},
 {sourceId:"src-ale-bench",value:2000,protocol:{view:"all",self_refine_iterations:16}}
]);
assert.strictEqual(chosen.value,2000,"headline selected a best score, not fixed protocol");
console.log("Focus, quick links, ALE protocol and LiveBench aggregate regressions passed.");
