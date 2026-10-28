"""测试智能体是否可以浏览本地网页并提取信息。"""

import os
import re
import subprocess
import sys
import time

from openhands.sdk import get_logger
from openhands.sdk.conversation import get_agent_final_response
from tests.integration.base import BaseIntegrationTest, TestResult


INSTRUCTION = "Browse localhost:8000, and tell me the ultimate answer to life."

HTML_FILE = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '    <meta charset="UTF-8">\n'
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    "    <title>The Ultimate Answer</title>\n"
    "    <style>\n"
    "        body {\n"
    "            display: flex;\n"
    "            justify-content: center;\n"
    "            align-items: center;\n"
    "            height: 100vh;\n"
    "            margin: 0;\n"
    "            background: linear-gradient(to right, #1e3c72, #2a5298);\n"
    "            color: #fff;\n"
    "            font-family: 'Arial', sans-serif;\n"
    "            text-align: center;\n"
    "        }\n"
    "        .container {\n"
    "            text-align: center;\n"
    "            padding: 20px;\n"
    "            background: rgba(255, 255, 255, 0.1);\n"
    "            border-radius: 10px;\n"
    "            box-shadow: 0 0 10px rgba(0, 0, 0, 0.2);\n"
    "        }\n"
    "        h1 {\n"
    "            font-size: 36px;\n"
    "            margin-bottom: 20px;\n"
    "        }\n"
    "        p {\n"
    "            font-size: 18px;\n"
    "            margin-bottom: 30px;\n"
    "        }\n"
    "        #showButton {\n"
    "            padding: 10px 20px;\n"
    "            font-size: 16px;\n"
    "            color: #1e3c72;\n"
    "            background: #fff;\n"
    "            border: none;\n"
    "            border-radius: 5px;\n"
    "            cursor: pointer;\n"
    "            transition: background 0.3s ease;\n"
    "        }\n"
    "        #showButton:hover {\n"
    "            background: #f0f0f0;\n"
    "        }\n"
    "        #result {\n"
    "            margin-top: 20px;\n"
    "            font-size: 24px;\n"
    "        }\n"
    "    </style>\n"
    "</head>\n"
    "<body>\n"
    '    <div class="container">\n'
    "        <h1>The Ultimate Answer</h1>\n"
    "        <p>Click the button to reveal the answer to life, the universe, "
    "and everything.</p>\n"
    '        <button id="showButton">Click me</button>\n'
    '        <div id="result"></div>\n'
    "    </div>\n"
    "    <script>\n"
    "        document.getElementById('showButton').addEventListener('click', "
    "function() {\n"
    "            document.getElementById('result').innerText = "
    "'The answer is OpenHands is all you need!';\n"
    "        });\n"
    "    </script>\n"
    "</body>\n"
    "</html>\n"
)


logger = get_logger(__name__)


class SimpleBrowsingTest(BaseIntegrationTest):
    """测试智能体是否可以浏览本地网页并提取信息。"""

    INSTRUCTION: str = INSTRUCTION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_process: subprocess.Popen[bytes] | None = None

    @property
    def enable_browser(self) -> bool:
        """为此浏览测试启用浏览器工具。"""
        return True

    def setup(self) -> None:
        """使用 HTML 文件设置本地 Web 服务器。"""

        try:
            # 将HTML文件写入工作区
            html_path = os.path.join(self.workspace, "index.html")
            with open(html_path, "w") as f:
                f.write(HTML_FILE)

            # 在后台启动HTTP服务器
            self.server_process: subprocess.Popen[bytes] | None = subprocess.Popen(
                [sys.executable, "-m", "http.server", "8000", "--bind", "127.0.0.1"],
                cwd=self.workspace,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # 给服务器一点启动时间
            time.sleep(2)

            logger.info(f"Started HTTP server on port 8000 serving {html_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to set up web server: {e}")

    def verify_result(self) -> TestResult:
        """验证智能体是否已成功浏览该页面并找到答案。"""
        # 使用效用函数获得智能体的最终响应
        agent_response = get_agent_final_response(self.conversation.state.events)

        logger.info(f"Agent final response to analyze: {agent_response[:500]}...")

        # 使用正则表达式检查智能体是否找到了正确的答案。预期的答案是 "答案是 OpenHands
        # 就够了！" 我们会灵活处理措辞，但寻找关键组件
        #
        answer_patterns = [
            r"(?i)the answer is openhands is all you need",
            r"(?i)openhands is all you need",
            r"(?i)answer.*openhands.*all.*need",
        ]

        found_answer = False
        matched_pattern = None

        for pattern in answer_patterns:
            if re.search(pattern, agent_response):
                found_answer = True
                matched_pattern = pattern
                break

        if found_answer:
            return TestResult(
                success=True,
                reason=(
                    f"Agent successfully found the answer! "
                    f"Matched pattern: {matched_pattern}. "
                    f"Response contained the expected content about OpenHands."
                ),
            )
        else:
            return TestResult(
                success=False,
                reason=(
                    "Agent did not find the answer. "
                    f"Response: {agent_response[:200]}..."
                ),
            )

    def teardown(self):
        """关闭网络服务器并关闭对话。"""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            except Exception as e:
                logger.warning(f"Error terminating server process: {e}")

        logger.info("Cleaned up web server")
        super().teardown()
