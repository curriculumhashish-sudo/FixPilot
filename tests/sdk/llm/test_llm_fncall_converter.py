"""测试 FunctionCallingConverter。"""

import json
import textwrap
from typing import cast

import pytest
from litellm import ChatCompletionToolParam

from openhands.sdk.llm.exceptions import (
    FunctionCallConversionError,
    FunctionCallValidationError,
)
from openhands.sdk.llm.mixins.fn_call_converter import (
    STOP_WORDS,
    convert_fncall_messages_to_non_fncall_messages,
    convert_non_fncall_messages_to_fncall_messages,
    convert_tool_call_to_string,
    convert_tools_to_description,
    system_message_suffix_TEMPLATE,
)


FNCALL_TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Execute a bash command in the terminal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish the interaction when the task is complete.",
        },
    },
]


def test_stop_words_defined():
    """测试 STOP_WORDS 是否已正确定义。"""
    assert isinstance(STOP_WORDS, list)
    assert len(STOP_WORDS) > 0
    assert all(isinstance(word, str) for word in STOP_WORDS)


def test_convert_fncall_to_non_fncall_basic():
    """测试从函数调用消息到非函数调用的基本转换
    消息。"""
    fncall_messages = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": "I'll run the ls command for you.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls"}',
                    },
                }
            ],
        },
        {"role": "tool", "content": "file1.txt\nfile2.txt", "tool_call_id": "call_123"},
    ]

    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )

    assert isinstance(non_fncall_messages, list)
    assert len(non_fncall_messages) >= len(fncall_messages)

    # 检查工具调用是否已转换为文本格式
    assistant_msg = None
    for msg in non_fncall_messages:
        if msg.get("role") == "assistant" and "terminal" in str(msg.get("content", "")):
            assistant_msg = msg
            break

    assert assistant_msg is not None
    assert "terminal" in assistant_msg["content"]


def test_convert_non_fncall_to_fncall_basic():
    """测试从非函数调用消息到函数调用的基本转换
    消息。"""
    non_fncall_messages = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": (
                "I'll run the ls command for you.\n\n<function=terminal>\n"
                "<parameter=command>ls</parameter>\n</function>"
            ),
        },
    ]

    fncall_messages = convert_non_fncall_messages_to_fncall_messages(
        non_fncall_messages, FNCALL_TOOLS
    )

    assert isinstance(fncall_messages, list)
    assert len(fncall_messages) >= len(non_fncall_messages)

    # 检查函数调用是否正确转换
    assistant_msg = None
    for msg in fncall_messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_msg = msg
            break

    assert assistant_msg is not None
    assert "tool_calls" in assistant_msg
    assert len(assistant_msg["tool_calls"]) == 1
    assert assistant_msg["tool_calls"][0]["function"]["name"] == "terminal"


def test_convert_fncall_to_non_fncall_with_in_context_learning():
    """使用 in-上下文学习示例测试转换。"""
    fncall_messages = [{"role": "user", "content": "Please run ls command"}]

    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS, add_in_context_learning_example=True
    )

    assert isinstance(non_fncall_messages, list)
    # 智能体-SDK 可以将示例合并到现有消息中，而不是创建新消息
    #
    assert len(non_fncall_messages) >= len(fncall_messages)

    # 检查示例是否已添加到内容中
    has_example = False
    for msg in non_fncall_messages:
        content = str(msg.get("content", "")).lower()
        if "example" in content or "start of example" in content:
            has_example = True
            break

    # 应要求时提供示例
    assert has_example, (
        "In-context learning examples should be added to message content"
    )


def test_convert_fncall_to_non_fncall_without_in_context_learning():
    """无需 in-上下文学习示例即可测试转换。"""
    fncall_messages = [{"role": "user", "content": "Please run ls command"}]

    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS, add_in_context_learning_example=False
    )

    assert isinstance(non_fncall_messages, list)
    # 没有例子，应该是相同的长度或相似的
    assert len(non_fncall_messages) >= len(fncall_messages)


