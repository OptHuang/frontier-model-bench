# Frontier Model Bench 维护计划

本文是这个信息站的长期维护契约。目标是让新模型、新 benchmark 和新成绩定期进入信息站，同时保留来源、协议、历史和可恢复的发布记录。

## 0. 当前发布授权（2026-09-07）

用户已明确要求“以后直接发布，有问题再改”。本地 Codex 日常维护因此采用 **检查来源 → 更新 → 校验 → 提交/推送 → 确认 Pages 上线**，不再对普通公开披露补数、来源明确的目录补全、关注排序及相关数据/展示修正逐次请求审核。此授权仅适用于本仓库及现有 GitHub Pages，不扩展到相邻仓库、付费评测或其他外部操作。

- 发布门槛是来源说明完整、历史保留、strict validation 与测试通过，不是“本站重跑每条 run”。公开分数继续标为“披露 · 未复现”；发布不等于晋升 approved。
- 不因表格行号/抓取时间变化批量新增重复分数。比较来源、原始模型/effort、benchmark/version、metric/unit、harness/protocol 与值，只发布实质变化；完整抓取及旧证据保留在本地维护 artifact。
- 不清楚的版本、日期、工具/环境保持未知并标明；身份歧义先留在公开索引/候选，不强行映射矩阵，也不阻挡其他明确的数据发布。
- 发布前检查 Git diff，只提交本次维护的文件，不夹带用户改动；非快进、测试失败或权限限制先安全诊断，不强推或绕过检查。GitHub Actions 现有候选任务继续只读，本地 heartbeat 负责自动发布，避免两个写入者竞争。
- 推送后核对当前 SHA 的 CI、Pages 及线上关键数据，不能把 push 成功当作上线成功。有问题直接做本任务范围内的前向修复，必要时以新提交回退已确认有问题的本任务变更，保留历史，不使用 hard reset/force push。只有无法安全解决或需要新权限时才询问用户。
- 无实质变化保持安静；有新内容成功上线、重要修复、发布失败或确需用户决定时简短汇报。

## 1. 不可变的工作流

```text
来源页面 / API / Arena
        ↓（只读抓取，保留 URL、时间、hash、parser 版本）
candidate 候选区（GitHub Actions artifact）
        ├─→ public/reported evidence（数值先展示，明确“未复现”）
        ↓（人工确认身份、版本、协议、证据和许可证）
approved observation（data/observations/results.jsonl）
        ↓
build_derived.py → validate_data.py --strict → Pages
```

定时任务不覆盖 `data/observations/` 或已批准分数，不抹去既有目录与历史。数值完整且能
安全保留来源定位的候选，可以先进入独立的 `public/reported evidence` 页面层；它必须
显示“披露 · 未复现”，不参与 canonical 排名。网络失败、网页改版和解析不确定性只能
产生 warning/candidate；进入 approved 仍必须是人工审阅的 PR。

## 2. 已配置的自动任务

### 关注优先排序（2026-09-06）

- 矩阵、Agent 系统表、模型目录统一默认“关注优先”；规则只在 `data/presentation/model-order.json` 维护。构建生成每个模型的 `displayOrder`，不改 canonical 目录顺序、身份、分数或证据状态。
- 当前 OpenAI / Anthropic 优先；精选主力目前为 GPT-6 Astra、Fable 5.1、GPT-5.6 Sol、Opus 5。其余当前模型按已有旗舰/前沿标签、发布日期安排，同日同族参考 `sibling_tiers`（如 Terra 在 Luna 前）；两家的其他当前模型仍在其他 provider 前。历史/上一代和已退役模型后置，不删除。未知发布日期不猜测。
- 每日维护同时复查新 release、上下线状态和重要公开测评；每周至少完整复查一次精选顺序。优先参考 Terminal-Bench Science 0.1、OR / math / science 与重要 agent 榜单的有来源结果，同版本/指标/预算内比较；允许采用清晰标注的厂商/第三方披露，不要求重跑每条 run。
- 这是用户关注顺序，不是总实力排名；不把跨 benchmark 分数平均，不将覆盖率、单次最高分或型号名称当作实力结论。新主力或多项可比结果有明确变化时调整精选列表并记录来源链接、理由、复查日期；只有单项或不同 harness 的优势时，不推断全面领先。没有依据的顺序不悄悄改。
- 后续定时任务可修改此独立展示配置、重建 derived，校验通过后直接提交/推送并确认上线，不再逐次等审核；不修改 approved。无排序变化不为刷新日期制造提交或提醒。用户手动按日期、覆盖率、分数、成本等排序不受关注排序覆盖。

