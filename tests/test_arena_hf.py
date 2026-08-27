from __future__ import annotations

import json
import urllib.parse
import unittest
from pathlib import Path

from scripts.adapters.arena import ArenaHFDatasetAdapter, ArenaMetadataAdapter
from scripts.adapters.base import AdapterRun
from scripts.fetch import parse_arena_configs


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class FakeResponse:
    def __init__(self, body: dict):
        self.url = "https://datasets-server.huggingface.co/rows"
        self.status = 200
        self.headers = {"content-type": "application/json"}
        self.body = json.dumps(body).encode("utf-8")
        self.error = None
        self.not_modified = False


class RateLimitedResponse(FakeResponse):
    def __init__(self):
        super().__init__({"error": "rate limited"})
        self.status = 429
        self.error = "HTTP 429: Too Many Requests"


class PagingClient:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, **_kwargs):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        config = query["config"][0]
        offset = int(query["offset"][0])
        self.calls.append((config, offset))
        rows = [
            {
                "row_idx": index,
                "row": {
                    "model_name": f"model-{index}",
                    "rating": 1400 + index,
                    "rating_lower": 1390 + index,
                    "rating_upper": 1410 + index,
                    "variance": 4,
                    "vote_count": 100 + index,
                    "rank": index + 1,
                    "category": "overall",
                    "leaderboard_publish_date": "2026-08-27",
                },
            }
            for index in range(offset, min(offset + 2, 3))
        ]
        return FakeResponse({"num_rows_total": 3, "rows": rows})


class RateLimitedClient:
    def __init__(self):
        self.calls = 0

    def get(self, _url: str, **_kwargs):
        self.calls += 1
        return RateLimitedResponse()


class ArenaHFDatasetTests(unittest.TestCase):
    def test_cli_config_scope_is_explicit_and_bounded(self):
        self.assertIsNone(parse_arena_configs("core"))
        self.assertEqual(parse_arena_configs("text,agent,text"), ("text", "agent"))
        self.assertEqual(
            parse_arena_configs("all"), ArenaHFDatasetAdapter.ALL_CONFIGS
        )
        with self.assertRaises(ValueError):
            parse_arena_configs("not-a-real-arena")

    def test_safe_default_is_one_page(self):
        adapter = ArenaHFDatasetAdapter()
        self.assertEqual(adapter.max_rows_per_config, 100)
        self.assertEqual(adapter.page_size, 100)

    def test_paginates_until_reported_total(self):
        adapter = ArenaHFDatasetAdapter(
            configs=("text",), page_size=2, max_rows_per_config=10
        )
        client = PagingClient()
        run = adapter.fetch(client, retrieved_at="2026-08-27T00:00:00Z")
        self.assertEqual(run.errors, [])
        self.assertEqual(len(run.candidates), 3)
        self.assertEqual(client.calls, [("text", 0), ("text", 2)])
        self.assertEqual(run.metadata["reported_rows"]["text"], 3)
        self.assertFalse(run.metadata["truncated_configs"])

    def test_parses_rating_and_agent_ips_with_ci(self):
        payload = (FIXTURES / "arena_hf_pages.json").read_bytes()
        adapter = ArenaHFDatasetAdapter(configs=("text", "agent"))
        run = AdapterRun(
            source_id=adapter.spec.id,
            requested_url="file://arena-fixture",
            resolved_url="file://arena-fixture",
            retrieved_at="2026-08-27T00:00:00Z",
            http_status=200,
            payload=payload,
        )
        rows = adapter.parse_payload(payload, run)
        self.assertEqual(len(rows), 2)
        rating = rows[0]
        ips = rows[1]
        self.assertEqual(rating["metric"], "arena_score_bt")
        self.assertEqual(rating["unit"], "rating")
        self.assertEqual(rating["value"], 1450.5)
        self.assertEqual(rating["uncertainty"]["lower"], 1440.0)
        self.assertEqual(rating["metadata"]["vote_count"], 1234)
        self.assertEqual(ips["metric"], "ips")
        self.assertEqual(ips["protocol"]["subject_type"], "system")
        self.assertEqual(ips["uncertainty"]["upper"], 0.14)
        self.assertEqual(ips["metadata"]["observation_count"], 9000)
        self.assertIn("config=agent", ips["source_locator"])

    def test_rate_limit_is_reported_without_fabricating_rows(self):
        adapter = ArenaHFDatasetAdapter(configs=("text",), max_rows_per_config=100)
        client = RateLimitedClient()
        run = adapter.fetch(client, retrieved_at="2026-08-27T00:00:00Z")
        self.assertEqual(run.http_status, 429)
        self.assertEqual(run.candidates, [])
        self.assertTrue(any("HTTP 429" in error for error in run.errors))
        self.assertEqual(client.calls, 1)

    def test_disabled_interactive_adapter_never_requests(self):
        class FailingClient:
            def get(self, *_args, **_kwargs):
                raise AssertionError("disabled adapter must not request")

        run = ArenaMetadataAdapter().fetch(
            FailingClient(), retrieved_at="2026-08-27T00:00:00Z"
        )
        self.assertTrue(run.metadata["disabled"])
        self.assertEqual(run.candidates, [])


if __name__ == "__main__":
    unittest.main()
