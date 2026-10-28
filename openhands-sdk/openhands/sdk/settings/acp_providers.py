"""ACP 提供者注册表 — 内置提供者元数据的单一事实来源。

每个记录捕获配置时已知的静态属性（在启动任何子进程之前）：

- ``key`` 设置鉴别器 (``ACPAgentSettings.acp_server``)
- ``display_name`` 用于 UI 显示的人类可读标签
- ``default_command`` 默认基于 ``npx`` 的启动命令
- ``api_key_env_var``       环境变量子进程需要为 API 键
- ``base_url_env_var`` proxy/base-URL 路由的环境变量（或 ``None``）
- ``default_session_mode`` ACP 禁用权限的模式 ID 提示词，或 ``None``（当服务器没有此
模式时）
- ``agent_name_patterns`` 运行时智能体名称中的小写子字符串； ``ACPAgent`` 用于自动检
测模式/协议
- ``supports_set_session_model`` 提供者是否在会话创建时通过协议调用应用其 * 初始 * 模
型（``set_config_option``
/``set_session_model``)
- ``supports_runtime_model_switch`` 服务器是否支持运行时、会话中使用的协议级模型切换
- ``session_meta_key`` 顶级 ``_meta`` 键用于模型选择（或 ``None``）
- ``available_models`` 已弃用精选模型列表； 询问服务器
                            :函数：
                            `~openhands.sdk.agent.acp_model_discovery.discover_acp_models`
- ``default_model`` 已弃用策划的默认模型（或 ``None``）
- ``file_secrets`` 保留“文件内容”凭据机密提供商通过（Codex ``auth.json``、Gemini
Vertex SA JSON）进行身份验证；
 参见：类：`ACPFileSecretSpec`

注册表描述了存在哪些工具，而不是部署提供了哪些工具。 呈现子集的客户端独立声明
``SURFACED_ACP_PROVIDERS`` 并自行执行该策略。 它们的一致性检查是
单向的：表面的键必须是注册表键，因此上游重命名或删除会失败，而添加则为无操作。 不要在
此注册表中添加补充性的未公开列表或部署策略字段； 要么会将每个客户端耦合到每个上游添加
。
"""  # noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openhands.sdk.settings.acp_install_catalog import (
    ACP_INSTALL_CATALOG,
    CLAUDE_AGENT_ACP_VERSION as CLAUDE_AGENT_ACP_VERSION,
    CODEX_ACP_VERSION as CODEX_ACP_VERSION,
    GEMINI_CLI_VERSION as GEMINI_CLI_VERSION,
    KIMI_CODE_VERSION as KIMI_CODE_VERSION,
)
from openhands.sdk.utils.deprecation import warn_deprecated


_ASK_THE_ACP_SERVER = (
    "Ask the ACP server for its models instead: POST /api/acp/models, or "
    "openhands.sdk.agent.acp_model_discovery.discover_acp_models()."
)


@dataclass(frozen=True)
class ACPModelOption:
    """一种针对内置 ACP 提供商选择器 (已弃用) 的精选模型。"""

    id: str
    """确切的型号标识符作为 ``acp_model`` 发送到 ACP 服务器。"""

    label: str
    """模型选择器中显示的人类可读标签 (e.g. ``"Claude Opus 4.7"``)."""


class ACPFileSecretSpec(BaseModel):
    """从保留的“文件内容”机密到凭据的声明性映射
    文件 ACP 子进程进行身份验证。

    一些提供程序从磁盘 * 上的 * 文件而不是环境变量读取凭据：Codex 读取
    ``$CODEX_HOME/auth.json``； Gemini (Vertex
    AI) 读取 ``GOOGLE_APPLICATION_CREDENTIALS`` 指向的服务帐户 JSON。 用户提供该凭据
    作为粘贴的 blob — 名为的保留机
    密
    :attr:`secret_name` — 和：class:`~openhands.sdk.agent.ACPAgent` 实现
    它到会话的持久每个会话根（seed-if-absent）下的：attr:`filename`，然后设置：attr:
    `env_var` 以便 CLI 可以找到它。

    物化被关闭：attr:`secret_name` （不是启动命令），因此只要提供了保留的机密，自定义
    或别名的 ``acp_command`` 仍然可以工作。

    SDK 拥有 * 机制 *（在运行时 pod 中写入文件、设置环境变量、种子如果不存在、权限）
    ； *政策* — 机密映射到哪些文件和哪些CLIs — 位于这些规范中
    。 内置默认值涵盖支持的提供程序，但下游应用程序可以覆盖
    :attr:`~openhands.sdk.agent.ACPAgent.acp_file_secrets` 支持其他 ACP
    具有不同文件身份验证方案的服务器，无需 SDK 更改。
    """

    model_config = ConfigDict(frozen=True)

    secret_name: str = Field(min_length=1)
    """保留机密，其值为凭据文件的内容（查找
    在 ``state.secret_registry`` / ``agent_context.secrets`` 中）。"""

    filename: str = Field(min_length=1)
    """e.g 物料化文件的文件名。 ``auth.json``)."""

    env_var: str = Field(min_length=1)
    """Env var CLI 读取以定位具体化的凭据。"""

    subdir: str = Field(min_length=1)
    """每个对话 ``<conversations>/{id.hex}/acp/`` 根目录下的文件夹
    文件写入的位置 — 内置程序的提供程序密钥 (``codex`` /
    ``gemini-cli``)，或自定义规范的任何稳定文件夹名称。 将并发提供商的凭据文件隔离在
    一个沙箱内。
"""

    env_points_to: Literal["dir", "file"] = "file"
    """:attr:`env_var` 是否设置为文件的父目录 *目录*（Codex 的
    ``CODEX_HOME``) 或 *file* 路径本身（Gemini 的
    ``GOOGLE_APPLICATION_CREDENTIALS``)."""

    warn_if_unset: tuple[str, ...] = ()
    """伴随环境变量，用于在机密实现时发出警告，但是
    他们失踪了（e.g. ``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION`` 对于 Vertex
     AI）。 仅供参
    考——具体化仍在进行中。
"""

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        """``filename`` 必须是裸露的基本名称，而不是路径或遍历。"""
        if "/" in value or "\\" in value or value in (".", ".."):
            raise ValueError("filename must be a bare basename, not a path")
        return value

    @field_validator("subdir")
    @classmethod
    def _validate_subdir(cls, value: str) -> str:
        """``subdir``必须是真实的相对文件夹（禁止遍历、根转义、
        或者将凭据直接放入共享 ``acp/`` 根的 ``.`` 身份路径，其中两个规范可能会发生冲
        突）。
        """
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value.strip() in ("", "."):
            raise ValueError(
                "subdir must be a non-empty relative path without '.'/'..' segments"
            )
        return value


