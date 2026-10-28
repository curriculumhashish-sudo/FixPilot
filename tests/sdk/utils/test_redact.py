"""测试编辑实用函数。"""

import pytest

from openhands.sdk.utils.redact import (
    SENSITIVE_URL_PARAMS,
    redact_api_key_literals,
    redact_text_secrets,
    redact_url_credentials,
    redact_url_credentials_in_text,
    redact_url_params,
)


# ---------------------------------------------------------------------------
# SENSITIVE_URL_PARAMS 常数
# ---------------------------------------------------------------------------


class TestSensitiveUrlParams:
    """验证 SENSITIVE_URL_PARAMS 常数。"""

    def test_is_frozenset(self):
        assert isinstance(SENSITIVE_URL_PARAMS, frozenset)

    def test_contains_expected_entries(self):
        expected = {
            "tavilyapikey",
            "apikey",
            "api_key",
            "token",
            "access_token",
            "secret",
            "key",
        }
        assert SENSITIVE_URL_PARAMS == expected


# ---------------------------------------------------------------------------
# redact_url_params
# ---------------------------------------------------------------------------


class TestRedactUrlParams:
    """测试 redact_url_params()。"""

    # -- 基础脱敏 --------------------------------------------------

    def test_redacts_apikey_param(self):
        url = "https://example.com/search?q=hello&apikey=secret123"
        result = redact_url_params(url)
        assert "secret123" not in result
        assert "apikey=" in result
        assert "q=hello" in result

    def test_redacts_api_key_param(self):
        url = "https://api.example.com/v1/data?api_key=sk-abc123&format=json"
        result = redact_url_params(url)
        assert "sk-abc123" not in result
        assert "format=json" in result

    def test_redacts_token_param(self):
        url = "https://example.com/callback?token=jwt_xyz&state=abc"
        result = redact_url_params(url)
        assert "jwt_xyz" not in result
        assert "state=abc" in result

    def test_redacts_access_token_param(self):
        url = "https://example.com/api?access_token=ghp_xxxx"
        result = redact_url_params(url)
        assert "ghp_xxxx" not in result

    def test_redacts_secret_param(self):
        url = "https://example.com?secret=mysecret&other=value"
        result = redact_url_params(url)
        assert "mysecret" not in result
        assert "other=value" in result

    def test_redacts_key_param(self):
        url = "https://example.com?key=12345"
        result = redact_url_params(url)
        assert "12345" not in result

    def test_redacts_tavilyapikey_param(self):
        url = "https://api.tavily.com/search?tavilyApiKey=tvly-abc123&query=test"
        result = redact_url_params(url)
        assert "tvly-abc123" not in result
        assert "query=test" in result

    # -- 不区分大小写的匹配 --------------------------------------------------

    def test_case_insensitive_exact_match(self):
        """SENSITIVE_URL_PARAMS 匹配不区分大小写。"""
        url = "https://example.com?ApiKey=val1&TOKEN=val2&Secret=val3"
        result = redact_url_params(url)
        assert "val1" not in result
        assert "val2" not in result
        assert "val3" not in result

    # -- is_secret_key 模式匹配 ------------------------------------------------

    def test_redacts_via_is_secret_key_pattern(self):
        """通过 is_secret_key() 匹配 SECRET_KEY_PATTERNS 的参数得到已脱敏。"""
        url = "https://example.com?Authorization=Bearer+xyz&page=1"
        result = redact_url_params(url)
        assert "Bearer" not in result
        assert "xyz" not in result
        assert "page=1" in result

    def test_redacts_x_api_key_via_pattern(self):
        """'x-API-key' 包含 'KEY'，因此 is_secret_key 匹配。"""
        url = "https://example.com?x-api-key=abc123&limit=10"
        result = redact_url_params(url)
        assert "abc123" not in result
        assert "limit=10" in result

    # -- 边缘情况--------------------------------------------------------------------

    def test_no_query_params(self):
        url = "https://example.com/path"
        assert redact_url_params(url) == url

    def test_empty_query_string(self):
        url = "https://example.com/path?"
        # urlparse 处理尾随的 '?'作为空查询； 应该返回不变
        result = redact_url_params(url)
        assert result == "https://example.com/path?"

    def test_empty_string(self):
        assert redact_url_params("") == ""

    def test_non_url_string(self):
        """非 URL 字符串应按原样返回（不会崩溃）。"""
        text = "not a url at all"
        assert redact_url_params(text) == text

    def test_url_with_fragment(self):
        url = "https://example.com/page?apikey=secret#section"
        result = redact_url_params(url)
        assert "secret" not in result
        assert "#section" in result

    def test_url_with_port_and_path(self):
        url = "http://localhost:8080/api/v1?token=abc&debug=true"
        result = redact_url_params(url)
        assert "abc" not in result
        assert "debug=true" in result
        assert "localhost:8080" in result

    def test_preserves_non_sensitive_params(self):
        url = "https://example.com?page=1&limit=50&sort=asc"
        assert redact_url_params(url) == url

    def test_multiple_sensitive_params(self):
        url = "https://example.com?apikey=k1&token=t1&secret=s1&q=hello"
        result = redact_url_params(url)
        assert "k1" not in result
        assert "t1" not in result
        assert "s1" not in result
        assert "q=hello" in result

    def test_param_with_empty_value(self):
        url = "https://example.com?apikey=&other=value"
        result = redact_url_params(url)
        # 即使是空值也应该替换为 <redacted>
        assert "other=value" in result

    def test_param_with_multiple_values(self):
        """当一个参数出现多次时，所有值都是已脱敏。"""
        url = "https://example.com?token=FIRSTVAL&token=SECONDVAL&page=1"
        result = redact_url_params(url)
        assert "token=" in result
        assert "FIRSTVAL" not in result
        assert "SECONDVAL" not in result
        assert "page=1" in result

    def test_url_with_encoded_characters(self):
        url = "https://example.com/path?q=hello%20world&apikey=secret%20value"
        result = redact_url_params(url)
        assert "secret" not in result
        # 应保留非敏感参数值（可能重新编码）
        assert "hello" in result


