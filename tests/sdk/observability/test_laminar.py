"""层流可观测性配置测试。"""

import asyncio
import contextvars
import inspect
import os
from unittest.mock import MagicMock, patch

import pytest

from openhands.sdk.agent.agent import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation


@pytest.fixture(autouse=True)
def _reset_observability_cache():
    """在测试之间重置模块级 _observability_enabled 标志。

    该标志在设计上是粘性的True（参见laminar.py文档字符串），因此它会在测试中泄漏。 此
    测试夹具将每个测试与先前状态隔离。
    """
    from openhands.sdk.observability import laminar

    laminar._observability_enabled = False
    yield
    laminar._observability_enabled = False


def test_lmnr_base_url_passed_to_laminar():
    """测试 LMNR_BASE_URL 是否正确传递到 Laminar.initialize。"""
    import os

    # 保存原始值
    original_base_url = os.environ.get("LMNR_BASE_URL")
    original_key = os.environ.get("LMNR_PROJECT_API_KEY")

    try:
        os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
        os.environ["LMNR_BASE_URL"] = "https://custom.lmnr.ai"

        with patch("lmnr.Laminar") as mock_laminar:
            with patch("lmnr.LaminarLiteLLMCallback"):
                with patch("litellm.callbacks", new=MagicMock()):
                    mock_laminar.is_initialized.return_value = False
                    from openhands.sdk.observability.laminar import maybe_init_laminar

                    maybe_init_laminar()

                    # 检查 Laminar.initialize 是否被 base_url 调用
                    call_kwargs = mock_laminar.initialize.call_args.kwargs
                    assert call_kwargs.get("base_url") == "https://custom.lmnr.ai"
    finally:
        # 恢复原始值
        if original_base_url is not None:
            os.environ["LMNR_BASE_URL"] = original_base_url
        elif "LMNR_BASE_URL" in os.environ:
            del os.environ["LMNR_BASE_URL"]
        if original_key is not None:
            os.environ["LMNR_PROJECT_API_KEY"] = original_key
        elif "LMNR_PROJECT_API_KEY" in os.environ:
            del os.environ["LMNR_PROJECT_API_KEY"]


def test_lmnr_base_url_not_passed_when_empty():
    """当LMNR_BASE_URL未设置时，测试base_url是否为None。"""
    # 保存原始值
    original_base_url = os.environ.get("LMNR_BASE_URL")
    original_key = os.environ.get("LMNR_PROJECT_API_KEY")

    try:
        os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
        if "LMNR_BASE_URL" in os.environ:
            del os.environ["LMNR_BASE_URL"]

        with patch("lmnr.Laminar") as mock_laminar:
            with patch("lmnr.LaminarLiteLLMCallback"):
                with patch("litellm.callbacks", new=MagicMock()):
                    mock_laminar.is_initialized.return_value = False
                    from openhands.sdk.observability.laminar import maybe_init_laminar

                    maybe_init_laminar()

                    # 检查 Laminar.initialize 是否已通过 base_url=None 调用
                    call_kwargs = mock_laminar.initialize.call_args.kwargs
                    assert call_kwargs.get("base_url") is None
    finally:
        # 恢复原始值
        if original_base_url is not None:
            os.environ["LMNR_BASE_URL"] = original_base_url
        elif "LMNR_BASE_URL" in os.environ:
            del os.environ["LMNR_BASE_URL"]
        if original_key is not None:
            os.environ["LMNR_PROJECT_API_KEY"] = original_key
        elif "LMNR_PROJECT_API_KEY" in os.environ:
            del os.environ["LMNR_PROJECT_API_KEY"]


