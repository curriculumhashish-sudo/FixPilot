"""测试路线级别 ``agent.agent_context.skills`` 修剪。

对话内容为端点 (``GET /search``, ``GET /{id}``,
``GET ""``, ``POST ""``, ``POST /{id}/fork``) 在会话路由器上从响应载荷中剥离
``agent.agent_context.skills``
**默认情况下**（截至本版本为不兼容变更）。 来电者表示
仍然需要遗留形状才能通过``?include_skills=true``。 已持久化 ``ConversationState`` 和
智能体运行时保存的内存中副本不受影响 -
 只有 HTTP 上留下的字节会收缩。

请参阅 SDK PR 描述，了解为什么它位于路线边界而不是 ``AgentContext`` 本身内部。
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.config import Config
from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.models import (
    ConversationInfo,
    ConversationPage,
    trim_conversation_response_skills,
)
from openhands.agent_server.utils import utc_now
from openhands.sdk import LLM, Agent
from openhands.sdk.context import AgentContext
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.skills import Skill
from openhands.sdk.workspace import LocalWorkspace


def _make_skill(name: str, content: str = "skill body bytes") -> Skill:
    return Skill(name=name, content=content, source=f"/fake/{name}.md")


def _make_conversation_with_skills(skills: list[Skill]) -> ConversationInfo:
    """构建一个 ``ConversationInfo``，其智能体带有 ``skills``。

    否则，完整的 ``AgentContext`` 字段集为空，因此修剪后的载荷仅反映技能增量。
    """
    now = utc_now()
    return ConversationInfo(
        id=uuid4(),
        agent=Agent(
            llm=LLM(model="gpt-4o", api_key=SecretStr("k"), usage_id="test-llm"),
            tools=[],
            agent_context=AgentContext(skills=skills),
        ),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="Test",
        created_at=now,
        updated_at=now,
    )


class TestTrimHelper:
    """单元测试为纯函数助手。"""

    def test_strips_skills_when_present(self):
        info = _make_conversation_with_skills(
            [_make_skill("a"), _make_skill("b"), _make_skill("c")]
        )
        trimmed = trim_conversation_response_skills(info)
        assert trimmed.agent.agent_context is not None
        assert trimmed.agent.agent_context.skills == []

    def test_returns_same_instance_when_nothing_to_strip(self):
        # 清空技能列表→身份返回（无需model_copy）。
        info = _make_conversation_with_skills([])
        trimmed = trim_conversation_response_skills(info)
        assert trimmed is info

    def test_does_not_touch_other_agent_context_fields(self):
        info = _make_conversation_with_skills([_make_skill("a")])
        # 改变一个非技能领域，这样我们就可以断言它能够生存。
        assert info.agent.agent_context is not None
        info = info.model_copy(
            update={
                "agent": info.agent.model_copy(
                    update={
                        "agent_context": info.agent.agent_context.model_copy(
                            update={"system_message_suffix": "carry me through"}
                        )
                    }
                )
            }
        )
        trimmed = trim_conversation_response_skills(info)
        assert trimmed.agent.agent_context is not None
        assert trimmed.agent.agent_context.skills == []
        assert trimmed.agent.agent_context.system_message_suffix == "carry me through"

    def test_does_not_mutate_input(self):
        info = _make_conversation_with_skills([_make_skill("a"), _make_skill("b")])
        trim_conversation_response_skills(info)
        # 调用者的参考仍然可以看到完整的技能 - model_copy 给了我们一个新鲜的实例，输入未
        # 受影响。
        #
        assert info.agent.agent_context is not None
        assert {s.name for s in info.agent.agent_context.skills} == {"a", "b"}

    def test_agent_without_agent_context_passes_through(self):
        now = utc_now()
        info = ConversationInfo(
            id=uuid4(),
            agent=Agent(
                llm=LLM(model="gpt-4o", api_key=SecretStr("k"), usage_id="t"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir="/tmp/test"),
            execution_status=ConversationExecutionStatus.IDLE,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        # 根本没有 agent_context → helper 是一个空操作。
        assert trim_conversation_response_skills(info) is info


class TestRouteIntegration:
    """集成测试通过 FastAPI 路由器。

    证明了新的默认修剪语义和
    ``?include_skills=true`` 在每次返回 ``ConversationInfo`` 的读取端点时选择加入逃生
    舱口。
    """

    @pytest.fixture
    def heavy_conversation(self):
        # 5 个具有重要内容的技能 — 足以使修剪在已序列化 JSON 字节数中可见。
        #
        return _make_conversation_with_skills(
            [_make_skill(f"skill-{i}", "x" * 500) for i in range(5)]
        )

    @pytest.fixture
    def client(self, heavy_conversation):
        service = AsyncMock(spec=ConversationService)
        service.get_conversation.return_value = heavy_conversation
        service.batch_get_conversations.return_value = [heavy_conversation]
        service.search_conversations.return_value = ConversationPage(
            items=[heavy_conversation], next_page_id=None
        )

        app = FastAPI()
        app.include_router(conversation_router, prefix="/api")
        app.state.config = Config(
            static_files_path=None, session_api_keys=[], secret_key=None
        )
        app.dependency_overrides[get_conversation_service] = lambda: service
        return TestClient(app), heavy_conversation

    # --- 默认（无查询参数）→ 修剪（破坏性更改行为）---

    def test_get_conversation_default_trims_skills(self, client):
        """默认响应将 ``agent.agent_context.skills`` 修剪为 ``[]``。

        这是不兼容变更：之前的版本返回了内联的完整技能列表。 阅读的来电者
        ``conversation.agent.agent_context.skills``（特别是通过
        ``RemoteConversation``) 现在参见 ``[]``，除非他们通过
        ``?include_skills=true``. 目前没有已知的客户端（智能体-canvas，OpenHands-app-
        server，SDK-examp
        les）从HTTP响应中读取该字段，因此此更改是文档+选择性启用，而不是协调迁移。
        """
        c, heavy = client
        response = c.get(f"/api/conversations/{heavy.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["agent"]["agent_context"]["skills"] == []

    def test_batch_get_default_trims_skills(self, client):
        c, heavy = client
        response = c.get(f"/api/conversations?ids={heavy.id}")
        assert response.status_code == 200
        body = response.json()
        assert body[0]["agent"]["agent_context"]["skills"] == []

    def test_search_default_trims_skills(self, client):
        c, _heavy = client
        response = c.get("/api/conversations/search")
        assert response.status_code == 200
        body = response.json()
        assert body["items"][0]["agent"]["agent_context"]["skills"] == []

    # --- include_skills=False（显式）→ 与默认值相同 ---

    def test_get_conversation_explicit_false_trims_skills(self, client):
        c, heavy = client
        response = c.get(f"/api/conversations/{heavy.id}?include_skills=false")
        assert response.status_code == 200
        body = response.json()
        assert body["agent"]["agent_context"]["skills"] == []

    # --- include_skills=True → 选择旧版完整载荷 ---

    def test_get_conversation_opt_in_includes_skills(self, client):
        """旧版选择加入。 仍在阅读的来电者
        来自 HTTP 响应的 ``conversation.agent.agent_context.skills`` 可以通过
        ``?include_skills=true`` 以保持先前的形状。 记录为弃用逃生舱口，而不是稳态路
        径。
        """
        c, heavy = client
        response = c.get(f"/api/conversations/{heavy.id}?include_skills=true")
        assert response.status_code == 200
        body = response.json()
        assert len(body["agent"]["agent_context"]["skills"]) == 5

    def test_batch_get_opt_in_includes_skills(self, client):
        c, heavy = client
        response = c.get(f"/api/conversations?ids={heavy.id}&include_skills=true")
        assert response.status_code == 200
        body = response.json()
        assert len(body[0]["agent"]["agent_context"]["skills"]) == 5

    def test_search_opt_in_includes_skills(self, client):
        c, _heavy = client
        response = c.get("/api/conversations/search?include_skills=true")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"][0]["agent"]["agent_context"]["skills"]) == 5

    def test_batch_get_handles_null_items(self):
        """丢失的物品返回 ``None`` 并且修剪不会在它们上崩溃。"""
        service = AsyncMock(spec=ConversationService)
        service.batch_get_conversations.return_value = [None]
        app = FastAPI()
        app.include_router(conversation_router, prefix="/api")
        app.state.config = Config(
            static_files_path=None, session_api_keys=[], secret_key=None
        )
        app.dependency_overrides[get_conversation_service] = lambda: service
        c = TestClient(app)
        response = c.get(f"/api/conversations?ids={uuid4()}")
        assert response.status_code == 200
        assert response.json() == [None]

    def test_default_response_size_drops_meaningfully(self, client):
        """比较默认（已修剪）与选择加入（完整）HTTP 响应。

        对话有5个技能×500个字符的内容。 默认响应至少应比显式 ``?include_skills=true``
         选择加入小得多。
        """
        c, _heavy = client
        default_bytes = len(c.get("/api/conversations/search").content)
        full_bytes = len(c.get("/api/conversations/search?include_skills=true").content)
        # 5 × 500 个字符的“x”技能内容 + 每个技能元数据开销。 保守地要求至少削减 1500 字
        # 节。
        #
        assert full_bytes - default_bytes > 1500, (
            f"default trim should drop ~2500 B of skill content; got "
            f"{full_bytes - default_bytes} B saved "
            f"(full {full_bytes} → default {default_bytes})"
        )
