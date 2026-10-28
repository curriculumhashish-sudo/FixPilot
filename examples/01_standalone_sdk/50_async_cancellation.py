"""
异步中断演示 — 在 LLM 推理 * 或 * 工具执行期间取消。

该任务旨在提供两个可以触发 ``interrupt()`` 的窗口：

1. **在LLM完成期间**——模型必须推理如何编写脚本然后运行它，这需要几秒钟的生成时间。
2. **在长时间运行的终端命令期间** - 智能体运行一个休眠 30 秒的 shell 脚本，从而有足够
的时间来中断
   while a tool call is in-flight.

随时按 **Ctrl-C**，或让自动计时器在可配置的延迟（默认 8 秒）后触发。 对话转到
``PAUSED``，稍后可以使用另一个 ``arun()`` / ``run()`` 恢复。

用途：
    LLM_API_KEY=... python examples/01_standalone_sdk/50_async_cancellation.py

    # 覆盖自动中断延迟：
    AUTO_CANCEL_SECONDS=12 LLM_API_KEY=... python examples/...
"""

import asyncio
import os
import signal
import time

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, Conversation, Event
from openhands.sdk.event import ActionEvent, ObservationEvent
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# ── 配置────────────────────────────────────────────────────
api_key = os.getenv("LLM_API_KEY")
assert api_key, "Set LLM_API_KEY in your environment."

model = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")
base_url = os.getenv("LLM_BASE_URL")

llm = LLM(
    model=model,
    api_key=SecretStr(api_key),
    base_url=base_url,
    usage_id="async-cancel-demo",
)

# ── 智能体与对话──────────────────────────────────────────────
agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
)

# ── 现场事件日志──────────────────────────────────────────────────────
phase = "llm"  # 跟踪我们处于状态行的哪个阶段


def on_event(event: Event) -> None:
    """为每个事件打印一行行内容，以便用户可以看到进度。"""
    global phase
    if isinstance(event, ActionEvent):
        phase = "tool"
        print(f"  🔧 Agent calls: {event.tool_name}")
    elif isinstance(event, ObservationEvent):
        text = str(event.observation)[:120] if event.observation else ""
        print(f"  📋 Result: {text}")


conversation = Conversation(
    agent=agent,
    workspace=os.getcwd(),
    callbacks=[on_event],
)

# 要求智能体做一些自然会产生 TWO 阻塞的事情
# 阶段：首先是长LLM完成（推理+生成），然后
# 长时间运行的终端命令（sleep 30）。
conversation.send_message(
    "Please do the following:\n"
    "1. Write a bash script called countdown.sh that prints the numbers "
    "30 down to 1, sleeping 1 second between each number.\n"
    "2. Run the script with `bash countdown.sh` and wait for it to finish.\n"
    "3. After the script completes, create a file called done.txt with "
    "the text 'Countdown complete!'."
)


# ── 中断机械────────────────────────────────────────────
AUTO_CANCEL_SECONDS = float(os.getenv("AUTO_CANCEL_SECONDS", "8"))


def _request_interrupt(source: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"⚡ Interrupt requested ({source})")
    print(f"   Current phase: {phase}")
    print(f"{'=' * 60}\n")
    conversation.interrupt()


async def _auto_interrupt_timer() -> None:
    await asyncio.sleep(AUTO_CANCEL_SECONDS)
    _request_interrupt(f"auto-timer after {AUTO_CANCEL_SECONDS}s")


async def main() -> None:
    loop = asyncio.get_running_loop()

    # 连接 Ctrl-C 来中断而不是终止进程。
    try:
        loop.add_signal_handler(
            signal.SIGINT,
            lambda: _request_interrupt("Ctrl-C"),
        )
    except NotImplementedError:
        pass  # Windows — KeyboardInterrupt 仍然有效

    print("=" * 60)
    print("Async Interrupt Demo")
    print("=" * 60)
    print(f"Model          : {model}")
    print(f"Auto-interrupt : {AUTO_CANCEL_SECONDS}s  (or press Ctrl-C)")
    print()
    print("The agent will first reason + generate code (window 1),")
    print("then run a 30-second countdown script (window 2).")
    print("Interrupt at any time to cancel instantly.")
    print("=" * 60)
    print()

    # ── 用中断定时器运行──────────────────────────────────────
    timer_task = asyncio.create_task(_auto_interrupt_timer())
    wall_start = time.monotonic()

    await conversation.arun()

    timer_task.cancel()
    elapsed = time.monotonic() - wall_start

    # ── 概要──────────────────────────────────────────────────────
    status = conversation.state.execution_status
    print()
    print("─" * 60)
    print(f"Status    : {status}")
    print(f"Wall time : {elapsed:.1f}s")
    print(f"Phase     : interrupted during {phase}")
    print()
    if str(status) == "paused":
        print("The conversation is paused — you could resume it with")
        print("another arun() or run() call to let the agent continue.")
    print("─" * 60)

    cost = llm.metrics.accumulated_cost
    print(f"\nEXAMPLE_COST: {cost}")


asyncio.run(main())
