import pytest

from openhands.tools.terminal.utils.command import (
    escape_bash_special_chars,
    needs_heredoc_completion_boundary,
    split_bash_commands,
)


def test_split_commands_util():
    cmds = [
        "ls -l",
        'echo -e "hello\nworld"',
        """
echo -e "hello it\\'s me"
""".strip(),
        """
echo \\
    -e 'hello' \\
    -v
""".strip(),
        """
echo -e 'hello\\nworld\\nare\\nyou\\nthere?'
""".strip(),
        """
echo -e 'hello
world
are
you\\n
there?'
""".strip(),
        """
echo -e 'hello
world "
'
""".strip(),
        """
mkdir -p _modules && \
for month in {01..04}; do
    for day in {01..05}; do
        touch "_modules/2024-${month}-${day}-sample.md"
    done
done
""".strip(),
        """
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: busybox-sleep
spec:
  containers:
  - name: busybox
    image: busybox:1.28
    args:
    - sleep
    - "1000000"
EOF
""".strip(),
    ]
    joined_cmds = "\n".join(cmds)
    split_cmds = split_bash_commands(joined_cmds)
    for i in range(len(cmds)):
        assert split_cmds[i].strip() == cmds[i].strip(), (
            f"At index {i}: {split_cmds[i]} != {cmds[i]}."
        )


@pytest.mark.parametrize(
    "input_command, expected_output",
    [
        ("ls -l", ["ls -l"]),
        ("echo 'Hello, world!'", ["echo 'Hello, world!'"]),
        ("cd /tmp && touch test.txt", ["cd /tmp && touch test.txt"]),
        ("test -f missing || echo absent", ["test -f missing || echo absent"]),
        ("sleep 0 & wait", ["sleep 0 & wait"]),
        ("echo -e 'line1\\nline2\\nline3'", ["echo -e 'line1\\nline2\\nline3'"]),
        (
            "grep 'pattern' file.txt | sort | uniq",
            ["grep 'pattern' file.txt | sort | uniq"],
        ),
        ("for i in {1..5}; do echo $i; done", ["for i in {1..5}; do echo $i; done"]),
        (
            "echo 'Single quotes don\\'t escape'",
            ["echo 'Single quotes don\\'t escape'"],
        ),
        (
            'echo "Double quotes \\"do\\" escape"',
            ['echo "Double quotes \\"do\\" escape"'],
        ),
    ],
)
def test_single_commands(input_command, expected_output):
    assert split_bash_commands(input_command) == expected_output


@pytest.mark.parametrize(
    "input_commands",
    [
        "cat <<EOF\nmultiline\ntext\nEOF\necho done",
        "cat <<'EOF'\n$VALUE\nEOF\nprintf done",
        "cat <<-EOF\n\tindented\n\tEOF\nprintf done",
        "cat <<EOF | sed 's/text/replaced/'\ntext\nEOF\nprintf done",
        "value=$(cat <<EOF\ntext\nEOF\n) && printf '%s' \"$value\"",
        (
            "printf start; python - <<'PY'\n"
            "print('first')\n"
            "PY\n"
            "printf middle; python - <<'PY'\n"
            "print('second')\n"
            "PY\n"
            "printf done"
        ),
    ],
)
def test_heredoc_script_is_not_split(input_commands):
    assert split_bash_commands(input_commands) == [input_commands]


@pytest.mark.parametrize(
    "command",
    [
        "cat <<'EOF'\nbody\nEOF\nsleep 1; echo done",
        "cat <<A <<B\na\nA\nb\nB\necho done",
        'cat <<E"OF"\nbody\nEOF\necho done',
        "cat <<EOF &\nbody\nEOF\nwait",
    ],
)
def test_heredoc_scripts_need_completion_boundary(command):
    assert needs_heredoc_completion_boundary(command)


def test_single_heredoc_does_not_need_completion_boundary():
    command = "cat <<'EOF'\nbody\nEOF\n"

    assert not needs_heredoc_completion_boundary(command)


def test_incomplete_heredoc_does_not_need_completion_boundary():
    assert not needs_heredoc_completion_boundary("cat <<EOF\nbody")


