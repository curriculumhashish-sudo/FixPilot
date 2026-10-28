"""测试钩子执行器。"""

import json
import subprocess
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.hooks.config import HookDefinition, HookType
from openhands.sdk.hooks.executor import HookExecutor
from openhands.sdk.hooks.types import HookDecision, HookEvent, HookEventType
from openhands.sdk.llm import LLM, Message, TextContent, content_to_str
from openhands.sdk.llm.call_context import LLMCallContext
from openhands.sdk.llm.utils.metrics import Metrics
from tests.command_utils import python_command


class TestHookExecutor:
    """测试 HookExecutor。"""

    @pytest.fixture
    def executor(self, tmp_path):
        """创建一个带有临时工作目录的执行器。"""
        return HookExecutor(working_dir=str(tmp_path))

    @pytest.fixture
    def sample_event(self):
        """创建示例挂钩事件。"""
        return HookEvent(
            event_type=HookEventType.PRE_TOOL_USE,
            tool_name="BashTool",
            tool_input={"command": "ls -la"},
            session_id="test-session",
        )

    def test_execute_simple_command(self, executor, sample_event):
        """测试执行简单的 echo 命令。"""
        hook = HookDefinition(command="echo 'success'")
        result = executor.execute(hook, sample_event)

        assert result.success
        assert result.exit_code == 0
        assert "success" in result.stdout

    def test_execute_receives_json_stdin(self, executor, sample_event, tmp_path):
        """测试钩子在标准输入上接收事件数据为 JSON。"""
        hook = HookDefinition(
            command=python_command("import sys; sys.stdout.write(sys.stdin.read())")
        )
        result = executor.execute(hook, sample_event)

        assert result.success
        output_data = json.loads(result.stdout)
        assert output_data["event_type"] == "PreToolUse"
        assert output_data["tool_name"] == "BashTool"

    def test_null_decision_leaves_a_successful_hook_successful(
        self, executor, sample_event
    ):
        hook = HookDefinition(command="""echo '{"decision": null}'""")

        result = executor.execute(hook, sample_event)

        assert result.success
        assert result.exit_code == 0
        assert result.decision is None
        assert not result.error

    def test_non_string_decision_is_ignored_rather_than_fatal(
        self, executor, sample_event
    ):
        """任何非字符串决策都意味着没有决策，而不是失败的钩子。"""
        hook = HookDefinition(command="""echo '{"decision": 1}'""")

        result = executor.execute(hook, sample_event)

        assert result.success
        assert result.decision is None

    def test_string_decisions_still_parse(self, executor, sample_event):
        hook = HookDefinition(command="""echo '{"decision": "allow"}'""")

        result = executor.execute(hook, sample_event)

        assert result.decision == HookDecision.ALLOW

    def test_execute_blocking_exit_code(self, executor, sample_event):
        """测试退出代码 2 是否阻止操作。"""
        hook = HookDefinition(command=python_command("import sys; sys.exit(2)"))
        result = executor.execute(hook, sample_event)

        assert not result.success
        assert result.blocked
        assert result.exit_code == 2
        assert not result.should_continue

    def test_execute_json_output_decision(self, executor, sample_event):
        """使用决策字段测试解析 JSON 输出。"""
        hook = HookDefinition(
            command=python_command(
                "import json; print(json.dumps("
                "{'decision': 'deny', 'reason': 'Not allowed'}))"
            )
        )
        result = executor.execute(hook, sample_event)

        assert result.decision == HookDecision.DENY
        assert result.reason == "Not allowed"
        assert result.blocked

    def test_execute_environment_variables(self, executor, sample_event, tmp_path):
        """测试环境变量设置是否正确。"""
        hook = HookDefinition(
            command=python_command(
                "import os; "
                "print(f\"SESSION={os.environ['OPENHANDS_SESSION_ID']}\"); "
                "print(f\"TOOL={os.environ['OPENHANDS_TOOL_NAME']}\")"
            )
        )

        result = executor.execute(hook, sample_event)

        assert result.success
        assert "SESSION=test-session" in result.stdout
        assert "TOOL=BashTool" in result.stdout

    def test_execute_timeout(self, executor, sample_event):
        """测试超时是否已强制执行。"""
        hook = HookDefinition(
            command=python_command("import time; time.sleep(10)"), timeout=1
        )
        result = executor.execute(hook, sample_event)

        assert not result.success
        assert "timed out" in result.error.lower()

    def test_execute_all_stops_on_block(self, executor, sample_event):
        """测试 execute_all 是否停止在阻塞钩子上。"""
        hooks = [
            HookDefinition(command="echo 'first'"),
            HookDefinition(command=python_command("import sys; sys.exit(2)")),
            HookDefinition(command="echo 'third'"),
        ]

        results = executor.execute_all(hooks, sample_event, stop_on_block=True)

        assert len(results) == 2  # 第二个钩子后停止
        assert results[0].success
        assert results[1].blocked

    def test_execute_captures_stderr(self, executor, sample_event):
        """测试 stderr 是否被捕获。"""
        hook = HookDefinition(
            command=python_command(
                "import sys; sys.stderr.write('error message\\n'); sys.exit(2)"
            )
        )
        result = executor.execute(hook, sample_event)

        assert result.blocked
        assert "error message" in result.stderr


