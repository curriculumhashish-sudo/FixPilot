# rolling_view.py
import logging
import sys
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager

from rich.live import Live

from .logger import ENV_JSON, IN_CI


RenderFnType = Callable[[], str]


class _RollingViewHandler(logging.Handler):
    def __init__(self, max_lines: int, use_live: bool):
        super().__init__()
        self._buf: deque[str] = deque(maxlen=max_lines)
        self._use_live: bool = use_live
        self._live: Live | None = None  # 当 Live 处于活动状态时设置为 rolling_log_view
        self.render_fn: RenderFnType | None = None

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self._buf.append(msg)

        if self._use_live and self._live:
            # 实时模式：使用自定义 render_fn 或缓冲区重新绘制
            self._live.update(
                self.render_fn() if self.render_fn else "\n".join(self._buf)
            )
            return

        # 非活动路径
        if ENV_JSON:
            # JSON模式：此处不执行任何操作； 通过传播依赖其他处理程序
            return

        # CI/非TTY普通传递（避免双换行符）
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()

    @property
    def snapshot(self) -> str:
        return "\n".join(self._buf)


@contextmanager
def rolling_log_view(
    logger: logging.Logger,
    max_lines: int = 60,
    level: int = logging.INFO,
    propagate: bool = False,
    header: str | None = None,
    footer: str | None = None,
    *,
    json_flush_level: int | None = None,  # 可选：最终 JSON 冲洗的单独级别
):
    """
    临时附加一个滚动视图处理程序，用于呈现最后 N 条日志行。

    - 本地 TTY 且非 CI 且非 JSON：漂亮的实时更新视图 (Rich.Live)
    - CI/非TTY：逐行普通（无终端控制）
    - JSON模式：仅缓冲； 退出时发出一个大日志记录和完整快照。
    """
    is_tty = sys.stdout.isatty()
    use_live = (not IN_CI) and is_tty and (not ENV_JSON)

    handler = _RollingViewHandler(max_lines=max_lines, use_live=use_live)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    prev_propagate = logger.propagate
    # 如果需要，让其他处理程序（e.g.，您的 JSON 处理程序）运行
    logger.propagate = bool(propagate or ENV_JSON)

    logger.addHandler(handler)

    def _render() -> str:
        parts: list[str] = []
        if header:
            parts.append(header.rstrip())
        parts.append("\n".join(handler._buf))
        if footer:
            parts.append(footer.rstrip())
        return "\n".join(parts)

    try:
        if use_live:
            with Live(_render(), refresh_per_second=8) as live:
                handler._live = live
                handler.render_fn = _render
                yield handler
        else:
            yield handler
    finally:
        final_text = _render()

        # 如果 Live 处于活动状态，则冻结最后一帧
        if handler._live:
            handler._live.update(final_text)

        # 分离我们的处理程序之前刷新以避免递归
        logger.removeHandler(handler)
        logger.propagate = prev_propagate

        # JSON模式：退出时发出一大条记录
        if ENV_JSON:
            logger.log(
                json_flush_level if json_flush_level is not None else level, final_text
            )
