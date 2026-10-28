"""将函数调用消息转换为非函数调用消息，反之亦然。

这将注入提示词，以便不支持函数调用的模型仍然可以与函数调用智能体一起使用。

我们遵循以下格式： https://docs.litellm.ai/docs/completion/function_call
"""  # noqa: E501

import copy
import json
import re
from collections.abc import Iterable
from typing import Any, Final, Literal, NotRequired, TypedDict, cast

from litellm import ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk

from openhands.sdk.llm.exceptions import (
    FunctionCallConversionError,
    FunctionCallValidationError,
)
from openhands.sdk.llm.mixins.fn_call_examples import get_example_for_tools


class CacheControl(TypedDict):
    type: Literal["ephemeral"]


class TextPart(TypedDict):
    type: Literal["text"]
    text: str
    cache_control: NotRequired[CacheControl]


Content = str | list[TextPart]

# 灵感来源：
# https://docs.together.ai/docs/llama-3-function-calling#function-calling-w-llama-31-70b
MISSING_DESCRIPTION_PLACEHOLDER: Final[str] = "No description provided"
SCHEMA_INDENT_STEP: Final[int] = 2
SCHEMA_UNION_KEYS: Final[tuple[str, str, str]] = ("anyOf", "oneOf", "allOf")


system_message_suffix_TEMPLATE = """
You have access to the following functions:

{description}

If you choose to call a function ONLY reply in the following format with NO suffix:

<function=example_function_name>
<parameter=example_parameter_1>value_1</parameter>
<parameter=example_parameter_2>
This is the value for the second parameter
that can span
multiple lines
</parameter>
</function>

<IMPORTANT>
Reminder:
- Function calls MUST follow the specified format, start with <function= and end with </function>
- Required parameters MUST be specified
- Only call one function at a time
- You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after.
- If there is no function call available, answer the question like normal with your current knowledge and do not tell the user about function calls
</IMPORTANT>
"""  # noqa: E501

SECURITY_PARAMS_EXAMPLE: Final[str] = """\
<parameter=security_risk>LOW</parameter>
<parameter=summary>Brief description of action</parameter>
"""

STOP_WORDS = ["</function"]

IN_CONTEXT_LEARNING_EXAMPLE_PREFIX = get_example_for_tools

IN_CONTEXT_LEARNING_EXAMPLE_SUFFIX = """
--------------------- END OF NEW TASK DESCRIPTION ---------------------

PLEASE follow the format strictly! PLEASE EMIT ONE AND ONLY ONE FUNCTION CALL PER MESSAGE.
"""  # noqa: E501

# 用于函数调用解析的正则表达式模式
# 注意：函数名后面的换行符是可选的，以兼容各种模型
FN_REGEX_PATTERN = r"<function=([^>]+)>\n?(.*?)</function>"
FN_PARAM_REGEX_PATTERN = r"<parameter=([^>]+)>(.*?)</parameter>"

# 为工具执行结果添加新的正则表达式模式
TOOL_RESULT_REGEX_PATTERN = r"EXECUTION RESULT of \[(.*?)\]:\n(.*)"


def convert_tool_call_to_string(tool_call: dict) -> str:
    """将工具调用转换为字符串格式的内容。"""
    for key in ("function", "id", "type"):
        if key not in tool_call:
            raise FunctionCallConversionError(f"Tool call must contain '{key}' key.")
    if tool_call["type"] != "function":
        raise FunctionCallConversionError("Tool call type must be 'function'.")

    try:
        args = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError as e:
        raise FunctionCallConversionError(
            f"Failed to parse arguments as JSON. "
            f"Arguments: {tool_call['function']['arguments']}"
        ) from e

    parts = [f"<function={tool_call['function']['name']}>"]
    for name, value in args.items():
        if isinstance(value, (list, dict)):
            rendered = json.dumps(value)
        else:
            rendered = str(value)
        if isinstance(value, str) and "\n" in value:
            parts.append(f"<parameter={name}>\n{rendered}\n</parameter>")
        else:
            parts.append(f"<parameter={name}>{rendered}</parameter>")
    parts.append("</function>")
    return "\n".join(parts)


