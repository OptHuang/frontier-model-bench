# Frontier Model Bench 维护计划

本文是这个信息站的长期维护契约。目标不是做一个会悄悄变动的“实时总榜”，而是让新模型、新 benchmark 和新成绩可以被定期发现、审阅、追溯，并以小 PR 安全地进入静态站点。

## 1. 不可变的工作流

```text
来源页面 / API / Arena
        ↓（只读抓取，保留 URL、时间、hash、parser 版本）
candidate 候选区（GitHub Actions artifact）
        ↓（人工确认身份、版本、协议、证据和许可证）
approved observation（data/observations/results.jsonl）
        ↓
build_derived.py → validate_data.py --strict → Pages
```

定时任务永远不覆盖 `data/catalog/`、`data/observations/` 或已批准分数，也不自动把网页中的数字发布到首页。网络失败、网页改版和解析不确定性只能产生 warning/candidate；最后一步必须是人工审阅的 PR。

## 2. 已配置的自动任务

`.github/workflows/maintenance.yml` 每天 UTC 02:17（北京时间 10:17）运行，也可以手动 `workflow_dispatch`：

1. 检查 canonical catalog 和 observation contract。
2. 计算当前模型 × active benchmark 的覆盖率。
3. 为没有 approved observation 的单元生成缺失候选；为超过 freshness 阈值的旧事实生成 refresh 候选。
4. 对 registry 中的来源 landing page 做有上限的 HEAD/GET 健康探测，不解析或保存题目、整张榜单等 payload。
5. 生成并上传 30 天保留的 artifact：
   - `summary.md`：可直接贴到 Actions Summary 的中文摘要；
   - `health.json`：状态、覆盖率、freshness、网络探测结果；
   - `candidates.json`：缺失/刷新候选队列；
   - `source-status.json`：逐来源健康状态。
   - `artifacts/fetch/`：已注册公开 adapter 的 manifest、解析候选和汇总（`check --dry-run`，不保存原始 payload）。

本地等价命令：

```bash
python3 scripts/maintenance_report.py --root . --output-dir /tmp/fmb-maintenance
# 需要探测来源页面时：
python3 scripts/maintenance_report.py --root . --output-dir /tmp/fmb-maintenance --check-sources
# 读取已注册的公开 adapters，只写候选 artifact，不保存原始 payload：
python3 scripts/fetch.py check --dry-run --root . --output-dir /tmp/fmb-fetch
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
```

`maintenance_report.py` 是只读报告器；它的 exit code 只在输入损坏或报告无法生成时非零。候选很多并不代表发布失败，应该按优先级分批处理。

本地 Codex 维护 heartbeat 另在每天北京时间 09:00 检查同一仓库：读取本计划、运行报告/适配器和校验，并只在出现候选、来源变化、失败或需要决策时提醒。它与 GitHub Actions 是“主动审阅提醒 + 可下载 artifact”两层，不会自动合并或发布数据。

## 3. 日常、每周、每月节奏

### 每日：发现与健康检查

- 查看最近一次 `maintenance.yml` 的 `summary.md`。
- 先处理 `high`：当前/preview 模型的 featured benchmark 缺口、来源失效、协议冲突和明显撤回。
- 检查 source probe 的 4xx/5xx、重定向到登录页、robots/许可证变化；不要把 HTTP 200 当成数据解析成功。
- 将可确认的事实放入一个小 PR；无法确认的只留在 candidate artifact，不手工“猜”分数。

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
- **D：** 二手报道、截图或协议不明；只进入 candidate，不进入默认矩阵。

建议逐步为以下来源写 adapter（先做快照/解析，再做人工审阅）：

- 官方与 benchmark owner：OpenAI、Anthropic、Google、Qwen、DeepSeek、Kimi、GLM、MiniMax、MiMo、HELM、SWE-bench、Terminal-Bench、LiveCodeBench、Humanity’s Last Exam、FrontierMath、BFCL、τ-bench、Toolathlon、OSWorld、CyberGym。
- Arena/聚合观察：LMSYS Chatbot Arena（Elo）、Artificial Analysis、Hugging Face Open LLM Leaderboard、LiveBench、SuperCLUE 等。

Arena 的 Elo、聚合榜的 intelligence index 与 benchmark accuracy 是不同 metric；必须单独登记 benchmark/version/metric，不能合成一个“综合分”。聚合站可以帮助发现缺口，但若原始协议、采样和版本不完整，最多标 `conditional`，不冒充 exact。

## 5. 模型准入、更新和淘汰

### 新模型准入

- 有明确 provider、family、release/endpoint id、发布日期和至少一个可打开的来源。
- alias、reasoning/速度 tier、preview、量化和 API endpoint 的差异写入 `variant`/`endpoint_id`；不要把不同条件塞进同一个 id。
- 可变字段（价格、context window、availability、参数规模）带 `as_of` 和 evidence；不能把网页当前值当作永久事实。
- 没有分数也可以先进入 catalog，标记 `catalog-only`，不进入模型成绩矩阵的统计分子。

### 更新与冲突

- 新结果追加一行 observation；旧结果只通过 `superseded`/`retracted` 和理由失效。
- 同一条件来自两个来源时保留两行，记录 source、evidence、observed/published date，并在 PR 中说明 preferred 规则。
- benchmark version、prompt、shots、tools、judge、temperature、reasoning effort、harness 或预算任一变化，都不能默认为 exact comparable。

### 淘汰

- `previous`：仍可访问但不再是默认 frontier；保留在 Latest vs Previous 和历史视图。
- `deprecated`/`retired`：endpoint 下线、官方明确撤回或长期不可用；从默认预设隐藏，但不删除数据。
- 只有错误身份、违法再分发或明确要求移除时才做 `retracted`，并留下治理说明。

## 6. PR 审阅门槛

每个数据 PR 至少回答：

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

Pages workflow 只发布通过校验的 derived index。若新数据有问题，关闭 PR 即可；上一个 approved commit/Pages 版本不受候选任务影响。

## 7. 健康状态解释

`health.json.status`：

- `green`：没有缺失/过期候选，且输入与来源探测正常。
- `amber`：有缺失、过期或网络探测失败；需要维护者处理，但不会替换线上数据。
- `red`：catalog/JSONL 损坏，报告无法可靠生成；先修复 schema，再讨论补数。

覆盖率只用于定位工作量，不用于给模型排名。尤其是当前目录故意比成绩表更宽，`catalog-only` 是待补数据队列，不是低分模型。

## 8. 后续演进

第一阶段只做 landing-page health + candidate queue；第二阶段为高价值来源增加带 fixture 的 adapter；第三阶段再考虑受控的自动 PR（仍需人工 merge）。仓库内的 skill 草案已经把这些动作固化为可复用流程；无论是否安装到个人环境，都必须遵守“candidate 不覆盖 approved”和人工审阅门槛。

仓库内的维护 skill 草案位于 [`skills/frontier-model-bench-maintenance/SKILL.md`](../skills/frontier-model-bench-maintenance/SKILL.md)，它把本计划转成 Audit、Fetch、Review/Promotion、Catalog maintenance 四种操作模式。新增 adapter 的接口和 fixture 约定见 [`docs/adding-source.md`](adding-source.md)。
