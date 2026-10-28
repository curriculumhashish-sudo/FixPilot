"""用于 Web 自动化的浏览器使用工具实现。"""

import base64
import hashlib
import logging
import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, Self

from pydantic import Field

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)
from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT, maybe_truncate
from openhands.sdk.utils.masking import SkipSecretMasking


_logger = logging.getLogger(__name__)

# 延迟导入以避免模块导入期间挂起
if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState
    from openhands.tools.browser_use.impl import BrowserToolExecutor


# 保存浏览器会话记录的目录
BROWSER_RECORDING_OUTPUT_DIR = os.path.join(".agent_tmp", "browser_observations")

# 将 Base64 前缀映射到 MIME 类型以进行图像检测
BASE64_IMAGE_PREFIXES = {
    "/9j/": "image/jpeg",
    "iVBORw0KGgo": "image/png",
    "R0lGODlh": "image/gif",
    "UklGR": "image/webp",
}


def detect_image_mime_type(base64_data: str) -> str:
    """从 Base64 编码的图像数据中检测 MIME 类型。

    Args:
        base64_data: Base64 编码的图像数据

    Returns:
        检测到 MIME 类型，如果未检测到，则默认为“image/png”
    """
    for prefix, mime_type in BASE64_IMAGE_PREFIXES.items():
        if base64_data.startswith(prefix):
            return mime_type
    return "image/png"


class BrowserObservation(Observation):
    """浏览器操作的基址观测结果。"""

    screenshot_data: Annotated[str | None, SkipSecretMasking()] = Field(
        default=None,
        description="Base64 screenshot data if available",
    )
    full_output_save_dir: str | None = Field(
        default=None,
        description="Directory where full output files are saved",
    )

    def _save_screenshot(self, base64_data: str, save_dir: str) -> str | None:
        try:
            save_dir_path = Path(save_dir)
            save_dir_path.mkdir(parents=True, exist_ok=True)

            mime_type = detect_image_mime_type(base64_data)
            ext = mime_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"

            # 生成文件名的哈希值
            content_hash = hashlib.sha256(base64_data.encode("utf-8")).hexdigest()[:8]
            filename = f"browser_screenshot_{content_hash}.{ext}"
            file_path = save_dir_path / filename

            if not file_path.exists():
                image_data = base64.b64decode(base64_data)
                file_path.write_bytes(image_data)

            return str(file_path)
        except Exception:
            return None

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        llm_content: list[TextContent | ImageContent] = []

        # 如果 is_error 为 True，则添加错误消息
        if self.is_error:
            llm_content.append(TextContent(text=self.ERROR_MESSAGE_HEADER))

        # 获取文本内容并根据需要截断
        content_text = self.text
        if content_text:
            llm_content.append(
                TextContent(
                    text=maybe_truncate(
                        content=content_text,
                        truncate_after=DEFAULT_TEXT_CONTENT_LIMIT,
                        save_dir=self.full_output_save_dir,
                        tool_prefix="browser",
                    )
                )
            )

        if self.screenshot_data:
            mime_type = detect_image_mime_type(self.screenshot_data)

            # 如果目录可用，则保存屏幕截图
            if self.full_output_save_dir:
                saved_path = self._save_screenshot(
                    self.screenshot_data, self.full_output_save_dir
                )
                if saved_path:
                    llm_content.append(
                        TextContent(text=f"Screenshot saved to: {saved_path}")
                    )

            # 将 ImageContent 的 Base64 转换为数据 URL 格式
            data_url = f"data:{mime_type};base64,{self.screenshot_data}"
            llm_content.append(ImageContent(image_urls=[data_url]))

        return llm_content


# ============================================
# 基本浏览器操作
# ============================================
class BrowserAction(Action):
    """所有浏览器操作的基类。

    该基类充当所有与浏览器相关的操作的父类，从而启用正确的类型层次结构并消除对联合类
    型的需要。
    """

    pass


# ============================================
# `go_to_url`
# ============================================
class BrowserNavigateAction(BrowserAction):
    """模式用于浏览器导航。"""

    url: str = Field(description="The URL to navigate to")
    new_tab: bool = Field(
        default=False, description="Whether to open in a new tab. Default: False"
    )


