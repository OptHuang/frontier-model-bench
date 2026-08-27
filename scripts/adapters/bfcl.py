"""Adapter for the official Berkeley Function Calling Leaderboard CSV.

The BFCL page publishes a machine-readable ``data_overall.csv`` export.  It
contains both native function-calling (``FC``) and prompt-based rows, so a
row is not a model-only fact until its calling mode and evaluator protocol
have been reviewed.  This adapter therefore emits candidate facts only and
keeps the mode, benchmark commit, latency/cost, and all category metrics in
the candidate metadata.

The current public export is BFCL V4.  The evaluator commit is recorded in
the protocol instead of being inferred from the CSV URL; if the upstream
page changes it, a maintainer can update this constant and the catalog
version together.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from .base import Adapter, AdapterRun, SourceSpec, parse_number


class BFCLOfficialAdapter(Adapter):
    """Parse the official BFCL V4 overall-results CSV as candidates."""

    SOURCE_ID = "src-bfcl"
    CSV_URL = "https://gorilla.cs.berkeley.edu/data_overall.csv"
    LEADERBOARD_URL = "https://gorilla.cs.berkeley.edu/leaderboard"
    BENCHMARK_REF = "bfcl"
    BENCHMARK_VERSION_ID = "bfcl@v4"
    BENCHMARK_VERSION = "BFCL-V4"
    EVALUATOR_COMMIT = "f7cf735"
    EVALUATOR_COMMIT_URL = (
        "https://github.com/ShishirPatil/gorilla/commit/"
        "f7cf7359b7ac615a0b294831c5ba2bc95ee4a000"
    )

    # Columns represented by the candidate's primary value or by top-level
    # metadata.  Every remaining score-like column is retained as a
    # submetric below, so a future dashboard can expose category breakdowns
    # without another network fetch.
    _PRIMARY_COLUMNS = {
        "Rank",
        "Overall Acc",
        "Model",
        "Model Link",
        "Total Cost ($)",
        "Latency Mean (s)",
        "Latency Standard Deviation (s)",
        "Latency 95th Percentile (s)",
        "Organization",
        "License",
    }

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id=self.SOURCE_ID,
            label="Berkeley Function Calling Leaderboard · official V4 CSV",
            kind="official_artifact",
            url=self.CSV_URL,
            cadence="weekly",
            notes=(
                "Official BFCL V4 overall CSV. Rows mix native FC and prompt "
                "workarounds; retain calling mode, evaluator commit, latency, "
                "cost, and category metrics as candidate provenance."
            ),
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        """Parse rows without silently turning N/A values into zero."""

        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("expected a CSV header")
        fieldnames = [str(field).strip() for field in reader.fieldnames if field is not None]
        required = {"Model", "Overall Acc"}
        missing = sorted(required - set(fieldnames))
        if missing:
            raise ValueError("missing required BFCL columns: " + ", ".join(missing))

        # Put immutable evaluator context in the manifest as well as each
        # candidate; this makes a source-level snapshot self-describing even
        # when a reviewer only opens ``manifest.json``.
        run.metadata.setdefault("benchmark_ref", self.BENCHMARK_REF)
        run.metadata.setdefault("benchmark_version", self.BENCHMARK_VERSION)
        run.metadata.setdefault("benchmark_version_id", self.BENCHMARK_VERSION_ID)
        run.metadata.setdefault("evaluator_commit", self.EVALUATOR_COMMIT)
        run.metadata.setdefault("leaderboard_url", self.LEADERBOARD_URL)

        candidates: list[dict[str, Any]] = []
        for row_index, raw_row in enumerate(reader):
            # DictReader uses the original header spelling; normalize header
            # whitespace while preserving each source value verbatim.
            row = {
                str(key).strip(): value
                for key, value in raw_row.items()
                if key is not None
            }
            source_model = _text(row.get("Model"))
            if not source_model:
                run.warnings.append(f"CSV row {row_index}: missing Model; skipped")
                continue

            model_ref, mode, mode_label, variant = _split_model_label(source_model)
            accuracy_raw = row.get("Overall Acc")
            accuracy = _percent(accuracy_raw)
            rank = _integer(row.get("Rank"))
            model_link = _text(row.get("Model Link"))
            cost = _number(row.get("Total Cost ($)"))
            latency_mean = _number(row.get("Latency Mean (s)"))
            latency_std = _number(row.get("Latency Standard Deviation (s)"))
            latency_p95 = _number(row.get("Latency 95th Percentile (s)"))

            submetrics: dict[str, dict[str, Any]] = {}
            submetrics_raw: dict[str, Any] = {}
            missing_submetrics = 0
            for column in fieldnames:
                if column in self._PRIMARY_COLUMNS:
                    continue
                raw_value = row.get(column)
                parsed = _submetric_value(column, raw_value)
                if parsed is None:
                    missing_submetrics += 1
                submetrics[column] = {"value": parsed, "raw": raw_value}
                submetrics_raw[column] = raw_value

            quality_flags = ["official_csv", "benchmark_v4", "mode_specific"]
            if mode == "unspecified":
                quality_flags.append("missing_calling_mode")
            if accuracy is None:
                quality_flags.append("missing_accuracy")
            if cost is None:
                quality_flags.append("missing_cost")
            if latency_mean is None:
                quality_flags.append("missing_latency_mean")
            if missing_submetrics:
                quality_flags.append("missing_submetrics")
            # The CSV does not carry a published observation date.  Retrieval
            # time remains in the run manifest and is deliberately not used as
            # an observation date.
            quality_flags.append("missing_source_date")

            protocol = {
                "harness": "bfcl-eval",
                "evaluator": "bfcl",
                "benchmark_version": self.BENCHMARK_VERSION,
                "benchmark_version_id": self.BENCHMARK_VERSION_ID,
                "commit": self.EVALUATOR_COMMIT,
                "commit_url": self.EVALUATOR_COMMIT_URL,
                "evaluator_commit": self.EVALUATOR_COMMIT,
                "leaderboard_url": self.LEADERBOARD_URL,
                "calling_mode": mode,
                "calling_mode_label": mode_label,
                "variant": variant,
                # Even a native FC row is a model + tool/evaluator protocol;
                # keep it in System Runs so FC/Prompt and V4 agentic modes
                # cannot be mistaken for a bare model score.
                "subject_type": "system",
            }
            metadata = {
                "source_model": source_model,
                "leaderboard_url": self.LEADERBOARD_URL,
                "model": model_ref,
                "model_link": model_link,
                "calling_mode": mode,
                "calling_mode_label": mode_label,
                "variant": variant,
                "rank": rank,
                "organization": _text(row.get("Organization")),
                "license": _text(row.get("License")),
                "overall_accuracy": accuracy_raw,
                "overall_accuracy_percent": accuracy,
                "total_cost_usd": cost,
                "total_cost_raw": row.get("Total Cost ($)"),
                "latency_mean_s": latency_mean,
                "latency_mean_raw": row.get("Latency Mean (s)"),
                "latency_std_s": latency_std,
                "latency_std_raw": row.get("Latency Standard Deviation (s)"),
                "latency_p95_s": latency_p95,
                "latency_p95_raw": row.get("Latency 95th Percentile (s)"),
                "submetrics": submetrics,
                "submetrics_raw": submetrics_raw,
                "source_status": "official_published_csv",
                "benchmark_version": self.BENCHMARK_VERSION,
                "benchmark_version_id": self.BENCHMARK_VERSION_ID,
                "evaluator_commit": self.EVALUATOR_COMMIT,
                "source_row_index": row_index,
            }
            locator = (
                f"csv-row={row_index};rank={rank if rank is not None else 'unknown'};"
                f"model={source_model};mode={mode_label or 'unknown'}"
            )
            candidate = self.make_candidate(
                run,
                model_ref=model_ref,
                benchmark_ref=self.BENCHMARK_REF,
                metric="accuracy",
                value=accuracy,
                unit="percent",
                raw_value=accuracy_raw,
                locator=locator,
                rank=rank,
                verified=None,
                status="candidate",
                evidence_level="A",
                comparability="conditional",
                protocol=protocol,
                metadata=metadata,
                quality_flags=quality_flags,
                observed_at=None,
            )
            candidate["benchmark_version_id"] = self.BENCHMARK_VERSION_ID
            candidate["harness_id"] = "bfcl-eval"
            candidate["subject_type"] = "system"
            candidate["source_model"] = source_model
            candidate["source_flags"] = ["official_csv", mode]
            candidates.append(candidate)
        return candidates


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    number, _ = parse_number(value)
    return number


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else None


def _percent(value: Any) -> float | None:
    """Normalize a percent cell to the catalog's 0--100 scale."""

    number, raw = parse_number(value)
    if number is None:
        return None
    raw_text = str(raw or "")
    if "%" not in raw_text and -1 <= number <= 1:
        return number * 100
    return number


