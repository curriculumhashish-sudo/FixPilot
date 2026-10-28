"""测试智能体与机密管理器的集成。"""

import sys
from typing import cast
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM
from openhands.sdk.secret import LookupSecret, SecretSource, StaticSecret
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.terminal import TerminalTool
from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.impl import TerminalExecutor


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="TerminalTool V1 backend is not supported on Windows.",
)


class MySecretSource(SecretSource):
    def get_value(self):
        return "dynamic-token-123"


class MyFailingSecretSource(SecretSource):
    def get_value(self):
        raise ValueError("Secret retrieval failed")


class MyDynamicSecretSource(SecretSource):
    def get_value(self):
        return "dynamic-secret"


class MyChangingDynamicSecretSource(SecretSource):
    counter: int = 0

    def get_value(self):
        self.counter += 1
        return f"changing-secret-{self.counter}"


class MyChangingFailingDynamicSecretSource(SecretSource):
    counter: int = 0
    raised_on_second: bool = False

    def get_value(self):
        self.counter += 1
        if self.counter == 1:
            return f"changing-secret-{self.counter}"
        self.raised_on_second = True
        raise Exception("Blip occured, failed to refresh token")


# -----------------------
# 测试夹具
# -----------------------


@pytest.fixture
def llm() -> LLM:
    return LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")


@pytest.fixture
def tools() -> list[Tool]:
    register_tool("TerminalTool", TerminalTool)
    return [Tool(name="TerminalTool")]


@pytest.fixture
def agent(llm: LLM, tools: list[Tool]) -> Agent:
    return Agent(llm=llm, tools=tools)


@pytest.fixture
def conversation(agent: Agent, tmp_path) -> LocalConversation:
    return LocalConversation(agent, workspace=str(tmp_path))


@pytest.fixture
def terminal_executor(conversation: LocalConversation) -> TerminalExecutor:
    # 访问 tools_map 之前触发延迟初始化
    conversation._ensure_agent_ready()
    tools_map = conversation.agent.tools_map
    terminal_tool = tools_map["terminal"]
    return cast(TerminalExecutor, terminal_tool.executor)


@pytest.fixture
def agent_no_bash(llm: LLM) -> Agent:
    return Agent(llm=llm, tools=[])


@pytest.fixture
def conversation_no_bash(agent_no_bash: Agent, tmp_path) -> LocalConversation:
    return LocalConversation(agent_no_bash, workspace=str(tmp_path))


def test_agent_configures_bash_tools_env_provider(
    conversation: LocalConversation, terminal_executor: TerminalExecutor, agent: Agent
):
    """测试 bash 执行器是否可以与对话一起使用机密。"""
    # 将机密添加到对话
    conversation.update_secrets(
        {
            "API_KEY": "test-api-key",
            "DB_PASSWORD": "test-password",
        }
    )

    # 从智能体获取 bash 工具
    bash_tool = agent.tools_map["terminal"]

    assert bash_tool is not None
    assert bash_tool.executor is not None

    # 测试是否可以通过对话访问机密
    secret_registry = conversation.state.secret_registry
    env_vars = secret_registry.get_secrets_as_env_vars("echo $API_KEY")
    assert env_vars == {"API_KEY": "test-api-key"}

    env_vars = secret_registry.get_secrets_as_env_vars("echo $NOT_A_KEY")
    assert env_vars == {}


def test_agent_env_provider_with_callable_secrets(
    conversation: LocalConversation, terminal_executor: TerminalExecutor
):
    """测试机密与可调用机密的对话是否正常。"""

    conversation.update_secrets(
        {
            "STATIC_KEY": "static-value",
            "DYNAMIC_TOKEN": MySecretSource(),
        }
    )

    secret_registry = conversation.state.secret_registry
    env_vars = secret_registry.get_secrets_as_env_vars(
        "export DYNAMIC_TOKEN=$DYNAMIC_TOKEN"
    )
    assert env_vars == {"DYNAMIC_TOKEN": "dynamic-token-123"}


