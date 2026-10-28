"""演示设置和机密 API 的示例。

此示例显示了管理机密的推荐工作流程：
1. 通过 PUT /api/settings/secrets 存储机密（在 REST 处加密）
2. 通过 LookupSecret 进行的对话中参考机密
3. 智能体通过环境变量使用机密 ($SECRET_NAME)
4. 通过 DELETE /api/settings/secrets/{name} 清理机密

该模式可以：
- 安全机密存储（在 REST 处使用 OH_SECRET_KEY 加密）
- 运行时的懒惰机密解析（通过 LookupSecret URLs）
- 细粒度机密生命周期管理（CRUD 操作）
- 机密访问的审核跟踪
"""

import os
import tempfile
import time
from uuid import UUID

import httpx
from scripts.utils import ManagedAPIServer

from openhands.sdk import get_logger
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)


# 从环境中获取 LLM 配置
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
llm_model = os.getenv("LLM_MODEL", "gpt-5.5")
llm_base_url = os.getenv("LLM_BASE_URL")  # 可选定制底座 URL

with ManagedAPIServer(
    port=8765,
    extra_env={
        "OH_SECRET_KEY": "example-secret-key-for-demo-only-32b",
        "TMUX_TMPDIR": "/tmp/oh-tmux",
    },
    health_request_timeout=2.0,
) as server:
    client = httpx.Client(base_url=server.base_url, timeout=120.0)

    try:
        # ══════════════════════════════════════════════════════════════ 第一部分：通过
        # 设置 LLM 存储设置 API ════════════════════════════════════════════════════════
        # ══════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔧 Storing LLM configuration via Settings API")
        logger.info("=" * 60)

        # 存储 LLM 配置 - API 密钥在 REST 处加密
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
        logger.info(f"   - LLM model: {settings['agent_settings']['llm']['model']}")
        if llm_base_url:
            logger.info(f"   - Base URL: {llm_base_url}")
        logger.info(f"   - API key set: {settings['llm_api_key_is_set']}")

        # ══════════════════════════════════════════════════════════════ 第二部分：通过
        # 机密存储自定义机密 API ═══════════════════════════════════════════════════════
        # ═══════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🔐 Storing custom secret via Secrets API")
        logger.info("=" * 60)

        # 存储自定义机密 - 这可以是 API token、数据库密码等。 机密在 REST 处使用
        # OH_SECRET_KEY 加密
        #
        secret_name = "MY_PROJECT_TOKEN"
        secret_value = "super-secret-token-12345"

        response = client.put(
            "/api/settings/secrets",
            json={
                "name": secret_name,
                "value": secret_value,
                "description": "Example project token for demonstration",
            },
        )
        assert response.status_code == 200, f"PUT secret failed: {response.text}"
        logger.info(f"✅ Created secret: {secret_name}")

        # 要验证的列表机密（值不公开）
        response = client.get("/api/settings/secrets")
        assert response.status_code == 200
        secrets_list = response.json()["secrets"]
        logger.info(f"✅ Server has {len(secrets_list)} secret(s) stored")
        for secret in secrets_list:
            logger.info(f"   - {secret['name']}: {secret.get('description', '')}")

        # ══════════════════════════════════════════════════════════════ 第三部分：与
        # LookupSecret 参考开始对话 ════════════════════════════════════════════════════
        # ══════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🤖 Starting conversation with secret reference")
        logger.info("=" * 60)

        # 创建工作区目录
        temp_workspace_dir = tempfile.mkdtemp(prefix="secrets_api_demo_")

        # 构建 LookupSecret URL - Agent Server 在运行时解决此问题 URL 指向同一服务器上的
        # 机密端点
        #
        lookup_url = f"{server.base_url}/api/settings/secrets/{secret_name}"

        # 与 LookupSecret 引用开始对话机密将在智能体需要时延迟解析
        #
        start_request = {
            "agent": {
                "kind": "Agent",
                "llm": llm_config,  # 使用相同的 LLM 配置（型号、api_key、base_url）
                "tools": [
                    {"name": TerminalTool.name},
                    {"name": FileEditorTool.name},
                ],
            },
            "workspace": {"working_dir": temp_workspace_dir},
            # 通过 LookupSecret 引用存储的机密这将在智能体中创建环境变量 $
            # MY_PROJECT_TOKEN
            #
            "secrets": {
                secret_name: {
                    "kind": "LookupSecret",
                    "url": lookup_url,
                    "description": "Project token resolved from secrets API",
                }
            },
            "initial_message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Echo the value of the ${secret_name} environment "
                        "variable to see if you have access. "
                        "If so just respond `YES`, otherwise `NO`.",
                    }
                ],
                "run": True,  # 发送消息后自动运行
            },
        }

        response = client.post("/api/conversations", json=start_request)
        assert response.status_code == 201, (
            f"Start conversation failed: {response.text}"
        )
        conversation_info = response.json()
        conversation_id = UUID(conversation_info["id"])

        logger.info("✅ Conversation started!")
        logger.info(f"   - Conversation ID: {conversation_id}")
        logger.info(f"   - Secret '{secret_name}' available as env var")

        # ══════════════════════════════════════════════════════════════ 第四部分：等待
        # 智能体完成══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("⏳ Waiting for agent to complete task...")
        logger.info("=" * 60)

        # 投票对话直至智能体结束
        max_wait = 120  # 秒
        poll_interval = 2
        elapsed = 0
        execution_status = "unknown"

        while elapsed < max_wait:
            response = client.get(f"/api/conversations/{conversation_id}")
            assert response.status_code == 200
            conversation_data = response.json()
            execution_status = conversation_data.get("execution_status", "unknown")

            if execution_status in ("stopped", "paused", "error"):
                break

            logger.info(f"   Status: {execution_status} (waited {elapsed}s)")
            time.sleep(poll_interval)
            elapsed += poll_interval

        logger.info(f"✅ Agent finished with status: {execution_status}")

        # 获取智能体的最终响应以验证任务是否已完成
        response = client.get(
            f"/api/conversations/{conversation_id}/agent_final_response"
        )
        accumulated_cost = 0.0
        if response.status_code == 200:
            result = response.json()
            agent_response = result.get("response", "")
            if agent_response:
                # 截断长响应以供显示
                display_response = (
                    agent_response[:200] + "..."
                    if len(agent_response) > 200
                    else agent_response
                )
                logger.info(f"   Agent response: {display_response}")
                logger.info("   ✅ Agent completed the task using the secret!")

        # 从统计数据中获取对话指标
        response = client.get(f"/api/conversations/{conversation_id}")
        if response.status_code == 200:
            conversation_data = response.json()
            # 指标按 stats.usage_to_metrics 中的 LLM 使用情况进行跟踪
            stats = conversation_data.get("stats") or {}
            usage_to_metrics = stats.get("usage_to_metrics") or {}
            # 所有 LLM 次使用的总和 accumulated_cost
            accumulated_cost = sum(
                m.get("accumulated_cost", 0.0) for m in usage_to_metrics.values()
            )

        # 清理 - 删除对话
        client.delete(f"/api/conversations/{conversation_id}")
        logger.info("   Conversation deleted")

        # ══════════════════════════════════════════════════════════════ 第五部分：清理
        # - 删除机密 ══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("🧹 Cleaning up - deleting secret")
        logger.info("=" * 60)

        # 使用后删除机密
        response = client.delete(f"/api/settings/secrets/{secret_name}")
        assert response.status_code == 200, f"DELETE secret failed: {response.text}"
        logger.info(f"✅ Deleted secret: {secret_name}")

        # 验证删除
        response = client.get(f"/api/settings/secrets/{secret_name}")
        assert response.status_code == 404
        logger.info("✅ Verified deletion (secret no longer accessible)")

        # ══════════════════════════════════════════════════════════════ 第六部分：测试
        # 机密名称验证 ══════════════════════════════════════════════════════════════
        #
        logger.info("\n" + "=" * 60)
        logger.info("⚠️  Testing secret name validation")
        logger.info("=" * 60)

        # 无效：以数字开头
        response = client.put(
            "/api/settings/secrets",
            json={"name": "123_invalid", "value": "test"},
        )
        assert response.status_code == 422
        logger.info("✅ Rejected '123_invalid' (starts with number)")

        # 无效：包含连字符
        response = client.put(
            "/api/settings/secrets",
            json={"name": "invalid-name", "value": "test"},
        )
        assert response.status_code == 422
        logger.info("✅ Rejected 'invalid-name' (contains hyphen)")

        logger.info("\n" + "=" * 60)
        logger.info("🎉 All Settings and Secrets API tests passed!")
        logger.info("=" * 60)

        print(f"EXAMPLE_COST: {accumulated_cost}")

    finally:
        client.close()
