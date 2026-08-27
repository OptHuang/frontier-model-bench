#!/usr/bin/env python3
"""Validate the Frontier Model Bench seed/normalized data contract.

The first version of the site stores a nested ``data/models.json`` file.  This
validator intentionally accepts that shape while enforcing the invariants that
also apply to the future long-form observation store:

* ids are present and unique;
* scores are finite numbers within the declared benchmark scale;
* score references point to known benchmarks and sources;
* missing values are explicit and are never represented by a dash or by zero.

No third-party package is required.  The script is suitable for a GitHub
Actions check as well as a local pre-commit check.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "models.json"
)
DEFAULT_CANONICAL_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CATALOG_DIR = DEFAULT_CANONICAL_ROOT / "data" / "catalog"
CANONICAL_OBSERVATIONS_PATH = (
    DEFAULT_CANONICAL_ROOT / "data" / "observations" / "results.jsonl"
)

# Slashes and @ are intentional: the target canonical model id is commonly
# ``provider/family@release``.  We warn, rather than fail, for other printable
# characters so that a source-specific id can be migrated without blocking all
# data checks.
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+~\-]*$")
MISSING_MARKERS = {"", "-", "—", "–", "n/a", "na", "none", "null", "unknown"}
KNOWN_STATUS = {
    "active",
    "deprecated",
    "retired",
    "published",
    "candidate",
    "superseded",
    "retracted",
    "conflict",
    "verified",
    "reproduced",
    "reported",
    "unverified",
    "curated",
    "seed",
    "demo",
    "missing",
    "legacy",
    "preview",
    "restricted",
    "catalog-only",
    "draft",
    "approved",
    "current",
    "previous",
}
KNOWN_COMPARABILITY = {"exact", "conditional", "none"}


@dataclass(frozen=True)
class Issue:
    level: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"level": self.level, "path": self.path, "message": self.message}


class DataValidator:
    """Collect errors and warnings while checking one data document."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.benchmark_bounds: dict[str, tuple[float, float]] = {}

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue("error", path, message))

    def warning(self, path: str, message: str) -> None:
        self.issues.append(Issue("warning", path, message))

    def check(self, document: Any) -> dict[str, int]:
        if not isinstance(document, Mapping):
            self.error("$", "顶层必须是 JSON object")
            return {"models": 0, "benchmarks": 0, "sources": 0, "scores": 0}

        self._check_meta(document.get("meta"))
        benchmarks = self._as_list(document, "benchmarks")
        models = self._as_list(document, "models")
        sources = self._as_list(document, "sources")

        source_ids = self._check_sources(sources)
        benchmark_ids = self._check_benchmarks(benchmarks, source_ids)
        score_count = self._check_models(models, benchmark_ids, source_ids)

        # Empty registries are legal while scaffolding a new site, but warn so
        # a scheduled data job cannot silently publish a blank dashboard.
        if not benchmarks:
            self.warning("benchmarks", "没有 benchmark；页面将没有可比较的列")
        if not models:
            self.warning("models", "没有模型；页面将为空")
        if not sources:
            self.warning("sources", "没有来源 registry；成绩无法显示证据链接")

        return {
            "models": len(models),
            "benchmarks": len(benchmarks),
            "sources": len(sources),
            "scores": score_count,
        }

    def _as_list(self, document: Mapping[str, Any], key: str) -> list[Any]:
        value = document.get(key)
        if value is None:
            self.error(key, "缺少必填数组")
            return []
        if not isinstance(value, list):
            self.error(key, "必须是 JSON array")
            return []
        return value

    def _check_meta(self, meta: Any) -> None:
        if meta is None:
            self.error("meta", "缺少 meta object")
            return
        if not isinstance(meta, Mapping):
            self.error("meta", "必须是 JSON object")
            return

        for key in ("asOf", "lastUpdated"):
            if key in meta and meta[key] is not None:
                if not _is_iso_date(meta[key]):
                    self.error(f"meta.{key}", "必须是 ISO 日期或 ISO datetime")
        if "version" in meta and not _is_nonempty_string(meta["version"]):
            self.error("meta.version", "必须是非空字符串")
        if "status" in meta:
            self._check_status(meta["status"], "meta.status")

    def _check_benchmarks(
        self,
        benchmarks: Sequence[Any],
        source_ids: set[str],
    ) -> set[str]:
        ids: set[str] = set()
        for index, benchmark in enumerate(benchmarks):
            path = f"benchmarks[{index}]"
            if not isinstance(benchmark, Mapping):
                self.error(path, "必须是 JSON object")
                continue
            identifier = self._check_id(benchmark.get("id"), f"{path}.id")
            if identifier is not None:
                if identifier in ids:
                    self.error(f"{path}.id", f"重复 id: {identifier}")
                ids.add(identifier)

            for key in ("name", "metric", "unit"):
                if key in benchmark and not _is_nonempty_string(benchmark[key]):
                    self.error(f"{path}.{key}", "必须是非空字符串")

            scale = benchmark.get("scale")
            bounds = _scale_bounds(scale)
            if bounds is None:
                self.error(
                    f"{path}.scale",
                    "必须是正数，或包含有限 min/max 的 object",
                )
            elif bounds[0] >= bounds[1]:
                self.error(f"{path}.scale", "scale.min 必须小于 scale.max")
            elif identifier is not None:
                self.benchmark_bounds[identifier] = bounds

            direction = benchmark.get("direction")
            if direction not in ("higher", "lower"):
                self.error(
                    f"{path}.direction",
                    "必须为 higher 或 lower",
                )

            if "source" in benchmark:
                self._check_url(benchmark["source"], f"{path}.source")
            elif "sourceId" not in benchmark:
                self.warning(path, "缺少 source/sourceId；benchmark 定义无法回溯")

            if "sourceId" in benchmark:
                source_id = benchmark["sourceId"]
                if not _is_nonempty_string(source_id):
                    self.error(f"{path}.sourceId", "必须是非空字符串")
                elif source_id not in source_ids:
                    self.error(f"{path}.sourceId", f"未知 source id: {source_id}")

            if "lastVerified" in benchmark and benchmark["lastVerified"] is not None:
                if not _is_iso_date(benchmark["lastVerified"]):
                    self.error(
                        f"{path}.lastVerified",
                        "必须是 ISO 日期或 ISO datetime",
                    )

            versions = benchmark.get("versions")
            if versions is not None:
                self._check_nested_registry(versions, f"{path}.versions")

            metrics = benchmark.get("metrics")
            if metrics is not None:
                self._check_nested_registry(metrics, f"{path}.metrics")

        return ids

    def _check_sources(self, sources: Sequence[Any]) -> set[str]:
        ids: set[str] = set()
        for index, source in enumerate(sources):
            path = f"sources[{index}]"
            if not isinstance(source, Mapping):
                self.error(path, "必须是 JSON object")
                continue
            identifier = self._check_id(source.get("id"), f"{path}.id")
            if identifier is not None:
                if identifier in ids:
                    self.error(f"{path}.id", f"重复 id: {identifier}")
                ids.add(identifier)
            for key in ("label", "kind"):
                if key in source and not _is_nonempty_string(source[key]):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            if "url" in source:
                self._check_url(source["url"], f"{path}.url")
            else:
                self.warning(path, "source 没有 url；用户无法打开原始证据")
            if "api_url" in source and source["api_url"] is not None:
                self._check_url(source["api_url"], f"{path}.api_url")
            if "default_evidence_level" in source:
                self._check_evidence_level(
                    source["default_evidence_level"],
                    f"{path}.default_evidence_level",
                )
            if "staleness_after_days" in source:
                value = source["staleness_after_days"]
                if not _is_finite_number(value) or value <= 0:
                    self.error(
                        f"{path}.staleness_after_days",
                        "必须是正数",
                    )
        return ids

    def _check_models(
        self,
        models: Sequence[Any],
        benchmark_ids: set[str],
        source_ids: set[str],
    ) -> int:
        model_ids: set[str] = set()
        score_count = 0
        for index, model in enumerate(models):
            path = f"models[{index}]"
            if not isinstance(model, Mapping):
                self.error(path, "必须是 JSON object")
                continue
            identifier = self._check_id(model.get("id"), f"{path}.id")
            if identifier is not None:
                if identifier in model_ids:
                    self.error(f"{path}.id", f"重复 id: {identifier}")
                model_ids.add(identifier)

            for key in ("name", "provider"):
                if key in model and not _is_nonempty_string(model[key]):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            if "release" in model and model["release"] is not None:
                if not _is_iso_date(model["release"]):
                    self.warning(
                        f"{path}.release",
                        "不是 ISO 日期；如为自由文本请迁移到 metadata.release_label",
                    )
            if "overall" in model:
                self._check_number(
                    model["overall"],
                    f"{path}.overall",
                    bounds=(0.0, 100.0),
                    allow_null=True,
                )
            if "trend" in model:
                trend = model["trend"]
                if not isinstance(trend, list):
                    self.error(f"{path}.trend", "必须是数组")
                else:
                    for trend_index, value in enumerate(trend):
                        self._check_number(
                            value,
                            f"{path}.trend[{trend_index}]",
                            bounds=(0.0, 100.0),
                            allow_null=False,
                        )

            scores = model.get("scores")
            if scores is None:
                self.warning(path, "没有 scores；该模型没有可显示的成绩")
                continue
            if not isinstance(scores, Mapping):
                self.error(f"{path}.scores", "必须是以 benchmark id 为键的 object")
                continue
            for benchmark_id, score in scores.items():
                score_path = f"{path}.scores[{benchmark_id!r}]"
                score_count += 1
                if not _is_nonempty_string(benchmark_id):
                    self.error(score_path, "benchmark key 必须是非空字符串")
                elif benchmark_id not in benchmark_ids:
                    self.error(score_path, f"未知 benchmark id: {benchmark_id}")
                self._check_score(
                    score,
                    score_path,
                    benchmark_id,
                    benchmark_bounds=self.benchmark_bounds,
                    source_ids=source_ids,
                )

        return score_count

    def _check_score(
        self,
        score: Any,
        path: str,
        benchmark_id: str,
        benchmark_bounds: Mapping[str, tuple[float, float]],
        source_ids: set[str],
    ) -> None:
        if score is None:
            self.error(path, "score 不能直接为 null；请使用 object + missing_reason")
            return
        if not isinstance(score, Mapping):
            self.error(path, "必须是 score object，不能用数字/字符串占位")
            return
        if "value" not in score:
            self.error(path, "缺少 value；若不可用请写 value:null + missing_reason")
        else:
            value = score["value"]
            legacy_missing = (
                score.get("missing") is True
                or score.get("status") == "missing"
                or score.get("verified") == "missing"
            )
            if value is None:
                reason = score.get("missing_reason") or score.get("reason")
                if not _is_nonempty_string(reason) and not legacy_missing:
                    self.error(
                        f"{path}.value",
                        "null 必须同时提供 missing_reason 或 status=missing",
                    )
                elif not _is_nonempty_string(reason):
                    self.warning(
                        f"{path}.value",
                        "legacy demo 使用 verified/status=missing；迁移到 missing_reason 字段",
                    )
            elif isinstance(value, str):
                marker = value.strip().lower()
                if marker in MISSING_MARKERS:
                    self.error(
                        f"{path}.value",
                        "禁止用破折号/空字符串表示缺失；请使用 value:null + missing_reason",
                    )
                else:
                    self.error(
                        f"{path}.value",
                        "必须是有限数字，不能使用数字字符串",
                    )
            elif not _is_finite_number(value):
                self.error(f"{path}.value", "必须是有限数字或带理由的 null")
            else:
                missing_flag = score.get("missing") is True or score.get("status") == "missing"
                if missing_flag:
                    self.error(
                        f"{path}.value",
                        "status=missing 时 value 必须为 null；真实的 0 分不要标为 missing",
                    )
                bounds = benchmark_bounds.get(benchmark_id)
                if bounds is not None and not (bounds[0] <= float(value) <= bounds[1]):
                    self.error(
                        f"{path}.value",
                        f"数值 {value} 超出 benchmark scale "
                        f"[{_format_number(bounds[0])}, {_format_number(bounds[1])}]",
                    )

        uncertainty = score.get("uncertainty")
        if uncertainty is not None:
            self._check_uncertainty(uncertainty, f"{path}.uncertainty", benchmark_bounds.get(benchmark_id))

        if "raw_value" in score and score["raw_value"] is not None:
            if not isinstance(score["raw_value"], (str, int, float)):
                self.error(f"{path}.raw_value", "必须是字符串或数字")
        if "setting" in score and score["setting"] is not None:
            if not _is_nonempty_string(score["setting"]):
                self.error(f"{path}.setting", "必须是非空字符串")
        if "sourceId" in score:
            source_id = score["sourceId"]
            missing_value = score.get("value") is None and (
                score.get("missing") is True
                or score.get("status") == "missing"
                or score.get("verified") == "missing"
            )
            if source_id is None and missing_value:
                # An unavailable score has no source row to link.  Keep this
                # legal for the demo while asking future normalized records to
                # provide a reason/evidence for the absence.
                pass
            elif not _is_nonempty_string(source_id):
                self.error(f"{path}.sourceId", "必须是非空字符串")
            elif source_id not in source_ids:
                self.error(f"{path}.sourceId", f"未知 source id: {source_id}")
        else:
            # A deliberate missing observation can be source-less when the
            # reason itself is recorded.  Non-missing numbers still need a
            # source link so the UI can open the evidence chain.
            if not (score.get("value") is None and _is_nonempty_string(score.get("missing_reason") or score.get("reason"))):
                self.warning(path, "score 没有 sourceId；无法展示逐条证据")

        if "verified" in score:
            self._check_status(score["verified"], f"{path}.verified")
        if "status" in score:
            self._check_status(score["status"], f"{path}.status")
        if "evidence_level" in score:
            self._check_evidence_level(score["evidence_level"], f"{path}.evidence_level")
        if "observed_at" in score and score["observed_at"] is not None:
            if not _is_iso_date(score["observed_at"]):
                self.error(f"{path}.observed_at", "必须是 ISO 日期或 ISO datetime")

    def _check_nested_registry(self, value: Any, path: str) -> None:
        if not isinstance(value, list):
            self.error(path, "必须是数组")
            return
        ids: set[str] = set()
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, Mapping):
                self.error(item_path, "必须是 object")
                continue
            if "id" in item:
                identifier = self._check_id(item["id"], f"{item_path}.id")
                if identifier is not None:
                    if identifier in ids:
                        self.error(f"{item_path}.id", f"重复 id: {identifier}")
                    ids.add(identifier)

    def _check_id(self, value: Any, path: str) -> str | None:
        if not _is_nonempty_string(value):
            self.error(path, "必须是非空字符串")
            return None
        if any(char.isspace() for char in value):
            self.error(path, "不能包含空白字符")
        if value.strip().lower() in MISSING_MARKERS:
            self.error(path, "不能使用缺失占位符作为 id")
        if not ID_PATTERN.fullmatch(value):
            self.warning(path, "包含非标准 slug 字符；请确认跨来源引用稳定")
        return value

    def _check_url(self, value: Any, path: str) -> None:
        if not _is_nonempty_string(value):
            self.error(path, "必须是非空 URL 字符串")
            return
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.error(path, "必须是 http(s) URL")

    def _check_number(
        self,
        value: Any,
        path: str,
        bounds: tuple[float, float] | None,
        allow_null: bool,
    ) -> None:
        if value is None and allow_null:
            return
        if not _is_finite_number(value):
            self.error(path, "必须是有限数字" + (" 或 null" if allow_null else ""))
            return
        if bounds is not None and not (bounds[0] <= float(value) <= bounds[1]):
            self.error(
                path,
                f"数值 {value} 超出范围 [{_format_number(bounds[0])}, {_format_number(bounds[1])}]",
            )

    def _check_uncertainty(
        self,
        value: Any,
        path: str,
        bounds: tuple[float, float] | None,
    ) -> None:
        if not isinstance(value, Mapping):
            self.error(path, "必须是 object（例如 type/level/lower/upper）")
            return
        kind = value.get("type")
        if not _is_nonempty_string(kind):
            self.error(f"{path}.type", "必须是非空字符串")
        if "level" in value:
            level = value["level"]
            if not _is_finite_number(level) or not 0 < float(level) < 1:
                self.error(f"{path}.level", "必须在 (0, 1) 内")
        lower = value.get("lower")
        upper = value.get("upper")
        if lower is not None:
            self._check_number(lower, f"{path}.lower", bounds, allow_null=False)
        if upper is not None:
            self._check_number(upper, f"{path}.upper", bounds, allow_null=False)
        if _is_finite_number(lower) and _is_finite_number(upper) and float(lower) > float(upper):
            self.error(path, "uncertainty.lower 不能大于 upper")

    def _check_status(self, value: Any, path: str) -> None:
        if not _is_nonempty_string(value):
            self.error(path, "必须是非空字符串")
        elif value not in KNOWN_STATUS:
            self.warning(path, f"未登记的 status: {value}")

    def _check_evidence_level(self, value: Any, path: str) -> None:
        if value not in {"A", "B", "C", "D"}:
            self.error(path, "必须为 A、B、C 或 D")


