# Public leaderboard update — 2026-09-10

242 public disclosures for existing models, **披露 · 未复现**. Publication is not canonical approval or independent reproduction.

- [Agents' Last Exam official public API](https://agents-last-exam.org/api/demo/leaderboard): 168 records — GPT-6 Astra (144) and Muse Spark 1.3 (24), all with Codex harness. Preserve ALE-v1, 12 source splits/tracks, source reasoning variants, and separate average-score/pass-rate metrics. Missing evaluation/publication dates and Muse's unspecified reasoning variant remain unknown. These are configuration/metric records, not 168 independent runs. This is Agents' Last Exam, not SakanaAI ALE-Bench.
- [Arena official HF dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset): 74 new/changed disclosures — 29 Agent IPS and 45 WebDev Bradley–Terry ratings, with source date 2026-09-08. Retain category, sample metadata and original model/effort names. IPS/rating is not accuracy, and heuristic identity mappings retain their uncertainty labels.

Both sources were retrieved at `2026-09-09T17:01:04Z`. Each directory preserves selected raw candidates and a focused manifest with source URL, exact locator, retrieval time, parser and payload hash. Full payloads are not bundled; `snapshot_dir` refers to the original local receipt location. Arena stayed capped at 100 rows per config with explicit truncation warnings, so this is not exhaustive Arena coverage.

Semantic comparison excluded 4,731 locator-only new IDs. The complete historical public/unmapped/alternatives baseline is retained, including old ratings and source receipts; source rows disappearing from a rolling page are not treated as retractions. Unknown model aliases and external tables needing unit/protocol classification remain in the local audit. No catalog, approved observations, focused column selection or preferred model ordering changed.
