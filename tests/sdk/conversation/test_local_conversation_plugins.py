"""通过 LocalConversation 和对话工厂测试插件加载。"""

import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent, AgentContext, Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.hooks import HookConfig
from openhands.sdk.hooks.config import HookDefinition, HookMatcher
from openhands.sdk.marketplace import MarketplaceRegistration
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import MCPServer, dump_mcp_config
from openhands.sdk.plugin import (
    PluginSource,
    discovery,
    install_plugin,
    installed,
)
from openhands.sdk.skills import Skill
from openhands.sdk.skills.skill import DEFAULT_MARKETPLACE_PATH
from openhands.sdk.tool.builtins import ThinkTool


class EmptyMCPClient:
    def __init__(self):
        self.tools = []
        self._tools_reconciled_callback: Any = None


class RecordingMCPToolProvider:
    def __init__(
        self,
        created: list[Any],
        client: object | None = None,
        state_locked: Callable[[], bool] | None = None,
    ):
        self.created = created
        self.client: Any = client or EmptyMCPClient()
        self.state_locked = state_locked

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: Any = None,
        on_tools_reconciled: Any = None,
    ) -> MCPClient:
        if self.state_locked is None:
            self.created.append(mcp_config)
        else:
            self.created.append((mcp_config, self.state_locked()))
        self.client._tools_reconciled_callback = on_tools_reconciled
        return cast(MCPClient, self.client)


@pytest.fixture
def mock_llm():
    """为智能体个测试创建模拟对象 LLM。"""
    return LLM(
        model="test/model",
        api_key=SecretStr("test-key"),
    )


@pytest.fixture
def basic_agent(mock_llm):
    """创建一个基本的智能体进行测试。"""
    return Agent(
        llm=mock_llm,
        tools=[],
    )


def create_test_plugin(
    plugin_dir: Path,
    name: str = "test-plugin",
    skills: list[dict] | None = None,
    mcp_config: dict | None = None,
    hooks: dict | None = None,
):
    """帮助程序创建测试插件目录。"""
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"name": name, "version": "1.0.0", "description": f"Test plugin {name}"}
    (manifest_dir / "plugin.json").write_text(json.dumps(manifest))

    if skills:
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for skill in skills:
            skill_name = skill["name"]
            skill_content = skill["content"]
            skill_file = skills_dir / f"{skill_name}.md"
            skill_file.write_text(f"---\nname: {skill_name}\n---\n{skill_content}")

    if mcp_config:
        mcp_file = plugin_dir / ".mcp.json"
        mcp_file.write_text(json.dumps(mcp_config))

    if hooks:
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hooks_file = hooks_dir / "hooks.json"
        hooks_file.write_text(json.dumps(hooks))

    return plugin_dir


def create_test_marketplace(
    marketplace_dir: Path,
    plugins: list[dict],
    name: str = "test-marketplace",
) -> Path:
    """使用本地插件条目创建测试市场的帮助程序。"""
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for plugin in plugins:
        plugin_name = plugin["name"]
        create_test_plugin(
            marketplace_dir / "plugins" / plugin_name,
            name=plugin_name,
            skills=plugin.get("skills"),
            mcp_config=plugin.get("mcp_config"),
            hooks=plugin.get("hooks"),
        )
        entry = {
            "name": plugin_name,
            "source": plugin.get("source", f"./plugins/{plugin_name}"),
            "description": f"Test plugin {plugin_name}",
        }
        if "ref" in plugin:
            entry["ref"] = plugin["ref"]
        if "repo_path" in plugin:
            entry["repo_path"] = plugin["repo_path"]
        entries.append(entry)

    manifest = {
        "name": name,
        "owner": {"name": "Test Team"},
        "plugins": entries,
    }
    (manifest_dir / "marketplace.json").write_text(json.dumps(manifest))
    return marketplace_dir


def create_test_marketplace_with_standalone_skills(
    marketplace_dir: Path,
    skills: list[str],
    name: str = "skills-marketplace",
) -> Path:
    """帮助创建一个仅声明独立技能的市场。"""
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for skill_name in skills:
        skill_dir = marketplace_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: {skill_name} desc\n---\nbody"
        )
        entries.append({"name": skill_name, "source": f"./skills/{skill_name}"})
    manifest = {
        "name": name,
        "owner": {"name": "Test Team"},
        "plugins": [],
        "skills": entries,
    }
    (manifest_dir / "marketplace.json").write_text(json.dumps(manifest))
    return marketplace_dir


