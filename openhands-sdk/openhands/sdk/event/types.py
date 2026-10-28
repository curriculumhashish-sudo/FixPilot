from typing import Annotated, Final, Literal

from openhands.sdk.utils.masking import SkipSecretMasking


EventType = Literal["action", "observation", "message", "system_prompt", "agent_error"]
SourceType = Literal["agent", "user", "environment", "hook"]

UnmaskedID = Annotated[str, SkipSecretMasking()]
"""机密屏蔽永远不会重写的标识符。

对于事件上的每个 id 字段或观测结果，使用它或 ``EventID`` / ``ToolCallID``。 屏蔽的事
件 ID 会破坏事件文件名，因此对话无法重新加载。 屏
蔽的工具调用 ID 会破坏 LLM 请求中的工具调用配对。
"""

EventID = UnmaskedID
"""输入事件 ID 的别名。"""

ROOT_PARENT_ID: Final = "__root__"
"""保留 ``parent_id`` 标记在 ``navigate_to(None)`` 之后创建的树根。

没有事件 ``id`` 可以等于它（由验证器对 ``Event`` 强制执行），因此
``parent_id == ROOT_PARENT_ID`` 明确表示“根”，而不是“id 为 ``__root__`` 的事件的子级”
。
"""

ToolCallID = UnmaskedID
"""键入工具调用 ID 的别名。"""
