"""测试 ACPAgent。"""

from __future__ import annotations

import asyncio
import gc
import json
import threading
import time
import uuid
import weakref
from collections.abc import Mapping
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from acp.exceptions import RequestError as ACPRequestError
from acp.schema import NewSessionResponse, PromptResponse
from pydantic import SecretStr

import openhands.sdk.agent.acp_agent as acp_agent_module
import openhands.sdk.agent.acp_file_credentials as acp_file_credentials_module
import openhands.sdk.utils.files as files_module
from openhands.sdk.agent.acp_agent import (
    ACPAgent,
    _acp_error_detail,
    _acp_error_indicates_auth,
    _apply_acp_model,
    _auth_selection_failure_reason,
    _classify_acp_init_error,
    _classify_acp_turn_error,
    _codex_model_config_options,
    _estimate_cost_from_tokens,
    _extract_session_models,
    _extract_token_usage,
    _image_url_to_acp_block,
    _log_acp_provider_version,
    _log_acp_subprocess_stderr,
    _mask_json_value,
    _maybe_set_session_model,
    _mcp_config_to_acp_servers,
    _NewSessionResponse,
    _npx_packages,
    _OpenHandsACPBridge,
    _preconfigured_credentials,
    _reapply_session_model_on_resume,
    _select_auth_method,
    _serialize_tool_content,
    _stringify_acp_error_data,
    _strip_inherited_npm_env,
    _warn_auth_selection_failure,
    _with_codex_base_url,
)
from openhands.sdk.agent.acp_file_credentials import (
    ACPFileCredentialNeedsReauthError,
    ACPFileCredentialSyncError,
    codex_auth_file,
)
from openhands.sdk.agent.acp_models import ACPModelInfo
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.agent.stream_context import (
    StreamAborted,
    StreamDelta,
    StreamStarted,
)
from openhands.sdk.context import AgentContext
from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.credential import CredentialSyncError, ResolvedCredential
from openhands.sdk.event import (
    ACPToolCallEvent,
    ActionEvent,
    MessageEvent,
    SystemPromptEvent,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import ImageContent, Message, TextContent
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.secret import SecretSource
from openhands.sdk.settings.acp_install_catalog import (
    ACPInstallSpec,
    ACPPackagePin,
)
from openhands.sdk.settings.acp_providers import ACP_PROVIDERS
from openhands.sdk.skills import KeywordTrigger, Skill
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE
from openhands.sdk.workspace.local import LocalWorkspace


# ---------------------------------------------------------------------------
# 帮手
# ---------------------------------------------------------------------------


class _FakeLookupSecret(SecretSource):
    """注册表测试使用的 ``LookupSecret`` 的模块级替代。

    在模块范围内定义（不在测试方法内），因此其 ``__qualname__`` 不包含 ``<locals>``。
    ``DiscriminatedUnionMixin`` 在 ``SecretSource`` union 验证期间拒绝 qualname 包含
    ``<locals>`` 的子类，并且任何此类本地子类都会泄漏到全局中
    ``__subclasses__`` 注册表 — 破坏稍后在同一个 xdist 工作线程上运行的不相关的序列化
    测试。
    """

    stored_value: str

    def get_value(self) -> str | None:
        return self.stored_value


def _make_agent(**kwargs) -> ACPAgent:
    if isinstance(kwargs.get("mcp_config"), dict):
        mcp_config = kwargs["mcp_config"]
        servers = mcp_config.get("mcpServers", mcp_config)
        kwargs["mcp_config"] = coerce_mcp_config(servers)
    return ACPAgent(acp_command=["echo", "test"], **kwargs)


def _agent_conn(agent: ACPAgent) -> Any:
    assert agent._conn is not None
    return cast(Any, agent._conn)


def _attach_file_credential_lifecycle(
    agent: ACPAgent,
    path: Path,
    name: str = "TEST_AUTH_JSON",
) -> MagicMock:
    lifecycle = MagicMock()
    lifecycle.path = path
    agent._file_credential_lifecycles[name] = lifecycle
    return lifecycle


def test_file_credential_flush_does_not_hold_agent_lock(tmp_path):
    agent = _make_agent()
    lifecycle = _attach_file_credential_lifecycle(agent, tmp_path / "auth.json")
    threads: list[threading.Thread] = []

    def flush() -> None:
        acquired = threading.Event()

        def acquire_lock() -> None:
            with agent._file_credential_lock:
                acquired.set()

        thread = threading.Thread(target=acquire_lock)
        threads.append(thread)
        thread.start()
        assert acquired.wait(0.2)

    lifecycle.flush.side_effect = flush
    failures = agent._sync_file_credentials_collect()
    for thread in threads:
        thread.join(timeout=1)
    assert failures == {}


def _make_state(tmp_path) -> ConversationState:
    agent = _make_agent()
    workspace = LocalWorkspace(working_dir=str(tmp_path))
    return ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=workspace,
    )


def test_logs_matching_acp_provider_version(caplog):
    with caplog.at_level("INFO"):
        _log_acp_provider_version("codex-acp", "2.2.2")

    assert "provider=codex" in caplog.text
    assert "pinned_version='2.2.2'" in caplog.text
    assert "reported_version='2.2.2'" in caplog.text
    assert "mismatch" not in caplog.text


def test_warns_when_acp_provider_version_differs_from_pin(caplog):
    with caplog.at_level("INFO"):
        _log_acp_provider_version("gemini-cli 0.38.0", "")

    assert "provider=gemini-cli" in caplog.text
    assert "pinned_version='0.46.0'" in caplog.text
    assert "reported_version='0.38.0'" in caplog.text
    assert "probably installed at runtime via the npx fallback" in caplog.text


def test_npx_packages_skips_prefer_offline():
    assert _npx_packages(
        ["npx", "-y", "--prefer-offline", "@agentclientprotocol/codex-acp@1.10.0"]
    ) == ["@agentclientprotocol/codex-acp@1.10.0"]


def test_npx_packages_prefers_pinned_package_flags():
    """多包规范的位置参数是裸二进制名称；
    变暖将获取未固定的包裹，因此 ``--package=`` 引脚获胜。 每当提供者固定多个包（一个
    适配器加上它生成的引擎）时，``npx_command`` 就会发
    出该形式。
    """
    spec = ACPInstallSpec(
        key="two-package",
        packages=(
            ACPPackagePin("adapter-acp", "1.2.3"),
            ACPPackagePin("@scope/engine", "4.5.6"),
        ),
        binary_name="adapter-acp",
    )
    assert _npx_packages(list(spec.npx_command())) == [
        "adapter-acp@1.2.3",
        "@scope/engine@4.5.6",
    ]


def test_acp_npm_cache_is_shared_across_conversations(tmp_path):
    agent = _make_agent()
    state = _make_state(tmp_path)
    state.persistence_dir = str(tmp_path / "conversations" / "conversation-id")

    assert agent._acp_npm_cache_dir(state) == tmp_path / "conversations" / "npm-cache"


async def test_warm_npx_cache_passes_every_pinned_package(tmp_path):
    agent = _make_agent()
    process = MagicMock()
    process.returncode = 0
    process.wait = AsyncMock(return_value=0)

    with patch(
        "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as create_process:
        await agent._warm_npx_cache(
            ["adapter-acp@1.2.3", "@scope/engine@4.5.6"],
            "two-package",
            {},
            str(tmp_path),
        )

    assert create_process.await_args is not None
    assert create_process.await_args.args[:8] == (
        "npx",
        "--yes",
        "--prefer-offline",
        "--package",
        "adapter-acp@1.2.3",
        "--package",
        "@scope/engine@4.5.6",
        "--",
    )


async def test_warm_npx_cache_uses_prefer_offline_and_durable_env(tmp_path):
    agent = _make_agent()
    process = MagicMock()
    process.returncode = 0
    process.wait = AsyncMock(return_value=0)
    env = {"npm_config_cache": str(tmp_path / "npm-cache")}

    with patch(
        "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as create_process:
        await agent._warm_npx_cache(
            ["@agentclientprotocol/codex-acp@1.10.0"], "codex", env, str(tmp_path)
        )

    create_process.assert_awaited_once_with(
        "npx",
        "--yes",
        "--prefer-offline",
        "--package",
        "@agentclientprotocol/codex-acp@1.10.0",
        "--",
        "node",
        "-e",
        "",
        cwd=str(tmp_path),
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


def test_npx_cache_warm_failure_continues_with_normal_startup(tmp_path, caplog):
    agent = ACPAgent(
        acp_command=[
            "npx",
            "-y",
            "--prefer-offline",
            "@agentclientprotocol/codex-acp@1.10.0",
        ],
        acp_server="codex",
    )
    state = ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
    )
    conn = TestACPSessionIdPersistence._make_conn()

    try:
        with caplog.at_level("WARNING"):
            with patch.object(
                ACPAgent,
                "_warm_npx_cache",
                new=AsyncMock(side_effect=RuntimeError("registry unavailable")),
            ):
                TestACPSessionIdPersistence._patched_start_acp_server(
                    agent, state, conn=conn
                )
    finally:
        agent._unregister_atexit_cleanup()
        assert agent._executor is not None
        agent._executor.close()
        agent._executor = None

    assert "continuing with normal startup" in caplog.text
    conn.initialize.assert_awaited_once()


# ---------------------------------------------------------------------------
# 实例化
# ---------------------------------------------------------------------------


class TestACPAgentInstantiation:
    def test_creates_with_sentinel_llm(self):
        agent = _make_agent()
        assert agent.llm.model == "acp-managed"

    def test_creates_with_empty_tools(self):
        agent = _make_agent()
        assert agent.tools == []

    def test_creates_with_empty_default_tools(self):
        agent = _make_agent()
        assert agent.include_default_tools == []

    def test_strip_inherited_npm_env_keeps_subprocesses_out_of_parent_context(self):
        env = {
            "INIT_CWD": "/repo",
            "npm_config_prefix": "/repo",
            "npm_package_name": "parent-package",
            "NPM_CONFIG_PREFIX": "/repo",
            "PATH": "/usr/bin",
            "USER_VALUE": "kept",
        }

        _strip_inherited_npm_env(env)

        assert env == {
            "PATH": "/usr/bin",
            "USER_VALUE": "kept",
        }

    def test_requires_acp_command(self):
        with pytest.raises(Exception):
            ACPAgent()  # type: ignore[call-arg]

    def test_acp_command_stored(self):
        agent = ACPAgent(acp_command=["npx", "-y", "claude-agent-acp"])
        assert agent.acp_command == ["npx", "-y", "claude-agent-acp"]

    def test_acp_args_default_empty(self):
        agent = _make_agent()
        assert agent.acp_args == []

    def test_get_all_llms_yields_sentinel(self):
        agent = _make_agent()
        llms = list(agent.get_all_llms())
        assert len(llms) == 1
        assert llms[0].model == "acp-managed"

    def test_agent_is_frozen(self):
        agent = _make_agent()
        with pytest.raises(Exception):
            agent.acp_command = ["other"]  # type: ignore[misc]

    def test_acp_model_propagated_to_metrics(self):
        """设置 acp_model 时，metrics.model_name 应反映实际模型。"""
        agent = _make_agent(acp_model="gemini-3-flash-preview")
        assert agent.llm.metrics.model_name == "gemini-3-flash-preview"
        assert agent.llm.metrics.accumulated_token_usage is not None
        assert (
            agent.llm.metrics.accumulated_token_usage.model == "gemini-3-flash-preview"
        )

    def test_acp_model_propagated_to_llm_model(self):
        """acp_model 覆盖哨兵值模型名称，以便显示日志/状态
        真实模型。 ACP-哨兵值标记位于 usage_id 上。"""
        agent = _make_agent(acp_model="claude-opus-4-6")
        assert agent.llm.model == "claude-opus-4-6"
        assert agent.llm.usage_id == "acp-managed"

    def test_sentinel_usage_id_without_acp_model(self):
        agent = _make_agent()
        assert agent.llm.model == "acp-managed"
        assert agent.llm.usage_id == "acp-managed"

    def test_no_acp_model_keeps_sentinel(self):
        """如果没有 acp_model，metrics.model_name 仍为哨兵值值。"""
        agent = _make_agent()
        assert agent.llm.metrics.model_name == "acp-managed"

    def test_acp_model_used_in_cost_entries(self):
        """成本条目应使用实际型号名称，而不是哨兵值。"""
        agent = _make_agent(acp_model="claude-opus-4-6")
        agent.llm.metrics.add_cost(0.05)
        assert agent.llm.metrics.costs[0].model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


class TestACPAgentSerialization:
    def test_kind_is_acp_agent(self):
        agent = _make_agent()
        data = json.loads(agent.model_dump_json())
        assert data["kind"] == "ACPAgent"

    def test_roundtrip_serialization(self):
        agent = ACPAgent(
            acp_command=["npx", "-y", "claude-agent-acp"],
            acp_args=["--verbose"],
        )
        dumped = agent.model_dump_json()
        restored = AgentBase.model_validate_json(dumped)
        assert isinstance(restored, ACPAgent)
        assert restored.acp_command == agent.acp_command
        assert restored.acp_args == agent.acp_args

    def test_deserialization_from_dict(self):
        data = {
            "kind": "ACPAgent",
            "acp_command": ["echo", "test"],
        }
        agent = AgentBase.model_validate(data)
        assert isinstance(agent, ACPAgent)
        assert agent.acp_command == ["echo", "test"]


# ---------------------------------------------------------------------------
# 特征验证（init_state守卫）
# ---------------------------------------------------------------------------


class TestACPAgentValidation:
    """测试不支持的功能是否会在 init_state 中引发 NotImplementedError。"""

    def _init_with_patches(self, agent, tmp_path):
        """用 ACP SDK 模拟的呼出 init_state。"""
        state = _make_state(tmp_path)
        events = []
        with (
            patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"),
            patch(
                "openhands.sdk.utils.async_executor.AsyncExecutor",
                return_value=MagicMock(),
            ),
        ):
            agent.init_state(state, on_event=events.append)
        return events

    def test_allows_mcp_config(self, tmp_path):
        """mcp_config被转发到ACP子进程，没有被拒绝。

        服务器被翻译并传递到new_session/load_session（参见test_acp_mcp.py）； 这里我
        们只是断言 init_state 不再加
        注。
        """
        agent = ACPAgent(
            acp_command=["echo"],
            mcp_config=coerce_mcp_config({"test": {"command": "echo"}}),
        )
        # 不应提高； ACP 在会话创建时接收 MCP 服务器，而不是 OpenHands 创建进程内运行时
        # MCP 工具。
        #
        self._init_with_patches(agent, tmp_path)
        assert agent.supports_openhands_tools is False

    def test_allows_agent_context_for_prompt_extensions(self, tmp_path):
        agent = ACPAgent(
            acp_command=["echo"],
            agent_context=AgentContext(
                skills=[
                    Skill(
                        name="review",
                        content="Review instructions",
                        trigger=KeywordTrigger(keywords=["/review"]),
                    )
                ]
            ),
        )

        self._init_with_patches(agent, tmp_path)

    def test_allows_agent_context_with_secrets(self, tmp_path):
        """机密现在与 ACP 兼容：它们被注入到子进程中
        env 由 _start_acp_server 并通过 <CUSTOM_SECRETS> 在提示词中公布。"""
        agent = ACPAgent(
            acp_command=["echo"],
            agent_context=AgentContext(secrets={"GITHUB_TOKEN": "ghp_secret"}),
        )
        # 不应该提高
        self._init_with_patches(agent, tmp_path)

    def test_agent_context_to_acp_prompt_context(self):
        context = AgentContext(
            skills=[
                Skill(
                    name="review",
                    content="Full review instructions",
                    trigger=KeywordTrigger(keywords=["/review"]),
                    description="Review pull requests.",
                )
            ],
            system_message_suffix="Follow repository rules.",
            user_message_suffix="Prefer concise responses.",
            current_datetime="2026-04-24T00:00:00",
        )

        prompt = context.to_acp_prompt_context()

        assert prompt is not None
        # 由与一般智能体使用的相同的提示词注册表组装，因此呈现的动态层部分是相同的。
        #
        assert "<CURRENT_DATETIME>" in prompt
        assert "2026-04-24T00:00:00" in prompt
        assert "<name>review</name>" in prompt
        assert "<description>Review pull requests.</description>" in prompt
        assert "Full review instructions" not in prompt
        assert "Follow repository rules." in prompt
        # user_message_suffix 不是由 to_acp_prompt_context 发出的，因为
        # LocalConversation 已经通过 event.to_llm_message() 应用了它。
        #
        assert "Prefer concise responses." not in prompt

    def test_agent_context_to_acp_prompt_context_returns_none_when_empty(self):
        context = AgentContext(skills=[], current_datetime=None)

        assert context.to_acp_prompt_context() is None

    def test_agent_context_to_acp_prompt_context_emits_datetime_by_default(self):
        context = AgentContext(skills=[])

        prompt = context.to_acp_prompt_context()
        assert prompt is not None
        assert "<CURRENT_DATETIME>" in prompt

    def test_agent_context_to_acp_prompt_context_includes_secrets(self):
        """机密作为 <CUSTOM_SECRETS> 块出现在 ACP 提示词中，因此
        ACP 子进程知道哪些环境变量可用。"""
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        context = AgentContext(
            secrets={
                "GITHUB_TOKEN": StaticSecret(
                    value=SecretStr("ghp_secret"),
                    description="GitHub authentication token",
                ),
                "MY_API_KEY": StaticSecret(value=SecretStr("key123")),
            },
            current_datetime=None,
        )

        prompt = context.to_acp_prompt_context()

        assert prompt is not None
        assert "<CUSTOM_SECRETS>" in prompt
        assert "$GITHUB_TOKEN" in prompt
        assert "GitHub authentication token" in prompt
        assert "$MY_API_KEY" in prompt

    def test_agent_context_to_acp_prompt_context_includes_legacy_repo_skills(self):
        context = AgentContext(
            skills=[
                Skill(
                    name="claude",
                    content="Always follow the repository review checklist.",
                    trigger=None,
                ),
                Skill(
                    name="repo-skill",
                    content="Full AgentSkills instructions should stay out.",
                    description="Use repo-specific tools.",
                    is_agentskills_format=True,
                ),
            ],
            current_datetime=None,
        )

        prompt = context.to_acp_prompt_context()

        assert prompt is not None
        assert "<REPO_CONTEXT>" in prompt
        assert "[BEGIN context from [claude]]" in prompt
        assert "Always follow the repository review checklist." in prompt
        assert "<name>repo-skill</name>" in prompt
        assert "<description>Use repo-specific tools.</description>" in prompt
        assert "Full AgentSkills instructions should stay out." not in prompt
        assert "<name>claude</name>" not in prompt

    def test_agent_context_to_acp_prompt_context_lists_legacy_triggered_skills(self):
        context = AgentContext(
            skills=[
                Skill(
                    name="roasted-review",
                    content="Use a stricter review tone.",
                    trigger=KeywordTrigger(keywords=["/roasted"]),
                    description="Run a stricter review.",
                )
            ],
            current_datetime=None,
        )

        prompt = context.to_acp_prompt_context()

        assert prompt is not None
        assert "<REPO_CONTEXT>" not in prompt
        assert "<name>roasted-review</name>" in prompt
        assert "<description>Run a stricter review.</description>" in prompt
        assert "Use a stricter review tone." not in prompt

    def test_build_acp_prompt_preserves_all_text_blocks(self):
        agent = _make_agent(
            agent_context=AgentContext(
                user_message_suffix="Prefer concise responses.",
                current_datetime=None,
            )
        )
        event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[
                    TextContent(text="First block."),
                    TextContent(text="Second block."),
                ],
            ),
            extended_content=[TextContent(text="Prefer concise responses.")],
        )

        blocks = agent._build_acp_prompt(event)

        assert blocks is not None
        texts = [b.text for b in blocks if hasattr(b, "text")]
        assert "First block." in texts
        assert "Second block." in texts
        assert sum(1 for t in texts if t == "Prefer concise responses.") == 1

    def test_build_acp_prompt_includes_image_content(self):
        agent = _make_agent()
        event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[
                    TextContent(text="What is in this image?"),
                    ImageContent(image_urls=["data:image/png;base64,iVBOR"]),
                ],
            ),
        )

        blocks = agent._build_acp_prompt(event)

        assert blocks is not None
        assert len(blocks) == 2
        assert blocks[0].type == "text"
        assert blocks[0].text == "What is in this image?"
        assert blocks[1].type == "image"
        assert blocks[1].data == "iVBOR"
        assert blocks[1].mime_type == "image/png"


class TestImageUrlToAcpBlock:
    def test_data_uri(self):
        block = _image_url_to_acp_block("data:image/jpeg;base64,/9j/4AAQ")
        assert block is not None
        assert block.data == "/9j/4AAQ"
        assert block.mime_type == "image/jpeg"

    def test_plain_url(self):
        block = _image_url_to_acp_block("https://example.com/img.png")
        assert block is not None
        assert block.uri == "https://example.com/img.png"

    def test_invalid_data_uri_returns_none(self):
        block = _image_url_to_acp_block("data:broken")
        assert block is None

    def test_real_png_round_trips(self):
        """验证真实的 PNG 图像在整个转换路径中是否存在。"""
        import base64
        import struct
        import zlib

        # 最小有效 1x1 红色 PNG
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        raw = zlib.compress(b"\x00\xff\x00\x00")
        idat_crc = zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF
        idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        png_bytes = sig + ihdr + idat + iend

        b64_data = base64.b64encode(png_bytes).decode()
        data_uri = f"data:image/png;base64,{b64_data}"

        block = _image_url_to_acp_block(data_uri)
        assert block is not None
        assert block.mime_type == "image/png"
        decoded = base64.b64decode(block.data)
        assert decoded == png_bytes
        assert decoded[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# init_state
# ---------------------------------------------------------------------------


class TestACPAgentInitState:
    def test_init_state_emits_system_prompt_placeholder(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        events: list = []

        with (
            patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"),
        ):
            agent.init_state(state, on_event=events.append)

        assert len(events) == 1
        assert isinstance(events[0], SystemPromptEvent)
        assert "ACP server" in events[0].system_prompt.text
        assert events[0].tools == []

    def test_init_state_no_dynamic_context_without_agent_context(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        events: list = []

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=events.append)

        assert events[0].dynamic_context is None

    def test_init_state_populates_dynamic_context_from_suffix(self, tmp_path):
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)
        events: list = []

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=events.append)

        assert events[0].dynamic_context is not None
        assert "Team rules." in events[0].dynamic_context.text

    def test_init_state_sets_pending_state_for_new_session(self, tmp_path):
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=lambda _: None)

        assert agent._suffix_install_state == "pending_first_prompt"
        assert agent._installed_suffix is not None
        assert "Team rules." in agent._installed_suffix

    def test_init_state_sets_installed_when_suffix_marker_persisted(self, tmp_path):
        """成功的第一轮持续 ``acp_suffix_installed`` — 恢复时
        的 ACPAgent 读取该标记并跳过重新注入。"""
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)
        state.agent_state = {
            "acp_session_id": "prior-session-id",
            "acp_suffix_installed": True,
        }

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=lambda _: None)

        assert agent._suffix_install_state == "installed"

    def test_init_state_pending_when_session_id_only_no_suffix_marker(self, tmp_path):
        """已持久化 ``acp_session_id`` 没有 ``acp_suffix_installed`` 表示
        先前的会话已创建，但其第一个提示词从未完成（在 ``_finalize_successful_turn``
        之前取消/崩溃）。 ACP 子进程从未收到后缀；
         在恢复时，我们必须在下一轮重新注入它，而不是仅从会话 ID 的存在推断“已安装”。
        """
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)
        state.agent_state = {"acp_session_id": "prior-session-id"}

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=lambda _: None)

        assert agent._suffix_install_state == "pending_first_prompt"

    def test_init_state_includes_registry_secrets_in_suffix(self, tmp_path):
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(agent_context=AgentContext(current_datetime=None))
        state = _make_state(tmp_path)
        state.secret_registry.update_secrets(
            {
                "REGISTRY_TOKEN": StaticSecret(
                    value=SecretStr("tok"), description="Registry token"
                )
            }
        )
        events: list = []

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=events.append)

        assert events[0].dynamic_context is not None
        assert "REGISTRY_TOKEN" in events[0].dynamic_context.text

    def test_init_state_renders_registry_secrets_without_agent_context(self, tmp_path):
        """<CUSTOM_SECRETS> 块应单独从 secret_registry 渲染。

        通过规范对话渠道发送机密的呼叫者 (``StartConversationRequest.secrets`` →
        ``Conversation.update_secrets`` → ``secret_registry``) 但不要附加
        ``AgentContext``，
        不应该看到这些机密无声地从系统后缀中删除 —— 值仍然通过 ``_start_acp_server``
        流入子进程环境，因此智能体需要知道它们是可用的。
        """
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()  # 没有 agent_context
        state = _make_state(tmp_path)
        state.secret_registry.update_secrets(
            {
                "REGISTRY_TOKEN": StaticSecret(
                    value=SecretStr("tok"), description="Registry token"
                )
            }
        )
        events: list = []

        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=events.append)

        assert events[0].dynamic_context is not None
        assert "REGISTRY_TOKEN" in events[0].dynamic_context.text

    # -- 冷启动错误出现（问题#1024） --------------------------

    def _init_state_failure(self, tmp_path, exc: BaseException):
        """运行 init_state，``_start_acp_server`` 加注 ``exc``。

        返回 ``(state, events, raised)``，其中 ``raised`` 是转义 init_state 的异常（
        断言是原始 ``exc``）
        。
        """
        agent = _make_agent()
        state = _make_state(tmp_path)
        events: list = []
        with patch(
            "openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server",
            side_effect=exc,
        ):
            with pytest.raises(type(exc)) as excinfo:
                agent.init_state(state, on_event=events.append)
        assert excinfo.value is exc, "original exception must propagate unchanged"
        return state, events

    def test_init_state_surfaces_auth_required(self, tmp_path):
        """认证要求的协议错误变成一个类型 ACPAuthRequired 事件
        具有 ERROR 状态 - 而不是绕过发射并以通用的“远程对话因错误结束”的方式到达客户
        端。
        """
        exc = ACPRequestError(-32000, "Authentication required")
        state, events = self._init_state_failure(tmp_path, exc)

        errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1
        assert errors[0].source == "agent"
        assert errors[0].code == "ACPAuthRequired"
        assert "Authentication required" in errors[0].detail
        assert state.execution_status == ConversationExecutionStatus.ERROR

    def test_init_state_surfaces_spawn_error(self, tmp_path):
        """丢失/无法执行的 CLI 二进制文件 (FileNotFoundError /
        PermissionError 从 create_subprocess_exec 开始，变为 ACPSpawnError。"""
        for exc in (
            FileNotFoundError("no such file: claude-agent-acp"),
            PermissionError("permission denied"),
        ):
            state, events = self._init_state_failure(tmp_path, exc)
            errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
            assert len(errors) == 1
            assert errors[0].code == "ACPSpawnError"
            assert state.execution_status == ConversationExecutionStatus.ERROR

    def test_init_state_surfaces_generic_init_error(self, tmp_path):
        """任何其他握手/会话失败都回退到 ACPInitError。"""
        exc = RuntimeError("protocol handshake timed out")
        state, events = self._init_state_failure(tmp_path, exc)

        errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1
        assert errors[0].code == "ACPInitError"
        assert "protocol handshake timed out" in errors[0].detail
        assert state.execution_status == ConversationExecutionStatus.ERROR

    def test_init_state_surfaces_request_error_data(self, tmp_path):
        """``RequestError`` 冷启动故障表面其 ``.code`` 和
        ``.data`` — 不是 ``str(exc)`` 产生的纯粹的“内部错误” — 因此真正的原因（此处的
        身份验证标记）到达了用户并被分类。
        """
        exc = ACPRequestError(
            -32603, "Internal error", {"message": "401 Unauthorized from provider"}
        )
        _state, events = self._init_state_failure(tmp_path, exc)
        errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1
        assert errors[0].code == "ACPAuthRequired"
        assert "401 Unauthorized from provider" in errors[0].detail
        assert "-32603" in errors[0].detail

    def test_init_state_truncates_long_detail(self, tmp_path):
        """详细信息的上限为 500 个字符，与运行循环错误路径匹配。"""
        exc = RuntimeError("x" * 1000)
        _state, events = self._init_state_failure(tmp_path, exc)
        errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
        assert len(errors[0].detail) == 500

    def test_init_state_reraises_even_if_emission_fails(self, tmp_path):
        """暴露错误时的失败绝不能掩盖原来的错误
        exception — 依赖于的重抛合同 run()/arun() 仍保留。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        exc = RuntimeError("boom")

        def _explode(_event):
            raise ValueError("on_event is broken")

        with patch(
            "openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server",
            side_effect=exc,
        ):
            with pytest.raises(RuntimeError, match="boom") as excinfo:
                agent.init_state(state, on_event=_explode)
        assert excinfo.value is exc


# ---------------------------------------------------------------------------
# _classify_acp_init_error
# ---------------------------------------------------------------------------


class TestClassifyACPInitError:
    def test_auth_required_code(self):
        exc = ACPRequestError(-32000, "Authentication required")
        assert _classify_acp_init_error(exc) == "ACPAuthRequired"

    def test_other_request_error_is_init_error(self):
        # 不需要身份验证的协议错误 (e.g. 内部错误）是一般的初始化失败，而不是身份验证失
        # 败。
        #
        exc = ACPRequestError(-32603, "Internal error")
        assert _classify_acp_init_error(exc) == "ACPInitError"

    def test_timeout_error_is_startup_timeout(self):
        assert _classify_acp_init_error(TimeoutError()) == "ACPStartupTimeout"

    def test_file_not_found_is_spawn_error(self):
        assert _classify_acp_init_error(FileNotFoundError()) == "ACPSpawnError"

    def test_permission_error_is_spawn_error(self):
        assert _classify_acp_init_error(PermissionError()) == "ACPSpawnError"

    def test_broken_pipe_is_init_error(self):
        # A 传输层握手期间掉包是 OSError 子类但不是生成失败 - 它必须分类为 ACPInitError,
        #  not ACPSpawnError.
        #
        assert _classify_acp_init_error(BrokenPipeError()) == "ACPInitError"

    def test_generic_exception_is_init_error(self):
        assert _classify_acp_init_error(RuntimeError("x")) == "ACPInitError"

    def test_auth_marker_in_internal_error_is_auth_required(self):
        # 服务器将上游 401/403 折叠为通用 -32603 而不是 -32000； 该消息/数据仍然揭示了凭
        # 据失败，必须映射到ACPAuthRequired，以便客户端可以提供重新认证。
        #
        exc = ACPRequestError(
            -32603, "Internal error", {"message": "401 Unauthorized: invalid api key"}
        )
        assert _classify_acp_init_error(exc) == "ACPAuthRequired"

    def test_benign_internal_error_stays_init_error(self):
        # 没有 auth 标记的 -32603 是一般的 init 失败，而不是 auth。
        exc = ACPRequestError(-32603, "Internal error", {"message": "disk full"})
        assert _classify_acp_init_error(exc) == "ACPInitError"


def test_file_credential_sync_failure_is_init_error():
    assert (
        _classify_acp_init_error(ACPFileCredentialSyncError("unavailable"))
        == "ACPInitError"
    )


# ---------------------------------------------------------------------------
# _stringify_acp_error_data
# ---------------------------------------------------------------------------


class TestStringifyACPErrorData:
    def test_none_is_empty(self):
        assert _stringify_acp_error_data(None) == ""

    def test_bare_string_passthrough(self):
        assert _stringify_acp_error_data("OPENAI_API_KEY is not set") == (
            "OPENAI_API_KEY is not set"
        )

    def test_dict_prefers_message_key(self):
        # Codex 转向错误发送 {"message", "codex_error_info"}。
        out = _stringify_acp_error_data(
            {"message": "model not found", "codex_error_info": "gpt-9"}
        )
        assert out == "model not found (gpt-9)"

    def test_dict_details_key(self):
        # claude SDK catch-all 将非 RequestError 异常包装为 {"details"}。
        assert _stringify_acp_error_data({"details": "boom"}) == "boom"

    def test_opaque_dict_falls_back_to_json(self):
        out = _stringify_acp_error_data({"foo": "bar"})
        assert "foo" in out and "bar" in out


# ---------------------------------------------------------------------------
# _acp_error_indicates_auth
# ---------------------------------------------------------------------------


class TestACPErrorIndicatesAuth:
    def test_explicit_auth_code(self):
        assert _acp_error_indicates_auth(
            ACPRequestError(-32000, "Authentication required")
        )

    def test_marker_in_message(self):
        assert _acp_error_indicates_auth(
            ACPRequestError(-32603, "Internal error: please run /login")
        )

    def test_marker_in_data(self):
        assert _acp_error_indicates_auth(
            ACPRequestError(-32603, "Internal error", {"message": "token expired"})
        )

    def test_marker_in_plain_exception(self):
        assert _acp_error_indicates_auth(RuntimeError("HTTP 401 Unauthorized"))

    def test_no_marker(self):
        assert not _acp_error_indicates_auth(ACPRequestError(-32603, "Internal error"))
        assert not _acp_error_indicates_auth(RuntimeError("timed out"))

    def test_http_401_as_word_matches(self):
        assert _acp_error_indicates_auth(RuntimeError("HTTP 401 Unauthorized"))

    def test_digit_substring_in_timeout_does_not_match(self):
        # “4031ms”包含“403”，但不得触发 — 字边界检查。
        assert not _acp_error_indicates_auth(RuntimeError("timeout after 4031ms"))

    def test_model_id_with_401_does_not_match(self):
        assert not _acp_error_indicates_auth(
            ACPRequestError(
                -32603, "Internal error", {"message": "model id '401b' not found"}
            )
        )


# ---------------------------------------------------------------------------
# _classify_acp_turn_error
# ---------------------------------------------------------------------------


class TestClassifyACPTurnError:
    def test_generic_turn_error(self):
        assert _classify_acp_turn_error(RuntimeError("boom")) == "ACPPromptError"

    def test_usage_policy_refusal(self):
        exc = RuntimeError("blocked by usage policy")
        assert _classify_acp_turn_error(exc) == "UsagePolicyRefusal"

    def test_content_policy_refusal(self):
        exc = ACPRequestError(-32603, "Internal error", {"message": "content policy"})
        assert _classify_acp_turn_error(exc) == "UsagePolicyRefusal"

    def test_auth_failure_maps_to_auth_required(self):
        # 错误的凭据出现在中间，因为 -32603 仍必须路由到重新验证。
        exc = ACPRequestError(-32603, "Internal error", {"message": "401 unauthorized"})
        assert _classify_acp_turn_error(exc) == "ACPAuthRequired"


def test_file_credential_sync_failure_is_prompt_error():
    assert (
        _classify_acp_turn_error(ACPFileCredentialSyncError("unavailable"))
        == "ACPPromptError"
    )


# ---------------------------------------------------------------------------
# _acp_error_detail
# ---------------------------------------------------------------------------


class TestACPErrorDetail:
    def test_plain_exception_is_str(self):
        assert _acp_error_detail(RuntimeError("boom")) == "boom"

    def test_request_error_keeps_code_and_data(self):
        # 此修复的错误：str(RequestError) 只是“内部错误”； 真正的原因位于 .code/.data 中
        # 并且必须到达用户。
        #
        exc = ACPRequestError(
            -32603, "Internal error", {"message": "model gpt-9 not found"}
        )
        detail = _acp_error_detail(exc)
        assert "-32603" in detail
        assert "model gpt-9 not found" in detail

    def test_request_error_bare_data_string(self):
        exc = ACPRequestError(-32603, "Internal error", "OPENAI_API_KEY is not set")
        detail = _acp_error_detail(exc)
        assert "OPENAI_API_KEY is not set" in detail

    def test_no_duplicate_when_data_matches_message(self):
        exc = ACPRequestError(-32000, "Authentication required")
        detail = _acp_error_detail(exc)
        assert detail == "[-32000] Authentication required"

    def test_data_appended_when_it_differs_from_message(self):
        # data[“message”] 与 exc.message 不同 → 必须包含在内。
        exc = ACPRequestError(
            -32603, "Internal error", {"message": "model gpt-9 not found"}
        )
        detail = _acp_error_detail(exc)
        assert "model gpt-9 not found" in detail
        assert "Internal error" in detail

    def test_data_not_duplicated_when_equal_to_message(self):
        # 当 data["message"] == exc.message 时，无需添加任何额外内容 — 避免“[-32603] 内
        # 部错误：内部错误”冗余。
        #
        exc = ACPRequestError(-32603, "Internal error", {"message": "Internal error"})
        detail = _acp_error_detail(exc)
        assert detail == "[-32603] Internal error"

    def test_truncated_to_500_chars(self):
        exc = ACPRequestError(-32603, "Internal error", "x" * 1000)
        assert len(_acp_error_detail(exc)) == 500

    def test_pattern_redaction_of_data(self):
        # redact_text_secrets 磨砂 api_key=... 即使没有注册表。
        exc = ACPRequestError(-32603, "Internal error", "api_key='sk-leakme123'")
        detail = _acp_error_detail(exc)
        assert "sk-leakme123" not in detail
        assert "<redacted>" in detail

    def test_registry_masks_tracked_secret_value(self):
        registry = SecretRegistry()
        registry.update_secrets({"PROVIDER_TOKEN": "supersecretvalue"})
        # 解析一次，以便跟踪该值以进行屏蔽。
        registry.get_all_secrets_as_env_vars()
        exc = ACPRequestError(
            -32603, "Internal error", {"message": "rejected supersecretvalue"}
        )
        detail = _acp_error_detail(exc, registry)
        assert "supersecretvalue" not in detail
        assert "<secret-hidden>" in detail


# ---------------------------------------------------------------------------
# _OpenHandsACPBridge
# ---------------------------------------------------------------------------


class TestOpenHandsACPClient:
    def test_reset_clears_state(self):
        client = _OpenHandsACPBridge()
        client.accumulated_text.append("hello")
        client.accumulated_thoughts.append("thinking")
        client.on_token = lambda _: None

        client.reset()

        assert client.accumulated_text == []
        assert client.accumulated_thoughts == []
        assert client.on_token is None

    @pytest.mark.asyncio
    async def test_session_update_accumulates_text(self):
        client = _OpenHandsACPBridge()
        client.accumulated_text.append("Hello")
        client.accumulated_text.append(" World")
        assert "".join(client.accumulated_text) == "Hello World"

    @pytest.mark.asyncio
    async def test_session_update_accumulates_thoughts(self):
        client = _OpenHandsACPBridge()
        client.accumulated_thoughts.append("Let me think")
        client.accumulated_thoughts.append(" about this")
        assert "".join(client.accumulated_thoughts) == "Let me think about this"

    def test_on_token_callback(self):
        client = _OpenHandsACPBridge()
        tokens: list[str] = []
        client.on_token = tokens.append

        # 模拟 session_update 会做什么
        text = "chunk1"
        client.accumulated_text.append(text)
        if client.on_token is not None:
            client.on_token(text)

        assert tokens == ["chunk1"]

    @pytest.mark.asyncio
    async def test_fs_methods_raise(self):
        client = _OpenHandsACPBridge()
        with pytest.raises(NotImplementedError):
            await client.write_text_file("c", "/f", "s1")
        with pytest.raises(NotImplementedError):
            await client.read_text_file("/f", "s1")

    @pytest.mark.asyncio
    async def test_terminal_methods_raise(self):
        client = _OpenHandsACPBridge()
        with pytest.raises(NotImplementedError):
            await client.create_terminal("bash", "s1")
        with pytest.raises(NotImplementedError):
            await client.terminal_output("s1", "t1")
        with pytest.raises(NotImplementedError):
            await client.release_terminal("s1", "t1")
        with pytest.raises(NotImplementedError):
            await client.wait_for_terminal_exit("s1", "t1")
        with pytest.raises(NotImplementedError):
            await client.kill_terminal("s1", "t1")

    @pytest.mark.asyncio
    async def test_ext_method_returns_empty_dict(self):
        client = _OpenHandsACPBridge()
        result = await client.ext_method("test", {})
        assert result == {}

    @pytest.mark.asyncio
    async def test_ext_notification_is_noop(self):
        client = _OpenHandsACPBridge()
        await client.ext_notification("test", {})  # 不应该提高


# ---------------------------------------------------------------------------
# 工具调用事件发射（启动 + 终端，无按进度扇出）
# ---------------------------------------------------------------------------


def _mk_tool_start(
    tool_call_id: str = "tc-1",
    *,
    title: str = "git status",
    kind: str = "execute",
    status: str = "in_progress",
    raw_input: Any | None = None,
    raw_output: Any | None = None,
    content: Any | None = None,
) -> Any:
    from acp.schema import ToolCallStart

    start = MagicMock(spec=ToolCallStart)
    start.tool_call_id = tool_call_id
    start.title = title
    start.kind = kind
    start.status = status
    start.raw_input = raw_input
    start.raw_output = raw_output
    start.content = content
    return start


def _mk_tool_progress(
    tool_call_id: str = "tc-1",
    *,
    title: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    raw_input: Any | None = None,
    raw_output: Any | None = None,
    content: Any | None = None,
) -> Any:
    from acp.schema import ToolCallProgress

    progress = MagicMock(spec=ToolCallProgress)
    progress.tool_call_id = tool_call_id
    progress.title = title
    progress.kind = kind
    progress.status = status
    progress.raw_input = raw_input
    progress.raw_output = raw_output
    progress.content = content
    return progress


class TestACPToolCallProgressCollapse:
    """该桥恰好持续存在一个 ``started`` + 一个终止事件。

    每个 ``ToolCallProgress`` 承载 * 完整累积 * 输出，因此每帧发出一个事件是 O(n^2)
    存储 + WebSocket 继电器。 相反，桥
    接器会传输一个早期 ``started`` 事件和一个终端 (``completed`` /
    ``failed``) 每个 ``tool_call_id`` 的事件 — 操作 ->观测结果对 —
    while silently accumulating the intermediate frames so the terminal event
    仍然带有最终输出。
    """

    @pytest.mark.asyncio
    async def test_tool_call_start_emits_started_event(self) -> None:
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update("s1", _mk_tool_start(status="in_progress"))

        assert len(events) == 1
        assert isinstance(events[0], ACPToolCallEvent)
        assert events[0].tool_call_id == "tc-1"
        assert events[0].status == "in_progress"
        assert events[0].is_error is False

    @pytest.mark.asyncio
    async def test_intermediate_progress_frames_are_not_emitted(self) -> None:
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update("s1", _mk_tool_start(status="in_progress"))
        # 几个非终端进度框架，累积输出不断增长。
        for chunk in ("a", "ab", "abc"):
            await client.session_update(
                "s1", _mk_tool_progress(status="in_progress", raw_output=chunk)
            )

        # 只有开始的事件是已持久化 - 中间帧默默地累积（这是 O(n^2)->O(1) 崩溃）。
        #
        assert len(events) == 1
        assert events[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_full_lifecycle_emits_exactly_two_events(self) -> None:
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update("s1", _mk_tool_start(status="pending"))
        await client.session_update(
            "s1", _mk_tool_progress(status="in_progress", raw_output="partial")
        )
        await client.session_update(
            "s1", _mk_tool_progress(status="completed", raw_output="partial-final")
        )

        assert len(events) == 2
        started, terminal = events
        assert started.status == "pending"
        assert terminal.status == "completed"
        # 终端事件承载最终的累积输出。
        assert terminal.raw_output == "partial-final"
        assert terminal.is_error is False

    @pytest.mark.asyncio
    async def test_failed_terminal_sets_is_error(self) -> None:
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update("s1", _mk_tool_start(status="in_progress"))
        await client.session_update(
            "s1", _mk_tool_progress(status="failed", raw_output="boom")
        )

        assert len(events) == 2
        assert events[-1].status == "failed"
        assert events[-1].is_error is True

    @pytest.mark.asyncio
    async def test_single_shot_completed_start_emits_once(self) -> None:
        """已经终止的 ToolCallStart 是唯一的事件。"""
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update(
            "s1", _mk_tool_start(status="completed", raw_output="done")
        )

        assert len(events) == 1
        assert events[0].status == "completed"

    @pytest.mark.asyncio
    async def test_redundant_terminal_progress_does_not_double_emit(self) -> None:
        """只有第一次转换到终端状态时才会发出。"""
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append

        await client.session_update("s1", _mk_tool_start(status="in_progress"))
        await client.session_update("s1", _mk_tool_progress(status="completed"))
        # 尾随的重复终端帧不得产生第三个事件。
        await client.session_update("s1", _mk_tool_progress(status="completed"))

        assert len(events) == 2
        assert [e.status for e in events] == ["in_progress", "completed"]

    def test_finalize_flush_completes_orphaned_tool_calls(self) -> None:
        """服务器打开但从未关闭的卡将刷新为完成。"""
        agent = _make_agent()
        client = _OpenHandsACPBridge()
        events: list[Any] = []
        client.on_event = events.append
        agent._client = client

        # 一个仍在运行的呼叫和一个已经终止的呼叫。
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": "live-1",
                "title": "long task",
                "tool_kind": "execute",
                "status": "in_progress",
                "raw_input": None,
                "raw_output": "partial output",
                "content": None,
            }
        )
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": "done-1",
                "title": "quick task",
                "tool_kind": "read",
                "status": "completed",
                "raw_input": None,
                "raw_output": "ok",
                "content": None,
            }
        )

        agent._flush_inflight_tool_calls_as_completed()

        # 仅刷新非终端调用（终端调用不受影响）。
        assert len(events) == 1
        assert events[0].tool_call_id == "live-1"
        assert events[0].status == "completed"
        assert events[0].is_error is False
        assert events[0].raw_output == "partial output"
        # 累加器条目现在已终止，因此不会再次刷新。
        assert client.accumulated_tool_calls[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Activity heartbeat
# ---------------------------------------------------------------------------


class TestACPActivityHeartbeat:
    """测试 _OpenHandsACPBridge 中的 on_activity 心跳。"""

    def test_reset_clears_on_activity(self):
        client = _OpenHandsACPBridge()
        client.on_activity = lambda: None
        client.reset()
        assert client.on_activity is None

    def test_reset_preserves_last_activity_signal(self):
        """_last_activity_signal 在重置后仍然存在（如遥测状态）。"""
        client = _OpenHandsACPBridge()
        client._last_activity_signal = 999.0
        client.reset()
        assert client._last_activity_signal == 999.0

    def test_idle_clock_unarmed_reports_infinite_idle(self):
        """在启动之前，空闲时钟会报告无限的间隙。"""
        client = _OpenHandsACPBridge()
        assert client.seconds_since_last_activity() == float("inf")

    def test_arm_activity_clock_resets_idle(self):
        client = _OpenHandsACPBridge()
        client.arm_activity_clock()
        # 刚刚武装→活动后零秒有效。
        assert client.seconds_since_last_activity() < 1.0

    @pytest.mark.asyncio
    async def test_session_update_records_activity_for_idle_clock(self):
        """每个 session_update 都会重置空闲时钟，即使在节流时也是如此。

        _last_activity_signal 速率限制心跳和_last_activity_monotonic 停机计时器是独立
        的：在速率限制窗口内进行第二次更
        新不会重新触发on_activity，但仍然计为进度超时。
        """
        from acp.schema import AgentThoughtChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client._last_activity_monotonic = float("-inf")

        # 思想块根本不会触发 on_activity 心跳，但仍必须算作空闲时钟的活动。
        #
        chunk = MagicMock(spec=AgentThoughtChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "thinking"
        await client.session_update("sess-1", chunk)

        assert client.seconds_since_last_activity() < 1.0

    @pytest.mark.asyncio
    async def test_tool_call_start_signals_activity(self):
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        signals: list[bool] = []
        client.on_activity = lambda: signals.append(True)

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read file"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None

        await client.session_update("sess-1", start)
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_tool_call_progress_signals_activity(self):
        from acp.schema import ToolCallProgress, ToolCallStart

        client = _OpenHandsACPBridge()
        signals: list[bool] = []
        client.on_activity = lambda: signals.append(True)

        # 首先需要一个ToolCallStart
        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None
        await client.session_update("sess-1", start)

        # 重置油门，以便 ToolCallProgress 可以开火
        client._last_activity_signal = float("-inf")
        signals.clear()

        progress = MagicMock(spec=ToolCallProgress)
        progress.tool_call_id = "tc-1"
        progress.title = None
        progress.kind = None
        progress.status = "completed"
        progress.raw_input = None
        progress.raw_output = "ok"
        progress.content = None
        await client.session_update("sess-1", progress)
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_agent_message_chunk_signals_activity(self):
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        signals: list[bool] = []
        client.on_activity = lambda: signals.append(True)

        chunk = MagicMock(spec=AgentMessageChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "hello"

        await client.session_update("sess-1", chunk)
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_activity_signal_is_throttled(self):
        """信号应限制在每个时间间隔最多一个。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        signals: list[bool] = []
        client.on_activity = lambda: signals.append(True)

        for i in range(5):
            start = MagicMock(spec=ToolCallStart)
            start.tool_call_id = f"tc-{i}"
            start.title = f"Tool {i}"
            start.kind = "read"
            start.status = "completed"
            start.raw_input = None
            start.raw_output = None
            start.content = None
            await client.session_update("sess-1", start)

        # 所有这些都发生在同一个油门窗口内→只有 1 个信号
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_no_signal_without_callback(self):
        """当on_activity为None时没有错误。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        assert client.on_activity is None

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Tool"
        start.kind = "read"
        start.status = "completed"
        start.raw_input = None
        start.raw_output = None
        start.content = None

        await client.session_update("sess-1", start)  # 不应该提高

    @pytest.mark.asyncio
    async def test_activity_callback_error_is_swallowed(self):
        """on_activity 中的错误不得破坏 session_update。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        client.on_activity = MagicMock(side_effect=RuntimeError("boom"))

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Tool"
        start.kind = "read"
        start.status = "completed"
        start.raw_input = None
        start.raw_output = None
        start.content = None

        await client.session_update("sess-1", start)  # 不应该提高
        client.on_activity.assert_called_once()

    def test_step_wires_on_activity(self, tmp_path):
        """step() 应在 _on_activity 的桥上设置 on_activity。"""
        agent = _make_agent()
        state = _make_state(tmp_path)

        # 连接用户消息
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="sys"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="test")]),
            ),
        )

        activity_fn = MagicMock()
        agent._on_activity = activity_fn

        # 模拟对象内部结构，因此 step() 实际上并不调用 ACP 服务器
        agent._client = _OpenHandsACPBridge()

        # 在 prompt() 还在运行时捕获 on_activity —— 在 step() 完成后， 回调的 finally 块
        # 会断开，这样返回值 None 是设计的。
        #
        wired_during_prompt: list = []

        def _capture_run_async(_coro, **_kwargs):
            wired_during_prompt.append(agent._client.on_activity)
            return MagicMock(usage=None)

        agent._executor = MagicMock()
        agent._executor.run_async = _capture_run_async
        agent._session_id = "sess-1"
        agent._initialized = True

        conversation = MagicMock()
        conversation.state = state
        events: list = []

        agent.step(conversation, on_event=events.append)

        # 验证 on_activity 在转弯期间已连接至桥。
        assert wired_during_prompt == [activity_fn]
        # 并且后来它被清除，因此迟到的 session_update 无法在带外触发每轮心跳回调。
        #
        assert agent._client.on_activity is None


