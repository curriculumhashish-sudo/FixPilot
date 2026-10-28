<a id="hooks-examples"></a>

# 钩子示例

该文件夹演示了 OpenHands 挂钩系统。

<a id="example"></a>

## 示例

- **main.py** - 显示所有四种钩子类型的完整钩子演示

<a id="scripts"></a>

## 脚本

`hook_scripts/` 目录包含可重用的钩子脚本示例：

- `block_dangerous.sh` - 阻止 rm -rf 命令 (PreToolUse)
- `log_tools.sh` - 将工具使用情况记录到文件中 (PostToolUse)
- `inject_git_context.sh` - 将 git status 注入提示词 (UserPromptSubmit)
- `require_summary.sh` - 停止前需要 summary.txt（停止）

<a id="running"></a>

## 跑步

```bash
# 设置您的 LLM 凭据
export LLM_API_KEY="your-key"
export LLM_MODEL="gpt-5.5"  # 可选的
export LLM_BASE_URL="https://your-endpoint"  # 可选的

# 运行示例
python main.py
```

<a id="hook-types"></a>

## 挂钩类型

| 钩子 | 当它运行时 | 可以拦截吗？ |
|------|--------------|------------|
| PreToolUse | 工具执行之前 | 有（2号出口） |
| PostToolUse | 工具执行后 | 否 |
| UserPromptSubmit | 处理用户消息之前 | 有（2号出口） |
| 停止 | 当智能体尝试完成 | 有（2号出口） |
| SessionStart | 当谈话开始时 | 否 |
| SessionEnd | 当谈话结束时 | 否 |

<a id="exit-codes"></a>

## 退出代码

挂钩脚本通过退出代码发出结果信号（与 Claude Code 挂钩合约匹配）：

- **`0` — 成功。**操作继续进行。 对于结构化输出（`decision`、`reason`、`additionalContext`），`stdout` 被解析为 JSON。
- **`2` — 块。**操作被拒绝。 对于 `Stop` 挂钩，这会阻止智能体完成并且智能体继续运行。 `stderr` /
  `reason` 作为反馈出现。
- **任何其他非零退出代码 — 非阻塞错误。**错误已记录，但操作仍继续进行。

> **注意：** 仅退出代码 `2` 块。 退出代码 `1`（常规 Unix
> 故障代码）被视为非阻塞错误。 一个钩子，旨在
> 执行策略必须以 `2` 退出。
