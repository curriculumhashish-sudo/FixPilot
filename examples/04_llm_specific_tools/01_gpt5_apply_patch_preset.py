"""Example: 使用 GPT-5 预设和 ApplyPatchTool 进行文件编辑。

此示例演示如何启用 GPT-5 预设，它将标准克劳德样式 FileEditorTool 替换为
ApplyPatchTool。

用途：
    export OPENAI_API_KEY=...  # 或设置 LLM_API_KEY
    # 可选择设置一个模型（如果可用，我们建议使用迷你变体）：
    # 导出LLM_MODEL=(
    #   "openai/gpt-5.2-mini" # 或回退方案："openai/gpt-5.1-mini" 或 "openai/gpt-5.1"
    # )

    uv run python examples/04_llm_specific_tools/01_gpt5_apply_patch_preset.py
"""

import os

from openhands.sdk import LLM, Agent, Conversation
from openhands.tools.preset.gpt5 import get_gpt5_agent


# 解析环境中的 API 键
api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("Please set OPENAI_API_KEY or LLM_API_KEY to run this example.")

model = os.getenv("LLM_MODEL", "openai/gpt-5.1")
base_url = os.getenv("LLM_BASE_URL", None)

llm = LLM(model=model, api_key=api_key, base_url=base_url)

# 使用 GPT-5 预设构建智能体（基于 ApplyPatchTool 的编辑）
agent: Agent = get_gpt5_agent(llm)

# 在当前工作目录中运行
cwd = os.getcwd()
conversation = Conversation(agent=agent, workspace=cwd)

conversation.send_message(
    "Create (or update) a file named GPT5_DEMO.txt at the repo root with "
    "two short lines describing this repository."
)
conversation.run()

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
