"""Streamlit 应用程序用于探索 OpenHands 对话日志。

用途：
    运行 scripts/conversation_viewer.py 的 streamlit

查看者期望包含对话文件夹的目录。 默认情况下，我们在存储库根目录（由创建的位置）旁边查
找 ``.conversations``
``openhands`` 录制会话时）。 您可以通过以下方式覆盖该位置：

* 环境变量 ``OPENHANDS_CONVERSATIONS_ROOT``
* URL打开应用时查询参数``?root=/path/to/logs``
* 侧边栏文本输入标记为“对话目录”

每个对话目录应包含 ``base_state.json`` 加上一个
``events/`` 文件夹，其中包含单独的 ``*.json`` 个事件文件。 查看器将在表格中总结事件并
在展开时显示完整的载荷。
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


ENV_ROOT = os.getenv("OPENHANDS_CONVERSATIONS_ROOT")
DEFAULT_CONVERSATIONS_ROOT = (
    Path(ENV_ROOT).expanduser()
    if ENV_ROOT
    else Path(__file__).resolve().parents[1] / ".conversations"
)

st.set_page_config(page_title="OpenHands Agent-SDK Conversation Viewer", layout="wide")


@dataclass
class Conversation:
    identifier: str
    path: Path
    base_state: dict[str, Any]
    events: list[dict[str, Any]]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def add_filename(event: dict[str, Any], filename: str) -> dict[str, Any]:
    event_copy = dict(event)
    event_copy["_filename"] = filename
    return event_copy


@st.cache_data(show_spinner=False)
def load_conversation(path_str: str) -> Conversation:
    path = Path(path_str)
    identifier = path.name

    base_state: dict[str, Any] = {}
    base_state_path = path / "base_state.json"
    if base_state_path.exists():
        try:
            base_state = load_json(base_state_path)
        except json.JSONDecodeError as exc:
            base_state = {"error": f"Failed to parse base_state.json: {exc}"}

    events_dir = path / "events"
    events: list[dict[str, Any]] = []
    if events_dir.exists():
        for event_file in sorted(events_dir.glob("*.json")):
            try:
                event_data = load_json(event_file)
                events.append(add_filename(event_data, event_file.name))
            except json.JSONDecodeError as exc:
                events.append(
                    {
                        "kind": "InvalidJSON",
                        "source": "parser",
                        "timestamp": "",
                        "error": str(exc),
                        "_filename": event_file.name,
                    }
                )

    return Conversation(
        identifier=identifier, path=path, base_state=base_state, events=events
    )


@st.cache_data(show_spinner=False)
def get_last_event_timestamp(conversation_path_str: str) -> str:
    """获取对话目录中最近事件的时间戳。

    如果未找到事件或无法解析时间戳，则返回空字符串。
    """
    conversation_path = Path(conversation_path_str)
    events_dir = conversation_path / "events"

    if not events_dir.exists():
        return ""

    latest_timestamp = ""
    latest_datetime = None

    for event_file in events_dir.glob("*.json"):
        try:
            event_data = load_json(event_file)
            timestamp = event_data.get("timestamp", "")
            if timestamp:
                # 尝试解析时间戳以正确比较
                try:
                    # 处理各种时间戳格式
                    if "T" in timestamp:
                        # ISO 带 T 分隔符的格式
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    else:
                        # 尝试其他常见格式
                        dt = datetime.fromisoformat(timestamp)

                    if latest_datetime is None or dt > latest_datetime:
                        latest_datetime = dt
                        latest_timestamp = timestamp
                except (ValueError, TypeError):
                    # 如果我们无法解析时间戳，则回退到字符串比较
                    if timestamp > latest_timestamp:
                        latest_timestamp = timestamp
        except (json.JSONDecodeError, OSError):
            # 跳过无法读取或解析的文件
            continue

    return latest_timestamp


def conversation_dirs(root: Path) -> list[Path]:
    """返回 ``root`` 下的对话子目录。

    按最后事件时间戳排序（最近的在前）。
    """
    dirs = [p for p in root.iterdir() if p.is_dir()]

    # 按最后一个事件时间戳排序（最近的在前），回退到目录名称
    def sort_key(path: Path) -> tuple[str, str]:
        timestamp = get_last_event_timestamp(str(path))
        # 降序反转时间戳（最近的在前）使用空字符串作为回退方案，这将排序在最后
        #
        return (timestamp or "", path.name)

    return sorted(dirs, key=sort_key, reverse=True)


def extract_text_blocks(blocks: Iterable[Any] | None) -> str:
    pieces: list[str] = []
    for block in blocks or []:
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "text":
                pieces.append(str(block.get("text", "")))
            elif "text" in block:
                pieces.append(str(block.get("text")))
            elif "content" in block:
                pieces.append(extract_text_blocks(block.get("content")))
        elif isinstance(block, str):
            pieces.append(block)
    return "\n".join(piece for piece in pieces if piece)


def get_event_text(event: dict[str, Any]) -> str:
    kind = event.get("kind")
    if kind == "MessageEvent":
        message = event.get("llm_message", {})
        return extract_text_blocks(message.get("content", []))
    if kind == "ActionEvent":
        segments: list[str] = []
        segments.append(extract_text_blocks(event.get("thought", [])))
        action = event.get("action", {})
        if isinstance(action, dict):
            if action.get("command"):
                segments.append(str(action.get("command")))
            if action.get("path"):
                segments.append(f"Path: {action.get('path')}")
            if action.get("file_text"):
                segments.append(action.get("file_text", ""))
        return "\n\n".join(s for s in segments if s)
    if kind == "ObservationEvent":
        observation = event.get("observation", {})
        return extract_text_blocks(observation.get("content", []))
    if kind == "SystemPromptEvent":
        prompt = event.get("system_prompt", {})
        if isinstance(prompt, dict) and prompt.get("type") == "text":
            return str(prompt.get("text", ""))
    return ""


def truncate(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "\u2026"


def event_summary_rows(events: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, event in enumerate(events):
        kind = event.get("kind", "")
        source = event.get("source", "")
        preview = (
            truncate(get_event_text(event))
            if kind != "InvalidJSON"
            else event.get("error", "")
        )
        rows.append(
            {
                "#": f"{idx:03d}",
                "File": event.get("_filename", ""),
                "Kind": kind,
                "Source": source,
                "Timestamp": event.get("timestamp", ""),
                "Preview": preview,
            }
        )
    return rows


def draw_base_state(base_state: dict[str, Any]) -> None:
    if not base_state:
        st.info("No base_state.json found for this conversation.")
        return

    st.subheader("Base State")
    cols = st.columns(3)
    agent = base_state.get("agent", {})
    llm = agent.get("llm", {})
    cols[0].metric("Agent kind", agent.get("kind", "Unknown"))
    cols[1].metric("LLM model", llm.get("model", "Unknown"))
    cols[2].metric("Temperature", str(llm.get("temperature", "Unknown")))

    with st.expander("View raw base_state.json", expanded=False):
        st.json(base_state)


def create_conversation_zip(conversation_path: Path) -> bytes:
    """创建一个包含对话目录中所有文件的 zip 文件。

    Args:
        conversation_path: 对话目录的路径

    Returns:
        zip 文件的字节数
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 如果存在则添加base_state.json
        base_state_path = conversation_path / "base_state.json"
        if base_state_path.exists():
            zip_file.write(base_state_path, "base_state.json")

        # 添加事件目录中的所有事件文件
        events_dir = conversation_path / "events"
        if events_dir.exists():
            for event_file in sorted(events_dir.glob("*.json")):
                arcname = f"events/{event_file.name}"
                zip_file.write(event_file, arcname)

    buffer.seek(0)
    return buffer.getvalue()


