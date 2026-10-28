"""测试对话中的路径类型处理和LocalConversation。"""

import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_conversation_with_path_workspace():
    """测试 Path 对象是否可以作为工作区参数传递。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # 应该接受工作区的 Path 对象
        conv = Conversation(agent=agent, workspace=workspace_path)

        # 验证工作区设置正确
        assert conv.workspace is not None
        assert isinstance(conv.workspace, LocalWorkspace)
        # working_dir 应该是路径的字符串表示形式
        assert conv.workspace.working_dir == str(workspace_path)
        # 验证路径存在并且可访问
        assert Path(conv.workspace.working_dir).exists()


def test_conversation_with_path_persistence_dir():
    """测试 Path 对象是否可以作为 persistence_dir 参数传递。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        persistence_path = Path(tmpdir) / "persistence"
        persistence_path.mkdir(parents=True, exist_ok=True)

        # 应该接受 persistence_dir 的 Path 对象
        conv = Conversation(
            agent=agent,
            workspace=str(workspace_path),
            persistence_dir=persistence_path,
        )

        # 验证持久化目录设置正确
        assert conv.state is not None
        assert conv.state.persistence_dir is not None
        # 持久化目录应包含对话 ID 作为子目录
        expected_persistence_dir = persistence_path / conv.id.hex
        # 验证实际的持久化路径与预期匹配
        assert Path(conv.state.persistence_dir) == expected_persistence_dir


def test_conversation_with_both_path_types():
    """测试工作区和 persistence_dir 都可以是 Path 对象。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        persistence_path = Path(tmpdir) / "persistence"
        persistence_path.mkdir(parents=True, exist_ok=True)

        # 两个参数都应该接受 Path 对象
        conv = Conversation(
            agent=agent,
            workspace=workspace_path,
            persistence_dir=persistence_path,
        )

        # 验证两者均设置正确
        assert conv.workspace is not None
        assert conv.workspace.working_dir == str(workspace_path)
        assert Path(conv.workspace.working_dir).exists()

        # 验证持久化目录
        assert conv.state.persistence_dir is not None
        expected_persistence_dir = persistence_path / conv.id.hex
        assert Path(conv.state.persistence_dir) == expected_persistence_dir


def test_local_workspace_with_path():
    """测试 LocalWorkspace 是否可以用 Path 对象初始化。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # 应该直接接受 Path 对象（通过验证器转换为 str）
        workspace = LocalWorkspace(working_dir=workspace_path)

        # 验证 working_dir 是否正确转换为字符串
        assert workspace.working_dir == str(workspace_path)
        assert isinstance(workspace.working_dir, str)


def test_conversation_with_localworkspace_from_path():
    """测试通过使用对话路径初始化的 LocalWorkspace。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # 使用 Path 创建 LocalWorkspace（通过验证器转换为 str）
        workspace = LocalWorkspace(working_dir=str(workspace_path))

        # 将 LocalWorkspace 传递到对话
        conv = Conversation(agent=agent, workspace=workspace)

        # 验证工作区设置正确
        assert conv.workspace is workspace
        assert conv.workspace.working_dir == str(workspace_path)
