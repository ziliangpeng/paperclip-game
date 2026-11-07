# AGENTS.md

本文件规定 paperclip-game 的 Issue、实现、评审与合并流程。`requirements/` 是产品与工程需求的唯一版本化事实来源；本文件不复制游戏规则或完整测试矩阵。

## 1. 开工授权与交付单位

1. 所有实现工作必须从一个 **open、所有 blockers 均已 closed 的 GitHub Issue** 开始。开工前阅读 Issue 链接的需求及其状态。聊天评论、口头要求、代码里的 TODO 或笼统待办都不是实现授权。
2. 一个 Agent 同一时间只认领一个 Issue；一个 Issue 只对应一个可独立测试的 PR。不要把一个 Issue 拆成一串实现 PR，也不要用一个 PR 打包多个 Issue。
3. Worker 从最新 `main` 创建范围明确的 `issue-<N>-<short-scope>` 分支，提交一个 PR，并在 PR body 使用且只使用一个 `Refs #N`。不得使用 `Closes` / `Fixes` / `Resolves` 等自动关闭关键词；Issue 只能在主分支验证通过后由 controller 显式关闭。
4. 禁止直接 push 到 `main`；修复和 revert 也必须走 PR。实现 Agent 不得靠自我批准完成合并。
5. 不做 drive-by fix。发现范围外问题时，另开 Issue 记录；不要夹带在当前 PR 中。

## 2. Milestone、依赖与 Issue 内容

- 使用 **GitHub Milestones** 表达交付阶段，使用 Issue body 中的可移植依赖标记表达 Issue 关系：
  - `Blocked by: #123`
  - `Blocks: #456`
- 多个依赖时按行重复同类标记；没有依赖时写 `None`。自动化选任务和合并前都必须验证 `Blocked by` 指向的 Issues 已经 closed。
- 当前 Milestone 的 Issues 应细化到各自能由一个独立 PR 交付；只有下一个 Milestone 可以保留粗粒度任务轮廓。更远阶段先留在 Milestone 地图中，等前一阶段带来新信息后再细化，不要预先生成大量会过期的详细 Issues。
- 每个可实施 Issue 必须包含：**Objective、Specification references、Scope、Non-goals、Dependencies、Acceptance criteria、Required tests / evidence**，以及适用时的 **Risk flags**。使用 `.github/ISSUE_TEMPLATE/task.md`。
- Issue 引用需求文件、章节和稳定的不变量，不在 Issue 内另写一套游戏规则或复制完整测试矩阵。`CONFIRMED`、`PROPOSED`、`OPEN` 的含义以 `requirements/README.md` 为准。
- 如果需求相互冲突，或产品行为的歧义会影响实现，给 Issue 加上 `needs-decision` 并停止相关工作。需求 resolver 必须先按需求确认流程更新 `requirements/`，再解除阻塞；实现 Agent 不得自行发明规则。
- 纯机械实现细节可由 Agent 在不扩大 Scope、不改变产品行为的前提下选择，但必须用测试证明所选行为。

## 3. 实现、测试与证据

- 按 `requirements/testing.md` 和 Issue 的风险选择必要测试。测试必须覆盖 Acceptance criteria 和真实失败模式，不以某个魔法覆盖率百分比作为目标，也不要求每个 PR 机械执行完整测试矩阵。
- PR 必须列出实际执行的命令、结果和 Acceptance criteria 对应证据；不能只写“应该可用”或粘贴未经执行的结果。
- UI 按 `requirements/testing.md` 做语义、状态与真实可玩路径验证，视觉为 best effort，可附截图辅助观察，但不设 pixel-perfect 截图门槛。
- 不得为了让实现变绿而删除或削弱测试、lint、CI、required checks、安全控制或 merge controls。修改 test/CI/merge infrastructure 属于 high-risk，必须独立评审；属于下一节双人评审类别的，还必须满足双人要求。

## 4. 独立 Agent 评审

本流程不设置 human per-PR code review gate。质量由可执行验收测试、CI、**fresh-context 独立 reviewer Agents** 和独立 merge controller 共同保证。

- 普通变更至少需要 **1 名独立 reviewer** 的批准。
- Core simulation、economy/game rules、concurrency、persistence、CI 或 merge workflow 变更至少需要 **2 名独立 reviewer**；其中 1 名必须执行 adversarial correctness review，主动寻找违反不变量的执行路径。这两人可以包含该 adversarial reviewer，不要求第三人。
- Reviewer 必须独立于实现 Agent，并使用 fresh context。实现 Agent 自己的工作不能充当所需的独立批准，也不能成为自己 PR 的唯一 reviewer。
- Reviewer 对当前 PR HEAD 给出明确结论、检查范围和发现；新提交后必须重新检查受影响的结论与证据。

