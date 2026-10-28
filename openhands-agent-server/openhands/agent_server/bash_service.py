import asyncio
import glob
import json
import os
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from openhands.agent_server.models import (
    BashCommand,
    BashEventBase,
    BashEventPage,
    BashEventSortOrder,
    BashOutput,
    ExecuteBashRequest,
)
from openhands.agent_server.pub_sub import PubSub, Subscriber
from openhands.sdk.logger import get_logger
from openhands.sdk.utils import sanitized_env, utc_now


logger = get_logger(__name__)
MAX_CONTENT_CHAR_LENGTH = 1024 * 1024


@dataclass
class BashEventService:
    """用于执行未添加到事件流中的 bash 事件的服务
    智能体将不可见。"""

    bash_events_dir: Path = field()
    default_cwd: str | None = None
    _tasks: set[asyncio.Task] = field(default_factory=set, init=False)
    _closed: bool = field(default=False, init=False)
    # 当前正在运行的命令的进程，以命令 id 为键。 None 个值意味着 spawn 正在等待：
    # start_bash_command 同步注册了 id，因此，如果在子进程之前没有收到停止信号，就会记录
    # 为未丢失，而不是丢失。 允许 stop-by-id 操作发出一个命令信号而不触及其他命令。
    #
    _processes: dict[UUID, asyncio.subprocess.Process | None] = field(
        default_factory=dict, init=False
    )
    # 当它们的生成仍在等待时，ID 被请求停止。
    _stop_requests: set[UUID] = field(default_factory=set, init=False)
    _pub_sub: PubSub[BashEventBase] = field(
        default_factory=lambda: PubSub[BashEventBase](max_subscribers=50),
        init=False,
    )
    # 多个打开的终端选项卡同时轮询 bash 事件。 将每个目录扫描移动到默认线程池子把它隔开
    # 了事件循环但是没有限制并发扫描仍然会占用每个工人，导致其他工人被饿死端点 that use
    # asyncio.to_thread (特别是对话/搜索) 序列化只有昂贵的 bash-event 文件系统工作：排队
    # 的调用者仍然存在异步在只有一个工作进程执行共享目录扫描。1 (完整) 序列化）是一个有
    # 意的严格限制：单次扫描成本很低（在100k文件上大约0.2秒），因此即使只重叠几次扫描也
    # 节省了很少的壁时，但在大规模情况下，可能会为了微小的轮询延迟而垄断共享工作池。 排
    # 队的调用者仍然异步进行。
    #
    _filesystem_search_semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(1),
        init=False,
        repr=False,
    )

    def _ensure_bash_events_dir(self) -> None:
        """确保 bash 事件目录存在。"""
        self.bash_events_dir.mkdir(parents=True, exist_ok=True)

    def _timestamp_to_str(self, timestamp: datetime) -> str:
        # 包括微秒，以便基于文件名的排序反映亚秒突发的发射顺序 (e.g. 快速 `yes` 式洪水，
        # 在同一挂钟秒内发出多个 BashOutput 块）。 文件名保存 UTC 次，因此转换感知日期时
        # 间 (e.g. a
        # ``+02:00`` 搜索范围）到 UTC 首先； 朴素的被视为UTC。
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(UTC)
        return timestamp.strftime("%Y%m%d%H%M%S%f")

    def _get_event_filename(self, event: BashEventBase) -> str:
        """使用 YYYYMMDDHHMMSSffffff_eventId_actionId 格式生成文件名。"""
        result = [self._timestamp_to_str(event.timestamp), event.kind]
        command_id = getattr(event, "command_id", None)
        if command_id:
            result.append(command_id.hex)
        result.append(event.id.hex)
        return "_".join(result)

    def _save_event_to_file(self, event: BashEventBase) -> None:
        """将事件保存到文件中。"""
        self._ensure_bash_events_dir()
        filename = self._get_event_filename(event)
        filepath = self.bash_events_dir / filename

        with open(filepath, "w") as f:
            # 使用 model_dump 和 mode='JSON' 来处理 UUID 序列化
            data = event.model_dump(mode="json")
            f.write(json.dumps(data, indent=2))

    def _load_event_from_file(self, filepath: Path) -> BashEventBase | None:
        """从文件加载事件。"""
        try:
            json_data = filepath.read_text()
            return BashEventBase.model_validate_json(json_data)
        except Exception as e:
            logger.error(f"Error loading event from {filepath}: {e}")
            return None

    def _get_event_files_by_pattern(self, pattern: str) -> list[Path]:
        """获取与全局模式匹配的事件文件，按时间戳排序。"""
        self._ensure_bash_events_dir()
        files = glob.glob(str(self.bash_events_dir / pattern))
        return sorted([Path(f) for f in files])

    async def get_bash_event(self, event_id: str) -> BashEventBase | None:
        """获取具有给定 id 的事件，如果没有此类事件，则获取 None。"""
        async with self._filesystem_search_semaphore:
            return await asyncio.to_thread(self._get_bash_event_sync, event_id)

    def _get_bash_event_sync(self, event_id: str) -> BashEventBase | None:
        """Sync: 查找名称以 ``_<event_id>`` 结尾的事件文件。

        在单个 ``os.scandir`` 传递中扫描事件目录（一个 readdir，没有每个条目的统计信
        息或正则表达式）并返回第一个匹配的文件。
        """
        self._ensure_bash_events_dir()
        suffix = f"_{event_id}"
        with os.scandir(self.bash_events_dir) as it:
            for entry in it:
                if entry.name.endswith(suffix):
                    return self._load_event_from_file(Path(entry.path))
        return None

    async def batch_get_bash_events(
        self, event_ids: list[str]
    ) -> list[BashEventBase | None]:
        """给定一个 id 列表，获取 bash 事件（或者 None 表示任何
        未找到）"""
        results = await asyncio.gather(
            *[self.get_bash_event(event_id) for event_id in event_ids]
        )
        return results

    async def search_bash_events(
        self,
        kind__eq: str | None = None,
        command_id__eq: UUID | None = None,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
        order__gt: int | None = None,
        sort_order: BashEventSortOrder = BashEventSortOrder.TIMESTAMP,
        page_id: str | None = None,
        limit: int = 100,
    ) -> BashEventPage:
        """搜索事件。 如果给出 command_id，则仅观测结果为
        操作被返回。

        目录扫描、排序、过滤和文件读取都是阻塞式I/O，因此整个搜索在工作线程线程 (
        ``asyncio.to_thread``) 中使用 asyncio 事件循环
        来避免阻塞并发的请求。
        """
        async with self._filesystem_search_semaphore:
            return await asyncio.to_thread(
                self._search_bash_events_sync,
                kind__eq,
                command_id__eq,
                timestamp__gte,
                timestamp__lt,
                order__gt,
                sort_order,
                page_id,
                limit,
            )

    def _search_bash_events_sync(
        self,
        kind__eq: str | None,
        command_id__eq: UUID | None,
        timestamp__gte: datetime | None,
        timestamp__lt: datetime | None,
        order__gt: int | None,
        sort_order: BashEventSortOrder,
        page_id: str | None,
        limit: int,
    ) -> BashEventPage:
        """同步搜索：一``os.scandir``通+廉价段过滤器。

        在 ``_`` 上分割每个文件名并直接比较固定段（种类，command_id），而不是与正则表
        达式匹配。 文件名是以20位时间戳前缀的
        ``<timestamp>_<kind>[_<command_id>]_<event_id>``，因此，字典序比较实际上是时
        间戳比较，用于过滤时间窗口和排序
        。
        """
        self._ensure_bash_events_dir()
        gte_str = self._timestamp_to_str(timestamp__gte) if timestamp__gte else None
        lt_str = self._timestamp_to_str(timestamp__lt) if timestamp__lt else None
        kind_filter = kind__eq
        cmd_filter = command_id__eq.hex if command_id__eq else None
        reverse = sort_order == BashEventSortOrder.TIMESTAMP_DESC

        matched: list[str] = []
        with os.scandir(self.bash_events_dir) as it:
            for entry in it:
                name = entry.name
                # 时间戳前缀过滤器：文件名按时间戳字典序排序，因此对整个名称的字符串比较
                # 可以限制时间窗口，而无需解析时间戳。
                #
                if gte_str is not None and name < gte_str:
                    continue
                if lt_str is not None and name >= lt_str:
                    continue
                # 分段过滤器：[时间戳、种类、(command_id)、event_id]。 比 fnmatch 便宜并
                # 且避免匹配不相关的文件。
                #
                if kind_filter is not None or cmd_filter is not None:
                    parts = name.split("_")
                    if kind_filter is not None:
                        if len(parts) < 2 or parts[1] != kind_filter:
                            continue
                    if cmd_filter is not None:
                        # 只有 BashOutput（4 个段）带有 command_id。
                        if len(parts) < 4 or parts[2] != cmd_filter:
                            continue
                matched.append(name)

        matched.sort(reverse=reverse)

        # 将 page_id 解析为起始索引。
        start_index = 0
        if page_id:
            for i, name in enumerate(matched):
                if name == page_id:
                    start_index = i
                    break

        # 在计数到 ``limit`` 之前过滤：首先切片文件名
        # ``order__gt`` 清空一页，而 ``next_page_id`` 仍处于设置状态。 光标是通过过滤器
        # 的下一个事件，因此页面后面永远不会是空页面。
        #
        page_events: list[BashEventBase] = []
        next_page_id = None
        for name in matched[start_index:]:
            event = self._load_event_from_file(self.bash_events_dir / name)
            if event is None:
                continue
            # 如果指定，则按顺序过滤（仅适用于 BashOutput 个事件）
            if order__gt is not None:
                event_order = getattr(event, "order", None)
                if event_order is not None and event_order <= order__gt:
                    continue
            if len(page_events) >= limit:
                next_page_id = name
                break
            page_events.append(event)

        return BashEventPage(items=page_events, next_page_id=next_page_id)

    def _signal_process_group(
        self,
        process: asyncio.subprocess.Process,
        sig: signal.Signals,
    ) -> None:
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except ProcessLookupError:
            pass
        except OSError as e:
            logger.debug(
                "Failed to send %s to process group (error_type=%s)",
                sig.name,
                type(e).__name__,
            )

    async def start_bash_command(
        self, request: ExecuteBashRequest
    ) -> tuple[BashCommand, asyncio.Task]:
        """执行 bash 命令。 输出结果将单独发布。"""
        if self._closed:
            raise RuntimeError("Bash event service is closed")
        cwd = request.cwd or self.default_cwd
        command = BashCommand(**{**request.model_dump(), "cwd": cwd})
        self._save_event_to_file(command)
        await self._pub_sub(command)

        # 同步注册，以便记录停止比赛的生成而不是丢失； 该任务将 None 替换为实时进程。
        #
        self._processes[command.id] = None
        # 在后台任务中执行 bash 命令
        task = asyncio.create_task(self._execute_bash_command(command))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return command, task

    async def _execute_bash_command(self, command: BashCommand) -> None:
        """执行 bash 事件并创建一个观测结果事件。"""
        try:
            # 在新会话中创建子进程，以便我们可以在拆卸时向整个进程组发出信号（shell 的子
            # 进程，e.g。 sleep，必须在 shell 运行用户安装的陷阱之前死亡）。
            #
            process = await asyncio.create_subprocess_shell(
                command.command,
                cwd=command.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True,
                env=sanitized_env(),
                start_new_session=True,
            )
            self._processes[command.id] = process
            if command.id in self._stop_requests:
                # 在生成完成之前到达停止：立即应用它，而不是让命令运行到其超时。
                #
                self._stop_requests.discard(command.id)
                await self.stop_bash_command(command.id)

            # 跟踪输出顺序和缓冲区
            output_order = 0
            stdout_buffer = ""
            stderr_buffer = ""

            async def read_stream(stream, is_stderr=False):
                nonlocal output_order, stdout_buffer, stderr_buffer

                buffer = stderr_buffer if is_stderr else stdout_buffer

                while True:
                    try:
                        # 从流中读取数据
                        data = await stream.read(8192)  # 分块读取
                        if not data:
                            break

                        text = data.decode("utf-8", errors="replace")
                        buffer += text

                        # 更新适当的缓冲区
                        if is_stderr:
                            stderr_buffer = buffer
                        else:
                            stdout_buffer = buffer

                        # 检查我们是否需要分割输出
                        while len(buffer) > MAX_CONTENT_CHAR_LENGTH:
                            # 以最大长度分割
                            chunk = buffer[:MAX_CONTENT_CHAR_LENGTH]
                            buffer = buffer[MAX_CONTENT_CHAR_LENGTH:]

                            # 创建并发布 BashOutput 事件
                            output_event = BashOutput(
                                command_id=command.id,
                                order=output_order,
                                stdout=chunk if not is_stderr else None,
                                stderr=chunk if is_stderr else None,
                            )

                            self._save_event_to_file(output_event)
                            await self._pub_sub(output_event)
                            output_order += 1

                            # 更新适当的缓冲区
                            if is_stderr:
                                stderr_buffer = buffer
                            else:
                                stdout_buffer = buffer

                    except Exception as e:
                        logger.error(f"Error reading from stream: {e}")
                        break

            # 使用超时执行整个命令
            try:
                # 与超时同时运行流读取和进程等待
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, is_stderr=False),
                        read_stream(process.stderr, is_stderr=True),
                        process.wait(),
                        return_exceptions=True,
                    ),
                    timeout=command.timeout,
                )
                exit_code = process.returncode
            except asyncio.CancelledError:
                self._signal_process_group(process, signal.SIGKILL)
                await process.wait()
                raise
            except TimeoutError:
                # 将 SIGTERM 发送到整个进程组，以便用户安装的清理陷阱可以运行，然后根据
                # 需要升级到 SIGKILL。
                #
                self._signal_process_group(process, signal.SIGTERM)
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except TimeoutError:
                    self._signal_process_group(process, signal.SIGKILL)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except TimeoutError:
                        logger.error(
                            "Failed to kill process (command_id=%s)", command.id
                        )
                exit_code = -1
                logger.warning(
                    "Command timed out after %s seconds (command_id=%s)",
                    command.timeout,
                    command.id,
                )

            # 使用任何剩余的缓冲区内容和退出代码创建最终输出事件
            final_stdout = stdout_buffer if stdout_buffer else None
            final_stderr = stderr_buffer if stderr_buffer else None

            # 仅当有剩余内容或我们需要报告退出代码时才创建最终事件
            #
            if final_stdout or final_stderr or exit_code is not None:
                final_output = BashOutput(
                    command_id=command.id,
                    order=output_order,
                    exit_code=exit_code,
                    stdout=final_stdout,
                    stderr=final_stderr,
                )

                self._save_event_to_file(final_output)
                await self._pub_sub(final_output)

        except Exception as e:
            logger.error(
                "Error executing bash command (command_id=%s, error_type=%s)",
                command.id,
                type(e).__name__,
            )
            # 创建错误输出事件
            error_output = BashOutput(
                command_id=command.id,
                order=0,
                exit_code=-1,
                stderr=f"Error executing command: {str(e)}",
            )

            self._save_event_to_file(error_output)
            await self._pub_sub(error_output)
        finally:
            self._processes.pop(command.id, None)
            self._stop_requests.discard(command.id)

    async def stop_bash_command(self, command_id: UUID) -> bool:
        """通过命令 ID 停止正在运行的命令的进程组。

        重用超时路径的 SIGTERM-then-SIGKILL 升级，以便运行用户安装的清理陷阱。 该命令
        自己的任务观察退出并发布终端输出，因此这里只需要信令。

        一旦子进程存在，就会记录并应用停止竞赛生成。 当 id 已知时（现在发出信号、已经
        完成或为待生成的记录进行记录），返回 True。 仅对于未知 id 返回
        False； 调用者将已知但已完成的 id 映射到 success，将未知 id 映射到 not-found
        。
        """
        if command_id not in self._processes:
            return False
        process = self._processes[command_id]
        if process is None:
            self._stop_requests.add(command_id)
            return True
        self._signal_process_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            self._signal_process_group(process, signal.SIGKILL)
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except TimeoutError:
                logger.error("Failed to stop process (command_id=%s)", command_id)
        return True

    def delete_events_older_than(self, cutoff: datetime) -> int:
        """删除记录时间戳早于 ``cutoff`` 的 bash 事件文件。

        这是一个同步方法 — 所有操作都会阻塞文件系统 I/O。 asyncio 事件循环上的调用者
        应该使用
        ``await asyncio.to_thread(service.delete_events_older_than, cutoff)`` 以避免
        循环停止。

        文件名在升序排序中以 ``YYYYMMDDHHMMSS`` 开头，因此扫描会停止，当达到或超过截
        止点的文件时。

        Returns:
            int: 已删除的事件文件的数量。
        """
        cutoff_str = self._timestamp_to_str(cutoff)
        files = self._get_event_files_by_pattern("*")  # 按时间升序
        count = 0
        for path in files:
            if path.name >= cutoff_str:
                break  # 剩余文件等于或更新于截止时间
            try:
                path.unlink(missing_ok=True)
                count += 1
            except Exception as e:
                logger.warning("Failed to delete bash event file %s: %s", path, e)
        if count:
            logger.info(
                "Deleted %d bash event file(s) older than %s", count, cutoff_str
            )
        return count

    async def run_retention_cleanup_loop(
        self,
        retention_seconds: int,
        interval_seconds: float | None = None,
    ) -> None:
        """定期清除早于 ``retention_seconds`` 的 bash 事件文件。

        运行直至取消 (e.g. 在应用程序关闭期间）。 清理运行立即在启动时进行，这样就可
        以在服务器重启后立即清除累积的文件，而无需等待第一个间隔到期。

        阻塞文件系统工作通过以下方式分派到线程
        ``asyncio.to_thread`` 保持事件循环空闲。

        Args:
            retention_seconds: 年龄阈值（以秒为单位）； 较旧的文件被删除。
            interval_seconds: 运行清理的频率。 默认为
                ``max(60, retention_seconds / 2)``. 在测试中传递较小的值以避免长时间
                等待。
        """
        interval = (
            interval_seconds
            if interval_seconds is not None
            else max(60.0, retention_seconds / 2)
        )
        while True:
            try:
                cutoff = utc_now() - timedelta(seconds=retention_seconds)
                await asyncio.to_thread(self.delete_events_older_than, cutoff)
            except Exception as e:
                logger.warning("Bash events retention cleanup error: %s", e)
                # 如果故障持续存在，则短暂回退以防止日志泛滥 (e.g. 权限错误，磁盘已满）
                # 。 按正常间隔设置上限，这样我们就不会在低保留配置中过度延迟。
                #
                await asyncio.sleep(min(interval, 60.0))
            # 始终在错误回退后休眠整个间隔，因此总等待错误 = min(interval, 60) + 间隔 ≈
            # 2× 正常节奏。
            #
            await asyncio.sleep(interval)

    async def subscribe_to_events(self, subscriber: Subscriber[BashEventBase]) -> UUID:
        """订阅 bash 事件。

        订阅者将收到 BashEventBase 个实例。
        """
        return self._pub_sub.subscribe(subscriber)

    async def unsubscribe_from_events(self, subscriber_id: UUID) -> bool:
        return self._pub_sub.unsubscribe(subscriber_id)

    async def clear_all_events(self) -> int:
        """从存储中清除所有 bash 事件。

        Returns:
            int: 已清除的事件数。
        """
        self._ensure_bash_events_dir()

        # 获取所有事件文件
        files = self._get_event_files_by_pattern("*")

        # 删除前对文件进行计数
        count = len(files)

        # 删除所有事件文件
        for file_path in files:
            try:
                file_path.unlink()
            except Exception as e:
                logger.error(f"Error deleting event file {file_path}: {e}")

        logger.info(f"Cleared {count} bash events from storage")
        return count

    async def close(self):
        """关闭bash事件服务并清理资源。"""
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._processes.clear()
        self._stop_requests.clear()
        await self._pub_sub.close()

    async def __aenter__(self):
        """开始使用此任务服务"""
        # bash 事件服务不需要特殊的初始化
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """完成使用此任务服务"""
        await self.close()


_bash_event_service: BashEventService | None = None


def get_default_bash_event_service() -> BashEventService:
    """获取默认的 bash 事件服务实例。"""
    global _bash_event_service
    if _bash_event_service:
        return _bash_event_service

    from openhands.agent_server.config import get_default_config

    config = get_default_config()
    _bash_event_service = BashEventService(bash_events_dir=config.bash_events_dir)
    return _bash_event_service
