from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import textwrap
import types
from collections.abc import Collection
from typing import (
    Annotated,
    Any,
    Union,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel

from openhands.sdk.context.condenser.base import CondenserBase
from openhands.sdk.context.view import View
from openhands.sdk.event.base import LLMConvertibleEvent
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.llm import LLM, Message


# 根据 RFC 8259 §7，正则表达式匹配在 JSON 字符串内非法的原始 ASCII 控制字符 (U+0000–U+
# 001F)。
#
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")

# 从原始控制字符序数映射到其 JSON 合法的两字符转义序列。 没有短别名的字符会回退到 \uXXXX
# 。
#
_CTRL_ESCAPE_TABLE: dict[int, str] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
}


logger = logging.getLogger(__name__)


def _escape_control_char(m: re.Match[str]) -> str:
    """将单个原始控制字符替换为其 JSON 转义符。"""
    ch = m.group(0)
    return _CTRL_ESCAPE_TABLE.get(ord(ch), f"\\u{ord(ch):04x}")


def sanitize_json_control_chars(raw: str) -> str:
    """对 LLM 生成的 JSON 字符串中的原始控制字符进行转义。

    一些模型 (e.g. kimi-k2.5, minimax-m2.5) 会发出内部包含换行符、制表符等标点符号的
    纯文本
    ``tool_call.arguments`` 而是使用它们应有的两个字符 JSON 转义序列 (``\\n``,
    ``\\t``, …).
    ``json.loads`` 根据 RFC 8259 拒绝这些。

    此函数将每个原始 U+0000–U+001F 字节替换为正确的转义序列，以便字符串变为有效 JSON
    。
    """
    return _CONTROL_CHAR_RE.sub(_escape_control_char, raw)


def _is_chunked_str_field(value: Any, expected_origins: list[Any]) -> bool:
    """如果为仅限 str 的字段提供了字符串块列表，则返回 True。

    一些模型 (e.g. minimax-m2.5) 将单个字符串参数，例如 file_editor's old_str/new_str
     into a JSON 数组的
    块。 这样的列表由调用者重新连接成一个字符串。 ``str | list[str]`` 字段被排除，因
    此真正的有效列表永远不会被压缩，非字符串列表被拒绝，因此它们会
    失败验证而不是被默默地变形。
    """
    return (
        isinstance(value, list)
        and str in expected_origins
        and not any(exp in (list, dict) for exp in expected_origins)
        and all(isinstance(part, str) for part in value)
    )


