"""客户端定义的工具：通过JSON规范定义的工具，由外部客户端执行。

这些工具允许前端客户端（如Agent Canvas）纯粹通过``POST /conversations``中的JSON注册工
具，不需要Python代码。 当智能体调用客户端
工具时，会通过 WebSocket 发出 ActionEvent，并且客户端处理执行。 SDK立即返回确认观测结
果。

这消除了对 JavaScript 存储库中的 Python 工具代码的需要以及复杂的
``tool_module_qualnames`` / ``--import-modules`` 管道。
"""

import copy
import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Self

from pydantic import BaseModel, Field, field_validator

from openhands.sdk.logger import get_logger
from openhands.sdk.tool.schema import Action, Observation, Schema
from openhands.sdk.tool.tool import (
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.tool.spec import Tool


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 缓存的动态操作类型
#
# ``Action.from_mcp_schema`` 创建一个 *具体* ``Action`` 子类，其
# ``kind`` 派生自类名 (``ClientAction_<name>``)。 这些子类在可区分联合层次结构中全局注册
# 进程，因此创建两个具有相同名称的类（e.g. 当同一个客户端工具注册两次或在对话恢复时重新
# 创建时）
# ``Action.resolve_kind`` 引发重复类错误并中断事件反序列化。 因此，我们缓存每个工具名称
# 生成的类型，并显式拒绝同名/不同-模式冲突。
# ---------------------------------------------------------------------------
_client_action_types: dict[str, type[Action]] = {}
_client_action_schemas: dict[str, dict[str, Any]] = {}
_client_tool_names: set[str] = set()
_client_action_lock = threading.RLock()


class ClientToolRegistrationError(ValueError):
    """当客户端工具注册收到无效输入时引发。

    这是调用者/输入错误 (e.g. 一个坏的 ``POST /conversations`` 载荷），因此诸如 Agent
     Server 之类的调用者将其映射到 4x
    x 响应而不是
    500.
    """


class ClientToolSchemaConflictError(ClientToolRegistrationError):
    """当客户端工具名称与不同的模式重用时引发。

    生成的操作 ``kind`` (``ClientAction_<name>``) 是进程全局的，因此单个名称不能代表
    两个不同的参数模式。
    """


def _get_client_action_type(name: str, schema: dict[str, Any]) -> type[Action]:
    """返回从 ``schema`` 构建的 ``name`` 的缓存 ``Action`` 子类。

    当再次请求相同的 ``name`` + ``schema`` 时，重用先前生成的类型。 如果 ``name`` 已
    经使用 * 不同的 * 模式注册，则引发：clas
    s:`ClientToolSchemaConflictError`，因为生成的操作
    ``kind`` 是进程全局的，不能同时表示两个模式。
    """
    with _client_action_lock:
        existing = _client_action_types.get(name)
        if existing is not None:
            if _client_action_schemas[name] != schema:
                raise ClientToolSchemaConflictError(
                    f"Client tool '{name}' is already registered with a different "
                    "parameters schema. Client tool names must map to a single, "
                    "stable schema within a process."
                )
            return existing
        action_type = Action.from_mcp_schema(
            model_name=f"ClientAction_{name}",
            schema=schema,
        )
        _client_action_types[name] = action_type
        _client_action_schemas[name] = copy.deepcopy(schema)
        return action_type


class ClientToolSpec(BaseModel):
    """由客户端定义的工具，在外部执行（不是由 SDK）。

    客户端在 ``POST /conversations`` 中传递这些规范来注册其执行在 SDK 之外处理的工具
    （e.g，由前端监听 ActionEvents 和
    WebSocket）。
    """

    name: str = Field(
        ...,
        description="Unique tool name the agent will use to call this tool.",
    )
    description: str = Field(
        ...,
        description=(
            "Description shown to the LLM explaining when and how to use this tool."
        ),
    )
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description=(
            "JSON Schema describing the tool's input parameters. "
            "Must be an object schema."
        ),
    )
    annotations: ToolAnnotations | None = Field(
        default=None,
        description=(
            "Optional MCP-style annotations for the tool. When omitted, the "
            "tool is treated conservatively (not read-only), so the agent is "
            "asked to predict a security risk before calling it."
        ),
    )

    @field_validator("parameters")
    @classmethod
    def _validate_object_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        """确保 ``parameters`` 是 JSON 模式 * 对象 * 模式。

        ``ClientTool`` 通过此模式构建 Pydantic 动作模型
        ``Action.from_mcp_schema``，仅支持对象模式。 在此处进行验证，以便调用者在源头
        立即获得明确的错误，而不是稍后在工具创建过程中出现令
        人困惑的失败。
        """
        if v.get("type") != "object":
            raise ValueError(
                "ClientToolSpec.parameters must be an object JSON Schema "
                f"(got type={v.get('type')!r}). Example: "
                '{"type": "object", "properties": {...}}'
            )
        return v


