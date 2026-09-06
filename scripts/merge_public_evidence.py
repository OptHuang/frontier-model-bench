#!/usr/bin/env python3
"""Merge normalized public history with new adapter results without data loss.

Historical public/evidence and unmapped rows must both be supplied. Input
files are never modified. Same-id incoming rows are treated as corrections;
changed prior values remain inspectable in previousReports. Distinct ids are
retained even when their values happen to be equal.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_public_evidence as public


def read_normalized_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            payload = json.loads(text)
            incoming = payload.get("rows") if isinstance(payload, dict) else payload
            if not isinstance(incoming, list):
                raise ValueError(f"{path.name}: expected normalized rows")
        else:
            incoming = [json.loads(line) for line in text.splitlines() if line.strip()]
        for index, row in enumerate(incoming, 1):
            if not isinstance(row, dict) or not all(row.get(key) for key in ("id", "sourceId", "modelRef", "benchmarkId", "metricId")):
                raise ValueError(f"{path.name}:{index}: incomplete normalized row")
            if row.get("verified") is not False or row.get("status") not in {"reported", "candidate"}:
                raise ValueError(f"{path.name}:{index}: expected unverified public evidence")
            rows.append(row)
    return rows


def _instant(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("_", "-").replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except ValueError:
        return None


def _clean_display_dates(row: dict[str, Any], now: datetime) -> None:
    flags = set(row.get("qualityFlags") or [])
    protocol = row.get("protocol") or {}
    metadata = (row.get("sourceRow") or {}).get("metadata") or {}
    table = protocol.get("release_date") or metadata.get("release_date")
    observed = row.get("observedAt")
    if row.get("sourceId") == "src-epoch-benchmark-hub" and observed and metadata.get("release_date") and str(observed) == str(metadata["release_date"]):
        row.setdefault("sourceReportedDates", {})["observedAt"] = observed
        row["observedAt"] = None
        flags.add("model_release_is_not_evaluation_date")
    if row.get("sourceId") == "livebench-official" and observed and table and str(observed).replace("_", "-") == str(table).replace("_", "-"):
        row.setdefault("sourceReportedDates", {})["observedAt"] = observed
        row["observedAt"] = None
        flags.add("table_version_is_not_evaluation_date")
    for field in ("observedAt", "publishedAt"):
        original = row.get(field)
        parsed = _instant(original)
        if original and (parsed is None or parsed > now):
            row.setdefault("sourceReportedDates", {})[field] = original
            row[field] = None
            flags.add("invalid_source_date" if parsed is None else "future_source_date")
    if row.get("sourceId") == "livebench-official" and not row.get("observedAt"):
        flags.add("evaluation_date_not_reported")
    row["qualityFlags"] = sorted(flags)


def _receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(row.get(key)) for key in (
        "id", "value", "rawValue", "unit", "sourceLocator", "protocol",
        "observedAt", "publishedAt", "retrievedAt", "payloadSha256", "sourceReportedDates",
    )}


def _locations(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = list(row.get("snapshotLocations") or [])
    source = row.get("sourceRow") or {}
    result.append({"artifact": source.get("artifact"), "line": source.get("line"),
                   "retrievedAt": row.get("retrievedAt"), "payloadSha256": row.get("payloadSha256")})
    return result


def _unique(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return list({json.dumps(item, sort_keys=True, ensure_ascii=False): dict(item) for item in items}.values())


def merge_normalized_rows(
    baseline: Sequence[Mapping[str, Any]], incoming: Sequence[Mapping[str, Any]],
    *, generated_at: str,
) -> list[dict[str, Any]]:
    now = _instant(generated_at)
    if now is None:
        raise ValueError("generated_at must be an ISO date/time")
    merged: dict[str, dict[str, Any]] = {}
    for original in (*baseline, *incoming):
        row = copy.deepcopy(dict(original))
        identifier = row.get("id")
        if not identifier:
            raise ValueError("cannot preserve normalized row without id")
        _clean_display_dates(row, now)
        old = merged.get(identifier)
        if old is not None:
            # Input order is deliberate: the newly parsed layer wins exact
            # id collisions, including explicit parser corrections.
            history = list(old.get("previousReports") or []) + list(row.get("previousReports") or [])
            if any(old.get(k) != row.get(k) for k in ("value", "rawValue", "unit", "protocol", "observedAt", "publishedAt")):
                history.append(_receipt(old))
            if history:
                row["previousReports"] = _unique(history)
            row["snapshotLocations"] = _unique(_locations(old) + _locations(row))
        else:
            row["snapshotLocations"] = _unique(_locations(row))
        row["snapshotCount"] = len(row["snapshotLocations"])
        merged[identifier] = row
    # Preserve distinct ids while retaining the generator's conflict flags.
    groups = defaultdict(list)
    for row in merged.values():
        groups[public._digest(public._comparison_key(row), length=32)].append(row)
    for group_id, group in groups.items():
        if len({json.dumps((r.get("value"), r.get("rawValue"))) for r in group}) > 1:
            for row in group:
                row["conflictGroup"] = "conflict-" + group_id
                row["qualityFlags"] = sorted(set(row.get("qualityFlags") or []) | {"reported_value_conflict"})
    return sorted(merged.values(), key=lambda r: str(r["id"]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=public.ROOT)
    parser.add_argument("--baseline", action="append", type=Path, required=True,
                        help="normalized public.json/evidence.jsonl/unmapped.jsonl (repeatable)")
    parser.add_argument("--input-dir", action="append", type=Path, default=[])
    parser.add_argument("--input-jsonl", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="explicit destination for all five generated outputs")
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    paths = [p if p.is_absolute() else root / p for p in args.baseline]
    output = args.output_dir.resolve()
    outputs = {output / name for name in ("public.json", "public-evidence.jsonl", "public-unmapped.jsonl", "public-alternatives.jsonl", "public-unmapped-summary.json")}
    if any(p.resolve() in outputs for p in paths):
        raise ValueError("output files must not overwrite baseline inputs")
    baseline = read_normalized_rows(paths)
    index = public.build_index(
        root, args.input_dir, args.input_jsonl,
        generated_at=args.generated_at or public.utc_now(),
        max_per_key=0, baseline_rows=baseline,
    )
    if index["meta"].get("errors"):
        raise ValueError("refusing incomplete merge: " + "; ".join(index["meta"]["errors"]))
    all_rows = index["rows"] + index["_omittedRows"]
    missing = {r["id"] for r in baseline} - {r["id"] for r in all_rows}
    if missing:
        raise ValueError(f"refusing merge that loses {len(missing)} historical ids")
    index["meta"]["baselineFiles"] = [p.name for p in paths]
    index["meta"]["baselineUniqueRows"] = len({r["id"] for r in baseline})
    index["meta"]["mergePolicy"] = "preserve historical ids; incoming same-id corrections keep prior receipts; source dates do not replace retrieval time"
    output = args.output_dir.resolve()
    public.write_index(index, output / "public.json", output / "public-evidence.jsonl",
                       output / "public-unmapped.jsonl", output / "public-alternatives.jsonl",
                       output / "public-unmapped-summary.json")
    print(json.dumps({"output": str(output), "historicalIdsRetained": len({r['id'] for r in baseline}),
                      "mappedRows": len(index['rows']), "unmappedRows": len(index['_omittedRows']),
                      "generatedAt": index['meta']['generatedAt']}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
