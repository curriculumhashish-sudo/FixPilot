"""使用批评模型示例进行迭代细化。

这是EXPERIMENTAL。

此示例演示了如何使用批评者模型来引导智能体完成复杂的多步骤任务。 批评者评估智能体的进
度并提供反馈，当智能体未成功完成任务时，可以触发后续行动提示词。

演示的关键概念：
1. 使用 IterativeRefinementConfig 设置批评家以实现自动重试
2. Conversation.run() 自动处理批评者驱动的细化
3. 独立于可变评论家分数定制细化策略
4. 限制智能体工作并验证最终工件

对于 All-Hands LLM 代理 (llm-proxy.*.all-hands.dev)，批评家是使用相同的 base_url 和
/vllm 后缀以及“critic
”作为模型名称来自动配置的。
"""

import os
import re
import tempfile
from pathlib import Path

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.sdk.agent.critic_mixin import ITERATIVE_REFINEMENT_ITERATION_KEY
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.critic import APIBasedCritic, CriticResult, IterativeRefinementConfig
from openhands.sdk.critic.base import CriticBase
from openhands.tools.file_editor import FileEditorTool


# 保持活例确定且舒适地位于框架内超时：一次初始尝试，一次基于批评的细化，以及有限的步骤智
# 能体。
#
MAX_REFINEMENTS = 1
MAX_AGENT_STEPS = 10


class SingleRefinementCritic(APIBasedCritic):
    """无论分数差异如何，始终只展示一项改进。"""

    def should_refine(self, critic_result: CriticResult) -> bool:  # noqa: ARG002
        return True


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise ValueError(
        f"Missing required environment variable: {name}. "
        f"Set {name} before running this example."
    )


def get_default_critic(llm: LLM) -> CriticBase | None:
    """自动配置 All-Hands LLM 代理的批评家。

    当 LLM 和 base_url 匹配 `llm-proxy.*.all-hands.dev` 时，返回一个 APIBasedCritic
    配置为：
    - server_url: {base_url}/vllm
    - api_key: 与LLM相同
    - model_name: “批评家”

    Args:
        llm: 从中派生批评者配置的 LLM 实例。

    Returns:
        APIBasedCritic 如果 LLM 配置为全手代理，None 否则。

    Example:
        llm = LLM(
            model="anthropic/claude-sonnet-4-5",
            api_key=api_key,
            base_url="https://llm-proxy.eval.all-hands.dev",
        )
        critic = get_default_critic(llm)
        if critic is None:
            # 回退到显式配置
            critic = APIBasedCritic(
                server_url="https://my-critic-server.com",
                api_key="my-api-key",
                model_name="my-critic-model",
            )
    """
    base_url = llm.base_url
    api_key = llm.api_key
    if base_url is None or api_key is None:
        return None

    # 匹配：llm-proxy.{env}.all-hands.dev (e.g., staging, prod, eval)
    pattern = r"^https?://llm-proxy\.[^./]+\.all-hands\.dev"
    if not re.match(pattern, base_url):
        return None

    return SingleRefinementCritic(
        server_url=f"{base_url.rstrip('/')}/vllm",
        api_key=api_key,
        model_name="critic",
    )


INITIAL_TASK_PROMPT = """\
Create `greeting.txt` containing exactly this one line, including the final newline:

Hello from the OpenHands critic example!

Use the file editor, verify the content once, then finish. Do not create other files,
initialize version control, or perform unrelated work.
"""

EXPECTED_GREETING = "Hello from the OpenHands critic example!\n"


llm_api_key = get_required_env("LLM_API_KEY")
llm_model = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4-5-20251001")
llm = LLM(
    model=llm_model,
    api_key=llm_api_key,
    temperature=0,
    base_url=os.getenv("LLM_BASE_URL"),
)

# 批评家总是要求进行一项改进，使这种行为独立于模型得分方差，同时仍然行使真正的批评家API
# 。
#
iterative_config = IterativeRefinementConfig(max_iterations=MAX_REFINEMENTS)

# 自动配置 All-Hands 代理的批评家或使用显式环境变量
critic = get_default_critic(llm)
if critic is None:
    print("⚠️  No All-Hands LLM proxy detected, trying explicit env vars...")
    critic = SingleRefinementCritic(
        server_url=get_required_env("CRITIC_SERVER_URL"),
        api_key=get_required_env("CRITIC_API_KEY"),
        model_name=get_required_env("CRITIC_MODEL_NAME"),
        iterative_refinement=iterative_config,
    )
else:
    # 将迭代细化配置添加到自动配置的批评家中
    critic = critic.model_copy(update={"iterative_refinement": iterative_config})

# 使用批评家创建智能体（批评家内置了迭代细化）
agent = Agent(
    llm=llm,
    tools=[Tool(name=FileEditorTool.name)],
    critic=critic,
)

# 创建工作区
workspace = Path(tempfile.mkdtemp(prefix="critic_demo_"))
print(f"📁 Created workspace: {workspace}")

# 创建对话 - 迭代细化由 Conversation.run() 根据批评者的配置自动处理
#
conversation = Conversation(
    agent=agent,
    workspace=str(workspace),
    max_iteration_per_run=MAX_AGENT_STEPS,
)

print("\n" + "=" * 70)
print("🚀 Starting Iterative Refinement with Critic Model")
print("=" * 70)
print(f"Refinements: {MAX_REFINEMENTS}")
print(f"Max agent steps: {MAX_AGENT_STEPS}")

conversation.send_message(INITIAL_TASK_PROMPT)
conversation.run()

if conversation.state.execution_status is not ConversationExecutionStatus.FINISHED:
    raise RuntimeError(
        f"Conversation ended with {conversation.state.execution_status.value}"
    )
if workspace.joinpath("greeting.txt").read_text() != EXPECTED_GREETING:
    raise RuntimeError("greeting.txt does not contain the expected text")
refinement_count = conversation.state.agent_state.get(
    ITERATIVE_REFINEMENT_ITERATION_KEY, 0
)
if refinement_count != MAX_REFINEMENTS:
    raise RuntimeError(
        f"Expected {MAX_REFINEMENTS} refinement, observed {refinement_count}"
    )

print(f"Completed {refinement_count} critic-driven refinement.")
print("Verified greeting.txt.")

# 报告费用
cost = llm.metrics.accumulated_cost
print(f"\nEXAMPLE_COST: {cost:.4f}")
