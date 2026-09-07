"""Regression checks for the versioned September 7 public disclosure input."""

import unittest
from pathlib import Path

from scripts.build_public_evidence import build_index


class EpochScienceReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        directory = root / "data/public/leaderboard_reports/epoch-science-2026-09-07"
        cls.index = build_index(root, [directory], generated_at="2026-09-07T01:16:36Z")
        cls.rows = cls.index["rows"]

    def test_exact_batch_keeps_all_efforts_and_original_units(self):
        self.assertFalse(self.index["meta"]["errors"])
        self.assertEqual(len(self.rows), 11)
        self.assertFalse(self.index["_omittedRows"])
        expected = {
            "epoch-critpt_external": ("percent", {
                "low": 26.285714285714302, "medium": 29.1428571428571,
                "high": 28.857142857142897, "xhigh": 31.4285714285714,
                "max": 31.7142857142857,
            }),
            "epoch-scicode_external": ("fraction", {
                "low": 0.540509259259259, "medium": 0.541666666666667,
                "high": 0.554398148148148, "xhigh": 0.556712962962963,
                "max": 0.564814814814815,
            }),
        }
        for benchmark, (unit, scores) in expected.items():
            rows = [row for row in self.rows if row["benchmarkId"] == benchmark]
            self.assertEqual({row["modelRef"].rsplit("_", 1)[1]: row["value"] for row in rows}, scores)
            for row in rows:
                self.assertEqual(row["canonicalModelId"], "openai/gpt-6-astra@2026-09-03")
                self.assertEqual(row["unit"], unit)
        hle = [row for row in self.rows if row["benchmarkId"] == "hle"]
        self.assertEqual(len(hle), 1)
        self.assertEqual(hle[0]["canonicalModelId"], "anthropic/claude-fable-5.1@2026-09-01")
        self.assertEqual((hle[0]["modelRef"], hle[0]["value"], hle[0]["unit"]),
                         ("claude-fable-5-1_xhigh", 46.5, "percent"))
        self.assertIn("heuristic_model_mapping", hle[0]["qualityFlags"])

    def test_publication_does_not_imply_verification_or_invent_dates(self):
        for row in self.rows:
            self.assertEqual((row["status"], row["verified"], row["comparability"]),
                             ("reported", False, "conditional"))
            self.assertEqual(row["reviewStatus"], "unreviewed")
            self.assertIsNone(row["benchmarkVersionId"])
            self.assertIsNone(row["observedAt"])
            self.assertIsNone(row["publishedAt"])
            self.assertEqual(row["protocol"], {"harness": None, "subject_type": "model"})
            self.assertEqual(row["retrievedAt"], "2026-09-06T17:01:56Z")
            self.assertIn("missing_evaluation_date", row["qualityFlags"])

    def test_source_receipt_and_downstream_links_survive_normalization(self):
        for row in self.rows:
            self.assertEqual(row["sourceUrl"], "https://epoch.ai/data/benchmark_data.zip")
            self.assertEqual(row["payloadSha256"],
                             "ca1e2be0e7e94f4b40331e4e1083f0d3ac04cb47912776668eb4b76653909d95")
            self.assertRegex(row["sourceLocator"], r"^(critpt|scicode|hle)_external\.csv:row=\d+;column=(Score|Accuracy)$")
            metadata = row["sourceRow"]["metadata"]
            if row["benchmarkId"] == "epoch-scicode_external":
                self.assertEqual(metadata["source_link"], "https://artificialanalysis.ai/evaluations/scicode")
            else:
                self.assertIsNone(metadata["source_link"])


if __name__ == "__main__":
    unittest.main()
