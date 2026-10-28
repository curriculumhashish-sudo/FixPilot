"""测试 ParallelToolExecutor。"""

import threading
import time
from typing import Any
from unittest.mock import MagicMock

from openhands.sdk.agent.parallel_executor import ParallelToolExecutor
from openhands.sdk.event.llm_convertible import AgentErrorEvent


def test_default_max_workers():
    executor = ParallelToolExecutor()
    assert executor._max_workers == 1


def test_custom_max_workers():
    executor = ParallelToolExecutor(max_workers=4)
    assert executor._max_workers == 4


def test_empty_batch():
    executor = ParallelToolExecutor()
    results = executor.execute_batch([], lambda x: [MagicMock()])
    assert results == []


def test_single_action_bypasses_thread_pool():
    executor = ParallelToolExecutor()
    action: Any = MagicMock()
    event = MagicMock()

    results = executor.execute_batch([action], lambda a: [event])
    assert len(results) == 1
    assert results[0] == [event]


def test_multi_action_limit_one_runs_sequentially_on_caller_thread():
    """
    当 max_workers=1 时，多个操作在调用方线程上运行，而不是在池线程上运行。
    """
    executor = ParallelToolExecutor(max_workers=1)
    actions: list[Any] = [MagicMock() for _ in range(3)]
    caller_thread = threading.current_thread().name
    observed_threads: list[str] = []

    def tool_runner(action: Any) -> list:
        observed_threads.append(threading.current_thread().name)
        return [MagicMock()]

    executor.execute_batch(actions, tool_runner)

    # 所有调用都应该在调用者的线程上运行，而不是在池线程上运行
    assert all(t == caller_thread for t in observed_threads), (
        f"Expected all calls on {caller_thread}, got {observed_threads}"
    )


def test_result_ordering_preserved_despite_variable_duration():
    """即使后面的操作先完成，结果也按输入顺序排列。"""
    executor = ParallelToolExecutor()
    actions: list[Any] = [MagicMock() for _ in range(5)]

    def tool_runner(action: Any) -> list:
        idx = actions.index(action)
        time.sleep((5 - idx) * 0.01)  # 第一个动作睡眠时间最长
        return [f"result-{idx}"]

    results = executor.execute_batch(actions, tool_runner)

    assert results == [
        ["result-0"],
        ["result-1"],
        ["result-2"],
        ["result-3"],
        ["result-4"],
    ]


def test_actions_run_concurrently():
    """验证操作实际上是并行运行的，而不是顺序运行的。"""
    executor = ParallelToolExecutor(max_workers=4)
    actions: list[Any] = [MagicMock() for _ in range(4)]
    max_concurrent = [0]
    current = [0]
    lock = threading.Lock()

    def tool_runner(action: Any) -> list:
        with lock:
            current[0] += 1
            max_concurrent[0] = max(max_concurrent[0], current[0])
        time.sleep(0.05)
        with lock:
            current[0] -= 1
        return [MagicMock()]

    executor.execute_batch(actions, tool_runner)

    assert max_concurrent[0] > 1


def test_concurrency_limited_by_max_workers():
    """并发未超出配置的限制。"""
    executor = ParallelToolExecutor(max_workers=2)
    actions: list[Any] = [MagicMock() for _ in range(6)]
    concurrent_count: list[int] = []
    lock = threading.Lock()
    current = [0]

    def tool_runner(action: Any) -> list:
        with lock:
            current[0] += 1
            concurrent_count.append(current[0])
        time.sleep(0.02)
        with lock:
            current[0] -= 1
        return [MagicMock()]

    executor.execute_batch(actions, tool_runner)

    assert max(concurrent_count) <= 2


def test_multiple_events_per_action():
    """tool_runner 可以为单个操作返回多个事件。"""
    executor = ParallelToolExecutor()
    actions: list[Any] = [MagicMock(), MagicMock()]

    def tool_runner(action: Any) -> list:
        return [MagicMock(name="obs"), MagicMock(name="followup")]

    results = executor.execute_batch(actions, tool_runner)

    assert len(results) == 2
    assert len(results[0]) == 2
    assert len(results[1]) == 2


def _make_action(name: str = "test_tool", tool_call_id: str = "call_1") -> Any:
    """创建包含必填字段的模拟对象 ActionEvent。"""
    action = MagicMock()
    action.tool_name = name
    action.tool_call_id = tool_call_id
    return action


def test_error_returns_agent_error_event_for_single_action():
    """单个操作错误包含在 AgentErrorEvent 中。"""
    executor = ParallelToolExecutor()
    action = _make_action("my_tool", "call_1")

    def tool_runner(a: Any) -> list:
        raise ValueError("Test error")

    results = executor.execute_batch([action], tool_runner)
    assert len(results) == 1
    assert len(results[0]) == 1
    assert isinstance(results[0][0], AgentErrorEvent)
    assert "Test error" in results[0][0].error


def test_error_returns_agent_error_event_in_batch():
    """
    ValueErrors批量产生AgentErrorEvents成功的结果被保存。
    """
    executor = ParallelToolExecutor()
    actions = [
        _make_action("tool_a", "call_0"),
        _make_action("tool_b", "call_1"),
        _make_action("tool_c", "call_2"),
    ]
    success_event = MagicMock()

    def tool_runner(action: Any) -> list:
        if action.tool_call_id == "call_1":
            raise ValueError("action 1 failed")
        time.sleep(0.02)
        return [success_event]

    results = executor.execute_batch(actions, tool_runner)

    assert len(results) == 3
    assert results[0] == [success_event]
    assert len(results[1]) == 1
    assert isinstance(results[1][0], AgentErrorEvent)
    assert "action 1 failed" in results[1][0].error
    assert results[2] == [success_event]


def test_all_exceptions_wrapped_in_agent_error_event():
    """所有异常都会被捕获并转换为 AgentErrorEvent。"""
    executor = ParallelToolExecutor()
    actions = [
        _make_action("tool_a", "call_0"),
        _make_action("tool_b", "call_1"),
    ]
    success_event = MagicMock()

    def tool_runner(action: Any) -> list:
        if action.tool_call_id == "call_1":
            raise RuntimeError("something broke")
        return [success_event]

    results = executor.execute_batch(actions, tool_runner)

    assert len(results) == 2
    assert results[0] == [success_event]
    assert isinstance(results[1][0], AgentErrorEvent)
    assert "something broke" in results[1][0].error


def test_nested_execution_no_deadlock():
    """嵌套 execute_batch（子智能体场景）不会死锁。

    外层执行器 max_workers 的值为 1。 子智能体工具创建自己的执行器 - 因为池是每个实例
    的，所以没有线程饥饿。
    """
    outer_executor = ParallelToolExecutor(max_workers=1)

    def inner_tool_runner(action: Any) -> list:
        return [f"inner-{action}"]

    def outer_tool_runner(action: Any) -> list:
        if action == "subagent":
            inner_executor = ParallelToolExecutor(max_workers=2)
            inner_results = inner_executor.execute_batch(
                ["a", "b"],  # type: ignore[arg-type]
                inner_tool_runner,
            )
            return [item for sublist in inner_results for item in sublist]
        return [f"leaf-{action}"]

    results = outer_executor.execute_batch(
        ["subagent"],  # type: ignore[arg-type]
        outer_tool_runner,
    )

    assert results == [["inner-a", "inner-b"]]
