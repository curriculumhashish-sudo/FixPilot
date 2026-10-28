<a id="maintaining-the-map-periodic-or-weekly"></a>

# 维护地图（定期或每周）

当服务器发生变化时，特征图就会腐烂。 此传递保持诚实，并回答了有关自上次传递以来的间隔的三个独立问题：
**每个功能都存在吗？ 它是否像 API 消费者所看到的那样有效？ 是每个
更改记录和意图？**合并的PR证明了最后两个的None。

严谨的单位是特征：每个家庭文件都得到来源报道和现场报道，而不需要重新证明每句话。 这是一个程序，而不是一个
调度程序：除非要求，否则不要创建自动化、合并或外部发布。

<a id="outcomes"></a>

## 结果

选择一个并说出哪一个：

- **干净**：每个家庭都有来源和现场报道，意图一致，没有什么值得运送的。 没有分支，就没有 PR。
- **更改**：一 PR 个经过验证的地图/CLI 更正，与产品修复分开。
- **被阻止/部分**：覆盖无法完成。 准确地说出什么和为什么； 不要称其为干净或推进可接受的基线。

编辑范围仅限于该技能的目录（SKILL.md、references/、scripts/）。 切勿在维护期间编辑产品代码。

<a id="1-freeze-the-comparison"></a>

## 1. 冻结比较

