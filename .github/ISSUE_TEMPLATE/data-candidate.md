---
name: Data candidate / correction
about: 提交一个待审阅的模型、benchmark 或成绩线索；不会自动进入线上榜单
title: "[data] "
labels: "data-candidate"
assignees: ""
---

> 这是候选线索，不是直接发布请求。请不要粘贴受许可证限制的题目、完整榜单或 API token。

## 类型

- [ ] 新模型 / endpoint
- [ ] 新 benchmark / version
- [ ] 缺失成绩补全
- [ ] 已有成绩修正、冲突或撤回
- [ ] 来源失效 / freshness

## 身份

- canonical `model_id`（如适用）：
- `family_id` / provider：
- `benchmark_id` / version / metric：
- model-only 还是 system run：
- endpoint / harness / scaffold / budget（system 必填）：

## 候选事实

- value / raw value / unit：
- split / subset / shots / tools / temperature / reasoning effort：
- observed date：
- published date：
- evidence level（A/B/C/D）：
- comparability（exact/conditional/none）：

## 来源与定位

- source URL：
- 页面中的 table/row/locator：
- 是否允许保存 payload（若不确定请写“不确定”）：
- 相关 `candidate_id` 或 maintenance artifact：

## 备注

请说明为什么这条事实值得优先处理、是否与现有 observation 冲突，以及你是否已经在本地运行：

```bash
python3 scripts/build_derived.py
python3 scripts/validate_data.py --strict
```
