"""线程-并行工具执行下 TaskManager 的安全测试。

这些测试通过将并发 ``_create_task`` 呼叫路由到真实的 ``ParallelToolExecutor`` 和真实
的来验证这一保证
``TaskTool.declared_resources()``. 内部有线程屏障
``_generate_ids`` 强制所有线程同时读取 ``len(_tasks)``，从而最大化竞争窗口。

如果 TaskManager 中的内部锁定被删除或破坏，这些测试将失败，并出现重复的任务 ID 和丢失
的字典更新。
"""

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.agent.parallel_executor import ParallelToolExecutor
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.resource_lock_manager import ResourceLockManager
from openhands.sdk.subagent.registry import _reset_registry_for_tests
from openhands.sdk.tool import ToolDefinition
from openhands.tools.preset import register_builtins_agents
from openhands.tools.task.definition import TaskAction, TaskTool
from openhands.tools.task.impl import TaskExecutor
from openhands.tools.task.manager import TaskManager


def _make_llm() -> LLM:
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )


def _make_parent_conversation(tmp_path: Path) -> LocalConversation:
    llm = _make_llm()
    agent = Agent(llm=llm, tools=[])
    return LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
        delete_on_close=False,
    )


def _make_action_event(call_id: str) -> Any:
    """创建一个带有真实TaskAction的模拟对象ActionEvent。"""
    ae = MagicMock()
    ae.tool_name = TaskTool.name
    ae.tool_call_id = call_id
    ae.action = TaskAction(prompt=f"do something ({call_id})")
    return ae


@pytest.fixture(autouse=True)
def _register_agents():
    _reset_registry_for_tests()
    register_builtins_agents()
    yield
    _reset_registry_for_tests()


NUM_CALLS = 10


def _run_concurrent_create_tasks(
    tmp_path: Path,
) -> tuple[TaskManager, list[str]]:
    """运行 NUM_CALLS 并发 _create_task 调用
    ParallelToolExecutor使用真实的TaskTool。

    _generate_ids 内部的障碍迫使线程同时撞击 len(_tasks)，从而对锁施加压力。
    """
    manager = TaskManager()
    parent = _make_parent_conversation(tmp_path)
    manager._ensure_parent(parent)

    mock_conversation = MagicMock(spec=LocalConversation)
    mock_conversation.state.confirmation_policy = MagicMock()

    created_ids: list[str] = []
    id_lock = threading.Lock()

    barrier = threading.Barrier(NUM_CALLS, timeout=10)
    original_generate_ids = manager._generate_ids

    def racy_generate_ids():
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return original_generate_ids()

    task_executor = TaskExecutor(manager=manager)
    task_tools = TaskTool.create(executor=task_executor, description="test")
    task_tool = task_tools[0]
    tools: dict[str, ToolDefinition] = {TaskTool.name: task_tool}

    action_events = [_make_action_event(f"call_{i}") for i in range(NUM_CALLS)]

    def tool_runner(ae: Any) -> list[Any]:
        with (
            patch.object(manager, "_get_conversation", return_value=mock_conversation),
            patch.object(manager, "_generate_ids", side_effect=racy_generate_ids),
        ):
            task = manager._create_task(
                subagent_type="default",
                description=f"task from {ae.tool_call_id}",
            )
            with id_lock:
                created_ids.append(task.id)
        return [MagicMock()]

    executor = ParallelToolExecutor(
        max_workers=NUM_CALLS,
        lock_manager=ResourceLockManager(),
    )
    executor.execute_batch(action_events, tool_runner, tools)

    return manager, created_ids


def test_concurrent_task_ids_are_unique(tmp_path: Path):
    """并发 _create_task 调用必须每次生成一个唯一的任务 ID。

    如果没有 _tasks_lock，线程将读取相同的 len(_tasks) 并为每个线程生成重复的 ID，例
    如“task_00000001”。
    """
    _, created_ids = _run_concurrent_create_tasks(tmp_path)

    unique_ids = set(created_ids)
    assert len(unique_ids) == NUM_CALLS, (
        f"Duplicate task IDs: got {len(unique_ids)} unique "
        f"out of {NUM_CALLS}. IDs: {created_ids}"
    )


def test_concurrent_tasks_all_preserved_in_dict(tmp_path: Path):
    """并发 _create_task 调用必须全部存在于 _tasks 字典中。

    如果没有 _tasks_lock，两个生成相同 ID 的线程会默默地互相覆盖，从而丢失任务。
    """
    manager, _ = _run_concurrent_create_tasks(tmp_path)

    assert len(manager._tasks) == NUM_CALLS, (
        f"Lost updates: only {len(manager._tasks)} tasks in dict, "
        f"expected {NUM_CALLS}. "
        f"Keys: {list(manager._tasks.keys())}"
    )
