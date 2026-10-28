"""
回归测试聊天模板的实现。

该文件包含示例跟踪及其预期的格式化输出。 这些用于确保聊天模板实现保持稳定并在各个版本
中产生相同的结果。

基本事实是使用带有 Qwen/Qwen3-4B-Instruct-2507 分词器的变压器 AutoTokenizer 生成的。
运行这些测试不需要 transformer
s 库；只有使用 --generate-ground-truth 标志重新生成基准真值时，才需要它。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from openhands.sdk.critic.impl.api.chat_template import ChatTemplateRenderer


# =============================================================================
# 测试用例与真实值每个测试用例包含：
#   - messages：输入的消息
#   - 工具：可选工具定义
#   - add_generation_prompt：是否添加代提示词
#   - 预期：确切的预期输出字符串
# =============================================================================

TEST_CASES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # 测试 1：简单的单轮对话
    # ------------------------------------------------------------------
    {
        "name": "simple_single_turn",
        "messages": [
            {"role": "user", "content": "Hello!"},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": "<|im_start|>user\nHello!<|im_end|>\n",
    },
    # ------------------------------------------------------------------
    # 测试2：用户+助手轮流
    # ------------------------------------------------------------------
    {
        "name": "user_assistant_turn",
        "messages": [
            {"role": "user", "content": "What is Python?"},
            {
                "role": "assistant",
                "content": "Python is a high-level programming language.",
            },
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>user\nWhat is Python?<|im_end|>\n"
            "<|im_start|>assistant\n"
            "Python is a high-level programming language.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试3：使用系统消息
    # ------------------------------------------------------------------
    {
        "name": "with_system_message",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Write a hello world in Python."},
            {"role": "assistant", "content": 'print("Hello, World!")'},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\nYou are a helpful coding assistant.<|im_end|>\n"
            "<|im_start|>user\nWrite a hello world in Python.<|im_end|>\n"
            '<|im_start|>assistant\nprint("Hello, World!")<|im_end|>\n'
        ),
    },
    # ------------------------------------------------------------------
    # 测试 4：多轮对话
    # ------------------------------------------------------------------
    {
        "name": "multi_turn_conversation",
        "messages": [
            {"role": "system", "content": "You are a math tutor."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 equals 4."},
            {"role": "user", "content": "And 3+3?"},
            {"role": "assistant", "content": "3+3 equals 6."},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\nYou are a math tutor.<|im_end|>\n"
            "<|im_start|>user\nWhat is 2+2?<|im_end|>\n"
            "<|im_start|>assistant\n2+2 equals 4.<|im_end|>\n"
            "<|im_start|>user\nAnd 3+3?<|im_end|>\n"
            "<|im_start|>assistant\n3+3 equals 6.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 5：使用生成提示词
    # ------------------------------------------------------------------
    {
        "name": "with_generation_prompt",
        "messages": [
            {"role": "user", "content": "Tell me a joke."},
        ],
        "tools": None,
        "add_generation_prompt": True,
        "expected": (
            "<|im_start|>user\nTell me a joke.<|im_end|>\n<|im_start|>assistant\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 6：使用单一工具
    # ------------------------------------------------------------------
    {
        "name": "with_single_tool",
        "messages": [
            {"role": "user", "content": "What's the weather?"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\n# Tools\n\n"
            "You may call one or more functions to assist with the user query.\n\n"
            "You are provided with function signatures within "
            "<tools></tools> XML tags:\n<tools>\n"
            '{"type": "function", "function": {"name": "get_weather", '
            '"description": "Get weather info", "parameters": {"type": "object", '
            '"properties": {"city": {"type": "string"}}, "required": ["city"]}}}\n'
            "</tools>\n\n"
            "For each function call, return a json object with function name "
            "and arguments within <tool_call></tool_call> XML tags:\n"
            "<tool_call>\n"
            '{"name": <function-name>, "arguments": <args-json-object>}\n'
            "</tool_call><|im_end|>\n"
            "<|im_start|>user\nWhat's the weather?<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试7：使用工具和系统消息
    # ------------------------------------------------------------------
    {
        "name": "tools_with_system_message",
        "messages": [
            {"role": "system", "content": "You are a weather assistant."},
            {"role": "user", "content": "Check weather in Tokyo."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ],
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\nYou are a weather assistant.\n\n# Tools\n\n"
            "You may call one or more functions to assist with the user query.\n\n"
            "You are provided with function signatures within "
            "<tools></tools> XML tags:\n<tools>\n"
            '{"type": "function", "function": {"name": "get_weather", '
            '"description": "Get weather", "parameters": {"type": "object", '
            '"properties": {"city": {"type": "string"}}}}}\n'
            "</tools>\n\n"
            "For each function call, return a json object with function name "
            "and arguments within <tool_call></tool_call> XML tags:\n"
            "<tool_call>\n"
            '{"name": <function-name>, "arguments": <args-json-object>}\n'
            "</tool_call><|im_end|>\n"
            "<|im_start|>user\nCheck weather in Tokyo.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试8：带有特殊字符的代码内容
    # ------------------------------------------------------------------
    {
        "name": "code_with_special_chars",
        "messages": [
            {
                "role": "user",
                "content": "```python\ndef foo():\n    return {'key': 'value'}\n```",
            },
            {"role": "assistant", "content": "This function returns a dictionary."},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>user\n```python\ndef foo():\n    return {'key': 'value'}\n"
            "```<|im_end|>\n<|im_start|>assistant\n"
            "This function returns a dictionary.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 9：Unicode 和表情符号内容
    # ------------------------------------------------------------------
    {
        "name": "unicode_and_emoji",
        "messages": [
            {"role": "user", "content": "Translate: 你好 🌍"},
            {"role": "assistant", "content": "Hello 🌍"},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>user\nTranslate: 你好 🌍<|im_end|>\n"
            "<|im_start|>assistant\nHello 🌍<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试10：长的多段落内容
    # ------------------------------------------------------------------
    {
        "name": "long_multi_paragraph",
        "messages": [
            {
                "role": "system",
                "content": "You are a writing assistant.\n\nBe concise and clear.",
            },
            {"role": "user", "content": "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\nYou are a writing assistant.\n\n"
            "Be concise and clear.<|im_end|>\n"
            "<|im_start|>user\nParagraph 1.\n\nParagraph 2.\n\n"
            "Paragraph 3.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 11：多种工具
    # ------------------------------------------------------------------
    {
        "name": "multiple_tools",
        "messages": [
            {"role": "user", "content": "Help me search and save."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save",
                    "description": "Save",
                    "parameters": {
                        "type": "object",
                        "properties": {"data": {"type": "string"}},
                    },
                },
            },
        ],
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\n# Tools\n\n"
            "You may call one or more functions to assist with the user query.\n\n"
            "You are provided with function signatures within "
            "<tools></tools> XML tags:\n<tools>\n"
            '{"type": "function", "function": {"name": "search", '
            '"description": "Search", "parameters": {"type": "object", '
            '"properties": {"q": {"type": "string"}}}}}\n'
            '{"type": "function", "function": {"name": "save", '
            '"description": "Save", "parameters": {"type": "object", '
            '"properties": {"data": {"type": "string"}}}}}\n'
            "</tools>\n\n"
            "For each function call, return a json object with function name "
            "and arguments within <tool_call></tool_call> XML tags:\n"
            "<tool_call>\n"
            '{"name": <function-name>, "arguments": <args-json-object>}\n'
            "</tool_call><|im_end|>\n"
            "<|im_start|>user\nHelp me search and save.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 12：空内容
    # ------------------------------------------------------------------
    {
        "name": "empty_content",
        "messages": [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "Your message is empty."},
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>user\n<|im_end|>\n"
            "<|im_start|>assistant\nYour message is empty.<|im_end|>\n"
        ),
    },
    # ------------------------------------------------------------------
    # 测试 13：现实智能体跟踪（关键用例）
    # ------------------------------------------------------------------
    {
        "name": "realistic_agent_trace",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a coding assistant helping with "
                    "software development tasks."
                ),
            },
            {"role": "user", "content": "Create a function to calculate factorial."},
            {
                "role": "assistant",
                "content": (
                    "I'll create a factorial function for you.\n\n```python\n"
                    "def factorial(n):\n    if n <= 1:\n        return 1\n"
                    "    return n * factorial(n - 1)\n```\n\n"
                    "This is a recursive implementation."
                ),
            },
            {"role": "user", "content": "Can you add input validation?"},
            {
                "role": "assistant",
                "content": (
                    "Here's the updated function with validation:\n\n```python\n"
                    "def factorial(n):\n"
                    "    if not isinstance(n, int):\n"
                    '        raise TypeError("Input must be an integer")\n'
                    "    if n < 0:\n"
                    '        raise ValueError("Input must be non-negative")\n'
                    "    if n <= 1:\n        return 1\n"
                    "    return n * factorial(n - 1)\n```"
                ),
            },
        ],
        "tools": None,
        "add_generation_prompt": False,
        "expected": (
            "<|im_start|>system\n"
            "You are a coding assistant helping with software development tasks."
            "<|im_end|>\n"
            "<|im_start|>user\nCreate a function to calculate factorial.<|im_end|>\n"
            "<|im_start|>assistant\n"
            "I'll create a factorial function for you.\n\n```python\n"
            "def factorial(n):\n    if n <= 1:\n        return 1\n"
            "    return n * factorial(n - 1)\n```\n\n"
            "This is a recursive implementation.<|im_end|>\n"
            "<|im_start|>user\nCan you add input validation?<|im_end|>\n"
            "<|im_start|>assistant\n"
            "Here's the updated function with validation:\n\n```python\n"
            "def factorial(n):\n"
            "    if not isinstance(n, int):\n"
            '        raise TypeError("Input must be an integer")\n'
            "    if n < 0:\n"
            '        raise ValueError("Input must be non-negative")\n'
            "    if n <= 1:\n        return 1\n"
            "    return n * factorial(n - 1)\n```<|im_end|>\n"
        ),
    },
]


@pytest.fixture
def renderer(qwen3_tokenizer_config_path):
    """创建一个 ChatTemplateRenderer 进行测试。"""
    with qwen3_tokenizer_config_path.open(encoding="utf-8") as handle:
        tokenizer_config = json.load(handle)
    return ChatTemplateRenderer(chat_template=tokenizer_config["chat_template"])


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["name"] for tc in TEST_CASES])
def test_chat_template_regression(
    renderer: ChatTemplateRenderer, test_case: dict[str, Any]
):
    """
    回归测试聊天模板渲染。

    将我们实现的输出与变压器 AutoTokenizer 生成的地面实况进行比较。
    """
    messages = test_case["messages"]
    tools = test_case.get("tools")
    add_generation_prompt = test_case.get("add_generation_prompt", False)
    expected = test_case["expected"]

    actual = renderer.apply_chat_template(
        messages=messages,
        tools=tools,
        add_generation_prompt=add_generation_prompt,
    )

    assert actual == expected, (
        f"\nExpected ({len(expected)} chars):\n"
        f"  {repr(expected[:200])}{'...' if len(expected) > 200 else ''}\n"
        f"Actual ({len(actual)} chars):\n"
        f"  {repr(actual[:200])}{'...' if len(actual) > 200 else ''}"
    )


def generate_ground_truth(tokenizer_name: str = "Qwen/Qwen3-4B-Instruct-2507") -> None:
    """
    使用 Transformer 库生成地面实况。

    该函数用于在需要时更新 TEST_CASES 中的预期值（e.g.，当添加新的测试用例时）。

    需要安装变压器：pip install Transformers
    """
    try:
        from transformers import AutoTokenizer  # type: ignore
        # 默认情况下，此依赖项不包含在 pyproject.toml 中，以避免让不需要它的用户安装变得
        # 臃肿。
        #
    except ImportError as e:
        raise ImportError(
            "transformers is required to generate ground truth. "
            "Install it with: pip install transformers"
        ) from e

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)

    print("# Generated ground truth values:")
    print("# Copy these into TEST_CASES if updating expected values")
    print()

    for test_case in TEST_CASES:
        name = test_case["name"]
        messages = test_case["messages"]
        tools = test_case.get("tools")
        add_generation_prompt = test_case.get("add_generation_prompt", False)

        if tools:
            output = tokenizer.apply_chat_template(
                messages,
                tools=tools,
                tokenize=False,
                add_generation_prompt=add_generation_prompt,
            )
        else:
            output = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=add_generation_prompt
            )

        print(f"# Test: {name}")
        print(f'"expected": {repr(output)},')
        print()


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description=(
            "Chat template tests - use pytest to run tests, or "
            "--generate-ground-truth to regenerate expected values"
        )
    )
    parser.add_argument(
        "--generate-ground-truth",
        action="store_true",
        help=(
            "Generate ground truth values using transformers library "
            "(requires transformers)"
        ),
    )
    parser.add_argument(
        "--tokenizer",
        default="Qwen/Qwen3-4B-Instruct-2507",
        help="Tokenizer name to use",
    )

    args = parser.parse_args()

    if args.generate_ground_truth:
        generate_ground_truth(args.tokenizer)
    else:
        print(
            "Use pytest to run tests: "
            "pytest tests/sdk/critic/api/test_template_render.py"
        )
        print("Or use --generate-ground-truth to regenerate expected values")
        sys.exit(1)
