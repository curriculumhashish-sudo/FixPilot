"""技能服务测试。"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from openhands.agent_server.skills_service import (
    SANDBOX_WORKER_URL_PREFIX,
    ExposedUrlData,
    SkillLoadResult,
    create_sandbox_skill,
    discover_profile_skills,
    discover_public_skill_names,
    load_all_skills,
    load_org_skills_from_url,
    load_registered_marketplace_skills,
    merge_skills,
    sync_public_skills,
)
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.skills import Skill


def _create_test_plugin(plugin_dir: Path, name: str, skill_name: str) -> Path:
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0"})
    )
    skills_dir = plugin_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / f"{skill_name}.md").write_text(
        f"---\nname: {skill_name}\n---\n{skill_name} content"
    )
    return plugin_dir


def _create_test_marketplace(marketplace_dir: Path) -> Path:
    _create_test_plugin(marketplace_dir / "plugins" / "auto", "auto", "auto-skill")
    _create_test_plugin(
        marketplace_dir / "plugins" / "manual", "manual", "manual-skill"
    )
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "test-marketplace",
                "owner": {"name": "Test Team"},
                "plugins": [
                    {"name": "auto", "source": "./plugins/auto"},
                    {"name": "manual", "source": "./plugins/manual"},
                ],
            }
        )
    )
    return marketplace_dir


def _create_standalone_skill(skill_dir: Path, name: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n{name} content"
    )


def _create_skills_only_marketplace(marketplace_dir: Path) -> Path:
    """市场仅声明独立技能（无插件）。"""
    _create_standalone_skill(marketplace_dir / "skills" / "greet", "greet")
    _create_standalone_skill(marketplace_dir / "skills" / "commit", "commit")
    manifest_dir = marketplace_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "skills-marketplace",
                "owner": {"name": "Test Team"},
                "plugins": [],
                "skills": [
                    {"name": "greet", "source": "./skills/greet"},
                    {"name": "commit", "source": "./skills/commit"},
                ],
            }
        )
    )
    return marketplace_dir


class TestExposedUrlData:
    """测试 ExposedUrlData 数据类。"""

    def test_create_exposed_url_data(self):
        """测试创建 ExposedUrlData 实例。"""
        url_data = ExposedUrlData(
            name="WORKER_8080",
            url="http://localhost:8080",
            port=8080,
        )
        assert url_data.name == "WORKER_8080"
        assert url_data.url == "http://localhost:8080"
        assert url_data.port == 8080


class TestCreateSandboxSkill:
    """测试 create_sandbox_skill 功能。"""

    def test_create_sandbox_skill_with_worker_urls(self):
        """测试带有 WORKER_ 前缀的 URLs 预置的沙盒技能。"""
        exposed_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:8080", port=8080),
            ExposedUrlData(name="WORKER_3000", url="http://localhost:3000", port=3000),
        ]

        skill = create_sandbox_skill(exposed_urls)

        assert skill is not None
        assert skill.name == "work_hosts"
        assert "http://localhost:8080" in skill.content
        assert "http://localhost:3000" in skill.content
        assert "port 8080" in skill.content
        assert "port 3000" in skill.content
        assert skill.trigger is None
        assert skill.source is None

    def test_create_sandbox_skill_no_worker_urls(self):
        """测试非WORKER_ URLs 被过滤掉。"""
        exposed_urls = [
            ExposedUrlData(name="DATABASE", url="http://localhost:5432", port=5432),
            ExposedUrlData(name="REDIS", url="http://localhost:6379", port=6379),
        ]

        skill = create_sandbox_skill(exposed_urls)

        assert skill is None

    def test_create_sandbox_skill_mixed_urls(self):
        """WORKER_ 和非WORKER_ URLs 进行测试。"""
        exposed_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:8080", port=8080),
            ExposedUrlData(name="DATABASE", url="http://localhost:5432", port=5432),
            ExposedUrlData(name="WORKER_3000", url="http://localhost:3000", port=3000),
        ]

        skill = create_sandbox_skill(exposed_urls)

        assert skill is not None
        assert "http://localhost:8080" in skill.content
        assert "http://localhost:3000" in skill.content
        assert "http://localhost:5432" not in skill.content

    def test_create_sandbox_skill_empty_list(self):
        """使用空的 URL 列表进行测试。"""
        skill = create_sandbox_skill([])
        assert skill is None

    def test_sandbox_worker_url_prefix_constant(self):
        """测试 SANDBOX_WORKER_URL_PREFIX 的定义是否正确。"""
        assert SANDBOX_WORKER_URL_PREFIX == "WORKER_"


class TestMergeSkills:
    """测试 merge_skills 功能。"""

    def test_merge_empty_lists(self):
        """测试合并空技能列表。"""
        result = merge_skills([[], [], []])
        assert result == []

    def test_merge_single_list(self):
        """测试合并单个技能列表。"""
        skills = [
            Skill(name="skill1", content="content1", trigger=None),
            Skill(name="skill2", content="content2", trigger=None),
        ]

        result = merge_skills([skills])

        assert len(result) == 2
        assert {s.name for s in result} == {"skill1", "skill2"}

    def test_merge_multiple_lists_no_duplicates(self):
        """测试合并多个不重复的列表。"""
        list1 = [Skill(name="skill1", content="content1", trigger=None)]
        list2 = [Skill(name="skill2", content="content2", trigger=None)]
        list3 = [Skill(name="skill3", content="content3", trigger=None)]

        result = merge_skills([list1, list2, list3])

        assert len(result) == 3
        assert {s.name for s in result} == {"skill1", "skill2", "skill3"}

    def test_merge_with_duplicates_later_wins(self):
        """测试稍后列出的内容是否会覆盖先前列出的重复名称。"""
        list1 = [Skill(name="skill1", content="original", trigger=None)]
        list2 = [Skill(name="skill1", content="override", trigger=None)]

        result = merge_skills([list1, list2])

        assert len(result) == 1
        assert result[0].name == "skill1"
        assert result[0].content == "override"

    def test_merge_preserves_precedence_order(self):
        """测试优先顺序是否得到维护（稍后覆盖之前）。"""
        list1 = [Skill(name="shared", content="first", trigger=None)]
        list2 = [Skill(name="shared", content="second", trigger=None)]
        list3 = [Skill(name="shared", content="third", trigger=None)]

        result = merge_skills([list1, list2, list3])

        assert len(result) == 1
        assert result[0].content == "third"


class TestLoadOrgSkillsFromUrl:
    """测试 load_org_skills_from_url 功能。"""

    def test_load_org_skills_git_clone_failure(self):
        """测试 git 克隆失败的处理。"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Git not found")

            result = load_org_skills_from_url(
                org_repo_url="https://github.com/org/.openhands",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_skills_repo_not_found(self):
        """未找到存储库的测试处理。"""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "clone"],
            )

            result = load_org_skills_from_url(
                org_repo_url="https://github.com/org/.openhands",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_skills_timeout(self):
        """测试 git clone 超时的处理。"""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "clone"],
                timeout=120,
            )

            result = load_org_skills_from_url(
                org_repo_url="https://github.com/org/.openhands",
                org_name="test-org",
            )

            assert result == []

    def test_load_org_skills_custom_working_dir(self):
        """使用自定义工作目录进行测试。"""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=128,
                    cmd=["git", "clone"],
                )

                result = load_org_skills_from_url(
                    org_repo_url="https://github.com/org/.openhands",
                    org_name="test-org",
                    working_dir=tmpdir,
                )

                assert result == []


