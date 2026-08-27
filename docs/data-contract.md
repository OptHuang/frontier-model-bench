# Data contract

本文档定义 Frontier Model Bench 的数据边界。它优先保证三件事：成绩可回溯、不同口径不被误合并、数据可以由脚本重复生成。当前 `data/models.json` 是便于快速发布的兼容性 seed；目标格式可以在不改 UI 的情况下逐步迁移。

## 1. 数据分层与目录

```text
data/
  catalog/
    models.json              # 模型 release registry
    model_profiles.json      # 可读的能力、endpoint、限制与来源补充
    benchmarks.json          # benchmark/version/metric registry
    benchmark_profiles.json  # 逐项任务、数据、协议与比较说明（非成绩）
    sources.json             # 来源 registry
    aliases.json             # source model name -> canonical model id (legacy/approved layer)
  observations/
    results.jsonl            # 规范化长表：每行一个 observation
  raw/<source_id>/<date>/
    manifest.json            # URL、抓取时间、状态、哈希、parser 版本
    payload.*                # 允许再分发时才保存原始 payload
  overrides/
    models.yaml              # 人工别名与显示名修正
    exclusions.yaml          # 撤回/排除规则，必须带理由
  derived/
    latest.json              # 最新已批准快照指针
    matrix.json              # 页面读取的宽表索引
    health.json              # 新鲜度、冲突、覆盖率
  public/
    evidence.jsonl           # 公开榜单 reported/unverified 长表
    unmapped.jsonl           # 尚未安全映射的完整候选
    unmapped-summary.json     # 按 source modelRef 聚合的 alias 审计索引
    alternatives.jsonl       # 已映射但超过页面限额的候选
```

`raw` 是不可变证据层，`observations` 是可审计事实层，`derived` 是可丢弃的构建产物。页面不应直接解析来源网页，也不应把 UI 排名写回事实层。

公开榜单结果另有一个平行的 `public/reported evidence` 层（由
`scripts/build_public_evidence.py` 生成）。它可以直接供页面展示大量来源报告值，但每行
必须带 `verified: false`、`reviewStatus: unreviewed`、来源 URL/locator/retrieved_at/hash，
并且不能参与 canonical atlas 的选值、排名或覆盖率。未安全映射的模型保留在
`data/public/unmapped.jsonl`，不能因为页面需要填满矩阵而猜测 canonical release。
仓库的 `data/public/model_aliases.json` 是一个 source-scoped、显式维护的同 release
别名注册表；它只保留高置信度的 endpoint/effort/上下文展示变体，原始 `modelRef`、
来源和 mapping evidence 仍写入公开行。无法安全归属的原名及其 benchmark/locator
摘要写入 `unmapped-summary.json`，完整行写入 `unmapped.jsonl`。
当来源表把 task score 与 token、latency、cost、eval/train count 等遥测混在一起时，公开行
仍完整保留，但必须写入 `matrixExcluded: true` 与 `matrixExcludedReason:
telemetry_metric`；这类行只进入可检索证据索引，不进入 Atlas 分数或 System Runs。

## 2. 当前 seed 兼容格式

当前 demo 文件是一个 JSON object：

```json
{
  "meta": {},
  "benchmarks": [],
  "models": [],
  "sources": []
}
```

每个 benchmark 至少有 `id`、`name`、`metric`、`scale`、`unit`、`direction` 和 `source`；每个 model 至少有 `id`、`name`、`provider`、`release` 和 `scores`。`scores` 是以 benchmark id 为键的 object，score object 至少有数值 `value`；推荐同时给出 `setting`、`sourceId` 和 `verified`。

模型目录的长文说明放在可选的 `data/catalog/model_profiles.json`，按 canonical
model id 索引。它承载 positioning、capabilities、endpoint、reasoning modes、
context/parameter 口径和 caveats；这些字段是带来源的目录事实，不是 benchmark
observation。`null`/空数组表示当前尚未从公开资料核验，页面应显示“未注明”，不得推断为
0 或“不支持”。`scripts/build_derived.py` 会把匹配 profile 合并到 `site.json` 的
`catalogModels[*].profile`，因此 profile 更新不会改写成绩长表。

