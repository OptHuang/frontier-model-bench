#!/usr/bin/env python3
"""Build the public/reported evidence index from leaderboard candidates.

The canonical matrix is intentionally conservative: only observations that
have passed the repository's identity/protocol review are written to
``data/observations/results.jsonl``.  That policy is useful for reproducible
claims, but it should not hide the large amount of information already
published by benchmark owners and model providers.  This script builds a
separate, display-oriented evidence layer from source adapter artifacts.

The output is *not* an importer and never mutates the canonical observations
or catalog.  Every row remains explicitly unverified and links back to the
source URL and a row/field locator.  Unknown model aliases are retained so a
future review can map them without another network fetch.

Typical use::

    python3 scripts/build_public_evidence.py \
      --root . --input-dir /tmp/fmb-public-audit-v2 \
      --input-dir /tmp/fmb-ale-audit \
      --jsonl-output data/public/evidence.jsonl \
      --output data/derived/public.json

``--input-dir`` may point at a fetch artifact root (containing one directory
per source) or at a single source directory.  The output is deterministic for
fixed inputs apart from ``generatedAt``; pass ``--generated-at`` when a
reproducible snapshot is desired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "artifacts" / "fetch"
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "public.json"
DEFAULT_JSONL_OUTPUT = ROOT / "data" / "public" / "evidence.jsonl"
DEFAULT_UNMAPPED_OUTPUT = ROOT / "data" / "public" / "unmapped.jsonl"
DEFAULT_ALTERNATIVES_OUTPUT = ROOT / "data" / "public" / "alternatives.jsonl"
DEFAULT_UNMAPPED_SUMMARY_OUTPUT = ROOT / "data" / "public" / "unmapped-summary.json"
DEFAULT_ALIAS_REGISTRY = ROOT / "data" / "public" / "model_aliases.json"
SCHEMA_VERSION = "public-evidence@0.1"
# The public layer is an index of what sources report.  Keep every mapped
# row by default; pass a positive value for a deliberately compact preview.
# (``0`` is interpreted as unlimited in ``select_public_rows``.)
DEFAULT_MAX_PER_KEY = 0

# Public tables sometimes mix task scores with counters and telemetry in the
# same row. Keep those measurements in the evidence ledger, but mark them as
# evidence-only so downstream consumers cannot mistake latency, tokens, or
# sample counts for benchmark performance.
PUBLIC_TELEMETRY_METRICS = {
    "eval",
    "train",
    "truncated",
    "prompt-tokens",
    "output-tokens",
    "input-tokens",
    "total-tokens",
    "observed-inference-time-s",
    "inference-time-s",
    "latency-ms",
    "runtime-seconds",
    "cost-usd",
    "num-samples",
    "sample-count",
    "n",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any, length: int = 24) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:length]


def _json_load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _iso_sort(value: Any) -> str:
    return str(value or "")


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _public_metric_key(value: Any) -> str:
    text = str(value or "score").strip().casefold()
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9@^]+", "-", text)) or "score"


def _is_public_telemetry_metric(value: Any) -> bool:
    key = _public_metric_key(value)
    return (
        key in PUBLIC_TELEMETRY_METRICS
        or key.startswith("prompt-tokens")
        or key.startswith("output-tokens")
        or key.startswith("observed-inference-time")
    )


def _as_list(payload: Any, key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key, []) if isinstance(payload, Mapping) else payload
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def load_catalog(root: Path) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Load optional labels from the canonical registries.

    Public candidates are allowed to reference entities that are not yet in
    the catalog, so lookup failures never discard a row.
    """

    result: dict[str, dict[str, Mapping[str, Any]]] = {
        "models": {},
        "benchmarks": {},
        "sources": {},
        "harnesses": {},
    }
    for kind, filename in (
        ("models", "models.json"),
        ("benchmarks", "benchmarks.json"),
        ("sources", "sources.json"),
        ("harnesses", "harnesses.json"),
    ):
        payload = _json_load(root / "data" / "catalog" / filename, [])
        for item in _as_list(payload, kind):
            identifier = _nonempty(item.get("id"))
            if identifier:
                result[kind][identifier] = item
    return result


def load_public_aliases(
    root: Path,
    models: Mapping[str, Mapping[str, Any]] | None = None,
    path: Path | None = None,
) -> tuple[dict[tuple[str, str], set[str]], dict[str, dict[str, Any]], list[str]]:
    """Load explicitly reviewed source-specific public model aliases.

    The normalizer intentionally avoids fuzzy matching because a release,
    endpoint, quantized checkpoint, and effort presentation can have nearly
    identical names.  This small registry is the opt-in escape hatch for
    aliases that have been inspected by a maintainer.  Entries are keyed by
    ``(source_id, normalized_alias)``; an entry without ``sourceIds`` is
    treated as a wildcard only when it maps to a single catalog release.

    The function returns the lookup, a note/metadata map keyed by
    ``source_id|normalized_alias``, and non-fatal validation warnings.  A
    malformed or unknown target is ignored rather than changing a row's
    identity implicitly.
    """

    alias_path = (path or DEFAULT_ALIAS_REGISTRY)
    if not alias_path.is_absolute():
        alias_path = root / alias_path
    payload = _json_load(alias_path, {})
    if not isinstance(payload, Mapping):
        return {}, {}, [f"alias registry is not an object: {alias_path.name}"]
    entries = payload.get("aliases", payload.get("modelAliases", []))
    if not isinstance(entries, list):
        return {}, {}, [f"alias registry aliases must be a list: {alias_path.name}"]
    known_models = set(models or {})
    lookup: dict[tuple[str, str], set[str]] = defaultdict(set)
    metadata: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping):
            warnings.append(f"alias registry entry {index} is not an object")
            continue
        target = _nonempty(item.get("canonicalModelId") or item.get("canonical_model_id"))
        if not target or (known_models and target not in known_models):
            warnings.append(f"alias registry entry {index} has unknown target: {target or 'missing'}")
            continue
        values = item.get("values", item.get("aliases", item.get("alias")))
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            warnings.append(f"alias registry entry {index} has no values")
            continue
        source_ids = item.get("sourceIds", item.get("source_ids", item.get("sourceId", item.get("source_id"))))
        if isinstance(source_ids, str):
            source_ids = [source_ids]
        if not isinstance(source_ids, list) or not source_ids:
            source_ids = ["*"]
        sources = [str(value).strip() for value in source_ids if str(value).strip()]
        if not sources:
            sources = ["*"]
        note = _nonempty(item.get("note"))
        confidence = _nonempty(item.get("confidence")) or "high"
        for value in values:
            normalized = _normal_model_text(value)
            if not normalized:
                warnings.append(f"alias registry entry {index} has empty alias")
                continue
            for source_id in sources:
                key = (source_id, normalized)
                lookup[key].add(target)
                metadata_key = f"{source_id}|{normalized}"
                metadata[metadata_key] = {
                    "registry": str(alias_path.name),
                    "note": note,
                    "confidence": confidence,
                }
    return lookup, metadata, warnings


