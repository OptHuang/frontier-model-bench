---
name: frontier-model-bench-maintenance
description: "Maintain the Frontier Model Bench registry and evidence-backed benchmark data: audit missing or stale observations, run public-source adapters, prepare candidate diffs, and validate the static index without silently changing approved history."
---

# Frontier Model Bench Maintenance

Use this skill when the user asks to refresh the Frontier Model Bench, fill missing scores, inspect leaderboard changes, update the model catalog, or prepare a maintenance PR.

## Scope and invariants

- Work only in the Frontier Model Bench repository. Never reorganize, delete, or overwrite `/Users/huangcunxin/Work/AI/raw` or the personal Hugo site.
- Read `docs/maintenance-plan.md` first when it exists, then inspect `git status` and the current generated snapshot.
- Keep the entity boundary explicit: `family → release → endpoint → harness/agent → run`.
- A direct/model observation and a tool-using/agentic system run are different subjects. SWE-bench, Terminal-Bench, BFCL, τ-bench, OSWorld, BrowserGym and CyberGym require a non-null harness/system context.
- Never turn `candidate` into `approved` implicitly. Do not overwrite an observation; append a new row and mark the old row superseded/retracted when a correction is accepted.
- Missing is `value: null` with a reason (or no observation), never `0`, `—`, or an invented estimate. Unknown parameters, price, latency and context remain null.
- Every promoted value needs a source URL/ID, benchmark version, metric/unit, protocol, observed/published dates when known, evidence level, and comparability. Preserve raw source snapshots only when their license permits redistribution; otherwise keep URL, locator, retrieval metadata and hash.
- Adapter output may be annotated `exact_alias` only when the CLI finds one exact catalog id/name/alias; never promote a fuzzy or ambiguous match without human review.

## Operating modes

1. **Audit** — run the validator and derived builder; report catalog-only models, missing benchmark cells, stale sources, conflicts, invalid aliases and coverage changes. This mode is read-only.
2. **Fetch** — use the repository adapters (`python3 scripts/fetch.py list` and `python3 scripts/fetch.py check --dry-run` when available). Prefer official APIs, official Git repositories/raw JSON, and reproducible benchmark exports. Save immutable raw metadata and candidate records; do not edit approved observations in place.
3. **Review/promotion** — first make a bounded review packet with `python3 scripts/review_candidates.py --input-dir artifacts/fetch --output-dir artifacts/review --limit 50`. Compare candidate rows against the source locator and protocol. The packet is a read-only scaffold with `decision: pending`; it never promotes a row. Promote only source-backed rows after human review, with a small auditable diff. Keep provider self-reports at the appropriate evidence tier and mark cross-protocol comparisons conditional.
4. **Catalog maintenance** — add a concrete release/endpoint only when an official identity source exists. Keep aliases and speed/reasoning variants explicit; do not inflate family counts by treating an alias as a new model.

## Arena and leaderboard policy

- Human-preference Arena/Elo is a separate metric family, not an accuracy score and not part of a cross-benchmark total. Record arena date, category, vote/sample information, rating method and source snapshot.
- If a site has no stable public API/export, do not scrape interactive or authenticated pages. Record a blocked/stale source and leave a candidate task for manual export or an approved snapshot.
- Third-party aggregators are discovery inputs only unless their methodology, license and snapshot provenance are explicit; use a lower evidence tier and `conditional` comparability.
- Agents' Last Exam (ALE-V1) is a system benchmark: keep the source harness, effort/variant, environment track and split with each Pass Rate/partial-Score candidate. Do not collapse it into a model-only cell. ALE-Bench (SakanaAI) is a separate algorithm-engineering benchmark and must use a different catalog id.

## Verification and handoff

After any data or adapter change, run:

```bash
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
git diff --check
```

If a browser-facing change is involved, smoke-test Model Atlas, System Runs, preset mode switching, details/source links, missing-value semantics and a narrow mobile viewport. Report exact counts, source failures, candidate files, commit/PR status and anything still requiring the user's decision. Do not claim the refresh is complete until the generated index, CI and (when requested) the live Pages URL have been checked.
