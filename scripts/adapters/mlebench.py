"""Adapter for the public MLE-bench README leaderboard table.

The project intentionally pauses new submissions while revising fairness.  We
therefore preserve the README's published rows as conditional candidates and
emit one metric per complexity split (Lite/Medium/High/All).
"""

from __future__ import annotations

import re
from typing import Any

from .base import Adapter, AdapterRun, SourceSpec


class MLEBenchAdapter(Adapter):
    URL = "https://raw.githubusercontent.com/openai/mle-bench/main/README.md"

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="src-mle-bench",
            label="OpenAI · MLE-bench README leaderboard",
            kind="official_repository",
            url=self.URL,
            cadence="monthly",
            notes=(
                "Published README table; scores are system/agent candidates. "
                "The project currently pauses new submissions while fairness is reviewed."
            ),
        )

    @staticmethod
    def _number(value: str) -> float | None:
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value or "")
        return float(match.group(0)) if match else None

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        in_main = False
        headers: list[str] = []
        for line_no, line in enumerate(payload.decode("utf-8-sig").splitlines(), 1):
            if line.startswith("## Leaderboard"):
                in_main = True
                continue
            if in_main and line.startswith("### "):
                break
            if not in_main or not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not headers:
                headers = cells
                continue
            if all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            if len(cells) != len(headers) or not cells[0] or cells[0].lower() == "agent":
                continue
            row = dict(zip(headers, cells))
            agent = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", row.get("Agent", "")).strip()
            model = row.get("LLM(s) used", "").strip()
            date = row.get("Date")
            for label, column in (("lite", "Low == Lite (%)"), ("medium", "Medium (%)"), ("high", "High (%)"), ("all", "All (%)")):
                raw = row.get(column, "")
                value = self._number(raw)
                if value is None:
                    continue
                rows.append(
                    self.make_candidate(
                        run,
                        model_ref=model,
                        benchmark_ref="mle-bench",
                        metric=label,
                        value=value,
                        unit="percent",
                        raw_value=raw,
                        locator=f"README.md:row={line_no};column={column}",
                        status="candidate",
                        evidence_level="A",
                        comparability="conditional",
                        protocol={"subject_type": "system", "harness": agent, "split": label},
                        metadata={"agent": agent, "date": date, "all_columns": row},
                        observed_at=date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or "") else None,
                    )
                )
        return rows
