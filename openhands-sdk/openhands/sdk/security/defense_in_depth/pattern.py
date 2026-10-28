"""通过将内容与已知威胁签名进行匹配来对智能体操作进行分类。

当智能体即将运行 ``rm -rf /`` 时，你想抓住它。 当智能体在运行``ls /tmp``时仅仅*思考*
``rm -rf /``时，你不会。 该模块通过两个扫描语料
库来解决这个问题。

- **可执行语料库**（tool_name、tool_call参数）：扫描 shell 破坏性、代码执行和网络执行
模式。
- **所有字段语料库**（包含可执行代码 + 思考/推理/总结）：扫描以识别任何危险的注入和社
会工程模式。

每个模式都带有一个稳定的探测器 ID，用于遥测准备。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field, PrivateAttr

from openhands.sdk.event import ActionEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.defense_in_depth.shell_semantics import (
    scan_shell_command,
)
from openhands.sdk.security.defense_in_depth.utils import (
    _extract_content,
    _extract_exec_content,
    _extract_exec_segments,
    _normalize,
)
from openhands.sdk.security.risk import SecurityRisk


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 稳定的检测器 ID——在没有文档的情况下不要在版本之间进行更改。
# 格式：DET_{CORPUS}_{FAMILY}_{SPECIFIC}
# ---------------------------------------------------------------------------

DET_EXEC_DESTRUCT_RM_RF = "exec.destruct.rm_rf"
DET_EXEC_DESTRUCT_SUDO_RM = "exec.destruct.sudo_rm"
DET_EXEC_DESTRUCT_MKFS = "exec.destruct.mkfs"
DET_EXEC_DESTRUCT_DD = "exec.destruct.dd_raw_disk"
DET_EXEC_CODE_EVAL = "exec.code.eval_call"
DET_EXEC_CODE_EXEC = "exec.code.exec_call"
DET_EXEC_CODE_OS_SYSTEM = "exec.code.os_system"
DET_EXEC_CODE_SUBPROCESS = "exec.code.subprocess"
DET_EXEC_NET_CURL_EXEC = "exec.net.curl_pipe_exec"
DET_EXEC_NET_WGET_EXEC = "exec.net.wget_pipe_exec"
DET_EXEC_NET_CURL = "exec.net.curl"
DET_EXEC_NET_WGET = "exec.net.wget"
DET_INJECT_OVERRIDE = "inject.override"
DET_INJECT_MODE_SWITCH = "inject.mode_switch"
DET_INJECT_IDENTITY = "inject.identity"

# ---------------------------------------------------------------------------
# 模式定义
#
# 格式：(regex_pattern、描述、detector_id)
#
# 图案设计限制：
# - 没有无限的 .* 或 .+ 围绕交替（灾难性回溯）
# - 风险跨度有界 ({0,N}) 以防止 ReDoS
# - \s* 和 \w+ 在非交替位置是可接受的
# - \b-锚定以避免子字符串匹配
# - IGNORECASE 编译于
# ---------------------------------------------------------------------------

DEFAULT_HIGH_PATTERNS: list[tuple[str, str, str]] = [
    # 破坏性文件系统操作
    (
        r"\brm\s+(?:-[frR]{2,}|-[rR]\s+-f|-f\s+-[rR]"
        r"|--recursive\s+--force|--force\s+--recursive)\b",
        "Recursive force-delete (rm -rf variants)",
        DET_EXEC_DESTRUCT_RM_RF,
    ),
    (r"\bsudo\s+rm\b", "Privileged file deletion", DET_EXEC_DESTRUCT_SUDO_RM),
    (r"\bmkfs\.\w+", "Filesystem format command", DET_EXEC_DESTRUCT_MKFS),
    (r"\bdd\b.{0,100}of=/dev/", "Raw disk write", DET_EXEC_DESTRUCT_DD),
    # 通过动态解释器调用代码
    (r"\beval\s*\(", "Dynamic code evaluation", DET_EXEC_CODE_EVAL),
    (r"\bexec\s*\(", "Dynamic code execution", DET_EXEC_CODE_EXEC),
    (r"\bos\.system\s*\(", "OS-level command execution", DET_EXEC_CODE_OS_SYSTEM),
    (
        r"\bsubprocess\.(?:call|run|Popen|check_output|check_call)\s*\(",
        "Subprocess invocation",
        DET_EXEC_CODE_SUBPROCESS,
    ),
    # 下载并运行
    (
        r"\bcurl\b[^|]{0,200}\|\s*(?:ba)?sh\b",
        "Download and run (curl | sh)",
        DET_EXEC_NET_CURL_EXEC,
    ),
    (
        r"\bwget\b[^|]{0,200}\|\s*(?:ba)?sh\b",
        "Download and run (wget | sh)",
        DET_EXEC_NET_WGET_EXEC,
    ),
]

DEFAULT_MEDIUM_PATTERNS: list[tuple[str, str, str]] = [
    # 无需调用管道的网络访问
    (r"\bcurl\b.{0,100}https?://", "HTTP request via curl", DET_EXEC_NET_CURL),
    (r"\bwget\b.{0,100}https?://", "Download via wget", DET_EXEC_NET_WGET),
]

# 注入模式：针对全部字段进行扫描（调用 + 推理）。 这些是针对指令跟踪的文本攻击，而不是针
# 对操作系统。
#

DEFAULT_INJECTION_HIGH_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?"
        r"(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?|directives?)\b",
        "Instruction override attempt",
        DET_INJECT_OVERRIDE,
    ),
]

DEFAULT_INJECTION_MEDIUM_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"\byou\s+are\s+now\s+(?:in\s+)?(?:\w+\s+)?mode\b",
        "Mode switching attempt",
        DET_INJECT_MODE_SWITCH,
    ),
    (
        r"\bpretend\s+(?:you\s+are|to\s+be)\s+(?:a\s+)?different\b",
        "Identity manipulation",
        DET_INJECT_IDENTITY,
    ),
]


# ---------------------------------------------------------------------------
# PatternSecurityAnalyzer
# ---------------------------------------------------------------------------


class PatternSecurityAnalyzer(SecurityAnalyzerBase):
    """通过确定性签名扫描捕获危险的智能体操作。

    当您希望在操作边界进行快速、本地、无网络威胁检测时，请使用此选项。 它返回
    ``SecurityRisk.HIGH``、``MEDIUM`` 或 ``LOW``。
    当shell扫描无法解析相关破坏性结构时，返回``UNKNOWN``。 将其与 ``ConfirmRisky`` 配
    对来决定要确认的内容。

    关键的设计选择：外壳破坏性模式仅扫描智能体 will *execute* (工具参数)，而不是它 *
    thought about* (reasoning text).
     注入模式会扫描一切，因为“忽略所有先前的指令”无论出现在哪里都是危险的。

    规范化始终处于开启状态——不可见字符和全角替换在匹配之前被折叠。

    示例：:

        from openhands.sdk.security import PatternSecurityAnalyzer, ConfirmRisky

        analyzer = PatternSecurityAnalyzer()
        policy = ConfirmRisky(threshold=SecurityRisk.MEDIUM)
    """

    high_patterns: list[tuple[str, str, str]] = Field(
        default_factory=lambda: list(DEFAULT_HIGH_PATTERNS),
        description="HIGH patterns scanned against executable fields only",
    )
    medium_patterns: list[tuple[str, str, str]] = Field(
        default_factory=lambda: list(DEFAULT_MEDIUM_PATTERNS),
        description="MEDIUM patterns scanned against executable fields only",
    )
    injection_high_patterns: list[tuple[str, str, str]] = Field(
        default_factory=lambda: list(DEFAULT_INJECTION_HIGH_PATTERNS),
        description="HIGH patterns scanned against all fields",
    )
    injection_medium_patterns: list[tuple[str, str, str]] = Field(
        default_factory=lambda: list(DEFAULT_INJECTION_MEDIUM_PATTERNS),
        description="MEDIUM patterns scanned against all fields",
    )

    _compiled_high: list[tuple[re.Pattern[str], str, str]] = PrivateAttr(
        default_factory=list,
    )
    _compiled_medium: list[tuple[re.Pattern[str], str, str]] = PrivateAttr(
        default_factory=list,
    )
    _compiled_injection_high: list[tuple[re.Pattern[str], str, str]] = PrivateAttr(
        default_factory=list,
    )
    _compiled_injection_medium: list[tuple[re.Pattern[str], str, str]] = PrivateAttr(
        default_factory=list,
    )

    def model_post_init(self, __context: Any) -> None:
        """模型初始化后编译正则表达式模式。"""
        self._compiled_high = [
            (re.compile(p, re.IGNORECASE), d, det_id)
            for p, d, det_id in self.high_patterns
        ]
        self._compiled_medium = [
            (re.compile(p, re.IGNORECASE), d, det_id)
            for p, d, det_id in self.medium_patterns
        ]
        self._compiled_injection_high = [
            (re.compile(p, re.IGNORECASE), d, det_id)
            for p, d, det_id in self.injection_high_patterns
        ]
        self._compiled_injection_medium = [
            (re.compile(p, re.IGNORECASE), d, det_id)
            for p, d, det_id in self.injection_medium_patterns
        ]

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        """通过两个语料库模式匹配评估安全风险。"""
        exec_content = _normalize(_extract_exec_content(action))
        all_content = _normalize(_extract_content(action))

        if not exec_content and not all_content:
            return SecurityRisk.LOW

        # HIGH：仅适用于可执行字段的模式
        for pattern, _desc, det_id in self._compiled_high:
            if pattern.search(exec_content):
                logger.debug("Pattern matched: %s -> HIGH", det_id)
                return SecurityRisk.HIGH

        # HIGH：所有字段的注入模式
        for pattern, _desc, det_id in self._compiled_injection_high:
            if pattern.search(all_content):
                logger.debug("Pattern matched: %s -> HIGH", det_id)
                return SecurityRisk.HIGH

        # HIGH: AST 可执行字段解析，捕获引用，
        # 单词边界锚点看不到的路径限定和嵌套命令名称。
        #
        shell_scans = (
            scan_shell_command(segment, DET_EXEC_DESTRUCT_RM_RF)
            for segment in _extract_exec_segments(action)
        )
        shell_scan_uncertain = False
        for shell_scan in shell_scans:
            if shell_scan.matched:
                logger.debug("Shell AST matched: %s -> HIGH", shell_scan.detector_id)
                return SecurityRisk.HIGH
            shell_scan_uncertain = shell_scan_uncertain or shell_scan.uncertain

        # MEDIUM：仅适用于可执行字段的模式
        for pattern, _desc, det_id in self._compiled_medium:
            if pattern.search(exec_content):
                logger.debug("Pattern matched: %s -> MEDIUM", det_id)
                return SecurityRisk.MEDIUM

        # MEDIUM：所有字段的注入模式
        for pattern, _desc, det_id in self._compiled_injection_medium:
            if pattern.search(all_content):
                logger.debug("Pattern matched: %s -> MEDIUM", det_id)
                return SecurityRisk.MEDIUM

        # 扫描无法解析的动词上的破坏性标志形状：UNKNOWN 而不是 False LOW。 默认情况下，
        # ConfirmRisky 提示词代表 UNKNOWN。 仅仅无法解析的文本仍保留在LOW中。
        #
        if shell_scan_uncertain:
            logger.debug("Shell AST uncertain (unresolvable verb) -> UNKNOWN")
            return SecurityRisk.UNKNOWN

        return SecurityRisk.LOW
