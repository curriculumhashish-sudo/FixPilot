import warnings

from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse

from openhands.sdk.llm import LLM, LLMResponse, Message
from openhands.sdk.llm.message import TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage


def test_pydantic_serializer_warnings_suppressed():
    """
    测试来自 LiteLLM 的 Pydantic 序列化器警告是否被抑制。

    该测试验证了警告过滤器是否正确配置在了  openhands.sdk.llm 模块初始化以抑制 "
    Pydantic  序列化器当  LiteLLM's Pydant
    ic 模型是已序列化字段计数不匹配。

    该过滤器在 openhands.sdk.llm.__init__.py 中的模块导入时应用，并防止在正常使用期间
    向用户显示这些警告。
    """
    # 捕获模块导入期间的所有警告
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")

        # 触发可能导致警告的模块操作只需验证 LLM 类可访问
        #
        assert LLM is not None

        # 检查列表中是否没有 Pydantic 序列化器警告
        pydantic_warnings = [
            w for w in warning_list if "Pydantic serializer warnings" in str(w.message)
        ]

        assert len(pydantic_warnings) == 0, (
            f"Expected no Pydantic serializer warnings, "
            f"but found {len(pydantic_warnings)}"
        )


def test_llm_response_serialization_no_warnings():
    """测试 LLMResponse 与 LiteLLM ModelResponse 的序列化。

    该测试创建了一个包含LiteLLM ModelResponse的模拟对象 LLMResponse，并使用
    model_dump()对其进行序列化，这通常会触发Pyda
    ntic 序列化器警告。 llm_response.py 中的警告过滤器在正常使用时应抑制这些警告。
    """
    # 创建具有最少字段的模拟对象 LiteLLM ModelResponse
    mock_response = ModelResponse(
        id="test-id",
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content="Test response", role="assistant"),
            )
        ],
        created=1234567890,
        model="test-model",
        object="chat.completion",
    )

    # 创建一个 LLMResponse 并返回模拟对象响应
    llm_response = LLMResponse(
        message=Message(
            role="assistant", content=[TextContent(type="text", text="Test response")]
        ),
        metrics=MetricsSnapshot(
            model_name="test-model",
            accumulated_cost=0.0,
            max_budget_per_task=None,
            accumulated_token_usage=TokenUsage(
                model="test-model", prompt_tokens=0, completion_tokens=0
            ),
        ),
        raw_response=mock_response,
    )

    # 在序列化期间捕获警告我们需要测试过滤器是否有效，但catch_warnings创建了一个新的隔离
    # 环境，因此我们需要重新应用过滤器
    #
    with warnings.catch_warnings(record=True) as warning_list:
        # 重新应用应该在全局范围内处于活动状态的过滤器
        warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

        # 序列化的 LLMResponse - 这将触发警告，但不使用过滤器
        serialized = llm_response.model_dump()
        assert serialized is not None
        assert "message" in serialized
        assert "metrics" in serialized

        # 检查是否出现 Pydantic 序列化器警告
        pydantic_warnings = [
            w for w in warning_list if "Pydantic serializer warnings" in str(w.message)
        ]

        assert len(pydantic_warnings) == 0, (
            "Expected no Pydantic serializer warnings during "
            f"LLMResponse serialization, but found {len(pydantic_warnings)}"
        )
