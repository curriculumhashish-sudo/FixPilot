"""测试 git_router.py 端点。"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.git_provider_service import GitProviderAPIError
from openhands.agent_server.runtime_router import create_runtime_router
from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.git.models import (
    GitChange,
    GitChangeStatus,
    GitCommit,
    GitCommitsPage,
    GitDiff,
    GitProviderRepository,
    GitProviderRepositoryPage,
)


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证
    return TestClient(create_app(config), raise_server_exceptions=False)


def test_git_repositories_search_success(client):
    """GET /api/git/repositories/search 代理提供程序存储库结果。"""
    page = GitProviderRepositoryPage(
        items=[
            GitProviderRepository(
                id="123",
                full_name="OpenHands/software-agent-sdk",
                git_provider="github",
                is_public=True,
                stargazers_count=7,
                pushed_at="2026-09-29T12:00:00Z",
                main_branch="main",
            )
        ],
        next_page_id="2",
        missing_token=False,
    )

    with patch(
        "openhands.agent_server.git_router.search_provider_repositories",
        new_callable=AsyncMock,
    ) as search_provider_repositories:
        search_provider_repositories.return_value = page

        response = client.get(
            "/api/git/repositories/search",
            params={"provider": "github", "limit": 30, "page_id": "1"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "123",
                "full_name": "OpenHands/software-agent-sdk",
                "git_provider": "github",
                "is_public": True,
                "stargazers_count": 7,
                "pushed_at": "2026-09-29T12:00:00Z",
                "main_branch": "main",
            }
        ],
        "next_page_id": "2",
        "missing_token": False,
    }
    search_provider_repositories.assert_awaited_once()
    await_args = search_provider_repositories.await_args
    assert await_args is not None
    _, provider = await_args.args
    assert provider.value == "github"
    assert await_args.kwargs == {
        "query": None,
        "limit": 30,
        "page_id": "1",
    }


def test_git_repositories_search_reports_missing_token(client):
    """存储库发现可以报告缺少的提供程序 token。"""
    page = GitProviderRepositoryPage(items=[], next_page_id=None, missing_token=True)

    with patch(
        "openhands.agent_server.git_router.search_provider_repositories",
        new_callable=AsyncMock,
    ) as search_provider_repositories:
        search_provider_repositories.return_value = page

        response = client.get(
            "/api/git/repositories/search", params={"provider": "github"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_page_id": None,
        "missing_token": True,
    }


@pytest.mark.parametrize("status_code", [401, 403, 502, 504])
def test_git_repositories_search_preserves_provider_error_status(client, status_code):
    """提供者身份验证/重试失败应该保持可区分。"""
    with patch(
        "openhands.agent_server.git_router.search_provider_repositories",
        new_callable=AsyncMock,
    ) as search_provider_repositories:
        search_provider_repositories.side_effect = GitProviderAPIError(
            "GitHub repository search failed", status_code=status_code
        )

        response = client.get(
            "/api/git/repositories/search", params={"provider": "github"}
        )

    assert response.status_code == status_code
    if status_code < 500:
        assert response.json() == {"detail": "GitHub repository search failed"}


def test_runtime_git_router_excludes_repository_search():
    """存储库搜索使用全局机密存储，而不是会话机密。"""
    paths = {
        route.path
        for route in create_runtime_router().routes
        if isinstance(route, APIRoute)
    }

    assert (
        "/conversations/{runtime_conversation_id}/git/repositories/search" not in paths
    )
    assert "/conversations/{runtime_conversation_id}/git/changes" in paths


# =============================================================================
# 查询参数测试（首选方法）
# =============================================================================


@pytest.mark.asyncio
async def test_git_changes_query_param_success(client):
    """使用查询参数测试成功的 git 更改端点。"""
    expected_changes = [
        GitChange(status=GitChangeStatus.ADDED, path=Path("new_file.py")),
        GitChange(status=GitChangeStatus.UPDATED, path=Path("existing_file.py")),
        GitChange(status=GitChangeStatus.DELETED, path=Path("old_file.py")),
    ]

    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = expected_changes

        test_path = "src/test_repo"
        response = client.get("/api/git/changes", params={"path": test_path})

        assert response.status_code == 200
        response_data = response.json()

        assert len(response_data) == 3
        assert response_data[0]["status"] == "ADDED"
        assert response_data[0]["path"] == "new_file.py"
        assert response_data[1]["status"] == "UPDATED"
        assert response_data[1]["path"] == "existing_file.py"
        assert response_data[2]["status"] == "DELETED"
        assert response_data[2]["path"] == "old_file.py"

        mock_git_changes.assert_called_once_with(Path(test_path), ref=None)


@pytest.mark.asyncio
async def test_git_changes_query_param_empty_result(client):
    """使用查询参数测试 git 更改端点且没有更改。"""
    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = []

        test_path = "src/empty_repo"
        response = client.get("/api/git/changes", params={"path": test_path})

        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_git_changes_query_param_with_exception(client):
    """测试意外的 git 故障是否仍然显示为 500。"""
    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.side_effect = RuntimeError("unexpected failure")

        response = client.get("/api/git/changes", params={"path": "nonexistent/repo"})

        assert response.status_code == 500


@pytest.mark.asyncio
async def test_git_changes_query_param_with_command_error(client):
    """测试 git 更改为 GitCommandError 返回 400。"""
    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.side_effect = GitCommandError(
            message="git diff failed",
            command=["git", "diff"],
            exit_code=128,
            stderr="fatal: bad revision",
        )

        response = client.get("/api/git/changes", params={"path": "broken/repo"})

        assert response.status_code == 400
        assert "git diff failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_git_changes_returns_empty_list_when_path_is_not_git_repo(client):
    """非回购工作区应产生 200 + [] 而不是 500。

    重现 v1-conversation 错误，其中工作区目录存在但从未被 `git init`-ed：端点不得使“
    更改”选项卡崩溃。
    """
    # 安排
    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.side_effect = GitRepositoryError(
            "Not a git repository: /Users/hieple/.openhands/agent-server-gui"
        )

        # 法案
        response = client.get(
            "/api/git/changes",
            params={"path": "/Users/hieple/.openhands/agent-server-gui"},
        )

        # 断言
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
async def test_git_diff_returns_empty_diff_when_path_is_not_git_repo(client):
    """到 /api/git/diff 的非存储库路径应该产生 200 个带有 null 字段的结果。"""
    # 安排
    with patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff:
        mock_git_diff.side_effect = GitRepositoryError(
            "Not a git repository: /tmp/not-a-repo"
        )

        # 法案
        response = client.get(
            "/api/git/diff", params={"path": "/tmp/not-a-repo/file.py"}
        )

        # 断言
        assert response.status_code == 200
        body = response.json()
        assert body["modified"] is None
        assert body["original"] is None


@pytest.mark.asyncio
async def test_git_changes_query_param_ref_head_on_empty_repo_returns_200(
    client, tmp_path
):
    """端到端：``?ref=HEAD`` 在新初始化的存储库上必须返回 200。

    真正的 git repo（无模拟对象），因此 SDK 修复是通过路由器执行的。 重现错误：修复之
    前返回 400
    ``Git command failed: git --no-pager rev-parse --verify 'HEAD^{commit}'``.
    """
    # 排列：带有单个未跟踪文件的真正空 git 存储库。
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "untracked.txt").write_text("new")

    # 法案
    response = client.get(
        "/api/git/changes",
        params={"path": str(tmp_path), "ref": "HEAD"},
    )

    # 断言
    assert response.status_code == 200
    assert response.json() == [{"status": "ADDED", "path": "untracked.txt"}]


def test_git_changes_lists_repo_below_non_repo_path(client, tmp_path):
    """保存存储库的非存储库路径列出了该存储库的更改。

    真正的 git（无模拟对象）：用于回答 ``200 []`` 的存储库支持的对话的
    ``{base}/{repo}`` 工作区。
    """
    repo = tmp_path / "proj"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    (repo / "README.md").write_text("hello\n")
    git("add", "README.md")
    git("-c", "user.name=qa", "-c", "user.email=qa@example.com", "commit", "-qm", "i")
    (repo / "README.md").write_text("hello\nedit\n")
    (repo / "notes.txt").write_text("note\n")

    response = client.get("/api/git/changes", params={"path": str(tmp_path)})

    assert response.status_code == 200
    assert response.json() == [
        {"status": "UPDATED", "path": "proj/README.md"},
        {"status": "ADDED", "path": "proj/notes.txt"},
    ]


@pytest.mark.asyncio
async def test_git_changes_query_param_ref_head_on_orphan_branch_returns_200(
    client, tmp_path
):
    """端到端：孤立分支上的 ``?ref=HEAD`` 必须返回 200。

    真正的 git repo（无模拟对象），因此 SDK 修复是通过路由器执行的。 该存储库在
    ``main`` 上有一个提交，但 HEAD 当前指向一个未出生的孤儿分
    支 - 正是用户报告的状态，显示为
    “更改”选项卡中的
    ``400 Bad Request: Git command failed: git --no-pager rev-parse --verify 'HEAD^{commit}'``
    。 早期的 ``_repo_has_commits`` 短路无法捕获这种情况（提交存在于 main 上），因此
    修复必须来自 ``rev-parse`` 故障处理程序
    。
    """  # noqa: E501

    # 安排：在主分支上进行一次提交，然后切换到一个孤立分支。
    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    run_git("init")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "user.name", "Test")
    (tmp_path / "committed.txt").write_text("on main")
    run_git("add", ".")
    run_git("commit", "-m", "on main")
    run_git("checkout", "--orphan", "orphan")
    run_git("rm", "-rf", "--cached", ".")
    (tmp_path / "untracked.txt").write_text("new")

    # 法案
    response = client.get(
        "/api/git/changes",
        params={"path": str(tmp_path), "ref": "HEAD"},
    )

    # 断言
    assert response.status_code == 200
    paths = {entry["path"] for entry in response.json()}
    assert "untracked.txt" in paths


@pytest.mark.asyncio
async def test_git_changes_missing_path_param(client):
    """测试 gitchanges端点当路径参数丢失时返回 422。"""
    response = client.get("/api/git/changes")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_git_changes_query_param_absolute_path(client):
    """使用查询参数和绝对路径测试 git 更改（主要修复用例）。"""
    expected_changes = [
        GitChange(status=GitChangeStatus.ADDED, path=Path("new_file.py")),
    ]

    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = expected_changes

        # 这是主要用例 - 带前导斜杠的绝对路径
        test_path = "/workspace/project"
        response = client.get("/api/git/changes", params={"path": test_path})

        assert response.status_code == 200
        assert len(response.json()) == 1
        mock_git_changes.assert_called_once_with(Path(test_path), ref=None)


@pytest.mark.asyncio
async def test_git_diff_query_param_success(client):
    """使用查询参数测试成功的 git diff 端点。"""
    expected_diff = GitDiff(
        modified="def new_function():\n    return 'updated'",
        original="def old_function():\n    return 'original'",
    )

    with patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff:
        mock_git_diff.return_value = expected_diff

        test_path = "src/test_file.py"
        response = client.get("/api/git/diff", params={"path": test_path})

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["modified"] == expected_diff.modified
        assert response_data["original"] == expected_diff.original
        mock_git_diff.assert_called_once_with(Path(test_path), ref=None)


@pytest.mark.asyncio
async def test_git_diff_query_param_with_none_values(client):
    """使用查询参数和 None 值测试 git diff 端点。"""
    expected_diff = GitDiff(modified=None, original=None)

    with patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff:
        mock_git_diff.return_value = expected_diff

        test_path = "nonexistent_file.py"
        response = client.get("/api/git/diff", params={"path": test_path})

        assert response.status_code == 200
        response_data = response.json()

        assert response_data["modified"] is None
        assert response_data["original"] is None


@pytest.mark.asyncio
async def test_git_diff_query_param_with_command_error(client):
    """测试 git diff 对于 GitCommandError 返回 400。"""
    with patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff:
        mock_git_diff.side_effect = GitCommandError(
            message="git diff failed",
            command=["git", "diff"],
            exit_code=128,
            stderr="fatal: bad revision",
        )

        response = client.get("/api/git/diff", params={"path": "broken/file.py"})

        assert response.status_code == 400
        assert "git diff failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_git_diff_missing_path_param(client):
    """测试 git diff 端点当路径参数丢失时返回 422。"""
    response = client.get("/api/git/diff")

    assert response.status_code == 422


# =============================================================================
# 额外的边缘情况测试
# =============================================================================


@pytest.mark.asyncio
async def test_git_changes_with_all_status_types(client):
    """使用所有可能的 GitChangeStatus 值测试 git 更改端点。"""
    expected_changes = [
        GitChange(status=GitChangeStatus.ADDED, path=Path("added.py")),
        GitChange(status=GitChangeStatus.UPDATED, path=Path("updated.py")),
        GitChange(status=GitChangeStatus.DELETED, path=Path("deleted.py")),
        GitChange(status=GitChangeStatus.MOVED, path=Path("moved.py")),
    ]

    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = expected_changes

        test_path = "src/test_repo"
        response = client.get("/api/git/changes", params={"path": test_path})

        assert response.status_code == 200
        response_data = response.json()

        assert len(response_data) == 4
        assert response_data[0]["status"] == "ADDED"
        assert response_data[1]["status"] == "UPDATED"
        assert response_data[2]["status"] == "DELETED"
        assert response_data[3]["status"] == "MOVED"


@pytest.mark.asyncio
async def test_git_changes_with_complex_paths(client):
    """使用复杂的文件路径测试 git 更改端点。"""
    expected_changes = [
        GitChange(
            status=GitChangeStatus.ADDED,
            path=Path("src/deep/nested/file.py"),
        ),
        GitChange(
            status=GitChangeStatus.UPDATED,
            path=Path("file with spaces.txt"),
        ),
        GitChange(
            status=GitChangeStatus.DELETED,
            path=Path("special-chars_file@123.py"),
        ),
    ]

    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = expected_changes

        test_path = "src/complex_repo"
        response = client.get("/api/git/changes", params={"path": test_path})

        assert response.status_code == 200
        response_data = response.json()

        assert len(response_data) == 3
        assert response_data[0]["path"] == "src/deep/nested/file.py"
        assert response_data[1]["path"] == "file with spaces.txt"
        assert response_data[2]["path"] == "special-chars_file@123.py"


@pytest.mark.asyncio
async def test_git_changes_forwards_ref_query_param(client):
    """``ref`` 查询参数应连接至 ``get_git_changes``。"""
    with patch("openhands.agent_server.git_router.get_git_changes") as mock_git_changes:
        mock_git_changes.return_value = []

        test_path = "src/test_repo"
        response = client.get(
            "/api/git/changes", params={"path": test_path, "ref": "HEAD"}
        )

        assert response.status_code == 200
        mock_git_changes.assert_called_once_with(Path(test_path), ref="HEAD")


@pytest.mark.asyncio
async def test_git_diff_forwards_ref_query_param(client):
    """``ref`` 查询参数应连接至 ``get_git_diff``。"""
    with patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff:
        mock_git_diff.return_value = GitDiff(modified="m", original="o")

        test_path = "src/test_file.py"
        response = client.get(
            "/api/git/diff",
            params={"path": test_path, "ref": "abc1234"},
        )

        assert response.status_code == 200
        mock_git_diff.assert_called_once_with(Path(test_path), ref="abc1234")


def test_git_endpoints_expose_ref_query_param(client):
    """OpenAPI 模式应通告新的可选 ``ref`` 查询参数。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    for endpoint in ("/api/git/changes", "/api/git/diff"):
        params = paths[endpoint]["get"]["parameters"]
        ref_param = next((p for p in params if p["name"] == "ref"), None)
        assert ref_param is not None, f"ref param missing on {endpoint}"
        assert ref_param["in"] == "query"
        assert ref_param.get("required", False) is False


