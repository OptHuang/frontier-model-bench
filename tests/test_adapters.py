from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.adapters.arena import ArenaMetadataAdapter
from scripts.adapters.aider import AiderPolyglotAdapter
from scripts.adapters.base import AdapterRun
from scripts.adapters.helm import HELMAdapter
from scripts.adapters.huggingface import HuggingFaceLeaderboardAdapter
from scripts.adapters.livebench import LiveBenchAdapter
from scripts.adapters.mlebench import MLEBenchAdapter
from scripts.adapters.swebench import SWEbenchOfficialAdapter


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class AdapterFixtureTests(unittest.TestCase):
    def run_parse(self, adapter, filename: str, **metadata):
        payload = fixture(filename)
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://fixture",
            resolved_url="file://fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload,
            metadata=metadata,
        )
        run.candidates = adapter.parse_payload(payload, run)
        self.assertFalse(run.errors)
        return run.candidates

    def test_huggingface_preserves_missing_and_unverified_tier(self):
        adapter = HuggingFaceLeaderboardAdapter(
            "fixture-hf",
            dataset="org/dataset",
            benchmark_ref="swebench-verified",
            label="fixture",
        )
        rows = self.run_parse(adapter, "hf_leaderboard.json")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["value"], 87.5)
        self.assertEqual(rows[0]["evidence_level"], "A")
        self.assertIsNone(rows[1]["value"])
        self.assertEqual(rows[1]["evidence_level"], "C")
        self.assertIn("unverified_submission", rows[1]["quality_flags"])

    def test_swebench_marks_agent_rows_as_system(self):
        rows = self.run_parse(SWEbenchOfficialAdapter(), "swebench_leaderboards.json")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["protocol"]["subject_type"], "system")
        self.assertEqual(rows[0]["protocol"]["scaffold"], "mini-SWE-agent")
        self.assertEqual(rows[0]["value"], 72.4)

    def test_livebench_keeps_dash_as_missing(self):
        adapter = LiveBenchAdapter()
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://fixture",
            resolved_url="file://fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=fixture("livebench_table.csv"),
            metadata={"selected_path": "public/table_2026_08_27.csv", "release_date": "2026-08-27"},
        )
        rows = adapter.parse_payload(run.payload, run)
        self.assertEqual(len(rows), 4)
        self.assertIsNone(rows[2]["value"])
        self.assertIn("missing_score", rows[2]["quality_flags"])

    def test_helm_parses_explicit_table_rows(self):
        adapter = HELMAdapter("capabilities")
        rows = self.run_parse(
            adapter,
            "helm_groups.json",
            project="capabilities",
            release="fixture",
            summary_date="2026-08-27",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["benchmark_ref"], "helm-mean-win-rate")
        self.assertEqual(rows[0]["value"], 0.75)
        self.assertEqual(rows[0]["unit"], "fraction")

    def test_helm_qualifies_same_named_summary_scores_by_table(self):
        adapter = HELMAdapter("capabilities")
        payload = json.dumps(
            [
                {
                    "title": "Accuracy",
                    "header": [{"value": "Model"}, {"value": "Mean score"}],
                    "rows": [[{"value": "Model-1"}, {"value": 0.8}]],
                },
                {
                    "title": "Efficiency",
                    "header": [{"value": "Model"}, {"value": "Mean score"}],
                    "rows": [[{"value": "Model-1"}, {"value": 42.0}]],
                },
            ]
        ).encode("utf-8")
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://fixture",
            resolved_url="file://fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload,
            metadata={"project": "capabilities", "release": "fixture"},
        )

        rows = adapter.parse_payload(payload, run)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["benchmark_ref"], "helm-mean-score")
        self.assertEqual(rows[0]["metric"], "score")
        self.assertEqual(rows[1]["benchmark_ref"], "helm-mean-score")
        self.assertEqual(rows[1]["metric"], "efficiency-score")
        self.assertNotEqual(
            (rows[0]["benchmark_ref"], rows[0]["metric"]),
            (rows[1]["benchmark_ref"], rows[1]["metric"]),
        )
        self.assertNotEqual(rows[0]["candidate_id"], rows[1]["candidate_id"])

    def test_arena_is_metadata_only(self):
        class FailingClient:
            def get(self, _url):
                raise AssertionError("disabled Arena adapter must not make requests")

        run = ArenaMetadataAdapter().fetch(FailingClient(), retrieved_at="2026-08-27T00:00:00Z")
        self.assertEqual(run.candidates, [])
        self.assertTrue(run.metadata["metadata_only"])
        self.assertTrue(run.metadata["disabled"])

    def test_aider_polyglot_emits_system_candidates_with_protocol(self):
        rows = self.run_parse(AiderPolyglotAdapter(), "aider_polyglot_leaderboard.yml")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["benchmark_ref"], "aider-polyglot")
        self.assertEqual(rows[0]["value"], 62.2)
        self.assertEqual(rows[0]["protocol"]["subject_type"], "system")
        self.assertEqual(rows[0]["protocol"]["edit_format"], "diff")
        self.assertEqual(rows[0]["metadata"]["date"], "2026-08-20")
        self.assertEqual(rows[0]["status"], "candidate")

    def test_mlebench_parses_main_table_and_complexity_splits(self):
        rows = self.run_parse(MLEBenchAdapter(), "mlebench_readme.md")
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["metric"] for row in rows}, {"lite", "medium", "high", "all"})
        self.assertEqual(rows[0]["protocol"]["subject_type"], "system")
        self.assertEqual(rows[0]["protocol"]["harness"], "DemoAgent")
        self.assertEqual(rows[0]["metadata"]["date"], "2026-02-23")
        self.assertEqual(rows[0]["value"], 80.3)


if __name__ == "__main__":
    unittest.main()
