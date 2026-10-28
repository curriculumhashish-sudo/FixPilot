import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.hooks.config import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.subagent.registry import (
    _reset_registry_for_tests,
    register_agent,
)
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.tools.preset import register_builtins_agents
from openhands.tools.task.manager import (
    Task,
    TaskManager,
    TaskStatus,
)


def _make_llm() -> LLM:
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )


def _make_parent_conversation(
    tmp_path: Path,
    persistence_dir: str | Path | None = None,
) -> LocalConversation:
    """为经理创建一个真正的（最少的）家长对话。"""
    llm = _make_llm()
    agent = Agent(llm=llm, tools=[])
    return LocalConversation(
        agent=agent,
        workspace=str(tmp_path),
        visualizer=None,
        delete_on_close=False,
        persistence_dir=persistence_dir,
    )


def _manager_with_parent(
    tmp_path: Path,
    persistence_dir: str | Path | None = None,
) -> tuple[TaskManager, LocalConversation]:
    """返回已设置父对话的 TaskManager。"""
    manager = TaskManager()
    parent = _make_parent_conversation(tmp_path, persistence_dir=persistence_dir)
    manager._ensure_parent(parent)
    return manager, parent


class TestTaskStatusEnum:
    def test_all_values(self):
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.ERROR == "error"

    def test_is_str_enum(self):
        assert isinstance(TaskStatus.RUNNING, str)
        assert f"status={TaskStatus.RUNNING}" == "status=running"


class TestTaskState:
    """测试 TaskState"""

    def test_initial_state(self):
        """TaskState 应该以 'running' 状态开始。"""
        state = Task(
            id="test_1",
            conversation=None,
            status=TaskStatus.RUNNING,
            conversation_id=uuid.uuid4(),
        )
        assert state.status == "running"
        assert state.result is None
        assert state.error is None

    @pytest.mark.parametrize("result", ["Done!", ""])
    def test_set_completed(self, result):
        """set_completed 应更新状态和结果。"""
        state = Task(
            id="test_1",
            conversation=None,
            status=TaskStatus.RUNNING,
            conversation_id=uuid.uuid4(),
        )
        state.set_result(result)
        assert state.status == "completed"
        assert state.result == result
        assert state.error is None

    def test_set_error(self):
        """set_error 应更新状态、错误和结果。"""
        state = Task(
            id="test_1",
            conversation=None,
            status=TaskStatus.RUNNING,
            conversation_id=uuid.uuid4(),
        )
        state.set_error("Something went wrong")
        assert state.status == "error"
        assert state.error == "Something went wrong"
        assert state.result is None


