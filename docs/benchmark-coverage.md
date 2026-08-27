# Benchmark 覆盖审计

> 快照日期：2026-08-28。本文解释“矩阵空白”的证据状态；它不是一张新的成绩表，也不把候选数据当作已发布结果。

## 结论

矩阵缺失不等于没人测过。页面现在同时读取两层数据：`canonical observations` 是已经
完成身份/版本/协议核对的事实；`public/reported evidence` 直接收录公开 leaderboard、
模型卡和 provider 披露值，并在单元格与详情中标记 `披露 · 未复现`。后者可以帮助快速
填满信息地图，但不参与 canonical 排名，也不被描述成本站实测。

因此，一个空单元可能属于以下四种状态；公开层还有一条独立的“已报告但未映射”队列：

| 状态 | 含义 | 页面/维护动作 |
| --- | --- | --- |
| `catalog-only` | 已确认模型或 benchmark 存在，但尚无可发布的 observation | 默认公开覆盖视图保留无分数行；不参与成绩计算或排名 |
| `reported / unreviewed` | 公开来源已经给出数字，本站尚未复现或逐条核对 | 进入矩阵，显示 `披露 · 未复现`；点击查看 URL、locator、时间、hash 和 protocol |
| `candidate` | 已从公开来源发现结果，但缺值或仍需身份、版本、协议、指标审核 | 进入公开索引/Actions review packet，显示候选标记 |
| `approved` | 已核对并追加到 canonical observation 长表 | 进入对应 Model Atlas 或 System Runs |
| `no-public-result` | 截至检索日没有找到可核验的公开结果，或官方明确限制公开 | 记录检索日期和原因，不能推断为未测试 |

公开来源的 model alias 无法安全映射时，原始名称仍保留在 `data/public/unmapped.jsonl`
及其 `unmapped-summary.json` 审计索引和维护 artifact，但不会被猜测成另一个
canonical release。

## 当前精确快照

统计对象不同，数字会不同，不能把它们混为“已经收录的成绩数”：

- 目录有 **100 个模型 / 配置条目、53 个 canonical benchmark 定义、88 个来源、15 个 harness**（另有 19 个比较预设）；Benchmarks 页面还从公开证据生成 **73 个 public-only slices**，合计可浏览 **126 项**。
- canonical 文件当前有 **15 行**；构建后的站点索引包含 **47 个 runs/observations**（其中 **32 行**是兼容旧 schema 的 legacy 记录）。
- 有数值的 canonical 已观察模型为 **9 个**，仅目录模型为 **91 个**；已观察的模型×benchmark 单元为 **29 个**，按全目录口径覆盖率为 **0.5%**。维护报告按 active 集合和 freshness 口径计算时可能显示不同百分比，这是分母不同，不是数据丢失。
- 公开层本次 union 合并 **21,227 条去重报告行**（18 个来源、128 个 raw benchmark 切片；其中 99 个切片出现在 mapped rows、724 个 source×原始模型名键）；其中 **21,129 条**带数值，**6,461 条**能以 exact/heuristic/curated alias 映射到目录（alias registry 当前 **129 条**显式 source-scoped 规则，产生 **2,830 条**curated rows）。这些 mapped rows 以本地默认 `--max-per-key 0` **全部载入** `public.json`/`evidence.jsonl`，覆盖 **2,750 个** mapped model×benchmark 单元（细分为 **3,064 个** model×benchmark×metric slices；270 条 telemetry 原始行对应 **240 个**仅证据 metric 单元，实际 performance slices 为 **2,824**）；**14,766 条**未安全映射行完整保存在 gitignored `data/public/unmapped.jsonl`，并由 `data/public/unmapped-summary.json` 按来源原名聚合索引（**1,591 个**原名组）。因默认不设上限，`alternatives.jsonl` 当前为空；需要轻量预览时可显式传入正数 cap。这不是删除，而是把无法安全归属的记录与可展示记录分层。
- 公开层的 performance 行进入可见矩阵；只有 system-scoped 行进入 System Runs，token、latency、eval/train count 等 telemetry 保留在证据索引但明确不进成绩。所有公开行始终带 `reported/unreviewed/verified:false/not_reproduced`，且不改变上面的 canonical 统计。因而页面看到的覆盖会明显高于 **0.5%**，但应理解为“公开报告覆盖”，不是本站复现率。
- Agents’ Last Exam 官方接口返回 **713 行** `model × harness × variant/effort × split`（两个核心 metric 共 **1,426 条**），现已进入公开层；同一模型的不同 harness、split 和 effort 会保留为不同 run，不取最高值冒充裸模型。Epoch AI 的可下载快照另带来 **5,697 条**跨 benchmark 报告行；不同表的单位（百分比、fraction、Elo、rank、raw score）在页面上分开显示，不强行归一化。

这解释了为什么“公开层覆盖率”和“canonical 覆盖率”必须分开：前者回答“外部已经报告
了什么”，后者回答“本站已经核对并愿意作为可复现事实维护什么”。

## 已连接的公开来源

