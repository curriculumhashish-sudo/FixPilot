<a id="subagent-loader-file-based-agents-design--invariants"></a>

# 子智能体加载器（基于文件智能体）：设计+不变量

请参阅 [ 项目根 AGENTS.md](../../../../AGENTS.md) 了解存储库范围的策略和工作流程。

该软件包 (`openhands.sdk.subagent`) 集中了 **子智能体发现 ** 和 ** 注册 **。 它的存在是为了让贡献者（人类或智能体式）能够回答：

- “这个智能体从哪里来？”
- “为什么这个定义胜过另一个定义？”

无需逆向工程 `LocalConversation` 和加载程序。

<a id="scope"></a>

## 适用范围

- **基于文件智能体**：Markdown 个文件 (`*.md`) 和 YAML 前置元数据。
- **Plugin 智能体**: `Plugin.agents`（已由插件加载器解析； 在此注册）。
- **编程智能体**：显式 `register_agent(...)` 调用。
- **内置智能体**：由`openhands-tools`提供，位于此SDK封装之外。

相关实施文件：

- `load.py`：文件系统发现+解析错误处理。
- `schema.py`：Markdown/YAML模式以及解析规则。
- `registry.py`: 注册表 API + “先注册者获胜”语义。
- `conversation/impl/local_conversation.py`：惰性插件和文件智能体注册。
- `openhands-tools/openhands/tools/preset/default.py`：内置智能体发现和注册。

<a id="invariant-1-discovery-locations--file-rules"></a>

## 不变量 1：发现位置和文件规则

<a id="directories-scanned"></a>

### 扫描的目录

**项目级（优先级高于用户级）：**

1. `{project}/.agents/agents/*.md`
2. `{project}/.openhands/agents/*.md`

**用户级别：**

3. `~/.agents/agents/*.md`
4. `~/.openhands/agents/*.md`

Notes:

- 仅扫描 ** 顶级 ** `*.md` 文件。
  - 子目录 (e.g. `{project}/.agents/skills/…`) 被忽略。
- `README.md` / `readme.md` 始终被跳过。
- 目录迭代是确定性的 (`sorted(dir.iterdir())`)。

<a id="parse-failures-must-be-non-fatal"></a>

### 解析失败必须是非致命的

如果单个文件无法解析（无效的 YAML 前置元数据、格式错误的 Markdown 等），则加载必须：

- 记录警告（带有堆栈跟踪），以及
- 继续扫描其他文件。

（参见 `load.py` 中的 `load_agents_from_dir`。）

<a id="registration-failures-must-be-non-fatal"></a>

### 注册失败必须是非致命的

如果无法注册基于已解析文件的定义或插件定义（例如，其
`skills` 命名了一项不存在的技能），注册必须：

- 记录一条警告，命名为智能体、其 `source` 和错误，并且
- 跳过该定义并继续注册其他定义。

（参见 `registry.py` 中的 `_register_definition`。）

<a id="invariant-2-resolution--precedence-who-wins"></a>

## 不变量 2：决议/优先级（“谁赢了”）

<a id="core-rule-first-registration-wins"></a>

### 核心规则：先报名者胜

一旦智能体名称在全局注册表 (`_agent_factories`) 中注册，后续来源不得覆盖它。

这是通过使用以下方式强制执行的：

- `register_agent(...)`（重复时加注； 用于程序化注册）
- `register_agent_if_absent(...)`（跳过重复项； 用于插件、文件智能体、内置）

<a id="effective-precedence-order"></a>

### 有效的优先顺序

`LocalConversation._ensure_agent_ready()` 为作为对话初始化的一部分加载的智能体建立此顺序：

1. 现有的注册表条目，包括显式 `register_agent(...)` 调用
2. 插件提供智能体 (`Plugin.agents` → `register_plugin_agents`)
3. 基于项目文件智能体
   - `{project}/.agents/agents/*.md` 然后 `{project}/.openhands/agents/*.md`
4. 基于用户文件智能体
   - `~/.agents/agents/*.md` 然后 `~/.openhands/agents/*.md`

