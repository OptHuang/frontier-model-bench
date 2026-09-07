"""Keep the September 8 public batch's system and history boundaries explicit."""
from collections import Counter
from pathlib import Path
import unittest

from scripts.build_public_evidence import build_index


class DailyPublicReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.index = build_index(root, [root / "data/public/leaderboard_reports/daily-2026-09-08"],
                               generated_at="2026-09-07T17:05:18Z")
        cls.rows = cls.index["rows"]

    def test_selected_disclosures_keep_provenance_without_approval(self):
        self.assertFalse(self.index["meta"]["errors"])
        self.assertFalse(self.index["_omittedRows"])
        self.assertEqual(Counter(row["sourceId"] for row in self.rows),
                         {"src-ale-bench": 30, "lmarena-hf-dataset": 110,
                          "src-epoch-benchmark-hub": 9})
        for row in self.rows:
            self.assertEqual((row["status"], row["verified"]), ("reported", False))
            self.assertNotEqual(row["reviewStatus"], "approved")
            for key in ("sourceUrl", "sourceLocator", "retrievedAt", "payloadSha256", "unit"):
                self.assertTrue(row[key], key)

    def test_gpt6_ale_preserves_fixed_headline_and_other_budgets(self):
        rows = [row for row in self.rows if row["sourceId"] == "src-ale-bench"]
        headline = [row for row in rows if row["metricId"] == "performance"
                    and row["protocol"]["self_refine_iterations"] == 16
                    and row["protocol"]["view"] == "all"]
        self.assertEqual(len(headline), 1)
        self.assertEqual(headline[0]["value"], 3128.1)
        self.assertEqual({row["protocol"]["self_refine_iterations"] for row in rows}, {1, 2, 4, 8, 16})
        for row in rows:
            self.assertEqual(row["canonicalModelId"], "openai/gpt-6-astra@2026-09-03")
            self.assertEqual((row["subjectType"], row["harnessId"]), ("system", "ale-bench-self-refine"))
            self.assertEqual(row["protocol"]["reasoning_effort"], "max")
            self.assertIsNone(row["benchmarkVersionId"])
            self.assertIsNone(row["observedAt"])

    def test_epoch_agent_results_do_not_impersonate_other_benchmarks(self):
        rows = [row for row in self.rows if row["sourceId"] == "src-epoch-benchmark-hub"]
        self.assertEqual(Counter(row["benchmarkId"] for row in rows),
                         {"epoch-frontiermath_tier_4_v2": 4, "epoch-deepswe_external": 5})
        for row in rows:
            if row["benchmarkId"] == "epoch-deepswe_external":
                self.assertEqual((row["subjectType"], row["harnessId"]), ("system", "mini-swe-agent"))
                self.assertIsNone(row["observedAt"])
            else:
                self.assertEqual(row["benchmarkVersionId"], "frontiermath@v2-tier-4")
                self.assertIn(row["value"], (90.2, 97.6))


if __name__ == "__main__":
    unittest.main()
