from typing import Any, ClassVar

from pydantic import BaseModel, Field
from rich.text import Text


class CriticResult(BaseModel):
    """评论家的结果是一个分数和一条消息。"""

    THRESHOLD: ClassVar[float] = 0.5
    DISPLAY_THRESHOLD: ClassVar[float] = 0.2  # 仅显示高于此阈值的分数

    score: float = Field(
        description="A predicted probability of success between 0 and 1.",
        ge=0.0,
        le=1.0,
    )
    message: str | None = Field(description="An optional message explaining the score.")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional metadata about the critic evaluation. "
            "Can include event_ids and categorized_features for visualization."
        ),
    )

    @property
    def success(self) -> bool:
        """智能体是否成功。"""
        return self.score >= CriticResult.THRESHOLD

    @staticmethod
    def _get_star_rating(score: float) -> str:
        """将分数 (0-1) 转换为 5 星级评级字符串。

        每颗星代表分数的 20%。
        """
        filled_stars = round(score * 5)
        empty_stars = 5 - filled_stars
        return "★" * filled_stars + "☆" * empty_stars

    @staticmethod
    def _get_star_style(score: float) -> str:
        """根据分数获取星级评定的样式。"""
        if score >= 0.6:
            return "green"
        elif score >= 0.4:
            return "yellow"
        else:
            return "red"

    @property
    def visualize(self) -> Text:
        """返回评论家结果的富文本表示。"""
        content = Text()
        content.append("\n\nCritic: agent success likelihood ", style="bold")

        # 以百分比显示星级
        stars = self._get_star_rating(self.score)
        style = self._get_star_style(self.score)
        percentage = self.score * 100
        content.append(stars, style=style)
        content.append(f" ({percentage:.1f}%)", style="dim")

        # 如果可用的话，使用元数据中的分类特征
        if self.metadata and "categorized_features" in self.metadata:
            categorized = self.metadata["categorized_features"]
            self._append_categorized_features(content, categorized)
        else:
            # 回退方案：按原样显示消息
            if self.message:
                content.append(f"\n  {self.message}\n")
            else:
                content.append("\n")

        return content

    def _append_categorized_features(
        self, content: Text, categorized: dict[str, Any]
    ) -> None:
        """将分类功能附加到内容中，每个类别独占一行。"""
        has_content = False

        # 智能体行为问题
        agent_issues = categorized.get("agent_behavioral_issues", [])
        if agent_issues:
            content.append("\n  ")
            content.append("Potential Issues: ", style="bold")
            self._append_feature_list_inline(content, agent_issues)
            has_content = True

        # 用户跟进模式
        user_patterns = categorized.get("user_followup_patterns", [])
        if user_patterns:
            content.append("\n  ")
            content.append("Likely Follow-up: ", style="bold")
            self._append_feature_list_inline(content, user_patterns)
            has_content = True

        # 基础设施问题
        infra_issues = categorized.get("infrastructure_issues", [])
        if infra_issues:
            content.append("\n  ")
            content.append("Infrastructure: ", style="bold")
            self._append_feature_list_inline(content, infra_issues)
            has_content = True

        # 其他指标
        other = categorized.get("other", [])
        if other:
            content.append("\n  ")
            content.append("Other: ", style="bold")
            self._append_feature_list_inline(content, other, is_other=True)
            has_content = True

        if not has_content:
            content.append("\n")
        else:
            content.append("\n")

    def _append_feature_list_inline(
        self,
        content: Text,
        features: list[dict[str, Any]],
        is_other: bool = False,
    ) -> None:
        """附加与可能性百分比内联的特征。"""
        for i, feature in enumerate(features):
            display_name = feature.get("display_name", feature.get("name", "Unknown"))
            prob = feature.get("probability", 0.0)
            percentage = prob * 100

            # 根据概率获取样式
            if is_other:
                prob_style = "white"
            elif prob >= 0.7:
                prob_style = "red bold"
            elif prob >= 0.5:
                prob_style = "yellow"
            else:
                prob_style = "dim"

            # 在特征之间添加点分隔符
            if i > 0:
                content.append(" · ", style="dim")

            content.append(f"{display_name}", style="white")
            content.append(f" (likelihood {percentage:.0f}%)", style=prob_style)
