"""Tom 咨询工具的执行者。"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.events_list_base import EventsListBase
from openhands.sdk.event import (
    ActionEvent,
    LLMConvertibleEvent,
    ObservationEvent,
)
from openhands.sdk.io import FileStore
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import Observation, ToolExecutor
from openhands.tools.tom_consult.definition import (
    ConsultTomAction,
    ConsultTomObservation,
    SleeptimeComputeAction,
    SleeptimeComputeObservation,
)


if TYPE_CHECKING:
    from tom_swe.tom_agent import ToMAgent

    from openhands.sdk.conversation.base import BaseConversation

logger = get_logger(__name__)


class TomConsultExecutor(
    ToolExecutor[ConsultTomAction | SleeptimeComputeAction, Observation]
):
    """咨询汤姆智能体的执行人。

    该执行器包装了 tom-swe 包，以提供用于理解用户意图和偏好的心理理论功能。
    """

    def __init__(
        self,
        file_store: FileStore,
        enable_rag: bool = True,
        llm_model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        """初始化Tom咨询执行者。

        Args:
            file_store: 用于访问用户建模数据的文件存储
            enable_rag: 是否在Tom智能体中启用RAG
            llm_model: LLM 用于汤姆的模型智能体
            api_key: API 汤姆智能体的 LLM 的钥匙
            api_base: 汤姆智能体的 LLM 的底座 URL
        """
        self.file_store: FileStore = file_store
        self.enable_rag: bool = enable_rag
        self.llm_model: str | None = llm_model
        self.api_key: str | None = api_key
        self.api_base: str | None = api_base
        self._tom_agent: ToMAgent | None = None
        self.user_id: str = ""
        self.conversations_dir: str = "conversations"

    def _get_tom_agent(self) -> "ToMAgent":
        """Tom 智能体的延迟初始化。"""
        if self._tom_agent is None:
            from typing import cast

            from tom_swe.tom_agent import create_tom_agent

            self._tom_agent = create_tom_agent(
                file_store=cast(Any, self.file_store),
                enable_rag=self.enable_rag,
                llm_model=self.llm_model,
                api_key=self.api_key,
                api_base=self.api_base,
            )
        logger.info("Tom agent initialized successfully")
        return self._tom_agent

    def __call__(
        self,
        action: ConsultTomAction | SleeptimeComputeAction,
        conversation: "BaseConversation | None" = None,
    ) -> ConsultTomObservation | SleeptimeComputeObservation:
        """执行汤姆操作。

        Args:
            action: 要执行的操作（咨询或睡眠时间计算）
            conversation: 用于访问状态和历史记录的对话上下文

        Returns:
            观测结果有结果
        """
        if isinstance(action, SleeptimeComputeAction):
            return self._sleeptime_compute(conversation)
        else:
            return self._consult_tom(action, conversation)

    def _format_events(
        self,
        event_log: EventLog | EventsListBase,
        conversation: "BaseConversation | None" = None,
    ) -> list[dict[str, Any]]:
        """将事件格式化为 Tom 智能体的消息。

        Args:
            event_log: 要格式化的事件
            conversation: 用于 LLM 格式的可选对话

        Returns:
            格式化消息列表（跳过系统消息）
        """
        events = list(event_log)
        # 仅获取已完成的动作-观测结果对
        matched_action_ids = {
            obs_event.action_id
            for obs_event in events
            if isinstance(obs_event, ObservationEvent)
        }

        llm_convertible_events = [
            e
            for e in events
            if isinstance(e, LLMConvertibleEvent)
            and (not isinstance(e, ActionEvent) or e.id in matched_action_ids)
        ]

        if not llm_convertible_events:
            return []

        # 转换为消息
        messages = LLMConvertibleEvent.events_to_messages(llm_convertible_events)

        # 格式化消息 - 如果可用，请使用对话的 LLM，否则手动格式化
        if conversation is not None:
            # 跳过系统消息（第一条消息）
            return conversation.state.agent.llm.format_messages_for_llm(messages)[1:]
        else:
            # 如果没有对话，则直接从事件中格式化消息
            from openhands.sdk.llm import TextContent

            formatted_messages = []
            for msg in messages:
                if msg.role != "system":  # 跳过系统消息
                    text_contents = [
                        {"text": c.text}
                        for c in msg.content
                        if isinstance(c, TextContent)
                    ]
                    if text_contents:
                        formatted_messages.append(
                            {"role": msg.role, "content": text_contents}
                        )
            return formatted_messages

    def _consult_tom(
        self, action: ConsultTomAction, conversation: "BaseConversation | None" = None
    ) -> ConsultTomObservation:
        """执行汤姆咨询。

        Args:
            action: 查询详情的咨询动作
            conversation: 用于访问历史记录的对话上下文

        Returns:
            ConsultTomObservation 根据汤姆的建议
        """
        try:
            tom_agent = self._get_tom_agent()

            # 使用原始实现中的精确格式构建查询文本
            if action.use_user_message:
                query_text = f"I am SWE agent. {action.reason} I need to consult ToM agent about the user's message: [USER MESSAGE PLACEHOLDER]"  # noqa: E501
            elif action.custom_query:
                query_text = f"I am SWE agent. {action.reason} I need to consult ToM agent: {action.custom_query}"  # noqa: E501
            else:
                logger.warning("⚠️ Tom: No query specified for consultation")
                return ConsultTomObservation(
                    suggestions="[CRITICAL] Tom agent cannot provide consultation for this user message. Do not consult ToM agent again for this message and use other actions instead."  # noqa: E501
                )

            # 获取对话历史记录（如果有）
            formatted_messages = []
            if conversation is not None:
                formatted_messages = self._format_events(
                    conversation.state.events, conversation
                )

                # 获取查询文本的最后一条用户消息
                if formatted_messages:
                    last_user_message = [
                        m for m in formatted_messages if m["role"] == "user"
                    ][-1]
                    query_text = query_text.replace(
                        "[USER MESSAGE PLACEHOLDER]",
                        last_user_message["content"][0]["text"],
                    )

                    logger.info(
                        f"Consulting Tom agent with "
                        f"{len(formatted_messages)} history messages"
                    )

            logger.info(f"Consulting Tom agent: {query_text[:100]}...")
            result = tom_agent.give_suggestions(
                user_id=self.user_id,
                query=query_text,
                formatted_messages=formatted_messages,
            )

            if result and hasattr(result, "suggestions"):
                logger.info(
                    "✅ Tom: Requesting observation update with consultation result"
                )

                # 响应的格式与原始实现完全相同
                query_description = action.custom_query or "the user's message"
                formatted_response = (
                    f"{action.reason}\n"
                    f"I need to consult Tom agent about {query_description}\n\n"
                    "[Starting consultation with Tom agent...]\n"
                    f"{result.suggestions}\n\n"
                    "[Finished consulting with ToM Agent...]"
                )

                return ConsultTomObservation(
                    suggestions=formatted_response,
                    confidence=getattr(result, "confidence", None),
                    reasoning=getattr(result, "reasoning", None),
                )
            else:
                logger.warning("⚠️ Tom: No consultation result received")
                return ConsultTomObservation(
                    suggestions="[CRITICAL] Tom agent cannot provide consultation for this user message. Do not consult ToM agent again for this message and use other actions instead."  # noqa: E501
                )

        except Exception as e:
            logger.error(f"❌ Tom: Error in consultation: {e}")
            return ConsultTomObservation(
                suggestions="[CRITICAL] Tom agent cannot provide consultation for this user message. Do not consult ToM agent again for this message and use other actions instead."  # noqa: E501
            )

    def _sleeptime_compute(
        self, conversation: "BaseConversation | None" = None
    ) -> SleeptimeComputeObservation:
        """执行睡眠时间计算以索引对话以进行用户建模。

        这会处理文件存储中所有未处理的对话，类似于 OpenHands 实现。

        Args:
            conversation: 对话上下文（用于 LLM 格式）

        Returns:
            SleeptimeComputeObservation 带有索引结果
        """
        tom_agent = self._get_tom_agent()

        logger.info("🔄 Tom: Starting sleeptime compute")

        session_paths = self.file_store.list(self.conversations_dir)
        all_sessions = [
            Path(path).name
            for path in session_paths
            if not Path(path).name.startswith(".")
        ]

        if not all_sessions:
            logger.info("📭 Tom: No conversation sessions found")
            return SleeptimeComputeObservation(
                message="No conversation sessions found", sessions_processed=0
            )

        # 加载处理历史记录以查找未处理的会话
        processing_history = self._load_processing_history()

        # 查找需要处理的会话
        sessions_to_process = []
        for session_id in all_sessions:
            events_dir = f"{self.conversations_dir}/{session_id}/events"
            event_files = self.file_store.list(events_dir)  # type: ignore
            if not event_files:
                continue

            current_event_count = len(event_files)

            # 检查是否需要处理（新的或有新的事件）
            if session_id not in processing_history:
                sessions_to_process.append(session_id)
                logger.info(f"📋 Tom: Session {session_id} needs processing (new)")
            elif current_event_count > processing_history[session_id].get(
                "last_event_count", 0
            ):
                sessions_to_process.append(session_id)
                logger.info(
                    f"📋 Tom: Session {session_id} has new events "
                    f"({current_event_count} events)"
                )

        if not sessions_to_process:
            logger.info("📭 Tom: No sessions need processing")
            return SleeptimeComputeObservation(
                message="All conversations already indexed", sessions_processed=0
            )

        logger.info(f"📊 Tom: Found {len(sessions_to_process)} sessions to process")
        # 收集每个对话的会话数据
        sessions_data = []
        for session_id in sessions_to_process:
            session_data = self._extract_session_data(session_id, conversation)
            if session_data:
                sessions_data.append(session_data)
        if not sessions_data:
            logger.info("📭 Tom: No valid session data extracted")
            return SleeptimeComputeObservation(
                message="No valid conversations to index", sessions_processed=0
            )

        logger.info(
            f"📊 Tom: Extracted {len(sessions_data)} sessions, calling Tom agent"
        )
        # 致电 sleeptime_compute
        tom_agent.sleeptime_compute(
            sessions_data=sessions_data,
            user_id=self.user_id,
        )

        # 更新处理历史记录
        self._save_processing_history(sessions_to_process)

        logger.info(f"✅ Tom: Successfully indexed {len(sessions_data)} conversations")
        return SleeptimeComputeObservation(
            message=f"Indexed {len(sessions_data)} conversations for user modeling",  # noqa: E501
            sessions_processed=len(sessions_data),
        )

    def _extract_session_data(
        self, session_id: str, conversation: "BaseConversation | None"
    ) -> dict[str, Any] | None:
        """从对话目录中提取会话数据。"""

        # 使用 file_store 从会话加载事件
        events_dir = f"{self.conversations_dir}/{session_id}/events"
        events = EventLog(self.file_store, events_dir)

        # 将事件格式化为消息
        formatted_messages = self._format_events(events, conversation)
        if not formatted_messages:
            return None

        # 转换为 tom-swe 格式
        conversation_messages = []
        for msg in formatted_messages:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                text_parts = []
                if isinstance(msg["content"], list):
                    for content in msg["content"]:
                        if isinstance(content, dict) and "text" in content:
                            text_parts.append(content["text"])
                if text_parts:
                    conversation_messages.append(
                        {"role": msg["role"], "content": "\n".join(text_parts)}
                    )

        if not conversation_messages:
            return None

        return {
            "session_id": session_id,
            "start_time": events[0].timestamp if events else "",  # type: ignore
            "end_time": events[-1].timestamp if events else "",  # type: ignore
            "event_count": len(events),
            "message_count": len(conversation_messages),
            "conversation_messages": conversation_messages,
        }

    def _load_processing_history(self) -> dict[str, Any]:
        """加载该用户的处理历史记录。"""
        try:
            from tom_swe.memory.locations import get_usermodeling_dir

            history_file = f"{get_usermodeling_dir(self.user_id)}/processed_sessions_timestamps.json"  # noqa: E501
            content = self.file_store.read(history_file)
            return json.loads(content)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.debug(f"Could not load processing history: {e}")
            return {}

    def _save_processing_history(self, session_ids: list[str]) -> None:
        """保存已处理会话的处理历史记录。"""
        try:
            from tom_swe.memory.locations import get_usermodeling_dir

            history = self._load_processing_history()
            timestamp = datetime.now().isoformat()

            for session_id in session_ids:
                events_dir = f"{self.conversations_dir}/{session_id}/events"
                try:
                    event_files = self.file_store.list(events_dir)
                    event_count = len(event_files)
                except Exception:
                    event_count = 0

                history[session_id] = {
                    "processed_at": timestamp,
                    "last_event_count": event_count,
                }

            history_file = f"{get_usermodeling_dir(self.user_id)}/processed_sessions_timestamps.json"  # noqa: E501

            self.file_store.write(history_file, json.dumps(history, indent=2))
            logger.info(
                f"📝 Tom: Updated processing history for {len(session_ids)} sessions"
            )  # noqa: E501
        except Exception as e:
            logger.error(f"Failed to save processing history: {e}")
