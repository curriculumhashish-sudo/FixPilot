import time
from collections.abc import Mapping
from functools import lru_cache
from logging import getLogger
from typing import Any

import httpx
import litellm
from litellm import model_cost
from litellm.utils import get_model_info
from pydantic import SecretStr

from openhands.sdk.llm.utils.openhands_provider import litellm_call_kwargs


logger = getLogger(__name__)


def _merge_raw_model_metadata(model_info: Mapping[str, Any]) -> dict[str, Any]:
    """保留原始 LiteLLM 功能字段。"""
    key = model_info.get("key")
    raw = model_cost.get(key) if isinstance(key, str) else None
    if not isinstance(raw, dict):
        return dict(model_info)
    return {**raw, **model_info}


# 从底层模型复制的定价字段，以便自定义代理别名在 LiteLLM 的全局 `model_cost` 映射中变得
# 可定价 (#4816)。
#
_PRICING_FIELDS: tuple[str, ...] = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
    "max_input_tokens",
    "max_output_tokens",
    "litellm_provider",
    "mode",
)


def _register_proxy_alias_pricing(
    alias: str,
    underlying_model_info: Mapping[str, Any] | None,
    proxy_model_info: Mapping[str, Any] | None,
) -> None:
    """将 `litellm_proxy/*` 别名注册到 LiteLLM 的 `model_cost` 中 (#4816)。

    LiteLLM 去掉 `litellm_proxy/` 前缀并将第一个段解析为提供者，因此像
    `prod/claude-sonnet-4-5-bedrock` 这样
    的自定义名称使得
    `cost_per_token` 筹集资金，跨度默默定价为 0 美元。 使用基础模型的定价注册别名可以
    使其定价，而无需重命名代理模型。
    """
    if not alias or alias in model_cost:
        return
    try:
        litellm.cost_per_token(model=alias, prompt_tokens=1, completion_tokens=1)
        return
    except Exception:
        pass

    entry: dict[str, Any] = {}
    for src in (underlying_model_info, proxy_model_info):
        if isinstance(src, Mapping):
            entry.update({f: src[f] for f in _PRICING_FIELDS if f in src})

    # LiteLLM 的 `get_llm_provider` 不能将 `bedrock_converse` 解析为未知别名标识的提供者
    # 标签（仅 ``bedrock`` 被接受），因此在注册之前需要对其进行规范化，或者
    # `cost_per_token` 仍然会报错。
    #

    if entry.get("litellm_provider") == "bedrock_converse":
        entry["litellm_provider"] = "bedrock"

    if (
        entry.get("input_cost_per_token") is None
        and entry.get("output_cost_per_token") is None
    ):
        return

    entry.setdefault("mode", "chat")
    try:
        litellm.register_model({alias: entry})
    except Exception as e:
        logger.debug("Failed to register litellm_proxy alias %r: %s", alias, e)


@lru_cache
def _get_model_info_from_litellm_proxy(
    secret_api_key: SecretStr | str | None,
    base_url: str,
    model: str,
    cache_key: int | None = None,
):
    logger.debug(f"Get model_info_from_litellm_proxy:{cache_key}")
    try:
        headers = {}
        if isinstance(secret_api_key, SecretStr):
            secret_api_key = secret_api_key.get_secret_value()
        if secret_api_key:
            headers["Authorization"] = f"Bearer {secret_api_key}"

        response = httpx.get(f"{base_url}/v1/model/info", headers=headers)
        data = response.json().get("data", [])
        # 与公共别名 (`model_name`) 或底层提供者/model_name 形式 (`litellm_params.model`
        # ) 匹配。 代理本身接受任何一种形式的请求，并且我们的代理配置通常会宣传一个短别
        # 名（e.g. `claude-opus-4-8`) 获取提供商 ID (`anthropic/claude-opus-4-8`)。 如果
        # 没有第二场比赛，
        # `model_info` 代理上设置的覆盖对于通过其提供者 ID 寻址模型的客户端来说是不可见
        # 的。
        #
        stripped = model.removeprefix("litellm_proxy/")
        current = next(
            (
                info
                for info in data
                if info.get("model_name") == stripped
                or info.get("litellm_params", {}).get("model") == stripped
            ),
            None,
        )
        if current:
            model_info = current.get("model_info")
            logger.debug(f"Got model info from litellm proxy: {model_info}")

            # 使自定义代理别名定价，这样成本检测就不会默默地记录 0 美元 (#4816)。
            #
            underlying_model = current.get("litellm_params", {}).get("model")
            underlying_model_info = None
            if isinstance(underlying_model, str) and underlying_model != stripped:
                try:
                    underlying_model_info = get_model_info(underlying_model)
                except Exception as e:
                    logger.debug(
                        f"get_model_info(underlying={underlying_model}) failed: {e}"
                    )
            _register_proxy_alias_pricing(
                alias=stripped,
                underlying_model_info=underlying_model_info,
                proxy_model_info=model_info,
            )

            return model_info
    except Exception as e:
        logger.debug(
            f"Error fetching model info from proxy: {e}",
            exc_info=True,
            stack_info=True,
        )


def get_litellm_model_info(
    secret_api_key: SecretStr | str | None, base_url: str | None, model: str
) -> dict[str, Any] | None:
    call_kwargs = litellm_call_kwargs(model, base_url)
    model = call_kwargs["model"]
    base_url = call_kwargs["api_base"]

    # 首先尝试通过 openrouter 或 LiteLLM 代理获取模型信息
    try:
        if model.startswith("openrouter"):
            model_info = get_model_info(model)
            if model_info:
                return _merge_raw_model_metadata(model_info)
    except Exception as e:
        logger.debug(f"get_model_info(openrouter) failed: {e}")

    if model.startswith("litellm_proxy/") and base_url:
        # 使用当前小时作为缓存键 - 仅每小时刷新
        cache_key = int(time.time() / 3600)

        model_info = _get_model_info_from_litellm_proxy(
            secret_api_key=secret_api_key,
            base_url=base_url,
            model=model,
            cache_key=cache_key,
        )
        if model_info:
            return model_info

    # 回退方案：尝试基本名称变体
    try:
        model_info = get_model_info(model.split(":")[0])
        if model_info:
            return _merge_raw_model_metadata(model_info)
    except Exception:
        pass
    try:
        model_info = get_model_info(model.split("/")[-1])
        if model_info:
            return _merge_raw_model_metadata(model_info)
    except Exception:
        pass

    return None