def test_convert_with_multiple_tool_calls():
    """测试一条消息中的多个工具调用是否会引发错误。"""
    fncall_messages = [
        {"role": "user", "content": "Please run ls and then pwd"},
        {
            "role": "assistant",
            "content": "I'll run both commands for you.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls"}',
                    },
                },
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "pwd"}',
                    },
                },
            ],
        },
    ]

    # 智能体-SDK 不支持每条消息多个工具调用
    with pytest.raises(
        FunctionCallConversionError, match="Expected exactly one tool call"
    ):
        convert_fncall_messages_to_non_fncall_messages(fncall_messages, FNCALL_TOOLS)


def test_convert_with_tool_response():
    """测试转换，包括工具响应。"""
    fncall_messages = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": "I'll run the ls command.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "file1.txt\nfile2.txt\nfolder1/",
            "tool_call_id": "call_123",
        },
        {
            "role": "assistant",
            "content": "The directory contains two files and one folder.",
        },
    ]

    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )

    assert isinstance(non_fncall_messages, list)
    assert len(non_fncall_messages) >= 3  # 至少是用户、助理、最终助理

    # 检查工具响应是否已合并
    has_tool_output = False
    for msg in non_fncall_messages:
        content = str(msg.get("content", ""))
        if "file1.txt" in content or "folder1" in content:
            has_tool_output = True
            break

    assert has_tool_output


def test_convert_roundtrip():
    """测试转换是否可逆。"""
    original_fncall = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": "I'll run the ls command.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls"}',
                    },
                }
            ],
        },
    ]

    # 转换为非函数调用格式
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        original_fncall, FNCALL_TOOLS
    )
    # 转换回函数调用格式
    back_to_fncall = convert_non_fncall_messages_to_fncall_messages(
        non_fncall, FNCALL_TOOLS
    )

    assert isinstance(back_to_fncall, list)

    # 检查结果中是否有工具调用
    has_tool_calls = False
    for msg in back_to_fncall:
        if msg.get("tool_calls"):
            has_tool_calls = True
            break

    assert has_tool_calls


def test_convert_with_invalid_function_call():
    """测试无效函数调用格式的处理。"""
    non_fncall_messages = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": (
                "I'll run the ls command.\n\n<function=invalid_function>\n"
                "<parameter=command>ls</parameter>\n</function>"
            ),
        },
    ]

    # 这应该优雅地处理无效的函数调用
    try:
        fncall_messages = convert_non_fncall_messages_to_fncall_messages(
            non_fncall_messages, FNCALL_TOOLS
        )
        # 如果没有异常，检查结果是否合理
        assert isinstance(fncall_messages, list)
    except (
        FunctionCallConversionError,
        FunctionCallValidationError,
        ValueError,
        KeyError,
    ):
        # 对于无效的函数调用，这些异常是可以接受的
        pass


def test_convert_with_malformed_parameters():
    """测试格式错误的函数参数的处理。"""
    non_fncall_messages = [
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": (
                "I'll run the ls command.\n\n<function=terminal>\n"
                "<parameter=invalid_param>ls</parameter>\n</function>"
            ),
        },
    ]

    # 这应该可以优雅地处理格式错误的参数
    try:
        fncall_messages = convert_non_fncall_messages_to_fncall_messages(
            non_fncall_messages, FNCALL_TOOLS
        )
        assert isinstance(fncall_messages, list)
    except (
        FunctionCallConversionError,
        FunctionCallValidationError,
        ValueError,
        KeyError,
    ):
        # 对于格式错误的参数，这些异常是可以接受的
        pass


def test_convert_empty_messages():
    """使用空消息列表测试转换。"""
    empty_messages = []
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        empty_messages, FNCALL_TOOLS
    )
    assert isinstance(non_fncall, list)
    fncall = convert_non_fncall_messages_to_fncall_messages(
        empty_messages, FNCALL_TOOLS
    )
    assert isinstance(fncall, list)


