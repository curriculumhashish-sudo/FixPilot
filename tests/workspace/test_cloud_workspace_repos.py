"""OpenHandsCloudWorkspace 中存储库克隆和技能加载测试。"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 从 SDK 存储库模块导入（云工作区重新导出这些）
from openhands.sdk.workspace.repo import (
    CloneResult,
    GitProvider,
    RepoMapping,
    RepoSource,
    _build_clone_url,
    _detect_provider_from_url,
    _extract_repo_name,
    _get_unique_dir_name,
    _is_commit_sha,
    _sanitize_dir_name,
    clone_repos,
    get_repos_context,
)


class TestRepoSource:
    """测试 RepoSource 模型。"""

    # --- 短 URL 格式（需要提供商）---

    def test_short_url_with_provider(self):
        """使用短 URL 和显式提供程序测试 RepoSource。"""
        repo = RepoSource(url="owner/repo", provider="github")
        assert repo.url == "owner/repo"
        assert repo.provider == "github"
        assert repo.get_provider() == GitProvider.GITHUB

    def test_short_url_with_ref_and_provider(self):
        """使用短 URL、引用和提供者测试 RepoSource。"""
        repo = RepoSource(url="owner/repo", ref="main", provider="gitlab")
        assert repo.url == "owner/repo"
        assert repo.ref == "main"
        assert repo.get_provider() == GitProvider.GITLAB

    def test_short_url_without_provider_rejected(self):
        """测试没有提供者的短 URL 被拒绝。"""
        with pytest.raises(ValueError, match="requires explicit 'provider' field"):
            RepoSource(url="owner/repo")

    def test_short_url_string_without_provider_rejected(self):
        """测试没有提供者的字符串输入是否被拒绝。"""
        with pytest.raises(ValueError, match="requires explicit 'provider' field"):
            RepoSource.model_validate("owner/repo")

    def test_short_url_dict_without_provider_rejected(self):
        """测试没有提供者的字典输入被拒绝。"""
        with pytest.raises(ValueError, match="requires explicit 'provider' field"):
            RepoSource.model_validate({"url": "owner/repo", "ref": "v1.0"})

    # --- 完整 URL 格式（自动检测提供商）---

    def test_full_https_url_github(self):
        """使用完整的 GitHub HTTPS URL 测试 RepoSource。"""
        repo = RepoSource(url="https://github.com/owner/repo")
        assert repo.url == "https://github.com/owner/repo"
        assert repo.provider is None
        assert repo.get_provider() == GitProvider.GITHUB

    def test_full_https_url_gitlab(self):
        """使用完整的 GitLab HTTPS URL 测试 RepoSource。"""
        repo = RepoSource(url="https://gitlab.com/owner/repo")
        assert repo.provider is None
        assert repo.get_provider() == GitProvider.GITLAB

    def test_full_https_url_bitbucket(self):
        """测试 RepoSource 与 Bitbucket HTTPS URL 全部。"""
        repo = RepoSource(url="https://bitbucket.org/owner/repo")
        assert repo.provider is None
        assert repo.get_provider() == GitProvider.BITBUCKET

    def test_full_https_url_azure_devops(self):
        """使用完整的 Azure DevOps HTTPS URL 测试 RepoSource。"""
        repo = RepoSource(url="https://dev.azure.com/org/project/_git/repo")
        assert repo.provider is None
        assert repo.get_provider() == GitProvider.AZURE_DEVOPS

    def test_azure_devops_clone_dialog_url(self):
        """URL Azure DevOps 在其“克隆”对话框中显示组织名称。"""
        repo = RepoSource(url="https://org@dev.azure.com/org/project/_git/repo")
        assert repo.get_provider() == GitProvider.AZURE_DEVOPS

    def test_azure_devops_legacy_host(self):
        """{org} 上的组织。visualstudio.com也是 Azure DevOps。"""
        repo = RepoSource(url="https://org.visualstudio.com/project/_git/repo")
        assert repo.get_provider() == GitProvider.AZURE_DEVOPS

    def test_git_ssh_url(self):
        """使用 git SSH URL 测试 RepoSource（包含 github.com）。"""
        repo = RepoSource(url="git@github.com:owner/repo.git")
        assert repo.url == "git@github.com:owner/repo.git"
        assert repo.get_provider() == GitProvider.GITHUB

    # --- 提供者字段行为 ---

    def test_provider_explicit_overrides_detection(self):
        """测试是否使用了显式提供程序，即使使用完整的 URL。"""
        # 用户明确地说 GitLab，即使 URL 是 GitHub 这可能是故意的（镜像等）
        #
        repo = RepoSource(url="https://github.com/owner/repo", provider="gitlab")
        assert repo.get_provider() == GitProvider.GITLAB

    def test_provider_github_token_name(self):
        """测试 GitHub token 名称。"""
        repo = RepoSource(url="owner/repo", provider="github")
        assert repo.get_token_name() == "github_token"

    def test_provider_gitlab_token_name(self):
        """测试 GitLab token 名称。"""
        repo = RepoSource(url="owner/repo", provider="gitlab")
        assert repo.get_token_name() == "gitlab_token"

    def test_provider_bitbucket_token_name(self):
        """测试 Bitbucket token 名称。"""
        repo = RepoSource(url="owner/repo", provider="bitbucket")
        assert repo.get_token_name() == "bitbucket_token"

    def test_provider_azure_devops_token_name(self):
        """测试 Azure DevOps token 名称。"""
        repo = RepoSource(url="https://dev.azure.com/org/project/_git/repo")
        assert repo.get_token_name() == "azure_devops_token"

    def test_short_url_with_azure_devops_rejected(self):
        """Azure DevOps 需要 org/project/repo，因此 Owner/repo 被拒绝。"""
        with pytest.raises(ValueError, match="need a full URL"):
            RepoSource(url="owner/repo", provider="azure_devops")

    # --- URL 验证 ---

    def test_invalid_url_rejected(self):
        """测试无效的 URLs 被拒绝。"""
        with pytest.raises(ValueError, match="URL must be"):
            RepoSource(url="invalid-url-format", provider="github")

    def test_url_with_dots_allowed(self):
        """URLs 中包含 repo 名称中的点。"""
        repo = RepoSource(url="owner/repo.name", provider="github")
        assert repo.url == "owner/repo.name"

    def test_url_with_dashes_allowed(self):
        """测试 URLs 中带有下划线的字符是否被允许。"""
        repo = RepoSource(url="my-org/my-repo", provider="github")
        assert repo.url == "my-org/my-repo"

    def test_http_url_credentials_redacted_in_warning(self, caplog):
        """HTTP->HTTPS 规范化警告不得泄漏嵌入的信用。"""
        with caplog.at_level(logging.WARNING):
            repo = RepoSource(url="http://oauth2:SUPERSECRET@github.com/owner/repo.git")
        # 凭据永远不会到达日志...
        assert "SUPERSECRET" not in caplog.text
        assert "oauth2" not in caplog.text
        assert "Converting HTTP URL to HTTPS" in caplog.text
        assert "http://****@github.com/owner/repo.git" in caplog.text
        # ...but normalization still happens on the stored value.
        assert repo.url == "https://oauth2:SUPERSECRET@github.com/owner/repo.git"


class TestProviderDetection:
    """从 URLs 进行提供商检测的测试。"""

    def test_detect_github(self):
        assert _detect_provider_from_url("https://github.com/o/r") == GitProvider.GITHUB

    def test_detect_gitlab(self):
        assert _detect_provider_from_url("https://gitlab.com/o/r") == GitProvider.GITLAB

    def test_detect_bitbucket(self):
        assert (
            _detect_provider_from_url("https://bitbucket.org/o/r")
            == GitProvider.BITBUCKET
        )

    def test_detect_azure_devops(self):
        assert (
            _detect_provider_from_url("https://dev.azure.com/o/p/_git/r")
            == GitProvider.AZURE_DEVOPS
        )
        # 克隆对话框 URL 将组织命名为用户。
        assert (
            _detect_provider_from_url("https://o@dev.azure.com/o/p/_git/r")
            == GitProvider.AZURE_DEVOPS
        )
        assert (
            _detect_provider_from_url("https://o.visualstudio.com/p/_git/r")
            == GitProvider.AZURE_DEVOPS
        )

    def test_detect_unknown(self):
        assert _detect_provider_from_url("https://example.com/o/r") is None
        assert _detect_provider_from_url("owner/repo") is None
        assert _detect_provider_from_url("https://visualstudio.com/p/_git/r") is None
        assert _detect_provider_from_url("https://dev.azure.com.evil.com/o/p") is None
        assert _detect_provider_from_url("https://x.visualstudio.com.evil.com") is None


class TestHelperFunctions:
    """测试 repo 模块中的辅助函数。"""

    def test_is_commit_sha_valid(self):
        """检测有效的提交 SHAs。"""
        assert _is_commit_sha("abc1234") is True
        assert (
            _is_commit_sha("abc1234567890abcdef1234567890abcdef12") is True
        )  # 40 个字符
        assert _is_commit_sha("ABC1234") is True  # 不区分大小写

    def test_is_commit_sha_invalid(self):
        """检测无效提交 SHAs。"""
        assert _is_commit_sha(None) is False
        assert _is_commit_sha("main") is False
        assert _is_commit_sha("v1.0.0") is False
        assert _is_commit_sha("abc123") is False  # 太短
        assert _is_commit_sha("xyz1234") is False  # 无效的十六进制字符

    def test_extract_repo_name_owner_repo(self):
        """测试从所有者/存储库格式中提取存储库名称。"""
        assert _extract_repo_name("owner/repo") == "repo"
        assert _extract_repo_name("my-org/my-repo") == "my-repo"

    def test_extract_repo_name_https_url(self):
        """HTTPS URLs 中提取仓库名称。"""
        assert _extract_repo_name("https://github.com/owner/repo") == "repo"
        assert _extract_repo_name("https://github.com/owner/repo.git") == "repo"
        assert _extract_repo_name("https://gitlab.com/owner/repo") == "repo"

    def test_extract_repo_name_azure_devops_url(self):
        """测试从Azure中提取仓库名称 DevOps URLs。"""
        assert _extract_repo_name("https://dev.azure.com/o/p/_git/repo") == "repo"
        assert _extract_repo_name("https://o@dev.azure.com/o/p/_git/repo") == "repo"

    def test_extract_repo_name_windows_file_url(self):
        """测试从Windows文件中提取仓库名称 URLs。"""
        assert _extract_repo_name(r"file://C:\Users\user\work\repo") == "repo"

    def test_extract_repo_name_ssh_url(self):
        """SSH URLs 中提取仓库名称。"""
        assert _extract_repo_name("git@github.com:owner/repo.git") == "repo"
        assert _extract_repo_name("git@gitlab.com:owner/repo") == "repo"

    def test_sanitize_dir_name(self):
        """测试目录名称清理。"""
        assert _sanitize_dir_name("repo") == "repo"
        assert _sanitize_dir_name("my-repo") == "my-repo"
        assert _sanitize_dir_name("my.repo") == "my.repo"
        assert _sanitize_dir_name("repo/name") == "repo_name"  # 无效字符
        assert _sanitize_dir_name("...repo...") == "repo"  # 修剪点
        assert _sanitize_dir_name("") == "repo"  # 空->默认

    def test_get_unique_dir_name(self):
        """测试唯一目录名称生成。"""
        existing: set[str] = set()
        assert _get_unique_dir_name("repo", existing) == "repo"

        existing = {"repo"}
        assert _get_unique_dir_name("repo", existing) == "repo_1"

        existing = {"repo", "repo_1", "repo_2"}
        assert _get_unique_dir_name("repo", existing) == "repo_3"

    def test_build_clone_url_github_owner_repo_no_token(self):
        """测试从所有者/存储库构建克隆 URL，而不使用 token。"""
        url = _build_clone_url("owner/repo", GitProvider.GITHUB, None)
        assert url == "https://github.com/owner/repo.git"

    def test_build_clone_url_github_owner_repo_with_token(self):
        """使用 GitHub token 测试从所有者/存储库构建克隆 URL。"""
        url = _build_clone_url("owner/repo", GitProvider.GITHUB, "ghtoken123")
        assert url == "https://ghtoken123@github.com/owner/repo.git"

    def test_build_clone_url_github_https_with_token(self):
        """测试从 GitHub HTTPS URL 和 token 构建克隆 URL。"""
        url = _build_clone_url(
            "https://github.com/owner/repo", GitProvider.GITHUB, "ghtoken123"
        )
        assert url == "https://ghtoken123@github.com/owner/repo"

    def test_build_clone_url_gitlab_owner_repo_with_token(self):
        """使用 token 测试从所有者/存储库为 GitLab 构建克隆 URL。"""
        url = _build_clone_url("owner/repo", GitProvider.GITLAB, "gltoken123")
        assert url == "https://oauth2:gltoken123@gitlab.com/owner/repo.git"

    def test_build_clone_url_gitlab_https_with_token(self):
        """使用 token 测试从 GitLab URL 构建克隆 URL。"""
        url = _build_clone_url(
            "https://gitlab.com/owner/repo", GitProvider.GITLAB, "gltoken123"
        )
        assert url == "https://oauth2:gltoken123@gitlab.com/owner/repo"

    def test_build_clone_url_bitbucket_with_token(self):
        """使用 token 测试为 Bitbucket 构建克隆 URL。"""
        url = _build_clone_url("owner/repo", GitProvider.BITBUCKET, "bbtoken123")
        assert url == "https://x-token-auth:bbtoken123@bitbucket.org/owner/repo.git"

    def test_build_clone_url_no_token_passthrough(self):
        """测试完整 URLs without token 不变地通过。"""
        url = _build_clone_url(
            "https://github.com/owner/repo", GitProvider.GITHUB, None
        )
        assert url == "https://github.com/owner/repo"

    def test_build_clone_url_self_hosted_gitlab_with_explicit_provider(self):
        """当提供程序显式时，自托管 GitLab 主机将获取 token。"""
        url = _build_clone_url(
            "https://gitlab.mycompany.com/owner/repo",
            GitProvider.GITLAB,
            "gltoken123",
            explicit_provider=True,
        )
        assert url == "https://oauth2:gltoken123@gitlab.mycompany.com/owner/repo"

    def test_build_clone_url_self_hosted_host_without_explicit_provider(self):
        """自动检测的提供程序不得将 token 注入不相关的主机。"""
        url = _build_clone_url(
            "https://gitlab.mycompany.com/owner/repo",
            GitProvider.GITLAB,
            "gltoken123",
            explicit_provider=False,
        )
        assert url == "https://gitlab.mycompany.com/owner/repo"

    @pytest.mark.parametrize("explicit_provider", [False, True])
    def test_build_clone_url_lookalike_host_not_injected(self, explicit_provider):
        """公共主机的相似者永远不会收到 token。"""
        url = _build_clone_url(
            "https://github.com.evil.com/owner/repo",
            GitProvider.GITHUB,
            "ghtoken123",
            explicit_provider=explicit_provider,
        )
        assert url == "https://github.com.evil.com/owner/repo"

    def test_build_clone_url_self_hosted_host_is_normalized(self):
        """主机案例和非默认端口在 token 注入中幸存。"""
        url = _build_clone_url(
            "https://GitLab.MyCompany.com:8443/owner/repo",
            GitProvider.GITLAB,
            "gltoken123",
            explicit_provider=True,
        )
        assert url == "https://oauth2:gltoken123@gitlab.mycompany.com:8443/owner/repo"

    def test_build_clone_url_existing_credentials_preserved(self):
        """已经携带凭据的 URL 保留其自己的。"""
        url = _build_clone_url(
            "https://oauth2:embedded@gitlab.mycompany.com/owner/repo",
            GitProvider.GITLAB,
            "gltoken123",
            explicit_provider=True,
        )
        assert url == "https://oauth2:embedded@gitlab.mycompany.com/owner/repo"

    def test_build_clone_url_user_only_url_gets_token_as_password(self):
        """仅命名用户的 URL 保留它并获取 token 作为其密码。"""
        url = _build_clone_url(
            "https://someone@github.com/owner/repo", GitProvider.GITHUB, "ghtoken123"
        )
        assert url == "https://someone:ghtoken123@github.com/owner/repo"

    def test_build_clone_url_azure_devops_with_token(self):
        """使用 token 测试为 Azure DevOps 构建克隆 URL。"""
        url = _build_clone_url(
            "https://dev.azure.com/org/project/_git/repo",
            GitProvider.AZURE_DEVOPS,
            "adotoken",
        )
        assert url == "https://oauth2:adotoken@dev.azure.com/org/project/_git/repo"

    def test_build_clone_url_azure_devops_keeps_organization_user(self):
        """克隆对话框的组织用户保留，密码为 token。"""
        url = _build_clone_url(
            "https://org@dev.azure.com/org/project/_git/repo",
            GitProvider.AZURE_DEVOPS,
            "adotoken",
        )
        assert url == "https://org:adotoken@dev.azure.com/org/project/_git/repo"

    def test_build_clone_url_azure_devops_legacy_host(self):
        """一个{org}。visualstudio.com主机是 Azure DevOps 自己的并获取 token。"""
        url = _build_clone_url(
            "https://org.visualstudio.com/project/_git/repo",
            GitProvider.AZURE_DEVOPS,
            "adotoken",
        )
        assert url == "https://oauth2:adotoken@org.visualstudio.com/project/_git/repo"

    @pytest.mark.parametrize(
        "url",
        [
            "https://dev.azure.com.evil.com/org/project/_git/repo",
            "https://org.visualstudio.com.evil.com/project/_git/repo",
        ],
    )
    @pytest.mark.parametrize("explicit_provider", [False, True])
    def test_build_clone_url_azure_devops_lookalike_not_injected(
        self, url, explicit_provider
    ):
        """任何 Azure DevOps 主机的相似者都不会收到 token。"""
        assert (
            _build_clone_url(
                url,
                GitProvider.AZURE_DEVOPS,
                "adotoken",
                explicit_provider=explicit_provider,
            )
            == url
        )


class TestGetReposContext:
    """测试 get_repos_context 功能。"""

    def test_empty_mappings(self):
        """测试空映射是否返回空字符串。"""
        assert get_repos_context({}) == ""

    def test_single_repo(self):
        """测试单个存储库的上下文生成。"""
        mappings = {
            "owner/repo": RepoMapping(
                url="owner/repo",
                dir_name="repo",
                local_path="/workspace/project/repo",
                ref=None,
            )
        }
        context = get_repos_context(mappings)
        assert "## Cloned Repositories" in context
        assert "`owner/repo`" in context
        assert "`/workspace/project/repo/`" in context

    def test_repo_with_ref(self):
        """使用 ref 测试存储库的上下文生成。"""
        mappings = {
            "owner/repo": RepoMapping(
                url="owner/repo",
                dir_name="repo",
                local_path="/workspace/project/repo",
                ref="main",
            )
        }
        context = get_repos_context(mappings)
        assert "(ref: main)" in context

    def test_multiple_repos(self):
        """测试多个存储库的上下文生成。"""
        mappings = {
            "owner/repo1": RepoMapping(
                url="owner/repo1",
                dir_name="repo1",
                local_path="/workspace/project/repo1",
                ref=None,
            ),
            "owner/repo2": RepoMapping(
                url="owner/repo2",
                dir_name="repo2",
                local_path="/workspace/project/repo2",
                ref="v1.0",
            ),
        }
        context = get_repos_context(mappings)
        assert "`owner/repo1`" in context
        assert "`owner/repo2`" in context
        assert "(ref: v1.0)" in context


class TestCloneRepos:
    """测试 clone_repos 功能。"""

    def test_empty_repos_list(self):
        """使用空存储库列表测试克隆。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = clone_repos([], Path(tmpdir))
            assert result.success_count == 0
            assert result.failed_repos == []
            assert result.repo_mappings == {}

    @patch("subprocess.run")
    def test_successful_clone(self, mock_run):
        """测试成功的存储库克隆。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="owner/repo", provider="github")]
            result = clone_repos(repos, Path(tmpdir))

            assert result.success_count == 1
            assert result.failed_repos == []
            assert "owner/repo" in result.repo_mappings
            assert result.repo_mappings["owner/repo"].dir_name == "repo"

    @patch("subprocess.run")
    def test_successful_clone_full_url(self, mock_run):
        """使用完整的 URL 测试成功的克隆（无需提供程序）。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="https://github.com/owner/repo")]
            result = clone_repos(repos, Path(tmpdir))

            assert result.success_count == 1
            assert "https://github.com/owner/repo" in result.repo_mappings

    @patch("subprocess.run")
    def test_clone_with_sha_ref(self, mock_run):
        """使用 SHA ref 测试克隆（需要完整克隆 + 签出）。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="owner/repo", ref="abc1234567", provider="github")]
            clone_repos(repos, Path(tmpdir))

            # 应该被调用两次：克隆+结账
            assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_clone_failure(self, mock_run):
        """测试克隆失败的处理。"""
        mock_run.return_value = MagicMock(returncode=1, stderr="Clone failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="owner/repo", provider="github")]
            result = clone_repos(repos, Path(tmpdir))

            assert result.success_count == 0
            assert len(result.failed_repos) == 1
            assert result.repo_mappings == {}

    @patch("subprocess.run")
    def test_clone_failure_redacts_credentials_in_stderr(self, mock_run, caplog):
        """失败的克隆不得泄漏 stderr 中回显的身份验证令牌。"""
        token = "ghp_supersecrettoken"
        # git often echoes the authenticated remote URL back in stderr on failure.
        leaky_stderr = (
            f"fatal: Authentication failed for "
            f"'https://{token}@github.com/owner/repo.git/'"
        )
        mock_run.return_value = MagicMock(returncode=1, stderr=leaky_stderr)

        def token_fetcher(name: str) -> str | None:
            return token if name == "github_token" else None

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="owner/repo", provider="github")]
            with caplog.at_level(logging.WARNING):
                result = clone_repos(repos, Path(tmpdir), token_fetcher=token_fetcher)

        assert result.success_count == 0
        assert token not in caplog.text
        assert "[clone] Failed:" in caplog.text
        assert "https://****@github.com/owner/repo.git" in caplog.text

    @patch("subprocess.run")
    def test_clone_with_token_fetcher(self, mock_run):
        """使用 token fetcher 回调测试克隆。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        def token_fetcher(name: str) -> str | None:
            if name == "github_token":
                return "ghtoken123"
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="owner/repo", provider="github")]
            clone_repos(
                repos,
                Path(tmpdir),
                token_fetcher=token_fetcher,
            )

            # 检查 token 是否包含在克隆 URL 中
            call_args = mock_run.call_args[0][0]
            assert any("ghtoken123" in str(arg) for arg in call_args)

    @patch("subprocess.run")
    def test_clone_with_provider_specific_token(self, mock_run):
        """测试克隆根据提供程序获取正确的 token。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        fetched_tokens = []

        def token_fetcher(name: str) -> str | None:
            fetched_tokens.append(name)
            return f"token_for_{name}"

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [
                RepoSource(url="owner/repo1", provider="github"),
                RepoSource(url="owner/repo2", provider="gitlab"),
            ]
            clone_repos(repos, Path(tmpdir), token_fetcher=token_fetcher)

            # 应该获取 github_token 和 gitlab_token
            assert "github_token" in fetched_tokens
            assert "gitlab_token" in fetched_tokens

    @patch("subprocess.run")
    def test_clone_self_hosted_gitlab_with_token(self, mock_run):
        """自托管 GitLab 实例通过 token 进行身份验证进行克隆，
        而不是默默地发送未经身份验证的请求。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        def token_fetcher(name: str) -> str | None:
            return "gltoken123" if name == "gitlab_token" else None

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [
                RepoSource(
                    url="https://gitlab.mycompany.com/owner/repo",
                    provider="gitlab",
                )
            ]
            clone_repos(repos, Path(tmpdir), token_fetcher=token_fetcher)

            call_args = mock_run.call_args[0][0]
            assert any(
                "oauth2:gltoken123@gitlab.mycompany.com" in str(arg)
                for arg in call_args
            )

    @patch("subprocess.run")
    def test_clone_azure_devops_with_token(self, mock_run):
        """Azure DevOps 存储库克隆了 azure_devops_token。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        def token_fetcher(name: str) -> str | None:
            return "adotoken" if name == "azure_devops_token" else None

        with tempfile.TemporaryDirectory() as tmpdir:
            repos = [RepoSource(url="https://dev.azure.com/org/project/_git/repo")]
            result = clone_repos(repos, Path(tmpdir), token_fetcher=token_fetcher)

            assert result.success_count == 1
            assert result.repo_mappings[repos[0].url].dir_name == "repo"
            call_args = mock_run.call_args[0][0]
            assert any(
                "oauth2:adotoken@dev.azure.com/org/project/_git/repo" in str(arg)
                for arg in call_args
            )

    @patch("subprocess.run")
    def test_directory_name_collision(self, mock_run):
        """测试目录名称冲突的处理。"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            # 两个同名的仓库应该有唯一的目录
            repos = [
                RepoSource(url="owner1/utils", provider="github"),
                RepoSource(url="owner2/utils", provider="github"),
            ]
            result = clone_repos(repos, Path(tmpdir))

            dir_names = [m.dir_name for m in result.repo_mappings.values()]
            assert "utils" in dir_names
            assert "utils_1" in dir_names


