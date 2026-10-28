"""MCP 积分的实用函数。"""

import copy
import json
import re
import threading
from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation

import mcp.types
from litellm import ChatCompletionToolParam
from openai.types.responses import FunctionToolParam
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_serializer,
    field_validator,
)

from openhands.sdk.llm import TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.definition import MCPToolAction, MCPToolObservation
from openhands.sdk.observability.laminar import observe
from openhands.sdk.security import risk
from openhands.sdk.skills.utils import expand_variable_references
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from openhands.sdk.tool.schema import Schema, _process_schema_node
from openhands.sdk.tool.tool import _prioritize_schema_fields
from openhands.sdk.utils.models import DiscriminatedUnionMixin


logger = get_logger(__name__)


# MCP 工具执行的默认值超时（以秒为单位）
MCP_TOOL_TIMEOUT_SECONDS = 300

# MCP 2.x 转储其 snake_case 属性名称，除非 by_alias=True； MCP 1.x 仅读取 camelCase 线路
# 名称。 inputSchema/outputSchema 内的键是用户 JSON 模式，并且绝不能重命名。
#
_MCP_TOOL_WIRE_KEYS: Final[dict[str, str]] = {
    "input_schema": "inputSchema",
    "output_schema": "outputSchema",
    "meta": "_meta",
}
_MCP_NESTED_WIRE_KEYS: Final[dict[str, dict[str, str]]] = {
    "annotations": {
        "read_only_hint": "readOnlyHint",
        "destructive_hint": "destructiveHint",
        "idempotent_hint": "idempotentHint",
        "open_world_hint": "openWorldHint",
    },
    "execution": {"task_support": "taskSupport"},
    "icons": {"mime_type": "mimeType"},
}


def _mcp_tool_to_wire_keys(data: Any) -> Any:
    """将已序列化 mcp.types.Tool 规范化为 MCP 规格的 camelCase 键。"""
    if not isinstance(data, dict):
        return data
    out = {_MCP_TOOL_WIRE_KEYS.get(k, k): v for k, v in data.items()}
    for key, renames in _MCP_NESTED_WIRE_KEYS.items():
        value = out.get(key)
        if isinstance(value, dict):
            out[key] = {renames.get(k, k): v for k, v in value.items()}
        elif isinstance(value, list):
            out[key] = [
                {renames.get(k, k): v for k, v in item.items()}
                if isinstance(item, dict)
                else item
                for item in value
            ]
    return out


# 注意我们不定义 MCPToolAction 因为它是
# 将是从 MCP 工具模式动态创建的 Pydantic BaseModel。 它将作为“tool.action_type”提供。
#


def to_camel_case(s: str) -> str:
    parts = re.split(r"[_\-\s]+", s)
    return "".join(word.capitalize() for word in parts if word)


