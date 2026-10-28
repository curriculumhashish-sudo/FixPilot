#!/usr/bin/env python3
"""
Example: 任务执行器

该脚本针对任意任务运行 OpenHands 智能体。 它接受提示词作为字符串或来自文件/URL 并执行
任务。 设计用于 GitHub Actions 工作流程。

用途：
    python agent_script.py [prompt_location]

Arguments:
    prompt_location: （可选）本地文件的路径或包含提示词的 URL
                     如果未提供，则必须设置 PROMPT_STRING 环境变量

环境变量：
    PROMPT_STRING: 直接提示词文本（替代 prompt_location）
    LLM_API_KEY: API 键用于 LLM（必需）
    LLM_MODEL: 要使用的语言模型（默认值：gpt-5.5）
    LLM_BASE_URL: 可选底座 URL 用于 LLM API

Note: 提供 prompt_location 参数或 PROMPT_STRING 环境变量，但不能同时提供两者。

有关设置说明、使用示例和 GitHub 操作集成，请参阅此目录中的 README.md。
"""

import argparse
import os
import sys
from urllib.parse import urlparse
from urllib.request import urlopen

from openhands.sdk import LLM, Conversation, get_logger
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)


def is_url(path: str) -> bool:
    """检查给定路径是否为 URL。"""
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def load_prompt(prompt_location: str) -> str:
    """
    从文件加载提示词或 URL。

    Args:
        prompt_location: 本地文件或包含提示词的 URL 的路径

    Returns:
        提示词内容为字符串

    Raises:
        ValueError: 如果提示词无法加载
    """
    try:
        if is_url(prompt_location):
            logger.info(f"Downloading prompt from URL: {prompt_location}")
            with urlopen(prompt_location) as response:
                return response.read().decode("utf-8")
        else:
            logger.info(f"Loading prompt from file: {prompt_location}")
            with open(prompt_location) as f:
                return f.read()
    except Exception as e:
        raise ValueError(f"Failed to load prompt from {prompt_location}: {e}")


def main():
    """使用提供的提示词运行任务。"""
    parser = argparse.ArgumentParser(
        description="Run OpenHands agent for arbitrary tasks"
    )
    parser.add_argument(
        "prompt_location",
        nargs="?",
        help=(
            "Path to a local file or URL containing the prompt "
            "(optional if PROMPT_STRING is set)"
        ),
    )
    args = parser.parse_args()

    # 从位置或字符串获取提示词
    prompt_string = os.getenv("PROMPT_STRING")
    prompt_location = args.prompt_location

    # 验证是否确实提供了一个
    if prompt_string and prompt_location:
        logger.error(
            "Error: Both PROMPT_STRING and prompt_location provided. "
            "Please provide only one."
        )
        sys.exit(1)

    if not prompt_string and not prompt_location:
        logger.error(
            "Error: Neither PROMPT_STRING nor prompt_location provided. "
            "Please provide one."
        )
        sys.exit(1)

    # 加载提示词
    try:
        if prompt_string:
            logger.info("Using prompt from PROMPT_STRING environment variable")
            prompt = prompt_string
        else:
            prompt = load_prompt(prompt_location)
        logger.info(f"Loaded prompt ({len(prompt)} characters)")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

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


if __name__ == "__main__":
    main()
