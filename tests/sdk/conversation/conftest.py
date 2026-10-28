"""用于对话测试的共享测试测试夹具。"""

from unittest.mock import Mock


def create_mock_http_client(conversation_id: str | None = None):
    """为 RemoteConversation 创建一个全面的模拟对象 HTTP 客户端。

    该帮助器创建一个模拟对象 httpx.Client，它可以正确处理 POST 和 GET 请求以及适当的
    模拟对象响应。

    Args:
        conversation_id: 用于模拟的可选特定对话 ID。
                        如果未提供，将使用固定的测试 ID。
    """
    # 如果未提供，请使用固定对话 ID 进行测试
    if conversation_id is None:
        conversation_id = "12345678-1234-5678-9abc-123456789abc"

    mock_client = Mock()

    # 模拟对象 POST 对话创建响应
    mock_post_response = Mock()
    mock_post_response.raise_for_status.return_value = None
    mock_post_response.json.return_value = {"id": conversation_id}

    # 模拟对象 GET 事件响应同步
    mock_get_response = Mock()
    mock_get_response.raise_for_status.return_value = None
    mock_get_response.json.return_value = {"items": []}

    # 配置请求方法以返回适当的响应
    def mock_request(method, url, **kwargs):
        if method == "POST":
            return mock_post_response
        elif method == "GET":
            return mock_get_response
        else:
            # 默认响应
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {}
            return response

    mock_client.request = Mock(side_effect=mock_request)
    mock_client.post = Mock(return_value=mock_post_response)
    mock_client.get = Mock(return_value=mock_get_response)

    return mock_client
