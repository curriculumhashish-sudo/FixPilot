"""演示设置驱动对话的 workspace.get_llm() 的示例。

此示例演示如何使用新的 RemoteWorkspace 设置方法和 API 键身份验证进行安全访问：

1. 启动配置了会话 API 密钥的智能体服务器
2. 通过设置 API 配置 LLM 设置（需要 API 密钥身份验证）
3. 使用 workspace.get_llm() 检索配置的 LLM （也经过身份验证）
4. 使用检索到的 LLM 开始对话

安全模型：
- 智能体-服务器配置为 SESSION_API_KEY env var
- 所有请求必须包含 X-Session-API-Key 标头
- RemoteWorkspace.api_key 参数自动设置此标头
- LookupSecrets 在其标头中包含 API 键以进行解析

该模式可以：
- 智能体服务器上的安全集中式 LLM 配置
- 经过身份验证的设置访问和机密
- 所有工作区操作均保持一致的安全性
"""

import os

import httpx
from scripts.utils import ManagedAPIServer

from openhands.sdk import Conversation, get_logger
from openhands.sdk.workspace.remote.base import RemoteWorkspace
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)


# 从环境中获取 LLM 配置
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
llm_model = os.getenv("LLM_MODEL", "gpt-5.5")
llm_base_url = os.getenv("LLM_BASE_URL")  # 可选定制底座 URL