def _summarize_schema_type(schema: object | None) -> str:
    """
    捕获数组、联合、枚举和嵌套类型信息。
    """
    if not isinstance(schema, dict):
        return "unknown" if schema is None else str(schema)

    for key in SCHEMA_UNION_KEYS:
        if key in schema:
            return " or ".join(_summarize_schema_type(option) for option in schema[key])

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " or ".join(str(t) for t in schema_type)
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, list):
            item_types = ", ".join(_summarize_schema_type(item) for item in items)
            return f"array[{item_types}]"
        if isinstance(items, dict):
            return f"array[{_summarize_schema_type(items)}]"
        return "array"
    if schema_type:
        return str(schema_type)
    if "enum" in schema:
        return "enum"
    return "unknown"


def _indent(indent: int) -> str:
    return " " * indent


def _nested_indent(indent: int, levels: int = 1) -> int:
    return indent + SCHEMA_INDENT_STEP * levels


def _get_description(schema: dict[str, object] | None) -> str:
    """
    从模式中提取描述，如果缺少则返回占位符。
    """
    if not isinstance(schema, dict):
        return MISSING_DESCRIPTION_PLACEHOLDER
    description = schema.get("description")
    if isinstance(description, str) and description.strip():
        return description
    return MISSING_DESCRIPTION_PLACEHOLDER


def _format_union_details(schema: dict[str, object], indent: int) -> list[str] | None:
    for key in SCHEMA_UNION_KEYS:
        options = schema.get(key)
        if not isinstance(options, list):
            continue
        lines = [f"{_indent(indent)}{key} options:"]
        for option in options:
            option_type = _summarize_schema_type(option)
            option_line = f"{_indent(_nested_indent(indent))}- {option_type}"
            option_line += (
                f": {_get_description(option if isinstance(option, dict) else None)}"
            )
            lines.append(option_line)
            lines.extend(_format_schema_detail(option, _nested_indent(indent, 2)))
        return lines
    return None


def _format_array_details(schema: dict[str, object], indent: int) -> list[str]:
    lines = [f"{_indent(indent)}Array items:"]
    items = schema.get("items")
    if isinstance(items, list):
        for index, item_schema in enumerate(items):
            item_type = _summarize_schema_type(item_schema)
            lines.append(
                f"{_indent(_nested_indent(indent))}- index {index}: {item_type}"
            )
            lines.extend(_format_schema_detail(item_schema, _nested_indent(indent, 2)))
    elif isinstance(items, dict):
        lines.append(
            f"{_indent(_nested_indent(indent))}Type: {_summarize_schema_type(items)}"
        )
        lines.extend(_format_schema_detail(items, _nested_indent(indent, 2)))
    else:
        lines.append(f"{_indent(_nested_indent(indent))}Type: unknown")
    return lines


def _format_additional_properties(
    additional_props: object | None, indent: int
) -> list[str]:
    if isinstance(additional_props, dict):
        line = (
            f"{_indent(indent)}Additional properties allowed: "
            f"{_summarize_schema_type(additional_props)}"
        )
        lines = [line]
        lines.extend(_format_schema_detail(additional_props, _nested_indent(indent)))
        return lines
    if additional_props is True:
        return [f"{_indent(indent)}Additional properties allowed."]
    if additional_props is False:
        return [f"{_indent(indent)}Additional properties not allowed."]
    return []


