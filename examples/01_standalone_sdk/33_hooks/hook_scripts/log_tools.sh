#!/bin/bash
# PostToolUse 挂钩：记录所有工具使用情况使用 OPENHANDS_TOOL_NAME env var（不需要 jq/python！）
#

# LOG_FILE 应由调用脚本设置
LOG_FILE="${LOG_FILE:-/tmp/tool_usage.log}"

echo "[$(date)] Tool used: $OPENHANDS_TOOL_NAME" >> "$LOG_FILE"
exit 0
