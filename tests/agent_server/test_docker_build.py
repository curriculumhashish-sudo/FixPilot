"""测试 agent_server Docker 构建模块。"""

import os
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest


BUILDKIT_STDERR_SAMPLE = "\n".join(
    [
        "#8 importing cache manifest from "
        "ghcr.io/openhands/eval-agent-server:buildcache-source-minimal-sample",
        "#8 DONE 15.3s",
        "#12 importing cache manifest from "
        "ghcr.io/openhands/eval-agent-server:buildcache-shared-source-minimal-main",
        "#12 ERROR: failed to configure registry cache importer: "
        "ghcr.io/openhands/eval-agent-server:"
        "buildcache-shared-source-minimal-main: not found",
        "#14 importing cache manifest from "
        "ghcr.io/openhands/eval-agent-server:buildcache-shared-source-minimal",
        "#14 DONE 20.4s",
        "#17 [builder 10/10] RUN uv sync",
        "#17 CACHED",
        "#30 exporting to image",
        "#30 exporting manifest sha256:abc123 1.4s done",
        "#30 exporting config sha256:def456 2.3s done",
        "#30 pushing layers 35.9s done",
        "#30 DONE 142.8s",
        "#31 exporting cache to registry",
        "#31 DONE 264.3s",
        "",
    ]
)


def _create_fake_sdist(tmp_path: Path) -> Path:
    src_root = tmp_path / "openhands-sdk-test"
    src_root.mkdir()
    (src_root / "README.md").write_text("fixture", encoding="utf-8")

    tarball = tmp_path / "openhands-sdk-test.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(src_root, arcname=src_root.name)

    return tarball


def test_git_info_priority_sdk_sha():
    """测试 SDK_SHA 优先于 GITHUB_SHA 和 git 命令。"""
    from openhands.agent_server.docker.build import _git_info

    with patch.dict(
        os.environ,
        {
            "SDK_SHA": "abc1234567890",
            "GITHUB_SHA": "def1234567890",
            "SDK_REF": "refs/heads/test-branch",  # 还设置 REF 以避免 git 调用
        },
        clear=False,
    ):
        with patch(
            "openhands.agent_server.docker.build._run"
        ) as mock_run:  # 不应该被称为
            git_ref, git_sha = _git_info()

            assert git_sha == "abc1234567890"
            assert git_sha[:7] == "abc1234"
            # git command should not be called when SDK_SHA is set
            mock_run.assert_not_called()


def test_git_info_priority_github_sha():
    """测试未设置 SDK_SHA 时使用 GITHUB_SHA。"""
    from openhands.agent_server.docker.build import _git_info

    with patch.dict(
        os.environ,
        {
            "GITHUB_SHA": "def1234567890",
            "GITHUB_REF": "refs/heads/main",  # 还设置 REF 以避免 git 调用
        },
        clear=False,
    ):
        # 删除 SDK_SHA（如果存在）
        if "SDK_SHA" in os.environ:
            del os.environ["SDK_SHA"]
        if "SDK_REF" in os.environ:
            del os.environ["SDK_REF"]

        with patch(
            "openhands.agent_server.docker.build._run"
        ) as mock_run:  # 不应该被称为
            git_ref, git_sha = _git_info()

            assert git_sha == "def1234567890"
            assert git_sha[:7] == "def1234"
            mock_run.assert_not_called()


def test_git_info_priority_sdk_ref():
    """测试 SDK_REF 优先于 GITHUB_REF 和 git 命令。"""
    from openhands.agent_server.docker.build import _git_info

    with patch.dict(
        os.environ,
        {
            "SDK_REF": "refs/heads/my-branch",
            "GITHUB_REF": "refs/heads/other-branch",
            "SDK_SHA": "test123456",  # 还设置 SHA 以避免 git 调用
        },
        clear=False,
    ):
        git_ref, git_sha = _git_info()

        assert git_ref == "refs/heads/my-branch"


def test_git_info_priority_github_ref():
    """测试未设置 SDK_REF 时使用 GITHUB_REF。"""
    from openhands.agent_server.docker.build import _git_info

    with patch.dict(
        os.environ,
        {
            "GITHUB_REF": "refs/heads/other-branch",
            "GITHUB_SHA": "test123456",  # 还设置 SHA 以避免 git 调用
        },
        clear=False,
    ):
        # 删除 SDK_REF（如果存在）
        if "SDK_REF" in os.environ:
            del os.environ["SDK_REF"]
        if "SDK_SHA" in os.environ:
            del os.environ["SDK_SHA"]

        git_ref, git_sha = _git_info()

        assert git_ref == "refs/heads/other-branch"


