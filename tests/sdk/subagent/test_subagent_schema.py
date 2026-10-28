from pathlib import Path

import pytest
from pydantic import ValidationError

from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.mcp.config import MCPServer, dump_mcp_config
from openhands.sdk.subagent.schema import (
    AgentDefinition,
    _extract_examples,
)


class TestAgentDefinition:
    """测试 AgentDefinition 加载。"""

    def test_load_agent_basic(self, tmp_path: Path):
        """测试加载基本的智能体定义。"""
        agent_md = tmp_path / "test-agent.md"
        agent_md.write_text(
            """---
name: test-agent
description: A test agent
model: gpt-4
tools:
  - Read
  - Write
---

You are a test agent.
"""
        )

        agent = AgentDefinition.load(agent_md)

        assert agent.name == "test-agent"
        assert agent.description == "A test agent"
        assert agent.model == "gpt-4"
        assert agent.tools == ["Read", "Write"]
        assert agent.system_prompt == "You are a test agent."

    def test_load_agent_with_examples(self, tmp_path: Path):
        """使用 when_to_use 个示例测试加载智能体。"""
        agent_md = tmp_path / "helper.md"
        agent_md.write_text(
            """---
name: helper
description: A helper. <example>When user needs help</example>
---

Help the user.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert len(agent.when_to_use_examples) == 1
        assert "When user needs help" in agent.when_to_use_examples[0]

    def test_load_agent_with_color(self, tmp_path: Path):
        """测试用颜色加载智能体。"""
        agent_md = tmp_path / "colored.md"
        agent_md.write_text(
            """---
name: colored
color: blue
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.color == "blue"

    def test_load_agent_with_tools_as_string(self, tmp_path: Path):
        """使用工具作为单个字符串测试加载智能体。"""
        agent_md = tmp_path / "single-tool.md"
        agent_md.write_text(
            """---
name: single-tool
tools: Read
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.tools == ["Read"]

    def test_load_agent_defaults(self, tmp_path: Path):
        """当未提供字段时，测试智能体默认值。"""
        agent_md = tmp_path / "minimal.md"
        agent_md.write_text(
            """---
---

Just content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.name == "minimal"  # 从文件名
        assert agent.model == "inherit"
        assert agent.tools == []

    def test_load_agent_with_max_iteration_per_run(self, tmp_path: Path):
        """使用 max_iteration_per_run 测试加载智能体。"""
        agent_md = tmp_path / "limited.md"
        agent_md.write_text(
            """---
name: limited
max_iteration_per_run: 10
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.max_iteration_per_run == 10

    def test_load_agent_without_max_iteration_per_run(self, tmp_path: Path):
        """测试当省略时 max_iteration_per_run 默认为 None。"""
        agent_md = tmp_path / "default.md"
        agent_md.write_text(
            """---
name: default-iter
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.max_iteration_per_run is None

    def test_max_iteration_per_run_not_in_metadata(self, tmp_path: Path):
        """测试 max_iteration_per_run 不会泄漏到元数据中。"""
        agent_md = tmp_path / "meta-check.md"
        agent_md.write_text(
            """---
name: meta-check
max_iteration_per_run: 5
custom_field: value
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert "max_iteration_per_run" not in agent.metadata
        assert agent.metadata.get("custom_field") == "value"

    def test_max_iteration_per_run_zero_raises(self):
        """max_iteration_per_run=0 should fail Pydantic validation."""
        with pytest.raises(ValidationError):
            AgentDefinition(name="bad", max_iteration_per_run=0)

    def test_max_iteration_per_run_negative_raises(self):
        """否定 max_iteration_per_run 应该失败 Pydantic 验证。"""
        with pytest.raises(ValidationError):
            AgentDefinition(name="bad", max_iteration_per_run=-1)

    def test_load_agent_with_metadata(self, tmp_path: Path):
        """使用额外元数据测试加载智能体。"""
        agent_md = tmp_path / "meta.md"
        agent_md.write_text(
            """---
name: meta-agent
custom_field: custom_value
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.metadata.get("custom_field") == "custom_value"

    def test_load_agent_with_hooks(self, tmp_path: Path):
        """使用钩子配置测试加载智能体。"""
        agent_md = tmp_path / "hooked.md"
        agent_md.write_text(
            """---
name: hooked-agent
description: An agent with hooks
hooks:
  pre_tool_use:
    - matcher: "terminal"
      hooks:
        - command: "./scripts/validate.sh"
          timeout: 10
  post_tool_use:
    - matcher: "*"
      hooks:
        - command: "./scripts/log.sh"
---

You are a hooked agent.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.hooks is not None
        assert isinstance(agent.hooks, HookConfig)
        assert len(agent.hooks.pre_tool_use) == 1
        assert agent.hooks.pre_tool_use[0].matcher == "terminal"
        assert agent.hooks.pre_tool_use[0].hooks[0].command == "./scripts/validate.sh"
        assert agent.hooks.pre_tool_use[0].hooks[0].timeout == 10
        assert len(agent.hooks.post_tool_use) == 1
        assert agent.hooks.post_tool_use[0].matcher == "*"
        # 挂钩不应出现在元数据中
        assert "hooks" not in agent.metadata

    def test_load_agent_hooks_none_when_missing(self, tmp_path: Path):
        """测试 hooks 不在前置元数据中时默认为 None。"""
        agent_md = tmp_path / "no-hooks.md"
        agent_md.write_text(
            """---
name: no-hooks-agent
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.hooks is None

    def test_skills_default_empty(self):
        """测试技能是否默认为空列表。"""
        agent = AgentDefinition(name="no-skills")
        assert agent.skills == []

    def test_skills_as_list(self):
        """测试使用技能名称作为列表创建 AgentDefinition。"""
        agent = AgentDefinition(
            name="skilled-agent",
            skills=["code-review", "linting"],
        )
        assert agent.skills == ["code-review", "linting"]

    def test_load_skills_comma_separated(self, tmp_path: Path):
        """测试从逗号分隔的前置元数据字符串加载技巧。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: skilled-agent
skills: code-review, linting, testing
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.skills == ["code-review", "linting", "testing"]

    def test_load_skills_as_yaml_list(self, tmp_path: Path):
        """测试前置元数据中YAML列表的加载技巧。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: skilled-agent
skills:
  - code-review
  - linting
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.skills == ["code-review", "linting"]

    def test_load_skills_single_string(self, tmp_path: Path):
        """测试从前置元数据字符串加载单个技能名称。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: skilled-agent
skills: code-review
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.skills == ["code-review"]

    def test_load_skills_default_empty(self, tmp_path: Path):
        """测试没有技能的情况下从文件加载会给出空列表。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: file-agent
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.skills == []

    def test_load_skills_not_in_metadata(self, tmp_path: Path):
        """测试技能字段是否被排除在额外元数据之外。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
skills: my-skill
custom_field: value
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert "skills" not in agent.metadata
        assert agent.metadata.get("custom_field") == "value"

    def test_load_agent_with_profile_store_dir(self, tmp_path: Path):
        """测试从前置元数据中使用 profile_store_dir 加载智能体。"""
        agent_md = tmp_path / "profiled.md"
        agent_md.write_text(
            """---
name: profiled
profile_store_dir: /custom/profiles
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.profile_store_dir == "/custom/profiles"

    def test_load_agent_without_profile_store_dir(self, tmp_path: Path):
        """测试当省略时 profile_store_dir 默认为 None。"""
        agent_md = tmp_path / "default.md"
        agent_md.write_text(
            """---
name: no-profile-dir
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.profile_store_dir is None

    def test_profile_store_dir_not_in_metadata(self, tmp_path: Path):
        """测试 profile_store_dir 不会泄漏到元数据中。"""
        agent_md = tmp_path / "meta-check.md"
        agent_md.write_text(
            """---
name: meta-check
profile_store_dir: /some/path
custom_field: value
---

Content.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert "profile_store_dir" not in agent.metadata
        assert agent.metadata.get("custom_field") == "value"

    def test_profile_store_dir_default_none(self):
        """测试直接构造时 profile_store_dir 默认为 None。"""
        agent = AgentDefinition(name="test")
        assert agent.profile_store_dir is None

    def test_mcp_config_default_none(self):
        """测试直接构造时 mcp_config 默认为 None。"""
        agent = AgentDefinition(name="test")
        assert agent.mcp_config is None

    def test_mcp_config(self):
        """测试使用类型化的 MCP 服务器创建 AgentDefinition。"""
        servers = {"fetch": MCPServer(command="uvx", args=["mcp-server-fetch"])}
        agent = AgentDefinition(name="mcp-agent", mcp_config=servers)
        assert agent.mcp_config is not None
        assert dump_mcp_config(agent.mcp_config) == {
            "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}
        }

    def test_load_mcp_config_from_frontmatter(self, tmp_path: Path):
        """测试从 YAML 前置元数据加载 mcp_config。"""
        agent_md = tmp_path / "mcp-agent.md"
        agent_md.write_text(
            """---
name: mcp-agent
mcp_config:
  fetch:
    command: uvx
    args:
      - mcp-server-fetch
  filesystem:
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-filesystem"
---

You are an agent with MCP tools.
"""
        )

        agent = AgentDefinition.load(agent_md)
        assert agent.mcp_config is not None
        assert "fetch" in agent.mcp_config
        servers = dump_mcp_config(agent.mcp_config)
        assert servers["fetch"]["command"] == "uvx"
        assert servers["fetch"]["args"] == ["mcp-server-fetch"]
        assert "filesystem" in agent.mcp_config

    def test_load_mcp_config_not_in_metadata(self, tmp_path: Path):
        """测试 mcp_config 不会泄漏到元数据中。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
mcp_config:
  fetch:
    command: uvx
    args:
      - mcp-server-fetch
custom_field: value
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert "mcp_config" not in agent.metadata
        assert agent.metadata.get("custom_field") == "value"

    def test_load_without_mcp_config(self, tmp_path: Path):
        """测试从文件加载的代码 mcp_config gives None."""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: no-mcp
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.mcp_config is None

    def test_mcp_config_env_vars_preserved_in_env_field(self, tmp_path: Path):
        """测试是否保留 env 值中的 ${VAR} 引用。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
mcp_config:
  my-server:
    command: npx
    args:
      - mcp-server
    env:
      API_KEY: ${MY_API_KEY}
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        mcp_config = agent.mcp_config
        assert mcp_config is not None
        dumped = dump_mcp_config(mcp_config)
        # 为每个会话的运行时扩展保留占位符机密
        assert dumped["my-server"]["env"]["API_KEY"] == "${MY_API_KEY}"

    def test_mcp_config_env_vars_preserved_in_command(self, tmp_path: Path):
        """测试命令中的 ${VAR} 引用是否被保留。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
mcp_config:
  my-server:
    command: ${PLUGIN_ROOT}/bin/server
    args:
      - --config
      - ${PLUGIN_ROOT}/config.json
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        mcp_config = agent.mcp_config
        assert mcp_config is not None
        dumped = dump_mcp_config(mcp_config)
        # 为运行时扩展保留的占位符
        assert dumped["my-server"]["command"] == "${PLUGIN_ROOT}/bin/server"
        assert dumped["my-server"]["args"] == [
            "--config",
            "${PLUGIN_ROOT}/config.json",
        ]

    def test_mcp_config_env_vars_preserved_in_url_and_headers(self, tmp_path: Path):
        """测试 url 和标头中的 ${VAR} 引用是否被保留。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
mcp_config:
  remote:
    transport: http
    url: ${API_BASE}/mcp
    headers:
      Authorization: Bearer ${AUTH_TOKEN}
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        mcp_config = agent.mcp_config
        assert mcp_config is not None
        dumped = dump_mcp_config(mcp_config)
        # 为运行时扩展保留的占位符
        assert dumped["remote"]["url"] == "${API_BASE}/mcp"
        assert dumped["remote"]["headers"]["Authorization"] == ("Bearer ${AUTH_TOKEN}")

    def test_mcp_config_placeholders_preserved(self, tmp_path: Path):
        """测试所有 ${VAR} 占位符是否保持不变。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
mcp_config:
  my-server:
    command: ${SOME_VAR}
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        mcp_config = agent.mcp_config
        assert mcp_config is not None
        assert dump_mcp_config(mcp_config)["my-server"]["command"] == "${SOME_VAR}"

    def test_permission_mode_defaults_to_none(self):
        """测试 permission_mode 默认为 None（继承父级）。"""
        agent = AgentDefinition(name="test")
        assert agent.permission_mode is None

    @pytest.mark.parametrize(
        "mode",
        [
            "never_confirm",
            "confirm_risky",
            "always_confirm",
        ],
    )
    def test_permission_mode_valid_values(self, mode: str):
        """测试每个有效值的设置 permission_mode。"""
        agent = AgentDefinition(name="test", permission_mode=mode)
        assert agent.permission_mode == mode

    def test_load_permission_mode_from_frontmatter(self, tmp_path: Path):
        """测试从前置元数据加载 permission_mode。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: secure-agent
permission_mode: always_confirm
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.permission_mode == "always_confirm"

    def test_load_permission_mode_none_when_omitted(self, tmp_path: Path):
        """测试，permission_mode 是 None 不在的时候前置元数据。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: basic-agent
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert agent.permission_mode is None

    def test_load_permission_mode_not_in_metadata(self, tmp_path: Path):
        """测试 permission_mode 是否被排除在额外元数据之外。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
permission_mode: never_confirm
custom_field: value
---

Prompt.
"""
        )
        agent = AgentDefinition.load(agent_md)
        assert "permission_mode" not in agent.metadata
        assert agent.metadata.get("custom_field") == "value"

    def test_get_confirmation_policy_none(self):
        """测试 None permission_mode 返回 None（继承父级）。"""
        agent = AgentDefinition(name="test")
        assert agent.get_confirmation_policy() is None

    @pytest.mark.parametrize(
        "permission_mode, expected_class_name",
        [
            ("always_confirm", "AlwaysConfirm"),
            ("never_confirm", "NeverConfirm"),
            ("confirm_risky", "ConfirmRisky"),
        ],
    )
    def test_get_confirmation_policy_returns_instance(
        self, permission_mode: str, expected_class_name: str
    ):
        """测试每个 permission_mode 返回正确的策略实例。"""
        agent = AgentDefinition(name="test", permission_mode=permission_mode)
        policy = agent.get_confirmation_policy()
        assert policy is not None
        assert type(policy).__name__ == expected_class_name

    def test_load_permission_mode_invalid_raises(self, tmp_path: Path):
        """测试无效的 permission_mode 引发 ValueError。"""
        agent_md = tmp_path / "agent.md"
        agent_md.write_text(
            """---
name: agent
permission_mode: invalid_mode
---

Prompt.
"""
        )
        with pytest.raises(ValueError, match="Invalid permission_mode"):
            AgentDefinition.load(agent_md)


class TestExtractExamples:
    """测试 _extract_examples 功能。"""

    def test_extract_single_example(self):
        """测试提取单个示例。"""
        description = "A tool. <example>Use when X</example>"
        examples = _extract_examples(description)
        assert examples == ["Use when X"]

    def test_extract_multiple_examples(self):
        """测试提取多个示例。"""
        description = "<example>First</example> text <example>Second</example>"
        examples = _extract_examples(description)
        assert examples == ["First", "Second"]

    def test_extract_no_examples(self):
        """当没有示例时进行测试。"""
        description = "A tool without examples"
        examples = _extract_examples(description)
        assert examples == []

    def test_extract_multiline_example(self):
        """测试提取多行示例。"""
        description = """<example>
        Multi
        Line
        </example>"""
        examples = _extract_examples(description)
        assert len(examples) == 1
        assert "Multi" in examples[0]


class TestAgentDefinitionCondenser:
    """测试上下文压缩器前置元数据字段。"""

    def test_condenser_absent_is_none(self, tmp_path: Path):
        agent_md = tmp_path / "a.md"
        agent_md.write_text("---\nname: a\n---\n\nPrompt.\n")
        assert AgentDefinition.load(agent_md).condenser is None

    def test_condenser_none_disables(self, tmp_path: Path):
        from openhands.sdk.context.condenser import NoOpCondenser

        agent_md = tmp_path / "a.md"
        agent_md.write_text("---\nname: a\ncondenser: none\n---\n\nPrompt.\n")
        assert isinstance(AgentDefinition.load(agent_md).condenser, NoOpCondenser)

    def test_condenser_false_disables(self, tmp_path: Path):
        from openhands.sdk.context.condenser import NoOpCondenser

        agent_md = tmp_path / "a.md"
        agent_md.write_text("---\nname: a\ncondenser: false\n---\n\nPrompt.\n")
        assert isinstance(AgentDefinition.load(agent_md).condenser, NoOpCondenser)

    def test_condenser_invalid_string_raises(self, tmp_path: Path):
        agent_md = tmp_path / "a.md"
        agent_md.write_text("---\nname: a\ncondenser: bogus\n---\n\nPrompt.\n")
        with pytest.raises(ValueError, match="Invalid condenser value"):
            AgentDefinition.load(agent_md)

    def test_condenser_not_in_metadata(self, tmp_path: Path):
        """上下文压缩器是已知字段，未泄漏到元数据附加中。"""
        agent_md = tmp_path / "a.md"
        agent_md.write_text("---\nname: a\ncondenser: none\n---\n\nPrompt.\n")
        assert "condenser" not in AgentDefinition.load(agent_md).metadata


class TestAgentDefinitionMaxBudget:
    """测试 max_budget_per_run 前置元数据字段。"""

    def test_absent_is_none(self, tmp_path: Path):
        md = tmp_path / "a.md"
        md.write_text("---\nname: a\n---\n\nPrompt.\n")
        assert AgentDefinition.load(md).max_budget_per_run is None

    def test_numeric_value(self, tmp_path: Path):
        md = tmp_path / "a.md"
        md.write_text("---\nname: a\nmax_budget_per_run: 2.5\n---\n\nPrompt.\n")
        assert AgentDefinition.load(md).max_budget_per_run == 2.5

    def test_string_value(self, tmp_path: Path):
        md = tmp_path / "a.md"
        md.write_text('---\nname: a\nmax_budget_per_run: "1.0"\n---\n\nPrompt.\n')
        assert AgentDefinition.load(md).max_budget_per_run == 1.0

    def test_not_in_metadata(self, tmp_path: Path):
        md = tmp_path / "a.md"
        md.write_text("---\nname: a\nmax_budget_per_run: 3\n---\n\nPrompt.\n")
        assert "max_budget_per_run" not in AgentDefinition.load(md).metadata