def test_convert_with_no_tools():
    """使用空工具列表测试转换。"""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    non_fncall = convert_fncall_messages_to_non_fncall_messages(messages, [])
    assert isinstance(non_fncall, list)
    assert len(non_fncall) >= len(messages)

    fncall = convert_non_fncall_messages_to_fncall_messages(messages, [])
    assert isinstance(fncall, list)
    assert len(fncall) >= len(messages)


def test_convert_preserves_user_messages():
    """测试用户消息在转换过程中是否被保留。"""
    messages = [
        {"role": "user", "content": "Please help me with this task"},
        {"role": "assistant", "content": "I'll help you with that."},
    ]

    non_fncall = convert_fncall_messages_to_non_fncall_messages(messages, FNCALL_TOOLS)

    # 在结果中查找用户消息
    user_msg = None
    for msg in non_fncall:
        if msg.get("role") == "user":
            user_msg = msg
            break

    assert user_msg is not None
    assert "Please help me with this task" in user_msg["content"]


def test_convert_with_system_message():
    """使用系统消息测试转换。"""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Please run ls command"},
        {
            "role": "assistant",
            "content": "I'll run the ls command.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "terminal",
                        "arguments": '{"command": "ls"}',
                    },
                }
            ],
        },
    ]

    non_fncall = convert_fncall_messages_to_non_fncall_messages(messages, FNCALL_TOOLS)

    # 应保留系统消息
    system_msg = None
    for msg in non_fncall:
        if msg.get("role") == "system":
            system_msg = msg
            break

    assert system_msg is not None
    assert "helpful assistant" in system_msg["content"]


def test_convert_with_finish_tool():
    """使用完成工具调用测试转换。"""
    fncall_messages = [
        {"role": "user", "content": "Please finish the task"},
        {
            "role": "assistant",
            "content": "Task completed.",
            "tool_calls": [
                {
                    "id": "call_finish",
                    "type": "function",
                    "function": {"name": "finish", "arguments": "{}"},
                }
            ],
        },
    ]

    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )

    assert isinstance(non_fncall, list)

    # 检查是否代表完成调用
    has_finish = False
    for msg in non_fncall:
        content = str(msg.get("content", ""))
        if "finish" in content.lower():
            has_finish = True
            break

    assert has_finish


def test_convert_tools_to_description_array_items():
    """确保对象项的数组参数格式清晰。"""
    tools = cast(
        list[ChatCompletionToolParam],
        [
            {
                "type": "function",
                "function": {
                    "name": "task_tracker",
                    "description": "Track task plans for execution.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command to execute. `view` shows the current task list. `plan` creates or updates the task list based on provided requirements and progress. Always `view` the current list before making changes.",  # noqa: E501
                                "enum": ["view", "plan"],
                            },
                            "task_list": {
                                "type": "array",
                                "description": (
                                    "The full task list. Required parameter of `plan` command."  # noqa: E501
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "A brief title for the task.",  # noqa: E501
                                        },
                                        "notes": {
                                            "type": "string",
                                            "description": "Additional details or notes about the task.",  # noqa: E501
                                        },
                                        "status": {
                                            "type": "string",
                                            "description": (
                                                "The current status of the task. One of "  # noqa: E501
                                                "'todo', 'in_progress', or 'done'."
                                            ),
                                            "enum": ["todo", "in_progress", "done"],
                                        },
                                    },
                                    "required": ["title"],
                                },
                            },
                        },
                        "required": [],
                    },
                },
            }
        ],
    )

    description = convert_tools_to_description(tools)

    expected_command_line = (
        "  (1) command (string, optional): The command to execute. `view` shows the current task list. "  # noqa: E501
        "`plan` creates or updates the task list based on provided requirements and progress. "  # noqa: E501
        "Always `view` the current list before making changes.\n"
        "Allowed values: [`view`, `plan`]\n"
    )
    assert expected_command_line in description
    # 顶级参数行应反映汇总数组类型
    assert (
        "  (2) task_list (array[object], optional): The full task list. Required parameter of `plan` command.\n"  # noqa: E501
        in description
    )
    # 嵌套结构应通过通用递归格式化程序显示
    assert "Object properties:" in description
    assert "- title (string, required): A brief title for the task." in description
    assert (
        "- notes (string, optional): Additional details or notes about the task."
        in description
    )
    assert (
        "- status (string, optional): The current status of the task. One of 'todo', 'in_progress', or 'done'."  # noqa: E501
        in description
    )
    # 嵌套的枚举值在字段描述中内联描述； 不需要单独的“允许值”行。
    #