def test_maybe_init_laminar_skips_when_already_initialized():
    """Laminar.initialize 已初始化后不得再次调用。

    在前一个 init 发出“Laminar 已初始化”之后重新调用 Laminar.initialize。 跳过初始化
    。'在 INFO 级别
    from lmnr. Since ``maybe_init_laminar`` runs at import time in agent.py
    和 acp_agent.py，该行显示在第一个模块加载之后的每个模块加载上。 防止重新初始化以
    保持日志干净。
    """
    original_key = os.environ.get("LMNR_PROJECT_API_KEY")

    try:
        os.environ["LMNR_PROJECT_API_KEY"] = "test-key"

        with patch("lmnr.Laminar") as mock_laminar:
            with patch("lmnr.LaminarLiteLLMCallback"):
                with patch("litellm.callbacks", new=MagicMock()):
                    mock_laminar.is_initialized.return_value = True
                    from openhands.sdk.observability.laminar import maybe_init_laminar

                    maybe_init_laminar()
                    maybe_init_laminar()

                    mock_laminar.initialize.assert_not_called()
    finally:
        if original_key is not None:
            os.environ["LMNR_PROJECT_API_KEY"] = original_key
        elif "LMNR_PROJECT_API_KEY" in os.environ:
            del os.environ["LMNR_PROJECT_API_KEY"]


def test_observe_preserves_async_signature():
    """@observe must keep an async function async so introspection works.

    回归测试惰性包装器无条件同步的错误，导致 `inspect.iscoroutinefunction` 对于修饰的
    异步方法返回 False。 这破坏了
    `MCPToolExecutor.__call__`，它依赖 `run_async` 中的 `iscoroutinefunction` 来调度
    调用。
    """
    from openhands.sdk.observability.laminar import observe

    @observe(name="async_fn")
    async def async_fn(x: int) -> int:
        return x + 1

    @observe(name="sync_fn")
    def sync_fn(x: int) -> int:
        return x + 1

    assert inspect.iscoroutinefunction(async_fn)
    assert not inspect.iscoroutinefunction(sync_fn)


@pytest.mark.parametrize(
    ("force_http_value", "expected_force_http"),
    [
        ("true", True),
        ("1", True),
        ("YeS", True),
        ("ON", True),
        ("false", False),
        ("0", False),
        (None, False),
    ],
)
def test_lmnr_force_http_passed_to_laminar(force_http_value, expected_force_http):
    """测试 LMNR_FORCE_HTTP 是否正确传递到 Laminar.initialize。"""
    original_key = os.environ.get("LMNR_PROJECT_API_KEY")
    original_force_http = os.environ.get("LMNR_FORCE_HTTP")

    try:
        os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
        if force_http_value is not None:
            os.environ["LMNR_FORCE_HTTP"] = force_http_value
        elif "LMNR_FORCE_HTTP" in os.environ:
            del os.environ["LMNR_FORCE_HTTP"]

        with patch("lmnr.Laminar") as mock_laminar:
            with patch("lmnr.LaminarLiteLLMCallback"):
                with patch("litellm.callbacks", new=MagicMock()):
                    mock_laminar.is_initialized.return_value = False
                    from openhands.sdk.observability.laminar import maybe_init_laminar

                    maybe_init_laminar()

                    call_kwargs = mock_laminar.initialize.call_args.kwargs
                    assert call_kwargs.get("force_http") == expected_force_http
    finally:
        if original_key is not None:
            os.environ["LMNR_PROJECT_API_KEY"] = original_key
        elif "LMNR_PROJECT_API_KEY" in os.environ:
            del os.environ["LMNR_PROJECT_API_KEY"]
        if original_force_http is not None:
            os.environ["LMNR_FORCE_HTTP"] = original_force_http
        elif "LMNR_FORCE_HTTP" in os.environ:
            del os.environ["LMNR_FORCE_HTTP"]


