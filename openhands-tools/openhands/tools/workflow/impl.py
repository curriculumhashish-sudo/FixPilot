"""动态工作流工具的实现。"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json as jsonlib
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from openhands.sdk.logger import get_logger
from openhands.sdk.subagent import SubAgentScope
from openhands.sdk.tool import ToolExecutor
from openhands.tools.task.manager import TaskManager
from openhands.tools.workflow.definition import WorkflowObservation


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation
    from openhands.tools.workflow.definition import WorkflowAction

logger = get_logger(__name__)

_MAX_SCRIPT_CHARS = 20_000
_MAX_REDUCE_INPUT_CHARS = 12_000
_TRUNCATION_MARKER = "\n... [truncated workflow intermediate results]"
_WORKFLOW_TIMEOUT_SECONDS = 3600.0  # 1小时； 防止无限期挂起的工作流程
_UNSAFE_CALLS = frozenset(
    {
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
        "__import__",
    }
)
# 属性根拒绝列表是故意狭窄的：脚本不能导入模块，因此仅需在这里列出通过 _safe_globals()
# 预注入的名称。 os 和子进程是如果不经意暴露的话危害最大的两个。
#
_UNSAFE_ATTRIBUTE_ROOTS = frozenset({"os", "subprocess"})


class WorkflowScriptError(ValueError):
    """当工作流脚本无效或不安全时引发。"""


class _TaskLike(Protocol):
    result: str | None
    error: str | None


class _TaskStarter(Protocol):
    def start_task(
        self,
        prompt: str,
        subagent_type: str = "default",
        resume: str | None = None,
        description: str | None = None,
        conversation: LocalConversation | None = None,
    ) -> _TaskLike: ...

    def close(self) -> None: ...


class WorkflowContext:
    """向生成的工作流脚本公开的小型功能对象。"""

    def __init__(
        self,
        parent_conversation: LocalConversation,
        max_concurrency: int,
        manager: _TaskStarter | None = None,
        sub_agent_scope: SubAgentScope | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._parent_conversation = parent_conversation
        self._max_concurrency = max_concurrency
        if manager is None:
            task_manager = TaskManager(sub_agent_scope=sub_agent_scope)
            task_manager.attach_parent(parent_conversation)
            self._manager = task_manager
        else:
            self._manager = manager
        self._semaphore: asyncio.Semaphore | None = None
        self._closed = False

    @property
    def _default_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
        return self._semaphore

    async def run_agent(
        self,
        prompt: str,
        subagent_type: str = "general-purpose",
        description: str | None = None,
    ) -> str:
        """运行单个子智能体任务并返回其最终结果。"""
        async with self._default_semaphore:
            return await self._run_agent_task(
                prompt=prompt,
                subagent_type=subagent_type,
                description=description,
            )

    async def _run_agent_task(
        self,
        prompt: str,
        subagent_type: str,
        description: str | None,
    ) -> str:
        # 注意：`_TaskStarter.start_task` 接受 `resume` 参数，但是
        # 工作流程子智能体始终是新鲜任务； 故意不通过 MVP 中的 WorkflowContext 暴露恢复
        # 。
        #
        if self._closed:
            raise WorkflowScriptError("WorkflowContext is already closed")
        task = await asyncio.to_thread(
            self._manager.start_task,
            prompt=prompt,
            subagent_type=subagent_type,
            description=description,
            conversation=self._parent_conversation,
        )
        if task.error:
            raise RuntimeError(task.error)
        return task.result or ""

    async def map_agents(
        self,
        items: Sequence[Any],
        prompt: Callable[[Any], str] | str,
        subagent_type: str = "general-purpose",
        max_concurrency: int | None = None,
        description: Callable[[Any], str] | str | None = None,
    ) -> list[str]:
        """每个项目运行一个子智能体任务并按项目顺序返回结果。

        每次调用 ``max_concurrency`` caps 并发仅适用于此映射操作； 它默默地限制在上下
        文的 ``max_concurrency`` 限制。
        """
        if max_concurrency is not None and max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        semaphore = (
            asyncio.Semaphore(min(max_concurrency, self._max_concurrency))
            if max_concurrency is not None
            else self._default_semaphore
        )

        async def run_one(index: int, item: Any) -> str:
            rendered_prompt = _render_required_template(prompt, item)
            rendered_description = _render_template(description, item)
            async with semaphore:
                try:
                    return await self._run_agent_task(
                        prompt=rendered_prompt,
                        subagent_type=subagent_type,
                        description=rendered_description,
                    )
                except Exception as exc:
                    raise RuntimeError(f"[item {index + 1}] {exc}") from exc

        results = await asyncio.gather(
            *(run_one(i, item) for i, item in enumerate(items)),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            exceptions = [
                failure
                if isinstance(failure, Exception)
                else RuntimeError(str(failure))
                for failure in failures
            ]
            raise ExceptionGroup(
                "map_agents: one or more sub-agents failed",
                exceptions,
            )
        return [str(result) for result in results]

    async def pipeline(
        self,
        items: Sequence[Any],
        *stages: Callable[[Any], Any],
    ) -> list[Any]:
        """独立运行每个项目通过所有阶段，之间没有障碍
        stages: 快的项目可以到达较晚的阶段，而慢的项目仍处于较晚的阶段
        较早的一个。 第一阶段接收原始物品； 每个后面的阶段都会收到前一个阶段的结果。
        阶段可以是同步或异步。 提升的阶段会将该项目降至 ``None`` 并跳过其
        剩余阶段； 其他项目不受影响。

        并发受到阶段内的智能体调用（获取共享信号量）的限制，因此管道不会添加自己的屏
        障。 没有阶段直接重新获取信号量； 呼叫``run_agent``
        /``map_agents``.
        """
        if not stages:
            raise ValueError("pipeline requires at least one stage")

        async def run_chain(index: int, item: Any) -> Any:
            value: Any = item
            try:
                for stage in stages:
                    result = stage(value)
                    value = await result if inspect.isawaitable(result) else result
                return value
            except Exception as exc:
                logger.warning("pipeline: item %d failed: %s", index + 1, exc)
                return None

        return list(
            await asyncio.gather(*(run_chain(i, item) for i, item in enumerate(items)))
        )

    async def reduce_agent(
        self,
        items: Any,
        prompt: str,
        subagent_type: str = "general-purpose",
        description: str | None = None,
    ) -> str:
        """运行具有已序列化中间结果的单个减速器子智能体。

        委托给 ``run_agent``，它获取 ``_default_semaphore``。 工作流脚本始终按顺序等
        待操作，因此在调用
        ``reduce_agent`` 时信号量始终完全可用。
        """
        return await self.run_agent(
            prompt=f"{prompt}\n\nInput:\n{_format_value(items)}",
            subagent_type=subagent_type,
            description=description,
        )

    def flatten(self, values: list[Any]) -> list[Any]:
        """展平一个列表级别。"""
        flattened: list[Any] = []
        for value in values:
            if isinstance(value, list):
                flattened.extend(value)
            else:
                flattened.append(value)
        return flattened

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._manager.close()


def _render_required_template(template: Callable[[Any], str] | str, item: Any) -> str:
    if callable(template):
        return str(template(item))
    # 普通替换避免了 Python 的格式迷你语言属性遍历 (e.g. “{item._manager}”），这将绕过
    # AST 私有属性保护。
    #
    if "{item}" not in template:
        logger.debug(
            "map_agents string template does not contain '{item}'; "
            "all sub-agents will receive the same prompt."
        )
    # 对非 str 项使用 json.dumps，以便字典/列表和标量一致序列化为 JSON（布尔值 → true/
    # false，None → null），匹配 reduce_agent。
    #
    serialised = item if isinstance(item, str) else jsonlib.dumps(item, default=str)
    return template.replace("{item}", serialised)


def _render_template(
    template: Callable[[Any], str] | str | None, item: Any
) -> str | None:
    if template is None:
        return None
    return _render_required_template(template, item)


def _format_value(value: Any) -> str:
    """序列化减少减速器提示词的输入，边界为
    ``_MAX_REDUCE_INPUT_CHARS``. 对于列表/字典，删除整个尾随元素（保持有效 JSON）并报
    告省略了多少个元素，而不是切片中间 token；
     其他一切都回到字符截断。
    """
    if isinstance(value, (list, dict)):
        return _truncate_structured(value)
    text = value if isinstance(value, str) else jsonlib.dumps(value, default=str)
    return _truncate_text(text)


def _truncate_text(text: str) -> str:
    if len(text) <= _MAX_REDUCE_INPUT_CHARS:
        return text
    return text[:_MAX_REDUCE_INPUT_CHARS] + _TRUNCATION_MARKER


def _truncate_structured(value: list | dict) -> str:
    """保留尽可能多的前导元素，删除整个元素，以便 JSON
    保持有效。 始终保留至少一个元素； 作为最后的手段，单个超大元素会被字符截断。
    """
    full = jsonlib.dumps(value, indent=2, default=str)
    if len(full) <= _MAX_REDUCE_INPUT_CHARS:
        return full

    is_dict = isinstance(value, dict)
    items = list(value.items()) if is_dict else list(value)
    total = len(items)

    def render(kept: list) -> str:
        body = jsonlib.dumps(dict(kept) if is_dict else kept, indent=2, default=str)
        dropped = total - len(kept)
        if not dropped:
            return body
        return (
            f"{body}\n... [{dropped} of {total} items omitted to fit the "
            "reduce input limit]"
        )

    # 通过逐元素估计填充，然后纠正以与实际的总和序列化 （大于部分之和）相匹配，以确保结
    # 果在不切分 token 时无缝拼接。
    #
    kept: list = []
    used = 0
    for item in items:
        chunk = jsonlib.dumps(dict([item]) if is_dict else item, default=str)
        if kept and used + len(chunk) > _MAX_REDUCE_INPUT_CHARS:
            break
        kept.append(item)
        used += len(chunk)
    while len(kept) > 1 and len(render(kept)) > _MAX_REDUCE_INPUT_CHARS:
        kept.pop()

    # 安全网：单个超大元素仍然可能超出预算。
    return _truncate_text(render(kept))


def validate_workflow_script(script: str) -> None:
    """对生成的工作流脚本执行尽力而为验证。

    Note: 私有属性保护检查字面名称 ``wf``，因此别名
    (e.g. ``x = wf; x._attr``) 可以绕过检查。 通过``WorkflowContext``访问的属性不会暴
    露危险的功能，因此这是一个文档漏洞而
    不是安全漏洞。
    """
    if len(script) > _MAX_SCRIPT_CHARS:
        raise WorkflowScriptError(
            f"Workflow script is too large: {len(script)} > {_MAX_SCRIPT_CHARS}"
        )

    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        raise WorkflowScriptError(f"Workflow script has invalid syntax: {e}") from e

    main_defs = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"
    ]
    if len(main_defs) != 1:
        raise WorkflowScriptError(
            "Workflow script must define exactly one async main(wf)"
        )

    main_args = main_defs[0].args
    if (
        [a.arg for a in main_args.args] != ["wf"]
        or main_args.kwonlyargs
        or main_args.vararg
        or main_args.kwarg
        or main_args.defaults
        or main_args.posonlyargs
    ):
        raise WorkflowScriptError("Workflow entry point must be `async def main(wf):`")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise WorkflowScriptError("Workflow scripts may not import modules")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise WorkflowScriptError("Workflow scripts may not access dunder names")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise WorkflowScriptError(
                "Workflow scripts may not access dunder attributes"
            )
        if (
            isinstance(node, ast.Attribute)
            and _attribute_root_name(node) == "wf"
            and (node.attr.startswith("_") or node.attr == "close")
        ):
            raise WorkflowScriptError(
                "Workflow scripts may not access private wf attributes"
                " or call wf.close()"
            )
        if (
            isinstance(node, ast.Attribute)
            and _attribute_root_name(node) in _UNSAFE_ATTRIBUTE_ROOTS
        ):
            raise WorkflowScriptError("Workflow scripts may not access unsafe modules")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _UNSAFE_CALLS
        ):
            raise WorkflowScriptError(f"Workflow scripts may not call `{node.func.id}`")


def _attribute_root_name(node: ast.Attribute) -> str | None:
    value = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    return value.id if isinstance(value, ast.Name) else None


def execute_workflow_script(script: str, context: WorkflowContext) -> Any:
    """验证并执行同步上下文中的工作流脚本。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise WorkflowScriptError(
            "Workflow scripts must be executed from a synchronous context"
        )

    validate_workflow_script(script)
    namespace: dict[str, Any] = {}
    exec(compile(script, "<dynamic-workflow>", "exec"), _safe_globals(), namespace)
    main = namespace.get("main")
    if not inspect.iscoroutinefunction(main):
        raise WorkflowScriptError("Workflow entry point must be async")

    async def _run_with_timeout() -> Any:
        async with asyncio.timeout(_WORKFLOW_TIMEOUT_SECONDS):
            return await main(context)

    try:
        return asyncio.run(_run_with_timeout())
    except TimeoutError:
        raise WorkflowScriptError(
            f"Workflow timed out after {_WORKFLOW_TIMEOUT_SECONDS:.0f} seconds"
        ) from None


