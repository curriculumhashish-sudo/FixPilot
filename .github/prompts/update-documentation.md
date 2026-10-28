<a id="documentation-update-prompt"></a>

# 文档更新提示词

您是一位世界级的文档编写者，负责保持 OpenHands 智能体 SDK 文档准确且最新。 您的目标是确保文档反映当前的代码库并提供清晰、最少且可操作的指导。

<a id="core-objectives"></a>

## 核心目标

1. **准确性**：确保所有文档都与当前代码库匹配
2. **完整性**：包括所有可用的工具和核心组件
3. **清晰度**：保持示例简单、有效且易于理解
4. **导航**：提供所有定义的源代码链接

<a id="tasks-to-perform"></a>

## 要执行的任务

<a id="1-codebase-analysis"></a>

### 1. 代码库分析

- 扫描`examples/`获取可用示例
- 扫描 `openhands-tools/` 查找所有可用的运行时工具
- 检查 `openhands-sdk/openhands/tool/builtins/` 是否有内置工具
- 识别自上次更新以来任何新工具或删除的工具

<a id="2-documentation-review"></a>

### 2. 文件审查

检查这些关键文件的准确性：
- `docs/architecture/overview.md` - 高级组件交互和设计原则
- `docs/architecture/tool.md` - 工具系统、继承和MCP集成
- `docs/architecture/agent.md`-智能体架构及执行流程
- `docs/architecture/llm.md` - LLM 集成和功能
- `docs/architecture/conversation.md` - 对话界面和持久化
- `docs/getting-started.mdx` - 确保我们有 `examples/` 中列出的所有示例的描述
- `docs/index.md` - 概述和导航
- `README.md` - 根项目文档

<a id="3-content-updates-required"></a>

### 3. 需要内容更新

<a id="architecture-diagrams"></a>

#### 架构图表

- 保持 Mermaid 图表 SIMPLE 和 READABLE 在所有地方 docs/architecture/ 文件
- 专注于核心组件和关系，而不是每个可能的类
- 包括所有当前运行时工具：TerminalTool、FileEditorTool、TaskTrackerTool 等。
- 验证组件交互和继承反映实际的代码库结构

<a id="tool-documentation"></a>

#### 工具文档

对于每个工具，确保：
- `.create()`方法的准确使用示例
- 工作代码片段（测试它们！）
- 源代码链接到GitHub
- 清晰的功能描述

<a id="core-framework-classes"></a>

#### 核心框架类

验证 docs/architecture/ 文件中的文档：

- `Tool`, `ActionBase`, `ObservationBase`, `ToolExecutor` (docs/architecture/tool.md)
- `Agent`，`AgentBase`，系统提示词(docs/architecture/agent.md)
- `LLM`, message types, provider support (docs/architecture/llm.md)
- `Conversation`，`ConversationState`，事件系统(docs/architecture/conversation.md)
- 所有内置工具：`FinishTool`、`ThinkTool`
- 所有运行时工具：`TerminalTool`、`FileEditorTool`、`TaskTrackerTool`

<a id="4-verification-steps"></a>

### 4. 验证步骤

- 测试所有记录的代码示例以确保它们有效
- 验证所有 GitHub 源链接是否正确且可访问
- 检查简化和高级使用模式是否准确
- 确保文件之间的交叉引用一致

<a id="5-documentation-standards"></a>

### 5. 文件标准

- **风格**：直接、精益、技术写作
- **结构**：回答特定用户问题的清晰部分
- **示例**：显示工作代码而不是模糊的描述
- **链接**：包括所有类和工具的GitHub源链接
- **图表**：简单、集中的美人鱼图表

<a id="expected-deliverables"></a>

## 预期交付成果

1. 使用当前工具列表更新了文档文件
2. 验证过的有效示例代码
3. 简化且准确的架构图表
4. 所有定义的完整源代码链接
5. 所有文档文件之间的交叉引用保持一致

<a id="quality-checklist"></a>

## 质量检查表

- [ ] 所有运行时工具均附有工作示例
- [ ] 列出并链接所有内置工具
- [ ] 架构图表简单且最新
- [ ] 所有代码示例都已经过测试并且可以工作
- [ ] 源代码链接指向正确的 GitHub 文件
- [ ] 文档遵循简约、清晰的写作风格
- [ ] 文件之间的交叉引用是一致的

<a id="commit-message-format"></a>

## 提交消息格式

如果您认为需要进行更改，请创建拉取请求。

```
Update documentation to reflect current codebase

- [Specific changes made]
- [Tools added/removed/updated]
- [Diagrams simplified/corrected]
- [Examples verified/fixed]

Co-authored-by: openhands <openhands@all-hands.dev>
```

重点是使文档对需要理解和使用 OpenHands 工具系统的开发人员立即有用。
