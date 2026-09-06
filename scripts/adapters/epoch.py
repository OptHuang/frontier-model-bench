"""Adapter for Epoch AI's openly downloadable benchmark snapshot.

Epoch publishes a small ZIP of CSV tables with model scores and provenance.
The files are released under CC BY (with original licences retained for some
external tables), so this adapter keeps the source URL, CSV row and original
value in candidate evidence.  It never writes canonical observations.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from typing import Any

from .base import Adapter, AdapterRun, SourceSpec, parse_number


class EpochBenchmarkAdapter(Adapter):
    URL = "https://epoch.ai/data/benchmark_data.zip"

    # Only aliases that are unambiguous and already represented in our catalog
    # are normalised.  Other tables remain visible as ``epoch-*`` slices.
    BENCHMARK_ALIASES = {
        "gpqa_diamond": "gpqa-diamond",
        "swe_bench_verified": "swebench-verified",
        "frontiermath": "frontiermath",
        "simpleqa_verified": "simpleqa",
        "aider_polyglot_external": "aider-polyglot",
        "live_bench_external": "livebench",
        "hle_external": "hle",
        "os_world_external": "osworld",
    }

    # A model release date is not a benchmark revision. Keep the v2 tables
    # separate from the legacy benchmark IDs and bind versions by filename.
    FILE_VERSIONS = {
        "frontiermath": "frontiermath@t1-t3",
        "frontiermath_tier_4": "epoch-frontiermath_tier_4@rolling",
        "frontiermath_tiers_1_3_v2": "frontiermath@v2-t1-t3",
        "frontiermath_tier_4_v2": "frontiermath@v2-tier-4",
    }

    # The first numeric column is the headline metric shown by Epoch.  The
    # other columns are useful context but are intentionally not fanned out
    # into hundreds of synthetic metrics here.
    SCORE_COLUMNS = (
        "mean_score", "Percent correct", "Accuracy", "Score", "Overall score",
        "Overall", "Global average", "Main score", "Arena Score", "Performance",
        "Pass@1", "Pass@1 score", "ECI Score", "Win Rate (%)", "Average score",
        "Average", "EM", "Correct", "Challenge score", "Binary accuracy",
    )
    RANK_COLUMNS = ("Implementation rank", "Rank")
    # These benchmark exports are known to publish percentage points even
    # when Epoch names the column simply ``Score`` or ``Global average``.
    KNOWN_PERCENT_BENCHMARKS = {
        "gpqa-diamond", "frontiermath", "simpleqa", "swebench-verified",
        "osworld", "livebench", "aider-polyglot",
    }

    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="src-epoch-benchmark-hub",
            label="Epoch AI · Benchmarking Hub downloadable snapshot",
            kind="official_artifact",
            url=self.URL,
            cadence="weekly",
            parser_version="epoch@0.2.0",
            notes=(
                "Public CSV ZIP under CC BY; some tables retain original licences. "
                "Rows are external/provider or Epoch reports and are not reproduced here."
            ),
        )

    @classmethod
    def _benchmark_ref(cls, name: str) -> str:
        stem = re.sub(r"\.csv$", "", name.rsplit("/", 1)[-1])
        return cls.BENCHMARK_ALIASES.get(stem, f"epoch-{stem}")

    @classmethod
    def _score_column(cls, fields: list[str]) -> str | None:
        for name in cls.SCORE_COLUMNS:
            if name in fields:
                return name
        # A rank-only table is still useful evidence, but it must be labelled
        # as rank (and never be mistaken for a higher-is-better score).
        for name in cls.RANK_COLUMNS:
            if name in fields:
                return name
        # A few future files use a single obvious numeric score column.  Use
        # word boundaries here: a substring search for ``em`` accidentally
        # selected ``Implementation rank`` in FrontiersWE as a score column.
        for name in fields:
            low = name.lower()
            if any(token in low for token in ("rank", "cost", "latency", "time", "token", "flop", "parameter", "horizon")):
                continue
            if re.search(r"(?:^|[^a-z])(?:score|accuracy|correct|pass@\d+|em|progress)(?:$|[^a-z])", low):
                return name
        return None

    @staticmethod
    def _score_value(number: float, column: str, benchmark_ref: str) -> tuple[float, str, list[str]]:
        """Make units explicit without pretending every Epoch column is %.

        Epoch's ZIP combines accuracies, fractions, Elo-like ratings, ranks,
        and benchmark-specific raw scores. Accuracy/progress/pass-rate
        columns are displayed in percentage points; ambiguous ``Score``
        columns stay as fractions or neutral scores. The original string is
        always retained as ``raw_value`` by the caller.
        """

        low = f"{benchmark_ref} {column}".casefold()
        if benchmark_ref == "epoch-scicode_external" and column == "Score":
            # AA publishes subproblem accuracy as a fraction in this export.
            # Keep 0.56 as a fraction, never label it as 0.56 percent.
            if 0 <= number <= 1:
                return number, "fraction", ["source_fraction_accuracy"]
            return number, "score", ["unexpected_scicode_scale", "unit_unverified"]
        if "rank" in low:
            return number, "rank", ["unit_inferred_from_column"]
        if "arena score" in low or "elo" in low or "rating" in low:
            return number, "elo", ["unit_inferred_from_column"]
        if "eci score" in low:
            return number, "index", ["unit_inferred_from_column"]
        # Benchmark-specific objective scales are kept neutral until a
        # registry entry defines their direction and scale.
        if any(token in low for token in (
            "ale_bench", "vending_bench", "geobench", "algotune",
            "metr_time_horizons", "token score", "implementation rank",
        )):
            return number, "score", ["unit_unverified"]

        percent_hint = benchmark_ref in EpochBenchmarkAdapter.KNOWN_PERCENT_BENCHMARKS or any(token in low for token in (
            "accuracy", "correct", "pass@", "pass rate", "win rate",
            "progress", "percent", "mean_score", "mean score",
            "overall score", "overall accuracy", "challenge score",
            "average score", "global average", "% score", "em",
        ))
        # Brier/RPS-style pooled scores and generic score columns are not
        # silently relabelled as percentages.
        if "pooled score" in low or (column.casefold().strip() in {"score", "score (avg@5)"} and not percent_hint):
            if 0 <= number <= 1:
                return number, "fraction", ["unit_unverified"]
            return number, "score", ["unit_unverified"]
        if percent_hint:
            if 0 <= number <= 1:
                return number * 100, "percent", ["fraction_scaled_to_percent"]
            return number, "percent", ["unit_inferred_from_column"]
        if 0 <= number <= 1:
            return number, "fraction", ["unit_unverified"]
        return number, "score", ["unit_unverified"]

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile as exc:
            run.errors.append(f"invalid Epoch ZIP: {exc}")
            return candidates
        for member in sorted(archive.namelist()):
            if not member.lower().endswith(".csv") or member.startswith("additional_eci_data/"):
                continue
            text = archive.read(member).decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            fields = list(reader.fieldnames or [])
            model_key = "Model version" if "Model version" in fields else None
            score_key = self._score_column(fields)
            if not model_key or not score_key:
                run.warnings.append(f"{member}: no model/score column; skipped")
                continue
            benchmark_ref = self._benchmark_ref(member)
            stem = re.sub(r"\.csv$", "", member.rsplit("/", 1)[-1])
            benchmark_version_id = self.FILE_VERSIONS.get(stem)
            for row_no, row in enumerate(reader, 2):
                model = (row.get(model_key) or "").strip()
                number, raw = parse_number(row.get(score_key))
                if not model or number is None:
                    continue
                value, unit, unit_flags = self._score_value(number, score_key, benchmark_ref)
                subject_type = "system" if (row.get("Agent") or row.get("Harness")) else "model"
                harness = (row.get("Agent") or row.get("Harness") or "").strip() or None
                observed = (row.get("Date of evaluation") or row.get("Run date") or
                            row.get("Started at") or "").strip() or None
                published = (row.get("Last updated") or row.get("Date") or "").strip() or None
                protocol = {"subject_type": subject_type, "harness": harness}
                if stem == "proofbench_external":
                    protocol.update({
                        "subject_type": "system",
                        "harness": "Vals ProofBench",
                        "harness_id": "vals-proofbench",
                        "benchmark_version_id": None,
                        "setup_url": "https://www.vals.ai/benchmarks/proof_bench",
                    })
                if benchmark_version_id:
                    protocol["benchmark_version_id"] = benchmark_version_id
                effort = (row.get("Reasoning effort") or "").strip()
                if effort:
                    protocol["reasoning_effort"] = effort
                if not observed:
                    unit_flags.append("missing_evaluation_date")
                source_link = (row.get("Log viewer") or row.get("Source link") or
                               row.get("Source Link") or row.get("Source") or "").strip() or None
                candidate = self.make_candidate(
                        run,
                        model_ref=model,
                        benchmark_ref=benchmark_ref,
                        metric=score_key,
                        value=value,
                        unit=unit,
                        raw_value=raw,
                        locator=f"{member}:row={row_no};column={score_key}",
                        status="candidate",
                        evidence_level="A",
                        comparability="conditional",
                        protocol=protocol,
                        metadata={
                            "epoch_file": member,
                            "organization": row.get("Organization"),
                            "model_release_date": row.get("Release date"),
                            "source_link": source_link,
                            "source": row.get("Source"),
                            "log_viewer": row.get("Log viewer"),
                            "logs": row.get("Logs"),
                            "started_at": row.get("Started at"),
                            "aa_model_slug": row.get("AA model slug"),
                            "source_model_name": row.get("Name"),
                            "notes": row.get("Notes") or row.get("Notes (details)"),
                        },
                        quality_flags=unit_flags,
                        observed_at=observed[:10] if observed else None,
                )
                candidate["published_at"] = published[:10] if published else None
                candidates.append(candidate)
        run.metadata["csv_files"] = len([n for n in archive.namelist() if n.lower().endswith(".csv")])
        return candidates