class ACPEnvConflictSpec(BaseModel):
    """一个提供商针对环境变量的规则不得与凭据共存。

    CLIs中有些接受多个凭据通道，并通过一个呼叫者看不到的优先级来选择它们，因此一个仅
    仅*存在的变量*就无声地击败了用户原本的凭据意图。
    ``CLAUDE_CODE_OAUTH_TOKEN`` 是这个案例的触发点：api.anthropic.com 是一个受验证的
    载体，
    ``ANTHROPIC_API_KEY`` 优先于它，而 ``ANTHROPIC_BASE_URL`` 会将载体路由到一个拒绝
    它的代理。

    规则属于提供者，而不是过程：另一个提供者可以合法地将这些变量视为自己的 * * 凭据
    （一个提供者 ``api_key_env_var``
    ``ANTHROPIC_API_KEY``），并在那里删除该提供者唯一的凭据。
    """

    model_config = ConfigDict(frozen=True)

    dominant: str = Field(min_length=1)
    """环境变量，其存在意味着该提供者正在使用它进行身份验证。"""

    strip: tuple[str, ...] = Field(min_length=1)
    """当：attr:`dominant` 时，环境变量从子进程环境中删除
    存在。"""


@dataclass(frozen=True)
class ACPProviderInfo:
    """一个内置 ACP 提供程序的不可变元数据记录。"""

    key: str
    """设置鉴别器值（``ACPAgentSettings.acp_server``）。"""

    display_name: str
    """适合 UI 标签的人类可读名称。"""

    default_command: tuple[str, ...] = field(compare=False)
    """未设置显式 ``acp_command`` 时使用默认子进程命令。"""

    api_key_env_var: str | None
    """ACP 子进程期望其主环境变量 API 凭据。

    ``None`` 对于通过浏览器登录而不是 API 密钥进行身份验证的提供商 (e.g. Claude Code
    的 ``claude-login`` 流程）。
    """

    base_url_env_var: str | None
    """Env var ACP 子进程读取自定义 API 基 URL。

    允许通过代理（例如 LiteLLM）路由提供程序调用。
    ``None`` 如果提供程序不支持基于环境的 base-URL 覆盖。
    """

    default_session_mode: str | None
    """ACP 会话模式 ID 设置在 ``session/new`` 之后，或 ``None`` 跳过
    的电话。

    对于具有权限抑制模式的服务器，该值是：
    ``bypassPermissions``（克劳德-智能体-ACP），``agent-full-access``（@
    agentclientprotocol/code
    x-ACP）。 gemini-CLI 使用 ``default``（其 ``yolo`` 模式在初始化时出现错误）； ACP
     桥梁自动批准权限请求，因此模式不会阻止
    提示词。
    ``None`` 对于根本不公开任何权限模式的服务器：pi-ACP 将 ACP 模式映射到 pi 的思维级
    别 (``off``..``xhigh``) 并拒绝任何其
    他 id，因此发送一个模式将使会话初始化失败。
    """

    agent_name_patterns: tuple[str, ...]
    """运行时 ``agent_name`` 中存在小写子字符串片段。

    ``ACPAgent`` 根据 ACP 服务器返回的名称检查这些内容
    ``InitializeResponse`` 自动选择正确的会话模式并确定使用哪种模型选择协议。
    """

    supports_set_session_model: bool
    """``True`` 如果该提供商通过以下方式选择其 * 初始 * 模型
    ``set_session_model`` 协议调用（而不是会话 ``_meta``）。

    这仅控制 **session-creation** 路径。 ``True`` 对于每个内置提供程序，在创建会话后
    立即进行一次性
    ``set_session_model`` 调用。 claude-智能体-ACP 是 ``False``，直到 0.30.0 被发现默
    默地忽略它所依赖的 sessi
    on-``_meta`` 选择（#3654）； 它的 ``_meta`` 载荷仍然一起发送（参见
    ：属性：`session_meta_key`）。

    这是 ** 独立于 ** 运行时切换能力 — 请参阅
    ：属性：`supports_runtime_model_switch`。 这面旗帜的最初含义
    被保留，以便使用它来选择初始选择路径的外部消费者继续工作。
    """

    session_meta_key: str | None
    """用于在会话创建 * 时选择模型 * 的顶级 ``_meta`` 键。

    当非 ``None`` 时，模型会通过 ACP 会话另外进行广告
    ``_meta`` 使用结构
    ``{session_meta_key: {"options": {"model": <model>}}}`` 传递至
    ``new_session()``. 这只是尽力而为：claude-智能体-ACP 忽略它（#3654），因此权威的
    初始选择是在：attr:
    `supports_set_session_model` 上门控的协议调用。

    运行时交换机使用会话通告的机制（``set_config_option`` 或 ``set_session_model``）
    ，门控
    ：属性：`supports_runtime_model_switch`。

    - ``"claudeCode"`` — 克劳德-智能体-ACP
    - ``None``         — codex-ACP, gemini-CLI, pi-ACP
    """

    available_models: tuple[ACPModelOption, ...] = field(
        default=(), compare=False, repr=False
    )
    """Deprecated: 请改为使用 ``discover_acp_models`` 询问 ACP 服务器。

    该提供商的 ``acp_model`` 选择器中出现了精选的模型列表。

    这些反映了每个内置工具的运行时选择器值，但只是建议，而不是权威的访问检查。 用户仍
    然可以配置列表中不包含的自定义 ``acp_model``，实际可用性取决于帐户的
    计划层级。 对于没有精选列表的提供商为空（e.g. 向前兼容的条目）。
    """

    default_model: str | None = field(default=None, compare=False, repr=False)
    """Deprecated: 请改为使用 ``discover_acp_models`` 询问 ACP 服务器。

    未配置 ``acp_model`` 时预选型号 ID，否则为 ``None``。

    设置后，它必须是：attr:`available_models` id 之一。 ``None`` 让 ACP 服务器选择自
    己的默认值。
    """

    supports_runtime_model_switch: bool = False
    """``True``如果服务器支持``session/set_model``协议调用
    用于**运行时、对话中模型切换**。

    该调用适用于实时会话，因此后续回合将使用新模型，而不会重新启动子进程或丢失上下文
    。 每个内置提供程序都支持它（已根据 claude-智能体-ACP、codex-
    ACP、gemini-CLI 和 pi-ACP 进行验证）。

    与：attr:`supports_set_session_model` 不同，这是关于切换 * 已经运行的 * 会话的模
    型，而不是初始选择。 提供者可以通过
    ``_meta`` (claude-智能体-ACP) 选择其初始模型，但仍然支持协议级切换以供以后更改。

    默认值为 ``False``，因此，支持向前兼容的提供者以及任何通过位置参数构建此数据类的
    外部调用者都不会出现签名断开的情况。 内置提供程序明确设置它。
    """

    file_secrets: tuple[ACPFileSecretSpec, ...] = field(default=(), compare=False)
    """保留的文件内容凭据机密该提供程序从中进行身份验证。

    每个条目将保留的机密名称映射到：class:`~openhands.sdk.agent.ACPAgent` 在启动子进
    程之前实现的磁盘文件（以及指向它的环境变量）。
     对于纯粹通过环境变量进行身份验证的提供者为空（e.g. 克劳德代码）。 默认为 ``()``
     ，因此按位置构造此数据类的外部调用者可以继续工作。
    """

    binary_name: str | None = field(default=None, compare=False)
    """为此提供商固定的、预安装的 CLI 二进制文件 (e.g. ``codex-acp``).

    智能体-服务器镜像固定安装ACP CLIs，并使用``PATH``包装。 当此二进制通过：func:
    `shutil.which` 解析时，
    ：甲基：`~openhands.sdk.settings.model.ACPAgentSettings.resolve_acp_command`
    重写 ``npx -y <pkg>`` 启动命令以直接运行它（保留像 Gemini 的 ``--acp`` 一样的尾随
    参数）； 否则，``npx`` 命令将保持不变
    。 ``None`` 对于没有固定二进制文件的提供商（和 ``custom`` 服务器）； 默认，因此位
    置构造继续有效。
    """

    data_dir_env_var: str | None = None
    """重新定位此 CLI 的每用户数据/配置根目录的环境变量。

    将其设置为按会话目录，以隔离  CLI当用户的多个会话共享一个沙盒时，'on-disk state (
    config, transcripts, caches, lo
    ckfiles)``SandboxGroupingStrategy != NO_GROUPING``) — 否则它们会在一个共享的上竞
    速 ``HOME`` (见#1
    019)。 每个 CLI 暴露了不同的杠杆：

    - ``CODEX_HOME`` — codex-ACP（批量迁移 ``~/.codex``）
    - ``CLAUDE_CONFIG_DIR`` — claude-智能体-ACP（重新定位 ``~/.claude*``）
    - ``HOME`` — gemini-CLI（无专用变量； 它硬编码
      ``~/.gemini`` 并忽略 ``XDG``，因此只有 ``HOME`` 移动它）
    - ``HOME`` — pi-ACP（其会话映射被硬编码为
      ``~/.pi/pi-acp``; ``PI_CODING_AGENT_DIR`` 移动 pi 自己的配置目录，但不移动适配
      器的配置目录，因此只有
      ``HOME`` 重新定位两者）

    ``None`` 对于没有已知重定位杠杆的提供商，然后跳过隔离。 消耗于
    ：属性：`~openhands.sdk.agent.ACPAgent.acp_isolate_data_dir`。
    """

    env_conflicts: tuple[ACPEnvConflictSpec, ...] = field(default=(), compare=False)
    """该提供者自己的环境变量凭据不得与其共存。

    应用于子进程环境
    :class:`~openhands.sdk.agent.ACPAgent` 仅适用于声明的提供者
    他们——参见：class:`ACPEnvConflictSpec`。
    """

    def __getattribute__(self, name: str) -> Any:
        if name == "available_models":
            warn_deprecated(
                "ACPProviderInfo.available_models",
                deprecated_in="1.54.0",
                removed_in="1.59.0",
                details=_ASK_THE_ACP_SERVER,
                stacklevel=3,
            )
        elif name == "default_model":
            warn_deprecated(
                "ACPProviderInfo.default_model",
                deprecated_in="1.54.0",
                removed_in="1.59.0",
                details=_ASK_THE_ACP_SERVER,
                stacklevel=3,
            )
        return object.__getattribute__(self, name)