with ManagedAPIServer(
    port=8766,
    extra_env={
        "OH_SECRET_KEY": "example-secret-key-for-demo-only-32b",
        "TMUX_TMPDIR": "/tmp/oh-tmux",
    },
    use_session_api_key=True,
    health_request_timeout=2.0,
) as server:
    # 为设置 API - 必须创建 HTTP 客户端，包括会话 API 密钥！ X-Session-API-Key 标头对所
    # 有请求进行身份验证
    #
    assert server.session_api_key is not None  # 通过use_session_api_key=True设置
    client = httpx.Client(
        base_url=server.base_url,
        timeout=120.0,
        headers={"X-Session-API-Key": server.session_api_key},
    )

    try:
        # ══════════════════════════════════════════════════════════════ 第0部分：演示身
        # 份验证要求 ══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔐 Demonstrating API key authentication")
        logger.info("=" * 60)

        # 请求 WITHOUT API 密钥应该失败（401 未经授权）
        unauthenticated = httpx.Client(base_url=server.base_url, timeout=10.0)
        response = unauthenticated.get("/api/settings")
        assert response.status_code == 401, (
            f"Expected 401 without API key, got {response.status_code}"
        )
        logger.info("✅ Request without API key rejected (401 Unauthorized)")
        unauthenticated.close()

        # 请求 WITH API 键应该成功
        response = client.get("/api/settings")
        assert response.status_code == 200, f"Authenticated request failed: {response}"
        logger.info("✅ Request with API key accepted (200 OK)")

        # ══════════════════════════════════════════════════════════════ 第一部分：配置
        # LLM 设置在智能体-服务器上 ════════════════════════════════════════════════════
        # ══════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔧 Configuring LLM settings on agent-server")
        logger.info("=" * 60)

        # 通过设置 API 存储 LLM 配置
        llm_config: dict[str, str] = {
            "model": llm_model,
            "api_key": api_key,
        }
        if llm_base_url:
            llm_config["base_url"] = llm_base_url

        response = client.patch(
            "/api/settings",
            json={"agent_settings_diff": {"llm": llm_config}},
        )
        assert response.status_code == 200, f"PATCH settings failed: {response.text}"
        settings = response.json()

        logger.info("✅ LLM settings stored successfully")
        logger.info(f"   - Model: {settings['agent_settings']['llm']['model']}")
        logger.info(f"   - API key set: {settings['llm_api_key_is_set']}")

        # ═══════════════════════════════ Part 2: Create 工作区 and Retrieve LLM via
        # get_llm() ══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔗 Creating workspace and retrieving LLM configuration")
        logger.info("=" * 60)

        # 用API键身份验证创建一个RemoteWorkspace！ api_key 用于所有请求上的 X-Session-
        # API-Key 标头，包括 get_llm()、get_secrets() 和 get_mcp_config()。
        #
        workspace = RemoteWorkspace(
            host=server.base_url,
            working_dir="/tmp/workspace_get_llm_demo",
            api_key=server.session_api_key,  # 验证工作区个请求
        )

        logger.info("✅ Workspace created with session API key")

        # 使用 get_llm() 检索智能体服务器上配置的 LLM！ 这调用 GET /api/settings 两者：
        # - X-会话-API-密钥 (身份验证)
        # - X-Expose-机密：明文（获取实际的API键值）
        llm = workspace.get_llm()

        logger.info("✅ Retrieved LLM from workspace.get_llm()")
        logger.info(f"   - Model: {llm.model}")
        logger.info(f"   - Base URL: {llm.base_url or '(default)'}")

        # 您还可以覆盖特定设置：
        # llm_custom = workspace.get_llm(model="gpt-4o", temperature=0.5)

        # ══════════════════════════════════════════════════════════════ 第三部分：创建
        # 智能体并开始对话 ═════════════════════════════════════════════════════════════
        # ═
        #
        logger.info("\n" + "=" * 60)
        logger.info("🤖 Creating agent with retrieved LLM")
        logger.info("=" * 60)

        # 使用工作区设置中的 LLM 创建智能体
        agent = get_default_agent(llm=llm, cli_mode=True)

        logger.info("✅ Agent created with workspace LLM settings")

        # ══════════════════════════════════════════════════════════════ 第四部分：开始
        # 对话并运行任务 ══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("💬 Starting conversation")
        logger.info("=" * 60)

        # 使用工作区和智能体创建对话
        conversation = Conversation(
            agent=agent,
            workspace=workspace,
        )

        try:
            logger.info(f"   Conversation ID: {conversation.state.id}")

            # 发送一个简单的任务
            conversation.send_message("What is 2 + 2? Just respond with the number.")
            logger.info("📝 Sent message, running conversation...")
            conversation.run()

            logger.info("✅ Conversation completed!")
            logger.info(f"   Status: {conversation.state.execution_status}")

            # 获取成本指标
            cost = (
                conversation.conversation_stats.get_combined_metrics().accumulated_cost
            )
            logger.info(f"   Cost: ${cost:.6f}")

            print(f"EXAMPLE_COST: {cost}")

        finally:
            conversation.close()
            logger.info("🧹 Conversation closed")

        # ══════════════════════════════════════════════════════════════ 第五部分：演示
        # get_secrets() 和 API 密钥认证 ════════════════════════════════════════════════
        # ══════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔐 Demonstrating get_secrets() and get_mcp_config()")
        logger.info("=" * 60)

        # 存储测试机密
        response = client.put(
            "/api/settings/secrets",
            json={
                "name": "TEST_SECRET",
                "value": "secret-value-123",
                "description": "Test secret for demo",
            },
        )
        assert response.status_code == 200

        # 通过 workspace.get_secrets() 检索机密返回的 LookupSecrets 在其标头中包含 API
        # 密钥，以便在智能体服务器解析时可以进行身份验证
        #
        workspace_secrets = workspace.get_secrets()
        logger.info(
            f"✅ Retrieved {len(workspace_secrets)} secret(s) via "
            "workspace.get_secrets()"
        )
        for name, lookup_secret in workspace_secrets.items():
            logger.info(f"   - {name}: LookupSecret")
            logger.info(f"     URL: {lookup_secret.url}")
            # LookupSecret 包含 X-Session-API-Key 标头，以便在解析时可以进行身份验证
            #
            has_auth = "X-Session-API-Key" in (lookup_secret.headers or {})
            logger.info(f"     Has API key header: {has_auth}")

        # 清理测试机密
        client.delete("/api/settings/secrets/TEST_SECRET")
        logger.info("   Test secret deleted")

        # 如果没有设置 MCP 配置，get_mcp_config() 返回空字典
        mcp_config = workspace.get_mcp_config()
        logger.info(f"✅ MCP config: {mcp_config or '(none configured)'}")

        logger.info("\n" + "=" * 60)
        logger.info("🎉 Example completed successfully!")
        logger.info("=" * 60)
        logger.info("""
Key takeaways:
1. Agent-server can be secured with SESSION_API_KEY env var
2. RemoteWorkspace.api_key passes X-Session-API-Key header
3. workspace.get_llm() retrieves LLM with authentication
4. workspace.get_secrets() returns LookupSecrets with auth headers
5. workspace.get_mcp_config() retrieves MCP config with auth
""")

    finally:
        client.close()
