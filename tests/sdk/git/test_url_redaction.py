"""测试 URL 凭据脱敏实用程序。"""

import logging
import subprocess
import sys
from unittest.mock import patch

import pytest

from openhands.sdk.git.exceptions import GitCommandError
from openhands.sdk.git.utils import (
    get_git_repository_metadata,
    redact_url_credentials,
    run_git_command,
)  # 重新导出以兼容
from openhands.sdk.plugin.types import PluginSource, ResolvedPluginSource
from openhands.sdk.utils.redact import (
    redact_url_credentials as redact_url_credentials_central,
)


class TestRedactUrlCredentials:
    """测试 redact_url_credentials 功能。"""

    def test_https_with_oauth2_token(self):
        """HTTPS URLs 应该删除 oauth2 token。"""
        url = "https://oauth2:SECRET_TOKEN@gitlab.com/org/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@gitlab.com/org/repo.git"
        assert "SECRET_TOKEN" not in result

    def test_https_with_username_password(self):
        """HTTPS URLs 中应红帽用户名密码。"""
        url = "https://user:password123@github.com/owner/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@github.com/owner/repo.git"
        assert "user" not in result
        assert "password123" not in result

    def test_https_with_x_token_auth(self):
        """应编辑 x-token-auth 凭据（Bitbucket 样式）。"""
        url = "https://x-token-auth:MY_TOKEN@bitbucket.org/team/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@bitbucket.org/team/repo.git"
        assert "MY_TOKEN" not in result

    def test_https_with_just_token(self):
        """应编辑仅 token 的身份验证（GitHub PAT 样式）。"""
        url = "https://ghp_xxxxxxxxxxxx@github.com/owner/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@github.com/owner/repo.git"
        assert "ghp_xxxxxxxxxxxx" not in result

    def test_https_without_credentials(self):
        """在凭据之前不应修改URLs。"""
        url = "https://github.com/owner/repo.git"
        result = redact_url_credentials(url)
        assert result == url

    def test_http_with_credentials(self):
        """应在HTTP URLs中删除凭据。"""
        url = "http://user:pass@internal-git.company.com/repo.git"
        result = redact_url_credentials(url)
        assert result == "http://****@internal-git.company.com/repo.git"
        assert "user" not in result
        assert "pass" not in result

    def test_ssh_url_unchanged(self):
        """不应修改 SSH URLs （不得嵌入凭据）。"""
        url = "git@github.com:owner/repo.git"
        result = redact_url_credentials(url)
        assert result == url

    def test_ssh_gitlab_url_unchanged(self):
        """不应修改 GitLab SSH URLs。"""
        url = "git@gitlab.com:org/project.git"
        result = redact_url_credentials(url)
        assert result == url

    def test_local_path_unchanged(self):
        """不应修改本地路径。"""
        path = "/path/to/local/repo"
        result = redact_url_credentials(path)
        assert result == path

    def test_github_shorthand_unchanged(self):
        """不应修改 GitHub 速记格式（不应修改凭据）。"""
        source = "github:owner/repo"
        result = redact_url_credentials(source)
        assert result == source

    def test_preserves_port_in_url(self):
        """在 URLs 中保留端口号，在凭据中进行红帽处理。"""
        url = "https://user:pass@git.company.com:8443/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@git.company.com:8443/repo.git"
        assert "8443" in result
        assert "user" not in result

    def test_preserves_path_with_subdirectories(self):
        """应保留带有子目录的完整路径。"""
        url = "https://token@github.com/org/repo/tree/main/subdir"
        result = redact_url_credentials(url)
        assert result == "https://****@github.com/org/repo/tree/main/subdir"
        assert "/org/repo/tree/main/subdir" in result

    def test_empty_string(self):
        """应该处理空字符串。"""
        result = redact_url_credentials("")
        assert result == ""

    def test_special_characters_in_token(self):
        """应处理 token 中的特殊字符。"""
        # 凭据中的 URL 编码特殊字符
        url = "https://user%40domain:p%40ss%3Aword@github.com/repo.git"
        result = redact_url_credentials(url)
        assert result == "https://****@github.com/repo.git"
        assert "user%40domain" not in result

    def test_preserve_placeholders_keeps_var_reference(self):
        """${VAR} 用户信息不是机密，并且在被询问时必须保留。"""
        url = "https://x-token-auth:${MY_TOKEN}@host/repo.git"
        assert redact_url_credentials(url, preserve_placeholders=True) == url
        # 如果没有该标志，它会像任何其他用户信息一样被屏蔽。
        assert redact_url_credentials(url) == "https://****@host/repo.git"

    def test_preserve_placeholders_still_masks_inline_credentials(self):
        """preserve_placeholders仅备件${VAR}； 真正的内联信用被掩盖。"""
        url = "https://oauth2:SECRET@github.com/org/repo.git"
        result = redact_url_credentials(url, preserve_placeholders=True)
        assert result == "https://****@github.com/org/repo.git"
        assert "SECRET" not in result


