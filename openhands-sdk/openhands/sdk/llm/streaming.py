import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from litellm.types.utils import ModelResponseStream


# 流块的类型别名
LLMStreamChunk = ModelResponseStream

TokenCallbackType = Callable[[LLMStreamChunk], None]
AsyncTokenCallbackType = Callable[[LLMStreamChunk], Coroutine[Any, Any, None]]

# 对于异步方法，接受同步或异步 token 回调。
AnyTokenCallbackType = TokenCallbackType | AsyncTokenCallbackType


async def _invoke_token_callback(
    cb: AnyTokenCallbackType, chunk: LLMStreamChunk
) -> None:
    """调用 token 回调，等待它是否返回协程。

    处理普通协程函数 ** 和 ``__call__`` 为异步的 ** 可调用对象（
    ``asyncio.iscoroutinefunction`` 不检测后者）。
    """
    result = cb(chunk)  # type: ignore[arg-type]
    if asyncio.iscoroutine(result):
        await result
