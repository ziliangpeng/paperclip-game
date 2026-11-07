---
name: Implementation task
about: 由一个独立可测试 PR 交付的任务
title: "[Task] "
labels: ""
assignees: ""
---

<!-- 创建后选择 GitHub Milestone。一个 Agent 一次只认领一个 Issue；施工规则见根目录 AGENTS.md。 -->

## Objective

<!-- 用一两句话说明要交付的可验证结果。 -->

## Specification references

- `requirements/<file>.md` §`<section>` — <!-- 相关状态与不变量；只引用，不复述一套规则。 -->

## Scope

- <!-- 本 Issue 包含的可交付范围。 -->

## Non-goals

- <!-- 明确排除、需要另开 Issue 的工作。 -->

## Dependencies

Blocked by: None
Blocks: None

<!-- 有依赖时把 None 换成 #123；多个依赖按行重复同一 marker。 -->

## Acceptance criteria

- [ ] <!-- 可独立验证、能追溯到需求的结果。 -->

## Required tests / evidence

<!-- 按 requirements/testing.md 选择与风险相关的验证，不复制完整测试矩阵。 -->
- Tests / commands:
- Expected results / artifacts:

## Risk flags

- [ ] Core simulation / economy / game rules
- [ ] Concurrency / persistence / recovery
- [ ] Test / CI / merge infrastructure
- [ ] Security / data / main-branch risk
- [ ] 以上均不适用

<!-- 需求冲突或产品歧义：标记 needs-decision 并停止实现，先解决需求。 -->