BROWSER_NAVIGATE_DESCRIPTION = """Navigate to a URL in the browser.

This tool allows you to navigate to any web page. You can optionally open the URL in a new tab.

Parameters:
- url: The URL to navigate to (required)
- new_tab: Whether to open in a new tab (optional, default: False)

Examples:
- Navigate to Google: url="https://www.google.com"
- Open GitHub in new tab: url="https://github.com", new_tab=True
"""  # noqa: E501


class BrowserNavigateTool(ToolDefinition[BrowserNavigateAction, BrowserObservation]):
    """浏览器导航工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_NAVIGATE_DESCRIPTION,
                action_type=BrowserNavigateAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_navigate",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_click`
# ============================================
class BrowserClickAction(BrowserAction):
    """模式用于点击元素。"""

    index: int = Field(
        ge=0, description="The index of the element to click (from browser_get_state)"
    )
    new_tab: bool = Field(
        default=False,
        description="Whether to open any resulting navigation in a new tab. Default: False",  # noqa: E501
    )


BROWSER_CLICK_DESCRIPTION = """Click an element on the page by its index.

Use this tool to click on interactive elements like buttons, links, or form controls. 
The index comes from the browser_get_state tool output.

Parameters:
- index: The index of the element to click (from browser_get_state)
- new_tab: Whether to open any resulting navigation in a new tab (optional)

Important: Only use indices that appear in your current browser_get_state output.
"""  # noqa: E501


class BrowserClickTool(ToolDefinition[BrowserClickAction, BrowserObservation]):
    """用于单击浏览器元素的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_CLICK_DESCRIPTION,
                action_type=BrowserClickAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_click",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_type`
# ============================================
class BrowserTypeAction(BrowserAction):
    """模式用于将文本输入到元素中。"""

    index: int = Field(
        ge=0, description="The index of the input element (from browser_get_state)"
    )
    text: str = Field(description="The text to type")


BROWSER_TYPE_DESCRIPTION = """Type text into an input field.

Use this tool to enter text into form fields, search boxes, or other text input elements.
The index comes from the browser_get_state tool output.

Parameters:
- index: The index of the input element (from browser_get_state)
- text: The text to type

Important: Only use indices that appear in your current browser_get_state output.
"""  # noqa: E501


class BrowserTypeTool(ToolDefinition[BrowserTypeAction, BrowserObservation]):
    """用于在浏览器元素中输入文本的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_TYPE_DESCRIPTION,
                action_type=BrowserTypeAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_type",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_get_state`
# ============================================
class BrowserGetStateAction(BrowserAction):
    """模式用于获取浏览器状态。"""

    include_screenshot: bool = Field(
        default=False,
        description="Whether to include a screenshot of the current page. Default: False",  # noqa: E501
    )


BROWSER_GET_STATE_DESCRIPTION = """Get the current state of the page including all interactive elements.

This tool returns the current page content with numbered interactive elements that you can 
click or type into. Use this frequently to understand what's available on the page.

Parameters:
- include_screenshot: Whether to include a screenshot (optional, default: False)
"""  # noqa: E501


class BrowserGetStateTool(ToolDefinition[BrowserGetStateAction, BrowserObservation]):
    """获取浏览器状态的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_GET_STATE_DESCRIPTION,
                action_type=BrowserGetStateAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_get_state",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_get_content`
# ============================================
class BrowserGetContentAction(BrowserAction):
    """模式用于获取Markdown中的页面内容。"""

    extract_links: bool = Field(
        default=False,
        description="Whether to include links in the content (default: False)",
    )
    start_from_char: int = Field(
        default=0,
        ge=0,
        description="Character index to start from in the page content (default: 0)",
    )


BROWSER_GET_CONTENT_DESCRIPTION = """Extract the main content of the current page in clean markdown format. It has been filtered to remove noise and advertising content.

If the content was truncated and you need more information, use start_from_char parameter to continue from where truncation occurred.
"""  # noqa: E501


