import os
import tempfile
import time
from pathlib import Path

from pydantic import SecretStr
from scripts.utils import ManagedAPIServer

from openhands.sdk import LLM, Conversation, RemoteConversation, Workspace, get_logger
from openhands.sdk.event import ConversationStateUpdateEvent, HookExecutionEvent
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)

# 本例的 Hook 脚本目录
HOOK_SCRIPTS_DIR = Path(__file__).parent / "hook_scripts"


api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)
title_gen_llm = LLM(
    usage_id="title-gen-llm",
    model=os.getenv("LLM_MODEL", "openhands/gpt-5-mini-2025-08-07"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)

# 使用托管 API 服务器
with ManagedAPIServer(port=8001) as server:
    # 创建智能体
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,  # 为了简单起见，禁用浏览器工具
    )

    # 定义回调以测试 WebSocket 功能
    received_events = []
    event_tracker = {"last_event_time": time.time()}

    def event_callback(event):
        """回调捕获事件以进行测试。"""
        event_type = type(event).__name__
        logger.info(f"🔔 Callback received event: {event_type}\n{event}")
        received_events.append(event)
        event_tracker["last_event_time"] = time.time()

    # 使用回调创建 RemoteConversation
    # 注意：RemoteConversation 需要工作区
    # 使用 CI 环境中存在且可访问的临时目录
    temp_workspace_dir = tempfile.mkdtemp(prefix="agent_server_demo_")
    workspace = Workspace(host=server.base_url, working_dir=temp_workspace_dir)
    result = workspace.execute_command("pwd")
    logger.info(
        f"Command '{result.command}' completed with exit code {result.exit_code}"
    )
    logger.info(f"Output: {result.stdout}")

    # 配置钩子 - 使用 RemoteConversation 演示钩子系统服务器端钩子（PreToolUse、
    # PostToolUse、UserPromptSubmit、Stop）由 Agent Server 执行。 客户端挂钩（
    # SessionStart、SessionEnd）在本地执行。
    #

    hook_config = HookConfig(
        # 停止钩子 - 在允许智能体完成之前运行 Python 语法检查。 如果任何 Python 文件有语
        # 法错误，钩子返回 "deny" 并输出错误信息，该信息被发送回智能体作为反馈，而智能体
        # 继续努力解决问题。
        #
        stop=[
            HookMatcher(
                matcher="*",  # 匹配所有停止原因
                hooks=[
                    HookDefinition(
                        command=str(HOOK_SCRIPTS_DIR / "pycompile_check.sh"),
                        timeout=60,
                    )
                ],
            )
        ],
    )

    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[event_callback],
        hook_config=hook_config,
    )
    assert isinstance(conversation, RemoteConversation)

    # 跟踪钩子执行事件
    hook_events: list[HookExecutionEvent] = []

    def hook_event_tracker(event):
        """用于跟踪钩子执行事件的附加回调。"""
        if isinstance(event, HookExecutionEvent):
            hook_events.append(event)
            logger.info(f"🪝 HookExecutionEvent captured: {event.hook_event_type}")

    # 将我们的钩子跟踪器附加到现有的回调
    conversation._callbacks.append(hook_event_tracker)

    try:
        logger.info(f"\n📋 Conversation ID: {conversation.state.id}")

        # 测试场景：要求智能体创建一个有语法错误的Python文件。停止钩子应该检测到语法错误
        # ，并将反馈发送回智能体以进行修复
        #
        logger.info("📝 Sending message to test on_stop hook with syntax check...")
        conversation.send_message(
            "Create a Python file called 'test_broken.py' in the current directory "
            "with an obvious syntax error (like 'def broken(:\n    pass' - missing "
            "closing parenthesis). After creating the file, immediately use the "
            "finish action. If you receive any feedback about errors, fix them and "
            "try to finish again."
        )

        # 使用特定的 LLM 生成标题
        title = conversation.generate_title(max_length=60, llm=title_gen_llm)
        logger.info(f"Generated conversation title: {title}")

        logger.info("🚀 Running conversation...")
        logger.info(
            "Expected behavior: Agent creates broken .py file -> tries to finish "
            "-> stop hook runs syntax check -> check fails -> hook sends feedback "
            "-> agent fixes the syntax error -> tries to finish again -> passes"
        )

        # 继续运行直到智能体实际上，当一个停止钩子拒绝时，状态会变为：运行 -> 完成 -> 运
        # 行。客户端的 run() 它可能会在看到 'finished' 时返回，所以我们需要检查是否智能
        # 体仍然运行并继续
        #
        max_runs = 10  # 允许足够的重试供智能体解决问题
        run_count = 0
        while run_count < max_runs:
            run_count += 1
            logger.info(f"🔄 Run attempt #{run_count}")
            conversation.run()
            current_status = conversation.state.execution_status
            logger.info(f"   After run(), status = {current_status}")

            # 让任何挂起的状态更新到达的小延迟
            time.sleep(0.5)
            current_status = conversation.state.execution_status
            logger.info(f"   After delay, status = {current_status}")

            if current_status.value == "finished":
                logger.info("   ✅ Agent finished!")
                break
            elif current_status.value == "running":
                logger.info("   Agent still running (hook denied stop), continuing...")
            else:
                logger.info(f"   Unexpected status: {current_status}, stopping")
                break

        logger.info("✅ Task completed!")
        logger.info(f"Final agent status: {conversation.state.execution_status}")

        # 等待事件停止发生（2 秒内没有事件）
        logger.info("⏳ Waiting for events to stop...")
        while time.time() - event_tracker["last_event_time"] < 2.0:
            time.sleep(0.1)
        logger.info("✅ Events have stopped")

        # 分析钩子执行事件
        logger.info("\n" + "=" * 50)
        logger.info("📊 Hook Execution Events Analysis")
        logger.info("=" * 50)

        logger.info(f"Total HookExecutionEvents received: {len(hook_events)}")
        for i, he in enumerate(hook_events, 1):
            logger.info(f"\n  Hook Event #{i}:")
            logger.info(f"    Type: {he.hook_event_type}")
            logger.info(f"    Command: {he.hook_command}")
            logger.info(f"    Success: {he.success}")
            logger.info(f"    Blocked: {he.blocked}")
            logger.info(f"    Exit Code: {he.exit_code}")
            if he.additional_context:
                # 为了可读性而截断
                ctx = (
                    he.additional_context[:500] + "..."
                    if len(he.additional_context) > 500
                    else he.additional_context
                )
                logger.info(f"    Additional Context: {ctx}")
            if he.error:
                logger.info(f"    Error: {he.error}")

        # 计数被拒绝的停止挂钩（预提交失败）
        stop_events = [e for e in hook_events if e.hook_event_type == "Stop"]
        denied_stops = [e for e in stop_events if e.blocked]

        logger.info(f"\nStop hook events: {len(stop_events)}")
        logger.info(f"Denied stops (pre-commit failures): {len(denied_stops)}")

        if denied_stops:
            logger.info(
                "\n✅ SUCCESS: Stop hook denied at least once due to "
                "pre-commit failure!"
            )
            logger.info(
                "   The agent should have received feedback and fixed the issue."
            )
        else:
            logger.info(
                "\n⚠️  No denied stops detected. Either pre-commit passed on first "
                "try or the hook didn't work as expected."
            )

        # 演示 state.events 功能
        logger.info("\n" + "=" * 50)
        logger.info("📊 Demonstrating State Events API")
        logger.info("=" * 50)

        # 使用 state.events 计算事件总数
        total_events = len(conversation.state.events)
        logger.info(f"📈 Total events in conversation: {total_events}")

        # 使用 state.events 获取最近的事件（最后 10 个）
        logger.info("\n🔍 Getting last 10 events using state.events...")
        all_events = conversation.state.events
        recent_events = all_events[-10:] if len(all_events) >= 10 else all_events

        for i, event in enumerate(recent_events, 1):
            event_type = type(event).__name__
            timestamp = getattr(event, "timestamp", "Unknown")
            logger.info(f"  {i}. {event_type} at {timestamp}")

        # 让我们看看实际的事件类型是什么
        logger.info("\n🔍 Event types found in recent events:")
        event_types = set()
        for event in recent_events:
            event_type = type(event).__name__
            event_types.add(event_type)
        for event_type in sorted(event_types):
            logger.info(f"  - {event_type}")

        # 打印全部 ConversationStateUpdateEvent
        logger.info("\n🗂️  ConversationStateUpdateEvent events:")
        for event in conversation.state.events:
            if isinstance(event, ConversationStateUpdateEvent):
                logger.info(f"  - {event}")

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")

    finally:
        # 清理
        print("\n🧹 Cleaning up conversation...")
        conversation.close()
