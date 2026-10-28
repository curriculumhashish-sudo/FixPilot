#!/usr/bin/env python3
"""
PostHog 调试示例

此示例演示如何使用 OpenHands 智能体调试 PostHog 中记录的错误。 智能体将：
1. 使用查询 API 查询 PostHog 事件以了解错误
2. 使用 git 命令克隆相关 GitHub 存储库
3. 分析代码库以确定潜在原因
4. 尝试重现错误
5. （可选）创建包含修复的草稿 PR

用途：
    python posthog_debugging.py --query "$exception" \\
        --repos "All-Hands-AI/OpenHands,All-Hands-AI/deploy"

环境变量必填：
    - POSTHOG_API_KEY: 您的 PostHog 个人 API 密钥
    - POSTHOG_PROJECT_ID: 您的 PostHog 项目 ID
    - POSTHOG_HOST: （可选）PostHog 主机（e.g.、us.posthog.com、eu.posthog.com）
    - GITHUB_TOKEN: 您的 GitHub 个人访问令牌
    - LLM_API_KEY: LLM 服务的 API 键
"""

import argparse
import json
import os
import sys
from datetime import datetime
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

DEFAULT_POSTHOG_HOST = "us.posthog.com"


def get_posthog_host() -> str:
    """从环境中获取 PostHog 主机，如果未设置或为空，则使用默认值。"""
    host = os.getenv("POSTHOG_HOST", "")
    return host if host else DEFAULT_POSTHOG_HOST


def _extract_issue_title(examples: list[dict], query: str) -> str:
    """
    从事件示例中提取有意义的问题标题。

    对于 $exception 事件，尝试提取异常类型和消息。 如果无法提取有意义的信息，则返回到
    查询。

    Args:
        examples: 事件示例列表
        query: 原始查询字符串

    Returns:
        描述性标题字符串（最多 100 个字符）
    """
    if not examples:
        return query[:50]

    first_event = examples[0]
    properties = first_event.get("properties", {})

    # 处理字符串属性（需要解析JSON）
    if isinstance(properties, str):
        try:
            properties = json.loads(properties)
        except json.JSONDecodeError:
            properties = {}

    # 尝试从 $exception 事件中提取异常信息
    exception_types = properties.get("$exception_types", [])
    exception_values = properties.get("$exception_values", [])

    if exception_types and exception_values:
        # 组合描述性标题的类型和值
        exc_type = exception_types[0] if exception_types else "Error"
        exc_value = exception_values[0] if exception_values else ""

        if exc_value:
            # 截断长消息
            if len(exc_value) > 60:
                exc_value = exc_value[:57] + "..."
            return f"{exc_type}: {exc_value}"
        return exc_type

    # 尝试 $exception_list 格式
    exception_list = properties.get("$exception_list", [])
    if exception_list:
        first_exc = exception_list[0]
        exc_type = first_exc.get("type", "Error")
        exc_value = first_exc.get("value", "")

        if exc_value:
            if len(exc_value) > 60:
                exc_value = exc_value[:57] + "..."
            return f"{exc_type}: {exc_value}"
        return exc_type

    # 回退到事件名称或查询
    event_name = first_event.get("event", query)
    return event_name[:50] if event_name else query[:50]


