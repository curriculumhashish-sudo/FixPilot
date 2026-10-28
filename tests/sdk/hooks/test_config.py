"""测试钩子配置加载和管理。"""

import json
import tempfile

import pytest
from pydantic import ValidationError

from openhands.sdk.hooks.config import HookConfig, HookDefinition, HookMatcher, HookType
from openhands.sdk.hooks.types import HookEventType


def test_command_hook_requires_command():
    with pytest.raises(ValidationError, match="'command' is required"):
        HookDefinition(type=HookType.COMMAND)


def test_command_hook_valid():
    h = HookDefinition(command="echo hi")
    assert h.type == HookType.COMMAND
    assert h.command == "echo hi"


def test_prompt_hook_valid():
    hook = HookDefinition(type=HookType.PROMPT, prompt="Block destructive commands")
    assert hook.type == HookType.PROMPT
    assert hook.command == ""


def test_prompt_hook_preserves_command_rest_contract():
    hook = HookDefinition(type=HookType.PROMPT, prompt="Block destructive commands")
    schema = HookDefinition.model_json_schema()

    assert "command" in schema["required"]
    assert schema["properties"]["command"] == {"title": "Command", "type": "string"}
    assert hook.model_dump()["command"] == ""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": "agent", "system_prompt": "Block writes to /etc"},
        {"type": "agent"},
    ],
    ids=["with-system-prompt", "without-system-prompt"],
)
def test_agent_hook_valid(kwargs):
    h = HookDefinition(**kwargs)
    assert h.type == HookType.AGENT


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"command": "block.sh"}, "block.sh"),
        (
            {
                "type": "agent",
                "name": "block-deletions",
                "system_prompt": "Block rm -rf",
            },
            "agent-hook:block-deletions",
        ),
        (
            {"type": "agent", "system_prompt": "Block network calls to external IPs"},
            "agent-hook:Block network calls ",
        ),
        ({"type": "agent", "system_prompt": "A" * 100}, f"agent-hook:{'A' * 20}"),
        ({"type": "agent"}, "agent-hook:agent"),
        (
            {
                "type": "prompt",
                "name": "block-deletions",
                "prompt": "Block rm -rf",
            },
            "prompt-hook:block-deletions",
        ),
        (
            {"type": "prompt", "prompt": "Block destructive shell commands"},
            "prompt-hook:Block destructive sh",
        ),
    ],
    ids=[
        "command",
        "agent-named",
        "agent-prompt-prefix",
        "agent-prompt-truncated",
        "agent-fallback",
        "prompt-named",
        "prompt-policy-prefix",
    ],
)
def test_display_command(kwargs, expected):
    h = HookDefinition(**kwargs)
    assert h.display_command == expected


def test_multiple_agent_hooks_are_distinguishable():
    hooks = [
        HookDefinition(
            type=HookType.AGENT,
            name="block-deletions",
            system_prompt="Block rm -rf",
        ),
        HookDefinition(
            type=HookType.AGENT,
            system_prompt="Block network calls to external IPs",
        ),
        HookDefinition(
            type=HookType.AGENT,
            system_prompt="Verify all tasks are complete",
        ),
    ]
    assert len({h.display_command for h in hooks}) == 3


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {"type": "agent", "command": "echo hi"},
            "'command' must not be set when type is 'agent'",
        ),
        (
            {
                "type": "prompt",
                "prompt": "Evaluate this event",
                "command": "echo hi",
            },
            "'command' must not be set when type is 'prompt'",
        ),
        ({"type": "command"}, "'command' is required"),
    ],
    ids=[
        "agent-rejects-command",
        "prompt-rejects-command",
        "command-requires-command",
    ],
)
def test_hook_definition_validation_errors(kwargs, match):
    with pytest.raises(Exception, match=match):
        HookDefinition(**kwargs)


def test_agent_hook_rejects_async():
    with pytest.raises(Exception, match="not supported for agent hooks"):
        HookDefinition.model_validate({"type": "agent", "async": True})


def test_prompt_hook_rejects_async():
    with pytest.raises(Exception, match="not supported for prompt hooks"):
        HookDefinition.model_validate(
            {"type": "prompt", "prompt": "Evaluate this event", "async": True}
        )


