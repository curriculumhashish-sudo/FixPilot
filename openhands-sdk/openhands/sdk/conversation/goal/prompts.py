"""提示词 ``/goal`` 命令的判断和继续消息的文本。"""

from typing import Final


JUDGE_SYSTEM_PROMPT: Final[str] = """\
You are auditing whether a long-running GOAL has been COMPLETED by an AI \
software agent.

Derive the concrete requirements implied by the objective. For EACH requirement,
look for authoritative evidence in the transcript: file contents, command
output, or test results produced by the agent. Treat missing, uncertain, or
merely-claimed-but-unverified evidence as NOT satisfied.

Respond with STRICT JSONand nothing else, in exactly this shape:
{"score": <float 0.0-1.0, probability the FULL objective is provably done>, \
"complete": <true|false>, "missing": "<concise description of what remains, or \
an empty string if complete>"}"""


JUDGE_USER_PROMPT: Final[str] = """\
<objective>
{objective}
</objective>

<transcript>
{transcript}
</transcript>"""


JUDGE_PROMPT: Final[str] = (
    JUDGE_SYSTEM_PROMPT.replace("{", "{{").replace("}", "}}")
    + "\n\n"
    + JUDGE_USER_PROMPT
)
"""系统控制提示词和用户载荷模板的向后兼容串联。 保持外部调用者仍然格式化单个提示词
continue to work; new code should use ``JUDGE_SYSTEM_PROMPT`` and
``JUDGE_USER_PROMPT``分别构建``system + user``消息对。

JUDGE_SYSTEM_PROMPT 携带原始的、未转义的 JSON 形状，因为它是在 ins ``judge_goal`` 中
未格式化发送的；
``JUDGE_PROMPT`` 重新转义它，以便组合模板保留下来
``.format(objective=..., transcript=...)``。
"""


FOLLOWUP_PROMPT: Final[str] = """The goal is NOT yet complete (audit iteration \
{iteration}).
Outstanding: {missing}

Inspect the real current state of the workspace (do not rely on memory). For \
each remaining requirement, make concrete progress and gather authoritative \
evidence by running the relevant tests/commands. Keep the full objective intact \
and finish only once every requirement is provably satisfied."""


RESUME_PROMPT: Final[str] = """Resuming a goal that was paused or interrupted. \
Re-check the real current state of the workspace (do not rely on memory) and \
continue making concrete, verified progress toward the original objective. \
Finish only once every requirement is provably satisfied."""
