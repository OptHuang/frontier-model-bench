import io
import unittest
import zipfile

from scripts.adapters.base import AdapterRun
from scripts.adapters.epoch import EpochBenchmarkAdapter


class EpochFocusTests(unittest.TestCase):
    def parse(self, files):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            for name, contents in files.items():
                archive.writestr(name, contents)
        run = AdapterRun("src-epoch-benchmark-hub", EpochBenchmarkAdapter.URL,
                         EpochBenchmarkAdapter.URL, "2026-09-06T00:00:00Z", 200,
                         payload=payload.getvalue())
        return EpochBenchmarkAdapter().parse_payload(run.payload, run)

    def test_frontiermath_files_keep_separate_ids_and_explicit_versions(self):
        header = "Model version,mean_score,Release date\ngpt-5.6-sol_max,0.8,2026-07-09\n"
        files = ["frontiermath", "frontiermath_tier_4", "frontiermath_tiers_1_3_v2", "frontiermath_tier_4_v2"]
        rows = self.parse({f"{name}.csv": header for name in files})
        actual = {row["benchmark_ref"]: row["protocol"]["benchmark_version_id"] for row in rows}
        self.assertEqual(actual, {
            "frontiermath": "frontiermath@t1-t3",
            "epoch-frontiermath_tier_4": "epoch-frontiermath_tier_4@rolling",
            "epoch-frontiermath_tiers_1_3_v2": "frontiermath@v2-t1-t3",
            "epoch-frontiermath_tier_4_v2": "frontiermath@v2-tier-4",
        })
        self.assertTrue(all(row["raw_value"] == "0.8" for row in rows))
        self.assertTrue(all(row["observed_at"] is None for row in rows))
        self.assertTrue(all(row["metadata"]["model_release_date"] == "2026-07-09" for row in rows))
        self.assertTrue(all("release_date" not in row["metadata"] for row in rows))

    def test_started_at_and_viewer_are_preserved_without_using_model_release_date(self):
        rows = self.parse({"frontiermath_tiers_1_3_v2.csv":
            "Model version,mean_score,Release date,Started at,Log viewer,Logs,Source\n"
            "gpt-5.6-sol_max,0.8,2026-07-09,2026-07-10T02:45:09Z,https://logs.epoch.ai/viewer.html,https://logs.epoch.ai/run.eval,https://epoch.ai/benchmarks/frontiermath\n"})
        row = rows[0]
        self.assertEqual(row["observed_at"], "2026-07-10")
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["metadata"]["started_at"], "2026-07-10T02:45:09Z")
        self.assertEqual(row["metadata"]["source_link"], "https://logs.epoch.ai/viewer.html")
        self.assertEqual(row["metadata"]["source"], "https://epoch.ai/benchmarks/frontiermath")
        self.assertEqual(row["metadata"]["logs"], "https://logs.epoch.ai/run.eval")

    def test_scicode_fraction_source_and_fallback_configuration_survive(self):
        rows = self.parse({"scicode_external.csv":
            "Model version,Score,AA model slug,Name,Release date,Source\n"
            "claude-fable-5_max,0.601851851851852,claude-fable-5,Fable 5 Opus 4.8 Fallback,2026-06-09,https://artificialanalysis.ai/evaluations/scicode\n"})
        row = rows[0]
        self.assertEqual(row["benchmark_ref"], "epoch-scicode_external")
        self.assertEqual(row["unit"], "fraction")
        self.assertEqual(row["value"], 0.601851851851852)
        self.assertEqual(row["raw_value"], "0.601851851851852")
        self.assertEqual(row["metadata"]["aa_model_slug"], "claude-fable-5")
        self.assertIn("Opus 4.8 Fallback", row["metadata"]["source_model_name"])
        self.assertEqual(row["metadata"]["source_link"], "https://artificialanalysis.ai/evaluations/scicode")
        self.assertIsNone(row["observed_at"])

    def test_report_update_date_is_not_an_evaluation_date(self):
        row = self.parse({"proofbench_external.csv":
            "Model version,Accuracy,Reasoning effort,Last updated,Source\n"
            "gpt-5.6-sol_max,0.83,max,2026-08-18,https://www.vals.ai/benchmarks/proof_bench\n"})[0]
        self.assertIsNone(row["observed_at"])
        self.assertEqual(row["published_at"], "2026-08-18")
        self.assertEqual(row["protocol"]["reasoning_effort"], "max")
        self.assertEqual(row["protocol"]["subject_type"], "system")
        self.assertEqual(row["protocol"]["harness"], "Vals ProofBench")
        self.assertEqual(row["protocol"]["harness_id"], "vals-proofbench")
        self.assertIsNone(row["protocol"]["benchmark_version_id"])


if __name__ == "__main__":
    unittest.main()
