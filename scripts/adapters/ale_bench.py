"""Aggregate-only adapter for SakanaAI's ALE-Bench leaderboard.

This is algorithm engineering on AHC tasks, distinct from Agents' Last Exam.
The public summary includes generated programs and per-task results; this
adapter emits only the published aggregate numbers and provenance. It does
not redistribute tasks or solutions, infer a judge version, or approve runs.
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from .base import Adapter, AdapterRun, SourceSpec, candidate_id, json_loads


class ALEBenchAdapter(Adapter):
    LEADERBOARD_URL = "https://sakanaai.github.io/ALE-Bench-Leaderboard/"
    URL = LEADERBOARD_URL + "data/results_summary.json"
    SETUP_URL = "https://github.com/SakanaAI/ALE-Bench/tree/v1.2.1/llm_configs"
    IMPLEMENTATION_URL = "https://github.com/SakanaAI/ALE-Bench/tree/v1.2.1/src/ale_bench_eval"
    VIEWS = ("all", "short", "long")

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="src-ale-bench",
            label="SakanaAI · ALE-Bench official aggregate results",
            kind="official_artifact",
            url=self.URL,
            cadence="weekly",
            parser_version="ale-bench@0.1.0",
            notes="Published performance/rank aggregates, with self-refine configuration; not independently reproduced.",
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        document = json_loads(payload)
        if not isinstance(document, list):
            raise ValueError("expected an array of model summaries")
        candidates: list[dict[str, Any]] = []
        model_count = 0
        configuration_count = 0
        for model_index, model in enumerate(document):
            if not isinstance(model, Mapping) or not isinstance(model.get("model_name"), str):
                run.warnings.append(f"model[{model_index}]: missing model_name; skipped")
                continue
            model_name = model["model_name"].strip()
            configurations = model.get("overall_results")
            if not model_name or not isinstance(configurations, list):
                run.warnings.append(f"model[{model_index}]: missing model/configurations; skipped")
                continue
            model_count += 1
            detail_url = self._detail_url(model.get("detail_path"))
            effort = self._effort(model_name)
            for config_index, config in enumerate(configurations):
                if not isinstance(config, Mapping):
                    run.warnings.append(f"{model_name}[{config_index}]: non-object configuration; skipped")
                    continue
                iterations = config.get("num_self_refine")
                if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
                    run.warnings.append(f"{model_name}[{config_index}]: missing positive self-refine count; skipped")
                    continue
                configuration_count += 1
                task_results = config.get("results")
                task_ids = [
                    row["problem_id"] for row in task_results
                    if isinstance(row, Mapping) and isinstance(row.get("problem_id"), str)
                ] if isinstance(task_results, list) else []
                for metric, unit, direction in (("performance", "score", "higher"), ("rank", "rank", "lower")):
                    metric_views = config.get(metric)
                    if not isinstance(metric_views, Mapping):
                        continue
                    for view in self.VIEWS:
                        stats = metric_views.get(view)
                        if not isinstance(stats, Mapping) or "mean" not in stats:
                            continue
                        protocol = {
                            "subject_type": "system",
                            "harness": "ALE-Bench self-refine",
                            "harness_id": "ale-bench-self-refine",
                            "self_refine_iterations": iterations,
                            "view": view,
                            "aggregation": "arithmetic_mean",
                            "metric_direction": direction,
                            "reasoning_effort": effort,
                            "benchmark_version": None,
                            "judge_version": None,
                            "harness_version_hint": "v1.2.1",
                            "setup_url": self.SETUP_URL,
                            "implementation_url": self.IMPLEMENTATION_URL,
                            "leaderboard_url": self.LEADERBOARD_URL,
                        }
                        row = self.make_candidate(
                            run,
                            model_ref=model_name,
                            benchmark_ref="ale-bench",
                            metric=metric,
                            value=stats["mean"],
                            unit=unit,
                            raw_value=stats["mean"],
                            locator=(f"$[{model_index}];model_name={model_name};"
                                     f"overall_results[{config_index}];num_self_refine={iterations};"
                                     f"{metric}.{view}.mean"),
                            status="candidate",
                            evidence_level="A",
                            comparability="conditional",
                            verified=False,
                            protocol=protocol,
                            metadata={
                                "source_status": "reported",
                                "source_name": "SakanaAI ALE-Bench leaderboard",
                                "source_link": self.LEADERBOARD_URL,
                                "detail_url": detail_url,
                                "aggregate_statistics": dict(stats),
                                "all_problem_count": len(task_ids) if task_ids else None,
                                "all_problem_ids": task_ids,
                                "cost_statistics": self._statistics(config, "cost", view),
                                "input_token_statistics": self._statistics(config, "input_tokens", view),
                                "output_token_statistics": self._statistics(config, "output_tokens", view),
                            },
                            quality_flags=[
                                "agent_system_score", "configuration_specific",
                                "missing_source_date", "missing_benchmark_version", "missing_judge_version",
                            ],
                        )
                        row.update({
                            "subject_type": "system",
                            "harness_id": "ale-bench-self-refine",
                            "harness": "ALE-Bench self-refine",
                            "source_model": model_name,
                            "benchmark_version_id": None,
                            "published_at": None,
                        })
                        row["candidate_id"] = candidate_id(run.source_id, {
                            key: value for key, value in row.items() if key != "candidate_id"
                        })
                        candidates.append(row)
        run.metadata.update({
            "model_count": model_count,
            "configuration_count": configuration_count,
            "leaderboard_url": self.LEADERBOARD_URL,
            "aggregate_only": True,
            "benchmark_version_id": None,
            "judge_version": None,
        })
        if not candidates:
            run.warnings.append("no supported ALE-Bench aggregate rows found")
        return candidates

    @staticmethod
    def _effort(model_name: str) -> str | None:
        match = re.search(r"-(no-thinking|xhigh|high|medium|low|max)$", model_name)
        return match.group(1) if match else None

    @classmethod
    def _detail_url(cls, value: Any) -> str | None:
        if not isinstance(value, str) or not value.startswith("data/model_details/"):
            return None
        result = urljoin(cls.LEADERBOARD_URL, value)
        return result if urlsplit(result).netloc == urlsplit(cls.LEADERBOARD_URL).netloc else None

    @staticmethod
    def _statistics(config: Mapping[str, Any], metric: str, view: str) -> dict[str, Any] | None:
        views = config.get(metric)
        value = views.get(view) if isinstance(views, Mapping) else None
        return dict(value) if isinstance(value, Mapping) else None
