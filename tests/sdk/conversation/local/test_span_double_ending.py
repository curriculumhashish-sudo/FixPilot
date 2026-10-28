"""测试LocalConversation中的跨度双端问题。"""

import logging
import tempfile
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_no_double_span_ending_warning(caplog):
    """测试 LocalConversation 不会产生双跨度结束警告。"""

    # 创建测试智能体
    agent = create_test_agent()

    # 创建临时工作区
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建对话
        conversation = LocalConversation(
            agent=agent,
            workspace=temp_dir,
            visualizer=None,  # 禁用可视化以简化测试
        )

        # 捕获警告级别的日志
        with caplog.at_level(logging.WARNING):
            # 模拟对象 agent.step 引发异常以触发finally块
            with patch(
                "openhands.sdk.agent.agent.Agent.step",
                side_effect=Exception("Test exception"),
            ):
                # 尝试运行对话（由于模拟的异常而失败）
                with pytest.raises(Exception):
                    conversation.run()

            # 关闭对话（通常由 __del__ 调用）
            conversation.close()

        # 检查是否未记录有关空跨度堆栈的警告
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]
        span_warnings = [
            msg
            for msg in warning_messages
            if "Attempted to end active span, but stack is empty" in msg
        ]

        # 该测试最初应该会失败（表明存在错误）修复后，应该不会出现跨度警告
        #
        assert len(span_warnings) == 0, f"Found span warnings: {span_warnings}"


def test_span_ending_with_successful_run(caplog):
    """测试跨度结束行为并成功运行（无例外）。"""

    # 创建测试智能体
    agent = create_test_agent()

    # 创建临时工作区
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建对话
        conversation = LocalConversation(
            agent=agent, workspace=temp_dir, visualize=False
        )

        # 模拟对象 agent.step 立即完成（无迭代）
        def finish_immediately(*args, **kwargs):
            conversation._state.execution_status = (
                conversation._state.execution_status.__class__.FINISHED
            )

        # 捕获警告级别的日志
        with caplog.at_level(logging.WARNING):
            with patch(
                "openhands.sdk.agent.agent.Agent.step", side_effect=finish_immediately
            ):
                # 成功运行对话
                conversation.run()

            # 关闭对话
            conversation.close()

        # 检查是否未记录有关空跨度堆栈的警告
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]
        span_warnings = [
            msg
            for msg in warning_messages
            if "Attempted to end active span, but stack is empty" in msg
        ]

        assert len(span_warnings) == 0, f"Found span warnings: {span_warnings}"


def test_no_span_operations_when_observability_disabled(caplog):
    """测试禁用可观察性时是否不会发生跨度操作。"""

    # 创建测试智能体
    agent = create_test_agent()

    # 创建临时工作区
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建对话
        conversation = LocalConversation(
            agent=agent, workspace=temp_dir, visualize=False
        )

        # 模拟对象 agent.step 立即完成
        def finish_immediately(*args, **kwargs):
            conversation._state.execution_status = (
                conversation._state.execution_status.__class__.FINISHED
            )

        # 捕获警告级别的日志
        with caplog.at_level(logging.WARNING):
            # 运行并关闭对话
            with patch(
                "openhands.sdk.agent.agent.Agent.step", side_effect=finish_immediately
            ):
                conversation.run()
            conversation.close()

        # 检查是否未记录有关空跨度堆栈的警告
        warning_messages = [
            record.message for record in caplog.records if record.levelname == "WARNING"
        ]
        span_warnings = [
            msg
            for msg in warning_messages
            if "Attempted to end active span, but stack is empty" in msg
        ]

        assert len(span_warnings) == 0, f"Found span warnings: {span_warnings}"
