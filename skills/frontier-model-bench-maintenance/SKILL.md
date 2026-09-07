---
name: frontier-model-bench-maintenance
description: "Maintain Frontier Model Bench: fetch source-backed public scores, preserve evidence and history, update the focused catalog/order, validate and publish routine updates under the owner's standing authorization without promoting unverified results to approved."
---

# Frontier Model Bench Maintenance

Use this skill when the user asks to refresh the Frontier Model Bench, fill missing scores, inspect leaderboard changes, update the model catalog, or prepare a maintenance PR.

## Standing publication authorization

On 2026-09-07 the repository owner instructed: “以后直接发布，有问题再改”. Routine public/reported evidence updates, source-backed catalog additions, presentation ordering, and relevant corrections should therefore be committed and pushed to this repository's existing GitHub Pages flow after validation, without another review request. This replaces the old candidate-only publication gate, not the distinction between public reports and approved observations. It does not authorize paid evaluation, writes to other repositories, or bypassing access/branch protections.

Read the publication contract in `docs/maintenance-plan.md` section 0. Check status/diff, publish only task-owned changes, verify the exact pushed SHA's CI/Pages and live data, then report meaningful changes briefly. No semantic change means no publication or notification. Fix discovered problems directly within this task's scope; preserve history and use forward fixes or a scoped revert commit, never force-push/hard-reset. Ask only when ambiguity, user changes, permissions, or an unsafe recovery genuinely prevent progress.

## Scope and invariants

- Work only in the Frontier Model Bench repository. Never reorganize, delete, or overwrite `/Users/huangcunxin/Work/AI/raw` or the personal Hugo site.
- Read `docs/maintenance-plan.md` first when it exists, then inspect `git status` and the current generated snapshot.
- Keep the entity boundary explicit: `family → release → endpoint → harness/agent → run`.
- A direct/model observation and a tool-using/agentic system run are different subjects. SWE-bench, Terminal-Bench, BFCL, τ-bench, OSWorld, BrowserGym and CyberGym require a non-null harness/system context.
- Never turn `candidate` into `approved` implicitly. Do not overwrite an observation; append a new row and mark the old row superseded/retracted when a correction is accepted.
- Missing is `value: null` with a reason (or no observation), never `0`, `—`, or an invented estimate. Unknown parameters, price, latency and context remain null.
- Every promoted value needs a source URL/ID, benchmark version, metric/unit, protocol, observed/published dates when known, evidence level, and comparability. Preserve raw source snapshots only when their license permits redistribution; otherwise keep URL, locator, retrieval metadata and hash.
- Adapter output may be annotated `exact_alias` only when the CLI finds one exact catalog id/name/alias. Do not guess ambiguous identities; preserve unresolved model refs outside the canonical matrix. Existing heuristic/public mappings must keep their uncertainty labels.

## Operating modes

1. **Audit** — run the validator and derived builder; report catalog-only models, missing benchmark cells, stale sources, conflicts, invalid aliases and coverage changes. This mode is read-only.
2. **Fetch** — use the repository adapters (`python3 scripts/fetch.py list` and `python3 scripts/fetch.py check --dry-run` when available). Prefer official APIs, official Git repositories/raw JSON, and reproducible benchmark exports. Save immutable raw metadata and candidate records; do not edit approved observations in place.
3. **Review/promotion** — first make a bounded review packet with `python3 scripts/review_candidates.py --input-dir artifacts/fetch --output-dir artifacts/review --limit 50`. Compare candidate rows against the source locator and protocol. The packet is a read-only scaffold with `decision: pending`; it never promotes a row. Promote only source-backed rows after human review, with a small auditable diff. Keep provider self-reports at the appropriate evidence tier and mark cross-protocol comparisons conditional.
4. **Catalog maintenance** — add a concrete release/endpoint only when an official identity source exists. Keep aliases and speed/reasoning variants explicit; do not inflate family counts by treating an alias as a new model.
5. **Public publication** — select substantive new/changed source results, not locator/retrieval-only ID churn. Save a versioned source receipt, merge with the complete public/unmapped/alternatives history via `scripts/merge_public_evidence.py`, check prior IDs/hashes are retained, rebuild and validate, then commit/push directly and verify deployment. Unknown protocol details stay unknown with `conditional` comparability; this mode does not need human canonical promotion or a rerun of each reported score. Keep incomplete candidates separately and publish the other valid updates.

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
python3 -m unittest discover -s tests -q
git diff --check
```

For data-only updates use the existing runtime/semantic harnesses to check ordering, score/source details and missing-value semantics; no screenshot or redesign is needed. Browser interaction testing is for explicitly requested QA or actual interaction changes. Report relevant counts and failures, without asking the owner to approve an ordinary publication. Do not claim completion until the generated index, CI and live Pages data have been checked.
