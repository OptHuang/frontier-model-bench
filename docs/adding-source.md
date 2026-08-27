# 添加一个公开数据源

本仓库的抓取器只生成可审阅的 candidate artifact，不会修改
`data/catalog/`、`data/observations/results.jsonl` 或线上页面。适配器采用
`fetch(client) -> AdapterRun`、`parse_payload(bytes, run) -> candidates` 两步契约，
仅依赖 Python 标准库。

## 先运行现有适配器

```bash
python3 scripts/fetch.py list
python3 scripts/fetch.py fetch \
  --sources hf-swebench-verified,swebench-official \
  --dry-run --fail-on-error
```

默认结果写到 `artifacts/fetch/`（该目录是候选报告，不是批准数据；每次运行还会
保留带时间/hash 的 snapshot manifest）。如果要把
候选报告作为本地审阅材料保存，使用 `--save-payload` 前先确认来源许可证：

```bash
python3 scripts/fetch.py fetch --sources livebench-official --save-payload
```

`check --dry-run` 是定时任务的安全入口；它解析并报告候选，但不保存完整 payload。
`--retrieved-at` 可固定时间，便于 fixture 测试。`--max-bytes` 和
`--max-candidates` 始终保留上限，避免来源失控。

Arena 适配器的定时默认值是每个 config 读取一页（100 行），以避免 Dataset
Viewer 限流；需要人工分批补全时可以显式指定范围和上限，例如：

```bash
python3 scripts/fetch.py check --sources lmarena-hf-dataset \
  --arena-configs text,text_style_control --arena-max-rows 500 \
  --output-dir /tmp/fmb-arena-refresh
```

`--arena-configs all` 可发现数据集中的全部 Arena subset，但应分批运行并检查
`429`/`truncated` 警告。

## 生成 candidate 审阅包

抓取完成后可以用只读审阅 helper 把各来源的 `candidates.jsonl` 汇总成一个
去重、分级的 Markdown/JSON 队列：

```bash
python3 scripts/review_candidates.py \
  --root . \
  --input-dir artifacts/fetch \
  --output-dir artifacts/review \
  --limit 50
```

`review.json` 会记录每个候选的 exact-alias 建议、canonical reference/protocol/
evidence 检查、来源 manifest 定位和 `decision: pending`；`review.md` 适合在
PR/Issue 中逐条核对。`--limit 0` 可输出全部候选，摘要仍按去重后的全量统计。
输出目录不得位于 `data/` 或输入 artifact 内；helper 永远不会把候选写进
`data/observations/results.jsonl`。接受某一行后，维护者仍需手工核对并追加
canonical observation，再运行构建和 strict 校验。

## 新适配器最小要求

在 `scripts/adapters/` 新增模块并注册到 `all_adapters()`：

1. `SourceSpec` 写清稳定 URL、publisher/kind、更新 cadence、parser version 和许可证/不确定性备注。
2. `fetch` 保留请求 URL、最终 URL、HTTP 状态、ETag/Last-Modified、抓取时间和 payload hash。
3. `parse_payload` 保留源模型名、benchmark/version 原文、metric/unit、原始值、rank、locator 和协议字段。
4. 用 `make_candidate` 生成候选；适配器不要猜 canonical model id。CLI 只会对
   catalog 中完全相同的 id/name/alias 做 `exact_alias` 注释，模糊匹配仍保持
   `unmatched`，有歧义则标 `ambiguous_alias`。
5. 缺失值保持 `null`/缺失标记并加 `quality_flags`，绝不能把 `—` 变成 0。
6. system/agent 结果写入 `protocol.harness`、`scaffold` 或 `subject_type`，不能伪装成 model-only 分数。
7. 解析异常写入 `run.errors`，不要吞掉错误，也不要让单个来源阻断其他来源的报告。

建议为每个解析器放一个小 fixture，并运行：

```bash
python3 -m py_compile scripts/fetch.py scripts/adapters/*.py
python3 scripts/fetch.py check --sources <adapter-id> \
  --input tests/fixtures/<payload> --dry-run --fail-on-error
```

## 当前来源策略

- Hugging Face leaderboard API：支持 SWE-bench、HLE、MMLU-Pro、GPQA、Terminal-Bench、AIME/HMMT 等 dataset leaderboard；保留 `verified`、model card URL、PR 和 filename。
- SWE-bench official JSON：保留 Verified/Lite/Test/Multilingual/Multimodal 等 variant，并标出 agent/scaffold 与 checked 状态。
- LiveBench official repository：通过 GitHub tree 选择最新日期 CSV，记录 release date 和 task 列。
- Stanford HELM：从公开 `config.js` 解析最新 release，再读取 JSON artifact；保留 HELM 原生 fraction/seconds 等单位，不强行改成百分比。
- LMArena / Chatbot Arena：互动页面仍是 metadata-only、`enabled=false`；新增的 `lmarena-hf-dataset` 从 Arena 官方发布的 Hugging Face `leaderboard-dataset` 读取 `latest` split，按 Dataset Viewer 每页最多 100 行分页覆盖 `text`、`vision`、`webdev`、`search`、`document`、`agent`，默认每个 config 只抓一页（超出总量会显式 warning/truncated，避免 429；人工刷新可显式提高上限）。它保留 Elo/IPS、95% CI、votes/observations、category、发布日期和 row locator。互动页面没有稳定 API，仍不要抓取临时前端 bundle、截图或猜 Elo。
- Agents' Last Exam（ALE-V1）：官方页面当前使用公开 JSON endpoint `/api/demo/leaderboard`；适配器保留 `full`、`linux_only`、`near-term`、`full-spectrum`、`last-exam` 及 licensed/unlicensed split，并将每行的 Pass Rate 与 partial Score 分成两个候选 metric。ALE 是 `system` benchmark，source harness（如 Codex、Claude Code、ALE-Claw）和 effort variant 必须留在 protocol；接口没有稳定的 published date 时只记录 retrieved time/hash，不把抓取时间冒充 observed date。SakanaAI 的 ALE-Bench 另有 catalog 条目，因许可证与 judge/hardware 口径不同暂不自动抓取。
- Berkeley Function Calling Leaderboard（BFCL-V4）：官方 `data_overall.csv` 可机器读取；适配器保留 native `FC` 与 `Prompt` workaround、固定 evaluator commit、overall accuracy、成本、均值/标准差/P95 latency 及分类子指标。BFCL 设为 hybrid/tool-use benchmark；不同 calling mode、版本或 evaluator 不能合并排名，所有新行先进入 candidate。

## 从 candidate 晋升为 approved observation

candidate 不能直接复制到 canonical JSONL。维护者必须核对：

- source model name 是否能唯一映射到已登记 release/endpoint；
- benchmark version、metric、unit、direction、split/subset；
- model-only 与 system/harness/scaffold 的边界；
- observed/published/retrieved 日期、原始 locator、证据级别和许可证；
- 与已有记录是 `exact`、`conditional` 还是 `none`，以及是否存在冲突。

核对后手工追加 observation（旧值用 `superseded`/`retracted` 标记，不覆盖），再运行：

```bash
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
git diff --check
```

定时抓取失败或 parser 改版只应产生 warning/candidate；上一次 approved 快照仍然有效。
