# Benchmark 覆盖审计

> 快照日期：2026-08-27。本文解释“矩阵空白”的证据状态；它不是一张新的成绩表，也不把候选数据当作已发布结果。

## 结论

矩阵缺失不等于没人测过。当前页面的矩阵只展示已经完成 model/benchmark/version/protocol/来源核对、并进入 `data/observations/results.jsonl` 的 canonical observations。公开榜单中已经存在的结果，如果身份、版本、harness、指标、日期或许可证还没有核实，会停留在 candidate artifact；只有模型身份已确认但暂时没有合格成绩时，才显示为 `catalog-only` 和 `—`，绝不显示为 0。

因此，一个空单元可能属于以下四种状态：

| 状态 | 含义 | 页面/维护动作 |
| --- | --- | --- |
| `catalog-only` | 已确认模型或 benchmark 存在，但尚无可发布的 observation | 保留目录，默认不参与排名 |
| `candidate` | 已从公开来源发现结果，等待身份、版本、协议、指标或证据审核 | 进入 Actions artifact/review packet，不进入矩阵 |
| `approved` | 已核对并追加到 canonical observation 长表 | 进入对应 Model Atlas 或 System Runs |
| `no-public-result` | 截至检索日没有找到可核验的公开结果，或官方明确限制公开 | 记录检索日期和原因，不能推断为未测试 |

## 当前精确快照

统计对象不同，数字会不同，不能把它们混为“已经收录的成绩数”：

- 目录有 **49 个模型 release、38 个 benchmark 定义、69 个来源、15 个 harness**（另有 19 个比较预设）。
- canonical 文件当前有 **15 行**；构建后的站点索引包含 **47 个 runs/observations**（其中 **32 行**是兼容旧 schema 的 legacy 记录）。
- 有数值的已观察模型为 **9 个**，仅目录模型为 **40 个**；已观察的模型×benchmark 单元为 **29 个**，按全目录口径覆盖率为 **1.6%**。维护报告按 active 集合和 freshness 口径计算时显示约 **1.3%**，这是分母不同，不是数据丢失。
- 对 **13 个**常规可机器读取的公开来源做只读抓取，本次快照解析 **11,367 条**、写入候选 artifact **9,724 条**（HELM lite 按维护上限截断并显式标记；BFCL 官方 CSV 为 109 行）；ALE 单独再发现 **713 行**，因每行同时有两个核心 metric，适配器生成 **1,426 条 metric candidates**。合并后的候选队列为 **11,150 条**，其中当前可由目录 exact-alias 注释的 **1,602 条**；候选不是 canonical：其中很多仍是未确认 alias、第三方提交或协议不完整的行。
- Agents’ Last Exam 官方接口返回 **713 行** `model × harness × variant/effort × split` 结果（两个 metric 共 1,426 条候选；其中 1,210 条可先做 exact-alias 注释）；它们尚未因“看到了数字”而自动晋升为 approved。当前适配器已注册，下一步是按 row locator/模型 release/协议逐批审核。

这解释了为什么当前页面看起来比公开信息稀疏：现阶段的统计分子是“可追溯且可比较的 approved observation”，不是“互联网上出现过的所有数字”。

## 已连接的公开来源

当前 adapter 已覆盖或可读取以下来源，抓取结果先进入 candidate 层：