def _deprecated_model_option() -> type[ACPModelOption]:
    warn_deprecated(
        "ACPModelOption",
        deprecated_in="1.54.0",
        removed_in="1.59.0",
        details=_ASK_THE_ACP_SERVER,
        stacklevel=4,
    )
    return ACPModelOption


# ---------------------------------------------------------------------------
# 为内置提供者策划了 ``acp_model`` 个候选列表。
#
# 这些是对模型选择器的建议，反映了每个线束自己的运行时 ``/model`` 选项。 它们不是权威的
# 访问检查 - 可用性最终取决于用户的计划级别和自定义
# 这些列表之外的 ``acp_model`` 始终是允许的。
# ---------------------------------------------------------------------------

# Claude Code 模型 ID CLI 接受，与之类似 ``model``  configOptions 选择 claud -智能体-ACP
#  报告 ``session/new`` (这些简短的别名) CLI自己的 ``/model`` 菜单选项，通过切换实现
# ``set_config_option``).
# ``opus[1m]`` 是 SDK 记录的与版本无关的 1M-上下文别名和 CLI 自己的默认值 (
# ``currentValue``)； ``default`` 是 CLI 推荐的账户层级。 ``claude-opus-5`` 是为想要
# Opus 5 而不是依赖于提供商的别名的用户提供的显式完整模型 pin。 ``/model`` 菜单是动态的/
# 与帐户相关的，CLI 根据实时选择验证 ``set_config_option(model)`` — 它拒绝缺失的 id (e.g
# . ``sonnet`` 没有它的帐户），所以这些是会前建议，而不是事实真相； 被拒绝的 ID 降级为服
# 务器默认值。
#
_CLAUDE_MODELS: tuple[ACPModelOption, ...] = (
    ACPModelOption(id="default", label="Default (recommended)"),
    ACPModelOption(id="opus[1m]", label="Claude Opus (1M)"),
    ACPModelOption(id="claude-opus-5", label="Claude Opus 5"),
    ACPModelOption(id="sonnet", label="Claude Sonnet"),
    ACPModelOption(id="haiku", label="Claude Haiku"),
)