def _fetch_event_timeline(
    event_name: str,
    posthog_host: str,
    posthog_project_id: str,
    posthog_api_key: str,
    days_back: int = 30,
) -> dict:
    """
    获取有关事件首次发生时间和每日计数的时间线信息。

    这有助于识别错误何时开始发生，这对于与代码更改和部署相关联至关重要。

    Args:
        event_name: 要查询的事件名称 (e.g., '$exception')
        posthog_host: PostHog API 主持人
        posthog_project_id: PostHog 项目编号
        posthog_api_key: PostHogAPI键
        days_back: 回溯多少天来查找第一次出现的情况

    Returns:
        带有时间线信息的词典
    """
    api_url = f"https://{posthog_host}/api/projects/{posthog_project_id}/query/"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {posthog_api_key}",
    }

    timeline_info: dict = {
        "first_seen": None,
        "last_seen": None,
        "total_count": 0,
        "daily_counts": [],
        "days_analyzed": days_back,
    }

    # 查询 1：获取第一次和最后一次出现的时间戳以及总计数
    summary_query = (
        f"SELECT min(timestamp) as first_seen, max(timestamp) as last_seen, "
        f"count() as total_count FROM events "
        f"WHERE event = '{event_name}' "
        f"AND timestamp > now() - INTERVAL {days_back} DAY"
    )

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={"query": {"kind": "HogQLQuery", "query": summary_query}},
            timeout=60,
        )
        if response.ok:
            data = response.json()
            results = data.get("results", [])
            if results and results[0]:
                timeline_info["first_seen"] = results[0][0]
                timeline_info["last_seen"] = results[0][1]
                timeline_info["total_count"] = results[0][2]
    except Exception as e:
        print(f"⚠️  Warning: Could not fetch event timeline summary: {e}")

    # 查询 2：获取该时段内的每日计数
    daily_query = (
        f"SELECT toDate(timestamp) as day, count() as count FROM events "
        f"WHERE event = '{event_name}' "
        f"AND timestamp > now() - INTERVAL {days_back} DAY "
        f"GROUP BY day ORDER BY day"
    )

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={"query": {"kind": "HogQLQuery", "query": daily_query}},
            timeout=60,
        )
        if response.ok:
            data = response.json()
            results = data.get("results", [])
            timeline_info["daily_counts"] = [
                {"date": str(row[0]), "count": row[1]} for row in results
            ]
    except Exception as e:
        print(f"⚠️  Warning: Could not fetch daily event counts: {e}")

    return timeline_info


