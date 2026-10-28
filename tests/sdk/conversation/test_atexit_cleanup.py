"""测试 atexit 处理程序清理以防止内存泄漏。"""

import gc
import tempfile
import weakref
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM


def _make_conversation(workspace: str) -> LocalConversation:
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("k"), usage_id="test")
    return LocalConversation(agent=Agent(llm=llm, tools=[]), workspace=workspace)


def test_close_unregisters_atexit_handler():
    """close() 必须删除 atexit 处理程序，以便可以对对象进行 GC。"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = str(Path(tmp) / "ws")
        Path(workspace).mkdir()
        conv = _make_conversation(workspace)

        conv.close()

        # 如果 atexit 仍然保留引用，那么在我们删除强引用后，弱引用将保持活动状态。
        #
        ref = weakref.ref(conv)
        del conv
        gc.collect()
        assert ref() is None, "Conversation was not GC'd — atexit leak"


def test_close_is_idempotent_with_atexit():
    """即使使用 atexit 处理，调用 close() 两次也不能引发异常。"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = str(Path(tmp) / "ws")
        Path(workspace).mkdir()
        conv = _make_conversation(workspace)

        conv.close()
        conv.close()  # 第二次调用是空操作