def _format_exception(error: Exception) -> str:
    if isinstance(error, ExceptionGroup):
        details = "\n".join(
            f"  [{index}] {exception}"
            for index, exception in enumerate(error.exceptions, start=1)
        )
        return f"{error.args[0]}:\n{details}"
    return str(error)


def _safe_globals() -> dict[str, Any]:
    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "Exception": Exception,
        "float": float,
        "IndexError": IndexError,
        "int": int,
        "isinstance": isinstance,
        "KeyError": KeyError,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "print": print,
        "range": range,
        "repr": repr,
        "round": round,
        "RuntimeError": RuntimeError,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        # type() is included for 1-arg introspection (e.g. type(x).__name__).
        # 允许创建 3-arg 类； 方法 DEFINED IN THE  SCRIPT 在受限全局中执行，以及 AST  验
        # 证器块 __dunder__ 属性访问 (关闭) __子类__-based escapes) 调用现有的注入对象，
        # 如 wf，不会重新沙盒化，但它们只暴露公共 wf API.
        #
        "type": type,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "zip": zip,
        "format": format,
    }
    return {"__builtins__": safe_builtins}


class WorkflowExecutor(ToolExecutor["WorkflowAction", WorkflowObservation]):
    """动态工作流工具的执行器。"""

    def __init__(self, sub_agent_scope: SubAgentScope | None = None) -> None:
        self._sub_agent_scope = sub_agent_scope

    def __call__(
        self,
        action: WorkflowAction,
        conversation: LocalConversation | None = None,
    ) -> WorkflowObservation:
        if conversation is None:
            return WorkflowObservation.from_text(
                text="Workflow tool requires a local conversation context.",
                name=action.name,
                status="error",
                is_error=True,
            )

        context = WorkflowContext(
            parent_conversation=conversation,
            max_concurrency=action.max_concurrency,
            sub_agent_scope=self._sub_agent_scope,
        )
        try:
            result = execute_workflow_script(action.script, context)
            return WorkflowObservation.from_text(
                text=str(result),
                name=action.name,
                status="completed",
            )
        except Exception as e:
            error_text = _format_exception(e)
            logger.warning("Workflow '%s' failed: %s", action.name, e, exc_info=True)
            return WorkflowObservation.from_text(
                text=error_text,
                name=action.name,
                status="error",
                is_error=True,
            )
        finally:
            context.close()
