"""API 设置端点的请求和响应模型。

这些模型定义了之间的合同 SDK 客户端和智能体服务器设置端点。 它们在定义 SDK 因此，这两
个包可以共享它们，而无需循环依赖SDK 不能从...导入智能体-server
, but 智能体服务器可以导入 SDK).

服务器端使用：
    智能体-服务器导入这些模型并将它们用作FastAPI response_model。

客户端使用：
    RemoteWorkspace 使用这些模型来验证设置 APIs 的响应。 使用类型化的访问器方法(
    ``get_agent_settings()``)
    ``get_conversation_settings()``）将原始字典解析为类型化模型。

字典字段注意事项：
    ``SettingsResponse`` 将 ``agent_settings`` 和 ``conversation_settings`` 保留为字
    典，因为服务器需
    要通过序列化上下文控制机密如何变为已序列化（明文/加密/编辑）。 输入的 Pydantic 字
    段将在 FastAPI 自动 JSON 序列化期间丢失此上下文。

    ``agent_settings`` 字典有一个单独的 OpenAPI 模式，它公开已知的契约字段，例如
    ``mcp_config``，同时保留扩展表面。 需要运行
    时类型安全的客户端应该使用访问器方法来验证字典``AgentSettingsConfig``和
    ``ConversationSettings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    RootModel,
    SecretStr,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from openhands.sdk.llm.llm_profile_store import PROFILE_NAME_PATTERN
from openhands.sdk.mcp.config import MCPAuthCredential, MCPServer, MCPTransport


# AgentProfile 的稳定 id 是 UUID（指针目标）； 拒绝 HTTP 层的格式错误的值，镜像
# ``active_profile`` 的名称模式。
#
UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


if TYPE_CHECKING:
    from .model import AgentSettingsConfig, ConversationSettings


# ── 设置API型号────────────────────────────────────────────────────


class MCPConfig(RootModel[dict[str, MCPServer]]):
    """由稳定服务器名称键入的规范已持久化 MCP 服务器映射。"""


class MCPServerPatch(BaseModel):
    """适用于一台已持久化 MCP 服务器的稀疏 RFC 7386 合并补丁。"""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=1)
    transport: MCPTransport | None = None
    command: str | None = Field(default=None, min_length=1)
    args: list[str] | None = None
    env: dict[str, SecretStr | None] | None = None
    cwd: str | None = None
    description: str | None = None
    icon: str | None = None
    timeout: float | None = None
    sse_read_timeout: float | None = None
    keep_alive: bool | None = None
    headers: dict[str, SecretStr | None] | None = None
    auth: MCPAuthCredential | None = None
    enabled: bool | None = Field(
        default=None,
        description=(
            "Switch the server off (false) or back on (true) without touching "
            "the rest of its configuration. A null clears the override, which "
            "restores the canonical default (enabled)."
        ),
    )


class MCPConfigPatch(RootModel[dict[str, MCPServerPatch | None]]):
    """稀疏MCP地图补丁； null 映射值删除该指定服务器。"""


class _AgentSettingsContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int | None = Field(default=None, ge=1)
    agent_kind: Literal["openhands", "acp"] | None = None
    mcp_config: MCPConfig


class _AgentSettingsPatchContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    mcp_config: MCPConfigPatch | None = None


class _AgentSettingsJsonSchema:
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return handler(_AgentSettingsContract.__pydantic_core_schema__)


class _AgentSettingsPatchJsonSchema:
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        return handler(_AgentSettingsPatchContract.__pydantic_core_schema__)


AgentSettingsDict = Annotated[dict[str, Any], _AgentSettingsJsonSchema]
AgentSettingsPatchDict = Annotated[dict[str, Any], _AgentSettingsPatchJsonSchema]


class SettingsResponse(BaseModel):
    """GET /api/settings. 的响应模型

    包含完整的设置载荷，包括智能体配置、会话设置、活动 LLM 角色、前端所有者设置，以及
    一个标志，指示 LLM API 键是否设置。

    ``agent_settings`` 和 ``conversation_settings`` 字段是原始字典，因为服务器通过上
    下文控制机密序列化。 使用验证的类型化
    访问器方法：

    示例：:

        response = SettingsResponse.model_validate(api_response.json())
        agent = response.get_agent_settings()  # 返回 AgentSettingsConfig
        conv = response.get_conversation_settings()  # 返回 ConversationSettings

    ``misc_settings`` 是前端拥有的数据的不透明容器，智能体服务器保留但不解释该数据 -
    请参阅文档字符串
    ：类：`PersistedSettings.misc_settings`。
    """

    agent_settings: AgentSettingsDict
    conversation_settings: dict[str, Any]
    llm_api_key_is_set: bool
    active_profile: str | None = Field(
        default=None,
        description="Name of the currently active LLM profile, if one is selected.",
    )
    active_agent_profile_id: str | None = Field(
        default=None,
        description="Stable id of the currently active AgentProfile, if one is set.",
    )
    active_meta_profile: str | None = Field(
        default=None,
        description="Name of the currently active meta-profile, if one is selected.",
    )
    misc_settings: dict[str, Any] = Field(default_factory=dict)

    def get_agent_settings(self) -> AgentSettingsConfig:
        """将 ``agent_settings`` 解析并验证为类型化模型。

        Returns:
            验证的智能体设置为 ``OpenHandsAgentSettings`` 或 ``ACPAgentSettings``，具
            体取决于
            ``agent_kind`` 鉴别器。
        """
        from .model import validate_agent_settings

        return validate_agent_settings(self.agent_settings)

    def get_conversation_settings(self) -> ConversationSettings:
        """将 ``conversation_settings`` 解析并验证为类型化模型。

        Returns:
            已验证的对话设置。
        """
        from .model import ConversationSettings

        return ConversationSettings.from_persisted(self.conversation_settings)


class SettingsUpdateRequest(BaseModel):
    """请求 PATCH /api/settings. 的模型

    支持通过与现有设置深度合并的 diff 对象进行部分更新。 ``misc_settings_diff`` 深度
    合并到已持久化 ``misc_settings`` 块
    中，其语义与
    ``agent_settings_diff`` 和 ``conversation_settings_diff``：嵌套字典递归合并，列表
    被批量替换而不是合并。 由于
     ``misc_settings`` 对智能体服务器来说是不透明的，因此调用者需要对其存储的内容的形
     状负责。
    """

    agent_settings_diff: AgentSettingsPatchDict | None = None
    conversation_settings_diff: dict[str, Any] | None = None
    misc_settings_diff: dict[str, Any] | None = None
    active_profile: str | None = Field(
        default=None,
        pattern=PROFILE_NAME_PATTERN,
        description="Name of the active LLM profile to persist; null clears it.",
    )
    active_agent_profile_id: str | None = Field(
        default=None,
        pattern=UUID_PATTERN,
        description="Stable id of the active AgentProfile to persist; null clears it.",
    )
    active_meta_profile: str | None = Field(
        default=None,
        pattern=PROFILE_NAME_PATTERN,
        description="Name of the active meta-profile to persist; null clears it.",
    )


# ── 机密 API 型号 ────────────────────────────────────────────────────


class SecretItemResponse(BaseModel):
    """机密项的响应模型（无值）。

    用于列表响应以及作为创建/更新操作的响应。
    """

    name: str
    description: str | None = None


class SecretsListResponse(BaseModel):
    """GET /api/settings/secrets. 的响应模型

    列出所有可用的机密及其名称和描述。 值永远不会包含在列表响应中。
    """

    secrets: list[SecretItemResponse]


class SecretCreateRequest(BaseModel):
    """请求 PUT /api/settings/secrets. 的模型

    使用给定名称和值创建或更新机密。
    """

    name: str
    value: SecretStr
    description: str | None = None