### 2026-09-06：关注领域与历史合并

- 首页默认只呈现核心 8 列；OR 为 OptMATH / IndustryOR / MIPLIB-NL / ALE-Bench，数学聚焦 FrontierMath v2 两组与 ProofBench，科学为 TB-Science 0.1 / GPQA / HLE / SciCode / CritPt。AIME/HMMT 等目前仅较早模型有成绩的列保留在完整目录。OR 默认仅有成绩，用户可展开全部模型。
- **科学首要来源：Terminal-Bench Science 0.1**，核心/科学页首列。`src-terminal-bench-science` 读取官方主页的公开 `/api/leaderboard`，固定 `v0-1-eval`，仅解析公开聚合行（70 任务 × 3 次）。保留 model × harness × effort、dataset version ID、标准误、领域分项、cost/tokens 与 Harbor Hub row 深链；不获取题目或轨迹，不将网站编辑日期当作 run 日期。0.2 必须新增版本，不覆盖 0.1。
- 主榜缺少新模型时，同时检查厂商发布页，不以“未进主榜”为留空理由。GPT-6 Astra 64.6% 与 Fable 5.1 52.6% 已由 `data/public/provider_reports/tb-science-0.1-2026-09-06/` 的版本化摘录补入，标记“厂商披露 · 未复现”。摘录 hash 仅覆盖 `source_excerpt.json`，不是整页 HTML hash；保留来源 URL、表格列定位、采集方法与日期。OpenAI 直接 HTTP 返回 403 时使用已可访问的 web 文本，不绕过限制。厂商未注明的 harness / 重复次数留空，不挪用主榜设置；后续更新追加新摘录并合并历史。
- 同名单独检查 release：TB-Science 的 DeepSeek V4 Pro 行明确指向 0813；source-scoped alias 可显式纠正 fetch 的自动别名，保留旧映射记录，不能覆盖人工 reviewed 身份。
- 分数底色为单一浅青绿色。百分比/小数按 0–100 / 0–1 的固定尺度，非有界 performance/rank 按当前视图同版本/指标/配置范围；越低越好的指标反向。颜色不代表核验状态、统计显著性或跨 benchmark 可比，缺失格不着色。
- 优先刷新 ALE-Bench 官方聚合 JSON、Epoch 的 FrontierMath **独立 v2 CSV**、SciCode、ProofBench、CritPt。ALE-Bench 默认摘要是 self-refine 16 / all / performance；其他配置不删除，系统表可展开。
- OptArena 已导入公开矩阵 JSON；目前是一次性来源，未确认长期接口契约，不盲目启用 adapter。零值如无法区分未跑/无记录，保留 raw value 和 missing，不填 0。
- 每次补数必须合并旧公开层及完整 unmapped/alternatives，禁止用当天局部 fetch 替换历史。运行 `scripts/merge_public_evidence.py --baseline data/derived/public.json --baseline data/public/unmapped.jsonl --baseline data/public/alternatives.jsonl --input-dir <新候选目录> --output-dir <新的临时目录>`；检查历史 ID 与旧快照 hash 全部保留后，再安装生成的五份输出、运行 build_derived、strict validation 与 tests。
- 模型发布日期、LiveBench 任务版本、站点生成日期不是评测日期。来源未披露的 benchmark/judge 版本和 observed 日期必须留空；原始疑点日期保留在 `sourceReportedDates`，不据此猜测一次 run。
- 公开层永远保持 reported/candidate 与 verified=false；上述合并不触碰 approved observations。校验通过的实质公开更新按第 0 节直接发布。

`.github/workflows/maintenance.yml` 每天 UTC 02:17（北京时间 10:17）运行，也可以手动 `workflow_dispatch`：

