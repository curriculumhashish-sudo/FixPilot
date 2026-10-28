"""AST 支持的 shell 扫描器的故障安全合约测试。

``scan_shell_command`` 必须永远不无声地承诺 LOW，当它 *拒绝 * 扫描 (嵌套-运行时深度限
制) 或无法信任它解析的内容 (ERROR/
MISSING 与检测依赖的区间相交的节点)。 关于第 2b 阶段 PR 的两项审查结果都是沉默的 LOW
此类路径； 这些测试将更正后的契约固定在单元级别，并确认
``uncertain``到``UNKNOWN``的分析器级别映射。

范围边界（通过代码中的注释反映） ``shell_semantics.py``): 语法错误不执行带有破坏标志
的命令，或者 shell 运行器的 argv 会 inters
ect LOW. 任意非shell文本经常无法解析，并且每出现一个此类错误都会导致整个集合被淹没
UNKNOWNs -- 以下边界测试表明，故意打开的边缘。

样式遵循``test_shell_parser_bypasses.py``； 载荷片段在运行时组装只是为了保持本地扫描
工具安静。
"""

from __future__ import annotations

import json

import pytest

from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.security.defense_in_depth.pattern import PatternSecurityAnalyzer
from openhands.sdk.security.defense_in_depth.shell_semantics import (
    _MAX_NESTING_DEPTH,
    scan_shell_command,
)
from openhands.sdk.security.risk import SecurityRisk


_DETECTOR_ID = "test.detector.id"

_RF = "-" + "rf"
_RM = "r" + "m"
_DEL_SHORT = _RM + " " + _RF + " /"
# 引用分割动词：对于扁平文本正则表达式层不可见，因此下面的分析器级断言隔离了 AST 路径。
#
_DEL_QUOTED = "r" + '"m" ' + _RF + " /"


def make_action(command: str, tool_name: str = "bash") -> ActionEvent:
    """创建一个带有 ``command`` 作为工具参数的最小 ActionEvent。"""
    return ActionEvent(
        thought=[TextContent(text="test")],
        tool_name=tool_name,
        tool_call_id="test",
        tool_call=MessageToolCall(
            id="test",
            name=tool_name,
            arguments=json.dumps({"command": command}),
            origin="completion",
        ),
        llm_response_id="test",
    )


def _double_quoted(source: str) -> str:
    """将 ``source`` 用双引号引起来，POSIX 转义。"""
    escaped = (
        source.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def _nest_in_runners(payload: str, levels: int) -> str:
    """将 ``payload`` 包裹在 ``levels`` 层运行程序脚本操作数中。"""
    command = payload
    for _ in range(levels):
        command = f"bash -c {_double_quoted(command)}"
    return command


def test_dynamic_runner_option_boundary_is_uncertain():
    command = f"bash \"$OPT\" -c '{_DEL_QUOTED}'"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.UNKNOWN
    )


@pytest.mark.parametrize(
    ("shell", "flag"),
    [("bash", "+c"), ("bash", "+xc"), ("dash", "+c"), ("dash", "+xc")],
)
def test_plus_c_runner_script_is_scanned(shell: str, flag: str):
    command = f"{shell} {flag} '{_DEL_QUOTED}'"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is True
    assert result.detector_id == _DETECTOR_ID


@pytest.mark.parametrize(
    "command",
    [
        f"bash 2>/dev/null -c '{_DEL_QUOTED}'",
        f"eval 2>/dev/null '{_DEL_QUOTED}'",
        f"eval 0<<< x '{_DEL_QUOTED}'",
        f"builtin command -p -- eval '{_DEL_QUOTED}'",
        f"bash 2>/dev/null 0<<< '{_DEL_QUOTED}'",
        f"bash 2>/dev/null 00<<< '{_DEL_QUOTED}'",
    ],
)
def test_redirected_executable_source_is_scanned(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is True
    assert result.detector_id == _DETECTOR_ID
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.HIGH
    )


def test_pattern_ast_uses_original_shell_source():
    command = 'echo ＃; r"m" -rf /'

    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.HIGH
    )


