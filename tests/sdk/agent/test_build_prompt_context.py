"""测试 ``AgentBase._build_prompt_context()``。

``test_equivalent_to_static_template_kwargs`` 捕获 kwargs
``static_system_message`` 生成并断言快照会重现它们。
"""

import pytest

import openhands.sdk.agent.base as agent_base
from openhands.sdk import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.context.prompts.section import Platform, PromptContext
from openhands.sdk.llm import LLM
from openhands.sdk.skills import Skill
from openhands.sdk.tool import Tool


def _make_llm(model: str = "test-model") -> LLM:
    return LLM(model=model, usage_id="test-llm")


def test_returns_prompt_context() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    assert isinstance(agent._build_prompt_context(), PromptContext)


def test_equivalent_to_static_template_kwargs(monkeypatch) -> None:
    # 第 3 阶段切换后，默认提示词通过注册表渲染，因此只能通过自定义文件名逃逸舱口到达
    # render_template。 该路径和 _build_prompt_context 都通过 _resolved_template_kwargs
    # 解析 kwargs，因此它们不能漂移。
    #
    agent = Agent(
        llm=_make_llm(),
        tools=[Tool(name="browser_tool_set")],
        system_prompt_kwargs={"cli_mode": True},
        system_prompt_filename="custom.j2",
    )

    captured: dict = {}

    def _capture(*, prompt_dir, template_name, **kwargs):
        captured.update(kwargs)
        return ""

    monkeypatch.setattr(agent_base, "render_template", _capture)
    _ = agent.static_system_message  # 填充 `captured`

    ctx = agent._build_prompt_context()
    assert captured == ctx.template_kwargs


@pytest.mark.parametrize("enabled", [False, True])
def test_saved_browser_prompt_flag_loads_but_no_longer_controls_templates(
    tmp_path, enabled
) -> None:
    template = tmp_path / "legacy.j2"
    template.write_text("{{ enable_browser | default('removed') }} {{ cli_mode }}")
    saved = Agent(llm=_make_llm(), system_prompt_filename=str(template)).model_dump(
        mode="json"
    )
    saved["system_prompt_kwargs"] = {"enable_browser": enabled, "cli_mode": True}
    agent = Agent.model_validate(saved)
    assert "enable_browser" not in agent.system_prompt_kwargs
    assert agent.system_prompt_kwargs["cli_mode"] is True
    assert agent.static_system_message == "removed True"
    assert (
        Agent.model_validate_json(agent.model_dump_json()).system_prompt_kwargs
        == agent.system_prompt_kwargs
    )


def test_model_family_from_spec() -> None:
    agent = Agent(llm=_make_llm(model="claude-sonnet-4-5"), tools=[])
    assert agent._build_prompt_context().model_family == "anthropic_claude"


def test_template_kwargs_passthrough_includes_security_analyzer_and_cli_mode() -> None:
    agent = Agent(llm=_make_llm(), tools=[], system_prompt_kwargs={"cli_mode": True})
    ctx = agent._build_prompt_context()
    # 智能体注入 llm_security_analyzer=True 作为默认 kwarg。
    assert ctx.template_kwargs.get("llm_security_analyzer") is True
    assert ctx.cli_mode is True


def test_tool_names_snapshot() -> None:
    agent = Agent(
        llm=_make_llm(),
        tools=[Tool(name="terminal_tool"), Tool(name="browser_tool_set")],
    )
    assert agent._build_prompt_context().tool_names == (
        "terminal_tool",
        "browser_tool_set",
    )


def test_working_dir_is_none_in_bridge() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    assert agent._build_prompt_context().working_dir is None


def test_platform_is_snapshot() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    assert agent._build_prompt_context().platform is Platform.current()


def test_dynamic_snapshot_from_agent_context() -> None:
    agent = Agent(
        llm=_make_llm(),
        tools=[],
        agent_context=AgentContext(secrets={"API_TOKEN": "shh"}),
    )
    ctx = agent._build_prompt_context()
    assert ctx.secret_names == ("API_TOKEN",)
    assert ctx.now is not None  # AgentContext 默认 current_datetime


def test_no_agent_context_yields_empty_dynamic_fields() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    ctx = agent._build_prompt_context()
    assert ctx.skill_names == ()
    assert ctx.secret_names == ()
    assert ctx.now is None


def test_explicit_model_family_kwarg_wins_over_spec() -> None:
    """调用者提供的 model_family 不会被自动检测到的覆盖。"""
    agent = Agent(
        llm=_make_llm(model="claude-sonnet-4-5"),
        tools=[],
        system_prompt_kwargs={"model_family": "custom"},
    )
    assert agent._build_prompt_context().model_family == "custom"


def test_model_variant_from_spec() -> None:
    agent = Agent(llm=_make_llm(model="gpt-5-codex"), tools=[])
    ctx = agent._build_prompt_context()
    assert ctx.model_family == "openai_gpt"
    assert ctx.template_kwargs["model_variant"] == "gpt-5-codex"


def test_skill_names_snapshot_from_agent_context() -> None:
    agent = Agent(
        llm=_make_llm(),
        tools=[],
        agent_context=AgentContext(
            skills=[Skill(name="demo", content="x", source="s.md", trigger=None)]
        ),
    )
    assert agent._build_prompt_context().skill_names == ("demo",)
