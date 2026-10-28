import copy
from collections.abc import Sequence
from typing import Any, cast

import httpx
from litellm import ChatCompletionToolParam
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    field_serializer,
    field_validator,
)
from pydantic.json_schema import SkipJsonSchema
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from openhands.sdk.utils.pydantic_secrets import (
    is_redacted_secret,
    serialize_secret,
    validate_secret,
)

from .chat_template import ChatTemplateRenderer


# ============================================================
# 输入 API 响应模型
# ============================================================


class UsageTokens(BaseModel):
    prompt_tokens: int | None = None
    total_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tokens_details: dict | None = None
    model_config = ConfigDict(extra="allow")


class ClassificationItem(BaseModel):
    """每个标签一个或平面分类结果。"""

    index: int | None = None
    label: str | None = None
    probs: list[float]
    num_classes: int | None = None
    model_config = ConfigDict(extra="allow")


class ClassificationResponse(BaseModel):
    id: str | None = None
    object: str | None = None
    created: int | None = None
    model: str | None = None
    data: list[ClassificationItem] = Field(default_factory=list)
    usage: UsageTokens | None = None
    model_config = ConfigDict(extra="allow")


class LabelProbMap(BaseModel):
    """归一化概率图标签 -> 值，具有可选的排序。"""

    probs: dict[str, float]  # {"label": probability}
    order: list[str] | None = None  # 如果您要求特定订单
    model_config = ConfigDict(extra="forbid")


# ============================================================
# CriticClient
# ============================================================


DEFAULT_CRITIC_SERVER_URL = "https://llm-proxy.app.all-hands.dev/vllm"
DEFAULT_CRITIC_MODEL_NAME = "critic"


