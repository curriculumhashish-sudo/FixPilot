import os
import platform
import time

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation, get_logger
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import DockerWorkspace


logger = get_logger(__name__)

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)


def detect_platform():
    """检测正确的 Docker 平台字符串。"""
    machine = platform.machine().lower()
    if "arm" in machine or "aarch64" in machine:
        return "linux/arm64"
    return "linux/amd64"


def get_server_image():
    """使用 CI 中的 PR 特定图像获取服务器图像标签。"""
    platform_str = detect_platform()
    arch = "arm64" if "arm64" in platform_str else "amd64"
    # SDK_SHA 是 CI 工作流设置的规范提交 SHA（避免解析为 PR 上的合并提交的内置
    # GITHUB_SHA）。
    #
    sha = os.getenv("SDK_SHA") or os.getenv("GITHUB_SHA")
    if sha:
        return f"ghcr.io/openhands/agent-server:{sha[:7]}-python-{arch}"
    return "ghcr.io/openhands/agent-server:latest-python"


# 创建一个基于 Docker 的远程工作区，并带有用于浏览器访问的额外端口。 将
# `DockerWorkspace` 与预构建的映像一起使用，或使用 `DockerDevWorkspace` 按需自动构建映像
# 。
#
#    with DockerDevWorkspace(
#        # 动态构建智能体-服务器镜像
#        base_image="nikolaik/python-nodejs:python3.13-nodejs24-slim",
#        host_port=8010,
#        platform=detect_platform(),
#    ) 作为工作区：
server_image = get_server_image()
logger.info(f"Using server image: {server_image}")
with DockerWorkspace(
    server_image=server_image,
    # host_port 未指定时自动选择可用端口
    platform=detect_platform(),
) as workspace:
    # 在启用浏览器工具的情况下创建智能体
    agent = get_default_agent(
        llm=llm,
        cli_mode=False,  # CLI mode = False 将启用浏览器工具
    )

    # 设置回调个集合
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        event_type = type(event).__name__
        logger.info(f"🔔 Callback received event: {event_type}\n{event}")
        received_events.append(event)
        last_event_time["ts"] = time.time()

    # 使用工作区创建 RemoteConversation
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[event_callback],
    )
    assert isinstance(conversation, RemoteConversation)

    logger.info(f"\n📋 Conversation ID: {conversation.state.id}")
    logger.info("📝 Sending first message...")
    conversation.send_message(
        "Could you go to https://openhands.dev/ blog page and summarize main "
        "points of the latest blog?"
    )
    conversation.run()

    cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
    print(f"EXAMPLE_COST: {cost}")