@pytest.mark.parametrize(
    "tool_call, expected",
    [
        # 基本单参数
        (
            {
                "id": "test_id",
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": '{"command": "ls -la"}',
                },
            },
            ("<function=terminal>\n<parameter=command>ls -la</parameter>\n</function>"),
        ),
        # 多个不同类型的参数
        (
            {
                "id": "test_id",
                "type": "function",
                "function": {
                    "name": "file_editor",
                    "arguments": (
                        '{"command": "view", "path": "/test/file.py", '
                        '"view_range": [1, 10]}'
                    ),
                },
            },
            (
                "<function=file_editor>\n<parameter=command>view</parameter>\n"
                "<parameter=path>/test/file.py</parameter>\n"
                "<parameter=view_range>[1, 10]</parameter>\n</function>"
            ),
        ),
        # 缩进代码块（空格保留）
        (
            {
                "id": "test_id",
                "type": "function",
                "function": {
                    "name": "file_editor",
                    "arguments": json.dumps(
                        {
                            "command": "str_replace",
                            "path": "/test/file.py",
                            "old_str": "def example():\n    pass",
                            "new_str": (
                                "def example():\n    # This is indented\n"
                                '    print("hello")\n    return True'
                            ),
                        }
                    ),
                },
            },
            (
                "<function=file_editor>\n<parameter=command>str_replace</parameter>\n"
                "<parameter=path>/test/file.py</parameter>\n<parameter=old_str>\n"
                "def example():\n    pass\n</parameter>\n<parameter=new_str>\n"
                'def example():\n    # This is indented\n    print("hello")\n'
                "    return True\n</parameter>\n</function>"
            ),
        ),
        # 列出参数值
        (
            {
                "id": "test_id",
                "type": "function",
                "function": {
                    "name": "test_function",
                    "arguments": (
                        '{"command": "test", "path": "/test/file.py", '
                        '"tags": ["tag1", "tag2", "tag with spaces"]}'
                    ),
                },
            },
            (
                "<function=test_function>\n<parameter=command>test</parameter>\n"
                "<parameter=path>/test/file.py</parameter>\n"
                '<parameter=tags>["tag1", "tag2", "tag with spaces"]</parameter>\n'
                "</function>"
            ),
        ),
        # 字典参数值
        (
            {
                "id": "test_id",
                "type": "function",
                "function": {
                    "name": "test_function",
                    "arguments": json.dumps(
                        {
                            "command": "test",
                            "path": "/test/file.py",
                            "metadata": {
                                "key1": "value1",
                                "key2": 42,
                                "nested": {"subkey": "subvalue"},
                            },
                        }
                    ),
                },
            },
            (
                "<function=test_function>\n<parameter=command>test</parameter>\n"
                "<parameter=path>/test/file.py</parameter>\n"
                '<parameter=metadata>{"key1": "value1", "key2": 42, '
                '"nested": {"subkey": "subvalue"}}</parameter>\n</function>'
            ),
        ),
    ],
)
def test_convert_tool_call_to_string_parameterized(tool_call, expected):
    """使用各种参数类型和格式测试工具调用到字符串的转换。"""
    converted = convert_tool_call_to_string(tool_call)
    assert converted == expected


