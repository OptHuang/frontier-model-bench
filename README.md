# Frontier Model Bench

一个面向个人主页的静态模型评测信息站：把模型卡、论文和 benchmark 榜单里的分数收进一张可追溯的矩阵，并在点击单元格时展示设置与来源。

> 当前仓库是 **MVP / curated seed snapshot**。首批数字来自公开的模型卡、技术报告或 benchmark 页面，并逐条保留来源链接与设置；它还不是自动抓取的实时排行榜，引用前仍应打开详情核对版本、工具和 scaffold。

## 本地运行

```bash
python3 -m http.server 8765
# 打开 http://127.0.0.1:8765/
```

直接双击 `index.html` 会被浏览器的跨域策略阻止读取 JSON；请使用一个本地静态服务器。

## 目录

```text
index.html                 # 页面结构
styles.css / app.js        # 无构建依赖的静态前端
data/models.json            # MVP catalog（模型、benchmark、成绩、来源）
docs/data-contract.md       # 从 seed catalog 迁移到长表 observation 的契约
scripts/validate_data.py    # 只依赖 Python 标准库的数据检查器
.github/workflows/validate.yml
.github/workflows/pages.yml      # GitHub Pages build/deploy
```

数据层的长期形态是：

```text
source snapshots → canonical observations → derived indexes → static UI
```

新增来源时，优先增加独立 adapter 和来源快照，不在前端写爬虫；新增 benchmark 时，先登记版本、指标和可比性说明。完整字段约定见 [`docs/data-contract.md`](docs/data-contract.md)。

## 更新数据

1. 在 `data/models.json` 中添加或更新一个具体 release 的记录；不要把不同日期、preview 或 reasoning 变体混成一个 model id。
2. 每个 score 同时写 `setting`、`sourceId`、`observed`/`published`（迁移到长表后写进 `protocol` 和 evidence）。没有成绩请使用 `value: null`，不要用 `0` 或 `—`。
3. 运行校验：

   ```bash
   python3 scripts/validate_data.py
   python3 scripts/validate_data.py --strict  # 发布前把迁移 warning 也视为失败
   ```

4. 打开页面，检查矩阵横向滚动、筛选、详情抽屉、来源链接和缺失值语义，再提交一个小 PR。

GitHub Actions 会在涉及 `data/`、`scripts/` 或 schema 的 push/PR 上自动运行校验。后续可再加一个按来源运行的定时抓取 workflow：抓取只生成候选数据和不可变快照，人工审阅后才进入默认矩阵。

## 设计边界

- 不默认计算跨 benchmark 的“总分”；accuracy、pass@1、Elo 和 agent resolve rate 不能混为一个排名。
- 记录 benchmark version、prompt/tools/reasoning effort、harness/scaffold 和 observed date；SWE-bench 等 agent benchmark 的成绩属于“模型 + scaffold + harness”系统。
- `reported / reproduced / verified` 与 `exact / conditional / none` 分开表达证据等级和可比性。
- source 失效或数据过期时保留旧 observation，并显示 stale/conflict，而不是悄悄删除。

## 发布到 GitHub Pages

这是纯静态目录，不需要 Node 或数据库。当前仓库已配置 GitHub Pages workflow；推送 `main` 会先校验数据，再发布静态产物。也可以把整个目录作为个人主页的 `static/benchmarks/` 构建产物，或仅在主页增加外链。

推荐仓库名：`OptHuang/frontier-model-bench`。个人主页仓库保持独立，避免网站内容和数据抓取权限相互耦合。
