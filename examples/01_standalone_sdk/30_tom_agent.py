"""演示 Tom 智能体具有心理理论能力的示例。

此示例展示了如何使用 Tom 工具设置智能体，以获取基于用户建模的个性化指导。 Tom 工具包
括：
- TomConsultTool: 获取模糊或不明确任务的指导
- SleeptimeComputeTool: 用于用户建模的索引对话
"""

import os

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation
from openhands.sdk.tool import Tool
from openhands.tools.preset.default import get_default_tools
from openhands.tools.tom_consult import (
    SleeptimeComputeAction,
    SleeptimeComputeObservation,
    SleeptimeComputeTool,
    TomConsultTool,
)


# 配置LLM
api_key: str | None = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm: LLM = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
    usage_id="agent",
    drop_params=True,
)

# 使用 Tom 工具构建工具列表
# 注意：Tom 工具在导入时自动注册 (PR #862)
tools = get_default_tools(enable_browser=False)

# 使用参数配置 Tom 工具
tom_params: dict[str, bool | str] = {
    "enable_rag": True,  # 在 Tom 智能体中启用 RAG
}

# 为 Tom 工具添加 LLM 配置（使用与主智能体相同的 LLM）
tom_params["llm_model"] = llm.model
if llm.api_key:
    if isinstance(llm.api_key, SecretStr):
        tom_params["api_key"] = llm.api_key.get_secret_value()
    else:
        tom_params["api_key"] = llm.api_key
if llm.base_url:
    tom_params["api_base"] = llm.base_url

# 将两个 Tom 工具添加到智能体
tools.append(Tool(name=TomConsultTool.name, params=tom_params))
tools.append(Tool(name=SleeptimeComputeTool.name, params=tom_params))

# 使用 Tom 能力创建智能体此智能体可以咨询 Tom 以获得个性化指导
# 注意：Tom的用户建模数据将存储在~/.openhands/中
agent: Agent = Agent(llm=llm, tools=tools)

# 开始对话
cwd: str = os.getcwd()
PERSISTENCE_DIR = os.path.expanduser("~/.openhands")
CONVERSATIONS_DIR = os.path.join(PERSISTENCE_DIR, "conversations")
conversation = Conversation(
    agent=agent, workspace=cwd, persistence_dir=CONVERSATIONS_DIR
)

# 可选地运行 sleeptime 计算来索引现有对话。这会根据对话历史构建用户偏好和模式。使用
# execute_tool 可以在 conversation.run 之前运行工具
#
print("\nRunning sleeptime compute to index conversations...")
try:
    sleeptime_result = conversation.execute_tool(
        "sleeptime_compute", SleeptimeComputeAction()
    )
    # 转换为预期的观测结果类型以进行类型安全访问
    if isinstance(sleeptime_result, SleeptimeComputeObservation):
        print(f"Result: {sleeptime_result.message}")
        print(f"Sessions processed: {sleeptime_result.sessions_processed}")
    else:
        print(f"Result: {sleeptime_result.text}")
except KeyError as e:
    print(f"Tool not available: {e}")

# 发送一条可能含糊不清的消息，汤姆咨询可能会有所帮助
conversation.send_message(
    "I need to debug some code but I'm not sure where to start. "
    + "Can you help me figure out the best approach?"
)
conversation.run()

print("\n" + "=" * 80)
print("Tom agent consultation example completed!")
print("=" * 80)

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")


# 可选：为此对话建立索引以进行 Tom 的用户建模
# 这会根据对话历史记录构建用户首选项和模式取消注释以下行以索引对话：
#
# conversation.send_message("Please index this conversation using sleeptime_compute")
# conversation.run()
# print("\nConversation indexed for user modeling!")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
