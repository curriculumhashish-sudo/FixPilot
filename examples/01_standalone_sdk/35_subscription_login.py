"""Example: 使用 Codex 模型的 ChatGPT 订阅。

此示例演示如何使用您的 ChatGPT Plus/Pro 订阅来访问 OpenAI 的 Codex 模型，而无需消耗
API 积分。

subscription_login() 方法处理：
- OAuth PKCE 身份验证流程
- 用于远程/无头环境的设备代码身份验证
- 凭据 caching (~/.openhands/auth/)
- 自动token刷新

支持型号：
- gpt-5.2-法典
- GPT-5.2
- gpt-5.1-codex-max
- gpt-5.1-codex-mini

要求：
- 有效 ChatGPT Plus 或 Pro 订阅
- 用于初始 OAuth 登录的浏览器访问，或用于设备代码登录的其他浏览器/设备

环境变量：
- OPENHANDS_SUBSCRIPTION_MODEL: 要使用的模型（默认值：gpt-5.2-codex）
- OPENHANDS_SUBSCRIPTION_AUTH_METHOD: “浏览器”或“device_code”（默认：浏览器）
- OPENHANDS_SUBSCRIPTION_FORCE_LOGIN: 设置为“1”以强制重新登录
- SUBSCRIPTION_LOGIN_ONLY: 设置为“1”以验证登录而不运行智能体
"""

import os
from typing import Literal

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


AuthMethod = Literal["browser", "device_code"]


# 第一次：打开浏览器进行 OAuth 登录后续调用：重用缓存凭据（过期自动刷新）
#
model = os.getenv("OPENHANDS_SUBSCRIPTION_MODEL", "gpt-5.2-codex")
auth_method_env = os.getenv("OPENHANDS_SUBSCRIPTION_AUTH_METHOD", "browser")
if auth_method_env not in ("browser", "device_code"):
    raise ValueError(
        "OPENHANDS_SUBSCRIPTION_AUTH_METHOD must be 'browser' or 'device_code'"
    )
auth_method: AuthMethod = auth_method_env
force_login = os.getenv("OPENHANDS_SUBSCRIPTION_FORCE_LOGIN") == "1"

llm = LLM.subscription_login(
    vendor="openai",
    model=model,  # 或“gpt-5.2”、“gpt-5.1-codex-max”、“gpt-5.1-codex-mini”
    auth_method=auth_method,
    force_login=force_login,
)

# 替代方案：强制重新登录（如果凭据已过时，则很有用）
# llm = LLM.subscription_login(vendor="openai", model="gpt-5.2-codex", force_login=True)

# 替代方案：禁用自动打开浏览器（改为打印 URL 到控制台）
# llm = LLM.subscription_login(
#     vendor="openai", model="gpt-5.2-codex", open_browser=False
# )
#
# 替代方案：对远程/无头环境使用设备代码登录
# llm = LLM.subscription_login(
#     vendor="openai",
#     model="gpt-5.2-codex",
#     auth_method="device_code",
#     force_login=True,
# )

# 验证订阅模式是否处于活动状态
print(f"Using subscription mode: {llm.is_subscription}")
print(f"Model: {llm.model}")
print(f"Auth method: {auth_method}")

if os.getenv("SUBSCRIPTION_LOGIN_ONLY") == "1":
    print("Login verified; skipping agent run because SUBSCRIPTION_LOGIN_ONLY=1.")
    raise SystemExit(0)

# 像平常一样使用 LLM 和智能体
agent = Agent(
    llm=llm,
    tools=[
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ],
)

cwd = os.getcwd()
conversation = Conversation(agent=agent, workspace=cwd)

conversation.send_message("List the files in the current directory.")
conversation.run()
print("Done!")
