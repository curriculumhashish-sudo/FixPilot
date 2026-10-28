"""Example: 使用 FallbackStrategy 来实现 LLM 弹性。

当主 LLM 失效，且是短暂错误（如限流超时等）， FallbackStrategy 会自动尝试备用 LLMs。
回退方案是按次计费：每次新的请求都从主模型开始。 词元用量
和回退方案的成本被合并到主 LLM 的指标中。

这个例子：
  1. 将两个回退方案 LLM 配置文件保存到临时存储中。
  2. 配置主 LLM，其中 FallbackStrategy 指向这些配置文件。
  3. 运行对话 - 如果主模型不可用，智能体会透明地回退到下一个可用模型。
"""

import os
import tempfile

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, LLMProfileStore, Tool
from openhands.sdk.llm import FallbackStrategy
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# 从环境中读取配置
api_key = os.getenv("LLM_API_KEY", None)
assert api_key is not None, "LLM_API_KEY environment variable is not set."
base_url = os.getenv("LLM_BASE_URL")
primary_model = os.getenv("LLM_MODEL", "gpt-5.5")

# 使用临时目录，以便此示例不会污染您的主文件夹。 在实际使用中，您可以省略 base_dir 以使
# 用默认值（~/.openhands/profiles).
#
profile_store_dir = tempfile.mkdtemp()
store = LLMProfileStore(base_dir=profile_store_dir)

fallback_1 = LLM(
    usage_id="fallback-1",
    model=os.getenv("LLM_FALLBACK_MODEL_1", "openai/gpt-4o"),
    api_key=SecretStr(os.getenv("LLM_FALLBACK_API_KEY_1", api_key)),
    base_url=os.getenv("LLM_FALLBACK_BASE_URL_1", base_url),
)
store.save("fallback-1", fallback_1, include_secrets=True)

fallback_2 = LLM(
    usage_id="fallback-2",
    model=os.getenv("LLM_FALLBACK_MODEL_2", "openai/gpt-4o-mini"),
    api_key=SecretStr(os.getenv("LLM_FALLBACK_API_KEY_2", api_key)),
    base_url=os.getenv("LLM_FALLBACK_BASE_URL_2", base_url),
)
store.save("fallback-2", fallback_2, include_secrets=True)

print(f"Saved fallback profiles: {store.list()}")


# 使用 FallbackStrategy 配置主 LLM
primary_llm = LLM(
    usage_id="agent-primary",
    model=primary_model,
    api_key=SecretStr(api_key),
    base_url=base_url,
    fallback_strategy=FallbackStrategy(
        fallback_llms=["fallback-1", "fallback-2"],
        profile_store_dir=profile_store_dir,
    ),
)


# 进行对话
agent = Agent(
    llm=primary_llm,
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
)

conversation = Conversation(agent=agent, workspace=os.getcwd())
conversation.send_message("Write a haiku about resilience into HAIKU.txt.")
conversation.run()


# 检查指标（包括任何回退方案使用情况）
metrics = primary_llm.metrics
print(f"Total cost (including fallbacks): ${metrics.accumulated_cost:.6f}")
print(f"Token usage records: {len(metrics.token_usages)}")
for usage in metrics.token_usages:
    print(
        f"  model={usage.model}"
        f"  prompt={usage.prompt_tokens}"
        f"  completion={usage.completion_tokens}"
    )

print(f"EXAMPLE_COST: {metrics.accumulated_cost}")
