"""文件操作的编码管理。"""

import codecs
import functools
import inspect
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import charset_normalizer
from cachetools import LRUCache


if TYPE_CHECKING:
    from openhands.tools.file_editor.impl import FileEditor


# 从未出现在普通文本文件中的控制字节。
BINARY_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")

# 当检测器无法解析文件的编码时，用于整个文件解码的候选编解码器。 短非-UTF-8个文件低于检
# 测器的置信度阈值，被报告为默认编码，因此检测到的值本身不足以恢复它们。 对源文件按最可
# 能到最不可能的顺序排序； 检测器的自我猜测随后被尝试 UTF-8 当它其中之一。
#
TEXT_DECODE_CANDIDATES = ("utf-8", "cp1252", "latin-1", "cp1251")

# charset_normalizer 报告 IANA 名称下的一些编解码器； 将它们映射到上面使用的 Python 编解
# 码器名称，以便它们的猜测正确解码。
#
TEXT_DECODE_ALIASES = {
    "windows-1251": "cp1251",
    "windows-1252": "cp1252",
    "iso-8859-1": "latin-1",
    "iso-8859-15": "latin-1",
}


class EncodingManager:
    """跨多个操作管理文件编码以确保一致性。"""

    # 缓存中默认最大条目数
    DEFAULT_MAX_CACHE_SIZE: int = 1000  # 〜= 300 KB
    default_encoding: str
    confidence_threshold: float

    def __init__(self, max_cache_size=None):
        # 缓存检测到的编码以避免对同一文件进行重复检测
        # 格式：{path_str:(编码，mtime)}
        self._encoding_cache: LRUCache[str, tuple[str, float]] = LRUCache(
            maxsize=max_cache_size or self.DEFAULT_MAX_CACHE_SIZE
        )
        # 默认回退方案编码
        self.default_encoding = "utf-8"
        # 编码检测的置信阈值
        self.confidence_threshold = 0.9

    def detect_encoding(self, path: Path) -> str:
        """检测文件的编码而不处理缓存逻辑。
        Args:
            path: 文件路径
        Returns:
            检测到的编码或检测失败时的默认编码
        """
        # 处理不存在的文件
        if not path.exists():
            return self.default_encoding

        # 读取文件样本以检测编码
        sample_size = min(os.path.getsize(path), 1024 * 1024)  # 最大 1MB 样本
        with open(path, "rb") as f:
            raw_data = f.read(sample_size)

        if raw_data.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"

        try:
            raw_data.decode(self.default_encoding)
        except UnicodeDecodeError:
            pass
        else:
            return self.default_encoding

        # 使用 charset_normalizer 代替 chardet
        results = charset_normalizer.detect(raw_data)

        # 获取最佳匹配（如果存在）
        if (
            results
            and results["confidence"]
            and results["confidence"] > self.confidence_threshold
            and results["encoding"]
        ):
            encoding = results["encoding"]
            # 文本文件始终使用 utf-8 而不是 ascii，以支持非 ASCII 字符。 这确保最初仅包
            # 含 ASCII 的文件稍后可以接受非 ASCII 内容
            #
            if encoding.lower() == "ascii":
                encoding = self.default_encoding
        else:
            encoding = self.default_encoding

        return encoding

    def _best_guess_encoding(self, path: Path) -> str | None:
        """当它是我们信任的编解码器时，返回 charset_normalizer 的猜测。

        短非-UTF-8 个得分低于 ``confidence_threshold`` 即使猜测正确，但原始猜测也值得
        一试——但仅当它指出了一个常见的编码器，因为检
        测器还提出了异国情调的候选者e.g. cp1006（表示 latin-1 文本），解码为 mojibake
        。
        """
        try:
            sample_size = min(os.path.getsize(path), 1024 * 1024)
            with open(path, "rb") as f:
                raw_data = f.read(sample_size)
        except OSError:
            return None
        guess = charset_normalizer.detect(raw_data) or {}
        encoding = guess.get("encoding")
        if not encoding:
            return None
        normalized = str(encoding).lower().replace("_", "-")
        if normalized in TEXT_DECODE_ALIASES:
            return TEXT_DECODE_ALIASES[normalized]
        return normalized if normalized in TEXT_DECODE_CANDIDATES else None

    def _recover_encoding(self, path: Path) -> str | None:
        """返回一个将 ``path`` 解码为无控制字节文本的编解码器。"""
        candidates = (
            self.default_encoding,
            self._best_guess_encoding(path),
            *TEXT_DECODE_CANDIDATES,
        )
        for candidate in dict.fromkeys(c for c in candidates if c):
            try:
                text = path.read_text(encoding=candidate)
            except (OSError, UnicodeDecodeError, LookupError):
                continue
            if BINARY_CONTROL_CHARS.search(text) is None:
                return candidate
        return None

    def resolve_text_encoding(self, path: Path) -> str | None:
        """返回将 ``path`` 解码为干净文本的编码，否则返回 None。"""
        encoding = self.get_encoding(path)
        try:
            text = path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            return None
        return encoding if BINARY_CONTROL_CHARS.search(text) is None else None

    def get_encoding(self, path: Path) -> str:
        """获取文件的编码，使用缓存或检测（如果需要）。
        Args:
            path: 文件路径
        Returns:
            文件的编码
        """
        path_str = str(path)
        # 如果文件不存在，则返回默认编码
        if not path.exists():
            return self.default_encoding

        # 获取当前修改时间
        current_mtime = os.path.getmtime(path)

        # 检查缓存中是否有有效条目
        if path_str in self._encoding_cache:
            cached_encoding, cached_mtime = self._encoding_cache[path_str]
            if cached_mtime == current_mtime:
                return cached_encoding

        # 没有有效的缓存条目，检测编码
        encoding = self.detect_encoding(path)

        # 检测器报告低于其置信阈值的短非 UTF-8 文件的默认编码。 恢复可解码的编码，以便读
        # 取和验证在相同的编解码器上达成一致。
        #
        if encoding == self.default_encoding:
            recovered = self._recover_encoding(path)
            if recovered is not None:
                encoding = recovered

        # 缓存当前修改时间的结果
        self._encoding_cache[path_str] = (encoding, current_mtime)
        return encoding


def with_encoding(method):
    """处理文件操作的文件编码的装饰器。
    该装饰器自动检测并应用文件操作的正确编码，确保读写操作之间的一致性。
    Args:
        method: 装饰方法
    Returns:
        装饰方法
    """

    @functools.wraps(method)
    def wrapper(self: "FileEditor", path: Path, *args, **kwargs):
        # 跳过目录的编码处理
        if path.is_dir():
            return method(self, path, *args, **kwargs)

        # 检查该方法是否接受编码参数
        sig = inspect.signature(method)
        accepts_encoding = "encoding" in sig.parameters

        if accepts_encoding:
            # 对于尚不存在的文件（例如“创建”命令中的文件），请使用默认编码
            #
            if not path.exists():
                if "encoding" not in kwargs:
                    kwargs["encoding"] = self._encoding_manager.default_encoding
            else:
                # 从编码管理器获取现有文件的编码
                encoding = self._encoding_manager.get_encoding(path)
                # 如果方法接受，则将编码添加到 kwargs
                if "encoding" not in kwargs:
                    kwargs["encoding"] = encoding

        return method(self, path, *args, **kwargs)

    return wrapper