def test_git_info_submodule_scenario():
    """
    测试父存储库设置 SDK_SHA 和 SDK_REF 的子模块场景。 这模拟了 PR 描述中的用例。
    """
    from openhands.agent_server.docker.build import _git_info

    # 模拟父存储库提取子模块提交并传递它
    with patch.dict(
        os.environ,
        {
            "SDK_SHA": "a612c0a1234567890abcdef",  # 子模块提交
            "SDK_REF": "refs/heads/detached",  # 在子模块中分离 HEAD
        },
        clear=False,
    ):
        git_ref, git_sha = _git_info()

        assert git_sha == "a612c0a1234567890abcdef"
        assert git_sha[:7] == "a612c0a"
        assert git_ref == "refs/heads/detached"


def test_git_info_empty_sdk_sha_falls_back():
    """测试空的 SDK_SHA 回落到 GITHUB_SHA。"""
    from openhands.agent_server.docker.build import _git_info

    with patch.dict(
        os.environ,
        {
            "SDK_SHA": "",  # 空字符串应该回退
            "GITHUB_SHA": "github123456",
            "GITHUB_REF": "refs/heads/fallback",  # 还设置 REF 以避免 git 调用
        },
        clear=False,
    ):
        with patch("openhands.agent_server.docker.build._run") as mock_run:
            git_ref, git_sha = _git_info()

            assert git_sha == "github123456"
            assert git_sha[:7] == "github1"
            mock_run.assert_not_called()


def test_base_slug_short_image():
    """测试短图像名称是否原样返回。"""
    from openhands.agent_server.docker.build import _base_slug

    # 简单的图像名称，无需截断
    result = _base_slug("python:3.13")
    assert result == "python_tag_3.13"

    # 与注册表
    result = _base_slug("ghcr.io/org/repo:v1.0")
    assert result == "ghcr.io_s_org_s_repo_tag_v1.0"


def test_base_slug_no_tag():
    """使用没有标签的图像测试 base_slug。"""
    from openhands.agent_server.docker.build import _base_slug

    result = _base_slug("python")
    assert result == "python"

    result = _base_slug("ghcr.io/org/repo")
    assert result == "ghcr.io_s_org_s_repo"


def test_truncate_ident_cases():
    """练习_truncate_ident优先规则。"""
    from openhands.agent_server.docker.build import _truncate_ident

    assert _truncate_ident("repo", "v1", 20) == "repo_tag_v1"
    assert _truncate_ident("averylongrepo", "tag", 10) == "av_tag_tag"
    assert _truncate_ident("repo", "averylongtag", 8) == "_tag_ave"
    assert _truncate_ident("averylongrepo", "", 5) == "avery"


def test_base_slug_truncation_with_tag():
    """测试带有标签的长图像名称是否被正确截断。"""
    from openhands.agent_server.docker.build import _base_slug

    # 创建一个很长的图像名称，超过 max_len=64
    long_image = (
        "ghcr.io/very-long-organization-name/"
        "very-long-repository-name:very-long-tag-v1.2.3-alpha.1+build.123"
    )

    result = _base_slug(long_image, max_len=64)

    # 检查结果是否在 max_len 范围内
    assert len(result) <= 64

    # 检查结果是否包含摘要后缀（13 个字符：“-”+ 12 个十六进制字符）
    assert result[-13:-12] == "-"
    assert all(c in "0123456789abcdef" for c in result[-12:])

    # 检查确切的截断输出以确定性
    assert result == "very-lon_tag_very-long-tag-v1.2.3-alpha.1+build.123-cdb8db90d8c5"


def test_base_slug_truncation_no_tag():
    """测试没有标签的长图像名称是否被正确截断。"""
    from openhands.agent_server.docker.build import _base_slug

    # 创建一个很长的没有标签的图像名称
    long_image = (
        "ghcr.io/very-long-organization-name-here/"
        "very-long-repository-name-that-exceeds-max-length"
    )

    result = _base_slug(long_image, max_len=64)

    # 检查结果是否在 max_len 范围内
    assert len(result) <= 64

    # 检查结果是否包含摘要后缀
    assert result[-13:-12] == "-"
    assert all(c in "0123456789abcdef" for c in result[-12:])

    # 检查确切的截断输出以确定性
    assert result == "very-long-repository-name-that-exceeds-max-length-2a772685291d"


