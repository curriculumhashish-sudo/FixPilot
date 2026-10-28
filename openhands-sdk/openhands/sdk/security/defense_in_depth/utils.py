"""行动边界安全分析的提取和标准化。

在智能体操作被分类为安全或危险之前，需要发生两件事：必须从 ActionEvent 中提取正确的内
容（提取），并且必须消除隐藏危险命令的编码技巧（正常化）。

提取控制攻击面。 未提取的字段对于每个下游层都是不可见的。 维护两个语料库：*可执行语料
库*（智能体将做什么）和*文本语料库*（它想到什么）。 外壳破坏模式只看到第一个；
注射模式两者兼而有之。

规范化会折叠不可见字符、控制代码和全角替换，以便 ``r\\u200bm`` 匹配 ``rm`` 且
在测试任何模式之前，``\\uff52\\uff4d`` 与 ``rm`` 匹配。

这些是内部助手（以下划线前缀，不重新导出）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from openhands.sdk.event import ActionEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 常数
# ---------------------------------------------------------------------------

# 在标准化和模式匹配之前从 ActionEvent 中提取的最大字符数。 限制正则​​表达式运行时和内存
# ，但超出此限制的内容对分析器不可见。
#
_EXTRACT_HARD_CAP = 30_000


# ---------------------------------------------------------------------------
# 提取：仅限白名单字段
# ---------------------------------------------------------------------------


class _BoundedSegments:
    """具有连接长度上限的仅附加段缓冲区。

    跟踪最终 ``" ".join(segments)`` 字符串的长度，并默默地删除或截断超出 ``cap`` 的附
    加内容。 每个
    ``add()`` 调用为连接输出中该段之前的空格分隔符收取一个字符（第一个除外），因此
    即使产生大量短片段，也必须满足 ``len(" ".join(self.segments)) <= cap``；否则，含
    单字符叶节点的 JSON 对象会因分隔符而扩
    大拼接后的长度。
    """

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.segments: list[str] = []
        self._total = 0

    def add(self, text: str) -> None:
        """追加文本，截断剩余预算； 如果已满则跳过。"""
        separator_len = 1 if self.segments else 0
        remaining = self.cap - self._total - separator_len
        if remaining <= 0:
            return
        if len(text) > remaining:
            text = text[:remaining]
        self.segments.append(text)
        self._total += len(text) + separator_len


def _walk_json_strings(obj: Any) -> list[str]:
    """从已解析的 JSON 结构中递归收集叶字符串。

    走到树叶处并将每个树叶作为单独的路段返回，可以保留场边界，以便进行路段感知的铁路
    评估。

    RecursionError 被不捕获——它传播到 _extract_exec_segments()，后者又扫描原始参数字
    符串。 返回 [] 会默默地删除所有叶子，
    为深度嵌套的载荷创建一条 False 负路径。
    """
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        parts: list[str] = []
        for v in obj.values():
            parts.extend(_walk_json_strings(v))
        return parts
    if isinstance(obj, list):
        parts = []
        for item in obj:
            parts.extend(_walk_json_strings(item))
        return parts
    return []


def _extract_exec_segments(action: ActionEvent) -> list[str]:
    """从描述智能体将 * 执行 * 操作的字段中提取片段。

    仅可执行字段：tool_call.arguments（JSON叶字符串）、tool_name、tool_call.name。
    Shell/权限/执行模式和策略轨道专
    门扫描该语料库。

    首先提取参数，因为它是间接提示词注入载荷的主要攻击面。 将其放在 tool_name 和
    tool_call.name 之前可以保证参数始终收到扫描预算，即使较早的
    字段非常大。 tool_name 在 SDK 的任何地方都没有长度验证； 否则，30K 的幻觉名称将消
    耗全部预算并隐藏参数载荷。
    """
    buf = _BoundedSegments(_EXTRACT_HARD_CAP)

    # 第一个参数：提示词-注入载荷的主要攻击面。
    if action.tool_call and action.tool_call.arguments:
        try:
            parsed = json.loads(action.tool_call.arguments)
            for leaf in _walk_json_strings(parsed):
                buf.add(leaf)
        except (json.JSONDecodeError, TypeError, RecursionError):
            buf.add(action.tool_call.arguments)

    if action.tool_name:
        buf.add(action.tool_name)

    if action.tool_call and action.tool_call.name:
        buf.add(action.tool_call.name)

    return buf.segments


def _extract_text_segments(action: ActionEvent) -> list[str]:
    """从描述智能体 * 想法 * 的字段中提取片段。

    摘要、reasoning_content 和思想仅扫描注入和社会工程模式，而从不扫描 shell 破坏性模
    式。

    首先提取摘要，因为它描述了智能体将要采取的操作。 将它放在第一位，
    reasoning_content 和智能体发出多个长思想或大量推理轨迹时，总是确保摘要接收扫描预
    算。 思想是TextContent的列表； 否则，多个 10K 条目将共同耗尽 30K 预算并隐藏注入扫
    描仪的摘要。
    """
    buf = _BoundedSegments(_EXTRACT_HARD_CAP)

    # 首先摘要：描述智能体将要采取的操作。
    if action.summary:
        buf.add(action.summary)

    if action.reasoning_content:
        buf.add(action.reasoning_content)

    for t in action.thought:
        if t.text:
            buf.add(t.text)

    return buf.segments


def _extract_segments(action: ActionEvent) -> list[str]:
    """从 ActionEvent 中提取所有段（可执行文件 + 推理）。"""
    return _extract_exec_segments(action) + _extract_text_segments(action)


def _extract_content(action: ActionEvent) -> str:
    """来自所有视场的扁弦——全视场扫描面。

    长度以 ``2 * _EXTRACT_HARD_CAP + 1`` 为界：``_extract_exec_segments`` 和
    ``_extract_text_segments`` 中的每个语料库的上限跟踪包含分隔符的连接长度，因此每个
    语料库的
    ``" ".join(segments)`` ≤ ``_EXTRACT_HARD_CAP``。 两个连接的语料库之间的单个空格加
     1。 没有外层切片应用：这样做会丢
    弃文本语料库，当执行填充预算时，会破坏由组合分析器路径保证的先摘要后摘要的原则。
    """
    return " ".join(_extract_segments(action))


def _extract_exec_content(action: ActionEvent) -> str:
    """仅来自可执行字段的平面字符串——shell 模式表面。

    长度以 ``_EXTRACT_HARD_CAP`` 为界：每个语料库的上限
    ``_extract_exec_segments`` 轨道连接长度，包括分隔符。
    """
    return " ".join(_extract_exec_segments(action))


# ---------------------------------------------------------------------------
# 不可见字符定义
#
# 从最初的 14 个代码点集扩展到涵盖 9 个类别的约 200 多个不可见字符。 由 navi-sanitize (
# _invisible.py, MIT, Project-Navi/navi-sanitize) 通知 - 逻辑内联，无依赖性。
#
# 与原始零宽度剥离相同的防御类别，只是更完整。 编译成单个正则表达式以提高性能。
# ---------------------------------------------------------------------------

# 零宽度字符
_ZERO_WIDTH: set[str] = {
    "\u200b",  # 零宽度空间
    "\u200c",  # 零宽度非连接符
    "\u200d",  # 零宽度连接符
    "\u200e",  # 从左到右标记
    "\u200f",  # 从右到左标记
    "\u2060",  # 词连接器
    "\ufeff",  # BOM / 零宽度不间断空格
    "\u180e",  # 蒙古语元音分隔符
}

# 格式和控制字符（不可见或几乎不可见）
_FORMAT_CHARS: set[str] = {
    "\u00ad",  # 软连字符
    "\u034f",  # 组合字素连接器
    "\u2009",  # 狭小的空间
    "\u200a",  # 头发空间
    # 这里不会剥离 U+2028（行分隔符）和 U+2029（段落分隔符）；它们类似空白字符，应在 \s+
    #  阶段折叠，而不是删除。 删除它们会合并 token 并且可以绕过字边界正则表达式检测器。
    #
    "\ufff9",  # 行间注释锚点
    "\ufffa",  # 行间注释分隔符
    "\ufffb",  # 行间注释终止符
    "\ufffc",  # 对象替换字符
    "\u2061",  # 函数应用（不可见）
    "\u2062",  # 看不见的时代
    "\u2063",  # 隐形分隔符
    "\u2064",  # 隐形加号
    "\u206a",  # 禁止对称交换 (已弃用)
    "\u206b",  # 激活对称交换 (已弃用)
    "\u206c",  # 抑制阿拉伯语形式塑造 (已弃用)
    "\u206d",  # 激活阿拉伯语形式塑造 (已弃用)
    "\u206e",  # 国家数字形状 (已弃用)
    "\u206f",  # 标称数字形状 (已弃用)
    "\u2800",  # 盲文图案空白
    "\u1680",  # 奥格姆空格标记
    "\u115f",  # 韩文初声填充物
    "\u1160",  # 韩文中城填充物
    "\u3164",  # 韩文填充物
    "\uffa0",  # 半角韩文填充符
    "\u061c",  # 阿拉伯字母标
}

# 双向覆盖/隔离字符
_BIDI_CHARS: set[str] = {
    "\u202a",  # LRE
    "\u202b",  # RLE
    "\u202c",  # PDF
    "\u202d",  # LRO
    "\u202e",  # RLO
    "\u2066",  # LRI
    "\u2067",  # RLI
    "\u2068",  # FSI
    "\u2069",  # PDI
}

# 蒙古文自由变体选择器
_MONGOLIAN_FVS: set[str] = {
    "\u180b",
    "\u180c",
    "\u180d",
    "\u180f",
}

# 范围编译成正则表达式字符类
_VARIATION_SELECTOR_RANGE = (0xFE00, 0xFE0F)  # VS1-VS16
_VARIATION_SELECTOR_SUPP_RANGE = (0xE0100, 0xE01EF)  # VS17-VS256
_TAG_BLOCK_RANGE = (0xE0000, 0xE007F)  # Unicode 标签块
_C0_RANGES = [(0x0001, 0x0008), (0x000B, 0x000C), (0x000E, 0x001F)]
_DEL = "\x7f"  # DEL 字符——不在 C0 或 C1 中，但同样不可见
_C1_RANGE = (0x0080, 0x009F)

# 为所有不可见字符构建单个编译的正则表达式
_INVISIBLE_PATTERN = (
    # 字符集
    "["
    + "".join(sorted(_ZERO_WIDTH))
    + "]"
    + "|["
    + "".join(sorted(_FORMAT_CHARS))
    + "]"
    + "|["
    + "".join(sorted(_BIDI_CHARS))
    + "]"
    + "|["
    + "".join(sorted(_MONGOLIAN_FVS))
    + "]"
    # 范围
    + "|["
    + chr(_VARIATION_SELECTOR_RANGE[0])
    + "-"
    + chr(_VARIATION_SELECTOR_RANGE[1])
    + "]"
    + "|["
    + chr(_TAG_BLOCK_RANGE[0])
    + "-"
    + chr(_TAG_BLOCK_RANGE[1])
    + "]"
    + "|["
    + chr(_VARIATION_SELECTOR_SUPP_RANGE[0])
    + "-"
    + chr(_VARIATION_SELECTOR_SUPP_RANGE[1])
    + "]"
    # C0 控制（不包括 NUL/TAB/LF/CR）
    + "|["
    + chr(_C0_RANGES[0][0])
    + "-"
    + chr(_C0_RANGES[0][1])
    + "]"
    + "|["
    + chr(_C0_RANGES[1][0])
    + "-"
    + chr(_C0_RANGES[1][1])
    + "]"
    + "|["
    + chr(_C0_RANGES[2][0])
    + "-"
    + chr(_C0_RANGES[2][1])
    + "]"
    # C1控制
    + "|["
    + chr(_C1_RANGE[0])
    + "-"
    + chr(_C1_RANGE[1])
    + "]"
    # DEL
    + "|"
    + re.escape(_DEL)
)

_INVISIBLE_RE: re.Pattern[str] = re.compile(_INVISIBLE_PATTERN)


# ---------------------------------------------------------------------------
# 标准化
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """折叠编码规避，使危险的命令与其模式相匹配。

    攻击者可以使 ``rm`` 对于正则表达式引擎看起来不像 ``rm``
    while still looking like ``rm`` to a shell: zero-width characters,
    fullwidth ASCII、bidi 控件和 null 字节都可以实现此目的。 该函数分四个阶段中和这些
    技术：

    1. **null bytes** -- 防止 C 级字符串截断。
    2. **看不见的字符** -- 去除 ~200+ 个字符，包括零宽度、格式/控制、 bidi、变长选择
    器、标签块、 C0、 C1。（参考 navi-sanitiz
    e，MIT，无依赖。）
    3. **NFKC** -- 全角 ``\\uff52\\uff4d`` 变为 ASCII ``rm``。
    4. **空白崩溃** - NFKC可能会产生新的空白。

    不是否涵盖西里尔字母同形文字或组合标记规避（记录为严格 xfails，推迟到后续）。
    """
    # 第 1 阶段：null 字节
    text = text.replace("\x00", "")

    # 第 2 阶段：不可见字符（编译的正则表达式）
    text = _INVISIBLE_RE.sub("", text)

    # 第 3 阶段：NFKC 标准化
    text = unicodedata.normalize("NFKC", text)

    # 第四阶段：折叠空白
    return re.sub(r"\s+", " ", text)
