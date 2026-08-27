# Frontier Model Bench

一个面向个人主页的静态模型评测信息站：把模型卡、论文和 benchmark 榜单里的分数收进可追溯的数据层，并用两种视图呈现模型能力与完整系统运行。

> 当前仓库是 **curated snapshot / static MVP**。目录可以比成绩覆盖更多模型；没有逐条证据的模型会显示为 `catalog-only`，不会被当作有成绩的模型。页面不会把不同 benchmark、harness 或协议偷偷合成一个总分。

## 本地运行

```bash
python3 -m http.server 8765
# 打开 http://127.0.0.1:8765/
```

直接双击 `index.html` 会被浏览器的跨域策略阻止读取 JSON；请使用一个本地静态服务器。

## 页面和目录

```text
index.html                 # 页面结构
styles.css / app.js        # 无构建依赖的静态前端
data/catalog/               # models / benchmarks / sources / harnesses / presets 注册表
data/observations/results.jsonl # 追加式 canonical observation 长表
data/derived/site.json      # 由脚本生成，供静态前端读取
data/models.json            # 旧 seed 兼容回退（逐步迁移中）
docs/data-contract.md       # 长表 observation 与证据契约
docs/model-catalog.md       # 模型身份、版本、endpoint 与淘汰规则
docs/presets.md             # 比较维度/预设的配置说明
scripts/build_derived.py    # catalog + observations → site index
scripts/validate_data.py    # 只依赖 Python 标准库的数据检查器
.github/workflows/validate.yml
.github/workflows/pages.yml      # GitHub Pages build/deploy
```

数据层的形态是：

```text
source snapshots → canonical observations → derived indexes → static UI
```

新增来源时，优先增加独立 adapter 和来源快照，不在前端写爬虫；新增 benchmark 时，先登记版本、指标和可比性说明。完整字段约定见 [`docs/data-contract.md`](docs/data-contract.md)。

## 两种比较主体

- **Model Atlas**：每行一个 model release/config。适合 GPQA、MMLU-Pro、AIME、MMMU、LiveCodeBench 等直接评测；单元格仍显示 shots、effort、tools、evidence 与可比性。
- **System Runs**：每行一个精确的 `model × endpoint × harness × protocol × benchmark version`。SWE-bench、Terminal-Bench、BFCL、τ-bench、OSWorld 等必须在这个视图中比较；不跨 harness 取最高值或平均值。

预设由 `data/catalog/presets.json` 驱动，可切换 Frontier、Flash/Fast、小模型、数学、代码 Agent、工具、多模态、长上下文、中文/多语、开放权重、可靠性和参数规模等比较维度。`catalog-only` 模型只有打开“显示全量目录”才出现，缺失始终表示 `—`，不是 0。

## 更新数据

1. 在 catalog 中登记具体 release、endpoint、benchmark version 和 source；不要把 alias、reasoning effort 或速度 variant 当作新模型。
2. 在 `data/observations/results.jsonl` 追加一条事实：分数必须同时带 protocol、harness（如适用）、observed date、evidence 和 comparability。旧事实不覆盖，修订用新 observation 标 superseded/retracted。
3. 生成索引并运行校验：

   ```bash
   python3 scripts/build_derived.py
   python3 scripts/validate_data.py
   python3 scripts/validate_data.py --strict  # 发布前把迁移 warning 也视为失败
   ```

4. 打开页面，检查矩阵横向滚动、筛选、详情抽屉、来源链接和缺失值语义，再提交一个小 PR。

GitHub Actions 会在涉及 `data/`、`scripts/` 或 schema 的 push/PR 上先重建 `site.json` 再校验；Pages 发布同样只上传通过校验的静态产物。后续可按来源增加定时 adapter：抓取只生成候选数据和不可变快照，人工审阅后才进入默认矩阵。

## 设计边界

- 不默认计算跨 benchmark 的“总分”；accuracy、pass@1、Elo 和 agent resolve rate 不能混为一个排名。
- 记录 benchmark version、prompt/tools/reasoning effort、harness/scaffold 和 observed date；SWE-bench 等 agent benchmark 的成绩属于“模型 + scaffold + harness”系统。
- `reported / reproduced / verified` 与 `exact / conditional / none` 分开表达证据等级和可比性。
- source 失效或数据过期时保留旧 observation，并显示 stale/conflict，而不是悄悄删除。

## 发布到 GitHub Pages

这是纯静态目录，不需要 Node 或数据库。当前仓库已配置 GitHub Pages workflow；推送 `main` 会先校验数据，再发布静态产物。也可以把整个目录作为个人主页的 `static/benchmarks/` 构建产物，或仅在主页增加外链。

推荐仓库名：`OptHuang/frontier-model-bench`。个人主页仓库保持独立，避免网站内容和数据抓取权限相互耦合。
