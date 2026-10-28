"""``/sockets/session/{conversation_id}`` — 会话套接字。

修复了遗留 ``/sockets/events/{id}`` 端点的三个错误，但没有触及它：帧是信封而不是磁盘
记录； 历史和实时交通不能交织； 并且缓慢的消费者无法楔入发布
者，因为准入是字节限制的，并且只有该连接的写入器任务等待套接字。
"""

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from openhands.agent_server.conversation_service import (
    CredentialBindingActivationRequired,
)
from openhands.agent_server.pub_sub import MaxSubscribersError, Subscriber
from openhands.agent_server.session_protocol import (
    MAX_FRAME_BYTES,
    MAX_PENDING_BYTES,
    DeltaFrame,
    DurableFrame,
    ErrorFrame,
    ItemAbortedFrame,
    ItemStartedFrame,
    SessionFrameBase,
    SyncFrame,
    TransientFrame,
)
from openhands.agent_server.sockets import (
    _accept_authenticated_websocket,
    _get_conversation_service,
    _is_auth_control_message,
    _is_websocket_connected,
    _safe_close_websocket,
)
from openhands.sdk import Event, Message
from openhands.sdk.agent.stream_context import (
    StreamAborted,
    StreamDelta,
    StreamProgress,
    StreamStarted,
)
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.event import StreamingDeltaEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent


session_router = APIRouter(prefix="/sockets", tags=["WebSockets"])
logger = logging.getLogger(__name__)

REPLAY_PAGE_SIZE: Final[int] = 100
"""每个执行器跃点从磁盘读取的事件。"""


@dataclass(slots=True)
class _ConnectionWriter:
    """在单个写入器任务之前进行字节限制、非阻塞的准入。

    ``send`` 是故意的同步：它在 pub/sub 扇出中运行，绝不能等待此套接字，否则一个楔形
    选项卡会阻止发布者。 排序来自队列加上一个排出任务。

    溢出会丢弃连接，而不是帧 - 丢弃 ``Durable`` 会破坏客户端所依赖的保证，而重新连接
    ``after_seq`` 没有任何损失。 断开连接就是背压。
    """

    websocket: WebSocket
    max_frame_bytes: int = MAX_FRAME_BYTES
    max_pending_bytes: int = MAX_PENDING_BYTES

    closed_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    drop_reason: str | None = field(default=None, init=False)

    _queue: deque[tuple[str, int]] = field(default_factory=deque, init=False)
    _wake: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _pending_bytes: int = field(default=0, init=False)
    _task: asyncio.Task | None = field(default=None, init=False)

    @property
    def closed(self) -> bool:
        return self.closed_event.is_set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def send(self, frame: SessionFrameBase) -> bool:
        """承认一帧，从不阻塞。 False 如果连接完成。"""
        if self.closed:
            return False

        payload = frame.model_dump_json(exclude_none=True)
        size = len(payload.encode("utf-8"))

        if size > self.max_frame_bytes:
            # 值得一提的是：这意味着框架预算需要重新审视。
            logger.warning(
                "session_socket_frame_too_large: %d bytes > %d",
                size,
                self.max_frame_bytes,
            )
            self._fail("frame_too_large")
            return False

        if self._pending_bytes + size > self.max_pending_bytes:
            logger.info(
                "session_socket_slow_consumer: pending=%d incoming=%d budget=%d",
                self._pending_bytes,
                size,
                self.max_pending_bytes,
            )
            self._fail("slow_consumer")
            return False

        self._queue.append((payload, size))
        self._pending_bytes += size
        self._wake.set()
        return True

    def _fail(self, reason: str) -> None:
        if not self.closed:
            self.drop_reason = reason
            self.closed_event.set()
        self._wake.set()

    async def _run(self) -> None:
        try:
            while not self.closed:
                await self._wake.wait()
                self._wake.clear()
                while self._queue:
                    if self.closed:
                        return
                    payload, size = self._queue.popleft()
                    self._pending_bytes -= size
                    if not _is_websocket_connected(self.websocket):
                        self._fail("disconnected")
                        return
                    await self.websocket.send_text(payload)
        except asyncio.CancelledError:
            raise
        except (RuntimeError, WebSocketDisconnect):
            # Peer 在状态检查和发送之间离开了。
            self._fail("disconnected")
        except Exception:
            logger.exception("session_socket_writer_error", stack_info=True)
            self._fail("writer_error")

    async def aclose(self) -> None:
        self._fail("closing")
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # 只吞下我们要求的取消； 一项旨在完成这项任务的任务意味着关闭，绝不能被
                # 吸收。
                #
                if not task.cancelled():
                    raise
            except Exception:
                pass


