"""ApplyPatch ToolDefinition 和执行器集成了说明书的实现。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)
from openhands.sdk.tool.tool import FunctionToolParam

from .core import Commit, DiffError, process_patch


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class ApplyPatchAction(Action):
    """工具操作模式指定要应用的补丁。

    该补丁必须遵循 OpenAI Cookbook 的 GPT-5.1 提示指南中描述的确切文本格式。 执行器解
    析此补丁并应用相对于当前工作区根的更改。
    """

    patch: str = Field(
        description=(
            "Patch content following the '*** Begin Patch' ... '*** End Patch' "
            "format as described in OpenAI GPT-5.1 prompting guide."
        ),
    )


class ApplyPatchObservation(Observation):
    """应用补丁的结果。

    - message: 人类可读的更改或错误摘要
    - fuzz: 应用 hunk 时使用的模糊行数（0 表示精确）
    - commit: 应用操作的结构化摘要
    """

    message: str = ""
    fuzz: int = 0
    commit: Commit | None = None


class ApplyPatchExecutor(ToolExecutor[ApplyPatchAction, ApplyPatchObservation]):
    """在工作区内应用统一文本补丁的执行器。

    使用 core.py 中的纯函数来解析和应用补丁。 所有文件系统访问都仅限于智能体的
    workspace_root。
    """

    def __init__(self, workspace_root: str):
        """使用工作区 root 初始化执行器。

        Args:
            workspace_root: 所有补丁路径相对于的基目录
                解决了。 绝对或路径转义引用将被拒绝。
        """
        self.workspace_root = Path(workspace_root).resolve()

    def _resolve_path(self, p: str) -> Path:
        """将文件路径解析为工作区，不允许转义。"""
        pth = (
            (self.workspace_root / p).resolve()
            if not p.startswith("/")
            else Path(p).resolve()
        )
        if not pth.is_relative_to(self.workspace_root):
            raise DiffError("Absolute or escaping paths are not allowed")
        return pth

    def __call__(
        self,
        action: ApplyPatchAction,
        conversation=None,  # noqa: ARG002 - signature match
    ) -> ApplyPatchObservation:
        """执行补丁应用程序并返回观测结果。"""

        def open_file(path: str) -> str:
            fp = self._resolve_path(path)
            with open(fp, encoding="utf-8") as f:
                return f.read()

        def write_file(path: str, content: str) -> None:
            fp = self._resolve_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)

        def remove_file(path: str) -> None:
            fp = self._resolve_path(path)
            fp.unlink(missing_ok=False)

        try:
            msg, fuzz, commit = process_patch(
                action.patch, open_file, write_file, remove_file
            )
            # 在内容中包含人类可读的摘要，以便响应 API 看到与 function_call 配对的
            # function_call_output 载荷。
            #
            obs = ApplyPatchObservation(message=msg, fuzz=fuzz, commit=commit)
            if msg:
                # 使用 Observation.from_text 正确填充内容字段
                obs = ApplyPatchObservation.from_text(
                    text=msg, message=msg, fuzz=fuzz, commit=commit, is_error=False
                )
            return obs
        except DiffError as e:
            return ApplyPatchObservation.from_text(text=str(e), is_error=True)


_DESCRIPTION = (
    "Apply unified text patches to files in the workspace. "
    "Input must start with '*** Begin Patch' and end with '*** End Patch'."
)


class ApplyPatchTool(ToolDefinition[ApplyPatchAction, ApplyPatchObservation]):
    """ToolDefinition 用于应用统一文本补丁。

    创建绑定到当前工作区的 ApplyPatchExecutor 并提供简洁的描述。 响应工具模式已最小化
    ，以依赖 GPT-5.1 模型的提供者已知行为。
    """

    @classmethod
    def create(cls, conv_state: ConversationState) -> Sequence[ApplyPatchTool]:
        """初始化活动对话状态的工具。"""
        executor = ApplyPatchExecutor(workspace_root=conv_state.workspace.working_dir)
        return [
            cls(
                description=_DESCRIPTION,
                action_type=ApplyPatchAction,
                observation_type=ApplyPatchObservation,
                annotations=ToolAnnotations(
                    title="apply_patch",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]

    # 对于 GPT-5.1 模型的 OpenAI 响应 API，该工具是服务器已知的。 返回一个最小的函数规范
    # ，以便提供者连接其自己的定义。
    #
    def to_responses_tool(
        self,
        add_security_risk_prediction: bool = False,  # noqa: ARG002 - signature match
        action_type: type | None = None,  # noqa: ARG002 - signature match
    ) -> FunctionToolParam:  # type: ignore[override]
        """序列化至 OpenAI 响应功能工具规格。

        GPT-5.1 工具是已知的服务器端工具。 我们返回一个最小的模式以确保模型在调用此工
        具时包含规范的“补丁”参数。
        """
        return {
            "type": "function",
            "name": self.name,
            "parameters": {
                "type": "object",
                "properties": {"patch": {"type": "string"}},
                "required": ["patch"],
            },
            "strict": False,
        }  # type: ignore[return-value]


register_tool(ApplyPatchTool.name, ApplyPatchTool)
