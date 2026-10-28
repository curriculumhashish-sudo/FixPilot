"""写入文件的 Gemini 工具的共享观测结果行为。

``edit`` 和 ``write_file`` 都报告已创建或更改的文件，并且都将结果呈现为差异。 唯一不
同的部分是宣布对现有文件进行更改的行，因此渲染位于此处，并且每
个工具都提供该行。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import PrivateAttr
from rich.text import Text

from openhands.sdk.tool import Observation


class FileChangeObservation(Observation, ABC):
    """观测结果报告已创建或重写的文件的基础。

    子类声明 ``file_path``、``is_new_file``、``old_content`` 和
    ``new_content`` 本身，以便每个工具保留自己的字段描述，并实现：meth:
    `change_summary`。
    """

    if TYPE_CHECKING:
        file_path: str | None
        is_new_file: bool
        old_content: str | None
        new_content: str | None

    _diff_cache: Text | None = PrivateAttr(default=None)

    @abstractmethod
    def change_summary(self) -> str:
        """返回现有文件更改时显示的行。"""

    @property
    def visualize(self) -> Text:
        """返回此观测结果的富文本表示形式。"""
        if self.is_error:
            return super().visualize

        text = Text()
        if self.file_path:
            if self.is_new_file:
                text.append("✨ ", style="green bold")
                text.append(f"Created: {self.file_path}\n", style="green")
            else:
                text.append("✏️  ", style="yellow bold")
                text.append(self.change_summary(), style="yellow")

            if self.old_content is not None and self.new_content is not None:
                from openhands.tools.file_editor.utils.diff import visualize_diff

                if not self._diff_cache:
                    self._diff_cache = visualize_diff(
                        self.file_path,
                        self.old_content,
                        self.new_content,
                        n_context_lines=2,
                        change_applied=True,
                    )
                text.append(self._diff_cache)
        return text