class TestTaskManager:
    """测试 TaskManager。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_init_defaults(self):
        """管理器应使用正确的默认值进行初始化。"""
        manager = TaskManager()
        assert len(manager._tasks) == 0
        assert manager._parent_conversation is None

    def test_persistence_dir_none_at_init(self):
        manager = TaskManager()
        assert manager._persistence_dir is None

    def test_generate_task_id(self):
        """生成的任务 ID 应该是唯一的并带有前缀。"""
        manager = TaskManager()

        tasks_ids: list[str] = []
        for j in range(10):
            id_, _ = manager._generate_ids()
            tasks_ids.append(id_)
            manager._tasks[id_] = Task(
                id=id_,
                conversation=None,
                status=TaskStatus.RUNNING,
                conversation_id=uuid.uuid4(),
            )
            assert id_.startswith("task_")

        assert len(tasks_ids) == len(set(tasks_ids))

    def test_parent_conversation_raises_before_set(self):
        """在第一次调用之前访问 parent_conversation 应该引发。"""
        manager = TaskManager()
        with pytest.raises(RuntimeError, match="Parent conversation not set"):
            _ = manager.parent_conversation

    def test_ensure_parent_sets_once(self):
        """_ensure_parent 应该只在第一次调用时设置父级。"""
        manager = TaskManager()
        conv1 = MagicMock()
        conv2 = MagicMock()

        manager._ensure_parent(conv1)
        assert manager._parent_conversation is conv1

        manager._ensure_parent(conv2)
        # 还是第一个
        assert manager._parent_conversation is conv1

    def test_returns_running_task_state(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()

        task = manager._create_task(
            subagent_type="general-purpose",
            description="test task",
        )
        assert isinstance(task, Task)
        assert task.status == TaskStatus.RUNNING
        assert task.id.startswith("task_")
        assert task.conversation is not None
        assert task.result is None
        assert task.error is None

    def test_registers_uuid(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()

        task = manager._create_task(subagent_type="general-purpose", description=None)
        assert task.id in manager._tasks
        assert isinstance(manager._tasks[task.id].conversation_id, uuid.UUID)

    def test_create_task_uses_parent_max_iteration_when_factory_is_none(self, tmp_path):
        """当工厂有 None 时，回退方案发送给父母的 max_iteration_per_run。"""
        register_builtins_agents()
        llm = _make_llm()
        agent = Agent(llm=llm, tools=[])
        parent = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            visualizer=None,
            delete_on_close=False,
            max_iteration_per_run=100,
        )
        manager = TaskManager()
        manager._ensure_parent(parent)

        task = manager._create_task(subagent_type="default", description=None)
        assert task.conversation is not None
        assert task.conversation.max_iteration_per_run == 100

    def test_create_task_prefers_factory_max_iteration_over_parent(self, tmp_path):
        """工厂定义 max_iteration_per_run 优先于父级。"""
        from openhands.sdk.subagent.registry import agent_definition_to_factory

        agent_def = AgentDefinition(
            name="limited_agent",
            description="Agent with iteration limit",
            model="inherit",
            tools=[],
            system_prompt="You are limited.",
            max_iteration_per_run=50,
        )
        factory_func = agent_definition_to_factory(agent_def)
        register_agent(
            name="limited_agent",
            factory_func=factory_func,
            description=agent_def,
        )

        llm = _make_llm()
        agent = Agent(llm=llm, tools=[])
        parent = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            visualizer=None,
            delete_on_close=False,
            max_iteration_per_run=200,
        )
        manager = TaskManager()
        manager._ensure_parent(parent)

        task = manager._create_task(subagent_type="limited_agent", description=None)
        assert task.conversation is not None
        assert task.conversation.max_iteration_per_run == 50

    def test_resume_unknown_task_raises(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            manager._resume_task(
                resume="task_nonexistent", subagent_type="general-purpose"
            )

    def test_resume_after_evict(self, tmp_path):
        """创建、驱逐然后恢复的任务应该可以工作。"""
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()

        # 创建和退出任务（模拟已完成的首次运行）
        task = manager._create_task(subagent_type="general-purpose", description=None)
        original_id = task.id
        original_uuid = task.conversation_id
        manager._evict_task(task)
        assert original_id in manager._tasks

        # 恢复它
        resumed = manager._resume_task(
            resume=original_id, subagent_type="general-purpose"
        )
        assert resumed.id == original_id
        assert resumed.conversation_id == original_uuid
        assert resumed.status == TaskStatus.RUNNING
        assert resumed.conversation is not None
        assert resumed.conversation.state.id == original_uuid

    def test_default_agent_type(self, tmp_path):
        """'default' 应该返回智能体而不引发。"""
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()
        agent = manager._get_sub_agent("general-purpose")
        assert isinstance(agent, Agent)
        assert agent.llm.stream is False

    def test_registered_agent_type(self, tmp_path):
        """注册工厂应生产正确的智能体。"""
        factory_called_with: list[LLM] = []

        def factory(llm: LLM) -> Agent:
            factory_called_with.append(llm)
            return Agent(llm=llm, tools=[])

        register_agent(
            name="test_expert",
            factory_func=factory,
            description="test",
        )

        manager, _ = _manager_with_parent(tmp_path)
        agent = manager._get_sub_agent("test_expert")
        assert isinstance(agent, Agent)
        assert len(factory_called_with) == 1
        assert factory_called_with[0].stream is False

    def test_unknown_agent_type_raises(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        with pytest.raises(ValueError, match="Unknown agent"):
            manager._get_sub_agent("nonexistent_agent")

    def test_close(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        assert manager._persistence_dir is not None
        assert manager._persistence_dir.exists()

        manager._tasks["tasks_123"] = Task(
            id="tasks_123",
            conversation_id=uuid.uuid4(),
            status=TaskStatus.RUNNING,
        )

        manager.close()

        assert not manager._persistence_dir.exists()
        assert len(manager._tasks) == 0

    def test_returns_local_conversation(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()
        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description="quiz",
            task_id=task_id,
            subagent_type="default",
            worker_agent=agent,
            max_iteration_per_run=500,
            conversation_id=conversation_id,
        )
        assert isinstance(conv, LocalConversation)
        assert conv.max_iteration_per_run == 500

    def test_persistence_dir_is_tmp_dir(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()
        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description=None,
            max_iteration_per_run=500,
            task_id=task_id,
            subagent_type="default",
            worker_agent=agent,
            conversation_id=conversation_id,
        )
        # 对话的持久化目录应位于经理的 tmp_dir 目录下
        persistence_dir = conv.state.persistence_dir
        assert persistence_dir is not None
        conv_persistence = Path(persistence_dir)
        assert str(conv_persistence).startswith(str(manager._persistence_dir))

    def test_no_visualizer_when_parent_has_none(self, tmp_path):
        manager, _ = _manager_with_parent(tmp_path)
        register_builtins_agents()
        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description="test",
            max_iteration_per_run=500,
            task_id=task_id,
            subagent_type="default",
            conversation_id=conversation_id,
            worker_agent=agent,
        )
        assert conv._visualizer is None

    def test_sub_agents_inherit_parent_prompt_cache_key(self, tmp_path):
        """同级子智能体共享父级的 OpenAI 前缀缓存分片。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()
        parent_key = str(parent.state.id)

        sub_keys = []
        for _ in range(2):
            task_id, conversation_id = manager._generate_ids()
            agent = manager._get_sub_agent("general-purpose")
            conv = manager._get_conversation(
                description=None,
                max_iteration_per_run=500,
                task_id=task_id,
                subagent_type="default",
                conversation_id=conversation_id,
                worker_agent=agent,
            )
            sub_keys.append(conv.get_llm_call_context().prompt_cache_key)

        assert sub_keys == [parent_key, parent_key]

    def test_marks_conversation_as_delegate_with_linking_metadata(self, tmp_path):
        """子智能体对话必须建立在分离的跟踪内，
        标记为原始 task_id/subagent_type（软件-智能体-SDK#4365）。 练习真实的
        `detached_delegate_context`，而不是它的模拟对象。
        """
        from openhands.sdk.observability import laminar as lam

        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()
        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        with (
            patch("lmnr.Laminar") as mock_laminar,
            patch(
                "openhands.sdk.conversation.base.start_root_span",
                return_value=None,
            ) as mock_start_root_span,
        ):
            mock_laminar.get_laminar_span_context.return_value = None
            lam._observability_enabled = True
            try:
                manager._get_conversation(
                    description="test",
                    max_iteration_per_run=500,
                    task_id=task_id,
                    subagent_type="general-purpose",
                    conversation_id=conversation_id,
                    worker_agent=agent,
                )
            finally:
                lam._observability_enabled = False

        mock_start_root_span.assert_called_once()
        kwargs = mock_start_root_span.call_args.kwargs
        assert kwargs["tags"] == ["delegate"]
        assert kwargs["metadata"] == {
            "is_delegate": True,
            "task_id": task_id,
            "subagent_type": "general-purpose",
            "parent_session_id": str(parent.state.id),
        }

    def test_resume_task_marks_conversation_as_delegate(self, tmp_path):
        """恢复任务还必须构建一个分离的、带有委托标记的跟踪。"""
        from openhands.sdk.observability import laminar as lam

        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        task = manager._create_task(subagent_type="general-purpose", description=None)
        manager._evict_task(task)

        with (
            patch("lmnr.Laminar") as mock_laminar,
            patch(
                "openhands.sdk.conversation.base.start_root_span",
                return_value=None,
            ) as mock_start_root_span,
        ):
            mock_laminar.get_laminar_span_context.return_value = None
            lam._observability_enabled = True
            try:
                manager._resume_task(resume=task.id, subagent_type="general-purpose")
            finally:
                lam._observability_enabled = False

        mock_start_root_span.assert_called_once()
        kwargs = mock_start_root_span.call_args.kwargs
        assert kwargs["tags"] == ["delegate"]
        assert kwargs["metadata"] == {
            "is_delegate": True,
            "task_id": task.id,
            "subagent_type": "general-purpose",
            "parent_session_id": str(parent.state.id),
        }

    def test_delegate_metadata_includes_parent_span_link(self, tmp_path):
        """当父跨度处于活动状态时，其 trace_id/span_id/tool_call_id 必须
        被合并到委托的可观察性元数据中。"""
        from types import SimpleNamespace

        from openhands.sdk.observability import laminar as lam

        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()
        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        parent_ctx = SimpleNamespace(
            trace_id="11111111-1111-1111-1111-111111111111",
            span_id="22222222-2222-2222-2222-222222222222",
            metadata={"tool_call_id": "call_abc123"},
        )

        with (
            patch("lmnr.Laminar") as mock_laminar,
            patch(
                "openhands.sdk.conversation.base.start_root_span",
                return_value=None,
            ) as mock_start_root_span,
        ):
            mock_laminar.get_laminar_span_context.return_value = parent_ctx
            lam._observability_enabled = True
            try:
                manager._get_conversation(
                    description="test",
                    max_iteration_per_run=500,
                    task_id=task_id,
                    subagent_type="general-purpose",
                    conversation_id=conversation_id,
                    worker_agent=agent,
                )
            finally:
                lam._observability_enabled = False

        kwargs = mock_start_root_span.call_args.kwargs
        assert kwargs["metadata"] == {
            "is_delegate": True,
            "task_id": task_id,
            "subagent_type": "general-purpose",
            "parent_session_id": str(parent.state.id),
            "delegate.parent_trace_id": str(parent_ctx.trace_id),
            "delegate.parent_span_id": str(parent_ctx.span_id),
            "tool_call_id": "call_abc123",
        }


