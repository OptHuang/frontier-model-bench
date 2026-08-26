(() => {
  "use strict";

  const state = {
    data: null,
    view: "matrix",
    search: "",
    provider: "all",
    family: "all",
    sort: "coverage",
    availableOnly: false,
    selected: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    asOfLabel: $("asOfLabel"), cadenceLabel: $("cadenceLabel"), qualityValue: $("qualityValue"),
    qualityBar: $("qualityBar"), modelCount: $("modelCount"), benchmarkCount: $("benchmarkCount"),
    familyCount: $("familyCount"), observationCount: $("observationCount"), coverageValue: $("coverageValue"),
    providerFilter: $("providerFilter"), familyFilter: $("familyFilter"), sortSelect: $("sortSelect"),
    searchInput: $("searchInput"), availableOnly: $("availableOnly"), activeFilters: $("activeFilters"),
    matrixHead: $("matrixHead"), matrixBody: $("matrixBody"), matrixView: $("matrixView"), cardsView: $("cardsView"),
    emptyState: $("emptyState"), spotlightGrid: $("spotlightGrid"), footerStatus: $("footerStatus"),
    freshnessPill: $("freshnessPill"), drawer: $("detailDrawer"), drawerBackdrop: $("drawerBackdrop"),
    drawerContent: $("drawerContent"), toast: $("toast"),
  };

  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || value === "") return "—";
    return Number.isInteger(value) ? String(value) : Number(value).toFixed(digits).replace(/\.0$/, "");
  };

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));

  const sourceFor = (id) => (state.data?.sources || []).find((source) => source.id === id);
  const benchmarkFor = (id) => (state.data?.benchmarks || []).find((benchmark) => benchmark.id === id);

  function scoreEntry(model, benchmarkId) {
    return model.scores?.[benchmarkId] || { value: null, setting: "未报告", verified: "missing" };
  }

  function scoreClass(entry, benchmark) {
    if (entry.value === null || entry.value === undefined) return "score-missing";
    const scale = Number(benchmark?.scale || 100);
    const ratio = Number(entry.value) / scale;
    if (ratio >= 0.85) return "score-high";
    if (ratio >= 0.70) return "score-mid";
    return "score-low";
  }

  function statusLabel(entry) {
    if (!entry || entry.value === null || entry.value === undefined) return "未报告";
    if (entry.verified === "reported") return "官方披露";
    if (entry.verified === "reproduced") return "可复现";
    if (entry.verified === "verified") return "已核验";
    if (entry.verified === "conditional") return "条件性";
    return "示例数据";
  }

  function statusClass(entry) {
    if (!entry || entry.value === null || entry.value === undefined) return "missing";
    if (entry.verified === "reported" || entry.verified === "reproduced" || entry.verified === "verified") return "reported";
    if (entry.verified === "conditional") return "conditional";
    return "demo";
  }

  function modelCoverage(model) {
    const list = state.data.benchmarks || [];
    const observed = list.filter((bench) => {
      const value = scoreEntry(model, bench.id).value;
      return value !== null && value !== undefined;
    }).length;
    return list.length ? observed / list.length : 0;
  }

  function filteredModels() {
    const query = state.search.trim().toLowerCase();
    const models = (state.data.models || []).filter((model) => {
      const searchable = [model.name, model.provider, ...(model.tags || []), model.summary].join(" ").toLowerCase();
      const matchesQuery = !query || searchable.includes(query);
      const matchesProvider = state.provider === "all" || model.provider === state.provider;
      const matchesFamily = state.family === "all" || (model.tags || []).includes(state.family);
      const hasScore = !state.availableOnly || (state.data.benchmarks || []).some((bench) => scoreEntry(model, bench.id).value !== null && scoreEntry(model, bench.id).value !== undefined);
      return matchesQuery && matchesProvider && matchesFamily && hasScore;
    });
    return models.sort((a, b) => {
      if (state.sort === "recent") return String(b.release || "").localeCompare(String(a.release || ""));
      if (state.sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      return modelCoverage(b) - modelCoverage(a) || String(b.release || "").localeCompare(String(a.release || ""));
    });
  }

  function renderFilters() {
    const providers = [...new Set((state.data.models || []).map((model) => model.provider))].sort();
    els.providerFilter.innerHTML = '<option value="all">所有厂商</option>' + providers.map((provider) => `<option value="${esc(provider)}">${esc(provider)}</option>`).join("");
    els.providerFilter.value = state.provider;
    // Tags are intentionally shown as a light capability filter. Families in the catalog remain free-form.
    const families = [...new Set((state.data.models || []).flatMap((model) => model.tags || []))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    els.familyFilter.innerHTML = '<option value="all">所有标签</option>' + families.map((family) => `<option value="${esc(family)}">${esc(family)}</option>`).join("");
    els.familyFilter.value = state.family;
    els.sortSelect.value = state.sort;
  }

  function renderActiveFilters() {
    const chips = [];
    if (state.search) chips.push(`搜索：${esc(state.search)}`);
    if (state.provider !== "all") chips.push(`厂商：${esc(state.provider)}`);
    if (state.family !== "all") chips.push(`标签：${esc(state.family)}`);
    if (state.availableOnly) chips.push("只看有成绩");
    els.activeFilters.innerHTML = chips.map((chip) => `<span class="filter-chip">${chip}</span>`).join("");
  }

  function renderStats() {
    const models = state.data.models || [];
    const benchmarks = state.data.benchmarks || [];
    const observations = models.reduce((sum, model) => sum + benchmarks.filter((bench) => {
      const value = scoreEntry(model, bench.id).value;
      return value !== null && value !== undefined;
    }).length, 0);
    const total = models.length * benchmarks.length;
    const coverage = total ? observations / total : 0;
    const families = new Set(benchmarks.map((bench) => bench.family));
    const quality = models.reduce((sum, model) => sum + benchmarks.reduce((inner, bench) => {
      const entry = scoreEntry(model, bench.id);
      return inner + (entry.value !== null && entry.value !== undefined ? (entry.verified === "demo" ? 0.45 : 1) : 0);
    }, 0), 0);
    const qualityMax = Math.max(1, observations);
    const qualityPct = Math.round(Math.min(100, quality / qualityMax * 100));
    els.modelCount.textContent = models.length;
    els.benchmarkCount.textContent = benchmarks.length;
    els.familyCount.textContent = families.size;
    els.observationCount.textContent = observations;
    els.coverageValue.textContent = `${Math.round(coverage * 100)}%`;
    els.qualityValue.textContent = `${qualityPct}%`;
    els.qualityBar.style.width = `${qualityPct}%`;
    els.asOfLabel.textContent = state.data.meta?.asOf || "—";
    els.cadenceLabel.textContent = state.data.meta?.updateCadence || "—";
    const isDemo = state.data.meta?.status === "demo" || state.data.meta?.status === "illustrative";
    els.freshnessPill.innerHTML = `<span class="status-dot"></span><span>${isDemo ? "seed snapshot" : "curated snapshot"}</span>`;
    els.footerStatus.textContent = isDemo ? "Seed data: replace or verify before citing." : "Sources linked per observation.";
  }

  function renderMatrix() {
    const benchmarks = state.data.benchmarks || [];
    const models = filteredModels();
    els.matrixHead.innerHTML = `<tr><th scope="col">MODEL / RELEASE</th>${benchmarks.map((bench) => `<th scope="col"><span class="bench-head"><strong>${esc(bench.short || bench.name)}</strong><small>${esc(bench.metricLabel || bench.metric || "score")}</small></span></th>`).join("")}</tr>`;
    els.matrixBody.innerHTML = models.map((model) => {
      const tags = (model.tags || []).slice(0, 2).map((tag) => `<span class="model-badge">${esc(tag)}</span>`).join("");
      const cells = benchmarks.map((bench) => {
        const entry = scoreEntry(model, bench.id);
        const missing = entry.value === null || entry.value === undefined;
        const source = sourceFor(entry.sourceId);
        const sourceMark = source ? '<span class="source-chip">S</span>' : "";
        return `<td class="score-cell ${scoreClass(entry, bench)}" data-model="${esc(model.id)}" data-benchmark="${esc(bench.id)}" tabindex="0" role="button" aria-label="${esc(model.name)} ${esc(bench.name)} ${missing ? "未报告" : fmt(entry.value) + (bench.unit || "")}">
          <span class="score-value">${missing ? "—" : fmt(entry.value)}${!missing && bench.unit ? `<small>${esc(bench.unit)}</small>` : ""}${sourceMark}</span>
          <span class="score-setting">${esc(entry.setting || "未说明")}</span>
        </td>`;
      }).join("");
      return `<tr><td class="model-cell" data-model="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)}"><div class="model-line"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><span><span class="model-name">${esc(model.name)}</span><span class="model-provider">${esc(model.provider)} · ${esc(model.release || "release 未注明")}</span></span></div><div class="model-badges">${tags}</div></td>${cells}</tr>`;
    }).join("");
    els.emptyState.hidden = models.length !== 0;
  }

  function renderCards() {
    const models = filteredModels();
    const benchmarks = state.data.benchmarks || [];
    els.cardsView.innerHTML = models.map((model) => {
      const ranked = benchmarks.map((bench) => ({ bench, entry: scoreEntry(model, bench.id) })).filter(({ entry }) => entry.value !== null && entry.value !== undefined).sort((a, b) => b.entry.value - a.entry.value).slice(0, 5);
      const recorded = benchmarks.filter((bench) => scoreEntry(model, bench.id).value !== null && scoreEntry(model, bench.id).value !== undefined).length;
      return `<article class="model-card" data-model="${esc(model.id)}" tabindex="0" role="button" aria-label="查看 ${esc(model.name)} 详情"><div class="card-top"><div class="model-line"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><span><span class="model-name">${esc(model.name)}</span><span class="model-provider">${esc(model.provider)}</span></span></div><span class="card-score">${recorded}/${benchmarks.length}<small>reported</small></span></div><div class="mini-bars">${ranked.map(({ bench, entry }) => `<div class="mini-bar-row"><span>${esc(bench.short || bench.name)}</span><span class="mini-bar-track"><span style="width:${Math.min(100, Number(entry.value) / Number(bench.scale || 100) * 100)}%"></span></span><strong>${fmt(entry.value)}</strong></div>`).join("")}</div></article>`;
    }).join("");
  }

  function renderSpotlights() {
    const benchmarks = state.data.benchmarks || [];
    const models = state.data.models || [];
    const signals = benchmarks.map((bench) => {
      const values = models.map((model) => ({ model, entry: scoreEntry(model, bench.id) })).filter(({ entry }) => entry.value !== null && entry.value !== undefined).sort((a, b) => Number(b.entry.value) - Number(a.entry.value));
      return { bench, best: values[0], count: values.length };
    }).filter((signal) => signal.best).sort((a, b) => Number(b.best.entry.value) - Number(a.best.entry.value)).slice(0, 3);
    els.spotlightGrid.innerHTML = signals.map(({ bench, best, count }) => `<article class="spotlight-card"><span class="spotlight-kicker">${esc(bench.familyLabel || bench.family)} / ${esc(bench.short || bench.name)}</span><h3>${esc(best.model.name)}</h3><p><span class="spotlight-number">${fmt(best.entry.value)}${esc(bench.unit || "")}</span> · ${count}/${models.length} models have a recorded observation</p></article>`).join("");
  }

  function render() {
    renderStats(); renderActiveFilters(); renderMatrix(); renderCards(); renderSpotlights();
    els.matrixView.hidden = state.view !== "matrix";
    els.cardsView.hidden = state.view !== "cards";
    document.querySelectorAll(".view-tab").forEach((tab) => {
      const active = tab.dataset.view === state.view;
      tab.classList.toggle("active", active); tab.setAttribute("aria-selected", String(active));
    });
  }

  function modelById(id) { return (state.data.models || []).find((model) => model.id === id); }

  function openDrawer(modelId, benchmarkId = null) {
    const model = modelById(modelId);
    if (!model) return;
    state.selected = { modelId, benchmarkId };
    const benchmark = benchmarkId ? benchmarkFor(benchmarkId) : null;
    const entry = benchmark ? scoreEntry(model, benchmark.id) : null;
    const source = entry ? sourceFor(entry.sourceId) : null;
    const benchmarks = state.data.benchmarks || [];
    const recorded = benchmarks.map((bench) => ({ bench, entry: scoreEntry(model, bench.id) })).filter(({ entry: value }) => value.value !== null && value.value !== undefined).sort((a, b) => Number(b.entry.value) - Number(a.entry.value));
    const mainScore = entry || (recorded[0] ? recorded[0].entry : null);
    const mainBench = benchmark || (recorded[0] ? recorded[0].bench : null);
    const status = mainScore ? statusLabel(mainScore) : "未报告";
    els.drawerContent.innerHTML = `<div class="drawer-model-head"><span class="model-mark">${esc(model.mark || model.name.slice(0, 1))}</span><div><h3>${esc(model.name)}</h3><p>${esc(model.provider)} · release ${esc(model.release || "未注明")} · ${esc(model.access || "access 未注明")}</p></div></div>
      <div class="drawer-score"><span class="status-badge ${statusClass(mainScore)}">${esc(status)}</span><div class="big-score">${mainScore && mainScore.value !== null && mainScore.value !== undefined ? `${fmt(mainScore.value)}<small>${esc(mainBench?.unit || "")}</small>` : "—"}</div><p>${mainBench ? `${esc(mainBench.name)} · ${esc(mainScore.setting || "设置未说明")}` : "选择一个单元格查看具体 observation。"}</p></div>
      <section class="detail-section"><h4>Model note</h4><p class="detail-note">${esc(model.summary || "暂无模型说明。")}</p></section>
      <section class="detail-section"><h4>Protocol & provenance</h4><div class="detail-grid"><div class="detail-item"><label>Benchmark version</label><span>${esc(mainScore?.version || mainScore?.benchmark_version || mainBench?.version || "未注明")}</span></div><div class="detail-item"><label>Observed</label><span>${esc(mainScore?.observed || mainScore?.observed_at || state.data.meta?.asOf || "未注明")}</span></div><div class="detail-item"><label>Comparability</label><span>${esc(mainScore?.comparability || "conditional")}</span></div><div class="detail-item"><label>Evidence</label><span>${esc(mainScore?.evidenceLevel || mainScore?.evidence_level || (state.data.meta?.status === "demo" ? "demo" : "reported"))}</span></div></div>${mainScore?.note || mainScore?.notes ? `<p class="detail-note">${esc(mainScore.note || mainScore.notes)}</p>` : ""}</section>
      ${source ? `<section class="detail-section"><h4>Source</h4><a class="source-link" href="${esc(source.url)}" target="_blank" rel="noreferrer">↗ ${esc(source.label || source.title || source.url)}</a>${source.locator ? `<p class="detail-note">定位：${esc(source.locator)}</p>` : ""}</section>` : ""}
      <section class="detail-section"><h4>Recorded signals</h4><div class="timeline">${recorded.map(({ bench: itemBench, entry: itemEntry }) => `<div class="timeline-row"><span>${esc(itemBench.short || itemBench.name)}</span><span class="timeline-track"><i style="width:${Math.min(100, Number(itemEntry.value) / Number(itemBench.scale || 100) * 100)}%"></i></span><strong>${fmt(itemEntry.value)}${esc(itemBench.unit || "")}</strong></div>`).join("") || '<p class="detail-note">暂无可显示的成绩。</p>'}</div></section>
      <button class="copy-json" type="button" id="copyObservation">复制 observation JSON</button>`;
    els.drawerBackdrop.hidden = false;
    requestAnimationFrame(() => { els.drawer.classList.add("open"); els.drawer.setAttribute("aria-hidden", "false"); });
    const copyButton = $("copyObservation");
    if (copyButton) copyButton.addEventListener("click", () => copyObservation(model, benchmark));
  }

  function copyObservation(model, benchmark) {
    const payload = benchmark ? { model_id: model.id, benchmark_id: benchmark.id, ...scoreEntry(model, benchmark.id) } : model;
    const text = JSON.stringify(payload, null, 2);
    navigator.clipboard?.writeText(text).then(() => showToast("已复制 observation JSON")).catch(() => showToast("浏览器阻止了复制，请从 Data 打开"));
  }

  function closeDrawer() { els.drawer.classList.remove("open"); els.drawer.setAttribute("aria-hidden", "true"); setTimeout(() => { els.drawerBackdrop.hidden = true; }, 280); }
  function showToast(message) { els.toast.textContent = message; els.toast.classList.add("show"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => els.toast.classList.remove("show"), 2200); }

  function resetFilters() {
    state.search = ""; state.provider = "all"; state.family = "all"; state.sort = "coverage"; state.availableOnly = false;
    els.searchInput.value = ""; els.availableOnly.checked = false; renderFilters(); render();
  }

  function bind() {
    els.searchInput.addEventListener("input", (event) => { state.search = event.target.value; render(); });
    els.providerFilter.addEventListener("change", (event) => { state.provider = event.target.value; render(); });
    els.familyFilter.addEventListener("change", (event) => { state.family = event.target.value; render(); });
    els.sortSelect.addEventListener("change", (event) => { state.sort = event.target.value; render(); });
    els.availableOnly.addEventListener("change", (event) => { state.availableOnly = event.target.checked; render(); });
    $("resetFilters").addEventListener("click", resetFilters); $("emptyReset").addEventListener("click", resetFilters);
    document.querySelectorAll(".view-tab").forEach((tab) => tab.addEventListener("click", () => { state.view = tab.dataset.view; render(); }));
    document.addEventListener("click", (event) => {
      const cell = event.target.closest("[data-model][data-benchmark]");
      if (cell) return openDrawer(cell.dataset.model, cell.dataset.benchmark);
      const model = event.target.closest("[data-model]");
      if (model) openDrawer(model.dataset.model);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && document.activeElement !== els.searchInput) { event.preventDefault(); els.searchInput.focus(); }
      if (event.key === "Escape") closeDrawer();
      if (event.key === "Enter" && document.activeElement?.matches("[data-model]")) openDrawer(document.activeElement.dataset.model, document.activeElement.dataset.benchmark || null);
    });
    $("closeDrawer").addEventListener("click", closeDrawer); els.drawerBackdrop.addEventListener("click", closeDrawer);
    const themeButton = $("themeToggle");
    const savedTheme = localStorage.getItem("fmb-theme"); if (savedTheme === "light") document.documentElement.classList.add("light");
    themeButton.addEventListener("click", () => { const light = document.documentElement.classList.toggle("light"); localStorage.setItem("fmb-theme", light ? "light" : "dark"); themeButton.textContent = light ? "☾" : "☼"; });
    themeButton.textContent = document.documentElement.classList.contains("light") ? "☾" : "☼";
  }

  async function boot() {
    try {
      const response = await fetch("data/models.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
      renderFilters(); bind(); render();
    } catch (error) {
      console.error(error);
      els.footerStatus.textContent = "无法读取 data/models.json；请通过本地服务器打开。";
      els.matrixBody.innerHTML = `<tr><td colspan="99" class="empty-state"><h3>数据加载失败</h3><p>${esc(error.message)}</p></td></tr>`;
    }
  }

  boot();
})();
