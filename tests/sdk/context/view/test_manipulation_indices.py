from openhands.sdk.context.view.manipulation_indices import ManipulationIndices
from tests.sdk.context.view.conftest import message_event  # noqa: F401


def test_complete_empty_list() -> None:
    """使用空事件列表测试完整的操作索引。"""
    manipulation_indices = ManipulationIndices.complete([])
    assert manipulation_indices == {0}


def test_complete_single_message_event() -> None:
    """使用单个消息事件测试完整的操作索引。"""
    manipulation_indices = ManipulationIndices.complete([message_event("Event 0")])
    assert manipulation_indices == {0, 1}


def test_complete_multiple_message_events() -> None:
    """使用多个消息事件测试完整的操作索引。"""
    manipulation_indices = ManipulationIndices.complete(
        [
            message_event("Event 0"),
            message_event("Event 1"),
            message_event("Event 2"),
        ]
    )
    assert manipulation_indices == {0, 1, 2, 3}
