"""Example: APIRemoteWorkspace 动态构建。

该示例演示了从SDK代码库构建智能体服务器镜像，并通过运行时API在远程沙箱环境中启动它。

用途：
  uv run examples/02_remote_agent_server/04_convo_with_api_sandboxed_server.py

要求：
  - LLM_API_KEY: 用于 LLM 访问的 API 键
  - RUNTIME_API_KEY: API 运行时 API 访问密钥
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
from openhands.workspace import APIRemoteWorkspace


logger = get_logger(__name__)


api_key = os.getenv("LLM_API_KEY")
assert api_key, "LLM_API_KEY required"

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)

runtime_api_key = os.getenv("RUNTIME_API_KEY")
if not runtime_api_key:
    logger.error("RUNTIME_API_KEY required")
    exit(1)


# SDK_SHA 是 CI 工作流设置的规范提交 SHA（避免解析为 PR 上的合并提交的内置 GITHUB_SHA）
# 。
#
server_image_sha = os.getenv("SDK_SHA") or os.getenv("GITHUB_SHA") or "main"
server_image = f"ghcr.io/openhands/agent-server:{server_image_sha[:7]}-python-amd64"
logger.info(f"Using server image: {server_image}")

with APIRemoteWorkspace(
    runtime_api_url=os.getenv("RUNTIME_API_URL", "https://runtime.eval.all-hands.dev"),
    runtime_api_key=runtime_api_key,
    server_image=server_image,
    image_pull_policy="Always",
) as workspace:
    agent = get_default_agent(llm=llm, cli_mode=True)
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        received_events.append(event)
        last_event_time["ts"] = time.time()

    result = workspace.execute_command(
        "echo 'Hello from sandboxed environment!' && pwd"
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
