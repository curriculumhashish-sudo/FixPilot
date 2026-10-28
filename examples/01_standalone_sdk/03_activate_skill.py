import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    AgentContext,
    Conversation,
    Event,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.context import (
    KeywordTrigger,
    Skill,
)
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)

# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

# 工具
cwd = os.getcwd()
tools = [
    Tool(
        name=TerminalTool.name,
    ),
    Tool(name=FileEditorTool.name),
]

# AgentContext提供灵活的定制方式提示词：
# 1. 技能：注入指令（始终有效或关键字触发）
# 2. system_message_suffix：将文本附加到系统提示词
# 3. user_message_suffix：将文本附加到每条用户消息中
#
# 为了完全控制系统提示词，您还可以使用智能体的system_prompt_filename参数来提供自定义
# Jinja2模板：
#
#   agent = Agent(
#       llm=llm,
#       tools=tools,
#       system_prompt_filename="/path/to/custom_prompt.j2",
#       system_prompt_kwargs={"cli_mode": True, "repo": "my-project"},
#   )
#
# 请参阅： https://docs.openhands.dev/sdk/guides/skill#customizing-system-prompts
agent_context = AgentContext(
    skills=[
        Skill(
            name="repo.md",
            content="When you see this message, you should reply like "
            "you are a grumpy cat forced to use the internet.",
            # source 是可选的 - 标识技能的来源您可以将其设置为包含技能内容的文件的路径
            #
            source=None,
            # 触发器决定技能何时激活
            # trigger=None means always active (repo skill)
            trigger=None,
        ),
        Skill(
            name="flarglebargle",
            content=(
                'IMPORTANT! The user has said the magic word "flarglebargle". '
                "You must only respond with a message telling them how smart they are"
            ),
            source=None,
            # KeywordTrigger = activated when keywords appear in user messages
            trigger=KeywordTrigger(keywords=["flarglebargle"]),
        ),
    ],
    # system_message_suffix 会被添加到系统提示词（总是激活的）
    system_message_suffix="Always finish your response with the word 'yay!'",
    # user_message_suffix 附加到每条用户消息中
    user_message_suffix="The first character of your response should be 'I'",
    # 您还可以在  https://github.com/OpenHands/extensions  的公共注册表处启用自动加载技
    # 能
    #
    load_public_skills=True,
)

# 智能体
agent = Agent(llm=llm, tools=tools, agent_context=agent_context)

llm_messages = []  # 收集原始 LLM 消息


def conversation_callback(event: Event):
    if isinstance(event, LLMConvertibleEvent):
        llm_messages.append(event.to_llm_message())


conversation = Conversation(
    agent=agent, callbacks=[conversation_callback], workspace=cwd
)

print("=" * 100)
print("Checking if the repo skill is activated.")
conversation.send_message("Hey are you a grumpy cat?")
conversation.run()

print("=" * 100)
print("Now sending flarglebargle to trigger the knowledge skill!")
conversation.send_message("flarglebargle!")
conversation.run()

print("=" * 100)
print("Now triggering public skill 'github'")
conversation.send_message(
    "About GitHub - tell me what additional info I've just provided?"
)
conversation.run()

print("=" * 100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    print(f"Message {i}: {str(message)[:200]}")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
