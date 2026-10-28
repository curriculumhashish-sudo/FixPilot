#!/bin/bash

if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv is already installed."
    uv self update  # 始终更新到最新版本
fi

make build
