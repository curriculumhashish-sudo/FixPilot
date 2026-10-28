"""测试 openhands.sdk.event.resume_transcript。"""

from __future__ import annotations

import json

import pytest

from openhands.sdk.event import (
    RESUME_CONTEXT_MARKER,
    ACPToolCallEvent,
    ActionEvent,
    MessageEvent,
    render_resume_transcript,
)
from openhands.sdk.event.resume_transcript import (
    DEFAULT_FOOTER,
    DEFAULT_HEADER_BODY,
)
from openhands.sdk.llm import ImageContent, Message, MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishAction
from openhands.sdk.tool.schema import Action


def _user(text: str) -> MessageEvent:
    return MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text=text)]),
    )


def _assistant(text: str) -> MessageEvent:
    return MessageEvent(
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text=text)]),
    )


def _finish(text: str) -> ActionEvent:
    return ActionEvent(
        source="agent",
        thought=[TextContent(text="")],
        action=FinishAction(message=text),
        tool_name="finish",
        tool_call_id="finish-1",
        tool_call=MessageToolCall(
            id="finish-1",
            name="finish",
            arguments=json.dumps({"message": text}),
            origin="completion",
        ),
        llm_response_id="resp-1",
    )


def _tool(
    call_id: str,
    *,
    title: str = "edit",
    status: str | None = "completed",
    raw_input: object | None = None,
    raw_output: object | None = None,
    is_error: bool = False,
    content: list | None = None,
    tool_kind: str | None = None,
) -> ACPToolCallEvent:
    return ACPToolCallEvent(
        tool_call_id=call_id,
        title=title,
        status=status,
        tool_kind=tool_kind,
        raw_input=raw_input,
        raw_output=raw_output,
        content=content,
        is_error=is_error,
    )


