"""Adapters for LMArena / Chatbot Arena.

The interactive Arena application and undocumented endpoints are deliberately
not scraped.  The enabled adapter below consumes Arena's official,
versioned Hugging Face dataset export; the interactive-page adapter remains a
metadata-only sentinel so a source change cannot silently turn into a scrape.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Iterable, Mapping, Sequence

from .base import Adapter, AdapterRun, SourceSpec, json_loads, slugify, utc_now


class ArenaMetadataAdapter(Adapter):
    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="lmsys-arena",
            label="LMArena / Chatbot Arena · metadata only (disabled)",
            kind="unstable_web_app",
            url="https://arena.ai/leaderboard",
            cadence="daily",
            enabled=False,
            notes=(
                "Disabled: no stable, documented public score API. Do not "
                "scrape transient frontend bundles or infer ratings from "
                "screenshots. Add a dated, licensed snapshot adapter first."
            ),
        )

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        now = retrieved_at or utc_now()
        return AdapterRun(
            source_id=self.spec.id,
            requested_url=self.spec.url,
            resolved_url=self.spec.url,
            retrieved_at=now,
            http_status=None,
            candidates=[],
            warnings=[self.spec.notes or "adapter disabled"],
            metadata={
                "enabled": False,
                "disabled": True,
                "reason": "unstable_or_undocumented_api",
                "metadata_only": True,
            },
            parser_version=self.spec.parser_version,
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        return []


class ArenaHFDatasetAdapter(Adapter):
    """Read the official Arena leaderboard dataset through HF Dataset Viewer.

    Arena publishes historical leaderboard snapshots in
    ``lmarena-ai/leaderboard-dataset``.  The Dataset Viewer ``/rows`` endpoint
    has a documented maximum page length of 100, so this adapter paginates by
    offset and stops at both the reported total and a configurable per-config
    safety limit.  It emits only candidate rows; model aliases and benchmark
    release mapping remain a human review step.

    ``configs`` defaults to the six high-value views requested for the model
    dashboard.  Callers can pass ``ALL_CONFIGS`` (or another tuple) to include
    style-control, factuality, image/video, and agent-signal subsets.
    """

    DATASET = "lmarena-ai/leaderboard-dataset"
    ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"
    DATASET_URL = "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"
    PAGE_SIZE = 100
    CORE_CONFIGS = (
        "text",
        "vision",
        "webdev",
        "search",
        "document",
        "agent",
    )
    ALL_CONFIGS = (
        "agent",
        "agent_bash_recovery_steps",
        "agent_praise_complaint",
        "agent_steerability",
        "agent_task_outcome_explicit",
        "agent_tool_hallucination",
        "document",
        "document_style_control",
        "image_edit",
        "image_to_video",
        "search",
        "search_factuality",
        "search_style_control",
        "text",
        "text_factuality",
        "text_style_control",
        "text_to_image",
        "text_to_video",
        "video_edit",
        "vision",
        "vision_style_control",
        "webdev",
    )
    AGENT_CONFIGS = frozenset(
        {
            "agent",
            "agent_bash_recovery_steps",
            "agent_praise_complaint",
            "agent_steerability",
            "agent_task_outcome_explicit",
            "agent_tool_hallucination",
        }
    )
    # These views involve an externally mediated workflow even when the
    # published row uses a rating field rather than Agent IPS.  Keep them out
    # of a model-only matrix unless a reviewer explicitly maps the harness.
    SYSTEM_CONFIGS = AGENT_CONFIGS | {"webdev", "search", "search_factuality"}

    def __init__(
        self,
        *,
        configs: Sequence[str] | None = None,
        split: str = "latest",
        # One page is the safe scheduled default.  Dataset Viewer rate limits
        # repeated pagination aggressively; a maintainer can opt into a
        # larger limit for an ad-hoc refresh after checking the source quota.
        max_rows_per_config: int = 100,
        page_size: int = PAGE_SIZE,
    ) -> None:
        chosen = tuple(dict.fromkeys(configs or self.CORE_CONFIGS))
        if not chosen:
            raise ValueError("Arena HF adapter needs at least one config")
        if split not in {"latest", "full"}:
            raise ValueError("Arena HF split must be latest or full")
        if max_rows_per_config <= 0:
            raise ValueError("max_rows_per_config must be positive")
        if not 1 <= page_size <= self.PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {self.PAGE_SIZE}")
        self.configs = chosen
        self.split = split
        self.max_rows_per_config = max_rows_per_config
        self.page_size = page_size
        self.spec = SourceSpec(
            id="lmarena-hf-dataset",
            label="Arena · official Hugging Face leaderboard dataset",
            kind="official_dataset_api",
            url=self.DATASET_URL,
            cadence="daily",
            notes=(
                "Arena-published CC-BY dataset via the documented HF Dataset "
                "Viewer rows API; latest split, paginated at 100 rows/page. "
                "Rows remain candidates until aliases and protocol are reviewed."
            ),
        )

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        now = retrieved_at or utc_now()
        pages: list[dict[str, Any]] = []
        all_rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        response_headers: dict[str, str] = {}
        statuses: list[int] = []
        totals: dict[str, int | None] = {}
        page_counts: dict[str, int] = {}
        truncated_configs: list[str] = []

        for config in self.configs:
            offset = 0
            config_rows = 0
            pages_for_config = 0
            reported_total: int | None = None
            while config_rows < self.max_rows_per_config:
                query = urllib.parse.urlencode(
                    {
                        "dataset": self.DATASET,
                        "config": config,
                        "split": self.split,
                        "offset": offset,
                        "length": min(self.page_size, self.max_rows_per_config - config_rows),
                    }
                )
                request_url = f"{self.ROWS_ENDPOINT}?{query}"
                response = client.get(request_url, headers={"Accept": "application/json"})
                response_headers.update(response.headers)
                if response.status is not None:
                    statuses.append(response.status)
                if response.error or response.status is None or not (200 <= response.status < 300):
                    errors.append(
                        f"{config} offset={offset}: "
                        f"{response.error or f'HTTP status {response.status}'}"
                    )
                    break
                try:
                    page = json_loads(response.body)
                except Exception as exc:
                    errors.append(
                        f"{config} offset={offset}: response JSON parse error: {exc}"
                    )
                    break
                if not isinstance(page, Mapping):
                    errors.append(f"{config} offset={offset}: response is not an object")
                    break
                raw_rows = page.get("rows")
                if not isinstance(raw_rows, list):
                    errors.append(f"{config} offset={offset}: rows is not an array")
                    break
                reported = page.get("num_rows_total")
                if isinstance(reported, int) and reported >= 0:
                    reported_total = reported
                pages.append(
                    {
                        "config": config,
                        "split": self.split,
                        "offset": offset,
                        "request_url": request_url,
                        "response": page,
                    }
                )
                pages_for_config += 1
                for item in raw_rows:
                    if isinstance(item, Mapping):
                        row = item.get("row")
                        if isinstance(row, Mapping):
                            all_rows.append(
                                {
                                    "config": config,
                                    "split": self.split,
                                    "row_idx": item.get("row_idx"),
                                    "row": dict(row),
                                }
                            )
                received = len(raw_rows)
                config_rows += received
                offset += received
                if received == 0 or (
                    reported_total is not None and offset >= reported_total
                ):
                    break
                if received < self.page_size:
                    # A short page is normally the final page.  Continue only
                    # when the server explicitly reports more rows.
                    if reported_total is None or offset >= reported_total:
                        break
            totals[config] = reported_total
            page_counts[config] = pages_for_config
            if reported_total is not None and config_rows < reported_total:
                truncated_configs.append(config)
                warnings.append(
                    f"{config}: capped at {self.max_rows_per_config} rows "
                    f"of reported {reported_total}"
                )

        envelope = {
            "dataset": self.DATASET,
            "split": self.split,
            "configs": list(self.configs),
            "pages": pages,
        }
        payload = json.dumps(
            envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        all_success = bool(statuses) and all(200 <= status < 300 for status in statuses)
        run = AdapterRun(
            source_id=self.spec.id,
            requested_url=self.spec.url,
            resolved_url=self.ROWS_ENDPOINT,
            retrieved_at=now,
            http_status=200 if all_success else (statuses[-1] if statuses else None),
            headers=response_headers,
            payload=payload,
            warnings=warnings,
            errors=errors,
            metadata={
                "dataset": self.DATASET,
                "dataset_url": self.DATASET_URL,
                "rows_endpoint": self.ROWS_ENDPOINT,
                "split": self.split,
                "configs": list(self.configs),
                "page_size": self.page_size,
                "max_rows_per_config": self.max_rows_per_config,
                "reported_rows": totals,
                "pages": page_counts,
                "rows_fetched": {
                    config: sum(1 for row in all_rows if row["config"] == config)
                    for config in self.configs
                },
                "truncated_configs": truncated_configs,
                "license": "cc-by-4.0",
            },
            parser_version=self.spec.parser_version,
        )
        run.candidates = self.parse_payload(payload, run)
        return run

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        document = json_loads(payload)
        if isinstance(document, Mapping) and isinstance(document.get("pages"), list):
            page_items: Iterable[Mapping[str, Any]] = (
                item for item in document["pages"] if isinstance(item, Mapping)
            )
            dataset = str(document.get("dataset") or self.DATASET)
            split = str(document.get("split") or self.split)
        elif isinstance(document, Mapping) and isinstance(document.get("rows"), list):
            # Convenient single-page fixture form.
            page_items = [{"config": self.configs[0], "split": self.split, "response": document}]
            dataset = self.DATASET
            split = self.split
        else:
            raise ValueError("expected Arena HF page envelope or rows response")

        candidates: list[dict[str, Any]] = []
        for page_item in page_items:
            config = str(page_item.get("config") or self.configs[0])
            page_split = str(page_item.get("split") or split)
            offset = page_item.get("offset", 0)
            response = page_item.get("response", page_item)
            if not isinstance(response, Mapping):
                run.warnings.append(f"{config} offset={offset}: page is not an object")
                continue
            rows = response.get("rows")
            if not isinstance(rows, list):
                run.warnings.append(f"{config} offset={offset}: missing rows")
                continue
            for position, item in enumerate(rows):
                if not isinstance(item, Mapping):
                    continue
                row = item.get("row", item)
                if not isinstance(row, Mapping):
                    continue
                row_idx = item.get("row_idx")
                if row_idx is None:
                    row_idx = int(offset or 0) + position
                candidate = self._candidate_for_row(
                    run,
                    row,
                    config=config,
                    split=page_split,
                    dataset=dataset,
                    row_idx=row_idx,
                )
                if candidate is not None:
                    candidates.append(candidate)
        return candidates

    def _candidate_for_row(
        self,
        run: AdapterRun,
        row: Mapping[str, Any],
        *,
        config: str,
        split: str,
        dataset: str,
        row_idx: Any,
    ) -> dict[str, Any] | None:
        model_ref = row.get("model_name") or row.get("model")
        if model_ref is None or not str(model_ref).strip():
            run.warnings.append(f"{config} row={row_idx}: missing model_name")
            return None
        is_ips = config in self.AGENT_CONFIGS or (
            "score" in row and "rating" not in row
        )
        is_agent = config in self.SYSTEM_CONFIGS or is_ips
        if "rating" in row:
            value = row.get("rating")
            # Arena switched its public rating methodology to Bradley–Terry;
            # keep the metric name explicit instead of perpetuating the old
            # generic "Elo" label. Historical snapshots remain versioned by
            # source locator/date and must not be merged across methods.
            metric = "arena_score_bt"
            unit = "rating"
            lower = row.get("rating_lower")
            upper = row.get("rating_upper")
            rating_method = "bradley-terry"
            count_key = "vote_count"
        elif "score" in row:
            value = row.get("score")
            metric = "ips"
            unit = "fraction"
            lower = row.get("score_ci_lower")
            upper = row.get("score_ci_upper")
            rating_method = "ips"
            count_key = "observation_count"
        else:
            run.warnings.append(f"{config} row={row_idx}: no rating or score field")
            return None
        flags: list[str] = []
        flags.append("agent_ips" if is_ips else "human_preference_rating")
        if lower is None or upper is None:
            flags.append("missing_confidence_interval")
        if row.get(count_key) is None:
            flags.append(f"missing_{count_key}")
        category = row.get("category")
        if category is None or str(category).strip() == "":
            flags.append("missing_category")
        subject_type = "system" if is_agent else "model"
        candidate = self.make_candidate(
            run,
            model_ref=model_ref,
            benchmark_ref=f"arena-{slugify(config)}",
            metric=metric,
            value=value,
            unit=unit,
            raw_value=value,
            locator=(
                f"dataset={dataset};config={config};split={split};row_idx={row_idx}"
            ),
            rank=row.get("rank"),
            verified=True,
            # The source row is published by Arena, but this adapter's output
            # is still an unreviewed candidate and must not look approved.
            status="candidate",
            evidence_level="A",
            comparability="conditional",
            protocol={
                "harness": "arena-agent" if is_ips else "arena-human-preference",
                "arena_config": config,
                "split": split,
                "category": category,
                "rating_method": rating_method,
                "subject_type": subject_type,
            },
            metadata={
                "organization": row.get("organization"),
                "license": row.get("license"),
                "source_status": "publisher_dataset",
                "category": category,
                "rating": row.get("rating"),
                "rating_lower": row.get("rating_lower"),
                "rating_upper": row.get("rating_upper"),
                "score": row.get("score"),
                "score_ci_lower": row.get("score_ci_lower"),
                "score_ci_upper": row.get("score_ci_upper"),
                "variance": row.get("variance"),
                "vote_count": row.get("vote_count"),
                "observation_count": row.get("observation_count"),
                "session_count": row.get("session_count"),
                "dataset": dataset,
                "config": config,
                "split": split,
            },
            quality_flags=flags,
            observed_at=row.get("leaderboard_publish_date"),
        )
        candidate["uncertainty"] = {
            "type": "confidence_interval",
            "level": 0.95,
            "lower": lower,
            "upper": upper,
        }
        return candidate


def build_arena_adapters(
    *,
    configs: Sequence[str] | None = None,
    max_rows_per_config: int = 100,
) -> dict[str, Adapter]:
    """Return disabled interactive and enabled official dataset adapters.

    ``configs`` and ``max_rows_per_config`` are exposed for an explicit local
    refresh; the scheduled CLI keeps the conservative one-page default.
    """

    return {
        "lmsys-arena": ArenaMetadataAdapter(),
        "lmarena-hf-dataset": ArenaHFDatasetAdapter(
            configs=configs, max_rows_per_config=max_rows_per_config
        ),
    }
