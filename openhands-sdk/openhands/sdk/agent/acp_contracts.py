"""输入 ACP 功能和会话合同。

定义了显式类型模型、协议和边界标准化辅助工具，用于ACP对象（会话响应选项、模型选择、
MCP能力、协议错误、凭据修订和序列化）。

所有动态属性探测（用于后/前协议版本兼容性和UNSTABLE扩展）仅限于本模块中的规范化边界函
数。 ACPAgent 下游代码及其辅助代码严格通过直接属性访问与类型数据类和
协议交互。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from openhands.sdk.agent.acp_models import ACPModelInfo


_MODEL_CONFIG_OPTION_ID = "model"


# ---------------------------------------------------------------------------
# 认证方法合约
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPAuthMethodProtocol(Protocol):
    """ACP 服务器返回的身份验证方法的协议。"""

    id: str


@runtime_checkable
class ACPAuthMethodWithTypeProtocol(Protocol):
    """指定登录类型的身份验证方法的协议 (e.g. 终端）。"""

    id: str
    type: str | None


@dataclass(frozen=True)
class ACPAuthMethod:
    """标准化 ACP 身份验证方法描述符。"""

    id: str
    type: str | None = None


def normalize_auth_method(raw: Any) -> ACPAuthMethod:
    """在外部库边界标准化 raw ACP auth 方法。"""
    if isinstance(raw, ACPAuthMethod):
        return raw
    if isinstance(raw, Mapping):
        return ACPAuthMethod(
            id=str(raw.get("id", "")),
            type=raw.get("type") if isinstance(raw.get("type"), str) else None,
        )
    if isinstance(raw, ACPAuthMethodWithTypeProtocol):
        return ACPAuthMethod(
            id=str(raw.id),
            type=raw.type if isinstance(raw.type, str) else None,
        )
    if isinstance(raw, ACPAuthMethodProtocol):
        return ACPAuthMethod(id=str(raw.id), type=None)
    return ACPAuthMethod(id="", type=None)


# ---------------------------------------------------------------------------
# 模型和会话配置选项合约
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPConfigOptionBasicProtocol(Protocol):
    """任何 ACP 配置选项的最小协议。"""

    id: str
    type: str


@runtime_checkable
class ACPConfigOptionValueProtocol(Protocol):
    """携带当前选择的选项的协议。"""

    current_value: str | None


@runtime_checkable
class ACPConfigOptionOptionsProtocol(Protocol):
    """用于携带可用选项的选择选项的协议。"""

    options: list[Any]


@runtime_checkable
class ACPRootModelProtocol(Protocol):
    """Pydantic RootModel 包装选项的协议 (智能体-client-protocol 0.8.x)。"""

    root: Any


@runtime_checkable
class ACPSessionConfigOptionsResponseProtocol(Protocol):
    """公开配置选项的会话响应协议。"""

    config_options: list[Any] | None


@runtime_checkable
class ACPCurrentModelIdProtocol(Protocol):
    """带有 current_model_id 属性的对象的协议。"""

    current_model_id: str | None


@runtime_checkable
class ACPAvailableModelsProtocol(Protocol):
    """携带 available_models 列表的对象的协议。"""

    available_models: list[Any] | None


@runtime_checkable
class ACPSessionModelsResponseProtocol(Protocol):
    """公开 UNSTABLE 模型块的会话响应协议。"""

    models: Any | None


class ACPLegacyModelInfo(BaseModel):
    """服务器发送时，UNSTABLE ``models`` 块的一项。"""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    model_id: str = Field(alias="modelId")
    name: str | None = None
    description: str | None = None


class ACPLegacySessionModels(BaseModel):
    """UNSTABLE ``models`` 块，ACP 0.12 模式不再对其建模。"""

    model_config = ConfigDict(populate_by_name=True)

    current_model_id: str | None = Field(default=None, alias="currentModelId")
    available_models: list[ACPLegacyModelInfo] = Field(
        default_factory=list, alias="availableModels"
    )


@runtime_checkable
class ACPLegacyModelSwitchConnection(Protocol):
    """支持传统 set_session_model RPC 的连接协议。"""

    async def set_session_model(self, *, model_id: str, session_id: str) -> Any: ...


def supports_legacy_model_switch(conn: Any) -> bool:
    """如果 conn 支持旧版 set_session_model RPC，则返回 True。"""
    return isinstance(conn, ACPLegacyModelSwitchConnection) or hasattr(
        conn, "set_session_model"
    )


@dataclass(frozen=True)
class ACPConfigSelectOption:
    """从会话响应中标准化配置选择选项。"""

    id: str
    type: str
    current_value: str | None = None
    options: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ACPSessionModelState:
    """从边界处的会话响应中提取的模型状态。"""

    current_model_id: str | None
    available_models: list[ACPModelInfo] | None
    via_config_option: bool


def extract_model_config_option(response: Any) -> ACPConfigSelectOption | None:
    """从边界处的会话响应中提取模型选择选项。

    跨智能体-client-protocol 0.8.x（RootModel 包装）和 0.10.x+（直接联合成员）以及字
    典载荷进行规范化。
    """
    if response is None:
        return None

    raw_options: list[Any] | None = None
    if isinstance(response, ACPSessionConfigOptionsResponseProtocol):
        raw_options = response.config_options
    elif isinstance(response, Mapping):
        raw_options = response.get("config_options")

    if not raw_options:
        return None

    for raw in raw_options:
        opt = raw.root if isinstance(raw, ACPRootModelProtocol) else raw
        if isinstance(opt, Mapping):
            opt_type = opt.get("type")
            opt_id = opt.get("id")
            if opt_type == "select" and opt_id == _MODEL_CONFIG_OPTION_ID:
                val = opt.get("current_value")
                opts = opt.get("options")
                return ACPConfigSelectOption(
                    id=str(opt_id),
                    type=str(opt_type),
                    current_value=val if isinstance(val, str) else None,
                    options=list(opts) if isinstance(opts, (list, tuple)) else [],
                )
        elif isinstance(opt, ACPConfigOptionBasicProtocol):
            if opt.type == "select" and opt.id == _MODEL_CONFIG_OPTION_ID:
                val = (
                    opt.current_value
                    if isinstance(opt, ACPConfigOptionValueProtocol)
                    else None
                )
                opts = (
                    opt.options
                    if isinstance(opt, ACPConfigOptionOptionsProtocol)
                    else []
                )
                return ACPConfigSelectOption(
                    id=str(opt.id),
                    type=str(opt.type),
                    current_value=val if isinstance(val, str) else None,
                    options=list(opts) if isinstance(opts, (list, tuple)) else [],
                )
    return None


def extract_session_models(
    response: Any,
    *,
    default_via_config_option: bool = False,
) -> ACPSessionModelState:
    """将会话响应中的模型状态提取到类型化合约中。

    处理较新的 ``configOptions`` 模型选择机制和 UNSTABLE 旧 ``models`` 块，返回：
    class:
    `ACPSessionModelState`。
    """
    if response is None:
        return ACPSessionModelState(
            current_model_id=None,
            available_models=None,
            via_config_option=default_via_config_option,
        )

    # 1. 偏好 configOptions
    opt = extract_model_config_option(response)
    if opt is not None:
        current = opt.current_value
        current = current if isinstance(current, str) and current else None
        usable = [
            info
            for o in opt.options
            if (info := ACPModelInfo.from_protocol(o, id_attr="value")).model_id
        ]
        return ACPSessionModelState(
            current_model_id=current,
            available_models=usable,
            via_config_option=True,
        )

    # 2. 回退到旧模型功能
    models_block = None
    if isinstance(response, ACPSessionModelsResponseProtocol):
        models_block = response.models
    elif isinstance(response, Mapping):
        models_block = response.get("models")

    if models_block is not None:
        current = None
        raw_list: list[Any] = []
        if isinstance(models_block, Mapping):
            current = models_block.get("current_model_id")
            raw_val = models_block.get("available_models")
            if isinstance(raw_val, (list, tuple)):
                raw_list = list(raw_val)
        else:
            if isinstance(models_block, ACPCurrentModelIdProtocol):
                current = models_block.current_model_id
            if isinstance(models_block, ACPAvailableModelsProtocol):
                raw_val = models_block.available_models
                if isinstance(raw_val, (list, tuple)):
                    raw_list = list(raw_val)

        current = current if isinstance(current, str) and current else None
        usable = [
            info for m in raw_list if (info := ACPModelInfo.from_protocol(m)).model_id
        ]
        return ACPSessionModelState(
            current_model_id=current,
            available_models=usable,
            via_config_option=False,
        )

    return ACPSessionModelState(
        current_model_id=None,
        available_models=None,
        via_config_option=default_via_config_option,
    )


# ---------------------------------------------------------------------------
# MCP 能力合同
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPMcpHttpCapabilityProtocol(Protocol):
    """MCP 功能广告 HTTP 传输层的协议。"""

    http: bool


@runtime_checkable
class ACPMcpSseCapabilityProtocol(Protocol):
    """用于 MCP 功能广告 sse 传输层的协议。"""

    sse: bool


@dataclass(frozen=True)
class ACPMcpCapabilities:
    """来自 ACP 初始化响应的标准化 MCP 功能。"""

    http: bool = False
    sse: bool = False


def normalize_mcp_capabilities(raw: Any) -> ACPMcpCapabilities:
    """标准化边界处的原始 MCP 能力。"""
    if isinstance(raw, ACPMcpCapabilities):
        return raw
    if isinstance(raw, Mapping):
        return ACPMcpCapabilities(
            http=bool(raw.get("http", False)),
            sse=bool(raw.get("sse", False)),
        )
    http_ok = bool(raw.http) if isinstance(raw, ACPMcpHttpCapabilityProtocol) else False
    sse_ok = bool(raw.sse) if isinstance(raw, ACPMcpSseCapabilityProtocol) else False
    return ACPMcpCapabilities(http=http_ok, sse=sse_ok)


# ---------------------------------------------------------------------------
# 错误信息合同
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPErrorCodeProtocol(Protocol):
    """携带 JSON-RPC 错误代码的异常协议。"""

    code: int | None


@runtime_checkable
class ACPErrorDataProtocol(Protocol):
    """携带错误数据的异常协议载荷。"""

    data: Any


@dataclass(frozen=True)
class ACPErrorInfo:
    """从边界处的 ACP 异常中提取的类型化错误详细信息。"""

    code: int | None
    message: str
    data: Any


def normalize_acp_error(exc: BaseException) -> ACPErrorInfo:
    """提取异常边界处的结构化错误信息。"""
    code = (
        exc.code
        if isinstance(exc, ACPErrorCodeProtocol) and isinstance(exc.code, int)
        else None
    )
    data = exc.data if isinstance(exc, ACPErrorDataProtocol) else None
    return ACPErrorInfo(code=code, message=str(exc), data=data)


# ---------------------------------------------------------------------------
# 文件凭据具有约束力的修订合同
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPRevisionedCredentialBinding(Protocol):
    """用于公开 authorization_revision 的凭据绑定的协议。"""

    @property
    def authorization_revision(self) -> int | None: ...


# ---------------------------------------------------------------------------
# 序列化 / 追踪合约
# ---------------------------------------------------------------------------


@runtime_checkable
class ACPModelDumpable(Protocol):
    """支持 Pydantic 样式 model_dump 的对象的协议。"""

    def model_dump(self, *args: Any, **kwargs: Any) -> Any: ...


def is_model_dumpable(obj: Any) -> bool:
    """如果 obj 是 BaseModel 或实现 model_dump()，则返回 True。"""
    return isinstance(obj, (BaseModel, ACPModelDumpable)) or hasattr(obj, "model_dump")
