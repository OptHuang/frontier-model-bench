import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkProfileTests(unittest.TestCase):
    """Keep the directory's long-form profile layer complete and renderable."""

    @classmethod
    def setUpClass(cls):
        cls.benchmarks = json.loads((ROOT / "data/catalog/benchmarks.json").read_text())
        cls.profiles = json.loads((ROOT / "data/catalog/benchmark_profiles.json").read_text())

    def test_every_catalog_benchmark_has_a_profile(self):
        benchmark_ids = {row["id"] for row in self.benchmarks}
        profile_ids = {key for key in self.profiles if not key.startswith("_")}
        self.assertEqual(benchmark_ids, profile_ids)

    def test_profiles_have_required_reading_groups(self):
        required = {"task", "dataset", "protocol", "comparison", "source_locator"}
        for benchmark_id, profile in self.profiles.items():
            if benchmark_id.startswith("_"):
                continue
            self.assertTrue(required <= profile.keys(), benchmark_id)
            for group in ("task", "dataset", "protocol", "comparison"):
                self.assertIsInstance(profile[group], dict, benchmark_id)
                self.assertTrue(profile[group], benchmark_id)

    def test_promoted_public_slices_are_canonical_and_protocol_explicit(self):
        by_id = {row["id"]: row for row in self.benchmarks}
        expected_modes = {
            "livebench": "direct",
            "epoch-arc_agi_2_external": "unknown",
            "epoch-frontiermath_tier_4": "system",
            "epoch-bbh_external": "unknown",
            "helm-ifeval": "direct",
            "helm-math": "direct",
            "helm-mmlu": "direct",
            "helm-gsm8k": "direct",
            "swebench-lite": "system",
            "swebench-multilingual": "system",
            "swebench-multimodal": "system",
        }
        self.assertTrue(expected_modes.keys() <= by_id.keys())
        for benchmark_id, mode in expected_modes.items():
            self.assertEqual(by_id[benchmark_id]["evaluation_mode"], mode, benchmark_id)
            profile = self.profiles[benchmark_id]
            self.assertTrue(profile["comparison"].get("recommended"), benchmark_id)
            self.assertTrue(profile["comparison"].get("avoid"), benchmark_id)
            self.assertTrue(profile["source_locator"], benchmark_id)

        self.assertIn("ARC-AGI-2", by_id["epoch-arc_agi_2_external"]["name"])
        self.assertIn("Epoch external aggregation", by_id["epoch-arc_agi_2_external"]["name"])
        self.assertEqual(by_id["helm-ifeval"]["source_ids"], ["helm-capabilities"])
        self.assertEqual(by_id["helm-math"]["source_ids"], ["helm-lite"])
        self.assertEqual(by_id["swebench-lite"]["source_ids"], ["swebench-official"])


if __name__ == "__main__":
    unittest.main()