# ---------------------------------------------------------------------------
# 提示词空闲（不活动）超时
# ---------------------------------------------------------------------------


class TestACPPromptIdleTimeout:
    """提示词截止时间是空闲的超时：ACP 活动将其重置。

    回归对智能体-canvas#1245 的覆盖率 —— 长运行的 ACP 提示词必须像智能体进展一样继续
    运行，而不是在硬的时钟截止日期上死掉。
    """

    @pytest.mark.asyncio
    async def test_active_prompt_outlives_idle_window(self):
        """保持流式传输更新的提示词不会在截止日期前被杀死。

        智能体运行时间超过``acp_prompt_timeout``总时长，但比空闲窗口
        ``session_update`` 更频繁地发出，因此截止日期不断重置
        ，提示词正常完成。
        """
        from acp.schema import AgentMessageChunk, TextContentBlock

        agent = _make_agent(acp_prompt_timeout=0.3)
        client = _OpenHandsACPBridge()
        agent._client = client
        client.arm_activity_clock()

        sentinel = object()

        async def _active_prompt() -> Any:
            # 总共约 0.5 秒（> 0.3 秒空闲窗口），但每 0.02 秒（<< 0.3 秒）一次，因此空闲
            # 时钟永远不会消失。
            #
            for _ in range(25):
                await asyncio.sleep(0.02)
                chunk = MagicMock(spec=AgentMessageChunk)
                chunk.content = MagicMock(spec=TextContentBlock)
                chunk.content.text = "tick"
                await client.session_update("sess-1", chunk)
            return sentinel

        result = await agent._await_with_idle_deadline(
            _active_prompt(), cancel_on_exit=True
        )
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_silent_prompt_times_out_after_idle_window(self):
        """不产生任何活动的提示词将在空闲窗口后中止。"""
        agent = _make_agent(acp_prompt_timeout=0.1)
        client = _OpenHandsACPBridge()
        agent._client = client
        client.arm_activity_clock()

        cancelled = asyncio.Event()

        async def _silent_prompt() -> Any:
            try:
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return object()

        with pytest.raises(TimeoutError, match="no activity"):
            await agent._await_with_idle_deadline(_silent_prompt(), cancel_on_exit=True)

        # 助手取消超时上的基础提示词。
        await asyncio.wait_for(cancelled.wait(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_late_activity_extends_then_idle_times_out(self):
        """活动延长期限； 仍然超时后的沉默。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        agent = _make_agent(acp_prompt_timeout=0.15)
        client = _OpenHandsACPBridge()
        agent._client = client
        client.arm_activity_clock()

        async def _active_then_silent() -> Any:
            # 第一个空闲窗口过后的突发活动...
            await asyncio.sleep(0.1)
            chunk = MagicMock(spec=AgentMessageChunk)
            chunk.content = MagicMock(spec=TextContentBlock)
            chunk.content.text = "tick"
            await client.session_update("sess-1", chunk)
            # ...then go silent so the (extended) idle window elapses.
            await asyncio.sleep(5.0)
            return object()

        with pytest.raises(TimeoutError, match="no activity"):
            await agent._await_with_idle_deadline(
                _active_then_silent(), cancel_on_exit=True
            )


# ---------------------------------------------------------------------------
# 步骤
# ---------------------------------------------------------------------------


class TestACPAgentStep:
    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        """使用用户消息创建模拟对象对话。"""
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )

        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_step_emits_finish_action_event(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        # 设置模拟的运行时状态 — 在 * 重置后填充文本 *（step() 调用 client.reset()，然后
        # 调用 run_async 填充文本）
        #
        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("The answer is 4")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        # step() emits ActionEvent(FinishAction) + ObservationEvent(FinishObservation)
        # MessageEvent 不会发出 — FinishAction.message 包含响应文本
        assert len(events) == 2
        assert isinstance(events[0], ActionEvent)
        assert isinstance(events[0].action, FinishAction)
        assert events[0].action.message == "The answer is 4"

    @staticmethod
    def _wire_passthrough_mocks(agent: ACPAgent) -> None:
        """通过 asyncio 连接模拟对象 ACP 中继 prompt() 调用的内部结构。"""
        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        _agent_conn(agent).prompt = AsyncMock(return_value=None)
        agent._session_id = "test-session"

        def _fake_run_async(coro_factory, **_kwargs):
            return asyncio.run(coro_factory())

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

    def test_step_sends_skill_catalog_to_acp_server(self, tmp_path):
        agent = _make_agent(
            agent_context=AgentContext(
                skills=[
                    Skill(
                        name="review",
                        content="Full review instructions that ACP should not receive.",
                        trigger=KeywordTrigger(keywords=["/review"]),
                        description="Review pull requests.",
                    )
                ]
            )
        )
        state = _make_state(tmp_path)
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text="Review this PR.")],
                ),
                extended_content=[
                    TextContent(
                        text="<skill_context>Use strict review.</skill_context>"
                    )
                ],
            )
        )
        conversation = MagicMock()
        conversation.state = state
        self._wire_passthrough_mocks(agent)
        assert agent.agent_context is not None
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()
        agent._suffix_install_state = "pending_first_prompt"

        agent.step(conversation, on_event=lambda _: None)

        prompt_call = _agent_conn(agent).prompt.await_args
        assert prompt_call is not None
        assert prompt_call.kwargs["session_id"] == "test-session"
        prompt_blocks = prompt_call.kwargs["prompt"]
        prompt_text = "\n\n".join(b.text for b in prompt_blocks if hasattr(b, "text"))
        assert "Review this PR." in prompt_text
        assert "<name>review</name>" in prompt_text
        assert "<description>Review pull requests.</description>" in prompt_text
        assert "<skill_context>Use strict review.</skill_context>" in prompt_text
        assert (
            "Full review instructions that ACP should not receive." not in prompt_text
        )

    def test_step_sends_legacy_repo_context_to_acp_server(self, tmp_path):
        agent = _make_agent(
            agent_context=AgentContext(
                skills=[
                    Skill(
                        name="claude",
                        content="Always follow repository-specific review rules.",
                        trigger=None,
                    ),
                    Skill(
                        name="agent-skill",
                        content="AgentSkills full instructions should not be sent.",
                        is_agentskills_format=True,
                        description="Use the agent skill catalog entry.",
                    ),
                ],
                current_datetime=None,
            )
        )
        state = _make_state(tmp_path)
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text="Review this PR.")],
                ),
            )
        )
        conversation = MagicMock()
        conversation.state = state
        self._wire_passthrough_mocks(agent)
        assert agent.agent_context is not None
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()
        agent._suffix_install_state = "pending_first_prompt"

        agent.step(conversation, on_event=lambda _: None)

        prompt_call = _agent_conn(agent).prompt.await_args
        assert prompt_call is not None
        assert prompt_call.kwargs["session_id"] == "test-session"
        prompt_text = "\n\n".join(
            b.text for b in prompt_call.kwargs["prompt"] if hasattr(b, "text")
        )
        assert "Review this PR." in prompt_text
        assert "<REPO_CONTEXT>" in prompt_text
        assert "Always follow repository-specific review rules." in prompt_text
        assert "<name>agent-skill</name>" in prompt_text
        assert (
            "<description>Use the agent skill catalog entry.</description>"
            in prompt_text
        )
        assert "AgentSkills full instructions should not be sent." not in prompt_text

    def test_step_sends_triggered_skill_content_to_acp_server(self, tmp_path):
        agent = _make_agent(
            agent_context=AgentContext(
                skills=[
                    Skill(
                        name="legacy-review",
                        content="Legacy triggered review instructions.",
                        trigger=KeywordTrigger(keywords=["/review"]),
                    ),
                    Skill(
                        name="agentskill-review",
                        content="AgentSkills triggered review instructions.",
                        trigger=KeywordTrigger(keywords=["/review"]),
                        is_agentskills_format=True,
                        description="AgentSkills review catalog.",
                    ),
                ],
                current_datetime=None,
            )
        )
        state = _make_state(tmp_path)
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text="/review this PR.")],
                ),
                extended_content=[
                    TextContent(text="Legacy triggered review instructions."),
                    TextContent(text="AgentSkills triggered review instructions."),
                ],
            )
        )
        conversation = MagicMock()
        conversation.state = state
        self._wire_passthrough_mocks(agent)
        assert agent.agent_context is not None
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()
        agent._suffix_install_state = "pending_first_prompt"

        agent.step(conversation, on_event=lambda _: None)

        prompt_call = _agent_conn(agent).prompt.await_args
        assert prompt_call is not None
        assert prompt_call.kwargs["session_id"] == "test-session"
        prompt_text = "\n\n".join(
            b.text for b in prompt_call.kwargs["prompt"] if hasattr(b, "text")
        )
        assert "Legacy triggered review instructions." in prompt_text
        assert "AgentSkills triggered review instructions." in prompt_text
        assert "<name>agentskill-review</name>" in prompt_text
        assert "<description>AgentSkills review catalog.</description>" in prompt_text

    def test_step_does_not_re_inject_suffix_on_second_turn(self, tmp_path):
        """第一次注射后的后续回合中不得出现后缀。"""
        agent = _make_agent(
            agent_context=AgentContext(
                system_message_suffix="Team rules.", current_datetime=None
            )
        )
        state = _make_state(tmp_path)
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="Turn 2.")]),
            )
        )
        conversation = MagicMock()
        conversation.state = state
        self._wire_passthrough_mocks(agent)
        # 模拟：第一回合就已经安装了后缀。
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()  # type: ignore[union-attr]
        agent._suffix_install_state = "installed"

        agent.step(conversation, on_event=lambda _: None)

        prompt_call = _agent_conn(agent).prompt.await_args
        assert prompt_call is not None
        assert prompt_call.kwargs["session_id"] == "test-session"
        prompt_text = "\n\n".join(
            b.text for b in prompt_call.kwargs["prompt"] if hasattr(b, "text")
        )
        assert "Team rules." not in prompt_text

    def test_step_suffix_install_state_transitions_to_installed(self, tmp_path):
        """第一轮后安装状态必须为“已安装”AND
        ``acp_suffix_installed`` 标记必须位于已持久化中
        ``state.agent_state``，因此随后的智能体-服务器重新启动可以告诉后缀确实已安装
        （而不是仅根据 ``acp_session_id`` 的存
        在来推断）。
        """
        agent = _make_agent(
            agent_context=AgentContext(
                system_message_suffix="Team rules.", current_datetime=None
            )
        )
        state = _make_state(tmp_path)
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="First.")]),
            )
        )
        conversation = MagicMock()
        conversation.state = state
        self._wire_passthrough_mocks(agent)
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()  # type: ignore[union-attr]
        agent._suffix_install_state = "pending_first_prompt"

        agent.step(conversation, on_event=lambda _: None)

        assert agent._suffix_install_state == "installed"
        assert state.agent_state.get("acp_suffix_installed") is True

    def test_step_with_reasoning_surfaces_via_action_event(self, tmp_path):
        """推理痕迹保存在ActionEvent.reasoning_content中。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("4")
            mock_client.accumulated_thoughts.append("I need to add 2+2")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        assert isinstance(events[0], ActionEvent)
        assert isinstance(events[0].action, FinishAction)
        assert events[0].action.message == "4"
        assert events[0].reasoning_content == "I need to add 2+2"

    def test_step_sets_finished(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("done")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=lambda _: None)

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )

    def test_step_no_user_message_finishes(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        # 未添加用户留言

        conversation = MagicMock()
        conversation.state = state

        agent._client = _OpenHandsACPBridge()

        agent.step(conversation, on_event=lambda _: None)

        assert state.execution_status == ConversationExecutionStatus.FINISHED

    def test_step_error_sets_error_status(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        mock_executor = MagicMock()
        mock_executor.run_async = MagicMock(side_effect=RuntimeError("boom"))
        agent._executor = mock_executor

        with pytest.raises(RuntimeError, match="boom"):
            agent.step(conversation, on_event=events.append)

        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR
        assert len(events) >= 1
        content_block = events[0].llm_message.content[0]
        assert isinstance(content_block, TextContent)
        assert "ACP error: boom" in content_block.text

    def test_step_no_response_text_fallback(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        # accumulated_text 保持为空 — run_async 是无操作
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        mock_executor = MagicMock()
        mock_executor.run_async = lambda _coro, **_kwargs: None
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        assert isinstance(events[0], ActionEvent)
        assert isinstance(events[0].action, FinishAction)
        assert "(No response from ACP server)" in events[0].action.message

    def test_step_passes_on_token(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        # 在 prompt() 仍在运行时捕获 on_token — 一旦回合结束，step() 就会清除其finally
        # 块中的每回合回调。
        #
        wired_during_prompt: list = []

        def _fake_run_async(_coro, **_kwargs):
            wired_during_prompt.append(mock_client.on_token)
            mock_client.accumulated_text.append("ok")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        on_token = MagicMock()

        agent.step(conversation, on_event=lambda _: None, on_token=on_token)

        # 该桥与 StreamContext 的标记包装器连接，该包装器不变地转发到调用者的回调。
        #
        assert len(wired_during_prompt) == 1
        wired = wired_during_prompt[0]
        assert wired is not None and wired is not on_token
        wired("chunk")
        on_token.assert_called_once_with("chunk")
        # 之后未连线，因此迟到的 token 块是无操作的。
        assert mock_client.on_token is None

    def test_step_retires_its_stream_on_the_turn_finish_action(self, tmp_path):
        """ACP 回合的流文本落在 FinishAction 中，而不是消息。

        参见 https://github.com/OpenHands/software-agent-sdk/issues/4682.
        """
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        frames: list = []
        conversation.on_stream = frames.append

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.on_token("streamed ")
            mock_client.on_token("text")
            mock_client.accumulated_text.append("streamed text")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        events: list = []
        agent.step(conversation, on_event=events.append)

        started = [f for f in frames if isinstance(f, StreamStarted)]
        deltas = [f for f in frames if isinstance(f, StreamDelta)]
        assert len(started) == 1
        assert [d.content for d in deltas] == ["streamed ", "text"]

        action = next(e for e in events if isinstance(e, ActionEvent))
        assert action.id == started[0].item_id
        assert not any(isinstance(f, StreamAborted) for f in frames)
        # 上下文随回合释放。
        assert agent._stream is None

    @pytest.mark.asyncio
    async def test_astep_opens_and_retires_the_same_slot(self, tmp_path):
        """异步入口得到与同步相同的保证。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        frames: list = []
        conversation.on_stream = frames.append

        async def _fake_astep(_self, _conv, _on_event, on_token=None, _prompt=None):
            assert on_token is not None
            on_token("streamed text")
            raise RuntimeError("the prompt died after streaming")

        with patch.object(ACPAgent, "_astep", _fake_astep):
            with pytest.raises(RuntimeError):
                await agent.astep(conversation, on_event=lambda _: None)

        started = [f for f in frames if isinstance(f, StreamStarted)]
        aborted = [f for f in frames if isinstance(f, StreamAborted)]
        assert len(started) == len(aborted) == 1
        assert aborted[0].item_id == started[0].item_id
        assert aborted[0].reason == "RuntimeError"
        assert agent._stream is None


# ---------------------------------------------------------------------------
# 异步步骤 (astep) — 回归 #3348 的覆盖范围
# ---------------------------------------------------------------------------


class TestACPAgentAstep:
    """本机 ``ACPAgent.astep`` 不得回退到 ``AgentBase.astep``
    （将 ``step`` 包裹在 ``loop.run_in_executor`` 中）。 这样做会将后提示词回调和状态
    更新移动到执行器工作线程线程上，位于
    ``LocalConversation.arun`` 的受控事件序列化之外。 参见#3348。
    """

    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )
        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_astep_overrides_default_agentbase_implementation(self):
        """结构防护：如果翻转回来，``AgentBase.astep``的
        ``run_in_executor`` 包装器恢复并重新打开 #3348。
        """
        assert ACPAgent.astep is not AgentBase.astep

    def test_astep_runs_post_prompt_callbacks_on_caller_thread(self, tmp_path):
        """Post-提示词 ``on_event`` 回调必须对调用者触发
        线程。 如果 astep 在工作线程线程上调度 ``step``（有缺陷的默认值），回调和最终
        状态更新在异步运行任务的序列化模型之外运行 - 请参阅#334
        8。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        caller_thread_id = threading.get_ident()
        prompt_thread_id: list[int] = []
        on_event_thread_ids: list[int] = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        async def _fake_prompt(session_id, prompt):  # noqa: ARG001
            # 必须在入口循环的线程上执行，而不是调用者的 - 证明我们实际上跨越了循环边界
            # 。
            #
            prompt_thread_id.append(threading.get_ident())
            mock_client.accumulated_text.append("answer")
            return None

        _agent_conn(agent).prompt = _fake_prompt
        agent._session_id = "test-session"

        executor = AsyncExecutor()
        try:
            agent._executor = executor

            def _capture_event(event):
                on_event_thread_ids.append(threading.get_ident())

            asyncio.run(agent.astep(conversation, on_event=_capture_event))
        finally:
            executor.close()

        assert len(prompt_thread_id) == 1
        assert prompt_thread_id[0] != caller_thread_id

        # FinishAction + ObservationEvent — 均在呼叫者线程上。
        assert len(on_event_thread_ids) >= 2
        for tid in on_event_thread_ids:
            assert tid == caller_thread_id, (
                f"on_event ran on thread {tid} instead of caller "
                f"{caller_thread_id} — astep regressed to thread-pool path"
            )

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )

    def test_astep_restarts_session_off_caller_loop(self, tmp_path):
        """重启init可以同步解析loopbackLookupSecret值。

        ``astep`` 必须确保重启工作不在调用者循环中，这样智能体-服务器就可以用这些回环
         HTTP 请求代替等待每个机密查找超时。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"
        agent._restart_session_on_next_turn = True

        async def _fake_prompt(session_id, prompt):  # noqa: ARG001
            mock_client.accumulated_text.append("answer")
            return None

        _agent_conn(agent).prompt = _fake_prompt

        executor = AsyncExecutor()

        async def _run_restart() -> None:
            caller_loop = asyncio.get_running_loop()
            caller_thread_id = threading.get_ident()
            restart_entered = asyncio.Event()
            release_restart = threading.Event()
            restart_thread_ids: list[int] = []

            def _blocking_restart(self, state, on_event):  # noqa: ARG001
                assert self is agent
                restart_thread_ids.append(threading.get_ident())
                caller_loop.call_soon_threadsafe(restart_entered.set)
                assert release_restart.wait(5.0)
                agent._restart_session_on_next_turn = False

            with patch.object(
                ACPAgent,
                "_restart_session_after_drain_timeout",
                new=_blocking_restart,
            ):
                task = asyncio.create_task(
                    agent.astep(conversation, on_event=emitted.append)
                )
                await asyncio.wait_for(restart_entered.wait(), timeout=5.0)
                assert len(restart_thread_ids) == 1
                assert restart_thread_ids[0] != caller_thread_id
                release_restart.set()
                await asyncio.wait_for(task, timeout=5.0)

        try:
            agent._executor = executor
            asyncio.run(_run_restart())
        finally:
            executor.close()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert emitted

    def test_astep_active_prompt_survives_idle_window(self, tmp_path):
        """通过真正的门户进行端到端：一个主动的流式传输提示词
        正常运行超过 ``acp_prompt_timeout`` 结束。

        执行完整操作并发 model — the 提示词在空闲 watchdog 检查循环中运行，在 caller
        检查循环中运行，每个桥都运行
        ``session_update`` (越过循环边界时)重置了截止时间。 回归覆盖率智能体-canvas#
        1245.
        """
        from acp.schema import AgentMessageChunk, TextContentBlock

        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent(acp_prompt_timeout=0.3)
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        async def _fake_prompt(session_id, prompt):  # noqa: ARG001
            # 总计约 0.5 秒（> 0.3 秒空闲窗口），每 0.02 秒更新一次，因此截止时间不断重
            # 置； 然后完成转弯。
            #
            for _ in range(25):
                await asyncio.sleep(0.02)
                chunk = MagicMock(spec=AgentMessageChunk)
                chunk.content = MagicMock(spec=TextContentBlock)
                chunk.content.text = "tick"
                await mock_client.session_update(session_id, chunk)
            return None

        _agent_conn(agent).prompt = _fake_prompt

        executor = AsyncExecutor()
        try:
            agent._executor = executor
            asyncio.run(agent.astep(conversation, on_event=emitted.append))
        finally:
            executor.close()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert not any(
            isinstance(e, MessageEvent)
            and any(
                isinstance(c, TextContent) and "timed out" in c.text
                for c in e.llm_message.content
            )
            for e in emitted
        )

    def test_astep_emits_error_and_reraises_on_exception(self, tmp_path):
        """astep的错误路径必须调用``_emit_turn_error``AND重新引发。

        防备着被无声吞噬的``raise``
        ``except Exception`` 分支 — 无需重新加注，
        ``LocalConversation.arun()`` 不会转换出循环，并且失败对于
        ``RemoteConversation`` 来说是不可见的。 反映
        同步 ``step()`` 已经执行的合同。
        """
        from openhands.sdk.event.conversation_error import ConversationErrorEvent
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        async def _failing_prompt(session_id, prompt):  # noqa: ARG001
            raise RuntimeError("simulated upstream failure")

        _agent_conn(agent).prompt = _failing_prompt

        executor = AsyncExecutor()
        try:
            agent._executor = executor
            with pytest.raises(RuntimeError, match="simulated upstream failure"):
                asyncio.run(agent.astep(conversation, on_event=emitted.append))
        finally:
            executor.close()

        # _emit_turn_error 恰好发出两个事件：MessageEvent + 输入的
        # ConversationErrorEvent。 双方都必须在重新加注之前落地。
        #
        def _message_text(ev: MessageEvent) -> str:
            first = ev.llm_message.content[0]
            return first.text if isinstance(first, TextContent) else ""

        error_messages = [
            e
            for e in emitted
            if isinstance(e, MessageEvent) and "ACP error" in _message_text(e)
        ]
        typed_errors = [
            e
            for e in emitted
            if isinstance(e, ConversationErrorEvent) and e.code == "ACPPromptError"
        ]
        assert len(error_messages) == 1, (
            f"expected one error MessageEvent, got {emitted}"
        )
        assert len(typed_errors) == 1, (
            f"expected one ConversationErrorEvent, got {emitted}"
        )
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_astep_times_out_when_idle_with_inflight_tool_call(self, tmp_path):
        """当工具调用挂起且没有进一步更新时，空闲超时会触发。

        截止日期是一个停用状态超时一个被打开但随后不再产生进一步内容的工具卡片
        ``session_update`` (the) 提示词未来永远不会解决，没有什么流
        过，所以空闲窗口会消失， 译文：未来永远不会解决，没有什么流过。所以空闲窗口会
        消失超时路径必须取消  ACP 关闭流工具卡片并标记为失败。（正在进行的活动会
        重置时钟——请参阅
        ``TestACPPromptIdleTimeout``.)
        """
        from concurrent.futures import Future

        agent = _make_agent(acp_prompt_timeout=0.02)
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []
        cancel_called = threading.Event()

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        class _FakePortal:
            def __init__(self) -> None:
                self.prompt_future: Future = Future()

            def start_task_soon(self, fn, *args):  # noqa: ANN001, ANN202
                if args:
                    entry = {
                        "tool_call_id": "git-1",
                        "title": "git status",
                        "tool_kind": "execute",
                        "status": "in_progress",
                        "raw_input": None,
                        "raw_output": None,
                        "content": None,
                    }
                    mock_client.accumulated_tool_calls.append(entry)
                    mock_client._emit_tool_call_event(entry)
                    return self.prompt_future

                cancel_called.set()
                cancel_future: Future = Future()
                cancel_future.set_result(None)
                return cancel_future

        mock_executor = MagicMock()
        mock_executor.portal = _FakePortal()
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent._ACP_CANCEL_DRAIN_TIMEOUT", 0.01):
            asyncio.run(agent.astep(conversation, on_event=emitted.append))

        assert cancel_called.is_set()
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR
        assert any(
            isinstance(e, ACPToolCallEvent)
            and e.tool_call_id == "git-1"
            and e.status == "failed"
            and e.is_error
            for e in emitted
        )

        def _message_text(ev: MessageEvent) -> str:
            first = ev.llm_message.content[0]
            return first.text if isinstance(first, TextContent) else ""

        assert any(
            isinstance(e, MessageEvent)
            and "ACP prompt timed out after" in _message_text(e)
            for e in emitted
        )
        assert not any(
            isinstance(e, ActionEvent) and isinstance(e.action, FinishAction)
            for e in emitted
        )

    def test_astep_emits_failed_tool_calls_on_cancellation(self, tmp_path):
        """``asyncio.CancelledError`` 在步骤期间必须在飞行中关闭
        ``ACPToolCallEvent`` 变为 ``failed`` 并重新加注。

        ``asyncio.CancelledError`` 继承自 ``BaseException``（不是
        ``Exception``），因此通用 ``except Exception`` 处理程序不会捕获它 - 如果没有
        显式
        ``except asyncio.CancelledError`` 分支，取消会直接进入 ``finally``（仅清除回
        调）。 任何已流式传输的
        ``pending`` / ``in_progress`` 工具卡将永远保持有效（
        ``LocalConversation._emit_orphaned_action_errors`` 仅补丁
        ``ActionEvent``，而不是 ``ACPToolCallEvent``）。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        executor = AsyncExecutor()

        async def _run_with_cancel() -> None:
            prompt_entered = asyncio.Event()
            cancel_called = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                # 正在运行的种子工具调用之后 _reset_client_for_turn 已运行（这将清除
                # accumulated_tool_calls）。 在生产环境中，桥接器将这些信息累积到
                # session_update，当 ToolCallStart / ToolCallProgress 通知到达时。
                #
                mock_client.accumulated_tool_calls.append(
                    {
                        "tool_call_id": "tc-cancel-1",
                        "title": "in-flight tool",
                        "status": "in_progress",
                        "tool_kind": None,
                        "raw_input": None,
                        "raw_output": None,
                        "content": None,
                    }
                )
                # 我们将信号调用者循环保留在提示词内，因此取消可以确定地进行。
                #
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                # 阻止超出取消耗尽超时，因此此测试练习必须合成失败的 ACP 工具调用事件的
                # 非静默取消路径。
                #
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                return None

            async def _fake_cancel(session_id):
                assert session_id == "test-session"
                caller_loop.call_soon_threadsafe(cancel_called.set)

            _agent_conn(agent).prompt = _fake_prompt
            _agent_conn(agent).cancel = _fake_cancel
            agent._session_id = "test-session"

            task = asyncio.create_task(
                agent.astep(conversation, on_event=emitted.append)
            )
            await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
            task.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    with patch(
                        "openhands.sdk.agent.acp_agent._ACP_CANCEL_DRAIN_TIMEOUT",
                        0.01,
                    ):
                        await task
                await asyncio.wait_for(cancel_called.wait(), timeout=5.0)
            finally:
                prompt_released.set()

        try:
            agent._executor = executor
            asyncio.run(_run_with_cancel())
        finally:
            executor.close()

        failed_tool_events = [
            e
            for e in emitted
            if isinstance(e, ACPToolCallEvent)
            and e.tool_call_id == "tc-cancel-1"
            and e.status == "failed"
        ]
        assert len(failed_tool_events) == 1, (
            f"expected one terminal failed event for tc-cancel-1, "
            f"got: {[(type(e).__name__, getattr(e, 'status', None)) for e in emitted]}"
        )
        assert failed_tool_events[0].is_error is True

    def test_astep_finalizes_and_reraises_completed_cancelled_prompt(self, tmp_path):
        """如果取消的 ACP 提示词成功耗尽，则保留已完成的回合。

        ACP服务器可以在传送``session/cancel``的同时完成提示词。 在这种情况下，远程会
        话已经接受了助理的会话，所以OpenHands必须本地完成
        相同的会话，而不是丢弃响应并稍后从分叉的会话历史中恢复。 原始的取消仍然在对话
        层传播如此明确的用户停止意图。
        """
        from acp.schema import AgentMessageChunk, TextContentBlock

        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()
        _attach_file_credential_lifecycle(agent, tmp_path / "auth.json")

        executor = AsyncExecutor()

        async def _run_with_cancel() -> None:
            prompt_entered = asyncio.Event()
            cancel_called = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                await mock_client.session_update(
                    session_id,
                    AgentMessageChunk(
                        session_update="agent_message_chunk",
                        content=TextContentBlock(type="text", text="done"),
                    ),
                )
                return None

            async def _fake_cancel(session_id):
                assert session_id == "test-session"
                caller_loop.call_soon_threadsafe(cancel_called.set)
                prompt_released.set()

            _agent_conn(agent).prompt = _fake_prompt
            _agent_conn(agent).cancel = _fake_cancel
            agent._session_id = "test-session"

            with (
                patch.object(
                    ACPAgent,
                    "_sync_file_credentials",
                    autospec=True,
                    side_effect=lambda _agent: threading.Event().wait(0.05),
                ),
                # 必须超过0.05秒的延迟凭据-同步：在0.01秒时，加载的运行器的释放窗口在提
                # 示词完成之前就到期了，导致 `idle`。
                #
                patch.object(acp_agent_module, "_ACP_CANCEL_DRAIN_TIMEOUT", 5.0),
            ):
                task = asyncio.create_task(
                    agent.astep(conversation, on_event=emitted.append)
                )
                await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            await asyncio.wait_for(cancel_called.wait(), timeout=5.0)

        try:
            agent._executor = executor
            asyncio.run(_run_with_cancel())
        finally:
            executor.close()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert any(
            isinstance(e, ActionEvent)
            and isinstance(e.action, FinishAction)
            and e.action.message == "done"
            for e in emitted
        )
        assert agent._restart_session_on_next_turn is False

    def test_astep_cancelled_prompt_error_pauses_without_turn_error(self, tmp_path):
        """显式取消不应发出过时的提示词错误。"""
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        emitted: list = []

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        executor = AsyncExecutor()

        async def _run_with_cancel() -> None:
            prompt_entered = asyncio.Event()
            cancel_called = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                raise RuntimeError("late prompt failure")

            async def _fake_cancel(session_id):
                assert session_id == "test-session"
                caller_loop.call_soon_threadsafe(cancel_called.set)
                prompt_released.set()

            _agent_conn(agent).prompt = _fake_prompt
            _agent_conn(agent).cancel = _fake_cancel
            agent._session_id = "test-session"

            task = asyncio.create_task(
                agent.astep(conversation, on_event=emitted.append)
            )
            await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(cancel_called.wait(), timeout=5.0)

        try:
            agent._executor = executor
            asyncio.run(_run_with_cancel())
        finally:
            executor.close()

        assert not any(
            isinstance(e, MessageEvent)
            and e.source == "agent"
            and any(
                isinstance(c, TextContent) and c.text.startswith("ACP error:")
                for c in e.llm_message.content
            )
            for e in emitted
        )
        assert not any(isinstance(e, ConversationErrorEvent) for e in emitted)
        assert agent._restart_session_on_next_turn is True

    def test_astep_double_cancel_during_drain_restarts_next_turn(self, tmp_path):
        """排水期间的第二个取消应隔离活体提示词。"""
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        executor = AsyncExecutor()

        async def _run_with_double_cancel() -> None:
            prompt_entered = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                return None

            async def _fake_cancel(session_id):
                assert session_id == "test-session"

            async def _raise_during_drain(self, future):  # noqa: ARG001
                assert future is not None
                assert not future.done()
                raise asyncio.CancelledError

            _agent_conn(agent).prompt = _fake_prompt
            _agent_conn(agent).cancel = _fake_cancel
            agent._session_id = "test-session"

            with patch.object(
                ACPAgent,
                "_drain_cancelled_prompt",
                new=_raise_during_drain,
            ):
                task = asyncio.create_task(
                    agent.astep(conversation, on_event=lambda _: None)
                )
                await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
                task.cancel()
                try:
                    with pytest.raises(asyncio.CancelledError):
                        await task
                finally:
                    prompt_released.set()

        try:
            agent._executor = executor
            asyncio.run(_run_with_double_cancel())
        finally:
            executor.close()

        assert agent._restart_session_on_next_turn is True

    def test_astep_double_cancel_during_cancel_send_restarts_next_turn(self, tmp_path):
        """会话/取消期间的第二个取消应隔离提示词。"""
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        executor = AsyncExecutor()

        async def _run_with_cancelled_cancel_send() -> None:
            prompt_entered = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                return None

            async def _raise_during_cancel_send(self):  # noqa: ARG001
                raise asyncio.CancelledError

            _agent_conn(agent).prompt = _fake_prompt
            agent._session_id = "test-session"

            with patch.object(
                ACPAgent,
                "_arequest_session_cancel",
                new=_raise_during_cancel_send,
            ):
                task = asyncio.create_task(
                    agent.astep(conversation, on_event=lambda _: None)
                )
                await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
                task.cancel()
                try:
                    with pytest.raises(asyncio.CancelledError):
                        await task
                finally:
                    prompt_released.set()

        try:
            agent._executor = executor
            asyncio.run(_run_with_cancelled_cancel_send())
        finally:
            executor.close()

        assert agent._restart_session_on_next_turn is True

    def test_cleanup_interruption_finalizes_completed_prompt(self, tmp_path):
        """如果取消清理，则应完成已完成的提示词。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._session_id = "test-session"

        prompt_future: Future[PromptResponse | None] = Future()
        prompt_future.set_result(None)
        emitted = []

        with conversation.state as state:
            agent._handle_cancelled_cleanup_interruption(
                prompt_future,
                0.1,
                state,
                emitted.append,
            )

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert agent._restart_session_on_next_turn is False
        assert any(isinstance(event, ActionEvent) for event in emitted)

    def test_cleanup_interruption_emits_masking_error_before_propagating(
        self,
        tmp_path,
    ):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        client = _OpenHandsACPBridge()
        client.get_turn_usage_update = MagicMock(return_value=object())
        emitted = []
        client.on_event = emitted.append
        client._masking_error = ACPFileCredentialSyncError("credential tracking failed")
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": "tc-masking-1",
                "title": "in-flight tool",
                "status": "in_progress",
                "tool_kind": None,
                "raw_input": None,
                "raw_output": None,
                "content": None,
            }
        )
        agent._client = client
        agent._session_id = "test-session"
        prompt_future: Future[PromptResponse | None] = Future()
        prompt_future.set_result(None)

        with (
            conversation.state as state,
            pytest.raises(ACPFileCredentialSyncError, match="tracking failed"),
        ):
            agent._handle_cancelled_cleanup_interruption(
                prompt_future,
                0.1,
                state,
                emitted.append,
            )

        assert any(
            isinstance(event, ACPToolCallEvent)
            and event.tool_call_id == "tc-masking-1"
            and event.status == "failed"
            for event in emitted
        )
        assert any(isinstance(event, ConversationErrorEvent) for event in emitted)
        assert agent._restart_session_on_next_turn is True
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_astep_cancellation_does_not_mark_suffix_installed(self, tmp_path):
        """取消回合结束前必须离开
        ``_suffix_install_state`` 为 ``pending_first_prompt``。

        否则本地状态会说“已安装”，而 ACP 服务器从未收到后缀（取消在门户任务之前就持久
        化了），下一回合会跳过重新注入。 镜像
        ``_build_acp_prompt`` 合约，安装状态仅通过以下方式提交
        ``_finalize_successful_turn`` → ``_commit_suffix_installation``.
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent(
            agent_context=AgentContext(
                system_message_suffix="Team rules.", current_datetime=None
            )
        )
        conversation = self._make_conversation_with_message(tmp_path)
        agent._installed_suffix = agent.agent_context.to_acp_prompt_context()  # type: ignore[union-attr]
        agent._suffix_install_state = "pending_first_prompt"

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        executor = AsyncExecutor()

        async def _run_with_cancel() -> None:
            prompt_entered = asyncio.Event()
            prompt_released = threading.Event()
            caller_loop = asyncio.get_running_loop()

            async def _fake_prompt(session_id, prompt):  # noqa: ARG001
                caller_loop.call_soon_threadsafe(prompt_entered.set)
                released = await asyncio.to_thread(prompt_released.wait, 10.0)
                assert released
                return None

            async def _fake_cancel(session_id):
                assert session_id == "test-session"

            _agent_conn(agent).prompt = _fake_prompt
            _agent_conn(agent).cancel = _fake_cancel
            agent._session_id = "test-session"

            task = asyncio.create_task(
                agent.astep(conversation, on_event=lambda _: None)
            )
            await asyncio.wait_for(prompt_entered.wait(), timeout=5.0)
            task.cancel()
            try:
                with pytest.raises(asyncio.CancelledError):
                    with patch(
                        "openhands.sdk.agent.acp_agent._ACP_CANCEL_DRAIN_TIMEOUT",
                        0.01,
                    ):
                        await task
            finally:
                prompt_released.set()

        try:
            agent._executor = executor
            asyncio.run(_run_with_cancel())
        finally:
            executor.close()

        # 取消在 _finalize_successful_turn 运行之前命中，因此后缀安装状态必须保持待定状
        # 态 - 后续回合将重新注入后缀。
        #
        assert agent._suffix_install_state == "pending_first_prompt", (
            f"suffix install state was prematurely flipped to "
            f"{agent._suffix_install_state!r} — next turn would skip suffix"
        )
        # ``acp_suffix_installed`` 也不得被已持久化纳入
        # ``agent_state``：否则，在该取消的回合和下一个回合之间重新启动流程将读取标记并
        # 跳过重新注入（问题＃3359评论线程 7）。
        #
        assert conversation.state.agent_state.get("acp_suffix_installed") is not True, (
            "acp_suffix_installed was persisted despite cancellation — "
            "a process restart would skip suffix re-injection"
        )

    def test_astep_does_not_deadlock_under_reentrant_state_lock(self, tmp_path):
        """#3348 bug 的端到端形状。

        涵盖直接拨打者 ``state.lock`` 在循环中线程 across ``await astep(...)`` 在发布
        提示词回调重新获得它。 在重写步骤
        之后，的回调运行在同一个平台上线程 as the 锁 owner — FIFOLock's 可重入性通过
        它。 如果没有覆盖，这个就会挂起。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        state = conversation.state

        mock_client = _OpenHandsACPBridge()
        mock_client.get_turn_usage_update = MagicMock(return_value=object())
        agent._client = mock_client
        agent._conn = MagicMock()

        async def _fake_prompt(session_id, prompt):  # noqa: ARG001
            mock_client.accumulated_text.append("done")
            return None

        _agent_conn(agent).prompt = _fake_prompt
        agent._session_id = "test-session"

        executor = AsyncExecutor()
        try:
            agent._executor = executor

            # stats_callback形重入：简单取状态锁
            # from each event callback.  Same-thread reentry must succeed.
            def _capture_event(event):
                with state:
                    pass

            async def _arun_shaped() -> None:
                with state:
                    await asyncio.wait_for(
                        agent.astep(conversation, on_event=_capture_event),
                        timeout=10.0,
                    )

            asyncio.run(_arun_shaped())
        finally:
            executor.close()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )


# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------


def _own_finalize_calls(finalize_mock, agent) -> list:
    """由 *智能体* 本身调用 autospec'd ACPAgent._finalize。

    ``_finalize`` 必须在类中进行修补ACPAgent 是一个冻结的 Pydantic 模型，因此实例属性
    不能被替换，这意味着模拟对象也记录了来电 *其他*
      智能体。 无关的测试留下智能体 holding MagicMock 执行器/连接当其中之一被收集时，
    ``__del__`` 在其上调用 ``_finalize``，并使用一个普通的类补丁在运行中不可预测的点
    落在此模拟对象上。 ``autospec=True``记录
    ``self``，因此调用者只能计算自己的。
    """
    return [c for c in finalize_mock.call_args_list if c.args[:1] == (agent,)]


class TestACPAgentCleanup:
    def test_close_during_credential_materialization_discards_lifecycle(
        self, tmp_path, monkeypatch
    ):
        agent = _make_agent()
        state = _make_state(tmp_path)
        started = threading.Event()
        release = threading.Event()
        value = json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"refresh_token": "refresh-r0"},
            }
        )

        async def load():
            started.set()
            assert release.wait(2)
            return ResolvedCredential(value, "v0")

        binding = MagicMock(spec=["load", "replace"])
        binding.load = load
        binding.replace = AsyncMock(return_value="v1")
        agent.activate_file_credential_binding("CODEX_AUTH_JSON", binding)
        executor = MagicMock()
        executor.run_async.side_effect = asyncio.run
        agent._executor = executor
        runtime_dir = tmp_path / "runtime-auth"

        def make_runtime_dir(*, prefix):
            runtime_dir.mkdir()
            return str(runtime_dir)

        monkeypatch.setattr(
            acp_file_credentials_module.tempfile,
            "mkdtemp",
            make_runtime_dir,
        )
        env: dict[str, str] = {}
        errors: list[BaseException] = []

        def materialize() -> None:
            try:
                agent._materialise_file_secrets(state, env)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=materialize)
        thread.start()
        assert started.wait(1)
        agent.close()
        release.set()
        thread.join(timeout=2)

        assert not thread.is_alive()
        assert len(errors) == 1
        assert isinstance(errors[0], CredentialSyncError)
        assert str(errors[0]) == "Credential binding is closed."
        assert agent._file_credential_lifecycles == {}
        assert "CODEX_HOME" not in env
        assert not runtime_dir.exists()
        assert not any(
            thread.name == "codex-credential-monitor" and thread.is_alive()
            for thread in threading.enumerate()
        )

    def test_close_during_failed_legacy_unlink_discards_lifecycle(
        self, tmp_path, monkeypatch
    ):
        agent = _make_agent()
        state = _make_state(tmp_path)
        started = threading.Event()
        release = threading.Event()
        value = json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"refresh_token": "refresh-r0"},
            }
        )

        async def load():
            started.set()
            assert release.wait(2)
            return ResolvedCredential(value, "v0")

        binding = MagicMock(spec=["load", "replace"])
        binding.load = load
        binding.replace = AsyncMock(return_value="v1")
        agent.activate_file_credential_binding("CODEX_AUTH_JSON", binding)
        executor = MagicMock()
        executor.run_async.side_effect = asyncio.run
        agent._executor = executor
        runtime_dir = tmp_path / "runtime-auth"

        def make_runtime_dir(*, prefix):
            runtime_dir.mkdir()
            return str(runtime_dir)

        durable_dir = MagicMock()
        durable_path = durable_dir.__truediv__.return_value
        durable_path.unlink.side_effect = OSError("unlink failed")
        monkeypatch.setattr(
            acp_file_credentials_module.tempfile,
            "mkdtemp",
            make_runtime_dir,
        )
        monkeypatch.setattr(
            ACPAgent,
            "_acp_file_secret_dir",
            lambda *_args: durable_dir,
        )
        env: dict[str, str] = {}
        errors: list[BaseException] = []

        def materialize() -> None:
            try:
                agent._materialise_file_secrets(state, env)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=materialize)
        thread.start()
        assert started.wait(1)
        agent.close()
        release.set()
        thread.join(timeout=2)

        assert not thread.is_alive()
        assert len(errors) == 1
        assert isinstance(errors[0], CredentialSyncError)
        assert str(errors[0]) == "Durable credential copy could not be removed."
        assert agent._file_credential_lifecycles == {}
        assert "CODEX_HOME" not in env
        assert not runtime_dir.exists()
        binding.replace.assert_not_awaited()

    def test_failed_credential_materialization_can_retry(self, tmp_path):
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        durable_auth = agent._acp_file_secret_dir(state, "codex") / "auth.json"
        durable_auth.parent.mkdir(parents=True)
        durable_auth.write_text('{"legacy": true}', encoding="utf-8")
        valid = json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"refresh_token": "refresh-r0"},
            }
        )
        binding = MagicMock(spec=["load", "replace"])
        binding.load = AsyncMock(
            side_effect=[
                ResolvedCredential("{}", "v0"),
                ResolvedCredential(valid, "v1"),
            ]
        )
        binding.replace = AsyncMock(return_value="v2")
        agent.activate_file_credential_binding("CODEX_AUTH_JSON", binding)
        agent._executor = AsyncExecutor()

        with pytest.raises(ACPFileCredentialNeedsReauthError):
            agent._materialise_file_secrets(state, {})

        assert agent._file_credential_lifecycles == {}
        assert durable_auth.read_text(encoding="utf-8") == '{"legacy": true}'
        env: dict[str, str] = {}
        agent._materialise_file_secrets(state, env)
        assert Path(env["CODEX_HOME"], "auth.json").read_text() == valid
        assert not durable_auth.exists()
        agent.close()

    def test_failed_init_keeps_agent_reusable(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        binding = MagicMock(spec=["load", "replace"])
        agent.activate_file_credential_binding("CODEX_AUTH_JSON", binding)
        events: list = []

        with patch.object(
            ACPAgent,
            "_start_acp_server",
            side_effect=[RuntimeError("startup failed"), None],
        ):
            with pytest.raises(RuntimeError, match="startup failed"):
                agent.init_state(state, events.append)
            assert agent._closed is False
            assert agent._file_credential_bindings == {"CODEX_AUTH_JSON": binding}

            agent.init_state(state, events.append)

        assert agent._initialized is True
        agent.close()

    def test_close_terminates_process(self):
        agent = _make_agent()
        mock_process = MagicMock()
        agent._process = mock_process
        agent._executor = MagicMock()
        agent._conn = None

        agent.close()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_not_called()

    def test_close_is_idempotent(self):
        agent = _make_agent()
        mock_process = MagicMock()
        agent._process = mock_process
        agent._executor = MagicMock()
        agent._conn = None

        agent.close()
        agent.close()  # 第二次调用应该是空操作

        # 终止/终止只能调用一次
        mock_process.terminate.assert_called_once()

    def test_close_closes_executor(self):
        agent = _make_agent()
        mock_executor = MagicMock()
        agent._executor = mock_executor
        agent._process = None
        agent._conn = None

        agent.close()

        mock_executor.close.assert_called_once()

    def test_close_handles_errors_gracefully(self):
        agent = _make_agent()
        mock_process = MagicMock()
        mock_process.terminate.side_effect = OSError("already dead")
        mock_process.kill.side_effect = OSError("already dead")
        agent._process = mock_process
        agent._executor = MagicMock()
        agent._conn = None

        # 不应该提高
        agent.close()

    def test_failed_credential_close_can_be_retried(self):
        agent = _make_agent()
        lifecycle = MagicMock()
        lifecycle.close.side_effect = [CredentialSyncError("unavailable"), None]
        binding = MagicMock()
        executor = MagicMock()
        agent._file_credential_lifecycles["CODEX_AUTH_JSON"] = lifecycle
        agent._file_credential_bindings["CODEX_AUTH_JSON"] = binding
        agent._executor = executor

        with pytest.raises(CredentialSyncError, match="unavailable"):
            agent.close()

        assert agent._closed is True
        assert agent._file_credential_lifecycles == {"CODEX_AUTH_JSON": lifecycle}
        assert agent._file_credential_bindings == {"CODEX_AUTH_JSON": binding}
        executor.close.assert_not_called()

        agent.close()

        assert agent._file_credential_lifecycles == {}
        assert agent._file_credential_bindings == {}
        executor.close.assert_called_once_with()

    def test_kill_wait_is_bounded(self):
        agent = _make_agent()
        process = MagicMock()
        process.returncode = None
        process.terminate.side_effect = OSError("still running")
        executor = MagicMock()
        agent._process = process
        agent._executor = executor

        agent.close()

        process.kill.assert_called_once_with()
        executor.run_async.assert_called_once_with(
            agent._wait_for_process,
            process,
            timeout=5.0,
        )

    def test_finalizer_falls_back_when_thread_start_fails(self):
        agent = _make_agent()
        agent._executor = MagicMock()

        with (
            patch.object(threading.Thread, "start", side_effect=RuntimeError),
            patch.object(ACPAgent, "_finalize", autospec=True) as finalize,
        ):
            agent.__del__()

        assert _own_finalize_calls(finalize, agent) == [call(agent)]
        agent._executor = None

    def test_atexit_cleanup_is_weak_and_inline(self):
        agent = _make_agent()

        with (
            patch.object(acp_agent_module.atexit, "register") as register,
            patch.object(acp_agent_module.atexit, "unregister") as unregister,
            patch.object(ACPAgent, "_finalize", autospec=True) as finalize,
        ):
            agent._register_atexit_cleanup()
            callback = register.call_args.args[0]
            callback()
            agent._unregister_atexit_cleanup()

        assert _own_finalize_calls(finalize, agent) == [call(agent)]
        unregister.assert_called_once_with(callback)

    def test_atexit_callback_does_not_retain_agent(self):
        with patch.object(acp_agent_module.atexit, "register") as register:
            agent = _make_agent()
            agent._register_atexit_cleanup()
            callback = register.call_args.args[0]
            agent_ref = weakref.ref(agent)

            del agent
            gc.collect()

        assert agent_ref() is None
        assert callback() is None

    def test_turn_error_survives_credential_tracking_failure(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        client = _OpenHandsACPBridge()
        events: list = []
        client.on_event = events.append
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": "tc-1",
                "title": "Run",
                "status": "in_progress",
                "raw_input": None,
                "raw_output": None,
                "content": None,
            }
        )
        agent._client = client
        lifecycle = _attach_file_credential_lifecycle(agent, tmp_path / "auth.json")
        raw_rotated_token = "raw-rotated-token"
        lifecycle.track_current.side_effect = ACPFileCredentialSyncError(
            "credential tracking failed"
        )

        agent._emit_turn_error(
            RuntimeError(f"upstream returned {raw_rotated_token}"),
            state,
            events.append,
        )

        assert isinstance(events[0], ACPToolCallEvent)
        assert events[0].status == "failed"
        assert any(isinstance(event, MessageEvent) for event in events)
        assert any(isinstance(event, ConversationErrorEvent) for event in events)
        serialized = "\n".join(event.model_dump_json() for event in events)
        assert raw_rotated_token not in serialized
        assert "credential tracking failed" in serialized
        assert state.execution_status == ConversationExecutionStatus.ERROR
        agent.release_runtime()


# ---------------------------------------------------------------------------
# _filter_jsonrpc_lines
# ---------------------------------------------------------------------------


class TestFilterJsonrpcLines:
    @pytest.mark.asyncio
    async def test_passes_jsonrpc_lines(self):
        from openhands.sdk.agent.acp_agent import _filter_jsonrpc_lines

        source = asyncio.StreamReader()
        dest = asyncio.StreamReader()

        jsonrpc_line = b'{"jsonrpc":"2.0","method":"test"}\n'
        source.feed_data(jsonrpc_line)
        source.feed_eof()

        await _filter_jsonrpc_lines(source, dest)

        result = await dest.readline()
        assert result == jsonrpc_line

    @pytest.mark.asyncio
    async def test_filters_non_jsonrpc_lines(self):
        from openhands.sdk.agent.acp_agent import _filter_jsonrpc_lines

        source = asyncio.StreamReader()
        dest = asyncio.StreamReader()

        source.feed_data(b"[ACP] Starting server...\n")
        source.feed_data(b'{"jsonrpc":"2.0","id":1}\n')
        source.feed_data(b"Some debug output\n")
        source.feed_eof()

        await _filter_jsonrpc_lines(source, dest)

        result = await dest.readline()
        assert b'"jsonrpc"' in result

        # 应该获取 EOF 下一个（过滤掉了非 JSON 行）
        result2 = await dest.readline()
        assert result2 == b""

    @pytest.mark.asyncio
    async def test_logs_non_jsonrpc_stdout(self, caplog):
        source = asyncio.StreamReader()
        dest = asyncio.StreamReader()
        source.feed_data(b"codex-acp startup detail\n")
        source.feed_eof()

        with caplog.at_level("INFO"):
            await acp_agent_module._filter_jsonrpc_lines(source, dest)

        assert "ACP stdout (non-JSON): codex-acp startup detail" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_subprocess_stderr(self, caplog):
        source = asyncio.StreamReader()
        source.feed_data(b"codex-acp diagnostic\n")
        source.feed_eof()

        with caplog.at_level("INFO"):
            await _log_acp_subprocess_stderr(source)

        assert "ACP stderr: codex-acp diagnostic" in caplog.text

    def test_shutdown_cancels_stdout_and_stderr_drain_tasks(self):
        """stdout-filter 和 stderr-log 任务未在任何地方引用
        else once started; _shutdown_runtime must cancel and clear them so
        没有任何东西会无限期地耗尽关闭的子进程的管道。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        agent._executor = AsyncExecutor()

        async def _never_ending():
            await asyncio.sleep(3600)

        async def _spawn_task():
            # 镜像 _init() 如何安排真正的排出任务：通过 asyncio.get_event_loop().
            # create_task() 从已经在执行器的门户循环上运行的协程内部。
            #
            return asyncio.get_event_loop().create_task(_never_ending())

        stdout_task = agent._executor.run_async(_spawn_task)
        stderr_task = agent._executor.run_async(_spawn_task)
        agent._stdout_filter_task = stdout_task
        agent._stderr_log_task = stderr_task

        agent._shutdown_runtime(discard_bindings=True)

        assert agent._stdout_filter_task is None
        assert agent._stderr_log_task is None
        assert stdout_task.cancelled()
        assert stderr_task.cancelled()

    @pytest.mark.asyncio
    async def test_filters_pretty_printed_json(self):
        from openhands.sdk.agent.acp_agent import _filter_jsonrpc_lines

        source = asyncio.StreamReader()
        dest = asyncio.StreamReader()

        # 漂亮打印的 JSON 以 { 开头，但不包含“jsonrpc”
        source.feed_data(b"{\n")
        source.feed_data(b'  "type": "message"\n')
        source.feed_data(b"}\n")
        source.feed_eof()

        await _filter_jsonrpc_lines(source, dest)

        # 应该只得到EOF
        result = await dest.readline()
        assert result == b""


# ---------------------------------------------------------------------------
# 遥测
# ---------------------------------------------------------------------------


class TestACPAgentTelemetry:
    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        """使用用户消息创建模拟对象对话。"""
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )

        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_get_all_llms_yields_sentinel(self):
        """get_all_llms() 产生用于遥测的哨兵值 LLM。"""
        agent = _make_agent()
        llms = list(agent.get_all_llms())
        assert len(llms) == 1
        assert llms[0] is agent.llm
        assert llms[0].model == "acp-managed"

    def _make_step_fixtures(self, tmp_path, agent=None, usage=None, cost=None):
        """为 step() 遥测测试设置智能体 + 客户端 + 执行器。"""
        if agent is None:
            agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = agent._client or _OpenHandsACPBridge()
        mock_client._context_window = 200000
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        mock_response = MagicMock()
        if usage is not None:
            mock_usage = MagicMock()
            mock_usage.input_tokens = usage.get("input", 0)
            mock_usage.output_tokens = usage.get("output", 0)
            mock_usage.cached_read_tokens = usage.get("cache_read", 0)
            mock_usage.cached_write_tokens = usage.get("cache_write", 0)
            mock_usage.thought_tokens = usage.get("thought", 0)
            mock_response.usage = mock_usage
        else:
            mock_response.usage = None
            mock_response.field_meta = None

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("response text")
            if cost is not None:
                mock_update = MagicMock()
                mock_update.cost = MagicMock()
                mock_update.cost.amount = cost[0]
                mock_update.size = cost[1]
                mock_client._turn_usage_updates["test-session"] = mock_update
                mock_client._context_window_by_session["test-session"] = cost[1]
                mock_client._context_window = cost[1]
            return mock_response

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        return agent, conversation

    def test_step_records_token_usage(self, tmp_path):
        """step() 从 PromptResponse.usage 记录每回合词元用量。"""
        agent, conversation = self._make_step_fixtures(
            tmp_path,
            usage={
                "input": 100,
                "output": 50,
                "cache_read": 10,
                "cache_write": 5,
                "thought": 20,
            },
            cost=(0.05, 200000),
        )

        agent.step(conversation, on_event=lambda _: None)

        metrics = agent.llm.metrics
        assert len(metrics.token_usages) == 1
        usage = metrics.token_usages[0]
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.cache_read_tokens == 10
        assert usage.cache_write_tokens == 5
        assert usage.reasoning_tokens == 20
        assert usage.context_window == 200000

    def test_step_handles_no_usage(self, tmp_path):
        """step() 优雅地处理没有使用的 PromptResponse。"""
        agent, conversation = self._make_step_fixtures(tmp_path)

        agent.step(conversation, on_event=lambda _: None)

        assert len(agent.llm.metrics.token_usages) == 0

    def test_step_records_cost_from_usage_update(self, tmp_path):
        """step() 记录单个遥测路径中 UsageUpdate 的成本。"""
        agent, conversation = self._make_step_fixtures(
            tmp_path,
            usage={"input": 100, "output": 50},
            cost=(0.05, 128000),
        )

        agent.step(conversation, on_event=lambda _: None)

        assert agent.llm.metrics.accumulated_cost == pytest.approx(0.05)
        assert len(agent.llm.metrics.costs) == 1
        assert agent._client._last_cost == pytest.approx(0.05)

    def test_step_records_incremental_cost(self, tmp_path):
        """成本跟踪是跨回合递增的。"""
        agent = _make_agent()

        _, conversation1 = self._make_step_fixtures(
            tmp_path,
            agent=agent,
            usage={"input": 100, "output": 50},
            cost=(0.05, 128000),
        )
        agent.step(conversation1, on_event=lambda _: None)
        assert agent.llm.metrics.accumulated_cost == pytest.approx(0.05)

        _, conversation2 = self._make_step_fixtures(
            tmp_path,
            agent=agent,
            usage={"input": 200, "output": 100},
            cost=(0.12, 130000),
        )
        agent.step(conversation2, on_event=lambda _: None)
        assert agent.llm.metrics.accumulated_cost == pytest.approx(0.12)
        assert len(agent.llm.metrics.costs) == 2

    def test_step_no_cost_when_usage_update_missing(self, tmp_path):
        """当 PromptResponse 到达但没有 UsageUpdate 时，不记录任何成本。"""
        agent, conversation = self._make_step_fixtures(
            tmp_path,
            usage={"input": 100, "output": 50},
            cost=None,
        )

        agent.step(conversation, on_event=lambda _: None)

        assert agent.llm.metrics.accumulated_cost == 0.0
        assert len(agent.llm.metrics.costs) == 0
        assert len(agent.llm.metrics.token_usages) == 1

    def test_step_records_partial_metrics_on_usage_timeout(self, tmp_path, caplog):
        """超时等待 UsageUpdate 记录警告，但记录 token 指标。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        # 一个持有者-机密-看起来的id，所以下面的日志卫生断言是
        # 有意义：超时警告必须将其指纹识别为 ``...<last-8>``，
        # 永远不要发出完整的 ID。
        agent._session_id = "sk-resume-secret-DEADBEEF"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cached_read_tokens = 0
        mock_usage.cached_write_tokens = 0
        mock_usage.thought_tokens = 0

        mock_response = MagicMock()
        mock_response.usage = mock_usage

        async def _fake_prompt(*_args, **_kwargs):
            return mock_response

        def _run_async(coro_fn, **_kwargs):
            loop = asyncio.new_event_loop()
            try:
                _agent_conn(agent).prompt = _fake_prompt
                return loop.run_until_complete(coro_fn())
            finally:
                loop.close()

        mock_executor = MagicMock()
        mock_executor.run_async = _run_async
        agent._executor = mock_executor

        async def _raise_timeout(awaitable, timeout):
            awaitable.close()
            raise TimeoutError

        with patch(
            "openhands.sdk.agent.acp_agent.asyncio.wait_for",
            new=AsyncMock(side_effect=_raise_timeout),
        ):
            agent.step(conversation, on_event=lambda _: None)

        assert "UsageUpdate not received within 2.0s" in caplog.text
        # 在超时警告中，承载会话 ID 已被指纹识别，并未泄露。
        assert "sk-resume-secret-DEADBEEF" not in caplog.text
        assert "...DEADBEEF" in caplog.text
        assert len(agent.llm.metrics.token_usages) == 1
        assert len(agent.llm.metrics.costs) == 0
        assert agent.llm.metrics.accumulated_cost == 0.0

    def test_step_records_latency(self, tmp_path):
        """step() 记录单个遥测路径中的响应延迟。"""
        agent, conversation = self._make_step_fixtures(tmp_path)

        agent.step(conversation, on_event=lambda _: None)

        assert len(agent.llm.metrics.response_latencies) == 1
        assert agent.llm.metrics.response_latencies[0].latency >= 0.0

    @pytest.mark.asyncio
    async def test_session_update_stores_usage_update(self):
        """session_update() 存储 UsageUpdate 供 step() 稍后处理。"""
        from acp.schema import UsageUpdate

        client = _OpenHandsACPBridge()
        usage_event = client.prepare_usage_sync("sess-1")

        update = MagicMock(spec=UsageUpdate)
        update.size = 128000
        update.cost = MagicMock()
        update.cost.amount = 0.05

        await client.session_update("sess-1", update)

        assert client.get_turn_usage_update("sess-1") is update
        assert client._context_window == 128000
        assert client._context_window_by_session["sess-1"] == 128000
        assert usage_event.is_set()

    @pytest.mark.asyncio
    async def test_usage_update_updates_context_window(self):
        """UsageUpdate.size 更新客户端的 _context_window。"""
        from acp.schema import UsageUpdate

        client = _OpenHandsACPBridge()

        update = MagicMock(spec=UsageUpdate)
        update.size = 200000
        update.cost = None

        await client.session_update("sess-1", update)

        assert client._context_window == 200000
        assert client._context_window_by_session["sess-1"] == 200000

    def test_stats_callback_invoked(self, tmp_path):
        """step() 之后，哨兵值 LLM 的统计信息回调被调用。"""
        agent, conversation = self._make_step_fixtures(tmp_path)

        callback = MagicMock()
        agent.llm.telemetry._stats_update_callback = callback

        agent.step(conversation, on_event=lambda _: None)

        callback.assert_called_once()

    def test_init_state_sets_bridge_client(self, tmp_path):
        """init_state() 保留 _start_acp_server 安装的网桥实例。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        expected_client = _OpenHandsACPBridge()

        with patch(
            "openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"
        ) as mock_start:

            def fake_start(_state):
                agent._client = expected_client

            mock_start.side_effect = fake_start
            agent.init_state(state, on_event=lambda _: None)

        assert agent._client is expected_client

    def test_reset_preserves_telemetry_state(self):
        """reset() 清除每轮缓冲区，但保留累积遥测数据。"""
        client = _OpenHandsACPBridge()
        client._last_cost = 1.23
        client._last_cost_by_session["sess-1"] = 1.23
        client._context_window = 128000
        client._context_window_by_session["sess-1"] = 128000
        client._turn_usage_updates["sess-1"] = MagicMock()
        client._usage_received["sess-1"] = asyncio.Event()
        client.accumulated_text.append("hello")
        client.accumulated_thoughts.append("thinking")

        client.reset()

        assert client.accumulated_text == []
        assert client.accumulated_thoughts == []
        assert client._last_cost == 1.23
        assert client._context_window == 128000
        assert client._last_cost_by_session["sess-1"] == 1.23
        assert client._context_window_by_session["sess-1"] == 128000
        assert client._turn_usage_updates == {}
        assert client._usage_received == {}


# ---------------------------------------------------------------------------
# 工具调用积累与排放
# ---------------------------------------------------------------------------


class TestACPToolCallAccumulation:
    """测试桥中的 ToolCallStart/ToolCallProgress 累积情况。"""

    @pytest.mark.asyncio
    async def test_session_update_accumulates_tool_call_start(self):
        """ToolCallStart 在 accumulated_tool_calls 中创建一个条目。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read file"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = {"path": "/tmp/test.py"}
        start.raw_output = None
        start.content = None

        await client.session_update("sess-1", start)

        assert len(client.accumulated_tool_calls) == 1
        tc = client.accumulated_tool_calls[0]
        assert tc["tool_call_id"] == "tc-1"
        assert tc["title"] == "Read file"
        assert tc["tool_kind"] == "read"
        assert tc["status"] == "in_progress"
        assert tc["raw_input"] == {"path": "/tmp/test.py"}
        assert tc["raw_output"] is None
        assert tc["content"] is None

    @pytest.mark.asyncio
    async def test_session_update_merges_tool_call_progress(self):
        """ToolCallProgress 将更新合并到现有的工具调用条目中。"""
        from acp.schema import ToolCallProgress, ToolCallStart

        client = _OpenHandsACPBridge()

        # 开始
        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-2"
        start.title = "Execute command"
        start.kind = "execute"
        start.status = "in_progress"
        start.raw_input = {"command": "ls"}
        start.raw_output = None
        start.content = None

        await client.session_update("sess-1", start)

        # 进展
        progress = MagicMock(spec=ToolCallProgress)
        progress.tool_call_id = "tc-2"
        progress.title = None  # 未更新
        progress.kind = None  # 未更新
        progress.status = "completed"
        progress.raw_input = None  # 未更新
        progress.raw_output = "file1.py\nfile2.py"
        progress.content = None

        await client.session_update("sess-1", progress)

        assert len(client.accumulated_tool_calls) == 1
        tc = client.accumulated_tool_calls[0]
        assert tc["title"] == "Execute command"  # 不变
        assert tc["tool_kind"] == "execute"  # 不变
        assert tc["status"] == "completed"  # 已更新
        assert tc["raw_output"] == "file1.py\nfile2.py"  # 已更新

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_accumulated(self):
        """多个 ToolCallStart 事件创建单独的条目。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()

        for i in range(3):
            start = MagicMock(spec=ToolCallStart)
            start.tool_call_id = f"tc-{i}"
            start.title = f"Tool {i}"
            start.kind = "read"
            start.status = "completed"
            start.raw_input = None
            start.raw_output = None
            start.content = None
            await client.session_update("sess-1", start)

        assert len(client.accumulated_tool_calls) == 3
        assert [tc["tool_call_id"] for tc in client.accumulated_tool_calls] == [
            "tc-0",
            "tc-1",
            "tc-2",
        ]

    def test_reset_clears_accumulated_tool_calls(self):
        """reset() 清除 accumulated_tool_calls。"""
        client = _OpenHandsACPBridge()
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": "tc-1",
                "title": "Read file",
                "tool_kind": "read",
                "status": "completed",
                "raw_input": None,
                "raw_output": None,
            }
        )

        client.reset()

        assert client.accumulated_tool_calls == []