# Codex 应用服务器通过以下方式公布的裸预设 ID
# ``@agentclientprotocol/codex-acp``. 推理工作层是一个单独的 ``reasoning_effort``
# configOption，不是模型 id 的一部分，因此这里没有对其进行编码。 GPT-5.6 变体是与部署/帐
# 户相关的建议； 适配器的实时模型列表仍然具有权威性。
#
# ``gpt-5.6`` (裸体)，``gpt-5.4`` 和 ``gpt-5.4-mini`` 是活服务器 ``set_config_option``
# 拒绝的无效参数 (#4830 P0-2 模型接受探针捕获到的) 并已移除； 只有 GPT-5.6 层的后缀变体
# 是实时的。
#
_CODEX_MODELS: tuple[ACPModelOption, ...] = (
    ACPModelOption(id="gpt-6-astra", label="GPT-6 Astra"),
    ACPModelOption(id="gpt-5.6-sol", label="GPT-5.6 Sol"),
    ACPModelOption(id="gpt-5.6-terra", label="GPT-5.6 Terra"),
    ACPModelOption(id="gpt-5.6-luna", label="GPT-5.6 Luna"),
    ACPModelOption(id="gpt-5.5", label="GPT-5.5"),
)

# ``@google/gemini-cli --acp`` 接受的模型 ID。 镜像
# ``availableModels`` CLI 在 ``session/new`` 中报告了固定版本 (gemini-CLI 0.46.0)。
# ``auto``将版本选择委托给CLI的路由器； 显式 ``gemini-*`` 条目固定到特定快照。 CLI 还接
# 受此列表之外的 id（它在生成时重新映射它们），因此这些是精心策划的建议，而不是访问检查
# 。
#
_GEMINI_MODELS: tuple[ACPModelOption, ...] = (
    ACPModelOption(id="auto", label="Auto"),
    # gemini-CLI 0.46 展示了 pro-preview ``gemini-3.1-pro-preview`` 当 Gemini 3.1 发射标
    # 志 [on] 时，``PREVIEW_GEMINI_3_1_MODEL``), 降级到 ``gemini-3-pro-preview`` (
    # ``PREVIEW_GEMINI_MODEL``否则，保留两者，这样选择器与滚动条的状态匹配。
    #
    ACPModelOption(id="gemini-3.1-pro-preview", label="Gemini 3.1 Pro (preview)"),
    ACPModelOption(id="gemini-3-pro-preview", label="Gemini 3 Pro (preview)"),
    ACPModelOption(id="gemini-3-flash-preview", label="Gemini 3 Flash (preview)"),
    ACPModelOption(id="gemini-3.1-flash-lite", label="Gemini 3.1 Flash Lite"),
    ACPModelOption(id="gemini-2.5-pro", label="Gemini 2.5 Pro"),
    ACPModelOption(id="gemini-2.5-flash", label="Gemini 2.5 Flash"),
)