## 5. Blocking 与 non-blocking 标准

每条 **blocking finding** 必须同时给出：

1. 被违反的 Issue Acceptance criterion 或精确需求文件/章节/不变量；
2. 精确代码位置（文件与行号，或等价定位）；
3. 可复现命令/测试，或明确可演示的执行路径及其实际错误结果。

只有已证明的问题可以阻塞合并。Blocker 类型包括：

- Acceptance criterion 未满足；
- 未经授权的游戏行为或需求变更；
- 服务器权威状态被破坏；
- 真实竞态、lost update 或 double execution；
- 无效或不正确的恢复；
- Issue 要求的测试或证据缺失；
- 通过削弱测试或质量门槛隐藏回归；
- 已演示的 data/security/main-branch 风险。

以下属于 **non-blocking**：品味或命名偏好、同样合理的替代方案、未经测量的优化、超出当前需求的 speculative abstraction 或 multi-instance 预备、无关重构、只提升优雅程度的注释，以及未验证的理论担忧。这类意见必须明确标为 non-blocking，不能阻止合并。值得做的后续工作另开 Issue，不以无限 polish 拖延当前交付。

## 6. Merge controller 与完成条件

独立 merge controller 在合并前机械核验：

- [ ] PR 恰好链接一个仍为 open 的 Issue；
- [ ] 所有 `Blocked by` Issues 均已 closed；
- [ ] 变更未超出 Issue Scope，也没有未经批准的需求偏差；
- [ ] 所有 required CI checks 通过；
- [ ] 每项 Acceptance criterion 都有所要求的证据；
- [ ] 按风险所需数量和类型的独立批准齐全，评审对应当前 HEAD；
- [ ] 没有尚未解决的 blocking findings；
- [ ] 最新变更已经重新检查，测试与评审证据没有停留在旧提交；
- [ ] required checks 已在基于当时最新 `main` 的合并结果上通过。

后续实现 merge controller 时，必须使用 **merge queue 或等价串行化机制**，在合并前将 PR update/rebase 到当时最新 `main`，并对该精确合并结果重新执行 required checks，避免并行 PR 各自通过旧基线却产生语义竞态。

Reviewer 输出必须由负责编排的 controller 获取并保存，绑定 PR 与 HEAD SHA。PR 评论中的自称批准、复制粘贴的评审文本或伪造评论不能替代 controller 验证过的评审记录。

Controller 按队列执行合并后，必须运行规定的 `main` post-merge verification；验证通过后，controller 才显式关闭对应 Issue，并将其标记为依赖意义上的完成。验证期间 Issue 保持 open，任何自动提前关闭都必须 reopen。若 `main` 出现问题，暂停新的 feature merges，保持或重开关联 Issue，通过关联 regression Issue 的 PR 修复或 revert。Agent 应优先处理 regression、main breakage 和其他 blocker，再领取新 Issue。

## 7. Public-repository hygiene

本仓库按 **PUBLIC repository** 管理：即使当前仍因公开前清理而处于 Private，所有 committed files、git history、Issues、PRs/comments、CI logs、screenshots、fixtures 和 CI artifacts 也一律按未来会公开的信息处理。

- 不得读取、复制或向仓库内容及公开日志加入 credentials、tokens、`.env` 内容、SSH keys、cookies、personal information、绝对 home paths/user names、private hostnames 或其他私有材料。使用 repo-relative paths 和明显虚构的 example data；test fixtures 不得使用真实个人数据。
- Worker 不得让 secrets 或私有信息出现在 test output、browser screenshots、错误转储或调试日志中。
- Push/merge 前检查**完整 diff、相关 history，以及将公开的 generated files、logs、screenshots、fixtures 和 CI artifacts**，不能只检查最终文件树。
- 一旦发现 secret 或 private datum，立即停止 publishing/merging 并升级到适当的人工处理。后续提交删除不等于从公开历史中擦除；history rewrite、泄露处置和 key rotation 必须按相应人工安全流程执行。
- 仓库所有者已明确允许其本人的 Git author/committer 署名和邮箱作为公开提交元数据，不要求清理或改写该元数据。此例外不扩展到其他人的个人信息，也不允许任何凭据、私有文件或私有项目内容。

Worker、reviewer 及其自动化只获得完成任务所需的最小权限；不得分发不必要的 secrets、admin credentials 或直接写 `main` 的权限。
