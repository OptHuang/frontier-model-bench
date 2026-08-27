"""Small dependency-free HTTP client used by source adapters."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping


DEFAULT_USER_AGENT = "frontier-model-bench-source-adapter/0.1 (+https://github.com/OptHuang/frontier-model-bench)"


@dataclass
class HttpResponse:
    url: str
    status: int | None
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    error: str | None = None
    not_modified: bool = False


class HttpClient:
    """Bounded GET client with conditional-request support.

    The client intentionally exposes response metadata (ETag and
    Last-Modified) for manifests.  It follows redirects through urllib but
    records the final URL in the returned response.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_bytes: int = 64 * 1024 * 1024,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        # Optional URL -> cache validator map populated by the CLI from the
        # previous manifest.  Adapters do not need to know about cache files.
        self.conditional: dict[str, dict[str, str]] = {}

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> HttpResponse:
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/csv, text/plain, */*",
        }
        cached = self.conditional.get(url, {})
        etag = etag or cached.get("etag")
        last_modified = last_modified or cached.get("last_modified")
        if headers:
            request_headers.update(headers)
        if etag:
            request_headers["If-None-Match"] = etag
        if last_modified:
            request_headers["If-Modified-Since"] = last_modified
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = self._read_bounded(response)
                response_headers = {
                    str(k).lower(): str(v) for k, v in response.headers.items()
                }
                status = getattr(response, "status", None) or response.getcode()
                return HttpResponse(
                    url=response.geturl(),
                    status=int(status) if status is not None else None,
                    headers=response_headers,
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            response_headers = {
                str(k).lower(): str(v) for k, v in exc.headers.items()
            }
            if exc.code == 304:
                return HttpResponse(
                    url=exc.geturl() or url,
                    status=304,
                    headers=response_headers,
                    not_modified=True,
                )
            # Keep a small error body for diagnostics; never treat it as a
            # candidate payload.
            try:
                body = exc.read(min(self.max_bytes, 64 * 1024))
            except Exception:
                body = b""
            return HttpResponse(
                url=exc.geturl() or url,
                status=exc.code,
                headers=response_headers,
                body=body,
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return HttpResponse(url=url, status=None, error=f"request error: {exc}")

    def _read_bounded(self, response: object) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(1024 * 1024, self.max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise ValueError(
                    f"response exceeds max_bytes={self.max_bytes}; refusing to store it"
                )
            chunks.append(chunk)
        return b"".join(chunks)
