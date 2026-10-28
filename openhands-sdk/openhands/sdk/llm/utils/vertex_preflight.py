"""预检检查 Vertex AI 合作伙伴模型依赖性。

`google-cloud-aiplatform` 是可选的附加项 (`openhands-sdk[vertex]`)。 当调用者以没有安
装额外的
`vertex_ai/*` 模型为目标时，LiteLLM 会失败，并从其提供程序处理程序内部返回低级别
`ModuleNotFoundError`。 我们更早地发现了这一点
，并提供了一个友好的安装提示。
"""

from __future__ import annotations

import importlib.util

from openhands.sdk.llm.exceptions import LLMBadRequestError


_INSTALL_HINT = (
    "Vertex AI partner models require the Vertex SDK. "
    'Install with: pip install "openhands-sdk[vertex]"'
)


def _vertex_sdk_available() -> bool:
    return importlib.util.find_spec("vertexai") is not None


def assert_vertex_sdk_available(provider: str | None) -> None:
    """如果调用者的目标是没有 SDK 的 Vertex，则会引发友好错误。

    对于任何非 `vertex_ai` 提供者均无操作，因此无条件调用是安全的
    from the transport path.
    """
    if provider != "vertex_ai":
        return
    if _vertex_sdk_available():
        return
    raise LLMBadRequestError(_INSTALL_HINT)
