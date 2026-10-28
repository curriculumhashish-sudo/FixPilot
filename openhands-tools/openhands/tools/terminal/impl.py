import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Literal

from libtmux.exc import LibTmuxException, TmuxObjectDoesNotExist

from openhands.sdk.llm import TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.tool import ToolExecutor


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation
from openhands.tools.terminal.constants import CMD_OUTPUT_PS1_END
from openhands.tools.terminal.definition import (
    _LITERAL_ARG_HINT_TEMPLATE,
    TerminalAction,
    TerminalObservation,
    looks_like_python_literal_argument,
)
from openhands.tools.terminal.env import (
    ENV_VAR_NAME_RE,
    normalize_terminal_env,
)
from openhands.tools.terminal.terminal.factory import (
    _is_tmux_available,
    create_terminal_session,
)
from openhands.tools.terminal.terminal.terminal_session import (
    TerminalCommandStatus,
    TerminalSession,
)
from openhands.tools.terminal.terminal.tmux_pane_pool import (
    DEFAULT_MAX_PANES,
    PooledTmuxTerminal,
    TmuxPanePool,
)


_TMUX_POOL_RECOVERY_MESSAGE = (
    "The terminal session was reset because the underlying tmux server/session "
    "disappeared while running the previous command. This often happens when a "
    "command terminates the persistent shell, for example by ending with a "
    "top-level `exit` such as `exit $code`, or otherwise kills tmux. OpenHands "
    "rebuilt the terminal pool, but the interrupted command's result is not "
    "reliable and was not retried. Avoid top-level `exit` in future terminal "
    'commands; use a non-shell-exiting status check like `test "$code" -eq 0` '
    "or conditional shell logic instead. Please rerun any needed command."
)

_TMUX_RECOVERABLE_ERROR_MARKERS = (
    "no server running",
    "can't find session",
    "could not find window_id",
    "could not find pane_id",
)

logger = get_logger(__name__)


