"""测试 HookManager。"""

import pytest

from openhands.sdk.hooks.config import HookConfig
from openhands.sdk.hooks.manager import HookManager
from openhands.sdk.hooks.types import HookDecision
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM
from tests.command_utils import python_command, sleep_command, touch_command


class TestHookManager:
    """测试 HookManager 编排。"""

    @pytest.fixture
    def tmp_working_dir(self, tmp_path):
        """Create a temporary 工作目录。"""
        return str(tmp_path)

    @pytest.fixture
    def config_with_blocking_hook(self, tmp_path):
        """使用阻塞 PreToolUse 挂钩创建配置。"""
        command = python_command(
            "import json, sys; "
            "print(json.dumps({'decision': 'deny', 'reason': 'Blocked by test'})); "
            "sys.exit(2)"
        )

        return HookConfig.from_dict(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "BashTool",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        )

    def test_run_pre_tool_use_blocks_when_hook_denies(
        self, tmp_working_dir, config_with_blocking_hook
    ):
        """测试当 hook 拒绝时 PreToolUse 是否阻塞。"""
        manager = HookManager(
            config=config_with_blocking_hook,
            working_dir=tmp_working_dir,
            session_id="test-session",
        )

        should_continue, results = manager.run_pre_tool_use(
            tool_name="BashTool",
            tool_input={"command": "rm -rf /"},
        )

        assert not should_continue
        assert len(results) == 1
        assert results[0].blocked

    def test_run_post_tool_use(self, tmp_working_dir, tmp_path):
        """测试 PostToolUse 挂钩执行。"""
        log_file = tmp_path / "log.txt"

        hook = {
            "type": "command",
            "command": python_command(
                "from pathlib import Path; "
                f"Path({str(log_file)!r}).write_text('logged\\n')"
            ),
        }
        config = HookConfig.from_dict(
            {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        results = manager.run_post_tool_use(
            tool_name="BashTool",
            tool_input={"command": "ls"},
            tool_response={"output": "file1.txt\nfile2.txt"},
        )

        assert len(results) == 1
        assert results[0].success
        assert log_file.read_text().strip() == "logged"

    def test_run_user_prompt_submit(self, tmp_working_dir):
        """测试 UserPromptSubmit 挂钩执行并返回 additionalContext。"""
        cmd = python_command(
            "import json; "
            "print(json.dumps({'additionalContext': 'Always check tests'}))"
        )
        config = HookConfig.from_dict(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        should_continue, additional_context, results = manager.run_user_prompt_submit(
            message="Hello, agent!"
        )

        assert should_continue
        assert additional_context == "Always check tests"
        assert len(results) == 1

    def test_run_session_start(self, tmp_working_dir, tmp_path):
        """测试 SessionStart 挂钩执行。"""
        marker_file = tmp_path / "started"

        hook = {"type": "command", "command": touch_command(marker_file)}
        config = HookConfig.from_dict(
            {"hooks": {"SessionStart": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        results = manager.run_session_start()

        assert len(results) == 1
        assert results[0].success
        assert marker_file.exists()

    def test_run_stop_blocked_means_continue(self, tmp_working_dir, tmp_path):
        """测试阻塞 Stop 钩子意味着智能体应该继续。"""
        hook = {
            "type": "command",
            "command": python_command(
                "import json, sys; print(json.dumps({'decision': 'deny'})); sys.exit(2)"
            ),
        }
        config = HookConfig.from_dict(
            {"hooks": {"Stop": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        should_stop, results = manager.run_stop()

        assert not should_stop  # 阻塞意味着不要停止（继续）

    def test_get_blocking_reason(self, tmp_working_dir):
        """测试 get_blocking_reason 从结果中提取原因。"""
        from openhands.sdk.hooks.executor import HookResult

        manager = HookManager(config=HookConfig(), working_dir=tmp_working_dir)

        # 有理由场
        results = [HookResult(blocked=True, reason="Custom reason")]
        assert manager.get_blocking_reason(results) == "Custom reason"

        # 与标准错误
        results = [HookResult(blocked=True, stderr="Error from stderr\n")]
        assert manager.get_blocking_reason(results) == "Error from stderr"

        # 默认消息
        results = [HookResult(blocked=True)]
        assert manager.get_blocking_reason(results) == "Blocked by hook"

        # 没有被阻止
        results = [HookResult(success=True)]
        assert manager.get_blocking_reason(results) is None


def _prompt_decision(decision: str, reason: str) -> Message:
    return Message(
        role="assistant",
        content=[
            TextContent(text=f'{{"decision": "{decision}", "reason": "{reason}"}}')
        ],
    )


def test_pre_tool_use_prompt_deny_blocks(tmp_path):
    config = HookConfig.from_dict(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "BashTool",
                        "hooks": [
                            {
                                "type": "prompt",
                                "prompt": "Block destructive commands",
                            }
                        ],
                    }
                ]
            }
        }
    )
    llm = TestLLM.from_messages([_prompt_decision("deny", "Destructive command")])
    manager = HookManager(config=config, working_dir=str(tmp_path), llm=llm)

    should_continue, results = manager.run_pre_tool_use(
        "BashTool", {"command": "rm -rf build"}
    )

    assert not should_continue
    assert len(results) == 1
    assert results[0].decision == HookDecision.DENY
    assert results[0].reason == "Destructive command"


def test_stop_prompt_deny_keeps_agent_running(tmp_path):
    config = HookConfig.from_dict(
        {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "prompt",
                                "prompt": "Require every requested task to be complete",
                            }
                        ]
                    }
                ]
            }
        }
    )
    llm = TestLLM.from_messages([_prompt_decision("deny", "Task is incomplete")])
    manager = HookManager(config=config, working_dir=str(tmp_path), llm=llm)

    should_stop, results = manager.run_stop(reason="Agent requested finish")

    assert not should_stop
    assert len(results) == 1
    assert results[0].blocked
    assert results[0].reason == "Task is incomplete"