def discover_candidate_files(input_dirs: Sequence[Path], input_files: Sequence[Path] = ()) -> tuple[list[Path], list[str]]:
    """Find only current candidate files, not immutable snapshot duplicates."""

    files: list[Path] = []
    errors: list[str] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            errors.append(f"input not found: {resolved}")
            return
        if resolved not in seen:
            seen.add(resolved)
            files.append(resolved)

    for raw in input_files:
        add(raw)
    for raw in input_dirs:
        path = raw.expanduser().resolve()
        if not path.exists():
            errors.append(f"input not found: {path}")
            continue
        if path.is_file():
            add(path)
            continue
        direct = path / "candidates.jsonl"
        if direct.is_file():
            add(direct)
            continue
        matches = sorted(path.glob("*/candidates.jsonl"))
        if not matches:
            errors.append(f"no candidates.jsonl under: {path}")
        for match in matches:
            add(match)
    return sorted(files), errors


def manifest_context(path: Path) -> dict[str, Any]:
    """Read provenance from the source manifest next to a candidate file."""

    manifest = _json_load(path.parent / "manifest.json", {})
    if not isinstance(manifest, Mapping):
        return {}
    wanted = (
        "source_id",
        "requested_url",
        "resolved_url",
        "retrieved_at",
        "http_status",
        "payload_sha256",
        "parser_version",
        "snapshot_dir",
        "warnings",
        "errors",
        "metadata",
    )
    return {key: manifest.get(key) for key in wanted if key in manifest}


def _source_label(source: Mapping[str, Any] | None, fallback: str) -> str:
    if not isinstance(source, Mapping):
        return fallback
    return str(source.get("label") or source.get("title") or source.get("publisher") or fallback)


def _source_url(source: Mapping[str, Any] | None) -> str | None:
    if not isinstance(source, Mapping):
        return None
    for key in ("url", "api_url", "download_url"):
        value = _nonempty(source.get(key))
        if value and _valid_url(value):
            return value
    return None


def _source_page_url(source: Mapping[str, Any] | None) -> str | None:
    """Return a human-facing context page, distinct from an API URL."""

    if not isinstance(source, Mapping):
        return None
    for key in ("web_url", "page_url", "homepage", "website", "url"):
        value = _nonempty(source.get(key))
        if value and _valid_url(value):
            return value
    return None


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _public_input_label(path: Path) -> str:
    """Render an artifact path without exposing a maintainer's local path."""

    resolved = path.resolve()
    if resolved.name == "candidates.jsonl":
        return f"{resolved.parent.name}/{resolved.name}"
    return resolved.name


def _metadata_url(metadata: Mapping[str, Any]) -> str | None:
    """Prefer a row-specific link while retaining the source endpoint too."""

    for key in (
        "submission_source_url",
        "leaderboard_url",
        "model_link",
        "source_url",
        "source_link",
        "sourceLink",
        "source",
        "url",
    ):
        value = _nonempty(metadata.get(key))
        if value and _valid_url(value):
            return value
    return None


def _normal_model_text(value: Any) -> str:
    """Return a conservative alias key for cross-source model matching.

    We remove an optional provider/repository prefix and punctuation, but do
    not strip release dates, effort tiers, or quantization suffixes.  This
    intentionally maps only obvious spelling differences; ambiguous or
    fuzzy-looking names stay unmapped for later review.
    """

    text = _nonempty(value) or ""
    text = text.casefold().strip()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


# These suffixes describe an endpoint/effort presentation rather than a new
# release identity on several public tables.  We only use the stripped form
# when it maps to exactly one catalog release; date/version and quantization
# suffixes are deliberately left intact to avoid mapping an old release to a
# current one.
_PRESENTATION_SUFFIXES = (
    "nonreasoning",
    "reasoning",
    "high-effort",
    "medium-effort",
    "low-effort",
    "xhigh",
    "high",
    "medium",
    "low",
    "thinking",
    "auto",
    "effort",
    "preview",
    "latest",
    "fast",
    "instant",
    "max",
    "64k",
    "32k",
)


def _model_alias_keys(value: Any) -> list[str]:
    """Generate exact and conservative presentation-normalized keys."""

    base = _normal_model_text(value)
    if not base:
        return []
    keys = [base]
    # Work on the punctuation-preserving spelling as well so e.g.
    # ``high-effort`` is removed as one suffix before punctuation is erased.
    text = (_nonempty(value) or "").casefold().strip()
    repository_qualified = "/" in text
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    changed = True
    while changed:
        changed = False
        for suffix in _PRESENTATION_SUFFIXES:
            # A repository-qualified ``provider/model-preview`` names an
            # upstream checkpoint, not a display-only effort tier.  Keep the
            # suffix so e.g. tencent/Hy3-preview cannot resolve to formal Hy3.
            if suffix == "preview" and (repository_qualified or base == "hy3preview"):
                continue
            # Leaderboards commonly put effort/speed variants in parentheses
            # (``GPT 5.5 (High)``) or append them with punctuation.  Strip
            # only these explicitly presentation-level suffixes; dates,
            # quantization and release numbers remain part of the alias.
            patterns = (
                r"\s*[\(\[]\s*" + re.escape(suffix) + r"\s*[\)\]]$",
                r"(?:[-_ .]+|^)" + re.escape(suffix) + r"$",
            )
            stripped = text
            for pattern in patterns:
                candidate = re.sub(pattern, "", text)
                if candidate != text:
                    stripped = candidate
                    break
            stripped = stripped.strip("-_. ")
            if stripped != text:
                text = stripped
                changed = True
                normalized = _normal_model_text(text)
                if normalized and normalized not in keys:
                    keys.append(normalized)
                break
    return keys


def build_model_alias_lookup(models: Mapping[str, Mapping[str, Any]]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = defaultdict(set)
    for model_id, model in models.items():
        values: list[Any] = [model_id, model.get("name")]
        aliases = model.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, Mapping):
                    values.extend((alias.get("value"), alias.get("name")))
                else:
                    values.append(alias)
        for value in values:
            # Do not add presentation-stripped variants for catalog values:
            # ``Qwen3.8 Max`` must not make a bare ``Qwen3.8`` source look
            # like the Max release.  Stripping is applied only to the source
            # spelling in ``annotate_public_mapping`` and must land on an
            # explicit catalog alias/base key.
            key = _normal_model_text(value)
            if key:
                lookup[key].add(model_id)
    return lookup


def annotate_public_mapping(
    row: dict[str, Any], alias_lookup: Mapping[str, set[str]]
) -> None:
    """Add a safe normalized alias match without changing source spelling."""

    if row.get("canonicalModelId"):
        return
    keys = _model_alias_keys(row.get("modelRef"))
    for key in keys:
        matches = sorted(alias_lookup.get(key, set()))
        if len(matches) == 1:
            row["canonicalModelId"] = matches[0]
            row["mappingStatus"] = "heuristic_alias"
            # Resolve the display name lazily in the caller's catalog-aware pass.
            row["mappingCandidates"] = matches
            flags = set(row.get("qualityFlags") or [])
            flags.add("heuristic_model_mapping")
            row["qualityFlags"] = sorted(flags)
            return
        if len(matches) > 1:
            # An ambiguous key must not block trying a more specific key (for
            # example ``gpt54`` can be ambiguous while ``gpt54mini`` is not).
            row["mappingStatus"] = "ambiguous_alias"
            row["mappingCandidates"] = matches