def test_convert_fncall_messages_with_cache_control():
    """测试工具消息中的 cache_control 是否得到正确处理。"""
    messages = [
        {
            "role": "tool",
            "name": "test_tool",
            "content": [{"type": "text", "text": "test content"}],
            "cache_control": {"type": "ephemeral"},
            "tool_call_id": "call_123",
        }
    ]

    result = convert_fncall_messages_to_non_fncall_messages(messages, FNCALL_TOOLS)

    # 验证结果
    assert len(result) == 1
    assert result[0]["role"] == "user"

    # 检查转换后的消息中是否保留了 cache_control
    assert "cache_control" in result[0]["content"][-1]
    assert result[0]["content"][-1]["cache_control"] == {"type": "ephemeral"}

    # 检查工具结果内容的格式是否正确
    assert (
        result[0]["content"][0]["text"]
        == "EXECUTION RESULT of [test_tool]:\ntest content"
    )


def test_convert_fncall_messages_without_cache_control():
    """测试不带 cache_control 的工具消息是否按预期工作。"""
    messages = [
        {
            "role": "tool",
            "name": "test_tool",
            "content": [{"type": "text", "text": "test content"}],
            "tool_call_id": "call_123",
        }
    ]

    result = convert_fncall_messages_to_non_fncall_messages(messages, FNCALL_TOOLS)

    # 验证结果
    assert len(result) == 1
    assert result[0]["role"] == "user"

    # 检查不存在时不添加cache_control
    assert "cache_control" not in result[0]["content"][-1]

    # 检查工具结果内容的格式是否正确
    assert (
        result[0]["content"][0]["text"]
        == "EXECUTION RESULT of [test_tool]:\ntest content"
    )


def test_convert_fncall_messages_with_image_url():
    """测试 convert_fncall_messages_to_non_fncall_messages 处理图像 URLs
    正确。"""
    messages = [
        {
            "role": "tool",
            "name": "browser",
            "content": [
                {
                    "type": "text",
                    "text": "some browser tool results",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/gif;base64,R0lGODlhAQABAAAAACw="},
                },
            ],
            "tool_call_id": "call_123",
        }
    ]

    converted_messages = convert_fncall_messages_to_non_fncall_messages(
        messages, FNCALL_TOOLS
    )

    assert len(converted_messages) == 1
    assert converted_messages[0]["role"] == "user"
    assert len(converted_messages[0]["content"]) == len(messages[0]["content"])

    # 检查文本内容与工具执行结果的格式是否正确
    text_content = next(
        c for c in converted_messages[0]["content"] if c["type"] == "text"
    )
    assert text_content["text"] == (
        f"EXECUTION RESULT of [{messages[0]['name']}]:\n"
        f"{messages[0]['content'][0]['text']}"
    )

    # 检查图像 URL 是否已保留
    image_content = next(
        c for c in converted_messages[0]["content"] if c["type"] == "image_url"
    )
    assert (
        image_content["image_url"]["url"]
        == "data:image/gif;base64,R0lGODlhAQABAAAAACw="
    )


def test_convert_tools_to_description_nested_array():
    tools: list[ChatCompletionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "nested_array",
                "description": "Handle nested arrays",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "description": "List of entries",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {
                                        "type": "integer",
                                        "description": "The numeric value",
                                    }
                                },
                                "required": ["value"],
                            },
                        }
                    },
                    "required": ["items"],
                },
            },
        }
    ]

    result = convert_tools_to_description(tools)

    expected = textwrap.dedent(
        """\
        ---- BEGIN FUNCTION #1: nested_array ----
        Description: Handle nested arrays
        Parameters:
          (1) items (array[object], required): List of entries
              Array items:
                Type: object
                  Object properties:
                    - value (integer, required): The numeric value
        ---- END FUNCTION #1 ----
        """
    )

    assert result.strip() == expected.strip()


def test_convert_tools_to_description_union_options():
    tools: list[ChatCompletionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "union_tool",
                "description": "Test union parameter",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filters": {
                            "description": "Supported filters",
                            "anyOf": [
                                {"type": "string", "description": "match by name"},
                                {"type": "integer", "description": "match by id"},
                            ],
                        }
                    },
                },
            },
        }
    ]

    result = convert_tools_to_description(tools)

    expected = textwrap.dedent(
        """\
        ---- BEGIN FUNCTION #1: union_tool ----
        Description: Test union parameter
        Parameters:
          (1) filters (string or integer, optional): Supported filters
              anyOf options:
                - string: match by name
                - integer: match by id
        ---- END FUNCTION #1 ----
        """
    )

    assert result.strip() == expected.strip()


