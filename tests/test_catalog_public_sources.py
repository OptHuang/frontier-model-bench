import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicBenchmarkCatalogTests(unittest.TestCase):
    def test_high_value_catalog_only_sources_are_explicitly_disabled(self):
        sources = json.loads((ROOT / "data/catalog/sources.json").read_text())
        by_id = {row["id"]: row for row in sources}
        expected = {
            "src-browsecomp",
            "src-androidworld",
        }
        self.assertTrue(expected <= by_id.keys())
        for source_id in expected:
            source = by_id[source_id]
            self.assertFalse(source.get("enabled", True), source_id)
            notes = source.get("notes", "").lower()
            self.assertTrue("no stable" in notes or "no documented" in notes)
        self.assertTrue(by_id["src-aider-polyglot"].get("enabled"))
        self.assertEqual(by_id["src-aider-polyglot"].get("adapter_id"), "src-aider-polyglot")
        self.assertTrue(by_id["src-mle-bench"].get("enabled"))
        self.assertEqual(by_id["src-mle-bench"].get("adapter_id"), "src-mle-bench")
        self.assertTrue(by_id["swebench-official"].get("enabled"))
        self.assertEqual(by_id["swebench-official"].get("adapter_id"), "swebench-official")
        self.assertEqual(
            by_id["swebench-official"].get("url"),
            "https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json",
        )

    def test_system_benchmarks_keep_environment_protocol_visible(self):
        benchmarks = json.loads((ROOT / "data/catalog/benchmarks.json").read_text())
        by_id = {row["id"]: row for row in benchmarks}
        for benchmark_id in ("browsecomp", "aider-polyglot", "androidworld", "mle-bench"):
            benchmark = by_id[benchmark_id]
            self.assertTrue(benchmark["catalog_only"])
            self.assertEqual(benchmark["evaluation_mode"], "system")
            self.assertEqual(benchmark["unit"], "%")
            self.assertTrue(benchmark["source_ids"])


if __name__ == "__main__":
    unittest.main()
