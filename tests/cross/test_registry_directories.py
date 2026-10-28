"""在工具注册表中测试目录处理。"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event.llm_convertible import SystemPromptEvent
from openhands.sdk.llm import LLM, TextContent
from openhands.sdk.tool.registry import resolve_tool
from openhands.sdk.tool.spec import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


class DummyAgent(AgentBase):
    """Test 智能体用于目录测试。"""

    def __init__(self):
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        super().__init__(llm=llm, tools=[])

    def init_state(
        self, state: ConversationState, on_event: ConversationCallbackType
    ) -> None:
        event = SystemPromptEvent(
            source="agent", system_prompt=TextContent(text="test agent"), tools=[]
        )
        on_event(event)

    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        pass


@pytest.fixture
def test_agent():
    """创建一个测试智能体进行测试。"""
    return DummyAgent()


@pytest.fixture(autouse=True)
def register_tools():
    """注册测试工具。"""
    from openhands.sdk.tool import register_tool

    register_tool("TerminalTool", TerminalTool)
    register_tool("FileEditorTool", FileEditorTool)
    register_tool("TaskTrackerTool", TaskTrackerTool)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="TerminalTool directory resolution requires the Unix terminal backend.",
)
def test_resolve_tool_with_conversation_directories(test_agent):
    """测试 resolve_tool 使用对话中的目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        persistence_dir = os.path.join(temp_dir, "persist")
        os.makedirs(working_dir)
        os.makedirs(persistence_dir)

        conversation = Conversation(
            agent=test_agent,
            persistence_dir=persistence_dir,
            workspace=working_dir,
        )

        # 测试 TerminalTool
        bash_tool = Tool(name="TerminalTool")
        bash_tools = resolve_tool(bash_tool, conv_state=conversation._state)
        assert len(bash_tools) == 1
        work_dir = bash_tools[0].executor.working_dir  # type: ignore[attr-defined]
        assert work_dir == working_dir

        # 测试 FileEditorTool
        editor_tool = Tool(name="FileEditorTool")
        editor_tools = resolve_tool(editor_tool, conv_state=conversation._state)
        assert len(editor_tools) == 1
        # 特定于测试的执行程序访问所需的类型忽略
        cwd = str(editor_tools[0].executor.editor._cwd)  # type: ignore[attr-defined]
        assert cwd == working_dir

        # 测试 TaskTrackerTool
        tracker_tool = Tool(name="TaskTrackerTool")
        tracker_tools = resolve_tool(tracker_tool, conv_state=conversation._state)
        assert len(tracker_tools) == 1
        # 特定于测试的执行程序访问所需的类型忽略
        save_dir = str(tracker_tools[0].executor.save_dir)  # type: ignore[attr-defined]
        # TaskTrackerTool 使用对话的 persistence_dir，其中包括对话 ID
        #
        expected_save_dir = str(Path(persistence_dir) / conversation._state.id.hex)
        assert save_dir == expected_save_dir
