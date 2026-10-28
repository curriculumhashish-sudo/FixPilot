"""MCP 工具参数的密钥/环境变量展开测试。

涵盖描述的行为 GitHub issue #3277: MCP 工具参数应扩展机密就像终端命令那样，而不是传递
原始的 "$"SECRET_NAME" through to
the MCP server. 机密服务器返回的值被隐藏在观测结果返回到智能体。
"""

from typing import Any
from unittest.mock import MagicMock

import mcp.types
import pytest

from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.llm import ImageContent
from openhands.sdk.mcp.definition import MCPToolAction, MCPToolObservation
from openhands.sdk.mcp.tool import MCPToolExecutor


@pytest.fixture
def secret_registry() -> SecretRegistry:
    registry = SecretRegistry()
    registry.update_secrets(
        {
            "CUSTOMER_ID": "expanded-customer",
            "API_KEY": "expanded-api-key",
        }
    )
    return registry


@pytest.fixture
def conversation(secret_registry: SecretRegistry) -> MagicMock:
    conv = MagicMock()
    conv.state.secret_registry = secret_registry
    return conv


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.is_connected.return_value = True
    return client


@pytest.fixture
def executor(mock_client: MagicMock) -> MCPToolExecutor:
    return MCPToolExecutor(tool_name="test_tool", client=mock_client)


def _make_result(content=None, is_error=False) -> MagicMock:
    """使用给定的内容块构建模拟对象 CallToolResult。"""
    result = MagicMock(spec=mcp.types.CallToolResult)
    result.content = content or [mcp.types.TextContent(type="text", text="Success")]
    result.isError = is_error
    return result


def _call_and_capture(executor, mock_client, action, conversation, result=None):
    """运行执行器，并返回 (action_sent_to_server, observation_returned)。"""
    captured: dict[str, Any] = {}

    def fake_call(coro_func, **kwargs):
        captured["action"] = kwargs.get("action")
        return MCPToolObservation.from_call_tool_result(
            tool_name="test_tool",
            result=result if result is not None else _make_result(),
        )

    mock_client.call_async_from_sync = fake_call
    observation = executor(action, conversation=conversation)
    assert "action" in captured, "MCP client was not called"
    return captured["action"], observation


@pytest.mark.parametrize(
    "input_data, expected",
    [
        pytest.param(
            {"customer_id": "$CUSTOMER_ID", "api_key": "${API_KEY}"},
            {"customer_id": "expanded-customer", "api_key": "expanded-api-key"},
            id="unbraced-and-braced",
        ),
        pytest.param(
            {
                "existing": "${CUSTOMER_ID:-fallback}",
                "missing": "${NONEXISTENT:-default-value}",
            },
            {"existing": "expanded-customer", "missing": "default-value"},
            id="braced-with-default",
        ),
        pytest.param(
            {
                "auth": {
                    "customer_id": "$CUSTOMER_ID",
                    "credentials": {"token": "${API_KEY}"},
                },
                "ids": ["$CUSTOMER_ID", "static-id"],
            },
            {
                "auth": {
                    "customer_id": "expanded-customer",
                    "credentials": {"token": "expanded-api-key"},
                },
                "ids": ["expanded-customer", "static-id"],
            },
            id="nested-dicts-and-lists",
        ),
        pytest.param(
            {
                "url": "https://$CUSTOMER_ID.example.com/v1",
                "auth": "Bearer ${API_KEY}",
                "pair": "$CUSTOMER_ID:${API_KEY}",
            },
            {
                "url": "https://expanded-customer.example.com/v1",
                "auth": "Bearer expanded-api-key",
                "pair": "expanded-customer:expanded-api-key",
            },
            id="embedded-and-multiple-refs-in-one-string",
        ),
        pytest.param(
            {"price": "$5", "doubled": "$$", "bare": "$", "shell": "$ ls"},
            {"price": "$5", "doubled": "$$", "bare": "$", "shell": "$ ls"},
            id="literal-dollar-is-not-corrupted",
        ),
        pytest.param(
            {"a": "$UNKNOWN", "b": "${ALSO_UNKNOWN}"},
            {"a": "$UNKNOWN", "b": "${ALSO_UNKNOWN}"},
            id="unknown-var-without-default-is-preserved",
        ),
        pytest.param(
            {"count": 5, "ok": True, "ratio": 1.5, "nothing": None},
            {"count": 5, "ok": True, "ratio": 1.5, "nothing": None},
            id="non-string-scalars-pass-through-untouched",
        ),
    ],
)
def test_executor_expands_secrets_in_action_data(
    executor, mock_client, conversation, input_data, expected
):
    """机密引用在操作发送到服务器之前展开。"""
    sent, _ = _call_and_capture(
        executor, mock_client, MCPToolAction(data=input_data), conversation
    )
    assert sent.data == expected


def test_executor_without_conversation_passes_literal_values(executor, mock_client):
    """没有对话就没有机密注册表，因此值保持字面意思。"""
    action = MCPToolAction(
        data={"customer_id": "$CUSTOMER_ID", "api_key": "${API_KEY}"}
    )
    sent, _ = _call_and_capture(executor, mock_client, action, conversation=None)
    assert sent.data == {"customer_id": "$CUSTOMER_ID", "api_key": "${API_KEY}"}