class TestResolvedPluginSourceCredentialRedaction:
    """测试 ResolvedPluginSource 中的凭据脱敏。"""

    def test_from_plugin_source_redacts_credentials(self):
        """从 PluginSource 创建时应编辑凭据。"""
        plugin_source = PluginSource(
            source="https://oauth2:SECRET_TOKEN@gitlab.com/org/repo.git",
            ref="main",
        )
        resolved = ResolvedPluginSource.from_plugin_source(
            plugin_source, resolved_ref="abc123def456"
        )
        assert resolved.source == "https://****@gitlab.com/org/repo.git"
        assert "SECRET_TOKEN" not in resolved.source
        assert resolved.resolved_ref == "abc123def456"
        assert resolved.original_ref == "main"

    def test_from_plugin_source_preserves_url_without_credentials(self):
        """在凭据之前不应修改URLs。"""
        plugin_source = PluginSource(
            source="https://github.com/owner/repo.git",
            ref="v1.0.0",
        )
        resolved = ResolvedPluginSource.from_plugin_source(
            plugin_source, resolved_ref="abc123def456"
        )
        assert resolved.source == "https://github.com/owner/repo.git"
        assert resolved.resolved_ref == "abc123def456"

    def test_from_plugin_source_preserves_local_path(self):
        """不应修改本地路径。"""
        plugin_source = PluginSource(source="/path/to/local/plugin")
        resolved = ResolvedPluginSource.from_plugin_source(
            plugin_source, resolved_ref=None
        )
        assert resolved.source == "/path/to/local/plugin"
        assert resolved.resolved_ref is None

    def test_from_plugin_source_preserves_repo_path(self):
        """编辑凭据时应保留 repo_path。"""
        plugin_source = PluginSource(
            source="https://token@github.com/org/monorepo.git",
            ref="main",
            repo_path="plugins/my-plugin",
        )
        resolved = ResolvedPluginSource.from_plugin_source(
            plugin_source, resolved_ref="abc123"
        )
        assert resolved.source == "https://****@github.com/org/monorepo.git"
        assert resolved.repo_path == "plugins/my-plugin"

    def test_to_plugin_source_uses_redacted_url(self):
        """当转换回PluginSource时，应使用已脱敏URL。"""
        # 模拟从持久化加载的 ResolvedPluginSource
        resolved = ResolvedPluginSource(
            source="https://****@gitlab.com/org/repo.git",  # 已经已脱敏
            resolved_ref="abc123def456",
            repo_path=None,
            original_ref="main",
        )
        plugin_source = resolved.to_plugin_source()
        assert plugin_source.source == "https://****@gitlab.com/org/repo.git"
        assert plugin_source.ref == "abc123def456"  # 使用解析的参考，而不是原始的

    def test_serialization_does_not_expose_credentials(self):
        """确保 JSON 序列化不会暴露凭据。"""
        plugin_source = PluginSource(
            source="https://oauth2:SUPER_SECRET@gitlab.com/org/repo.git",
            ref="main",
        )
        resolved = ResolvedPluginSource.from_plugin_source(
            plugin_source, resolved_ref="abc123"
        )
        json_str = resolved.model_dump_json()
        assert "SUPER_SECRET" not in json_str
        assert "****" in json_str


class TestPluginSourceCredentialRedaction:
    """PluginSource.source 在序列化时间内嵌凭据掩码，同时
    将原始值保留在内存中以供获取/克隆并保留 ${VAR} 引用。"""

    CRED = "https://oauth2:SUPER_SECRET@gitlab.com/org/repo.git"
    REDACTED = "https://****@gitlab.com/org/repo.git"
    PLACEHOLDER = "https://x-token-auth:${MY_TOKEN}@host/repo.git"

    def test_default_dump_masks_only_the_credential(self):
        ps = PluginSource(source=self.CRED)
        # 保留 URL 形状（不是完整的 ********** 掩模）。
        assert ps.model_dump()["source"] == self.REDACTED
        assert "SUPER_SECRET" not in ps.model_dump_json()

    def test_in_memory_value_is_raw_for_fetch(self):
        # 该属性保留真实的 URL，因此插件仍然可以被克隆。
        assert PluginSource(source=self.CRED).source == self.CRED

    def test_placeholder_survives_dump(self):
        # ${VAR} 不是机密； 它在获取时从机密注册表扩展（包括。 服务器端），因此它必须在
        # 每次转储中都存在。
        #
        ps = PluginSource(source=self.PLACEHOLDER)
        assert ps.model_dump()["source"] == self.PLACEHOLDER
        assert ps.model_dump_json().count("${MY_TOKEN}") == 1

    @pytest.mark.parametrize(
        "source",
        [
            "github:owner/repo",
            "/path/to/local/plugin",
            "git@github.com:owner/repo.git",
            "https://github.com/owner/repo.git",
        ],
    )
    def test_non_credential_sources_unchanged(self, source):
        assert PluginSource(source=source).model_dump()["source"] == source

    def test_redacted_dump_round_trips(self):
        # 重新加载已脱敏转储不会引发； 源代码保持在已脱敏（内联凭证插件的恢复依赖于已解
        # 析的 SHA）。
        #
        dumped = PluginSource(source=self.CRED).model_dump()
        assert PluginSource.model_validate(dumped).source == self.REDACTED


