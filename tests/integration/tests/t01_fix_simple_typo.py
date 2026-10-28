"""测试智能体是否可以使用 BaseIntegrationTest 修复文本文件中的拼写错误。"""

import os

from openhands.sdk import get_logger
from tests.integration.base import BaseIntegrationTest, TestResult


INSTRUCTION = (
    "Please fix all the typos in the file 'document.txt' that is in "
    "the current directory. "
    "Read the file first, identify the typos, and correct them. "
)

TYPO_CONTENT = """
This is a sample documnet with three typos that need to be fixed.
The purpse of this document is to test the agent's ability to correct spelling mistakes.
Please fix all the mispelled words in this document.
"""


logger = get_logger(__name__)


class TypoFixTest(BaseIntegrationTest):
    """测试智能体是否可以修复文本文件中的拼写错误。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_path: str = os.path.join(self.workspace, "document.txt")

    def setup(self) -> None:
        """创建一个包含拼写错误的文本文件，智能体用于修复。"""
        # 创建带有拼写错误的测试文件
        typo_content = TYPO_CONTENT
        with open(self.document_path, "w") as f:
            f.write(typo_content)

        logger.info(f"Created test document with typos at: {self.document_path}")

    def verify_result(self) -> TestResult:
        """验证智能体是否成功修复了拼写错误。"""
        if not os.path.exists(self.document_path):
            return TestResult(
                success=False, reason="Document file not found after agent execution"
            )
        with open(self.document_path) as f:
            corrected_content = f.read()

        are_typos_fixed: bool = (
            "document" in corrected_content
            and "purpose" in corrected_content
            and "misspelled" in corrected_content
        )
        if are_typos_fixed:
            return TestResult(success=True, reason="Successfully fixed all typos")
        else:
            return TestResult(
                success=False,
                reason=f"Typos were not fully corrected:\n{corrected_content}",
            )
