"""分支对话。 对话是一棵树（每个事件都有一个
``parent_id``; HEAD 是 ``leaf_event_id``)，暴露了三个原语：

  - ``fork()`` — 将整个对话深复制到一个新对话中； ``run()`` 恢复时事件内存已满。
  - ``fork(from_event_id=...)`` — 仅分叉至所选事件的分支； 分叉的 HEAD 就是那个事件。
  - ``navigate_to(event_id)`` — 在一次对话中移动 HEAD； 导航后追加会创建同级分支，废
  弃的事件保留在磁盘上。

用例：从原始审计跟踪中调试错误的 CI 补丁、A/B 测试提示词、工具更改上的 fork、编辑过去
的转弯并重新运行。
"""

import os

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.sdk.event import MessageEvent
from openhands.tools.terminal import TerminalTool


# -----------------------------------------------------------------
# 设置
# -----------------------------------------------------------------
llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
)

agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name)])
cwd = os.getcwd()

# =================================================================
# 1. 运行源对话
# =================================================================
source = Conversation(agent=agent, workspace=cwd)
source.send_message("Run `echo hello-from-source` in the terminal.")
source.run()

print("=" * 64)
print("  Conversation.fork() — SDK Example")
print("=" * 64)
print(f"\nSource conversation ID : {source.id}")
print(f"Source events count    : {len(source.state.events)}")

# =================================================================
# 2. 独立分叉并继续
# =================================================================
fork = source.fork()
source_event_count = len(source.state.events)

print("\n--- Fork created ---")
print(f"Fork ID                : {fork.id}")
print(f"Fork events (copied)   : {len(fork.state.events)}")

assert fork.id != source.id
assert len(fork.state.events) == source_event_count

fork.send_message("Now run `echo hello-from-fork` in the terminal.")
fork.run()

# 来源未受影响
assert len(source.state.events) == source_event_count
print("\n--- After running fork ---")
print(f"Source events (unchanged): {source_event_count}")
print(f"Fork events (grew)       : {len(fork.state.events)}")

# =================================================================
# 3. 具有不同智能体的前叉（工具更换/A/B 测试）
# =================================================================
alt_llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", None),
    usage_id="alt",
)
alt_agent = Agent(llm=alt_llm, tools=[Tool(name=TerminalTool.name)])

fork_alt = source.fork(
    agent=alt_agent,
    tags={"purpose": "a/b-test"},
)

print("\n--- Fork with alternate agent ---")
print(f"Fork ID     : {fork_alt.id}")
print(f"Fork tags   : {dict(fork_alt.state.tags)}")

fork_alt.send_message("What command did you run earlier? Just tell me, no tools.")
fork_alt.run()

print(f"Fork events : {len(fork_alt.state.events)}")

# =================================================================
# 4. 分支切片分叉：来自选定的过去事件的分叉
# =================================================================
# 从第一条用户消息分叉：仅复制 path_to_root（事件）并在那里设置分叉的 HEAD。
#
cut_event_id = next(
    e.id
    for e in source.state.events
    if isinstance(e, MessageEvent) and e.source == "user"
)

fork_slice = source.fork(from_event_id=cut_event_id)

print("\n--- Branch-slice fork (from_event_id) ---")
print(f"Cut event id          : {cut_event_id}")
print(f"Source events (full)  : {len(source.state.events)}")
print(f"Fork events (sliced)  : {len(fork_slice.state.events)}")
print(f"Fork HEAD             : {fork_slice.state.leaf_event_id}")

# 该切片仅包含直到切割点的分支。
assert len(fork_slice.state.events) <= len(source.state.events)
assert fork_slice.state.leaf_event_id == cut_event_id

fork_slice.send_message("Run `echo sliced-branch` in the terminal.")
fork_slice.run()
print(f"Fork events after run : {len(fork_slice.state.events)}")
assert any("sliced-branch" in str(e) for e in fork_slice.state.events)

# =================================================================
# 5. 对话内导航：移动 HEAD 并创建同级分支
# =================================================================
# 将 HEAD 移回剪切点并发送一条新消息：兄弟分支。 废弃的分支保留在磁盘上，但保留智能体的
# 活动上下文。
#
events_before_nav = len(source.state.events)

source.navigate_to(cut_event_id)
print("\n--- navigate_to (in-conversation branching) ---")
print(f"HEAD moved to         : {source.state.leaf_event_id}")
print(f"Active branch length  : {len(source.state.view.events)} events in context")
print(f"Events still on disk  : {events_before_nav}")

source.send_message("Actually, instead run `echo sibling-branch`.")
source.run()
print(f"Events on disk now     : {len(source.state.events)} (old branch retained)")

# =================================================================
# 总结
# =================================================================
print(f"\n{'=' * 64}")
print("All done — fork() works end-to-end.")
print("=" * 64)

# 报告费用
cost = llm.metrics.accumulated_cost + alt_llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
