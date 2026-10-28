"""使用基于 git 的缓存测试 load_public_skills 功能。"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.skills import (
    KeywordTrigger,
    Skill,
    load_public_skills,
)
from openhands.sdk.skills.skill import (
    _invalidate_public_skills_cache,
    load_marketplace_skill_names,
)
from openhands.sdk.skills.utils import update_skills_repository


@pytest.fixture(autouse=True)
def _clear_public_skills_cache():
    """在测试之间清除内存中的公共技能缓存。

    缓存是进程全局的，因此如果不清除它，一次测试泄漏到后续测试的结果会有所不同模拟对
    象 ``update_skills_repository``。
    """
    _invalidate_public_skills_cache()
    yield
    _invalidate_public_skills_cache()


@pytest.fixture
def mock_repo_dir(tmp_path):
    """使用技能创建模拟对象 git 存储库。"""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # 创建技能目录
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 创建技能文件
    git_skill = skills_dir / "git.md"
    git_skill.write_text(
        "---\n"
        "name: git\n"
        "triggers:\n"
        "  - git\n"
        "  - github\n"
        "---\n"
        "Git best practices and commands."
    )

    docker_skill = skills_dir / "docker.md"
    docker_skill.write_text(
        "---\n"
        "name: docker\n"
        "triggers:\n"
        "  - docker\n"
        "  - container\n"
        "---\n"
        "Docker guidelines and commands."
    )

    testing_skill = skills_dir / "testing.md"
    testing_skill.write_text(
        "---\nname: testing\n---\nTesting guidelines for all repos."
    )

    # 创建 .git 目录来模拟 git 存储库
    git_dir = repo_dir / ".git"
    git_dir.mkdir()

    return repo_dir


@pytest.fixture
def mock_repo_with_agentskills_references(tmp_path):
    """使用参考 Markdown 文件创建具有 AgentSkills 风格技能的模拟对象存储库。

    这重现了 Markdown 文件在 SKILL.md 目录（如 themes/ 或 references/）下的子目录中被
    错误加载为独立技能的问题。
    See: https://github.com/OpenHands/software-agent-sdk/issues/1981
    """
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # 创建技能目录
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 使用 theme/ 中的 SKILL.md 和参考 Markdown 文件创建主题工厂技能
    theme_factory_dir = skills_dir / "theme-factory"
    theme_factory_dir.mkdir()

    # 主SKILL.md文件
    skill_md = theme_factory_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: theme-factory\n"
        "description: Toolkit for styling artifacts with a theme.\n"
        "---\n"
        "# Theme Factory Skill\n\n"
        "This skill provides a curated collection of professional themes.\n"
    )

    # 使用参考 Markdown 文件创建主题子目录
    themes_dir = theme_factory_dir / "themes"
    themes_dir.mkdir()

    # 这些是参考文件，不单独的技能
    (themes_dir / "arctic-frost.md").write_text(
        "# Arctic Frost\n\nA cool and crisp winter-inspired theme.\n"
    )
    (themes_dir / "ocean-depths.md").write_text(
        "# Ocean Depths\n\nA professional and calming maritime theme.\n"
    )
    (themes_dir / "sunset-boulevard.md").write_text(
        "# Sunset Boulevard\n\nWarm and vibrant sunset colors.\n"
    )

    # 使用引用/子目录创建准备报告技能
    readiness_dir = skills_dir / "readiness-report"
    readiness_dir.mkdir()

    (readiness_dir / "SKILL.md").write_text(
        "---\n"
        "name: readiness-report\n"
        "description: Generate readiness reports.\n"
        "---\n"
        "# Readiness Report Skill\n"
    )

    # 使用参考 Markdown 文件创建参考子目录
    refs_dir = readiness_dir / "references"
    refs_dir.mkdir()

    (refs_dir / "criteria.md").write_text("# Criteria\n\nEvaluation criteria.\n")
    (refs_dir / "maturity-levels.md").write_text(
        "# Maturity Levels\n\nMaturity level definitions.\n"
    )

    # 创建常规遗留技能（不是 AgentSkills 格式）
    legacy_skill = skills_dir / "legacy-skill.md"
    legacy_skill.write_text(
        "---\nname: legacy-skill\ntriggers:\n  - legacy\n---\nA legacy format skill.\n"
    )

    # 创建 .git 目录来模拟 git 存储库
    git_dir = repo_dir / ".git"
    git_dir.mkdir()

    return repo_dir


def _create_skills_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgSign", "false"], cwd=repo, check=True)
    (repo / "version.txt").write_text("v1")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=repo, check=True)
    return repo


def test_load_public_skills_success(mock_repo_dir, tmp_path):
    """测试从缓存存储库成功加载技能。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()
        assert len(skills) == 3
        skill_names = {s.name for s in skills}
        assert skill_names == {"git", "docker", "testing"}

        # 检查 git 技能详细信息
        git_skill = next(s for s in skills if s.name == "git")
        assert isinstance(git_skill.trigger, KeywordTrigger)
        assert "git" in git_skill.trigger.keywords

        # 检查测试技能（无触发器 - 始终处于活动状态）
        testing_skill = next(s for s in skills if s.name == "testing")
        assert testing_skill.trigger is None