class BrowserGetContentTool(
    ToolDefinition[BrowserGetContentAction, BrowserObservation]
):
    """用于获取Markdown中页面内容的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_GET_CONTENT_DESCRIPTION,
                action_type=BrowserGetContentAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_get_content",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_scroll`
# ============================================
class BrowserScrollAction(BrowserAction):
    """模式用于滚动页面。"""

    direction: Literal["up", "down"] = Field(
        default="down",
        description="Direction to scroll. Options: 'up', 'down'. Default: 'down'",
    )


BROWSER_SCROLL_DESCRIPTION = """Scroll the page up or down.

Use this tool to scroll through page content when elements are not visible or when you need
to see more content.

Parameters:
- direction: Direction to scroll - "up" or "down" (optional, default: "down")
"""  # noqa: E501


class BrowserScrollTool(ToolDefinition[BrowserScrollAction, BrowserObservation]):
    """用于滚动浏览器页面的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_SCROLL_DESCRIPTION,
                action_type=BrowserScrollAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_scroll",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_go_back`
# ============================================
class BrowserGoBackAction(BrowserAction):
    """模式用于返回浏览器历史记录。"""

    pass


BROWSER_GO_BACK_DESCRIPTION = """Go back to the previous page in browser history.

Use this tool to navigate back to the previously visited page, similar to clicking the 
browser's back button.
"""  # noqa: E501


class BrowserGoBackTool(ToolDefinition[BrowserGoBackAction, BrowserObservation]):
    """用于返回浏览器历史记录的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_GO_BACK_DESCRIPTION,
                action_type=BrowserGoBackAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_go_back",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_list_tabs`
# ============================================
class BrowserListTabsAction(BrowserAction):
    """模式用于列出浏览器选项卡。"""

    pass


BROWSER_LIST_TABS_DESCRIPTION = """List all open browser tabs.

This tool shows all currently open tabs with their IDs, titles, and URLs. Use the tab IDs
with browser_switch_tab or browser_close_tab.
"""  # noqa: E501


class BrowserListTabsTool(ToolDefinition[BrowserListTabsAction, BrowserObservation]):
    """用于列出浏览器选项卡的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_LIST_TABS_DESCRIPTION,
                action_type=BrowserListTabsAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_list_tabs",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_switch_tab`
# ============================================
class BrowserSwitchTabAction(BrowserAction):
    """模式用于切换浏览器选项卡。"""

    tab_id: str = Field(
        description="4 Character Tab ID of the tab to switch"
        + " to (from browser_list_tabs)"
    )


BROWSER_SWITCH_TAB_DESCRIPTION = """Switch to a different browser tab.

Use this tool to switch between open tabs. Get the tab_id from browser_list_tabs.

Parameters:
- tab_id: 4 Character Tab ID of the tab to switch to
"""


class BrowserSwitchTabTool(ToolDefinition[BrowserSwitchTabAction, BrowserObservation]):
    """用于切换浏览器选项卡的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_SWITCH_TAB_DESCRIPTION,
                action_type=BrowserSwitchTabAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_switch_tab",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_close_tab`
# ============================================
class BrowserCloseTabAction(BrowserAction):
    """模式用于关闭浏览器选项卡。"""

    tab_id: str = Field(
        description="4 Character Tab ID of the tab to close (from browser_list_tabs)"
    )


BROWSER_CLOSE_TAB_DESCRIPTION = """Close a specific browser tab.

Use this tool to close tabs you no longer need. Get the tab_id from browser_list_tabs.

Parameters:
- tab_id: 4 Character Tab ID of the tab to close
"""


class BrowserCloseTabTool(ToolDefinition[BrowserCloseTabAction, BrowserObservation]):
    """用于关闭浏览器选项卡的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_CLOSE_TAB_DESCRIPTION,
                action_type=BrowserCloseTabAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_close_tab",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_get_storage`
# ============================================
class BrowserGetStorageAction(BrowserAction):
    """模式用于获取浏览器存储（cookie、本地存储、会话存储）。"""

    pass


