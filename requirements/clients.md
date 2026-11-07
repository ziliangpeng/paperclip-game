# Clients, Commands and State Streaming

## 1. 默认游戏对用户透明 — CONFIRMED

- 用户打开 `/` 就进入当前唯一游戏。
- 用户不需要知道 `game_id`、`default`、实例选择器或邀请码。
- 多个网页默认连接同一局。
- 浏览器 URL、Command body 和 SSE 连接不要求用户选择游戏 ID。

内部映射仍使用 `default`，以满足未来扩展边界。

## 2. 外部接口形状 — PROPOSED

建议使用以下不带实例 ID 的接口：

```http
GET  /api/game/view
POST /api/game/commands
GET  /api/game/stream
```

- Commands 用普通 HTTP POST；
- 状态流用 SSE；
- 当前不需要 WebSocket；
- 具体 JSON schemas 在对应 API Issue 中固化。

未来多实例可以在入口层新增寻址方案，不要求当前用户暴露实例概念。

## 3. Commands — CONFIRMED / PROPOSED

### Confirmed 语义

- Command 表达意图，不提交客户端计算的权威状态。
- 不包含 Human/Agent `actor`。
- 不包含要求用户选择的 `game_id`。
- 执行时校验资源和解锁条件。
- 过期观察不自动导致失败；失败必须基于当前实际状态和明确规则原因。
- 当前进程运行期间，同一逻辑 Command 的幂等重试不得重复应用状态变化；崩溃窗口按运行时恢复规则处理。
- 不允许通过特殊 Agent API 修改时间或直接写入资源。

### Proposed envelope 与重试契约

建议用客户端生成的 `command_id` 表达逻辑命令身份；该字段名称及编码不是 CONFIRMED 产品接口，由对应 API Issue 固化。

```json
{
  "command_id": "client-generated-id",
  "type": "action-name",
  "arguments": {}
}
```

若采用该方案，基线契约为：

- 作用域是 `default` 游戏的当前进程运行期；
- 同键、相同规范化 Command payload 的并发重试共享一次执行，不得重复应用状态变化；
- 完成后的同键同参重试返回首次记录的终态结果，不按照新状态重新执行；
- 游戏规则校验失败也是可读取的终态结果，使用同键同参重试返回相同拒绝结果；新意图必须使用新键；
- 同键不同 payload 返回明确的 Conflict 错误（建议 HTTP 409）；发生冲突的后续请求不得应用状态变化，首个已接受的 payload 和已有键绑定保持不变；
- 崩溃恢复窗口不保证保留该结果，恢复后客户端先同步当前状态，再决定新的动作；
- API Issue 必须定义 malformed request、并发 in-flight 重试、结果绑定和规范化 payload 的具体实现及测试。

动作名称、参数限制、响应 schema 和错误码属于对应 API Issues 的明确工作项。

## 4. GameView — CONFIRMED / PROPOSED

- 客户端接收适合观察的服务器状态视图，而不是可写的服务端内部对象。
- UI 和结构化 Agent 可以使用同一种公开 View。
- View 派生自权威状态，不在浏览器中形成第二套规则。
- 不因为未来可能有多个 UI 而在核心状态中保存展示偏好。

建议 View 带 `revision` 和 `run_id`，初始连接可以得到完整快照，再接收更新。

## 5. SSE 与重连

### Confirmed 语义

- 浏览器和 Agent 都能观察状态更新。
- 服务器到客户端的连接断开不影响游戏时钟。
- 客户端重连后必须能获得一致的当前状态。
- 迟到的 HTTP 响应或旧 SSE 事件不得覆盖客户端已知的较新 View。
- 崩溃恢复可能使服务器回到较早的游戏状态；客户端必须接受恢复后的权威状态并重新同步，不能用崩溃前缓存覆盖它。

### Proposed ordering metadata

建议用递增 `revision` 和每次进程运行不同的 `run_id` 实现上述语义：

- 同一 `run_id` 内按 revision 丢弃迟到的旧 View；
- `run_id` 改变时先接受恢复后的完整快照，再重新比较 revision；
- 具体字段和编码与 `runtime.md` 的 Revision 与恢复 PROPOSED 小节一致，由 API Issue 固化。

第一版状态较小时可直接发送完整公开 View，而不是预先建设复杂 JSON Patch 或 event-sourcing 框架；若未来状态规模证明需要增量协议，再单独评审。

## 6. 浏览器 UI 行为 — CONFIRMED

- 点击只发送 Command，不在 JavaScript 内直接修改权威资源。
- 点击后可有 pending 反馈，但不能通过本地加总资源伪造成功。
- 按钮 disabled 只是显示服务器状态；服务器仍必须独立校验。
- 两个页面可以操作同一局并看到相同的世界，不要求用户登录或选择角色。
- UI 刷新只是重新连接，不触发存档回滚。
- 第一版视觉验收采用 best effort 原版风格，而不是 DOM 或像素级等价。