@pytest.mark.parametrize("is_laminar_backend", [True, False])
@pytest.mark.parametrize(
    ("instruments_env", "expected", "invalid"),
    [
        ("litellm,mcp", {"litellm", "mcp"}, None),
        ("litellm,,unsupported,", {"litellm"}, "unsupported"),
    ],
)
def test_lmnr_instruments_passed_to_laminar(
    is_laminar_backend, instruments_env, expected, invalid, caplog
):
    """LMNR_INSTRUMENTS 将层流限制为所选积分。"""
    from lmnr import Instruments

    with patch.dict(
        os.environ,
        {
            "LMNR_PROJECT_API_KEY": "test-key",
            "LMNR_INSTRUMENTS": instruments_env,
        },
    ):
        with (
            patch("lmnr.Laminar") as mock_laminar,
            patch(
                "openhands.sdk.observability.laminar._is_otel_backend_laminar",
                return_value=is_laminar_backend,
            ),
        ):
            mock_laminar.is_initialized.return_value = False
            from openhands.sdk.observability.laminar import maybe_init_laminar

            maybe_init_laminar()

    assert mock_laminar.initialize.call_args.kwargs["instruments"] == {
        Instruments(value) for value in expected
    }
    if invalid:
        assert f"Ignoring invalid LMNR_INSTRUMENTS value '{invalid}'" in caplog.text


# ---------------------------------------------------------------------------
# 跨上下文根跨传播
# ---------------------------------------------------------------------------
#
# 回归测试了 ``@observe``-装饰方法在 Conversation 上，当从不同的异步任务或线程于构建
# Conversation 的任务中调用时，会启动一个新的跟踪，而不是附接到 Conversation 的根跟踪。
# 修复动作
#
# from ``Laminar.start_active_span`` (which relies on contextvars
# 传播）到 ``Laminar.start_span`` + ``Laminar.use_span``，每入口重新连接一次。
#


class _DummyOwner:
    """出于观察包装器的目的，模拟 ``BaseConversation``。"""

    def __init__(self, root_span):
        from openhands.sdk.observability.laminar import RootSpan

        # 构建一个类似 RootSpan 的对象，而不调用真正的 lmnr。
        self._observability_root_span = RootSpan.__new__(RootSpan)
        self._observability_root_span.span = root_span
        self._observability_root_span._ended = False