def _format_object_details(schema: dict[str, Any], indent: int) -> list[str]:
    lines: list[str] = []
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    if isinstance(properties, dict) and properties:
        lines.append(f"{_indent(indent)}Object properties:")
        for name, prop in properties.items():
            prop_type = _summarize_schema_type(prop)
            required_flag = "required" if name in required else "optional"
            prop_desc = _get_description(prop if isinstance(prop, dict) else None)
            lines.append(
                f"{_indent(_nested_indent(indent))}- {name} ({prop_type},"
                f" {required_flag}): {prop_desc}"
            )
            lines.extend(_format_schema_detail(prop, _nested_indent(indent, 2)))
    lines.extend(
        _format_additional_properties(schema.get("additionalProperties"), indent)
    )
    return lines


def _format_schema_detail(schema: object | None, indent: int = 4) -> list[str]:
    """递归地描述数组、对象、联合和其他属性。"""
    if not isinstance(schema, dict):
        return []

    union_lines = _format_union_details(schema, indent)
    if union_lines is not None:
        return union_lines

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        allowed_types = ", ".join(str(t) for t in schema_type)
        return [f"{_indent(indent)}Allowed types: {allowed_types}"]

    if schema_type == "array":
        return _format_array_details(schema, indent)

    if schema_type == "object":
        return _format_object_details(schema, indent)

    return []


def convert_tools_to_description(tools: list[ChatCompletionToolParam]) -> str:
    ret = ""
    for i, tool in enumerate(tools):
        assert tool["type"] == "function"
        fn = tool["function"]
        if i > 0:
            ret += "\n"
        ret += f"---- BEGIN FUNCTION #{i + 1}: {fn['name']} ----\n"
        if "description" in fn:
            ret += f"Description: {fn['description']}\n"

        if "parameters" in fn:
            ret += "Parameters:\n"
            properties = fn["parameters"].get("properties", {})
            required_params = set(fn["parameters"].get("required", []))

            for j, (param_name, param_info) in enumerate(properties.items()):
                is_required = param_name in required_params
                param_status = "required" if is_required else "optional"
                param_type = _summarize_schema_type(param_info)

                desc = _get_description(
                    param_info if isinstance(param_info, dict) else None
                )

                if "enum" in param_info:
                    enum_values = ", ".join(f"`{v}`" for v in param_info["enum"])
                    desc += f"\nAllowed values: [{enum_values}]"

                ret += (
                    f"  ({j + 1}) {param_name} ({param_type}, {param_status}): {desc}\n"
                )

                detail_lines = _format_schema_detail(param_info, indent=6)
                if detail_lines:
                    ret += "\n".join(detail_lines) + "\n"

        else:
            ret += "No parameters are required for this function.\n"

        ret += f"---- END FUNCTION #{i + 1} ----\n"
    return ret


def _build_system_message_suffix(
    tools: list[ChatCompletionToolParam],
    include_security_params: bool,
) -> str:
    """使用工具描述构建系统消息后缀。"""
    formatted_tools = convert_tools_to_description(tools)
    template = system_message_suffix_TEMPLATE
    if include_security_params:
        template = template.replace(
            "</function>", SECURITY_PARAMS_EXAMPLE + "</function>"
        )
    return template.format(description=formatted_tools)


def _append_to_content(content: Content, suffix: str) -> Content:
    """将文本附加到内容（字符串或列表格式）。"""
    if isinstance(content, str):
        return content + suffix
    if isinstance(content, list):
        if content and content[-1]["type"] == "text":
            content[-1]["text"] += suffix
        else:
            content.append({"type": "text", "text": suffix})
        return content
    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _prepend_to_content(content: Content, prefix: str) -> Content:
    """将文本添加到内容前面（字符串或列表格式）。"""
    if isinstance(content, str):
        return prefix + content
    if isinstance(content, list):
        if content and content[0]["type"] == "text":
            content[0]["text"] = prefix + content[0]["text"]
        else:
            content = [cast(TextPart, {"type": "text", "text": prefix})] + content
        return content
    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _wrap_content_with_example(
    content: Content,
    prefix: str,
    suffix: str,
) -> Content:
    """使用前缀和后缀包装内容以进行 in-上下文学习。"""
    if isinstance(content, str):
        return prefix + content + suffix
    if isinstance(content, list):
        if content and content[0]["type"] == "text":
            content[0]["text"] = prefix + content[0]["text"] + suffix
        else:
            content = (
                [cast(TextPart, {"type": "text", "text": prefix})]
                + content
                + [cast(TextPart, {"type": "text", "text": suffix})]
            )
        return content
    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _convert_system_to_non_fncall(
    content: Content,
    system_message_suffix: str,
) -> dict:
    """将系统消息转换为非函数调用格式。"""
    content = _append_to_content(content, system_message_suffix)
    return {"role": "system", "content": content}


