"""fastmcp.Client 之上的最小同步个助手，保留原始行为。"""

import asyncio
import inspect
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any

from fastmcp import Client as AsyncMCPClient

from openhands.sdk.mcp.exceptions import MCPError
from openhands.sdk.utils.async_executor import AsyncExecutor


if TYPE_CHECKING:
    from openhands.sdk.mcp.tool import MCPToolDefinition


ToolsReconciledCallback = Callable[
    ["MCPClient", Sequence["MCPToolDefinition"]],
    None,
]


class MCPClient(AsyncMCPClient):
    """MCP 客户端与同步助手和生命周期管理。

    将 fastmcp.Client 扩展为：
      - call_async_from_sync(awaitable_or_fn, *args, 超时=None, **kwargs)
      - call_sync_from_async(fn, *args, **kwargs) # 从异步代码中等待

    create_mcp_tools() 填充后，用作同步上下文管理器：

        with create_mcp_tools(config) as client:
            for tool in client.tools:
                # 使用工具
        # 连接自动关闭

    或者在完成后调用 sync_close() 手动管理生命周期。
    """

    _executor: AsyncExecutor
    _closed: bool
    _tools: "list[MCPToolDefinition]"
    _tools_reconciled_callback: ToolsReconciledCallback | None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = AsyncExecutor()
        self._closed = False
        self._tools = []
        self._tools_reconciled_callback = None

    @property
    def tools(self) -> "list[MCPToolDefinition]":
        """使用此客户端连接的 MCP 工具（返回副本）。"""
        return list(self._tools)

    async def connect(self) -> None:
        """建立与 MCP 服务器的连接。"""
        async with self._session_state.lock:
            session_task = self._session_state.session_task
            if session_task is not None and session_task.done():
                self._reset_session_state(full=True)
        try:
            await self.__aenter__()
        except RuntimeError as exc:
            raise MCPError("MCP Connection Failure") from exc

    def call_async_from_sync(
        self,
        awaitable_or_fn: Callable[..., Any] | Any,
        *args,
        timeout: float,
        **kwargs,
    ) -> Any:
        """
        从同步代码在此客户端循环上运行协程或异步函数。

        用途：
            mcp.call_async_from_sync(async_fn, arg1, kw=...)
            mcp.call_async_from_sync(coro)
        """
        return self._executor.run_async(
            awaitable_or_fn, *args, timeout=timeout, **kwargs
        )

    async def call_sync_from_async(
        self, fn: Callable[..., Any], *args, **kwargs
    ) -> Any:
        """
        等待从异步代码在默认线程池中运行阻塞函数。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def sync_close(self) -> None:
        """
        同步关闭MCP客户端并清理资源。

        这将尝试调用异步 close() 方法（如果可用），然后关闭后台事件循环。 可以安全地
        多次拨打。
        """
        if self._closed:
            return

        # 尽力而为：如果父级提供，请尝试异步关闭
        if hasattr(self, "close") and inspect.iscoroutinefunction(self.close):
            try:
                self._executor.run_async(self.close, timeout=10.0)
            except Exception:
                pass  # 清理期间忽略关闭错误

        # 始终清理执行器
        self._executor.close()
        self._closed = True

    def __del__(self):
        """删除时清理。"""
        try:
            self.sync_close()
        except Exception:
            pass  # 忽略删除期间的清理错误

    # 同步上下文管理器支持
    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.sync_close()

    # 工具的迭代支持
    def __iter__(self) -> "Iterator[MCPToolDefinition]":
        return iter(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __getitem__(self, index: int) -> "MCPToolDefinition":
        return self._tools[index]
