import json
import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict

from filelock import FileLock

from openhands.sdk import get_logger


logger = get_logger(__name__)

LEASE_FILE_NAME = "owner_lease.json"
LEASE_LOCK_FILE_NAME = ".owner_lease.lock"
DEFAULT_LEASE_TTL_SECONDS = 45.0


@dataclass(frozen=True)
class LeaseClaim:
    generation: int
    takeover: bool


class LeasePayload(TypedDict):
    owner_instance_id: str
    generation: int
    expires_at: float
    # 添加了用于崩溃恢复的可选字段。 它们在旧版本的 Agent Server 编写的租赁文件中不存在
    # ，因此消费者必须将它们视为可选的。
    #
    owner_host: NotRequired[str]
    owner_pid: NotRequired[int]


def _current_host() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ""


def _is_pid_alive(pid: int) -> bool:
    """尽力检查 ``pid`` 是否是该主机上的实时进程。

    使用 ``os.kill(pid, 0)``，它可以跨 POSIX 平台移植，并且自 Python 3.2 起可在
    Windows 上使用。 当活检测无法确定（权限
    错误、不支持的平台等）时，我们保守地报告进程为存活，以避免窃取可能仍在使用的租约
    。
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但由另一个用户拥有。
        return True
    except OSError:
        # 未知错误 - 保守一点并假设进程处于活动状态。
        return True
    return True


class ConversationLeaseHeldError(RuntimeError):
    def __init__(
        self,
        *,
        conversation_dir: Path,
        owner_instance_id: str,
        expires_at: float,
    ) -> None:
        self.conversation_dir = conversation_dir
        self.owner_instance_id = owner_instance_id
        self.expires_at = expires_at
        super().__init__(
            f"conversation lease is held by {owner_instance_id} until {expires_at}"
        )


class ConversationOwnershipLostError(RuntimeError):
    def __init__(
        self,
        *,
        conversation_dir: Path,
        owner_instance_id: str,
        generation: int,
    ) -> None:
        self.conversation_dir = conversation_dir
        self.owner_instance_id = owner_instance_id
        self.generation = generation
        super().__init__("conversation ownership was lost before the write completed")


class ConversationLease:
    """协调多个服务实例之间的对话所有权。

    租赁文件存储活跃所有者、递增的生成代和过期时间戳，这样在接管后，陈旧的所有者可以
    被隔离。
    """

    def __init__(
        self,
        *,
        conversation_dir: Path,
        owner_instance_id: str,
        ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> None:
        self._conversation_dir = conversation_dir
        self._owner_instance_id = owner_instance_id
        self._ttl_seconds = ttl_seconds
        self._lease_path = conversation_dir / LEASE_FILE_NAME
        self._lock_path = conversation_dir / LEASE_LOCK_FILE_NAME

    def claim(self) -> LeaseClaim:
        """声明或更新对话目录的所有权。"""
        self._conversation_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self._lock_path)):
            now = time.time()
            payload = self._read_payload()
            if payload is not None:
                current_owner = payload["owner_instance_id"]
                current_generation = payload["generation"]
                expires_at = payload["expires_at"]
                same_owner = current_owner == self._owner_instance_id
                if (
                    not same_owner
                    and expires_at > now
                    and not self._owner_is_dead(payload)
                ):
                    raise ConversationLeaseHeldError(
                        conversation_dir=self._conversation_dir,
                        owner_instance_id=current_owner,
                        expires_at=expires_at,
                    )
                generation = (
                    current_generation if same_owner else current_generation + 1
                )
                takeover = not same_owner
                if takeover and expires_at > now:
                    logger.info(
                        "Taking over conversation lease in %s from dead owner "
                        "%s (pid=%s host=%s); lease nominally valid until %s",
                        self._conversation_dir,
                        current_owner,
                        payload.get("owner_pid"),
                        payload.get("owner_host"),
                        expires_at,
                    )
            else:
                generation = 1
                takeover = False
            self._write_payload(
                generation=generation,
                expires_at=now + self._ttl_seconds,
            )
            return LeaseClaim(generation=generation, takeover=takeover)

    def _owner_is_dead(self, payload: LeasePayload) -> bool:
        """如果租赁记录的所有者进程消失，则返回 True。

        仅在 ``owner_host`` 匹配此时考虑
        host: PIDs 在其他主机上的存活检查毫无意义。
        由较旧的智能体服务器版本编写的租用文件不包括主机/pid，因此这会为它们返回
        False （保留旧的 TTL-only 行为）。
        """
        owner_host = payload.get("owner_host")
        owner_pid = payload.get("owner_pid")
        if not owner_host or not isinstance(owner_pid, int):
            return False
        if owner_host != _current_host():
            return False
        # 如果租约指向这个进程，请不要错误地认为我们已经死了（e.g. 同一流程的回收）。
        #
        if owner_pid == os.getpid():
            return False
        return not _is_pid_alive(owner_pid)

    def renew(self, generation: int) -> None:
        """延长当前租约，同时保留同一代。"""
        with FileLock(str(self._lock_path)):
            self._assert_owner_locked(generation)
            self._write_payload(
                generation=generation,
                expires_at=time.time() + self._ttl_seconds,
            )

    @contextmanager
    def guarded_write(self, generation: int) -> Iterator[None]:
        """在验证磁盘写入的所有权时保留租约锁。"""
        with FileLock(str(self._lock_path)):
            self._assert_owner_locked(generation)
            yield

    def release(self, generation: int) -> None:
        """如果该实例仍然拥有该代，则释放租约。"""
        with FileLock(str(self._lock_path)):
            payload = self._read_payload()
            if payload is None:
                return
            if (
                payload["owner_instance_id"] != self._owner_instance_id
                or payload["generation"] != generation
            ):
                return
            self._lease_path.unlink(missing_ok=True)

    def _assert_owner_locked(self, generation: int) -> None:
        payload = self._read_payload()
        if payload is None:
            raise ConversationOwnershipLostError(
                conversation_dir=self._conversation_dir,
                owner_instance_id=self._owner_instance_id,
                generation=generation,
            )
        if (
            payload["owner_instance_id"] != self._owner_instance_id
            or payload["generation"] != generation
        ):
            raise ConversationOwnershipLostError(
                conversation_dir=self._conversation_dir,
                owner_instance_id=self._owner_instance_id,
                generation=generation,
            )

    def _read_payload(self) -> LeasePayload | None:
        if not self._lease_path.exists():
            return None
        try:
            raw_payload = json.loads(self._lease_path.read_text())
            if not isinstance(raw_payload, dict):
                raise ValueError("lease payload must be an object")

            owner_instance_id = raw_payload.get("owner_instance_id")
            generation = raw_payload.get("generation")
            expires_at = raw_payload.get("expires_at")
            if not isinstance(owner_instance_id, str):
                raise ValueError("lease owner_instance_id must be a string")
            if not isinstance(generation, int):
                raise ValueError("lease generation must be an integer")
            if not isinstance(expires_at, int | float):
                raise ValueError("lease expires_at must be numeric")

            payload: LeasePayload = LeasePayload(
                owner_instance_id=owner_instance_id,
                generation=generation,
                expires_at=float(expires_at),
            )
            owner_host = raw_payload.get("owner_host")
            if isinstance(owner_host, str) and owner_host:
                payload["owner_host"] = owner_host
            owner_pid = raw_payload.get("owner_pid")
            if isinstance(owner_pid, int):
                payload["owner_pid"] = owner_pid
            return payload
        except Exception:
            logger.warning(
                "Failed to parse conversation lease file; treating as stale: %s",
                self._lease_path,
            )
            return None

    def _write_payload(self, *, generation: int, expires_at: float) -> None:
        payload = {
            "owner_instance_id": self._owner_instance_id,
            "generation": generation,
            "expires_at": expires_at,
            "owner_host": _current_host(),
            "owner_pid": os.getpid(),
        }
        tmp_path = self._lease_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload))
        tmp_path.replace(self._lease_path)
