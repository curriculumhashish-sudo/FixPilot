"""OpenHands 智能体 SDK — 图像输入示例。

该脚本反映了基本设置
``examples/01_standalone_sdk/01_hello_world.py`` 但通过将图像与文本指令一起发送到智能
体来添加视觉支持。

它还演示了多图像输入，使用 base64 编码的图像，该输入 Anthropic 多图像缩放路径（>20 张
图像将自动缩放至 2000×2000 像素）。
"""

import base64
import io
import os

from PIL import Image
from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    ImageContent,
    LLMConvertibleEvent,
    Message,
    TextContent,
    get_logger,
)
from openhands.sdk.tool.spec import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)


def _make_png_data_url(width: int, height: int, color: str = "red") -> str:
    """使用给定的尺寸和颜色创建 base64 PNG 数据 URL。"""
    image = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# 配置 LLM（具有视觉功能的型号）
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    usage_id="vision-llm",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)
assert llm.vision_is_active(), "The selected LLM model does not support vision input."

cwd = os.getcwd()

agent = Agent(
    llm=llm,
    tools=[
        Tool(
            name=TerminalTool.name,
        ),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ],
)

llm_messages = []  # 收集原始 LLM 消息以供检查


def conversation_callback(event: Event) -> None:
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation = Conversation(
    agent=agent, callbacks=[conversation_callback], workspace=cwd
)

# ── 第1部分：单张URL图像──────────────────────────────────────────────
IMAGE_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

conversation.send_message(
    Message(
        role="user",
        content=[
            TextContent(
                text=(
                    "Study this image and describe the key elements you see. "
                    "Summarize them in a short paragraph and suggest a catchy caption."
                )
            ),
            ImageContent(image_urls=[IMAGE_URL]),
        ],
    )
)
conversation.run()

conversation.send_message(
    "Great! Please save your description and caption into image_report.md."
)
conversation.run()

# ── 第2部分：生成21张超大的Base64图片（练习Anthropic缩放）── 生成21张2500×100像素的图片
# ，刚好超过触发Anthropic的多图片限制（每张图片2000×2000像素）。 SDK 将在发送给提供商之
# 前自动缩小这些范围。
#
COLORS = [
    "red",
    "green",
    "blue",
    "yellow",
    "cyan",
    "magenta",
    "orange",
    "purple",
    "pink",
    "brown",
    "gray",
    "white",
    "navy",
    "teal",
    "olive",
    "maroon",
    "lime",
    "aqua",
    "coral",
    "gold",
    "indigo",
]
oversized_data_urls = [
    _make_png_data_url(2500, 100, color=COLORS[i % len(COLORS)]) for i in range(21)
]

conversation.send_message(
    Message(
        role="user",
        content=[
            TextContent(
                text=(
                    "I'm sending you 21 solid-colour test images. "
                    "List the dominant colour of each image in order, "
                    "one per line."
                )
            ),
            ImageContent(image_urls=oversized_data_urls),
        ],
    )
)
conversation.run()

print("=" * 100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    print(f"Message {i}: {str(message)[:200]}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
