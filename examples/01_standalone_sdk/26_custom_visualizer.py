"""自定义展示台示例

此示例演示如何通过子类化 ConversationVisualizer 创建和使用自定义可视化工具。 这种方法
提供：
- 具有基于类的状态管理的干净、可测试的代码
- 直接配置（只需将可视化器实例传递给可视化器参数）
- 可在对话中共享的可重复使用的可视化工具

这演示了如何将 ConversationVisualizer 实例直接传递给可视化器参数，以获得干净、可重用
的可视化逻辑。
"""

import logging
import os

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation
from openhands.sdk.conversation.visualizer import ConversationVisualizerBase
from openhands.sdk.event import (
    Event,
)
from openhands.tools.preset.default import get_default_agent


class MinimalVisualizer(ConversationVisualizerBase):
    """一个最小的可视化工具，可以在原始事件发生时打印它们。"""

    def on_event(self, event: Event) -> None:
        """处理事件以实现最小进度可视化。"""
        print(f"\n\n[EVENT] {type(event).__name__}: {event.model_dump_json()[:200]}...")


api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    model=model,
    api_key=SecretStr(api_key),
    base_url=base_url,
    usage_id="agent",
)
agent = get_default_agent(llm=llm, cli_mode=True)

# ============================================================================
# 配置可视化
# ============================================================================
# 设置日志记录级别以减少冗长
logging.getLogger().setLevel(logging.WARNING)

# 与自定义可视化工具开始对话
cwd = os.getcwd()
conversation = Conversation(
    agent=agent,
    workspace=cwd,
    visualizer=MinimalVisualizer(),
)

# 发送消息并让智能体运行
print("Sending task to agent...")
conversation.send_message("Write 3 facts about the current project into FACTS.txt.")
conversation.run()
print("Task completed!")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost:.4f}")
