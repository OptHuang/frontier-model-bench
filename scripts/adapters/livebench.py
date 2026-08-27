"""Adapter for the machine-readable LiveBench GitHub leaderboard tables."""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Mapping

from .base import Adapter, AdapterRun, SourceSpec, json_loads, slugify


TABLE_PATTERN = re.compile(r"^public/table_(\d{4}_\d{2}_\d{2})\.csv$")


class LiveBenchAdapter(Adapter):
    """Discover and parse the newest ``table_YYYY_MM_DD.csv`` release.

    Discovery happens through the public GitHub tree API, then the selected
    raw CSV is downloaded.  The selected path/date is stored in the manifest
    metadata so a later run can be compared even if ``main`` moves.
    """

    TREE_URL = "https://api.github.com/repos/LiveBench/new-livebench/git/trees/main?recursive=1"
    RAW_BASE = "https://raw.githubusercontent.com/LiveBench/new-livebench/main/"

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="livebench-official",
            label="LiveBench · official release table",
            kind="official_repository",
            url=self.TREE_URL,
            cadence="weekly",
            notes=(
                "Selects the newest dated CSV in the official repository; "
                "scores are source-release candidates until model aliases and "
                "task/version semantics are reviewed."
            ),
        )

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        from .base import utc_now

        now = retrieved_at or utc_now()
        discovery = client.get(self.TREE_URL, headers={"Accept": "application/vnd.github+json"})
        if discovery.error or discovery.status is None or not (200 <= discovery.status < 300):
            run = AdapterRun(
                source_id=self.spec.id,
                requested_url=self.TREE_URL,
                resolved_url=self.TREE_URL,
                retrieved_at=now,
                http_status=discovery.status,
                headers=discovery.headers,
                payload=discovery.body,
                parser_version=self.spec.parser_version,
            )
            if discovery.error:
                run.errors.append(discovery.error)
            if discovery.status is not None and not (200 <= discovery.status < 300):
                run.errors.append(f"HTTP status {discovery.status}")
            return run
        try:
            tree = json_loads(discovery.body)
            paths = [
                item.get("path")
                for item in tree.get("tree", [])
                if isinstance(item, Mapping) and item.get("type") == "blob"
            ]
            dated = [
                (match.group(1), path)
                for path in paths
                if isinstance(path, str) and (match := TABLE_PATTERN.match(path))
            ]
        except Exception as exc:
            run = AdapterRun(
                source_id=self.spec.id,
                requested_url=self.TREE_URL,
                resolved_url=self.TREE_URL,
                retrieved_at=now,
                http_status=discovery.status,
                headers=discovery.headers,
                payload=discovery.body,
                parser_version=self.spec.parser_version,
                errors=[f"discovery parse error: {type(exc).__name__}: {exc}"],
            )
            return run
        if not dated:
            return AdapterRun(
                source_id=self.spec.id,
                requested_url=self.TREE_URL,
                resolved_url=self.TREE_URL,
                retrieved_at=now,
                http_status=discovery.status,
                headers=discovery.headers,
                payload=discovery.body,
                parser_version=self.spec.parser_version,
                errors=["no dated public/table_YYYY_MM_DD.csv found"],
            )
        release_date, path = max(dated)
        selected_url = self.RAW_BASE + path
        response = client.get(selected_url, headers={"Accept": "text/csv"})
        run = AdapterRun(
            source_id=self.spec.id,
            requested_url=self.TREE_URL,
            resolved_url=response.url or selected_url,
            retrieved_at=now,
            http_status=response.status,
            headers=response.headers,
            payload=response.body,
            parser_version=self.spec.parser_version,
            metadata={
                "discovery_url": self.TREE_URL,
                "selected_path": path,
                "release_date": release_date,
                "tree_sha": tree.get("sha") if isinstance(tree, Mapping) else None,
            },
        )
        if response.error:
            run.errors.append(response.error)
        if response.status is not None and not (200 <= response.status < 300):
            run.errors.append(f"HTTP status {response.status}")
            return run
        try:
            run.candidates = self.parse_payload(run.payload, run)
        except Exception as exc:
            run.errors.append(f"parse error: {type(exc).__name__}: {exc}")
        return run

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(reader.fieldnames) < 2:
            raise ValueError("expected a CSV with model and task columns")
        model_column = reader.fieldnames[0]
        candidates: list[dict[str, Any]] = []
        for row_index, row in enumerate(reader):
            model_ref = (row.get(model_column) or "").strip()
            if not model_ref:
                run.warnings.append(f"CSV row {row_index}: missing model; skipped")
                continue
            for task in reader.fieldnames[1:]:
                raw = row.get(task)
                candidates.append(
                    self.make_candidate(
                        run,
                        model_ref=model_ref,
                        benchmark_ref=f"livebench-{slugify(task)}",
                        metric="score",
                        value=raw,
                        unit="percent",
                        raw_value=raw,
                        locator=f"path={run.metadata.get('selected_path')};row={row_index};column={task}",
                        status="candidate",
                        evidence_level="A",
                        comparability="conditional",
                        protocol={
                            "harness": "livebench-official-table",
                            "release_date": run.metadata.get("release_date"),
                            "task": task,
                        },
                        metadata={
                            "release_date": run.metadata.get("release_date"),
                            "task": task,
                            "source_status": "published_release",
                        },
                        quality_flags=(
                            ["missing_score"]
                            if raw is None or str(raw).strip().lower() in {"", "-", "—", "n/a"}
                            else []
                        ),
                        observed_at=run.metadata.get("release_date"),
                    )
                )
        return candidates
