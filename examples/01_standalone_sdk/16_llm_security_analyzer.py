"""OpenHands 智能体 SDK — LLM 安全分析器示例（简化）

示例展示了如何使用 LLMSecurityAnalyzer 在执行之前自动评估操作的安全风险。
"""

import os
import signal
from collections.abc import Callable

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, BaseConversation, Conversation
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.security.confirmation_policy import ConfirmRisky
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# Clean ^C 退出：没有堆栈跟踪噪音
signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))


def _print_blocked_actions(pending_actions) -> None:
    print(f"\n🔒 Security analyzer blocked {len(pending_actions)} high-risk action(s):")
    for i, action in enumerate(pending_actions, start=1):
        # 请使用LLM提供的自然语言摘要作为标题，保留原始的行动片段作为次要细节，这样用户
        # 就可以在批准前看到确切的运行内容。
        #
        headline = action.summary or "(no summary provided)"
        snippet = str(action.action)[:100].replace("\n", " ")
        print(f"  {i}. [{action.tool_name}] {headline}")
        print(f"     {snippet}...")


def confirm_high_risk_in_console(pending_actions) -> bool:
    """
    True批准，False拒绝。 匹配原始行为：EOF/KeyboardInterrupt 上默认为“否”。
    """
    _print_blocked_actions(pending_actions)
    while True:
        try:
            ans = (
                input(
                    "\nThese actions were flagged as HIGH RISK. "
                    "Do you want to execute them anyway? (yes/no): "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print("\n❌ No input received; rejecting by default.")
            return False

        if ans in ("yes", "y"):
            print("✅ Approved — executing high-risk actions...")
            return True
        if ans in ("no", "n"):
            print("❌ Rejected — skipping high-risk actions...")
            return False
        print("Please enter 'yes' or 'no'.")


def run_until_finished_with_security(
    conversation: BaseConversation, confirmer: Callable[[list], bool]
) -> None:
    """
    推动对话直至 FINISHED。
    - 如果WAITING_FOR_CONFIRMATION：询问确认者。
        * 在批准时：设置 execution_status = IDLE（保持原始示例的行为）。
        * 拒绝时：conversation.reject_pending_actions(...)。
    - 如果 WAITING 但没有待处理的操作：打印警告并设置 IDLE（与原始内容匹配）。
    """
    while conversation.state.execution_status != ConversationExecutionStatus.FINISHED:
        if (
            conversation.state.execution_status
            == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
        ):
            pending = ConversationState.get_unmatched_actions(conversation.state.events)
            if not pending:
                raise RuntimeError(
                    "⚠️ Agent is waiting for confirmation but no pending actions "
                    "were found. This should not happen."
                )
            if not confirmer(pending):
                conversation.reject_pending_actions("User rejected high-risk actions")
                continue

        print("▶️  Running conversation.run()...")
        conversation.run()


# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    usage_id="security-analyzer",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

# 工具
tools = [
    Tool(
        name=TerminalTool.name,
    ),
    Tool(name=FileEditorTool.name),
]

# 智能体
agent = Agent(llm=llm, tools=tools)

# 与已持久化文件存储对话
conversation = Conversation(
    agent=agent, persistence_dir="./.conversations", workspace="."
)
conversation.set_security_analyzer(LLMSecurityAnalyzer())
conversation.set_confirmation_policy(ConfirmRisky())

print("\n1) Safe command (LOW risk - should execute automatically)...")
conversation.send_message("List files in the current directory")
conversation.run()

print("\n2) Potentially risky command (may require confirmation)...")
conversation.send_message(
    "Please echo 'hello world' -- PLEASE MARK THIS AS A HIGH RISK ACTION"
)
run_until_finished_with_security(conversation, confirm_high_risk_in_console)