def test_agent_hook_from_json():
    data = {
        "stop": [
            {
                "hooks": [
                    {
                        "type": "agent",
                        "system_prompt": "Verify all tasks are done",
                        "timeout": 30,
                    }
                ]
            }
        ]
    }
    config = HookConfig.from_dict(data)
    hooks = config.get_hooks_for_event(HookEventType.STOP)
    assert len(hooks) == 1
    assert hooks[0].type == HookType.AGENT
    assert hooks[0].system_prompt == "Verify all tasks are done"
    assert hooks[0].timeout == 30


class TestHookMatcher:
    """测试 HookMatcher 模式匹配。"""

    def test_wildcard_matches_all(self):
        """测试 * 匹配所有工具名称。"""
        matcher = HookMatcher(matcher="*")
        assert matcher.matches("BashTool")
        assert matcher.matches("FileEditorTool")
        assert matcher.matches(None)

    def test_exact_match(self):
        """测试精确的字符串匹配。"""
        matcher = HookMatcher(matcher="BashTool")
        assert matcher.matches("BashTool")
        assert not matcher.matches("FileEditorTool")

    def test_regex_match_with_delimiters(self):
        """使用显式 /pattern/ 分隔符测试正则表达式模式匹配。"""
        matcher = HookMatcher(matcher="/.*Tool$/")
        assert matcher.matches("BashTool")
        assert matcher.matches("FileEditorTool")
        assert not matcher.matches("BashCommand")

    def test_regex_match_auto_detect(self):
        """测试正则表达式自动检测（没有分隔符的裸正则表达式）。"""
        # 管道字符触发正则表达式模式
        matcher = HookMatcher(matcher="Edit|Write")
        assert matcher.matches("Edit")
        assert matcher.matches("Write")
        assert not matcher.matches("Read")
        assert not matcher.matches("EditWrite")

        # 通配符模式
        matcher2 = HookMatcher(matcher="Bash.*")
        assert matcher2.matches("BashTool")
        assert matcher2.matches("BashCommand")
        assert not matcher2.matches("ShellTool")

    def test_empty_matcher_matches_all(self):
        """测试空字符串匹配器是否匹配所有工具。"""
        matcher = HookMatcher(matcher="")
        assert matcher.matches("BashTool")
        assert matcher.matches(None)


