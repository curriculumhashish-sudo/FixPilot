import base64
import mimetypes
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import get_args

from binaryornot.check import is_binary

from openhands.sdk import ImageContent, TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import is_host_absolute_path, to_posix_path
from openhands.sdk.utils.truncate import maybe_truncate
from openhands.tools.file_editor.definition import (
    CommandLiteral,
    FileEditorObservation,
)
from openhands.tools.file_editor.exceptions import (
    EditorToolParameterInvalidError,
    EditorToolParameterMissingError,
    FileValidationError,
    ToolError,
)
from openhands.tools.file_editor.utils.config import SNIPPET_CONTEXT_WINDOW
from openhands.tools.file_editor.utils.constants import (
    BINARY_FILE_CONTENT_TRUNCATED_NOTICE,
    DIRECTORY_CONTENT_TRUNCATED_NOTICE,
    MAX_RESPONSE_LEN_CHAR,
    TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
)
from openhands.tools.file_editor.utils.encoding import (
    EncodingManager,
    with_encoding,
)
from openhands.tools.file_editor.utils.history import FileHistoryManager


logger = get_logger(__name__)

# 支持查看 Base64 编码内容的图像扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _is_encodable(text: str, encoding: str) -> bool:
    """如果文本可以使用给定的编码进行编码，则返回 True。"""
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


