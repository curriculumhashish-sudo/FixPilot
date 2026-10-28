"""测试清理 LLM 配置文件 (``clean_outward_text``)。

清理脚本修复了智能体在人类阅读之前的人外文本。 它解决了一个保存的 LLM [profile named]
 ``cleanup`` 它运行一个单个无状态完成，当配置缺失或调
用失败时，以失败打开（返回原始文本）。
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import PrivateAttr

from openhands.sdk.llm import (
    CLEANUP_PROFILE_NAME,
    LLM,
    LLMResponse,
    Message,
    TextContent,
    aclean_outward_text,
    clean_outward_text,
    llm_profile_store,
)
from openhands.sdk.llm.llm import LLMCallContext
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.llm.streaming import TokenCallbackType
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import ToolDefinition


class CapturingTestLLM(TestLLM):
    """TestLLM记录上次完成的消息和工具。"""

    _last_messages: list[Message] = PrivateAttr(default_factory=list)
    _last_tools: Sequence[ToolDefinition] | None = PrivateAttr(default=None)

    @property
    def last_messages(self) -> list[Message]:
        return self._last_messages

    @property
    def last_tools(self) -> Sequence[ToolDefinition] | None:
        return self._last_tools

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self._last_messages = list(messages)
        self._last_tools = tools
        return super().completion(
            messages=messages,
            tools=tools,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            call_context=call_context,
            **kwargs,
        )


def _assistant_message(text: str) -> Message:
    return Message(role="assistant", content=[TextContent(text=text)])


def _message_text(message: Message) -> str:
    return "".join(
        content.text for content in message.content if isinstance(content, TextContent)
    )


def _capturing_llm(*replies: str) -> CapturingTestLLM:
    return cast(
        CapturingTestLLM,
        CapturingTestLLM.from_messages(
            [_assistant_message(reply) for reply in replies],
            model="cleanup-model",
            usage_id="cleanup",
        ),
    )


def test_returns_cleaned_text_from_cleanup_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_llm = _capturing_llm("Done! I appreciate the nudge.")

    def load_profile(self: LLMProfileStore, name: str, *, cipher: Any = None) -> LLM:
        assert name == CLEANUP_PROFILE_NAME
        return cleanup_llm

    monkeypatch.setattr(LLMProfileStore, "load", load_profile)

    original = "Done! I appreciate the nudge! \u00f0"
    result = clean_outward_text(original)

    assert result == "Done! I appreciate the nudge."
    # 无状态调用：只有系统+用户消息，没有工具，没有历史记录。
    assert [message.role for message in cleanup_llm.last_messages] == ["system", "user"]
    assert cleanup_llm.last_tools is None
    assert "repair" in _message_text(cleanup_llm.last_messages[0]).lower()
    assert original in _message_text(cleanup_llm.last_messages[1])


def test_cipher_is_forwarded_to_profile_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 密码参数必须达到 LLMProfileStore.load，以便当调用者传递 1 时加密的机密路径起作用。
    #
    cleanup_llm = _capturing_llm("clean")
    sentinel = object()
    seen: dict[str, Any] = {}

    def load_profile(self: LLMProfileStore, name: str, *, cipher: Any = None) -> LLM:
        seen["cipher"] = cipher
        return cleanup_llm

    monkeypatch.setattr(LLMProfileStore, "load", load_profile)

    clean_outward_text("draft \u00f0", cipher=cast(Any, sentinel))

    assert seen["cipher"] is sentinel


def test_missing_profile_returns_original_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 真实的空配置文件目录：不存在“清理”配置文件，因此该功能关闭，原始文本不变地通过。
    #
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)

    original = "Ship it \u00f0"
    assert clean_outward_text(original) == original


def test_call_failure_returns_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 编写没有回复的脚本：下一个完成引发（耗尽），因此清理必须失败并返回未触及的原始内容
    # 。
    #
    failing_llm = _capturing_llm()

    monkeypatch.setattr(
        LLMProfileStore,
        "load",
        lambda self, name, *, cipher=None: failing_llm,
    )

    original = "Keep me exactly \u00e2 as is"
    assert clean_outward_text(original) == original


def test_empty_cleanup_reply_returns_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 空白回复不得使消息空白； 保留原件。
    cleanup_llm = _capturing_llm("   ")
    monkeypatch.setattr(
        LLMProfileStore,
        "load",
        lambda self, name, *, cipher=None: cleanup_llm,
    )

    original = "Real content here"
    assert clean_outward_text(original) == original


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_input_short_circuits_without_loading_profile(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_load(self: LLMProfileStore, name: str, *, cipher: Any = None) -> LLM:
        raise AssertionError("profile should not be loaded for blank input")

    monkeypatch.setattr(LLMProfileStore, "load", fail_load)

    assert clean_outward_text(blank) == blank


async def test_async_returns_cleaned_text_from_cleanup_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_llm = _capturing_llm("Done! I appreciate the nudge.")

    def load_profile(self: LLMProfileStore, name: str, *, cipher: Any = None) -> LLM:
        assert name == CLEANUP_PROFILE_NAME
        return cleanup_llm

    monkeypatch.setattr(LLMProfileStore, "load", load_profile)

    result = await aclean_outward_text("Done! I appreciate the nudge! \u00f0")

    assert result == "Done! I appreciate the nudge."
    assert [message.role for message in cleanup_llm.last_messages] == ["system", "user"]


async def test_async_missing_profile_returns_original_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)

    original = "Ship it \u00f0"
    assert await aclean_outward_text(original) == original


async def test_async_call_failure_returns_original_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing_llm = _capturing_llm()
    monkeypatch.setattr(
        LLMProfileStore,
        "load",
        lambda self, name, *, cipher=None: failing_llm,
    )

    original = "Keep me exactly \u00e2 as is"
    assert await aclean_outward_text(original) == original