def _json_schema_expected_types(
    schema: dict[str, Any], defs: dict[str, Any]
) -> list[Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = defs.get(ref.rsplit("/", 1)[-1])
        if isinstance(target, dict):
            return _json_schema_expected_types(target, defs)

    expected: list[Any] = []
    for key in ("anyOf", "oneOf"):
        for option in schema.get(key, []):
            if isinstance(option, dict):
                expected.extend(_json_schema_expected_types(option, defs))

    json_types = schema.get("type")
    if isinstance(json_types, str):
        json_types = [json_types]
    if isinstance(json_types, list):
        type_map = {
            "array": list,
            "boolean": bool,
            "integer": int,
            "number": float,
            "object": dict,
            "string": str,
        }
        expected.extend(
            type_map[json_type] for json_type in json_types if json_type in type_map
        )
    return expected


def fix_malformed_tool_arguments(
    arguments: dict[str, Any], action_type: type[BaseModel] | dict[str, Any]
) -> dict[str, Any]:
    """修复一些发出的畸形工具参数 LLMs 在原生 fn 调用中。

    修复了两个畸形：

    1. 列表/字典参数编码为 JSON 字符串 (e.g. GLM 4.6），它们被解码回本机数组/对象（参
    见下面的示例）。
    2. 仅 str 参数作为字符串块的 JSON 数组发出 (e.g. minimax-m2.5 分块 file_editor 的
     old_str/new_str)，
    它们被连接回单个字符串。

    GLM 4.6 的原始 LLM 输出示例：
    {
        "role": "助理", "content": "我帮你查看文件。", "tool_calls": [{
            “id”：“call_ef8e”，“类型”：“功能”，“功能”：{
                “名称”：“str_replace_editor”，“参数”：'{
                    “命令”：“视图”，“路径”：“/tmp/test.txt"，“view_range”：“[1, 5]”
                }'
            }
        }]
    }

    预期输出：`"view_range" : [1, 5]`

    Note: 参数字段是一个 JSON 字符串。 解码后，view_range 为
    错误地使用字符串“[1, 5]”而不是正确的数组 [1, 5]。 该函数通过检测 view_range 需要
    列表类型并解码 JSON 字符串以获取实际数组来自动修复
    此问题。

    Args:
        arguments: 解析后的参数字典来自 json.loads(tool_call.arguments)。
        action_type: 定义预期参数的模型或 JSON 模式。

    Returns:
        参数 dict 中的 JSON 字符串在适当的情况下进行了解码。
    """
    if not isinstance(arguments, dict):
        return arguments

    fixed_arguments = arguments.copy()

    if isinstance(action_type, dict):
        defs = action_type.get("$defs", {})
        field_types = [
            (field_name, _json_schema_expected_types(field_schema, defs))
            for field_name, field_schema in action_type.get("properties", {}).items()
            if isinstance(field_schema, dict)
        ]
    else:
        field_types = []
        for field_name, field_info in action_type.model_fields.items():
            data_key = field_info.alias if field_info.alias else field_name
            expected_type = field_info.annotation
            if get_origin(expected_type) is Annotated:
                type_args = get_args(expected_type)
                expected_type = type_args[0] if type_args else expected_type

            origin = get_origin(expected_type)
            if origin is Union or origin is types.UnionType:
                type_args = get_args(expected_type)
                expected_origins = [get_origin(arg) or arg for arg in type_args]
            else:
                expected_origins = [origin or expected_type]
            field_types.append((data_key, expected_origins))

    for data_key, expected_origins in field_types:
        if data_key not in fixed_arguments:
            continue

        value = fixed_arguments[data_key]

        # 重新加入模型分块到 JSON 数组中的仅 str 字段。
        if _is_chunked_str_field(value, expected_origins):
            fixed_arguments[data_key] = "".join(value)
            continue

        # 跳过非字符串 - 下面的 JSON 解码仅适用于字符串。
        if not isinstance(value, str):
            continue

        # 检查是否有任何预期类型是列表或字典
        if any(exp in (list, dict) for exp in expected_origins):
            # 尝试将字符串解析为 JSON
            try:
                # `strict=False` 允许控制字符 (e.g. 换行符），外部 json.loads 从转义序列
                # 解码。
                # https://docs.python.org/3/library/json.html#json.JSONDecoder
                parsed_value = json.loads(value, strict=False)
                # json.loads() 返回 dict、list、str、int、float、bool 或 None 仅在与预期
                # 集合类型匹配时才使用解析值
                #
                if isinstance(parsed_value, (list, dict)):
                    fixed_arguments[data_key] = parsed_value
            except (json.JSONDecodeError, ValueError):
                # LLMs 有时追加尾部的垃圾（e.g. XML 在有效的情况下，[tags] JSON. 在最后
                # 一个}处截断 ] 和重试。
                #
                for end_char in ("}", "]"):
                    idx = value.rfind(end_char)
                    if idx == -1:
                        continue
                    with contextlib.suppress(json.JSONDecodeError, ValueError):
                        parsed_value = json.loads(value[: idx + 1], strict=False)
                        if isinstance(parsed_value, (list, dict)):
                            truncated = value[idx + 1 :]
                            logger.warning(
                                "Truncated trailing garbage from tool argument %r: %r",
                                data_key,
                                truncated,
                            )
                            fixed_arguments[data_key] = parsed_value
                            break
    return fixed_arguments


TOOL_NAME_ALIASES: dict[str, str] = {
    "bash": "terminal",
    "command": "terminal",
    "execute": "terminal",
    "execute_bash": "terminal",
    "git": "terminal",
    "reset": "terminal",
    "str_replace": "file_editor",
    "str_replace_editor": "file_editor",
}

# 用于检测格式错误的工具名称的正则表达式（e.g.、“str_replace
# </parameter" or "str_replace</function>”）。 这些发生在工具名称中 LLMs 发出 XML/HTML
# 标签片段。 提取前导标识符并将其用作查找键。
#
_MALFORMED_TOOL_NAME_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)")