class TestACPToolCallLiveEmission:
    """测试 ``session_update`` 实时触发 ``on_event``（未批量）。

    关闭 OpenHands/software-智能体-SDK#2866: 工具调用事件必须到达
    ``on_event`` 随着每个 ACP 通知到达，因此事件流反映真实的子进程进度，而不是单个回
    合结束突发。
    """

    @pytest.mark.asyncio
    async def test_session_update_fires_on_event_live(self):
        """每个 ToolCallStart/Progress 都会立即触发 on_event 调用。"""
        from acp.schema import ToolCallProgress, ToolCallStart

        client = _OpenHandsACPBridge()
        events: list = []
        client.on_event = events.append

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read file"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = {"path": "/a"}
        start.raw_output = None
        start.content = None
        await client.session_update("sess", start)

        # on_event 同步触发 - 事件已存在，未批量处理。
        assert len(events) == 1
        assert isinstance(events[0], ACPToolCallEvent)
        assert events[0].tool_call_id == "tc-1"
        assert events[0].status == "in_progress"
        assert events[0].raw_output is None

        progress = MagicMock(spec=ToolCallProgress)
        progress.tool_call_id = "tc-1"
        progress.title = None
        progress.kind = None
        progress.status = "completed"
        progress.raw_input = None
        progress.raw_output = "hello"
        progress.content = None
        await client.session_update("sess", progress)

        # 相同的 tool_call_id，不断变化的状态/raw_output — 消费者重复数据删除。
        assert len(events) == 2
        assert events[1].tool_call_id == "tc-1"
        assert events[1].status == "completed"
        assert events[1].raw_output == "hello"
        assert events[1].is_error is False

    @pytest.mark.asyncio
    async def test_session_update_preserves_interleaved_order(self):
        """工具调用和文本块更新按到达顺序到达回调。

        桥发出 on_event 同步地 session_update因此，消费者看到的订单与的订单完全一致
        ACP  子进程他们被发送了。 文本/想法块被路由到
        on_token rather than on_event，但是…… *combined*  回调流必须保持到达顺序，以
        便消费者可以重建一个连贯的跟踪。
        """
        from acp.schema import (
            AgentMessageChunk,
            AgentThoughtChunk,
            TextContentBlock,
            ToolCallProgress,
            ToolCallStart,
        )

        client = _OpenHandsACPBridge()
        # 回调个到达者的单一时间线，按来源标记。
        observed: list[tuple[str, Any]] = []
        client.on_event = lambda e: observed.append(("event", e))
        client.on_token = lambda t: observed.append(("token", t))

        def make_start(tc_id: str) -> Any:
            s = MagicMock(spec=ToolCallStart)
            s.tool_call_id = tc_id
            s.title = f"Tool {tc_id}"
            s.kind = "read"
            s.status = "in_progress"
            s.raw_input = None
            s.raw_output = None
            s.content = None
            return s

        def make_progress(tc_id: str, status: str) -> Any:
            p = MagicMock(spec=ToolCallProgress)
            p.tool_call_id = tc_id
            p.title = None
            p.kind = None
            p.status = status
            p.raw_input = None
            p.raw_output = None
            p.content = None
            return p

        def make_text_chunk(text: str) -> Any:
            c = MagicMock(spec=AgentMessageChunk)
            c.content = MagicMock(spec=TextContentBlock)
            c.content.text = text
            return c

        def make_thought_chunk(text: str) -> Any:
            c = MagicMock(spec=AgentThoughtChunk)
            c.content = MagicMock(spec=TextContentBlock)
            c.content.text = text
            return c

        sequence: list = [
            make_thought_chunk("thinking..."),
            make_start("tc-a"),
            make_text_chunk("reading "),
            make_progress("tc-a", "completed"),
            make_start("tc-b"),
            make_text_chunk("done"),
            make_progress("tc-b", "completed"),
        ]
        for update in sequence:
            await client.session_update("sess", update)

        # 思想块今天不会触发回调 - 过滤到我们驱动的回调类型并确认到达顺序与驱动序列匹配
        # 。
        #
        expected_stream = [
            "event",  # tc-a 开始
            "token",  # 文本块
            "event",  # TC-a 进展
            "event",  # tc-b 开始
            "token",  # 文本块
            "event",  # tc-b 进展
        ]
        assert [kind for kind, _ in observed] == expected_stream
        tool_events = [payload for kind, payload in observed if kind == "event"]
        assert [e.tool_call_id for e in tool_events] == [
            "tc-a",
            "tc-a",
            "tc-b",
            "tc-b",
        ]
        assert [e.status for e in tool_events] == [
            "in_progress",
            "completed",
            "in_progress",
            "completed",
        ]

    @pytest.mark.asyncio
    async def test_session_update_no_on_event_when_unset(self):
        """当 on_event 为 None（无活动步骤）时，session_update 为无操作发射。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        assert client.on_event is None

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None

        # 不得提高
        await client.session_update("sess", start)
        # 仍在积累，因此 step() 可以在需要时引用它。
        assert len(client.accumulated_tool_calls) == 1

    @pytest.mark.asyncio
    async def test_on_event_errors_are_swallowed(self):
        """提升 on_event 不得破坏 session_update 管道。"""
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        client.on_event = MagicMock(side_effect=RuntimeError("boom"))

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Read"
        start.kind = "read"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None

        await client.session_update("sess", start)  # 不得提高
        client.on_event.assert_called_once()

    def test_reset_clears_on_event(self):
        """reset() 清除 on_event，因此下一步会连接新的回调。"""
        client = _OpenHandsACPBridge()
        client.on_event = lambda _: None
        client.reset()
        assert client.on_event is None


class TestACPCancelInflightToolCalls:
    """测试 _cancel_inflight_tool_calls — 确保幽灵工具卡
    在重试上关闭/中止，因此实时发射流不能在 ``state.events`` 上留下孤立的待处理事件。

    在 PR 评论中，ACP 服务器在提示词重试时会重新生成 ``tool_call_id``，因此，对于失败
    尝试中已经触发的任何待处理事件，否则在 dedup-by-
    id 消费者中会无限期地循环。
    """

    @staticmethod
    def _push_entry(
        client: _OpenHandsACPBridge, tool_call_id: str, status: str
    ) -> None:
        client.accumulated_tool_calls.append(
            {
                "tool_call_id": tool_call_id,
                "title": f"Tool {tool_call_id}",
                "tool_kind": "read",
                "status": status,
                "raw_input": {"k": "v"},
                "raw_output": None,
                "content": None,
            }
        )

    def test_emits_failed_event_for_pending_entries(self, tmp_path):
        """待办/ in_progress 获取条目失败 ACPToolCallEvent."""
        agent = _make_agent()
        agent._client = _OpenHandsACPBridge()
        emitted: list = []
        agent._client.on_event = emitted.append
        self._push_entry(agent._client, "tc-1", "pending")
        self._push_entry(agent._client, "tc-2", "in_progress")

        agent._cancel_inflight_tool_calls()

        assert len(emitted) == 2
        assert all(isinstance(e, ACPToolCallEvent) for e in emitted)
        assert [e.tool_call_id for e in emitted] == ["tc-1", "tc-2"]
        assert all(e.status == "failed" and e.is_error for e in emitted)

    def test_skips_already_terminal_entries(self, tmp_path):
        """已完成/失败的条目将被保留 - 它们已经关闭。"""
        agent = _make_agent()
        agent._client = _OpenHandsACPBridge()
        emitted: list = []
        agent._client.on_event = emitted.append
        self._push_entry(agent._client, "tc-done", "completed")
        self._push_entry(agent._client, "tc-bad", "failed")
        self._push_entry(agent._client, "tc-live", "pending")

        agent._cancel_inflight_tool_calls()

        # 只有待处理的事件才会获得合成终端事件。
        assert [e.tool_call_id for e in emitted] == ["tc-live"]

    def test_callback_errors_are_swallowed(self):
        """在取消期间加注 on_event 不得破坏重试路径。"""
        agent = _make_agent()
        agent._client = _OpenHandsACPBridge()
        self._push_entry(agent._client, "tc-1", "pending")
        self._push_entry(agent._client, "tc-2", "pending")

        seen: list = []

        def flaky(event) -> None:
            seen.append(event)
            raise RuntimeError("boom")

        agent._client.on_event = flaky
        agent._cancel_inflight_tool_calls()  # 不得提高
        # 尽管第一个条目提出了，但两个条目仍然尝试。
        assert len(seen) == 2

    def test_noop_when_on_event_unset(self):
        """如果没有连接 on_event，取消则不执行任何操作。"""
        agent = _make_agent()
        agent._client = _OpenHandsACPBridge()
        self._push_entry(agent._client, "tc-1", "pending")

        # on_event 默认为 None — 不得引发，不得迭代
        assert agent._client.on_event is None
        agent._cancel_inflight_tool_calls()

    def test_retry_cancels_pending_events_before_reset(self, tmp_path):
        """完整的 step() 重试路径会在新尝试之前关闭待处理的卡。"""
        from acp.schema import ToolCallStart

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="sys"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="go")]),
            )
        )
        conversation = MagicMock()
        conversation.state = state

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        events: list = []
        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次尝试：流式传输待处理的工具调用，然后失败
                start = MagicMock(spec=ToolCallStart)
                start.tool_call_id = "toolu_AAA"
                start.title = "Read file"
                start.kind = "read"
                start.status = "pending"
                start.raw_input = {"path": "/tmp/x"}
                start.raw_output = None
                start.content = None
                asyncio.run(mock_client.session_update("sess", start))
                raise ConnectionError("reset by peer")
            # 重试：新的工具调用 id 达到最终状态
            start = MagicMock(spec=ToolCallStart)
            start.tool_call_id = "toolu_BBB"
            start.title = "Read file"
            start.kind = "read"
            start.status = "completed"
            start.raw_input = {"path": "/tmp/x"}
            start.raw_output = "ok"
            start.content = None
            asyncio.run(mock_client.session_update("sess", start))
            mock_client.accumulated_text.append("done")
            return MagicMock(usage=None)

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent.time.sleep"):
            agent.step(conversation, on_event=events.append)

        assert call_count == 2
        tool_events = [e for e in events if isinstance(e, ACPToolCallEvent)]
        # 预期顺序：
        # toolu_AAA（待定）— 尝试 1 期间实时发射 toolu_AAA（失败）— 在重试重置之前合成取
        # 消 toolu_BBB（已完成）— 尝试 2
        #
        by_id: dict[str, list[ACPToolCallEvent]] = {}
        for e in tool_events:
            by_id.setdefault(e.tool_call_id, []).append(e)

        assert "toolu_AAA" in by_id
        aaa_events = by_id["toolu_AAA"]
        # 必须以终端状态结束，以便消费者按 ID 重复数据删除关闭卡。
        assert aaa_events[-1].status == "failed"
        assert aaa_events[-1].is_error is True

        assert "toolu_BBB" in by_id
        assert by_id["toolu_BBB"][-1].status == "completed"

        # toolu_AAA 取消出现在任何 toolu_BBB 事件之前。
        aaa_idx = max(
            i for i, e in enumerate(tool_events) if e.tool_call_id == "toolu_AAA"
        )
        bbb_idx = min(
            i for i, e in enumerate(tool_events) if e.tool_call_id == "toolu_BBB"
        )
        assert aaa_idx < bbb_idx


class TestACPToolCallEmission:
    """测试 for ACPToolCallEvent 排放 step()."""

    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        """使用用户消息创建模拟对象对话。"""
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )

        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_step_emits_tool_call_events_before_message(self, tmp_path):
        """工具调用事件先于 MessageEvent 实时到达 on_event。"""
        from acp.schema import ToolCallStart

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            # 在 prompt() 期间模拟 ACP 子进程流式传输两个工具调用通知。 session_update
            # 同步触发 on_event，因此这些事件在 run_async 返回之前出现。
            #
            for tool_call_id, title, kind, status, raw_input, raw_output in [
                (
                    "tc-1",
                    "Read file",
                    "read",
                    "completed",
                    {"path": "/tmp/f.py"},
                    "content",
                ),
                ("tc-2", "Execute bash", "execute", "failed", {"command": "ls"}, None),
            ]:
                start = MagicMock(spec=ToolCallStart)
                start.tool_call_id = tool_call_id
                start.title = title
                start.kind = kind
                start.status = status
                start.raw_input = raw_input
                start.raw_output = raw_output
                start.content = None
                asyncio.run(mock_client.session_update("sess", start))
            mock_client.accumulated_text.append("done")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        # 应该是：2 工具调用个事件（实时）+ 完成动作 + 完成观测结果
        assert len(events) == 4
        assert isinstance(events[0], ACPToolCallEvent)
        assert isinstance(events[1], ACPToolCallEvent)
        assert isinstance(events[2], ActionEvent)

        # 验证第一个工具调用事件
        assert events[0].tool_call_id == "tc-1"
        assert events[0].title == "Read file"
        assert events[0].tool_kind == "read"
        assert events[0].status == "completed"
        assert events[0].raw_input == {"path": "/tmp/f.py"}
        assert events[0].raw_output == "content"
        assert events[0].is_error is False

        # 验证第二个工具调用事件（失败）
        assert events[1].tool_call_id == "tc-2"
        assert events[1].is_error is True

    def test_step_clears_live_callbacks_on_return(self, tmp_path):
        """step() 返回后，桥回调被断开。

        逗号 ``session_update`` 在转弯之间 ACP  子进程发送晚的 ``ToolCallProgress``
        在它的提示词 response)
         会触发之前的步骤 ``on_event`` 在门户上线程没有 FIFOLock 被任何人持有，进行竞
         速线程 append ``state.events``
        .
        """
        from acp.schema import ToolCallStart

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("done")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append, on_token=lambda _: None)

        # 回调未连线 — 迟到的 session_update 是安全的无操作发射。
        assert mock_client.on_event is None
        assert mock_client.on_token is None
        assert mock_client.on_activity is None

        pre_count = len(events)
        trailing = MagicMock(spec=ToolCallStart)
        trailing.tool_call_id = "tc-late"
        trailing.title = "Late arrival"
        trailing.kind = "read"
        trailing.status = "completed"
        trailing.raw_input = None
        trailing.raw_output = None
        trailing.content = None
        asyncio.run(mock_client.session_update("sess", trailing))
        assert len(events) == pre_count  # 没有任何内容达到陈旧状态回调

    def test_step_clears_live_callbacks_on_error(self, tmp_path):
        """回调 unwire 也会在 step() 上升时运行（finally 阻塞）。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            raise RuntimeError("boom")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with pytest.raises(RuntimeError):
            agent.step(conversation, on_event=events.append)

        assert mock_client.on_event is None
        assert mock_client.on_token is None
        assert mock_client.on_activity is None

    def test_step_emits_no_tool_call_events_when_none(self, tmp_path):
        """当没有积累工具调用时，step() 仅发出 MessageEvent。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            mock_client.accumulated_text.append("no tools used")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        # ActionEvent(FinishAction) + ObservationEvent(FinishObservation)
        assert len(events) == 2
        assert isinstance(events[0], ActionEvent)

    def test_tool_call_events_cleared_between_turns(self, tmp_path):
        """accumulated_tool_calls 在回合之间在 reset() 上被清除。"""
        agent = _make_agent()
        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        # 使用工具调用模拟第一回合
        mock_client.accumulated_tool_calls.append(
            {
                "tool_call_id": "tc-old",
                "title": "Old tool",
                "tool_kind": "read",
                "status": "completed",
                "raw_input": None,
                "raw_output": None,
            }
        )

        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        def _fake_run_async(_coro, **_kwargs):
            # 重置后，accumulated_tool_calls 应该为空仅添加文本，以便 step() 成功
            #
            mock_client.accumulated_text.append("response")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        # step() 调用 reset()，应清除旧的工具调用
        agent.step(conversation, on_event=events.append)

        # 仅应出现 FinishAction + FinishObservation — 旧的工具调用已被 reset() 清除
        #
        assert len(events) == 2
        assert isinstance(events[0], ActionEvent)


# ---------------------------------------------------------------------------
# ask_agent
# ---------------------------------------------------------------------------


class TestACPAgentAskAgent:
    def test_ask_agent_raises_if_not_initialized(self):
        """当 _conn 为 None 时，ask_agent() 引发 RuntimeError。"""
        agent = _make_agent()
        # _conn 和 _session_id 默认为 None
        with pytest.raises(RuntimeError, match="no ACP connection"):
            agent.ask_agent("What is 2+2?")

    def test_ask_agent_raises_if_session_id_missing(self):
        """当 _session_id 为 None 时，ask_agent() 引发 RuntimeError。"""
        agent = _make_agent()
        agent._conn = MagicMock()
        agent._session_id = None
        with pytest.raises(RuntimeError, match="no session ID"):
            agent.ask_agent("What is 2+2?")

    def test_ask_agent_forks_and_prompts(self):
        """ask_agent() 分叉会话提示词，并返回响应。"""
        agent = _make_agent()
        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "main-session"
        agent._working_dir = "/workspace"

        # 模拟对象 fork_session 回复
        mock_fork_response = MagicMock()
        mock_fork_response.session_id = "fork-session-123"

        # 模拟对象提示词响应（无使用）
        mock_prompt_response = MagicMock()
        mock_prompt_response.usage = None

        async def _fake_prompt(*args, **kwargs):
            # 模拟在提示词期间通过 session_update 到达的文本
            mock_client._fork_accumulated_text.extend(["Hello", " world"])
            return mock_prompt_response

        def _fake_run_async(coro_fn, **_kwargs):
            """同步模拟异步执行。"""
            loop = asyncio.new_event_loop()
            try:
                _agent_conn(agent).fork_session = AsyncMock(
                    return_value=mock_fork_response
                )
                _agent_conn(agent).prompt = _fake_prompt
                return loop.run_until_complete(coro_fn())
            finally:
                loop.close()

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        result = agent.ask_agent("What is 2+2?")

        assert result == "Hello world"

    def test_ask_agent_records_token_usage(self):
        """ask_agent()记录PromptResponse中的词元用量。"""
        agent = _make_agent()
        mock_client = _OpenHandsACPBridge()
        mock_client._context_window = 200000
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "main-session"
        agent._working_dir = "/workspace"

        mock_fork_response = MagicMock()
        mock_fork_response.session_id = "fork-session-456"

        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cached_read_tokens = 10
        mock_usage.cached_write_tokens = 5
        mock_usage.thought_tokens = 20

        mock_prompt_response = MagicMock()
        mock_prompt_response.usage = mock_usage

        async def _fake_prompt(*args, **kwargs):
            mock_client._fork_accumulated_text.append("response")
            return mock_prompt_response

        def _fake_run_async(coro_fn, **_kwargs):
            loop = asyncio.new_event_loop()
            try:
                _agent_conn(agent).fork_session = AsyncMock(
                    return_value=mock_fork_response
                )
                _agent_conn(agent).prompt = _fake_prompt
                return loop.run_until_complete(coro_fn())
            finally:
                loop.close()

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.ask_agent("Summarize this")

        metrics = agent.llm.metrics
        assert len(metrics.token_usages) == 1
        usage = metrics.token_usages[0]
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.cache_read_tokens == 10
        assert usage.cache_write_tokens == 5
        assert usage.reasoning_tokens == 20
        assert usage.context_window == 200000

    def test_ask_agent_cleans_up_fork_state(self):
        """即使成功，ask_agent() 也会清除分叉状态。"""
        agent = _make_agent()
        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "main-session"
        agent._working_dir = "/workspace"

        mock_fork_response = MagicMock()
        mock_fork_response.session_id = "fork-session-789"

        mock_prompt_response = MagicMock()
        mock_prompt_response.usage = None

        async def _fake_prompt(*args, **kwargs):
            mock_client._fork_accumulated_text.append("ok")
            return mock_prompt_response

        def _fake_run_async(coro_fn, **_kwargs):
            loop = asyncio.new_event_loop()
            try:
                _agent_conn(agent).fork_session = AsyncMock(
                    return_value=mock_fork_response
                )
                _agent_conn(agent).prompt = _fake_prompt
                return loop.run_until_complete(coro_fn())
            finally:
                loop.close()

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.ask_agent("test")

        # 应该清理fork状态
        assert mock_client._fork_session_id is None
        assert mock_client._fork_accumulated_text == []


# ---------------------------------------------------------------------------
# 客户端分叉文本路由
# ---------------------------------------------------------------------------


class TestClientForkTextRouting:
    @pytest.mark.asyncio
    async def test_fork_text_routed_to_fork_accumulator(self):
        """当设置 _fork_session_id 时，匹配的文本将进入 fork 累加器。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client._fork_session_id = "fork-sess"
        client._fork_accumulated_text = []

        update = MagicMock(spec=AgentMessageChunk)
        update.content = MagicMock(spec=TextContentBlock)
        update.content.text = "fork response"

        await client.session_update("fork-sess", update)

        assert client._fork_accumulated_text == ["fork response"]
        # 主蓄能器应为空
        assert client.accumulated_text == []

    @pytest.mark.asyncio
    async def test_main_text_unaffected_by_active_fork(self):
        """即使分叉处于活动状态，主会话文本也会路由到 accumulated_text。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client._fork_session_id = "fork-sess"
        client._fork_accumulated_text = []

        update = MagicMock(spec=AgentMessageChunk)
        update.content = MagicMock(spec=TextContentBlock)
        update.content.text = "main response"

        await client.session_update("main-sess", update)

        assert client.accumulated_text == ["main response"]
        assert client._fork_accumulated_text == []

    @pytest.mark.asyncio
    async def test_no_fork_normal_routing(self):
        """当_fork_session_id为None时，所有文本都进入主累加器。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        assert client._fork_session_id is None

        update = MagicMock(spec=AgentMessageChunk)
        update.content = MagicMock(spec=TextContentBlock)
        update.content.text = "normal text"

        await client.session_update("any-session", update)

        assert client.accumulated_text == ["normal text"]
        assert client._fork_accumulated_text == []