@dataclass(slots=True)
class _SessionSubscriber(Subscriber[Event]):
    """将事件转换为帧并将其交给编写者。

    开始缓冲，以便历史记录可以在下面重播而无需交错；
    ``go_live`` 冲洗并切换到直通。
    """

    writer: _ConnectionWriter
    events: EventLog

    _buffer: list[Event] | None = field(default_factory=list, init=False)

    async def __call__(self, event: Event) -> None:
        if isinstance(event, StreamingDeltaEvent):
            # 三角洲从来不走持久航道； 进度帧来自 StreamContext，通过它们自己的扇出。
            #
            return
        if self._buffer is not None:
            self._buffer.append(event)
            return
        self._emit(event)

    def _emit(self, event: Event) -> None:
        seq = self._seq_of(event)
        frame: SessionFrameBase = (
            TransientFrame(event=event)
            if seq is None
            else DurableFrame(seq=seq, event=event)
        )
        self.writer.send(frame)

    def _seq_of(self, event: Event) -> int | None:
        """事件在日志中的索引，如果不是已持久化，则为 None。

        通过查找，而不是通过类型：大多数 ``ConversationStateUpdateEvent`` * 都附加了
        *，因此将类型视为瞬态会剥离它们的
        ``seq`` 并击败 ``go_live`` 中的重复数据删除。 一个真正不持久的事件是连接时的
        快照 ``subscribe_to_events`` 综合
        ，因此只有任何 * 其他 * 缺失的内容才值得警告。
        """
        try:
            return self.events.get_index(event.id)
        except KeyError:
            if not isinstance(event, ConversationStateUpdateEvent):
                logger.warning(
                    "session_socket_event_published_before_persist: kind=%s id=%s",
                    type(event).__name__,
                    event.id,
                )
            return None

    def go_live(self, through_seq: int | None) -> None:
        """刷新缓冲区，删除已从磁盘重播的所有内容。"""
        buffered = self._buffer
        self._buffer = None
        for event in buffered or ():
            seq = self._seq_of(event)
            if seq is not None and through_seq is not None and seq <= through_seq:
                continue  # 重播期间已从磁盘发送
            self._emit(event)


def _to_wire(frame: StreamProgress) -> SessionFrameBase:
    """将一个 SDK 进度帧映射到其信封上。"""
    match frame:
        case StreamStarted():
            return ItemStartedFrame(
                item_id=frame.item_id,
                attempt=frame.attempt,
                anchor_seq=frame.anchor_seq,
            )
        case StreamDelta():
            return DeltaFrame(
                item_id=frame.item_id,
                attempt=frame.attempt,
                order=frame.order,
                kind=frame.kind,
                content=frame.content,
                chunk_id=frame.chunk_id,
                choice_index=frame.choice_index,
            )
        case StreamAborted():
            return ItemAbortedFrame(
                item_id=frame.item_id,
                attempt=frame.attempt,
                reason=frame.reason,
            )


class _ProgressSubscriber(Subscriber[StreamProgress]):
    """将进度直接转发给作者。

    无缓冲，无重播边界：丢帧需要重新绘制，真实文本随持久事件到达。
    """

    def __init__(self, writer: _ConnectionWriter) -> None:
        self._writer = writer

    async def __call__(self, frame: StreamProgress) -> None:
        self._writer.send(_to_wire(frame))


