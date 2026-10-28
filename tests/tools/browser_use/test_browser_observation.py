"""测试 BrowserObservation 包装器行为。"""

from openhands.sdk.llm.message import ImageContent, TextContent
from openhands.tools.browser_use.definition import BrowserObservation


def test_browser_observation_basic_output():
    """使用输出测试基本的 BrowserObservation 创建。"""
    observation = BrowserObservation.from_text(text="Test output")

    assert observation.text == "Test output"
    assert observation.is_error is False
    assert observation.screenshot_data is None


def test_browser_observation_with_error():
    """测试 BrowserObservation 有错误。"""
    observation = BrowserObservation.from_text(text="Test error", is_error=True)

    assert observation.text == "Test error"
    assert observation.is_error is True
    assert observation.screenshot_data is None


def test_browser_observation_with_screenshot():
    """使用屏幕截图数据测试 BrowserObservation。"""
    screenshot_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=="  # noqa: E501
    observation = BrowserObservation.from_text(
        text="Screenshot taken", screenshot_data=screenshot_data
    )

    assert observation.text == "Screenshot taken"
    assert observation.is_error is False
    assert observation.screenshot_data == screenshot_data


def test_browser_observation_to_llm_content_text_only():
    """仅使用文本测试 to_llm_content 属性。"""
    observation = BrowserObservation.from_text(text="Test output")
    agent_obs = observation.to_llm_content

    assert len(agent_obs) == 1
    assert isinstance(agent_obs[0], TextContent)
    assert agent_obs[0].text == "Test output"


def test_browser_observation_to_llm_content_with_screenshot():
    """使用屏幕截图测试 to_llm_content 属性。"""
    screenshot_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=="  # noqa: E501
    observation = BrowserObservation.from_text(
        text="Screenshot taken", screenshot_data=screenshot_data
    )
    agent_obs = observation.to_llm_content

    assert len(agent_obs) == 2
    assert isinstance(agent_obs[0], TextContent)
    assert agent_obs[0].text == "Screenshot taken"
    assert isinstance(agent_obs[1], ImageContent)
    assert len(agent_obs[1].image_urls) == 1
    assert agent_obs[1].image_urls[0].startswith("data:image/png;base64,")
    assert screenshot_data in agent_obs[1].image_urls[0]


def test_browser_observation_to_llm_content_with_error():
    """测试 to_llm_content 属性有错误。"""
    observation = BrowserObservation.from_text(text="Test error", is_error=True)
    agent_obs = observation.to_llm_content

    assert len(agent_obs) == 2
    assert isinstance(agent_obs[0], TextContent)
    assert agent_obs[0].text == BrowserObservation.ERROR_MESSAGE_HEADER
    assert isinstance(agent_obs[1], TextContent)
    assert "Test error" in agent_obs[1].text


def test_browser_observation_output_truncation():
    """测试非常长的输出的输出截断。"""
    # 创建一个很长的输出字符串
    long_output = "x" * 100000  # 10万个字符
    observation = BrowserObservation.from_text(text=long_output)

    agent_obs = observation.to_llm_content

    # 应截断为 MAX_BROWSER_OUTPUT_SIZE (50000)
    assert len(agent_obs) == 1
    assert isinstance(agent_obs[0], TextContent)
    assert len(agent_obs[0].text) <= 50000
    assert "<response clipped>" in agent_obs[0].text


def test_browser_observation_screenshot_data_url_conversion():
    """测试屏幕截图数据是否正确转换为数据 URL。"""
    screenshot_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAI9jU77zgAAAABJRU5ErkJggg=="  # noqa: E501
    observation = BrowserObservation.from_text(
        text="Test", screenshot_data=screenshot_data
    )

    agent_obs = observation.to_llm_content
    expected_data_url = f"data:image/png;base64,{screenshot_data}"

    assert len(agent_obs) == 2
    assert isinstance(agent_obs[1], ImageContent)
    assert agent_obs[1].image_urls[0] == expected_data_url


def test_browser_observation_empty_screenshot_handling():
    """测试空或 None 屏幕截图数据的处理。"""
    observation = BrowserObservation.from_text(text="Test", screenshot_data="")
    agent_obs = observation.to_llm_content
    assert len(agent_obs) == 1  # 只有文字内容，没有图片

    observation = BrowserObservation.from_text(text="Test", screenshot_data=None)
    agent_obs = observation.to_llm_content
    assert len(agent_obs) == 1  # 只有文字内容，没有图片


def test_browser_observation_mime_type_detection():
    """测试不同图像格式的 MIME 类型检测。"""
    test_cases = [
        (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",  # noqa: E501
            "image/png",
        ),
        (
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/",  # noqa: E501
            "image/jpeg",
        ),
        (
            "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
            "image/gif",
        ),
        (
            "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAQAcJaQAA3AA/v3AgAA=",
            "image/webp",
        ),
        (
            "AAAABBBBCCCC",  # 未知格式
            "image/png",  # 回落至 PNG
        ),
    ]

    for screenshot_data, expected_mime_type in test_cases:
        observation = BrowserObservation.from_text(
            text="Test", screenshot_data=screenshot_data
        )
        agent_obs = observation.to_llm_content

        assert len(agent_obs) == 2
        assert isinstance(agent_obs[1], ImageContent)
        assert (
            agent_obs[1].image_urls[0].startswith(f"data:{expected_mime_type};base64,")
        )