# Pi 模型 ID 为 ``<pi-provider>/<model-id>``，实时目录取决于配置的上游凭据 — pi 仅显示它
# 可以验证的提供者。 这些镜像了 ``ANTHROPIC_API_KEY`` 下 ``session/new`` 中的 Anthropic
# 条目 pi 报告（凭据通道 ``api_key_env_var`` 规定）； 列表之外的 ``acp_model``，e.g。
# OpenAI 键上的 ``openai/gpt-5.5`` 仍然被接受。
#
_PI_MODELS: tuple[ACPModelOption, ...] = (
    ACPModelOption(id="anthropic/claude-opus-5", label="Claude Opus 5"),
    ACPModelOption(id="anthropic/claude-opus-4-8", label="Claude Opus 4.8"),
    ACPModelOption(id="anthropic/claude-sonnet-5", label="Claude Sonnet 5"),
    ACPModelOption(id="anthropic/claude-sonnet-4-6", label="Claude Sonnet 4.6"),
    ACPModelOption(id="anthropic/claude-haiku-4-5", label="Claude Haiku 4.5"),
)

# ``opencode acp`` 接受的模型 ID，镜像 ``model`` configOptions 选择 OpenCode 的报告
# ``session/new``。 每个 id 都是 ``<provider>/<model>``，并且提供的集合是凭据相关的，但
# 与 Kimi 的不同，它不是
# *用户定义的*：这些是OpenCode Zen id，目录
# ``OPENCODE_API_KEY`` — 提供商自己的凭据 — 解锁，因此精心策划的列表是有意义的。 如果没
# 有密钥，服务器仅提供免费层，这就是保留 ``nemotron-3-ultra-free`` 的原因。 用户仍然可以
# 配置任何
# ``<provider>/<model>`` CLI 知道 (e.g. ``anthropic/...`` 和 ANTHROPIC_API_KEY 作为对话
# 提供机密）。
#
_OPENCODE_MODELS: tuple[ACPModelOption, ...] = (
    ACPModelOption(id="opencode/big-pickle", label="Big Pickle"),
    ACPModelOption(id="opencode/claude-opus-5", label="Claude Opus 5"),
    ACPModelOption(id="opencode/claude-sonnet-5", label="Claude Sonnet 5"),
    ACPModelOption(id="opencode/gpt-5.5", label="GPT-5.5"),
    ACPModelOption(id="opencode/gemini-3.1-pro", label="Gemini 3.1 Pro"),
    ACPModelOption(id="opencode/kimi-k3", label="Kimi K3"),
    ACPModelOption(
        id="opencode/nemotron-3-ultra-free", label="Nemotron 3 Ultra (free)"
    ),
)


# ---------------------------------------------------------------------------
# 为内置提供程序保留的文件内容凭据机密。
#
# Codex 的 ChatGPT-订阅 ``auth.json`` 随 ``CODEX_HOME`` 一起重新定位（并在 token 刷新时
# 就地重写，因此它必须存在于持久、可写的存储上）。 Gemini 的 Vertex AI 服务帐户 JSON 直
# 接指向
# ``GOOGLE_APPLICATION_CREDENTIALS``; Vertex 还需要一个项目/位置，因此在未设置时发出警告
# 。 Pi 从 ``auth.json`` 下读取其凭据
# ``PI_CODING_AGENT_DIR``（同一目录中的 ``settings.json`` 保存模型和 UI 首选项，并且不进
# 行身份验证）。
# ---------------------------------------------------------------------------
_CODEX_FILE_SECRETS: tuple[ACPFileSecretSpec, ...] = (
    ACPFileSecretSpec(
        secret_name="CODEX_AUTH_JSON",
        filename="auth.json",
        env_var="CODEX_HOME",
        subdir="codex",
        env_points_to="dir",
    ),
)
_KIMI_FILE_SECRETS: tuple[ACPFileSecretSpec, ...] = (
    # Kimi 从其配置文件而不是环境进行身份验证：ACP 身份验证门通过 config.toml 内的
    # ``provider.env`` 解析凭据，并且从不读取 ``process.env``。 在 0.38.0 上验证 - 仅当
    # 密钥内联在文件中时会话才会启动，即使导出了 KIMI_API_KEY。
    #
    ACPFileSecretSpec(
        secret_name="KIMI_CODE_CONFIG_TOML",
        filename="config.toml",
        env_var="KIMI_CODE_HOME",
        subdir="kimi-code",
        env_points_to="dir",
    ),
)
_GEMINI_FILE_SECRETS: tuple[ACPFileSecretSpec, ...] = (
    ACPFileSecretSpec(
        secret_name="GOOGLE_APPLICATION_CREDENTIALS_JSON",
        filename="gcloud-credentials.json",
        env_var="GOOGLE_APPLICATION_CREDENTIALS",
        subdir="gemini-cli",
        env_points_to="file",
        warn_if_unset=("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"),
    ),
)
_PI_FILE_SECRETS: tuple[ACPFileSecretSpec, ...] = (
    ACPFileSecretSpec(
        secret_name="PI_AUTH_JSON",
        filename="auth.json",
        env_var="PI_CODING_AGENT_DIR",
        subdir="pi",
        env_points_to="dir",
    ),
)


