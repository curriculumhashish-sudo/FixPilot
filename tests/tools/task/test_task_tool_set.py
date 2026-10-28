import json

from openhands.sdk import Agent, Conversation, LocalConversation, Tool
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.llm_convertible.observation import ObservationEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.subagent.registry import _reset_registry_for_tests, register_agent
from openhands.sdk.testing import TestLLM
from openhands.tools.task import TaskToolSet
from openhands.tools.task.definition import TASK_TOOL_EXAMPLES, TaskObservation
from openhands.tools.task.manager import TaskStatus


def _task_tool_call(
    call_id: str,
    prompt: str,
    subagent_type: str = "test_agent",
    description: str | None = None,
    resume: str | None = None,
) -> Message:
    """构建一条消息，其唯一的工具调用是任务工具。"""
    args: dict = {
        "prompt": prompt,
        "subagent_type": subagent_type,
    }
    if description is not None:
        args["description"] = description
    if resume is not None:
        args["resume"] = resume

    return Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[
            MessageToolCall(
                id=call_id,
                name="task",
                arguments=json.dumps(args),
                origin="completion",
            )
        ],
    )


def _text_message(text: str) -> Message:
    """普通的助理短信（无工具调用）。"""
    return Message(role="assistant", content=[TextContent(text=text)])


def _register_simple_agent(name: str, sub_llm: TestLLM) -> None:
    """注册由 *sub_llm* 支持的子智能体（忽略父复制的 LLM）。"""

    def factory(llm):
        return Agent(llm=sub_llm, tools=[])

    register_agent(name=name, factory_func=factory, description=f"Test agent: {name}")


def _get_task_observations(conversation: LocalConversation) -> list[TaskObservation]:
    """从对话事件中提取所有 TaskObservation 对象。"""
    results = []
    for event in conversation.state.events:
        if isinstance(event, ObservationEvent) and isinstance(
            event.observation, TaskObservation
        ):
            results.append(event.observation)
    return results


