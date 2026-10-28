"""Example: 使用 Gemini 风格的文件编辑工具。

此示例演示如何使用 Gemini 风格的文件编辑工具（read_file、write_file、edit、
list_directory）而不是标准的 claude 风格的
file_editor 工具。

与标准设置的唯一区别是替换：
    Tool(name=FileEditorTool.name)
with:
    *GEMINI_FILE_TOOLS

这是一个单行更改，将 claude 风格的 file_editor 替换为 Gemini 风格的工具（read_file、
write_file、编辑、
list_directory）。
"""

import os

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.gemini import GEMINI_FILE_TOOLS
from openhands.tools.terminal import TerminalTool


# 将日志路由到自己的目录中以便于跟踪
_log_dir = "logs/gemini"
os.makedirs(_log_dir, exist_ok=True)

llm = LLM(
    model=os.getenv("LLM_MODEL", "gemini/gemini-3.1-pro-preview"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
    log_completions=True,
    log_completions_folder=_log_dir,
)

agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),
        *GEMINI_FILE_TOOLS,  # 而不是 Tool(name=FileEditorTool.name)
    ],
)

cwd = os.getcwd()
conversation = Conversation(agent=agent, workspace=cwd)

# 要求智能体创建一个文件，然后将其删除
conversation.send_message("Write 3 facts about the current project into FACTS.txt.")
conversation.run()

conversation.send_message("Now delete the FACTS.txt file you just created.")
conversation.run()

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