- Hugging Face 上的 SWE-bench Verified/Pro、HLE、MMLU-Pro、GPQA、Terminal-Bench、AIME/HMMT 数据集榜单接口；接口发现和 leaderboard 数据约定见 [Hugging Face leaderboard data guide](https://huggingface.co/docs/hub/leaderboard-data-guide)。
- [LiveBench](https://github.com/livebench/livebench) 与 Stanford [HELM](https://crfm.stanford.edu/helm/index.html) 的公开结果。
- [Arena leaderboard dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset)：包括 text、vision、webdev、search、document 和 agent 等历史/最新切片；Arena 还说明了其公开历史数据集的范围（[官方说明](https://arena.ai/blog/arena-leaderboard-dataset)）。Arena 的 Elo/偏好分、投票数和置信区间必须作为独立 system benchmark 保存，不能和 accuracy 混成总分。
- [Berkeley Function Calling Leaderboard (BFCL-V4)](https://gorilla.cs.berkeley.edu/leaderboard)：官方页面公开 `data_overall.csv`（本次抓取 109 行：67 native FC、35 Prompt、7 未注明），适配器保留固定 evaluator commit、成本/延迟和分类子指标；由于 calling mode 与工具协议是测量对象，候选进入 System Runs/待审核层。
- Agents’ Last Exam（ALE-V1）的 [官方说明](https://agents-last-exam.org/docs/ale/index.html)、[leaderboard](https://agents-last-exam.org/leaderboard) 与公开 JSON endpoint（[接口](https://agents-last-exam.org/api/demo/leaderboard)）。

## ALE 的正确建模

这里的 ALE 默认指 **Agents’ Last Exam**，不是单纯 model-only benchmark。官方定义的运行对象是 `Agent(harness) × Environment × Task`，并同时提供 Pass Rate（满分任务比例）与 Score（平均 partial-credit）。因此接入时应放在 **System Runs**：

`model release × endpoint × harness × effort/variant × ALE-V1 split`

至少保留 `pass_rate`、`score`、`runs/tasks`、split/track、harness、reasoning effort、cost、runtime、input/output tokens、retrieved_at 和来源 hash。不同 harness 或 split 不能取最高值后冒充模型分数；API 是公开可读接口，但页面没有承诺稳定 API，故仍需快照、parser 版本和人工审核。

**ALE-Bench 必须另列。** [SakanaAI/ALE-Bench](https://github.com/SakanaAI/ALE-Bench) 面向 AtCoder Heuristic Contest 的算法工程/优化问题，输出绝对分数、排名或性能，不是 Agents’ Last Exam 的 agent workflow 分数。另有 Arcade Learning Environment（[ALE 论文](https://arxiv.org/abs/1207.4708)）这一 Atari 强化学习含义，也不应与前两者共用 benchmark id。

## 已发现、但仍待接入或人工审核的重点 benchmark

以下项目有公开页面、代码、榜单或论文证据，但当前不应写成“已经纳入 canonical”；下一步应各自建立 versioned adapter/fixture，或先做人工快照：

| 优先级 | benchmark | 主要信息与接入注意事项 |
| --- | --- | --- |
| P0 | Agents’ Last Exam (ALE-V1) | 官方 system leaderboard；适配器已连接并生成 Pass Rate/partial Score candidates，仍需按 harness、effort、split 和模型 release 批量审核。 |
| P0 | BFCL V4 | [Berkeley Gorilla leaderboard](https://gorilla.cs.berkeley.edu/leaderboard)；官方 CSV 适配器已连接（109 行 candidates），overall 是子类别未加权均值，必须固定 commit/version、calling mode 和 evaluator。 |
| P0 | BrowseComp | [OpenAI benchmark page](https://openai.com/index/browsecomp/)；1,266 个 browsing problems，需记录 agent/tool setting、effort 和评测日期。 |
| P0 | LiveCodeBench V6、Aider Polyglot | 时间切片、污染控制和 pass@1 不能与静态代码榜混合；先锁定版本与 evaluation window。 |
| P1 | Terminal-Bench 2.1、OSWorld、AndroidWorld | 真实环境/system benchmark；保留 harness、环境镜像、任务版本和预算。AndroidWorld 官方仓库列出任务、评测和 leaderboard：[Google Research AndroidWorld](https://github.com/google-research/android_world)。 |
| P1 | MLE-bench | [OpenAI repository](https://github.com/openai/mle-bench/)；Kaggle 机器学习工程任务，区分 Lite/Medium/High/All，当前榜单状态和 grading report 需随快照记录。 |
| P1 | AssistantBench、GAIA、WebArena/BrowserGym | browsing/电脑使用 agent；AssistantBench 的公开入口见 [official site](https://assistantbench.github.io/)，需保留网页工具、成功定义和版本。 |
| P1 | ARC-AGI-2 | [ARC Prize official page](https://arcprize.org/arc-agi/2)；部分评测集/提交流程受限，不能把社区复现分数当作官方结果。 |
| P1 | ALE-Bench | 独立的算法工程 benchmark；单列 benchmark id、problem family、lite/full、hardware 和 judge version。 |
| P2 | FrontierMath、IMO-AnswerBench、Math-500、BBH、IFEval、HumanEval/MBPP、EvalPlus/BigCodeBench/MultiPL-E | 适合作为数学、推理和代码细分视图；需要防止旧版本、题目污染和不同 aggregation 被合并。 |
| P2 | τ-bench、Toolathlon、GDPval-AA、AutomationBench、CoWorkBench、CyberGym/ExploitBench | 重点是 tool、agent、安全或工作流协议；必须建成 System Runs，而不是普通模型列。 |
| P2 | RULER、LongBench v2、AA-LCR、C-Eval、CMMLU、SuperCLUE、MMMLU、视频/多模态系列 | 用于长上下文、中文和多模态分组；各自保留语言、模态、prompt、subset 与 judge。 |

“有公开页面”只说明可以建立 candidate，不等于已经完成可比性审查。尤其是 provider self-report、聚合站 intelligence index、动态 Arena 和截图，都需要回到原始协议与版本。

## 准入原则与补全顺序

一个结果进入 approved 前，必须能回答：这是哪个 canonical model release/endpoint？benchmark 的 version、split、metric、unit、direction 是什么？若是 agent，harness、scaffold、tools、environment、预算和 effort 是什么？observed/published/retrieved 日期是否分开？来源 locator、hash、许可证是否可追溯？

证据优先级为：benchmark owner 的官方榜单或可复现实验产物（A）→ provider model card/technical report（B）→ 协议完整的可信第三方榜单（C）→ 二手报道/截图（D，仅 candidate）。新数据采用追加式 observation；版本、协议或 snapshot 改变时新建记录，不覆盖旧值。

后续维护按以下顺序推进：

1. ALE 与 BFCL 适配器已完成；下一步将 BrowseComp 和高价值代码/agent benchmark 做成带 fixture 的 adapter，并把官方公开行批量转为可审核 candidate。
2. 再按当前 active/preview 模型补全 featured direct benchmarks，以及 GPT、Claude、Qwen、DeepSeek、Kimi、GLM、MiniMax、MiMo、小米等模型的同协议对照。
3. 最后扩展 flash/fast、小模型、数学、代码 agent、工具调用、多模态、长上下文、中文和开放权重等预设；旧模型保留历史记录，但从默认 frontier 视图淘汰。

详细的 candidate-only 工作流、freshness 和 PR 审阅门槛见 [`docs/maintenance-plan.md`](maintenance-plan.md)；来源 adapter 接口见 [`docs/adding-source.md`](adding-source.md)。
