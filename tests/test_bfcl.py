from __future__ import annotations

import unittest
from pathlib import Path

from scripts.adapters import all_adapters
from scripts.adapters.base import AdapterRun
from scripts.adapters.bfcl import BFCLAdapter, BFCLOfficialAdapter


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bfcl_overall.csv"


class BFCLAdapterTests(unittest.TestCase):
    def _parse(self, adapter: BFCLOfficialAdapter | None = None):
        adapter = adapter or BFCLOfficialAdapter()
        payload = FIXTURE.read_bytes()
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://bfcl-fixture",
            resolved_url="file://bfcl-fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload,
        )
        rows = adapter.parse_payload(payload, run)
        self.assertEqual(run.errors, [])
        self.assertEqual(run.metadata["benchmark_version_id"], "bfcl@v4")
        self.assertEqual(run.metadata["evaluator_commit"], "f7cf735")
        return rows

    def test_alias_and_registry(self):
        self.assertIs(BFCLAdapter, BFCLOfficialAdapter)
        registered = all_adapters()
        self.assertIn("src-bfcl", registered)
        self.assertEqual(registered["src-bfcl"].spec.url, BFCLOfficialAdapter.CSV_URL)

    def test_fc_row_preserves_protocol_cost_latency_and_submetrics(self):
        rows = self._parse()
        self.assertEqual(len(rows), 4)
        row = rows[0]
        self.assertEqual(row["model_ref"], "Claude-Opus-4-5-20251101")
        self.assertEqual(row["source_model"], "Claude-Opus-4-5-20251101 (FC)")
        self.assertEqual(row["value"], 77.47)
        self.assertEqual(row["raw_value"], "77.47%")
        self.assertEqual(row["unit"], "percent")
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["harness_id"], "bfcl-eval")
        self.assertEqual(row["subject_type"], "system")
        self.assertEqual(row["protocol"]["calling_mode"], "native_fc")
        self.assertEqual(row["protocol"]["calling_mode_label"], "FC")
        self.assertEqual(row["protocol"]["benchmark_version_id"], "bfcl@v4")
        self.assertEqual(row["protocol"]["commit"], "f7cf735")
        self.assertEqual(row["protocol"]["leaderboard_url"], BFCLOfficialAdapter.LEADERBOARD_URL)
        self.assertEqual(row["metadata"]["total_cost_usd"], 86.55)
        self.assertEqual(row["metadata"]["latency_mean_s"], 4.38)
        self.assertEqual(row["metadata"]["latency_std_s"], 3.13)
        self.assertEqual(row["metadata"]["latency_p95_s"], 7.56)
        self.assertEqual(row["metadata"]["organization"], "Anthropic")
        self.assertEqual(row["metadata"]["submetrics"]["Non-Live AST Acc"]["value"], 88.58)
        self.assertEqual(row["metadata"]["submetrics"]["Format Sensitivity Max Delta"]["value"], None)
        self.assertIn("missing_source_date", row["quality_flags"])
        self.assertIn("mode_specific", row["quality_flags"])
        self.assertEqual(row["status"], "candidate")
        self.assertIsNone(row["observed_at"])

        prompt = self._parse()[1]
        self.assertEqual(
            prompt["metadata"]["submetrics"]["Format Sensitivity Max Delta"]["value"],
            0.5,
        )

    def test_prompt_and_variant_modes_are_distinct(self):
        rows = self._parse()
        prompt = rows[1]
        thinking = rows[2]
        unspecified = rows[3]
        self.assertEqual(prompt["model_ref"], "Gemini-3-Pro-Preview")
        self.assertEqual(prompt["protocol"]["calling_mode"], "prompt")
        self.assertEqual(prompt["protocol"]["variant"], None)
        self.assertEqual(prompt["metadata"]["submetrics"]["Format Sensitivity Max Delta"]["value"], 0.5)
        self.assertEqual(thinking["model_ref"], "Tiny-Tool-Model")
        self.assertEqual(thinking["protocol"]["calling_mode"], "native_fc")
        self.assertEqual(thinking["protocol"]["variant"], "thinking")
        self.assertIn("missing_calling_mode", unspecified["quality_flags"])
        self.assertIsNone(unspecified["value"])
        self.assertIn("missing_accuracy", unspecified["quality_flags"])

    def test_bad_payload_reports_missing_columns(self):
        adapter = BFCLOfficialAdapter()
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://bad",
            resolved_url="file://bad",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=b"Model,Rank\nfoo,1\n",
        )
        with self.assertRaises(ValueError):
            adapter.parse_payload(run.payload, run)


if __name__ == "__main__":
    unittest.main()