def _convert_user_to_non_fncall(
    content: Content,
    tools: list[ChatCompletionToolParam],
    is_first_user_message: bool,
    add_in_context_learning_example: bool,
) -> dict:
    """将用户消息转换为非函数调用格式。"""
    if is_first_user_message and add_in_context_learning_example:
        example = IN_CONTEXT_LEARNING_EXAMPLE_PREFIX(tools)
        if example:
            content = _wrap_content_with_example(
                content, example, IN_CONTEXT_LEARNING_EXAMPLE_SUFFIX
            )
    return {"role": "user", "content": content}


def _convert_assistant_to_non_fncall(
    message: dict,
    content: Content,
    messages: list[dict],
) -> dict:
    """将助理消息转换为非功能调用格式。"""
    if "tool_calls" in message and message["tool_calls"] is not None:
        if len(message["tool_calls"]) != 1:
            raise FunctionCallConversionError(
                f"Expected exactly one tool call in the message. "
                f"More than one tool call is not supported. "
                f"But got {len(message['tool_calls'])} tool calls. "
                f"Content: {content}"
            )
        try:
            tool_content = convert_tool_call_to_string(message["tool_calls"][0])
        except FunctionCallConversionError as e:
            raise FunctionCallConversionError(
                f"Failed to convert tool call to string.\n"
                f"Current tool call: {message['tool_calls'][0]}.\n"
                f"Raw messages: {json.dumps(messages, indent=2)}"
            ) from e

        if isinstance(content, str):
            content = (content + "\n\n" + tool_content).lstrip()
        elif isinstance(content, list):
            if content and content[-1]["type"] == "text":
                content[-1]["text"] = (
                    content[-1]["text"] + "\n\n" + tool_content
                ).lstrip()
            else:
                content.append({"type": "text", "text": tool_content})
        else:
            raise FunctionCallConversionError(
                f"Unexpected content type {type(content)}. "
                f"Expected str or list. Content: {content}"
            )
    return {"role": "assistant", "content": content}


def _convert_tool_to_non_fncall(message: dict, content: Content) -> dict:
    """将工具消息转换为非函数调用格式（作为用户消息）。"""
    tool_name = message.get("name", "function")
    prefix = f"EXECUTION RESULT of [{tool_name}]:\n"

    if isinstance(content, str):
        content = prefix + content
    elif isinstance(content, list):
        first_text = next((c for c in content if c["type"] == "text"), None)
        if first_text:
            first_text["text"] = prefix + first_text["text"]
        else:
            content = [cast(TextPart, {"type": "text", "text": prefix})] + content

        if "cache_control" in message:
            content[-1]["cache_control"] = cast(CacheControl, {"type": "ephemeral"})
    else:
        raise FunctionCallConversionError(
            f"Unexpected content type {type(content)}. Expected str or list."
        )

    return {"role": "user", "content": content}


