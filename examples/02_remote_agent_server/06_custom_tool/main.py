"""Example: 使用带有远程功能的自定义工具 Agent Server。

本示例展示了如何使用自定义工具与远程 Agent Server 通过构建包含工具实现的自定义基础镜
像，并通过 ``OH_EXTRA_PYTHON_PATH`` 将其暴露给二
进制 Agent Server。

先决条件：
    1. 首先构建自定义基础镜像：
       cd examples/02_remote_agent_server/06_custom_tool
       ./build_custom_image.sh

    2. 设置 LLM_API_KEY 环境变量

工作流程是：
1. 定义自定义工具（LogDataTool 用于将结构化数据记录到 JSON）
2. 创建一个简单的 Dockerfile，将该工具复制到基础映像中
3. 设置 OH_EXTRA_PYTHON_PATH 以便二进制服务器可以导入自定义工具
4. 构建自定义基础镜像
5. 使用 DockerDevWorkspace 和 base_image 指向自定义图像
6. DockerDevWorkspace 在自定义基础镜像之上构建二进制文件 Agent Server
7. 当客户端创建会话时，服务器动态注册工具
8. 智能体可以在执行过程中使用自定义工具
9. 通过从工作区读取 JSON 文件来验证记录的数据

该模式适用于：
- 在智能体次运行期间收集结构化数据（日志、指标、事件）
- 实施与外部系统的自定义集成
- 将特定于域的操作添加到智能体
"""

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Conversation,
    RemoteConversation,
    Tool,
    get_logger,
)
from openhands.workspace import DockerDevWorkspace


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


# 获取包含该脚本的目录
example_dir = Path(__file__).parent.absolute()

# 自定义基本图像标签（包含自定义工具，Agent Server构建在顶部）
CUSTOM_BASE_IMAGE_TAG = "custom-base-image:latest"

# 2) 检查自定义基础镜像是否存在，如果不存在则构建
logger.info(f"🔍 Checking for custom base image: {CUSTOM_BASE_IMAGE_TAG}")
result = subprocess.run(
    ["docker", "images", "-q", CUSTOM_BASE_IMAGE_TAG],
    capture_output=True,
    text=True,
    check=False,
)

if not result.stdout.strip():
    logger.info("⚠️  Custom base image not found. Building...")
    logger.info("📦 Building custom base image with custom tools...")
    build_script = example_dir / "build_custom_image.sh"
    try:
        subprocess.run(
            [str(build_script), CUSTOM_BASE_IMAGE_TAG],
            cwd=str(example_dir),
            check=True,
        )
        logger.info("✅ Custom base image built successfully!")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Failed to build custom base image: {e}")
        logger.error("Please run ./build_custom_image.sh manually and fix any errors.")
        sys.exit(1)
else:
    logger.info(f"✅ Custom base image found: {CUSTOM_BASE_IMAGE_TAG}")

# 3) 使用自定义基础映像 DockerDevWorkspace 创建 DockerDevWorkspace 将在此基础映像之上构
# 建二进制文件 Agent Server
#
logger.info("🚀 Building and starting binary agent server with custom tools...")
logger.info("📦 This may take a few minutes on first run...")