class TestHookConfig:
    """测试 HookConfig 加载和管理。"""

    def test_load_from_dict(self):
        """测试从字典加载配置。"""
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "BashTool",
                        "hooks": [{"type": "command", "command": "echo pre-hook"}],
                    }
                ]
            }
        }
        config = HookConfig.from_dict(data)
        assert config.has_hooks_for_event(HookEventType.PRE_TOOL_USE)
        hooks = config.get_hooks_for_event(HookEventType.PRE_TOOL_USE, "BashTool")
        assert len(hooks) == 1
        assert hooks[0].command == "echo pre-hook"

    def test_load_from_json_file(self):
        """测试从 JSON 文件加载配置。"""
        hook = {"type": "command", "command": "logger.sh", "timeout": 30}
        data = {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [hook]}]}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            config = HookConfig.load(f.name)

        assert config.has_hooks_for_event(HookEventType.POST_TOOL_USE)
        hooks = config.get_hooks_for_event(HookEventType.POST_TOOL_USE, "AnyTool")
        assert len(hooks) == 1
        assert hooks[0].timeout == 30

    def test_load_missing_file_returns_empty(self):
        """测试加载丢失的文件是否返回空配置。"""
        config = HookConfig.load("/nonexistent/path/hooks.json")
        assert config.is_empty()

    def test_load_discovers_config_in_working_dir(self):
        """load() 应该 openhands/hooks.json working_dir。"""
        hook = {"type": "command", "command": "test-hook.sh"}
        data = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}}

        with tempfile.TemporaryDirectory() as tmpdir:
            # 在工作目录中创建openhands/hooks.json
            import os

            hooks_dir = os.path.join(tmpdir, ".openhands")
            os.makedirs(hooks_dir)
            hooks_file = os.path.join(hooks_dir, "hooks.json")
            with open(hooks_file, "w") as f:
                json.dump(data, f)

            # 使用 working_dir (不 cwd) 加载
            config = HookConfig.load(working_dir=tmpdir)

            assert config.has_hooks_for_event(HookEventType.PRE_TOOL_USE)
            hooks = config.get_hooks_for_event(HookEventType.PRE_TOOL_USE, "AnyTool")
            assert len(hooks) == 1
            assert hooks[0].command == "test-hook.sh"

    def test_get_hooks_filters_by_tool_name(self):
        """测试挂钩是否按工具名称过滤。"""
        data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "BashTool",
                        "hooks": [{"type": "command", "command": "bash-hook.sh"}],
                    },
                    {
                        "matcher": "FileEditorTool",
                        "hooks": [{"type": "command", "command": "file-hook.sh"}],
                    },
                ]
            }
        }
        config = HookConfig.from_dict(data)

        bash_hooks = config.get_hooks_for_event(HookEventType.PRE_TOOL_USE, "BashTool")
        assert len(bash_hooks) == 1
        assert bash_hooks[0].command == "bash-hook.sh"

        file_hooks = config.get_hooks_for_event(
            HookEventType.PRE_TOOL_USE, "FileEditorTool"
        )
        assert len(file_hooks) == 1
        assert file_hooks[0].command == "file-hook.sh"

    def test_typed_field_instantiation(self):
        """测试使用类型化字段创建 HookConfig（推荐方法）。"""
        config = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="terminal",
                    hooks=[HookDefinition(command="block.sh", timeout=10)],
                )
            ],
            post_tool_use=[HookMatcher(hooks=[HookDefinition(command="log.sh")])],
        )

        assert config.has_hooks_for_event(HookEventType.PRE_TOOL_USE)
        assert config.has_hooks_for_event(HookEventType.POST_TOOL_USE)
        assert not config.has_hooks_for_event(HookEventType.STOP)

        hooks = config.get_hooks_for_event(HookEventType.PRE_TOOL_USE, "terminal")
        assert len(hooks) == 1
        assert hooks[0].command == "block.sh"
        assert hooks[0].timeout == 10

    def test_json_round_trip(self):
        """测试 model_dump 是否为往返生成与 JSON 兼容的输出。"""
        config = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="terminal",
                    hooks=[HookDefinition(command="test.sh")],
                )
            ]
        )

        # model_dump 应产生 snake_case 格式
        output = config.model_dump(mode="json", exclude_defaults=True)
        assert "pre_tool_use" in output
        assert output["pre_tool_use"][0]["matcher"] == "terminal"
        assert output["pre_tool_use"][0]["hooks"][0]["command"] == "test.sh"

        # 应该能够从输出重新加载
        reloaded = HookConfig.model_validate(output)
        assert reloaded.pre_tool_use == config.pre_tool_use

    def test_is_empty(self):
        """测试 is_empty() 正确识别空配置。"""
        empty_config = HookConfig()
        assert empty_config.is_empty()

        non_empty_config = HookConfig(
            pre_tool_use=[HookMatcher(hooks=[HookDefinition(command="a.sh")])],
        )
        assert not non_empty_config.is_empty()

    def test_legacy_format_is_still_supported(self):
        """测试旧格式是否仍受支持而不发出警告。"""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = HookConfig.from_dict(
                {"hooks": {"PreToolUse": [{"hooks": [{"command": "test.sh"}]}]}}
            )

        assert len(w) == 0
        assert cfg.pre_tool_use[0].hooks[0].command == "test.sh"

    def test_duplicate_keys_raises_error(self):
        """测试同时提供 PascalCase 和 snake_case 是否会引发错误。"""
        import pytest

        with pytest.raises(ValueError, match="Duplicate hook event"):
            HookConfig.from_dict(
                {
                    "PreToolUse": [{"hooks": [{"command": "a.sh"}]}],
                    "pre_tool_use": [{"hooks": [{"command": "b.sh"}]}],
                }
            )

    def test_unknown_event_type_raises_error(self):
        """测试事件类型中的拼写错误是否会引发有用的错误。"""
        import pytest

        with pytest.raises(ValueError, match="Unknown event type.*PreToolExecute"):
            HookConfig.from_dict(
                {"PreToolExecute": [{"hooks": [{"command": "test.sh"}]}]}
            )


