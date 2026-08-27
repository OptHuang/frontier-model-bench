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
SCHEMA_VERSION = "public-evidence@0.1"
DEFAULT_MAX_PER_KEY = 3


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
        if value:
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
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    changed = True
    while changed:
        changed = False
        for suffix in _PRESENTATION_SUFFIXES:
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
    metric_id = _nonempty(candidate.get("metric")) or "score"
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
    source = catalog.get("sources", {}).get(source_id)
    manifest_url = _nonempty(manifest.get("resolved_url")) or _nonempty(manifest.get("requested_url"))
    source_url = _nonempty(candidate.get("source_url")) or manifest_url or _source_url(source)
    row_url = _metadata_url(metadata)
    status, review_status = _reported_status(candidate, metadata)
    canonical_model_id = _nonempty(candidate.get("canonical_model_id"))
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
        "value": candidate.get("value") if _finite(candidate.get("value")) else None,
        "rawValue": candidate.get("raw_value"),
        "unit": _nonempty(candidate.get("unit")) or "unknown",
        "rank": candidate.get("rank"),
        "status": status,
        "reviewStatus": review_status,
        "verified": False,
        "verificationStatus": "not_reproduced",
        "verification_status": "not_reproduced",
        "evidenceNote": "公开来源报告值；尚未由本项目独立复现/核验。",
        "evidenceLevel": _nonempty(candidate.get("evidence_level")) or "D",
        "comparability": _nonempty(candidate.get("comparability")) or "conditional",
        "subjectType": _nonempty(candidate.get("subject_type")) or _nonempty(protocol.get("subject_type")) or "model",
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
    Keep a small number of alternatives per model × benchmark × metric ×
    source, while preserving every unselected row in ``unmapped.jsonl`` or
    the caller's audit artifact.
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

    if max_per_key < 1:
        raise ValueError("max_per_key must be positive")
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
        take = ordered[:max_per_key] if mapped else []
        for index, item in enumerate(take, 1):
            item["selection"] = "curated"
            item["selectionRank"] = index
            item["alternativesCount"] = len(group)
            item["selectionKey"] = group_id
            item["selectionReason"] = [
                "canonical_model_mapping",
                "bounded_source_variants",
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
    files, discovery_errors = discover_candidate_files(input_dirs, input_files)
    raw_rows, read_errors = read_candidates(files, catalog)
    alias_lookup = build_model_alias_lookup(catalog.get("models", {}))
    for row in raw_rows:
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
    benchmarks = [
        {"id": identifier, "name": catalog.get("benchmarks", {}).get(identifier, {}).get("name"), "rowCount": count}
        for identifier, count in sorted(benchmark_counts.items())
    ]
    models = [
        {"id": identifier, "rowCount": count, "mapped": identifier in catalog.get("models", {})}
        for identifier, count in sorted(model_counts.items())
    ]
    errors = discovery_errors + read_errors
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
            "payloadHashes": payload_hashes,
            "selection": {
                "maxPerModelBenchmarkMetricSource": max_per_key,
                "selectedPolicy": "mapped rows only; highest evidence/current/featured/numeric priority",
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


def write_index(
    index: Mapping[str, Any],
    output: Path,
    jsonl_output: Path | None = None,
    unmapped_output: Path | None = None,
    alternatives_output: Path | None = None,
) -> None:
    """Write the compact index and optional long-form exports."""

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
        "--max-per-key",
        type=int,
        default=DEFAULT_MAX_PER_KEY,
        help="maximum selected rows per model×benchmark×metric×source group",
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
        write_index(
            index,
            output.resolve(),
            jsonl_output.resolve(),
            unmapped_output.resolve(),
            alternatives_output.resolve(),
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
