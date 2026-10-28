"""测试 SecretsManager 类。"""

from pydantic import SecretStr

from openhands.sdk.conversation.secret_registry import (
    FAILED_LOOKUP_RETRY_SECONDS,
    SecretRegistry,
)
from openhands.sdk.secret import SecretSource, StaticSecret


# 注意：有意的模块级。 局部函数 ``SecretSource``
# (DiscriminatedUnionMixin) 类自动注册全局，并且使注册表在任何后续的歧异联合中引发 "本地
# 类不支持！" 验证在同一个 xdist 工作进程（破坏了无关的） ConversationState (空)序列化).
#  在这里定义每个类还可以避免两个同名函数本地类会触发“重复类定义”保护。
#
class MyTokenSource(SecretSource):
    def get_value(self):
        return "dynamic-token-456"


class MyFailingTokenSource(SecretSource):
    def get_value(self):
        raise ValueError("Secret retrieval failed")


class MyWorkingTokenSource(SecretSource):
    def get_value(self):
        return "working-value"


class MyCountingFailingSource(SecretSource):
    attempts: int = 0

    def get_value(self):
        type(self).attempts += 1
        raise OSError("Secret retrieval failed")


class MyCountingLazySource(SecretSource):
    attempts: int = 0

    def get_value(self):
        type(self).attempts += 1
        return "lazy-value"


class MyRecoveringSource(SecretSource):
    fail: bool = True

    def get_value(self):
        if type(self).fail:
            raise OSError("Secret retrieval failed")
        return "recovered-value"


def test_update_secrets_with_static_values():
    """测试使用静态字符串值更新机密。"""
    secret_registry = SecretRegistry()
    secrets = {
        "API_KEY": "test-api-key",
        "DATABASE_URL": "postgresql://localhost/test",
    }

    secret_registry.update_secrets(secrets)
    assert secret_registry.secret_sources == {
        "API_KEY": StaticSecret(value=SecretStr("test-api-key")),
        "DATABASE_URL": StaticSecret(value=SecretStr("postgresql://localhost/test")),
    }


def test_update_secrets_overwrites_existing():
    """测试 update_secrets 是否覆盖现有键。"""
    secret_registry = SecretRegistry()

    # 添加首字母机密
    secret_registry.update_secrets({"API_KEY": "old-value"})
    assert secret_registry.secret_sources["API_KEY"] == StaticSecret(
        value=SecretStr("old-value")
    )

    # 使用新值更新
    secret_registry.update_secrets({"API_KEY": "new-value", "NEW_KEY": "key-value"})
    assert secret_registry.secret_sources["API_KEY"] == StaticSecret(
        value=SecretStr("new-value")
    )

    secret_registry.update_secrets({"API_KEY": "new-value-2"})
    assert secret_registry.secret_sources["API_KEY"] == StaticSecret(
        value=SecretStr("new-value-2")
    )


def test_find_secrets_in_text_case_insensitive():
    """测试 find_secrets_in_text 是否不区分大小写。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "test-key",
            "DATABASE_PASSWORD": "test-password",
        }
    )

    # 测试各种案例组合
    found = secret_registry.find_secrets_in_text("echo api_key=$API_KEY")
    assert found == {"API_KEY"}

    found = secret_registry.find_secrets_in_text("echo $database_password")
    assert found == {"DATABASE_PASSWORD"}

    found = secret_registry.find_secrets_in_text("API_KEY and DATABASE_PASSWORD")
    assert found == {"API_KEY", "DATABASE_PASSWORD"}

    found = secret_registry.find_secrets_in_text("echo hello world")
    assert found == set()


def test_find_secrets_in_text_partial_matches():
    """测试 find_secrets_in_text 是否正确处理部分匹配。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "test-key",
            "API": "test-api",  # API_KEY 中包含的较短密钥
        }
    )

    # 两者都应该找到，因为“API”包含在“API_KEY”中
    found = secret_registry.find_secrets_in_text("export API_KEY=$API_KEY")
    assert "API_KEY" in found
    assert "API" in found


