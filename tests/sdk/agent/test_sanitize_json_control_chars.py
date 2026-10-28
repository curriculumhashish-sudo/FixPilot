"""测试 sanitize_json_control_chars 辅助函数。

该模块测试了 sanitize_json_control_chars 的 JSON 辅助函数，该函数用于 LLMs 生成的原始
控制字符（U+0000–U+001F）进行转义
。 一些模型(e.g。) kimi-k2.5、minimax-m2.5) 发送字节码而不是合法的两个字符 JSON 逃逸
序列，这导致 json.loads() 失败。
"""

import json

from openhands.sdk.agent.utils import sanitize_json_control_chars


def test_valid_json_unchanged():
    """已有效的 JSON 未修改地返回。"""
    raw = '{"command": "echo hello", "path": "/tmp"}'
    assert sanitize_json_control_chars(raw) == raw


def test_literal_newline_escaped():
    """JSON 字符串内的原始 0x0A 字节被替换为 \\n。"""
    raw = '{"command": "line1\nline2"}'
    sanitized = sanitize_json_control_chars(raw)
    assert "\n" not in sanitized
    parsed = json.loads(sanitized)
    assert parsed["command"] == "line1\nline2"


def test_literal_tab_escaped():
    """JSON 字符串内的原始 0x09 字节被替换为 \\t。"""
    raw = '{"indent": "col1\tcol2"}'
    sanitized = sanitize_json_control_chars(raw)
    assert "\t" not in sanitized
    parsed = json.loads(sanitized)
    assert parsed["indent"] == "col1\tcol2"


def test_multiple_control_chars():
    """多个不同的控制字符都被转义。"""
    raw = '{"text": "a\tb\nc\rd"}'
    sanitized = sanitize_json_control_chars(raw)
    parsed = json.loads(sanitized)
    assert parsed["text"] == "a\tb\nc\rd"


def test_null_byte_escaped():
    """原始 NUL (0x00) 字节转义为 \\u0000。"""
    raw = '{"data": "before\x00after"}'
    sanitized = sanitize_json_control_chars(raw)
    assert "\\u0000" in sanitized
    parsed = json.loads(sanitized)
    assert parsed["data"] == "before\x00after"


def test_form_feed_and_backspace():
    """换页符和退格键获得它们的短转义别名。"""
    raw = '{"x": "a\x08b\x0cc"}'
    sanitized = sanitize_json_control_chars(raw)
    assert "\\b" in sanitized
    assert "\\f" in sanitized
    parsed = json.loads(sanitized)
    assert parsed["x"] == "a\x08b\x0cc"


def test_already_escaped_sequences_preserved():
    """正确转义的序列 (\\n, \\t) 是不双重转义的。"""
    raw = r'{"command": "echo \"hello\\nworld\""}'
    sanitized = sanitize_json_control_chars(raw)
    # 已经有效的转义序列应该正确解析
    parsed = json.loads(sanitized)
    assert "hello\\nworld" in parsed["command"]


def test_empty_string():
    """空输入返回空输出。"""
    assert sanitize_json_control_chars("") == ""


def test_realistic_tool_call_arguments():
    """从 LLM 模拟现实的畸形 tool_call.arguments。"""
    # LLM 在“命令”值中发出了一个文字换行符
    raw = '{"command": "cd /workspace && \\\npython test.py", "path": "/workspace"}'
    sanitized = sanitize_json_control_chars(raw)
    parsed = json.loads(sanitized)
    assert "python test.py" in parsed["command"]
    assert parsed["path"] == "/workspace"
