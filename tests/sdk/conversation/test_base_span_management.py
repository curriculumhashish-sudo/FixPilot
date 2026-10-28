"""测试 BaseConversation 是否正确管理跨度状态以防止双端警告。"""  # noqa: E501

import logging
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.types import TraceMetadataValue
from openhands.sdk.llm.llm import LLM
from openhands.sdk.tool.schema import Action, Observation


class MockConversation(BaseConversation):
    """用于测试跨度管理的 BaseConversation 的测试实现。"""

    def __init__(self):
        super().__init__()

    # 用最少的存根实现抽象方法
    def close(self) -> None:
        pass

    @property
    def conversation_stats(self) -> ConversationStats:
        return ConversationStats()

    def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        return "Test"

    @property
    def id(self) -> UUID:
        return UUID("12345678-1234-5678-9abc-123456789abc")

    def pause(self) -> None:
        pass

    def reject_pending_actions(self, reason: str = "User rejected the action") -> None:
        pass

    def run(self) -> None:
        pass

    def send_message(self, message: Any, sender: str | None = None) -> None:
        pass

    def set_confirmation_policy(self, policy: Any) -> None:
        pass

    def set_security_analyzer(self, analyzer: Any) -> None:
        pass

    @property
    def state(self) -> Any:
        return MagicMock()

    def update_secrets(self, secrets: Any) -> None:
        pass

    def ask_agent(self, question: str) -> str:
        return "Mock response"

    def condense(self) -> None:
        """模拟对象压缩方法的实现。"""
        pass

    def execute_tool(self, tool_name: str, action: Action) -> Observation:
        """模拟对象 execute_tool 方法的实现。"""
        raise NotImplementedError("Mock execute_tool not implemented")

    def fork(self, **kwargs: Any) -> "MockConversation":
        """模拟对象fork方法的实现。"""
        raise NotImplementedError("Mock fork not implemented")

    def navigate_to(self, event_id: Any) -> None:
        """模拟对象 navigate_to 方法的实现。"""
        raise NotImplementedError("Mock navigate_to not implemented")


def test_base_conversation_load_plugin_default_not_supported():
    conversation = MockConversation()

    with pytest.raises(NotImplementedError, match="does not support loading plugins"):
        conversation.load_plugin("plugin@marketplace")


def test_base_conversation_span_management():
    """测试 BaseConversation 是否正确管理跨度状态以防止双端。"""  # noqa: E501

    # 创建一个最小的 BaseConversation 实例用于测试
    conversation = MockConversation()

    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability"
        ) as mock_should_enable,
        patch("openhands.sdk.conversation.base.start_root_span") as mock_start_span,
        patch("openhands.sdk.conversation.base.end_root_span") as mock_end_span,
    ):
        # 测试何时启用可观察性
        mock_should_enable.return_value = True
        fake_root = MagicMock(name="root-span")
        mock_start_span.return_value = fake_root

        # 起始跨度
        conversation._start_observability_span("test-session-id")
        mock_start_span.assert_called_once_with(
            "conversation",
            session_id="test-session-id",
            user_id=None,
            metadata={},
            tags=None,
            attributes={},
            parent_span_context=None,
        )
        assert conversation._span_ended is False
        assert conversation._observability_root_span is fake_root

        # 再次调用 start 是幂等的（已经开始的对话不得产生第二个根跨度）。
        #
        conversation._start_observability_span("test-session-id")
        assert mock_start_span.call_count == 1

        # 第一次结束跨度
        conversation._end_observability_span()
        mock_end_span.assert_called_once_with(fake_root)
        assert conversation._span_ended is True
        assert conversation._observability_root_span is None

        # 再次尝试结束跨度 - 不应再次调用 end_root_span
        conversation._end_observability_span()
        assert mock_end_span.call_count == 1  # 还是只打过一次电话
        assert conversation._span_ended is True