class TestLoadAllSkills:
    """测试 load_all_skills 功能。"""

    _PATCH_TARGET = "openhands.agent_server.skills_service.load_available_skills"

    def test_load_all_skills_registered_marketplaces_keep_legacy_public(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")
        public_skill = Skill(name="public-skill", content="public", trigger=None)
        user_skill = Skill(name="user-skill", content="user", trigger=None)

        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"public-skill": public_skill, "user-skill": user_skill},
                {},
            ],
        ) as mock_avail:
            result = load_all_skills(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="test",
                        source=str(marketplace_dir),
                        auto_load=True,
                    )
                ],
            )

        skill_names = {skill.name for skill in result.skills}
        assert "auto-skill" in skill_names
        assert "manual-skill" in skill_names
        assert "public-skill" in skill_names
        assert "user-skill" in skill_names
        assert result.sources["registered_marketplaces"] == 2
        assert result.sources["sdk_base"] == 2
        assert mock_avail.call_args_list[0].kwargs["include_public"] is True

    def test_load_all_skills_non_auto_registered_marketplaces_keep_legacy_public(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")
        public_skill = Skill(name="public-skill", content="public", trigger=None)

        with patch(
            self._PATCH_TARGET, side_effect=[{"public-skill": public_skill}, {}]
        ) as mock_avail:
            result = load_all_skills(
                load_public=True,
                load_user=False,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(name="manual", source=str(marketplace_dir))
                ],
            )

        assert [skill.name for skill in result.skills] == ["public-skill"]
        assert result.sources["registered_marketplaces"] == 0
        assert mock_avail.call_args_list[0].kwargs["include_public"] is True

    def test_load_registered_marketplace_skills_uses_auto_load_registrations(
        self, tmp_path: Path
    ):
        """只有标记为 auto_load=True 的注册才能贡献插件技能。"""
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        skills = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="test",
                    source=str(marketplace_dir),
                    auto_load=True,
                ),
                MarketplaceRegistration(name="manual", source=str(marketplace_dir)),
            ]
        )

        assert {skill.name for skill in skills} == {"auto-skill", "manual-skill"}

    def test_load_registered_marketplace_skills_selects_listed_plugins(
        self, tmp_path: Path
    ):
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        skills = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="test",
                    source=str(marketplace_dir),
                    auto_load=["manual"],
                )
            ]
        )

        assert [skill.name for skill in skills] == ["manual-skill"]

    def test_load_registered_marketplace_skills_loads_standalone_skills(
        self, tmp_path: Path
    ):
        """auto_load=True loads standalone skills, not just plugins."""
        marketplace_dir = _create_skills_only_marketplace(tmp_path / "marketplace")

        skills = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="skills-only",
                    source=str(marketplace_dir),
                    auto_load=True,
                )
            ]
        )

        assert {skill.name for skill in skills} == {"greet", "commit"}

    def test_load_registered_marketplace_skills_selects_listed_standalone_skills(
        self, tmp_path: Path
    ):
        """名单选择独立技能的方式与选择插件的方式相同。"""
        marketplace_dir = _create_skills_only_marketplace(tmp_path / "marketplace")

        skills = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="skills-only",
                    source=str(marketplace_dir),
                    auto_load=["greet"],
                )
            ]
        )

        assert [skill.name for skill in skills] == ["greet"]

    def test_load_registered_marketplace_skills_skips_standalone_when_not_auto_load(
        self, tmp_path: Path
    ):
        """没有 auto_load 的纯技能市场没有任何贡献。"""
        marketplace_dir = _create_skills_only_marketplace(tmp_path / "marketplace")

        skills = load_registered_marketplace_skills(
            [MarketplaceRegistration(name="skills-only", source=str(marketplace_dir))]
        )

        assert skills == []

    def test_load_registered_marketplace_skills_loads_plain_skills_repository(
        self, tmp_path: Path
    ):
        """没有清单的存储库会贡献其技能文件夹。"""
        repo = tmp_path / "repo"
        _create_standalone_skill(repo / "skills" / "greet", "greet")
        _create_standalone_skill(repo / "skills" / "commit", "commit")

        loaded = load_registered_marketplace_skills(
            [MarketplaceRegistration(name="plain", source=str(repo), auto_load=True)]
        )
        selected = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="plain", source=str(repo), auto_load=["greet"]
                )
            ]
        )

        assert {skill.name for skill in loaded} == {"greet", "commit"}
        assert [skill.name for skill in selected] == ["greet"]

    def test_load_registered_marketplace_skills_loads_plugins_and_standalone(
        self, tmp_path: Path
    ):
        """具有插件和独立技能的市场会加载两者。"""
        marketplace_dir = tmp_path / "marketplace"
        _create_test_plugin(marketplace_dir / "plugins" / "auto", "auto", "auto-skill")
        _create_standalone_skill(marketplace_dir / "skills" / "greet", "greet")
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "mixed-marketplace",
                    "owner": {"name": "Test Team"},
                    "plugins": [{"name": "auto", "source": "./plugins/auto"}],
                    "skills": [{"name": "greet", "source": "./skills/greet"}],
                }
            )
        )

        skills = load_registered_marketplace_skills(
            [
                MarketplaceRegistration(
                    name="mixed", source=str(marketplace_dir), auto_load=True
                )
            ]
        )

        assert {skill.name for skill in skills} == {"auto-skill", "greet"}

    def test_plugin_wins_over_standalone_on_name_collision(self, tmp_path: Path):
        """插件技能会覆盖同名的独立技能（目录规则）。"""
        marketplace_dir = tmp_path / "marketplace"
        # 插件“p”捆绑了名为“共享”的技能。
        plugin_dir = marketplace_dir / "plugins" / "p"
        (plugin_dir / ".plugin").mkdir(parents=True)
        (plugin_dir / ".plugin" / "plugin.json").write_text(
            json.dumps({"name": "p", "version": "1.0.0"})
        )
        (plugin_dir / "skills").mkdir()
        (plugin_dir / "skills" / "shared.md").write_text(
            "---\nname: shared\n---\nFROM_PLUGIN"
        )
        # 独立技能也称为“共享”。
        standalone = marketplace_dir / "skills" / "shared"
        standalone.mkdir(parents=True)
        (standalone / "SKILL.md").write_text(
            "---\nname: shared\ndescription: d\n---\nFROM_STANDALONE"
        )
        manifest_dir = marketplace_dir / ".plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "collision",
                    "owner": {"name": "Test Team"},
                    "plugins": [{"name": "p", "source": "./plugins/p"}],
                    "skills": [{"name": "shared", "source": "./skills/shared"}],
                }
            )
        )

        # 市场自动加载由 load_public 控制； 该补丁使公共层保持空白，因此只有市场贡献“共
        # 享”。
        #
        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_skills(
                load_public=True,
                load_user=False,
                load_project=False,
                load_org=False,
                registered_marketplaces=[
                    MarketplaceRegistration(
                        name="collision", source=str(marketplace_dir), auto_load=True
                    )
                ],
            )

        shared = [s for s in result.skills if s.name == "shared"]
        assert len(shared) == 1
        assert "FROM_PLUGIN" in shared[0].content
        assert "FROM_STANDALONE" not in shared[0].content

    def test_load_registered_marketplace_skills_uses_registration_fetch_fields(
        self, tmp_path: Path
    ):
        """市场源、参考和 repo_path 驱动器注册表获取。"""
        marketplace_dir = _create_test_marketplace(tmp_path / "marketplace")

        with patch(
            "openhands.sdk.marketplace.registry.fetch_plugin_with_resolution",
            return_value=(marketplace_dir, "abc123"),
        ) as mock_fetch:
            skills = load_registered_marketplace_skills(
                [
                    MarketplaceRegistration(
                        name="custom",
                        source="github:example/marketplaces",
                        ref="feature-branch",
                        repo_path="catalogs/public",
                        auto_load=True,
                    )
                ]
            )

        assert {skill.name for skill in skills} == {"auto-skill", "manual-skill"}
        mock_fetch.assert_called_once_with(
            source="github:example/marketplaces",
            ref="feature-branch",
            repo_path="catalogs/public",
        )

    def test_load_all_skills_returns_skill_load_result(self):
        """测试 load_all_skills 返回 SkillLoadResult。"""
        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_skills(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert isinstance(result, SkillLoadResult)
            assert isinstance(result.skills, list)
            assert isinstance(result.sources, dict)

    def test_load_all_skills_sources_tracking(self):
        """测试源计数是否正确跟踪。"""
        skill1 = Skill(name="public1", content="c1", trigger=None)
        skill2 = Skill(name="user1", content="c2", trigger=None)

        # 第一次调用返回 sdk_base (public+user)，第二次返回项目
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"public1": skill1, "user1": skill2},  # sdk_base
                {},  # 项目
            ],
        ):
            result = load_all_skills(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert result.sources["sdk_base"] == 2
            assert result.sources["sandbox"] == 0
            assert result.sources["org"] == 0
            assert result.sources["project"] == 0
            assert result.sources["registered_marketplaces"] == 0

    def test_load_all_skills_passes_marketplace_path_to_sdk_base(self):
        """测试marketplace_path转发到SDK公共技能加载。"""
        with patch(self._PATCH_TARGET, side_effect=[{}, {}]) as mock_avail:
            load_all_skills(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
                marketplace_path="marketplaces/custom.json",
            )

        sdk_base_call = mock_avail.call_args_list[0]
        assert sdk_base_call.kwargs["include_public"] is True
        assert sdk_base_call.kwargs["marketplace_path"] == "marketplaces/custom.json"

        project_call = mock_avail.call_args_list[1]
        assert project_call.kwargs["include_public"] is False

    def test_load_all_skills_disabled_sources(self):
        """测试禁用的源是否未加载。"""
        with patch(self._PATCH_TARGET, return_value={}) as mock_avail:
            result = load_all_skills(
                load_public=False,
                load_user=False,
                load_project=False,
                load_org=False,
            )

            # 调用两次（sdk_base + 项目），均带有禁用标志
            assert mock_avail.call_count == 2
            assert result.sources["sdk_base"] == 0
            assert result.sources["project"] == 0

    def test_load_all_skills_with_sandbox_urls(self):
        """使用沙盒测试加载技能 URLs。"""
        sandbox_urls = [
            ExposedUrlData(name="WORKER_8080", url="http://localhost:8080", port=8080),
        ]

        with patch(self._PATCH_TARGET, return_value={}):
            result = load_all_skills(
                load_public=False,
                load_user=False,
                load_project=False,
                load_org=False,
                sandbox_exposed_urls=sandbox_urls,
            )

            assert result.sources["sandbox"] == 1
            assert len(result.skills) == 1
            assert result.skills[0].name == "work_hosts"

    def test_load_all_skills_handles_exceptions(self):
        """测试技能加载器的异常是否得到妥善处理。"""
        user_skill = Skill(name="user1", content="content", trigger=None)

        # load_available_skills 在内部处理异常并返回任何它能返回的内容。 模拟：第一次调
        # 用仅返回用户技能（公共内部失败），第二次调用返回空项目。
        #
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"user1": user_skill},  # sdk_base（内部处理公共错误）
                {},  # 项目
            ],
        ):
            result = load_all_skills(
                load_public=True,
                load_user=True,
                load_project=False,
                load_org=False,
            )

            assert result.sources["sdk_base"] == 1

    def test_load_all_skills_merge_precedence(self):
        """测试技能是否以正确的优先顺序合并。"""
        base_skill = Skill(name="shared", content="user", trigger=None)
        project_skill = Skill(name="shared", content="project", trigger=None)

        # sdk_base返回用户版本，项目返回项目版本
        with patch(
            self._PATCH_TARGET,
            side_effect=[
                {"shared": base_skill},  # sdk_base
                {"shared": project_skill},  # 项目
            ],
        ):
            result = load_all_skills(
                load_public=True,
                load_user=True,
                load_project=True,
                load_org=False,
                project_dir="/workspace",
            )

            # 项目应覆盖用户/公共
            shared_skills = [s for s in result.skills if s.name == "shared"]
            assert len(shared_skills) == 1
            assert shared_skills[0].content == "project"

    def test_load_all_skills_loops_and_merges_multiple_org_repos(self):
        """每个组织存储库都会加载（按顺序）并合并到组织源中。"""
        with patch(self._PATCH_TARGET, return_value={}):
            with patch(
                "openhands.agent_server.skills_service.load_org_skills_from_url",
                side_effect=[
                    [Skill(name="org_a", content="a", trigger=None)],
                    [Skill(name="org_b", content="b", trigger=None)],
                ],
            ) as mock_org:
                result = load_all_skills(
                    load_public=False,
                    load_user=False,
                    load_project=False,
                    load_org=True,
                    org_repos=[
                        ("https://git/hieptl/.openhands", "hieptl"),
                        ("https://git/hieptl/.agents", "hieptl"),
                    ],
                )

        assert result.sources["org"] == 2
        assert [c.kwargs["org_repo_url"] for c in mock_org.call_args_list] == [
            "https://git/hieptl/.openhands",
            "https://git/hieptl/.agents",
        ]

    def test_load_all_skills_org_merge_precedence(self):
        """多个组织存储库中的技能解析为较晚的存储库版本。"""
        with patch(self._PATCH_TARGET, return_value={}):
            with patch(
                "openhands.agent_server.skills_service.load_org_skills_from_url",
                side_effect=[
                    [Skill(name="shared", content="openhands", trigger=None)],
                    [Skill(name="shared", content="agents", trigger=None)],
                ],
            ):
                result = load_all_skills(
                    load_public=False,
                    load_user=False,
                    load_project=False,
                    load_org=True,
                    org_repos=[
                        ("https://git/hieptl/.openhands", "hieptl"),
                        ("https://git/hieptl/.agents", "hieptl"),
                    ],
                )

        shared = [s for s in result.skills if s.name == "shared"]
        assert len(shared) == 1
        assert shared[0].content == "agents"


