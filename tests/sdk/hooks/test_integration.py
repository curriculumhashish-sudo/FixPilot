"""集成测试用于阻止智能体和对话中的钩子。"""

import pytest

from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event import ActionEvent, HookExecutionEvent, MessageEvent
from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.hooks.conversation_hooks import (
    HookEventProcessor,
    create_hook_callback,
)
from openhands.sdk.hooks.manager import HookManager
from openhands.sdk.llm import Message, TextContent
from tests.command_utils import python_command


def _json_command(payload: dict[str, object], exit_code: int = 0) -> str:
    return python_command(
        f"import json, sys; print(json.dumps({payload!r})); sys.exit({exit_code})"
    )


def _stderr_exit_command(message: str, exit_code: int) -> str:
    return python_command(
        f"import sys; sys.stderr.write({message!r} + '\\n'); sys.exit({exit_code})"
    )


def _write_stdin_to_file_command(path) -> str:
    return python_command(
        "import sys; "
        "from pathlib import Path; "
        f"Path({str(path)!r}).write_text(sys.stdin.read())"
    )


class TestBlockedActionsState:
    """测试 ConversationState 上的 blocked_actions 字段。"""

    def test_blocked_actions_field_exists(self):
        """测试 ConversationState 是否有 blocked_actions 字段。"""
        # blocked_actions 应位于模型字段中
        assert "blocked_actions" in ConversationState.model_fields

    def test_blocked_actions_default_empty(self):
        """测试 blocked_actions 默认为空字典。"""
        # 为验证创建一个最小状态字典
        import tempfile
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        with tempfile.TemporaryDirectory() as tmpdir:
            llm = LLM(model="test-model", api_key=SecretStr("test-key"))
            agent = Agent(llm=llm, tools=[])
            workspace = LocalWorkspace(working_dir=tmpdir)

            state = ConversationState(
                id=uuid.uuid4(),
                agent=agent,
                workspace=workspace,
                persistence_dir=None,
            )

            assert state.blocked_actions == {}


class TestBlockedStatePersistence:
    """跨恢复测试阻塞状态持久化。"""

    def _create_persistent_state(self, tmp_path, conversation_id):
        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))
        persistence_dir = tmp_path / "conversations"
        return ConversationState.create(
            id=conversation_id,
            agent=agent,
            workspace=workspace,
            persistence_dir=str(persistence_dir),
        )

    def test_blocked_entries_persist_across_resume(self, tmp_path):
        import uuid

        conversation_id = uuid.uuid4()
        state = self._create_persistent_state(tmp_path, conversation_id)
        state.block_action("action-1", "Blocked")
        state.block_message("message-1", "Nope")

        resumed = self._create_persistent_state(tmp_path, conversation_id)

        assert resumed.blocked_actions["action-1"] == "Blocked"
        assert resumed.blocked_messages["message-1"] == "Nope"

    def test_blocked_entries_removal_persists(self, tmp_path):
        import uuid

        conversation_id = uuid.uuid4()
        state = self._create_persistent_state(tmp_path, conversation_id)
        state.block_action("action-1", "Blocked")
        state.block_message("message-1", "Nope")

        assert state.pop_blocked_action("action-1") == "Blocked"
        assert state.pop_blocked_message("message-1") == "Nope"

        resumed = self._create_persistent_state(tmp_path, conversation_id)

        assert "action-1" not in resumed.blocked_actions
        assert "message-1" not in resumed.blocked_messages


