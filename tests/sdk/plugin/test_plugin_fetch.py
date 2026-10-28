"""测试特定于插件的获取行为。

验证插件获取层是否使用插件特定的错误类型 (PluginFetchError)、插件 DEFAULT_CACHE_DIR
和 Plugin.fetch() 类方法正确包装
extensions.fetch。

核心的获取逻辑（解析、缓存、Git 操作）在 tests/sdk/extensions/test_fetch.py. 进行测试
。
tests/sdk/git/test_cached_repo.py. Git 基础设施（克隆、更新、检查出、锁定）在进行测试
"""

import subprocess
from pathlib import Path
from unittest.mock import create_autospec, patch

import pytest

from openhands.sdk.git.cached_repo import GitHelper
from openhands.sdk.git.exceptions import GitCommandError
from openhands.sdk.plugin import Plugin, PluginFetchError
from openhands.sdk.plugin.fetch import fetch_plugin


def test_fetch_git_error_raises_plugin_fetch_error(tmp_path: Path):
    """git 失败中的 ExtensionFetchError 被包装为 PluginFetchError。"""
    mock_git = create_autospec(GitHelper, instance=True)
    mock_git.clone.side_effect = GitCommandError(
        "fatal: repository not found",
        command=["git", "clone"],
        exit_code=128,
    )

    with pytest.raises(PluginFetchError, match="Failed to fetch plugin"):
        fetch_plugin(
            "github:owner/nonexistent",
            cache_dir=tmp_path,
            git_helper=mock_git,
        )


def test_fetch_generic_error_raises_plugin_fetch_error(tmp_path: Path):
    """通用运行时错误也包装为 PluginFetchError。"""
    mock_git = create_autospec(GitHelper, instance=True)
    mock_git.clone.side_effect = RuntimeError("Unexpected error")

    with pytest.raises(PluginFetchError, match="Failed to fetch plugin"):
        fetch_plugin(
            "github:owner/repo",
            cache_dir=tmp_path,
            git_helper=mock_git,
        )


def test_fetch_unknown_ref_from_existing_cache_raises_plugin_fetch_error(
    tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    (source / "version.txt").write_text("v1")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=source,
        check=True,
    )
    source_url = f"file://{source}"
    cache_path = fetch_plugin(source_url, cache_dir=tmp_path / "cache")
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cache_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    with pytest.raises(PluginFetchError, match="Failed to fetch plugin"):
        fetch_plugin(
            source_url,
            cache_dir=tmp_path / "cache",
            ref="missing-ref",
        )

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cache_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert head_after == head_before
    assert (cache_path / "version.txt").read_text() == "v1"


def test_fetch_local_with_repo_path_resolves_subdirectory(tmp_path: Path):
    """本地单体仓库源加上 repo_path 解析为子目录。"""
    plugin_dir = tmp_path / "monorepo"
    (plugin_dir / "plugins" / "my-plugin").mkdir(parents=True)

    result = fetch_plugin(str(plugin_dir), repo_path="plugins/my-plugin")

    assert result == (plugin_dir / "plugins" / "my-plugin").resolve()


def test_fetch_local_with_missing_repo_path_raises_plugin_fetch_error(
    tmp_path: Path,
):
    """不存在作为 PluginFetchError 的曲面的 repo_path。"""
    plugin_dir = tmp_path / "monorepo"
    plugin_dir.mkdir()

    with pytest.raises(PluginFetchError, match="not found in local source"):
        fetch_plugin(str(plugin_dir), repo_path="plugins/my-plugin")


def test_fetch_uses_default_cache_dir(tmp_path: Path):
    """fetch_plugin 使用特定于插件的 DEFAULT_CACHE_DIR。"""
    mock_git = create_autospec(GitHelper, instance=True)

    def clone_side_effect(url, dest, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ".git").mkdir()

    mock_git.clone.side_effect = clone_side_effect

    with patch("openhands.sdk.plugin.fetch.DEFAULT_CACHE_DIR", tmp_path / "cache"):
        result = fetch_plugin(
            "github:owner/repo",
            cache_dir=None,
            git_helper=mock_git,
        )

    assert result.exists()
    assert str(tmp_path / "cache") in str(result)


def test_plugin_fetch_delegates(tmp_path: Path):
    """Plugin.fetch() 将本地路径委托给 fetch_plugin。"""
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()

    result = Plugin.fetch(str(plugin_dir))
    assert result == plugin_dir.resolve()


def test_plugin_fetch_local_with_repo_path_resolves_subdirectory(tmp_path: Path):
    """Plugin.fetch 构成了一个本地源 repo_path。"""
    plugin_dir = tmp_path / "monorepo"
    (plugin_dir / "plugins" / "my-plugin").mkdir(parents=True)

    result = Plugin.fetch(str(plugin_dir), repo_path="plugins/my-plugin")

    assert result == (plugin_dir / "plugins" / "my-plugin").resolve()
