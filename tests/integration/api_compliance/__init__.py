"""API 合规性测试。

该模块提供了一个框架，用于测试不同 LLM APIs 如何响应畸形的消息模式。 这些测试是文档性
质的 - 它们故意发送无效数据以了解API行为。

测试是 NON-BLOCKING：它们预计会失败，并且存在是为了记录 API 行为，而不是强制正确性。
"""

from tests.integration.api_compliance.base import BaseAPIComplianceTest
from tests.integration.api_compliance.result import APIResponse, ComplianceTestResult


__all__ = [
    "BaseAPIComplianceTest",
    "APIResponse",
    "ComplianceTestResult",
]