def test_convert_tools_to_description_object_details():
    tools: list[ChatCompletionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "object_tool",
                "description": "Test object parameter",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "config": {
                            "type": "object",
                            "description": "Configuration payload",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Friendly name",
                                },
                                "thresholds": {
                                    "type": "array",
                                    "description": "Threshold list",
                                    "items": {"type": "number"},
                                },
                            },
                            "required": ["name"],
                            "additionalProperties": {
                                "type": "string",
                                "description": "Extra properties",
                            },
                        }
                    },
                    "required": ["config"],
                },
            },
        }
    ]

    result = convert_tools_to_description(tools)

    expected = textwrap.dedent(
        """\
        ---- BEGIN FUNCTION #1: object_tool ----
        Description: Test object parameter
        Parameters:
          (1) config (object, required): Configuration payload
              Object properties:
                - name (string, required): Friendly name
                - thresholds (array[number], optional): Threshold list
                  Array items:
                    Type: number
              Additional properties allowed: string
        ---- END FUNCTION #1 ----
        """
    )

    assert result.strip() == expected.strip()


def test_system_message_suffix_template_excludes_security_risk_by_default():
    """测试 system_message_suffix_TEMPLATE 是否不包含 security_risk
    当安全分析器被禁用时。"""
    assert "<parameter=security_risk>" not in system_message_suffix_TEMPLATE
    assert "<parameter=summary>" not in system_message_suffix_TEMPLATE


def test_security_params_included_when_flag_is_true():
    """测试 security_risk 和摘要是否出现在转换后的消息中
    当include_security_params=True（i.e.，安全分析器处于活动状态）时。

    回归测试问题#2740。
    """
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]
    result = convert_fncall_messages_to_non_fncall_messages(
        messages, FNCALL_TOOLS, include_security_params=True
    )
    system_content = result[0]["content"]
    assert "<parameter=security_risk>" in system_content
    assert "<parameter=summary>" in system_content


def test_security_params_excluded_when_flag_is_false():
    """测试 security_risk 和摘要不是否出现在转换后的消息中
    当include_security_params=False（默认）时。"""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ]
    result = convert_fncall_messages_to_non_fncall_messages(
        messages, FNCALL_TOOLS, include_security_params=False
    )
    system_content = result[0]["content"]
    assert "<parameter=security_risk>" not in system_content
    assert "<parameter=summary>" not in system_content


def test_security_risk_param_allowed_for_tool_that_does_not_declare_it():
    """工具模式省略 security_risk（如只读工具，如
    `finish` do, per add_security_risk_prediction in tool.py) 仍然必须接受一个包含它
    的调用，因为上下文 in
    的示例教模型在任何工具下都添加 security_risk。

    回归测试：之前提出的 FunctionCallValidationError（“函数‘finish’不允许使用参数‘
    security_risk’”）。
    """
    finish_tool: list[ChatCompletionToolParam] = [
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Finish the interaction when the task is complete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["message"],
                },
            },
        }
    ]
    non_fncall_messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": (
                "<function=finish>\n"
                "<parameter=message>Hello!</parameter>\n"
                "<parameter=summary>Greet user</parameter>\n"
                "<parameter=security_risk>LOW</parameter>\n"
                "</function>"
            ),
        },
    ]

    fncall_messages = convert_non_fncall_messages_to_fncall_messages(
        non_fncall_messages, finish_tool
    )

    assistant_msg = next(
        msg
        for msg in fncall_messages
        if msg.get("role") == "assistant" and msg.get("tool_calls")
    )
    arguments = json.loads(assistant_msg["tool_calls"][0]["function"]["arguments"])
    assert arguments["message"] == "Hello!"
    assert arguments["security_risk"] == "LOW"
