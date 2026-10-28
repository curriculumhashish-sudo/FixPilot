"""工具输出在共享阻塞点被屏蔽（问题#4677）。

``ToolDefinition.__call__`` 是每个工具的观测结果都会经过的地方，因此默认情况下屏蔽该
位置会覆盖新工具，而不是记住对其进行修补。
"""

import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM
from openhands.sdk.tool import Tool, ToolDefinition, register_tool
from openhands.tools.apply_patch.definition import (
    ApplyPatchAction,
    ApplyPatchObservation,
    ApplyPatchTool,
)
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.file_editor.definition import FileEditorAction
from openhands.tools.glob import GlobTool
from openhands.tools.glob.definition import GlobAction, GlobObservation
from openhands.tools.grep import GrepTool
from openhands.tools.grep.definition import GrepAction, GrepObservation


SECRET = "sk-supersecret-value"
MASK = "<secret-hidden>"

_TOOLS = {
    "FileEditorTool": FileEditorTool,
    "GrepTool": GrepTool,
    "GlobTool": GlobTool,
    "ApplyPatchTool": ApplyPatchTool,
}


@pytest.fixture
def conversation(tmp_path: Path) -> LocalConversation:
    for name, cls in _TOOLS.items():
        register_tool(name, cls)
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[Tool(name=name) for name in _TOOLS])
    convo = LocalConversation(agent, workspace=str(tmp_path))
    convo._ensure_agent_ready()
    convo.update_secrets({"TOKEN": SECRET})
    return convo


def test_file_editor_view_masks_file_contents(
    conversation: LocalConversation, tmp_path: Path
):
    """头条新闻：读取包含机密的文件不再泄漏。"""
    env = tmp_path / ".env"
    env.write_text(f"API_KEY={SECRET}\n")

    action = FileEditorAction(command="view", path=str(env))
    observation = conversation.agent.tools_map["file_editor"](action, conversation)

    assert SECRET not in observation.text
    assert f"API_KEY={MASK}" in observation.text
    # 文件本身未受影响 - 仅返回的记录被屏蔽。
    assert env.read_text() == f"API_KEY={SECRET}\n"


def test_grep_masks_the_echoed_pattern(conversation: LocalConversation, tmp_path: Path):
    """``grep`` 返回路径，而不是文件内容 - 泄漏是回显模式。"""
    action = GrepAction(pattern=SECRET, path=str(tmp_path))
    observation = conversation.agent.tools_map["grep"](action, conversation)

    assert isinstance(observation, GrepObservation)
    assert observation.pattern == MASK
    assert SECRET not in observation.text


def test_glob_masks_a_matched_path(conversation: LocalConversation, tmp_path: Path):
    """``glob`` 返回路径，因此包含机密的文件名就是泄漏。"""
    (tmp_path / f"note-{SECRET}.txt").write_text("hi\n")

    action = GlobAction(pattern="*.txt", path=str(tmp_path))
    observation = conversation.agent.tools_map["glob"](action, conversation)

    assert isinstance(observation, GlobObservation)
    assert observation.files and all(SECRET not in f for f in observation.files)
    assert SECRET not in observation.text


def test_apply_patch_masks_nested_commit_content(conversation: LocalConversation):
    """嵌套模型案例 ``Observation.content`` 掩码将会丢失。

    机密落在 ``commit.changes[...].new_content`` 中，而不是 ``content`` 中。
    """
    patch = (
        f"*** Begin Patch\n*** Add File: secrets.txt\n+TOKEN={SECRET}\n*** End Patch"
    )
    action = ApplyPatchAction(patch=patch)
    observation = conversation.agent.tools_map["apply_patch"](action, conversation)

    assert isinstance(observation, ApplyPatchObservation)
    assert observation.commit is not None
    change = observation.commit.changes["secrets.txt"]
    assert change.new_content == f"TOKEN={MASK}"
    assert SECRET not in observation.model_dump_json()


def test_no_conversation_means_no_masking(tmp_path: Path):
    """在没有对话的情况下调用没有注册表，因此没有任何内容被屏蔽。"""
    for name, cls in _TOOLS.items():
        register_tool(name, cls)
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[Tool(name="FileEditorTool")])
    convo = LocalConversation(agent, workspace=str(tmp_path))
    convo._ensure_agent_ready()

    env = tmp_path / ".env"
    env.write_text(f"API_KEY={SECRET}\n")
    action = FileEditorAction(command="view", path=str(env))
    observation = convo.agent.tools_map["file_editor"](action, None)

    assert SECRET in observation.text


def _all_tool_definition_subclasses() -> set[type[ToolDefinition]]:
    """导入每个已发布的工具包，然后收集 ToolDefinition 个子类。"""
    import openhands.tools

    for module in pkgutil.walk_packages(
        openhands.tools.__path__, prefix="openhands.tools."
    ):
        try:
            importlib.import_module(module.name)
        except Exception:  # 可选的附加设施不能让警卫失望
            continue

    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    return set(walk(ToolDefinition))


def test_no_tool_bypasses_the_masking_chokepoint():
    """当新工具覆盖 __call__ 而不委托给 super() 时失败。

    这是问题所要求的属性：默认情况下涵盖工具#14。 构建自己的观测结果并默默返回它的覆
    盖选择不屏蔽，因此它必须经过 ``super().__call__``。
    """
    offenders = []
    for cls in _all_tool_definition_subclasses():
        override = cls.__dict__.get("__call__")
        if override is None:
            continue
        try:
            source = inspect.getsource(override)
        except (OSError, TypeError):  # pragma: no cover - source always available
            continue
        if "super().__call__" not in source:
            offenders.append(f"{cls.__module__}.{cls.__qualname__}")

    assert not offenders, (
        "These ToolDefinition subclasses override __call__ without delegating to "
        "super().__call__, so their output never reaches the secret-masking "
        f"chokepoint: {sorted(offenders)}"
    )
