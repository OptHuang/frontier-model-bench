"""Metadata-only placeholder for LMArena / Chatbot Arena.

Arena's web application and undocumented endpoints change frequently and its
ratings are not a stable public API.  We therefore expose the source in
``list`` for maintenance visibility but refuse to fetch or emit candidates by
default.  A human can add a versioned, licensed snapshot as a separate
adapter once an auditable endpoint is available.
"""

from __future__ import annotations

from typing import Any

from .base import Adapter, AdapterRun, SourceSpec, utc_now


class ArenaMetadataAdapter(Adapter):
    def __init__(self) -> None:
        self.spec = SourceSpec(
            id="lmsys-arena",
            label="LMArena / Chatbot Arena · metadata only (disabled)",
            kind="unstable_web_app",
            url="https://arena.ai/leaderboard",
            cadence="daily",
            enabled=False,
            notes=(
                "Disabled: no stable, documented public score API. Do not "
                "scrape transient frontend bundles or infer ratings from "
                "screenshots. Add a dated, licensed snapshot adapter first."
            ),
        )

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        now = retrieved_at or utc_now()
        return AdapterRun(
            source_id=self.spec.id,
            requested_url=self.spec.url,
            resolved_url=self.spec.url,
            retrieved_at=now,
            http_status=None,
            candidates=[],
            warnings=[self.spec.notes or "adapter disabled"],
            metadata={
                "enabled": False,
                "disabled": True,
                "reason": "unstable_or_undocumented_api",
                "metadata_only": True,
            },
            parser_version=self.spec.parser_version,
        )

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        return []
