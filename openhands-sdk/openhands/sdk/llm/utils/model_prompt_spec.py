"""用于检测模型系列和变体的实用程序。

这些助手允许提示词和其他系统为特定的 LLM 提供者定制行为，同时保持命名启发式集中。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelPromptSpec(BaseModel):
    """检测到给定模型配置的提示词元数据。"""

    model_config = ConfigDict(frozen=True)

    family: str | None = None
    variant: str | None = None


_MODEL_FAMILY_PATTERNS: dict[str, tuple[str, ...]] = {
    "openai_gpt": (
        "gpt-",
        "o1",
        "o3",
        "o4",
    ),
    "anthropic_claude": ("claude",),
    "google_gemini": ("gemini",),
    "meta_llama": ("llama",),
    "mistral": ("mistral",),
    "deepseek": ("deepseek",),
    "alibaba_qwen": ("qwen",),
}

# 有序启发法为一个家庭选择最具体的变体。
_MODEL_VARIANT_PATTERNS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "openai_gpt": (
        (
            "gpt-5-codex",
            (
                "gpt-5-codex",
                "gpt-5.1-codex",
                "gpt-5.2-codex",
                "gpt-5.3-codex",
                "gpt-5.5-codex",
            ),
        ),
        ("gpt-5", ("gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.5")),
    ),
}


def _normalize(name: str | None) -> str:
    return (name or "").strip().lower()


def _match_family(model_name: str) -> str | None:
    normalized = _normalize(model_name)
    if not normalized:
        return None

    for family, patterns in _MODEL_FAMILY_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return family
    return None


def _match_variant(
    family: str,
    model_name: str,
    canonical_name: str | None = None,
) -> str | None:
    patterns = _MODEL_VARIANT_PATTERNS.get(family)
    if not patterns:
        return None

    # 如果可用，请选择 canonical_name，否则返回 model_name
    candidate = _normalize(canonical_name) or _normalize(model_name)
    if not candidate:
        return None

    for variant, substrings in patterns:
        if any(sub in candidate for sub in substrings):
            return variant

    return None


def get_model_prompt_spec(
    model_name: str,
    canonical_name: str | None = None,
) -> ModelPromptSpec:
    """返回给定标识符的家族和变体提示词元数据。"""

    family = _match_family(model_name)
    if family is None and canonical_name:
        family = _match_family(canonical_name)

    variant = None
    if family is not None:
        variant = _match_variant(family, model_name, canonical_name)

    return ModelPromptSpec(family=family, variant=variant)


__all__ = ["ModelPromptSpec", "get_model_prompt_spec"]
