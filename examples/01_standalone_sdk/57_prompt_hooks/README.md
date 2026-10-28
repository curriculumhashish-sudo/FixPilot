<a id="prompt-based-hooks-example"></a>

# 基于提示词的 Hook 示例

此示例演示了 `type="prompt"`：通过一个 LLM 完成而不是 shell 命令或使用工具子智能体来评估的生命周期挂钩。

该脚本通过 `HookManager` 发送两个合成 `PreToolUse` 事件：

- 策略应允许的测试命令
- 政策应拒绝的破坏性命令

这些命令只是事件数据，永远不会执行。

<a id="when-to-use-a-prompt-hook"></a>

## 何时使用提示词挂钩

提示词钩子适合可以单独从 `HookEvent` 载荷做出的政策决策。 它们比智能体钩子更便宜、更可预测，因为它们完成一次并且无法调用工具。

当评估者在做出决定之前必须检查文件、运行命令或收集其他工作区上下文时，请使用智能体挂钩。 使用命令钩子进行不需要模型判断的确定性检查。

<a id="running"></a>

## 跑步

```bash
export LLM_API_KEY="your-key"
export LLM_MODEL="anthropic/claude-sonnet-4-5-20250929"  # 可选的
export LLM_BASE_URL="https://your-endpoint"              # 可选的

python main.py
```

<a id="configuration"></a>

## 配置

```python
HookDefinition(
    type=HookType.PROMPT,
    name="terminal-safety",
    prompt="Deny terminal commands that recursively delete files ...",
    timeout=30,
)
```

提示词挂钩使用对话的当前 LLM。 复制的 LLM 将超时、指标和稳定 `prompt-hook:<name>` 使用存储桶与主智能体隔离开来。 配置的策略作为可信系统发送上下文； 已序列化钩子事件单独发送并标记为不可信数据。

SDK 自动从模型的功能中选择聊天完成或响应 API。 提示词挂钩是单次且非流式传输的，无论父级 LLM 的流式传输设置如何。

执行器向模型询问此共享钩子结果合约：

```json
{"decision": "allow" | "deny", "reason": "<short explanation>"}
```

缺少 LLM 配置、提供程序故障和无效响应无法打开
with `decision="allow"` and `success=False`, so callers can distinguish an
故意允许判决导致执行失败。
