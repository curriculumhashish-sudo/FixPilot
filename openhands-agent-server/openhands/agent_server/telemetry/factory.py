"""构建：class:`DiagnosticEvent` 对象。

集中在这里意味着运行时环境、伪名盐和身份规则都在一个地方决定，因此调用者无法意外地组
装一个事件，使用原始对话ID或未桶化计数。
"""

import sys
import uuid
from datetime import datetime
from typing import Final
from uuid import UUID

from openhands.agent_server.server_details_router import ServerInfo
from openhands.agent_server.telemetry.models import (
    TELEMETRY_SCHEMA_VERSION,
    DeploymentKind,
    DiagnosticEvent,
    DiagnosticProperties,
    EventName,
    RuntimeProperties,
)
from openhands.agent_server.telemetry.sanitizer import (
    UNKNOWN_TOKEN,
    pseudonymize,
    safe_token,
    safe_version,
)
from openhands.sdk.utils import utc_now


ANONYMOUS_PREFIX: Final[str] = "anon:"

# ：可选的请求标头，携带调用者的分析身份。 : 前端将其设置为 (
# ``posthog.get_distinct_id()``)，因此请求范围的活动：— 没有对话 ``user_id`` — 属性属于
# 同一个人。
#
DISTINCT_ID_HEADER: Final[str] = "X-OpenHands-Telemetry-Distinct-Id"

_MAX_DISTINCT_ID_LEN: Final[int] = 256


def distinct_id_from_header(value: str | None) -> str | None:
    """强制 ``X-OpenHands-Telemetry-Distinct-Id`` 标头或 ``None``。

    与 ``user_id`` 一样受信任：它逐字成为分析身份。 有界并去除了控制字符，因此杂散值
    既不能超过模式的长度限制，也不能将换行符偷偷带入配置文件中； 任何留空
    的内容都会返回到匿名 ID。
    """
    if not value:
        return None
    candidate = "".join(ch for ch in value if ch.isprintable()).strip()
    if not candidate:
        return None
    return candidate[:_MAX_DISTINCT_ID_LEN]


def _platform_token() -> str:
    return safe_token(sys.platform, default=UNKNOWN_TOKEN)


def _python_version() -> str:
    # 不是 sys.version：携带编译器和构建元数据。
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def build_runtime_properties(
    *,
    deferred_init: bool,
    deployment_kind: DeploymentKind = "local",
) -> RuntimeProperties:
    """快照每个事件共享的粗略运行时事实。"""
    # 版本和构建元数据来自 ServerInfo 自己的字段默认值，因此 /server_info 和遥测永远不会
    # 对正在运行的内容产生分歧。
    #
    info = ServerInfo(uptime=0.0, idle_time=0.0)
    return RuntimeProperties(
        server_version=safe_version(info.version),
        sdk_version=safe_version(info.sdk_version),
        tools_version=safe_version(info.tools_version),
        build_git_sha=safe_version(info.build_git_sha),
        build_git_ref=safe_version(info.build_git_ref),
        python_version=_python_version(),
        platform=_platform_token(),
        deferred_init=deferred_init,
        deployment_kind=deployment_kind,
    )


class DiagnosticEventFactory:
    """将信封标记到已清理的每个事件属性上。"""

    def __init__(
        self,
        *,
        runtime: RuntimeProperties,
        salt: str | bytes | None = None,
    ) -> None:
        self._runtime = runtime
        # 随机回退方案：在运行中稳定，在运行之间不可链接。
        self._salt = salt if salt else uuid.uuid4().hex
        self._session_ref = uuid.uuid4().hex

    @property
    def session_ref(self) -> str:
        return self._session_ref

    @property
    def runtime(self) -> RuntimeProperties:
        return self._runtime

    def conversation_ref(self, conversation_id: UUID | str) -> str:
        """对话 ID 的键入假名。

        从不出现于 URLs 中的 UUID 值，不会出现在日志和托管产品的数据库中，因此输出该
        值会使分析数据集能够回溯到个体。
        """
        raw = (
            conversation_id.bytes
            if isinstance(conversation_id, UUID)
            else str(conversation_id).encode("utf-8")
        )
        return pseudonymize(raw, self._salt)

    def distinct_id(self, user_id: str | None) -> str:
        """解析关联恒等式。

        部署提供的 ``user_id`` 会逐字传递，因此事件会落在主机已识别的人员身上。 缺少
        一个，就用内存中进程级的匿名ID —— 重启会得到一个新的值，这反
        而低估了本地唯一值，而不是在某人的机器上创建一个持久ID。
        """
        if user_id and user_id.strip():
            return user_id.strip()[:256]
        return f"{ANONYMOUS_PREFIX}{self._session_ref}"

    def build(
        self,
        event_name: EventName,
        properties: DiagnosticProperties,
        *,
        user_id: str | None = None,
        occurred_at: datetime | None = None,
        insert_id: str | None = None,
    ) -> DiagnosticEvent:
        return DiagnosticEvent(
            event_name=event_name,
            schema_version=TELEMETRY_SCHEMA_VERSION,
            occurred_at=occurred_at or utc_now(),
            insert_id=insert_id,
            distinct_id=self.distinct_id(user_id),
            runtime=self._runtime,
            properties=properties,
        )
