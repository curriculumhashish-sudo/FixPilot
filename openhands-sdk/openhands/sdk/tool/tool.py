import asyncio
import copy
import json
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Protocol,
    Self,
    TypeVar,
)

from jsonschema import Draft202012Validator
from jsonschema.exceptions import (
    SchemaError,
    ValidationError as JSONSchemaValidationError,
)
from litellm import (
    ChatCompletionToolParam,
    ChatCompletionToolParamFunctionChunk,
)
from openai.types.responses import FunctionToolParam
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    field_validator,
)
from pydantic.json_schema import SkipJsonSchema

from openhands.sdk.security import risk
from openhands.sdk.tool.schema import Action, Observation, Schema
from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
    get_known_concrete_subclasses,
    kind_of,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


ActionT = TypeVar("ActionT", bound=Action)
ObservationT = TypeVar("ObservationT", bound=Observation)
type ResponseSchema = type[BaseModel] | dict[str, Any]
_action_types_with_risk: dict[type, type] = {}
_action_types_with_summary: dict[type, type] = {}
_action_type_lock = threading.Lock()
# JSON 模式用于 Pydantic-模型响应模式，由不可变类缓存，因此 model_json_schema() 每个类最
# 多运行一次。 Dict 模式没有被缓存（它们没有安全地使用身份密钥）； 他们使用下面的廉价深
# 度复制路径。 由它自己的锁而不是 _action_type_lock 守护：两者从不嵌套，并且单独的锁使模
# 式构建动作类型关键部分。
#
_response_schema_json_cache: dict[type[BaseModel], dict[str, Any]] = {}
_response_schema_json_lock = threading.Lock()
_RESERVED_RESPONSE_FIELDS = frozenset(
    {"kind", "security_risk", "structured_output", "summary"}
)
_SUPPORTED_RESPONSE_SCHEMA_KEYS = frozenset(
    {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$id",
        "$schema",
        "$vocabulary",
        "additionalProperties",
        "default",
        "deprecated",
        "description",
        "examples",
        "properties",
        "readOnly",
        "required",
        "title",
        "type",
        "writeOnly",
    }
)


def _validated_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid response_schema: {exc.message}") from exc
    if schema.get("type") != "object":
        raise ValueError("response_schema must describe a JSON object")
    return schema


def _response_schema_json(response_schema: ResponseSchema) -> dict[str, Any]:
    if isinstance(response_schema, dict):
        return _validated_response_schema(copy.deepcopy(response_schema))
    if not (
        isinstance(response_schema, type) and issubclass(response_schema, BaseModel)
    ):
        raise TypeError("response_schema must be a Pydantic model or JSON Schema")

    # 在锁下构建，因此 model_json_schema() 实际上每个类最多运行一次，并交回私有副本，以
    # 便调用者无法改变缓存。
    #
    with _response_schema_json_lock:
        cached = _response_schema_json_cache.get(response_schema)
        if cached is None:
            cached = _validated_response_schema(response_schema.model_json_schema())
            _response_schema_json_cache[response_schema] = cached
        return copy.deepcopy(cached)


def _response_tool_schema(response_schema: ResponseSchema) -> dict[str, Any]:
    schema = _response_schema_json(response_schema)
    properties = schema.get("properties")
    if not properties:
        raise ValueError("response_schema must define named properties")

    unsupported = set(schema) - _SUPPORTED_RESPONSE_SCHEMA_KEYS
    if unsupported:
        raise ValueError(
            f"response_schema has unsupported top-level keywords: {sorted(unsupported)}"
        )

    additional_properties = schema.get("additionalProperties")
    if additional_properties not in (None, False):
        raise ValueError(
            "response_schema does not support dynamic fields via additionalProperties"
        )

    unnamed_required = set(schema.get("required", ())) - set(properties)
    if unnamed_required:
        raise ValueError(
            f"response_schema required fields {sorted(unnamed_required)} must be "
            "named properties"
        )

    expanded = _expand_response_refs(schema, schema.get("$defs", {}))
    assert isinstance(expanded, dict)
    return expanded


