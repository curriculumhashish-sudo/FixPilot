"""任务工具定义和注册。

该模块定义了模式和子智能体任务委托的工具类。 它包含：
- TaskTool 的行动/观察模型 (TaskAction, TaskObservation)
- TaskTool 的工具说明

此外，它还注册了两个工具类 TaskTool（单个工具）和 TaskToolSet（连接 TaskManager 支持
的执行器的入口点）。
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Final

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from rich.text import Text

from openhands.sdk import ImageContent, TextContent
from openhands.sdk.event.types import UnmaskedID
from openhands.sdk.logger import get_logger
from openhands.sdk.subagent import (
    AgentDefinition,
    SubAgentScope,
    get_factory_info,
    get_registered_agent_definitions,
)
from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)


if TYPE_CHECKING:
    from openhands.sdk.agent.base import AgentBase
    from openhands.sdk.conversation.state import ConversationState
    from openhands.tools.task.impl import TaskExecutor
    from openhands.tools.task.manager import ConfirmationHandler


logger = get_logger(__name__)


class TaskAction(Action):
    """模式用于启动子智能体任务。"""

    description: str | None = Field(
        default=None,
        description="A short (3-5 word) description of the task.",
    )
    prompt: str = Field(
        description="The task for the agent to perform.",
    )
    subagent_type: str = Field(
        default="general-purpose",
        description="The type of specialized agent to use for this task.",
    )
    resume: str | None = Field(
        default=None,
        description="Task ID of the task to resume from.",
    )
    max_turns: SkipJsonSchema[int | None] = Field(
        default=None,
        description="Deprecated: This field is ignored and will be removed "
        "in version 2. Maximum iterations are now determined by "
        "the agent definition or parent conversation.",
        deprecated=True,
        ge=1,
    )


class TaskObservation(Observation):
    """观测结果来自任务执行。"""

    task_id: UnmaskedID = Field(description="The unique identifier of the task.")
    subagent: str = Field(description="The subagent of the task.")
    status: str = Field(description="The status of the task.")

    def _get_task_info(self) -> str:
        return (
            f"Task ID: {self.task_id}\nSubagent: {self.subagent}\nStatus: {self.status}"
        )

    @property
    def visualize(self) -> Text:
        text = Text()
        text.append(self._get_task_info(), style="blue")
        text.append("\n")

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        text.append(self.text)
        return text

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        """
        用于将观测结果转换为 LLM 可读内容的默认内容格式。 子类可以重写以提供更丰富的
        内容（e.g.、图像、差异）。
        """
        llm_content: list[TextContent | ImageContent] = [
            TextContent(text=self._get_task_info())
        ]

        # 如果 is_error 为 True，则添加错误消息
        if self.is_error:
            llm_content.append(TextContent(text=self.ERROR_MESSAGE_HEADER))

        # 添加内容（现在始终是列表）
        llm_content.extend(self.content)

        return llm_content


TASK_TOOL_DESCRIPTION: Final[
    str
] = """Launch a subagent to handle complex, multi-step tasks autonomously.

Subagents are autonomous agents that work independently and return results to you. They are your primary tool for understanding codebases and running
tests, but each delegation has overhead — use them when the task genuinely benefits from a separate agent, not for simple lookups.

Available agent types and the tools they have access to:
{agent_types_info}

When NOT to use the task tool:
- A single grep, find, or cat command would answer your question — just run it yourself
- You are making a file edit (use file_editor directly)
- You already have the context needed

When using the task tool:
- Write a detailed prompt describing exactly what you need
- Include specific file paths, class names, or error messages from the issue
- Tell the agent what to report back (file paths, line numbers, code snippets)
- The agent's results are authoritative — verify subagent results only when the task involves judgment or
  interpretation.
  
{task_tool_examples}
"""  # noqa: E501

TASK_TOOL_EXAMPLES: Final[dict[str, str]] = {
    "code-explorer": """
Example — Multi-step exploration (good use of code-explorer):
    subagent_type="code-explorer"
    prompt="Trace how the DateFormat.y() method is called through Django's
    template system. Find: (1) the method definition, (2) where it's
    registered as a format character, (3) all test cases. Include code
    snippets and file paths."
""",
    "bash-runner": """
