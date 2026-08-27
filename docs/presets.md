# 比较预设（Comparison presets）

> 预设是可复用的查询配置，不是一个“总分公式”。快照日期：2026-08-27。每个 preset 都必须声明比较主体、benchmark 版本、协议要求和默认排序。

## 1. 基本原则

### 1.1 两种比较主体

| `subject` | 一行代表 | 默认 benchmark |
| --- | --- | --- |
| `model` | model release + prompt/decoding/evaluator | GPQA、MMLU-Pro、AIME、MMMU、LiveCodeBench 等单轮或固定解码评测 |
| `system` | model + endpoint + harness/agent + tools + environment + budget | SWE-bench、Terminal-Bench、τ-bench、BFCL、OSWorld、BrowserGym 等行动评测 |

同一模型在不同 harness 下是不同 system subject。页面默认先看 Model Atlas；进入 `System Runs` 后固定一个 harness 比模型，或固定一个模型比 harness。Agentic benchmark 不得把多个 harness 的最高值静默合并成“模型分数”。

### 1.2 严格可比性

只有下面的 fingerprint 全部相同才标 `exact` 并进入严格排名：

```text
benchmark suite/version/split
+ metric/unit
+ prompt/shots/answer extraction
+ reasoning effort / temperature / pass-k
+ tools / harness / environment / model endpoint
+ grader / judge / budget
```

