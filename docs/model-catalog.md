# 模型目录（Model catalog）

> 目录快照：2026-08-28。本文只登记模型身份、版本、可用性和可核验的静态事实；不在这里填写 benchmark 分数。分数必须进入 observation 长表，并带有具体 protocol、harness 和 evidence。

当前机器目录包含 **100 个 model / config entry**，并为每个条目提供 **100 个 profile**；其中少量显式 context/speed serving variant 为了覆盖地图单独展示，但不应被解读为新的基础模型 release。目录中的来源链接有时只代表 discovery/family scope 或公开榜单入口，未逐项完成官方型号确认；详情页会保留这一不确定性，不能把它当作本站独立核验。

2026-08-28 roster 扩充新增 15 个明确 release/endpoint 条目：OpenAI 4 个（GPT-5.4 Pro/nano、GPT-5 mini/nano），Qwen 4 个（Qwen3.5 35B-A3B/9B/Max Preview、Qwen3-Coder-Next），Google 4 个（Gemini 3.7/3.6/3.5 Flash 与 3.5 Flash-Lite），xAI 2 个（Grok 4.6/4.5），Z.ai 1 个（GLM-5V-Turbo）。同时，既有 `qwen/qwen3-coder@current` 已具体化为 Qwen3-Coder 480B-A35B；其 canonical id 保持不变。所有新增公开榜单拼写均按 source scope 显式映射，reasoning effort 保留在 protocol，未引入 floating `latest` alias。

## 1. 目录的边界

目录回答“这是什么模型、哪个版本、从哪里调用、现在是否还值得比较”；`data/observations/` 回答“在什么条件下得到什么结果”。一个模型可以没有任何分数（派生的 `scoreCoverage: catalog-only`），但它仍保留自己的 `active` / `previous` / `preview` / `restricted` 生命周期；一条分数则不能没有规范化的 `model_id`。

模型、endpoint、harness 和 system 不是同一个实体：

```text
family → release → endpoint/snapshot → harness/agent → evaluation run
```

