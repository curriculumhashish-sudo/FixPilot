from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic import Field

from openhands.sdk.critic.base import CriticBase, CriticResult
from openhands.sdk.critic.impl.api.client import CriticClient
from openhands.sdk.critic.impl.api.taxonomy import categorize_features


if TYPE_CHECKING:
    from openhands.sdk.event import LLMConvertibleEvent


def _format_feature_list(features: list[dict[str, Any]]) -> str:
    """格式化特征列表及其概率。"""
    if not features:
        return "None detected"
    items = []
    for f in features:
        name = f.get("display_name", f.get("name", "Unknown"))
        prob = f.get("probability", 0)
        items.append(f"{name} ({prob:.0%})")
    return ", ".join(items)


def _get_high_probability_agent_issues(
    critic_result: CriticResult, issue_threshold: float
) -> tuple[dict[str, Any], ...]:
    if not critic_result.metadata:
        return ()

    categorized = critic_result.metadata.get("categorized_features", {})
    if not isinstance(categorized, dict):
        return ()

    return tuple(
        issue
        for issue in categorized.get("agent_behavioral_issues", [])
        if isinstance(issue, dict) and issue.get("probability", 0) >= issue_threshold
    )


class APIBasedCritic(CriticBase, CriticClient):
    issue_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description=(
            "APIBasedCritic-specific probability threshold for agent issue "
            "labels that should trigger iterative refinement."
        ),
    )

    def evaluate(
        self,
        events: Sequence[LLMConvertibleEvent],
        git_patch: str | None = None,  # noqa: ARG002
    ) -> CriticResult:
        # 本地导入以避免模块加载期间的循环依赖
        from openhands.sdk.context.view import View
        from openhands.sdk.event import LLMConvertibleEvent, SystemPromptEvent

        system_prompt_event: SystemPromptEvent | None = None
        tools = []
        for event in events:
            if isinstance(event, SystemPromptEvent):
                system_prompt_event = event
                tools = event.tools
                break
        if system_prompt_event is None:
            raise ValueError(
                "SystemPromptEvent is required for APIBasedCritic evaluation"
            )
        if not tools:
            raise ValueError(
                "APIBasedCritic requires tools to be defined in SystemPromptEvent. "
                "Ensure your agent configuration includes tool definitions."
            )

        # 这只会保留上下文压缩器保留的事件
        view = View.from_events(events)
        llm_convertible_events = view.events

        # 将事件转换为消息
        messages = LLMConvertibleEvent.events_to_messages(llm_convertible_events)

        # 序列化向 API 的词典发送消息
        formatted_messages = [
            message.to_chat_dict(
                cache_enabled=False,
                vision_enabled=False,  # Critic 目前不支持愿景
                function_calling_enabled=True,
                force_string_serializer=False,
                send_reasoning_content=False,
            )
            for message in messages
        ]

        # 将 ToolDefinition 对象转换为 ChatCompletionToolParam 格式
        tools_for_api = [tool.to_openai_tool() for tool in tools]
        response = self.classify_trace(formatted_messages, tools_for_api)
        prob_map = self.extract_prob_map(response)

        explanation = []

        if "success" not in prob_map.probs:
            raise ValueError("APIBasedCritic requires 'success' label in the response.")

        score = prob_map.probs["success"]
        explanation.append(f"Success: {score:.2f}")

        # 添加顶部标签以进行解释
        sorted_probs = sorted(prob_map.probs.items(), key=lambda x: x[1], reverse=True)
        explanation.append(json.dumps(dict(sorted_probs)))

        # 收集事件 ID 以实现可重复性
        event_ids = [event.id for event in llm_convertible_events]

        # 对可视化特征进行分类
        categorized = categorize_features(prob_map.probs)

        return CriticResult(
            score=score,
            message="; ".join(explanation),
            metadata={
                "event_ids": event_ids,
                "categorized_features": categorized,
            },
        )

    def should_refine(self, critic_result: CriticResult) -> bool:
        """除了分数阈值之外，还使用 API 批评者分类信号。"""
        if super().should_refine(critic_result):
            return True
        if self.iterative_refinement is None:
            return False

        return bool(
            _get_high_probability_agent_issues(critic_result, self.issue_threshold)
        )

    def get_followup_prompt(self, critic_result: CriticResult, iteration: int) -> str:
        """使用评分细则预测生成详细的后续提示词。

        此重写提供了比基类更详细的反馈，包括所有分类特征（智能体行为问题，用户跟进模
        式，基础设施问题）及其概率。

        Args:
            critic_result: 批评家的结果来自上一次迭代。
            iteration: 当前迭代次数（1-索引）。

        Returns:
            带有标题预测的详细后续提示词字符串。
        """
        score_percent = critic_result.score * 100
        lines = [
            f"The task appears incomplete (iteration {iteration}, "
            f"predicted success likelihood: {score_percent:.1f}%).",
            "",
        ]

        # 从分类特征中提取详细的量规
        if critic_result.metadata and "categorized_features" in critic_result.metadata:
            categorized = critic_result.metadata["categorized_features"]

            # 智能体行为问题
            agent_issues = categorized.get("agent_behavioral_issues", [])
            if agent_issues:
                lines.append(
                    f"Potential agent issues: {_format_feature_list(agent_issues)}"
                )

            # 用户跟进模式（预测）
            user_patterns = categorized.get("user_followup_patterns", [])
            if user_patterns:
                formatted = _format_feature_list(user_patterns)
                lines.append(f"Predicted user follow-up needs: {formatted}")

            # 基础设施问题
            infra_issues = categorized.get("infrastructure_issues", [])
            if infra_issues:
                lines.append(
                    f"Infrastructure issues: {_format_feature_list(infra_issues)}"
                )

            # 其他指标
            other = categorized.get("other", [])
            if other:
                lines.append(f"Other observations: {_format_feature_list(other)}")

            if agent_issues or user_patterns or infra_issues or other:
                lines.append("")

        lines.extend(
            [
                "Please review what you've done and verify each requirement is met.",
                "List what's working and what needs fixing, then complete the task.",
            ]
        )

        return "\n".join(lines)