否则标 `conditional`，仍可展示，但必须显示差异标签。不同指标（accuracy、resolved、Elo、latency、USD）不合成跨 benchmark 总分。[HELM](https://crfm.stanford.edu/helm/index.html) 的 reproducibility 思路、[Artificial Analysis methodology](https://artificialanalysis.ai/methodology) 对 model/endpoint/system 和成本/速度的区分，可作为实现参照。

## 2. Preset 配置形状

建议存放在 `data/catalog/presets.json`；UI 只读取配置，不在 JavaScript 中硬编码模型名单。

```json
{
  "id": "coding-agent",
  "label": "Coding agent",
  "subject": "system",
  "include": {
    "status": ["active", "previous", "preview"],
    "tags": ["coding", "agent"]
  },
  "benchmarks": [
    {"id": "swebench-pro", "version_policy": "same-version-only", "metric": "resolved"},
    {"id": "terminal-bench", "version_policy": "2.1-only", "metric": "pass_rate"}
  ],
  "protocol": {
    "harness_policy": "fixed-required",
    "effort_policy": "same-effort-or-split-columns",
    "environment_policy": "same-image-and-grader"
  },
  "display": {
    "sort": "per-benchmark-desc",
    "secondary_fields": ["harness", "effort", "cost", "latency", "evidence_level"]
  },
  "quality_gate": {"minimum_evidence": "B", "allow_conditional": true}
}
```

默认 `public-coverage` preset 会保留 `scoreCoverage: catalog-only` 条目作为覆盖地图中的无 canonical 分数行；这是派生的成绩覆盖状态，不是模型生命周期。其它窄 preset 可隐藏它们，用户也可打开“全量目录”查看完整注册表。未知参数、未知成本和未知上下文保持 `null`，不以 0 参与筛选。

## 3. Benchmark 映射

下表是第一版 benchmark registry 的建议映射。具体版本、split、metric 和 source 必须在 `data/catalog/benchmarks.json` 中登记；同名 benchmark 的不同版本不能合并。

| 维度 | benchmark / 建议 version key | subject | 默认 metric | 协议要点 |
| --- | --- | --- | --- | --- |
| 通用知识与推理 | `mmlu-pro@v1`、`gpqa-diamond@v1`、`hle@full`、`livebench@date` | model | accuracy / score | 明确 tools、shots、judge 和滚动日期；HLE text/image 分开 |
| 数学与科学 | `aime@year`、`hmmt@year`、`frontiermath@tier`、`imo-answerbench@version` | model | pass@1 / avg@k | 年份、采样次数、工具和答案抽取必须相同；不要把 avg@32 与 pass@1 混排 |
| 静态代码 | `livecodebench@v6`、`evalplus@version`、`bigcodebench@version` | model | pass@1 / pass@k | rolling window、语言集合和执行器固定；有 agent loop 时移至 system |
| 软件工程 Agent | `swebench-verified@500`、`swebench-pro@version`、`deepswe@1.1`、`nl2repo@version` | system | resolved / pass rate | 固定 harness、容器镜像、patch policy、预算和 grader；[SWE-bench](https://www.swebench.com/) |
| 终端执行 | `terminal-bench@2.1`、`terminal-bench@3.0` | system | pass rate | Agent、model、effort、cost、hacks 分列；版本不可混合。[Terminal-Bench](https://www.tbench.ai/news/terminal-bench-2-1) |
| 工具调用 | `bfcl@v4`、`tau-bench@version`、`toolathlon@verified` | system | accuracy / pass^k / pass@1 | native function calling 与 prompt workaround 分开；τ-bench 记录 pass^k 可靠性。[BFCL](https://gorilla.cs.berkeley.edu/leaderboard)、[τ-bench](https://taubench.com/) |
| 办公/工作流 | `gdpval-aa@v2`、`automationbench@version`、`coworkbench@version` | system | Elo / success / score | 任务池、工具、人工/LLM judge 和 token budget 必须公开；Elo 不转百分比 |
| 多模态理解 | `mmmu@original`、`mmmu@pro`、`mathvista@version`、`video-mme@version` | model 或 system | accuracy / score | 输入模态、分辨率、视频采样和工具单独记录 |
| 电脑使用 | `osworld@2.0`、`androidworld@version`、`browsergym@version` | system | binary/partial success | OS 镜像、浏览器版本、动作预算和截图/DOM 工具固定；[OSWorld 2.0](https://arxiv.org/abs/2606.29537) |
| 长上下文与检索 | `ruler@version`、`longbench-v2@version`、`aa-lcr@version` | model 或 system | accuracy / retrieval score | 按 128K/256K/1M context bucket 分层；不能只按声明的最大 context 排名 |
| 中文与多语言 | `ceval@version`、`cmmlu@version`、`superclue@arena`、`mmmlu@version`、`swe-multilingual@version` | model 或 system | accuracy / resolved | 语言、翻译、代码库和 judge 分开；中文榜不与英文总榜合并 |
| 可靠性与事实性 | `simpleqa@version`、`facts@version`、`pass^k@protocol` | model 或 system | accuracy / pass^k | 重复运行、置信区间、拒答和引用正确性一起展示 |
| 安全与网络能力 | `cybergym@version`、`exploitbench@version`、provider safety card | system 或 model | vulnerability success / safety rate | 仅展示获授权、可公开的 aggregate；安全限制/fallback 作为 protocol 字段 |
| 部署与效率 | 非单一题集：`usd_per_task`、`ttft_ms`、`output_tok_s`、`e2e_latency_ms`、`vram_gb` | endpoint/system | lower-is-better metrics | 与质量列并列做 Pareto；成本和速度必须带日期、region、batch、缓存口径 |
| 人类偏好（发现用） | `arena@date`、`artificial-analysis@date` | system/provider | Elo / preference | 只作发现和趋势，不与客观 benchmark 混成总榜 |

## 4. 首批预设

### P0 · Frontier current

- **主体**：`model`；另提供同名 `system` 子页。
- **选择**：每个 family 最近的 `active` release；`preview/restricted` 显示徽标但默认不进严格排名；每个 family 可展开一代 `previous`。
- **benchmark**：GPQA、MMLU-Pro、HLE、AIME、MMMU、LiveCodeBench；有官方 system run 时在右侧显示链接。
- **排序**：各 benchmark 独立降序；不生成综合分。

### P1 · Latest vs previous

- **主体**：`model` 或固定 system。
- **选择**：同一 family 的最新 release 与上一代 release；只保留共同 benchmark version/protocol。
- **输出**：显示 `latest - previous`、绝对分数和缺失原因；若协议变化则标 `conditional`，不计算增量。

### P2 · Flash / Fast efficiency

- **主体**：`model`（静态质量）+ `endpoint/system`（成本速度）。
- **选择**：名称含 Flash/Fast 只是候选标签；最终按价格 tier、TTFT、output tok/s、context 和 active params 验证。可包括 GPT-5.6 Luna、Gemini Flash、DeepSeek V4 Flash、Qwen3.8 Flash-Next、GLM-5.3-Flash、Kimi K2.7 HighSpeed、MiniMax HighSpeed、MiMo V2.5。
- **benchmark**：GPQA/MMLU-Pro/LiveCodeBench + Terminal-Bench/Toolathlon（固定 harness）；效率指标做 Pareto，不给单一“性价比总分”。

### P3 · Fast / resource-efficient candidates（legacy id: `small-efficient`）

- **主体**：`model` + deployment facts。
- **选择**：这个兼容 preset 同时收录两类候选：有来源支持的较小权重/active-parameter 档，以及带 Flash/Fast/Highspeed/UltraSpeed 等服务标签的效率端点。后者可能来自巨大 MoE，不能称为“小模型”。
- **benchmark**：MMLU-Pro、GPQA、AIME、LiveCodeBench、BFCL；另列 quality、cost、latency、memory。
- **规则**：先按“可核验规模档”与“托管效率端点”分组；dense 与 MoE 再分组。只有 source-backed `params_total` / `params_active` 才进入规模筛选；实际成本、VRAM、TTFT 和吞吐必须带 deployment 条件。active 参数和 total 参数不能互换排序，产品标签也不能替代实测效率。

### P4 · Math / science

- **主体**：`model`。
- **benchmark**：AIME（按年份）、HMMT、FrontierMath T1–T3/T4、GPQA Diamond、HLE、IMO-AnswerBench。
- **协议**：同一 answer extraction、tools、max completion、effort、pass@k；`avg@32`、`pass@1`、工具增强结果拆列。

### P5 · Static coding

- **主体**：`model`。
- **benchmark**：LiveCodeBench v6、EvalPlus、BigCodeBench、MultiPL-E。
- **协议**：不允许外部 agent loop；记录语言、编译器、test timeout、pass@k 和 rolling window。

### P6 · Coding agent

- **主体**：`system`（固定 harness 必须）。
- **benchmark**：SWE-bench Verified/Pro、Terminal-Bench 2.1、DeepSWE 1.1、NL2Repo、SWE-Multilingual。
- **显示**：模型、harness、effort、环境、预算、cost/task、resolved rate、CI、失败原因分列。若官方榜已固定 harness，仍记录其版本。

### P7 · Harness A/B

- **主体**：固定 `model + benchmark`，比较不同 harness/system。
- **benchmark**：Terminal-Bench、SWE-bench Pro、DeepSWE、OSWorld。
- **输出**：scaffold uplift、步数、工具调用数、token、延迟和失败类型；不把 uplift 归因于模型本身。

### P8 · Tool / workflow agents

- **主体**：`system`。
- **benchmark**：BFCL v4、τ-bench、Toolathlon Verified、GDPval-AA v2、AutomationBench、CoWorkBench。
- **协议**：工具 schema、native FC/prompt workaround、user simulator、pass^k、judge 和预算必须一致。

### P9 · Multimodal / computer use

- **主体**：普通图文题用 `model`；GUI/浏览器题用 `system`。
- **benchmark**：MMMU/Pro、MathVista、Video-MME、OSWorld 2.0、AndroidWorld、BrowserGym。
- **显示**：输入模态、分辨率、视频帧率、操作系统/浏览器、截图/DOM/视觉工具和动作预算。

### P10 · Long context / retrieval

- **主体**：`model` 或带检索工具的 `system`。
- **benchmark**：RULER、LongBench v2、AA-LCR。
- **分层**：128K、256K、1M context buckets；同时显示 recall、needle accuracy、latency 和 token cost。声明的最大 context 不等于实测有效 context。

### P11 · Chinese / multilingual

- **主体**：静态题 `model`；多语言代码/工具题按 `system`。
- **benchmark**：C-Eval、CMMLU、SuperCLUE、MMMLU、SWE-Multilingual。
- **规则**：中文、英文、跨语言代码库分开；翻译提示和 judge 语言写入 protocol。

### P12 · Open-weight / deployment

- **主体**：`model` + deployment endpoint。
- **选择**：权重、许可证、可下载日期、量化格式、推理框架和硬件必须有来源。
- **显示**：params_total、params_active、context、VRAM、tokens/s、batch、量化和 license；质量只在同一 benchmark 口径下比较。

### P13 · Reliability / safety

- **主体**：`model` 或 `system`，取决于评测是否有工具。
- **benchmark**：SimpleQA、FACTS、pass^k、CyberGym、ExploitBench、安全 model card。
- **显示**：均值、CI/方差、拒答率、fallback rate、prompt-injection/hijack 结果；安全限制不隐藏在备注里。

### P14 · Scale watchlist（含 1T+/2T+/10T）

- **主体**：`model` metadata，不是能力排行榜。
- **选择**：只收官方 source-backed `params_total`；同时列 active、architecture、license、context。
- **规则**：未知参数排最后；1T、2T、3T 等可做筛选，`10T` 只有在出现可核验事实后才启用，不为占位模型补数字。

### P15 · Arena / human preference

- **主体**：`model`；Text、Vision、Document 等 Arena 子集分别列出。
- **指标**：Bradley–Terry rating、95% CI、votes、category 和 leaderboard snapshot date；rating 不是 accuracy，也不与其他 benchmark 合成总分。
- **来源**：优先使用 Arena 官方发布的 Hugging Face `leaderboard-dataset`；互动页面不做未文档化抓取。

### P16 · Arena / agent workflows

- **主体**：`system`（model + Arena workflow/harness）。
- **指标**：Agent Arena IPS 与 WebDev/Search rating 分开；保留 observation/session counts、CI、category 和日期。
- **规则**：固定 harness、工具策略和 snapshot 后再比较；候选数据必须先人工核对 model release 与 protocol。

## 5. UI 与更新约定

- preset URL 应可分享，例如 `?preset=coding-agent&version=terminal-bench@2.1`；筛选状态不写回 observation。
- 每个分数单元显示 `value · evidence · harness/effort`，点击展开完整 protocol 和 source locator。
- 默认列按 benchmark registry 顺序；同列只有在 `exact` 时显示排序徽标，`conditional` 只显示比较提示。
- `scoreCoverage: catalog-only` 与生命周期 `preview` / `restricted` 分开显示；`stale`、`conflict` 也用明确徽标，不用空白或 0 混淆。
- 自动更新流程只产生 candidate observations；人工确认后才进入 `approved`/默认矩阵。来源适配器应保存 URL、retrieved_at、published_at、hash 和 parser version。
