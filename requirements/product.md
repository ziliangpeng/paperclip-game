# Product Requirements

## 1. 产品愿景 — CONFIRMED

建立一个以服务器为唯一权威状态源的 Universal Paperclips 重实现。

- 游戏世界由服务器持续推进。
- 网页、人类 harness、一个或多个 Agent 都只是客户端。
- 客户端发送动作并接收用于观察的状态；客户端不拥有游戏规则。
- 项目最终目标是完整 gameplay clone，而不是只做一个 paperclip 主题的按钮演示。

## 2. 完整范围与增量交付 — CONFIRMED

### Full clone

Full clone 指**完整忠实复刻原版游戏的高层与中层游戏设计、内容和 gameplay 体验**。

应保留：

- 原版的主要阶段、进程和结局；
- 资源、动作、生产、销售、自动化、升级和解锁之间的设计关系；
- 初始状态、主要经济数值、增长曲线和平衡所体现的 gameplay；
- 核心战略取舍、节奏和关键反馈；
- 让玩家能够经历原版完整进程的全部主要机制。

完整游戏通过多个可玩 Milestones 增量交付。每个 Milestone：

- 必须实现最终游戏中的真实子集；
- 不得先用自创简化规则占位，再把 simplification 当作 clone 验收；
- 未达到完整功能清单前，只能称为阶段性版本，不能声称 full clone 完成。

### Inspired game — 后续方向

受启发的新游戏、额外机制或非原版玩法，必须等完整 gameplay clone 完成后再规划。它不属于当前 clone 的验收范围。

## 3. 官方参考 — CONFIRMED

主要参考为官方页面及其正常加载的游戏内容：

- `https://www.decisionproblem.com/paperclips/index2.html`

2026-11-07 初次核对时，页面加载了带 `?v3` 参数的主要游戏脚本。Wiki、视频、记忆和其他资料只能辅助理解；游戏设计冲突时以官方参考为准。

官方参考用于确定 gameplay，不要求逐行移植其 JavaScript。

## 4. Gameplay 保真边界 — CONFIRMED

### 保留

- 原版游戏设计和 gameplay 体验；
- 资源关系、动作效果、主要解锁与 progression；
- 经济系统的有实际 gameplay 意义的规则；
- 阶段内容和战略选择。

### 不要求保留

- JavaScript 变量、模块和 DOM 的内部组织；
- 多个 `setInterval` 的具体调度顺序；
- 后台标签页 timer 限速；
- 浮点尾数、无 gameplay 意义的舍入差异或浏览器数值副作用；
- DevTools 修改变量、负数内部参数和直接调用内部函数等越权行为；
- 仅依赖 DOM `disabled` 的资源校验方式；
- `localStorage` 格式、刷新回滚和浏览器多标签状态分裂；
- 与原版浏览器完全一致的随机数序列或逐 tick 浮点轨迹。

这意味着：

- 不进行 bit-for-bit、pixel-for-bit 或原版 JS 状态轨迹对拍；
- 数值和公式有 gameplay 意义的部分仍需保持原版设计，不得以“实现细节”为理由改成另一套平衡；
- 疑似原版 bug 若会影响产品设计，先归类并记录；实现 Agent 不得自行决定隐藏修改；
- 服务器应正确处理越权输入和并发，不复制客户端信任缺陷。

## 5. 客户端与操作者 — CONFIRMED

- Human、Agent 和其他程序都使用同类 Command/View 交互。
- 游戏服务器不知道操作者类型；Command 不含 `actor` 身份字段。
- 不存在当前玩家、Human/Agent 回合或控制权接管流程。
- 同一局允许多个 Humans、多个 Agents 和多个网页同时发送 Commands。
- 只观察而不发送 Command 是自然行为，不需要特殊服务器角色。
- 任何客户端的思考、推理或犹豫都不暂停世界。
- 相同当前状态和相同 Command 产生相同的规则结果，不因来源不同而变化。

## 6. 第一版 Web UI — CONFIRMED

第一版 UI 是对原版的 **best effort visual clone**：

- 尽量保留极简黑白风格、主要面板、按钮、信息层级和浏览体验；
- 让熟悉原版的玩家能够自然识别和操作；
- 不要求 pixel-perfect；
- 不要求 DOM、CSS、事件绑定或静态资源与官方文件一致；
- 不以逐像素截图一致作为 merge gate；
- UI 只显示服务器状态并发送 Commands，不在本地推进或计算权威游戏状态。

后续可以设计不同 UI、Dashboard、监控和调试视图，但不提前扩大当前范围。

## 7. 最终验收原则 — CONFIRMED

Full clone 只有在下列条件满足后才可宣称完成：

1. 官方功能清单全部被映射到已完成的 Milestones；
2. 游戏能从原版初始状态推进到原有主要阶段与结局；
3. 核心资源、策略、progression 和 gameplay 体验保持原版设计；
4. 所有关键行为有分层的可执行验证；
5. 整个过程中服务器始终保持唯一权威状态和实时模拟语义。
