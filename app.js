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
    // Public evidence is broad by default; the preset menu still offers a
    // compact current-frontier slice when a narrower view is preferable.
    preset: "public-coverage",
    sort: "coverage",
    availableOnly: false,
    showCatalog: false,
    matrixDensity: "compact",
    matrixBenchmarkJump: "",
    publicEvidenceExpanded: false,
    runPage: 0,
    selected: null,
  };

  const RUN_PAGE_SIZE = 50;

  const $ = (id) => document.getElementById(id);
  const els = {
    asOfLabel: $("asOfLabel"), cadenceLabel: $("cadenceLabel"), qualityValue: $("qualityValue"),
    qualityBar: $("qualityBar"), modelCount: $("modelCount"), benchmarkCount: $("benchmarkCount"),
    familyCount: $("familyCount"), observationCount: $("observationCount"), coverageValue: $("coverageValue"),
    providerFilter: $("providerFilter"), familyFilter: $("familyFilter"), presetSelect: $("presetSelect"),
    harnessFilter: $("harnessFilter"), runBenchmarkFilter: $("runBenchmarkFilter"), sortSelect: $("sortSelect"),
    harnessFilterWrap: $("harnessFilterWrap"), runBenchmarkFilterWrap: $("runBenchmarkFilterWrap"),
    searchInput: $("searchInput"), availableOnly: $("availableOnly"), showCatalog: $("showCatalog"),
    activeFilters: $("activeFilters"), presetHint: $("presetHint"), coverageNote: $("coverageNote"),
    matrixHead: $("matrixHead"), matrixBody: $("matrixBody"), matrixView: $("matrixView"), matrixScroll: $("matrixScroll"), cardsView: $("cardsView"),
    matrixTools: $("matrixTools"), matrixNavigationStatus: $("matrixNavigationStatus"), benchmarkJump: $("benchmarkJump"), matrixHome: $("matrixHome"),
    emptyState: $("emptyState"), spotlightGrid: $("spotlightGrid"), spotlightSection: $("spotlightSection"),
    atlasLegend: $("atlasLegend"), publicEvidenceSection: $("publicEvidenceSection"), publicEvidenceToggle: $("publicEvidenceToggle"), publicEvidenceBody: $("publicEvidenceBody"), publicEvidenceCount: $("publicEvidenceCount"), publicEvidenceList: $("publicEvidenceList"), publicAliasLedger: $("publicAliasLedger"),
    runsView: $("runsView"), runTableFrame: $("runTableFrame"),
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
  // URLs come from catalog and public snapshots, so treat them as untrusted
  // data before interpolating them into an anchor.  The static site only
  // needs external HTTP(S) source links; reject javascript:, data:, file: and
  // malformed values even if a future hand-edited snapshot contains them.
  const safeUrl = (value) => {
    const candidate = String(value ?? "").trim();
    if (!/^https?:\/\//i.test(candidate)) return "";
    try {
      const parsed = new URL(candidate);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? candidate : "";
    } catch (_error) {
      return "";
    }
  };
  // Try candidates independently: a malformed first field must not hide a
  // valid page/API URL supplied in a later field of the same snapshot row.
  const firstSafeUrl = (...values) => {
    for (const value of values) {
      const url = safeUrl(value);
      if (url) return url;
    }
    return "";
  };
  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || value === "") return "—";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return String(value);
    if (Object.is(numeric, -0)) return "0";
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(digits).replace(/\.0$/, "");
  };
  const display = (value, fallback = "未注明") => {
    if (value === null || value === undefined || value === "") return fallback;
    if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(" · ");
    return String(value);
  };
  const unitLabel = (value, fallback = "%") => {
    const unit = text(value, fallback);
    const lowered = unit.toLowerCase();
    return lowered === "percent" || lowered === "percentage" ? "%" : unit;
  };

  /*
   * Public evidence is deliberately kept separate from our own run layer.
   * Producers may call it `publicEvidence`, `evidenceRecords`, or simply
   * `evidence`; this small adapter accepts all of those spellings and keeps
   * provenance fields intact.  Evidence is ranked for display only — it is
   * never silently upgraded to an independently reproduced result.
   */
  function evidenceStatus(raw, fallback = "reported") {
    const value = raw && typeof raw === "object"
      ? first(raw.approvalStatus, raw.approval_status, raw.status, raw.state,
        raw.reviewStatus, raw.review_status, raw.verificationStatus, raw.verification_status,
        raw.evidenceStatus, raw.evidence_status,
        typeof raw.evidence === "string" ? raw.evidence : null, raw.kind)
      : raw;
    const status = String(first(value, fallback) || fallback).trim().toLowerCase().replace(/[\s_]+/g, "-");
    if (["approved", "accepted", "verified", "reproduced", "canonical", "validated", "reviewed"].includes(status)) return "approved";
    if (["candidate", "pending", "unreviewed", "discovered", "proposed", "queued"].includes(status)) return "candidate";
    if (["reported", "published", "official", "provider", "provider-report", "self-report", "selfreported", "disclosed"].includes(status)) return "reported";
    if (["missing", "unavailable", "not-reported"].includes(status)) return "missing";
    return status || fallback;
  }

  function evidencePriority(item) {
    const status = evidenceStatus(item, "reported");
    return status === "approved" ? 3 : (status === "reported" ? 2 : (status === "candidate" ? 1 : 0));
  }

  function hasEvidencePayload(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    return [
      "value", "score", "result", "percentage", "accuracy", "rawValue", "raw_value",
      "status", "state", "approvalStatus", "approval_status", "evidenceLevel", "evidence_level",
      "sourceId", "source_id", "sourceIds", "source_ids", "sourceUrl", "source_url", "url",
      "locator", "sourceLocator", "source_locator", "evidenceId", "evidence_id", "candidateId",
      "observedAt", "observed_at", "publishedAt", "published_at", "retrievedAt", "retrieved_at",
      "fetchedAt", "fetched_at", "sha256", "snapshotHash", "snapshot_hash", "hash", "protocol",
    ].some((key) => Object.prototype.hasOwnProperty.call(value, key));
  }

  function evidenceRelations(value, inherited = {}) {
    const object = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    const model = object.model && typeof object.model === "object" ? object.model : {};
    const benchmark = object.benchmark && typeof object.benchmark === "object" ? object.benchmark : {};
    return {
      ...inherited,
      modelId: first(object.modelId, object.model_id, object.canonicalModelId, object.canonical_model_id,
        object.modelRef, object.model_ref, model.id, model.modelId, model.model_id,
        object.sourceModel, object.source_model, object.sourceModelName, object.source_model_name,
        object.modelName, object.model_name, inherited.modelId),
      benchmarkId: first(object.benchmarkId, object.benchmark_id, object.benchmarkRef, object.benchmark_ref,
        benchmark.id, benchmark.benchmarkId, benchmark.benchmark_id,
        object.sourceBenchmark, object.source_benchmark, object.benchmarkName, object.benchmark_name, inherited.benchmarkId),
    };
  }

  /* Recursively flatten common wrappers (`items`, `records`, keyed maps). */
  function flattenEvidence(raw, inherited = {}, output = []) {
    if (raw === null || raw === undefined || raw === "") return output;
    if (Array.isArray(raw)) {
      raw.forEach((item) => flattenEvidence(item, inherited, output));
      return output;
    }
    if (typeof raw !== "object") {
      output.push({ ...inherited, value: raw });
      return output;
    }
    const relation = evidenceRelations(raw, inherited);
    const wrappers = ["items", "records", "rows", "values", "evidence", "publicEvidence", "public_evidence", "evidenceRecords", "evidence_records"];
    const nested = wrappers.filter((key) => Object.prototype.hasOwnProperty.call(raw, key));
    if (hasEvidencePayload(raw) || (!nested.length && Object.keys(raw).length === 0)) {
      output.push({ ...relation, ...raw });
    }
    nested.forEach((key) => {
      const child = raw[key];
      /* A string evidence level is metadata, not a standalone row. */
      if (key === "evidence" && typeof child === "string") return;
      flattenEvidence(child, relation, output);
    });
    if (!hasEvidencePayload(raw) && !nested.length) {
      Object.entries(raw).forEach(([key, child]) => {
        if (child === null || child === undefined) return;
        const lower = key.toLowerCase();
        const next = { ...relation };
        if (lower.includes("model") && !next.modelId) next.modelId = key;
        else if ((lower.includes("benchmark") || lower.includes("bench")) && !next.benchmarkId) next.benchmarkId = key;
        else if (!next.modelId && (key.includes("/") || key.includes("@"))) next.modelId = key;
        else if (!next.benchmarkId) next.benchmarkId = key;
        flattenEvidence(child, next, output);
      });
    }
    return output;
  }

  function normaliseEvidence(rawEvidence, fallback = {}) {
    const raw = rawEvidence && typeof rawEvidence === "object" && !Array.isArray(rawEvidence)
      ? { ...fallback, ...rawEvidence } : { ...fallback, value: rawEvidence };
    const nestedEvidence = raw.evidence && typeof raw.evidence === "object" && !Array.isArray(raw.evidence) ? raw.evidence : {};
    const rawValue = first(raw.value, raw.score, raw.result, raw.percentage, raw.accuracy, raw.rawValue, raw.raw_value);
    const value = rawValue === null || rawValue === undefined || rawValue === ""
      ? null : (Number.isFinite(Number(rawValue)) ? Number(rawValue) : rawValue);
    const source = raw.source && typeof raw.source === "object" ? raw.source : {};
    const sourceIds = list(first(raw.sourceIds, raw.source_ids, nestedEvidence.sourceIds, nestedEvidence.source_ids));
    const sourceId = first(raw.sourceId, raw.source_id, typeof raw.source === "string" ? raw.source : null,
      source.id, nestedEvidence.sourceId, nestedEvidence.source_id, ...sourceIds);
    const sourceUrl = first(raw.sourceUrl, raw.source_url, raw.evidenceUrl, raw.evidence_url, raw.url, source.url, nestedEvidence.sourceUrl, nestedEvidence.source_url, nestedEvidence.evidenceUrl, nestedEvidence.evidence_url, nestedEvidence.url);
    const sourceLabel = first(raw.sourceLabel, raw.source_label, raw.sourceTitle, raw.source_title,
      raw.title, source.label, source.title, nestedEvidence.sourceLabel, nestedEvidence.source_label);
    const subject = raw.subject && typeof raw.subject === "object" ? raw.subject : {};
    const protocol = raw.protocol && typeof raw.protocol === "object" ? raw.protocol : {};
    const level = first(raw.level, raw.evidenceLevel, raw.evidence_level, nestedEvidence.level,
      nestedEvidence.evidenceLevel, nestedEvidence.evidence_level);
    const status = evidenceStatus(raw, value === null ? "missing" : "reported");
    const modelId = first(raw.canonicalModelId, raw.canonical_model_id, raw.modelId, raw.model_id,
      raw.canonicalModel, raw.canonical_model,
      raw.modelRef, raw.model_ref, raw.sourceModel, raw.source_model, raw.sourceModelName, raw.source_model_name,
      raw.modelName, raw.model_name, fallback.modelId, fallback.model_id);
    const benchmarkId = first(raw.benchmarkId, raw.benchmark_id, raw.benchmarkRef, raw.benchmark_ref,
      raw.sourceBenchmark, raw.source_benchmark, raw.benchmarkName, raw.benchmark_name,
      fallback.benchmarkId, fallback.benchmark_id);
    return {
      ...raw,
      id: first(raw.id, raw.evidenceId, raw.evidence_id, raw.candidateId, raw.candidate_id),
      evidenceId: first(raw.evidenceId, raw.evidence_id, raw.id, raw.candidateId, raw.candidate_id),
      modelId,
      canonicalModelId: first(raw.canonicalModelId, raw.canonical_model_id),
      modelRef: first(raw.modelRef, raw.model_ref, raw.sourceModel, raw.source_model),
      benchmarkId,
      benchmarkVersionId: first(raw.benchmarkVersionId, raw.benchmark_version_id, raw.versionId, raw.version_id),
      metricId: first(raw.metricId, raw.metric_id, raw.metric, raw.metricName, raw.metric_name),
      subjectType: first(raw.subjectType, raw.subject_type, subject.type, subject.subjectType, subject.subject_type, protocol.subjectType, protocol.subject_type),
      sourceSubjectType: first(raw.sourceSubjectType, raw.source_subject_type, subject.sourceType, subject.source_type,
        raw.subjectType, raw.subject_type, subject.type, subject.subjectType, subject.subject_type, protocol.subjectType, protocol.subject_type),
      sourceModel: first(raw.sourceModel, raw.source_model, raw.sourceModelName, raw.source_model_name, raw.modelRef, raw.model_ref, raw.modelName, raw.model_name),
      value,
      unit: (() => {
        const rawUnit = first(raw.unit, raw.displayUnit, raw.display_unit);
        if (!rawUnit) return raw.unit;
        const lowered = String(rawUnit).toLowerCase();
        return lowered === "percent" || lowered === "percentage" ? "%" : rawUnit;
      })(),
      rawValue: first(raw.rawValue, raw.raw_value, raw.value, raw.score, raw.result),
      status,
      evidenceStatus: status,
      level,
      evidenceLevel: level,
      sourceId,
      sourceUrl,
      sourceLabel,
      harnessId: first(raw.harnessId, raw.harness_id, protocol.harnessId, protocol.harness_id),
      harness: first(raw.harness, protocol.harness),
      locator: first(raw.locator, raw.sourceLocator, raw.source_locator, raw.evidenceLocator, raw.evidence_locator),
      fetchedAt: first(raw.fetchedAt, raw.fetched_at, raw.retrievedAt, raw.retrieved_at, raw.retrievedOn, raw.retrieved_on),
      snapshotHash: first(raw.snapshotHash, raw.snapshot_hash, raw.sha256, raw.hash, raw.checksum, raw.payloadSha256, raw.payload_sha256),
      publishedAt: first(raw.publishedAt, raw.published_at),
      observedAt: first(raw.observedAt, raw.observed_at, raw.date),
      protocol: first(raw.protocol, raw.protocolConfig, raw.protocol_config, raw.setting, raw.config),
      notes: first(raw.notes, raw.note, raw.description),
      preferred: raw.preferred === true || raw.isPreferred === true || raw.is_preferred === true,
      public: raw.public === true || raw.publicEvidence === true || raw.public_evidence === true || raw.origin === "public" || raw.evidenceOrigin === "public" || raw.verificationStatus === "not_reproduced",
      evidenceOrigin: first(raw.evidenceOrigin, raw.evidence_origin, raw.origin, raw.public === true || raw.verificationStatus === "not_reproduced" ? "public" : "canonical"),
    };
  }

  function evidenceItems(raw) {
    if (!raw || typeof raw !== "object") return [];
    const rawItems = [];
    if (Array.isArray(raw.evidenceItems)) rawItems.push(...raw.evidenceItems);
    ["publicEvidence", "public_evidence", "evidenceRecords", "evidence_records"].forEach((key) => {
      if (raw[key] !== undefined && raw[key] !== null) rawItems.push(raw[key]);
    });
    if (Array.isArray(raw.evidence) || (raw.evidence && typeof raw.evidence === "object")) rawItems.push(raw.evidence);
    if (!rawItems.length && hasEvidencePayload(raw)) rawItems.push(raw);
    const flattened = [];
    rawItems.forEach((item) => flattenEvidence(item, evidenceRelations(raw), flattened));
    const normalised = flattened.map((item) => normaliseEvidence(item, evidenceRelations(raw))).filter((item) => item.value !== null || item.sourceUrl || item.sourceId || item.locator || item.status);
    const seen = new Set();
    return normalised.filter((item) => {
      const key = [item.evidenceId || "", item.sourceId || "", item.sourceUrl || "", item.locator || "", item.status || "", item.value ?? ""].join("|");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  /* A canonical run/score often stores the value on the parent object and
     keeps only source metadata in `evidence`.  Hydrate that metadata row with
     the parent value so the drawer does not render a misleading “missing”
     evidence item. */
  function hydrateEvidenceItems(items, raw, value) {
    if (value === null || value === undefined || value === "") return items;
    const fallbackStatus = evidenceStatus(raw, "reported");
    const rawValue = first(raw?.rawValue, raw?.raw_value, raw?.value, raw?.score, raw?.result, value);
    return (items || []).map((item) => {
      if (item.value !== null && item.value !== undefined && item.value !== "") return item;
      return normaliseEvidence({ ...item, value, rawValue, status: fallbackStatus, evidenceStatus: fallbackStatus }, {
        ...evidenceRelations(raw),
        value,
        rawValue,
        status: fallbackStatus,
        evidenceLevel: first(item.evidenceLevel, item.evidence_level, raw?.evidenceLevel, raw?.evidence_level),
      });
    });
  }

  function chooseEvidence(items) {
    return [...(items || [])].sort((a, b) => {
      return Number(Boolean(b.preferred)) - Number(Boolean(a.preferred))
        || evidencePriority(b) - evidencePriority(a)
        || Number(Boolean(b.public || b.evidenceOrigin !== "public")) - Number(Boolean(a.public || a.evidenceOrigin !== "public"))
        || (Number(a.selectionRank || 999) - Number(b.selectionRank || 999))
        || String(b.observedAt || b.publishedAt || b.fetchedAt || "").localeCompare(String(a.observedAt || a.publishedAt || a.fetchedAt || ""));
    })[0] || null;
  }

  function mergeScoreEntries(base, incoming) {
    if (!base) return incoming;
    if (!incoming) return base;
    const merged = { ...base, ...incoming };
    const items = evidenceItems(base).concat(evidenceItems(incoming));
    const unique = [];
    const seen = new Set();
    items.forEach((item) => {
      const key = [item.evidenceId || "", item.sourceId || "", item.sourceUrl || "", item.locator || "", item.status || "", item.value ?? ""].join("|");
      if (!seen.has(key)) { seen.add(key); unique.push(item); }
    });
    const selected = chooseEvidence(unique);
    if (selected) {
      ["value", "rawValue", "sourceId", "sourceUrl", "sourceLabel", "locator", "fetchedAt", "snapshotHash", "publishedAt", "observedAt", "protocol", "notes", "evidenceLevel"].forEach((key) => {
        if (selected[key] !== undefined && selected[key] !== null && selected[key] !== "") merged[key] = selected[key];
      });
      merged.evidenceStatus = selected.status;
      merged.approvalStatus = selected.status;
      merged.verified = selected.status;
      merged.status = selected.status;
      merged.public = Boolean(selected.public || selected.evidenceOrigin === "public");
      merged.evidenceOrigin = selected.evidenceOrigin || (merged.public ? "public" : "canonical");
      merged.subjectType = first(selected.subjectType, merged.subjectType);
    }
    merged.evidenceItems = unique;
    merged.publicEvidence = unique;
    return merged;
  }

  function normaliseScore(rawEntry) {
    if (rawEntry === null || rawEntry === undefined || rawEntry === "") return { value: null, verified: "missing", evidenceItems: [] };
    if (typeof rawEntry === "number") {
      const evidence = normaliseEvidence({ value: rawEntry, status: "reported" });
      return { value: rawEntry, verified: "reported", evidenceStatus: "reported", evidenceItems: [evidence], publicEvidence: [evidence] };
    }
    if (typeof rawEntry === "string" && Number.isFinite(Number(rawEntry))) {
      const value = Number(rawEntry);
      const evidence = normaliseEvidence({ value, rawValue: rawEntry, status: "reported" });
      return { value, rawValue: rawEntry, verified: "reported", evidenceStatus: "reported", evidenceItems: [evidence], publicEvidence: [evidence] };
    }
    const entry = { ...(typeof rawEntry === "object" ? rawEntry : { value: rawEntry }) };
    const rawValue = first(entry.value, entry.score, entry.result, entry.percentage, entry.accuracy);
    entry.value = rawValue === null || rawValue === undefined || rawValue === "" ? null : (Number.isFinite(Number(rawValue)) ? Number(rawValue) : rawValue);
    entry.setting = first(entry.setting, entry.protocol, entry.prompt, entry.config, "未说明");
    const items = hydrateEvidenceItems(evidenceItems(entry), entry, entry.value);
    const selected = chooseEvidence(items);
    const directEvidence = typeof entry.evidence === "string" ? entry.evidence : null;
    entry.verified = first(entry.verified, entry.approvalStatus, entry.approval_status, entry.status, directEvidence,
      selected?.status, entry.value === null ? "missing" : "reported");
    entry.evidenceStatus = evidenceStatus(entry, selected?.status || (entry.value === null ? "missing" : "reported"));
    entry.evidenceLevel = first(entry.evidenceLevel, entry.evidence_level, selected?.level, entry.verified);
    entry.observedAt = first(entry.observedAt, entry.observed_at, entry.date, selected?.observedAt);
    entry.sourceId = first(entry.sourceId, entry.source_id, typeof entry.source === "string" ? entry.source : null,
      ...(list(entry.sourceIds || entry.source_ids)), selected?.sourceId);
    entry.sourceUrl = first(entry.sourceUrl, entry.source_url, entry.url, selected?.sourceUrl);
    entry.sourceLabel = first(entry.sourceLabel, entry.source_label, entry.sourceTitle, entry.source_title, selected?.sourceLabel);
    entry.locator = first(entry.locator, entry.sourceLocator, entry.source_locator, selected?.locator);
    entry.fetchedAt = first(entry.fetchedAt, entry.fetched_at, entry.retrievedAt, entry.retrieved_at, selected?.fetchedAt);
    entry.snapshotHash = first(entry.snapshotHash, entry.snapshot_hash, entry.sha256, entry.hash, selected?.snapshotHash);
    entry.publishedAt = first(entry.publishedAt, entry.published_at, selected?.publishedAt);
    entry.protocol = first(entry.protocol, selected?.protocol);
    entry.subjectType = first(entry.subjectType, entry.subject_type, selected?.subjectType);
    entry.public = Boolean(entry.public || selected?.public || selected?.evidenceOrigin === "public");
    entry.evidenceOrigin = first(entry.evidenceOrigin, entry.evidence_origin, selected?.evidenceOrigin, entry.public ? "public" : "canonical");
    entry.publicEvidence = items;
    entry.evidenceItems = items;
    /* A public record can be the only value for a cell.  Promote the chosen
       record's value for display, while retaining every alternative above. */
    if (selected && selected.value !== null && selected.value !== undefined && selected.value !== "") {
      entry.value = selected.value;
      entry.rawValue = first(selected.rawValue, entry.rawValue, entry.value);
    }
    entry.comparability = first(entry.comparability, entry.comparable, "conditional");
    entry.harnessId = first(entry.harnessId, entry.harness_id);
    entry.benchmarkVersion = first(entry.benchmarkVersion, entry.benchmark_version, entry.version);
    return entry;
  }

  function scoresFor(model) {
    const out = {};
    const addScore = (benchmarkId, rawEntry) => {
      if (!benchmarkId) return;
      const entry = normaliseScore(rawEntry);
      out[benchmarkId] = mergeScoreEntries(out[benchmarkId], entry);
    };
    const rawScores = first(model.scores, model.scorecard, model.results, model.observationsByBenchmark, {});
    if (Array.isArray(rawScores)) {
      rawScores.forEach((entry) => {
        const benchmarkId = first(entry?.benchmarkId, entry?.benchmark_id, entry?.benchmark, entry?.id);
        addScore(benchmarkId, entry);
      });
    } else if (rawScores && typeof rawScores === "object") {
      Object.entries(rawScores).forEach(([benchmarkId, entry]) => addScore(benchmarkId, entry));
    }
    // Some early canonical drafts put observations directly on the model.
    list(model.observations).forEach((entry) => {
      const benchmarkId = first(entry?.benchmarkId, entry?.benchmark_id, entry?.benchmark, entry?.id);
      addScore(benchmarkId, entry);
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
      // Keep an explicit lower bound when a metric is not zero-based (for
      // example Arena IPS).  Older seed data still uses a numeric max.
      scale: (() => {
        const rawScale = first(benchmark.scale, benchmark.max, 100);
        if (rawScale && typeof rawScale === "object") {
          const min = Number(first(rawScale.min, rawScale.minimum, 0));
          const max = Number(first(rawScale.max, rawScale.maximum, 100));
          return Number.isFinite(min) && Number.isFinite(max) && max > min ? { min, max } : 100;
        }
        return Number(rawScale) || 100;
      })(),
      unit: (() => {
        const rawUnit = text(first(benchmark.unit, benchmark.displayUnit, benchmark.display_unit), "%");
        return rawUnit.toLowerCase() === "percent" || rawUnit.toLowerCase() === "percentage" ? "%" : rawUnit;
      })(),
      direction: text(first(benchmark.direction, "higher")),
      evaluationMode: text(first(benchmark.evaluationMode, benchmark.evaluation_mode, benchmark.subjectType, benchmark.subject_type), "direct").toLowerCase(),
      subjectType: first(benchmark.subjectType, benchmark.subject_type),
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
      kind: text(first(harness.kind, harness.type), "unknown").toLowerCase(),
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
    const runEvidence = hydrateEvidenceItems(evidenceItems(run), run, numericValue);
    const selectedEvidence = chooseEvidence(runEvidence);
    const directEvidence = typeof run.evidence === "string" ? run.evidence : null;
    return {
      ...run,
      id: text(first(run.id, run.runId, run.run_id), `run-${index + 1}`),
      modelId,
      modelName: text(first(run.modelName, run.model_name, model.name, modelId), modelId),
      endpointId: first(run.endpointId, run.endpoint_id, run.endpoint),
      harnessId: first(run.harnessId, run.harness_id, run.harness?.id),
      sourceSubjectType: first(run.sourceSubjectType, run.source_subject_type, run.subjectType, run.subject_type),
      subjectType: first(run.subjectType, run.subject_type),
      benchmarkId,
      benchmarkVersion: first(run.benchmarkVersion, run.benchmark_version, run.version, benchmark.version),
      metric: first(run.metric, run.metricName, run.metric_name, benchmark.metric),
      value: numericValue,
      unit: unitLabel(first(run.unit, benchmark.unit), "%"),
      protocol: first(run.protocol, run.protocolConfig, run.protocol_config, run.setting, run.config),
      evidenceRaw: run.evidence,
      evidence: first(directEvidence, run.status, run.verificationStatus, selectedEvidence?.status, "reported"),
      evidenceStatus: evidenceStatus(run, selectedEvidence?.status || "reported"),
      evidenceLevel: first(run.evidenceLevel, run.evidence_level, selectedEvidence?.level, "reported"),
      comparability: first(run.comparability, run.comparable, "conditional"),
      status: first(run.status, run.verificationStatus, run.verification_status, selectedEvidence?.status, "reported"),
      sourceId: first(run.sourceId, run.source_id, typeof run.source === "string" ? run.source : null,
        ...(list(run.sourceIds || run.source_ids)), selectedEvidence?.sourceId),
      sourceUrl: first(run.sourceUrl, run.source_url, run.url, selectedEvidence?.sourceUrl),
      sourceLabel: first(run.sourceLabel, run.source_label, run.sourceTitle, run.source_title, selectedEvidence?.sourceLabel),
      locator: first(run.locator, run.sourceLocator, run.source_locator, selectedEvidence?.locator),
      fetchedAt: first(run.fetchedAt, run.fetched_at, run.retrievedAt, run.retrieved_at, selectedEvidence?.fetchedAt),
      snapshotHash: first(run.snapshotHash, run.snapshot_hash, run.sha256, run.hash, selectedEvidence?.snapshotHash),
      publishedAt: first(run.publishedAt, run.published_at, selectedEvidence?.publishedAt),
      observedAt: first(run.observedAt, run.observed_at, run.date, selectedEvidence?.observedAt),
      evidenceItems: runEvidence,
      publicEvidence: runEvidence,
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

  function publicBenchmarkFromEvidence(item) {
    const id = text(first(item?.benchmarkId, item?.benchmark_id), "public-benchmark");
    const sourceName = text(first(item?.benchmarkName, item?.benchmark_name), id);
    const lower = id.toLowerCase();
    let family = "public / other";
    let familyLabel = "公开切片";
    if (lower.startsWith("livebench-")) { family = "coding / reasoning"; familyLabel = "LiveBench"; }
    else if (lower.startsWith("helm-")) { family = "general / knowledge"; familyLabel = "HELM"; }
    else if (lower.startsWith("arena-")) { family = lower.includes("agent") || lower.includes("web") || lower.includes("search") ? "agent / preference" : "preference"; familyLabel = "Arena"; }
    else if (lower.includes("aime") || lower.includes("math") || lower.includes("hmmt")) { family = "math / science"; familyLabel = "Math"; }
    else if (lower.includes("swe") || lower.includes("terminal") || lower.includes("code")) { family = "coding"; familyLabel = "Coding"; }
    const unitRaw = text(first(item?.unit, "%"), "%");
    const unit = unitRaw.toLowerCase() === "percent" || unitRaw.toLowerCase() === "percentage" ? "%" : unitRaw;
    const scale = unit === "%" ? 100 : (unit.toLowerCase() === "fraction" ? { min: 0, max: 1 } : null);
    const subjectType = text(first(item?.subjectType, item?.subject_type), "model");
    const aleNote = lower.includes("ale_bench") || lower.includes("ale-bench")
      ? "该来源切片的命名含 ale_bench；不等同于 SakanaAI ALE-Bench、Agents' Last Exam (ALE-V1) 或 Atari ALE。"
      : lower.includes("agents-last-exam")
        ? "这是 Agents' Last Exam (ALE-V1) 系统评测；不等同于 SakanaAI ALE-Bench 或 Atari ALE。"
        : "";
    return normaliseBenchmark({
      id,
      name: sourceName === id ? id.replace(/^(livebench|helm)-/i, "$1 · ").replace(/-/g, " ") : sourceName,
      short: sourceName === id ? id.replace(/^(livebench|helm)-/i, "").replace(/-/g, " ") : sourceName,
      family,
      familyLabel,
      metric: first(item?.metricId, item?.metric_id, "score"),
      metricLabel: first(item?.metricId, item?.metric_id, "score"),
      unit,
      ...(scale ? { scale } : {}),
      direction: "higher",
      version: first(item?.benchmarkVersionId, item?.benchmarkVersion, item?.benchmark_version),
      evaluationMode: subjectType.toLowerCase() === "system" ? "system" : "direct",
      publicOnly: true,
      // Dynamically observed source slices must not masquerade as curator-pinned
      // columns even if a future source row happens to carry UI-like metadata.
      displayPriority: null,
      sourceId: item?.sourceId,
      description: `来自公开榜单或模型卡的切片；本站未独立复现。${aleNote ? ` ${aleNote}` : ""}`,
    });
  }

  /*
   * Public tables often publish several columns for one benchmark (for
   * example ALE's pass rate and average partial-credit score, or HELM's
   * accuracy plus token/latency telemetry).  A model × benchmark cell cannot
   * safely hold all of those values.  Keep the raw evidence intact, but make
   * each meaningful metric a display slice with a stable id.  Telemetry is
   * still searchable in the evidence drawer, yet is deliberately excluded
   * from the score matrix so it cannot be mistaken for task performance.
   */
  const PUBLIC_TELEMETRY_METRICS = new Set([
    "eval", "train", "truncated", "prompt-tokens", "output-tokens", "input-tokens",
    "total-tokens", "observed-inference-time-s", "inference-time-s", "latency-ms",
    "runtime-seconds", "cost-usd", "num-samples", "sample-count", "n",
  ]);
  const PUBLIC_METRIC_LABELS = {
    accuracy: "准确率", acc: "准确率", score: "分数", mean_score: "平均分", "mean-score": "平均分",
    avg_score: "平均分", "avg-score": "平均分", pass_at_1: "Pass@1", "pass-at-1": "Pass@1",
    "pass@1": "Pass@1", pass_rate: "Pass rate", "pass-rate": "Pass rate", pass: "Pass",
    pass_k: "Pass^k", "pass-k": "Pass^k", elo: "Elo", arena_rating: "Arena rating",
    "arena-rating": "Arena rating", ips: "IPS", success: "Success", performance: "Performance",
    arena_score_bt: "Arena Score (Bradley–Terry)", "arena-score-bt": "Arena Score (Bradley–Terry)",
    rank: "Rank", em: "Exact match", f1: "F1", "cot-correct": "CoT correct",
  };
  function publicMetricKey(value) {
    return text(value, "score").trim().toLowerCase().replace(/[^a-z0-9@^]+/g, "-").replace(/^-+|-+$/g, "") || "score";
  }
  function publicMetricLabel(value) {
    const raw = text(value, "score").trim();
    const key = publicMetricKey(raw);
    return PUBLIC_METRIC_LABELS[key] || raw.replace(/_/g, " ") || "score";
  }
  function publicMetricIdentity(item, fallback = "score") {
    const sourceMetric = text(first(item?.metricId, item?.metric_id, item?.metric), fallback);
    const sourceId = text(first(item?.sourceId, item?.source_id), "").toLowerCase();
    const table = item?.protocol && typeof item.protocol === "object" ? text(item.protocol.table, "") : "";
    const tableKey = publicMetricKey(table);
    const sourceKey = publicMetricKey(sourceMetric);
    // Older snapshots from Arena's own HF dataset called the numeric field
    // `elo` even though the published methodology is Bradley–Terry. Preserve
    // that raw source spelling on the evidence row, but map it to the current
    // catalog metric so the headline column is not duplicated or left empty.
    if (sourceId === "lmarena-hf-dataset" && sourceKey === "elo") {
      return { sourceMetric, metricId: "arena_score_bt", label: "Arena Score (Bradley–Terry)" };
    }
    // Existing HELM snapshots call both Accuracy/Mean score and
    // Efficiency/Mean score simply `score`. Preserve that source metric, but
    // give the non-Accuracy display slice a stable table-qualified identity.
    if (sourceId.startsWith("helm-") && sourceKey === "score" && tableKey && tableKey !== "accuracy") {
      return { sourceMetric, metricId: `${tableKey}-score`, label: `${table} · ${publicMetricLabel(sourceMetric)}` };
    }
    if (sourceId.startsWith("helm-") && sourceKey.endsWith("-score") && tableKey && sourceKey.startsWith(`${tableKey}-`)) {
      return { sourceMetric, metricId: sourceKey, label: `${table} · score` };
    }
    return { sourceMetric, metricId: sourceMetric, label: publicMetricLabel(sourceMetric) };
  }
  function publicTelemetryMetric(value) {
    const key = publicMetricKey(value);
    return PUBLIC_TELEMETRY_METRICS.has(key)
      || key.startsWith("prompt-tokens") || key.startsWith("output-tokens")
      || key.startsWith("observed-inference-time") || key === "eval" || key === "train";
  }
  function publicMetricScale(item, base) {
    const unit = text(item?.unit, base?.unit || "").toLowerCase();
    if (["%", "percent", "percentage"].includes(unit)) return 100;
    if (unit === "fraction") return { min: 0, max: 1 };
    if (base?.scale && unit === text(base?.unit, "").toLowerCase()) return base.scale;
    return null;
  }
  function publicMetricDirection(metric, base, item = null) {
    const reported = item?.protocol && typeof item.protocol === "object" ? item.protocol.direction : null;
    if (["higher", "lower"].includes(String(reported || "").toLowerCase())) return String(reported).toLowerCase();
    const key = publicMetricKey(metric);
    if (key === "rank" || key.endsWith("-rank") || key.includes("latency") || key.includes("time")) return "lower";
    return text(base?.direction, "higher");
  }
  function addPublicMetricSlices(benchmarks, publicEvidence) {
    const byId = new Map(benchmarks.map((benchmark) => [String(benchmark.id), benchmark]));
    const slices = [];
    const meaningfulBaseIds = new Set();
    publicEvidence.forEach((item) => {
      const baseId = text(first(item?.benchmarkId, item?.benchmark_id), "public-benchmark");
      let base = byId.get(baseId);
      if (!base) {
        if (publicTelemetryMetric(item?.metricId || item?.metric)) {
          item.matrixExcluded = true;
          item.matrixExcludedReason = "telemetry_metric";
          return;
        }
        base = publicBenchmarkFromEvidence(item);
        byId.set(baseId, base);
        slices.push(base);
      }
      const metricIdentity = publicMetricIdentity(item, base.metric || "score");
      const rawMetric = metricIdentity.metricId;
      item.sourceMetricId = first(item.sourceMetricId, item.source_metric_id, metricIdentity.sourceMetric);
      item.displayMetricId = rawMetric;
      if (publicTelemetryMetric(rawMetric)) {
        item.matrixExcluded = true;
        item.matrixExcludedReason = "telemetry_metric";
        return;
      }
      meaningfulBaseIds.add(baseId);
      base.publicReported = true;
      const metricKey = publicMetricKey(rawMetric);
      // A catalog benchmark may define several metrics (ALE's pass rate and
      // partial-credit average are the important example).  Only its declared
      // default metric occupies the base column; every other meaningful metric
      // gets an explicit display slice so values are never overwritten or
      // silently compared under the wrong label.
      const defaultMetric = first(base.defaultMetricId, base.default_metric_id, base.metric,
        base.metrics?.[0]?.id, base.metrics?.[0]?.metric, base.metrics?.[0]?.name, "score");
      const isPrimary = metricKey === publicMetricKey(defaultMetric);
      let displayId = base.id;
      if (!isPrimary) {
        displayId = `${base.id}--${slug(metricKey)}`;
        let slice = byId.get(displayId);
        if (!slice) {
          const label = metricIdentity.label;
          slice = normaliseBenchmark({
            ...base,
            id: displayId,
            canonicalId: displayId,
            short: `${base.short || base.name} · ${label}`,
            name: `${base.name || base.id} · ${rawMetric}`,
            metric: rawMetric,
            metricLabel: label,
            unit: first(item?.unit, base.unit, "unknown"),
            scale: publicMetricScale(item, base),
            direction: publicMetricDirection(rawMetric, base, item),
            publicOnly: true,
            publicMetricSlice: true,
            // Do not inherit the base benchmark's curated position. Secondary
            // metrics stay inspectable but follow canonical/base columns.
            displayPriority: null,
            baseBenchmarkId: base.id,
            description: `公开 ${rawMetric} 指标切片；本站未独立复现。`,
          });
          byId.set(displayId, slice);
          slices.push(slice);
        }
        item.metricSliceLabel = metricIdentity.label;
        item.metricSlice = true;
      } else if (base.publicOnly) {
        base.metric = rawMetric;
        base.metricLabel = metricIdentity.label;
      }
      item.displayBenchmarkId = displayId;
      item.baseBenchmarkId = base.id;
      item.matrixExcluded = false;
    });
    // `meaningfulBaseIds` is intentionally computed even when a source only
    // contains telemetry; retain canonical empty columns but remove a
    // dynamically-created telemetry-only definition.
    return benchmarks.filter((benchmark) => !benchmark.publicOnly || meaningfulBaseIds.has(String(benchmark.id))).concat(slices.filter((benchmark) => !benchmarks.includes(benchmark)));
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
    let runs = rawRuns.length ? rawRuns : deriveRuns(models, benchmarks);
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
    runs.forEach((run) => applySubjectSemantics(
      run,
      benchmarks.find((benchmark) => benchmark.id === run.benchmarkId),
      harnesses.find((harness) => harness.id === run.harnessId),
    ));
    /*
     * Public leaderboard rows are useful context even when they have not
     * passed our own review.  Map only exact canonical ids/names/aliases;
     * unmatched rows stay in `unmappedEvidence` for inspection and are never
     * turned into a fabricated model row.
     */
    const rawPublicEvidence = ["publicEvidence", "public_evidence", "evidenceRecords", "evidence_records"]
      .filter((key) => source[key] !== undefined && source[key] !== null)
      .map((key) => source[key]);
    const flattenedPublicEvidence = [];
    rawPublicEvidence.forEach((item) => flattenEvidence(item, {}, flattenedPublicEvidence));
    const publicEvidence = flattenedPublicEvidence
      .map((item) => ({ ...normaliseEvidence(item), public: true, evidenceOrigin: "public" }))
      .filter((item) => item.value !== null || item.sourceUrl || item.sourceId || item.locator || item.status);
    publicEvidence.forEach((item) => applySubjectSemantics(
      item,
      benchmarks.find((benchmark) => benchmark.id === item.benchmarkId),
      harnesses.find((harness) => harness.id === first(item.harnessId, item.harness)),
    ));
    // Public adapters may expose a benchmark slice before it has a canonical
    // registry row (for example each LiveBench or HELM sub-suite). Add a
    // display-only definition rather than dropping those cells or implying
    // that two differently evaluated suites are identical.
    const benchmarkIds = new Set(benchmarks.map((benchmark) => benchmark.id));
    publicEvidence.forEach((item) => {
      const id = first(item.benchmarkId, item.benchmark_id);
      if (id && !benchmarkIds.has(String(id)) && !publicTelemetryMetric(item.metricId || item.metric)) {
        const benchmark = publicBenchmarkFromEvidence(item);
        benchmarks.push(benchmark);
        benchmarkIds.add(benchmark.id);
      }
    });
    // Keep distinct public metrics as explicit matrix columns and hide
    // non-performance telemetry from the matrix while retaining it below in
    // the full public evidence list.
    const publicBenchmarks = addPublicMetricSlices(benchmarks, publicEvidence);
    benchmarks.splice(0, benchmarks.length, ...publicBenchmarks);
    publicEvidence.forEach((item) => applySubjectSemantics(
      item,
      benchmarks.find((benchmark) => benchmark.id === first(item.displayBenchmarkId, item.benchmarkId)),
      harnesses.find((harness) => harness.id === first(item.harnessId, item.harness)),
    ));
    const modelLookup = new Map();
    const benchmarkLookup = new Map();
    const addLookup = (map, value, object) => {
      if (value === undefined || value === null || value === "") return;
      map.set(String(value).trim().toLowerCase(), object);
    };
    merged.forEach((model) => {
      [model.id, model.name, ...(model.aliases || [])].forEach((value) => addLookup(modelLookup, value, model));
    });
    benchmarks.forEach((benchmark) => {
      [benchmark.id, benchmark.name, benchmark.short].forEach((value) => addLookup(benchmarkLookup, value, benchmark));
    });
    const unmappedEvidence = [];
    publicEvidence.forEach((evidence) => {
      // Telemetry (tokens, latency, cost, eval/train counters) remains in the
      // public evidence list for inspection, but must never populate a score
      // cell.  `addPublicMetricSlices` marks these rows before this mapping
      // pass; skipping here prevents a telemetry value from overwriting the
      // benchmark's actual performance metric.
      if (evidence.matrixExcluded) return;
      const modelKey = first(evidence.canonicalModelId, evidence.canonical_model_id, evidence.modelId, evidence.model_id, evidence.modelRef, evidence.model_ref);
      const benchmarkKey = first(evidence.displayBenchmarkId, evidence.benchmarkId, evidence.benchmark_id);
      const model = modelLookup.get(String(modelKey || "").trim().toLowerCase());
      const benchmark = benchmarkLookup.get(String(benchmarkKey || "").trim().toLowerCase());
      if (!model || !benchmark) {
        unmappedEvidence.push(evidence);
        return;
      }
      const mapped = { ...evidence, modelId: model.id, benchmarkId: benchmark.id, displayBenchmarkId: benchmark.id, public: true, evidenceOrigin: "public" };
      model.scores[benchmark.id] = mergeScoreEntries(model.scores[benchmark.id], normaliseScore(mapped));
      evidence.mappedModelId = model.id;
      evidence.mappedBenchmarkId = benchmark.id;
      // Preserve the public builder's exact/curated/heuristic alias class so
      // the UI can distinguish identity confidence from reproduction status.
      // Only rows without a builder classification receive the generic label.
      evidence.mappingStatus = first(evidence.mappingStatus, evidence.mapping_status, "mapped");
      evidence.mappingResolved = true;
    });
    // Keep agent/tool/environment measurements in System Runs as well. The
    // atlas may use a system value only when no model-only value exists; the
    // explicit system badge prevents that coverage fallback being mistaken
    // for a bare-model score.
    const publicRuns = [];
    publicEvidence.forEach((evidence, index) => {
      if (evidence.value === null || evidence.value === undefined) return;
      const mappedModel = merged.find((item) => item.id === first(evidence.mappedModelId, evidence.canonicalModelId, evidence.modelId, evidence.modelRef));
      if (evidence.matrixExcluded) return;
      const benchmark = benchmarks.find((item) => item.id === first(evidence.mappedBenchmarkId, evidence.displayBenchmarkId, evidence.benchmarkId));
      const subject = String(first(evidence.subjectType, evidence.subject_type, benchmark?.evaluationMode, "model")).toLowerCase();
      if (!mappedModel || subject !== "system") return;
      publicRuns.push(normaliseRun({
        ...evidence,
        id: `public-${evidence.id || index + 1}`,
        modelId: mappedModel.id,
        modelName: mappedModel.name,
        benchmarkId: benchmark.id,
        benchmarkVersion: evidence.benchmarkVersion || evidence.benchmarkVersionId || benchmark.version,
        metric: evidence.metricId || benchmark.metric,
        value: evidence.value,
        unit: evidence.unit || benchmark.unit,
        status: "reported",
        evidenceStatus: "reported",
        evidenceLevel: evidence.evidenceLevel || "D",
        public: true,
        evidenceOrigin: "public",
        evidenceItems: [evidence],
      }, index));
    });
    const runIds = new Set(runs.map((run) => run.id));
    runs = runs.concat(publicRuns.filter((run) => !runIds.has(run.id)));
    const harnessIds = new Set(harnesses.map((harness) => harness.id));
    publicEvidence.forEach((item) => {
      const id = first(item.harnessId, item.harness_id, item.harness);
      if (id && !harnessIds.has(String(id))) {
        harnesses.push(normaliseHarness({
          id: String(id),
          name: item.harness || id,
          publicOnly: true,
          description: "公开来源标注的 harness；本站未独立复现。",
        }));
        harnessIds.add(String(id));
      }
    });
    const presets = list(source.presets).map(normalisePreset);
    if (publicEvidence.length && !presets.some((preset) => preset.id === "public-coverage")) {
      presets.unshift(normalisePreset({
        id: "public-coverage",
        label: "公开覆盖 / 全量切片",
        description: "展示目录与公开榜单已报告的全部 benchmark 切片；每个披露值均标记为本站未复现。",
        model_filter: { status: ["active", "preview", "restricted", "previous"] },
        mode: "atlas",
      }));
    }
    return {
      ...source,
      meta: source.meta || {},
      benchmarks,
      models: merged,
      catalogModels,
      harnesses,
      runs,
      presets,
      sources: list(source.sources),
      publicEvidence,
      unmappedEvidence,
    };
  }

  const sourceFor = (idOrSource) => {
    if (!idOrSource) return null;
    if (typeof idOrSource === "object") return idOrSource;
    const match = (state.data?.sources || []).find((source) => source.id === idOrSource || source.url === idOrSource);
    const external = safeUrl(idOrSource);
    return match || (external ? { id: external, url: external, label: external } : null);
  };
  const sourceContextUrl = (source) => firstSafeUrl(source?.web_url, source?.page_url, source?.homepage, source?.website, source?.url);
  const benchmarkFor = (id) => (state.data?.benchmarks || []).find((benchmark) => benchmark.id === id);
  const harnessFor = (id) => (state.data?.harnesses || []).find((harness) => harness.id === id);
  const modelById = (id) => (state.data?.models || []).find((model) => model.id === id);
  const runById = (id) => (state.data?.runs || []).find((run) => run.id === id);

  function isSystemSubject(value) {
    return ["system", "agent", "harness", "agent-system", "agentic"].includes(String(value || "").trim().toLowerCase());
  }
  function isSystemHarness(harness, harnessId = null) {
    const kind = String(first(harness?.kind, harness?.type, "") || "").toLowerCase();
    if (["model", "static-eval", "provider", "preference-eval", "unknown"].includes(kind)) return false;
    if (["agent", "terminal", "computer-use", "tool-use"].some((token) => kind.includes(token))) return true;
    const id = String(first(harnessId, harness?.id, "") || "").toLowerCase();
    if (["", "model-only", "lm-eval", "helm", "vendor-default", "unspecified-reported"].includes(id)) return false;
    return ["agent", "codex", "claude-code", "terminus"].some((token) => id.includes(token));
  }
  function resolvedSubjectType(sourceSubject, benchmark, harness, harnessId = null) {
    const benchmarkMode = first(benchmark?.evaluationMode, benchmark?.evaluation_mode, benchmark?.subjectType, benchmark?.subject_type);
    if (isSystemSubject(sourceSubject) || isSystemSubject(benchmarkMode) || isSystemHarness(harness, harnessId)) return "system";
    return String(sourceSubject || "model").trim().toLowerCase() || "model";
  }
  function applySubjectSemantics(record, benchmark, harness) {
    if (!record) return record;
    const sourceSubject = first(record.sourceSubjectType, record.source_subject_type, record.subjectType, record.subject_type);
    if (!record.sourceSubjectType && sourceSubject) record.sourceSubjectType = String(sourceSubject).toLowerCase();
    record.subjectType = resolvedSubjectType(sourceSubject, benchmark, harness, first(record.harnessId, record.harness_id, record.harness));
    return record;
  }
  function runIsSystem(run) {
    if (!run) return false;
    return resolvedSubjectType(
      first(run.sourceSubjectType, run.source_subject_type, run.subjectType, run.subject_type),
      benchmarkFor(run.benchmarkId),
      harnessFor(run.harnessId),
      first(run.harnessId, run.harness_id, run.harness),
    ) === "system";
  }

  /*
   * A public source can report both a model-only score and a harness/system
   * score for the same model × benchmark pair. Keep all evidence in the
   * cell, but prefer a model-only observation for Model Atlas; only fall back
   * to a system observation when no model-only value exists. The fallback
   * remains visibly marked `system` and is also available in System Runs.
   */
  function atlasScoreEntry(rawDirect) {
    const direct = normaliseScore(rawDirect);
    const items = evidenceItems(direct);
    if (!items.length) return direct;
    const parentSystem = isSystemSubject(first(direct.subjectType, direct.subject_type));
    const modelItems = parentSystem ? [] : items.filter((item) => !isSystemSubject(first(item.subjectType, item.subject_type)));
    const pool = modelItems.length ? modelItems : items;
    const selected = chooseEvidence(pool);
    if (!selected) return direct;
    const entry = normaliseScore({ ...direct, ...selected, evidenceItems: items, publicEvidence: items });
    entry.evidenceItems = items;
    entry.publicEvidence = items;
    if (isSystemSubject(first(selected.subjectType, selected.subject_type)) || (parentSystem && !modelItems.length)) {
      entry.subjectType = "system";
    }
    return entry;
  }

  function scoreEntry(model, benchmarkId) {
    const candidates = (state.data?.runs || []).filter((run) => run.modelId === model?.id && run.benchmarkId === benchmarkId && run.value !== null && run.value !== undefined);
    const isModelRun = (run) => !runIsSystem(run);
    const systemRuns = candidates.filter((run) => !isModelRun(run));
    const direct = model?.scores?.[benchmarkId];
    if (direct) {
      const entry = atlasScoreEntry(direct);
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
    const filtered = (state.data?.benchmarks || []).filter((benchmark) => {
      if (!presetAllowsBenchmark(benchmark)) return false;
      if (state.mode === "runs" && state.runBenchmark !== "all" && benchmark.id !== state.runBenchmark) return false;
      return true;
    });
    if (state.mode !== "atlas") return filtered;

    // Matrix order is a reading aid, not a ranking of benchmark quality. A
    // curator can pin the intended left-to-right order with displayPriority
    // (smaller first). Otherwise put featured and empirically populated
    // columns first, then retain canonical source order as the stable tie-break.
    const models = allModels();
    const directCoverage = new Map(filtered.map((benchmark) => {
      const count = models.reduce((sum, model) => {
        const entry = model?.scores?.[benchmark.id];
        const value = entry && typeof entry === "object" ? first(entry.value, entry.score, entry.result) : entry;
        return sum + (value !== null && value !== undefined && value !== "" ? 1 : 0);
      }, 0);
      return [benchmark.id, count];
    }));
    return filtered.map((benchmark, sourceOrder) => ({ benchmark, sourceOrder })).sort((left, right) => {
      const leftPriority = Number(first(left.benchmark.displayPriority, left.benchmark.display_priority));
      const rightPriority = Number(first(right.benchmark.displayPriority, right.benchmark.display_priority));
      const leftPinned = Number.isFinite(leftPriority);
      const rightPinned = Number.isFinite(rightPriority);
      if (leftPinned !== rightPinned) return leftPinned ? -1 : 1;
      if (leftPinned && leftPriority !== rightPriority) return leftPriority - rightPriority;
      if (Boolean(left.benchmark.publicMetricSlice) !== Boolean(right.benchmark.publicMetricSlice)) return left.benchmark.publicMetricSlice ? 1 : -1;
      if (Boolean(left.benchmark.featured) !== Boolean(right.benchmark.featured)) return left.benchmark.featured ? -1 : 1;
      const coverageDifference = (directCoverage.get(right.benchmark.id) || 0) - (directCoverage.get(left.benchmark.id) || 0);
      return coverageDifference || left.sourceOrder - right.sourceOrder;
    }).map(({ benchmark }) => benchmark);
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
      // The public-coverage atlas is explicitly a coverage map: keep every
      // current/previous catalog release visible even when it has no canonical
      // score yet.  Narrow presets retain the quieter catalog-only behavior.
      const publicCoveragePreset = state.preset === "public-coverage";
      const hiddenCatalog = !state.showCatalog && !publicCoveragePreset && model.catalogOnly && !currentStatus;
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
      if (!runIsSystem(run)) return false;
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
    const unit = String(benchmark?.unit || "").toLowerCase();
    if (unit && !["%", "percent", "percentage", "fraction"].includes(unit) && benchmark?.publicOnly) return "score-neutral";
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
    const selected = chooseEvidence(evidenceItems(entry));
    const publicEvidence = Boolean(entry?.public || entry?.evidenceOrigin === "public" || selected?.public || selected?.evidenceOrigin === "public");
    const status = evidenceStatus(entry, selected?.status || "reported");
    if (publicEvidence && status === "candidate") return "榜单候选 · 未复现";
    if (publicEvidence) return "榜单披露 · 未复现";
    if (status === "approved" || status === "verified" || status === "reproduced") return "已核验";
    if (status === "reported" || status === "official" || status === "published") return "官方披露 · 未复现";
    if (status === "candidate") return "候选 · 未复现";
    if (status === "conditional") return "条件性";
    if (status === "demo" || status === "illustrative") return "示例数据";
    return status;
  }
  function statusClass(entry) {
    if (!entry || entry.value === null || entry.value === undefined || entry.value === "") return "missing";
    const selected = chooseEvidence(evidenceItems(entry));
    const publicEvidence = Boolean(entry?.public || entry?.evidenceOrigin === "public" || selected?.public || selected?.evidenceOrigin === "public");
    if (publicEvidence) return "conditional";
    const status = evidenceStatus(entry, selected?.status || "reported");
    if (status === "approved" || ["reported", "official", "verified", "reproduced", "published"].includes(status)) return status === "approved" ? "approved" : "reported";
    if (status === "candidate") return "conditional";
    if (status === "conditional") return "conditional";
    if (status === "demo" || status === "illustrative") return "demo";
    return "conditional";
  }
  function isPublicEvidence(entry) {
    const selected = chooseEvidence(evidenceItems(entry));
    return Boolean(entry?.public || entry?.evidenceOrigin === "public" || selected?.public || selected?.evidenceOrigin === "public");
  }
  function mappingStatusLabel(status) {
    const value = String(status || "").trim().toLowerCase();
    return ({
      exact_alias: "exact alias",
      curated_alias: "curated alias",
      heuristic_alias: "heuristic alias",
      mapped: "mapped",
      unmatched: "unmapped",
    })[value] || (value || "mapping 未注明");
  }
  function evidenceBadge(entry, compact = false) {
    if (!entry || entry.value === null || entry.value === undefined || entry.value === "") return "";
    const items = evidenceItems(entry);
    const selected = chooseEvidence(items);
    if (!selected && !entry?.evidenceStatus && !entry?.status) return "";
    const status = evidenceStatus(entry, selected?.status || "reported");
    const publicEvidence = isPublicEvidence(entry);
    const system = String(first(entry?.subjectType, entry?.subject_type, selected?.subjectType, "")).toLowerCase() === "system";
    const mapping = first(entry?.mappingStatus, entry?.mapping_status, selected?.mappingStatus, selected?.mapping_status);
    const label = publicEvidence
      ? (status === "candidate" ? "候选 · 未复现" : "披露 · 未复现")
      : (status === "approved" ? "approved" : (status === "candidate" ? "candidate · 未复现" : "官方披露 · 未复现"));
    const count = items.length > 1 ? ` +${items.length - 1}` : "";
    const systemMark = system ? " · system" : "";
    const mappingHint = mapping ? `；身份映射：${mappingStatusLabel(mapping)}` : "";
    return `<span class="score-evidence evidence-${slug(status)}${publicEvidence ? " evidence-public" : ""}${system ? " evidence-system" : ""}" title="${esc((status === "approved" ? `${items.length || 1} 条已核验证据` : "来源披露数字，本项目尚未独立复现") + mappingHint)}">${esc(label)}${compact ? "" : count}${esc(systemMark)}</span>`;
  }
  function evidenceWeight(entry) {
    const tier = String(first(entry?.evidenceLevel, entry?.evidence_level, chooseEvidence(evidenceItems(entry))?.level, "")).toUpperCase();
    const tierWeight = { A: 1, B: 0.85, C: 0.65, D: 0.4 }[tier];
    const status = evidenceStatus(entry, chooseEvidence(evidenceItems(entry))?.status || "reported");
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
      const systemHarnessIds = new Set((state.data?.runs || []).filter(runIsSystem).map((run) => run.harnessId).filter(Boolean));
      const harnesses = (state.data?.harnesses || []).filter((harness) => systemHarnessIds.has(harness.id));
      els.harnessFilter.innerHTML = '<option value="all">所有 harness</option>' + harnesses.map((harness) => `<option value="${esc(harness.id)}">${esc(harness.name)}${harness.version ? ` · ${esc(harness.version)}` : ""}</option>`).join("");
      els.harnessFilter.value = state.harness === "all" || systemHarnessIds.has(state.harness) ? state.harness : "all";
    }
    if (els.runBenchmarkFilter) {
      const systemBenchmarkIds = new Set((state.data?.runs || []).filter(runIsSystem).map((run) => run.benchmarkId));
      const runBenchmarks = (state.data?.benchmarks || []).filter((benchmark) => systemBenchmarkIds.has(benchmark.id));
      els.runBenchmarkFilter.innerHTML = '<option value="all">所有 benchmark</option>' + runBenchmarks.map((benchmark) => `<option value="${esc(benchmark.id)}">${esc(benchmark.short || benchmark.name)}</option>`).join("");
      els.runBenchmarkFilter.value = state.runBenchmark === "all" || systemBenchmarkIds.has(state.runBenchmark) ? state.runBenchmark : "all";
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
    const notes = mode === "runs" ? ["参与当前筛选的模型", "当前运行记录覆盖的 benchmark", "有 protocol 的系统记录", "运行记录非缺失率"] : ["当前目录中的 model / config entry", "跨能力面的 benchmark", "canonical + 公开披露值", "矩阵非缺失率"];
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
    if (els.asOfLabel) {
      const snapshotDates = [state.data?.publicMeta?.generatedAt, state.data?.meta?.asOf, state.data?.meta?.lastUpdated]
        .filter(Boolean).map((value) => String(value).slice(0, 10)).sort();
      els.asOfLabel.textContent = snapshotDates.at(-1) || "—";
    }
    if (els.cadenceLabel) els.cadenceLabel.textContent = state.data?.meta?.updateCadence || state.data?.meta?.update_cadence || "—";
    if (els.coverageNote) {
      const stats = state.data?.stats || {};
      const publicStats = state.data?.publicStats || {};
      const unmappedGroups = (state.data?.publicUnmappedModels || []).length;
      const mappedCells = publicStats.mappedCells || 0;
      const publicMetricCells = publicStats.mappedMetricCells || 0;
      const publicRows = Array.isArray(state.data?.publicEvidence) ? state.data.publicEvidence : [];
      const telemetryCells = new Set(publicRows
        .filter((item) => item.matrixExcluded)
        .map((item) => [item.canonicalModelId || item.modelRef || "", item.displayBenchmarkId || item.benchmarkId || "", item.metricId || ""].join("|"))
        .filter((key) => key !== "||"));
      const performanceMetricCells = Math.max(0, publicMetricCells - telemetryCells.size);
      const metricNote = telemetryCells.size
        ? `${fmt(publicMetricCells, 0)} 个含 metric 单元（其中 ${fmt(telemetryCells.size, 0)} 个 telemetry 仅证据；实际 performance ${fmt(performanceMetricCells, 0)}）`
        : `${fmt(publicMetricCells, 0)} 个含 metric 单元`;
      const publicHint = publicStats.rows
        ? `；公开层已载入 ${fmt(publicStats.rows, 0)} 条已映射披露（${fmt(mappedCells, 0)} 个 model × benchmark 单元、${metricNote}；原始去重 ${fmt(publicStats.deduplicatedRows || 0, 0)} 条；${fmt(publicStats.unmappedRows || 0, 0)} 条未安全归一化，${fmt(unmappedGroups, 0)} 个来源原名见 aliases）`
        : "；公开榜单候选由日常维护任务另行审阅";
      const canonicalHint = stats.observedCells !== undefined ? `；canonical 已整理 ${fmt(stats.observedCells, 0)} 个单元格` : "";
      els.coverageNote.innerHTML = `矩阵数值包含公开来源报告值；“披露 · 未复现”不代表本站复现，空白也不代表没人测试${canonicalHint}${publicHint}。<a href="docs/benchmark-coverage.md">查看覆盖审计 ↗</a>`;
    }
    const status = String(state.data?.meta?.status || "curated").toLowerCase();
    const isDemo = ["demo", "illustrative", "seed"].includes(status);
    if (els.freshnessPill) els.freshnessPill.innerHTML = `<span class="status-dot"></span><span>${isDemo ? "seed snapshot" : (state.data?.publicStats?.rows ? "public + curated" : "curated snapshot")}</span>`;
    if (els.footerStatus) els.footerStatus.textContent = isDemo ? "Seed data: replace or verify before citing." : `${state.data?.runs?.length || 0} system runs · public reports are marked not reproduced.`;
  }

  function syncMatrixDensity() {
    const density = state.matrixDensity === "standard" ? "standard" : "compact";
    state.matrixDensity = density;
    if (els.matrixView) els.matrixView.dataset.density = density;
    document.querySelectorAll("[data-matrix-density]").forEach((button) => {
      const active = button.dataset.matrixDensity === density;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderMatrixNavigation(benchmarks) {
    syncMatrixDensity();
    if (els.matrixNavigationStatus) {
      const pinned = benchmarks.filter((benchmark) => Number.isFinite(Number(first(benchmark.displayPriority, benchmark.display_priority)))).length;
      els.matrixNavigationStatus.textContent = `${fmt(benchmarks.length, 0)} 个 benchmark · ${pinned ? `${fmt(pinned, 0)} 个策展置顶，其余` : ""}热门与高覆盖优先`;
    }
    if (!els.benchmarkJump) return;
    const current = benchmarks.some((benchmark) => benchmark.id === state.matrixBenchmarkJump) ? state.matrixBenchmarkJump : "";
    els.benchmarkJump.innerHTML = '<option value="">定位 benchmark…</option>' + benchmarks.map((benchmark, index) => `<option value="${esc(benchmark.id)}">${fmt(index + 1, 0)} · ${esc(benchmark.short || benchmark.name)}</option>`).join("");
    els.benchmarkJump.value = current;
  }

  function scrollMatrixToBenchmark(benchmarkId) {
    if (!benchmarkId || !els.matrixScroll || !els.matrixHead?.querySelectorAll) return;
    const headers = [...els.matrixHead.querySelectorAll("[data-benchmark-col]")];
    const target = headers.find((header) => header.dataset.benchmarkCol === benchmarkId);
    if (!target) return;
    const stickyWidth = els.matrixBody?.querySelector?.(".model-cell")?.offsetWidth || 0;
    const left = Math.max(0, Number(target.offsetLeft || 0) - stickyWidth - 12);
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (typeof els.matrixScroll.scrollTo === "function") els.matrixScroll.scrollTo({ left, behavior: reducedMotion ? "auto" : "smooth" });
    else els.matrixScroll.scrollLeft = left;
  }

  function renderMatrix() {
    const benchmarks = filteredBenchmarks();
    const models = filteredModels();
    renderMatrixNavigation(benchmarks);
    if (els.matrixHead) els.matrixHead.innerHTML = `<tr><th scope="col">MODEL / RELEASE</th>${benchmarks.map((benchmark) => `<th scope="col" data-benchmark-col="${esc(benchmark.id)}"><span class="bench-head"><strong>${esc(benchmark.short || benchmark.name)}</strong><small>${esc(benchmark.metricLabel || benchmark.metric || "score")}${benchmark.evaluationMode === "system" ? " · system" : ""}${benchmark.publicOnly || benchmark.publicReported ? " · public" : ""}</small></span></th>`).join("")}</tr>`;
    if (els.matrixBody) els.matrixBody.innerHTML = models.map((model) => {
      const cells = benchmarks.map((benchmark) => {
        const entry = scoreEntry(model, benchmark.id);
        const missing = entry.value === null || entry.value === undefined;
        const selectedEvidence = chooseEvidence(evidenceItems(entry));
        const source = sourceFor(first(entry.sourceId, entry.sourceUrl, selectedEvidence?.sourceId, selectedEvidence?.sourceUrl));
        const sourceMark = source ? '<span class="source-chip">S</span>' : "";
        const runHint = missing && entry.systemRunCount ? `<span class="score-run-hint">↗ ${entry.systemRunCount} run${entry.systemRunCount === 1 ? "" : "s"}</span>` : "";
        const evidenceMarkup = evidenceBadge(entry);
        const ariaEvidence = !missing && evidenceMarkup ? `；${statusLabel(entry)}` : "";
        const mapping = first(entry.mappingStatus, entry.mapping_status, selectedEvidence?.mappingStatus, selectedEvidence?.mapping_status);
        const mappingHint = mapping ? `；身份映射：${mappingStatusLabel(mapping)}` : "";
        return `<td class="score-cell ${scoreClass(entry, benchmark)}" data-model="${esc(model.id)}" data-benchmark="${esc(benchmark.id)}"${mapping ? ` data-mapping-status="${esc(mapping)}"` : ""} title="${esc(mappingHint ? mappingHint.slice(1) : "点击查看版本、协议与来源")}" tabindex="0" role="button" aria-label="${esc(model.name)} ${esc(benchmark.name)} ${missing ? (entry.systemRunCount ? `${entry.systemRunCount} system runs；切换 System Runs` : "未报告") : fmt(entry.value) + (benchmark.unit || "") + ariaEvidence + mappingHint}"><span class="score-value">${missing ? "—" : fmt(entry.value)}${!missing && benchmark.unit ? `<small>${esc(benchmark.unit)}</small>` : ""}${sourceMark}</span>${evidenceMarkup}${runHint}<span class="score-setting">${esc(display(entry.setting, "未说明"))}</span></td>`;
      }).join("");
      return `<tr><td class="model-cell" data-model="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)}">${modelMarkup(model)}</td>${cells}</tr>`;
    }).join("");
    if (els.emptyState) els.emptyState.hidden = models.length !== 0;
  }

  function renderPublicEvidence() {
    const recordMap = new Map();
    [...(state.data?.publicEvidence || []), ...(state.data?.unmappedEvidence || [])].forEach((item, index) => {
      recordMap.set(item?.id || `public-${index}`, item);
    });
    const records = [...recordMap.values()];
    if (!els.publicEvidenceSection || !els.publicEvidenceList) return;
    const query = state.search.trim().toLowerCase();
    const filtered = records.filter((item) => {
      if (!query) return true;
      return [item.modelName, item.modelRef, item.canonicalModelId, item.benchmarkName, item.benchmarkId,
        item.metricId, item.sourceLabel, item.sourceId, item.harness, item.harnessId, display(item.protocol)].filter(Boolean).join(" ").toLowerCase().includes(query);
    });
    els.publicEvidenceSection.hidden = state.mode !== "atlas" || records.length === 0;
    els.publicEvidenceSection.classList.toggle("expanded", state.publicEvidenceExpanded);
    if (els.publicEvidenceToggle) {
      els.publicEvidenceToggle.setAttribute("aria-expanded", String(state.publicEvidenceExpanded));
      const icon = els.publicEvidenceToggle.querySelector?.(".public-evidence-toggle-icon");
      const label = els.publicEvidenceToggle.querySelector?.(".public-evidence-toggle-label");
      if (icon) icon.textContent = state.publicEvidenceExpanded ? "−" : "＋";
      if (label) label.textContent = state.publicEvidenceExpanded ? "收起审计详情" : "展开审计详情";
    }
    if (els.publicEvidenceBody) els.publicEvidenceBody.hidden = !state.publicEvidenceExpanded;
    if (els.publicEvidenceCount) {
      const stats = state.data?.publicStats || {};
      const mapped = stats.rows || records.length;
      const unmapped = stats.unmappedRows || 0;
      const mappedCells = stats.mappedCells || 0;
      const sources = stats.sources || Object.keys(stats.sourceCounts || {}).length;
      const filterPrefix = query ? `${fmt(filtered.length, 0)} / ` : "";
      els.publicEvidenceCount.textContent = `${filterPrefix}${fmt(mapped, 0)} 条披露 · ${fmt(sources, 0)} 个来源 · ${fmt(mappedCells, 0)} 个单元 · ${fmt(unmapped, 0)} 条待归一化`;
    }
    // The evidence ledger is an audit surface, not primary page content. Keep
    // the collapsed state truly light by releasing its representative rows
    // and alias cards instead of merely hiding a large pre-rendered DOM.
    if (!state.publicEvidenceExpanded) {
      els.publicEvidenceList.innerHTML = "";
      if (els.publicAliasLedger) { els.publicAliasLedger.innerHTML = ""; els.publicAliasLedger.hidden = true; }
      return;
    }
    const visible = filtered.slice(0, 60);
    els.publicEvidenceList.innerHTML = visible.map((item) => {
      const source = sourceFor(first(item.sourceId, item.sourceUrl));
      const status = evidenceStatus(item, "reported");
      const sourceName = first(item.sourceModel, item.modelName, item.modelRef, item.modelId, "unmapped model");
      const benchmarkName = first(item.sourceBenchmark, item.benchmarkName, item.benchmarkId, "unmapped benchmark");
      const score = item.value === null || item.value === undefined ? "—" : fmt(item.value);
      const protocol = display(item.protocol, "protocol 未注明");
      const sourceLink = firstSafeUrl(item.evidenceUrl, item.sourceUrl, source?.url);
      const mapped = item.mappedModelId || item.canonicalModelId;
      const mappingStatus = first(item.mappingStatus, item.mapping_status, mapped ? "mapped" : "unmatched");
      const mappingClass = slug(mappingStatus);
      const subject = String(first(item.subjectType, "model")).toLowerCase() === "system" ? "system" : "model";
      const metric = item.metricSliceLabel || item.metricId || "score";
      const matrixNote = item.matrixExcluded ? "telemetry · 仅证据" : (item.metricSlice ? `matrix · ${metric}` : "matrix");
      return `<article class="public-evidence-row" data-public-evidence="${esc(item.id || "")}" tabindex="0" role="button" aria-label="查看 ${esc(sourceName)} 的公开 ${esc(benchmarkName)} 证据"><div class="public-evidence-main"><div class="public-evidence-title"><strong>${esc(sourceName)}</strong><span>×</span><strong>${esc(benchmarkName)}</strong></div><div class="public-evidence-meta"><span class="score-evidence evidence-${slug(status)} evidence-public${subject === "system" ? " evidence-system" : ""}">${esc(status === "candidate" ? "候选 · 未复现" : "披露 · 未复现")}</span><span class="model-badge mapping-badge mapping-${mappingClass}">${esc(mappingStatusLabel(mappingStatus))}</span><span class="model-badge">${esc(subject)}</span><span class="model-badge public-metric-badge">${esc(matrixNote)}</span><strong class="public-evidence-score">${esc(score)}${item.unit && score !== "—" ? esc(item.unit) : ""}</strong><span>${esc(item.rawValue && item.rawValue !== item.value ? item.rawValue : "")}</span><span>${esc(protocol)}</span></div></div><div class="public-evidence-source">${sourceLink ? `<a href="${esc(sourceLink)}" target="_blank" rel="noreferrer">↗ ${esc(item.sourceLabel || source?.label || sourceLink)}</a>` : "<span>来源未注明</span>"}<small>${esc(item.locator || item.sourceLocator || "locator 未注明")}</small><small>${esc(item.fetchedAt || item.retrievedAt || item.observedAt || "retrieved 未注明")}${item.snapshotHash || item.payloadSha256 ? ` · hash ${esc(String(item.snapshotHash || item.payloadSha256).slice(0, 12))}…` : ""}</small></div></article>`;
    }).join("");
    renderPublicAliasLedger();
  }

  /*
   * Keep unresolved source spellings visible without manufacturing matrix
   * rows.  The full summary is linked as a machine-readable audit artifact;
   * this compact ledger makes the distinction understandable at a glance.
   */
  function renderPublicAliasLedger() {
    const target = els.publicAliasLedger;
    if (!target) return;
    const rawGroups = Array.isArray(state.data?.publicUnmappedModels)
      ? state.data.publicUnmappedModels : [];
    const groups = rawGroups.map((raw) => {
      const item = raw && typeof raw === "object" ? raw : { modelRef: raw };
      const examples = Array.isArray(item.examples)
        ? item.examples.filter((example) => example && typeof example === "object") : [];
      const sourceIds = Array.isArray(item.sourceIds) ? item.sourceIds : (item.sourceId ? [item.sourceId] : []);
      const sourceLabels = Array.isArray(item.sourceLabels) ? item.sourceLabels : [];
      const sourceUrls = Array.isArray(item.sourceUrls) ? item.sourceUrls : [];
      const example = examples[0] || {};
      const firstSourceId = first(sourceIds[0], example.sourceId);
      const source = sourceFor(firstSourceId);
      const sourceLabel = first(sourceLabels[0], example.sourceLabel, source?.label, firstSourceId, "来源未注明");
      const sourceUrl = firstSafeUrl(sourceUrls[0], example.sourceUrl, example.evidenceUrl, source?.url);
      const benchmarks = Array.isArray(item.benchmarkIds) ? item.benchmarkIds : [];
      return {
        modelRef: text(item.modelRef, "unknown source model"),
        rowCount: Number(item.rowCount) || 0,
        numericRowCount: Number(item.numericRowCount) || 0,
        benchmarkCount: Number(item.benchmarkCount) || benchmarks.length,
        benchmarks,
        sourceLabel,
        sourceUrl,
        sourceLocator: first(example.sourceLocator, example.locator),
        latest: first(item.observedAtMax, item.latestRetrievedAt, example.observedAt, example.retrievedAt),
        status: Object.keys(item.mappingStatusCounts || {})[0] || "unmatched",
      };
    }).filter((item) => item.modelRef && (item.rowCount || item.numericRowCount));
    // Put recently observed source spellings first so the compact ledger is
    // useful for current frontier releases; the linked summary remains the
    // complete, deterministic list.
    const aliasSort = (a, b) => String(b.latest || "").localeCompare(String(a.latest || "")) || b.rowCount - a.rowCount || a.modelRef.localeCompare(b.modelRef);
    groups.sort(aliasSort);
    const query = String(state.search || "").trim().toLowerCase();
    const filtered = query
      ? groups.filter((item) => [item.modelRef, item.sourceLabel, item.sourceLocator, ...item.benchmarks].join(" ").toLowerCase().includes(query))
      : groups;
    target.hidden = state.mode !== "atlas" || groups.length === 0;
    if (!groups.length) { target.innerHTML = ""; return; }
    const visible = filtered.slice(0, 12);
    const totalRows = Number(state.data?.publicStats?.unmappedRows) || groups.reduce((sum, item) => sum + item.rowCount, 0);
    const cards = visible.map((item) => {
      const benchmarkText = item.benchmarks.slice(0, 3).map((value) => benchmarkFor(value)?.short || String(value).replace(/^epoch-/, "").replace(/_external$/, "").replace(/[-_]+/g, " ")).join(" · ");
      const sourceMarkup = item.sourceUrl
        ? `<a href="${esc(item.sourceUrl)}" target="_blank" rel="noreferrer">↗ ${esc(item.sourceLabel)}</a>`
        : `<span>${esc(item.sourceLabel)}</span>`;
      return `<article class="public-alias-card"><div class="public-alias-card-top"><code>${esc(item.modelRef)}</code><span>${fmt(item.rowCount, 0)} 条</span></div><div class="public-alias-card-meta"><span class="model-badge">source-native</span><span class="model-badge">${esc(item.status)}</span><span>${item.numericRowCount ? `${fmt(item.numericRowCount, 0)} 条有数值` : "无数值"}</span></div><p>${sourceMarkup}</p><small>${esc(benchmarkText || `${fmt(item.benchmarkCount, 0)} benchmarks`)}${item.latest ? ` · ${esc(String(item.latest).slice(0, 10))}` : ""}</small>${item.sourceLocator ? `<small class="public-alias-locator">${esc(item.sourceLocator)}</small>` : ""}</article>`;
    }).join("");
    target.innerHTML = `<div class="public-alias-heading"><div><h4>未安全归一化的来源原名</h4><p>这些公开记录确实存在，但当前没有足够身份信息映射到某个 release；保留原名和来源，不把它们猜进矩阵。</p></div><span class="section-note">${fmt(totalRows, 0)} 条 · ${fmt(groups.length, 0)} 个原名组</span></div><div class="public-alias-grid">${cards || '<p class="public-alias-empty">当前筛选没有匹配的来源原名。</p>'}</div><p class="public-alias-footnote">显示 ${fmt(visible.length, 0)} 个代表性分组；完整列表见 <a href="data/public/unmapped-summary.json" target="_blank" rel="noreferrer">unmapped summary ↗</a>，完整行见维护 artifact。空白单元格仍不代表没人测试。</p>`;
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
  function runScoreEntry(run) {
    const items = hydrateEvidenceItems(evidenceItems(run), run, run.value);
    const selected = chooseEvidence(items);
    return {
      value: run.value,
      verified: first(run.status, run.verificationStatus, selected?.status, "reported"),
      evidenceLevel: first(run.evidenceLevel, selected?.level),
      status: first(run.status, selected?.status, "reported"),
      evidenceStatus: evidenceStatus(run, selected?.status || "reported"),
      public: Boolean(run.public || run.evidenceOrigin === "public" || selected?.public || selected?.evidenceOrigin === "public"),
      evidenceOrigin: first(run.evidenceOrigin, selected?.evidenceOrigin),
      subjectType: first(run.subjectType, run.subject_type, selected?.subjectType),
      evidenceItems: items,
    };
  }
  function runRow(run) {
    const model = modelById(run.modelId) || normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider });
    const benchmark = benchmarkFor(run.benchmarkId) || { id: run.benchmarkId, name: run.benchmarkId, short: run.benchmarkId, scale: 100, unit: run.unit || "%" };
    const entry = runScoreEntry(run);
    const source = sourceFor(first(run.sourceId, run.sourceUrl, chooseEvidence(evidenceItems(run))?.sourceId, chooseEvidence(evidenceItems(run))?.sourceUrl));
    const evidence = statusLabel(entry);
    const badges = `${badge(harnessLabel(run), "harness-badge")}${badge(protocolLabel(run), "protocol-badge")}${evidenceBadge(entry)}`;
    return `<tr class="run-row" data-run="${esc(run.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 的 ${esc(benchmark.name)} system run"><td class="run-model-cell">${modelMarkup(model)}</td><td><span class="run-benchmark-name">${esc(benchmark.short || benchmark.name)}</span><small>${esc(benchmark.version || run.benchmarkVersion || "version 未注明")}</small></td><td class="run-score-cell ${scoreClass(entry, benchmark)}"><strong>${run.value === null || run.value === undefined ? "—" : fmt(run.value)}${run.value !== null && run.value !== undefined ? esc(run.unit || benchmark.unit || "") : ""}</strong><small>${esc(run.metric || benchmark.metric || "score")}</small></td><td><div class="run-badges">${badges}</div></td><td><span class="status-badge ${statusClass(entry)}">${esc(evidence)}</span><small class="run-date">${esc(run.observedAt || "未注明")}</small></td><td class="run-source-cell">${source ? '<span class="source-chip">S</span>' : "—"}</td></tr>`;
  }
  function runPage(runs) {
    const pageCount = Math.max(1, Math.ceil(runs.length / RUN_PAGE_SIZE));
    state.runPage = Math.min(Math.max(0, state.runPage), pageCount - 1);
    const start = state.runPage * RUN_PAGE_SIZE;
    return { items: runs.slice(start, start + RUN_PAGE_SIZE), start, pageCount };
  }
  function runPagerMarkup(start, visible, total, pageCount) {
    if (pageCount <= 1) return "";
    const from = total ? start + 1 : 0;
    const to = start + visible;
    return `<nav class="run-pagination" aria-label="System Runs pages"><button class="outline-button" type="button" data-run-page="-1"${state.runPage === 0 ? " disabled" : ""}>上一页</button><span>${fmt(from, 0)}–${fmt(to, 0)} / ${fmt(total, 0)}</span><button class="outline-button" type="button" data-run-page="1"${state.runPage >= pageCount - 1 ? " disabled" : ""}>下一页</button></nav>`;
  }
  function renderRuns() {
    const runs = filteredRuns();
    const page = runPage(runs);
    const pager = runPagerMarkup(page.start, page.items.length, runs.length, page.pageCount);
    if (state.runView === "table") {
      if (els.runCardsView) els.runCardsView.innerHTML = "";
      if (els.runTableHead) els.runTableHead.innerHTML = "<tr><th>MODEL / RELEASE</th><th>BENCHMARK</th><th>SCORE</th><th>HARNESS / PROTOCOL</th><th>EVIDENCE / DATE</th><th>SOURCE</th></tr>";
      if (els.runTableBody) els.runTableBody.innerHTML = page.items.map(runRow).join("") + (pager ? `<tr class="run-pagination-row"><td colspan="6">${pager}</td></tr>` : "");
    } else {
      if (els.runTableHead) els.runTableHead.innerHTML = "";
      if (els.runTableBody) els.runTableBody.innerHTML = "";
    }
    if (els.runEmptyState) els.runEmptyState.hidden = runs.length !== 0;
    if (els.runCountLabel) els.runCountLabel.textContent = runs.length > RUN_PAGE_SIZE ? `${page.start + 1}–${page.start + page.items.length} / ${runs.length}` : String(runs.length);
    if (state.runView === "cards" && els.runCardsView) els.runCardsView.innerHTML = page.items.map((run) => {
      const model = modelById(run.modelId) || normaliseModel({ id: run.modelId, name: run.modelName, provider: run.provider });
      const benchmark = benchmarkFor(run.benchmarkId) || { name: run.benchmarkId, short: run.benchmarkId, scale: 100 };
      const entry = runScoreEntry(run);
      return `<article class="run-card" data-run="${esc(run.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} system run"><div class="run-card-top"><div>${modelMarkup(model)}</div><strong class="run-card-score ${scoreClass(entry, benchmark)}">${run.value === null || run.value === undefined ? "—" : fmt(run.value)}<small>${esc(run.unit || benchmark.unit || "")}</small></strong></div><div class="run-card-benchmark"><span>${esc(benchmark.name || benchmark.short)}</span><small>${esc(benchmark.version || run.benchmarkVersion || "version 未注明")}</small></div><div class="run-badges">${badge(harnessLabel(run), "harness-badge")}${badge(protocolLabel(run), "protocol-badge")}${evidenceBadge(entry)}<span class="status-badge ${statusClass(entry)}">${esc(statusLabel(entry))}</span></div><p class="run-card-note">${esc(run.notes || `observed ${run.observedAt || "未注明"}`)}</p></article>`;
    }).join("") + pager;
  }

  function renderSpotlights() {
    const benchmarks = filteredBenchmarks();
    const models = filteredModels().filter((model) => hasScore(model));
    const signals = benchmarks.map((benchmark, order) => {
      const values = models.map((model) => ({ model, entry: scoreEntry(model, benchmark.id) })).filter(({ entry }) => entry.value !== null && entry.value !== undefined && String(entry.subjectType || entry.subject_type || "model").toLowerCase() !== "system").sort((a, b) => benchmark.direction === "lower" ? Number(a.entry.value) - Number(b.entry.value) : Number(b.entry.value) - Number(a.entry.value));
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
    if (els.matrixTools) els.matrixTools.hidden = !atlas || state.atlasView !== "matrix";
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
    if (state.mode === "runs") {
      if (els.matrixHead) els.matrixHead.innerHTML = "";
      if (els.matrixBody) els.matrixBody.innerHTML = "";
      if (els.cardsView) els.cardsView.innerHTML = "";
      if (els.publicEvidenceList) els.publicEvidenceList.innerHTML = "";
      if (els.publicAliasLedger) els.publicAliasLedger.innerHTML = "";
      if (els.publicEvidenceSection) els.publicEvidenceSection.hidden = true;
      if (els.spotlightGrid) els.spotlightGrid.innerHTML = "";
      renderRuns();
    } else {
      if (els.runTableHead) els.runTableHead.innerHTML = "";
      if (els.runTableBody) els.runTableBody.innerHTML = "";
      if (els.runCardsView) els.runCardsView.innerHTML = "";
      if (state.atlasView === "matrix") {
        if (els.cardsView) els.cardsView.innerHTML = "";
        renderMatrix();
      } else {
        if (els.matrixHead) els.matrixHead.innerHTML = "";
        if (els.matrixBody) els.matrixBody.innerHTML = "";
        renderCards();
      }
      renderPublicEvidence();
      renderSpotlights();
    }
    updateModeCopy();
  }

  function evidenceDetails(raw, title = "Public evidence") {
    const parentValue = raw && typeof raw === "object"
      ? first(raw.value, raw.score, raw.result, raw.percentage, raw.accuracy)
      : null;
    const numericValue = parentValue === null || parentValue === undefined || parentValue === ""
      ? null
      : (Number.isFinite(Number(parentValue)) ? Number(parentValue) : parentValue);
    const items = hydrateEvidenceItems(evidenceItems(raw), raw, numericValue);
    if (!items.length) return "";
    const unverified = items.some((item) => Boolean(item.public || item.evidenceOrigin === "public") || evidenceStatus(item, "reported") !== "approved");
    const rows = items.map((item, index) => {
      const status = evidenceStatus(item, item.value === null ? "missing" : "reported");
      const publicItem = Boolean(item.public || item.evidenceOrigin === "public");
      const statusText = publicItem
        ? (status === "candidate" ? "候选 · 未复现" : "披露 · 未复现")
        : (status === "approved" ? "approved" : (status === "reported" ? "官方披露 · 未复现" : `${status || "reported"} · 未复现`));
      const source = sourceFor(first(item.sourceId, item.sourceUrl));
      const sourceUrl = firstSafeUrl(item.evidenceUrl, item.evidence_url, item.sourceUrl, source?.url);
      const sourceText = item.sourceLabel || source?.label || source?.title || sourceUrl || item.sourceId || "来源未注明";
      const hash = item.snapshotHash || item.sha256 || item.hash;
      const rawModel = first(item.sourceModel, item.source_model, item.modelName, item.model_name, item.modelId);
      const rawBenchmark = first(item.sourceBenchmark, item.source_benchmark, item.benchmarkName, item.benchmark_name, item.benchmarkId);
      const rawValue = first(item.rawValue, item.raw_value);
      const qualityFlags = list(first(item.qualityFlags, item.quality_flags)).filter(Boolean).join(" · ");
      return `<div class="evidence-row"><div class="evidence-row-head"><span class="evidence-index">${String(index + 1).padStart(2, "0")}</span><span class="score-evidence evidence-${slug(status)}${publicItem ? " evidence-public" : ""}${String(item.subjectType || "").toLowerCase() === "system" ? " evidence-system" : ""}">${esc(statusText)}</span><strong>${item.value === null || item.value === undefined ? "—" : esc(fmt(item.value))}</strong>${item.unit ? `<small>${esc(item.unit)}</small>` : ""}</div><div class="evidence-row-grid"><span><label>source</label>${sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noreferrer">↗ ${esc(sourceText)}</a>` : `<em>${esc(sourceText)}</em>`}</span><span><label>raw model / bench</label><em>${esc([rawModel, rawBenchmark].filter(Boolean).join(" × ") || "未注明")}</em></span><span><label>raw value</label><em>${esc(rawValue === undefined || rawValue === null ? "未注明" : display(rawValue))}</em></span><span><label>locator</label><em>${esc(item.locator || item.sourceLocator || "未注明")}</em></span><span><label>retrieved</label><em>${esc(item.fetchedAt || item.retrievedAt || "未注明")}</em></span><span><label>published / observed</label><em>${esc([item.publishedAt, item.observedAt].filter(Boolean).join(" · ") || "未注明")}</em></span><span><label>snapshot hash</label><em class="evidence-hash" title="${esc(hash || "")}">${esc(hash || "未保存")}</em></span><span><label>subject / harness</label><em>${esc([item.subjectType, item.harnessId || item.harness].filter(Boolean).join(" · ") || "model")}</em></span><span><label>protocol</label><em>${esc(display(item.protocol, "未注明"))}</em></span>${qualityFlags ? `<span><label>quality flags</label><em>${esc(qualityFlags)}</em></span>` : ""}${item.parserVersion || item.parser_version ? `<span><label>parser</label><em>${esc(item.parserVersion || item.parser_version)}</em></span>` : ""}</div>${item.notes || item.evidenceNote ? `<p class="evidence-row-note">${esc(item.notes || item.evidenceNote)}</p>` : ""}</div>`;
    }).join("");
    return `<section class="detail-section evidence-section"><h4>${esc(title)} · ${items.length}</h4>${unverified ? '<p class="evidence-disclaimer">公开榜单 / provider 披露仅作参考；本项目尚未独立复现这些数字。</p>' : ""}<details class="evidence-details"${items.length === 1 ? " open" : ""}><summary>展开来源、locator、抓取时间、hash 与 protocol</summary><div class="evidence-list">${rows}</div></details></section>`;
  }

  function detailGrid(items) {
    return `<div class="detail-grid">${items.map(([label, value]) => `<div class="detail-item"><label>${esc(label)}</label><span>${esc(display(value))}</span></div>`).join("")}</div>`;
  }
  function publicEvidenceById(id) {
    return [...(state.data?.publicEvidence || []), ...(state.data?.unmappedEvidence || [])].find((item) => item.id === id) || null;
  }
  function openEvidenceDrawer(id) {
    const item = publicEvidenceById(id);
    if (!item || !els.drawerContent) return;
    state.selected = { type: "public-evidence", evidenceId: id };
    const source = sourceFor(first(item.sourceId, item.sourceUrl));
    const subject = first(item.subjectType, item.subject_type, "model");
    const link = firstSafeUrl(item.evidenceUrl, item.sourceUrl, source?.url);
    const displayBenchmarkId = first(item.displayBenchmarkId, item.display_benchmark_id, item.benchmarkId);
    const baseBenchmarkId = first(item.baseBenchmarkId, item.base_benchmark_id, item.benchmarkId);
    const benchmark = benchmarkFor(displayBenchmarkId) || benchmarkFor(baseBenchmarkId);
    const protocol = item.protocol && typeof item.protocol === "object" ? JSON.stringify(item.protocol) : item.protocol;
    const sourcePage = firstSafeUrl(item.sourcePageUrl, sourceContextUrl(source));
    const benchmarkVersion = first(item.benchmarkVersionId, item.benchmarkVersion, item.benchmarkVersionHint, "version 未注明");
    const matrixStatus = item.matrixExcluded
      ? `仅证据（${item.matrixExcludedReason || "telemetry metric"}，未进入矩阵）`
      : `已进入矩阵${item.metricSlice ? ` · ${item.metricSliceLabel || item.metricId || "metric slice"}` : ""}`;
    const rawBenchmark = first(item.sourceBenchmark, item.source_benchmark, item.benchmarkName, item.benchmarkId, "公开 benchmark");
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">E</span><div><h3 id="drawerTitle">${esc(first(item.sourceModel, item.modelName, item.modelRef, "公开模型行"))}</h3><p>${esc(rawBenchmark)} · ${esc(item.sourceLabel || source?.label || item.sourceId || "source 未注明")}</p></div></div><div class="drawer-score"><span class="status-badge conditional">披露 · 未复现</span><div class="big-score">${item.value === null || item.value === undefined ? "—" : `${fmt(item.value)}<small>${esc(item.unit || "")}</small>`}</div><p>${esc(item.metricId || "score")} · ${esc(benchmarkVersion)}</p></div><section class="detail-section"><h4>Mapping</h4>${detailGrid([["Source model", item.modelRef || item.sourceModel || item.modelName], ["Canonical release", item.canonicalModelId || item.mappedModelId || "未安全映射"], ["Source benchmark", rawBenchmark], ["Display column", displayBenchmarkId], ["Base benchmark", baseBenchmarkId], ["Mapping status", item.mappingStatus || "unmatched"], ["Matrix status", matrixStatus], ["Subject", subject], ["Harness", item.harnessId || item.harness]])}</section>${benchmark?.description ? `<section class="detail-section"><h4>What this measures</h4><p class="detail-note">${esc(benchmark.description)}</p></section>` : ""}${evidenceDetails(item, "Public evidence")}${link ? `<section class="detail-section"><h4>Snapshot / API</h4><a class="source-link" href="${esc(link)}" target="_blank" rel="noreferrer">↗ ${esc(link)}</a>${sourcePage && sourcePage !== link ? `<p class="detail-note"><a href="${esc(sourcePage)}" target="_blank" rel="noreferrer">打开来源说明页 ↗</a></p>` : ""}</section>` : (sourcePage ? `<section class="detail-section"><h4>Source page</h4><a class="source-link" href="${esc(sourcePage)}" target="_blank" rel="noreferrer">↗ ${esc(sourcePage)}</a></section>` : "")}${protocol ? `<section class="detail-section"><h4>Protocol</h4><p class="detail-note">${esc(protocol)}</p></section>` : ""}<button class="copy-json" type="button" id="copyObservation">复制公开证据 JSON</button>`;
    showDrawer();
    const copyButton = $("copyObservation");
    if (copyButton) copyButton.addEventListener("click", () => copyJson(item, "已复制公开证据 JSON"));
  }
  function openModelDrawer(modelId, benchmarkId = null) {
    const model = modelById(modelId);
    if (!model || !els.drawerContent) return;
    state.selected = { type: "model", modelId, benchmarkId };
    const benchmark = benchmarkId ? benchmarkFor(benchmarkId) : null;
    const entry = benchmark ? scoreEntry(model, benchmark.id) : null;
    const source = entry ? sourceFor(first(entry.sourceId, entry.sourceUrl, chooseEvidence(evidenceItems(entry))?.sourceId, chooseEvidence(evidenceItems(entry))?.sourceUrl)) : null;
    const benchmarks = state.data?.benchmarks || [];
    const recorded = benchmarks.map((item) => ({ benchmark: item, entry: scoreEntry(model, item.id) })).filter(({ entry: itemEntry }) => itemEntry.value !== null && itemEntry.value !== undefined);
    const mainScore = entry || (recorded[0]?.entry || { value: null });
    const mainBenchmark = benchmark || recorded[0]?.benchmark;
    const relatedRuns = (state.data?.runs || []).filter((run) => run.modelId === model.id).slice(0, 8);
    const runLinks = relatedRuns.map((run) => `<button class="drawer-run-link" type="button" data-run="${esc(run.id)}"><span>${esc(benchmarkFor(run.benchmarkId)?.short || run.benchmarkId)}</span><strong>${run.value === null || run.value === undefined ? "—" : fmt(run.value)}${esc(run.unit || "%")}</strong></button>`).join("");
    const modelSourcePage = sourceContextUrl(source);
    const modelSourceUrl = safeUrl(source?.url);
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3 id="drawerTitle">${esc(model.name)}</h3><p>${esc(model.provider)} · release ${esc(model.release || "未注明")} · ${esc(model.status || model.access || "access 未注明")}</p></div></div><div class="drawer-score"><span class="status-badge ${statusClass(mainScore)}">${esc(statusLabel(mainScore))}</span><div class="big-score">${mainScore.value !== null && mainScore.value !== undefined ? `${fmt(mainScore.value)}<small>${esc(mainBenchmark?.unit || "")}</small>` : "—"}</div><p>${mainBenchmark ? `${esc(mainBenchmark.name)} · ${esc(display(mainScore.setting, "设置未说明"))}` : "选择一个单元格查看具体 observation。"}</p></div><section class="detail-section"><h4>Model note</h4><p class="detail-note">${esc(model.summary)}</p></section><section class="detail-section"><h4>Model registry</h4>${detailGrid([["Status", model.status], ["Access", model.access], ["Params total", model.paramsTotal], ["Params active", model.paramsActive], ["Context", model.context], ["Endpoint", model.endpoint]])}</section><section class="detail-section"><h4>Protocol & provenance</h4>${detailGrid([["Benchmark version", mainScore.benchmarkVersion || mainScore.version || mainBenchmark?.version], ["Observed", mainScore.observedAt || mainScore.observed_at || state.data?.meta?.asOf], ["Comparability", mainScore.comparability || "conditional"], ["Evidence", mainScore.evidenceLevel || mainScore.evidence_level || mainScore.verified], ["Source URL", mainScore.sourceUrl], ["Locator", mainScore.locator], ["Retrieved", mainScore.fetchedAt], ["Snapshot hash", mainScore.snapshotHash]])}${mainScore.note || mainScore.notes ? `<p class="detail-note">${esc(mainScore.note || mainScore.notes)}</p>` : ""}</section>${evidenceDetails(mainScore)}${source && (modelSourcePage || modelSourceUrl) ? `<section class="detail-section"><h4>Source</h4><a class="source-link" href="${esc(modelSourcePage || modelSourceUrl)}" target="_blank" rel="noreferrer">↗ ${esc(source.label || source.title || modelSourcePage || modelSourceUrl)}</a>${modelSourceUrl && modelSourcePage && modelSourceUrl !== modelSourcePage ? `<p class="detail-note"><a href="${esc(modelSourceUrl)}" target="_blank" rel="noreferrer">打开 API / 快照 ↗</a></p>` : ""}${source.locator ? `<p class="detail-note">定位：${esc(source.locator)}</p>` : ""}</section>` : ""}<section class="detail-section"><h4>Recorded signals</h4><div class="timeline">${recorded.map(({ benchmark: itemBenchmark, entry: itemEntry }) => `<div class="timeline-row"><span>${esc(itemBenchmark.short || itemBenchmark.name)}</span><span class="timeline-track"><i style="width:${Math.min(100, Math.max(0, scoreRatio(itemEntry.value, itemBenchmark) * 100))}%"></i></span><strong>${fmt(itemEntry.value)}${esc(itemBenchmark.unit || "")}</strong></div>`).join("") || '<p class="detail-note">暂无可显示的成绩。</p>'}</div></section>${runLinks ? `<section class="detail-section"><h4>System runs</h4><div class="drawer-run-list">${runLinks}</div></section>` : ""}<button class="copy-json" type="button" id="copyObservation">复制 JSON</button>`;
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
    const source = sourceFor(first(run.sourceId, run.sourceUrl, chooseEvidence(evidenceItems(run))?.sourceId, chooseEvidence(evidenceItems(run))?.sourceUrl));
    const entry = runScoreEntry(run);
    const related = (state.data?.runs || []).filter((item) => item.modelId === run.modelId && item.benchmarkId === run.benchmarkId && item.id !== run.id).slice(0, 6);
    const runSourcePage = sourceContextUrl(source);
    const runSourceUrl = safeUrl(source?.url);
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3 id="drawerTitle">${esc(model.name)}</h3><p>${esc(model.provider)} · ${esc(run.endpointId || model.endpoint || "endpoint 未注明")}</p></div></div><div class="drawer-score run-drawer-score"><span class="status-badge ${statusClass(entry)}">${esc(statusLabel(entry))}</span><div class="big-score">${run.value === null || run.value === undefined ? "—" : `${fmt(run.value)}<small>${esc(run.unit || benchmark.unit || "")}</small>`}</div><p>${esc(benchmark.name)} · ${esc(run.benchmarkVersion || benchmark.version || "version 未注明")}</p></div><section class="detail-section"><h4>Harness & protocol</h4>${detailGrid([["Harness", harness ? `${harness.name}${harness.version ? ` · ${harness.version}` : ""}` : "model-only"], ["Endpoint", run.endpointId], ["Protocol", protocolLabel(run)], ["Effort", run.effort], ["Steps", run.steps], ["Tools", run.tools || run.toolPolicy || run.tool_policy]])}</section><section class="detail-section"><h4>Run provenance</h4>${detailGrid([["Benchmark", benchmark.name], ["Metric", run.metric || benchmark.metric], ["Observed", run.observedAt], ["Published", run.publishedAt], ["Retrieved", run.fetchedAt], ["Comparability", run.comparability], ["Evidence", run.evidenceLevel || run.evidence], ["Source URL", run.sourceUrl], ["Locator", run.locator], ["Snapshot hash", run.snapshotHash], ["Cost", run.cost], ["Latency", run.latency]])}${run.notes ? `<p class="detail-note">${esc(run.notes)}</p>` : ""}</section>${evidenceDetails(run, "Evidence trail")}${source && (runSourcePage || runSourceUrl) ? `<section class="detail-section"><h4>Source</h4><a class="source-link" href="${esc(runSourcePage || runSourceUrl)}" target="_blank" rel="noreferrer">↗ ${esc(source.label || source.title || runSourcePage || runSourceUrl)}</a>${runSourceUrl && runSourcePage && runSourceUrl !== runSourcePage ? `<p class="detail-note"><a href="${esc(runSourceUrl)}" target="_blank" rel="noreferrer">打开 API / 快照 ↗</a></p>` : ""}${source.locator ? `<p class="detail-note">定位：${esc(source.locator)}</p>` : ""}</section>` : ""}${related.length ? `<section class="detail-section"><h4>Same model / benchmark</h4><div class="drawer-run-list">${related.map((item) => `<button class="drawer-run-link" type="button" data-run="${esc(item.id)}"><span>${esc(harnessFor(item.harnessId)?.name || "model-only")}</span><strong>${item.value === null || item.value === undefined ? "—" : fmt(item.value)}${esc(item.unit || benchmark.unit || "")}</strong></button>`).join("")}</div></section>` : ""}<button class="copy-json" type="button" id="copyObservation">复制 run JSON</button>`;
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
    state.search = ""; state.provider = "all"; state.family = "all"; state.harness = "all"; state.runBenchmark = "all"; state.preset = state.data?.presets?.some((preset) => preset.id === "public-coverage") ? "public-coverage" : "all"; state.sort = state.mode === "runs" ? "run-recent" : "coverage"; state.availableOnly = false; state.showCatalog = false; state.runPage = 0;
    if (els.searchInput) els.searchInput.value = "";
    if (els.availableOnly) els.availableOnly.checked = false;
    if (els.showCatalog) els.showCatalog.checked = false;
    render();
  }

  function bind() {
    const savedDensity = localStorage.getItem("fmb-matrix-density");
    if (["compact", "standard"].includes(savedDensity)) state.matrixDensity = savedDensity;
    els.searchInput?.addEventListener("input", (event) => { state.search = event.target.value; state.runPage = 0; render(); });
    els.providerFilter?.addEventListener("change", (event) => { state.provider = event.target.value; state.runPage = 0; render(); });
    els.familyFilter?.addEventListener("change", (event) => { state.family = event.target.value; state.runPage = 0; render(); });
    els.presetSelect?.addEventListener("change", (event) => {
      state.preset = event.target.value;
      const preset = activePreset();
      // Presets declare the appropriate comparison subject.  Switching back
      // from a run preset must explicitly return to the release-level atlas;
      // otherwise the controls keep showing a stale System Runs view.
      state.mode = preset?.mode === "runs" ? "runs" : "atlas";
      state.sort = state.mode === "runs" ? "run-recent" : "coverage";
      state.runPage = 0;
      render();
    });
    els.harnessFilter?.addEventListener("change", (event) => { state.harness = event.target.value; state.runPage = 0; render(); });
    els.runBenchmarkFilter?.addEventListener("change", (event) => { state.runBenchmark = event.target.value; state.runPage = 0; render(); });
    els.sortSelect?.addEventListener("change", (event) => { state.sort = event.target.value; state.runPage = 0; render(); });
    els.availableOnly?.addEventListener("change", (event) => { state.availableOnly = event.target.checked; state.runPage = 0; render(); });
    els.showCatalog?.addEventListener("change", (event) => { state.showCatalog = event.target.checked; state.runPage = 0; render(); });
    $("resetFilters")?.addEventListener("click", resetFilters); $("emptyReset")?.addEventListener("click", resetFilters); $("runEmptyReset")?.addEventListener("click", resetFilters);
    document.querySelectorAll(".mode-tab").forEach((tab) => tab.addEventListener("click", () => { state.mode = tab.dataset.mode; state.sort = state.mode === "runs" ? "run-recent" : "coverage"; state.runPage = 0; render(); }));
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => tab.addEventListener("click", () => { state.atlasView = tab.dataset.view; render(); }));
    document.querySelectorAll(".view-tab[data-run-view]").forEach((tab) => tab.addEventListener("click", () => { state.runView = tab.dataset.runView; state.runPage = 0; render(); }));
    document.querySelectorAll("[data-matrix-density]").forEach((button) => button.addEventListener("click", () => {
      state.matrixDensity = button.dataset.matrixDensity === "standard" ? "standard" : "compact";
      localStorage.setItem("fmb-matrix-density", state.matrixDensity);
      syncMatrixDensity();
    }));
    els.benchmarkJump?.addEventListener("change", (event) => {
      state.matrixBenchmarkJump = event.target.value;
      scrollMatrixToBenchmark(state.matrixBenchmarkJump);
    });
    els.matrixHome?.addEventListener("click", () => {
      state.matrixBenchmarkJump = "";
      if (els.benchmarkJump) els.benchmarkJump.value = "";
      if (typeof els.matrixScroll?.scrollTo === "function") els.matrixScroll.scrollTo({ left: 0, behavior: "smooth" });
      else if (els.matrixScroll) els.matrixScroll.scrollLeft = 0;
    });
    els.publicEvidenceToggle?.addEventListener("click", () => {
      state.publicEvidenceExpanded = !state.publicEvidenceExpanded;
      renderPublicEvidence();
    });
    document.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      const pageTarget = event.target.closest("[data-run-page]");
      if (pageTarget) {
        state.runPage += Number(pageTarget.dataset.runPage || 0);
        render();
        return;
      }
      const runTarget = event.target.closest("[data-run]");
      if (runTarget) return openRunDrawer(runTarget.dataset.run);
      const cell = event.target.closest("[data-model][data-benchmark]");
      if (cell) return openModelDrawer(cell.dataset.model, cell.dataset.benchmark);
      const evidenceTarget = event.target.closest("[data-public-evidence]");
      if (evidenceTarget) return openEvidenceDrawer(evidenceTarget.dataset.publicEvidence);
      const modelTarget = event.target.closest("[data-model]");
      if (modelTarget) openModelDrawer(modelTarget.dataset.model);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && document.activeElement !== els.searchInput) { event.preventDefault(); els.searchInput?.focus(); }
      if (event.key === "Escape") closeDrawer();
      if (event.key === "Enter" && document.activeElement?.matches("[data-run]")) openRunDrawer(document.activeElement.dataset.run);
      else if (event.key === "Enter" && document.activeElement?.matches("[data-public-evidence]")) openEvidenceDrawer(document.activeElement.dataset.publicEvidence);
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
        const response = await fetch(path);
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
