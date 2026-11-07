# Requirements

本目录是 **paperclip-game 产品与工程需求的唯一版本化事实来源**。聊天记录、Issue 评论和 Agent 的记忆不能替代这里的明确要求。

## 状态约定

- **CONFIRMED**：用户已经确认，不得由实现 Agent 擅自改变。
- **PROPOSED**：当前推荐设计。若与需求不冲突，可在对应 Issue 中实施；若实施中发现代价或行为差异，应先更新本文并获得适当确认。
- **OPEN**：尚未明确、会影响产品行为或验收的内容。依赖它的实现工作必须保持阻塞，直到它被解决。

纯内部实现细节不要求逐项经过产品讨论，但必须在相关 Issue 中明确选择和验证方式。不得把 `PROPOSED` 写成 `CONFIRMED`。

## 文档索引

| 文档 | 范围 |
|---|---|
| [Product](./product.md) | 产品目标、gameplay 与 UI 保真边界、客户端角色 |
| [Runtime](./runtime.md) | 实时模拟、并发、实例边界、技术栈与持久化 |
| [Clients and API](./clients.md) | 默认寻址、Commands、GameView、SSE 与浏览器边界 |
| [Testing](./testing.md) | 分层测试、场景验收与证据要求 |
| [Milestones](./milestones.md) | 完整 Milestone 地图的形成方式与当前规划状态 |

## 变更与冲突

1. 项目级 Agent 开发流程见根目录 `AGENTS.md`，本目录不复制整套开发规范。
2. Issue 只能引用需求，不能在 Issue body 中制造另一套相互冲突的游戏规则。
3. 如果实现发现需求内部矛盾或产品歧义，应停止相关工作，标记 `needs-decision`，解决后先更新需求再继续。
4. 官方 HTML 是原版游戏设计的主要参考；本项目明确记录的服务器实时模型和状态管理方式优先于原版浏览器实现。
5. 需求变更通过 Issue 和 PR 留痕。实现 PR 不得顺手夹带未批准的需求变化。

## 当前阶段

当前只完成文档与开发流程初始化。完整 gameplay 功能清单、Milestone 地图和可实施 Issues 尚未全部完成，**尚未授权开始游戏功能实现**。
