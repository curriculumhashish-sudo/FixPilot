"""测试智能体是否可以使用 Jupyter IPython 写入文本文件。"""

import os

from openhands.sdk import get_logger
from tests.integration.base import BaseIntegrationTest, TestResult


INSTRUCTION = (
    "Use Jupyter IPython to write a text file in your workspace 'test.txt'"
    " containing 'hello world'."
)


logger = get_logger(__name__)


class JupyterWriteFileTest(BaseIntegrationTest):
    """测试智能体是否可以使用 Jupyter IPython 写入文本文件。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path: str = os.path.join(self.workspace, "test.txt")

    def setup(self) -> None:
        """不需要安装 - 智能体将根据需要创建目录。"""

    def verify_result(self) -> TestResult:
        """验证智能体是否使用 IPython 成功创建了文本文件。"""
        if not os.path.exists(self.file_path):
            return TestResult(
                success=False, reason=f"Text file '{self.file_path}' not found"
            )

        # 读取文件内容
        with open(self.file_path) as f:
            file_content = f.read().strip()

        # 检查文件是否包含预期的内容
        if "hello world" not in file_content.lower():
            return TestResult(
                success=False,
                reason=f"File does not contain 'hello world': {file_content}",
            )

        return TestResult(
            success=True,
            reason=f"Successfully created file with content: {file_content}",
        )
