"""智能体插件格式 (智能体-plugins.org)。

加载根级 ``plugin.json`` 反对一个封闭的 JSON  模式该功能本地 vendored 并由 manifest
自己选择 ``$schema`` -- 从未
从网络上获取过。

请参阅 ``openhands.sdk.plugin.format`` 包文档字符串了解设计。
"""

import json
from pathlib import Path
from typing import Any, ClassVar, Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.plugin.format.agent_plugins_mcp import (
    get_plugin_data_dir,
    load_mcp_servers,
)
from openhands.sdk.plugin.format.base import (
    PluginFormat,
    _load_schema,
    _read_command_definitions,
    _read_hooks_config,
)
from openhands.sdk.plugin.types import CommandDefinition, PluginManifest
from openhands.sdk.subagent.load import load_agents_from_dir
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.path import resolves_within


logger = get_logger(__name__)

# 在插件根目录，不像克劳德代码布局那样嵌套。
MANIFEST_FILE: Final[str] = "plugin.json"

# ：OpenHands'客户端扩展命名空间（规范§8）。 的反向域形式：openhands.dev，我们控制。 它
# 命名了：清单中的 ``extensions`` 成员和保存基于文件的：组件的顶级扩展 *directory*（第 8
# .2 节）。
#
EXTENSION_NAMESPACE: Final[str] = "dev.openhands"


# ：我们支持的唯一清单 ``$schema`` 及其供应商文件。 智能体：插件还发布了一个
# ``mcp.schema.json``，但这个与 ``mcp.json`` 加载器相关：声明 MCP：模式的 manifest 可以
# 与它兼容。
#
MANIFEST_SCHEMA_URL: Final[str] = (
    "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
)
_MANIFEST_SCHEMA_FILE: Final[str] = "plugin-1.0.0.schema.json"


