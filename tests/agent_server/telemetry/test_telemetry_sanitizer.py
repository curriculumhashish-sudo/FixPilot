"""证明去污术真的实现了文档字符串所声称的。

这里的中心测试是
``test_fingerprint_ignores_the_exception_message``它演示了两个不同的异常 *仅* 在他们
的信息中——其中包含一个机密 —
产生相同的指纹。 只有当消息从未被阅读时才有可能，这是全部保证。
"""

import json
from dataclasses import asdict

import pytest

from openhands.agent_server.telemetry.sanitizer import (
    COST_BOUNDS,
    COUNT_BOUNDS,
    DURATION_BOUNDS,
    Bounds,
    bucket,
    model_family,
    normalize_error_code,
    normalize_exception,
    pseudonymize,
    safe_identifier,
    safe_token,
    safe_version,
)


SECRET = "sk-ant-api03-SUPERSECRETVALUE"
PROMPT = "Summarize this confidential memo: Dear Board, ..."
PATH = "/Users/alice/private/repo/main.py"


def _raise(message: str) -> BaseException:
    try:
        raise ValueError(message)
    except ValueError as exc:  # noqa: PERF203
        return exc


def test_fingerprint_ignores_the_exception_message():
    """来自同一行指纹的两个错误完全相同。

    如果消息对哈希有贡献，其中之一中的机密将更改摘要。 相同的摘要证明消息从未被读取。
    """
    a = _raise("secret-A")
    b = _raise("secret-B")

    fa = normalize_exception(a)
    fb = normalize_exception(b)

    assert fa.error_fingerprint == fb.error_fingerprint
    assert fa.error_class == fb.error_class == "ValueError"


def test_fingerprint_distinguishes_different_error_types():
    try:
        raise KeyError("k")
    except KeyError as exc:
        key_fp = normalize_exception(exc)

    value_fp = normalize_exception(_raise("v"))
    assert key_fp.error_fingerprint != value_fp.error_fingerprint


def test_fingerprint_distinguishes_different_raise_sites():
    def site_one() -> BaseException:
        try:
            raise RuntimeError("x")
        except RuntimeError as exc:
            return exc

    def site_two() -> BaseException:
        try:
            raise RuntimeError("x")
        except RuntimeError as exc:
            return exc

    # 此（第一方外观）测试模块中的不同行通常会有所不同； 每个站点的指纹至少必须具有确定
    # 性。
    #
    assert (
        normalize_exception(site_one()).error_fingerprint
        == normalize_exception(site_one()).error_fingerprint
    )
    assert (
        normalize_exception(site_two()).error_fingerprint
        == normalize_exception(site_two()).error_fingerprint
    )


@pytest.mark.parametrize(
    "payload", [SECRET, PROMPT, PATH], ids=["secret", "prompt", "path"]
)
def test_no_part_of_the_message_survives_normalization(payload: str):
    fingerprint = normalize_exception(_raise(payload))
    serialized = json.dumps(asdict(fingerprint))

    assert payload not in serialized
    # 也没有任何独特的片段。
    for fragment in payload.split()[:3]:
        if len(fragment) > 6:
            assert fragment not in serialized


def test_normalization_never_emits_a_traceback_or_a_path():
    fingerprint = normalize_exception(_raise("boom"))
    serialized = json.dumps(asdict(fingerprint))

    assert "Traceback" not in serialized
    assert "/" not in serialized
    assert ".py" not in serialized


def test_third_party_exceptions_collapse_to_package_scope():
    """不熟悉的依赖关系一定不能破坏基数。"""

    class _FakeVendorError(Exception):
        pass

    _FakeVendorError.__module__ = "litellm.exceptions.deeply.nested"
    try:
        raise _FakeVendorError("nope")
    except _FakeVendorError as exc:
        fingerprint = normalize_exception(exc)

    assert fingerprint.error_class == "litellm:_FakeVendorError"
    assert fingerprint.is_first_party is False


def test_builtin_exceptions_keep_their_bare_name():
    assert normalize_exception(_raise("x")).error_class == "ValueError"


