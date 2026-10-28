"""可观测性跨度为 ACP 圈。

ACP 子进程运行自己的推理和工具执行，因此 lmnr 的 LiteLLM 仪器和
``Agent._execute_action_event`` 从不触发，ACP 跟踪中
没有 ``LLM`` 或 ``TOOL`` 跨度。 该模块发出它们
from the ACP protocol's own notifications, shaped like the native ones so a
跟踪消费者不需要 ACP 特定的分支。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from openhands.sdk.agent.acp_contracts import is_model_dumpable
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import should_enable_observability


if TYPE_CHECKING:
    from lmnr.sdk.types import LaminarSpanContext

logger = get_logger(__name__)

# ：将跨度标记为由 ACP 智能体而不是本机循环生成。
AGENT_KIND_METADATA_KEY = "agent_kind"
# ：哪个 ACP CLI 产生了它：一个 ACP_PROVIDERS 密钥，或“自定义”。
ACP_SERVER_METADATA_KEY = "acp_server"
# ：当报告 1 时，对报告的 ACP CLI 进行建模。
ACP_MODEL_METADATA_KEY = "acp_model"

TURN_SPAN_NAME = "acp.completion"


def _truncate(value: Any, limit: int = 100_000) -> Any:
    """限制跨度所承载的内容。

    非字符串的值通过它们来测量已序列化当过大的时候，尺寸和规格会全部替换掉，而不是通
    过：一个 ACP  提示词这是一个内容块列表，一个图像块可以包含数兆字节的 base
    64。
    """
    if isinstance(value, str):
        return value[:limit] + "…[truncated]" if len(value) > limit else value
    try:
        rendered = json.dumps(value, default=str)
    except Exception:
        return value
    if len(rendered) <= limit:
        return value
    return rendered[:limit] + "…[truncated]"


class ACPTurnTrace:
    """每 ACP 转发出一个 ``LLM`` 范围，每工具调用发出一个 ``TOOL`` 范围。

    当可观察性被禁用时，每个方法都是无操作的，并且没有方法可以
    raise: a tracing failure must not take down the turn it is describing.

    工具通知到达  ACP 执行器的事件循环线程在被叫方打开和关闭时，孩子由显式 span 亲代
    上下文而不是通过环境 ``contextvars`` 共享状态在下被修改
    锁。 Span I/O 保持在外部锁，除了
    ``start_turn``，其中跨度必须作为一个步骤创建和存储，因此重试无法打开第二个跨度。
    """

    def __init__(
        self,
        acp_server: str | None,
        model_id: str | None,
        mask: Callable[[str], str] | None = None,
    ) -> None:
        self._mask = mask
        self._enabled = should_enable_observability()
        self._metadata: dict[str, Any] = {AGENT_KIND_METADATA_KEY: "acp"}
        if acp_server:
            self._metadata[ACP_SERVER_METADATA_KEY] = acp_server
        if model_id:
            self._metadata[ACP_MODEL_METADATA_KEY] = model_id
        self._turn_span: Any = None
        self._turn_context: LaminarSpanContext | None = None
        self._tool_spans: dict[str, Any] = {}
        self._lock = threading.Lock()

    def start_turn(self, prompt: Any) -> None:
        if not self._enabled:
            return
        try:
            from lmnr import Laminar

            # 像所有其他突变一样，在锁下：重试重新进入此
            # while the portal thread may still be delivering notifications from
            # 刚刚失败的尝试。
            with self._lock:
                if self._turn_span is not None:
                    return
                span = Laminar.start_span(
                    name=TURN_SPAN_NAME,
                    input=_truncate(_mask_prompt(prompt, self._mask)),
                    span_type="LLM",
                    metadata=dict(self._metadata),
                )
                self._turn_span = span
                self._turn_context = Laminar.get_laminar_span_context(span)
        except Exception:
            logger.debug("ACP turn span could not be started", exc_info=True)
            with self._lock:
                self._turn_span = None
                self._turn_context = None

    def tool_started(self, entry: dict[str, Any]) -> None:
        if not self._enabled or self._turn_span is None:
            return
        call_id = str(entry.get("tool_call_id") or "")
        if not call_id:
            return
        try:
            from lmnr import Laminar

            metadata = dict(self._metadata)
            metadata["tool_call_id"] = call_id
            with self._lock:
                if call_id in self._tool_spans or self._turn_span is None:
                    return
                self._tool_spans[call_id] = Laminar.start_span(
                    name=str(
                        entry.get("title") or entry.get("tool_kind") or "acp_tool"
                    ),
                    input=_truncate(_tool_input(entry)),
                    span_type="TOOL",
                    parent_span_context=self._turn_context,
                    metadata=metadata,
                )
        except Exception:
            logger.debug("ACP tool span could not be started", exc_info=True)

    def tool_finished(self, entry: dict[str, Any]) -> None:
        with self._lock:
            span = self._tool_spans.pop(str(entry.get("tool_call_id") or ""), None)
        if span is None:
            return
        self._close_tool_span(span, entry)

    def finish_turn(
        self,
        text: str,
        thoughts: str,
        tool_calls: list[dict[str, Any]],
    ) -> None:
        """设置回合的辅助消息并关闭其打开的每个范围。"""
        with self._lock:
            open_spans = list(self._tool_spans.items())
            self._tool_spans.clear()
            span, self._turn_span, self._turn_context = self._turn_span, None, None
        for call_id, tool_span in open_spans:
            entry = next(
                (t for t in tool_calls if str(t.get("tool_call_id")) == call_id), {}
            )
            self._close_tool_span(tool_span, entry)

        if span is None:
            return
        try:
            span.set_output([_assistant_message(text, thoughts, tool_calls)])
        except Exception:
            logger.debug("ACP turn span output could not be set", exc_info=True)
        try:
            span.end()
        except Exception:
            logger.debug("ACP turn span could not be ended", exc_info=True)

    def abandon(self) -> None:
        """关闭超时或失败的回合后仍打开的所有内容。"""
        with self._lock:
            open_spans = list(self._tool_spans.values())
            self._tool_spans.clear()
            span, self._turn_span, self._turn_context = self._turn_span, None, None
        for tool_span in open_spans:
            self._close_tool_span(tool_span, {})
        if span is None:
            return
        try:
            span.end()
        except Exception:
            logger.debug("ACP turn span could not be ended", exc_info=True)

    @staticmethod
    def _close_tool_span(span: Any, entry: dict[str, Any]) -> None:
        try:
            output = entry.get("raw_output")
            if output is None:
                output = entry.get("content")
            span.set_output(_observation(output))
        except Exception:
            logger.debug("ACP tool span output could not be set", exc_info=True)
        try:
            span.end()
        except Exception:
            logger.debug("ACP tool span could not be ended", exc_info=True)


def _mask_prompt(prompt: Any, mask: Callable[[str], str] | None) -> Any:
    """对提示词中的每个字符串运行对话的机密掩码器。

    如果屏蔽失败，则返回 ``None`` 而不是原始值：未记录的提示词是可恢复的，而运送到后
    端的未屏蔽的则不可恢复。
    """
    if mask is None:
        return prompt

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return mask(node)
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if is_model_dumpable(node):
            return walk(node.model_dump())
        return node

    try:
        return walk(prompt)
    except Exception:
        logger.debug("ACP prompt could not be masked", exc_info=True)
        return None


def _observation(output: Any) -> dict[str, Any]:
    """以本机 ``Observation`` 序列化的方式包装工具结果。

    裸字符串将存储为 JSON 标量，并到达仍包含在引号中的消费者； 只有 ``{``/``[`` 载荷
    被解析回来。
    """
    if not isinstance(output, str):
        try:
            output = json.dumps(output, default=str)
        except Exception:
            output = str(output)
    return {"content": [{"type": "text", "text": _truncate(output)}]}


def _assistant_message(
    text: str,
    thoughts: str,
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建跟踪消费者期望的 OpenAI 形辅助消息。"""
    message: dict[str, Any] = {"role": "assistant", "content": text or ""}
    if thoughts:
        message["reasoning_content"] = thoughts
    calls = [_tool_call(tc) for tc in tool_calls if tc.get("tool_call_id")]
    if calls:
        message["tool_calls"] = calls
    return message


def _tool_input(entry: dict[str, Any]) -> Any:
    """根据服务器的报告，该工具是用什么来调用的。

    ``raw_input`` 在 ACP 中是可选的，Codex 完全省略了它，只留下 ``title`` 作为调用的
    唯一指示。
    """
    raw_input = entry.get("raw_input")
    if raw_input is not None:
        return raw_input
    title = entry.get("title")
    return {"title": title} if title else {}


def _tool_call(entry: dict[str, Any]) -> dict[str, Any]:
    raw_input = _tool_input(entry)
    if not isinstance(raw_input, str):
        try:
            raw_input = json.dumps(raw_input, default=str)
        except Exception:
            raw_input = "{}"
    return {
        "id": str(entry.get("tool_call_id") or ""),
        "type": "function",
        "function": {
            # ACP 报告显示 ``title`` 和分类 ``kind``； 只有后者在同一工具的调用中是稳定
            # 的。
            #
            "name": str(entry.get("tool_kind") or entry.get("title") or "acp_tool"),
            "arguments": raw_input,
        },
    }