# 已标记的 npm 包/版本和 CLI每个内置启动器的调用形状现在都生活在  ACP_INSTALL_CATALOG (
# openhands.sdk.settings. acp_install_catalog— 一个依赖项完全去除的模块，也直接被消费智
# 能体-server Dockerfile的 `acp-providers` 构建阶段。 版本升级只需要发生在那里；
# `default_command`/`binary_name` 以下内容均来源于它，因此两者都保留了下来同步自动地。
#
# claude-智能体-ACP 0.44+ / codex-ACP 通过 ``model`` 选择模型
# ``configOptions`` 条目（并保留旧的 ``session/set_model`` 扩展）； SDK 检测每个会话通告
# 的机制。
#


ACP_PROVIDERS: Mapping[str, ACPProviderInfo] = MappingProxyType(
    {
        "claude-code": ACPProviderInfo(
            key="claude-code",
            display_name="Claude Code",
            default_command=ACP_INSTALL_CATALOG["claude-code"].npx_command(),
            api_key_env_var="ANTHROPIC_API_KEY",
            base_url_env_var="ANTHROPIC_BASE_URL",
            default_session_mode="bypassPermissions",
            agent_name_patterns=("claude-agent",),
            # claude-智能体-ACP忽略session-_meta模型选择（请求的模型仅成为picker选项；
            # 会话保持默认运行），因此初始化路径必须通过协议调用推送模型（#3654）。 在 0
            # .44.0+ 上，该调用是
            # ``set_config_option(configId="model")`` 而不是
            # ``set_session_model``（从会话/新自动检测）； _meta 载荷（下面的
            # session_meta_key）仍然被发送——无害，并且如果未来的CLI尊重它，就会选择相同
            # 的模型。
            #
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            session_meta_key="claudeCode",
            available_models=_CLAUDE_MODELS,
            # CLI 自己的默认值（模型 configOptions ``currentValue``）。
            default_model="opus[1m]",
            binary_name=ACP_INSTALL_CATALOG["claude-code"].binary_name,
            data_dir_env_var="CLAUDE_CONFIG_DIR",
            # 键控在凭据本身上，不在 CLAUDE_CONFIG_DIR 上：配置目录是一个 *location* 杠
            # 杆（数据目录隔离，#1019），与凭据处于活动状态正交。 在 API 键隔离期间，在
            # 其上键入条带会被错误地触发，并且当 token 通过 env 未经隔离到达时错过了冲突
            #  (#3588)。
            #
            env_conflicts=(
                ACPEnvConflictSpec(
                    dominant="CLAUDE_CODE_OAUTH_TOKEN",
                    strip=("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"),
                ),
            ),
        ),
        "codex": ACPProviderInfo(
            key="codex",
            display_name="Codex",
            default_command=ACP_INSTALL_CATALOG["codex"].npx_command(),
            api_key_env_var="OPENAI_API_KEY",
            base_url_env_var="OPENAI_BASE_URL",
            default_session_mode="agent-full-access",
            agent_name_patterns=("codex-acp",),
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            session_meta_key=None,
            available_models=_CODEX_MODELS,
            default_model="gpt-5.5",
            file_secrets=_CODEX_FILE_SECRETS,
            binary_name=ACP_INSTALL_CATALOG["codex"].binary_name,
            data_dir_env_var="CODEX_HOME",
        ),
        "gemini-cli": ACPProviderInfo(
            key="gemini-cli",
            display_name="Gemini CLI",
            default_command=ACP_INSTALL_CATALOG["gemini-cli"].npx_command(),
            api_key_env_var="GEMINI_API_KEY",
            base_url_env_var="GEMINI_BASE_URL",
            # gemini-CLI 0.46.0 在会话初始化时拒绝 ``set_session_mode("yolo")`` (-32603)
            # ，这会导致无头启动崩溃； ``default``已被接受。 ACP 桥会自动批准每个
            # request_permission，因此无论模式如何，提示词都不会阻塞。 参见#3772。
            #
            default_session_mode="default",
            agent_name_patterns=("gemini-cli",),
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            session_meta_key=None,
            available_models=_GEMINI_MODELS,
            # 匹配 Gemini CLI 自己的自动路由器，而不是手动固定的快照。 固定e.g。
            # ``gemini-2.5-pro`` 这里将使下游客户端持久化成为绕过 CLI 自动路由的值。
            # ``auto`` 是 CLI 在其 0.46.0 ``availableModels`` 中报告的路由器 ID。
            #
            default_model="auto",
            file_secrets=_GEMINI_FILE_SECRETS,
            binary_name=ACP_INSTALL_CATALOG["gemini-cli"].binary_name,
            # Gemini CLI 没有专用的配置目录变量； 它硬编码
            # ``~/.gemini``（忽略 XDG），因此只有 HOME 重新定位其状态。
            data_dir_env_var="HOME",
        ),
        "kimi-code": ACPProviderInfo(
            key="kimi-code",
            display_name="Kimi Code",
            default_command=ACP_INSTALL_CATALOG["kimi-code"].npx_command(),
            # 没有 env-var API 键：``KIMI_API_KEY`` 是 config.toml 内部的只读，因此导出
            # 它不会进行任何身份验证（在 0.38.0 上进行验证，存在或不存在配置文件）。 凭
            # 据是文件本身 - 请参阅 _KIMI_FILE_SECRETS。 Kimi 的仅 env 路由是
            # ``KIMI_MODEL_NAME`` + ``KIMI_MODEL_API_KEY``，它需要该字段无法表达的第二个
            # 变量。 参见#4819。
            #
            api_key_env_var=None,
            # 不是身份验证声明：当 config.toml 声明没有 base_url 时，普通端点会覆盖 CLI
            # 荣誉为回退方案。
            #
            base_url_env_var="KIMI_BASE_URL",
            # 根据 Kimi 代码 CLI 0.38.0 进行验证：``session/set_mode`` 接受 ``auto``
            # /``yolo``/``default``/``plan``. ``yolo`` 自动批准工具调用，同时仍然允许问
            # 题引发； ``auto``会完全压制问题。
            #
            default_session_mode="yolo",
            # ``kimi acp``报道``agentInfo.name = "Kimi Code CLI"``。
            agent_name_patterns=("kimi",),
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            session_meta_key=None,
            # 故意未经策划。 不同于其他三个，Kimi的模型ID是凭据的属性，而不是计划层级：
            # 账户登录提供``kimi-code/*``个别名，而config.toml提供商提供用户指定的别名（
            # 在0.38.0版本中，``model``选择返回了用户选择的密钥）。 因此，对于没有帐户登
            # 录的任何人来说，静态列表都是错误的，而不仅仅是不完整。 客户端从实时会话的
            # 模型选择中呈现选择器；
            # ``default_model=None`` 让 CLI 选择自己的默认值，它根据配置的任何提供程序进
            # 行解析。
            #
            available_models=(),
            default_model=None,
            file_secrets=_KIMI_FILE_SECRETS,
            binary_name=ACP_INSTALL_CATALOG["kimi-code"].binary_name,
            # ``KIMI_CODE_HOME`` 重新定位 ``~/.kimi-code`` 数据根。
            data_dir_env_var="KIMI_CODE_HOME",
        ),
        "pi": ACPProviderInfo(
            key="pi",
            display_name="Pi",
            # 两个包，因此目录发出 ``--package=`` 形式
            # ``pi-acp`` 作为位置 npx 运行 — 这也是唯一的 token
            # ``_prefer_pinned_binary`` 和
            # ``detect_acp_provider_by_command`` 可以匹配。
            default_command=ACP_INSTALL_CATALOG["pi"].npx_command(),
            api_key_env_var="ANTHROPIC_API_KEY",
            # pi 从其自己的目录中解析每个提供者的基数 URL； ANTHROPIC_BASE_URL 仅到达供
            # 应商的 Anthropic SDK，pi 会覆盖该供应商。 重定向它需要 models.json 或扩展
            # 。
            #
            base_url_env_var=None,
            default_session_mode=None,
            agent_name_patterns=("pi-acp",),
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            session_meta_key=None,
            available_models=_PI_MODELS,
            # pi 从配置的凭据解锁的任何目录中预选一个模型，因此没有一个 id 是适合每个账
            # 户的——让服务器来决定。
            #
            default_model=None,
            file_secrets=_PI_FILE_SECRETS,
            binary_name=ACP_INSTALL_CATALOG["pi"].binary_name,
            data_dir_env_var="HOME",
        ),
        "opencode": ACPProviderInfo(
            key="opencode",
            display_name="OpenCode",
            default_command=ACP_INSTALL_CATALOG["opencode"].npx_command(),
            # OpenCode Zen，CLI 自己的网关及其模型 ID 的提供者都在命名空间下。 第三方密
            # 钥（ANTHROPIC_API_KEY、OPENAI_API_KEY、...）也在 OpenCode 内启用其提供者，
            # 但其中 None 是 OpenCode 自己的凭据。
            #
            api_key_env_var="OPENCODE_API_KEY",
            # Zen的端点来自模型目录，而不是
            # 环境：针对本地接收器进行验证，两者都没有
            # OPENCODE_BASE_URL 和 OPENAI_BASE_URL 都不会转移它。 每个提供商
            # 配置文件中的 ``options.baseURL`` 是唯一的覆盖。
            base_url_env_var=None,
            # OpenCode 恰好公开两种模式：``build`` 和 ``plan``。
            # ``build`` 是工具执行默认值，在库存权限配置下不会提出读/写/bash 的权限请求
            # 。
            #
            default_session_mode="build",
            # ``opencode acp``报告``agentInfo.name = "OpenCode"``； 该模式还为包基名
            # ``opencode-ai`` 和二进制文件 ``opencode`` 添加前缀，以进行命令时检测。
            #
            agent_name_patterns=("opencode",),
            supports_set_session_model=True,
            supports_runtime_model_switch=True,
            # ``session/new`` 忽略 ``_meta`` 模型选择（在三个可能的键下尝试）；
            # configOptions 选择是唯一生效的路径。
            #
            session_meta_key=None,
            available_models=_OPENCODE_MODELS,
            # CLI 自己的默认值（型号 configOptions ``currentValue``），带或不带密钥。
            #
            default_model="opencode/big-pickle",
            # 否 ``file_secrets``：OpenCode 在设置时从 OPENCODE_AUTH_CONTENT 读取其整个
            # 身份验证存储，在磁盘上 auth.json 之前，因此凭据使用普通的 env-var 通道。
            #
            binary_name=ACP_INSTALL_CATALOG["opencode"].binary_name,
            # OPENCODE_CONFIG_DIR 存在，但仅指向配置 * 文件 *； auth、sessions、SQLite
            # store 和 caches 都遵循 XDG_{DATA,CONFIG,CACHE,STATE}_HOME，所有都退回到
            # HOME。 HOME的搬迁是唯一能同时移动它们的单个杠杆。
            #
            data_dir_env_var="HOME",
        ),
    }
)
"""只读注册表内置 ACP 提供程序，由 ``acp_server`` 值键入。"""