def test_load_public_skills_repo_update_fails(tmp_path):
    """测试存储库更新失败时的处理。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return None

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()
        assert skills == []


def test_load_public_skills_no_skills_directory(tmp_path):
    """测试存储库中不存在技能目录时的处理。"""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    # 未创建技能目录

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()
        assert skills == []


def test_load_public_skills_with_invalid_skill(tmp_path):
    """测试无效技能是否被优雅地跳过。"""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 有效技能
    valid_skill = skills_dir / "valid.md"
    valid_skill.write_text("---\nname: valid\n---\nValid skill content.")

    # 技能无效
    invalid_skill = skills_dir / "invalid.md"
    invalid_skill.write_text(
        "---\nname: invalid\ntriggers: not_a_list\n---\nInvalid skill."
    )

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()
        # 只加载有效技能，无效技能则跳过
        assert len(skills) == 1
        assert skills[0].name == "valid"


def test_update_skills_repository_clone_new(tmp_path):
    source = _create_skills_git_repo(tmp_path)
    cache_dir = tmp_path / "cache"

    repo_path = update_skills_repository(f"file://{source}", "main", cache_dir)

    assert repo_path is not None
    assert repo_path == cache_dir / "public-skills"
    assert (repo_path / "version.txt").read_text() == "v1"


def test_update_skills_repository_update_existing(tmp_path):
    source = _create_skills_git_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    repo_path = update_skills_repository(f"file://{source}", "main", cache_dir)
    assert repo_path is not None
    (source / "version.txt").write_text("v2")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=source, check=True)

    result_path = update_skills_repository(f"file://{source}", "main", cache_dir)

    assert result_path is not None
    assert result_path == repo_path
    assert (result_path / "version.txt").read_text() == "v2"


def test_update_skills_repository_clone_timeout(tmp_path):
    """在克隆过程中测试超时的处理。"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    with patch(
        "openhands.sdk.git.utils.subprocess.run",
        side_effect=subprocess.TimeoutExpired("git", 60),
    ) as mock_run:
        repo_path = update_skills_repository(
            "https://github.com/OpenHands/extensions",
            "main",
            cache_dir,
        )

        assert repo_path is None
        mock_run.assert_called_once()


def test_update_skills_repository_update_fails_uses_cache(tmp_path):
    source = _create_skills_git_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    source_url = f"file://{source}"
    repo_path = update_skills_repository(source_url, "main", cache_dir)
    source.rename(tmp_path / "offline-source")

    result_path = update_skills_repository(source_url, "main", cache_dir)

    assert result_path == repo_path
    assert repo_path is not None
    assert (repo_path / "version.txt").read_text() == "v1"
    assert update_skills_repository(source_url, "main", cache_dir, strict=True) is None


def test_agent_context_loads_public_skills(mock_repo_dir, tmp_path):
    """测试 AgentContext 在启用时是否加载公共技能。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(load_public_skills=True)
        skill_names = {s.name for s in context.skills}
        assert "git" in skill_names
        assert "docker" in skill_names
        assert "testing" in skill_names


def test_agent_context_uses_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """测试 AgentContext 转发 marketplace_path 到公共技能加载。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(
            load_public_skills=True,
            marketplace_path="marketplaces/custom.json",
        )

    skill_names = {s.name for s in context.skills}
    assert skill_names == {"git", "internal-only"}


def test_agent_context_can_disable_public_skills_loading():
    """测试公共技能加载是否可以禁用。"""
    context = AgentContext(load_public_skills=False)
    assert context.skills == []


