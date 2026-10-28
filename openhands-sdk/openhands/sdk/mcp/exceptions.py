"""OpenHands SDK 的 MCP 相关异常。"""


class MCPError(Exception):
    """MCP 相关错误的基本异常。"""

    pass


class MCPTimeoutError(MCPError):
    """MCP 操作超时时引发异常。"""

    timeout: float
    config: dict | None

    def __init__(self, message: str, timeout: float, config: dict | None = None):
        self.timeout = timeout
        self.config = config
        super().__init__(message)