class CriticClient(BaseModel):
    """
    Critic 分类服务的核心推理客户端。

    拥有：
      - 配置（服务器 URL、API 密钥、模型、分词器等）
      - 标签空间（仅用于预测）
      - 消息规范化和聊天模板格式化
      - 通过 vLLM 进行推理 /classify 端点

    不是否处理：
      - 数据集加载
      - 地面实况提取
      - 评估/指标
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    # --- 连接/模型配置 ---
    server_url: str = Field(
        default=DEFAULT_CRITIC_SERVER_URL,
        description="Base URL of the vLLM classification service",
    )
    # validate_secret() 将空、仅空白和已脱敏输入标准化为 None。 在响应模型重建期间，该值
    # 可能序列化为 null，但它不是公共 REST 模式合约的一部分。
    #
    api_key: str | SecretStr | SkipJsonSchema[None] = Field(
        ..., description="API key for authenticating with the vLLM service"
    )
    model_name: str = Field(
        default=DEFAULT_CRITIC_MODEL_NAME, description="Name of the model to use"
    )
    tokenizer_name: str = Field(
        default="Qwen/Qwen3-4B-Instruct-2507",
        description="HuggingFace tokenizer name for loading chat template",
    )
    pass_tools_definitions: bool = Field(
        default=True, description="Whether to pass tool definitions to the model"
    )
    timeout_seconds: float = Field(
        default=300.0, description="Timeout for requests to the model"
    )
    has_success_label: bool = Field(
        default=True, description="Whether the model predicts success label at index 0"
    )

    # --- 运行时字段 ---
    _client: httpx.Client = PrivateAttr(default_factory=httpx.Client)
    _template_renderer: ChatTemplateRenderer | None = PrivateAttr(default=None)

    # --- 标签空间 ---
    sentiment_labels: tuple[str, ...] = (
        "sentiment_positive",
        "sentiment_neutral",
        "sentiment_negative",
    )
    agent_issue_labels: tuple[str, ...] = (
        "misunderstood_intention",
        "did_not_follow_instruction",
        "insufficient_analysis",
        "insufficient_clarification",
        "improper_tool_use_or_setup",
        "loop_behavior",
        "insufficient_testing",
        "insufficient_debugging",
        "incomplete_implementation",
        "file_management_errors",
        "scope_creep",
        "risky_actions_or_permission",
        "other_agent_issue",
    )
    infra_labels: tuple[str, ...] = (
        "infrastructure_external_issue",
        "infrastructure_agent_caused_issue",
    )
    user_followup_labels: tuple[str, ...] = (
        "clarification_or_restatement",
        "correction",
        "direction_change",
        "vcs_update_requests",
        "progress_or_scope_concern",
        "frustration_or_complaint",
        "removal_or_reversion_request",
        "other_user_issue",
    )
    sentiment_map: dict[str, str] = {
        "Positive": "sentiment_positive",
        "Neutral": "sentiment_neutral",
        "Negative": "sentiment_negative",
    }

    # ---------------------
    # 验证
    # ---------------------
    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_and_convert_api_key(
        cls, v: str | SecretStr | None, info
    ) -> SecretStr | None:
        """验证 api_key 并在需要时解密。"""
        return validate_secret(v, info)

    @field_serializer("api_key", when_used="always")
    def _serialize_api_key(self, v: str | SecretStr | None, info):
        secret = v if v is None or isinstance(v, SecretStr) else SecretStr(v)
        return serialize_secret(secret, info)

    # ---------------------
    # 标签助手
    # ---------------------
    @property
    def all_labels(self) -> tuple[str, ...]:
        base_labels = (
            self.sentiment_labels
            + self.agent_issue_labels
            + self.infra_labels
            + self.user_followup_labels
        )
        if self.has_success_label:
            return ("success",) + base_labels
        return base_labels

    # ---------------------
    # 分词器/格式化
    # ---------------------
    def _get_template_renderer(self) -> ChatTemplateRenderer:
        """延迟初始化聊天模板渲染器。"""
        if self._template_renderer is None:
            self._template_renderer = ChatTemplateRenderer(
                tokenizer_name=self.tokenizer_name
            )
        return self._template_renderer

    @staticmethod
    def normalize_messages(messages: Sequence[dict]) -> Sequence[dict]:
        """确保消息均具有字符串内容并展平文本块。"""
        out: list[dict] = []
        for msg in messages or []:
            content = msg.get("content", "") or ""
            if isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = "\n".join(text_parts)
            if not isinstance(content, str):
                content = str(content)
            out.append({"role": msg.get("role", ""), "content": content})
        return out

    def apply_chat_template(
        self,
        messages: Sequence[dict],
        tools: Sequence[ChatCompletionToolParam] | None = None,
    ) -> str:
        renderer = self._get_template_renderer()
        msgs = self.normalize_messages(copy.deepcopy(messages))
        # 将工具转换为 Sequence[dict[str、Any]] 以实现类型兼容性 ChatCompletionToolParam
        #  是结构上兼容的 TypedDict
        #
        tools_dicts: Sequence[dict[str, Any]] | None = (
            cast(Sequence[dict[str, Any]], tools) if tools is not None else None
        )
        if self.pass_tools_definitions and tools_dicts:
            return renderer.apply_chat_template(
                msgs, tools=tools_dicts, add_generation_prompt=False
            )
        return renderer.apply_chat_template(msgs, add_generation_prompt=False)

    # ---------------------
    # 推理
    # ---------------------
    def _get_api_key_value(self) -> str:
        if self.api_key is None:
            raise ValueError("api_key must be non-empty")
        api_key_value = (
            self.api_key.get_secret_value()
            if isinstance(self.api_key, SecretStr)
            else self.api_key
        )
        if not api_key_value.strip() or is_redacted_secret(api_key_value):
            raise ValueError("api_key must be non-empty")
        return api_key_value

    def classify_trace(
        self,
        messages: Sequence[dict],
        tools: Sequence[ChatCompletionToolParam] | None = None,
    ) -> ClassificationResponse:
        """POST /classify 并将响应解析为 ClassificationResponse。"""
        formatted = self.apply_chat_template(messages, tools)

        def should_retry(exc: BaseException) -> bool:
            # 重试只有在500内部服务器错误时
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code == 500
            return False

        @retry(
            retry=retry_if_exception(should_retry),
            stop=stop_after_attempt(3),  # 最多尝试 3 次
            wait=wait_exponential(
                multiplier=1, min=1, max=8
            ),  # 指数退避：1s、2s、4s、8s
            reraise=True,  # 如果所有重试失败，则重新引发最后一个异常
        )
        def _post_with_retry():
            api_key_value = self._get_api_key_value()
            resp = self._client.post(
                f"{self.server_url}/classify",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key_value}",
                },
                json={"model": self.model_name, "input": formatted},
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            return resp

        resp = _post_with_retry()
        return ClassificationResponse.model_validate(resp.json())

    # ---------------------
    # 后处理助手
    # ---------------------
    def extract_prob_map(self, response: ClassificationResponse) -> LabelProbMap:
        """
        服务器格式（仅限平面，严格）：
          response.data == [ ClassificationItem(概率=[p0, p1, ..., pN-1],
                            num_classes=N) ]
        我们将概率直接与 self.all_labels 对齐（相同的长度，相同的顺序）。
        """
        if not response.data:
            raise ValueError("empty response.data from server")

        item = response.data[0]
        if not item.probs:
            raise ValueError("server returned empty 'probs'")
        if item.num_classes is not None and item.num_classes != len(item.probs):
            raise ValueError(
                f"num_classes ({item.num_classes}) does not match "
                f"len(probs) ({len(item.probs)})"
            )

        probs = [float(x) for x in item.probs]
        if len(probs) != len(self.all_labels):
            raise ValueError(
                f"len(probs) ({len(probs)}) != len(all_labels) "
                f"({len(self.all_labels)}). "
                "Ensure server label space matches client label space."
            )

        mapping = {lbl: probs[i] for i, lbl in enumerate(self.all_labels)}
        return LabelProbMap(probs=mapping, order=list(self.all_labels))
