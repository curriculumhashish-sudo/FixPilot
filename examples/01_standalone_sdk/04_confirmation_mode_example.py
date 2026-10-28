"""OpenHands 智能体 SDK — 确认模式示例"""

import os
import signal
from collections.abc import Callable

from pydantic import SecretStr

from openhands.sdk import LLM, BaseConversation, Conversation
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.security.confirmation_policy import AlwaysConfirm, NeverConfirm
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.tools.preset.default import get_default_agent


# 使 ^C 成为干净的退出而不是堆栈跟踪
signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))


def _print_action_preview(pending_actions) -> None:
    print(f"\n🔍 Agent created {len(pending_actions)} action(s) awaiting confirmation:")
    for i, action in enumerate(pending_actions, start=1):
        # 请使用LLM提供的自然语言摘要作为标题，保留原始的行动片段作为次要细节，这样用户
        # 就可以在批准前看到确切的运行内容。
        #
        headline = action.summary or "(no summary provided)"
        snippet = str(action.action)[:100].replace("\n", " ")
        print(f"  {i}. [{action.tool_name}] {headline}")
        print(f"     {snippet}...")


def confirm_in_console(pending_actions) -> bool:
    """
    True批准，False拒绝。 EOF/KeyboardInterrupt 上默认为“否”（与原始行为匹配）。
    """
    _print_action_preview(pending_actions)
    while True:
        try:
            ans = (
                input("\nDo you want to execute these actions? (yes/no): ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print("\n❌ No input received; rejecting by default.")
            return False

        if ans in ("yes", "y"):
            print("✅ Approved — executing actions…")
            return True
        if ans in ("no", "n"):
            print("❌ Rejected — skipping actions…")
            return False
        print("Please enter 'yes' or 'no'.")


def run_until_finished(conversation: BaseConversation, confirmer: Callable) -> None:
    """
    推动对话直至 FINISHED。 如果是WAITING_FOR_CONFIRMATION，询问确认人； 拒绝时，调用
     reject_pending_actions(
    )。 如果智能体等待但不存在任何操作，则保留原始错误。
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
                conversation.reject_pending_actions("User rejected the actions")
                # 让智能体产生一个新的步骤或完成
                continue

        print("▶️  Running conversation.run()…")
        conversation.run()


# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "gpt-5.5")
base_url = os.getenv("LLM_BASE_URL")
llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

agent = get_default_agent(llm=llm)
conversation = Conversation(agent=agent, workspace=os.getcwd())

# 根据环境变量有条件添加安全分析器
add_security_analyzer = bool(os.getenv("ADD_SECURITY_ANALYZER", "").strip())
if add_security_analyzer:
    print("Agent security analyzer added.")
    conversation.set_security_analyzer(LLMSecurityAnalyzer())

# 1) 确认模式 ON
conversation.set_confirmation_policy(AlwaysConfirm())
print("\n1) Command that will likely create actions…")
conversation.send_message("Please list the files in the current directory using ls -la")
run_until_finished(conversation, confirm_in_console)

# 2) 用户可以选择拒绝的命令
print("\n2) Command the user may choose to reject…")
conversation.send_message("Please create a file called 'dangerous_file.txt'")
run_until_finished(conversation, confirm_in_console)

# 3) 简单的问候（无需采取任何行动）
print("\n3) Simple greeting (no actions expected)…")
conversation.send_message("Just say hello to me")
run_until_finished(conversation, confirm_in_console)

# 4) 禁用确认模式并直接运行命令
print("\n4) Disable confirmation mode and run a command…")
conversation.set_confirmation_policy(NeverConfirm())
conversation.send_message("Please echo 'Hello from confirmation mode example!'")
conversation.run()

conversation.send_message(
    "Please delete any file that was created during this conversation."
)
conversation.run()

print("\n=== Example Complete ===")
print("Key points:")
print(
    "- conversation.run() creates actions; confirmation mode "
    "sets execution_status=WAITING_FOR_CONFIRMATION"
)
print("- User confirmation is handled via a single reusable function")
print("- Rejection uses conversation.reject_pending_actions() and the loop continues")
print("- Simple responses work normally without actions")
print("- Confirmation policy is toggled with conversation.set_confirmation_policy()")