class TestRenderResumeTranscript:
    def test_empty_events_returns_none(self) -> None:
        assert render_resume_transcript([]) is None

    def test_only_irrelevant_events_returns_none(self) -> None:
        # 没有输入/输出/错误的占位符工具事件将被跳过。
        placeholder = _tool("tc-1", raw_input=None, raw_output=None)
        assert render_resume_transcript([placeholder]) is None

    def test_renders_user_and_assistant_messages(self) -> None:
        out = render_resume_transcript([_user("Hi"), _assistant("Hello!")])
        assert out is not None
        assert out.startswith(RESUME_CONTEXT_MARKER)
        assert DEFAULT_HEADER_BODY in out
        assert "[USER]: Hi" in out
        assert "[ASSISTANT]: Hello!" in out
        assert out.endswith(DEFAULT_FOOTER)

    def test_renders_tool_use_with_status_and_io(self) -> None:
        event = _tool(
            "tc-1",
            title="bash",
            status="completed",
            raw_input={"command": "ls"},
            raw_output="file.txt",
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[TOOL USE: bash] (completed)" in out
        assert "input:" in out
        assert "command" in out
        assert "output:" in out
        assert "file.txt" in out

    def test_failed_tool_uses_failed_status(self) -> None:
        event = _tool(
            "tc-1",
            title="bash",
            status="completed",
            raw_output="boom",
            is_error=True,
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[TOOL USE: bash] (failed)" in out

    def test_renders_finish_action_as_agent_summary(self) -> None:
        out = render_resume_transcript([_finish("All done.")])
        assert out is not None
        assert "[AGENT]: All done." in out

    def test_deduplicates_tool_events_by_id(self) -> None:
        # 同一 tool_call_id 的三个流事件 — 只应渲染终端事件（带有 raw_output）。
        #
        pending = _tool("tc-1", title="bash", status="pending", raw_input={"c": 1})
        progress = _tool("tc-1", title="bash", status="in_progress", raw_input={"c": 1})
        completed = _tool(
            "tc-1",
            title="bash",
            status="completed",
            raw_input={"c": 1},
            raw_output="ok",
        )
        out = render_resume_transcript([pending, progress, completed])
        assert out is not None
        assert out.count("[TOOL USE: bash]") == 1
        assert "(completed)" in out
        assert "ok" in out

    def test_started_then_terminal_renders_only_terminal(self) -> None:
        # 源现在每次调用都保留两个事件：早期
        # ``started`` in_progress 事件和一个终端事件。 转录本必须只保留最后一个——它携带
        # 最终的 I/O。
        #
        started = _tool("tc-1", title="bash", status="in_progress", raw_input={"c": 1})
        terminal = _tool(
            "tc-1",
            title="bash",
            status="completed",
            raw_input={"c": 1},
            raw_output="final output",
        )
        out = render_resume_transcript([started, terminal])
        assert out is not None
        assert out.count("[TOOL USE: bash]") == 1
        assert "(completed)" in out
        assert "final output" in out

    def test_cross_session_same_id_both_render(self) -> None:
        # ACP 像 Codex 重置 tool_call_id 这样的提供商会对每个会话进行计数器。 具有相同
        # id 的两个事件之间的用户消息意味着它们来了
        #
        # from different sessions — both must render, not just the latest.
        session_1 = _tool(
            "exec_1",
            title="bash",
            raw_input={"command": "pytest"},
            raw_output="5 passed",
        )
        boundary = _user("please continue")  # 会话边界
        session_2 = _tool(
            "exec_1",  # 相同的 ID，新会话
            title="bash",
            raw_input={"command": "ls"},
            raw_output="file.txt",
        )
        out = render_resume_transcript([session_1, boundary, session_2])
        assert out is not None
        # 两个会话都会渲染（不仅仅是最后一个）。
        assert out.count("[TOOL USE: bash]") == 2
        assert "5 passed" in out
        assert "file.txt" in out

    def test_cross_session_dedup_within_session_still_collapses(self) -> None:
        # 在一个会话中，同一 id 的待定→已完成仍然会折叠为终止事件。
        #
        pending = _tool("exec_1", title="bash", status="pending")
        completed = _tool("exec_1", title="bash", raw_output="ok", status="completed")
        # 注意：它们之间没有 MessageEvent — 同一会话。
        out = render_resume_transcript([pending, completed])
        assert out is not None
        assert out.count("[TOOL USE: bash]") == 1
        assert "(completed)" in out

    def test_preserves_order_across_event_types(self) -> None:
        events = [
            _user("first user"),
            _tool("tc-1", title="bash", raw_input={"c": 1}, raw_output="hi"),
            _assistant("second assistant"),
            _finish("third agent"),
        ]
        out = render_resume_transcript(events)
        assert out is not None
        idx_user = out.index("[USER]: first user")
        idx_tool = out.index("[TOOL USE: bash]")
        idx_assistant = out.index("[ASSISTANT]: second assistant")
        idx_agent = out.index("[AGENT]: third agent")
        assert idx_user < idx_tool < idx_assistant < idx_agent

    def test_max_chars_keeps_footer_when_tight(self) -> None:
        # ``max_chars`` 宽度如此之窄，以至于连头和尾页都不能单独容纳：尾部截断回退方案保
        # 留了转录的结尾，这是尾页（以及上面的最新事件内容）。
        #
        events = [_user("x" * 5000)]
        out = render_resume_transcript(events, max_chars=200)
        assert out is not None
        assert len(out) == 200
        assert out.endswith(DEFAULT_FOOTER)

    def test_max_chars_preserves_header_footer_and_newest_event(self) -> None:
        # 用足够大的预算容纳标记、头部、尾部和一段内容，标记位于顶部，尾部位于底部， 一
        # 段内容位于底部 BODY  是头截断的，所以最新的事件存活。
        #
        events = [
            _user("OLD first turn " + "o" * 500),
            _assistant("OLD assistant reply " + "o" * 500),
            _user("NEW most recent turn"),
        ]
        out = render_resume_transcript(events, max_chars=500)
        assert out is not None
        assert len(out) <= 500
        assert out.startswith(RESUME_CONTEXT_MARKER)
        assert out.endswith(DEFAULT_FOOTER)
        # 最新事件必须完好无损。
        assert "NEW most recent turn" in out
        # 最旧的转弯应被丢弃，并带有“...”剪切标记。
        assert "OLD first turn" not in out
        assert "..." in out

    @pytest.mark.parametrize("max_chars", [50, 100, 500])
    def test_max_chars_strictly_bounds_output(self, max_chars: int) -> None:
        # 对于预算 >= len(marker)，输出必须是非 None，且长度 <= max_chars。
        events = [_user("hello"), _assistant("world")]
        out = render_resume_transcript(events, max_chars=max_chars)
        assert out is not None
        assert len(out) <= max_chars

    @pytest.mark.parametrize("max_chars", [0, 1, 10, 23])
    def test_max_chars_below_marker_length_returns_none(self, max_chars: int) -> None:
        # 低于 len(RESUME_CONTEXT_MARKER)（24 个字符）的预算无法容纳完整的标记。 返回部
        # 分标记会绕过双重恢复检查（调用者检查 out.startswith(RESUME_CONTEXT_MARKER)），
        # 因此返回 None，调用者将其视为新的对话。
        #
        assert render_resume_transcript([_user("hello")], max_chars=max_chars) is None

    @pytest.mark.parametrize("max_chars", [24, 30, 200])
    def test_tight_budget_output_starts_with_complete_marker(
        self, max_chars: int
    ) -> None:
        # 对于任何预算 >= len(marker)，即使是非常严格的上限，也会返回一个以完整、未截断
        # 的标记开始的转录，这样用户可以可靠地检测到暂停，并且双暂停保护机制可以正常工作
        # 。
        #
        events = [_user("x" * 5000)]
        out = render_resume_transcript(events, max_chars=max_chars)
        assert out is not None
        assert len(out) <= max_chars
        assert out.startswith(RESUME_CONTEXT_MARKER)

    @pytest.mark.parametrize("cap", [0, 1, 2, 3, 4, 50])
    def test_max_message_chars_strictly_bounds_text(self, cap: int) -> None:
        # 消息行的文本部分（在“[USER]:”之后）必须≤大写字符，无论 ``cap`` 有多小。
        #
        events = [_user("x" * 500)]
        out = render_resume_transcript(events, max_message_chars=cap)
        assert out is not None
        user_line = next(ln for ln in out.splitlines() if ln.startswith("[USER]"))
        text_portion = user_line[len("[USER]: ") :]
        assert len(text_portion) <= cap

    def test_max_tool_chars_zero_skips_tool_block(self) -> None:
        # 使用 ``max_tool_chars=0`` 时，渲染的工具块将变为“”并被删除 — 非工具事件仍会渲
        # 染。
        #
        events = [
            _user("hi"),
            _tool("tc-1", title="bash", raw_input={"command": "ls"}),
        ]
        out = render_resume_transcript(events, max_tool_chars=0)
        assert out is not None
        assert "[USER]: hi" in out
        assert "[TOOL USE:" not in out

    def test_content_only_tool_event_is_rendered(self) -> None:
        # 工具事件，其唯一的载荷是结构化的 ``content``（无
        # ``raw_input``/``raw_output``/``is_error``) 必须不能被过滤为占位符。 ACP 服务器
        # （例如 Codex 和 Gemini）通过 ``content`` 而不是原始 I/O 发出差异或终端数据。
        #
        event = _tool(
            "tc-1",
            title="edit",
            content=[
                {
                    "type": "diff",
                    "path": "/workspace/app.py",
                    "old_text": "old",
                    "new_text": "new",
                }
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[TOOL USE: edit]" in out
        assert "content:" in out
        assert "[diff patch] /workspace/app.py" in out

    def test_content_only_tool_event_camelcase_diff(self) -> None:
        # 与上面的 JSON 线键相同 - 仅内容渲染必须接受 ``oldText`` / ``newText`` 别名。
        #
        event = _tool(
            "tc-1",
            title="Edit",
            content=[
                {
                    "type": "diff",
                    "path": "/workspace/app.py",
                    "oldText": "old",
                    "newText": "new",
                }
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[diff patch] /workspace/app.py" in out

    def test_content_only_write_block_labelled_as_write(self) -> None:
        # 没有 ``old_text`` 的 diff 块是完整文件写入，而不是补丁； 渲染的线反映了这一点
        # 。
        #
        event = _tool(
            "tc-1",
            title="write",
            content=[
                {
                    "type": "diff",
                    "path": "/workspace/new.py",
                    "old_text": None,
                    "new_text": "whole file",
                }
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[diff write] /workspace/new.py" in out

    def test_direct_text_block_renders_verbatim(self) -> None:
        # ``_serialize_tool_content`` 保留直接 ``{type: "text",
        # text: "..."}`` ContentBlocks 在顶层（没有
        # ``{type: "content"}`` 包装）。 它们的文本必须被渲染，而不是被压缩到``[text]``
        # 。
        #
        event = _tool(
            "tc-1",
            title="search",
            content=[{"type": "text", "text": "matched 12 lines"}],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "matched 12 lines" in out
        assert "[text]" not in out

    def test_direct_image_block_renders_placeholder(self) -> None:
        event = _tool(
            "tc-1",
            title="screenshot",
            content=[
                {"type": "image", "data": "base64-bytes", "mimeType": "image/png"}
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[Image]" in out

    @pytest.mark.parametrize("falsey_output", [0, False, ""])
    def test_falsey_raw_output_is_rendered(self, falsey_output: object) -> None:
        # 工具可以合法地返回错误标量：``0`` 来自 shell 退出代码，``False`` 来自布尔谓词
        # ，``""`` 来自静默命令。 None 其中是占位符。
        #
        event = _tool(
            "tc-1",
            title="cmd",
            raw_input={"command": "true"},
            raw_output=falsey_output,
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "output:" in out
        assert str(falsey_output) in out

    def test_falsey_raw_output_only_is_not_a_placeholder(self) -> None:
        # ``raw_output=0`` 是有效的完成； 即使没有 ``raw_input``，事件也应该呈现而不是被
        # 丢弃。
        #
        event = _tool("tc-1", title="cmd", raw_output=0)
        out = render_resume_transcript([event])
        assert out is not None
        assert "[TOOL USE: cmd]" in out
        assert "output:" in out

    def test_content_text_block_renders_inline(self) -> None:
        # ToolCallContent {type: "content", content: {type: "text", ...}} 是通用
        # ContentBlock 变体的 ACP 包装器。 文本内容应内联显示在“内容：”下。
        #
        event = _tool(
            "tc-1",
            title="search",
            content=[
                {
                    "type": "content",
                    "content": {"type": "text", "text": "found 3 matches"},
                }
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "found 3 matches" in out

    def test_content_terminal_block_renders_label(self) -> None:
        event = _tool(
            "tc-1",
            title="shell",
            content=[{"type": "terminal", "terminal_id": "term-abc"}],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "[terminal term-abc]" in out

    def test_placeholder_with_empty_content_still_skipped(self) -> None:
        # 没有输入、没有输出、没有错误且内容列表为空的待处理事件仍然是占位符，应将其删除
        # 。
        #
        event = _tool("tc-1", content=[])
        assert render_resume_transcript([event]) is None

    def test_content_rendered_alongside_raw_io(self) -> None:
        # 当内容和原始 I/O 都存在时，两者都会呈现（不会丢失信息）。
        #
        event = _tool(
            "tc-1",
            title="edit",
            raw_input={"file_path": "/foo"},
            raw_output="ok",
            content=[
                {"type": "diff", "path": "/foo", "old_text": "a", "new_text": "b"}
            ],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "input:" in out
        assert "content:" in out
        assert "output:" in out
        assert "[diff patch] /foo" in out

    def test_extended_content_is_included(self) -> None:
        # ``MessageEvent.extended_content``（AgentContext/每回合提供的钩子上下文）被
        # ``to_llm_message()``折叠，ACP将其视为回合的一部分。 成绩单必须包含它，以便恢复
        # 的智能体具有相同的上下文。
        #
        event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user", content=[TextContent(text="base content")]
            ),
            extended_content=[TextContent(text="extra context from hook")],
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "base content" in out
        assert "extra context from hook" in out

    def test_max_message_chars_truncates_long_turn(self) -> None:
        events = [_user("x" * 10_000)]
        out = render_resume_transcript(events, max_message_chars=100)
        assert out is not None
        user_line = next(ln for ln in out.splitlines() if ln.startswith("[USER]"))
        assert user_line.endswith("...")
        # 文本部分（“[USER]:”之后）上限为 max_message_chars。
        assert len(user_line) - len("[USER]: ") <= 100

    def test_max_tool_chars_truncates_tool_block(self) -> None:
        event = _tool(
            "tc-1",
            title="bash",
            raw_input={"command": "x" * 5000},
        )
        out = render_resume_transcript([event], max_tool_chars=120)
        assert out is not None
        # 从主体（页眉和页脚之间）恢复渲染的工具块，并验证整个块以 max_tool_chars 为边界
        # 。
        #
        body_start = out.index("[TOOL USE:")
        body_end = out.index(DEFAULT_FOOTER)
        tool_block = out[body_start:body_end].strip()
        assert "..." in tool_block
        assert len(tool_block) <= 120

    def test_image_content_renders_as_placeholder(self) -> None:
        # ImageContent → "[Image: N URLs]" via content_to_str. 测试渲染器不会崩溃并生成
        # 标记线。
        #
        event = MessageEvent(
            source="user",
            llm_message=Message(
                role="user",
                content=[
                    TextContent(text="see this:"),
                    ImageContent(image_urls=["http://example.com/a.png"]),
                ],
            ),
        )
        out = render_resume_transcript([event])
        assert out is not None
        assert "see this:" in out
        assert "[Image:" in out

    def test_empty_message_content_is_skipped(self) -> None:
        # 内容呈现为空文本的 MessageEvent 不应产生杂散的“[USER]:”行。
        #
        event = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="   ")]),
        )
        assert render_resume_transcript([event]) is None

    def test_unknown_event_types_are_ignored(self) -> None:
        # 将 MessageEvent 与“不可渲染”事件混合 — 此处，ActionEvent 的操作为 None（无消息
        # 字段）。
        #
        action_event = ActionEvent(
            source="agent",
            thought=[TextContent(text="thinking")],
            action=None,
            tool_name="x",
            tool_call_id="x-1",
            tool_call=MessageToolCall(
                id="x-1", name="x", arguments="{}", origin="completion"
            ),
            llm_response_id="r-1",
        )
        out = render_resume_transcript([action_event, _user("hi")])
        assert out is not None
        assert "[USER]: hi" in out
        assert "[AGENT]" not in out

    def test_custom_marker_and_header(self) -> None:
        out = render_resume_transcript(
            [_user("hi")],
            marker="<<CUSTOM MARKER>>",
            header_body="custom body",
            footer="--- end ---",
        )
        assert out is not None
        assert out.startswith("<<CUSTOM MARKER>>")
        assert "custom body" in out
        assert out.endswith("--- end ---")

    def test_empty_header_body_omits_header_paragraph(self) -> None:
        out = render_resume_transcript([_user("hi")], header_body="")
        assert out is not None
        lines = out.splitlines()
        assert lines[0] == RESUME_CONTEXT_MARKER
        assert lines[1] == ""
        # 下一个非空行是用户轮流，而不是标题正文文本。
        assert lines[2].startswith("[USER]")


class TestIsPatchEdit:
    def test_diff_content_with_old_text_is_patch(self) -> None:
        ev = _tool(
            "tc-1",
            content=[
                type(
                    "DiffBlock",
                    (),
                    {"type": "diff", "old_text": "before", "new_text": "after"},
                )()
            ],
        )
        assert ev.is_patch_edit is True

    def test_diff_content_without_old_text_is_full_write(self) -> None:
        ev = _tool(
            "tc-1",
            content=[
                type(
                    "DiffBlock",
                    (),
                    {"type": "diff", "old_text": None, "new_text": "whole file"},
                )()
            ],
        )
        assert ev.is_patch_edit is False

    def test_raw_input_old_string_fallback(self) -> None:
        ev = _tool(
            "tc-1",
            raw_input={"old_string": "x", "new_string": "y", "file_path": "/a"},
        )
        assert ev.is_patch_edit is True

    def test_raw_input_without_diff_keys_is_not_patch(self) -> None:
        ev = _tool("tc-1", raw_input={"command": "ls"})
        assert ev.is_patch_edit is False

    def test_no_content_no_raw_input_is_not_patch(self) -> None:
        ev = _tool("tc-1")
        assert ev.is_patch_edit is False

    def test_dict_content_with_old_text_is_patch(self) -> None:
        # 已持久化 ACP 事件将内容块存储为普通字典（通过
        # ``_serialize_tool_content`` → ``model_dump``). 该属性必须处理属性和字典访问。
        #
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "old_text": "before", "new_text": "after"}],
        )
        assert ev.is_patch_edit is True

    def test_dict_content_without_old_text_is_full_write(self) -> None:
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "old_text": None, "new_text": "whole file"}],
        )
        assert ev.is_patch_edit is False

    def test_model_validate_dict_content_classifies_correctly(self) -> None:
        # 回归覆盖了 QA 审查者发现的失败场景：通过 ``model_validate`` 从 JSON 结构的载荷
        # 重建事件时，``content[0]`` 会保留为字典，而 ``is_patch_edit`` 仍必须正确地对其
        # 分类。
        #
        ev = ACPToolCallEvent.model_validate(
            {
                "tool_call_id": "validated-diff",
                "title": "Edit",
                "content": [
                    {
                        "type": "diff",
                        "old_text": "before",
                        "new_text": "after",
                    }
                ],
            }
        )
        assert ev.content is not None
        assert isinstance(ev.content[0], dict)
        assert ev.is_patch_edit is True

    def test_raw_input_only_new_string_is_not_patch(self) -> None:
        # 写入/创建载荷可能只携带 ``new_string`` — 这不是补丁编辑，而是完整文件写入。
        #
        ev = _tool("tc-1", raw_input={"new_string": "whole file", "file_path": "/a"})
        assert ev.is_patch_edit is False

    def test_raw_input_empty_old_string_is_not_patch(self) -> None:
        # 空的 ``old_string`` 没有什么可修补的——它实际上是一个创建。
        #
        ev = _tool("tc-1", raw_input={"old_string": "", "new_string": "y"})
        assert ev.is_patch_edit is False

    def test_diff_content_takes_precedence_over_raw_input(self) -> None:
        # 如果两个信号都存在，则结构化 ACP 内容块获胜 - 它是协议级事实来源。
        #
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "old_text": None, "new_text": "x"}],
            raw_input={"old_string": "abc", "new_string": "def"},
        )
        assert ev.is_patch_edit is False

    def test_camel_case_oldText_alias_classifies_as_patch(self) -> None:
        # ACP 的 JSON 有线格式使用 camelCase: ``oldText`` / ``newText``。 当事件从外部
        # API 或 WebSocket 框架到达时，字典键保持该形状，因为 ``content`` 是
        # ``list[Any]``。
        #
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "oldText": "before", "newText": "after"}],
        )
        assert ev.is_patch_edit is True

    def test_camel_case_without_oldText_is_full_write(self) -> None:
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "oldText": None, "newText": "whole file"}],
        )
        assert ev.is_patch_edit is False

    def test_diff_block_after_other_blocks_is_found(self) -> None:
        # ACP 内容是任意顺序的变体列表 - 文本或端子块可以位于差异之前。
        # ``is_patch_edit`` 必须扫描整个列表，而不是仅检查 ``content[0]``。
        #
        ev = _tool(
            "tc-1",
            content=[
                {"type": "content", "content": {"type": "text", "text": "Editing…"}},
                {"type": "diff", "old_text": "before", "new_text": "after"},
            ],
        )
        assert ev.is_patch_edit is True

    def test_any_diff_block_with_old_text_is_patch(self) -> None:
        # 多文件工具调用可以包含写入 (``oldText=None``) 和补丁 (``oldText`` 集)。 如果 *
        # any* diff 是补丁，则该事件是补丁编辑； 只有全写集才被归类为写。
        #
        ev_patch_then_write = _tool(
            "tc-1",
            content=[
                {"type": "diff", "old_text": "before", "new_text": "after"},
                {"type": "diff", "old_text": None, "new_text": "second"},
            ],
        )
        assert ev_patch_then_write.is_patch_edit is True

        ev_write_then_patch = _tool(
            "tc-2",
            content=[
                {"type": "diff", "old_text": None, "new_text": "create"},
                {"type": "diff", "old_text": "before", "new_text": "after"},
            ],
        )
        assert ev_write_then_patch.is_patch_edit is True

    def test_all_diff_blocks_writes_classify_as_write(self) -> None:
        ev = _tool(
            "tc-1",
            content=[
                {"type": "diff", "old_text": None, "new_text": "a"},
                {"type": "diff", "old_text": None, "new_text": "b"},
            ],
        )
        assert ev.is_patch_edit is False

    def test_diff_content_blocks_never_fall_back_to_raw_input(self) -> None:
        # 结构化ACP内容具有权威性。 当所有 diff 块都被写入时，即使 ``raw_input`` 会触发
        # 补丁回退方案，事件也必须归类为写入。
        #
        ev = _tool(
            "tc-1",
            content=[{"type": "diff", "old_text": None, "new_text": "create"}],
            raw_input={"old_string": "abc", "new_string": "def"},
        )
        assert ev.is_patch_edit is False