def annotate_curated_public_mapping(
    row: dict[str, Any],
    alias_lookup: Mapping[tuple[str, str], set[str]],
    alias_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Apply an explicit, source-scoped alias without guessing identity.

    Curated aliases run before the generic presentation-suffix normalizer.
    A source-specific mapping wins only when it resolves to exactly one
    catalog release; conflicting registry entries are left ambiguous.  The
    original ``modelRef`` is never changed, and the row remains public /
    unverified after mapping.
    """

    if row.get("canonicalModelId"):
        return
    source_id = _nonempty(row.get("sourceId")) or _nonempty(row.get("source_id")) or ""
    normalized = _normal_model_text(row.get("modelRef"))
    if not normalized:
        return
    keys = [(source_id, normalized), ("*", normalized)]
    matches: set[str] = set()
    matched_key: tuple[str, str] | None = None
    for key in keys:
        candidates = set(alias_lookup.get(key, set()))
        if not candidates:
            continue
        if matched_key is None:
            matched_key = key
            matches = candidates
        else:
            matches.update(candidates)
    if len(matches) != 1:
        if len(matches) > 1:
            row["mappingStatus"] = "ambiguous_alias"
            row["mappingCandidates"] = sorted(matches)
        return
    target = sorted(matches)[0]
    row["canonicalModelId"] = target
    row["mappingStatus"] = "curated_alias"
    row["mappingCandidates"] = [target]
    flags = set(row.get("qualityFlags") or [])
    flags.add("curated_model_alias")
    row["qualityFlags"] = sorted(flags)
    metadata_key = f"{matched_key[0]}|{normalized}" if matched_key else ""
    details = dict((alias_metadata or {}).get(metadata_key, {}))
    if details:
        row["mappingEvidence"] = details
        note = _nonempty(details.get("note"))
        if note:
            row["mappingNote"] = note


def _version(row: Mapping[str, Any], protocol: Mapping[str, Any], metadata: Mapping[str, Any]) -> tuple[str | None, str | None]:
    version_id = None
    version_label = None
    for key in ("benchmark_version_id", "benchmarkVersionId"):
        version_id = _nonempty(row.get(key)) or version_id
    for key in ("benchmark_version_id", "benchmarkVersionId", "version_id", "versionId"):
        version_id = version_id or _nonempty(protocol.get(key)) or _nonempty(metadata.get(key))
    for key in ("benchmark_version", "benchmarkVersion", "version", "release", "release_date", "releaseDate"):
        version_label = _nonempty(row.get(key)) or version_label
    for key in ("benchmark_version", "benchmarkVersion", "version", "release", "release_date", "releaseDate"):
        version_label = version_label or _nonempty(protocol.get(key)) or _nonempty(metadata.get(key))
    return version_id, version_label


def _harness(row: Mapping[str, Any], protocol: Mapping[str, Any], metadata: Mapping[str, Any]) -> tuple[str | None, str | None]:
    harness_id = _nonempty(row.get("harness_id")) or _nonempty(row.get("harnessId"))
    harness = _nonempty(protocol.get("harness")) or _nonempty(metadata.get("harness"))
    harness_id = harness_id or _nonempty(protocol.get("harness_id")) or _nonempty(metadata.get("harness_id"))
    return harness_id or harness, harness


def _public_metric_id(source_id: str, source_metric: str, protocol: Mapping[str, Any]) -> str:
    """Upgrade legacy source metric ids during deterministic artifact rebuilds."""

    if source_id.startswith("helm-") and source_metric == "score":
        table = _nonempty(protocol.get("table"))
        table_id = re.sub(r"[^a-z0-9]+", "-", str(table or "").casefold()).strip("-")
        if table_id and table_id != "accuracy":
            return f"{table_id}-score"
    if source_id == "lmarena-hf-dataset" and source_metric == "elo":
        # The official dataset column historically used ``elo`` even after
        # the leaderboard moved to Bradley-Terry model scores.  Preserve that
        # raw spelling in sourceMetricId, but do not present it as Elo.
        return "arena_score_bt"
    return source_metric


def _public_unit(source_id: str, source_metric: str, source_unit: Any) -> str:
    if source_id == "lmarena-hf-dataset" and source_metric == "elo":
        return "rating"
    return _nonempty(source_unit) or "unknown"


_SYSTEM_SUBJECT_TYPES = {"system", "agent", "agent-system", "agentic", "harness"}
_SYSTEM_HARNESS_KIND_TOKENS = ("agent", "terminal", "computer-use", "tool-use")
_MODEL_HARNESS_IDS = {"", "model-only", "lm-eval", "helm", "vendor-default", "unspecified-reported"}
_CANONICAL_MODEL_ID_MIGRATIONS = {
    # These catalog rows originally used ingestion dates in their IDs.  Keep
    # old adapter artifacts rebuildable while exposing the official release
    # date as the canonical identity.
    "qwen/qwen3.8-27b@2026-08-26": "qwen/qwen3.8-27b@2026-08-14",
    "qwen/qwen3.8-2.4t-a95b@2026-08-26": "qwen/qwen3.8-2.4t-a95b@2026-08-12",
}


def _canonical_model_id(value: Any) -> str | None:
    model_id = _nonempty(value)
    return _CANONICAL_MODEL_ID_MIGRATIONS.get(model_id, model_id)


def _resolve_subject_type(
    candidate: Mapping[str, Any],
    protocol: Mapping[str, Any],
    benchmark: Mapping[str, Any],
    harness: Mapping[str, Any],
    harness_id: str | None,
) -> tuple[str, str | None, list[str]]:
    """Resolve display semantics while retaining the source's own subject.

    A source row may call its immediate subject a model even though the
    registered benchmark evaluates a complete agent/environment system.  The
    public layer uses the stronger system semantic for routing, but publishes
    ``sourceSubjectType`` separately so this inference is auditable.
    """

    source_subject = _nonempty(candidate.get("subject_type")) or _nonempty(candidate.get("subjectType"))
    source_subject = source_subject or _nonempty(protocol.get("subject_type")) or _nonempty(protocol.get("subjectType"))
    source_subject = source_subject.casefold() if source_subject else None
    benchmark_mode = _nonempty(benchmark.get("evaluation_mode")) or _nonempty(benchmark.get("evaluationMode"))
    benchmark_mode = benchmark_mode.casefold() if benchmark_mode else None
    harness_kind = _nonempty(harness.get("kind")) or _nonempty(harness.get("type"))
    harness_kind = harness_kind.casefold() if harness_kind else None
    normalized_harness_id = str(harness_id or "").strip().casefold()

    signals: list[str] = []
    if source_subject in _SYSTEM_SUBJECT_TYPES:
        signals.append(f"source:subject_type={source_subject}")
    if benchmark_mode in _SYSTEM_SUBJECT_TYPES:
        signals.append(f"benchmark:evaluation_mode={benchmark_mode}")
    if harness_kind and any(token in harness_kind for token in _SYSTEM_HARNESS_KIND_TOKENS):
        signals.append(f"harness:kind={harness_kind}")
    elif (
        normalized_harness_id not in _MODEL_HARNESS_IDS
        and any(token in normalized_harness_id for token in ("agent", "codex", "claude-code", "terminus"))
    ):
        signals.append(f"harness:id={normalized_harness_id}")

    if signals:
        return "system", source_subject, signals
    if source_subject:
        return source_subject, source_subject, [f"source:subject_type={source_subject}"]
    return "model", None, ["default:model"]


def _reported_status(row: Mapping[str, Any], metadata: Mapping[str, Any]) -> tuple[str, str]:
    """Separate source publication state from repository review state.

    A numeric row parsed from a public leaderboard is *reported* even when
    the adapter calls it a ``candidate``.  Missing/non-numeric rows remain
    ``candidate`` because they are not a reported score.  ``review_status``
    is always ``unreviewed`` in this layer and ``verified`` is always false.
    """

    value = row.get("value")
    source_status = str(metadata.get("source_status") or row.get("status") or "").casefold()
    if _finite(value) and source_status not in {"missing", "unavailable", "not_evaluated"}:
        return "reported", "unreviewed"
    return "candidate", "unreviewed"


def _semantic_key(row: Mapping[str, Any]) -> dict[str, Any]:
    """Key used to collapse the same source row across repeated snapshots."""

    # Retrieval time, payload hash, and candidate_id are intentionally omitted:
    # those change on every refresh even when the published row does not.
    return {
        "sourceId": row.get("sourceId"),
        "modelRef": row.get("modelRef"),
        "canonicalModelId": row.get("canonicalModelId"),
        "benchmarkId": row.get("benchmarkId"),
        "benchmarkVersionId": row.get("benchmarkVersionId"),
        "metricId": row.get("metricId"),
        "subjectType": row.get("subjectType"),
        "sourceSubjectType": row.get("sourceSubjectType"),
        "harnessId": row.get("harnessId"),
        "value": row.get("value"),
        "rawValue": row.get("rawValue"),
        "unit": row.get("unit"),
        "rank": row.get("rank"),
        "sourceLocator": row.get("sourceLocator"),
        "protocol": row.get("protocol") or {},
    }


def _comparison_key(row: Mapping[str, Any]) -> dict[str, Any]:
    """Key excluding score value, useful for flagging source conflicts."""

    key = _semantic_key(row)
    key.pop("value", None)
    key.pop("rawValue", None)
    return key


def normalize_candidate(
    candidate: Mapping[str, Any],
    manifest: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    artifact_path: Path,
) -> dict[str, Any]:
    """Convert an adapter candidate to the stable public evidence shape."""

    metadata_raw = candidate.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, Mapping) else {}
    protocol_raw = candidate.get("protocol")
    protocol = dict(protocol_raw) if isinstance(protocol_raw, Mapping) else {}
    source_id = _nonempty(candidate.get("source_id")) or _nonempty(manifest.get("source_id")) or "unknown-source"
    model_ref = _nonempty(candidate.get("model_ref"))
    benchmark_id = _nonempty(candidate.get("benchmark_ref")) or "unknown-benchmark"
    source_metric_id = _nonempty(candidate.get("metric")) or "score"
    metric_id = _public_metric_id(source_id, source_metric_id, protocol)
    version_id, version_label = _version(candidate, protocol, metadata)
    version_status = "source_reported" if version_id else ("source_hint" if version_label else "unknown")
    benchmark_catalog = catalog.get("benchmarks", {}).get(benchmark_id, {})
    benchmark_version_hint = None
    if not version_id and isinstance(benchmark_catalog, Mapping):
        default_version = benchmark_catalog.get("default_version_id") or benchmark_catalog.get("defaultVersionId")
        if _nonempty(default_version):
            benchmark_version_hint = str(default_version)
            version_status = "catalog_default_hint"
    harness_id, harness = _harness(candidate, protocol, metadata)
    harness_catalog = catalog.get("harnesses", {}).get(harness_id or "", {})
    subject_type, source_subject_type, subject_inferred_by = _resolve_subject_type(
        candidate,
        protocol,
        benchmark_catalog if isinstance(benchmark_catalog, Mapping) else {},
        harness_catalog if isinstance(harness_catalog, Mapping) else {},
        harness_id,
    )
    source = catalog.get("sources", {}).get(source_id)
    manifest_url = _nonempty(manifest.get("resolved_url")) or _nonempty(manifest.get("requested_url"))
    # Never publish local ``file://`` or maintainer-path links from an
    # adapter artifact.  Prefer a row-specific HTTP link, then the immutable
    # fetch manifest, then the catalog source endpoint.
    source_url = next(
        (
            value
            for value in (
                _nonempty(candidate.get("source_url")),
                manifest_url,
                _source_url(source),
            )
            if _valid_url(value)
        ),
        None,
    )
    row_url = _metadata_url(metadata)
    status, review_status = _reported_status(candidate, metadata)
    canonical_model_id = _canonical_model_id(candidate.get("canonical_model_id"))
    mapping_status = _nonempty(candidate.get("mapping_status")) or ("exact_alias" if canonical_model_id else "unmatched")
    retrieved_at = _nonempty(manifest.get("retrieved_at")) or _nonempty(candidate.get("retrieved_at"))
    payload_sha256 = _nonempty(manifest.get("payload_sha256"))
    observed_at = _nonempty(candidate.get("observed_at"))
    published_at = _nonempty(candidate.get("published_at"))
    source_locator = _nonempty(candidate.get("source_locator"))
    quality_flags = candidate.get("quality_flags")
    if not isinstance(quality_flags, list):
        quality_flags = []
    quality_flags = list(quality_flags)
    if version_status == "catalog_default_hint":
        quality_flags.append("inferred_benchmark_version_hint")
    elif version_status == "source_hint":
        quality_flags.append("source_version_label_without_id")
    mapping_candidates = candidate.get("mapping_candidates")
    if not isinstance(mapping_candidates, list):
        mapping_candidates = []
    mapping_candidates = [
        migrated
        for item in mapping_candidates
        if (migrated := _canonical_model_id(item)) is not None
    ]

    row: dict[str, Any] = {
        # Stable public id is independent of refresh timestamp.  If a source
        # reports a changed value at the same locator, it becomes a distinct
        # row and can be shown as a conflict rather than silently overwritten.
        "id": "pub-" + _digest(
            {
                "sourceId": source_id,
                "modelRef": model_ref,
                "canonicalModelId": canonical_model_id,
                "benchmarkId": benchmark_id,
                "benchmarkVersionId": version_id,
                "metricId": metric_id,
                "subjectType": subject_type,
                "sourceSubjectType": source_subject_type,
                "harnessId": harness_id,
                "value": candidate.get("value"),
                "rawValue": candidate.get("raw_value"),
                "unit": candidate.get("unit"),
                "rank": candidate.get("rank"),
                "sourceLocator": source_locator,
                "protocol": protocol,
            }
        ),
        "modelRef": model_ref,
        "canonicalModelId": canonical_model_id,
        "mappingStatus": mapping_status,
        "mappingCandidates": sorted(str(item) for item in mapping_candidates),
        "modelName": (
            catalog.get("models", {}).get(canonical_model_id or "", {}).get("name")
            if canonical_model_id
            else None
        ),
        "benchmarkId": benchmark_id,
        "benchmarkName": catalog.get("benchmarks", {}).get(benchmark_id, {}).get("name"),
        "benchmarkVersionId": version_id,
        "benchmarkVersion": version_label,
        "benchmarkVersionHint": benchmark_version_hint,
        "benchmarkVersionStatus": version_status,
        "metricId": metric_id,
        "sourceMetricId": source_metric_id,
        "matrixExcluded": _is_public_telemetry_metric(metric_id),
        "matrixExcludedReason": (
            "telemetry_metric" if _is_public_telemetry_metric(metric_id) else None
        ),
        "value": candidate.get("value") if _finite(candidate.get("value")) else None,
        "rawValue": candidate.get("raw_value"),
        "unit": _public_unit(source_id, source_metric_id, candidate.get("unit")),
        "rank": candidate.get("rank"),
        "status": status,
        "reviewStatus": review_status,
        "verified": False,
        "verificationStatus": "not_reproduced",
        "verification_status": "not_reproduced",
        "evidenceNote": "公开来源报告值；尚未由本项目独立复现/核验。",
        "evidenceLevel": _nonempty(candidate.get("evidence_level")) or "D",
        "comparability": _nonempty(candidate.get("comparability")) or "conditional",
        "subjectType": subject_type,
        "sourceSubjectType": source_subject_type,
        "subjectInferredBy": subject_inferred_by,
        "harnessId": harness_id,
        "harness": harness,
        "protocol": protocol,
        "observedAt": observed_at,
        "publishedAt": published_at,
        "sourceId": source_id,
        "sourceLabel": _source_label(source, source_id),
        "sourceUrl": source_url,
        "sourcePageUrl": _source_page_url(source),
        "sourceApiUrl": _nonempty(source.get("api_url")) if isinstance(source, Mapping) else None,
        # ``evidenceUrl`` is the row-level/model-card link when available;
        # ``sourceUrl`` remains the immutable endpoint/snapshot link.
        "evidenceUrl": row_url or source_url,
        "sourceLocator": source_locator,
        "retrievedAt": retrieved_at,
        "payloadSha256": payload_sha256,
        "parserVersion": _nonempty(manifest.get("parser_version")),
        "httpStatus": manifest.get("http_status"),
        "qualityFlags": sorted({str(flag) for flag in quality_flags if str(flag).strip()}),
        "candidateId": _nonempty(candidate.get("candidate_id")),
        "sourceRow": {
            # Do not leak a maintainer's absolute /tmp or home path into a
            # public static artifact.  The source id, URL, locator and hash
            # are the durable evidence pointers; this short hint is only for
            # local review packets.
            "artifact": f"{artifact_path.parent.name}/{artifact_path.name}",
            "sourceStatus": metadata.get("source_status") or candidate.get("status"),
            "metadata": metadata,
        },
    }
    # Keep explicit source flags and uncertainty when supplied by an adapter;
    # these are useful in the detail drawer but not needed for matrix joins.
    for key in ("source_flags", "uncertainty"):
        if key in candidate:
            row["sourceRow"][key] = candidate[key]
    return row


def read_candidates(files: Sequence[Path], catalog: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in files:
        manifest = manifest_context(path)
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path}: cannot read: {exc}")
            continue
        with handle:
            for line_number, raw in enumerate(handle, 1):
                text = raw.strip()
                if not text or text.startswith("#"):
                    continue
                try:
                    candidate = json.loads(text)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_number}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(candidate, Mapping):
                    errors.append(f"{path}:{line_number}: candidate must be an object")
                    continue
                row = normalize_candidate(candidate, manifest, catalog, artifact_path=path)
                row["sourceRow"]["line"] = line_number
                rows.append(row)
    return rows, errors


def _choose_duplicate(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the newest snapshot while aggregating refresh provenance."""

    left = _iso_sort(current.get("retrievedAt"))
    right = _iso_sort(incoming.get("retrievedAt"))
    chosen = dict(incoming if right >= left else current)
    locations: list[Mapping[str, Any]] = []
    for item in (current.get("snapshotLocations"), incoming.get("snapshotLocations")):
        if isinstance(item, list):
            locations.extend(x for x in item if isinstance(x, Mapping))
    if not locations:
        for item in (current, incoming):
            source_row = item.get("sourceRow")
            if isinstance(source_row, Mapping):
                locations.append({
                    "artifact": source_row.get("artifact"),
                    "line": source_row.get("line"),
                    "retrievedAt": item.get("retrievedAt"),
                    "payloadSha256": item.get("payloadSha256"),
                })
    # Stable de-duplication of location records.
    seen: set[str] = set()
    unique_locations: list[Mapping[str, Any]] = []
    for location in locations:
        key = _canonical_json(location)
        if key not in seen:
            seen.add(key)
            unique_locations.append(location)
    chosen["snapshotLocations"] = sorted(unique_locations, key=lambda x: (_iso_sort(x.get("retrievedAt")), str(x.get("artifact")), int(x.get("line") or 0)))
    chosen["snapshotCount"] = len(chosen["snapshotLocations"])
    return chosen


def deduplicate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _digest(_semantic_key(row), length=40)
        if key in by_key:
            by_key[key] = _choose_duplicate(by_key[key], row)
        else:
            copied = dict(row)
            source_row = copied.get("sourceRow")
            copied["snapshotLocations"] = [
                {
                    "artifact": source_row.get("artifact") if isinstance(source_row, Mapping) else None,
                    "line": source_row.get("line") if isinstance(source_row, Mapping) else None,
                    "retrievedAt": copied.get("retrievedAt"),
                    "payloadSha256": copied.get("payloadSha256"),
                }
            ]
            copied["snapshotCount"] = 1
            by_key[key] = copied

    # Mark reports that share the same source/model/benchmark/protocol but
    # disagree on value.  They remain separate rows by design.
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in by_key.values():
        groups[_digest(_comparison_key(row), length=32)].append(row)
    for group_id, group in groups.items():
        values = {_canonical_json((item.get("value"), item.get("rawValue"))) for item in group}
        if len(values) > 1:
            for item in group:
                item["conflictGroup"] = "conflict-" + group_id
                flags = set(item.get("qualityFlags") or [])
                flags.add("reported_value_conflict")
                item["qualityFlags"] = sorted(flags)
    return sorted(
        by_key.values(),
        key=lambda item: (
            str(item.get("benchmarkId") or ""),
            str(item.get("modelRef") or ""),
            str(item.get("metricId") or ""),
            str(item.get("harnessId") or ""),
            str(item.get("sourceId") or ""),
            str(item.get("sourceLocator") or ""),
            str(item.get("id") or ""),
        ),
    )


_EVIDENCE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}


