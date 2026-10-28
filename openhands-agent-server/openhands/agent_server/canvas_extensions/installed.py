"""安装的画布扩展。

基于 ``openhands.sdk.extensions.installation`` 构建，与插件/技能共享，有两个特定于此
模块的行为：

``InstallationInfo.enabled`` 默认禁用 -- ``True`` 默认为
``InstallationManager.install()``，因此
，任何可以创建一个新条目的写入路径都会强制 ``enabled=False`` 作为写后步骤。

分阶段刷新 -- ``check``/``apply`` 替换 ``update()``/
``install(force=True)``，其中 rmtree+copytree 直接进入实时安装路径，没有暂存目录。
``check`` 获取并验证到
``.staging/`` 中，而不触及活动安装； ``apply`` 通过两次原子重命名来交换它（POSIX 不能
在一次重命名中原子地替换非空目录），如果第二次失败则回滚
。
"""

import os
import shutil
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from openhands.agent_server.canvas_extensions.manifest import (
    MANIFEST_FILENAME,
    CanvasExtensionManifest,
    resolve_entrypoint,
    resolve_icon,
)
from openhands.sdk.extensions.fetch import fetch_with_resolution
from openhands.sdk.extensions.installation import (
    InstallationInfo,
    InstallationInterface,
    InstallationManager,
    InstallationMetadata,
)
from openhands.sdk.extensions.installation.manager import DEFAULT_CACHE_DIR
from openhands.sdk.utils.path import get_user_persistence_dir


# 匹配 InstalledPluginInfo 命名约定。
InstalledCanvasExtensionInfo = InstallationInfo


def get_installed_canvas_extensions_dir() -> Path:
    """获取已安装画布扩展的默认目录。"""
    return get_user_persistence_dir() / "canvas-extensions" / "installed"


class CanvasExtensionInstallationInterface(
    InstallationInterface[CanvasExtensionManifest]
):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> CanvasExtensionManifest:
        manifest_path = extension_dir / MANIFEST_FILENAME
        manifest = CanvasExtensionManifest.model_validate_json(
            manifest_path.read_text()
        )
        # 遏制也必须成立——仅可解析的清单是不够的。
        resolve_entrypoint(manifest, extension_dir)
        return manifest


def _resolve_installed_dir(installed_dir: Path | None) -> Path:
    return (
        installed_dir
        if installed_dir is not None
        else get_installed_canvas_extensions_dir()
    )


def _manager(installed_dir: Path) -> InstallationManager[CanvasExtensionManifest]:
    return InstallationManager(
        installation_dir=installed_dir,
        installation_interface=CanvasExtensionInstallationInterface(),
    )


def _tracked_names(installed_dir: Path) -> set[str]:
    """具有真实、有效的跟踪条目的名称，而不仅仅是元数据键。

    一个没有匹配目录的过期记录不能被视为“已安装”——否则，这个名称的真实安装会错误地继
    承其状态，好像这是强制重新安装。
    """
    if not installed_dir.exists():
        return set()
    metadata = InstallationMetadata.load_from_dir(installed_dir)
    return {info.name for info in metadata.validate_tracked(installed_dir)}


def _force_disable_new(
    manager: InstallationManager[CanvasExtensionManifest],
    info: InstallationInfo,
    pre_existing: set[str],
) -> InstallationInfo:
    """将新创建的跟踪条目强制设置为 ``enabled=False``。

    ``pre_existing`` 将真正的新条目与强制重新安装区分开来，后者先前的启用状态已被保留
    。
    """
    if info.name in pre_existing or not info.enabled:
        return info
    manager.disable(info.name)
    info.enabled = False
    return info


