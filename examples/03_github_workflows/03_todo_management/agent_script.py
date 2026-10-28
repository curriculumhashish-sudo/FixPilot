#!/usr/bin/env python3
"""
TODO 智能体用于 OpenHands 自动化 TODO 管理

该脚本使用 OpenHands 智能体处理各个 TODO(OpenHands) 注释以实现 TODO。 设计用于 GitHub
 Actions 工作流程。

用途：
    python agent_script.py <todo_json>

Arguments:
    todo_json: JSON 字符串，包含来自 scanner.py 的 TODO 信息

环境变量：
    LLM_API_KEY: API 键用于 LLM（必需）
    LLM_MODEL: 要使用的语言模型（默认值：gpt-5.5）
    LLM_BASE_URL: 可选底座 URL 用于 LLM API
    GITHUB_TOKEN: GitHub token 用于创建 PR（必填）
    GITHUB_REPOSITORY: 格式为所有者/存储库的存储库（必需）

有关设置说明和使用示例，请参阅此目录中的 README.md。
"""

import argparse
import json
import os
import sys

from prompt import PROMPT

from openhands.sdk import LLM, Conversation, get_logger
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)


def process_todo(todo_data: dict):
    """使用 OpenHands 智能体处理单个 TODO 项目。"""
    file_path = todo_data["file"]
    line_num = todo_data["line"]
    description = todo_data["description"]

    logger.info(f"Processing TODO in {file_path}:{line_num}")

    # 配置LLM
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        logger.error("LLM_API_KEY environment variable is not set.")
        sys.exit(1)

    model = os.getenv("LLM_MODEL", "gpt-5.5")
    base_url = os.getenv("LLM_BASE_URL")

    llm_config = {
        "model": model,
        "api_key": api_key,
        "usage_id": "agent_script",
        "drop_params": True,
    }

    if base_url:
        llm_config["base_url"] = base_url

    llm = LLM(**llm_config)

    # 创建提示词
    prompt = PROMPT.format(
        file_path=file_path,
        line_num=line_num,
        description=description,
    )

    # 获取当前工作目录为工作区
    cwd = os.getcwd()

    # 使用默认工具创建智能体
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,
    )

    # 创建对话
    conversation = Conversation(
        agent=agent,
        workspace=cwd,
    )

    logger.info("Starting task execution...")
    logger.info(f"Prompt: {prompt[:200]}...")

    # 发送提示词并运行智能体
    conversation.send_message(prompt)
    conversation.run()

    logger.info("Task completed successfully")


def main():
    """主要功能是处理 TODO 项。"""
    parser = argparse.ArgumentParser(
        description="Process a TODO(openhands) comment using OpenHands agent"
    )
    parser.add_argument("todo_json", help="JSON string containing TODO information")

    args = parser.parse_args()

    try:
        todo_data = json.loads(args.todo_json)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        sys.exit(1)

    # 验证必填字段
    required_fields = ["file", "line", "description"]
    for field in required_fields:
        if field not in todo_data:
            logger.error(f"Missing required field in TODO data: {field}")
            sys.exit(1)

    # 处理TODO
    process_todo(todo_data)


if __name__ == "__main__":
    main()
