"""测试可配置的安全策略功能。"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.event import ActionEvent, AgentErrorEvent
from openhands.sdk.llm import LLM, Message, TextContent


def test_security_policy_in_system_message():
    """测试系统消息中是否包含安全策略。"""
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )
    system_message = agent.static_system_message

    # 验证安全策略部分是否存在
    assert "🔐 Security Policy" in system_message
    assert "OK to do without Explicit User Consent" in system_message
    assert "Do only with Explicit User Consent" in system_message
    assert "Never Do" in system_message

    # 验证特定政策项目是否存在
    assert (
        "Download and run code from a repository specified by a user" in system_message
    )
    assert "Open pull requests on the original repositories" in system_message
    assert (
        "Install and run popular packages from **official** package registries"
        in system_message
    )
    assert (
        "Upload code to anywhere other than the location where it was obtained"
        in system_message
    )
    assert "Upload API keys or tokens anywhere" in system_message
    assert "Relocate or copy a secrets-bearing file" in system_message
    assert "Never perform any illegal activities" in system_message
    assert "Never run software to mine cryptocurrency" in system_message

    # 验证所有安全准则是否已合并到策略中
    assert "General Security Guidelines" in system_message
    assert "Only use GITHUB_TOKEN and other credentials" in system_message
    assert "Use APIs to work with GitHub or other platforms" in system_message
    assert (
        "This [message/comment/issue/PR] was created by an AI agent" in system_message
    )
    assert "AI assistant (OpenHands)" not in system_message


def test_none_security_policy_filename_disables_policy_without_null_public_value():
    """测试 None 输入禁用该策略而不暴露 null 合约。"""
    agent = Agent.model_validate(
        {
            "llm": LLM(
                usage_id="test-llm",
                model="test-model",
                api_key=SecretStr("test-key"),
                base_url="http://test",
            ),
            "security_policy_filename": None,
        }
    )

    assert agent.security_policy_filename == ""
    assert agent.model_dump()["security_policy_filename"] == ""
    assert "🔐 Security Policy" not in agent.static_system_message


def test_custom_security_policy_in_system_message():
    """自定义安全策略文件的内容解析为系统消息
    通过注册表（无模板复制或 Jinja 逃生舱口）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_policy_path = Path(temp_dir) / "custom_policy.j2"
        custom_policy_content = (
            "# 🔐 Custom Test Security Policy\n"
            "This is a custom security policy for testing.\n"
            "- **CUSTOM_RULE**: Always test custom policies."
        )
        custom_policy_path.write_text(custom_policy_content, encoding="utf-8")

        agent = Agent(
            llm=LLM(
                usage_id="test-llm",
                model="test-model",
                api_key=SecretStr("test-key"),
                base_url="http://test",
            ),
            security_policy_filename=str(custom_policy_path),
        )

        system_message = agent.static_system_message

        # 自定义策略内容出现...
        assert "Custom Test Security Policy" in system_message
        assert "CUSTOM_RULE" in system_message
        assert "Always test custom policies" in system_message
        # ...and the built-in default policy does not leak in alongside it.
        assert "Download and run code from a repository" not in system_message


def test_custom_security_policy_is_inserted_verbatim_not_rendered():
    """自定义策略文件作为原始文本注入——对 Jinja 语法进行不评估。

    有意契约（安全策略不应该是模板注入表面）； 用于渲染它的旧 ``{% include %}`` 路径
    。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        policy_path = Path(temp_dir) / "custom_policy.j2"
        policy_path.write_text(
            "# Policy for {{ model_name }}\n- {% if cli_mode %}rule{% endif %}",
            encoding="utf-8",
        )
        agent = Agent(
            llm=LLM(
                usage_id="test-llm",
                model="test-model",
                api_key=SecretStr("test-key"),
                base_url="http://test",
            ),
            security_policy_filename=str(policy_path),
        )
        system_message = agent.static_system_message

        # Jinja 保留字面意思，不进行评估。
        assert "# Policy for {{ model_name }}" in system_message
        assert "{% if cli_mode %}rule{% endif %}" in system_message


def test_empty_custom_security_policy_does_not_leak_default():
    """明确为空的自定义策略文件不得回退到默认值。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        empty_policy = Path(temp_dir) / "empty_policy.j2"
        empty_policy.write_text("", encoding="utf-8")
        agent = Agent(
            llm=LLM(
                usage_id="test-llm",
                model="test-model",
                api_key=SecretStr("test-key"),
                base_url="http://test",
            ),
            security_policy_filename=str(empty_policy),
        )
        system_message = agent.static_system_message

        assert "🔐 Security Policy" not in system_message
        assert "Download and run code from a repository" not in system_message


