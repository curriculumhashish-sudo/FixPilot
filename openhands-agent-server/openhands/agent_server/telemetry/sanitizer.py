"""将丰富的运行时间值减少为狭窄的、不可识别的形状
:mod:`.models`。

两条规则具有隐私保证，并且都是可测试的：

1. **永远不会读取异常消息。** ``str(exc)`` 未出现在此模块的任何路径上。 消息通常会嵌
入提示词、文件路径、请求正文和 API 键，因此唯一安全的策略是永
远不要查看。

2. **回溯从未被格式化。**我们手动行走``exc.__traceback__``，只阅读
``tb_frame.f_globals["__name__"]``并且
   ``tb.tb_lineno``. ``traceback.extract_tb`` / ``format_exception`` 在这里被禁止，因
   为：class:
   `traceback.FrameSummary` 读取实际的
   *源行*从磁盘进入对象，并且``f_locals``显然成立
   活生生的价值观。

指纹是一个分组键，而不是一个脱敏机制：其预图像已经PII，因此哈希是纵深防御而不是依赖的
对象。
"""

import bisect
import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from types import TracebackType
from typing import Final, NamedTuple

from openhands.agent_server.telemetry.models import (
    ERROR_CATEGORY_BY_CLASS_NAME,
    TELEMETRY_SCHEMA_VERSION,
    ErrorCategory,
)


_FIRST_PARTY_ROOT: Final[str] = __name__.split(".", 1)[0]
_MAX_FINGERPRINT_FRAMES: Final[int] = 5

_SAFE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_.:\-]{0,63}$")
_SAFE_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*([.:][A-Za-z_][A-Za-z0-9_]*)*$"
)
_SAFE_IDENTIFIER_MAX_LEN: Final[int] = 96
_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.+\-/]{0,63}$"
)

UNKNOWN_TOKEN: Final[str] = "unknown"
UNKNOWN_ERROR_CLASS: Final[str] = "UnknownError"
_UNKNOWN_CATEGORY: Final[ErrorCategory] = "unknown"


def safe_token(value: object, *, default: str = UNKNOWN_TOKEN) -> str:
    """强制转换为小写 token，如果不合适则强制转换为 ``default``。

    强制而不是引发：令人惊讶的值应该降低事件的质量，而不是丢失它或破坏对话。
    """
    if not isinstance(value, str):
        return default
    candidate = value.strip().lower()
    return candidate if _SAFE_TOKEN_RE.match(candidate) else default


def safe_identifier(value: object, *, default: str = UNKNOWN_ERROR_CLASS) -> str:
    """强制为点标识符，如果不合适则为 ``default``。"""
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    if len(candidate) > _SAFE_IDENTIFIER_MAX_LEN:
        return default
    return candidate if _SAFE_IDENTIFIER_RE.match(candidate) else default


def safe_version(value: object, *, default: str = UNKNOWN_TOKEN) -> str:
    """强制版本/git ref，如果不合适则为 ``default``。"""
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    return candidate if _VERSION_RE.match(candidate) else default


def allowlisted(
    value: object, allowed: frozenset[str], *, default: str = "other"
) -> str:
    """将 ``value`` 映射到封闭词汇表上，折叠其他任何内容。

    限制基数并保证没有自由格式的字符串转义。
    """
    token = safe_token(value, default=default)
    return token if token in allowed else default


class Bounds(NamedTuple):
    """有序的桶边缘加上大小的标签。

    保持边和查找在一起意味着调用者不能将值与错误的尺度配对，并且查找是二分查找而不是
    线性扫描。
    """

    edges: tuple[float, ...]

    def label(self, value: float | None) -> str:
        """将幅度映射到粗略标签，例如 ``5-20`` 或 ``500+``。

        原始幅度是与时间戳连接后的重新识别向量，因此不会准确报告计数、持续时间或成本
        。
        """
        if value is None:
            return UNKNOWN_TOKEN
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return UNKNOWN_TOKEN
        if numeric < 0:
            return UNKNOWN_TOKEN

        index = bisect.bisect_right(self.edges, numeric)
        if index == len(self.edges):
            return f"{_format_number(self.edges[-1])}+"
        lower = self.edges[index - 1] if index else None
        return _format_bucket(lower, self.edges[index])


