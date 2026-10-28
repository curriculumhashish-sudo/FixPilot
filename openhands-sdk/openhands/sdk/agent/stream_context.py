"""一个智能体步骤的流身份：铸造它，标记增量，关闭它一次。

持久事件是使用铸造的 id 构建的，因此客户端将其在 ``frame.event.id == slot.item_id``
上的开放插槽退役。

预先创建对于仅附加日志是安全的，因为它不是写入：
``Event.id`` 已经是客户端在进程中创建的 (``event/base.py``)，因此只有 * 当 *
``uuid4()`` 运行时才会更改，并且未使用的 I
D 永远不会在磁盘上。
"""

from __future__ import annotations

import asyncio
import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from openhands.sdk.conversation.secret_registry import StreamOutputMask
from openhands.sdk.llm.streaming import LLMStreamChunk
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation


logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StreamStarted:
    """一条溪流正在打开。 每次尝试一次，在第一个 token 之前。

    ``anchor_seq`` 是槽所在的 seq，因此到达中流的用户消息无法拆分它。
    """

    item_id: str
    attempt: int
    anchor_seq: int | None


@dataclass(frozen=True, slots=True)
class StreamDelta:
    """流的一个屏蔽增量。

    ``chunk_id`` 只是佐证： LiteLLM 生成一个新的完成标识重试尝试了，因此无法识别持久
    事件。
    """

    item_id: str
    attempt: int
    order: int
    kind: Literal["text", "reasoning"]
    content: str
    chunk_id: str | None = None
    choice_index: int | None = None


@dataclass(frozen=True, slots=True)
class StreamAborted:
    """流结束时未产生持久事件。"""

    item_id: str
    attempt: int
    reason: str


StreamProgress = StreamStarted | StreamDelta | StreamAborted
StreamProgressCallbackType = Callable[[StreamProgress], None]


