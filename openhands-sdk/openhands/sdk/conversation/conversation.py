from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Self, overload

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTokenCallbackType,
    StuckDetectionThresholds,
    TraceMetadataValue,
)
from openhands.sdk.conversation.visualizer import (
    ConversationVisualizerBase,
    DefaultConversationVisualizer,
)
from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger
from openhands.sdk.plugin import PluginSource
from openhands.sdk.secret import SecretValue
from openhands.sdk.tool.client_tool import ClientToolSpec
from openhands.sdk.utils.redact import redact_url_credentials
from openhands.sdk.workspace import LocalWorkspace, RemoteWorkspace


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation
    from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation

logger = get_logger(__name__)


class Conversation:
    """用于使用 OpenHands 智能体创建对话实例的工厂类。

    该工厂根据提供的工作区类型自动创建 LocalConversation 或 RemoteConversation。
    LocalConversation 在本地运行智
    能体，
    while RemoteConversation connects to a remote agent server.

    Returns:
        如果工作区是本地，则为 LocalConversation；如果工作区为远程，则为
        RemoteConversation。

    Example:
        ```python
        from openhands.sdk import LLM, Agent, Conversation
        from openhands.sdk.plugin import PluginSource
        from pydantic import SecretStr

        llm = LLM(model="gpt-5.5", api_key=SecretStr("key"))
        agent = Agent(llm=llm, tools=[])
        conversation = Conversation(
            agent=agent,
            workspace="./workspace",
            plugins=[PluginSource(source="github:org/security-plugin", ref="v1.0")],
        )
        conversation.send_message("Hello!")
        conversation.run()
        ```
    """

    @overload
    def __new__(
        cls: type[Self],
        agent: AgentBase,
        *,
        workspace: str | Path | LocalWorkspace = "workspace/project",
        plugins: list[PluginSource] | None = None,
        persistence_dir: str | Path | None = None,
        conversation_id: ConversationID | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        hook_config: HookConfig | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: dict[str, SecretValue] | dict[str, str] | None = None,
        delete_on_close: bool = True,
        tags: dict[str, str] | None = None,
        user_id: str | None = None,
        client_tools: list[ClientToolSpec] | None = None,
        observability_metadata: dict[str, TraceMetadataValue] | None = None,
        observability_tags: list[str] | None = None,
        observability_span_name: str = "conversation",
        observability_parent_span_context: str | None = None,
    ) -> "LocalConversation": ...

    @overload
    def __new__(
        cls: type[Self],
        agent: AgentBase,
        *,
        workspace: RemoteWorkspace,
        plugins: list[PluginSource] | None = None,
        conversation_id: ConversationID | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        hook_config: HookConfig | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: dict[str, SecretValue] | dict[str, str] | None = None,
        delete_on_close: bool = True,
        tags: dict[str, str] | None = None,
        user_id: str | None = None,
        client_tools: list[ClientToolSpec] | None = None,
        observability_metadata: dict[str, TraceMetadataValue] | None = None,
        observability_tags: list[str] | None = None,
        observability_span_name: str = "conversation",
        observability_parent_span_context: str | None = None,
    ) -> "RemoteConversation": ...

    def __new__(
        cls: type[Self],
        agent: AgentBase,
        *,
        workspace: str | Path | LocalWorkspace | RemoteWorkspace = "workspace/project",
        plugins: list[PluginSource] | None = None,
        persistence_dir: str | Path | None = None,
        conversation_id: ConversationID | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        hook_config: HookConfig | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: dict[str, SecretValue] | dict[str, str] | None = None,
        delete_on_close: bool = True,
        tags: dict[str, str] | None = None,
        user_id: str | None = None,
        client_tools: list[ClientToolSpec] | None = None,
        observability_metadata: dict[str, TraceMetadataValue] | None = None,
        observability_tags: list[str] | None = None,
        observability_span_name: str = "conversation",
        observability_parent_span_context: str | None = None,
    ) -> BaseConversation:
        from openhands.sdk.conversation.impl.local_conversation import LocalConversation
        from openhands.sdk.conversation.impl.remote_conversation import (
            RemoteConversation,
        )

        if isinstance(workspace, RemoteWorkspace):
            # 对于 RemoteConversation，不应使用 persistence_dir。
            if persistence_dir is not None:
                raise ValueError(
                    "persistence_dir should not be set when using RemoteConversation"
                )

            # 通过合并多个来源构建有效的标签：
            # 1. 工作区默认标签（自动化上下文）
            # 2. 自动生成的标签（插件/技能）
            # 3. 用户提供的标签（最高优先级）
            effective_tags: dict[str, str] = {}

            # 1. 从工作区个默认标签开始
            default_tags = workspace.default_conversation_tags
            if default_tags:
                effective_tags.update(default_tags)
                logger.debug(
                    f"Merged workspace default tags: {list(default_tags.keys())}"
                )

            # 2. 从插件参数自动生成插件/技能标签
            if plugins:
                # 标签持久化逐字记录 — 掩码内联信用（${VAR} 引用保留）。
                plugin_urls = [
                    redact_url_credentials(url, preserve_placeholders=True)
                    for p in plugins
                    if (url := p.source_url)
                ]
                if plugin_urls:
                    effective_tags["plugins"] = ",".join(plugin_urls)
                    logger.debug(f"Added plugins tag with {len(plugin_urls)} plugin(s)")

            # 3. 用户提供的标签会覆盖所有内容
            if tags:
                effective_tags.update(tags)

            return RemoteConversation(
                agent=agent,
                plugins=plugins,
                conversation_id=conversation_id,
                callbacks=callbacks,
                token_callbacks=token_callbacks,
                hook_config=hook_config,
                max_iteration_per_run=max_iteration_per_run,
                stuck_detection=stuck_detection,
                stuck_detection_thresholds=stuck_detection_thresholds,
                visualizer=visualizer,
                workspace=workspace,
                secrets=secrets,
                delete_on_close=delete_on_close,
                tags=effective_tags if effective_tags else None,
                user_id=user_id,
                client_tools=client_tools,
                observability_metadata=observability_metadata,
                observability_tags=observability_tags,
                observability_span_name=observability_span_name,
                observability_parent_span_context=observability_parent_span_context,
            )

        return LocalConversation(
            agent=agent,
            plugins=plugins,
            conversation_id=conversation_id,
            callbacks=callbacks,
            token_callbacks=token_callbacks,
            hook_config=hook_config,
            max_iteration_per_run=max_iteration_per_run,
            stuck_detection=stuck_detection,
            stuck_detection_thresholds=stuck_detection_thresholds,
            visualizer=visualizer,
            workspace=workspace,
            persistence_dir=persistence_dir,
            secrets=secrets,
            delete_on_close=delete_on_close,
            tags=tags,
            user_id=user_id,
            client_tools=client_tools,
            observability_metadata=observability_metadata,
            observability_tags=observability_tags,
            observability_span_name=observability_span_name,
            observability_parent_span_context=observability_parent_span_context,
        )
