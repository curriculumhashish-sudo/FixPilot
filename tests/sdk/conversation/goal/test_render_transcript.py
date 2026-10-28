"""对法官在 REAL 轨迹上看到的准确记录进行的一次完整测试。

``fixtures/events.jsonl`` 是实际对话的已持久化事件的修剪片段（PR-审查自动化运行：
``terminal`` 工具调用 + 观测结果
+ 状态更新），加载了 SDK 的真实解串器
(``Event.model_validate_json``). ``fixtures/expected_transcript.txt`` 正是
``judge_goal`` 为法官提供的逐字节黄金——因此这也保护了渲染和已持久化事件格式。
"""

from collections import Counter
from pathlib import Path

import pytest

from openhands.sdk.conversation.goal import judge_goal
from openhands.sdk.conversation.goal.judge import _render_transcript
from openhands.sdk.event import Event, LLMConvertibleEvent, SystemPromptEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


# 跟踪的 `terminal` 工具操作需要 OpenHands-工具来反序列化其类型； 在未安装的独立
# OpenHands-SDK 中跳过运行。
#
pytest.importorskip("openhands.tools.terminal")


_FIXTURES = Path(__file__).parent / "fixtures"


def _load_trace() -> list[Event]:
    lines = (_FIXTURES / "events.jsonl").read_text().splitlines()
    return [Event.model_validate_json(line) for line in lines if line.strip()]


def test_render_transcript_for_judge():
    events = _load_trace()

    # 真实跟踪：智能体工具调用 + 观测结果 +（非渲染）状态更新。
    kinds = Counter(type(e).__name__ for e in events)
    assert kinds["ActionEvent"] and kinds["ObservationEvent"]
    assert kinds["ConversationStateUpdateEvent"]  # 存在，但是不 LLM-可转换

    convertible = [e for e in events if isinstance(e, LLMConvertibleEvent)]
    transcript = _render_transcript(convertible)

    # 工具调用渲染为：ActionEvent->辅助推理回合，ObservationEvent->`tool:`回合。
    #
    assert "assistant: <think>" in transcript
    assert "\n\ntool: " in transcript
    # 机密是法官所见的已脱敏。
    assert "<secret-hidden>" in transcript

    # （大型）系统提示词在设计上被排除在外：前置 SystemPromptEvent 不会更改渲染的转录本
    # 。
    #
    system_event = SystemPromptEvent(
        system_prompt=TextContent(text="<SOUL>...big system prompt...</SOUL>"),
        tools=[],
    )
    assert _render_transcript([system_event, *convertible]) == transcript

    # 完整的内核将这份记录转化为判决（法官的反馈）。
    judge = TestLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[TextContent(text='{"score": 0.8, "complete": true}')],
            )
        ]
    )
    verdict = judge_goal(judge, "Review PR #3745", events)
    assert verdict.complete is True
    assert verdict.score == 0.8

    # 逐字节：EXACTLY什么judge_goal通过真实轨迹向法官提供信息。
    expected = (_FIXTURES / "expected_transcript.txt").read_text()
    assert transcript == expected
