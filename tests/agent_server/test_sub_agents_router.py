"""测试子智能体路由器 (POST /sub-agents)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证
    return TestClient(create_app(config), raise_server_exceptions=False)


def _write_agent(directory: Path, name: str, description: str = "desc") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nPrompt for {name}."
    )


def test_get_sub_agents_returns_builtins_only(client):
    """列出并标记内置插件； 可以排除用户/项目源。"""
    response = client.post(
        "/api/sub-agents",
        json={"load_builtin": True, "load_user": False, "load_project": False},
    )
    assert response.status_code == 200
    agents = response.json()["agents"]
    names = {a["name"] for a in agents}

    assert {"general-purpose", "code-explorer", "bash-runner"} <= names
    assert all(a["level"] == "builtin" and a["is_builtin"] for a in agents)
    # system_prompt 内联骑行，因此无需额外获取详细信息视图
    assert all(a["system_prompt"] for a in agents)


def test_get_sub_agents_includes_project_and_shadows_builtin(client, tmp_path: Path):
    """将出现一个项目智能体，并隐藏同名的内置项目。"""
    _write_agent(tmp_path / ".agents" / "agents", "code-reviewer", "Reviews code")
    # 与内置 -> 项目定义相同的名称必须获胜。
    _write_agent(tmp_path / ".agents" / "agents", "general-purpose", "Overridden")

    response = client.post(
        "/api/sub-agents",
        json={
            "load_builtin": True,
            "load_user": False,
            "load_project": True,
            "project_dir": str(tmp_path),
        },
    )
    assert response.status_code == 200
    agents = {a["name"]: a for a in response.json()["agents"]}

    assert agents["code-reviewer"]["level"] == "project"
    assert agents["code-reviewer"]["is_builtin"] is False

    # 只有一个通用条目，它是项目（影子）条目。
    gp = agents["general-purpose"]
    assert gp["level"] == "project"
    assert gp["is_builtin"] is False
    assert gp["description"] == "Overridden"


def test_get_sub_agents_load_builtin_false(client):
    """禁用没有其他源的内置程序会产生一个空目录。"""
    response = client.post(
        "/api/sub-agents",
        json={"load_builtin": False, "load_user": False, "load_project": False},
    )
    assert response.status_code == 200
    assert response.json()["agents"] == []


def test_get_sub_agents_exposes_full_frontmatter(client, tmp_path: Path):
    """返回每个前置元数据-可设置字段（无损视图）。"""
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "full.md").write_text(
        "---\n"
        "name: full\n"
        "description: Fully specified agent\n"
        "model: inherit\n"
        "color: purple\n"
        "tools:\n  - TerminalTool\n"
        "skills:\n  - some-skill\n"
        "permission_mode: confirm_risky\n"
        "max_iteration_per_run: 7\n"
        "max_budget_per_run: 1.5\n"
        "profile_store_dir: /tmp/profiles\n"
        "mcp_config:\n"
        "  fetch:\n    command: uvx\n    args:\n"
        "      - --with\n      - mcp==1.29.0\n"
        "      - mcp-server-fetch==2026.7.10\n"
        "condenser: none\n"
        "custom_key: custom_value\n"
        "---\n\n"
        "You are a fully specified agent."
    )

    response = client.post(
        "/api/sub-agents",
        json={"load_builtin": False, "load_user": False, "project_dir": str(tmp_path)},
    )
    assert response.status_code == 200
    agent = {a["name"]: a for a in response.json()["agents"]}["full"]

    assert agent["skills"] == ["some-skill"]
    assert agent["permission_mode"] == "confirm_risky"
    assert agent["max_iteration_per_run"] == 7
    assert agent["max_budget_per_run"] == 1.5
    assert agent["profile_store_dir"] == "/tmp/profiles"
    # ``enabled`` 默认为 True，MCPServer 的紧凑序列化器只会丢弃空值，因此标志总是报告，
    # 即使前置元数据也忽略它。
    #
    assert agent["mcp_config"] == {
        "fetch": {
            "command": "uvx",
            "args": [
                "--with",
                "mcp==1.29.0",
                "mcp-server-fetch==2026.7.10",
            ],
            "enabled": True,
        }
    }
    # 上下文压缩器：None -> a NoOpCondenser 是已序列化 （不是 null）
    assert agent["condenser"] is not None
    # 未知的前置元数据键保留在元数据中
    assert agent["metadata"]["custom_key"] == "custom_value"


@pytest.mark.parametrize("enable_browser", [True, False])
def test_get_sub_agents_follows_the_browser_setting(enable_browser: bool):
    """仅当浏览器启用时才会列出仅限浏览器的网络研究人员。"""
    config = Config(session_api_keys=[], enable_browser=enable_browser)
    client = TestClient(create_app(config), raise_server_exceptions=False)

    response = client.post(
        "/api/sub-agents",
        json={"load_builtin": True, "load_user": False, "load_project": False},
    )
    assert response.status_code == 200
    names = {a["name"] for a in response.json()["agents"]}

    assert {"general-purpose", "code-explorer", "bash-runner"} <= names
    assert ("web-researcher" in names) is enable_browser