# ---------------------------------------------------------------------------
# redact_url_credentials_in_text
# ---------------------------------------------------------------------------


class TestRedactUrlCredentialsInText:
    """测试 redact_url_credentials_in_text()（支持子字符串）。"""

    def test_redacts_credentials_embedded_in_larger_string(self):
        """锚定助手的关键限制：消息内的信用。"""
        s = "fatal: unable to access 'https://oauth2:SECRET@github.com/o/r.git/': 403"
        result = redact_url_credentials_in_text(s)
        assert "SECRET" not in result
        assert "oauth2" not in result
        assert result == (
            "fatal: unable to access 'https://****@github.com/o/r.git/': 403"
        )

    def test_redacts_token_only_credential(self):
        s = "Cloning https://ghp_supersecrettoken@github.com/o/r.git failed"
        result = redact_url_credentials_in_text(s)
        assert "ghp_supersecrettoken" not in result
        assert "https://****@github.com/o/r.git" in result

    def test_redacts_http_scheme(self):
        s = "warn http://user:pw@internal.example.com/x done"
        result = redact_url_credentials_in_text(s)
        assert "user:pw" not in result
        assert "http://****@internal.example.com/x" in result

    def test_redacts_mixed_case_scheme(self):
        s = "HTTPS://user:token@github.com/o/r.git"
        assert redact_url_credentials_in_text(s) == ("HTTPS://****@github.com/o/r.git")

    def test_redacts_multiple_embedded_urls(self):
        s = "a https://t1@github.com/o/r.git b https://user:t2@gitlab.com/o/r.git c"
        result = redact_url_credentials_in_text(s)
        assert "t1" not in result
        assert "t2" not in result
        assert result.count("****@") == 2

    def test_redacts_url_encoded_credentials(self):
        s = "url 'https://user%40domain:p%40ss@github.com/repo.git'"
        result = redact_url_credentials_in_text(s)
        assert "user%40domain" not in result
        assert "p%40ss" not in result
        assert "https://****@github.com/repo.git" in result

    def test_leaves_credential_free_url_untouched(self):
        s = "Cloning https://github.com/owner/repo.git into ./repo"
        assert redact_url_credentials_in_text(s) == s

    def test_does_not_match_at_sign_in_path(self):
        """路径段后面的“@”不是用户信息，必须单独保留。"""
        s = "see https://github.com/owner/repo/blob/main/x@v1.txt"
        assert redact_url_credentials_in_text(s) == s

    def test_leaves_ssh_url_untouched(self):
        s = "remote git@github.com:owner/repo.git fetched"
        assert redact_url_credentials_in_text(s) == s

    def test_empty_string(self):
        assert redact_url_credentials_in_text("") == ""

    def test_no_url_string(self):
        assert redact_url_credentials_in_text("nothing to redact here") == (
            "nothing to redact here"
        )

    def test_matches_whole_url_like_anchored_helper(self):
        """对于裸露的整个 URL 字符串，两个助手都同意。"""
        url = "https://oauth2:SECRET@gitlab.com/org/repo.git"
        assert redact_url_credentials_in_text(url) == redact_url_credentials(url)


# ---------------------------------------------------------------------------
# redact_text_secrets
# ---------------------------------------------------------------------------