def test_observe_calls_use_span_with_owner_root_span_on_sync():
    """同步 ``@observe``d 方法必须重新附加所有者的根跨度。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar  # noqa: F401  ensure module is importable

        from openhands.sdk.observability import laminar as lam

        sentinel_span = MagicMock(name="root-span")
        used_with: list = []

        @contextlib_compat()
        def fake_use_span(span, *args, **kwargs):
            used_with.append(span)
            yield span

        with patch.object(Laminar, "use_span", side_effect=fake_use_span):
            # 在此调用期间强制启用可观察性。
            lam._observability_enabled = True
            # 存根 lmnr-level ``observe``，以便包装器直接调用。
            with patch("lmnr.observe", lambda **kw: lambda f: f):

                @lam.observe(name="conversation.send_message")
                def send_message(self, msg: str) -> str:
                    return f"got {msg}"

                owner = _DummyOwner(sentinel_span)
                assert send_message(owner, "hi") == "got hi"

        assert used_with == [sentinel_span], (
            f"expected use_span to be called once with owner's root span, "
            f"got {used_with!r}"
        )
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_observe_with_owner_root_span_preserves_wrapped_exceptions():
    """包装函数中的异常不得被视为 use_span 错误。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar

        from openhands.sdk.observability import laminar as lam

        sentinel_span = MagicMock(name="root-span")
        used_with: list = []

        @contextlib_compat()
        def fake_use_span(span, *args, **kwargs):
            used_with.append(span)
            yield span

        with patch.object(Laminar, "use_span", side_effect=fake_use_span):
            lam._observability_enabled = True
            with patch("lmnr.observe", lambda **kw: lambda f: f):

                @lam.observe(name="conversation.run")
                def run(self) -> None:
                    raise ValueError("boom")

                owner = _DummyOwner(sentinel_span)
                with pytest.raises(ValueError, match="boom"):
                    run(owner)

        assert used_with == [sentinel_span]
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_observe_calls_use_span_with_owner_root_span_on_async():
    """异步 ``@observe``d 方法必须重新附加所有者的根跨度。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar

        from openhands.sdk.observability import laminar as lam

        sentinel_span = MagicMock(name="root-span")
        used_with: list = []

        @contextlib_compat()
        def fake_use_span(span, *args, **kwargs):
            used_with.append(span)
            yield span

        with patch.object(Laminar, "use_span", side_effect=fake_use_span):
            lam._observability_enabled = True
            with patch("lmnr.observe", lambda **kw: lambda f: f):

                @lam.observe(name="conversation.run")
                async def run(self) -> str:
                    return "done"

                owner = _DummyOwner(sentinel_span)
                # 从新的、空的上下文变量上下文运行，以模仿在对话的异步祖先之外创建的任务
                # 。
                #

                async def _call_in_isolated_context():
                    new_ctx = contextvars.Context()
                    return await asyncio.tasks.Task(run(owner), context=new_ctx)

                result = asyncio.run(_call_in_isolated_context())
                assert result == "done"

        assert used_with == [sentinel_span], (
            f"expected use_span to be called once even from an isolated "
            f"context, got {used_with!r}"
        )
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_root_span_sets_user_id():
    """当提供 user_id 时，RootSpan 必须调用 Laminar.set_trace_user_id。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar

        from openhands.sdk.observability import laminar as lam

        mock_span = MagicMock(name="span")

        @contextlib_compat()
        def fake_use_span(span, *args, **kwargs):
            yield span

        with (
            patch.object(Laminar, "start_span", return_value=mock_span),
            patch.object(Laminar, "use_span", side_effect=fake_use_span),
            patch.object(Laminar, "set_trace_session_id") as mock_session,
            patch.object(Laminar, "set_trace_user_id") as mock_user,
        ):
            lam._observability_enabled = True
            root = lam.RootSpan("conversation", session_id="sess-1", user_id="user-42")
            assert root.span is mock_span
            mock_session.assert_called_once_with("sess-1")
            mock_user.assert_called_once_with("user-42")
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_root_span_skips_user_id_when_none():
    """当 user_id 为 None 时，RootSpan 不得调用 set_trace_user_id。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar

        from openhands.sdk.observability import laminar as lam

        mock_span = MagicMock(name="span")

        @contextlib_compat()
        def fake_use_span(span, *args, **kwargs):
            yield span

        with (
            patch.object(Laminar, "start_span", return_value=mock_span),
            patch.object(Laminar, "use_span", side_effect=fake_use_span),
            patch.object(Laminar, "set_trace_session_id") as mock_session,
            patch.object(Laminar, "set_trace_user_id") as mock_user,
        ):
            lam._observability_enabled = True
            lam.RootSpan("conversation", session_id="sess-1")
            mock_session.assert_called_once_with("sess-1")
            mock_user.assert_not_called()
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_root_span_sets_attributes():
    """RootSpan 必须将提供的属性附加到基础跨度。"""
    os.environ["LMNR_PROJECT_API_KEY"] = "test-key"
    try:
        from lmnr import Laminar

        from openhands.sdk.observability import laminar as lam

        mock_span = MagicMock(name="span")

        with patch.object(Laminar, "start_span", return_value=mock_span):
            lam._observability_enabled = True
            root = lam.RootSpan(
                "conversation",
                attributes={"conversation.tags.automationid": "auto-1"},
            )
            assert root.span is mock_span
            mock_span.set_attribute.assert_called_once_with(
                "conversation.tags.automationid", "auto-1"
            )
    finally:
        os.environ.pop("LMNR_PROJECT_API_KEY", None)


def test_two_concurrent_conversations_do_not_collide():
    """每个会话必须拥有自己的根跨度（无全局堆栈）。

    在修复之前，一个全局的 ``SpanManager`` LIFO 栈意味着在第一个会话存活期间会创建第
    二个会话，这会破坏第一个会话的根跨度。
    """
    from openhands.sdk.conversation.base import BaseConversation

    # 通过在类似 ``object`` 的裸实例上调用 ``BaseConversation.__init__`` 来绕过 ABC 实例
    # 化。 我们仅使用跨度管理方法，该方法具体针对基类。
    #
    class _BareConvo:
        pass

    c1 = _BareConvo()
    c2 = _BareConvo()
    BaseConversation.__init__(c1)  # type: ignore[arg-type]
    BaseConversation.__init__(c2)  # type: ignore[arg-type]

    # 修补在调用时查找的模块中的符号，并强制启用可观察性，以便快捷方式提前返回不会触发。
    #
    from openhands.sdk.conversation import base as base_mod

    with (
        patch.object(base_mod, "should_enable_observability", return_value=True),
        patch.object(
            base_mod,
            "start_root_span",
            side_effect=lambda *a, **k: MagicMock(spec_set=["end"]),
        ) as mock_start,
    ):
        BaseConversation._start_observability_span(c1, "session-1")  # type: ignore[arg-type]
        BaseConversation._start_observability_span(c2, "session-2")  # type: ignore[arg-type]

        # 每个对话都有自己的根跨度——没有共享堆栈。
        assert c1._observability_root_span is not c2._observability_root_span  # type: ignore[attr-defined]

        # 关闭 c2 必须不结束 c1 的根跨度。
        c2_root = c2._observability_root_span  # type: ignore[attr-defined]
        c1_root = c1._observability_root_span  # type: ignore[attr-defined]
        BaseConversation._end_observability_span(c2)  # type: ignore[arg-type]
        c2_root.end.assert_called_once()
        c1_root.end.assert_not_called()

        # 反之亦然。
        BaseConversation._end_observability_span(c1)  # type: ignore[arg-type]
        c1_root.end.assert_called_once()

        assert mock_start.call_count == 2


# 很小的垫片，因为我们想要一个基于生成器的上下文管理器帮助器，它也可以用作 patch() 的
# side_effect。
#
def contextlib_compat():
    import contextlib

    return contextlib.contextmanager


def test_root_span_sets_trace_metadata_and_tags():
    from openhands.sdk.observability.laminar import RootSpan

    fake_span = MagicMock()

    with patch("lmnr.Laminar") as mock_laminar:
        mock_laminar.start_span.return_value = fake_span

        RootSpan(
            "conversation",
            session_id="session-1",
            metadata={"repo_name": "OpenHands/software-agent-sdk"},
            tags=["repo:OpenHands/software-agent-sdk"],
        )

        mock_laminar.start_span.assert_called_once_with("conversation")
        mock_laminar.use_span.assert_called_once_with(
            fake_span,
            record_exception=False,
            set_status_on_exception=False,
        )
        mock_laminar.set_trace_session_id.assert_called_once_with("session-1")
        mock_laminar.set_trace_metadata.assert_called_once_with(
            {"repo_name": "OpenHands/software-agent-sdk"}
        )
        mock_laminar.set_span_tags.assert_called_once_with(
            ["repo:OpenHands/software-agent-sdk"]
        )


def test_detached_delegate_context_severs_ambient_span_and_links_parent():
    """在上下文管理器内创建的跨度不得加入任何跨度
    该端点目前是活跃的——生成的链接必须标识断开的父端点
    (trace_id, span_id, tool_call_id)，因此两个追踪可以关联起来（软件-智能体-
    SDK#4365）。

    只有 ``Laminar.get_laminar_span_context`` 是模拟的（不是整个
    ``Laminar`` 类）：``detached_delegate_context`` 必须通过 lmnr 的 OWN 隔离上下文跟
    踪来切断环境跨度，而不仅仅是标
    准
    ``opentelemetry.context`` 一个（它们是独立的 - 请参阅上的文档字符串
    ``detached_delegate_context``），所以这需要真实的
    ``Laminar.use_span`` 运行。 Laminar 在这里从未初始化，因此它在内部回落到普通
    ``opentelemetry.trace.use_span``，这足以证明与原始 OTel 跟踪器的隔离。
    """
    from types import SimpleNamespace

    from lmnr import Laminar
    from opentelemetry import trace as trace_api
    from opentelemetry.sdk.trace import TracerProvider

    from openhands.sdk.observability import laminar as lam

    parent_ctx = SimpleNamespace(
        trace_id="11111111-1111-1111-1111-111111111111",
        span_id="22222222-2222-2222-2222-222222222222",
        metadata={"tool_call_id": "call_abc123"},
    )

    tracer = TracerProvider().get_tracer("test")
    outer_span = tracer.start_span("outer")

    with patch.object(Laminar, "get_laminar_span_context", return_value=parent_ctx):
        lam._observability_enabled = True
        with trace_api.use_span(outer_span, end_on_exit=False):
            with lam.detached_delegate_context() as link:
                inner_span = tracer.start_span("inner")

        assert (
            inner_span.get_span_context().trace_id
            != outer_span.get_span_context().trace_id
        )
        assert link == {
            "delegate.parent_trace_id": str(parent_ctx.trace_id),
            "delegate.parent_span_id": str(parent_ctx.span_id),
            "tool_call_id": "call_abc123",
        }


def test_detached_delegate_context_restores_ambient_span_after_exit():
    """``with`` 块之后的代码必须再次看到原始跨度。"""
    from lmnr import Laminar
    from opentelemetry import trace as trace_api
    from opentelemetry.sdk.trace import TracerProvider

    from openhands.sdk.observability import laminar as lam

    tracer = TracerProvider().get_tracer("test")
    outer_span = tracer.start_span("outer")

    with patch.object(Laminar, "get_laminar_span_context", return_value=None):
        lam._observability_enabled = True

        with trace_api.use_span(outer_span, end_on_exit=False):
            with lam.detached_delegate_context():
                pass
            assert trace_api.get_current_span() is outer_span


def test_detached_delegate_context_without_ambient_parent():
    """没有要切断的活动跨度不得崩溃并且必须产生空链接。"""
    from lmnr import Laminar

    from openhands.sdk.observability import laminar as lam

    with patch.object(Laminar, "get_laminar_span_context", return_value=None):
        lam._observability_enabled = True

        with lam.detached_delegate_context() as link:
            assert link == {}


def test_detached_delegate_context_noop_when_observability_disabled():
    """当可观察性关闭时，上下文管理器必须是纯粹的无操作。"""
    from openhands.sdk.observability import laminar as lam

    with patch("lmnr.Laminar") as mock_laminar:
        mock_laminar.is_initialized.return_value = False
        lam._observability_enabled = False

        with lam.detached_delegate_context() as link:
            assert link == {}

        mock_laminar.get_laminar_span_context.assert_not_called()


def test_deprecated_shims_are_removed():
    """旧的全局堆栈 API (已弃用 1.22.0) 在 1.27.0 中被删除。"""
    from openhands.sdk.observability import laminar as lam

    assert not hasattr(lam, "start_active_span")
    assert not hasattr(lam, "end_active_span")
    assert not hasattr(lam, "SpanManager")


def test_async_agent_and_conversation_paths_are_observed():
    """异步双胞胎必须像其同步版本一样被 ``@observe`` 包裹。

    回归测试异步-奇偶校验间隙（问题#3449）：``Agent.astep`` 和
    ``LocalConversation.arun`` 失去了他们的同步双胞胎 (``Agent.step`` /
    ``LocalConversation.run``
    ) 携带的追踪装饰器。 ``observe`` 包装器将底层代码对象重命名为 ``async_wrapper``
    /``sync_wrapper``，因此可以通过
    ``__code__.co_name`` 检测到它的存在。
    """
    assert Agent.step.__code__.co_name == "sync_wrapper"
    assert Agent.astep.__code__.co_name == "async_wrapper"
    assert LocalConversation.run.__code__.co_name == "sync_wrapper"
    assert LocalConversation.arun.__code__.co_name == "async_wrapper"


def test_should_enable_observability_returns_true_when_env_set():
    """当设置可观察性环境变量时，should_enable_observability 返回 True。"""
    from openhands.sdk.observability.laminar import should_enable_observability

    with patch.dict(os.environ, {"LMNR_PROJECT_API_KEY": "test_key"}, clear=True):
        assert should_enable_observability() is True


def test_should_enable_observability_returns_false_when_no_env():
    """当未设置相关环境变量时，should_enable_observability 返回 False。"""
    from openhands.sdk.observability.laminar import should_enable_observability

    with patch.dict(os.environ, {}, clear=True):
        with patch("lmnr.Laminar") as mock_laminar:
            mock_laminar.is_initialized.return_value = False
            assert should_enable_observability() is False
