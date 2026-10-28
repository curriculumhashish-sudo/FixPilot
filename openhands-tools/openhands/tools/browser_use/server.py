from browser_use.dom.markdown_extractor import extract_clean_markdown

from openhands.sdk import get_logger
from openhands.tools.browser_use.logging_fix import LogSafeBrowserUseServer
from openhands.tools.browser_use.recording import RecordingSession


logger = get_logger(__name__)


# =============================================================================
# CustomBrowserUseServer 班级
# =============================================================================


class CustomBrowserUseServer(LogSafeBrowserUseServer):
    """
    自定义 BrowserUseServer，使用新工具提取 Markdown 中的网页内容。
    """

    def __init__(self, session_timeout_minutes: int = 10):
        super().__init__(session_timeout_minutes=session_timeout_minutes)
        # 要注入到每个新文档中的脚本（在页面脚本运行之前）
        self._inject_scripts: list[str] = []
        # CDP 返回的脚本标识符（如果需要则用于清理）
        self._injected_script_ids: list[str] = []
        # 录音会话——封装所有录音状态和逻辑
        self._recording_session: RecordingSession | None = None

    @property
    def _is_recording(self) -> bool:
        """检查当前是否正在录制。"""
        return self._recording_session is not None and self._recording_session.is_active

    async def _cleanup_recording(self) -> None:
        """清理录制会话资源。

        停止任何活动记录、保存剩余事件并释放资源。 应该在浏览器会话关闭时调用。
        """
        if self._recording_session is None:
            return

        try:
            # 如果处于活动状态，则停止记录以保存任何剩余事件
            if self._recording_session.is_active and self.browser_session:
                await self._recording_session.stop(self.browser_session)
            else:
                # 如果不活动或没有浏览器会话，只需重置
                self._recording_session.reset()
        except Exception as e:
            logger.debug(f"Recording cleanup error (non-fatal): {e}")
        finally:
            self._recording_session = None

    async def _close_browser(self) -> str:
        """关闭浏览器会话并清理录制资源。"""
        await self._cleanup_recording()
        return await super()._close_browser()

    async def _close_session(self, session_id: str) -> str:
        """如果需要，请关闭特定的浏览器会话并清理记录。"""
        # 如果关闭当前会话则清除记录
        if self.browser_session and self.browser_session.id == session_id:
            await self._cleanup_recording()
        return await super()._close_session(session_id)

    async def _close_all_sessions(self) -> str:
        """关闭所有活动的浏览器会话并清理录制资源。"""
        await self._cleanup_recording()
        return await super()._close_all_sessions()

    def set_inject_scripts(self, scripts: list[str]) -> None:
        """设置要注入到每个新文档中的脚本。

        Args:
            scripts: 要注入的 JavaScript 代码字符串列表。
                     每个脚本将在页面脚本运行之前进行评估。
        """
        self._inject_scripts = scripts

    async def _inject_scripts_to_session(self) -> None:
        """使用 CDP 将配置的用户脚本注入浏览器会话。

        使用 Page.addScriptToEvaluateOnNewDocument 注入将在页面脚本执行之前在每个新文
        档上运行的脚本。
        Note: rrweb 脚本在录制开始时延迟注入。
        """
        if not self.browser_session or not self._inject_scripts:
            return

        try:
            cdp_session = await self.browser_session.get_or_create_cdp_session()
            cdp_client = cdp_session.cdp_client

            for script in self._inject_scripts:
                result = await cdp_client.send.Page.addScriptToEvaluateOnNewDocument(
                    params={"source": script, "runImmediately": True},
                    session_id=cdp_session.session_id,
                )
                script_id = result.get("identifier")
                if script_id:
                    self._injected_script_ids.append(script_id)
                    logger.debug(f"Injected script with identifier: {script_id}")

            num_scripts = len(self._inject_scripts)
            logger.info(f"Injected {num_scripts} user script(s) into browser session")
        except Exception as e:
            logger.warning(f"Failed to inject scripts: {e}")

    async def _flush_recording_events(self) -> int:
        """将记录事件从浏览器刷新到 Python 存储。

        返回刷新的事件数。
        """
        if not self.browser_session or not self._recording_session:
            return 0
        return await self._recording_session.flush_events(self.browser_session)

    async def _restart_recording_on_new_page(self) -> None:
        """导航后在新页面上重新开始录制。"""
        if not self.browser_session or not self._recording_session:
            return
        await self._recording_session.restart_on_new_page(self.browser_session)

    async def _start_recording(self, output_dir: str | None = None) -> str:
        """开始 rrweb 会话记录。

        记录在页面导航中持续存在 - 事件定期刷新到会话子文件夹中带时间戳的 JSON 文件。

        每个录制会话都会在 output_dir 下创建一个新的子文件夹，格式为：
        {output_dir}/recording-{timestamp}/

        Args:
            output_dir: 录制文件的根目录。 如果提供，则带有时间戳
                将为该录制会话创建子文件夹。
        """
        if not self.browser_session:
            return "Error: No browser session active"

        # 使用 output_dir 创建新的录制会话
        self._recording_session = RecordingSession(output_dir=output_dir)
        return await self._recording_session.start(self.browser_session)

    async def _stop_recording(self) -> str:
        """停止 rrweb 记录并保存剩余事件。

        事件保存到start_recording时间配置的目录中。

        Returns:
            包含保存目录和文件计数的摘要消息。
        """
        if not self.browser_session:
            return "Error: No browser session active"

        if not self._recording_session or not self._recording_session.is_active:
            return "Error: Not recording. Call browser_start_recording first."

        result = await self._recording_session.stop(self.browser_session)
        # 停止后重置会话
        self._recording_session.reset()
        return result

    async def _get_storage(self) -> str:
        """获取浏览器存储（cookie、本地存储、会话存储）。"""
        import json

        if not self.browser_session:
            return "Error: No browser session active"

        try:
            # 使用 BrowserSession 中的私有方法获取存储状态这将返回一个带有“cookies”和“
            # origins”的字典（localStorage/sessionStorage）
            #
            storage_state = await self.browser_session._cdp_get_storage_state()
            return json.dumps(storage_state, indent=2)
        except Exception as e:
            logger.exception("Error getting storage state", exc_info=e)
            return f"Error getting storage state: {str(e)}"

    async def _set_storage(self, storage_state: dict) -> str:
        """设置浏览器存储（cookie、本地存储、会话存储）。"""
        if not self.browser_session:
            return "Error: No browser session active"

        try:
            # 1. 设置cookie
            cookies = storage_state.get("cookies", [])
            if cookies:
                await self.browser_session._cdp_set_cookies(cookies)

            # 2. 设置本地/会话存储
            origins = storage_state.get("origins", [])
            if origins:
                cdp_session = await self.browser_session.get_or_create_cdp_session()

                # 启用 DOMStorage
                await cdp_session.cdp_client.send.DOMStorage.enable(
                    session_id=cdp_session.session_id
                )

                try:
                    for origin_data in origins:
                        origin = origin_data.get("origin")
                        if not origin:
                            continue

                        dom_storage = cdp_session.cdp_client.send.DOMStorage

                        # 设置 localStorage
                        for item in origin_data.get("localStorage", []):
                            key = item.get("key") or item.get("name")
                            if not key:
                                continue
                            await dom_storage.setDOMStorageItem(
                                params={
                                    "storageId": {
                                        "securityOrigin": origin,
                                        "isLocalStorage": True,
                                    },
                                    "key": key,
                                    "value": item["value"],
                                },
                                session_id=cdp_session.session_id,
                            )

                        # 设置 sessionStorage
                        for item in origin_data.get("sessionStorage", []):
                            key = item.get("key") or item.get("name")
                            if not key:
                                continue
                            await dom_storage.setDOMStorageItem(
                                params={
                                    "storageId": {
                                        "securityOrigin": origin,
                                        "isLocalStorage": False,
                                    },
                                    "key": key,
                                    "value": item["value"],
                                },
                                session_id=cdp_session.session_id,
                            )
                finally:
                    # 禁用 DOMStorage
                    await cdp_session.cdp_client.send.DOMStorage.disable(
                        session_id=cdp_session.session_id
                    )

            return "Storage set successfully"
        except Exception as e:
            logger.exception("Error setting storage state", exc_info=e)
            return f"Error setting storage state: {str(e)}"

    async def _get_content(self, extract_links=False, start_from_char: int = 0) -> str:
        MAX_CHAR_LIMIT = 30000

        if not self.browser_session:
            return "Error: No browser session active"

        # 使用新方法提取干净的Markdown
        try:
            content, content_stats = await extract_clean_markdown(
                browser_session=self.browser_session, extract_links=extract_links
            )
        except Exception as e:
            logger.exception(
                "Error extracting clean markdown", exc_info=e, stack_info=True
            )
            return f"Could not extract clean markdown: {type(e).__name__}"

        # 待处理的原始内容长度
        final_filtered_length = content_stats["final_filtered_chars"]

        if start_from_char > 0:
            if start_from_char >= len(content):
                return f"start_from_char ({start_from_char}) exceeds content length ({len(content)}). Content has {final_filtered_length} characters after filtering."  # noqa: E501

            content = content[start_from_char:]
            content_stats["started_from_char"] = start_from_char

        # 智能截断并保留上下文
        truncated = False
        if len(content) > MAX_CHAR_LIMIT:
            # 尝试在自然断点处截断（段落、句子）
            truncate_at = MAX_CHAR_LIMIT

            # 在限制的最后 500 个字符内查找段落中断
            paragraph_break = content.rfind(
                "\n\n", MAX_CHAR_LIMIT - 500, MAX_CHAR_LIMIT
            )
            if paragraph_break > 0:
                truncate_at = paragraph_break
            else:
                # 查找最后 200 个字符内的断句
                sentence_break = content.rfind(
                    ".", MAX_CHAR_LIMIT - 200, MAX_CHAR_LIMIT
                )
                if sentence_break > 0:
                    truncate_at = sentence_break + 1

            content = content[:truncate_at]
            truncated = True
            next_start = (start_from_char or 0) + truncate_at
            content_stats["truncated_at_char"] = truncate_at
            content_stats["next_start_char"] = next_start

        # 将内容统计添加到结果中
        original_html_length = content_stats["original_html_chars"]
        initial_markdown_length = content_stats["initial_markdown_chars"]
        chars_filtered = content_stats["filtered_chars_removed"]

        stats_summary = (
            f"Content processed: {original_html_length:,}"
            + f" HTML chars → {initial_markdown_length:,}"
            + f" initial markdown → {final_filtered_length:,} filtered markdown"
        )
        if start_from_char > 0:
            stats_summary += f" (started from char {start_from_char:,})"
        if truncated:
            stats_summary += f" → {len(content):,} final chars (truncated, use start_from_char={content_stats['next_start_char']} to continue)"  # noqa: E501
        elif chars_filtered > 0:
            stats_summary += f" (filtered {chars_filtered:,} chars of noise)"

        prompt = f"""<content_stats>
{stats_summary}
</content_stats>

<webpage_content>
{content}
</webpage_content>"""
        current_url = await self.browser_session.get_current_page_url()

        return f"""<url>
{current_url}
</url>
<content>
{prompt}
</content>"""
