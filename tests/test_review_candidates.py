from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.review_candidates import (
    build_review,
    ensure_safe_output,
    write_outputs,
)


class CandidateReviewTests(unittest.TestCase):
    def make_fixture(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp(prefix="fmb-review-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        catalog = root / "data" / "catalog"
        artifact = root / "artifacts" / "fetch" / "fixture-source"
        catalog.mkdir(parents=True)
        artifact.mkdir(parents=True)
        (catalog / "models.json").write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "acme/frontier@1",
                            "name": "Frontier 1",
                            "aliases": ["frontier-one"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (catalog / "benchmarks.json").write_text(
            json.dumps(
                [
                    {
                        "id": "toy-reasoning",
                        "name": "Toy reasoning",
                        "category": "reasoning",
                        "versions": [{"id": "toy-reasoning@v1"}],
                        "metrics": [
                            {
                                "id": "accuracy",
                                "unit": "percent",
                                "scale": {"min": 0, "max": 100},
                            }
                        ],
                    },
                    {
                        "id": "toy-agent",
                        "name": "Toy agent",
                        "category": "coding-agent",
                        "versions": [{"id": "toy-agent@v1"}],
                        "metrics": [
                            {
                                "id": "resolved",
                                "unit": "percent",
                                "scale": {"min": 0, "max": 100},
                            }
                        ],
                    },
                ]
            ),
            encoding="utf-8",
        )
        (catalog / "sources.json").write_text(
            json.dumps(
                [
                    {
                        "id": "fixture-source",
                        "label": "Fixture source",
                        "kind": "test",
                        "url": "https://example.org/fixture",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (catalog / "harnesses.json").write_text(
            json.dumps(
                [
                    {
                        "id": "model-only",
                        "name": "Model only",
                        "kind": "model",
                        "status": "active",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (artifact / "manifest.json").write_text(
            json.dumps(
                {
                    "source_id": "fixture-source",
                    "resolved_url": "https://example.org/fixture.json",
                    "retrieved_at": "2026-08-27T00:00:00Z",
                    "payload_sha256": "abc123",
                    "parser_version": "fixture@1",
                }
            ),
            encoding="utf-8",
        )
        reviewable = {
            "candidate_id": "cand-reviewable",
            "source_id": "fixture-source",
            "source_url": "https://example.org/fixture.json",
            "source_locator": "table=main;row=0;column=accuracy",
            "model_ref": "frontier-one",
            "benchmark_ref": "toy-reasoning",
            "metric": "accuracy",
            "value": 88.0,
            "raw_value": "88%",
            "unit": "percent",
            "evidence_level": "A",
            "comparability": "conditional",
            "protocol": {"release": "toy-reasoning@v1", "harness": "model-only", "shots": 0},
            "observed_at": "2026-08-26",
            "status": "candidate",
        }
        missing = {
            "candidate_id": "cand-missing",
            "source_id": "fixture-source",
            "source_url": "https://example.org/fixture.json",
            "source_locator": "table=main;row=1;column=accuracy",
            "model_ref": "unknown-model",
            "benchmark_ref": "toy-reasoning",
            "metric": "accuracy",
            "value": None,
            "raw_value": "—",
            "unit": "percent",
            "evidence_level": "A",
            "comparability": "conditional",
            "protocol": {"release": "toy-reasoning@v1", "harness": "model-only"},
            "status": "candidate",
        }
        system_without_harness = {
            "candidate_id": "cand-system-no-harness",
            "source_id": "fixture-source",
            "source_url": "https://example.org/fixture.json",
            "source_locator": "table=agents;row=0;column=resolved",
            "model_ref": "frontier-one",
            "benchmark_ref": "toy-agent",
            "metric": "resolved",
            "value": 42.0,
            "raw_value": "42%",
            "unit": "percent",
            "evidence_level": "A",
            "comparability": "conditional",
            "protocol": {"release": "toy-agent@v1", "subject_type": "system"},
            "observed_at": "2026-08-26",
            "status": "candidate",
        }
        (artifact / "candidates.jsonl").write_text(
            "\n".join(
                json.dumps(row, ensure_ascii=False)
                for row in (reviewable, reviewable, missing, system_without_harness)
            )
            + "\n",
            encoding="utf-8",
        )
        return root, root / "artifacts" / "fetch"

    def test_build_review_deduplicates_and_keeps_pending_decisions(self) -> None:
        root, input_dir = self.make_fixture()
        canonical_before = hashlib.sha256(
            (root / "data" / "catalog" / "models.json").read_bytes()
        ).hexdigest()
        packet = build_review(
            root,
            [input_dir],
            generated_at="2026-08-27T01:00:00Z",
            limit=0,
        )
        self.assertEqual(packet["summary"]["unique_candidates"], 3)
        self.assertEqual(packet["summary"]["duplicate_groups"], 1)
        self.assertEqual(packet["summary"]["duplicate_conflicts"], 0)
        self.assertTrue(packet["candidate_only"])
        self.assertFalse(packet["approved_mutation"])
        self.assertEqual(packet["root"], ".")
        self.assertEqual(packet["input_dirs"], ["artifacts/fetch"])
        self.assertTrue(all(item["decision"] == "pending" for item in packet["candidates"]))
        reviewable = next(item for item in packet["candidates"] if item["candidate_id"] == "cand-reviewable")
        self.assertEqual(reviewable["review_status"], "reviewable")
        self.assertEqual(reviewable["canonical_model_id_suggestion"], "acme/frontier@1")
        missing = next(item for item in packet["candidates"] if item["candidate_id"] == "cand-missing")
        self.assertEqual(missing["review_status"], "missing-value")
        system = next(item for item in packet["candidates"] if item["candidate_id"] == "cand-system-no-harness")
        self.assertEqual(system["subject_type"], "system")
        self.assertFalse(system["checks"]["harness_context"])
        self.assertEqual(
            hashlib.sha256((root / "data" / "catalog" / "models.json").read_bytes()).hexdigest(),
            canonical_before,
        )

    def test_outputs_are_review_scaffold_and_guard_canonical_paths(self) -> None:
        root, input_dir = self.make_fixture()
        packet = build_review(root, [input_dir], generated_at="2026-08-27T01:00:00Z", limit=1)
        output = root / "artifacts" / "review"
        write_outputs(output, packet)
        review_json = json.loads((output / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(review_json["schema_version"], "candidate-review@0.1")
        self.assertEqual(review_json["summary"]["selected_candidates"], 1)
        markdown = (output / "review.md").read_text(encoding="utf-8")
        self.assertIn("candidate-only", markdown)
        self.assertIn("decision: `pending`", markdown)
        with self.assertRaises(ValueError):
            ensure_safe_output(root, root / "data" / "observations", [input_dir])
        with self.assertRaises(ValueError):
            ensure_safe_output(root, input_dir / "review", [input_dir])


if __name__ == "__main__":
    unittest.main()
