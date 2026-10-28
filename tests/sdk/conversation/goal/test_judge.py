"""测试 judge_goal / GoalVerdict（目标完成判断内核）。"""

from typing import cast

import pytest
from pydantic import PrivateAttr

from openhands.sdk.conversation.goal import GoalVerdict, judge_goal
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


def _judge(text: str) -> TestLLM:
    """法官 LLM 编写脚本返回单个判决字符串。"""
    return TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text=text)])]
    )


class _StreamGuardLLM(TestLLM):
    """TestLLM 强制执行真正的 LLM 的流式传输防护。

    让我们在调用之前证明 ``judge_goal`` 禁用流式传输
    ``completion()``（普通 ``TestLLM`` 完全忽略 ``stream``）。
    """

    def completion(
        self,
        messages,
        tools=None,
        add_security_risk_prediction=False,
        on_token=None,
        call_context=None,
        **kwargs,
    ):
        if self.stream and on_token is None:
            raise ValueError("Streaming requires an on_token callback")
        return super().completion(
            messages,
            tools,
            add_security_risk_prediction,
            on_token,
            call_context,
            **kwargs,
        )


@pytest.mark.parametrize(
    ("response", "score", "complete", "missing"),
    [
        # 准确-JSON 判决
        ('{"score": 0.9, "complete": true, "missing": ""}', 0.9, True, ""),
        # 不完整的判决揭示了缺失的工作
        (
            '{"score": 0.1, "complete": false, "missing": "tests not run"}',
            0.1,
            False,
            "tests not run",
        ),
        # JSON 嵌入散文/仍提取代码围栏
        (
            "Here is my verdict:\n```json\n"
            '{"score": 0.4, "complete": false, "missing": "lint"}\n```',
            0.4,
            False,
            "lint",
        ),
        # 不可解析 -> 保守（保持调用者正常工作）
        ("I cannot decide.", 0.0, False, "Judge verdict could not be parsed."),
        # 超出范围的分数被限制为 [0, 1]
        ('{"score": 1.5, "complete": true, "missing": ""}', 1.0, True, ""),
    ],
    ids=["complete", "incomplete", "json-in-fence", "unparseable", "clamped-score"],
)
def test_judge_goal_parses_verdict(response, score, complete, missing):
    verdict = judge_goal(_judge(response), "build it", [])
    assert isinstance(verdict, GoalVerdict)
    assert verdict.score == score
    assert verdict.complete is complete
    assert verdict.missing == missing


def test_judge_goal_disables_streaming_on_judge_llm():
    """Stream=True 判断 LLM 不得绊倒 completion() 的 on_token 守卫。"""
    llm = _StreamGuardLLM.from_messages(
        [
            Message(
                role="assistant",
                content=[
                    TextContent(text='{"score": 1.0, "complete": true, "missing": ""}')
                ],
            )
        ],
        usage_id="judge",
        stream=True,
    )
    verdict = judge_goal(llm, "build x", [])  # 没有修复就会提高
    assert verdict.complete


class _CapturingJudgeLLM(TestLLM):
    """TestLLM 记录传递给 ``completion()`` 的消息。"""

    _captured_messages: list = PrivateAttr(default_factory=list)

    @property
    def captured_messages(self) -> list:
        return self._captured_messages

    def completion(self, messages, **kwargs):  # type: ignore[override]
        self._captured_messages = list(messages)
        return super().completion(messages, **kwargs)


def test_judge_goal_sends_system_then_user():
    """判断请求必须在用户载荷之前通过系统消息打开。"""
    llm = cast(
        _CapturingJudgeLLM,
        _CapturingJudgeLLM.from_messages(
            [
                Message(
                    role="assistant",
                    content=[
                        TextContent(
                            text='{"score": 1.0, "complete": true, "missing": ""}'
                        )
                    ],
                )
            ]
        ),
    )

    judge_goal(llm, "build it", [])

    assert [m.role for m in llm.captured_messages] == ["system", "user"]
    # 转向/格式指令存在于系统消息中； 用户中的数据。
    system_text = llm.captured_messages[0].content[0].text
    user_text = llm.captured_messages[1].content[0].text
    assert "STRICT JSON" in system_text
    assert '"score"' in system_text
    assert "{{" not in system_text
    assert "<objective>" in user_text
    assert "build it" in user_text
