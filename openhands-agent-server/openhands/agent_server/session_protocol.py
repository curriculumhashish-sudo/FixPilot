"""``/sockets/session/{conversation_id}`` 的有线协议。

不是建立在 ``Event`` 之上：遗留端点发送它持久化和验证的相同类，并且 ``Event`` 是
``extra="forbid"``，因此每个线字段都将是存储迁移。
 这里 ``Event`` 位于一个信封内，未受影响，并且协议字段位于信封上。

URL 是协议版本——没有握手，没有 ``protocol`` 字段。

发货规则：

1. ``Durable`` 通过 ``after_seq`` 重新连接后仍然存在； 在连接内，它可能会被丢弃，这就
是让缓慢的消费者断开连接而不是阻止发布者的原因。
2. ``Delta``可以自由丢弃； 间隙标志着槽有损，真实文本与持久消息一起到达。
3. 每个 ``ItemStarted`` 恰好被一个 ``Durable`` 退休或
   ``ItemAborted``. ``item_id`` * 是 * 完成的消息的 ``Event.id``，因此客户端关闭
   ``frame.event.id == slot.item_id`` 上的槽。
4. 进度帧永远不会重播。
5. 两个未清项目之间不承诺订购。
"""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from openhands.sdk import Event


# PROVISIONAL. 该上限是根据测量的帧大小分布得出的，但尚未完成。 不要将这些视为已调整的。
#

MAX_FRAME_BYTES: Final[int] = 4 * 1024 * 1024
"""服务器将发出的最大帧； 较大的会断开连接。"""

MAX_PENDING_BYTES: Final[int] = 4 * MAX_FRAME_BYTES
"""每个连接写入预算。 超过它，连接就会断开。"""


class SessionFrameBase(BaseModel):
    """每个框架的基础。

    故意不``extra="forbid"``：信封是为了增长，客户必须忽略他们不认识的东西。
    """

    model_config = ConfigDict(frozen=True)


class SyncFrame(SessionFrameBase):
    """在任何重播之前发送一次，描述即将发送的范围。"""

    type: Literal["sync"] = "sync"
    from_seq: int | None = Field(
        default=None,
        description=(
            "Exclusive lower bound of the replay range, echoing the client's "
            "`after_seq`. None means no history was requested."
        ),
    )
    through_seq: int | None = Field(
        default=None,
        description=(
            "Highest sequence number on disk when the connection was "
            "established; everything above it arrives live. None if empty."
        ),
    )


class DurableFrame(SessionFrameBase):
    """安全存入磁盘后发生的一个已持久化事件。

    ``seq`` 是它在日志中的索引，已经作为 ``{idx:05d}`` 文件名组件在磁盘上，因此公开它
    不需要迁移。
    """

    type: Literal["durable"] = "durable"
    seq: int
    event: Event


class TransientFrame(SessionFrameBase):
    """已发布但从未发布的事件已持久化。

    保持``seq``诚实：如果一帧有一个，那么它是真实的并且可恢复。 客户端呈现这些，但不
    得将光标移到它们上。
    """

    type: Literal["transient"] = "transient"
    event: Event


class ItemStartedFrame(SessionFrameBase):
    """一条溪流正在打开。 每次尝试发送一次，在第一个 token 之前。

    一个更高的 ``attempt`` 同样的原因 ``item_id`` 取代了一个更低一级的，所以需要重新
    流重试不像新文本那样读。 ``anchor_seq`` s
    eq是slot之后的序号，所以中途到达的用户消息无法分割它。
    """

    type: Literal["item_started"] = "item_started"
    item_id: str
    attempt: int = 1
    anchor_seq: int | None = None


class DeltaFrame(SessionFrameBase):
    """流的一个屏蔽增量。

    ``order`` 在 (``item_id``, ``attempt``) 内是单调的，因此客户端可以检测到间隙，而
    不是修复间隙。
    """

    type: Literal["delta"] = "delta"
    item_id: str
    attempt: int = 1
    order: int
    kind: Literal["text", "reasoning"] = "text"
    content: str
    chunk_id: str | None = Field(
        default=None,
        description=(
            "The provider's completion id for this chunk. Corroboration only: "
            "litellm mints a new one per retry attempt."
        ),
    )
    choice_index: int | None = Field(
        default=None, description="The provider's choice index for this chunk."
    )


class ItemAbortedFrame(SessionFrameBase):
    """流结束但未产生消息。

    如果没有它，取消或失败的流将永远搁置开放槽。
    """

    type: Literal["item_aborted"] = "item_aborted"
    item_id: str
    attempt: int = 1
    reason: str


class ErrorFrame(SessionFrameBase):
    """此套接字有问题，从来没有已持久化。

    与 ``ConversationErrorEvent`` 不同，这是关于对话的持久事实。
    """

    type: Literal["error"] = "error"
    code: str
    detail: str


SessionFrame = Annotated[
    SyncFrame
    | DurableFrame
    | TransientFrame
    | ItemStartedFrame
    | DeltaFrame
    | ItemAbortedFrame
    | ErrorFrame,
    Field(discriminator="type"),
]
