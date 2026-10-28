"""脱敏帮助器将机密排除在导出的工件之外。

用于出口边界 (e.g. 已持久化会话数据离开服务器的轨迹下载]，必须凭据从不携带 —— 无论是
明文还是不可恢复的 Fernet 密文。
"""

import json
from pathlib import Path
from typing import Final

from openhands.sdk.llm.llm import LLM_SECRET_FIELDS
from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE


# 在已持久化会话载荷中的任何位置携带凭据的字段名称（base_state.json、meta.json、事件）。
#  保存在同步中
# ``LLM_SECRET_FIELDS`` 并使用设置级别 ``llm_api_key`` 别名进行扩展。
#
TRAJECTORY_SECRET_FIELDS: frozenset[str] = frozenset(
    (*LLM_SECRET_FIELDS, "llm_api_key")
)

# 以换行符分隔的 JSON 文件的后缀：每行一个 JSON 文档。
_JSON_LINES_SUFFIX: Final[str] = ".jsonl"


def _is_secret_value(key: object, value: object) -> bool:
    if not isinstance(value, str) or value in ("", REDACTED_SECRET_VALUE):
        return False
    # 已持久化会话中的任何 Fernet token 都是使用服务器的 OH_SECRET_KEY (e.g. 自定义机密
    # ``secret_registry.secret_sources``），因此可回收机密材料，无论哪个领域携带它。
    #
    if value.startswith(FERNET_TOKEN_PREFIX):
        return True
    return key in TRAJECTORY_SECRET_FIELDS


def redact_secrets_in_obj(obj: object) -> bool:
    """递归地将机密值替换为脱敏标记。

    如果有任何更改，则返回 ``True``。 无论是明文还是加密的（Fernet）机密材料，都进行
    了掩码处理，因此该保证无论何时``OH_SECRET_KEY``被配
    置已持久化，都有效。
    """
    changed = False
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _is_secret_value(key, value):
                obj[key] = REDACTED_SECRET_VALUE
                changed = True
            elif redact_secrets_in_obj(value):
                changed = True
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            if _is_secret_value(None, item):
                obj[index] = REDACTED_SECRET_VALUE
                changed = True
            elif redact_secrets_in_obj(item):
                changed = True
    return changed


def should_redact(path: Path) -> bool:
    """如果导出将 ``path`` 的内容传递到脱敏，则返回 True。

    已持久化对话载荷是 JSON (``*.json``) 或换行符分隔的 JSON（``*.jsonl``/the 每个事
    件日志文件）； 这些是字节经过
    ``redacted_json_bytes`` 的文件。 所有其他文件均按原样导出。
    """
    return path.suffix.lower() in (".json", _JSON_LINES_SUFFIX)


def redacted_json_bytes(data: bytes, path: Path) -> bytes | None:
    """返回已脱敏 ``data``，如果不需要编辑，则返回 ``None``。

    ``data``是``path``的内容，选择了一个文件``should_redact``； ``.jsonl`` 路径每行解
    析一个 JSON 文档。 非 UTF-
    8 或未解析为 JSON 的内容保持不变（返回 ``None``），因此存档对于非机密内容是字节相
    同的。
    """
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if path.suffix.lower() == _JSON_LINES_SUFFIX:
        changed = False
        out_lines: list[str] = []
        for line in raw.splitlines(keepends=True):
            stripped = line.strip()
            if not stripped:
                out_lines.append(line)
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                out_lines.append(line)
                continue
            if redact_secrets_in_obj(obj):
                changed = True
            newline = "\n" if line.endswith("\n") else ""
            out_lines.append(json.dumps(obj) + newline)
        return "".join(out_lines).encode("utf-8") if changed else None

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not redact_secrets_in_obj(obj):
        return None
    return json.dumps(obj).encode("utf-8")
