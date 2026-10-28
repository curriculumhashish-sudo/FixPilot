"""终端后端的抽象接口。"""

import os
from abc import ABC, abstractmethod

from openhands.tools.terminal.constants import (
    NO_CHANGE_TIMEOUT_SECONDS,
)
from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
)


# 所有 TerminalInterface 实现都必须支持的规范的命名特殊键集。 每个后端将它们映射到自己的
# 表示形式（ANSI 转义字节表示 PTY，tmux 键名称表示 tmux）。
#
SUPPORTED_SPECIAL_KEYS: frozenset[str] = frozenset(
    {
        "ENTER",
        "TAB",
        "BS",
        "ESC",
        "UP",
        "DOWN",
        "LEFT",
        "RIGHT",
        "HOME",
        "END",
        "PGUP",
        "PGDN",
        "C-L",
        "C-D",
        "C-C",
    }
)


def parse_ctrl_key(text: str) -> str | None:
    """解析 Ctrl-<letter> token 并返回规范化形式 ``C-x``。

    接受 ``C-x``、``CTRL-x`` 和 ``CTRL+x``（不区分大小写），其中 *x* 是单个 ASCII 字
    母。 当 *text* 不是可识别的 Ct
    rl 序列时，返回 ``None``。
    """
    upper = text.strip().upper()
    key: str | None = None
    if upper.startswith("C-"):
        key = upper[2:]
    elif upper.startswith("CTRL-"):
        key = upper[5:]
    elif upper.startswith("CTRL+"):
        key = upper[5:]
    if key and len(key) == 1 and "A" <= key <= "Z":
        return f"C-{key.lower()}"
    return None


class TerminalInterface(ABC):
    """终端后端的抽象接口。

    该接口抽象了底层终端操作，允许使用不同的后端（tmux，子进程，PowerShell）与相同的
    高级会话控制器逻辑。
    """

    work_dir: str
    username: str | None
    _initialized: bool
    _closed: bool

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
    ):
        """初始化终端界面。

        Args:
            work_dir: 工作目录为终端
            username: 终端会话的可选用户名
        """
        self.work_dir = work_dir
        self.username = username
        self._initialized = False
        self._closed = False

    @abstractmethod
    def initialize(self) -> None:
        """初始化终端后端。

        这应该设置终端会话、配置 shell 并准备好执行命令。 成功初始化后，实现应设置
        self._initialized = True。
        """

    @abstractmethod
    def close(self) -> None:
        """清理终端后端。

        这应该正确终止终端会话并清理所有资源。 实施应设定
        self._closed = True upon successful cleanup.
        """

    @abstractmethod
    def send_keys(self, text: str, enter: bool = True) -> None:
        """将文本/按键发送到终端。

        所有实现必须支持：
          - 纯文本（逐字发送）
          - 命名特价：ENTER、TAB、BS、ESC、UP、DOWN、LEFT、RIGHT、HOME、END、PGUP、
          PGDN、C-L、C-D、C-C
          - 通用 Ctrl 序列：``C-<letter>``、``CTRL-<letter>``、
            ``CTRL+<letter>``（不区分大小写，a-z）

        Args:
            text: 要发送到终端的文本或按键序列。
            enter: 是否在文本后发送回车键。
                   默认为 True。 忽略特殊/ctrl 键。
        """

    @abstractmethod
    def read_screen(self) -> str:
        """读取当前终端屏幕内容。

        Returns:
            终端屏幕的当前可见内容作为字符串。
        """

    @abstractmethod
    def clear_screen(self) -> None:
        """清除终端屏幕和历史记录。

        此方法应清除可见的终端屏幕内容和任何回滚历史记录，为新输出提供一个干净的状态
        。
        """

    @abstractmethod
    def interrupt(self) -> bool:
        """向终端发送中断信号（Ctrl+C）。

        此方法应发送 SIGINT 信号以中断终端会话中当前正在运行的任何命令。

        Returns:
            如果中断发送成功则为 True，否则为 False。
        """

    @abstractmethod
    def is_running(self) -> bool:
        """检查命令当前是否正在终端中运行。

        此方法应确定终端会话中是否正在执行活动命令。

        Returns:
            如果命令正在运行，则为 True，否则为 False。
        """

    @property
    def initialized(self) -> bool:
        """检查终端是否已初始化。"""
        return self._initialized

    @property
    def closed(self) -> bool:
        """检查终端是否关闭。"""
        return self._closed

    def is_powershell(self) -> bool:
        """检查这是否是 PowerShell 终端。

        Returns:
            True 如果这是 PowerShell 终端，False 否则
        """
        return False


class TerminalSessionBase(ABC):
    """终端会话的抽象基类。

    此类定义所有终端会话实现的公共接口，包括基于 tmux、基于子进程和基于 PowerShell 的
    会话。
    """

    work_dir: str
    username: str | None
    no_change_timeout_seconds: int
    _initialized: bool
    _closed: bool
    _cwd: str

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
    ):
        """初始化终端会话。

        Args:
            work_dir: 工作目录会议
            username: 会话的可选用户名
            no_change_timeout_seconds: 超时表示无输出变化
        """
        self.work_dir = work_dir
        self.username = username
        self.no_change_timeout_seconds = (
            no_change_timeout_seconds or NO_CHANGE_TIMEOUT_SECONDS
        )
        self._initialized = False
        self._closed = False
        self._cwd = os.path.abspath(work_dir)

    @abstractmethod
    def initialize(self) -> None:
        """初始化终端会话。

        此方法应设置终端会话、配置环境并准备执行命令。 实施应设定
        self._initialized = True upon successful initialization.
        """

    @abstractmethod
    def execute(self, action: TerminalAction) -> TerminalObservation:
        """在终端会话中执行命令。

        此方法应执行操作中指定的 bash 命令并返回结果，包括输出、退出代码和任何错误。

        Args:
            action: 要执行的 bash 操作包含命令和参数。

        Returns:
            TerminalObservation 命令结果包括输出、退出代码和执行元数据。
        """

    @abstractmethod
    def close(self) -> None:
        """清理终端会话。

        此方法应正确终止终端会话，清理所有资源，并在成功清理后设置 self._closed =
        True。
        """

    @abstractmethod
    def interrupt(self) -> bool:
        """中断当前正在运行的命令（相当于Ctrl+C）。

        此方法应发送 SIGINT 信号以中断终端会话中当前正在运行的任何命令。

        Returns:
            如果中断成功则为 True，否则为 False。
        """

    @abstractmethod
    def is_running(self) -> bool:
        """检查命令当前是否正在运行。

        此方法应确定终端会话中是否正在执行活动命令。

        Returns:
            如果命令正在运行，则为 True，否则为 False。
        """

    @property
    def cwd(self) -> str:
        """获取当前工作目录。"""
        return self._cwd

    def __del__(self) -> None:
        """确保对象被销毁时会话已关闭。"""
        try:
            self.close()
        except ImportError:
            # Python 正在关闭，让操作系统处理清理工作
            pass
