import json
import os
import socket
import time
from pathlib import Path
from typing import cast

import pytest

from openhands.agent_server import conversation_lease as conversation_lease_module
from openhands.agent_server.conversation_lease import (
    LEASE_FILE_NAME,
    ConversationLease,
    ConversationLeaseHeldError,
    ConversationOwnershipLostError,
    LeasePayload,
)


def _read_lease_payload(conversation_dir: Path) -> LeasePayload:
    return cast(
        LeasePayload,
        json.loads((conversation_dir / LEASE_FILE_NAME).read_text()),
    )


def _expire_lease(conversation_dir: Path) -> None:
    lease_path = conversation_dir / LEASE_FILE_NAME
    payload = json.loads(lease_path.read_text())
    payload["expires_at"] = 0
    lease_path.write_text(json.dumps(payload))


def test_claim_and_renew_persist_same_owner_generation(tmp_path: Path) -> None:
    conversation_dir = tmp_path / "conversation"
    lease = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
        ttl_seconds=0.2,
    )

    claim = lease.claim()
    first_payload = _read_lease_payload(conversation_dir)

    time.sleep(0.01)
    lease.renew(claim.generation)
    renewed_payload = _read_lease_payload(conversation_dir)

    repeated_claim = lease.claim()
    repeated_payload = _read_lease_payload(conversation_dir)

    assert claim.generation == 1
    assert claim.takeover is False
    assert first_payload["owner_instance_id"] == "primary"
    assert renewed_payload["generation"] == 1
    assert renewed_payload["expires_at"] > first_payload["expires_at"]
    assert repeated_claim.generation == 1
    assert repeated_claim.takeover is False
    assert repeated_payload["owner_instance_id"] == "primary"
    assert repeated_payload["generation"] == 1


def test_claim_rejects_different_owner_while_lease_is_live(tmp_path: Path) -> None:
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
    )
    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )

    primary.claim()

    with pytest.raises(ConversationLeaseHeldError) as exc_info:
        secondary.claim()

    assert exc_info.value.conversation_dir == conversation_dir
    assert exc_info.value.owner_instance_id == "primary"


def test_takeover_bumps_generation_and_blocks_stale_owner_writes(
    tmp_path: Path,
) -> None:
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
    )
    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )

    primary_claim = primary.claim()
    _expire_lease(conversation_dir)

    secondary_claim = secondary.claim()
    payload = _read_lease_payload(conversation_dir)

    assert secondary_claim.generation == primary_claim.generation + 1
    assert secondary_claim.takeover is True
    assert payload["owner_instance_id"] == "secondary"
    assert payload["generation"] == secondary_claim.generation

    with pytest.raises(ConversationOwnershipLostError):
        primary.renew(primary_claim.generation)

    with pytest.raises(ConversationOwnershipLostError):
        with primary.guarded_write(primary_claim.generation):
            pass

    with secondary.guarded_write(secondary_claim.generation):
        assert _read_lease_payload(conversation_dir)["owner_instance_id"] == "secondary"


def test_release_keeps_new_owner_lease_intact_after_takeover(tmp_path: Path) -> None:
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
    )
    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )

    primary_claim = primary.claim()
    _expire_lease(conversation_dir)
    secondary_claim = secondary.claim()

    primary.release(primary_claim.generation)
    assert (conversation_dir / LEASE_FILE_NAME).exists()

    secondary.release(secondary_claim.generation)
    assert not (conversation_dir / LEASE_FILE_NAME).exists()


def test_claim_writes_owner_host_and_pid(tmp_path: Path) -> None:
    conversation_dir = tmp_path / "conversation"
    lease = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
    )

    lease.claim()
    payload = _read_lease_payload(conversation_dir)

    assert payload.get("owner_host") == socket.gethostname()
    assert payload.get("owner_pid") == os.getpid()