@pytest.mark.parametrize(
    "role,label",
    [("user", "[USER]"), ("assistant", "[ASSISTANT]")],
)
def test_role_labelling(role: str, label: str) -> None:
    event = MessageEvent(
        source="user" if role == "user" else "agent",
        llm_message=Message(role=role, content=[TextContent(text="x")]),  # type: ignore[arg-type]
    )
    out = render_resume_transcript([event])
    assert out is not None
    assert f"{label}: x" in out


def test_action_event_message_property_and_custom_action_transcript() -> None:
    """ActionEvent 公开来自 FinishAction 的转录消息和自定义操作。"""
    finish_action = FinishAction(message="Task finished successfully.")
    event_with_finish = ActionEvent(
        source="agent",
        thought=[TextContent(text="done")],
        action=finish_action,
        tool_name="finish",
        tool_call_id="call-finish",
        tool_call=MessageToolCall(
            id="call-finish",
            name="finish",
            arguments='{"message": "Task finished successfully."}',
            origin="completion",
        ),
        llm_response_id="resp-1",
    )
    assert finish_action.message == "Task finished successfully."
    assert event_with_finish.message == "Task finished successfully."

    transcript = render_resume_transcript([event_with_finish])
    assert transcript is not None
    assert "[AGENT]: Task finished successfully." in transcript

    class CustomActionWithMessage(Action):
        message: str = "custom summary here"

    custom_msg_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="calling custom with message")],
        action=CustomActionWithMessage(),
        tool_name="custom_with_msg",
        tool_call_id="call-custom-msg",
        tool_call=MessageToolCall(
            id="call-custom-msg",
            name="custom_with_msg",
            arguments='{"message": "custom summary here"}',
            origin="completion",
        ),
        llm_response_id="resp-2-msg",
    )
    assert isinstance(custom_msg_event.action, CustomActionWithMessage)
    assert custom_msg_event.action.message == "custom summary here"
    assert custom_msg_event.message == "custom summary here"
    custom_transcript = render_resume_transcript([custom_msg_event])
    assert custom_transcript is not None
    assert "[AGENT]: custom summary here" in custom_transcript

    class PropertyMessageAction(Action):
        @property
        def message(self) -> str:
            return "property summary here"

    property_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="calling property message")],
        action=PropertyMessageAction(),
        tool_name="property_msg",
        tool_call_id="call-property-msg",
        tool_call=MessageToolCall(
            id="call-property-msg",
            name="property_msg",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="resp-2-property",
    )
    assert property_event.message == "property summary here"
    property_transcript = render_resume_transcript([property_event])
    assert property_transcript is not None
    assert "[AGENT]: property summary here" in property_transcript

    class CustomActionWithoutMessage(Action):
        data: str = "custom"

    custom_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="calling custom")],
        action=CustomActionWithoutMessage(),
        tool_name="custom",
        tool_call_id="call-custom",
        tool_call=MessageToolCall(
            id="call-custom",
            name="custom",
            arguments='{"data": "custom"}',
            origin="completion",
        ),
        llm_response_id="resp-2",
    )
    assert custom_event.message is None

    none_action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="no action")],
        action=None,
        tool_name="none",
        tool_call_id="call-none",
        tool_call=MessageToolCall(
            id="call-none",
            name="none",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="resp-3",
    )
    assert none_action_event.message is None