模型生命周期与成绩覆盖必须分开：`status` 只表示 `active`、`previous`、`preview`、
`restricted` 或 `deprecated` 等身份/生命周期；“当前是否有 canonical score”是派生的
`scoreCoverage`。现有静态快照用 `catalogModels[*].catalogOnly` 表达这一层：`true`
等价于 `scoreCoverage: catalog-only`，`false` 等价于 `scoreCoverage: scored`。
`catalog-only` 不得写回 `status`，也不表示模型身份未确认；它只说明当前 canonical
observation 长表为空，公开披露层仍可能有未复现记录。

校验器保留这个形状是为了让静态 MVP 可以先运行。新增真实数据时，推荐把它转换成下面的长表；不要在 seed 的嵌套结构中继续增加只有某个页面理解的特殊字段。

## 3. 目标规范化实体

### 3.1 Model release

`family_id` 标识模型家族，`id` 标识可评测的具体 release 或 endpoint。日期版本、preview、reasoning 变体和 quantized 变体应使用不同的 `id`。

```json
{
  "id": "provider/family@release",
  "family_id": "provider/family",
  "name": "Display name",
  "provider": "Provider",
  "release_date": "2026-01-01",
  "status": "active",
  "aliases": [
    {"source_id": "hf", "value": "the name used by the source"}
  ],
  "access": "api",
  "modalities": ["text"],
  "variant": {"reasoning": false, "preview": false},
  "metadata": {"context_window": null, "license": null},
  "source_ids": ["src_model_card"],
  "updated_at": "2026-08-27T00:00:00Z"
}
```

上下文长度、价格、速率限制等会变化的属性不要当作永恒的 model metadata。规模扩大后使用 `model_facts.jsonl`，每行包含 `model_id`、`field`、`value`、`as_of` 和 `evidence_id`。

`scoreCoverage` 不是 canonical registry 的写入字段；构建产物按 observation 是否存在
计算它。尤其不要用 `status: catalog-only` 表示“暂无分数”。

### 3.2 Benchmark version and metric

benchmark 本体和具体版本分开。Live/滚动 benchmark 的月份、数据切片或 leaderboard snapshot 必须进入 `version_id`，否则无法解释时间线。

```json
{
  "id": "gpqa_diamond",
  "name": "GPQA Diamond",
  "category": "reasoning",
  "owner": "Benchmark owner",
  "homepage": "https://example.org/benchmark",
  "versions": [
    {
      "id": "gpqa_diamond@v1",
      "label": "v1",
      "released_at": "2025-01-01",
      "dataset_hash": null,
      "status": "active"
    }
  ],
  "metrics": [
    {
      "id": "accuracy",
      "label": "Accuracy",
      "unit": "percent",
      "scale": {"min": 0, "max": 100},
      "direction": "higher",
      "aggregation": "mean"
    }
  ],
  "protocol_schema": {
    "shots": "integer|null",
    "tools": "boolean|null",
    "judge_model": "string|null"
  },
  "comparability_notes": "版本、提示词或工具不同默认不直接比较"
}
```

`unit` 不是装饰信息。常见值包括 `percent`、`fraction`、`elo`、`seconds`、`usd` 和 `count`；不要为了画一张图而把 Elo 或 latency 强行缩放成百分比。

#### 3.2.1 Benchmark profile（目录深度说明）

`data/catalog/benchmark_profiles.json` 为每个 canonical benchmark 提供可读的背景资料，
并由 `build_derived.py` 透传到 `site.json` 的对应 benchmark。它只描述评测定义，不承载
模型成绩，也不能用来推断矩阵空白。每个 id 应至少包含以下五组字段：

```json
{
  "task": {"summary": "测什么", "input": "输入", "output": "输出"},
  "dataset": {"size": "规模或未固定说明", "splits": ["切分/track"], "availability": "公开状态"},
  "protocol": {"mode": "model/system/preference", "grader": "判定器", "tools": "工具与环境", "sampling": "采样与聚合"},
  "comparison": {"recommended": "建议怎样对齐", "avoid": "哪些结果不能混合"},
  "source_locator": "官方论文、数据卡或榜单中的定位提示"
}
```

