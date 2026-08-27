# Public / reported evidence layer

`data/observations/results.jsonl` 是严格核验后的 canonical facts；它不会因为
一个公开榜单出现数字就自动改变。为了让页面先展示“外部已经报告了什么”，仓库另有
一层 `public/reported evidence`：每一行保留原始模型名、公开分数、版本、协议、来源
链接和抓取哈希，但明确标记为未复现。

## 输出

```text
data/derived/public.json    # 页面加载的精选索引（默认每组最多 3 条）
data/public/evidence.jsonl  # 与 public.json rows 相同的长表导出
data/public/unmapped.jsonl  # 未安全映射的完整剩余候选，供后验审阅
data/public/alternatives.jsonl # 已映射但超过页面限额的其它协议/版本
```

`public.json` 的每个 row 至少包含：

- `modelRef` / `canonicalModelId` / `mappingStatus`：来源原名和可选目录映射；未知 alias
  不会被丢弃。
- `benchmarkId` / `benchmarkVersionId` / `metricId` / `value` / `unit`。
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
  --input-dir /tmp/fmb-public-audit-v2 \
  --input-dir /tmp/fmb-ale-audit \
  --generated-at 2026-08-27T07:00:00Z
```

默认每个 `model × benchmark × metric × source` 组保留 3 条最高优先级记录（目录映射、
官方证据等级、featured benchmark、当前 release、数值完整度优先）。用
`--max-per-key N` 调整；无安全映射的行完整写入 `data/public/unmapped.jsonl`，已映射但超出
限额的行写入 `data/public/alternatives.jsonl`。重复刷新会按
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