class TestAsyncHookExecution:
    """测试异步挂钩执行。"""

    @pytest.fixture
    def executor(self, tmp_path):
        """创建一个带有临时工作目录的执行器。"""
        return HookExecutor(working_dir=str(tmp_path))

    @pytest.fixture
    def sample_event(self):
        """创建示例挂钩事件。"""
        return HookEvent(
            event_type=HookEventType.POST_TOOL_USE,
            tool_name="TestTool",
            tool_input={"arg": "value"},
            session_id="test-session",
        )

    def test_execute_async_hook_returns_immediately(self, executor, sample_event):
        """测试异步钩子立即返回，无需等待。"""
        import time

        hook = HookDefinition.model_validate(
            {"command": python_command("import time; time.sleep(5)"), "async": True}
        )

        start = time.time()
        result = executor.execute(hook, sample_event)
        elapsed = time.time() - start

        assert result.success
        assert result.async_started
        assert elapsed < 1.0  # 应立即返回，而不是等待 5 秒

    def test_execute_async_hook_result_fields(self, executor, sample_event):
        """测试异步挂钩结果是否具有预期的字段值。"""
        hook = HookDefinition.model_validate({"command": "echo 'test'", "async": True})
        result = executor.execute(hook, sample_event)

        assert result.success is True
        assert result.async_started is True
        assert result.exit_code == 0
        assert result.blocked is False
        assert result.stdout == ""  # 未捕获异步的输出
        assert result.stderr == ""

    def test_execute_async_hook_process_tracked(self, executor, sample_event, tmp_path):
        """测试异步挂钩跟踪进程以进行清理。"""
        marker = tmp_path / "async_marker.txt"
        hook = HookDefinition.model_validate(
            {
                "command": python_command(
                    "import time; "
                    "from pathlib import Path; "
                    "time.sleep(0.3); "
                    f"Path({str(marker)!r}).touch()"
                ),
                "async": True,
                "timeout": 5,
            }
        )

        result = executor.execute(hook, sample_event)
        assert result.async_started

        # 应跟踪流程
        assert len(executor.async_process_manager._processes) == 1

        # 等待进程完成并验证创建的标记文件
        import time

        time.sleep(0.5)
        assert marker.exists()

    def test_execute_async_hook_receives_stdin(self, executor, sample_event, tmp_path):
        """测试异步挂钩是否接收 stdin 上的事件数据。"""
        output_file = tmp_path / "stdin_output.json"
        # 读取 stdin 并写入文件的脚本
        hook = HookDefinition.model_validate(
            {
                "command": python_command(
                    "import sys; "
                    "from pathlib import Path; "
                    f"Path({str(output_file)!r}).write_text(sys.stdin.read())"
                ),
                "async": True,
                "timeout": 5,
            }
        )

        result = executor.execute(hook, sample_event)
        assert result.async_started

        # 等待异步进程完成
        import json
        import time

        time.sleep(0.3)

        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert content["tool_name"] == "TestTool"
        assert content["event_type"] == "PostToolUse"

    def test_execute_async_hook_uses_windows_process_group(
        self, executor, sample_event, monkeypatch
    ):
        """通过在任何运行器上模拟 win32 来测试 Windows 进程组 kwargs。"""
        import openhands.sdk.hooks.executor as executor_module

        popen_kwargs: dict[str, object] = {}
        stdin = mock.Mock()
        process = mock.Mock()
        process.stdin = stdin
        process.poll.return_value = None

        def fake_popen(*args, **kwargs):
            popen_kwargs.update(kwargs)
            return process

        monkeypatch.setattr(executor_module.os, "name", "nt", raising=False)
        monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
        monkeypatch.setattr(subprocess, "Popen", fake_popen)

        hook = HookDefinition.model_validate({"command": "echo test", "async": True})
        result = executor.execute(hook, sample_event)

        assert result.async_started is True
        assert popen_kwargs["creationflags"] == 512
        assert popen_kwargs["start_new_session"] is False

    def test_sync_hook_not_marked_async(self, executor, sample_event):
        """测试同步挂钩未标记为 async_started。"""
        hook = HookDefinition.model_validate({"command": "echo 'sync'", "async": False})
        result = executor.execute(hook, sample_event)

        assert result.success
        assert result.async_started is False
        assert "sync" in result.stdout

    def test_execute_all_with_mixed_sync_async_hooks(
        self, executor, sample_event, tmp_path
    ):
        """混合使用同步和异步钩子测试 execute_all。"""
        marker = tmp_path / "async_ran.txt"
        hooks = [
            HookDefinition(command="echo 'sync1'"),
            HookDefinition.model_validate(
                {
                    "command": python_command(
                        f"from pathlib import Path; Path({str(marker)!r}).touch()"
                    ),
                    "async": True,
                }
            ),
            HookDefinition(command="echo 'sync2'"),
        ]

        results = executor.execute_all(hooks, sample_event, stop_on_block=False)

        assert len(results) == 3
        assert results[0].async_started is False
        assert results[1].async_started is True
        assert results[2].async_started is False

        # 等待异步挂钩完成
        import time

        time.sleep(0.2)
        assert marker.exists()


