"""OpenHands 智能体 SDK — 钩子示例

演示 OpenHands 挂钩系统。 Hook 是在关键生命周期事件中运行的 shell 脚本：

- PreToolUse: 在执行前阻止危险命令
- PostToolUse: 执行后工具使用情况
- UserPromptSubmit: 将上下文插入用户消息中
- Stop: 执行任务完成标准

挂钩脚本位于该文件旁边的 script/ 目录中。
"""

import os
import signal
import tempfile
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Conversation
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.tools.preset.default import get_default_agent


signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

SCRIPT_DIR = Path(__file__).parent / "hook_scripts"

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

# 使用 git repo 创建临时工作区
with tempfile.TemporaryDirectory() as tmpdir:
    workspace = Path(tmpdir)
    os.system(f"cd {workspace} && git init -q && echo 'test' > file.txt")

    log_file = workspace / "tool_usage.log"
    summary_file = workspace / "summary.txt"

    # 使用类型化方法配置挂钩（推荐）这提供了更好的类型安全性和 IDE 支持
    #
    hook_config = HookConfig(
        pre_tool_use=[
            HookMatcher(
                matcher="terminal",
                hooks=[
                    HookDefinition(
                        command=str(SCRIPT_DIR / "block_dangerous.sh"),
                        timeout=10,
                    )
                ],
            )
        ],
        post_tool_use=[
            HookMatcher(
                matcher="*",
                hooks=[
                    HookDefinition(
                        command=(f"LOG_FILE={log_file} {SCRIPT_DIR / 'log_tools.sh'}"),
                        timeout=5,
                    )
                ],
            )
        ],
        user_prompt_submit=[
            HookMatcher(
                hooks=[
                    HookDefinition(
                        command=str(SCRIPT_DIR / "inject_git_context.sh"),
                    )
                ],
            )
        ],
        stop=[
            HookMatcher(
                hooks=[
                    HookDefinition(
                        command=(
                            f"SUMMARY_FILE={summary_file} "
                            f"{SCRIPT_DIR / 'require_summary.sh'}"
                        ),
                    )
                ],
            )
        ],
    )

    # 替代方案：您还可以使用 .from_dict() 从 JSON 配置文件加载
    # 单钩子匹配器的示例：
    # hook_config = HookConfig.from_dict({
    #     “钩子”：{
    #         "PreToolUse": [{
    #             “匹配器”：“终端”，“挂钩”：[ {“命令”：“路径/到/script.sh”，“超时”：10}]
    #
    #         }]
    #     }
    # })

    agent = get_default_agent(llm=llm)
    conversation = Conversation(
        agent=agent,
        workspace=str(workspace),
        hook_config=hook_config,
    )

    # 演示 1：安全命令（PostToolUse 记录它）
    print("=" * 60)
    print("Demo 1: Safe command - logged by PostToolUse")
    print("=" * 60)
    conversation.send_message("Run: echo 'Hello from hooks!'")
    conversation.run()

    if log_file.exists():
        print(f"\n[Log: {log_file.read_text().strip()}]")

    # 演示 2：危险命令（PreToolUse 阻止它）
    print("\n" + "=" * 60)
    print("Demo 2: Dangerous command - blocked by PreToolUse")
    print("=" * 60)
    conversation.send_message("Run: rm -rf /tmp/test")
    conversation.run()

    # 演示3：上下文注入+停止钩子执行
    print("\n" + "=" * 60)
    print("Demo 3: Context injection + Stop hook")
    print("=" * 60)
    print("UserPromptSubmit injects git status; Stop requires summary.txt\n")
    conversation.send_message(
        "Check what files have changes, then create summary.txt describing the repo."
    )
    conversation.run()

    if summary_file.exists():
        print(f"\n[summary.txt: {summary_file.read_text()[:80]}...]")

    print("\n" + "=" * 60)
    print("Example Complete!")
    print("=" * 60)

    cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
    print(f"\nEXAMPLE_COST: {cost}")