def test_base_slug_preserves_latest_tag_suffix():
    """确保在截断长段时 tag_latest 后缀不会被破坏。"""
    from openhands.agent_server.docker.build import _base_slug

    image = (
        "docker.io/swebench/sweb.eval.x86_64.astropy_1776_astropy-8872:"
        "tag_latest-0a797356ebce"
    )

    result = _base_slug(image, max_len=64)

    assert len(result) <= 64
    assert result == "sweb.eval.x86_64.astropy_17_tag_latest-0a797356ebce-e023ce15bc3b"


def test_base_slug_preserves_tag_with_registry_port():
    """使用端口处理注册表，而不丢失标记段。"""
    from openhands.agent_server.docker.build import _base_slug

    image = (
        "localhost:5001/swebench/sweb.eval.x86_64.astropy_1776_astropy-8872:"
        "tag_latest-0a797356ebce"
    )

    result = _base_slug(image, max_len=64)

    assert len(result) <= 64
    assert result == "sweb.eval.x86_64.astropy_17_tag_latest-0a797356ebce-0138a908f35e"


def test_base_slug_custom_max_len():
    """使用自定义 max_len 参数测试 base_slug。"""
    from openhands.agent_server.docker.build import _base_slug

    image = "ghcr.io/org/very-long-repository-name:v1.2.3"

    # 当 max_len=40 时，应该触发截断
    result = _base_slug(image, max_len=40)
    assert len(result) <= 40
    assert result[-13:-12] == "-"  # 是否有摘要后缀

    # 当 max_len=100 时，不应截断
    result = _base_slug(image, max_len=100)
    assert result == "ghcr.io_s_org_s_very-long-repository-name_tag_v1.2.3"
    assert len(result) < 100


def test_base_slug_digest_consistency():
    """测试相同的图像始终生成相同的摘要。"""
    from openhands.agent_server.docker.build import _base_slug

    long_image = (
        "ghcr.io/very-long-organization-name/"
        "very-long-repository-name:very-long-tag-v1.2.3"
    )

    result1 = _base_slug(long_image, max_len=50)
    result2 = _base_slug(long_image, max_len=50)

    # 相同的输入应始终产生相同的输出
    assert result1 == result2

    # 不同的输入应该产生不同的摘要
    different_image = long_image.replace("v1.2.3", "v1.2.4")
    result3 = _base_slug(different_image, max_len=50)
    assert result1 != result3


def test_base_slug_edge_case_exact_max_len():
    """当段塞长度完全等于 max_len 时测试 base_slug。"""
    from openhands.agent_server.docker.build import _base_slug

    # 创建一个恰好包含 30 个字符的图像“python_tag_3.13”是 15 个字符，让我们将其与
    # max_len=15 一起使用
    #
    result = _base_slug("python:3.13", max_len=15)
    assert result == "python_tag_3.13"
    assert len(result) == 15


def test_release_tag_aliases_expand_semver_parts():
    from openhands.agent_server.docker.build import _release_tag_aliases

    assert _release_tag_aliases("v1.2.3") == ["v1", "v1.2", "v1.2.3"]
    assert _release_tag_aliases("1.2.3") == ["1", "1.2", "1.2.3"]


def test_release_tag_aliases_sanitize_non_semver_tags():
    from openhands.agent_server.docker.build import _release_tag_aliases

    assert _release_tag_aliases("release/v1.2.3+build") == ["release-v1.2.3-build"]


def test_versioned_tags_use_sdk_version_for_semver_git_tags():
    """Semver git 标签 (v1.2.3) 遵循 sdk_version (PEP 440，无“v”)。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        git_ref="refs/tags/v1.2.3",
        sdk_version="1.2.3",
        include_versioned_tag=True,
    )

    # Docker 标签使用 sdk_version 中的裸 semver，而不是 git 标签。
    assert opts.versioned_tags == ["1-python", "1.2-python", "1.2.3-python"]


def test_versioned_tags_semver_git_tag_strips_v_when_sdk_version_unknown():
    """即使 sdk_version 未知，Semver git 标签仍然会生成裸 semver。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        git_ref="refs/tags/v1.2.3",
        sdk_version="unknown",
        include_versioned_tag=True,
    )

    assert opts.versioned_tags == ["1-python", "1.2-python", "1.2.3-python"]


