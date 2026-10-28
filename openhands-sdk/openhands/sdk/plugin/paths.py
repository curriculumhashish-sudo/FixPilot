"""插件获取实现共享的文件系统路径。"""

from __future__ import annotations

from pathlib import Path

from openhands.sdk.extensions.fetch import get_cache_path


PINNED_REFS_DIR = "resolved-refs"


def get_pinned_plugin_cache_path(
    source_url: str, cache_dir: Path, resolved_ref: str
) -> Path:
    """返回提交 SHA 处插件源的不可变缓存路径。"""
    return get_cache_path(source_url, cache_dir) / PINNED_REFS_DIR / resolved_ref