def test_get_secrets_as_env_vars_static_values():
    """使用静态值测试 get_secrets_as_env_vars。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "test-api-key",
            "DATABASE_URL": "postgresql://localhost/test",
        }
    )

    env_vars = secret_registry.get_secrets_as_env_vars("curl -H 'X-API-Key: $API_KEY'")
    assert env_vars == {"API_KEY": "test-api-key"}

    env_vars = secret_registry.get_secrets_as_env_vars(
        "export API_KEY=$API_KEY && export DATABASE_URL=$DATABASE_URL"
    )
    assert env_vars == {
        "API_KEY": "test-api-key",
        "DATABASE_URL": "postgresql://localhost/test",
    }


def test_get_secrets_as_env_vars_callable_values():
    """使用可调用值测试 get_secrets_as_env_vars。"""
    secret_registry = SecretRegistry()

    secret_registry.update_secrets(
        {
            "STATIC_KEY": "static-value",
            "DYNAMIC_TOKEN": MyTokenSource(),
        }
    )

    env_vars = secret_registry.get_secrets_as_env_vars(
        "export DYNAMIC_TOKEN=$DYNAMIC_TOKEN"
    )
    assert env_vars == {"DYNAMIC_TOKEN": "dynamic-token-456"}


def test_get_secrets_as_env_vars_handles_callable_exceptions():
    """测试 get_secrets_as_env_vars 是否处理来自可调用对象的异常。"""
    secret_registry = SecretRegistry()

    secret_registry.update_secrets(
        {
            "FAILING_SECRET": MyFailingTokenSource(),
            "WORKING_SECRET": MyWorkingTokenSource(),
        }
    )

    # 不应引发异常，应跳过失败机密
    env_vars = secret_registry.get_secrets_as_env_vars(
        "export FAILING_SECRET=$FAILING_SECRET && export WORKING_SECRET=$WORKING_SECRET"
    )

    # 仅应返回工作机密
    assert env_vars == {"WORKING_SECRET": "working-value"}


def test_get_all_secrets_as_env_vars_resolves_whole_registry():
    """get_all_secrets_as_env_vars 无需命令扫描即可解析每个机密。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "static-value",
            "DYNAMIC_TOKEN": MyTokenSource(),
        }
    )

    env_vars = secret_registry.get_all_secrets_as_env_vars()
    assert env_vars == {
        "API_KEY": "static-value",
        "DYNAMIC_TOKEN": "dynamic-token-456",
    }


def test_get_all_secrets_as_env_vars_excludes_named_keys():
    """排除集会跳过键 (e.g. 更高优先级的层将设置）。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"KEEP": "keep-value", "DROP": "drop-value"})

    env_vars = secret_registry.get_all_secrets_as_env_vars(exclude={"DROP"})
    assert env_vars == {"KEEP": "keep-value"}


def test_get_all_secrets_as_env_vars_skips_failing_lookups():
    """失败的查找会被吞掉，而不是引发； 仅返回可解析的键。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "FAILING_SECRET": MyFailingTokenSource(),
            "WORKING_SECRET": MyWorkingTokenSource(),
        }
    )

    env_vars = secret_registry.get_all_secrets_as_env_vars()
    assert env_vars == {"WORKING_SECRET": "working-value"}


def test_get_all_secrets_as_env_vars_tracks_values_for_masking():
    """解析值馈送 _exported_values，因此输出屏蔽会覆盖它们。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"API_KEY": "super-secret"})

    secret_registry.get_all_secrets_as_env_vars()
    assert (
        secret_registry.mask_secrets_in_output("leak: super-secret")
        == "leak: <secret-hidden>"
    )


def test_get_secret_value_static():
    """使用静态字符串值测试 get_secret_value。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "test-api-key",
            "DATABASE_URL": "postgresql://localhost/test",
        }
    )

    assert secret_registry.get_secret_value("API_KEY") == "test-api-key"
    assert (
        secret_registry.get_secret_value("DATABASE_URL")
        == "postgresql://localhost/test"
    )
    assert secret_registry.get_secret_value("NONEXISTENT") is None


def test_get_secret_value_callable():
    """使用可调用值测试 get_secret_value。"""
    secret_registry = SecretRegistry()

    secret_registry.update_secrets(
        {
            "STATIC_KEY": "static-value",
            "DYNAMIC_TOKEN": MyTokenSource(),
        }
    )

    assert secret_registry.get_secret_value("STATIC_KEY") == "static-value"
    assert secret_registry.get_secret_value("DYNAMIC_TOKEN") == "dynamic-token-456"