class TestAsyncHookManager:
    """测试 HookManager 中的异步钩子处理。"""

    @pytest.fixture
    def tmp_working_dir(self, tmp_path):
        """Create a temporary 工作目录。"""
        return str(tmp_path)

    def test_async_pre_tool_use_logs_warning(self, tmp_working_dir, caplog):
        """测试异步 PreToolUse 挂钩是否记录警告。"""
        import logging

        hook = {"type": "command", "command": "echo test", "async": True}
        config = HookConfig.from_dict(
            {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)

        with caplog.at_level(logging.WARNING):
            manager.run_pre_tool_use("BashTool", {"command": "ls"})

        assert "Async hooks in PreToolUse cannot block tool execution" in caplog.text
        assert "1 async hook(s)" in caplog.text

    def test_async_pre_tool_use_still_runs(self, tmp_working_dir, tmp_path):
        """测试异步 PreToolUse 钩子是否在出现警告的情况下仍然执行。"""
        marker = tmp_path / "async_ran.txt"
        hook = {"type": "command", "command": touch_command(marker), "async": True}
        config = HookConfig.from_dict(
            {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        should_continue, results = manager.run_pre_tool_use(
            "BashTool", {"command": "ls"}
        )

        assert should_continue  # 异步钩子无法阻塞
        assert len(results) == 1
        assert results[0].async_started

        # 等待异步挂钩完成
        import time

        time.sleep(0.2)
        assert marker.exists()

    def test_cleanup_async_processes_on_session_end(self, tmp_working_dir, tmp_path):
        """测试会话结束是否清理异步个进程。"""
        hook = {"type": "command", "command": sleep_command(60), "async": True}
        config = HookConfig.from_dict(
            {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)

        # 启动异步事件钩子
        results = manager.run_post_tool_use("TestTool", {}, {"result": "ok"})
        assert len(results) == 1
        assert results[0].async_started
        assert len(manager.executor.async_process_manager._processes) == 1

        # 会话结束应该清理
        manager.run_session_end()
        assert len(manager.executor.async_process_manager._processes) == 0

    def test_cleanup_async_processes_method(self, tmp_working_dir, tmp_path):
        """直接测试cleanup_async_processes方法。"""
        hook = {"type": "command", "command": sleep_command(60), "async": True}
        config = HookConfig.from_dict(
            {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [hook]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)

        # 启动异步事件钩子
        manager.run_post_tool_use("TestTool", {}, {"result": "ok"})
        assert len(manager.executor.async_process_manager._processes) == 1

        # 直接清理
        manager.cleanup_async_processes()
        assert len(manager.executor.async_process_manager._processes) == 0

    def test_mixed_sync_async_hooks_in_post_tool_use(self, tmp_working_dir, tmp_path):
        """使用同步和异步挂钩测试 PostToolUse。"""
        sync_marker = tmp_path / "sync.txt"
        async_marker = tmp_path / "async.txt"

        config = HookConfig.from_dict(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "command": touch_command(sync_marker),
                                    "async": False,
                                },
                                {
                                    "command": python_command(
                                        "import time; "
                                        "from pathlib import Path; "
                                        "time.sleep(0.2); "
                                        f"Path({str(async_marker)!r}).touch()"
                                    ),
                                    "async": True,
                                },
                            ],
                        }
                    ]
                }
            }
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        results = manager.run_post_tool_use("TestTool", {}, {"result": "ok"})

        # 同步挂钩应立即完成
        assert sync_marker.exists()

        # 应该有 2 个结果
        assert len(results) == 2
        assert results[0].async_started is False
        assert results[1].async_started is True

        # 异步标记尚不应该存在
        assert not async_marker.exists()

        # 等待异步触发器
        import time

        time.sleep(0.4)
        assert async_marker.exists()

    def test_session_end_runs_hooks_before_cleanup(self, tmp_working_dir, tmp_path):
        """测试会话结束挂钩在异步进程清理之前运行。"""
        marker = tmp_path / "session_end.txt"
        config = HookConfig.from_dict(
            {"hooks": {"SessionEnd": [{"hooks": [{"command": touch_command(marker)}]}]}}
        )

        manager = HookManager(config=config, working_dir=tmp_working_dir)
        results = manager.run_session_end()

        assert len(results) == 1
        assert results[0].success
        assert marker.exists()
