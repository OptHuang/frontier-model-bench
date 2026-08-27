from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_derived import (
    PUBLIC_UNMAPPED_EXAMPLE_FIELDS,
    derive_site_timestamps,
    public_evidence_for_site,
    public_unmapped_model_for_site,
    write_compact_json,
)

ROOT = Path(__file__).resolve().parents[1]


class DerivedRuntimePayloadTests(unittest.TestCase):
    def test_public_evidence_projection_keeps_visible_provenance_and_semantics(self) -> None:
        row = {
            "id": "pub-1",
            "candidateId": "candidate-1",
            "canonicalModelId": "acme/model@2026",
            "modelName": "Acme Model",
            "modelRef": "acme-model-high",
            "benchmarkId": "toy-bench",
            "benchmarkName": "Toy Bench",
            "benchmarkVersion": "v1",
            "benchmarkVersionHint": "release-2026",
            "benchmarkVersionId": "toy-bench@v1",
            "benchmarkVersionStatus": "source_reported",
            "metricId": "score",
            "sourceMetricId": "raw_score",
            "value": 0,
            "rawValue": "0.0",
            "unit": "percent",
            "evidenceLevel": "A",
            "comparability": "conditional",
            "sourceId": "toy-source",
            "sourceLabel": "Toy source",
            "sourceUrl": "https://example.org/snapshot.json",
            "sourcePageUrl": "https://example.org/leaderboard",
            "sourceApiUrl": "https://example.org/api",
            "evidenceUrl": "https://example.org/model-card",
            "sourceLocator": "rows[4].score",
            "retrievedAt": "2026-08-27T12:00:00Z",
            "observedAt": "2026-08-26",
            "publishedAt": "2026-08-25",
            "payloadSha256": "deadbeef",
            "protocol": {"split": "test", "harness": "agent-x"},
            "harnessId": "agent-x",
            "harness": "agent-x",
            "qualityFlags": ["harness_specific"],
            "subjectType": "system",
            "sourceSubjectType": "model",
            "subjectInferredBy": ["benchmark:evaluation_mode=system"],
            "mappingStatus": "curated_alias",
            "matrixExcluded": True,
            "matrixExcludedReason": "telemetry_metric",
            # This is the one selection field consumed by both app.js and
            # models.js when choosing a representative public observation.
            "selectionRank": 2,
            "selection": "curated",
            "selectionKey": "internal-key",
            "selectionReason": ["canonical_model_mapping"],
            "mappingCandidates": ["acme/model@2026"],
            "mappingEvidence": {"registry": "aliases.json"},
            "mappingNote": "internal review note",
            "sourceRow": {"metadata": {"large": "raw payload"}},
            "snapshotLocations": [{"artifact": "source/candidates.jsonl", "line": 9}],
            "snapshotCount": 1,
            "verificationStatus": "not_reproduced",
            "verification_status": "not_reproduced",
            "verified": False,
            "reviewStatus": "unreviewed",
            "status": "reported",
            "evidenceNote": "generic public disclaimer",
            "parserVersion": "0.1.0",
            "httpStatus": 200,
            "publishedNull": None,
        }
        original = copy.deepcopy(row)

        projected = public_evidence_for_site(row)

        self.assertEqual(row, original, "projection must not mutate the full artifact row")
        for key in (
            "id",
            "canonicalModelId",
            "modelName",
            "modelRef",
            "benchmarkId",
            "benchmarkName",
            "benchmarkVersion",
            "benchmarkVersionHint",
            "benchmarkVersionId",
            "metricId",
            "sourceMetricId",
            "value",
            "rawValue",
            "unit",
            "evidenceLevel",
            "sourceId",
            "sourceLabel",
            "sourceUrl",
            "sourcePageUrl",
            "sourceApiUrl",
            "evidenceUrl",
            "sourceLocator",
            "retrievedAt",
            "observedAt",
            "publishedAt",
            "payloadSha256",
            "protocol",
            "harnessId",
            "qualityFlags",
            "subjectType",
            "sourceSubjectType",
            "mappingStatus",
            "matrixExcluded",
            "matrixExcludedReason",
            "selectionRank",
        ):
            self.assertEqual(projected[key], row[key], key)

        for key in (
            "candidateId",
            "benchmarkVersionStatus",
            "selection",
            "selectionKey",
            "selectionReason",
            "mappingCandidates",
            "mappingEvidence",
            "mappingNote",
            "subjectInferredBy",
            "sourceRow",
            "snapshotLocations",
            "snapshotCount",
            "verificationStatus",
            "verification_status",
            "verified",
            "reviewStatus",
            "status",
            "evidenceNote",
            "parserVersion",
            "httpStatus",
            "comparability",
        ):
            self.assertNotIn(key, projected, key)

    def test_public_projection_omits_duplicate_urls_and_defaults(self) -> None:
        projected = public_evidence_for_site(
            {
                "id": "pub-2",
                "sourceUrl": "https://example.org/data.json",
                "evidenceUrl": "https://example.org/data.json",
                "metricId": "score",
                "sourceMetricId": "score",
                "harnessId": "model-only",
                "harness": "model-only",
                "matrixExcluded": False,
                "status": "reported",
                "comparability": "conditional",
                "protocol": {},
                "qualityFlags": [],
            }
        )
        self.assertEqual(projected["sourceUrl"], "https://example.org/data.json")
        for key in (
            "evidenceUrl",
            "sourceMetricId",
            "harness",
            "matrixExcluded",
            "status",
            "comparability",
            "protocol",
            "qualityFlags",
        ):
            self.assertNotIn(key, projected, key)

    def test_unmapped_projection_keeps_one_compact_source_example(self) -> None:
        raw = {
            "modelRef": "unresolved-model",
            "rowCount": 7,
            "numericRowCount": 6,
            "benchmarkCount": 2,
            "benchmarkIds": ["bench-a", "bench-b"],
            "sourceIds": ["source-a"],
            "sourceLabels": ["Source A"],
            "sourceUrls": ["https://example.org/source-a"],
            "mappingStatusCounts": {"unmatched": 7},
            "latestRetrievedAt": "2026-08-27T12:00:00Z",
            "observedAtMax": "2026-08-26",
            "statusCounts": {"reported": 7},
            "metricIds": ["score"],
            "mappingCandidates": [],
            "examples": [
                {
                    "sourceId": "source-a",
                    "sourceLabel": "Source A",
                    "sourceUrl": "https://example.org/data.json",
                    "evidenceUrl": "https://example.org/model-card",
                    "sourceLocator": "rows[3]",
                    "retrievedAt": "2026-08-27T12:00:00Z",
                    "observedAt": "2026-08-26",
                    "protocol": {"large": "not needed by the alias card"},
                    "rawValue": "42",
                },
                {"sourceId": "source-b", "sourceLocator": "rows[9]"},
            ],
        }

        projected = public_unmapped_model_for_site(raw)

        self.assertEqual(len(projected["examples"]), 1)
        self.assertEqual(
            projected["examples"][0],
            {
                "sourceId": "source-a",
                "sourceLabel": "Source A",
                "sourceUrl": "https://example.org/data.json",
                "evidenceUrl": "https://example.org/model-card",
                "sourceLocator": "rows[3]",
                "retrievedAt": "2026-08-27T12:00:00Z",
                "observedAt": "2026-08-26",
            },
        )
        self.assertNotIn("statusCounts", projected)
        self.assertNotIn("metricIds", projected)
        self.assertNotIn("mappingCandidates", projected)

    def test_snapshot_metadata_uses_latest_catalog_or_public_date(self) -> None:
        as_of, last_updated = derive_site_timestamps(
            {"asOf": "2026-08-27", "lastUpdated": "2026-08-27T09:30:00Z"},
            {"meta": {"as_of": "2026-08-28"}},
            {"meta": {"as_of": "2026-08-26"}},
            {"generatedAt": "2026-08-27T16:21:44Z"},
        )
        self.assertEqual(as_of, "2026-08-28")
        self.assertEqual(last_updated, "2026-08-28T00:00:00Z")

        public_as_of, public_updated = derive_site_timestamps(
            {"asOf": "2026-08-27"},
            {"meta": {"as_of": "2026-08-27"}},
            {"meta": {"as_of": "2026-08-27"}},
            {"generatedAt": "2026-08-29T07:08:09Z"},
        )
        self.assertEqual(public_as_of, "2026-08-29")
        self.assertEqual(public_updated, "2026-08-29T07:08:09Z")

    def test_compact_writer_has_no_pretty_printing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "site.json"
            payload = {"中文": [1, {"value": "x"}]}
            write_compact_json(path, payload)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            )


class RepositoryRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.full = json.loads((ROOT / "data/derived/public.json").read_text(encoding="utf-8"))["rows"]
        cls.site = json.loads((ROOT / "data/derived/site.json").read_text(encoding="utf-8"))

    def test_real_projection_preserves_every_public_row_and_ui_contract(self) -> None:
        projected = self.site["publicEvidence"]
        self.assertEqual(
            [row["id"] for row in projected],
            [row["id"] for row in self.full],
        )
        forbidden = {
            "candidateId",
            "sourceRow",
            "snapshotLocations",
            "snapshotCount",
            "selection",
            "selectionKey",
            "selectionReason",
            "mappingCandidates",
            "mappingEvidence",
            "mappingNote",
            "subjectInferredBy",
            "verification_status",
            "verificationStatus",
            "verified",
        }
        direct_fields = (
            "canonicalModelId",
            "modelName",
            "modelRef",
            "benchmarkId",
            "benchmarkName",
            "benchmarkVersion",
            "benchmarkVersionHint",
            "benchmarkVersionId",
            "metricId",
            "value",
            "rawValue",
            "unit",
            "evidenceLevel",
            "sourceId",
            "sourceLabel",
            "sourceUrl",
            "sourcePageUrl",
            "sourceApiUrl",
            "sourceLocator",
            "retrievedAt",
            "observedAt",
            "publishedAt",
            "payloadSha256",
            "selectionRank",
            "subjectType",
            "sourceSubjectType",
            "mappingStatus",
        )
        for full, slim in zip(self.full, projected, strict=True):
            self.assertFalse(forbidden & slim.keys(), full["id"])
            for key in direct_fields:
                self.assertEqual(slim.get(key), full.get(key), f"{full['id']}.{key}")
            self.assertEqual(slim.get("protocol", {}), full.get("protocol") or {}, full["id"])
            self.assertEqual(slim.get("qualityFlags", []), full.get("qualityFlags") or [], full["id"])
            self.assertEqual(
                bool(slim.get("matrixExcluded")),
                bool(full.get("matrixExcluded")),
                full["id"],
            )
            self.assertEqual(
                slim.get("matrixExcludedReason"),
                full.get("matrixExcludedReason"),
                full["id"],
            )
            self.assertEqual(
                slim.get("evidenceUrl", slim.get("sourceUrl")),
                full.get("evidenceUrl"),
                full["id"],
            )
            self.assertEqual(
                slim.get("sourceMetricId", slim.get("metricId")),
                full.get("sourceMetricId"),
                full["id"],
            )
            self.assertEqual(
                slim.get("harnessId") or slim.get("harness"),
                full.get("harnessId") or full.get("harness"),
                full["id"],
            )

    def test_real_unmapped_payload_has_at_most_one_compact_example(self) -> None:
        allowed = set(PUBLIC_UNMAPPED_EXAMPLE_FIELDS)
        for group in self.site["publicUnmappedModels"]:
            examples = group.get("examples", [])
            self.assertLessEqual(len(examples), 1, group.get("modelRef"))
            if examples:
                self.assertTrue(set(examples[0]) <= allowed, group.get("modelRef"))


if __name__ == "__main__":
    unittest.main()
