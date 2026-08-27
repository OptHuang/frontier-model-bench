"""Hugging Face Hub leaderboard API adapter.

The Hub exposes a small JSON endpoint for benchmark datasets:
``/api/datasets/{owner}/{dataset}/leaderboard``.  This adapter keeps the
submission/model name exactly as returned by the Hub and emits candidates for
human alias mapping.  It never assumes that an unverified community
submission is equivalent to an official run.
"""

from __future__ import annotations

from typing import Any, Mapping

from .base import Adapter, AdapterRun, SourceSpec, json_loads


HF_DATASETS: dict[str, dict[str, Any]] = {
    "hf-swebench-verified": {
        "dataset": "SWE-bench/SWE-bench_Verified",
        "benchmark_ref": "swebench-verified",
        "label": "Hugging Face · SWE-bench Verified leaderboard",
    },
    "hf-swebench-pro": {
        "dataset": "ScaleAI/SWE-bench_Pro",
        "benchmark_ref": "swebench-pro",
        "label": "Hugging Face · SWE-bench Pro leaderboard",
    },
    "hf-hle": {
        "dataset": "cais/hle",
        "benchmark_ref": "hle",
        "label": "Hugging Face · Humanity's Last Exam leaderboard",
    },
    "hf-mmlu-pro": {
        "dataset": "TIGER-Lab/MMLU-Pro",
        "benchmark_ref": "mmlu-pro",
        "label": "Hugging Face · MMLU-Pro leaderboard",
    },
    "hf-gpqa": {
        "dataset": "Idavidrein/gpqa",
        "benchmark_ref": "gpqa-diamond",
        "label": "Hugging Face · GPQA leaderboard",
    },
    "hf-terminal-bench": {
        "dataset": "harborframework/terminal-bench-2.0",
        "benchmark_ref": "terminal-bench",
        "label": "Hugging Face · Terminal-Bench leaderboard",
    },
    "hf-aime-2026": {
        "dataset": "MathArena/aime_2026",
        "benchmark_ref": "aime-2026",
        "label": "Hugging Face · AIME leaderboard",
    },
    "hf-hmmt-2026": {
        "dataset": "MathArena/hmmt_feb_2026",
        "benchmark_ref": "hmmt",
        "label": "Hugging Face · HMMT leaderboard",
    },
}


class HuggingFaceLeaderboardAdapter(Adapter):
    def __init__(
        self,
        source_id: str,
        *,
        dataset: str,
        benchmark_ref: str,
        label: str,
        unit: str = "percent",
    ) -> None:
        self.dataset = dataset
        self.benchmark_ref = benchmark_ref
        self.unit = unit
        self.spec = SourceSpec(
            id=source_id,
            label=label,
            kind="official_api",
            url=f"https://huggingface.co/api/datasets/{dataset}/leaderboard",
            cadence="daily",
            notes=(
                "Hub leaderboard API; verify the submission flag and source "
                "before promoting a candidate to canonical observations."
            ),
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        value = json_loads(payload)
        if not isinstance(value, list):
            raise ValueError("expected a JSON array from the HF leaderboard API")

        candidates: list[dict[str, Any]] = []
        for index, row in enumerate(value):
            if not isinstance(row, Mapping):
                run.warnings.append(f"row {index}: ignored non-object entry")
                continue
            model_ref = row.get("modelId", row.get("model_id", row.get("model")))
            if not model_ref:
                run.warnings.append(f"row {index}: missing modelId; ignored")
                continue
            score = row.get("value", row.get("score"))
            source = row.get("source")
            source_url = source.get("url") if isinstance(source, Mapping) else None
            verified_raw = row.get("verified")
            verified = verified_raw if isinstance(verified_raw, bool) else None
            flags: list[str] = []
            if verified is not True:
                flags.append("unverified_submission")
            if not source_url:
                flags.append("missing_model_card_link")
            # Every emitted row is a *candidate*.  The source's verification
            # state is retained separately so it cannot be mistaken for this
            # repository's approved status.
            status = "candidate"
            author = row.get("author")
            # Keep provenance useful without copying the Hub's full author
            # profile (avatars, follower counts, plan metadata, etc.) into a
            # public artifact.
            if isinstance(author, Mapping):
                author_ref = author.get("name") or author.get("fullname") or author.get("_id")
            else:
                author_ref = author if isinstance(author, str) else None
            metadata = {
                "filename": row.get("filename"),
                "pull_request": row.get("pullRequest", row.get("pull_request")),
                "source_name": source.get("name")
                if isinstance(source, Mapping)
                else None,
                "submission_source_url": source_url,
                "lower_is_better": row.get("lower_is_better"),
                "num_parameters": row.get("num_parameters"),
                "author": author_ref,
                "source_status": "verified" if verified is True else "reported",
            }
            protocol = {
                "harness": "huggingface-eval-results",
                "filename": row.get("filename"),
                "verified": verified,
            }
            candidates.append(
                self.make_candidate(
                    run,
                    model_ref=model_ref,
                    benchmark_ref=self.benchmark_ref,
                    metric="score",
                    value=score,
                    unit=self.unit,
                    raw_value=score,
                    locator=f"rank={row.get('rank', index + 1)};row={index}",
                    rank=row.get("rank", index + 1),
                    verified=verified,
                    status=status,
                    # The endpoint is benchmark infrastructure, but an
                    # unverified community submission is not an A-level
                    # reproduced/owner result by itself.
                    evidence_level="A" if verified is True else "C",
                    comparability="conditional",
                    protocol=protocol,
                    metadata=metadata,
                    quality_flags=flags,
                )
            )
        return candidates


def build_huggingface_adapters() -> dict[str, HuggingFaceLeaderboardAdapter]:
    return {
        source_id: HuggingFaceLeaderboardAdapter(
            source_id,
            dataset=config["dataset"],
            benchmark_ref=config["benchmark_ref"],
            label=config["label"],
        )
        for source_id, config in HF_DATASETS.items()
    }
