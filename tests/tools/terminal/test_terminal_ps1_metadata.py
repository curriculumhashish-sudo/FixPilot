import json
from unittest.mock import MagicMock

from openhands.tools.terminal.constants import (
    CMD_OUTPUT_METADATA_PS1_REGEX,
    CMD_OUTPUT_PS1_BEGIN,
    CMD_OUTPUT_PS1_END,
)
from openhands.tools.terminal.definition import (
    TerminalObservation,
)
from openhands.tools.terminal.metadata import CmdOutputMetadata
from openhands.tools.terminal.terminal.terminal_session import (
    TerminalSession,
)


def test_ps1_metadata_format():
    """测试 PS1 提示词是否具有正确的格式标记"""
    prompt = CmdOutputMetadata.to_ps1_prompt()
    assert prompt.startswith("\n###PS1JSON###\n")
    assert prompt.endswith("\n###PS1END###\n")
    assert r"\"exit_code\"" in prompt, "PS1 prompt should contain escaped double quotes"


def test_ps1_metadata_json_structure():
    """测试 PS1 提示词是否包含具有预期字段的有效 JSON"""
    prompt = CmdOutputMetadata.to_ps1_prompt()
    # 提取标记之间的 JSON 内容
    json_str = prompt.replace("###PS1JSON###\n", "").replace("\n###PS1END###\n", "")
    # 解析前去掉转义
    json_str = json_str.replace(r"\"", '"')
    # 删除 JSON 之后的所有尾随内容
    json_str = json_str.split("###PS1END###")[0].strip()
    data = json.loads(json_str)

    # 检查必填字段
    expected_fields = {
        "pid",
        "exit_code",
        "username",
        "hostname",
        "working_dir",
        "py_interpreter_path",
    }
    assert set(data.keys()) == expected_fields


def test_ps1_metadata_parsing():
    """测试将 PS1 输出解析为 CmdOutputMetadata"""
    test_data = {
        "exit_code": 0,
        "username": "testuser",
        "hostname": "localhost",
        "working_dir": "/home/testuser",
        "py_interpreter_path": "/usr/bin/python",
    }

    ps1_str = f"""###PS1JSON###
{json.dumps(test_data, indent=2)}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == test_data["exit_code"]
    assert metadata.username == test_data["username"]
    assert metadata.hostname == test_data["hostname"]
    assert metadata.working_dir == test_data["working_dir"]
    assert metadata.py_interpreter_path == test_data["py_interpreter_path"]


def test_ps1_metadata_parsing_string():
    """测试将 PS1 输出解析为 CmdOutputMetadata"""
    ps1_str = r"""###PS1JSON###
{
  "exit_code": "0",
  "username": "myname",
  "hostname": "myhostname",
  "working_dir": "~/mydir",
  "py_interpreter_path": "/my/python/path"
}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.username == "myname"
    assert metadata.hostname == "myhostname"
    assert metadata.working_dir == "~/mydir"
    assert metadata.py_interpreter_path == "/my/python/path"


def test_ps1_metadata_parsing_string_real_example():
    """测试将 PS1 输出解析为 CmdOutputMetadata"""
    ps1_str = r"""
###PS1JSON###
{
  "pid": "",
  "exit_code": "0",
  "username": "runner",
  "hostname": "fv-az1055-610",
  "working_dir": "/home/runner/work/OpenHands/OpenHands",
  "py_interpreter_path": "/home/runner/.cache/pypoetry/virtualenvs/openhands-ai-ULPBlkAi-py3.13/bin/python"
}
###PS1END###
"""  # noqa: E501
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.username == "runner"
    assert metadata.hostname == "fv-az1055-610"
    assert metadata.working_dir == "/home/runner/work/OpenHands/OpenHands"
    assert (
        metadata.py_interpreter_path == "/home/runner/.cache/pypoetry/virtualenvs/"
        "openhands-ai-ULPBlkAi-py3.13/bin/python"
    )