def _expand_response_refs(
    node: dict[str, Any] | bool,
    defs: dict[str, Any],
    visiting: frozenset[str] = frozenset(),
) -> dict[str, Any] | bool:
    if isinstance(node, bool):
        return node
    if "$ref" in node:
        ref = node["$ref"]
        if ref.startswith("#/$defs/"):
            name = ref.removeprefix("#/$defs/")
            if name not in defs:
                return copy.deepcopy(node)
            if name in visiting:
                return _shallow_response_ref(defs[name])
            expanded = _expand_response_refs(defs[name], defs, visiting | {name})
            if isinstance(expanded, dict):
                siblings = {key: value for key, value in node.items() if key != "$ref"}
                expanded_siblings = _expand_response_refs(
                    siblings, defs, visiting | {name}
                )
                assert isinstance(expanded_siblings, dict)
                expanded.update(expanded_siblings)
            return expanded

    result = copy.deepcopy(node)
    result.pop("$defs", None)
    if "properties" in result:
        result["properties"] = {
            name: _expand_response_refs(value, defs, visiting)
            for name, value in result["properties"].items()
        }
    for keyword in ("items", "additionalProperties", "not"):
        value = result.get(keyword)
        if isinstance(value, (dict, bool)):
            result[keyword] = _expand_response_refs(value, defs, visiting)
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        if keyword in result:
            result[keyword] = [
                _expand_response_refs(value, defs, visiting)
                for value in result[keyword]
            ]
    return result


def _shallow_response_ref(node: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"type": node.get("type", "object")}
    if "description" in node:
        result["description"] = node["description"]
    return result


def _camel_to_snake(name: str) -> str:
    """将 CamelCase 转换为 snake_case。

    Examples:
        TerminalTool -> bash_tool FileEditorTool -> file_editor_tool XMLHttpRequest -> xml_http_request
    """  # noqa: E501
    # 在大写字母前插入下划线（第一个字母除外）
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    # 在小写字母后面的大写字母之前插入下划线
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class ToolAnnotations(BaseModel):
    """提供有关工具行为的提示的注释。

    根据模型上下文协议(MCP)说明：
    https://github.com/modelcontextprotocol/modelcontextprotocol/blob/caf3424488b10b4a7b1f8cb634244a450a1f4400/schema/2025-06-18/schema.ts#L838
    """  # noqa: E501

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        # 需要在此定义标题，避免与 MCP's ToolAnnotations 当两者都包含在同一个中 JSON  模
        # 式为了 openapi.json
        #
        title="openhands.sdk.tool.tool.ToolAnnotations",
    )

    title: str | None = Field(
        default=None, description="A human-readable title for the tool."
    )
    readOnlyHint: bool = Field(
        default=False,
        description="If true, the tool does not modify its environment. Default: false",
    )
    destructiveHint: bool = Field(
        default=True,
        description="If true, the tool may perform destructive updates to its environment. If false, the tool performs only additive updates. (This property is meaningful only when `readOnlyHint == false`) Default: true",  # noqa: E501
    )
    idempotentHint: bool = Field(
        default=False,
        description="If true, calling the tool repeatedly with the same arguments will have no additional effect on the its environment. (This property is meaningful only when `readOnlyHint == false`) Default: false",  # noqa: E501
    )
    openWorldHint: bool = Field(
        default=True,
        description="If true, this tool may interact with an 'open world' of external entities. If false, the tool's domain of interaction is closed. For example, the world of a web search tool is open, whereas that of a memory tool is not. Default: true",  # noqa: E501
    )


@dataclass(frozen=True, slots=True)
class DeclaredResources:
    """工具为给定操作访问的资源。

    由 ``ParallelToolExecutor`` 用于决定在运行工具之前要获取什么锁（如果有）。

    Examples:

        DeclaredResources(keys=(), declared=False)       # 未知序列化
        DeclaredResources(keys=(), declared=True)         # 安全，无资源
        DeclaredResources(keys=("file:/a.py",), declared=True)  # 锁这些

    Note:
        `declared=True` 与空键的区别
        `declared=False` 很微妙但很重要：

        - `declared=True, keys=()`：该工具已明确分析其资源使用情况并确定它没有触及任
        何共享内容。 执行者信任这一点并完全跳过锁定。
        - `declared=False`：该工具*未*声明其资源（默认）。 执行器无法保证安全，因此它
        会退回到工具范围的互斥体，该互斥体序列化对此工具的所有调用
        。

        简而言之：`declared=False` 表示“我还没有考虑过”
        while `declared=True, keys=()` means "I have, and I'm safe."

    """

    keys: tuple[str, ...]
    declared: bool


