from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from scripts.adapters import TerminalBenchScienceAdapter, all_adapters
from scripts.adapters.base import AdapterRun
from scripts.build_public_evidence import annotate_curated_public_mapping, build_index, load_catalog, load_public_aliases


class TerminalBenchScienceTests(unittest.TestCase):
    def fixture(self):
        return {
            "leaderboard": {"id": "board", "package": TerminalBenchScienceAdapter.PACKAGE,
                            "name": "v0-1-eval", "dataset_version_ids": ["dataset-01"]},
            "rows": [{"id": "row-1", "status": "display", "n_trials": 210,
                      "created_at": "2026-08-24T00:00:00Z", "updated_at": "2026-09-05T00:00:00Z",
                      "metadata": {"model_display": {"label": "Opus 5", "url": "https://www.anthropic.com/news/claude-opus-5"},
                                   "agent_display": {"label": "Claude Code", "url": "https://claude.com/product/claude-code"},
                                   "reasoning_effort": "max", "model_release_date": "2026-07-24"},
                      "metrics": {"accuracy": 30, "accuracy_stderr": 3.162, "tasks": 210, "passes": 63,
                                  "total_tokens": 1000, "total_cost_usd": 100,
                                  "domain_metrics": {"mathematical": {"accuracy": 25.49}},
                                  "generated_solution": "DO NOT INGEST"},
                      "trials": [{"messages": "DO NOT INGEST"}]}],
        }

    def parse(self, document=None):
        adapter = TerminalBenchScienceAdapter()
        payload = json.dumps(document or self.fixture()).encode()
        run = AdapterRun(adapter.spec.id, adapter.URL, adapter.URL, "2026-09-06T00:00:00Z", 200, payload=payload)
        return adapter.parse_payload(payload, run), run

    def test_registered_and_pin_version(self):
        self.assertIsInstance(all_adapters()["src-terminal-bench-science"], TerminalBenchScienceAdapter)
        document = self.fixture()
        document["leaderboard"]["name"] = "v0-2-eval"
        with self.assertRaises(ValueError):
            self.parse(document)

    def test_preserves_system_aggregate_and_deep_link(self):
        rows, run = self.parse()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["benchmark_ref"], row["benchmark_version_id"]), ("terminal-bench-science", "terminal-bench-science@0.1"))
        self.assertEqual((row["value"], row["metric"], row["unit"]), (30, "resolution_rate", "percent"))
        self.assertEqual((row["subject_type"], row["harness_id"]), ("system", "claude-code"))
        self.assertEqual(row["protocol"]["reasoning_effort"], "max")
        self.assertEqual(row["protocol"]["trials_per_task"], 3)
        self.assertEqual(row["protocol"]["task_count"], 70)
        self.assertIn("rows/row-1", row["metadata"]["submission_source_url"])
        self.assertIn("metrics.accuracy", row["source_locator"])
        self.assertEqual(row["uncertainty"]["standard_error_percentage_points"], 3.162)
        self.assertEqual(row["metadata"]["domain_metrics"]["mathematical"]["accuracy"], 25.49)
        self.assertNotIn("DO NOT INGEST", json.dumps(rows))
        self.assertTrue(run.payload_sha256)

    def test_display_is_not_approval_and_edit_dates_are_not_run_dates(self):
        rows, _ = self.parse()
        row = rows[0]
        self.assertFalse(row["verified"])
        self.assertEqual(row["status"], "candidate")
        self.assertEqual(row["metadata"]["source_status"], "reported")
        self.assertEqual(row["comparability"], "conditional")
        self.assertIsNone(row["published_at"])
        self.assertIsNone(row["observed_at"])
        self.assertIsNone(row["protocol"]["harness_version"])

    def test_zero_is_valid_but_missing_or_partial_or_hidden_is_not(self):
        for value in (0, 100):
            document = self.fixture()
            document["rows"][0]["metrics"]["accuracy"] = value
            self.assertEqual(self.parse(document)[0][0]["value"], value)
        for key, value in (("accuracy", None), ("accuracy", -1), ("accuracy", 101), ("tasks", 70)):
            document = self.fixture()
            document["rows"][0]["metrics"][key] = value
            rows, run = self.parse(document)
            self.assertEqual(rows, [])
            self.assertTrue(run.warnings)
        document = self.fixture()
        document["rows"][0]["status"] = "pending"
        self.assertEqual(self.parse(document)[0], [])
        document = self.fixture()
        document["rows"][0]["metadata"].pop("agent_display")
        self.assertEqual(self.parse(document)[0], [])

    def test_harness_changes_produce_distinct_evidence(self):
        document = self.fixture()
        second = copy.deepcopy(document["rows"][0])
        second["id"] = "row-2"
        second["metadata"]["agent_display"]["label"] = "Codex"
        document["rows"].append(second)
        rows, _ = self.parse(document)
        self.assertNotEqual(rows[0]["candidate_id"], rows[1]["candidate_id"])
        self.assertEqual(rows[1]["harness_id"], "codex")

    def test_source_dated_deepseek_release_overrides_only_automatic_alias(self):
        root = Path(__file__).resolve().parents[1]
        lookup, metadata, warnings = load_public_aliases(root, load_catalog(root)["models"])
        self.assertFalse(warnings)
        original = {"sourceId": "src-terminal-bench-science", "modelRef": "DeepSeek V4 Pro",
                    "canonicalModelId": "deepseek/v4-pro@2026-04-24", "mappingStatus": "exact_alias"}
        row = copy.deepcopy(original)
        annotate_curated_public_mapping(row, lookup, metadata)
        self.assertEqual(row["canonicalModelId"], "deepseek/v4-pro@2026-08-13")
        self.assertEqual(row["previousAutomaticMapping"]["canonicalModelId"], original["canonicalModelId"])
        for updates in ({"sourceId": "another-source"}, {"mappingStatus": "reviewed"}):
            row = {**original, **updates}
            annotate_curated_public_mapping(row, lookup, metadata)
            self.assertEqual(row["canonicalModelId"], original["canonicalModelId"])

    def test_provider_disclosures_are_versioned_unverified_systems(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / "data/public/provider_reports/tb-science-0.1-2026-09-06"
        index = build_index(root, [directory], generated_at="2026-09-06T14:37:33Z")
        self.assertFalse(index["meta"]["errors"])
        rows = {row["canonicalModelId"]: row for row in index["rows"]}
        self.assertEqual({key: row["value"] for key, row in rows.items()}, {
            "openai/gpt-6-astra@2026-09-03": 64.6,
            "anthropic/claude-fable-5.1@2026-09-01": 52.6,
        })
        for row in rows.values():
            self.assertEqual(row["benchmarkVersionId"], "terminal-bench-science@0.1")
            self.assertEqual((row["subjectType"], row["status"], row["verified"]), ("system", "reported", False))
            self.assertEqual(row["harnessId"], "unspecified-reported")
            self.assertEqual(row["protocol"]["reporting_party"], "model_provider")
            self.assertIsNone(row["observedAt"])
            self.assertIsNone(row["protocol"]["trials_per_task"])
            self.assertEqual(row["comparability"], "conditional")
            self.assertTrue(row["sourceLocator"])
            excerpt = directory / row["sourceId"] / "source_excerpt.json"
            self.assertEqual(row["payloadSha256"], hashlib.sha256(excerpt.read_bytes()).hexdigest())
            self.assertIn("curated_excerpt_not_full_page", row["qualityFlags"])
        self.assertIsNone(rows["openai/gpt-6-astra@2026-09-03"]["protocol"]["reasoning_effort"])
        self.assertEqual(rows["anthropic/claude-fable-5.1@2026-09-01"]["protocol"]["reasoning_effort"], "max")


if __name__ == "__main__":
    unittest.main()
