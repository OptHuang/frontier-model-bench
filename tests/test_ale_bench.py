from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.adapters import ALEBenchAdapter, all_adapters
from scripts.adapters.base import AdapterRun


ROOT = Path(__file__).resolve().parents[1]


class ALEBenchTests(unittest.TestCase):
    def parse(self, payload: bytes | None = None):
        adapter = ALEBenchAdapter()
        payload = payload if payload is not None else (ROOT / "tests/fixtures/ale_bench_summary.json").read_bytes()
        run = AdapterRun(adapter.spec.id, adapter.URL, adapter.URL, "2026-09-06T00:00:00Z", 200, payload=payload)
        return adapter.parse_payload(payload, run), run

    def test_registered_separately_from_agents_last_exam(self):
        self.assertIsInstance(all_adapters()["src-ale-bench"], ALEBenchAdapter)
        self.assertIn("agents-last-exam", all_adapters())

    def test_preserves_objective_unit_iteration_and_view(self):
        rows, run = self.parse()
        self.assertEqual(len(rows), 12)
        self.assertEqual(run.metadata["model_count"], 2)
        row = rows[0]
        self.assertEqual(row["model_ref"], "gpt-5.6-sol-max")
        self.assertEqual(row["benchmark_ref"], "ale-bench")
        self.assertEqual((row["metric"], row["value"], row["unit"]), ("performance", 2176.875, "score"))
        self.assertEqual(row["protocol"]["reasoning_effort"], "max")
        self.assertEqual(row["protocol"]["self_refine_iterations"], 1)
        self.assertEqual(row["protocol"]["view"], "all")
        self.assertEqual(row["harness_id"], "ale-bench-self-refine")
        self.assertEqual(row["subject_type"], "system")
        refined = rows[6]
        self.assertEqual(refined["protocol"]["self_refine_iterations"], 16)
        self.assertEqual(refined["value"], 2409.525)
        self.assertNotEqual(row["candidate_id"], refined["candidate_id"])
        self.assertIn("performance.all.mean", row["source_locator"])
        rank = rows[3]
        self.assertEqual((rank["metric"], rank["unit"], rank["protocol"]["metric_direction"]), ("rank", "rank", "lower"))

    def test_missing_negative_and_zero_scores_are_distinct(self):
        rows, _ = self.parse()
        self.assertEqual(rows[8]["value"], 0)
        self.assertIsNone(rows[9]["value"])
        self.assertEqual(rows[10]["value"], -110)
        self.assertEqual(rows[8]["protocol"]["reasoning_effort"], "no-thinking")

    def test_evidence_has_no_invented_date_version_or_approval(self):
        rows, _ = self.parse()
        row = rows[0]
        self.assertIsNone(row["published_at"])
        self.assertIsNone(row["observed_at"])
        self.assertIsNone(row["benchmark_version_id"])
        self.assertIsNone(row["protocol"]["judge_version"])
        self.assertEqual(row["status"], "candidate")
        self.assertFalse(row["verified"])
        self.assertNotIn("DO NOT COPY", json.dumps(rows))
        self.assertNotIn("987654321", json.dumps(rows))
        self.assertIsNone(rows[8]["metadata"]["detail_url"])

    def test_rejects_unknown_shape_and_missing_configuration(self):
        with self.assertRaises(ValueError):
            self.parse(b'{"results": []}')
        rows, run = self.parse(b'[{"model_name":"x","overall_results":[{"performance":{"all":{"mean":100}}}]}]')
        self.assertEqual(rows, [])
        self.assertTrue(run.warnings)


if __name__ == "__main__":
    unittest.main()
