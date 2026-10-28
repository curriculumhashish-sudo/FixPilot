"""API 合规性测试的结果类型。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class APIResponse(StrEnum):
    """格式错误的输入可能的 API 响应类型。"""

    ACCEPTED = "accepted"
    """API 处理了请求（意外输入格式错误）。"""

    REJECTED = "rejected"
    """API 返回错误（预计输入格式错误）。"""

    TIMEOUT = "timeout"
    """请求超时。"""

    CONNECTION_ERROR = "connection_error"
    """无法连接到 API。"""


class ComplianceTestResult(BaseModel):
    """单次合规性测试运行的结果。"""

    pattern_name: str = Field(description="Name of the malformed pattern tested")
    model: str = Field(description="Full model path (e.g., litellm_proxy/...)")
    model_id: str = Field(description="Short model ID for display (e.g., gpt-5.5)")
    provider: str = Field(description="Provider name (anthropic, openai, etc.)")
    response_type: APIResponse = Field(description="How the API responded")
    error_message: str | None = Field(
        default=None, description="Error message if rejected"
    )
    error_type: str | None = Field(
        default=None, description="Exception type name if rejected"
    )
    http_status: int | None = Field(default=None, description="HTTP status code")
    raw_response: dict[str, Any] | None = Field(
        default=None, description="Raw API response if accepted"
    )
    notes: str | None = Field(default=None, description="Additional notes")


class PatternResults(BaseModel):
    """跨多个模型的单一模式的结果。"""

    pattern_name: str
    pattern_description: str
    results: list[ComplianceTestResult] = Field(default_factory=list)

    def add_result(self, result: ComplianceTestResult) -> None:
        self.results.append(result)

    @property
    def rejected_count(self) -> int:
        return sum(1 for r in self.results if r.response_type == APIResponse.REJECTED)

    @property
    def accepted_count(self) -> int:
        return sum(1 for r in self.results if r.response_type == APIResponse.ACCEPTED)


class ComplianceReport(BaseModel):
    """完整的合规性测试报告。"""

    test_run_id: str = Field(description="Unique ID for this test run")
    timestamp: str = Field(description="ISO timestamp of test run")
    elapsed_time: float = Field(
        default=0.0, description="Total test duration in seconds"
    )
    patterns_tested: int = Field(description="Number of patterns tested")
    models_tested: list[str] = Field(description="List of models tested")
    results: list[PatternResults] = Field(default_factory=list)

    @property
    def total_tests(self) -> int:
        return sum(len(p.results) for p in self.results)

    @property
    def total_rejected(self) -> int:
        return sum(p.rejected_count for p in self.results)

    @property
    def total_accepted(self) -> int:
        return sum(p.accepted_count for p in self.results)