# ---------------------------------------------------------------------------
# acp_session_mode 字段
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _select_auth_method
# ---------------------------------------------------------------------------


_CHATGPT_AUTH_JSON = (
    '{"tokens": {"id_token": "x", "access_token": "y", "refresh_token": "z"}}'
)


class TestSelectAuthMethod:
    """测试环境变量中 ACP auth 方法的自动检测。"""

    @staticmethod
    def _make_auth_method(method_id: str) -> MagicMock:
        m = MagicMock()
        m.id = method_id
        return m

    def test_openai_api_key(self):
        methods = [self._make_auth_method("api-key")]
        env = {"OPENAI_API_KEY": "sk-test"}
        assert _select_auth_method(methods, env) == "api-key"

    def test_codex_api_key(self):
        methods = [self._make_auth_method("api-key")]
        env = {"CODEX_API_KEY": "key1"}
        assert _select_auth_method(methods, env) == "api-key"

    def test_chatgpt_preferred_over_api_key(self, tmp_path):
        """ChatGPT 订阅登录优先于 API 键。"""
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir()
        (auth_dir / "auth.json").write_text(_CHATGPT_AUTH_JSON, encoding="utf-8")

        env = {"OPENAI_API_KEY": "sk-test"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "chat-gpt"

    def test_api_key_fallback_when_no_chatgpt_file(self, tmp_path):
        """当提供 chatgpt 但缺少验证文件时，返回到 API 键。"""
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "api-key"

    def test_no_matching_credentials(self, tmp_path):
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        env = {"UNRELATED": "value"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) is None

    def test_missing_codex_auth_reason(self, tmp_path, caplog):
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        with (
            patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path),
            caplog.at_level("WARNING"),
        ):
            _warn_auth_selection_failure(methods, {})

        assert (
            f"Codex auth file {tmp_path / '.codex' / 'auth.json'} is missing"
            in caplog.text
        )
        assert "CODEX_API_KEY and OPENAI_API_KEY are unset" in caplog.text

    def test_invalid_codex_auth_reason(self, tmp_path):
        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir()
        auth_path = auth_dir / "auth.json"
        auth_path.write_text('{"auth_mode": "apikey"}', encoding="utf-8")
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            reason = _auth_selection_failure_reason(methods, {})

        assert f"Codex auth file {auth_path} is not valid ChatGPT auth" in reason
        assert "CODEX_API_KEY and OPENAI_API_KEY are unset" in reason

    def test_chatgpt_auth_file(self, tmp_path):
        methods = [self._make_auth_method("chat-gpt")]
        auth_dir = tmp_path / ".codex"
        auth_dir.mkdir()
        (auth_dir / "auth.json").write_text(_CHATGPT_AUTH_JSON, encoding="utf-8")

        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, {}) == "chat-gpt"

    def test_gemini_oauth_personal_when_creds_file_present(self, tmp_path):
        """当~/.gemini/oauth_creds.json时选择gemini-CLI的OAuth登录
        存在，不需要 GEMINI_API_KEY。"""
        methods = [
            self._make_auth_method("oauth-personal"),
            self._make_auth_method("gemini-api-key"),
        ]
        gem_dir = tmp_path / ".gemini"
        gem_dir.mkdir()
        (gem_dir / "oauth_creds.json").write_text("{}", encoding="utf-8")

        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, {}) == "oauth-personal"

    def test_gemini_oauth_preferred_over_api_key(self, tmp_path):
        """OAuth 登录优先于 GEMINI_API_KEY（镜像 chatgpt）。"""
        methods = [
            self._make_auth_method("oauth-personal"),
            self._make_auth_method("gemini-api-key"),
        ]
        gem_dir = tmp_path / ".gemini"
        gem_dir.mkdir()
        (gem_dir / "oauth_creds.json").write_text("{}", encoding="utf-8")

        env = {"GEMINI_API_KEY": "g-test"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "oauth-personal"

    def test_gemini_api_key_fallback_when_no_oauth_file(self, tmp_path):
        """回到 GEMINI_API_KEY 当提供 oauth-personal 时，
        creds 文件不存在 (e.g. 在服务器图像中）。"""
        methods = [
            self._make_auth_method("oauth-personal"),
            self._make_auth_method("gemini-api-key"),
        ]
        env = {"GEMINI_API_KEY": "g-test"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "gemini-api-key"

    def test_gemini_oauth_offered_but_no_creds_no_key(self, tmp_path):
        """提供了 oauth-personal，没有信用文件，也没有 API 密钥 -> None。"""
        methods = [
            self._make_auth_method("oauth-personal"),
            self._make_auth_method("gemini-api-key"),
        ]
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, {}) is None

    def test_empty_auth_methods(self):
        assert _select_auth_method([], {}) is None

    def test_method_not_in_server_list(self, tmp_path):
        """即使设置了环境变量，方法也必须由服务器提供。"""
        methods = [self._make_auth_method("chat-gpt")]
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) is None

    # -- CODEX_HOME 感知 chatgpt 检测（问题 #1020） ------------------

    def test_chatgpt_detected_under_relocated_codex_home(self, tmp_path):
        """当 auth.json 位于重新定位的 CODEX_HOME 下时，选择 chatgpt，
        即使 ~/.codex/auth.json 不存在。"""
        codex_home = tmp_path / "conv" / "acp" / "codex"
        codex_home.mkdir(parents=True)
        (codex_home / "auth.json").write_text(_CHATGPT_AUTH_JSON, encoding="utf-8")
        methods = [self._make_auth_method("chat-gpt")]
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=empty_home):
            assert (
                _select_auth_method(methods, {"CODEX_HOME": str(codex_home)})
                == "chat-gpt"
            )

    def test_codex_home_without_auth_file_falls_back(self, tmp_path):
        """没有 auth.json 的 CODEX_HOME 不会被检测为 chatgpt； 它掉下来了
        当提供时返回到 API 键。"""
        codex_home = tmp_path / "empty_codex_home"
        codex_home.mkdir()
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        env = {"CODEX_HOME": str(codex_home), "OPENAI_API_KEY": "sk-test"}
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=empty_home):
            assert _select_auth_method(methods, env) == "api-key"

    def test_codex_auth_file_honors_codex_home(self, tmp_path):
        """设置后，codex_auth_file 指向 $CODEX_HOME/auth.json，否则
        ~/.codex/auth.json."""
        home = tmp_path / "home"
        home.mkdir()
        with patch.object(acp_file_credentials_module.Path, "home", return_value=home):
            assert codex_auth_file({}) == home / ".codex" / "auth.json"
        ch = tmp_path / "ch"
        assert codex_auth_file({"CODEX_HOME": str(ch)}) == ch / "auth.json"

    # -- apikey-format auth.json 不得被视为 chatgpt (#3627) -----

    def test_apikey_format_auth_file_falls_back_to_api_key(self, tmp_path):
        """Codex 用 {"auth_mode": "apikey", ...} 重写 $CODEX_HOME/auth.json
        在 apikey 模式会话期间。 重新启动时，该文件必须不被选择为 ``chatgpt``，否则
        codex-ACP 会挂在基于浏览器的 OAuth 上（问
        题 #3627）。
        """
        codex_home = tmp_path / "codex"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text(
            '{"auth_mode": "apikey", "OPENAI_API_KEY": "sk-test"}',
            encoding="utf-8",
        )
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        env = {"CODEX_HOME": str(codex_home), "OPENAI_API_KEY": "sk-test"}
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=empty_home):
            assert _select_auth_method(methods, env) == "api-key"

    def test_malformed_auth_file_falls_back_to_api_key(self, tmp_path):
        """非 JSON/不可读的 auth.json 不得触发 chatgpt 选择。"""
        codex_home = tmp_path / "codex"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text("not-json{", encoding="utf-8")
        methods = [
            self._make_auth_method("chat-gpt"),
            self._make_auth_method("api-key"),
        ]
        env = {"CODEX_HOME": str(codex_home), "OPENAI_API_KEY": "sk-test"}
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=empty_home):
            assert _select_auth_method(methods, env) == "api-key"

    # -- Gemini Vertex AI 服务帐户检测（问题 #1020） ----------

    def test_vertex_ai_selected_when_credentials_file_present(self, tmp_path):
        """当 GOOGLE_APPLICATION_CREDENTIALS 指向某个点时，将选择 vertex-ai
        现有服务帐户JSON。"""
        sa = tmp_path / "gcloud-credentials.json"
        sa.write_text("{}", encoding="utf-8")
        methods = [
            self._make_auth_method("vertex-ai"),
            self._make_auth_method("oauth-personal"),
            self._make_auth_method("gemini-api-key"),
        ]
        env = {"GOOGLE_APPLICATION_CREDENTIALS": str(sa), "GEMINI_API_KEY": "g"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "vertex-ai"

    def test_vertex_ai_preferred_over_personal_oauth(self, tmp_path):
        """物化 Vertex SA（可部署）胜过主机绑定
        个人 OAuth 登录文件。"""
        sa = tmp_path / "sa.json"
        sa.write_text("{}", encoding="utf-8")
        gem_dir = tmp_path / ".gemini"
        gem_dir.mkdir()
        (gem_dir / "oauth_creds.json").write_text("{}", encoding="utf-8")
        methods = [
            self._make_auth_method("vertex-ai"),
            self._make_auth_method("oauth-personal"),
        ]
        env = {"GOOGLE_APPLICATION_CREDENTIALS": str(sa)}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "vertex-ai"

    def test_vertex_ai_offered_but_no_credentials_file(self, tmp_path):
        """vertex-ai 已提供，但 GOOGLE_APPLICATION_CREDENTIALS 缺失/为空 ->
        落入 API 键回退方案。"""
        methods = [
            self._make_auth_method("vertex-ai"),
            self._make_auth_method("gemini-api-key"),
        ]
        env = {"GEMINI_API_KEY": "g"}
        with patch("openhands.sdk.agent.acp_agent.Path.home", return_value=tmp_path):
            assert _select_auth_method(methods, env) == "gemini-api-key"


# ---------------------------------------------------------------------------
# _with_codex_base_url
# ---------------------------------------------------------------------------


class TestWithCodexBaseUrl:
    def test_current_adapter_uses_child_config_without_mutating_input(self):
        env = {
            "OPENAI_BASE_URL": "https://proxy.example",
            "OPENAI_API_KEY": "sk-test",
        }
        original = env.copy()
        result = _with_codex_base_url(
            "npx",
            ["-y", "@agentclientprotocol/codex-acp@1.10.0"],
            env,
        )
        assert json.loads(result["CODEX_CONFIG"]) == {
            "openai_base_url": "https://proxy.example"
        }
        assert env == original
        assert "CODEX_CONFIG" not in env

    def test_preinstalled_current_adapter_uses_child_config(self):
        env = {"OPENAI_BASE_URL": "https://proxy.example"}
        result = _with_codex_base_url("codex-acp", [], env)
        assert json.loads(result["CODEX_CONFIG"])["openai_base_url"] == (
            "https://proxy.example"
        )

    def test_existing_codex_config_is_merged_in_returned_mapping(self):
        env = {
            "OPENAI_BASE_URL": "https://proxy.example",
            "CODEX_CONFIG": json.dumps({"model": "gpt-5.5"}),
        }
        original = env.copy()
        result = _with_codex_base_url("codex-acp", [], env)
        assert json.loads(result["CODEX_CONFIG"]) == {
            "model": "gpt-5.5",
            "openai_base_url": "https://proxy.example",
        }
        assert env == original

    def test_current_adapter_preserves_explicit_codex_base_url(self):
        env = {
            "OPENAI_BASE_URL": "https://proxy.example",
            "CODEX_CONFIG": json.dumps({"openai_base_url": "https://explicit"}),
        }
        result = _with_codex_base_url(
            "npx",
            ["-y", "@agentclientprotocol/codex-acp@1.10.0"],
            env,
        )
        assert json.loads(result["CODEX_CONFIG"])["openai_base_url"] == (
            "https://explicit"
        )
        assert result == env

    def test_invalid_codex_config_is_left_to_adapter(self):
        env = {
            "OPENAI_BASE_URL": "https://proxy.example",
            "CODEX_CONFIG": "not-json",
        }
        result = _with_codex_base_url(
            "npx",
            ["-y", "@agentclientprotocol/codex-acp@1.10.0"],
            env,
        )
        assert result == env

    def test_noop_for_non_codex(self):
        env = {"OPENAI_BASE_URL": "https://p"}
        assert _with_codex_base_url("claude-agent-acp", [], env) == env

    def test_noop_when_no_base_url(self):
        env: dict[str, str] = {}
        assert _with_codex_base_url("codex-acp", [], env) == env

    def test_noop_when_model_provider_is_explicit(self):
        env = {
            "OPENAI_BASE_URL": "https://p",
            "MODEL_PROVIDER": "custom",
        }
        assert _with_codex_base_url("codex-acp", [], env) == env

    def test_noop_when_config_model_provider_is_explicit(self):
        env = {
            "OPENAI_BASE_URL": "https://p",
            "CODEX_CONFIG": json.dumps({"model_provider": "custom"}),
        }
        assert _with_codex_base_url("codex-acp", [], env) == env


class TestCodexModelConfigOptions:
    def test_splits_combined_model_and_reasoning_effort(self):
        assert _codex_model_config_options("gpt-5.5/high") == (
            ("model", "gpt-5.5"),
            ("reasoning_effort", "high"),
        )

    def test_leaves_base_or_custom_model_id_unchanged(self):
        assert _codex_model_config_options("gpt-5.5") == (("model", "gpt-5.5"),)
        assert _codex_model_config_options("custom/provider/model") == (
            ("model", "custom/provider/model"),
        )


# ---------------------------------------------------------------------------
# ACP 模型覆盖
# ---------------------------------------------------------------------------


class TestMaybeSetSessionModel:
    @pytest.mark.asyncio
    async def test_set_session_model_mechanism(self):
        # ``via_config_option=False``（gemini-CLI 的 ``models`` 功能）通过
        # ``set_session_model`` 应用模型。
        #
        conn = AsyncMock()
        applied = await _maybe_set_session_model(
            conn, "codex-acp", "session-1", "gpt-5.4", via_config_option=False
        )
        conn.set_session_model.assert_awaited_once_with(
            model_id="gpt-5.4",
            session_id="session-1",
        )
        conn.set_config_option.assert_not_called()
        # 覆盖实际上是通过协议调用推送到服务器的。
        assert applied is True

    @pytest.mark.asyncio
    async def test_set_config_option_mechanism(self):
        # ``via_config_option=True``（codex-ACP 和 claude-智能体-ACP）通过
        # ``set_config_option(configId="model")`` 应用模型。
        #
        conn = AsyncMock()
        applied = await _maybe_set_session_model(
            conn,
            "claude-agent-acp",
            "session-1",
            "opus[1m]",
            via_config_option=True,
        )
        conn.set_config_option.assert_awaited_once_with(
            config_id="model",
            value="opus[1m]",
            session_id="session-1",
        )
        conn.set_session_model.assert_not_called()
        assert applied is True

    @pytest.mark.asyncio
    async def test_codex_config_option_splits_reasoning_effort(self):
        # Canvas 可能持久化 Codex ids 为 ``model/effort``； codex-ACP 将工作量公开为其自
        # 己的配置选项。
        #
        conn = AsyncMock()
        applied = await _maybe_set_session_model(
            conn, "codex-acp", "session-1", "gpt-5.4/low", via_config_option=True
        )
        conn.set_session_model.assert_not_called()
        conn.set_config_option.assert_has_awaits(
            [
                call(config_id="model", value="gpt-5.4", session_id="session-1"),
                call(
                    config_id="reasoning_effort",
                    value="low",
                    session_id="session-1",
                ),
            ]
        )
        assert conn.set_config_option.await_count == 2
        assert applied is True

    @pytest.mark.asyncio
    async def test_pi_model_switch_mechanism(self):
        """pi-ACP 通过 set_config_option(config_id='model') 应用模型。"""
        conn = AsyncMock()
        applied = await _maybe_set_session_model(
            conn,
            "pi-acp",
            "session-1",
            "anthropic/claude-sonnet-4-6",
            via_config_option=True,
        )
        conn.set_config_option.assert_awaited_once_with(
            config_id="model",
            value="anthropic/claude-sonnet-4-6",
            session_id="session-1",
        )
        assert applied is True

    @pytest.mark.asyncio
    async def test_missing_model_skips_protocol_override(self):
        conn = AsyncMock()
        applied = await _maybe_set_session_model(
            conn, "codex-acp", "session-1", None, via_config_option=True
        )
        conn.set_session_model.assert_not_called()
        conn.set_config_option.assert_not_called()
        assert applied is False

    @pytest.mark.asyncio
    async def test_unknown_provider_applies_via_detected_mechanism(self):
        # 未知/自定义服务器通过其会话/新广告（在上游检测到）的任何机制应用模型，而不是硬
        # 编码的猜测。
        #
        conn_cfg = AsyncMock()
        applied = await _maybe_set_session_model(
            conn_cfg, "devin-cli", "session-1", "kimi-k2-6", via_config_option=True
        )
        conn_cfg.set_config_option.assert_awaited_once_with(
            config_id="model", value="kimi-k2-6", session_id="session-1"
        )
        conn_cfg.set_session_model.assert_not_called()
        assert applied is True

        conn_set = AsyncMock()
        applied = await _maybe_set_session_model(
            conn_set, "devin-cli", "session-1", "kimi-k2-6", via_config_option=False
        )
        conn_set.set_session_model.assert_awaited_once_with(
            model_id="kimi-k2-6", session_id="session-1"
        )
        conn_set.set_config_option.assert_not_called()
        assert applied is True

    @pytest.mark.asyncio
    async def test_unknown_provider_apply_failure_is_tolerated(self):
        # 如果模型应用对于未知提供者失败，我们会记录警告，但不会中断会话创建。
        #
        conn = AsyncMock()
        conn.set_config_option.side_effect = ACPRequestError(
            code=-32601, message="method not found"
        )
        applied = await _maybe_set_session_model(
            conn, "some-custom-acp", "session-1", "whatever", via_config_option=True
        )
        conn.set_config_option.assert_awaited_once()
        assert applied is False

    @pytest.mark.asyncio
    async def test_known_provider_apply_rejection_is_tolerated(self):
        # Claude-智能体-ACP's ``model`` 选择是动态/账户相关的，并且拒绝缺失的自定义
        # IDe.g. ``sonnet`` 在没有它的情况下，伪装成 -32603)。 拒绝 *初始* 模型必须不能
        # 失败会话创建——它降级到服务器默认值（应用）False）类似于未知提供者路径，因为精
        # 选列表是一个建议，而不是访问检查。（运行时切换 via set_acp_model 展示错误。
        #
        conn = AsyncMock()
        conn.set_config_option.side_effect = ACPRequestError(
            code=-32603, message="Invalid value for config option model: sonnet"
        )
        applied = await _maybe_set_session_model(
            conn, "claude-agent-acp", "session-1", "sonnet", via_config_option=True
        )
        conn.set_config_option.assert_awaited_once()
        conn.set_session_model.assert_not_called()
        assert applied is False


class TestReapplySessionModelOnResume:
    """Resume 通过运行时切换门重新应用已持久化模型。"""

    @pytest.mark.asyncio
    async def test_reapply_via_set_session_model_mechanism(self):
        # load_session() 不进行模型选择，因此在恢复时必须通过运行时切换门重新应用已持久
        # 化模型。 服务器与
        # ``models`` 能力（gemini-CLI，较旧的法典/克劳德）使用
        # ``set_session_model``.
        conn = AsyncMock()
        applied = await _reapply_session_model_on_resume(
            conn,
            "claude-agent-acp",
            "sess-1",
            "claude-haiku-4-5-20251001",
            via_config_option=False,
        )
        conn.set_session_model.assert_awaited_once_with(
            model_id="claude-haiku-4-5-20251001", session_id="sess-1"
        )
        assert applied is True

    @pytest.mark.asyncio
    async def test_reapply_via_set_config_option_mechanism(self):
        # codex-acp/claude-智能体-ACP 0.44+ 通过重新申请
        # ``set_config_option(configId="model")`` 带有裸预设 ID。
        conn = AsyncMock()
        applied = await _reapply_session_model_on_resume(
            conn, "codex-acp", "sess-1", "gpt-5.5", via_config_option=True
        )
        conn.set_config_option.assert_awaited_once_with(
            config_id="model", value="gpt-5.5", session_id="sess-1"
        )
        conn.set_session_model.assert_not_called()
        assert applied is True

    @pytest.mark.asyncio
    async def test_codex_reapply_splits_reasoning_effort(self):
        conn = AsyncMock()
        applied = await _reapply_session_model_on_resume(
            conn, "codex-acp", "sess-1", "gpt-5.4/low", via_config_option=True
        )
        conn.set_session_model.assert_not_called()
        conn.set_config_option.assert_has_awaits(
            [
                call(config_id="model", value="gpt-5.4", session_id="sess-1"),
                call(
                    config_id="reasoning_effort",
                    value="low",
                    session_id="sess-1",
                ),
            ]
        )
        assert conn.set_config_option.await_count == 2
        assert applied is True

    @pytest.mark.asyncio
    async def test_missing_model_skips_reapply(self):
        conn = AsyncMock()
        applied = await _reapply_session_model_on_resume(
            conn, "claude-agent-acp", "sess-1", None, via_config_option=True
        )
        conn.set_session_model.assert_not_called()
        conn.set_config_option.assert_not_called()
        assert applied is False

    @pytest.mark.asyncio
    async def test_unknown_provider_reapplies_via_detected_mechanism(self):
        # provider=None (custom server) reapplies via whichever mechanism the
        # 已恢复会话广告，而不是硬编码的猜测。
        conn = AsyncMock()
        applied = await _reapply_session_model_on_resume(
            conn, "devin-cli", "sess-1", "kimi-k2-6", via_config_option=True
        )
        conn.set_session_model.assert_not_called()
        conn.set_config_option.assert_awaited_once_with(
            config_id="model",
            value="kimi-k2-6",
            session_id="sess-1",
        )
        assert applied is True

    @pytest.mark.asyncio
    async def test_known_unsupported_provider_skips_reapply(self):
        from openhands.sdk.settings.acp_providers import ACPProviderInfo

        unsupported = ACPProviderInfo(
            key="legacy",
            display_name="Legacy",
            default_command=("legacy",),
            api_key_env_var=None,
            base_url_env_var=None,
            default_session_mode="default",
            agent_name_patterns=("legacy",),
            supports_set_session_model=False,
            supports_runtime_model_switch=False,
            session_meta_key=None,
        )
        conn = AsyncMock()
        with patch(
            "openhands.sdk.agent.acp_agent.detect_acp_provider_by_agent_name",
            return_value=unsupported,
        ):
            applied = await _reapply_session_model_on_resume(
                conn, "legacy-acp", "sess-1", "x", via_config_option=False
            )
        conn.set_session_model.assert_not_called()
        assert applied is False

    @pytest.mark.asyncio
    async def test_client_rejection_is_swallowed_on_resume(self):
        # 客户端/协议拒绝（方法未找到 = 服务器不支持调用，或无效模型 ID）不应中断回放 —
        # 这与 load_session 回退方案相同。 错误被记录，而不是引发。
        #
        conn = AsyncMock()
        conn.set_config_option.side_effect = ACPRequestError(
            code=-32601, message="method not found"
        )
        applied = await _reapply_session_model_on_resume(
            conn, "some-custom-acp", "sess-1", "whatever", via_config_option=True
        )
        conn.set_config_option.assert_awaited_once()
        # Rejected => the live session kept the server default, so the override
        # 必须将不报告为已应用。
        assert applied is False

    @pytest.mark.asyncio
    async def test_any_request_error_is_swallowed_on_resume(self):
        # 任何 ACPRequestError（例如 -32603 服务器错误）在恢复时都容忍 — 比如
        # load_session 回退方案 — 因此，一个不可靠/过时的服务器不能破坏会话启动； 会话保
        # 持服务器默认值。
        #
        conn = AsyncMock()
        conn.set_session_model.side_effect = ACPRequestError(
            code=-32603, message="internal error"
        )
        applied = await _reapply_session_model_on_resume(
            conn, "codex-acp", "sess-1", "gpt-5.5", via_config_option=False
        )
        conn.set_session_model.assert_awaited_once()
        assert applied is False


class TestHasLiveACPSession:
    """公共谓词 LocalConversation 分支用于模型切换。"""

    def test_false_before_session(self):
        # 全新构建：尚未连接连接/会话/执行器。
        agent = _make_agent()
        assert agent.has_live_acp_session is False

    def test_true_when_fully_wired(self):
        agent = _make_agent()
        agent._conn = MagicMock()
        agent._session_id = "sess-1"
        agent._executor = MagicMock()
        assert agent.has_live_acp_session is True

    @pytest.mark.parametrize(
        "conn,session_id,executor",
        [
            (None, "sess-1", "exec"),
            ("conn", None, "exec"),
            ("conn", "sess-1", None),
        ],
    )
    def test_false_when_partially_wired(self, conn, session_id, executor):
        # 三个运行时句柄中的每一个都必须存在； 部分拆卸/引导程序不得读取为实时会话。
        #
        agent = _make_agent()
        agent._conn = MagicMock() if conn else None
        agent._session_id = session_id
        agent._executor = MagicMock() if executor else None
        assert agent.has_live_acp_session is False

    def test_set_acp_model_raises_when_no_live_session(self):
        # 低级原语仍然拒绝会话前调用（延迟位于 LocalConversation.switch_acp_model 中，它
        # 在谓词上分支）； 两人呆在同步中的警卫。
        #
        agent = _make_agent()
        assert not agent.has_live_acp_session
        with pytest.raises(RuntimeError, match="not initialized"):
            agent.set_acp_model("gpt-5.4")


class TestSetACPModel:
    """通过会话机制进行运行时（对话中）模型切换。"""

    @staticmethod
    def _wire(
        agent: ACPAgent, agent_name: str, *, via_config_option: bool = False
    ) -> ACPAgent:
        conn = MagicMock()
        conn.set_session_model = AsyncMock()
        conn.set_config_option = AsyncMock()
        agent._conn = conn
        agent._session_id = "sess-1"
        agent._agent_name = agent_name
        agent._model_via_config_option = via_config_option
        executor = MagicMock()

        # run_async 实际上驱动 (异步) apply 协程完成，因此 AsyncMock conn 调用 fire — 行
        # 使真正的 apply/split 路径。
        #
        def _run(coro: Any, timeout: Any = None) -> Any:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        executor.run_async = MagicMock(side_effect=_run)
        agent._executor = executor
        return agent

    def test_switches_model_on_live_codex_session(self):
        # 默认（模型能力）会话 ⇒ set_session_model，id 按原样。
        agent = self._wire(_make_agent(), "codex-acp")
        agent.set_acp_model("gpt-5.5")
        _agent_conn(agent).set_session_model.assert_awaited_once_with(
            model_id="gpt-5.5", session_id="sess-1"
        )
        _agent_conn(agent).set_config_option.assert_not_called()
        agent._executor.run_async.assert_called_once()
        # 哨兵值 LLM + 指标反映了成本/代币跟踪的实时模型。
        assert agent.llm.model == "gpt-5.5"
        assert agent.llm.metrics.model_name == "gpt-5.5"

    def test_switches_codex_via_config_option_single_call(self):
        # codex-ACP configOptions：裸预设 id 作为单个应用
        # `model`选择。
        agent = self._wire(_make_agent(), "codex-acp", via_config_option=True)
        agent.set_acp_model("gpt-5.5")
        _agent_conn(agent).set_config_option.assert_awaited_once_with(
            config_id="model", value="gpt-5.5", session_id="sess-1"
        )
        _agent_conn(agent).set_session_model.assert_not_called()
        assert agent.llm.model == "gpt-5.5"
        assert agent._current_model_id == "gpt-5.5"

    def test_switches_codex_via_config_option_splits_reasoning_effort(self):
        agent = self._wire(_make_agent(), "codex-acp", via_config_option=True)
        agent.set_acp_model("gpt-5.5/high")
        _agent_conn(agent).set_config_option.assert_has_awaits(
            [
                call(config_id="model", value="gpt-5.5", session_id="sess-1"),
                call(
                    config_id="reasoning_effort",
                    value="high",
                    session_id="sess-1",
                ),
            ]
        )
        assert _agent_conn(agent).set_config_option.await_count == 2
        _agent_conn(agent).set_session_model.assert_not_called()
        assert agent.llm.model == "gpt-5.5/high"
        assert agent._current_model_id == "gpt-5.5/high"

    def test_switches_claude_via_config_option_single_call(self):
        # 裸 ID（无 `/`）可用作单个 `model` 选择 — 毫不费力。
        agent = self._wire(_make_agent(), "claude-agent-acp", via_config_option=True)
        agent.set_acp_model("sonnet")
        _agent_conn(agent).set_config_option.assert_awaited_once_with(
            config_id="model", value="sonnet", session_id="sess-1"
        )
        assert agent._current_model_id == "sonnet"

    def test_switch_method_not_found_raises_no_fallback(self):
        # 无跨机制回退方案：-32601 表面作为 ValueError 命名所公布的机制，并且从未尝试其
        # 他调用。
        #
        agent = self._wire(_make_agent(), "codex-acp", via_config_option=False)
        _agent_conn(agent).set_session_model.side_effect = ACPRequestError(
            code=-32601, message="Method not found"
        )
        with pytest.raises(ValueError, match="rejected set_session_model"):
            agent.set_acp_model("gpt-5.5")
        _agent_conn(agent).set_config_option.assert_not_called()
        agent._executor.run_async.assert_called_once()
        # 机制 + 哨兵值模型在发生故障的开关上保持不变。
        assert agent._model_via_config_option is False
        assert agent.llm.model != "gpt-5.5"

    def test_switch_invalid_model_raises_value_error(self):
        # -32602 invalid-params 是真正的客户端错误，而不是错误机制
        # signal：将其显示为 ValueError，无需第二次调用。
        agent = self._wire(_make_agent(), "codex-acp", via_config_option=True)
        _agent_conn(agent).set_config_option.side_effect = ACPRequestError(
            code=-32602, message="Invalid params"
        )
        with pytest.raises(ValueError, match="rejected set_config_option"):
            agent.set_acp_model("nonsense")
        agent._executor.run_async.assert_called_once()

    def test_claude_provider_supports_runtime_switch(self):
        agent = self._wire(_make_agent(), "claude-agent-acp")
        agent.set_acp_model("claude-haiku-4-5-20251001")
        _agent_conn(agent).set_session_model.assert_called_once_with(
            model_id="claude-haiku-4-5-20251001", session_id="sess-1"
        )

    def test_unknown_provider_still_attempts_switch(self):
        # 允许自定义/无法识别的服务器（provider=None）尝试调用； 如果实际上不支持，则
        # ACP 层错误。
        #
        agent = self._wire(_make_agent(), "some-custom-acp")
        agent.set_acp_model("whatever")
        _agent_conn(agent).set_session_model.assert_called_once()

    def test_rejects_empty_model(self):
        agent = self._wire(_make_agent(), "codex-acp")
        with pytest.raises(ValueError, match="non-empty"):
            agent.set_acp_model("   ")
        _agent_conn(agent).set_session_model.assert_not_called()

    def test_raises_before_session_initialized(self):
        agent = _make_agent()  # 没有 _conn / _session_id / _executor
        with pytest.raises(RuntimeError, match="not initialized"):
            agent.set_acp_model("gpt-5.4")

    def test_raises_for_provider_without_protocol_support(self):
        from openhands.sdk.settings.acp_providers import ACPProviderInfo

        unsupported = ACPProviderInfo(
            key="legacy",
            display_name="Legacy",
            default_command=("legacy",),
            api_key_env_var=None,
            base_url_env_var=None,
            default_session_mode="default",
            agent_name_patterns=("legacy",),
            supports_set_session_model=False,
            supports_runtime_model_switch=False,
            session_meta_key=None,
        )
        agent = self._wire(_make_agent(), "legacy-acp")
        with patch(
            "openhands.sdk.agent.acp_agent.detect_acp_provider_by_agent_name",
            return_value=unsupported,
        ):
            with pytest.raises(ValueError, match="does not support runtime"):
                agent.set_acp_model("x")
        _agent_conn(agent).set_session_model.assert_not_called()

    def test_translates_acp_request_error_to_value_error(self):
        # 协议级拒绝 (e.g. 自定义服务器上未找到方法，或无效的模型 ID）必须以 ValueError
        # 形式出现 - 不会作为原始 acp.exceptions.RequestError 泄漏 - 因此智能体服务器将
        # 其映射到 400。 拒绝是由 conn 引发的（通过实际应用协程驱动），行使
        # set_acp_model 的实际错误路径。
        #
        agent = self._wire(_make_agent(), "codex-acp")
        _agent_conn(agent).set_session_model.side_effect = ACPRequestError(
            code=-32601, message="method not found"
        )
        with pytest.raises(ValueError, match="rejected set_session_model"):
            agent.set_acp_model("bogus-model")
        # 当交换机发生故障时，哨兵值LLM不得发生突变。
        assert agent.llm.model != "bogus-model"

    def test_propagates_server_internal_error(self):
        # JSON-RPC -32603 是服务器内部错误，不是客户端请求的错误。 它必须传播（作为原始
        # ） ACPRequestError -> 5xx) 而不是被错误地标记为 400 类别 ValueError，重现处理
        # 的镜像提示词路径。
        #
        agent = self._wire(_make_agent(), "codex-acp")
        _agent_conn(agent).set_session_model.side_effect = ACPRequestError(
            code=-32603, message="internal error"
        )
        with pytest.raises(ACPRequestError):
            agent.set_acp_model("some-model")
        # 当交换机发生故障时，哨兵值LLM不得发生突变。
        assert agent.llm.model != "some-model"

    def test_passes_timeout_to_run_async(self):
        # 协议往返在会话状态锁下运行，因此必须对其进行限制，以避免在服务器从未应答时楔入
        # 锁。
        #
        agent = self._wire(_make_agent(acp_prompt_timeout=42.0), "codex-acp")
        agent.set_acp_model("gpt-5.5")
        _, kwargs = agent._executor.run_async.call_args
        assert kwargs["timeout"] == 42.0


# ---------------------------------------------------------------------------
# acp_session_mode 字段
# ---------------------------------------------------------------------------


class TestACPSessionMode:
    def test_default_is_none(self):
        agent = _make_agent()
        assert agent.acp_session_mode is None

    def test_can_set_explicit_mode(self):
        agent = ACPAgent(acp_command=["echo"], acp_session_mode="custom-mode")
        assert agent.acp_session_mode == "custom-mode"

    def test_serialization_roundtrip(self):
        agent = ACPAgent(
            acp_command=["codex-acp"],
            acp_session_mode="full-access",
        )
        dumped = agent.model_dump_json()
        restored = AgentBase.model_validate_json(dumped)
        assert isinstance(restored, ACPAgent)
        assert restored.acp_session_mode == "full-access"


# ---------------------------------------------------------------------------
# 连接重试逻辑
# ---------------------------------------------------------------------------


class TestACPPromptRetry:
    """测试重试逻辑是否存在 ACP 提示词故障。"""

    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        """使用用户消息创建模拟对象对话。"""
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )

        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_retry_on_connection_error_then_success(self, tmp_path):
        """重试在暂时连接错误后成功。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection reset by peer")
            mock_client.accumulated_text.append("Success after retry")
            return MagicMock(usage=None)

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent.time.sleep"):
            agent.step(conversation, on_event=events.append)

        assert call_count == 2
        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert len(events) == 2
        assert isinstance(events[0], ActionEvent)
        assert isinstance(events[0].action, FinishAction)
        assert "Success after retry" in events[0].action.message

    def test_no_retry_on_non_connection_error(self, tmp_path):
        """非连接错误会立即失败，没有重试。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Some application error")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with pytest.raises(RuntimeError, match="Some application error"):
            agent.step(conversation, on_event=events.append)

        assert call_count == 1
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_no_retry_on_timeout(self, tmp_path):
        """超时错误不会重试。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("ACP prompt timed out")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=lambda _: None)

        assert call_count == 1
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_max_retries_exceeded(self, tmp_path):
        """max 重试用尽后引发错误。"""
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent connection failure")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent.time.sleep"):
            with pytest.raises(ConnectionError, match="Persistent connection failure"):
                agent.step(conversation, on_event=events.append)

        assert call_count == 4
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_retry_on_acp_server_error_then_success(self, tmp_path):
        """重试在短暂的 ACP 服务器错误 (JSON-RPC -32603) 后成功。"""
        from acp.exceptions import RequestError as ACPRequestError

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ACPRequestError(-32603, "Internal Server Error")
            mock_client.accumulated_text.append("Success after server error retry")
            return MagicMock(usage=None)

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent.time.sleep"):
            agent.step(conversation, on_event=events.append)

        assert call_count == 2
        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        assert isinstance(events[0], ActionEvent)
        assert isinstance(events[0].action, FinishAction)
        assert "Success after server error retry" in events[0].action.message

    def test_no_retry_on_non_retriable_acp_error(self, tmp_path):
        """不可重试的 ACP 错误代码立即失败。"""
        from acp.exceptions import RequestError as ACPRequestError

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise ACPRequestError(-32600, "Invalid request")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with pytest.raises(ACPRequestError, match="Invalid request"):
            agent.step(conversation, on_event=events.append)

        assert call_count == 1  # 对于不可重试的错误代码，没有重试
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR

    def test_max_retries_exceeded_acp_server_error(self, tmp_path):
        """max 重试耗尽后出现 ACP 服务器错误。"""
        from acp.exceptions import RequestError as ACPRequestError

        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        call_count = 0

        def _fake_run_async(_coro, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise ACPRequestError(-32603, "Internal Server Error")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        with patch("openhands.sdk.agent.acp_agent.time.sleep"):
            with pytest.raises(ACPRequestError, match="Internal Server Error"):
                agent.step(conversation, on_event=events.append)

        # 默认最大值重试为 3，因此总共尝试 4 次
        assert call_count == 4
        assert conversation.state.execution_status == ConversationExecutionStatus.ERROR


# ---------------------------------------------------------------------------
# 双子座特定测试
# ---------------------------------------------------------------------------


class TestGeminiSessionModel:
    @pytest.mark.asyncio
    async def test_gemini_cli_uses_protocol_model_override(self):
        # gemini-CLI 保留 ``models`` 功能，因此模型选择会起作用
        # ``set_session_model`` (via_config_option=False).
        conn = AsyncMock()
        await _maybe_set_session_model(
            conn, "gemini-cli", "session-1", "gemini-3-flash", via_config_option=False
        )
        conn.set_session_model.assert_awaited_once_with(
            model_id="gemini-3-flash",
            session_id="session-1",
        )


# ---------------------------------------------------------------------------
# _extract_token_usage
# ---------------------------------------------------------------------------


class TestExtractTokenUsage:
    def test_from_response_usage(self):
        """claude-智能体-ACP，codex-ACP：标准 response.usage 字段。"""
        response = MagicMock()
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        response.usage.cached_read_tokens = 10
        response.usage.cached_write_tokens = 5
        response.usage.thought_tokens = 20
        assert _extract_token_usage(response) == (100, 50, 10, 5, 20)

    def test_from_field_meta_quota(self):
        """双子座-CLI：_meta.quota.token_count回退方案。"""
        response = MagicMock()
        response.usage = None
        response.field_meta = {
            "quota": {"token_count": {"input_tokens": 200, "output_tokens": 80}}
        }
        assert _extract_token_usage(response) == (200, 80, 0, 0, 0)

    def test_none_response(self):
        assert _extract_token_usage(None) == (0, 0, 0, 0, 0)

    def test_no_usage_no_meta(self):
        response = MagicMock()
        response.usage = None
        response.field_meta = None
        assert _extract_token_usage(response) == (0, 0, 0, 0, 0)

    def test_empty_quota(self):
        response = MagicMock()
        response.usage = None
        response.field_meta = {"quota": {}}
        assert _extract_token_usage(response) == (0, 0, 0, 0, 0)

    def test_missing_quota_token_count(self):
        response = MagicMock()
        response.usage = None
        response.field_meta = {"quota": {"token_count": None}}
        assert _extract_token_usage(response) == (0, 0, 0, 0, 0)


# ---------------------------------------------------------------------------
# _estimate_cost_from_tokens
# ---------------------------------------------------------------------------


class TestEstimateCostFromTokens:
    def test_unknown_model_returns_zero(self):
        assert _estimate_cost_from_tokens("nonexistent-model-xyz", 100, 50) == 0.0

    def test_zero_tokens_returns_zero(self):
        assert _estimate_cost_from_tokens("gemini-3-flash-preview", 0, 0) == 0.0

    def test_known_model_returns_positive(self):
        mock_cost_map = {
            "gemini-3-flash-preview": {
                "input_cost_per_token": 5e-07,
                "output_cost_per_token": 3e-06,
            }
        }
        mock_litellm = MagicMock()
        mock_litellm.model_cost = mock_cost_map
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            cost = _estimate_cost_from_tokens("gemini-3-flash-preview", 1000, 500)
            assert cost == pytest.approx(1000 * 5e-07 + 500 * 3e-06)

    def test_import_failure_returns_zero(self):
        with patch.dict("sys.modules", {"litellm": None}):
            assert (
                _estimate_cost_from_tokens("gemini-3-flash-preview", 1000, 500) == 0.0
            )


# ---------------------------------------------------------------------------
# _serialize_tool_content
# ---------------------------------------------------------------------------


class TestSerializeToolContent:
    def test_none_returns_none(self):
        assert _serialize_tool_content(None) is None

    def test_empty_list_returns_none(self):
        assert _serialize_tool_content([]) is None

    def test_pydantic_model(self):
        model = MagicMock()
        model.model_dump.return_value = {
            "type": "diff",
            "path": "a.py",
            "old_text": "x",
            "new_text": "y",
        }
        result = _serialize_tool_content([model])
        assert result == [
            {"type": "diff", "path": "a.py", "old_text": "x", "new_text": "y"}
        ]
        model.model_dump.assert_called_once_with(mode="json")

    def test_plain_dict_passthrough(self):
        d = {"type": "content", "text": "hello"}
        result = _serialize_tool_content([d])
        assert result == [d]

    def test_mixed_content(self):
        model = MagicMock()
        model.model_dump.return_value = {"type": "diff", "path": "b.py"}
        d = {"type": "content", "text": "world"}
        result = _serialize_tool_content([model, d])
        assert result == [{"type": "diff", "path": "b.py"}, d]


# ---------------------------------------------------------------------------
# ACP 通过 ConversationState.agent_state 恢复会话（问题 #2867）
# ---------------------------------------------------------------------------


class TestACPSessionIdPersistence:
    """验证 ACP 会话 ID 是否已保存在 ``state.agent_state`` 中
    第一次启动，_start_acp_server 在恢复时读取它以驱动 load_session 与 new_session.
    """

    @staticmethod
    def _transport_patches(conn):
        """上下文管理器堆叠传输层层模拟对象让
        _start_acp_server 运行时不会生成真正的子进程。
        """
        from contextlib import ExitStack

        mock_process = MagicMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        async def _fake_create_subprocess_exec(*_args, **_kwargs):
            return mock_process

        async def _fake_filter(_src, _dst):
            return None

        stack = ExitStack()
        stack.enter_context(
            patch(
                "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
                new=_fake_create_subprocess_exec,
            )
        )
        stack.enter_context(
            patch(
                "openhands.sdk.agent.acp_agent._ACPClientConnection",
                return_value=conn,
            )
        )
        stack.enter_context(
            patch(
                "openhands.sdk.agent.acp_agent._filter_jsonrpc_lines",
                new=_fake_filter,
            )
        )
        stack.enter_context(
            patch(
                "openhands.sdk.agent.acp_agent.asyncio.StreamReader",
                return_value=MagicMock(),
            )
        )
        return stack

    @staticmethod
    def _patched_start_acp_server(agent, state, *, conn):
        """使用 ACP 传输层层模拟的调用真实的 _start_acp_server。"""
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent._executor = AsyncExecutor()
        with TestACPSessionIdPersistence._transport_patches(conn):
            agent._start_acp_server(state)

    @staticmethod
    def _make_conn(
        *,
        new_session_id: str = "sess-new",
        load_exc: Exception | None = None,
    ):
        conn = MagicMock()

        init_response = MagicMock()
        init_response.agent_info = MagicMock()
        init_response.agent_info.name = "claude-agent-acp"
        init_response.agent_info.version = "1.0"
        init_response.auth_methods = []
        conn.initialize = AsyncMock(return_value=init_response)

        new_response = MagicMock()
        new_response.session_id = new_session_id
        conn.new_session = AsyncMock(return_value=new_response)

        if load_exc is not None:
            conn.load_session = AsyncMock(side_effect=load_exc)
        else:
            conn.load_session = AsyncMock(return_value=MagicMock())

        conn.set_session_mode = AsyncMock()
        conn.set_session_model = AsyncMock()
        conn.authenticate = AsyncMock()
        conn.close = AsyncMock()
        return conn

    def test_fresh_state_has_no_session_id(self, tmp_path):
        """新鲜的 ConversationState 在 agent_state 下不包含任何会话 ID。"""
        state = _make_state(tmp_path)
        assert "acp_session_id" not in state.agent_state

    def test_first_launch_calls_new_session(self, tmp_path):
        """空 agent_state → _start_acp_server 仅调用 new_session。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        conn = self._make_conn(new_session_id="fresh-sess")

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.new_session.assert_awaited_once()
        conn.load_session.assert_not_awaited()
        assert agent._session_id == "fresh-sess"

    @pytest.mark.parametrize("with_skills", [True, False])
    def test_skills_directory_is_shared_with_the_session(self, tmp_path, with_skills):
        context = (
            AgentContext(
                skills=[Skill(name="s", content="body", is_agentskills_format=True)]
            )
            if with_skills
            else None
        )
        agent = _make_agent().model_copy(update={"agent_context": context})
        state = _make_state(tmp_path)
        agent._materialize_skills(state)
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        extra = conn.new_session.await_args.kwargs["additional_directories"]
        assert extra == ([str(agent._skills_root)] if with_skills else None)

    def test_skills_directory_is_not_sent_when_the_server_lacks_the_capability(
        self, tmp_path
    ):
        agent = _make_agent().model_copy(
            update={
                "agent_context": AgentContext(
                    skills=[Skill(name="s", content="body", is_agentskills_format=True)]
                )
            }
        )
        state = _make_state(tmp_path)
        agent._materialize_skills(state)
        conn = self._make_conn()
        conn.initialize.return_value.agent_capabilities.session_capabilities = None

        self._patched_start_acp_server(agent, state, conn=conn)

        assert conn.new_session.await_args.kwargs["additional_directories"] is None

    def test_cancel_drain_restart_keeps_retry_flag_when_init_fails(self, tmp_path):
        """失败的替换会话应该使延迟重新启动处于待命状态。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        agent._restart_session_on_next_turn = True

        with patch.object(ACPAgent, "init_state", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                agent._restart_session_after_drain_timeout(
                    state, on_event=lambda _: None
                )

        assert agent._restart_session_on_next_turn is True

    def test_init_state_writes_session_id_into_agent_state(self, tmp_path):
        """init_state 将会话 ID 放入 state.agent_state 中，因此
        ConversationState 的 base_state.json 持久化将其向前推进。
        """
        agent = _make_agent()
        state = _make_state(tmp_path)

        # 短路 _start_acp_server：假装 ACP 握手运行并填充 init_state 之后读取的运行时属
        # 性。
        #
        def _fake_start(self, _state):
            self._session_id = "end-to-end-sess"
            self._agent_name = "claude-agent-acp"
            self._agent_version = "1.0"

        with patch.object(ACPAgent, "_start_acp_server", _fake_start):
            agent.init_state(state, on_event=lambda _: None)

        assert state.agent_state["acp_session_id"] == "end-to-end-sess"
        assert state.agent_state["acp_agent_name"] == "claude-agent-acp"
        assert state.agent_state["acp_agent_version"] == "1.0"

    def test_resume_reads_session_id_from_agent_state(self, tmp_path):
        """agent_state → load_session 中的先前会话 ID 被调用。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {**state.agent_state, "acp_session_id": "stored-sess"}
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        _, kwargs = conn.load_session.call_args
        assert kwargs["session_id"] == "stored-sess"
        assert kwargs["cwd"] == str(tmp_path)
        conn.new_session.assert_not_awaited()
        assert agent._session_id == "stored-sess"

    def test_cancel_drain_restart_preserves_session_id_for_resume(self, tmp_path):
        """已取消的提示词排水超时会重新启动子进程，但应该
        仍然加载已持久化 ACP 会话，以便服务器保留会话内存。
        """
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stored-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_suffix_installed": True,
        }
        conn = self._make_conn()

        with self._transport_patches(conn):
            agent._restart_session_after_drain_timeout(state, on_event=lambda _: None)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_not_awaited()
        assert agent._session_id == "stored-sess"
        assert state.agent_state["acp_session_id"] == "stored-sess"
        assert state.agent_state["acp_session_cwd"] == str(tmp_path)
        assert state.agent_state["acp_suffix_installed"] is True
        assert agent._suffix_install_state == "installed"

    def test_load_session_failure_falls_back_to_new_session(self, tmp_path):
        """ACPRequestError on load_session → new_session 是叫的。"""
        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {**state.agent_state, "acp_session_id": "stale-sess"}
        conn = self._make_conn(
            new_session_id="replacement-sess",
            load_exc=ACPRequestError(-32602, "unknown session"),
        )

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_awaited_once()
        assert agent._session_id == "replacement-sess"

    # ----- 显式 acp_resume_session_id （持久镜像覆盖）-----

    def test_acp_resume_session_id_drives_load_session_when_no_fs_state(self, tmp_path):
        """即使 ``agent_state`` 为空，``acp_resume_session_id`` 也会恢复。

        云沙箱在回收时丢失 ``base_state.json``，因此 FS-已持久化
        ``acp_session_id`` 不见了。 应用程序服务器将 ID 镜像到持久存储中，并通过
        ``acp_resume_session_id`` 将其传
        回 - 这仍应驱动 ``load_session``。
        """
        agent = _make_agent(acp_resume_session_id="externally-stored-sess")
        state = _make_state(tmp_path)
        assert "acp_session_id" not in state.agent_state
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        _, kwargs = conn.load_session.call_args
        assert kwargs["session_id"] == "externally-stored-sess"
        assert kwargs["cwd"] == str(tmp_path)
        conn.new_session.assert_not_awaited()
        assert agent._session_id == "externally-stored-sess"

    def test_acp_resume_session_id_overrides_fs_session_id(self, tmp_path):
        """当显式字段不同时，显式字段优先于 FS-已持久化 id。"""
        agent = _make_agent(acp_resume_session_id="durable-sess")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "fs-sess",
            "acp_session_cwd": str(tmp_path),
        }
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        _, kwargs = conn.load_session.call_args
        assert kwargs["session_id"] == "durable-sess"
        conn.new_session.assert_not_awaited()
        assert agent._session_id == "durable-sess"

    def test_mask_callback_does_not_retain_agent(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        conn = self._make_conn()
        self._patched_start_acp_server(agent, state, conn=conn)
        client = agent._client
        executor = agent._executor
        agent_ref = weakref.ref(agent)

        del agent
        gc.collect()

        deadline = time.monotonic() + 5
        while agent_ref() is not None and time.monotonic() < deadline:
            time.sleep(0.01)

        assert agent_ref() is None
        assert executor is not None
        assert executor._portal is None
        assert client is not None
        assert client.before_mask is not None
        assert client.before_mask() is None

    def test_acp_resume_session_id_failure_falls_back_to_new_session(self, tmp_path):
        """如果服务器无法加载显式 ID，则返回到 new_session。

        ACP服务器可能丢失了自己的会话存储（没有PVC，不同的主机......）； 通过中止而失
        败比重新开始更糟糕。 匹配现有的 ``load_session``
         故障路径。
        """
        agent = _make_agent(acp_resume_session_id="missing-sess")
        state = _make_state(tmp_path)
        conn = self._make_conn(
            new_session_id="replacement-sess",
            load_exc=ACPRequestError(-32602, "unknown session"),
        )

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_awaited_once()
        assert agent._session_id == "replacement-sess"

    def test_acp_resume_session_id_matches_fs_id_uses_fs_cwd(self, tmp_path):
        """当显式id等于FS id时，FS cwd被重用。

        当 agent_state 刚刚从相同的 id 中水合时，避免虚假的“从当前工作区推断 cwd”分支
        。
        """
        agent = _make_agent(acp_resume_session_id="same-sess")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "same-sess",
            "acp_session_cwd": str(tmp_path),
        }
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        _, kwargs = conn.load_session.call_args
        assert kwargs["session_id"] == "same-sess"

    def test_session_ids_redacted_in_resume_log_lines(self, tmp_path, caplog):
        """Resume / 回退方案日志行不得发出纯文本会话 ID。

        ACP 会话 ID 是承载者 token； 日志聚合器会保留行数周，因此它们本身就是一个序列
        化边界。 的
        ``_start_acp_server`` 日志行必须仅发出短后缀指纹，而不是完整 ID。
        """
        sensitive_explicit = "explicit-do-not-log-abc12345-LONGTAIL"
        sensitive_fs = "fs-session-do-not-log-OTHERTAIL"

        agent = _make_agent(acp_resume_session_id=sensitive_explicit)
        state = _make_state(tmp_path)
        state.agent_state = {**state.agent_state, "acp_session_id": sensitive_fs}
        conn = self._make_conn()
        with caplog.at_level("INFO"):
            self._patched_start_acp_server(agent, state, conn=conn)
        messages = "\n".join(rec.getMessage() for rec in caplog.records)
        assert sensitive_explicit not in messages
        assert sensitive_fs not in messages
        assert sensitive_explicit[-8:] in messages  # 存在指纹后缀

        caplog.clear()
        agent2 = _make_agent(acp_resume_session_id=sensitive_explicit)
        state2 = _make_state(tmp_path)
        conn2 = self._make_conn(
            new_session_id="replacement",
            load_exc=ACPRequestError(-32602, "unknown session"),
        )
        with caplog.at_level("WARNING"):
            self._patched_start_acp_server(agent2, state2, conn=conn2)
        fail_warnings = "\n".join(
            rec.getMessage()
            for rec in caplog.records
            if "load_session" in rec.getMessage()
        )
        assert sensitive_explicit not in fail_warnings

    def test_fingerprint_session_id_helper(self):
        """``_fingerprint_session_id`` 返回最后 8 个后缀，而不是完整 ID。"""
        from openhands.sdk.agent.acp_agent import _fingerprint_session_id

        assert _fingerprint_session_id(None) == "<none>"
        assert _fingerprint_session_id("short") == "<short>"
        assert _fingerprint_session_id("exactly8") == "<short>"
        long_sid = "a" * 24 + "12345678"
        out = _fingerprint_session_id(long_sid)
        assert long_sid not in out
        assert out.endswith("12345678")
        assert out.startswith("...")

    # ----- acp_resume_session_id 是线路上的承载机密 -----

    def test_acp_resume_session_id_redacted_by_default(self):
        """默认值序列化必须屏蔽 ``acp_resume_session_id``。"""
        sensitive = "super-secret-resume-id-do-not-leak"
        agent = _make_agent(acp_resume_session_id=sensitive)

        data_json = agent.model_dump_json()
        assert sensitive not in data_json, (
            f"plaintext id leaked into model_dump_json: {data_json}"
        )
        data = json.loads(data_json)
        assert data.get("acp_resume_session_id") == REDACTED_SECRET_VALUE

        py_dump = agent.model_dump()
        py_value = py_dump.get("acp_resume_session_id")
        assert sensitive not in repr(py_value)
        assert sensitive not in str(py_value)

    def test_acp_resume_session_id_none_serializes_as_none(self):
        """缺席不是机密 — ``None`` 必须像 ``null`` 一样往返。"""
        agent = _make_agent()
        data = json.loads(agent.model_dump_json())
        assert data.get("acp_resume_session_id") is None

    def test_acp_resume_session_id_redacted_sentinel_loads_as_none(self):
        """Default-已脱敏转储必须重新加载为 ``None``，而不是 ``'**********'``。

        如果没有匹配的验证器，默认转储的 ``model_validate_json`` 会将字段设置为文字哨
        兵值 — 调用
        ``session/load`` 服务器端失败，我们会回退到
        ``new_session`` 每次都击败了耐用镜子设计。
        """
        sensitive = "super-secret-resume-id-do-not-leak"
        agent = _make_agent(acp_resume_session_id=sensitive)
        reloaded = ACPAgent.model_validate_json(agent.model_dump_json())
        assert reloaded.acp_resume_session_id is None

    def test_acp_resume_session_id_plaintext_roundtrip(self):
        """明文转储（可信后端）逐字重新加载，无需密码。"""
        sensitive = "super-secret-resume-id-do-not-leak"
        agent = _make_agent(acp_resume_session_id=sensitive)
        exposed = agent.model_dump_json(context={"expose_secrets": "plaintext"})
        assert json.loads(exposed)["acp_resume_session_id"] == sensitive
        reloaded = ACPAgent.model_validate_json(exposed)
        assert reloaded.acp_resume_session_id == sensitive

    def test_acp_resume_session_id_encrypted_roundtrip(self):
        """上下文中的加密转储 + 密码解密回真实 ID。"""
        sensitive = "super-secret-resume-id-do-not-leak"
        agent = _make_agent(acp_resume_session_id=sensitive)
        cipher = Cipher(secret_key="test-cipher-secret-key-for-roundtrip-only")

        encrypted_json = agent.model_dump_json(
            context={"expose_secrets": "encrypted", "cipher": cipher}
        )
        assert sensitive not in encrypted_json

        reloaded = ACPAgent.model_validate_json(
            encrypted_json, context={"cipher": cipher}
        )
        assert reloaded.acp_resume_session_id == sensitive

    def test_session_id_not_on_serialized_agent(self):
        """会话 ID 不得泄漏到智能体模型上 — 它位于
        ConversationState.agent_state，不在冻结的ACPAgent。
        """
        agent = _make_agent()
        data = json.loads(agent.model_dump_json())
        assert "acp_session_id" not in data
        assert not hasattr(agent, "acp_session_id")

    def test_init_state_writes_cwd_alongside_session_id(self, tmp_path):
        """init_state 记录会话创建时使用的 cwd，以便稍后使用
        resume 可以拒绝 cwd 不匹配（cwd 的 ACP 键持久化）。
        """
        agent = _make_agent()
        state = _make_state(tmp_path)

        def _fake_start(self, _state):
            self._session_id = "sess-123"
            self._agent_name = "claude-agent-acp"
            self._agent_version = "1.0"
            self._working_dir = str(tmp_path)

        with patch.object(ACPAgent, "_start_acp_server", _fake_start):
            agent.init_state(state, on_event=lambda _: None)

        assert state.agent_state["acp_session_id"] == "sess-123"
        assert state.agent_state["acp_session_cwd"] == str(tmp_path)

    def test_cwd_mismatch_skips_load_and_calls_new_session(self, tmp_path, caplog):
        """如果存储的cwd与当前的工作区 cwd不同，则恢复
        被跳过并运行 new_session — 因此我们永远不会默默加载 ACP 服务器与不同目录关联
        的会话。
        """
        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "old-sess",
            "acp_session_cwd": "/some/other/place",
        }
        conn = self._make_conn(new_session_id="fresh-sess")

        with caplog.at_level("WARNING"):
            self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_not_awaited()
        conn.new_session.assert_awaited_once()
        assert agent._session_id == "fresh-sess"
        assert any(
            "cwd=/some/other/place" in rec.message and "differs" in rec.message
            for rec in caplog.records
        ), "expected a warning explaining the cwd mismatch"

    def test_resume_without_stored_cwd_still_works(self, tmp_path):
        """早期版本编写的遗留状态有 acp_session_id 但
        否 acp_session_cwd — 简历仍应继续（尽力而为）。
        """
        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {**state.agent_state, "acp_session_id": "legacy-sess"}
        conn = self._make_conn()

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_not_awaited()
        assert agent._session_id == "legacy-sess"

    def test_resume_preserves_persisted_model_when_load_session_omits_models(
        self, tmp_path
    ):
        """恢复时不得将已持久化 ``acp_current_model_*`` 留空
        ``load_session`` 不返回 ``models`` 字段。

        ``models``能力为UNSTABLE； 有些智能体仅将其附加到
        ``new_session`` 回复，而不是 ``load_session``。 以前
        ``init_state`` 无条件地用新提取的（可能是 ``None``）值覆盖 ``agent_state``，
        从而在每份简历上删除芯片。 契约是：只有
        当我们真正学到新东西时才更新模型状态。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "resumable-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "claude-opus-4-1",
            "acp_available_models": [
                {
                    "model_id": "claude-opus-4-1",
                    "name": "Opus 4.1",
                    "description": None,
                }
            ],
        }
        # ``load_session`` 返回一个不存在 ``models`` 字段的响应 — 与在恢复响应上不显示
        # UNSTABLE 功能的服务器的形状相同。
        #
        conn = self._make_conn()
        load_response = MagicMock(spec=[])  # spec=[] → no .models attribute
        conn.load_session = AsyncMock(return_value=load_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # 已持久化值在简历中保留下来，即使 load_session 没有重新报告它们。
        #
        assert state.agent_state["acp_current_model_id"] == "claude-opus-4-1"
        assert state.agent_state["acp_available_models"] == [
            {"model_id": "claude-opus-4-1", "name": "Opus 4.1", "description": None}
        ]

    def test_resume_with_forced_model_preserves_persisted_available_models(
        self, tmp_path
    ):
        """切换 ``acp_model`` 后继续，不得将已持久化留空
        ``acp_available_models``.

        Regression: ``current_model_id = self.acp_model or reported`` 变为
        即使 ``load_session`` 省略了 UNSTABLE ``models`` 块（因此
        ``_available_models`` 为空），强制
        ``acp_model`` 中的非 null 也是如此。 列表持久化必须在实际接收到列表时进行门控
        ，而不是在
        设置 ``current_model_id`` — 否则，切换对话的每个简历上的选择器载荷都会被擦除
        。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        # 先前的运行时切换使 ``model-b`` 成为权威模型。
        agent = _make_agent(acp_model="model-b")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "resumable-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "model-a",
            "acp_available_models": [
                {"model_id": "model-a", "name": "Model A", "description": None},
                {"model_id": "model-b", "name": "Model B", "description": None},
            ],
        }
        conn = self._make_conn()
        load_response = MagicMock(spec=[])  # 没有 .models 块
        conn.load_session = AsyncMock(return_value=load_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # current_model_id 反映了强制（切换）模型...
        assert state.agent_state["acp_current_model_id"] == "model-b"
        # ...but the previously persisted list is preserved, not clobbered.
        assert state.agent_state["acp_available_models"] == [
            {"model_id": "model-a", "name": "Model A", "description": None},
            {"model_id": "model-b", "name": "Model B", "description": None},
        ]

    def test_resume_with_explicit_empty_models_clears_stale_list(self, tmp_path):
        """在服务器 * 明确 * 报告 ``availableModels: []`` 的位置恢复
        必须 CLEAR 已持久化列表——而不是保留它。

        Regression: 真实的 ``if self._available_models`` 检查无法判断
        一个省略掉的 ``models`` 块（保留）从一个明确的空列表（清除）中，因此一个丢弃
        其模型的服务器在恢复后继续广播过时的筛选器选项。 ``None``（
        缺席）与 ``[]``（报告为空）与 ``_extract_session_models`` 的区别解决了这个问
        题。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "resumable-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "model-a",
            "acp_available_models": [
                {"model_id": "model-a", "name": "Model A", "description": None},
            ],
        }
        # load_session DOES 带有 ``models`` 块，但服务器现在不提供模型（显式空列表）。
        #
        conn = self._make_conn()
        load_response = MagicMock()
        load_response.models = MagicMock()
        load_response.models.current_model_id = ""
        load_response.models.available_models = []
        conn.load_session = AsyncMock(return_value=load_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # 过时列表被清除（用 [] 覆盖），而不是保留。
        assert state.agent_state["acp_available_models"] == []
        # ...and the stale current id is cleared in lock-step: the server
        # 报告了一个 ``models`` 个不可用的当前 id 的块，因此保留旧 id 会使指向上不存在的
        # 模型的芯片无效。
        #
        assert "acp_current_model_id" not in state.agent_state

    def test_resume_with_reported_models_but_no_current_clears_stale_id(self, tmp_path):
        """恢复服务器报告非空 ``availableModels`` 列表的位置
        但在采用新报告的列表时，可用的 ``currentModelId`` 必须 CLEAR 过时的已持久化当
        前 ID。

        这是非对称门控情况：报告 ``_available_models``（因此列表被覆盖），而
        ``_current_model_id`` 为 ``None``
        。 当前 id 必须遵循列表的“报告”信号，而不是默默地保留服务器不再声明的陈旧值。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "resumable-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "model-a",
            "acp_available_models": [
                {"model_id": "model-a", "name": "Model A", "description": None},
            ],
        }
        # load_session 包含一个模型块，列出模型，但没有当前选择 (e.g. 服务器清除其当前模
        # 型）。
        #
        conn = self._make_conn()
        load_response = MagicMock()
        load_response.models = MagicMock()
        load_response.models.current_model_id = ""
        model_x = MagicMock()
        model_x.model_id = "model-x"
        model_x.name = "Model X"
        model_x.description = None
        load_response.models.available_models = [model_x]
        conn.load_session = AsyncMock(return_value=load_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # 过时的当前 ID 已被删除（服务器报告 None）...
        assert "acp_current_model_id" not in state.agent_state
        # ...while the freshly reported picker list replaces the stale one.
        assert [m["model_id"] for m in state.agent_state["acp_available_models"]] == [
            "model-x"
        ]

    def test_resume_rejected_override_with_absent_models_clears_stale_id(
        self, tmp_path
    ):
        """恢复 ``set_session_model`` 被拒绝的位置 AND ``load_session``
        省略 ``models`` 块必须 CLEAR 过时的已持久化当前 ID。

        这是保留恢复规则的情况，否则会保留：
        ``truly_resumed`` 是 True，``_available_models`` 是 ``None``（服务器没有报告
        块），因此已持久化 id
        现在错误的唯一信号是我们尝试强制 ``acp_model``，但服务器拒绝了它（
        ``_model_override_applied`` 是 False）。
        被命名为拒绝覆盖的已持久化 id，因此它不再反映实时会话。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        # ``model-x``是上次发布的权威模型（已应用+已持久化）。
        agent = _make_agent(acp_model="model-x")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "resumable-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "model-x",
        }
        # load_session 成功（idserved => truly_resumed），但不携带模型块，服务器现在拒绝
        # 重新申请 ``model-x``。
        #
        conn = self._make_conn()
        conn.initialize.return_value.agent_info.name = "codex-acp"
        conn.initialize.return_value.auth_methods = []
        load_response = MagicMock(spec=[])  # 没有 .models 块
        conn.load_session = AsyncMock(return_value=load_response)
        conn.set_session_model = AsyncMock(
            side_effect=ACPRequestError(code=-32601, message="method not found")
        )

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # 简历保留相同的会话 ID（因此这是 True 简历）...
        assert state.agent_state["acp_session_id"] == "resumable-sess"
        # ...the override was not applied, so neither the live attr nor the
        # 已持久化提示可能声称 ``model-x``。
        assert agent.current_model_id is None
        assert agent._model_override_applied is False
        assert "acp_current_model_id" not in state.agent_state

    def test_fresh_replacement_clears_stale_model_when_new_session_omits_models(
        self, tmp_path
    ):
        """全新更换（load_session 失败 → new_session），无
        响应中的 ``models`` 块必须清除已持久化
        ``acp_current_model_*`` 而不是继承旧会话的价值观。

        否则，``acp_session_id`` 指向替换会话，而模型字段仍然描述失效的会话 -
        ``ConversationInfo`` 渲染错误的芯片。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stale-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_current_model_id": "claude-opus-4-1",
            "acp_available_models": [
                {"model_id": "claude-opus-4-1", "name": "Opus 4.1"}
            ],
        }
        # load_session 失败 → new_session 运行； 它的响应没有.models。
        new_session_response = MagicMock(spec=["session_id"])
        new_session_response.session_id = "replacement-sess"
        conn = self._make_conn(
            load_exc=ACPRequestError(-32602, "unknown session"),
        )
        conn.new_session = AsyncMock(return_value=new_session_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        # 替换 id 获胜，过时的模型字段消失了。
        assert state.agent_state["acp_session_id"] == "replacement-sess"
        assert "acp_current_model_id" not in state.agent_state
        assert "acp_available_models" not in state.agent_state

    def test_cwd_mismatch_clears_stale_model_when_new_session_omits_models(
        self, tmp_path
    ):
        """与 load_session-失败案例相同的合同，但通过
        ``_start_acp_server`` 中的 cwd-mismatch 分支（设置
        ``prior_session_id = None`` 在下降到 new_session 之前）。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "old-sess",
            "acp_session_cwd": "/some/other/place",
            "acp_current_model_id": "claude-opus-4-1",
            "acp_available_models": [
                {"model_id": "claude-opus-4-1", "name": "Opus 4.1"}
            ],
        }
        new_session_response = MagicMock(spec=["session_id"])
        new_session_response.session_id = "fresh-sess"
        conn = self._make_conn()
        conn.new_session = AsyncMock(return_value=new_session_response)

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        conn.load_session.assert_not_awaited()
        conn.new_session.assert_awaited_once()
        assert state.agent_state["acp_session_id"] == "fresh-sess"
        assert "acp_current_model_id" not in state.agent_state
        assert "acp_available_models" not in state.agent_state

    def test_fallback_replacement_id_lands_in_agent_state(self, tmp_path):
        """当 load_session 失败且 new_session 运行时，init_state 必须
        用新的 id 覆盖 state.agent_state['acp_session_id']，这样下次重新启动时就不会
        继续尝试恢复旧的 id。
        """
        from openhands.sdk.utils.async_executor import AsyncExecutor

        agent = _make_agent()
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stale-sess",
            "acp_session_cwd": str(tmp_path),
        }
        conn = self._make_conn(
            new_session_id="replacement-sess",
            load_exc=ACPRequestError(-32602, "unknown session"),
        )

        agent._executor = AsyncExecutor()
        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_awaited_once()
        assert state.agent_state["acp_session_id"] == "replacement-sess"
        assert state.agent_state["acp_session_cwd"] == str(tmp_path)

    def test_fallback_replacement_clears_suffix_marker(self, tmp_path):
        """如果 load_session 失败，则替换会话没有看到任何
        后缀，即使过时的会话具有已持久化标记。
        """
        agent = _make_agent(
            agent_context=AgentContext(system_message_suffix="Team rules.")
        )
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stale-sess",
            "acp_session_cwd": str(tmp_path),
            "acp_suffix_installed": True,
        }
        conn = self._make_conn(
            new_session_id="replacement-sess",
            load_exc=ACPRequestError(-32602, "unknown session"),
        )

        with self._transport_patches(conn):
            agent.init_state(state, on_event=lambda _: None)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_awaited_once()
        assert state.agent_state["acp_session_id"] == "replacement-sess"
        assert state.agent_state["acp_session_cwd"] == str(tmp_path)
        assert state.agent_state.get("acp_suffix_installed") is not True
        assert agent._suffix_install_state == "pending_first_prompt"

    def test_resume_path_still_applies_session_mode_and_model(self, tmp_path):
        """load_session 后面必须跟有相同的 set_session_model 和
        set_session_mode 调用为 new_session，因此恢复的会话将遵循 acp_model 覆盖和旁
        路权限模式。
        """
        agent = _make_agent(acp_model="claude-opus-4-6")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stored-sess",
            "acp_session_cwd": str(tmp_path),
        }
        # 维护的 Codex 适配器报告其作用域包名称； 提供商检测仍然通过
        # conn.set_session_model 路由 acp_model。
        #
        conn = self._make_conn()
        conn.initialize.return_value.agent_info.name = "@agentclientprotocol/codex-acp"
        conn.initialize.return_value.auth_methods = []

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        conn.new_session.assert_not_awaited()
        conn.set_session_model.assert_awaited_once_with(
            model_id="claude-opus-4-6",
            session_id="stored-sess",
        )
        conn.set_session_mode.assert_awaited_once_with(
            mode_id="agent-full-access",
            session_id="stored-sess",
        )

    @staticmethod
    def _models_block(current_model_id: str, model_ids: list[str]):
        """为分辨率测试构建响应 ``.models`` 块模拟对象。"""
        models = MagicMock()
        models.current_model_id = current_model_id
        entries = []
        for mid in model_ids:
            m = MagicMock()
            m.model_id = mid
            m.name = mid
            m.description = None
            entries.append(m)
        models.available_models = entries
        return models

    def test_unknown_provider_applies_override_via_detected_mechanism(self, tmp_path):
        """未知/自定义提供商的新会话设置为 ``acp_model``：
        覆盖是通过会话通告的机制推送的 - 这里是
        ``models``-能力响应，因此``set_session_model`` - 和
        ``current_model_id`` 必须反映所应用的覆盖。
        """
        agent = _make_agent(acp_model="caller-model")
        state = _make_state(tmp_path)
        new_response = MagicMock()
        new_response.session_id = "fresh-sess"
        new_response.models = self._models_block("server-model", ["server-model"])
        conn = self._make_conn()
        conn.set_config_option = AsyncMock()
        conn.initialize.return_value.agent_info.name = "some-custom-acp"
        conn.initialize.return_value.auth_methods = []
        conn.new_session = AsyncMock(return_value=new_response)

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.set_config_option.assert_not_awaited()
        conn.set_session_model.assert_awaited_once_with(
            model_id="caller-model", session_id="fresh-sess"
        )
        assert agent.current_model_id == "caller-model"

    def test_known_provider_surfaces_applied_override(self, tmp_path):
        """提供程序上的新会话通过以下方式应用覆盖
        协议调用（codex）：``current_model_id``反映了覆盖，因为它实际上被推送到服务器
        。 保护 QA 验证的优先级 - 修复不得倒退快乐的覆
        盖路径。
        """
        agent = _make_agent(acp_model="caller-model")
        state = _make_state(tmp_path)
        new_response = MagicMock()
        new_response.session_id = "fresh-sess"
        new_response.models = self._models_block("server-old", ["server-old"])
        conn = self._make_conn()
        conn.initialize.return_value.agent_info.name = "codex-acp"
        conn.initialize.return_value.auth_methods = []
        conn.new_session = AsyncMock(return_value=new_response)

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.set_session_model.assert_awaited_once_with(
            model_id="caller-model", session_id="fresh-sess"
        )
        assert agent.current_model_id == "caller-model"

    def test_resume_rejected_override_surfaces_server_model(self, tmp_path):
        """在 ``set_session_model`` 被拒绝的地方继续：实时会话保持
        服务器默认值，因此 ``current_model_id`` 必须回退到服务器在 ``load_session``
        上报告的内容，而不是声明覆盖。
        """
        agent = _make_agent(acp_model="caller-model")
        state = _make_state(tmp_path)
        state.agent_state = {
            **state.agent_state,
            "acp_session_id": "stored-sess",
            "acp_session_cwd": str(tmp_path),
        }
        load_response = MagicMock()
        load_response.models = self._models_block("server-resumed", ["server-resumed"])
        conn = self._make_conn()
        conn.initialize.return_value.agent_info.name = "codex-acp"
        conn.initialize.return_value.auth_methods = []
        conn.load_session = AsyncMock(return_value=load_response)
        # 服务器拒绝重新申请——被吞没，会话保留自己的模型。
        conn.set_session_model = AsyncMock(
            side_effect=ACPRequestError(code=-32601, message="method not found")
        )

        self._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        assert agent.current_model_id == "server-resumed"

    def test_roundtrip_via_conversation_state_persistence(self, tmp_path):
        """通过ConversationState持久化的端到端往返：

        1. 与 persistence_dir → init_state 的第一个对话运行，调用 new_session，写入
        ``state.agent_state["acp_session_id"]``，自动保存将 ``base_state.json`` 刷新
        到磁盘。
        2. 新鲜 ACPAgent + 会话指向同一个 persistence_dir 和 id →
        ConversationState.create() 重置
        ``base_state.json`` so ``agent_state["acp_session_id"]`` 生存； init_state 在
        恢复状态触
        发 ``load_session`` 使用该ID。
        """
        import uuid as _uuid

        from openhands.sdk.conversation import Conversation
        from openhands.sdk.utils.async_executor import AsyncExecutor

        persistence_dir = tmp_path / "persist"
        conv_id = _uuid.uuid4()
        workspace = tmp_path / "work"
        workspace.mkdir()

        conn1 = self._make_conn(new_session_id="roundtrip-sess")
        agent1 = _make_agent()
        agent1._executor = AsyncExecutor()
        with self._transport_patches(conn1):
            conv1 = Conversation(
                agent=agent1,
                workspace=str(workspace),
                persistence_dir=str(persistence_dir),
                conversation_id=conv_id,
                delete_on_close=False,
                visualizer=None,
            )
            conv1._ensure_agent_ready()
            assert conv1.state.agent_state["acp_session_id"] == "roundtrip-sess"
            conv1.close()

        conn1.new_session.assert_awaited_once()
        conn1.load_session.assert_not_awaited()

        # ACPAgent 无运行时知识，与先前会话无关。
        conn2 = self._make_conn()
        agent2 = _make_agent()
        agent2._executor = AsyncExecutor()
        with self._transport_patches(conn2):
            conv2 = Conversation(
                agent=agent2,
                workspace=str(workspace),
                persistence_dir=str(persistence_dir),
                conversation_id=conv_id,
                delete_on_close=True,
                visualizer=None,
            )
            conv2._ensure_agent_ready()
            # base_state.json 将 ID 恢复到 agent_state 中。
            assert conv2.state.agent_state["acp_session_id"] == "roundtrip-sess"
            conv2.close()

        # 第二次启动采用了 ID 为已持久化的 load_session 分支。
        conn2.load_session.assert_awaited_once()
        _, kwargs = conn2.load_session.call_args
        assert kwargs["session_id"] == "roundtrip-sess"
        assert kwargs["cwd"] == str(workspace)
        conn2.new_session.assert_not_awaited()
        assert agent2._session_id == "roundtrip-sess"

    def test_start_acp_server_bounds_a_hung_handshake_call(self, tmp_path):
        """握手期间挂起的 ACP 调用 (e.g. codex-ACP 阻塞
        authenticate() 内的 id_token 过期，#3629) 用于永久冻结 init_state()。
        acp_startup_timeout
        现在限制了整个 _init() 协程，并且生成的裸 TimeoutError（由 anyio.fail_after
        提出，没有消息）被转换为描述性的。
        """
        agent = _make_agent(acp_startup_timeout=0.05)
        state = _make_state(tmp_path)
        conn = self._make_conn()

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(10)

        conn.initialize = _hang

        with pytest.raises(TimeoutError, match="ACP startup timed out after 0s"):
            self._patched_start_acp_server(agent, state, conn=conn)

    def test_init_state_surfaces_startup_timeout(self, tmp_path):
        """转换后的 TimeoutError 作为类型到达客户端
        ACPStartupTimeout  ConversationErrorEvent不是通用的 ACPInitError, via the
        same
        init_state（冷启动路径）和其他分类失败一样。
        """
        agent = _make_agent(acp_startup_timeout=0.05)
        state = _make_state(tmp_path)
        conn = self._make_conn()

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(10)

        conn.initialize = _hang
        events: list = []

        with self._transport_patches(conn):
            with pytest.raises(TimeoutError):
                agent.init_state(state, on_event=events.append)

        errors = [e for e in events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1
        assert errors[0].code == "ACPStartupTimeout"
        assert "ACP startup timed out after 0s" in errors[0].detail
        assert state.execution_status == ConversationExecutionStatus.ERROR


class TestACPSecretsEnvInjection:
    """测试机密注入 ACP 子进程环境。

    通过 ``agent_context.secrets`` 传递的机密必须落在子进程环境中，以便 ACP 服务器（
    Claude Code、Codex CLI 等）可以
    使用它们。 它们通过 ``state.secret_registry`` 到达子进程：``LocalConversation``
    种子
    ``agent_context.secrets`` 在 init 处进入注册表（覆盖从未将它们提升到
    ``request.secrets`` 的调用者），并且
    ``_start_acp_server`` 注入注册表。
    """

    @staticmethod
    def _make_conn():
        conn = MagicMock()
        init_response = MagicMock()
        init_response.agent_info = MagicMock()
        init_response.agent_info.name = "claude-agent-acp"
        init_response.agent_info.version = "1.0"
        init_response.auth_methods = []
        conn.initialize = AsyncMock(return_value=init_response)
        new_response = MagicMock()
        new_response.session_id = "sess-1"
        conn.new_session = AsyncMock(return_value=new_response)
        conn.load_session = AsyncMock(return_value=MagicMock())
        conn.set_session_mode = AsyncMock()
        conn.set_session_model = AsyncMock()
        conn.authenticate = AsyncMock()
        conn.close = AsyncMock()
        return conn

    @staticmethod
    def _run_start_capturing_env(agent, tmp_path, *, state=None) -> dict:
        """运行 _start_acp_server 并返回传递给子进程的环境字典。

        传递 ``state`` 以对抗对话种子注册表 (e.g. 一个通过 ``LocalConversation`` 构建
        ，因此
        ``agent_context.secrets`` 被提升）； 否则使用裸状态。
        """
        from contextlib import ExitStack

        from openhands.sdk.utils.async_executor import AsyncExecutor

        captured: dict = {}
        conn = TestACPSecretsEnvInjection._make_conn()

        mock_process = MagicMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        async def _fake_create_subprocess_exec(*_args, env=None, **_kwargs):
            captured.update(env or {})
            return mock_process

        async def _fake_filter(_src, _dst):
            return None

        if state is None:
            state = _make_state(tmp_path)
        agent._executor = AsyncExecutor()

        with ExitStack() as stack:
            # e.g 包含跑者的环境。 一个真实的
            # GITHUB_TOKEN / ANTHROPIC_API_KEY) 因此它不能遮蔽测试下的注册表值 —
            # env.update(os.environ) 在 _start_acp_server 中的 fill-if-absent 注册表层之
            # 前运行。
            #
            stack.enter_context(patch.dict("os.environ", {}, clear=True))
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
                    new=_fake_create_subprocess_exec,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._ACPClientConnection",
                    return_value=conn,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._filter_jsonrpc_lines",
                    new=_fake_filter,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.StreamReader",
                    return_value=MagicMock(),
                )
            )
            agent._start_acp_server(state)

        return captured

    def test_static_secret_injected_into_subprocess_env(self, tmp_path):
        """agent_context.secrets 中的 StaticSecret 到达子进程环境。

        ``LocalConversation`` 种子 ``agent_context.secrets`` 进入
        ``state.secret_registry`` 在 init 处，``_start_acp_server`` 注入注册表 — 将
        ``agent_context.secrets`` 传递到 CLI 的路径，对于不通过以下方式将其提升到
        ``request.secrets`` 的调用者
        ``create_request`` (e.g. 画布本地）。
        """
        from pydantic import SecretStr

        from openhands.sdk.conversation.impl.local_conversation import (
            LocalConversation,
        )
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={
                    "GITHUB_TOKEN": StaticSecret(
                        value=SecretStr("ghp_test123"),
                        description="GitHub token",
                    )
                }
            )
        )
        conv = LocalConversation(agent, workspace=str(tmp_path))
        try:
            env = self._run_start_capturing_env(agent, tmp_path, state=conv.state)
        finally:
            conv.close()
        assert env.get("GITHUB_TOKEN") == "ghp_test123"

    def test_none_value_secret_not_injected(self, tmp_path):
        """value=None 的 StaticSecret 不会添加到子进程环境中。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={"ABSENT_SECRET": StaticSecret(value=None)}
            )
        )
        env = self._run_start_capturing_env(agent, tmp_path)
        assert "ABSENT_SECRET" not in env

    def test_empty_string_secret_not_injected(self, tmp_path):
        """空字符串机密不会注入到子进程环境中。"""
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={"EMPTY_SECRET": StaticSecret(value=SecretStr(""))}
            )
        )
        env = self._run_start_capturing_env(agent, tmp_path)
        assert "EMPTY_SECRET" not in env