def _submetric_value(column: str, value: Any) -> float | None:
    """Normalize a BFCL submetric while respecting non-percent deltas.

    Most category columns are percentages in the export.  Format-sensitivity
    columns are absolute deltas/standard deviations and must remain on their
    native numeric scale (for example ``0.5`` is not ``50%``).
    """

    if column.casefold().startswith("format sensitivity"):
        return _number(value)
    return _percent(value)


_MODE_RE = re.compile(r"^(?P<base>.*?)\s*\((?P<label>[^()]*)\)\s*$")


def _split_model_label(value: str) -> tuple[str, str, str | None, str | None]:
    """Return canonical-ish model text, normalized mode, label, and variant."""

    match = _MODE_RE.match(value.strip())
    if not match:
        return value.strip(), "unspecified", None, None
    base = match.group("base").strip() or value.strip()
    label = match.group("label").strip() or None
    lowered = (label or "").casefold()
    if "prompt" in lowered:
        mode = "prompt"
    elif re.search(r"\bfc\b|function\s*call", lowered):
        mode = "native_fc"
    else:
        mode = "unspecified"
    variant = None
    if label:
        variant_text = re.sub(r"\b(?:fc|prompt)\b", "", label, flags=re.IGNORECASE)
        variant_text = variant_text.strip(" +-_/,")
        variant = variant_text or None
    return base, mode, label, variant


BFCLAdapter = BFCLOfficialAdapter


def build_bfcl_adapters() -> dict[str, BFCLOfficialAdapter]:
    adapter = BFCLOfficialAdapter()
    return {adapter.spec.id: adapter}


__all__ = ["BFCLOfficialAdapter", "BFCLAdapter", "build_bfcl_adapters"]
