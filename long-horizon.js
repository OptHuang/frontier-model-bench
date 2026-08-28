(() => {
  "use strict";

  const PATHS = {
    registry: "data/catalog/long_horizon.json",
    benchmarks: "data/catalog/benchmarks.json",
    harnesses: "data/catalog/harnesses.json",
  };

  const state = {
    registry: null,
    catalog: [],
    harnesses: [],
    benchmarks: [],
    agents: [],
    search: "",
    domain: "all",
    coverage: "all",
    tier: "all",
    horizon: "all",
    sort: "tier",
    selectedId: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    totalCount: $("totalCount"), canonicalCount: $("canonicalCount"), externalCount: $("externalCount"),
    missingCount: $("missingCount"), scienceCount: $("scienceCount"), visibleCount: $("visibleCount"),
    directoryCount: $("directoryCount"), agentCount: $("agentCount"), searchInput: $("searchInput"),
    domainFilter: $("domainFilter"), coverageFilter: $("coverageFilter"), tierFilter: $("tierFilter"),
    horizonFilter: $("horizonFilter"), sortFilter: $("sortFilter"), activeFilters: $("activeFilters"),
    domainRail: $("domainRail"), domainAllCount: $("domainAllCount"), benchmarkGrid: $("benchmarkGrid"),
    agentGrid: $("agentGrid"), emptyState: $("emptyState"), emptyReset: $("emptyReset"), resetFilters: $("resetFilters"),
    detailDrawer: $("detailDrawer"), drawerBackdrop: $("drawerBackdrop"), drawerContent: $("drawerContent"),
    closeDrawer: $("closeDrawer"), themeToggle: $("themeToggle"), footerStatus: $("footerStatus"), toast: $("toast"),
  };

  const DOMAIN_LABELS = {
    "scientific-research": "科学研究",
    "scientific-reproduction": "科学复现",
    "scientific-coding": "科学编程",
    "scientific-discovery": "科学发现",
    "scientific-software": "科学软件",
    "ml-engineering": "ML 工程",
    "terminal-agent": "终端 Agent",
    "software-engineering": "软件工程",
    "browser-agent": "浏览器 Agent",
    "computer-use": "电脑操作",
    "tool-agent": "工具 Agent",
    "information-seeking": "信息检索",
    "general-agent": "通用 Agent",
    "continual-learning": "持续学习",
    "professional-workflow": "专业工作流",
    "algorithm-engineering": "算法工程",
    "agent-system": "Agent 系统",
  };
  const HORIZON_LABELS = {
    "multi-turn": "多轮",
    "multi-step": "多步",
    "minutes-to-hours": "分钟–小时",
    "hours": "小时级",
    "hours-to-days": "小时–天",
    "12-to-24-hours": "12–24 小时",
    "90-minutes": "90 分钟",
    "days": "天级",
    "cross-session": "跨 session",
    "minutes-to-days": "分钟–天",
  };
  const ROLE_LABELS = {
    "origin-repository": "repo",
    "origin-paper": "paper",
    "origin-dataset": "dataset",
    "origin-project": "project",
    "official-leaderboard": "leaderboard",
    "historical-redirect": "redirect",
  };
  const STATUS_LABELS = { canonical: "本站 canonical", external: "外部 snapshot", missing: "待收录" };
  const TIER_RANK = { A: 0, B: 1, C: 2 };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  }

  function safeUrl(value) {
    try {
      const parsed = new URL(String(value || ""), window.location.href);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
    } catch (_error) {
      return "";
    }
  }

  function list(value) { return Array.isArray(value) ? value : []; }

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  }

  function catalogRows(payload) {
    if (Array.isArray(payload)) return payload;
    return list(payload?.benchmarks);
  }

  function coverageFor(item) {
    const ids = list(item.catalog_ids).map(String);
    if (ids.some((id) => state.catalog.some((row) => String(row.id) === id))) return "canonical";
    if (list(item.external_ids).length) return "external";
    return "missing";
  }

  function normalise(item, index) {
    const coverage = coverageFor(item);
    const domains = String(item.domain || "other");
    return {
      ...item,
      _index: index + 1,
      _coverage: coverage,
      _domainLabel: item.domain_label || DOMAIN_LABELS[domains] || domains,
      _horizonLabel: HORIZON_LABELS[item.horizon] || item.horizon || "未注明",
      _haystack: [item.id, item.name, ...list(item.aliases), item.domain, item.domain_label, item.summary, item.protocol, item.metric_label, item.task_count_label].join(" ").toLowerCase(),
    };
  }

  function taskValue(item) {
    return Number.isFinite(Number(item.task_count)) ? Number(item.task_count) : -1;
  }

  function visibleRows() {
    const query = state.search.trim().toLowerCase();
    const filtered = state.benchmarks.filter((item) => {
      if (query && !item._haystack.includes(query)) return false;
      if (state.domain !== "all" && item.domain !== state.domain) return false;
      if (state.coverage !== "all" && item._coverage !== state.coverage) return false;
      if (state.tier !== "all" && item.tier !== state.tier) return false;
      if (state.horizon !== "all" && item.horizon !== state.horizon) return false;
      return true;
    });
    return filtered.sort((a, b) => {
      if (state.sort === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "coverage") return ({ canonical: 0, external: 1, missing: 2 }[a._coverage] - ({ canonical: 0, external: 1, missing: 2 }[b._coverage])) || a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "tasks") return (taskValue(b) - taskValue(a)) || a.name.localeCompare(b.name, "zh-CN");
      if (state.sort === "sources") return (list(b.sources).length - list(a.sources).length) || a.name.localeCompare(b.name, "zh-CN");
      return ((TIER_RANK[a.tier] ?? 9) - (TIER_RANK[b.tier] ?? 9)) || ({ canonical: 0, external: 1, missing: 2 }[a._coverage] - ({ canonical: 0, external: 1, missing: 2 }[b._coverage])) || a.name.localeCompare(b.name, "zh-CN");
    });
  }

  function sourceMarkup(source, drawer = false) {
    const url = safeUrl(source?.url);
    if (!url) return "";
    const label = esc(source.label || "原始地址");
    const role = esc(ROLE_LABELS[source.role] || source.role || "source");
    const caution = source.link_status === "needs-recheck";
    const classes = `long-source-link${caution ? " needs-recheck" : ""}`;
    if (drawer) {
      return `<div class="long-drawer-source"><div><strong>${label}</strong><small>${role}${caution ? " · 待复核可访问性" : ""}</small></div><a class="${caution ? "needs-recheck" : ""}" href="${esc(url)}" target="_blank" rel="noreferrer noopener">打开 ↗</a></div>`;
    }
    return `<a class="${classes}" href="${esc(url)}" target="_blank" rel="noreferrer noopener" title="${esc(url)}"><span>${label}</span><small>${role}${caution ? " · ?" : ""}</small></a>`;
  }

  function statusMarkup(item) {
    const status = item._coverage;
    return `<span class="long-card-status ${status}"><span class="long-status-dot ${status}"></span>${STATUS_LABELS[status]}</span>`;
  }

  function renderStats() {
    const rows = state.benchmarks;
    const count = (status) => rows.filter((row) => row._coverage === status).length;
    const scienceDomains = new Set(["scientific-research", "scientific-reproduction", "scientific-coding", "scientific-discovery", "scientific-software"]);
    els.totalCount.textContent = rows.length;
    els.canonicalCount.textContent = count("canonical");
    els.externalCount.textContent = count("external");
    els.missingCount.textContent = count("missing");
    els.scienceCount.textContent = rows.filter((row) => scienceDomains.has(row.domain)).length;
    els.directoryCount.textContent = rows.length;
    els.agentCount.textContent = state.agents.length;
  }

  function optionMarkup(value, label) { return `<option value="${esc(value)}">${esc(label)}</option>`; }

  function renderFilterOptions() {
    const domains = [...new Set(state.benchmarks.map((row) => row.domain).filter(Boolean))].sort((a, b) => (DOMAIN_LABELS[a] || a).localeCompare(DOMAIN_LABELS[b] || b, "zh-CN"));
    const horizons = [...new Set(state.benchmarks.map((row) => row.horizon).filter(Boolean))];
    els.domainFilter.innerHTML = `<option value="all">所有领域</option>${domains.map((id) => optionMarkup(id, DOMAIN_LABELS[id] || id)).join("")}`;
    els.horizonFilter.innerHTML = `<option value="all">所有时间跨度</option>${horizons.map((id) => optionMarkup(id, HORIZON_LABELS[id] || id)).join("")}`;
    els.domainFilter.value = state.domain;
    els.horizonFilter.value = state.horizon;
    els.coverageFilter.value = state.coverage;
    els.tierFilter.value = state.tier;
    els.sortFilter.value = state.sort;
  }

  function renderDomainRail() {
    const counts = new Map();
    state.benchmarks.forEach((row) => counts.set(row.domain, (counts.get(row.domain) || 0) + 1));
    els.domainAllCount.textContent = state.benchmarks.length;
    els.domainRail.innerHTML = [...counts.entries()].sort((a, b) => (DOMAIN_LABELS[a[0]] || a[0]).localeCompare(DOMAIN_LABELS[b[0]] || b[0], "zh-CN")).map(([id, count]) => `<button class="long-domain-chip${state.domain === id ? " active" : ""}" type="button" data-domain="${esc(id)}"><span>${esc(DOMAIN_LABELS[id] || id)}</span><b>${count}</b></button>`).join("");
    document.querySelectorAll(".long-domain-chip[data-domain]").forEach((button) => {
      button.classList.toggle("active", button.dataset.domain === state.domain);
      button.addEventListener("click", () => { state.domain = button.dataset.domain; renderAll(); });
    });
  }

  function renderActiveFilters() {
    const tags = [];
    if (state.search) tags.push(`搜索：${state.search}`);
    if (state.domain !== "all") tags.push(`领域：${DOMAIN_LABELS[state.domain] || state.domain}`);
    if (state.coverage !== "all") tags.push(`状态：${STATUS_LABELS[state.coverage]}`);
    if (state.tier !== "all") tags.push(`Tier：${state.tier}`);
    if (state.horizon !== "all") tags.push(`跨度：${HORIZON_LABELS[state.horizon] || state.horizon}`);
    els.activeFilters.innerHTML = tags.map((tag) => `<span class="long-filter-tag">${esc(tag)}</span>`).join("");
  }

  function renderCard(item) {
    const aliases = list(item.aliases).filter(Boolean).slice(0, 2).join(" · ");
    const sourceRows = list(item.sources).slice(0, 4).map((source) => sourceMarkup(source)).join("");
    const catalogNames = list(item.catalog_ids).map((id) => state.catalog.find((row) => String(row.id) === String(id))?.name || id);
    const externalText = list(item.external_ids).length ? `外部：${list(item.external_ids).join(" · ")}` : "";
    return `<article class="long-benchmark-card is-${item._coverage}" tabindex="0" role="button" data-benchmark-id="${esc(item.id)}" aria-label="查看 ${esc(item.name)} 详情">
      <div class="long-card-top"><span class="long-card-index">${String(item._index).padStart(2, "0")}</span><span class="long-tier">TIER ${esc(item.tier || "?")}</span></div>
      <h3>${esc(item.name)}</h3><p class="long-card-alias">${esc(aliases || item.id)}</p>
      <div class="long-card-status-wrap">${statusMarkup(item)}</div>
      <p class="long-card-summary">${esc(item.summary || "暂无摘要")}</p>
      <div class="long-card-meta"><span><label>DOMAIN</label><strong>${esc(item._domainLabel)}</strong></span><span><label>HORIZON</label><strong>${esc(item._horizonLabel)}</strong></span><span><label>SCALE</label><strong>${esc(item.task_count_label || "版本化任务集")}</strong></span><span><label>METRIC</label><strong>${esc(item.metric_label || item.metric || "campaign-defined")}</strong></span></div>
      <p class="long-card-protocol" title="${esc(item.protocol || "")}">${esc(item.protocol || "协议说明待补")}</p>
      <div class="long-source-list"><span class="long-source-list-label">ORIGINAL SOURCES / 原始地址</span>${sourceRows || "<span class=\"card-empty-note\">未登记可访问的一手链接</span>"}</div>
      <div class="long-card-foot"><span>${esc(catalogNames.length ? `本站：${catalogNames.join(" · ")}` : externalText || "尚未进入本站 catalog")}</span><span class="open-label">详情 ↗</span></div>
    </article>`;
  }

  function renderCards() {
    const rows = visibleRows();
    els.visibleCount.textContent = rows.length;
    els.benchmarkGrid.innerHTML = rows.map(renderCard).join("");
    els.emptyState.hidden = rows.length !== 0;
    els.benchmarkGrid.hidden = rows.length === 0;
    els.benchmarkGrid.querySelectorAll("[data-benchmark-id]").forEach((card) => {
      const open = () => openDrawer(card.dataset.benchmarkId);
      card.addEventListener("click", open);
      card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
      // A source link is an action of its own; do not also open the card drawer
      // when a reader follows the project's original URL.
      card.querySelectorAll("a").forEach((link) => link.addEventListener("click", (event) => event.stopPropagation()));
    });
  }

  function renderAgents() {
    els.agentGrid.innerHTML = state.agents.map((agent) => {
      const links = list(agent.source_urls).map((url, index) => {
        const safe = safeUrl(url);
        return safe ? `<a href="${esc(safe)}" target="_blank" rel="noreferrer noopener" title="${esc(safe)}">${index === 0 ? "原始实现" : `补充地址 ${index + 1}`} ↗</a>` : "";
      }).join("");
      return `<article class="long-agent-card"><div class="long-agent-top"><h3>${esc(agent.name)}</h3><span class="long-agent-kind">${esc(agent.kind || "agent")}</span></div><p>${esc(agent.note || "具体结果需绑定 release、配置和 benchmark protocol。")}</p><div class="long-agent-sources">${links || "<span class=\"card-empty-note\">未登记原始地址</span>"}</div></article>`;
    }).join("");
  }

  function openDrawer(id) {
    const item = state.benchmarks.find((row) => row.id === id);
    if (!item) return;
    state.selectedId = id;
    const catalogNames = list(item.catalog_ids).map((entry) => state.catalog.find((row) => String(row.id) === String(entry))?.name || entry);
    const sourceRows = list(item.sources).map((source) => sourceMarkup(source, true)).join("");
    const discrepancy = item.count_note || "";
    els.drawerContent.innerHTML = `<div class="long-drawer-title-row"><div><h2 id="drawerTitle">${esc(item.name)}</h2><p>${esc(item._domainLabel)} · ${esc(item._horizonLabel)}</p></div><span class="long-drawer-id">${esc(item.id)}</span></div>
      <div class="long-drawer-tags">${statusMarkup(item)}<span class="long-drawer-tag">Tier ${esc(item.tier || "?")}</span><span class="long-drawer-tag">${esc(item.metric_label || item.metric || "campaign-defined")}</span></div>
      <p class="long-drawer-summary">${esc(item.summary || "暂无摘要")}</p>
      <section class="long-drawer-section"><h3>Definition / 任务口径</h3><div class="long-detail-grid"><div class="long-detail-item"><label>任务规模</label><strong>${esc(item.task_count_label || "版本化任务集")}</strong></div><div class="long-detail-item"><label>时间跨度</label><strong>${esc(item._horizonLabel)}</strong></div><div class="long-detail-item"><label>主指标</label><strong>${esc(item.metric_label || item.metric || "campaign-defined")}</strong></div><div class="long-detail-item"><label>本站映射</label><strong>${esc(catalogNames.length ? catalogNames.join(" · ") : "尚未登记 canonical profile")}</strong></div>${item.built_with ? `<div class="long-detail-item"><label>构建 / 运行框架</label><strong>${esc(item.built_with)}</strong></div>` : ""}</div></section>
      <section class="long-drawer-section"><h3>Protocol / 比较前提</h3><p class="long-drawer-text">${esc(item.protocol || "尚未提供统一协议说明。")}</p></section>
      ${discrepancy ? `<section class="long-drawer-section"><p class="long-guardrail">${esc(discrepancy)}</p></section>` : ""}
      <section class="long-drawer-section"><h3>Original sources / 原始地址</h3><div class="long-drawer-sources">${sourceRows || "<p class=\"long-drawer-text\">尚未登记可访问的一手链接。</p>"}</div></section>
      <section class="long-drawer-section"><p class="long-guardrail">覆盖状态只回答“本站是否登记了定义”。它不代表本站已经运行该 benchmark，也不代表存在可直接比较的成绩。${list(item.external_ids).length ? ` 外部快照：${esc(list(item.external_ids).join(" · "))}。` : ""}</p></section>`;
    els.drawerBackdrop.hidden = false;
    els.detailDrawer.classList.add("open");
    els.detailDrawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
    els.closeDrawer.focus();
  }

  function closeDrawer() {
    els.detailDrawer.classList.remove("open");
    els.detailDrawer.setAttribute("aria-hidden", "true");
    els.drawerBackdrop.hidden = true;
    document.body.classList.remove("drawer-open");
    state.selectedId = null;
  }

  function resetFilters() {
    state.search = ""; state.domain = "all"; state.coverage = "all"; state.tier = "all"; state.horizon = "all"; state.sort = "tier";
    els.searchInput.value = "";
    renderAll();
  }

  function renderAll() {
    renderFilterOptions();
    renderDomainRail();
    renderActiveFilters();
    renderCards();
  }

  function showError(error) {
    els.benchmarkGrid.innerHTML = `<div class="long-empty"><span class="empty-icon">!</span><h3>目录暂时无法加载</h3><p>${esc(error?.message || "请通过静态服务器打开此页面。")}</p></div>`;
    els.benchmarkGrid.hidden = false;
    els.emptyState.hidden = true;
    els.footerStatus.textContent = "数据加载失败；请检查 data/catalog/long_horizon.json。";
  }

  function setupTheme() {
    let saved = "";
    try { saved = localStorage.getItem("fmb-theme") || ""; } catch (_error) { /* private browsing */ }
    if (saved === "light") document.documentElement.classList.add("light");
    els.themeToggle.addEventListener("click", () => {
      const light = document.documentElement.classList.toggle("light");
      try { localStorage.setItem("fmb-theme", light ? "light" : "dark"); } catch (_error) { /* no-op */ }
    });
  }

  function setupEvents() {
    els.searchInput.addEventListener("input", (event) => { state.search = event.target.value; renderCards(); renderActiveFilters(); });
    els.domainFilter.addEventListener("change", (event) => { state.domain = event.target.value; renderAll(); });
    els.coverageFilter.addEventListener("change", (event) => { state.coverage = event.target.value; renderCards(); renderActiveFilters(); });
    els.tierFilter.addEventListener("change", (event) => { state.tier = event.target.value; renderCards(); renderActiveFilters(); });
    els.horizonFilter.addEventListener("change", (event) => { state.horizon = event.target.value; renderCards(); renderActiveFilters(); });
    els.sortFilter.addEventListener("change", (event) => { state.sort = event.target.value; renderCards(); });
    els.resetFilters.addEventListener("click", resetFilters);
    els.emptyReset.addEventListener("click", resetFilters);
    els.closeDrawer.addEventListener("click", closeDrawer);
    els.drawerBackdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !els.drawerBackdrop.hidden) closeDrawer();
      if (event.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { event.preventDefault(); els.searchInput.focus(); }
    });
  }

  async function init() {
    setupTheme();
    setupEvents();
    try {
      const [registry, catalog, harnesses] = await Promise.all([loadJson(PATHS.registry), loadJson(PATHS.benchmarks), loadJson(PATHS.harnesses)]);
      state.registry = registry;
      state.catalog = catalogRows(catalog);
      state.harnesses = Array.isArray(harnesses) ? harnesses : list(harnesses?.harnesses);
      state.benchmarks = list(registry?.benchmarks).map(normalise);
      state.agents = list(registry?.agents);
      renderStats();
      renderAgents();
      renderAll();
      els.footerStatus.textContent = `${registry?.meta?.as_of || "2026-08-28"} snapshot · ${state.benchmarks.length} 条 benchmark · 原始地址逐条保留。`;
    } catch (error) {
      showError(error);
    }
  }

  init();
})();