def convert_fncall_messages_to_non_fncall_messages(
    messages: list[dict],
    tools: list[ChatCompletionToolParam],
    add_in_context_learning_example: bool = True,
    include_security_params: bool = False,
) -> list[dict]:
    """将函数调用消息转换为非函数调用消息。"""
    messages = copy.deepcopy(messages)
    system_message_suffix = _build_system_message_suffix(tools, include_security_params)

    converted_messages = []
    first_user_message_encountered = False

    for message in messages:
        role = message["role"]
        content: Content = message.get("content") or ""

        if role == "system":
            converted_messages.append(
                _convert_system_to_non_fncall(content, system_message_suffix)
            )
        elif role == "user":
            converted_messages.append(
                _convert_user_to_non_fncall(
                    content,
                    tools,
                    not first_user_message_encountered,
                    add_in_context_learning_example,
                )
            )
            first_user_message_encountered = True
        elif role == "assistant":
            converted_messages.append(
                _convert_assistant_to_non_fncall(message, content, messages)
            )
        elif role == "tool":
            converted_messages.append(_convert_tool_to_non_fncall(message, content))
        else:
            raise FunctionCallConversionError(
                f"Unexpected role {role}. Expected system, user, assistant or tool."
            )

    return converted_messages


def _extract_and_validate_params(
    matching_tool: ChatCompletionToolParamFunctionChunk,
    param_matches: Iterable[re.Match],
    fn_name: str,
) -> dict:
    parameters = matching_tool.get("parameters") or {}
    properties: dict[str, dict] = parameters.get("properties") or {}
    required_params = set(parameters.get("required") or [])
    allowed_params = set(properties)

    params: dict = {}
    found_params: set[str] = set()

    for param_match in param_matches:
        param_name = param_match.group(1)
        param_value: Any = param_match.group(2).strip()

        # 此处排除 security_risk 的原因与从下面的 missing_params 中排除的原因相同：只读
        # 工具 (e.g. finish）永远不要将其声明为允许的参数（请参阅tool.py中的
        # add_security_risk_prediction），但模型在每次调用时都包含它，无论工具如何。
        #
        if (
            allowed_params
            and param_name not in allowed_params
            and param_name != "security_risk"
        ):
            raise FunctionCallValidationError(
                f"Parameter '{param_name}' is not allowed for function '{fn_name}'. "
                f"Allowed parameters: {allowed_params}"
            )

        prop = properties.get(param_name, {})
        param_type = prop.get("type", "string")

        if param_type == "integer":
            try:
                param_value = int(param_value)
            except ValueError:
                raise FunctionCallValidationError(
                    f"Parameter '{param_name}' is expected to be an integer."
                )
        elif param_type == "array":
            try:
                param_value = json.loads(param_value)
            except json.JSONDecodeError:
                raise FunctionCallValidationError(
                    f"Parameter '{param_name}' is expected to be an array."
                )

        enum = prop.get("enum")
        if enum is not None and param_value not in enum:
            raise FunctionCallValidationError(
                f"Parameter '{param_name}' is expected to be one of {enum}."
            )

        params[param_name] = param_value
        found_params.add(param_name)

    # security_risk 被排除：稍后在 Agent._extract_security_risk 中对其进行验证，它知道是
    # 否配置了安全分析器。 当没有分析器处于活动状态时，较弱的型号可能会忽略它；
    # LLMSecurityAnalyzer 对于更强的版本进行强制。
    #
    missing_params = required_params - found_params - {"security_risk"}
    if missing_params:
        raise FunctionCallValidationError(
            f"Missing required parameters for function '{fn_name}': {missing_params}"
        )
    return params


def _preprocess_model_output(content: str) -> str:
    """在解析函数调用之前清理特定于模型的格式。

    删除某些模型（如 Nemotron）在函数调用周围发出的包装标签：
    - </think> 函数调用之前
    - <tool_call>...</tool_call>围绕函数调用

    仅剥离边界处的标签，而不剥离参数值内的标签。
    """
    # 当</think>出现在<function=之前时将其剥离（Nemotron推理结束）
    content = re.sub(r"</think>\s*(?=<function=)", "", content)
    # 当 <tool_call> 出现在 <function= 之前时，将其删除
    content = re.sub(r"<tool_call>\s*(?=<function=)", "", content)
    # 当 </tool_call> 出现在 </function> 之后时将其删除
    content = re.sub(r"(?<=</function>)\s*</tool_call>", "", content)
    return content


