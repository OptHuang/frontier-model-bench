#!/usr/bin/env python3
"""Fetch public leaderboard payloads into an auditable candidate artifact.

This command is deliberately *not* an importer.  It never edits the
canonical catalog or ``data/observations/results.jsonl``.  A run writes a
manifest, source candidates, and a summary under an artifact directory; a
maintainer reviews those files and makes a small PR for any approved facts.

Examples
--------
    python3 scripts/fetch.py list
    python3 scripts/fetch.py fetch --sources hf-swebench-verified,swebench-official
    python3 scripts/fetch.py check --dry-run

The adapters use only public, bounded HTTP requests.  ``--dry-run`` means no
raw payload is persisted (the response is still parsed in memory); it is the
recommended mode for scheduled jobs.  The disabled Arena adapter is included
in ``list`` and can be selected for an explicit metadata-only audit, but it
does not scrape the interactive site or emit scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # ``python scripts/fetch.py``
    from adapters import all_adapters
    from adapters.base import AdapterRun, PARSER_VERSION, utc_now
    from adapters.http import HttpClient
except ImportError:  # ``python -m scripts.fetch``
    from scripts.adapters import all_adapters
    from scripts.adapters.base import AdapterRun, PARSER_VERSION, utc_now
    from scripts.adapters.http import HttpClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "fetch"


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def snapshot_tag(run: AdapterRun) -> str:
    """Return a filesystem-safe, content-addressed snapshot label."""

    stamp = re.sub(r"[^0-9A-Za-z]+", "", run.retrieved_at) or "unknown-time"
    digest = run.payload_sha256 or hashlib.sha256(
        f"{run.source_id}|{run.retrieved_at}".encode("utf-8")
    ).hexdigest()
    return f"{stamp}-{digest[:16]}"


def compact_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    """Keep only response headers useful for provenance and cache checks."""

    wanted = {
        "etag",
        "last-modified",
        "content-type",
        "content-length",
        "cache-control",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in wanted
    }


def source_ids(value: str | None, available: Mapping[str, Any]) -> list[str]:
    if not value or value.strip().lower() in {"all", "*"}:
        return list(sorted(available))
    requested: list[str] = []
    for item in value.split(","):
        source_id = item.strip()
        if not source_id:
            continue
        if source_id not in available:
            choices = ", ".join(sorted(available))
            raise ValueError(f"unknown adapter '{source_id}'; choose from: {choices}")
        if source_id not in requested:
            requested.append(source_id)
    return requested


def load_model_aliases(root: Path) -> dict[str, list[str]]:
    """Build a conservative exact-alias map for candidate annotation.

    This is only an annotation step.  Fuzzy matching is intentionally not
    attempted because a provider alias, preview release, and speed tier can
    look nearly identical while representing different evaluation subjects.
    """

    path = root / "data" / "catalog" / "models.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = payload.get("models", []) if isinstance(payload, Mapping) else payload
    result: dict[str, list[str]] = {}
    if not isinstance(records, list):
        return result
    for model in records:
        if not isinstance(model, Mapping) or not isinstance(model.get("id"), str):
            continue
        model_id = str(model["id"])
        values: list[Any] = [model_id, model.get("name")]
        aliases = model.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, Mapping):
                    # Catalog aliases may carry source-specific provenance;
                    # only the human-readable value participates in exact
                    # matching, never the source id itself.
                    values.append(alias.get("value"))
                    values.append(alias.get("name"))
                else:
                    values.append(alias)
        for value in values:
            if isinstance(value, str) and value.strip():
                result.setdefault(value.strip().casefold(), []).append(model_id)
    return result


def annotate_model_mapping(
    candidates: list[dict[str, Any]], aliases: Mapping[str, list[str]]
) -> None:
    """Annotate exact matches while retaining the source's original name."""

    for candidate in candidates:
        model_ref = candidate.get("model_ref")
        if not isinstance(model_ref, str) or not model_ref.strip():
            continue
        matches = sorted(set(aliases.get(model_ref.strip().casefold(), [])))
        if len(matches) == 1:
            candidate["canonical_model_id"] = matches[0]
            candidate["mapping_status"] = "exact_alias"
        elif len(matches) > 1:
            candidate["mapping_status"] = "ambiguous_alias"
            candidate["mapping_candidates"] = matches


