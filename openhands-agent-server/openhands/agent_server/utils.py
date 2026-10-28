import logging
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import PlainSerializer


logger = logging.getLogger(__name__)


def safe_rmtree(path: str | Path | None, description: str = "directory") -> bool:
    """安全地删除目录树，优雅地处理权限错误。

    Args:
        path: 要删除的目录的路径
        description: 正在删除的内容的描述（用于日志记录）

    Returns:
        bool: True 如果删除成功，False 如果失败
    """
    if not path or not os.path.exists(path):
        return True

    def handle_remove_readonly(func, path, _exc):
        """用于删除只读文件的错误处理程序。"""
        if os.path.exists(path):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except (OSError, PermissionError) as e:
                logger.warning(f"Failed to remove read-only file {path}: {e}")

    try:
        shutil.rmtree(path, onerror=handle_remove_readonly)
        logger.debug(f"Successfully removed {description}: {path}")
        return True
    except (OSError, PermissionError) as e:
        logger.warning(
            f"Failed to remove {description} at {path}: {e}. "
            f"This may leave temporary files on disk but won't affect functionality."
        )
        return False
    except Exception as e:
        logger.error(f"Unexpected error removing {description} at {path}: {e}")
        return False


def utc_now():
    """以 UTC 格式返回当前时间（因为 datetime.utcnow 为已弃用）"""
    return datetime.now(UTC)


def _uuid_to_hex(uuid_obj: UUID) -> str:
    """将 UUID 对象转换为不带连字符的十六进制字符串。"""
    return uuid_obj.hex


OpenHandsUUID = Annotated[UUID, PlainSerializer(_uuid_to_hex, when_used="json")]
