"""Adapter for Stanford CRFM HELM's public JSON release artifacts."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .base import Adapter, AdapterRun, SourceSpec, json_loads, parse_number, slugify, utc_now


class HELMAdapter(Adapter):
    """Fetch the latest HELM project release and its core-scenarios table.

    ``project`` can be ``capabilities`` (the modern capabilities leaderboard)
    or ``lite``.  The public ``config.js`` tells us the current release and
    storage bucket; no scraping of rendered HTML is required.
    """

    def __init__(self, project: str = "capabilities") -> None:
        if project not in {"capabilities", "lite"}:
            raise ValueError("HELM project must be capabilities or lite")
        self.project = project
        self.config_url = f"https://crfm.stanford.edu/helm/{project}/latest/config.js"
        self.spec = SourceSpec(
            id=f"helm-{project}",
            label=f"Stanford HELM · {project} latest JSON",
            kind="official_artifact",
            url=self.config_url,
            cadence="monthly",
            notes=(
                "Reads the public HELM config/release artifact and core "
                "scenarios table. Metrics remain in HELM's native scale."
            ),
        )

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        now = retrieved_at or utc_now()
        config_response = client.get(self.config_url)
        if config_response.error or config_response.status is None or not (200 <= config_response.status < 300):
            run = AdapterRun(
                source_id=self.spec.id,
                requested_url=self.config_url,
                resolved_url=self.config_url,
                retrieved_at=now,
                http_status=config_response.status,
                headers=config_response.headers,
                payload=config_response.body,
                parser_version=self.spec.parser_version,
            )
            if config_response.error:
                run.errors.append(config_response.error)
            if config_response.status is not None and not (200 <= config_response.status < 300):
                run.errors.append(f"HTTP status {config_response.status}")
            return run
        config_text = config_response.body.decode("utf-8", "replace")
        release = _window_value(config_text, "RELEASE")
        base_url = _window_value(config_text, "BENCHMARK_OUTPUT_BASE_URL")
        project_id = _window_value(config_text, "PROJECT_ID") or self.project
        if not release or not base_url:
            return AdapterRun(
                source_id=self.spec.id,
                requested_url=self.config_url,
                resolved_url=self.config_url,
                retrieved_at=now,
                http_status=config_response.status,
                headers=config_response.headers,
                payload=config_response.body,
                parser_version=self.spec.parser_version,
                errors=["config.js did not contain RELEASE and BENCHMARK_OUTPUT_BASE_URL"],
            )
        base = base_url.rstrip("/")
        release_base = f"{base}/releases/{release}"
        summary_url = f"{release_base}/summary.json"
        groups_url = f"{release_base}/groups/core_scenarios.json"
        summary_response = client.get(summary_url)
        groups_response = client.get(groups_url)
        run = AdapterRun(
            source_id=self.spec.id,
            requested_url=self.config_url,
            resolved_url=groups_response.url or groups_url,
            retrieved_at=now,
            http_status=groups_response.status,
            headers=groups_response.headers,
            payload=groups_response.body,
            parser_version=self.spec.parser_version,
            metadata={
                "config_url": self.config_url,
                "project": project_id,
                "release": release,
                "summary_url": summary_url,
                "groups_url": groups_url,
            },
        )
        if summary_response.error or summary_response.status is None or not (200 <= summary_response.status < 300):
            run.warnings.append(
                "summary.json unavailable; observed_at will be omitted"
            )
        else:
            try:
                summary = json_loads(summary_response.body)
                if isinstance(summary, Mapping):
                    run.metadata["summary_date"] = summary.get("date")
                    run.metadata["suite"] = summary.get("release")
            except Exception as exc:
                run.warnings.append(f"summary parse warning: {exc}")
        if groups_response.error:
            run.errors.append(groups_response.error)
        if groups_response.status is not None and not (200 <= groups_response.status < 300):
            run.errors.append(f"HTTP status {groups_response.status}")
            return run
        try:
            run.candidates = self.parse_payload(run.payload, run)
        except Exception as exc:
            run.errors.append(f"parse error: {type(exc).__name__}: {exc}")
        return run

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        groups = json_loads(payload)
        if not isinstance(groups, list):
            raise ValueError("expected HELM groups JSON array")
        # The first table is normally Accuracy.  Parse every table so metrics
        # such as efficiency are retained with their explicit direction.
        candidates: list[dict[str, Any]] = []
        for table_index, table in enumerate(groups):
            if not isinstance(table, Mapping):
                continue
            title = str(table.get("title") or f"table-{table_index}")
            headers = table.get("header")
            rows = table.get("rows")
            if not isinstance(headers, list) or not isinstance(rows, list):
                run.warnings.append(f"{title}: missing header/rows")
                continue
            labels = [
                str(cell.get("value") if isinstance(cell, Mapping) else cell)
                for cell in headers
            ]
            if not labels:
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, list) or not row:
                    continue
                model_cell = row[0]
                model_ref = (
                    model_cell.get("value")
                    if isinstance(model_cell, Mapping)
                    else model_cell
                )
                if model_ref is None or not str(model_ref).strip():
                    continue
                for column_index, header in enumerate(labels[1:], start=1):
                    if column_index >= len(row):
                        continue
                    cell = row[column_index]
                    score = cell.get("value") if isinstance(cell, Mapping) else cell
                    benchmark_label, metric_label = _split_header(header)
                    direction = _infer_direction(metric_label)
                    unit = _infer_unit(score, metric_label)
                    candidates.append(
                        self.make_candidate(
                            run,
                            model_ref=model_ref,
                            benchmark_ref=f"helm-{slugify(benchmark_label)}",
                            metric=slugify(metric_label),
                            value=score,
                            unit=unit,
                            raw_value=score,
                            locator=(
                                f"release={run.metadata.get('release')};"
                                f"table={title};row={row_index};column={header}"
                            ),
                            status="candidate",
                            evidence_level="A",
                            comparability="conditional",
                            protocol={
                                "harness": "helm",
                                "project": run.metadata.get("project"),
                                "release": run.metadata.get("release"),
                                "table": title,
                                "direction": direction,
                                "source_status": "published_release",
                            },
                            metadata={
                                "header": header,
                                "header_description": (
                                    headers[column_index].get("description")
                                    if isinstance(headers[column_index], Mapping)
                                    else None
                                ),
                                "project": run.metadata.get("project"),
                                "release": run.metadata.get("release"),
                                "direction": direction,
                            },
                            quality_flags=(
                                ["missing_score"] if score is None else []
                            ),
                            observed_at=run.metadata.get("summary_date"),
                        )
                    )
        return candidates


def _window_value(text: str, key: str) -> str | None:
    pattern = rf"window\.{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _split_header(header: str) -> tuple[str, str]:
    if " - " in header:
        benchmark, metric = header.split(" - ", 1)
        return benchmark.strip(), metric.strip()
    return header.strip(), "score"


def _infer_direction(metric: str) -> str:
    lowered = metric.lower()
    return "lower" if any(token in lowered for token in ("time", "cost", "#", "tokens", "length", "error")) else "higher"


def _infer_unit(score: Any, metric: str) -> str:
    lowered = metric.lower()
    if any(token in lowered for token in ("time", "latency", "seconds", "cost")):
        return "seconds" if "time" in lowered or "second" in lowered else "usd"
    number, _ = parse_number(score)
    if number is not None and 0 <= number <= 1:
        return "fraction"
    return "count"


def build_helm_adapters() -> dict[str, HELMAdapter]:
    return {
        "helm-capabilities": HELMAdapter("capabilities"),
        "helm-lite": HELMAdapter("lite"),
    }
