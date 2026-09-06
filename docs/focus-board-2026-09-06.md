# Focus board update · 2026-09-06

## Scope and presentation

Only Frontier Model Bench changed. The sibling Optimization Solver Bench is untouched.
Evaluations now opens directly on Model Matrix / Agent Systems. Core has 8 columns;
OR has 4; math has 3; science has 5. Search/provider remain visible; advanced
filters, all configurations, history and the evidence ledger are collapsed.
Model documentation, benchmark documentation and score sources are direct links.

Empty current-model LiveBench/AIME/HMMT columns are not shown by default. Their
historical data remains in All, the benchmark directory and the evidence ledger.
LiveBench task scores cannot substitute for Global Average.

## Public evidence, not independent reproduction

- Terminal-Bench Science 0.1 is first in Core and Science. Its official homepage
  API supplied 12 system results (70 tasks × 3 trials), including Gemini 3.8
  Flash and the 0813 DeepSeek V4 Pro release. Every score retains harness,
  effort, aggregate uncertainty, domain breakdown and a Harbor Hub row link.
  Website edit timestamps are not presented as evaluation dates.
- ALE-Bench official aggregate JSON: 3,780 fetched candidates; 2,490 mapped
  records across 71 catalog releases. Default representative configuration is
  self-refine 16 / all / performance, never the highest observed number.
- FrontierMath v2 CSVs have independent benchmark IDs for Tiers 1–3 and Tier 4.
  The public union covers 52 and 43 releases, respectively.
- SciCode, ProofBench and CritPt public evidence is visible in the focused
  domains. SciCode fractions retain three decimal places in the matrix.
- ReasLab OptArena: 176 candidate dataset records; 66 mapped records for four
  catalog releases, including separate thinking settings. Three ambiguous raw
  zeros remain missing. Current headline OR datasets are OptMATH, IndustryOR
  and MIPLIB-NL; this is not the traditional MIPLIB solver-speed leaderboard.
- Four newly cataloged releases: GPT-6 Astra, Claude Fable 5.1, Gemini 3.8 Flash,
  Muse Spark 1.3. Model/profile source links are recorded in the registry.

Sources: [Terminal-Bench Science](https://www.terminal-bench-science.ai/),
[ALE-Bench](https://sakanaai.github.io/ALE-Bench-Leaderboard/),
[Epoch Benchmarking Hub](https://epoch.ai/benchmarks),
[SciCode](https://scicode-bench.github.io/),
[ProofBench](https://www.vals.ai/benchmarks/proof_bench),
[CritPt](https://epoch.ai/benchmarks/critpt),
[OptArena](https://arena.reaslab.io/).

The union contains 13,226 mapped public rows and preserves all 31,455 historical
IDs from the preceding mapped/unmapped layers. This is a count of records, including
configurations and historical reports, not independent experiments. No canonical
approved observations changed. Reported version/date fields remain unknown when
not disclosed; source raw values and questionable dates stay in the audit layer.

## Verification

- 93 automated tests passed; strict validation: zero errors, zero warnings.
- TB-Science live fetch: 12 candidates, no errors. Existing source dry-run from
  the preceding pass: 20 sources, 19 successful, 1 disabled, zero errors.
- Final local VM with real data: parse + normalization + indexing approximately
  929 ms; core rendering 225 ms; domain switches 30–100 ms. These numbers do not
  include network transfer, browser layout or painting.
- Default matrix: core 48 models / 8 columns; OR 73 models with evidence /
  4 columns; math 48 / 3; science 48 / 5. Science includes all 12 TB-Science
  scores in both matrix and system table. Non-browser VM checks confirmed
  backgrounds, official links and model/harness identity; science render 86 ms.
- Restrained teal backgrounds use fixed percent/fraction scales, or the current
  same-metric range for unbounded performance/rank. Missing stays neutral;
  lower-is-better reverses the shade. Color is not a verification badge.
- This follow-up is authorized for GitHub publication. The Pages workflow now
  runs the complete regression suite before deployment.