def _fix_stopword(content: str) -> str:
    """修复某些 LLM 将不返回停用词时的问题。"""
    content = _preprocess_model_output(content)
    if "<function=" in content and content.count("<function=") == 1:
        if content.endswith("</"):
            content = content.rstrip() + "function>"
        elif not content.rstrip().endswith("</function>"):
            content = content + "\n</function>"
    return content


def _normalize_parameter_tags(fn_body: str) -> str:
    """将格式错误的参数标签标准化为规范格式。

    某些模型偶尔会发出格式错误的参数标签，例如：
        <parameter=command=str_replace</parameter>
    而不是正确的：
        <parameter=command>str_replace</parameter>

    此函数将格式错误的形式重写为正确的形式，以允许下游解析成功。
    """
    # 替换“<parameter=name=value</parameter>”
    # with '<parameter=name>value</parameter>'
    return re.sub(
        r"<parameter=([a-zA-Z0-9_]+)=([^<]*)</parameter>",
        r"<parameter=\1>\2</parameter>",
        fn_body,
    )


# 用于旧模型兼容性的工具名称别名
TOOL_NAME_ALIASES: dict[str, str] = {
    "str_replace_editor": "file_editor",
    "bash": "terminal",
    "execute_bash": "terminal",
    "str_replace": "file_editor",
}


def _find_tool(
    tools: list[ChatCompletionToolParam],
    name: str,
) -> ChatCompletionToolParamFunctionChunk | None:
    """在工具列表中按名称查找工具。"""
    return next(
        (
            tool["function"]
            for tool in tools
            if tool["type"] == "function" and tool["function"]["name"] == name
        ),
        None,
    )


def _resolve_tool_name(
    tools: list[ChatCompletionToolParam],
    fn_name: str,
) -> tuple[str, ChatCompletionToolParamFunctionChunk]:
    """解析工具名称（别名为回退方案）并返回匹配的工具。"""
    matching_tool = _find_tool(tools, fn_name)

    # 如果找不到工具，请尝试使用别名（某些型号使用旧名称）
    if not matching_tool and fn_name in TOOL_NAME_ALIASES:
        fn_name = TOOL_NAME_ALIASES[fn_name]
        matching_tool = _find_tool(tools, fn_name)

    if not matching_tool:
        available_tools = [
            tool["function"]["name"] for tool in tools if tool["type"] == "function"
        ]
        raise FunctionCallValidationError(
            f"Function '{fn_name}' not found in available tools: {available_tools}"
        )

    return fn_name, matching_tool


def _remove_suffix_from_content(content: Content, suffix: str) -> Content:
    """从内容（字符串或列表格式）中删除后缀。"""
    if isinstance(content, str):
        return content.split(suffix)[0]
    if isinstance(content, list) and content and content[-1]["type"] == "text":
        content[-1]["text"] = content[-1]["text"].split(suffix)[0]
    return content


def _strip_in_context_example(
    content: Content,
    tools: list[ChatCompletionToolParam],
) -> Content:
    """从内容中删除 in-上下文学习示例。"""
    example = IN_CONTEXT_LEARNING_EXAMPLE_PREFIX(tools)
    suffix = IN_CONTEXT_LEARNING_EXAMPLE_SUFFIX

    if isinstance(content, str):
        return content.removeprefix(example).removesuffix(suffix)
    if isinstance(content, list):
        for item in content:
            if item["type"] == "text":
                item["text"] = item["text"].removeprefix(example).removesuffix(suffix)
        return content
    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _find_tool_result_match(content: Content) -> re.Match | None:
    """在内容中查找工具结果模式。"""
    if isinstance(content, str):
        return re.search(TOOL_RESULT_REGEX_PATTERN, content, re.DOTALL)
    if isinstance(content, list):
        return next(
            (
                _match
                for item in content
                if item.get("type") == "text"
                and (
                    _match := re.search(
                        TOOL_RESULT_REGEX_PATTERN, item["text"], re.DOTALL
                    )
                )
            ),
            None,
        )
    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _convert_system_to_fncall(content: Content, system_message_suffix: str) -> dict:
    """通过删除后缀将系统消息转换为函数调用格式。"""
    content = _remove_suffix_from_content(content, system_message_suffix)
    return {"role": "system", "content": content}


