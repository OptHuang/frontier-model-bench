"""Incomplete HTTP payloads must not become plausible leaderboard candidates."""
import io
import http.client
import json
import unittest
from unittest.mock import patch

from scripts.adapters.http import HttpClient
from scripts.adapters.livebench import LiveBenchAdapter


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, declared_length=None):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if declared_length is None else declared_length)}

    def geturl(self):
        return "https://example.org/public/table_2026_06_25.csv"


class HttpIntegrityTests(unittest.TestCase):
    def test_early_eof_is_not_a_successful_payload(self):
        with patch("urllib.request.urlopen", return_value=Response(b"Model,Score\nqwen3.8-fl", 100)):
            result = HttpClient().get("https://example.org/table.csv")
        self.assertIsNotNone(result.error, "truncated HTTP 200 was accepted as complete")
        self.assertEqual(result.body, b"", "partial CSV escaped into parser input")

    def test_livebench_cannot_emit_fake_model_from_truncated_row(self):
        tree = json.dumps({"tree": [{"type": "blob", "path": "public/table_2026_06_25.csv"}]}).encode()
        responses = [Response(tree), Response(b"Model,Score\nqwen3.8-fl", 100)]
        with patch("urllib.request.urlopen", side_effect=responses):
            run = LiveBenchAdapter().fetch(HttpClient())
        self.assertTrue(run.errors)
        self.assertEqual(run.candidates, [], "incomplete transfer created a fake model alias")

    def test_valid_fragmented_download_is_read_to_completion(self):
        class Fragmented(Response):
            def read(self, size=-1):
                return super().read(min(size, 3))
        body = b"Model,Score\nqwen3.8-flash,99\n"
        with patch("urllib.request.urlopen", return_value=Fragmented(body)):
            result = HttpClient().get("https://example.org/table.csv")
        self.assertIsNone(result.error)
        self.assertEqual(result.body, body)

    def test_absent_length_and_chunked_framing_are_supported(self):
        for headers in ({}, {"Transfer-Encoding": "chunked", "Content-Length": "999"}):
            with self.subTest(headers=headers):
                response = Response(b"complete")
                response.headers = headers
                with patch("urllib.request.urlopen", return_value=response):
                    result = HttpClient().get("https://example.org/table.csv")
                self.assertIsNone(result.error)
                self.assertEqual(result.body, b"complete")

    def test_incomplete_read_exception_is_a_failed_receipt_not_payload(self):
        class Broken(Response):
            def read(self, size=-1):
                raise http.client.IncompleteRead(b"partial", 100)
        with patch("urllib.request.urlopen", return_value=Broken(b"partial", 107)):
            result = HttpClient().get("https://example.org/table.csv")
        self.assertIn("IncompleteRead", result.error)
        self.assertEqual(result.status, 200)
        self.assertEqual(result.headers["content-length"], "107")
        self.assertEqual(result.body, b"")

    def test_oversized_and_invalid_length_responses_fail_closed(self):
        with patch("urllib.request.urlopen", return_value=Response(b"too long")):
            result = HttpClient(max_bytes=3).get("https://example.org/table.csv")
        self.assertIn("max_bytes", result.error)
        self.assertEqual(result.body, b"")
        for length in ("invalid", "-1", "2, 3"):
            with self.subTest(length=length):
                with patch("urllib.request.urlopen", return_value=Response(b"ok", length)):
                    result = HttpClient().get("https://example.org/table.csv")
                self.assertIn("Content-Length", result.error)
                self.assertEqual(result.body, b"")

    def test_complete_livebench_still_parses(self):
        tree = json.dumps({"tree": [{"type": "blob", "path": "public/table_2026_06_25.csv"}]}).encode()
        with patch("urllib.request.urlopen", side_effect=[Response(tree), Response(b"Model,Score\nqwen3.8-flash,99\n")]):
            run = LiveBenchAdapter().fetch(HttpClient())
        self.assertFalse(run.errors)
        self.assertEqual(len(run.candidates), 1)
        self.assertEqual(run.candidates[0]["model_ref"], "qwen3.8-flash")
        self.assertEqual(run.candidates[0]["value"], 99)


if __name__ == "__main__":
    unittest.main()