def run_manifest(
    run: AdapterRun,
    *,
    saved_payload: str | None,
    truncated: bool,
    written_candidate_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": "source-fetch-manifest@0.1",
        "source_id": run.source_id,
        "requested_url": run.requested_url,
        "resolved_url": run.resolved_url,
        "retrieved_at": run.retrieved_at,
        "http_status": run.http_status,
        "headers": compact_headers(run.headers),
        "payload_sha256": run.payload_sha256,
        "payload_bytes": len(run.payload),
        "parser_version": run.parser_version or PARSER_VERSION,
        "not_modified": run.not_modified,
        "metadata": run.metadata,
        "warnings": run.warnings,
        "errors": run.errors,
        "candidate_count": len(run.candidates),
        "written_candidate_count": written_candidate_count,
        "candidates_truncated": truncated,
        "saved_payload": saved_payload,
    }


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_source_artifact(
    output_dir: Path,
    run: AdapterRun,
    *,
    dry_run: bool,
    save_payload: bool,
    max_candidates: int,
) -> dict[str, Any]:
    source_dir = output_dir / run.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    candidates = run.candidates
    truncated = len(candidates) > max_candidates
    if truncated:
        candidates = candidates[:max_candidates]
    saved_payload: str | None = None
    # Payload storage is opt-in.  Most leaderboard licenses permit linking
    # but not redistributing a complete export; the default artifact contains
    # the hash and parsed candidate rows only.
    if save_payload and not dry_run and run.payload:
        digest = run.payload_sha256 or "no-hash"
        # Content-address the optional payload so a repeated local run cannot
        # overwrite an earlier snapshot.  Identical bytes may be reused; a
        # changed response always receives a new immutable filename.
        payload_path = source_dir / f"payload-{digest[:16]}.bin"
        if not payload_path.exists():
            payload_path.write_bytes(run.payload)
        saved_payload = str(payload_path.relative_to(output_dir))
    write_jsonl(source_dir / "candidates.jsonl", candidates)
    manifest = run_manifest(
        run,
        saved_payload=saved_payload,
        truncated=truncated,
        written_candidate_count=len(candidates),
    )
    # Keep a per-run candidate/manifest copy as an immutable audit trail even
    # though the two files at the source root are convenient "latest" views.
    snapshot_dir = source_dir / "snapshots" / snapshot_tag(run)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(snapshot_dir / "candidates.jsonl", candidates)
    manifest["snapshot_dir"] = str(snapshot_dir.relative_to(output_dir))
    json_dump(snapshot_dir / "manifest.json", manifest)
    json_dump(source_dir / "manifest.json", manifest)
    return manifest


def list_adapters(as_json: bool = False) -> int:
    adapters = all_adapters()
    rows = []
    for source_id in sorted(adapters):
        spec = getattr(adapters[source_id], "spec", None)
        rows.append(
            {
                "id": source_id,
                "label": getattr(spec, "label", source_id),
                "kind": getattr(spec, "kind", None),
                "url": getattr(spec, "url", None),
                "cadence": getattr(spec, "cadence", None),
                "enabled": bool(getattr(spec, "enabled", True)),
                "notes": getattr(spec, "notes", None),
            }
        )
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("id\tenabled\tcadence\tkind\turl")
        for row in rows:
            print(
                "\t".join(
                    [
                        row["id"],
                        "yes" if row["enabled"] else "no",
                        str(row["cadence"] or ""),
                        str(row["kind"] or ""),
                        str(row["url"] or ""),
                    ]
                )
            )
    return 0


