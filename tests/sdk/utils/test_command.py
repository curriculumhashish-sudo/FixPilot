from collections import OrderedDict
from unittest.mock import patch

import pytest

from openhands.sdk.utils.command import execute_command, sanitized_env


def test_sanitized_env_returns_copy():
    """返回字典副本，而不是原始内容。"""
    env = {"FOO": "bar"}
    result = sanitized_env(env)
    assert result == {"FOO": "bar", "AI_AGENT": "openhands"}
    assert result is not env


def test_sanitized_env_strips_sensitive_credentials():
    """会话密钥 (V0)、密码密钥和索引会话密钥槽 (V1)
    绝不能达到子进程，而保留普通变量。"""
    env = {
        "SESSION_API_KEY": "v0-session",
        "OH_SECRET_KEY": "cipher-secret",
        "OH_SESSION_API_KEYS_0": "v1-session-0",
        "OH_SESSION_API_KEYS_1": "v1-session-1",
        "LMNR_PROJECT_API_KEY": "laminar-key",
        "OTEL_HEADERS": "legacy-headers",
        "OTEL_EXPORTER_OTLP_HEADERS": "otlp-headers",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "trace-headers",
        "OH_WEB_URL": "https://example.test",
        "FOO": "bar",
    }
    result = sanitized_env(env)
    assert "SESSION_API_KEY" not in result
    assert "OH_SECRET_KEY" not in result
    assert "OH_SESSION_API_KEYS_0" not in result
    assert "OH_SESSION_API_KEYS_1" not in result
    for key in (
        "LMNR_PROJECT_API_KEY",
        "OTEL_HEADERS",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    ):
        assert key not in result
    # 保留非敏感变量（包括其他 OH_* 配置）。
    assert result["OH_WEB_URL"] == "https://example.test"
    assert result["FOO"] == "bar"


def test_sanitized_env_preserves_explicit_ai_agent():
    result = sanitized_env({"AI_AGENT": "wrapper"})
    assert result["AI_AGENT"] == "wrapper"


def test_sanitized_env_replaces_blank_ai_agent():
    result = sanitized_env({"AI_AGENT": "  "})
    assert result["AI_AGENT"] == "openhands"


def test_sanitized_env_defaults_to_os_environ(monkeypatch):
    """当 env 为 None 时，返回基于 os.environ 的字典。"""
    monkeypatch.setenv("TEST_SANITIZED_ENV_VAR", "test_value")
    result = sanitized_env(None)
    assert result["TEST_SANITIZED_ENV_VAR"] == "test_value"


def test_sanitized_env_accepts_mapping_types():
    """接受任何映射类型，而不仅仅是字典。"""
    env: OrderedDict[str, str] = OrderedDict([("KEY", "value")])
    assert isinstance(sanitized_env(env), dict)


@pytest.mark.parametrize(
    ("env", "expected_ld_path"),
    [
        # ORIG存在且非空：恢复原始值
        (
            {"LD_LIBRARY_PATH": "/pyinstaller", "LD_LIBRARY_PATH_ORIG": "/original"},
            "/original",
        ),
        # ORIG 缺席：保持不变
        ({"LD_LIBRARY_PATH": "/some/path"}, "/some/path"),
    ],
)
def test_sanitized_env_ld_library_path(env: dict[str, str], expected_ld_path: str):
    """LD_LIBRARY_PATH从ORIG恢复或保持不变。"""
    assert sanitized_env(env)["LD_LIBRARY_PATH"] == expected_ld_path


def test_sanitized_env_removes_ld_library_path_when_orig_empty():
    """当LD_LIBRARY_PATH_ORIG为空时，删除LD_LIBRARY_PATH。"""
    env = {"LD_LIBRARY_PATH": "/pyinstaller", "LD_LIBRARY_PATH_ORIG": ""}
    assert "LD_LIBRARY_PATH" not in sanitized_env(env)


# ---------------------------------------------------------------------------
# execute_command 记录脱敏
# ---------------------------------------------------------------------------


class TestExecuteCommandLoggingRedaction:
    """测试 execute_command 日志记录中的敏感值脱敏。"""

    def test_logs_command_without_errors(self, caplog):
        """使用脱敏进行命令记录不会引发错误。"""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = mock_popen.return_value
            mock_process.stdout = None
            mock_process.stderr = None

            cmd = ["docker", "run", "-e", "LMNR_PROJECT_API_KEY=secret123", "image"]

            try:
                execute_command(cmd)
            except RuntimeError:
                # 即使子进程失败也应该进行记录
                pass

            # 应记录命令
            assert "docker" in caplog.text
            assert "run" in caplog.text
            assert "image" in caplog.text

    def test_redacts_api_key_from_string_command(self):
        """字符串命令中的 API 键正确为已脱敏。"""
        from openhands.sdk.utils.redact import redact_text_secrets

        # 直接测试脱敏功能有效Anthropic密钥格式：sk-ant-API[2digits]-[20+chars]
        #
        cmd_str = "curl -H 'Authorization: sk-ant-api00-abcd1234567890abcdefghijklmnop' https://api.anthropic.com"
        redacted = redact_text_secrets(cmd_str)

        # 函数输出中的机密应为已脱敏
        assert "sk-ant-api00-abcd1234567890abcdefghijklmnop" not in redacted
        assert "<redacted>" in redacted
        # 应保留命令结构
        assert "curl" in redacted
        assert "https://api.anthropic.com" in redacted

    def test_redacts_key_value_env_format(self):
        """KEY=VALUE environment variable format is redacted."""
        from openhands.sdk.utils.redact import redact_text_secrets

        cmd_str = "docker run -e api_key='secretvalue123456789' -e DEBUG=true image"
        redacted = redact_text_secrets(cmd_str)

        # api_key 值应为已脱敏
        assert "secretvalue123456789" not in redacted
        # 但应该存在不敏感的 DEBUG 值
        assert "DEBUG" in redacted
        # 保留命令结构
        assert "docker" in redacted

    def test_preserves_non_sensitive_args(self, caplog):
        """非敏感参数保留在日志中。"""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = mock_popen.return_value
            mock_process.stdout = None
            mock_process.stderr = None

            cmd = ["docker", "run", "-e", "DEBUG=true", "image:latest"]

            try:
                execute_command(cmd)
            except RuntimeError:
                pass

            # 非敏感值应该可见
            assert "DEBUG=true" in caplog.text
            assert "image:latest" in caplog.text
            assert "docker" in caplog.text
