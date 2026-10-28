"""测试 MCP 服务器机密序列化安全性。

这些测试验证机密扩展到 mcp_config 确实不通过序列化路径（持久化、WebSocket 事件、API
响应）泄漏。

See: https://github.com/OpenHands/software-agent-sdk/pull/2873#issuecomment-4273848645
"""

import json
import uuid

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.llm import LLM
from openhands.sdk.mcp.config import coerce_mcp_config, dump_mcp_config
from openhands.sdk.workspace import LocalWorkspace


# 用于测试的清晰可辨的机密值
SECRET_VALUE = "ghp_SUPER_SECRET_TOKEN_12345_SHOULD_NOT_LEAK"


@pytest.fixture
def agent_with_secret_in_mcp_config():
    """在 mcp_config 中创建一个具有机密值的智能体。

    这模拟了状态之后 expand_mcp_variables() 已将 ${GITHUB_TOKEN} 占位符解析为其实际机
    密值。
    """
    llm = LLM(model="test-model", api_key=SecretStr("test-key"))
    mcp_config = {
        "github": {
            "command": "uvx",
            "args": ["mcp-server-github"],
            "env": {
                # 这是扩展的机密 - expand_mcp_variables() 解析 ${GITHUB_TOKEN} 后
                # mcp_config 中的内容
                #
                "GITHUB_TOKEN": SECRET_VALUE
            },
        }
    }
    return Agent(llm=llm, mcp_config=coerce_mcp_config(mcp_config))


class TestMcpSecretsDoNotLeakToPersistence:
    """测试 mcp_config 机密不会泄漏到磁盘持久化。"""

    def test_secrets_not_in_base_state_json(
        self, agent_with_secret_in_mcp_config, tmp_path
    ):
        """验证 mcp_config 中的机密是否已将不写入 base_state.json。

        当 ConversationState 保留到磁盘时，应排除扩展为 mcp_config 的机密或已脱敏。
        """
        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))
        persistence_dir = tmp_path / "persistence"

        # 创建状态（触发持久化）
        _ = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent_with_secret_in_mcp_config,
            workspace=workspace,
            persistence_dir=str(persistence_dir),
        )

        # 从磁盘读取已持久化状态
        base_state_path = persistence_dir / "base_state.json"
        assert base_state_path.exists(), "base_state.json should exist"

        with open(base_state_path) as f:
            persisted_data = f.read()

        # 机密值应不出现在已持久化文件中
        assert SECRET_VALUE not in persisted_data, (
            f"Secret value '{SECRET_VALUE}' was found in base_state.json! "
            "Secrets in mcp_config should be excluded or redacted during persistence."
        )

    def test_mcp_config_excluded_or_redacted_in_persistence(
        self, agent_with_secret_in_mcp_config, tmp_path
    ):
        """验证 mcp_config 在持久化中得到安全处理。

        应完全排除 mcp_config，或者其中的敏感值应为已脱敏。
        """
        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))
        persistence_dir = tmp_path / "persistence"

        # 创建状态（触发持久化）
        _ = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent_with_secret_in_mcp_config,
            workspace=workspace,
            persistence_dir=str(persistence_dir),
        )

        base_state_path = persistence_dir / "base_state.json"
        with open(base_state_path) as f:
            persisted_json = json.load(f)

        agent_data = persisted_json.get("agent", {})
        mcp_config = agent_data.get("mcp_config", {})

        # 如果存在 mcp_config，请检查 env 值是否为已脱敏
        if mcp_config:
            mcp_str = json.dumps(mcp_config)
            assert SECRET_VALUE not in mcp_str, (
                "Secret value found in persisted mcp_config! "
                "Either exclude mcp_config or redact sensitive env values."
            )


class TestMcpSecretsDoNotLeakToWebSocket:
    """测试 mcp_config 机密不会通过 WebSocket 事件泄漏。"""

    def test_secrets_not_in_state_update_event(
        self, agent_with_secret_in_mcp_config, tmp_path
    ):
        """验证机密不会通过 ConversationStateUpdateEvent 泄漏。

        ConversationStateUpdateEvent.from_conversation_state() 序列化 WebSocket 传输
        的状态。 机密
        不得包含在内。
        """
        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent_with_secret_in_mcp_config,
            workspace=workspace,
            persistence_dir=str(tmp_path / "persistence"),
        )

        # 创建将通过 WebSocket 发送的事件
        event = ConversationStateUpdateEvent.from_conversation_state(state)

        # 序列化事件值（这是通过线路传输的值）
        event_json = json.dumps(event.value)

        assert SECRET_VALUE not in event_json, (
            f"Secret value '{SECRET_VALUE}' was found in WebSocket event! "
            "Secrets in mcp_config should be excluded from state update events."
        )

    def test_agent_field_update_does_not_leak_secrets(
        self, agent_with_secret_in_mcp_config, tmp_path
    ):
        """当智能体字段更改触发器回调时，验证机密不会泄漏。

        当 state.agent 更新时，__setattr__ 回调发送带有新值的
        ConversationStateUpdateEvent。 这不得包括
        mcp_config 中的机密。
        """
        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent_with_secret_in_mcp_config,
            workspace=workspace,
            persistence_dir=str(tmp_path / "persistence"),
        )

        # 跟踪通过回调发送的事件
        captured_events = []

        def capture_callback(event):
            captured_events.append(event)

        state.set_on_state_change(capture_callback)

        # 触发智能体更新（模拟 _ensure_plugins_loaded 的操作）
        new_agent = agent_with_secret_in_mcp_config.model_copy()
        with state:
            state.agent = new_agent

        # 检查所有捕获的事件是否存在机密泄漏
        for event in captured_events:
            if hasattr(event, "value"):
                event_str = json.dumps(event.value) if event.value else ""
                assert SECRET_VALUE not in event_str, (
                    f"Secret value found in state change callback event! "
                    f"Event key: {getattr(event, 'key', 'unknown')}"
                )


