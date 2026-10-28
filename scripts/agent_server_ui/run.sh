#!/bin/bash

# 使用其配置运行网络聊天应用程序示例的脚本
set -euo pipefail

# 将CWD设置为当前目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# 在生成进程之前更改到脚本的目录
cd "$SCRIPT_DIR"

export OH_STATIC_FILES_PATH="static"
python -m openhands.agent_server 
