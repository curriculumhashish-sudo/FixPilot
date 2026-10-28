"""ConversationService 中的插件处理测试。

该模块通过 StartConversationRequest 上的 `plugins` 列表参数测试插件处理。

这些测试验证：
1. 插件规范传递到 StoredConversation（用于延迟加载）
2. 显式 hook_config 被保留（合并在 LocalConversation 中延迟发生）
3. 插件 ARE 已持久化（与旧的急切加载模型不同），因为 LocalConversation 在第一个 run()
/send_message() 上延迟加载它们
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import (
    StartConversationRequest,
    StoredConversation,
)
from openhands.sdk import LLM
from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher, HookType
from openhands.sdk.plugin import PluginSource
from openhands.sdk.workspace import LocalWorkspace


def create_test_plugin_dir(
    tmp_path: Path,
    *,
    skills: list[dict] | None = None,
    hooks: dict | None = None,
    mcp_config: dict | None = None,
) -> Path:
    """创建测试插件目录结构。"""
    import json

    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir(parents=True)

    # 创建清单
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir()
    manifest_file = manifest_dir / "plugin.json"
    manifest_file.write_text('{"name": "test-plugin", "version": "1.0.0"}')

    # 创造技能
    if skills:
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        for skill_data in skills:
            skill_dir = skills_dir / skill_data["name"]
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                f"""---
name: {skill_data["name"]}
description: Test skill
---

{skill_data.get("content", "Test content")}
"""
            )

    # 创建挂钩
    if hooks:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir()
        hooks_json = hooks_dir / "hooks.json"
        hooks_json.write_text(json.dumps(hooks))

    # 创建 MCP 配置
    if mcp_config:
        mcp_json = plugin_dir / ".mcp.json"
        mcp_json.write_text(json.dumps(mcp_config))

    return plugin_dir


@pytest.fixture
def conversation_service():
    """创建一个 ConversationService 实例用于测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        service = ConversationService(
            conversations_dir=Path(temp_dir) / "conversations",
        )
        service._event_services = {}
        yield service


def test_start_conversation_request_has_plugins_field():
    """验证 StartConversationRequest 具有插件列表字段（不是旧字段）。"""
    fields = StartConversationRequest.model_fields
    # 新的插件列表字段应该存在
    assert "plugins" in fields
    # 旧版单个插件字段不应存在
    assert "plugin_source" not in fields
    assert "plugin_ref" not in fields
    assert "plugin_path" not in fields