def fetch_adapters(args: argparse.Namespace) -> int:
    adapters = all_adapters()
    selected = source_ids(args.sources, adapters)
    if not selected:
        print("fetch: at least one adapter must be selected", file=sys.stderr)
        return 2
    if args.input_path and len(selected) != 1:
        print("fetch: --input/--payload requires exactly one adapter", file=sys.stderr)
        return 2
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = args.root / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = args.retrieved_at or utc_now()
    client = HttpClient(timeout=args.timeout, max_bytes=args.max_bytes)
    aliases = load_model_aliases(args.root.resolve())
    manifests: list[dict[str, Any]] = []
    for source_id in selected:
        adapter = adapters[source_id]
        try:
            if args.input_path:
                input_path = args.input_path
                if not input_path.is_absolute():
                    input_path = args.root / input_path
                payload = input_path.read_bytes()
                run = AdapterRun(
                    source_id=source_id,
                    requested_url=input_path.resolve().as_uri(),
                    resolved_url=input_path.resolve().as_uri(),
                    retrieved_at=retrieved_at,
                    http_status=200,
                    headers={"content-type": "application/octet-stream"},
                    payload=payload,
                    metadata={"local_input": str(input_path)},
                    parser_version=getattr(adapter.spec, "parser_version", PARSER_VERSION),
                )
                run.candidates = adapter.parse_payload(payload, run)
            else:
                run = adapter.fetch(client, retrieved_at=retrieved_at)
        except Exception as exc:  # one broken source must not hide others
            spec = getattr(adapter, "spec", None)
            run = AdapterRun(
                source_id=source_id,
                requested_url=str(getattr(spec, "url", "")),
                resolved_url=str(getattr(spec, "url", "")),
                retrieved_at=retrieved_at,
                http_status=None,
                errors=[f"adapter exception: {type(exc).__name__}: {exc}"],
                parser_version=str(getattr(spec, "parser_version", PARSER_VERSION)),
            )
        annotate_model_mapping(run.candidates, aliases)
        manifests.append(
            write_source_artifact(
                output_dir,
                run,
                dry_run=bool(args.dry_run),
                save_payload=bool(args.save_payload),
                max_candidates=args.max_candidates,
            )
        )

    summary = make_summary(
        manifests,
        generated_at=retrieved_at,
        dry_run=bool(args.dry_run),
        output_dir=output_dir,
    )
    json_dump(output_dir / "summary.json", summary)
    write_summary_markdown(output_dir / "summary.md", summary)
    print(
        "fetch: "
        f"sources={summary['sources']['total']} "
        f"ok={summary['sources']['ok']} disabled={summary['sources']['disabled']} "
        f"errors={summary['sources']['errors']} candidates={summary['candidates']['written']} "
        f"dry_run={summary['dry_run']} output={output_dir}"
    )
    # Source failures are intentionally reported in the artifact and do not
    # replace the last approved site.  CI may opt into a hard gate with
    # --fail-on-error for parser development.
    return 1 if args.fail_on_error and summary["sources"]["errors"] else 0


def make_summary(
    manifests: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    dry_run: bool,
    output_dir: Path,
) -> dict[str, Any]:
    statuses = {"ok": 0, "disabled": 0, "errors": 0, "not_modified": 0}
    parsed = 0
    written = 0
    for manifest in manifests:
        errors = manifest.get("errors") or []
        enabled = bool((manifest.get("metadata") or {}).get("enabled", True))
        if not enabled:
            statuses["disabled"] += 1
        elif errors:
            statuses["errors"] += 1
        else:
            statuses["ok"] += 1
        if manifest.get("not_modified"):
            statuses["not_modified"] += 1
        parsed += int(manifest.get("candidate_count") or 0)
        written += int(manifest.get("written_candidate_count") or 0)
    return {
        "schema_version": "source-fetch-summary@0.1",
        "generated_at": generated_at,
        "dry_run": dry_run,
        "output_dir": str(output_dir),
        "sources": {"total": len(manifests), **statuses},
        "candidates": {
            "parsed": parsed,
            "written": written,
            "truncated_sources": sum(
                1 for manifest in manifests if manifest.get("candidates_truncated")
            ),
        },
        "manifests": list(manifests),
    }