def _convert_user_to_fncall(
    content: Content,
    tools: list[ChatCompletionToolParam],
    tool_call_counter: int,
    is_first_user_message: bool,
) -> tuple[dict, bool]:
    """将用户消息转换为函数调用格式。

    Returns:
        元组（转换后的消息，是否是工具结果）。
    """
    if is_first_user_message:
        content = _strip_in_context_example(content, tools)

    tool_result_match = _find_tool_result_match(content)

    if tool_result_match:
        # 验证内容是否包含文本（如果是列表）
        if isinstance(content, list):
            text_items = [item for item in content if item.get("type") == "text"]
            if not text_items:
                raise FunctionCallConversionError(
                    f"Could not find text content in message with tool result. "
                    f"Content: {content}"
                )

        tool_name = tool_result_match.group(1)
        tool_result = tool_result_match.group(2).strip()

        return {
            "role": "tool",
            "name": tool_name,
            "content": [{"type": "text", "text": tool_result}]
            if isinstance(content, list)
            else tool_result,
            "tool_call_id": f"toolu_{tool_call_counter - 1:02d}",
        }, True

    return {"role": "user", "content": content}, False


def _find_function_match(content: Content) -> tuple[Content, re.Match | None]:
    """在内容中查找函数调用模式并返回匹配的固定内容。"""
    if isinstance(content, str):
        content = _fix_stopword(content)
        fn_match = re.search(FN_REGEX_PATTERN, content, re.DOTALL)
        return content, fn_match

    if isinstance(content, list):
        if content and content[-1]["type"] == "text":
            content[-1]["text"] = _fix_stopword(content[-1]["text"])
            fn_match = re.search(FN_REGEX_PATTERN, content[-1]["text"], re.DOTALL)
        else:
            fn_match = None

        # 检查函数调用位置是否存在错误
        fn_match_exists = any(
            item.get("type") == "text"
            and re.search(FN_REGEX_PATTERN, item["text"], re.DOTALL)
            for item in content
        )
        if fn_match_exists and not fn_match:
            raise FunctionCallConversionError(
                f"Expecting function call in the LAST index of content list. "
                f"But got content={content}"
            )
        return content, fn_match

    raise FunctionCallConversionError(
        f"Unexpected content type {type(content)}. Expected str or list."
    )


def _strip_function_call_from_content(content: Content) -> Content:
    """从内容中删除函数调用部分。"""
    if isinstance(content, list):
        assert content and content[-1]["type"] == "text"
        content[-1]["text"] = content[-1]["text"].split("<function=")[0].strip()
    elif isinstance(content, str):
        content = content.split("<function=")[0].strip()
    else:
        raise FunctionCallConversionError(
            f"Unexpected content type {type(content)}. Expected str or list."
        )
    return content