def _read_page(events: EventLog, start: int, stop: int) -> list[tuple[int, Event]]:
    """按索引读取一页，跳过不可读的事件。

    损坏或半写入的文件应该花费一个事件，而不是连接 - 与
    ``EventService._get_searchable_event`` 相同的容忍度。
    """
    page: list[tuple[int, Event]] = []
    for idx in range(start, stop):
        try:
            page.append((idx, events[idx]))
        except (OSError, UnicodeDecodeError, ValidationError, IndexError):
            # 还包括了网络文件系统上的OSError 也覆盖了EventLog 警告的瞬时读取错误。
            #
            logger.warning("session_socket_skipping_unreadable_event: idx=%d", idx)
    return page


async def _replay(
    events: EventLog, start: int, stop: int, writer: _ConnectionWriter
) -> bool:
    """从磁盘发送 ``[start, stop)``，以页为单位，在页之间产生。"""
    loop = asyncio.get_running_loop()
    for page_start in range(start, stop, REPLAY_PAGE_SIZE):
        page_stop = min(page_start + REPLAY_PAGE_SIZE, stop)
        page = await loop.run_in_executor(
            None, _read_page, events, page_start, page_stop
        )
        for seq, event in page:
            if not writer.send(DurableFrame(seq=seq, event=event)):
                return False
            # 帧内，而不是页面内：只有写入任务会消耗剩余字节，而一个大事件页面则可能耗尽
            # 预算并丢弃一个原本从未慢的客户端。
            #
            await asyncio.sleep(0)
    return True


@session_router.websocket("/session/{conversation_id}")
async def session_socket(
    conversation_id: UUID,
    websocket: WebSocket,
    session_api_key: Annotated[str | None, Query(alias="session_api_key")] = None,
    after_seq: Annotated[
        int | None,
        Query(
            description=(
                "Resume cursor: everything with seq > after_seq is sent "
                "before going live. Omit for live-only, -1 for full history. "
                "Replaces the legacy resend_mode/after_timestamp pair, which "
                "compared naive local timestamps."
            )
        ),
    ] = None,
):
    """会话套接字：在一个有序通道上的信封中的持久事件。"""
    if not await _accept_authenticated_websocket(websocket, session_api_key):
        return

    logger.info("session_socket_connected: %s after_seq=%s", conversation_id, after_seq)
    conv_service = _get_conversation_service(websocket)
    try:
        event_service = await conv_service.get_event_service(conversation_id)
    except CredentialBindingActivationRequired:
        await _safe_close_websocket(
            websocket, code=1013, reason="credential_binding_activation_required"
        )
        return
    if event_service is None:
        logger.warning("session_socket_conversation_not_found: %s", conversation_id)
        await _safe_close_websocket(
            websocket, code=4004, reason="Conversation not found"
        )
        return

    try:
        events = event_service.get_conversation().state.events
    except ValueError:
        # 在上面的查找和此处之间关闭。
        logger.warning("session_socket_conversation_inactive: %s", conversation_id)
        await _safe_close_websocket(
            websocket, code=4004, reason="Conversation not found"
        )
        return

    writer = _ConnectionWriter(websocket)
    writer.start()
    subscriber = _SessionSubscriber(writer=writer, events=events)

    # FIRST订阅，然后读取标记：锁不需要，因为订阅之前添加的内容在标记读取之前就已经在磁
    # 盘上，订阅之后添加的内容会缓存并被序列化。
    #
    try:
        subscriber_id = await event_service.subscribe_to_events(subscriber)
    except MaxSubscribersError:
        logger.warning("session_socket_subscriber_limit: %s", conversation_id)
        await writer.aclose()
        await _safe_close_websocket(
            websocket, code=1013, reason="Too many connections for this conversation"
        )
        return
    except Exception:
        # subscribe_to_events 在失败之前注册，并且它在下面的 try/finally 之前着陆，因此
        # 请清理此处的 writer 和 socket。 注册本身无法回收（只有成功时才返回id）； 它是
        # 惰性的，但有一个槽。 属于subscribe_to_events，它与遗留端点有相同的漏洞。
        #
        logger.exception("session_socket_subscribe_failed: %s", conversation_id)
        await writer.aclose()
        await _safe_close_websocket(websocket, code=1011, reason="subscribe_failed")
        return

    progress_id: UUID | None = None
    try:
        try:
            progress_id = await event_service.subscribe_to_stream_progress(
                _ProgressSubscriber(writer)
            )
        except MaxSubscribersError:
            # 持久交付是指客户无法自行恢复的； 失去进度只会损失实时打字效果。
            #
            logger.warning("session_socket_progress_limit: %s", conversation_id)

        length = len(events)
        through_seq = length - 1 if length else None

        if not writer.send(SyncFrame(from_seq=after_seq, through_seq=through_seq)):
            return

        replayed = False
        if after_seq is not None and through_seq is not None:
            start = max(after_seq + 1, 0)
            if not await _replay(events, start, through_seq + 1, writer):
                return
            replayed = True

        # 只有当实际发送了该范围时，才与标记进行去重：一个只读客户端从磁盘上没有得到任何
        # 东西，也没有恢复标记会丢弃的任何内容的游标。
        #
        subscriber.go_live(through_seq if replayed else None)

        await _inbound_loop(conversation_id, websocket, event_service, writer)
    finally:
        if progress_id is not None:
            await event_service.unsubscribe_from_stream_progress(progress_id)
        await event_service.unsubscribe_from_events(subscriber_id)
        await writer.aclose()
        if writer.drop_reason in ("slow_consumer", "frame_too_large"):
            await _safe_close_websocket(websocket, code=1013, reason=writer.drop_reason)
        logger.info(
            "session_socket_closed: %s reason=%s", conversation_id, writer.drop_reason
        )


