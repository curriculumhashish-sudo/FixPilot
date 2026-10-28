"""设置和机密的基于文件的存储实现。

为了保持一致性，遵循与 OpenHands 应用程序服务器的 FileSettingsStore 和
FileSecretsStore 相同的模式。

文件锁定在 Unix 上使用 fcntl，在 Windows 上使用 msvcrt。
"""

from __future__ import annotations

import json
import os
import secrets as secrets_module
import stat
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from pydantic import SecretStr

from openhands.agent_server.persistence.models import (
    CustomSecret,
    PersistedSettings,
    PersistedWorkspaces,
    Secrets,
)
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.provider_connection_store import ProviderConnectionStore
from openhands.sdk.logger import get_logger
from openhands.sdk.profiles.agent_profile_store import AgentProfileStore
from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX, Cipher
from openhands.sdk.utils.path import get_user_persistence_dir
from openhands.sdk.utils.pydantic_secrets import (
    STRICT_DECRYPT_CONTEXT_KEY,
    SecretDecryptionError,
)


# fcntl仅限于Unix系统。 在 Windows 上，使用 msvcrt 进行文件锁定
if sys.platform != "win32":
    import fcntl

    msvcrt = None
else:
    fcntl = None  # type: ignore[assignment]
    import msvcrt


if TYPE_CHECKING:
    from openhands.agent_server.config import Config


logger = get_logger(__name__)

# 文件权限常量（所有者只读/写）
_DIR_MODE = stat.S_IRWXU  # 0o700 - rwx------
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600 - 读写-----

# Windows 保留文件名（不区分大小写）
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)


def _validate_filename(filename: str) -> None:
    """验证文件名以防止路径遍历和注入攻击。

    Raises:
        ValueError: 如果文件名无效或存在潜在危险。
    """
    # 检查空文件名（将解析为父目录）
    if not filename:
        raise ValueError("filename must not be empty")

    # 检查路径分隔符
    if "/" in filename or "\\" in filename:
        raise ValueError("filename must not contain path separators")

    # 检查前导点（隐藏文件、父目录遍历）
    if filename.startswith("."):
        raise ValueError("filename must not start with '.'")

    # 检查 null 字节（null 字节注入）
    if "\x00" in filename:
        raise ValueError("filename must not contain null bytes")

    # 检查尾随点/空格（Windows 路径处理问题）
    if filename.endswith(".") or filename.endswith(" "):
        raise ValueError("filename must not end with '.' or space")

    # 检查 Windows 保留名称（拆分处理多扩展名文件）e.g.、“CON.txt.json”->“CON”而不是“
    # CON.txt”
    #
    basename = filename.split(".")[0].upper()
    if basename in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"filename '{filename}' uses a reserved name")


def _ensure_secure_directory(path: Path) -> None:
    """确保目录存在并具有安全权限。

    创建具有安全权限 (0o700) 的所有父目录。 如果它已经存在，则确保权限正确。
    """
    if not path.exists():
        # 创建具有安全权限的父级
        current = path
        to_create: list[Path] = []
        while not current.exists():
            to_create.append(current)
            current = current.parent

        for dir_path in reversed(to_create):
            dir_path.mkdir(mode=_DIR_MODE, exist_ok=True)

    # 即使目录已经存在，也确保权限正确
    try:
        path.chmod(_DIR_MODE)
    except OSError as e:
        logger.warning(f"Failed to set permissions on {path}: {e}")


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    """上下文管理器用于基于文件的锁定。

    使用 Unix fcntl 进行独占锁定，以防止竞态条件执行读-修改-写操作。 在 Windows 上，
    使用 msvcrt.locking。
    """
    _ensure_secure_directory(lock_path.parent)

    # 创建锁文件 - 使用 O_RDWR 实现 Windows 与 msvcrt 的兼容性
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, _FILE_MODE)
    try:
        if fcntl is not None:
            # Unix：使用 fcntl 进行文件锁定
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        elif msvcrt is not None:
            # Windows：使用 msvcrt 进行文件锁定
            # 锁多个字节以获得更可靠的锁定行为
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 100)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 100)
        else:
            # 这种情况在标准系统（如Unix或Windows）上不应该发生（如并发写入可能导致数据
            # 损坏）
            #
            raise RuntimeError(
                "File locking not available on this platform. "
                "Concurrent writes may cause data corruption."
            )
    finally:
        os.close(fd)


