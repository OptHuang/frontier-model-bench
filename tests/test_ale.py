from __future__ import annotations

import unittest
from pathlib import Path

from scripts.adapters import all_adapters
from scripts.adapters.ale import (
    ALEV1Adapter,
    ALELeaderboardAdapter,
    AgentsLastExamAdapter,
)
from scripts.adapters.base import AdapterRun


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ale_leaderboard.json"


class ALEAdapterTests(unittest.TestCase):
    def _parse(self, adapter: AgentsLastExamAdapter | None = None):
        adapter = adapter or AgentsLastExamAdapter()
        payload = FIXTURE.read_bytes()
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://ale-fixture",
            resolved_url="file://ale-fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload,
        )
        rows = adapter.parse_payload(payload, run)
        self.assertEqual(run.errors, [])
        return rows

    def test_aliases_and_registry(self):
        self.assertIs(ALELeaderboardAdapter, AgentsLastExamAdapter)
        self.assertIs(ALEV1Adapter, AgentsLastExamAdapter)
        registered = all_adapters()
        self.assertIn("agents-last-exam", registered)
        self.assertEqual(registered["agents-last-exam"].spec.url, AgentsLastExamAdapter.ENDPOINT)

    def test_candidate_keeps_track_and_all_run_details(self):
        rows = self._parse()
        self.assertEqual(len(rows), 6)
        row = next(item for item in rows if item["metric"] == "pass_rate")
        partial = next(item for item in rows if item["metric"] == "avg_score")
        self.assertEqual(row["status"], "candidate")
        self.assertEqual(row["benchmark_ref"], "agents-last-exam")
        self.assertEqual(row["benchmark_version_id"], "agents-last-exam@v1")
        self.assertEqual(row["metric"], "pass_rate")
        self.assertEqual(row["unit"], "percent")
        self.assertAlmostEqual(row["value"], 30.59210526315789)
        self.assertAlmostEqual(row["raw_value"], 0.3059210526315789)
        self.assertEqual(row["protocol"]["benchmark_version"], "ALE-v1")
        self.assertEqual(row["protocol"]["split"], "full")
        self.assertEqual(row["protocol"]["source_harness"], "codex")
        self.assertEqual(row["protocol"]["harness"], "codex")
        self.assertEqual(row["protocol"]["subject_type"], "system")
        self.assertEqual(row["metadata"]["runs"], 301)
        self.assertEqual(row["metadata"]["tasks"], 152)
        self.assertEqual(row["metadata"]["passes"], 93)
        self.assertAlmostEqual(row["metadata"]["avg_score"], 0.5361628463309976)
        self.assertEqual(row["metadata"]["totalCostUsd"], 771.62)
        self.assertEqual(row["metadata"]["totalDurationS"], 340729.6965)
        self.assertEqual(row["metadata"]["totalInputTokens"], 762936773.1667)
        self.assertEqual(row["metadata"]["totalOutputTokens"], 3798417.8333)
        self.assertEqual(row["metadata"]["costSource"], "db+list")
        self.assertEqual(row["source_flags"], ["official"])
        self.assertIn("rows[0]", row["source_locator"])
        self.assertEqual(partial["metadata"]["metric_role"], "secondary")
        self.assertEqual(partial["metric"], "avg_score")
        self.assertAlmostEqual(partial["value"], 53.61628463309977)
        self.assertAlmostEqual(partial["raw_value"], 0.5361628463309976)
        self.assertIn("split_specific", row["quality_flags"])
        self.assertIn("source:official", row["quality_flags"])
        self.assertEqual(row["mapping_status"], "unmatched")
        self.assertIsNone(row["canonical_model_id"])

    def test_snake_case_aliases_and_unknown_harness_are_safe(self):
        rows = self._parse()
        row = next(item for item in rows if item["protocol"]["split"] == "linux_only" and item["metric"] == "pass_rate")
        self.assertEqual(row["protocol"]["split"], "linux_only")
        self.assertEqual(row["protocol"]["source_harness"], "ale_claw")
        self.assertEqual(row["harness_id"], "agents-last-exam")
        self.assertEqual(row["metadata"]["runtime"], 4321)
        self.assertEqual(row["metadata"]["tokens"], 123456)
        self.assertEqual(row["metadata"]["cost"], 12.5)
        self.assertIn("unregistered_source_harness", row["quality_flags"])

    def test_split_filter_does_not_change_source_semantics(self):
        rows = self._parse(AgentsLastExamAdapter(split="full/last-exam"))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["protocol"]["split"], "full/last-exam")
            self.assertEqual(row["metadata"]["split_benchmark_ref"], "agents-last-exam-v1-full-last-exam")

    def test_bad_payload_reports_error_to_caller(self):
        adapter = AgentsLastExamAdapter()
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://bad",
            resolved_url="file://bad",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=b"{}",
        )
        with self.assertRaises(ValueError):
            adapter.parse_payload(b"{}", run)


if __name__ == "__main__":
    unittest.main()
