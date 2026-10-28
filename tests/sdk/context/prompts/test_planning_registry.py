"""规划预设：``system_prompt_planning.j2``的逐字节端口。

确认奇偶性后，``.j2`` 被删除，因此计划组合现在固定在黄金快照上（使用
``REGEN_PROMPT_SNAPSHOTS=1`` 重新生成）。 规划提示词是一个独立的
部分，因此单元测试直接练习该部分 - 没有智能体，没有 Jinja 环境。
"""

import os
from pathlib import Path
from typing import Final

from openhands.sdk.context.prompts.presets import PromptPreset, create_registry
from openhands.sdk.context.prompts.section import Platform, PromptContext
from openhands.sdk.context.prompts.sections.planning import PlanningSection


SNAPSHOT_DIR: Final[Path] = Path(__file__).parent / "snapshots"
REGEN: Final[bool] = os.environ.get("REGEN_PROMPT_SNAPSHOTS") == "1"

# 代表 plan_structure（模板的唯一替换）。 保持内联，因此 SDK 测试不依赖于 OpenHands-工具
# 的 format_plan_structure()。
#
PLAN_STRUCTURE: Final[str] = (
    "The plan must follow this structure exactly:\n\n"
    "1. OBJECTIVE\n   * Summarize the goal of the plan in one or two sentences.\n\n"
    "2. IMPLEMENTATION STEPS\n   * Provide a step-by-step plan for execution."
)


def _ctx(
    platform: Platform = Platform.LINUX, **template_kwargs: object
) -> PromptContext:
    return PromptContext(template_kwargs=template_kwargs, platform=platform)


def _check_snapshot(name: str, content: str) -> None:
    path = SNAPSHOT_DIR / f"{name}.txt"
    if REGEN:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    assert path.exists(), (
        f"Missing snapshot {path}. Regenerate with REGEN_PROMPT_SNAPSHOTS=1."
    )
    assert content == path.read_text(encoding="utf-8"), (
        f"Planning prompt for '{name}' diverged from its committed snapshot. If the "
        "change is intentional, regenerate with REGEN_PROMPT_SNAPSHOTS=1."
    )


def test_planning_registry_static_snapshot() -> None:
    ctx = _ctx(plan_structure=PLAN_STRUCTURE)
    blocks = create_registry(PromptPreset.PLANNING).build(ctx)
    # 规划预设在此没有注册动态数据，因此动态块为空。
    assert blocks.dynamic is None
    _check_snapshot("planning__default", blocks.static)


def test_planning_is_standalone_composition() -> None:
    ctx = _ctx(plan_structure=PLAN_STRUCTURE)
    static = create_registry(PromptPreset.PLANNING).build(ctx).static
    assert static.startswith("You are a Planning Agent")
    # 独立：默认 OpenHands 部分的 None 泄漏。
    for tag in ("<SOUL>", "<SECURITY>", "<MEMORY>", "<VERSION_CONTROL>", "<IMPORTANT>"):
        assert tag not in static
    for tag in ("<ROLE>", "<PLANNING_WORKFLOW>", "<PLAN_SCOPE>", "<PLAN_STRUCTURE>"):
        assert tag in static


def test_planning_section_is_unguarded() -> None:
    assert PlanningSection().guard(_ctx()) is True


def test_planning_section_substitutes_plan_structure() -> None:
    out = PlanningSection().render(_ctx(plan_structure="STEP ONE")) or ""
    assert "<PLAN_STRUCTURE>\nSTEP ONE\n</PLAN_STRUCTURE>" in out
    # 空的 plan_structure 会逐字重现模板的空行正文。
    empty = PlanningSection().render(_ctx()) or ""
    assert empty.endswith("<PLAN_STRUCTURE>\n\n</PLAN_STRUCTURE>")


def test_planning_uses_glob_grep_and_is_platform_invariant() -> None:
    # 计划 <EFFICIENCY> 表示“glob 和 grep”（不是 bash/git），因此 Windows shell 替换是无
    # 操作的，并且提示词跨平台是相同的。
    #
    posix = PlanningSection().render(_ctx(platform=Platform.LINUX)) or ""
    windows = PlanningSection().render(_ctx(platform=Platform.WINDOWS)) or ""
    assert "glob and grep" in posix
    assert "bash" not in posix and "powershell" not in posix
    assert windows == posix


def test_planning_dynamic_tier_is_shared_with_default() -> None:
    # 动态层与预设无关：相同的上下文产生相同的块。
    ctx = PromptContext(
        now="2025-01-01T00:00:00+00:00",
        custom_suffix="Follow conventions.",
        secret_infos=(("GITHUB_TOKEN", None),),
        template_kwargs={"plan_structure": PLAN_STRUCTURE},
    )
    planning = create_registry(PromptPreset.PLANNING).build(ctx).dynamic
    default = create_registry(PromptPreset.DEFAULT).build(ctx).dynamic
    assert planning == default
    assert "<CURRENT_DATETIME>" in (planning or "")
