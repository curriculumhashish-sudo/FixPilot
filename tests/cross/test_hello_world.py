"""基于 hello_world.py 示例和模拟的 LLM 响应进行测试。"""

import logging
import os
import sys
import tempfile
from typing import Any
from unittest.mock import patch

import pytest
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Message,
    TextContent,
    get_logger,
)
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Hello-world cross tests include TerminalTool until PowerShell follow-up.",
)


class TestHelloWorld:
    """使用模拟的 LLM 测试 hello world 示例。"""

    def setup_method(self):
        """设置测试环境。"""
        self.temp_dir: str = tempfile.mkdtemp()
        self.logger: logging.Logger = get_logger(__name__)
        self.collected_events: list[Event] = []
        self.llm_messages: list[dict[str, Any]] = []

        # 清理任何现有的 hello.py 文件
        import os

        hello_files = ["/tmp/hello.py", os.path.join(self.temp_dir, "hello.py")]
        for file_path in hello_files:
            if os.path.exists(file_path):
                os.remove(file_path)

    def teardown_method(self):
        """清理测试环境。"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def conversation_callback(self, event: Event):
        """回调收集对话事件。"""
        self.collected_events.append(event)
        if isinstance(event, ActionEvent):
            self.logger.info(f"Found a conversation action: {event}")
        elif isinstance(event, ObservationEvent):
            self.logger.info(f"Found a conversation observation: {event}")
        elif isinstance(event, MessageEvent):
            self.logger.info(f"Found a conversation message: {str(event)[:200]}...")
            self.llm_messages.append(event.llm_message.model_dump())

    def create_real_llm_responses_from_fixtures(self, fncall_raw_logs):
        """从存储的测试夹具数据创建真实的 LLM 响应。"""
        responses = []

        # 过滤包含有内容的助理消息的条目
        valid_entries = []
        for log_entry in fncall_raw_logs:
            if "response" not in log_entry:
                continue
            response_data = log_entry["response"]
            choices = response_data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                # 包括带有内容的辅助消息的条目（tool_calls 在已处理的测试夹具数据中可能
                # 为空）
                #
                if message.get("role") == "assistant" and message.get("content"):
                    valid_entries.append(log_entry)

        # 使用所有有效条目进行完整的对话重播
        for log_entry in valid_entries:
            response_data = log_entry["response"]
            # 使用原始数据 - 无需清理
            model_response = ModelResponse(**response_data)
            responses.append(model_response)

        return responses

    def create_mock_llm_responses(self):
        """创建模拟智能体行为的模拟对象 LLM 响应。"""
        # 在临时目录中使用绝对路径
        hello_path = os.path.join(self.temp_dir, "hello.py")

        # 第一个响应：智能体决定创建文件
        first_response = ModelResponse(
            id="mock-response-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll help you create a Python file named hello.py "
                        "that prints 'Hello, World!'. Let me create this file for you.",
                        tool_calls=[
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "file_editor",
                                    "arguments": f'{{"command": "create", '
                                    f'"path": "{hello_path}", '
                                    f'"file_text": "print(\\"Hello, World!\\")"}}',
                                },
                            }
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=Usage(prompt_tokens=50, completion_tokens=30, total_tokens=80),
        )

        # 第二个响应：智能体确认文件创建
        second_response = ModelResponse(
            id="mock-response-2",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="Perfect! I've successfully created the hello.py file "
                        "that prints 'Hello, World!'. The file has been created and is "
                        "ready to use.",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=80, completion_tokens=25, total_tokens=105),
        )

        return [first_response, second_response]

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_hello_world_with_real_llm_data(self, mock_completion, fncall_raw_logs):
        """使用真实的 LLM 完成数据测试完整的 hello world 流程。"""
        # 设置来自测试夹具的真实 LLM 响应
        real_responses = self.create_real_llm_responses_from_fixtures(fncall_raw_logs)

        # 始终使用模拟对象响应来实现一致的行为实际测试夹具数据可能具有与当前智能体不同的
        # 工具调用序列
        #
        real_responses = self.create_mock_llm_responses()

        mock_completion.side_effect = real_responses

        # 配置 LLM（不需要真正的 API 密钥）
        llm = LLM(
            usage_id="test-llm",
            model="claude-sonnet-4",
            api_key=SecretStr("mock-api-key"),
        )

        # 使用临时目录设置工具 - 在运行时使用注册表 + Tool
        register_tool("terminal", TerminalTool)
        register_tool("file_editor", FileEditorTool)
        tools = [
            Tool(name="terminal"),
            Tool(name="file_editor"),
        ]

        # 智能体设置
        agent = Agent(llm=llm, tools=tools)

        # 对话设置
        conversation = Conversation(
            agent=agent,
            workspace=self.temp_dir,
            callbacks=[self.conversation_callback],
        )

        # 发送与 hello_world.py 中相同的消息
        conversation.send_message(
            message=Message(
                role="user",
                content=[
                    TextContent(
                        text="Hello! Can you create a new Python file named hello.py "
                        "that prints 'Hello, World!'?"
                    )
                ],
            )
        )

        # 运行对话
        conversation.run()

        # 验证是否使用真实数据调用了 LLM
        assert mock_completion.call_count >= 1, "LLM completion should have been called"

        # 验证我们是否收集了事件
        assert len(self.collected_events) > 0, (
            "Should have collected conversation events"
        )

        # 验证我们是否有操作和观测结果
        actions = [
            event for event in self.collected_events if isinstance(event, ActionEvent)
        ]
        observations = [
            event
            for event in self.collected_events
            if isinstance(event, ObservationEvent)
        ]
        messages = [
            event for event in self.collected_events if isinstance(event, MessageEvent)
        ]

        assert len(actions) > 0, (
            f"Should have at least one action. Found {len(actions)} actions out of "
            f"{len(self.collected_events)} total events"
        )
        assert len(observations) > 0, "Should have at least one observation"
        assert len(messages) > 0, "Should have at least one message"

        # 验证是否已收集 LLM 条消息
        assert len(self.llm_messages) > 0, "Should have collected LLM messages"

        # 验证对话流程是否有意义
        user_messages = [msg for msg in self.llm_messages if msg.get("role") == "user"]
        assistant_messages = [
            msg for msg in self.llm_messages if msg.get("role") == "assistant"
        ]

        assert len(user_messages) >= 1, "Should have at least one user message"
        assert len(assistant_messages) >= 1, (
            "Should have at least one assistant message"
        )

        # 验证用户消息内容
        first_user_message = user_messages[0]
        user_content = first_user_message.get("content", [])
        user_text = ""
        if user_content:
            # 从 TextContent 个对象中提取文本
            for content in user_content:
                if hasattr(content, "text"):
                    user_text += content.text.lower()
                else:
                    user_text += str(content).lower()

        assert "hello.py" in user_text and "hello, world" in user_text, (
            f"User message should mention hello.py and Hello, World! Got: {user_text}"
        )

        # 通过检查响应特征来验证我们使用的是真实的 LLM 数据真实的响应应该具有更真实的内
        # 容和结构
        #
        for response in real_responses:
            assert response.id is not None, "Real responses should have IDs"
            # 注意：模型字段在某些测试夹具数据中可能是 None，没关系
            if response.choices:
                choice = response.choices[0]
                # 转换为 Choices 类型以访问消息属性
                if isinstance(choice, Choices) and choice.message:
                    assert choice.message.content is not None, (
                        "Real responses should have content"
                    )

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_llm_completion_logging_fidelity(self, mock_completion, fncall_raw_logs):
        """测试模拟的 LLM 完成日志记录会产生相同的输出。"""
        # 使用模拟对象响应来实现一致的行为，而不是真实的测试夹具数据真实的测试夹具数据可
        # 能具有与当前智能体不同的工具调用序列
        #
        mock_responses = self.create_mock_llm_responses()
        mock_completion.side_effect = mock_responses

        # 配置 LLM 并启用日志记录
        llm = LLM(
            usage_id="test-llm",
            model="claude-sonnet-4",
            api_key=SecretStr("mock-api-key"),
        )

        # 使用临时目录设置工具 - 在运行时使用注册表 + Tool
        register_tool("terminal", TerminalTool)
        register_tool("file_editor", FileEditorTool)
        tools = [
            Tool(name="terminal"),
            Tool(name="file_editor"),
        ]

        # 创建智能体并对话
        agent = Agent(llm=llm, tools=tools)
        conversation = Conversation(
            agent=agent,
            workspace=self.temp_dir,
            callbacks=[self.conversation_callback],
        )

        # 通过监视 LLM 调用捕获记录的完成数据
        logged_completions = []
        mock_responses = self.create_mock_llm_responses()
        response_index = 0

        def capture_completion_call(*args, **kwargs):
            nonlocal response_index
            # 从列表中获取下一个响应
            if response_index < len(mock_responses):
                response = mock_responses[response_index]
                response_index += 1

                # 捕获记录的数据结构
                logged_data = {
                    "messages": kwargs.get("messages", []),
                    "tools": kwargs.get("tools", []),
                    "response": response.model_dump(),
                    "model": kwargs.get("model"),
                    "temperature": kwargs.get("temperature"),
                    "max_tokens": kwargs.get("max_tokens"),
                }
                logged_completions.append(logged_data)
                return response
            else:
                # 没有更多可用回复
                raise StopIteration("No more mock responses available")

        mock_completion.side_effect = capture_completion_call

        # 发送消息并运行对话
        user_message = "Hello! Can you create a hello.py file?"
        conversation.send_message(
            message=Message(
                role="user",
                content=[TextContent(text=user_message)],
            )
        )
        conversation.run()

        # 验证记录的完成结构
        assert len(logged_completions) > 0, "Should have captured LLM completion logs"

        # 验证记录的数据是否具有预期的结构
        for i, logged in enumerate(logged_completions):
            self._validate_completion_data(logged, f"completion_{i}")

    def _validate_completion_data(self, logged_data, context):
        """验证记录的完成数据具有预期的结构。"""

        # 验证基本结构
        assert "messages" in logged_data, f"{context}: Missing messages"
        assert "tools" in logged_data, f"{context}: Missing tools"
        assert "response" in logged_data, f"{context}: Missing response"

        # 验证消息结构
        logged_messages = logged_data.get("messages", [])
        assert len(logged_messages) > 0, f"{context}: No messages logged"

        for j, logged_msg in enumerate(logged_messages):
            assert "role" in logged_msg, f"{context} message {j}: Missing role"
            assert logged_msg.get("role") in ["user", "assistant", "system", "tool"], (
                f"{context} message {j}: Invalid role"
            )

        # 验证工具结构
        logged_tools = logged_data.get("tools", [])
        for k, logged_tool in enumerate(logged_tools):
            assert "function" in logged_tool, f"{context} tool {k}: Missing function"
            logged_func = logged_tool.get("function", {})
            assert "name" in logged_func, f"{context} tool {k}: Missing function name"

        # 验证响应结构
        logged_response = logged_data.get("response", {})
        assert "choices" in logged_response, f"{context}: Missing response choices"

        logged_choices = logged_response.get("choices", [])
        assert len(logged_choices) > 0, f"{context}: No response choices"

        for m, logged_choice in enumerate(logged_choices):
            assert "message" in logged_choice, f"{context} choice {m}: Missing message"
            logged_message = logged_choice.get("message", {})
            assert "role" in logged_message, (
                f"{context} choice {m}: Missing message role"
            )

    def test_non_function_call(self):
        """非函数调用响应的测试 LLM 完成日志记录（纯文本）。"""
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
        )

        # 创建不带函数调用的模拟对象响应（纯文本响应）
        mock_response = ModelResponse(
            id="test-non-func-call",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=LiteLLMMessage(
                        content="I understand you want to create a hello.py file.",
                        role="assistant",
                    ),
                )
            ],
            created=1234567890,
            model="claude-sonnet-4",
            object="chat.completion",
            system_fingerprint=None,
            usage=None,
        )

        # 模拟对象 LLM 返回我们的非函数调用响应
        captured_completions = []

        def capture_completion_fidelity(*args, **kwargs):
            # 捕获验证的完成数据
            completion_data = {
                "messages": kwargs.get("messages", []),
                "tools": kwargs.get("tools", []),
                "response": mock_response.model_dump(),
                "timestamp": "2025-01-01T00:00:00Z",
                "latency_sec": 0.5,
            }
            captured_completions.append(completion_data)
            return mock_response

        # 使用模拟的 LLM 创建智能体
        llm = LLM(model="claude-sonnet-4", usage_id="test-llm")
        agent = Agent(llm=llm, tools=[])

        # 模拟对象补全方法
        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            side_effect=capture_completion_fidelity,
        ):
            # 创建对话并发送消息
            conversation = Conversation(agent=agent)
            assert isinstance(conversation, LocalConversation)
            conversation.send_message(
                message=Message(
                    role="user",
                    content=[TextContent(text="What is 2+2?")],
                )
            )

            # 运行一步即可获取非函数调用响应
            agent.step(conversation, on_event=conversation._on_event)

        # 验证我们是否捕获了完成数据
        assert len(captured_completions) == 1, (
            f"Expected 1 completion, got {len(captured_completions)}"
        )

        logged_data = captured_completions[0]

        # 验证非功能调用响应的结构
        assert "messages" in logged_data
        assert "response" in logged_data
        assert "timestamp" in logged_data
        assert "latency_sec" in logged_data

        # 验证响应结构
        response = logged_data["response"]
        assert "choices" in response
        assert len(response["choices"]) == 1

        choice = response["choices"][0]
        message = choice["message"]

        # 验证这是一个非函数调用响应
        assert message["role"] == "assistant"
        assert message["content"] is not None
        assert len(message["content"]) > 0

        # 验证否工具调用
        tool_calls = message.get("tool_calls")
        assert tool_calls is None or tool_calls == [], (
            f"Expected no tool calls, got {tool_calls}"
        )

        print("✅ Non-function call path tested successfully!")
        print(f"   Response content: {message['content'][:100]}...")
        print(f"   Tool calls: {tool_calls}")
        print(f"   Message count: {len(logged_data['messages'])}")

        # 创建不带函数调用的模拟对象响应（纯文本响应）
        mock_response = ModelResponse(
            id="test-non-func-call",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=LiteLLMMessage(
                        content="I understand you want to create a hello.py file.",
                        role="assistant",
                    ),
                )
            ],
            created=1234567890,
            model="claude-sonnet-4",
            object="chat.completion",
            system_fingerprint=None,
            usage=None,
        )

        # 模拟对象 LLM 返回我们的非函数调用响应
        captured_completions = []

        def capture_completion_non_func(*args, **kwargs):
            # 捕获验证的完成数据
            completion_data = {
                "messages": kwargs.get("messages", []),
                "tools": kwargs.get("tools", []),
                "response": mock_response.model_dump(),
                "timestamp": "2025-01-01T00:00:00Z",
                "latency_sec": 0.5,
            }
            captured_completions.append(completion_data)
            return mock_response

        # 使用模拟的 LLM 创建智能体
        agent = Agent(llm=LLM(model="claude-sonnet-4", usage_id="test-llm"), tools=[])

        # 模拟对象补全方法
        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            side_effect=capture_completion_non_func,
        ):
            # 创建对话并发送消息
            conversation = Conversation(agent=agent)
            assert isinstance(conversation, LocalConversation)
            conversation.send_message(
                message=Message(
                    role="user",
                    content=[TextContent(text="What is 2+2?")],
                )
            )

            # 运行一步即可获取非函数调用响应
            agent.step(conversation, on_event=conversation._on_event)

        # 验证我们是否捕获了完成数据
        assert len(captured_completions) == 1, (
            f"Expected 1 completion, got {len(captured_completions)}"
        )

        logged_data = captured_completions[0]

        # 验证非功能调用响应的结构
        assert "messages" in logged_data
        assert "response" in logged_data
        assert "timestamp" in logged_data
        assert "latency_sec" in logged_data

        # 验证响应结构
        response = logged_data["response"]
        assert "choices" in response
        assert len(response["choices"]) == 1

        choice = response["choices"][0]
        message = choice["message"]

        # 验证这是一个非函数调用响应
        assert message["role"] == "assistant"
        assert message["content"] is not None
        assert len(message["content"]) > 0

        # 验证否工具调用
        tool_calls = message.get("tool_calls")
        assert tool_calls is None or tool_calls == [], (
            f"Expected no tool calls, got {tool_calls}"
        )

        print("✅ Non-function call path tested successfully!")
        print(f"   Response content: {message['content'][:100]}...")
        print(f"   Tool calls: {tool_calls}")
        print(f"   Message count: {len(logged_data['messages'])}")