with DockerDevWorkspace(
    base_image=CUSTOM_BASE_IMAGE_TAG,
    host_port=8011,
    platform=detect_platform(),
    # 自定义基础映像设置 OH_EXTRA_PYTHON_PATH=/app，因此二进制文件 Agent Server 可以从包
    # 外部导入 custom_tools.log_data。
    #
    target="binary",
) as workspace:
    logger.info("✅ Custom agent server started!")

    # 4) 将自定义工具导入客户端的注册表，这允许客户端将模块名称发送给服务器。服务器将导
    # 入相同的模块并执行工具
    #
    import custom_tools.log_data  # noqa: F401

    # 5) 使用自定义工具创建智能体
    #    注意：我们在这里指定了工具，但它实际上是在服务器上执行的
    #    获取默认工具并添加我们的自定义工具
    from openhands.sdk import Agent
    from openhands.tools.preset.default import get_default_condenser, get_default_tools

    tools = get_default_tools(enable_browser=False)
    # 添加我们的自定义工具！
    tools.append(Tool(name="LogDataTool"))

    agent = Agent(
        llm=llm,
        tools=tools,
        system_prompt_kwargs={"cli_mode": True},
        condenser=get_default_condenser(
            llm=llm.model_copy(update={"usage_id": "condenser"})
        ),
    )

    # 6) 设置回调个集合
    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        event_type = type(event).__name__
        logger.info(f"🔔 Callback received event: {event_type}\n{event}")
        received_events.append(event)
        last_event_time["ts"] = time.time()

    # 7) 使用简单的命令测试工作区
    result = workspace.execute_command(
        "echo 'Custom agent server ready!' && python --version"
    )
    logger.info(
        f"Command '{result.command}' completed with exit code {result.exit_code}"
    )
    logger.info(f"Output: {result.stdout}")

    # 8) 与自定义创建对话智能体
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[event_callback],
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        logger.info(f"\n📋 Conversation ID: {conversation.state.id}")

        logger.info("📝 Sending task to analyze files and log findings...")
        conversation.send_message(
            "Please analyze the Python files in the current directory. "
            "Use the LogDataTool to log your findings as you work. "
            "For example:\n"
            "- Log when you start analyzing a file (level: info)\n"
            "- Log any interesting patterns you find (level: info)\n"
            "- Log any potential issues (level: warning)\n"
            "- Include relevant data like file names, line numbers, etc.\n\n"
            "Make at least 3 log entries using the LogDataTool."
        )
        logger.info("🚀 Running conversation...")
        conversation.run()
        logger.info("✅ Task completed!")
        logger.info(f"Agent status: {conversation.state.execution_status}")

        # 等待事件稳定（2 秒内没有事件）
        logger.info("⏳ Waiting for events to stop...")
        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)
        logger.info("✅ Events have stopped")

        # 9) 使用 file_download API 从 JSON 文件读取记录的数据
        logger.info("\n📊 Logged Data Summary:")
        logger.info("=" * 80)

        # 使用文件下载 API 从工作区下载日志文件
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp_file:
            local_path = tmp_file.name

        download_result = workspace.file_download(
            source_path="/tmp/agent_data.json",
            destination_path=local_path,
        )

        if download_result.success:
            try:
                with open(local_path) as f:
                    log_entries = json.load(f)
                logger.info(f"Found {len(log_entries)} log entries:\n")
                for i, entry in enumerate(log_entries, 1):
                    logger.info(f"Entry {i}:")
                    logger.info(f"  Timestamp: {entry.get('timestamp', 'N/A')}")
                    logger.info(f"  Level: {entry.get('level', 'N/A')}")
                    logger.info(f"  Message: {entry.get('message', 'N/A')}")
                    if entry.get("data"):
                        logger.info(f"  Data: {json.dumps(entry['data'], indent=4)}")
                    logger.info("")
            except json.JSONDecodeError:
                logger.info("Log file exists but couldn't parse JSON")
                with open(local_path) as f:
                    logger.info(f"Raw content: {f.read()}")
            finally:
                # 清理临时文件
                Path(local_path).unlink(missing_ok=True)
        else:
            logger.info("No log file found (agent may not have used the tool)")
            if download_result.error:
                logger.debug(f"Download error: {download_result.error}")

        logger.info("=" * 80)

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"\nEXAMPLE_COST: {cost}")

    finally:
        logger.info("\n🧹 Cleaning up conversation...")
        conversation.close()

logger.info("\n✅ Example completed successfully!")
logger.info("\nThis example demonstrated how to:")
logger.info("1. Create a custom tool that logs structured data to JSON")
logger.info("2. Build a base image with the custom tool and OH_EXTRA_PYTHON_PATH")
logger.info("3. Use DockerDevWorkspace to build the binary agent server")
logger.info("4. Enable dynamic tool registration on the server")
logger.info("5. Use the custom tool during agent execution")
logger.info("6. Read the logged data back from the workspace")