def default_acp_file_secrets() -> tuple[ACPFileSecretSpec, ...]:
    """所有受支持的提供商的内置文件内容凭据规范。

    每个：attr:`ACPProviderInfo.file_secrets` 的并集（Codex ``auth.json``、Gemini
    Vertex SA）。
    用作默认值
    :attr:`~openhands.sdk.agent.ACPAgent.acp_file_secrets`，这是下游
    应用程序可以覆盖或扩展以支持其他 ACP 服务器，而无需进行 SDK 更改。
    """
    return tuple(spec for info in ACP_PROVIDERS.values() for spec in info.file_secrets)


def get_acp_provider(key: str) -> ACPProviderInfo | None:
    """返回 ``key`` 的：class:`ACPProviderInfo`，如果未知则返回 ``None``。"""
    return ACP_PROVIDERS.get(key)


def detect_acp_provider_by_agent_name(agent_name: str) -> ACPProviderInfo | None:
    """从运行时 ``agent_name`` 字符串中识别提供程序。

    按插入顺序迭代：data:`ACP_PROVIDERS` 并返回：attr:
    `~ACPProviderInfo.agent_name_patterns` 包含
    ``agent_name.lower()`` 子字符串的第一个条目。

    当没有模式匹配时返回 ``None`` (e.g. ``'custom'`` 服务器或无法识别的第三方 ACP 实
    现）。
    """
    lower = agent_name.lower()
    for info in ACP_PROVIDERS.values():
        if any(pat in lower for pat in info.agent_name_patterns):
            return info
    return None