@pytest.mark.parametrize(
    "command",
    [
        f"0<<< '{_DEL_QUOTED}' bash",
        f"bash </dev/null <<< '{_DEL_QUOTED}'",
    ],
)
def test_parser_recovered_source_is_scanned(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is True
    assert result.detector_id == _DETECTOR_ID


@pytest.mark.parametrize(
    "command",
    [
        f"bash '0'<<< '{_DEL_QUOTED}'",
        f"bash \"0\"<<< '{_DEL_QUOTED}'",
        f"bash \\0<<< '{_DEL_QUOTED}'",
        f"bash 2>/dev/null 0 <<< '{_DEL_QUOTED}'",
        f"bash 2>/dev/null 00 <<< '{_DEL_QUOTED}'",
        f"bash <<< '{_DEL_QUOTED}' </dev/null",
        f"builtin command -- -p eval '{_DEL_QUOTED}'",
    ],
)
def test_non_executable_source_control(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is False


@pytest.mark.parametrize(
    "command",
    [
        f"bash -oc errexit '{_DEL_QUOTED}'",
        f"dash -oc errexit '{_DEL_QUOTED}'",
        f"bash -Oxc extglob '{_DEL_QUOTED}'",
        f"bash -ooc errexit nounset '{_DEL_QUOTED}'",
        f"bash -oco errexit nounset '{_DEL_QUOTED}'",
        f"bash -cOO extglob nullglob '{_DEL_QUOTED}'",
    ],
)
def test_grouped_runner_option_values_are_uncertain(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True


@pytest.mark.parametrize(
    "option_group",
    ["-co errexit", "-cO extglob"],
)
def test_script_flag_before_value_option_is_scanned(option_group: str):
    command = f"bash {option_group} '{_DEL_QUOTED}'"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is True
    assert result.detector_id == _DETECTOR_ID


@pytest.mark.parametrize(
    "arguments",
    ["--rcfile profile", "--noprofile", "++c"],
)
def test_non_script_options_do_not_select_script_mode(arguments: str):
    command = f"bash {arguments} '{_DEL_QUOTED}'"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is False


@pytest.mark.parametrize(
    "command",
    [
        f"set -- -c '{_DEL_QUOTED}'; bash \"$@\"",
        f"set -- errexit -c '{_DEL_QUOTED}'; bash -o \"$@\"",
        f"ARGS=(-c '{_DEL_QUOTED}'); bash \"${{ARGS[@]}}\"",
        'bash -c -- "$@"',
        'bash -c - "$@"',
        'bash -c -- "${SCRIPTS[@]}"',
    ],
)
def test_multi_argument_runner_expansion_is_uncertain(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.UNKNOWN
    )


@pytest.mark.parametrize("command", ['bash -- "$@"', 'bash - "$@"'])
def test_multi_argument_operand_without_script_flag_is_not_scanned(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is False
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.LOW
    )


def test_multi_argument_command_name_is_uncertain():
    command = f"r{{m,x}} {_RF} /"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.UNKNOWN
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm {-r,-f} /",
        "rm -r {-f,file} /",
        "rm -f {-r,file} /",
        "rm {--recursive,--force} /",
        "rm -* /",
        "rm ?rf /",
        "rm *rf /",
        "rm [--]rf /",
        "rm [^a]rf /",
        "rm [[:punct:]][[:alpha:]][[:alpha:]] /",
        "rm ?r ?f /",
        "rm -f -f? /",
        "rm -r -? /",
        "rm {{-r,-f},file} /",
    ],
)
def test_expanded_rm_flags_are_uncertain(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.UNKNOWN
    )


def test_deep_brace_expansion_is_bounded():
    command = "rm " + "{,-r}{,-f}" * 250 + " /"
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is True


@pytest.mark.parametrize(
    "command",
    [
        "rm *.o",
        "rm build/*.log",
        "rm -- ./build/*.o",
        "rm {file-old,file-new}",
        "rm foo{-r,-f} /",
        "rm {foo-f,-r} /",
        "rm -f foo{,-r} /",
        'rm -f "{-r,-f}"* /',
        "rm -- {-r,-f} /",
    ],
)
def test_expansion_without_destructive_flags_is_low(command: str):
    result = scan_shell_command(command, _DETECTOR_ID)

    assert result.matched is False
    assert result.uncertain is False
    assert PatternSecurityAnalyzer().security_risk(make_action(command)) == (
        SecurityRisk.LOW
    )


class TestDetectorIdentity:
    """扫描仪报告呼叫者拥有的检测器 ID 未更改。"""

    def test_match_reports_callers_detector_id(self):
        result = scan_shell_command(_DEL_SHORT, _DETECTOR_ID)
        assert result.matched is True
        assert result.detector_id == _DETECTOR_ID
        assert result.uncertain is False

    def test_no_match_reports_no_detector_id(self):
        result = scan_shell_command("ls /tmp", _DETECTOR_ID)
        assert result.matched is False
        assert result.detector_id is None
        assert result.uncertain is False


class TestNestingDepthBound:
    """嵌套运行器深度界限是自动防故障的，绝不是静默的 LOW。

    在第2b阶段PR的审查发现：使用脚本操作符``_MAX_NESTING_DEPTH``击中返回了一个无声的
    LOW，给攻击者提供了一个建设性的绕过（将载荷一层更深地包
    裹）。 边界现在表面 ``uncertain``，因此分析器发出 UNKNOWN - 并且 UNKNOWN 在
    ``ConfirmRisky`` 下安全失败。
    """

    def test_depth_bound_hit_is_uncertain_not_low(self):
        # 超出界限的一层：最里面的操作数——良性与否
        # -- 从未被扫描过，因此扫描仪无法为其提供担保。
        command = _nest_in_runners("ls", _MAX_NESTING_DEPTH + 1)
        result = scan_shell_command(command, _DETECTOR_ID)
        assert result.matched is False
        assert result.uncertain is True

    def test_depth_bound_hit_maps_to_unknown(self):
        command = _nest_in_runners("ls", _MAX_NESTING_DEPTH + 1)
        analyzer = PatternSecurityAnalyzer()
        risk = analyzer.security_risk(make_action(command))
        assert risk == SecurityRisk.UNKNOWN

    def test_payload_at_bound_still_matches(self):
        # 精确地在边界处扫描每个级别：最里面的操作数内的破坏性动词仍然必须被解析。
        #
        command = _nest_in_runners(_DEL_QUOTED, _MAX_NESTING_DEPTH)
        result = scan_shell_command(command, _DETECTOR_ID)
        assert result.matched is True
        assert result.detector_id == _DETECTOR_ID

    def test_benign_nesting_within_bound_stays_low(self):
        command = _nest_in_runners("ls", _MAX_NESTING_DEPTH)
        result = scan_shell_command(command, _DETECTOR_ID)
        assert result.matched is False
        assert result.uncertain is False
        analyzer = PatternSecurityAnalyzer()
        assert analyzer.security_risk(make_action(command)) == SecurityRisk.LOW


class TestParseErrorFailSafe:
    """依赖跨度上的 ERROR/MISSING 节点表面上是不确定的。

    在第2b阶段PR的审查发现：``ShellCommand.has_error``通过AST视图接入，但从未咨询过，
    因此一个断句错误可能会悄无声息地截断检测读取的非常
    短的词（动词、跑步者argv），并且仍然保LOW证。 与带有破坏性标志形状或 shell 运行程
    序的 argv 的命令相交的错误现在可以安全故障处理； 具体的比赛仍
    然能战胜不确定性。
    """

    def test_destructive_shape_with_parse_error_is_uncertain(self):
        # 未闭合的引号位于命令节点内：当存在破坏性标志形状时，无法信任已解析的动词。
        #
        command = "foo " + _RF + ' / "unclosed'
        result = scan_shell_command(command, _DETECTOR_ID)
        assert result.matched is False
        assert result.uncertain is True

    def test_destructive_shape_with_parse_error_maps_to_unknown(self):
        command = "foo " + _RF + ' / "unclosed'
        analyzer = PatternSecurityAnalyzer()
        risk = analyzer.security_risk(make_action(command))
        assert risk == SecurityRisk.UNKNOWN

    def test_broken_runner_argv_is_uncertain(self):
        # 运行程序的脚本操作数是一个未闭合的字符串（MISSING 结束引号）：其 argv span 不
        # 可信。
        #
        result = scan_shell_command('bash -c "', _DETECTOR_ID)
        assert result.matched is False
        assert result.uncertain is True

    def test_match_wins_over_adjacent_parse_error(self):
        # 损坏语法旁边的可解析破坏性命令必须仍然匹配：故障安全仅替换静默丢失路径。
        #
        command = "'" + _RM + "' " + _RF + " / oops("
        result = scan_shell_command(command, _DETECTOR_ID)
        assert result.matched is True
        assert result.detector_id == _DETECTOR_ID

    def test_benign_broken_command_stays_low(self):
        # 文档化范围边界：此 ERROR 节点静止 OUTSIDE 命令节点（tree-sitter通过分裂恢复）
        # ，并且命令不携带破坏标志形状或运行者argv。 任意非shell文本总是这样解析失败；
        # 它会淹没整个集合 UNKNOWNs.
        #
        result = scan_shell_command('echo "unclosed', _DETECTOR_ID)
        assert result.matched is False
        assert result.uncertain is False
        analyzer = PatternSecurityAnalyzer()
        risk = analyzer.security_risk(make_action('echo "unclosed'))
        assert risk == SecurityRisk.LOW