class MCPToolExecutor(ToolExecutor):
    """MCP 工具的执行器。"""

    tool_name: str
    client: MCPClient
    timeout: float

    def __init__(
        self,
        tool_name: str,
        client: MCPClient,
        timeout: float = MCP_TOOL_TIMEOUT_SECONDS,
    ):
        self.tool_name = tool_name
        self.client = client
        self.timeout = timeout

    @observe(name="MCPToolExecutor.call_tool", span_type="TOOL")
    async def call_tool(self, action: MCPToolAction) -> MCPToolObservation:
        """使用已连接的客户端执行MCP 工具调用。

        如果客户端会话已丢失（e.g.，由于短暂的服务器错误，例如 HTTP 503），请在失败之
        前尝试重新连接一次。 这可以防止单个瞬态错误永久禁用对话剩余部分的
        所有 MCP 工具。
        """
        if not self.client.is_connected():
            if self.client._closed:
                return MCPToolObservation.from_text(
                    text=(
                        f"MCP client not connected for tool '{self.tool_name}'. "
                        "The client has been closed and cannot be reconnected."
                    ),
                    is_error=True,
                    tool_name=self.tool_name,
                )
            logger.info(
                f"MCP client not connected for tool '{self.tool_name}'; "
                "attempting reconnection before failing."
            )
            try:
                await self.client.connect()
            except Exception as exc:
                return MCPToolObservation.from_text(
                    text=(
                        f"MCP client not connected for tool '{self.tool_name}'. "
                        f"Reconnection attempt failed: {exc}"
                    ),
                    is_error=True,
                    tool_name=self.tool_name,
                )
        try:
            logger.debug(
                f"Calling MCP tool {self.tool_name} with args: {action.model_dump()}"
            )
            result: mcp.types.CallToolResult = await self.client.call_tool_mcp(
                name=self.tool_name, arguments=action.to_mcp_arguments()
            )
            return MCPToolObservation.from_call_tool_result(
                tool_name=self.tool_name, result=result
            )
        except Exception as e:
            error_msg = f"Error calling MCP tool {self.tool_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return MCPToolObservation.from_text(
                text=error_msg,
                is_error=True,
                tool_name=self.tool_name,
            )

    def __call__(
        self,
        action: MCPToolAction,
        conversation: "LocalConversation | None" = None,
    ) -> MCPToolObservation:
        """执行MCP工具调用。

        如果提供了对话，机密在动作数据中的引用（e.g、$VAR、${VAR}、${VAR:-default}）
        在调用 MCP 服务器之前会使用对话的机密注册表扩展
        。
        """
        # 展开操作数据中的机密引用 (e.g.$VAR, ${VAR}, ${VAR:-default})，镜像终端命令在执
        # 行前如何解析机密。 重复使用与 MCP 配置扩展相同的扩展器。
        #
        expanded_action = action
        if conversation is not None:
            try:
                secret_registry = conversation.state.secret_registry
                expanded_data = expand_variable_references(
                    action.data,
                    get_secret=secret_registry.get_secret_value,
                    check_env=False,  # 仅机密 — 从不扩展主机环境变量
                    support_unbraced=True,  # 也像 shell 一样解析 $VAR
                )
                expanded_action = action.model_copy(update={"data": expanded_data})
            except Exception as e:
                logger.warning(f"Failed to expand secrets in MCP tool action: {e}")
                # 如果扩展失败，则返回到原始操作

        try:
            observation = self.client.call_async_from_sync(
                self.call_tool, action=expanded_action, timeout=self.timeout
            )
            # 观测结果输出中的掩码机密
            return self._mask_observation(observation, conversation)
        except TimeoutError:
            error_msg = (
                f"MCP tool '{self.tool_name}' timed out after {self.timeout} seconds. "
                "The tool server may be unresponsive or the operation is taking "
                "too long. Consider retrying or using an alternative approach."
            )
            logger.error(error_msg)
            return MCPToolObservation.from_text(
                text=error_msg,
                is_error=True,
                tool_name=self.tool_name,
            )

    def _mask_observation(
        self,
        observation: MCPToolObservation,
        conversation: "LocalConversation | None" = None,
    ) -> MCPToolObservation:
        """对观测结果内容应用自动机密屏蔽。"""
        if conversation is None:
            return observation

        try:
            secret_registry = conversation.state.secret_registry
            # 文本块中的掩码机密； 不受影响地传递图像块。
            masked_content = [
                TextContent(text=secret_registry.mask_secrets_in_output(block.text))
                if isinstance(block, TextContent) and block.text
                else block
                for block in observation.content
            ]
            return observation.model_copy(update={"content": masked_content})
        except Exception as e:
            logger.warning(f"Failed to mask secrets in MCP observation: {e}")
            return observation

    def close(self) -> None:
        self.client.sync_close()


_MCP_ACTION_TYPE_CACHE_MAX: Final[int] = 512
# LRU-bounded：以 (name, 模式) 为键，因此模式不断变化的工具不再无限制地增长此缓存。 由锁
# 保护，因为 MCP 工具调用可以通过并行工具执行器同时验证。
#
_mcp_dynamic_action_type: OrderedDict[tuple[str, str], type[Schema]] = OrderedDict()
_mcp_dynamic_action_type_lock = threading.Lock()


def _create_mcp_action_type(action_type: mcp.types.Tool) -> type[Schema]:
    """为模式中的 MCP 工具操作动态创建 Pydantic 模型。

    我们从“模式”创建而不是：
    - "MCPToolAction"，因为 MCPToolAction 的 "data" 字段会包装所有动态字段，而此处不
    需要这种包装。
    - “Action”是因为 Action 继承自 DiscriminatedUnionMixin，其中包含此处不需要的
    `kind` 字段。

    .from_mcp_schema 只是定义了一个新的 Pydantic 模型类，该类继承自给定的基类。 我们
    可能想使用返回的类将字段定义转换为OpenAI工具模式。
    """

    cache_key = (
        action_type.name,
        json.dumps(action_type.inputSchema, sort_keys=True, separators=(",", ":")),
    )
    with _mcp_dynamic_action_type_lock:
        mcp_action_type = _mcp_dynamic_action_type.get(cache_key)
        if mcp_action_type:
            _mcp_dynamic_action_type.move_to_end(cache_key)
            return mcp_action_type

        model_name = f"MCP{to_camel_case(action_type.name)}Action"
        mcp_action_type = Schema.from_mcp_schema(model_name, action_type.inputSchema)
        _mcp_dynamic_action_type[cache_key] = mcp_action_type
        if len(_mcp_dynamic_action_type) > _MCP_ACTION_TYPE_CACHE_MAX:
            _mcp_dynamic_action_type.popitem(last=False)
        return mcp_action_type


