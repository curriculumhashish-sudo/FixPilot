"""Example: OpenHandsCloudWorkspace 对应 OpenHands 云 API。

此示例演示使用 OpenHandsCloudWorkspace 通过 OpenHands 云 (app.all-hands.dev) 配置沙箱
并运行智能体对话。

用途：
  uv run examples/02_remote_agent_server/07_convo_with_cloud_workspace.py

要求：
  - LLM_API_KEY: 用于直接 LLM 提供商访问的 API 键（e.g.、Anthropic API 键）
  - OPENHANDS_CLOUD_API_KEY: API 用于 OpenHands 云访问的密钥

Note:
  LLM 配置被发送到云沙箱，​​因此您需要一个直接与 LLM 提供程序（而不是本地代理）一起使
  用的 API 密钥。 如果使用 Anthropic，请将
  LLM_API_KEY 设置为 Anthropic API 键。
"""

import os
import time

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import OpenHandsCloudWorkspace


logger = get_logger(__name__)


api_key = os.getenv("LLM_API_KEY")
assert api_key, "LLM_API_KEY required"

# 注意：此处不要使用本地代理 URL - 云沙箱需要直接访问
# 给 LLM 提供商。 将 None 用于 base_url，让 LiteLLM 使用默认提供程序端点，或指定提供程序
# 的直接 URL。
#
llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    base_url=os.getenv("LLM_BASE_URL") or None,
    api_key=SecretStr(api_key),
)

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
    agent = get_default_agent(llm=llm, cli_mode=True)
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        received_events.append(event)
        last_event_time["ts"] = time.time()

    result = workspace.execute_command(
        "echo 'Hello from OpenHands Cloud sandbox!' && pwd"
    )
    logger.info(f"Command completed: {result.exit_code}, {result.stdout}")

    conversation = Conversation(
        agent=agent, workspace=workspace, callbacks=[event_callback]
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        conversation.send_message(
            "Read the current repo and write 3 facts about the project into FACTS.txt."
        )
        conversation.run()

        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)

        conversation.send_message("Great! Now delete that file.")
        conversation.run()
        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")
    finally:
        conversation.close()

    logger.info("✅ Conversation completed successfully.")
    logger.info(f"Total {len(received_events)} events received during conversation.")