def test_completion_boundary_is_platform_independent():
    """防护不能依赖于 PATH 上的 `bash` 可执行文件。

    在 Windows 上，树管理员会报告这些表单的解析错误，因此决策仅根据树做出，并且必须在
    每个平台上匹配。
    """
    assert needs_heredoc_completion_boundary(
        "cat <<'EOF'\nbody\nEOF\nsleep 1; echo done"
    )
    assert needs_heredoc_completion_boundary("cat <<A <<B\na\nA\nb\nB\necho done")
    assert needs_heredoc_completion_boundary('cat <<E"OF"\nbody\nEOF\necho done')
    assert needs_heredoc_completion_boundary("cat <<EOF &\nbody\nEOF\nwait")
    assert needs_heredoc_completion_boundary(
        "cat <<-EOF\n\tindented\n\tEOF\nprintf done"
    )
    assert not needs_heredoc_completion_boundary("cat <<EOF\nbody")
    assert not needs_heredoc_completion_boundary("cat <<EOF\nbody\nEOF\n")
    assert not needs_heredoc_completion_boundary("cat <<'EOF'\nbody\nEOF\n")


@pytest.mark.parametrize(
    "input_commands, expected_output",
    [
        ("echo first\necho second", ["echo first", "echo second"]),
        ("cat <<< text\necho second", ["cat <<< text", "echo second"]),
        (
            "cat <<EOF\ntext\nEOF\necho second\necho third",
            ["cat <<EOF\ntext\nEOF\necho second", "echo third"],
        ),
        (
            "cat <<EOF\nunterminated\necho second",
            ["cat <<EOF\nunterminated\necho second"],
        ),
        # 在复合语句或替换中嵌套的heredoc * *，不会结束语句：tree-sitter 会忽略 token (
        # `fi`, `)`)，因此，接下来的换行符仍需分隔。
        #
        (
            "if true; then\n  cat <<EOF\nx\nEOF\nfi\necho after",
            ["if true; then\n  cat <<EOF\nx\nEOF\nfi", "echo after"],
        ),
        (
            "x=$(cat <<EOF\nhi\nEOF\n)\nrm -rf /tmp/x",
            ["x=$(cat <<EOF\nhi\nEOF\n)", "rm -rf /tmp/x"],
        ),
        (
            "( cat <<EOF\nx\nEOF\n)\necho after",
            ["( cat <<EOF\nx\nEOF\n)", "echo after"],
        ),
        (
            "for i in 1 2; do cat <<EOF\nx\nEOF\ndone\necho after",
            ["for i in 1 2; do cat <<EOF\nx\nEOF\ndone", "echo after"],
        ),
    ],
)
def test_non_heredoc_newlines_still_split(input_commands, expected_output):
    assert split_bash_commands(input_commands) == expected_output


def test_backslash_continuation():
    input_commands = """
echo "This is a long \
command that spans \
multiple lines"
echo "Next command"
"""
    expected_output = [
        'echo "This is a long command that spans multiple lines"',
        'echo "Next command"',
    ]
    assert split_bash_commands(input_commands) == expected_output


def test_comments():
    input_commands = """
echo "Hello" # This is a comment
# This is another comment
ls -l
"""
    expected_output = [
        'echo "Hello" # This is a comment\n# This is another comment',
        "ls -l",
    ]
    assert split_bash_commands(input_commands) == expected_output


def test_complex_quoting():
    input_commands = """
echo "This is a \\"quoted\\" string"
echo 'This is a '\''single-quoted'\'' string'
echo "Mixed 'quotes' in \\"double quotes\\""
"""
    expected_output = [
        'echo "This is a \\"quoted\\" string"',
        "echo 'This is a '''single-quoted''' string'",
        'echo "Mixed \'quotes\' in \\"double quotes\\""',
    ]
    assert split_bash_commands(input_commands) == expected_output


def test_invalid_syntax():
    invalid_inputs = [
        'echo "Unclosed quote',
        "echo 'Unclosed quote",
        "cat <<EOF\nUnclosed heredoc",
    ]
    for input_command in invalid_inputs:
        # 它将回退以返回原始输入
        assert split_bash_commands(input_command) == [input_command]


