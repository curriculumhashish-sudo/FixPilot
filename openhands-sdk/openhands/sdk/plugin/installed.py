"""已安装 OpenHands SDK 的插件管理。

Public API 用于管理安装在用户主目录中的插件。 所有繁重的工作都委托给
``InstallationManager``。
"""

from __future__ import annotations

from pathlib import Path

from openhands.sdk.extensions.installation import (
    InstallationInfo,
    InstallationInterface,
    InstallationManager,
)
from openhands.sdk.plugin.plugin import Plugin
from openhands.sdk.utils.path import get_user_persistence_dir


# 公共类型别名 - 保持现有导入站点正常运行。
InstalledPluginInfo = InstallationInfo

DEFAULT_INSTALLED_PLUGINS_DIR = get_user_persistence_dir() / "plugins" / "installed"


def get_installed_plugins_dir() -> Path:
    """获取已安装插件的默认目录。"""
    return DEFAULT_INSTALLED_PLUGINS_DIR


# ---------------------------------------------------------------------------
# 内部帮手
# ---------------------------------------------------------------------------


class PluginInstallationInterface(InstallationInterface[Plugin]):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> Plugin:
        return Plugin.load(extension_dir)


def _resolve_installed_dir(installed_dir: Path | None) -> Path:
    return installed_dir if installed_dir is not None else DEFAULT_INSTALLED_PLUGINS_DIR


def _manager(installed_dir: Path) -> InstallationManager[Plugin]:
    return InstallationManager(
        installation_dir=installed_dir,
        installation_interface=PluginInstallationInterface(),
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def install_plugin(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    installed_dir: Path | None = None,
    force: bool = False,
) -> InstalledPluginInfo:
    """从源安装插件。

    Args:
        source: 插件源 — ``"github:owner/repo"``、git URL 或
            本地路径。
        ref: 可选的分支、标记或提交安装。
        repo_path: 存储库内的子目录路径（对于 monorepos）。
        installed_dir: 已安装插件的目录。
            默认为 ``~/.openhands/plugins/installed/``。
        force: 如果为 True，则覆盖现有安装。

    Returns:
        InstalledPluginInfo 包含有关安装的详细信息。
    """
    return _manager(_resolve_installed_dir(installed_dir)).install(
        source, ref=ref, repo_path=repo_path, force=force
    )


def uninstall_plugin(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称卸载插件。

    Returns:
        True 如果插件已卸载，False 如果插件未安装。
    """
    return _manager(_resolve_installed_dir(installed_dir)).uninstall(name)


def enable_plugin(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称启用已安装的插件。"""
    return _manager(_resolve_installed_dir(installed_dir)).enable(name)


def disable_plugin(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称禁用已安装的插件。"""
    return _manager(_resolve_installed_dir(installed_dir)).disable(name)


def list_installed_plugins(
    installed_dir: Path | None = None,
) -> list[InstalledPluginInfo]:
    """列出所有已安装的插件。

    自我修复：使元数据与磁盘上的内容保持一致。
    """
    return _manager(_resolve_installed_dir(installed_dir)).list_installed()


def load_installed_plugins(
    installed_dir: Path | None = None,
) -> list[Plugin]:
    """将所有已启用的已安装插件加载为 ``Plugin`` 对象。"""
    return _manager(_resolve_installed_dir(installed_dir)).load_installed()


def get_installed_plugin(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledPluginInfo | None:
    """获取有关特定已安装插件的信息。"""
    return _manager(_resolve_installed_dir(installed_dir)).get(name)


def update_plugin(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledPluginInfo | None:
    """将已安装的插件更新到最新版本。"""
    return _manager(_resolve_installed_dir(installed_dir)).update(name)