def _extract_tool_name_base(tool_name: str) -> str:
    """返回 ``tool_name`` 的前导标识符。

    这用于从格式错误的工具名称中恢复，例如
    ``"str_replace </parameter"`` 或 ``"str_replace</function>"`` that LLMs 有时通过
    追加来发出
    XML/HTML 标签片段。 如果 ``tool_name`` 没有有效的前缀标识，保持不变。
    """
    match = _MALFORMED_TOOL_NAME_RE.match(tool_name)
    return match.group(1) if match else tool_name


# 将工具名称添加到命令参数的终端别名。 与`bash`不同，这些工具（e.g，`git`，`reset`）本身
# 就是命令，应该与它们的参数（e.g，`git status`，`reset clear`）结合使用。
#
_TERMINAL_COMMAND_PREFIX_ALIASES = frozenset({"git", "reset"})

# 这个回退方案故意很小：它只接受精确的、裸命令名称，当某些模型将它们作为工具名称发出时，
# 这些名称作为只读默认值有用。
#
_SHELL_TOOL_FALLBACK_COMMANDS = frozenset({"find", "git", "ls", "pwd"})

# security_risk 字段中常见错误的拼写错误标准化
_SECURITY_RISK_TYPOS = {"security_rort", "securtiy_risk", "security_riks"}


def _normalize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """规范工具参数中的常见拼写错误和不一致。"""
    normalized = arguments.copy()

    # 修复 security_risk 个拼写错误
    for typo in _SECURITY_RISK_TYPOS:
        if typo in normalized:
            normalized["security_risk"] = normalized.pop(typo)
            break

    # 删除任何明显无效的参数（None 值等），但保留所有其他参数以保留特定于工具的参数
    #
    return {k: v for k, v in normalized.items() if v is not None}


def parse_tool_call_arguments(raw_arguments: str) -> dict[str, Any]:
    """解析工具调用参数，仅清理回退方案上的原始控制字符。"""
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        sanitized_args = sanitize_json_control_chars(raw_arguments)
        parsed = json.loads(sanitized_args)

    result = parsed if isinstance(parsed, dict) else {}
    return _normalize_arguments(result)


def _infer_file_editor_command(arguments: dict[str, Any]) -> str | None:
    if "command" in arguments:
        return None
    if "old_str" in arguments:
        return "str_replace"
    if "insert_line" in arguments:
        return "insert"
    if "file_text" in arguments:
        return "create"
    if "path" in arguments:
        return "view"
    return None


def _has_file_editor_hint(arguments: dict[str, Any]) -> bool:
    """检查参数是否包含任何提示，表明这是一个 file_editor 调用。"""
    file_editor_hints = frozenset(
        {
            "old_str",
            "new_str",
            "insert_line",
            "file_text",
            "path",
            "view_range",
        }
    )
    return bool(arguments and any(k in arguments for k in file_editor_hints))


_GREP_FALLBACK_SCRIPT = textwrap.dedent(
    """
    import fnmatch
    import pathlib
    import re
    import sys

    pattern = sys.argv[1]
    root = pathlib.Path(sys.argv[2])
    include = sys.argv[3] if len(sys.argv) > 3 else None
    regex = re.compile(pattern, re.IGNORECASE)

    if root.is_file():
        candidates = [root]
    else:
        candidates = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative_parts = path.relative_to(root).parts
            except ValueError:
                relative_parts = (path.name,)
            if any(part.startswith(".") for part in relative_parts[:-1]):
                continue
            if include:
                if not fnmatch.fnmatch(path.name, include):
                    continue
            elif path.name.startswith("."):
                continue
            candidates.append(path)
        candidates.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)

    for path in candidates:
        if root.is_file():
            if include and not fnmatch.fnmatch(path.name, include):
                continue
            if not include and path.name.startswith("."):
                continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if regex.search(line):
                        sys.stdout.write(f"{path}:{line_number}:{line}")
        except OSError:
            continue
    """
).strip()


def _join_shell_command(parts: list[str]) -> str:
    """使用当前平台的 shell 引用规则加入命令列表。"""
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _build_ripgrep_terminal_command(
    pattern: str,
    search_path: str,
    include: str | None,
) -> str:
    command_parts = ["rg", "-n", "-i", pattern, search_path, "--sortr=modified"]
    if include:
        command_parts.extend(["-g", include])
    return _join_shell_command(command_parts)


