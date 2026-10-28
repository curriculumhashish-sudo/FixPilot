"""测试对话目录处理。"""

import logging
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def mock_agent():
    """创建一个真实的智能体进行测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return agent


def test_conversation_state_working_dir(mock_agent):
    """测试 ConversationState 是否正确处理 working_dir。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        os.makedirs(working_dir)

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=mock_agent,
            workspace=LocalWorkspace(working_dir=working_dir),
        )
        assert state.workspace.working_dir == working_dir
        assert state.workspace.working_dir is not None
        assert Path(state.workspace.working_dir).exists()


def test_conversation_state_persistence_dir(mock_agent):
    """测试 ConversationState 是否正确处理 persistence_dir。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        persistence_dir = os.path.join(temp_dir, "persist")
        os.makedirs(working_dir)

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=mock_agent,
            workspace=LocalWorkspace(working_dir=working_dir),
            persistence_dir=persistence_dir,
        )
        # ConversationState.create() uses persistence_dir directly (no subdirectory)
        assert state.persistence_dir == persistence_dir
        # persistence_dir 应自动创建
        assert state.persistence_dir is not None
        assert Path(state.persistence_dir).exists()


def test_conversation_state_both_directories(mock_agent):
    """测试 ConversationState 是否处理这两个目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        persistence_dir = os.path.join(temp_dir, "persist")
        os.makedirs(working_dir)

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=mock_agent,
            persistence_dir=persistence_dir,
            workspace=LocalWorkspace(working_dir=working_dir),
        )
        assert state.workspace.working_dir == working_dir
        # ConversationState.create() uses persistence_dir directly (no subdirectory)
        assert state.persistence_dir == persistence_dir
        assert state.workspace.working_dir is not None
        assert state.persistence_dir is not None
        assert Path(state.workspace.working_dir).exists()
        assert Path(state.persistence_dir).exists()


def test_conversation_factory_with_directories(mock_agent):
    """测试会话工厂是否正确处理目录参数。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        persistence_dir = os.path.join(temp_dir, "persist")
        os.makedirs(working_dir)

        conversation = Conversation(
            agent=mock_agent,
            workspace=LocalWorkspace(working_dir=working_dir),
            persistence_dir=persistence_dir,
        )

        assert conversation.state.workspace.working_dir == working_dir
        # persistence_dir 应包含对话 ID 子目录
        expected_dir = os.path.join(persistence_dir, conversation.state.id.hex)
        assert conversation.state.persistence_dir == expected_dir


def test_conversation_factory_default_directories(mock_agent):
    """测试会话工厂在未指定时是否使用默认目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 更改为临时目录以避免与现有状态发生冲突
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            conversation = Conversation(agent=mock_agent)

            # 应使用“工作空间/项目”作为默认值工作目录
            assert conversation.state.workspace.working_dir == "workspace/project"
            assert conversation.state.persistence_dir is None
        finally:
            os.chdir(original_cwd)


def test_conversation_factory_working_dir_only(mock_agent):
    """测试会话工厂仅处理 working_dir。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = os.path.join(temp_dir, "work")
        os.makedirs(working_dir)

        conversation = Conversation(agent=mock_agent, workspace=working_dir)

        assert conversation.state.workspace.working_dir == working_dir
        assert conversation.state.persistence_dir is None


def test_conversation_factory_persistence_dir_only(mock_agent):
    """测试会话工厂仅处理 persistence_dir。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        persistence_dir = os.path.join(temp_dir, "persist")

        conversation = Conversation(agent=mock_agent, persistence_dir=persistence_dir)

        # 应使用默认的“工作空间/项目”作为工作目录
        assert conversation.state.workspace.working_dir == "workspace/project"
        # persistence_dir 应包含对话 ID 子目录
        expected_dir = os.path.join(persistence_dir, conversation.state.id.hex)
        assert conversation.state.persistence_dir == expected_dir


def test_no_persistence_dir_logs_warning(mock_agent, caplog):
    """测试未提供 persistence_dir 时是否记录警告。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = Path(temp_dir) / "work"
        working_dir.mkdir()

        with caplog.at_level(logging.WARNING):
            ConversationState.create(
                id=uuid.uuid4(),
                agent=mock_agent,
                workspace=LocalWorkspace(working_dir=working_dir),
            )

        assert any(
            "No persistence_dir provided; falling back to InMemoryFileStore"
            in record.message
            for record in caplog.records
        )