class TestAsyncProcessManager:
    """测试 AsyncProcessManager。"""

    def test_add_process_and_cleanup_all(self, tmp_path):
        """测试是否可以添加和清理进程。"""
        from openhands.sdk.hooks.executor import AsyncProcessManager

        manager = AsyncProcessManager()

        # 使用新会话启动长时间运行的进程以进行进程组清理
        process = subprocess.Popen(
            python_command("import time; time.sleep(60)"),
            shell=True,
            cwd=str(tmp_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        manager.add_process(process, timeout=30)
        assert len(manager._processes) == 1
        assert process.poll() is None  # 仍在运行

        manager.cleanup_all()
        assert len(manager._processes) == 0

        # 给进程一些时间终止
        import time

        time.sleep(0.1)
        assert process.poll() is not None  # 终止

    def test_cleanup_expired_terminates_old_processes(self, tmp_path):
        """测试 cleanup_expired 终止进程超时。"""
        import time

        from openhands.sdk.hooks.executor import AsyncProcessManager

        manager = AsyncProcessManager()

        # 启动一个非常短的超时且已过期的进程
        process = subprocess.Popen(
            python_command("import time; time.sleep(60)"),
            shell=True,
            cwd=str(tmp_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # 在过去添加超时（通过设置开始时间来模拟）
        manager._processes.append(
            (process, time.time() - 10, 5)
        )  # 10 秒前开始，5 秒前开始超时

        assert process.poll() is None  # 仍在运行
        manager.cleanup_expired()

        time.sleep(0.1)
        assert process.poll() is not None  # 终止
        assert len(manager._processes) == 0

    def test_async_process_manager_windows_kill_uses_bounded_wait(self, monkeypatch):
        """测试 Windows 清理不会在终止后无限期等待。"""
        import openhands.sdk.hooks.executor as executor_module
        from openhands.sdk.hooks.executor import AsyncProcessManager

        process = mock.Mock()
        process.pid = 123
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="cmd", timeout=1),
            subprocess.TimeoutExpired(cmd="cmd", timeout=1),
        ]

        taskkill_calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            taskkill_calls.append(args)
            return mock.Mock()

        monkeypatch.setattr(executor_module.os, "name", "nt", raising=False)
        monkeypatch.setattr(subprocess, "run", fake_run)

        manager = AsyncProcessManager()
        manager._terminate_process(process)

        assert taskkill_calls == [["taskkill", "/F", "/T", "/PID", "123"]]
        assert process.wait.call_args_list == [
            mock.call(timeout=1),
            mock.call(timeout=1),
        ]
        process.kill.assert_called_once_with()

    def test_cleanup_expired_keeps_active_processes(self, tmp_path):
        """测试 cleanup_expired 是否将进程保留在其超时内。"""
        from openhands.sdk.hooks.executor import AsyncProcessManager

        manager = AsyncProcessManager()

        process = subprocess.Popen(
            python_command("import time; time.sleep(60)"),
            shell=True,
            cwd=str(tmp_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        manager.add_process(process, timeout=60)  # 长超时

        manager.cleanup_expired()

        # 进程仍应被跟踪和运行
        assert len(manager._processes) == 1
        assert process.poll() is None

        # 清理测试拆卸
        process.terminate()


class TestAgentHookExecution:
    """测试 HookType.AGENT 执行路径。"""

    # 包/模块级别的补丁因此懒惰的 `from X import Y` 选择了模拟对象。
    _AGENT_PATH = "openhands.sdk.agent.Agent"
    _CONV_PATH = "openhands.sdk.conversation.impl.local_conversation.LocalConversation"
    _RESPONSE_PATH = (
        "openhands.sdk.conversation.response_utils.get_agent_final_response"
    )

    @pytest.fixture
    def mock_llm(self):
        return LLM(model="gpt-4o", api_key=SecretStr("test-key"), usage_id="test")

    @pytest.fixture
    def executor(self, tmp_path, mock_llm):
        return HookExecutor(working_dir=str(tmp_path), llm=mock_llm)

    @pytest.fixture
    def executor_no_llm(self, tmp_path):
        return HookExecutor(working_dir=str(tmp_path), llm=None)

    @pytest.fixture
    def sample_event(self):
        return HookEvent(
            event_type=HookEventType.STOP,
            session_id="test-session",
        )

    def test_execute_dispatches_to_agent_hook(self, executor, sample_event):
        """execute() 将 AGENT 类型路由到 _execute_agent_hook，而不是子进程。"""
        from openhands.sdk.hooks.executor import HookResult

        hook = HookDefinition(
            type=HookType.AGENT,
            system_prompt="Verify task completion",
        )

        with patch.object(
            executor,
            "_execute_agent_hook",
            return_value=HookResult(
                success=True, decision=HookDecision.ALLOW, reason="ok"
            ),
        ) as mock_agent:
            result = executor.execute(hook, sample_event)
            mock_agent.assert_called_once_with(hook, sample_event)

        assert result.decision == HookDecision.ALLOW
        assert result.should_continue

    def test_no_llm_defaults_to_allow(self, executor_no_llm, sample_event):
        """智能体没有配置 LLM 的钩子默认允许，不会出现错误。"""
        hook = HookDefinition(
            type=HookType.AGENT,
            system_prompt="Check something",
        )
        result = executor_no_llm.execute(hook, sample_event)

        assert not result.success
        assert result.decision == HookDecision.ALLOW
        assert not result.blocked

    def test_deny_decision_blocks(self, executor, sample_event):
        """_execute_agent_hook 解析拒绝 JSON 会产生阻止的 HookResult。"""
        deny_json = '{"decision": "deny", "reason": "Tasks not complete"}'

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=deny_json),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(
                type=HookType.AGENT,
                system_prompt="Check tasks",
            )
            result = executor._execute_agent_hook(hook, sample_event)

        assert result.blocked
        assert result.decision == HookDecision.DENY
        assert result.reason == "Tasks not complete"
        assert not result.should_continue

    def test_allow_decision_passes(self, executor, sample_event):
        """_execute_agent_hook 解析允许 JSON 产生非阻塞 HookResult。"""
        allow_json = '{"decision": "allow", "reason": "Looks safe"}'

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=allow_json),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.reason == "Looks safe"

    @pytest.mark.parametrize(
        "payload",
        [
            '{"reason": "no decision field"}',
            '{"decision": "maybe", "reason": "not allow or deny"}',
            '{"decision": "", "reason": "empty decision"}',
        ],
    )
    def test_invalid_decision_falls_open(self, executor, sample_event, payload):
        """缺失/未知的决定是一种开放性的决定，而不是故意的允许。"""
        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=payload),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.should_continue
        assert result.success is False
        assert result.error is not None

    def test_markdown_wrapped_deny_is_parsed(self, executor, sample_event):
        """```JSON fenced JSON 被尊重，而不是被当作非 JSON."""
        fenced = '```json\n{"decision": "deny", "reason": "Sensitive file read"}\n```'

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=fenced),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert result.blocked
        assert result.decision == HookDecision.DENY
        assert result.reason == "Sensitive file read"

    def test_plain_fence_without_language_tag_is_parsed(self, executor, sample_event):
        """一些 LLMs 使用 ``` 而没有语言标签 — 仍然提取 JSON。"""
        fenced = '```\n{"decision": "allow", "reason": "ok"}\n```'

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=fenced),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.reason == "ok"

    def test_prose_prefix_before_json_is_parsed(self, executor, sample_event):
        """JSON 对象之前的散文不能击败解析器。"""
        prose_then_json = (
            "After reviewing the workspace I found REPORT.md is missing.\n\n"
            '{"decision": "deny", "reason": "missing deliverable"}'
        )

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=prose_then_json),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert result.blocked
        assert result.decision == HookDecision.DENY
        assert result.reason == "missing deliverable"

    def test_prose_suffix_after_json_is_parsed(self, executor, sample_event):
        """JSON 对象之后的尾随喋喋不休不能击败解析器。"""
        json_then_prose = (
            '{"decision": "deny", "reason": "sensitive file"}\n\n'
            "Let me know if you need more details."
        )

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=json_then_prose),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert result.blocked
        assert result.decision == HookDecision.DENY
        assert result.reason == "sensitive file"

    def test_invalid_json_defaults_to_allow(self, executor, sample_event):
        """非 JSON 响应打开：ALLOW + 成功=False + 错误集。"""
        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value="I think you should allow this."),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.should_continue
        assert result.success is False
        assert result.error is not None

    def test_sub_conversation_failure_defaults_to_allow(self, executor, sample_event):
        """_execute_agent_hook 当子对话引发时默认允许。"""
        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH, side_effect=RuntimeError("workspace error")),
        ):
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.error is not None

    def test_empty_response_defaults_to_allow(self, executor, sample_event):
        """_execute_agent_hook 当智能体不产生响应时默认允许。"""
        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH) as mock_conv_cls,
            patch(self._RESPONSE_PATH, return_value=""),
        ):
            mock_conv_cls.return_value = MagicMock()
            hook = HookDefinition(type=HookType.AGENT)
            result = executor._execute_agent_hook(hook, sample_event)

        assert not result.blocked
        assert result.decision == HookDecision.ALLOW
        assert result.success is False

    def test_timeout_propagated_to_hook_llm(self, executor, sample_event):
        """hook.timeout 被转发到复制的 LLM，父级的超时保持不变。"""
        parent_timeout = executor.llm.timeout
        captured_llm = {}

        def capture_agent_init(**kwargs):
            captured_llm["llm"] = kwargs.get("llm")
            return MagicMock()

        with (
            patch(self._AGENT_PATH, side_effect=capture_agent_init),
            patch(self._CONV_PATH, side_effect=RuntimeError("stop early")),
        ):
            hook = HookDefinition(type=HookType.AGENT, timeout=7)
            executor._execute_agent_hook(hook, sample_event)

        hook_llm = captured_llm.get("llm")
        assert hook_llm is not None
        assert hook_llm.timeout == 7
        assert executor.llm.timeout == parent_timeout

    def test_agent_hook_inherits_llm_call_context(
        self, tmp_path, mock_llm, sample_event
    ):
        context = LLMCallContext(
            prompt_cache_key="parent-cache",
            session_id="parent-session",
        )
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm=mock_llm,
            llm_call_context=context,
        )

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH, side_effect=RuntimeError("stop early")) as mock_conv,
        ):
            executor._execute_agent_hook(
                HookDefinition(type=HookType.AGENT), sample_event
            )

        assert mock_conv.call_args.kwargs["_parent_llm_call_context"] is context

    def test_hook_metrics_under_usage_id(self, executor, sample_event):
        """Hook LLM 使用每个 hook usage_id 和一个独立的 Metrics 对象。"""
        parent_metrics = executor.llm.metrics

        captured_llm = {}

        def capture_agent_init(**kwargs):
            captured_llm["llm"] = kwargs.get("llm")
            return MagicMock()

        with (
            patch(self._AGENT_PATH, side_effect=capture_agent_init),
            patch(self._CONV_PATH, side_effect=RuntimeError("stop early")),
        ):
            hook = HookDefinition(type=HookType.AGENT)
            executor._execute_agent_hook(hook, sample_event)

        hook_llm = captured_llm.get("llm")
        assert hook_llm is not None
        assert hook_llm is not executor.llm
        assert hook_llm.usage_id == "agent-hook:default"
        assert hook_llm.metrics is not parent_metrics

    def test_llm_getter_is_resolved_live(self, tmp_path, sample_event):
        """llm_getter 在执行时被读取，因此智能体钩子跟随
        switch_llm()/switch_profile() 而不是使用捕获的过时的 LLM。"""
        current = {
            "llm": LLM(model="gpt-4o", api_key=SecretStr("k1"), usage_id="first")
        }
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm_getter=lambda: current["llm"],
        )

        # 模拟 switch_llm()：会话重新绑定其智能体的 LLM。
        current["llm"] = LLM(
            model="gpt-5.5", api_key=SecretStr("k2"), usage_id="second"
        )

        captured_llm = {}

        def capture_agent_init(**kwargs):
            captured_llm["llm"] = kwargs.get("llm")
            return MagicMock()

        with (
            patch(self._AGENT_PATH, side_effect=capture_agent_init),
            patch(self._CONV_PATH, side_effect=RuntimeError("stop early")),
        ):
            executor._execute_agent_hook(
                HookDefinition(type=HookType.AGENT), sample_event
            )

        hook_llm = captured_llm.get("llm")
        assert hook_llm is not None
        # 从 *current* LLM (gpt-5.5) 复制，而不是 init 中存在的那个。
        assert hook_llm.model == "gpt-5.5"

    def test_hook_metrics_are_merged_into_parent_stats(
        self, tmp_path, mock_llm, sample_event
    ):
        """子智能体-hook 支出包含在父对话统计数据中。"""
        parent_stats = ConversationStats()
        existing_hook_metrics = Metrics(model_name="gpt-4o")
        existing_hook_metrics.add_cost(0.25)
        parent_stats.usage_to_metrics["agent-hook:security-check"] = (
            existing_hook_metrics
        )

        child_hook_metrics = Metrics(model_name="gpt-4o")
        child_hook_metrics.add_cost(0.75)
        child_stats = ConversationStats(
            usage_to_metrics={"agent-hook:security-check": child_hook_metrics}
        )
        mock_conversation = MagicMock()
        mock_conversation.conversation_stats = child_stats
        mock_conversation.state.events = []

        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm=mock_llm,
            conversation_stats=parent_stats,
        )

        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH, return_value=mock_conversation),
            patch(
                self._RESPONSE_PATH,
                return_value='{"decision": "allow", "reason": "ok"}',
            ),
        ):
            hook = HookDefinition(type=HookType.AGENT, name="security-check")
            result = executor._execute_agent_hook(hook, sample_event)

        assert result.decision == HookDecision.ALLOW
        assert parent_stats.usage_to_metrics[
            "agent-hook:security-check"
        ].accumulated_cost == pytest.approx(1.0)
        assert parent_stats.get_combined_metrics().accumulated_cost == pytest.approx(
            1.0
        )

    def test_hook_usage_id_uses_hook_name(self, executor, sample_event):
        """命名钩子拥有自己的 usage_id 存储桶：智能体-钩子：<name>。"""
        captured_llm = {}

        def capture_agent_init(**kwargs):
            captured_llm["llm"] = kwargs.get("llm")
            return MagicMock()

        with (
            patch(self._AGENT_PATH, side_effect=capture_agent_init),
            patch(self._CONV_PATH, side_effect=RuntimeError("stop early")),
        ):
            hook = HookDefinition(type=HookType.AGENT, name="security-check")
            executor._execute_agent_hook(hook, sample_event)

        hook_llm = captured_llm.get("llm")
        assert hook_llm is not None
        assert hook_llm.usage_id == "agent-hook:security-check"

    def test_parent_visualizer_instance_is_not_rebound(self, tmp_path, mock_llm):
        """父可视化工具实例绝不能交给钩子转换。

        LocalConversation.initialize() 将可视化器实例重新绑定到其自己的状态，因此执行
        器必须请求一个新的子可视化器。
        """
        from openhands.sdk.conversation.visualizer import ConversationVisualizerBase

        sub_viz = MagicMock(spec=ConversationVisualizerBase)

        class _Viz(ConversationVisualizerBase):
            def on_event(self, event):  # pragma: no cover - not exercised
                pass

            def create_sub_visualizer(self, agent_id):
                self.requested_agent_id = agent_id
                return sub_viz

        parent_viz = _Viz()
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm=mock_llm,
            visualizer=parent_viz,
        )

        captured = {}

        def capture_conv_init(**kwargs):
            captured["visualizer"] = kwargs.get("visualizer")
            raise RuntimeError("stop early")

        sample_event = HookEvent(
            event_type=HookEventType.PRE_TOOL_USE, tool_name="BashTool"
        )
        with (
            patch(self._AGENT_PATH),
            patch(self._CONV_PATH, side_effect=capture_conv_init),
        ):
            hook = HookDefinition(type=HookType.AGENT, name="security-check")
            executor._execute_agent_hook(hook, sample_event)

        assert captured["visualizer"] is sub_viz
        assert captured["visualizer"] is not parent_viz
        assert parent_viz.requested_agent_id == "agent-hook:security-check"