class ToolExecutor[ActionT, ObservationT](ABC):
    """工具的执行器函数类型。"""

    @abstractmethod
    def __call__(
        self, action: ActionT, conversation: "LocalConversation | None" = None
    ) -> ObservationT:
        """使用给定操作执行该工具并返回观测结果。

        Args:
            action: 要执行的操作，包含参数和上下文
                   工具操作所需的。
            conversation: 用于工具执行的对话上下文。
                         Note: 其类型为 LocalConversation（不是
                         BaseConversation)，因为所有工具执行都发生在
                         LocalConversation 上下文内。 即使通过
                         RemoteConversation 调用工具，远程 Agent Server 也会创建一个
                         LocalConversation 实例来处理实际的工具执行。 参见
                         https://github.com/OpenHands/agent-sdk/pull/925
                         for more details.

        Returns:
            包含工具执行结果的观测结果。
        """

    def close(self) -> None:
        """关闭执行器并清理资源。

        默认实现不执行任何操作。 子类应该重写此方法来执行清理（e.g.、关闭连接、终止进
        程等）。
        """
        pass

    def interrupt(self) -> None:
        """中断任何正在进行的执行（e.g.，发送 Ctrl+C）。

        当此工具仍在执行时触发对话中断时，从 * 不同的 * 线程调用。 实现应该是线程安全
        并且是幂等的。

        默认为无操作； 具有长时间运行操作的工具（终端子进程、浏览器导航等）应覆盖。
        """
        pass


class ExecutableTool(Protocol):
    """保证具有非None执行器的工具的协议。

    当使用已知可执行的工具时，这消除了运行时 None 检查和类型缩小的需要。
    """

    name: str
    executor: ToolExecutor[Any, Any]  # 非可选执行人

    def __call__(
        self, action: Action, conversation: "LocalConversation | None" = None
    ) -> Observation:
        """使用给定的操作执行该工具。"""
        ...


