"""使用 ask_oracle 工具端到端查询 Oracle。

Oracle 是一个已保存的 LLM 配置文件，按照约定以名称解析
``oracle``. 这个示例连接了两个智能体的主模型和一个 ``oracle`` 的模型，添加了
``Tool(name="ask_oracle")`` 到智能体，然后
驱动了一个正常的对话：智能体决定给 ``ask_oracle`` 发电话，工具查询了 ``oracle`` 的模
型，然后智能体使用 Oracle 的答案来回复。

用途：
    LLM_API_KEY=... LLM_BASE_URL=https://llm-proxy.app.all-hands.dev \
        uv run python examples/01_standalone_sdk/58_ask_oracle_tool/main.py

Note:
    该示例将 ``oracle`` 配置文件保存在临时目录中，因此不会修改用户的默认配置文件存储
    。
"""

import os
import tempfile

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, LocalConversation, Tool
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.tools.ask_oracle import ORACLE_PROFILE_NAME, AskOracleTool


DEFAULT_BASE_URL = "https://llm-proxy.app.all-hands.dev"
# 智能体的主要模型（与其他示例一样遵循标准 LLM_MODEL env）。 Oracle默认为同模型； 覆盖
# ASK_ORACLE_MODEL 将“oracle”配置文件指向不同/更强的模型。
#
PRIMARY_MODEL = os.getenv("ASK_ORACLE_PRIMARY_MODEL") or os.getenv(
    "LLM_MODEL", "openai/gpt-5.5"
)
ORACLE_MODEL = os.getenv("ASK_ORACLE_MODEL", PRIMARY_MODEL)

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)

with tempfile.TemporaryDirectory() as profile_store_dir:
    store = LLMProfileStore(profile_store_dir)
    store.save(
        ORACLE_PROFILE_NAME,
        LLM(
            model=ORACLE_MODEL,
            api_key=SecretStr(api_key),
            base_url=base_url,
            usage_id="oracle",
        ),
        include_secrets=True,
    )

    primary_llm = LLM(
        model=PRIMARY_MODEL,
        api_key=SecretStr(api_key),
        base_url=base_url,
        usage_id="primary",
    )
    agent = Agent(llm=primary_llm, tools=[Tool(name=AskOracleTool.name)])
    conversation = LocalConversation(
        agent=agent,
        workspace=os.getcwd(),
        profile_store_dir=profile_store_dir,
    )

    print(f"Primary model: {conversation.agent.llm.model}")
    print(f"Oracle model:  {ORACLE_MODEL}")
    conversation.send_message(
        "Call the oracle to ask it for its opinion on the weather today, "
        "then just tell me in two words how it's like."
    )
    conversation.run()

    cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
    print(f"Total cost: ${cost:.6f}")
    print(f"EXAMPLE_COST: {cost}")
