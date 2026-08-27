"""Candidate adapter for Aider's published Polyglot YAML leaderboard.

The Aider repository keeps the leaderboard as a small, versioned YAML list.
This parser intentionally supports only the scalar/list shape used by that
file, avoiding a PyYAML dependency in the maintenance job.  Every row is a
source-reported candidate; no canonical observations are changed.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from .base import Adapter, AdapterRun, SourceSpec


class AiderPolyglotAdapter(Adapter):
    URL = "https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml"

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="src-aider-polyglot",
            label="Aider · Polyglot YAML leaderboard",
            kind="official_repository",
            url=self.URL,
            cadence="weekly",
            notes=(
                "Official repository YAML; pass rates are published system results. "
                "Retain edit format, Aider version and date; candidates are not reproduced here."
            ),
        )

    @staticmethod
    def _scalar(value: str) -> Any:
        value = value.strip()
        if not value:
            return None
        if value in {"null", "Null", "NULL", "~"}:
            return None
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value.strip("'\"")

    @classmethod
    def _rows(cls, payload: bytes) -> list[tuple[int, dict[str, Any]]]:
        rows: list[tuple[int, dict[str, Any]]] = []
        current: dict[str, Any] | None = None
        start = 0
        for line_no, raw in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.match(r"^\s*-\s*([^:]+):\s*(.*)$", line)
            if match:
                if current is not None:
                    rows.append((start, current))
                current = {match.group(1).strip(): cls._scalar(match.group(2))}
                start = line_no
                continue
            match = re.match(r"^\s+([^:#][^:]*):\s*(.*)$", line)
            if match and current is not None:
                current[match.group(1).strip()] = cls._scalar(match.group(2))
        if current is not None:
            rows.append((start, current))
        return rows

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for row_no, row in self._rows(payload):
            model = row.get("model")
            score = row.get("pass_rate_1")
            if not model:
                run.warnings.append(f"YAML row {row_no}: missing model; skipped")
                continue
            if score is None:
                run.warnings.append(f"YAML row {row_no}: missing pass_rate_1; skipped")
                continue
            date = row.get("date")
            candidates.append(
                self.make_candidate(
                    run,
                    model_ref=model,
                    benchmark_ref="aider-polyglot",
                    metric="pass_rate_1",
                    value=score,
                    unit="percent",
                    raw_value=score,
                    locator=f"yaml-row={row_no};dirname={row.get('dirname')}",
                    status="candidate",
                    evidence_level="A",
                    comparability="conditional",
                    protocol={
                        "subject_type": "system",
                        "harness": "aider",
                        "edit_format": row.get("edit_format"),
                        "command": row.get("command"),
                        "test_cases": row.get("test_cases"),
                    },
                    metadata={
                        "date": date,
                        "aider_version": row.get("versions"),
                        "pass_rate_2": row.get("pass_rate_2"),
                        "pass_num_1": row.get("pass_num_1"),
                        "pass_num_2": row.get("pass_num_2"),
                        "dirname": row.get("dirname"),
                    },
                    observed_at=date if isinstance(date, str) else None,
                )
            )
        return candidates