class TestTaskToolSetIntegration:
    """测试TaskToolSet。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_basic_task_delegation_and_result(self, tmp_path):
        """家长代表子智能体； 子智能体文本作为任务结果返回。"""
        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call("call_1", prompt="What is the capital of France?"),
                _text_message("The answer is Paris."),
            ]
        )
        sub_llm = TestLLM.from_messages(
            [
                _text_message("The capital of France is Paris."),
            ]
        )
        _register_simple_agent("test_agent", sub_llm)

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("What is the capital of France?")
        conversation.run()

        # 对话结束
        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )

        # LLMs都完全消耗了
        assert parent_llm.remaining_responses == 0
        assert sub_llm.remaining_responses == 0

        # 任务观测结果存在且成功
        observations = _get_task_observations(conversation)
        assert len(observations) == 1
        obs = observations[0]
        assert obs.status == TaskStatus.COMPLETED
        assert obs.task_id.startswith("task_")
        assert obs.subagent == "test_agent"
        assert "Paris" in obs.text

    # ── 多个连续任务────────────────────────────────────

    def test_two_sequential_tasks(self, tmp_path):
        """家长可以在一轮中相继启动两项任务。"""
        sub_llm_1 = TestLLM.from_messages([_text_message("first result")])
        sub_llm_2 = TestLLM.from_messages([_text_message("second result")])
        _register_simple_agent("agent_a", sub_llm_1)
        _register_simple_agent("agent_b", sub_llm_2)

        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call("call_1", prompt="Task A", subagent_type="agent_a"),
                _task_tool_call("call_2", prompt="Task B", subagent_type="agent_b"),
                _text_message("Both tasks done."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Run two tasks")
        conversation.run()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        observations = _get_task_observations(conversation)
        assert len(observations) == 2
        assert observations[0].text == "first result"
        assert observations[1].text == "second result"
        assert observations[0].subagent == "agent_a"
        assert observations[1].subagent == "agent_b"

    def test_task_resume_across_turns(self, tmp_path):
        """可以启动任务，然后通过传递 task_id 来恢复任务。"""
        # 子智能体第一次通话
        sub_llm_1 = TestLLM.from_messages(
            [
                _text_message("Here is a quiz: What color is the sky?"),
                _text_message("Correct! Blue is right."),
            ]
        )
        _register_simple_agent("quiz_agent", sub_llm_1)

        # 第一轮：家长代表quiz_agent
        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call(
                    "call_1",
                    prompt="Generate a quiz",
                    subagent_type="quiz_agent",
                ),
                _text_message("It is Blue!"),
                _task_tool_call(
                    "call_2",
                    prompt="Generate a quiz",
                    subagent_type="quiz_agent",
                    resume="task_00000001",
                ),
                _text_message("Thank you."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Give me a quiz")
        conversation.run()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        observations = _get_task_observations(conversation)
        assert len(observations) == 1
        task_id = observations[0].task_id

        conversation.send_message("My answer is blue")
        conversation.run()

        all_observations = _get_task_observations(conversation)
        # 现在总共应该有 2 个观测结果
        assert len(all_observations) == 2
        resumed_obs = all_observations[1]
        assert resumed_obs.task_id == task_id
        assert "Correct" in resumed_obs.text

    # ── 错误处理──────────────────────────────────────────────

    def test_unknown_agent_type_returns_error_observation(self, tmp_path):
        """使用未注册的 subagent_type 会产生错误 TaskObservation。"""
        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call(
                    "call_1",
                    prompt="Do something",
                    subagent_type="nonexistent_agent",
                ),
                _text_message("Oops."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Do something")
        conversation.run()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        observations = _get_task_observations(conversation)
        assert len(observations) == 1
        obs = observations[0]
        assert obs.is_error is True
        assert "nonexistent_agent" in obs.text or "Unknown agent" in obs.text

    def test_sub_agent_exception_returns_error_observation(self, tmp_path):
        """当子智能体的 LLM 升高时，任务报告错误。"""
        sub_llm = TestLLM.from_messages(
            [
                RuntimeError("LLM went boom"),
            ]
        )
        _register_simple_agent("failing_agent", sub_llm)

        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call(
                    "call_1", prompt="Run this", subagent_type="failing_agent"
                ),
                _text_message("The task failed."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Run this")
        conversation.run()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        observations = _get_task_observations(conversation)
        assert len(observations) == 1
        obs = observations[0]
        assert obs.is_error is True
        assert obs.status == TaskStatus.ERROR

    def test_task_ids_are_unique_and_sequential(self, tmp_path):
        """每个任务都有一个唯一的、递增的 ID。"""
        sub_llm_1 = TestLLM.from_messages([_text_message("r1")])
        sub_llm_2 = TestLLM.from_messages([_text_message("r2")])
        _register_simple_agent("agent_x", sub_llm_1)
        _register_simple_agent("agent_y", sub_llm_2)

        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call("c1", prompt="T1", subagent_type="agent_x"),
                _task_tool_call("c2", prompt="T2", subagent_type="agent_y"),
                _text_message("All done."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Do both")
        conversation.run()

        observations = _get_task_observations(conversation)
        assert len(observations) == 2
        id1 = observations[0].task_id
        id2 = observations[1].task_id
        assert id1 != id2
        # 顺序：task_00000001 < task_00000002
        assert id1 < id2

    def test_resume_nonexistent_task_returns_error(self, tmp_path):
        """恢复不存在的任务 ID 会产生错误观测结果。"""
        sub_llm = TestLLM.from_messages([_text_message("never reached")])
        _register_simple_agent("test_agent", sub_llm)

        parent_llm = TestLLM.from_messages(
            [
                _task_tool_call(
                    "call_1",
                    prompt="Continue",
                    subagent_type="test_agent",
                    resume="task_99999999",
                ),
                _text_message("Failed."),
            ]
        )

        agent = Agent(llm=parent_llm, tools=[Tool(name=TaskToolSet.name)])
        conversation = Conversation(
            agent=agent, workspace=str(tmp_path), visualizer=None
        )

        conversation.send_message("Resume a non-existent task")
        conversation.run()

        assert (
            conversation.state.execution_status == ConversationExecutionStatus.FINISHED
        )
        observations = _get_task_observations(conversation)
        assert len(observations) == 1
        assert observations[0].is_error is True


class TestTaskToolExamples:
    """测试工具描述中包含 TASK_TOOL_EXAMPLES
    仅当相应的智能体已注册时。"""

    def setup_method(self):
        _reset_registry_for_tests()

    def teardown_method(self):
        _reset_registry_for_tests()

    def test_matching_agent_example_included(self, tmp_path):
        """当注册的智能体名称与 TASK_TOOL_EXAMPLES 键匹配时，
        其示例出现在工具说明中。"""
        # 从示例字典中选择一个键
        example_name = next(iter(TASK_TOOL_EXAMPLES))
        example_text = TASK_TOOL_EXAMPLES[example_name]

        # 注册一个名称与示例密钥匹配的智能体
        register_agent(
            name=example_name,
            factory_func=lambda llm: Agent(llm=llm, tools=[]),
            description=f"Test agent: {example_name}",
        )

        tools = TaskToolSet.create(
            conv_state=None,  # type: ignore[arg-type]
        )
        assert len(tools) == 1
        description = tools[0].description
        assert example_text.strip() in description

    def test_no_matching_agent_example_excluded(self, tmp_path):
        """当没有注册的智能体名称与任何TASK_TOOL_EXAMPLES键匹配时，
        工具描述中没有出现示例文本。"""
        # 注册一个名称不与任何示例键匹配的智能体
        register_agent(
            name="unrelated_agent",
            factory_func=lambda llm: Agent(llm=llm, tools=[]),
            description="Test agent: unrelated",
        )

        tools = TaskToolSet.create(
            conv_state=None,  # type: ignore[arg-type]
        )
        assert len(tools) == 1
        description = tools[0].description
        for name, example_text in TASK_TOOL_EXAMPLES.items():
            assert example_text.strip() not in description

    def test_only_registered_examples_included(self, tmp_path):
        """仅出现已注册的智能体的示例； 其他人则被排除在外。"""
        keys = list(TASK_TOOL_EXAMPLES.keys())
        if len(keys) < 2:
            return  # 此测试至少需要 2 个示例

        included_name = keys[0]
        excluded_name = keys[1]

        register_agent(
            name=included_name,
            factory_func=lambda llm: Agent(llm=llm, tools=[]),
            description=f"Test agent: {included_name}",
        )

        tools = TaskToolSet.create(
            conv_state=None,  # type: ignore[arg-type]
        )
        description = tools[0].description
        assert TASK_TOOL_EXAMPLES[included_name].strip() in description
        assert TASK_TOOL_EXAMPLES[excluded_name].strip() not in description