规模只在官方来源明确给出时填写；动态榜单或保密评测使用“随 release/snapshot 变化”等
文字，不把未知数量猜成数值。`source_ids` 仍是可点击的原始链接，`source_locator` 用于
告诉读者应在该来源中查找哪一段；两者都不代表本站已经复现该 benchmark。

### 3.3 Source and evidence

`source` 描述可复用的来源，`evidence` 描述某次抓取或某个事实在来源中的具体定位。一个 source 可以支持很多 observation，但每个 observation 都应至少有一个 evidence id。

```json
{
  "id": "src_helm",
  "kind": "official_leaderboard",
  "publisher": "Stanford CRFM",
  "title": "HELM leaderboard",
  "url": "https://example.org/helm",
  "api_url": null,
  "license": null,
  "default_evidence_level": "A",
  "retrieval_method": "git",
  "update_cadence": "weekly",
  "staleness_after_days": 30
}
```

```json
{
  "id": "ev_20260827_helm_abc",
  "source_id": "src_helm",
  "source_url": "https://example.org/helm/runs/v1",
  "snapshot_path": "data/raw/src_helm/2026-08-27/payload.json",
  "retrieved_at": "2026-08-27T01:00:00Z",
  "published_at": "2026-08-26",
  "locator": "run=v1; table=leaderboard; row=model-x; column=accuracy",
  "sha256": "…",
  "parser_version": "helm-adapter@0.1.0"
}
```

如果许可证不允许再分发原始页面或题目，只保存 URL、locator、抓取元数据和哈希；不要把 benchmark 题目复制进仓库。

### 3.4 Observation（长表事实）

一行代表一个明确条件下的一个成绩。下面是最小可用形状；benchmark-specific 参数放在 `protocol.extra`，以免每加一个 benchmark 就修改公共 schema。

```json
{
  "id": "res_<stable-hash>",
  "model_id": "provider/family@release",
  "subject": {
    "type": "model",
    "system_id": null,
    "agent_id": null,
    "scaffold": null
  },
  "benchmark_id": "gpqa_diamond",
  "benchmark_version_id": "gpqa_diamond@v1",
  "metric_id": "accuracy",
  "value": 84.3,
  "raw_value": "84.3%",
  "uncertainty": {
    "type": "ci",
    "level": 0.95,
    "lower": 82.1,
    "upper": 86.0
  },
  "sample_size": 198,
  "split": "test",
  "subset": "diamond",
  "protocol": {
    "shots": 0,
    "prompt_template": "official-v2",
    "temperature": 0,
    "tools": false,
    "reasoning_mode": "default",
    "judge_model": null,
    "max_tokens": null,
    "harness": "lm-eval@v0.4.7",
    "budget": null,
    "seed": null,
    "extra": {}
  },
  "observed_at": "2026-08-20",
  "published_at": "2026-08-22",
  "status": "published",
  "evidence_level": "A",
  "comparability": "exact",
  "quality_flags": [],
  "evidence_ids": ["ev_20260827_helm_abc"],
  "notes": null
}
```

agent benchmark 必须把 `system_id`/`agent_id`、scaffold、harness 和预算写出来。相同模型在不同 agent 系统上的 `pass@1` 或 resolved rate 是不同 subject，不应在 UI 中伪装成同一个模型成绩。

建议把 `id` 与以下 observation key 分开：

```text
observation_key = hash(
  subject_id, benchmark_version_id, metric_id,
  protocol_fingerprint, observed_at, source_id
)
```

同一条件来自两个来源时保留两条事实，通过 `preferred` 或治理规则指定展示值；不要覆盖旧记录，也不要未经说明地取平均。

## 4. 缺失、冲突和新鲜度语义

| 情况 | 规范表示 | 页面表示 |
| --- | --- | --- |
| 尚未收录 | 没有 observation 行 | `—` 未报告 |
| 来源明确说无法评测 | `value: null` + `missing_reason` | `—` 不可用 |
| 来源暂时不可访问 | 保留最近 approved 行 + `stale` flag | 旧值 + 过期标记 |
| 同条件来源分歧 | 两条或多条 observation + `conflict` | 值 + 冲突提示 |
| 真实得分为零 | `value: 0`，不能有 missing 标记 | `0` |
| 破折号/空字符串占位 | 禁止作为 value | 校验失败 |