def test_executor_does_not_expand_host_env_vars(
    executor, mock_client, conversation, monkeypatch
):
    """主机环境变量必须将不扩展为工具参数。

    工具参数扩展以 check_env=False 运行，因此机密值到达 MCP 个服务器，但任意主机环境
    变量永远不会到达。 对未注册机密的环境变量的引用保持原义，而同
    一载荷中的已注册机密仍会扩展。
    """
    monkeypatch.setenv("SOME_HOST_ENV", "host-env-value")
    action = MCPToolAction(
        data={"from_env": "$SOME_HOST_ENV", "from_secret": "$CUSTOMER_ID"}
    )
    sent, _ = _call_and_capture(executor, mock_client, action, conversation)
    # Env var 不是注册的机密 -> 保留为文字占位符。
    assert sent.data["from_env"] == "$SOME_HOST_ENV"
    # 已注册机密 -> 照常扩展。
    assert sent.data["from_secret"] == "expanded-customer"


def test_executor_masks_secrets_in_returned_observation(
    executor, mock_client, conversation
):
    """端到端：服务器回显的机密在返回过程中被屏蔽。

    该操作引用 $API_KEY，MCP 服务器回显已解析的值，并且返回到智能体的观测结果必须将其
    屏蔽。 非文本块和其他观测结果字段必须在屏蔽重建后幸存下来。
    """
    secret_value = "expanded-api-key"
    result = _make_result(
        content=[
            mcp.types.TextContent(
                type="text", text=f"authenticated with {secret_value}"
            ),
            mcp.types.ImageContent(type="image", data="aGVsbG8=", mimeType="image/png"),
        ],
    )
    action = MCPToolAction(data={"api_key": "$API_KEY"})

    _, observation = _call_and_capture(
        executor, mock_client, action, conversation, result=result
    )

    # 服务器回显的机密值在观测结果中被屏蔽。
    assert secret_value not in observation.text
    assert "<secret-hidden>" in observation.text
    # 非文本（图像）块不受影响地通过。
    image_blocks = [b for b in observation.content if isinstance(b, ImageContent)]
    assert len(image_blocks) == 1
    assert image_blocks[0].image_urls == ["data:image/png;base64,aGVsbG8="]
    # 其他观测结果字段在 model_copy 重建后仍然存在。
    assert observation.tool_name == "test_tool"
    assert observation.is_error is False


@pytest.mark.parametrize("secret_name", ["CUSTOMER_ID", "API_KEY"])
def test_registry_masks_secret_values_in_text(secret_registry, secret_name):
    """注册的机密值在文本中替换为 <secret-hidden>。"""
    value = secret_registry.get_secret_value(secret_name)  # 还跟踪掩蔽
    assert value is not None
    masked = secret_registry.mask_secrets_in_output(f"leaked {value} here")
    assert value not in masked
    assert "<secret-hidden>" in masked


# --- 失败/不愉快的道路------------------------------------------------


def test_executor_returns_error_observation_on_timeout(
    executor, mock_client, conversation
):
    """客户端超时变成错误观测结果，而不是引发。"""

    def raise_timeout(coro_func, **kwargs):
        raise TimeoutError

    mock_client.call_async_from_sync = raise_timeout

    observation = executor(MCPToolAction(data={"q": "x"}), conversation=conversation)

    assert observation.is_error is True
    assert "timed out" in observation.text
    assert observation.tool_name == "test_tool"


def test_executor_falls_back_to_literal_when_expansion_raises(executor, mock_client):
    """如果机密查找失败，则发送文字操作并继续调用。"""
    conv = MagicMock()
    conv.state.secret_registry.get_secret_value.side_effect = RuntimeError("down")

    action = MCPToolAction(data={"customer_id": "$CUSTOMER_ID"})
    sent, observation = _call_and_capture(executor, mock_client, action, conv)

    # 扩展失败 -> 原始占位符原封不动地发送，没有例外。
    assert sent.data == {"customer_id": "$CUSTOMER_ID"}
    assert observation.is_error is False


def test_executor_returns_unmasked_observation_when_masking_raises(
    executor, mock_client
):
    """如果屏蔽爆炸，则返回原始的观测结果，而不是引发。"""
    conv = MagicMock()
    conv.state.secret_registry.mask_secrets_in_output.side_effect = RuntimeError("down")

    result = _make_result(
        content=[mcp.types.TextContent(type="text", text="hello world")]
    )
    # 无引用 -> 扩展是无操作，隔离屏蔽失败。
    action = MCPToolAction(data={"q": "noop"})
    _, observation = _call_and_capture(
        executor, mock_client, action, conv, result=result
    )

    assert "hello world" in observation.text


def test_executor_without_conversation_does_not_mask(executor, mock_client):
    """没有对话就没有注册表，因此输出不会被屏蔽。"""
    result = _make_result(
        content=[mcp.types.TextContent(type="text", text="token=expanded-api-key")]
    )
    _, observation = _call_and_capture(
        executor, mock_client, MCPToolAction(data={"q": "x"}), None, result=result
    )

    assert "expanded-api-key" in observation.text
    assert "<secret-hidden>" not in observation.text