class _BrokenSecret(SecretSource):
    """``get_value()`` 引发的源，用于验证失败的查找是
    被视为“跳过”而不是删除子进程。"""

    def get_value(self) -> str | None:
        raise OSError("network down")


class TestACPSecretRegistryEnvInjection:
    """测试来自对话的 secret_registry 的机密注入。

    机密注册的 ``Conversation.update_secrets()`` — 或者等效的 ``payload.secrets`` 应
    用程序服务器调用者（智能体
    -canvas, the OpenHands 云应用服务器) 必须位于  ACP  子进程 env.
    ``agent_context.secrets`` 被种在同一
    组中注册表 at ``LocalConversation.__init__`` (以下) ``request.secrets``, 所以注册
    表这是一个单一的渠道
    ``_start_acp_server`` 注入。

    相同键优先级为 ``secret_registry > os.environ``。 注册表机密覆盖环境
    ``os.environ``，因此显式的每个会话/提供者机密
    胜过同名服务器环境变量。
    """

    @staticmethod
    def _run_start_capturing_env(
        agent, tmp_path, *, registry_secrets=None, extra_os_env=None, state=None
    ) -> dict:
        """重新使用 TestACPSecretsEnvInjection 中的环境捕获工具。

        传递 ``state`` 以对抗对话种子注册表 (e.g. 一个通过 ``LocalConversation`` 构建
        ，因此
        ``agent_context.secrets`` 被提升）； 否则使用裸状态并直接应用
        ``registry_secrets``。
        """
        if state is None:
            state = _make_state(tmp_path)
        if registry_secrets:
            state.secret_registry.update_secrets(registry_secrets)

        from contextlib import ExitStack

        from openhands.sdk.utils.async_executor import AsyncExecutor

        captured: dict = {}
        conn = TestACPSecretsEnvInjection._make_conn()

        mock_process = MagicMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        async def _fake_create_subprocess_exec(*_args, env=None, **_kwargs):
            captured.update(env or {})
            return mock_process

        async def _fake_filter(_src, _dst):
            return None

        agent._executor = AsyncExecutor()

        with ExitStack() as stack:
            # Hermetic：将跑步者的环境环境替换为 extra_os_env （或
            # 什么都没有），所以它不能隐藏测试中的注册表值，因此测试可以注入受控的环境变
            # 量来断言优先级。
            #
            stack.enter_context(
                patch.dict("os.environ", extra_os_env or {}, clear=True)
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
                    new=_fake_create_subprocess_exec,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._ACPClientConnection",
                    return_value=conn,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._filter_jsonrpc_lines",
                    new=_fake_filter,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.StreamReader",
                    return_value=MagicMock(),
                )
            )
            agent._start_acp_server(state)

        return captured

    def test_registry_string_secret_injected_into_subprocess_env(self, tmp_path):
        """secret_registry 中的字符串机密落在子进程环境中。

        canvas / OpenHands ``payload.secrets`` 通道通过
        ``Conversation.update_secrets()``
        → ``SecretRegistry.update_secrets`` 到达这里； 如果没有这种注入，机密对 ACP
        CLI 是不可见的。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"ANTHROPIC_API_KEY": "sk-from-registry"},
        )
        assert env.get("ANTHROPIC_API_KEY") == "sk-from-registry"

    def test_registry_lookup_secret_injected_into_subprocess_env(self, tmp_path):
        """secret_registry 中的 LookupSecret（可调用）解析并注入。

        这是线形画布实际发送的：一个 ``LookupSecret``，其 ``get_value()`` 从智能体服
        务器的 HTTP 获取
        ``/api/settings/secrets/{name}`` 端点。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={
                "OPENAI_API_KEY": _FakeLookupSecret(stored_value="sk-fake-openai")
            },
        )
        assert env.get("OPENAI_API_KEY") == "sk-fake-openai"

    def test_request_secret_wins_and_context_only_secret_still_reaches_env(
        self, tmp_path
    ):
        """request.secrets 碰撞获胜； 仅上下文的密钥仍然到达 env。

        两个通道首先流经 ``state.secret_registry``：``LocalConversation`` 种子
        ``agent_context.secrets``，然后 ``request.secrets`` 覆盖冲突键。 仅在
        ``agent_context.secrets`` 中存在的密钥仍然落在注册表中 - 因此子进程环境中 -
        证明两个通道共存而不会丢失另一个通道。
        """
        from pydantic import SecretStr

        from openhands.sdk.conversation.impl.local_conversation import (
            LocalConversation,
        )
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={
                    "GITHUB_TOKEN": StaticSecret(value=SecretStr("from-context")),
                    "CONTEXT_ONLY": StaticSecret(value=SecretStr("ctx-value")),
                }
            )
        )
        conv = LocalConversation(
            agent,
            workspace=str(tmp_path),
            secrets={"GITHUB_TOKEN": StaticSecret(value=SecretStr("from-request"))},
        )
        try:
            env = self._run_start_capturing_env(agent, tmp_path, state=conv.state)
        finally:
            conv.close()
        assert env.get("GITHUB_TOKEN") == "from-request"
        assert env.get("CONTEXT_ONLY") == "ctx-value"

    def test_empty_registry_does_not_change_behaviour(self, tmp_path):
        """空的 secret_registry 不得引发或改变生成环境。"""
        agent = _make_agent()
        env = self._run_start_capturing_env(agent, tmp_path, registry_secrets=None)
        # 没有机密可注入。 spawn 仍然成功并生成一个 env 字典。
        assert isinstance(env, dict)

    def test_failing_registry_lookup_swallowed(self, tmp_path):
        """引发的机密源将被丢弃，而不是传播。

        ``SecretRegistry.get_secret_value`` 已经捕获查找错误并返回 ``None``； spawn-
        env 循环必须将那个
        ``None`` 看作“跳过”，这样就不会因为机密的临时源失败（网络断开、过期 token）而
        将整个 ACP 子进程拒绝。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"BROKEN": _BrokenSecret()},
        )
        assert "BROKEN" not in env

    def test_registry_secret_overrides_ambient_os_environ(self, tmp_path):
        """注册表机密覆盖同名的环境 os.environ 变量。

        对话/提供者信用必须赢得智能体服务器自己的环境（os.environ 对于远程服务器来说
        是错误的进程）。 在这次改变之前，环境值悄然获胜。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"ANTHROPIC_API_KEY": "from-registry"},
            extra_os_env={"ANTHROPIC_API_KEY": "ambient-should-lose"},
        )
        assert env.get("ANTHROPIC_API_KEY") == "from-registry"

    def test_agent_context_secret_overrides_ambient_os_environ(self, tmp_path):
        """agent_context 机密（播种到注册表中）击败环境 os.environ。

        ``LocalConversation`` 将 ``agent_context.secrets`` 提升到注册表，并且注册表机
        密覆盖智能体服务器自己的
        ``os.environ``，因此每个会话/提供者机密胜过同名服务器环境变量。
        """
        from pydantic import SecretStr

        from openhands.sdk.conversation.impl.local_conversation import (
            LocalConversation,
        )
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={"GITHUB_TOKEN": StaticSecret(value=SecretStr("from-context"))}
            )
        )
        conv = LocalConversation(agent, workspace=str(tmp_path))
        try:
            env = self._run_start_capturing_env(
                agent,
                tmp_path,
                extra_os_env={"GITHUB_TOKEN": "ambient-should-lose"},
                state=conv.state,
            )
        finally:
            conv.close()
        assert env.get("GITHUB_TOKEN") == "from-context"


