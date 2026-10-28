"""测试 OpenHandsCloudWorkspace 自动化标签功能。"""

import json
import os
from unittest.mock import patch

import pytest


class TestDefaultConversationTags:
    """测试 default_conversation_tags 属性。"""

    @pytest.fixture
    def workspace(self):
        """使用模拟的沙箱创建创建工作区实例。"""
        from openhands.workspace import OpenHandsCloudWorkspace

        with patch.object(OpenHandsCloudWorkspace, "_start_sandbox"):
            workspace = OpenHandsCloudWorkspace(
                cloud_api_url="https://cloud.example.com",
                cloud_api_key="test-api-key",
            )
            # 设置最小状态
            workspace._sandbox_id = "sandbox-123"
            workspace._session_api_key = "session-key"
            workspace.host = "https://agent.example.com"
            yield workspace
            workspace._sandbox_id = None
            workspace.cleanup()

    def test_empty_tags_when_no_env_vars(self, workspace):
        """当未设置自动化环境变量时，应返回空字典。"""
        with patch.dict(os.environ, {}, clear=True):
            # 清除任何现有的环境变量
            os.environ.pop("AUTOMATION_EVENT_PAYLOAD", None)
            os.environ.pop("AUTOMATION_RUN_ID", None)
            workspace._automation_run_id = None

            tags = workspace.default_conversation_tags
            assert tags == {}

    def test_parses_trigger_from_payload(self, workspace):
        """应从 AUTOMATION_EVENT_PAYLOAD 中提取自动化触发器。"""
        payload = {"trigger": "cron"}
        with patch.dict(os.environ, {"AUTOMATION_EVENT_PAYLOAD": json.dumps(payload)}):
            tags = workspace.default_conversation_tags
            assert tags["automationtrigger"] == "cron"

    def test_parses_automation_id_from_payload(self, workspace):
        """应该从AUTOMATION_EVENT_PAYLOAD中提取automationid。"""
        payload = {"automation_id": "auto-123"}
        with patch.dict(os.environ, {"AUTOMATION_EVENT_PAYLOAD": json.dumps(payload)}):
            tags = workspace.default_conversation_tags
            assert tags["automationid"] == "auto-123"

    def test_parses_automation_name_from_payload(self, workspace):
        """应从 AUTOMATION_EVENT_PAYLOAD 中提取自动化名称。"""
        payload = {"automation_name": "Daily Report"}
        with patch.dict(os.environ, {"AUTOMATION_EVENT_PAYLOAD": json.dumps(payload)}):
            tags = workspace.default_conversation_tags
            assert tags["automationname"] == "Daily Report"

    def test_parses_run_id_from_env_var(self, workspace):
        """应从 AUTOMATION_RUN_ID 环境变量中提取 runid。"""
        with patch.dict(os.environ, {"AUTOMATION_RUN_ID": "run-456"}):
            workspace._automation_run_id = None
            tags = workspace.default_conversation_tags
            assert tags["automationrunid"] == "run-456"

    def test_prefers_env_var_run_id_over_private_attr(self, workspace):
        """应该更喜欢 AUTOMATION_RUN_ID 环境变量而不是 _automation_run_id。"""
        with patch.dict(os.environ, {"AUTOMATION_RUN_ID": "env-run-id"}):
            workspace._automation_run_id = "attr-run-id"
            tags = workspace.default_conversation_tags
            assert tags["automationrunid"] == "env-run-id"

    def test_uses_private_attr_run_id_when_no_env_var(self, workspace):
        """当环境变量未设置时应使用 _automation_run_id。"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AUTOMATION_RUN_ID", None)
            workspace._automation_run_id = "attr-run-id"
            tags = workspace.default_conversation_tags
            assert tags["automationrunid"] == "attr-run-id"

    def test_handles_invalid_json_payload(self, workspace):
        """应该优雅地处理 AUTOMATION_EVENT_PAYLOAD 中无效的 JSON。"""
        with patch.dict(os.environ, {"AUTOMATION_EVENT_PAYLOAD": "not-valid-json"}):
            # 不应该引发，只返回空标签
            tags = workspace.default_conversation_tags
            assert "trigger" not in tags

    def test_handles_non_dict_json_payload(self, workspace):
        """应该优雅地处理非 dict JSON 载荷。"""
        with patch.dict(os.environ, {"AUTOMATION_EVENT_PAYLOAD": '"just a string"'}):
            # 不应该提高
            tags = workspace.default_conversation_tags
            # 可能会在 .get() 上引发 AttributeError 字符串，确保优雅的处理
            assert isinstance(tags, dict)

    def test_parses_full_payload(self, workspace):
        """应该解析完整的载荷中的所有字段。"""
        payload = {
            "trigger": "webhook",
            "automation_id": "auto-abc",
            "automation_name": "PR Review Bot",
        }
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_EVENT_PAYLOAD": json.dumps(payload),
                "AUTOMATION_RUN_ID": "run-xyz",
            },
        ):
            tags = workspace.default_conversation_tags
            assert tags["automationtrigger"] == "webhook"
            assert tags["automationid"] == "auto-abc"
            assert tags["automationname"] == "PR Review Bot"
            assert tags["automationrunid"] == "run-xyz"
            # 技能不包含在工作区标签中
            assert "skills" not in tags


class TestRemoteWorkspaceDefaultConversationTags:
    """基于 RemoteWorkspace 的自动化标签测试。

    本地模式自动化运行使用普通的 RemoteWorkspace 与本地 Agent Server 相对应，因此基类
    本身必须派生自动化标签
    from the dispatcher-injected env vars (the derivation edge cases are
    上面通过 OpenHandsCloudWorkspace 子类进行了介绍，该子类继承了此实现）。
    """

    @pytest.fixture
    def workspace(self):
        """创建一个普通的 RemoteWorkspace（构造时不发出任何请求）。"""
        from openhands.sdk.workspace import RemoteWorkspace

        return RemoteWorkspace(host="http://localhost:1", working_dir="/tmp")

    def test_empty_tags_when_no_env_vars(self, workspace):
        """当未设置自动化环境变量时，应返回空字典。"""
        with patch.dict(os.environ, {}, clear=True):
            assert workspace.default_conversation_tags == {}

    def test_derives_automation_tags_from_env_vars(self, workspace):
        """应标记调度程序环境变量中的所有四个自动化标签。"""
        payload = {
            "trigger": "cron",
            "automation_id": "auto-abc",
            "automation_name": "Nightly Audit",
        }
        with patch.dict(
            os.environ,
            {
                "AUTOMATION_EVENT_PAYLOAD": json.dumps(payload),
                "AUTOMATION_RUN_ID": "run-xyz",
            },
        ):
            assert workspace.default_conversation_tags == {
                "automationtrigger": "cron",
                "automationid": "auto-abc",
                "automationname": "Nightly Audit",
                "automationrunid": "run-xyz",
            }


class TestConversationTagMerging:
    """在对话工厂中测试自动标签合并。"""

    def test_merges_default_tags_with_user_tags(self):
        """用户标签应覆盖工作区个默认标签。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.workspace import RemoteWorkspace

        # 使用 default_conversation_tags 创建模拟对象工作区
        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {
            "automationtrigger": "cron",
            "automationid": "auto-123",
        }

        # 模拟对象 RemoteConversation 在 impl 模块级别（从哪里导入）
        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            # 使用覆盖某些默认值的用户标签创建
            user_tags = {"automationtrigger": "manual", "custom": "value"}

            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                tags=user_tags,
            )

            # 检查传递给RemoteConversation的标签
            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            # 用户的“触发器”应覆盖工作区的“触发器”
            assert effective_tags["automationtrigger"] == "manual"
            # 应保留工作区的automationid
            assert effective_tags["automationid"] == "auto-123"
            # 应包含用户的自定义标签
            assert effective_tags["custom"] == "value"

    def test_uses_only_default_tags_when_no_user_tags(self):
        """当用户提供 None 时，应使用工作区默认标签。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {
            "automationtrigger": "cron",
            "automationid": "auto-123",
        }

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                tags=None,
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            assert effective_tags["automationtrigger"] == "cron"
            assert effective_tags["automationid"] == "auto-123"

    def test_no_merge_when_workspace_returns_none_for_default_tags(self):
        """当默认标签的工作区返回 None 时不应合并。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.workspace import RemoteWorkspace

        # 创建模拟对象，default_conversation_tags 返回 None
        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = None

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            user_tags = {"custom": "value"}
            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                tags=user_tags,
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            # 应该只使用用户标签
            assert effective_tags == {"custom": "value"}

    def test_no_merge_when_default_tags_empty(self):
        """当工作区返回空默认标签时不应合并。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {}

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            user_tags = {"custom": "value"}
            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                tags=user_tags,
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            # 当默认标签为空时，effective_tags应该是user_tags
            assert call_kwargs["tags"] == user_tags


class TestPluginSourceUrl:
    """测试 PluginSource.source_url 属性。"""

    def test_github_shorthand_basic(self):
        """应该将 GitHub:owner/repo 转换为完整的 URL。"""
        from openhands.sdk.plugin import PluginSource

        plugin = PluginSource(source="github:OpenHands/skills")
        assert plugin.source_url == "https://github.com/OpenHands/skills"

    def test_github_shorthand_with_ref(self):
        """应该为 GitHub 添加树/引用：带有引用的源。"""
        from openhands.sdk.plugin import PluginSource

        plugin = PluginSource(source="github:OpenHands/skills", ref="v1.0.0")
        assert plugin.source_url == "https://github.com/OpenHands/skills/tree/v1.0.0"

    def test_github_shorthand_with_repo_path(self):
        """应为 GitHub 添加树/主/路径：带有 repo_path 的源。"""
        from openhands.sdk.plugin import PluginSource

        plugin = PluginSource(
            source="github:OpenHands/monorepo", repo_path="plugins/security"
        )
        assert (
            plugin.source_url
            == "https://github.com/OpenHands/monorepo/tree/main/plugins/security"
        )

    def test_github_shorthand_with_ref_and_path(self):
        """应在 URL 中包含引用和路径。"""
        from openhands.sdk.plugin import PluginSource

        plugin = PluginSource(
            source="github:OpenHands/monorepo",
            ref="feature-branch",
            repo_path="plugins/security",
        )
        assert (
            plugin.source_url
            == "https://github.com/OpenHands/monorepo/tree/feature-branch/plugins/security"
        )

    def test_urls_returned_as_is(self):
        """应原样返回 URLs。"""
        from openhands.sdk.plugin import PluginSource

        # 已满 GitHub URL
        plugin = PluginSource(source="https://github.com/OpenHands/skills")
        assert plugin.source_url == "https://github.com/OpenHands/skills"

        # GitHub 斑点 URL
        plugin = PluginSource(
            source="https://github.com/OpenHands/skills/blob/main/SKILL.md"
        )
        assert (
            plugin.source_url
            == "https://github.com/OpenHands/skills/blob/main/SKILL.md"
        )

        # GitLab URL（按原样返回，不附加引用）
        plugin = PluginSource(source="https://gitlab.com/owner/repo", ref="v2.0.0")
        assert plugin.source_url == "https://gitlab.com/owner/repo"

        # Bitbucket URL（按原样返回）
        plugin = PluginSource(source="https://bitbucket.org/owner/repo", ref="v1.0.0")
        assert plugin.source_url == "https://bitbucket.org/owner/repo"

        # 其他 git URLs
        plugin = PluginSource(source="https://git.example.com/repo.git", ref="v1.0")
        assert plugin.source_url == "https://git.example.com/repo.git"

        # git URLs
        plugin = PluginSource(source="git@github.com:owner/repo.git")
        assert plugin.source_url == "git@github.com:owner/repo.git"

    def test_local_path_returns_none(self):
        """对于本地路径应返回 None（不可移植）。"""
        from openhands.sdk.plugin import PluginSource

        for path in ["/absolute/path", "./relative", "../parent", "~/home"]:
            plugin = PluginSource(source=path)
            assert plugin.source_url is None, f"Expected None for {path}"


class TestPluginsTagInConversation:
    """在对话工厂中测试自动插件标签生成。"""

    def test_plugins_added_as_urls_in_tags(self):
        """应该序列化插件到 URLs 在标签中。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.plugin import PluginSource
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {}

        plugins = [
            PluginSource(source="github:OpenHands/security-skill", ref="v1.0.0"),
            PluginSource(source="github:OpenHands/review-skill"),
        ]

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                plugins=plugins,
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            assert "plugins" in effective_tags
            plugin_urls = effective_tags["plugins"].split(",")
            assert len(plugin_urls) == 2
            assert (
                "https://github.com/OpenHands/security-skill/tree/v1.0.0" in plugin_urls
            )
            assert "https://github.com/OpenHands/review-skill" in plugin_urls

    def test_credentials_redacted_in_plugins_tag(self):
        """内联信用不得到达已持久化插件标签； ${VAR} 幸存下来。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.plugin import PluginSource
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {}

        plugins = [
            PluginSource(source="https://oauth2:SUPER_SECRET@github.com/org/repo.git"),
            PluginSource(source="https://x-token-auth:${MY_TOKEN}@host/org/ext.git"),
        ]
        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()
            Conversation(agent=MagicMock(), workspace=mock_workspace, plugins=plugins)
            tag = mock_convo_class.call_args.kwargs["tags"]["plugins"]

        assert "SUPER_SECRET" not in tag
        assert "https://****@github.com/org/repo.git" in tag.split(",")
        assert "https://x-token-auth:${MY_TOKEN}@host/org/ext.git" in tag.split(",")

    def test_local_plugins_not_included_in_tags(self):
        """标签中不应包含本地路径插件。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.plugin import PluginSource
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {}

        plugins = [
            PluginSource(source="github:OpenHands/skill"),
            PluginSource(source="/local/path/to/plugin"),  # 应该跳过
        ]

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                plugins=plugins,
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            # 应该只有一个插件（GitHub 那个）
            assert effective_tags["plugins"] == "https://github.com/OpenHands/skill"

    def test_plugins_tag_merges_with_other_tags(self):
        """插件标签应与工作区和用户标签合并。"""
        from unittest.mock import MagicMock

        from openhands.sdk.conversation.conversation import Conversation
        from openhands.sdk.plugin import PluginSource
        from openhands.sdk.workspace import RemoteWorkspace

        mock_workspace = MagicMock(spec=RemoteWorkspace)
        mock_workspace.default_conversation_tags = {
            "automationtrigger": "webhook",
            "automationid": "auto-123",
        }

        plugins = [PluginSource(source="github:OpenHands/skill")]

        with patch(
            "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
        ) as mock_convo_class:
            mock_convo_class.return_value = MagicMock()

            Conversation(
                agent=MagicMock(),
                workspace=mock_workspace,
                plugins=plugins,
                tags={"custom": "value"},
            )

            call_kwargs = mock_convo_class.call_args.kwargs
            effective_tags = call_kwargs["tags"]

            # 所有标签都应该存在
            assert effective_tags["automationtrigger"] == "webhook"
            assert effective_tags["automationid"] == "auto-123"
            assert effective_tags["plugins"] == "https://github.com/OpenHands/skill"
            assert effective_tags["custom"] == "value"
