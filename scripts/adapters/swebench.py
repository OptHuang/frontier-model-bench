"""Adapter for the official SWE-bench website's machine-readable JSON."""

from __future__ import annotations

from typing import Any, Mapping

from .base import Adapter, AdapterRun, SourceSpec, json_loads, slugify


class SWEbenchOfficialAdapter(Adapter):
    """Parse ``data/leaderboards.json`` from swe-bench.github.io.

    The official site publishes several variants (Verified, Lite, Test,
    Multilingual, ...).  Variant names are retained in ``benchmark_ref``;
    callers must map them to a registered benchmark version before approval.
    """

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="swebench-official",
            label="SWE-bench · official leaderboard JSON",
            kind="official_repository",
            url=(
                "https://raw.githubusercontent.com/swe-bench/"
                "swe-bench.github.io/master/data/leaderboards.json"
            ),
            cadence="daily",
            notes=(
                "Official site data; rows mix model-only and agent systems. "
                "Keep the variant and scaffold in review."
            ),
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        document = json_loads(payload)
        if not isinstance(document, Mapping):
            raise ValueError("expected an object with a leaderboards array")
        leaderboards = document.get("leaderboards")
        if not isinstance(leaderboards, list):
            raise ValueError("leaderboards field is not an array")

        candidates: list[dict[str, Any]] = []
        for board_index, board in enumerate(leaderboards):
            if not isinstance(board, Mapping):
                run.warnings.append(f"leaderboard {board_index}: ignored non-object")
                continue
            board_name = str(board.get("name") or f"variant-{board_index}").strip()
            benchmark_ref = f"swebench-{slugify(board_name)}"
            results = board.get("results")
            if not isinstance(results, list):
                run.warnings.append(f"{board_name}: results is not an array")
                continue
            for row_index, row in enumerate(results):
                if not isinstance(row, Mapping):
                    run.warnings.append(f"{board_name}[{row_index}]: ignored non-object")
                    continue
                model_ref = row.get("model_display") or row.get("model") or row.get("name")
                if not model_ref:
                    run.warnings.append(f"{board_name}[{row_index}]: missing model name")
                    continue
                agent = row.get("agent")
                os_model = row.get("os_model") is True
                os_system = row.get("os_system") is True
                # The site uses an agent/scaffold column.  Preserve it and use
                # a conservative subject classification for review.
                subject_type = "system" if (agent or os_system) and not os_model else "model"
                checked = row.get("checked")
                verified = checked if isinstance(checked, bool) else None
                flags: list[str] = []
                if verified is not True:
                    flags.append("not_independently_checked")
                if subject_type == "system":
                    flags.append("agent_system_score")
                metadata = {
                    "display_name": row.get("name"),
                    "model_display": row.get("model_display"),
                    "model_org": row.get("model_org"),
                    "folder": row.get("folder"),
                    "agent": agent,
                    "os_model": os_model,
                    "os_system": os_system,
                    "cost": row.get("cost"),
                    "instance_calls": row.get("instance_calls"),
                    "model_release_date": row.get("model_release_date"),
                    "logs": row.get("logs"),
                    "trajs": row.get("trajs"),
                    "source_status": "checked" if verified is True else "reported",
                }
                protocol = {
                    "harness": agent or "unspecified",
                    "scaffold": agent,
                    "subject_type": subject_type,
                    "leaderboard_variant": board_name,
                    "checked": verified,
                }
                candidates.append(
                    self.make_candidate(
                        run,
                        model_ref=model_ref,
                        benchmark_ref=benchmark_ref,
                        metric="resolved",
                        value=row.get("resolved", row.get("pass_rate")),
                        unit="percent",
                        raw_value=row.get("resolved", row.get("pass_rate")),
                        locator=(
                            f"leaderboards[{board_index}]={board_name};"
                            f"results[{row_index}]"
                        ),
                        rank=row.get("rank", row_index + 1),
                        verified=verified,
                        status="candidate",
                        evidence_level="A",
                        comparability="conditional",
                        protocol=protocol,
                        metadata=metadata,
                        quality_flags=flags,
                        observed_at=_date_only(row.get("date")),
                    )
                )
        return candidates


def _date_only(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None
