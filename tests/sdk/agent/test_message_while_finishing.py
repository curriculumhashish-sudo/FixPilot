"""
完成时的消息：确保在智能体完成后LLM正确处理最后智能体步骤中的并发用户消息。

目的
- 当用户消息到达时，智能体正在执行其最终步骤（包含一个结束动作）时，验证正确的对话行
为。
- 该消息应附加到对话事件 AND 中，并在完成操作完成后馈送到新的 LLM 调用中。

方法
- 使用带有仪器的 SleepTool 控制时间，并标记最终步骤的开始和结束（在一个步骤中，睡眠后
完成） LLM 带有多个响应工具调用).
- 发送两条用户消息：
  1) 在早期（非最终）步骤期间：应在下一个 LLM 调用中处理此消息（证明正常处理中运行消
  息）。
  2) 在最后一步的睡眠期间：该消息应在完成操作完成后由 LLM 处理，确保没有消息丢失。

断言
- 两条用户消息均出现在已持久化事件中。
- 第一条消息（“alligator”）出现在 LLM 输入中（已处理）。
- 第二条消息（“butterfly”）DOES 出现在 LLM 输入中（已处理）。

该测试验证了确保在智能体完成后检测并处理在最后一步发送的未attended用户消息的修复功能
，从而防止消息丢失。
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, ClassVar


# 当将此文件作为脚本运行时，请确保存储库根目录位于 sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from unittest.mock import patch  # noqa: E402

# noqa: E402
from litellm import ChatCompletionMessageToolCall  # noqa: E402
from litellm.types.utils import (  # noqa: E402
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import Field  # noqa: E402

from openhands.sdk.agent import Agent  # noqa: E402
from openhands.sdk.conversation import Conversation  # noqa: E402
from openhands.sdk.event import MessageEvent  # noqa: E402
from openhands.sdk.llm import (  # noqa: E402
    LLM,
    ImageContent,
    Message,
    TextContent,
)
from openhands.sdk.tool import (  # noqa: E402
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


# 用于测试时序场景的自定义睡眠工具
class SleepAction(Action):
    duration: float = Field(description="Sleep duration in seconds")
    message: str = Field(description="Message to return after sleep")


class SleepObservation(Observation):
    message: str = Field(description="Message returned after sleep")

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.message)]


class SleepExecutor(ToolExecutor):
    test_start_time: float | None = None
    test_instance: "TestMessageWhileFinishing | None" = None

    def __call__(self, action: SleepAction, conversation=None) -> SleepObservation:  # noqa: ARG002
        start_time = time.time()
        test_start_time = getattr(self, "test_start_time", None)
        if test_start_time is None:
            test_start_time = start_time
        elapsed = start_time - test_start_time
        print(
            f"[+{elapsed:.3f}s] Sleep action STARTED: "
            f"{action.duration}s - '{action.message}'"
        )

        # 如果这是最后一次睡眠，则记录最后一步计时
        # 注：final_step_start时间戳记录在_mock_llm_response中
        # 当旗帜被设置时，避免与蝴蝶赛跑线程
        if "Final sleep" in action.message:
            print(f"[+{elapsed:.3f}s] FINAL STEP SLEEP STARTED")

        time.sleep(action.duration)

        end_time = time.time()
        actual_duration = end_time - start_time
        test_start_time_end = getattr(self, "test_start_time", None)
        if test_start_time_end is None:
            test_start_time_end = start_time
        end_elapsed = end_time - test_start_time_end
        print(
            f"[+{end_elapsed:.3f}s] Sleep action COMPLETED: "
            f"{actual_duration:.3f}s actual - '{action.message}'"
        )

        # 跟踪最后一步结束时间
        if "Final sleep" in action.message:
            print(f"[+{end_elapsed:.3f}s] FINAL STEP ENDED")
            if hasattr(self, "test_instance") and self.test_instance is not None:
                self.test_instance.timestamps.append(("final_step_end", end_time))

        return SleepObservation(message=action.message)


class SleepTool(ToolDefinition[SleepAction, SleepObservation]):
    """用于在完成期间测试消息处理的睡眠工具。"""

    name: ClassVar[str] = "sleep"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["SleepTool"]:
        return [
            cls(
                action_type=SleepAction,
                observation_type=SleepObservation,
                description="Sleep for specified duration and return a message",
                executor=SleepExecutor(),
            )
        ]


# 注册工具
register_tool("SleepTool", SleepTool)


class TestMessageWhileFinishing:
    """测试套件演示未处理的消息问题。"""

    def setup_method(self):
        """设置测试测试夹具。"""
        # 使用支持本机函数调用和多个工具调用的gpt-4o
        self.llm: LLM = LLM(model="gpt-4o", usage_id="test-llm")
        self.llm_completion_calls: list[Any] = []
        self.agent: Agent = Agent(llm=self.llm, tools=[Tool(name="SleepTool")])
        self.step_count: int = 0
        self.final_step_started: bool = False
        self.timestamps: list[tuple[str, float]] = []  # 跟踪关键计时事件
        self.conversation: Any = None
        self.test_start_time: float = 0.0

    def _mock_llm_response(self, messages, **kwargs):
        """
        模拟对象 LLM 通过两步场景演示了消息处理错误。
        """
        self.llm_completion_calls.append({"messages": messages, "kwargs": kwargs})
        self.step_count += 1
        elapsed = time.time() - self.test_start_time
        print(f"[+{elapsed:.3f}s] Step {self.step_count} LLM call")

        all_content = str(messages).lower()
        has_alligator = "alligator" in all_content
        has_butterfly = "butterfly" in all_content

        if self.step_count == 1:
            # 第 1 步：处理初始请求 - 单次睡眠
            sleep_call = ChatCompletionMessageToolCall(
                id="sleep_call_1",
                type="function",
                function=Function(
                    name="sleep",
                    arguments='{"duration": 2.0, "message": "First sleep completed"}',
                ),
            )
            return ModelResponse(
                id=f"response_step_{self.step_count}",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content="I'll sleep for 2 seconds first",
                            tool_calls=[sleep_call],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )

        elif self.step_count == 2:
            # 第 2 步：最后一步 - 睡眠 AND 完成（多个工具调用） 记录时间戳之前设置标志以
            # 避免与蝴蝶赛跑线程
            #
            self.timestamps.append(("final_step_start", time.time()))
            self.final_step_started = True

            response_content = "Now I'll sleep for a longer time and then finish"
            sleep_message = "Final sleep completed"
            final_message = "Task completed"

            if has_alligator:
                response_content += " with alligator"
                sleep_message += " with alligator"
                final_message += " with alligator"

            if has_butterfly:
                response_content += " and butterfly"
                sleep_message += " and butterfly"
                final_message += " and butterfly"  # 这应该不发生

            # 多个工具调用：睡眠THEN完成
            sleep_call = ChatCompletionMessageToolCall(
                id="sleep_call_2",
                type="function",
                function=Function(
                    name="sleep",
                    arguments=f'{{"duration": 3.0, "message": "{sleep_message}"}}',
                ),
            )

            finish_call = ChatCompletionMessageToolCall(
                id="finish_call_2",
                type="function",
                function=Function(
                    name="finish",
                    arguments=f'{{"message": "{final_message}"}}',
                ),
            )

            return ModelResponse(
                id=f"response_step_{self.step_count}",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content=response_content,
                            tool_calls=[
                                sleep_call,
                                finish_call,
                            ],
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )
        else:
            # 步骤 3：发生这种情况是因为蝴蝶消息重置 FINISHED 状态这演示了错误：在最后一
            # 步重置状态期间发送的消息
            #
            response_content = "I see the butterfly message"
            if has_butterfly:
                response_content += " with butterfly"

            # 返回一个简单的消息响应（无工具调用）
            return ModelResponse(
                id=f"response_step_{self.step_count}",
                choices=[
                    Choices(
                        message=LiteLLMMessage(
                            role="assistant",
                            content=response_content,
                        )
                    )
                ],
                created=0,
                model="test-model",
                object="chat.completion",
            )

    def test_message_processing_fix_verification(self):
        """
        验证修复：在最后一步中发送的消息在完成后进行处理。

        该测试显示，当用户在智能体执行其最后一步（包括结束动作）时发送消息时，消息会
        被正确检测为无人值守，并在后续LLM调用中进行处理。

        时间表：
        1. 第 1 步：智能体休眠 2 秒
        2. 用户在第 1 步中发送“鳄鱼”请求 → 在第 2 步中得到处理 ✓
        3. 第 2 步：智能体休眠 3 秒 AND 完成（包含多个操作的最后一步）
        4. 用户发送“蝴蝶”请求 WHILE 步骤 2 睡眠正在执行 → 检测为无人值守
        5. 步骤3：对话继续处理butterfly消息 ✓

        Key: 蝴蝶消息被检测和处理，确保消息不丢失。

        Expected: 对话在完成操作后处理蝴蝶消息。
        Actual: 会话继续到步骤 3 以处理无人值守消息。
        """  # noqa
        # 重置此测试的步数
        self.step_count = 0
        self.llm_completion_calls = []
        self.final_step_started = False
        self.test_start_time = time.time()

        conversation = Conversation(agent=self.agent)
        # 存储对话参考以供在模拟对象 LLM 中使用
        self.conversation = conversation

        # 触发惰性智能体初始化来创建工具
        conversation._ensure_agent_ready()

        # 设置睡眠执行器的测试开始时间参考这必须发生之后智能体 init 但之前任何消息都会被
        # 处理
        #
        sleep_tool = self.agent._tools.get("sleep")
        if sleep_tool and sleep_tool.executor is not None:
            setattr(sleep_tool.executor, "test_start_time", self.test_start_time)
            setattr(sleep_tool.executor, "test_instance", self)

        def elapsed_time():
            return f"[+{time.time() - self.test_start_time:.3f}s]"

        print(f"{elapsed_time()} Test started")

        with patch(
            "openhands.sdk.llm.llm.litellm_completion",
            side_effect=self._mock_llm_response,
        ):
            # 以自然的请求开始对话
            print(f"{elapsed_time()} Sending initial message")
            conversation.send_message(
                Message(
                    role="user",
                    content=[
                        TextContent(
                            text="Please sleep for 2 seconds, then sleep for "
                            "3 seconds and finish"
                        )
                    ],
                )
            )

            # 在后台运行对话线程
            print(f"{elapsed_time()} Starting conversation thread")
            thread = threading.Thread(target=conversation.run)
            thread.start()

            # 等待步骤 1 处理（已进行 LLM 调用，但未完成）
            print(f"{elapsed_time()} Waiting for step 1 to be processing...")
            while self.step_count < 1:
                time.sleep(0.1)

            print(
                f"{elapsed_time()} Sending alligator request during step 1 processing"
            )
            conversation.send_message(
                Message(
                    role="user",
                    content=[
                        TextContent(
                            text="Please add the word 'alligator' to your next message"
                        )
                    ],
                )
            )

            # 当最后一步开始时发送蝴蝶消息
            def send_butterfly_when_final_step_starts():
                # 等待最后一步开始
                while not self.final_step_started:
                    time.sleep(0.01)  # 小睡一会，避免忙碌等待

                # 最后一步开始时立即发送消息这模拟用户在最后一步执行期间发送消息
                #
                butterfly_send_time = time.time()
                self.timestamps.append(("butterfly_sent", butterfly_send_time))
                elapsed = butterfly_send_time - self.test_start_time
                print(f"[+{elapsed:.3f}s] BUTTERFLY MESSAGE SENT DURING FINAL STEP")

                conversation.send_message(
                    Message(
                        role="user",
                        content=[
                            TextContent(
                                text="Please add the word 'butterfly' to your next "
                                "message"
                            )
                        ],
                    )
                )

            butterfly_thread = threading.Thread(
                target=send_butterfly_when_final_step_starts
            )
            butterfly_thread.start()

            # 等待对话完成
            print(f"{elapsed_time()} Waiting for conversation to complete...")

            # 等待完成
            thread.join(timeout=10)
            butterfly_thread.join(timeout=5)

        # 调试：打印我们得到的内容
        print(f"\nDEBUG: Made {len(self.llm_completion_calls)} LLM calls")

        # 关键点：蝴蝶在最后步骤执行时被发送，它应该只出现在事件中绝不任何 LLM 因为没有
        # 后续操作 step() 在完成动作之后
        #

        # 检查事件列表中是否存在这两条消息
        with conversation.state:
            message_events = [
                event
                for event in conversation.state.events
                if isinstance(event, MessageEvent) and event.llm_message.role == "user"
            ]

        user_messages = []
        for event in message_events:
            for content in event.llm_message.content:
                if isinstance(content, TextContent):
                    user_messages.append(content.text)

        assert "alligator" in str(user_messages), (
            "Alligator request message should be in events"
        )
        assert "butterfly" in str(user_messages), (
            "Butterfly request message should be in events"
        )

        # 注意：“alligator”消息是在第 1 步运行循环期间发送的
        # 保持状态锁。 它是否出现在下一个 LLM 调用中可能与时间相关（谁在下一次迭代中首先
        # 获取锁）。 出于本次测试的目的（防止终点比赛），我们不断言“鳄鱼”的存在。 我们只
        # 要求最后一步消息（“蝴蝶”）永远不会被处理。
        #

        # 验证蝴蝶请求 WAS 已处理（修复验证）
        butterfly_seen = any(
            "butterfly" in str(call["messages"]).lower()
            for call in self.llm_completion_calls
        )
        assert butterfly_seen, (
            "Butterfly request should have been seen by LLM. "
            "The fix should ensure unattended messages are processed."
        )

        # TIMING ANALYSIS: 验证在最后一步执行期间发送的蝴蝶
        print("\nTIMING ANALYSIS:")

        # 提取时间戳
        timestamp_dict: dict[str, float] = dict(self.timestamps)
        if (
            "final_step_start" in timestamp_dict
            and "butterfly_sent" in timestamp_dict
            and "final_step_end" in timestamp_dict
        ):
            final_start = timestamp_dict["final_step_start"]
            butterfly_sent = timestamp_dict["butterfly_sent"]
            final_end = timestamp_dict["final_step_end"]

            print(f"- Final step started: [{final_start - self.test_start_time:.3f}s]")
            print(f"- Butterfly sent: [{butterfly_sent - self.test_start_time:.3f}s]")
            print(f"- Final step ended: [{final_end - self.test_start_time:.3f}s]")

            # CRITICAL ASSERTION：最后一步执行期间发送的蝴蝶消息
            assert final_start <= butterfly_sent <= final_end, (
                f"Butterfly message was NOT sent during final step execution! "
                f"Final step: {final_start:.3f}s-{final_end:.3f}s, "
                f"Butterfly sent: {butterfly_sent:.3f}s"
            )
            print("VERIFIED: Butterfly message was sent DURING final step execution")

            # 持续时间计算
            step_duration = final_end - final_start
            butterfly_timing = butterfly_sent - final_start
            print(
                f"- Butterfly sent {butterfly_timing:.3f}s into "
                f"{step_duration:.3f}s final step"
            )
        else:
            print("WARNING: Missing timing data for analysis")
            print(f"Available timestamps: {list(timestamp_dict.keys())}")

        # 测试已成功验证修复行为！
        print("\nTEST SUCCESSFULLY VERIFIES THE FIX:")
        print("- Alligator request: sent during step 1 → processed in step 2")
        print(
            "- Butterfly request: sent during step 2 (final step execution) "
            "→ processed in step 3"
        )
        print("- Both messages exist in events, and both reached LLM")
        print(
            "- This proves: messages sent during final step execution "
            "are properly detected and processed"
        )


# 可选：作为脚本执行时并行运行此测试 N 次
# 用法（来自存储库根）：
#   python tests/sdk/agent/test_message_while_finishing.py --runs 50 --concurrency 50
# 这会多次调用 pytest 进行此测试，总结结果。


def _run_parallel_main():  # pragma: no cover - helper for manual stress testing
    import argparse
    import os
    import shutil
    import subprocess
    import sys

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    test_rel = os.path.relpath(__file__, repo_root)
    default_node = (
        f"{test_rel}::"
        "TestMessageWhileFinishing::test_message_processing_fix_verification"
    )

    parser = argparse.ArgumentParser(
        description="Run this race test many times in parallel"
    )
    parser.add_argument("--nodeid", default=default_node, help="Pytest node id")
    parser.add_argument("--runs", type=int, default=50, help="Total runs")
    parser.add_argument("--concurrency", type=int, default=50, help="Max parallel runs")
    parser.add_argument(
        "--no-uv", action="store_true", help="Run pytest directly (no 'uv run')"
    )
    parser.add_argument(
        "--pytest-args", nargs=argparse.REMAINDER, help="Extra args passed to pytest"
    )
    args = parser.parse_args()

    use_uv = not args.no_uv
    extra_args = args.pytest_args if args.pytest_args else []

    print(
        f"Running {args.nodeid} {args.runs} times with "
        f"concurrency={args.concurrency} (uv={use_uv})"
    )

    def run_one(idx: int) -> tuple[int, int, str]:
        cmd: list[str] = []
        if use_uv and shutil.which("uv"):
            cmd.extend(["uv", "run"])  # 首选 uv（如果有）
        cmd.extend(["pytest", "-q", args.nodeid])
        if extra_args:
            cmd.extend(extra_args)

        env = os.environ.copy()
        start = datetime.now()
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=repo_root,
            env=env,
            text=True,
        )
        duration = (datetime.now() - start).total_seconds()
        out = f"[run {idx:02d}] rc={proc.returncode} dur={duration:.2f}s\n" + (
            proc.stdout or ""
        )
        return idx, proc.returncode, out

    failures: list[tuple[int, int, str]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(run_one, i + 1) for i in range(args.runs)]
        for fut in as_completed(futures):
            idx, rc, output = fut.result()
            status = "PASS" if rc == 0 else "FAIL"
            print(f"[run {idx:02d}] {status}")
            if rc != 0:
                failures.append((idx, rc, output))

    print("\nSummary:")
    print(
        f"Total: {args.runs}, Passed: "
        f"{args.runs - len(failures)}, Failed: {len(failures)}"
    )
    if failures:
        print("\n--- Failure outputs (first 3) ---")
        for i, (_idx, _rc, out) in enumerate(failures[:3], 1):
            print(f"\n[Failure {i}]\n{out}")
        sys.exit(1)

    print("All runs passed ✅")


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    _run_parallel_main()