def test_get_secret_value_handles_exceptions():
    """测试 get_secret_value 是否优雅地处理来自可调用对象的异常。"""
    secret_registry = SecretRegistry()

    secret_registry.update_secrets(
        {
            "FAILING_SECRET": MyFailingTokenSource(),
            "WORKING_SECRET": MyWorkingTokenSource(),
        }
    )

    # 不应引发异常，如果失败机密应返回 None
    assert secret_registry.get_secret_value("FAILING_SECRET") is None
    assert secret_registry.get_secret_value("WORKING_SECRET") == "working-value"


def test_get_secret_value_empty_registry():
    """使用空注册表测试 get_secret_value。"""
    secret_registry = SecretRegistry()
    assert secret_registry.get_secret_value("ANY_KEY") is None


def test_get_secret_value_as_callback():
    """测试使用 get_secret_value 作为回调进行类似字典的查找。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_KEY": "test-api-key",
            "TOKEN": "test-token",
        }
    )

    # 这就是它与 expand_mcp_variables 一起使用的方式
    get_secret = secret_registry.get_secret_value

    assert get_secret("API_KEY") == "test-api-key"
    assert get_secret("TOKEN") == "test-token"
    assert get_secret("MISSING") is None


def test_get_secret_value_tracks_for_masking():
    """测试 get_secret_value 将机密添加到 _exported_values 以进行屏蔽。

    应跟踪通过 get_secret_value（e.g.，用于 MCP 扩展）检索的机密，以便可以在命令输出
    中屏蔽它们。
    """
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "API_TOKEN": "super-secret-token-123",
            "DB_PASSWORD": "db-pass-456",
        }
    )

    # 最初，没有导出值
    assert secret_registry._exported_values == {}

    # 通过 get_secret_value 检索机密
    value = secret_registry.get_secret_value("API_TOKEN")
    assert value == "super-secret-token-123"

    # 现在应该跟踪机密以进行屏蔽
    assert "API_TOKEN" in secret_registry._exported_values
    assert secret_registry._exported_values["API_TOKEN"] == "super-secret-token-123"

    # 屏蔽应该适用于跟踪的机密
    output = "Response: super-secret-token-123"
    masked = secret_registry.mask_secrets_in_output(output)
    assert masked == "Response: <secret-hidden>"

    # 检索另一个机密
    secret_registry.get_secret_value("DB_PASSWORD")
    assert "DB_PASSWORD" in secret_registry._exported_values

    # 现在两者都应该被屏蔽
    output2 = "API: super-secret-token-123, DB: db-pass-456"
    masked2 = secret_registry.mask_secrets_in_output(output2)
    assert masked2 == "API: <secret-hidden>, DB: <secret-hidden>"


def test_get_secret_value_missing_not_tracked():
    """测试缺失的机密是否不会添加到 _exported_values。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"EXISTING": "value"})

    # 查找丢失的钥匙
    result = secret_registry.get_secret_value("NONEXISTENT")
    assert result is None
    assert "NONEXISTENT" not in secret_registry._exported_values


def test_track_exported_values_drops_empty_values():
    """空值不得输入 _exported_values（它们会破坏屏蔽）。"""
    secret_registry = SecretRegistry()
    secret_registry.track_exported_values({"REAL": "secret", "EMPTY": ""})

    assert "EMPTY" not in secret_registry._exported_values
    assert secret_registry._exported_values["REAL"] == "secret"


def test_mask_secrets_in_output_ignores_empty_value():
    """空的导出值不得在字符之间拼接占位符。"""
    secret_registry = SecretRegistry()
    secret_registry._exported_values["EMPTY"] = ""

    assert secret_registry.mask_secrets_in_output("hello") == "hello"


def test_mask_secrets_without_name_reference_in_command():
    """即使没有命令引用过机密值的名称，它也会被屏蔽。"""
    token = "github_pat_REALSECRETVALUE123"
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"github_token": token})

    # name-scan 不导出任何内容：该命令未提及名称。
    assert secret_registry.get_secrets_as_env_vars("git remote -v") == {}

    output = f"origin\thttps://{token}@github.com/repo/test.git (fetch)"
    masked = secret_registry.mask_secrets_in_output(output)
    assert token not in masked
    assert masked == "origin\thttps://<secret-hidden>@github.com/repo/test.git (fetch)"


