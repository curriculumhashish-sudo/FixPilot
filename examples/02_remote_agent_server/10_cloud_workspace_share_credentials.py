"""Example: 通过 OpenHandsCloudWorkspace 继承 SaaS 凭据。

示例展示了简化流程，其中您的 OpenHands 云账户的 LLM 配置和机密会自动继承 —— 您无需单
独提供 LLM_API_KEY。

与 07_convo_with_cloud_workspace.py（需要单独的 LLM_API_KEY）相比，此方法使用：
  - workspace.get_llm() → 从您的 SaaS 帐户获取 LLM 配置
  - workspace.get_secrets() → 为您的机密构建惰性 LookupSecret 引用

原始机密值永远不会通过 SDK 客户端传输。 沙箱内的智能体-服务器根据需要解析它们。

用途：
  uv run examples/02_remote_agent_server/10_cloud_workspace_share_credentials.py

要求：
  - OPENHANDS_CLOUD_API_KEY: OpenHands 云的 API 密钥（仅需要凭据）

可选：
  - OPENHANDS_CLOUD_API_URL: 覆盖云 API URL（默认值： https://app.all-hands.dev ）
  - LLM_MODEL: 从您的 SaaS 设置覆盖模型
"""

import os
import time

from openhands.sdk import (
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import OpenHandsCloudWorkspace


logger = get_logger(__name__)


cloud_api_key = os.getenv("OPENHANDS_CLOUD_API_KEY")
if not cloud_api_key:
    logger.error("OPENHANDS_CLOUD_API_KEY required")
    exit(1)

cloud_api_url = os.getenv("OPENHANDS_CLOUD_API_URL", "https://app.all-hands.dev")
logger.info(f"Using OpenHands Cloud API: {cloud_api_url}")

with OpenHandsCloudWorkspace(
    cloud_api_url=cloud_api_url,
    cloud_api_key=cloud_api_key,
) as workspace:
    # --- 从 SaaS 账户设置获取 LLM ---
    # get_llm() 调用 GET /users/me?expose_secrets=true，
    # 同时使用 Bearer 和会话密钥认证，返回配置完整的 LLM 实例。
    # 可覆盖任意参数，例如 workspace.get_llm(model="gpt-4o")。
    #
    llm = workspace.get_llm()
    logger.info(f"LLM configured: model={llm.model}")

    # --- 机密来自 SaaS 帐户 ---
    # get_secrets() 获取机密 *名称*（不是值）并构建 LookupSecret 引用。 值在沙箱内延迟解
    # 析。
    #
    secrets = workspace.get_secrets()
    logger.info(f"Available secrets: {list(secrets.keys())}")

    # 构建智能体和对话
    agent = get_default_agent(llm=llm, cli_mode=True)
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        received_events.append(event)
        last_event_time["ts"] = time.time()

    conversation = Conversation(
        agent=agent, workspace=workspace, callbacks=[event_callback]
    )
    assert isinstance(conversation, RemoteConversation)

    # 将 SaaS 机密插入对话中
    if secrets:
        conversation.update_secrets(secrets)
        logger.info(f"Injected {len(secrets)} secrets into conversation")

    # 构建一个提示词，通过要求智能体来练习注入的机密
    # print the last 50% of each token — proves values resolved without leaking
    # 日志中已满机密。
    secret_names = list(secrets.keys()) if secrets else []
    if secret_names:
        names_str = ", ".join(f"${name}" for name in secret_names)
        prompt = (
            f"For each of these environment variables: {names_str} — "
            "print the variable name and the LAST 50% of its value "
            "(i.e. the second half of the string). "
            "Then write a short summary into SECRETS_CHECK.txt."
        )
    else:
        # OpenHands 云上未配置机密
        prompt = "Tell me, is there any secret configured for you?"

    try:
        conversation.send_message(prompt)
        conversation.run()

        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")
    finally:
        conversation.close()

    logger.info("✅ Conversation completed successfully.")
    logger.info(f"Total {len(received_events)} events received during conversation.")
