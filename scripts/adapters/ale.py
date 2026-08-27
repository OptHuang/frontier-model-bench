"""Adapter for the official Agents' Last Exam (ALE-V1) leaderboard API.

The public ALE page reports *agent systems*, rather than model-only runs.  A
row therefore keeps the evaluator harness, the source harness/effort variant,
and the split together.  The adapter emits an auditable candidate for the
source's pass rate; score, resource use, and all run counters stay in
``metadata`` so a later reviewer can choose the appropriate comparison view.

This module deliberately does not append to ``data/observations``.  Scheduled
fetches are safe even if the live endpoint changes shape: malformed rows are
reported as warnings and no score is invented.
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import Adapter, AdapterRun, SourceSpec, json_loads, parse_number, slugify


class AgentsLastExamAdapter(Adapter):
    """Parse ``/api/demo/leaderboard`` from ``agents-last-exam.org``.

    ALE publishes several tracks (for example ``full/last-exam`` and
    ``unlicensed/near-term``) in one response.  They intentionally map to one
    catalog benchmark, ``agents-last-exam``, with ``ALE-v1`` and the exact
    track retained in both ``protocol`` and ``metadata``.  This keeps the
    dashboard from creating a dozen nearly-identical columns while preserving
    enough context for a reviewer to split them later.
    """

    ENDPOINT = "https://agents-last-exam.org/api/demo/leaderboard"
    LEADERBOARD_URL = "https://agents-last-exam.org/leaderboard"
    SOURCE_ID = "agents-last-exam"
    BENCHMARK_REF = "agents-last-exam"
    BENCHMARK_VERSION_ID = "agents-last-exam@v1"
    BENCHMARK_VERSION = "ALE-v1"

    # These are the canonical harness ids already present in this repository.
    # New source harness names remain visible as ``source_harness`` and use
    # the generic ALE evaluator id until a maintainer adds a dedicated entry.
    HARNESS_ALIASES = {
        "codex": "codex",
        "claude_code": "claude-code",
        "kimi_code": "kimi-code",
    }

    def __init__(self, *, split: str | None = None) -> None:
        self.split = split.strip() if isinstance(split, str) and split.strip() else None
        self.spec = SourceSpec(
            id=self.SOURCE_ID,
            label="Agents' Last Exam · ALE-V1 official leaderboard API",
            kind="official_api",
            url=self.ENDPOINT,
            cadence="daily",
            notes=(
                "Official ALE-V1 aggregate endpoint. Rows are agent-system "
                "candidates; retain split, harness, effort variant, score, "
                "cost, runtime, and token provenance before promotion."
            ),
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        document = json_loads(payload)
        if isinstance(document, Mapping):
            rows = document.get("rows")
        elif isinstance(document, list):
            # Accept a bare array as a convenient fixture/export form.
            rows = document
        else:
            rows = None
        if not isinstance(rows, list):
            raise ValueError("expected an object with a rows array")

        candidates: list[dict[str, Any]] = []
        for index, item in enumerate(rows):
            if not isinstance(item, Mapping):
                run.warnings.append(f"rows[{index}]: ignored non-object entry")
                continue
            row = dict(item)
            split = _text(_first(row, "split", "track")) or "unknown"
            if self.split and split != self.split:
                continue
            model_ref = _text(_first(row, "model", "modelId", "model_id"))
            harness_source = _text(_first(row, "harness", "agent", "scaffold"))
            if not model_ref:
                run.warnings.append(f"rows[{index}]: missing model")
                continue
            if not harness_source:
                run.warnings.append(f"rows[{index}]: missing harness")

            variant = _text(_first(row, "harnessVariant", "harness_variant", "variant"))
            canonical_harness = self.HARNESS_ALIASES.get(
                harness_source or "", "agents-last-exam"
            )
            source_flags = _source_flags(row)
            quality_flags = ["agent_system_score", "harness_specific", "split_specific"]
            for flag in source_flags:
                if isinstance(flag, str) and flag.strip():
                    quality_flags.append(f"source:{slugify(flag)}")
            if canonical_harness == "agents-last-exam" and harness_source:
                quality_flags.append("unregistered_source_harness")
            if not variant:
                quality_flags.append("missing_harness_variant")

            pass_rate_raw = _first(row, "passRate", "pass_rate")
            avg_score_raw = _first(row, "avgScore", "avg_score", "score")
            pass_rate = _display_percent(pass_rate_raw)
            avg_score = _display_percent(avg_score_raw)
            if pass_rate is None:
                quality_flags.append("missing_pass_rate")
            if avg_score is None:
                quality_flags.append("missing_avg_score")
            if _first(row, "observedAt", "observed_at", "date", "updatedAt") is None:
                # Retrieval time is not substituted for an observation date.
                quality_flags.append("missing_source_date")

            cost = _first(row, "totalCostUsd", "costUsd", "cost", "total_cost_usd")
            runtime = _first(
                row,
                "totalDurationS",
                "runtimeS",
                "runtime",
                "total_runtime_s",
            )
            input_tokens = _first(
                row, "totalInputTokens", "inputTokens", "input_tokens"
            )
            output_tokens = _first(
                row, "totalOutputTokens", "outputTokens", "output_tokens"
            )
            total_tokens = _first(row, "tokens", "totalTokens", "total_tokens")
            cost_source = _first(row, "costSource", "cost_source")
            runs = _first(row, "runs")
            tasks = _first(row, "tasks")
            split_tasks = _first(row, "splitTasks", "split_tasks")
            passes = _first(row, "passes")

            # A stable hint lets a reviewer create split-specific benchmark
            # records later without making the default matrix wider today.
            split_ref = f"agents-last-exam-v1-{slugify(split)}"
            locator = (
                f"rows[{index}];split={split};harness={harness_source or 'unknown'};"
                f"model={model_ref};variant={variant or 'unknown'}"
            )
            protocol = {
                "harness": canonical_harness,
                "evaluator": self.SOURCE_ID,
                "source_harness": harness_source,
                "harness_variant": variant,
                "benchmark_version": self.BENCHMARK_VERSION,
                "benchmark_version_id": self.BENCHMARK_VERSION_ID,
                "split": split,
                "split_track": split,
                "split_benchmark_ref": split_ref,
                "subject_type": "system",
                "cost_source": cost_source,
            }
            metadata = {
                # Keep both source spelling and normalized keys so downstream
                # reports can evolve without another network fetch.
                "split": split,
                "track": split,
                "harness": harness_source,
                "source_harness": harness_source,
                "harness_id": canonical_harness,
                "harness_variant": variant,
                "model": model_ref,
                "runs": runs,
                "tasks": tasks,
                "split_tasks": split_tasks,
                "splitTasks": split_tasks,
                "passes": passes,
                "pass_rate": pass_rate_raw,
                "passRate": pass_rate_raw,
                "pass_rate_percent": pass_rate,
                "avg_score": avg_score_raw,
                "avgScore": avg_score_raw,
                "avg_score_percent": avg_score,
                "cost": cost,
                "total_cost_usd": cost,
                "totalCostUsd": cost,
                "runtime": runtime,
                "total_runtime_s": runtime,
                "totalDurationS": runtime,
                "tokens": total_tokens,
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "total_input_tokens": input_tokens,
                "totalInputTokens": input_tokens,
                "output_tokens": output_tokens,
                "total_output_tokens": output_tokens,
                "totalOutputTokens": output_tokens,
                "cost_source": cost_source,
                "costSource": cost_source,
                "source_flags": source_flags,
                "source_status": "official_api_reported",
                "benchmark_version": self.BENCHMARK_VERSION,
                "benchmark_version_id": self.BENCHMARK_VERSION_ID,
                "split_benchmark_ref": split_ref,
                "source_row_index": index,
            }
            # Preserve a source-provided date if one is ever added, but do not
            # infer one from retrieval time.
            observed_at = _date_value(
                _first(row, "observedAt", "observed_at", "date", "updatedAt")
            )
            # ALE publishes two first-class metrics for each system row:
            # full-task Pass Rate and partial-credit Average Score.  Emit both
            # as separate candidates so a reviewer can promote either metric
            # without having to reconstruct the second value from metadata.
            metric_rows = [("pass_rate", pass_rate, pass_rate_raw, "primary")]
            has_avg_score = any(
                key in row for key in ("avgScore", "avg_score", "score")
            )
            if has_avg_score:
                metric_rows.append(("avg_score", avg_score, avg_score_raw, "secondary"))
            for metric_id, metric_value, metric_raw, metric_role in metric_rows:
                metric_metadata = dict(metadata)
                metric_metadata["metric_role"] = metric_role
                metric_metadata["metric_id"] = metric_id
                metric_locator = f"{locator};metric={metric_id}"
                candidate = self.make_candidate(
                    run,
                    model_ref=model_ref,
                    benchmark_ref=self.BENCHMARK_REF,
                    metric=metric_id,
                    value=metric_value,
                    unit="percent",
                    raw_value=metric_raw,
                    locator=metric_locator,
                    rank=_first(row, "rank"),
                    verified=None,
                    status="candidate",
                    evidence_level="A",
                    comparability="conditional",
                    protocol=protocol,
                    metadata=metric_metadata,
                    quality_flags=quality_flags,
                    observed_at=observed_at,
                )
                # Extra top-level references are useful to review tools while
                # the canonical observation schema remains untouched.
                candidate["benchmark_version_id"] = self.BENCHMARK_VERSION_ID
                candidate["harness_id"] = canonical_harness
                candidate["subject_type"] = "system"
                candidate["source_flags"] = source_flags
                candidates.append(candidate)
        return candidates


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    """Return the first present value, preserving explicit ``None``."""

    for key in keys:
        if key in row:
            return row[key]
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display_percent(value: Any) -> float | None:
    """Normalize ALE's fractional rates to the catalog's percent scale."""

    number, _ = parse_number(value)
    if number is None:
        return None
    # The live API uses [0, 1].  Accept an already-percent export as a
    # defensive compatibility measure, without changing the raw value.
    return number * 100 if -1 <= number <= 1 else number


def _date_value(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    # Keep a valid ISO date/datetime prefix; arbitrary labels stay absent.
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _source_flags(row: Mapping[str, Any]) -> list[Any]:
    value = _first(row, "flags", "qualityFlags", "quality_flags")
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


# Friendly aliases make the adapter discoverable to callers that use the
# abbreviation from the official site.
ALELeaderboardAdapter = AgentsLastExamAdapter
ALEV1Adapter = AgentsLastExamAdapter


def build_ale_adapters() -> dict[str, AgentsLastExamAdapter]:
    """Return the enabled official ALE-V1 adapter."""

    adapter = AgentsLastExamAdapter()
    return {adapter.spec.id: adapter}


__all__ = [
    "AgentsLastExamAdapter",
    "ALELeaderboardAdapter",
    "ALEV1Adapter",
    "build_ale_adapters",
]
