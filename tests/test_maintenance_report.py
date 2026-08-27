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
        catalog.mkdir(parents=True)
        observations.mkdir(parents=True)
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
        return directory

    def test_missing_and_stale_candidates_are_separate(self) -> None:
        root = self.make_fixture()
        report = build_report(root, date(2026, 8, 27), False, 1, 0)
        candidates = report["candidates"]
        self.assertTrue(any(item["kind"] == "missing" and item["model_id"] == "acme/preview@1" for item in candidates))
        self.assertTrue(any(item["kind"] == "refresh" and item["observation_id"] == "obs-system-old" for item in candidates))
        self.assertEqual(report["health"]["network_checked"], False)
        self.assertEqual(report["health"]["coverage"]["featured_covered"], 1)

    def test_write_outputs_is_self_contained(self) -> None:
        root = self.make_fixture()
        report = build_report(root, date(2026, 8, 27), False, 1, 0)
        output = root / "artifacts" / "maintenance"
        write_outputs(output, report)
        for filename in ("health.json", "candidates.json", "source-status.json", "summary.md"):
            self.assertTrue((output / filename).is_file(), filename)
        self.assertIn("candidate", (output / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
