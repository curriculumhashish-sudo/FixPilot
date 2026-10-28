from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from openhands.sdk.extensions.installation.info import InstallationInfo
from openhands.sdk.extensions.installation.interface import (
    InstallationInterface,
)
from openhands.sdk.extensions.installation.utils import validate_extension_name
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class MetadataSession:
    """上下文管理器将 ``InstallationMetadata`` 绑定到其目录。

    干净退出时（也不例外），元数据会自动保存。 这消除了调用者手动配对
    ``load_from_dir`` 和 ``save_to_dir`` 的需要，并保证突变是已持
    久化。

    通过 ``InstallationMetadata.open(installed_dir)`` 使用。
    """

    def __init__(
        self,
        installed_dir: Path,
        metadata: InstallationMetadata,
        interface: InstallationInterface | None = None,
    ) -> None:
        self.installed_dir = installed_dir
        self.metadata = metadata
        self.interface = interface

    @property
    def extensions(self) -> dict[str, InstallationInfo]:
        return self.metadata.extensions

    def sync(self) -> list[InstallationInfo]:
        """使元数据与磁盘上的实际内容保持一致。

        修剪目录丢失的陈旧跟踪条目并发现未跟踪的扩展目录。 **不**保存 - 退出时封闭的
        ``with``块处理持久化。

        要求在创建会话时提供 ``InstallationInterface``（通过
        ``InstallationMetadata.open(..., interface=...)``）。

        Returns:
            有效跟踪和新发现的扩展程序的组合列表。
        """
        assert self.interface is not None, (
            "sync() requires an InstallationInterface; "
            "pass interface= to InstallationMetadata.open()"
        )
        valid = self.metadata.validate_tracked(self.installed_dir)
        discovered = self.metadata.discover_untracked(
            self.installed_dir, self.interface
        )
        return valid + discovered

    def __enter__(self) -> MetadataSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.metadata.save_to_dir(self.installed_dir)


class InstallationMetadata(BaseModel):
    """用于跟踪已安装扩展的元数据文件。

    通常通过 ``open()`` 上下文管理器使用，加载元数据，生成 ``MetadataSession``，并在
    退出时自动保存：:

        with InstallationMetadata.open(installed_dir) as session:
            session.extensions["my-ext"] = info
        # 自动保存
    """

    extensions: dict[str, InstallationInfo] = Field(
        default_factory=dict,
        description="Map from extension name to extension installation info",
    )

    metadata_filename: ClassVar[str] = ".installed.json"
    _LEGACY_KEYS: ClassVar[tuple[str, ...]] = ("plugins", "skills")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_keys(cls, data: Any) -> Any:
        """将旧的 ``plugins`` / ``skills`` 键迁移到 ``extensions``。

        旧条目将合并到现有的 ``extensions`` 字典（如果有）中。 显式的 ``extensions``
        条目在关键冲突上获胜。
        """
        if not isinstance(data, dict):
            return data
        merged: dict[str, Any] = {}
        for legacy_key in cls._LEGACY_KEYS:
            if legacy_key in data:
                logger.warning(
                    "Migrating legacy %r key to 'extensions'",
                    legacy_key,
                )
                merged.update(data.pop(legacy_key))
        if merged:
            merged.update(data.get("extensions") or {})
            data["extensions"] = merged
        return data

    @classmethod
    def open(
        cls,
        installed_dir: Path,
        *,
        interface: InstallationInterface | None = None,
    ) -> MetadataSession:
        """加载元数据并返回退出时自动保存的会话。

        Args:
            installed_dir: 安装扩展的根目录。
            interface: 可选安装接口，如果需要
                会话将调用``sync()``。
        """
        return MetadataSession(
            installed_dir, cls.load_from_dir(installed_dir), interface
        )

    @classmethod
    def get_metadata_path(cls, installed_dir: Path) -> Path:
        """获取已安装扩展目录的元数据文件路径。"""
        return installed_dir / cls.metadata_filename

    @classmethod
    def load_from_dir(cls, installed_dir: Path) -> InstallationMetadata:
        """从已安装的扩展目录加载元数据。"""
        metadata_path = cls.get_metadata_path(installed_dir)
        if not metadata_path.exists():
            return cls()

        try:
            return cls.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load installed extension metadata: {e}")
            return cls()

    def save_to_dir(self, installed_dir: Path) -> None:
        """将元数据保存到已安装的扩展目录。"""
        metadata_path = self.get_metadata_path(installed_dir)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def validate_tracked(self, installed_dir: Path) -> list[InstallationInfo]:
        """验证磁盘上是否存在跟踪的扩展。

        删除名称无效或缺少目录的条目
        ``self.extensions``到位。

        Returns:
            仍然有效的扩展列表。
        """
        valid_extensions: list[InstallationInfo] = []

        # 迭代快照是因为我们在循环期间发生了变化。
        for name, info in list(self.extensions.items()):
            try:
                validate_extension_name(name)
            except ValueError as e:
                logger.warning(
                    f"Invalid tracked extension name {name!r}, removing: {e}"
                )
                del self.extensions[name]
                continue

            extension_path = installed_dir / name
            if extension_path.exists():
                valid_extensions.append(info)
            else:
                logger.warning(
                    f"Extension {name} directory missing, removing from metadata"
                )
                del self.extensions[name]

        return valid_extensions

    def discover_untracked(
        self,
        installed_dir: Path,
        installation_interface: InstallationInterface,
    ) -> list[InstallationInfo]:
        """发现元数据未跟踪的扩展目录。

        将新发现的扩展添加到适当的位置 ``self.extensions``。

        Returns:
            新发现的扩展列表。
        """
        discovered: list[InstallationInfo] = []

        for item in sorted(installed_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue

            if item.name in self.extensions:
                continue

            try:
                validate_extension_name(item.name)
            except ValueError:
                logger.debug(f"Skipping directory with invalid extension name: {item}")
                continue

            try:
                extension = installation_interface.load_from_dir(item)
            except Exception as e:
                logger.debug(f"Skipping directory {item}: {e}")
                continue

            if extension.name != item.name:
                logger.warning(
                    "Skipping extension directory because manifest name"
                    " doesn't match directory name:"
                    f" dir={item.name!r}, manifest={extension.name!r}"
                )
                continue

            info = InstallationInfo.from_extension(
                extension, source="local", install_path=item
            )

            discovered.append(info)
            self.extensions[item.name] = info
            logger.info(f"Discovered untracked extension: {extension.name}")

        return discovered