def test_unclosed_backtick():
    # 此测试重现了 issue #7391。该问题发生在解析一个未闭合的反引号命令时，导致 TypeError
    # : ParsingError.__init__()缺少2个必需的参数：'s' 和 'position'
    #
    command = "echo `unclosed backtick"

    # 不应提高 TypeError
    try:
        result = split_bash_commands(command)
        # 如果我们到达这里，则错误已得到正确处理
        assert result == [command]
    except TypeError as e:
        # 这就是我们试图修复的错误
        raise e

    # 还可以使用问题中的原始命令进行测试（使用占位符 org/repo）
    curl_command = (
        'curl -X POST "https://api.github.com/repos/example-org/example-repo/pulls" \\ '
        '-H "Authorization: Bearer $GITHUB_TOKEN" \\ '
        '-H "Accept: application/vnd.github.v3+json" \\ '
        '-d \'{ "title": "XXX", "head": "XXX", "base": "main", "draft": false }\' '
        "`echo unclosed"
    )

    try:
        result = split_bash_commands(curl_command)
        assert result == [curl_command]
    except TypeError as e:
        raise e


def test_over_escaped_command():
    # 此测试重现问题 #8369 示例 1 解析带有过度转义引号的命令时会出现此问题
    #
    over_escaped_command = (
        r"# 0. Setup directory\\nrm -rf /workspace/repro_sphinx_bug && "
        r"mkdir -p /workspace/repro_sphinx_bug && cd /workspace/repro_sphinx_bug\\n\\n"
        r"# 1. Run sphinx-quickstart\\nsphinx-quickstart --no-sep --project myproject "
        r"--author me -v 0.1.0 --release 0.1.0 --language en . -q\\n\\n"
        r"# 2. Create index.rst\\necho -e \'Welcome\\\\\\\\n=======\\\\\\\\n\\\\\\\\n"
        r".. toctree::\\\\n   :maxdepth: 2\\\\\\\\n\\\\\\\\n   "
        r"mypackage_file\\\\\\\\n\' > index.rst"
    )

    # 不应引发任何异常
    try:
        result = split_bash_commands(over_escaped_command)
        # 如果解析失败，应该返回原始命令
        assert result == [over_escaped_command]
    except Exception as e:
        # 这就是我们试图修复的错误
        pytest.fail(f"split_bash_commands raised {type(e).__name__} unexpectedly: {e}")


@pytest.fixture
def sample_commands():
    return [
        "ls -l",
        'echo "Hello, world!"',
        "cd /tmp && touch test.txt",
        'echo -e "line1\\nline2\\nline3"',
        'grep "pattern" file.txt | sort | uniq',
        "for i in {1..5}; do echo $i; done",
        "cat <<EOF\nmultiline\ntext\nEOF",
        'echo "Escaped \\"quotes\\""',
        "echo 'Single quotes don\\'t escape'",
        'echo "Command with a trailing backslash \\\n  and continuation"',
    ]


def test_split_single_commands(sample_commands):
    for cmd in sample_commands:
        result = split_bash_commands(cmd)
        assert len(result) == 1, f"Expected single command, got: {result}"


def test_split_commands_with_heredoc():
    input_commands = """
cat <<EOF
multiline
text
EOF
echo "Done"
"""
    assert split_bash_commands(input_commands) == [input_commands.strip()]


def test_split_commands_with_backslash_continuation():
    input_commands = """
echo "This is a long \
command that spans \
multiple lines"
echo "Next command"
"""
    expected_output = [
        'echo "This is a long command that spans multiple lines"',
        'echo "Next command"',
    ]
    result = split_bash_commands(input_commands)
    assert result == expected_output, f"Expected {expected_output}, got {result}"


def test_split_commands_with_empty_lines():
    input_commands = """
ls -l

echo "Hello"

cd /tmp
"""
    expected_output = ["ls -l", 'echo "Hello"', "cd /tmp"]
    result = split_bash_commands(input_commands)
    assert result == expected_output, f"Expected {expected_output}, got {result}"


def test_split_commands_with_comments():
    input_commands = """
echo "Hello" # This is a comment
# This is another comment
ls -l
"""
    expected_output = [
        'echo "Hello" # This is a comment\n# This is another comment',
        "ls -l",
    ]
    result = split_bash_commands(input_commands)
    assert result == expected_output, f"Expected {expected_output}, got {result}"