def _make_task_with_mock_conv(task_id: str, **conv_kwargs) -> Task:
    """创建一个包含 MagicMock 对话的任务，绕过 Pydantic 验证。"""
    mock_conv = MagicMock(**conv_kwargs)
    # 默认为 FINISHED 运行； 非 FINISHED 状态现在显示为错误，因此覆盖
    # state.execution_status 来测试卡住/暂停的路径。
    #
    mock_conv.state.execution_status = ConversationExecutionStatus.FINISHED
    return Task.model_construct(
        id=task_id,
        conversation_id=uuid.uuid4(),
        conversation=mock_conv,
        status=TaskStatus.RUNNING,
        result=None,
        error=None,
    )


class TestRunTask:
    """测试 TaskManager._run_task。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_raises_when_conversation_is_none(self, tmp_path):
        """如果任务没有对话，_run_task 应该引发 RuntimeError。"""
        manager, _ = _manager_with_parent(tmp_path)
        task = Task(
            id="task_00000001",
            conversation_id=uuid.uuid4(),
            conversation=None,
            status=TaskStatus.RUNNING,
        )
        with pytest.raises(RuntimeError, match="has no conversation"):
            manager._run_task(task=task, prompt="do something")

    @patch(
        "openhands.tools.task.manager.get_agent_final_response",
        return_value="task result",
    )
    def test_successful_run_sets_result(self, mock_get_response, tmp_path):
        """成功运行应将状态设置为 COMPLETED 并填充结果。"""
        manager, _ = _manager_with_parent(tmp_path)

        task = _make_task_with_mock_conv("task_00000001")
        manager._tasks[task.id] = task

        result = manager._run_task(task=task, prompt="do something")

        assert result.status == TaskStatus.COMPLETED
        assert result.result == "task result"
        assert result.error is None
        conversation = task.conversation
        assert conversation is not None
        conversation.send_message.assert_called_once_with(  # type: ignore[attr-defined]
            "do something", sender=None
        )
        conversation.run.assert_called_once()  # type: ignore[attr-defined]

    @patch(
        "openhands.tools.task.manager.get_agent_final_response",
        return_value="task result",
    )
    def test_run_evicts_conversation_after_success(self, mock_get_response, tmp_path):
        """成功运行后，任务的对话应该被驱逐。"""
        manager, _ = _manager_with_parent(tmp_path)

        task = _make_task_with_mock_conv("task_00000001")
        mock_conv = task.conversation
        manager._tasks[task.id] = task

        manager._run_task(task=task, prompt="do something")

        # 驱逐后，存储的任务不应有任何对话
        assert manager._tasks[task.id].conversation is None
        assert mock_conv is not None
        mock_conv.pause.assert_called_once()  # type: ignore[attr-defined]
        mock_conv.close.assert_called_once()  # type: ignore[attr-defined]

    def test_run_sets_error_on_exception(self, tmp_path):
        """如果对话发生，则任务应设置为 ERROR。"""
        manager, _ = _manager_with_parent(tmp_path)

        task = _make_task_with_mock_conv(
            "task_00000001", **{"run.side_effect": RuntimeError("agent exploded")}
        )
        manager._tasks[task.id] = task

        result = manager._run_task(task=task, prompt="do something")

        assert result.status == TaskStatus.ERROR
        assert result.error is not None
        assert "agent exploded" in result.error
        assert result.result is None

    def test_non_finished_status_surfaced_as_error(self, tmp_path):
        """一个子智能体结束非 FINISHED (e.g. STUCK）作为错误出现，
        没有被报告为空洞的成功。"""
        manager, _ = _manager_with_parent(tmp_path)

        task = _make_task_with_mock_conv("task_00000001")
        assert task.conversation is not None
        mock_conv = cast(Any, task.conversation)
        mock_conv.state.execution_status = ConversationExecutionStatus.STUCK
        mock_conv.state.events = []
        manager._tasks[task.id] = task

        result = manager._run_task(task=task, prompt="do something")

        assert result.status == TaskStatus.ERROR
        assert result.result is None
        assert "stuck" in (result.error or "").lower()

    def test_run_evicts_conversation_after_error(self, tmp_path):
        """即使出现错误，任务的对话也应该被驱逐（最终阻止）。"""
        manager, _ = _manager_with_parent(tmp_path)

        task = _make_task_with_mock_conv(
            "task_00000001", **{"run.side_effect": RuntimeError("boom")}
        )
        mock_conv = task.conversation
        manager._tasks[task.id] = task

        manager._run_task(task=task, prompt="do something")

        assert manager._tasks[task.id].conversation is None
        assert mock_conv is not None
        mock_conv.pause.assert_called_once()  # type: ignore[attr-defined]
        mock_conv.close.assert_called_once()  # type: ignore[attr-defined]

    @patch(
        "openhands.tools.task.manager.get_agent_final_response",
        return_value="done",
    )
    def test_run_passes_parent_visualizer_name_as_sender(
        self, mock_get_response, tmp_path
    ):
        """如果父级有一个带有 _name 的可视化工具，则应将其作为发送者传递。"""
        manager, parent = _manager_with_parent(tmp_path)

        # 为父级提供一个带有 _name 的可视化工具
        mock_visualizer = MagicMock()
        mock_visualizer._name = "main-agent"
        parent._visualizer = mock_visualizer

        task = _make_task_with_mock_conv("task_00000001")
        manager._tasks[task.id] = task

        manager._run_task(task=task, prompt="hello")
        conversation = task.conversation
        assert conversation is not None
        task.conversation.send_message.assert_called_once_with(  # type: ignore[attr-defined]
            "hello", sender="main-agent"
        )


class TestStartTask:
    """测试 TaskManager.start_task（创建/恢复调度 + 运行）。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def _fake_run_task(self, task: Task, prompt: str) -> Task:
        """模拟成功的 _run_task，但未命中 LLM。"""
        task.set_result(f"result for: {prompt}")
        return task

    def test_start_new_task_creates_and_runs(self, tmp_path):
        """start_task 没有简历应该创建一个新任务并运行它。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        with patch.object(manager, "_run_task", side_effect=self._fake_run_task):
            result = manager.start_task(
                prompt="do the thing",
                subagent_type="general-purpose",
                conversation=parent,
            )

        assert result.status == TaskStatus.COMPLETED
        assert result.result == "result for: do the thing"
        assert result.id.startswith("task_")
        assert result.id in manager._tasks

    def test_start_task_sets_parent_conversation(self, tmp_path):
        """start_task 应在第一次通话时设置家长对话。"""
        manager = TaskManager()
        parent = _make_parent_conversation(tmp_path)
        register_builtins_agents()

        assert manager._parent_conversation is None

        with patch.object(manager, "_run_task", side_effect=self._fake_run_task):
            manager.start_task(
                prompt="hello",
                subagent_type="general-purpose",
                conversation=parent,
            )

        assert manager._parent_conversation is parent

    def test_start_task_with_resume(self, tmp_path):
        """start_task 带简历应恢复现有任务。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        # 创建和逐出任务以模拟先前已完成的运行
        first = manager._create_task(subagent_type="general-purpose", description=None)
        original_id = first.id
        manager._evict_task(first)

        with patch.object(manager, "_run_task", side_effect=self._fake_run_task):
            result = manager.start_task(
                prompt="continue",
                subagent_type="general-purpose",
                resume=original_id,
                conversation=parent,
            )

        assert result.status == TaskStatus.COMPLETED
        assert result.result == "result for: continue"
        assert result.id == original_id

    def test_start_task_resume_unknown_raises(self, tmp_path):
        """简历 ID 未知的 start_task 应引发 ValueError。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        with pytest.raises(ValueError, match="not found"):
            manager.start_task(
                prompt="continue",
                subagent_type="general-purpose",
                resume="task_nonexistent",
                conversation=parent,
            )


class TestTaskMetrics:
    """测试子智能体指标隔离和合并回。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_sub_agent_has_independent_metrics(self, tmp_path):
        """子智能体 LLM 不得共享父级的 Metrics 对象。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        parent_llm = parent.agent.llm
        sub_agent = manager._get_sub_agent("general-purpose")

        assert sub_agent.llm.metrics is not parent_llm.metrics

        before = parent_llm.metrics.accumulated_cost
        sub_agent.llm.metrics.add_cost(1.00)
        assert parent_llm.metrics.accumulated_cost == before

    def test_run_task_merges_metrics_into_parent(self, tmp_path):
        """_run_task 之后，子智能体指标出现在父统计信息中。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        task = manager._create_task(
            subagent_type="general-purpose",
            description="test",
        )

        # 将 LLM 连接到子转化统计数据（模拟 _ensure_agent_ready 的作用）
        sub_conv = task.conversation
        assert sub_conv is not None
        sub_llm = sub_conv.agent.llm
        sub_conv.conversation_stats.usage_to_metrics[sub_llm.usage_id] = sub_llm.metrics

        # 模拟子智能体 LLM 使用情况
        sub_llm.metrics.add_cost(1.50)
        sub_llm.metrics.add_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=128000,
            response_id="r1",
        )

        with (
            patch.object(sub_conv, "send_message"),
            patch.object(sub_conv, "run"),
            patch(
                "openhands.tools.task.manager.get_agent_final_response",
                return_value="done",
            ),
        ):
            manager._run_task(task=task, prompt="do something")

        # 指标已同步到任务下的父项：<id> 键
        parent_stats = parent.conversation_stats
        assert f"task:{task.id}" in parent_stats.usage_to_metrics
        task_metrics = parent_stats.usage_to_metrics[f"task:{task.id}"]
        assert task_metrics.accumulated_cost == 1.50
        accumulated_token_usage = task_metrics.accumulated_token_usage
        assert accumulated_token_usage is not None
        assert accumulated_token_usage.prompt_tokens == 100

    def test_multiple_tasks_have_separate_metrics(self, tmp_path):
        """每个任务在父统计信息中都有自己的指标条目。"""
        manager, parent = _manager_with_parent(tmp_path)
        register_builtins_agents()

        for cost in (1.00, 2.00):
            task = manager._create_task(
                subagent_type="general-purpose",
                description="test",
            )
            sub_conv = task.conversation
            assert sub_conv is not None
            sub_llm = sub_conv.agent.llm
            sub_conv.conversation_stats.usage_to_metrics[sub_llm.usage_id] = (
                sub_llm.metrics
            )
            sub_llm.metrics.add_cost(cost)

            with (
                patch.object(sub_conv, "send_message"),
                patch.object(sub_conv, "run"),
                patch(
                    "openhands.tools.task.manager.get_agent_final_response",
                    return_value="done",
                ),
            ):
                manager._run_task(task=task, prompt="work")

        parent_stats = parent.conversation_stats
        assert (
            parent_stats.usage_to_metrics["task:task_00000001"].accumulated_cost == 1.00
        )
        assert (
            parent_stats.usage_to_metrics["task:task_00000002"].accumulated_cost == 2.00
        )


