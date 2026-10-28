"""技能路由器测试端点。"""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app
from openhands.agent_server.config import Config
from openhands.agent_server.skills_service import MarketplaceSkillInfo, SkillLoadResult
from openhands.sdk.extensions.fetch import ExtensionFetchError
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.skills import (
    InstalledSkillInfo,
    KeywordTrigger,
    Skill,
    SkillFetchError,
    SkillValidationError,
)


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    config = Config(session_api_keys=[])  # 禁用身份验证
    return TestClient(create_app(config), raise_server_exceptions=False)


@pytest.fixture
def mock_installed_skill_info():
    """创建模拟对象 InstalledSkillInfo 进行测试。"""
    return InstalledSkillInfo(
        name="test-skill",
        version="1.0.0",
        description="A test skill",
        enabled=True,
        source="github:owner/repo/skills/test-skill",
        resolved_ref="abc123",
        repo_path=None,
        installed_at="2024-01-01T00:00:00Z",
        install_path=Path("/home/user/.openhands/skills/installed/test-skill"),
    )


class TestGetSkillsEndpoint:
    """测试 POST /skills 端点。"""

    def test_get_skills_default_request(self, client):
        """在启用所有来源的情况下测试默认技能请求。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(
                skills=[
                    Skill(name="test-skill", content="content", trigger=None),
                ],
                sources={"public": 1, "user": 0, "project": 0, "org": 0, "sandbox": 0},
            )

            response = client.post("/api/skills", json={})

            assert response.status_code == 200
            data = response.json()
            assert "skills" in data
            assert "sources" in data
            assert len(data["skills"]) == 1
            assert data["skills"][0]["name"] == "test-skill"

    def test_get_skills_with_project_dir(self, client):
        """使用项目目录测试技能请求。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "project_dir": "/workspace/myproject",
                    "load_project": True,
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["project_dir"] == "/workspace/myproject"
            assert call_kwargs["load_project"] is True

    def test_get_skills_with_org_configs_list(self, client):
        """多个 org_configs 作为 (url, name) 的有序列表转发。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "load_org": True,
                    "org_configs": [
                        {
                            "repository": "hieptl/.openhands",
                            "provider": "github",
                            "org_repo_url": "https://github.com/hieptl/.openhands",
                            "org_name": "hieptl",
                        },
                        {
                            "repository": "hieptl/.agents",
                            "provider": "github",
                            "org_repo_url": "https://github.com/hieptl/.agents",
                            "org_name": "hieptl",
                        },
                    ],
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            assert mock_load.call_args[1]["org_repos"] == [
                ("https://github.com/hieptl/.openhands", "hieptl"),
                ("https://github.com/hieptl/.agents", "hieptl"),
            ]

    def test_get_skills_with_registered_marketplaces(self, client):
        """已注册的市场将转发至技能服务。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/marketplace",
                            "ref": "main",
                            "repo_path": "marketplace",
                            "auto_load": True,
                        }
                    ]
                },
            )

            assert response.status_code == 200
            registrations = mock_load.call_args[1]["registered_marketplaces"]
            assert len(registrations) == 1
            assert registrations[0].name == "team"
            assert registrations[0].source == "https://github.com/org/marketplace"
            assert registrations[0].ref == "main"
            assert registrations[0].repo_path == "marketplace"
            assert registrations[0].auto_load is True

    def test_get_skills_with_selective_auto_load_marketplace(self, client):
        """注册市场接受选择性 auto_load 插件列表。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/marketplace",
                            "auto_load": ["formatter", "linter"],
                        }
                    ]
                },
            )

            assert response.status_code == 200
            registrations = mock_load.call_args[1]["registered_marketplaces"]
            assert len(registrations) == 1
            assert registrations[0].auto_load == ["formatter", "linter"]

    def test_get_skills_merges_server_registered_marketplaces(self):
        """服务器默认市场包含在请求市场中。"""
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="default",
                    source="https://github.com/org/default-marketplace",
                    auto_load=True,
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/team-marketplace",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        registrations = mock_load.call_args[1]["registered_marketplaces"]
        assert [registration.name for registration in registrations] == [
            "default",
            "team",
        ]

    def test_get_skills_server_manual_marketplace_keeps_public_skills(self):
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="manual",
                    source="https://github.com/org/manual-marketplace",
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        public_skill = Skill(name="public-skill", content="public", trigger=None)

        with patch(
            "openhands.agent_server.skills_service.load_available_skills",
            side_effect=[{"public-skill": public_skill}, {}],
        ) as mock_load_available:
            response = client.post(
                "/api/skills",
                json={
                    "load_user": False,
                    "load_project": False,
                    "load_org": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert [skill["name"] for skill in data["skills"]] == ["public-skill"]
        assert data["sources"]["registered_marketplaces"] == 0
        assert data["sources"]["sdk_base"] == 1
        assert mock_load_available.call_args_list[0].kwargs["include_public"] is True

    def test_get_skills_request_marketplace_overrides_server_default(self):
        """请求注册会覆盖同名服务器的默认设置。"""
        config = Config(
            session_api_keys=[],
            registered_marketplaces=[
                MarketplaceRegistration(
                    name="team",
                    source="https://github.com/org/default-marketplace",
                )
            ],
        )
        client = TestClient(create_app(config), raise_server_exceptions=False)
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "registered_marketplaces": [
                        {
                            "name": "team",
                            "source": "https://github.com/org/request-marketplace",
                        }
                    ]
                },
            )

        assert response.status_code == 200
        registrations = mock_load.call_args[1]["registered_marketplaces"]
        assert len(registrations) == 1
        assert registrations[0].source == "https://github.com/org/request-marketplace"

    def test_get_skills_with_sandbox_config(self, client):
        """使用沙箱配置测试技能请求。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(
                skills=[Skill(name="work_hosts", content="host info", trigger=None)],
                sources={"sandbox": 1},
            )

            response = client.post(
                "/api/skills",
                json={
                    "sandbox_config": {
                        "exposed_urls": [
                            {
                                "name": "WORKER_8080",
                                "url": "http://localhost:8080",
                                "port": 8080,
                            }
                        ]
                    }
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["sandbox_exposed_urls"] is not None
            assert len(call_kwargs["sandbox_exposed_urls"]) == 1
            assert call_kwargs["sandbox_exposed_urls"][0].name == "WORKER_8080"

    def test_get_skills_disabled_sources(self, client):
        """在禁用源的情况下测试技能请求。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            response = client.post(
                "/api/skills",
                json={
                    "load_public": False,
                    "load_user": False,
                    "load_project": False,
                    "load_org": False,
                },
            )

            assert response.status_code == 200
            mock_load.assert_called_once()
            call_kwargs = mock_load.call_args[1]
            assert call_kwargs["load_public"] is False
            assert call_kwargs["load_user"] is False
            assert call_kwargs["load_project"] is False
            assert call_kwargs["load_org"] is False

    def test_get_skills_converts_skill_to_skill_info(self, client):
        """测试 Skill 对象是否正确转换为 SkillInfo 格式。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(
                skills=[
                    Skill(
                        name="knowledge-skill",
                        content="knowledge content",
                        trigger=KeywordTrigger(keywords=["python", "coding"]),
                        source="/path/to/skill.md",
                        description="A knowledge skill",
                    ),
                ],
                sources={"public": 1},
            )

            response = client.post("/api/skills", json={})

            assert response.status_code == 200
            data = response.json()
            skill_info = data["skills"][0]
            assert skill_info["name"] == "knowledge-skill"
            assert skill_info["type"] == "knowledge"
            assert skill_info["content"] == "knowledge content"
            assert skill_info["triggers"] == ["python", "coding"]
            assert skill_info["source"] == "/path/to/skill.md"
            assert skill_info["description"] == "A knowledge skill"
            assert skill_info["is_agentskills_format"] is False

    def test_get_skills_agent_skill_format(self, client):
        """测试 AgentSkills 格式是否正确表示。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(
                skills=[
                    Skill(
                        name="agent-skill",
                        content="agent content",
                        trigger=None,
                        is_agentskills_format=True,
                        disable_model_invocation=True,
                    ),
                ],
                sources={"public": 1},
            )

            response = client.post("/api/skills", json={})

            assert response.status_code == 200
            data = response.json()
            skill_info = data["skills"][0]
            assert skill_info["type"] == "agentskills"
            assert skill_info["is_agentskills_format"] is True
            assert skill_info["disable_model_invocation"] is True

    def test_get_skills_response_sources(self, client):
        """测试响应中是否包含源计数。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(
                skills=[],
                sources={
                    "public": 10,
                    "user": 5,
                    "project": 3,
                    "org": 2,
                    "sandbox": 1,
                },
            )

            response = client.post("/api/skills", json={})

            assert response.status_code == 200
            data = response.json()
            assert data["sources"]["public"] == 10
            assert data["sources"]["user"] == 5
            assert data["sources"]["project"] == 3
            assert data["sources"]["org"] == 2
            assert data["sources"]["sandbox"] == 1


def test_skill_catalog_lists_profile_skills_with_their_origin(client):
    catalog = [
        Skill(name="from-catalog", content="c", description="catalog skill"),
        Skill(name="mine", content="m", description="user skill"),
        Skill(name="shadowed", content="s", description="user copy"),
    ]
    with (
        patch(
            "openhands.agent_server.skills_router.discover_profile_skills",
            return_value=catalog,
        ),
        patch(
            "openhands.agent_server.skills_router.discover_public_skill_names",
            return_value={"from-catalog"},
        ),
    ):
        response = client.get("/api/skills/catalog")

    assert response.status_code == 200
    skills = response.json()["skills"]
    assert [(s["name"], s["origin"]) for s in skills] == [
        ("from-catalog", "public"),
        ("mine", "user"),
        ("shadowed", "user"),
    ]
    assert skills[0]["description"] == "catalog skill"


class TestSyncSkillsEndpoint:
    """测试 POST /skills/sync 端点。"""

    def test_sync_skills_success(self, client):
        """测试成功的技能同步。"""
        with patch(
            "openhands.agent_server.skills_router.sync_public_skills"
        ) as mock_sync:
            mock_sync.return_value = (True, "Skills synced successfully")

            response = client.post("/api/skills/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "synced" in data["message"].lower()

    def test_sync_skills_failure(self, client):
        """测试失败的技能同步。"""
        with patch(
            "openhands.agent_server.skills_router.sync_public_skills"
        ) as mock_sync:
            mock_sync.return_value = (False, "Network error occurred")

            response = client.post("/api/skills/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            msg_lower = data["message"].lower()
            assert "error" in msg_lower or "network" in msg_lower


class TestPydanticModels:
    """测试 Pydantic 模型验证。"""

    def test_exposed_url_validation(self, client):
        """测试 ExposedUrl 模型验证。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            # 有效曝光 URL
            response = client.post(
                "/api/skills",
                json={
                    "sandbox_config": {
                        "exposed_urls": [
                            {
                                "name": "WORKER_8080",
                                "url": "http://localhost:8080",
                                "port": 8080,
                            }
                        ]
                    }
                },
            )
            assert response.status_code == 200

    def test_org_configs_validation(self, client):
        """通过 org_configs 列表测试 OrgConfig 模型验证。"""
        with patch("openhands.agent_server.skills_router.load_all_skills") as mock_load:
            mock_load.return_value = SkillLoadResult(skills=[], sources={})

            # 有效的组织配置
            response = client.post(
                "/api/skills",
                json={
                    "org_configs": [
                        {
                            "repository": "org/repo",
                            "provider": "github",
                            "org_repo_url": "https://github.com/org/.openhands",
                            "org_name": "org",
                        }
                    ]
                },
            )
            assert response.status_code == 200

    def test_invalid_request_body(self, client):
        """测试无效请求正文的处理。"""
        # 发送无效的JSON结构
        response = client.post(
            "/api/skills",
            json={"load_public": "not_a_boolean"},
        )
        # FastAPI 对于验证个错误返回 422
        assert response.status_code == 422

    def test_missing_required_org_configs_fields(self, client):
        """当 org_configs 条目缺少必填字段时测试验证。"""
        response = client.post(
            "/api/skills",
            json={
                "org_configs": [
                    {
                        "repository": "org/repo",
                        # 缺少提供者，org_repo_url，org_name
                    }
                ]
            },
        )
        assert response.status_code == 422


class TestInstallSkillEndpoint:
    """测试 POST /skills/install 端点。"""

    def test_install_skill_success(self, client, mock_installed_skill_info):
        """测试技能安装是否成功。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.return_value = mock_installed_skill_info

            response = client.post(
                "/api/skills/install",
                json={"source": "github:owner/repo/skills/test-skill"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-skill"
            assert data["source"] == "github:owner/repo/skills/test-skill"
            assert data["enabled"] is True

    def test_install_skill_with_force(self, client, mock_installed_skill_info):
        """使用强制选项测试技能安装。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.return_value = mock_installed_skill_info

            response = client.post(
                "/api/skills/install",
                json={
                    "source": "github:owner/repo/skills/test-skill",
                    "force": True,
                },
            )

            assert response.status_code == 200
            mock_install.assert_called_once()
            call_kwargs = mock_install.call_args[1]
            assert call_kwargs["force"] is True

    def test_install_skill_with_ref(self, client, mock_installed_skill_info):
        """使用特定参考测试技能安装。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.return_value = mock_installed_skill_info

            response = client.post(
                "/api/skills/install",
                json={
                    "source": "github:owner/repo",
                    "ref": "v1.0.0",
                    "repo_path": "skills/test-skill",
                },
            )

            assert response.status_code == 200
            mock_install.assert_called_once()
            call_kwargs = mock_install.call_args[1]
            assert call_kwargs["ref"] == "v1.0.0"
            assert call_kwargs["repo_path"] == "skills/test-skill"

    def test_install_skill_already_exists(self, client):
        """当技能已经存在时测试技能安装。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.side_effect = FileExistsError("Skill already exists")

            response = client.post(
                "/api/skills/install",
                json={"source": "github:owner/repo/skills/test-skill"},
            )

            assert response.status_code == 409
            assert "already installed" in response.json()["detail"].lower()

    def test_install_skill_fetch_error(self, client):
        """测试技能安装时出现获取错误。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.side_effect = SkillFetchError("Network error")

            response = client.post(
                "/api/skills/install",
                json={"source": "github:owner/repo/skills/test-skill"},
            )

            assert response.status_code == 400
            assert "fetch" in response.json()["detail"].lower()

    def test_install_skill_extension_fetch_error(self, client):
        """ExtensionFetchError（由 SDK 提出 GitHub URL/简写失败）
        必须映射到 400，而不是 500。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.side_effect = ExtensionFetchError(
                "Could not fetch from GitHub"
            )

            response = client.post(
                "/api/skills/install",
                json={"source": "https://github.com/Owner/repo/tree/main/path"},
            )

            assert response.status_code == 400
            assert "fetch" in response.json()["detail"].lower()

    def test_install_skill_validation_error(self, client):
        """测试技能安装时出现验证错误。"""
        with patch(
            "openhands.agent_server.skills_router.service_install_skill"
        ) as mock_install:
            mock_install.side_effect = SkillValidationError("Missing SKILL.md")

            response = client.post(
                "/api/skills/install",
                json={"source": "/path/to/invalid-skill"},
            )

            assert response.status_code == 422
            assert "invalid" in response.json()["detail"].lower()


class TestListInstalledSkillsEndpoint:
    """测试 GET /skills/installed 端点。"""

    def test_list_installed_skills_empty(self, client):
        """未安装技能时测试列表。"""
        with patch(
            "openhands.agent_server.skills_router.service_list_installed_skills"
        ) as mock_list:
            mock_list.return_value = []

            response = client.get("/api/skills/installed")

            assert response.status_code == 200
            data = response.json()
            assert data["skills"] == []

    def test_list_installed_skills_with_skills(self, client, mock_installed_skill_info):
        """测试列出已安装的技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_list_installed_skills"
        ) as mock_list:
            mock_list.return_value = [mock_installed_skill_info]

            response = client.get("/api/skills/installed")

            assert response.status_code == 200
            data = response.json()
            assert len(data["skills"]) == 1
            assert data["skills"][0]["name"] == "test-skill"


class TestGetInstalledSkillEndpoint:
    """测试 GET /skills/installed/{skill_name} 端点。"""

    def test_get_installed_skill_found(self, client, mock_installed_skill_info):
        """测试获取现有的已安装技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_get_installed_skill"
        ) as mock_get:
            mock_get.return_value = mock_installed_skill_info

            response = client.get("/api/skills/installed/test-skill")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-skill"

    def test_get_installed_skill_not_found(self, client):
        """测试获取未安装的技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_get_installed_skill"
        ) as mock_get:
            mock_get.return_value = None

            response = client.get("/api/skills/installed/nonexistent")

            assert response.status_code == 404
            assert "not installed" in response.json()["detail"].lower()


class TestUpdateSkillStateEndpoint:
    """测试 PATCH /skills/installed/{skill_name} 端点。"""

    def test_enable_skill_success(self, client):
        """测试启用技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_enable_skill"
        ) as mock_enable:
            mock_enable.return_value = True

            response = client.patch(
                "/api/skills/installed/test-skill",
                json={"enabled": True},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test-skill"
            assert data["enabled"] is True

    def test_disable_skill_success(self, client):
        """测试禁用技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_disable_skill"
        ) as mock_disable:
            mock_disable.return_value = True

            response = client.patch(
                "/api/skills/installed/test-skill",
                json={"enabled": False},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] is False

    def test_update_skill_state_not_found(self, client):
        """测试不存在的技能的更新状态。"""
        with patch(
            "openhands.agent_server.skills_router.service_enable_skill"
        ) as mock_enable:
            mock_enable.return_value = False

            response = client.patch(
                "/api/skills/installed/nonexistent",
                json={"enabled": True},
            )

            assert response.status_code == 404


class TestUninstallSkillEndpoint:
    """测试 DELETE /skills/installed/{skill_name} 端点。"""

    def test_uninstall_skill_success(self, client):
        """测试技能卸载成功。"""
        with patch(
            "openhands.agent_server.skills_router.service_uninstall_skill"
        ) as mock_uninstall:
            mock_uninstall.return_value = True

            response = client.delete("/api/skills/installed/test-skill")

            assert response.status_code == 200
            data = response.json()
            assert "uninstalled" in data["message"].lower()

    def test_uninstall_skill_not_found(self, client):
        """测试卸载不存在的技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_uninstall_skill"
        ) as mock_uninstall:
            mock_uninstall.return_value = False

            response = client.delete("/api/skills/installed/nonexistent")

            assert response.status_code == 404


class TestRefreshSkillEndpoint:
    """测试 POST /skills/installed/{skill_name}/refresh 端点。"""

    def test_refresh_skill_success(self, client, mock_installed_skill_info):
        """测试技能刷新成功。"""
        with patch(
            "openhands.agent_server.skills_router.service_update_skill"
        ) as mock_update:
            mock_update.return_value = mock_installed_skill_info

            response = client.post("/api/skills/installed/test-skill/refresh")

            assert response.status_code == 200
            data = response.json()
            assert data["skill"]["name"] == "test-skill"

    def test_refresh_skill_not_found(self, client):
        """测试刷新一个不存在的技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_update_skill"
        ) as mock_update:
            mock_update.return_value = None

            response = client.post("/api/skills/installed/nonexistent/refresh")

            assert response.status_code == 404

    def test_refresh_vanished_source_is_400_and_keeps_skill(
        self, client, tmp_path, monkeypatch
    ):
        """记录来源消失无法刷新的技能：路线
        像安装一样回答 400，并且安装的副本会保留。"""
        store = tmp_path / "installed-store"
        store.mkdir()
        monkeypatch.setattr(
            "openhands.sdk.skills.installed.DEFAULT_INSTALLED_SKILLS_DIR", store
        )
        src = tmp_path / "gone-skill"
        src.mkdir()
        (src / "SKILL.md").write_text(
            "---\nname: gone-skill\ndescription: Source that vanishes\n---\nBody\n"
        )
        installed = client.post("/api/skills/install", json={"source": str(src)})
        assert installed.status_code == 200
        shutil.rmtree(src)

        response = client.post("/api/skills/installed/gone-skill/refresh")

        assert response.status_code == 400
        assert "fetch" in response.json()["detail"].lower()
        kept = client.get("/api/skills/installed/gone-skill")
        assert kept.status_code == 200
        assert kept.json()["enabled"] is True

    def test_refresh_source_without_skill_md_is_422_and_keeps_skill(
        self, client, tmp_path, monkeypatch
    ):
        """不再包含 SKILL.md 的源是 422，如安装时一样，并且
        稍后的有效刷新仍然会成功。"""
        store = tmp_path / "installed-store"
        store.mkdir()
        monkeypatch.setattr(
            "openhands.sdk.skills.installed.DEFAULT_INSTALLED_SKILLS_DIR", store
        )
        src = tmp_path / "broken-skill"
        src.mkdir()
        skill_md = "---\nname: broken-skill\ndescription: Becomes invalid\n---\nBody\n"
        (src / "SKILL.md").write_text(skill_md)
        assert (
            client.post("/api/skills/install", json={"source": str(src)}).status_code
            == 200
        )
        (src / "SKILL.md").unlink()

        response = client.post("/api/skills/installed/broken-skill/refresh")

        assert response.status_code == 422
        kept = client.get("/api/skills/installed/broken-skill")
        assert kept.status_code == 200
        assert kept.json()["enabled"] is True

        (src / "SKILL.md").write_text(skill_md)
        assert (
            client.post("/api/skills/installed/broken-skill/refresh").status_code == 200
        )

    def test_refresh_fetch_error_returns_400(self, client):
        """SDK 无法解析的源 (e.g. ``local`` 对于采用的技能）
        是客户端错误，而不是 500。"""
        with patch(
            "openhands.agent_server.skills_router.service_update_skill"
        ) as mock_update:
            mock_update.side_effect = ExtensionFetchError(
                "Unable to parse extension source: local"
            )

            response = client.post("/api/skills/installed/test-skill/refresh")

            assert response.status_code == 400

    def test_refresh_validation_error_returns_422(self, client):
        """现在拥有无效技能的源是 422，如安装时一样。"""
        with patch(
            "openhands.agent_server.skills_router.service_update_skill"
        ) as mock_update:
            mock_update.side_effect = SkillValidationError("Missing SKILL.md")

            response = client.post("/api/skills/installed/test-skill/refresh")

            assert response.status_code == 422
            assert "no longer holds a valid skill" in response.json()["detail"].lower()


class TestMarketplaceCatalogEndpoint:
    """测试 GET /skills/marketplace 端点。"""

    def test_get_marketplace_catalog_empty(self, client):
        """在没有可用技能的情况下测试进入市场。"""
        with patch(
            "openhands.agent_server.skills_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = []

            response = client.get("/api/skills/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert data["skills"] == []

    def test_get_marketplace_catalog_with_skills(self, client):
        """测试利用可用技能进入市场。"""
        with patch(
            "openhands.agent_server.skills_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = [
                MarketplaceSkillInfo(
                    name="github",
                    description="GitHub integration skill",
                    source="github:OpenHands/extensions/skills/github",
                    installed=True,
                ),
                MarketplaceSkillInfo(
                    name="docker",
                    description="Docker management skill",
                    source="github:OpenHands/extensions/skills/docker",
                    installed=False,
                ),
            ]

            response = client.get("/api/skills/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert len(data["skills"]) == 2

            # 检查第一个技能
            assert data["skills"][0]["name"] == "github"
            assert data["skills"][0]["description"] == "GitHub integration skill"
            assert data["skills"][0]["installed"] is True

            # 检查第二项技能
            assert data["skills"][1]["name"] == "docker"
            assert data["skills"][1]["installed"] is False

    def test_get_marketplace_catalog_skill_without_description(self, client):
        """在没有描述的情况下测试市场技能。"""
        with patch(
            "openhands.agent_server.skills_router.service_get_marketplace_catalog"
        ) as mock_catalog:
            mock_catalog.return_value = [
                MarketplaceSkillInfo(
                    name="minimal-skill",
                    description=None,
                    source="github:owner/repo",
                    installed=False,
                ),
            ]

            response = client.get("/api/skills/marketplace")

            assert response.status_code == 200
            data = response.json()
            assert len(data["skills"]) == 1
            assert data["skills"][0]["description"] is None
