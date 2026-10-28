"""Claude Code 插件格式（OpenHands' 原始布局）。

这是 Claude-Code 风格插件目录的具体：class:
`~openhands.sdk.plugin.format.base.PluginFormat` 策略。 这是
通用的
fallback: 它的：meth:`ClaudeCodePluginFormat.detect` 接受任何目录，
当 None 存在时，从目录名称推断清单。

请参阅 ``openhands.sdk.plugin.format`` 包文档字符串了解设计概述和添加新格式的方法。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Final

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config
from openhands.sdk.plugin.format.base import (
    PluginFormat,
    _read_command_definitions,
    _read_hooks_config,
)
from openhands.sdk.plugin.types import (
    CommandDefinition,
    PluginAuthor,
    PluginManifest,
)
from openhands.sdk.skills.utils import load_mcp_config
from openhands.sdk.subagent.load import load_agents_from_dir
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.path import resolves_within


logger = get_logger(__name__)

# 克劳德代码布局按顺序检查（嵌套）清单的目录。
PLUGIN_MANIFEST_DIRS: Final[list[str]] = [".plugin", ".claude-plugin"]
PLUGIN_MANIFEST_FILE: Final[str] = "plugin.json"


class ClaudeCodePluginFormat(PluginFormat):
    """Claude Code 插件布局（OpenHands'原始格式）。

    ```
    plugin-name/
    ├── .claude-plugin/           # 或.plugin/
    │   └── plugin.json          # 插件元数据（嵌套）
    ├── commands/                # 斜线命令（可选）
    ├── agents/                  # 专业智能体（可选）
    ├── skills/                  # 智能体技能（可选）
    ├── hooks/                   # 事件处理程序（可选）
    │   └── hooks.json
    ├── .mcp.json                # 外部工具配置（可选）
    └── README.md                # 插件文档
    ```
    """

    name: ClassVar[str] = "claude-code"

    @classmethod
    def detect(cls, plugin_dir: Path) -> bool:  # noqa: ARG003
        # 克劳德代码格式是回退方案：它接受任何目录，当 None 存在时从目录名称推断清单。
        #
        return True

    def load_manifest(self, plugin_dir: Path) -> PluginManifest:
        """从 ``plugin.json`` 加载插件清单。

        检查 ``.plugin/`` 和 ``.claude-plugin/`` 目录。 如果未找到清单，则退回到从目
        录名称推断。
        """
        manifest_path = None

        for manifest_dir in PLUGIN_MANIFEST_DIRS:
            candidate = plugin_dir / manifest_dir / PLUGIN_MANIFEST_FILE
            # follow_symlinks=False: a dangling link must be rejected, not skipped.
            if candidate.exists(follow_symlinks=False):
                manifest_path = candidate
                break

        if manifest_path:
            if not resolves_within(manifest_path, plugin_dir):
                raise ValueError(
                    f"Manifest {manifest_path} resolves outside the plugin root"
                )
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    data = json.load(f)

                # 处理作者字段 - 可以是字符串或对象
                if "author" in data and isinstance(data["author"], str):
                    data["author"] = PluginAuthor.from_string(
                        data["author"]
                    ).model_dump()

                return PluginManifest.model_validate(data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {manifest_path}: {e}") from e
            except Exception as e:
                raise ValueError(
                    f"Failed to parse manifest {manifest_path}: {e}"
                ) from e

        # 回退到从目录名称推断
        logger.debug(
            f"No manifest found for {plugin_dir}, inferring from directory name"
        )
        return PluginManifest(
            name=plugin_dir.name,
            version="1.0.0",
            description=f"Plugin loaded from {plugin_dir.name}",
        )

    def load_mcp_config(self, plugin_dir: Path) -> dict[str, MCPServer]:
        """从 ``.mcp.json`` 加载 MCP 配置。

        Note: 变量在插件加载期间完全扩展不。 仅
        SKILL_ROOT 被扩展（因为 plugin_dir 已知）。 其他变量（如 ${VAR:-default}）被
        保留为占位符，以便稍后在每个对话机密可用
        时（在 LocalConversation._ensure_plugins_loaded() 中）进行扩展。

        这可以防止双重扩展错误，即在机密可用之前在插件加载期间应用默认值。
        """
        mcp_json = plugin_dir / ".mcp.json"
        if not mcp_json.exists() or not resolves_within(mcp_json, plugin_dir):
            return {}

        try:
            # expand_defaults=False: preserve ${VAR:-default} placeholders for
            # 稍后通过每个对话进行扩展机密。 现在仅扩展了SKILL_ROOT。
            #
            config = load_mcp_config(
                mcp_json, skill_root=plugin_dir, expand_defaults=False
            )
            if config and "mcpServers" in config:
                logger.info(
                    "Loaded MCP config from %s with %d server(s)",
                    mcp_json,
                    len(config["mcpServers"]),
                )
            servers = config.get("mcpServers", {}) if isinstance(config, dict) else {}
            return coerce_mcp_config(servers)
        except Exception as e:
            logger.warning(f"Failed to load MCP config from {mcp_json}: {e}")
            return {}

    def load_hooks(self, plugin_dir: Path) -> HookConfig | None:
        """从 ``hooks/hooks.json`` 加载钩子配置。"""
        return _read_hooks_config(plugin_dir)

    def load_agents(self, plugin_dir: Path) -> list[AgentDefinition]:
        """从 ``agents/`` 目录加载智能体定义。"""
        return load_agents_from_dir(plugin_dir / "agents", root=plugin_dir)

    def load_commands(self, plugin_dir: Path) -> list[CommandDefinition]:
        """从 ``commands/`` 目录加载命令定义。"""
        return _read_command_definitions(plugin_dir)