def _selection_group(row: Mapping[str, Any]) -> str:
    """Group rows for the compact public index.

    A source can publish many effort tiers/splits for one model and metric.
    The default full mode keeps every mapped row; a positive cap can be used
    for a compact preview.  Unmapped rows are always preserved in the
    unresolved JSONL/summary queue rather than guessed into a release.
    """

    return _digest(
        {
            "model": row.get("canonicalModelId") or row.get("modelRef"),
            "benchmark": row.get("benchmarkId"),
            "metric": row.get("metricId"),
            "source": row.get("sourceId"),
        },
        length=40,
    )


def _row_priority(
    row: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> tuple[Any, ...]:
    """Sort high-value, current, and more inspectable reports first."""

    benchmark = catalog.get("benchmarks", {}).get(str(row.get("benchmarkId")), {})
    model = catalog.get("models", {}).get(str(row.get("canonicalModelId")), {})
    status_rank = {"reported": 2, "candidate": 1}.get(str(row.get("status")), 0)
    # Release dates are strings in ISO form in the catalog; lexical ordering
    # gives the desired current/previous preference without parsing free text.
    release = str(model.get("release_date") or model.get("release") or "")
    rank = row.get("rank")
    rank_score = -float(rank) if _finite(rank) else -1000000000.0
    return (
        1 if row.get("canonicalModelId") else 0,
        1 if benchmark.get("featured") else 0,
        _EVIDENCE_RANK.get(str(row.get("evidenceLevel")), 0),
        1 if _finite(row.get("value")) else 0,
        status_rank,
        1 if row.get("observedAt") else 0,
        release,
        rank_score,
        _iso_sort(row.get("retrievedAt")),
        str(row.get("id") or ""),
    )


def select_public_rows(
    rows: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    max_per_key: int = DEFAULT_MAX_PER_KEY,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select a compact display set and return all omitted rows separately.

    The selected set includes mapped rows first.  If a group has no canonical
    mapping, its rows remain available in the complete unmapped export rather
    than being silently guessed into a model cell.  ``max_per_key`` keeps ALE
    effort/split variants and similar source tables legible while retaining
    a count and provenance for later review.
    """

    if max_per_key < 0:
        raise ValueError("max_per_key must be zero or positive")
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_selection_group(row)].append(dict(row))

    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    for group_id, group in grouped.items():
        ordered = sorted(group, key=lambda item: _row_priority(item, catalog), reverse=True)
        mapped = any(item.get("canonicalModelId") for item in ordered)
        # For a group with no mapping, keep it in the full audit export.  This
        # prevents a large third-party table from inflating the page payload.
        # ``0`` is the full mapped snapshot mode.  Unmapped rows remain in
        # the separate queue because assigning them a canonical release would
        # be an identity guess.
        full_group = mapped and (max_per_key == 0 or len(ordered) <= max_per_key)
        take = ordered if full_group else (ordered[:max_per_key] if mapped else [])
        for index, item in enumerate(take, 1):
            item["selection"] = "curated"
            item["selectionRank"] = index
            item["alternativesCount"] = len(group)
            item["selectionKey"] = group_id
            item["selectionReason"] = [
                "canonical_model_mapping",
                "all_source_variants" if full_group else "bounded_source_variants",
            ]
            selected.append(item)
        for item in ordered[len(take) :]:
            item["selection"] = "unmapped" if not mapped else "alternative"
            item["selectionRank"] = None
            item["alternativesCount"] = len(group)
            item["selectionKey"] = group_id
            item["unmappedReason"] = (
                "no_safe_model_alias" if not mapped else "bounded_alternative_not_loaded"
            )
            omitted.append(item)

    def sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            str(item.get("benchmarkId") or ""),
            str(item.get("modelRef") or ""),
            str(item.get("metricId") or ""),
            str(item.get("sourceId") or ""),
            int(item.get("selectionRank") or 0),
            str(item.get("id") or ""),
        )
    return sorted(selected, key=sort_key), sorted(omitted, key=sort_key)


def build_index(
    root: Path,
    input_dirs: Sequence[Path],
    input_files: Sequence[Path] = (),
    *,
    generated_at: str | None = None,
    max_per_key: int = DEFAULT_MAX_PER_KEY,
) -> dict[str, Any]:
    catalog = load_catalog(root)
    curated_alias_lookup, curated_alias_metadata, alias_warnings = load_public_aliases(
        root,
        catalog.get("models", {}),
    )
    files, discovery_errors = discover_candidate_files(input_dirs, input_files)
    raw_rows, read_errors = read_candidates(files, catalog)
    alias_lookup = build_model_alias_lookup(catalog.get("models", {}))
    for row in raw_rows:
        # Apply explicit source-scoped aliases first.  The generic matcher
        # remains deliberately conservative and is only a fallback.
        annotate_curated_public_mapping(row, curated_alias_lookup, curated_alias_metadata)
        annotate_public_mapping(row, alias_lookup)
        canonical_id = row.get("canonicalModelId")
        if canonical_id:
            model = catalog.get("models", {}).get(str(canonical_id))
            if isinstance(model, Mapping):
                row["modelName"] = model.get("name") or row.get("modelName")
    all_rows = deduplicate_rows(raw_rows)
    selected_rows, omitted_rows = select_public_rows(
        all_rows,
        catalog,
        max_per_key=max_per_key,
    )
    # Counts describe the complete de-duplicated evidence universe, not only
    # the compact page payload.  This makes the UI transparent about what is
    # available in the separate unmapped/alternative export.
    source_counts = Counter(str(row.get("sourceId") or "unknown-source") for row in all_rows)
    benchmark_counts = Counter(str(row.get("benchmarkId") or "unknown-benchmark") for row in all_rows)
    model_counts = Counter(str(row.get("canonicalModelId") or row.get("modelRef") or "unknown-model") for row in all_rows)
    harness_counts = Counter(str(row.get("harnessId")) for row in all_rows if row.get("harnessId"))
    status_counts = Counter(str(row.get("status") or "candidate") for row in all_rows)
    mapping_counts = Counter(str(row.get("mappingStatus") or "unmatched") for row in all_rows)
    numeric_rows = [row for row in all_rows if _finite(row.get("value"))]
    mapped_rows = [row for row in all_rows if row.get("canonicalModelId")]
    mapped_performance_rows = [row for row in mapped_rows if not row.get("matrixExcluded")]
    mapped_telemetry_rows = [row for row in mapped_rows if row.get("matrixExcluded")]
    retrieved_values = sorted(str(row.get("retrievedAt")) for row in all_rows if row.get("retrievedAt"))
    payload_hashes = sorted({str(row.get("payloadSha256")) for row in all_rows if row.get("payloadSha256")})
    sources = []
    for source_id, count in sorted(source_counts.items()):
        source = catalog.get("sources", {}).get(source_id, {})
        sources.append({
            "id": source_id,
            "label": _source_label(source, source_id),
            "url": _source_url(source),
            "rowCount": count,
        })
    benchmark_rows: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    model_rows: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in all_rows:
        benchmark_rows[str(row.get("benchmarkId") or "unknown-benchmark")].append(row)
        model_rows[str(row.get("canonicalModelId") or row.get("modelRef") or "unknown-model")].append(row)
    benchmarks = []
    for identifier, count in sorted(benchmark_counts.items()):
        group = benchmark_rows[identifier]
        retrieved = sorted(str(row.get("retrievedAt")) for row in group if row.get("retrievedAt"))
        observed = sorted(
            str(row.get("observedAt") or row.get("publishedAt"))
            for row in group
            if row.get("observedAt") or row.get("publishedAt")
        )
        benchmarks.append({
            "id": identifier,
            "name": catalog.get("benchmarks", {}).get(identifier, {}).get("name"),
            "rowCount": count,
            "numericRowCount": sum(1 for row in group if _finite(row.get("value"))),
            "modelCount": len({str(row.get("canonicalModelId") or row.get("modelRef") or "") for row in group}),
            "sourceIds": sorted({str(row.get("sourceId")) for row in group if row.get("sourceId")}),
            "metricIds": sorted({str(row.get("metricId")) for row in group if row.get("metricId")}),
            "units": sorted({str(row.get("unit")) for row in group if row.get("unit")}),
            "latestObservedAt": observed[-1] if observed else None,
            "latestRetrievedAt": retrieved[-1] if retrieved else None,
        })
    models = []
    for identifier, count in sorted(model_counts.items()):
        group = model_rows[identifier]
        retrieved = sorted(str(row.get("retrievedAt")) for row in group if row.get("retrievedAt"))
        observed = sorted(
            str(row.get("observedAt") or row.get("publishedAt"))
            for row in group
            if row.get("observedAt") or row.get("publishedAt")
        )
        model = catalog.get("models", {}).get(identifier, {})
        mapping_statuses = Counter(str(row.get("mappingStatus") or "unmatched") for row in group)
        models.append({
            "id": identifier,
            "name": model.get("name") if isinstance(model, Mapping) else None,
            "rowCount": count,
            "numericRowCount": sum(1 for row in group if _finite(row.get("value"))),
            "benchmarkCount": len({str(row.get("benchmarkId")) for row in group if row.get("benchmarkId")}),
            "sourceIds": sorted({str(row.get("sourceId")) for row in group if row.get("sourceId")}),
            "mappingStatusCounts": dict(sorted(mapping_statuses.items())),
            "latestObservedAt": observed[-1] if observed else None,
            "latestRetrievedAt": retrieved[-1] if retrieved else None,
            "mapped": identifier in catalog.get("models", {}),
        })
    errors = discovery_errors + read_errors + alias_warnings
    generated = generated_at or utc_now()
    return {
        "meta": {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAt": generated,
            "status": "reported-unverified",
            "verified": False,
            "reviewStatus": "unreviewed",
            "note": "公开榜单/模型卡报告值的展示层；不等同于本项目复现，也不覆盖 canonical observations。",
            "inputFiles": [_public_input_label(path) for path in files],
            "errors": errors,
            "aliasRegistry": "data/public/model_aliases.json",
            "payloadHashes": payload_hashes,
            "selection": {
                "maxPerModelBenchmarkMetricSource": max_per_key,
                "selectedPolicy": "all mapped rows by default; positive max_per_key keeps the highest evidence/current/featured/numeric variants",
                "omittedPolicy": "complete omitted rows are written to unmapped/alternatives JSONL",
            },
        },
        "stats": {
            "rows": len(selected_rows),
            "inputRows": len(raw_rows),
            "deduplicatedRows": len(all_rows),
            "selectedRows": len(selected_rows),
            "omittedRows": len(omitted_rows),
            "reportedRows": status_counts.get("reported", 0),
            "candidateRows": status_counts.get("candidate", 0),
            "numericRows": len(numeric_rows),
            "selectedReportedRows": sum(1 for row in selected_rows if row.get("status") == "reported"),
            "selectedCandidateRows": sum(1 for row in selected_rows if row.get("status") == "candidate"),
            "mappedRows": sum(1 for row in all_rows if row.get("canonicalModelId")),
            "mappedPerformanceRows": len(mapped_performance_rows),
            "mappedTelemetryRows": len(mapped_telemetry_rows),
            # ``mappedCells`` follows the matrix's model × benchmark grain;
            # keep the metric-inclusive count separately for audit users who
            # need to distinguish multiple metrics within one visual cell.
            "mappedCells": len({
                (
                    str(row.get("canonicalModelId")),
                    str(row.get("benchmarkId")),
                )
                for row in all_rows
                if row.get("canonicalModelId")
            }),
            "mappedMetricCells": len({
                (
                    str(row.get("canonicalModelId")),
                    str(row.get("benchmarkId")),
                    str(row.get("metricId")),
                )
                for row in all_rows
                if row.get("canonicalModelId")
            }),
            "mappedPerformanceMetricCells": len({
                (
                    str(row.get("canonicalModelId")),
                    str(row.get("benchmarkId")),
                    str(row.get("metricId")),
                )
                for row in mapped_performance_rows
            }),
            "mappedTelemetryMetricCells": len({
                (
                    str(row.get("canonicalModelId")),
                    str(row.get("benchmarkId")),
                    str(row.get("metricId")),
                )
                for row in mapped_telemetry_rows
            }),
            "curatedAliasRows": sum(1 for row in all_rows if row.get("mappingStatus") == "curated_alias"),
            "unmappedRows": sum(1 for row in all_rows if not row.get("canonicalModelId")),
            "conflictRows": sum(1 for row in all_rows if row.get("conflictGroup")),
            "sources": len(source_counts),
            "benchmarks": len(benchmark_counts),
            "models": len(model_counts),
            "harnesses": len(harness_counts),
            "snapshotCount": sum(int(row.get("snapshotCount") or 1) for row in all_rows),
            "sourceCounts": dict(sorted(source_counts.items())),
            "benchmarkCounts": dict(sorted(benchmark_counts.items())),
            "statusCounts": dict(sorted(status_counts.items())),
            "mappingCounts": dict(sorted(mapping_counts.items())),
            "retrievedAtMin": retrieved_values[0] if retrieved_values else None,
            "retrievedAtMax": retrieved_values[-1] if retrieved_values else None,
        },
        "sources": sources,
        "benchmarks": benchmarks,
        "models": models,
        "rows": selected_rows,
        "omitted": {
            "unmappedPath": "data/public/unmapped.jsonl",
            "unmappedSummaryPath": "data/public/unmapped-summary.json",
            "alternativesPath": "data/public/alternatives.jsonl",
            "rows": len(omitted_rows),
            "unmappedRows": sum(1 for row in omitted_rows if row.get("selection") == "unmapped"),
            "alternativeRows": sum(1 for row in omitted_rows if row.get("selection") == "alternative"),
            "includes": ["unmapped", "bounded alternatives"],
        },
        # Internal writer hint; removed from the JSON file by write_index.
        "_omittedRows": omitted_rows,
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def build_unmapped_summary(index: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact, path-safe index of source model refs left unmapped.

    The complete rows stay in ``unmapped.jsonl`` for forensic review.  This
    companion index makes the unresolved aliases discoverable without loading
    a large JSONL file in the browser or leaking the maintainer's local
    artifact path.  It deliberately reports source spellings and candidate
    hints only; it never promotes an alias to a catalog release.
    """

    omitted = index.get("_omittedRows", [])
    rows = [
        row
        for row in omitted
        if isinstance(row, Mapping) and row.get("selection") == "unmapped"
    ]
    by_alias: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    benchmark_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    mapping_counts: Counter[str] = Counter()
    numeric_rows = 0
    for row in rows:
        source_id = str(row.get("sourceId") or "unknown-source")
        model_ref = str(row.get("modelRef") or "")
        benchmark_id = str(row.get("benchmarkId") or "unknown-benchmark")
        by_alias[(source_id, model_ref)].append(row)
        source_counts[source_id] += 1
        benchmark_counts[benchmark_id] += 1
        status_counts[str(row.get("status") or "candidate")] += 1
        mapping_counts[str(row.get("mappingStatus") or "unmatched")] += 1
        numeric_rows += 1 if _finite(row.get("value")) else 0

    source_by_id = {
        str(item.get("id")): item
        for item in (index.get("sources") or [])
        if isinstance(item, Mapping) and item.get("id")
    }
    aliases: list[dict[str, Any]] = []
    for (source_id, model_ref), group in sorted(
        by_alias.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1]),
    ):
        group_benchmarks = sorted({str(row.get("benchmarkId")) for row in group if row.get("benchmarkId")})
        group_metrics = sorted({str(row.get("metricId")) for row in group if row.get("metricId")})
        group_urls = sorted({str(row.get("sourceUrl")) for row in group if _valid_url(row.get("sourceUrl"))})
        observed = sorted(
            str(row.get("observedAt") or row.get("publishedAt"))
            for row in group
            if row.get("observedAt") or row.get("publishedAt")
        )
        candidates = sorted(
            {
                str(candidate)
                for row in group
                for candidate in (row.get("mappingCandidates") or [])
                if str(candidate).strip()
            }
        )
        examples: list[dict[str, Any]] = []
        for row in sorted(
            group,
            key=lambda item: (
                str(item.get("benchmarkId") or ""),
                str(item.get("sourceLocator") or ""),
                str(item.get("id") or ""),
            ),
        )[:3]:
            source_row = row.get("sourceRow") if isinstance(row.get("sourceRow"), Mapping) else {}
            examples.append(
                {
                    "benchmarkId": row.get("benchmarkId"),
                    "benchmarkName": row.get("benchmarkName"),
                    "metricId": row.get("metricId"),
                    "value": row.get("value"),
                    "rawValue": row.get("rawValue"),
                    "unit": row.get("unit"),
                    "sourceId": row.get("sourceId"),
                    "sourceLabel": row.get("sourceLabel"),
                    "sourceUrl": row.get("sourceUrl"),
                    "evidenceUrl": row.get("evidenceUrl"),
                    "sourceLocator": row.get("sourceLocator"),
                    "observedAt": row.get("observedAt") or row.get("publishedAt"),
                    "protocol": row.get("protocol") or {},
                    "artifact": source_row.get("artifact"),
                    "line": source_row.get("line"),
                }
            )
        source = source_by_id.get(source_id, {})
        source_label = _source_label(source, source_id)
        aliases.append(
            {
                "sourceId": source_id,
                "sourceLabels": [source_label],
                "modelRef": model_ref,
                "rowCount": len(group),
                "numericRowCount": sum(1 for row in group if _finite(row.get("value"))),
                "benchmarkCount": len(group_benchmarks),
                "sourceIds": [source_id],
                "statusCounts": dict(sorted(Counter(str(row.get("status") or "candidate") for row in group).items())),
                "mappingStatusCounts": dict(sorted(Counter(str(row.get("mappingStatus") or "unmatched") for row in group).items())),
                "benchmarkIds": group_benchmarks,
                "metricIds": group_metrics,
                "sourceUrls": group_urls,
                "mappingCandidates": candidates,
                "observedAtMin": observed[0] if observed else None,
                "observedAtMax": observed[-1] if observed else None,
                "latestRetrievedAt": max((str(row.get("retrievedAt")) for row in group if row.get("retrievedAt")), default=None),
                # ``examples`` is deliberately the single compact sample
                # field.  The model directory normalizer accepts this name
                # (and legacy ``sampleEvidence``), so do not duplicate the
                # same objects and inflate the static site payload.
                "examples": examples,
            }
        )
    stats = index.get("stats") if isinstance(index.get("stats"), Mapping) else {}
    generated_at = (index.get("meta") or {}).get("generatedAt") if isinstance(index.get("meta"), Mapping) else None
    return {
        "meta": {
            "schemaVersion": "public-unmapped-summary@0.1",
            "generatedAt": generated_at,
            "status": "unmapped-unreviewed",
            "verified": False,
            "fullRowsPath": "data/public/unmapped.jsonl",
            "note": "Source model spellings without a safe canonical release alias; inspect and promote only with an explicit, source-scoped review.",
            "publicEvidenceGeneratedAt": generated_at,
        },
        "stats": {
            "rows": len(rows),
            "numericRows": numeric_rows,
            "uniqueAliases": len(aliases),
            "uniqueSources": len(source_counts),
            "uniqueBenchmarks": len(benchmark_counts),
            "sourceCounts": dict(sorted(source_counts.items())),
            "benchmarkCounts": dict(sorted(benchmark_counts.items())),
            "statusCounts": dict(sorted(status_counts.items())),
            "mappingCounts": dict(sorted(mapping_counts.items())),
            "publicDeduplicatedRows": stats.get("deduplicatedRows"),
        },
        "aliases": aliases,
    }


