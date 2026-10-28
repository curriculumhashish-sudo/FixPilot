"""实用程序 LLM 调用必须与跟踪中的主循环轮次区分开。"""

import json
import os
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.observability.laminar import OPERATION_METADATA_KEY


METADATA_ATTRIBUTE_PREFIX = "lmnr.association.properties.metadata."


def _record_observe_kwargs(unbound_method: Any) -> dict[str, Any]:
    """返回在延迟修饰方法上声明的 ``observe`` kwargs。"""
    recorded: dict[str, Any] = {}

    def recorder(**kwargs: Any):
        recorded.update(kwargs)
        return lambda func: func

    with patch("lmnr.observe", recorder):
        code = getattr(unbound_method, "__code__", None)
        closure = getattr(unbound_method, "__closure__", None)
        if code is not None and closure is not None:
            freevars = dict(zip(code.co_freevars, closure, strict=False))
            build_wrapped_cell = freevars.get("_build_wrapped")
            if build_wrapped_cell is not None:
                build_wrapped_cell.cell_contents(lambda: None)
                return recorded

        with patch(
            "openhands.sdk.observability.laminar.should_enable_observability",
            return_value=True,
        ):
            try:
                unbound_method(object())
            except Exception:
                pass

    return recorded


@pytest.mark.parametrize(
    ("unbound_method", "expected_name", "expected_operation"),
    [
        (
            LocalConversation.generate_title,
            "conversation.generate_title",
            "title_generation",
        ),
        (
            RemoteConversation.generate_title,
            "conversation.generate_title",
            "title_generation",
        ),
        (LocalConversation.ask_agent, "conversation.ask_agent", "ask_agent"),
    ],
)
def test_utility_methods_declare_operation_metadata(
    unbound_method: Any, expected_name: str, expected_operation: str
) -> None:
    kwargs = _record_observe_kwargs(unbound_method)

    assert kwargs["name"] == expected_name
    assert kwargs["metadata"] == {OPERATION_METADATA_KEY: expected_operation}


def _probe_exported_spans() -> list[dict[str, Any]]:
    """驱动真正的层流追踪器并将导出的跨度作为简单的字典返回。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"

    import litellm
    from lmnr import Instruments, Laminar
    from lmnr.opentelemetry_lib.tracing import TracerWrapper
    from lmnr.opentelemetry_lib.tracing.processor import LaminarSpanProcessor
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from pydantic import SecretStr

    from openhands.sdk.agent import Agent
    from openhands.sdk.conversation import Conversation
    from openhands.sdk.llm import LLM, Message, TextContent

    Laminar.initialize(
        project_api_key="test-key",
        base_url="http://localhost",
        http_port=1,
        grpc_port=1,
        disable_batch=True,
        instruments={Instruments.LITELLM},
    )
    exporter = InMemorySpanExporter()
    span_processor = TracerWrapper.instance._span_processor
    assert isinstance(span_processor, LaminarSpanProcessor)
    span_processor.instance = SimpleSpanProcessor(exporter)

    instrumented_completion = litellm.completion

    def mocked_completion(**kwargs: Any):
        return instrumented_completion(**{**kwargs, "mock_response": "Fix Auth Bug"})

    llm = LLM(usage_id="probe-llm", model="gpt-4o", api_key=SecretStr("test-key"))
    conversation = Conversation(
        agent=Agent(llm=llm, tools=[]),
        callbacks=[],
        observability_metadata={"repo": "OpenHands/software-agent-sdk"},
    )

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mocked_completion
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="fix the auth bug")])
        )
        conversation.run()
        conversation.generate_title()
        conversation.ask_agent("what did you do?")

    Laminar.flush()

    spans = exporter.get_finished_spans()
    names_by_id = {
        span.context.span_id: span.name for span in spans if span.context is not None
    }
    parent_id_by_id = {
        span.context.span_id: (span.parent.span_id if span.parent else None)
        for span in spans
        if span.context is not None
    }

    def operation_parent(span: Any) -> str | None:
        """不是 SDK 的合成 ``llm.<model>`` 跨度的最近祖先。

        Telemetry.on_request 打开保持当前状态的 ``llm.<model>`` 范围
        while the call runs (so the authoritative cost can be attached before
        lmnr 结束其 ``litellm.completion`` 跨度）。 该跨度位于操作跨度和
        ``litellm.completion`` 之间； 跳过它
        以恢复 LLM 调用所属的操作。
        """
        pid = span.parent.span_id if span.parent else None
        while pid is not None and names_by_id.get(pid, "").startswith("llm."):
            pid = parent_id_by_id.get(pid)
        return names_by_id.get(pid) if pid is not None else None

    return [
        {
            "name": span.name,
            "parent": operation_parent(span),
            "immediate_parent": (
                names_by_id.get(span.parent.span_id) if span.parent else None
            ),
            "attributes": {
                key: value
                for key, value in (span.attributes or {}).items()
                if key.startswith(METADATA_ATTRIBUTE_PREFIX)
            },
        }
        for span in spans
    ]


def _metadata(span: dict[str, Any]) -> dict[str, Any]:
    return {
        key.removeprefix(METADATA_ATTRIBUTE_PREFIX): value
        for key, value in span["attributes"].items()
    }


def test_operation_metadata_reaches_the_exported_llm_span() -> None:
    # 子进程：Laminar.initialize() 永久开启进程全局跟踪，
    # 这将改变该工人以后的每一次测试。
    result = subprocess.run(
        [sys.executable, __file__],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    spans = json.loads(result.stdout.splitlines()[-1])

    llm_spans = [span for span in spans if span["name"] == "litellm.completion"]
    # 现在，每个 litellm.completion 都嵌套在 SDK 的合成 ``llm.<model>`` 成本跨度 (
    # Telemetry.on_request) 下，而后者又嵌套在操作跨度下。 下面的操作属性将遍历该包装器
    # 。
    #
    assert llm_spans and all(
        span["immediate_parent"].startswith("llm.") for span in llm_spans
    )
    by_parent = {span["parent"]: span for span in llm_spans}
    assert set(by_parent) == {
        "agent.step",
        "conversation.generate_title",
        "conversation.ask_agent",
    }

    title_llm = by_parent["conversation.generate_title"]
    ask_llm = by_parent["conversation.ask_agent"]
    main_loop_llm = by_parent["agent.step"]

    # 拼写出来，不是从 OPERATION_METADATA_KEY 派生：这个确切的属性名称是有线合同下游消费
    # 者的硬编码。
    #
    assert (
        title_llm["attributes"][
            "lmnr.association.properties.metadata.openhands.operation"
        ]
        == "title_generation"
    )
    assert (
        ask_llm["attributes"][
            "lmnr.association.properties.metadata.openhands.operation"
        ]
        == "ask_agent"
    )

    # 子树范围：主智能体循环未受影响，并且会话自己的跟踪元数据仍然到达每个跨度。
    #
    assert OPERATION_METADATA_KEY not in _metadata(main_loop_llm)
    for span in llm_spans:
        assert _metadata(span)["repo"] == "OpenHands/software-agent-sdk"


if __name__ == "__main__":
    print(json.dumps(_probe_exported_spans()))
