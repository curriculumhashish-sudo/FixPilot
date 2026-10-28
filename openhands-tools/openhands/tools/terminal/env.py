"""终端后端的环境助手。"""

import re
from collections.abc import Mapping

from openhands.sdk.utils import sanitized_env


ENV_VAR_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def normalize_terminal_env(
    extra_env: Mapping[str, str] | None,
) -> dict[str, str] | None:
    """验证并复制客户端提供的终端环境变量。"""
    if extra_env is None:
        return None

    normalized: dict[str, str] = {}
    for key, value in extra_env.items():
        if not isinstance(key, str) or not ENV_VAR_NAME_RE.match(key):
            raise ValueError(f"Invalid terminal environment variable name: {key!r}")
        if not isinstance(value, str):
            raise TypeError(
                "Terminal environment variable values must be strings: "
                f"{key!r}={value!r}"
            )
        normalized[key] = value
    return normalized


def build_terminal_env(extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """返回清理后的流程环境以及客户端提供的覆盖。"""
    env = sanitized_env()
    normalized = normalize_terminal_env(extra_env)
    if normalized:
        env.update(normalized)
        env = sanitized_env(env)
    return env