def write_unmapped_summary(path: Path, index: Mapping[str, Any]) -> None:
    """Write the path-safe unresolved model-reference summary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_unmapped_summary(index), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_index(
    index: Mapping[str, Any],
    output: Path,
    jsonl_output: Path | None = None,
    unmapped_output: Path | None = None,
    alternatives_output: Path | None = None,
    unmapped_summary_output: Path | None = None,
) -> None:
    """Write the public index and optional long-form exports."""

    output.parent.mkdir(parents=True, exist_ok=True)
    # ``_omittedRows`` is an in-memory handoff to the writer and must never be
    # embedded in the page payload.  The complete omitted queue is available
    # as a separate JSONL file instead.
    serializable = dict(index)
    serializable.pop("_omittedRows", None)
    output.write_text(json.dumps(serializable, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if jsonl_output is not None:
        write_jsonl(jsonl_output, index.get("rows", []))
    if unmapped_output is not None:
        write_jsonl(
            unmapped_output,
            [
                row
                for row in index.get("_omittedRows", [])
                if isinstance(row, Mapping) and row.get("selection") == "unmapped"
            ],
        )
    if alternatives_output is not None:
        write_jsonl(
            alternatives_output,
            [
                row
                for row in index.get("_omittedRows", [])
                if isinstance(row, Mapping) and row.get("selection") == "alternative"
            ],
        )
    if unmapped_summary_output is not None:
        write_unmapped_summary(unmapped_summary_output, index)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument(
        "--input-dir",
        dest="input_dirs",
        action="append",
        type=Path,
        default=None,
        help="fetch artifact root/source directory (repeatable)",
    )
    parser.add_argument(
        "--input-jsonl",
        dest="input_files",
        action="append",
        type=Path,
        default=None,
        help="candidate JSONL file (repeatable)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="derived public index")
    parser.add_argument("--jsonl-output", type=Path, default=DEFAULT_JSONL_OUTPUT, help="public evidence JSONL")
    parser.add_argument(
        "--unmapped-output",
        type=Path,
        default=DEFAULT_UNMAPPED_OUTPUT,
        help="complete rows without a safe model mapping",
    )
    parser.add_argument(
        "--alternatives-output",
        type=Path,
        default=DEFAULT_ALTERNATIVES_OUTPUT,
        help="mapped rows omitted by the per-group display cap",
    )
    parser.add_argument(
        "--unmapped-summary-output",
        type=Path,
        default=DEFAULT_UNMAPPED_SUMMARY_OUTPUT,
        help="path-safe summary of unresolved source model refs",
    )
    parser.add_argument(
        "--max-per-key",
        type=int,
        default=DEFAULT_MAX_PER_KEY,
        help="maximum selected rows per model×benchmark×metric×source group (0 = all mapped rows)",
    )
    parser.add_argument("--generated-at", help="fixed ISO timestamp for reproducible output")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    input_dirs = [path if path.is_absolute() else root / path for path in (args.input_dirs or [DEFAULT_INPUT])]
    input_files = [path if path.is_absolute() else root / path for path in (args.input_files or [])]
    try:
        index = build_index(
            root,
            input_dirs,
            input_files,
            generated_at=args.generated_at,
            max_per_key=args.max_per_key,
        )
        output = args.output if args.output.is_absolute() else root / args.output
        jsonl_output = args.jsonl_output if args.jsonl_output.is_absolute() else root / args.jsonl_output
        unmapped_output = args.unmapped_output if args.unmapped_output.is_absolute() else root / args.unmapped_output
        alternatives_output = args.alternatives_output if args.alternatives_output.is_absolute() else root / args.alternatives_output
        unmapped_summary_output = args.unmapped_summary_output if args.unmapped_summary_output.is_absolute() else root / args.unmapped_summary_output
        write_index(
            index,
            output.resolve(),
            jsonl_output.resolve(),
            unmapped_output.resolve(),
            alternatives_output.resolve(),
            unmapped_summary_output.resolve(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"build public evidence failed: {exc}", file=sys.stderr)
        return 1
    stats = index["stats"]
    print(
        "Built {path}: rows={rows} reported={reported} candidate={candidate} "
        "mapped={mapped} sources={sources}".format(
            path=output.resolve(),
            rows=stats.get("rows", 0),
            reported=stats.get("reportedRows", 0),
            candidate=stats.get("candidateRows", 0),
            mapped=stats.get("mappedRows", 0),
            sources=stats.get("sources", 0),
        )
    )
    if index["meta"].get("errors"):
        print("Warnings:", *index["meta"]["errors"], sep="\n- ", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