class MCPToolDefinition(ToolDefinition[MCPToolAction, MCPToolObservation]):
    """MCP 包装 MCP 客户端并提供工具功能的工具。"""

    mcp_tool: mcp.types.Tool = Field(description="The MCP tool definition.")

    @field_validator("mcp_tool", mode="before")
    @classmethod
    def _read_either_mcp_spelling(cls, v: Any) -> Any:
        return _mcp_tool_to_wire_keys(v)

    @field_serializer("mcp_tool", mode="wrap")
    def _write_mcp_wire_spelling(
        self, v: mcp.types.Tool, handler: SerializerFunctionWrapHandler
    ):
        # 已持久化事件比已解决的 MCP 重大事件持续时间更长； 始终写下规范的线路名称，以便
        # 每个 MCP 版本都可以读回它们。 没有返回注释，因此 OpenAPI 模式继续引用
        # mcp.types.Tool。
        #
        return _mcp_tool_to_wire_keys(handler(v))

    @property
    def name(self) -> str:  # type: ignore[override]
        """返回 MCP 工具名称而不是类名称。"""
        return self.mcp_tool.name

    def __call__(
        self,
        action: Action,
        conversation: "LocalConversation | None" = None,  # noqa: ARG002
    ) -> Observation:
        """使用 MCP 客户端执行工具操作。

        我们动态创建一个新的MCPToolAction类，使用工具的输入模式来验证操作。

        Args:
            action: 要执行的操作。

        Returns:
            观测结果是执行操作的结果。
        """
        if not isinstance(action, MCPToolAction):
            raise ValueError(
                f"MCPTool can only execute MCPToolAction actions, got {type(action)}",
            )
        assert self.name == self.mcp_tool.name
        mcp_action_type = _create_mcp_action_type(self.mcp_tool)
        try:
            mcp_action_type.model_validate(action.data)
        except ValidationError as e:
            # 表面验证错误为观测结果，而不是崩溃
            error_msg = f"Validation error for MCP tool '{self.name}' args: {e}"
            logger.error(error_msg, exc_info=True)
            return MCPToolObservation.from_text(
                text=error_msg,
                is_error=True,
                tool_name=self.name,
            )

        return super().__call__(action, conversation)

    def action_from_arguments(self, arguments: dict[str, Any]) -> MCPToolAction:
        """创建一个 MCPToolAction 从解析的早期参数验证。

        我们验证原始参数是否符合  MCP 工具的输入模式这里如此 Agent._get_action_event
        can catch
        ValidationError 和表面 AgentErrorEvent 回到模型，而不是在工具执行过程中后期崩
        溃。 成功时，我们返回
        MCPToolAction 带有 sanitized 参数。

        Args:
            arguments: 来自工具调用的解析参数。

        Returns:
            的 MCPToolAction 带有从参数填充的数据的实例。

        Raises:
            ValidationError: 如果参数不符合工具模式。
        """
        tool_arguments, structured_output = self._split_response_arguments(arguments)
        prefiltered_args = {
            key: value for key, value in tool_arguments.items() if value is not None
        }
        # 针对动态创建的操作类型进行验证（来自 MCP 模式）
        mcp_action_type = _create_mcp_action_type(self.mcp_tool)
        validated = mcp_action_type.model_validate(prefiltered_args)
        # 使用 exclude_none 避免将空值注入回调用排除 DiscriminatedUnionMixin 字段（e.g.,
        #  'kind'），因为它们是 OpenHands 内部的而不是 MCP 工具模式的一部分
        #
        exclude_fields = set(DiscriminatedUnionMixin.model_fields.keys()) | set(
            DiscriminatedUnionMixin.model_computed_fields.keys()
        )
        sanitized = validated.model_dump(
            by_alias=True,  # 使用 MCP 参数名称 (e.g. “种类”），而不是内部字段。
            exclude_none=True,
            exclude=exclude_fields,
        )
        action = MCPToolAction(data=sanitized)
        action._structured_output = structured_output
        return action

    @classmethod
    def create(
        cls,
        mcp_tool: mcp.types.Tool,
        mcp_client: MCPClient,
    ) -> Sequence["MCPToolDefinition"]:
        try:
            annotations = (
                ToolAnnotations.model_validate(
                    mcp_tool.annotations.model_dump(exclude_none=True, by_alias=True)
                )
                if mcp_tool.annotations
                else None
            )

            tool_instance = cls(
                description=mcp_tool.description or "No description provided",
                action_type=MCPToolAction,
                observation_type=MCPToolObservation,
                annotations=annotations,
                meta=mcp_tool.meta,
                executor=MCPToolExecutor(tool_name=mcp_tool.name, client=mcp_client),
                # pass-through fields (enabled by **extra in Tool.create)
                mcp_tool=mcp_tool,
            )
            return [tool_instance]
        except ValidationError as e:
            logger.error(
                f"Validation error creating MCPTool for {mcp_tool.name}: "
                f"{e.json(indent=2)}",
                exc_info=True,
            )
            raise e

    def to_mcp_tool(
        self,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if input_schema is not None or output_schema is not None:
            raise ValueError("MCPTool.to_mcp_tool does not support overriding schemas")

        return super().to_mcp_tool(
            input_schema=self.mcp_tool.inputSchema,
            output_schema=self.observation_type.to_mcp_schema()
            if self.observation_type
            else None,
        )

    def _get_tool_schema(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """从原始的 MCP inputSchema 构建面向 LLM 的模式。

        父实现通过动态创建的 Pydantic 模型进行往返，其 ``py_type()`` 映射
        ``"type": "object"`` 到
        ``dict[str, Any]``，丢失嵌套的 ``properties`` 和 ``required`` 字段。 对于MCP
        个工具，权威的模式已经由MC
        P服务器提供，所以我们从一个深拷贝开始，并直接注入OpenHands特定字段
        (``security_risk``，``summary``)。

        See: https://github.com/OpenHands/software-agent-sdk/issues/3955
        """
        schema = copy.deepcopy(self.mcp_tool.inputSchema)
        # 解析任何 $ref / anyOf 节点（在原始 MCP 模式中不太可能，但保持契约与父实现一致
        # ）。
        #
        schema = _process_schema_node(schema, schema.get("$defs", {}))

        schema.setdefault("properties", {})

        # 适用时注入 security_risk（与父级相同的防护）。
        add_security_risk_prediction = add_security_risk_prediction and (
            self.annotations is None or (not self.annotations.readOnlyHint)
        )
        if add_security_risk_prediction:
            schema["properties"]["security_risk"] = {
                "type": "string",
                "description": (
                    "The LLM's assessment of the safety risk of this action."
                ),
                "enum": [e.value for e in risk.SecurityRisk],
            }

        # 除非 MCP 工具已经声明了一个，否则注入摘要。
        if "summary" not in schema["properties"]:
            schema["properties"]["summary"] = {
                "type": "string",
                "description": (
                    "A concise summary (approximately 10 words) "
                    "describing what this specific action does. "
                    "Focus on the key operation and target. "
                    "Example: 'List all Python files in current "
                    "directory'"
                ),
            }

        schema = self._merge_response_schema(schema)
        _prioritize_schema_fields(
            schema=schema,
            priority=("security_risk", "summary"),
        )
        return schema

    def to_openai_tool(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> ChatCompletionToolParam:
        """将工具转换为 OpenAI 工具。

        模式生成由：meth:`_get_tool_schema` 处理，它直接从原始 MCP 构建面向 LLM 的模
        式
        ``inputSchema`` 保留嵌套对象结构。 动态Pydantic模型仍然用于运行时验证
        ：甲基：`__call__` / ：甲基：`action_from_arguments`。

        Args:
            add_security_risk_prediction: 是否添加`security_risk`字段
                到 LLM 的动作模式进行预测。 这对于可能存在安全风险的工具很有用，因此
                LLM可以在调用该工具之前推断出风险级别。
        """
        if action_type is not None:
            raise ValueError(
                "MCPTool.to_openai_tool does not support overriding action_type"
            )

        assert self.name == self.mcp_tool.name
        return super().to_openai_tool(
            add_security_risk_prediction=add_security_risk_prediction,
        )

    def to_responses_tool(
        self,
        add_security_risk_prediction: bool = False,
        action_type: type[Schema] | None = None,
    ) -> FunctionToolParam:
        """将工具转换为 Responses API 功能工具。

        模式生成由：meth:`_get_tool_schema` 处理，它直接从原始 MCP 构建面向 LLM 的模
        式
        ``inputSchema`` 保留嵌套对象结构。

        Args:
            add_security_risk_prediction: 是否添加`security_risk`字段
                到 LLM 的动作模式进行预测。 这对于可能存在安全风险的工具很有用，因此
                LLM可以在调用该工具之前推断出风险级别。
        """
        if action_type is not None:
            raise ValueError(
                "MCPTool.to_responses_tool does not support overriding action_type"
            )

        assert self.name == self.mcp_tool.name
        return super().to_responses_tool(
            add_security_risk_prediction=add_security_risk_prediction,
        )
