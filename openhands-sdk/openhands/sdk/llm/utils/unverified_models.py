import importlib

import litellm
from pydantic import SecretStr

from openhands.sdk.llm.utils.verified_models import VERIFIED_MODELS
from openhands.sdk.logger import get_logger


def _get_boto3():
    """如果可用，则获取 boto3 模块，否则返回 None。"""
    try:
        return importlib.import_module("boto3")
    except ModuleNotFoundError:
        return None


logger = get_logger(__name__)


def _list_bedrock_foundation_models(
    aws_region_name: str, aws_access_key_id: str, aws_secret_access_key: str
) -> list[str]:
    boto3 = _get_boto3()
    if boto3 is None:
        logger.warning(
            "boto3 is not installed. To use Bedrock models,"
            "install with: openhands-sdk[boto3]"
        )
        return []

    try:
        # 如果未配置 AWS 参数，则不会查询 AWS 基岩模型 ID。
        client = boto3.client(
            service_name="bedrock",
            region_name=aws_region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        foundation_models_list = client.list_foundation_models(
            byOutputModality="TEXT", byInferenceType="ON_DEMAND"
        )
        model_summaries = foundation_models_list["modelSummaries"]
        return ["bedrock/" + model["modelId"] for model in model_summaries]
    except Exception as err:
        logger.warning(
            "%s. Please config AWS_REGION_NAME AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY"
            " if you want use bedrock model.",
            err,
        )
        return []


def _is_litellm_bedrock_model(model: str) -> bool:
    """LiteLLM 是否仅通过 AWS 基岩服务于 ``model``。

    许多基岩 ID 不带 ``bedrock`` 前缀（``deepseek.r1-v1:0``、
    ``us.anthropic.claude-...``），所以询问 LiteLLM 的模型成本映射哪个提供商将 id 归
    档在（``bedrock``、
    ``bedrock_converse``、``bedrock_mantle``）下。
    """
    if model.startswith("bedrock"):
        return True
    provider = litellm.model_cost.get(model, {}).get("litellm_provider")
    return isinstance(provider, str) and provider.startswith("bedrock")


def get_supported_llm_models(
    aws_region_name: str | None = None,
    aws_access_key_id: SecretStr | None = None,
    aws_secret_access_key: SecretStr | None = None,
) -> list[str]:
    """从 LiteLLM、已验证的 OpenRouter 路线和基岩获取模型。

    除非配置 AWS 凭据，否则基岩模型将被排除。

    Returns:
        list[str]：可用模型标识符。
    """
    litellm_model_list = (
        litellm.model_list
        + list(litellm.model_cost.keys())
        + [f"openrouter/{model}" for model in VERIFIED_MODELS["openrouter"]]
    )
    litellm_model_list_without_bedrock = [
        m for m in litellm_model_list if not _is_litellm_bedrock_model(m)
    ]
    bedrock_model_list = []
    if aws_region_name and aws_access_key_id and aws_secret_access_key:
        bedrock_model_list = _list_bedrock_foundation_models(
            aws_region_name,
            aws_access_key_id.get_secret_value(),
            aws_secret_access_key.get_secret_value(),
        )
    model_list = litellm_model_list_without_bedrock + bedrock_model_list
    return model_list


def _split_is_actually_version(split: list[str]) -> bool:
    return (
        len(split) > 1
        and bool(split[1])
        and bool(split[1][0])
        and split[1][0].isdigit()
    )


def _get_litellm_provider_names() -> set[str]:
    provider_list = litellm.provider_list

    result: set[str] = set()

    # 在LiteLLM中，这是`list(LlmProviders)`i.e。 枚举成员。
    for p in provider_list:
        if isinstance(p, str):
            if p:
                result.add(p)
            continue

        result.add(p.value)

    return result


_LITELLM_PROVIDER_NAMES = _get_litellm_provider_names()


def _extract_model_and_provider(model: str) -> tuple[str, str, str]:
    """从模型标识符中提取提供者和模型信息。

    这是故意保守的：
    - 仅当前缀是已知的 LiteLLM 提供程序时，才将其视为提供程序。
    - 否则，返回空提供程序（调用者将其存储在“其他”下）。

    这可以防止“us”、“eu”、“low”、“1024-x-1024”等虚假提供商泄漏到下游 UI。
    """

    separator = "/"
    split = model.split(separator)

    if len(split) == 1:
        # 找不到“/" 分隔符，请尝试使用“.”
        separator = "."
        split = model.split(separator)
        if _split_is_actually_version(split):
            split = [separator.join(split)]  # 撤消分裂

    if len(split) == 1:
        matched_provider = ""
        for provider, models in VERIFIED_MODELS.items():
            if split[0] in models:
                matched_provider = provider
                break

        if matched_provider:
            return matched_provider, split[0], "/"

        return matched_provider, model, ""

    provider = split[0]
    model_id = separator.join(split[1:])

    if provider not in _LITELLM_PROVIDER_NAMES:
        return "", model, ""

    return provider, model_id, separator


def get_unverified_models(
    aws_region_name: str | None = None,
    aws_access_key_id: SecretStr | None = None,
    aws_secret_access_key: SecretStr | None = None,
) -> dict[str, list[str]]:
    """
    按提供商组织未经验证的模型标识符的映射。
    """
    result_dict: dict[str, list[str]] = {}

    models = get_supported_llm_models(
        aws_region_name, aws_access_key_id, aws_secret_access_key
    )
    for model in models:
        provider, model_id, separator = _extract_model_and_provider(model)

        # 忽略带有“.”分隔符的“Anthropic”提供者。这些是过时且不兼容的提供商。
        #
        if provider == "anthropic" and separator == ".":
            continue

        # 经重复数据删除验证的模型
        if provider in VERIFIED_MODELS and model_id in VERIFIED_MODELS[provider]:
            continue

        key = provider or "other"
        if key not in result_dict:
            result_dict[key] = []

        result_dict[key].append(model_id)

    return result_dict


UNVERIFIED_MODELS_EXCLUDING_BEDROCK = get_unverified_models()
