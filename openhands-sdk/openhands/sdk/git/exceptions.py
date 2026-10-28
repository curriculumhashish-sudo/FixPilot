"""OpenHands SDK 的与 Git 相关的异常。"""


class GitError(Exception):
    """与 git 相关的错误的基本异常。"""

    pass


class GitRepositoryError(GitError):
    """git 存储库操作失败时引发异常。"""

    command: str | None
    exit_code: int | None

    def __init__(
        self, message: str, command: str | None = None, exit_code: int | None = None
    ):
        self.command = command
        self.exit_code = exit_code
        super().__init__(message)


class GitCommandError(GitError):
    """git 命令执行失败时引发异常。"""

    command: list[str]
    exit_code: int
    stderr: str

    def __init__(
        self, message: str, command: list[str], exit_code: int, stderr: str = ""
    ):
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(message)


class GitPathError(GitError):
    """git 路径操作失败时引发异常。"""

    pass
