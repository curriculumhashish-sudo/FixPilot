#!/bin/bash
# 停止挂钩：在允许智能体完成之前需要 summary.txt 文件 SUMMARY_FILE 应由调用脚本设置
#

SUMMARY_FILE="${SUMMARY_FILE:-./summary.txt}"

if [ ! -f "$SUMMARY_FILE" ]; then
    echo '{"decision": "deny", "additionalContext": "Create summary.txt first."}'
    exit 2
fi
exit 0