class TerminalExecutor(ToolExecutor[TerminalAction, TerminalObservation]):
    shell_path: str | None

    def __init__(
        self,
        working_dir: str,
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
        terminal_type: Literal["tmux", "subprocess", "powershell"] | None = None,
        shell_path: str | None = None,
        env: Mapping[str, str] | None = None,
        full_output_save_dir: str | None = None,
        max_panes: int = DEFAULT_MAX_PANES,
    ):
        """使用自动检测或指定的会话类型初始化 TerminalExecutor。

        Args:
            working_dir: 工作目录用于 shell 命令
            username: shell 会话的可选用户名
            no_change_timeout_seconds: 超时表示无输出变化
            terminal_type: 强制指定特定会话类型：
                         （“tmux”、“子进程”或“powershell”）。 如果是None，则根据系统
                         功能自动检测。
            shell_path: shell 二进制文件的路径。 在 Unix 上这适用于
                       子进程后端； 在 Windows 上，它可以指向 PowerShell 可执行文件。
            env: 添加到终端会话的额外环境变量。
            full_output_save_dir: 保存完整输出的目录路径
                                  日志和文件，在需要截断时使用。
            max_panes: 池模式下的最大并发窗格数。
        """
        self.shell_path = shell_path
        self._working_dir = working_dir
        self._username = username
        self._no_change_timeout_seconds = no_change_timeout_seconds
        self._terminal_type = terminal_type
        self._env = normalize_terminal_env(env)
        self._max_panes = max_panes
        self.full_output_save_dir: str | None = full_output_save_dir

        # Pool模式：使用TmuxPanePool并行执行
        self._pool: TmuxPanePool | None = None
        self._session: TerminalSession | None = None
        self._sessions: dict[int, TerminalSession] = {}
        self._sessions_lock = threading.Lock()
        self._pool_recovery_lock = threading.Lock()

        use_pool = terminal_type in (None, "tmux") and _is_tmux_available()

        if use_pool:
            self._initialize_pool()
        else:
            self._session = create_terminal_session(
                work_dir=working_dir,
                username=username,
                no_change_timeout_seconds=no_change_timeout_seconds,
                terminal_type=terminal_type,
                shell_path=shell_path,
                env=self._env,
            )
            self._session.initialize()
            logger.info(
                f"TerminalExecutor initialized with "
                f"working_dir: {working_dir}, "
                f"username: {username}, "
                f"terminal_type: "
                f"{terminal_type or self._session.__class__.__name__}"
            )

    @property
    def is_pooled(self) -> bool:
        """此执行程序是否正在将 tmux 窗格池用于并发。"""
        return self._pool is not None

    def _initialize_pool(self) -> None:
        self._pool = TmuxPanePool(
            self._working_dir,
            self._username,
            env=self._env,
            max_panes=self._max_panes,
        )
        self._pool.initialize()
        logger.info(
            f"TerminalExecutor initialized (pool mode) "
            f"working_dir: {self._working_dir}, username: {self._username}, "
            f"max_panes: {self._max_panes}"
        )

    @staticmethod
    def _is_recoverable_tmux_pool_error(error: Exception) -> bool:
        recoverable_types = (LibTmuxException, TmuxObjectDoesNotExist)
        if not isinstance(error, recoverable_types):
            return False
        message = " ".join(str(arg) for arg in error.args).lower()
        return any(marker in message for marker in _TMUX_RECOVERABLE_ERROR_MARKERS)

    def _recover_tmux_pool(self, failed_pool: TmuxPanePool) -> None:
        with self._pool_recovery_lock:
            if self._pool is not failed_pool:
                return

            with suppress(Exception):
                failed_pool.close()
            with self._sessions_lock:
                self._sessions.clear()
            self._initialize_pool()

    @staticmethod
    def _tmux_pool_recovery_observation(
        action: TerminalAction,
        error: Exception,
    ) -> TerminalObservation:
        return TerminalObservation.from_text(
            text=(f"{_TMUX_POOL_RECOVERY_MESSAGE}\n\nOriginal tmux error: {error}"),
            is_error=True,
            command=action.command or "[RESET]",
            exit_code=-1,
        )

    @property
    def working_dir(self) -> str:
        """返回此执行器的工作目录。"""
        return self._working_dir

    @property
    def session(self) -> TerminalSession:
        """访问单会话终端。

        Raises:
            AttributeError: 如果执行器处于池模式。
        """
        if self._pool is not None:
            raise AttributeError(
                "TerminalExecutor.session is not available in pool mode. "
                "Use the is_pooled property to check mode, or set "
                "terminal_type='subprocess' to disable pool mode."
            )
        assert self._session is not None
        return self._session

    # ------------------------------------------------------------------
    # 泳池助手
    # ------------------------------------------------------------------

    def _wrap_session(self, terminal: PooledTmuxTerminal) -> TerminalSession:
        """获取或创建池 PooledTmuxTerminal 的 TerminalSession。"""
        pane_id = id(terminal)
        with self._sessions_lock:
            if pane_id not in self._sessions:
                # 池已经初始化了终端 - 使用 attach_to_existing 跳过 session.initialize()
                # ，这将创建重复的 tmux 会话。
                #
                session = TerminalSession.attach_to_existing(
                    terminal, self._no_change_timeout_seconds
                )
                self._sessions[pane_id] = session
            return self._sessions[pane_id]

    def _discard_session(self, terminal: PooledTmuxTerminal) -> None:
        """删除要更换的终端的缓存 TerminalSession。

        我们将会话（及其底层终端）标记为关闭
        *在*删除引用之前。 这可以防止
        ``TerminalSessionBase.__del__`` 调用 ``close()``，这会杀死池终端的窗口 - 如果
        该窗口是最后一个窗口，则可能会杀
        死整个共享 tmux 会话。
        """
        with self._sessions_lock:
            session = self._sessions.pop(id(terminal), None)
            if session is not None:
                session._closed = True
                # 还要标记终端，以便池化的 close() 是无操作的
                terminal._closed = True

    @staticmethod
    def _prepare_pooled_session(session: TerminalSession) -> None:
        """重置可变会话状态，以便此签出是独立的。

        没有这个，超时命令遗留的``prev_status``会导致下一个独立调用被当作后续交互处理
        ，PS1计数可能会被破坏。
        """
        if session.prev_status in (
            TerminalCommandStatus.NO_CHANGE_TIMEOUT,
            TerminalCommandStatus.HARD_TIMEOUT,
            TerminalCommandStatus.CONTINUE,
        ):
            # 上一个命令未完成 - 中断并轮询，直到提示词重新出现，而不是休眠固定的持续时
            # 间。
            #
            session.terminal.interrupt()
            _max_wait = 2.0
            _poll = 0.05
            _waited = 0.0
            while _waited < _max_wait:
                time.sleep(_poll)
                _waited += _poll
                screen = session.terminal.read_screen()
                if screen.rstrip().endswith(CMD_OUTPUT_PS1_END.rstrip()):
                    break
            else:
                logger.debug(
                    "Prompt did not reappear within %.1fs after interrupt; "
                    "proceeding anyway",
                    _max_wait,
                )
            session.terminal.clear_screen()
        session.prev_status = None
        session.prev_output = ""

    @staticmethod
    def _powershell_quote(value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    @staticmethod
    def _bash_quote(value: str) -> str:
        """使用 $'...' ANSI-C 引用为 bash 引用一个值。"""
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace("\n", "\\n")
        escaped = escaped.replace("\r", "\\r")
        escaped = escaped.replace("\t", "\\t")
        return f"$'{escaped}'"

    @classmethod
    def _build_env_exports(
        cls,
        env_vars: dict[str, str],
        session: TerminalSession,
    ) -> str:
        valid: dict[str, str] = {}
        for key, value in env_vars.items():
            if ENV_VAR_NAME_RE.match(key):
                valid[key] = value
            else:
                logger.warning("Skipping secret with invalid env var name: %r", key)

        if not valid:
            return ""

        if session.terminal.is_powershell():
            assignments = [
                f"$env:{key} = {cls._powershell_quote(value)}"
                for key, value in valid.items()
            ]
            return "; ".join(assignments)

        assignments = [
            f"export {key}={cls._bash_quote(value)}" for key, value in valid.items()
        ]
        return " && ".join(assignments)

    # ------------------------------------------------------------------
    # 环境导出/机密掩蔽
    # ------------------------------------------------------------------

    def _export_envs(
        self,
        action: TerminalAction,
        conversation: "LocalConversation | None" = None,
        session: TerminalSession | None = None,
    ) -> None:
        if not action.command.strip():
            return

        if action.is_input:
            return

        # 从对话中获取机密
        env_vars = {}
        if conversation is not None:
            try:
                secret_registry = conversation.state.secret_registry
                env_vars = secret_registry.get_secrets_as_env_vars(action.command)
            except Exception:
                env_vars = {}

        if not env_vars:
            return

        target = session or self.session
        exports_cmd = self._build_env_exports(env_vars, target)

        if not exports_cmd:
            return

        logger.debug(f"Exporting {len(env_vars)} environment variables before command")
        # 分别对会话中的持久化 env执行export命令
        _ = target.execute(
            TerminalAction(
                command=exports_cmd,
                is_input=False,
                timeout=action.timeout,
            )
        )

    def _mask_observation(
        self,
        observation: TerminalObservation,
        conversation: "LocalConversation | None" = None,
    ) -> TerminalObservation:
        """将自动机密屏蔽应用到 *观测结果*。"""
        content_text = observation.text

        if content_text and conversation is not None:
            try:
                secret_registry = conversation.state.secret_registry
                masked_content = secret_registry.mask_secrets_in_output(content_text)
                if masked_content:
                    data = observation.model_dump(
                        exclude={"content", "full_output_save_dir"}
                    )
                    return TerminalObservation.from_text(
                        text=masked_content,
                        full_output_save_dir=self.full_output_save_dir,
                        **data,
                    )
            except Exception:
                pass

        return observation

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------

    def reset(self) -> TerminalObservation:
        """公共重置——委托给适当的后端。"""
        return self._reset_single_session()

    def _reset_single_session(self) -> TerminalObservation:
        """重置单会话终端。"""
        assert self._session is not None
        original_work_dir = self._session.work_dir
        original_username = self._session.username
        original_no_change_timeout = self._session.no_change_timeout_seconds

        self._session.close()
        self._session = create_terminal_session(
            work_dir=original_work_dir,
            username=original_username,
            no_change_timeout_seconds=original_no_change_timeout,
            terminal_type=None,
            shell_path=self.shell_path,
            env=self._env,
        )
        self._session.initialize()

        logger.info(
            f"Terminal session reset successfully with working_dir: {self._working_dir}"
        )

        return TerminalObservation.from_text(
            text=(
                "Terminal session has been reset. All previous environment "
                "variables and session state have been cleared."
            ),
            command="[RESET]",
            exit_code=0,
        )

    _RESET_TEXT = (
        "Terminal session has been reset. All previous environment "
        "variables and session state have been cleared."
    )

    # ------------------------------------------------------------------
    # 执行路径
    # ------------------------------------------------------------------

    def _execute_single_session(
        self,
        action: TerminalAction,
        conversation: "LocalConversation | None" = None,
    ) -> TerminalObservation:
        """在单会话（非池）模式下执行 *action*。"""
        if action.reset or self.session._closed:
            reset_result = self._reset_single_session()

            if action.command.strip():
                session = self.session  # 重置创建了一个新的
                command_action = TerminalAction(
                    command=action.command,
                    timeout=action.timeout,
                    is_input=False,
                )
                self._export_envs(command_action, conversation, session=session)
                command_result = session.execute(command_action)

                reset_text = reset_result.text
                command_text = command_result.text

                observation = command_result.model_copy(
                    update={
                        "content": [
                            TextContent(text=f"{reset_text}\n\n{command_text}")
                        ],
                        "command": f"[RESET] {action.command}",
                    }
                )
            else:
                observation = reset_result
        else:
            self._export_envs(action, conversation, session=self.session)
            observation = self.session.execute(action)

        return self._mask_observation(observation, conversation)

    def _execute_pooled(
        self,
        action: TerminalAction,
        conversation: "LocalConversation | None" = None,
    ) -> TerminalObservation:
        """在池模式下执行 *action*，并进行正确的签出/签入。

        所有窗格生命周期（签出、可选替换、签入）均由池的上下文管理器管理，因此每次调
        用恰好有一次签出和一次签入。
        """
        pool = self._pool
        assert pool is not None
        try:
            with pool.pane() as handle:
                reset_text: str | None = None

                if action.reset or handle.terminal._closed:
                    self._discard_session(handle.terminal)
                    handle.terminal = pool.replace(handle.terminal)
                    reset_text = self._RESET_TEXT
                    logger.info(
                        "Terminal pane replaced (reset) "
                        f"working_dir: {self._working_dir}"
                    )

                    if not action.command.strip():
                        return TerminalObservation.from_text(
                            text=reset_text,
                            command="[RESET]",
                            exit_code=0,
                        )

                session = self._wrap_session(handle.terminal)
                self._prepare_pooled_session(session)

                cmd_action = (
                    action
                    if reset_text is None
                    else TerminalAction(
                        command=action.command,
                        timeout=action.timeout,
                        is_input=False,
                    )
                )
                self._export_envs(cmd_action, conversation, session=session)
                observation = session.execute(cmd_action)

                if reset_text is not None:
                    observation = observation.model_copy(
                        update={
                            "content": [
                                TextContent(text=f"{reset_text}\n\n{observation.text}")
                            ],
                            "command": f"[RESET] {action.command}",
                        }
                    )

                return self._mask_observation(observation, conversation)
        except Exception as error:
            if not self._is_recoverable_tmux_pool_error(error):
                raise
            logger.warning(
                "Recovering terminal pane pool after tmux server/session disappeared",
                exc_info=True,
            )
            self._recover_tmux_pool(pool)
            return self._tmux_pool_recovery_observation(action, error)

    def __call__(
        self,
        action: TerminalAction,
        conversation: "LocalConversation | None" = None,
    ) -> TerminalObservation:
        if action.reset and action.is_input:
            raise ValueError("Cannot use reset=True with is_input=True")

        # 短路明显的工具调用畸形：Python/JSON 文字传递到模型应发送 shell 命令的位置。 否
        # 则，shell 会回显令人困惑的 `command not found`，并且模型很少在没有结构化提示的
        # 情况下进行自我纠正。 当以下情况时跳过检查
        # `is_input=True` 因为该路径转发原始字节 (e.g. 像 `C-c` 这样的击键）对正在运行的
        # 进程来说并不是一个新的 shell 命令。
        #
        if not action.is_input:
            literal_kind = looks_like_python_literal_argument(action.command)
            if literal_kind is not None:
                head = action.command.lstrip()[:60]
                logger.warning(
                    "Rejected terminal call: command argument looks like a "
                    "Python/JSON %s (head=%r). Returning structured hint to "
                    "the model instead of executing.",
                    literal_kind,
                    head,
                )
                return TerminalObservation.from_text(
                    _LITERAL_ARG_HINT_TEMPLATE.format(
                        literal_kind=literal_kind,
                        head=head,
                    ),
                    is_error=True,
                    command=action.command,
                    exit_code=None,
                )

        if self._pool is not None:
            return self._execute_pooled(action, conversation)
        else:
            return self._execute_single_session(action, conversation)

    def interrupt(self) -> None:
        """将 Ctrl+C 发送到所有活动的终端会话。

        当对话被打断时，从另一个线程调用，因此阻塞``session.execute()``的轮询循环会看
        到命令终止，从而worker线程可以退出。
        """
        if self._pool is not None:
            with self._sessions_lock:
                for session in self._sessions.values():
                    with suppress(Exception):
                        session.interrupt()
        elif self._session is not None:
            with suppress(Exception):
                self._session.interrupt()

    def close(self) -> None:
        """关闭终端会话并清理资源。"""
        if self._pool is not None:
            self._pool.close()
            with self._sessions_lock:
                self._sessions.clear()
        elif self._session is not None:
            self._session.close()