def _atomic_write_json(path: Path, data: dict) -> None:
    """使用安全权限自动写入 JSON。

    使用 write-to-temp-then-rename 模式来防止中断时发生损坏。 从一开始就创建仅具有所
    有者权限的临时文件，以防止在 chmod 之前读取敏感数
    据的竞态条件。

    Note:
        重命名操作 (Path.replace) 在 POSIX 系统上是原子操作。 在 Windows 上，它在所有
        边缘情况中可能不是完全原子的（e.g、并发访问
        ，网络驱动器），但提供了对中断写入的合理保护。
    """
    import uuid

    # 使用 PID、时间和 uuid 作为唯一的临时文件名，以防止多个进程/线程同时写入同一文件时
    # 发生冲突
    #
    unique_suffix = f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    tmp_path = path.with_suffix(unique_suffix)
    # 从一开始就使用 os.open O_EXCL 创建具有安全权限的文件，确保独占创建（如果文件存在则
    # 失败）
    #
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
    fdopen_succeeded = False
    try:
        f = os.fdopen(fd, "w", encoding="utf-8")
        fdopen_succeeded = True
        with f:
            json.dump(data, f, indent=2)
    except Exception:
        # 仅当 os.fdopen() 未取得所有权时才手动关闭 fd
        if not fdopen_succeeded:
            try:
                os.close(fd)
            except OSError:
                pass
        # 出错时清理临时文件
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    # 原子重命名 - 如果 replace() 失败则清理临时文件
    try:
        tmp_path.replace(path)  # 原子 POSIX
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# 默认存储目录（相对于工作目录）
DEFAULT_PERSISTENCE_DIR = Path("workspace/.openhands")


# 附加到读取-修改-写入路径的“不同键”拒绝。
_KEY_HINT: Final[str] = (
    "restore the key it was saved under as OH_SECRET_KEY, or add it to "
    "OH_PREVIOUS_SECRET_KEYS"
)


def _has_stale_token(cipher: Cipher, data: Any) -> bool:
    """``data`` 是否拥有不在 ``cipher`` 当前密钥下的 Fernet token。"""
    if isinstance(data, str):
        return data.startswith(FERNET_TOKEN_PREFIX) and not cipher.is_current(data)
    if isinstance(data, dict):
        return any(_has_stale_token(cipher, v) for v in data.values())
    if isinstance(data, list):
        return any(_has_stale_token(cipher, v) for v in data)
    return False


def _file_has_stale_token(path: Path, cipher: Cipher | None) -> bool:
    if cipher is None or not cipher.previous_keys or not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return _has_stale_token(cipher, data)


def _load_context(cipher: Cipher | None, strict: bool) -> dict[str, Any] | None:
    """验证上下文用于加载带有 ``cipher`` 的存储文件。"""
    if cipher is None:
        return None
    return {"cipher": cipher, STRICT_DECRYPT_CONTEXT_KEY: strict}


class SettingsStore(ABC):
    """设置存储的抽象基类。"""

    @abstractmethod
    def load(self) -> PersistedSettings | None:
        """从存储加载设置。"""

    @abstractmethod
    def save(self, settings: PersistedSettings) -> None:
        """将设置保存到存储器。"""

    @abstractmethod
    def update(
        self, update_fn: Callable[[PersistedSettings], PersistedSettings]
    ) -> PersistedSettings:
        """通过文件锁定自动更新设置。

        Args:
            update_fn: 接收当前设置并返回的函数
                更新的设置。

        Returns:
            保存后更新的设置。
        """


class SecretsStore(ABC):
    """机密存储的抽象基类。"""

    @abstractmethod
    def load(self) -> Secrets | None:
        """从存储加载机密。"""

    @abstractmethod
    def save(self, secrets: Secrets) -> None:
        """将机密保存到存储器。"""

    @abstractmethod
    def get_secret(self, name: str) -> str | None:
        """按名称获取单个机密值。"""

    @abstractmethod
    def set_secret(self, name: str, value: str, description: str | None = None) -> None:
        """设置单个机密。"""

    @abstractmethod
    def delete_secret(self, name: str) -> bool:
        """删除机密。 如果存在则返回 True。"""