def install_canvas_extension(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    installed_dir: Path | None = None,
    force: bool = False,
) -> InstalledCanvasExtensionInfo:
    """从源安装画布扩展。

    无论调用者传入什么内容，新创建的条目始终处于禁用状态。

    Args:
        source: ``"github:owner/repo"``、git URL 或本地路径。
        ref: 可选的分支、标记或提交安装。
        repo_path: 存储库内的子目录（对于 monorepos）。
        installed_dir: 默认为 ``~/.openhands/canvas-extensions/installed/``。
        force: 如果为 True，则覆盖现有安装。

    Returns:
        InstalledCanvasExtensionInfo 表示已安装的扩展。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manager = _manager(installed_dir)
    pre_existing = _tracked_names(installed_dir)
    info = manager.install(source, ref=ref, repo_path=repo_path, force=force)
    return _force_disable_new(manager, info, pre_existing)


def uninstall_canvas_extension(name: str, installed_dir: Path | None = None) -> bool:
    """按名称卸载画布扩展。

    也删除了任何未应用的预置更新 *name*因此，从未安装过的名称从未留下孤儿阶段槽。

    Returns:
        如果已卸载，则为 True；如果未安装，则为 False。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    uninstalled = _manager(installed_dir).uninstall(name)
    if uninstalled:
        shutil.rmtree(_staging_root(installed_dir) / name, ignore_errors=True)
    return uninstalled


def enable_canvas_extension(name: str, installed_dir: Path | None = None) -> bool:
    """按名称启用已安装的画布扩展。"""
    return _manager(_resolve_installed_dir(installed_dir)).enable(name)


def disable_canvas_extension(name: str, installed_dir: Path | None = None) -> bool:
    """按名称禁用已安装的画布扩展。"""
    return _manager(_resolve_installed_dir(installed_dir)).disable(name)


def list_installed_canvas_extensions(
    installed_dir: Path | None = None,
) -> list[InstalledCanvasExtensionInfo]:
    """列出所有已安装的画布扩展。

    自我修复如``InstallationManager.list_installed()``； 通过这种方式发现的目录也被禁
    用。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manager = _manager(installed_dir)
    pre_existing = _tracked_names(installed_dir)
    infos = manager.list_installed()
    return [_force_disable_new(manager, info, pre_existing) for info in infos]


def load_installed_canvas_extensions(
    installed_dir: Path | None = None,
) -> list[CanvasExtensionManifest]:
    """加载所有启用的画布扩展的清单。

    首先运行 ``list_installed_canvas_extensions``，因此在加载任何内容之前发现会被强制
    禁用 - 请参阅模块文档字符串。 将
    ``InstallationManager.load_installed()`` 自己的启用过滤器/加载逻辑镜像到更正的信
    息列表之上。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manager = _manager(installed_dir)
    manifests: list[CanvasExtensionManifest] = []
    for info in list_installed_canvas_extensions(installed_dir):
        if not info.enabled:
            continue
        extension_path = installed_dir / info.name
        if extension_path.exists():
            manifests.append(
                manager.installation_interface.load_from_dir(extension_path)
            )
    return manifests


def get_installed_canvas_extension(
    name: str, installed_dir: Path | None = None
) -> InstalledCanvasExtensionInfo | None:
    """获取有关特定已安装画布扩展的信息。"""
    return _manager(_resolve_installed_dir(installed_dir)).get(name)


def get_installed_canvas_extension_manifest(
    name: str, installed_dir: Path | None = None
) -> CanvasExtensionManifest | None:
    """加载已安装扩展的经过验证的清单。

    根据实时安装路径重新读取并重新验证存储的清单 - 安装时验证的副本可能已在磁盘上更改
    。

    Returns:
        None 如果未安装，或者安装不再有效。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    if get_installed_canvas_extension(name, installed_dir) is None:
        return None
    try:
        return CanvasExtensionInstallationInterface.load_from_dir(installed_dir / name)
    except (ValidationError, ValueError, OSError):
        return None


def get_canvas_extension_bundle_path(
    name: str, installed_dir: Path | None = None
) -> Path | None:
    """解析 *name* 的入口捆绑文件的磁盘路径。

    在每次调用时，重新验证包的元数据和入口包含 -- 这个功能支持 bundle serve，因此在安
    装时所做的检查是不够的（因为一个符号链接可能会在请求之间改变）。

    Returns:
        None 如果未安装，或者安装不再有效。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manifest = get_installed_canvas_extension_manifest(name, installed_dir)
    if manifest is None:
        return None
    return resolve_entrypoint(manifest, installed_dir / name)


