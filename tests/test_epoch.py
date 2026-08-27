import io
import zipfile
import unittest

from scripts.adapters.epoch import EpochBenchmarkAdapter
from scripts.adapters.base import AdapterRun


class EpochAdapterTests(unittest.TestCase):
    def test_parses_headline_scores_and_preserves_external_context(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "gpqa_diamond.csv",
                "Model version,mean_score,Release date,Organization,Source link\n"
                "gpt-5.6-sol,0.901,2026-08-20,OpenAI,https://openai.com/evals\n",
            )
            archive.writestr(
                "terminalbench_external.csv",
                "Model version,Accuracy mean,Agent,Run date\n"
                "claude-opus-5,81.2,openhands,2026-08-21\n",
            )
            archive.writestr(
                "frontierswe_external.csv",
                "Model version,Implementation rank\n"
                "gpt-5.6-sol,3\n",
            )
            archive.writestr(
                "arc_agi_external.csv",
                "Model version,Score\n"
                "gpt-5.6-sol,0.73\n",
            )
        run = AdapterRun(
            source_id="src-epoch-benchmark-hub",
            requested_url=EpochBenchmarkAdapter.URL,
            resolved_url=EpochBenchmarkAdapter.URL,
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload.getvalue(),
        )
        rows = EpochBenchmarkAdapter().parse_payload(run.payload, run)
        self.assertEqual(len(rows), 4)
        gpqa = next(row for row in rows if row["benchmark_ref"] == "gpqa-diamond")
        self.assertAlmostEqual(gpqa["value"], 90.1)
        self.assertEqual(gpqa["raw_value"], "0.901")
        terminal = next(row for row in rows if row["benchmark_ref"] == "epoch-terminalbench_external")
        self.assertEqual(terminal["protocol"]["subject_type"], "system")
        self.assertEqual(terminal["protocol"]["harness"], "openhands")
        rank = next(row for row in rows if row["benchmark_ref"] == "epoch-frontierswe_external")
        self.assertEqual(rank["unit"], "rank")
        fraction = next(row for row in rows if row["benchmark_ref"] == "epoch-arc_agi_external")
        self.assertEqual(fraction["unit"], "fraction")
        self.assertAlmostEqual(fraction["value"], 0.73)


if __name__ == "__main__":
    unittest.main()