def test_ps1_metadata_parsing_additional_prefix():
    """测试将 PS1 输出解析为 CmdOutputMetadata"""
    test_data = {
        "exit_code": 0,
        "username": "testuser",
        "hostname": "localhost",
        "working_dir": "/home/testuser",
        "py_interpreter_path": "/usr/bin/python",
    }

    ps1_str = f"""
This is something that not part of the PS1 prompt

###PS1JSON###
{json.dumps(test_data, indent=2)}
###PS1END###
"""

    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == test_data["exit_code"]
    assert metadata.username == test_data["username"]
    assert metadata.hostname == test_data["hostname"]
    assert metadata.working_dir == test_data["working_dir"]
    assert metadata.py_interpreter_path == test_data["py_interpreter_path"]


def test_ps1_metadata_parsing_invalid():
    """测试解析无效 PS1 输出返回默认元数据"""
    # 测试无效 JSON
    invalid_json = """###PS1JSON###
    {invalid json}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(invalid_json)
    assert len(matches) == 0  # 找不到无效 JSON 的匹配项

    # 使用缺失的标记进行测试
    invalid_format = """NOT A VALID PS1 PROMPT"""
    matches = CmdOutputMetadata.matches_ps1_metadata(invalid_format)
    assert len(matches) == 0

    # 使用空 PS1 元数据进行测试
    empty_metadata = """###PS1JSON###

###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(empty_metadata)
    assert len(matches) == 0  # 不应为空元数据找到匹配项

    # 在 PS1 元数据中使用空格进行测试
    whitespace_metadata = """###PS1JSON###

    {
        "exit_code": "0",
        "pid": "123",
        "username": "test",
        "hostname": "localhost",
        "working_dir": "/home/test",
        "py_interpreter_path": "/usr/bin/python"
    }

###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(whitespace_metadata)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.pid == 123


def test_ps1_metadata_missing_fields():
    """测试 PS1 元数据中缺失字段的处理"""
    # 仅使用必需字段进行测试
    minimal_data = {"exit_code": 0, "pid": 123}
    ps1_str = f"""###PS1JSON###
{json.dumps(minimal_data)}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.pid == 123
    assert metadata.username is None
    assert metadata.hostname is None
    assert metadata.working_dir is None
    assert metadata.py_interpreter_path is None

    # 测试缺少 exit_code 但有效的 pid
    no_exit_code = {"pid": 123, "username": "test"}
    ps1_str = f"""###PS1JSON###
{json.dumps(no_exit_code)}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == -1  # 默认值
    assert metadata.pid == 123
    assert metadata.username == "test"


def test_ps1_metadata_multiple_blocks():
    """测试处理多个 PS1 元数据块"""
    test_data = {
        "exit_code": 0,
        "username": "testuser",
        "hostname": "localhost",
        "working_dir": "/home/testuser",
        "py_interpreter_path": "/usr/bin/python",
    }

    ps1_str = f"""###PS1JSON###
{json.dumps(test_data, indent=2)}
###PS1END###
Some other content
###PS1JSON###
{json.dumps(test_data, indent=2)}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 2  # 应该找到两个块
    # 两个块都应该解析成功
    metadata1 = CmdOutputMetadata.from_ps1_match(matches[0])
    metadata2 = CmdOutputMetadata.from_ps1_match(matches[1])
    assert metadata1.exit_code == test_data["exit_code"]
    assert metadata2.exit_code == test_data["exit_code"]


def test_ps1_metadata_regex_pattern():
    """测试用于提取 PS1 元数据的正则表达式模式"""
    # 测试基本模式匹配
    test_str = f"{CMD_OUTPUT_PS1_BEGIN}test\n{CMD_OUTPUT_PS1_END}"
    matches = CMD_OUTPUT_METADATA_PS1_REGEX.finditer(test_str)
    match = next(matches)
    assert match.group(1).strip() == "test"

    # 测试之前和之后的内容
    test_str = f"prefix\n{CMD_OUTPUT_PS1_BEGIN}test\n{CMD_OUTPUT_PS1_END}suffix"
    matches = CMD_OUTPUT_METADATA_PS1_REGEX.finditer(test_str)
    match = next(matches)
    assert match.group(1).strip() == "test"

    # 使用多行内容进行测试
    test_str = f"{CMD_OUTPUT_PS1_BEGIN}line1\nline2\nline3\n{CMD_OUTPUT_PS1_END}"
    matches = CMD_OUTPUT_METADATA_PS1_REGEX.finditer(test_str)
    match = next(matches)
    assert match.group(1).strip() == "line1\nline2\nline3"