1. 检查 canonical catalog 和 observation contract。
2. 计算当前模型 × active benchmark 的覆盖率。
3. 为没有 approved observation 的单元生成候选，并区分“已有 mapped public/reported evidence、等待 canonical 审阅”与“完全没有 mapped public evidence”；为超过 freshness 阈值的旧事实生成 refresh 候选。这个分类不改变 canonical coverage 口径。
4. 对 registry 中的来源 landing page 做有上限的 HEAD/GET 健康探测，不解析或保存题目、整张榜单等 payload。
5. 生成并上传 30 天保留的 artifact：
   - `summary.md`：可直接贴到 Actions Summary 的中文摘要；
   - `health.json`：状态、覆盖率、freshness、网络探测结果；
   - `candidates.json`：缺失/刷新候选队列；
   - `source-status.json`：逐来源健康状态。
   - `artifacts/fetch/`：已注册公开 adapter 的 manifest、解析候选和汇总（`check --dry-run`，不保存原始 payload）。
   - `artifacts/review/`：由 `review_candidates.py` 生成的去重/分级审阅包；其中每条决策都保持 `pending`，不写入 approved 数据。
   - `artifacts/maintenance/public*`：本次抓取可展示的 reported 快照、未映射队列和替代协议；只作公开信息层预览，不晋升 canonical。

本地等价命令：

```bash
python3 scripts/maintenance_report.py --root . --output-dir /tmp/fmb-maintenance
# 需要探测来源页面时：
python3 scripts/maintenance_report.py --root . --output-dir /tmp/fmb-maintenance --check-sources
# 读取已注册的公开 adapters，只写候选 artifact，不保存原始 payload：
python3 scripts/fetch.py check --dry-run --root . --output-dir /tmp/fmb-fetch
# 将候选整理成可逐条核对的 Markdown/JSON（仍是 candidate-only）
python3 scripts/review_candidates.py --root . --input-dir /tmp/fmb-fetch \
  --output-dir /tmp/fmb-review --limit 50
# 将数值完整的候选生成公开披露预览；仍不修改 approved 数据
python3 scripts/build_public_evidence.py --root . --input-dir /tmp/fmb-fetch \
  --output /tmp/fmb-public.json --jsonl-output /tmp/fmb-public.jsonl \
  --unmapped-output /tmp/fmb-public-unmapped.jsonl \
  --unmapped-summary-output /tmp/fmb-public-unmapped-summary.json \
  --alternatives-output /tmp/fmb-public-alternatives.jsonl --max-per-key 0
# Arena 人工分批扩展（定时任务仍使用 core/100 的安全默认）
python3 scripts/fetch.py check --sources lmarena-hf-dataset \
  --arena-configs text,text_style_control --arena-max-rows 500 \
  --output-dir /tmp/fmb-arena-refresh
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
```

`--max-per-key 0` 是本地默认值，会把所有已映射公开行保留在披露层；在 Actions 或移动端
预览需要控制体积时，可以显式传入正数 cap（被省略的已映射行会进入
`alternatives.jsonl`，不会丢失）。

`maintenance_report.py` 是只读报告器；它的 exit code 只在输入损坏或报告无法生成时非零。摘要会把 canonical gaps 分成 `Public reported / awaiting canonical review` 和 `No mapped public evidence` 两类；前者在 `summary.md` 中默认折叠，完整明细仍保留在 `candidates.json`。候选很多并不代表发布失败，应该按优先级分批处理。

本地 Codex 维护 heartbeat 按已保存的每日计划检查同一仓库：读取本计划、运行报告/适配器与校验，自动发布正常维护更新。它与 GitHub Actions 是“本地维护与发布 + 只读候选 artifact”两层。原描述为北京时间 09:00，但 09-07 的实际触发为 01:00；本次仅更新发布授权，未改触发时间，时区疑点保留待单独确认。

## 3. 日常、每周、每月节奏

### 每日：发现与健康检查