@pytest.mark.asyncio
async def test_start_conversation_without_plugin(conversation_service):
    """测试 start_conversation 无需插件配置即可工作。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证无插件时hook_config为None
            stored = mock_event_service_class.call_args.kwargs["stored"]
            assert stored.hook_config is None


# 测试插件列表参数


@pytest.mark.asyncio
async def test_start_conversation_with_plugins_list(conversation_service, tmp_path):
    """测试 start_conversation 将插件传递给 StoredConversation 以进行延迟加载。"""
    # 使用挂钩和技能创建插件
    plugin_dir = create_test_plugin_dir(
        tmp_path,
        skills=[{"name": "test-skill", "content": "Test skill content"}],
        hooks={
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo pre"}],
                    }
                ]
            }
        },
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
            plugins=[PluginSource(source=str(plugin_dir))],
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(exclude={"agent"}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证插件是否已通过延迟加载
            stored = mock_event_service_class.call_args.kwargs["stored"]
            # 插件应该被存储（尚未加载 - 延迟加载）
            assert stored.plugins is not None
            assert len(stored.plugins) == 1
            assert stored.plugins[0].source == str(plugin_dir)
            # 智能体单独传递到 EventService（已持久化到 base_state.json，而不是
            # meta.json）。 智能体上下文不尚未填充（LocalConversation 中延迟加载）。
            #
            agent = mock_event_service_class.call_args.kwargs["agent"]
            assert agent.agent_context is None


@pytest.mark.asyncio
async def test_start_conversation_with_multiple_plugins(conversation_service, tmp_path):
    """使用存储的多个插件进行测试 start_conversation 以进行延迟加载。"""
    # 创建两个插件
    plugin1_dir = create_test_plugin_dir(
        tmp_path / "plugin1",
        skills=[{"name": "skill-a", "content": "Skill A"}],
    )
    plugin2_dir = create_test_plugin_dir(
        tmp_path / "plugin2",
        skills=[{"name": "skill-b", "content": "Skill B"}],
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
            plugins=[
                PluginSource(source=str(plugin1_dir)),
                PluginSource(source=str(plugin2_dir)),
            ],
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(exclude={"agent"}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证两个插件是否已存储以进行延迟加载
            stored = mock_event_service_class.call_args.kwargs["stored"]
            assert stored.plugins is not None
            assert len(stored.plugins) == 2
            plugin_sources = [p.source for p in stored.plugins]
            assert str(plugin1_dir) in plugin_sources
            assert str(plugin2_dir) in plugin_sources


@pytest.mark.asyncio
async def test_plugins_persisted_in_stored_conversation_for_lazy_loading(
    conversation_service, tmp_path
):
    """通过 LocalConversation 测试插件 ARE 已持久化的延迟加载。"""
    plugin_dir = create_test_plugin_dir(
        tmp_path,
        skills=[{"name": "test-skill", "content": "Test"}],
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
            plugins=[PluginSource(source=str(plugin_dir))],
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(exclude={"agent"}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证插件 ARE 已持久化（用于延迟加载）LocalConversation 将在第一个 run()
            # /send_message() 上加载它们
            #
            stored = mock_event_service_class.call_args.kwargs["stored"]
            assert stored.plugins is not None
            assert len(stored.plugins) == 1
            assert stored.plugins[0].source == str(plugin_dir)


# 显式测试 hook_config


def test_start_conversation_request_has_hook_config_field():
    """验证 StartConversationRequest 具有 hook_config 字段。"""
    fields = StartConversationRequest.model_fields
    assert "hook_config" in fields


@pytest.mark.asyncio
async def test_start_conversation_with_explicit_hook_config(conversation_service):
    """使用显式 hook_config 测试 start_conversation（无插件）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        explicit_hooks = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="*",
                    hooks=[
                        HookDefinition(type=HookType.COMMAND, command="echo explicit")
                    ],
                )
            ]
        )
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
            hook_config=explicit_hooks,
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证是否使用了显式 hook_config
            stored = mock_event_service_class.call_args.kwargs["stored"]
            assert stored.hook_config is not None
            assert len(stored.hook_config.pre_tool_use) == 1
            hook_cmd = stored.hook_config.pre_tool_use[0].hooks[0].command
            assert hook_cmd == "echo explicit"


@pytest.mark.asyncio
async def test_start_conversation_stores_both_hooks_and_plugins_for_lazy_merge(
    conversation_service, tmp_path
):
    """测试显式 hook_config 和插件是否都已存储（合并是惰性的）。"""
    # 使用钩子创建插件
    plugin_dir = create_test_plugin_dir(
        tmp_path,
        hooks={
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo plugin"}],
                    }
                ]
            }
        },
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        explicit_hooks = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="*",
                    hooks=[
                        HookDefinition(type=HookType.COMMAND, command="echo explicit")
                    ],
                )
            ]
        )
        request = StartConversationRequest(
            agent=Agent(
                llm=LLM(model="gpt-4o", usage_id="test-llm"),
                tools=[],
            ),
            workspace=LocalWorkspace(working_dir=temp_dir),
            plugins=[PluginSource(source=str(plugin_dir))],
            hook_config=explicit_hooks,
        )

        with patch(
            "openhands.agent_server.conversation_service.EventService"
        ) as mock_event_service_class:
            mock_event_service = AsyncMock(spec=EventService)
            mock_event_service_class.return_value = mock_event_service

            mock_state = ConversationState(
                id=uuid4(),
                agent=request.agent,
                workspace=request.workspace,
                execution_status=ConversationExecutionStatus.IDLE,
                confirmation_policy=request.confirmation_policy,
            )
            mock_event_service.get_state.return_value = mock_state
            mock_event_service.stored = StoredConversation(
                id=mock_state.id,
                **request.model_dump(exclude={"agent"}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            await conversation_service.start_conversation(request)

            # 验证两个显式挂钩 AND 插件均已存储（合并在
            # LocalConversation._ensure_plugins_loaded 中延迟发生）
            #
            stored = mock_event_service_class.call_args.kwargs["stored"]

            # 显式 hook_config 按原样存储（尚未合并）
            assert stored.hook_config is not None
            assert len(stored.hook_config.pre_tool_use) == 1
            assert (
                stored.hook_config.pre_tool_use[0].hooks[0].command == "echo explicit"
            )

            # 存储插件以供延迟加载
            assert stored.plugins is not None
            assert len(stored.plugins) == 1
