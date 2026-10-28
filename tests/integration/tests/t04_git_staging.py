"""测试智能体是否可以写入 git 提交消息并提交更改。"""

import os
import subprocess

from openhands.sdk import get_logger
from tests.integration.base import BaseIntegrationTest, TestResult


INSTRUCTION = (
    "Write a git commit message for the current staging area and commit the changes."
)


logger = get_logger(__name__)


class GitStagingTest(BaseIntegrationTest):
    """测试智能体是否可以写入 git 提交消息并提交更改。"""

    INSTRUCTION: str = INSTRUCTION

    def setup(self) -> None:
        """设置包含分阶段更改的 git 存储库。"""
        # 初始化git仓库
        subprocess.run(
            ["git", "init"], cwd=self.workspace, check=True, capture_output=True
        )

        # 配置 git 用户（提交所需）
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.workspace,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.workspace,
            check=True,
            capture_output=True,
        )

        # 创建Python文件
        hello_py_path = os.path.join(self.workspace, "hello.py")
        with open(hello_py_path, "w") as f:
            f.write('print("hello world")\n')

        # 暂存文件
        subprocess.run(
            ["git", "add", "hello.py"],
            cwd=self.workspace,
            check=True,
            capture_output=True,
        )

        logger.info("Set up git repository with staged hello.py file")

    def verify_result(self) -> TestResult:
        """验证智能体是否成功提交了分阶段更改。"""

        try:
            # 检查 git status 以查看是否还有任何暂存的更改
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )

            # 如果仍然存在分阶段更改，则提交未发生
            if "hello.py" in status_result.stdout.strip():
                return TestResult(
                    success=False,
                    reason=f"File to commit still staged: {status_result.stdout}",
                )

            # 检查是否有任何提交
            log_result = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )

            if not log_result.stdout.strip():
                return TestResult(
                    success=False,
                    reason=f"No commits found in repository: {log_result.stdout}",
                )

            # 获取最新的提交消息
            commit_msg_result = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%s"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )

            commit_message = commit_msg_result.stdout.strip()

            # 验证提交包含 hello.py 文件
            show_result = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )

            if "hello.py" not in show_result.stdout:
                return TestResult(
                    success=False,
                    reason="hello.py not found in the committed changes",
                )

            return TestResult(
                success=True,
                reason=(
                    f"Successfully committed changes with message: '{commit_message}'"
                ),
            )

        except subprocess.CalledProcessError as e:
            return TestResult(success=False, reason=f"Git command failed: {e}")