def test_git_legacy_routes_are_removed_from_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_paths = response.json()["paths"]
    assert "/api/git/changes/{path}" not in openapi_paths
    assert "/api/git/diff/{path}" not in openapi_paths


# =============================================================================
# 提交历史测试
# =============================================================================


_SAMPLE_COMMIT = GitCommit(
    sha="a" * 40,
    short_sha="aaaaaaa",
    subject="add logging",
    author="Agent",
    timestamp="2026-07-10T12:00:00+07:00",
)


@pytest.mark.asyncio
async def test_git_commits_query_success(client):
    """提交端点转发到 SDK 并序列化页面。"""
    with patch("openhands.agent_server.git_router.get_git_commits") as mock_commits:
        mock_commits.return_value = GitCommitsPage(
            commits=[_SAMPLE_COMMIT], has_more=True
        )

        response = client.get("/api/git/commits", params={"path": "src/repo"})

        assert response.status_code == 200
        assert response.json() == {
            "commits": [
                {
                    "sha": "a" * 40,
                    "short_sha": "aaaaaaa",
                    "subject": "add logging",
                    "author": "Agent",
                    "timestamp": "2026-07-10T12:00:00+07:00",
                }
            ],
            "has_more": True,
        }
        mock_commits.assert_called_once_with(Path("src/repo"), limit=50)


