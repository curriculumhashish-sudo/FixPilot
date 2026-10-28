import json

from openhands.sdk.critic.result import CriticResult


def test_format_critic_result_with_json_message():
    """以 JSON 概率测试格式化评论家结果。

    当未提供带有 categorized_features 的元数据时，原始 JSON 消息将按回退方案格式显示
    。
    """
    probs_dict = {
        "sentiment_neutral": 0.7612602710723877,
        "direction_change": 0.5926198959350586,
        "success": 0.5067704319953918,
        "sentiment_positive": 0.18567389249801636,
        "correction": 0.14625290036201477,
    }
    critic_result = CriticResult(score=0.507, message=json.dumps(probs_dict))

    # 测试可视化属性
    formatted = critic_result.visualize
    text = formatted.plain

    # 应以百分比显示星级
    assert "Critic: agent success likelihood" in text
    assert "★★★☆☆" in text  # 得分 0.507 轮为 3 星
    assert "(50.7%)" in text

    # 如果没有元数据，原始 JSON 消息将按原样显示
    assert "sentiment_neutral" in text
    assert "direction_change" in text
    assert "success" in text
    assert "correction" in text


def test_format_critic_result_with_plain_message():
    """使用纯文本消息测试格式化评论家结果。"""
    critic_result = CriticResult(score=0.75, message="This is a plain text message")

    formatted = critic_result.visualize
    text = formatted.plain

    # 应显示星级
    assert "Critic: agent success likelihood" in text
    assert "★★★★☆" in text  # 得分 0.75 轮为 4 星
    # 应显示纯文本消息
    assert "This is a plain text message" in text


def test_format_critic_result_without_message():
    """测试格式化评论结果，不带消息。"""
    critic_result = CriticResult(score=0.65, message=None)

    formatted = critic_result.visualize
    text = formatted.plain

    # 应显示星级
    assert "Critic: agent success likelihood" in text
    assert "★★★☆☆" in text  # 得分 0.65 轮为 3 星
    # 应该紧凑——只有几行
    assert text.count("\n") <= 3


def test_visualize_consistency():
    """测试可视化属性是否一致地格式化结果。

    如果未提供带有 categorized_features 的元数据，则按原样显示原始 JSON 消息。
    """
    probs_dict = {
        "success": 0.8,
        "sentiment_positive": 0.7,
        "sentiment_neutral": 0.2,
    }
    critic_result = CriticResult(score=0.8, message=json.dumps(probs_dict))

    formatted = critic_result.visualize.plain

    # 应显示星级
    assert "Critic: agent success likelihood" in formatted
    assert "★★★★☆" in formatted  # 0.8 轮得分为 4 星
    # 如果没有元数据，原始 JSON 消息将按原样显示
    assert "success" in formatted
    assert "sentiment_positive" in formatted
    assert "sentiment_neutral" in formatted


def test_format_critic_result_sorting():
    """测试在未提供元数据时是否显示原始 JSON 消息。

    当未提供带有 categorized_features 的元数据时，原始 JSON 消息将按原样显示，不进行
    过滤或排序。
    """
    probs_dict = {
        "low": 0.1,
        "medium": 0.5,
        "high": 0.9,
        "very_low": 0.01,
    }
    critic_result = CriticResult(score=0.5, message=json.dumps(probs_dict))

    formatted = critic_result.visualize
    text = formatted.plain

    # 如果没有元数据，将显示原始 JSON 消息中的所有键
    assert "high" in text
    assert "medium" in text
    assert "low" in text
    assert "very_low" in text


def test_color_highlighting():
    """测试可视化输出是否具有适当的样式。

    如果未提供带有 categorized_features 的元数据，则按原样显示原始 JSON 消息。 星级和
    标题仍然具有样式。
    """
    probs_dict = {
        "critical": 0.85,
        "important": 0.65,
        "notable": 0.40,
        "medium": 0.15,
        "minimal": 0.02,
    }
    critic_result = CriticResult(score=0.5, message=json.dumps(probs_dict))

    formatted = critic_result.visualize

    # 如果没有元数据，将显示原始 JSON 消息中的所有键
    text = formatted.plain
    assert "critical" in text
    assert "important" in text
    assert "notable" in text
    assert "medium" in text
    assert "minimal" in text

    # 验证 Span 包含星级的样式信息，标题 Rich Text 对象的 Span 包含（开始、结束、样式）
    # 元组
    #
    spans = list(formatted.spans)
    assert len(spans) > 0, "Should have styled spans"

    # 检查是否应用了不同的样式（只需验证它们存在）
    styles = {span.style for span in spans if span.style}
    assert len(styles) > 1, "Should have multiple different styles"