async def _inbound_loop(
    conversation_id: UUID,
    websocket: WebSocket,
    event_service,
    writer: _ConnectionWriter,
) -> None:
    """读取客户端消息，直到对等方或写入者放弃。

    与失败的作家竞争，或者一个缓慢的消费者将永远坐在这里持有订阅。
    """
    closed_waiter = asyncio.ensure_future(writer.closed_event.wait())
    try:
        while True:
            receiver = asyncio.ensure_future(websocket.receive_json())
            done, _ = await asyncio.wait(
                {receiver, closed_waiter}, return_when=asyncio.FIRST_COMPLETED
            )
            if closed_waiter in done:
                receiver.cancel()
                if receiver in done:
                    # 两者同时完成：cancel() 是对已完成的未来的无操作，因此使用结果或
                    # asyncio 在 GC 上记录“从未检索到任务异常”。
                    #
                    with contextlib.suppress(Exception, asyncio.CancelledError):
                        receiver.result()
                return
            try:
                data = receiver.result()
            except WebSocketDisconnect:
                logger.info("session_socket_disconnected: %s", conversation_id)
                return
            except Exception as e:
                # receive_json 使用 json.loads 进行解码，因此此处会出现非 JSON 帧，而不
                # 是下面的验证。 保持连接，就像传统端点的一个广泛处理程序所做的那样。
                #
                logger.warning(
                    "session_socket_bad_inbound_frame: %s: %s",
                    e.__class__.__name__,
                    e,
                )
                if not writer.send(
                    ErrorFrame(code=e.__class__.__name__, detail=str(e))
                ):
                    return
                continue

            if _is_auth_control_message(data):
                continue

            try:
                message = Message.model_validate(data)
                await event_service.send_message(message, True)
            except WebSocketDisconnect:
                return
            except Exception as e:
                # 关于这个套接字，而不是对话，因此是 ErrorFrame 而不是持久事件 - 并且不
                # 值得放弃。
                #
                logger.exception("session_socket_inbound_error", stack_info=True)
                if not writer.send(
                    ErrorFrame(code=e.__class__.__name__, detail=str(e))
                ):
                    return
    finally:
        closed_waiter.cancel()
