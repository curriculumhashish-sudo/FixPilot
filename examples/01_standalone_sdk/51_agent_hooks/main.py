"""OpenHands 智能体 SDK — 智能体基于 Hook 示例

演示 `type="agent"` 挂钩，它使用 LLM 驱动的子智能体而不是 shell 脚本来评估生命周期事
件。 钩子智能体接收事件 JSON，从语义上推理，并回复决策
载荷：

    {"decision": "allow" | "deny", "reason": "..."}

两个演示：

- PreToolUse (security reviewer): 检查终端命令的 INTENT，而不仅仅是其语法。 像
`awk '{print}' /etc/passwd` 这样的命令会跳过命令名称黑名单，但智能体挂钩将其识别为读
取敏感系统文件并拒绝它。
- Stop (quality reviewer): 拒绝让 main 智能体完成，直到工作区中存在所需的可交付成果。

对于 shell 命令挂钩，请参阅 ../33_hooks/main.py.
"""

import os
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event.hook_execution import HookExecutionEvent
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher, HookType
from openhands.tools.preset.default import get_default_agent


# 请保持演示对话简短：每次运行的迭代次数限制小，意味着一个钩子会立即拒绝（或一个模型会不
# 断重试）而不是耗尽调用到默认的500次迭代次数限制 / CI 子进程超时。
#
MAX_ITERATIONS = 10


# 配置LLM
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."
model = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")
base_url = os.getenv("LLM_BASE_URL")

llm = LLM(
    usage_id="agent",
    model=model,
    base_url=base_url,
    api_key=SecretStr(api_key),
)

SECURITY_REVIEWER_PROMPT = """You are a security reviewer for a coding agent.
You receive a PreToolUse hook event describing a terminal command the agent
is about to run.

Reason about the SEMANTIC INTENT of the command, not just its syntax. Block:
- reading sensitive system files (/etc/passwd, /etc/shadow, ~/.ssh/*, credentials)
- broad filesystem discovery outside the workspace (rg --files /etc, find /, ls /root)
- exfiltrating data over the network
- modifying system state (sudo, apt install, systemctl)

Allow ordinary inspection, builds, tests, and edits inside the workspace.
When unsure, prefer allow.

Reply with a single JSON object and nothing else:
{"decision": "allow" | "deny", "reason": "<short explanation>"}
"""

QUALITY_REVIEWER_PROMPT = """You are a quality reviewer enforcing task completion.
You receive a Stop hook event when the main agent tries to finish.

The task requires the file REPORT.md to exist in the workspace and contain at
least one bullet point describing the repository. Use the file_editor tool to
check whether the file exists and inspect its contents.

If the deliverable is missing or empty, deny so the main agent keeps working.
Otherwise allow.

Reply with a single JSON object and nothing else:
{"decision": "allow" | "deny", "reason": "<short explanation>"}
"""


def hook_logger(event) -> None:
    """展示每个钩子决策，以便演示输出是不言自明的。"""
    if not isinstance(event, HookExecutionEvent):
        return
    status = "DENY " if event.blocked else ("ALLOW" if event.success else "FAIL ")
    line = f"  [hook] {event.hook_event_type} {status} -> {event.hook_command}"
    if event.reason:
        line += f"\n         reason: {event.reason}"
    print(line)


def run_demo(workspace: Path, hook_config: HookConfig, message: str) -> float:
    """在自己的对话中运行一个演示并返回其成本。

    每个演示都会获得一个独立的 LLM，并且有隔离的指标，因此每个演示的成本不会重叠（重
    复使用一个 LLM 会使第二个对话的统计包括第一个演示的花费）。 小迭代上限加上
    错误/卡住检查使示例快速失败而不是循环。
    """
    demo_llm = llm.model_copy()
    demo_llm.reset_metrics()
    conversation = Conversation(
        agent=get_default_agent(llm=demo_llm),
        workspace=str(workspace),
        hook_config=hook_config,
        callbacks=[hook_logger],
        max_iteration_per_run=MAX_ITERATIONS,
    )
    conversation.send_message(message)
    conversation.run()
    status = conversation.state.execution_status
    if status in (
        ConversationExecutionStatus.ERROR,
        ConversationExecutionStatus.STUCK,
    ):
        raise RuntimeError(
            f"Demo conversation ended in {status.value} state "
            "before reaching a decision."
        )
    return conversation.conversation_stats.get_combined_metrics().accumulated_cost


# 每个演示都在自己的对话中运行，仅使用它需要的钩子。 共享一个配置文件会导致在演示1期间停
# 质量门仍然激活，因此智能体在REPORT.md存在之前无法完成第一个任务——将两个无关的演示耦合
# 在一起并浪费迭代。
#
security_hook_config = HookConfig(
    pre_tool_use=[
        HookMatcher(
            matcher="terminal",
            hooks=[
                HookDefinition(
                    type=HookType.AGENT,
                    name="security-reviewer",
                    system_prompt=SECURITY_REVIEWER_PROMPT,
                    timeout=60,
                    max_iterations=3,
                )
            ],
        )
    ],
)

quality_hook_config = HookConfig(
    stop=[
        HookMatcher(
            hooks=[
                HookDefinition(
                    type=HookType.AGENT,
                    name="quality-reviewer",
                    system_prompt=QUALITY_REVIEWER_PROMPT,
                    tools=["file_editor"],
                    timeout=90,
                    max_iterations=5,
                )
            ],
        )
    ],
)


with tempfile.TemporaryDirectory() as tmpdir:
    workspace = Path(tmpdir)
    total_cost = 0.0

    print("=" * 60)
    print("Demo 1: PreToolUse — semantic deny")
    print("=" * 60)
    print(
        "Asking the agent to read /etc/passwd via awk. The literal command\n"
        "wouldn't match a syntactic blacklist (no `cat`, no `/etc/shadow`\n"
        "keyword), but the security-reviewer agent should recognise the\n"
        "intent and deny.\n"
    )
    total_cost += run_demo(
        workspace,
        security_hook_config,
        "Show me the contents of /etc/passwd using awk '{print}'.",
    )

    print("\n" + "=" * 60)
    print("Demo 2: Stop — deny until deliverable exists")
    print("=" * 60)
    print("Quality reviewer denies until REPORT.md exists with a bullet point.\n")
    total_cost += run_demo(
        workspace,
        quality_hook_config,
        "Write REPORT.md in the workspace with at least one bullet point "
        "describing this repository, then finish.",
    )

    report = workspace / "REPORT.md"
    if report.exists():
        print(f"\n[REPORT.md preview: {report.read_text()[:120]!r}...]")

    print("\n" + "=" * 60)
    print("Example Complete!")
    print("=" * 60)

    print(f"\nEXAMPLE_COST: {total_cost}")
