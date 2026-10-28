import os
import platform
import time

import httpx
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


# 创建一个基于Docker的远程工作区，并额外开放VSCode访问端口
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


server_image = get_server_image()
logger.info(f"Using server image: {server_image}")
with DockerWorkspace(
    server_image=server_image,
    host_port=18010,
    platform=detect_platform(),
    extra_ports=True,  # 暴露额外的 VSCode 端口
) as workspace:
    """额外的端口允许你访问 VSCode 在本地主机：18011"""

    # 创建智能体
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,
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
    conversation.send_message("Create a simple Python script that prints Hello World")
    conversation.run()

    # 获取 VSCode URL token
    vscode_port = (workspace.host_port or 8010) + 1
    try:
        response = httpx.get(
            f"{workspace.host}/api/vscode/url",
            params={"workspace_dir": workspace.working_dir},
        )
        vscode_data = response.json()
        vscode_url = vscode_data.get("url", "").replace(
            "localhost:8001", f"localhost:{vscode_port}"
        )
    except Exception:
        # 回退方案如果服务器路由不可用
        folder = (
            f"/{workspace.working_dir}"
            if not str(workspace.working_dir).startswith("/")
            else str(workspace.working_dir)
        )
        vscode_url = f"http://localhost:{vscode_port}/?folder={folder}"

    # 等待用户探索 VSCode
    y = None
    while y != "y":
        y = input(
            "\n"
            "Because you've enabled extra_ports=True in DockerDevWorkspace, "
            "you can open VSCode Web to see the workspace.\n\n"
            f"VSCode URL: {vscode_url}\n\n"
            "The VSCode should have the OpenHands settings extension installed:\n"
            "  - Dark theme enabled\n"
            "  - Auto-save enabled\n"
            "  - Telemetry disabled\n"
            "  - Auto-updates disabled\n\n"
            "Press 'y' and Enter to exit and terminate the workspace.\n"
            ">> "
        )