def validate_environment():
    """验证所有必需的环境变量均已设置。"""
    required_vars = [
        "POSTHOG_API_KEY",
        "POSTHOG_PROJECT_ID",
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


def fetch_posthog_events(
    query: str, working_dir: Path, query_type: str = "event-query", limit: int = 5
) -> Path:
    """
    从 PostHog 获取事件示例并保存到 JSON 文件。

    Args:
        query: PostHog 查询字符串（事件名称或事件 ID）
        working_dir: 保存事件示例的目录
        query_type: 查询类型 - “事件查询”（使用查询 API 和 HogQL）或
            “event-id”（获取特定事件）
        limit: 要获取的事件示例的最大数量（默认值：5）

    Returns:
        包含事件示例的 JSON 文件的路径
    """
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_project_id = os.getenv("POSTHOG_PROJECT_ID")
    posthog_host = get_posthog_host()

    event_examples = []

    if query_type == "event-id":
        # 使用 HogQL 查询按 ID 获取特定事件
        api_url = f"https://{posthog_host}/api/projects/{posthog_project_id}/query/"

        # 使用 HogQL 通过 UUID 获取事件
        hogql_query = f"SELECT * FROM events WHERE uuid = '{query}' LIMIT 1"

        request_body = {
            "query": {"kind": "HogQLQuery", "query": hogql_query},
            "refresh": "blocking",
        }

        print("📡 Fetching specific event from PostHog...")
        print(f"   Event ID: {query}")
        print(f"   API: {api_url}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {posthog_api_key}",
        }

        try:
            response = requests.post(
                api_url, headers=headers, json=request_body, timeout=120
            )
        except requests.exceptions.Timeout:
            print("❌ Error: Request to PostHog API timed out (120s)")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error connecting to PostHog API: {e}")
            sys.exit(1)

        if not response.ok:
            print(f"❌ Error fetching from PostHog API: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   Error details: {json.dumps(error_detail, indent=2)}")
            except Exception:
                print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing PostHog API response: {e}")
            print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        # 解析 HogQL 响应
        results = response_data.get("results", [])
        columns = response_data.get("columns", [])

        if not results:
            print(f"⚠️ No event found with ID: {query}")
            sys.exit(1)

        # 使用列名将行转换为字典
        row = results[0]
        event_data = dict(zip(columns, row))

        # 提取事件详细信息
        event_example = {
            "example_number": 1,
            "event_id": event_data.get("uuid"),
            "event": event_data.get("event"),
            "distinct_id": event_data.get("distinct_id"),
            "properties": event_data.get("properties", {}),
            "timestamp": event_data.get("timestamp"),
            "person": event_data.get("person"),
        }
        event_examples.append(event_example)

    else:  # 事件查询
        # 使用查询 API 和 HogQL 来获取事件
        api_url = f"https://{posthog_host}/api/projects/{posthog_project_id}/query/"

        # 构建 HogQL 查询来获取事件查询最近 1 天内的事件以避免服务器端超时
        #
        hogql_query = (
            f"SELECT * FROM events WHERE event = '{query}' "
            f"AND timestamp > now() - INTERVAL 1 DAY "
            f"ORDER BY timestamp DESC LIMIT {limit}"
        )

        request_body = {
            "query": {"kind": "HogQLQuery", "query": hogql_query},
            "refresh": "blocking",
        }

        print(f"📡 Fetching up to {limit} events from PostHog...")
        print(f"   Event name: {query}")
        print(f"   API: {api_url}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {posthog_api_key}",
        }

        try:
            response = requests.post(
                api_url, headers=headers, json=request_body, timeout=120
            )
        except requests.exceptions.Timeout:
            print("❌ Error: Request to PostHog API timed out (120s)")
            print("   Try reducing the number of events or using a more specific query")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error connecting to PostHog API: {e}")
            sys.exit(1)

        if not response.ok:
            print(f"❌ Error fetching from PostHog API: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"   Error details: {json.dumps(error_detail, indent=2)}")
            except Exception:
                print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing PostHog API response: {e}")
            print(f"   Response: {response.text[:500]}")
            sys.exit(1)

        # 检查 API 个错误（成功时 PostHog 返回“error”：null）
        if response_data.get("error"):
            print(f"❌ PostHog API error: {response_data['error']}")
            sys.exit(1)

        # 从 HogQL 查询响应中提取事件结果
        results = response_data.get("results", [])

        if results:
            # 结果是柱状格式，需要解析它们
            columns = response_data.get("columns", [])
            rows = response_data.get("results", [])

            for idx, row in enumerate(rows[:limit], 1):
                # 创建将列名映射到值的字典
                event_dict = {}
                if columns:
                    for col_idx, col_name in enumerate(columns):
                        if col_idx < len(row):
                            event_dict[col_name] = row[col_idx]
                else:
                    # 回退方案如果未提供列
                    event_dict = {"data": row}

                event_example = {
                    "example_number": idx,
                    "event_id": event_dict.get("uuid") or event_dict.get("id"),
                    "event": event_dict.get("event"),
                    "distinct_id": event_dict.get("distinct_id"),
                    "properties": event_dict.get("properties", {}),
                    "timestamp": event_dict.get("timestamp"),
                    "person_id": event_dict.get("person_id"),
                }
                event_examples.append(event_example)

    # 获取时间线信息（第一次发生错误时，每日计数）
    timeline_info: dict = {}
    if query_type == "event-query":
        print("📊 Fetching event timeline (first occurrence, daily counts)...")
        # 在调用该函数之前，这些由 validate_environment() 验证
        assert posthog_project_id is not None
        assert posthog_api_key is not None
        timeline_info = _fetch_event_timeline(
            query, posthog_host, posthog_project_id, posthog_api_key, days_back=30
        )
        if timeline_info.get("first_seen"):
            print(f"   First seen: {timeline_info['first_seen']}")
            print(f"   Last seen: {timeline_info['last_seen']}")
            print(f"   Total count (30 days): {timeline_info['total_count']}")

    # 保存到文件
    events_file = working_dir / "posthog_events.json"
    events_data = {
        "query": query,
        "fetch_time": datetime.now().isoformat(),
        "total_examples": len(event_examples),
        "examples": event_examples,
    }

    # 添加时间线信息（如果有）
    if timeline_info:
        events_data["timeline"] = timeline_info

    with open(events_file, "w") as f:
        json.dump(events_data, f, indent=2)

    print(f"✅ Fetched {len(event_examples)} event examples")
    print(f"📄 Saved to: {events_file}")
    return events_file


def create_unique_identifier(query: str, events_data: dict) -> str:
    """
    根据查询或事件 ID 为事件创建唯一标识符。

    Args:
        query: PostHog 查询字符串
        events_data: 来自 posthog_events.json 的已解析事件数据

    Returns:
        唯一标识符字符串
    """
    # 检查我们是否有特定的事件 ID
    examples = events_data.get("examples", [])
    if examples and examples[0].get("event_id"):
        event_id = examples[0]["event_id"]
        return f"event-id: {event_id}"
    else:
        # 使用查询作为标识符
        return f"query: {query}"


def search_existing_issue(
    issue_repo: str, identifier: str, github_token: str
) -> int | None:
    """
    搜索包含标识符的现有开放 GitHub 问题。

    仅返回未解决的问题。 如果所有匹配的问题都已关闭，则返回 None，以便可以创建新问题
    。

    Args:
        issue_repo: 存储库格式为“所有者/存储库”
        identifier: 要搜索的唯一标识符
        github_token: GitHub API token

    Returns:
        如果找到则发行号（开放），否则为 None
    """
    print(f"🔍 Searching for existing open issue with identifier: {identifier}")

    # 在存储库中搜索未解决的问题
    search_query = f'repo:{issue_repo} is:issue is:open "{identifier}"'
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
            print(
                f"✅ Found existing open issue #{issue_number} (oldest of {len(items)})"
            )
            return issue_number
        else:
            print("📭 No open issue found - will create new one")
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


def update_github_issue(
    issue_repo: str,
    issue_number: int,
    body: str,
    github_token: str,
) -> None:
    """
    更新现有的 GitHub 问题正文。

    Args:
        issue_repo: 存储库格式为“所有者/存储库”
        issue_number: 要更新的问题编号
        body: 新期正文内容
        github_token: GitHub API token
    """
    print(f"📝 Updating issue #{issue_number} with latest event data...")

    url = f"https://api.github.com/repos/{issue_repo}/issues/{issue_number}"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }
    payload = {"body": body}

    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        print(f"✅ Updated issue #{issue_number}")
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Warning: Could not update issue: {e}")
        # 不要退出 - 这并不重要


def _extract_exception_info(properties: dict | str) -> dict | None:
    """
    从事件属性中提取异常信息。

    Args:
        properties: 事件属性（字典或JSON字符串）

    Returns:
        包含 exception_type、exception_message、stack_frames 或 None 的字典
    """
    # 如果是字符串则解析属性
    if isinstance(properties, str):
        try:
            properties = json.loads(properties)
        except json.JSONDecodeError:
            return None

    if not isinstance(properties, dict):
        return None

    # 尝试从$exception_list（PostHog格式）中提取
    exception_list = properties.get("$exception_list", [])
    if exception_list and isinstance(exception_list, list):
        exc = exception_list[0]
        result = {
            "exception_type": exc.get("type", "Unknown"),
            "exception_message": exc.get("value", "No message"),
            "stack_frames": [],
        }

        # 提取堆栈帧
        stacktrace = exc.get("stacktrace", {})
        frames = stacktrace.get("frames", [])
        for frame in frames:
            frame_info = {
                "function": frame.get("mangled_name", frame.get("function", "?")),
                "file": frame.get("source", frame.get("filename", "?")),
                "line": frame.get("line", "?"),
                "column": frame.get("column", "?"),
            }
            result["stack_frames"].append(frame_info)

        return result

    # 回退方案：尝试$exception_types和$exception_values
    exc_types = properties.get("$exception_types", [])
    exc_values = properties.get("$exception_values", [])
    if exc_types or exc_values:
        return {
            "exception_type": exc_types[0] if exc_types else "Unknown",
            "exception_message": exc_values[0] if exc_values else "No message",
            "stack_frames": [],
        }

    return None


def _format_stack_trace(stack_frames: list[dict]) -> str:
    """将堆栈帧格式化为可读的堆栈跟踪。"""
    if not stack_frames:
        return "*No stack trace available*"

    lines = []
    for frame in stack_frames:
        func = frame.get("function", "?")
        file = frame.get("file", "?")
        line = frame.get("line", "?")
        col = frame.get("column", "")

        # 清理显示的文件路径
        if file.startswith("/"):
            file = file.lstrip("/")

        location = f"{file}:{line}"
        if col:
            location += f":{col}"

        lines.append(f"  at {func} ({location})")

    return "\n".join(lines)


def format_issue_body(
    events_data: dict,
    identifier: str,
    parent_issue_url: str | None,
) -> str:
    """
    使用事件详细信息格式化 GitHub 问题正文。

    Args:
        events_data: 解析的事件数据
        identifier: 唯一标识符
        parent_issue_url: 可选的父问题 URL

    Returns:
        格式化的问题正文
    """
    examples = events_data.get("examples", [])
    query = events_data.get("query", "")
    timeline = events_data.get("timeline", {})

    body_parts = []

    # 添加父问题参考（如果提供）
    if parent_issue_url:
        body_parts.append(f"**Parent Issue:** {parent_issue_url}\n")

    # 从第一个示例中提取异常信息
    exception_info = None
    if examples:
        first_example = examples[0]
        properties = first_example.get("properties", {})
        exception_info = _extract_exception_info(properties)

    # === QUICK SUMMARY SECTION ===
    body_parts.append("## 📋 Quick Summary\n")

    if exception_info:
        exc_type = exception_info.get("exception_type", "Unknown")
        exc_msg = exception_info.get("exception_message", "No message")
        body_parts.append(f"**Error:** `{exc_type}: {exc_msg}`\n")

    if timeline:
        first_seen = timeline.get("first_seen", "")
        if first_seen:
            # 很好地格式化日期
            date_part = first_seen.split("T")[0] if "T" in first_seen else first_seen
            body_parts.append(f"**First Occurred:** {date_part}")

        total = timeline.get("total_count", 0)
        days = timeline.get("days_analyzed", 30)
        if total:
            avg_per_day = total // days if days else total
            body_parts.append(f"**Total Occurrences:** {total:,} (~{avg_per_day}/day)")

    body_parts.append("")

    # === STACK TRACE SECTION ===
    if exception_info and exception_info.get("stack_frames"):
        body_parts.append("## 🔍 Stack Trace\n")
        body_parts.append("```")
        body_parts.append(_format_stack_trace(exception_info["stack_frames"]))
        body_parts.append("```\n")

    # === TIMELINE SECTION ===
    if timeline:
        body_parts.append("## ⏰ Error Timeline\n")

        if timeline.get("first_seen"):
            body_parts.append(f"- **First Seen:** {timeline['first_seen']}")
        if timeline.get("last_seen"):
            body_parts.append(f"- **Last Seen:** {timeline['last_seen']}")

        body_parts.append("")

        # 将每日计数添加为表格
        daily_counts = timeline.get("daily_counts", [])
        if daily_counts:
            body_parts.append("<details>")
            body_parts.append(
                "<summary>📊 Daily Error Counts (click to expand)</summary>\n"
            )
            body_parts.append("| Date | Count |")
            body_parts.append("|------|-------|")
            for day_data in daily_counts[-14:]:  # 过去 14 天
                body_parts.append(f"| {day_data['date']} | {day_data['count']} |")
            if len(daily_counts) > 14:
                body_parts.append(
                    f"\n*Showing last 14 days of {len(daily_counts)} days with data*"
                )
            body_parts.append("</details>\n")

    # === EVENT DETAILS SECTION ===
    if examples:
        first_example = examples[0]
        body_parts.append("## 📝 Event Details\n")

        if first_example.get("distinct_id"):
            body_parts.append(f"- **User:** `{first_example['distinct_id']}`")
        if first_example.get("timestamp"):
            body_parts.append(f"- **Timestamp:** {first_example['timestamp']}")
        if first_example.get("event_id"):
            body_parts.append(f"- **Event ID:** `{first_example['event_id']}`")

        body_parts.append("")

    # === METADATA SECTION（可折叠）===
    body_parts.append("<details>")
    body_parts.append("<summary>🔧 Technical Details</summary>\n")
    body_parts.append(f"**Identifier:** `{identifier}`\n")
    body_parts.append(f"**Query:** `{query}`\n")

    # 添加完整的 JSON 数据
    body_parts.append("**Full Event Data:**")
    body_parts.append("```json")
    body_parts.append(json.dumps(events_data, indent=2))
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
    events_file: Path,
    issue_repo: str,
    issue_prefix: str,
    issue_parent: str | None,
) -> tuple[int, str]:
    """
    创建或查找 GitHub 问题以跟踪调试进度。

    Args:
        query: PostHog 查询
        events_file: 事件 JSON 文件的路径
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

    # 加载事件数据
    with open(events_file) as f:
        events_data = json.load(f)

    # 创建唯一标识符
    identifier = create_unique_identifier(query, events_data)

    # 格式化问题正文（新问题和现有问题都需要）
    body = format_issue_body(events_data, identifier, issue_parent)

    # 搜索现有问题
    issue_number = search_existing_issue(issue_repo, identifier, github_token)

    if issue_number:
        # 使用最新数据更新现有问题（包括时间线信息）
        update_github_issue(issue_repo, issue_number, body, github_token)
        issue_url = f"https://github.com/{issue_repo}/issues/{issue_number}"
        return issue_number, issue_url

    # 创建新问题根据事件数据确定标题 - 尝试提取有意义的错误信息
    #
    examples = events_data.get("examples", [])
    title_suffix = _extract_issue_title(examples, query)
    title = f"{issue_prefix}{title_suffix}"

    # 创建问题
    issue_number = create_github_issue(issue_repo, title, body, github_token)
    issue_url = f"https://github.com/{issue_repo}/issues/{issue_number}"

    return issue_number, issue_url


def create_debugging_prompt(
    query: str, repos: list[str], events_file: Path, issue_url: str
) -> str:
    """为智能体创建调试提示词。"""
    repos_list = "\n".join(f"- {repo}" for repo in repos)
    posthog_host = get_posthog_host()
    posthog_project_id = os.getenv("POSTHOG_PROJECT_ID")
    query_url = f"https://{posthog_host}/api/projects/{posthog_project_id}/query/"
    events_url = f"https://{posthog_host}/api/projects/{posthog_project_id}/events/"

    # 加载 Jinja2 模板
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("debug_prompt.jinja")

    # 使用上下文渲染模板
    prompt = template.render(
        issue_url=issue_url,
        events_file=events_file,
        query=query,
        query_url=query_url,
        events_url=events_url,
        repos_list=repos_list,
    )

    return prompt


def main():
    """主要功能是运行PostHog调试示例。"""
    parser = argparse.ArgumentParser(
        description="Debug errors from PostHog events using OpenHands agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query-type",
        choices=["event-query", "event-id"],
        default="event-query",
        help=(
            "Type of query: 'event-query' for event name queries "
            "(e.g., '$exception'), "
            "'event-id' for specific event ID"
        ),
    )
    parser.add_argument(
        "--query",
        required=True,
        help=(
            "PostHog query string. For 'event-query': event name like "
            "'$exception' or 'error'. For 'event-id': "
            "specific event ID"
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
        default="./posthog_debug_workspace",
        help="Working directory for cloning repos and analysis "
        "(default: ./posthog_debug_workspace)",
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
        help="Prefix to add to issue titles (e.g., 'PostHog Error: ')",
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

    print("🔍 Starting PostHog debugging session")
    print(f"📊 Query: {args.query}")
    print(f"📁 Repositories: {', '.join(repos)}")
    print(f"🌍 PostHog host: {get_posthog_host()}")
    print(f"💼 Working directory: {working_dir}")
    print()

    # 从 PostHog 获取事件示例
    events_file = fetch_posthog_events(args.query, working_dir, args.query_type)
    print()

    # 设置 GitHub 跟踪问题
    print("📋 Setting up GitHub issue for tracking...")
    issue_number, issue_url = setup_github_issue(
        args.query,
        events_file,
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
    run_debugging_session(llm, working_dir, args.query, repos, events_file, issue_url)


def run_debugging_session(
    llm: LLM,
    working_dir: Path,
    query: str,
    repos: list[str],
    events_file: Path,
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
    debugging_prompt = create_debugging_prompt(query, repos, events_file, issue_url)

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
        print("- Queried PostHog events for error analysis")
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
