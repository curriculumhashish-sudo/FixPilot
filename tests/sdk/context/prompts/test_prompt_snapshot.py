"""渲染系统的黄金快照预言机提示词（问题#3607）。

矩阵上的引脚 ``static_system_message`` + ``dynamic_context`` 会改变其输出：模型系列 x
llm_security_analyzer x cli_mode。 快照位于 ``snapshots/`` 下（每个单元一个 .txt），
这是来自
``tests/sdk/persisted_settings_baselines`` 的无依赖性黄金文件习惯用法。

有意提示词更改后重新生成：
    REGEN_PROMPT_SNAPSHOTS=1 uv run pytest \
        tests/sdk/context/prompts/test_prompt_snapshot.py
"""

import os
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.agent.base import _DEFAULT_SOUL
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.skills import Skill
from openhands.sdk.workspace import LocalWorkspace


SNAPSHOT_DIR: Final[Path] = Path(__file__).parent / "snapshots"
SEPARATOR: Final[str] = (
    "\n\n===== DYNAMIC CONTEXT (second system content block) =====\n\n"
)
REGEN: Final[bool] = os.environ.get("REGEN_PROMPT_SNAPSHOTS") == "1"

# 选择字符串，以便 get_model_prompt_spec 解析每个系列（以及 gpt-5 变体）； 不匹配的字符
# 串是“其他”分支（没有 model_specific 部分）。
#
FAMILY_MODELS: Final[dict[str, str]] = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-5",
    "gemini": "gemini-2.5-pro",
    "other": "custom-made-model",
}

# Pin current_datetime （默认为 ） datetime.now） 因此，动态块是可重复的。 两个遗留的（
# 触发=）None) 技能被命名以执行模型族门禁操作 get_system_message_suffix: Anthropic keep
# "claude", keep "gemini" OpenAI 既不保留“其他”（无家庭），也不保留两者。 机密通过生产覆
# 盖 get_dynamic_context(请参见以下内容)。
#
DYNAMIC_CONTEXT: Final[AgentContext] = AgentContext(
    current_datetime="2025-01-01T00:00:00+00:00",
    system_message_suffix="Follow the repository's coding conventions.",
    skills=[
        Skill(name="claude", content="Anthropic-only repo guidance.", trigger=None),
        Skill(name="gemini", content="Gemini-only repo guidance.", trigger=None),
    ],
)

# 注入动态块的日期时间形状； 在静态块中，发生泄漏。
ISO_DATETIME_RE: Final[re.Pattern[str]] = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
)


@dataclass(frozen=True)
class Cell:
    family: str
    llm_security_analyzer: bool
    cli_mode: bool

    @property
    def id(self) -> str:
        def flag(name: str, value: bool) -> str:
            return f"{name}-{'on' if value else 'off'}"

        return "__".join(
            [
                self.family,
                flag("secana", self.llm_security_analyzer),
                flag("cli", self.cli_mode),
            ]
        )


def _build_matrix() -> list[Cell]:
    cells: list[Cell] = []
    for family in FAMILY_MODELS:
        for llm_security_analyzer in (True, False):
            # cli_mode 仅影响安全分析器部分。
            cli_values = (True, False) if llm_security_analyzer else (True,)
            for cli_mode in cli_values:
                cells.append(Cell(family, llm_security_analyzer, cli_mode))
    return cells


MATRIX: Final[list[Cell]] = _build_matrix()


def _build_agent(cell: Cell) -> Agent:
    llm = LLM(model=FAMILY_MODELS[cell.family], usage_id="snapshot-llm")
    return Agent(
        llm=llm,
        tools=[],
        agent_context=DYNAMIC_CONTEXT,
        system_prompt_kwargs={
            "llm_security_analyzer": cell.llm_security_analyzer,
            "cli_mode": cell.cli_mode,
            # 将 soul_content 固定到内置默认值，以便无论运行测试的计算机上是否存在 ~
            # /.openhands/SOUL.md，快照都是确定性的。
            #
            "soul_content": _DEFAULT_SOUL,
        },
    )