内置函数由 `openhands-tools` 单独发现并注册
`register_builtins_agents()`. 因为所有非程序化来源都使用
`register_agent_if_absent(...)`，无论哪个源首先注册名称，都会保留该名称。 如果内置程序应充当回退方案，则在更高优先级的源之后调用内置注册。 智能体-服务器在工具路由器导入期间、每个会话文件发现之前注册内置程序。

<a id="deduplication-rules-inside-file-based-loading"></a>

### 基于文件的加载内的重复数据删除规则

基于文件的加载具有*两*层“先胜”重复数据删除：

1. **在一个级别**（`load_project_agents` / `load_user_agents`）内：
   - 对于相同的智能体名称，`.agents/agents` 战胜了 `.openhands/agents`。
2. **跨级别** (`register_file_agents`)：
   - 项目赢得了具有相同智能体名称的用户。

如果更改这些规则，请更新 `tests/sdk/subagent/` 中的单元测试。

<a id="invariant-3-markdown-agent-schema--semantics"></a>

## 不变量 3: Markdown 智能体模式 & 语义

<a id="frontmatter-keys"></a>

### 前置元数据键

支持的 YAML 前置元数据键（参见 `schema.py` 中的 `AgentDefinition.load`）：

- `name`（默认值：文件名主干）
- `description`
- `tools`（默认值：`[]`）：一个工具名称或名称列表
- `skills`（默认值：`[]`）：以逗号分隔的字符串或技能名称列表
- `model`（默认值：`inherit`）：`inherit`重用父级LLM； 另一个值作为 LLM 配置文件名称从 `profile_store_dir` 或默认配置文件存储加载
- `color`（可选）
- `max_iteration_per_run`（可选，正整数）
- `max_budget_per_run`（可选，USD中的正数）
- `hooks`（可选钩子配置）
- `profile_store_dir`（可选自定义LLM配置文件目录）
- `mcp_config`（可选MCP服务器地图）； `mcp_servers` 是已弃用别名。 当智能体作为代理子智能体运行时，`inherit_mcp_config` (`scope.py`) 会为每个子智能体提供其父节点的已解析 MCP 服务器（插件服务器合并，机密扩展），并且子对话通过 `_mcp_config_from_parent=True` 创建，因此它既不重新合并插件服务器也不重新扩展 `${VAR}`。 声明的服务器永远不会影响资格。
- `permission_mode`（可选）：`always_confirm`、`never_confirm` 或 `confirm_risky`； 遗漏继承父确认策略
- `condenser`（可选）：省略则使用默认总结上下文压缩器； `none` 或
  `false` 禁用上下文压缩； 映射配置上下文压缩器

**未知密钥被保留**在`AgentDefinition.metadata`中。

<a id="body--system-prompt"></a>

### 本体 → 系统提示词

Markdown **主体内容**成为智能体的`system_prompt`。

目前，当实例化智能体时，这将应用为：

- `AgentContext(system_message_suffix=agent_def.system_prompt)`

这意味着它被附加到父系统消息中（不是完整的替换）。

<a id="tool-and-skill-resolution"></a>

### 工具和技能解析

`tools` 值在工厂实例化之前仍保留名称。 每个名称必须已经注册； 未知的工具引发`ValueError`。 有效名称变为 `Tool(name=...)`。

`skills` 工厂创建时解决。 项目技能优先于用户技能，公共技能被排除，未知技能提升`ValueError`。

<a id="trigger-examples-in-description"></a>

### 描述中的触发示例

加载器将 `<example>…</example>` 标签从 `description`（不区分大小写）提取到 `AgentDefinition.when_to_use_examples` 中。

这些示例用于其他地方的触发/路由逻辑。

<a id="minimal-example"></a>

### 最小的例子

```markdown
---
name: code-reviewer
description: |
  Reviews code changes.

  <example>please review this PR</example>
  <example>can you do a security review?</example>
tools:
  - terminal
model: inherit
permission_mode: confirm_risky
color: purple
# Any extra keys are preserved in `metadata`:
audience: maintainers
---

You are a meticulous code reviewer.
Focus on correctness, security, and clear reasoning.
```

<a id="user-facing-documentation"></a>

## 面向用户的文档

Markdown 智能体的用户文档位于文档存储库中。 如果您更改上述不变量中的任何一项，请更新此文件和用户文档。

- 已发布指南： https://docs.openhands.dev/sdk/guides/agent-file-based
