/*
 * Models directory
 *
 * This page intentionally reads the derived snapshot directly. It is a
 * static, catalog-first view: model metadata belongs here; score context is
 * shown only as a clearly labelled canonical/public signal, with the Matrix
 * remaining the place for cross-model comparison.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    freshnessPill: $("freshnessPill"),
    themeToggle: $("themeToggle"),
    asOfLabel: $("asOfLabel"),
    catalogVersion: $("catalogVersion"),
    heroModelCount: $("heroModelCount"),
    heroActiveCount: $("heroActiveCount"),
    heroProviderCount: $("heroProviderCount"),
    heroOpenCount: $("heroOpenCount"),
    heroPublicCount: $("heroPublicCount"),
    heroActiveBar: $("heroActiveBar"),
    modelCount: $("modelCount"),
    providerCount: $("providerCount"),
    activeCount: $("activeCount"),
    openCount: $("openCount"),
    searchInput: $("searchInput"),
    providerFilter: $("providerFilter"),
    statusFilter: $("statusFilter"),
    familyFilter: $("familyFilter"),
    modalityFilter: $("modalityFilter"),
    sortSelect: $("sortSelect"),
    weightsFilter: $("weightsFilter"),
    currentOnly: $("currentOnly"),
    withScoresOnly: $("withScoresOnly"),
    resetFilters: $("resetFilters"),
    activeFilters: $("activeFilters"),
    directoryNote: $("directoryNote"),
    modelGrid: $("modelGrid"),
    modelTableWrap: $("modelTableWrap"),
    modelTableBody: $("modelTableBody"),
    emptyState: $("emptyState"),
    emptyReset: $("emptyReset"),
    viewTabs: [...document.querySelectorAll(".directory-view-tab")],
    drawer: $("detailDrawer"),
    drawerBackdrop: $("drawerBackdrop"),
    drawerContent: $("drawerContent"),
    closeDrawer: $("closeDrawer"),
    toast: $("toast"),
  };

  const state = {
    data: null,
    models: [],
    sources: new Map(),
    benchmarks: new Map(),
    runs: [],
    publicEvidence: [],
    publicByModel: new Map(),
    view: "cards",
    query: "",
    provider: "all",
    status: "all",
    family: "all",
    modality: "all",
    weights: "all",
    sort: "recent",
    currentOnly: false,
    withScoresOnly: false,
    toastTimer: null,
  };

  const esc = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

  const first = (...values) => values.find((value) => value !== undefined && value !== null && value !== "");
  const list = (value) => Array.isArray(value) ? value : (value == null || value === "" ? [] : [value]);
  const text = (value, fallback = "—") => {
    const result = first(value, fallback);
    return result == null ? fallback : String(result);
  };
  const number = (value) => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value !== "string") return null;
    const parsed = Number(value.replace(/,/g, "").trim());
    return Number.isFinite(parsed) ? parsed : null;
  };
  const norm = (value) => String(value ?? "").trim().toLowerCase();
  const isCurrent = (model) => ["active", "preview", "restricted"].includes(norm(model.status));
  const hasScores = (model) => scoreEntries(model).length > 0 || publicEntries(model).length > 0 || Number(model.systemRunCount || 0) > 0 || relatedRuns(model).length > 0;

  function normaliseModel(raw) {
    const source = raw && typeof raw === "object" ? raw : {};
    const variant = source.variant && typeof source.variant === "object" ? source.variant : {};
    const id = text(first(source.id, source.canonicalId, source.canonical_id, source.modelId, source.name), "unknown-model");
    const status = text(first(source.status, source.state, source.lifecycle), source.catalogOnly ? "catalog-only" : "active");
    return {
      ...source,
      id,
      canonicalId: text(first(source.canonicalId, source.canonical_id, id), id),
      familyId: text(first(source.familyId, source.family_id, source.family), "未分组"),
      name: text(first(source.name, source.displayName, source.display_name, id), id),
      provider: text(first(source.provider, source.organization, source.vendor), "Unknown"),
      mark: text(first(source.mark, source.logoMark, source.name?.slice?.(0, 1), id.slice(0, 1)), "?").slice(0, 2),
      releaseDate: first(source.releaseDate, source.release_date, source.release, source.date),
      release: first(source.release, source.releaseDate, source.release_date, source.date),
      status,
      access: first(source.access, source.availability, source.endpoint) || "未注明",
      availability: first(source.availability, source.access),
      aliases: list(first(source.aliases, source.alias)),
      tags: list(first(source.tags, source.capabilities)),
      summary: text(first(source.summary, source.description, source.note), "暂无模型说明。"),
      modalities: list(first(source.modalities, source.modality)).map(String),
      contextWindow: first(source.contextWindow, source.context_window, source.context),
      paramsTotal: first(source.paramsTotal, source.params_total, source.totalParams, source.parameters),
      paramsActive: first(source.paramsActive, source.params_active, source.activeParams),
      openWeights: source.openWeights === true || source.open_weights === true,
      variant,
      sourceIds: list(first(source.sourceIds, source.source_ids)),
      scores: source.scores && typeof source.scores === "object" ? source.scores : {},
      scoreCount: Number(source.scoreCount || source.score_count || 0),
      systemRunCount: Number(source.systemRunCount || source.system_run_count || 0),
      catalogOnly: Boolean(source.catalogOnly || source.catalog_only || norm(status) === "catalog-only"),
    };
  }

  function normaliseRun(raw) {
    const item = raw && typeof raw === "object" ? raw : {};
    return {
      ...item,
      id: text(first(item.id, item.observationId), "run"),
      modelId: first(item.modelId, item.model_id),
      modelName: text(first(item.modelName, item.model_name, item.model), "unknown model"),
      benchmarkId: first(item.benchmarkId, item.benchmark_id),
      benchmarkName: text(first(item.benchmarkName, item.benchmark_name), first(item.benchmarkId, item.benchmark_id, "benchmark")),
      value: number(first(item.value, item.score)),
      rawValue: first(item.rawValue, item.raw_value),
      unit: first(item.unit, item.metricUnit),
      metric: first(item.metric, item.metricId),
      status: first(item.status, item.verified, "reported"),
      harness: first(item.harnessName, item.harness, item.harnessId),
      sourceId: first(item.sourceId, item.source_id),
      sourceUrl: first(item.sourceUrl, item.source_url, item.url),
      observedAt: first(item.observedAt, item.observed_at, item.date),
      notes: first(item.notes, item.note),
    };
  }

  function normalisePublicEvidence(raw) {
    const item = raw && typeof raw === "object" ? raw : {};
    const protocol = item.protocol && typeof item.protocol === "object" ? item.protocol : {};
    return {
      ...item,
      id: text(first(item.id, item.candidateId), "public-evidence"),
      canonicalModelId: first(item.canonicalModelId, item.canonical_model_id, item.mappedModelId, item.modelId, item.model_id),
      modelName: text(first(item.modelName, item.model_name, item.modelRef, item.model_ref), "unknown model"),
      benchmarkId: first(item.benchmarkId, item.benchmark_id),
      benchmarkName: text(first(item.benchmarkName, item.benchmark_name), first(item.benchmarkId, item.benchmark_id, "benchmark")),
      benchmarkVersion: first(item.benchmarkVersion, item.benchmark_version, item.benchmarkVersionId, item.benchmark_version_id),
      metricId: first(item.metricId, item.metric_id, item.metric),
      value: number(first(item.value, item.score)),
      rawValue: first(item.rawValue, item.raw_value),
      unit: first(item.unit, item.metricUnit, item.metric_unit),
      status: first(item.status, "reported"),
      verified: item.verified === true,
      verificationStatus: first(item.verificationStatus, item.verification_status, "not_reproduced"),
      evidenceLevel: first(item.evidenceLevel, item.evidence_level),
      comparability: item.comparability,
      sourceId: first(item.sourceId, item.source_id),
      sourceUrl: first(item.sourceUrl, item.source_url, item.evidenceUrl, item.evidence_url),
      sourcePageUrl: first(item.sourcePageUrl, item.source_page_url),
      sourceApiUrl: first(item.sourceApiUrl, item.source_api_url),
      sourceLabel: first(item.sourceLabel, item.source_label),
      sourceLocator: first(item.sourceLocator, item.source_locator, item.locator),
      retrievedAt: first(item.retrievedAt, item.retrieved_at),
      observedAt: first(item.observedAt, item.observed_at),
      publishedAt: first(item.publishedAt, item.published_at),
      payloadSha256: first(item.payloadSha256, item.payload_sha256, item.snapshotHash, item.snapshot_hash),
      harness: first(item.harness, item.harnessId, item.harness_id, protocol.harness),
      protocol,
      qualityFlags: list(first(item.qualityFlags, item.quality_flags)),
      reviewStatus: first(item.reviewStatus, item.review_status, "unreviewed"),
      selectionRank: number(item.selectionRank || item.selection_rank),
      subjectType: first(item.subjectType, item.subject_type),
    };
  }

  function sourceFor(idOrUrl) {
    if (!idOrUrl) return null;
    const key = String(idOrUrl);
    return state.sources.get(key) || [...state.sources.values()].find((source) => source.url === key || source.web_url === key || source.page_url === key) || null;
  }

  function benchmarkFor(id) {
    if (!id) return null;
    return state.benchmarks.get(String(id)) || null;
  }

  function benchmarkLabel(id, fallback) {
    const benchmark = benchmarkFor(id);
    if (benchmark?.name || benchmark?.short) return benchmark.name || benchmark.short;
    const raw = String(first(fallback, id, "benchmark"));
    return raw.replace(/^epoch-/, "").replace(/_external$/, "").replace(/[-_]+/g, " ");
  }

  function relatedRuns(model) {
    const keys = new Set([model.id, model.canonicalId, model.name, ...(model.aliases || [])].map(norm).filter(Boolean));
    return state.runs.filter((run) => keys.has(norm(run.modelId)) || keys.has(norm(run.modelName)));
  }

  function scoreEntries(model) {
    const entries = Object.entries(model?.scores || {}).map(([benchmarkId, raw]) => {
      const score = raw && typeof raw === "object" ? raw : { value: raw };
      const value = number(first(score.value, score.score));
      const rawValue = first(score.raw_value, score.rawValue, score.displayValue, score.display_value);
      return { benchmarkId, score, value, rawValue };
    }).filter((item) => item.value !== null || item.rawValue);
    return entries.sort((a, b) => {
      const ad = String(first(a.score.observed_at, a.score.observedAt, ""));
      const bd = String(first(b.score.observed_at, b.score.observedAt, ""));
      return bd.localeCompare(ad) || String(a.benchmarkId).localeCompare(String(b.benchmarkId));
    });
  }

  function publicEntries(model) {
    if (!model) return [];
    const direct = state.publicByModel.get(norm(model.id)) || state.publicByModel.get(norm(model.canonicalId));
    if (direct) return direct;
    const keys = new Set([model.id, model.canonicalId].map(norm).filter(Boolean));
    return state.publicEvidence.filter((item) => keys.has(norm(item.canonicalModelId)));
  }

  function publicPreviewEntries(model) {
    const preferredUnits = new Set(["percent", "%", "fraction", "elo", "score", "index"]);
    const seenBenchmarks = new Set();
    return publicEntries(model)
      .filter((item) => item.value !== null || item.rawValue !== undefined)
      .sort((a, b) => {
        const au = preferredUnits.has(norm(a.unit)) ? 0 : 1;
        const bu = preferredUnits.has(norm(b.unit)) ? 0 : 1;
        return au - bu || (a.selectionRank ?? 9999) - (b.selectionRank ?? 9999) || String(b.retrievedAt || "").localeCompare(String(a.retrievedAt || ""));
      })
      .filter((item) => {
        const key = `${item.benchmarkId || ""}|${item.metricId || ""}`;
        if (seenBenchmarks.has(key)) return false;
        seenBenchmarks.add(key);
        return true;
      })
      .slice(0, 3);
  }

  function statusLabel(status) {
    return ({
      active: "当前",
      previous: "上一代",
      preview: "预览",
      restricted: "受限",
      "catalog-only": "目录",
      retired: "退役",
      deprecated: "弃用",
    })[norm(status)] || text(status, "未注明");
  }

  function statusClass(status) {
    const value = norm(status).replace(/[^a-z-]/g, "");
    return ["active", "previous", "preview", "restricted", "catalog-only", "retired", "deprecated"].includes(value) ? value : "unknown";
  }

  function evidenceLabel(entry) {
    const value = norm(first(entry?.status, entry?.verified, entry?.verificationStatus));
    if (value === "approved" || value === "verified" || value === "canonical") return "approved";
    if (value === "candidate") return "candidate";
    if (value === "missing") return "missing";
    return "reported";
  }

  function evidenceText(entry) {
    return evidenceLabel(entry) === "approved" ? "approved" : evidenceLabel(entry) === "candidate" ? "候选" : evidenceLabel(entry) === "missing" ? "缺失" : "披露 · 未复现";
  }

  function formatDate(value) {
    if (!value) return "未注明";
    const raw = String(value);
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10);
    return raw;
  }

  function formatContext(value) {
    if (value && typeof value === "object") {
      const values = Object.values(value).map(number).filter((item) => item !== null);
      if (values.length) return formatContext(Math.max(...values));
      return "未注明";
    }
    const n = number(value);
    if (n === null || n <= 0) return "未注明";
    const compact = (base, suffix) => {
      const q = n / base;
      const digits = q >= 100 ? 0 : q >= 10 ? 1 : 2;
      return `${q.toFixed(digits).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "")}${suffix}`;
    };
    if (n >= 1e9) return compact(1e9, "B");
    if (n >= 1e6) return compact(1e6, "M");
    if (n >= 1e3) return compact(1e3, "k");
    return String(n);
  }

  function formatParams(total, active) {
    const fmt = (value) => {
      const n = number(value);
      if (n === null || n <= 0) return null;
      const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
      const unit = units.find(([base]) => n >= base);
      if (!unit) return String(n);
      const [base, suffix] = unit;
      const q = n / base;
      return `${q.toFixed(q >= 100 ? 0 : q >= 10 ? 1 : 2).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "")} ${suffix}`;
    };
    const all = fmt(total);
    const live = fmt(active);
    if (all && live && all !== live) return `${all} total · ${live} active`;
    return all || (live ? `${live} active` : "未注明");
  }

  function formatScore(item, benchmark) {
    const raw = first(item.rawValue, item.score?.raw_value, item.score?.rawValue);
    if (raw !== undefined && raw !== null && raw !== "") return String(raw);
    if (item.value === null) return "—";
    const unit = first(item.score?.unit, benchmark?.unit, item.score?.metricUnit, "");
    if (unit === "%" || unit === "percent") return `${item.value}%`;
    return `${item.value}${unit ? ` ${unit}` : ""}`;
  }

  function formatPublicEvidence(item) {
    const unit = norm(item?.unit);
    const value = item?.value;
    const raw = item?.rawValue;
    const compactNumber = (numeric, digits = 2) => Number(numeric).toFixed(digits).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    // Public adapters normalize percentages/fractions into `value`; rawValue
    // may intentionally remain a 0–1 source fraction (for example ALE).
    if (unit === "percent" || unit === "%" || unit === "percentage") {
      return value === null || value === undefined ? text(raw, "—") : `${compactNumber(value, Math.abs(Number(value)) >= 10 ? 1 : 2)}%`;
    }
    if (unit === "seconds" || unit === "second" || unit === "s") {
      return value === null || value === undefined ? text(raw, "—") : `${compactNumber(value, Number(value) >= 100 ? 0 : 1)}s`;
    }
    if (unit === "fraction") {
      return value === null || value === undefined ? text(raw, "—") : compactNumber(value, Number(value) >= 1 ? 1 : 3);
    }
    if (value !== null && value !== undefined) {
      const numeric = Number(value);
      if (Number.isFinite(numeric)) return compactNumber(numeric, Math.abs(numeric) >= 100 ? 0 : Math.abs(numeric) >= 10 ? 1 : 2);
    }
    return text(raw, "—");
  }

  function scoreUnit(item, benchmark) {
    return text(first(item.score?.metric, item.score?.metricId, benchmark?.metricLabel, benchmark?.metric), "score");
  }

  function familyName(model) {
    const family = text(model.familyId, "未分组");
    const parts = family.split(/[\\/]/);
    return parts[parts.length - 1] || family;
  }

  function modalityLabel(value) {
    return ({ text: "文本", image: "图像", video: "视频", audio: "音频", code: "代码" })[norm(value)] || text(value);
  }

  function variantLabels(model) {
    const v = model.variant || {};
    const labels = [];
    if (v.reasoning === true) labels.push("reasoning");
    if (v.omni === true) labels.push("omni");
    if (v.speed_variant === true || v.speedVariant === true) labels.push("fast");
    if (v.context_variant === true || v.contextVariant === true) labels.push("context variant");
    if (v.tier) labels.push(String(v.tier));
    if (v.specialization) labels.push(String(v.specialization));
    if (v.adaptive_thinking === true || v.adaptiveThinking === true) labels.push("adaptive thinking");
    if (v.preview === true) labels.push("preview");
    return [...new Set(labels)];
  }

  function searchable(model) {
    const publicTerms = publicEntries(model).flatMap((item) => [item.benchmarkId, item.benchmarkName, item.metricId, item.harness]);
    return [model.id, model.name, model.provider, model.familyId, model.summary, model.release, model.access, ...model.aliases, ...model.tags, ...model.modalities, ...variantLabels(model), ...publicTerms]
      .filter(Boolean).join(" ").toLowerCase();
  }

  function filteredModels() {
    const query = norm(state.query);
    const models = state.models.filter((model) => {
      if (query && !searchable(model).includes(query)) return false;
      if (state.provider !== "all" && model.provider !== state.provider) return false;
      if (state.status !== "all" && norm(model.status) !== norm(state.status)) return false;
      if (state.family !== "all" && model.familyId !== state.family) return false;
      if (state.modality !== "all" && !model.modalities.map(norm).includes(norm(state.modality))) return false;
      if (state.weights === "open" && model.openWeights !== true) return false;
      if (state.weights === "closed" && model.openWeights === true) return false;
      if (state.currentOnly && !isCurrent(model)) return false;
      if (state.withScoresOnly && !hasScores(model)) return false;
      return true;
    });
    const dateValue = (model) => {
      const raw = first(model.releaseDate, model.release);
      return raw == null ? "" : String(raw);
    };
    const paramsValue = (model) => number(model.paramsTotal) || 0;
    const contextValue = (model) => {
      if (model.contextWindow && typeof model.contextWindow === "object") return Math.max(...Object.values(model.contextWindow).map(number).filter((n) => n !== null), 0);
      return number(model.contextWindow) || 0;
    };
    return models.sort((a, b) => {
      if (state.sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "provider") return a.provider.localeCompare(b.provider, "zh-CN") || a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "context") return contextValue(b) - contextValue(a) || a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "params") return paramsValue(b) - paramsValue(a) || a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "scores") {
        const bCount = scoreEntries(b).length + publicEntries(b).length;
        const aCount = scoreEntries(a).length + publicEntries(a).length;
        return bCount - aCount || a.name.localeCompare(b.name, "zh-CN");
      }
      const ad = dateValue(a);
      const bd = dateValue(b);
      // Unknown release dates stay at the end instead of winning a lexical
      // comparison against an empty string.
      if (ad && bd && ad !== bd) return bd.localeCompare(ad);
      if (ad !== bd) return ad ? -1 : 1;
      return (isCurrent(b) ? -1 : 1) - (isCurrent(a) ? -1 : 1) || a.name.localeCompare(b.name, "zh-CN");
    });
  }

  function statusBadge(model) {
    return `<span class="model-directory-status status-${esc(statusClass(model.status))}">${esc(statusLabel(model.status))}</span>`;
  }

  function modelIdentity(model) {
    return `<div class="model-card-identity"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><span class="model-card-title"><strong>${esc(model.name)}</strong><small>${esc(model.provider)} · ${esc(familyName(model))}</small></span></div>`;
  }

  function cardMarkup(model) {
    const scores = scoreEntries(model);
    const publicRows = publicEntries(model);
    const publicPreview = publicPreviewEntries(model);
    const canonicalPreview = scores.slice(0, 3).map((item) => {
      const benchmark = benchmarkFor(item.benchmarkId);
      return `<span class="model-score-chip"><small>${esc(benchmark?.short || benchmarkLabel(item.benchmarkId, item.score?.benchmarkName))}</small><strong>${esc(formatScore(item, benchmark))}</strong><i>canonical</i></span>`;
    }).join("");
    const publicScorePreview = publicPreview.map((item) => {
      const benchmark = benchmarkFor(item.benchmarkId);
      return `<span class="model-score-chip model-score-chip-public"><small>${esc(benchmark?.short || benchmarkLabel(item.benchmarkId, item.benchmarkName))}</small><strong>${esc(formatPublicEvidence(item))}</strong><i>披露</i></span>`;
    }).join("");
    const tags = [...model.tags, ...variantLabels(model)].slice(0, 4).map((tag) => `<span class="model-badge">${esc(tag)}</span>`).join("");
    const modalities = model.modalities.length ? model.modalities.map(modalityLabel).join(" · ") : "未注明";
    return `<article class="model-directory-card" data-model-id="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 详情">
      <div class="model-card-head">${modelIdentity(model)}${statusBadge(model)}</div>
      <p class="model-card-summary">${esc(model.summary)}</p>
      <div class="model-card-specs">
        <span><small>RELEASE</small><strong>${esc(formatDate(model.releaseDate || model.release))}</strong></span>
        <span><small>CONTEXT</small><strong>${esc(formatContext(model.contextWindow))}</strong></span>
        <span><small>PARAMS</small><strong>${esc(formatParams(model.paramsTotal, model.paramsActive))}</strong></span>
        <span><small>MODALITIES</small><strong>${esc(modalities)}</strong></span>
      </div>
      <div class="model-card-tags">${tags || '<span class="model-badge muted-badge">暂无标签</span>'}</div>
      <div class="model-card-evidence">
        <div class="model-score-preview">${canonicalPreview}${publicScorePreview || (!canonicalPreview ? '<span class="model-score-empty">暂无已收录成绩；打开详情查看目录来源。</span>' : "")}</div>
        <div class="model-card-foot"><span>${scores.length || publicRows.length ? `${scores.length ? `${scores.length} canonical` : ""}${scores.length && publicRows.length ? " · " : ""}${publicRows.length ? `${publicRows.length} 条披露` : ""}` : "catalog-only"}${model.openWeights ? " · open weights" : ""}</span><span class="model-open-link">查看详情 ↗</span></div>
      </div>
    </article>`;
  }

  function tableMarkup(model) {
    const scores = scoreEntries(model);
    const publicRows = publicEntries(model);
    const modalities = model.modalities.length ? model.modalities.map(modalityLabel).join(" · ") : "—";
    return `<tr data-model-id="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 详情">
      <td><div class="table-model-identity"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><span><strong>${esc(model.name)}</strong><small>${esc(model.provider)} · ${esc(familyName(model))}</small></span></div></td>
      <td>${statusBadge(model)}</td>
      <td>${esc(modalities)}</td>
      <td class="mono-cell">${esc(formatContext(model.contextWindow))}</td>
      <td class="mono-cell">${esc(formatParams(model.paramsTotal, model.paramsActive))}</td>
      <td>${model.openWeights ? '<span class="table-yes">open</span>' : '<span class="table-muted">closed / ?</span>'}</td>
      <td class="mono-cell" title="c = canonical / curated · r = public reported">${scores.length || publicRows.length ? `${scores.length ? `${scores.length}c` : ""}${scores.length && publicRows.length ? " · " : ""}${publicRows.length ? `${publicRows.length}r` : ""}` : "—"}</td>
    </tr>`;
  }

  function updateStats() {
    const models = state.models;
    const providers = new Set(models.map((model) => model.provider).filter(Boolean));
    const current = models.filter(isCurrent);
    const open = models.filter((model) => model.openWeights === true);
    const publicTotal = state.publicEvidence.length;
    const setText = (element, value) => { if (element) element.textContent = String(value); };
    setText(els.modelCount, models.length);
    setText(els.providerCount, providers.size);
    setText(els.activeCount, current.length);
    setText(els.openCount, open.length);
    setText(els.heroModelCount, models.length);
    setText(els.heroActiveCount, current.length);
    setText(els.heroProviderCount, providers.size);
    setText(els.heroOpenCount, open.length);
    setText(els.heroPublicCount, publicTotal);
    if (els.heroActiveBar) els.heroActiveBar.style.width = `${models.length ? (current.length / models.length) * 100 : 0}%`;
  }

  function populateSelect(select, values, labeler = (value) => value) {
    if (!select) return;
    const old = select.value;
    select.innerHTML = '<option value="all">全部</option>' + values.map((value) => `<option value="${esc(value)}">${esc(labeler(value))}</option>`).join("");
    if ([...select.options].some((option) => option.value === old)) select.value = old;
  }

  function populateFilters() {
    const providers = [...new Set(state.models.map((model) => model.provider).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    const statuses = [...new Set(state.models.map((model) => model.status).filter(Boolean))].sort((a, b) => {
      const order = { active: 0, preview: 1, restricted: 2, previous: 3, "catalog-only": 4 };
      return (order[norm(a)] ?? 9) - (order[norm(b)] ?? 9) || String(a).localeCompare(String(b));
    });
    const families = [...new Set(state.models.map((model) => model.familyId).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    const modalities = [...new Set(state.models.flatMap((model) => model.modalities))].sort((a, b) => a.localeCompare(b));
    populateSelect(els.providerFilter, providers, (value) => value);
    populateSelect(els.statusFilter, statuses, statusLabel);
    populateSelect(els.familyFilter, families, (value) => String(value).split(/[\\/]/).pop());
    populateSelect(els.modalityFilter, modalities, modalityLabel);
    // The first option is deliberately contextual on this page.
    if (els.providerFilter?.options?.[0]) els.providerFilter.options[0].textContent = "所有 provider";
    if (els.statusFilter?.options?.[0]) els.statusFilter.options[0].textContent = "所有状态";
    if (els.familyFilter?.options?.[0]) els.familyFilter.options[0].textContent = "所有模型族";
    if (els.modalityFilter?.options?.[0]) els.modalityFilter.options[0].textContent = "所有模态";
  }

  function renderActiveFilters() {
    if (!els.activeFilters) return;
    const filters = [];
    if (state.query) filters.push(["搜索", state.query]);
    if (state.provider !== "all") filters.push(["provider", state.provider]);
    if (state.status !== "all") filters.push(["状态", statusLabel(state.status)]);
    if (state.family !== "all") filters.push(["模型族", familyName({ familyId: state.family })]);
    if (state.modality !== "all") filters.push(["模态", modalityLabel(state.modality)]);
    if (state.weights !== "all") filters.push(["权重", state.weights === "open" ? "开放" : "闭源 / 未注明"]);
    if (state.currentOnly) filters.push(["范围", "仅当前"]);
    if (state.withScoresOnly) filters.push(["成绩", "已有成绩"]);
    els.activeFilters.innerHTML = filters.map(([label, value]) => `<span class="filter-chip">${esc(label)}: ${esc(value)}</span>`).join("");
  }

  function render() {
    const models = filteredModels();
    updateStats();
    renderActiveFilters();
    if (els.directoryNote) {
      const canonicalTotal = models.reduce((sum, model) => sum + scoreEntries(model).length, 0);
      const publicTotal = models.reduce((sum, model) => sum + publicEntries(model).length, 0);
      els.directoryNote.textContent = `${models.length} / ${state.models.length} 个模型条目 · ${canonicalTotal} 条 canonical + ${publicTotal} 条公开披露 · 目录字段缺失会显示“未注明”，不会推断。`;
    }
    if (els.modelGrid) els.modelGrid.innerHTML = models.map(cardMarkup).join("");
    if (els.modelTableBody) els.modelTableBody.innerHTML = models.map(tableMarkup).join("");
    const empty = models.length === 0;
    if (els.emptyState) els.emptyState.hidden = !empty;
    if (els.modelGrid) els.modelGrid.hidden = empty || state.view !== "cards";
    if (els.modelTableWrap) els.modelTableWrap.hidden = empty || state.view !== "table";
  }

  function sourceLinkMarkup(source, fallbackUrl, label) {
    const url = first(source?.url, source?.web_url, source?.page_url, fallbackUrl);
    if (!url) return `<span class="source-link source-link-muted">${esc(label || source?.id || "未注明来源")}</span>`;
    return `<a class="source-link" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label || source?.label || url)} ↗</a>`;
  }

  function detailItem(label, value, extraClass = "") {
    return `<div class="detail-item model-detail-item"><label>${esc(label)}</label><span class="model-detail-value ${extraClass}">${value}</span></div>`;
  }

  function scoreMarkup(item) {
    const benchmark = benchmarkFor(item.benchmarkId);
    const score = item.score || {};
    const source = sourceFor(first(score.sourceId, score.source_id, score.sourceUrl, score.source_url));
    const sourceUrl = first(score.sourceUrl, score.source_url, source?.url);
    const observed = first(score.observed_at, score.observedAt, score.published_at, score.publishedAt);
    const protocol = first(score.setting, score.protocol?.raw_setting, score.protocol?.rawSetting, score.protocol);
    return `<article class="model-score-row">
      <div class="model-score-row-head"><div><strong>${esc(benchmarkLabel(item.benchmarkId, score.benchmarkName))}</strong><small>${esc(first(score.benchmark_version, score.benchmarkVersion, benchmark?.versionId, "version 未注明"))}</small></div><strong class="model-score-value">${esc(formatScore(item, benchmark))}</strong></div>
      <div class="model-score-row-meta"><span>${esc(scoreUnit(item, benchmark))}</span><span class="score-evidence evidence-${esc(evidenceLabel(score))}">${esc(evidenceText(score))}</span>${score.harness ? `<span>${esc(score.harness)}</span>` : ""}${observed ? `<span>${esc(formatDate(observed))}</span>` : ""}</div>
      ${protocol ? `<p>${esc(typeof protocol === "object" ? JSON.stringify(protocol) : protocol)}</p>` : ""}
      <div class="model-score-source">${sourceLinkMarkup(source, sourceUrl, first(score.sourceLabel, source?.label, "查看成绩来源"))}<a href="index.html#matrix" class="matrix-link">在 Matrix 中查看 ↗</a></div>
    </article>`;
  }

  function publicMarkup(item) {
    const benchmark = benchmarkFor(item.benchmarkId);
    const source = sourceFor(item.sourceId);
    const sourceUrl = first(item.sourceUrl, item.evidenceUrl, source?.url);
    const pageUrl = item.sourcePageUrl;
    const apiUrl = item.sourceApiUrl;
    const version = first(item.benchmarkVersion, item.benchmarkVersionId, benchmark?.versionId, "version 未注明");
    const protocolParts = item.protocol && typeof item.protocol === "object"
      ? [item.protocol.split, item.protocol.track, item.protocol.split_track, item.protocol.harness_variant, item.protocol.reasoning_mode].filter(Boolean)
      : [];
    const urls = [];
    [[sourceUrl, first(item.sourceLabel, source?.label, "来源")], [pageUrl, "source page"], [apiUrl, "source API"]].forEach(([url, label]) => {
      if (url && !urls.some(([known]) => known === url)) urls.push([url, label]);
    });
    return `<article class="model-public-row">
      <div class="model-score-row-head"><div><strong>${esc(benchmarkLabel(item.benchmarkId, item.benchmarkName))}</strong><small>${esc(version)} · ${esc(item.metricId || "metric 未注明")}</small></div><strong class="model-score-value public-value">${esc(formatPublicEvidence(item))}</strong></div>
      <div class="model-score-row-meta"><span class="score-evidence evidence-reported">披露 · 未复现</span><span>${esc(first(item.unit, "unit 未注明"))}</span>${item.harness ? `<span>${esc(item.harness)}</span>` : ""}${item.subjectType ? `<span>${esc(item.subjectType)}</span>` : ""}${item.observedAt || item.publishedAt ? `<span>${esc(formatDate(first(item.observedAt, item.publishedAt)))}</span>` : ""}</div>
      ${protocolParts.length ? `<p class="public-protocol">${esc(protocolParts.join(" · "))}</p>` : ""}
      <div class="model-public-source">${urls.map(([url, label]) => `<a class="source-link" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label)} ↗</a>`).join("") || '<span class="source-link source-link-muted">来源链接未注明</span>'}</div>
      ${item.sourceLocator ? `<p class="public-locator"><span>locator</span> <code>${esc(item.sourceLocator)}</code></p>` : ""}
      <p class="public-raw"><span>raw</span> <code>${esc(item.rawValue === undefined || item.rawValue === null ? "—" : item.rawValue)}</code>${item.payloadSha256 ? ` <span>· snapshot ${esc(String(item.payloadSha256).slice(0, 12))}…</span>` : ""}</p>
      ${item.qualityFlags?.length ? `<p class="public-flags">${item.qualityFlags.map((flag) => `<span>${esc(flag)}</span>`).join("")}</p>` : ""}
    </article>`;
  }

  function runMarkup(run) {
    const benchmark = benchmarkFor(run.benchmarkId);
    const source = sourceFor(first(run.sourceId, run.sourceUrl));
    const value = run.rawValue || (run.value === null ? "—" : `${run.value}${run.unit === "%" ? "%" : run.unit ? ` ${run.unit}` : ""}`);
    return `<article class="model-run-row"><div><strong>${esc(benchmark?.name || run.benchmarkName)}</strong><small>${esc(first(run.benchmarkVersion, benchmark?.versionId, "version 未注明"))}</small></div><strong class="model-run-value">${esc(value)}</strong><div class="model-run-meta"><span>${esc(first(run.harness, "harness 未注明"))}</span><span>${esc(evidenceText(run))}</span>${run.observedAt ? `<span>${esc(formatDate(run.observedAt))}</span>` : ""}</div>${source || run.sourceUrl ? `<div>${sourceLinkMarkup(source, run.sourceUrl, first(source?.label, "查看运行来源"))}</div>` : ""}</article>`;
  }

  function publicDetailEntries(model) {
    const rows = publicEntries(model).filter((item) => item.value !== null || item.rawValue !== undefined);
    const seen = new Set();
    const distinct = rows
      .slice()
      .sort((a, b) => (a.selectionRank ?? 9999) - (b.selectionRank ?? 9999) || String(b.retrievedAt || "").localeCompare(String(a.retrievedAt || "")))
      .filter((item) => {
        const split = item.protocol && typeof item.protocol === "object" ? first(item.protocol.split, item.protocol.track, item.protocol.split_track, "") : "";
        const key = [item.benchmarkId, item.metricId, item.harnessId || item.harness, split].join("|");
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    return { rows, distinct };
  }

  function renderDrawer(model) {
    if (!model || !els.drawerContent) return;
    const scoreItems = scoreEntries(model);
    const publicDetail = publicDetailEntries(model);
    const runs = relatedRuns(model);
    const variant = variantLabels(model);
    const sourceIds = [...new Set(model.sourceIds)];
    const sources = sourceIds.map((id) => sourceFor(id) || { id }).filter(Boolean);
    const aliases = model.aliases.length ? model.aliases.map((alias) => `<code>${esc(alias)}</code>`).join(" ") : "未注明";
    const tags = [...model.tags, ...variant].filter(Boolean).map((tag) => `<span class="model-badge">${esc(tag)}</span>`).join("");
    const modalities = model.modalities.length ? model.modalities.map(modalityLabel).join(" · ") : "未注明";
    const reasoning = model.variant?.reasoning === true ? "支持 / 标注" : model.variant?.reasoning === false ? "不标注" : "未注明";
    const sourceMarkup = sources.length ? sources.map((source) => `<li>${sourceLinkMarkup(source, null, source.label || source.id)}<small>${esc(first(source.publisher, source.kind, "source") || "")}</small></li>`).join("") : '<li class="model-source-empty">暂无直接来源链接。</li>';
    const rawJson = JSON.stringify(model, null, 2);
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3 id="drawerTitle">${esc(model.name)}</h3><p>${esc(model.provider)} · ${esc(familyName(model))}</p><div class="drawer-status-row">${statusBadge(model)}<span class="model-detail-id">${esc(model.id)}</span></div></div></div>
      <div class="model-drawer-summary"><p>${esc(model.summary)}</p><div class="model-card-tags">${tags || '<span class="model-badge muted-badge">暂无标签</span>'}</div></div>
      <section class="detail-section"><h4>MODEL PROFILE</h4><div class="detail-grid">
        ${detailItem("FAMILY", esc(model.familyId))}
        ${detailItem("RELEASE", esc(formatDate(model.releaseDate || model.release)))}
        ${detailItem("ACCESS", esc(model.access))}
        ${detailItem("STATUS", esc(statusLabel(model.status)))}
        ${detailItem("MODALITIES", esc(modalities))}
        ${detailItem("REASONING", esc(reasoning))}
        ${detailItem("CONTEXT", esc(formatContext(model.contextWindow)))}
        ${detailItem("PARAMETERS", esc(formatParams(model.paramsTotal, model.paramsActive)))}
        ${detailItem("OPEN WEIGHTS", model.openWeights ? '<span class="table-yes">yes</span>' : '<span class="table-muted">no / 未注明</span>')}
        ${detailItem("CATALOG STATE", model.catalogOnly ? "catalog-only" : "scored release")}
      </div></section>
      <section class="detail-section"><h4>ALIASES / ENDPOINT</h4><p class="model-aliases">${aliases}</p>${model.endpoint ? `<p class="model-endpoint"><span>endpoint</span> <code>${esc(model.endpoint)}</code></p>` : ""}</section>
      <section class="detail-section"><h4>PRIMARY SOURCES · ${sources.length}</h4><ul class="model-source-list">${sourceMarkup}</ul></section>
      <section class="detail-section"><h4>CANONICAL / CURATED SIGNALS · ${scoreItems.length}</h4>${scoreItems.length ? `<div class="model-score-list">${scoreItems.map(scoreMarkup).join("")}</div>` : '<p class="detail-note">当前目录暂无 canonical 成绩；这不表示模型未被测试。</p>'}</section>
      <section class="detail-section"><h4>PUBLIC REPORTED SIGNALS · ${publicDetail.rows.length}</h4>${publicDetail.rows.length ? `<p class="public-section-note">公开来源共 ${publicDetail.rows.length} 行，按 benchmark / metric / harness 去重后显示 ${publicDetail.distinct.length} 个代表项；全部保留在 snapshot 中，均标记“披露 · 未复现”。</p><div class="model-public-list">${publicDetail.distinct.slice(0, 100).map(publicMarkup).join("")}</div>${publicDetail.distinct.length > 100 ? `<p class="public-section-note">详情抽屉显示前 100 个代表项；可下载完整 <a href="data/public/evidence.jsonl" target="_blank" rel="noreferrer">公开 evidence JSONL ↗</a>。</p>` : ""}` : '<p class="detail-note">当前 snapshot 没有映射到该 release 的公开披露行；这不表示模型未被测试。</p>'}</section>
      <section class="detail-section"><h4>SYSTEM RUNS · ${runs.length}</h4>${runs.length ? `<div class="model-run-list">${runs.map(runMarkup).join("")}</div>` : '<p class="detail-note">当前 snapshot 没有与该 release 精确关联的 system run。</p>'}</section>
      <section class="detail-section"><details class="evidence-details"><summary>查看原始 catalog JSON</summary><pre class="model-json">${esc(rawJson)}</pre></details><button class="copy-json" type="button" data-copy-model="${esc(model.id)}">复制 JSON</button></section>`;
    els.drawer.setAttribute("aria-hidden", "false");
    els.drawer.classList.add("open");
    if (els.drawerBackdrop) els.drawerBackdrop.hidden = false;
    els.closeDrawer?.focus();
    els.drawerContent.querySelector("[data-copy-model]")?.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(rawJson);
        showToast("模型 JSON 已复制");
      } catch (_error) {
        showToast("当前浏览器不允许复制，请展开后手动复制");
      }
    });
  }

  function openModel(modelId, updateHash = false) {
    const model = state.models.find((item) => item.id === modelId || item.canonicalId === modelId);
    if (!model) return;
    if (updateHash) {
      const encoded = encodeURIComponent(model.id);
      if (location.hash !== `#model/${encoded}`) location.hash = `model/${encoded}`;
    }
    renderDrawer(model);
  }

  function closeDrawer(updateHash = true) {
    els.drawer?.classList.remove("open");
    els.drawer?.setAttribute("aria-hidden", "true");
    if (els.drawerBackdrop) els.drawerBackdrop.hidden = true;
    if (updateHash && location.hash.startsWith("#model/")) history.replaceState(null, "", `${location.pathname}${location.search}`);
  }

  function syncHash() {
    const raw = location.hash.replace(/^#/, "");
    if (!raw.startsWith("model/")) {
      closeDrawer(false);
      return;
    }
    let id = raw.slice("model/".length);
    try { id = decodeURIComponent(id); } catch (_error) { /* keep raw id */ }
    openModel(id, false);
  }

  function showToast(message) {
    if (!els.toast) return;
    clearTimeout(state.toastTimer);
    els.toast.textContent = message;
    els.toast.classList.add("show");
    state.toastTimer = setTimeout(() => els.toast.classList.remove("show"), 1800);
  }

  function resetFilters() {
    state.query = "";
    state.provider = "all";
    state.status = "all";
    state.family = "all";
    state.modality = "all";
    state.weights = "all";
    state.sort = "recent";
    state.currentOnly = false;
    state.withScoresOnly = false;
    if (els.searchInput) els.searchInput.value = "";
    if (els.providerFilter) els.providerFilter.value = "all";
    if (els.statusFilter) els.statusFilter.value = "all";
    if (els.familyFilter) els.familyFilter.value = "all";
    if (els.modalityFilter) els.modalityFilter.value = "all";
    if (els.weightsFilter) els.weightsFilter.value = "all";
    if (els.sortSelect) els.sortSelect.value = "recent";
    if (els.currentOnly) els.currentOnly.checked = false;
    if (els.withScoresOnly) els.withScoresOnly.checked = false;
    render();
  }

  function bindEvents() {
    els.searchInput?.addEventListener("input", (event) => { state.query = event.target.value; render(); });
    els.providerFilter?.addEventListener("change", (event) => { state.provider = event.target.value; render(); });
    els.statusFilter?.addEventListener("change", (event) => { state.status = event.target.value; render(); });
    els.familyFilter?.addEventListener("change", (event) => { state.family = event.target.value; render(); });
    els.modalityFilter?.addEventListener("change", (event) => { state.modality = event.target.value; render(); });
    els.weightsFilter?.addEventListener("change", (event) => { state.weights = event.target.value; render(); });
    els.sortSelect?.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
    els.currentOnly?.addEventListener("change", (event) => { state.currentOnly = event.target.checked; render(); });
    els.withScoresOnly?.addEventListener("change", (event) => { state.withScoresOnly = event.target.checked; render(); });
    els.resetFilters?.addEventListener("click", resetFilters);
    els.emptyReset?.addEventListener("click", resetFilters);
    els.modelGrid?.addEventListener("click", (event) => { const card = event.target.closest("[data-model-id]"); if (card) openModel(card.dataset.modelId, true); });
    els.modelGrid?.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { const card = event.target.closest("[data-model-id]"); if (card) { event.preventDefault(); openModel(card.dataset.modelId, true); } } });
    els.modelTableBody?.addEventListener("click", (event) => { const row = event.target.closest("[data-model-id]"); if (row) openModel(row.dataset.modelId, true); });
    els.modelTableBody?.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { const row = event.target.closest("[data-model-id]"); if (row) { event.preventDefault(); openModel(row.dataset.modelId, true); } } });
    els.viewTabs.forEach((tab) => tab.addEventListener("click", () => { state.view = tab.dataset.view; els.viewTabs.forEach((item) => { const active = item === tab; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); }); render(); }));
    els.closeDrawer?.addEventListener("click", () => closeDrawer(true));
    els.drawerBackdrop?.addEventListener("click", () => closeDrawer(true));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && els.drawer?.classList.contains("open")) closeDrawer(true);
      if (event.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { event.preventDefault(); els.searchInput?.focus(); }
    });
    window.addEventListener("hashchange", syncHash);
    const savedTheme = localStorage.getItem("fmb-theme");
    if (savedTheme === "light") document.documentElement.classList.add("light");
    if (els.themeToggle) {
      els.themeToggle.textContent = document.documentElement.classList.contains("light") ? "☾" : "☼";
      els.themeToggle.addEventListener("click", () => {
        const light = document.documentElement.classList.toggle("light");
        localStorage.setItem("fmb-theme", light ? "light" : "dark");
        els.themeToggle.textContent = light ? "☾" : "☼";
      });
    }
  }

  async function loadData() {
    const response = await fetch("data/derived/site.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`snapshot ${response.status}`);
    return response.json();
  }

  function applyData(data) {
    state.data = data || {};
    state.models = list(first(data?.catalogModels, data?.catalog_models, data?.models)).map(normaliseModel);
    state.sources = new Map(list(data?.sources).map((source) => [String(source.id), source]));
    state.benchmarks = new Map(list(data?.benchmarks).map((benchmark) => [String(benchmark.id), benchmark]));
    state.runs = list(data?.runs).map(normaliseRun);
    state.publicEvidence = list(first(data?.publicEvidence, data?.public_evidence)).map(normalisePublicEvidence).filter((item) => item.canonicalModelId);
    state.publicByModel = new Map();
    state.publicEvidence.forEach((item) => {
      const key = norm(item.canonicalModelId);
      if (!state.publicByModel.has(key)) state.publicByModel.set(key, []);
      state.publicByModel.get(key).push(item);
    });
    const meta = data?.meta || {};
    if (els.asOfLabel) els.asOfLabel.textContent = text(first(meta.asOf, meta.as_of, meta.lastUpdated), "—");
    if (els.catalogVersion) els.catalogVersion.textContent = text(first(meta.dataVersion, meta.version), "—");
    if (els.freshnessPill) els.freshnessPill.innerHTML = `<span class="status-dot"></span><span>${esc(first(meta.asOf, meta.lastUpdated, "snapshot"))}</span>`;
    updateStats();
    populateFilters();
    render();
    syncHash();
  }

  function showLoadError(error) {
    if (els.freshnessPill) els.freshnessPill.innerHTML = '<span class="status-dot status-dot-error"></span><span>snapshot unavailable</span>';
    if (els.modelGrid) els.modelGrid.innerHTML = `<div class="models-load-error"><strong>无法加载模型目录</strong><p>${esc(error?.message || "未知错误")}。请通过本地 HTTP server 或 GitHub Pages 打开此页。</p></div>`;
  }

  bindEvents();
  loadData().then(applyData).catch(showLoadError);
})();