class TestACPEnvConflictSuppression:
    """活动的 CLAUDE_CODE_OAUTH_TOKEN 不得与 API-key 环境变量共存。

    当 CLAUDE_CODE_OAUTH_TOKEN 存在时，子进程会根据 api.anthropic.com 对该承载者进行
    身份验证。
    ANTHROPIC_API_KEY 会优先处理（绕过订阅），而 ANTHROPIC_BASE_URL 会将承载路由到一
    个拒绝它的代理，从而无声地破坏认证。

    _start_acp_server 必须删除冲突的变量，无论它们来自哪里：os.environ、
    secret_registry 或
    agent_context.secrets。 该条带键控在 token 上，而不是 CLAUDE_CONFIG_DIR (#3588)。
    """

    @staticmethod
    def _make_conn():
        conn = MagicMock()
        init_response = MagicMock()
        init_response.agent_info = MagicMock()
        init_response.agent_info.name = "claude-agent-acp"
        init_response.agent_info.version = "1.0"
        init_response.auth_methods = []
        conn.initialize = AsyncMock(return_value=init_response)
        new_response = MagicMock()
        new_response.session_id = "sess-conflict"
        conn.new_session = AsyncMock(return_value=new_response)
        conn.load_session = AsyncMock(return_value=MagicMock())
        conn.set_session_mode = AsyncMock()
        conn.set_session_model = AsyncMock()
        conn.authenticate = AsyncMock()
        conn.close = AsyncMock()
        return conn

    @staticmethod
    def _run_start_capturing_env(
        agent, tmp_path, *, extra_os_env=None, registry_secrets=None
    ) -> dict:
        from contextlib import ExitStack

        from openhands.sdk.utils.async_executor import AsyncExecutor

        captured: dict = {}
        conn = TestACPEnvConflictSuppression._make_conn()

        mock_process = MagicMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        async def _fake_create_subprocess_exec(*_args, env=None, **_kwargs):
            captured.update(env or {})
            return mock_process

        async def _fake_filter(_src, _dst):
            return None

        state = _make_state(tmp_path)
        if registry_secrets:
            state.secret_registry.update_secrets(registry_secrets)
        agent._executor = AsyncExecutor()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
                    new=_fake_create_subprocess_exec,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._ACPClientConnection",
                    return_value=conn,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._filter_jsonrpc_lines",
                    new=_fake_filter,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.StreamReader",
                    return_value=MagicMock(),
                )
            )
            # Hermetic：清除跑步者的环境环境，使其无法遮蔽
            # 测试值； extra_os_env 是唯一的 os.environ 内容（由通过 os.environ 注入
            # ANTHROPIC_API_KEY 的测试使用）。
            #
            stack.enter_context(
                patch.dict("os.environ", extra_os_env or {}, clear=True)
            )
            agent._start_acp_server(state)

        return captured

    def test_oauth_token_suppresses_api_key_from_os_environ(self, tmp_path):
        """从 os.environ 泄漏的 ANTHROPIC_API_KEY 也被剥离。"""
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok"},
            extra_os_env={
                "ANTHROPIC_API_KEY": "sk-leaked",
                "ANTHROPIC_BASE_URL": "https://proxy.example.com",
            },
        )

        assert "CLAUDE_CODE_OAUTH_TOKEN" in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "ANTHROPIC_BASE_URL" not in env

    def test_oauth_token_suppresses_api_key_from_registry(self, tmp_path):
        """token + 冲突的变量全部通过 secret_registry 注入。

        这是渠道提供商的信用现在传播（折叠成
        ``agent_context.secrets`` 乘 ``create_agent`` → 提升到注册表乘
        ``create_request``）。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={
                "CLAUDE_CODE_OAUTH_TOKEN": "oauth-from-registry",
                "ANTHROPIC_API_KEY": "sk-from-registry",
                "ANTHROPIC_BASE_URL": "https://proxy.example.com",
            },
        )

        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-from-registry"
        assert "ANTHROPIC_API_KEY" not in env
        assert "ANTHROPIC_BASE_URL" not in env

    def test_oauth_token_suppresses_api_key_from_secrets(self, tmp_path):
        """从 agent_context.secrets 中排出的冲突变量也被删除。

        覆盖画布本地渠道：提供商信用纳入
        ``agent_context.secrets`` 通过排水到达 env，并且当 OAuth token 处于活动状态时
        仍必须被剥离。
        """
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                secrets={
                    "ANTHROPIC_API_KEY": StaticSecret(
                        value=SecretStr("sk-from-secret")
                    ),
                    "ANTHROPIC_BASE_URL": StaticSecret(
                        value=SecretStr("https://proxy.example.com")
                    ),
                }
            ),
        )
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok"},
        )

        assert "CLAUDE_CODE_OAUTH_TOKEN" in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "ANTHROPIC_BASE_URL" not in env

    def test_no_suppression_without_oauth_token(self, tmp_path):
        """如果没有 OAuth token，ANTHROPIC_API_KEY 会保持不变。"""
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={"ANTHROPIC_API_KEY": "sk-valid"},
        )

        assert env.get("ANTHROPIC_API_KEY") == "sk-valid"
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in env

    def test_config_dir_alone_does_not_suppress_api_key(self, tmp_path):
        """Regression (#3588): CLAUDE_CONFIG_DIR 没有 OAuth token 必须不
        剥离ANTHROPIC_API_KEY。 配置目录是一个隔离数据目录的开关（认证模式），与授权
        模式无关——在隔离期间使用它来删除一个工作 API 的密钥。
        """
        agent = _make_agent()
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={
                "CLAUDE_CONFIG_DIR": "/tmp/claude-isolated",
                "ANTHROPIC_API_KEY": "sk-valid",
            },
        )

        assert env["CLAUDE_CONFIG_DIR"] == "/tmp/claude-isolated"
        assert env.get("ANTHROPIC_API_KEY") == "sk-valid"

    def test_rule_does_not_reach_another_provider(self, tmp_path):
        """未声明冲突的提供者保留该变量。

        规则属于claude-code，但用于每个提供者运行的循环已被删除ANTHROPIC_API_KEY，任
        何ACP 子进程的token。 对于拥有自己的
        ``api_key_env_var``是ANTHROPIC_API_KEY，这是它唯一的凭据。
        """
        agent = _make_agent(acp_server="gemini-cli")
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={
                "CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok",
                "ANTHROPIC_API_KEY": "sk-this-providers-credential",
            },
        )

        assert env.get("ANTHROPIC_API_KEY") == "sk-this-providers-credential"

    def test_claude_code_key_still_applies_the_rule(self, tmp_path):
        """声明提供者不受范围的影响。"""
        agent = _make_agent(acp_server="claude-code")
        env = self._run_start_capturing_env(
            agent,
            tmp_path,
            registry_secrets={
                "CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok",
                "ANTHROPIC_API_KEY": "sk-leaked",
            },
        )

        assert "ANTHROPIC_API_KEY" not in env


class TestACPAgentCurrentModelIdProperty:
    """``current_model_id`` 是由 PrivateAttr 支持的只读属性。

    ``AgentBase`` 被冻结，因此该值不能作为常规 Pydantic 字段存在于智能体中； 它也不通
    过 ``model_dump`` 往返。 跨进程消费者（
    OpenHands app_server）应该从 ``ConversationInfo`` 中读取它 - 智能体服务器将智能体
    中的值提升到 API 响应中。
    """

    def test_defaults_to_none(self):
        agent = _make_agent()
        assert agent.current_model_id is None

    def test_reflects_private_attr(self):
        # ``_init`` 在咨询服务器响应 + 调用者覆盖后将解析的模型写入
        # ``_current_model_id``。
        #
        agent = _make_agent()
        agent._current_model_id = "claude-sonnet-4-5"
        assert agent.current_model_id == "claude-sonnet-4-5"

    def test_acp_model_override_wins_over_server_report(self):
        """设置 ``acp_model`` 时，``current_model_id`` 反映覆盖。

        镜像 ``_init`` 中的解析逻辑：调用者提供
        ``acp_model`` 优先于服务器报告的任何内容，无论应用哪种协议模型选择机制。
        """
        agent = _make_agent(acp_model="gpt-5")
        agent._current_model_id = agent.acp_model or "fallback-from-server"
        assert agent.current_model_id == "gpt-5"

    def test_does_not_round_trip_through_json(self):
        # 锁在刻意的设计选择中：PrivateAttr→不是已序列化。 跨进程消费者必须从
        # ``ConversationInfo``读取。
        #
        agent = _make_agent()
        agent._current_model_id = "claude-opus-4-1"
        clone = ACPAgent.model_validate_json(agent.model_dump_json())
        assert clone.current_model_id is None


class TestExtractSessionModels:
    """``_extract_session_models`` 读取 ACP 服务器报告的模型。

    ``models`` 功能在规范中标记为 UNSTABLE。 第二个元素将 **absent**（``None`` — 块丢
    失）与
    **present-but-empty**（``[]`` - 服务器报告没有模型），其中
    resume-持久化逻辑依赖于保存 vs. 清除已存储的列表。
    """

    def test_returns_both_when_response_carries_them(self):
        m1 = MagicMock()
        m1.model_id = "default"
        m1.name = "Default (recommended)"
        m1.description = "Opus 4.7 with 1M context · Most capable"
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = "default"
        response.models.available_models = [m1]
        cur, avail, _ = _extract_session_models(response)
        assert cur == "default"
        # 标准化为我们的稳定版本 ACPModelInfo，而不是原始 ACP 类型。
        assert avail == [
            ACPModelInfo(
                model_id="default",
                name="Default (recommended)",
                description="Opus 4.7 with 1M context · Most capable",
            )
        ]

    def test_returns_none_list_when_models_block_absent(self):
        # 较旧的智能体根本不包含 ``models`` 块 -> None，因此调用者知道没有报告任何内容（
        # 并且可以保留先前的状态）。
        #
        response = MagicMock(spec=[])
        cur, avail, _ = _extract_session_models(response)
        assert cur is None
        assert avail is None

    def test_returns_empty_list_when_available_models_missing(self):
        # ``models`` 块存在，但 ``availableModels`` 不存在/无：报告的块 WAS，因此我们返
        # 回 ``[]``（存在，无模型），而不是 None。
        #
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = "gpt-5"
        response.models.available_models = None
        cur, avail, _ = _extract_session_models(response)
        assert cur == "gpt-5"
        assert avail == []

    def test_returns_none_list_when_response_is_none(self):
        # 对于不实现调用的服务器，``load_session`` 可以返回 ``None`` — 帮助程序不得崩溃
        # ，并报告“缺席”。
        #
        assert _extract_session_models(None) == (None, None, False)

    def test_returns_none_list_when_models_field_is_none(self):
        response = MagicMock()
        response.models = None
        assert _extract_session_models(response) == (None, None, False)

    def test_returns_none_when_current_model_id_is_empty_string(self):
        # 空字符串被视为与缺失字段相同 - 我们不想将“”显示为真实的模型名称。 该块存在，因
        # 此 available_models 是 []（而不是 None）。
        #
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = ""
        response.models.available_models = []
        assert _extract_session_models(response) == (None, [], False)

    def test_returns_none_when_current_model_id_is_not_a_string(self):
        # 防御性：这里返回非字符串的智能体格式错误。
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = 42
        response.models.available_models = []
        assert _extract_session_models(response) == (None, [], False)


class TestExtractSessionModelsNormalization:
    """``_extract_session_models`` 标准化原始数据 ACP entries to ACPModelInfo.

    SDK 有意地将 UNSTABLE ``acp.schema`` ``ModelInfo`` 重映射为我们的稳定类型，在边界
    处容忍部分/畸形输入，而不是泄露供应商形
    状或抛出异常。
    """

    def _raw(self, model_id: Any, name: Any = None, description: Any = None) -> Any:
        m = MagicMock()
        m.model_id = model_id
        m.name = name
        m.description = description
        return m

    def test_maps_fields_through(self):
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = "gpt-5.4"
        response.models.available_models = [
            self._raw("gpt-5.4", "GPT-5.4", "Strong everyday model."),
        ]
        _cur, avail, _ = _extract_session_models(response)
        assert avail == [
            ACPModelInfo(
                model_id="gpt-5.4",
                name="GPT-5.4",
                description="Strong everyday model.",
            )
        ]

    def test_drops_entries_without_usable_id(self):
        # 一个畸形的条目（缺少或非字符串的id）必须不会导致会话启动失败，也不会显示为空id
        # 选择器选项——它被丢弃，而与之一起存在的有效条目则存活。
        #
        response = MagicMock()
        response.models = MagicMock()
        response.models.current_model_id = "good"
        response.models.available_models = [
            self._raw(model_id=42),  # 非字符串 -> "" -> 删除
            self._raw(model_id="good", name="Good"),
            self._raw(model_id="", name="Empty"),  # 空 -> 丢弃
        ]
        _cur, avail, _ = _extract_session_models(response)
        assert avail == [ACPModelInfo(model_id="good", name="Good", description=None)]


class TestConfigOptionModelMechanism:
    """通过 ``model`` ``configOptions`` 选择来选择型号。

    当前的 codex-ACP 和 claude-智能体-ACP 公开了由 ``session/set_config_option`` 驱动
    的 ``model`` 配置
    选项选择。 ``_extract_session_models`` 读取该选择并将应用机制报告为同一扫描中的第
    三个返回值 (
    ``via_config_option``)。
    """

    def _select(self, *, id="model", type="select", current_value, options):
        opt = SimpleNamespace(
            id=id, type=type, current_value=current_value, options=options
        )
        return opt

    def _opt(self, value, name=None, description=None):
        return SimpleNamespace(value=value, name=name, description=description)

    def _response(self, *, models=None, config_options):
        return SimpleNamespace(models=models, config_options=config_options)

    def test_extracts_model_state_from_config_option(self):
        # claude-智能体-ACP 0.44：使用短别名选择模型。
        response = self._response(
            config_options=[
                self._select(
                    current_value="opus[1m]",
                    options=[
                        self._opt("default", "Default (recommended)", "Opus 4.8 · 1M"),
                        self._opt("opus[1m]", "Opus", "Opus 4.8 · 1M"),
                        self._opt("sonnet", "Sonnet", "Sonnet 4.6"),
                        self._opt("haiku", "Haiku", "Haiku 4.5"),
                    ],
                )
            ],
        )
        cur, avail, via = _extract_session_models(response)
        assert cur == "opus[1m]"
        assert via is True
        assert avail == [
            ACPModelInfo(
                model_id="default",
                name="Default (recommended)",
                description="Opus 4.8 · 1M",
            ),
            ACPModelInfo(model_id="opus[1m]", name="Opus", description="Opus 4.8 · 1M"),
            ACPModelInfo(model_id="sonnet", name="Sonnet", description="Sonnet 4.6"),
            ACPModelInfo(model_id="haiku", name="Haiku", description="Haiku 4.5"),
        ]

    def test_unwraps_rootmodel_wrapped_config_option(self):
        # 智能体-client-protocol 0.8.x 将每个条目包装在 SessionConfigOption RootModel 中
        # （该选项位于 ``.root`` 下）； 检测必须将其打开，
        #
        # else ``opt.id`` is None and the SDK wrongly falls back to set_model.
        select = self._select(
            current_value="opus[1m]",
            options=[self._opt("opus[1m]", "Opus"), self._opt("sonnet", "Sonnet")],
        )
        wrapped = SimpleNamespace(root=select)  # 模仿 RootModel 包装器
        response = self._response(config_options=[wrapped])
        cur, avail, via = _extract_session_models(response)
        assert via is True
        assert cur == "opus[1m]"
        assert avail is not None
        assert [m.model_id for m in avail] == ["opus[1m]", "sonnet"]

    def test_config_option_wins_over_models_capability(self):
        # 当前的 codex-ACP 包含两者； 使用标准配置选项路径。
        models = MagicMock()
        models.current_model_id = "from-models"
        models.available_models = []
        response = self._response(
            models=models,
            config_options=[
                self._select(
                    current_value="from-config", options=[self._opt("from-config", "X")]
                )
            ],
        )
        cur, avail, via = _extract_session_models(response)
        assert cur == "from-config"
        assert avail == [
            ACPModelInfo(model_id="from-config", name="X", description=None)
        ]
        assert via is True

    def test_detects_config_option_mechanism(self):
        response = self._response(
            config_options=[
                self._select(
                    current_value="gpt-5.5", options=[self._opt("gpt-5.5", "GPT-5.5")]
                )
            ],
        )
        assert _extract_session_models(response)[2] is True

    def test_ignores_non_model_config_options(self):
        # ``mode`` 选择和``model`` 选择都没有 ⇒ 旧机制，且默认值(False)被报告，因为没有
        # 块。
        #
        response = self._response(
            config_options=[
                SimpleNamespace(
                    id="mode",
                    type="select",
                    current_value="default",
                    options=[self._opt("default", "Default")],
                ),
            ],
        )
        assert _extract_session_models(response) == (None, None, False)

    def test_drops_options_without_usable_value(self):
        response = self._response(
            config_options=[
                self._select(
                    current_value="ok",
                    options=[
                        self._opt(value=42),  # 非字符串 -> 被丢弃
                        self._opt("ok", "Ok"),
                        self._opt(value="", name="Empty"),  # 空 -> 丢弃
                    ],
                )
            ],
        )
        cur, avail, _ = _extract_session_models(response)
        assert cur == "ok"
        assert avail == [ACPModelInfo(model_id="ok", name="Ok", description=None)]

    def test_none_response_is_not_config_option(self):
        assert _extract_session_models(None)[2] is False

    def test_default_via_config_option_used_when_no_block_present(self):
        # 在恢复时 load_session 必须不盲目的默认掉模型的能力和配置选项 set_session_model
        # : 调用者传递了已持久化机制提示，已认可 (#3772)。
        #
        response = self._response(config_options=[])
        assert _extract_session_models(response)[2] is False
        assert (
            _extract_session_models(response, default_via_config_option=True)[2] is True
        )
        # 当前的块仍然胜过提示。
        present = self._response(
            config_options=[
                self._select(current_value="x", options=[self._opt("x", "X")])
            ]
        )
        assert (
            _extract_session_models(present, default_via_config_option=False)[2] is True
        )


# 从挂载的CLIs中捕获了实``session/new``的别名载荷。 通过真实的 ``NewSessionResponse`` 进
# 行解析，因此测试会测试真实的模式、INCLUDING、``SessionConfigOption``、RootModel 包
# ``agent-client-protocol`` lib 适用于 0.8.x 上的 ``config_options``（其中简单的
# ``opt.id`` 读取返回 ``None``）。 检测助手打开
# ``.root`` 所以它适用于 0.8.x + 0.10.x。
def _select_dict(opt_id, current, values, category=None):
    return {
        "id": opt_id,
        "name": opt_id,
        "type": "select",
        "category": category,
        "currentValue": current,
        "options": [{"value": v, "name": v} for v in values],
    }


_CLAUDE_046_SESSION = {
    "sessionId": "sess-claude",
    "models": None,
    "configOptions": [
        _select_dict("mode", "default", ["default", "acceptEdits"]),
        _select_dict(
            "model",
            "opus[1m]",
            ["default", "opus[1m]", "sonnet", "haiku"],
            category="model",
        ),
        _select_dict("effort", "xhigh", ["xhigh", "low"]),
    ],
}
_CODEX_112_SESSION = {
    "sessionId": "sess-codex",
    "models": {
        "currentModelId": "gpt-5.6-sol[xhigh]",
        "availableModels": [
            {"modelId": "gpt-5.6-sol[xhigh]", "name": "GPT-5.6-Sol (xhigh)"},
            {"modelId": "gpt-5.5[xhigh]", "name": "GPT-5.5 (xhigh)"},
        ],
    },
    "configOptions": [
        _select_dict(
            "mode",
            "agent-full-access",
            ["read-only", "agent", "agent-full-access"],
        ),
        _select_dict(
            "model",
            "gpt-5.6-sol",
            ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"],
            category="model",
        ),
        _select_dict("reasoning_effort", "xhigh", ["xhigh", "low"]),
    ],
}
_GEMINI_046_SESSION = {
    "sessionId": "sess-gemini",
    "configOptions": None,
    "models": {
        "currentModelId": "gemini-3-flash-preview",
        "availableModels": [
            {"modelId": mid, "name": mid}
            for mid in (
                "auto",
                "gemini-3-pro-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-3.1-flash-lite",
            )
        ],
    },
}


class TestDetectionAgainstRealSessionResponses:
    """针对真实 CLI ``session/new`` 线形状的检测 + 提取，
    通过实际的``acp.schema.NewSessionResponse``进行解析。

    守卫模式形状回归：每个 ``agent-client-protocol`` 0.8.x
    ``config_options`` 条目是 ``SessionConfigOption`` RootModel (``.root``)，因此简单
    的
    ``opt.id`` 读取是 ``None``，并且 SDK 将回退到已删除的 ``session/set_model``。
    """

    def test_config_options_is_the_schema_field_name(self):
        # SDK 变为 ``response.config_options``； 指出这是模式上的真实字段。
        #
        assert "config_options" in NewSessionResponse.model_fields

    def test_claude_046_uses_config_option(self):
        resp = NewSessionResponse.model_validate(_CLAUDE_046_SESSION)
        cur, avail, via = _extract_session_models(resp)
        assert via is True
        assert cur == "opus[1m]"
        assert avail is not None
        assert [m.model_id for m in avail] == ["default", "opus[1m]", "sonnet", "haiku"]

    def test_codex_112_prefers_config_option_over_legacy_models(self):
        resp = NewSessionResponse.model_validate(_CODEX_112_SESSION)
        cur, avail, via = _extract_session_models(resp)
        assert via is True
        assert cur == "gpt-5.6-sol"
        assert avail is not None
        assert [m.model_id for m in avail] == [
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
        ]

    def test_gemini_046_models_block_needs_the_extended_response(self):
        # 智能体-client-protocol 0.12.1 删除了 UNSTABLE ``models`` 块
        # from ``NewSessionResponse``; gemini-cli reports its models only there.
        plain = NewSessionResponse.model_validate(_GEMINI_046_SESSION)
        assert _extract_session_models(plain) == (None, None, False)

        resp = _NewSessionResponse.model_validate(_GEMINI_046_SESSION)
        cur, avail, via = _extract_session_models(resp)
        assert via is False
        assert cur == "gemini-3-flash-preview"
        assert avail is not None
        assert [m.model_id for m in avail][:3] == [
            "auto",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
        ]

    def test_malformed_models_block_is_ignored(self):
        resp = _NewSessionResponse.model_validate(
            {"sessionId": "s", "models": {"availableModels": [{"name": "no id"}]}}
        )
        assert resp.session_id == "s"
        assert resp.models is None


class TestApplyAcpModelNoFallback:
    """``_apply_acp_model`` 仅通过广告机制适用 - 有
    无交叉机制回退方案。 响应检测在会话/新形状下是确定性的，并且对每个验证过的 CLI 都
    是正确的，因此任何拒绝都是真正的错误（无效的模型 ID，或一个真正被错误地广
    播的服务器），而不是默默地尝试其他调用。
    """

    @pytest.mark.asyncio
    async def test_config_option_rejection_propagates(self):
        conn = AsyncMock()
        conn.set_config_option.side_effect = ACPRequestError(
            code=-32601, message="Method not found"
        )
        with pytest.raises(ACPRequestError):
            await _apply_acp_model(conn, "sess-1", "opus[1m]", via_config_option=True)
        conn.set_session_model.assert_not_called()  # 没有回退方案

    @pytest.mark.asyncio
    async def test_set_session_model_rejection_propagates(self):
        conn = AsyncMock()
        conn.set_session_model.side_effect = ACPRequestError(
            code=-32601, message="Method not found"
        )
        with pytest.raises(ACPRequestError):
            await _apply_acp_model(
                conn, "sess-1", "gemini-3-flash", via_config_option=False
            )
        conn.set_config_option.assert_not_called()  # 没有回退方案


class TestApplyAcpModel:
    """``_apply_acp_model`` 使用会话通告的机制。"""

    @pytest.mark.asyncio
    async def test_config_option_single_call(self):
        conn = AsyncMock()
        await _apply_acp_model(conn, "sess-1", "gpt-5.5", via_config_option=True)
        conn.set_config_option.assert_awaited_once_with(
            config_id="model", value="gpt-5.5", session_id="sess-1"
        )
        conn.set_session_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_session_model_branch(self):
        conn = AsyncMock()
        await _apply_acp_model(
            conn, "sess-1", "gemini-2.5-pro", via_config_option=False
        )
        conn.set_session_model.assert_awaited_once_with(
            model_id="gemini-2.5-pro", session_id="sess-1"
        )
        conn.set_config_option.assert_not_called()

    @pytest.mark.asyncio
    async def test_codex_config_option_splits_reasoning_effort(self):
        conn = AsyncMock()
        await _apply_acp_model(
            conn,
            "sess-1",
            "gpt-5.5/xhigh",
            agent_name="codex-acp",
            via_config_option=True,
        )
        conn.set_config_option.assert_has_awaits(
            [
                call(config_id="model", value="gpt-5.5", session_id="sess-1"),
                call(
                    config_id="reasoning_effort",
                    value="xhigh",
                    session_id="sess-1",
                ),
            ]
        )
        assert conn.set_config_option.await_count == 2
        conn.set_session_model.assert_not_called()


class TestACPAgentAvailableModelsProperty:
    """``available_models`` 逐字公开服务器的模型列表。

    无服务器端管理：酒店返还标准化的内容
    ``ACPModelInfo`` 列出以便客户端渲染选择器并解析
    ``current_model_id`` 为显示标签本身。
    """

    def test_defaults_to_empty(self):
        assert _make_agent().available_models == []

    def test_reflects_private_attr(self):
        agent = _make_agent()
        models = [
            ACPModelInfo(
                model_id="default",
                name="Default (recommended)",
                description="Opus 4.7 with 1M context · Most capable",
            ),
            ACPModelInfo(model_id="sonnet", name="Sonnet"),
        ]
        agent._available_models = models
        assert agent.available_models == models

    def test_returns_a_copy(self):
        # 改变返回的列表不得破坏智能体的状态。
        agent = _make_agent()
        agent._available_models = [ACPModelInfo(model_id="default")]
        got = agent.available_models
        got.append(ACPModelInfo(model_id="injected"))
        assert [m.model_id for m in agent.available_models] == ["default"]


class TestACPAgentSupportsRuntimeModelSwitch:
    """``supports_runtime_model_switch`` 控制实时开关选择器。

    ``True`` 仅适用于声明 ``session/set_model`` 支持的已知提供商。
    ``set_config_option`` 未知/自定义提供者在初始
    模型选择中使用，但这只是通用配置写入，而不是保证的实时切换原语，因此选择器对他们
    是隐藏的。 ``False`` 在会话存在之前。
    """

    def test_false_before_session(self):
        # 没有实时会话 (``_session_id is None``) -> 没有任何可切换的内容。
        agent = _make_agent()
        agent._agent_name = "codex-acp"
        assert agent.supports_runtime_model_switch is False

    def test_true_for_known_switch_capable_provider(self):
        agent = _make_agent()
        agent._session_id = "sess-1"
        agent._agent_name = "codex-acp"
        assert agent.supports_runtime_model_switch is True

    def test_false_for_unknown_provider(self):
        # 未知/自定义提供商仅使用 set_config_option 进行初始模型选择； 实时切换选择器对
        # 他们来说是隐藏的。
        #
        agent = _make_agent()
        agent._session_id = "sess-1"
        agent._agent_name = "some-third-party-acp-server"
        assert agent.supports_runtime_model_switch is False

    def test_false_for_known_unsupported_provider(self, monkeypatch):
        # 声明不提供支持的知名提供商是我们拒绝的一种情况。
        import openhands.sdk.agent.acp_agent as acp_agent_module

        unsupported = MagicMock()
        unsupported.supports_runtime_model_switch = False
        monkeypatch.setattr(
            acp_agent_module,
            "detect_acp_provider_by_agent_name",
            lambda _name: unsupported,
        )
        agent = _make_agent()
        agent._session_id = "sess-1"
        agent._agent_name = "locked-down-provider"
        assert agent.supports_runtime_model_switch is False


# ---------------------------------------------------------------------------

# MCP 转发
# ---------------------------------------------------------------------------


class TestMcpConfigToAcpServers:
    """单元测试为 mcp_config -> ACP 服务器翻译 + 门控。"""

    @staticmethod
    def _caps(http: bool, sse: bool):
        from acp.schema import McpCapabilities

        return McpCapabilities(http=http, sse=sse)

    @staticmethod
    def _config(config: Mapping[str, object]):
        servers = config.get("mcpServers", config)
        return coerce_mcp_config(servers)

    def test_stdio_always_forwarded(self):
        from acp.schema import McpServerStdio

        cfg = {
            "mcpServers": {
                "fetch": {
                    "command": "uvx",
                    "args": ["mcp-server-fetch"],
                    "env": {"API_KEY": "x"},
                }
            }
        }
        # 即使没有公开的远程功能，stdio 也会被转发。
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=False, sse=False)
        )
        assert len(out) == 1
        srv = out[0]
        assert isinstance(srv, McpServerStdio)
        assert srv.name == "fetch"
        assert srv.command == "uvx"
        assert srv.args == ["mcp-server-fetch"]
        assert [(e.name, e.value) for e in srv.env] == [("API_KEY", "x")]

    def test_http_gated_on_capability(self):
        from acp.schema import HttpMcpServer

        cfg = {
            "mcpServers": {
                "remote": {
                    "url": "https://h/mcp",
                    "headers": {"Authorization": "Bearer y"},
                }
            }
        }
        # 当服务器不做广告时被丢弃 HTTP。
        assert (
            _mcp_config_to_acp_servers(
                self._config(cfg), self._caps(http=False, sse=False)
            )
            == []
        )
        # 发布广告时转发。
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert len(out) == 1
        assert isinstance(out[0], HttpMcpServer)
        assert out[0].type == "http"
        assert out[0].url == "https://h/mcp"
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("Authorization", "Bearer y")
        ]

    def test_http_auth_maps_to_bearer_header(self):
        from acp.schema import HttpMcpServer

        cfg = {
            "mcpServers": {
                "remote": {
                    "url": "https://h/mcp",
                    "auth": {"strategy": "bearer", "value": "token-y"},
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert len(out) == 1
        assert isinstance(out[0], HttpMcpServer)
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("Authorization", "Bearer token-y")
        ]

    def test_oauth_access_token_maps_to_bearer_header(self):
        from acp.schema import HttpMcpServer

        cfg = {
            "mcpServers": {
                "linear": {
                    "url": "https://mcp.linear.app/mcp",
                    "auth": {
                        "strategy": "oauth2",
                        "state": {
                            "tokens": {"access_token": "oauth-access-token"},
                            "token_expires_at": 4102444800.0,
                        },
                    },
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert len(out) == 1
        assert isinstance(out[0], HttpMcpServer)
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("Authorization", "Bearer oauth-access-token")
        ]

    def test_oauth_token_encrypted_at_rest_is_forwarded_decrypted(self):
        from openhands.sdk.mcp.config import MCPServer

        cipher = Cipher(secret_key="test-secret-key-0123456789")
        stored = MCPServer.model_validate(
            {
                "url": "https://mcp.linear.app/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "state": {"tokens": {"access_token": "oauth-access-token"}},
                },
            }
        ).model_dump(mode="json", context={"cipher": cipher})
        assert stored["auth"]["state"]["tokens"]["access_token"] != (
            "oauth-access-token"
        )
        server = MCPServer.model_validate(stored, context={"cipher": cipher})

        out = _mcp_config_to_acp_servers(
            {"linear": server}, self._caps(http=True, sse=False)
        )
        assert [h.value for h in out[0].headers] == ["Bearer oauth-access-token"]

    def test_oauth_access_token_keeps_static_headers(self):
        cfg = {
            "mcpServers": {
                "linear": {
                    "url": "https://mcp.linear.app/mcp",
                    "headers": {"X-Client": "canvas"},
                    "auth": {
                        "strategy": "oauth2",
                        "state": {"tokens": {"access_token": "oauth-access-token"}},
                    },
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("X-Client", "canvas"),
            ("Authorization", "Bearer oauth-access-token"),
        ]

    def test_oauth_without_stored_token_omits_authorization_header(self):
        from acp.schema import HttpMcpServer

        cfg = {
            "mcpServers": {
                "granola": {
                    "url": "https://mcp.granola.ai/mcp",
                    "auth": {"strategy": "oauth2"},
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert len(out) == 1
        assert isinstance(out[0], HttpMcpServer)
        assert out[0].headers == []

    def test_oauth_access_token_maps_to_bearer_header_for_sse(self):
        from acp.schema import SseMcpServer

        cfg = {
            "mcpServers": {
                "linear": {
                    "url": "https://mcp.linear.app/sse",
                    "transport": "sse",
                    "auth": {
                        "strategy": "oauth2",
                        "state": {"tokens": {"access_token": "oauth-access-token"}},
                    },
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=True)
        )
        assert len(out) == 1
        assert isinstance(out[0], SseMcpServer)
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("Authorization", "Bearer oauth-access-token")
        ]

    def test_http_header_auth_forwards_authorization_header(self):
        cfg = {
            "mcpServers": {
                "remote": {
                    "url": "https://h/mcp",
                    "auth": {
                        "strategy": "header",
                        "headers": {"authorization": "Bearer explicit"},
                    },
                }
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=False)
        )
        assert [(h.name, h.value) for h in out[0].headers] == [
            ("authorization", "Bearer explicit")
        ]

    def test_sse_gated_on_capability(self):
        from acp.schema import SseMcpServer

        cfg = {"mcpServers": {"s": {"url": "https://s/sse", "transport": "sse"}}}
        assert (
            _mcp_config_to_acp_servers(
                self._config(cfg), self._caps(http=True, sse=False)
            )
            == []
        )
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=True)
        )
        assert len(out) == 1
        assert isinstance(out[0], SseMcpServer)
        assert out[0].type == "sse"

    def test_streamable_http_maps_to_http(self):
        from acp.schema import HttpMcpServer

        cfg = {
            "mcpServers": {
                "s": {"url": "https://h/mcp", "transport": "streamable-http"}
            }
        }
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=True)
        )
        assert len(out) == 1
        assert isinstance(out[0], HttpMcpServer)

    def test_disabled_servers_not_forwarded(self):
        cfg = {
            "mcpServers": {
                "fetch": {"command": "uvx"},
                "switched_off": {"command": "uvx", "enabled": False},
            }
        }
        # 子进程拥有该连接，因此保留该条目是使禁用的服务器无法访问的唯一方法。
        #
        out = _mcp_config_to_acp_servers(
            self._config(cfg), self._caps(http=True, sse=True)
        )
        assert [s.name for s in out] == ["fetch"]

    def test_empty_configs(self):
        caps = self._caps(http=True, sse=True)
        assert _mcp_config_to_acp_servers({}, caps) == []
        assert _mcp_config_to_acp_servers(self._config({"mcpServers": {}}), caps) == []

    def test_none_capabilities_drops_remote_keeps_stdio(self):
        from acp.schema import McpServerStdio

        cfg = {
            "mcpServers": {
                "fetch": {"command": "echo"},
                "remote": {"url": "https://h/mcp"},
            }
        }
        out = _mcp_config_to_acp_servers(self._config(cfg), None)
        assert [type(s).__name__ for s in out] == [McpServerStdio.__name__]


class TestACPMcpForwarding:
    """已翻译的服务器达到 new_session AND load_session（恢复）。"""

    @staticmethod
    def _conn_with_caps(*, http=True, sse=True, load_exc=None):
        conn = TestACPSessionIdPersistence._make_conn(load_exc=load_exc)
        conn.initialize.return_value.agent_capabilities.mcp_capabilities = (
            TestMcpConfigToAcpServers._caps(http=http, sse=sse)
        )
        return conn

    def test_new_session_receives_acp_mcp_servers(self, tmp_path):
        agent = _make_agent(mcp_config={"fetch": {"command": "echo"}})
        state = _make_state(tmp_path)
        conn = self._conn_with_caps()

        TestACPSessionIdPersistence._patched_start_acp_server(agent, state, conn=conn)

        conn.new_session.assert_awaited_once()
        servers = conn.new_session.call_args.kwargs["mcp_servers"]
        assert [s.name for s in servers] == ["fetch"]

    def test_resume_load_session_receives_acp_mcp_servers(self, tmp_path):
        """关键正确点：resume必须重新经过MCP个服务器，因为
        load_session 不持久化服务器端。"""
        agent = _make_agent(mcp_config={"fetch": {"command": "echo"}})
        state = _make_state(tmp_path)
        state.agent_state = {**state.agent_state, "acp_session_id": "stored-sess"}
        conn = self._conn_with_caps()

        TestACPSessionIdPersistence._patched_start_acp_server(agent, state, conn=conn)

        conn.load_session.assert_awaited_once()
        servers = conn.load_session.call_args.kwargs["mcp_servers"]
        assert [s.name for s in servers] == ["fetch"]
        conn.new_session.assert_not_awaited()

    def test_no_mcp_config_forwards_empty_acp_mcp_servers_list(self, tmp_path):
        agent = _make_agent()
        state = _make_state(tmp_path)
        conn = self._conn_with_caps()

        TestACPSessionIdPersistence._patched_start_acp_server(agent, state, conn=conn)

        conn.new_session.assert_awaited_once()
        assert conn.new_session.call_args.kwargs["mcp_servers"] == []


# ---------------------------------------------------------------------------
# 保留文件内容机密实现（问题 #1020）
# ---------------------------------------------------------------------------


class TestACPFileSecretMaterialisation:
    """Codex auth.json / Gemini Vertex SA JSON 实现耐用
    每个对话根，具有正确的数据目录环境变量，如果不存在则种子。
    """

    @staticmethod
    def _make_conn(
        *,
        agent_name: str = "codex-acp",
        auth_method: str | None = None,
        auth_method_type: str | None = None,
    ):
        conn = MagicMock()
        init_response = MagicMock()
        init_response.agent_info = MagicMock()
        init_response.agent_info.name = agent_name
        init_response.agent_info.version = "1.0"
        init_response.auth_methods = [MagicMock(id=auth_method)] if auth_method else []
        # MagicMock(id=...) 未设置 .id； 显式分配。
        for m in init_response.auth_methods:
            m.id = auth_method
            m.type = auth_method_type
        conn.initialize = AsyncMock(return_value=init_response)
        new_response = MagicMock()
        new_response.session_id = "sess-new"
        new_response.models = None
        conn.new_session = AsyncMock(return_value=new_response)
        conn.load_session = AsyncMock(return_value=MagicMock())
        conn.set_session_mode = AsyncMock()
        conn.set_session_model = AsyncMock()
        conn.authenticate = AsyncMock()
        conn.close = AsyncMock()
        return conn

    @staticmethod
    def _run_start(agent, state, *, conn):
        """用传输层模拟的运行真实的_start_acp_server； 返回环境
        字典交给子进程。"""
        from contextlib import ExitStack

        from openhands.sdk.utils.async_executor import AsyncExecutor

        captured: dict[str, Any] = {}
        mock_process = MagicMock(spec=asyncio.subprocess.Process)
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        async def _fake_exec(*_args, **kwargs):
            captured["env"] = kwargs.get("env")
            return mock_process

        async def _fake_filter(_src, _dst):
            return None

        agent._executor = AsyncExecutor()
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.create_subprocess_exec",
                    new=_fake_exec,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._ACPClientConnection",
                    return_value=conn,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent._filter_jsonrpc_lines",
                    new=_fake_filter,
                )
            )
            stack.enter_context(
                patch(
                    "openhands.sdk.agent.acp_agent.asyncio.StreamReader",
                    return_value=MagicMock(),
                )
            )
            agent._start_acp_server(state)
        return captured["env"]

    @staticmethod
    def _state(tmp_path, *, persisted: bool = True):
        from openhands.sdk.agent.acp_agent import ACPAgent

        agent = ACPAgent(acp_command=["codex-acp"])
        workspace = LocalWorkspace(working_dir=str(tmp_path / "ws"))
        (tmp_path / "ws").mkdir()
        persistence_dir = (
            str(tmp_path / "conversations" / uuid.uuid4().hex) if persisted else None
        )
        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=persistence_dir,
        )
        return state

    def test_codex_auth_json_materialises_to_conversation_root(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"tokens": "x"}'))}
        )
        env = self._run_start(agent, state, conn=self._make_conn())

        codex_home = Path(env["CODEX_HOME"])
        assert codex_home == Path(persist) / "acp" / "codex"
        auth_file = codex_home / "auth.json"
        assert auth_file.read_text(encoding="utf-8") == '{"tokens": "x"}'
        # 0700 目录中的 0600 文件，共享的 acp/ 父级也是 0700。
        assert auth_file.stat().st_mode & 0o777 == 0o600
        assert codex_home.stat().st_mode & 0o777 == 0o700
        assert codex_home.parent.stat().st_mode & 0o777 == 0o700
        # 该 blob 不会作为环境变量导出。
        assert "CODEX_AUTH_JSON" not in env

    def test_secret_file_replace_failure_preserves_existing_value(self, tmp_path):
        path = tmp_path / "auth.json"
        path.write_text("original")

        with (
            patch.object(
                files_module.os,
                "replace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            acp_file_credentials_module.write_secret_file(path, "replacement")

        assert path.read_text() == "original"
        assert list(tmp_path.iterdir()) == [path]

    def test_secret_file_write_without_fchmod(self, tmp_path):
        path = tmp_path / "auth.json"

        with patch.object(files_module.os, "fchmod", new=None, create=True):
            acp_file_credentials_module.write_secret_file(path, "credential")

        assert path.read_text(encoding="utf-8") == "credential"

    def test_gemini_vertex_sa_materialises_and_points_at_file(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {
                "GOOGLE_APPLICATION_CREDENTIALS_JSON": StaticSecret(
                    value=SecretStr('{"type": "service_account"}')
                )
            }
        )
        env = self._run_start(
            agent, state, conn=self._make_conn(agent_name="gemini-cli")
        )

        gac = Path(env["GOOGLE_APPLICATION_CREDENTIALS"])
        assert gac == Path(persist) / "acp" / "gemini-cli" / "gcloud-credentials.json"
        assert gac.read_text(encoding="utf-8") == '{"type": "service_account"}'
        # 0700 目录内的 0600 文件（与 Codex 测试对称）。
        assert gac.stat().st_mode & 0o777 == 0o600
        assert gac.parent.stat().st_mode & 0o777 == 0o700
        assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" not in env

    def test_pi_auth_json_materialises_into_the_agent_config_dir(self, tmp_path):
        """PI_AUTH_JSON 着陆为 auth.json，PI_CODING_AGENT_DIR 位于目录上。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {
                "PI_AUTH_JSON": StaticSecret(
                    value=SecretStr('{"anthropic": {"type": "api_key", "key": "k"}}')
                )
            }
        )

        env = self._run_start(
            agent,
            state,
            conn=self._make_conn(
                agent_name="pi-acp",
                auth_method="pi_terminal_login",
                auth_method_type="terminal",
            ),
        )

        auth_file = Path(persist) / "acp" / "pi" / "auth.json"
        assert Path(env["PI_CODING_AGENT_DIR"]) == Path(persist) / "acp" / "pi"
        assert (
            auth_file.read_text(encoding="utf-8")
            == '{"anthropic": {"type": "api_key", "key": "k"}}'
        )
        assert auth_file.stat().st_mode & 0o777 == 0o600
        assert "PI_AUTH_JSON" not in env

    def test_terminal_only_auth_with_seeded_file_does_not_warn(self, tmp_path):
        """pi-ACP 仅提供交互式登录； 种子 auth.json 是
        凭据，因此启动时不得调用authenticate()或警告。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"PI_AUTH_JSON": StaticSecret(value=SecretStr('{"anthropic": {}}'))}
        )
        conn = self._make_conn(
            agent_name="pi-acp",
            auth_method="pi_terminal_login",
            auth_method_type="terminal",
        )

        with patch(
            "openhands.sdk.agent.acp_agent._warn_auth_selection_failure"
        ) as mock_warn:
            self._run_start(agent, state, conn=conn)

        conn.authenticate.assert_not_called()
        mock_warn.assert_not_called()
        conn.new_session.assert_called_once()

    def test_terminal_only_auth_with_the_provider_api_key_does_not_warn(self, tmp_path):
        """pi 在自己的环境中甚至从 ANTHROPIC_API_KEY 进行身份验证
        尽管服务器仅通告交互式登录，因此 no-凭据警告将在工作配置上触发。
        """
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-ant-test"))}
        )
        conn = self._make_conn(
            agent_name="pi-acp",
            auth_method="pi_terminal_login",
            auth_method_type="terminal",
        )

        with patch(
            "openhands.sdk.agent.acp_agent._warn_auth_selection_failure"
        ) as mock_warn:
            env = self._run_start(agent, state, conn=conn)

        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"
        conn.authenticate.assert_not_called()
        mock_warn.assert_not_called()
        conn.new_session.assert_called_once()

    def test_terminal_only_auth_without_seeded_file_warns(self, tmp_path):
        agent = _make_agent()
        state = self._state(tmp_path)
        conn = self._make_conn(
            agent_name="pi-acp",
            auth_method="pi_terminal_login",
            auth_method_type="terminal",
        )

        with patch(
            "openhands.sdk.agent.acp_agent._warn_auth_selection_failure"
        ) as mock_warn:
            self._run_start(agent, state, conn=conn)

        conn.authenticate.assert_not_called()
        mock_warn.assert_called_once()

    def test_non_terminal_auth_still_warns_with_a_seeded_file(self, tmp_path):
        """抑制范围仅限于终端服务器：带有
        auth.json 这不是 ChatGPT 身份验证必须保持警告。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"tokens": null}'))}
        )
        conn = self._make_conn(agent_name="codex-acp", auth_method="chat-gpt")

        with patch(
            "openhands.sdk.agent.acp_agent._warn_auth_selection_failure"
        ) as mock_warn:
            self._run_start(agent, state, conn=conn)

        mock_warn.assert_called_once()

    def test_pi_initialization_skips_set_session_mode(self, tmp_path):
        """Pi 有 default_session_mode=None，所以 set_session_mode 没有被调用。"""
        agent = _make_agent()
        state = self._state(tmp_path)
        conn = self._make_conn(
            agent_name="pi-acp",
            auth_method="pi_terminal_login",
            auth_method_type="terminal",
        )

        self._run_start(agent, state, conn=conn)

        conn.set_session_mode.assert_not_called()

    def test_seed_if_absent_does_not_clobber_existing_file(self, tmp_path):
        """一个非空的现有凭据文件 (e.g. a token CLI 已刷新）
        被保留； 陈旧的粘贴斑点不会覆盖它。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        # 预先播种“焕然一新”的 auth.json 故意宽 (0644) 的烫发。
        codex_home = Path(persist) / "acp" / "codex"
        codex_home.mkdir(parents=True)
        refreshed = codex_home / "auth.json"
        refreshed.write_text('{"refreshed": true}', encoding="utf-8")
        refreshed.chmod(0o644)

        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"stale": true}'))}
        )
        env = self._run_start(agent, state, conn=self._make_conn())

        assert Path(env["CODEX_HOME"]) == codex_home
        # 内容被保留（没有被陈旧的糊状物破坏）......
        assert refreshed.read_text(encoding="utf-8") == '{"refreshed": true}'
        # ...but perms are still clamped to 0600 (regression: QA found a
        # 保留的 0644 文件保持世界可读）。
        assert refreshed.stat().st_mode & 0o777 == 0o600

    def test_updated_credential_replaces_existing_file_once(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        codex_home = Path(persist) / "acp" / "codex"
        codex_home.mkdir(parents=True)
        auth_file = codex_home / "auth.json"
        auth_file.write_text('{"stale": true}', encoding="utf-8")
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"fallback": true}'))}
        )
        agent.restart_for_updated_credentials({"CODEX_AUTH_JSON"})

        env = self._run_start(agent, state, conn=self._make_conn())

        assert Path(env["CODEX_HOME"]) == codex_home
        assert auth_file.read_text(encoding="utf-8") == '{"fallback": true}'
        assert (
            "CODEX_AUTH_JSON"
            not in agent._replace_file_credentials_on_next_materialisation
        )

        auth_file.write_text('{"refreshed": true}', encoding="utf-8")
        state.secret_registry.update_secrets(
            {
                "CODEX_AUTH_JSON": StaticSecret(
                    value=SecretStr('{"newer-fallback": true}')
                )
            }
        )
        agent._materialise_file_secrets(state, env)

        assert auth_file.read_text(encoding="utf-8") == '{"refreshed": true}'

    def test_reads_reserved_secret_seeded_from_agent_context(self, tmp_path):
        """通过 agent_context.secrets（canvas-local）提供的保留文件机密
        注册表被初始化时被种子，然后被实现。"""
        from openhands.sdk.conversation.impl.local_conversation import (
            LocalConversation,
        )
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(
                current_datetime=None,
                secrets={"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"a": 1}'))},
            ),
        )
        conv = LocalConversation(
            agent,
            workspace=str(tmp_path / "ws"),
            persistence_dir=str(tmp_path / "conversations"),
        )
        try:
            env = self._run_start(agent, conv.state, conn=self._make_conn())
        finally:
            conv.close()

        auth_file = Path(env["CODEX_HOME"]) / "auth.json"
        assert auth_file.read_text(encoding="utf-8") == '{"a": 1}'
        assert "CODEX_AUTH_JSON" not in env

    def test_fallback_root_when_not_persisted(self, tmp_path):
        """如果没有 persistence_dir，文件会落在工作区树下 -
        仍然是种子（如果不存在），没有 TemporaryDirectory。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path, persisted=False)
        assert state.persistence_dir is None
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr("{}"))}
        )
        env = self._run_start(agent, state, conn=self._make_conn())

        expected = Path(state.workspace.working_dir) / ".openhands" / "acp" / "codex"
        assert Path(env["CODEX_HOME"]) == expected
        assert (expected / "auth.json").is_file()

    def test_no_file_secret_when_secret_absent(self, tmp_path):
        """不存在保留机密 -> 未设置数据目录环境变量。"""
        agent = _make_agent()
        state = self._state(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            env = self._run_start(agent, state, conn=self._make_conn())
        assert "CODEX_HOME" not in env

    def test_materialisation_oserror_fails_fast(self, tmp_path):
        """如果凭据不能写(e.g. 只读挂载），错误
        从 _start_acp_server 传播（因此 init_state 表面有类型的
        ConversationErrorEvent），而不是被吞没并使
        CLI 在验证时失败，没有 SDK 面包屑。
        """
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr("{}"))}
        )
        with patch(
            "openhands.sdk.agent.acp_agent.write_secret_file",
            side_effect=OSError("[Errno 30] Read-only file system"),
        ):
            with pytest.raises(OSError, match="Read-only file system"):
                self._run_start(agent, state, conn=self._make_conn())

    def test_vertex_warns_when_project_unset(self, tmp_path, caplog):
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"GOOGLE_APPLICATION_CREDENTIALS_JSON": StaticSecret(value=SecretStr("{}"))}
        )
        with caplog.at_level("WARNING"):
            self._run_start(agent, state, conn=self._make_conn(agent_name="gemini-cli"))
        assert any("GOOGLE_CLOUD_PROJECT" in rec.message for rec in caplog.records)

    def test_present_file_secret_names_helper(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent()
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {
                "CODEX_AUTH_JSON": StaticSecret(value=SecretStr("{}")),
                "PLAIN_TOKEN": StaticSecret(value=SecretStr("t")),
            }
        )
        assert agent._present_file_secret_names(state) == {"CODEX_AUTH_JSON"}

    def test_blob_excluded_from_custom_secrets_advertisement(self, tmp_path):
        """<CUSTOM_SECRETS> 广告列出了普通的机密，但没有列出
        文件内容 blob（它不是智能体可以引用的环境变量）。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(
            agent_context=AgentContext(current_datetime=None),
        )
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {
                "CODEX_AUTH_JSON": StaticSecret(value=SecretStr("{}")),
                "PLAIN_TOKEN": StaticSecret(
                    value=SecretStr("t"), description="A plain token"
                ),
            }
        )
        events: list = []
        with patch("openhands.sdk.agent.acp_agent.ACPAgent._start_acp_server"):
            agent.init_state(state, on_event=events.append)

        suffix = events[0].dynamic_context
        assert suffix is not None
        assert "PLAIN_TOKEN" in suffix.text
        assert "CODEX_AUTH_JSON" not in suffix.text

    def test_downstream_can_override_specs_with_custom_provider(self, tmp_path):
        """下游应用为其 CLI 提供了自定义 ACPFileSecretSpec。
        SDK机制在没有任何注册表改变的情况下实现了它。"""
        from openhands.sdk import ACPFileSecretSpec
        from openhands.sdk.secret import StaticSecret

        custom = ACPFileSecretSpec(
            secret_name="MYCLI_TOKEN_JSON",
            filename="token.json",
            env_var="MYCLI_HOME",
            subdir="mycli",
            env_points_to="dir",
        )
        agent = _make_agent(acp_file_secrets=[custom])
        state = self._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {"MYCLI_TOKEN_JSON": StaticSecret(value=SecretStr('{"t": 1}'))}
        )
        env = self._run_start(agent, state, conn=self._make_conn())

        home = Path(env["MYCLI_HOME"])
        assert home == Path(persist) / "acp" / "mycli"
        assert (home / "token.json").read_text(encoding="utf-8") == '{"t": 1}'
        assert "MYCLI_TOKEN_JSON" not in env
        # 内置的 Codex/Gemini 规范已被替换，因此它们的机密将不通过此智能体实现。
        #
        assert agent._present_file_secret_names(state) == {"MYCLI_TOKEN_JSON"}

    def test_empty_specs_disables_materialisation(self, tmp_path):
        """当 acp_file_secrets=[] 时，CODEX_AUTH_JSON 机密被视为
        普通环境变量（未写入文件，无 CODEX_HOME）- 下游选择退出。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(acp_file_secrets=[])
        state = self._state(tmp_path)
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr("blob"))}
        )
        with patch.dict("os.environ", {}, clear=True):
            env = self._run_start(agent, state, conn=self._make_conn())

        assert "CODEX_HOME" not in env
        # 未配置为文件-机密，因此它作为普通环境变量流过。
        assert env.get("CODEX_AUTH_JSON") == "blob"

    def test_settings_pass_file_secrets_through_create_agent(self):
        """ACPAgentSettings 默认使用内置规格，并将它们转发给
        已构建的 ACPAgent。"""
        from openhands.sdk.settings.acp_providers import default_acp_file_secrets
        from openhands.sdk.settings.model import ACPAgentSettings

        settings = ACPAgentSettings(acp_server="codex")
        agent = settings.create_agent()
        names = {s.secret_name for s in agent.acp_file_secrets}
        assert "CODEX_AUTH_JSON" in names
        assert {s.secret_name for s in agent.acp_file_secrets} == {
            s.secret_name for s in default_acp_file_secrets()
        }


