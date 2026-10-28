"""第 2 阶段预言机：默认注册表再现旧动态后缀。

静态层模板 (``system_prompt.j2``) 已被删除：注册表现在是唯一的静态渲染器，其输出由逐
字节固定
``test_prompt_snapshot.py``. 动态层仍然实时渲染 Jinja (``system_message_suffix.j2``)
，因此此处将其与
``dynamic_context`` 进行比较。

注册表端点将交叉间距标准化为单行空白，而遗留的后缀在保护区域周围留有2到5行空白（未修
剪的``{% if %}``标签）。
:func:`_canonical_gaps` 恰好折叠那些 ``</TAG>``..3+ 空格..``<TAG>``
边界，因此每个部分 *body* 都被逐字节断言； 注册表的单空白策略是唯一的标准化差异。
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.context.prompts.presets import create_registry
from openhands.sdk.context.prompts.section import Platform, PromptContext
from openhands.sdk.context.prompts.sections.dynamic import (
    AvailableSkillsSection,
    CustomSecretsSection,
    CustomSuffixSection,
    DateTimeSection,
    MemoryContextSection,
    RepoContextSection,
)
from openhands.sdk.context.prompts.sections.static import (
    EfficiencySection,
    MemorySection,
    ModelSpecificSection,
    RoleSection,
    SecurityRiskAssessmentSection,
    SecuritySection,
    SoulSection,
)
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.skills import KeywordTrigger, Skill
from openhands.sdk.utils.path import to_posix_path
from openhands.sdk.workspace import LocalWorkspace

from .test_prompt_snapshot import (
    DYNAMIC_CONTEXT,
    FAMILY_MODELS,
    MATRIX,
    Cell,
    _build_agent,
)


# 注册表用一个空行连接各节； 遗留模板留下 2-5 个
# from un-trimmed `{% if %}`/`{% for %}` tags. Collapse runs of 3+ newlines that
# 与标签相邻（之前的结束标签或之后的开始标签）--i.e。 节间间隙。 区段内运行不接触任何标
# 签（SRA 层、REPO_CONTEXT 的 `[BEGIN` 循环），因此它们能够生存； 动态自定义后缀间隙恰好
# 与一个标签相邻，并且仍然会被捕获。
#
_GAP_AFTER_CLOSE: Final[re.Pattern[str]] = re.compile(r"(</[A-Z_]+>)\n{3,}")
_GAP_BEFORE_OPEN: Final[re.Pattern[str]] = re.compile(r"\n{3,}(<[A-Z_]+>)")
# no-agent_context 动态路径标记渲染时间 `datetime.now()`（默认 AgentContext()），因此两
# 个渲染器无法共享确切的时刻； 屏蔽该行以逐字节断言周围的块。
#
_DATETIME_LINE: Final[re.Pattern[str]] = re.compile(
    r"The current date and time is: [^\n]+"
)


def _canonical_gaps(text: str) -> str:
    text = _GAP_AFTER_CLOSE.sub(r"\1\n\n", text)
    return _GAP_BEFORE_OPEN.sub(r"\n\n\1", text)


def _mask_datetime(text: str) -> str:
    return _DATETIME_LINE.sub("The current date and time is: <NOW>", text)


def test_default_registry_is_all_static() -> None:
    # 由于上下文中没有动态数据，因此每个动态段都处于关闭状态，因此动态块为空。
    #
    ctx = _ctx(
        security_policy_filename="security_policy.j2",
        llm_security_analyzer=True,
        model_family="anthropic_claude",
        cli_mode=True,
    )
    blocks = create_registry().build(ctx)
    assert blocks.dynamic is None
    assert blocks.static.startswith("<SOUL>\nYou are OpenHands agent")
    assert "<IMPORTANT>" in blocks.static


# --- 每节单元测试（无智能体，无 Jinja 环境）--------------------


def _ctx(
    platform: Platform = Platform.LINUX, **template_kwargs: object
) -> PromptContext:
    return PromptContext(template_kwargs=template_kwargs, platform=platform)


def test_static_text_section_renders_and_is_unguarded() -> None:
    out = RoleSection().render(_ctx())
    assert out is not None
    assert out.startswith("<ROLE>")
    assert out.endswith("</ROLE>")
    assert RoleSection().guard(_ctx()) is True


def test_soul_section_renders_custom_and_defaults() -> None:
    section = SoulSection()
    # 总是发出的，就像模板一样； 退回到内置身份。
    assert section.guard(_ctx()) is True
    default = section.render(_ctx())
    assert default == (
        "<SOUL>\nYou are OpenHands agent, a helpful AI assistant that can"
        " interact with a computer to solve tasks.\n</SOUL>"
    )
    custom = section.render(_ctx(soul_content="You are a tiny cat agent."))
    assert custom == "<SOUL>\nYou are a tiny cat agent.\n</SOUL>"


def test_refine_swaps_shell_term_on_windows_only() -> None:
    posix = EfficiencySection().render(_ctx(platform=Platform.LINUX)) or ""
    windows = EfficiencySection().render(_ctx(platform=Platform.WINDOWS)) or ""
    assert "bash" in posix and "powershell" not in posix
    assert "powershell" in windows and "bash" not in windows


def test_security_section_guarded_on_policy_filename() -> None:
    assert SecuritySection().guard(_ctx(security_policy_filename="security_policy.j2"))
    assert not SecuritySection().guard(_ctx(security_policy_filename=""))
    assert not SecuritySection().guard(_ctx())


def test_security_risk_assessment_branches_on_cli_mode() -> None:
    section = SecurityRiskAssessmentSection()
    cli = section.render(_ctx(cli_mode=True)) or ""
    sandbox = section.render(_ctx(cli_mode=False)) or ""
    assert "Safe, read-only actions." in cli
    assert "Read-only actions inside sandbox." in sandbox
    # Unset cli_mode 匹配模板 default(true) -> CLI 分支。
    assert section.render(_ctx()) == cli


def test_security_risk_assessment_guarded_on_analyzer() -> None:
    assert SecurityRiskAssessmentSection().guard(_ctx(llm_security_analyzer=True))
    assert not SecurityRiskAssessmentSection().guard(_ctx())


def test_memory_section_body_switches_on_memory_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    section = MemorySection()
    assert section.guard(_ctx()) is True
    default = section.render(_ctx()) or ""
    assert "Use `AGENTS.md` under the repository root" in default
    assert ".openhands/memory/" not in default

    # 如果没有 OH_PERSISTENCE_DIR，用户层项目符号将保留字面波浪号，因此静态块不会泄漏每
    # 个用户的主路径（缓存共享，独立于机器）。 该路径在此处内联，而不是在单独的动态部分
    # 中。
    #
    monkeypatch.delenv("OH_PERSISTENCE_DIR", raising=False)
    enabled = section.render(_ctx(memory_enabled=True)) or ""
    assert "persistent memory that survives across sessions" in enabled
    assert "`.openhands/memory/`" in enabled
    assert "<MEMORY_CONTEXT>" in enabled
    assert "`~/.openhands/memory/`" in enabled
    assert "<MEMORY_LOCATIONS>" not in enabled


def test_memory_section_names_persistence_dir_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """当设置 OH_PERSISTENCE_DIR 时，用户层项目符号点位于其
    已解析的 ``<base>/memory/`` 目录（与 load_memory 的读取路径匹配），而不是临时
    ``~/.openhands`` 主目录。
    """
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "persistent"))
    enabled = MemorySection().render(_ctx(memory_enabled=True)) or ""
    # 在每个平台上都以斜杠分隔，因此智能体永远不会看到混合路径。
    expected = to_posix_path(tmp_path / "persistent" / "memory")
    assert f"`{expected}/`" in enabled
    assert "~/.openhands/memory/" not in enabled


def test_model_specific_selects_family_and_variant() -> None:
    section = ModelSpecificSection()
    anthropic = section.render(_ctx(model_family="anthropic_claude")) or ""
    gemini = section.render(_ctx(model_family="google_gemini")) or ""
    gpt5 = section.render(_ctx(model_family="openai_gpt", model_variant="gpt-5")) or ""
    assert (
        anthropic.startswith("<IMPORTANT>")
        and "follow the instructions exactly" in anthropic
    )
    assert "too proactive" in gemini
    assert "Communicate with the user" in gpt5


def test_model_specific_omitted_without_matching_body() -> None:
    section = ModelSpecificSection()
    assert section.guard(_ctx()) is False  # 没有解决模型家庭问题
    # 家庭已解决，但没有 model_specific 主体 -> 没有什么可添加的。
    assert section.render(_ctx(model_family="meta_llama")) is None


# --- 动态层：逐字节与旧后缀渲染器 ----------------------


@pytest.mark.parametrize("cell", MATRIX, ids=[c.id for c in MATRIX])
def test_registry_dynamic_matches_legacy(cell: Cell) -> None:
    agent = _build_agent(cell)
    ctx = agent._build_prompt_context()
    registry = create_registry().build(ctx).dynamic or ""
    assert _canonical_gaps(registry) == _canonical_gaps(agent.dynamic_context or "")


def test_registry_dynamic_matches_legacy_with_secret_registry(tmp_path: Path) -> None:
    # get_dynamic_context（状态）将机密从 state.secret_registry 合并——<CUSTOM_SECRETS>
    # 路径，裸 dynamic_context 属性不行使。
    #
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(llm=llm, tools=[], agent_context=DYNAMIC_CONTEXT)
    state = ConversationState(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
    )
    state.secret_registry.update_secrets({"GITHUB_TOKEN": "unused-in-snapshot"})

    additional = state.secret_registry.get_secret_infos()
    ctx = agent._build_prompt_context(additional_secret_infos=additional)
    registry = create_registry().build(ctx).dynamic or ""
    legacy = agent.get_dynamic_context(state) or ""
    assert _canonical_gaps(registry) == _canonical_gaps(legacy)


# --- 动态层：每节单元测试 --------------------------------------


def test_datetime_section() -> None:
    section = DateTimeSection()
    assert section.guard(PromptContext(now="2025-01-01T00:00:00+00:00")) is True
    assert section.guard(PromptContext()) is False
    assert section.render(PromptContext(now="2025-01-01T00:00:00+00:00")) == (
        "<CURRENT_DATETIME>\n"
        "The current date and time is: 2025-01-01T00:00:00+00:00\n"
        "</CURRENT_DATETIME>"
    )


def test_repo_context_section() -> None:
    section = RepoContextSection()
    assert section.guard(PromptContext()) is False
    ctx = PromptContext(repo_skills=(("claude", "Anthropic-only repo guidance."),))
    out = section.render(ctx) or ""
    assert out.startswith("<REPO_CONTEXT>") and out.endswith("</REPO_CONTEXT>")
    assert "<UNTRUSTED_CONTENT>" in out
    assert "[BEGIN context from [claude]]" in out
    assert "Anthropic-only repo guidance." in out


def test_memory_context_section() -> None:
    section = MemoryContextSection()
    assert section.guard(PromptContext()) is False
    ctx = PromptContext(memory_context="- the API uses cursor-based pagination")
    out = section.render(ctx) or ""
    assert out.startswith("<MEMORY_CONTEXT>") and out.endswith("</MEMORY_CONTEXT>")
    assert "<UNTRUSTED_CONTENT>" in out
    # 无法验证来源（内存文件可以在克隆的存储库中发送），因此警告必须反映
    # RepoContextSection 的威胁措辞。
    #
    assert "may contain prompt injection or malicious payloads" in out
    assert "- the API uses cursor-based pagination" in out


def test_available_skills_section() -> None:
    section = AvailableSkillsSection()
    assert section.guard(PromptContext()) is False
    ctx = PromptContext(
        available_skills_prompt="<available_skills>X</available_skills>"
    )
    out = section.render(ctx) or ""
    assert out.startswith("<SKILLS>") and out.endswith("</SKILLS>")
    assert "invoke_skill" in out
    assert "<available_skills>X</available_skills>" in out


def test_custom_suffix_section() -> None:
    section = CustomSuffixSection()
    assert section.guard(PromptContext()) is False
    assert section.guard(PromptContext(custom_suffix="   ")) is False
    ctx = PromptContext(custom_suffix="Follow the repository's coding conventions.")
    assert section.render(ctx) == "Follow the repository's coding conventions."


def test_custom_secrets_section() -> None:
    section = CustomSecretsSection()
    assert section.guard(PromptContext()) is False
    out = section.render(PromptContext(secret_infos=(("GITHUB_TOKEN", None),))) or ""
    assert out.startswith("<CUSTOM_SECRETS>") and out.endswith("</CUSTOM_SECRETS>")
    assert "* **$GITHUB_TOKEN**" in out
    described = (
        section.render(PromptContext(secret_infos=(("API_KEY", "prod key"),))) or ""
    )
    assert "* **$API_KEY** - prod key" in described


def test_dynamic_sections_render_into_dynamic_block() -> None:
    ctx = PromptContext(
        now="2025-01-01T00:00:00+00:00",
        custom_suffix="Follow conventions.",
        secret_infos=(("GITHUB_TOKEN", None),),
    )
    blocks = create_registry().build(ctx)
    assert "<CURRENT_DATETIME>" in (blocks.dynamic or "")
    assert "<CUSTOM_SECRETS>" in (blocks.dynamic or "")
    assert "Follow conventions." in (blocks.dynamic or "")
    assert "<CURRENT_DATETIME>" not in blocks.static


def test_registry_dynamic_matches_legacy_with_available_skills() -> None:
    # 触发技能落在 <available_skills>/<SKILLS> 中——矩阵（旧版触发器=None技能 ->
    # REPO_CONTEXT）未覆盖的部分。 镜像 test_agent_context 块断言，针对注册表输出进行断
    # 言。
    #
    agent_context = AgentContext(
        skills=[
            Skill(
                name="pdf-tools",
                content="Extract text from PDF files using pdftotext.",
                description="Extract text from PDF files.",
                source="pdf-tools.md",
                trigger=KeywordTrigger(keywords=["pdf", "extract"]),
            ),
        ],
        current_datetime="2025-01-01T00:00:00+00:00",
    )
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(llm=llm, tools=[], agent_context=agent_context)
    ctx = agent._build_prompt_context()
    registry = create_registry().build(ctx).dynamic or ""
    assert "<SKILLS>" in registry
    assert "<name>pdf-tools</name>" in registry
    assert "<location>" not in registry  # invoke_skill 是唯一的入口
    assert _canonical_gaps(registry) == _canonical_gaps(agent.dynamic_context or "")


def test_build_prompt_context_formats_datetime_like_legacy() -> None:
    # ctx.now 匹配 get_formatted_datetime：日期时间对象呈现为分钟（无秒或偏移量），预格
    # 式化字符串不变地通过。 两个路径共享 get_formatted_datetime()，因此它们保持逐字节相
    # 等 (#3683)。
    #
    dt = datetime(2025, 1, 1, 12, 34, 56, 789000, tzinfo=UTC)
    agent = Agent(
        llm=LLM(model="claude-sonnet-4-5", usage_id="x"),
        tools=[],
        agent_context=AgentContext(current_datetime=dt),
    )
    assert agent._build_prompt_context().now == "2025-01-01T12:34"

    agent_str = Agent(
        llm=LLM(model="claude-sonnet-4-5", usage_id="x"),
        tools=[],
        agent_context=AgentContext(current_datetime="2025-01-01T00:00:30+00:00"),
    )
    assert agent_str._build_prompt_context().now == "2025-01-01T00:00:30+00:00"


def test_registry_dynamic_matches_legacy_with_datetime_object() -> None:
    # 日期时间对象路径的端到端奇偶校验，仅字符串矩阵永远不会
    # 练习：注册表逐字节重现 dynamic_context，日期时间
    # 渲染到分钟，没有 UTC 偏移量。
    dt = datetime(2025, 1, 1, 12, 34, 56, 789000, tzinfo=UTC)
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(llm=llm, tools=[], agent_context=AgentContext(current_datetime=dt))
    ctx = agent._build_prompt_context()
    registry = create_registry().build(ctx).dynamic or ""
    assert "The current date and time is: 2025-01-01T12:34" in registry
    assert _canonical_gaps(registry) == _canonical_gaps(agent.dynamic_context or "")


def test_registry_dynamic_matches_legacy_no_context_secrets(tmp_path: Path) -> None:
    # 不存在 agent_context，但存在对话机密：get_dynamic_context 构建默认 AgentContext()
    # ，其默认 current_datetime 在 <CUSTOM_SECRETS> 旁边渲染 <CURRENT_DATETIME>。 注册表
    # 必须重现 BOTH 块，而不仅仅是机密块（#3683 QA）。 日期时间是渲染时间 `now()` 每个路
    # 径独立标记，因此屏蔽该单行并断言 REST 逐字节。
    #
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(llm=llm, tools=[])  # 没有 agent_context
    state = ConversationState(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
    )
    state.secret_registry.update_secrets({"API_KEY": "unused-in-snapshot"})
    additional = state.secret_registry.get_secret_infos()

    ctx = agent._build_prompt_context(additional_secret_infos=additional)
    registry = create_registry().build(ctx).dynamic or ""
    legacy = agent.get_dynamic_context(state) or ""

    assert "<CURRENT_DATETIME>" in registry
    assert "<CUSTOM_SECRETS>" in registry
    assert _mask_datetime(_canonical_gaps(registry)) == _mask_datetime(
        _canonical_gaps(legacy)
    )