def detect_acp_provider_by_command(
    command: Sequence[str],
) -> ACPProviderInfo | None:
    """在子进程运行之前，从其启动 ``command`` 识别提供程序。

    每个提供程序的：attr:`~ACPProviderInfo.agent_name_patterns` 片段（``"codex-acp"``
    、
    ``"claude-agent"``、``"gemini-cli"``、``"pi-acp"``）是其 npm-package / 二进制基本
    名称的前缀，因此我们可
    以选择提供程序
    *before* 服务器启动并报告其名称（当子进程
    环境，e.g。 重新定位的数据目录，必须已设置）。

    匹配故意比
    :func:`detect_acp_provider_by_agent_name` 因为启动命令是
    *调用者控制的*：每个token都减少为其基本名称（最后一个路径段，
    减去尾随 ``@version`` 引脚），并且仅当基本名称 * 以 * 其模式之一开头时，提供程序
    才匹配。 这接受真实形式 -
    ``@agentclientprotocol/codex-acp``, ``@google/gemini-cli@0.46.0``,
    ``/opt/node_modules/.bin/codex-acp`` - 同时拒绝普通子字符串测试会错误归因的附带子
    字符串，例如
    ``my-codex-acp-wrapper`` 或 ``/opt/shims/not-codex-acp``。

    对于自定义/无法识别的命令返回 ``None``，因此需要已知提供程序的调用者 (e.g. 数据目
    录隔离）安全无操作。
    """
    bases: list[str] = []
    for token in command:
        base = token.rsplit("/", 1)[-1].lower()
        at = base.rfind("@")
        if at > 0:  # 剥离尾部@version pin（而不是前导@scope）
            base = base[:at]
        bases.append(base)
    for info in ACP_PROVIDERS.values():
        if any(
            base.startswith(pat) for base in bases for pat in info.agent_name_patterns
        ):
            return info
    return None


def build_session_model_meta(agent_name: str, acp_model: str | None) -> dict[str, Any]:
    """构建 ACP 会话 ``_meta`` 内容以供模型选择。

    返回字典以传播到 ``new_session()`` kwargs 中，以便提供者通过 ``_meta`` (i.e. 那些
    :attr:`~ACPProviderInfo.session_meta_key` 不是 ``None``）。

    当 *acp_model* 为 ``None`` 或检测到的提供程序使用 ``set_session_model`` 协议调用
    时，返回空字典。
    """
    if not acp_model:
        return {}
    provider = detect_acp_provider_by_agent_name(agent_name)
    if provider is None or provider.session_meta_key is None:
        return {}
    return {provider.session_meta_key: {"options": {"model": acp_model}}}
