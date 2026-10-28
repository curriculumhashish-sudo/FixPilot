"""测试智能体 / AgentBase 上的 system_prompt 内联覆盖。"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.context.prompts.presets import PromptPreset, create_registry
from openhands.sdk.llm import LLM


def _make_llm() -> LLM:
    return LLM(model="test-model", usage_id="test")


class _CustomPromptDirAgent(Agent):
    """智能体子类，其 ``prompt_dir`` 指向每个测试目录。"""

    custom_prompt_dir: ClassVar[str] = ""

    @property
    def prompt_dir(self) -> str:
        return type(self).custom_prompt_dir


# --- construction ---


def test_system_prompt_is_accepted_and_stored() -> None:
    agent = Agent(llm=_make_llm(), tools=[], system_prompt="CUSTOM")
    assert agent.system_prompt == "CUSTOM"


def test_system_prompt_defaults_to_none() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    assert agent.system_prompt is None


# --- static_system_message 使用内联提示词 ---


def test_static_system_message_returns_inline_prompt() -> None:
    agent = Agent(llm=_make_llm(), tools=[], system_prompt="MY PROMPT")
    assert agent.static_system_message == "MY PROMPT"


def test_static_system_message_falls_back_to_template_when_none() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    # 默认模板呈现非空字符串
    assert len(agent.static_system_message) > 0
    assert agent.static_system_message != ""


# --- 互斥性验证 ---


def test_system_prompt_and_custom_filename_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="Cannot set both"):
        Agent(
            llm=_make_llm(),
            tools=[],
            system_prompt="inline",
            system_prompt_filename="custom.j2",
        )


def test_system_prompt_with_default_filename_is_ok() -> None:
    """system_prompt + 应接受默认文件名。"""
    agent = Agent(
        llm=_make_llm(),
        tools=[],
        system_prompt="inline",
        system_prompt_filename="system_prompt.j2",
    )
    assert agent.system_prompt == "inline"
    assert agent.static_system_message == "inline"


# --- 自定义 prompt_dir 逃生舱口（注册表切换）---


def test_subclass_default_named_template_renders_through_jinja(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一个子类传送它自己的默认命名模板来渲染它，而不是
    注册表提示词。"""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "system_prompt.j2").write_text(
        "CUSTOM SUBCLASS PROMPT", encoding="utf-8"
    )
    monkeypatch.setattr(_CustomPromptDirAgent, "custom_prompt_dir", str(prompts))

    agent = _CustomPromptDirAgent(llm=_make_llm(), tools=[])
    assert agent.static_system_message == "CUSTOM SUBCLASS PROMPT"


def test_builtin_default_prompt_uses_registry() -> None:
    """内置的提示词目录 + 默认文件名仍然通过注册表进行路由。"""
    agent = Agent(llm=_make_llm(), tools=[])
    expected = create_registry().build(agent._build_prompt_context()).static
    assert agent.static_system_message == expected


# --- 规划预设 (哨兵值-文件名路由) ---


def test_prompt_preset_resolves_from_builtin_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """内置哨兵值文件名映射到预设； 其他任何东西都会逃到 Jinja。"""
    assert Agent(llm=_make_llm(), tools=[])._prompt_preset is PromptPreset.DEFAULT
    planning = Agent(
        llm=_make_llm(),
        tools=[],
        system_prompt_filename="system_prompt_planning.j2",
        system_prompt_kwargs={"plan_structure": "X"},
    )
    assert planning._prompt_preset is PromptPreset.PLANNING
    # 非哨兵值文件名采用 Jinja 逃生舱口（预设 None）。
    assert (
        Agent(
            llm=_make_llm(), tools=[], system_prompt_filename="custom.j2"
        )._prompt_preset
        is None
    )
    # 一个有自己prompt_dir的子类，即使有哨兵值文件名也是如此。
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    monkeypatch.setattr(_CustomPromptDirAgent, "custom_prompt_dir", str(prompts))
    sub = _CustomPromptDirAgent(
        llm=_make_llm(), tools=[], system_prompt_filename="system_prompt_planning.j2"
    )
    assert sub._prompt_preset is None


def test_planning_filename_routes_through_registry() -> None:
    """规划哨兵值呈现预设的规划注册表，而不是默认值。"""
    agent = Agent(
        llm=_make_llm(),
        tools=[],
        system_prompt_filename="system_prompt_planning.j2",
        system_prompt_kwargs={"plan_structure": "1. OBJECTIVE"},
    )
    static = agent.static_system_message
    expected = (
        create_registry(PromptPreset.PLANNING)
        .build(agent._build_prompt_context())
        .static
    )
    assert static == expected
    assert static.startswith("You are a Planning Agent")
    # 独立组合：默认的 OpenHands 身份不得泄漏。
    assert "<SOUL>" not in static


def test_custom_security_policy_is_resolved_by_registry(tmp_path: Path) -> None:
    """自定义 security_policy_filename 通过注册表得到尊重（没有 Jinja 逃逸）
    孵化），并且内置默认策略不会随之泄漏。"""
    policy = tmp_path / "custom_policy.j2"
    policy.write_text("CUSTOM POLICY", encoding="utf-8")

    agent = Agent(llm=_make_llm(), tools=[], security_policy_filename=str(policy))
    static = agent.static_system_message

    assert "CUSTOM POLICY" in static
    # 默认策略必须不与自定义策略一起泄漏。
    assert "🔐 Security Policy" not in static


# --- 序列化往返 ---


def test_system_prompt_survives_json_round_trip() -> None:
    agent = Agent(llm=_make_llm(), tools=[], system_prompt="ROUND TRIP")
    agent_json = agent.model_dump_json()
    restored = AgentBase.model_validate_json(agent_json)
    assert isinstance(restored, Agent)
    assert restored.system_prompt == "ROUND TRIP"
    assert restored.static_system_message == "ROUND TRIP"


def test_system_prompt_none_survives_json_round_trip() -> None:
    agent = Agent(llm=_make_llm(), tools=[])
    agent_json = agent.model_dump_json()
    restored = AgentBase.model_validate_json(agent_json)
    assert isinstance(restored, Agent)
    assert restored.system_prompt is None
