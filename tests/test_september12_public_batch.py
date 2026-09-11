"""Focused math/science and ALE disclosures keep their original boundaries."""
from collections import Counter
from pathlib import Path
import unittest

from scripts.build_public_evidence import build_index


class September12PublicBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.index = build_index(root, [root / "data/public/leaderboard_reports/daily-2026-09-12"],
                               generated_at="2026-09-11T17:01:36Z")
        cls.rows = cls.index["rows"]

    def test_receipts_and_history_only_attribution_changes(self):
        self.assertFalse(self.index["meta"]["errors"])
        self.assertFalse(self.index["_omittedRows"])
        self.assertEqual(len(self.rows), 51)
        self.assertNotIn("gpt-6-astra", {r["modelRef"] for r in self.rows})
        for row in self.rows:
            self.assertEqual((row["status"], row["verified"], row["comparability"]),
                             ("reported", False, "conditional"))
            for field in ("sourceUrl", "sourceLocator", "payloadSha256", "retrievedAt", "unit"):
                self.assertTrue(row[field])

    def test_muse_preserves_effort_split_and_uncertainty(self):
        rows = [r for r in self.rows if r["sourceId"] == "agents-last-exam"]
        self.assertEqual(len(rows), 48)
        self.assertEqual(Counter(r["protocol"]["harness_variant"] for r in rows),
                         {"reasoning-max": 24, "reasoning-xhigh": 24})
        self.assertEqual(len({r["protocol"]["split"] for r in rows}), 12)
        self.assertEqual(Counter(r["metricId"] for r in rows), {"avg_score": 24, "pass_rate": 24})
        for row in rows:
            self.assertEqual(row["benchmarkVersionId"], "agents-last-exam@v1")
            self.assertEqual((row["subjectType"], row["harnessId"]), ("system", "codex"))
            self.assertEqual(row["modelRef"], "muse-spark-1-3")
            self.assertEqual(row["mappingStatus"], "heuristic_alias")
            self.assertIsNone(row["observedAt"])
            self.assertIsNone(row["publishedAt"])

    def test_gemini_math_versions_and_fraction_conversion(self):
        rows = [r for r in self.rows if r["sourceId"] == "src-epoch-benchmark-hub"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["benchmarkVersionId"] for r in rows},
                         {"frontiermath@v2-tier-4", "frontiermath@v2-t1-t3", None})
        for row in rows:
            self.assertEqual(row["modelRef"], "gemini-3.8-flash_high")
            self.assertEqual(row["canonicalModelId"], "google/gemini-3.8-flash@2026-09-02")
            self.assertAlmostEqual(row["value"], float(row["rawValue"]) * 100)
            self.assertEqual(row["unit"], "percent")
            self.assertEqual(row["observedAt"], "2026-09-02")
            self.assertIsNone(row["harnessId"])
            self.assertIsNone(row["publishedAt"])


if __name__ == "__main__":
    unittest.main()