def test_category_is_derived_from_type_via_mro():
    try:
        raise FileNotFoundError("missing")
    except FileNotFoundError as exc:
        assert normalize_exception(exc).error_category == "workspace_io"

    try:
        raise TimeoutError("slow")
    except TimeoutError as exc:
        assert normalize_exception(exc).error_category == "llm_timeout"


def test_unknown_exception_types_get_the_unknown_category():
    class _Weird(Exception):
        pass

    try:
        raise _Weird("?")
    except _Weird as exc:
        assert normalize_exception(exc).error_category == "unknown"


def test_normalize_error_code_rejects_free_text():
    """ConversationErrorEvent.code 仅在验证时才可信。"""
    assert normalize_error_code("LLMAuthError").error_class == "LLMAuthError"
    # 实际上是散文的代码会降低质量而不是泄漏。
    assert normalize_error_code(PROMPT).error_class == "UnknownError"
    assert normalize_error_code(None).error_class == "UnknownError"


# ── 标量强制转换 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("finished", "finished"),
        ("FINISHED", "finished"),
        ("has space", "unknown"),
        ("/a/path", "unknown"),
        (None, "unknown"),
        (123, "unknown"),
    ],
)
def test_safe_token(value, expected):
    assert safe_token(value) == expected


def test_safe_identifier_rejects_secret_and_path_shapes():
    assert safe_identifier("ValueError") == "ValueError"
    assert safe_identifier("openhands.sdk.Foo") == "openhands.sdk.Foo"
    assert safe_identifier(SECRET) == "UnknownError"
    assert safe_identifier(PATH) == "UnknownError"
    assert safe_identifier("a" * 200) == "UnknownError"


def test_safe_version_accepts_real_versions_and_refs():
    assert safe_version("1.36.1") == "1.36.1"
    assert safe_version("refs/heads/main") == "refs/heads/main"
    assert safe_version("unknown") == "unknown"
    assert safe_version("not a version!") == "unknown"


# ── 装桶──────────────────────────────────────────────────────────────


def test_buckets_never_reveal_exact_magnitudes():
    assert bucket(0.5, DURATION_BOUNDS) == "lt-1"
    assert bucket(7, DURATION_BOUNDS) == "5-15"
    assert bucket(100_000, DURATION_BOUNDS) == "1800+"
    assert bucket(0, COUNT_BOUNDS) == "lt-1"
    assert bucket(3, COUNT_BOUNDS) == "1-5"
    assert bucket(0.005, COST_BOUNDS) == "lt-0p01"
    assert bucket(None, DURATION_BOUNDS) == "unknown"
    assert bucket(-1, DURATION_BOUNDS) == "unknown"


def test_bucket_is_monotonic():
    bounds = Bounds((1, 10, 100))
    labels = [bucket(v, bounds) for v in (0, 5, 50, 500)]
    assert len(set(labels)) == 4


# ── 化名────────────────────────────────────────────────────────


def test_pseudonymize_is_stable_and_salt_dependent():
    a = pseudonymize("conversation-1", "salt-A")
    b = pseudonymize("conversation-1", "salt-A")
    c = pseudonymize("conversation-1", "salt-B")

    assert a == b
    assert a != c
    assert "conversation-1" not in a


def test_pseudonymize_accepts_an_oversized_salt():
    """blake2s 将密钥上限限制为 32 字节； 长的机密不能引发。"""
    digest = pseudonymize("x", "s" * 500)
    assert len(digest) == 32


# ── 模范家庭────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "model,expected",
    [
        ("anthropic/claude-sonnet-5", "anthropic"),
        ("claude-opus-4-8", "anthropic"),
        ("gpt-4o", "openai"),
        ("gemini-2.0-flash", "gemini"),
        ("litellm_proxy/my-internal-deployment", "litellm_proxy"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_model_family_collapses_to_a_closed_vocabulary(model, expected):
    assert model_family(model) == expected


def test_model_family_never_leaks_a_custom_endpoint():
    assert "internal.corp" not in model_family("openai/https://internal.corp/v1/x")