class TestLocalConversationPlugins:
    """测试 LocalConversation 中的插件加载。

    Note: 插件在第一次 run()/send_message() 调用时延迟加载。
    测试触发器 _ensure_plugins_loaded() 以验证加载行为。
    """

    def test_auto_load_marketplace_plugins(self, tmp_path: Path, mock_llm):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "auto-plugin",
                    "skills": [{"name": "auto-skill", "content": "Auto-loaded skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        public_skill = Skill(name="public-skill", content="Public", trigger=None)
        with patch(
            "openhands.sdk.context.agent_context.load_available_skills",
            return_value={"public-skill": public_skill},
        ) as load_available_skills:
            agent = Agent(
                llm=mock_llm,
                tools=[],
                agent_context=AgentContext(
                    load_public_skills=True,
                    registered_marketplaces=[
                        MarketplaceRegistration(
                            name="auto",
                            source=str(marketplace_dir),
                            auto_load=True,
                        )
                    ],
                ),
            )

        load_available_skills.assert_called_with(
            work_dir=None,
            include_user=False,
            include_project=False,
            include_public=True,
            marketplace_path=DEFAULT_MARKETPLACE_PATH,
        )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "auto-skill" in skill_names
        assert "public-skill" in skill_names
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1

    def test_auto_load_marketplace_standalone_skills(self, tmp_path: Path, mock_llm):
        """独立市场技能自动加载到智能体上下文中。"""
        marketplace_dir = create_test_marketplace_with_standalone_skills(
            tmp_path / "marketplace",
            skills=["greet", "commit"],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        with patch(
            "openhands.sdk.context.agent_context.load_available_skills",
            return_value={},
        ):
            agent = Agent(
                llm=mock_llm,
                tools=[],
                agent_context=AgentContext(
                    registered_marketplaces=[
                        MarketplaceRegistration(
                            name="skills-only",
                            source=str(marketplace_dir),
                            auto_load=True,
                        )
                    ],
                ),
            )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = {s.name for s in conversation.agent.agent_context.skills}
        assert {"greet", "commit"} <= skill_names

        conversation.close()

    def test_auto_load_plain_skills_repository(self, tmp_path: Path, mock_llm):
        """没有清单的注册存储库会自动加载其技能。"""
        repo = create_test_marketplace_with_standalone_skills(
            tmp_path / "repo",
            skills=["greet", "commit"],
        )
        shutil.rmtree(repo / ".plugin")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        with patch(
            "openhands.sdk.context.agent_context.load_available_skills",
            return_value={},
        ):
            agent = Agent(
                llm=mock_llm,
                tools=[],
                agent_context=AgentContext(
                    registered_marketplaces=[
                        MarketplaceRegistration(
                            name="plain", source=str(repo), auto_load=True
                        )
                    ],
                ),
            )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = {s.name for s in conversation.agent.agent_context.skills}
        assert {"greet", "commit"} <= skill_names

        conversation.close()

    def test_plugin_wins_over_standalone_on_name_collision(
        self, tmp_path: Path, mock_llm
    ):
        """插件技能会覆盖同名的独立技能（目录规则）。"""
        marketplace_dir = tmp_path / "marketplace"
        create_test_plugin(
            marketplace_dir / "plugins" / "p",
            name="p",
            skills=[{"name": "shared", "content": "FROM_PLUGIN"}],
        )
        standalone = marketplace_dir / "skills" / "shared"
        standalone.mkdir(parents=True)
        (standalone / "SKILL.md").write_text(
            "---\nname: shared\ndescription: d\n---\nFROM_STANDALONE"
        )
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "collision",
                    "owner": {"name": "Test Team"},
                    "plugins": [{"name": "p", "source": "./plugins/p"}],
                    "skills": [{"name": "shared", "source": "./skills/shared"}],
                }
            )
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        with patch(
            "openhands.sdk.context.agent_context.load_available_skills",
            return_value={},
        ):
            agent = Agent(
                llm=mock_llm,
                tools=[],
                agent_context=AgentContext(
                    registered_marketplaces=[
                        MarketplaceRegistration(
                            name="collision",
                            source=str(marketplace_dir),
                            auto_load=True,
                        )
                    ],
                ),
            )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skills = {s.name: s for s in conversation.agent.agent_context.skills}
        assert "shared" in skills
        assert "FROM_PLUGIN" in skills["shared"].content
        assert "FROM_STANDALONE" not in skills["shared"].content

        conversation.close()

    def test_auto_load_marketplace_plugin_list_selects_plugins(
        self, tmp_path: Path, mock_llm
    ):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "formatter",
                    "skills": [{"name": "formatter-skill", "content": "Format"}],
                },
                {
                    "name": "linter",
                    "skills": [{"name": "linter-skill", "content": "Lint"}],
                },
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="selective",
                        source=str(marketplace_dir),
                        auto_load=["formatter"],
                    )
                ]
            ),
        )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert [skill.name for skill in conversation.agent.agent_context.skills] == [
            "formatter-skill"
        ]
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1

        conversation.close()

    def test_auto_load_marketplace_expands_registration_secret_refs(
        self, tmp_path: Path, mock_llm
    ):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "auto-plugin",
                    "skills": [{"name": "auto-skill", "content": "Auto-loaded skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="private",
                        source="https://${MARKETPLACE_TOKEN}@example.com/catalog.git",
                        ref="${MARKETPLACE_REF}",
                        repo_path="catalogs/team",
                        auto_load=True,
                    )
                ]
            ),
        )
        conversation = LocalConversation(
            agent=agent, workspace=workspace, visualizer=None
        )
        conversation.update_secrets(
            {
                "MARKETPLACE_TOKEN": "token-value",
                "MARKETPLACE_REF": "release-branch",
            }
        )

        with patch(
            "openhands.sdk.marketplace.registry.fetch_plugin_with_resolution",
            return_value=(marketplace_dir, "abc123"),
        ) as mock_fetch:
            conversation._ensure_plugins_loaded()

        mock_fetch.assert_called_once_with(
            source="https://token-value@example.com/catalog.git",
            ref="release-branch",
            repo_path="catalogs/team",
        )
        assert conversation.agent.agent_context is not None
        assert [skill.name for skill in conversation.agent.agent_context.skills] == [
            "auto-skill"
        ]
        conversation.close()

    def test_auto_load_marketplace_continues_after_fetch_failure(
        self, tmp_path: Path, mock_llm, caplog: pytest.LogCaptureFixture
    ):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "auto-plugin",
                    "skills": [{"name": "auto-skill", "content": "Auto-loaded skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="broken",
                        source=str(tmp_path / "missing-marketplace"),
                        auto_load=True,
                    ),
                    MarketplaceRegistration(
                        name="working",
                        source=str(marketplace_dir),
                        auto_load=True,
                    ),
                ]
            ),
        )
        conversation = LocalConversation(
            agent=agent, workspace=workspace, visualizer=None
        )

        with caplog.at_level(
            "WARNING", logger="openhands.sdk.conversation.impl.local_conversation"
        ):
            conversation._ensure_plugins_loaded()

        assert (
            "Failed to load marketplace 'broken'; continuing without it" in caplog.text
        )
        assert conversation.agent.agent_context is not None
        assert [skill.name for skill in conversation.agent.agent_context.skills] == [
            "auto-skill"
        ]
        conversation.close()

    def test_auto_load_marketplace_duplicate_names_fail(self, tmp_path: Path, mock_llm):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "auto-plugin",
                    "skills": [{"name": "auto-skill", "content": "Auto-loaded skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="duplicate",
                        source=str(marketplace_dir),
                        auto_load=True,
                    ),
                    MarketplaceRegistration(
                        name="duplicate",
                        source=str(marketplace_dir),
                        auto_load=True,
                    ),
                ]
            ),
        )
        conversation = LocalConversation(
            agent=agent, workspace=workspace, visualizer=None
        )

        try:
            with pytest.raises(ValueError, match="Duplicate marketplace registration"):
                conversation._ensure_plugins_loaded()
        finally:
            conversation.close()

    def test_registered_only_marketplace_does_not_auto_load(
        self, tmp_path: Path, mock_llm
    ):
        """测试已注册的市场，无需 auto_load 仅保留解析。"""
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "manual-plugin",
                    "skills": [{"name": "manual-skill", "content": "Manual skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ]
            ),
        )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert conversation.agent.agent_context.skills == []
        assert conversation.resolved_plugins is None

        conversation.close()

    def test_explicit_plugins_override_auto_loaded_marketplace_plugins(
        self, tmp_path: Path, mock_llm
    ):
        """在自动加载市场插件后测试显式插件加载。"""
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "auto-plugin",
                    "skills": [{"name": "shared", "content": "Auto content"}],
                }
            ],
        )
        explicit_plugin = create_test_plugin(
            tmp_path / "explicit-plugin",
            name="explicit-plugin",
            skills=[{"name": "shared", "content": "Explicit content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="auto",
                        source=str(marketplace_dir),
                        auto_load=True,
                    )
                ]
            ),
        )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(explicit_plugin))],
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skills = {s.name: s for s in conversation.agent.agent_context.skills}
        assert skills["shared"].content == "Explicit content"
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 2

        conversation.close()

    def test_registered_marketplaces_keep_public_skill_loading(self, tmp_path: Path):
        with patch(
            "openhands.sdk.context.agent_context.load_available_skills",
            return_value={},
        ) as mock_load_available_skills:
            AgentContext(
                load_public_skills=True,
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="auto",
                        source=str(tmp_path / "marketplace"),
                        auto_load=True,
                    )
                ],
            )

        mock_load_available_skills.assert_called_with(
            work_dir=None,
            include_user=False,
            include_project=False,
            include_public=True,
            marketplace_path=DEFAULT_MARKETPLACE_PATH,
        )

    def test_create_conversation_with_plugins(self, tmp_path: Path, basic_agent):
        """测试使用plugins参数创建LocalConversation。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            skills=[{"name": "test-skill", "content": "Test skill content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
        )

        # 插件是延迟加载的 - 触发加载
        conversation._ensure_plugins_loaded()

        # 智能体应该更新插件技能
        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "test-skill" in skill_names

        # 验证已解析的插件是否已被跟踪
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1
        assert conversation.resolved_plugins[0].source == str(plugin_dir)

        conversation.close()

    def test_load_plugin_from_registered_marketplace(self, tmp_path: Path, mock_llm):
        """测试从注册市场加载的运行时插件。"""
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "manual-plugin",
                    "skills": [{"name": "manual-skill", "content": "Manual skill"}],
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ]
            ),
        )
        conversation = LocalConversation(
            agent=agent, workspace=workspace, visualizer=None
        )

        conversation.load_plugin("manual-plugin@manual")

        assert conversation.agent.agent_context is not None
        skills = {
            skill.name: skill for skill in conversation.agent.agent_context.skills
        }
        assert skills["manual-skill"].content == "Manual skill"
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1

        conversation.close()

    def test_load_plugin_expands_resolved_plugin_source_secret_refs(
        self,
        tmp_path: Path,
        mock_llm,
        caplog: pytest.LogCaptureFixture,
    ):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "private-plugin",
                    "source": {
                        "source": "url",
                        "url": "https://${PLUGIN_TOKEN}@example.com/private.git",
                        "ref": "${PLUGIN_REF}",
                        "path": "plugins/private-plugin",
                    },
                    "skills": [{"name": "private-skill", "content": "Private skill"}],
                }
            ],
        )
        plugin_dir = marketplace_dir / "plugins" / "private-plugin"
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ]
            ),
        )
        conversation = LocalConversation(
            agent=agent, workspace=workspace, visualizer=None
        )
        conversation.update_secrets(
            {"PLUGIN_TOKEN": "token-value", "PLUGIN_REF": "release-branch"}
        )

        with (
            caplog.at_level(logging.INFO),
            patch(
                "openhands.sdk.conversation.impl.local_conversation."
                "fetch_plugin_with_resolution",
                return_value=(plugin_dir, "abc123"),
            ) as mock_fetch,
        ):
            conversation.load_plugin("private-plugin")

        assert "token-value" not in caplog.text
        assert "https://" not in caplog.text
        mock_fetch.assert_called_once_with(
            source="https://token-value@example.com/private.git",
            ref="release-branch",
            repo_path="plugins/private-plugin",
        )
        assert conversation.agent.agent_context is not None
        assert [skill.name for skill in conversation.agent.agent_context.skills] == [
            "private-skill"
        ]
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 1

        conversation.close()

    def test_load_plugin_adds_runtime_tools_without_reinitializing_existing_tools(
        self, tmp_path: Path, mock_llm
    ):
        mcp_tools_created = []

        class RuntimeOnlyTool(ThinkTool):
            name = "runtime_only"

        runtime_tool = RuntimeOnlyTool.create()[0]

        class RuntimeMCPClient:
            def __init__(self):
                self.tools = [runtime_tool]
                self._tools_reconciled_callback: Any = None

        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "mcp-plugin",
                    "mcp_config": {
                        "mcpServers": {"runtime-server": {"command": "runtime"}}
                    },
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ]
            ),
        )
        runtime_client = RuntimeMCPClient()
        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            visualizer=None,
            mcp_tool_provider=RecordingMCPToolProvider(
                mcp_tools_created,
                runtime_client,
                state_locked=lambda: conversation.state.locked(),
            ),
        )
        conversation._ensure_agent_ready()
        existing_tools = dict(conversation.agent.tools_map)

        conversation.load_plugin("mcp-plugin")

        for name, tool in existing_tools.items():
            assert conversation.agent.tools_map[name] is tool
        assert conversation.agent.tools_map[runtime_tool.name] is runtime_tool
        assert callable(runtime_client._tools_reconciled_callback)
        assert "runtime-server" in conversation.agent.mcp_config
        assert len(mcp_tools_created) == 1
        created_config, state_locked = mcp_tools_created[0]
        assert not state_locked
        assert "runtime-server" in created_config

        conversation.close()

    def test_load_plugin_merges_runtime_hooks_and_restarts_processor(
        self, tmp_path: Path, mock_llm
    ):
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace",
            plugins=[
                {
                    "name": "hook-plugin",
                    "hooks": {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "runtime-*",
                                    "hooks": [{"command": "runtime-cmd"}],
                                }
                            ]
                        }
                    },
                }
            ],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent = Agent(
            llm=mock_llm,
            tools=[],
            agent_context=AgentContext(
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ]
            ),
        )
        explicit_hooks = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="explicit-*", hooks=[HookDefinition(command="explicit-cmd")]
                )
            ]
        )
        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            hook_config=explicit_hooks,
            visualizer=None,
        )
        initial_processor = MagicMock()
        initial_processor.on_event = MagicMock()
        runtime_processor = MagicMock()
        runtime_processor.on_event = MagicMock()

        callback_lock_owned: list[bool] = []

        def mock_create_hook_callback(*args, **kwargs):
            callback_lock_owned.append(conversation.state._lock.owned())
            if len(callback_lock_owned) == 1:
                return initial_processor, initial_processor.on_event
            return runtime_processor, runtime_processor.on_event

        with patch(
            "openhands.sdk.conversation.impl.local_conversation.create_hook_callback",
            side_effect=mock_create_hook_callback,
        ) as mock_create_hook_callback:
            conversation.load_plugin("hook-plugin")

        assert conversation.state.hook_config is not None
        assert [
            matcher.matcher for matcher in conversation.state.hook_config.pre_tool_use
        ] == ["explicit-*", "runtime-*"]
        assert mock_create_hook_callback.call_count == 2
        assert callback_lock_owned[1]
        initial_processor.set_conversation_state.assert_called_once_with(
            conversation.state
        )
        initial_processor.run_session_start.assert_called_once()
        initial_processor.run_session_end.assert_called_once()
        runtime_processor.set_conversation_state.assert_called_once_with(
            conversation.state
        )
        runtime_processor.run_session_start.assert_called_once()

        conversation.close()

    def test_load_plugin_requires_registered_marketplaces(
        self, tmp_path: Path, basic_agent
    ):
        """测试运行时插件加载需要注册市场。"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            visualizer=None,
        )

        with pytest.raises(ValueError, match="registered_marketplaces"):
            conversation.load_plugin("missing-plugin")

        conversation.close()

    def test_conversation_with_multiple_plugins(self, tmp_path: Path, basic_agent):
        """通过 LocalConversation 测试加载多个插件。"""
        plugin1 = create_test_plugin(
            tmp_path / "plugin1",
            name="plugin1",
            skills=[{"name": "skill-a", "content": "Content A"}],
        )
        plugin2 = create_test_plugin(
            tmp_path / "plugin2",
            name="plugin2",
            skills=[{"name": "skill-b", "content": "Content B"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[
                PluginSource(source=str(plugin1)),
                PluginSource(source=str(plugin2)),
            ],
            visualizer=None,
        )

        # 插件是延迟加载的 - 触发加载
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "skill-a" in skill_names
        assert "skill-b" in skill_names

        # 验证跟踪的两个插件
        assert conversation.resolved_plugins is not None
        assert len(conversation.resolved_plugins) == 2

        conversation.close()

    def test_plugin_hooks_combined_with_explicit_hooks(
        self, tmp_path: Path, basic_agent
    ):
        """测试插件钩子是否与显式hook_config结合。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            hooks={
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "plugin-*", "hooks": [{"command": "plugin-cmd"}]}
                    ]
                }
            },
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        explicit_hooks = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="explicit-*", hooks=[HookDefinition(command="explicit-cmd")]
                )
            ]
        )

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            hook_config=explicit_hooks,
            visualizer=None,
        )

        # 钩子是延迟加载的 - 触发加载
        conversation._ensure_plugins_loaded()

        # 两个钩子源应该结合起来
        assert conversation._hook_processor is not None
        # 我们可以通过检查传递的 hook_config 来验证钩子是否已处理（实际的 hook_processor
        #  是内部的，但我们相信合并工作）
        #
        conversation.close()

    def test_hook_sub_conversations_receive_persistence_base_dir(
        self, tmp_path: Path, basic_agent
    ):
        """智能体挂钩持久化不应嵌套在父对话 ID 下。"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        persistence_base = tmp_path / "state"
        hook_config = HookConfig(
            pre_tool_use=[
                HookMatcher(matcher="*", hooks=[HookDefinition(command="echo test")])
            ]
        )

        processor = MagicMock()
        processor.on_event = MagicMock()
        processor.set_conversation_state = MagicMock()
        processor.run_session_start = MagicMock()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            persistence_dir=persistence_base,
            hook_config=hook_config,
            visualizer=None,
        )

        with patch(
            "openhands.sdk.conversation.impl.local_conversation.create_hook_callback",
            return_value=(processor, processor.on_event),
        ) as mock_create_hook_callback:
            conversation._ensure_plugins_loaded()

        assert conversation.state.persistence_dir is not None
        assert Path(conversation.state.persistence_dir).parent == persistence_base
        assert mock_create_hook_callback.call_args.kwargs["persistence_dir"] == str(
            persistence_base
        )
        conversation.close()

    def test_plugins_not_loaded_until_needed(self, tmp_path: Path, basic_agent):
        """测试插件是否未在构造函数中加载（延迟加载）。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            skills=[{"name": "test-skill", "content": "Test skill content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
        )

        # 加载之前，不应应用插件
        assert conversation._plugins_loaded is False
        assert conversation.resolved_plugins is None
        assert conversation.agent.agent_context is None

        # 触发负载后
        conversation._ensure_plugins_loaded()

        assert conversation._plugins_loaded is True
        assert conversation.resolved_plugins is not None
        assert conversation.agent.agent_context is not None

        conversation.close()

    def test_plugin_mcp_config_are_initialized(self, tmp_path: Path, basic_agent):
        """测试插件的 MCP 服务器是否已正确初始化。

        这是针对错误的回归测试，其中未创建来自插件的 MCP 工具，因为智能体在加载插件之
        前已初始化。
        """
        # 注入 MCP 提供程序以避免在测试中实际启动 MCP 服务器
        mcp_tools_created = []
        mcp_tool_provider = RecordingMCPToolProvider(mcp_tools_created)

        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            mcp_config={"mcpServers": {"test-server": {"command": "test-cmd"}}},
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
            mcp_tool_provider=mcp_tool_provider,
        )

        # 加载插件之前，不应存在 MCP 个服务器
        assert conversation.agent.mcp_config == {}

        # 触发插件加载和智能体初始化
        conversation._ensure_agent_ready()

        # 加载后，MCP台服务器应该被合并
        assert "test-server" in conversation.agent.mcp_config

        # 智能体应该已使用完整的 MCP 服务器进行初始化这验证了 create_mcp_tools 是通过插
        # 件的 MCP 服务器调用的
        #
        assert len(mcp_tools_created) > 0
        assert "test-server" in mcp_tools_created[-1]

        conversation.close()


class TestConversationFactoryPlugins:
    """通过对话工厂测试插件加载。

    Note: 插件在第一次 run()/send_message() 调用时延迟加载。
    """

    def test_factory_passes_plugins_to_local_conversation(
        self, tmp_path: Path, basic_agent
    ):
        """测试会话工厂是否将插件传递给 LocalConversation。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            skills=[{"name": "factory-skill", "content": "Factory skill content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = Conversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
        )

        assert isinstance(conversation, LocalConversation)

        # 插件是延迟加载的 - 触发加载
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "factory-skill" in skill_names
        conversation.close()

    def test_factory_with_string_workspace_and_plugins(
        self, tmp_path: Path, basic_agent
    ):
        """使用字符串工作区路径和插件测试工厂。"""
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="plugin",
            skills=[{"name": "skill", "content": "Content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = Conversation(
            agent=basic_agent,
            workspace=str(workspace),
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
        )

        # 插件是延迟加载的 - 触发加载
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        assert len(conversation.agent.agent_context.skills) == 1
        conversation.close()

    def test_factory_with_no_plugins(self, tmp_path: Path, basic_agent):
        """测试工厂在没有插件的情况下是否可以工作（默认为plugins=None）。"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = Conversation(
            agent=basic_agent,
            workspace=workspace,
            visualizer=None,
        )

        # 应该可以正常工作而不会出现错误
        assert conversation is not None
        conversation.close()


class TestPluginMcpSecretsExpansion:
    """测试 MCP 配置扩展中的每个会话机密。

    这些测试验证通过 REST API 注入的机密是否正确用于 MCP 配置变量扩展（${VAR} 语法）
    。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2872
    """

    def test_plugin_mcp_secrets_without_defaults(self, tmp_path: Path, basic_agent):
        """测试每个对话机密是否适用于没有默认值的变量。

        此测试验证 ${VAR} 占位符（无默认值）是否使用 SecretRegistry 中的机密正确扩展
        。
        """
        # 注入 MCP 提供程序以避免实际启动 MCP 服务器
        mcp_tools_created = []
        mcp_tool_provider = RecordingMCPToolProvider(mcp_tools_created)

        # 使用 ${VAR} WITHOUT 默认值创建具有 MCP 配置的插件
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            mcp_config={
                "mcpServers": {
                    "test-server": {
                        "url": "https://example.com/mcp",
                        "headers": {"Authorization": "Bearer ${SECRET_TOKEN}"},
                    }
                }
            },
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
            mcp_tool_provider=mcp_tool_provider,
        )

        # Inject 机密之前触发插件加载
        conversation.update_secrets({"SECRET_TOKEN": "my-actual-secret"})

        # 触发插件加载和智能体初始化
        conversation._ensure_agent_ready()

        # 验证机密已在 MCP 服务器中扩展
        headers = dump_mcp_config(conversation.agent.mcp_config)["test-server"][
            "headers"
        ]
        assert isinstance(headers, dict)
        auth_header = headers["Authorization"]
        assert auth_header == "Bearer my-actual-secret", (
            f"Expected 'Bearer my-actual-secret', got '{auth_header}'"
        )

        conversation.close()

    def test_plugin_mcp_secrets_with_defaults(self, tmp_path: Path, basic_agent):
        """测试每个对话机密是否使用默认值。

        此测试验证 ${VAR:-default} 占位符是否使用机密值（如果可用），不为默认值。

        这是针对双展开错误的回归测试，其中：
        1. plugin.py 中的第一次扩展将 ${VAR:-default} 替换为“默认”
        2. local_conversation.py 中的第二次扩展没有看到要扩展的占位符

        Expected: 应使用机密值，而不是默认值。
        """
        # 注入 MCP 提供程序以避免实际启动 MCP 服务器
        mcp_tools_created = []
        mcp_tool_provider = RecordingMCPToolProvider(mcp_tools_created)

        # 使用 ${VAR:-default} WITH 默认值创建具有 MCP 配置的插件
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            mcp_config={
                "mcpServers": {
                    "test-server": {
                        "url": "https://example.com/mcp",
                        "headers": {
                            "Authorization": "Bearer ${SECRET_TOKEN:-fallback-token}"
                        },
                    }
                }
            },
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
            mcp_tool_provider=mcp_tool_provider,
        )

        # Inject 机密之前触发插件加载
        conversation.update_secrets({"SECRET_TOKEN": "my-actual-secret"})

        # 触发插件加载和智能体初始化
        conversation._ensure_agent_ready()

        # CRITICAL：验证是否使用了机密，不为默认值
        headers = dump_mcp_config(conversation.agent.mcp_config)["test-server"][
            "headers"
        ]
        assert isinstance(headers, dict)
        auth_header = headers["Authorization"]

        # 此断言将 FAIL 带有双展开错误
        assert auth_header == "Bearer my-actual-secret", (
            f"Expected secret value 'Bearer my-actual-secret', got '{auth_header}'. "
            "This is likely due to double-expansion: the default value was applied "
            "during plugin loading before secrets were available."
        )

        conversation.close()

    def test_plugin_mcp_secrets_fallback_to_default_when_no_secret(
        self, tmp_path: Path, basic_agent
    ):
        """测试未提供机密时默认值是否有效。

        此测试验证当没有注入机密时，${VAR:-default} 是否正确回退到默认值。
        """
        # 注入 MCP 提供程序以避免实际启动 MCP 服务器
        mcp_tools_created = []
        mcp_tool_provider = RecordingMCPToolProvider(mcp_tools_created)

        # 使用 ${VAR:-default} 创建具有 MCP 配置的插件
        # 注意：MCP 配置结构需要有效字段，因此我们使用“headers”
        # 对于字符串值而不是需要整数的“超时”
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            mcp_config={
                "mcpServers": {
                    "test-server": {
                        "url": "${API_URL:-https://default.example.com/mcp}",
                        "headers": {
                            "X-Custom-Header": "${CUSTOM_HEADER:-default-header-value}"
                        },
                    }
                }
            },
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
            mcp_tool_provider=mcp_tool_provider,
        )

        # 执行不注入任何机密 - 应使用默认值

        # 触发插件加载和智能体初始化
        conversation._ensure_agent_ready()

        # 验证是否使用了默认值
        mcp_config = dump_mcp_config(conversation.agent.mcp_config)
        url = mcp_config["test-server"]["url"]
        headers = mcp_config["test-server"]["headers"]
        assert isinstance(headers, dict)
        header = headers["X-Custom-Header"]

        assert url == "https://default.example.com/mcp"
        assert header == "default-header-value"

        conversation.close()


class TestPluginSourceSecretExpansion:
    """插件 ``source``/``ref`` 中的机密在获取之前展开。

    这使得可以使用通过每个会话机密 API、e.g 提供的 token 来克隆私有插件存储库。 的
    ``source``
    ``https://x-token-auth:${MY_TOKEN}@host/org/repo.git``.
    """

    def _make_conversation(
        self, tmp_path: Path, basic_agent, plugin_source: str, ref: str | None = None
    ):
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="private-plugin",
            skills=[{"name": "private-skill", "content": "Private content"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=plugin_source, ref=ref)],
            visualizer=None,
        )
        return conversation, plugin_dir

    def test_source_secret_expanded_before_fetch(self, tmp_path: Path, basic_agent):
        """源中的 ${VAR} 在克隆之前被替换为机密值。"""
        source = "https://x-token-auth:${MY_TOKEN}@host.example.com/org/repo.git"
        conversation, plugin_dir = self._make_conversation(
            tmp_path, basic_agent, source
        )
        conversation.update_secrets({"MY_TOKEN": "s3cr3t-value"})

        captured: dict[str, str | None] = {}

        def fake_fetch(source, ref=None, repo_path=None, **kwargs):
            captured["source"] = source
            captured["ref"] = ref
            return plugin_dir, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        with patch(
            "openhands.sdk.conversation.impl.local_conversation."
            "fetch_plugin_with_resolution",
            side_effect=fake_fetch,
        ):
            conversation._ensure_plugins_loaded()

        # 机密在传递给获取器的 URL 中展开。
        assert captured["source"] == (
            "https://x-token-auth:s3cr3t-value@host.example.com/org/repo.git"
        )

        # 已持久化状态必须不包含原始机密值。
        assert conversation.resolved_plugins is not None
        assert "s3cr3t-value" not in conversation.resolved_plugins[0].source

        conversation.close()

    def test_host_env_not_expanded_in_source(
        self, tmp_path: Path, basic_agent, monkeypatch
    ):
        """主机环境变量必须不折叠到源 URL 中。"""
        monkeypatch.setenv("HOST_ONLY_VAR", "host-value")
        source = "https://x-token-auth:${HOST_ONLY_VAR}@host.example.com/org/repo.git"
        conversation, plugin_dir = self._make_conversation(
            tmp_path, basic_agent, source
        )
        # 故意注册名为HOST_ONLY_VAR的NO机密。

        captured: dict[str, str | None] = {}

        def fake_fetch(source, ref=None, repo_path=None, **kwargs):
            captured["source"] = source
            return plugin_dir, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        with patch(
            "openhands.sdk.conversation.impl.local_conversation."
            "fetch_plugin_with_resolution",
            side_effect=fake_fetch,
        ):
            conversation._ensure_plugins_loaded()

        # 逐字保留的占位符 - 未使用主机 env。
        assert captured["source"] == source
        assert "host-value" not in (captured["source"] or "")

        conversation.close()

    def test_unknown_var_with_default_left_untouched(self, tmp_path: Path, basic_agent):
        """`${MISSING:-default}` 逐字保留 (expand_defaults=False)。

        在 URL 中未解决的变量必须不被无声地替换为默认值 -- 保留占位符以使失败可见，而
        不是产生一个看似合理但错误的 URL。
        """
        source = "https://x-token-auth:${MISSING:-fallback}@host.example.com/o/r.git"
        conversation, plugin_dir = self._make_conversation(
            tmp_path, basic_agent, source
        )
        # 未注册名为 MISSING 的机密。

        captured: dict[str, str | None] = {}

        def fake_fetch(source, ref=None, repo_path=None, **kwargs):
            captured["source"] = source
            return plugin_dir, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        with patch(
            "openhands.sdk.conversation.impl.local_conversation."
            "fetch_plugin_with_resolution",
            side_effect=fake_fetch,
        ):
            conversation._ensure_plugins_loaded()

        # 逐字保留占位符：默认将不替换进去，整个 ${MISSING:-fallback} token 保持不变。
        #
        assert captured["source"] == source
        assert "${MISSING:-fallback}" in (captured["source"] or "")

        conversation.close()

    def test_ref_secret_expanded_before_fetch(self, tmp_path: Path, basic_agent):
        """ref 中的 ${VAR} 也是从机密扩展而来。"""
        source = str(tmp_path / "plugin")
        conversation, plugin_dir = self._make_conversation(
            tmp_path, basic_agent, source, ref="${MY_REF}"
        )
        conversation.update_secrets({"MY_REF": "v1.2.3"})

        captured: dict[str, str | None] = {}

        def fake_fetch(source, ref=None, repo_path=None, **kwargs):
            captured["ref"] = ref
            return plugin_dir, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        with patch(
            "openhands.sdk.conversation.impl.local_conversation."
            "fetch_plugin_with_resolution",
            side_effect=fake_fetch,
        ):
            conversation._ensure_plugins_loaded()

        assert captured["ref"] == "v1.2.3"

        conversation.close()


class TestAmbientPluginAutoLoad:
    """环境自动加载：启用已安装+本地插件加载到
    沿着显式附加路径（和下方）进行对话。
    """

    def _isolate(self, monkeypatch, user_dirs: list[Path], install_store: Path):
        """将发现指向测试目录而不是真正的主目录。"""
        monkeypatch.setattr(discovery, "USER_PLUGINS_DIRS", user_dirs)
        monkeypatch.setattr(installed, "DEFAULT_INSTALLED_PLUGINS_DIR", install_store)

    def test_enabled_installed_plugin_auto_loads_into_conversation(
        self, tmp_path: Path, basic_agent, monkeypatch
    ):
        """已安装并启用的插件无需显式附加即可加载。

        该插件仅贡献一项技能（无 MCP/无明确规格），因此这也涵盖了仅技能环境插件仍然更
        新智能体。
        """
        install_store = tmp_path / "installed-store"
        install_store.mkdir()
        source = create_test_plugin(
            tmp_path / "src",
            name="ambient-plugin",
            skills=[{"name": "ambient-skill", "content": "Ambient content"}],
        )
        install_plugin(str(source), installed_dir=install_store)
        self._isolate(monkeypatch, [tmp_path / "empty-user"], install_store)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent, workspace=workspace, visualizer=None
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "ambient-skill" in skill_names
        conversation.close()

    def test_explicitly_attached_plugin_overrides_ambient_plugin(
        self, tmp_path: Path, basic_agent, monkeypatch
    ):
        """一个同名的显式插件获胜； 环境音被完全跳过。"""
        user_dir = tmp_path / ".agents" / "plugins"
        create_test_plugin(
            user_dir / "shared",
            name="shared",
            skills=[{"name": "ambient-skill", "content": "Ambient"}],
        )
        explicit_src = create_test_plugin(
            tmp_path / "explicit",
            name="shared",
            skills=[{"name": "explicit-skill", "content": "Explicit"}],
        )
        install_store = tmp_path / "installed-store"
        install_store.mkdir()
        self._isolate(monkeypatch, [user_dir], install_store)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(explicit_src))],
            visualizer=None,
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "explicit-skill" in skill_names
        assert "ambient-skill" not in skill_names
        conversation.close()

    def test_ambient_plugins_are_not_recorded_in_resolved_plugins(
        self, tmp_path: Path, basic_agent, monkeypatch
    ):
        """环境插件加载但未固定（恢复重新发现它们）。"""
        user_dir = tmp_path / ".agents" / "plugins"
        create_test_plugin(
            user_dir / "ambient",
            name="ambient-plugin",
            skills=[{"name": "ambient-skill", "content": "Ambient"}],
        )
        install_store = tmp_path / "installed-store"
        install_store.mkdir()
        self._isolate(monkeypatch, [user_dir], install_store)
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent, workspace=workspace, visualizer=None
        )
        conversation._ensure_plugins_loaded()

        assert conversation.agent.agent_context is not None
        skill_names = [s.name for s in conversation.agent.agent_context.skills]
        assert "ambient-skill" in skill_names
        assert conversation.resolved_plugins is None
        conversation.close()

    def test_plugin_load_log_never_leaks_credentials(
        self, tmp_path: Path, basic_agent, caplog: pytest.LogCaptureFixture
    ):
        """插件加载日志绝不能包含源凭据。 A 序列化器
        涵盖模型转储，而不是 f 字符串日志行，因此这可以防止任何人将 spec.source 重新
        添加到该日志（问题＃3752）。
        """
        plugin_dir = create_test_plugin(
            tmp_path / "plugin",
            name="test-plugin",
            skills=[{"name": "s", "content": "c"}],
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[
                PluginSource(source="https://oauth2:LEAKME@host.example.com/o/r.git")
            ],
            visualizer=None,
        )
        with (
            caplog.at_level(logging.DEBUG),
            patch(
                "openhands.sdk.conversation.impl.local_conversation."
                "fetch_plugin_with_resolution",
                return_value=(plugin_dir, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
            ),
        ):
            conversation._ensure_plugins_loaded()

        assert "LEAKME" not in caplog.text
        conversation.close()


class TestAgentPluginsMCPExpansion:
    """智能体 Plugins 包带来了自己的、已经完成的扩展。

    对话级别通道根据环境和每个对话机密扩展 ``${VAR}``。 该标准允许使用两个占位符并禁
    止其他所有内容，因此这些服务器必须保持不变。
    """

    def test_package_values_are_not_expanded_again(
        self, tmp_path: Path, basic_agent, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR",
            tmp_path / "plugin-data",
        )
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "$schema": (
                        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
                    ),
                    "name": "portable",
                    "version": "1.0.0",
                    "description": "An Agent Plugins package.",
                }
            )
        )
        (plugin_dir / "mcp.json").write_text(
            json.dumps(
                {
                    "$schema": (
                        "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
                    ),
                    "mcpServers": {
                        "portable-server": {
                            "type": "stdio",
                            "command": "echo",
                            "args": ["${SECRET_TOKEN}", "${MISSING:-fallback}"],
                        }
                    },
                }
            )
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        conversation = LocalConversation(
            agent=basic_agent,
            workspace=workspace,
            plugins=[PluginSource(source=str(plugin_dir))],
            visualizer=None,
            mcp_tool_provider=RecordingMCPToolProvider([]),
        )
        conversation.update_secrets({"SECRET_TOKEN": "my-actual-secret"})
        conversation._ensure_agent_ready()

        server = conversation.agent.mcp_config["portable-server"]
        assert server.args == ["${SECRET_TOKEN}", "${MISSING:-fallback}"]
        assert server.literal_values
        conversation.close()

    def test_load_plugin_does_not_expand_package_servers(
        self, tmp_path: Path, mock_llm, monkeypatch: pytest.MonkeyPatch
    ):
        """load_plugin() 扩展两次——运行时服务器和合并的服务器
        config - 并且两者都必须留下智能体 Plugins 包文字。"""
        monkeypatch.setattr(
            "openhands.sdk.plugin.format.agent_plugins_mcp.DEFAULT_PLUGIN_DATA_DIR",
            tmp_path / "plugin-data",
        )
        monkeypatch.setenv("LEAKED", "from-environment")
        marketplace_dir = create_test_marketplace(
            tmp_path / "marketplace", plugins=[{"name": "portable"}]
        )
        package = marketplace_dir / "plugins" / "portable"
        (package / ".plugin" / "plugin.json").unlink()
        (package / ".plugin").rmdir()
        (package / "plugin.json").write_text(
            json.dumps(
                {
                    "$schema": (
                        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
                    ),
                    "name": "portable",
                    "version": "1.0.0",
                    "description": "An Agent Plugins package.",
                }
            )
        )
        literal_args = ["${SECRET_TOKEN}", "${LEAKED}", "${MISSING:-fallback}"]
        (package / "mcp.json").write_text(
            json.dumps(
                {
                    "$schema": (
                        "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
                    ),
                    "mcpServers": {
                        "portable-server": {
                            "type": "stdio",
                            "command": "echo",
                            "args": literal_args,
                        }
                    },
                }
            )
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        mcp_tools_created: list[Any] = []
        conversation = LocalConversation(
            agent=Agent(
                llm=mock_llm,
                tools=[],
                agent_context=AgentContext(
                    registered_marketplaces=[
                        MarketplaceRegistration(
                            name="manual", source=str(marketplace_dir)
                        )
                    ]
                ),
            ),
            workspace=workspace,
            visualizer=None,
            mcp_tool_provider=RecordingMCPToolProvider(mcp_tools_created),
        )
        conversation.update_secrets({"SECRET_TOKEN": "my-actual-secret"})
        conversation._ensure_agent_ready()

        conversation.load_plugin("portable")

        merged = conversation.agent.mcp_config["portable-server"]
        assert merged.args == literal_args
        assert mcp_tools_created[-1]["portable-server"].args == literal_args
        conversation.close()
