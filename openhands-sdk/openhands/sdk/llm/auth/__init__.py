"""身份验证用于 LLM 基于订阅的访问的模块。

该模块为支持基于订阅的访问的 LLM 提供商提供基于 OAuth 的身份验证（e.g.、ChatGPT Plus/
Pro 用于 OpenAI Codex 模型）。
"""

from openhands.sdk.llm.auth.credentials import (
    CredentialStore,
    OAuthCredentials,
)
from openhands.sdk.llm.auth.openai import (
    OPENAI_CODEX_MODELS,
    OpenAISubscriptionAuth,
    SupportedVendor,
    create_subscription_llm_from_config,
    inject_system_prefix,
    transform_for_subscription,
)


__all__ = [
    "CredentialStore",
    "OAuthCredentials",
    "OpenAISubscriptionAuth",
    "OPENAI_CODEX_MODELS",
    "SupportedVendor",
    "create_subscription_llm_from_config",
    "inject_system_prefix",
    "transform_for_subscription",
]
