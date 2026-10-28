#!/usr/bin/env python3
"""
Datadog调试示例

此示例演示如何使用 OpenHands 智能体调试 Datadog 中记录的错误。 智能体将：
1. 使用curl命令查询Datadog日志以了解错误
2. 使用 git 命令克隆相关 GitHub 存储库
3. 分析代码库以确定潜在原因
4. 尝试重现错误
5. （可选）创建包含修复的草稿 PR

用途：
    python 26_datadog_debugging.py --query "status:error service:deploy" \\
        --repos "All-Hands-AI/OpenHands,All-Hands-AI/deploy"

环境变量必填：
    - DD_API_KEY: 您的 Datadog API 密钥
    - DD_APP_KEY: 您的 Datadog 应用程序密钥
    - DD_SITE: （可选）Datadog 站点（e.g.、datadoghq.com、datadoghq.eu）
    - GITHUB_TOKEN: 您的 GitHub 个人访问令牌
    - LLM_API_KEY: LLM 服务的 API 键
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader
from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    Event,
    LLMConvertibleEvent,
    Message,
    TextContent,
    get_logger,
)
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool


logger = get_logger(__name__)


def validate_environment():
    """验证所有必需的环境变量均已设置。"""
    required_vars = [
        "DD_API_KEY",
        "DD_APP_KEY",
        "GITHUB_TOKEN",
        "LLM_API_KEY",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        for var in missing_vars:
            print(f"  export {var}=your_key_here")
        return False

    return True


def fetch_datadog_errors(
    query: str, working_dir: Path, query_type: str = "log-query", limit: int = 5
) -> Path:
    """
    从 Datadog 获取错误示例并保存到 JSON 文件。

    Args:
        query: Datadog 查询字符串（搜索查询或错误跟踪 ID）
        working_dir: 保存错误示例的目录
        query_type: 查询类型 - “日志查询”（使用日志 API）或
            “log-error-id”（使用错误跟踪 API）
        limit: 要获取的错误示例的最大数量（默认值：5）

    Returns:
        包含错误示例的 JSON 文件的路径
    """
    dd_api_key = os.getenv("DD_API_KEY")
    dd_app_key = os.getenv("DD_APP_KEY")
    dd_site = os.getenv("DD_SITE", "datadoghq.com")

    error_examples = []

    if query_type == "log-error-id":
        # 使用 GET 端点按 ID 获取特定错误
        api_url = f"https://api.{dd_site}/api/v2/error-tracking/issues/{query}"

        print("📡 Fetching specific error from Datadog...")
        print(f"   Error ID: {query}")
        print(f"   API: {api_url}")

        headers = {
            "DD-API-KEY": dd_api_key,
            "DD-APPLICATION-KEY": dd_app_key,
        }

        try:
            response = requests.get(api_url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print("❌ Error: Request to Datadog API timed out")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching from Datadog API: {e}")
            sys.exit(1)

        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing Datadog API response: {e}")
            print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        # 检查是否有 API 个错误
        if "errors" in response_data:
            print(f"❌ Datadog API error: {response_data['errors']}")
            sys.exit(1)

        # 从 GET 响应中提取错误详细信息
        data = response_data.get("data", {})
        attrs = data.get("attributes", {})

        error_example = {
            "example_number": 1,
            "issue_id": query,
            "service": attrs.get("service"),
            "error_type": attrs.get("error_type"),
            "error_message": attrs.get("error_message", ""),
            "file_path": attrs.get("file_path"),
            "function_name": attrs.get("function_name"),
            "first_seen": attrs.get("first_seen"),
            "last_seen": attrs.get("last_seen"),
            "state": attrs.get("state"),
            "platform": attrs.get("platform"),
            "languages": attrs.get("languages", []),
        }
        error_examples.append(error_example)

    else:  # 日志查询
        api_url = f"https://api.{dd_site}/api/v2/logs/events/search"

        # 计算时间戳（30 天前）
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        # 构建日志的请求正文 API
        request_body = {
            "filter": {
                "query": query,
                "from": thirty_days_ago.isoformat() + "Z",
                "to": now.isoformat() + "Z",
            },
            "page": {"limit": limit},
            "sort": "-timestamp",
        }

        print(f"📡 Fetching up to {limit} log entries from Datadog...")
        print(f"   Query: {query}")
        print(f"   API: {api_url}")

        headers = {
            "Content-Type": "application/json",
            "DD-API-KEY": dd_api_key,
            "DD-APPLICATION-KEY": dd_app_key,
        }

        try:
            response = requests.post(
                api_url, headers=headers, json=request_body, timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print("❌ Error: Request to Datadog API timed out")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching from Datadog API: {e}")
            sys.exit(1)

        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing Datadog API response: {e}")
            print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        # 检查是否有 API 个错误
        if "errors" in response_data:
            print(f"❌ Datadog API error: {response_data['errors']}")
            sys.exit(1)

        # 提取并格式化日志条目
        log_entries = response_data.get("data", [])

        if log_entries:
            for idx, log_entry in enumerate(log_entries[:limit], 1):
                log_id = log_entry.get("id", "")
                log_attrs = log_entry.get("attributes", {})

                # 从日志条目中提取相关字段
                error_example = {
                    "example_number": idx,
                    "log_id": log_id,
                    "service": log_attrs.get("service"),
                    "host": log_attrs.get("host"),
                    "message": log_attrs.get("message", ""),
                    "status": log_attrs.get("status"),
                    "timestamp": log_attrs.get("timestamp"),
                    "tags": log_attrs.get("tags", []),
                    "attributes": log_attrs.get("attributes", {}),
                }
                error_examples.append(error_example)

    # 保存到文件
    errors_file = working_dir / "datadog_errors.json"
    with open(errors_file, "w") as f:
        json.dump(
            {
                "query": query,
                "fetch_time": "now",
                "total_examples": len(error_examples),
                "examples": error_examples,
            },
            f,
            indent=2,
        )

    print(f"✅ Fetched {len(error_examples)} error examples")
    print(f"📄 Saved to: {errors_file}")
    return errors_file


def create_unique_identifier(query: str, errors_data: dict) -> str:
    """
    根据查询或问题 ID 创建错误的唯一标识符。

    Args:
        query: Datadog 查询字符串
        errors_data: 来自datadog_errors.json的解析错误数据

    Returns:
        唯一标识符字符串
    """
    # 检查我们是否有特定的问题 ID
    examples = errors_data.get("examples", [])
    if examples and examples[0].get("issue_id"):
        issue_id = examples[0]["issue_id"]
        return f"error-id: {issue_id}"
    else:
        # 使用查询作为标识符
        return f"query: {query}"


def search_existing_issue(
    issue_repo: str, identifier: str, github_token: str
) -> int | None:
    """
    搜索包含该标识符的现有 GitHub 个问题。

    Args:
        issue_repo: 存储库格式为“所有者/存储库”
        identifier: 要搜索的唯一标识符
        github_token: GitHub API token

    Returns:
        如果找到则为问题编号，否则为 None
    """
    print(f"🔍 Searching for existing issue with identifier: {identifier}")

    # 在存储库中搜索问题
    search_query = f'repo:{issue_repo} is:issue "{identifier}"'
    url = "https://api.github.com/search/issues"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    params = {"q": search_query}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if items:
            # 按 created_at 排序以获取最旧的问题（首先创建）
            items_sorted = sorted(items, key=lambda x: x["created_at"])
            issue_number = items_sorted[0]["number"]
            print(f"✅ Found existing issue #{issue_number} (oldest of {len(items)})")
            return issue_number
        else:
            print("❌ No existing issue found")
            return None
    except (
        requests.exceptions.RequestException,
        json.JSONDecodeError,
        KeyError,
    ) as e:
        print(f"⚠️  Error searching for issues: {e}")
        return None


def create_github_issue(
    issue_repo: str,
    title: str,
    body: str,
    github_token: str,
) -> int:
    """
    创建一个新的 GitHub 问题。

    Args:
        issue_repo: 存储库格式为“所有者/存储库”
        title: 问题标题
        body: 问题正文内容
        github_token: GitHub API token

    Returns:
        创建问题编号
    """
    print(f"📝 Creating new issue: {title}")

    url = f"https://api.github.com/repos/{issue_repo}/issues"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    payload = {"title": title, "body": body}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating issue: {e}")
        if hasattr(e, "response") and e.response:
            print(f"Response: {e.response.text[:500]}")
        sys.exit(1)

    try:
        data = response.json()
        issue_number = data["number"]
        issue_url = data["html_url"]
        print(f"✅ Created issue #{issue_number}: {issue_url}")
        return issue_number
    except (json.JSONDecodeError, KeyError) as e:
        print(f"❌ Error parsing response: {e}")
        print(f"Response: {response.text[:500]}")
        sys.exit(1)


def format_issue_body(
    errors_data: dict,
    identifier: str,
    parent_issue_url: str | None,
) -> str:
    """
    使用错误详细信息格式化 GitHub 问题正文。

    Args:
        errors_data: 解析出的错误数据
        identifier: 唯一标识符
        parent_issue_url: 可选的父问题 URL

    Returns:
        格式化的问题正文
    """
    examples = errors_data.get("examples", [])
    query = errors_data.get("query", "")

    body_parts = []

    # 添加父问题参考（如果提供）
    if parent_issue_url:
        body_parts.append(f"**Parent Issue:** {parent_issue_url}\n")

    # 添加标识符以提高可搜索性
    body_parts.append(f"**Identifier:** `{identifier}`\n")

    # 添加查询信息
    body_parts.append(f"**Query:** `{query}`\n")

    # 添加错误摘要
    if examples:
        first_example = examples[0]
        body_parts.append("## Error Summary\n")

        if first_example.get("issue_id"):
            body_parts.append(f"- **Issue ID:** `{first_example['issue_id']}`")
        if first_example.get("total_count"):
            body_parts.append(
                f"- **Total Occurrences:** {first_example['total_count']}"
            )
        if first_example.get("error_type"):
            body_parts.append(f"- **Error Type:** `{first_example['error_type']}`")
        if first_example.get("service"):
            body_parts.append(f"- **Service:** `{first_example['service']}`")
        if first_example.get("file_path"):
            body_parts.append(f"- **File:** `{first_example['file_path']}`")
        if first_example.get("function_name"):
            body_parts.append(f"- **Function:** `{first_example['function_name']}`")
        if first_example.get("state"):
            body_parts.append(f"- **State:** {first_example['state']}")

        body_parts.append("")

        # 如果可用，则添加错误消息
        if first_example.get("error_message"):
            body_parts.append("## Error Message\n")
            body_parts.append("```")
            body_parts.append(first_example["error_message"])
            body_parts.append("```\n")

    # 添加有关完整数据的注释
    body_parts.append("## Full Error Data\n")
    body_parts.append(
        "The complete error tracking data has been saved and will be analyzed "
        "by the debugging agent.\n"
    )

    # 添加 JSON 数据作为可折叠部分
    body_parts.append("<details>")
    body_parts.append("<summary>View Full Error Data (JSON)</summary>\n")
    body_parts.append("```json")
    body_parts.append(json.dumps(errors_data, indent=2))
    body_parts.append("```")
    body_parts.append("</details>\n")

    body_parts.append("---")
    body_parts.append(
        "*This issue is being tracked by an automated debugging agent. "
        "Analysis findings will be posted as comments below.*"
    )

    return "\n".join(body_parts)


def setup_github_issue(
    query: str,
    errors_file: Path,
    issue_repo: str,
    issue_prefix: str,
    issue_parent: str | None,
) -> tuple[int, str]:
    """
    创建或查找 GitHub 问题以跟踪调试进度。

    Args:
        query: 数据狗查询
        errors_file: 错误 JSON 文件的路径
        issue_repo: GitHub 问题存储库
        issue_prefix: 问题标题的前缀
        issue_parent: 可选的父问题 URL

    Returns:
        (issue_number, issue_url) 的元组
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("❌ GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    # 加载错误数据
    with open(errors_file) as f:
        errors_data = json.load(f)

    # 创建唯一标识符
    identifier = create_unique_identifier(query, errors_data)

    # 搜索现有问题
    issue_number = search_existing_issue(issue_repo, identifier, github_token)

    if issue_number:
        # 返回现有问题
        issue_url = f"https://github.com/{issue_repo}/issues/{issue_number}"
        return issue_number, issue_url

    # 创建新问题根据错误数据确定标题
    #
    examples = errors_data.get("examples", [])
    if examples and examples[0].get("error_type"):
        error_name = examples[0]["error_type"]
    else:
        # 使用查询作为回退方案
        error_name = query[:50]  # 极限长度

    title = f"{issue_prefix}{error_name}"

    # 格式化问题正文
    body = format_issue_body(errors_data, identifier, issue_parent)

    # 创建问题
    issue_number = create_github_issue(issue_repo, title, body, github_token)
    issue_url = f"https://github.com/{issue_repo}/issues/{issue_number}"

    return issue_number, issue_url


def create_debugging_prompt(
    query: str, repos: list[str], errors_file: Path, issue_url: str
) -> str:
    """为智能体创建调试提示词。"""
    repos_list = "\n".join(f"- {repo}" for repo in repos)
    dd_site = os.getenv("DD_SITE", "datadoghq.com")
    error_tracking_url = f"https://api.{dd_site}/api/v2/error-tracking/issues/search"
    logs_url = f"https://api.{dd_site}/api/v2/logs/events/search"

    # 加载 Jinja2 模板
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("debug_prompt.jinja")

    # 使用上下文渲染模板
    prompt = template.render(
        issue_url=issue_url,
        errors_file=errors_file,
        query=query,
        error_tracking_url=error_tracking_url,
        logs_url=logs_url,
        repos_list=repos_list,
    )

    return prompt


def main():
    """运行Datadog调试示例的主要函数。"""
    parser = argparse.ArgumentParser(
        description="Debug errors from Datadog logs using OpenHands agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query-type",
        choices=["log-query", "log-error-id"],
        default="log-query",
        help=(
            "Type of query: 'log-query' for search queries "
            "(e.g., 'service:deploy ClientDisconnect'), "
            "'log-error-id' for specific error tracking ID "
            "(e.g., '2adba034-ab5a-11f0-b04e-da7ad0900000')"
        ),
    )
    parser.add_argument(
        "--query",
        required=True,
        help=(
            "Datadog query string. For 'log-query': search query like "
            "'status:error service:deploy'. For 'log-error-id': "
            "specific error tracking ID"
        ),
    )
    parser.add_argument(
        "--repos",
        required=True,
        help="Comma-separated list of GitHub repositories to analyze "
        "(e.g., 'All-Hands-AI/OpenHands,All-Hands-AI/deploy')",
    )
    parser.add_argument(
        "--working-dir",
        default="./datadog_debug_workspace",
        help="Working directory for cloning repos and analysis "
        "(default: ./datadog_debug_workspace)",
    )
    parser.add_argument(
        "--issue-repo",
        required=True,
        help="GitHub repository for creating/updating issues "
        "(e.g., 'All-Hands-AI/infra')",
    )
    parser.add_argument(
        "--issue-parent",
        help="Parent issue URL to reference (e.g., "
        "'https://github.com/All-Hands-AI/infra/issues/672')",
    )
    parser.add_argument(
        "--issue-prefix",
        default="",
        help="Prefix to add to issue titles (e.g., 'DataDog Error Bash: ')",
    )

    args = parser.parse_args()

    # Validate environment
    if not validate_environment():
        sys.exit(1)

    # 解析存储库
    repos = [repo.strip() for repo in args.repos.split(",")]

    # 创建工作目录
    working_dir = Path(args.working_dir).resolve()
    working_dir.mkdir(exist_ok=True)

    print("🔍 Starting Datadog debugging session")
    print(f"📊 Query: {args.query}")
    print(f"📁 Repositories: {', '.join(repos)}")
    print(f"🌍 Datadog site: {os.getenv('DD_SITE', 'datadoghq.com')}")
    print(f"💼 Working directory: {working_dir}")
    print()

    # 从 Datadog 获取错误示例
    errors_file = fetch_datadog_errors(args.query, working_dir, args.query_type)
    print()

    # 设置 GitHub 跟踪问题
    print("📋 Setting up GitHub issue for tracking...")
    issue_number, issue_url = setup_github_issue(
        args.query,
        errors_file,
        args.issue_repo,
        args.issue_prefix,
        args.issue_parent,
    )
    print(f"📌 Tracking issue: {issue_url}")
    print()

    # 配置LLM
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        print("❌ LLM_API_KEY environment variable is required")
        sys.exit(1)

    # 从环境中获取 LLM 配置
    model = os.getenv("LLM_MODEL", "gpt-5.5")
    base_url = os.getenv("LLM_BASE_URL")

    llm = LLM(
        model=model,
        base_url=base_url,
        api_key=SecretStr(api_key),
    )

    # 运行调试会话
    run_debugging_session(llm, working_dir, args.query, repos, errors_file, issue_url)


def run_debugging_session(
    llm: LLM,
    working_dir: Path,
    query: str,
    repos: list[str],
    errors_file: Path,
    issue_url: str,
):
    """使用给定的配置运行调试会话。"""
    # 注册并设置工具
    register_tool("TerminalTool", TerminalTool)
    register_tool("FileEditorTool", FileEditorTool)
    register_tool("TaskTrackerTool", TaskTrackerTool)

    tools = [
        Tool(name="TerminalTool"),
        Tool(name="FileEditorTool"),
        Tool(name="TaskTrackerTool"),
    ]

    # 创建智能体
    agent = Agent(llm=llm, tools=tools)

    # 收集 LLM 条消息以进行调试
    llm_messages = []

    def conversation_callback(event: Event):
        if isinstance(event, LLMConvertibleEvent):
            llm_messages.append(event.to_llm_message())

    # 与当地人开始对话工作区
    conversation = Conversation(
        agent=agent, workspace=str(working_dir), callbacks=[conversation_callback]
    )

    # 发送调试任务
    debugging_prompt = create_debugging_prompt(query, repos, errors_file, issue_url)

    conversation.send_message(
        message=Message(
            role="user",
            content=[TextContent(text=debugging_prompt)],
        )
    )

    print("🤖 Starting debugging analysis...")
    try:
        conversation.run()

        print("\n" + "=" * 80)
        print("🎯 Debugging session completed!")
        print(f"📁 Results saved in: {working_dir}")
        print(f"💬 Total LLM messages: {len(llm_messages)}")

        # 显示已完成事项的摘要
        print("\n📋 Session Summary:")
        print("- Queried Datadog logs for error analysis")
        print("- Cloned and analyzed relevant repositories")
        print("- Investigated potential root causes")
        print("- Attempted error reproduction")

        # 检查克隆存储库
        if working_dir.exists():
            cloned_repos = [
                d for d in working_dir.iterdir() if d.is_dir() and (d / ".git").exists()
            ]
            if cloned_repos:
                print(
                    f"- Cloned repositories: {', '.join(d.name for d in cloned_repos)}"
                )
    finally:
        # 清理对话
        logger.info("Closing conversation...")
        conversation.close()


if __name__ == "__main__":
    main()
