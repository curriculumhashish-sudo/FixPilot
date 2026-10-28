<a id="contributing"></a>

# 参与贡献

感谢你帮助改进 OpenHands 软件智能体 SDK。

本仓库提供底层基础。我们希望 SDK 保持稳定和可扩展，让各种应用都能可靠地基于它构建。

我们重点考虑的下游应用包括：
- [OpenHands-CLI](https://github.com/OpenHands/OpenHands-CLI)（客户端）
- [OpenHands app-server](https://github.com/OpenHands/OpenHands/blob/main/openhands/app_server/README.md)（客户端）
- [OpenHands Enterprise](https://github.com/OpenHands/OpenHands/blob/main/enterprise/README.md)（客户端）

SDK 本身提供 Python 接口。此外，
[agent-server](https://docs.openhands.dev/sdk/guides/agent-server/overview) 作为
REST/WebSocket 服务器组件，将 SDK 的能力用于远程执行和系统集成。 所有变更都应保持这两类接口的稳定与一致。

<a id="a-lesson-we-learned-why-we-care-about-architecture"></a>

## 我们的经验教训：为什么重视架构

在早期迭代中，我们反复遇到同一类问题：下游应用的需求或假设渗入了核心逻辑。

这种耦合在当时看似方便，却往往会在其他环境、工作区、执行模式或评估配置中引发隐蔽的问题。

OpenHands V0 的架构过于集中，难以同时支持内置的 CLI、评估脚本、Web 服务器， 以及基于它构建的 OpenHands Cloud 等多个应用。

更详细的背景与经验总结，请参阅我们的论文：
[OpenHands: An Open Platform for AI Software Developers as Generalist Agents](https://arxiv.org/abs/2511.03690)

我们将 SDK 作为独立的基础重新构建，正是为了避免再次出现这类问题。

<a id="principles-we-review-prs-with"></a>

## PR 审查原则

欢迎各种规模的贡献，共同改进和扩展软件智能体 SDK。

我们在以下方面有明确的要求：

- **OpenHands SDK 是独立的组件**：下游应用都是它的客户端。
- **优先设计接口，减少特例**：客户端需要某种能力时，应新增或改进清晰、可复用的接口或扩展点。
- **优先考虑可扩展性**：让多个客户端都能使用新功能，无须重写核心逻辑。
- **避免隐含假设**：不要依赖仅存在于某个应用中的特定环境变量、工作区布局、请求上下文或运行时特性。
  - 工作区*确实*需要表达本地、Docker、远程等环境差异，但这些假设必须通过参数与校验明确表达， 并限定在 `workspace` 层。
- **避免客户端专用的代码路径**：不要加入只适用于某个下游应用的逻辑。
  - 可以提供多种工作区实现；SDK 核心行为应根据能力或配置决定， 不应根据调用方是 CLI、app-server 还是 SaaS 来分支。
- **保持智能体循环稳定**：将稳定性视为一项功能，谨慎修改控制流和看似微小的行为细节。
- **兼容性是 API 的一部分**：可能影响下游客户端时，应明确说明影响并考虑迁移路径。 项目已有可供使用的弃用机制。

<a id="new-ai-providers"></a>

### 新增 AI 提供商

除非某个 AI 提供商已广泛普及且被 OpenHands 用户普遍使用，否则为其新增集成通常不属于 SDK 的范围。 SDK 应提供可复用的接口和扩展点，无须维护大量提供商专用的长尾集成。

不满足上述条件的功能请求和拉取请求应标记为超出范围，并礼貌地关闭。 贡献者仍可使用现有的通用提供商接口，或在外部维护集成。 如果需求变得广泛且持续，可以结合用户使用情况和可维护的集成方案重新评估。

如果不确定变更是否超出这些边界，请尽早沟通。我们很乐意一起设计清晰的接口。

<a id="practical-pointers"></a>

## 实用参考

本文件主要介绍原则。具体操作请参阅：
- [AGENTS.md](AGENTS.md)：供 AI 智能体使用
- [DEVELOPMENT.md](DEVELOPMENT.md)：供开发者使用
- [openhands-sdk/openhands/sdk/subagent/AGENTS.md](openhands-sdk/openhands/sdk/subagent/AGENTS.md)：基于文件的子智能体发现、优先级和任务交接约定
- `examples/01_standalone_sdk/41_task_tool_set.py`：向已注册的子智能体委派工作，并支持恢复执行
- `examples/01_standalone_sdk/42_file_based_subagents.py`：以编程方式注册 `AgentDefinition`

<a id="design-doc-for-non-trivial-prs"></a>

## 较复杂 PR 的设计文档

对于新增或修改公共 API（Python 或 agent-server 的 REST/WebSocket 接口）、引入新子系统、 调整智能体循环行为或进行迁移等较复杂的 PR，审查者往往只能根据差异重建设计思路。 这既费时，也容易遗漏兼容性风险。因此，我们鼓励附上一份简短的设计文档，帮助审查者快速理解方案； 这不是强制要求。

约定如下：

1. 编写一个**自包含的 HTML** 页面（内联 CSS/SVG，可双击打开），结合实际代码说明代码/API 设计， 并展示变更**前后的对比**。涉及接口时，应对比签名、模式或事件结构， 并说明兼容性影响：新增能力、不兼容变更，或由功能开关控制。
2. 将页面提交到临时的 **`.pr/`** 目录，例如 `.pr/design.html`。此目录仅存放 PR 专用产物。 PR 合并到 `main` 后，`.github/workflows/pr-artifacts.yml` 会自动创建或更新清理 PR，将该目录从 `main` 中移除。
3. 在 PR 描述靠前的位置添加 htmlpreview 链接，指向发起 PR 的派生仓库和分支， 以便合并前就能预览：

   ```
   https://htmlpreview.github.io/?https://github.com/<your-fork>/<repo>/blob/<your-branch>/.pr/design.html
   ```

修正拼写、添加一行保护条件、更新依赖或修复小问题等简单 PR 可以省略设计文档。

[OpenHands extensions](https://github.com/OpenHands/extensions) 仓库中的
`pr-design-doc` 技能可以帮助生成此页面。

<a id="questions--discussion"></a>

## 提问与讨论

欢迎加入 Slack：https://openhands.dev/joinslack
