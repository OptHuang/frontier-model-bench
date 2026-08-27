#!/usr/bin/env python3
"""Turn fetched candidate artifacts into a human-review packet.

The maintenance fetcher intentionally stops at ``candidate`` rows.  This
small companion makes the next step less tedious without pretending that a
machine can approve benchmark facts: it reads ``artifacts/fetch`` (or one or
more explicit artifact directories), checks references and provenance against
the canonical registries, de-duplicates repeated rows, and writes
``review.json`` plus a Markdown queue.  It never writes ``data/catalog`` or
``data/observations/results.jsonl`` and every emitted decision starts as
``pending``.

Examples
--------
    python3 scripts/review_candidates.py
    python3 scripts/review_candidates.py --input-dir /tmp/fmb-fetch \
        --output-dir /tmp/fmb-review --limit 30

The JSON packet is deliberately a *review scaffold*, not an importer.  A
maintainer must verify the source locator, release/version, metric, protocol,
subject and evidence before manually appending an approved observation in a
small PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

try:  # ``python scripts/review_candidates.py``
    from adapters.base import utc_now
except ImportError:  # ``python -m scripts.review_candidates``
    from scripts.adapters.base import utc_now


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "artifacts" / "fetch"
DEFAULT_OUTPUT = ROOT / "artifacts" / "review"
SCHEMA_VERSION = "candidate-review@0.1"
DECISIONS = ("pending", "accept", "reject", "defer")
EVIDENCE_LEVELS = {"A", "B", "C", "D"}


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry(path: Path, key: str) -> list[Mapping[str, Any]]:
    """Read either a bare array or the keyed registry shape."""

    try:
        payload = _json_load(path)
    except (OSError, json.JSONDecodeError):
        return []
    value = payload.get(key) if isinstance(payload, Mapping) else payload
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:20]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def discover_candidate_files(input_dirs: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """Find source-root candidate files without walking immutable snapshots.

    ``fetch.py`` keeps a convenient ``<source>/candidates.jsonl`` alongside
    ``<source>/snapshots/...``.  Reading only the former avoids counting the
    same row once per historical snapshot.
    """

    files: list[Path] = []
    errors: list[str] = []
    seen: set[Path] = set()
    for raw in input_dirs:
        path = raw.expanduser().resolve()
        if not path.exists():
            errors.append(f"input not found: {path}")
            continue
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            direct = path / "candidates.jsonl"
            candidates = [direct] if direct.is_file() else sorted(path.glob("*/candidates.jsonl"))
        else:
            errors.append(f"input is not a regular file/directory: {path}")
            continue
        for candidate_file in candidates:
            resolved = candidate_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return sorted(files), errors


def _manifest_context(path: Path) -> dict[str, Any]:
    """Return small provenance fields from a sibling source manifest."""

    manifest_path = path.parent / "manifest.json"
    try:
        manifest = _json_load(manifest_path)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(manifest, Mapping):
        return {}
    keys = (
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
    )
    return {key: manifest.get(key) for key in keys if key in manifest}


def read_candidate_groups(
    files: Sequence[Path], root: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    """Read candidate JSONL files and collapse exact duplicate IDs.

    A group retains every artifact location so a reviewer can see whether a
    row was repeated by multiple source exports.  Rows lacking a
    ``candidate_id`` receive a deterministic local fingerprint and are still
    included rather than silently discarded.
    """

    groups: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in files:
        manifest = _manifest_context(path)
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
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{line_number}: invalid JSON: {exc.msg}")
                    continue
                if not isinstance(row, Mapping):
                    errors.append(f"{path}:{line_number}: candidate must be an object")
                    continue
                candidate = dict(row)
                identifier = candidate.get("candidate_id")
                key = str(identifier).strip() if _nonempty(identifier) else f"anonymous-{_digest(candidate)}"
                location = {
                    "path": _relative_or_absolute(path, root),
                    "line": line_number,
                    "manifest": manifest,
                }
                group = groups.setdefault(
                    key,
                    {
                        "candidate": candidate,
                        "candidate_key": key,
                        "locations": [],
                        "row_digests": set(),
                    },
                )
                group["locations"].append(location)
                group["row_digests"].add(_digest(candidate))
    result: list[dict[str, Any]] = []
    for group in groups.values():
        # ``set`` is an internal convenience and must not leak into JSON.
        result.append(
            {
                "candidate": group["candidate"],
                "candidate_key": group["candidate_key"],
                "locations": group["locations"],
                "duplicate_count": max(0, len(group["locations"]) - 1),
                "duplicate_conflict": len(group["row_digests"]) > 1,
            }
        )
    return result, errors


def _load_catalog_context(root: Path) -> dict[str, Any]:
    models = _registry(root / "data" / "catalog" / "models.json", "models")
    benchmarks = _registry(root / "data" / "catalog" / "benchmarks.json", "benchmarks")
    sources = _registry(root / "data" / "catalog" / "sources.json", "sources")
    harnesses = _registry(root / "data" / "catalog" / "harnesses.json", "harnesses")
    aliases: dict[str, list[str]] = defaultdict(list)
    for model in models:
        model_id = model.get("id")
        if not _nonempty(model_id):
            continue
        values: list[Any] = [model_id, model.get("name")]
        raw_aliases = model.get("aliases")
        if isinstance(raw_aliases, list):
            for alias in raw_aliases:
                if isinstance(alias, Mapping):
                    values.extend((alias.get("value"), alias.get("name")))
                else:
                    values.append(alias)
        for value in values:
            if _nonempty(value):
                aliases[str(value).strip().casefold()].append(str(model_id))
    benchmark_map = {
        str(item.get("id")): item for item in benchmarks if _nonempty(item.get("id"))
    }
    source_map = {str(item.get("id")): item for item in sources if _nonempty(item.get("id"))}
    harness_map = {str(item.get("id")): item for item in harnesses if _nonempty(item.get("id"))}
    metric_map: dict[tuple[str, str], Mapping[str, Any]] = {}
    version_map: dict[str, set[str]] = {}
    for benchmark_id, benchmark in benchmark_map.items():
        metrics = benchmark.get("metrics")
        if isinstance(metrics, list):
            for metric in metrics:
                if isinstance(metric, Mapping) and _nonempty(metric.get("id")):
                    metric_map[(benchmark_id, str(metric["id"]))] = metric
        versions = benchmark.get("versions")
        version_map[benchmark_id] = {
            str(item.get("id"))
            for item in (versions if isinstance(versions, list) else [])
            if isinstance(item, Mapping) and _nonempty(item.get("id"))
        }
    return {
        "models": {str(item.get("id")): item for item in models if _nonempty(item.get("id"))},
        "benchmarks": benchmark_map,
        "sources": source_map,
        "harnesses": harness_map,
        "aliases": dict(aliases),
        "metrics": metric_map,
        "versions": version_map,
    }


def _protocol_for(row: Mapping[str, Any]) -> Mapping[str, Any]:
    protocol = row.get("protocol")
    return protocol if isinstance(protocol, Mapping) else {}


def _subject_type(row: Mapping[str, Any], benchmark: Mapping[str, Any] | None) -> str | None:
    protocol = _protocol_for(row)
    value = protocol.get("subject_type") or row.get("subject_type")
    if not value:
        metadata = row.get("metadata")
        if isinstance(metadata, Mapping):
            value = metadata.get("subject_type")
    if value in {"model", "system"}:
        return str(value)
    category = str((benchmark or {}).get("category") or "").casefold()
    flags = {str(item).casefold() for item in (row.get("quality_flags") or []) if item is not None}
    if "agent_system_score" in flags or "system" in category or "agent" in category:
        return "system"
    return None


def assess_candidate(
    group: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach machine checks and conservative review guidance to one row."""

    row = group.get("candidate") if isinstance(group.get("candidate"), Mapping) else {}
    row = dict(row)
    model_ref = row.get("model_ref")
    model_id = row.get("canonical_model_id") if _nonempty(row.get("canonical_model_id")) else None
    mapping_status = str(row.get("mapping_status") or "unmatched")
    alias_matches: list[str] = []
    if model_id not in context["models"] and _nonempty(model_ref):
        alias_matches = sorted(set(context["aliases"].get(str(model_ref).strip().casefold(), [])))
        if len(alias_matches) == 1:
            model_id = alias_matches[0]
            mapping_status = "exact_alias_available"
        elif len(alias_matches) > 1:
            mapping_status = "ambiguous_alias"
    if model_id not in context["models"]:
        model_id = None

    benchmark_ref = str(row.get("benchmark_ref") or "").strip()
    benchmark = context["benchmarks"].get(benchmark_ref)
    metric = str(row.get("metric") or "").strip()
    protocol = _protocol_for(row)
    subject_type = _subject_type(row, benchmark)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    source_id = str(row.get("source_id") or "").strip()
    source_url = row.get("source_url")
    locator = row.get("source_locator")
    evidence = row.get("evidence_level")
    value = row.get("value")
    harness = protocol.get("harness") or row.get("harness_id")
    version_hints = [
        row.get("benchmark_version_id"),
        row.get("version"),
        protocol.get("benchmark_version"),
        protocol.get("version"),
        protocol.get("release"),
        metadata.get("benchmark_version"),
        metadata.get("release"),
    ]
    version_context = next((str(item) for item in version_hints if _nonempty(item)), None)
    observed_at = row.get("observed_at") or row.get("published_at") or metadata.get("release_date")

    checks: dict[str, bool] = {
        "model_mapping": model_id in context["models"],
        "benchmark_ref": benchmark is not None,
        "metric_ref": bool(benchmark and (benchmark_ref, metric) in context["metrics"]),
        "value_numeric_or_explicit_missing": value is None or _finite_number(value),
        "unit_present": _nonempty(row.get("unit")),
        "source_ref": source_id in context["sources"],
        "source_url": _nonempty(source_url)
        and urlparse(str(source_url)).scheme in {"http", "https", "file"},
        "source_locator": _nonempty(locator),
        "evidence_level": evidence in EVIDENCE_LEVELS,
        "protocol_present": bool(protocol),
        "observed_date": _nonempty(observed_at),
        "version_context": version_context is not None,
        "harness_context": (subject_type != "system") or bool(harness),
        "harness_registered": (not harness) or (str(harness) in context["harnesses"]),
    }

    actions: list[str] = []
    if not checks["model_mapping"]:
        if mapping_status == "ambiguous_alias":
            actions.append("在多个 canonical model release 中选择唯一对象；不要按模糊名称猜测。")
        elif alias_matches:
            actions.append(f"确认 exact alias 是否确实对应 `{alias_matches[0]}`，再手工写入 canonical model_id。")
        else:
            actions.append("确认 model_ref 对应的具体 release/endpoint，并先登记 canonical model。")
    if not checks["benchmark_ref"]:
        actions.append("确认 benchmark id、版本和 split/subset；未知 benchmark 不能直接晋升。")
    elif not checks["metric_ref"]:
        actions.append("核对 metric 是否是该 benchmark 已登记的 metric。")
    if value is None:
        actions.append("来源没有数值：保留为缺失/不可用语义，不要填 0。")
    elif not checks["value_numeric_or_explicit_missing"]:
        actions.append("核对原始值；当前值不是有限数字。")
    if not checks["unit_present"]:
        actions.append("补齐 unit，不能把 Elo、比例或秒数默认为百分比。")
    if not checks["source_ref"]:
        actions.append("登记或确认 source_id，并保留来源许可证与发布者。")
    if not checks["source_url"] or not checks["source_locator"]:
        actions.append("打开 source URL 并确认可复核的表格/行/列 locator。")
    if not checks["evidence_level"]:
        actions.append("按来源性质选择 evidence level A/B/C/D。")
    if not checks["protocol_present"]:
        actions.append("补齐 shots、tools、reasoning、judge、split 等 protocol 字段。")
    if subject_type == "system" and not checks["harness_context"]:
        actions.append("这是 system/agent 结果：补齐 harness、scaffold 或 agent 身份。")
    if not checks["harness_registered"]:
        actions.append("确认 source 中的 harness 名称，必要时先登记 harness；不要隐式改成 model-only。")
    if not checks["version_context"]:
        actions.append("确认 benchmark release/version；滚动榜单必须保留快照日期。")
    if not checks["observed_date"]:
        actions.append("补齐 observed_at 或 published_at；retrieved_at 不能替代评测日期。")
    if group.get("duplicate_conflict"):
        actions.append("同一 candidate_id 对应不同内容；先检查 parser/source snapshot 冲突。")

    blocking = {
        "model_mapping",
        "benchmark_ref",
        "metric_ref",
        "value_numeric_or_explicit_missing",
        "unit_present",
        "source_ref",
        "source_url",
        "source_locator",
        "evidence_level",
        "protocol_present",
        "harness_context",
    }
    blocking_failures = [name for name in blocking if not checks[name]]
    if value is None:
        review_status = "missing-value"
        priority = "low"
    elif not checks["model_mapping"] or not checks["benchmark_ref"]:
        review_status = "needs-mapping"
        priority = "medium"
    elif blocking_failures:
        review_status = "needs-review"
        priority = "medium"
    else:
        review_status = "reviewable"
        priority = "high"
    if group.get("duplicate_conflict"):
        review_status = "needs-review"
        priority = "medium"

    candidate_id = row.get("candidate_id") or group.get("candidate_key")
    return {
        "review_id": f"review-{_digest({"candidate_id": candidate_id, "row": row})}",
        "candidate_id": candidate_id,
        "decision": "pending",
        "review_status": review_status,
        "priority": priority,
        "canonical_model_id_suggestion": model_id,
        "mapping_status": mapping_status,
        "alias_matches": alias_matches,
        "subject_type": subject_type,
        "checks": checks,
        "blocking_failures": sorted(blocking_failures),
        "required_actions": actions,
        "duplicate_count": int(group.get("duplicate_count") or 0),
        "duplicate_conflict": bool(group.get("duplicate_conflict")),
        "locations": list(group.get("locations") or []),
        "candidate": row,
    }


