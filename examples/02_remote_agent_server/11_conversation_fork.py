"""通过 Agent Server REST API 分叉对话。

演示 ``RemoteConversation.fork()`` 委托给服务器的
``POST /api/conversations/{id}/fork`` 端点。 分叉在服务器端深度复制事件和状态，然后返
回一个新的
``RemoteConversation`` 指向副本。

涵盖的场景：
  1. 在服务器上运行源对话
  2. Fork it — 验证独立事件历史
  3. 带有标题和自定义标签的分叉
"""

import os
import tempfile

from pydantic import SecretStr
from scripts.utils import ManagedAPIServer

from openhands.sdk import LLM, Agent, Conversation, RemoteConversation, Tool, Workspace
from openhands.tools.terminal import TerminalTool


# -----------------------------------------------------------------
# 配置
# -----------------------------------------------------------------
api_key = os.getenv("LLM_API_KEY")
assert api_key, "LLM_API_KEY must be set"

llm = LLM(
    model=os.getenv("LLM_MODEL", "gpt-5.5"),
    api_key=SecretStr(api_key),
    base_url=os.getenv("LLM_BASE_URL"),
)
agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name)])

# -----------------------------------------------------------------
# 运行
# -----------------------------------------------------------------
with ManagedAPIServer(port=8002) as server:
    workspace_dir = tempfile.mkdtemp(prefix="fork_demo_")
    workspace = Workspace(host=server.base_url, working_dir=workspace_dir)

    # =============================================================
    # 1. 来源对话
    # =============================================================
    source = Conversation(agent=agent, workspace=workspace)
    assert isinstance(source, RemoteConversation)

    source.send_message("Run `echo hello-from-source` in the terminal.")
    source.run()

    print("=" * 64)
    print("  RemoteConversation.fork() — Agent-Server Example")
    print("=" * 64)
    print(f"\nSource conversation ID : {source.id}")
    source_event_count = len(source.state.events)
    print(f"Source events count    : {source_event_count}")

    # =============================================================
    # 2. 独立分叉并继续
    # =============================================================
    fork = source.fork(title="Follow-up fork")
    assert isinstance(fork, RemoteConversation)

    print("\n--- Fork created ---")
    print(f"Fork ID                : {fork.id}")
    fork_event_count = len(fork.state.events)
    print(f"Fork events (copied)   : {fork_event_count}")

    assert fork.id != source.id
    # 分叉从服务器端 EventLog 复制所有已持久化事件。 源的客户端列表可能还包含仅瞬态
    # WebSocket 事件 (e.g. 全状态快照）永远不会已持久化，因此我们只断言分叉具有非平凡数
    # 量的事件而不是精确的奇偶校验。
    #
    assert fork_event_count > 0

    fork.send_message("Now run `echo hello-from-fork` in the terminal.")
    fork.run()

    print("\n--- After running fork ---")
    print(f"Source events          : {len(source.state.events)}")
    print(f"Fork events (grew)     : {len(fork.state.events)}")
    assert len(fork.state.events) > fork_event_count

    # =============================================================
    # 3. 带标签的叉子
    # =============================================================
    fork_tagged = source.fork(
        title="Tagged experiment",
        tags={"purpose": "a/b-test"},
    )
    assert isinstance(fork_tagged, RemoteConversation)

    print("\n--- Fork with tags ---")
    print(f"Fork ID     : {fork_tagged.id}")

    fork_tagged.send_message(
        "What command did you run earlier? Just tell me, no tools."
    )
    fork_tagged.run()

    print(f"Fork events : {len(fork_tagged.state.events)}")

    # =============================================================
    # 总结
    # =============================================================
    print(f"\n{'=' * 64}")
    print("All done — RemoteConversation.fork() works end-to-end.")
    print("=" * 64)

    # 清理
    fork.close()
    fork_tagged.close()
    source.close()

cost = llm.metrics.accumulated_cost
print(f"EXAMPLE_COST: {cost}")