Example — Running tests (good use of bash-runner):
    subagent_type="bash-runner"
    prompt="Run: cd /workspace/django && python tests/runtests.py
    utils_tests.test_dateformat -v 2. Provide a summary including
    the total tests run, the final status, and a list of any
    failing test names. For each failure, include the specific
    cause or assertion error, but do not include the full stack
    trace or the verbose setup/teardown output."
""",
    "web researcher": """
Example — Research information on a website (good use of web researcher):
    subagent_type="web researcher"
    prompt="Navigate to the Stripe API docs and find the parameters for the PaymentIntent create endpoint."
""",  # noqa: E501
    "general purpose": """
Example — Perform a multi-step task involving code editing and shell commands:
    subagent_type="general purpose"
    prompt="Read the database module in src/db.py, extract the connection
    pooling logic into a separate file, update all imports, and run the
    test suite to verify nothing breaks."
""",
}


class TaskTool(ToolDefinition[TaskAction, TaskObservation]):
    """用于启动（阻止）子智能体任务的工具。"""

    user_selectable: ClassVar[bool] = False

    def declared_resources(self, action: Action) -> DeclaredResources:  # noqa: ARG002
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(
        cls,
        executor: "TaskExecutor",
        description: str,
    ) -> Sequence["TaskTool"]:
        return [
            cls(
                action_type=TaskAction,
                observation_type=TaskObservation,
                description=description,
                annotations=ToolAnnotations(
                    title="task",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


class TaskToolSet(ToolDefinition[TaskAction, TaskObservation]):
    """任务工具集。

    创建由共享 TaskManager 支持的任务工具。

    用途：
        from openhands.tools.task import TaskToolSet

        agent = Agent(
            llm=llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
                Tool(name=TaskToolSet.name),
            ],
        )
    """

    catalog_description: ClassVar[str] = (
        "Delegate a self-contained sub-task to a separate agent."
    )

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        confirmation_handler: "ConfirmationHandler | None" = None,
        sub_agent_scope: SubAgentScope | dict[str, bool] | None = None,
    ) -> list[ToolDefinition]:
        """创建任务工具。

        Args:
            conv_state: 工作区信息的对话状态。
            confirmation_handler: 当子智能体的时候调用可选的回调
                确认策略需要用户批准。 收到
                `(task_id, pending_actions)` 并且必须返回 `True` 表示批准或返回
                `False` 表示拒绝。
            sub_agent_scope: 它提供和启动的子智能体是否必须
                留在这个智能体的工具中。 子智能体始终继承此智能体的 MCP 服务器。

        Returns:
            包含单个 TaskTool 的列表。
        """
        from openhands.tools.task.impl import TaskExecutor, TaskManager

        scope = SubAgentScope.model_validate(sub_agent_scope or {})
        registered = {
            d.name
            for d in get_registered_agent_definitions()
            if not scope.restricts or _offered(scope, conv_state.agent, d)
        }
        if not scope.restricts:
            agent_types_info = get_factory_info()
        elif registered:
            agent_types_info = get_factory_info(lambda d: d.name in registered)
        else:
            agent_types_info = (
                "- None: every registered agent uses tools this agent does not have."
            )

        task_tool_examples = "\n".join(
            ex for name, ex in TASK_TOOL_EXAMPLES.items() if name in registered
        )

        task_description = TASK_TOOL_DESCRIPTION.format(
            agent_types_info=agent_types_info,
            task_tool_examples=task_tool_examples,
        )

        manager = TaskManager(
            confirmation_handler=confirmation_handler, sub_agent_scope=scope
        )
        task_executor = TaskExecutor(manager=manager)

        tools: list[ToolDefinition] = []
        tools.extend(
            TaskTool.create(
                executor=task_executor,
                description=task_description,
            )
        )
        return tools


def _offered(
    scope: SubAgentScope, parent: "AgentBase", definition: AgentDefinition
) -> bool:
    missing = scope.missing_from(parent, definition)
    if missing:
        logger.info(
            "Not offering sub-agent %r: it uses %s, which this agent lacks",
            definition.name,
            ", ".join(missing),
        )
    return not missing


# 导入该模块时自动注册
register_tool(TaskToolSet.name, TaskToolSet)
register_tool(TaskTool.name, TaskTool)