def _register_hooked_agent(name: str, hook_config: HookConfig) -> None:
    """通过 AgentDefinition 向钩子注册智能体。"""
    from openhands.sdk.subagent.registry import agent_definition_to_factory

    agent_def = AgentDefinition(
        name=name,
        description=f"Agent with hooks: {name}",
        model="inherit",
        tools=[],
        system_prompt=f"You are {name}.",
        hooks=hook_config,
    )
    factory_func = agent_definition_to_factory(agent_def)
    register_agent(name=name, factory_func=factory_func, description=agent_def)


class TestTaskManagerHooks:
    """测试 hook_config 传播到子智能体对话。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_create_task_passes_hook_config(self, tmp_path):
        """_create_task 应将 AgentDefinition.hooks 传递给子对话。"""
        hook_config = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="terminal",
                    hooks=[HookDefinition(command="./validate.sh", timeout=10)],
                )
            ]
        )
        _register_hooked_agent("hooked_agent", hook_config)

        manager, _ = _manager_with_parent(tmp_path)
        task = manager._create_task(
            subagent_type="hooked_agent",
            description="test hooks",
        )

        sub_conv = task.conversation
        assert sub_conv is not None
        assert sub_conv._pending_hook_config is not None
        assert len(sub_conv._pending_hook_config.pre_tool_use) == 1
        assert sub_conv._pending_hook_config.pre_tool_use[0].matcher == "terminal"

    def test_create_task_no_hooks_passes_none(self, tmp_path):
        """当智能体定义没有钩子时，hook_config应该是None。"""
        register_builtins_agents()

        manager, _ = _manager_with_parent(tmp_path)
        task = manager._create_task(
            subagent_type="general-purpose",
            description="no hooks",
        )

        sub_conv = task.conversation
        assert sub_conv is not None
        assert sub_conv._pending_hook_config is None

    def test_resume_task_passes_hook_config(self, tmp_path):
        """_resume_task 应该传递智能体定义中的钩子。"""
        hook_config = HookConfig(
            post_tool_use=[
                HookMatcher(
                    matcher="*",
                    hooks=[HookDefinition(command="./log.sh")],
                )
            ]
        )
        _register_hooked_agent("hooked_resume", hook_config)

        manager, _ = _manager_with_parent(tmp_path)

        # 创建和退出任务
        task = manager._create_task(
            subagent_type="hooked_resume",
            description="test",
        )
        original_id = task.id
        manager._evict_task(task)

        # 恢复它
        resumed = manager._resume_task(
            resume=original_id, subagent_type="hooked_resume"
        )
        sub_conv = resumed.conversation
        assert sub_conv is not None
        assert sub_conv._pending_hook_config is not None
        assert len(sub_conv._pending_hook_config.post_tool_use) == 1
        assert sub_conv._pending_hook_config.post_tool_use[0].matcher == "*"

    def test_get_conversation_passes_hook_config(self, tmp_path):
        """_get_conversation 应将 hook_config 转发到 LocalConversation。"""
        register_builtins_agents()
        manager, _ = _manager_with_parent(tmp_path)

        hook_config = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="file_editor",
                    hooks=[HookDefinition(command="./lint.sh")],
                )
            ]
        )

        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description="test",
            max_iteration_per_run=100,
            task_id=task_id,
            subagent_type="default",
            conversation_id=conversation_id,
            worker_agent=agent,
            hook_config=hook_config,
        )

        assert conv._pending_hook_config is not None
        assert len(conv._pending_hook_config.pre_tool_use) == 1
        assert conv._pending_hook_config.pre_tool_use[0].matcher == "file_editor"

    def test_get_conversation_without_hook_config(self, tmp_path):
        """_get_conversation 没有 hook_config 时应将其保留为 None。"""
        register_builtins_agents()
        manager, _ = _manager_with_parent(tmp_path)

        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description="test",
            max_iteration_per_run=100,
            task_id=task_id,
            subagent_type="default",
            conversation_id=conversation_id,
            worker_agent=agent,
        )

        assert conv._pending_hook_config is None


class TestTaskManagerPersistence:
    """测试持久化目录行为。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_no_persistence_uses_tmp_dir(self, tmp_path):
        """当父级没有 persistence_dir 时，管理器使用临时目录。"""
        manager, parent = _manager_with_parent(tmp_path)
        assert parent.state.persistence_dir is None
        assert manager._persistence_dir is not None
        assert manager._persistence_dir.exists()
        assert "openhands_tasks_" in str(manager._persistence_dir)

    def test_no_persistence_close_deletes_tmp_dir(self, tmp_path):
        """当父级没有 persistence_dir 时，close() 删除临时目录。"""
        manager, _ = _manager_with_parent(tmp_path)
        persistence_dir = manager._persistence_dir
        assert persistence_dir is not None
        assert persistence_dir.exists()

        manager.close()

        assert not persistence_dir.exists()

    def test_with_persistence_creates_subagents_dir(self, tmp_path):
        """当父目录持续存在时，管理器会创建一个 subagents/ 子目录。"""
        parent_persistence = tmp_path / "conversations"
        parent_persistence.mkdir()
        manager, parent = _manager_with_parent(
            tmp_path, persistence_dir=parent_persistence
        )

        assert parent.state.persistence_dir is not None
        assert manager._persistence_dir is not None
        assert manager._persistence_dir.exists()
        assert manager._persistence_dir.name == "subagents"
        assert str(manager._persistence_dir).startswith(
            str(parent.state.persistence_dir)
        )

    def test_with_persistence_close_preserves_subagents_dir(self, tmp_path):
        """当父目录仍然存在时，close() 会不删除子智能体目录。"""
        parent_persistence = tmp_path / "conversations"
        parent_persistence.mkdir()
        manager, _ = _manager_with_parent(tmp_path, persistence_dir=parent_persistence)
        persistence_dir = manager._persistence_dir
        assert persistence_dir is not None
        assert persistence_dir.exists()

        manager.close()

        # 应保留子智能体目录以供将来重新启动
        assert persistence_dir.exists()

    def test_with_persistence_subagent_conv_stored_under_subagents(self, tmp_path):
        """子智能体对话应位于 subagents/ 目录下的已持久化。"""
        parent_persistence = tmp_path / "conversations"
        parent_persistence.mkdir()
        manager, _ = _manager_with_parent(tmp_path, persistence_dir=parent_persistence)
        register_builtins_agents()

        task_id, conversation_id = manager._generate_ids()
        agent = manager._get_sub_agent("general-purpose")

        conv = manager._get_conversation(
            description=None,
            max_iteration_per_run=500,
            task_id=task_id,
            subagent_type="default",
            worker_agent=agent,
            conversation_id=conversation_id,
        )

        conv_persistence = conv.state.persistence_dir
        assert conv_persistence is not None
        assert str(conv_persistence).startswith(str(manager._persistence_dir))