记录 UTC 运行时间、预算（模型、支出）、可用帐户和密钥以及允许的副作用。 获取 `main` 并将其完整的 SHA 冻结为 TARGET。 检查`git rev-parse --is-shallow-repository`； 有界加深
`git fetch --depth=...` 直到 BASE 出现（来自浅克隆的空日志不是“无更改”）。 BASE是之前完成的pass的记录TARGET，保留在`Maintenance baseline: main@<sha> (<date>)`行
[the map index](feature-map/README.md) (`control-agent-server map baseline`
读它）； 第一次运行时，在商定的截止时间 (`git rev-list --first-parent -1 --before="$CUTOFF" "$TARGET"`) 之前的最后一个父级提交。 更改地图的通道会将该线移动到 PR (`map baseline --set "$TARGET"`) 中的 TARGET，因此合并 PR 会接受新的基线。

```sh
git merge-base --is-ancestor "$BASE" "$TARGET"
git log --first-parent --format='%H %cI %s' "$BASE..$TARGET"
git diff --name-status "$BASE" "$TARGET"
```

每日通行证可能是**增量通行证**：仅针对在BASE..TARGET中路径或路线发生变化的家庭提供源和实时报道(§2) 以及链接自 BASE 以来已关闭问题的行。 [daily.md](daily.md) 就是这个过程。 它在报告中提到了“delta”。 现在还是需要全量更新（每周或在发布前），因为依赖版本的升级（LiteLLM、FastAPI、MCP）不会改变行为，但会更新路由器。

对 BASE 和 TARGET 以及 `control-智能体-server 启动使用单独的工作树
--new --checkout <worktree>` for each (after `uv 同步 --dev` 在每个工作树中），
所以状态和端口永远不会混合。 切勿从今天的来源重建基线或覆盖上一次的证据。

<a id="2-diff-the-contract-not-just-the-files"></a>

## 2. 区分合同，而不仅仅是文件

面向智能体的合约是路由表加上请求和响应模式。 比较两端：

```sh
control-agent-server map diff --base "$BASE_WORKTREE" --target "$TARGET_WORKTREE"
control-agent-server map owners --changed "$BASE..$TARGET"
```

每增加、删除或新增的已弃用路线是一个地图变更：新路线需要一个所有者`map coverage` 直到它有一个子功能，被移除的路由需要标记其子功能 `retired` with the authorizing PR, and a 已弃用路由需要家族的Gotchas中的移除版本。 对于模式 changes, the CI's REST breakage check (oasdiff against the last release) 会告诉你发生了不兼容的变化。 读取它 PR 评论而不是重新推导它，重新推导受影响的食谱。

`map owners --changed` 将每个更改的文件路由到其家族
`Source:` 前缀覆盖它并列出了没有系列声明的更改的产品路径。 将其中每一个映射到一个系列或一个明确的非智能体面向的原因（测试、CI、文档、没有合同更改的内部重构）。 对于共享模型（`openhands-sdk` 事件、设置、LLM 配置），扩展到序列化它们的每个系列，而不是对其中一个进行采样。

<a id="3-build-the-pr-intent-ledger"></a>

## 3. 构建 PR 意向账本

解决 BASE..TARGET 中的每个提交通过 API (`repos/OpenHands/agent-sdk/commits/<sha>/pulls` 到达其 PR； 提交消息 `(#123)` 正则表达式错过变基和直接推送）。 阅读每个 PR 的描述、链接的问题接受标准、相关审查讨论和文件列表。

| 提交/PR | 改变路径 | 家庭/路线 | 预期结果+引用证据 | 需要运行时证明 |
|---|---|---|---|---|

将直接提交和无法解析的 PR 记录为未知意图。 保持意图（`documented`、`undocumented`、`contradictory`）独立于运行时（`pass`、`fail`、`blocked`、`not-run`）。 工作变更可能仍然没有记录。 切勿编辑 PR 描述（`HUMAN:` 部分仅供人类使用）来证明事后更改的合理性。

<a id="4-index-hygiene-and-source-wave"></a>

## 4. 索引卫生和源波

运行`control-agent-server map check`和`map coverage`； 修复丢失、重复和无效的条目（`map check --fix-counts` 刷新索引计数）。 然后为每个家庭档案指定一名只读读者（如果可以委托，则并行）。 每个人都会读取该系列的当前源代码并
返回：摘要、来源入口、可能随引用发生偏差（或 None）、
地图中缺少新路线或行为、消费者更改（`RemoteConversation`、`RemoteWorkspace`、TypeScript 客户端）以及一个实时菜谱。 读者从不编辑文件，也从不启动服务器。

每当 CLI 获得动词时，重新检查过时的工具声明：grep the map for
`blocked`、`not run`、`harness gap`、`no verb` 和 `cannot be driven`，并重新驱动当前动词现在可以到达的任何内容（与
`control-agent-server --help`).

<a id="5-live-pass"></a>

## 5. 现场通行证

即使源看起来很干净也是必需的。 一名协调员拥有每个已启动的运行并串行驱动它； 并行实时工作每个工作人员需要一个 `launch --new`，每个工作人员都有自己的导出 `AGENT_SERVER_VERIFY_RUN`。 每个家庭至少对其所有入口（REST、WebSocket、SDK、TypeScript 客户端）的行为进行一次改变。 持有三不变量：

1. 切勿驾驶自上次意外以来未经过修改的跑步 (`control-agent-server doctor`; `restart` 或在运行被楔入时重新启动）。
2. 迄今为止捕获的证据在每次清理后都幸存下来（在`stop`之后检查）。
3. 驱动器启动后的任何内容都不会超过其有用性：配方不再需要的对话将被删除，后台捕获将停止，运行将停止。

由技能漂移引起的医生失败是漂移：修复它并在呼叫阻塞之前重试一次。 仅在具有具体先决条件和尝试的路线的情况下，无法达到的功能是`blocked`。

当 TypeScript 客户端的固定服务器映像 (`clients/typescript/package.json` → `config.agentServerImage`) 滞后于 TARGET 时，请注意哪些食谱的消费者方法尚未在客户端中； 那是这里拥有的客户端漂移，而不是地图漂移。

<a id="6-triage-and-ship"></a>

## 6. 分诊和运送

- **地图漂移**（地图关于预期行为是错误的）：修复条目，重新驱动，引用更改它的PR。
- **利用差距**：修复CLI，证明新动词live，re-drive。
- **产品错误**：记录`fail`并提供证据和最小重现命令列表； 在此存储库（或所属存储库）中报告它，而不是在地图中 PR。
- **已知错误，不同失败**: a `known bug` 标记的命令没有匹配的 `# bug: PREDICATE` 被报告了 `fail` 根据观察到的状态和提示。 阅读转录：文档中的错误可能已经改变了形态（更新谓语和散文，引用） PR或者，新的失败可能会掩盖它（单独对它进行分析）。 永远不要为了把子弹转回来而扩大谓语 `xfail`.
- **意图差距**（行为在没有文档的情况下发生改变）：通过PR链接向用户报告； 不要“修复”地图来默默祝福它。

对于 ** 更改 **：一 PR 个经过验证的更正。 重新阅读所有更改的文件，运行`map check`、`map coverage`和CLI测试，更新`Maintenance baseline`行到TARGET，并将证据报告（失败/阻塞）和意图日志放在PR描述中或在`.pr/`下。 对于 ** 干净 ** 或
**已阻止**：无PR； 诚实地报告结果和覆盖范围。

将简明的运行记录（涵盖的家庭、无法达到的先决条件、已确认的漂移、结果）保留在临时位置； 不要犯他们。
