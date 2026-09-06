"""Read the official TB-Science 0.1 aggregate API, never individual traces.

The endpoint is the public homepage's own data source. Pin the board/version,
retain model x harness, and treat website display status as disclosure only.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from .base import Adapter, AdapterRun, SourceSpec, candidate_id, json_loads, parse_number, slugify


class TerminalBenchScienceAdapter(Adapter):
    PACKAGE = "terminal-bench-science/terminal-bench-science"
    BOARD = "v0-1-eval"
    VERSION = "terminal-bench-science@0.1"
    URL = "https://www.terminal-bench-science.ai/api/leaderboard?package=terminal-bench-science%2Fterminal-bench-science&name=v0-1-eval"
    PAGE = "https://www.terminal-bench-science.ai/"
    HARNESS_IDS = {"Claude Code": "claude-code", "Codex": "codex", "mini-SWE-agent": "mini-swe-agent", "Grok Build": "grok-build"}

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="src-terminal-bench-science", label="Terminal-Bench Science 0.1 · official leaderboard",
            kind="official_leaderboard", url=self.URL, cadence="daily", parser_version="tb-science@0.1.0",
            notes="Aggregate resolution rates; model x harness x effort, not independently reproduced.",
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        document = json_loads(payload)
        board = document.get("leaderboard") if isinstance(document, Mapping) else None
        if not isinstance(board, Mapping) or board.get("package") != self.PACKAGE or board.get("name") != self.BOARD:
            raise ValueError("expected the pinned TB-Science v0-1-eval leaderboard")
        if not isinstance(document.get("rows"), list):
            raise ValueError("missing public aggregate rows")
        candidates = []
        for index, result in enumerate(document["rows"]):
            if not isinstance(result, Mapping) or result.get("status") != "display":
                run.warnings.append(f"rows[{index}]: not a displayed public row; skipped")
                continue
            metadata, metrics = result.get("metadata", {}), result.get("metrics", {})
            model, agent = metadata.get("model_display", {}), metadata.get("agent_display", {})
            model_name, harness = model.get("label"), agent.get("label")
            value, _ = parse_number(metrics.get("accuracy"))
            if not model_name or not harness or not result.get("id") or value is None or not 0 <= value <= 100:
                run.warnings.append(f"rows[{index}]: missing model/harness/id or valid percent; skipped")
                continue
            if metrics.get("tasks") != 210 or result.get("n_trials") != 210:
                run.warnings.append(f"rows[{index}]: not the complete 70 tasks x 3 trials; skipped")
                continue
            harness_id = self.HARNESS_IDS.get(harness, "reported-" + slugify(harness))
            row_url = f"https://hub.harborframework.com/datasets/{self.PACKAGE}/latest/leaderboards/{self.BOARD}/rows/{quote(result['id'], safe='')}"
            protocol = {
                "subject_type": "system", "harness": harness, "harness_id": harness_id,
                "harness_url": agent.get("url"), "harness_version": None,
                "reasoning_effort": metadata.get("reasoning_effort"), "benchmark_version": "0.1",
                "leaderboard": self.BOARD, "dataset_version_ids": board.get("dataset_version_ids", []),
                "view": "all", "task_count": 70, "trials_per_task": 3, "n_trials": result["n_trials"],
                "aggregation": "mean_resolution_rate", "metric_direction": "higher",
                "environment": None, "timeout": None, "judge_version": None,
            }
            row = self.make_candidate(
                run, model_ref=model_name, benchmark_ref="terminal-bench-science",
                metric="resolution_rate", value=value, raw_value=metrics["accuracy"], unit="percent",
                locator=f"$.rows[{index}];id={result['id']};metrics.accuracy",
                status="candidate", verified=False, evidence_level="A", comparability="conditional",
                protocol=protocol,
                metadata={
                    "source_status": "reported", "source_name": board.get("title"),
                    "submission_source_url": row_url, "leaderboard_url": self.PAGE,
                    "model_url": model.get("url"), "source_model_release_date": metadata.get("model_release_date"),
                    "source_row_id": result["id"], "source_row_created_at": result.get("created_at"),
                    "source_row_updated_at": result.get("updated_at"), "source_board_updated_at": board.get("updated_at"),
                    "passes": metrics.get("passes"), "total_cost_usd": metrics.get("total_cost_usd"),
                    "total_tokens": metrics.get("total_tokens"), "accuracy_stderr": metrics.get("accuracy_stderr"),
                    "domain_metrics": metrics.get("domain_metrics"),
                },
                quality_flags=["agent_system_score", "missing_harness_version", "missing_environment", "missing_source_date"],
            )
            row.update({"subject_type": "system", "harness_id": harness_id, "harness": harness,
                        "source_model": model_name, "benchmark_version_id": self.VERSION,
                        "published_at": None, "uncertainty": {"standard_error_percentage_points": metrics.get("accuracy_stderr")}})
            # Source row timestamps describe website edits, not the run date.
            row["candidate_id"] = candidate_id(run.source_id, {k: v for k, v in row.items() if k != "candidate_id"})
            candidates.append(row)
        run.metadata.update({"aggregate_only": True, "benchmark_version_id": self.VERSION,
                             "leaderboard_id": board.get("id"), "model_count": len(candidates)})
        return candidates