def test_agent_env_provider_handles_exceptions(
    conversation: LocalConversation, terminal_executor: TerminalExecutor
):
    """测试对话机密是否优雅地处理异常。"""

    conversation.update_secrets(
        {
            "WORKING_KEY": "working-value",
            "FAILING_KEY": MyFailingSecretSource(),
        }
    )

    secret_registry = conversation.state.secret_registry

    # 不应引发异常，应返回空字典
    env_vars = secret_registry.get_secrets_as_env_vars(
        "export FAILING_KEY=$FAILING_KEY"
    )
    assert env_vars == {}

    # 工作键应该仍然有效
    env_vars = secret_registry.get_secrets_as_env_vars(
        "export WORKING_KEY=$WORKING_KEY"
    )
    assert env_vars == {"WORKING_KEY": "working-value"}


def test_agent_env_provider_no_matches(
    conversation: LocalConversation, terminal_executor: TerminalExecutor
):
    """当命令没有机密匹配时测试对话机密。"""

    conversation.update_secrets({"API_KEY": "test-value"})

    # 使用未引用机密的命令测试机密管理器
    secret_registry = conversation.state.secret_registry
    env_vars = secret_registry.get_secrets_as_env_vars("echo hello world")

    assert env_vars == {}


def test_agent_without_bash_throws_warning(llm):
    """当不存在 bash 工具时，测试智能体是否正常工作。"""
    # 由于我们移除了 _configure_bash_tools_env_provider 智能体不再记录缺少 bash 工具的警
    # 告，这个测试已经不再相关了。创建没有 bash 工具的对话应该可以正常工作
    #
    conversation = Conversation(agent=Agent(llm=llm, tools=[]))
    assert conversation is not None
    conversation.close()


# ---------------------------------------------------------------------------
# agent_context.secrets → secret_registry 提升（画布/TypeScript 间隙固定）
# ---------------------------------------------------------------------------


def test_agent_context_secrets_seeded_into_registry_at_init(llm, tmp_path):
    """agent_context.secrets 登陆 secret_registry，没有任何 request.secrets。

    覆盖调用者 (e.g. canvas / TypeScript) 直接构建 StartConversationRequest 而无需经
    过
    create_request()，因此 agent_context.secrets 只能通过 _start_acp_server() 排水管
    可见。
    """
    agent = Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            secrets={"ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-from-ctx"))}
        ),
    )
    conv = LocalConversation(agent, workspace=str(tmp_path))
    try:
        registry = conv.state.secret_registry
        assert registry.get_secret_value("ANTHROPIC_API_KEY") == "sk-from-ctx"
    finally:
        conv.close()


def test_request_secrets_win_over_agent_context_secrets_on_collision(llm, tmp_path):
    """当两者命名相同的键时，request.secrets 会覆盖 agent_context.secrets。

    request.secrets 是规范通道，必须具有更高的优先级。
    """
    agent = Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            secrets={"ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-from-ctx"))}
        ),
    )
    request_secrets = {
        "ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-from-request"))
    }
    conv = LocalConversation(agent, workspace=str(tmp_path), secrets=request_secrets)
    try:
        registry = conv.state.secret_registry
        assert registry.get_secret_value("ANTHROPIC_API_KEY") == "sk-from-request"
    finally:
        conv.close()


def test_agent_context_and_request_secrets_are_merged(llm, tmp_path):
    """两个通道中不冲突的密钥显示在 secret_registry 中。"""
    agent = Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            secrets={"ANTHROPIC_API_KEY": StaticSecret(value=SecretStr("sk-provider"))}
        ),
    )
    request_secrets = {"GITHUB_TOKEN": StaticSecret(value=SecretStr("ghp-panel"))}
    conv = LocalConversation(agent, workspace=str(tmp_path), secrets=request_secrets)
    try:
        registry = conv.state.secret_registry
        assert registry.get_secret_value("ANTHROPIC_API_KEY") == "sk-provider"
        assert registry.get_secret_value("GITHUB_TOKEN") == "ghp-panel"
    finally:
        conv.close()


def test_no_agent_context_does_not_raise(llm, tmp_path):
    """当智能体没有 agent_context 时，会话初始化成功。"""
    agent = Agent(llm=llm, tools=[], agent_context=None)
    conv = LocalConversation(agent, workspace=str(tmp_path))
    try:
        assert conv.state.secret_registry.get_secret_value("NONEXISTENT") is None
    finally:
        conv.close()