当前 adapter 已覆盖或可读取以下来源。抓取结果先进入 candidate artifact；固定快照经
`build_public_evidence.py` 生成后，数值完整的安全映射行可直接作为 `reported` 展示，
仍不等于 approved：

- Hugging Face 上的 SWE-bench Verified/Pro、HLE、MMLU-Pro、GPQA、Terminal-Bench、AIME/HMMT 数据集榜单接口；接口发现和 leaderboard 数据约定见 [Hugging Face leaderboard data guide](https://huggingface.co/docs/hub/leaderboard-data-guide)。
- [LiveBench](https://github.com/livebench/livebench) 与 Stanford [HELM](https://crfm.stanford.edu/helm/index.html) 的公开结果。
- [Arena leaderboard dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)：包括 text、vision、webdev、search、document 和 agent 等历史/最新切片；Arena 还说明了其公开历史数据集的范围（[官方说明](https://arena.ai/blog/arena-leaderboard-dataset)）。Arena 的 Elo/偏好分、投票数和置信区间必须作为独立 system benchmark 保存，不能和 accuracy 混成总分。
- [Berkeley Function Calling Leaderboard (BFCL-V4)](https://gorilla.cs.berkeley.edu/leaderboard)：官方页面公开 `data_overall.csv`（本次抓取 109 行：67 native FC、35 Prompt、7 未注明），适配器保留固定 evaluator commit、成本/延迟和分类子指标；由于 calling mode 与工具协议是测量对象，候选进入 System Runs/待审核层。
- Agents’ Last Exam（ALE-V1）的 [官方说明](https://agents-last-exam.org/docs/ale/index.html)、[leaderboard](https://agents-last-exam.org/leaderboard) 与公开 JSON endpoint（[接口](https://agents-last-exam.org/api/demo/leaderboard)）。页面公开层会显示其报告值，详情中保留 split、harness、variant、locator 与抓取 hash。
- [Aider Polyglot](https://aider.chat/docs/leaderboards/) 的官方仓库 YAML、[OpenAI MLE-bench](https://github.com/openai/mle-bench/) README leaderboard，以及 [Epoch AI Benchmarking Hub](https://epoch.ai/benchmarks/use-this-data) 的 CC-BY 下载快照。三者都作为 `reported · 未复现` 展示；Epoch 的外部表保留原始许可和原始链接。
- [SWE-bench 官方 leaderboard 页面](https://www.swebench.com/) 的 [机器可读 JSON](https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json)（`swebench-official`）保留 bash-only、Verified、Multilingual 等 variant 以及 agent/scaffold、checked、cost 和 instance-call 字段；本次快照 370 行，其中 35 行安全映射、其余 alias 留在 unmapped 审计队列，全部标记 `reported · 未复现`。
- 目录 profile 还为 MathVista、Video-MME、RULER、LongBench v2 和 CyberGym 注册了各自的官方项目/论文链接；它们不再借用相邻 benchmark 的 homepage，详情抽屉会同时显示任务、数据切分、协议和 source locator。

## ALE 的正确建模

这里的 ALE 默认指 **Agents’ Last Exam**，不是单纯 model-only benchmark。官方定义的运行对象是 `Agent(harness) × Environment × Task`，并同时提供 Pass Rate（满分任务比例）与 Score（平均 partial-credit）。因此接入时应放在 **System Runs**：

`model release × endpoint × harness × effort/variant × ALE-V1 split`

至少保留 `pass_rate`、`score`、`runs/tasks`、split/track、harness、reasoning effort、cost、runtime、input/output tokens、retrieved_at 和来源 hash。不同 harness 或 split 不能取最高值后冒充模型分数；API 是公开可读接口，但页面没有承诺稳定 API，故仍需快照、parser 版本和人工审核。

**ALE-Bench 必须另列。** [SakanaAI/ALE-Bench](https://github.com/SakanaAI/ALE-Bench) 面向 AtCoder Heuristic Contest 的算法工程/优化问题，输出绝对分数、排名或性能，不是 Agents’ Last Exam 的 agent workflow 分数。另有 Arcade Learning Environment（[ALE 论文](https://arxiv.org/abs/1207.4708)）这一 Atari 强化学习含义，也不应与前两者共用 benchmark id。

## 已发现、但仍待接入或人工审核的重点 benchmark

以下项目有公开页面、代码、榜单或论文证据，但当前不应写成“已经纳入 canonical”；下一步应各自建立 versioned adapter/fixture，或先做人工快照：

| 优先级 | benchmark | 主要信息与接入注意事项 |
| --- | --- | --- |
| P0 | Agents’ Last Exam (ALE-V1) | 官方 system leaderboard；适配器已连接，公开层先显示 Pass Rate/partial Score，仍按 harness、effort、split 和模型 release 保留未复现标记。 |
| P0 | BFCL V4 | [Berkeley Gorilla leaderboard](https://gorilla.cs.berkeley.edu/leaderboard)；官方 CSV 适配器已连接（109 行公开报告），overall 是子类别未加权均值，详情保留 commit/version、calling mode 和 evaluator。 |
| P0 | BrowseComp | [OpenAI benchmark page](https://openai.com/index/browsecomp/)；1,266 个 browsing problems，需记录 agent/tool setting、effort 和评测日期。当前登记为 catalog-only：官方页面没有稳定 leaderboard API，后续以带日期的公开表或 provider report 作为 `reported` candidate。 |
| P0 | LiveCodeBench V6、Aider Polyglot | 时间切片、污染控制和 pass@1 不能与静态代码榜混合；Aider Polyglot 已接入官方仓库 YAML adapter（保留 edit format、版本与日期），结果仍为 `reported · 未复现`。 |
| P1 | Terminal-Bench 2.1、OSWorld、AndroidWorld | 真实环境/system benchmark；保留 harness、环境镜像、任务版本和预算。AndroidWorld 已登记 catalog-only，官方仓库列出任务、评测和 leaderboard：[Google Research AndroidWorld](https://github.com/google-research/android_world)。 |
| P1 | MLE-bench | [OpenAI repository](https://github.com/openai/mle-bench/)；README 主表已接入 adapter，按 Lite/Medium/High/All 拆列，保留 agent、LLM、运行时间、日期和 grading report 可用性；项目当前暂停新提交，结果仍标为 reported·未复现。 |
| P1 | Epoch Benchmarking Hub | [Epoch downloadable snapshot](https://epoch.ai/benchmarks/use-this-data)；ZIP 中的标准 benchmark、外部 leaderboard 和能力指数均保留原始文件/行定位。单位不一致的表显示为 `fraction`/`score`/`Elo`/`rank`，不参与跨指标排名。 |
| P1 | AssistantBench、GAIA、WebArena/BrowserGym | browsing/电脑使用 agent；AssistantBench 的公开入口见 [official site](https://assistantbench.github.io/)，需保留网页工具、成功定义和版本。 |
| P1 | ARC-AGI-2 | [ARC Prize official page](https://arcprize.org/arc-agi/2)；部分评测集/提交流程受限，不能把社区复现分数当作官方结果。 |
| P1 | ALE-Bench | 独立的算法工程 benchmark；单列 benchmark id、problem family、lite/full、hardware 和 judge version。 |
| P2 | FrontierMath、IMO-AnswerBench、Math-500、BBH、IFEval、HumanEval/MBPP、EvalPlus/BigCodeBench/MultiPL-E | 适合作为数学、推理和代码细分视图；需要防止旧版本、题目污染和不同 aggregation 被合并。 |
| P2 | τ-bench、Toolathlon、GDPval-AA、AutomationBench、CoWorkBench、CyberGym/ExploitBench | 重点是 tool、agent、安全或工作流协议；必须建成 System Runs，而不是普通模型列。 |
| P2 | RULER、LongBench v2、AA-LCR、C-Eval、CMMLU、SuperCLUE、MMMLU、视频/多模态系列 | 用于长上下文、中文和多模态分组；各自保留语言、模态、prompt、subset 与 judge。 |

“有公开页面”只说明可以建立 candidate，不等于已经完成可比性审查。尤其是 provider self-report、聚合站 intelligence index、动态 Arena 和截图，都需要回到原始协议与版本。

## 准入原则与补全顺序

一个结果进入 approved 前，必须能回答：这是哪个 canonical model release/endpoint？benchmark 的 version、split、metric、unit、direction 是什么？若是 agent，harness、scaffold、tools、environment、预算和 effort 是什么？observed/published/retrieved 日期是否分开？来源 locator、hash、许可证是否可追溯？在此之前，它仍可以作为 `reported` 进入页面，但必须保留原始名称、来源和“本站未复现”标识。

证据优先级为：benchmark owner 的官方榜单或可复现实验产物（A）→ provider model card/technical report（B）→ 协议完整的可信第三方榜单（C）→ 二手报道/截图（D，仅 candidate）。新数据采用追加式 observation；版本、协议或 snapshot 改变时新建记录，不覆盖旧值。

后续维护按以下顺序推进：

1. ALE、BFCL、Aider Polyglot、MLE-bench 与 Epoch Benchmarking Hub 适配器已完成；BrowseComp、AndroidWorld 已先纳入 benchmark/source catalog（明确 catalog-only 与抓取限制），待稳定机器可读表或许可的日期快照后再启用 candidate adapter，并把公开行批量转为可审核 candidate。
2. 再按当前 active/preview 模型补全 featured direct benchmarks，以及 GPT、Claude、Qwen、DeepSeek、Kimi、GLM、MiniMax、MiMo、小米等模型的同协议对照。
3. 最后扩展 flash/fast、小模型、数学、代码 agent、工具调用、多模态、长上下文、中文和开放权重等预设；旧模型保留历史记录，但从默认 frontier 视图淘汰。

详细的 candidate → public reported → approved 工作流、freshness 和 PR 审阅门槛见 [`docs/maintenance-plan.md`](maintenance-plan.md)；来源 adapter 接口见 [`docs/adding-source.md`](adding-source.md)。
