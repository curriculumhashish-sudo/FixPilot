"""LocalConversation 上客户端定义的工具的持久/恢复行为。"""

import gc
import uuid
from pathlib import Path

import pytest

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.settings import OpenHandsAgentSettings
from openhands.sdk.tool import Tool, client_tool as ct, registry as reg
from openhands.sdk.tool.client_tool import ClientToolSpec, register_client_tools
from openhands.sdk.utils.models import clear_subclass_cache


@pytest.fixture(autouse=True)
def _collect_dynamic_client_tool_classes():
    """删除这些测试定义的动态 ``ClientAction_*`` 类。

    每个客户端工具规范都会构建一个新类，因此两次注册相同工具名称的测试会留下两个同名
    的类。 它们只能通过引用循环访问，因此在循环集合运行之前，它们会保留在
    ``Action.__subclasses__()`` 中并进行重复类签入
    ``_get_checked_concrete_subclasses`` 在*不相关的*个后续测试中失败。 一旦测试框架
    消失，在拆卸时收集，将泄漏保留在本地。
    """
    yield
    gc.collect()
    clear_subclass_cache()


def _make_agent() -> Agent:
    return Agent(
        llm=LLM(model="gpt-4o", usage_id="test-llm"),
        tools=[Tool(name="terminal")],
    )


def _wipe_client_tool_globals(names: list[str]) -> None:
    """模拟未注册动态客户端工具的新流程。"""
    ct._client_action_types.clear()
    ct._client_action_schemas.clear()
    for name in names:
        reg._REG.pop(name, None)
        reg._USABILITY_REG.pop(name, None)
        reg._TOOL_CLASSES.pop(name, None)


def test_persisted_client_tools_resume_without_respecifying(tmp_path: Path) -> None:
    """已持久化对话在恢复时重新注册/注入客户端工具。

    调用者未在简历中传递 ``client_tools``； 规范必须从已持久化状态恢复，以便智能体保
    留工具，并且恢复不会因“工具在对话中被删除”而失败。
    """
    specs = [
        ClientToolSpec(
            name="persist_show_notification",
            description="show",
            parameters={
                "type": "object",
                "properties": {"message": {"type": "string"}},
            },
        ),
        ClientToolSpec(
            name="persist_navigate_to",
            description="nav",
            parameters={
                "type": "object",
                "properties": {"route": {"type": "string"}},
            },
        ),
    ]
    names = [s.name for s in specs]
    cid = uuid.uuid4()
    persist_dir = tmp_path / "persist"
    ws_dir = tmp_path / "ws"

    created = Conversation(
        agent=_make_agent(),
        workspace=str(ws_dir),
        persistence_dir=str(persist_dir),
        conversation_id=cid,
        client_tools=specs,
        delete_on_close=False,
    )
    assert set(names) <= {t.name for t in created.agent.tools}
    created.close()

    # 新流程模拟：放弃全局注册。
    _wipe_client_tool_globals(names)
    assert not any(n in reg.list_registered_tools() for n in names)

    # 恢复 WITHOUT 重新供应 client_tools。
    resumed = Conversation(
        agent=_make_agent(),
        workspace=str(ws_dir),
        persistence_dir=str(persist_dir),
        conversation_id=cid,
        delete_on_close=False,
    )
    try:
        assert set(names) <= {t.name for t in resumed.agent.tools}
        # 动态操作类型再次注册，因此已持久化 ClientAction_* 事件可能是已反序列化。
        #
        for n in names:
            assert n in reg.list_registered_tools()
    finally:
        resumed.close()


def test_client_tool_named_like_an_unattached_builtin_resumes(
    tmp_path: Path,
) -> None:
    specs = [ClientToolSpec(name="route_task_to_model", description="client")]
    cid = uuid.uuid4()
    ws, persist = str(tmp_path / "ws"), str(tmp_path / "persist")
    Conversation(
        agent=_make_agent(),
        workspace=ws,
        persistence_dir=persist,
        conversation_id=cid,
        client_tools=specs,
        delete_on_close=False,
    ).close()
    _wipe_client_tool_globals(["route_task_to_model"])

    resumed = Conversation(
        agent=_make_agent(),
        workspace=ws,
        persistence_dir=persist,
        conversation_id=cid,
        delete_on_close=False,
    )
    try:
        assert "route_task_to_model" in {t.name for t in resumed.agent.tools}
    finally:
        resumed.close()


def test_client_tool_named_like_an_attached_builtin_is_rejected(
    tmp_path: Path,
) -> None:
    convo = Conversation(
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=str(tmp_path / "ws"),
        persistence_dir=str(tmp_path / "persist"),
        conversation_id=uuid.uuid4(),
        client_tools=[ClientToolSpec(name="finish", description="client")],
        delete_on_close=False,
    )
    try:
        with pytest.raises(ValueError, match="Duplicate tool names"):
            convo._ensure_agent_ready()
    finally:
        convo.close()
        _wipe_client_tool_globals(["finish"])


def test_client_tool_named_like_a_builtin_leaves_other_agents_alone() -> None:
    register_client_tools([ClientToolSpec(name="switch_llm", description="client")])
    try:
        agent = OpenHandsAgentSettings(
            llm=LLM(model="gpt-4o", usage_id="test-llm")
        ).create_agent()
    finally:
        _wipe_client_tool_globals(["switch_llm"])

    assert "switch_llm" not in {t.name for t in agent.tools}
    assert "SwitchLLMTool" in agent.include_default_tools


def test_recover_persisted_client_tools_no_state(tmp_path: Path) -> None:
    """当没有已持久化基状态时，恢复是无操作（空列表）。"""
    convo = Conversation(
        agent=_make_agent(),
        workspace=str(tmp_path / "ws"),
        persistence_dir=str(tmp_path / "persist"),
        conversation_id=uuid.uuid4(),
        delete_on_close=False,
    )
    try:
        recovered = convo._recover_persisted_client_tools(
            str(tmp_path / "nonexistent"), uuid.uuid4()
        )
        assert recovered == []
    finally:
        convo.close()