def _sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    priorities = {"high": 0, "medium": 1, "low": 2}
    statuses = {"reviewable": 0, "needs-review": 1, "needs-mapping": 2, "missing-value": 3}
    return (
        priorities.get(str(item.get("priority")), 9),
        statuses.get(str(item.get("review_status")), 9),
        str(item.get("candidate", {}).get("source_id", "")),
        str(item.get("candidate", {}).get("model_ref", "")),
        str(item.get("candidate", {}).get("benchmark_ref", "")),
        str(item.get("candidate_id", "")),
    )


def build_review(
    root: Path,
    input_dirs: Sequence[Path],
    *,
    generated_at: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a JSON-serializable review packet without writing any files."""

    root = root.resolve()
    files, discovery_errors = discover_candidate_files(input_dirs)
    groups, read_errors = read_candidate_groups(files, root)
    context = _load_catalog_context(root)
    assessed = sorted((assess_candidate(group, context) for group in groups), key=_sort_key)
    if limit < 0:
        raise ValueError("limit must be >= 0 (0 means all candidates)")
    selected = assessed if limit == 0 else assessed[:limit]
    counts = Counter(str(item["review_status"]) for item in assessed)
    priority_counts = Counter(str(item["priority"]) for item in assessed)
    source_counts = Counter(str(item["candidate"].get("source_id") or "unknown") for item in assessed)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now(),
        "candidate_only": True,
        "approved_mutation": False,
        "decisions": list(DECISIONS),
        # Keep packets portable (and avoid leaking a maintainer's local
        # username/path when an artifact is pasted into an issue).  Paths
        # outside the repository remain absolute so they are still useful for
        # a local one-off review.
        "root": ".",
        "input_dirs": [_relative_or_absolute(path, root) for path in input_dirs],
        "candidate_files": [_relative_or_absolute(path, root) for path in files],
        "summary": {
            "candidate_files": len(files),
            "unique_candidates": len(assessed),
            "selected_candidates": len(selected),
            "omitted_candidates": max(0, len(assessed) - len(selected)),
            "review_status": dict(sorted(counts.items())),
            "priority": dict(sorted(priority_counts.items())),
            "sources": dict(sorted(source_counts.items())),
            "duplicate_groups": sum(1 for item in assessed if item.get("duplicate_count")),
            "duplicate_conflicts": sum(1 for item in assessed if item.get("duplicate_conflict")),
        },
        "errors": discovery_errors + read_errors,
        "candidates": selected,
        "policy": {
            "next_step": "人工核对 candidate 的来源、版本、protocol、subject 和 evidence，然后在小 PR 中追加 approved observation。",
            "forbidden": [
                "不要把 candidate.jsonl 直接复制到 data/observations/results.jsonl。",
                "不要把 missing、unknown 或破折号转换成 0。",
                "不要因为 exact alias suggestion 就跳过 release/protocol 审阅。",
            ],
        },
    }


def _md(value: Any) -> str:
    text = "—" if value is None or value == "" else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _display_value(row: Mapping[str, Any]) -> str:
    value = row.get("value")
    if value is None:
        return "—"
    unit = row.get("unit")
    return f"{value} {unit}" if unit else str(value)


def render_markdown(packet: Mapping[str, Any]) -> str:
    summary = packet.get("summary") if isinstance(packet.get("summary"), Mapping) else {}
    lines = [
        "# Candidate review packet",
        "",
        "> This is a candidate-only review scaffold. It does not approve, merge, or modify canonical observations.",
        "",
        f"- generated: `{_md(packet.get('generated_at'))}`",
        f"- unique candidates: **{summary.get('unique_candidates', 0)}**",
        f"- shown: **{summary.get('selected_candidates', 0)}**",
        f"- omitted by limit: **{summary.get('omitted_candidates', 0)}**",
        f"- duplicate groups: **{summary.get('duplicate_groups', 0)}** (conflicts: **{summary.get('duplicate_conflicts', 0)}**)",
        "",
        "## Review queue",
        "",
        "| priority | status | candidate | model_ref | benchmark | value | mapping | source |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in packet.get("candidates", []):
        if not isinstance(item, Mapping):
            continue
        row = item.get("candidate") if isinstance(item.get("candidate"), Mapping) else {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(item.get("priority")),
                    _md(item.get("review_status")),
                    f"`{_md(item.get('candidate_id'))}`",
                    _md(row.get("model_ref")),
                    _md(row.get("benchmark_ref")),
                    _md(_display_value(row)),
                    _md(item.get("mapping_status")),
                    _md(row.get("source_id")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Candidate details", ""])
    for item in packet.get("candidates", []):
        if not isinstance(item, Mapping):
            continue
        row = item.get("candidate") if isinstance(item.get("candidate"), Mapping) else {}
        lines.extend(
            [
                f"### `{_md(item.get('candidate_id'))}`",
                "",
                f"- decision: `{_md(item.get('decision'))}` (edit only after human review)",
                f"- status/priority: `{_md(item.get('review_status'))}` / `{_md(item.get('priority'))}`",
                f"- model: `{_md(row.get('model_ref'))}` → suggestion `{_md(item.get('canonical_model_id_suggestion'))}`",
                f"- benchmark/metric: `{_md(row.get('benchmark_ref'))}` / `{_md(row.get('metric'))}` ({_md(row.get('unit'))})",
                f"- value/raw: `{_md(row.get('value'))}` / `{_md(row.get('raw_value'))}`",
                f"- subject: `{_md(item.get('subject_type'))}`; protocol: `{_md(json.dumps(row.get('protocol') or {}, ensure_ascii=False, sort_keys=True))}`",
                f"- source: [{_md(row.get('source_id'))}]({_md(row.get('source_url'))}); locator: `{_md(row.get('source_locator'))}`",
                f"- evidence/comparability: `{_md(row.get('evidence_level'))}` / `{_md(row.get('comparability'))}`",
            ]
        )
        actions = item.get("required_actions") or []
        if actions:
            lines.append("- required actions:")
            lines.extend(f"  - {action}" for action in actions)
        else:
            lines.append("- required actions: none detected by machine checks; human evidence review is still required.")
        lines.append("")
    lines.extend(
        [
            "## Promotion guardrail",
            "",
            "For accepted rows, manually map the release and benchmark version, verify protocol/harness and evidence, then append a canonical observation in a small PR. Run `python3 scripts/build_derived.py` and `python3 scripts/validate_data.py --strict`; this helper never performs that write.",
            "",
        ]
    )
    errors = packet.get("errors") or []
    if errors:
        lines.extend(["## Input warnings", "", *[f"- {_md(error)}" for error in errors], ""])
    return "\n".join(lines)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def ensure_safe_output(root: Path, output_dir: Path, input_dirs: Sequence[Path]) -> Path:
    """Reject output locations that could overwrite canonical data or inputs."""

    output = output_dir.expanduser().resolve()
    canonical_data = root.resolve() / "data"
    if _is_under(output, canonical_data):
        raise ValueError("review output must not be inside canonical data/")
    for input_dir in input_dirs:
        candidate = input_dir.expanduser().resolve()
        if output == candidate or _is_under(output, candidate):
            raise ValueError("review output must be separate from candidate input artifacts")
    return output


def write_outputs(output_dir: Path, packet: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "review.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "review.md").write_text(render_markdown(packet), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument(
        "--input-dir",
        "--input",
        dest="input_dirs",
        action="append",
        type=Path,
        help="fetch artifact directory or candidates.jsonl (repeatable)",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="number of rows in the packet (0 means all; summary always counts all)",
    )
    parser.add_argument("--generated-at", help="fixed ISO timestamp for reproducible packets")
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="return non-zero when no candidate JSONL files/rows are found",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    input_dirs = args.input_dirs or [DEFAULT_INPUT]
    if args.limit < 0:
        print("review_candidates: --limit must be >= 0", file=sys.stderr)
        return 2
    try:
        output_dir = ensure_safe_output(root, args.output_dir, input_dirs)
        packet = build_review(
            root,
            input_dirs,
            generated_at=args.generated_at,
            limit=args.limit,
        )
        write_outputs(output_dir, packet)
    except (OSError, ValueError) as exc:
        print(f"review_candidates: {exc}", file=sys.stderr)
        return 2
    unique = int(packet["summary"]["unique_candidates"])
    if args.fail_on_empty and unique == 0:
        print("review_candidates: no candidates found", file=sys.stderr)
        return 1
    print(
        "review_candidates: "
        f"files={packet['summary']['candidate_files']} "
        f"unique={unique} shown={packet['summary']['selected_candidates']} "
        f"output={output_dir} candidate_only=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