def test_star_rating():
    """测试分数是否映射到正确的星级评级。

    每颗星代表20%，使用round()进行换算。 Python 使用银行家四舍五入（四舍五入到偶数）
    。
    """
    # 5 星
    assert CriticResult._get_star_rating(1.0) == "★★★★★"

    # 4 星
    assert CriticResult._get_star_rating(0.9) == "★★★★☆"  # 4.5 比 4（庄家）
    assert CriticResult._get_star_rating(0.8) == "★★★★☆"
    assert CriticResult._get_star_rating(0.7) == "★★★★☆"  # 3.5 轮到 4 轮（庄家）

    # 3 星
    assert CriticResult._get_star_rating(0.6) == "★★★☆☆"
    assert CriticResult._get_star_rating(0.55) == "★★★☆☆"

    # 2星
    assert CriticResult._get_star_rating(0.5) == "★★☆☆☆"  # 2.5 比 2（庄家）
    assert CriticResult._get_star_rating(0.4) == "★★☆☆☆"
    assert CriticResult._get_star_rating(0.35) == "★★☆☆☆"

    # 1 星
    assert CriticResult._get_star_rating(0.3) == "★★☆☆☆"  # 1.5 比 2（庄家）
    assert CriticResult._get_star_rating(0.2) == "★☆☆☆☆"
    assert CriticResult._get_star_rating(0.15) == "★☆☆☆☆"

    # 0 星
    assert CriticResult._get_star_rating(0.1) == "☆☆☆☆☆"  # 0.5 舍入为 0（庄家）
    assert CriticResult._get_star_rating(0.0) == "☆☆☆☆☆"


def test_star_style():
    """根据分数测试星形样式是否正确。"""
    # 绿色表示 >= 0.6
    assert CriticResult._get_star_style(0.6) == "green"
    assert CriticResult._get_star_style(1.0) == "green"

    # 黄色为0.4-0.6
    assert CriticResult._get_star_style(0.4) == "yellow"
    assert CriticResult._get_star_style(0.59) == "yellow"

    # 红色表示 < 0.4
    assert CriticResult._get_star_style(0.0) == "red"
    assert CriticResult._get_star_style(0.39) == "red"


def test_visualize_with_categorized_features():
    """使用元数据中的分类特征测试可视化。"""
    categorized = {
        "sentiment": {
            "predicted": "Neutral",
            "probability": 0.77,
            "all": {"positive": 0.10, "neutral": 0.77, "negative": 0.13},
        },
        "agent_behavioral_issues": [
            {
                "name": "loop_behavior",
                "display_name": "Loop Behavior",
                "probability": 0.85,
            },
            {
                "name": "insufficient_testing",
                "display_name": "Insufficient Testing",
                "probability": 0.57,
            },
        ],
        "user_followup_patterns": [
            {
                "name": "direction_change",
                "display_name": "Direction Change",
                "probability": 0.59,
            },
        ],
        "infrastructure_issues": [],
        "other": [],
    }

    result = CriticResult(
        score=0.65,
        message="test",
        metadata={"categorized_features": categorized},
    )

    text = result.visualize.plain

    # 应显示星级
    assert "Critic: agent success likelihood" in text
    assert "★★★☆☆" in text  # 得分 0.65 轮为 3 星
    assert "(65.0%)" in text

    # 应显示问题的可能性百分比
    assert "Potential Issues:" in text
    assert "Loop Behavior" in text
    assert "(likelihood 85%)" in text
    assert "Insufficient Testing" in text
    assert "(likelihood 57%)" in text

    # 应显示后续模式
    assert "Likely Follow-up:" in text
    assert "Direction Change" in text
    assert "(likelihood 59%)" in text

    # 应不显示情绪（已删除）
    assert "Expected User Sentiment" not in text
