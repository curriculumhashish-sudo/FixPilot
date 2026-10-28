"""Example: ACPAgent 通过 API 使用远程运行时。

此示例演示了运行  ACPAgent (Claude Code via ACP 通过运行时在远程沙箱环境中协议 API.
它遵循相同的模式
04_convo_with_api_sandboxed_server.py 但使用了 ACPAgent 而不是默认的 LLM-based 智能体
。

用途：
  uv run examples/02_remote_agent_server/09_acp_agent_with_remote_runtime.py

要求：
  - LLM_BASE_URL: LiteLLM代理URL（路由克劳德代码请求）
  - LLM_API_KEY: LiteLLM 虚拟 API 键
  - RUNTIME_API_KEY: API 运行时 API 访问密钥
"""

import os
import time

from openhands.sdk import (
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.sdk.agent import ACPAgent
from openhands.workspace import APIRemoteWorkspace


logger = get_logger(__name__)


# ACP 智能体 (Claude Code) 通过 LiteLLM 代理路由
llm_base_url = os.getenv("LLM_BASE_URL")
llm_api_key = os.getenv("LLM_API_KEY")
assert llm_base_url and llm_api_key, "LLM_BASE_URL and LLM_API_KEY required"

# 设置 ANTHROPIC_* 变量，以便 Claude Code 路由通过 LiteLLM
os.environ["ANTHROPIC_BASE_URL"] = llm_base_url
os.environ["ANTHROPIC_API_KEY"] = llm_api_key

runtime_api_key = os.getenv("RUNTIME_API_KEY")
assert runtime_api_key, "RUNTIME_API_KEY required"

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
    target_type="binary",  # CI 构建二进制目标图像
    forward_env=["ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"],
) as workspace:
    agent = ACPAgent(
        acp_command=["claude-agent-acp"],  # 预安装在 Docker 图像中
    )

    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        received_events.append(event)
        last_event_time["ts"] = time.time()

    conversation = Conversation(
        agent=agent, workspace=workspace, callbacks=[event_callback]
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        conversation.send_message(
            "List the files in /workspace and describe what you see."
        )
        conversation.run()

        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)

        # 报告费用
        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost:.4f}")
    finally:
        conversation.close()