def _build_system_grep_terminal_command(
    pattern: str,
    search_path: str,
    include: str | None,
) -> str:
    command_parts = ["grep", "-R", "-I", "-n", "-i", pattern, search_path]
    if include:
        command_parts.append(f"--include={include}")
    return _join_shell_command(command_parts)


def _build_python_grep_terminal_command(
    pattern: str,
    search_path: str,
    include: str | None,
) -> str:
    command_parts = ["python", "-c", f"exec({_GREP_FALLBACK_SCRIPT!r})", pattern]
    command_parts.append(search_path)
    if include:
        command_parts.append(include)
    return _join_shell_command(command_parts)


def _build_grep_terminal_command(arguments: dict[str, Any]) -> str | None:
    """返回结构化 grep 回退方案的便携式终端命令。

    返回 ``None`` 将格式错误的 grep 载荷保留在正常的“未找到工具”路径上，而不是扩大终
    端执行。
    """
    pattern = arguments.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        return None

    path = arguments.get("path")
    search_path = path if isinstance(path, str) and path.strip() else "."

    include = arguments.get("include")
    include_pattern = include if isinstance(include, str) and include.strip() else None

    if shutil.which("rg") is not None:
        return _build_ripgrep_terminal_command(pattern, search_path, include_pattern)
    if shutil.which("grep") is not None:
        return _build_system_grep_terminal_command(
            pattern, search_path, include_pattern
        )
    return _build_python_grep_terminal_command(pattern, search_path, include_pattern)


def _maybe_rewrite_as_terminal_command(
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    """返回 shell 样式工具名称的窄终端回退方案。

    别名在此助手之前处理，因此 Anthropic 样式的名称如
    ``str_replace`` 标准化为规范 SDK 工具，而不是被视为 shell 命令。 当智能体已经公开
     ``terminal`` 时，此帮助器仅针对其他未知
    的名称运行。
    """
    if tool_name == "grep":
        return _build_grep_terminal_command(arguments)

    if arguments or tool_name not in _SHELL_TOOL_FALLBACK_COMMANDS:
        return None

    return tool_name


def normalize_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    available_tools: Collection[str],
) -> tuple[str, dict[str, Any]]:
    """标准化旧工具名称和 Anthropic 样式参数形状。

    优先级是故意的：首先保留显式注册的工具，然后对未知名称应用遗留别名，回退方案只对
    仍然未知的名称才起作用，file_editor 命令推断在工具名称的通用名称确定之后
    运行。
    """
    normalized_tool_name = tool_name
    normalized_arguments = arguments.copy()

    # 仅对未显式注册的工具名称应用别名。 这可以防止劫持与别名共享名称的合法工具。
    #
    if tool_name not in available_tools:
        # 提取前导标识符，以便我们可以从格式错误的名称中恢复，例如“str_replace <
        # /parameter"（LLM 附加了 XML 片段）。 对于像“git”这样的干净名称，这是一个空操作
        # 。
        #
        base_name = _extract_tool_name_base(tool_name)
        alias_target = TOOL_NAME_ALIASES.get(base_name)
        if base_name != tool_name and base_name in available_tools:
            normalized_tool_name = base_name
        elif alias_target and alias_target in available_tools:
            normalized_tool_name = alias_target
            # 对于带前缀的终端别名，将工具名称与命令组合起来
            if (
                alias_target == "terminal"
                and base_name in _TERMINAL_COMMAND_PREFIX_ALIASES
            ):
                original_command = arguments.get("command")
                normalized_arguments = {
                    key: value
                    for key, value in arguments.items()
                    if key in {"security_risk", "summary"}
                }
                if not original_command:
                    normalized_arguments["command"] = base_name
                elif str(original_command).split(maxsplit=1)[:1] == [base_name]:
                    # 已携带可执行文件，e.g。 git(command="git status"). 比较整个 token
                    # 保留“GitHub status”前缀。
                    #
                    normalized_arguments["command"] = original_command
                else:
                    normalized_arguments["command"] = f"{base_name} {original_command}"
        elif "terminal" in available_tools:
            terminal_command = _maybe_rewrite_as_terminal_command(
                tool_name,
                normalized_arguments,
            )
            if terminal_command is not None:
                normalized_tool_name = "terminal"
                # 仅保留与终端相关的参数（security_risk，摘要）以及生成的命令
                #
                normalized_arguments = {
                    key: value
                    for key, value in normalized_arguments.items()
                    if key in {"security_risk", "summary"}
                }
                normalized_arguments["command"] = terminal_command

    if normalized_tool_name == "file_editor":
        inferred_command = _infer_file_editor_command(normalized_arguments)
        if inferred_command is not None:
            normalized_arguments = {
                "command": inferred_command,
                **normalized_arguments,
            }
        elif not normalized_arguments or (
            "command" not in normalized_arguments
            and not _has_file_editor_hint(normalized_arguments)
        ):
            raise ValueError(
                f"Cannot infer 'command' for tool '{normalized_tool_name}' "
                f"from empty arguments {normalized_arguments!r}. "
                f"Expected one of: str_replace, insert, create, view with "
                f"appropriate arguments (e.g., old_str for str_replace, "
                f"path for view)."
            )

    return normalized_tool_name, normalized_arguments


