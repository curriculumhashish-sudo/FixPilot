"""PostHog 出口商行为，尤其是它必须*永远*调用的行为。

使用假的 ``posthog`` 模块，因此无论是否安装了可选的附加模块，它们都会运行。
"""

import sys
import types
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from openhands.agent_server.telemetry import models as m


@pytest.fixture
def fake_posthog(monkeypatch):
    """安装一个假的``posthog``模块并返回构建的客户端。

    ``Mock(spec=...)`` 是要点：客户端仅公开 ** 允许导出器使用的方法，因此任何尝试调用
     ``identify`` 或
    ``alias`` 引发 ``AttributeError``，而不是默默地创建或合并个人资料。
    """
    client = Mock(spec=["capture", "flush", "shutdown"])
    constructor_kwargs = {}

    def _posthog_ctor(**kwargs):
        constructor_kwargs.update(kwargs)
        return client

    module = types.ModuleType("posthog")
    module.Posthog = _posthog_ctor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "posthog", module)

    return client, constructor_kwargs


def make_event(distinct_id: str) -> m.DiagnosticEvent:
    return m.DiagnosticEvent(
        event_name=m.EventName.CONVERSATION_FINISHED,
        occurred_at=datetime.now(UTC),
        distinct_id=distinct_id,
        runtime=m.RuntimeProperties(
            server_version="1.36.1",
            sdk_version="1.36.1",
            tools_version="1.36.1",
            build_git_sha="unknown",
            build_git_ref="unknown",
            python_version="3.13",
            platform="darwin",
            deferred_init=False,
        ),
        properties=m.ConversationOutcomeProperties(
            conversation_ref="a" * 32,
            terminal_status="finished",
            duration_bucket="5-15",
            event_count_bucket="5-20",
            total_tokens_bucket="1000-10000",
            cost_bucket="lt-0p01",
            llm_model_family="anthropic",
        ),
    )


async def test_identified_events_reuse_the_host_distinct_id_verbatim(fake_posthog):
    """相关性取决于主机身份的逐字节重用。"""
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    client, _ = fake_posthog
    exporter = PostHogExporter("phc_test")

    await exporter.send([make_event("user-abc-123")])

    assert client.capture.call_count == 1
    kwargs = client.capture.call_args.kwargs
    assert kwargs["distinct_id"] == "user-abc-123"


async def test_exporter_never_creates_or_merges_an_identity(fake_posthog):
    """identify()/alias()会复制或不可逆转地合并一个人。"""
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    client, _ = fake_posthog
    exporter = PostHogExporter("phc_test")

    await exporter.send([make_event("user-abc"), make_event("anon:deadbeef")])

    # 模拟对象规范完全忽略了这些； 也明确地断言意图。
    assert not hasattr(client, "identify")
    assert not hasattr(client, "alias")
    assert not hasattr(client, "group_identify")
    assert client.capture.called


async def test_anonymous_events_do_not_create_person_profiles(fake_posthog):
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    client, _ = fake_posthog
    exporter = PostHogExporter("phc_test")

    await exporter.send([make_event("anon:deadbeef")])
    properties = client.capture.call_args.kwargs["properties"]
    assert properties["$process_person_profile"] is False


async def test_identified_events_do_attach_to_the_existing_person(fake_posthog):
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    client, _ = fake_posthog
    exporter = PostHogExporter("phc_test")

    await exporter.send([make_event("user-abc")])
    properties = client.capture.call_args.kwargs["properties"]
    # 缺席，因此事件发生在主持人已经确定的人身上。
    assert "$process_person_profile" not in properties


async def test_vendor_side_collection_is_disabled(fake_posthog):
    """自动捕获将发送回溯，完全击败消毒剂。"""
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    _, kwargs = fake_posthog
    PostHogExporter("phc_test")

    assert kwargs["enable_exception_autocapture"] is False
    assert kwargs["log_captured_exceptions"] is False
    assert kwargs["disable_geoip"] is True


async def test_sent_properties_stay_within_the_allowlist(fake_posthog):
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    client, _ = fake_posthog
    exporter = PostHogExporter("phc_test")

    await exporter.send([make_event("user-abc")])
    properties = client.capture.call_args.kwargs["properties"]

    assert set(properties) <= set(m.EXPECTED_PROPERTY_NAMES)
    assert "distinct_id" not in properties


async def test_host_is_configurable(fake_posthog):
    from openhands.agent_server.telemetry.posthog_exporter import PostHogExporter

    _, kwargs = fake_posthog
    PostHogExporter("phc_test", host="https://eu.i.posthog.com")
    assert kwargs["host"] == "https://eu.i.posthog.com"