def _rendered(cell: Cell) -> str:
    agent = _build_agent(cell)
    return agent.static_system_message + SEPARATOR + (agent.dynamic_context or "")


def _check_snapshot(name: str, content: str) -> None:
    path = SNAPSHOT_DIR / f"{name}.txt"
    if REGEN:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    assert path.exists(), (
        f"Missing snapshot {path}. Regenerate with "
        f"REGEN_PROMPT_SNAPSHOTS=1 pytest {Path(__file__).name}"
    )
    assert content == path.read_text(encoding="utf-8"), (
        f"Rendered prompt for '{name}' diverged from its committed snapshot. If the "
        f"change is intentional, regenerate with REGEN_PROMPT_SNAPSHOTS=1."
    )


@pytest.mark.parametrize("cell", MATRIX, ids=[c.id for c in MATRIX])
def test_prompt_snapshot(cell: Cell) -> None:
    _check_snapshot(cell.id, _rendered(cell))


# 每个部分“打开”的代表性单元格，用于固定 Windows 变体。
PLATFORM_CELL: Final[Cell] = Cell(
    family="anthropic",
    llm_security_analyzer=True,
    cli_mode=True,
)


def test_prompt_snapshot_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    # refine() (context/prompts/prompt.py) 在 win32 上交换 bash -> powershell 和终端 ->
    # execute_powershell，在渲染时读取 sys.platform。
    #
    monkeypatch.setattr(sys, "platform", "win32")
    content = _rendered(PLATFORM_CELL)
    _check_snapshot(f"{PLATFORM_CELL.id}__win32", content)
    assert "powershell" in content  # 替补实际上被解雇了


def test_dynamic_context_with_secret_registry(tmp_path: Path) -> None:
    # 生产构建动态块的get_dynamic_context(状态)，该块合并了机密从state.secret_registry(
    # agent.py) -- <CUSTOM_SECRETS>路径和dynamic_context裸属性没有覆盖。working_dir没有
    # 渲染到后缀，所以tmp_path没有进入快照。
    #
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(llm=llm, tools=[], agent_context=DYNAMIC_CONTEXT)
    state = ConversationState(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
    )
    state.secret_registry.update_secrets({"GITHUB_TOKEN": "unused-in-snapshot"})
    _check_snapshot(
        "dynamic_context__with_secret_registry",
        agent.get_dynamic_context(state) or "",
    )


def test_soul_default_snapshot(tmp_path: Path) -> None:
    """与内置默认灵魂完全匹配的提示词快照。"""
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(
        llm=llm,
        tools=[],
        system_prompt_kwargs={"soul_content": _DEFAULT_SOUL},
    )
    _check_snapshot("soul__default", agent.static_system_message)


def test_soul_custom_snapshot(tmp_path: Path) -> None:
    """完整提示词与自定义 soul_content 与快照匹配。"""
    llm = LLM(model=FAMILY_MODELS["anthropic"], usage_id="snapshot-llm")
    agent = Agent(
        llm=llm,
        tools=[],
        system_prompt_kwargs={
            "soul_content": "You are a tiny cat agent with toe beans."
        },
    )
    _check_snapshot("soul__custom", agent.static_system_message)


@pytest.mark.parametrize("cell", MATRIX, ids=[c.id for c in MATRIX])
def test_static_block_has_no_dynamic_content(cell: Cell) -> None:
    """静态块是缓存共享前缀 (#2827)：per-run/per-env 内容
    那里默默地破坏了交叉对话缓存命中。 路径/主机名根据本机的具体值进行检查——唯一可能
    泄漏的注入。
    """
    static = _build_agent(cell).static_system_message
    assert not ISO_DATETIME_RE.search(static), "static block contains a timestamp"
    assert os.getcwd() not in static, "static block contains the working directory"
    assert str(Path.home()) not in static, "static block contains the home directory"
    assert socket.gethostname() not in static, "static block contains the hostname"