@pytest.mark.asyncio
async def test_git_commits_query_not_a_repo_returns_empty_page(client):
    """非 repo 工作区会产生一个空页，而不是错误。"""
    with patch("openhands.agent_server.git_router.get_git_commits") as mock_commits:
        mock_commits.side_effect = GitRepositoryError("not a git repository")

        response = client.get("/api/git/commits", params={"path": "/not-a-repo"})

        assert response.status_code == 200
        assert response.json() == {"commits": [], "has_more": False}


@pytest.mark.asyncio
async def test_git_commit_changes_query_success(client):
    """每次提交更改端点转发 sha 和 repo 路径。"""
    sha = "b" * 40
    with patch("openhands.agent_server.git_router.get_commit_changes") as mock_changes:
        mock_changes.return_value = [
            GitChange(status=GitChangeStatus.DELETED, path=Path("doomed.txt"))
        ]

        response = client.get(
            f"/api/git/commits/{sha}/changes", params={"path": "src/repo"}
        )

        assert response.status_code == 200
        assert response.json() == [{"status": "DELETED", "path": "doomed.txt"}]
        mock_changes.assert_called_once_with(Path("src/repo"), sha)


def test_git_commit_changes_query_malformed_sha_is_rejected(client):
    """非十六进制 sha 在到达 git argv 之前会失败验证。"""
    response = client.get(
        "/api/git/commits/not-a-sha/changes", params={"path": "src/repo"}
    )

    assert response.status_code == 422