class TestRedactTextSecretsDictKeys:
    """字典条目脱敏不区分大小写，就像 is_secret_key 一样。

    回归测试  https://github.com/OpenHands/software-agent-sdk/issues/4505
    """

    def test_redacts_lowercase_and_mixed_case_dict_keys(self):
        text = (
            "{'api_key': 's3cr3t', \"token\": \"tok-XYZ\", "
            "'UserPassword': 'p@ssw0rd', 'normal': 'keep-me'}"
        )
        assert redact_text_secrets(text) == (
            "{'api_key': '<redacted>', \"token\": \"<redacted>\", "
            "'UserPassword': '<redacted>', 'normal': 'keep-me'}"
        )

    def test_uppercase_dict_keys_still_redacted(self):
        text = "{'API_KEY': 'abc', \"MY_SECRET\": \"def\"}"
        assert redact_text_secrets(text) == (
            "{'API_KEY': '<redacted>', \"MY_SECRET\": \"<redacted>\"}"
        )

    def test_non_sensitive_entries_unchanged(self):
        text = "{'name': 'alice', 'path': '/tmp/x'}"
        assert redact_text_secrets(text) == text


@pytest.mark.parametrize(
    ("key", "key_quote", "value_quote"),
    [
        ("private_key", "'", "'"),
        ("token", '"', '"'),
        ("authorization", "'", '"'),
        ("password", '\\"', '\\"'),
    ],
    ids=["pem", "double-quotes", "mixed-quotes", "escaped-quotes"],
)
def test_redact_text_secrets_redacts_multiline_values(key, key_quote, value_quote):
    head = f"{{{key_quote}{key}{key_quote}: {value_quote}"
    secret = "-----BEGIN PRIVATE KEY-----\nsecret-content\n-----END PRIVATE KEY-----"
    tail = f"{value_quote}, 'note': 'first public line\nsecond public line'}}"

    assert redact_text_secrets(f"{head}{secret}{tail}") == f"{head}<redacted>{tail}"


class TestRedactTextSecretsHeaders:
    """标头条目作为提供者错误回显它们：任何情况，或者引用
    样式、带破折号的姓名，以及 JSON 中嵌入的转义引号。"""

    @pytest.mark.parametrize(
        "text",
        [
            "{'authorization': 'Bearer hdr-secret-1'}",
            '{"Authorization": "Bearer hdr-secret-1"}',
            '{"authorization": "Bearer hdr-secret-1"}',
            '{"api-key": "hdr-secret-1"}',
            "{'x-api-key': \"hdr-secret-1\"}",
            "{'X-Session-API-Key': 'hdr-secret-1'}",
            'Error: {\\"Authorization\\": \\"Bearer hdr-secret-1\\"}',
        ],
    )
    def test_redacts_credential_headers(self, text):
        redacted = redact_text_secrets(text)
        assert "hdr-secret-1" not in redacted
        assert "<redacted>" in redacted

    def test_keeps_other_headers(self):
        text = "{'content-type': 'application/json', 'x-title': 'OpenHands'}"
        assert redact_text_secrets(text) == text


# ---------------------------------------------------------------------------
# redact_api_key_literals
# ---------------------------------------------------------------------------


class TestRedactApiKeyLiterals:
    """测试 redact_api_key_literals() — 裸 API 键模式匹配。"""

    def test_redacts_sk_oh_api_key(self):
        """sk-oh-* OpenHands API 键是已脱敏。"""
        text = "key is sk-oh-abcdef1234567890 here"
        result = redact_api_key_literals(text)
        assert "sk-oh-abcdef1234567890" not in result
        assert result == "key is <redacted> here"

    def test_redacts_sk_oh_key_with_hyphens_and_underscores(self):
        """sk-oh-* 包含连字符和下划线的键是已脱敏。"""
        text = "export KEY=sk-oh-abc_def-123_XYZ-456"
        result = redact_api_key_literals(text)
        assert "sk-oh-abc_def-123_XYZ-456" not in result
        assert "export KEY=<redacted>" == result

    def test_does_not_redact_short_sk_oh_key(self):
        """sk-oh- 后跟少于 10 个字符应不匹配。"""
        text = "sk-oh-short"
        result = redact_api_key_literals(text)
        assert result == text

    def test_redacts_sk_oh_key_in_log_line(self):
        """具有 sk-oh-* 键的实际日志行是已脱敏。"""
        text = (
            'ERROR runtime stderr: api_key="sk-oh-Xk9mP2vL4nR7wQ1y" connection refused'
        )
        result = redact_api_key_literals(text)
        assert "sk-oh-Xk9mP2vL4nR7wQ1y" not in result
        assert "ERROR runtime stderr:" in result