`observed_at` 是评测发生或结果对应的时间，`published_at` 是原作者公布时间，`retrieved_at` 是本项目抓取时间；三者不要互换。`staleness_after_days` 按 source 或 benchmark 设置，`latest` 只从 approved、未撤回的记录中按观测时间选择。

## 5. 证据等级与可比性

`evidence_level` 是治理提示，不是对科学质量的绝对判断：

- `A`：benchmark owner 官方榜单，或含原始运行产物、可复现协议的独立评测。
- `B`：provider model card/technical report；协议完整但属于 self-report。
- `C`：方法和设置公开的可信第三方榜单。
- `D`：二手报道、无协议截图或无法核验的数字；默认只进入候选区。

`comparability` 的取值为 `exact`、`conditional`、`none`。即使两个值都来自 A 级来源，benchmark version、prompt、shot、工具、judge、scaffold 或预算不同，也只能标 `conditional` 或 `none`。

## 6. Source adapter 更新契约

每个 adapter 实现如下逻辑（语言不限）：

```text
fetch()  -> RawSnapshot
parse(snapshot) -> CandidateObservation[]
```

`RawSnapshot` 至少含：`source_id`、请求 URL、HTTP 状态、抓取时间、ETag/Last-Modified（若有）、payload hash 和 parser 版本。`parse` 不得直接写 UI 文件；它只能产出候选事实。

建议的流水线：

1. 定时任务（每日或按 source cadence）抓取，遇到 ETag 未变化则不产生新事实。
2. 保存 raw manifest，解析 candidate，解析 model alias 和 benchmark version。
3. 校验必填字段、单位、范围、重复键、来源和时间；分数大幅跳变或 protocol 缺失只警告/进入候选。
4. 以 PR 形式提交 raw + normalized diff；人工确认冲突、撤回和许可证问题。
5. 合并后构建 `derived` 和 GitHub Pages；失败时保留上一版站点并报告 health 状态。

不要把 API token 写入仓库；私有来源通过 GitHub Actions secret 拉取，并在公开产物中只留下允许披露的事实和链接。

## 7. 新增数据 checklist

### 新 benchmark

- [ ] 注册稳定 `id`、owner、主页和版本。
- [ ] 为每个 metric 写 unit、scale、direction、aggregation。
- [ ] 说明 split、shot、prompt、工具、judge、scaffold 等可比条件。
- [ ] 注册 source、许可证、抓取方式和 staleness 阈值。
- [ ] 添加一个真实 fixture 和 parser/范围测试。

### 新模型

- [ ] 选择具体 release/endpoint id，并记录 family、provider、发布日期和 aliases。
- [ ] 不把 preview、reasoning、量化版本合并成同一 id。
- [ ] metadata 和每个可变属性都带 source/evidence 和 as-of 日期。

### 新成绩

- [ ] 指定 benchmark version、metric、split/subset 和完整 protocol。
- [ ] 填 `observed_at`、`published_at`（已知时）和 evidence locator。
- [ ] 选择 evidence level 与 comparability，写 quality flags。
- [ ] 缺失使用缺失语义，不填 0、不填 `—` 字符串。

## 8. 从 demo 迁移到长表

迁移可以分三步完成：

1. 保留 `data/models.json` 作为 UI fallback，同时新增 `catalog` registry；给每个当前 model 生成 release id 和 alias。
2. 将 `models[*].scores[*]` 展开成 `observations/results.jsonl`，把原来的 `setting` 映射到 `protocol`，把 `sourceId` 映射到 evidence。
3. 生成 `derived/matrix.json`，让 UI 只读 derived；当长表通过一段时间的校验后，再删除 nested fallback。

迁移期间仍应保留 seed 的来源与状态标记，直到存在可点击的真实来源定位。任何“overall”或趋势线都应标明它是导航性派生值，而非跨 benchmark 的科学结论。