def test_agent_secrets_integration_workflow(
    conversation: LocalConversation, terminal_executor: TerminalExecutor, agent: Agent
):
    """测试对话机密集成的完整工作流程。"""

    # 将机密与混合类型相加

    with patch("httpx.get") as mock_get:
        mock_get.return_value.text = "bearer-token-456"

        conversation.update_secrets(
            {
                "API_KEY": "static-api-key-123",
                "AUTH_TOKEN": LookupSecret(url="https://my-idp.com/"),
                "DATABASE_URL": "postgresql://localhost/test",
            }
        )

        secret_registry = conversation.state.secret_registry

        # 单曲机密
        env_vars = secret_registry.get_secrets_as_env_vars(
            "curl -H 'X-API-Key: $API_KEY'"
        )
        assert env_vars == {"API_KEY": "static-api-key-123"}

        # 多个机密
        command = "export API_KEY=$API_KEY && export AUTH_TOKEN=$AUTH_TOKEN"
        env_vars = secret_registry.get_secrets_as_env_vars(command)
        assert env_vars == {
            "API_KEY": "static-api-key-123",
            "AUTH_TOKEN": "bearer-token-456",
        }

        # 没有引用机密
        env_vars = secret_registry.get_secrets_as_env_vars("echo hello world")
        assert env_vars == {}

    # 第 5 步：更新机密并验证更改是否已传播
    conversation.update_secrets({"API_KEY": "updated-api-key-789"})

    secret_registry = conversation.state.secret_registry
    env_vars = secret_registry.get_secrets_as_env_vars("curl -H 'X-API-Key: $API_KEY'")
    assert env_vars == {"API_KEY": "updated-api-key-789"}


def test_mask_secrets(
    conversation: LocalConversation, terminal_executor: TerminalExecutor, agent: Agent
):
    """测试会话通过时 bash 执行器是否屏蔽机密。"""

    # 将机密添加到对话
    conversation.update_secrets(
        {
            "API_KEY": "test-api-key",
            "DB_PASSWORD": MyDynamicSecretSource(),
        }
    )

    try:
        action = TerminalAction(command="echo $API_KEY")
        result = terminal_executor(action, conversation=conversation)
        assert "test-api-key" not in result.text
        assert "<secret-hidden>" in result.text

        action = TerminalAction(command="echo $DB_PASSWORD")
        result = terminal_executor(action, conversation=conversation)
        assert "dynamic-secret" not in result.text
        assert "<secret-hidden>" in result.text

    finally:
        terminal_executor.close()


def test_mask_changing_secrets(
    conversation: LocalConversation, terminal_executor: TerminalExecutor, agent: Agent
):
    conversation.update_secrets(
        {
            "DB_PASSWORD": MyChangingDynamicSecretSource(),
        }
    )

    try:
        action = TerminalAction(command="echo $DB_PASSWORD")
        result = terminal_executor(action, conversation=conversation)
        assert "changing-secret" not in result.text
        assert "<secret-hidden>" in result.text

        action = TerminalAction(command="echo $DB_PASSWORD")
        result = terminal_executor(action, conversation=conversation)
        assert "changing-secret" not in result.text
        assert "<secret-hidden>" in result.text

    finally:
        terminal_executor.close()


def test_masking_persists(
    conversation: LocalConversation, terminal_executor: TerminalExecutor, agent: Agent
):
    dynamic_secret = MyChangingFailingDynamicSecretSource()
    conversation.update_secrets(
        {
            "DB_PASSWORD": dynamic_secret,
        }
    )

    try:
        action = TerminalAction(command="echo $DB_PASSWORD")
        result = terminal_executor(action, conversation=conversation)
        print(result)
        assert "changing-secret" not in result.text
        assert "<secret-hidden>" in result.text

        action = TerminalAction(command="echo $DB_PASSWORD")
        result = terminal_executor(action, conversation=conversation)
        assert "changing-secret" not in result.text
        assert "<secret-hidden>" in result.text
        assert dynamic_secret.raised_on_second

    finally:
        terminal_executor.close()


# -----------------------
# 测试系统提示词中的机密
# -----------------------


def test_update_secrets_adds_to_registry(conversation: LocalConversation):
    """测试 update_secrets 将机密添加到 secret_registry。"""
    # 添加机密
    conversation.update_secrets(
        {
            "API_KEY": StaticSecret(
                value=SecretStr("test-key"), description="API authentication key"
            ),
            "DB_PASSWORD": "plain-secret-value",
        }
    )

    # 验证机密在 secret_registry 中
    secret_infos = conversation.state.secret_registry.get_secret_infos()
    secret_names = [s["name"] for s in secret_infos]
    assert "API_KEY" in secret_names
    assert "DB_PASSWORD" in secret_names


