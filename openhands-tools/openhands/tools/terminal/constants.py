import re
from typing import Final


CMD_OUTPUT_PS1_BEGIN: Final[str] = "\n###PS1JSON###\n"
CMD_OUTPUT_PS1_END: Final[str] = "\n###PS1END###"
# 用于匹配 PS1 元数据块的正则表达式。 使用负前瞻来处理并发输出导致嵌套 ###PS1JSON### 标
# 记的损坏场景。 这确保我们只匹配每个 ###PS1END### 之前的 LAST ###PS1JSON###。
#
CMD_OUTPUT_METADATA_PS1_REGEX: Final[re.Pattern[str]] = re.compile(
    rf"^{CMD_OUTPUT_PS1_BEGIN.strip()}((?:(?!{CMD_OUTPUT_PS1_BEGIN.strip()}).)*?){CMD_OUTPUT_PS1_END.strip()}",
    re.DOTALL | re.MULTILINE,
)

# 命令输出内容的默认最大大小，以防止在流中保存太大的观测结果这与 LLM 类中的默认
# max_message_chars 匹配
#
MAX_CMD_OUTPUT_SIZE: Final[int] = 30000


# 可在不同超时场景中使用的通用超时消息
TIMEOUT_MESSAGE_TEMPLATE: Final[str] = (
    "You may wait longer to see additional output by sending empty command '', "
    "send other commands to interact with the current process, send keys "
    '("C-c", "C-z", "C-d") '
    "to interrupt/kill the previous command before sending your new command, "
    "or use the timeout parameter in terminal for future commands."
)

# 在没有新输出的情况下等待多长时间才将其视为无变化超时
NO_CHANGE_TIMEOUT_SECONDS: Final[int] = 30

# 命令运行一段时间后，以秒为单位轮询新输出的频率
POLL_INTERVAL: Final[float] = 0.5
# 最短轮询间隔，在发送命令后立即使用
MIN_POLL_INTERVAL: Final[float] = 0.02
HISTORY_LIMIT: Final[int] = 10_000

TMUX_SOCKET_NAME: Final[str] = "openhands"

# tmux 用户选项记录创建套接字的进程的PID。 启动清理会读取它，这样它就不会终止共享一个外
# 部提供的 TMUX_TMPDIR 的同级智能体服务器的实时会话。
#
TMUX_SOCKET_OWNER_OPTION: Final[str] = "@openhands_socket_owner_pid"

# tmux 套接字目录内的跨进程锁文件，该文件通过智能体服务器的启动清理来序列化套接字创建。
# 一个套接字只存在于创建和记录其所有者之间，因此这两个操作都使用这个锁来防止清理一个正在
# 设置的活进程的套接字。
#
TMUX_SOCKET_CREATION_LOCK: Final[str] = ".openhands-socket-creation.lock"

# tmux 会话维度（列 x 行）。 保持视口足够宽以用于常见命令输出，同时将回滚保留设置为
# HISTORY_LIMIT。 输出宽于 TMUX_SESSION_WIDTH 列将换行； 这是一个可接受的权衡，以避免过
# 大的 1000x1000 虚拟终端网格。
#
TMUX_SESSION_WIDTH: Final[int] = 256
TMUX_SESSION_HEIGHT: Final[int] = 200
