import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "catalog" / "long_horizon.json"
PUBLIC_PATH = ROOT / "data" / "derived" / "public.json"


class LongHorizonRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.public_payload = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
        cls.public_benchmark_ids = {
            row.get("id")
            for row in cls.public_payload.get("benchmarks", [])
            if isinstance(row, dict) and row.get("id")
        }

    def test_registry_has_expected_shape_and_breadth(self):
        self.assertIsInstance(self.payload.get("meta"), dict)
        benchmarks = self.payload.get("benchmarks")
        agents = self.payload.get("agents")
        self.assertIsInstance(benchmarks, list)
        self.assertIsInstance(agents, list)
        self.assertGreaterEqual(len(benchmarks), 40)
        self.assertGreaterEqual(len(agents), 10)
        self.assertEqual(len({row.get("id") for row in benchmarks}), len(benchmarks))
        self.assertEqual(len({row.get("id") for row in agents}), len(agents))

    @staticmethod
    def assert_http_url(testcase, value, path):
        parsed = urlparse(str(value or ""))
        testcase.assertIn(parsed.scheme, {"http", "https"}, path)
        testcase.assertTrue(parsed.netloc, path)

    def test_every_benchmark_has_first_party_source_and_explicit_coverage_axes(self):
        for index, row in enumerate(self.payload["benchmarks"]):
            path = f"benchmarks[{index}]"
            self.assertTrue(row.get("id"), path)
            self.assertTrue(row.get("name"), path)
            self.assertTrue(row.get("domain"), path)
            self.assertTrue(row.get("metric"), path)
            self.assertIsInstance(row.get("catalog_ids"), list, path)
            self.assertIsInstance(row.get("external_ids"), list, path)
            sources = row.get("sources")
            self.assertIsInstance(sources, list, path)
            self.assertGreaterEqual(len(sources), 1, path)
            self.assertTrue(any(str(source.get("role", "")).startswith("origin-") for source in sources), path)
            for source in sources:
                self.assert_http_url(self, source.get("url"), f"{path}.sources")
            if isinstance(row.get("task_count"), (int, float)):
                self.assertGreaterEqual(row["task_count"], 0, path)

    def test_every_agent_has_direct_original_url(self):
        for index, agent in enumerate(self.payload["agents"]):
            path = f"agents[{index}]"
            self.assertTrue(agent.get("id"), path)
            self.assertTrue(agent.get("name"), path)
            urls = agent.get("source_urls")
            self.assertIsInstance(urls, list, path)
            self.assertGreaterEqual(len(urls), 1, path)
            for url in urls:
                self.assert_http_url(self, url, f"{path}.source_urls")

    def test_external_ids_exist_in_public_snapshot(self):
        for index, row in enumerate(self.payload["benchmarks"]):
            path = f"benchmarks[{index}].external_ids"
            for external_id in row.get("external_ids", []):
                self.assertIn(external_id, self.public_benchmark_ids, path)

    def test_independent_variants_are_not_collapsed(self):
        ids = {row["id"] for row in self.payload["benchmarks"]}
        self.assertIn("naturebench", ids)
        self.assertIn("lhtb", ids)
        self.assertIn("deepresearchbench-ayanami", ids)
        self.assertIn("deepresearchbench-futuresearch", ids)
        self.assertNotEqual(
            next(row for row in self.payload["benchmarks"] if row["id"] == "lhtb")["catalog_ids"],
            ["terminal-bench"],
        )
        # This page is intentionally an independent public-source crosswalk;
        # it must not silently become a mirror of the WOA survey page.
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("long-horizon-agents.pages.woa.com", raw)


if __name__ == "__main__":
    unittest.main()
