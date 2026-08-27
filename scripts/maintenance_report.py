#!/usr/bin/env python3
"""Build a read-only maintenance report for the benchmark dashboard.

The scheduled GitHub Action uses this script as a *candidate* pass.  It reads
the canonical registries and observations, checks freshness/coverage, and
writes JSON/Markdown reports under an output directory.  It never edits an
approved catalog or observation file and it never treats a missing value as a
zero.

Network checks are intentionally limited to source landing pages.  They are a
health signal, not a scraper: an adapter or a human review is still required
before a candidate observation can enter ``data/observations/results.jsonl``.
This keeps a flaky leaderboard, a changed HTML table, or a provider alias from
silently changing the public dashboard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "maintenance"
CURRENT_STATUSES = {"active", "preview", "restricted"}
APPROVED_STATUSES = {"published", "reported", "reproduced", "verified", "curated"}
IGNORED_STATUSES = {"candidate", "draft", "superseded", "retracted", "missing"}
DEFAULT_STALENESS_DAYS = 180
USER_AGENT = "frontier-model-bench-maintenance/0.1 (+https://github.com/OptHuang/frontier-model-bench)"


class MaintenanceError(RuntimeError):
    """A malformed registry that should fail the scheduled job."""


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceError(f"无法读取 {path}: {exc}") from exc


def as_records(payload: Any, key: str | None = None) -> list[dict[str, Any]]:
    value = payload.get(key, []) if key and isinstance(payload, Mapping) else payload
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                text = raw.strip()
                if not text or text.startswith("#"):
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise MaintenanceError(
                        f"JSONL 解析失败 {path}:{line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(value, Mapping):
                    raise MaintenanceError(
                        f"JSONL {path}:{line_number} 必须是 object"
                    )
                rows.append(dict(value))
    except OSError as exc:
        raise MaintenanceError(f"无法读取 {path}: {exc}") from exc
    return rows


def first_nonempty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def identifier(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value.strip() else None


def source_ids_for(row: Mapping[str, Any]) -> list[str]:
    values = row.get("source_ids", row.get("sourceIds"))
    if values is None:
        values = row.get("source_id", row.get("sourceId"))
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if isinstance(value, str) and value]


def iso_day(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str) and value:
        return value
    return None


def age_days(value: Any, today: date) -> int | None:
    parsed = iso_day(value)
    if parsed is None:
        return None
    return max(0, (today - parsed).days)


def url_ok(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def metric_for(benchmark: Mapping[str, Any]) -> dict[str, Any]:
    metrics = benchmark.get("metrics")
    if isinstance(metrics, list):
        wanted = benchmark.get("default_metric_id") or benchmark.get("metric")
        for metric in metrics:
            if isinstance(metric, Mapping) and metric.get("id") == wanted:
                return dict(metric)
        for metric in metrics:
            if isinstance(metric, Mapping):
                return dict(metric)
    return {
        "id": benchmark.get("metric") or "score",
        "label": benchmark.get("metricLabel") or benchmark.get("metric") or "score",
        "unit": benchmark.get("unit", "percent"),
        "scale": benchmark.get("scale", 100),
        "direction": benchmark.get("direction", "higher"),
    }


def default_version(benchmark: Mapping[str, Any]) -> str:
    explicit = benchmark.get("default_version_id") or benchmark.get("defaultVersionId")
    if isinstance(explicit, str) and explicit:
        return explicit
    versions = benchmark.get("versions")
    if isinstance(versions, list):
        for version in versions:
            if isinstance(version, Mapping) and version.get("status") == "active":
                if isinstance(version.get("id"), str):
                    return str(version["id"])
        for version in versions:
            if isinstance(version, Mapping) and isinstance(version.get("id"), str):
                return str(version["id"])
    return f"{benchmark.get('id', 'benchmark')}@v1"


def benchmark_mode(benchmark: Mapping[str, Any]) -> str:
    explicit = benchmark.get("evaluation_mode") or benchmark.get("evaluationMode")
    if explicit in {"direct", "system"}:
        return str(explicit)
    families = {
        str(benchmark.get("family", "")),
        str(benchmark.get("category", "")),
    }
    return "system" if families & {
        "coding-agent",
        "coding_agent",
        "tool-use",
        "computer-use",
        "cyber",
        "agent",
        "agents",
    } else "direct"


def source_url(source: Mapping[str, Any]) -> str | None:
    value = source.get("url") or source.get("source_url") or source.get("homepage")
    return str(value) if isinstance(value, str) and value else None


def source_threshold(source: Mapping[str, Any]) -> int:
    value = source.get("staleness_after_days") or source.get("stalenessAfterDays")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return int(value)
    return DEFAULT_STALENESS_DAYS


def source_label(source: Mapping[str, Any]) -> str:
    return str(source.get("label") or source.get("title") or source.get("publisher") or source.get("id") or "source")


def row_status(row: Mapping[str, Any]) -> str:
    return str(row.get("status") or "reported").lower()


def row_subject_type(row: Mapping[str, Any]) -> str:
    subject = row.get("subject")
    if isinstance(subject, Mapping) and subject.get("type") in {"model", "system"}:
        return str(subject["type"])
    harness = row.get("harness_id", row.get("harnessId"))
    # Legacy/direct rows may omit harness entirely. Only a concrete non-model
    # harness implies a system run.
    return "model" if harness in (None, "", "model-only") else "system"


def row_model_id(row: Mapping[str, Any]) -> str | None:
    return identifier(row.get("model_id", row.get("modelId")))


def row_benchmark_id(row: Mapping[str, Any]) -> str | None:
    return identifier(row.get("benchmark_id", row.get("benchmarkId")))


def public_row_model_id(row: Mapping[str, Any]) -> str | None:
    return identifier(row.get("canonicalModelId", row.get("canonical_model_id")))


def public_row_benchmark_id(row: Mapping[str, Any]) -> str | None:
    return identifier(row.get("benchmarkId", row.get("benchmark_id")))


def is_mapped_public_evidence(row: Mapping[str, Any]) -> bool:
    """Return whether a public row is a usable mapped score-review signal.

    Public/reported evidence never counts as canonical coverage.  This helper
    only prevents a mapped public score from being triaged as if no evidence
    existed at all.  Telemetry-only rows remain evidence details, not score
    coverage signals.
    """

    if not public_row_model_id(row) or not public_row_benchmark_id(row):
        return False
    if row.get("value") is None or row.get("matrixExcluded") is True:
        return False
    if str(row.get("status") or "reported").lower() in {
        "missing",
        "retracted",
        "superseded",
    }:
        return False
    return True


def is_approved(row: Mapping[str, Any]) -> bool:
    status = row_status(row)
    # A row in the canonical JSONL has already crossed the repository review
    # gate.  ``candidate``/``draft`` rows are deliberately excluded so an
    # unfinished handoff cannot hide a coverage gap.
    return status in APPROVED_STATUSES


def protocol_fingerprint(row: Mapping[str, Any]) -> str:
    protocol = row.get("protocol")
    if not isinstance(protocol, Mapping):
        protocol = {}
    compact = {
        str(key): value
        for key, value in protocol.items()
        if value is not None and value != ""
    }
    harness = row.get("harness_id", row.get("harnessId"))
    endpoint = row.get("endpoint_id", row.get("endpointId"))
    return json.dumps({"protocol": compact, "harness": harness, "endpoint": endpoint}, sort_keys=True, ensure_ascii=False, default=str)


def candidate_id(*parts: str) -> str:
    text = "|".join(parts)
    return "cand-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def suggested_harnesses(benchmark: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]) -> list[str]:
    """Suggest only a small, explainable harness set for a system gap."""

    mode = benchmark_mode(benchmark)
    if mode != "system":
        return ["model-only"]
    benchmark_id = str(benchmark.get("id", ""))
    observed = []
    for row in observations:
        if row_benchmark_id(row) == benchmark_id:
            value = row.get("harness_id", row.get("harnessId"))
            if isinstance(value, str) and value and value not in observed:
                observed.append(value)
    if observed:
        return sorted(observed)
    category = str(benchmark.get("category") or benchmark.get("family") or "")
    if category == "coding-agent":
        return ["mini-swe-agent", "swebench-official", "unspecified-reported"]
    return ["unspecified-reported"]


def check_source(url: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.1"},
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - URLs are registry data
            return {
                "status": "ok",
                "http_status": int(getattr(response, "status", 200)),
                "final_url": response.geturl(),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
    except HTTPError as exc:
        # Some sites reject HEAD but serve GET.  A bounded GET retry avoids
        # marking an otherwise healthy source as broken while keeping the
        # scheduled job read-only and cheap.
        # Do not retry 429: a scheduled job should respect a source's rate
        # limit and surface the response as a health signal.
        if exc.code in {405, 403, 406}:
            try:
                fallback = Request(
                    url,
                    headers={"User-Agent": USER_AGENT, "Range": "bytes=0-1023"},
                    method="GET",
                )
                with urlopen(fallback, timeout=timeout) as response:  # nosec B310
                    return {
                        "status": "ok",
                        "http_status": int(getattr(response, "status", 200)),
                        "final_url": response.geturl(),
                        "method": "GET",
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                    }
            except Exception as retry_exc:  # noqa: BLE001 - health must continue
                return {
                    "status": "error",
                    "http_status": exc.code,
                    "error": f"{type(retry_exc).__name__}: {retry_exc}",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                }
        return {
            "status": "error",
            "http_status": exc.code,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def markdown_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> str:
    if not rows:
        return "_无记录。_"

    def clean(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(clean(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def build_report(
    root: Path,
    today: date,
    check_sources: bool,
    timeout: float,
    max_sources: int,
) -> dict[str, Any]:
    catalog_dir = root / "data" / "catalog"
    model_payload = load_json(catalog_dir / "models.json", {})
    models = as_records(model_payload, "models")
    benchmarks = as_records(load_json(catalog_dir / "benchmarks.json", []))
    sources = as_records(load_json(catalog_dir / "sources.json", []))
    observations = load_jsonl(root / "data" / "observations" / "results.jsonl")
    public_evidence = load_jsonl(root / "data" / "public" / "evidence.jsonl")

    if not models:
        raise MaintenanceError("models catalog 为空或格式不正确")
    if not benchmarks:
        raise MaintenanceError("benchmarks catalog 为空或格式不正确")

    models_by_id = {str(item["id"]): item for item in models if identifier(item.get("id"))}
    benchmarks_by_id = {str(item["id"]): item for item in benchmarks if identifier(item.get("id"))}
    sources_by_id = {str(item["id"]): item for item in sources if identifier(item.get("id"))}
    current_models = [item for item in models if str(item.get("status", "active")) in CURRENT_STATUSES]
    active_benchmarks = [
        item
        for item in benchmarks
        if not item.get("status") or str(item.get("status")) in {"active", "published", "current"}
    ]
    featured_benchmarks = [item for item in active_benchmarks if bool(item.get("featured"))]
    if not featured_benchmarks:
        featured_benchmarks = active_benchmarks

    by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    public_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        model_id = row_model_id(row)
        benchmark_id = row_benchmark_id(row)
        if model_id and benchmark_id:
            by_cell[(model_id, benchmark_id)].append(row)
        if is_approved(row):
            for source_id in source_ids_for(row):
                by_source[source_id].append(row)
    for row in public_evidence:
        if not is_mapped_public_evidence(row):
            continue
        model_id = public_row_model_id(row)
        benchmark_id = public_row_benchmark_id(row)
        if model_id and benchmark_id:
            public_by_cell[(model_id, benchmark_id)].append(row)

    # A direct model score and a system run are different cells.  For a direct
    # benchmark we require model-only; for an agentic benchmark any approved
    # system run counts as coverage for that model/benchmark, while the run
    # still retains its exact harness in the System Runs view.
    def covered(model_id: str, benchmark: Mapping[str, Any]) -> list[dict[str, Any]]:
        mode = benchmark_mode(benchmark)
        rows = by_cell.get((model_id, str(benchmark.get("id"))), [])
        expected_version = default_version(benchmark)
        result = []
        for row in rows:
            if not is_approved(row):
                continue
            # A deliberate null/missing row is an audit fact, not score
            # coverage. Missing must remain distinct from zero.
            if row.get("value") is None:
                continue
            # A score from an older rolling snapshot is useful history, but it
            # does not satisfy the current benchmark cell.  Keep it visible in
            # the dashboard and surface a new candidate for the active
            # version instead of silently counting it as coverage.
            row_version = row.get("benchmark_version_id", row.get("benchmarkVersionId"))
            if row_version != expected_version:
                continue
            subject = row_subject_type(row)
            harness = row.get("harness_id", row.get("harnessId"))
            if mode == "direct" and (subject == "model" or harness == "model-only"):
                result.append(row)
            elif mode == "system" and subject == "system":
                result.append(row)
        return result

    candidates: list[dict[str, Any]] = []
    covered_featured = 0
    total_featured = len(current_models) * len(featured_benchmarks)
    covered_all = 0
    public_reported_gaps = 0
    no_public_evidence_gaps = 0
    featured_public_reported_gaps = 0
    featured_no_public_evidence_gaps = 0
    total_all = len(current_models) * len(active_benchmarks)
    for model in current_models:
        model_id = str(model.get("id"))
        for benchmark in active_benchmarks:
            benchmark_id = str(benchmark.get("id"))
            hits = covered(model_id, benchmark)
            is_featured = benchmark in featured_benchmarks
            if hits:
                covered_all += 1
                if is_featured:
                    covered_featured += 1
                continue
            source_ids = source_ids_for(benchmark)
            if not source_ids:
                source_ids = source_ids_for(model)
            urls = [source_url(sources_by_id[sid]) for sid in source_ids if sid in sources_by_id]
            urls = [url for url in urls if url]
            existing_rows = by_cell.get((model_id, benchmark_id), [])
            public_rows = public_by_cell.get((model_id, benchmark_id), [])
            expected_version = default_version(benchmark)
            existing_versions = sorted(
                {
                    str(row.get("benchmark_version_id", row.get("benchmarkVersionId")))
                    for row in existing_rows
                    if row.get("benchmark_version_id", row.get("benchmarkVersionId"))
                }
            )
            has_current_approved = any(
                is_approved(row)
                and row.get("benchmark_version_id", row.get("benchmarkVersionId")) == expected_version
                and row.get("value") is not None
                for row in existing_rows
            )
            has_current_pending = any(
                row.get("benchmark_version_id", row.get("benchmarkVersionId")) == expected_version
                and not is_approved(row)
                for row in existing_rows
            )
            if public_rows:
                reason = (
                    "已有已映射 public/reported evidence，但尚未复现或晋升 canonical；"
                    "请核对 benchmark version、protocol、subject/harness 和来源后再决定是否晋升。"
                )
                kind = "public_reported"
                public_reported_gaps += 1
                if is_featured:
                    featured_public_reported_gaps += 1
            elif existing_versions and not has_current_pending:
                reason = f"已有 observation，但版本不是当前 {expected_version}；请检查滚动 benchmark 的新快照。"
                kind = "missing"
                no_public_evidence_gaps += 1
                if is_featured:
                    featured_no_public_evidence_gaps += 1
            elif has_current_pending and not has_current_approved:
                reason = "已有 current-version candidate 尚未审阅；请先核对来源、协议和证据，不要重复录入。"
                kind = "missing"
                no_public_evidence_gaps += 1
                if is_featured:
                    featured_no_public_evidence_gaps += 1
            else:
                reason = "当前 release 尚无通过审阅的 observation；请先从来源快照生成 candidate，再人工确认 protocol/evidence。"
                kind = "missing"
                no_public_evidence_gaps += 1
                if is_featured:
                    featured_no_public_evidence_gaps += 1
            priority = "high" if is_featured else "normal"
            if str(model.get("status")) == "preview":
                priority = "high"
            candidates.append(
                {
                    "candidate_id": candidate_id(model_id, benchmark_id, default_version(benchmark), str(metric_for(benchmark).get("id"))),
                    "kind": kind,
                    "priority": priority,
                    "model_id": model_id,
                    "model_name": model.get("name") or model_id,
                    "model_status": model.get("status", "active"),
                    "benchmark_id": benchmark_id,
                    "benchmark_name": benchmark.get("name") or benchmark_id,
                    "benchmark_version_id": default_version(benchmark),
                    "metric_id": metric_for(benchmark).get("id") or "score",
                    "evaluation_mode": benchmark_mode(benchmark),
                    "suggested_harness_ids": suggested_harnesses(benchmark, by_cell.get((model_id, benchmark_id), [])),
                    "source_ids": source_ids,
                    "source_urls": urls,
                    "reason": reason,
                    "existing_observation_ids": [str(row.get("id")) for row in existing_rows if row.get("id")],
                    "existing_versions": existing_versions,
                    "public_evidence_count": len(public_rows),
                    "public_evidence_ids": [str(row.get("id")) for row in public_rows if row.get("id")],
                    "public_source_ids": sorted(
                        {
                            str(row.get("sourceId", row.get("source_id")))
                            for row in public_rows
                            if row.get("sourceId", row.get("source_id"))
                        }
                    ),
                    "public_evidence_urls": sorted(
                        {
                            str(url)
                            for row in public_rows
                            for url in (
                                row.get("evidenceUrl"),
                                row.get("sourcePageUrl"),
                                row.get("sourceUrl"),
                            )
                            if isinstance(url, str) and url
                        }
                    ),
                }
            )

    # Refresh candidates are deliberately separate from missing candidates.
    # They do not replace the old value; they tell a reviewer which source or
    # benchmark should be re-checked next.
    stale_observations: list[dict[str, Any]] = []
    for row in observations:
        if not is_approved(row):
            continue
        if row.get("value") is None:
            continue
        observed = row.get("observed_at", row.get("observedAt"))
        age = age_days(observed, today)
        if age is None:
            continue
        source_ids = source_ids_for(row)
        thresholds = [source_threshold(sources_by_id[sid]) for sid in source_ids if sid in sources_by_id]
        threshold = min(thresholds) if thresholds else DEFAULT_STALENESS_DAYS
        if age <= threshold:
            continue
        model_id = row_model_id(row) or "unknown-model"
        benchmark_id = row_benchmark_id(row) or "unknown-benchmark"
        benchmark = benchmarks_by_id.get(benchmark_id, {})
        model = models_by_id.get(model_id, {})
        source_urls = [source_url(sources_by_id[sid]) for sid in source_ids if sid in sources_by_id]
        stale_observations.append(
            {
                "candidate_id": candidate_id("refresh", str(row.get("id", ""))),
                "kind": "refresh",
                "priority": "high" if str(model.get("status")) in CURRENT_STATUSES else "normal",
                "observation_id": row.get("id"),
                "model_id": model_id,
                "model_name": model.get("name") or model_id,
                "benchmark_id": benchmark_id,
                "benchmark_name": benchmark.get("name") or benchmark_id,
                "observed_at": observed,
                "age_days": age,
                "staleness_after_days": threshold,
                "value": row.get("value"),
                "source_ids": source_ids,
                "source_urls": [url for url in source_urls if url],
                "reason": "已有 observation 超过来源 freshness 阈值；保留旧值，建议重新检查并追加新 observation。",
            }
        )
    candidates.extend(stale_observations)

    # Source health combines registry linkage/freshness with an optional
    # bounded HEAD/GET probe.  It never downloads leaderboard payloads.
    source_status: list[dict[str, Any]] = []
    ordered_sources = sorted(sources, key=lambda item: str(item.get("id", "")))
    for source_index, source in enumerate(ordered_sources):
        source_id = str(source.get("id", ""))
        linked = by_source.get(source_id, [])
        latest_dates = [iso_day(row.get("observed_at", row.get("observedAt"))) for row in linked]
        latest_dates = [item for item in latest_dates if item]
        latest = max(latest_dates).isoformat() if latest_dates else None
        age = age_days(latest, today)
        threshold = source_threshold(source)
        freshness = "unknown" if age is None else ("stale" if age > threshold else "fresh")
        url = source_url(source)
        probe: dict[str, Any] = {"status": "not_checked"}
        if source.get("enabled") is False:
            # Disabled/metadata-only sources (notably Arena) must not even be
            # probed. Their status is explicit so a reviewer can add a dated,
            # licensed export later without scraping the interactive app.
            probe = {"status": "disabled"}
        elif check_sources and source_index >= max_sources:
            probe = {"status": "skipped_limit"}
        elif check_sources and url:
            probe = check_source(url, timeout)
        elif check_sources and not url:
            probe = {"status": "error", "error": "registry source 缺少有效 URL"}
        source_status.append(
            {
                "source_id": source_id,
                "label": source_label(source),
                "kind": source.get("kind"),
                "url": url,
                "staleness_after_days": threshold,
                "latest_observed_at": latest,
                "age_days": age,
                "freshness": freshness,
                "linked_observations": len(linked),
                "probe": probe,
            }
        )

    probe_counts = Counter(item["probe"].get("status") for item in source_status)
    freshness_counts = Counter(item["freshness"] for item in source_status)
    errors = [
        f"source {item['source_id']}: {item['probe'].get('error', 'HTTP ' + str(item['probe'].get('http_status')))}"
        for item in source_status
        if item["probe"].get("status") == "error"
    ]
    warnings: list[str] = []
    if not check_sources:
        warnings.append("本次未进行网络探测；source freshness 仅根据 observation 日期估算。")
    if candidates:
        missing_count = sum(1 for item in candidates if item.get("kind") == "missing")
        public_reported_count = sum(1 for item in candidates if item.get("kind") == "public_reported")
        refresh_count = sum(1 for item in candidates if item.get("kind") == "refresh")
        warnings.append(
            f"发现 {len(candidates)} 个待处理 candidate（public reported 待 canonical 审阅 "
            f"{public_reported_count}，无 mapped public evidence {missing_count}，刷新 {refresh_count}）。"
        )
    if freshness_counts.get("stale"):
        warnings.append(f"有 {freshness_counts['stale']} 个来源按 registry 阈值过期。")
    if probe_counts.get("error"):
        warnings.append(f"有 {probe_counts['error']} 个来源网络探测失败；失败不会覆盖 approved 数据。")

    # ``green`` means no follow-up is currently needed.  Missing/stale cells
    # are expected in a curated snapshot but should still make the scheduled
    # report visible as ``amber``; only malformed input is fatal/``red``.
    status = "green"
    if errors or candidates or freshness_counts.get("stale"):
        status = "amber"
    if not models or not benchmarks:
        status = "red"
    health = {
        "schema_version": "maintenance-health@0.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of": today.isoformat(),
        "status": status,
        "network_checked": check_sources,
        "catalog": {
            "models": len(models),
            "current_models": len(current_models),
            "benchmarks": len(active_benchmarks),
            "featured_benchmarks": len(featured_benchmarks),
            "sources": len(sources),
            "observations": len(observations),
            "public_evidence": len(public_evidence),
        },
        "coverage": {
            "current_model_benchmark_cells": total_all,
            "covered_cells": covered_all,
            "missing_cells": total_all - covered_all,
            "public_reported_awaiting_review_cells": public_reported_gaps,
            "no_mapped_public_evidence_cells": no_public_evidence_gaps,
            "ratio": round(covered_all / total_all, 4) if total_all else 0,
            "featured_cells": total_featured,
            "featured_covered": covered_featured,
            "featured_missing": total_featured - covered_featured,
            "featured_public_reported_awaiting_review": featured_public_reported_gaps,
            "featured_no_mapped_public_evidence": featured_no_public_evidence_gaps,
            "featured_ratio": round(covered_featured / total_featured, 4) if total_featured else 0,
        },
        "candidates": {
            "total": len(candidates),
            "missing": sum(1 for item in candidates if item.get("kind") == "missing"),
            "public_reported": sum(1 for item in candidates if item.get("kind") == "public_reported"),
            "refresh": sum(1 for item in candidates if item.get("kind") == "refresh"),
            "high_priority": sum(1 for item in candidates if item.get("priority") == "high"),
        },
        "sources": {
            "freshness": dict(freshness_counts),
            "probe": dict(probe_counts),
        },
        "errors": errors,
        "warnings": warnings,
    }
    return {
        "health": health,
        "candidates": candidates,
        "source_status": source_status,
    }


def write_outputs(output_dir: Path, report: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    health = report["health"]
    candidates = report["candidates"]
    source_status = report["source_status"]
    for filename, payload in (
        ("health.json", health),
        ("candidates.json", {"generated_at": health["generated_at"], "candidates": candidates}),
        ("source-status.json", {"generated_at": health["generated_at"], "sources": source_status}),
    ):
        path = output_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    priority_rank = {"high": 0, "normal": 1, "low": 2}
    missing_candidates = sorted(
        (item for item in candidates if item.get("kind") == "missing"),
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            str(item.get("model_name", "")),
            str(item.get("benchmark_name", "")),
        ),
    )
    public_reported_candidates = sorted(
        (item for item in candidates if item.get("kind") == "public_reported"),
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            str(item.get("model_name", "")),
            str(item.get("benchmark_name", "")),
        ),
    )
    refresh_candidates = sorted(
        (item for item in candidates if item.get("kind") == "refresh"),
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            -int(item.get("age_days") or 0),
        ),
    )
    missing_rows = [
        [item.get("priority"), item.get("model_name"), item.get("benchmark_name"), item.get("evaluation_mode"), ", ".join(item.get("suggested_harness_ids", []))]
        for item in missing_candidates
    ]
    public_reported_rows = [
        [
            item.get("priority"),
            item.get("model_name"),
            item.get("benchmark_name"),
            item.get("public_evidence_count"),
            ", ".join(item.get("public_source_ids", [])) or "—",
        ]
        for item in public_reported_candidates
    ]
    refresh_rows = [
        [item.get("priority"), item.get("model_name"), item.get("benchmark_name"), item.get("age_days"), item.get("staleness_after_days")]
        for item in refresh_candidates
    ]
    source_rows = [
        [item.get("source_id"), item.get("freshness"), item.get("probe", {}).get("status"), item.get("linked_observations"), item.get("url") or "—"]
        for item in source_status
    ]
    coverage = health["coverage"]
    lines = [
        "# Frontier Model Bench maintenance report",
        "",
        f"- 生成时间：`{health['generated_at']}`",
        f"- 快照日期：`{health['as_of']}`",
        f"- 状态：`{health['status']}`（network checked: `{health['network_checked']}`）",
        "- 本报告只产生候选和健康信号，不修改 `data/catalog/` 或 `data/observations/`。",
        "",
        "## Coverage",
        "",
        f"当前模型 × active benchmark：{coverage['covered_cells']}/{coverage['current_model_benchmark_cells']}（{coverage['ratio']:.1%}）；featured：{coverage['featured_covered']}/{coverage['featured_cells']}（{coverage['featured_ratio']:.1%}）。",
        f"Canonical gaps（口径不变）：{coverage['missing_cells']}；Public reported / awaiting canonical review：{coverage['public_reported_awaiting_review_cells']}；No mapped public evidence：{coverage['no_mapped_public_evidence_cells']}。",
        "",
        "## Public reported / awaiting canonical review",
        "",
        "这些单元已有映射到 canonical model × benchmark 的公开披露值，但仍不计入 canonical coverage。完整队列见 `candidates.json`。",
        "",
        "<details>",
        f"<summary>展开前 80 条（共 {len(public_reported_candidates)} 条）</summary>",
        "",
        markdown_table(public_reported_rows[:80], ["优先级", "模型", "Benchmark", "公开证据数", "来源"]),
        "",
        "</details>",
        "",
        "## No mapped public evidence candidates",
        "",
        markdown_table(missing_rows[:80], ["优先级", "模型", "Benchmark", "模式", "建议 harness"]),
        "",
        "## Refresh candidates",
        "",
        markdown_table(refresh_rows[:80], ["优先级", "模型", "Benchmark", "年龄天数", "阈值"]),
        "",
        "## Source health",
        "",
        markdown_table(source_rows, ["Source", "freshness", "probe", "observations", "URL"]),
        "",
        "## Warnings / errors",
        "",
    ]
    messages = [f"- {message}" for message in health.get("warnings", []) + health.get("errors", [])]
    lines.extend(messages or ["_无。_"])
    lines.extend(
        [
            "",
            "## Review contract",
            "",
            "1. 检查来源快照、model alias、benchmark version 和完整 protocol。",
            "2. 在 PR 中追加 observation；不要直接编辑旧值或把 `—` 当作 0。",
            "3. 运行 `python3 scripts/build_derived.py` 与 `python3 scripts/validate_data.py --strict`，通过人工审阅后才发布。",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="report directory")
    parser.add_argument("--today", help="override report date (YYYY-MM-DD), useful for tests")
    parser.add_argument("--check-sources", action="store_true", help="probe source landing pages with bounded HEAD/GET requests")
    parser.add_argument("--timeout", type=float, default=8.0, help="per-source network timeout in seconds")
    parser.add_argument("--max-sources", type=int, default=80, help="maximum source URLs to probe")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
        if args.timeout <= 0 or args.max_sources < 0:
            raise MaintenanceError("timeout 必须 > 0，max-sources 必须 >= 0")
        report = build_report(root, today, bool(args.check_sources), float(args.timeout), int(args.max_sources))
        write_outputs(output_dir, report)
    except (MaintenanceError, ValueError) as exc:
        print(f"maintenance_report: ERROR: {exc}", file=sys.stderr)
        return 2
    health = report["health"]
    print(
        "maintenance_report: "
        f"status={health['status']} candidates={health['candidates']['total']} "
        f"coverage={health['coverage']['ratio']:.1%} "
        f"output={output_dir}"
    )
    # Network errors and stale/missing data are review signals, not a reason
    # to replace the last approved dashboard.  Structural errors above remain
    # fatal and return 2.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