class TestTaskManagerBudget:
    """每个子智能体的成本预算来自智能体定义/父级
    进入生成的子对话。"""

    def test_budget_from_agent_definition(self, tmp_path):
        from openhands.sdk.subagent.registry import agent_definition_to_factory

        agent_def = AgentDefinition(
            name="budgeted", model="inherit", tools=[], max_budget_per_run=4.0
        )
        register_agent(
            name="budgeted",
            factory_func=agent_definition_to_factory(agent_def),
            description=agent_def,
        )
        manager, _ = _manager_with_parent(tmp_path)
        task = manager._create_task(subagent_type="budgeted", description=None)
        assert task.conversation is not None
        assert task.conversation.max_budget_per_run == 4.0

    def test_budget_inherits_from_parent(self, tmp_path):
        register_builtins_agents()
        agent = Agent(llm=_make_llm(), tools=[])
        parent = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            visualizer=None,
            delete_on_close=False,
            max_budget_per_run=7.0,
        )
        manager = TaskManager()
        manager._ensure_parent(parent)
        task = manager._create_task(subagent_type="general-purpose", description=None)
        assert task.conversation is not None
        assert task.conversation.max_budget_per_run == 7.0


class TestRunErrorSurfacing:
    """以非 FINISHED 状态结束的子智能体运行（卡住、暂停、运行限制、
    ...) is surfaced to the parent task rather than reported as an empty success."""

    def test_run_stop_detail_returns_last_error(self):
        from types import SimpleNamespace

        from openhands.sdk.event.conversation_error import ConversationErrorEvent

        err = ConversationErrorEvent(
            source="environment",
            code="MaxIterationsReached",
            detail="Agent reached the maximum iteration limit.",
        )
        conv = SimpleNamespace(state=SimpleNamespace(events=[err]))
        detail = TaskManager._run_stop_detail(
            cast(LocalConversation, conv), ConversationExecutionStatus.ERROR
        )
        assert err.detail in detail

    def test_run_stop_detail_default_mentions_status(self):
        from types import SimpleNamespace

        conv = SimpleNamespace(state=SimpleNamespace(events=[]))
        detail = TaskManager._run_stop_detail(
            cast(LocalConversation, conv), ConversationExecutionStatus.STUCK
        )
        assert "stuck" in detail.lower()