def write_summary_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    rows = [
        "# Source fetch candidate report",
        "",
        f"- generated: `{summary.get('generated_at')}`",
        f"- dry run: `{summary.get('dry_run')}`",
        "- This artifact is candidate-only; it never edits approved observations.",
        "",
        "| source | status | HTTP | parsed | written | warnings/errors |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for manifest in summary.get("manifests", []):
        if not isinstance(manifest, Mapping):
            continue
        meta = manifest.get("metadata") or {}
        status = "disabled" if meta.get("disabled") else ("error" if manifest.get("errors") else "ok")
        count = int(manifest.get("candidate_count") or 0)
        written = int(manifest.get("written_candidate_count") or 0)
        messages = len(manifest.get("warnings") or []) + len(manifest.get("errors") or [])
        rows.append(
            f"| {manifest.get('source_id')} | {status} | {manifest.get('http_status') or '—'} | {count} | {written} | {messages} |"
        )
    rows.extend(
        [
            "",
            "## Review",
            "",
            "Map `model_ref`/`benchmark_ref` to canonical IDs, verify locator and protocol, then append only approved facts to `data/observations/results.jsonl`.",
            "Never treat a missing or unverified candidate as zero, and do not scrape disabled Arena pages.",
        ]
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="list built-in public adapters")
    list_parser.add_argument("--json", action="store_true", help="emit JSON")
    list_parser.set_defaults(handler=lambda args: list_adapters(args.json))

    def add_fetch_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root", type=Path, default=ROOT, help="repository root")
        command.add_argument(
            "--sources",
            default="all",
            help="comma-separated adapter IDs (default: all; use list to inspect)",
        )
        command.add_argument(
            "--output-dir",
            type=Path,
            default=DEFAULT_OUTPUT,
            help="artifact directory (never canonical data)",
        )
        command.add_argument(
            "--input",
            "--payload",
            dest="input_path",
            type=Path,
            help="local fixture/payload for one adapter; skips network",
        )
        command.add_argument("--timeout", type=float, default=30.0)
        command.add_argument("--max-bytes", type=int, default=64 * 1024 * 1024)
        command.add_argument("--max-candidates", type=int, default=10000)
        command.add_argument(
            "--retrieved-at",
            help="override retrieval timestamp (ISO datetime; useful for fixtures)",
        )
        command.add_argument(
            "--dry-run",
            action="store_true",
            help="parse in memory and do not persist raw payloads",
        )
        command.add_argument(
            "--save-payload",
            action="store_true",
            help="opt in to payload storage after checking redistribution rights",
        )
        command.add_argument(
            "--fail-on-error",
            action="store_true",
            help="return non-zero if any selected adapter errors",
        )
        command.set_defaults(handler=fetch_adapters)

    fetch_parser = sub.add_parser("fetch", help="fetch and parse public sources")
    add_fetch_options(fetch_parser)

    check_parser = sub.add_parser(
        "check", help="scheduled-safe fetch: candidate metadata, no raw payloads"
    )
    add_fetch_options(check_parser)
    check_parser.set_defaults(dry_run=True, save_payload=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"fetch", "check"}:
        if args.timeout <= 0 or args.max_bytes <= 0 or args.max_candidates < 0:
            print("fetch: timeout/max-bytes must be positive and max-candidates >= 0", file=sys.stderr)
            return 2
        if args.retrieved_at:
            try:
                datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
            except ValueError:
                print("fetch: --retrieved-at must be ISO datetime", file=sys.stderr)
                return 2
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(f"fetch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