def test_versioned_tags_fallback_to_sdk_version_aliases():
    """当不存在 git 标签时，测试 versioned_tags 回退到 SDK 版本。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python,java,golang",
        sdk_version="1.2.0",
        include_versioned_tag=True,
    )

    assert opts.versioned_tags == [
        "1-python",
        "1.2-python",
        "1.2.0-python",
        "1-java",
        "1.2-java",
        "1.2.0-java",
        "1-golang",
        "1.2-golang",
        "1.2.0-golang",
    ]


def test_versioned_tags_non_semver_git_tag_preserved():
    """每个自定义标签只发布一次测试非 semver git 标签。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        git_ref="refs/tags/build-docker",
        sdk_version="1.2.0",
        include_versioned_tag=True,
    )

    assert opts.versioned_tags == ["build-docker-python"]


def test_versioned_tags_no_custom_tags():
    """当未提供自定义标签时测试 versioned_tags。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="",
        sdk_version="1.2.0",
        include_versioned_tag=True,
    )

    assert opts.versioned_tags == []


def test_all_tags_include_short_long_sha_and_branch():
    """测试 all_tags 是否包含短 SHA、长 SHA 和经过清理的分支标签。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        git_sha="abc1234567890fedcba",
        git_ref="refs/heads/Feature/Release_1",
        include_base_tag=False,
    )

    assert opts.all_tags == [
        "ghcr.io/openhands/agent-server:abc1234-python",
        "ghcr.io/openhands/agent-server:abc1234567890fedcba-python",
        "ghcr.io/openhands/agent-server:feature-release-1-python",
    ]


def test_slim_flavor_has_distinct_image_and_cache_tags():
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        base_image="python:3.13",
        custom_tags="python",
        git_sha="abc1234567890fedcba",
        git_ref="refs/heads/main",
        image_flavor="slim",
        include_base_tag=False,
    )

    assert opts.all_tags == [
        "ghcr.io/openhands/agent-server:abc1234-python-slim",
        "ghcr.io/openhands/agent-server:abc1234567890fedcba-python-slim",
        "ghcr.io/openhands/agent-server:main-python-slim",
    ]
    assert opts.cache_tags == (
        "buildcache-binary-python_tag_3.13-slim-main",
        "buildcache-binary-python_tag_3.13-slim",
    )


def test_minimal_flavor_names_binary_minimal_without_duplicate_suffix():
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        base_image="python-node-runtime",
        custom_tags="python",
        git_sha="abc1234567890fedcba",
        git_ref="refs/tags/v1.48.0",
        sdk_version="1.48.0",
        image_flavor="minimal",
        target="binary-minimal",
        arch="amd64",
        include_base_tag=False,
        include_versioned_tag=True,
    )

    assert opts.all_tags == [
        "ghcr.io/openhands/agent-server:abc1234-python-minimal-amd64",
        "ghcr.io/openhands/agent-server:abc1234567890fedcba-python-minimal-amd64",
        "ghcr.io/openhands/agent-server:1-python-minimal-amd64",
        "ghcr.io/openhands/agent-server:1.48-python-minimal-amd64",
        "ghcr.io/openhands/agent-server:1.48.0-python-minimal-amd64",
    ]
    assert all("minimal-binary-minimal" not in tag for tag in opts.all_tags)


def test_all_tags_includes_versioned_tags():
    """测试 all_tags 在为标记构建启用时是否包含裸 semver 别名。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python,java",
        git_ref="refs/tags/v1.2.0",
        sdk_version="1.2.0",
        git_sha="abc1234567890",
        include_versioned_tag=True,
        include_base_tag=False,
    )

    all_tags = opts.all_tags

    assert "ghcr.io/openhands/agent-server:abc1234-python" in all_tags
    assert "ghcr.io/openhands/agent-server:abc1234567890-python" in all_tags
    # 版本化标签使用裸语义版本（无“v”前缀）
    assert "ghcr.io/openhands/agent-server:1-python" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2-python" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2.0-python" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2.0-java" in all_tags
    assert "ghcr.io/openhands/agent-server:1-java" in all_tags


def test_all_tags_excludes_versioned_tags_when_disabled():
    """测试 all_tags 禁用时是否排除版本化标签。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        sdk_version="1.2.0",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        include_versioned_tag=False,
        include_base_tag=False,
    )

    all_tags = opts.all_tags

    assert "ghcr.io/openhands/agent-server:abc1234-python" in all_tags
    assert "ghcr.io/openhands/agent-server:abc1234567890-python" in all_tags
    assert "ghcr.io/openhands/agent-server:main-python" in all_tags
    assert "ghcr.io/openhands/agent-server:1-python" not in all_tags