def get_canvas_extension_icon_path(
    name: str, installed_dir: Path | None = None
) -> Path | None:
    """解析 *name* 的图标文件，重新检查包的包含情况。

    Returns:
        None 如果未安装，则不会声明图标，或者图标不会解析为包含的文件。 损坏的图标永
        远不会影响清单本身。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manifest = get_installed_canvas_extension_manifest(name, installed_dir)
    if manifest is None:
        return None
    with suppress(ValueError, OSError):
        return resolve_icon(manifest, installed_dir / name)
    return None


class CanvasExtensionUpdateCheck(BaseModel):
    """``check_canvas_extension_update`` 的结果。

    活动安装未受影响； 仅写入``.staging/``。 通行证
    ``resolved_ref`` 返回 ``apply_canvas_extension_update`` 以确认此确切的暂存内容并
    将其交换到位。
    """

    requested_ref: str | None = Field(
        description="Ref the staged fetch was resolved against"
    )
    resolved_ref: str | None = Field(
        description="Commit SHA the staged content was resolved to"
    )
    validated: bool = Field(
        description="Whether staged content passed validation; only True may be applied"
    )


def _staging_root(installed_dir: Path) -> Path:
    return installed_dir / ".staging"


def _staged_path(installed_dir: Path, name: str, resolved_ref: str | None) -> Path:
    """(*name*, *resolved_ref*) 的暂存槽的路径。

    *resolved_ref* 不受信任（``apply_canvas_extension_update`` 认为
    作为调用者提供的参数），因此如果它可以转义暂存目录，则会被拒绝 - 与 manifest.py
    中的 ``entrypoint`` 相同的检查。
    """
    if resolved_ref is not None and (
        not resolved_ref
        or resolved_ref.startswith("/")
        or ".." in Path(resolved_ref).parts
    ):
        raise ValueError(f"Invalid resolved_ref: {resolved_ref!r}")
    return _staging_root(installed_dir) / name / (resolved_ref or "local")


def _stage_fetched_content(
    installed_dir: Path, name: str, resolved_ref: str | None, fetched_path: Path
) -> Path:
    """将获取的内容复制到 *name* 的干净暂存槽中。

    首先清除任何先前暂存的候选项——每个分机一次最多保留一个候选项。
    """
    slot_root = _staging_root(installed_dir) / name
    shutil.rmtree(slot_root, ignore_errors=True)
    staged_path = _staged_path(installed_dir, name, resolved_ref)
    # symlinks=True: dereferencing here would copy a malicious symlink's
    # 目标作为普通文件，击败下面的遏制验证。
    shutil.copytree(fetched_path, staged_path, symlinks=True)
    return staged_path


def _load_validated_manifest(
    staged_path: Path, expected_name: str
) -> CanvasExtensionManifest:
    """加载并验证分阶段扩展的清单。

    如果清单格式错误、其入口转义包根或其名称不再匹配 *expected_name*，则引发。
    """
    manifest = CanvasExtensionInstallationInterface.load_from_dir(staged_path)
    if manifest.name != expected_name:
        raise ValueError(
            f"Staged content for {expected_name!r} declares a different "
            f"name {manifest.name!r}; refusing to treat it as an update"
        )
    return manifest


def check_canvas_extension_update(
    name: str, installed_dir: Path | None = None
) -> CanvasExtensionUpdateCheck | None:
    """检查 *name* 的更新，暂存并验证它。

    将跟踪源的原始引用（绝不是“最新”）重新获取到 ``.staging/`` 中； 活动安装未受影响
    。 参见
    ``apply_canvas_extension_update`` 用于将其交换到位的步骤。

    Args:
        name: 要检查的已安装扩展的名称。
        installed_dir: 默认为 ``~/.openhands/canvas-extensions/installed/``。

    Returns:
        None 如果未安装，则结果为 - 仅在 ``validated`` 时适用。

    Raises:
        ValueError: 如果 *name* 不是有效的 kebab-case。
        ExtensionFetchError: 如果获取跟踪源失败。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manager = _manager(installed_dir)
    current_info = manager.get(name)
    if current_info is None:
        return None

    fetched_path, resolved_ref = fetch_with_resolution(
        source=current_info.source,
        cache_dir=DEFAULT_CACHE_DIR,
        ref=current_info.requested_ref,
        repo_path=current_info.repo_path,
        update=True,
    )

    staged_path = _stage_fetched_content(
        installed_dir, name, resolved_ref, fetched_path
    )
    try:
        _load_validated_manifest(staged_path, name)
        validated = True
    except (ValidationError, ValueError, OSError):
        validated = False
        shutil.rmtree(staged_path.parent, ignore_errors=True)

    return CanvasExtensionUpdateCheck(
        requested_ref=current_info.requested_ref,
        resolved_ref=resolved_ref,
        validated=validated,
    )