def test_base_conversation_passes_observability_metadata_and_tag_attributes():
    """对话元数据、跨度标签和对话标签到达根跨度。"""
    conversation = MockConversation()

    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability",
            return_value=True,
        ),
        patch("openhands.sdk.conversation.base.start_root_span") as mock_start_span,
    ):
        metadata: dict[str, TraceMetadataValue] = {
            "repo_name": "OpenHands/software-agent-sdk"
        }
        span_tags = ["repo:OpenHands/software-agent-sdk"]
        conversation_tags = {"automationid": "auto-1", "automationrunid": "run-1"}

        conversation._start_observability_span(
            "test-session-id",
            user_id="user-42",
            metadata=metadata,
            tags=span_tags,
            conversation_tags=conversation_tags,
        )

        mock_start_span.assert_called_once_with(
            "conversation",
            session_id="test-session-id",
            user_id="user-42",
            metadata=metadata,
            tags=span_tags,
            attributes={
                "repo_name": "OpenHands/software-agent-sdk",
                "conversation.tags.automationid": "auto-1",
                "conversation.tags.automationrunid": "run-1",
            },
            parent_span_context=None,
        )


def test_base_conversation_uses_custom_observability_span_name_as_child_span():
    """自定义 Span 名称作为对话根下的子 Span 发出。"""
    conversation = MockConversation()

    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability",
            return_value=True,
        ),
        patch("openhands.sdk.conversation.base.start_root_span") as mock_start_span,
        patch("openhands.sdk.conversation.base.start_child_span") as mock_child_span,
    ):
        conversation._start_observability_span(
            "test-session-id",
            span_name="pr_review_evaluation",
        )

        mock_start_span.assert_called_once_with(
            "conversation",
            session_id="test-session-id",
            user_id=None,
            metadata={},
            tags=None,
            attributes={},
            parent_span_context=None,
        )
        mock_child_span.assert_called_once_with(
            mock_start_span.return_value,
            "pr_review_evaluation",
            tags=None,
        )


def test_base_conversation_span_management_disabled():
    """测试当可观察性被禁用时 BaseConversation 不执行跨度操作。"""  # noqa: E501

    # 创建一个最小的 BaseConversation 实例用于测试
    conversation = MockConversation()

    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability"
        ) as mock_should_enable,
        patch("openhands.sdk.conversation.base.start_root_span") as mock_start_span,
        patch("openhands.sdk.conversation.base.end_root_span") as mock_end_span,
    ):
        # 测试何时禁用可观察性
        mock_should_enable.return_value = False

        # 尝试启动跨度 - 不应调用 start_root_span
        conversation._start_observability_span("test-session-id")
        mock_start_span.assert_not_called()
        assert conversation._span_ended is False
        assert conversation._observability_root_span is None

        # 在没有启动根跨度的情况下结束是无操作并标记结束。
        conversation._end_observability_span()
        mock_end_span.assert_not_called()
        assert conversation._span_ended is True


def test_base_conversation_no_span_warnings(caplog):
    """测试 BaseConversation 在正常操作期间不会产生跨度警告。"""  # noqa: E501

    # 创建一个最小的 BaseConversation 实例用于测试
    conversation = MockConversation()

    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability",
            return_value=True,
        ),
        patch("openhands.sdk.conversation.base.start_root_span"),
        patch("openhands.sdk.conversation.base.end_root_span"),
    ):
        # 捕获警告级别的日志
        with caplog.at_level(logging.WARNING):
            # 正常开始和结束跨度
            conversation._start_observability_span("test-session-id")
            conversation._end_observability_span()

            # 再次尝试结束（模拟__del__调用close()）
            conversation._end_observability_span()

        # 检查是否未记录跨度警告
        span_warnings = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING
            and "span" in record.getMessage().lower()
        ]
        assert len(span_warnings) == 0, (
            f"Found span warnings: {[r.getMessage() for r in span_warnings]}"
        )
