#!/bin/bash
# PreToolUse 挂钩：阻止危险的 rm -rf 命令在原始 JSON 输入上使用 grep（不需要 jq）
#

input=$(cat)

# 通过检查输入是否包含模式来阻止 rm -rf 命令
if echo "$input" | grep -q "rm -rf"; then
    echo '{"decision": "deny", "reason": "rm -rf commands are blocked for safety"}'
    exit 2  # 退出代码 2 = 阻止操作
fi

exit 0  # 退出代码 0 = 允许操作