class TestCloudWorkspaceRepoMethods:
    """测试 OpenHandsCloudWorkspace 存储库方法。"""

    @patch("openhands.sdk.workspace.remote.base._clone_repos_helper")
    @patch.object(
        __import__(
            "openhands.workspace.cloud.workspace", fromlist=["OpenHandsCloudWorkspace"]
        ).OpenHandsCloudWorkspace,
        "_get_secret_value",
        return_value=None,
    )
    def test_clone_repos_full_url_list(self, mock_secret, mock_clone):
        """使用完整的 URL 字符串列表测试 clone_repos。"""
        from openhands.workspace import OpenHandsCloudWorkspace

        mock_clone.return_value = CloneResult(0, [], {})

        with patch.object(
            OpenHandsCloudWorkspace, "model_post_init", lambda self, ctx: None
        ):
            workspace = OpenHandsCloudWorkspace(
                cloud_api_url="https://test.com",
                cloud_api_key="test-key",
                local_agent_server_mode=True,
            )
            workspace._sandbox_id = "test-sandbox"
            workspace._session_api_key = "test-session"
            workspace.working_dir = "/workspace/project"

            # URLs 全部不需要提供方
            workspace.clone_repos(
                [
                    "https://github.com/owner/repo1",
                    "https://github.com/owner/repo2",
                ]
            )

            mock_clone.assert_called_once()
            call_args = mock_clone.call_args
            repos = call_args.kwargs["repos"]
            assert len(repos) == 2
            assert all(isinstance(r, RepoSource) for r in repos)

    @patch("openhands.sdk.workspace.remote.base._clone_repos_helper")
    @patch.object(
        __import__(
            "openhands.workspace.cloud.workspace", fromlist=["OpenHandsCloudWorkspace"]
        ).OpenHandsCloudWorkspace,
        "_get_secret_value",
        return_value=None,
    )
    def test_clone_repos_dict_list(self, mock_secret, mock_clone):
        """使用字典列表测试 clone_repos。"""
        from openhands.workspace import OpenHandsCloudWorkspace

        mock_clone.return_value = CloneResult(0, [], {})

        with patch.object(
            OpenHandsCloudWorkspace, "model_post_init", lambda self, ctx: None
        ):
            workspace = OpenHandsCloudWorkspace(
                cloud_api_url="https://test.com",
                cloud_api_key="test-key",
                local_agent_server_mode=True,
            )
            workspace._sandbox_id = "test-sandbox"
            workspace._session_api_key = "test-session"
            workspace.working_dir = "/workspace/project"

            # 短URL，指定提供者
            workspace.clone_repos(
                [{"url": "owner/repo", "ref": "main", "provider": "github"}]
            )

            mock_clone.assert_called_once()
            call_args = mock_clone.call_args
            repos = call_args.kwargs["repos"]
            assert len(repos) == 1
            assert repos[0].url == "owner/repo"
            assert repos[0].ref == "main"
            assert repos[0].provider == "github"

    def test_get_repos_context_from_mappings(self):
        """使用显式映射测试 get_repos_context。"""
        from openhands.workspace import OpenHandsCloudWorkspace

        with patch.object(
            OpenHandsCloudWorkspace, "model_post_init", lambda self, ctx: None
        ):
            workspace = OpenHandsCloudWorkspace(
                cloud_api_url="https://test.com",
                cloud_api_key="test-key",
                local_agent_server_mode=True,
            )
            workspace.working_dir = "/workspace/project"

            mappings = {
                "owner/repo": RepoMapping(
                    url="owner/repo",
                    dir_name="repo",
                    local_path="/workspace/project/repo",
                    ref="main",
                )
            }

            context = workspace.get_repos_context(mappings)
            assert "## Cloned Repositories" in context
            assert "`owner/repo`" in context

    def test_load_skills_from_agent_server_preserves_base_context(self):
        """OpenHandsCloudWorkspace 覆盖必须转发 base_context 通过
        更改为 RemoteWorkspace，以便调用者配置的 AgentContext 字段得以保留。"""
        from openhands.sdk.context import AgentContext
        from openhands.workspace import OpenHandsCloudWorkspace

        with patch.object(
            OpenHandsCloudWorkspace, "model_post_init", lambda self, ctx: None
        ):
            workspace = OpenHandsCloudWorkspace(
                cloud_api_url="https://test.com",
                cloud_api_key="test-key",
                local_agent_server_mode=True,
            )
            workspace._sandbox_id = "test-sandbox"
            workspace._session_api_key = "test-session"
            workspace.working_dir = "/workspace/project"
            workspace.host = "http://localhost:8000"

            base_context = AgentContext(
                marketplace_path="internal/marketplace.json",
                disabled_skills=["risky-skill"],
            )

            with patch.object(
                workspace,
                "_call_skills_api",
                return_value=[{"name": "test-skill", "content": "Test content"}],
            ):
                skills, context = workspace.load_skills_from_agent_server(
                    base_context=base_context
                )

            assert len(skills) == 1
            assert context.marketplace_path == "internal/marketplace.json"
            assert context.disabled_skills == ["risky-skill"]
            assert context.load_public_skills is False