例如 `gpt-5.6` 是 OpenAI 的 alias，而 `gpt-5.6-sol` 是 API model id；二者不能在目录中重复算作两个 release。[OpenAI API model catalog](https://developers.openai.com/api/docs/models)

当前快照为可读性保留了少量带 `context_variant` / `speed_variant` 标记的 serving 配置（例如 Kimi 256k、Highspeed、UltraSpeed）；它们用于单独查看端点和效率信号，基础模型身份仍由 family/release 与 alias 规则约束。

Agent benchmark 的被测对象应是 `model + endpoint + harness + tools + environment + budget`。静态问答 benchmark 通常以 model 为主体，但仍要记录 prompt、shots、reasoning effort、temperature 和 judge。

## 2. 状态和可用性

`status` 是面向页面的生命周期标签；`availability` 单独描述调用权限。这样“上一代但仍可调用”和“当前但仅限早期访问”不会混在一起。

| status | 含义 | 默认视图 |
| --- | --- | --- |
| `active` | 官方资料显示为当前正式 release；仍可加入默认矩阵 | 显示 |
| `previous` | 已有更新一代，但仍有公开资料、端点或比较价值 | 显示（可折叠） |
| `preview` | preview、beta、early release 或生产端点尚未普遍开放 | 显示徽标，不进入严格排名 |
| `restricted` | 仅 vetted partners、专项计划或早期访问可用 | 默认折叠 |
| `deprecated` | 官方已宣布端点/版本退役 | 历史页 |

`catalog-only` 不是生命周期，也不表示身份不可信。它是页面从当前 canonical score 长表派生的覆盖状态：`scoreCoverage = scored` 表示至少有一条 canonical score，`scoreCoverage = catalog-only` 表示当前没有 canonical score。公开披露层可能仍有该模型的未复现记录。机器目录因此不把 `catalog-only` 写进 `status`；派生快照以 `catalogOnly: true/false` 暴露这一状态。

`availability` 建议使用 `api`、`hosted`、`open-weights`、`early-access`、`restricted`、`deprecated` 的数组；不要用它替代 `status`。例如 Claude Fable 5 与 Claude Mythos 5 当前都按 `restricted + restricted` 记录；MiMo-V2.5-Pro-UltraSpeed 是 `active + api` 的 serving variant，而不是新的基础模型。

## 3. 规范 ID 和必填字段

### 3.1 ID 规则

统一 canonical id：`provider/family@release`，全小写、稳定、不可复用。日期 snapshot、reasoning 变体、量化权重和不同上下文 endpoint 不能悄悄覆盖原 id。下方示例使用 family 级简写；机器可读的首批目录使用带发布日期或 snapshot 的具体 ID，详见 `data/catalog/models.json`。面向读者的能力定位、endpoint 列表、参数/上下文口径和限制说明维护在 `data/catalog/model_profiles.json`，由 canonical id 一一索引。

```json
{
  "id": "qwen/qwen@3.8-flash-next",
  "family_id": "qwen/qwen",
  "name": "Qwen3.8-Flash-Next",
  "provider": "Qwen",
  "release_date": "2026-08-26",
  "status": "preview",
  "availability": ["open-weights", "hosted-preview"],
  "endpoint_ids": ["Qwen/Qwen3.8-Flash-Next", "qwen3.8-flash"],
  "modalities": ["text", "image"],
  "context_window": {"native": 262144, "extended": 1000000, "method": "YaRN"},
  "params_total": 125000000000,
  "params_active": 6000000000,
  "params_extra": {"ngram_embedding": 51000000000},
  "architecture": "MoE",
  "license": null,
  "source_ids": ["src_qwen38_flash_next"],
  "last_checked": "2026-08-27"
}
```

### 3.2 字段契约

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `id` | 是 | canonical release id；不可用显示名作 id |
| `family_id` | 是 | 同一训练谱系共享；不同产品路由不自动拆 family |
| `name`, `provider` | 是 | 页面显示名和发布方 |
| `release_date` | 否 | 只填官方发布日期；未知为 `null` |
| `status` | 是 | 生命周期；只能取本文的 `active`、`previous`、`preview`、`restricted`、`deprecated` |
| `scoreCoverage` | 派生 | `scored` 或 `catalog-only`；由构建脚本按 canonical score 计算，不写回身份目录 |
| `availability` | 是 | API、hosted、open-weights、early-access 等，可多选 |
| `endpoint_ids` | 否 | 每个 provider/API/聚合端点原名；alias 单独标 `kind: alias` |
| `modalities` | 是 | 输入模态；`text`、`image`、`video`、`audio` 等 |
| `reasoning_modes` | 否 | 例如 `low/high/max`；不要把 effort 当新模型 |
| `context_window` | 否 | 记录单位 token、native/extended 和扩展方法；不同限制写在 endpoint facts |
| `params_total` | 否 | source-backed 总参数；未知为 `null`，绝不由规模猜测 |
| `params_active` | 否 | 每 token 激活参数；dense 模型可等于 total，但仍建议明确写出 |
| `params_approximate` | 否 | 厂商仅披露“约 N”时为 `true`；页面保留 `≈`，不能伪装成精确计数 |
| `params_extra` | 否 | 例如 N-gram embedding；不得静默加进 `params_total` |
| `architecture` | 否 | dense、MoE、hybrid 等，仅在来源明确时填写 |
| `license` | 否 | 只登记原始权重许可证，不把“可试用”当开源 |
| `source_ids` | 是 | 至少一个官方 model card、API 文档或发布公告 |
| `last_checked` | 是 | 本项目核验日期；价格、配额等时变事实另存 model fact |

`model_profiles.json` 中每个 profile 至少应有 `positioning`、`capabilities`、
`best_for`、`endpoint_ids`、`availability`、`caveats`、`fact_source_ids` 和
`last_checked`。architecture、reasoning modes、context/parameter note、license
等字段只在来源明确时填写；未知值保留 `null` 或 `[]`。profile 的 `fact_source_ids`
会与模型的 `source_ids` 合并显示，方便从详情页直接打开具体官方页面。

闭源模型若有可复核的独立分析，可在 profile 的 `parameter_estimates` 中登记，
但必须与 canonical 参数严格分层：每条估计需给出 `kind`、点估计、区间、方法
`basis`、置信度、日期、来源和明确 caveat。当前支持的 `ikp_effective` 表示“与多大
开放模型相当的长尾知识容量”，不是实际权重数；因此它不会写入或参与
`params_total` / `params_active` 的筛选、排序和“10T 模型”分组。页面以“第三方估计”
单独展示，且区间必须与点估计同时出现。

底座或衍生关系使用 profile 的 `parameter_evidence`：必须标出 `base_checkpoint`
或 `base_lineage`、total/active 的适用对象、来源、confidence 和 caveat。这类数字只在
详情页的 “PARAMETER PROVENANCE” 中显示，不写入当前 hosted endpoint 的 canonical
参数，也不参与参数排序。厂商对 exact model 只给约数时可写入 canonical 数值，但必须
同时设置 `params_approximate: true`，例如 MiniMax M3 的约 428B / 23B。

### 3.3 Endpoint、variant 与 system

- Alias（例如 `gpt-5.6`）是 `endpoint_alias`，指向一个 release，不新增模型行。
- 上下文/速度/配额变化（例如 `k3` 与 `k3-256k`）默认是同一 release 的 endpoint variant；只有模型权重或训练版本明确不同，才拆 release。
- Reasoning effort、temperature、parallel sampling、quantization、provider routing 和 prompt template 都属于 run protocol。
- Fable 5 的 fallback、Opus 5 的安全 fallback、DeepSeek Harness 和 Kimi Code 都必须进入 system/run 记录，不能写成模型固有分数。

## 4. 参数和规模规则

1. 总参数与 active 参数永远分列：`params_total`、`params_active`、可选的 `params_extra`。
2. MoE 的“总参数”是专家池、共享专家和其他可计入权重的总和；active 是一次 token 路由实际使用的参数。dense 模型也不要把未知值写成 0。
3. N-gram embedding、视觉 encoder、外接检索器等只有在原始来源明确计入时才进入对应字段；否则放到 `params_extra` 并注明口径。
4. 参数数字必须带 `parameter_scope`（例如 `model_only`、`model_plus_embedding`）、`as_of`、单位和 evidence locator。不同来源冲突时保留多条 fact，不取平均。
5. 量化（FP8、FP4、GGUF 等）改变部署占用，不改变基础模型参数量；量化信息进入 deployment fact。
6. `10T` 不是默认类别。只有来源给出可定位、可解释的总参数才进入 scale watchlist；未知值排在末尾，不参加“规模最大”排名。
7. 黑盒行为分析得到的 effective-capacity estimate 不能替代总参数。即使点估计看似精确，也必须显示其方法名、预测区间和“非实际权重”提示。

## 5. 首批目录（截至 2026-08-28）

表中只登记身份与元数据，不填分数。`endpoint` 是来源中的调用名；`—` 表示尚未从官方资料核验，不代表参数为零。

### OpenAI

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `openai/gpt@5.6-sol` | GPT-5.6 Sol | `active` | `api`; `gpt-5.6-sol`; alias `gpt-5.6` | text+image；1.05M context | [API catalog](https://developers.openai.com/api/docs/models) |
| `openai/gpt@5.6-terra` | GPT-5.6 Terra | `active` | `api`; `gpt-5.6-terra` | text+image；1.05M context | [API catalog](https://developers.openai.com/api/docs/models) |
| `openai/gpt@5.6-luna` | GPT-5.6 Luna | `active` | `api`; `gpt-5.6-luna` | text+image；1.05M context | [API catalog](https://developers.openai.com/api/docs/models) |
| `openai/gpt@5.5` | GPT-5.5 | `active` | `api`; product endpoint 需按发布页复核 | 以 launch report 为准 | [GPT-5.5 launch](https://openai.com/index/introducing-gpt-5-5/) |
| `openai/gpt@5.5-pro` | GPT-5.5 Pro（评测/产品变体） | `active` | `api`; 不单独假设 API id | 当前 `scoreCoverage: catalog-only`；不与 GPT-5.5 release 重复计数 | [GPT-5.5 launch](https://openai.com/index/introducing-gpt-5-5/) |
| `openai/gpt@5.4` | GPT-5.4 | `active` | `api`; product endpoint 需按发布页复核 | 保留作上一代 baseline | [GPT-5.4 launch](https://openai.com/index/introducing-gpt-5-4/) |

GPT-5.6 Pro、Daybreak/Cyber 等产品层或专项安全模型，先作为 `variant`/specialized catalog 记录；没有独立 API model id 时不放入通用文本总表。

### Anthropic

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `anthropic/claude@opus-5` | Claude Opus 5 | `active` | `api/hosted`; `claude-opus-5` | 1M context；有 Fast mode | [Opus 5 announcement](https://www.anthropic.com/news/claude-opus-5) |
| `anthropic/claude@sonnet-5` | Claude Sonnet 5 | `active` | `api/hosted`; `claude-sonnet-5` | 1M context；adaptive effort | [Sonnet 5 research post](https://www.anthropic.com/research/claude-sonnet-5) |
| `anthropic/claude@fable-5` | Claude Fable 5 | `restricted` | `restricted`; `claude-fable-5` | Mythos-class；安全分类器可能 fallback 到 Opus 4.8 | [Fable/Mythos announcement](https://www.anthropic.com/news/claude-fable-5-mythos-5) |
| `anthropic/claude@mythos-5` | Claude Mythos 5 | `restricted` | `restricted`; vetted partners / trusted access | 与 Fable 5 同基础模型，安全措施不同 | [Mythos availability](https://www.anthropic.com/claude/mythos) |
| `anthropic/claude@opus-4.8` | Claude Opus 4.8 | `active` | `api/hosted` | Fable/Opus fallback 与上一代对照 | [Opus 4.8](https://www.anthropic.com/news/claude-opus-4-8) |
| `anthropic/claude@opus-4.7` | Claude Opus 4.7 | `previous` | `api/hosted` | 保留历史代际比较 | [Anthropic system cards](https://www.anthropic.com/system-cards) |
| `anthropic/claude@sonnet-4.6` | Claude Sonnet 4.6 | `previous` | `api/hosted` | Sonnet 5 的上一代 baseline | [Sonnet 4.6](https://www.anthropic.com/news/claude-sonnet-4-6) |

### Qwen

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `qwen/qwen@3.8-max` | Qwen3.8-Max | `active` | `api/hosted`; Qwen Studio/QwenCloud 名称 | 1M hosted context；2.4T MoE total；95B active 仅按 base-checkpoint lineage 展示 | [Qwen Cloud specification](https://docs.qwencloud.com/developer-guides/getting-started/latest-model)；[base checkpoint](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) |
| `qwen/qwen@3.8-2.4t-a95b` | Qwen3.8-Max open release | `active` | `open-weights`; `Qwen/Qwen3.8-2.4T-A95B` | 2.4T total / 95B active；262K native / ~1.01M extended | [official model card](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B)；[Qwen3.8 repository](https://github.com/QwenLM/Qwen3.8) |
| `qwen/qwen@3.8-flash-next` | Qwen3.8-Flash-Next | `active` | `open-weights`; hosted production name `qwen3.8-flash`（API 状态另核验） | 125B main、6B active、51B N-gram；262K native / 1M YaRN | [Flash-Next release](https://qwen.ai/blog?id=qwen3.8-flash-next) |
| `qwen/qwen@3.8-27b` | Qwen3.8-27B | `active` | `open-weights`; `Qwen/Qwen3.8-27B` | 27B dense | [Qwen3.8-27B](https://qwen.ai/blog?id=qwen3.8-27b) |
| `qwen/qwen@3.7-plus` | Qwen3.7-Plus | `previous` | `api/hosted` | 托管 endpoint；参数、架构与 context 待逐型号一手资料 | [Qwen API platform](https://qwen.ai/apiplatform) |
| `qwen/qwen@3.7-max` | Qwen3.7-Max | `previous` | `hosted` | 产品目录已列；参数待 model card | [Qwen API platform](https://qwen.ai/apiplatform) |
| `qwen/qwen@3.6-max-preview` | Qwen3.6-Max-Preview | `preview` | `hosted-preview`; `qwen3.6-max-preview` | 仍在迭代的 preview | [Qwen3.6-Max-Preview](https://qwen.ai/blog?id=qwen3.6-max-preview) |
| `qwen/qwen@3.6-plus` | Qwen3.6-Plus | `previous` | `hosted` | 作为 3.8/3.7 对照 | [Qwen API platform](https://qwen.ai/apiplatform) |
| `qwen/qwen@3-max-thinking` | Qwen3-Max-Thinking | `previous` | `hosted/api`; `qwen3-max-2026-01-23` | reasoning + adaptive tools | [Qwen3-Max-Thinking](https://qwen.ai/blog?id=qwen3-max-thinking) |
| `qwen/qwen@3-max` | Qwen3-Max-Instruct | `previous` | `api`; `qwen3-max` | 上一代 Max baseline | [Qwen3-Max](https://qwen.ai/blog?id=qwen3-max) |

`Qwen3.8-Flash-Next` 是架构早期公开版本，不能与生产 `qwen3.8-flash` 自动合并；若两者被证明是同一权重，只通过 `endpoint`/`snapshot` 关联。

表中以 `↳` 开头的行只是为了让人类读者看见 endpoint/serving variant；机器可读 catalog 应保留一个 model release 对象，并把这些名称放进其 `endpoints[]`，避免重复计数。

### DeepSeek

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `deepseek/v4@pro` | DeepSeek-V4-Pro | `active` | `api/hosted`; `deepseek-v4-pro` | 1.6T total / 49B active；1M context | [V4 preview release](https://api-docs.deepseek.com/news/news260424/)；[API updates](https://api-docs.deepseek.com/updates/) |
| `deepseek/v4@flash` | DeepSeek-V4-Flash | `active` | `api`; `deepseek-v4-flash` | 284B total / 13B active；public beta | [V4 preview release](https://api-docs.deepseek.com/news/news260424/)；[Flash update](https://api-docs.deepseek.com/updates/) |
| `deepseek/v4@flash-vision-exp` | DeepSeek-V4-Flash-Vision-Exp | `preview` | `api/experimental` | Flash 的视觉 agent variant；参数继承关系需按 card 核验 | [DeepSeek API updates](https://api-docs.deepseek.com/updates/) |
| `deepseek/v3@3.2` | DeepSeek-V3.2 | `previous` | `api/hosted` | 保留为上一代 baseline | [DeepSeek API updates](https://api-docs.deepseek.com/updates/) |

`deepseek-chat` 和 `deepseek-reasoner` 是历史 alias；官方已说明其退役/路由变化，不能继续当作独立模型行。[DeepSeek V4 release](https://api-docs.deepseek.com/news/news260424/)

### Kimi / Moonshot

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `moonshot/kimi@k3` | Kimi K3 | `active` | `api/hosted/open-weights`; `k3` | 2.8T total；1M context；native vision | [Kimi K3 tech blog](https://www.kimi.com/en/blog/kimi-k3) |
| `↳ moonshot/kimi@k3` | Kimi K3 256K endpoint | `active` | `api/hosted`; `k3-256k` | 同一 release 的 256K context variant，不新增 model id | [Kimi Code model configuration](https://www.kimi.com/code/docs/en/kimi-code/models.html) |
| `moonshot/kimi@k2.7-code` | Kimi K2.7 Code | `active` | `api/hosted`; `kimi-for-coding` | Coding tier；256K context | [Kimi Code model configuration](https://www.kimi.com/code/docs/en/kimi-code/models.html) |
| `↳ moonshot/kimi@k2.7-code` | Kimi K2.7 Code HighSpeed | `active` | `api/hosted`; `kimi-for-coding-highspeed` | serving/speed variant，不拆 release | [Kimi Code model configuration](https://www.kimi.com/code/docs/en/kimi-code/models.html) |
| `moonshot/kimi@k2.6` | Kimi K2.6 | `previous` | `api/hosted/open-weights`; `kimi-k2.6` | 仍可用；支持 coding、vision、agent | [Kimi K2.6 overview](https://www.kimi.com/en/help/agent/agent-overview) |
| `moonshot/kimi@k2.5` | Kimi K2.5 | `previous` | `api/hosted/open-weights` | 历史多模态/Agent baseline | [Kimi K2.5](https://www.kimi.com/en/blog/kimi-k2-5) |

Kimi 文档要求调用时填写 model ID 而不是展示名；因此 `k3`/`k3-256k` 进入 endpoint 字段，不把“1M”和“256K”误写成两个 family。[Kimi Code docs](https://www.kimi.com/code/docs/en/kimi-code/models.html)

### GLM / Z.ai

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `zai/glm@5.3` | GLM-5.3 | `preview` | `api/hosted-preview`; Z.ai/Coding Plan | open weights announced, release timing需复核 | [GLM-5.3](https://z.ai/blog/glm-5.3) |
| `zai/glm@5.3-flash` | GLM-5.3-Flash | `active` | `hosted/open-weights` | 320B total / 18B active；面向低成本推理 | [GLM-5.3-Flash](https://z.ai/blog/glm-5.3-flash) |
| `zai/glm@5.2` | GLM-5.2 | `previous` | `hosted/open-weights` | 作为 5.3 对照 | [GLM-5.2](https://z.ai/blog/glm-5.2) |
| `zai/glm@5.1` | GLM-5.1 | `previous` | `hosted` | 代码/Agent baseline | [GLM-5.1 docs](https://docs.z.ai/guides/llm/glm-5.1) |
| `zai/glm@5` | GLM-5 | `previous` | `hosted/open-weights` | 早期 Agent baseline | [GLM-5](https://z.ai/blog/glm-5) |

### MiniMax

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `minimax/text@m3` | MiniMax M3 | `active` | `hosted/api`; `MiniMax-M3` | 1M context；native multimodal；open weights announced | [MiniMax M3 model page](https://www.minimax.io/models/text/m3)；[M3 release](https://www.minimax.io/blog/minimax-m3) |
| `minimax/text@m2.7` | MiniMax M2.7 | `previous` | `hosted/api`; M2.7 | Coding/Agent baseline | [MiniMax release notes](https://platform.minimaxi.com/docs/release-notes/models) |
| `↳ minimax/text@m2.7` | MiniMax M2.7 HighSpeed | `previous` | `hosted/api`; M2.7-highspeed | serving/speed variant，不拆 release | [MiniMax release notes](https://platform.minimaxi.com/docs/release-notes/models) |
| `minimax/text@m2.5` | MiniMax M2.5 | `previous` | `hosted/api`; M2.5 | 上一代生产 baseline | [MiniMax release notes](https://platform.minimaxi.com/docs/release-notes/models) |
| `↳ minimax/text@m2.5` | MiniMax M2.5 HighSpeed | `previous` | `hosted/api`; M2.5-highspeed | serving/speed variant，不拆 release | [MiniMax release notes](https://platform.minimaxi.com/docs/release-notes/models) |

### Xiaomi MiMo

| canonical release | 展示名 | status | availability / endpoint | 已核验元数据 | 官方来源与备注 |
| --- | --- | --- | --- | --- | --- |
| `xiaomi/mimo@v2.5-pro` | MiMo-V2.5-Pro | `active` | `api/hosted/open-weights`; `mimo-v2.5-pro` | 1T total / 42B active；1M context | [MiMo model docs](https://mimo.mi.com/docs/en-US/quick-start/model)；[V2.5 release](https://mimo.mi.com/docs/en-US/updates/model) |
| `xiaomi/mimo@v2.5` | MiMo-V2.5 | `active` | `api/hosted/open-weights`; `mimo-v2.5` | text/image/video/audio；1M context | [MiMo model docs](https://mimo.mi.com/docs/en-US/quick-start/model) |
| `↳ xiaomi/mimo@v2.5-pro` | MiMo-V2.5-Pro UltraSpeed | `active` | `api`; serving variant | 只记录为速度/部署 variant，不当新权重 | [MiMo model docs](https://mimo.mi.com/docs/en-US/quick-start/model) |
| `xiaomi/mimo@v2-pro` | MiMo-V2-Pro | `previous` | `api` | 目录保留的上一代 reasoning/Agent endpoint；退役状态尚未写入机器目录 | [MiMo model updates](https://mimo.mi.com/docs/en-US/updates/model) |
| `xiaomi/mimo@v2-omni` | MiMo-V2-Omni | `previous` | `api` | 目录保留的上一代全模态 endpoint；退役状态尚未写入机器目录 | [MiMo model updates](https://mimo.mi.com/docs/en-US/updates/model) |

语音模型（ASR/TTS）单独归入 audio catalog，不与文本/多模态 reasoning leaderboard 混排。

### 已有 seed 与下一批

Gemini 3.7 Flash（latest）、Gemini 3.6 Flash（previous-generation）、Gemini 3.5 Flash / Flash-Lite（legacy/efficiency）以及 Grok 4.6 / 4.5 已进入 canonical roster；Gemini 3.1 Pro、Gemini 2.5 Pro、Grok 4 Fast 继续保留作历史对照。Llama、Mistral、Cohere、Amazon Nova、Doubao、ERNIE、Hunyuan、StepFun 等仍属于后续批次，前提是逐条取得官方 model card/API 目录和可复现 endpoint 信息。聚合站（Arena、Artificial Analysis、OpenRouter）可作为发现入口，不能单独证明 release 身份。

## 6. 更新和淘汰策略

- 默认矩阵：公开覆盖视图保留当前目录与已映射公开报告；`preview/restricted` 是生命周期徽标，`scoreCoverage: catalog-only` 的行可见但无 canonical 分数、不产生排名。
- 窄 preset / 全量目录开关：可分别收窄到当前 family，或显示所有 `scoreCoverage: catalog-only`、specialized 和历史 release；没有 canonical 分数时显示 `—`，不产生排名。
- 年龄规则：普通模型在 18–24 个月后从默认矩阵移入历史页；只要有重要 benchmark 时间线或 API 仍广泛使用，就保留历史记录。
- 退役规则：只有 provider 明确写出 retirement/deprecation 才设 `deprecated`；旧 alias 的路由变化不等于新 release。
- 每次更新写 `last_checked`、source locator 和变更理由；参数、价格、context、配额等变化事实写入带 `as_of` 的 `model_facts`，不要覆盖 release 身份。
