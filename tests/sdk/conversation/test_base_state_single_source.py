"""回归测试：base_state.json 是智能体的唯一事实来源。

这些固定 meta.json / base_state.json 重复数据删除背后的行为：

* 当调用者提供 ``agent=None`` 时，``ConversationState.create`` 从 ``base_state.json``
 恢复智能体 — 持
久模型开关在重新加载后仍可正常运行。
* 在恢复时传递显式智能体会保留传统的验证和覆盖行为（在恢复时重新配置的调用者的向后兼
容）。
"""

import uuid

import pytest

from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.io import LocalFileStore
from openhands.sdk.workspace import LocalWorkspace


def _agent(model: str, usage_id: str = "default") -> Agent:
    return Agent(llm=LLM(model=model, usage_id=usage_id), tools=[])


def test_resume_with_agent_none_keeps_persisted_agent(tmp_path):
    """写入 base_state.json 的模型更改在智能体=None 重新加载后仍然有效。"""
    file_store = LocalFileStore(str(tmp_path))
    workspace = LocalWorkspace(working_dir=str(tmp_path))

    cid = uuid.uuid4()
    state = ConversationState.create(
        id=cid,
        agent=_agent("model-a"),
        workspace=workspace,
        file_store=file_store,
    )
    # 模拟持久开关：将智能体重写为base_state.json。
    state.agent = _agent("model-b")
    assert state.agent.llm.model == "model-b"

    # 不提供智能体 -> base_state.json 的重新加载是权威的。
    reloaded = ConversationState.create(
        id=cid,
        agent=None,
        workspace=workspace,
        file_store=LocalFileStore(str(tmp_path)),
    )
    assert reloaded.agent.llm.model == "model-b"


def test_resume_with_explicit_agent_overrides(tmp_path):
    """在恢复中传递智能体会保留旧版验证并覆盖行为。"""
    file_store = LocalFileStore(str(tmp_path))
    workspace = LocalWorkspace(working_dir=str(tmp_path))
    cid = uuid.uuid4()

    ConversationState.create(
        id=cid,
        agent=_agent("model-a"),
        workspace=workspace,
        file_store=file_store,
    )

    reloaded = ConversationState.create(
        id=cid,
        agent=_agent("model-c"),
        workspace=workspace,
        file_store=LocalFileStore(str(tmp_path)),
    )
    assert reloaded.agent.llm.model == "model-c"


def test_new_conversation_requires_agent(tmp_path):
    """创建一个全新的状态（没有base_state.json）仍然需要智能体。"""
    with pytest.raises(ValueError, match="agent is required"):
        ConversationState.create(
            id=uuid.uuid4(),
            agent=None,
            workspace=LocalWorkspace(working_dir=str(tmp_path)),
            file_store=LocalFileStore(str(tmp_path)),
        )