class FileSettingsStore(SettingsStore):
    """基于文件的设置存储。

    将设置存储为可配置目录中的 JSON。 设置内的机密使用提供的密码进行加密。

    Security features:
        - 使用仅限所有者的权限创建的文件 (0o600)
        - 使用仅限所有者的权限创建的目录 (0o700)
        - 原子写入以防止腐败
    """

    def __init__(
        self,
        persistence_dir: Path | str,
        cipher: Cipher | None = None,
        filename: str = "settings.json",
    ):
        # 验证文件名以防止路径遍历和注入攻击
        _validate_filename(filename)
        self.persistence_dir = Path(persistence_dir)
        self.cipher = cipher
        self.filename = filename
        self._path = self.persistence_dir / filename
        self._lock_path = self.persistence_dir / ".settings.lock"

    def load(self, *, strict: bool = False) -> PersistedSettings | None:
        """从文件加载设置。

        如果提供了密码， 机密都是通过 Pydantic's 验证上下文。 密码被传递给
        model_validate 这流到字段验证器使用
        validate_secret().

        A 机密密码无法将负载解密为 ``None``。 与
        ``strict=True``（读取-修改-写入路径）加载失败，返回 ``None``，因此调用者拒绝
        覆盖文件。
        """
        if not self._path.exists():
            logger.debug(f"Settings file not found: {self._path}")
            return None

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # 在上下文中传递密码以自动解密所有机密字段这使用 validate_secret() 流向字段
            # 验证器
            #
            context = _load_context(self.cipher, strict)
            return PersistedSettings.from_persisted(data, context=context)
        except SecretDecryptionError as e:
            logger.error(f"Cannot load settings for update: {e}")
            return None
        except (PermissionError, OSError) as e:
            # 应重新提出严重的文件系统错误
            logger.error(f"Cannot access settings file: {e}")
            raise
        except json.JSONDecodeError as e:
            # 损坏的文件 - 记录并返回 None 以允许恢复
            logger.error(f"Settings file is corrupted: {e}")
            return None
        except Exception:
            # 验证或其他错误 - 记录并返回 None
            logger.error("Failed to load settings", exc_info=True)
            return None

    def save(self, settings: PersistedSettings) -> None:
        """使用安全权限将设置自动保存到文件。

        如果提供了密码， 机密都是通过 Pydantic's 序列化上下文。 密码被传递给
        model_dump 这流到字段序列化器使用
        serialize_secret().

        Warning:
            此方法不获取文件锁。 对于并发安全更新，请使用：meth:`update`，它用文件锁
            定包装 save()。 从多个进程直接调用 save() 可能
            会导致更新丢失。

        Warning:
            如果未提供密码，则机密以明文形式存储。 这会在首次保存时记录为安全警告。
        """
        _ensure_secure_directory(self.persistence_dir)

        # 在上下文中传递密码以自动加密所有机密字段这使用 serialize_secret() 流向字段序列
        # 化器
        #
        if self.cipher:
            context: dict[str, Any] = {"cipher": self.cipher}
        else:
            context = {"expose_secrets": "plaintext"}
            # 关于明文机密存储的警告（仅当机密存在时）
            if settings.has_any_secret:
                logger.warning(
                    "Saving settings with secrets in PLAINTEXT (no cipher configured). "
                    "Configure OH_SECRET_KEY for production deployments."
                )

        data = settings.model_dump(mode="json", context=context)

        _atomic_write_json(self._path, data)
        logger.debug(f"Settings saved to {self._path}")

    def update(
        self, update_fn: Callable[[PersistedSettings], PersistedSettings]
    ) -> PersistedSettings:
        """通过文件锁定自动更新设置。

        使用文件锁定来防止并发更新相互覆盖。 更新函数在锁中调用。

        Args:
            update_fn: 接收当前设置并返回的函数
                更新的设置。

        Returns:
            保存后更新的设置。

        Raises:
            RuntimeError: 如果设置文件存在但无法加载
                （e.g.，损坏的 JSON，解密失败）。 这可以防止因用默认值覆盖现有设置而
                导致数据丢失。
        """
        with _file_lock(self._lock_path):
            settings = self.load(strict=True)
            if settings is None:
                # 文件不存在或为空 - 使用默认值是安全的
                if self._path.exists():
                    # 文件存在，但 load() 返回 None - 已损坏或无法读取
                    raise RuntimeError(
                        f"Cannot load settings from {self._path}. "
                        "File may be corrupted or encrypted with a different key "
                        f"({_KEY_HINT}). "
                        "Refusing to overwrite with defaults to prevent data loss."
                    )
                settings = PersistedSettings()
            updated = update_fn(settings)
            self.save(updated)
            return updated

    def reencrypt(self) -> bool:
        """在当前密钥下重新加密先前密钥下保存的值。

        当文件被重写时返回``True``。 当文件中没有任何内容过时，或者其中的值无法使用任
        何配置的密钥解密时，文件将保持原样。
        """
        with _file_lock(self._lock_path):
            if not _file_has_stale_token(self._path, self.cipher):
                return False
            settings = self.load(strict=True)
            if settings is None:
                return False
            self.save(settings)
            return True