def test_cmd_output_observation_properties():
    """测试 TerminalObservation 类属性"""
    from openhands.sdk.tool.schema import TextContent

    # 使用成功的命令进行测试
    metadata = CmdOutputMetadata(exit_code=0, pid=123)
    obs = TerminalObservation.from_text(
        text="file1\nfile2",
        command="ls",
        exit_code=0,
        metadata=metadata,
    )
    assert obs.command_id == 123
    assert obs.exit_code == 0
    assert not obs.is_error
    assert len(obs.to_llm_content) == 1
    assert isinstance(obs.to_llm_content[0], TextContent)
    assert "exit code 0" in obs.to_llm_content[0].text
    assert "ls" not in obs.to_llm_content[0].text
    assert "file1\n" in obs.to_llm_content[0].text
    assert "file2\n" in obs.to_llm_content[0].text

    # 使用失败的命令进行测试
    metadata = CmdOutputMetadata(exit_code=1, pid=456)
    obs = TerminalObservation.from_text(
        text="Command failed",
        command="invalid",
        exit_code=1,
        is_error=True,
        metadata=metadata,
    )
    assert obs.command_id == 456
    assert obs.exit_code == 1
    assert obs.is_error
    assert len(obs.to_llm_content) == 2
    assert isinstance(obs.to_llm_content[0], TextContent)
    assert obs.to_llm_content[0].text == TerminalObservation.ERROR_MESSAGE_HEADER
    assert isinstance(obs.to_llm_content[1], TextContent)
    assert "Command failed" in obs.to_llm_content[1].text


def test_ps1_metadata_empty_fields():
    """测试 PS1 元数据中空字段的处理"""
    # 使用空字符串进行测试
    empty_data = {
        "exit_code": 0,
        "pid": 123,
        "username": "",
        "hostname": "",
        "working_dir": "",
        "py_interpreter_path": "",
    }
    ps1_str = f"""###PS1JSON###
{json.dumps(empty_data)}
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(ps1_str)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.pid == 123
    assert metadata.username == ""
    assert metadata.hostname == ""
    assert metadata.working_dir == ""
    assert metadata.py_interpreter_path == ""

    # 测试格式错误但有效 JSON
    malformed_json = """###PS1JSON###
    {
        "exit_code":0,
        "pid"  :  123,
        "username":    "test"  ,
        "hostname": "host",
        "working_dir"    :"dir",
        "py_interpreter_path":"path"
    }
###PS1END###
"""
    matches = CmdOutputMetadata.matches_ps1_metadata(malformed_json)
    assert len(matches) == 1
    metadata = CmdOutputMetadata.from_ps1_match(matches[0])
    assert metadata.exit_code == 0
    assert metadata.pid == 123
    assert metadata.username == "test"
    assert metadata.hostname == "host"
    assert metadata.working_dir == "dir"
    assert metadata.py_interpreter_path == "path"


def test_issue_2416_missing_ps1_metadata_graceful_fallback():
    """当PS1标记缺失时，_handle_completed_command应该
    返回有效的观测结果而不是因断言错误而崩溃。

    当命令产生复杂的输出（TUI 渲染、ANSI 转义序列）并破坏终端屏幕缓冲区中的 PS1 标记
    时，就会发生这种情况。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2416
    """
    mock_terminal = MagicMock()
    mock_terminal.work_dir = "/tmp"
    mock_terminal.username = None

    session = TerminalSession(terminal=mock_terminal)
    session._cwd = "/home/user/project"
    session._initialized = True

    # 模拟没有 PS1 元数据的终端输出（标记已损坏）
    terminal_content = (
        "running 139 tests\ntest result: ok. 139 passed; 0 failed; 0 ignored\n"
    )

    obs = session._handle_completed_command(
        command="cargo test",
        terminal_content=terminal_content,
        ps1_matches=[],  # 找不到 PS1 元数据
    )

    assert isinstance(obs, TerminalObservation)
    assert obs.exit_code == -1
    assert "139 passed" in obs.text
    assert "PS1 metadata" in obs.metadata.suffix
