from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.maintenance_report import build_report, write_outputs


class MaintenanceReportTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="fmb-maintenance-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        catalog = directory / "data" / "catalog"
        observations = directory / "data" / "observations"
        public = directory / "data" / "public"
        catalog.mkdir(parents=True)
        observations.mkdir(parents=True)
        public.mkdir(parents=True)
        (catalog / "models.json").write_text(
            json.dumps(
                {
                    "models": [
                        {"id": "acme/frontier@1", "name": "Frontier 1", "status": "active"},
                        {"id": "acme/preview@1", "name": "Preview 1", "status": "preview"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (catalog / "benchmarks.json").write_text(
            json.dumps(
                [
                    {
                        "id": "toy-reasoning",
                        "name": "Toy reasoning",
                        "category": "reasoning",
                        "featured": True,
                        "source_ids": ["src-toy"],
                        "default_version_id": "toy-reasoning@v1",
                        "metrics": [{"id": "accuracy", "scale": {"min": 0, "max": 100}, "direction": "higher"}],
                    },
                    {
                        "id": "toy-agent",
                        "name": "Toy agent",
                        "category": "coding-agent",
                        "source_ids": ["src-toy"],
                        "default_version_id": "toy-agent@v1",
                        "metrics": [{"id": "resolved", "scale": {"min": 0, "max": 100}, "direction": "higher"}],
                    },
                ]
            ),
            encoding="utf-8",
        )
        (catalog / "sources.json").write_text(
            json.dumps(
                [
                    {
                        "id": "src-toy",
                        "label": "Toy source",
                        "kind": "test",
                        "url": "https://example.org/toy",
                        "staleness_after_days": 30,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (observations / "results.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "obs-direct",
                            "model_id": "acme/frontier@1",
                            "benchmark_id": "toy-reasoning",
                            "benchmark_version_id": "toy-reasoning@v1",
                            "metric_id": "accuracy",
                            "value": 80,
                            "subject": {"type": "model"},
                            "harness_id": "model-only",
                            "observed_at": "2026-08-20",
                            "status": "reported",
                            "source_ids": ["src-toy"],
                        }
                    ),
                    json.dumps(
                        {
                            "id": "obs-system-old",
                            "model_id": "acme/frontier@1",
                            "benchmark_id": "toy-agent",
                            "benchmark_version_id": "toy-agent@v1",
                            "metric_id": "resolved",
                            "value": 50,
                            "subject": {"type": "system", "system_id": "agent-1"},
                            "harness_id": "mini-swe-agent",
                            "observed_at": "2026-07-01",
                            "status": "reported",
                            "source_ids": ["src-toy"],
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (public / "evidence.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "pub-preview-reasoning",
                            "canonicalModelId": "acme/preview@1",
                            "benchmarkId": "toy-reasoning",
                            "benchmarkVersionId": "toy-reasoning@v1",
                            "metricId": "accuracy",
                            "value": 75,
                            "status": "reported",
                            "reviewStatus": "unreviewed",
                            "verificationStatus": "not_reproduced",
                            "matrixExcluded": False,
                            "sourceId": "src-toy",
                            "evidenceUrl": "https://example.org/toy#preview-reasoning",
                        }
                    ),
                    # Telemetry may be retained as evidence, but it must not
                    # make a benchmark score cell look publicly covered.
                    json.dumps(
                        {
                            "id": "pub-preview-agent-runtime",
                            "canonicalModelId": "acme/preview@1",
                            "benchmarkId": "toy-agent",
                            "benchmarkVersionId": "toy-agent@v1",
                            "metricId": "runtime-seconds",
                            "value": 12,
                            "status": "reported",
                            "reviewStatus": "unreviewed",
                            "matrixExcluded": True,
                            "sourceId": "src-toy",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return directory

    def test_missing_and_stale_candidates_are_separate(self) -> None:
        root = self.make_fixture()
        report = build_report(root, date(2026, 8, 27), False, 1, 0)
        candidates = report["candidates"]
        self.assertTrue(any(item["kind"] == "missing" and item["model_id"] == "acme/preview@1" for item in candidates))
        self.assertTrue(any(item["kind"] == "refresh" and item["observation_id"] == "obs-system-old" for item in candidates))
        self.assertEqual(report["health"]["network_checked"], False)
        self.assertEqual(report["health"]["coverage"]["featured_covered"], 1)

    def test_canonical_gaps_distinguish_public_reported_from_no_evidence(self) -> None:
        root = self.make_fixture()
        report = build_report(root, date(2026, 8, 27), False, 1, 0)
        coverage = report["health"]["coverage"]
        candidates = report["candidates"]

        # Canonical coverage is unchanged: both preview cells are still gaps.
        self.assertEqual(coverage["covered_cells"], 2)
        self.assertEqual(coverage["missing_cells"], 2)
        self.assertEqual(coverage["public_reported_awaiting_review_cells"], 1)
        self.assertEqual(coverage["no_mapped_public_evidence_cells"], 1)

        public_review = [item for item in candidates if item["kind"] == "public_reported"]
        no_evidence = [item for item in candidates if item["kind"] == "missing"]
        self.assertEqual(len(public_review), 1)
        self.assertEqual(public_review[0]["model_id"], "acme/preview@1")
        self.assertEqual(public_review[0]["benchmark_id"], "toy-reasoning")
        self.assertEqual(public_review[0]["public_evidence_ids"], ["pub-preview-reasoning"])
        self.assertEqual(len(no_evidence), 1)
        self.assertEqual(no_evidence[0]["benchmark_id"], "toy-agent")
        self.assertEqual(report["health"]["candidates"]["public_reported"], 1)
        self.assertEqual(report["health"]["candidates"]["missing"], 1)

    def test_write_outputs_is_self_contained(self) -> None:
        root = self.make_fixture()
        report = build_report(root, date(2026, 8, 27), False, 1, 0)
        output = root / "artifacts" / "maintenance"
        write_outputs(output, report)
        for filename in ("health.json", "candidates.json", "source-status.json", "summary.md"):
            self.assertTrue((output / filename).is_file(), filename)
        summary = (output / "summary.md").read_text(encoding="utf-8")
        self.assertIn("candidate", summary)
        self.assertIn("Public reported / awaiting canonical review：1", summary)
        self.assertIn("No mapped public evidence：1", summary)


if __name__ == "__main__":
    unittest.main()