def test_split_commands_with_complex_quoting():
    input_commands = """
echo "This is a \\"quoted\\" string"
echo "Mixed 'quotes' in \\"double quotes\\""
"""
    # echo 'This is a '\''single-quoted'\'' string'

    expected_output = [
        'echo "This is a \\"quoted\\" string"',
        'echo "Mixed \'quotes\' in \\"double quotes\\""',
    ]
    # "echo '这是一个'\\''单引号'\\''字符串'",
    result = split_bash_commands(input_commands)
    assert result == expected_output, f"Expected {expected_output}, got {result}"


def test_split_commands_with_invalid_input():
    invalid_inputs = [
        'echo "Unclosed quote',
        "echo 'Unclosed quote",
        "cat <<EOF\nUnclosed heredoc",
    ]
    for input_command in invalid_inputs:
        # 它将回退以返回原始输入
        assert split_bash_commands(input_command) == [input_command]


def test_escape_bash_special_chars():
    test_cases = [
        # 基本情况 - 使用原始字符串 (r'') 以避免 Python 转义序列警告
        ("echo test \\; ls", "echo test \\\\; ls"),
        ("grep pattern \\| sort", "grep pattern \\\\| sort"),
        ("cmd1 \\&\\& cmd2", "cmd1 \\\\&\\\\& cmd2"),
        ("cat file \\> output.txt", "cat file \\\\> output.txt"),
        ("cat \\< input.txt", "cat \\\\< input.txt"),
        # 引用的字符串应保持不变
        ('echo "test \\; unchanged"', 'echo "test \\; unchanged"'),
        ("echo 'test \\| unchanged'", "echo 'test \\| unchanged'"),
        # 混合引用和未引用
        (
            'echo "quoted \\;" \\; "more" \\| grep',
            'echo "quoted \\;" \\\\; "more" \\\\| grep',
        ),
        # 连续多次逃脱
        ("cmd1 \\;\\|\\& cmd2", "cmd1 \\\\;\\\\|\\\\& cmd2"),
        # 带有其他反斜杠的命令
        ("echo test\\ntest", "echo test\\ntest"),
        ('echo "test\\ntest"', 'echo "test\\ntest"'),
        # 边缘情况
        ("", ""),  # 空字符串
        ("\\\\", "\\\\"),  # 双反斜杠
        ('\\"', '\\"'),  # 转义报价
    ]

    for input_cmd, expected in test_cases:
        result = escape_bash_special_chars(input_cmd)
        assert result == expected, (
            f'Failed on input "{input_cmd}"\nExpected: "{expected}"\nGot: "{result}"'
        )


def test_escape_bash_special_chars_with_invalid_syntax():
    invalid_inputs = [
        'echo "unclosed quote',
        "echo 'unclosed quote",
        "cat <<EOF\nunclosed heredoc",
    ]
    for input_cmd in invalid_inputs:
        # 解析失败时应返回原始输入
        result = escape_bash_special_chars(input_cmd)
        assert result == input_cmd, f"Failed to handle invalid input: {input_cmd}"


def test_escape_bash_special_chars_with_heredoc():
    input_cmd = r"""cat <<EOF
line1 \; not escaped
line2 \| not escaped
EOF"""
    # Heredoc 内容不应被转义
    expected = input_cmd
    result = escape_bash_special_chars(input_cmd)
    assert result == expected, (
        f"Failed to handle heredoc correctly\nExpected: {expected}\nGot: {result}"
    )


def test_escape_bash_special_chars_with_parameter_expansion():
    test_cases = [
        # 应保留参数扩展
        ("echo $HOME", "echo $HOME"),
        ("echo ${HOME}", "echo ${HOME}"),
        ("echo ${HOME:-default}", "echo ${HOME:-default}"),
        # 与特殊字符混合
        ("echo $HOME \\; ls", "echo $HOME \\\\; ls"),
        ("echo ${PATH} \\| grep bin", "echo ${PATH} \\\\| grep bin"),
        # 引用参数扩展
        ('echo "$HOME"', 'echo "$HOME"'),
        ('echo "${HOME}"', 'echo "${HOME}"'),
        # 复杂的参数扩展
        ("echo ${var:=default} \\; ls", "echo ${var:=default} \\\\; ls"),
        ("echo ${!prefix*} \\| sort", "echo ${!prefix*} \\\\| sort"),
    ]

    for input_cmd, expected in test_cases:
        result = escape_bash_special_chars(input_cmd)
        assert result == expected, (
            f'Failed on input "{input_cmd}"\nExpected: "{expected}"\nGot: "{result}"'
        )