class TestACPFileSecretProviderScoping:
    """``acp_file_secrets`` 默认为每个注册的联合
    提供商，但仅适用正在运行的提供商的规范 (#4923)。 如果没有范围，在上游注册线束会改
    变不相关提供者的对话处理带有新保留名称的机密的方式。
    """

    _H = TestACPFileSecretMaterialisation

    @staticmethod
    def _names(agent):
        return {spec.secret_name for spec in agent._active_file_secrets()}

    @pytest.mark.parametrize(
        "acp_server,expected",
        [
            ("claude-code", set()),
            ("codex", {"CODEX_AUTH_JSON"}),
            ("gemini-cli", {"GOOGLE_APPLICATION_CREDENTIALS_JSON"}),
            ("kimi-code", {"KIMI_CODE_CONFIG_TOML"}),
            ("pi", {"PI_AUTH_JSON"}),
            ("opencode", set()),
        ],
    )
    def test_scopes_to_the_running_provider(self, acp_server, expected):
        agent = _make_agent(acp_server=acp_server)
        assert self._names(agent) == expected

    def test_no_provider_claims_another_providers_reserved_secret(self):
        """该属性存在的目的是注册表
        因此，无需编辑此测试即可覆盖添加到上游的提供程序。"""
        from openhands.sdk.settings.acp_providers import ACP_PROVIDERS

        for key, info in ACP_PROVIDERS.items():
            others = {
                spec.secret_name
                for other, other_info in ACP_PROVIDERS.items()
                if other != key
                for spec in other_info.file_secrets
            } - {spec.secret_name for spec in info.file_secrets}
            assert self._names(_make_agent(acp_server=key)).isdisjoint(others)

    def test_unrecognised_server_keeps_the_union(self):
        """没有身份意味着我们无法分辨谁的凭据是保留名称
        属于，所以保持保守——就像``_strip_conflicting_env``一样。"""
        from openhands.sdk.settings.acp_providers import default_acp_file_secrets

        agent = ACPAgent(acp_command=["some-unknown-acp-server"])
        assert self._names(agent) == {
            spec.secret_name for spec in default_acp_file_secrets()
        }

    def test_custom_command_resolves_the_provider_from_the_command(self):
        agent = ACPAgent(acp_command=["codex-acp"])
        assert self._names(agent) == {"CODEX_AUTH_JSON"}

    def test_specs_outside_the_registry_always_apply(self):
        """下游 CLI 的规范不属于任何注册提供者，因此它是
        从未被过滤掉——无论对话运行在哪个工具上。"""
        from openhands.sdk import ACPFileSecretSpec

        custom = ACPFileSecretSpec(
            secret_name="MYCLI_TOKEN_JSON",
            filename="token.json",
            env_var="MYCLI_HOME",
            subdir="mycli",
        )
        agent = _make_agent(acp_server="codex", acp_file_secrets=[custom])
        assert self._names(agent) == {"MYCLI_TOKEN_JSON"}

        from openhands.sdk.settings.acp_providers import default_acp_file_secrets

        agent = _make_agent(
            acp_server="codex",
            acp_file_secrets=[custom, *default_acp_file_secrets()],
        )
        assert self._names(agent) == {"MYCLI_TOKEN_JSON", "CODEX_AUTH_JSON"}

    def test_a_list_persisted_before_a_provider_was_added_still_scopes(self):
        """升级案例。 仅当注册表举行时编写的对话
        Codex 和 Gemini 包含两个规格列表； 在较新的 SDK 上恢复它仍然必须具有范围，而
        与今天的默认值进行比较无法做到这一点 - 存储的列表不再等于
        它。
        """
        from openhands.sdk.settings.acp_providers import ACP_PROVIDERS

        pre_upgrade = [
            *ACP_PROVIDERS["codex"].file_secrets,
            *ACP_PROVIDERS["gemini-cli"].file_secrets,
        ]
        agent = _make_agent(acp_server="claude-code", acp_file_secrets=pre_upgrade)
        assert self._names(agent) == set()

        agent = _make_agent(acp_server="codex", acp_file_secrets=pre_upgrade)
        assert self._names(agent) == {"CODEX_AUTH_JSON"}

    def test_a_name_several_providers_share_is_kept(self):
        """``owned_elsewhere`` 减去正在运行的提供商自己的名称，因此
        规范两个提供商都声称没有被过滤掉。"""
        from openhands.sdk import ACPFileSecretSpec

        shared = ACPFileSecretSpec(
            secret_name="GOOGLE_APPLICATION_CREDENTIALS_JSON",
            filename="gcloud-credentials.json",
            env_var="GOOGLE_APPLICATION_CREDENTIALS",
            subdir="gemini-cli",
        )
        agent = _make_agent(acp_server="gemini-cli", acp_file_secrets=[shared])
        assert self._names(agent) == {"GOOGLE_APPLICATION_CREDENTIALS_JSON"}

    def test_empty_specs_stay_empty(self):
        agent = _make_agent(acp_server="codex", acp_file_secrets=[])
        assert self._names(agent) == set()

    def test_scoping_survives_a_serialization_round_trip(self):
        """恢复的对话也必须涵盖范围——包括由一位
        旧的 SDK，``test_a_list_persisted_before_a_provider_was_added_ still_scopes``
         涵盖。
        """
        agent = _make_agent(acp_server="claude-code")
        restored = ACPAgent.model_validate(agent.model_dump())
        assert self._names(restored) == set()

    def test_other_providers_blob_stays_a_plain_env_var(self, tmp_path):
        """端到端通过 ``_start_acp_server``：在克劳德代码上
        对话 ``PI_AUTH_JSON`` 作为普通环境变量传递，未通过 ``PI_CODING_AGENT_DIR`` 设
        置具体化到磁盘。
        """
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(acp_server="claude-code")
        state = self._H._state(tmp_path)
        state.secret_registry.update_secrets(
            {"PI_AUTH_JSON": StaticSecret(value=SecretStr("blob"))}
        )

        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="claude-agent-acp")
            )

        assert env.get("PI_AUTH_JSON") == "blob"
        assert "PI_CODING_AGENT_DIR" not in env
        assert not (agent._acp_file_secret_dir(state, "pi") / "auth.json").exists()

    def test_own_blob_still_materialises(self, tmp_path):
        """对应：在 pi 对话中，写入相同的机密
        disk 和 data-dir var 指向它。"""
        from openhands.sdk.secret import StaticSecret

        agent = _make_agent(acp_server="pi")
        state = self._H._state(tmp_path)
        state.secret_registry.update_secrets(
            {"PI_AUTH_JSON": StaticSecret(value=SecretStr("blob"))}
        )

        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="pi-acp")
            )

        target = agent._acp_file_secret_dir(state, "pi") / "auth.json"
        assert target.read_text() == "blob"
        assert env.get("PI_CODING_AGENT_DIR") == str(target.parent)
        assert "PI_AUTH_JSON" not in env