class TestUserPromptSubmitBlocking:
    """测试 UserPromptSubmit 钩子阻塞。"""

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """创建模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        return ConversationState(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_is_message_blocked_without_state(self, tmp_path):
        """测试 is_message_blocked 返回 False 且未设置状态。"""
        manager = HookManager(config=HookConfig(), working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        # 未设置状态
        assert not processor.is_message_blocked("any-message-id")

    def test_blocking_user_prompt_hook_adds_to_state(
        self, tmp_path, mock_conversation_state
    ):
        """测试阻塞 UserPromptSubmit 挂钩将消息 ID 添加到 blocked_messages。"""
        command = _stderr_exit_command("Blocked by policy", 2)

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        message_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello, this should be blocked")],
            ),
        )

        processor.on_event(message_event)

        assert processor.is_message_blocked(message_event.id)
        assert (
            "Blocked by policy"
            in mock_conversation_state.blocked_messages[message_event.id]
        )

    def test_non_blocking_user_prompt_hook_does_not_block(
        self, tmp_path, mock_conversation_state
    ):
        """测试非阻塞挂钩不会添加到 blocked_messages。"""
        command = python_command("import sys; sys.exit(0)")

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        message_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello, this should pass")],
            ),
        )

        processor.on_event(message_event)

        assert not processor.is_message_blocked(message_event.id)


class TestHookEventProcessorBlocking:
    """测试 HookEventProcessor 阻塞集成。"""

    @pytest.fixture
    def blocking_config(self, tmp_path):
        """创建一个带有阻塞钩子的配置。"""
        command = _json_command({"decision": "deny", "reason": "Test block"}, 2)

        return HookConfig.from_dict(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        )

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """创建与 blocked_actions 的模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        return ConversationState(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_set_conversation_state(self, tmp_path, mock_conversation_state):
        """测试 set_conversation_state 是否存储状态引用。"""
        manager = HookManager(
            config=HookConfig(),
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)

        assert processor._conversation_state is None
        processor.set_conversation_state(mock_conversation_state)
        assert processor._conversation_state is mock_conversation_state

    def test_blocking_hook_adds_to_state(
        self, tmp_path, blocking_config, mock_conversation_state
    ):
        """测试阻塞钩子是否将操作 ID 添加到 state.blocked_actions。"""
        manager = HookManager(
            config=blocking_config,
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        # 创建具有必填字段的模拟对象操作事件
        from openhands.sdk.llm import MessageToolCall
        from openhands.sdk.tool.builtins import ThinkAction

        action_event = ActionEvent(
            source="agent",
            tool_name="terminal",
            tool_call_id="test-call-id",
            tool_call=MessageToolCall(
                id="test-call-id", name="terminal", arguments="{}", origin="completion"
            ),
            llm_response_id="test-response-id",
            action=ThinkAction(thought="test"),
            thought=[],
        )

        # 处理事件（这应该触发阻塞钩子）
        processor.on_event(action_event)

        # 检查该操作是否被标记为已阻止
        assert action_event.id in mock_conversation_state.blocked_actions
        assert "Test block" in mock_conversation_state.blocked_actions[action_event.id]

    def test_is_action_blocked_uses_state(
        self, tmp_path, blocking_config, mock_conversation_state
    ):
        """测试 is_action_blocked 检查状态。"""
        manager = HookManager(
            config=blocking_config,
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        # 手动添加阻止的操作
        mock_conversation_state.blocked_actions["test-action-id"] = "Blocked"

        assert processor.is_action_blocked("test-action-id")
        assert not processor.is_action_blocked("other-action-id")

    def test_is_action_blocked_without_state(self, tmp_path):
        """测试 is_action_blocked 返回没有状态的 False。"""
        manager = HookManager(
            config=HookConfig(),
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)

        # 未设置状态
        assert not processor.is_action_blocked("any-action-id")


class TestPostToolUseActionLookup:
    """测试 PostToolUse 从对话状态事件中查找操作。"""

    @pytest.fixture
    def logging_config(self, tmp_path):
        """使用记录 tool_input 的 PostToolUse 挂钩创建一个配置。"""
        log_file = tmp_path / "hook_output.log"
        command = _write_stdin_to_file_command(log_file)

        return HookConfig.from_dict(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        ), log_file

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """使用工厂方法创建模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        # 使用create()工厂正确初始化_events
        return ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_post_tool_use_finds_action_from_events(
        self, tmp_path, logging_config, mock_conversation_state
    ):
        """测试 PostToolUse 挂钩是否找到来自 conversation.state.events 的操作。"""
        import json

        from openhands.sdk.event import ObservationEvent
        from openhands.sdk.llm import MessageToolCall
        from openhands.sdk.tool.builtins import ThinkAction, ThinkObservation

        config, log_file = logging_config
        manager = HookManager(
            config=config,
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        # 创建动作事件
        action_event = ActionEvent(
            source="agent",
            tool_name="Think",
            tool_call_id="test-call-id",
            tool_call=MessageToolCall(
                id="test-call-id", name="Think", arguments="{}", origin="completion"
            ),
            llm_response_id="test-response-id",
            action=ThinkAction(thought="test thought"),
            thought=[],
        )

        # 向状态事件添加操作（模拟对话的作用）
        mock_conversation_state.events.append(action_event)

        # 创建对应的观测结果事件
        observation_event = ObservationEvent(
            source="agent",
            action_id=action_event.id,  # 操作链接
            tool_name="Think",
            tool_call_id="test-call-id",
            observation=ThinkObservation(),
        )

        # 处理观测结果（这应该触发 PostToolUse 并找到操作）
        processor.on_event(observation_event)

        # 验证挂钩收到操作的 tool_input 和 tool_response
        assert log_file.exists(), "Hook should have been called and written to log file"
        hook_input = json.loads(log_file.read_text())
        assert hook_input["tool_name"] == "Think"
        assert "tool_input" in hook_input
        # tool_input 应包含操作的 model_dump
        assert "thought" in hook_input["tool_input"]
        # tool_response 应包含观测结果的 model_dump
        assert "tool_response" in hook_input
        assert isinstance(hook_input["tool_response"], dict)
        assert "content" in hook_input["tool_response"]  # 来自观测结果基类

    def test_post_tool_use_without_state_does_not_crash(self, tmp_path, logging_config):
        """测试 PostToolUse 是否妥善处理丢失的对话状态。"""
        from openhands.sdk.event import ObservationEvent
        from openhands.sdk.tool.builtins import ThinkObservation

        config, log_file = logging_config
        manager = HookManager(
            config=config,
            working_dir=str(tmp_path),
        )
        processor = HookEventProcessor(hook_manager=manager)
        # 注意：不呼叫set_conversation_state

        observation_event = ObservationEvent(
            source="agent",
            action_id="nonexistent-action",
            tool_name="Think",
            tool_call_id="test-call-id",
            observation=ThinkObservation(),
        )

        # 不应该崩溃，只要早点返回
        processor.on_event(observation_event)

        # 应该已调用挂钩不（未找到操作）
        assert not log_file.exists()


class TestCreateHookCallback:
    """测试 create_hook_callback 功能。"""

    def test_create_hook_callback_returns_processor_and_callback(self, tmp_path):
        """测试 create_hook_callback 返回处理器和回调。"""
        config = HookConfig.from_dict({"hooks": {}})

        processor, callback = create_hook_callback(
            hook_config=config,
            working_dir=str(tmp_path),
            session_id="test-session",
        )

        assert isinstance(processor, HookEventProcessor)
        assert callable(callback)
        assert callback == processor.on_event


class TestLocalConversationHookCallbackWiring:
    """测试 LocalConversation 将挂钩回调连接到事件持久化。"""

    def test_modified_events_with_additional_context_persisted(self, tmp_path):
        """测试钩子修改的事件（带有 additional_context）是否获得已持久化。"""
        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.conversation import LocalConversation
        from openhands.sdk.llm import LLM

        # 创建一个添加 additional_context 的钩子
        command = _json_command(
            {"additionalContext": "HOOK_INJECTED_CONTEXT"},
        )

        hook_config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])

        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            hook_config=hook_config,
            visualizer=None,
        )

        conversation.send_message("Hello")

        # 验证 MODIFIED 事件（带有 extended_content）为已持久化
        events = list(conversation.state.events)
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        assert len(message_events[0].extended_content) > 0
        assert any(
            "HOOK_INJECTED_CONTEXT" in c.text
            for c in message_events[0].extended_content
        )

        conversation.close()


class TestAdditionalContextInjection:
    """测试 additional_context 注入 LLM 消息。"""

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """使用工厂方法创建模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        return ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_additional_context_appears_in_extended_content(
        self, tmp_path, mock_conversation_state
    ):
        """测试挂钩 additional_context 被注入到 extended_content 中。"""
        # 创建一个返回附加上下文的钩子
        command = _json_command(
            {"additionalContext": "Important context from hook"},
        )

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager, original_callback=capture_callback
        )
        processor.set_conversation_state(mock_conversation_state)

        original_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello")],
            ),
        )

        processor.on_event(original_event)

        # 筛选 MessageEvent（不包括 HookExecutionEvent）
        message_events = [e for e in processed_events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        processed_event = message_events[0]

        # extended_content 应包含钩子的附加上下文
        assert len(processed_event.extended_content) == 1
        assert processed_event.extended_content[0].text == "Important context from hook"

    def test_additional_context_appears_in_llm_message(
        self, tmp_path, mock_conversation_state
    ):
        """测试转换为LLM消息时是否出现挂钩additional_context。"""
        command = _json_command({"additionalContext": "Injected by hook"})

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager, original_callback=capture_callback
        )
        processor.set_conversation_state(mock_conversation_state)

        original_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="User message")],
            ),
        )

        processor.on_event(original_event)

        # 筛选 MessageEvent（不包括 HookExecutionEvent）
        message_events = [e for e in processed_events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        processed_event = message_events[0]
        llm_message = processed_event.to_llm_message()

        # 内容应包括原始消息和挂钩上下文
        content_texts = [
            c.text for c in llm_message.content if isinstance(c, TextContent)
        ]
        assert "User message" in content_texts
        assert "Injected by hook" in content_texts

    def test_additional_context_preserves_existing_extended_content(
        self, tmp_path, mock_conversation_state
    ):
        """测试挂钩上下文是否附加到现有 extended_content。"""
        command = _json_command({"additionalContext": "Hook context"})

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager, original_callback=capture_callback
        )
        processor.set_conversation_state(mock_conversation_state)

        # 使用现有的 extended_content 创建事件
        original_event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[TextContent(text="Hello")],
            ),
            extended_content=[TextContent(text="Existing context")],
        )

        processor.on_event(original_event)

        # 筛选 MessageEvent（不包括 HookExecutionEvent）
        message_events = [e for e in processed_events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        processed_event = message_events[0]

        # 现有的和钩子上下文都应该存在
        assert len(processed_event.extended_content) == 2
        content_texts = [c.text for c in processed_event.extended_content]
        assert "Existing context" in content_texts
        assert "Hook context" in content_texts


class TestStopHookIntegration:
    """测试对话中的 Stop 挂钩集成。"""

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """使用工厂方法创建模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        return ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_run_stop_with_allowing_hook(self, tmp_path, mock_conversation_state):
        """测试当 hook 允许停止时 ​​run_stop 返回 True。"""
        command = _json_command({"decision": "allow"})

        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        should_stop, feedback = processor.run_stop(reason="finish_tool")

        assert should_stop is True
        assert feedback is None

    def test_run_stop_with_denying_hook(self, tmp_path, mock_conversation_state):
        """测试当钩子拒绝停止时 run_stop 返回 False。"""
        command = _json_command(
            {"decision": "deny", "reason": "Not done yet"},
            2,
        )

        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        should_stop, feedback = processor.run_stop(reason="finish_tool")

        assert should_stop is False
        assert feedback == "Not done yet"

    def test_run_stop_with_additional_context_as_feedback(
        self, tmp_path, mock_conversation_state
    ):
        """当停止被拒绝时，返回测试 additional_context 作为反馈。"""
        command = _json_command(
            {"decision": "deny", "additionalContext": "Please complete X"},
            2,
        )

        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        should_stop, feedback = processor.run_stop(reason="finish_tool")

        assert should_stop is False
        assert feedback == "Please complete X"

    def test_stop_hook_error_is_logged_and_allows_stop(
        self, tmp_path, mock_conversation_state
    ):
        """测试挂钩错误是否得到妥善处理并允许停止。"""
        command = python_command("import sys; sys.exit(1)")

        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processor = HookEventProcessor(hook_manager=manager)
        processor.set_conversation_state(mock_conversation_state)

        should_stop, feedback = processor.run_stop(reason="finish_tool")

        # 错误退出 (1) 不会阻塞，因此应继续停止
        assert should_stop is True
        assert feedback is None


class TestStopHookConversationIntegration:
    """集成测试用于 LocalConversation 运行循环中的停止钩子。"""

    def test_stop_hook_denial_injects_feedback_and_continues(self, tmp_path):
        """测试停止钩子拒绝注入反馈并继续循环。"""
        from unittest.mock import patch

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.conversation import LocalConversation
        from openhands.sdk.conversation.state import ConversationExecutionStatus
        from openhands.sdk.llm import LLM

        # 创建一个停止钩子，第一次拒绝停止，然后允许
        stop_count_file = tmp_path / "stop_count"
        stop_count_file.write_text("0")

        command = python_command(
            "import json, sys; "
            "from pathlib import Path; "
            f"path = Path({str(stop_count_file)!r}); "
            "count = int(path.read_text()); "
            "path.write_text(str(count + 1)); "
            "payload = "
            "({'decision': 'deny', "
            "'additionalContext': 'Complete the task first'} "
            "if count == 0 else {'decision': 'allow'}); "
            "print(json.dumps(payload)); "
            "sys.exit(2 if count == 0 else 0)"
        )

        hook_config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])

        # 追踪事件
        events_captured = []

        def capture_event(event):
            events_captured.append(event)

        # 创建立即设置 FINISHED 的模拟对象智能体
        step_count = 0

        def mock_step(self, conversation, on_event, on_token=None):
            nonlocal step_count
            step_count += 1
            # 始终设置为 FINISHED - 停止挂钩集成应该处理此问题
            conversation.state.execution_status = ConversationExecutionStatus.FINISHED

        with patch.object(Agent, "step", mock_step):
            conversation = LocalConversation(
                agent=agent,
                workspace=tmp_path,
                hook_config=hook_config,
                callbacks=[capture_event],
                visualizer=None,
                max_iteration_per_run=10,
            )

            # 发送消息开始
            conversation.send_message("Hello")

            # 运行对话
            conversation.run()

            # 接近触发会话结束
            conversation.close()

        # 智能体应该被调用两次：
        # 1. 第一步设置 FINISHED，停止钩子拒绝，注入反馈
        # 2. 第二步设置FINISHED，停止挂机允许，通话结束
        assert step_count == 2

        # 检查反馈是否作为带有前缀的环境消息注入
        feedback_messages = [
            e
            for e in events_captured
            if isinstance(e, MessageEvent)
            and e.source == "environment"
            and any(
                "[Stop hook feedback] Complete the task first" in c.text
                for c in e.llm_message.content
                if isinstance(c, TextContent)
            )
        ]
        assert len(feedback_messages) == 1, "Feedback message should be injected once"


class TestHookExecutionEventEmission:
    """在钩子执行期间测试 HookExecutionEvent 发射。"""

    @pytest.fixture
    def mock_conversation_state(self, tmp_path):
        """使用工厂方法创建模拟对象对话状态。"""
        import uuid

        from pydantic import SecretStr

        from openhands.sdk.agent import Agent
        from openhands.sdk.llm import LLM
        from openhands.sdk.workspace import LocalWorkspace

        llm = LLM(model="test-model", api_key=SecretStr("test-key"))
        agent = Agent(llm=llm, tools=[])
        workspace = LocalWorkspace(working_dir=str(tmp_path))

        return ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=workspace,
            persistence_dir=None,
        )

    def test_hook_execution_event_emitted_for_user_prompt_submit(
        self, tmp_path, mock_conversation_state
    ):
        """测试 UserPromptSubmit 挂钩运行时是否发出 HookExecutionEvent。"""
        command = _json_command({"decision": "allow"})

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager,
            original_callback=capture_callback,
            emit_hook_events=True,
        )
        processor.set_conversation_state(mock_conversation_state)

        original_event = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        )

        processor.on_event(original_event)

        # 应该同时具有 HookExecutionEvent 和 MessageEvent
        hook_events = [e for e in processed_events if isinstance(e, HookExecutionEvent)]
        message_events = [e for e in processed_events if isinstance(e, MessageEvent)]

        assert len(hook_events) == 1
        assert len(message_events) == 1

        hook_event = hook_events[0]
        assert hook_event.hook_event_type == "UserPromptSubmit"
        assert hook_event.hook_command == command
        assert hook_event.success is True
        assert hook_event.blocked is False
        assert hook_event.exit_code == 0
        assert hook_event.source == "hook"

    def test_hook_execution_event_not_emitted_when_disabled(
        self, tmp_path, mock_conversation_state
    ):
        """测试当 emit_hook_events=False 时不发射 HookExecutionEvent。"""
        command = _json_command({"decision": "allow"})

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager,
            original_callback=capture_callback,
            emit_hook_events=False,  # 残疾人
        )
        processor.set_conversation_state(mock_conversation_state)

        original_event = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        )

        processor.on_event(original_event)

        # 应该只有 MessageEvent，没有 HookExecutionEvent
        hook_events = [e for e in processed_events if isinstance(e, HookExecutionEvent)]
        message_events = [e for e in processed_events if isinstance(e, MessageEvent)]

        assert len(hook_events) == 0
        assert len(message_events) == 1

    def test_hook_execution_event_captures_blocking(
        self, tmp_path, mock_conversation_state
    ):
        """测试 HookExecutionEvent 是否正确捕获阻塞状态。"""
        command = _json_command({"decision": "deny", "reason": "Blocked!"}, 2)

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager,
            original_callback=capture_callback,
            emit_hook_events=True,
        )
        processor.set_conversation_state(mock_conversation_state)

        original_event = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        )

        processor.on_event(original_event)

        hook_events = [e for e in processed_events if isinstance(e, HookExecutionEvent)]
        assert len(hook_events) == 1

        hook_event = hook_events[0]
        assert hook_event.blocked is True
        assert hook_event.reason == "Blocked!"
        assert hook_event.exit_code == 2

    def test_hook_execution_event_emitted_for_session_start(
        self, tmp_path, mock_conversation_state
    ):
        """测试是否为 SessionStart 挂钩发出 HookExecutionEvent。"""
        command = python_command("print('Session started')")

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager,
            original_callback=capture_callback,
            emit_hook_events=True,
        )
        processor.set_conversation_state(mock_conversation_state)

        processor.run_session_start()

        hook_events = [e for e in processed_events if isinstance(e, HookExecutionEvent)]
        assert len(hook_events) == 1

        hook_event = hook_events[0]
        assert hook_event.hook_event_type == "SessionStart"
        assert hook_event.success is True

    def test_hook_execution_event_emitted_for_stop(
        self, tmp_path, mock_conversation_state
    ):
        """测试是否为 Stop 挂钩发出 HookExecutionEvent。"""
        command = _json_command({"decision": "allow"})

        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        )

        manager = HookManager(config=config, working_dir=str(tmp_path))
        processed_events = []

        def capture_callback(event):
            processed_events.append(event)

        processor = HookEventProcessor(
            hook_manager=manager,
            original_callback=capture_callback,
            emit_hook_events=True,
        )
        processor.set_conversation_state(mock_conversation_state)

        should_stop, _ = processor.run_stop(reason="finish")

        assert should_stop is True

        hook_events = [e for e in processed_events if isinstance(e, HookExecutionEvent)]
        assert len(hook_events) == 1

        hook_event = hook_events[0]
        assert hook_event.hook_event_type == "Stop"
        assert hook_event.success is True
        assert hook_event.hook_input == {"reason": "finish"}
