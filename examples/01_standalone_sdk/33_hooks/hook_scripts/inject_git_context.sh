#!/bin/bash
# UserPromptSubmit hook：当用户询问代码更改时注入 git status

input=$(cat)

# 检查用户是否询问更改、diff 或 git
if echo "$input" | grep -qiE "(changes|diff|git|commit|modified)"; then
    # 如果在 git 存储库中，则获取 git 状态
    if git rev-parse --git-dir > /dev/null 2>&1; then
        status=$(git status --short 2>/dev/null | head -10)
        if [ -n "$status" ]; then
            # 逃离JSON
            escaped=$(echo "$status" | sed 's/"/\\"/g' | tr '\n' ' ')
            echo "{\"additionalContext\": \"Current git status: $escaped\"}"
        fi
    fi
fi
exit 0
