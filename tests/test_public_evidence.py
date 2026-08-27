from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_public_evidence import (
    _model_alias_keys,
    build_index,
    build_model_alias_lookup,
    write_index,
)


class PublicEvidenceTests(unittest.TestCase):
    def test_parenthesized_effort_suffix_is_display_only(self) -> None:
        self.assertIn("gpt55", _model_alias_keys("GPT 5.5 (High)"))
        self.assertIn("claudeopus5", _model_alias_keys("Claude Opus 5 (Max)"))
        # A date/release suffix must remain, so an old snapshot is not
        # silently mapped to the current release.
        self.assertNotIn("deepseekv4flash", _model_alias_keys("DeepSeek V4 Flash (High) (20260731)"))

    def make_fixture(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp(prefix="fmb-public-evidence-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        catalog = root / "data" / "catalog"
        source_dir = root / "artifacts" / "fetch" / "fixture-source"
        catalog.mkdir(parents=True)
        source_dir.mkdir(parents=True)
        (catalog / "models.json").write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "acme/frontier@2026",
                            "name": "Frontier 2026",
                            "release_date": "2026-08-01",
                            "aliases": ["frontier-2026"],
                        },
                        {
                            "id": "acme/other@2026",
                            "name": "Other 2026",
                            "aliases": ["other-2026"],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        (catalog / "benchmarks.json").write_text(
            json.dumps(
                {
                    "benchmarks": [
                        {
                            "id": "toy-bench",
                            "name": "Toy benchmark",
                            "featured": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (catalog / "sources.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "fixture-source",
                            "label": "Fixture leaderboard",
                            "url": "https://example.org/leaderboard",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (catalog / "harnesses.json").write_text(json.dumps({"harnesses": []}), encoding="utf-8")
        (source_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "source_id": "fixture-source",
                    "resolved_url": "https://example.org/leaderboard.json",
                    "retrieved_at": "2026-08-27T07:00:00Z",
                    "payload_sha256": "deadbeef",
                    "parser_version": "fixture@1",
                    "http_status": 200,
                }
            ),
            encoding="utf-8",
        )
        rows = [
            {
                "candidate_id": "old-id",
                "source_id": "fixture-source",
                "source_url": "https://example.org/leaderboard.json",
                "source_locator": "table=main;row=0",
                "model_ref": "frontier-2026",
                "benchmark_ref": "toy-bench",
                "metric": "accuracy",
                "value": 88,
                "raw_value": "88%",
                "unit": "percent",
                "status": "candidate",
                "verified": None,
                "evidence_level": "A",
                "comparability": "conditional",
                "protocol": {"harness": "model-only", "shots": 0},
                "metadata": {
                    "source_status": "official_published",
                    "leaderboard_url": "https://example.org/leaderboard",
                },
            },
            {
                "candidate_id": "new-id",
                "source_id": "fixture-source",
                "source_url": "https://example.org/leaderboard.json",
                "source_locator": "table=main;row=1",
                "model_ref": "unknown-frontier",
                "benchmark_ref": "toy-bench",
                "metric": "accuracy",
                "value": 77,
                "raw_value": "77%",
                "unit": "percent",
                "status": "candidate",
                "verified": None,
                "evidence_level": "C",
                "comparability": "conditional",
                "protocol": {"harness": "model-only"},
                "metadata": {"source_status": "reported"},
            },
            {
                "candidate_id": "missing-id",
                "source_id": "fixture-source",
                "source_url": "https://example.org/leaderboard.json",
                "source_locator": "table=main;row=2",
                "model_ref": "frontier-2026",
                "benchmark_ref": "toy-bench",
                "metric": "accuracy",
                "value": None,
                "raw_value": "—",
                "unit": "percent",
                "status": "candidate",
                "verified": None,
                "evidence_level": "A",
                "comparability": "conditional",
                "protocol": {"harness": "model-only"},
                "metadata": {"source_status": "missing"},
            },
        ]
        (source_dir / "candidates.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
        )
        return root, source_dir

    def test_alias_lookup_is_conservative_and_unique(self) -> None:
        lookup = build_model_alias_lookup(
            {
                "acme/frontier@2026": {
                    "id": "acme/frontier@2026",
                    "name": "Frontier 2026",
                    "aliases": ["frontier-2026"],
                }
            }
        )
        self.assertIn("frontier2026", lookup)
        self.assertEqual(lookup["frontier2026"], {"acme/frontier@2026"})

    def test_build_separates_curated_and_unmapped_rows(self) -> None:
        root, _ = self.make_fixture()
        index = build_index(
            root,
            [root / "artifacts" / "fetch"],
            generated_at="2026-08-27T08:00:00Z",
            max_per_key=1,
        )
        self.assertEqual(index["meta"]["schemaVersion"], "public-evidence@0.1")
        self.assertEqual(index["meta"]["verified"], False)
        self.assertEqual(index["stats"]["inputRows"], 3)
        self.assertEqual(index["stats"]["deduplicatedRows"], 3)
        self.assertEqual(index["stats"]["selectedRows"], 1)
        self.assertEqual(index["stats"]["omittedRows"], 2)
        self.assertEqual(index["stats"]["mappedRows"], 2)
        self.assertEqual(index["stats"]["unmappedRows"], 1)

        selected = index["rows"][0]
        self.assertEqual(selected["status"], "reported")
        self.assertEqual(selected["reviewStatus"], "unreviewed")
        self.assertEqual(selected["verificationStatus"], "not_reproduced")
        self.assertFalse(selected["verified"])
        self.assertEqual(selected["canonicalModelId"], "acme/frontier@2026")
        self.assertEqual(selected["mappingStatus"], "heuristic_alias")
        self.assertEqual(selected["evidenceUrl"], "https://example.org/leaderboard")
        self.assertEqual(selected["sourceUrl"], "https://example.org/leaderboard.json")
        self.assertEqual(selected["payloadSha256"], "deadbeef")
        self.assertEqual(selected["protocol"]["shots"], 0)
        self.assertEqual(selected["alternativesCount"], 2)

        omitted = index["_omittedRows"]
        self.assertEqual(len(omitted), 2)
        self.assertTrue(any(row["mappingStatus"] == "unmatched" for row in omitted))
        self.assertTrue(any(row["status"] == "candidate" for row in omitted))

    def test_write_index_keeps_omitted_rows_out_of_page_json(self) -> None:
        root, _ = self.make_fixture()
        index = build_index(
            root,
            [root / "artifacts" / "fetch"],
            generated_at="2026-08-27T08:00:00Z",
            max_per_key=1,
        )
        output = root / "data" / "derived" / "public.json"
        evidence = root / "data" / "public" / "evidence.jsonl"
        unmapped = root / "data" / "public" / "unmapped.jsonl"
        alternatives = root / "data" / "public" / "alternatives.jsonl"
        write_index(index, output, evidence, unmapped, alternatives)
        page = json.loads(output.read_text(encoding="utf-8"))
        self.assertNotIn("_omittedRows", page)
        self.assertEqual(len(page["rows"]), 1)
        self.assertEqual(len(evidence.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(len(unmapped.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(len(alternatives.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