class AgentPluginsFormat(PluginFormat):
    """智能体 Plugins v1.0.0 可移植包布局。

    ```
    plugin-name/
    ├── plugin.json              # 所需清单（根级，已关闭模式）
    ├── skills/                  # 智能体技能（可选）
    ├── mcp.json                 # MCP 服务器，无前导点（可选）
    └── dev.openhands/           # 我们的客户端扩展目录（可选）
        ├── commands/
        ├── agents/
        └── hooks/hooks.json
    ```

    挂钩、命令、智能体和 ``entry_command`` 不是可移植核心，因此它们位于我们的客户端扩
    展中（§8）：顶层下基于文件的组件
    ``dev.openhands/``目录下，``entry_command``下
    清单中的 ``extensions["dev.openhands"]``。 该目录内部的他们的文件布局与Claude代码
    格式相同，因此插件可以通过移动那些目录而不是
    重写它们来使用。 命名空间除我们之外的其他内容将被忽略，而不验证其内容。

    Args:
        plugin_data_root: 每个插件 ``PLUGIN_DATA`` 目录的父目录。
            默认为用户的插件数据目录； 可注入用于测试和将插件状态保存在其他地方的调用
            者。
    """

    name: ClassVar[str] = "agent-plugins"

    def __init__(self, *, plugin_data_root: Path | None = None) -> None:
        self._plugin_data_root = plugin_data_root

    @classmethod
    def detect(cls, plugin_dir: Path) -> bool:
        # 智能体插件元数据（坏JSON，不支持$模式）必须由load_manifest()来认领和拒绝，而不
        # 是通过Claude代码格式加载，这会用目录名称来推断名称。 没有 $模式键的 JSON 对象
        # 不会声明 this
        # 格式：其他工具(e.g. GitHub Copilot）还提供了根 plugin.json，
        # 因此此类插件会加载 Claude Code 布局。
        manifest_path = plugin_dir / MANIFEST_FILE
        if not manifest_path.is_file():
            return False
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return True
        return not isinstance(data, dict) or "$schema" in data

    def load_manifest(self, plugin_dir: Path) -> PluginManifest:
        """加载并验证根 ``plugin.json``。

        违规行为是致命的，除了两个规范标记为非致命的，它们被报告并被忽略：未知的顶级
        字段和非对象
        ``extensions``.

        没有 ``PluginManifest`` 列的字段（``$schema``、``homepage``、
        ``repository``, ``license``, ``keywords``, ``extensions``) 生存通过
        ``extra="allow"``. 我们自己的扩展数据另外投影到匹配的 ``PluginManifest`` 字段
        上，因此下游代码读取
        ``manifest.entry_command`` 无论它来自何种格式。

        Raises:
            ValueError: 任何明显的致命违规行为。
        """
        manifest_path = plugin_dir / MANIFEST_FILE
        if not resolves_within(manifest_path, plugin_dir):
            raise ValueError(
                f"Manifest {manifest_path} resolves outside the plugin root"
            )
        try:
            # utf-8-sig：容忍前导 BOM，RFC 8259 让我们忽略。
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {manifest_path}: {e}") from e
        except (OSError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to read manifest {manifest_path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(
                f"Manifest {manifest_path} must contain a JSON object, "
                f"got {type(data).__name__}"
            )

        schema_url = data.get("$schema")
        if schema_url != MANIFEST_SCHEMA_URL:
            raise ValueError(
                f"Unsupported or missing $schema in {manifest_path}: "
                f"{schema_url!r}. Supported: {MANIFEST_SCHEMA_URL}"
            )
        schema = _load_schema(_MANIFEST_SCHEMA_FILE)

        # 非致命：报告并忽略。 已知字段来自模式，因此没有第二个字段列表需要漂移。
        #
        unknown = sorted(set(data) - set(schema["properties"]))
        if unknown:
            logger.warning(
                "Ignoring unknown top-level field(s) in %s: %s",
                manifest_path,
                ", ".join(unknown),
            )
            data = {k: v for k, v in data.items() if k not in unknown}

        if "extensions" in data and not isinstance(data["extensions"], dict):
            logger.warning("Ignoring non-object 'extensions' in %s", manifest_path)
            data = {k: v for k, v in data.items() if k != "extensions"}

        # 其他一切都是致命的。 名称约束来自供应模式，而不是 Python 重新实现。
        #
        try:
            Draft202012Validator(schema).validate(data)
        except JSONSchemaValidationError as e:
            raise ValueError(
                f"Invalid Agent Plugins manifest {manifest_path}: {e.message}"
            ) from e

        return PluginManifest.model_validate(
            data | _extension_manifest_fields(data, manifest_path)
        )

    def load_mcp_config(self, plugin_dir: Path) -> dict[str, MCPServer]:
        """从根 ``mcp.json``（无前导点）加载 MCP 个服务器。

        与Claude代码格式不同，这里没有扩展。 智能体插件定义了两个确切的占位符，并禁止
        了其他任何类型，因此，一旦开始对话，就无法再扩展了机密 arrive.
        """
        plugin_root = plugin_dir.resolve()
        return load_mcp_servers(
            plugin_dir,
            plugin_root=plugin_root,
            plugin_data=get_plugin_data_dir(
                plugin_root, data_root=self._plugin_data_root
            ),
        )

    def load_hooks(self, plugin_dir: Path) -> HookConfig | None:
        """从 ``dev.openhands/hooks/hooks.json`` 加载钩子。"""
        return _read_hooks_config(plugin_dir / EXTENSION_NAMESPACE, plugin_dir)

    def load_agents(self, plugin_dir: Path) -> list[AgentDefinition]:
        """从 ``dev.openhands/agents/`` 加载智能体定义。"""
        return load_agents_from_dir(
            plugin_dir / EXTENSION_NAMESPACE / "agents", root=plugin_dir
        )

    def load_commands(self, plugin_dir: Path) -> list[CommandDefinition]:
        """从 ``dev.openhands/commands/`` 加载命令定义。"""
        return _read_command_definitions(plugin_dir / EXTENSION_NAMESPACE, plugin_dir)


def _extension_manifest_fields(
    data: dict[str, Any], manifest_path: Path
) -> dict[str, Any]:
    """将命名空间的清单数据映射到 ``PluginManifest`` 字段。

    仅读取 ``extensions["dev.openhands"]``。 其他命名空间会被忽略，而不检查其内容，正
    如第 8.1 节所要求的那样——携带错误类型的
    ``entry_command`` 的外国人命名空间是我们业务的 None。

    在我们自己的命名空间中，我们拥有验证，并应用了其他地方的相同狭窄失败边界：不可用
    的值报告并忽略，而不是拒绝插件。
    """
    # 清单已通过验证，因此 ``extensions``——如果仍然存在
    # -- 是一个对象，其值是对象。
    extension = data.get("extensions", {}).get(EXTENSION_NAMESPACE)
    if not extension:
        return {}

    entry_command = extension.get("entry_command")
    if entry_command is not None and not isinstance(entry_command, str):
        logger.warning(
            "Ignoring non-string '%s' entry_command in %s: %r",
            EXTENSION_NAMESPACE,
            manifest_path,
            entry_command,
        )
        entry_command = None

    return {"entry_command": entry_command} if entry_command else {}
