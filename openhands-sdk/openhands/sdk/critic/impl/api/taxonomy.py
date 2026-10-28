"""批评分类法 - 将特征映射到类别以进行可视化。"""

import math
from typing import Any


# 特征到类别的映射
FEATURE_CATEGORIES: dict[str, str] = {
    # 一般上下文和任务分类
    "user_goal_summary": "general_context",
    "overall_sentiment": "general_context",
    # 智能体行为问题
    "misunderstood_intention": "agent_behavioral_issues",
    "did_not_follow_instruction": "agent_behavioral_issues",
    "insufficient_analysis": "agent_behavioral_issues",
    "insufficient_clarification": "agent_behavioral_issues",
    "improper_tool_use_or_setup": "agent_behavioral_issues",
    "loop_behavior": "agent_behavioral_issues",
    "insufficient_testing": "agent_behavioral_issues",
    "insufficient_debugging": "agent_behavioral_issues",
    "incomplete_implementation": "agent_behavioral_issues",
    "file_management_errors": "agent_behavioral_issues",
    "scope_creep": "agent_behavioral_issues",
    "risky_actions_or_permission": "agent_behavioral_issues",
    "other_agent_issue": "agent_behavioral_issues",
    # 用户跟进模式
    "follow_up_timing": "user_followup_patterns",
    "clarification_or_restatement": "user_followup_patterns",
    "correction": "user_followup_patterns",
    "direction_change": "user_followup_patterns",
    "vcs_update_requests": "user_followup_patterns",
    "progress_or_scope_concern": "user_followup_patterns",
    "frustration_or_complaint": "user_followup_patterns",
    "removal_or_reversion_request": "user_followup_patterns",
    "other_user_issue": "user_followup_patterns",
    # 基础设施问题
    "infrastructure_external_issue": "infrastructure_issues",
    "infrastructure_agent_caused_issue": "infrastructure_issues",
}

# 用于可视化的类别显示名称
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "general_context": "General Context",
    "agent_behavioral_issues": "Detected Agent Behavioral Issues",
    "user_followup_patterns": "Predicted User Follow-Up Patterns",
    "infrastructure_issues": "Detected Infrastructure Issues",
}


def _softmax_normalize(probs: dict[str, float]) -> dict[str, float]:
    """应用 softmax 归一化将 logits 转换为概率。

    Args:
        probs: 名称到原始概率/logit 值的字典

    Returns:
        具有总和为 1.0 的 softmax 归一化概率的字典
    """
    if not probs:
        return {}

    values = list(probs.values())
    exp_values = [math.exp(v) for v in values]
    exp_sum = sum(exp_values)
    normalized = [exp_v / exp_sum for exp_v in exp_values]

    return dict(zip(probs.keys(), normalized))


def categorize_features(
    probs_dict: dict[str, float],
    display_threshold: float = 0.2,
) -> dict[str, Any]:
    """将概率字典中的特征分类为分类组。

    该函数从批评者模型中获取原始概率输出，并将它们组织成可供可视化的类别。

    Args:
        probs_dict: 特征名称到概率值的字典
        display_threshold: 包含某个功能的最小概率（默认值：0.2）

    Returns:
        具有可供可视化分类的特征的字典：
        {
            “情绪”：{
                “预测”：“中性”，“概率”：0.77，“全部”：{“积极”：0.10，“中性”：0.77，“
                消极”：0.13}
            },
            "agent_behavioral_issues": [
                {"name": "loop_behavior", "display_name": "Loop Behavior",
                 “概率”：0.85}，
                ...
            ],
            “user_followup_patterns”：[...]，“infrastructure_issues”：[...]，“其他”：
            [...]
        }
    """
    result: dict[str, Any] = {
        "sentiment": None,
        "agent_behavioral_issues": [],
        "user_followup_patterns": [],
        "infrastructure_issues": [],
        "other": [],
    }

    # 提取情感特征并应用 softmax 归一化
    raw_sentiment_probs = {}
    for feature_name, prob in probs_dict.items():
        if feature_name.startswith("sentiment_"):
            short_name = feature_name.replace("sentiment_", "")
            raw_sentiment_probs[short_name] = prob

    if raw_sentiment_probs:
        # 应用 softmax 归一化将 logits 转换为概率
        sentiment_probs = _softmax_normalize(raw_sentiment_probs)
        max_sentiment = max(sentiment_probs.items(), key=lambda x: x[1])
        result["sentiment"] = {
            "predicted": max_sentiment[0].capitalize(),
            "probability": max_sentiment[1],
            "all": sentiment_probs,
        }

    # 对其他功能进行分类
    for feature_name, prob in probs_dict.items():
        # 跳过情感特征（已处理）
        if feature_name.startswith("sentiment_"):
            continue

        # 跳过“成功”，因为它对分数来说是多余的
        if feature_name == "success":
            continue

        # 跳过低于阈值的特征
        if prob < display_threshold:
            continue

        category = FEATURE_CATEGORIES.get(feature_name)
        feature_entry = {
            "name": feature_name,
            "display_name": feature_name.replace("_", " ").title(),
            "probability": prob,
        }

        if category == "general_context":
            # 暂时跳过常规上下文功能
            continue
        elif category == "agent_behavioral_issues":
            result["agent_behavioral_issues"].append(feature_entry)
        elif category == "user_followup_patterns":
            result["user_followup_patterns"].append(feature_entry)
        elif category == "infrastructure_issues":
            result["infrastructure_issues"].append(feature_entry)
        else:
            result["other"].append(feature_entry)

    # 按概率对每个类别进行排序（降序）
    for key in [
        "agent_behavioral_issues",
        "user_followup_patterns",
        "infrastructure_issues",
        "other",
    ]:
        result[key] = sorted(result[key], key=lambda x: x["probability"], reverse=True)

    return result
