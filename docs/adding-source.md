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
- LMArena / Chatbot Arena：当前仅 metadata-only、`enabled=false`。Arena 页面没有稳定、文档化的公开 score API；不要抓取临时前端 bundle、截图或猜 Elo。若以后获得可审计、可再分发的版本化快照，应新建显式 adapter 和 fixture。

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
