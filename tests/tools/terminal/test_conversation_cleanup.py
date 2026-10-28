"""
测试对话中工具执行器的正确清理。

此测试套件验证当会话关闭或销毁时工具执行器是否已正确清理。
"""

import tempfile
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Literal
from unittest.mock import Mock

from openhands.sdk import Agent, Conversation
from openhands.sdk.tool import Tool, ToolExecutor, register_tool
from openhands.tools.terminal import TerminalExecutor, TerminalTool


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class _InjectedExecutorTerminalTool(TerminalTool):
    """TerminalTool 变体，在解析时注入测试提供的执行器。

    ``TerminalTool.create`` 需要 ``conv_state``（用于工作目录），因此该子类从
    ``conv_state`` 构建真正的工具，然后
    交换在类属性上捕获的执行器。 每个测试在注册该子类之前设置 ``injected_executor``。
    """

    injected_executor: ClassVar[ToolExecutor | None] = None

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
        terminal_type: Literal["tmux", "subprocess", "powershell"] | None = None,
        shell_path: str | None = None,
        executor: ToolExecutor | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Sequence[TerminalTool]:
        tools = TerminalTool.create(
            conv_state,
            username=username,
            no_change_timeout_seconds=no_change_timeout_seconds,
            terminal_type=terminal_type,
            shell_path=shell_path,
            executor=executor,
            env=env,
        )
        return [
            tool.model_copy(update={"executor": cls.injected_executor})
            for tool in tools
        ]


def test_conversation_close_calls_executor_close(mock_llm):
    """测试 Conversation.close() 在所有工具执行器上调用 close()。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建一个 TerminalExecutor 并使用子进程终端以避免 tmux 问题
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )
        terminal_executor.close = Mock()

        _InjectedExecutorTerminalTool.injected_executor = terminal_executor
        register_tool("test_terminal", _InjectedExecutorTerminalTool)

        # 创建智能体并对话
        agent = Agent(
            llm=mock_llm,
            tools=[Tool(name="test_terminal")],
        )
        conversation = Conversation(
            agent=agent, workspace=temp_dir, delete_on_close=True
        )

        # 触发惰性智能体初始化来创建工具
        conversation._ensure_agent_ready()

        # 关闭对话
        conversation.close()

        # 验证执行器的 close 方法是否被调用
        terminal_executor.close.assert_called_once()


def test_conversation_close_calls_executor_close_without_delete(mock_llm):
    """即使 delete_on_close = False，执行器也会关闭。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )
        terminal_executor.close = Mock()

        _InjectedExecutorTerminalTool.injected_executor = terminal_executor
        register_tool("test_terminal", _InjectedExecutorTerminalTool)

        agent = Agent(
            llm=mock_llm,
            tools=[Tool(name="test_terminal")],
        )
        conversation = Conversation(
            agent=agent, workspace=temp_dir, delete_on_close=False
        )
        conversation._ensure_agent_ready()
        conversation.close()

        terminal_executor.close.assert_called_once()


def test_conversation_del_calls_close(mock_llm):
    """测试 Conversation.__del__() 调用 close()。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建一个 TerminalExecutor 并使用子进程终端以避免 tmux 问题
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )
        terminal_executor.close = Mock()

        _InjectedExecutorTerminalTool.injected_executor = terminal_executor
        register_tool("test_terminal", _InjectedExecutorTerminalTool)

        # 创建智能体并对话
        agent = Agent(
            llm=mock_llm,
            tools=[Tool(name="test_terminal")],
        )
        conversation = Conversation(
            agent=agent, workspace=temp_dir, delete_on_close=True
        )

        # 触发惰性智能体初始化来创建工具
        conversation._ensure_agent_ready()

        # 手动调用__del__模拟垃圾回收
        conversation.__del__()

        # 验证执行器的 close 方法是否被调用
        terminal_executor.close.assert_called_once()


def test_conversation_close_handles_executor_exceptions(mock_llm):
    """测试 Conversation.close() 是否处理来自 executor.close() 的异常。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建模拟对象 LLM 以避免实际的 API 调用

        # 创建一个带有子进程终端的 TerminalExecutor 并创建其 close 方法
        # raise an exception
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )
        terminal_executor.close = Mock(side_effect=Exception("Test exception"))

        _InjectedExecutorTerminalTool.injected_executor = terminal_executor
        register_tool("test_terminal", _InjectedExecutorTerminalTool)

        # 创建智能体并对话
        agent = Agent(
            llm=mock_llm,
            tools=[Tool(name="test_terminal")],
        )
        conversation = Conversation(agent=agent, workspace=temp_dir)

        # 即使 executor.close() 失败，关闭也不应该引发异常我们可以从捕获的 stderr 中看到
        # 警告已正确记录
        #
        conversation.close()  # 这不应该引发异常


def test_conversation_close_skips_none_executors(mock_llm):
    """测试 Conversation.close() 是否跳过具有 None 执行器的工具。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建模拟对象 LLM 以避免实际的 API 调用

        # 创建一个没有执行器的工具
        _InjectedExecutorTerminalTool.injected_executor = None
        register_tool("test_terminal", _InjectedExecutorTerminalTool)

        # 创建智能体并对话
        agent = Agent(
            llm=mock_llm,
            tools=[Tool(name="test_terminal")],
        )
        conversation = Conversation(agent=agent, workspace=temp_dir)

        # 这不应该引发异常
        conversation.close()


def test_terminal_executor_close_calls_session_close():
    """测试 TerminalExecutor.close() 调用 session.close()。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用子进程终端创建 TerminalExecutor
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )

        # 模拟对象会话的关闭方法
        terminal_executor.session.close = Mock()

        # 调用执行器的 close
        terminal_executor.close()

        # 验证是否调用了 session.close()
        terminal_executor.session.close.assert_called_once()


def test_terminal_executor_close_handles_missing_session():
    """测试 TerminalExecutor.close() 是否处理丢失的会话属性。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用子进程终端创建 TerminalExecutor
        terminal_executor = TerminalExecutor(
            working_dir=temp_dir, terminal_type="subprocess"
        )

        # 清除会话以模拟丢失/未初始化状态
        terminal_executor._session = None

        # 这不应该引发异常
        terminal_executor.close()
