"""测试布线 SDK 在401刷新钩子上绑定管理代理 LLMs.

``register_managed_llm_key_refresh`` 是 OpenHands/software-智能体-SDK#5189 的智能体-
服务器一半：它注册
在托管的LLMs上调用[meth:`openhands.sdk.llm.LLM.set_api_key_refresh_hook`]
过时的托管密钥恢复到位。 这些测试断言，除非控制平面选择加入，否则布线是无害的，它只针
对管理代理 LLMs，并且注册的钩子实际上提供 SDK 的重新解析路径。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal
from uuid import uuid4

import pytest
from litellm import ModelResponse
from litellm.exceptions import AuthenticationError
from pydantic import SecretStr

from openhands.agent_server.event_service import EventService
from openhands.agent_server.managed_llm_key import (
    REFRESH_BASE_URLS_ENV,
    REFRESH_HEADERS_ENV,
    REFRESH_URL_ENV,
    _load_headers,
    register_managed_llm_key_refresh,
)
from openhands.agent_server.models import StoredConversation
from openhands.sdk import LLM, Agent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.secret import (
    register_local_secret_resolver,
    unregister_local_secret_resolver,
)
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.workspace import LocalWorkspace


MANAGED_BASE_URL = "https://llm-proxy.example/v1"
BYOK_BASE_URL = "https://api.openai.com/v1"
REFRESH_URL = "https://app.example/api/v1/sandboxes/s1/managed-llm-key"


def _auth_error() -> AuthenticationError:
    return AuthenticationError(
        message=(
            "Invalid proxy server token passed. Unable to find token in cache or "
            "LiteLLM_VerificationTokenTable (token_not_found_in_db)"
        ),
        llm_provider="openhands",
        model="gpt-4o",
    )


def _llm(
    usage_id: str,
    base_url: str | None,
    auth_type: Literal["api_key", "subscription"] = "api_key",
) -> LLM:
    return LLM(
        usage_id=usage_id,
        model="gpt-4o",
        api_key=SecretStr("stale_key"),
        base_url=base_url,
        auth_type=auth_type,
    )


def _agent(llm: LLM) -> Agent:
    return Agent(llm=llm, tools=[])


@contextmanager
def _served_key(url: str, value: str) -> Iterator[None]:
    """在本地回答 ``url``，因此 LookupSecret 在没有实际 HTTP 的情况下解析。"""

    def resolver(requested: str) -> str | None:
        return value if requested == url else None

    register_local_secret_resolver(resolver)
    try:
        yield
    finally:
        unregister_local_secret_resolver(resolver)


def test_no_env_is_noop(monkeypatch):
    monkeypatch.delenv(REFRESH_URL_ENV, raising=False)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)

    assert register_managed_llm_key_refresh(agent) == 0
    # 未触及的挂钩：401 无法解析刷新的密钥。
    assert llm._resolve_refreshed_api_key(_auth_error()) is None


def test_registers_and_feeds_sdk_resolution(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)

    assert register_managed_llm_key_refresh(agent) == 1

    with _served_key(REFRESH_URL, "fresh_key"):
        refreshed = llm._resolve_refreshed_api_key(_auth_error())
    assert refreshed is not None
    assert refreshed.get_secret_value() == "fresh_key"


def test_scopes_to_managed_base_url(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    byok = _llm("byok", BYOK_BASE_URL)
    agent = _agent(byok)

    # BYOK LLM（不同的 base_url）不得接收托管挂钩。
    assert register_managed_llm_key_refresh(agent) == 0
    with _served_key(REFRESH_URL, "fresh_key"):
        assert byok._resolve_refreshed_api_key(_auth_error()) is None


@pytest.mark.parametrize("persisted", [False, True])
def test_canonical_managed_provider_refreshes(monkeypatch, persisted):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, "https://llm-proxy.app.all-hands.dev")
    llm = LLM(
        model="openhands/deepseek-v4.1-flash",
        api_key=SecretStr("stale_key"),
        usage_id="managed",
    )
    if persisted:
        llm = LLM.model_validate_json(
            llm.model_dump_json(context={"expose_secrets": True})
        )
    assert llm.base_url is None
    assert register_managed_llm_key_refresh(_agent(llm)) == 1
    keys = []

    def complete(**kwargs):
        keys.append(kwargs["api_key"])
        if kwargs["api_key"] == "stale_key":
            raise _auth_error()
        return ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "resumed"}}]
        )

    monkeypatch.setattr("openhands.sdk.llm.llm.litellm_completion", complete)
    with _served_key(REFRESH_URL, "fresh_key"):
        response = llm.completion(
            [Message(role="user", content=[TextContent(text="continue")])]
        )
    assert response.message.content == [TextContent(text="resumed")]
    assert keys == ["stale_key", "fresh_key"]


def test_skips_subscription_auth(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    sub = _llm("sub", MANAGED_BASE_URL, auth_type="subscription")
    agent = _agent(sub)

    assert register_managed_llm_key_refresh(agent) == 0


def test_without_allowlist_feature_stays_off(monkeypatch):
    # 失败：操作员必须显式枚举管理的代理，否则钩子也会附加到 BYOK LLMs。
    #
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.delenv(REFRESH_BASE_URLS_ENV, raising=False)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)

    assert register_managed_llm_key_refresh(agent) == 0
    with _served_key(REFRESH_URL, "fresh_key"):
        assert llm._resolve_refreshed_api_key(_auth_error()) is None


def test_blank_allowlist_feature_stays_off(monkeypatch):
    # 已设置但为空的允许列表与不存在的允许列表一样未配置。
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, " , ")
    llm = _llm("m", MANAGED_BASE_URL)

    assert register_managed_llm_key_refresh(_agent(llm)) == 0


def test_hook_failure_surfaces_original_error(monkeypatch):
    # 无法到达的地址，没有本地解析器：获取失败，钩子必须吞掉它（返回None）而不是屏蔽原始
    # 的401。
    #
    monkeypatch.setenv(REFRESH_URL_ENV, "http://127.0.0.1:1/managed-llm-key")
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)
    assert register_managed_llm_key_refresh(agent) == 1

    assert llm._resolve_refreshed_api_key(_auth_error()) is None


def test_empty_served_key_does_not_retry(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)
    assert register_managed_llm_key_refresh(agent) == 1

    with _served_key(REFRESH_URL, "   "):
        # 仅空白的正文将被剥离为空 -> 没有可用的键 -> 没有重试。
        assert llm._resolve_refreshed_api_key(_auth_error()) is None


def test_base_url_match_ignores_trailing_slash(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    # 允许列表没有尾部斜杠，LLM base_url 有 - 必须仍然匹配。
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL + "/")
    assert register_managed_llm_key_refresh(_agent(llm)) == 1


def test_allowlist_entry_trailing_slash_ignored(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    # 允许列表有一个尾部斜杠，LLM base_url 没有 - 必须仍然匹配。
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL + "/")
    llm = _llm("m", MANAGED_BASE_URL)
    assert register_managed_llm_key_refresh(_agent(llm)) == 1


def test_non_object_headers_env_is_ignored(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    # 必须忽略不是对象的有效 JSON，而不是崩溃注册。
    monkeypatch.setenv(REFRESH_HEADERS_ENV, '["a", "b"]')
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL)

    assert register_managed_llm_key_refresh(_agent(llm)) == 1
    with _served_key(REFRESH_URL, "fresh_key"):
        refreshed = llm._resolve_refreshed_api_key(_auth_error())
    assert refreshed is not None
    assert refreshed.get_secret_value() == "fresh_key"


def test_bad_headers_env_is_ignored(monkeypatch):
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_HEADERS_ENV, "not-json")
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    llm = _llm("m", MANAGED_BASE_URL)
    agent = _agent(llm)

    # 格式错误的标头不得破坏注册； 钩子仍然解析。
    assert register_managed_llm_key_refresh(agent) == 1
    with _served_key(REFRESH_URL, "fresh_key"):
        refreshed = llm._resolve_refreshed_api_key(_auth_error())
    assert refreshed is not None
    assert refreshed.get_secret_value() == "fresh_key"


def test_headers_expand_env_references(monkeypatch):
    """标头值可以引用环境变量，因此控制平面可以指向
    每个沙箱凭据 (e.g. 会话密钥）它无法预先知道。"""
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "sess-abc123")
    headers = _load_headers(
        '{"X-Session-API-Key": "${OH_SESSION_API_KEYS_0}", "X-Static": "plain"}'
    )
    assert headers == {"X-Session-API-Key": "sess-abc123", "X-Static": "plain"}


def test_headers_bare_dollar_reference_expands(monkeypatch):
    """``$VAR`` 形式（无大括号）也会扩展。"""
    monkeypatch.setenv("OH_SESSION_API_KEYS_0", "sess-xyz")
    assert _load_headers('{"X-Session-API-Key": "$OH_SESSION_API_KEYS_0"}') == {
        "X-Session-API-Key": "sess-xyz"
    }


@pytest.mark.asyncio
async def test_switched_llm_keeps_refresh_hook(monkeypatch, tmp_path):
    """switch_llm 在加载的对话上重新注册挂钩 (#5890)。"""
    monkeypatch.setenv(REFRESH_URL_ENV, REFRESH_URL)
    monkeypatch.setenv(REFRESH_BASE_URLS_ENV, MANAGED_BASE_URL)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = EventService(
        stored=StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(workspace)),
            confirmation_policy=NeverConfirm(),
        ),
        agent=_agent(_llm("loaded", MANAGED_BASE_URL)),
        conversations_dir=tmp_path / "conversations",
    )
    await service.start()
    try:
        conversation = service.get_conversation()

        conversation.switch_llm(_llm("switched", MANAGED_BASE_URL))
        switched = conversation.agent.llm
        assert switched.usage_id == "switched"
        with _served_key(REFRESH_URL, "fresh_key"):
            refreshed = switched._resolve_refreshed_api_key(_auth_error())
        assert refreshed is not None
        assert refreshed.get_secret_value() == "fresh_key"

        # 切换到 BYOK base_url 仍然得不到托管挂钩。
        conversation.switch_llm(_llm("byok", BYOK_BASE_URL))
        byok = conversation.agent.llm
        assert byok.usage_id == "byok"
        with _served_key(REFRESH_URL, "fresh_key"):
            assert byok._resolve_refreshed_api_key(_auth_error()) is None

        # 未选择加入：交换机不记录任何内容。
        monkeypatch.delenv(REFRESH_URL_ENV)
        conversation.switch_llm(_llm("off", MANAGED_BASE_URL))
        off = conversation.agent.llm
        assert off.usage_id == "off"
        with _served_key(REFRESH_URL, "fresh_key"):
            assert off._resolve_refreshed_api_key(_auth_error()) is None
    finally:
        await service.close()
