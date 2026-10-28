"""LLM 配置文件和 ``AgentProfile``\\ 之间的外键生命周期。

``OpenHandsAgentProfile.llm_profile_ref`` 是对 LLM 配置文件存储密钥的软 FK。
``find_referrers`` /
``cascade_rename`` / ``delete_llm_profile`` /
``rename_llm_profile`` 防止 FK 悬空。

与存储无关：这些仅通过以下方式接触智能体-配置文件存储
:类：`~openhands.sdk.profiles.agent_profile_store.AgentProfileStoreProtocol`,
从来没有文件系统，因此文件存储和云数据库存储逐字重用它们。

锁顺序：智能体-profiles 在 llm-profiles 之前（绝不相反 - 死锁）。 受保护的删除/重命名
在整个扫描→变异窗口中保留可重入的智能体-配置文件
``lock()`` 以关闭 TOCTOU。 FK 仅涵盖 ``llm_profile_ref``； ``mcp_server_refs`` 在解析
时检查（#3717）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openhands.sdk.llm.llm_profile_store import canonical_profile_name
from openhands.sdk.logger import get_logger
from openhands.sdk.profiles.agent_profile_store import PROFILE_NAME_REGEX


if TYPE_CHECKING:
    from openhands.sdk.llm.llm_profile_store import LLMProfileMutator
    from openhands.sdk.profiles.agent_profile_store import AgentProfileStoreProtocol

logger = get_logger(__name__)


class ProfileReferenced(Exception):
    """当 LLM 配置文件因智能体配置文件引用而无法删除时引发。

    ``referrers`` 是引用智能体-配置文件名称的列表； 路由器将其显示在 409 中，以便用户
    知道首先要分离什么。
    """

    def __init__(self, referrers: list[str]) -> None:
        self.referrers = list(referrers)
        joined = ", ".join(self.referrers) or "<none>"
        super().__init__(
            f"LLM profile is referenced by {len(self.referrers)} agent "
            f"profile(s): {joined}"
        )


def _validate_name(name: str) -> None:
    """拒绝不是合法配置文件键的名称（路径遍历等）。"""
    if not PROFILE_NAME_REGEX.match(name):
        raise ValueError(f"Invalid profile name: {name!r}.")


def _scan_referrers(
    store: AgentProfileStoreProtocol, llm_profile_name: str
) -> list[str]:
    """返回引用智能体-配置文件名称。 调用者必须按住：meth:`store.lock`。

    通过 ``list_summaries`` 读取元数据（无验证 / 机密实例化）。 只有 OpenHands 变体带
    有 ``llm_profile_ref``。 名
    称通过存储键进行比较，因此 ``foo.json`` 与 ``foo`` 匹配。
    """
    key = canonical_profile_name(llm_profile_name)
    return [
        str(summary["name"])
        for summary in store.list_summaries()
        if summary.get("agent_kind", "openhands") == "openhands"
        and isinstance(ref := summary.get("llm_profile_ref"), str)
        and canonical_profile_name(ref) == key
    ]


def _rewrite_refs(
    store: AgentProfileStoreProtocol, old_name: str, new_name: str
) -> list[str]:
    """重新指向每个 ``llm_profile_ref == old_name`` 到 ``new_name``。

    调用者必须按住：meth:`store.lock`。 通过 ``list_summaries`` 找到referrer，然后按
    ``set_llm_profile_ref`` 的手术写入原语，这样加密的 ``mcp_tools`` 和稳定的 ``id``
    不会被修改，不需要加密。 返回重写的
    配置文件的名称。
    """
    rewritten = _scan_referrers(store, old_name)
    new_key = canonical_profile_name(new_name)
    for name in rewritten:
        store.set_llm_profile_ref(name, new_key)
    return rewritten


def find_referrers(
    store: AgentProfileStoreProtocol, llm_profile_name: str
) -> list[str]:
    """``llm_profile_ref == llm_profile_name`` 的智能体个配置文件的名称。"""
    with store.lock():
        return _scan_referrers(store, llm_profile_name)


def cascade_rename(
    store: AgentProfileStoreProtocol, old_name: str, new_name: str
) -> list[str]:
    """以原子方式将所有 ``llm_profile_ref == old_name`` 重新指向 ``new_name``。

    保存整个扫描和重写的智能体-配置文件锁，因此并发保存不能交错。 返回重写的配置文件
    名称。
    """
    _validate_name(new_name)
    with store.lock():
        rewritten = _rewrite_refs(store, old_name, new_name)
    if rewritten:
        logger.info(
            f"[Profile FK] Cascaded llm_profile_ref `{old_name}` -> `{new_name}` "
            f"across {len(rewritten)} agent profile(s)."
        )
    return rewritten


def delete_llm_profile(
    agent_store: AgentProfileStoreProtocol,
    llm_store: LLMProfileMutator,
    llm_profile_name: str,
) -> None:
    """仅当没有智能体配置文件引用它时才删除 LLM 配置文件。

    持有智能体-profile 锁的 [referrer check] 和 [delete]，然后委托给
    ``llm_store.delete``（它管理自己的锁）——
    保留智能体-profile 之前的 [llm-profile] 顺序。 提高
    :class:`ProfileReferenced` 命名引用者（如果存在）。
    """
    with agent_store.lock():
        referrers = _scan_referrers(agent_store, llm_profile_name)
        if referrers:
            raise ProfileReferenced(referrers)
        llm_store.delete(llm_profile_name)


def rename_llm_profile(
    agent_store: AgentProfileStoreProtocol,
    llm_store: LLMProfileMutator,
    old_name: str,
    new_name: str,
) -> list[str]:
    """重命名一个 LLM 角色，并将重命名传播到其引用者。

    在整个操作中保存智能体-配置文件锁，然后委托给
    ``llm_store.rename``（管理自己的锁）— 保留智能体-profiles-before-llm-profiles 顺
    序。 LLM 文件首先被重命名，
    因此如果失败（缺少源/获取的目标），则不会重写任何引用。 返回重写的智能体-配置文件
    名称。
    """
    _validate_name(new_name)
    with agent_store.lock():
        llm_store.rename(old_name, new_name)
        return _rewrite_refs(agent_store, old_name, new_name)
