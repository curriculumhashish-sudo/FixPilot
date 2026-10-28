from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from openhands.sdk.extensions.fetch import (
    SourceType,
    fetch_with_resolution,
    resolve_extension_source,
)
from openhands.sdk.extensions.installation.info import InstallationInfo
from openhands.sdk.extensions.installation.interface import (
    ExtensionProtocol,
    InstallationInterface,
)
from openhands.sdk.extensions.installation.metadata import (
    InstallationMetadata,
    MetadataSession,
)
from openhands.sdk.extensions.installation.utils import validate_extension_name
from openhands.sdk.git.utils import extract_repo_name
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import get_user_persistence_dir
from openhands.sdk.utils.redact import redact_url_credentials


logger = get_logger(__name__)

DEFAULT_CACHE_DIR = get_user_persistence_dir() / "cache" / "extensions"


@dataclass
class InstallationManager[T: ExtensionProtocol]:
    """用于安装、跟踪和加载扩展的通用管理器。

    由满足 ``ExtensionProtocol`` 的任何类型 ``T`` 进行参数化。 同伴
    ``InstallationInterface[T]`` 告诉管理器
    如何从磁盘上的目录加载 ``T``； 其他一切（获取、复制、元数据簿记）都是通用处理的。

    Attributes:
        installation_dir: 安装扩展的根目录。
        installation_interface: 知道如何从目录加载 ``T``。
    """

    installation_dir: Path
    installation_interface: InstallationInterface[T]

    def __post_init__(self) -> None:
        self.installation_dir = self.installation_dir.resolve()

    @property
    def metadata_session(self) -> MetadataSession:
        """打开绑定到该管理器的目录和接口的元数据会话。"""
        return InstallationMetadata.open(
            self.installation_dir, interface=self.installation_interface
        )

    def install(
        self,
        source: str | Path,
        ref: str | None = None,
        repo_path: str | None = None,
        force: bool = False,
    ) -> InstallationInfo:
        """从源安装扩展。

        从源获取扩展，将其复制到安装目录，并记录安装元数据。 当 ``force=True`` 覆盖现
        有安装时，将保留先前的 ``enabled`` 状态。

        Args:
            source: 扩展源 — 可以是 ``"github:owner/repo"``
                简写、任何 git URL 或本地文件系统路径。
            ref: 可选的分支、标记或提交安装。
            repo_path: 存储库内的子目录路径（对于 monorepos）。
            force: 如果为 True，则覆盖现有安装。 如果 False，则提高
                如果扩展已安装，则会出现错误。

        Returns:
            InstallationInfo 包含有关安装的详细信息。

        Raises:
            ExtensionFetchError: 如果获取扩展失败。
            FileExistsError: 如果扩展已安装并且force=False。
            ValueError: 如果扩展名无效。
        """
        return self._install(source, ref=ref, repo_path=repo_path, force=force)

    def _install(
        self,
        source: str | Path,
        ref: str | None = None,
        repo_path: str | None = None,
        force: bool = False,
        root_name: str | None = None,
    ) -> InstallationInfo:
        """像``install``一样安装； ``root_name`` 命名存储库根。

        ``root_name`` 将存储库的名称替换为从中加载不带 ``repo_path`` 的远程源的目录名
        称（请参阅
        ``_load_fetched``). ``update`` 传递安装的名称，因此以其他名称安装的扩展会保留
        它。
        """
        if isinstance(source, Path):
            source = str(source)

        logger.info(f"Fetching extension from {redact_url_credentials(source)}")
        fetched_path, resolved_ref = fetch_with_resolution(
            source=source,
            cache_dir=DEFAULT_CACHE_DIR,
            ref=ref,
            repo_path=repo_path,
            update=True,
        )

        extension = self._load_fetched(fetched_path, source, repo_path, root_name)
        validate_extension_name(extension.name)

        install_path = self.installation_dir / extension.name
        if install_path.exists() and not force:
            raise FileExistsError(
                f"Extension '{extension.name}' is already installed"
                f" at {install_path}. Use force=True to overwrite."
            )

        if install_path.exists():
            logger.info(f"Removing existing installation of '{extension.name}'")
            shutil.rmtree(install_path)

        logger.info(f"Installing extension '{extension.name}' to {install_path}")
        self.installation_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fetched_path, install_path)

        info = InstallationInfo.from_extension(
            extension,
            source=source,
            install_path=install_path,
            requested_ref=ref,
            resolved_ref=resolved_ref,
            repo_path=repo_path,
        )

        with self.metadata_session as session:
            existing = session.extensions.get(extension.name)
            if existing is not None:
                info.enabled = existing.enabled
            session.extensions[extension.name] = info

        logger.info(
            f"Successfully installed extension '{extension.name}' v{info.version}"
        )
        return info

    def _load_fetched(
        self,
        fetched_path: Path,
        source: str,
        repo_path: str | None,
        root_name: str | None = None,
    ) -> T:
        """加载获取的扩展，如果它是一个，则以其存储库命名。

        没有显式或嵌入子路径的远程源将被提取到其克隆缓存 ``<repo>-<hash>``。 一个从目
        录名称推断名称的加载器（没有manifest的插件）必须使用
         ``<repo>``，就像它对本地目录一样，因此从带有那个名称的副本加载。
        """
        source_type, url, repo_path = resolve_extension_source(source, repo_path)
        if repo_path or source_type == SourceType.LOCAL:
            return self.installation_interface.load_from_dir(fetched_path)

        with tempfile.TemporaryDirectory() as staging:
            load_path = Path(staging) / (root_name or extract_repo_name(url))
            shutil.copytree(
                fetched_path,
                load_path,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git"),
            )
            return self.installation_interface.load_from_dir(load_path)

    def uninstall(self, name: str) -> bool:
        """按名称卸载扩展。

        只能卸载元数据中跟踪的扩展。 这可以防止意外删除安装目录中恰好存在的任意目录。
         如果扩展的目录已被删除，元数据条目仍会被清除。

        Args:
            name: 要卸载的扩展的名称。

        Returns:
            True 如果扩展已卸载，False 如果未跟踪。

        Raises:
            ValueError: 如果 *name* 不是有效的 kebab-case。
        """
        validate_extension_name(name)

        with self.metadata_session as session:
            if name not in session.extensions:
                logger.warning(f"Extension '{name}' is not installed")
                return False

            extension_path = self.installation_dir / name
            if extension_path.exists():
                logger.info(f"Uninstalling extension '{name}' from {extension_path}")
                shutil.rmtree(extension_path)
            else:
                logger.warning(
                    f"Extension '{name}' was tracked but {extension_path} is missing"
                )

            del session.extensions[name]

        logger.info(f"Successfully uninstalled extension '{name}'")
        return True

    def _set_enabled(
        self,
        name: str,
        enabled: bool,
    ) -> bool:
        """设置已安装扩展的启用状态。

        在检查之前同步元数据，因此陈旧或未跟踪的条目首先得到协调。 如果未安装扩展或其
        目录丢失，则返回 False。
        """
        validate_extension_name(name)

        if not self.installation_dir.exists():
            logger.warning(
                f"Installation directory does not exist: {self.installation_dir}"
            )
            return False

        with self.metadata_session as session:
            session.sync()

            info = session.extensions.get(name)
            if info is None:
                logger.warning(f"Extension '{name}' is not installed")
                return False

            extension_path = self.installation_dir / name
            if not extension_path.exists():
                logger.warning(
                    f"Extension '{name}' was tracked but {extension_path} is missing"
                )
                return False

            if info.enabled == enabled:
                return True

            info.enabled = enabled
            session.extensions[name] = info

        state = "enabled" if enabled else "disabled"
        logger.info(f"Successfully {state} extension '{name}'")
        return True

    def enable(self, name: str) -> bool:
        """按名称启用已安装的扩展。"""
        return self._set_enabled(name, True)

    def disable(self, name: str) -> bool:
        """按名称禁用已安装的扩展。"""
        return self._set_enabled(name, False)

    def list_installed(self) -> list[InstallationInfo]:
        """列出所有已安装的扩展。

        自我修复：更新元数据文件以删除已删除目录的条目，并添加扩展目录的条目，这些目
        录是手动复制到安装目录中的。

        Returns:
            每个已安装扩展的 InstallationInfo 列表。
        """
        if not self.installation_dir.exists():
            return []

        with self.metadata_session as session:
            return session.sync()

    def load_installed(self) -> list[T]:
        """将所有启用的扩展加载为 ``T`` 对象。

        首先调用 ``list_installed()``（同步元数据），然后通过安装界面加载每个启用的扩
        展。 禁用的扩展将被跳过。

        Returns:
            已加载类型 ``T`` 的扩展对象的列表。
        """
        if not self.installation_dir.exists():
            return []

        extensions: list[T] = []

        for info in self.list_installed():
            if not info.enabled:
                continue

            extension_path = self.installation_dir / info.name
            if extension_path.exists():
                extension = self.installation_interface.load_from_dir(extension_path)
                extensions.append(extension)

        return extensions

    def get(self, name: str) -> InstallationInfo | None:
        """获取有关特定已安装扩展的信息。

        如果元数据中未跟踪扩展或其目录不再存在于磁盘上，则返回 ``None``。

        Args:
            name: 要查找的扩展名。

        Returns:
            如果安装了扩展，则为 InstallationInfo，否则为 None。

        Raises:
            ValueError: 如果 *name* 不是有效的 kebab-case。
        """
        validate_extension_name(name)

        metadata = InstallationMetadata.load_from_dir(self.installation_dir)
        info = metadata.extensions.get(name)

        if info is not None:
            extension_path = self.installation_dir / name
            if not extension_path.exists():
                return None

        return info

    def update(self, name: str) -> InstallationInfo | None:
        """将已安装的扩展更新到最新版本。

        使用 ``ref=None`` (i.e. 最新的可用）并强制重新安装它。 上一个
        ``enabled`` 状态被保留，因为 ``install(force=True)`` 继承了它。 没有清单的存
        储库根保留其安装名称。

        Args:
            name: 要更新的扩展名。

        Returns:
            如果成功则更新 InstallationInfo，如果未安装扩展则更新 None。

        Raises:
            ExtensionFetchError: 如果获取更新的扩展失败。
            ValueError: 如果 *name* 不是有效的 kebab-case。
        """
        validate_extension_name(name)

        current_info = self.get(name)
        if current_info is None:
            logger.warning(f"Extension {name} not installed")
            return None

        redacted = redact_url_credentials(current_info.source)
        logger.info(f"Updating extension {name} from {redacted}")
        return self._install(
            source=current_info.source,
            ref=None,
            repo_path=current_info.repo_path,
            force=True,
            root_name=name,
        )