def _convert_assistant_to_fncall(
    message: dict,
    content: Content,
    tools: list[ChatCompletionToolParam],
    tool_call_counter: int,
) -> tuple[dict, int]:
    """将助理消息转换为函数调用格式。

    Returns:
        元组（转换后的消息，更新tool_call_counter）。
    """
    content, fn_match = _find_function_match(content)

    if not fn_match:
        return message, tool_call_counter

    fn_name = fn_match.group(1)
    fn_body = _normalize_parameter_tags(fn_match.group(2))

    fn_name, matching_tool = _resolve_tool_name(tools, fn_name)

    # 解析参数
    param_matches = re.finditer(FN_PARAM_REGEX_PATTERN, fn_body, re.DOTALL)
    params = _extract_and_validate_params(matching_tool, param_matches, fn_name)

    # 创建工具调用
    tool_call = {
        "index": 1,  # 始终为 1，因为我们只支持每条消息一个工具调用
        "id": f"toolu_{tool_call_counter:02d}",
        "type": "function",
        "function": {"name": fn_name, "arguments": json.dumps(params)},
    }

    content = _strip_function_call_from_content(content)

    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [tool_call],
    }, tool_call_counter + 1


def convert_non_fncall_messages_to_fncall_messages(
    messages: list[dict],
    tools: list[ChatCompletionToolParam],
    include_security_params: bool = False,
) -> list[dict]:
    """将非函数调用消息转换回函数调用消息。"""
    messages = copy.deepcopy(messages)
    system_message_suffix = _build_system_message_suffix(tools, include_security_params)

    converted_messages = []
    tool_call_counter = 1
    first_user_message_encountered = False

    for message in messages:
        role = message["role"]
        content: Content = message.get("content") or ""

        if role == "system":
            converted_messages.append(
                _convert_system_to_fncall(content, system_message_suffix)
            )
        elif role == "user":
            converted_msg, was_tool_result = _convert_user_to_fncall(
                content,
                tools,
                tool_call_counter,
                not first_user_message_encountered,
            )
            converted_messages.append(converted_msg)
            first_user_message_encountered = True
            # 注意：由于工具结果，tool_call_counter 此处未递增
            # 参考之前的计数器值
        elif role == "assistant":
            converted_msg, tool_call_counter = _convert_assistant_to_fncall(
                message, content, tools, tool_call_counter
            )
            converted_messages.append(converted_msg)
        else:
            raise FunctionCallConversionError(
                f"Unexpected role {role}. Expected system, user, or assistant "
                f"in non-function calling messages."
            )

    return converted_messages


def convert_from_multiple_tool_calls_to_single_tool_call_messages(
    messages: list[dict],
    ignore_final_tool_result: bool = False,
) -> list[dict]:
    """将具有多个工具调用的一条消息分成多条消息。"""
    converted_messages = []

    pending_tool_calls: dict[str, dict] = {}
    for message in messages:
        role: str
        content: Content
        role = message["role"]
        content = message.get("content") or ""
        if role == "assistant":
            if message.get("tool_calls") and len(message["tool_calls"]) > 1:
                # 通过将多个工具调用分成多个消息来处理它们
                for i, tool_call in enumerate(message["tool_calls"]):
                    pending_tool_calls[tool_call["id"]] = {
                        "role": "assistant",
                        "content": content if i == 0 else "",
                        "tool_calls": [tool_call],
                    }
            else:
                converted_messages.append(message)
        elif role == "tool":
            if message["tool_call_id"] in pending_tool_calls:
                # 从待处理列表中删除工具调用
                _tool_call_message = pending_tool_calls.pop(message["tool_call_id"])
                converted_messages.append(_tool_call_message)
                # 添加工具结果
                converted_messages.append(message)
            else:
                assert len(pending_tool_calls) == 0, (
                    f"Found pending tool calls but not found in pending list: "
                    f"{pending_tool_calls=}"
                )
                converted_messages.append(message)
        else:
            assert len(pending_tool_calls) == 0, (
                f"Found pending tool calls but not expect to handle it "
                f"with role {role}: "
                f"{pending_tool_calls=}, {message=}"
            )
            converted_messages.append(message)

    if not ignore_final_tool_result and len(pending_tool_calls) > 0:
        raise FunctionCallConversionError(
            f"Found pending tool calls but no tool result: {pending_tool_calls=}"
        )
    return converted_messages