class TestCloneReposIntegration:
    """集成测试 for clone_repos 使用真正的 git 操作。

    这些测试练习实际的 git 克隆行为而不是模拟子进程。 使用小型本地 git 存储库作为测试
    夹具以避免网络依赖。
    """

    @pytest.fixture
    def local_git_repo(self, tmp_path):
        """创建一个最小的本地 git 存储库用于测试。"""
        import subprocess

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # 初始化 git 仓库
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        # 创建文件并提交
        (repo_dir / "README.md").write_text("# Test Repo")
        subprocess.run(
            ["git", "add", "README.md"], cwd=repo_dir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )

        # 创建标签
        subprocess.run(
            ["git", "tag", "v1.0.0"], cwd=repo_dir, capture_output=True, check=True
        )

        # 获取提交 SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_sha = result.stdout.strip()

        return {"path": repo_dir, "sha": commit_sha}

    def test_clone_local_repo(self, local_git_repo, tmp_path):
        """测试克隆本地 git 存储库。"""
        target_dir = tmp_path / "cloned"
        repo_url = f"file://{local_git_repo['path']}"

        repos = [RepoSource(url=repo_url)]
        result = clone_repos(repos, target_dir)

        assert result.success_count == 1
        assert len(result.failed_repos) == 0
        assert repo_url in result.repo_mappings

        # 验证存储库确实已克隆
        cloned_path = Path(result.repo_mappings[repo_url].local_path)
        assert cloned_path.exists()
        assert (cloned_path / "README.md").exists()
        assert (cloned_path / "README.md").read_text() == "# Test Repo"

    def test_clone_with_tag_ref(self, local_git_repo, tmp_path):
        """使用特定标签引用测试克隆。"""
        import subprocess

        target_dir = tmp_path / "cloned"
        repo_url = f"file://{local_git_repo['path']}"

        repos = [RepoSource(url=repo_url, ref="v1.0.0")]
        result = clone_repos(repos, target_dir)

        assert result.success_count == 1
        cloned_path = Path(result.repo_mappings[repo_url].local_path)
        assert cloned_path.exists()

        # 验证标签确实已签出
        tag_result = subprocess.run(
            ["git", "-C", str(cloned_path), "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert tag_result.stdout.strip() == "v1.0.0"

    def test_clone_with_sha_ref(self, local_git_repo, tmp_path):
        """使用特定提交测试克隆 SHA。"""
        import subprocess

        target_dir = tmp_path / "cloned"
        repo_url = f"file://{local_git_repo['path']}"
        sha = local_git_repo["sha"]

        repos = [RepoSource(url=repo_url, ref=sha)]
        result = clone_repos(repos, target_dir)

        assert result.success_count == 1
        cloned_path = Path(result.repo_mappings[repo_url].local_path)
        assert cloned_path.exists()

        # 验证 SHA 确实已签出
        sha_result = subprocess.run(
            ["git", "-C", str(cloned_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert sha_result.stdout.strip() == sha

    def test_clone_invalid_url_fails(self, tmp_path):
        """测试无效的 URLs 被妥善处理。"""
        target_dir = tmp_path / "cloned"

        repos = [RepoSource(url="file:///nonexistent/repo")]
        result = clone_repos(repos, target_dir)

        assert result.success_count == 0
        assert len(result.failed_repos) == 1

    def test_clone_duplicate_urls_deduplicated(self, local_git_repo, tmp_path):
        """测试重复的 URLs 是否被去重。"""
        target_dir = tmp_path / "cloned"
        repo_url = f"file://{local_git_repo['path']}"

        # 两次相同的 URL
        repos = [RepoSource(url=repo_url), RepoSource(url=repo_url)]
        result = clone_repos(repos, target_dir)

        # 应该只克隆一次
        assert result.success_count == 1
        assert len(result.repo_mappings) == 1