class CanonicalBundleValidator:
    """Validate the registry/JSONL form used by the update pipeline.

    The legacy validator above intentionally remains independent so old seed
    files can still be checked.  This checker adds reference and protocol
    checks for ``data/catalog`` and ``data/observations`` without requiring a
    third-party schema package.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.issues: list[Issue] = []
        self.models: list[Mapping[str, Any]] = []
        self.benchmarks: list[Mapping[str, Any]] = []
        self.sources: list[Mapping[str, Any]] = []
        self.harnesses: list[Mapping[str, Any]] = []
        self.presets: list[Mapping[str, Any]] = []
        self.model_ids: set[str] = set()
        self.benchmark_ids: set[str] = set()
        self.source_ids: set[str] = set()
        self.harness_ids: set[str] = set()
        self.benchmark_map: dict[str, Mapping[str, Any]] = {}
        self.metric_map: dict[tuple[str, str], Mapping[str, Any]] = {}
        self.observation_count = 0
        self.numeric_observation_count = 0

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue("error", path, message))

    def warning(self, path: str, message: str) -> None:
        self.issues.append(Issue("warning", path, message))

    def check(self) -> dict[str, int]:
        catalog_dir = self.root / "data" / "catalog"
        self.sources = self._load_registry(catalog_dir / "sources.json", "sources")
        self.models = self._load_registry(catalog_dir / "models.json", "models")
        self.benchmarks = self._load_registry(catalog_dir / "benchmarks.json", "benchmarks")
        self.harnesses = self._load_registry(catalog_dir / "harnesses.json", "harnesses")
        self.presets = self._load_registry(catalog_dir / "presets.json", "presets")

        self.source_ids = self._check_registry_ids(self.sources, "sources")
        self.model_ids = self._check_registry_ids(self.models, "models")
        self.benchmark_ids = self._check_registry_ids(self.benchmarks, "benchmarks")
        self.harness_ids = self._check_registry_ids(self.harnesses, "harnesses")
        self.benchmark_map = {
            str(item.get("id")): item
            for item in self.benchmarks
            if isinstance(item.get("id"), str)
        }
        self._check_sources()
        self._check_models()
        self._check_benchmarks()
        self._check_harnesses()
        self._check_presets()
        self._check_observations(self.root / "data" / "observations" / "results.jsonl")

        return {
            "models": len(self.models),
            "benchmarks": len(self.benchmarks),
            "sources": len(self.sources),
            "harnesses": len(self.harnesses),
            "presets": len(self.presets),
            "observations": self.observation_count,
            "numeric_observations": self.numeric_observation_count,
        }

    def _load_registry(self, path: Path, key: str) -> list[Mapping[str, Any]]:
        if not path.is_file():
            self.error(str(path.relative_to(self.root)), "缺少 canonical registry 文件")
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            self.error(str(path.relative_to(self.root)), f"JSON 无法解析: {exc.msg}")
            return []
        value = payload.get(key) if isinstance(payload, Mapping) else payload
        if not isinstance(value, list):
            self.error(str(path.relative_to(self.root)), f"必须是 array，或包含 {key} array 的 object")
            return []
        return [item for item in value if isinstance(item, Mapping)]

    def _check_registry_ids(self, items: Sequence[Mapping[str, Any]], label: str) -> set[str]:
        ids: set[str] = set()
        for index, item in enumerate(items):
            path = f"canonical.{label}[{index}]"
            identifier = item.get("id")
            if not _is_nonempty_string(identifier):
                self.error(f"{path}.id", "必须是非空字符串")
                continue
            if identifier in ids:
                self.error(f"{path}.id", f"重复 id: {identifier}")
            ids.add(identifier)
            if any(char.isspace() for char in identifier):
                self.error(f"{path}.id", "不能包含空白字符")
        return ids

    def _check_source_refs(self, values: Any, path: str, required: bool = False) -> list[str]:
        if isinstance(values, str):
            values = [values]
        if values is None:
            values = []
        if not isinstance(values, list):
            self.error(path, "必须是字符串数组")
            return []
        refs = [value for value in values if isinstance(value, str) and value]
        if required and not refs:
            self.error(path, "至少需要一个 source id")
        for index, value in enumerate(refs):
            if value not in self.source_ids:
                self.error(f"{path}[{index}]", f"未知 source id: {value}")
        return refs

    def _check_sources(self) -> None:
        for index, source in enumerate(self.sources):
            path = f"canonical.sources[{index}]"
            for key in ("label", "kind"):
                if not _is_nonempty_string(source.get(key)):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            url = source.get("url")
            if url is not None:
                self._check_url_value(url, f"{path}.url")
            else:
                self.error(f"{path}.url", "canonical source 必须提供 URL")
            if source.get("api_url") is not None:
                self._check_url_value(source["api_url"], f"{path}.api_url")
            if source.get("default_evidence_level") is not None:
                self._check_evidence(source["default_evidence_level"], f"{path}.default_evidence_level")
            stale = source.get("staleness_after_days")
            if stale is not None and (not _is_finite_number(stale) or float(stale) <= 0):
                self.error(f"{path}.staleness_after_days", "必须是正数")

    def _check_models(self) -> None:
        for index, model in enumerate(self.models):
            path = f"canonical.models[{index}]"
            for key in ("name", "provider", "family_id"):
                if not _is_nonempty_string(model.get(key)):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            release = model.get("release_date", model.get("release"))
            if release is not None and not _is_iso_date(release):
                self.error(f"{path}.release_date", "必须是 ISO 日期或 null")
            status = model.get("status")
            if status is not None:
                self._check_status_value(status, f"{path}.status")
            self._check_source_refs(model.get("source_ids", model.get("sourceIds", [])), f"{path}.source_ids", required=True)
            modalities = model.get("modalities")
            if modalities is not None and (not isinstance(modalities, list) or any(not isinstance(item, str) for item in modalities)):
                self.error(f"{path}.modalities", "必须是字符串数组")
            for field in ("context_window", "params_total", "params_active"):
                value = model.get(field)
                if value is not None and (not _is_finite_number(value) or float(value) < 0):
                    self.error(f"{path}.{field}", "必须是非负有限数字或 null")
            total = model.get("params_total")
            active = model.get("params_active")
            if _is_finite_number(total) and _is_finite_number(active) and float(active) > float(total):
                self.error(f"{path}.params_active", "不能大于 params_total")

    def _check_benchmarks(self) -> None:
        for index, benchmark in enumerate(self.benchmarks):
            path = f"canonical.benchmarks[{index}]"
            for key in ("name", "category"):
                if not _is_nonempty_string(benchmark.get(key)):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            self._check_source_refs(benchmark.get("source_ids", benchmark.get("sourceIds", [])), f"{path}.source_ids", required=True)
            versions = benchmark.get("versions")
            version_ids: set[str] = set()
            if not isinstance(versions, list) or not versions:
                self.error(f"{path}.versions", "必须是非空版本数组")
            else:
                for version_index, version in enumerate(versions):
                    version_path = f"{path}.versions[{version_index}]"
                    if not isinstance(version, Mapping) or not _is_nonempty_string(version.get("id")):
                        self.error(version_path, "必须是包含非空 id 的 object")
                        continue
                    version_id = str(version["id"])
                    if version_id in version_ids:
                        self.error(f"{version_path}.id", f"重复 version id: {version_id}")
                    version_ids.add(version_id)
            default_version = benchmark.get("default_version_id")
            if default_version is not None and default_version not in version_ids:
                self.error(f"{path}.default_version_id", f"未知 version id: {default_version}")
            metrics = benchmark.get("metrics")
            metric_ids: set[str] = set()
            if not isinstance(metrics, list) or not metrics:
                self.error(f"{path}.metrics", "必须是非空 metric 数组")
            else:
                for metric_index, metric in enumerate(metrics):
                    metric_path = f"{path}.metrics[{metric_index}]"
                    if not isinstance(metric, Mapping) or not _is_nonempty_string(metric.get("id")):
                        self.error(metric_path, "必须是包含非空 id 的 object")
                        continue
                    metric_id = str(metric["id"])
                    if metric_id in metric_ids:
                        self.error(f"{metric_path}.id", f"重复 metric id: {metric_id}")
                    metric_ids.add(metric_id)
                    self.metric_map[(str(benchmark.get("id")), metric_id)] = metric
                    bounds = _scale_bounds(metric.get("scale"))
                    if bounds is None or bounds[0] >= bounds[1]:
                        self.error(f"{metric_path}.scale", "必须包含有效 min/max 范围")
                    if metric.get("direction") not in {"higher", "lower"}:
                        self.error(f"{metric_path}.direction", "必须为 higher 或 lower")
                    if not _is_nonempty_string(metric.get("unit")):
                        self.error(f"{metric_path}.unit", "必须是非空字符串")
            default_metric = benchmark.get("default_metric_id")
            if default_metric is not None and default_metric not in metric_ids:
                self.error(f"{path}.default_metric_id", f"未知 metric id: {default_metric}")

    def _check_harnesses(self) -> None:
        for index, harness in enumerate(self.harnesses):
            path = f"canonical.harnesses[{index}]"
            for key in ("name", "kind", "status"):
                if not _is_nonempty_string(harness.get(key)):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            self._check_status_value(harness.get("status"), f"{path}.status")
            self._check_source_refs(harness.get("source_ids", harness.get("sourceIds", [])), f"{path}.source_ids")

    def _check_presets(self) -> None:
        for index, preset in enumerate(self.presets):
            path = f"canonical.presets[{index}]"
            for key in ("id", "label", "description"):
                if not _is_nonempty_string(preset.get(key)):
                    self.error(f"{path}.{key}", "必须是非空字符串")
            benchmark_ids = preset.get("benchmark_ids", preset.get("benchmarkIds", []))
            if isinstance(benchmark_ids, str):
                benchmark_ids = [benchmark_ids]
            if benchmark_ids is not None and not isinstance(benchmark_ids, list):
                self.error(f"{path}.benchmark_ids", "必须是字符串数组")
            elif isinstance(benchmark_ids, list):
                for item_index, benchmark_id in enumerate(benchmark_ids):
                    if benchmark_id not in self.benchmark_ids:
                        self.error(f"{path}.benchmark_ids[{item_index}]", f"未知 benchmark id: {benchmark_id}")
            harness_ids = preset.get("harness_ids", preset.get("harnessIds", []))
            if isinstance(harness_ids, str):
                harness_ids = [harness_ids]
            if harness_ids is not None and not isinstance(harness_ids, list):
                self.error(f"{path}.harness_ids", "必须是字符串数组")
            elif isinstance(harness_ids, list):
                for item_index, harness_id in enumerate(harness_ids):
                    if harness_id not in self.harness_ids:
                        self.error(f"{path}.harness_ids[{item_index}]", f"未知 harness id: {harness_id}")

    def _check_observations(self, path: Path) -> None:
        if not path.is_file():
            self.error(str(path.relative_to(self.root)), "缺少 observations/results.jsonl")
            return
        seen_ids: set[str] = set()
        seen_keys: set[tuple[Any, ...]] = set()
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError as exc:
            self.error(str(path.relative_to(self.root)), f"无法读取: {exc}")
            return
        with handle:
            for line_number, raw in enumerate(handle, 1):
                text = raw.strip()
                if not text or text.startswith("#"):
                    continue
                path_prefix = f"observations.results.jsonl:{line_number}"
                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    self.error(path_prefix, f"JSON 无法解析: {exc.msg}")
                    continue
                if not isinstance(row, Mapping):
                    self.error(path_prefix, "必须是 JSON object")
                    continue
                self.observation_count += 1
                identifier = row.get("id")
                if not _is_nonempty_string(identifier):
                    self.error(f"{path_prefix}.id", "必须是非空字符串")
                elif identifier in seen_ids:
                    self.error(f"{path_prefix}.id", f"重复 id: {identifier}")
                else:
                    seen_ids.add(identifier)
                model_id = row.get("model_id", row.get("modelId"))
                benchmark_id = row.get("benchmark_id", row.get("benchmarkId"))
                metric_id = row.get("metric_id", row.get("metricId"))
                if model_id not in self.model_ids:
                    self.error(f"{path_prefix}.model_id", f"未知 model id: {model_id}")
                if benchmark_id not in self.benchmark_ids:
                    self.error(f"{path_prefix}.benchmark_id", f"未知 benchmark id: {benchmark_id}")
                    benchmark = {}
                else:
                    benchmark = self.benchmark_map[benchmark_id]
                metric = self.metric_map.get((str(benchmark_id), str(metric_id)))
                if metric is None and benchmark:
                    self.error(f"{path_prefix}.metric_id", f"benchmark 中不存在 metric: {metric_id}")
                value = row.get("value")
                if value is None:
                    if not _is_nonempty_string(row.get("missing_reason")) and row.get("status") != "missing":
                        self.error(f"{path_prefix}.value", "null 必须提供 missing_reason 或 status=missing")
                elif not _is_finite_number(value):
                    self.error(f"{path_prefix}.value", "必须是有限数字或带理由的 null")
                else:
                    self.numeric_observation_count += 1
                    if metric is not None:
                        bounds = _scale_bounds(metric.get("scale"))
                        if bounds and not bounds[0] <= float(value) <= bounds[1]:
                            self.error(f"{path_prefix}.value", f"超出范围 [{bounds[0]}, {bounds[1]}]")
                version_id = row.get("benchmark_version_id", row.get("benchmarkVersionId"))
                versions = benchmark.get("versions", []) if isinstance(benchmark, Mapping) else []
                known_versions = {item.get("id") for item in versions if isinstance(item, Mapping)}
                if version_id not in known_versions:
                    self.error(f"{path_prefix}.benchmark_version_id", f"未知 benchmark version: {version_id}")
                source_ids = self._check_source_refs(row.get("source_ids", row.get("sourceIds", [])), f"{path_prefix}.source_ids", required=value is not None)
                harness_id = row.get("harness_id", row.get("harnessId"))
                if harness_id is not None and harness_id not in self.harness_ids:
                    self.error(f"{path_prefix}.harness_id", f"未知 harness id: {harness_id}")
                subject = row.get("subject")
                subject_type = subject.get("type") if isinstance(subject, Mapping) else row.get("subject_type")
                if subject_type not in {"model", "system"}:
                    self.error(f"{path_prefix}.subject.type", "必须为 model 或 system")
                if subject_type == "system" and harness_id is None:
                    self.warning(f"{path_prefix}.harness_id", "system observation 未注明 harness；只能 conditional")
                status = row.get("status")
                if status is not None:
                    self._check_status_value(status, f"{path_prefix}.status")
                evidence_level = row.get("evidence_level", row.get("evidenceLevel"))
                self._check_evidence(evidence_level, f"{path_prefix}.evidence_level")
                comparability = row.get("comparability")
                if comparability not in KNOWN_COMPARABILITY:
                    self.error(f"{path_prefix}.comparability", "必须为 exact、conditional 或 none")
                for field in ("observed_at", "published_at"):
                    if row.get(field) is not None and not _is_iso_date(row[field]):
                        self.error(f"{path_prefix}.{field}", "必须是 ISO 日期或 datetime")
                protocol = row.get("protocol")
                if protocol is not None and not isinstance(protocol, Mapping):
                    self.error(f"{path_prefix}.protocol", "必须是 object")
                key = (model_id, benchmark_id, version_id, metric_id, json.dumps(protocol or {}, sort_keys=True, ensure_ascii=False))
                if key in seen_keys:
                    self.warning(f"{path_prefix}", "重复 observation key；如为不同来源请保留 source/evidence 差异")
                seen_keys.add(key)
                if value is not None and not source_ids:
                    # _check_source_refs already emits the main error; retain
                    # a focused message for machine-readable output.
                    self.error(f"{path_prefix}.source_ids", "numeric observation 必须有 source")

    def _check_status_value(self, value: Any, path: str) -> None:
        if not _is_nonempty_string(value):
            self.error(path, "必须是非空字符串")
        elif value not in KNOWN_STATUS:
            self.warning(path, f"未登记的 status: {value}")

    def _check_evidence(self, value: Any, path: str) -> None:
        if value not in {"A", "B", "C", "D"}:
            self.error(path, "必须为 A、B、C 或 D")

    def _check_url_value(self, value: Any, path: str) -> None:
        if not _is_nonempty_string(value):
            self.error(path, "必须是非空 URL 字符串")
            return
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.error(path, "必须是 http(s) URL")


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_finite_number(value: Any) -> bool:
    # bool is a subclass of int, but a boolean is never a meaningful score.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    try:
        if "T" in text or " " in text:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _scale_bounds(scale: Any) -> tuple[float, float] | None:
    if _is_finite_number(scale):
        number = float(scale)
        if number <= 0:
            return None
        # The demo's numeric scale means [0, scale].
        return (0.0, number)
    if isinstance(scale, Mapping):
        lower = scale.get("min")
        upper = scale.get("max")
        if _is_finite_number(lower) and _is_finite_number(upper):
            return (float(lower), float(upper))
    return None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _load_document(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _render_text(
    path: Path,
    summary: Mapping[str, int],
    validator: DataValidator,
    strict: bool,
) -> str:
    lines = [
        f"Data file: {path}",
        "Summary: "
        + ", ".join(
            f"{key}={summary[key]}"
            for key in ("models", "benchmarks", "sources", "scores")
        ),
        f"Errors: {len(validator.errors)}; warnings: {len(validator.warnings)}",
    ]
    for issue in validator.issues:
        lines.append(f"{issue.level.upper()}: {issue.path}: {issue.message}")
    if not validator.errors and (not strict or not validator.warnings):
        lines.append("Result: PASS" + (" (strict)" if strict else ""))
    else:
        lines.append("Result: FAIL")
    return "\n".join(lines)


def _render_json(
    path: Path,
    summary: Mapping[str, int],
    validator: DataValidator,
    strict: bool,
) -> str:
    payload = {
        "path": str(path),
        "summary": dict(summary),
        "errors": len(validator.errors),
        "warnings": len(validator.warnings),
        "strict": strict,
        "passed": not validator.errors and (not strict or not validator.warnings),
        "issues": [issue.as_dict() for issue in validator.issues],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_bundle_text(
    root: Path,
    summary: Mapping[str, int],
    validator: CanonicalBundleValidator,
    strict: bool,
) -> str:
    lines = [
        f"Canonical data root: {root}",
        "Summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()),
        f"Errors: {len(validator.errors)}; warnings: {len(validator.warnings)}",
    ]
    for issue in validator.issues:
        lines.append(f"{issue.level.upper()}: {issue.path}: {issue.message}")
    passed = not validator.errors and (not strict or not validator.warnings)
    lines.append("Result: PASS" + (" (strict)" if strict else "") if passed else "Result: FAIL")
    return "\n".join(lines)


def _render_bundle_json(
    root: Path,
    summary: Mapping[str, int],
    validator: CanonicalBundleValidator,
    strict: bool,
) -> str:
    passed = not validator.errors and (not strict or not validator.warnings)
    payload = {
        "root": str(root),
        "summary": dict(summary),
        "errors": len(validator.errors),
        "warnings": len(validator.warnings),
        "strict": strict,
        "passed": passed,
        "issues": [issue.as_dict() for issue in validator.issues],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=None,
        help="待校验 JSON（默认检查 canonical bundle；显式传文件则检查 legacy shape）",
    )
    parser.add_argument(
        "--canonical",
        action="store_true",
        help="检查 data/catalog 与 data/observations 的 canonical bundle",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="将 warning 也视为失败，适合发布前检查",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="以机器可读 JSON 输出结果",
    )
    args = parser.parse_args(argv)

    # No path now means the full update bundle.  Passing the old JSON path is
    # still supported for scripts and contributors who only want a seed check.
    if args.canonical or args.path is None or (args.path.expanduser().is_dir() if args.path else False):
        root = (args.path.expanduser() if args.path is not None else DEFAULT_CANONICAL_ROOT)
        if root.is_file():
            root = root.parent
        root = root.resolve()
        validator = CanonicalBundleValidator(root)
        summary = validator.check()
        # The compatibility seed is part of the publication input as well;
        # include its errors with a prefix, but do not require it when a caller
        # explicitly validates a standalone canonical fixture directory.
        legacy_path = root / "data" / "models.json"
        if legacy_path.is_file():
            try:
                legacy_document = _load_document(legacy_path)
                legacy_validator = DataValidator()
                legacy_summary = legacy_validator.check(legacy_document)
                summary = dict(summary)
                summary["legacy_models"] = legacy_summary["models"]
                summary["legacy_scores"] = legacy_summary["scores"]
                for issue in legacy_validator.issues:
                    validator.issues.append(
                        Issue(issue.level, f"legacy.{issue.path}", issue.message)
                    )
            except (OSError, json.JSONDecodeError) as exc:
                validator.error("legacy.data/models.json", f"无法读取兼容 seed: {exc}")
        if args.as_json:
            print(_render_bundle_json(root, summary, validator, args.strict))
        else:
            print(_render_bundle_text(root, summary, validator, args.strict))
        return 0 if not validator.errors and (not args.strict or not validator.warnings) else 1

    path = (args.path or DEFAULT_DATA_PATH).expanduser()
    if not path.is_file():
        message = f"Data file not found: {path}"
        if args.as_json:
            print(json.dumps({"passed": False, "error": message}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 2

    try:
        document = _load_document(path)
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        if args.as_json:
            print(json.dumps({"passed": False, "error": message}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 1
    except OSError as exc:
        message = f"Unable to read {path}: {exc}"
        if args.as_json:
            print(json.dumps({"passed": False, "error": message}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 2

    validator = DataValidator()
    summary = validator.check(document)
    if args.as_json:
        print(_render_json(path, summary, validator, args.strict))
    else:
        print(_render_text(path, summary, validator, args.strict))

    return 0 if not validator.errors and (not args.strict or not validator.warnings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