class StreamContext:
    """一个流式传输槽：铸造它的 id，标记它的增量，关闭它一次。"""

    def __init__(
        self,
        item_id: str,
        anchor_seq: int | None,
        on_token: Callable[[Any], None] | None,
        on_stream: StreamProgressCallbackType | None,
        mask: Callable[[], StreamOutputMask],
    ) -> None:
        self.item_id = item_id
        self._anchor_seq = anchor_seq
        self._on_token = on_token
        self._on_stream = on_stream
        self._mask = mask
        # 每种掩码器：文本和推理是分开排序的，并且掩码器在其自身类型的块中保留部分机密。
        #
        self._masks: dict[Literal["text", "reasoning"], StreamOutputMask] = {}
        self._attempt = 1
        self._order = itertools.count()
        self._started = False
        self._opened = False
        self._started_attempt: int | None = None
        self._reserved = False
        self._claimed = False
        self._chunk_id: str | None = None

    @classmethod
    def open(
        cls,
        conversation: LocalConversation,
        on_token: Callable[[Any], None] | None,
    ) -> StreamContext:
        """创建一个 id 并读取锚点。 两者都不触及事件日志。"""
        state = conversation.state
        length = len(state.events)
        return cls(
            item_id=str(uuid.uuid4()),
            anchor_seq=length - 1 if length else None,
            on_token=on_token,
            on_stream=conversation.on_stream,
            mask=state.secret_registry.compile_stream_mask,
        )

    @property
    def token_callback(self) -> Callable[[Any], None] | None:
        """回调交给 LLM，或者当没有东西消耗它时 ``None``。

        当 ``on_token`` 为 ``None`` 时，``llm.completion`` 将 ``stream=True`` 模型降
        级为非流式传输调用
        (#4014)； 无条件包装器会将回退方案拿走。
        """
        if self._on_token is None and self._on_stream is None:
            return None
        return self.on_chunk

    def on_chunk(self, chunk: Any) -> None:
        """将原始块转发到下游，然后发出其标记的增量。

        传递是让现有 ``on_token`` 消费者准确看到他们今天所看到的内容的原因。
        """
        if self._on_token is not None:
            self._on_token(chunk)
        if self._on_stream is None:
            return
        try:
            for kind, text, chunk_id, choice_index in _split_chunk(chunk):
                self._emit_delta(kind, text, chunk_id, choice_index)
        except Exception:
            # 进步是用户体验的可供性； 永远不会失败。
            logger.debug("stream progress emission failed", exc_info=True)

    def new_attempt(self) -> None:
        """对同一项目开始新的尝试； 更高的取代。"""
        if not self._opened:
            return
        self._attempt += 1
        self._order = itertools.count()
        self._started = False
        self._chunk_id = None
        # 新的尝试重新流式传输该项目，因此旧的尾部被取代。
        self._masks.clear()

    def claim(self) -> str | None:
        """为正在构建的持久事件保留铸造的 ID。

        ``None`` 一旦保留，因此同一步骤中的第二个持久事件将保留其自己的 id 而不会发生
        冲突。 保留并不意味着退休
        slot: 从未发出的事件仍然需要中止，因此
        一旦发射成功，调用者必须：meth:`commit`。
        """
        if self._reserved or self._on_stream is None:
            return None
        self._flush()
        self._reserved = True
        return self.item_id

    def commit(self) -> None:
        """退出槽：发出带有 id 的持久事件。"""
        if self._reserved:
            self._claimed = True

    def close(self, reason: str) -> None:
        """除非持久事件提交了该 ID，否则发出 ``StreamAborted``。

        关注的是永远打开的，而不是当前的尝试：在第一个 token 之前死亡的重试仍然欠下流
        的答案。
        """
        if not self._opened or self._claimed:
            return
        self._claimed = True
        self._flush()
        self._emit(
            StreamAborted(self.item_id, self._started_attempt or self._attempt, reason)
        )

    def __enter__(self) -> StreamContext:
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        self.close(_abort_reason(exc_type))
        return False

    def _emit_delta(
        self,
        kind: Literal["text", "reasoning"],
        text: str,
        chunk_id: str | None,
        choice_index: int | None,
    ) -> None:
        if chunk_id is not None and self._chunk_id is not None:
            if chunk_id != self._chunk_id:
                # LiteLLM 每次尝试都会生成一个完成ID，因此在中间步骤中更改ID相当于重新播
                # 放同一个槽位。
                #
                self.new_attempt()
        self._chunk_id = chunk_id
        if not self._started:
            self._started = self._opened = True
            self._started_attempt = self._attempt
            self._emit(StreamStarted(self.item_id, self._attempt, self._anchor_seq))
        masker = self._masks.get(kind)
        if masker is None:
            masker = self._masks[kind] = self._mask()
        released = masker.feed(text)
        if released:
            self._emit_content(kind, released, chunk_id, choice_index)

    def _flush(self) -> None:
        """释放每个掩蔽器阻止分裂的尾巴机密。"""
        for kind, masker in self._masks.items():
            held = masker.flush()
            if held:
                self._emit_content(kind, held, self._chunk_id, None)
        self._masks.clear()

    def _emit_content(
        self,
        kind: Literal["text", "reasoning"],
        content: str,
        chunk_id: str | None,
        choice_index: int | None,
    ) -> None:
        self._emit(
            StreamDelta(
                item_id=self.item_id,
                attempt=self._attempt,
                order=next(self._order),
                kind=kind,
                content=content,
                chunk_id=chunk_id,
                choice_index=choice_index,
            )
        )

    def _emit(self, frame: StreamProgress) -> None:
        """从不引发：``close()`` 从 ``__exit__`` 运行，其中出现接收器错误
        将替换该步骤正在展开的异常。"""
        assert self._on_stream is not None
        try:
            self._on_stream(frame)
        except Exception:
            logger.debug("stream progress sink failed", exc_info=True)


def _abort_reason(exc_type: type[BaseException] | None) -> str:
    if exc_type is None:
        return "no_durable_event"
    if issubclass(exc_type, (asyncio.CancelledError, KeyboardInterrupt)):
        return "cancelled"
    return exc_type.__name__


def _split_chunk(
    chunk: LLMStreamChunk | str,
) -> list[tuple[Literal["text", "reasoning"], str, str | None, int | None]]:
    """将 token-回调载荷分解为它所携带的增量。

    ACP 桥穿过裸露的 ``str`` 层，并且永远不会进入 LLM 层，这就是为什么它位于两者之上
    而不是 ``llm.py`` 中。
    """
    if isinstance(chunk, str):
        return [("text", chunk, None, None)] if chunk else []

    out: list[tuple[Literal["text", "reasoning"], str, str | None, int | None]] = []
    for choice in chunk.choices or ():
        delta = choice.delta
        if delta is None:
            continue
        reasoning = (
            delta.reasoning_content
            if "reasoning_content" in delta.model_fields_set
            else None
        )
        if isinstance(reasoning, str) and reasoning:
            out.append(("reasoning", reasoning, chunk.id, choice.index))
        if isinstance(delta.content, str) and delta.content:
            out.append(("text", delta.content, chunk.id, choice.index))
    return out
