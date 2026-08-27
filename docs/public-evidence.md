# Public / reported evidence layer

`data/observations/results.jsonl` 是严格核验后的 canonical facts；它不会因为
一个公开榜单出现数字就自动改变。为了让页面先展示“外部已经报告了什么”，仓库另有
一层 `public/reported evidence`：每一行保留原始模型名、公开分数、版本、协议、来源
链接和抓取哈希，但明确标记为未复现。

## 输出

```text
data/derived/public.json    # 页面加载的公开索引（当前 union 快照载入全部已映射行）
data/public/evidence.jsonl  # 与 public.json rows 相同的长表导出
data/public/unmapped.jsonl  # 未安全映射的完整剩余候选，供后验审阅
data/public/unmapped-summary.json # 按来源模型原名聚合的可读 alias 审计索引
data/public/alternatives.jsonl # 已映射但超过页面限额的其它协议/版本
```

仓库随附的 2026-08-27 union 快照由 18 个带 manifest 的来源 artifact 生成：
21,227 条去重记录中 6,461 条已安全映射并全部载入页面（覆盖 2,750 个 model × benchmark
单元；3,064 个 model × benchmark × metric slices，其中 270 条 telemetry 原始行对应 240 个
仅证据 metric 单元，实际 performance slices 为 2,824）；14,766 条仍未映射的记录保存在
`unmapped.jsonl`；本地默认 `--max-per-key 0` 表示不设上限，因此
`alternatives.jsonl` 为空是有意的，而不是丢失数据（需要轻量预览时可传入正数 cap）。所有公开行仍标记
`reported/unreviewed/not_reproduced`。

新增的 `swebench-official` artifact 来自 [SWE-bench 官方 leaderboard 页面](https://www.swebench.com/) 发布的 [机器可读 JSON](https://raw.githubusercontent.com/swe-bench/swe-bench.github.io/master/data/leaderboards.json)：
原始快照含 370 行，保留 benchmark variant、agent/scaffold、checked、cost 和
instance-call 字段；其中 35 行可以安全映射到目录 release，其余原始 alias 仍在
`unmapped.jsonl` 中。它们都是来源披露值，尚未由本站独立复现。

`public.json` 的每个 row 至少包含：

- `modelRef` / `canonicalModelId` / `mappingStatus`：来源原名和可选目录映射；未知 alias
  不会被丢弃，而是进入 `unmapped.jsonl` 及其摘要索引。
- `benchmarkId` / `benchmarkVersionId` / `metricId` / `value` / `unit`。
- `matrixExcluded` / `matrixExcludedReason`：token、latency、eval/train count 等遥测仍可搜索和
  查看来源，但不会被误写进性能矩阵或 System Runs。
- `status`：`reported` 表示来源公开报告了数值，`candidate` 表示缺值或仍只有候选
  记录；`reviewStatus: unreviewed`、`verified: false`、`verificationStatus:
  not_reproduced` 始终保留。
- `harnessId`、`harness`、`subjectType`、`protocol`：同一模型的裸模型、工具调用和
  agent system 不混成一个值。
- `sourceUrl`、`sourcePageUrl`、`sourceApiUrl`、`evidenceUrl`、`sourceLocator`、
  `retrievedAt`、`payloadSha256`、`parserVersion`：点击来源并定位到具体行/模型卡所需的证据链。
- `benchmarkVersionHint` 与 `qualityFlags`：当来源没有明确 version id 或单位时，页面会显式显示提示；Epoch 等混合快照中的 `percent`、`fraction`、`Elo`、`rank` 和 `score` 不会被强行合成一个尺度。

## 生成

抓取器仍然只写候选 artifact；生成器可以合并多个快照目录：

```bash
python3 scripts/build_public_evidence.py \
  --root . \
  --input-dir "$ARTIFACT_ROOT/fmb-public-audit-final" \
  --input-dir "$ARTIFACT_ROOT/fmb-epoch-audit-v2" \
  --input-dir "$ARTIFACT_ROOT/fmb-aider-audit" \
  --input-dir "$ARTIFACT_ROOT/fmb-bfcl-audit" \
  --input-dir "$ARTIFACT_ROOT/fmb-mle-audit" \
  --input-dir "$ARTIFACT_ROOT/fmb-swebench-official" \
  --output data/derived/public.json \
  --jsonl-output data/public/evidence.jsonl \
  --unmapped-output data/public/unmapped.jsonl \
  --alternatives-output data/public/alternatives.jsonl \
  --unmapped-summary-output data/public/unmapped-summary.json \
  --max-per-key 0 \
  --generated-at 2026-08-27T16:21:44Z
```

`ARTIFACT_ROOT` 是本地维护工作区变量（不会写入产物）；每个目录应包含来源的
`manifest.json` 与 `candidates.jsonl`。刷新时可替换为新的 fetch 输出目录，保留
`generated-at` 只用于可重复比较，不代表来源观测日期。
本次固定快照来自 `fmb-all/swebench-official` 工作区 artifact；复制或映射到
`$ARTIFACT_ROOT/fmb-swebench-official` 后即可复用上面的可移植命令。

默认（`--max-per-key 0`）每个 `model × benchmark × metric × source` 组保留全部已映射记录；
若需要轻量预览，可用 `--max-per-key N` 保留 N 条最高优先级记录（目录映射、官方证据等级、
featured benchmark、当前 release、数值完整度优先）。无安全映射的行完整写入
`data/public/unmapped.jsonl`，已映射但超出限额的行写入 `data/public/alternatives.jsonl`。重复刷新会按
语义键去重并保留 snapshot count；同一定位出现不同数值时保留两行并加
`reported_value_conflict`。

显式 alias 首选；仅通过 provider basename、大小写/标点和常见 effort presentation suffix
得到的映射标为 `heuristic_alias`，仍然是未复现数据。日期、量化和 release suffix 不会被
自动剥掉，以免把旧版本误配到当前 release。

生成后的 `data/derived/site.json` 会在存在 `public.json` 时附带
`publicEvidence`、`publicMeta`、`publicStats`；这些字段只供展示，不参与 canonical atlas
选择、排名或覆盖率。

## 审阅关系

```text
公开榜单/API → scripts/fetch.py → artifacts/fetch/*/candidates.jsonl
            → scripts/build_public_evidence.py → public.json / evidence.jsonl
            → 人工核对 URL、release、protocol、metric
            → 小 PR 追加 data/observations/results.jsonl（approved/canonical）
```

因此页面可以直观比较已报告数字，同时不会把“来源声称”误写成“本项目已经复现”。
