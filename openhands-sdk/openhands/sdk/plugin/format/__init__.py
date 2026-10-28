"""插件格式策略。

*插件格式*拥有与插件在磁盘上的布局方式相关的所有内容（清单位置和验证、MCP配置文件和变
量扩展，以及客户端扩展 - 命令 / 智能体 / 钩子 - 活动的位置）并将插件目
录转换为规范化的：class:`~openhands.sdk.plugin.Plugin`。 加载插件下游的所有内容都是与
格式无关的，并且依赖于 ``Plugin`` 本身
，因此添加新格式永远不会触及合并/应用路径。

模块布局：

- ``base`` — 抽象：class:`PluginFormat` 合约加上共享发现逻辑（技能发现、最终组装）。
- ``claude_code`` — 具体的：class:`ClaudeCodePluginFormat` 策略。
- ``agent_plugins`` — :class:`AgentPluginsFormat` 策略，它还拥有我们的
``dev.openhands`` 客户端扩展命名
空间和 ``agent_plugins_mcp``，它的 ``mcp.json`` 加载器。
- 该包 ``__init__`` — 格式注册表 (``_FORMATS``) 和
  :func:`detect_format` 调度程序。

:func:`detect_format` 返回 ``_FORMATS`` 中的第一个格式，其
:meth:`PluginFormat.detect` 返回 True。 智能体插件优先，因为它是
具体的 - 根 ``plugin.json`` - 克劳德代码最后，因为它的 ``detect`` 接受任何目录，使其
成为通用的回退方案。

如何添加新的插件格式
------------------------------
1. 在此包中创建一个模块并子类：class:`PluginFormat`，为其提供唯一的类级别 ``name``（
在日志中使用）。
2. 实现：meth:`PluginFormat.detect` — 便宜、具体，并且 True 仅适用于该格式应声明的目
录。
3. 实现特定于格式的加载器 (:meth:`~PluginFormat.load_manifest`,
   ：方法：`~PluginFormat.load_mcp_config`，：方法：`~PluginFormat.load_hooks`，
   ：方法：`~PluginFormat.load_agents`，：方法：`~PluginFormat.load_commands`）。 每
   个
   拥有一种组件类型，应该隔离其自身的故障，而不是中止整个插件。
4. 重用共享行为的基础——尤其是
   :meth:`~PluginFormat.load_skills` （``skills/<name>/SKILL.md`` 规则）和
   :meth:`~PluginFormat.load`（最终组装）； 你不需要覆盖
   要么。
5. 按检测优先顺序在下面的 ``_FORMATS`` 中注册类（较早 = 较高优先级； 回退方案最后）。
6. 添加：func:`detect_format` 选择测试（请参阅
   ``tests/sdk/plugin/test_plugin_loading.py::TestDetectFormat``).
"""

from __future__ import annotations

from pathlib import Path

from openhands.sdk.logger import get_logger
from openhands.sdk.plugin.format.agent_plugins import AgentPluginsFormat
from openhands.sdk.plugin.format.base import PluginFormat
from openhands.sdk.plugin.format.claude_code import ClaudeCodePluginFormat


logger = get_logger(__name__)


# 注册格式，按检测优先顺序排列。 优先级较高的格式优先； Claude Code 格式排在最后，因为它
# 接受任何目录。
#
_FORMATS: list[type[PluginFormat]] = [AgentPluginsFormat, ClaudeCodePluginFormat]


def detect_format(plugin_dir: Path) -> PluginFormat:
    """选择 ``plugin_dir`` 的插件格式。

    Precedence: ``detect()`` 返回 True 的第一个注册格式。 的
    克劳德代码格式无条件匹配，因此总是可以解决。
    """
    for fmt_cls in _FORMATS:
        if fmt_cls.detect(plugin_dir):
            logger.debug(f"Detected plugin format '{fmt_cls.name}' for {plugin_dir}")
            return fmt_cls()
    # 当 ClaudeCodePluginFormat.detect() 返回 True 时无法访问，但如果发生变化，则保留显
    # 式的、可操作的错误，而不是隐式的 None。
    #
    raise ValueError(f"No plugin format matched {plugin_dir}")


__all__ = [
    "PluginFormat",
    "AgentPluginsFormat",
    "ClaudeCodePluginFormat",
    "detect_format",
]