def draw_event_detail(event: dict[str, Any]) -> None:
    meta_cols = st.columns(4)
    meta_cols[0].markdown(f"**File**\n{event.get('_filename', '—')}")
    meta_cols[1].markdown(f"**Kind**\n{event.get('kind', '—')}")
    meta_cols[2].markdown(f"**Source**\n{event.get('source', '—')}")
    meta_cols[3].markdown(f"**Timestamp**\n{event.get('timestamp', '—')}")

    text = get_event_text(event)
    if text:
        st.markdown("**Narrative**")
        st.code(text)

    if event.get("kind") == "ActionEvent" and event.get("action"):
        st.markdown("**Action Payload**")
        st.json(event.get("action"))

    if event.get("kind") == "ObservationEvent" and event.get("observation"):
        st.markdown("**Observation Payload**")
        st.json(event.get("observation"))

    st.markdown("**Raw Event JSON**")
    st.json(event)


def main() -> None:
    st.title("OpenHands Conversation Viewer")

    # 如果不存在，则在会话状态下初始化根目录
    if "root_directory" not in st.session_state:
        params = st.query_params
        default_root = DEFAULT_CONVERSATIONS_ROOT
        # 处理旧的（列表）和新的（字符串）查询参数格式
        root_from_params = params.get("root", str(default_root))
        if isinstance(root_from_params, list):
            root_from_params = (
                root_from_params[0] if root_from_params else str(default_root)
            )
        st.session_state["root_directory"] = root_from_params

    root_input = st.sidebar.text_input(
        "Conversations directory",
        value=st.session_state["root_directory"],
        help="Root folder containing OpenHands conversation dumps",
    )

    # 确保 root_input 不是 None（默认值不会发生）
    if not root_input:
        root_input = st.session_state["root_directory"]

    # 如果根输入更改则更新会话状态
    if root_input != st.session_state["root_directory"]:
        st.session_state["root_directory"] = root_input
        if not st.session_state.get("_suppress_query_update", False):
            try:
                st.session_state["_suppress_query_update"] = True
                st.query_params["root"] = root_input
            finally:
                st.session_state["_suppress_query_update"] = False

    root_path = Path(root_input).expanduser()

    if st.sidebar.button(
        "Reload conversations", help="Clear cached data and reload from disk"
    ):
        load_conversation.clear()
        get_last_event_timestamp.clear()
        rerun = getattr(st, "experimental_rerun", None)
        if callable(rerun):
            rerun()
        else:
            st.rerun()

    if not root_path.exists() or not root_path.is_dir():
        st.error(f"Directory not found: {root_path}")
        return

    directories = conversation_dirs(root_path)
    if not directories:
        st.warning("No conversation folders found in the selected directory.")
        return

    # 创建带有时间戳的选项以获得更好的用户体验
    options_with_timestamps = []
    options = []
    for directory in directories:
        timestamp = get_last_event_timestamp(str(directory))
        if timestamp:
            # 显示时间戳格式
            try:
                if "T" in timestamp:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    formatted_time = timestamp[:16]  # 如果太长则截断
                display_name = f"{directory.name} ({formatted_time})"
            except (ValueError, TypeError):
                display_name = f"{directory.name} ({timestamp[:16]})"
        else:
            display_name = f"{directory.name} (no events)"

        options_with_timestamps.append(display_name)
        options.append(directory.name)

    selected_idx = 0
    if "conversation" in st.session_state:
        try:
            selected_idx = options.index(st.session_state["conversation"])
        except ValueError:
            selected_idx = 0

    selected_display = st.sidebar.selectbox(
        "Conversation (sorted by last event)",
        options_with_timestamps,
        index=selected_idx,
        help="Conversations are sorted by their most recent event timestamp",
    )
    selected = options[options_with_timestamps.index(selected_display)]
    st.session_state["conversation"] = selected

    conversation = load_conversation(str(root_path / selected))

    # 为对话添加下载按钮
    st.sidebar.divider()
    zip_data = create_conversation_zip(conversation.path)
    st.sidebar.download_button(
        label="📥 Download Conversation as ZIP",
        data=zip_data,
        file_name=f"{selected}.zip",
        mime="application/zip",
        help="Download all conversation files as a ZIP archive",
    )

    st.caption(f"Loaded from {conversation.path}")
    draw_base_state(conversation.base_state)

    st.subheader("Events")
    events = conversation.events
    if not events:
        st.info("No events found for this conversation.")
        return

    kinds = sorted({event.get("kind", "Unknown") for event in events})
    selected_kinds = st.sidebar.multiselect(
        "Filter by event kind", kinds, default=kinds
    )

    search_term = st.sidebar.text_input("Search across events", value="")
    lowered = search_term.lower()

    filtered_events: list[dict[str, Any]] = []
    for event in events:
        if selected_kinds and event.get("kind", "Unknown") not in selected_kinds:
            continue
        if lowered:
            as_text = json.dumps(event).lower()
            if lowered not in as_text:
                continue
        filtered_events.append(event)

    st.markdown(f"Showing {len(filtered_events)} of {len(events)} events")

    summary = event_summary_rows(filtered_events)
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Event Details")

    for idx, event in enumerate(filtered_events):
        label = " · ".join(
            [
                f"{idx:03d}",
                event.get("kind", "Unknown"),
                event.get("source", "Unknown"),
            ]
        )
        with st.expander(label, expanded=False):
            draw_event_detail(event)


if __name__ == "__main__":
    main()
