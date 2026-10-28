"""Pydantic 个模型用于已持久化设置和机密。

这些模型模仿了使用的结构 OpenHands 一致性应用服务器，允许智能体- 用于独立运行或作为云
的替代品使用的服务器 API'settings/secrets' 端点。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from openhands.sdk.settings import (
    AgentSettingsConfig,
    ConversationSettings,
    OpenHandsAgentSettings,
    apply_agent_settings_diff,
    default_agent_settings,
    validate_agent_settings,
)
from openhands.sdk.utils.pydantic_secrets import serialize_secret, validate_secret


class _SecretProbeCipher:
    """无需真实密钥即可标记机密序列化的假密码。

    通过 ``context={"cipher": probe}`` 这迫使每个机密字段的序列化器沿着“加密”分支（见
     ``resolve_expose_mode``)
    , 重用真实序列化检测管道机密-使用字段而不是手走模型进行操作 ``SecretStr`` 实例。
    这对于诸如的领域很重要
    ``AgentContext.secrets``[whose] 空心字符串的条目是裸露的 ``str`` at REST 仅能成为
    机密在自己的领域内序列化器在dum
    p时间 -- 值类型遍历无法看到这一点，但重用管道可以。
    """

    def __init__(self) -> None:
        self.found = False

    def try_decrypt_str(self, raw: str) -> str | None:  # noqa: ARG002
        return None

    def encrypt(self, value: SecretStr) -> str:
        if value.get_secret_value():
            self.found = True
        return ""


def _contains_secret_value(model: BaseModel) -> bool:
    """检查序列化 `model` 是否会触及任何包含机密的字段。"""
    probe = _SecretProbeCipher()
    model.model_dump(mode="json", context={"cipher": probe})
    return probe.found


class SettingsUpdatePayload(TypedDict, total=False):
    """为 PersistedSettings.update() 方法键入载荷。

    ``agent_settings_diff`` 通过：func:`apply_agent_settings_diff` 应用，完整遵循 RFC
     7386 的合并补丁
    语义；任意顶层或嵌套键的值为 ``None`` 时，都会删除该键，使对应字段恢复默认值。

    ``conversation_settings_diff`` 和 ``misc_settings_diff`` 使用
    :func:`_deep_merge`: 嵌套映射递归合并，``None`` *inside* a
    嵌套映射会删除该条目，但顶级字段上的 ``None`` 会像以前一样流向验证。

    ``misc_settings_diff`` 深度合并到已持久化 ``misc_settings`` 块中。 智能体-服务器
    将``misc_settings``视为
    不透明的前端拥有的数据（它保留并合并，但不解释），因此客户端选择的任何形状都是有
    效的； 列表被深度合并大规模取代。
    """

    agent_settings_diff: dict[str, Any]
    conversation_settings_diff: dict[str, Any]
    misc_settings_diff: dict[str, Any]
    active_profile: str | None
    active_agent_profile_id: str | None
    active_meta_profile: str | None


def _deep_merge(
    base: dict[str, Any],
    overlay: dict[str, Any],
    *,
    unset_nulls: bool = False,
) -> dict[str, Any]:
    """递归地将 ``overlay`` 合并到 ``base`` 中。

    - 嵌套字典被递归合并。
    - **在嵌套映射内部**，``None``值**删除**该键——普通深度合并所缺少的“未设置”原语。
    它让一个
      ``PATCH /api/settings`` diff 删除单个映射条目（一个 MCP
      ``env`` / ``headers`` 键）无需往返整个地图：:

          {"agent_settings_diff":
              {"mcp_config": {"svc": {"env": {"STALE_KEY": null}}}}}

    - **在顶层**（像``confirmation_mode``一样的设置*字段*），``None``保持原样并流向模
    型验证——与该原语存在之前完全相同。 那么流浪
      ``{"confirmation_mode": null}`` 仍然会大声失败 (422)，而不是默默地将字段重置为
      其默认值。 这个范围界定是经过深思熟虑的：
      ``unset`` 用于 * 映射内的 * 条目，而不是用于清空整个字段。
    - 对于任何其他标量/列表值，覆盖获胜。

    对于顶级调用，``unset_nulls`` 是 ``False``，对于每个递归（嵌套）调用，``True`` 是
    这样的——这就是上面绘制字段与条目线的原因。

    **缺失的键** ``base``的覆盖值是一个字典时，``null``字典内部的任何条目都将被存储原
    样，而不是被处理为删除。 这是有意为之——你不能从一个不存在的
    图中删除一条记录——但这意味着“初始化一个新的图并清除其中的一个键”在一次差异中不会
    移除 null。 下游验证处理结果值。
    """
    result = dict(base)
    for key, value in overlay.items():
        if value is None and unset_nulls:
            # 嵌套映射条目：null 成员删除键（如果不存在则无操作）。
            result.pop(key, None)
        elif (
            key in result and isinstance(result[key], dict) and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value, unset_nulls=True)
        else:
            # 顶级 null (unset_nulls=False) 位于此处：按原样设置并让模型验证决定（保留预
            # 先存在的行为）。
            #
            result[key] = value
    return result


PERSISTED_SETTINGS_SCHEMA_VERSION = 6


class PersistedSettings(BaseModel):
    """Agent Server 的已持久化设置。

    智能体设置（LLM 配置、MCP 配置、上下文压缩器）位于 ``agent_settings`` 中。 对话设
    置 (max_iterations,
    confirmation_mode) 实时存在
    ``conversation_settings``.

    ``active_profile`` 字段跟踪最后激活的 LLM 配置文件，允许前端显示当前正在使用的配
    置文件。

    ``misc_settings`` 字段是一个不透明的字典，智能体服务器代表前端保留。 智能体-服务
    器从不读取其内容，也没有模式。 客户端可以自由存储他们需要的任何
     JSON-可序列化结构（e.g. 应用程序/UI 首选项、用于对话中提交的 git 身份等）。

    ``misc_settings`` 内的命名空间是“从不读取”规则的记录例外：
    ``misc_settings.telemetry`` 包含 ``consent``（
    ``granted``/``denied``/``unset``) 和可选的 ``managed`` 标志。 前端仍然拥有该值；
    智能体-服务器仅读取它，以决定是否
    可以提供产品分析。 容器中的任何其他内容都不会被解释。
    """

    schema_version: int = Field(
        default=PERSISTED_SETTINGS_SCHEMA_VERSION,
        description="Persisted settings file schema version.",
    )

    agent_settings: AgentSettingsConfig = Field(default_factory=default_agent_settings)
    conversation_settings: ConversationSettings = Field(
        default_factory=ConversationSettings
    )
    active_profile: str | None = Field(
        default=None,
        description="Name of the currently active LLM profile.",
    )
    active_agent_profile_id: str | None = Field(
        default=None,
        description=(
            "Stable id of the currently active AgentProfile. Distinct from "
            "active_profile (the active LLM profile name); additive with a "
            "default, so older settings files load with this as None."
        ),
    )
    active_meta_profile: str | None = Field(
        default=None,
        description="Name of the currently active meta-profile used for "
        "intelligent model routing.",
    )
    misc_settings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Opaque dict the agent-server persists on behalf of the frontend. "
            "Updated through misc_settings_diff (deep-merged); contents are "
            "never read or validated by the agent-server."
        ),
    )

    model_config = ConfigDict(populate_by_name=True)

    @property
    def llm_api_key_is_set(self) -> bool:
        """检查是否配置了LLMAPI键。"""
        if not isinstance(self.agent_settings, OpenHandsAgentSettings):
            return False
        raw = self.agent_settings.llm.api_key
        if raw is None:
            return False
        secret_value = (
            raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)
        )
        return bool(secret_value and secret_value.strip())

    @property
    def has_any_secret(self) -> bool:
        """检查这些设置是否在任何地方包含任何机密值。

        比 ``llm_api_key_is_set`` 更广泛：遍历整个 ``agent_settings`` 树（MCP 服务器
        环境/标头、
        ``critic_api_key``、提供商信用、
        ``agent_context.secrets``, ...) 而不是检查固定字段列表，因此在添加新的机密字
        段时它保持正确。
        """
        return _contains_secret_value(self.agent_settings)

    def update(
        self,
        payload: SettingsUpdatePayload,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """应用嵌套字典中的一批更改。

        接受 ``agent_settings_diff``、``conversation_settings_diff``、
        ``active_profile`` 和 ``active_agent_profile_id`` 用于部分更新。

        ``agent_settings_diff`` 通过：func:`apply_agent_settings_diff`: RFC 7386 具有
        种类切换感知
        的合并补丁语义来应用。 当
        ``agent_kind`` 更改时，差异将应用到目标变体的新基础上。 同类差异在变体中深度
        合并。 A
        任何级别的 ``None`` 值都会删除该键并将其重置为默认值。

        ``conversation_settings_diff`` 在嵌套映射内使用：func:`_deep_merge`: ``None``
         删除该条目；
        ``None`` 顶级字段流向验证。

        线程安全：
            此方法是不线程安全，用于并发内存中更新。 对 ``agent_settings`` 和
            ``conversation_settings`` 的赋值不
            是原子的。 然而，路由器通过 ``store.update()`` 包装调用，它使用文件锁定来
            防止 I/O 层的并发更新。 多个
            ``PersistedSettings`` 实例应该不在线程之间共享，无需外部同步。

        原子性：
            两个更新都会在任何突变发生之前进行验证。 如果任一验证失败，则该对象保持不
            变。

        Raises:
            ValueError: 如果验证失败（已清理以避免机密泄漏）。
        """
        agent_update = payload.get("agent_settings_diff")
        conv_update = payload.get("conversation_settings_diff")

        # 第 1 阶段：在任何突变之前验证所有更新
        new_agent: AgentSettingsConfig | None = None
        new_conv: ConversationSettings | None = None
        conv_merged: dict | None = None

        try:
            if isinstance(agent_update, dict):
                try:
                    new_agent = apply_agent_settings_diff(
                        self.agent_settings, agent_update, context=context
                    )
                except Exception as e:
                    # 使用“from None”来中断异常链 - 原始异常可能在 Pydantic 错误中包含机
                    # 密值
                    #
                    raise ValueError(
                        f"Failed to update agent settings: {type(e).__name__}"
                    ) from None

            if isinstance(conv_update, dict):
                conv_merged = _deep_merge(
                    self.conversation_settings.model_dump(mode="json"),
                    conv_update,
                )
                try:
                    new_conv = ConversationSettings.from_persisted(conv_merged)
                except Exception as e:
                    # 使用“from None”打破异常链 - 见上文
                    raise ValueError(
                        f"Failed to update conversation settings: {type(e).__name__}"
                    ) from None

            # ``misc_settings`` 是不透明的：没有模式验证的深度合并。 智能体服务器不理解
            # 其中的内容，``misc_settings``不是一个机密容器——因此，合并字典直接存储，而
            # 不是像``conversation_settings``使用的post-commit清空那样。
            #
            misc_update = payload.get("misc_settings_diff")
            new_misc: dict[str, Any] | None = None
            if isinstance(misc_update, dict):
                new_misc = _deep_merge(self.misc_settings, misc_update)

            # 第 2 阶段：自动应用经过验证的更改
            if new_agent is not None:
                self.agent_settings = new_agent
            if new_conv is not None:
                self.conversation_settings = new_conv
            if new_misc is not None:
                self.misc_settings = new_misc

            # 如果明确提供则更新指针（包括要清除的 None）
            if "active_profile" in payload:
                self.active_profile = payload["active_profile"]
            if "active_agent_profile_id" in payload:
                self.active_agent_profile_id = payload["active_agent_profile_id"]

            # 如果明确提供，则更新 active_meta_profile（包括 None)
            if "active_meta_profile" in payload:
                self._apply_active_meta_profile(payload["active_meta_profile"])

            # 即使仅 ``agent_settings`` 发生更改，也强制执行不变量：切换到无法附加布线工
            # 具的智能体变体 (e.g. ACP) 不得留下过时的顶级 ``active_meta_profile`` 声明
            # 路由处于活动状态。 （当活动已经匹配时，无操作。）
            #
            self._clear_active_meta_profile_if_unsupported()
        finally:
            # 清除 conv_merged 以最小化明文暴露窗口
            if conv_merged is not None:
                conv_merged.clear()

    def _agent_supports_routing(self) -> bool:
        """当前智能体变体是否可以附加布线工具。

        OpenHands 智能体设置公开 ``active_meta_profile`` /
        ``enable_classify_and_switch_llm_tool``; ACP（和任何其他）变体不会也永远不会
        附加：class：
        `ClassifyAndSwitchLLMTool`。
        """
        return "active_meta_profile" in type(self.agent_settings).model_fields

    def _apply_active_meta_profile(self, name: str | None) -> None:
        """设置 ``active_meta_profile`` 并将其传播到 agent_settings。

        ``agent_settings`` 中的传播使得路由工具能够在基于这些设置的智能体中运行（就像
        激活一个预设会将 LLM 贴合到
        ``agent_settings`` 一样）。

        顶层字段是一个嵌套状态的严格面纱，而不是一种最佳努力的提示：如果当前智能体变
        体无法附上路由工具 (e.g。 ACP)，请求被丢弃并且外观被清除，因此已持久化
        状态永远不会声明没有会话可以使用的活动路由器。
        """
        if not self._agent_supports_routing():
            self.active_meta_profile = None
            return
        self.active_meta_profile = name
        self.agent_settings = self.agent_settings.model_copy(
            update={
                "active_meta_profile": name,
                "enable_classify_and_switch_llm_tool": name is not None,
            }
        )

    def _clear_active_meta_profile_if_unsupported(self) -> None:
        """当智能体变体无法支持路由时清除外观。

        保护智能体-kind-switch 路径：将 ``agent_settings`` 更改为非路由变体 (e.g. ACP
        ）当元配置文件处于活动状态时，否则会
        使顶级 ``active_meta_profile`` 过时。
        """
        if not self._agent_supports_routing() and self.active_meta_profile is not None:
            self.active_meta_profile = None

    @classmethod
    def from_persisted(
        cls, data: Any, *, context: dict[str, Any] | None = None
    ) -> PersistedSettings:
        """加载已持久化设置。

        模式-版本历史：

        - **v1**: ``agent_settings`` + ``conversation_settings`` 加
          ``active_profile``.
        - **v2**: 添加不透明的 ``misc_settings`` 容器。
        - **v3**: 嵌套 ``agent_settings`` 升级到模式 v6（删除了已删除的
        ``llm.modify_params`` 字段）。 嵌套
        的载荷通过 ``validate_agent_settings`` 迁移
          ``_normalize_inputs``; 顶层凹凸使文件模式与嵌套形状变化保持同步。
        - **v4**: 嵌套 ``agent_settings`` 升级到模式 v7（从 ACP 设置中删除了已弃用
        ``llm``）。
        - **v5**: 嵌套 ``agent_settings`` 升级到模式 v8（已退役的工具开关合并到
        ``tools`` 中）。
        - **v6** (current): 嵌套 ``agent_settings`` 升级到模式 v9（删除了已弃用实时输
        入路径； 已持久化输入仍然迁移）。
        """
        if not isinstance(data, dict):
            return cls.model_validate(data, context=context)

        payload = dict(data)
        version = payload.get("schema_version", 0) or 0
        if type(version) is not int:
            raise ValueError("PersistedSettings schema_version must be an integer")
        if version > PERSISTED_SETTINGS_SCHEMA_VERSION:
            raise ValueError(
                "PersistedSettings schema_version "
                f"{version} is newer than supported version "
                f"{PERSISTED_SETTINGS_SCHEMA_VERSION}"
            )

        payload["schema_version"] = PERSISTED_SETTINGS_SCHEMA_VERSION
        return cls.model_validate(payload, context=context)

    @field_serializer("agent_settings")
    def agent_settings_serializer(
        self,
        agent_settings: AgentSettingsConfig,
        info: SerializationInfo,
    ) -> dict[str, Any]:
        # 将完整的上下文（密码，expose_secrets）传递到 AgentSettings 这确保机密基于上下
        # 文正确加密/公开
        #
        return agent_settings.model_dump(mode="json", context=info.context)

    @model_validator(mode="before")
    @classmethod
    def _normalize_inputs(
        cls, data: dict | object, info: ValidationInfo
    ) -> dict | object:
        """在反序列化期间标准化输入。

        对智能体和对话设置应用模式迁移，确保加载使用旧模式版本保存的设置文件时向前兼
        容性。

        智能体设置通过 ``validate_agent_settings`` 标准化，因此相同的迁移入口用于设置
        文件和直接 SDK 调用者。 验证上下文被转发，因
        此基于密码的机密解密在嵌套设置验证期间仍然有效。
        """
        if not isinstance(data, dict):
            return data

        agent_settings = data.get("agent_settings")
        if isinstance(agent_settings, dict):
            coerced = _coerce_dict_secrets(agent_settings)
            data["agent_settings"] = validate_agent_settings(
                coerced,
                context=info.context,
                persisted=True,
            )

        # 为 conversation_settings 应用迁移
        conv_settings = data.get("conversation_settings")
        if isinstance(conv_settings, dict):
            data["conversation_settings"] = ConversationSettings.from_persisted(
                conv_settings
            )

        return data


# 机密名称的验证模式 - 导出供 settings_router 使用
# 名称：以字母开头、字母数字+下划线、1-64 个字符
SECRET_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


class CustomSecret(BaseModel):
    """包含名称、值和可选描述的自定义机密。"""

    name: str
    secret: SecretStr | None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        """为了安全起见，验证机密名称格式。

        机密名称用作环境变量名称并且可能会被记录，因此我们强制执行严格的验证来防止：
        - 路径遍历（../，null字节）
        - 日志注入（控制字符）
        - Shell注入（特殊字符）
        - 无效的环境变量名称（以数字、特殊字符开头）

        Note: 路由器也验证名称，但这提供了一层纵深防御
        对于直接通过商店创建的机密（绕过 HTTP 层）。
        """
        if not SECRET_NAME_PATTERN.match(v):
            raise ValueError(
                "Secret name must start with a letter, contain only "
                "letters/numbers/underscores, and be 1-64 characters"
            )
        return v

    @field_validator("secret")
    @classmethod
    def _validate_secret(
        cls, v: str | SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        return validate_secret(v, info)

    @field_serializer("secret", when_used="always")
    def _serialize_secret(self, v: SecretStr | None, info: SerializationInfo):
        return serialize_secret(v, info)


class Secrets(BaseModel):
    """用于存储自定义机密的模型。

    不像 OpenHands 也存储提供商的 app-server token, the 智能体- 服务器仅存储自定义机
    密因为它直接不与OAuth提供商集成。
    """

    custom_secrets: dict[str, CustomSecret] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @property
    def has_any_secret(self) -> bool:
        """检查这些机密是否包含任何非空值。"""
        return _contains_secret_value(self)

    def get_env_vars(self) -> dict[str, str]:
        """获取机密作为环境变量字典。

        安全提取机密值，记录格式错误的警告机密。
        """
        result: dict[str, str] = {}
        for name, secret in self.custom_secrets.items():
            if secret.secret is None:
                continue
            try:
                result[name] = secret.secret.get_secret_value()
            except Exception:
                # 记录而不暴露机密内容
                from openhands.sdk.logger import get_logger

                get_logger(__name__).warning(
                    f"Failed to extract secret '{name}' - skipping"
                )
        return result

    def get_descriptions(self) -> dict[str, str | None]:
        """获取机密名称到描述的映射。"""
        return {
            name: secret.description for name, secret in self.custom_secrets.items()
        }

    @field_serializer("custom_secrets")
    def custom_secrets_serializer(
        self, custom_secrets: dict[str, CustomSecret], info: SerializationInfo
    ) -> dict[str, dict[str, Any]]:
        # 委托给使用 serialize_secret 的 CustomSecret.model_dump 这确保密码上下文流过进
        # 行加密
        #
        result = {}
        for name, secret in custom_secrets.items():
            result[name] = secret.model_dump(mode="json", context=info.context)
        return result

    @model_validator(mode="before")
    @classmethod
    def _normalize_inputs(cls, data: dict | object) -> dict | object:
        """将字典输入标准化为预期结构。

        Note: 我们故意将值保留为原始字符串/字典，以便
        Pydantic 的字段验证器可以通过验证上下文处理基于密码的解密。 此处包裹在
        SecretStr 中将绕过处理解密的 validate_secret()
         调用。
        """
        if not isinstance(data, dict):
            return data

        custom_secrets = data.get("custom_secrets")
        if isinstance(custom_secrets, dict):
            converted = {}
            for name, value in custom_secrets.items():
                if isinstance(value, CustomSecret):
                    converted[name] = value
                elif isinstance(value, dict):
                    # 保留为字典 - 让 Pydantic 用上下文处理验证
                    # 注意：对于缺少的机密，请使用None而不是“”来保留
                    # 区分“空机密”和“缺失机密”之间的区别
                    converted[name] = {
                        "name": name,
                        "secret": value.get("secret"),  # None 如果缺失
                        "description": value.get("description"),
                    }
                elif isinstance(value, str):
                    converted[name] = {
                        "name": name,
                        "secret": value,
                        "description": None,
                    }
            data["custom_secrets"] = converted

        return data


# ── 工作区 ───────────────────────────────────────────────────────────

WORKSPACES_SCHEMA_VERSION = 1


class WorkspaceItem(BaseModel):
    # ``id`` 是不透明的服务器端（重复数据删除由 ``path`` 进行），但 GUI 设置
    # ``id == path`` 对于工作区和父母。 下面的上限 ``id``
    # ``path`` 将是 422 个长但有效的文件系统路径，因此两个上限必须保持对齐。
    #
    id: str = Field(..., min_length=1, max_length=4096)
    name: str = Field(..., min_length=1, max_length=256)
    path: str = Field(..., min_length=1, max_length=4096)
    parent_path: str | None = Field(default=None, alias="parentPath", max_length=4096)
    model_config = ConfigDict(populate_by_name=True)


class WorkspaceParentItem(BaseModel):
    # 请参阅 ``WorkspaceItem.id`` — 保持 ``id`` 和 ``path`` 盖子对齐。
    id: str = Field(..., min_length=1, max_length=4096)
    name: str = Field(..., min_length=1, max_length=256)
    path: str = Field(..., min_length=1, max_length=4096)


class PersistedWorkspaces(BaseModel):
    schema_version: int = Field(default=WORKSPACES_SCHEMA_VERSION)
    workspaces: list[WorkspaceItem] = Field(default_factory=list)
    workspace_parents: list[WorkspaceParentItem] = Field(
        default_factory=list, alias="workspaceParents"
    )
    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_persisted(cls, data: Any) -> PersistedWorkspaces:
        if not isinstance(data, dict):
            return cls.model_validate(data)
        payload = dict(data)
        version = payload.get("schema_version", WORKSPACES_SCHEMA_VERSION)
        if not isinstance(version, int):
            raise ValueError("PersistedWorkspaces schema_version must be an integer")
        if version > WORKSPACES_SCHEMA_VERSION:
            raise ValueError(
                f"PersistedWorkspaces schema_version {version} is newer than "
                f"supported {WORKSPACES_SCHEMA_VERSION}"
            )
        payload["schema_version"] = WORKSPACES_SCHEMA_VERSION
        return cls.model_validate(payload)


# ── 辅助函数──────────────────────────────────────────────────────
#
# 注意：API 请求/响应模型已移至 SDK 以启用
# 在 SDK 客户端和智能体服务器之间共享。 参见：
#   openhands.sdk.settings.api_models（SecretCreateRequest、SecretItemResponse等）


def _coerce_dict_secrets(d: dict[str, Any]) -> dict[str, Any]:
    """递归地将 SecretStr 叶子强制转换为普通值。

    Note: SecretStr 提取包含在错误处理中以防止机密
    异常回溯中泄漏的值。
    """
    from openhands.sdk.logger import get_logger

    _logger = get_logger(__name__)
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _coerce_dict_secrets(v)
        elif isinstance(v, SecretStr):
            try:
                out[k] = v.get_secret_value()
            except Exception:
                _logger.warning(
                    f"Failed to extract secret value for key '{k}' - skipping"
                )
                out[k] = None
        else:
            out[k] = v
    return out