def test_git_diff_query_rejects_ref_and_commit_together(client):
    """``ref`` 和 ``commit`` 在 /diff. 上互斥"""
    response = client.get(
        "/api/git/diff",
        params={"path": "src/repo/f.txt", "ref": "HEAD", "commit": "a" * 40},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_git_diff_query_commit_param_uses_commit_file_diff(client):
    """``commit=`` 路由到 git-object diff，而不是工作树 diff。"""
    sha = "c" * 40
    with (
        patch(
            "openhands.agent_server.git_router.get_commit_file_diff"
        ) as mock_commit_diff,
        patch("openhands.agent_server.git_router.get_git_diff") as mock_git_diff,
    ):
        mock_commit_diff.return_value = GitDiff(modified="", original="contents")

        response = client.get(
            "/api/git/diff", params={"path": "src/repo/doomed.txt", "commit": sha}
        )

        assert response.status_code == 200
        assert response.json() == {"modified": "", "original": "contents"}
        mock_commit_diff.assert_called_once_with(Path("src/repo/doomed.txt"), sha)
        mock_git_diff.assert_not_called()


def test_git_commit_endpoints_in_openapi(client):
    """模式通告提交路由和 /diff 提交参数。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/git/commits" in paths
    assert "/api/git/commits/{sha}/changes" in paths
    diff_params = paths["/api/git/diff"]["get"]["parameters"]
    commit_param = next((p for p in diff_params if p["name"] == "commit"), None)
    assert commit_param is not None
    assert commit_param["in"] == "query"
    assert commit_param.get("required", False) is False