DURATION_BOUNDS: Final[Bounds] = Bounds((1, 5, 15, 60, 300, 1800))
COUNT_BOUNDS: Final[Bounds] = Bounds((1, 5, 20, 100, 500))
TOKEN_BOUNDS: Final[Bounds] = Bounds((1_000, 10_000, 50_000, 200_000, 1_000_000))
COST_BOUNDS: Final[Bounds] = Bounds((0.01, 0.1, 1, 10, 100))


def bucket(value: float | None, bounds: Bounds) -> str:
    """:meth:`Bounds.label` 上的向后兼容包装器。"""
    return bounds.label(value)


def _format_bucket(lower: float | None, upper: float) -> str:
    if lower is None:
        return f"lt-{_format_number(upper)}"
    return f"{_format_number(lower)}-{_format_number(upper)}"


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value).replace(".", "p")


def _derive_key(salt: str | bytes | None) -> bytes:
    """将任何 salt 标准化为 blake2s 接受的 32 字节密钥。"""
    if salt is None:
        return b""
    raw = salt.encode("utf-8") if isinstance(salt, str) else salt
    if len(raw) <= 32:
        return raw
    return hashlib.blake2s(raw, digest_size=32).digest()


def pseudonymize(value: str | bytes, salt: str | bytes | None) -> str:
    """标识符的键控摘要。

    用于会话ID，出现在 URLs 和日志中——只发送一个原始值会使整个分析数据集能够回溯到个
    人。
    """
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.blake2s(raw, key=_derive_key(salt), digest_size=16).hexdigest()


@lru_cache(maxsize=1)
def _known_providers() -> frozenset[str]:
    """提供者名称，源自 LiteLLM 而不是手动维护。"""
    from litellm import provider_list

    return frozenset(str(getattr(p, "value", p)).lower() for p in provider_list)


# 型号 *family*, which LiteLLM 没有概念：它模型提供商，同一家庭由许多（克莱尔-）服务* 正
# 在运行 Anthropic, bedrock, azure_ai and deepinfra). 从这里推导出 models_by_provider 对
# 于每个家庭，都会产生 4+ 个候选模型名称回退方案保持明确。 使用了带有提供者前缀的路径
# LiteLLM真实提供者列表； 测试断言这里的每个目标都是其中之一。
#
_MODEL_FAMILY_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("claude", "anthropic"),
    ("gpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("gemini", "gemini"),
    ("mistral", "mistral"),
    ("deepseek", "deepseek"),
    ("llama", "ollama"),
    ("grok", "xai"),
)


def model_family(model: object) -> str:
    """将模型字符串简化为粗略的提供者系列。

    ``litellm`` 模型字符串可以携带部署名称，对于自定义端点，还可以携带主机名 — 因此仅
    报告已识别的系列。
    """
    if not isinstance(model, str) or not model.strip():
        return UNKNOWN_TOKEN
    lowered = model.strip().lower()

    prefix = lowered.split("/", 1)[0] if "/" in lowered else ""
    if prefix in _known_providers():
        return prefix

    for hint, family in _MODEL_FAMILY_HINTS:
        if hint in lowered:
            return family
    return "other"


@dataclass(frozen=True, slots=True)
class ErrorFingerprint:
    """对故障的完整、经过净化的描述。"""

    error_class: str
    error_category: ErrorCategory
    error_fingerprint: str
    error_origin_module: str | None
    error_origin_lineno: int | None
    is_first_party: bool


def _walk_frames(tb: TracebackType | None) -> Iterator[tuple[str, int]]:
    """收集 ``(module, lineno)`` 对，但不具体化来源。

    只读 ``f_globals["__name__"]`` 和 ``tb_lineno``。 从来不碰
    ``f_locals``，并且从不调用：mod:`traceback`。
    """
    current = tb
    # 有界：失控的递归会产生一条巨大的链。
    remaining = 256
    while current is not None and remaining > 0:
        module = current.tb_frame.f_globals.get("__name__")
        if isinstance(module, str) and module:
            yield module, current.tb_lineno
        current = current.tb_next
        remaining -= 1


