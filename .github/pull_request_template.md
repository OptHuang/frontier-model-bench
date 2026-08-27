## Data / maintenance checklist

适用于新增模型、benchmark、observation 或维护脚本的 PR；纯文档/样式 PR 可删去不适用项。

- [ ] 这是一个小而可审阅的变更；没有把 candidate 直接当作 approved。
- [ ] 没有覆盖或删除旧 observation；修订使用新行并说明 `superseded`/`retracted` 理由。
- [ ] canonical model release、endpoint、benchmark version 和 metric 已确认。
- [ ] model-only 与 system run 已区分；system 已记录 harness/scaffold/预算。
- [ ] protocol、observed/published date、source URL/locator、evidence level、comparability 齐全。
- [ ] 遵守来源许可证；没有提交题目、私有数据、token 或整页 payload。
- [ ] 已运行 `python3 scripts/build_derived.py`。
- [ ] 已运行 `python3 scripts/validate_data.py --strict`。
- [ ] 已运行 `git diff --check`。

### 摘要

<!-- 说明这次新增/修正了什么，以及为何选择这些来源。 -->
