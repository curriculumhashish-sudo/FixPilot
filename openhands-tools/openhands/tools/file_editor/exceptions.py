class ToolError(Exception):
    """当工具遇到错误时被触发。"""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return self.message


class EditorToolParameterMissingError(ToolError):
    """当工具命令缺少所需参数时引发。"""

    command: str
    parameter: str

    def __init__(self, command: str, parameter: str):
        self.command = command
        self.parameter = parameter
        self.message: str = (
            f"Parameter `{parameter}` is required for command: {command}."
        )


class EditorToolParameterInvalidError(ToolError):
    """当参数对于工具命令无效时引发。"""

    parameter: str
    value: str

    def __init__(self, parameter: str, value: str, hint: str | None = None):
        self.parameter = parameter
        self.value = value
        self.message: str = (
            f"Invalid `{parameter}` parameter: {value}. {hint}"
            if hint
            else f"Invalid `{parameter}` parameter: {value}."
        )


class FileValidationError(ToolError):
    """当文件未通过验证检查（大小、类型等）时引发。"""

    path: str
    reason: str

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        self.message: str = f"File validation failed for {path}: {reason}"
        super().__init__(self.message)
