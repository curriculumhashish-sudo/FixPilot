"""通用 HTTP 导出器。

已批处理的已 sanitized 事件 POSTs，配置的端点。 旨在前端一个后端，该后端在转发之前验
证运行时的认证和同意，因此不需要任何供应商凭据需要在沙盒中生存。

载荷合约是稳定的并记录在智能体-服务器 README 中：

    POST <endpoint> 内容类型：application/json
    Authorization: Bearer <token> #仅当配置token时

    {
      “schema_version”：1，“事件”：[
        {
          “事件”：“agent_server.conversation_finished”，“distinct_id”：“
          <user id, or anon:...>”，“occurred_at”：“2026-07-21T10：00：00Z”，“属性”：{
           ... 列入许可
          名单的属性...}
        }
      ]
    }

失败传播到``BufferedTelemetrySink``，它拥有重试、丢弃和有界关闭行为——这个类故意实现了
它的None。
"""

from typing import Final

import httpx

from openhands.agent_server.telemetry.models import (
    TELEMETRY_SCHEMA_VERSION,
    DiagnosticEvent,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS: Final[float] = 15.0


class HttpExporter:
    """将清理后的诊断事件发送到任意 HTTP 端点。"""

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._endpoint = endpoint
        self._headers = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(self, events: list[DiagnosticEvent]) -> None:
        payload = {
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "events": [
                {
                    "event": str(event.event_name),
                    "distinct_id": event.distinct_id,
                    "occurred_at": event.occurred_at.isoformat(),
                    "properties": event.to_payload(),
                }
                for event in events
            ],
        }
        response = await self._client.post(
            self._endpoint, json=payload, headers=self._headers
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception as exc:
            logger.debug("HTTP exporter close failed: %s", type(exc).__name__)
