def test_llm_malformed_action_error_default():
    """使用默认消息测试 LLMMalformedActionError。"""
    from openhands.sdk.llm.exceptions import LLMMalformedActionError

    error = LLMMalformedActionError()
    assert str(error) == "Malformed response"
    assert error.message == "Malformed response"


def test_llm_malformed_action_error_custom():
    """使用自定义消息测试 LLMMalformedActionError。"""
    from openhands.sdk.llm.exceptions import LLMMalformedActionError

    custom_message = "Custom malformed error"
    error = LLMMalformedActionError(custom_message)
    assert str(error) == custom_message
    assert error.message == custom_message


def test_llm_no_action_error_default():
    """使用默认消息测试 LLMNoActionError。"""
    from openhands.sdk.llm.exceptions import LLMNoActionError

    error = LLMNoActionError()
    assert str(error) == "Agent must return an action"
    assert error.message == "Agent must return an action"


def test_llm_no_action_error_custom():
    """使用自定义消息测试 LLMNoActionError。"""
    from openhands.sdk.llm.exceptions import LLMNoActionError

    custom_message = "Custom no action error"
    error = LLMNoActionError(custom_message)
    assert str(error) == custom_message
    assert error.message == custom_message


def test_llm_response_error_default():
    """使用默认消息测试 LLMResponseError。"""
    from openhands.sdk.llm.exceptions import LLMResponseError

    error = LLMResponseError()
    assert str(error) == "Failed to retrieve action from LLM response"
    assert error.message == "Failed to retrieve action from LLM response"


def test_llm_response_error_custom():
    """使用自定义消息测试 LLMResponseError。"""
    from openhands.sdk.llm.exceptions import LLMResponseError

    custom_message = "Custom response error"
    error = LLMResponseError(custom_message)
    assert str(error) == custom_message
    assert error.message == custom_message


def test_llm_context_window_exceed_error_default():
    """使用默认消息测试 LLMContextWindowExceedError。"""
    from openhands.sdk.llm.exceptions import LLMContextWindowExceedError

    error = LLMContextWindowExceedError()
    expected_message = "Conversation history longer than LLM context window limit. "
    expected_message += "Consider enabling a condenser or shortening inputs."
    assert str(error) == expected_message
    assert error.message == expected_message


def test_llm_context_window_exceed_error_custom():
    """使用自定义消息测试 LLMContextWindowExceedError。"""
    from openhands.sdk.llm.exceptions import LLMContextWindowExceedError

    custom_message = "Custom context window error"
    error = LLMContextWindowExceedError(custom_message)
    assert str(error) == custom_message
    assert error.message == custom_message


def test_llm_malformed_conversation_history_error_default():
    """使用默认消息测试 LLMMalformedConversationHistoryError。"""
    from openhands.sdk.llm.exceptions import LLMMalformedConversationHistoryError

    error = LLMMalformedConversationHistoryError()
    expected_message = "Conversation history produced an invalid LLM request. "
    expected_message += (
        "Consider retrying with condensed history and investigating the event stream."
    )
    assert str(error) == expected_message
    assert error.message == expected_message


def test_llm_malformed_conversation_history_error_custom():
    """使用自定义消息测试 LLMMalformedConversationHistoryError。"""
    from openhands.sdk.llm.exceptions import LLMMalformedConversationHistoryError

    custom_message = "Custom malformed history error"
    error = LLMMalformedConversationHistoryError(custom_message)
    assert str(error) == custom_message
    assert error.message == custom_message


def test_function_call_not_exists_error():
    """测试FunctionCallNotExistsError。"""
    from openhands.sdk.llm.exceptions import FunctionCallNotExistsError

    message = "Function 'unknown_function' does not exist"
    error = FunctionCallNotExistsError(message)
    assert str(error) == message
    assert error.message == message


def test_user_cancelled_error_default():
    """使用默认消息测试 UserCancelledError。"""
    from openhands.sdk.llm.exceptions import UserCancelledError

    error = UserCancelledError()
    assert str(error) == "User cancelled the request"


def test_user_cancelled_error_custom():
    """使用自定义消息测试 UserCancelledError。"""
    from openhands.sdk.llm.exceptions import UserCancelledError

    custom_message = "Custom cancellation message"
    error = UserCancelledError(custom_message)
    assert str(error) == custom_message


def test_operation_cancelled_error_default():
    """使用默认消息测试 OperationCancelled。"""
    from openhands.sdk.llm.exceptions import OperationCancelled

    error = OperationCancelled()
    assert str(error) == "Operation was cancelled"


def test_operation_cancelled_error_custom():
    """使用自定义消息测试 OperationCancelled。"""
    from openhands.sdk.llm.exceptions import OperationCancelled

    custom_message = "Custom operation cancelled message"
    error = OperationCancelled(custom_message)
    assert str(error) == custom_message
