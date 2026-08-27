(() => {
  "use strict";

  const DATA_PATHS = ["data/derived/site.json", "data/catalog/benchmarks.json"];
  const state = {
    data: null,
    benchmarks: [],
    sources: [],
    publicCounts: {},
    runs: [],
    search: "",
    category: "all",
    mode: "all",
    metric: "all",
    family: "all",
    sort: "featured",
    featuredOnly: false,
    includePublic: true,
    canonicalCount: 0,
    publicOnlyCount: 0,
    selectedId: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    catalogCount: $("catalogCount"), familyCount: $("familyCount"), sourceCount: $("sourceCount"),
    activeVersionCount: $("activeVersionCount"), visibleCount: $("visibleCount"), totalCount: $("totalCount"),
    familyAllCount: $("familyAllCount"), familyRail: $("familyRail"), benchmarkGrid: $("benchmarkGrid"),
    emptyState: $("emptyState"), benchSearch: $("benchSearch"), categoryFilter: $("categoryFilter"),
    modeFilter: $("modeFilter"), metricFilter: $("metricFilter"), sortFilter: $("sortFilter"),
    featuredOnly: $("featuredOnly"), includePublic: $("includePublic"), activeFilters: $("activeFilters"), resetFilters: $("resetFilters"),
    emptyReset: $("emptyReset"), detailDrawer: $("detailDrawer"), drawerBackdrop: $("drawerBackdrop"),
    drawerContent: $("drawerContent"), closeDrawer: $("closeDrawer"), themeToggle: $("themeToggle"),
    catalogFreshness: $("catalogFreshness"), catalogNote: $("catalogNote"), footerStatus: $("footerStatus"), toast: $("toast"),
  };

  const CATEGORY_LABELS = {
    reasoning: "推理", math: "数学", knowledge: "知识", reliability: "事实性", coding: "代码",
    "coding-agent": "代码 Agent", "tool-use": "工具调用", "knowledge-work": "知识工作",
    multimodal: "多模态", "computer-use": "电脑操作", "long-context": "长上下文", chinese: "中文",
    multilingual: "多语言", cyber: "网络安全", preference: "人类偏好", agents: "Agent / 工具",
    arena: "Arena / 偏好", retrieval: "长上下文 / 检索", "agent-workflow": "Agent 工作流",
    "algorithm-engineering": "算法工程", "browsing-agent": "浏览 Agent", "ml-engineering": "ML 工程",
  };
  const MODE_LABELS = {
    direct: "模型 / 直接评测", model: "模型 / 直接评测", system: "系统 / harness 评测",
    preference: "人类偏好竞技", arena: "Arena / pairwise", hybrid: "混合 / tool protocol", unknown: "口径待补",
  };
  const METRIC_LABELS = {
    accuracy: "准确率", "pass@1": "Pass@1", resolved: "Resolved", pass_rate: "Pass rate",
    pass: "Pass", "pass^k": "Pass^k", avg_score: "Average score", "arena-rating": "Arena rating",
    success: "Success", elo: "Elo", ips: "IPS score", performance: "Performance", rank: "Rank",
  };

  /* These notes are intentionally short, but richer than the catalog's one-line
     description. They explain what a score means and what can invalidate a
     comparison. A new benchmark can still use the category fallback below. */
  const BENCHMARK_NOTES = {
    "gpqa-diamond": ["专家编写的研究生级生物、物理、化学问答，重点看知识迁移和多步推理。", "题目难度高且样本较小；报告 subject expertise、提示词和是否允许外部检索。"],
    "aime-2025": ["AIME 2025 数学竞赛题，答案为 0–999 的整数，适合观察精确解题能力。", "pass@1、best-of-n、工具和答案抽取会显著改变结果；年份之间不要混合。"],
    "aime-2026": ["AIME 2026 新题窗口，较适合追踪最新模型在竞赛数学上的即时能力。", "需要固定题集版本、截止日期、采样预算和是否使用 Python；公开 API 行可能仍在更新。"],
    frontiermath: ["由 Epoch AI 组织的前沿数学题，按难度层级覆盖普通模型很少触及的区域。", "T1–T3 与 T4 是不同难度切片；题目窗口、污染控制和 judge 设置必须一起读。"],
    hmmt: ["HMMT 数学竞赛题，覆盖代数、几何、组合与数论，常用于高阶数学能力对比。", "年份、赛季、avg@k / pass@1 不是同一个指标；不要把多次采样分数当成单次准确率。"],
    "mmlu-pro": ["更高难度的多学科选择题，减少简单模式匹配和提示泄漏。", "类别平均与总体平均的权重可能不同；shot、选项顺序和污染策略需保持一致。"],
    hle: ["跨学科专家级问题，覆盖文本、图像和工具辅助的知识推理。", "text、vision、tools 和 judge track 不可直接合并；低分并不等于模型在常规知识问答上弱。"],
    simpleqa: ["短事实问答，主要测模型是否给出正确、简洁且可核验的事实。", "除了 accuracy，还应关注拒答率、校准和知识截止日期；搜索工具会改变任务定义。"],
    "swebench-verified": ["从真实 GitHub issue 到可运行补丁的端到端软件工程评测。", "结果是模型、上下文、工具、预算、补丁筛选和 harness 的联合产物；Resolved 不是裸模型分数。"],
    "swebench-pro": ["更难、更加接近真实软件维护的 issue 集合，强调长上下文和仓库级修改。", "不同任务版本、测试修复策略和 agent scaffold 会造成很大差异；优先比较同一 harness。"],
    livecodebench: ["按时间滚动收集竞赛编程题，带有污染控制，观察模型对新题的代码生成能力。", "V5/V6、时间窗口、语言、pass@1 与采样策略不能混合；榜单更新也可能回填历史模型。"],
    deepswe: ["面向软件工程 Agent 的任务集，强调仓库理解、修改和测试闭环。", "应同时记录 rollout 数、timeout、工具权限和修复判定；系统分数不应标成模型-only。"],
    nl2repo: ["从自然语言需求生成仓库级实现，测试需求理解、规划和跨文件编码。", "反作弊、隐藏测试和仓库快照决定难度；不同 scaffold 的结果只做 conditional comparison。"],
    "terminal-bench": ["在隔离终端环境中完成真实工程任务，关注长程执行、调试与环境操作。", "Terminal-Bench 版本、镜像、工具权限、timeout 和 harness 是结果的一部分。"],
    bfcl: ["Berkeley Function Calling Leaderboard，覆盖单轮、多轮、并行和复杂函数调用。", "native function calling、prompt workaround、工具 schema 和 evaluator 版本必须分开；overall 是子类聚合，不是通用知识分。"],
    "tau-bench": ["模拟用户、Agent 与业务工具的交互，考察策略遵循和任务完成可靠性。", "pass^k 比单次 pass 更能体现稳定性；领域、工具状态和对话预算必须固定。"],
    toolathlon: ["跨多个真实工具的长程任务，衡量规划、调用和错误恢复的综合能力。", "工具集合、权限、预算、环境状态和成功判定器都要记录；不同版本不可直接排位。"],
    "gdpval-aa": ["知识工作任务的 pairwise 人类或模型评审，输出 Elo / preference rating。", "Elo 反映相对偏好，不是准确率；评审池、任务类别和置信区间比小数点更重要。"],
    mmmu: ["大学级多学科图文理解，覆盖自然科学、社会科学和专业知识。", "图像分辨率、OCR、选项顺序与工具会改变结果；原版与 Pro 必须分开。"],
    "mmmu-pro": ["MMMU 的更难变体，要求更强的视觉解析和跨学科推理。", "需注明题型、图像输入、工具和答案抽取；不能与原版分数直接平均。"],
    mathvista: ["视觉数学推理，结合图表、几何图形和自然语言问题。", "分辨率、OCR、视觉编码器和计算器工具是关键协变量；accuracy 只代表指定设置。"],
    "video-mme": ["长短视频理解评测，覆盖字幕、音频、事件和时序推理。", "视频时长、帧采样、音频开关和上下文预算需要一起披露。"],
    osworld: ["在真实桌面和浏览器环境中完成多步电脑操作，测感知、规划与执行。", "操作系统镜像、分辨率、浏览器状态、截图频率和执行器决定可比性。"],
    ruler: ["RULER 用合成和半合成长上下文任务，画出随 context length 变化的检索/推理曲线。", "不要只看单点平均；context bucket、位置分布和最大 token 需要与曲线一起报告。"],
    longbench: ["多任务长文本理解，覆盖摘要、问答、代码和跨文档检索。", "语言、上下文长度、截断方式和检索策略会改变难度；v1/v2 不是同一测试。"],
    ceval: ["中文多学科选择题，覆盖基础教育到专业知识领域。", "shot、prompt、语言和学科权重需保持一致；与 CMMLU、SuperCLUE 的任务定义不同。"],
    cmmlu: ["中文知识与推理评测，覆盖生活常识、专业学科和社会科学。", "应保留语言、subject split 和 few-shot 设置；总体均值可能掩盖学科差异。"],
    superclue: ["中文偏好竞技榜，通过 pairwise 比较汇总为 Arena Elo。", "Elo 受对手池、时间窗口和投票分布影响，不应当作客观准确率。"],
    mmmlu: ["多语言 MMLU，按语言切片衡量跨语言知识迁移和推理。", "整体平均会掩盖低资源语言表现；语言版本、翻译策略和 prompt 必须标注。"],
    cybergym: ["网络安全任务，涵盖漏洞发现、分析与利用，强调工具和权限下的闭环。", "发现、利用、修复是不同能力；沙箱网络、工具权限与安全策略不可省略。"],
    "arena-text": ["文本对话 Arena 的 Bradley–Terry / Elo 偏好评分，反映真实用户选择。", "它是相对偏好而非标准答案；category、投票量、时间窗口和置信区间决定解释范围。"],
    "arena-vision": ["图文交互 Arena，比较模型在视觉问答、理解和生成式请求中的用户偏好。", "必须与 Text Arena 分开；图片类型、投票池和模型 endpoint 可能随快照变化。"],
    "arena-webdev": ["WebDev Arena 让用户比较模型生成网页/应用的实际观感和可用性。", "模型名可能包含 endpoint、effort 或 scaffold；不能把网页构建 Elo 当作通用代码分。"],
    "arena-search": ["带搜索工具的 Arena，观察模型在检索、引用和综合回答上的实际偏好。", "搜索引擎、工具调用次数、时效和 citation policy 都是系统条件。"],
    "arena-document": ["文档理解 Arena，比较模型处理长文档、表格和版面信息的用户体验。", "文档类型、解析器、上下文长度和视觉输入必须固定；保留投票量和置信区间。"],
    "arena-agent": ["Agent Arena 的系统级 IPS 指标，面向多步任务的效率与成功表现。", "IPS 不是 Bradley–Terry Elo；必须记录 agent scaffold、工具、任务集和预算。"],
    "agents-last-exam": ["Agents’ Last Exam（ALE-V1）评测真实职业工作流中的长程 Agent 系统。", "每条结果是 Agent × harness × environment × task；full、near-term、last-exam 和 licensed/unlicensed split 不能混合。"],
    "ale-bench": ["SakanaAI ALE-Bench 面向 AtCoder Heuristic Contest 的长程算法工程和优化。", "它输出 performance / rank，通常没有已知精确解；与 Agents’ Last Exam 或 pass/fail coding benchmark 完全不同。"],
    browsecomp: ["BrowseComp 需要多步网页检索、证据拼接和最终事实判断，专门测 browsing Agent。", "搜索工具、浏览预算、effort、网页快照和答案验证器会改变结果；目前不假定有稳定 API。"],
    "aider-polyglot": ["Aider Polyglot 用多语言代码编辑任务测试模型在真实编辑器工作流中的完成率。", "edit format、repo/task snapshot、endpoint、temperature 和 patch 应用方式需一并记录。"],
    androidworld: ["AndroidWorld 在 Android emulator 中执行真实应用任务，覆盖点击、输入、导航和状态判断。", "设备镜像、应用版本、屏幕尺寸、执行器和任务版本是系统协议；成功率不能脱离环境。"],
    "mle-bench": ["MLE-bench 把 Kaggle 机器学习竞赛改造成可审计的 ML engineering Agent 任务。", "Lite/Medium/High/All、GPU/时间预算、提交分数和 grader track 需分开，不能与普通代码 pass@1 合并。"],
    livebench: ["LiveBench 按日期滚动发布题目和子任务，覆盖数学、代码、推理、语言与数据分析，重点降低静态题库污染。", "比较时必须固定 release date、task/category、judge 与模型 endpoint；总分和 23 个子任务切片不能互相替代。"],
    "epoch-arc_agi_2_external": ["ARC-AGI-2 通过抽象视觉网格转换任务衡量从少量示例归纳新规则的能力；这里展示 Epoch 汇总的外部公开记录。", "官方提交、第三方 harness、工具/采样预算和 private evaluation 可能不同；不要把 ARC-AGI-1 与 ARC-AGI-2 合并。"],
    "epoch-frontiermath_tier_4": ["FrontierMath Tier 4 是比 T1–T3 更高难度的独立切片；这里保留 Epoch 来源中的原始公开行。", "题目可见性、版本窗口、工具和 judge 条件必须一致；T4 分数不能与 T1–T3 直接平均。"],
    "epoch-bbh_external": ["BIG-Bench Hard（BBH）汇集 23 个对早期模型较难的推理任务；这里是 Epoch 汇总的外部结果。", "CoT、few-shot、任务平均方式和答案解析会显著改变结果；旧题污染风险也应纳入解读。"],
    "helm-ifeval": ["IFEval 用可自动验证的显式指令约束检查模型是否真正遵循格式、数量、关键词和结构要求。", "prompt-level 与 instruction-level accuracy、strict/loose evaluator、HELM release 和解码设置必须分开。"],
    "helm-math": ["HELM 的 MATH 切片覆盖竞赛数学问题与 exact/equivalence grader，用于比较结构化数学推理。", "MATH 原版、MATH-500、不同 shot/CoT 与等价判定器不是同一协议；需查看 HELM table 和 release。"],
    "helm-mmlu": ["HELM 的 MMLU 切片覆盖多学科选择题，并同时公开准确率、效率和一般信息字段。", "只比较同一 HELM release、shot、subject aggregation 与 Accuracy table；token、runtime、样本数不应进入性能分数矩阵。"],
    "helm-gsm8k": ["HELM 的 GSM8K 切片测小学数学文字题的多步算术推理。", "exact match、CoT、shot、答案抽取和 HELM release 必须固定；效率/样本计数属于 telemetry。"],
    "swebench-lite": ["SWE-bench Lite 是从真实 GitHub issue 精简出的较小软件工程任务集，仍然是模型与 agent harness 的联合评测。", "Lite、Verified、Pro、Multilingual 与不同 harness/timeout 不可混排；Resolved 必须保留仓库快照和测试策略。"],
    "swebench-multilingual": ["SWE-bench Multilingual 扩展到多语言代码仓库和生态，衡量跨语言 issue 修复。", "语言/仓库构成、镜像、测试和 agent scaffold 都影响结果；不要与英文 Verified 总分直接平均。"],
    "swebench-multimodal": ["SWE-bench Multimodal 把截图、界面或其他视觉信息加入真实 issue 修复任务。", "视觉输入管线、分辨率、浏览器/GUI 工具和 harness 是协议组成部分；不能当作纯文本模型成绩。"],
  };

  const CATEGORY_FALLBACK = {
    math: ["竞赛或研究数学题，观察精确推导、搜索与验证能力。", "题目年份、采样预算、工具和答案抽取通常是首要比较条件。"],
    coding: ["代码生成或工程任务，关注从需求到可执行结果的闭环。", "语言、测试集、工具和执行预算必须对齐。"],
    agents: ["多步 Agent 任务，模型能力之外还包含工具、环境和 harness。", "应把系统条件与模型 release 一起记录，不将其当作裸模型成绩。"],
    multimodal: ["涉及图像、视频或文档输入的综合理解任务。", "输入预处理、分辨率、采样和工具设置会改变结果。"],
    multilingual: ["跨语言知识、理解或偏好任务。", "语言切片和翻译/提示策略比总体平均更有解释力。"],
    arena: ["通过 pairwise 人类偏好聚合的竞技型评测。", "Elo 是相对指标，时间窗口、投票池和置信区间不可省略。"],
  };

  // The canonical catalog is intentionally curated, while public adapters
  // often expose additional dated suites or metric slices (for example
  // HELM/LiveBench/Epoch rows).  Build lightweight, explicitly public-only
  // directory entries from those rows so the Benchmarks page does not hide
  // evidence merely because a maintainer has not yet promoted a definition
  // into the canonical registry.
  function publicSliceCategory(id) {
    const value = String(id || "").toLowerCase();
    if (value.includes("arena")) return value.includes("agent") || value.includes("web") || value.includes("search") ? "agent-workflow" : "preference";
    if (value.includes("swe") || value.includes("code") || value.includes("terminal") || value.includes("aider") || value.includes("cyber")) return "coding-agent";
    if (value.includes("math") || value.includes("aime") || value.includes("hmmt") || value.includes("gpqa")) return "math";
    if (value.includes("mmlu") || value.includes("qa") || value.includes("knowledge")) return "knowledge";
    if (value.includes("helm")) return "knowledge-work";
    if (value.includes("vision") || value.includes("video") || value.includes("mmmu")) return "multimodal";
    if (value.includes("tool") || value.includes("function") || value.includes("bfcl")) return "tool-use";
    return value.startsWith("epoch-") ? "knowledge-work" : "other";
  }

  function publicSliceMode(id, rows) {
    const value = String(id || "").toLowerCase();
    if (value.includes("arena") && !value.includes("agent") && !value.includes("web") && !value.includes("search")) return "preference";
    const hasSystem = rows.some((row) => String(first(row.subjectType, row.subject_type, row.protocol?.subject_type, "")).toLowerCase() === "system");
    return hasSystem || ["coding-agent", "tool-use", "agent-workflow", "browsing-agent", "ml-engineering"].includes(publicSliceCategory(id)) ? "system" : "direct";
  }

  function publicSliceProfile(id, name, rows, sourceLabel) {
    const metrics = [...new Set(rows.map((row) => first(row.metricId, row.metric_id, row.metric)).filter(Boolean).map(String))];
    const versions = [...new Set(rows.map((row) => first(row.benchmarkVersionId, row.benchmark_version_id, row.benchmarkVersion, row.version)).filter(Boolean).map(String))];
    const harnesses = [...new Set(rows.map((row) => first(row.harnessId, row.harness_id, row.harness, row.protocol?.harness)).filter(Boolean).map(String))];
    const subject = publicSliceMode(id, rows);
    const lowerId = String(id || "").toLowerCase();
    const aleNote = lowerId.includes("ale_bench") || lowerId.includes("ale-bench")
      ? "该来源切片的命名含 ale_bench；不等同于 SakanaAI ALE-Bench、Agents' Last Exam (ALE-V1) 或 Atari ALE。"
      : lowerId.includes("agents-last-exam")
        ? "这是 Agents' Last Exam (ALE-V1) 系统评测；不等同于 SakanaAI ALE-Bench 或 Atari ALE。"
        : "";
    return {
      task: {
        summary: `公开来源中的「${name}」切片；此条目用于索引已发布的榜单记录，不表示本站重新运行了该 benchmark。${aleNote ? ` ${aleNote}` : ""}`,
        input: "来源榜单 / 模型卡中的公开行",
        output: metrics.length ? `来源指标：${metrics.join("、")}` : "来源报告的分数或排名",
      },
      dataset: {
        size: `${rows.length} 条已收录公开记录`,
        splits: versions.length ? versions.join(" · ") : "版本由来源行决定，未统一归并",
        availability: "公开快照；定义与题集以来源页面为准",
      },
      protocol: {
        mode: subject === "system" ? "系统 / harness 或工具流程" : subject === "preference" ? "pairwise / 偏好聚合" : "模型直接评测",
        grader: "来源自带 evaluator、投票聚合或 judge；本站未独立复核",
        tools: harnesses.length ? `来源 harness：${harnesses.join(" · ")}` : "工具 / harness 未在全部来源行注明",
        sampling: "保留来源 metric、版本、日期和 locator；不跨来源重算总分",
      },
      comparison: {
        recommended: "只与相同 source、版本、metric、模型身份和 protocol 的行比较。",
        avoid: `不要把 public-only slice 当作 canonical 定义，也不要与同名但不同版本的 benchmark 合并。${aleNote ? ` ${aleNote}` : ""}`,
      },
      source_locator: first(rows[0]?.sourceLocator, rows[0]?.locator, "public evidence rows; see source URL and locator"),
    };
  }

  function buildPublicSliceEntries(data, canonicalIds) {
    const rows = Array.isArray(data?.publicEvidence) ? data.publicEvidence : [];
    const groups = new Map();
    rows.forEach((row) => {
      if (!row || typeof row !== "object") return;
      const id = String(first(row.displayBenchmarkId, row.display_benchmark_id, row.benchmarkId, row.benchmark_id, "")).trim();
      if (!id || canonicalIds.has(id)) return;
      const group = groups.get(id) || [];
      group.push(row);
      groups.set(id, group);
    });
    return [...groups.entries()].map(([id, group]) => {
      const firstRow = group[0] || {};
      const name = String(first(firstRow.sourceBenchmark, firstRow.source_benchmark, firstRow.benchmarkName, firstRow.benchmark_name, id));
      const metrics = [...new Set(group.map((row) => first(row.metricId, row.metric_id, row.metric)).filter(Boolean).map(String))];
      const units = [...new Set(group.map((row) => first(row.unit, row.displayUnit, "%")).filter(Boolean).map(String))];
      const versions = [...new Set(group.map((row) => first(row.benchmarkVersionId, row.benchmark_version_id, row.benchmarkVersion, row.version)).filter(Boolean).map(String))];
      const sourceIds = [...new Set(group.map((row) => first(row.sourceId, row.source_id)).filter(Boolean).map(String))];
      const sourceRows = [];
      const seenUrls = new Set();
      group.forEach((row) => {
        const page = firstSafeUrl(row.sourcePageUrl, row.source_page_url);
        const endpoint = firstSafeUrl(row.sourceUrl, row.source_url, row.evidenceUrl, row.evidence_url);
        const url = page || endpoint;
        if (!url || seenUrls.has(url)) return;
        seenUrls.add(url);
        sourceRows.push({
          id: first(row.sourceId, row.source_id, `public-${sourceRows.length}`),
          label: first(row.sourceLabel, row.source_label, row.sourceId, "公开来源"),
          url: page || endpoint,
          web_url: page || undefined,
          api_url: endpoint && endpoint !== page ? endpoint : undefined,
        });
      });
      const category = publicSliceCategory(id);
      const mode = publicSliceMode(id, group);
      const sourceLabel = first(firstRow.sourceLabel, firstRow.source_label, sourceIds[0], "公开来源");
      return {
        id,
        canonicalId: id,
        short: name === id ? id.replace(/^epoch-/, "Epoch · ").replace(/[-_]+/g, " ") : name,
        name,
        family: category,
        category,
        familyLabel: categoryLabel(category),
        evaluationMode: mode,
        metric: metrics[0] || "score",
        metricLabel: metrics[0] || "score",
        metrics: metrics.map((metric) => ({ id: metric, label: METRIC_LABELS[metric] || metric, unit: units[0] || "%", direction: metric === "rank" ? "lower" : "higher" })),
        unit: units[0] || "%",
        scale: units[0] === "fraction" ? { min: 0, max: 1 } : units[0] === "%" || !units.length ? 100 : null,
        direction: metrics.some((metric) => metric === "rank") ? "lower" : "higher",
        version: versions[0] || "public snapshot",
        versionId: versions[0] || null,
        defaultVersionId: versions[0] || null,
        description: `公开来源切片：${name}。页面直接索引来源报告值，全部标记为「披露 · 未复现」。`,
        owner: sourceLabel,
        sourceIds,
        source: sourceRows[0]?.url || first(firstRow.sourceUrl, firstRow.evidenceUrl),
        sourceLabel,
        _publicSources: sourceRows,
        _publicRows: group,
        publicOnly: true,
        publicReported: true,
        featured: false,
        tags: ["公开切片", "reported-only", sourceLabel],
        profile: publicSliceProfile(id, name, group, sourceLabel),
      };
    }).sort((a, b) => String(a.name).localeCompare(String(b.name), "zh"));
  }

  const first = (...values) => values.find((v) => v !== undefined && v !== null && v !== "");
  const arr = (v) => Array.isArray(v) ? v : (v === undefined || v === null ? [] : [v]);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
  const text = (v, fallback = "—") => v === undefined || v === null || v === "" ? fallback : String(v);
  const number = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
  const fmt = (v) => { const n = number(v); return n === null ? text(v) : Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, ""); };
  const slug = (v) => text(v, "unknown").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "-").replace(/^-+|-+$/g, "") || "unknown";
  // Source URLs are snapshot data and may be edited independently of the
  // renderer.  Accept only absolute HTTP(S) URLs so a malformed or alternate
  // scheme can never become an active link in the detail drawer.
  const safeUrl = (v) => {
    const raw = String(v ?? "").trim();
    if (!/^https?:\/\//i.test(raw)) return "";
    try {
      const parsed = new URL(raw);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? raw : "";
    } catch (_error) {
      return "";
    }
  };

  // Try candidates independently so a malformed preferred field cannot hide
  // a valid page/API URL supplied later in the same source record.
  const firstSafeUrl = (...values) => {
    for (const value of values) {
      const url = safeUrl(value);
      if (url) return url;
    }
    return "";
  };

  function categoryLabel(value) { return CATEGORY_LABELS[value] || text(value, "其它"); }
  function modeOf(bench) {
    const explicit = first(bench.evaluationMode, bench.evaluation_mode, bench.mode);
    if (explicit) return String(explicit).toLowerCase();
    if (["preference"].includes(bench.category)) return "preference";
    if (String(bench.family || "").toLowerCase() === "arena") return bench.id === "arena-agent" ? "system" : "preference";
    if (["coding-agent", "tool-use", "computer-use", "agent-workflow", "browsing-agent", "ml-engineering"].includes(bench.category)) return "system";
    return "direct";
  }
  function modeLabel(value) { return MODE_LABELS[value] || text(value, "口径待补"); }
  function metricList(bench) {
    const values = arr(bench.metrics || bench.metricDefinitions);
    if (values.length) return values.map((m) => typeof m === "string" ? { id: m, label: METRIC_LABELS[m] || m, unit: bench.unit, direction: bench.direction } : {
      id: first(m.id, m.metric, m.name), label: first(m.label, m.metricLabel, METRIC_LABELS[m.id], m.id), unit: first(m.unit, bench.unit), direction: first(m.direction, bench.direction), scale: m.scale,
    });
    return [{ id: first(bench.metric, bench.defaultMetricId), label: first(bench.metricLabel, METRIC_LABELS[bench.metric], bench.metric), unit: bench.unit, direction: bench.direction, scale: bench.scale ? { min: 0, max: bench.scale } : null }];
  }
  function metricLabel(bench) { const m = metricList(bench)[0] || {}; return text(first(m.label, bench.metricLabel, bench.metric), "未注明"); }
  function versionList(bench) {
    const values = arr(bench.versions || bench.version);
    if (!values.length) return [{ id: first(bench.defaultVersionId, bench.default_version_id), label: first(bench.version, bench.defaultVersionId), status: "active" }];
    return values.map((v) => typeof v === "string" ? { id: v, label: v, status: "active" } : { id: first(v.id, v.version), label: first(v.label, v.name, v.id), status: first(v.status, "active") });
  }
  function familyOf(bench) { return first(bench.family, bench.familyLabel, bench.category, "other"); }
  function familyLabel(bench) { return first(bench.familyLabel, bench.family_label, CATEGORY_LABELS[bench.family], categoryLabel(bench.category)); }
  function detailsFor(bench) {
    const note = BENCHMARK_NOTES[bench.id];
    const profile = profileOf(bench);
    const profileTask = profile.task && typeof profile.task === "object" ? profile.task.summary : "";
    const profileAvoid = profile.comparison && typeof profile.comparison === "object" ? profile.comparison.avoid : "";
    if (profileTask || profileAvoid) {
      return {
        focus: first(profileTask, note && note[0], bench.description, "该 benchmark 的任务定义与公开协议见来源页面。"),
        guardrail: first(profileAvoid, note && note[1], "比较前请固定版本、指标、数据切分、工具和评测器。"),
      };
    }
    if (note) return { focus: note[0], guardrail: note[1] };
    const fallback = CATEGORY_FALLBACK[bench.family] || CATEGORY_FALLBACK[bench.category] || [text(bench.description, "该 benchmark 的任务定义与公开协议见来源页面。"), "比较前请固定版本、指标、数据切分、工具和评测器。"];
    return { focus: fallback[0], guardrail: fallback[1] };
  }

  function profileOf(bench) {
    return bench && bench.profile && typeof bench.profile === "object" ? bench.profile : {};
  }
  function profileField(value) {
    if (Array.isArray(value)) return value.filter((item) => item !== undefined && item !== null && item !== "").join(" · ");
    if (value && typeof value === "object") return Object.values(value).filter((item) => item !== undefined && item !== null && item !== "").join(" · ");
    return text(value, "未注明");
  }
  function renderProfileGroup(bench, title, profileKey, labels) {
    const group = profileOf(bench)[profileKey];
    if (!group || typeof group !== "object") return "";
    const rows = labels.map(([key, label, wide]) => {
      const value = group[key];
      if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) return "";
      return `<div class="bench-profile-item${wide ? " wide" : ""}"><label>${esc(label)}</label><p>${esc(profileField(value))}</p></div>`;
    }).filter(Boolean).join("");
    return rows ? `<section class="bench-drawer-section bench-profile-section"><h3>${esc(title)}</h3><div class="bench-profile-grid">${rows}</div></section>` : "";
  }

  async function loadJson(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${response.status} ${path}`);
    return response.json();
  }

  async function loadData() {
    let data;
    let loadedPath = DATA_PATHS[0];
    for (const path of DATA_PATHS) {
      try { data = await loadJson(path); loadedPath = path; break; } catch (error) { /* try the next static fallback */ }
    }
    if (!data) throw new Error("无法读取 benchmark catalog");
    const benchmarks = Array.isArray(data.benchmarks) ? data.benchmarks : Array.isArray(data) ? data : [];
    let sources = Array.isArray(data.sources) ? data.sources : [];
    if (!sources.length && loadedPath !== DATA_PATHS[0]) {
      try { sources = await loadJson("data/catalog/sources.json"); } catch (error) { /* source links remain optional */ }
    }
    // Long-form profiles are kept in a separate catalog file.  A freshly
    // derived site embeds them, while this fallback also supports local
    // previews built from an older site.json.
    let externalProfiles = {};
    try {
      const profilePayload = await loadJson("data/catalog/benchmark_profiles.json");
      if (profilePayload && typeof profilePayload === "object" && !Array.isArray(profilePayload)) {
        // Accept both the current flat catalog map and a wrapped `{profiles}`
        // payload so an exported profile bundle can be used as a fallback.
        externalProfiles = profilePayload.profiles && typeof profilePayload.profiles === "object"
          ? profilePayload.profiles
          : profilePayload;
      }
    } catch (error) { /* embedded profiles remain usable */ }
    state.data = data;
    const canonicalEntries = benchmarks.map((b) => ({
      ...b,
      // An older derived index may contain an empty profile object while the
      // catalog file has since been enriched; prefer the non-empty source.
      profile: b.profile && typeof b.profile === "object" && Object.keys(b.profile).length
        ? b.profile
        : externalProfiles[b.id] || {},
      _mode: modeOf(b),
      _metrics: metricList(b),
      _versions: versionList(b),
    }));
    const canonicalIds = new Set(canonicalEntries.map((bench) => String(bench.id)));
    const publicEntries = buildPublicSliceEntries(data, canonicalIds).map((b) => ({
      ...b,
      _mode: modeOf(b),
      _metrics: metricList(b),
      _versions: versionList(b),
    }));
    state.canonicalCount = canonicalEntries.length;
    state.publicOnlyCount = publicEntries.length;
    state.benchmarks = [...canonicalEntries, ...publicEntries];
    state.sources = sources;
    state.publicCounts = (data.publicStats && data.publicStats.benchmarkCounts) || {};
    state.runs = Array.isArray(data.runs) ? data.runs : [];
    state.loadedPath = loadedPath;
  }

  function sourceRows(bench) {
    const sourceMap = new Map(state.sources.map((source) => [source.id, source]));
    const ids = arr(first(bench.sourceIds, bench.source_ids));
    const rows = ids.map((id) => sourceMap.get(id) || { id, label: id, url: "" }).filter(Boolean);
    const direct = firstSafeUrl(bench.source, bench.sourceUrl, bench.source_url);
    if (direct && !rows.some((row) => row.url === direct)) rows.unshift({ id: "catalog-source", label: first(bench.sourceLabel, "Benchmark source"), url: direct });
    arr(bench._publicSources).forEach((candidate) => {
      if (!candidate || typeof candidate !== "object") return;
      const page = firstSafeUrl(candidate.web_url, candidate.page_url, candidate.url);
      const api = firstSafeUrl(candidate.api_url, candidate.apiUrl);
      const url = page || api;
      if (!url || rows.some((row) => row.url === url || row.api_url === api)) return;
      rows.push({ ...candidate, url, api_url: api && api !== url ? api : undefined });
    });
    return rows;
  }
  function evidenceCount(bench) { return number(state.publicCounts[bench.id]) || 0; }
  function canonicalCount(bench) { return state.runs.filter((run) => String(first(run.benchmarkId, run.benchmark_id)) === bench.id).length; }
  function latestDate(bench) {
    const dates = state.runs.filter((run) => String(first(run.benchmarkId, run.benchmark_id)) === bench.id).map((run) => first(run.observedAt, run.observed_at, run.publishedAt)).filter(Boolean);
    return dates.sort().at(-1) || "";
  }
  function activeVersions(bench) { return bench._versions.filter((v) => String(v.status).toLowerCase() === "active").length; }

  function populateSelect(select, values, labeler, selected = "all") {
    const options = [`<option value="all">全部${labeler === categoryLabel ? "能力面" : labeler === modeLabel ? "评估模式" : "指标"}</option>`];
    values.forEach((value) => options.push(`<option value="${esc(value)}">${esc(labeler(value))}</option>`));
    select.innerHTML = options.join("");
    select.value = values.includes(selected) ? selected : "all";
  }
  function setupControls() {
    const categories = [...new Set(state.benchmarks.map((b) => b.category).filter(Boolean))].sort((a, b) => categoryLabel(a).localeCompare(categoryLabel(b), "zh"));
    const modes = [...new Set(state.benchmarks.map((b) => b._mode).filter(Boolean))].sort();
    const metrics = [...new Set(state.benchmarks.flatMap((b) => b._metrics.map((m) => m.id)).filter(Boolean))].sort();
    populateSelect(els.categoryFilter, categories, categoryLabel, state.category);
    populateSelect(els.modeFilter, modes, modeLabel, state.mode);
    populateSelect(els.metricFilter, metrics, (value) => METRIC_LABELS[value] || value, state.metric);
    renderFamilyRail();
  }
  function renderFamilyRail() {
    const counts = new Map();
    state.benchmarks.forEach((bench) => counts.set(familyOf(bench), (counts.get(familyOf(bench)) || 0) + 1));
    const families = [...counts.keys()].sort((a, b) => familyLabel({ family: a }).localeCompare(familyLabel({ family: b }), "zh"));
    els.familyAllCount.textContent = state.benchmarks.length;
    els.familyRail.innerHTML = families.map((family) => `<button class="family-chip" type="button" data-family="${esc(family)}"><span>${esc(familyLabel({ family }))}</span><b>${counts.get(family)}</b></button>`).join("");
    els.familyRail.parentElement.querySelectorAll(".family-chip").forEach((button) => button.classList.toggle("active", button.dataset.family === state.family));
  }
  function filteredBenchmarks() {
    const query = state.search.trim().toLowerCase();
    const result = state.benchmarks.filter((bench) => {
      const haystack = [bench.id, bench.short, bench.name, bench.description, bench.owner, bench.category, bench.family, bench.familyLabel, ...arr(bench.tags)].filter(Boolean).join(" ").toLowerCase();
      return (!query || haystack.includes(query)) && (state.includePublic || !bench.publicOnly) && (state.category === "all" || bench.category === state.category) && (state.mode === "all" || bench._mode === state.mode) && (state.metric === "all" || bench._metrics.some((m) => m.id === state.metric)) && (state.family === "all" || familyOf(bench) === state.family) && (!state.featuredOnly || bench.featured === true);
    });
    const sorted = [...result];
    sorted.sort((a, b) => {
      if (state.sort === "name") return text(a.name, a.id).localeCompare(text(b.name, b.id), "zh");
      if (state.sort === "family") return `${familyLabel(a)}${a.name}`.localeCompare(`${familyLabel(b)}${b.name}`, "zh");
      if (state.sort === "evidence") return evidenceCount(b) - evidenceCount(a) || text(a.name, a.id).localeCompare(text(b.name, b.id), "zh");
      if (state.sort === "sources") return sourceRows(b).length - sourceRows(a).length || text(a.name, a.id).localeCompare(text(b.name, b.id), "zh");
      return Number(b.featured === true) - Number(a.featured === true) || categoryLabel(a.category).localeCompare(categoryLabel(b.category), "zh") || text(a.name, a.id).localeCompare(text(b.name, b.id), "zh");
    });
    return sorted;
  }
  function renderActiveFilters() {
    const tags = [];
    if (state.search) tags.push(`搜索：${state.search}`);
    if (state.category !== "all") tags.push(`能力面：${categoryLabel(state.category)}`);
    if (state.mode !== "all") tags.push(`模式：${modeLabel(state.mode)}`);
    if (state.metric !== "all") tags.push(`指标：${METRIC_LABELS[state.metric] || state.metric}`);
    if (state.family !== "all") tags.push(`家族：${familyLabel({ family: state.family })}`);
    if (state.featuredOnly) tags.push("重点评测");
    if (!state.includePublic) tags.push("隐藏公开切片");
    els.activeFilters.innerHTML = tags.length ? tags.map((tag) => `<span class="bench-filter-tag">${esc(tag)}</span>`).join("") : "<span>浏览全量目录 · 点击卡片打开详情</span>";
  }
  function renderCard(bench, index) {
    const detail = detailsFor(bench);
    const versions = bench._versions;
    const evidence = evidenceCount(bench);
    const canonical = canonicalCount(bench);
    const metric = bench._metrics[0] || {};
    return `<article class="benchmark-card${bench.featured === true ? " is-featured" : ""}${bench.publicOnly ? " is-public-only" : ""}" data-benchmark-id="${esc(bench.id)}" tabindex="0" role="button" aria-label="查看 ${esc(bench.name || bench.id)} 详情">
      <div class="bench-card-top"><span class="bench-index">${String(index + 1).padStart(2, "0")}</span><span class="bench-category-pill">${bench.publicOnly ? "公开切片" : esc(categoryLabel(bench.category))}</span></div>
      <h3>${esc(first(bench.name, bench.id))}</h3><p class="bench-card-id">${esc(first(bench.short, bench.id))} · ${esc(bench.owner || "owner 未注明")}</p>
      <p class="bench-card-description">${esc(first(detail.focus, bench.description, "暂无描述"))}</p>
      <div class="bench-card-meta"><span><label>PRIMARY METRIC</label><strong>${esc(first(metric.label, metricLabel(bench)))}${metric.direction === "lower" ? " ↓" : " ↑"}</strong></span><span><label>VERSION</label><strong>${esc(first(bench.version, versions.find((v) => v.status === "active")?.label, versions[0]?.label, "未注明"))}</strong></span></div>
      <div class="bench-card-foot"><span>${esc(modeLabel(bench._mode))}</span><span><strong>${evidence ? `${fmt(evidence)} 条公开记录` : "暂无公开记录"}${canonical ? ` · ${fmt(canonical)} canonical` : ""}</strong></span><span class="bench-open-link">打开 ↗</span></div>
    </article>`;
  }
  function render() {
    const visible = filteredBenchmarks();
    els.visibleCount.textContent = visible.length;
    els.totalCount.textContent = state.benchmarks.length;
    els.benchmarkGrid.innerHTML = visible.map(renderCard).join("");
    els.emptyState.hidden = visible.length > 0;
    renderActiveFilters();
    renderFamilyRail();
  }

  function renderMetrics(bench) {
    return bench._metrics.map((metric) => {
      const scale = metric.scale && typeof metric.scale === "object" ? `${text(metric.scale.min, "0")}–${text(metric.scale.max, "—")}` : metric.scale ? `0–${metric.scale}` : "—";
      const unit = first(metric.unit, bench.unit, "—");
      const direction = metric.direction === "lower" ? "越低越好 ↓" : "越高越好 ↑";
      return `<div class="bench-metric-row"><strong>${esc(first(metric.label, metric.id, "未注明"))}</strong><span>${esc(unit)} · ${esc(scale)} · ${direction}</span></div>`;
    }).join("");
  }
  function renderVersions(bench) {
    return bench._versions.map((version) => `<div class="bench-version-row"><div><strong>${esc(first(version.label, version.id, "未注明"))}</strong><small>${esc(first(version.id, "version id 未注明"))}</small></div><span class="status-badge ${String(version.status).toLowerCase() === "active" ? "approved" : "missing"}">${esc(first(version.status, "active"))}</span></div>`).join("");
  }
  function renderSources(bench) {
    const rows = sourceRows(bench);
    if (!rows.length) return `<p class="bench-evidence-note">目录暂未登记稳定来源链接；请在数据契约中补充 source_ids。</p>`;
    return rows.map((source) => {
      // Prefer a human-facing page when a registry entry also exposes an API
      // endpoint.  Keep API/download links visible so a reader can inspect
      // the exact machine-readable evidence behind the catalog description.
      const url = firstSafeUrl(source.web_url, source.page_url, source.url, source.source_url);
      // Some older registry rows used `url` for the API and kept the
      // human-facing page in `web_url`; preserve that endpoint as a secondary
      // link when the preferred primary URL differs.
      const apiUrl = firstSafeUrl(source.api_url, source.url !== url ? source.url : "");
      const downloadUrl = firstSafeUrl(source.download_url);
      const note = first(source.notes, source.license_note, source.licenseNote, "");
      const evidence = first(source.default_evidence_level, source.defaultEvidenceLevel, "");
      const metadata = [source.publisher, source.kind, evidence ? `evidence ${evidence}` : ""].filter(Boolean).join(" · ");
      const links = [];
      if (url) links.push(`<a href="${esc(url)}" target="_blank" rel="noreferrer">打开 ↗</a>`);
      if (apiUrl && apiUrl !== url) links.push(`<a href="${esc(apiUrl)}" target="_blank" rel="noreferrer">API ↗</a>`);
      if (downloadUrl && downloadUrl !== url && downloadUrl !== apiUrl) links.push(`<a href="${esc(downloadUrl)}" target="_blank" rel="noreferrer">下载 ↗</a>`);
      return `<div class="bench-source-row"><div><strong>${esc(first(source.label, source.id, "source"))}</strong>${metadata ? `<small>${esc(metadata)}</small>` : ""}${url ? `<small class="bench-source-url">${esc(url)}</small>` : ""}${note ? `<small class="bench-source-note">${esc(note)}</small>` : ""}</div>${links.length ? `<div class="bench-source-links">${links.join("")}</div>` : `<span class="bench-drawer-id">链接待补</span>`}</div>`;
    }).join("");
  }
  function renderProfileSections(bench) {
    const sections = [
      renderProfileGroup(bench, "Task & scope", "task", [["summary", "任务摘要", true], ["input", "输入", false], ["output", "输出", false]]),
      renderProfileGroup(bench, "Dataset & splits", "dataset", [["size", "规模", true], ["splits", "切分 / track", true], ["availability", "公开状态", true]]),
      renderProfileGroup(bench, "Evaluation protocol", "protocol", [["mode", "评估对象", false], ["grader", "判定器", false], ["tools", "工具 / 环境", true], ["sampling", "采样与聚合", true]]),
      renderProfileGroup(bench, "Comparison notes", "comparison", [["recommended", "建议比较", true], ["avoid", "避免混合", true]]),
    ].join("");
    const locator = profileOf(bench).source_locator;
    return sections + (locator ? `<div class="bench-profile-source-note"><span>SOURCE LOCATOR</span><p>${esc(locator)}</p></div>` : "");
  }
  function renderDrawer(bench) {
    if (!bench) return;
    const detail = detailsFor(bench);
    const publicRows = evidenceCount(bench);
    const canonicalRows = canonicalCount(bench);
    const latest = latestDate(bench);
    const sourceCount = sourceRows(bench).length;
    els.drawerContent.innerHTML = `<div class="bench-drawer-title-row"><div><h2 id="drawerTitle">${esc(first(bench.name, bench.id))}</h2><p>${esc(first(bench.owner, "Owner 未注明"))} · ${esc(categoryLabel(bench.category))}</p></div><span class="bench-drawer-id">${esc(bench.id)}</span></div>
      <div class="bench-drawer-tags"><span class="bench-drawer-tag accent">${esc(modeLabel(bench._mode))}</span><span class="bench-drawer-tag">${esc(familyLabel(bench))}</span>${bench.publicOnly ? '<span class="bench-drawer-tag public">公开切片 · 未复现</span>' : ""}${bench.featured === true ? '<span class="bench-drawer-tag">重点评测</span>' : ""}<span class="bench-drawer-tag">${esc(first(bench.version, bench._versions[0]?.label, "version 未注明"))}</span></div>
      <p class="bench-drawer-summary">${esc(detail.focus)}</p>
      <section class="bench-drawer-section"><h3>Identity & protocol</h3><div class="bench-meta-grid"><div class="bench-meta-item"><label>CANONICAL ID</label><strong>${esc(bench.id)}</strong></div><div class="bench-meta-item"><label>EVALUATION MODE</label><strong>${esc(modeLabel(bench._mode))}</strong></div><div class="bench-meta-item"><label>OWNER</label><strong>${esc(first(bench.owner, "未注明"))}</strong></div><div class="bench-meta-item"><label>FAMILY</label><strong>${esc(familyLabel(bench))}</strong></div><div class="bench-meta-item"><label>DEFAULT VERSION</label><strong>${esc(first(bench.defaultVersionId, bench.default_version_id, bench._versions[0]?.id, "未注明"))}</strong></div><div class="bench-meta-item"><label>PRIMARY METRIC</label><strong>${esc(metricLabel(bench))}</strong></div></div></section>
      <section class="bench-drawer-section"><h3>What it measures</h3><p class="bench-drawer-summary">${esc(first(bench.description, detail.focus))}</p></section>
      ${renderProfileSections(bench)}
      <section class="bench-drawer-section"><h3>Metrics</h3><div class="bench-metric-list">${renderMetrics(bench)}</div></section>
      <section class="bench-drawer-section"><h3>Versions</h3><div class="bench-version-list">${renderVersions(bench)}</div></section>
      <section class="bench-drawer-section"><h3>Comparison guardrail</h3><p class="bench-guardrail">${esc(detail.guardrail)}</p></section>
      <section class="bench-drawer-section"><h3>Evidence footprint</h3><div class="bench-evidence-summary"><div class="bench-evidence-pill"><label>PUBLIC REPORTED</label><strong>${fmt(publicRows)}</strong></div><div class="bench-evidence-pill"><label>CANONICAL RUNS</label><strong>${fmt(canonicalRows)}</strong></div><div class="bench-evidence-pill"><label>SOURCES</label><strong>${fmt(sourceCount)}</strong></div></div><p class="bench-evidence-note">公开记录来自榜单、模型卡或公开 API，默认标记“披露 · 未复现”；canonical run 仍需结合具体模型、harness 和 protocol 阅读。${bench.publicOnly ? "此条目是由公开 evidence 自动汇总的切片，尚未进入 canonical benchmark registry。" : ""}${latest ? ` 最近观测：${esc(latest)}。` : ""}</p></section>
      <section class="bench-drawer-section"><h3>Primary sources</h3><div class="bench-source-list">${renderSources(bench)}</div></section>
      <div class="bench-drawer-cta"><a href="index.html#matrix">在评测矩阵中查看 ↗</a><a href="data/catalog/benchmarks.json" target="_blank" rel="noreferrer">打开原始目录 ↗</a><a href="data/catalog/benchmark_profiles.json" target="_blank" rel="noreferrer">打开 profile 数据 ↗</a></div>`;
  }
  function setHash(id) {
    const next = id ? `#bench=${encodeURIComponent(id)}` : "#catalog";
    if (window.location.hash !== next) window.history.pushState({}, "", next);
  }
  function openDrawer(id, updateHash = true) {
    const bench = state.benchmarks.find((item) => item.id === id);
    if (!bench) return;
    state.selectedId = id;
    renderDrawer(bench);
    els.drawerBackdrop.hidden = false;
    els.detailDrawer.classList.add("open");
    els.detailDrawer.setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
    if (updateHash) setHash(id);
    els.closeDrawer.focus({ preventScroll: true });
  }
  function closeDrawer(updateHash = true) {
    state.selectedId = null;
    els.detailDrawer.classList.remove("open");
    els.detailDrawer.setAttribute("aria-hidden", "true");
    window.setTimeout(() => { if (!state.selectedId) els.drawerBackdrop.hidden = true; }, 280);
    document.body.classList.remove("drawer-open");
    if (updateHash && window.location.hash.startsWith("#bench=")) setHash("");
  }
  function readHash() {
    const match = window.location.hash.match(/^#bench=(.+)$/);
    if (match) openDrawer(decodeURIComponent(match[1]), false);
    else if (state.selectedId) closeDrawer(false);
  }
  function resetFilters() {
    state.search = ""; state.category = "all"; state.mode = "all"; state.metric = "all"; state.family = "all"; state.sort = "featured"; state.featuredOnly = false; state.includePublic = true;
    els.benchSearch.value = ""; els.categoryFilter.value = "all"; els.modeFilter.value = "all"; els.metricFilter.value = "all"; els.sortFilter.value = "featured"; els.featuredOnly.checked = false; if (els.includePublic) els.includePublic.checked = true;
    render();
  }
  let toastTimer;
  function toast(message) { if (!els.toast) return; els.toast.textContent = message; els.toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2300); }
  function setupTheme() {
    let light = false;
    try { light = localStorage.getItem("fmb-theme") === "light"; } catch (error) { /* ignore storage restrictions */ }
    document.documentElement.classList.toggle("light", light);
    els.themeToggle.textContent = light ? "☾" : "☼";
    els.themeToggle.addEventListener("click", () => {
      light = !document.documentElement.classList.contains("light");
      document.documentElement.classList.toggle("light", light);
      els.themeToggle.textContent = light ? "☾" : "☼";
      try { localStorage.setItem("fmb-theme", light ? "light" : "dark"); } catch (error) { /* optional */ }
    });
  }
  function bindEvents() {
    [els.benchSearch, els.categoryFilter, els.modeFilter, els.metricFilter, els.sortFilter, els.featuredOnly, els.includePublic].filter(Boolean).forEach((element) => {
      element.addEventListener("input", () => {
        state.search = els.benchSearch.value;
        state.category = els.categoryFilter.value;
        state.mode = els.modeFilter.value;
        state.metric = els.metricFilter.value;
        state.sort = els.sortFilter.value;
        state.featuredOnly = els.featuredOnly.checked;
        state.includePublic = !els.includePublic || els.includePublic.checked;
        render();
      });
      element.addEventListener("change", () => {
        state.search = els.benchSearch.value;
        state.category = els.categoryFilter.value;
        state.mode = els.modeFilter.value;
        state.metric = els.metricFilter.value;
        state.sort = els.sortFilter.value;
        state.featuredOnly = els.featuredOnly.checked;
        state.includePublic = !els.includePublic || els.includePublic.checked;
        render();
      });
    });
    els.resetFilters.addEventListener("click", resetFilters);
    els.emptyReset.addEventListener("click", resetFilters);
    document.addEventListener("click", (event) => {
      const card = event.target.closest("[data-benchmark-id]");
      if (card) openDrawer(card.dataset.benchmarkId);
      const family = event.target.closest("[data-family]");
      if (family) { state.family = family.dataset.family; render(); }
    });
    els.benchmarkGrid.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && event.target.closest("[data-benchmark-id]")) { event.preventDefault(); openDrawer(event.target.closest("[data-benchmark-id]").dataset.benchmarkId); }
    });
    els.closeDrawer.addEventListener("click", () => closeDrawer());
    els.drawerBackdrop.addEventListener("click", () => closeDrawer());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && state.selectedId) closeDrawer();
      if (event.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "SELECT" && document.activeElement?.tagName !== "TEXTAREA") { event.preventDefault(); els.benchSearch.focus(); }
    });
    window.addEventListener("hashchange", readHash);
    window.addEventListener("popstate", readHash);
  }
  function updateSummary() {
    const families = new Set(state.benchmarks.map(familyOf));
    // Keep the headline useful when public-only slices are enabled: active
    // versions describe the curated registry, while the companion note tells
    // the reader how many source slices were indexed alongside it.
    const active = state.benchmarks.filter((bench) => !bench.publicOnly).reduce((sum, bench) => sum + activeVersions(bench), 0);
    const sourceIds = new Set(state.sources.map((source) => source && source.id).filter(Boolean));
    els.catalogCount.textContent = state.benchmarks.length;
    els.familyCount.textContent = families.size;
    els.sourceCount.textContent = sourceIds.size;
    els.activeVersionCount.textContent = active;
    if (els.catalogNote) els.catalogNote.textContent = `${state.canonicalCount} canonical · ${state.publicOnlyCount} public-only slices`;
    const snapshotDates = [state.data?.publicMeta?.generatedAt, state.data?.meta?.generatedAt, state.data?.meta?.asOf, state.data?.meta?.lastUpdated]
      .filter(Boolean).map((value) => String(value).slice(0, 10)).sort();
    const date = snapshotDates.at(-1);
    if (date) {
      els.catalogFreshness.innerHTML = `<span class="status-dot"></span><span>snapshot ${esc(date)}</span>`;
      els.footerStatus.textContent = `${state.canonicalCount} 个 canonical benchmark · ${state.publicOnlyCount} 个公开切片 · ${sourceIds.size} 个来源。`;
    }
  }

  async function init() {
    setupTheme();
    try {
      await loadData();
      setupControls();
      updateSummary();
      bindEvents();
      render();
      readHash();
    } catch (error) {
      els.benchmarkGrid.innerHTML = `<div class="bench-empty"><span class="empty-icon">!</span><h3>目录暂时无法加载</h3><p>${esc(error.message)}。请确认通过 HTTP 服务打开页面，并检查 data/derived/site.json。</p></div>`;
      toast("benchmark catalog 加载失败");
    }
  }
  init();
})();