# ---------------------------------------------------------------------------
# 每个对话 CLI 数据目录隔离（问题 #1019）
# ---------------------------------------------------------------------------


class TestACPDataDirIsolation:
    """``acp_isolate_data_dir`` 将每个提供商的 CLI 数据/配置根重新定位到
    ``<persistence_dir>/acp/<provider>`` 因此共享一个沙箱的对话不会在共享的 HOME 上竞
    争。 重用物化工具，以便针对相同的
    _start_acp_server 路径运用这两个功能。
    """

    _H = TestACPFileSecretMaterialisation

    @staticmethod
    def _agent(command, **kw):
        return ACPAgent(acp_command=command, acp_isolate_data_dir=True, **kw)

    def test_codex_sets_codex_home_to_conversation_root(self, tmp_path):
        agent = self._agent(["codex-acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        data_dir = Path(env["CODEX_HOME"])
        assert data_dir == Path(persist) / "acp" / "codex"
        assert data_dir.is_dir()
        assert data_dir.stat().st_mode & 0o777 == 0o700

    def test_gemini_sets_home_to_conversation_root(self, tmp_path):
        agent = self._agent(["npx", "-y", "@google/gemini-cli", "--acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="gemini-cli")
            )
        assert Path(env["HOME"]) == Path(persist) / "acp" / "gemini-cli"

    def test_disabled_by_default_leaves_home_shared(self, tmp_path):
        # 相同的 codex 命令，隔离 OFF（默认）：没有注入 CODEX_HOME。
        agent = ACPAgent(acp_command=["codex-acp"])
        state = self._H._state(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        assert "CODEX_HOME" not in env

    def test_unknown_command_no_ops(self, tmp_path):
        agent = self._agent(["my-custom-acp", "serve"])
        state = self._H._state(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        assert "CODEX_HOME" not in env
        assert "CLAUDE_CONFIG_DIR" not in env

    def test_falls_back_to_workspace_when_not_persisted(self, tmp_path):
        agent = self._agent(["codex-acp"])
        state = self._H._state(tmp_path, persisted=False)
        assert state.persistence_dir is None
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        assert (
            Path(env["CODEX_HOME"])
            == Path(state.workspace.working_dir) / ".openhands" / "acp" / "codex"
        )

    def test_composes_with_materialised_codex_auth(self, tmp_path):
        """隔离和文件机密实现在一项CODEX_HOME上达成一致。"""
        from openhands.sdk.secret import StaticSecret

        agent = self._agent(["codex-acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {"CODEX_AUTH_JSON": StaticSecret(value=SecretStr('{"tokens": "x"}'))}
        )
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        codex_home = Path(env["CODEX_HOME"])
        assert codex_home == Path(persist) / "acp" / "codex"
        # 物化将 auth.json 播种到 SAME dir 隔离点中。
        assert (codex_home / "auth.json").read_text(
            encoding="utf-8"
        ) == '{"tokens": "x"}'

    def test_binding_overrides_isolated_codex_home(self, tmp_path):
        agent = self._agent(["codex-acp"])
        state = self._H._state(tmp_path)
        durable_codex_home = Path(state.persistence_dir or "") / "acp" / "codex"
        durable_codex_home.mkdir(parents=True)
        durable_auth = durable_codex_home / "auth.json"
        durable_auth.write_text('{"legacy": true}', encoding="utf-8")
        auth = json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {"refresh_token": "refresh-r0", "access_token": "access-r0"},
            }
        )
        binding = MagicMock(spec=["load", "replace"])
        binding.load = AsyncMock(return_value=ResolvedCredential(auth, "v0"))
        binding.replace = AsyncMock(return_value="v1")
        agent.activate_file_credential_binding("CODEX_AUTH_JSON", binding)

        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(agent, state, conn=self._H._make_conn())
        try:
            codex_home = Path(env["CODEX_HOME"])
            assert codex_home != durable_codex_home
            assert (codex_home / "auth.json").read_text(encoding="utf-8") == auth
            assert not durable_auth.exists()
            assert durable_codex_home.exists()
        finally:
            agent.close()

    # --- Claude：隔离适用于任一身份验证模式 (#3588) ------------

    def test_claude_isolates_under_api_key(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = self._agent(["npx", "-y", "@agentclientprotocol/claude-agent-acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {"ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-live"))}
        )
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="claude-agent-acp")
            )
        # #3588: 冲突条键在 CLAUDE_CODE_OAUTH_TOKEN 上，而不是在
        # CLAUDE_CONFIG_DIR，因此重新定位数据目录不再删除工作的 API 键 — API 键 Claude
        # 获得相同的每个会话隔离。
        #
        assert Path(env["CLAUDE_CONFIG_DIR"]) == Path(persist) / "acp" / "claude-code"
        assert env["ANTHROPIC_API_KEY"] == "sk-live"

    def test_claude_isolates_under_oauth_token(self, tmp_path):
        from openhands.sdk.secret import StaticSecret

        agent = self._agent(["npx", "-y", "@agentclientprotocol/claude-agent-acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None
        state.secret_registry.update_secrets(
            {"CLAUDE_CODE_OAUTH_TOKEN": StaticSecret(value=SecretStr("oauth-xyz"))}
        )
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="claude-agent-acp")
            )
        assert Path(env["CLAUDE_CONFIG_DIR"]) == Path(persist) / "acp" / "claude-code"

    def test_pi_isolates_data_dir(self, tmp_path):
        """pi-ACP 的会话映射遵循 HOME； pi 自己的配置目录如下
        PI_CODING_AGENT_DIR，仅文件机密设置。"""
        from openhands.sdk.secret import StaticSecret

        agent = self._agent(["npx", "-y", "pi-acp"])
        state = self._H._state(tmp_path)
        persist = state.persistence_dir
        assert persist is not None

        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="pi-acp")
            )
        assert Path(env["HOME"]) == Path(persist) / "acp" / "pi"
        assert "PI_CODING_AGENT_DIR" not in env

        state.secret_registry.update_secrets(
            {"PI_AUTH_JSON": StaticSecret(value=SecretStr("{}"))}
        )
        with patch.dict("os.environ", {}, clear=True):
            env = self._H._run_start(
                agent, state, conn=self._H._make_conn(agent_name="pi-acp")
            )
        assert Path(env["HOME"]) == Path(persist) / "acp" / "pi"
        assert Path(env["PI_CODING_AGENT_DIR"]) == Path(persist) / "acp" / "pi"


# ---------------------------------------------------------------------------
# 机密掩蔽 (#1023)
# ---------------------------------------------------------------------------


def _redacting_mask(text: str) -> str:
    """替代``secret_registry.mask_secrets_in_output``：替换
    文字机密与实际注册表使用的哨兵值相同。"""
    return text.replace("SEKRET", "<secret-hidden>")


class TestMaskJsonValue:
    """单元测试用于递归 JSON 掩码助手。"""

    def test_masks_bare_string(self):
        assert _mask_json_value("token=SEKRET", _redacting_mask) == (
            "token=<secret-hidden>"
        )

    def test_masks_nested_dict_and_list(self):
        value = {
            "command": "curl -H 'Authorization: Bearer SEKRET'",
            "args": ["--data", "key=SEKRET"],
            "count": 3,
            "ok": True,
            "nothing": None,
        }
        masked = _mask_json_value(value, _redacting_mask)
        assert masked["command"] == "curl -H 'Authorization: Bearer <secret-hidden>'"
        assert masked["args"] == ["--data", "key=<secret-hidden>"]
        # 非串叶通过时保持不变。
        assert masked["count"] == 3
        assert masked["ok"] is True
        assert masked["nothing"] is None

    def test_non_string_scalar_passthrough(self):
        assert _mask_json_value(42, _redacting_mask) == 42
        assert _mask_json_value(None, _redacting_mask) is None


class TestACPBridgeMasking:
    """``_OpenHandsACPBridge`` 口罩在到达目的地之前已注入机密
    ``on_token`` / ``on_event`` 接收器（已持久化 + 网络中继）。"""

    @pytest.mark.asyncio
    async def test_message_chunk_masked_in_relay_and_accumulation(self):
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        tokens: list[str] = []
        client.on_token = tokens.append

        chunk = MagicMock(spec=AgentMessageChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "the token is SEKRET"

        await client.session_update("sess-1", chunk)

        assert tokens == ["the token is <secret-hidden>"]
        assert client.accumulated_text == ["the token is <secret-hidden>"]

    @pytest.mark.asyncio
    async def test_thought_chunk_masked(self):
        from acp.schema import AgentThoughtChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask

        chunk = MagicMock(spec=AgentThoughtChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "I will use SEKRET"

        await client.session_update("sess-1", chunk)

        assert client.accumulated_thoughts == ["I will use <secret-hidden>"]

    @pytest.mark.asyncio
    async def test_tool_call_start_masks_raw_fields(self):
        from acp.schema import ToolCallStart

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        events: list = []
        client.on_event = events.append

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Running: echo SEKRET"
        start.kind = "execute"
        start.status = "in_progress"
        start.raw_input = {"command": "echo SEKRET"}
        start.raw_output = "leaked SEKRET here"
        start.content = None

        await client.session_update("sess-1", start)

        assert len(events) == 1
        evt = events[0]
        assert evt.title == "Running: echo <secret-hidden>"
        assert evt.raw_input == {"command": "echo <secret-hidden>"}
        assert evt.raw_output == "leaked <secret-hidden> here"
        # 累加器本身必须保存屏蔽值，以便取代/刷新路径不能重新泄漏它们。
        #
        stored = client.accumulated_tool_calls[0]
        assert stored["title"] == "Running: echo <secret-hidden>"
        assert stored["raw_input"] == {"command": "echo <secret-hidden>"}
        assert stored["raw_output"] == "leaked <secret-hidden> here"

    @pytest.mark.asyncio
    async def test_tool_call_progress_masks_terminal_output(self):
        from acp.schema import ToolCallProgress, ToolCallStart

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        events: list = []
        client.on_event = events.append

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Run"
        start.kind = "execute"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None
        await client.session_update("sess-1", start)

        # 终端进度帧在其累积输出中携带机密。
        progress = MagicMock(spec=ToolCallProgress)
        progress.tool_call_id = "tc-1"
        progress.title = None
        progress.kind = None
        progress.status = "completed"
        progress.raw_input = None
        progress.raw_output = "result: SEKRET"
        progress.content = None
        await client.session_update("sess-1", progress)

        # 终止事件（在 in_progress-> 完成的转换上发出）携带屏蔽输出。
        #
        assert events[-1].status == "completed"
        assert events[-1].raw_output == "result: <secret-hidden>"
        assert (
            client.accumulated_tool_calls[0]["raw_output"] == "result: <secret-hidden>"
        )

    @pytest.mark.asyncio
    async def test_failed_progress_mask_keeps_accumulator_safe(self):
        from contextlib import suppress

        from acp.schema import ToolCallProgress, ToolCallStart

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask

        start = MagicMock(spec=ToolCallStart)
        start.tool_call_id = "tc-1"
        start.title = "Run"
        start.kind = "execute"
        start.status = "in_progress"
        start.raw_input = None
        start.raw_output = None
        start.content = None
        await client.session_update("sess-1", start)

        client.before_mask = MagicMock(
            side_effect=ACPFileCredentialSyncError("writeback failed")
        )
        progress = MagicMock(spec=ToolCallProgress)
        progress.tool_call_id = "tc-1"
        progress.title = None
        progress.kind = None
        progress.status = "completed"
        progress.raw_input = None
        progress.raw_output = "rotated SEKRET"
        progress.content = None

        with suppress(ACPFileCredentialSyncError):
            await client.session_update("sess-1", progress)

        stored = client.accumulated_tool_calls[0]
        assert stored["status"] == "in_progress"
        assert stored["raw_output"] is None
        with pytest.raises(ACPFileCredentialSyncError, match="writeback failed"):
            client._raise_masking_error()

    @pytest.mark.asyncio
    async def test_no_masking_when_mask_unset(self):
        """独立的网桥（掩码为 None）通过不变地传递文本
        并且从不加注。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        assert client.mask is None
        tokens: list[str] = []
        client.on_token = tokens.append

        chunk = MagicMock(spec=AgentMessageChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "raw SEKRET"

        await client.session_update("sess-1", chunk)

        assert tokens == ["raw SEKRET"]
        assert client.accumulated_text == ["raw SEKRET"]

    def test_mask_value_swallows_mask_errors(self):
        """失败的掩码器绝不能崩溃 session_update — 退回到
        原始值（与常规终端工具的屏蔽合约匹配）。"""

        def _boom(_text: str) -> str:
            raise RuntimeError("masker exploded")

        client = _OpenHandsACPBridge()
        client.mask = _boom
        assert client._mask_value("keep SEKRET") == "keep SEKRET"

    def test_mask_value_propagates_credential_errors(self):
        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        client.before_mask = MagicMock(
            side_effect=ACPFileCredentialNeedsReauthError("missing")
        )

        with pytest.raises(ACPFileCredentialNeedsReauthError):
            client._mask_value("SEKRET")

    def test_reset_preserves_mask(self):
        """mask 是会话生命周期（在 _start_acp_server 中绑定一次），所以
        每回合 reset() 必须不清除它——与 on_token/on_event 不同。"""
        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        client.reset()
        assert client.mask is _redacting_mask

    @pytest.mark.asyncio
    async def test_fork_session_text_masked(self):
        """ask_agent() 连接 _fork_accumulated_text 并将其返回给
        调用者，因此分叉会话块也必须被屏蔽。"""
        from acp.schema import AgentMessageChunk, TextContentBlock

        client = _OpenHandsACPBridge()
        client.mask = _redacting_mask
        client._fork_session_id = "fork-1"

        chunk = MagicMock(spec=AgentMessageChunk)
        chunk.content = MagicMock(spec=TextContentBlock)
        chunk.content.text = "fork says SEKRET"

        await client.session_update("fork-1", chunk)

        assert client._fork_accumulated_text == ["fork says <secret-hidden>"]


class TestACPStepMasksPersistedTurn:
    """端到端：已持久化 FinishAction 文本在连接处被屏蔽
    边界，包括机密跨流块分割。"""

    def _make_conversation_with_message(self, tmp_path, text="Hello"):
        state = _make_state(tmp_path)
        state.events.append(
            SystemPromptEvent(
                source="agent",
                system_prompt=TextContent(text="ACP-managed agent"),
                tools=[],
            )
        )
        state.events.append(
            MessageEvent(
                source="user",
                llm_message=Message(role="user", content=[TextContent(text=text)]),
            )
        )
        conversation = MagicMock()
        conversation.state = state
        return conversation

    def test_finish_action_masks_secret_split_across_chunks(self, tmp_path):
        agent = _make_agent()
        conversation = self._make_conversation_with_message(tmp_path)
        # 通过规范注册表路径（get_secret_value 记录 _exported_values 中的解析值）播种掩
        # 码集 — 相同的路径 _start_acp_server 驱动 StartConversationRequest 机密。
        #
        reg = conversation.state.secret_registry
        reg.update_secrets({"TOKEN": "supersecret"})
        reg.get_secret_value("TOKEN")
        events: list = []

        mock_client = _OpenHandsACPBridge()
        agent._client = mock_client
        agent._conn = MagicMock()
        agent._session_id = "test-session"

        def _fake_run_async(_coro, **_kwargs):
            # 直接填充 accumulated_text，故意绕过 session_update（从而绕过每个块掩码）：
            # 这隔离了 _finalize_successful_turn 中的连接边界重新掩码。 机密横跨两个块，
            # 因此两个块都不会单独匹配 - 只有重新组装的连接才会匹配，这正是持久化边界掩
            # 码捕获的内容。
            #
            mock_client.accumulated_text.append("the value is super")
            mock_client.accumulated_text.append("secret now")

        mock_executor = MagicMock()
        mock_executor.run_async = _fake_run_async
        agent._executor = mock_executor

        agent.step(conversation, on_event=events.append)

        finish = next(
            e for e in events if isinstance(getattr(e, "action", None), FinishAction)
        )
        assert "supersecret" not in finish.action.message
        assert finish.action.message == "the value is <secret-hidden> now"


class TestPreconfiguredCredentials:
    """我们无法执行其广告身份验证方法的服务器可能仍然是
    带外验证，因此 SDK 必须能够区分“我们无法验证”和“我们不需要”。

    源自提供者的注册表记录而不是提供者名称，因此它适用于稍后添加的提供者，而无需触及
    此代码。
    """

    def test_reports_the_provider_api_key_when_present(self):
        provider = ACP_PROVIDERS["gemini-cli"]
        assert _preconfigured_credentials(provider, (), {"GEMINI_API_KEY": "k"}) == [
            "GEMINI_API_KEY"
        ]

    def test_ignores_another_providers_key(self):
        provider = ACP_PROVIDERS["gemini-cli"]
        assert _preconfigured_credentials(provider, (), {"OPENAI_API_KEY": "k"}) == []

    def test_reports_a_materialised_file_secret_pointed_at_a_directory(self, tmp_path):
        spec = ACP_PROVIDERS["codex"].file_secrets[0]
        (tmp_path / spec.filename).write_text(_CHATGPT_AUTH_JSON, encoding="utf-8")
        env = {spec.env_var: str(tmp_path)}
        assert _preconfigured_credentials(None, (spec,), env) == [spec.secret_name]

    def test_ignores_a_file_secret_that_cannot_authenticate(self, tmp_path):
        """存在但不可用的是最需要警告的情况：
        服务器提供了一种使用该文件的方法并拒绝了它。"""
        spec = ACP_PROVIDERS["codex"].file_secrets[0]
        (tmp_path / spec.filename).write_text('{"tokens": null}', encoding="utf-8")
        env = {spec.env_var: str(tmp_path)}
        assert _preconfigured_credentials(None, (spec,), env) == []

    def test_ignores_a_file_secret_whose_file_is_absent(self, tmp_path):
        spec = ACP_PROVIDERS["codex"].file_secrets[0]
        env = {spec.env_var: str(tmp_path)}
        assert _preconfigured_credentials(None, (spec,), env) == []

    def test_no_provider_and_no_specs_reports_nothing(self):
        assert _preconfigured_credentials(None, (), {"ANTHROPIC_API_KEY": "k"}) == []


class TestAuthSelectionFailureReason:
    """原因行必须指出实际缺少的内容。

    它之前无法描述的两个形状：一个没有设置自身密钥的提供者，以及一个仅能通过交互式终
    端完成的登录 —— 这就是每个最近添加的框架宣称的，所以旧文本“没有可用的凭据源”暗
    示了一个缺失的凭据，而None本应出现。
    """

    @staticmethod
    def _method(method_id: str, method_type: str | None = None) -> MagicMock:
        m = MagicMock()
        m.id = method_id
        m.type = method_type
        return m

    def test_names_the_providers_unset_key_var(self):
        reason = _auth_selection_failure_reason(
            [self._method("some-login")], {}, ACP_PROVIDERS["gemini-cli"]
        )
        assert "GEMINI_API_KEY is unset" in reason

    def test_names_a_terminal_only_login(self):
        reason = _auth_selection_failure_reason(
            [self._method("login", "terminal")], {}, None
        )
        assert "login needs an interactive terminal" in reason

    def test_falls_back_to_the_generic_reason(self):
        assert (
            _auth_selection_failure_reason([self._method("mystery")], {}, None)
            == "no supported credential source is available"
        )


class TestUnperformableAuthMethodLogging:
    """当服务器唯一的身份验证方法是运行时方法时，日志显示的内容
    无法执行 - 交互式登录，这是每个最近添加的工具所宣传的内容。

    端点仍然启动，因为这些 CLIs 在生成时从环境读取密钥，所以警告“没有可用的凭据”。 每
    次启动时“会话创建可能会失败”既令人震惊又错误。
    """

    @staticmethod
    def _start_with_auth_method(agent, tmp_path, *, method_id: str, registry_secrets):
        from pydantic import SecretStr

        from openhands.sdk.secret import StaticSecret

        state = _make_state(tmp_path)
        for name, value in registry_secrets.items():
            state.secret_registry.update_secrets(
                {name: StaticSecret(value=SecretStr(value))}
            )
        conn = TestACPFileSecretMaterialisation._make_conn(
            agent_name="gemini-cli", auth_method=method_id
        )
        with patch.dict("os.environ", {}, clear=True):
            TestACPFileSecretMaterialisation._run_start(agent, state, conn=conn)

    def test_reports_the_credential_in_use_instead_of_warning(self, tmp_path, caplog):
        agent = _make_agent(acp_server="gemini-cli")
        with caplog.at_level("INFO"):
            self._start_with_auth_method(
                agent,
                tmp_path,
                method_id="some-interactive-login",
                registry_secrets={"GEMINI_API_KEY": "k"},
            )

        assert "using the already-configured credential(s) ['GEMINI_API_KEY']" in (
            caplog.text
        )
        assert "session creation may fail" not in caplog.text

    def test_still_warns_when_nothing_is_configured(self, tmp_path, caplog):
        agent = _make_agent(acp_server="gemini-cli")
        with caplog.at_level("INFO"):
            self._start_with_auth_method(
                agent,
                tmp_path,
                method_id="some-interactive-login",
                registry_secrets={},
            )

        assert "session creation may fail" in caplog.text
        assert "GEMINI_API_KEY is unset" in caplog.text
