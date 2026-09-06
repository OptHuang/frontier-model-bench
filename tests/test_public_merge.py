from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_public_evidence import build_index
from scripts.merge_public_evidence import merge_normalized_rows, read_normalized_rows


NOW = "2026-09-05T23:26:31Z"


def row(identifier="pub-old", **extra):
    value = {
        "id": identifier, "modelRef": "frontier-v2-max", "canonicalModelId": None,
        "sourceId": "source", "sourceUrl": "https://example.org/results.json",
        "sourceLocator": "row=1", "benchmarkId": "math", "metricId": "accuracy",
        "value": 80, "rawValue": "80", "unit": "percent", "protocol": {},
        "status": "reported", "verified": False, "reviewStatus": "unreviewed",
        "verificationStatus": "not_reproduced", "retrievedAt": "2026-09-01T10:00:00Z",
        "payloadSha256": "old-hash", "observedAt": "2026-08-31", "qualityFlags": [],
    }
    value.update(extra)
    return value


class PublicMergeTests(unittest.TestCase):
    def test_preserves_distinct_historical_ids_and_does_not_mutate_input(self):
        baseline = [row(), row("pub-same-fact-other-id"), row("pub-unmapped", modelRef="unknown-v7")]
        original = copy.deepcopy(baseline)
        merged = merge_normalized_rows(baseline, [row("pub-new", value=90)], generated_at=NOW)
        self.assertEqual({r["id"] for r in merged}, {r["id"] for r in baseline} | {"pub-new"})
        self.assertEqual(baseline, original)
        self.assertTrue(all(r["verified"] is False for r in merged))

    def test_same_id_correction_wins_and_keeps_previous_value_and_receipts(self):
        baseline = row(snapshotLocations=[{"artifact": "old/candidates.jsonl", "line": 3,
                                           "retrievedAt": "2026-08-30T00:00:00Z", "payloadSha256": "earlier-hash"}])
        corrected = row(value=81, rawValue="81", retrievedAt="2026-09-05T20:00:00Z", payloadSha256="new-hash")
        merged = merge_normalized_rows([baseline], [corrected], generated_at=NOW)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["value"], 81)
        self.assertEqual(merged[0]["previousReports"][0]["value"], 80)
        self.assertEqual({r["payloadSha256"] for r in merged[0]["snapshotLocations"]},
                         {"earlier-hash", "old-hash", "new-hash"})
        again = merge_normalized_rows(merged, [corrected], generated_at=NOW)
        self.assertEqual(again, merged)

    def test_future_source_dates_are_hidden_without_falsifying_retrieval(self):
        future = row(observedAt="2026-09-07", publishedAt="2026-09-09")
        merged = merge_normalized_rows([future], [], generated_at=NOW)[0]
        self.assertIsNone(merged["observedAt"])
        self.assertIsNone(merged["publishedAt"])
        self.assertEqual(merged["sourceReportedDates"], {"observedAt": "2026-09-07", "publishedAt": "2026-09-09"})
        self.assertEqual(merged["retrievedAt"], future["retrievedAt"])
        self.assertIn("future_source_date", merged["qualityFlags"])

    def test_livebench_historical_table_label_remains_version_only(self):
        old = row(sourceId="livebench-official", observedAt="2026_06_25",
                  protocol={"release_date": "2026_06_25", "harness": "livebench-official-table"})
        merged = merge_normalized_rows([old], [], generated_at=NOW)[0]
        self.assertIsNone(merged["observedAt"])
        self.assertEqual(merged["protocol"]["release_date"], "2026_06_25")
        self.assertEqual(merged["sourceReportedDates"]["observedAt"], "2026_06_25")

    def test_epoch_model_release_is_not_an_observation_date(self):
        old = row(sourceId="src-epoch-benchmark-hub", observedAt="2026-08-31",
                  sourceRow={"metadata": {"release_date": "2026-08-31"}})
        merged = merge_normalized_rows([old], [], generated_at=NOW)[0]
        self.assertIsNone(merged["observedAt"])
        self.assertEqual(merged["sourceReportedDates"]["observedAt"], "2026-08-31")

    def test_generator_remaps_historical_unmapped_and_preserves_other_history(self):
        with tempfile.TemporaryDirectory(prefix="fmb-merge-test-") as directory:
            root = Path(directory)
            catalog = root / "data/catalog"
            catalog.mkdir(parents=True)
            (catalog / "models.json").write_text(json.dumps({"models": [{"id": "acme/frontier-v2@2026", "name": "Frontier V2", "aliases": ["frontier-v2"]}]}))
            for name in ("benchmarks", "sources", "harnesses"):
                (catalog / (name + ".json")).write_text("[]")
            baseline = [row(), row("pub-unmapped", modelRef="unknown-v7")]
            index = build_index(root, [], baseline_rows=baseline, generated_at=NOW)
            self.assertEqual(len(index["rows"]), 1)
            self.assertEqual(index["rows"][0]["canonicalModelId"], "acme/frontier-v2@2026")
            self.assertEqual(index["_omittedRows"][0]["id"], "pub-unmapped")
            self.assertEqual(index["meta"]["generatedAt"], NOW)
            self.assertEqual(index["meta"]["payloadHashes"], ["old-hash"])
            self.assertEqual(index["rows"][0]["retrievedAt"], baseline[0]["retrievedAt"])

    def test_reader_fails_closed_on_candidate_shape_or_approved_input(self):
        with tempfile.TemporaryDirectory(prefix="fmb-merge-read-") as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text(json.dumps({"model_ref": "x", "source_id": "s"}) + "\n")
            with self.assertRaises(ValueError):
                read_normalized_rows([path])
            path.write_text(json.dumps(row(verified=True, status="approved")) + "\n")
            with self.assertRaises(ValueError):
                read_normalized_rows([path])


if __name__ == "__main__":
    unittest.main()