class FileSecretsStore(SecretsStore):
    """基于文件的机密存储。

    将机密作为加密的 JSON 存储在可配置目录中。 所有机密值均使用提供的密码进行加密。

    Security features:
        - 使用仅限所有者的权限创建的文件 (0o600)
        - 使用仅限所有者的权限创建的目录 (0o700)
        - 原子写入以防止腐败
        - 文件锁定以防止竞态条件

    Note:
        在 Windows 上，文件系统不强制执行 0o600 文件权限。 如果存储机密时未加密 (
        cipher=None)，则其他本地用户可能可以读取它们。 配置
         OH_SECRET_KEY 以在所有平台上启用安全存储加密。
    """

    def __init__(
        self,
        persistence_dir: Path | str,
        cipher: Cipher | None = None,
        filename: str = "secrets.json",
    ):
        # 使用与 FileSettingsStore 相同的验证
        _validate_filename(filename)
        self.persistence_dir = Path(persistence_dir)
        self.cipher = cipher
        self.filename = filename
        self._path = self.persistence_dir / filename
        self._lock_path = self.persistence_dir / ".secrets.lock"

        # 未加密时警告 Windows 安全限制
        if sys.platform == "win32" and not cipher:
            logger.warning(
                "Storing secrets without encryption on Windows. "
                "File permissions are not enforced. Configure OH_SECRET_KEY "
                "for secure storage."
            )

    def load(self, *, strict: bool = False) -> Secrets | None:
        """从文件加载机密。

        如果提供了密码， 机密都是通过 Pydantic's 验证上下文。 密码被传递给
        model_validate 这流到字段验证器使用
        validate_secret().

        A 机密密码无法将负载解密为 ``None``。 与
        ``strict=True``（读取-修改-写入路径）加载失败，返回 ``None``，因此调用者拒绝
        覆盖文件。
        """
        if not self._path.exists():
            logger.debug(f"Secrets file not found: {self._path}")
            return None

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # 在上下文中传递密码以自动解密所有机密字段
            context = _load_context(self.cipher, strict)
            return Secrets.model_validate(data, context=context)
        except SecretDecryptionError as e:
            logger.error(f"Cannot load secrets for update: {e}")
            return None
        except (PermissionError, OSError) as e:
            # 应重新提出严重的文件系统错误
            logger.error(f"Cannot access secrets file: {e}")
            raise
        except json.JSONDecodeError as e:
            # 损坏的文件 - 记录并返回 None 以允许恢复
            logger.error(f"Secrets file is corrupted: {e}")
            return None
        except Exception:
            # 验证或其他错误 - 记录并返回 None
            logger.error("Failed to load secrets", exc_info=True)
            return None

    def save(self, secrets: Secrets) -> None:
        """保存机密代，同时保留凭据代。"""
        with _file_lock(self._lock_path):
            current = self.load(strict=True)
            if current is None:
                if self._path.exists():
                    raise RuntimeError(
                        f"Cannot load secrets from {self._path}. "
                        "Refusing to overwrite existing data."
                    )
                current = Secrets()

            versions = self._load_versions()
            current_secrets = current.custom_secrets
            replacement_secrets = secrets.custom_secrets
            versioned_names = set(versions)

            for name in list(versions):
                replacement = replacement_secrets.get(name)
                if replacement is None or replacement.secret is None:
                    versions.pop(name, None)

            for name, replacement in replacement_secrets.items():
                if name not in versioned_names or replacement.secret is None:
                    continue
                previous = current_secrets.get(name)
                previous_value = (
                    previous.secret.get_secret_value()
                    if previous is not None and previous.secret is not None
                    else None
                )
                if previous_value != replacement.secret.get_secret_value():
                    versions[name] = secrets_module.token_urlsafe(24)

            self._save_with_versions(secrets, versions)

    def reencrypt(self) -> bool:
        """在当前密钥下重新加密先前密钥下保存的值。

        当文件被重写时返回``True``。 当文件中没有任何内容过时，或者其中的值无法使用任
        何配置的密钥解密时，文件将保持原样。
        """
        with _file_lock(self._lock_path):
            if not _file_has_stale_token(self._path, self.cipher):
                return False
            secrets = self.load(strict=True)
            if secrets is None:
                return False
            self._save_with_versions(secrets, self._load_versions())
            return True

    def _save_with_versions(
        self,
        secrets: Secrets,
        versions: dict[str, str],
    ) -> None:
        _ensure_secure_directory(self.persistence_dir)

        # 在上下文中传递密码以自动加密所有机密字段
        if self.cipher:
            context: dict[str, Any] = {"cipher": self.cipher}
        else:
            context = {"expose_secrets": "plaintext"}
            # 关于明文机密存储的警告（仅当机密存在时）
            if secrets.has_any_secret:
                logger.warning(
                    "Saving secrets in PLAINTEXT (no cipher configured). "
                    "Configure OH_SECRET_KEY for production deployments."
                )

        data = secrets.model_dump(mode="json", context=context)
        if versions:
            data["_credential_versions"] = versions

        _atomic_write_json(self._path, data)
        logger.debug(f"Secrets saved to {self._path}")

    def _load_versions(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        versions = data.get("_credential_versions") if isinstance(data, dict) else None
        if not isinstance(versions, dict):
            return {}
        return {
            name: version
            for name, version in versions.items()
            if isinstance(name, str) and isinstance(version, str) and version
        }

    def get_secret(self, name: str) -> str | None:
        """按名称获取单个机密值。

        使用文件锁定来防止在并发写入期间读取。
        """
        with _file_lock(self._lock_path):
            secrets = self.load()
            if secrets is None:
                return None
            secret = secrets.custom_secrets.get(name)
            if secret is None or secret.secret is None:
                return None
            return secret.secret.get_secret_value()

    def set_secret(self, name: str, value: str, description: str | None = None) -> None:
        """设置具有文件锁定的单个机密以防止竞态条件。

        Raises:
            RuntimeError: 如果机密文件存在但无法加载
                （e.g.，损坏的 JSON，解密失败）。 这可以防止数据因用默认值覆盖现有的
                机密而丢失。
        """
        with _file_lock(self._lock_path):
            secrets = self.load(strict=True)
            if secrets is None:
                # 文件不存在 - 使用默认值可以安全
                if self._path.exists():
                    # 文件存在，但 load() 返回 None - 已损坏或无法读取
                    raise RuntimeError(
                        f"Cannot load secrets from {self._path}. "
                        "File may be corrupted or encrypted with a different key "
                        f"({_KEY_HINT}). "
                        "Refusing to overwrite with defaults to prevent data loss."
                    )
                secrets = Secrets()

            # 创建具有更新值的新机密字典
            new_secrets = dict(secrets.custom_secrets)
            new_secrets[name] = CustomSecret(
                name=name,
                secret=SecretStr(value),
                description=description,
            )

            versions = self._load_versions()
            if name in versions:
                versions[name] = secrets_module.token_urlsafe(24)
            self._save_with_versions(Secrets(custom_secrets=new_secrets), versions)

    def delete_secret(self, name: str) -> bool:
        """删除带有文件锁定的机密。 如果存在则返回 True。

        Raises:
            RuntimeError: 如果机密文件存在但无法加载
                （e.g.，损坏的 JSON，解密失败）。 这可以防止数据因用默认值覆盖现有的
                机密而丢失。
        """
        with _file_lock(self._lock_path):
            secrets = self.load(strict=True)
            if secrets is None:
                # 文件不存在 - 没有可删除的内容
                if self._path.exists():
                    # 文件存在，但 load() 返回 None - 已损坏或无法读取
                    raise RuntimeError(
                        f"Cannot load secrets from {self._path}. "
                        "File may be corrupted or encrypted with a different key "
                        f"({_KEY_HINT}). "
                        "Refusing to modify to prevent data loss."
                    )
                return False
            if name not in secrets.custom_secrets:
                return False

            new_secrets = {k: v for k, v in secrets.custom_secrets.items() if k != name}
            versions = self._load_versions()
            versions.pop(name, None)
            self._save_with_versions(Secrets(custom_secrets=new_secrets), versions)
            return True

    def load_versioned_secret(self, name: str) -> tuple[str, str]:
        with _file_lock(self._lock_path):
            secrets = self.load(strict=True)
            if secrets is None:
                if self._path.exists():
                    raise RuntimeError(
                        f"Cannot load secrets from {self._path}. "
                        "File may be corrupted or encrypted with a different key "
                        f"({_KEY_HINT}). "
                        "Refusing to modify to prevent data loss."
                    )
                raise KeyError(name)

            current = secrets.custom_secrets.get(name)
            if current is None or current.secret is None:
                raise KeyError(name)
            versions = self._load_versions()
            version = versions.get(name)
            if version is None:
                version = secrets_module.token_urlsafe(24)
                versions[name] = version
                self._save_with_versions(secrets, versions)
            return current.secret.get_secret_value(), version

    def replace_versioned_secret(
        self,
        name: str,
        expected_version: str,
        value: str,
    ) -> str:
        with _file_lock(self._lock_path):
            secrets = self.load(strict=True)
            if secrets is None:
                if self._path.exists():
                    raise RuntimeError(
                        f"Cannot load secrets from {self._path}. "
                        "File may be corrupted or encrypted with a different key "
                        f"({_KEY_HINT}). "
                        "Refusing to modify to prevent data loss."
                    )
                raise KeyError(name)

            current = secrets.custom_secrets.get(name)
            if current is None or current.secret is None:
                raise KeyError(name)
            versions = self._load_versions()
            if versions.get(name) != expected_version:
                raise ValueError("credential_version_conflict")

            new_secrets = dict(secrets.custom_secrets)
            new_secrets[name] = current.model_copy(update={"secret": SecretStr(value)})
            successor = secrets_module.token_urlsafe(24)
            versions[name] = successor
            self._save_with_versions(Secrets(custom_secrets=new_secrets), versions)
            return successor


class WorkspacesStore(ABC):
    """工作区存储的抽象基类。"""

    @abstractmethod
    def load(self) -> PersistedWorkspaces | None:
        """从存储加载工作区。"""

    @abstractmethod
    def save(self, workspaces: PersistedWorkspaces) -> None:
        """将工作区保存到存储器。"""

    @abstractmethod
    def update(
        self,
        update_fn: Callable[[PersistedWorkspaces], PersistedWorkspaces],
    ) -> PersistedWorkspaces:
        """使用文件锁定自动更新工作区。

        ``update_fn`` 返回其参数不变以表示无操作，在这种情况下不会写入任何内容。
        """


class FileWorkspacesStore(WorkspacesStore):
    """基于文件的存储，用于存储用户已保存的工作区 / 工作区父母。

    使用与 ``FileSettingsStore`` 相同的原子写入 + 文件锁原语在
    ``<persistence_dir>/workspaces.json`` 处
    保留单个 JSON 文档。 工作区路径不是机密，因此不使用密码。
    """

    def __init__(
        self,
        persistence_dir: Path | str,
        filename: str = "workspaces.json",
    ):
        _validate_filename(filename)
        self.persistence_dir = Path(persistence_dir)
        self.filename = filename
        self._path = self.persistence_dir / filename
        self._lock_path = self.persistence_dir / ".workspaces.lock"

    def load(self) -> PersistedWorkspaces | None:
        if not self._path.exists():
            return None

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return PersistedWorkspaces.from_persisted(data)
        except (PermissionError, OSError) as e:
            logger.error(f"Cannot access workspaces file: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Workspaces file is corrupted: {e}")
            return None
        except Exception:
            logger.error("Failed to load workspaces", exc_info=True)
            return None

    def save(self, workspaces: PersistedWorkspaces) -> None:
        _ensure_secure_directory(self.persistence_dir)
        # ``exclude_none=True`` 保持磁盘上的形状与线对齐
        # 契约：未设置``parentPath``而不是``null``，这
        # 匹配 GUI 的 ``LocalWorkspace.parentPath?: string`` 类型。
        data = workspaces.model_dump(mode="json", by_alias=True, exclude_none=True)
        _atomic_write_json(self._path, data)
        logger.debug(f"Workspaces saved to {self._path}")

    def update(
        self,
        update_fn: Callable[[PersistedWorkspaces], PersistedWorkspaces],
    ) -> PersistedWorkspaces:
        with _file_lock(self._lock_path):
            workspaces = self.load()
            if workspaces is None:
                if self._path.exists():
                    raise RuntimeError(
                        f"Cannot load workspaces from {self._path}. "
                        "File may be corrupted. "
                        "Refusing to overwrite with defaults to prevent data loss."
                    )
                workspaces = PersistedWorkspaces()
            updated = update_fn(workspaces)
            # ``update_fn`` 当没有任何内容需要更改时，返回其输入不变（重新添加、删除不匹
            # 配任何内容）； 跳过写入，因此无操作既不会创建也不会重写文件。
            #
            if updated is not workspaces:
                self.save(updated)
            return updated


# ── 全球商店访问──────────────────────────────────────────────────

_settings_store: FileSettingsStore | None = None
_secrets_store: FileSecretsStore | None = None
_provider_connections_store: ProviderConnectionStore | None = None
_workspaces_store: FileWorkspacesStore | None = None
_llm_profile_store: LLMProfileStore | None = None
_agent_profile_store: AgentProfileStore | None = None
_store_lock = threading.Lock()


def _get_persistence_dir(config: Config | None = None) -> Path:
    """从配置或默认中获取持久化目录。"""
    # 缺少 OH_PERSISTENCE_DIR，则回退到配置的 conversations_path 父级。
    default = (
        config.conversations_path.parent / ".openhands"
        if config is not None
        else DEFAULT_PERSISTENCE_DIR
    )
    return get_user_persistence_dir(default)


def _get_profile_persistence_dir() -> Path:
    """获取 LLM/代理配置文件存储的基本目录。

    配置文件可以容纳凭据（LLM API 键），因此不存在
    ``OH_PERSISTENCE_DIR`` 他们退回到用户端 ``~/.openhands`` rather than the 工作区-
    relative 智能体-
    server 默认，保留裸本地配置机密在预期的用户配置目录中。
    """
    return get_user_persistence_dir()


def _get_cipher(config: Config | None = None) -> Cipher | None:
    """从配置中获取密码以进行加密机密。"""
    if config is not None:
        return config.cipher
    return None


def get_settings_store(config: Config | None = None) -> FileSettingsStore:
    """获取全局设置存储实例 (线程安全)。

    Note:
        配置参数仅在第一次初始化时使用。 无论配置如何，后续调用都会返回现有实例。

    Warning:
        密钥 (OH_SECRET_KEY) 必须不在运行时更改。 存储单例缓存第一次初始化时的密码。
        如果密钥发生变化：
        - 新数据可能使用过时的密钥进行加密
        - 现有数据可能无法解密
        - 这可能会在更新操作中触发数据丢失保护

        要使用新的密钥，请重新启动服务器进程。 为了进行测试，请使用：func:
        `reset_stores` 清除单例。
    """
    global _settings_store
    if _settings_store is not None:
        return _settings_store

    with _store_lock:
        # 获取锁后仔细检查
        if _settings_store is None:
            _settings_store = FileSettingsStore(
                persistence_dir=_get_profile_persistence_dir(),
                cipher=_get_cipher(config),
            )
        return _settings_store


def get_secrets_store(config: Config | None = None) -> FileSecretsStore:
    """获取全局机密存储实例 (线程安全)。

    Note:
        配置参数仅在第一次初始化时使用。 无论配置如何，后续调用都会返回现有实例。

    Warning:
        密钥 (OH_SECRET_KEY) 必须不在运行时更改。 存储单例缓存第一次初始化时的密码。
        如果密钥发生变化：
        - 新数据可能使用过时的密钥进行加密
        - 现有数据可能无法解密
        - 这可能会在更新操作中触发数据丢失保护

        要使用新的密钥，请重新启动服务器进程。 为了进行测试，请使用：func:
        `reset_stores` 清除单例。
    """
    global _secrets_store
    if _secrets_store is not None:
        return _secrets_store

    with _store_lock:
        # 获取锁后仔细检查
        if _secrets_store is None:
            _secrets_store = FileSecretsStore(
                persistence_dir=_get_profile_persistence_dir(),
                cipher=_get_cipher(config),
            )
        return _secrets_store


def reencrypt_stale_stores(config: Config) -> None:
    """使用当前密钥重新加密设置和机密存储。

    配置 ``previous_secret_keys`` 时在启动时运行，因此旋转密钥不会等待下一次写入。 失
    败会被记录下来，而不会引发：无论哪种方式，存储都可以通过
    以前的键保持可读性。
    """
    cipher = config.cipher
    if cipher is None or not cipher.previous_keys:
        return
    for name, store in (
        ("settings", get_settings_store(config)),
        ("secrets", get_secrets_store(config)),
    ):
        try:
            if store.reencrypt():
                logger.info(f"Re-encrypted the {name} store under the current key")
        except Exception:
            logger.error(f"Could not re-encrypt the {name} store", exc_info=True)


def get_provider_connections_store(
    config: Config | None = None,  # noqa: ARG001
) -> ProviderConnectionStore:
    """获取全局提供者连接存储实例 (线程安全)。

    与 ``profiles`` 一起存储在 ``<dir>/provider-connections`` /
    ``agent-profiles``. 商店本身与密码无关； 调用者每次调用都会传递请求密码，因此密钥
    在 REST 处进行加密。
    """
    global _provider_connections_store
    if _provider_connections_store is not None:
        return _provider_connections_store

    with _store_lock:
        if _provider_connections_store is None:
            _provider_connections_store = ProviderConnectionStore(
                base_dir=_get_profile_persistence_dir() / "provider-connections",
            )
        return _provider_connections_store


def get_workspaces_store(config: Config | None = None) -> FileWorkspacesStore:
    """获取全局工作区存储实例 (线程安全)。

    Note:
        配置参数仅在第一次初始化时使用。 无论配置如何，后续调用都会返回现有实例。
    """
    global _workspaces_store
    if _workspaces_store is not None:
        return _workspaces_store

    with _store_lock:
        if _workspaces_store is None:
            _workspaces_store = FileWorkspacesStore(
                persistence_dir=_get_persistence_dir(config),
            )
        return _workspaces_store


def get_llm_profile_store() -> LLMProfileStore:
    """获取全局 ``LLMProfileStore`` 实例 (线程安全)。

    存储在 ``<dir>/profiles``，其中 ``<dir>`` 设置时为 ``OH_PERSISTENCE_DIR``，否则为
    ``~/.openhands``。 这尊重隔离的智能体服务器实例，同时在用户的配置目录中保留裸露的
    本地配置文件机密（从不相对于工作区）。 参见
    :func:`_get_profile_persistence_dir`。
    """
    global _llm_profile_store
    if _llm_profile_store is not None:
        return _llm_profile_store

    # 首先解析提供程序存储：它采用 ``_store_lock`` 本身，并且
    # ``_store_lock`` 不是可重入，因此在已经持有下面的锁的情况下调用它会是死锁。
    #
    provider_store = get_provider_connections_store()
    with _store_lock:
        if _llm_profile_store is None:
            _llm_profile_store = LLMProfileStore(
                base_dir=_get_profile_persistence_dir() / "profiles",
                provider_store=provider_store,
            )
        return _llm_profile_store


def get_agent_profile_store() -> AgentProfileStore:
    """获取全局 ``AgentProfileStore`` 实例 (线程安全)。

    存储在 ``<dir>/agent-profiles``，其中 ``<dir>`` 通过以下方式解析
    :func:`_get_profile_persistence_dir`，原因与
    :func:`get_llm_profile_store`。
    """
    global _agent_profile_store
    if _agent_profile_store is not None:
        return _agent_profile_store

    with _store_lock:
        if _agent_profile_store is None:
            _agent_profile_store = AgentProfileStore(
                base_dir=_get_profile_persistence_dir() / "agent-profiles",
            )
        return _agent_profile_store


def reset_stores() -> None:
    """重置全局存储实例（用于测试）。"""
    global _settings_store, _secrets_store, _provider_connections_store
    global _workspaces_store, _llm_profile_store, _agent_profile_store
    with _store_lock:
        _settings_store = None
        _secrets_store = None
        _provider_connections_store = None
        _workspaces_store = None
        _llm_profile_store = None
        _agent_profile_store = None