class TestDiscoverProfileSkills:
    """测试 discover_profile_skills（OpenHands 配置文件启动目录）。"""

    _LOAD_ALL = "openhands.agent_server.skills_service.load_all_skills"

    def test_returns_merged_user_and_public_skills(self):
        skills = [Skill(name="a", content="x"), Skill(name="b", content="y")]
        with patch(self._LOAD_ALL) as mock_load:
            mock_load.return_value = SkillLoadResult(skills=skills, sources={})
            result = discover_profile_skills()

        assert result == skills
        # 仅发现确定性的、无额外上下文的来源。
        assert mock_load.call_args.kwargs == {
            "load_public": True,
            "load_user": True,
            "load_org": False,
            "load_project": False,
        }

    def test_propagates_unexpected_failure(self):
        # load_all_skills 在内部吸收良性的每源故障； 意外的失败会传播，而不是默默地解决
        # 为零技能智能体（调用者大声地表达它）。
        #
        with patch(self._LOAD_ALL, side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                discover_profile_skills()


class TestDiscoverPublicSkillNames:
    _LOAD = "openhands.agent_server.skills_service.load_available_skills"

    def test_a_user_skill_shadowing_a_public_one_is_not_public(self):
        def load(*, include_public=False, include_user=False):
            names = (["alpha", "shared"] if include_public else []) + (
                ["shared", "mine"] if include_user else []
            )
            return {name: Skill(name=name, content="x") for name in names}

        with patch(self._LOAD, side_effect=load):
            assert discover_public_skill_names() == {"alpha"}


class TestSyncPublicSkills:
    """测试 sync_public_skills 功能。"""

    def test_sync_public_skills_success(self):
        """测试成功的技能同步。"""
        with (
            patch(
                "openhands.agent_server.skills_service.get_skills_cache_dir"
            ) as mock_cache,
            patch(
                "openhands.agent_server.skills_service.update_skills_repository"
            ) as mock_update,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = Path("/tmp/cache/public-skills")

            success, message = sync_public_skills()

            assert success is True
            assert "success" in message.lower()

    def test_sync_public_skills_failure(self):
        """测试失败的技能同步。"""
        with (
            patch(
                "openhands.agent_server.skills_service.get_skills_cache_dir"
            ) as mock_cache,
            patch(
                "openhands.agent_server.skills_service.update_skills_repository"
            ) as mock_update,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = None

            success, message = sync_public_skills()

            assert success is False
            assert "failed" in message.lower()

    def test_sync_public_skills_exception(self):
        """测试技能同步有异常。"""
        with patch(
            "openhands.agent_server.skills_service.get_skills_cache_dir"
        ) as mock_cache:
            mock_cache.side_effect = Exception("Permission denied")

            success, message = sync_public_skills()

            assert success is False
            assert "failed" in message.lower() or "error" in message.lower()

    def test_sync_public_skills_invalidates_in_memory_cache(self):
        """成功的同步必须删除内存中的缓存，以便下次调用
        立即重新解析，而不是等待 TTL。"""
        with (
            patch(
                "openhands.agent_server.skills_service.get_skills_cache_dir"
            ) as mock_cache,
            patch(
                "openhands.agent_server.skills_service.update_skills_repository"
            ) as mock_update,
            patch(
                "openhands.agent_server.skills_service._invalidate_public_skills_cache"
            ) as mock_invalidate,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = Path("/tmp/cache/public-skills")

            success, _ = sync_public_skills()

            assert success is True
            mock_invalidate.assert_called_once()

    def test_sync_public_skills_failure_does_not_invalidate_cache(self):
        """失败的同步不得破坏缓存，因此之前的技能
        保持可用，直到下一次成功刷新。"""
        with (
            patch(
                "openhands.agent_server.skills_service.get_skills_cache_dir"
            ) as mock_cache,
            patch(
                "openhands.agent_server.skills_service.update_skills_repository"
            ) as mock_update,
            patch(
                "openhands.agent_server.skills_service._invalidate_public_skills_cache"
            ) as mock_invalidate,
        ):
            mock_cache.return_value = Path("/tmp/cache")
            mock_update.return_value = None

            success, _ = sync_public_skills()

            assert success is False
            mock_invalidate.assert_not_called()

    def test_sync_public_skills_reports_unreachable_origin(self, tmp_path):
        """获取失败的同步必须报告失败，而不是过时的克隆。"""
        import subprocess

        def git(*args: str, cwd: Path) -> None:
            subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

        origin = tmp_path / "origin"
        origin.mkdir()
        git("init", "-q", "-b", "main", cwd=origin)
        (origin / "README.md").write_text("skills\n")
        git("add", "README.md", cwd=origin)
        git(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-qm",
            "init",
            cwd=origin,
        )
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        with (
            patch(
                "openhands.agent_server.skills_service.get_skills_cache_dir",
                return_value=cache_dir,
            ),
            patch(
                "openhands.agent_server.skills_service.PUBLIC_SKILLS_REPO",
                str(origin),
            ),
            patch("openhands.agent_server.skills_service.PUBLIC_SKILLS_REF", "main"),
        ):
            assert sync_public_skills()[0] is True
            clone = cache_dir / "public-skills"

            # 一旦克隆存在，原点就变得不可访问。
            origin.rename(tmp_path / "moved")
            success, message = sync_public_skills()

        assert success is False
        assert "failed" in message.lower()
        # 过时的克隆仍然可用于离线技能加载。
        assert (clone / "README.md").read_text() == "skills\n"


class TestSkillLoadResult:
    """测试 SkillLoadResult 数据类。"""

    def test_skill_load_result_creation(self):
        """测试创建 SkillLoadResult 实例。"""
        skills = [Skill(name="test", content="content", trigger=None)]
        sources = {"public": 1, "user": 0}

        result = SkillLoadResult(skills=skills, sources=sources)

        assert result.skills == skills
        assert result.sources == sources

    def test_skill_load_result_empty(self):
        """测试创建空SkillLoadResult。"""
        result = SkillLoadResult(skills=[], sources={})

        assert result.skills == []
        assert result.sources == {}


class TestMarketplaceCatalogCache:
    """测试 service_get_marketplace_catalog 中的 TTL 缓存。"""

    def setup_method(self):
        """每次测试前重置模块级缓存。"""
        import openhands.agent_server.skills_service as svc

        svc._catalog_cache = None

    def test_cache_miss_calls_fetch(self):
        """第一次调用（冷缓存）从存储库中获取。"""
        entries = [("github", "GitHub skill", "github:org/repo")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
        ):
            from openhands.agent_server.skills_service import (
                service_get_marketplace_catalog,
            )

            result = service_get_marketplace_catalog()

        mock_fetch.assert_called_once()
        assert len(result) == 1
        assert result[0].name == "github"
        assert result[0].installed is False

    def test_cache_hit_skips_fetch(self):
        """TTL 内的第二次调用重用缓存的条目，无需再次提取。"""
        entries = [("github", "GitHub skill", "github:org/repo")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
        ):
            from openhands.agent_server.skills_service import (
                service_get_marketplace_catalog,
            )

            service_get_marketplace_catalog()
            service_get_marketplace_catalog()

        mock_fetch.assert_called_once()  # 尽管有两次调用，但只有一次获取

    def test_installed_status_always_fresh(self):
        """已安装标志在每次调用时都会重新派生，而不是从缓存中派生。"""
        from unittest.mock import MagicMock

        from openhands.agent_server.skills_service import (
            InstalledSkillInfo,
            service_get_marketplace_catalog,
        )

        entries = [("github", "GitHub skill", "github:org/repo")]
        installed_skill = MagicMock(spec=InstalledSkillInfo)
        installed_skill.name = "github"

        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                return_value=entries,
            ),
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
            ) as mock_installed,
        ):
            # 第一次调用：技能未安装
            mock_installed.return_value = []
            result1 = service_get_marketplace_catalog()
            assert result1[0].installed is False

            # 第二次调用（缓存命中）：技能现已安装
            mock_installed.return_value = [installed_skill]
            result2 = service_get_marketplace_catalog()
            assert result2[0].installed is True

        # service_list_installed_skills 调用两次（每个请求一次）
        assert mock_installed.call_count == 2

    def test_cache_expires_after_ttl(self):
        """TTL 过期后，下一次调用将再次从存储库中获取。"""
        import openhands.agent_server.skills_service as svc

        entries = [("github", "GitHub skill", "github:org/repo")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
        ):
            from openhands.agent_server.skills_service import (
                service_get_marketplace_catalog,
            )

            service_get_marketplace_catalog()
            # 人为地使缓存过期
            assert svc._catalog_cache is not None
            svc._catalog_cache = (
                svc._catalog_cache[0] - svc._CATALOG_TTL_SECONDS - 1,
                entries,
            )
            service_get_marketplace_catalog()

        assert mock_fetch.call_count == 2  # 过期后再次获取

    def test_empty_result_is_not_cached(self):
        """失败或空的提取将在下次调用时重试，而不是
        清空整个目录 TTL。"""
        import openhands.agent_server.skills_service as svc

        entries = [("github", "GitHub skill", "github:org/repo")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                side_effect=[[], entries],
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
        ):
            assert svc.service_get_marketplace_catalog() == []
            assert svc._catalog_cache is None
            result = svc.service_get_marketplace_catalog()

        assert mock_fetch.call_count == 2
        assert [s.name for s in result] == ["github"]

    def test_sync_clears_catalog_cache(self):
        """成功的同步使下一个目录读取拾取新条目。"""
        import openhands.agent_server.skills_service as svc

        before = [("github", "GitHub skill", "github:org/repo")]
        after = [*before, ("jira", "Jira skill", "github:org/repo/jira")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                side_effect=[before, after],
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
            patch("openhands.agent_server.skills_service.get_skills_cache_dir"),
            patch(
                "openhands.agent_server.skills_service.update_skills_repository",
                return_value=Path("/tmp/cache/public-skills"),
            ),
        ):
            assert len(svc.service_get_marketplace_catalog()) == 1
            success, _ = svc.sync_public_skills()
            result = svc.service_get_marketplace_catalog()

        assert success is True
        assert mock_fetch.call_count == 2
        assert [s.name for s in result] == ["github", "jira"]

    def test_failed_sync_keeps_catalog_cache(self):
        """失败的同步会将缓存的目录保留在原处。"""
        import openhands.agent_server.skills_service as svc

        entries = [("github", "GitHub skill", "github:org/repo")]
        with (
            patch(
                "openhands.agent_server.skills_service._fetch_catalog_entries",
                return_value=entries,
            ) as mock_fetch,
            patch(
                "openhands.agent_server.skills_service.service_list_installed_skills",
                return_value=[],
            ),
            patch("openhands.agent_server.skills_service.get_skills_cache_dir"),
            patch(
                "openhands.agent_server.skills_service.update_skills_repository",
                return_value=None,
            ),
        ):
            svc.service_get_marketplace_catalog()
            success, _ = svc.sync_public_skills()
            svc.service_get_marketplace_catalog()

        assert success is False
        mock_fetch.assert_called_once()