class TestPromptHookExecution:
    """测试单完成 HookType.PROMPT 执行路径。"""

    @pytest.fixture
    def mock_llm(self):
        return LLM(model="gpt-4o", api_key=SecretStr("test-key"), usage_id="test")

    @pytest.fixture
    def executor(self, tmp_path, mock_llm):
        return HookExecutor(working_dir=str(tmp_path), llm=mock_llm)

    @pytest.fixture
    def executor_no_llm(self, tmp_path):
        return HookExecutor(working_dir=str(tmp_path), llm=None)

    @pytest.fixture
    def sample_event(self):
        return HookEvent(
            event_type=HookEventType.PRE_TOOL_USE,
            tool_name="BashTool",
            tool_input={"command": "rm -rf build"},
            session_id="test-session",
        )

    @staticmethod
    def _completion_response(raw: str):
        return MagicMock(
            message=Message(
                role="assistant",
                content=[TextContent(text=raw)],
            )
        )

    def test_execute_dispatches_to_prompt_hook(self, executor, sample_event):
        hook = HookDefinition(type=HookType.PROMPT, prompt="Block destructive commands")

        with patch.object(
            executor,
            "_execute_prompt_hook",
            return_value=MagicMock(decision=HookDecision.ALLOW),
        ) as mock_prompt:
            executor.execute(hook, sample_event)

        mock_prompt.assert_called_once_with(hook, sample_event)

    @pytest.mark.parametrize(
        "payload,expected_decision,expected_blocked",
        [
            (
                '{"decision": "allow", "reason": "Command is reversible"}',
                HookDecision.ALLOW,
                False,
            ),
            (
                '{"decision": "deny", "reason": "Command deletes files"}',
                HookDecision.DENY,
                True,
            ),
        ],
    )
    def test_completion_decision_is_parsed(
        self,
        executor,
        sample_event,
        payload,
        expected_decision,
        expected_blocked,
    ):
        with patch.object(
            LLM,
            "completion",
            return_value=self._completion_response(payload),
        ):
            result = executor.execute(
                HookDefinition(
                    type=HookType.PROMPT,
                    prompt="Block destructive commands",
                ),
                sample_event,
            )

        assert result.success
        assert result.decision == expected_decision
        assert result.blocked is expected_blocked

    def test_policy_and_untrusted_event_are_separate_messages(
        self, executor, sample_event
    ):
        captured_messages = []

        def capture_completion(_llm, messages, **_kwargs):
            captured_messages.extend(messages)
            return self._completion_response('{"decision": "allow", "reason": "safe"}')

        with patch.object(
            LLM, "completion", autospec=True, side_effect=capture_completion
        ):
            executor.execute(
                HookDefinition(
                    type=HookType.PROMPT,
                    prompt="Block destructive commands",
                ),
                sample_event,
            )

        assert [message.role for message in captured_messages] == ["system", "user"]
        system_text = "\n".join(content_to_str(captured_messages[0].content))
        event_text = "\n".join(content_to_str(captured_messages[1].content))
        assert "Block destructive commands" in system_text
        assert '"command": "rm -rf build"' in event_text
        assert "untrusted" in event_text.lower()

    @pytest.mark.parametrize(
        "uses_responses_api,called_method,uncalled_method",
        [
            (False, "completion", "responses"),
            (True, "responses", "completion"),
        ],
        ids=["chat-completions", "responses-api"],
    )
    def test_uses_model_appropriate_llm_api(
        self,
        executor,
        sample_event,
        uses_responses_api,
        called_method,
        uncalled_method,
    ):
        response = self._completion_response('{"decision": "allow", "reason": "safe"}')

        with (
            patch.object(
                LLM,
                "uses_responses_api",
                return_value=uses_responses_api,
            ),
            patch.object(LLM, called_method, return_value=response) as expected_call,
            patch.object(LLM, uncalled_method) as unexpected_call,
        ):
            result = executor.execute(
                HookDefinition(type=HookType.PROMPT, prompt="Evaluate this event"),
                sample_event,
            )

        assert result.decision == HookDecision.ALLOW
        expected_call.assert_called_once()
        unexpected_call.assert_not_called()

    @pytest.mark.parametrize(
        "response",
        [
            "",
            "ALLOW",
            '{"decision": "maybe", "reason": "uncertain"}',
        ],
    )
    def test_invalid_response_falls_open(self, executor, sample_event, response):
        with patch.object(
            LLM,
            "completion",
            return_value=self._completion_response(response),
        ):
            result = executor.execute(
                HookDefinition(type=HookType.PROMPT, prompt="Evaluate this event"),
                sample_event,
            )

        assert not result.success
        assert result.decision == HookDecision.ALLOW
        assert not result.blocked
        assert result.error is not None

    def test_no_llm_falls_open(self, executor_no_llm, sample_event):
        result = executor_no_llm.execute(
            HookDefinition(type=HookType.PROMPT, prompt="Evaluate this event"),
            sample_event,
        )

        assert not result.success
        assert result.decision == HookDecision.ALLOW
        assert result.error is not None

    def test_completion_failure_falls_open(self, executor, sample_event):
        with patch.object(LLM, "completion", side_effect=RuntimeError("provider down")):
            result = executor.execute(
                HookDefinition(type=HookType.PROMPT, prompt="Evaluate this event"),
                sample_event,
            )

        assert not result.success
        assert result.decision == HookDecision.ALLOW
        assert result.error == "provider down"

    def test_timeout_usage_id_and_metrics_are_isolated(self, executor, sample_event):
        parent_metrics = executor.llm.metrics
        captured_llm = None
        executor.llm.stream = True

        def capture_completion(hook_llm, messages, **_kwargs):
            nonlocal captured_llm
            assert messages
            captured_llm = hook_llm
            return self._completion_response('{"decision": "allow", "reason": "safe"}')

        with patch.object(
            LLM, "completion", autospec=True, side_effect=capture_completion
        ):
            executor.execute(
                HookDefinition(
                    type=HookType.PROMPT,
                    name="safety-check",
                    prompt="Evaluate this event",
                    timeout=7,
                ),
                sample_event,
            )

        assert captured_llm is not None
        assert captured_llm is not executor.llm
        assert captured_llm.timeout == 7
        assert captured_llm.usage_id == "prompt-hook:safety-check"
        assert captured_llm.metrics is not parent_metrics
        assert captured_llm.stream is False
        assert executor.llm.stream is True

    def test_hook_metrics_are_merged_into_parent_stats(
        self, tmp_path, mock_llm, sample_event
    ):
        parent_stats = ConversationStats()
        existing_metrics = Metrics(model_name="gpt-4o")
        existing_metrics.add_cost(0.25)
        parent_stats.usage_to_metrics["prompt-hook:policy"] = existing_metrics
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm=mock_llm,
            conversation_stats=parent_stats,
        )

        def add_hook_cost(hook_llm, messages, **_kwargs):
            assert messages
            hook_llm.metrics.add_cost(0.75)
            return self._completion_response('{"decision": "allow", "reason": "safe"}')

        with patch.object(LLM, "completion", autospec=True, side_effect=add_hook_cost):
            executor.execute(
                HookDefinition(
                    type=HookType.PROMPT,
                    name="policy",
                    prompt="Evaluate this event",
                ),
                sample_event,
            )

        assert parent_stats.usage_to_metrics[
            "prompt-hook:policy"
        ].accumulated_cost == pytest.approx(1.0)

    def test_repeated_prompt_hooks_merge_metrics(
        self, tmp_path, mock_llm, sample_event
    ):
        parent_stats = ConversationStats()
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm=mock_llm,
            conversation_stats=parent_stats,
        )
        hook = HookDefinition(
            type=HookType.PROMPT,
            name="policy",
            prompt="Evaluate this event",
        )

        def add_hook_cost(hook_llm, messages, **_kwargs):
            assert messages
            hook_llm.metrics.add_cost(0.5)
            return self._completion_response('{"decision": "allow", "reason": "safe"}')

        with patch.object(LLM, "completion", autospec=True, side_effect=add_hook_cost):
            results = executor.execute_all([hook, hook], sample_event)

        assert len(results) == 2
        assert parent_stats.usage_to_metrics[
            "prompt-hook:policy"
        ].accumulated_cost == pytest.approx(1.0)

    def test_execute_all_stops_after_prompt_deny(self, executor, sample_event):
        hooks = [
            HookDefinition(
                type=HookType.PROMPT,
                name="deny",
                prompt="Deny this event",
            ),
            HookDefinition(
                type=HookType.PROMPT,
                name="never-called",
                prompt="Evaluate this event",
            ),
        ]

        with patch.object(
            LLM,
            "completion",
            return_value=self._completion_response(
                '{"decision": "deny", "reason": "blocked"}'
            ),
        ) as completion:
            results = executor.execute_all(hooks, sample_event, stop_on_block=True)

        assert len(results) == 1
        assert results[0].blocked
        completion.assert_called_once()

    def test_llm_getter_is_resolved_live(self, tmp_path, sample_event):
        current = {
            "llm": LLM(model="gpt-4o", api_key=SecretStr("k1"), usage_id="first")
        }
        executor = HookExecutor(
            working_dir=str(tmp_path),
            llm_getter=lambda: current["llm"],
        )
        current["llm"] = LLM(
            model="gpt-5.5",
            api_key=SecretStr("k2"),
            usage_id="second",
        )
        captured_model = None

        def capture_completion(hook_llm, messages, **_kwargs):
            nonlocal captured_model
            assert messages
            captured_model = hook_llm.model
            return self._completion_response('{"decision": "allow", "reason": "safe"}')

        with patch.object(
            LLM, "responses", autospec=True, side_effect=capture_completion
        ):
            executor.execute(
                HookDefinition(type=HookType.PROMPT, prompt="Evaluate this event"),
                sample_event,
            )

        assert captured_model == "gpt-5.5"
