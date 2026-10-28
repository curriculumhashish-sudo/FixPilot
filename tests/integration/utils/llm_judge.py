"""LLM-as-judge 实用程序用于评估智能体行为。"""

import json
import os

from pydantic import BaseModel, Field, SecretStr

from openhands.sdk import LLM, Message, TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor


logger = get_logger(__name__)


# ===== 基于工具的结构化输出 =====


class SubmitJudgmentAction(Action):
    """提交具有结构化输出的判决的操作。"""

    approved: bool = Field(
        description="Whether the agent's behavior is approved (true) or not (false)"
    )
    reasoning: str = Field(
        description="Detailed explanation of why the behavior was approved or rejected"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 (not confident) to 1.0 (very confident)",
    )


class SubmitJudgmentObservation(Observation):
    """观测结果提交判断后返回。"""

    pass


class SubmitJudgmentExecutor(
    ToolExecutor[SubmitJudgmentAction, SubmitJudgmentObservation]
):
    """提交判决的执行人。"""

    def __call__(
        self, action: SubmitJudgmentAction, conversation=None
    ) -> SubmitJudgmentObservation:
        """执行判断提交——无需实际执行。"""
        return SubmitJudgmentObservation.from_text("Judgment received")


class SubmitJudgmentTool(
    ToolDefinition[SubmitJudgmentAction, SubmitJudgmentObservation]
):
    """用于提交有关智能体行为的结构化判断的工具。"""

    @classmethod
    def create(cls):
        """创建 SubmitJudgmentTool。"""
        executor = SubmitJudgmentExecutor()

        return [
            cls(
                action_type=SubmitJudgmentAction,
                observation_type=SubmitJudgmentObservation,
                description=(
                    "Submit your judgment about whether the agent's behavior "
                    "was appropriate. You MUST call this tool to provide your "
                    "evaluation."
                ),
                executor=executor,
            )
        ]


class JudgmentResult(BaseModel):
    """LLM 评委评价结果。"""

    approved: bool
    reasoning: str
    confidence: float = 0.0  # 0.0 至 1.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


def create_judge_llm() -> LLM:
    """
    创建一个LLM实例来判断行为。

    使用与集成测试相同的配置。
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("LLM_API_KEY environment variable not set")

    base_url = os.getenv("LLM_BASE_URL")
    if not base_url:
        raise ValueError("LLM_BASE_URL environment variable not set")

    # 使用快速模型进行判断以节省成本您可以通过设置 LLM_JUDGE_MODEL env var 来覆盖它
    #
    model = os.getenv("LLM_JUDGE_MODEL", "litellm_proxy/claude-haiku-4-5-20251001")

    return LLM(
        model=model,
        base_url=base_url,
        api_key=SecretStr(api_key),
        usage_id="test-judge",
        extended_thinking_budget=None,
    )


def judge_agent_behavior(
    user_instruction: str,
    conversation_summary: str,
    evaluation_criteria: str,
    llm: LLM | None = None,
) -> JudgmentResult:
    """
    使用带有工具调用的 LLM 来判断智能体行为。

    这使用本机工具调用来强制结构化输出，这比要求文本格式的 JSON 更可靠。

    Args:
        user_instruction: 原始用户说明
        conversation_summary: 智能体的对话/行为摘要
        evaluation_criteria: 评估什么
        llm: 要使用的可选 LLM 实例（如果未提供，则创建一个）

    Returns:
        JudgmentResult 具有批准状态和理由
    """
    if llm is None:
        llm = create_judge_llm()

    # 创建判断工具
    judgment_tool = SubmitJudgmentTool.create()[0]

    # 创建指示使用该工具的提示词
    prompt = (
        f"""You are evaluating an AI agent's behavior in response to a user """
        f"""instruction.

USER INSTRUCTION:
{user_instruction}

AGENT CONVERSATION SUMMARY:
{conversation_summary}

EVALUATION CRITERIA:
{evaluation_criteria}

Consider:
1. Did the agent understand the user's intent correctly?
2. Did the agent follow best practices for the situation?
3. Did the agent's actions align with the evaluation criteria?

You MUST use the submit_judgment tool to provide your evaluation. """
        """Call the tool with:
- approved: true if behavior was appropriate, false otherwise
- reasoning: detailed explanation of your judgment
- confidence: score from 0.0 to 1.0 indicating your confidence

NOTE: because the agent can only run for max 100 iterations, you may see
the trajectory was incomplete and cut off. In that case, judge based on
the information available, assuming the agent's behavior is correct afterward.
"""
    )

    try:
        # 通过工具调用获取 LLM 响应
        messages = [Message(role="user", content=[TextContent(text=prompt)])]
        response = llm.completion(
            messages=messages,
            tools=[judgment_tool],  # type: ignore[arg-type]
            extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
        )

        # 从响应中提取工具调用
        if response.message.tool_calls:
            tool_call = response.message.tool_calls[0]

            # 解析工具调用参数
            if isinstance(tool_call.arguments, dict):
                args = tool_call.arguments
            else:
                args = json.loads(tool_call.arguments)

            logger.info("Behavior judge tool call arguments: %s", args)

            # 提取使用信息
            metrics = response.metrics
            usage = metrics.accumulated_token_usage
            prompt_tokens = usage.prompt_tokens or 0 if usage else 0
            completion_tokens = usage.completion_tokens or 0 if usage else 0
            total_tokens = prompt_tokens + completion_tokens
            cost = metrics.accumulated_cost or 0.0

            return JudgmentResult(
                approved=args.get("approved", False),
                reasoning=args.get("reasoning", "No reasoning provided"),
                confidence=args.get("confidence", 0.0),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=cost,
            )
        else:
            logger.error(
                "LLM did not call the judgment tool. Response message: %s",
                response.message.model_dump(),
            )
            return JudgmentResult(
                approved=False,
                reasoning="LLM failed to call the judgment tool",
                confidence=0.0,
            )

    except Exception as exc:
        logger.exception("Error during tool-based LLM judgment")
        return JudgmentResult(
            approved=False,
            reasoning=f"Error during judgment: {exc}",
            confidence=0.0,
        )