BROWSER_GET_STORAGE_DESCRIPTION = """Get browser storage data including cookies,
local storage, and session storage.

This tool extracts all cookies and storage data from the current browser session.
Useful for debugging, session management, or extracting authentication tokens.
"""


class BrowserGetStorageTool(
    ToolDefinition[BrowserGetStorageAction, BrowserObservation]
):
    """用于获取浏览器存储空间的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_GET_STORAGE_DESCRIPTION,
                action_type=BrowserGetStorageAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_get_storage",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_set_storage`
# ============================================
class BrowserSetStorageAction(BrowserAction):
    """模式用于设置浏览器存储（cookie、本地存储、会话存储）。"""

    storage_state: dict = Field(
        description="Storage state dictionary containing 'cookies' and 'origins' (from browser_get_storage)"  # noqa: E501
    )


BROWSER_SET_STORAGE_DESCRIPTION = """Set browser storage data including cookies,
local storage, and session storage.

This tool allows you to restore or set the browser's storage state. You can use the
output from browser_get_storage to restore a previous session.

Parameters:
- storage_state: A dictionary containing 'cookies' and 'origins'.
  - cookies: List of cookie objects
  - origins: List of origin objects containing 'localStorage' and 'sessionStorage'
"""


class BrowserSetStorageTool(
    ToolDefinition[BrowserSetStorageAction, BrowserObservation]
):
    """用于设置浏览器存储的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_SET_STORAGE_DESCRIPTION,
                action_type=BrowserSetStorageAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_set_storage",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_start_recording`
# ============================================
class BrowserStartRecordingAction(BrowserAction):
    """模式用于启动浏览器会话记录。"""

    pass


BROWSER_START_RECORDING_DESCRIPTION = f"""Start recording the browser session.

This tool starts recording all browser interactions using rrweb. The recording
captures DOM mutations, mouse movements, clicks, scrolls, and other user interactions.

Output Location: {BROWSER_RECORDING_OUTPUT_DIR}/recording-<timestamp>/
Format: Recording events are saved as numbered JSON files (1.json, 2.json, etc.)
containing rrweb event arrays. Events are flushed every 5 seconds or when they
exceed 1 MB. These files can be replayed using rrweb-player.

Call browser_stop_recording to stop recording and save any remaining events.

Note: Recording persists across page navigations - the recording will automatically
restart on new pages.
"""


class BrowserStartRecordingTool(
    ToolDefinition[BrowserStartRecordingAction, BrowserObservation]
):
    """用于启动浏览器会话记录的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_START_RECORDING_DESCRIPTION,
                action_type=BrowserStartRecordingAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_start_recording",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


# ============================================
# `browser_stop_recording`
# ============================================
class BrowserStopRecordingAction(BrowserAction):
    """模式用于停止浏览器会话记录。"""

    pass


BROWSER_STOP_RECORDING_DESCRIPTION = f"""Stop recording the browser session.

This tool stops the current recording session and saves any remaining events to disk.

Output Location: {BROWSER_RECORDING_OUTPUT_DIR}/recording-<timestamp>/
Format: Events are saved as numbered JSON files (1.json, 2.json, etc.) containing
rrweb event arrays. These files can be replayed using rrweb-player to visualize
the recorded session.