class ClientToolObservation(Observation):
    """调用客户端工具时返回观测结果。

    实际执行发生在客户端； SDK 返回此确认，以便智能体循环可以继续。
    """


class ClientToolExecutor(ToolExecutor):
    """返回确认的无操作执行器观测结果。

    真正的执行发生在客户端（前端）上，它监听 ActionEvent over WebSocket。
    """

    def __call__(
        self,
        action: Action,  # noqa: ARG002
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> ClientToolObservation:
        return ClientToolObservation.from_text(text="Tool call dispatched to client.")


# 共享执行器实例——无状态，所以一个就足够了。
_CLIENT_TOOL_EXECUTOR = ClientToolExecutor()


class ClientTool(ToolDefinition[Action, ClientToolObservation]):
    """其执行被推迟到外部客户端的工具。

    在对话开始时从：class:`ClientToolSpec` 创建。 智能体将其视为普通工具并可以调用它
    ； ActionEvent 通过 WebSocket 发出供
    客户端处理。
    """

    user_selectable: ClassVar[bool] = False

    client_tool_name: str = Field(
        description="Per-instance tool name from the ClientToolSpec.",
    )
    input_schema: dict[str, Any] = Field(
        description=(
            "The original JSON Schema for the tool's parameters, as provided by "
            "the client. Used verbatim when exporting the tool to the LLM so "
            "client-defined constraints (enum, nested objects, bounds, "
            "additionalProperties, ...) are preserved."
        ),
    )

    @property
    def name(self) -> str:  # type: ignore[override]
        """返回客户端定义的工具名称。"""
        return self.client_tool_name

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        **params: Any,
    ) -> Sequence[Self]:
        """从：class:`ClientToolSpec` 创建 ClientTool。

        Args:
            conv_state: 对话状态（未使用）。
            **params: 必须包含 ``spec`` — :class:`ClientToolSpec`
                实例或 JSON-可序列化字典 1。 当规范流经每个对话时，使用字典形式
                ``Tool.params`` 在服务器上。

        Returns:
            包含 ClientTool 的单元素序列。
        """
        spec_param = params.get("spec")
        if spec_param is None:
            raise ValueError(
                "ClientTool.create requires a 'spec' parameter "
                "(a ClientToolSpec or a dict of one)."
            )
        if isinstance(spec_param, ClientToolSpec):
            spec = spec_param
        elif isinstance(spec_param, dict):
            spec = ClientToolSpec.model_validate(spec_param)
        else:
            raise TypeError(
                "ClientTool.create 'spec' must be a ClientToolSpec or dict, "
                f"got {type(spec_param)}."
            )

        action_type = _get_client_action_type(spec.name, spec.parameters)

        return [
            cls(
                client_tool_name=spec.name,
                description=spec.description,
                action_type=action_type,
                observation_type=ClientToolObservation,
                executor=_CLIENT_TOOL_EXECUTOR,
                # 除非客户端明确提供，否则保留注释未设置
                # 他们：客户端工具可以触发任意前端副作用，
                # 所以我们不能乐观地假设只读/幂等。
                annotations=spec.annotations,
                input_schema=spec.parameters,
            )
        ]

    @classmethod
    def from_spec(cls, spec: ClientToolSpec) -> "ClientTool":
        """从规范创建 ClientTool 的便利工厂。

        返回单个 ClientTool 实例（不是序列）。
        """
        tools = cls.create(spec=spec)
        return tools[0]

    def _get_tool_schema(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> dict[str, Any]:
        """从原始客户端模式构建面向提供商的模式。

        基线实现会重建模式从生成的 Pydantic 动作模型，这会丢弃客户端定义的 JSON 模式
        约束 (``enum``, 子 ``properties``,
        ``additionalProperties``, 数值范围，...). 这里我们从原始的``input_schema``开
        始，只覆盖SDK添加的元字段（
        ``summary``，并且，如果适用，
        ``security_risk``）因此客户端约束被准确保留。
        """
        if action_type is not None:
            raise ValueError(
                "ClientTool._get_tool_schema does not support overriding action_type"
            )

        # 与基本实现完全相同地渲染 SDK 元字段（摘要/security_risk），然后仅提升这些属性
        # 。
        #
        sdk_schema = super()._get_tool_schema(
            add_security_risk_prediction=add_security_risk_prediction,
        )
        sdk_props: dict[str, Any] = sdk_schema.get("properties", {})
        sdk_required: list[str] = sdk_schema.get("required", []) or []

        merged = copy.deepcopy(self.input_schema)
        merged.setdefault("type", "object")
        props = merged.setdefault("properties", {})
        for meta in ("security_risk", "summary"):
            if meta in sdk_props:
                props[meta] = sdk_props[meta]
                if meta in sdk_required:
                    required = merged.setdefault("required", [])
                    if meta not in required:
                        required.append(meta)
        merged = self._merge_response_schema(merged)

        from openhands.sdk.tool.tool import _prioritize_schema_fields

        _prioritize_schema_fields(
            schema=merged,
            priority=("security_risk", "summary"),
        )
        return merged

    def to_mcp_tool(
        self,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if input_schema is not None or output_schema is not None:
            raise ValueError(
                "ClientTool.to_mcp_tool does not support overriding schemas"
            )
        return super().to_mcp_tool(
            input_schema=self.input_schema,
            output_schema=self.observation_type.to_mcp_schema()
            if self.observation_type
            else None,
        )


def extract_client_tool_specs(tools: "Sequence[Tool]") -> list[ClientToolSpec]:
    """恢复已持久化 ``Tool`` 规范中嵌入的：class:`ClientToolSpec`。

    客户端工具在 ``Tool.params['spec']`` 下包含其完整规范（请参阅
    :func:`register_client_tools`)。 当谈话以新的方式恢复时
    过程中，该规范是模式唯一存在的地方，因此我们使用它来重新注册动态工具。 仅当已持久
    化 ``Tool`` 的 ``params['spec']`` 验证为
    ``ClientToolSpec`` 且其
    ``name`` 匹配工具名称，这避免了对碰巧使用 ``spec`` 参数的普通工具进行错误分类。
    """
    from pydantic import ValidationError

    specs: list[ClientToolSpec] = []
    for tool in tools:
        raw = (tool.params or {}).get("spec")
        if not isinstance(raw, dict):
            continue
        try:
            spec = ClientToolSpec.model_validate(raw)
        except ValidationError:
            continue
        if spec.name == tool.name:
            specs.append(spec)
    return specs


def register_client_tools(specs: Sequence[ClientToolSpec]) -> list["Tool"]:
    """注册客户端定义的工具并返回每个对话的工具规格。

    请输出简体中文译文。`ClientTool`  *class* (一个状态机解析器) 在全局工具名下注册一
    次注册表，while each tool's 模式旅行于对
    话之中 ``Tool.params`` 而不是生活在全局流程中注册表。 这使解析器保持无状态，因此
    ，两个定义相同的工具名称的对话不会影响到彼此模式不要互相覆盖。

    Args:
        specs: 要注册的客户端工具规格。

    Returns:
        :class:`~openhands.sdk.tool.spec.Tool` 规范列表（每个输入规范一个），注入到智
        能体的 ``tools`` 中，以便
        ``_initialize()`` 可以解析它们。
    """
    from openhands.sdk.tool.registry import list_registered_tools, register_tool
    from openhands.sdk.tool.spec import Tool

    seen_names: set[str] = set()
    for spec in specs:
        if spec.name in seen_names:
            raise ClientToolRegistrationError(
                f"Duplicate client tool name '{spec.name}' in one registration "
                "request. Client tool names must be unique."
            )
        seen_names.add(spec.name)

    with _client_action_lock:
        tool_specs: list[Tool] = []
        already_registered = set(list_registered_tools())
        for spec in specs:
            collides_with_non_client_tool = (
                spec.name in already_registered and spec.name not in _client_tool_names
            )
            if collides_with_non_client_tool:
                raise ClientToolRegistrationError(
                    f"Client tool name '{spec.name}' collides with an existing "
                    "non-client tool. Choose a unique client tool name."
                )

        for spec in specs:
            _get_client_action_type(spec.name, spec.parameters)
            if spec.name not in already_registered:
                register_tool(spec.name, ClientTool)
                already_registered.add(spec.name)
            _client_tool_names.add(spec.name)
            tool_specs.append(Tool(name=spec.name, params={"spec": spec.model_dump()}))
        return tool_specs