def test_all_tags_with_arch_suffix():
    """测试扩展版本标签是否包含架构后缀。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        git_ref="refs/tags/v1.2.0",
        sdk_version="1.2.0",
        git_sha="abc1234567890",
        arch="amd64",
        include_versioned_tag=True,
        include_base_tag=False,
    )

    all_tags = opts.all_tags

    # 版本化标签使用裸语义版本（无“v”前缀）
    assert "ghcr.io/openhands/agent-server:1-python-amd64" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2-python-amd64" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2.0-python-amd64" in all_tags
    assert "ghcr.io/openhands/agent-server:abc1234567890-python-amd64" in all_tags


def test_all_tags_with_target_suffix():
    """在非二进制目标上测试扩展版本标签。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(
        custom_tags="python",
        sdk_version="1.2.0",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        target="source",
        include_versioned_tag=True,
        include_base_tag=False,
    )

    all_tags = opts.all_tags

    assert "ghcr.io/openhands/agent-server:1-python-source" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2-python-source" in all_tags
    assert "ghcr.io/openhands/agent-server:1.2.0-python-source" in all_tags
    assert "ghcr.io/openhands/agent-server:abc1234567890-python-source" in all_tags


def test_make_build_context_reuses_prebuilt_sdist_without_running_uv_build(
    tmp_path: Path,
):
    from openhands.agent_server.docker.build import (
        _default_sdk_project_root,
        _make_build_context,
    )

    prebuilt_sdist = _create_fake_sdist(tmp_path)

    with patch("openhands.agent_server.docker.build._run") as mock_run:
        ctx = _make_build_context(
            _default_sdk_project_root(),
            prebuilt_sdist=prebuilt_sdist,
        )

    try:
        mock_run.assert_not_called()
        assert (ctx / "README.md").read_text(encoding="utf-8") == "fixture"
        assert (ctx / "Dockerfile").exists()
    finally:
        if ctx.exists():
            import shutil

            shutil.rmtree(ctx, ignore_errors=True)


def test_install_acp_providers_defaults_to_full_provider_set():
    """测试默认值是否再现今天的完整 ACP 提供程序集。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions()
    assert opts.install_acp_providers == "claude-code,codex,gemini-cli"


def test_install_acp_providers_rejects_unknown_provider():
    """测试未知的提供商密钥是否快速失败并显示明确的消息。"""
    from pydantic import ValidationError

    from openhands.agent_server.docker.build import BuildOptions

    with pytest.raises(ValidationError, match="Unknown ACP provider.*bogus"):
        BuildOptions(install_acp_providers="codex,bogus")


def test_install_acp_providers_accepts_empty_list():
    """测试空提供程序列表是否有效（安装 None）。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(install_acp_providers="")
    assert opts.install_acp_providers == ""


@pytest.mark.parametrize(
    "install_acp_providers",
    ["claude-code,codex,gemini-cli", "codex", ""],
)
def test_build_passes_install_acp_providers_build_arg(
    tmp_path: Path, install_acp_providers: str
):
    """测试 build() 将 install_acp_providers 作为 --build-arg 转发。"""
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()
    docker_calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        docker_calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        push=False,
        sdk_project_root=_default_sdk_project_root(),
        install_acp_providers=install_acp_providers,
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context",
            return_value=ctx,
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        build(opts)

    assert len(docker_calls) == 1
    cmd = docker_calls[0][0]
    assert f"INSTALL_ACP_PROVIDERS={install_acp_providers}" in cmd


@pytest.mark.parametrize(
    "env_value,expected",
    [
        (None, "claude-code,codex,gemini-cli"),
        ("", ""),
        ("codex", "codex"),
    ],
)
def test_main_resolves_install_acp_providers_from_env(
    monkeypatch, env_value: str | None, expected: str
):
    """测试显式空 $INSTALL_ACP_PROVIDERS 是否作为空存在，
    而不是像未设置的变量那样被强制恢复为默认值。
    """
    from openhands.agent_server.docker import build as build_module

    if env_value is None:
        monkeypatch.delenv("INSTALL_ACP_PROVIDERS", raising=False)
    else:
        monkeypatch.setenv("INSTALL_ACP_PROVIDERS", env_value)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    captured = {}

    def fake_build(opts):
        captured["opts"] = opts
        return []

    monkeypatch.setattr(build_module, "build", fake_build)
    build_module.main(["--load"])

    assert captured["opts"].install_acp_providers == expected