def test_agent_context_merges_explicit_and_public_skills(mock_repo_dir, tmp_path):
    """测试显性技能和公共技能是否正确合并。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    # 创造显性技能
    explicit_skill = Skill(
        name="explicit_skill",
        content="Explicit skill content.",
        trigger=None,
    )

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(skills=[explicit_skill], load_public_skills=True)
        skill_names = {s.name for s in context.skills}
        assert "explicit_skill" in skill_names
        assert "git" in skill_names
        assert len(context.skills) == 4  # 1 个显式 + 3 个公共


def test_agent_context_explicit_skill_takes_precedence(mock_repo_dir, tmp_path):
    """测试明确提供的技能优先于公共技能。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_dir

    # 创建与公共技能同名的显式技能
    explicit_skill = Skill(
        name="git",
        content="Explicit git skill content.",
        trigger=None,
    )

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        context = AgentContext(skills=[explicit_skill], load_public_skills=True)
        # 应具备 3 项技能（1 项显式 git + 2 项其他公共技能）
        assert len(context.skills) == 3
        git_skill = next(s for s in context.skills if s.name == "git")
        # 应使用显性技能，而不是公共技能
        assert git_skill.content == "Explicit git skill content."


def test_load_public_skills_custom_repo(mock_repo_dir, tmp_path):
    """测试从自定义存储库加载URL。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        assert repo_url == "https://github.com/custom-org/custom-skills"
        return mock_repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills(
            repo_url="https://github.com/custom-org/custom-skills"
        )
        assert len(skills) == 3


def test_load_public_skills_custom_branch(mock_repo_dir, tmp_path):
    """测试从特定分支加载。"""

    def mock_update_repo(repo_url, ref, cache_dir):
        assert ref == "develop"
        return mock_repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills(ref="develop")
        assert len(skills) == 3


def test_load_public_skills_excludes_reference_markdown_in_agentskills_folders(
    mock_repo_with_agentskills_references, tmp_path
):
    """测试 SKILL.md 子目录中的 Markdown 个文件是否已作为技能加载不。

    这是针对问题 #1981 的回归测试：
    https://github.com/OpenHands/software-agent-sdk/issues/1981

    技能目录中包含的 SKILL.md 文件 (AgentSkills format), any Markdown 子目录中的文件
    （如 themes/、 referen
    ces/等）应被视为该技能的参考材料不作为独立的技能。

    预期行为：
    - theme-factory/SKILL.md -> 加载为“theme-factory”技能
    - theme-factory/themes/*.md -> 不已加载（参考文件）
    - readiness-report/SKILL.md -> 加载为“readiness-report”技能
    - readiness-report/references/*.md -> 不已加载（参考文件）
    - legacy-skill.md -> 加载为“遗留技能”技能
    """

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_agentskills_references

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()

        # 获取所有技能名称
        skill_names = {s.name for s in skills}

        # 应该正好具备 3 项技能：主题工厂、就绪报告、遗留技能
        assert len(skills) == 3, (
            f"Expected 3 skills but got {len(skills)}. "
            f"Skill names: {skill_names}. "
            "Reference markdown files in themes/ or references/ subdirectories "
            "should NOT be loaded as separate skills."
        )

        # 验证已加载正确的技能
        assert "theme-factory" in skill_names
        assert "readiness-report" in skill_names
        assert "legacy-skill" in skill_names

        # 验证参考文件是否已作为技能加载不这些文件将加载诸如“theme-factory/themes/arctic
        # -frost”之类的名称
        #
        for skill in skills:
            assert "arctic-frost" not in skill.name, (
                f"Reference arctic-frost.md loaded as skill: {skill.name}"
            )
            assert "ocean-depths" not in skill.name, (
                f"Reference ocean-depths.md loaded as skill: {skill.name}"
            )
            assert "sunset-boulevard" not in skill.name, (
                f"Reference sunset-boulevard.md loaded as skill: {skill.name}"
            )
            assert "criteria" not in skill.name, (
                f"Reference criteria.md loaded as skill: {skill.name}"
            )
            assert "maturity-levels" not in skill.name, (
                f"Reference maturity-levels.md loaded as skill: {skill.name}"
            )


# 基于市场的技能过滤测试


@pytest.fixture
def mock_repo_with_marketplace(tmp_path):
    """使用市场文件和技能创建模拟对象 git 存储库。"""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    # 创建技能目录
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 创建市场目录
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()

    # 创造多种技能（有些在市场中，有些不在市场中） 技能 1：git（在市场中）
    #
    git_dir = skills_dir / "git"
    git_dir.mkdir()
    (git_dir / "SKILL.md").write_text(
        "---\nname: git\ndescription: Git best practices\n---\nGit skill content."
    )

    # 技能2：Docker（在市场中）
    docker_dir = skills_dir / "docker"
    docker_dir.mkdir()
    (docker_dir / "SKILL.md").write_text(
        "---\nname: docker\ndescription: Docker guidelines\n---\nDocker skill content."
    )

    # 技能 3：仅限内部（市场中的不）
    internal_dir = skills_dir / "internal-only"
    internal_dir.mkdir()
    (internal_dir / "SKILL.md").write_text(
        "---\nname: internal-only\ndescription: Internal skill\n---\nInternal content."
    )

    # 技能 4：实验（市场中的不）
    experimental_dir = skills_dir / "experimental"
    experimental_dir.mkdir()
    (experimental_dir / "SKILL.md").write_text(
        "---\nname: experimental\ndescription: Experimental\n---\nExperimental content."
    )

    # 仅使用 git 和 Docker 创建默认市场
    marketplace = {
        "name": "default",
        "owner": {"name": "OpenHands", "email": "test@test.com"},
        "metadata": {"description": "Test marketplace", "version": "1.0.0"},
        "plugins": [
            {"name": "git", "source": "./git", "description": "Git skill"},
            {"name": "docker", "source": "./docker", "description": "Docker skill"},
        ],
    }
    (marketplaces_dir / "default.json").write_text(json.dumps(marketplace))

    custom_marketplace = {
        "name": "custom",
        "owner": {"name": "OpenHands", "email": "test@test.com"},
        "metadata": {"description": "Custom test marketplace", "version": "1.0.0"},
        "plugins": [
            {"name": "git", "source": "./git", "description": "Git skill"},
            {
                "name": "internal-only",
                "source": "./internal-only",
                "description": "Internal skill",
            },
        ],
    }
    (marketplaces_dir / "custom.json").write_text(json.dumps(custom_marketplace))

    # 创建 .git 目录来模拟 git 存储库
    (repo_dir / ".git").mkdir()

    return repo_dir


def test_load_marketplace_skill_names_returns_skill_names(mock_repo_with_marketplace):
    """测试 load_marketplace_skill_names 是否正确提取技能名称。"""
    skill_names = load_marketplace_skill_names(
        mock_repo_with_marketplace, "marketplaces/default.json"
    )

    assert skill_names is not None
    assert skill_names == {"git", "docker"}


def test_load_marketplace_skill_names_returns_none_when_file_missing(tmp_path):
    """测试当文件不存在时 load_marketplace_skill_names 返回 None。"""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    result = load_marketplace_skill_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_marketplace_skill_names_returns_none_for_invalid_json(tmp_path):
    """测试 load_marketplace_skill_names 是否优雅地处理无效的 JSON。"""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    (marketplaces_dir / "default.json").write_text("{ invalid json }")

    result = load_marketplace_skill_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_marketplace_skill_names_returns_none_for_missing_plugins(tmp_path):
    """测试 load_marketplace_skill_names 是否处理缺失的插件密钥。"""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    (marketplaces_dir / "default.json").write_text(json.dumps({"name": "test"}))

    result = load_marketplace_skill_names(repo_dir, "marketplaces/default.json")
    assert result is None


def test_load_public_skills_filters_by_marketplace(
    mock_repo_with_marketplace, tmp_path
):
    """测试 load_public_skills 仅加载市场中列出的技能。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()

    skill_names = {skill.name for skill in skills}
    assert skill_names == {"git", "docker"}
    assert "internal-only" not in skill_names
    assert "experimental" not in skill_names


def test_load_public_skills_uses_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """测试自定义 marketplace_path 选择不同的技能集。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills(marketplace_path="marketplaces/custom.json")

    assert {skill.name for skill in skills} == {"git", "internal-only"}


def test_load_public_skills_returns_empty_for_invalid_custom_marketplace_path(
    mock_repo_with_marketplace, tmp_path
):
    """测试无效的自定义 marketplace_path 不会扩大技能负载。"""

    def mock_update_repo(repo_url, branch, cache_dir):
        return mock_repo_with_marketplace

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills(marketplace_path="marketplaces/missing.json")

    assert skills == []


def test_load_public_skills_loads_all_when_no_marketplace(tmp_path):
    """测试 load_public_skills 在不存在市场时加载所有技能。"""
    # 在没有市场的情况下创建存储库
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 创造技能
    for name in ["git", "docker", "internal-only"]:
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n{name} content."
        )

    (repo_dir / ".git").mkdir()

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()

        # 应该具备所有技能，因为不存在市场
        skill_names = {s.name for s in skills}
        assert skill_names == {"git", "docker", "internal-only"}


def test_load_public_skills_handles_legacy_md_files_with_marketplace(tmp_path):
    """测试市场过滤适用于旧版 .md 技能文件。"""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    skills_dir = repo_dir / "skills"
    skills_dir.mkdir()

    # 创建遗留 .md 技能
    (skills_dir / "git.md").write_text(
        "---\nname: git\ntriggers:\n  - git\n---\nGit skill."
    )
    (skills_dir / "docker.md").write_text(
        "---\nname: docker\ntriggers:\n  - docker\n---\nDocker skill."
    )
    (skills_dir / "internal.md").write_text(
        "---\nname: internal\ntriggers:\n  - internal\n---\nInternal skill."
    )

    # 创建包含 git 和 Docker 但不包含内部的市场
    marketplaces_dir = repo_dir / "marketplaces"
    marketplaces_dir.mkdir()
    marketplace = {
        "name": "default",
        "owner": {"name": "Test Team"},
        "plugins": [
            {"name": "git", "source": "./git.md"},
            {"name": "docker", "source": "./docker.md"},
        ],
    }
    (marketplaces_dir / "default.json").write_text(json.dumps(marketplace))

    (repo_dir / ".git").mkdir()

    def mock_update_repo(repo_url, branch, cache_dir):
        return repo_dir

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            side_effect=mock_update_repo,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        skills = load_public_skills()

        # 应该只有 git 和来自市场的 Docker
        skill_names = {s.name for s in skills}
        assert skill_names == {"git", "docker"}
        assert "internal" not in skill_names


def test_load_public_skills_caches_result_within_ttl(mock_repo_dir, tmp_path):
    """TTL 窗口内的第二次调用不得重新运行 update_skills_repository。

    回归测试慢对话创建路径：AgentContext 在每次请求中被重新验证了几次，导致
    load_public_skills 每次都执行 git fetch + 解析。
    """
    update_mock = MagicMock(return_value=mock_repo_dir)
    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            update_mock,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        first = load_public_skills()
        second = load_public_skills()

    assert update_mock.call_count == 1
    assert {s.name for s in first} == {s.name for s in second}


def test_invalidate_public_skills_cache_forces_recompute(mock_repo_dir, tmp_path):
    """显式失效后，下一次调用将重新运行 update_skills_repository。"""
    update_mock = MagicMock(return_value=mock_repo_dir)
    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            update_mock,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        load_public_skills()
        _invalidate_public_skills_cache()
        load_public_skills()

    assert update_mock.call_count == 2


def test_load_public_skills_does_not_cache_empty_results(mock_repo_dir, tmp_path):
    """瞬态故障不得毒害整个缓存 TTL。

    第一次调用模拟 git/repo 失败（没有返回技能）； 第二次调用成功，应该再次命中真实路
    径而不是空缓存。
    """
    update_mock = MagicMock(side_effect=[None, mock_repo_dir])
    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            update_mock,
        ),
        patch(
            "openhands.sdk.skills.skill.get_skills_cache_dir",
            return_value=tmp_path,
        ),
    ):
        first = load_public_skills()
        second = load_public_skills()

    assert first == []
    assert {s.name for s in second} == {"git", "docker", "testing"}
    assert update_mock.call_count == 2


def test_load_public_skills_reads_extensions_path_without_cloning(
    mock_repo_dir, monkeypatch
):
    monkeypatch.setenv("EXTENSIONS_PATH", str(mock_repo_dir))

    with patch("openhands.sdk.skills.skill.update_skills_repository") as update:
        skills = load_public_skills()

    update.assert_not_called()
    assert {s.name for s in skills} == {"git", "docker", "testing"}


def test_extensions_path_does_not_replace_a_custom_repository(
    mock_repo_dir, tmp_path, monkeypatch
):
    monkeypatch.setenv("EXTENSIONS_PATH", str(tmp_path / "unused"))

    with (
        patch(
            "openhands.sdk.skills.skill.update_skills_repository",
            return_value=mock_repo_dir,
        ) as update,
        patch("openhands.sdk.skills.skill.get_skills_cache_dir", return_value=tmp_path),
    ):
        skills = load_public_skills(repo_url="https://example.com/skills.git")

    update.assert_called_once()
    assert {s.name for s in skills} == {"git", "docker", "testing"}
