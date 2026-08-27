#!/usr/bin/env python3
"""Build the static site index from the canonical model-bench registries.

The repository deliberately keeps the canonical facts in small registries and
the observations in a JSONL long table.  This script joins those files into a
single browser-friendly ``data/derived/site.json``.  The original
``data/models.json`` seed is read as a compatibility source: its numeric
observations are migrated in memory, so an existing checkout keeps working
while the long table is filled in incrementally.

No network access is performed here.  Source adapters (or a human PR) should
write candidate observations first; this deterministic build step only joins,
selects and annotates them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "site.json"

# The first MVP used short ids.  Keep an explicit map rather than silently
# deriving a new id from a display name; aliases and endpoint names are not
# release identities.
LEGACY_MODEL_IDS: dict[str, str] = {
    "gemini-3-1-pro": "google/gemini-3.1-pro@2026-02-19",
    "gpt-5": "openai/gpt-5@2025-08-07",
    "claude-opus-4": "anthropic/claude-opus@4",
    "gemini-2-5-pro": "google/gemini-2.5-pro@2025-06-05",
    "qwen3-max-thinking": "qwen/qwen3-max@thinking",
    "grok-4-fast": "xai/grok-4-fast@2025-09-19",
    "deepseek-r1-0528": "deepseek/r1@0528",
}

LEGACY_BENCHMARK_VERSIONS: dict[str, str] = {
    "gpqa-diamond": "gpqa-diamond@v1",
    "aime-2025": "aime-2025@v1",
    "swebench-verified": "swebench-verified@verified",
    "livecodebench": "livecodebench@v5",
    "mmlu-pro": "mmlu-pro@v1",
    "mmmu": "mmmu@v1",
    "terminal-bench": "terminal-bench@2.0",
    "hle": "hle@v1",
}

LEGACY_METRIC_IDS: dict[str, str] = {
    # The MVP used human-facing labels as metric ids in two columns.  Canonical
    # registries use slug-safe ids so observations can be joined reliably.
    "terminal-bench": "pass_rate",
}

FAMILY_LABELS = {
    "reasoning": "推理",
    "knowledge": "知识",
    "coding": "代码",
    "coding-agent": "代码 Agent",
    "agents": "Agent",
    "tool-use": "工具调用",
    "knowledge-work": "知识工作",
    "multimodal": "多模态",
    "computer-use": "电脑操作",
    "long-context": "长上下文",
    "chinese": "中文 / 多语言",
    "multilingual": "中文 / 多语言",
    "cyber": "网络安全",
}

STATUS_RANK = {
    "verified": 6,
    "reproduced": 5,
    "published": 4,
    "reported": 3,
    "curated": 2,
    "seed": 1,
}
EVIDENCE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}
COMPARABILITY_RANK = {"exact": 3, "conditional": 2, "none": 1}


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at {path}:{line_number}: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row at {path}:{line_number} must be an object")
            rows.append(value)
    return rows


def load_public_evidence(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load the compact public/reported evidence layer if it exists.

    Public leaderboard reports are intentionally kept outside canonical
    observations.  The page index can still expose the curated, explicitly
    unverified rows in one request; missing/older public artifacts simply
    produce an empty layer and never block the canonical build.
    """

    path = root / "data" / "derived" / "public.json"
    payload = load_json(path, {})
    if not isinstance(payload, Mapping):
        payload = {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    meta = payload.get("meta")
    stats = payload.get("stats")
    # The full unmapped JSONL is intentionally ignored by git/Pages.  A
    # compact, path-safe alias summary is tracked separately so the UI can
    # make unresolved source spellings discoverable without shipping tens of
    # megabytes of raw rows.
    summary = load_json(root / "data" / "public" / "unmapped-summary.json", {})
    aliases = summary.get("aliases") if isinstance(summary, Mapping) else []
    if not isinstance(aliases, list):
        aliases = []
    aliases = [dict(item) for item in aliases if isinstance(item, Mapping)]
    return (
        dict(meta) if isinstance(meta, Mapping) else {},
        dict(stats) if isinstance(stats, Mapping) else {},
        rows,
        aliases,
    )


def as_list(payload: Any, key: str | None = None) -> list[dict[str, Any]]:
    value = payload.get(key, []) if isinstance(payload, Mapping) and key else payload
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def first_nonempty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _payload_meta(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    meta = payload.get("meta")
    return meta if isinstance(meta, Mapping) else {}


def _utc_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def derive_site_timestamps(
    legacy_meta: Mapping[str, Any],
    model_payload: Any,
    model_profiles_payload: Any,
    public_meta: Mapping[str, Any],
) -> tuple[str, str]:
    """Return a coherent snapshot date and timestamp for the derived site.

    Catalog/profile metadata can advance independently of the legacy seed and
    the public evidence snapshot.  The page date therefore follows the newest
    declared input rather than whichever file happens to be read first.
    """

    model_meta = _payload_meta(model_payload)
    profile_meta = _payload_meta(model_profiles_payload)
    date_values = (
        legacy_meta.get("asOf", legacy_meta.get("as_of")),
        model_meta.get("as_of", model_meta.get("asOf")),
        profile_meta.get("as_of", profile_meta.get("asOf")),
        public_meta.get("generatedAt", public_meta.get("generated_at")),
    )
    parsed_dates = [stamp for value in date_values if (stamp := _utc_timestamp(value)) is not None]
    if parsed_dates:
        as_of = max(parsed_dates).date().isoformat()
    else:
        as_of = "2026-08-27"

    timestamp_values = (
        f"{as_of}T00:00:00Z",
        legacy_meta.get("lastUpdated", legacy_meta.get("last_updated")),
        public_meta.get("generatedAt", public_meta.get("generated_at")),
    )
    parsed_timestamps = [
        stamp for value in timestamp_values if (stamp := _utc_timestamp(value)) is not None
    ]
    last_updated = max(parsed_timestamps).strftime("%Y-%m-%dT%H:%M:%SZ")
    return as_of, last_updated


def _has_runtime_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


PUBLIC_EVIDENCE_RUNTIME_FIELDS = (
    "id",
    "canonicalModelId",
    "modelName",
    "modelRef",
    "benchmarkId",
    "benchmarkName",
    "benchmarkVersion",
    "benchmarkVersionHint",
    "benchmarkVersionId",
    "metricId",
    "value",
    "rawValue",
    "unit",
    # Used by evidenceStrength() when several public sources share a cell.
    "evidenceLevel",
    "sourceId",
    "sourceLabel",
    "sourceUrl",
    "sourcePageUrl",
    "sourceApiUrl",
    "sourceLocator",
    "retrievedAt",
    "observedAt",
    "publishedAt",
    "payloadSha256",
    "protocol",
    "harnessId",
    "qualityFlags",
    "subjectType",
    "sourceSubjectType",
    "mappingStatus",
    # Despite its name this is display behavior, not review-only metadata:
    # app.js and models.js use it to select the representative observation.
    "selectionRank",
)


def public_evidence_for_site(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project a full public evidence row into the browser display contract.

    The complete, review-oriented row remains in ``public.json`` and
    ``evidence.jsonl``.  This DTO retains everything the three pages need for
    matrix joins, subject/harness semantics, provenance drawers and telemetry
    disclosure, while omitting raw source payloads and duplicated defaults.
    """

    result = {
        key: row.get(key)
        for key in PUBLIC_EVIDENCE_RUNTIME_FIELDS
        if _has_runtime_value(row.get(key))
    }

    source_url = row.get("sourceUrl")
    evidence_url = row.get("evidenceUrl")
    if _has_runtime_value(evidence_url) and evidence_url != source_url:
        result["evidenceUrl"] = evidence_url

    source_metric = row.get("sourceMetricId")
    if _has_runtime_value(source_metric) and source_metric != row.get("metricId"):
        result["sourceMetricId"] = source_metric

    harness = row.get("harness")
    if _has_runtime_value(harness) and harness != row.get("harnessId"):
        result["harness"] = harness

    if row.get("matrixExcluded") is True:
        result["matrixExcluded"] = True
        reason = row.get("matrixExcludedReason")
        if _has_runtime_value(reason):
            result["matrixExcludedReason"] = reason

    # These fields have safe browser defaults but may carry a future
    # non-default value that changes ranking or the public disclosure label.
    comparability = row.get("comparability")
    if _has_runtime_value(comparability) and comparability != "conditional":
        result["comparability"] = comparability
    status = row.get("status")
    if _has_runtime_value(status) and status != "reported":
        result["status"] = status
    return result


PUBLIC_UNMAPPED_RUNTIME_FIELDS = (
    "modelRef",
    "rowCount",
    "numericRowCount",
    "benchmarkCount",
    "benchmarkIds",
    "sourceIds",
    "sourceLabels",
    "sourceUrls",
    "mappingStatusCounts",
    "mappingStatus",
    "latestRetrievedAt",
    "observedAtMax",
    "aliases",
    "canonicalModelId",
    "suggestedCanonicalModelId",
)

PUBLIC_UNMAPPED_EXAMPLE_FIELDS = (
    "sourceId",
    "sourceLabel",
    "sourceUrl",
    "evidenceUrl",
    "sourceLocator",
    "locator",
    "retrievedAt",
    "observedAt",
)


def public_unmapped_model_for_site(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only alias-card data and one compact provenance example."""

    result = {
        key: row.get(key)
        for key in PUBLIC_UNMAPPED_RUNTIME_FIELDS
        if _has_runtime_value(row.get(key))
    }
    examples = row.get("examples")
    if not isinstance(examples, list):
        examples = row.get("sampleEvidence")
    first_example = examples[0] if isinstance(examples, list) and examples else None
    if isinstance(first_example, Mapping):
        compact_example = {
            key: first_example.get(key)
            for key in PUBLIC_UNMAPPED_EXAMPLE_FIELDS
            if _has_runtime_value(first_example.get(key))
        }
        if compact_example:
            result["examples"] = [compact_example]
    return result


def write_compact_json(path: Path, payload: Any) -> None:
    """Write a generated browser artifact without human-oriented indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def source_ids_for(row: Mapping[str, Any]) -> list[str]:
    values = row.get("source_ids", row.get("sourceIds"))
    if values is None and row.get("source_id", row.get("sourceId")) is not None:
        values = [row.get("source_id", row.get("sourceId"))]
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if isinstance(value, str) and value]


def evidence_ids_for(row: Mapping[str, Any]) -> list[str]:
    values = row.get("evidence_ids", row.get("evidenceIds"))
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if isinstance(value, str) and value]


def metric_for(benchmark: Mapping[str, Any], metric_id: str | None = None) -> dict[str, Any]:
    metrics = benchmark.get("metrics")
    if isinstance(metrics, list):
        wanted = metric_id or benchmark.get("default_metric_id") or benchmark.get("metric")
        for metric in metrics:
            if isinstance(metric, Mapping) and metric.get("id") == wanted:
                return dict(metric)
        for metric in metrics:
            if isinstance(metric, Mapping):
                return dict(metric)
    scale = benchmark.get("scale", 100)
    if isinstance(scale, (int, float)):
        scale = {"min": 0, "max": scale}
    return {
        "id": metric_id or benchmark.get("metric") or "score",
        "label": benchmark.get("metricLabel") or benchmark.get("metric") or "score",
        "unit": "%" if benchmark.get("unit") == "%" else benchmark.get("unit", "percent"),
        "scale": scale,
        "direction": benchmark.get("direction", "higher"),
    }


def default_version_for(benchmark: Mapping[str, Any]) -> str:
    explicit = benchmark.get("default_version_id") or benchmark.get("defaultVersionId")
    if isinstance(explicit, str) and explicit:
        return explicit
    versions = benchmark.get("versions")
    if isinstance(versions, list):
        for version in versions:
            if isinstance(version, Mapping) and isinstance(version.get("id"), str):
                if version.get("status") == "active":
                    return str(version["id"])
        for version in versions:
            if isinstance(version, Mapping) and isinstance(version.get("id"), str):
                return str(version["id"])
    identifier = str(benchmark.get("id", "benchmark"))
    return f"{identifier}@v1"


def version_label(benchmark: Mapping[str, Any], version_id: str | None) -> str:
    versions = benchmark.get("versions")
    if isinstance(versions, list):
        for version in versions:
            if isinstance(version, Mapping) and version.get("id") == version_id:
                return str(version.get("label") or version_id)
    return str(version_id or benchmark.get("version") or "未注明")


def display_unit(metric: Mapping[str, Any]) -> str:
    unit = metric.get("unit", "%")
    if unit in {"percent", "percentage", "%"}:
        return "%"
    return str(unit)


def scale_for(metric: Mapping[str, Any]) -> int | float | dict[str, Any]:
    scale = metric.get("scale", 100)
    if isinstance(scale, Mapping):
        lower = scale.get("min", 0)
        upper = scale.get("max", 100)
        if lower == 0:
            return upper
        return {"min": lower, "max": upper}
    return scale


def canonical_model_list(payload: Any) -> list[dict[str, Any]]:
    return as_list(payload, "models")


def model_profile_map(payload: Any) -> dict[str, dict[str, Any]]:
    """Return the optional, source-linked profile layer keyed by model id.

    Profiles intentionally live beside the identity registry: release ids and
    scores remain stable while descriptive facts can be enriched independently.
    Accept both ``{"profiles": {id: profile}}`` and a list of profile rows so
    future maintenance scripts can use either shape.
    """

    value: Any = payload.get("profiles", {}) if isinstance(payload, Mapping) else payload
    if isinstance(value, Mapping):
        return {
            str(identifier): dict(profile)
            for identifier, profile in value.items()
            if isinstance(identifier, str) and isinstance(profile, Mapping)
        }
    if isinstance(value, list):
        result: dict[str, dict[str, Any]] = {}
        for profile in value:
            if not isinstance(profile, Mapping):
                continue
            identifier = profile.get("model_id", profile.get("modelId", profile.get("id")))
            if isinstance(identifier, str) and identifier:
                result[identifier] = {
                    key: item
                    for key, item in profile.items()
                    if key not in {"id", "model_id", "modelId"}
                }
        return result
    return {}


def canonical_benchmark_list(payload: Any) -> list[dict[str, Any]]:
    return as_list(payload, "benchmarks")


def canonical_source_list(payload: Any) -> list[dict[str, Any]]:
    return as_list(payload, "sources")


def canonical_harness_list(payload: Any) -> list[dict[str, Any]]:
    return as_list(payload, "harnesses")


def canonical_preset_list(payload: Any) -> list[dict[str, Any]]:
    return as_list(payload, "presets")


def model_lookup(models: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for model in models:
        identifier = model.get("id")
        if isinstance(identifier, str):
            lookup[identifier] = dict(model)
        aliases = model.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                value = alias.get("value") if isinstance(alias, Mapping) else alias
                if isinstance(value, str) and value:
                    lookup.setdefault(value, dict(model))
    for legacy, canonical in LEGACY_MODEL_IDS.items():
        if canonical in lookup:
            lookup.setdefault(legacy, lookup[canonical])
    return lookup


def benchmark_lookup(benchmarks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for benchmark in benchmarks:
        identifier = benchmark.get("id")
        if isinstance(identifier, str):
            lookup[identifier] = dict(benchmark)
    return lookup


def legacy_observations(
    legacy: Mapping[str, Any],
    models_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert numeric values in the old nested seed into long-table rows."""

    rows: list[dict[str, Any]] = []
    old_benchmarks = {
        str(item.get("id")): item
        for item in as_list(legacy, "benchmarks")
        if isinstance(item.get("id"), str)
    }
    for model in as_list(legacy, "models"):
        old_id = model.get("id")
        if not isinstance(old_id, str):
            continue
        model_id = LEGACY_MODEL_IDS.get(old_id, old_id)
        if model_id not in models_by_id:
            # A legacy-only model is still useful; the derived catalog can
            # expose it without pretending it belongs to a newer release.
            model_id = LEGACY_MODEL_IDS.get(old_id, f"legacy/{old_id}@legacy")
        scores = model.get("scores")
        if not isinstance(scores, Mapping):
            continue
        for benchmark_id, score in scores.items():
            if not isinstance(benchmark_id, str) or not isinstance(score, Mapping):
                continue
            value = score.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            benchmark = old_benchmarks.get(benchmark_id, {})
            subject_type = "system" if benchmark_id in {"swebench-verified", "terminal-bench"} else "model"
            harness_id = "model-only" if subject_type == "model" else "unspecified-reported"
            observed = first_nonempty(
                score.get("observed_at"), score.get("observed"), model.get("release"),
                legacy.get("meta", {}).get("asOf") if isinstance(legacy.get("meta"), Mapping) else None,
                default="2026-08-27",
            )
            source_id = score.get("sourceId")
            rows.append(
                {
                    "id": f"legacy-{old_id}-{benchmark_id}",
                    "model_id": model_id,
                    "benchmark_id": benchmark_id,
                    "benchmark_version_id": LEGACY_BENCHMARK_VERSIONS.get(
                        benchmark_id, f"{benchmark_id}@legacy"
                    ),
                    "metric_id": LEGACY_METRIC_IDS.get(
                        benchmark_id, benchmark.get("metric", "score")
                    ),
                    "value": value,
                    "raw_value": f"{value}{benchmark.get('unit', '%')}",
                    "subject": {
                        "type": subject_type,
                        "system_id": None,
                        "agent_id": None,
                        "scaffold": None,
                    },
                    "endpoint_id": None,
                    "harness_id": harness_id,
                    "protocol": {
                        "shots": None,
                        "temperature": None,
                        "top_p": None,
                        "tools": None,
                        "reasoning_mode": None,
                        "raw_setting": score.get("setting"),
                    },
                    "observed_at": observed,
                    "published_at": observed,
                    "status": "reported",
                    "evidence_level": score.get("evidence_level", "B"),
                    "comparability": score.get("comparability", "conditional"),
                    "preferred": True,
                    "source_ids": [source_id] if isinstance(source_id, str) and source_id else [],
                    "notes": score.get("note") or "Migrated from legacy nested seed; protocol detail is limited.",
                    "legacy_migrated": True,
                }
            )
    return rows


def normalize_observation(
    row: Mapping[str, Any],
    models_by_id: Mapping[str, Mapping[str, Any]],
    benchmarks_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    harness_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize snake/camel aliases while retaining the original protocol."""

    value = row.get("value")
    if isinstance(value, bool):
        value = None
    model_id = row.get("model_id", row.get("modelId"))
    if not isinstance(model_id, str):
        model_id = "unknown/model@unknown"
    if model_id not in models_by_id:
        model_id = LEGACY_MODEL_IDS.get(model_id, model_id)
    benchmark_id = row.get("benchmark_id", row.get("benchmarkId"))
    if not isinstance(benchmark_id, str):
        benchmark_id = "unknown-benchmark"
    # Common aliases used by provider tables.
    benchmark_id = {
        "terminal-bench-2.1": "terminal-bench",
        "terminal-bench-2-1": "terminal-bench",
        "livecodebench-v6": "livecodebench",
        "deepswe-v1.1": "deepswe",
    }.get(benchmark_id, benchmark_id)
    benchmark = benchmarks_by_id.get(benchmark_id, {})
    metric_id = row.get("metric_id", row.get("metricId"))
    if not isinstance(metric_id, str):
        metric_id = str(benchmark.get("default_metric_id") or benchmark.get("metric") or "score")
    version_id = row.get("benchmark_version_id", row.get("benchmarkVersionId"))
    if not isinstance(version_id, str) or not version_id:
        version_id = default_version_for(benchmark) if benchmark else f"{benchmark_id}@v1"
    subject = row.get("subject")
    if not isinstance(subject, Mapping):
        subject = {}
    subject_type = subject.get("type") or row.get("subject_type") or row.get("subjectType")
    harness_id = row.get("harness_id", row.get("harnessId"))
    if not isinstance(harness_id, str) or not harness_id:
        harness_id = "model-only" if subject_type in {None, "model"} else "unspecified-reported"
    if harness_id not in harness_by_id and harness_id not in {"model-only", "unspecified-reported"}:
        # Preserve a source-specific identifier; validation will flag it if a
        # catalog entry is missing, rather than silently changing identity.
        pass
    if subject_type not in {"model", "system"}:
        subject_type = "system" if harness_id != "model-only" else "model"
    protocol = row.get("protocol")
    if not isinstance(protocol, Mapping):
        protocol = {}
    source_ids = source_ids_for(row)
    evidence_ids = evidence_ids_for(row)
    identifier = row.get("id")
    if not isinstance(identifier, str) or not identifier:
        fingerprint = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str)
        identifier = "obs-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    observed_at = first_nonempty(row.get("observed_at"), row.get("observedAt"), default=None)
    published_at = first_nonempty(row.get("published_at"), row.get("publishedAt"), default=None)
    return {
        "id": identifier,
        "model_id": model_id,
        "benchmark_id": benchmark_id,
        "benchmark_version_id": version_id,
        "metric_id": metric_id,
        "value": value,
        "raw_value": row.get("raw_value", row.get("rawValue")),
        "subject": {
            "type": subject_type,
            "system_id": subject.get("system_id", subject.get("systemId")),
            "agent_id": subject.get("agent_id", subject.get("agentId")),
            "scaffold": subject.get("scaffold"),
        },
        "endpoint_id": row.get("endpoint_id", row.get("endpointId")),
        "harness_id": harness_id,
        "protocol": dict(protocol),
        "observed_at": observed_at,
        "published_at": published_at,
        "status": row.get("status") or "reported",
        "evidence_level": row.get("evidence_level", row.get("evidenceLevel")) or "B",
        "comparability": row.get("comparability") or "conditional",
        "preferred": bool(row.get("preferred", False)),
        "source_ids": source_ids,
        "evidence_ids": evidence_ids,
        "uncertainty": row.get("uncertainty"),
        "sample_size": row.get("sample_size", row.get("sampleSize")),
        "quality_flags": row.get("quality_flags", row.get("qualityFlags")) or [],
        "notes": row.get("notes", row.get("note")),
        "legacy_migrated": bool(row.get("legacy_migrated", False)),
    }


def observation_rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
    observed = row.get("observed_at") or ""
    return (
        1 if row.get("preferred") else 0,
        STATUS_RANK.get(str(row.get("status")), 0),
        EVIDENCE_RANK.get(str(row.get("evidence_level")), 0),
        COMPARABILITY_RANK.get(str(row.get("comparability")), 0),
        str(observed),
        str(row.get("id", "")),
    )


def is_model_observation(row: Mapping[str, Any]) -> bool:
    """Return whether an observation measures the release without an agent loop.

    Agentic scores remain available in ``runs`` but must not silently become a
    model-level matrix score.  ``harness_id=model-only`` is the explicit
    canonical marker; the subject type is retained as a second guard for
    records authored before that marker was introduced.
    """

    subject = row.get("subject")
    subject_type = subject.get("type") if isinstance(subject, Mapping) else None
    return subject_type == "model" and row.get("harness_id") == "model-only"


def source_url(source: Mapping[str, Any] | None) -> str | None:
    if not isinstance(source, Mapping):
        return None
    value = source.get("url") or source.get("source_url")
    return str(value) if isinstance(value, str) else None


def source_label(source: Mapping[str, Any] | None, fallback: str = "来源") -> str:
    if not isinstance(source, Mapping):
        return fallback
    return str(source.get("label") or source.get("title") or source.get("publisher") or fallback)


def benchmark_for_site(
    benchmark: Mapping[str, Any],
    source_by_id: Mapping[str, Mapping[str, Any]],
    as_of: str,
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identifier = str(benchmark.get("id"))
    metric = metric_for(benchmark)
    source_ids = benchmark.get("source_ids", benchmark.get("sourceIds", []))
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    source_ids = [sid for sid in source_ids if isinstance(sid, str)] if isinstance(source_ids, list) else []
    first_source = source_by_id.get(source_ids[0]) if source_ids else None
    family = str(benchmark.get("family") or benchmark.get("category") or "other")
    category = str(benchmark.get("category") or family)
    evaluation_mode = benchmark.get("evaluation_mode") or benchmark.get("evaluationMode")
    if not evaluation_mode:
        # The registry keeps a broad comparison family (for example
        # ``coding`` or ``agents``) and a more specific category (for
        # example ``coding-agent`` or ``tool-use``).  Agentic suites must be
        # marked as system runs even when their broad family is shared with
        # direct code-generation or reasoning benchmarks.
        evaluation_mode = "system" if ({family, category} & {"coding-agent", "tool-use", "computer-use", "cyber"}) else "direct"
    site_benchmark = {
        "id": identifier,
        "canonicalId": identifier,
        "short": benchmark.get("short") or benchmark.get("name") or identifier,
        "name": benchmark.get("name") or identifier,
        "family": family,
        "category": category,
        "familyLabel": benchmark.get("family_label") or benchmark.get("familyLabel") or FAMILY_LABELS.get(family, family),
        "evaluationMode": evaluation_mode,
        "comparisonKey": benchmark.get("comparison_key") or benchmark.get("comparisonKey") or f"{identifier}:{default_version_for(benchmark)}:{metric.get('id')}",
        "metric": metric.get("id") or benchmark.get("metric") or "score",
        "metricLabel": metric.get("label") or benchmark.get("metricLabel") or "score",
        "scale": scale_for(metric),
        "unit": display_unit(metric),
        "direction": metric.get("direction") or benchmark.get("direction") or "higher",
        "version": version_label(benchmark, default_version_for(benchmark)),
        "versionId": default_version_for(benchmark),
        "description": benchmark.get("description") or "",
        "owner": benchmark.get("owner"),
        "source": source_url(first_source) or benchmark.get("homepage") or benchmark.get("source"),
        "sourceLabel": source_label(first_source, str(benchmark.get("owner") or "benchmark")),
        "sourceIds": source_ids,
        "lastVerified": benchmark.get("lastVerified") or as_of,
        "versions": benchmark.get("versions", []),
        "metrics": benchmark.get("metrics", []),
        "featured": bool(benchmark.get("featured", False)),
        # Editorial reading order for the wide matrix. Lower values appear
        # first; this is navigation metadata, never a benchmark-quality score.
        "displayPriority": benchmark.get("display_priority", benchmark.get("displayPriority")),
    }
    # Long-form benchmark profiles live in a separate catalog file so that
    # the compact registry stays easy to scan.  Keep the profile opaque here:
    # the browser renders its task/dataset/protocol/comparison fields without
    # turning qualitative notes into observations or scores.
    if isinstance(profile, Mapping):
        site_benchmark["profile"] = dict(profile)
    return site_benchmark


def model_for_site(
    model: Mapping[str, Any],
    selected: Mapping[str, Mapping[str, Any]],
    alternatives: Mapping[str, list[Mapping[str, Any]]],
    benchmark_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    harness_by_id: Mapping[str, Mapping[str, Any]],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identifier = str(model.get("id"))
    scores: dict[str, Any] = {}
    for benchmark_id, row in selected.items():
        benchmark = benchmark_by_id.get(benchmark_id, {})
        metric = metric_for(benchmark, str(row.get("metric_id")))
        source_ids = row.get("source_ids", [])
        first_source = source_by_id.get(source_ids[0]) if source_ids else None
        harness_id = row.get("harness_id")
        harness = harness_by_id.get(str(harness_id), {}) if harness_id else {}
        protocol = row.get("protocol") if isinstance(row.get("protocol"), Mapping) else {}
        setting = protocol.get("raw_setting") or protocol.get("setting")
        if not setting:
            bits = []
            if protocol.get("tools") is not None:
                bits.append("tools" if protocol.get("tools") else "no tools")
            if protocol.get("reasoning_mode"):
                bits.append(str(protocol["reasoning_mode"]))
            setting = " · ".join(bits) or "未注明"
        score: dict[str, Any] = {
            "value": row.get("value"),
            "raw_value": row.get("raw_value"),
            "setting": setting,
            "sourceId": source_ids[0] if source_ids else None,
            "sourceUrl": source_url(first_source),
            "sourceLabel": source_label(first_source),
            "verified": row.get("status"),
            "status": row.get("status"),
            "evidence_level": row.get("evidence_level"),
            "comparability": row.get("comparability"),
            "observed_at": row.get("observed_at"),
            "published_at": row.get("published_at"),
            "benchmark_version": row.get("benchmark_version_id"),
            "version": version_label(benchmark, row.get("benchmark_version_id")),
            "metric": row.get("metric_id") or metric.get("id"),
            "unit": display_unit(metric),
            "protocol": protocol,
            "harnessId": harness_id,
            "harness": harness.get("name") or harness.get("label") or harness_id,
            "subjectType": row.get("subject", {}).get("type") if isinstance(row.get("subject"), Mapping) else "model",
            "observationId": row.get("id"),
            "notes": row.get("notes"),
            "legacyMigrated": bool(row.get("legacy_migrated")),
        }
        other = [item.get("id") for item in alternatives.get(benchmark_id, []) if item.get("id") != row.get("id")]
        if other:
            score["alternativeObservationIds"] = other
        scores[benchmark_id] = score

    release = model.get("release_date", model.get("release"))
    tags = model.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    source_ids = model.get("source_ids", model.get("sourceIds", []))
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    return {
        "id": identifier,
        "canonicalId": identifier,
        "familyId": model.get("family_id", model.get("familyId")),
        "name": model.get("name") or identifier,
        "provider": model.get("provider") or "Unknown",
        "mark": model.get("mark") or str(model.get("name") or identifier)[:1],
        "release": release,
        "releaseDate": release,
        "access": model.get("access") or "unknown",
        "status": model.get("status") or "active",
        "availability": model.get("availability") or model.get("access"),
        "aliases": model.get("aliases", []),
        "tags": tags,
        "summary": model.get("summary") or "",
        "modalities": model.get("modalities", []),
        "contextWindow": model.get("context_window", model.get("contextWindow")),
        "paramsTotal": model.get("params_total", model.get("paramsTotal")),
        "paramsActive": model.get("params_active", model.get("paramsActive")),
        "paramsApproximate": bool(model.get("params_approximate", model.get("paramsApproximate", False))),
        "openWeights": model.get("open_weights", model.get("openWeights")),
        "variant": model.get("variant", {}),
        # Keep the descriptive profile separate from canonical identity fields
        # so page copy can evolve without changing score semantics.
        "profile": dict(profile) if isinstance(profile, Mapping) else {},
        "sourceIds": source_ids if isinstance(source_ids, list) else [],
        "scores": scores,
        "scoreCount": len(scores),
        "catalogOnly": not bool(scores),
    }


def run_for_site(
    row: Mapping[str, Any],
    model_by_id: Mapping[str, Mapping[str, Any]],
    benchmark_by_id: Mapping[str, Mapping[str, Any]],
    source_by_id: Mapping[str, Mapping[str, Any]],
    harness_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    model = model_by_id.get(str(row.get("model_id")), {})
    benchmark = benchmark_by_id.get(str(row.get("benchmark_id")), {})
    metric = metric_for(benchmark, str(row.get("metric_id")))
    source_ids = row.get("source_ids", [])
    first_source = source_by_id.get(source_ids[0]) if source_ids else None
    harness_id = row.get("harness_id")
    harness = harness_by_id.get(str(harness_id), {}) if harness_id else {}
    subject = row.get("subject") if isinstance(row.get("subject"), Mapping) else {}
    protocol = row.get("protocol") if isinstance(row.get("protocol"), Mapping) else {}
    return {
        "id": row.get("id"),
        "modelId": row.get("model_id"),
        "modelName": model.get("name") or row.get("model_id"),
        "provider": model.get("provider"),
        "familyId": model.get("family_id", model.get("familyId")),
        "endpointId": row.get("endpoint_id"),
        "harnessId": harness_id,
        "harnessName": harness.get("name") or harness.get("label") or harness_id,
        "benchmarkId": row.get("benchmark_id"),
        "benchmarkName": benchmark.get("name") or row.get("benchmark_id"),
        "benchmarkVersion": row.get("benchmark_version_id"),
        "metricId": row.get("metric_id"),
        "metric": metric.get("label") or row.get("metric_id"),
        "value": row.get("value"),
        "rawValue": row.get("raw_value"),
        "unit": display_unit(metric),
        "protocol": protocol,
        "subject": subject,
        "subjectType": subject.get("type", "model"),
        "evidence": {
            "level": row.get("evidence_level"),
            "sourceIds": source_ids,
            "evidenceIds": row.get("evidence_ids", []),
            "sourceUrl": source_url(first_source),
            "sourceLabel": source_label(first_source),
        },
        "evidenceLevel": row.get("evidence_level"),
        "evidenceIds": row.get("evidence_ids", []),
        "comparability": row.get("comparability"),
        "status": row.get("status"),
        "sourceId": source_ids[0] if source_ids else None,
        "sourceUrl": source_url(first_source),
        "observedAt": row.get("observed_at"),
        "publishedAt": row.get("published_at"),
        "uncertainty": row.get("uncertainty"),
        "sampleSize": row.get("sample_size"),
        "qualityFlags": row.get("quality_flags", []),
        "preferred": bool(row.get("preferred")),
        "notes": row.get("notes"),
        "legacyMigrated": bool(row.get("legacy_migrated")),
    }


def build(root: Path, output: Path) -> dict[str, Any]:
    catalog_dir = root / "data" / "catalog"
    observations_path = root / "data" / "observations" / "results.jsonl"
    legacy_path = root / "data" / "models.json"

    model_payload = load_json(catalog_dir / "models.json", [])
    benchmark_payload = load_json(catalog_dir / "benchmarks.json", [])
    benchmark_profiles_payload = load_json(catalog_dir / "benchmark_profiles.json", {})
    model_profiles_payload = load_json(catalog_dir / "model_profiles.json", {})
    source_payload = load_json(catalog_dir / "sources.json", [])
    harness_payload = load_json(catalog_dir / "harnesses.json", [])
    preset_payload = load_json(catalog_dir / "presets.json", [])
    legacy = load_json(legacy_path, {})
    public_meta, public_stats, public_rows, public_unmapped_models = load_public_evidence(root)

    canonical_models = canonical_model_list(model_payload)
    canonical_benchmarks = canonical_benchmark_list(benchmark_payload)
    benchmark_profiles = (
        benchmark_profiles_payload
        if isinstance(benchmark_profiles_payload, Mapping)
        else {}
    )
    model_profiles = model_profile_map(model_profiles_payload)
    canonical_sources = canonical_source_list(source_payload)
    canonical_harnesses = canonical_harness_list(harness_payload)
    canonical_presets = canonical_preset_list(preset_payload)

    models_by_id = model_lookup(canonical_models)
    benchmarks_by_id = benchmark_lookup(canonical_benchmarks)
    source_by_id = {
        str(source.get("id")): dict(source)
        for source in canonical_sources
        if isinstance(source.get("id"), str)
    }
    harness_by_id = {
        str(harness.get("id")): dict(harness)
        for harness in canonical_harnesses
        if isinstance(harness.get("id"), str)
    }

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in load_jsonl(observations_path):
        normalized = normalize_observation(raw, models_by_id, benchmarks_by_id, source_by_id, harness_by_id)
        rows.append(normalized)
        seen_ids.add(str(normalized["id"]))
    for migrated in legacy_observations(legacy, models_by_id):
        if str(migrated["id"]) not in seen_ids:
            rows.append(normalize_observation(migrated, models_by_id, benchmarks_by_id, source_by_id, harness_by_id))

    # Keep only rows whose model and benchmark are registered in the catalog in
    # the default index.  Unknown candidate rows remain visible in runs with a
    # warning from the validator, but cannot create phantom matrix columns.
    registered_rows = [
        row for row in rows
        if row.get("model_id") in models_by_id and row.get("benchmark_id") in benchmarks_by_id
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    system_counts: dict[str, int] = {}
    for row in registered_rows:
        if isinstance(row.get("value"), (int, float)) and not isinstance(row.get("value"), bool):
            grouped.setdefault((str(row["model_id"]), str(row["benchmark_id"])), []).append(row)
            if not is_model_observation(row):
                model_id = str(row.get("model_id"))
                system_counts[model_id] = system_counts.get(model_id, 0) + 1
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    alternatives: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for key, candidates in grouped.items():
        # The atlas is release-level.  Keep only direct/model-only
        # observations here; every candidate (including system runs) remains
        # available in the System Runs view below.
        model_candidates = [candidate for candidate in candidates if is_model_observation(candidate)]
        if not model_candidates:
            continue
        ordered = sorted(model_candidates, key=observation_rank, reverse=True)
        selected[key] = ordered[0]
        alternatives[key] = ordered

    meta_legacy = legacy.get("meta") if isinstance(legacy, Mapping) else {}
    if not isinstance(meta_legacy, Mapping):
        meta_legacy = {}
    as_of, last_updated = derive_site_timestamps(
        meta_legacy,
        model_payload,
        model_profiles_payload,
        public_meta,
    )
    site_benchmarks = [
        benchmark_for_site(
            item,
            source_by_id,
            as_of,
            benchmark_profiles.get(str(item.get("id"))),
        )
        for item in canonical_benchmarks
    ]

    scored_models: list[dict[str, Any]] = []
    catalog_models: list[dict[str, Any]] = []
    for model in canonical_models:
        model_id = str(model.get("id"))
        chosen = {
            benchmark_id: selected[(model_id, benchmark_id)]
            for (selected_model, benchmark_id) in selected
            if selected_model == model_id
        }
        model_alternatives = {
            benchmark_id: alternatives[(model_id, benchmark_id)]
            for (selected_model, benchmark_id) in alternatives
            if selected_model == model_id
        }
        site_model = model_for_site(
            model,
            chosen,
            model_alternatives,
            benchmarks_by_id,
            source_by_id,
            harness_by_id,
            model_profiles.get(model_id),
        )
        site_model["systemRunCount"] = system_counts.get(model_id, 0)
        catalog_models.append(site_model)
        if chosen:
            scored_models.append(site_model)

    # Preserve explicit canonical order in the matrix; the UI can sort the
    # catalog independently without changing the deterministic source order.
    site_runs = [
        run_for_site(row, models_by_id, benchmarks_by_id, source_by_id, harness_by_id)
        for row in sorted(registered_rows, key=lambda item: (str(item.get("observed_at") or ""), str(item.get("id"))), reverse=True)
    ]
    # Public/reported evidence is a parallel display layer and cannot influence
    # canonical atlas statistics.  The complete review rows remain in
    # ``public.json``/``evidence.jsonl``; only the browser display contract is
    # embedded below.
    public_site_rows = [public_evidence_for_site(row) for row in public_rows]
    public_site_unmapped_models = [
        public_unmapped_model_for_site(row) for row in public_unmapped_models
    ]
    featured_ids = [item["id"] for item in site_benchmarks if item.get("featured")]
    numeric_rows = [
        row
        for row in registered_rows
        if isinstance(row.get("value"), (int, float))
        and not isinstance(row.get("value"), bool)
    ]
    # Coverage is a matrix property, not a row count.  A model can have many
    # historical observations (or several harness runs) for one cell; those
    # rows must not inflate the percentage beyond what the atlas can display.
    direct_cells = {
        (str(row.get("model_id")), str(row.get("benchmark_id")))
        for row in numeric_rows
        if is_model_observation(row)
    }
    numeric_count = len(numeric_rows)
    total_possible = len(canonical_models) * len(canonical_benchmarks)
    stats = {
        "catalogModels": len(catalog_models),
        "scoredModels": len(scored_models),
        "catalogOnlyModels": len(catalog_models) - len(scored_models),
        "benchmarks": len(site_benchmarks),
        "featuredBenchmarks": len(featured_ids),
        "sources": len(canonical_sources),
        "harnesses": len(canonical_harnesses),
        "presets": len(canonical_presets),
        "runs": len(site_runs),
        "systemRuns": sum(1 for row in registered_rows if not is_model_observation(row)),
        "observations": len(registered_rows),
        "numericObservations": numeric_count,
        "observedCells": len(direct_cells),
        "coverage": round(len(direct_cells) / total_possible, 4) if total_possible else 0,
        "coveragePct": round(100 * len(direct_cells) / total_possible, 1) if total_possible else 0,
        "legacyMigrated": sum(1 for row in registered_rows if row.get("legacy_migrated")),
        "modelProfiles": sum(1 for model in catalog_models if model.get("profile")),
        "modelProfilesMissing": sum(1 for model in catalog_models if not model.get("profile")),
    }
    meta = {
        "title": meta_legacy.get("title") or "Frontier Model Bench",
        "version": "0.3.0-derived",
        "dataVersion": "canonical-catalog-v1",
        "asOf": as_of,
        "status": "curated",
        "lastUpdated": last_updated,
        "owner": meta_legacy.get("owner") or "Cunxin Huang",
        "note": "Canonical catalog + long-form observations；公开披露层默认作为 coverage map 展示，catalog-only 行无分数且不参与成绩计算。",
        "updateCadence": meta_legacy.get("updateCadence") or "每周复核，重大模型发布时加急",
        "defaultView": "atlas",
        "defaultPreset": "public-coverage",
        "defaultBenchmarkIds": featured_ids,
        "generatedFrom": [
            "data/catalog/models.json",
            "data/catalog/benchmarks.json",
            "data/catalog/benchmark_profiles.json",
            "data/catalog/model_profiles.json",
            "data/catalog/sources.json",
            "data/catalog/harnesses.json",
            "data/catalog/presets.json",
            "data/observations/results.jsonl",
            "data/models.json (legacy fallback)",
            "data/derived/public.json (reported/unverified display layer, optional)",
        ],
    }
    site = {
        "meta": meta,
        "benchmarks": site_benchmarks,
        "models": scored_models,
        "sources": canonical_sources,
        "catalogModels": catalog_models,
        "harnesses": canonical_harnesses,
        "runs": site_runs,
        "presets": canonical_presets,
        "stats": stats,
        "publicEvidence": public_site_rows,
        "publicUnmappedModels": public_site_unmapped_models,
        "publicMeta": public_meta,
        "publicStats": public_stats,
    }
    write_compact_json(output, site)
    return site


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="仓库根目录")
    parser.add_argument("--output", type=Path, default=None, help="derived JSON 输出路径")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    output = (args.output.expanduser().resolve() if args.output else root / "data" / "derived" / "site.json")
    try:
        site = build(root, output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    stats = site.get("stats", {})
    print(
        "Built {path}: models={models}, catalogModels={catalog}, benchmarks={benchmarks}, "
        "runs={runs}, coverage={coverage}%".format(
            path=output,
            models=stats.get("scoredModels", 0),
            catalog=stats.get("catalogModels", 0),
            benchmarks=stats.get("benchmarks", 0),
            runs=stats.get("runs", 0),
            coverage=stats.get("coveragePct", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
