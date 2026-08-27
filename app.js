(() => {
  "use strict";

  /*
   * The page intentionally has a small, dependency-free view layer. The
   * canonical build (data/derived/site.json) is preferred, while the original
   * nested seed (data/models.json) remains a valid fallback. Keeping the
   * normalisation here makes the static page useful while adapters evolve.
   */
  const state = {
    data: null,
    dataPath: "",
    mode: "atlas",
    atlasView: "matrix",
    runView: "table",
    search: "",
    provider: "all",
    family: "all",
    harness: "all",
    runBenchmark: "all",
    // Start with a readable current-frontier slice; “所有模型 / benchmark”
    // remains available in the preset menu for the full registry.
    preset: "frontier-current",
    sort: "coverage",
    availableOnly: false,
    showCatalog: false,
    selected: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    asOfLabel: $("asOfLabel"), cadenceLabel: $("cadenceLabel"), qualityValue: $("qualityValue"),
    qualityBar: $("qualityBar"), modelCount: $("modelCount"), benchmarkCount: $("benchmarkCount"),
    familyCount: $("familyCount"), observationCount: $("observationCount"), coverageValue: $("coverageValue"),
    providerFilter: $("providerFilter"), familyFilter: $("familyFilter"), presetSelect: $("presetSelect"),
    harnessFilter: $("harnessFilter"), runBenchmarkFilter: $("runBenchmarkFilter"), sortSelect: $("sortSelect"),
    harnessFilterWrap: $("harnessFilterWrap"), runBenchmarkFilterWrap: $("runBenchmarkFilterWrap"),
    searchInput: $("searchInput"), availableOnly: $("availableOnly"), showCatalog: $("showCatalog"),
    activeFilters: $("activeFilters"), presetHint: $("presetHint"),
    matrixHead: $("matrixHead"), matrixBody: $("matrixBody"), matrixView: $("matrixView"), cardsView: $("cardsView"),
    emptyState: $("emptyState"), spotlightGrid: $("spotlightGrid"), spotlightSection: $("spotlightSection"),
    atlasLegend: $("atlasLegend"), runsView: $("runsView"), runTableFrame: $("runTableFrame"),
    runTableHead: $("runTableHead"), runTableBody: $("runTableBody"), runCardsView: $("runCardsView"),
    runEmptyState: $("runEmptyState"), runCountLabel: $("runCountLabel"),
    atlasViewSwitcher: $("atlasViewSwitcher"), runViewSwitcher: $("runViewSwitcher"),
    matrixTitle: $("matrixTitle"), matrixSubtitle: document.querySelector("#matrix .section-subtitle"),
    footerStatus: $("footerStatus"), freshnessPill: $("freshnessPill"), dataLink: $("dataLink"),
    drawer: $("detailDrawer"), drawerBackdrop: $("drawerBackdrop"), drawerContent: $("drawerContent"), toast: $("toast"),
  };

  const first = (...values) => values.find((value) => value !== undefined && value !== null && value !== "");
  const list = (value) => Array.isArray(value) ? value : (value === undefined || value === null ? [] : [value]);
  const text = (value, fallback = "") => value === undefined || value === null || value === "" ? fallback : String(value);
  const slug = (value) => text(value, "unknown").toLowerCase().trim().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "-").replace(/^-+|-+$/g, "") || "unknown";
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));
  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || value === "") return "—";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return String(value);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(digits).replace(/\.0$/, "");
  };
  const display = (value, fallback = "未注明") => {
    if (value === null || value === undefined || value === "") return fallback;
    if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(" · ");
    return String(value);
  };

  function normaliseScore(rawEntry) {
    if (rawEntry === null || rawEntry === undefined || rawEntry === "") return { value: null, verified: "missing" };
    if (typeof rawEntry === "number") return { value: rawEntry, verified: "reported" };
    if (typeof rawEntry === "string" && Number.isFinite(Number(rawEntry))) return { value: Number(rawEntry), verified: "reported" };
    const entry = { ...(typeof rawEntry === "object" ? rawEntry : { value: rawEntry }) };
    const rawValue = first(entry.value, entry.score, entry.result, entry.percentage, entry.accuracy);
    entry.value = rawValue === null || rawValue === undefined || rawValue === "" ? null : (Number.isFinite(Number(rawValue)) ? Number(rawValue) : rawValue);
    entry.setting = first(entry.setting, entry.protocol, entry.prompt, entry.config, "未说明");
    entry.verified = first(entry.verified, entry.status, entry.evidence, entry.evidenceLevel, entry.evidence_level, entry.value === null ? "missing" : "reported");
    entry.evidenceLevel = first(entry.evidenceLevel, entry.evidence_level, entry.evidence, entry.verified);
    entry.observedAt = first(entry.observedAt, entry.observed_at, entry.date);
    entry.sourceId = first(entry.sourceId, entry.source_id, entry.source, ...(list(entry.sourceIds || entry.source_ids)));
    entry.comparability = first(entry.comparability, entry.comparable, "conditional");
    entry.harnessId = first(entry.harnessId, entry.harness_id);
    entry.benchmarkVersion = first(entry.benchmarkVersion, entry.benchmark_version, entry.version);
    return entry;
  }

  function scoresFor(model) {
    const out = {};
    const rawScores = first(model.scores, model.scorecard, model.results, model.observationsByBenchmark, {});
    if (Array.isArray(rawScores)) {
      rawScores.forEach((entry) => {
        const benchmarkId = first(entry?.benchmarkId, entry?.benchmark_id, entry?.benchmark, entry?.id);
        if (benchmarkId) out[benchmarkId] = normaliseScore(entry);
      });
    } else if (rawScores && typeof rawScores === "object") {
      Object.entries(rawScores).forEach(([benchmarkId, entry]) => { out[benchmarkId] = normaliseScore(entry); });
    }
    // Some early canonical drafts put observations directly on the model.
    list(model.observations).forEach((entry) => {
      const benchmarkId = first(entry?.benchmarkId, entry?.benchmark_id, entry?.benchmark, entry?.id);
      if (benchmarkId && !out[benchmarkId]) out[benchmarkId] = normaliseScore(entry);
    });
    return out;
  }

  function normaliseModel(rawModel, catalogOnly = false) {
    const model = rawModel && typeof rawModel === "object" ? rawModel : {};
    const id = text(first(model.id, model.modelId, model.model_id, model.slug, model.name), "unknown-model");
    const explicitCatalog = Boolean(model.catalogOnly || model.catalog_only || model.status === "catalog-only" || model.status === "catalog_only");
    const tags = [...new Set([
      ...list(model.tags), ...list(model.capabilities), ...list(model.families),
    ].filter(Boolean).map(String))];
    return {
      ...model,
      id,
      name: text(first(model.name, model.displayName, model.display_name, id), id),
      provider: text(first(model.provider, model.organization, model.vendor), "Unknown"),
      mark: text(first(model.mark, model.logoMark, model.name?.slice?.(0, 1), id.slice(0, 1)), "?").slice(0, 2),
      release: first(model.release, model.releaseDate, model.release_date, model.date),
      access: first(model.access, model.availability, model.status),
      tags,
      family: first(model.family, model.familyId, model.family_id),
      familyId: first(model.familyId, model.family_id),
      modalities: list(first(model.modalities, model.modality)),
      summary: text(first(model.summary, model.description, model.note), "暂无模型说明。"),
      aliases: list(first(model.aliases, model.alias)),
      paramsTotal: first(model.paramsTotal, model.params_total, model.totalParams, model.parameters),
      paramsActive: first(model.paramsActive, model.params_active, model.activeParams),
      context: first(model.context, model.contextWindow, model.context_window),
      openWeights: first(model.openWeights, model.open_weights),
      license: first(model.license, model.licenseName, model.license_name),
      endpoint: first(model.endpoint, model.endpointId, model.endpoint_id),
      status: text(first(model.status, explicitCatalog || catalogOnly ? "catalog-only" : "active")),
      catalogOnly: explicitCatalog || catalogOnly,
      scores: scoresFor(model),
    };
  }

  function normaliseBenchmark(rawBenchmark) {
    const benchmark = rawBenchmark && typeof rawBenchmark === "object" ? rawBenchmark : { id: rawBenchmark, name: rawBenchmark };
    return {
      ...benchmark,
      id: text(first(benchmark.id, benchmark.benchmarkId, benchmark.benchmark_id, benchmark.name), "unknown-benchmark"),
      short: text(first(benchmark.short, benchmark.shortName, benchmark.short_name, benchmark.name, benchmark.id), "Benchmark"),
      name: text(first(benchmark.name, benchmark.title, benchmark.id), "Benchmark"),
      family: text(first(benchmark.family, benchmark.category, benchmark.track), "other"),
      familyLabel: text(first(benchmark.familyLabel, benchmark.family_label, benchmark.categoryLabel, benchmark.family), "其他"),
      metric: text(first(benchmark.metric, benchmark.metricName, benchmark.metric_name), "score"),
      metricLabel: text(first(benchmark.metricLabel, benchmark.metric_label, benchmark.metric), "score"),
      scale: (() => {
        const rawScale = first(benchmark.scale, benchmark.max, 100);
        if (rawScale && typeof rawScale === "object") return Number(first(rawScale.max, rawScale.maximum, 100)) || 100;
        return Number(rawScale) || 100;
      })(),
      unit: (() => {
        const rawUnit = text(first(benchmark.unit, benchmark.displayUnit, benchmark.display_unit), "%");
        return rawUnit.toLowerCase() === "percent" || rawUnit.toLowerCase() === "percentage" ? "%" : rawUnit;
      })(),
      direction: text(first(benchmark.direction, "higher")),
      version: first(benchmark.version, benchmark.benchmarkVersion, benchmark.benchmark_version),
      description: text(first(benchmark.description, benchmark.note), ""),
    };
  }

  function normaliseHarness(rawHarness) {
    const harness = rawHarness && typeof rawHarness === "object" ? rawHarness : { id: rawHarness, name: rawHarness };
    const id = text(first(harness.id, harness.harnessId, harness.harness_id, harness.name), "model-only");
    return {
      ...harness,
      id,
      name: text(first(harness.name, harness.displayName, harness.display_name, id), id),
      version: first(harness.version, harness.commit, harness.revision),
      description: text(first(harness.description, harness.note), ""),
    };
  }

  function normaliseRun(rawRun, index = 0) {
    const run = rawRun && typeof rawRun === "object" ? rawRun : {};
    const model = run.model && typeof run.model === "object" ? run.model : {};
    const benchmark = run.benchmark && typeof run.benchmark === "object" ? run.benchmark : {};
    const modelId = text(first(run.modelId, run.model_id, model.id, run.modelName, run.model_name), "unknown-model");
    const benchmarkId = text(first(run.benchmarkId, run.benchmark_id, benchmark.id, run.benchmarkName, run.benchmark_name), "unknown-benchmark");
    const rawValue = first(run.value, run.score, run.result, run.percentage);
    const numericValue = rawValue === null || rawValue === undefined || rawValue === "" ? null : (Number.isFinite(Number(rawValue)) ? Number(rawValue) : rawValue);
    return {
      ...run,
      id: text(first(run.id, run.runId, run.run_id), `run-${index + 1}`),
      modelId,
      modelName: text(first(run.modelName, run.model_name, model.name, modelId), modelId),
      endpointId: first(run.endpointId, run.endpoint_id, run.endpoint),
      harnessId: first(run.harnessId, run.harness_id, run.harness?.id),
      benchmarkId,
      benchmarkVersion: first(run.benchmarkVersion, run.benchmark_version, run.version, benchmark.version),
      metric: first(run.metric, run.metricName, run.metric_name, benchmark.metric),
      value: numericValue,
      unit: text(first(run.unit, benchmark.unit), "%"),
      protocol: first(run.protocol, run.protocolConfig, run.protocol_config, run.setting, run.config),
      evidence: first(run.evidence, run.evidenceLevel, run.evidence_level, run.verified, "reported"),
      evidenceLevel: first(run.evidenceLevel, run.evidence_level, run.evidence, run.verified, "reported"),
      comparability: first(run.comparability, run.comparable, "conditional"),
      status: first(run.status, run.verificationStatus, run.verification_status, "reported"),
      sourceId: first(run.sourceId, run.source_id, run.source, ...(list(run.sourceIds || run.source_ids))),
      observedAt: first(run.observedAt, run.observed_at, run.date),
      cost: first(run.cost, run.costUsd, run.cost_usd, run.price),
      latency: first(run.latency, run.latencyMs, run.latency_ms),
      tokens: first(run.tokens, run.outputTokens, run.output_tokens),
      steps: first(run.steps, run.stepCount, run.step_count),
      effort: first(run.effort, run.reasoningEffort, run.reasoning_effort),
      notes: first(run.notes, run.note, run.description),
    };
  }

  function deriveRuns(models, benchmarks) {
    return models.flatMap((model) => benchmarks.flatMap((benchmark) => {
      const entry = model.scores?.[benchmark.id];
      if (!entry || entry.value === null || entry.value === undefined) return [];
      return [normaliseRun({
        id: `score-${model.id}-${benchmark.id}`,
        modelId: model.id,
        modelName: model.name,
        benchmarkId: benchmark.id,
        benchmarkVersion: entry.benchmarkVersion || benchmark.version,
        metric: entry.metric || benchmark.metric,
        value: entry.value,
        unit: entry.unit || benchmark.unit,
        protocol: entry.protocol || entry.setting,
        evidence: entry.evidenceLevel || entry.verified,
        comparability: entry.comparability,
        status: entry.verified,
        sourceId: entry.sourceId,
        observedAt: entry.observedAt || entry.observed_at,
        notes: entry.note || entry.notes,
      }, 0)];
    }));
  }

  function normalisePreset(rawPreset, index = 0) {
    const preset = rawPreset && typeof rawPreset === "object" ? rawPreset : { id: rawPreset, name: rawPreset };
    const id = text(first(preset.id, preset.slug, preset.key), `preset-${index + 1}`);
    const modelFilter = first(preset.modelFilter, preset.model_filter, {}) || {};
    return {
      ...preset,
      id,
      name: text(first(preset.name, preset.label, preset.title, id), id),
      label: text(first(preset.label, preset.name, preset.title, id), id),
      description: text(first(preset.description, preset.note, preset.summary), ""),
      modelIds: list(first(preset.modelIds, preset.model_ids, preset.models)).map((item) => typeof item === "object" ? first(item.id, item.modelId, item.model_id) : String(item)).filter(Boolean),
      benchmarkIds: list(first(preset.benchmarkIds, preset.benchmark_ids, preset.benchmarks)).map((item) => typeof item === "object" ? first(item.id, item.benchmarkId, item.benchmark_id) : String(item)).filter(Boolean),
      harnessIds: list(first(preset.harnessIds, preset.harness_ids, preset.harnesses)).map((item) => typeof item === "object" ? first(item.id, item.harnessId, item.harness_id) : String(item)).filter(Boolean),
      providers: list(first(preset.providers, preset.provider)).map(String).filter(Boolean),
      tags: list(first(preset.tags, preset.capabilities)).map(String).filter(Boolean),
      families: list(first(preset.families, preset.benchmarkFamilies, preset.benchmark_families)).map(String).filter(Boolean),
      modelFilter,
      statuses: list(first(modelFilter.status, modelFilter.statuses, preset.status)).map(String).filter(Boolean),
      includeTags: list(first(modelFilter.includeTags, modelFilter.include_tags)).map(String).filter(Boolean),
      excludeTags: list(first(modelFilter.excludeTags, modelFilter.exclude_tags)).map(String).filter(Boolean),
      modalitiesAny: list(first(modelFilter.modalitiesAny, modelFilter.modalities_any)).map(String).filter(Boolean),
      familyIds: list(first(modelFilter.familyIds, modelFilter.family_ids)).map(String).filter(Boolean),
      minContextWindow: Number(first(modelFilter.minContextWindow, modelFilter.min_context_window, 0)) || 0,
      minParamsTotal: Number(first(modelFilter.minParamsTotal, modelFilter.min_params_total, 0)) || 0,
      openWeights: modelFilter.openWeights === true || modelFilter.open_weights === true,
      mode: first(preset.mode, preset.defaultMode),
    };
  }

  function normalise(raw) {
    const source = raw && typeof raw === "object" ? raw : {};
    const benchmarks = list(source.benchmarks).map(normaliseBenchmark);
    const models = list(source.models).map((model) => normaliseModel(model, false));
    const catalogModels = list(first(source.catalogModels, source.catalog_models)).map((model) => normaliseModel(model, true));
    const merged = [...models];
    const known = new Set(merged.map((model) => model.id));
    catalogModels.forEach((model) => { if (!known.has(model.id)) { merged.push(model); known.add(model.id); } });
    const harnesses = list(source.harnesses).map(normaliseHarness);
    const rawRuns = list(source.runs).map(normaliseRun);
    const runs = rawRuns.length ? rawRuns : deriveRuns(models, benchmarks);
    // Be forgiving when a producer ships a run before its registry row. The
    // row is surfaced as catalog-only rather than silently dropping evidence.
    const knownModelIds = new Set(merged.map((model) => model.id));
    runs.forEach((run) => {
      if (run.modelId && !knownModelIds.has(run.modelId)) {
        merged.push(normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider, status: "catalog-only" }, true));
        knownModelIds.add(run.modelId);
      }
    });
    const knownBenchmarkIds = new Set(benchmarks.map((benchmark) => benchmark.id));
    runs.forEach((run) => {
      if (run.benchmarkId && !knownBenchmarkIds.has(run.benchmarkId)) {
        benchmarks.push(normaliseBenchmark({ id: run.benchmarkId, name: run.benchmarkId, short: run.benchmarkId, unit: run.unit }));
        knownBenchmarkIds.add(run.benchmarkId);
      }
    });
    return {
      ...source,
      meta: source.meta || {},
      benchmarks,
      models: merged,
      catalogModels,
      harnesses,
      runs,
      presets: list(source.presets).map(normalisePreset),
      sources: list(source.sources),
    };
  }

  const sourceFor = (idOrSource) => {
    if (!idOrSource) return null;
    if (typeof idOrSource === "object") return idOrSource;
    const match = (state.data?.sources || []).find((source) => source.id === idOrSource || source.url === idOrSource);
    return match || (String(idOrSource).startsWith("http") ? { id: idOrSource, url: idOrSource, label: idOrSource } : null);
  };
  const benchmarkFor = (id) => (state.data?.benchmarks || []).find((benchmark) => benchmark.id === id);
  const harnessFor = (id) => (state.data?.harnesses || []).find((harness) => harness.id === id);
  const modelById = (id) => (state.data?.models || []).find((model) => model.id === id);
  const runById = (id) => (state.data?.runs || []).find((run) => run.id === id);

  function scoreEntry(model, benchmarkId) {
    const candidates = (state.data?.runs || []).filter((run) => run.modelId === model?.id && run.benchmarkId === benchmarkId && run.value !== null && run.value !== undefined);
    const isModelRun = (run) => run.harnessId === "model-only" || run.subjectType === "model" || !run.harnessId;
    const systemRuns = candidates.filter((run) => !isModelRun(run));
    const direct = model?.scores?.[benchmarkId];
    if (direct) {
      const entry = normaliseScore(direct);
      entry.systemRunCount = systemRuns.length;
      return entry;
    }
    // A derived site may only expose long-form runs.  The atlas is strictly
    // release/model-level: never promote an agentic system run to a model
    // score just because it is the only value available.  Those observations
    // remain visible in System Runs and in the model drawer's run list.
    const modelOnly = candidates.find((run) => isModelRun(run));
    if (modelOnly) {
      const entry = normaliseScore({ ...modelOnly, setting: modelOnly.protocol });
      entry.systemRunCount = systemRuns.length;
      return entry;
    }
    return {
      value: null,
      setting: systemRuns.length ? "切换 System Runs 查看" : "未报告",
      verified: "missing",
      systemRunCount: systemRuns.length,
    };
  }

  function allModels() { return state.data?.models || []; }
  function hasScore(model) {
    return (state.data?.benchmarks || []).some((benchmark) => {
      const value = scoreEntry(model, benchmark.id).value;
      return value !== null && value !== undefined;
    }) || (state.data?.runs || []).some((run) => run.modelId === model.id && run.value !== null && run.value !== undefined);
  }
  function modelCoverage(model, benchmarks = filteredBenchmarks()) {
    const observed = benchmarks.filter((benchmark) => {
      const value = scoreEntry(model, benchmark.id).value;
      return value !== null && value !== undefined;
    }).length;
    return benchmarks.length ? observed / benchmarks.length : 0;
  }

  function activePreset() { return state.data?.presets?.find((preset) => preset.id === state.preset) || null; }
  function presetAllowsModel(model) {
    const preset = activePreset();
    if (!preset) return true;
    if (preset.modelIds.length && !preset.modelIds.includes(model.id) && !preset.modelIds.includes(model.name)) return false;
    if (preset.providers.length && !preset.providers.includes(model.provider)) return false;
    if (preset.tags.length && !preset.tags.some((tag) => (model.tags || []).includes(tag))) return false;
    if (preset.statuses.length && !preset.statuses.includes(model.status)) return false;
    if (preset.includeTags.length && !preset.includeTags.some((tag) => (model.tags || []).includes(tag))) return false;
    if (preset.excludeTags.length && preset.excludeTags.some((tag) => (model.tags || []).includes(tag))) return false;
    if (preset.modalitiesAny.length && !preset.modalitiesAny.some((modality) => (model.modalities || []).includes(modality))) return false;
    if (preset.familyIds.length && !preset.familyIds.includes(model.familyId) && !preset.familyIds.includes(model.family)) return false;
    if (preset.minContextWindow) {
      const context = model.context && typeof model.context === "object"
        ? Math.max(...Object.values(model.context).map((value) => Number(value) || 0))
        : Number(model.context || 0);
      if (context < preset.minContextWindow) return false;
    }
    if (preset.minParamsTotal && Number(model.paramsTotal || 0) < preset.minParamsTotal) return false;
    if (preset.openWeights && model.openWeights !== true) return false;
    return true;
  }
  function presetAllowsBenchmark(benchmark) {
    const preset = activePreset();
    if (!preset) return true;
    if (preset.benchmarkIds.length && !preset.benchmarkIds.includes(benchmark.id)) return false;
    if (preset.families.length && !preset.families.includes(benchmark.family) && !preset.families.includes(benchmark.familyLabel)) return false;
    return true;
  }
  function presetAllowsRun(run) {
    const model = modelById(run.modelId);
    const benchmark = benchmarkFor(run.benchmarkId);
    const preset = activePreset();
    if (!preset) return true;
    if (!presetAllowsModel(model || { id: run.modelId, name: run.modelName, provider: run.provider, tags: [] })) return false;
    if (benchmark && !presetAllowsBenchmark(benchmark)) return false;
    if (preset.harnessIds.length && !preset.harnessIds.includes(run.harnessId)) return false;
    return true;
  }
  function filteredBenchmarks() {
    return (state.data?.benchmarks || []).filter((benchmark) => {
      if (!presetAllowsBenchmark(benchmark)) return false;
      if (state.mode === "runs" && state.runBenchmark !== "all" && benchmark.id !== state.runBenchmark) return false;
      return true;
    });
  }
  function searchableModel(model) {
    return [model.name, model.id, model.provider, model.summary, model.release, model.endpoint, model.paramsTotal, model.paramsActive, ...(model.tags || []), ...(model.aliases || [])].filter(Boolean).join(" ").toLowerCase();
  }
  function filteredModels() {
    const query = state.search.trim().toLowerCase();
    const benchmarks = filteredBenchmarks();
    const models = allModels().filter((model) => {
      const matchesQuery = !query || searchableModel(model).includes(query);
      const matchesProvider = state.provider === "all" || model.provider === state.provider;
      const modelFamilies = [...(model.tags || []), model.family].filter(Boolean);
      const matchesFamily = state.family === "all" || modelFamilies.includes(state.family);
      const matchesPreset = presetAllowsModel(model);
      const hasAnyScore = !state.availableOnly || benchmarks.some((benchmark) => {
        const value = scoreEntry(model, benchmark.id).value;
        return value !== null && value !== undefined;
      });
      const currentStatus = ["active", "preview", "restricted"].includes(String(model.status).toLowerCase());
      // Keep current catalog entries visible even before they have a score;
      // this makes the atlas a useful coverage map for newly released models.
      // Older/deprecated catalog-only entries stay behind the explicit toggle.
      const hiddenCatalog = !state.showCatalog && model.catalogOnly && !currentStatus;
      // Retired releases stay in the registry and in explicit historical
      // presets, but should not crowd the default “current” atlas.  The
      // full-catalog toggle is the deliberate way to inspect them.
      const hiddenRetired = !state.showCatalog && state.preset === "all" && ["deprecated", "retired"].includes(String(model.status).toLowerCase());
      return matchesQuery && matchesProvider && matchesFamily && matchesPreset && hasAnyScore && !hiddenCatalog && !hiddenRetired;
    });
    return models.sort((a, b) => {
      if (state.sort === "recent") return String(b.release || "").localeCompare(String(a.release || ""));
      if (state.sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      return modelCoverage(b, benchmarks) - modelCoverage(a, benchmarks) || String(b.release || "").localeCompare(String(a.release || ""));
    });
  }

  function filteredRuns() {
    const query = state.search.trim().toLowerCase();
    const runs = (state.data?.runs || []).filter((run) => {
      const model = modelById(run.modelId);
      const benchmark = benchmarkFor(run.benchmarkId);
      const harness = harnessFor(run.harnessId);
      const tags = model?.tags || [];
      const haystack = [run.id, run.modelName, run.modelId, model?.provider, benchmark?.name, benchmark?.family, harness?.name, run.harnessId, display(run.protocol), run.effort, run.status].filter(Boolean).join(" ").toLowerCase();
      const matchesQuery = !query || haystack.includes(query);
      const matchesProvider = state.provider === "all" || model?.provider === state.provider || run.provider === state.provider;
      const familyValues = [benchmark?.family, benchmark?.familyLabel, ...tags].filter(Boolean);
      const matchesFamily = state.family === "all" || familyValues.includes(state.family);
      const matchesHarness = state.harness === "all" || run.harnessId === state.harness;
      const matchesBenchmark = state.runBenchmark === "all" || run.benchmarkId === state.runBenchmark;
      const matchesPreset = presetAllowsRun(run);
      const hasValue = !state.availableOnly || (run.value !== null && run.value !== undefined);
      return matchesQuery && matchesProvider && matchesFamily && matchesHarness && matchesBenchmark && matchesPreset && hasValue;
    });
    return runs.sort((a, b) => {
      if (state.sort === "score-desc") return Number(b.value || -Infinity) - Number(a.value || -Infinity);
      if (state.sort === "cost") return Number(a.cost || Infinity) - Number(b.cost || Infinity);
      if (state.sort === "name") return a.modelName.localeCompare(b.modelName, "zh-CN");
      return String(b.observedAt || "").localeCompare(String(a.observedAt || ""));
    });
  }

  function scoreClass(entry, benchmark) {
    if (!entry || entry.value === null || entry.value === undefined || !Number.isFinite(Number(entry.value))) return "score-missing";
    const ratio = scoreRatio(entry.value, benchmark);
    if (benchmark?.direction === "lower") {
      if (ratio <= 0.15) return "score-high";
      if (ratio <= 0.3) return "score-mid";
      return "score-low";
    }
    if (ratio >= 0.85) return "score-high";
    if (ratio >= 0.70) return "score-mid";
    return "score-low";
  }
  function scoreRatio(value, benchmark) {
    const rawScale = benchmark?.scale;
    const minScale = rawScale && typeof rawScale === "object" ? Number(rawScale.min ?? 0) : 0;
    const maxScale = rawScale && typeof rawScale === "object" ? Number(rawScale.max ?? 100) : Number(rawScale || 100);
    return (Number(value) - minScale) / (maxScale - minScale || 1);
  }
  function statusLabel(entry) {
    const value = entry?.value;
    if (value === null || value === undefined || value === "") return "未报告";
    const status = String(first(entry.verified, entry.status, entry.evidence, "reported")).toLowerCase();
    if (status === "verified" || status === "reproduced") return "已核验";
    if (status === "reported" || status === "official") return "官方披露";
    if (status === "conditional") return "条件性";
    if (status === "demo" || status === "illustrative") return "示例数据";
    return status;
  }
  function statusClass(entry) {
    if (!entry || entry.value === null || entry.value === undefined || entry.value === "") return "missing";
    const status = String(first(entry.verified, entry.status, entry.evidence, "reported")).toLowerCase();
    if (["reported", "official", "verified", "reproduced"].includes(status)) return "reported";
    if (status === "conditional") return "conditional";
    if (status === "demo" || status === "illustrative") return "demo";
    return "conditional";
  }
  function evidenceWeight(entry) {
    const tier = String(first(entry?.evidenceLevel, entry?.evidence_level, "")).toUpperCase();
    const tierWeight = { A: 1, B: 0.85, C: 0.65, D: 0.4 }[tier];
    const status = String(first(entry?.verified, entry?.status, entry?.evidence, "reported")).toLowerCase();
    const fallback = ["verified", "reproduced"].includes(status) ? 1 : (["reported", "official", "published"].includes(status) ? 0.8 : 0.45);
    const comparability = String(first(entry?.comparability, "conditional")).toLowerCase();
    const comparabilityWeight = comparability === "exact" ? 1 : (comparability === "none" ? 0.7 : 0.9);
    return (tierWeight ?? fallback) * comparabilityWeight;
  }
  function badge(label, kind = "protocol-badge") { return `<span class="run-badge ${kind}">${esc(label)}</span>`; }
  function modelMarkup(model, extra = "") {
    const tags = (model.tags || []).slice(0, 3).map((tag) => `<span class="model-badge">${esc(tag)}</span>`).join("");
    const catalog = model.catalogOnly ? `<span class="model-badge catalog-badge">目录</span>` : "";
    const systems = Number(model.systemRunCount || 0) > 0 ? `<span class="model-badge system-run-badge">${fmt(model.systemRunCount, 0)} system runs</span>` : "";
    return `<div class="model-line"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><span><span class="model-name">${esc(model.name)}</span><span class="model-provider">${esc(model.provider)} · ${esc(model.release || "release 未注明")}</span></span></div><div class="model-badges">${catalog}${systems}${tags}</div>${extra}`;
  }

  function renderFilters() {
    const models = allModels();
    const providers = [...new Set(models.map((model) => model.provider).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    if (els.providerFilter) {
      els.providerFilter.innerHTML = '<option value="all">所有厂商</option>' + providers.map((provider) => `<option value="${esc(provider)}">${esc(provider)}</option>`).join("");
      els.providerFilter.value = providers.includes(state.provider) ? state.provider : "all";
    }
    const families = [...new Set([
      ...models.flatMap((model) => model.tags || []),
      ...(state.data?.benchmarks || []).flatMap((benchmark) => [benchmark.family, benchmark.familyLabel]),
    ].filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    if (els.familyFilter) {
      els.familyFilter.innerHTML = '<option value="all">所有能力面 / 标签</option>' + families.map((family) => `<option value="${esc(family)}">${esc(family)}</option>`).join("");
      els.familyFilter.value = families.includes(state.family) ? state.family : "all";
    }
    if (els.presetSelect) {
      els.presetSelect.innerHTML = '<option value="all">所有模型 / benchmark</option>' + (state.data?.presets || []).map((preset) => `<option value="${esc(preset.id)}">${esc(preset.label)}</option>`).join("");
      els.presetSelect.value = state.preset;
    }
    if (els.harnessFilter) {
      const harnesses = state.data?.harnesses || [];
      els.harnessFilter.innerHTML = '<option value="all">所有 harness</option>' + harnesses.map((harness) => `<option value="${esc(harness.id)}">${esc(harness.name)}${harness.version ? ` · ${esc(harness.version)}` : ""}</option>`).join("");
      els.harnessFilter.value = state.harness;
    }
    if (els.runBenchmarkFilter) {
      els.runBenchmarkFilter.innerHTML = '<option value="all">所有 benchmark</option>' + (state.data?.benchmarks || []).map((benchmark) => `<option value="${esc(benchmark.id)}">${esc(benchmark.short || benchmark.name)}</option>`).join("");
      els.runBenchmarkFilter.value = state.runBenchmark;
    }
    if (els.sortSelect) {
      const atlasOptions = [["recent", "按发布日期"], ["coverage", "按覆盖率"], ["name", "按模型名称"]];
      const runOptions = [["run-recent", "按运行时间"], ["score-desc", "按分数"], ["cost", "按成本"], ["name", "按模型名称"]];
      const options = state.mode === "runs" ? runOptions : atlasOptions;
      if (!options.some(([value]) => value === state.sort)) state.sort = options[0][0];
      els.sortSelect.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
      els.sortSelect.value = state.sort;
    }
    if (els.harnessFilterWrap) els.harnessFilterWrap.hidden = state.mode !== "runs";
    if (els.runBenchmarkFilterWrap) els.runBenchmarkFilterWrap.hidden = state.mode !== "runs";
    if (els.atlasViewSwitcher) els.atlasViewSwitcher.hidden = state.mode !== "atlas";
    if (els.runViewSwitcher) els.runViewSwitcher.hidden = state.mode !== "runs";
    if (els.presetHint) {
      const preset = activePreset();
      els.presetHint.hidden = !preset || !preset.description;
      if (preset) els.presetHint.textContent = preset.description;
    }
  }

  function renderActiveFilters() {
    const chips = [];
    if (state.search) chips.push(`搜索：${esc(state.search)}`);
    if (state.provider !== "all") chips.push(`厂商：${esc(state.provider)}`);
    if (state.family !== "all") chips.push(`能力：${esc(state.family)}`);
    if (state.preset !== "all") chips.push(`预设：${esc(activePreset()?.label || state.preset)}`);
    if (state.mode === "runs" && state.harness !== "all") chips.push(`harness：${esc(harnessFor(state.harness)?.name || state.harness)}`);
    if (state.mode === "runs" && state.runBenchmark !== "all") chips.push(`benchmark：${esc(benchmarkFor(state.runBenchmark)?.short || state.runBenchmark)}`);
    if (state.availableOnly) chips.push("只看有成绩");
    if (state.showCatalog) chips.push("全量目录");
    if (els.activeFilters) els.activeFilters.innerHTML = chips.map((chip) => `<span class="filter-chip">${chip}</span>`).join("");
  }

  function setStatCopy(mode) {
    const cards = [...document.querySelectorAll(".stat-card")];
    if (cards.length < 4) return;
    const labels = mode === "runs" ? ["SYSTEM MODELS", "RUN BENCHMARKS", "SYSTEM RUNS", "VALUE COVERAGE"] : ["TRACKED MODELS", "BENCHMARKS", "OBSERVATIONS", "COVERAGE"];
    const notes = mode === "runs" ? ["参与当前筛选的模型", "当前运行记录覆盖的 benchmark", "有 protocol 的系统记录", "运行记录非缺失率"] : ["当前目录中的 model release", "跨能力面的 benchmark", "直接 model-level 成绩", "矩阵非缺失率"];
    cards.forEach((card, index) => {
      const kicker = card.querySelector(".stat-kicker");
      const note = card.querySelector(".stat-note");
      if (kicker) kicker.textContent = labels[index];
      if (note) note.textContent = notes[index];
    });
  }

  function renderStats() {
    const benchmarks = filteredBenchmarks();
    if (state.mode === "runs") {
      const runs = filteredRuns();
      const modelIds = new Set(runs.map((run) => run.modelId));
      const benchmarkIds = new Set(runs.map((run) => run.benchmarkId));
      const observed = runs.filter((run) => run.value !== null && run.value !== undefined).length;
      const coverage = runs.length ? observed / runs.length : 0;
      const quality = runs.reduce((sum, run) => sum + evidenceWeight(run), 0);
      const qualityPct = runs.length ? Math.round(Math.min(100, quality / runs.length * 100)) : 0;
      if (els.modelCount) els.modelCount.textContent = modelIds.size;
      if (els.benchmarkCount) els.benchmarkCount.textContent = benchmarkIds.size;
      if (els.familyCount) els.familyCount.textContent = new Set([...benchmarkIds].map((id) => benchmarkFor(id)?.family).filter(Boolean)).size;
      if (els.observationCount) els.observationCount.textContent = runs.length;
      if (els.coverageValue) els.coverageValue.textContent = `${Math.round(coverage * 100)}%`;
      if (els.qualityValue) els.qualityValue.textContent = `${qualityPct}%`;
      if (els.qualityBar) els.qualityBar.style.width = `${qualityPct}%`;
      if (els.runCountLabel) els.runCountLabel.textContent = runs.length;
      setStatCopy("runs");
    } else {
      const models = filteredModels();
      const observed = models.reduce((sum, model) => sum + benchmarks.filter((benchmark) => {
        const value = scoreEntry(model, benchmark.id).value;
        return value !== null && value !== undefined;
      }).length, 0);
      const total = models.length * benchmarks.length;
      const coverage = total ? observed / total : 0;
      const quality = models.reduce((sum, model) => sum + benchmarks.reduce((inner, benchmark) => {
        const entry = scoreEntry(model, benchmark.id);
        return inner + (entry.value !== null && entry.value !== undefined ? evidenceWeight(entry) : 0);
      }, 0), 0);
      const qualityPct = observed ? Math.round(Math.min(100, quality / observed * 100)) : 0;
      if (els.modelCount) els.modelCount.textContent = models.length;
      if (els.benchmarkCount) els.benchmarkCount.textContent = benchmarks.length;
      if (els.familyCount) els.familyCount.textContent = new Set(benchmarks.map((benchmark) => benchmark.family)).size;
      if (els.observationCount) els.observationCount.textContent = observed;
      if (els.coverageValue) els.coverageValue.textContent = `${Math.round(coverage * 100)}%`;
      if (els.qualityValue) els.qualityValue.textContent = `${qualityPct}%`;
      if (els.qualityBar) els.qualityBar.style.width = `${qualityPct}%`;
      setStatCopy("atlas");
    }
    if (els.asOfLabel) els.asOfLabel.textContent = state.data?.meta?.asOf || state.data?.meta?.lastUpdated?.slice?.(0, 10) || "—";
    if (els.cadenceLabel) els.cadenceLabel.textContent = state.data?.meta?.updateCadence || state.data?.meta?.update_cadence || "—";
    const status = String(state.data?.meta?.status || "curated").toLowerCase();
    const isDemo = ["demo", "illustrative", "seed"].includes(status);
    if (els.freshnessPill) els.freshnessPill.innerHTML = `<span class="status-dot"></span><span>${isDemo ? "seed snapshot" : "curated snapshot"}</span>`;
    if (els.footerStatus) els.footerStatus.textContent = isDemo ? "Seed data: replace or verify before citing." : `${state.data?.runs?.length || 0} system runs · sources linked per observation.`;
  }

  function renderMatrix() {
    const benchmarks = filteredBenchmarks();
    const models = filteredModels();
    if (els.matrixHead) els.matrixHead.innerHTML = `<tr><th scope="col">MODEL / RELEASE</th>${benchmarks.map((benchmark) => `<th scope="col"><span class="bench-head"><strong>${esc(benchmark.short || benchmark.name)}</strong><small>${esc(benchmark.metricLabel || benchmark.metric || "score")}${benchmark.evaluationMode === "system" ? " · system" : ""}</small></span></th>`).join("")}</tr>`;
    if (els.matrixBody) els.matrixBody.innerHTML = models.map((model) => {
      const cells = benchmarks.map((benchmark) => {
        const entry = scoreEntry(model, benchmark.id);
        const missing = entry.value === null || entry.value === undefined;
        const source = sourceFor(entry.sourceId);
        const sourceMark = source ? '<span class="source-chip">S</span>' : "";
        const runHint = missing && entry.systemRunCount ? `<span class="score-run-hint">↗ ${entry.systemRunCount} run${entry.systemRunCount === 1 ? "" : "s"}</span>` : "";
        return `<td class="score-cell ${scoreClass(entry, benchmark)}" data-model="${esc(model.id)}" data-benchmark="${esc(benchmark.id)}" tabindex="0" role="button" aria-label="${esc(model.name)} ${esc(benchmark.name)} ${missing ? (entry.systemRunCount ? `${entry.systemRunCount} system runs；切换 System Runs` : "未报告") : fmt(entry.value) + (benchmark.unit || "")}"><span class="score-value">${missing ? "—" : fmt(entry.value)}${!missing && benchmark.unit ? `<small>${esc(benchmark.unit)}</small>` : ""}${sourceMark}</span>${runHint}<span class="score-setting">${esc(display(entry.setting, "未说明"))}</span></td>`;
      }).join("");
      return `<tr><td class="model-cell" data-model="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)}">${modelMarkup(model)}</td>${cells}</tr>`;
    }).join("");
    if (els.emptyState) els.emptyState.hidden = models.length !== 0;
  }

  function renderCards() {
    const models = filteredModels();
    const benchmarks = filteredBenchmarks();
    if (!els.cardsView) return;
    els.cardsView.innerHTML = models.map((model) => {
      const ranked = benchmarks.map((benchmark) => ({ benchmark, entry: scoreEntry(model, benchmark.id) })).filter(({ entry }) => entry.value !== null && entry.value !== undefined).slice(0, 5);
      const recorded = benchmarks.filter((benchmark) => {
        const value = scoreEntry(model, benchmark.id).value;
        return value !== null && value !== undefined;
      }).length;
      const bars = ranked.map(({ benchmark, entry }) => `<div class="mini-bar-row"><span>${esc(benchmark.short || benchmark.name)}</span><span class="mini-bar-track"><span style="width:${Math.min(100, Math.max(0, scoreRatio(entry.value, benchmark) * 100))}%"></span></span><strong>${fmt(entry.value)}</strong></div>`).join("");
      return `<article class="model-card ${model.catalogOnly ? "catalog-only-card" : ""}" data-model="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 详情"><div class="card-top"><div>${modelMarkup(model)}</div><span class="card-score">${recorded}/${benchmarks.length}<small>${model.catalogOnly ? "catalog" : "reported"}</small></span></div><div class="mini-bars">${bars || '<p class="card-empty-note">暂无已录入分数；打开详情查看目录信息。</p>'}</div></article>`;
    }).join("");
  }

  function harnessLabel(run) {
    const harness = harnessFor(run.harnessId);
    if (!harness) return "model-only";
    return `${harness.name}${harness.version ? ` · ${harness.version}` : ""}`;
  }
  function protocolLabel(run) {
    const parts = [];
    if (run.protocol && typeof run.protocol === "object") {
      const protocol = run.protocol;
      if (protocol.shots !== null && protocol.shots !== undefined) parts.push(`${protocol.shots}-shot`);
      if (protocol.tools !== null && protocol.tools !== undefined) parts.push(protocol.tools ? "tools" : "no tools");
      if (protocol.reasoning_mode && protocol.reasoning_mode !== "reported") parts.push(String(protocol.reasoning_mode));
      if (protocol.temperature !== null && protocol.temperature !== undefined) parts.push(`t=${protocol.temperature}`);
      if (!parts.length && protocol.raw_setting) parts.push(String(protocol.raw_setting));
    } else if (run.protocol) {
      parts.push(display(run.protocol));
    }
    if (run.effort) parts.push(`effort ${run.effort}`);
    if (run.endpointId) parts.push(run.endpointId);
    return parts.join(" · ") || "未说明";
  }
  function runScoreEntry(run) { return { value: run.value, verified: first(run.status, run.verificationStatus, run.evidence, "reported"), evidenceLevel: run.evidenceLevel, status: run.status }; }
  function runRow(run) {
    const model = modelById(run.modelId) || normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider });
    const benchmark = benchmarkFor(run.benchmarkId) || { id: run.benchmarkId, name: run.benchmarkId, short: run.benchmarkId, scale: 100, unit: run.unit || "%" };
    const entry = runScoreEntry(run);
    const source = sourceFor(run.sourceId);
    const evidence = statusLabel(entry);
    const badges = `${badge(harnessLabel(run), "harness-badge")}${badge(protocolLabel(run), "protocol-badge")}`;
    return `<tr class="run-row" data-run="${esc(run.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 的 ${esc(benchmark.name)} system run"><td class="run-model-cell">${modelMarkup(model)}</td><td><span class="run-benchmark-name">${esc(benchmark.short || benchmark.name)}</span><small>${esc(benchmark.version || run.benchmarkVersion || "version 未注明")}</small></td><td class="run-score-cell ${scoreClass(entry, benchmark)}"><strong>${run.value === null || run.value === undefined ? "—" : fmt(run.value)}${run.value !== null && run.value !== undefined ? esc(run.unit || benchmark.unit || "") : ""}</strong><small>${esc(run.metric || benchmark.metric || "score")}</small></td><td><div class="run-badges">${badges}</div></td><td><span class="status-badge ${statusClass(entry)}">${esc(evidence)}</span><small class="run-date">${esc(run.observedAt || "未注明")}</small></td><td class="run-source-cell">${source ? '<span class="source-chip">S</span>' : "—"}</td></tr>`;
  }
  function renderRuns() {
    const runs = filteredRuns();
    if (els.runTableHead) els.runTableHead.innerHTML = "<tr><th>MODEL / RELEASE</th><th>BENCHMARK</th><th>SCORE</th><th>HARNESS / PROTOCOL</th><th>EVIDENCE / DATE</th><th>SOURCE</th></tr>";
    if (els.runTableBody) els.runTableBody.innerHTML = runs.map(runRow).join("");
    if (els.runEmptyState) els.runEmptyState.hidden = runs.length !== 0;
    if (els.runCountLabel) els.runCountLabel.textContent = runs.length;
    if (els.runCardsView) els.runCardsView.innerHTML = runs.map((run) => {
      const model = modelById(run.modelId) || normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider });
      const benchmark = benchmarkFor(run.benchmarkId) || { name: run.benchmarkId, short: run.benchmarkId, scale: 100 };
      const entry = runScoreEntry(run);
      return `<article class="run-card" data-run="${esc(run.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} system run"><div class="run-card-top"><div>${modelMarkup(model)}</div><strong class="run-card-score ${scoreClass(entry, benchmark)}">${run.value === null || run.value === undefined ? "—" : fmt(run.value)}<small>${esc(run.unit || benchmark.unit || "")}</small></strong></div><div class="run-card-benchmark"><span>${esc(benchmark.name || benchmark.short)}</span><small>${esc(benchmark.version || run.benchmarkVersion || "version 未注明")}</small></div><div class="run-badges">${badge(harnessLabel(run), "harness-badge")}${badge(protocolLabel(run), "protocol-badge")}<span class="status-badge ${statusClass(entry)}">${esc(statusLabel(entry))}</span></div><p class="run-card-note">${esc(run.notes || `observed ${run.observedAt || "未注明"}`)}</p></article>`;
    }).join("");
  }

  function renderSpotlights() {
    const benchmarks = filteredBenchmarks();
    const models = filteredModels().filter((model) => hasScore(model));
    const signals = benchmarks.map((benchmark, order) => {
      const values = models.map((model) => ({ model, entry: scoreEntry(model, benchmark.id) })).filter(({ entry }) => entry.value !== null && entry.value !== undefined).sort((a, b) => benchmark.direction === "lower" ? Number(a.entry.value) - Number(b.entry.value) : Number(b.entry.value) - Number(a.entry.value));
      return { benchmark, best: values[0], count: values.length, order };
    }).filter((signal) => signal.best).sort((a, b) => b.count - a.count || a.order - b.order).slice(0, 3);
    if (els.spotlightGrid) els.spotlightGrid.innerHTML = signals.map(({ benchmark, best, count }) => `<article class="spotlight-card"><span class="spotlight-kicker">${esc(benchmark.familyLabel || benchmark.family)} / ${esc(benchmark.short || benchmark.name)}</span><h3>${esc(best.model.name)}</h3><p><span class="spotlight-number">${fmt(best.entry.value)}${esc(benchmark.unit || "")}</span> · column leader among ${count}/${models.length} reported observations</p></article>`).join("");
  }

  function updateModeCopy() {
    const atlas = state.mode === "atlas";
    if (els.matrixTitle) els.matrixTitle.textContent = atlas ? "Model Atlas" : "System Runs";
    if (els.matrixSubtitle) els.matrixSubtitle.textContent = atlas ? "静态能力按 model 展示；点击单元格查看版本、设置与来源。不同 benchmark 不合成总分。" : "一行代表一次 model × harness × protocol 运行；只在相同口径下比较，不跨 harness 合并。";
    if (els.spotlightSection) els.spotlightSection.hidden = !atlas;
    if (els.atlasLegend) els.atlasLegend.hidden = !atlas;
    if (els.matrixView) els.matrixView.hidden = !atlas || state.atlasView !== "matrix";
    if (els.cardsView) els.cardsView.hidden = !atlas || state.atlasView !== "cards";
    if (els.runsView) els.runsView.hidden = atlas;
    if (els.runTableFrame) els.runTableFrame.hidden = !(!atlas && state.runView === "table");
    if (els.runCardsView) els.runCardsView.hidden = !(!atlas && state.runView === "cards");
    document.querySelectorAll(".mode-tab").forEach((tab) => {
      const active = tab.dataset.mode === state.mode;
      tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => {
      const active = tab.dataset.view === state.atlasView;
      tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".view-tab[data-run-view]").forEach((tab) => {
      const active = tab.dataset.runView === state.runView;
      tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active));
    });
  }

  function render() {
    renderFilters();
    renderActiveFilters();
    renderStats();
    renderMatrix();
    renderCards();
    renderRuns();
    renderSpotlights();
    updateModeCopy();
  }

  function detailGrid(items) {
    return `<div class="detail-grid">${items.map(([label, value]) => `<div class="detail-item"><label>${esc(label)}</label><span>${esc(display(value))}</span></div>`).join("")}</div>`;
  }
  function openModelDrawer(modelId, benchmarkId = null) {
    const model = modelById(modelId);
    if (!model || !els.drawerContent) return;
    state.selected = { type: "model", modelId, benchmarkId };
    const benchmark = benchmarkId ? benchmarkFor(benchmarkId) : null;
    const entry = benchmark ? scoreEntry(model, benchmark.id) : null;
    const source = entry ? sourceFor(entry.sourceId) : null;
    const benchmarks = state.data?.benchmarks || [];
    const recorded = benchmarks.map((item) => ({ benchmark: item, entry: scoreEntry(model, item.id) })).filter(({ entry: itemEntry }) => itemEntry.value !== null && itemEntry.value !== undefined);
    const mainScore = entry || (recorded[0]?.entry || { value: null });
    const mainBenchmark = benchmark || recorded[0]?.benchmark;
    const relatedRuns = (state.data?.runs || []).filter((run) => run.modelId === model.id).slice(0, 8);
    const runLinks = relatedRuns.map((run) => `<button class="drawer-run-link" type="button" data-run="${esc(run.id)}"><span>${esc(benchmarkFor(run.benchmarkId)?.short || run.benchmarkId)}</span><strong>${run.value === null || run.value === undefined ? "—" : fmt(run.value)}${esc(run.unit || "%")}</strong></button>`).join("");
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3>${esc(model.name)}</h3><p>${esc(model.provider)} · release ${esc(model.release || "未注明")} · ${esc(model.status || model.access || "access 未注明")}</p></div></div><div class="drawer-score"><span class="status-badge ${statusClass(mainScore)}">${esc(statusLabel(mainScore))}</span><div class="big-score">${mainScore.value !== null && mainScore.value !== undefined ? `${fmt(mainScore.value)}<small>${esc(mainBenchmark?.unit || "")}</small>` : "—"}</div><p>${mainBenchmark ? `${esc(mainBenchmark.name)} · ${esc(display(mainScore.setting, "设置未说明"))}` : "选择一个单元格查看具体 observation。"}</p></div><section class="detail-section"><h4>Model note</h4><p class="detail-note">${esc(model.summary)}</p></section><section class="detail-section"><h4>Model registry</h4>${detailGrid([["Status", model.status], ["Access", model.access], ["Params total", model.paramsTotal], ["Params active", model.paramsActive], ["Context", model.context], ["Endpoint", model.endpoint]])}</section><section class="detail-section"><h4>Protocol & provenance</h4>${detailGrid([["Benchmark version", mainScore.benchmarkVersion || mainScore.version || mainBenchmark?.version], ["Observed", mainScore.observedAt || mainScore.observed_at || state.data?.meta?.asOf], ["Comparability", mainScore.comparability || "conditional"], ["Evidence", mainScore.evidenceLevel || mainScore.evidence_level || mainScore.verified]])}${mainScore.note || mainScore.notes ? `<p class="detail-note">${esc(mainScore.note || mainScore.notes)}</p>` : ""}</section>${source ? `<section class="detail-section"><h4>Source</h4><a class="source-link" href="${esc(source.url)}" target="_blank" rel="noreferrer">↗ ${esc(source.label || source.title || source.url)}</a>${source.locator ? `<p class="detail-note">定位：${esc(source.locator)}</p>` : ""}</section>` : ""}<section class="detail-section"><h4>Recorded signals</h4><div class="timeline">${recorded.map(({ benchmark: itemBenchmark, entry: itemEntry }) => `<div class="timeline-row"><span>${esc(itemBenchmark.short || itemBenchmark.name)}</span><span class="timeline-track"><i style="width:${Math.min(100, Math.max(0, scoreRatio(itemEntry.value, itemBenchmark) * 100))}%"></i></span><strong>${fmt(itemEntry.value)}${esc(itemBenchmark.unit || "")}</strong></div>`).join("") || '<p class="detail-note">暂无可显示的成绩。</p>'}</div></section>${runLinks ? `<section class="detail-section"><h4>System runs</h4><div class="drawer-run-list">${runLinks}</div></section>` : ""}<button class="copy-json" type="button" id="copyObservation">复制 JSON</button>`;
    showDrawer();
    const copyButton = $("copyObservation");
    if (copyButton) copyButton.addEventListener("click", () => copyJson(benchmark ? { model_id: model.id, benchmark_id: benchmark.id, ...mainScore } : model, "已复制 JSON"));
  }

  function openRunDrawer(runId) {
    const run = runById(runId);
    if (!run || !els.drawerContent) return;
    state.selected = { type: "run", runId };
    const model = modelById(run.modelId) || normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider });
    const benchmark = benchmarkFor(run.benchmarkId) || { name: run.benchmarkId, short: run.benchmarkId, unit: run.unit || "%" };
    const harness = harnessFor(run.harnessId);
    const source = sourceFor(run.sourceId);
    const entry = runScoreEntry(run);
    const related = (state.data?.runs || []).filter((item) => item.modelId === run.modelId && item.benchmarkId === run.benchmarkId && item.id !== run.id).slice(0, 6);
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3>${esc(model.name)}</h3><p>${esc(model.provider)} · ${esc(run.endpointId || model.endpoint || "endpoint 未注明")}</p></div></div><div class="drawer-score run-drawer-score"><span class="status-badge ${statusClass(entry)}">${esc(statusLabel(entry))}</span><div class="big-score">${run.value === null || run.value === undefined ? "—" : `${fmt(run.value)}<small>${esc(run.unit || benchmark.unit || "")}</small>`}</div><p>${esc(benchmark.name)} · ${esc(run.benchmarkVersion || benchmark.version || "version 未注明")}</p></div><section class="detail-section"><h4>Harness & protocol</h4>${detailGrid([["Harness", harness ? `${harness.name}${harness.version ? ` · ${harness.version}` : ""}` : "model-only"], ["Endpoint", run.endpointId], ["Protocol", protocolLabel(run)], ["Effort", run.effort], ["Steps", run.steps], ["Tools", run.tools || run.toolPolicy || run.tool_policy]])}</section><section class="detail-section"><h4>Run provenance</h4>${detailGrid([["Benchmark", benchmark.name], ["Metric", run.metric || benchmark.metric], ["Observed", run.observedAt], ["Comparability", run.comparability], ["Evidence", run.evidenceLevel || run.evidence], ["Cost", run.cost], ["Latency", run.latency]])}${run.notes ? `<p class="detail-note">${esc(run.notes)}</p>` : ""}</section>${source ? `<section class="detail-section"><h4>Source</h4><a class="source-link" href="${esc(source.url)}" target="_blank" rel="noreferrer">↗ ${esc(source.label || source.title || source.url)}</a>${source.locator ? `<p class="detail-note">定位：${esc(source.locator)}</p>` : ""}</section>` : ""}${related.length ? `<section class="detail-section"><h4>Same model / benchmark</h4><div class="drawer-run-list">${related.map((item) => `<button class="drawer-run-link" type="button" data-run="${esc(item.id)}"><span>${esc(harnessFor(item.harnessId)?.name || "model-only")}</span><strong>${item.value === null || item.value === undefined ? "—" : fmt(item.value)}${esc(item.unit || benchmark.unit || "")}</strong></button>`).join("")}</div></section>` : ""}<button class="copy-json" type="button" id="copyObservation">复制 run JSON</button>`;
    showDrawer();
    const copyButton = $("copyObservation");
    if (copyButton) copyButton.addEventListener("click", () => copyJson(run, "已复制 run JSON"));
  }

  function showDrawer() {
    if (!els.drawer || !els.drawerBackdrop) return;
    els.drawerBackdrop.hidden = false;
    requestAnimationFrame(() => { els.drawer.classList.add("open"); els.drawer.setAttribute("aria-hidden", "false"); });
  }
  function closeDrawer() {
    if (!els.drawer || !els.drawerBackdrop) return;
    els.drawer.classList.remove("open"); els.drawer.setAttribute("aria-hidden", "true");
    setTimeout(() => { els.drawerBackdrop.hidden = true; }, 280);
  }
  function copyJson(payload, message) {
    const json = JSON.stringify(payload, null, 2);
    const write = navigator.clipboard?.writeText ? navigator.clipboard.writeText(json) : Promise.reject(new Error("clipboard unavailable"));
    write.then(() => showToast(message)).catch(() => showToast("浏览器阻止了复制，请从 Data 打开"));
  }
  function showToast(message) {
    if (!els.toast) return;
    els.toast.textContent = message; els.toast.classList.add("show"); clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => els.toast.classList.remove("show"), 2200);
  }

  function resetFilters() {
    state.search = ""; state.provider = "all"; state.family = "all"; state.harness = "all"; state.runBenchmark = "all"; state.preset = "all"; state.sort = state.mode === "runs" ? "run-recent" : "coverage"; state.availableOnly = false; state.showCatalog = false;
    if (els.searchInput) els.searchInput.value = "";
    if (els.availableOnly) els.availableOnly.checked = false;
    if (els.showCatalog) els.showCatalog.checked = false;
    render();
  }

  function bind() {
    els.searchInput?.addEventListener("input", (event) => { state.search = event.target.value; render(); });
    els.providerFilter?.addEventListener("change", (event) => { state.provider = event.target.value; render(); });
    els.familyFilter?.addEventListener("change", (event) => { state.family = event.target.value; render(); });
    els.presetSelect?.addEventListener("change", (event) => {
      state.preset = event.target.value;
      const preset = activePreset();
      // Presets declare the appropriate comparison subject.  Switching back
      // from a run preset must explicitly return to the release-level atlas;
      // otherwise the controls keep showing a stale System Runs view.
      state.mode = preset?.mode === "runs" ? "runs" : "atlas";
      state.sort = state.mode === "runs" ? "run-recent" : "coverage";
      render();
    });
    els.harnessFilter?.addEventListener("change", (event) => { state.harness = event.target.value; render(); });
    els.runBenchmarkFilter?.addEventListener("change", (event) => { state.runBenchmark = event.target.value; render(); });
    els.sortSelect?.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
    els.availableOnly?.addEventListener("change", (event) => { state.availableOnly = event.target.checked; render(); });
    els.showCatalog?.addEventListener("change", (event) => { state.showCatalog = event.target.checked; render(); });
    $("resetFilters")?.addEventListener("click", resetFilters); $("emptyReset")?.addEventListener("click", resetFilters); $("runEmptyReset")?.addEventListener("click", resetFilters);
    document.querySelectorAll(".mode-tab").forEach((tab) => tab.addEventListener("click", () => { state.mode = tab.dataset.mode; state.sort = state.mode === "runs" ? "run-recent" : "coverage"; render(); }));
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => tab.addEventListener("click", () => { state.atlasView = tab.dataset.view; render(); }));
    document.querySelectorAll(".view-tab[data-run-view]").forEach((tab) => tab.addEventListener("click", () => { state.runView = tab.dataset.runView; render(); }));
    document.addEventListener("click", (event) => {
      const runTarget = event.target.closest("[data-run]");
      if (runTarget) return openRunDrawer(runTarget.dataset.run);
      const cell = event.target.closest("[data-model][data-benchmark]");
      if (cell) return openModelDrawer(cell.dataset.model, cell.dataset.benchmark);
      const modelTarget = event.target.closest("[data-model]");
      if (modelTarget) openModelDrawer(modelTarget.dataset.model);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && document.activeElement !== els.searchInput) { event.preventDefault(); els.searchInput?.focus(); }
      if (event.key === "Escape") closeDrawer();
      if (event.key === "Enter" && document.activeElement?.matches("[data-run]")) openRunDrawer(document.activeElement.dataset.run);
      else if (event.key === "Enter" && document.activeElement?.matches("[data-model]")) openModelDrawer(document.activeElement.dataset.model, document.activeElement.dataset.benchmark || null);
    });
    $("closeDrawer")?.addEventListener("click", closeDrawer); els.drawerBackdrop?.addEventListener("click", closeDrawer);
    const themeButton = $("themeToggle");
    const savedTheme = localStorage.getItem("fmb-theme"); if (savedTheme === "light") document.documentElement.classList.add("light");
    themeButton?.addEventListener("click", () => { const light = document.documentElement.classList.toggle("light"); localStorage.setItem("fmb-theme", light ? "light" : "dark"); themeButton.textContent = light ? "☾" : "☼"; });
    if (themeButton) themeButton.textContent = document.documentElement.classList.contains("light") ? "☾" : "☼";
  }

  async function readData() {
    const paths = ["data/derived/site.json", "data/models.json"];
    let lastError = new Error("没有可读取的数据文件");
    for (const path of paths) {
      try {
        const response = await fetch(path, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const raw = await response.json();
        return { raw, path };
      } catch (error) { lastError = error; }
    }
    throw lastError;
  }

  async function boot() {
    try {
      const loaded = await readData();
      state.dataPath = loaded.path;
      state.data = normalise(loaded.raw);
      if (state.preset !== "all" && !state.data.presets.some((preset) => preset.id === state.preset)) state.preset = "all";
      if (els.dataLink) els.dataLink.href = loaded.path;
      if (els.searchInput) els.searchInput.placeholder = state.dataPath.includes("derived") ? "搜索模型、endpoint、harness 或标签…" : "搜索模型、厂商或标签…";
      bind();
      render();
    } catch (error) {
      console.error(error);
      if (els.footerStatus) els.footerStatus.textContent = `无法读取数据；请通过本地服务器打开。${error.message ? ` (${error.message})` : ""}`;
      if (els.matrixBody) els.matrixBody.innerHTML = `<tr><td colspan="99" class="empty-state"><h3>数据加载失败</h3><p>${esc(error.message)}</p></td></tr>`;
    }
  }

  boot();
})();
