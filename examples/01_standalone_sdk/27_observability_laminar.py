"""
可观测性和层流示例

此示例演示了在 OpenHands SDK 中使用 Laminar 启用 OpenTelemetry 跟踪。 设置
LMNR_PROJECT_API_KEY 并运行脚本以查
看痕迹。
"""

import os

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.terminal import TerminalTool


# 提示：运行前在您的环境中设置 LMNR_PROJECT_API_KEY，e.g。：
#   export LMNR_PROJECT_API_KEY="your-laminar-api-key"
# 对于非层流 OTLP 后端，请设置 OTEL_* 变量。

# 配置LLM和智能体
api_key = os.getenv("LLM_API_KEY")
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    model=model,
    api_key=SecretStr(api_key) if api_key else None,
    base_url=base_url,
    usage_id="agent",
)

agent = Agent(
    llm=llm,
    tools=[Tool(name=TerminalTool.name)],
)

# 创建对话并运行简单的任务
conversation = Conversation(agent=agent, workspace=".")
conversation.send_message("List the files in the current directory and print them.")
conversation.run()
print(
    "All done! Check your Laminar dashboard for traces "
    "(session is the conversation UUID)."
)
