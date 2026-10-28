import os
import platform
import time

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import DockerWorkspace


logger = get_logger(__name__)

# 1) 确保我们有 LLM API 键
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


# 2) 创建一个基于 Docker 的远程工作区，它将自动设置和管理 Docker 容器。 将
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
    # 使用预构建的映像以加快启动速度
    server_image=server_image,
    # host_port 未指定时自动选择可用端口
    platform=detect_platform(),
) as workspace:
    # 3) 创建智能体
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,
    )

    # 4) 设置回调个集合
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        event_type = type(event).__name__
        logger.info(f"🔔 Callback received event: {event_type}\n{event}")
        received_events.append(event)
        last_event_time["ts"] = time.time()

    # 5) 使用简单的命令测试工作区
    result = workspace.execute_command(
        "echo 'Hello from sandboxed environment!' && pwd"
    )
    logger.info(
        f"Command '{result.command}' completed with exit code {result.exit_code}"
    )
    logger.info(f"Output: {result.stdout}")
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[event_callback],
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        logger.info(f"\n📋 Conversation ID: {conversation.state.id}")

        logger.info("📝 Sending first message...")
        conversation.send_message(
            "Read the current repo and write 3 facts about the project into FACTS.txt."
        )
        logger.info("🚀 Running conversation...")
        conversation.run()
        logger.info("✅ First task completed!")
        logger.info(f"Agent status: {conversation.state.execution_status}")

        # 等待事件稳定（2 秒内没有事件）
        logger.info("⏳ Waiting for events to stop...")
        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)
        logger.info("✅ Events have stopped")

        logger.info("🚀 Running conversation again...")
        conversation.send_message("Great! Now delete that file.")
        conversation.run()
        logger.info("✅ Second task completed!")

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")
    finally:
        print("\n🧹 Cleaning up conversation...")
        conversation.close()