- 查看最近一次 `maintenance.yml` 的 `summary.md`。
- 按上述“关注优先排序”复查当前主力；有依据时更新独立展示配置，并测试矩阵、系统表、模型目录顺序一致与手动排序仍可用。
- 先处理 `high`：当前/preview 模型的 featured benchmark 缺口、来源失效、协议冲突和明显撤回。
- 检查 source probe 的 4xx/5xx、重定向到登录页、robots/许可证变化；不要把 HTTP 200 当成数据解析成功。
- 先看 public preview：它能快速告诉我们外部榜单已经报告了哪些值；确认来源、版本或
  协议不清的行保留 `unreviewed`，不要因为矩阵想填满就手动改名或平均。
- 公开层做来源和实质差异检查，校验后直接小批次发布；不要求逐条重跑评测。`review.md`/`review.json` 留作审计与 canonical promotion 的材料；无法确认的身份/事实不手工“猜”。

### 每周：补全和冲突审阅

- 从 `candidates.json` 按“当前模型 → featured benchmark → system run → 其他 benchmark”顺序认领 10–30 条。
- 对同一模型/版本/benchmark 的多个来源做对照，保留各条 observation；用 `preferred` 或 PR 说明选择展示值，不覆盖历史。
- 优先补全有完整 protocol 的官方榜单/benchmark-owner 结果，再处理 provider self-report 和聚合榜。
- 检查新 release 是否只是 alias、reasoning tier、速度 tier、量化或 endpoint 变化；必要时新增 release/endpoint，而不是改旧 id。

### 每月：目录和治理复盘

- 复查 active/preview/previous/restricted/retired 状态、family 归属、发布日期、上下文和开放权重字段。
- 检查 benchmark 版本是否滚动、metric/direction/scale 是否变化；滚动榜必须新建 `version_id` 或 snapshot，而不是原地改分数。
- 更新来源的 `staleness_after_days`、抓取方式和许可证说明。
- 淘汰默认视图中长期不再维护的旧模型，但保留其 catalog、历史 observation 和来源链接。
- 统计本月新增模型、approved observation、冲突、撤回、候选转化率，并在 release note/维护日志中记录。

## 4. 缺失数据如何补全

### 优先级

候选按以下顺序处理：

1. 当前 `active`/`preview`/`restricted` 模型 × featured direct benchmark（GPQA、AIME、MMLU-Pro、HLE、MMMU 等）。
2. 当前模型的 system benchmark（SWE-bench、Terminal-Bench、BFCL、τ-bench、OSWorld 等），必须保留 harness、scaffold、预算和 endpoint。
3. Flash/Fast、小模型、中文、多模态、长上下文、开放权重等预设中的对照组。
4. `previous` 模型和非 featured benchmark，用于趋势和“上一代”视图。

缺失不等于零：没有 observation 就显示 `—`。来源明确说“无法评测”时，写 `value: null` 加 `missing_reason`；来源暂时不可访问时保留最近 approved 值并加 `stale`，不要删除旧事实。

### 来源梯度

- **A：** benchmark owner 官方榜单、可复现运行产物。
- **B：** provider model card/technical report，协议完整但属于 self-report。
- **C：** 方法和设置公开的可信第三方榜单。
- **D：** 二手报道、截图或协议不明；数值完整时可进入 public/reported 索引并标记未复现，
  但不进入 approved/canonical；缺值或无法定位的行只进入 candidate 队列。

建议逐步为以下来源写 adapter（先做快照/解析，再做人工审阅）：

- 官方与 benchmark owner：OpenAI、Anthropic、Google、Qwen、DeepSeek、Kimi、GLM、MiniMax、MiMo、HELM、SWE-bench、Terminal-Bench、LiveCodeBench、Humanity’s Last Exam、FrontierMath、BFCL、τ-bench、Toolathlon、OSWorld、CyberGym。
- Arena/聚合观察：Arena 官方 `lmarena-hf-dataset`（HF `leaderboard-dataset` 的 text/vision/webdev/search/document/agent latest rows；默认每 config 100 行安全上限，超量显式标记 truncated）、Epoch AI Benchmarking Hub（CC-BY 下载快照）、Aider Polyglot、MLE-bench、Artificial Analysis、Hugging Face Open LLM Leaderboard、LiveBench、SuperCLUE 等；互动 Arena 页面仍禁用抓取。