class TestAsyncHooks:
    """测试异步挂钩配置。"""

    def test_async_field_defaults_false(self):
        """测试异步默认为 False。"""
        hook = HookDefinition(command="echo test")
        assert hook.async_ is False

    def test_async_field_set_true(self):
        """测试是否可以使用异步别名将异步设置为 True。"""
        hook = HookDefinition.model_validate({"command": "echo test", "async": True})
        assert hook.async_ is True

    def test_async_field_parsed_from_json_alias(self):
        """测试 JSON 中的“异步”键是否通过别名正确解析。"""
        data = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "*", "hooks": [{"command": "test.sh", "async": True}]}
                ]
            }
        }
        config = HookConfig.from_dict(data)
        hooks = config.get_hooks_for_event(HookEventType.POST_TOOL_USE, "AnyTool")
        assert len(hooks) == 1
        assert hooks[0].async_ is True

    def test_async_field_serialization_by_alias(self):
        """使用别名测试异步字段是否正确序列化。"""
        hook = HookDefinition.model_validate({"command": "test.sh", "async": True})
        output = hook.model_dump(mode="json", by_alias=True)
        assert output["async"] is True
        assert "async_" not in output

    def test_async_field_serialization_without_alias(self):
        """测试异步字段是否序列化为不带 by_alias 的 async_。"""
        hook = HookDefinition.model_validate({"command": "test.sh", "async": True})
        output = hook.model_dump(mode="json")
        assert output["async_"] is True

    def test_async_hook_in_config_round_trip(self):
        """测试异步钩子是否能够在 JSON 往返中幸存。"""
        data = {
            "PostToolUse": [
                {
                    "matcher": "terminal",
                    "hooks": [
                        {"command": "sync-hook.sh", "async": False},
                        {"command": "async-hook.sh", "async": True, "timeout": 30},
                    ],
                }
            ]
        }
        config = HookConfig.from_dict(data)
        hooks = config.get_hooks_for_event(HookEventType.POST_TOOL_USE, "terminal")

        assert len(hooks) == 2
        assert hooks[0].async_ is False
        assert hooks[1].async_ is True
        assert hooks[1].timeout == 30

    def test_multiple_async_hooks_across_events(self):
        """测试跨多个事件类型配置的异步挂钩。"""
        data = {
            "PostToolUse": [
                {"matcher": "*", "hooks": [{"command": "log.sh", "async": True}]}
            ],
            "SessionStart": [{"hooks": [{"command": "notify.sh", "async": True}]}],
        }
        config = HookConfig.from_dict(data)

        post_hooks = config.get_hooks_for_event(HookEventType.POST_TOOL_USE, "test")
        assert len(post_hooks) == 1
        assert post_hooks[0].async_ is True

        start_hooks = config.get_hooks_for_event(HookEventType.SESSION_START)
        assert len(start_hooks) == 1
        assert start_hooks[0].async_ is True


def test_issue_2749():
    """基于提示词的停止挂钩不应导致验证错误。

    https://github.com/OpenHands/software-agent-sdk/issues/2749
    """
    data = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "prompt",
                            "prompt": "Evaluate if we should stop.",
                        }
                    ],
                }
            ]
        }
    }
    config = HookConfig.from_dict(data)
    hooks = config.get_hooks_for_event(HookEventType.STOP)
    assert len(hooks) == 1
    assert hooks[0].type.value == "prompt"
    assert hooks[0].prompt == "Evaluate if we should stop."


@pytest.mark.parametrize(
    ("hook_type", "match"),
    [
        (HookType.COMMAND, "command"),
        (HookType.PROMPT, "'prompt' is required"),
    ],
    ids=["command_requires_command", "prompt_requires_prompt"],
)
def test_issue_2749_validation(hook_type: HookType, match: str):
    """验证器应根据挂钩类型强制执行必填字段。

    https://github.com/OpenHands/software-agent-sdk/issues/2749
    """
    with pytest.raises(ValidationError, match=match):
        HookDefinition(type=hook_type)  # type: ignore[call-arg]


def test_hook_config_typed_events_and_merge():
    """HookConfig 方法访问无需动态 getattr 键入的事件。"""
    matcher = HookMatcher(matcher="*")
    cfg1 = HookConfig(pre_tool_use=[matcher], session_start=[matcher])
    cfg2 = HookConfig(post_tool_use=[matcher], stop=[matcher])

    for evt in HookEventType:
        matchers = cfg1._get_matchers_for_event(evt)
        assert isinstance(matchers, list)

    assert len(cfg1._get_matchers_for_event(HookEventType.PRE_TOOL_USE)) == 1
    assert len(cfg1._get_matchers_for_event(HookEventType.POST_TOOL_USE)) == 0

    merged = HookConfig.merge([cfg1, cfg2])
    assert merged is not None
    assert len(merged.pre_tool_use) == 1
    assert len(merged.post_tool_use) == 1
    assert len(merged.session_start) == 1
    assert len(merged.stop) == 1
    assert len(merged.user_prompt_submit) == 0

    with pytest.raises(RuntimeError, match="Unhandled hook event type"):
        cfg1._get_matchers_for_event("unknown_event")  # type: ignore[arg-type]
