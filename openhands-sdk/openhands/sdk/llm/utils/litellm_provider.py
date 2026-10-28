from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, cast


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import litellm


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMProvider:
    """LiteLLM-已解析的模型字符串的提供者元数据。

    SDK 在边界处接受完整的模型字符串，但内部提供程序逻辑应该从 LiteLLM 的解析的
    ``provider`` + ``model`` 视图工作。
    """

    model: str
    name: str | None
    # 请求的 API 基点，逐字转发到 LiteLLM。 get_llm_provider 返回的 api_base 被有意丢弃
    # ：LiteLLM 可能会重写它 (e.g. mistral 会添加 "/v1", 一些提供商会注入一个默认的 base
    # )，然后解析后的值会冻结 LiteLLM's 每次调用的解析，从而改变用户配置的值。
    #
    api_base: str | None

    @classmethod
    def from_model(cls, *, model: str, api_base: str | None) -> LLMProvider:
        """使用 LiteLLM 的提供者推理逻辑解析模型字符串。"""
        try:
            get_llm_provider = cast(Any, litellm).get_llm_provider
            parsed_model, provider_name, _dynamic_key, _resolved_api_base = (
                get_llm_provider(
                    model=model,
                    custom_llm_provider=None,
                    api_base=api_base,
                    api_key=None,
                )
            )
        except Exception as exc:
            logger.debug(
                "Failed to parse LiteLLM provider for model=%s: %s",
                model,
                exc,
            )
            parsed_model = model
            provider_name = None

        return cls(
            model=parsed_model,
            name=provider_name,
            api_base=api_base,
        )

    @property
    def is_bedrock(self) -> bool:
        return self.name == "bedrock"

    def api_key_for_litellm(self, api_key: str | None) -> str | None:
        # LiteLLM 将基岩的 api_key 视为 AWS 持有者令牌。 传递非基岩钥匙 (e.g. OpenAI/
        # Anthropic）可能会导致 Bedrock 拒绝请求，并出现“无效的 API 密钥格式”错误。 对于
        #  IAM/SigV4 auth（默认基岩路径），请勿转发 api_key。
        #
        if api_key is not None and self.is_bedrock:
            return None
        return api_key

    def as_litellm_call_kwargs(self, *, api_key: str | None = None) -> dict[str, str]:
        kwargs = {"model": self.model}
        if self.name is not None:
            kwargs["custom_llm_provider"] = self.name
        normalized_api_key = self.api_key_for_litellm(api_key)
        if normalized_api_key is not None:
            kwargs["api_key"] = normalized_api_key
        return kwargs