class ToolDefinition[ActionT, ObservationT](DiscriminatedUnionMixin, ABC):
    """所有工具实现的基类。

    此类充当所有工具类型的可区分联合的基础。 所有工具都必须从此类继承并实现 .create()
     方法，以便使用执行器和参数进行正确的初始化。

    特点：
    - 将输入/输出模式（类或字典）规范化为模型+模式。
    - 执行前验证输入。
    - 仅当定义了输出模型时才强制输出； 否则返回原版 JSON。
    - 导出 MCP 工具说明。

    Examples:
        没有参数的简单工具：
            class FinishTool(ToolDefinition[FinishAction, FinishObservation]):
                @classmethod
                def create(cls, conv_state=None, **params):
                    return [cls(name="finish", ..., executor=FinishExecutor())]

        具有初始化参数的复杂工具：
            class TerminalTool(ToolDefinition[TerminalAction,
                TerminalObservation]):
                @classmethod
                def create(cls, conv_state, **params):
                    executor = TerminalExecutor(
                        working_dir=conv_state.workspace.working_dir,
                        **参数，
                    )
                    return [cls(name="terminal", ..., executor=executor)]
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True, arbitrary_types_allowed=True
    )

    # 自动工具命名 - 由 __init_subclass__ 设置
    name: ClassVar[str] = ""

    user_selectable: ClassVar[bool] = True
    """用户在配置智能体的工具集时是否可以选择此工具。"""

    catalog_description: ClassVar[str] = ""
    """面向用户的目录简介； ``description`` 是 LLM 读取的内容。"""

    conversation_local: ClassVar[bool] = False
    """该工具是否仅读取和写入其自己的对话状态。"""

    def __init_subclass__(cls, **kwargs):
        """创建子类时自动根据类名设置名称。"""
        super().__init_subclass__(**kwargs)
        # 仅当当前类中未显式定义时才自动设置
        if "name" not in cls.__dict__:
            cls.name = _camel_to_snake(cls.__name__).removesuffix("_tool")

    description: str
    action_type: type[Action] = Field(repr=False)
    observation_type: type[Observation] | None = Field(default=None, repr=False)

    annotations: ToolAnnotations | None = None
    meta: dict[str, Any] | None = None

    # 仅运行时； 总是隐藏在垃圾场
    executor: SkipJsonSchema[ToolExecutor | None] = Field(
        default=None, repr=False, exclude=True
    )

    prompt_guidance: SkipJsonSchema[str | None] = Field(
        default=None,
        repr=False,
        exclude=True,
        description="System-prompt guidance for this tool; deduplicated by text.",
    )

    response_schema: SkipJsonSchema[ResponseSchema | None] = Field(
        default=None, repr=False, exclude=True
    )

    @classmethod
    def is_usable(cls) -> bool:
        """返回该工具是否可以在当前环境中使用。"""
        return True

    @classmethod
    @abstractmethod
    def create(cls, *args, **kwargs) -> Sequence[Self]:
        """创建一系列工具实例。

        该方法必须由所有子类实现，以提供自定义初始化逻辑，通常使用参数初始化执行器
        from conv_state and other optional parameters.

        Args:
            *args: 可变位置参数（通常将 conv_state 作为第一个参数）。
            **kwargs: 用于工具初始化的可选参数。

        Returns:
            一系列工具实例。 即使单个工具也会作为序列返回，以提供一致的接口并消除联合
            返回类型。
        """
        raise NotImplementedError("ToolDefinition subclasses must implement .create()")

    @computed_field(return_type=str, alias="title")
    @property
    def title(self) -> str:
        if self.annotations and self.annotations.title:
            return self.annotations.title
        return self.name

    @field_serializer("action_type")
    def _ser_action_type(self, t: type[Action]) -> str:
        # 序列化作为普通字符串
        return kind_of(t)

    @field_serializer("observation_type")
    def _ser_observation_type(self, t: type[Observation] | None) -> str | None:
        return None if t is None else kind_of(t)

    @field_validator("action_type", mode="before")
    @classmethod
    def _val_action_type(cls, v):
        if isinstance(v, str):
            return Action.resolve_kind(v)
        assert isinstance(v, type) and issubclass(v, Action), (
            f"action_type must be a subclass of Action, but got {type(v)}"
        )
        return v

    @field_validator("observation_type", mode="before")
    @classmethod
    def _val_observation_type(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = Observation.resolve_kind(v)
        assert isinstance(v, type) and issubclass(v, Observation), (
            f"observation_type must be a subclass of Observation, but got {type(v)}"
        )
        return v

    def set_executor(self, executor: ToolExecutor) -> Self:
        """使用给定的执行器创建一个新的 Tool 实例。"""
        return self.model_copy(update={"executor": executor})

    def set_response_schema(self, response_schema: ResponseSchema | None) -> Self:
        """返回为结构化输出配置的副本。"""
        if response_schema is None:
            return self.model_copy(update={"response_schema": None})

        response_fields = set(
            _response_tool_schema(response_schema).get("properties", {})
        )
        reserved = response_fields & _RESERVED_RESPONSE_FIELDS
        if reserved:
            raise ValueError(f"response_schema fields {sorted(reserved)} are reserved")

        base_tool = self.model_copy(update={"response_schema": None})
        tool_fields = set(base_tool._get_tool_schema().get("properties", {}))
        overlap = response_fields & tool_fields
        if overlap:
            raise ValueError(
                f"response_schema fields {sorted(overlap)} collide with "
                f"existing fields on {self.action_type.__name__}"
            )
        return self.model_copy(update={"response_schema": response_schema})

    def as_executable(self) -> ExecutableTool:
        """将此工具作为 ExecutableTool 返回，确保它有一个执行器。

        此方法通过保证返回的工具具有非 None 执行器来消除运行时 None 检查的需要。

        Returns:
            该工具实例，类型为ExecutableTool。

        Raises:
            NotImplementedError: 如果该工具没有执行器。
        """
        if self.executor is None:
            raise NotImplementedError(f"Tool '{self.name}' has no executor")
        return self  # type: ignore[return-value]

    def declared_resources(self, action: Action) -> DeclaredResources:  # noqa: ARG002
        """声明该工具针对给定操作访问的资源。

        在子类中重写以启用细粒度并行执行。

        键应使用格式 ``"<type>:<identifier>"``、e.g。
        ``"file:/absolute/path"`` 或 ``"terminal:session"``。
        """
        return DeclaredResources(keys=(), declared=False)

    def action_from_arguments(self, arguments: dict[str, Any]) -> Action:
        """从解析的参数创建一个操作。"""
        action_arguments, structured_output = self._split_response_arguments(arguments)
        action = self.action_type.model_validate(action_arguments)
        action._structured_output = structured_output
        return action

    def _split_response_arguments(
        self, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if self.response_schema is None:
            return dict(arguments), None

        schema = _response_schema_json(self.response_schema)
        response_fields = set(schema.get("properties", {}))
        response_arguments = {
            key: value for key, value in arguments.items() if key in response_fields
        }
        action_arguments = {
            key: value for key, value in arguments.items() if key not in response_fields
        }

        if isinstance(self.response_schema, type):
            response = self.response_schema.model_validate(response_arguments)
            structured_output = response.model_dump(mode="json")
        else:
            try:
                Draft202012Validator(schema).validate(response_arguments)
            except JSONSchemaValidationError as exc:
                raise ValueError(
                    f"response_schema validation failed: {exc.message}"
                ) from exc
            structured_output = response_arguments
        return action_arguments, structured_output

    def parse_response(self, action: Action) -> BaseModel | dict[str, Any]:
        """解析操作的结构化输出。"""
        if self.response_schema is None:
            raise ValueError(f"Tool '{self.name}' has no response_schema configured.")
        if action.structured_output is None:
            raise ValueError(
                f"Action '{type(action).__name__}' has no structured output"
            )
        if isinstance(self.response_schema, type):
            return self.response_schema.model_validate(
                action.structured_output, by_name=True
            )
        try:
            Draft202012Validator(self.response_schema).validate(
                action.structured_output
            )
        except JSONSchemaValidationError as exc:
            raise ValueError(
                f"response_schema validation failed: {exc.message}"
            ) from exc
        return action.structured_output

    def parse_last_response(
        self, events: "Sequence[Any]"
    ) -> BaseModel | dict[str, Any] | None:
        """解析此工具的最新操作。"""
        from openhands.sdk.event import ActionEvent

        event = next(
            (
                event
                for event in reversed(events)
                if isinstance(event, ActionEvent)
                and event.tool_name == self.name
                and event.action is not None
            ),
            None,
        )
        if event is None:
            return None
        arguments = json.loads(event.tool_call.arguments)
        _, structured_output = self._split_response_arguments(arguments)
        if structured_output is None:
            return None
        assert event.action is not None
        action = event.action.model_copy()
        action._structured_output = structured_output
        return self.parse_response(action)

    def __call__(
        self, action: ActionT, conversation: "LocalConversation | None" = None
    ) -> Observation:
        """验证输入、执行和强制输出。

        我们总是返回一些观测结果子类，但并不总是通用 ObservationT。
        """
        if self.executor is None:
            raise NotImplementedError(f"Tool '{self.name}' has no executor")

        # 执行
        result = self.executor(action, conversation)

        # 仅当我们声明模型时才强制输出； 否则包裹在基数观测结果中
        if self.observation_type:
            if isinstance(result, self.observation_type):
                observation = result
            else:
                observation = self.observation_type.model_validate(result)
        elif isinstance(result, Observation):
            observation = result
        elif isinstance(result, BaseModel):
            observation = Observation.model_validate(result.model_dump())
        elif isinstance(result, dict):
            observation = Observation.model_validate(result)
        else:
            raise TypeError(
                "Output must be dict or BaseModel when no output schema is defined"
            )

        # 每个工具的输出都通过这里进行，因此屏蔽一次可以默认覆盖新工具，而不是记住修补它
        # 。
        #
        if conversation is None:
            return observation
        registry = conversation.state.secret_registry
        return registry.mask_secrets_in_model(observation)

    async def acall(
        self, action: ActionT, conversation: "LocalConversation | None" = None
    ) -> Observation:
        """直接调用时异步运行此工具。

        默认实现通过事件循环的执行器在线程中运行：meth:`__call__`，因此调用者可以等待
        单个工具调用，而不会阻塞事件循环。

        SDK的内部异步调度路径不调用此钩子； 它直接从自己的执行器通过：meth:`__call__`
         调度。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self, action, conversation)

    def to_mcp_tool(
        self,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将工具转换为 MCP 工具定义。

        允许覆盖输入/输出模式（通常由子类）。

        Args:
            input_schema: 可以选择覆盖输入模式。
            output_schema: 可以选择覆盖输出模式。
        """
        input_schema = (
            self.action_type.to_mcp_schema() if input_schema is None else input_schema
        )
        out = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self._merge_response_schema(input_schema),
        }
        if self.annotations:
            out["annotations"] = self.annotations
        if self.meta is not None:
            out["_meta"] = self.meta

        derived_output = (
            output_schema
            if output_schema is not None
            else (
                self.observation_type.to_mcp_schema() if self.observation_type else None
            )
        )
        if derived_output is not None:
            out["outputSchema"] = derived_output
        return out

    def _get_tool_schema(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> dict[str, Any]:
        action_type = action_type or self.action_type

        # 如果启用，则应用安全风险增强
        add_security_risk_prediction = add_security_risk_prediction and (
            self.annotations is None or (not self.annotations.readOnlyHint)
        )
        if add_security_risk_prediction:
            action_type = create_action_type_with_risk(action_type)

        # 始终添加摘要字段以提高透明度和可解释性
        action_type = _create_action_type_with_summary(action_type)

        schema = self._merge_response_schema(action_type.to_mcp_schema())
        _prioritize_schema_fields(
            schema=schema,
            priority=("security_risk", "summary"),
        )
        return schema

    def _merge_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        if self.response_schema is None:
            return schema

        response_schema = _response_tool_schema(self.response_schema)
        merged = copy.deepcopy(schema)
        properties = merged.setdefault("properties", {})
        response_properties = response_schema.get("properties", {})
        overlap = set(properties) & set(response_properties)
        if overlap:
            raise ValueError(
                f"response_schema fields {sorted(overlap)} collide with tool fields"
            )
        properties.update(response_properties)

        required = merged.setdefault("required", [])
        for field_name in response_schema.get("required", []):
            if field_name not in required:
                required.append(field_name)
        if response_schema.get("additionalProperties") is False:
            merged["additionalProperties"] = False
        return merged

    def to_openai_tool(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> ChatCompletionToolParam:
        """将工具转换为 OpenAI 工具。

        Args:
            add_security_risk_prediction: 是否添加`security_risk`字段
                到 LLM 的动作模式进行预测。 这对于可能存在安全风险的工具很有用，因此
                LLM可以在调用该工具之前推断出风险级别。
            action_type: 可以选择覆盖 action_type 以用于模式。
                这很有用 MCPTool 使用基于工具输入动态创建的动作类型模式。

        Note:
            摘要字段始终添加到模式，以提高智能体操作的透明度和可解释性。
        """
        return ChatCompletionToolParam(
            type="function",
            function=ChatCompletionToolParamFunctionChunk(
                name=self.name,
                description=self.description,
                parameters=self._get_tool_schema(
                    add_security_risk_prediction,
                    action_type,
                ),
            ),
        )

    def to_responses_tool(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> FunctionToolParam:
        """将工具转换为响应 API 功能工具（输入 LiteLLM）。

        对于响应 API，功能工具需要顶级键：
        { "type": "function", "name": ..., "description": ..., "parameters": ... }

        Args:
            add_security_risk_prediction: 是否添加`security_risk`字段
            action_type: 操作类型的可选覆盖

        Note:
            摘要字段始终添加到模式，以提高智能体操作的透明度和可解释性。
        """

        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self._get_tool_schema(
                add_security_risk_prediction,
                action_type,
            ),
            "strict": False,
        }

    @classmethod
    def resolve_kind(cls, kind: str) -> type:
        """将种类字符串解析为其相应的工具类。

        Args:
            kind: 要解析的工具类的名称

        Returns:
            kind对应的工具类

        Raises:
            ValueError: 如果种类未知
        """
        for subclass in get_known_concrete_subclasses(cls):
            if subclass.__name__ == kind:
                return subclass

        # 获取错误消息的所有可能类型
        possible_kinds = [
            subclass.__name__ for subclass in get_known_concrete_subclasses(cls)
        ]
        possible_kinds_str = (
            ", ".join(sorted(possible_kinds)) if possible_kinds else "none"
        )

        error_msg = (
            f"Unexpected kind '{kind}' for {cls.__name__}. "
            f"Expected one of: {possible_kinds_str}. "
            f"If you receive this error when trying to wrap a DiscriminatedUnion "
            f"instance inside another pydantic model, you may need to use "
            f"OpenHandsModel instead of BaseModel to make sure that an invalid "
            f"schema has not been cached."
        )
        raise ValueError(error_msg)


def _prioritize_schema_fields(
    schema: dict[str, Any], priority: tuple[str, ...]
) -> None:
    """将 *priority* 字段移至 ``schema["properties"]`` 的前面。

    这确保 LLM 在大内容参数之前生成短元数据字段，因此输出 token 截断不会剪切所需字段
    。 参见
    https://github.com/OpenHands/software-agent-sdk/issues/1911
    """
    if "properties" not in schema:
        return
    props = schema["properties"]
    priority_set = set(priority)
    ordered = {k: props[k] for k in priority if k in props}
    ordered.update({k: v for k, v in props.items() if k not in priority_set})
    schema["properties"] = ordered


def create_action_type_with_risk(action_type: type[Schema]) -> type[Schema]:
    with _action_type_lock:
        action_type_with_risk = _action_types_with_risk.get(action_type)
        if action_type_with_risk:
            return action_type_with_risk

        # 重新使用层次结构中已存在但其缓存条目丢失的 WithRisk 类（修复#2642）。
        #
        target_name = f"{action_type.__name__}WithRisk"
        for sub in action_type.__subclasses__():
            if sub.__name__ == target_name:
                _action_types_with_risk[action_type] = sub
                return sub

        action_type_with_risk = type(
            target_name,
            (action_type,),
            {
                "security_risk": Field(
                    default=risk.SecurityRisk.UNKNOWN,
                    description="The LLM's assessment of the safety risk of this action.",  # noqa:E501
                ),
                "__annotations__": {"security_risk": risk.SecurityRisk},
            },
        )
        _action_types_with_risk[action_type] = action_type_with_risk
        return action_type_with_risk


def _create_action_type_with_summary(action_type: type[Schema]) -> type[Schema]:
    """创建一个新的操作类型，其中包含要预测的 LLM 的摘要字段。

    这会动态地将“摘要”字段添加到操作模式，从而允许 LLM 提供每个操作的简要说明。

    如果 action_type 已在其自己的模式中声明了 ``summary`` (e.g. 像 Jira 这样的 MCP 工
    具，其 ``summary`` 是工单标
    题），原始类型将原封不动地返回，以避免隐藏真实参数。

    Args:
        action_type: 原有动作类型强化

    Returns:
        包含摘要字段的新类型，如果已声明 ``summary``，则为原始类型。
    """
    # 不要使用元字段来隐藏工具自己的“摘要”参数。
    if "summary" in action_type.model_fields:
        return action_type

    with _action_type_lock:
        action_type_with_summary = _action_types_with_summary.get(action_type)
        if action_type_with_summary:
            return action_type_with_summary

        # 重新使用层次结构中已存在但其缓存条目丢失的 WithSummary 类（修复#2642）。
        #
        target_name = f"{action_type.__name__}WithSummary"
        for sub in action_type.__subclasses__():
            if sub.__name__ == target_name:
                _action_types_with_summary[action_type] = sub
                return sub

        action_type_with_summary = type(
            target_name,
            (action_type,),
            {
                "summary": Field(
                    default=None,
                    description=(
                        "A concise summary (approximately 10 words) describing what "
                        "this specific action does. Focus on the key operation and target. "  # noqa:E501
                        "Example: 'List all Python files in current directory'"
                    ),
                ),
                "__annotations__": {"summary": str | None},
            },
        )
        _action_types_with_summary[action_type] = action_type_with_summary
        return action_type_with_summary
