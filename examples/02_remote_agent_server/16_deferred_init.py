"""演示 Agent Server 的延迟初始化（热池）模式的示例。

在热池部署中，服务器 Pod 在用户与用户匹配之前会进行预热。 ``OH_DEFERRED_INIT=true``
pod启动时，VSCode 状态机服务（如
``/api/*``工具预加载等）正常启动，但所有``POST /api/init``路由返回503，直到凭据提供运
行时配置（工作区路径，会话密钥）。

编排器使用服务器的引导机密密钥 (``OH_SECRET_KEY`` / ``X-Init-API-Key``) 来验证 init
调用，该密钥已出于加密目的而保存。

此处展示的生命周期：
  1. 服务器以休眠模式启动。
  2. ``GET /api/init``报告状态=休眠。
  3. ``GET /api/conversations`` 返回 503（休眠门处于活动状态）。
  4. ``POST /api/init`` 传递运行时配置 → 服务器转换为就绪状态。
  5. ``GET /api/init`` 报告状态=就绪。
  6. 对话在现已准备就绪的服务器上正常运行。
"""

import os
import tempfile
import time
from uuid import UUID

import httpx
from scripts.utils import ManagedAPIServer

from openhands.sdk import get_logger


logger = get_logger(__name__)

# ── LLM 配置 ──────────────────────────────────────────────────────────────

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
llm_model = os.getenv("LLM_MODEL", "gpt-5.5")
llm_base_url = os.getenv("LLM_BASE_URL")

# 在 pod 与用户匹配之前，协调器就知道该密钥。 它用于验证 POST /api/init 并用作加密机密。
#
BOOTSTRAP_SECRET_KEY = "demo-warm-pool-bootstrap-key-32b!"

# ── 服务器生命周期──────────────────────────────────────────────────────────

with ManagedAPIServer(
    port=8003,
    extra_env={
        "OH_DEFERRED_INIT": "true",
        "OH_SECRET_KEY": BOOTSTRAP_SECRET_KEY,
        "TMUX_TMPDIR": "/tmp/oh-tmux-deferred",
    },
) as server:
    client = httpx.Client(base_url=server.base_url, timeout=120.0)

    try:
        # ── 1. 确认休眠状态──────────────────────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("📊 Step 1: checking initial (dormant) state")
        logger.info("=" * 60)

        resp = client.get("/api/init")
        assert resp.status_code == 200, f"GET /api/init failed: {resp.text}"
        init_status = resp.json()
        assert init_status["state"] == "dormant", (
            f"Expected dormant, got: {init_status['state']}"
        )
        logger.info(f"✅ Server is dormant — {init_status}")

        # ── 2. 验证休眠门区块/api/* ──────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("🚧 Step 2: dormant gate returns 503 on /api/conversations")
        logger.info("=" * 60)

        resp = client.get("/api/conversations")
        assert resp.status_code == 503, (
            f"Expected 503 from dormant gate, got {resp.status_code}"
        )
        logger.info("✅ /api/conversations correctly returns 503 while dormant")

        # ── 3. 通过POST/api/init激活──────────────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("🚀 Step 3: activating server via POST /api/init")
        logger.info("=" * 60)

        temp_workspace_dir = tempfile.mkdtemp(prefix="deferred_init_demo_")

        # 在真正的热池部署中，服务器在冷启动时不应具有的凭据（e.g.，用户的 LLM API 密钥
        # ）将到达此处。
        #
        llm_env: dict[str, str] = {"LLM_API_KEY": api_key}
        if llm_base_url:
            llm_env["LLM_BASE_URL"] = llm_base_url

        init_body: dict = {
            # 将用户凭据传递到服务器环境中。
            "env": llm_env,
        }

        resp = client.post(
            "/api/init",
            json=init_body,
            headers={"X-Init-API-Key": BOOTSTRAP_SECRET_KEY},
        )
        assert resp.status_code == 200, f"POST /api/init failed: {resp.text}"
        init_status = resp.json()
        assert init_status["state"] == "ready", (
            f"Expected ready after init, got: {init_status['state']}"
        )
        logger.info(f"✅ Server is now ready — {init_status}")

        # ── 4. 通过GET /api/init确认准备就绪 ────────────────────────────────
        resp = client.get("/api/init")
        assert resp.status_code == 200
        assert resp.json()["state"] == "ready"
        logger.info("✅ GET /api/init confirms ready state")

        # ── 5. 在现在准备好的服务器上运行对话────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("🤖 Step 5: running a conversation on the ready server")
        logger.info("=" * 60)

        llm_config: dict[str, str] = {"model": llm_model, "api_key": api_key}
        if llm_base_url:
            llm_config["base_url"] = llm_base_url

        start_request: dict = {
            "agent": {
                "kind": "Agent",
                "llm": llm_config,
                "tools": [],
            },
            "workspace": {"working_dir": temp_workspace_dir},
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": "Reply with just the number 42."}],
                "run": True,
            },
        }

        resp = client.post("/api/conversations", json=start_request)
        assert resp.status_code == 201, f"Start conversation failed: {resp.text}"
        conversation_id = UUID(resp.json()["id"])
        logger.info(f"✅ Conversation started: {conversation_id}")

        # 轮询直至智能体完成。
        max_wait = 120
        elapsed = 0
        execution_status = "unknown"
        while elapsed < max_wait:
            resp = client.get(f"/api/conversations/{conversation_id}")
            assert resp.status_code == 200
            data = resp.json()
            execution_status = data.get("execution_status", "unknown")
            # 每个 ConversationExecutionStatus.is_terminal() 的终端状态。
            if execution_status in ("finished", "error", "stuck"):
                break
            logger.info(f"   status: {execution_status} ({elapsed}s elapsed)")
            time.sleep(2)
            elapsed += 2

        logger.info(f"✅ Conversation finished — status: {execution_status}")
        assert execution_status == "finished", (
            f"Unexpected final status: {execution_status}"
        )

        resp = client.get(f"/api/conversations/{conversation_id}/agent_final_response")
        if resp.status_code == 200:
            agent_response = resp.json().get("response", "")
            logger.info(f"   Agent response: {agent_response!r}")

        # 收集成本指标。
        accumulated_cost = 0.0
        resp = client.get(f"/api/conversations/{conversation_id}")
        if resp.status_code == 200:
            stats = resp.json().get("stats") or {}
            usage_to_metrics = stats.get("usage_to_metrics") or {}
            accumulated_cost = sum(
                m.get("accumulated_cost", 0.0) for m in usage_to_metrics.values()
            )

        client.delete(f"/api/conversations/{conversation_id}")
        logger.info("   Conversation deleted")

        logger.info("\n" + "=" * 60)
        logger.info("🎉 Deferred-init example completed successfully!")
        logger.info("=" * 60)

        print(f"EXAMPLE_COST: {accumulated_cost}")

    finally:
        client.close()
