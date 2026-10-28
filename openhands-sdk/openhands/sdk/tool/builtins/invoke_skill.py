from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.skills.execute import render_content_with_commands
from openhands.sdk.tool.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from openhands.sdk.utils.path import to_posix_path


if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation
    from openhands.sdk.conversation.state import ConversationState


class InvokeSkillAction(Action):
    name: str = Field(description="Name of the loaded skill to invoke.")

    @property
    def visualize(self) -> Text:
        t = Text()
        t.append("Invoke skill: ", style="bold blue")
        t.append(self.name)
        return t


class InvokeSkillObservation(Observation):
    skill_name: str = Field(
        description="Name of the skill this observation corresponds to."
    )

    @property
    def visualize(self) -> Text:
        t = Text()
        t.append(f"[skill: {self.skill_name}]\n", style="bold green")
        t.append(self.text)
        return t


TOOL_DESCRIPTION = """Invoke a skill by name.

This is the only supported way to invoke a skill listed in
`<available_skills>`. Call it with the `<name>` shown in that block; the
skill's full content is rendered (including any dynamic context) and
returned as the tool result.
"""


class InvokeSkillExecutor(ToolExecutor):
    @staticmethod
    def _get_skills_and_working_dir(
        conversation: BaseConversation | None,
    ) -> tuple[list, Path | None]:
        """从对话状态中提取技能目录和工作目录。"""
        if conversation is None:
            return [], None

        state = conversation.state
        ctx = state.agent.agent_context
        skills = list(ctx.skills) if ctx else []
        working_dir = state.workspace.working_dir
        return skills, Path(working_dir) if working_dir else None

    @staticmethod
    def _record_invocation(conversation: BaseConversation | None, name: str) -> None:
        """将 `name` 附加到对话的调用技能列表（已删除重复数据）。"""
        if conversation is None:
            return
        invoked = conversation.state.invoked_skills
        if name not in invoked:
            invoked.append(name)

    @staticmethod
    def _error(name: str, text: str) -> InvokeSkillObservation:
        return InvokeSkillObservation.from_text(
            text=text, is_error=True, skill_name=name
        )

    def __call__(
        self,
        action: InvokeSkillAction,
        conversation: BaseConversation | None = None,
    ) -> InvokeSkillObservation:
        skills, working_dir = self._get_skills_and_working_dir(conversation)
        name = action.name.strip()

        match = next((s for s in skills if s.name == name), None)
        if match is None:
            available = (
                ", ".join(
                    sorted(s.name for s in skills if not s.disable_model_invocation)
                )
                or "<none>"
            )
            return self._error(
                name, f"Unknown skill '{name}'. Available skills: {available}."
            )
        if match.disable_model_invocation:
            return self._error(
                name,
                (
                    f"Skill '{name}' cannot be invoked directly. "
                    "It can only be activated by trigger matching."
                ),
            )

        rendered = render_content_with_commands(match.content, working_dir=working_dir)
        rendered = self._append_skill_location_footer(
            rendered, match.source, working_dir
        )
        self._record_invocation(conversation, name)
        return InvokeSkillObservation.from_text(text=rendered, skill_name=name)

    @staticmethod
    def _append_skill_location_footer(
        rendered: str, source: str | None, working_dir: Path | None
    ) -> str:
        """添加一个尾注，将 LLM 指向技能的磁盘目录。

        AgentSkills 规范允许技能捆绑 `scripts/`、`references/` 和
        `assets/` 与 `SKILL.md` 并排。 技能作者通过相对路径引用这些技能，因此模型需要
        知道技能所在的位置才能到达它们。

        当技能位于对话的 `working_dir` 时，路径将相对于它来避免将绝对的家目录路径泄露
        到 LLM 上下文。
        """
        if not source:
            return rendered
        try:
            skill_md = Path(source).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return rendered
        if not skill_md.is_file():
            return rendered
        skill_dir = skill_md.parent
        display: Path = skill_dir
        if working_dir is not None:
            try:
                display = skill_dir.relative_to(working_dir.resolve())
            except (ValueError, OSError):
                pass  # 技能存在于 working_dir 之外，保持绝对
        footer = (
            f"\n\n---\n"
            f"This skill is located at `{to_posix_path(display)}`. "
            f"Any files it references (e.g. under `scripts/`, `references/`, "
            f"`assets/`) are relative to that directory."
        )
        return rendered + footer


class InvokeSkillTool(ToolDefinition[InvokeSkillAction, InvokeSkillObservation]):
    """用于显式调用渐进式披露技能的内置工具。"""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:
        # 渲染技能可以执行内联`!`cmd``token，它可以触及任意磁盘状态。 键入技能名称可序列
        # 化并发同一技能的调用，同时仍允许并行渲染不同的技能。
        #
        name = action.name if isinstance(action, InvokeSkillAction) else ""
        return DeclaredResources(keys=(f"skill:{name.strip()}",), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: ConversationState | None = None,  # noqa: ARG003
        **params,
    ) -> Sequence[Self]:
        if params:
            raise ValueError("InvokeSkillTool doesn't accept parameters")
        return [
            cls(
                action_type=InvokeSkillAction,
                observation_type=InvokeSkillObservation,
                description=TOOL_DESCRIPTION,
                executor=InvokeSkillExecutor(),
                annotations=ToolAnnotations(
                    title="invoke_skill",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]