class TestMcpSecretsDoNotLeakToAPI:
    """测试 mcp_config 机密不会通过 API 响应泄漏。"""

    def test_secrets_not_in_state_model_dump(
        self, agent_with_secret_in_mcp_config, tmp_path
    ):
        """通过 state.model_dump() 验证机密不会泄漏。

        state.model_dump(mode="JSON") 由API 端点到序列化对话状态使用。 mcp_config 中
        的机密必须排除。
        """
        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))

        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent_with_secret_in_mcp_config,
            workspace=workspace,
            persistence_dir=str(tmp_path / "persistence"),
        )

        # 这就是 API 端点用于序列化的内容
        state_dump = state.model_dump(mode="json")
        state_json = json.dumps(state_dump)

        assert SECRET_VALUE not in state_json, (
            f"Secret value '{SECRET_VALUE}' was found in state.model_dump()! "
            "Secrets in mcp_config should be excluded from API responses."
        )

    def test_agent_model_dump_excludes_mcp_secrets(
        self, agent_with_secret_in_mcp_config
    ):
        """验证 agent.model_dump() 是否从 mcp_config 中排除机密。

        智能体通常是独立的已序列化。 应排除 mcp_config 中的机密或已脱敏。
        """
        agent_dump = agent_with_secret_in_mcp_config.model_dump(mode="json")
        agent_json = json.dumps(agent_dump)

        assert SECRET_VALUE not in agent_json, (
            f"Secret value '{SECRET_VALUE}' was found in agent.model_dump()! "
            "Secrets in mcp_config should be excluded from serialization."
        )


class TestMcpConfigPreservation:
    """验证 mcp_config 功能在安全的情况下得到保留的测试。"""

    def test_mcp_config_still_accessible_in_memory(
        self, agent_with_secret_in_mcp_config
    ):
        """验证 mcp_config 和机密在内存中仍然可用。

        虽然机密不应该序列化，但内存中 mcp_config 应保留机密以进行实际的 MCP 服务器初
        始化。
        """
        # 机密应该可以在内存中访问以供实际使用
        env_config = dump_mcp_config(agent_with_secret_in_mcp_config.mcp_config)[
            "github"
        ]["env"]
        assert env_config["GITHUB_TOKEN"] == SECRET_VALUE, (
            "mcp_config should retain secrets in memory for runtime use"
        )

    def test_non_secret_mcp_server_values_persist_with_cipher(self, tmp_path):
        """验证在对持久化使用密码时是否保留了 mcp_config。

        当提供密码（生产流程）时，mcp_config 应在保存时加密并在恢复时解密，从而保留所
        有值。
        """
        from openhands.sdk.utils.cipher import Cipher

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        mcp_config = {
            "mcpServers": {
                "fetch": {
                    "command": "uvx",
                    "args": ["mcp-server-fetch"],
                    "env": {"API_KEY": "sk-mcp-secret"},
                }
            }
        }
        agent = Agent(
            llm=llm,
            mcp_config=coerce_mcp_config(mcp_config["mcpServers"]),
        )
        cipher = Cipher(secret_key="test-encryption-key")

        workspace = LocalWorkspace(working_dir=str(tmp_path / "workspace"))
        # 使用密码创建状态（通过加密触发持久化）
        state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=str(tmp_path / "persistence"),
            cipher=cipher,
        )

        base_state_path = tmp_path / "persistence" / "base_state.json"
        with open(base_state_path) as f:
            persisted_json = json.load(f)

        agent_data = persisted_json.get("agent", {})

        encrypted_key = agent_data["mcp_config"]["fetch"]["env"]["API_KEY"]
        assert encrypted_key != "sk-mcp-secret"
        decrypted_key = cipher.decrypt(encrypted_key)
        assert decrypted_key is not None
        assert decrypted_key.get_secret_value() == "sk-mcp-secret"
        assert "sk-mcp-secret" not in json.dumps(agent_data), (
            "plaintext mcp_config secrets should not be present when encrypted"
        )

        # 验证往返：使用相同密码恢复应获得原始配置
        restored_state = ConversationState.create(
            id=state.id,
            agent=agent,
            workspace=workspace,
            persistence_dir=str(tmp_path / "persistence"),
            cipher=cipher,
        )
        # 使用了运行时智能体，但解密应该可以工作
        assert (
            dump_mcp_config(restored_state.agent.mcp_config) == mcp_config["mcpServers"]
        )
