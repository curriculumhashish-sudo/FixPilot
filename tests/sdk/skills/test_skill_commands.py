"""测试技能内容中的内联 !`command` 执行。

!`command` 语法允许技能作者将动态 shell 输出嵌入到 Markdown 中。 这些测试验证：

  - 基本执行： !`echo hello` → hello
  - 错误/超时处理
  - 大输出的输出截断
  - 代码块安全：围栏 (```) and inline (`) 块永远不会执行
  - 未封闭的围栏块：奇数个 ``` 分隔符不得泄漏最后一个未封闭围栏后面的命令
  - 逃生口：\\!`cmd` 保留为文字文本 !`cmd`
  - 与技能模型集成（加载+渲染）
"""

from pathlib import Path

import pytest

from openhands.sdk.skills import Skill
from openhands.sdk.skills.execute import (
    MAX_OUTPUT_SIZE,
    _execute_inline_command,
    render_content_with_commands,
)
from tests.command_utils import python_command


# ---------------------------------------------------------------------------
# 低级：_execute_inline_command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "timeout", "check_fn"),
    [
        pytest.param("echo hello", 10.0, lambda r: r == "hello", id="success"),
        pytest.param(
            python_command("print('line1'); print('line2'); print('line3')"),
            10.0,
            lambda r: r == "line1\nline2\nline3",
            id="multiline_output",
        ),
        pytest.param(
            python_command("import sys; sys.exit(1)"),
            10.0,
            lambda r: "[Error:" in r,
            id="failure",
        ),
        pytest.param(
            python_command("import time; time.sleep(5)"),
            0.1,
            lambda r: "timed out" in r,
            id="timeout",
        ),
    ],
)
def test_execute_inline_command(command, timeout, check_fn):
    assert check_fn(_execute_inline_command(command, timeout=timeout))


def test_execute_inline_command_respects_working_dir(tmp_path: Path):
    result = _execute_inline_command(
        python_command("from pathlib import Path; print(Path.cwd())"),
        working_dir=tmp_path,
    )
    assert result == str(tmp_path.resolve())


def test_execute_inline_command_truncates_large_output():
    size = MAX_OUTPUT_SIZE + 100
    result = _execute_inline_command(
        python_command(f"import sys; sys.stdout.write('x' * {size})")
    )
    assert result.endswith("... [output truncated]")
    assert len(result.encode()) <= MAX_OUTPUT_SIZE + 50  # 小开销还可以


# ---------------------------------------------------------------------------
# 渲染：基本命令替换
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("Hello world", "Hello world", id="plain_text_unchanged"),
        pytest.param("Branch: !`echo main`", "Branch: main", id="single_command"),
        pytest.param(
            "A: !`echo one` B: !`echo two`", "A: one B: two", id="multiple_commands"
        ),
        pytest.param("!``", "!``", id="empty_backticks_ignored"),
    ],
)
def test_render_basic(content, expected):
    assert render_content_with_commands(content) == expected


# ---------------------------------------------------------------------------
# 渲染：代码块永远不会被执行
# ---------------------------------------------------------------------------


def test_render_preserves_inline_code():
    """常规的 `code` 跨度保持不变。"""
    content = "Use `git status` to check"
    assert render_content_with_commands(content) == content


def test_render_preserves_fenced_block():
    """``` 栅栏内的命令不会执行。"""
    content = "Real: !`echo yes`\n```\n!`echo no`\n```"
    result = render_content_with_commands(content)
    assert "yes" in result
    assert "!`echo no`" in result


def test_render_inline_code_next_to_command():
    """`code` 紧接着是一个真正的 !`cmd`——两者都处理正确。"""
    content = "Run `git status` then !`echo done`"
    result = render_content_with_commands(content)
    assert "`git status`" in result
    assert "done" in result


# ---------------------------------------------------------------------------
# 效果图：未封闭的围栏块
#
# 当围栏块被打开但从未关闭时（奇数 ```), everything after the opening ``` 必须被视为在围
# 栏内 - 不应在那里执行任何命令。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "executed", "preserved"),
    [
        pytest.param(
            "```\nblock1\n```\n!`echo mid`\n```\n!`echo sneaky`\n",
            "mid",
            "!`echo sneaky`",
            id="odd_fences_protects_trailing_command",
        ),
        pytest.param(
            "```\n!`echo nope`\n",
            None,
            "!`echo nope`",
            id="single_unclosed_fence",
        ),
    ],
)
def test_render_unclosed_fenced_blocks(content, executed, preserved):
    result = render_content_with_commands(content)
    if executed is not None:
        assert executed in result
    assert preserved in result


def test_render_properly_closed_fences():
    content = "```\nblock1\n```\n!`echo between`\n```\nblock2\n```"
    result = render_content_with_commands(content)
    assert "between" in result
    assert "!`echo between`" not in result


# ---------------------------------------------------------------------------
# 渲染：逃生舱口 — \!`cmd` 生成文字文本 !`cmd`
#
# 这使得技能作者可以记录 !`...` 语法本身，或者显示命令示例，而无需在渲染时运行它们。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected_literal", "expected_executed"),
    [
        pytest.param(
            r"\!`echo hello`",
            "!`echo hello`",
            None,
            id="escaped_becomes_literal",
        ),
        pytest.param(
            r"Docs: \!`echo no` Real: !`echo yes`",
            "!`echo no`",
            "yes",
            id="escaped_and_real_coexist",
        ),
    ],
)
def test_render_escaped_commands(content, expected_literal, expected_executed):
    result = render_content_with_commands(content)
    assert expected_literal in result
    if expected_executed is not None:
        assert expected_executed in result


def test_render_escape_inside_fenced_block_untouched():
    r"""\\!`cmd` 在围栏块内完全保持原样。"""
    content = "```\n\\!`echo hi`\n```"
    result = render_content_with_commands(content)
    assert result == content


# ---------------------------------------------------------------------------
# 积分：Skill.render_content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("Plain text", "Plain text", id="no_commands"),
        pytest.param("Out: !`echo hi`", "Out: hi", id="with_command"),
    ],
)
def test_skill_render_content(content, expected):
    assert Skill(name="t", content=content).render_content() == expected


def test_skill_load_and_render(tmp_path: Path):
    skill_md = tmp_path / "test-skill" / "SKILL.md"
    skill_md.parent.mkdir()
    skill_md.write_text("---\nname: test-skill\n---\nBranch: !`echo main`\n")
    skill = Skill.load(skill_md)
    assert skill.render_content() == "Branch: main"