def _classify(exc: BaseException) -> tuple[str, bool]:
    """返回``(error_class, is_first_party)``。

    第一方保留其点模块以确保精度。 第三方崩溃为 ``pkg:QualName``，因此不熟悉的依赖关
    系不会破坏基数。
    """
    exc_type = type(exc)
    # __name__，而不是 __qualname__：嵌套类给出 ``outer.<locals>.Inner``，它不是有效的标
    # 识符，会绕过验证。
    #
    name = safe_identifier(getattr(exc_type, "__name__", None))
    module = getattr(exc_type, "__module__", "") or ""

    if module in ("builtins", "", "__main__"):
        return name, False

    if module == _FIRST_PARTY_ROOT or module.startswith(f"{_FIRST_PARTY_ROOT}."):
        return safe_identifier(f"{module}.{name}", default=name), True

    top_level = module.split(".", 1)[0]
    return safe_identifier(f"{top_level}:{name}", default=name), False


def _categorize(exc: BaseException) -> ErrorCategory:
    """类别仅从异常*type*开始，走MRO。"""
    candidates: Iterator[ErrorCategory | None] = (
        ERROR_CATEGORY_BY_CLASS_NAME.get(klass.__name__) for klass in type(exc).__mro__
    )
    # 使用循环而不是 next(): Pyright 将生成器表达式上的 next() 加宽为 str，从而丢失了
    # Literal 类型。
    #
    for category in candidates:
        if category is not None:
            return category
    return _UNKNOWN_CATEGORY


def normalize_exception(exc: BaseException) -> ErrorFingerprint:
    """减少可分组、非识别指纹的例外情况。

    消息永远不会被读取，回溯也不会被格式化； 请参阅模块文档字符串。
    """
    error_class, is_first_party = _classify(exc)
    category = _categorize(exc)

    frames = list(_walk_frames(exc.__traceback__))
    first_party_frames = [
        (module, lineno)
        for module, lineno in frames
        if module == _FIRST_PARTY_ROOT or module.startswith(f"{_FIRST_PARTY_ROOT}.")
    ]

    origin_module: str | None = None
    origin_lineno: int | None = None
    if first_party_frames:
        deepest_module, deepest_lineno = first_party_frames[-1]
        origin_module = safe_identifier(deepest_module, default=UNKNOWN_TOKEN)
        origin_lineno = deepest_lineno
    elif frames:
        # 无第一方框架：仅报告顶级包。
        deepest_module, deepest_lineno = frames[-1]
        origin_module = safe_identifier(
            deepest_module.split(".", 1)[0], default=UNKNOWN_TOKEN
        )
        origin_lineno = deepest_lineno

    # 原像已经是PII自由的：类、类别、模块/行。 没有消息。
    parts = [str(TELEMETRY_SCHEMA_VERSION), error_class, category]
    parts.extend(
        f"{module}:{lineno}"
        for module, lineno in first_party_frames[-_MAX_FINGERPRINT_FRAMES:]
    )
    fingerprint = hashlib.blake2s(
        "|".join(parts).encode("utf-8"), digest_size=8
    ).hexdigest()

    return ErrorFingerprint(
        error_class=error_class,
        error_category=category,
        error_fingerprint=fingerprint,
        error_origin_module=origin_module,
        error_origin_lineno=origin_lineno,
        is_first_party=is_first_party,
    )


def normalize_error_code(code: object) -> ErrorFingerprint:
    """对仅通过字符串代码识别的故障进行指纹识别。

    ``ConversationErrorEvent.code`` 被记录为“通常是一种类型”，因此它被视为类名并通过
    相同的验证运行。 永远不会读取随附的
    ``detail`` 字段。
    """
    error_class = safe_identifier(code)
    category = ERROR_CATEGORY_BY_CLASS_NAME.get(
        error_class.rsplit(".", 1)[-1].rsplit(":", 1)[-1], "unknown"
    )
    fingerprint = hashlib.blake2s(
        "|".join([str(TELEMETRY_SCHEMA_VERSION), error_class, category]).encode(
            "utf-8"
        ),
        digest_size=8,
    ).hexdigest()
    return ErrorFingerprint(
        error_class=error_class,
        error_category=category,
        error_fingerprint=fingerprint,
        error_origin_module=None,
        error_origin_lineno=None,
        is_first_party=False,
    )