def test_install_capabilities_defaults_to_full_capability_set():
    """测试默认值是否再现了今天的完整基础映像内容。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions()
    assert opts.install_capabilities == "vscode,browser,docker"


def test_install_capabilities_rejects_unknown_capability():
    """测试未知的功能密钥是否快速失败并显示明确的消息。"""
    from pydantic import ValidationError

    from openhands.agent_server.docker.build import BuildOptions

    with pytest.raises(ValidationError, match="Unknown capability.*bogus"):
        BuildOptions(install_capabilities="vscode,bogus")


def test_install_capabilities_accepts_empty_list():
    """测试空功能列表是否有效（安装 None）。"""
    from openhands.agent_server.docker.build import BuildOptions

    opts = BuildOptions(install_capabilities="")
    assert opts.install_capabilities == ""


@pytest.mark.parametrize(
    "install_capabilities",
    ["vscode,browser,docker", "vscode,browser", "docker", ""],
)
def test_build_passes_install_capabilities_build_arg(
    tmp_path: Path, install_capabilities: str
):
    """测试 build() 将 install_capabilities 作为 --build-arg 转发。"""
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()
    docker_calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        docker_calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        push=False,
        sdk_project_root=_default_sdk_project_root(),
        install_capabilities=install_capabilities,
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context",
            return_value=ctx,
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        build(opts)

    assert len(docker_calls) == 1
    cmd = docker_calls[0][0]
    assert f"INSTALL_CAPABILITIES={install_capabilities}" in cmd


@pytest.mark.parametrize(
    "env_value,expected",
    [
        (None, "vscode,browser,docker"),
        ("", ""),
        ("vscode", "vscode"),
    ],
)
def test_main_resolves_install_capabilities_from_env(
    monkeypatch, env_value: str | None, expected: str
):
    """测试显式空 $INSTALL_CAPABILITIES 是否作为空存在，
    而不是像未设置的变量那样被强制恢复为默认值。
    """
    from openhands.agent_server.docker import build as build_module

    if env_value is None:
        monkeypatch.delenv("INSTALL_CAPABILITIES", raising=False)
    else:
        monkeypatch.setenv("INSTALL_CAPABILITIES", env_value)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    captured = {}

    def fake_build(opts):
        captured["opts"] = opts
        return []

    monkeypatch.setattr(build_module, "build", fake_build)
    build_module.main(["--load"])

    assert captured["opts"].install_capabilities == expected


@pytest.mark.parametrize(
    "target,expect_real_context",
    [
        ("base-image-minimal", False),
        ("base-image", True),
        ("binary", True),
    ],
)
def test_base_image_target_uses_real_build_context(
    tmp_path: Path, target: str, expect_real_context: bool
):
    """回归测试：只有基本图像最小有零构建-上下文
    依赖性。 基础镜像通过`builder`阶段（VSCode扩展所需）依赖于它，而这个阶段需要真实
    的上下文 — 空的上下文路径默默地破坏了
    `--target base-image`（已存在，非特定于INSTALL_CAPABILITIES）。
    """
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()

    def fake_run(cmd, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        target=target,  # type: ignore
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        push=False,
        sdk_project_root=_default_sdk_project_root(),
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context",
            return_value=ctx,
        ) as mock_make_context,
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        build(opts)

    assert mock_make_context.called == expect_real_context


def test_base_image_minimal_stages_acp_install_catalog_without_full_context(
    tmp_path: Path,
):
    """base-image-minimal 的空-上下文快速路径仍必须上演
    ACP 无依赖的 COPies 安装 Dockerfile 的 ACP 提供者阶段上下文，在 —— 与真实 sdist-
    提取的上下文使用相同的相对路径 —— 而不是
    回退到昂贵的完整 SDK 构建。
    """
    from openhands.agent_server.docker.build import (
        _ACP_INSTALL_CATALOG_RELPATH,
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    fake_ctx = tmp_path / "base-ctx"

    def fake_run(cmd, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    sdk_project_root = _default_sdk_project_root()
    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        target="base-image-minimal",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        push=False,
        sdk_project_root=sdk_project_root,
    )

    with (
        patch(
            "openhands.agent_server.docker.build.tempfile.mkdtemp",
            return_value=str(fake_ctx),
        ),
        patch(
            "openhands.agent_server.docker.build._make_build_context"
        ) as mock_make_context,
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        fake_ctx.mkdir()
        build(opts)

    assert not mock_make_context.called
    staged = fake_ctx / _ACP_INSTALL_CATALOG_RELPATH
    assert staged.read_text() == (
        (sdk_project_root / _ACP_INSTALL_CATALOG_RELPATH).read_text()
    )


def test_build_with_prebuilt_sdist_preserves_tags_and_docker_args(tmp_path: Path):
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    prebuilt_sdist = _create_fake_sdist(tmp_path)
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    docker_calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        docker_calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python,java",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        sdk_version="1.2.0",
        include_versioned_tag=True,
        target="source-minimal",
        push=False,
        sdk_project_root=_default_sdk_project_root(),
        prebuilt_sdist=prebuilt_sdist,
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context", return_value=ctx
        ) as mock_make_context,
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        tags = build(opts)

    assert tags == opts.all_tags
    mock_make_context.assert_called_once_with(opts.sdk_project_root, prebuilt_sdist)
    assert len(docker_calls) == 1
    cmd, cwd = docker_calls[0]
    assert cwd == str(ctx)
    assert "--load" in cmd
    assert "--target" in cmd and "source-minimal" in cmd
    assert "--build-arg" in cmd
    assert "BASE_IMAGE=python:3.12" in cmd
    for tag in opts.all_tags:
        assert tag in cmd


def test_build_can_reuse_same_prebuilt_sdist_multiple_times(tmp_path: Path):
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    prebuilt_sdist = _create_fake_sdist(tmp_path)
    docker_calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        docker_calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    def fake_make_context(*_args, **_kwargs):
        idx = len(docker_calls)
        ctx = tmp_path / f"ctx-{idx}"
        ctx.mkdir()
        return ctx

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context",
            side_effect=fake_make_context,
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build._active_buildx_driver",
            return_value="docker-container",
        ),
        patch(
            "openhands.agent_server.docker.build._default_local_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        first_tags = build(
            BuildOptions(
                base_image="python:3.12",
                custom_tags="python",
                git_sha="abc1234567890",
                git_ref="refs/heads/main",
                push=False,
                sdk_project_root=_default_sdk_project_root(),
                prebuilt_sdist=prebuilt_sdist,
            )
        )
        second_tags = build(
            BuildOptions(
                base_image="python:3.12",
                custom_tags="java",
                git_sha="abc1234567890",
                git_ref="refs/heads/main",
                push=False,
                sdk_project_root=_default_sdk_project_root(),
                prebuilt_sdist=prebuilt_sdist,
            )
        )

    assert prebuilt_sdist.exists()
    assert len(docker_calls) == 2
    assert first_tags != second_tags


def test_parse_buildkit_telemetry_extracts_phase_timings():
    from openhands.agent_server.docker.build import _parse_buildkit_telemetry

    telemetry = _parse_buildkit_telemetry(BUILDKIT_STDERR_SAMPLE)

    assert telemetry.cache_import_seconds == 35.7
    assert telemetry.cache_import_miss_count == 1
    assert telemetry.cache_export_seconds == 264.3
    assert telemetry.image_export_seconds == 142.8
    assert telemetry.push_layers_seconds == 35.9
    assert telemetry.export_manifest_seconds == 3.7
    assert telemetry.cached_step_count == 1


def test_parse_buildkit_telemetry_cache_export_with_preparing_line():
    """测试当子操作出现时是否捕获缓存导出时间。

    这会重现 BuildKit 输出的错误：
        #33 正在将缓存导出到注册表
        #33 准备导出构建缓存
        #33 DONE 36.2s

    之前，第二行覆盖了 step_descriptions["33"]，导致 DONE 时间被归因于“准备导出缓存”
    这一项，而这一项并未被分类为
    cache_export。

    修复确保了一旦步骤有一个分类描述（“导出缓存到注册表” -> cache_export），后续子操
    作描述不会覆盖它。
    """
    from openhands.agent_server.docker.build import _parse_buildkit_telemetry

    # 真实世界 BuildKit 输出模式
    stderr_with_preparing = "\n".join(
        [
            "#33 exporting cache to registry",
            "#33 preparing build cache for export",
            "#33 writing layer sha256:abc123 0.5s done",
            "#33 preparing build cache for export 36.2s done",
            "#33 DONE 36.2s",
            "",
        ]
    )

    telemetry = _parse_buildkit_telemetry(stderr_with_preparing)

    # 应捕获缓存导出时间，因为“将缓存导出到注册表”被保留为步骤描述（不会被“准备...”覆盖
    # ）
    #
    assert telemetry.cache_export_seconds == 36.2


def test_build_with_telemetry_returns_parsed_buildkit_fields(tmp_path: Path):
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build_with_telemetry,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        return subprocess.CompletedProcess(
            cmd, 0, stdout="ok", stderr=BUILDKIT_STDERR_SAMPLE
        )

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        image="ghcr.io/openhands/eval-agent-server",
        target="source-minimal",
        push=True,
        sdk_project_root=_default_sdk_project_root(),
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context", return_value=ctx
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build.time.monotonic",
            side_effect=[10.0, 13.25, 20.0, 45.5, 46.0, 46.2],
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        result = build_with_telemetry(opts)

    assert result.tags == opts.all_tags
    assert result.telemetry.build_context_seconds == 3.25
    assert result.telemetry.buildx_wall_clock_seconds == 25.5
    assert result.telemetry.cleanup_seconds == 0.2
    assert result.telemetry.cache_import_seconds == 35.7
    assert result.telemetry.cache_export_seconds == 264.3
    assert result.telemetry.image_export_seconds == 142.8
    assert result.telemetry.push_layers_seconds == 35.9
    assert result.telemetry.export_manifest_seconds == 3.7
    assert result.telemetry.cache_import_miss_count == 1
    assert result.telemetry.cached_step_count == 1


def test_build_with_telemetry_preserves_telemetry_on_failure(tmp_path: Path):
    import pytest

    from openhands.agent_server.docker.build import (
        BuildCommandError,
        BuildOptions,
        _default_sdk_project_root,
        build_with_telemetry,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        raise subprocess.CalledProcessError(
            1,
            cmd,
            output="stdout failure",
            stderr=BUILDKIT_STDERR_SAMPLE,
        )

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        image="ghcr.io/openhands/eval-agent-server",
        target="source-minimal",
        push=True,
        sdk_project_root=_default_sdk_project_root(),
    )

    with (
        patch(
            "openhands.agent_server.docker.build._make_build_context", return_value=ctx
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch(
            "openhands.agent_server.docker.build.time.monotonic",
            side_effect=[10.0, 13.25, 20.0, 45.5, 46.0, 46.2],
        ),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
        pytest.raises(BuildCommandError) as excinfo,
    ):
        build_with_telemetry(opts)

    assert excinfo.value.telemetry.build_context_seconds == 3.25
    assert excinfo.value.telemetry.buildx_wall_clock_seconds == 25.5
    assert excinfo.value.telemetry.cache_export_seconds == 264.3
    assert excinfo.value.telemetry.cache_import_miss_count == 1


@pytest.mark.parametrize(
    "mode,expect_cache_to,expect_mode_value",
    [
        ("off", False, None),
        ("max", True, "max"),
        ("min", True, "min"),
        ("invalid", True, "max"),  # 无效值默认为“max”（保留行为）
    ],
)
def test_cache_export_modes(
    tmp_path: Path,
    mode: str,
    expect_cache_to: bool,
    expect_mode_value: str | None,
):
    """测试不同 OPENHANDS_BUILDKIT_CACHE_MODE 值的缓存导出行为。"""
    from openhands.agent_server.docker.build import (
        BuildOptions,
        _default_sdk_project_root,
        build,
    )

    ctx = tmp_path / "ctx"
    ctx.mkdir()
    docker_calls: list[tuple[list[str], str | None]] = []

    def fake_run(cmd: list[str], cwd: str | None = None):
        if cmd[:3] != ["docker", "buildx", "build"]:
            raise AssertionError(f"unexpected command: {cmd}")
        docker_calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    opts = BuildOptions(
        base_image="python:3.12",
        custom_tags="python",
        git_sha="abc1234567890",
        git_ref="refs/heads/main",
        image="ghcr.io/openhands/eval-agent-server",
        target="source-minimal",
        push=True,
        sdk_project_root=_default_sdk_project_root(),
    )

    with (
        patch.dict(os.environ, {"OPENHANDS_BUILDKIT_CACHE_MODE": mode}, clear=False),
        patch(
            "openhands.agent_server.docker.build._make_build_context",
            return_value=ctx,
        ),
        patch("openhands.agent_server.docker.build._run", side_effect=fake_run),
        patch("openhands.agent_server.docker.build.shutil.rmtree"),
    ):
        build(opts)

    cmd = docker_calls[0][0]
    cmd_str = " ".join(cmd)

    # 应该总是有 --cache-from
    assert "--cache-from" in cmd_str

    if expect_cache_to:
        assert "--cache-to" in cmd_str
        assert f"mode={expect_mode_value}" in cmd_str
    else:
        assert "--cache-to" not in cmd_str
