"""稳定 DTOs ACP 会话模型元数据。

它们存在于独立模块中 - *而不是* ``acp_agent`` - 因此智能体服务器可以为其公共
``ConversationInfo`` 模式导入它们，而无需导入
``ACPAgent``，它会急切地将其注册到智能体中
``DiscriminatedUnion``（参见``openhands/sdk/agent/__init__.py``）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


@runtime_checkable
class _ModelInfoWithModelId(Protocol):
    model_id: str


@runtime_checkable
class _ModelInfoWithValue(Protocol):
    value: str


@runtime_checkable
class _ModelInfoWithName(Protocol):
    name: str | None


@runtime_checkable
class _ModelInfoWithDescription(Protocol):
    description: str | None


class ACPModelInfo(BaseModel):
    """ACP 服务器为会话提供的一种模型。

    ACP 协议 ``ModelInfo`` 的标准化、稳定的镜像。 ``models`` 协议 **UNSTABLE** 标记，
    因此我们将其映射到我们的类型，在
    SDK 边界而不是将 ``acp.schema`` 供应商的类型重新序列化到智能体服务器的公共 API ——
     客户端无论上游协议变化都能获得稳定形状。

    携带客户端渲染选择器和解析问题所需的一切
    ``current_model_id`` 到显示标签 * 本身 *； SDK 故意没有命名。
    """

    # ``model_id`` 与 Pydantic 受保护的 ``model_`` 命名空间发生冲突； 选择退出（名称反映
    # 了协议字段和已持久化形状）。
    #
    model_config = ConfigDict(protected_namespaces=())

    model_id: str = Field(
        description=(
            "Server-assigned model identifier. May be concrete "
            '(e.g. ``"gpt-5.6"``) or an opaque alias '
            '(e.g. ``"default"``, ``"auto"``). This is the value to pass back '
            "to the server to switch to this model."
        ),
    )
    name: str | None = Field(
        default=None,
        description='Human-readable label, e.g. ``"GPT-5.5"``.',
    )
    description: str | None = Field(
        default=None,
        description="Optional longer description supplied by the server.",
    )

    @classmethod
    def from_protocol(cls, raw: Any, *, id_attr: str = "model_id") -> ACPModelInfo:
        """从原始的 ACP ``ModelInfo`` （或任何鸭子类型的对象）构建。

        容忍部分/格式错误的条目：非字符串字段降级为
        ``""`` 或 ``model_id``，或者 ``None`` 或 ``name``/``description``) 而不是抛出
        异常，因为源协议能力是
         UNSTABLE 协议能力，而较旧或半实现的智能体可能会发出不完全。

        ``id_attr`` 命名携带模型 id 的属性 — ``"model_id"`` 表示 ``models``-能力
        ``ModelInfo``，
        ``"value"`` 表示
        ``configOptions`` 选择选项。
        """
        if isinstance(raw, ACPModelInfo):
            if id_attr == "model_id":
                return raw
            return cls(
                model_id=raw.model_id,
                name=raw.name,
                description=raw.description,
            )

        model_id = None
        name = None
        description = None

        if isinstance(raw, Mapping):
            model_id = raw.get(id_attr)
            name = raw.get("name")
            description = raw.get("description")
        else:
            if id_attr == "model_id" and isinstance(raw, _ModelInfoWithModelId):
                model_id = raw.model_id
            elif id_attr == "value" and isinstance(raw, _ModelInfoWithValue):
                model_id = raw.value
            elif isinstance(raw, _ModelInfoWithModelId):
                model_id = raw.model_id
            elif isinstance(raw, _ModelInfoWithValue):
                model_id = raw.value

            if isinstance(raw, _ModelInfoWithName):
                name = raw.name
            if isinstance(raw, _ModelInfoWithDescription):
                description = raw.description

        return cls(
            model_id=model_id if isinstance(model_id, str) else "",
            name=name if isinstance(name, str) else None,
            description=description if isinstance(description, str) else None,
        )


class ACPModelDiscoveryError(BaseModel):
    """为什么 ACP 服务器无法报告其型号。"""

    code: str = Field(
        description=(
            "Same codes as a conversation's cold-start ``ConversationErrorEvent``: "
            "``ACPAuthRequired``, ``ACPStartupTimeout``, ``ACPSpawnError`` or "
            "``ACPInitError``."
        ),
    )
    detail: str = Field(description="Human-readable, secret-free cause.")


class ACPModelDiscovery(BaseModel):
    """在任何对话之前，ACP 服务器报告新会话的内容。"""

    model_config = ConfigDict(protected_namespaces=())

    agent_name: str | None = Field(
        default=None, description="Server name from ``initialize``."
    )
    agent_version: str | None = Field(
        default=None, description="Server version from ``initialize``."
    )
    current_model_id: str | None = Field(
        default=None,
        description=(
            "Model the server picks when none is requested — its own default "
            "for the given credentials. May be an opaque alias such as "
            '``"default"``; match it against ``available_models`` for a label.'
        ),
    )
    available_models: list[ACPModelInfo] = Field(
        default_factory=list,
        description=(
            "Models the server offers for the given credentials. Empty when the "
            "server does not report any."
        ),
    )
    supports_runtime_model_switch: bool = Field(
        default=False,
        description="Whether a conversation can switch among these models live.",
    )
    error: ACPModelDiscoveryError | None = Field(
        default=None,
        description="Set when the server could not start a session.",
    )
