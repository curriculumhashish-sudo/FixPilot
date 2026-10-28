"""对当前任务进行分类并切换 LLM 配置文件的内置工具。

该工具读取 * 活动元配置文件 *（请参阅
:class:`~openhands.sdk.llm.meta_profile_store.MetaProfile`)，询问
``classifier_model`` 用于根据最近的对话消息对 meta-profile 进行分类，然后将对话切换到
与选择的类对应的 LLM。 当分类器没有产生可用的答
案时，工具会大声失败（返回错误观测结果），这样可以显式地和可重试地失败，而不是默默地
路由到默认模型。
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.auth.openai import create_subscription_llm_from_config
from openhands.sdk.llm.meta_profile_store import MetaProfile, MetaProfileStore
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.registry import register_tool
from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)


if TYPE_CHECKING:
    from openhands.sdk.conversation.impl.local_conversation import LocalConversation
    from openhands.sdk.conversation.state import ConversationState


logger = get_logger(__name__)

# 显示给分类器的尾随对话消息数。
_RECENT_MESSAGE_LIMIT = 6

_CLASSIFIER_SYSTEM_PREFIX = "You are a model-routing classifier."


class ClassifyAndSwitchLLMAction(Action):
    """触发当前任务的分类并切换LLM配置文件。"""

    @property
    def visualize(self) -> Text:
        content = Text()
        content.append("Classify task and switch LLM", style="bold magenta")
        return content


class ClassifyAndSwitchLLMObservation(Observation):
    """对任务进行分类并切换 LLM 配置文件的结果。"""

    chosen_class: str | None = Field(
        default=None,
        description="Description of the matched class, or None when no class "
        "matched and the tool returned an error.",
    )
    model: str | None = Field(
        default=None,
        description="Name of the LLM profile that was activated.",
    )
    active_model: str | None = Field(
        default=None,
        description="Model configured by the activated profile, when available.",
    )

    @property
    def visualize(self) -> Text:
        content = Text()
        if self.is_error:
            content.append("Failed to classify and switch LLM", style="bold red")
        else:
            content.append("Classified task and switched LLM", style="bold green")
        if self.model:
            content.append(f": {self.model}")
        if self.active_model:
            content.append(f" ({self.active_model})")
        if self.chosen_class:
            content.append("\nMatched class: ", style="bold")
            content.append(self.chosen_class)
        return content


def build_classifier_prompt(meta: MetaProfile) -> str:
    """构建列出元配置文件类的分类器系统提示词。"""
    lines = [
        _CLASSIFIER_SYSTEM_PREFIX,
        "",
        "Based on the recent conversation, pick the single category that best "
        "describes the current task.",
        "",
        "Categories:",
    ]
    for i, cls in enumerate(meta.classes, start=1):
        lines.append(f"{i}. {cls.description}")
    lines.append("")
    lines.append(
        "Respond with ONLY the number of the best matching category. "
        "If none of the categories clearly apply, respond with 0."
    )
    return "\n".join(lines)


def parse_class_index(text: str, num_classes: int) -> int:
    """将分类器回复解析为类索引。

    当未找到范围内的整数时，返回 0（无可用答案）。
    """
    match = re.search(r"-?\d+", text)
    if match is None:
        return 0
    index = int(match.group())
    if 1 <= index <= num_classes:
        return index
    return 0


def render_direct_prompt(meta: MetaProfile, instance_text: str) -> str:
    """渲染直接路由提示词主体（不带系统前缀）。

    仅替换元配置文件支持的最少占位符。 此处有意*不*在前面添加
    ``_CLASSIFIER_SYSTEM_PREFIX``，让调用方能将渲染后的正文放入
    ``user`` 消息，同时将前缀保留在 ``system`` 消息中；部分提供商（e.g。 MiniMax) 拒
    绝仅轮到 ``system`` 消息和
    ``"chat content is empty"`` 的请求。
    """
    prompt = meta.prompt_template or ""
    values = {
        "instance_text": instance_text,
        "model_table": meta.model_table or "",
    }

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return re.sub(r"{{\s*(instance_text|model_table)\s*}}", replace, prompt).strip()


def build_classifier_messages(meta: MetaProfile, transcript: str) -> list[Message]:
    """构建 ``meta`` 的分类器请求消息。

    始终返回一条 ``system`` 消息，后跟一条非空 ``user`` 消息。 诸如 MiniMax 之类的提
    供者会拒绝唯一轮到的请求
    ``system`` 消息 (``"chat content is empty"``)，因此对于两种路由模式，任务记录和渲
    染的提示词都被放置在 ``user`` 角
    色中。
    """
    if meta.prompt_template is None:
        return [
            Message(
                role="system",
                content=[TextContent(text=build_classifier_prompt(meta))],
            ),
            Message(
                role="user",
                content=[
                    TextContent(
                        text=(f"Recent conversation:\n{transcript}\n\nCategory number:")
                    )
                ],
            ),
        ]
    return [
        Message(
            role="system",
            content=[TextContent(text=_CLASSIFIER_SYSTEM_PREFIX)],
        ),
        Message(
            role="user",
            content=[TextContent(text=render_direct_prompt(meta, transcript))],
        ),
    ]


def parse_direct_model(text: str, available_models: Sequence[str]) -> str | None:
    """将直接路由分类器回复解析为保存的配置文件名称。

    预期的合同是 JSON，有一个 ``model`` 字段，但解析器还会扫描原始响应以容忍允许的模
    板名称，以容忍被包围的 JSON 或小的格式错误。 匹配不区分大小写
    ，但返回值是``available_models``中保存的规范配置文件名称。
    """
    raw = (text or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    profile_by_casefold = {model.casefold(): model for model in available_models}

    candidate = ""
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            obj = json.loads(match.group(0))
            candidate = str(obj.get("model", "")).strip()
    except Exception:  # noqa: BLE001
        candidate = ""

    if candidate:
        return profile_by_casefold.get(candidate.casefold())

    scan = raw.casefold()
    for model in sorted(available_models, key=len, reverse=True):
        if model.casefold() in scan:
            return model
    return None


def _saved_profile_names(conversation: "LocalConversation") -> list[str]:
    """返回已保存的不带 ``.json`` 后缀的 LLM 配置文件名称。"""
    return [name.removesuffix(".json") for name in conversation._profile_store.list()]


def _recent_messages_text(
    conversation: "LocalConversation", limit: int = _RECENT_MESSAGE_LIMIT
) -> str:
    """返回最后 ``limit`` 条对话消息的记录。

    故意只包含 ``MessageEvent``：用户/助理消息是分类器需要的任务信号。 工具调用事件/
    观察事件（输出）是故意排除的——它们是噪声，可以很大，而且不能比
    周围的消息更清楚地描述任务。
    """
    from openhands.sdk.event.llm_convertible.message import MessageEvent
    from openhands.sdk.llm import content_to_str

    messages: list[str] = []
    for event in conversation.state.events:
        if not isinstance(event, MessageEvent):
            continue
        text = "\n".join(content_to_str(event.llm_message.content)).strip()
        if text:
            messages.append(f"{event.source}: {text}")
    return "\n".join(messages[-limit:])


class ClassifyAndSwitchLLMExecutor(ToolExecutor):
    def __init__(
        self,
        meta_profile_store: MetaProfileStore,
        active_meta_profile: str | None = None,
        meta_profile: MetaProfile | None = None,
        meta_profile_llms: dict[str, LLM] | None = None,
    ) -> None:
        # 应在调用时延迟解析元配置，而不是在构造时解析；这样 ~/.openhands/meta-profiles
        # 下的文件缺失或改名时，只会产生工具错误，不会导致对话启动失败。
        #
        self._store = meta_profile_store
        self._active_meta_profile = active_meta_profile
        self._meta_profile = meta_profile
        self._meta_profile_llms = meta_profile_llms or {}

    def _resolve_meta_profile(self) -> MetaProfile:
        """解析活动元配置文件。

        当 ``active_meta_profile`` 名称已设置，商店是权威的（按名称加载），因此内联
        ``meta_profile`` 在名称更改后，blo
        b和存储库不能 diverge``PATCH /api/settings``) 或文件覆盖
        ``POST /api/meta-profiles/{name}``). 只有当商店无法解析名称时，才会咨询内联
        blob e.g. 其临时文件系统没有元配
        置文件存储的云运行时。 如果未设置名称，则返回到内联 blob（如果存在），否则返
        回到存储中的第一个可用元配置文件。

        Raises:
            FileNotFoundError: 如果没有meta-profile可以解决。
            ValueError: 如果解析的元配置文件无效。
        """
        name = self._active_meta_profile
        if name:
            try:
                return self._store.load(name)
            except FileNotFoundError:
                # 商店无法解析名称 (e.g. 磁盘上没有元配置文件存储的云运行时）； 落入内联
                #  blob。
                #
                pass

        if self._meta_profile is not None:
            return self._meta_profile

        if name:
            available = self._store.list()
            raise FileNotFoundError(
                f"Active meta-profile '{name}' could not be resolved from the "
                "store or inline configuration. "
                f"Available meta-profiles: {', '.join(available) or 'none'}"
            )

        available = self._store.list()
        if not available:
            raise FileNotFoundError(
                "No meta-profile is active and none are available in the "
                "meta-profile store."
            )
        # ``list()`` 按字母顺序排序，因此这是按字母顺序排列的第一个元配置文件，而不是最
        # 近保存的元配置文件。
        #
        name = available[0]
        logger.info(
            "No active meta-profile set; falling back to first available: %r",
            name,
        )
        return self._store.load(name)

    def __call__(
        self,
        action: ClassifyAndSwitchLLMAction,  # noqa: ARG002
        conversation: "LocalConversation | None" = None,
    ) -> ClassifyAndSwitchLLMObservation:
        from openhands.sdk.llm import content_to_str

        if conversation is None:
            return ClassifyAndSwitchLLMObservation.from_text(
                text="Cannot classify and switch LLM without an active conversation.",
                is_error=True,
            )

        try:
            meta = self._resolve_meta_profile()
        except (FileNotFoundError, ValueError) as exc:
            return ClassifyAndSwitchLLMObservation.from_text(
                text=f"Failed to resolve the active meta-profile: {exc}",
                is_error=True,
            )
        # 1) 加载分类器 LLM（已保存的配置文件），尊重 at-REST 密码，并将其注册到对话的
        # LLM 注册表中的稳定使用 ID 下。 注册是使分类器完成的标记/成本流进入
        # ``conversation.conversation_stats``并计入``max_budget_per_run``——调用未注册的
        # LLM会超出预算（与``ask-agent-llm``模式一致）。 按使用 ID 进行缓存意味着重复的
        # 路由调用会重用一个指标存储桶。
        #
        usage_id = f"classifier:{meta.classifier_model}"
        try:
            classifier_llm = conversation.llm_registry.get(usage_id)
        except KeyError:
            try:
                loaded = self._meta_profile_llms.get(meta.classifier_model)
                if loaded is None:
                    loaded = conversation._profile_store.load(
                        meta.classifier_model, cipher=conversation._cipher
                    )
            except (FileNotFoundError, ValueError) as exc:
                return ClassifyAndSwitchLLMObservation.from_text(
                    text=(
                        f"Failed to load classifier profile "
                        f"'{meta.classifier_model}': {exc}"
                    ),
                    is_error=True,
                )
            classifier_llm = create_subscription_llm_from_config(
                loaded.model_copy(update={"usage_id": usage_id})
            )
            conversation.llm_registry.add(classifier_llm)

        # 2) 单个分类器调用最近的对话。
        transcript = _recent_messages_text(conversation) or "(no messages yet)"
        messages = build_classifier_messages(meta, transcript)
        try:
            response = classifier_llm.completion(
                messages,
                call_context=conversation.get_llm_call_context(),
            )
        except Exception as exc:
            return ClassifyAndSwitchLLMObservation.from_text(
                text=f"Classifier call failed: {type(exc).__name__}: {exc}",
                is_error=True,
            )

        reply = "\n".join(content_to_str(response.message.content))

        # 3) 解析目标配置文件（选择的类或直接模型）。 无静默回退方案：当分类器没有产生可
        # 用答案时，工具返回错误观测结果，因此未命中是可见的/可重试的。
        #
        if meta.prompt_template is None:
            index = parse_class_index(reply, len(meta.classes))
            if index == 0:
                return ClassifyAndSwitchLLMObservation.from_text(
                    text=(
                        "Classifier did not pick a valid category "
                        f"(reply: {reply!r}); refusing to silently route to a "
                        "default. Retry the tool or fix the meta-profile classes."
                    ),
                    is_error=True,
                )
            chosen = meta.classes[index - 1]
            target_profile = chosen.model
            chosen_class = chosen.description
        else:
            target_profile = parse_direct_model(
                reply,
                sorted(
                    set(_saved_profile_names(conversation))
                    | set(self._meta_profile_llms)
                ),
            )
            if target_profile is None:
                return ClassifyAndSwitchLLMObservation.from_text(
                    text=(
                        "Classifier reply did not resolve to a saved LLM profile "
                        f"(reply: {reply!r}); refusing to silently route to a "
                        "default. Retry the tool or extend the model table."
                    ),
                    is_error=True,
                )
            chosen_class = f"model: {target_profile}"

        # 4) 将对话切换到目标配置文件。
        try:
            inline_target = self._meta_profile_llms.get(target_profile)
            if inline_target is None:
                conversation.switch_profile(target_profile)
            else:
                conversation.switch_llm(
                    inline_target.model_copy(
                        update={"usage_id": f"profile:{target_profile}"}
                    )
                )
        except FileNotFoundError:
            return ClassifyAndSwitchLLMObservation.from_text(
                text=f"Target LLM profile '{target_profile}' was not found.",
                is_error=True,
                model=target_profile,
                chosen_class=chosen_class,
            )
        except Exception as exc:
            return ClassifyAndSwitchLLMObservation.from_text(
                text=(
                    f"Failed to switch to LLM profile '{target_profile}': "
                    f"{type(exc).__name__}: {exc}"
                ),
                is_error=True,
                model=target_profile,
                chosen_class=chosen_class,
            )

        active_model = conversation.agent.llm.model
        label = chosen_class or target_profile
        return ClassifyAndSwitchLLMObservation.from_text(
            text=(
                f"Classified task as '{label}' and switched to LLM profile "
                f"'{target_profile}' (model '{active_model}'). "
                "Future agent steps will use this profile."
            ),
            chosen_class=chosen_class,
            model=target_profile,
            active_model=active_model,
        )


_DESCRIPTION = (
    "Classify the current task and switch this conversation to the most "
    "suitable saved LLM profile.\n\n"
    "Use this near the start of a task (or when the task changes) to route "
    "the work to the best model. A classifier model inspects the recent "
    "conversation and picks a category from the active meta-profile; the "
    "conversation then switches to that category's LLM profile. The switch "
    "takes effect on the next LLM call."
)


class ClassifyAndSwitchLLMTool(
    ToolDefinition[ClassifyAndSwitchLLMAction, ClassifyAndSwitchLLMObservation]
):
    """对任务进行分类并切换到元配置文件的 LLM 的工具。"""

    name = "route_task_to_model"
    user_selectable: ClassVar[bool] = False

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState | None" = None,  # noqa: ARG003
        active_meta_profile: str | None = None,
        meta_profile: MetaProfile | Mapping[str, object] | None = None,
        meta_profile_llms: Mapping[str, LLM | Mapping[str, object]] | None = None,
        meta_profile_store: MetaProfileStore | None = None,
        **params,
    ) -> Sequence[Self]:
        if params:
            raise ValueError(
                "ClassifyAndSwitchLLMTool only accepts 'active_meta_profile', "
                "'meta_profile', 'meta_profile_llms', and 'meta_profile_store'."
            )

        # 元配置文件解析被推迟到调用时间（参见 ClassifyAndSwitchLLMExecutor），因此用户
        # 管理的文件
        # ~/.openhands/meta-profiles 无法中断对话启动； 缺失/无效的轮廓会显示为工具错误
        # 。
        #
        store = meta_profile_store or MetaProfileStore()
        inline_meta_profile = (
            MetaProfile.model_validate(meta_profile)
            if meta_profile is not None
            else None
        )
        inline_llms = {
            name: LLM.model_validate(llm)
            for name, llm in (meta_profile_llms or {}).items()
        }
        return [
            cls(
                description=_DESCRIPTION,
                action_type=ClassifyAndSwitchLLMAction,
                observation_type=ClassifyAndSwitchLLMObservation,
                executor=ClassifyAndSwitchLLMExecutor(
                    store, active_meta_profile, inline_meta_profile, inline_llms
                ),
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]


# 已注册，因此可以从带有以下内容的 ``Tool`` 规范中解析
# ``active_meta_profile`` param（内置``include_default_tools``路径不能传递params）。
#
register_tool(ClassifyAndSwitchLLMTool.__name__, ClassifyAndSwitchLLMTool)