def test_mask_secrets_survives_serialization_round_trip():
    """简历中的掩码仍然存在：_exported_values 不是已序列化。"""
    token = "github_pat_REALSECRETVALUE123"
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"github_token": token})

    restored = SecretRegistry.model_validate_json(
        secret_registry.model_dump_json(context={"expose_secrets": True})
    )
    assert restored._exported_values == {}

    output = f"origin\thttps://{token}@github.com/repo/test.git (fetch)"
    assert token not in restored.mask_secrets_in_output(output)


def test_mask_secrets_tolerates_failing_source():
    """无法解析的源将被跳过； 其他机密仍然是掩码。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {
            "FAILING_SECRET": MyFailingTokenSource(),
            "WORKING_SECRET": MyWorkingTokenSource(),
        }
    )

    masked = secret_registry.mask_secrets_in_output("leak: working-value")
    assert masked == "leak: <secret-hidden>"


def test_mask_secrets_backs_off_failing_source():
    """失败的源会在每个窗口重试一次，而不是在每次掩码调用时重试。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"FAILING_SECRET": MyCountingFailingSource()})

    MyCountingFailingSource.attempts = 0
    for _ in range(25):
        secret_registry.mask_secrets_in_output("unrelated output")
    assert MyCountingFailingSource.attempts == 1

    # 窗口已过：再次重试。
    secret_registry._failed_lookups["FAILING_SECRET"] -= FAILED_LOOKUP_RETRY_SECONDS
    secret_registry.mask_secrets_in_output("unrelated output")
    assert MyCountingFailingSource.attempts == 2


def test_mask_secrets_retries_until_source_succeeds():
    """回退不会永久禁用已恢复源的屏蔽。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"FLAKY": MyRecoveringSource()})

    MyRecoveringSource.fail = True
    assert secret_registry.mask_secrets_in_output("leak: recovered-value") == (
        "leak: recovered-value"
    )

    MyRecoveringSource.fail = False
    secret_registry._failed_lookups["FLAKY"] -= FAILED_LOOKUP_RETRY_SECONDS
    assert secret_registry.mask_secrets_in_output("leak: recovered-value") == (
        "leak: <secret-hidden>"
    )


def test_compile_stream_mask_uses_only_already_resolved_values():
    """流路径无法解析：get_value() 可能会阻塞 I/O。"""
    MyCountingLazySource.attempts = 0
    secret_registry = SecretRegistry()
    secret_registry.update_secrets(
        {"RESOLVED": "abc123", "LAZY": MyCountingLazySource()}
    )
    secret_registry.get_secrets_as_env_vars("echo $RESOLVED")

    def mask(text: str) -> str:
        masker = secret_registry.compile_stream_mask()
        return masker.feed(text) + masker.flush()

    assert mask("leak: abc123") == "leak: <secret-hidden>"
    # 未查询的源不会被查询，因此它的值不会在此处被屏蔽。
    assert mask("leak: lazy-value") == "leak: lazy-value"
    assert MyCountingLazySource.attempts == 0


def test_compile_stream_mask_prefers_the_longest_overlapping_value():
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"SHORT": "abc", "LONG": "abc123"})
    secret_registry.get_secrets_as_env_vars("echo $SHORT $LONG")

    masker = secret_registry.compile_stream_mask()

    assert masker.feed("leak: abc123") + masker.flush() == "leak: <secret-hidden>"


def test_compile_stream_mask_masks_a_value_split_across_chunks():
    """每个块的掩码器无法看到提供者分成两部分的机密。"""
    secret_registry = SecretRegistry()
    secret_registry.update_secrets({"TOKEN": "hunter2"})
    secret_registry.get_secrets_as_env_vars("echo $TOKEN")

    masker = secret_registry.compile_stream_mask()
    released = [masker.feed(piece) for piece in ("leak: ", "hunt", "er2", " done")]
    released.append(masker.flush())

    assert "".join(released) == "leak: <secret-hidden> done"


def test_compile_stream_mask_releases_text_when_nothing_is_registered():
    masker = SecretRegistry().compile_stream_mask()

    assert masker.feed("nothing held back") == "nothing held back"
    assert masker.flush() == ""
