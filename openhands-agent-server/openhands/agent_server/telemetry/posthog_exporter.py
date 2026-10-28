"""可选的 PostHog 导出器。 树中唯一的供应商感知模块。

``posthog`` 在：meth:`PostHogExporter.__init__` 中懒加载，因此导入这个包或禁用
telemetry 的服务器永远不会拉取依赖。
因此，图书馆和无头消费者无需支付任何费用，并且丢失的额外内容会降级为无操作接收器，而
不是导致启动崩溃。

**该出口商仅调用 ``capture()``。**没有``identify()``，没有
``alias()``，无 ``group_identify()``，无 ``$set``。 原因按顺序为
严重程度：

1. ``identify()`` 创建或更改托管产品 (Canvas) 已拥有的 * 人员配置文件 *。 另一个作家
篡改了其属性，并且在 ``distinct_id``（
电子邮件 vs UUID）之间任何漂移都会生成一个被标记为第二个月活跃用户的重复人。
2. ``alias()`` 在 PostHog 中是不可逆转的——一个错误就会永久地合并两个身份。
3. 人员档案将廉价事件转变为收费事件，这些是诊断而不是每个人的产品使用情况。

关联是通过*重用*部署已建立的身份来实现的，而不是通过断言新的身份来实现。
"""

import asyncio
from typing import Final

from openhands.agent_server.telemetry.factory import ANONYMOUS_PREFIX
from openhands.agent_server.telemetry.models import DiagnosticEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

DEFAULT_POSTHOG_HOST: Final[str] = "https://us.i.posthog.com"


class PostHogExporter:
    """将清理后的诊断事件发送至 PostHog。"""

    def __init__(
        self,
        api_key: str,
        *,
        host: str = DEFAULT_POSTHOG_HOST,
        timeout: int = 15,
    ) -> None:
        # 懒惰，故意：模块范围会击败可选的额外内容。
        from posthog import Posthog

        self._client = Posthog(
            project_api_key=api_key,
            host=host,
            timeout=timeout,
            # 自动捕获将发送完整的回溯，击败`sanitizer`。
            enable_exception_autocapture=False,
            log_captured_exceptions=False,
            disable_geoip=True,
            enable_local_evaluation=False,
            sync_mode=False,
        )

    async def send(self, events: list[DiagnosticEvent]) -> None:
        """将一批交给客户。

        在工作线程线程上运行：PostHog 客户端是同步，并且当其内部队列饱和时可能会阻塞
        ，而这种情况决不能在事件循环上发生。
        """
        await asyncio.to_thread(self._send_sync, events)

    def _send_sync(self, events: list[DiagnosticEvent]) -> None:
        for event in events:
            properties = event.to_payload()

            # 已识别的事件忽略了这一点，因此它们附加到主机的现有人员上——这就是关联机制。
            #
            if event.distinct_id.startswith(ANONYMOUS_PREFIX):
                properties["$process_person_profile"] = False

            self._client.capture(
                event.event_name,
                distinct_id=event.distinct_id,
                properties=properties,
                timestamp=event.occurred_at,
                disable_geoip=True,
            )

    async def aclose(self) -> None:
        try:
            await asyncio.to_thread(self._client.shutdown)
        except Exception as exc:
            logger.debug("PostHog shutdown failed: %s", type(exc).__name__)
