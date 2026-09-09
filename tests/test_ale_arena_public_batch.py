"""September 10 disclosures retain system, split and metric boundaries."""
from collections import Counter
from pathlib import Path
import unittest

from scripts.build_public_evidence import build_index


class AleArenaPublicBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.index = build_index(root, [root / "data/public/leaderboard_reports/daily-2026-09-10"],
                               generated_at="2026-09-09T17:05:00Z")
        cls.rows = cls.index["rows"]

    def test_publication_preserves_receipts_and_unverified_status(self):
        self.assertFalse(self.index["meta"]["errors"])
        self.assertFalse(self.index["_omittedRows"])
        self.assertEqual(Counter(r["sourceId"] for r in self.rows),
                         {"agents-last-exam": 168, "lmarena-hf-dataset": 74})
        for row in self.rows:
            self.assertEqual((row["status"], row["verified"], row["comparability"]),
                             ("reported", False, "conditional"))
            for field in ("sourceUrl", "sourceLocator", "payloadSha256", "retrievedAt", "unit"):
                self.assertTrue(row[field])

    def test_ale_is_a_versioned_system_with_separate_splits_and_metrics(self):
        rows = [r for r in self.rows if r["sourceId"] == "agents-last-exam"]
        self.assertEqual(Counter(r["modelRef"] for r in rows), {"gpt-6-astra": 144, "muse-spark-1-3": 24})
        self.assertEqual(Counter(r["metricId"] for r in rows), {"avg_score": 84, "pass_rate": 84})
        self.assertEqual(len({r["protocol"]["split"] for r in rows}), 12)
        for row in rows:
            self.assertEqual(row["benchmarkId"], "agents-last-exam")
            self.assertEqual(row["benchmarkVersionId"], "agents-last-exam@v1")
            self.assertEqual((row["subjectType"], row["harnessId"]), ("system", "codex"))
            self.assertIsNone(row["observedAt"])
            self.assertIsNone(row["publishedAt"])
            if row["modelRef"] == "muse-spark-1-3":
                self.assertIsNone(row["protocol"]["harness_variant"])

    def test_arena_metrics_and_source_dates_are_not_accuracy_or_retrieval(self):
        rows = [r for r in self.rows if r["sourceId"] == "lmarena-hf-dataset"]
        self.assertEqual(Counter(r["metricId"] for r in rows), {"ips": 29, "arena_score_bt": 45})
        for row in rows:
            self.assertEqual(row["observedAt"], "2026-09-08")
            self.assertEqual(row["retrievedAt"], "2026-09-09T17:01:04Z")
            self.assertTrue(row["protocol"]["harness"])


if __name__ == "__main__":
    unittest.main()
