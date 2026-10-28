<a id="agent-based-hooks-example"></a>

# 基于智能体的 Hook 示例

此文件夹演示了 `type="agent"` 挂钩 — 一个生命周期挂钩，其决策由 LLM 驱动的子智能体而不是 shell 脚本生成。

有关 shell 命令挂钩，请参阅 [`../33_hooks/`](../33_hooks)。

<a id="why-an-agent-hook"></a>

## 为什么要使用智能体钩子

基于 shell 的 PreToolUse 挂钩只能阻止其黑名单字面匹配的内容。 智能体将 `cat /etc/passwd` 重写为 `awk '{print}' /etc/passwd` 并跳过。 智能体钩子会分析命令的**语义意图**，无论使用什么工具名称，都拒绝。

<a id="example"></a>

## 示例

- **main.py** — 两个智能体钩子，每个钩子都有自己的对话：
  - **PreToolUse**“安全审查者”拒绝意图读取`/etc/passwd`的命令，即使黑名单中没有出现明显的关键字。
  - **Stop**“质量审核员”拒绝让主智能体完成，直到工作区中出现所需的可交付成果 (`REPORT.md`)。

每个钩子决策都通过 `HookExecutionEvent` 回调打印到控制台，因此您可以在演示运行时观看允许/拒绝结果。

<a id="running"></a>

## 跑步

```bash
export LLM_API_KEY="your-key"
export LLM_MODEL="anthropic/claude-sonnet-4-5-20250929"  # 可选的
export LLM_BASE_URL="https://your-endpoint"              # 可选的

python main.py
```

<a id="how-an-agent-hook-is-configured"></a>

## 如何配置智能体挂钩

```python
HookDefinition(
    type=HookType.AGENT,
    name="security-reviewer",      # 成本指标桶（智能体-hook:<name>）
    system_prompt="...",           # 指示钩子智能体； 必须请求 JSON
    tools=["file_editor"],         # 钩子智能体可能使用的可选工具
                                   # （使用注册名称，e.g。 “file_editor”、“terminal”——不是像“FileEditorTool”这样的类名）
                                   #
    timeout=60,                    # 转发到每个钩子 LLM 副本
    max_iterations=3,              # 子对话步骤
)
```

钩子智能体接收事件 JSON 并且必须回复：

```json
{"decision": "allow" | "deny", "reason": "<short explanation>"}
```

其他任何内容（非 JSON、缺少字段、子对话错误）默认为
`allow` 因此破损的钩子无法楔入主钩智能体。