def test_escape_bash_special_chars_with_command_substitution():
    test_cases = [
        # 基本命令替换
        ("echo $(pwd)", "echo $(pwd)"),
        ("echo `pwd`", "echo `pwd`"),
        # 与特殊字符混合
        ("echo $(pwd) \\; ls", "echo $(pwd) \\\\; ls"),
        ("echo `pwd` \\| grep home", "echo `pwd` \\\\| grep home"),
        # 嵌套命令替换
        ("echo $(echo `pwd`)", "echo $(echo `pwd`)"),
        # 复杂的命令替换
        ('echo $(find . -name "*.txt" \\; ls)', 'echo $(find . -name "*.txt" \\; ls)'),
        # 与引号混合
        ('echo "$(pwd)"', 'echo "$(pwd)"'),
        ('echo "`pwd`"', 'echo "`pwd`"'),
    ]

    for input_cmd, expected in test_cases:
        result = escape_bash_special_chars(input_cmd)
        assert result == expected, (
            f'Failed on input "{input_cmd}"\nExpected: "{expected}"\nGot: "{result}"'
        )


def test_escape_bash_special_chars_mixed_nodes():
    test_cases = [
        # 参数扩展和命令替换的混合
        ("echo $HOME/$(pwd)", "echo $HOME/$(pwd)"),
        # 与特殊字符混合
        ("echo $HOME/$(pwd) \\; ls", "echo $HOME/$(pwd) \\\\; ls"),
        # 复杂的混合情况
        (
            'echo "${HOME}/$(basename `pwd`) \\; next"',
            'echo "${HOME}/$(basename `pwd`) \\; next"',
        ),
        (
            "VAR=${HOME} \\; echo $(pwd)",
            "VAR=${HOME} \\\\; echo $(pwd)",
        ),
        # 现实世界的例子
        (
            'find . -name "*.txt" -exec grep "${PATTERN:-default}" {} \\;',
            'find . -name "*.txt" -exec grep "${PATTERN:-default}" {} \\\\;',
        ),
        (
            'echo "Current path: ${PWD}/$(basename `pwd`)" \\| grep home',
            'echo "Current path: ${PWD}/$(basename `pwd`)" \\\\| grep home',
        ),
    ]

    for input_cmd, expected in test_cases:
        result = escape_bash_special_chars(input_cmd)
        assert result == expected, (
            f'Failed on input "{input_cmd}"\nExpected: "{expected}"\nGot: "{result}"'
        )


def test_escape_bash_special_chars_with_chained_commands():
    test_cases = [
        # 基本的链式命令
        ("ls && pwd", "ls && pwd"),
        ('echo "hello" && ls', 'echo "hello" && ls'),
        # 带有特殊字符的链接命令
        ("ls \\; pwd && echo test", "ls \\\\; pwd && echo test"),
        ("echo test && grep pattern \\| sort", "echo test && grep pattern \\\\| sort"),
        # 复杂的连锁案件
        ("echo ${HOME} && ls \\; pwd", "echo ${HOME} && ls \\\\; pwd"),
        (
            'echo "$(pwd)" && cat file \\> out.txt',
            'echo "$(pwd)" && cat file \\\\> out.txt',
        ),
        # 多链
        ("cmd1 && cmd2 && cmd3", "cmd1 && cmd2 && cmd3"),
        (
            "cmd1 \\; ls && cmd2 \\| grep && cmd3",
            "cmd1 \\\\; ls && cmd2 \\\\| grep && cmd3",
        ),
    ]

    for input_cmd, expected in test_cases:
        result = escape_bash_special_chars(input_cmd)
        assert result == expected, (
            f'Failed on input "{input_cmd}"\nExpected: "{expected}"\nGot: "{result}"'
        )