def test_llm_security_analyzer_template_kwargs():
    """测试智能体设置 template_kwargs 时，安全分析器为 LLMSecurityAnalyzer。"""  # noqa: E501
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        ),
    )

    # 获取系统消息（自动包含安全分析器上下文）
    system_message = agent.static_system_message

    # 验证系统中是否包含安全风险评估部分提示词
    assert "<SECURITY_RISK_ASSESSMENT>" in system_message
    assert "# Security Risk Policy" in system_message
    assert "When using tools that support the security_risk parameter" in system_message
    # 默认情况下，cli_mode是True，所以我们应该看到CLI模式版本
    assert "**LOW**: Safe, read-only actions" in system_message
    assert "**MEDIUM**: Project-scoped edits or execution" in system_message
    assert "**HIGH**: System-level or untrusted operations" in system_message
    assert "**Global Rules**" in system_message


def test_llm_security_analyzer_sandbox_mode():
    """当cli_mode=False时，测试智能体包括沙盒模式安全风险评估。"""  # noqa: E501
    # 使用 cli_mode=False 创建智能体
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        ),
        system_prompt_kwargs={"cli_mode": False},
    )

    # 获取系统消息（自动包含安全分析器上下文）
    system_message = agent.static_system_message

    print(agent.system_prompt_kwargs)

    # 验证安全风险评估部分包含沙箱模式的内容  # noqa: E501
    assert "<SECURITY_RISK_ASSESSMENT>" in system_message
    assert "# Security Risk Policy" in system_message
    assert "When using tools that support the security_risk parameter" in system_message
    # 当cli_mode=False时，我们应该看到沙盒模式版本
    assert "**LOW**: Read-only actions inside sandbox" in system_message
    assert "**MEDIUM**: Container-scoped edits and installs" in system_message
    assert "**HIGH**: Data exfiltration or privilege breaks" in system_message
    assert "**Global Rules**" in system_message


def test_no_security_analyzer_still_includes_risk_assessment():
    """测试未设置安全分析器时是否排除安全风险评估部分。"""  # noqa: E501
    # 不使用安全分析器创建智能体
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )

    # 无需安全分析器即可获取系统消息
    system_message = agent.static_system_message

    # 验证是否包含安全风险评估部分不
    assert "<SECURITY_RISK_ASSESSMENT>" in system_message
    assert "# Security Risk Policy" in system_message
    assert "When using tools that support the security_risk parameter" in system_message


def test_non_llm_security_analyzer_still_includes_risk_assessment():
    """测试安全风险评估部分在安全分析器 LLMSecurityAnalyzer 时被排除。"""  # noqa: E501
    from openhands.sdk.security.analyzer import SecurityAnalyzerBase
    from openhands.sdk.security.risk import SecurityRisk

    class MockSecurityAnalyzer(SecurityAnalyzerBase):
        def security_risk(self, action: ActionEvent) -> SecurityRisk:
            return SecurityRisk.LOW

    # 创建智能体（安全分析器功能已已弃用并删除）
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        ),
    )

    # 获取系统消息
    system_message = agent.static_system_message

    # 验证是否包含安全风险评估部分不
    assert "<SECURITY_RISK_ASSESSMENT>" in system_message
    assert "# Security Risk Policy" in system_message
    assert "When using tools that support the security_risk parameter" in system_message


def _tool_response(name: str, args_json: str) -> ModelResponse:
    return ModelResponse(
        id="mock-response",
        choices=[
            Choices(
                index=0,
                message=LiteLLMMessage(
                    role="assistant",
                    content="tool call with security_risk",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call_1",
                            type="function",
                            function=Function(name=name, arguments=args_json),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        created=0,
        model="test-model",
        object="chat.completion",
    )


def test_security_risk_param_ignored_when_no_analyzer():
    """当未配置分析器时，安全风险参数将被忽略。

    此测试重现了 #1957 中的问题，其中 LLM 在工具调用中包含 security_risk，即使
    llm_security_analyzer=False 且未配
    置安全分析器也是如此。

    预期行为：当未设置分析器时，security_risk 应为 UNKNOWN。
    """
    from openhands.sdk.security.risk import SecurityRisk

    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    # 在system_prompt_kwargs中设置llm_security_analyzer=False
    agent = Agent(
        llm=llm, tools=[], system_prompt_kwargs={"llm_security_analyzer": False}
    )

    events = []
    convo = Conversation(agent=agent, callbacks=[events.append])

    # 模拟对象  LLM 包含的响应 security_risk=HIGH even though
    # llm_security_analyzer=False (the LLM might do this if it's well-trained)
    with patch(
        "openhands.sdk.llm.llm.litellm_completion",
        return_value=_tool_response(
            "think",
            '{"thought": "This is a test thought", "security_risk": "HIGH"}',
        ),
    ):
        convo.send_message(
            Message(role="user", content=[TextContent(text="Please think")])
        )
        agent.step(convo, on_event=events.append)

    # 没有智能体个错误
    assert not any(isinstance(e, AgentErrorEvent) for e in events)

    # 找到ActionEvent
    action_events = [e for e in events if isinstance(e, ActionEvent)]
    assert len(action_events) == 1

    # 验证未设置分析器时 security_risk 是否为 UNKNOWN（忽略） 即使 LLM 提供了“HIGH”，也
    # 应忽略
    #
    assert action_events[0].security_risk == SecurityRisk.UNKNOWN
