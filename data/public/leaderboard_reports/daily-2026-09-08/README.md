# Daily public disclosures — 2026-09-08

149 source-backed records for existing current-catalog models, published under the owner's standing maintenance authorization. These are **披露 · 未复现**, not approved observations or 149 independently verified runs.

| Source | Records | Scope |
| --- | ---: | --- |
| [SakanaAI ALE-Bench](https://sakanaai.github.io/ALE-Bench-Leaderboard/) | 30 | GPT-6 Astra max: five self-refine budgets, three views, performance/rank kept separate |
| [Arena official HF dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset) | 110 | Agent IPS, text and webdev ratings; category, original model variants, sample metadata and reported dates preserved |
| [Epoch benchmark export](https://epoch.ai/benchmarks/use-this-data) | 9 | Five GPT-6 Astra DeepSWE/mini-swe-agent configurations and four updated FrontierMath Tier 4 v2 disclosures |

The default ALE-Bench summary remains **self-refine 16 / all / performance**: this source reports **3128.1** for GPT-6 Astra max. Other settings are available separately, not selected by their maximum score. Unknown benchmark/judge versions and evaluation dates stay unknown; implementation version hints are not benchmark versions. The external Epoch ALE-Bench table is not substituted for this official configuration.

Epoch now reports Tier 4 v2 values of 97.6% for GPT-6 Astra high/xhigh/max and 90.2% for Fable 5 max. Previous disclosures (95.121951…% and 87.804878…%) remain in history with their original receipts. These are source updates, not evidence of new runs or a causal model improvement. DeepSWE remains its own benchmark, not SWE-bench Verified/Pro.

Each source directory contains original selected candidate rows and a focused manifest with exact locators, retrieval time, payload hash and parser metadata. `snapshot_dir` refers to the original local fetch receipt; full payloads are not bundled. Arena retrieval remained capped at 100 rows per config, explicitly retaining truncation warnings; this is not full-Arena coverage. Initial incomplete Epoch/LiveBench transfers recovered on a normal retry, with both attempts retained locally.

Semantic selection compared source/model ref/benchmark/version/metric/unit/subject/harness/protocol/value, excluding 3,175 locator-only new IDs. Unresolved model identities, non-current models, and other Epoch tables needing unit or agent-context classification remain in the local audit rather than being guessed into the matrix. Existing heuristic alias mappings retain their uncertainty flags. No catalog, approved observations or model-order configuration changed; current OpenAI/Anthropic priority and manual sorting remain intact.
