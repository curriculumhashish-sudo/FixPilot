"""在 TerminalExecutor 中测试自动机密屏蔽。"""

import tempfile
from unittest.mock import Mock

from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.llm import LLM
from openhands.sdk.tool.schema import TextContent
from openhands.tools.terminal import TerminalAction, TerminalObservation
from openhands.tools.terminal.impl import TerminalExecutor


def test_terminal_executor_without_conversation():
    """测试TerminalExecutor在没有对话的情况下是否正常工作（无屏蔽）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 无需对话即可创建执行者
        executor = TerminalExecutor(working_dir=temp_dir)

        try:
            # 执行输出机密值的命令
            action = TerminalAction(command="echo 'The secret is: secret-value-123'")
            result = executor(action)

            # 检查输出是否未被屏蔽（未提供对话）
            assert "secret-value-123" in result.text
            assert "<secret-hidden>" not in result.text

        finally:
            executor.close()


def test_terminal_executor_with_conversation_secrets():
    """测试 TerminalExecutor 使用 conversation.state.secret_registry 中的机密。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 与机密创建对话
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        test_secrets = {
            "SECRET_TOKEN": "secret-value-123",
            "API_KEY": "another-secret-456",
        }

        conversation = Conversation(
            agent=agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            secrets=test_secrets,
        )

        # 强制子进程模式，以便我们有一个会话到模拟对象
        executor = TerminalExecutor(working_dir=temp_dir, terminal_type="subprocess")

        try:
            # 模拟对象避免子进程测试中出现问题的会话
            mock_session = Mock()
            # session.execute 返回 TerminalObservation
            mock_observation = TerminalObservation(
                command="echo 'Token: $SECRET_TOKEN, Key: $API_KEY'",
                exit_code=0,
                content=[
                    TextContent(text="Token: secret-value-123, Key: another-secret-456")
                ],
            )
            mock_session.execute.return_value = mock_observation
            mock_session._closed = False
            executor._session = mock_session

            # 通过对话执行命令 - 机密应导出并屏蔽
            action = TerminalAction(
                command="echo 'Token: $SECRET_TOKEN, Key: $API_KEY'"
            )
            result = executor(action, conversation=conversation)

            # 验证 session.execute 被调用
            assert mock_session.execute.called

            # 检查两个机密在输出中都被屏蔽
            assert "secret-value-123" not in result.text
            assert "another-secret-456" not in result.text
            # SecretsManager 使用 <secret-hidden> 作为掩码
            assert "<secret-hidden>" in result.text

        finally:
            executor.close()
            conversation.close()


def test_terminal_executor_masks_secret_not_referenced_by_command():
    """即使命令从未引用其名称，机密也会被屏蔽。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])

        token = "github_pat_REALSECRETVALUE123"
        conversation = Conversation(
            agent=agent,
            workspace=temp_dir,
            persistence_dir=temp_dir,
            secrets={"GITHUB_TOKEN": token},
        )

        executor = TerminalExecutor(working_dir=temp_dir, terminal_type="subprocess")

        try:
            command = "git remote -v"
            mock_session = Mock()
            mock_session.execute.return_value = TerminalObservation(
                command=command,
                exit_code=0,
                content=[
                    TextContent(
                        text=f"origin\thttps://{token}@github.com/repo/test.git (fetch)"
                    )
                ],
            )
            mock_session._closed = False
            executor._session = mock_session

            result = executor(
                TerminalAction(command=command), conversation=conversation
            )

            assert token not in result.text
            assert "<secret-hidden>" in result.text

        finally:
            executor.close()
            conversation.close()
