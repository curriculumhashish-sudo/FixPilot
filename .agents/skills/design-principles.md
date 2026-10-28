---
name: design-principles
description: Core architectural design principles of the OpenHands Software Agent SDK. Reference when making architectural decisions, reviewing PRs that change agent/tool/state boundaries, or evaluating whether a proposed change aligns with V1 design goals.
---

<a id="sdk-design-principles"></a>

# SDK 设计原则

参考：<https://docs.openhands.dev/sdk/arch/design>

<a id="quick-summary"></a>

## 快速总结

1. **相对于强制沙盒的可选隔离**沙盒是选择性加入的，而不是通用的。 智能体并且工具执行默认在单个进程中运行。 当需要隔离时，可以透明地对同一堆栈进行容器化。

2. **默认为无状态，一个单一的真相状态** 所有组件 — 智能体，tools, LLMs, configurations — are **immutable Pydantic models** 在构建时验证。 唯一可变的实体是对话状态。 这使得确定性回放和稳健性得以实现持久化。

3. ** 智能体和应用程序之间的边界清晰** SDK（智能体核心）、工具、工作区和Agent Server之间的严格分离。 应用程序通过APIs进行通信，而不是嵌入智能体。

4. 可组合组件用于扩展性** ** 智能体是由可互换组件组成的图——工具、提示词、LLMs、上下文——**声明式地描述**。 开发人员无需修改核心代码即可重新配置功能。

<a id="implications-for-development"></a>

## 对发展的影响

- 由于智能体是不可变的 Pydantic 模型，因此它们的配置 ** 是 ** 它们的可序列化表示。 不需要从运行时实例进行“逆向工程”智能体配置。
- 工具实现（可调用）是唯一不可序列化的部分； 这是通过`tool_module_qualnames`进行远程转发解决的。
- 其他所有内容（system_prompt、模型、技能、工具名称）已经是声明性数据，可以已序列化并直接转发。
- 避免为同一配置创建多个事实来源的模式（e.g.、工厂函数 AND 提取的定义）。
- `model_copy(update=...)` 应谨慎使用，并通过明确定义的路径使用，以避免破坏无状态性。