class FileEditor:
    """
    一个文件系统编辑器工具，允许智能体
    - 查看
    - 创造
    - 导航
    - 编辑文件
    工具参数由 Anthropic 定义且不可编辑。

    原始实现：
    https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/computer_use_demo/tools/edit.py
    """  # noqa: E501

    MAX_FILE_SIZE_MB: int = 10  # 最大文件大小（MB）
    _history_manager: FileHistoryManager
    _max_file_size: int
    _encoding_manager: EncodingManager
    _cwd: str

    def __init__(
        self,
        workspace_root: str | None = None,
        max_file_size_mb: int | None = None,
    ):
        """初始化编辑器。

        Args:
            max_file_size_mb: 最大文件大小（以 MB 为单位）。 如果 None，则使用默认值
                MAX_FILE_SIZE_MB.
            workspace_root: 作为当前工作的根目录
                相对路径建议的目录。 必须是绝对路径。 如果为 None，则不会为相对路径提
                供路径建议。
        """
        self._history_manager = FileHistoryManager(max_history_per_file=10)
        self._max_file_size = (
            (max_file_size_mb or self.MAX_FILE_SIZE_MB) * 1024 * 1024
        )  # 转换为字节

        # 初始化编码管理器
        self._encoding_manager = EncodingManager()

        # 如果提供了 workspace_root，则设置 cwd（当前工作目录）
        if workspace_root is not None:
            workspace_path = Path(workspace_root)
            # 确保 workspace_root 是绝对路径
            if not workspace_path.is_absolute():
                workspace_path = workspace_path.resolve()
            self._cwd = str(workspace_path)
        else:
            self._cwd = os.path.abspath(os.getcwd())
        logger.info(f"FileEditor initialized with cwd: {self._cwd}")

    def __call__(
        self,
        *,
        command: CommandLiteral,
        path: str,
        file_text: str | None = None,
        view_range: list[int] | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
    ) -> FileEditorObservation:
        _path = Path(path)
        self.validate_path(command, _path)
        if command == "view":
            return self.view(_path, view_range)
        elif command == "create":
            if file_text is None:
                raise EditorToolParameterMissingError(command, "file_text")
            self.write_file(_path, file_text)
            self._history_manager.add_history(_path, file_text)
            return FileEditorObservation.from_text(
                text=f"File created successfully at: {_path}",
                command=command,
                path=str(_path),
                new_content=file_text,
                prev_exist=False,
            )
        elif command == "str_replace":
            if old_str is None:
                raise EditorToolParameterMissingError(command, "old_str")
            if new_str is None:
                raise EditorToolParameterMissingError(command, "new_str")
            if new_str == old_str:
                raise EditorToolParameterInvalidError(
                    "new_str",
                    new_str,
                    "No replacement was performed. `new_str` and `old_str` must be "
                    "different.",
                )
            return self.str_replace(_path, old_str, new_str)
        elif command == "insert":
            if insert_line is None:
                raise EditorToolParameterMissingError(command, "insert_line")
            if new_str is None:
                raise EditorToolParameterMissingError(command, "new_str")
            return self.insert(_path, insert_line, new_str)
        elif command == "undo_edit":
            return self.undo_edit(_path)

        raise ToolError(
            f"Unrecognized command {command}. The allowed commands for "
            f"{self.__class__.__name__} tool are: {', '.join(get_args(CommandLiteral))}"
        )

    @with_encoding
    def _count_lines(self, path: Path, encoding: str = "utf-8") -> int:
        """
        安全地计算文件中的行数。

        Args:
            path: 文件路径
            encoding: 读取文件时使用的编码（由
                装饰器）

        Returns:
            文件中的行数
        """
        with open(path, encoding=encoding) as f:
            return sum(1 for _ in f)

    @with_encoding
    def str_replace(
        self,
        path: Path,
        old_str: str,
        new_str: str | None,
    ) -> FileEditorObservation:
        """
        执行str_replace命令，将文件内容中的old_str替换为new_str。

        Args:
            path: 文件路径
            old_str: 要替换的字符串
            new_str: 替换弦
            enable_linting: 是否对更改运行静态检查
            encoding: 要使用的编码（由装饰器自动检测）
        """
        self.validate_file(path)
        new_str = new_str or ""

        # 首先读取整个文件，以处理单行和多行替换
        #
        file_content = self.read_file(path)

        # 使用正则表达式查找所有出现的情况转义 old_str 中的特殊正则表达式字符以字面匹配
        #
        pattern = re.escape(old_str)
        occurrences = [
            (
                file_content.count("\n", 0, match.start()) + 1,  # 行号
                match.group(),  # 匹配的文本
                match.start(),  # 起始位置
            )
            for match in re.finditer(pattern, file_content)
        ]

        if not occurrences:
            # 我们没有发现任何出现的情况，可能是因为字符串前面或后面有多余的空格。 仅删
            # 除 old_str 至重试 * 匹配 *。 执行不剥离 new_str：它是替换内容，剥离它会默
            # 默地删除有意义的前导/尾随空白 (e.g. Markdown 强硬路线
            #
            # break or intentional indentation) the caller asked to write.
            old_str = old_str.strip()
            pattern = re.escape(old_str)
            occurrences = [
                (
                    file_content.count("\n", 0, match.start()) + 1,  # 行号
                    match.group(),  # 匹配的文本
                    match.start(),  # 起始位置
                )
                for match in re.finditer(pattern, file_content)
            ]
            if not occurrences:
                raise ToolError(
                    f"No replacement was performed, old_str `{old_str}` did not "
                    f"appear verbatim in {path}."
                )
        if len(occurrences) > 1:
            line_numbers = sorted(set(line for line, _, _ in occurrences))
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str "
                f"`{old_str}` in lines {line_numbers}. Please ensure it is unique."
            )

        # 我们恰好发现了一个现象
        replacement_line, matched_text, idx = occurrences[0]

        # 通过仅替换匹配的文本来创建新内容
        new_file_content = (
            file_content[:idx] + new_str + file_content[idx + len(matched_text) :]
        )

        # 将新内容写入文件
        self.write_file(path, new_file_content)

        # 将内容保存到历史记录
        self._history_manager.add_history(path, file_content)

        # 创建已编辑部分的片段
        start_line = max(0, replacement_line - SNIPPET_CONTEXT_WINDOW)
        end_line = replacement_line + SNIPPET_CONTEXT_WINDOW + new_str.count("\n")

        # 仅读取片段范围
        snippet = self.read_file(path, start_line=start_line + 1, end_line=end_line)

        # 准备成功消息
        success_message = f"The file {path} has been edited. "
        success_message += self._make_output(
            snippet, f"a snippet of {path}", start_line + 1
        )

        success_message += (
            "Review the changes and make sure they are as expected. Edit the "
            "file again if necessary."
        )
        return FileEditorObservation.from_text(
            text=success_message,
            command="str_replace",
            prev_exist=True,
            path=str(path),
            old_content=file_content,
            new_content=new_file_content,
        )

    def view(
        self, path: Path, view_range: list[int] | None = None
    ) -> FileEditorObservation:
        """
        查看文件或目录的内容。
        """
        if path.is_dir():
            if view_range:
                raise EditorToolParameterInvalidError(
                    "view_range",
                    str(view_range),
                    "The `view_range` parameter is not allowed when `path` points to "
                    "a directory.",
                )

            try:
                hidden_count = self._count_hidden_children(path)
                formatted_paths = self._list_directory_for_view(path)
            except OSError as e:
                return FileEditorObservation.from_text(
                    text=str(e),
                    command="view",
                    is_error=True,
                    path=str(path),
                    prev_exist=True,
                )

            msg = [
                f"Here's the files and directories up to 2 levels deep in {path}, "
                "excluding hidden items:\n" + "\n".join(formatted_paths)
            ]
            if hidden_count > 0:
                msg.append(
                    f"\n{hidden_count} hidden files/directories in this directory "
                    f"are excluded. You can use 'ls -la {path}' to see them."
                )
            stdout = maybe_truncate(
                "\n".join(msg),
                truncate_after=MAX_RESPONSE_LEN_CHAR,
                truncate_notice=DIRECTORY_CONTENT_TRUNCATED_NOTICE,
            )
            return FileEditorObservation.from_text(
                text=stdout,
                command="view",
                path=str(path),
                prev_exist=True,
            )

        # 检查文件是否是图像
        file_extension = path.suffix.lower()
        if file_extension in IMAGE_EXTENSIONS:
            # 将图像文件读取为 base64
            try:
                with open(path, "rb") as f:
                    image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                mime_type, _ = mimetypes.guess_type(str(path))
                if not mime_type or not mime_type.startswith("image/"):
                    mime_type = "image/png"
                output_msg = (
                    f"Image file {path} read successfully. Displaying image content."
                )
                image_url = f"data:{mime_type};base64,{image_base64}"
                return FileEditorObservation(
                    command="view",
                    content=[
                        TextContent(text=output_msg),
                        ImageContent(image_urls=[image_url]),
                    ],
                    path=str(path),
                    prev_exist=True,
                )
            except Exception as e:
                raise ToolError(f"Failed to read image file {path}: {e}") from None

        # 验证文件并计算行数
        self.validate_file(path)
        try:
            num_lines = self._count_lines(path)
        except UnicodeDecodeError as e:
            raise ToolError(
                f"Cannot view {path}: file contains binary content that cannot be "
                f"decoded as text. Error: {e}"
            ) from None

        start_line = 1
        if not view_range:
            file_content = self.read_file(path)
            output = self._make_output(file_content, str(path), start_line)

            return FileEditorObservation.from_text(
                text=output,
                command="view",
                path=str(path),
                prev_exist=True,
            )

        if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                "It should be a list of two integers.",
            )

        start_line, end_line = view_range
        if start_line < 1 or start_line > num_lines:
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                f"Its first element `{start_line}` should be within the range of "
                f"lines of the file: {[1, num_lines]}.",
            )

        # 规范化 end_line 并在超出文件长度时发出警告
        warning_message: str | None = None
        if end_line == -1:
            end_line = num_lines
        elif end_line > num_lines:
            warning_message = (
                f"We only show up to {num_lines} since there're only {num_lines} "
                "lines in this file."
            )
            end_line = num_lines

        if end_line < start_line:
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                f"Its second element `{end_line}` should be greater than or equal "
                f"to the first element `{start_line}`.",
            )

        file_content = self.read_file(path, start_line=start_line, end_line=end_line)
        file_content = self._normalize_lines(file_content)

        output = self._make_output(file_content, str(path), start_line)

        # 如果我们截断 end_line 则添加警告
        if warning_message:
            output = f"NOTE: {warning_message}\n{output}"

        return FileEditorObservation.from_text(
            text=output,
            command="view",
            path=str(path),
            prev_exist=True,
        )

    def _format_directory_entry(self, root: Path, entry: Path) -> str:
        root_display = to_posix_path(root)
        if entry == root:
            display = root_display
        else:
            display = f"{root_display}/{to_posix_path(entry.relative_to(root))}"
        if entry.is_dir():
            return f"{display}/"
        return display

    def _count_hidden_children(self, path: Path) -> int:
        return sum(1 for item in path.iterdir() if item.name.startswith("."))

    def _list_directory_for_view(self, path: Path) -> list[str]:
        visible_entries = [path]
        for item in sorted(path.iterdir(), key=lambda p: str(p)):
            if item.name.startswith("."):
                continue
            visible_entries.append(item)
            if item.is_dir():
                try:
                    visible_entries.extend(
                        child
                        for child in sorted(item.iterdir(), key=lambda p: str(p))
                        if not child.name.startswith(".")
                    )
                except OSError:
                    pass
        return [self._format_directory_entry(path, entry) for entry in visible_entries]

    @with_encoding
    def write_file(self, path: Path, file_text: str, encoding: str = "utf-8") -> None:
        """
        将文件内容写入给定路径； 如果发生错误，则引发 ToolError。

        Args:
            path: 要写入的文件的路径
            file_text: 要写入文件的内容
            encoding: 写入文件时使用的编码（由
                装饰器）
        """
        self.validate_file(path)
        try:
            self._atomic_write(path, file_text, encoding)
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to write to {path}") from None

    def _atomic_write(self, path: Path, file_text: str, encoding: str) -> None:
        """以原子方式将 file_text 写入路径，永远不会留下被截断的文件。

        内容被写入同一目录下的临时文件中，然后 Path.replace一旦数据写入，那么任何失败
        的写入都不会破坏原始文件。 如果检测到的文件编码无法表示新内容，
        fallback 到  UTF-8 一个编辑可能会添加字符（箭头，表情符号，） CJK... 由于原始
        的单字节编码缺乏这些，而是失败并截断文件。 注意回退方
        案将整个文件转码为 UTF-8.
        """
        default = self._encoding_manager.default_encoding
        if encoding != default and not _is_encodable(file_text, encoding):
            logger.warning(
                f"Detected encoding '{encoding}' cannot represent the new content "
                f"for {path}; writing as '{default}' instead."
            )
            encoding = default

        with self._temp_file(path, file_text, encoding) as tmp_path:
            # 当原始文件已存在时，保留其权限位。
            if path.exists():
                os.chmod(tmp_path, os.stat(path).st_mode & 0o7777)
            Path.replace(tmp_path, path)

    @contextmanager
    def _temp_file(self, path: Path, file_text: str, encoding: str) -> Iterator[Path]:
        """将 file_text 写入路径旁边的新临时文件并生成其路径。

        发生任何故障（写入、chmod 或替换）时，临时文件都会被删除，因此原始文件永远不
        会被破坏，并且不会留下任何杂散临时文件。 由于 Windows 无法删除打
        开的文件，因此取消链接会在文件关闭后运行。
        """
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            encoding=encoding,
            delete=False,
        )
        tmp_path = Path(tmp.name)
        try:
            with tmp:
                tmp.write(file_text)
            yield tmp_path
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    @with_encoding
    def insert(
        self,
        path: Path,
        insert_line: int,
        new_str: str,
        encoding: str = "utf-8",
    ) -> FileEditorObservation:
        """
        实现插入命令，该命令在文件内容中的指定行插入new_str。

        Args:
            path: 文件路径
            insert_line: 插入新内容的行号
            new_str: 要插入的内容
            enable_linting: 是否对更改运行静态检查
            encoding: 要使用的编码（由装饰器自动检测）
        """
        # 验证文件并计算行数
        self.validate_file(path)
        num_lines = self._count_lines(path)

        if insert_line < 0 or insert_line > num_lines:
            raise EditorToolParameterInvalidError(
                "insert_line",
                str(insert_line),
                f"It should be within the range of allowed values: {[0, num_lines]}",
            )

        new_str_lines = new_str.split("\n")

        # 在内存中构建新内容，然后以原子方式写入。 通过 write_file 路由写入与其他所有编
        # 辑一样，重复使用相同的原子、编码安全路径（无截断，新字符为 UTF-8 回退方案）。
        #
        new_lines: list[str] = []
        history_lines: list[str] = []
        with open(path, encoding=encoding) as f:
            for i, line in enumerate(f, 1):
                if i > insert_line:
                    break
                new_lines.append(line)
                history_lines.append(line)

        # 插入新内容
        for line in new_str_lines:
            new_lines.append(line + "\n")

        # 复制剩余的行并将其保存为历史记录
        with open(path, encoding=encoding) as f:
            for i, line in enumerate(f, 1):
                if i <= insert_line:
                    continue
                new_lines.append(line)
                history_lines.append(line)

        self.write_file(path, "".join(new_lines))

        # 仅读取片段范围
        start_line = max(0, insert_line - SNIPPET_CONTEXT_WINDOW)
        end_line = min(
            num_lines + len(new_str_lines),
            insert_line + SNIPPET_CONTEXT_WINDOW + len(new_str_lines),
        )
        snippet = self.read_file(path, start_line=start_line + 1, end_line=end_line)

        # 保存历史记录 - 我们已经在内存中保存了这些行
        file_text = "".join(history_lines)
        self._history_manager.add_history(path, file_text)

        # 阅读新内容以获得结果
        new_file_text = self.read_file(path)

        success_message = f"The file {path} has been edited. "
        success_message += self._make_output(
            snippet,
            "a snippet of the edited file",
            max(1, insert_line - SNIPPET_CONTEXT_WINDOW + 1),
        )

        success_message += (
            "Review the changes and make sure they are as expected (correct "
            "indentation, no duplicate lines, etc). Edit the file again if necessary."
        )
        return FileEditorObservation.from_text(
            text=success_message,
            command="insert",
            prev_exist=True,
            path=str(path),
            old_content=file_text,
            new_content=new_file_text,
        )

    def validate_path(self, command: CommandLiteral, path: Path) -> None:
        """
        检查路径/命令组合是否有效。

        验证：
        1. 路径是绝对的
        2. 路径和命令兼容
        """
        # 检查它是否是当前主机文件系统上的绝对路径。
        if not is_host_absolute_path(path):
            suggestion_message = "The path should be an absolute path."

            # 如果提供了 cwd 并且路径存在，则仅建议绝对路径
            if self._cwd is not None:
                suggested_path = Path(self._cwd) / path
                if suggested_path.exists():
                    suggestion_message += f" Maybe you meant {suggested_path}?"

            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                suggestion_message,
            )

        # 检查路径和命令是否兼容
        if command == "create" and path.exists():
            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                f"File already exists at: {path}. Cannot overwrite files using "
                "command `create`.",
            )
        if command != "create" and not path.exists():
            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                f"The path {path} does not exist. Please provide a valid path.",
            )
        if command != "view":
            if path.is_dir():
                raise EditorToolParameterInvalidError(
                    "path",
                    str(path),
                    f"The path {path} is a directory and only the `view` command can "
                    "be used on directories.",
                )

    def undo_edit(self, path: Path) -> FileEditorObservation:
        """
        执行undo_edit命令。
        """
        current_text = self.read_file(path)
        old_text = self._history_manager.pop_last_history(path)
        if old_text is None:
            raise ToolError(f"No edit history found for {path}.")

        self.write_file(path, old_text)

        return FileEditorObservation.from_text(
            text=(
                f"Last edit to {path} undone successfully. "
                f"{self._make_output(old_text, str(path))}"
            ),
            command="undo_edit",
            path=str(path),
            prev_exist=True,
            old_content=current_text,
            new_content=old_text,
        )

    def validate_file(self, path: Path) -> None:
        """
        验证文件的读取或编辑操作。

        Args:
            path: 要验证的文件的路径

        Raises:
            FileValidationError: 如果文件失败验证
        """
        # 对于目录或不存在的文件跳过验证（对于创建命令）
        if not path.exists() or not path.is_file():
            return

        # 检查文件大小
        file_size = os.path.getsize(path)
        max_size = self._max_file_size
        if file_size > max_size:
            raise FileValidationError(
                path=str(path),
                reason=(
                    f"File is too large ({file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum allowed size is {int(max_size / 1024 / 1024)}MB."
                ),
            )

        # 检查文件类型 - 允许图像文件
        file_extension = path.suffix.lower()
        if is_binary(str(path)) and file_extension not in IMAGE_EXTENSIONS:
            # binaryornot 仅对第一个块进行采样，因此非 UTF-8 (e.g. cp1251) 或非 ASCII 文
            # 本文件可能会被错误分类为二进制文件。 使用编辑器将使用的编码解码整个文件，
            # 如果它是干净文本则接受它。
            #
            if self._is_decodable_text(path):
                return
            raise FileValidationError(
                path=str(path),
                reason=(
                    "File appears to be binary and this file type cannot be read "
                    "or edited by this tool."
                ),
            )

    def _is_decodable_text(self, path: Path) -> bool:
        """如果文件以已知编码解码为干净文本，则返回 True。

        用于覆盖非 UTF-8 文本文件的二进制或错误分类。
        """
        return self._encoding_manager.resolve_text_encoding(path) is not None

    @with_encoding
    def read_file(
        self,
        path: Path,
        start_line: int | None = None,
        end_line: int | None = None,
        encoding: str = "utf-8",  # 默认值将被装饰器覆盖
    ) -> str:
        """
        从给定路径读取文件内容； 如果发生错误，则引发 ToolError。

        Args:
            path: 要读取的文件的路径
            start_line: 可选的起始行号（从 1 开始）。 如果提供
                end_line，只读取该范围。
            end_line: 可选的结束行号（从 1 开始）。 必须提供
                start_line.
            encoding: 读取文件时使用的编码（由
                装饰器）
        """
        self.validate_file(path)
        try:
            if start_line is not None and end_line is not None:
                # 只读指定行范围
                lines = []
                with open(path, encoding=encoding) as f:
                    for i, line in enumerate(f, 1):
                        if i > end_line:
                            break
                        if i >= start_line:
                            lines.append(line)
                return "".join(lines)
            elif start_line is not None or end_line is not None:
                raise ValueError(
                    "Both start_line and end_line must be provided together"
                )
            else:
                # 使用逐行读取以避免将整个文件加载到内存中
                with open(path, encoding=encoding) as f:
                    return "".join(f)
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    def _normalize_lines(self, content: str) -> str:
        """重新加入模板片段，无需折叠外来行分隔符。

        ``read_file`` 返回一个由换行符分隔的片段 ``\\n``. The ranged ``view`` 用于来
        回传输的路径
        ``str.splitlines()``，它也会破坏换页符和 Unicode 分隔符 REST 编辑器将它们视为
        普通字符，移动行号。 加入 ``\\n``
        而是保留了所有其他字符。
        """
        return "\n".join(content.split("\n"))

    def _make_output(
        self,
        snippet_content: str,
        snippet_description: str,
        start_line: int = 1,
        is_converted_markdown: bool = False,
    ) -> str:
        """
        根据代码片段的内容生成 CLI 的输出。
        """
        # 如果内容是从Markdown转换过来的，我们就不需要行号
        if is_converted_markdown:
            snippet_content = maybe_truncate(
                snippet_content,
                truncate_after=MAX_RESPONSE_LEN_CHAR,
                truncate_notice=BINARY_FILE_CONTENT_TRUNCATED_NOTICE,
            )
            return (
                f"Here's the content of the file {snippet_description} displayed in "
                "Markdown format:\n" + snippet_content + "\n"
            )

        snippet_content = maybe_truncate(
            snippet_content,
            truncate_after=MAX_RESPONSE_LEN_CHAR,
            truncate_notice=TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
        )

        # 按“”分割\n仅匹配  read_file/_count_lines 定义行，以便于字符 splitlines() 视为
        # 换行符 (\x0c, \u2028, ...) 保持插入线号一致view_range. 终止换行符结束最后一行
        # 而不是添加空白行，因此删除它生成的空字段。
        #
        lines = snippet_content.split("\n")
        if lines[-1] == "":
            lines.pop()
        snippet_content = "\n".join(
            [f"{i + start_line:6}\t{line}" for i, line in enumerate(lines)]
        )
        output = f"Here's the result of running `cat -n` on {snippet_description}:\n"
        if snippet_content:
            output += snippet_content + "\n"
        return output