class TestRedactUrlCredentialsCentralModule:
    """验证 redact_url_credentials 可以从中央编辑模块访问。"""

    def test_same_behaviour_as_git_utils(self):
        url = "https://oauth2:SECRET@gitlab.com/org/repo.git"
        assert redact_url_credentials(url) == redact_url_credentials_central(url)

    def test_importable_from_sdk_utils_redact(self):
        assert (
            redact_url_credentials_central("https://t@host/r") == "https://****@host/r"
        )


CREDENTIAL_URL = "https://oauth2:SUPERSECRET@github.com/o/r.git"
REDACTED_URL = "https://****@github.com/o/r.git"


class TestRunGitCommandCredentialRedaction:
    """凭据不得在任何错误路径上泄漏到 GitCommandError.command 中。"""

    def _args(self):
        return ["git", "clone", CREDENTIAL_URL, "/tmp/x"]

    def test_nonzero_returncode_redacts_command(self):
        completed = subprocess.CompletedProcess(
            args=self._args(), returncode=128, stdout="", stderr="fatal: repo not found"
        )
        with patch("subprocess.run", return_value=completed):
            with pytest.raises(GitCommandError) as exc_info:
                run_git_command(self._args())
        assert CREDENTIAL_URL not in exc_info.value.command
        assert REDACTED_URL in exc_info.value.command

    def test_nonzero_returncode_redacts_embedded_url(self):
        args = ["git", "check-ref-format", f"refs/heads/{CREDENTIAL_URL}"]
        completed = subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="invalid ref"
        )
        with patch("subprocess.run", return_value=completed):
            with pytest.raises(GitCommandError) as exc_info:
                run_git_command(args)
        assert all("SUPERSECRET" not in arg for arg in exc_info.value.command)
        assert f"refs/heads/{REDACTED_URL}" in exc_info.value.command

    def test_timeout_expired_redacts_command(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=self._args(), timeout=30),
        ):
            with pytest.raises(GitCommandError) as exc_info:
                run_git_command(self._args())
        assert CREDENTIAL_URL not in exc_info.value.command
        assert REDACTED_URL in exc_info.value.command

    def test_file_not_found_redacts_command(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitCommandError) as exc_info:
                run_git_command(["git-not-on-path", "clone", CREDENTIAL_URL, "/tmp/x"])
        assert CREDENTIAL_URL not in exc_info.value.command
        assert REDACTED_URL in exc_info.value.command

    def test_stderr_credentials_redacted_on_exception(self):
        """stderr 中回显的凭据不得泄漏到 GitCommandError.stderr 上。"""
        leaky_stderr = f"fatal: Authentication failed for '{CREDENTIAL_URL}/'"
        completed = subprocess.CompletedProcess(
            args=self._args(), returncode=128, stdout="", stderr=leaky_stderr
        )
        with patch("subprocess.run", return_value=completed):
            with pytest.raises(GitCommandError) as exc_info:
                run_git_command(self._args())
        assert "SUPERSECRET" not in exc_info.value.stderr
        assert REDACTED_URL in exc_info.value.stderr

    def test_stderr_credentials_redacted_in_error_log_by_default(self, caplog):
        """stderr 中回显的凭据不得泄漏到错误日志行中。"""
        leaky_stderr = f"fatal: Authentication failed for '{CREDENTIAL_URL}/'"
        completed = subprocess.CompletedProcess(
            args=self._args(), returncode=128, stdout="", stderr=leaky_stderr
        )
        with patch("subprocess.run", return_value=completed):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(GitCommandError):
                    run_git_command(self._args())
        assert "SUPERSECRET" not in caplog.text
        assert REDACTED_URL in caplog.text
        assert any(record.levelno == logging.ERROR for record in caplog.records)

    def test_expected_failure_is_logged_at_debug(self, caplog):
        completed = subprocess.CompletedProcess(
            args=self._args(), returncode=128, stdout="", stderr="fatal: repo not found"
        )
        with patch("subprocess.run", return_value=completed):
            with caplog.at_level(logging.DEBUG):
                with pytest.raises(GitCommandError):
                    run_git_command(self._args(), expected_failure=True)
        assert "Git command failed" in caplog.text
        assert all(record.levelno < logging.ERROR for record in caplog.records)


def test_run_git_command_replaces_undecodable_stdout_bytes():
    """无效编码标准输出不得引发 UnicodeDecodeError (AGE-1871)。"""
    result = run_git_command(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"],
        cwd=None,
        timeout=5,
    )
    assert result == "��"


def test_get_git_repository_metadata():
    responses = [
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="HTTPS://user:secret@github.com/org/repo.git\n",
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="abc123\nfeature-x\n",
            stderr="",
        ),
    ]
    with patch("openhands.sdk.git.utils._run_git_subprocess", side_effect=responses):
        metadata = get_git_repository_metadata("/repo")

    assert metadata == {
        "repo_remote": "HTTPS://****@github.com/org/repo.git",
        "head_commit": "abc123",
        "branch": "feature-x",
    }
