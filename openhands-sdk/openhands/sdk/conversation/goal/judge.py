"""LLM 判断，决定 ``/goal`` 目标是否完成。

这是目标功能的可重用内核：一个纯粹的
``objective + transcript -> verdict`` 不依赖于批评者机制的评估者。 ``/goal`` 运行程序
使用它来驱动继续，但它同样可以支持状态
命令、停止挂钩或服务器端点。
"""

import contextlib
import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from openhands.sdk.conversation.goal.prompts import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_PROMPT,
)
from openhands.sdk.event import Event, LLMConvertibleEvent
from openhands.sdk.llm import LLM, Message, TextContent, content_to_str
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class GoalVerdict(BaseModel):
    """法官对目标是否完成的判断。"""

    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Probability (0-1) that the full objective is provably done.",
    )
    complete: bool = Field(
        description="Whether the judge considers the objective complete."
    )
    missing: str = Field(
        default="",
        description="Concise description of what remains, or empty if complete.",
    )


def judge_goal(judge_llm: LLM, objective: str, events: Sequence[Event]) -> GoalVerdict:
    """审核成绩单并确定 ``objective`` 是否完整。

    Args:
        judge_llm: 第二个 LLM 表示完成度。
        objective: 审计目标。
        events: 对话事件（非 LLM 事件将被忽略）。

    Returns:
        A GoalVerdict. 对于无法解析的判断响应，返回保守的低分，以便调用者继续工作而不
        是错误地完成。
    """
    convertible = [e for e in events if isinstance(e, LLMConvertibleEvent)]
    transcript = _render_transcript(convertible)
    system_prompt = JUDGE_SYSTEM_PROMPT
    user_prompt = JUDGE_USER_PROMPT.format(objective=objective, transcript=transcript)

    # 法官只需要判决文本。 强制非流式传输，因此重用流式传输智能体 LLM，因为当流 = True
    # 时，法官不会触发 completion() 对 on_token 回调的要求。
    #
    if judge_llm.stream:
        judge_llm = judge_llm.model_copy(update={"stream": False})
    # 构建规范系统+用户对：系统消息中存在转向/格式指令，用户消息中存在目标+转录本载荷。
    #
    response = judge_llm.completion(
        messages=[
            Message(role="system", content=[TextContent(text=system_prompt)]),
            Message(role="user", content=[TextContent(text=user_prompt)]),
        ]
    )
    verdict = _parse_verdict(response.message)
    logger.debug("judge_goal verdict: %s", verdict)
    return verdict


def _render_transcript(events: Sequence[LLMConvertibleEvent]) -> str:
    """将事件呈现为法官的简单 ``role: text`` 记录。

    智能体的``system`` 提示词被排除：它很大（~数千个token），没有特定目标证据，因此它
    只会增加审计token的成本。
    """
    turns = [
        (msg.role, text)
        for msg in LLMConvertibleEvent.events_to_messages(list(events))
        if msg.role != "system"
        and (text := "\n".join(content_to_str(msg.content)).strip())
    ]
    return "\n\n".join(f"{role}: {text}" for role, text in turns)


def _parse_verdict(message: Message) -> GoalVerdict:
    """保守地将法官响应归一化为 GoalVerdict。"""
    raw = "\n".join(content_to_str(message.content)).strip()

    data: dict[str, Any] | None = None
    candidates = [raw]
    block = re.search(r"\{.*\}", raw, re.DOTALL)
    if block:
        candidates.append(block.group(0))
    for candidate in candidates:
        with contextlib.suppress(json.JSONDecodeError):
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                data = parsed
                break

    if data is None:
        logger.warning("judge_goal: could not parse verdict: %r", raw)
        return GoalVerdict(
            score=0.0, complete=False, missing="Judge verdict could not be parsed."
        )

    try:
        score = float(data.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))

    return GoalVerdict(
        score=score,
        complete=bool(data.get("complete", score >= 1.0)),
        missing=str(data.get("missing") or ""),
    )