def apply_canvas_extension_update(
    name: str,
    resolved_ref: str | None,
    enabled: bool,
    installed_dir: Path | None = None,
) -> InstalledCanvasExtensionInfo | None:
    """应用之前检查和验证的更新。

    *resolved_ref* 必须与已通过验证的分阶段候选者匹配
    ``check_canvas_extension_update``，确认正在应用的内容。 以原子方式将暂存内容交换
    到活动安装路径中；
    *enabled* 始终显式应用，从不继承。

    Args:
        name: 要更新的已安装扩展的名称。
        resolved_ref: 来自之前经过验证的检查的 ``resolved_ref``。
        enabled: 启用状态以应用于新包。
        installed_dir: 默认为 ``~/.openhands/canvas-extensions/installed/``。

    Returns:
        None 如果未安装，则 InstallationInfo 表示新捆绑包。

    Raises:
        ValueError: 如果 *name* 无效，*resolved_ref* 可以转义
            暂存目录，或没有经过验证的暂存候选目录与之匹配
            ——先打电话检查一下。
    """
    installed_dir = _resolve_installed_dir(installed_dir)
    manager = _manager(installed_dir)
    current_info = manager.get(name)
    if current_info is None:
        return None

    staged_path = _staged_path(installed_dir, name, resolved_ref)
    if not staged_path.is_dir():
        raise ValueError(
            f"No validated staged update found for {name!r} at ref "
            f"{resolved_ref!r}. Call check_canvas_extension_update() first."
        )
    manifest = _load_validated_manifest(staged_path, name)

    install_path = installed_dir / name
    backup_path = _staging_root(installed_dir) / f"{name}.previous"
    shutil.rmtree(backup_path, ignore_errors=True)

    # POSIX rename() 无法自动替换非空目录，因此活动包首先移到一边； 如果第二次重命名失败
    # 则回滚。
    #
    os.replace(install_path, backup_path)
    try:
        os.replace(staged_path, install_path)
    except OSError:
        os.replace(backup_path, install_path)
        raise
    shutil.rmtree(backup_path, ignore_errors=True)
    shutil.rmtree(_staging_root(installed_dir) / name, ignore_errors=True)

    info = InstallationInfo.from_extension(
        manifest,
        source=current_info.source,
        install_path=install_path,
        requested_ref=current_info.requested_ref,
        resolved_ref=resolved_ref,
        repo_path=current_info.repo_path,
    )
    info.enabled = enabled

    with manager.metadata_session as session:
        session.extensions[name] = info

    return info