def test_update_secrets_appears_in_dynamic_context(conversation: LocalConversation):
    """测试通过 update_secrets 添加的机密是否出现在智能体的动态上下文中。"""
    # 添加机密和说明
    conversation.update_secrets(
        {
            "GITHUB_TOKEN": StaticSecret(
                value=SecretStr("ghp_xxx"), description="GitHub authentication token"
            ),
            "OPENAI_API_KEY": StaticSecret(
                value=SecretStr("sk-xxx"), description="OpenAI API key for LLM calls"
            ),
        }
    )

    # 智能体在构建动态上下文时从状态中拉出机密
    agent = cast(Agent, conversation.agent)
    dynamic_context = agent.get_dynamic_context(conversation.state)

    # 验证机密出现在动态上下文中
    assert dynamic_context is not None
    assert "<CUSTOM_SECRETS>" in dynamic_context
    assert "GITHUB_TOKEN" in dynamic_context
    assert "GitHub authentication token" in dynamic_context
    assert "OPENAI_API_KEY" in dynamic_context
    assert "OpenAI API key for LLM calls" in dynamic_context
    assert "</CUSTOM_SECRETS>" in dynamic_context


def test_secrets_merges_with_existing_context(llm: LLM, tmp_path):
    """测试注册表机密与现有 agent_context 机密合并。"""
    # 使用现有的上下文和机密创建智能体
    existing_secrets = {
        "EXISTING_SECRET": StaticSecret(
            value=SecretStr("existing-value"), description="Pre-existing secret"
        ),
    }
    agent = Agent(
        llm=llm,
        tools=[],
        agent_context=AgentContext(
            secrets=existing_secrets,
            system_message_suffix="Custom instructions here",
        ),
    )
    conversation = LocalConversation(agent, workspace=str(tmp_path))

    # 通过 update_secrets 添加新的机密（转到注册表）
    conversation.update_secrets(
        {
            "NEW_SECRET": StaticSecret(
                value=SecretStr("new-value"), description="Newly added secret"
            ),
        }
    )

    # 智能体应合并 agent_context 和注册表中的机密
    dynamic_context = agent.get_dynamic_context(conversation.state)

    # 两个机密都应该出现在动态上下文中
    assert dynamic_context is not None
    assert "EXISTING_SECRET" in dynamic_context
    assert "Pre-existing secret" in dynamic_context
    assert "NEW_SECRET" in dynamic_context
    assert "Newly added secret" in dynamic_context

    # 验证现有的上下文属性是否已保留
    assert "Custom instructions here" in dynamic_context

    conversation.close()


def test_update_secrets_overrides_existing_secret(conversation: LocalConversation):
    """测试 update_secrets 是否使用相同的密钥覆盖现有的机密。"""
    # 添加首字母机密
    conversation.update_secrets(
        {
            "API_KEY": StaticSecret(
                value=SecretStr("old-key"), description="Old description"
            ),
        }
    )

    # 使用新值更新
    conversation.update_secrets(
        {
            "API_KEY": StaticSecret(
                value=SecretStr("new-key"), description="New description"
            ),
        }
    )

    # 验证机密已在动态上下文中更新
    agent = cast(Agent, conversation.agent)
    dynamic_context = agent.get_dynamic_context(conversation.state)
    assert dynamic_context is not None
    assert "New description" in dynamic_context


def test_secrets_via_constructor_appear_in_prompt(llm: LLM, tmp_path):
    """测试通过构造函数传递的机密是否出现在提示词中。"""
    agent = Agent(llm=llm, tools=[])
    secrets = {
        "CONSTRUCTOR_SECRET": StaticSecret(
            value=SecretStr("constructor-value"),
            description="Secret passed via constructor",
        ),
    }
    conversation = LocalConversation(agent, workspace=str(tmp_path), secrets=secrets)

    # 验证机密在注册表中
    secret_infos = conversation.state.secret_registry.get_secret_infos()
    secret_names = [s["name"] for s in secret_infos]
    assert "CONSTRUCTOR_SECRET" in secret_names

    # 验证机密出现在动态上下文中
    dynamic_context = agent.get_dynamic_context(conversation.state)
    assert dynamic_context is not None
    assert "CONSTRUCTOR_SECRET" in dynamic_context
    assert "Secret passed via constructor" in dynamic_context

    conversation.close()
