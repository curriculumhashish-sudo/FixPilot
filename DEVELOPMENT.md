<a id="development-guide"></a>

# 开发指南

<a id="setup"></a>

## 环境配置

```bash
git clone https://github.com/OpenHands/software-agent-sdk.git
cd software-agent-sdk
make build
```

<a id="repository-boundaries"></a>

## 仓库职责边界

本仓库负责 Python SDK 和 Agent Server，涵盖智能体与工具行为、对话、工作区、事件，以及新的 REST/WebSocket 端点。API 契约通过 `clients/typescript/` 提供给 [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 中的 Agent Canvas；自动化调度、Webhook、运行历史和任务分发由 [`OpenHands/automation`](https://github.com/OpenHands/automation) 负责。如果 PR 提交到了错误的仓库，应建议关闭并移至负责该功能的仓库。每个 PR 都须遵循 [`.agents/skills/custom-codereview-guide.md`](.agents/skills/custom-codereview-guide.md)。

<a id="code-quality"></a>

## 代码质量

```bash
make format                              # 格式化代码
make lint                                # 检查代码
uv run pre-commit run --all-files        # 运行所有检查
```

提交时会自动运行 pre-commit 钩子，执行类型检查和代码检查。

<a id="testing"></a>

## 测试

```bash
uv run pytest                            # 运行所有测试
uv run pytest tests/sdk/                 # 仅运行 SDK 测试
uv run pytest tests/tools/               # 仅运行工具测试
```

<a id="project-structure"></a>

## 项目结构

```
software-agent-sdk/
├── openhands-sdk/          # 核心 SDK 包
├── openhands-tools/        # 内置工具
├── openhands-workspace/    # 工作区管理
├── openhands-agent-server/ # 智能体服务器
├── examples/               # 用法示例
└── tests/                  # 测试套件
```

<a id="contributing"></a>

## 参与贡献

1. 创建新分支
2. 修改代码
3. 运行测试和检查
4. 推送并创建拉取请求

如有问题，请加入我们的 [Slack 社区](https://openhands.dev/joinslack)。

<a id="llm-message-construction-invariant"></a>

## LLM 消息构造不变量

**本仓库构造的每个 LLM 请求，都必须在第一条 `user` 消息之前放置一条 `system` 消息。**

该约束由 `Agent.init_state()`（`openhands-sdk/openhands/sdk/agent/agent.py`）统一执行： 它确保 `SystemPromptEvent` 位于事件流开头（索引 0/1）；如果用户的 `MessageEvent` 出现在它之前，则抛出 `AssertionError`。
`LLMConvertibleEvent.events_to_messages()`（`openhands-sdk/openhands/sdk/event/base.py`） 按顺序将事件流转换为消息，确保主智能体循环始终以系统消息开头。

此要求适用于**所有**独立的 LLM 调用，包括上下文压缩器、目标评估器、Agent Server 配置预检、安全分析器、标题生成、清理提示词、钩子提示词、ToolShield 分析器和视觉检查。 这些调用的消息列表都必须以 `system` 角色开始。

<a id="why-it-matters"></a>

### 约束的作用

- **统一行为指导：** 独立调用若省略系统消息，就会丢失其他调用路径共有的上下文和格式要求。
- **正确的传输序列化：** 在 OpenAI Responses API 中，`Message.to_responses_value()` 将 `system` 转为字符串（对应 `instructions`），将 `user` 转为字典列表（对应 `input`）。 仅通过一条 `user` 消息发送行为指导，会混淆执行方式和任务内容；仅有一条 `system` 消息则会生成带 `instructions` 但 `input` 为空的请求。
- **订阅/Codex 传输层**会把系统消息片段添加到第一条用户消息前；缺少系统前导内容时， 请求将缺失必要的行为指导。

<a id="documented-exceptions"></a>

### 已记录的例外

- **ACP 智能体：** 实际的系统提示词和工具由 ACP 服务器管理，而非由 SDK 构造的消息列表管理； SDK 会生成一个占位的 `SystemPromptEvent`，供可视化工具使用。
- **订阅/Codex 传输层**（`transform_for_subscription`）：由于 Codex 风格的端点不接受 过长或过于复杂的 `instructions`，系统片段会被添加到第一条用户消息的*内容内部*。 这种方式将消息结构展平，同时保留原有的顺序要求。

<a id="reviewer-checklist"></a>

### 审查要点

第一条消息的角色必须是 `system`，除非属于上述已记录的例外。