@overload
def prepare_llm_messages(
    view: View,
    condenser: None = None,
    additional_messages: list[Message] | None = None,
    llm: LLM | None = None,
) -> list[Message]: ...


@overload
def prepare_llm_messages(
    view: View,
    condenser: CondenserBase,
    additional_messages: list[Message] | None = None,
    llm: LLM | None = None,
) -> list[Message] | Condensation: ...


def prepare_llm_messages(
    view: View,
    condenser: CondenserBase | None = None,
    additional_messages: list[Message] | None = None,
    llm: LLM | None = None,
) -> list[Message] | Condensation:
    """从对话视图准备 LLM 条消息。

    此实用程序函数提取在 agent.step() 和 ask_agent() 方法之间共享的准备对话上下文的通
    用逻辑。 它在内部处理上下文压缩并在需要时调用回调。

    调用者应传递缓存的 `ConversationState.view`，该缓存在附加事件时增量维护。 这避免
    了每一步都支付 O(n)
    `View.from_events` （和 `enforce_properties`）成本。 参见
    https://github.com/OpenHands/software-agent-sdk/issues/3053.

    Args:
        view: 对话历史记录的 `View`。 该视图被视为
            只读 — 请参阅 `CondenserBase.condense` 了解同一合约。
        condenser: 用于处理上下文窗口限制的可选上下文压缩器
        additional_messages: 要附加的可选附加消息
        llm: 来自智能体的可选 LLM 实例，传递给上下文压缩器
            token 计数或其他 LLM 功能

    Returns:
        准备好 LLM 完成的消息列表，或上下文压缩事件（如果需要上下文压缩）
    """
    llm_convertible_events: list[LLMConvertibleEvent] = view.events

    # 如果注册了上下文压缩器，我们需要给它一个转换事件的机会。 这将产生一个完全符合预期
    # 的事件列表，或者一个需要处理的新的上下文压缩
    #
    if condenser is not None:
        condensation_result = condenser.condense(view, agent_llm=llm)

        match condensation_result:
            case View():
                llm_convertible_events = condensation_result.events

            case Condensation():
                return condensation_result

    # 将事件转换为消息
    messages = LLMConvertibleEvent.events_to_messages(llm_convertible_events)

    # 添加任何其他消息（e.g.，ask_agent 的用户问题）
    if additional_messages:
        messages.extend(additional_messages)

    return messages


# ---------------------------------------------------------------------------
# 异步变种
# ---------------------------------------------------------------------------


async def aprepare_llm_messages(
    view: View,
    condenser: CondenserBase | None = None,
    additional_messages: list[Message] | None = None,
    llm: LLM | None = None,
) -> list[Message] | Condensation:
    """异步：func:`prepare_llm_messages` 的变体。

    调用 ``condenser.acondense()``，以便 LLM 支持的上下文压缩器可以使用异步完成，而不
    会阻塞事件循环。
    """
    llm_convertible_events: list[LLMConvertibleEvent] = view.events

    if condenser is not None:
        condensation_result = await condenser.acondense(view, agent_llm=llm)

        match condensation_result:
            case View():
                llm_convertible_events = condensation_result.events
            case Condensation():
                return condensation_result

    messages = LLMConvertibleEvent.events_to_messages(llm_convertible_events)

    if additional_messages:
        messages.extend(additional_messages)

    return messages
