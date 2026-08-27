"""Common contracts for auditable public leaderboard adapters.

The adapters in this directory deliberately stop at *candidate* facts.  A
candidate keeps the name used by the source and its locator; it is not a
canonical observation and is never merged into ``data/observations`` by the
fetch command.  This makes scheduled fetching safe: a broken parser can create
an inspectable diff, but cannot silently change the published dashboard.

Only the Python standard library is used so the same code runs locally and in
the repository's GitHub Actions jobs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


PARSER_VERSION = "0.1.0"
MISSING_MARKERS = {"", "-", "—", "–", "n/a", "na", "null", "none", "unknown"}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a stable ``Z`` suffix."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def slugify(value: Any, *, fallback: str = "unknown") -> str:
    """Make a conservative, readable identifier from source text."""

    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def parse_number(value: Any) -> tuple[float | None, str | None]:
    """Parse a finite number without turning missing markers into zero.

    The second return value is the original textual representation, useful for
    audit output.  Percent signs and thousands separators are accepted; callers
    still decide whether the resulting value is a percent or a fraction.
    """

    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, str(value)
    raw = str(value).strip()
    if raw.lower() in MISSING_MARKERS:
        return None, raw
    cleaned = raw.replace(",", "").replace("%", "").strip()
    # Parenthesised negatives occur in a few CSV exports.
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        number = float(cleaned)
    except (TypeError, ValueError):
        return None, raw
    if not math.isfinite(number):
        return None, raw
    return number, raw


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def candidate_id(source_id: str, payload: Mapping[str, Any]) -> str:
    """Generate a deterministic id for a candidate row.

    The source id and locator are included so two observations of the same
    model/benchmark on different snapshots remain distinct candidates.
    """

    digest = hashlib.sha256(
        (source_id + "\n" + canonical_json(payload)).encode("utf-8")
    ).hexdigest()[:20]
    return f"cand-{slugify(source_id)}-{digest}"


@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str
    kind: str
    url: str
    cadence: str
    enabled: bool = True
    parser_version: str = PARSER_VERSION
    notes: str | None = None


@dataclass
class AdapterRun:
    """Result of one adapter fetch/parse cycle."""

    source_id: str
    requested_url: str
    resolved_url: str
    retrieved_at: str
    http_status: int | None
    headers: dict[str, str] = field(default_factory=dict)
    payload: bytes = b""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    not_modified: bool = False
    parser_version: str = PARSER_VERSION

    @property
    def payload_sha256(self) -> str | None:
        if not self.payload:
            return None
        return hashlib.sha256(self.payload).hexdigest()


class Adapter:
    """Minimal adapter interface.

    Subclasses implement ``parse_payload`` and may override ``fetch`` when a
    source requires discovery (for example, selecting the newest LiveBench
    CSV or HELM release).  ``fetch`` never writes files.
    """

    spec: SourceSpec

    def fetch(self, client: Any, *, retrieved_at: str | None = None) -> AdapterRun:
        now = retrieved_at or utc_now()
        if not self.spec.enabled:
            return AdapterRun(
                source_id=self.spec.id,
                requested_url=self.spec.url,
                resolved_url=self.spec.url,
                retrieved_at=now,
                http_status=None,
                warnings=[self.spec.notes or "adapter disabled"],
                metadata={"enabled": False, "disabled": True},
                parser_version=self.spec.parser_version,
            )

        response = client.get(self.spec.url)
        run = AdapterRun(
            source_id=self.spec.id,
            requested_url=self.spec.url,
            resolved_url=response.url or self.spec.url,
            retrieved_at=now,
            http_status=response.status,
            headers=response.headers,
            payload=response.body,
            parser_version=self.spec.parser_version,
        )
        if response.error:
            run.errors.append(response.error)
        if response.not_modified:
            run.not_modified = True
            run.metadata["not_modified"] = True
            return run
        if response.status is not None and not (200 <= response.status < 300):
            run.errors.append(f"HTTP status {response.status}")
            return run
        if run.payload:
            try:
                run.candidates = self.parse_payload(run.payload, run)
            except Exception as exc:  # adapters must report, not crash a batch
                run.errors.append(f"parse error: {type(exc).__name__}: {exc}")
        return run

    def parse_payload(self, payload: bytes, run: AdapterRun) -> list[dict[str, Any]]:
        raise NotImplementedError

    def make_candidate(
        self,
        run: AdapterRun,
        *,
        model_ref: Any,
        benchmark_ref: Any,
        metric: str,
        value: Any,
        unit: str,
        raw_value: Any = None,
        locator: str | None = None,
        rank: Any = None,
        verified: bool | None = None,
        status: str = "candidate",
        evidence_level: str = "C",
        comparability: str = "conditional",
        protocol: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        quality_flags: Sequence[str] | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        number, parsed_raw = parse_number(value)
        if raw_value is None:
            raw_value = parsed_raw if parsed_raw is not None else value
        candidate: dict[str, Any] = {
            "source_id": run.source_id,
            "source_url": run.resolved_url,
            "source_locator": locator,
            "model_ref": str(model_ref).strip() if model_ref is not None else None,
            "benchmark_ref": str(benchmark_ref).strip()
            if benchmark_ref is not None
            else None,
            "metric": metric,
            "value": number,
            "raw_value": raw_value,
            "unit": unit,
            "rank": rank,
            "verified": verified,
            "status": status,
            "evidence_level": evidence_level,
            "comparability": comparability,
            "protocol": dict(protocol or {}),
            "observed_at": observed_at,
            "retrieved_at": run.retrieved_at,
            "quality_flags": list(quality_flags or []),
            "metadata": dict(metadata or {}),
            # Mapping is intentionally a later human/review step.
            "mapping_status": "unmatched",
            "canonical_model_id": None,
        }
        if number is None and candidate["raw_value"] not in (None, ""):
            candidate["quality_flags"].append("non_numeric_or_missing")
        candidate["candidate_id"] = candidate_id(run.source_id, candidate)
        return candidate


def json_loads(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8-sig"))


def rows_from_json(value: Any) -> Iterable[Mapping[str, Any]]:
    """Yield rows from common leaderboard JSON envelopes."""

    if isinstance(value, list):
        yield from (row for row in value if isinstance(row, Mapping))
        return
    if not isinstance(value, Mapping):
        return
    for key in ("results", "rows", "entries", "leaderboard", "data"):
        nested = value.get(key)
        if isinstance(nested, list):
            yield from (row for row in nested if isinstance(row, Mapping))
            return
        if isinstance(nested, Mapping):
            yield from rows_from_json(nested)
            return
