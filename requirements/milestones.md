# Milestone Planning

## 1. 完整地图先于功能实现 — CONFIRMED

开始游戏功能实现前，必须先形成：

1. 基于官方 HTML 和游戏内容的完整 gameplay 功能清单；
2. 从初始游戏到完整结局的 Milestone 地图；
3. 每个 Milestone 的可玩增量、依赖和退出条件；
4. 当前 Milestone 的细分 Issues 与依赖关系；
5. 每个 Issue 的测试与验收策略。

**具体 M1 gameplay 边界尚未确认。**此前关于“初期制造—销售—自动化闭环”的讨论只是候选切法，不应误记为已冻结 M1。

## 2. Milestone 的切法 — CONFIRMED

- 以可玩的纵向能力增量切分，不以“后端全部完成”“前端全部完成”等横向层切分。
- 每个 Milestone 都是最终完整游戏的真实子集。
- 不用自创临时经济规则填充尚未实现的 gameplay。
- 每个 Milestone 明确 Entry criteria、Exit criteria、依赖、官方功能覆盖和端到端场景。
- 所有 Milestones 完成并通过验收后才宣称 Full Clone。

## 3. Issue 规划粒度 — CONFIRMED

- 当前 Milestone 拆成足够细、各自可由一个独立 PR 完成的 Issues。
- 下一个 Milestone 可以只保留较粗的任务轮廓。
- 更远的 Milestones 先放在完整地图中，等前一阶段验证后再细化，避免大量陈旧任务。
- GitHub Milestone 表达能力阶段；Issue 表达一个独立可交付任务；Issue body 的 `Blocked by` / `Blocks` 表达依赖。
- 自动化执行只选择 open 且 blockers 已完成的 Issues。

## 4. 各阶段的共同验收

每个 Milestone 至少需要：

- 相关规则与序列测试；
- 对应的服务器 API 与实时行为验证；
- 与风险匹配的并发和快照测试；
- 对应 Web UI 的真实可玩路径；
- 从规定的开始状态到达 Exit criteria 的端到端场景；
- 需求与官方功能清单的覆盖映射更新；
- 所有依赖 Issues 完成且主分支验证通过。

## 5. 当前状态 — OPEN

- [ ] 完整官方 gameplay 功能清单尚未建立；
- [ ] 完整 Milestone 地图尚未建立；
- [ ] M1 精确范围与 Exit criteria 尚未确认；
- [ ] 功能实现 Issues 尚未创建；
- [ ] 尚未开始游戏功能实现。