Returns a summary message with the total event count, file count, and save directory.
"""


class BrowserStopRecordingTool(
    ToolDefinition[BrowserStopRecordingAction, BrowserObservation]
):
    """用于停止浏览器会话记录的工具。"""

    @classmethod
    def create(cls, executor: "BrowserToolExecutor") -> Sequence[Self]:
        return [
            cls(
                description=BROWSER_STOP_RECORDING_DESCRIPTION,
                action_type=BrowserStopRecordingAction,
                observation_type=BrowserObservation,
                annotations=ToolAnnotations(
                    title="browser_stop_recording",
                    # 修改状态：停止记录，将事件刷新到磁盘
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=executor,
            )
        ]


BROWSER_PROMPT_GUIDANCE = """\
<BROWSER_TOOLS>
You have a browser for navigating pages and interacting with web UIs.
* Try curl/wget/fetch first. Use the browser only when simpler tools fail or the page requires JS/interaction.
* ALWAYS call `browser_get_state` before EVERY `browser_click` or `browser_type` — indices change after each action. Flow: navigate → get_state → interact → get_state → get_content.
* Max 10 browser actions per sub-task. If stuck, switch approach entirely.
* If 20+ total steps without converging, stop exploring and commit to your best answer.
* On 403/CAPTCHA/login wall: try one alternative, then abandon the browser.
* Do NOT submit forms or create accounts unless explicitly asked.
</BROWSER_TOOLS>"""  # noqa: E501


class BrowserToolSet(ToolDefinition[BrowserAction, BrowserObservation]):
    """一组所有浏览器工具。

    该工具集包括所有可用的浏览器相关工具
      用于与网页交互。

    该工具集在创建时会自动检查 Chromium 的可用性，如果缺少则自动安装。
    """

    catalog_description: ClassVar[str] = (
        "Browse the web: navigate pages, click, type and read content."
    )

    # 共享执行器：跨父级和子智能体重用单个 Chromium/CDP 实例，以避免沙箱容器中的 CDP 端
    # 口冲突。
    #
    _shared_executor: ClassVar["BrowserToolExecutor | None"] = None
    _shared_executor_lock: ClassVar[threading.Lock] = threading.Lock()
    _shared_executor_creation_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def is_usable(cls) -> bool:
        from openhands.tools.browser_use.impl import BrowserToolExecutor

        return BrowserToolExecutor.check_chromium_available() is not None

    @classmethod
    def _warn_config_ignored(cls, executor_config: dict[str, object]) -> None:
        if not executor_config:
            return
        _logger.warning(
            "BrowserToolSet.create() called with executor_config but a "
            "shared executor already exists. The config %s will be "
            "ignored. This typically happens when a subagent requests "
            "browser tools — it reuses the parent's browser session.",
            list(executor_config.keys()),
        )

    @classmethod
    def _get_or_create_shared_executor(
        cls,
        conv_state: "ConversationState",
        **executor_config,
    ) -> "BrowserToolExecutor":
        with cls._shared_executor_creation_lock:
            with cls._shared_executor_lock:
                executor = cls._shared_executor

            if executor is not None:
                cls._warn_config_ignored(executor_config)
                return executor

            from openhands.tools.browser_use.impl import BrowserToolExecutor

            executor = BrowserToolExecutor(
                full_output_save_dir=conv_state.env_observation_persistence_dir,
                **executor_config,
            )
            with cls._shared_executor_lock:
                cls._shared_executor = executor
            return executor

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        **executor_config,
    ) -> list[ToolDefinition[BrowserAction, BrowserObservation]]:
        try:
            executor = cls._get_or_create_shared_executor(conv_state, **executor_config)
        except Exception:
            # 无法启动的浏览器一定不会导致整个会话失败； 智能体继续使用其剩余的工具。
            #
            _logger.warning(
                "Browser tools are unavailable: the browser executor failed to "
                "start. Continuing without them.",
                exc_info=True,
            )
            return []

        # 每个 tool.create() 返回一个 Sequence[Self]，因此我们将结果展平
        tools: list[ToolDefinition[BrowserAction, BrowserObservation]] = []
        for tool_class in [
            BrowserNavigateTool,
            BrowserClickTool,
            BrowserGetStateTool,
            BrowserGetContentTool,
            BrowserTypeTool,
            BrowserScrollTool,
            BrowserGoBackTool,
            BrowserListTabsTool,
            BrowserSwitchTabTool,
            BrowserCloseTabTool,
            BrowserGetStorageTool,
            BrowserSetStorageTool,
            BrowserStartRecordingTool,
            BrowserStopRecordingTool,
        ]:
            tools.extend(tool_class.create(executor))
        return [
            tool.model_copy(update={"prompt_guidance": BROWSER_PROMPT_GUIDANCE})
            for tool in tools
        ]


register_tool(BrowserToolSet.name, BrowserToolSet)