Arena 的 Elo、聚合榜的 intelligence index 与 benchmark accuracy 是不同 metric；必须单独登记 benchmark/version/metric，不能合成一个“综合分”。聚合站可以帮助发现缺口，但若原始协议、采样和版本不完整，最多标 `conditional`，不冒充 exact。

## 5. 模型准入、更新和淘汰

### 新模型准入

- 有明确 provider、family、release/endpoint id、发布日期和至少一个可打开的来源。
- alias、reasoning/速度 tier、preview、量化和 API endpoint 的差异写入 `variant`/`endpoint_id`；不要把不同条件塞进同一个 id。
- 可变字段（价格、context window、availability、参数规模）带 `as_of` 和 evidence；不能把网页当前值当作永久事实。
- 没有分数也可以先进入 catalog，标记 `catalog-only`；默认公开覆盖视图显示其无分数行，但不进入模型成绩矩阵的统计分子。

### 更新与冲突

- 新结果追加一行 observation；旧结果只通过 `superseded`/`retracted` 和理由失效。
- 同一条件来自两个来源时保留两行，记录 source、evidence、observed/published date，并在 PR 中说明 preferred 规则。
- benchmark version、prompt、shots、tools、judge、temperature、reasoning effort、harness 或预算任一变化，都不能默认为 exact comparable。

### 淘汰

- `previous`：仍可访问但不再是默认 frontier；保留在 Latest vs Previous 和历史视图。
- `deprecated`/`retired`：endpoint 下线、官方明确撤回或长期不可用；从默认预设隐藏，但不删除数据。
- 只有错误身份、违法再分发或明确要求移除时才做 `retracted`，并留下治理说明。

## 6. 发布检查与 canonical PR 审阅

每次数据发布检查至少回答；canonical promotion 的 PR 也必须回答：

- 这是哪个 canonical model release/endpoint？是否误把 alias 当新模型？
- benchmark 的 version、metric、unit、direction、split/subset 是什么？
- 是 model-only 还是 system run？system 是否写清 harness/scaffold/预算？
- observed、published、retrieved 日期是否分开？来源 URL、locator、evidence level 是否可回溯？
- 与现有结果是 `exact`、`conditional` 还是 `none`？是否存在冲突或重复？
- 许可证是否允许保存 payload？不允许时只保存元数据、URL、locator 和 hash。

合并前必须通过：

```bash
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
git diff --check
```

Pages workflow 只发布通过校验的 derived index。公开层不再等用户逐次审核；线上发现问题按第 0 节修复或用新提交回退本任务问题变更。canonical promotion 仍需要人工审阅，不得借发布授权改成已复现。

## 7. 健康状态解释

`health.json.status`：

- `green`：没有缺失/过期候选，且输入与来源探测正常。
- `amber`：有缺失、过期或网络探测失败；需要维护者处理，但不会替换线上数据。
- `red`：catalog/JSONL 损坏，报告无法可靠生成；先修复 schema，再讨论补数。

覆盖率只用于定位工作量，不用于给模型排名。`covered_cells` / `missing_cells` 始终只按 canonical approved observation 计算；public/reported evidence 只细分缺口的审阅状态，不进入覆盖率分子。尤其是当前目录故意比成绩表更宽，`catalog-only` 是待补数据队列，不是低分模型；公开覆盖视图中的空白也不等于没人测试。

## 8. 后续演进

当前已启用公开层与排序的自动发布；后续优先补高价值来源 adapter、语义去重和修正回执。仓库内的维护 skill 固化同一授权边界；无论是否安装到个人环境，都必须遵守“candidate 不覆盖 approved”。人工审阅门槛针对 canonical promotion，不是普通公开层发布。

仓库内的维护 skill 位于 [`skills/frontier-model-bench-maintenance/SKILL.md`](../skills/frontier-model-bench-maintenance/SKILL.md)，包含 Audit、Fetch、Review/Promotion、Catalog maintenance、Public publication 五种操作模式。新增 adapter 的接口和 fixture 约定见 [`docs/adding-source.md`](adding-source.md)。