def test_claim_takes_over_when_previous_owner_pid_is_dead(
    tmp_path: Path,
) -> None:
    """模拟非正常关闭：死亡的 PID 仍然拥有活动租约。

    如果没有崩溃恢复检查，第二个索赔将失败
    ``ConversationLeaseHeldError`` 直到 TTL 过去，对话将在智能体服务器重新启动时跳过
    。
    """
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
        ttl_seconds=3600.0,  # 确保 TTL 远未过去。
    )
    primary_claim = primary.claim()
    payload = _read_lease_payload(conversation_dir)
    # 健全性：租约名义上有效。
    assert payload["expires_at"] > time.time() + 60

    # 伪造指向 PID 的租约，保证该主机上不存在。 PID 2**31 - 1 在任何真实环境中都远远超出
    #  /proc/sys/kernel/pid_max。
    #
    dead_pid = 2**31 - 1
    forged = dict(payload)
    forged["owner_pid"] = dead_pid
    (conversation_dir / LEASE_FILE_NAME).write_text(json.dumps(forged))

    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )
    secondary_claim = secondary.claim()

    new_payload = _read_lease_payload(conversation_dir)
    assert secondary_claim.takeover is True
    assert secondary_claim.generation == primary_claim.generation + 1
    assert new_payload["owner_instance_id"] == "secondary"
    assert new_payload.get("owner_pid") == os.getpid()


def test_claim_blocks_takeover_when_owner_is_on_a_different_host(
    tmp_path: Path,
) -> None:
    """不得为其他主机上的所有者触发活动检查。

    如果租约是由运行在不同机器上的智能体-服务器写的，我们本地PID表中没有关于该进程是
    否存活的信息，因此我们不得不回退到TTL。
    """
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
        ttl_seconds=3600.0,
    )
    primary.claim()

    payload = _read_lease_payload(conversation_dir)
    forged = dict(payload)
    forged["owner_host"] = "some-other-host"
    forged["owner_pid"] = 2**31 - 1  # 如果在本地检查将是“死”
    (conversation_dir / LEASE_FILE_NAME).write_text(json.dumps(forged))

    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )
    with pytest.raises(ConversationLeaseHeldError):
        secondary.claim()


def test_claim_falls_back_to_ttl_for_legacy_lease_files(
    tmp_path: Path,
) -> None:
    """旧版本编写的租约文件不包括host/pid。

    他们必须继续像以前一样行事：TTL-只有到期才决定是否可能发生接管。
    """
    conversation_dir = tmp_path / "conversation"
    conversation_dir.mkdir(parents=True)
    legacy_payload = {
        "owner_instance_id": "primary",
        "generation": 7,
        "expires_at": time.time() + 3600.0,
    }
    (conversation_dir / LEASE_FILE_NAME).write_text(json.dumps(legacy_payload))

    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )
    with pytest.raises(ConversationLeaseHeldError):
        secondary.claim()


def test_owner_pid_check_treats_unknown_errors_as_alive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """我们必须避免窃取实时租约。"""
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
        ttl_seconds=3600.0,
    )
    primary.claim()

    def _raise_oserror(_pid: int, _sig: int) -> None:
        raise OSError("EPERM-like error from a sandbox")

    monkeypatch.setattr(conversation_lease_module.os, "kill", _raise_oserror)

    # 伪造租约，使其指向 PID，即不此进程（否则同一进程短路会在咨询 _is_pid_alive 之前启
    # 动）。
    #
    payload = _read_lease_payload(conversation_dir)
    forged = dict(payload)
    forged["owner_pid"] = os.getpid() + 1
    (conversation_dir / LEASE_FILE_NAME).write_text(json.dumps(forged))

    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )
    with pytest.raises(ConversationLeaseHeldError):
        secondary.claim()


def test_claim_self_pid_match_is_not_treated_as_dead(tmp_path: Path) -> None:
    """引用 *this* 进程的租约绝不能被视为死亡。

    否则，同一进程重新进入 (e.g. 测试，或者碰巧重用相同的快速重启 PID）可能会错误地触
    发接管。
    """
    conversation_dir = tmp_path / "conversation"
    primary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="primary",
        ttl_seconds=3600.0,
    )
    primary.claim()

    # 租约已经有 owner_pid == os.getpid()。 不同所有者的索赔仍必须被拒绝。
    #
    secondary = ConversationLease(
        conversation_dir=conversation_dir,
        owner_instance_id="secondary",
    )
    with pytest.raises(ConversationLeaseHeldError):
        secondary.claim()
