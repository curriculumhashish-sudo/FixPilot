"""集成测试 for Plugin.fetch() 与真正的 git 操作。

这些测试执行实际的 git 操作，并且可能需要网络访问。 它们旨在测试插件获取的完整端到端
流程。
"""

import subprocess
from pathlib import Path

from openhands.sdk.git.cached_repo import GitHelper
from openhands.sdk.plugin import Plugin
from openhands.sdk.plugin.fetch import fetch_plugin


class TestGitHelperIntegration:
    """集成测试 for GitHelper 具有真正的 git 操作。"""

    def test_clone_real_repo(self, tmp_path: Path):
        """测试克隆真实存储库。"""
        git = GitHelper()
        dest = tmp_path / "repo"

        # 创建一个本地裸存储库以从中克隆
        bare_repo = tmp_path / "bare.git"
        subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True)

        git.clone(f"file://{bare_repo}", dest)

        assert dest.exists()
        assert (dest / ".git").exists()

    def test_clone_with_branch(self, tmp_path: Path):
        """使用特定分支测试克隆。"""
        git = GitHelper()

        # 创建带有分支的源存储库
        source = tmp_path / "source"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=source, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
        (source / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=source, check=True)
        subprocess.run(["git", "branch", "feature"], cwd=source, check=True)

        dest = tmp_path / "dest"
        git.clone(f"file://{source}", dest, branch="feature")

        assert dest.exists()
        # 验证我们在功能分支上
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=dest,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "feature"

    def test_fetch_and_checkout(self, tmp_path: Path):
        """测试获取和结帐操作。"""
        git = GitHelper()

        # 创建源存储库
        source = tmp_path / "source"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=source, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
        (source / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=source, check=True)
        subprocess.run(["git", "tag", "v1.0.0"], cwd=source, check=True)

        # 克隆它
        dest = tmp_path / "dest"
        git.clone(f"file://{source}", dest, depth=None)

        # 在源中进行更改
        (source / "file.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=source, check=True)

        # 获取并验证
        git.fetch(dest)

        # 结帐标签
        git.checkout(dest, "v1.0.0")
        assert (dest / "file.txt").read_text() == "v1"

    def test_get_current_branch(self, tmp_path: Path):
        """测试获取当前分支名称。"""
        git = GitHelper()

        # 创建仓库
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True)

        # 默认分支
        branch = git.get_current_branch(repo)
        assert branch in ("main", "master")

        # 创建并切换到新分支
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=repo, check=True)
        branch = git.get_current_branch(repo)
        assert branch == "develop"

    def test_get_current_branch_detached_head(self, tmp_path: Path):
        """测试分离的 HEAD 返回 None。"""
        git = GitHelper()

        # 使用提交创建存储库
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        (repo / "file.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=repo, check=True)
        (repo / "file.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=repo, check=True)

        # 获取第一次提交的提交哈希
        result = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        first_commit = result.stdout.strip()

        # 分离 HEAD
        subprocess.run(["git", "checkout", first_commit], cwd=repo, check=True)

        branch = git.get_current_branch(repo)
        assert branch is None


class TestFetchPluginIntegration:
    """集成测试 for fetch_plugin 具有真正的 git 操作。"""

    def test_fetch_from_local_git_repo(self, tmp_path: Path):
        """测试从本地 git 存储库获取插件。"""
        # 创建插件仓库
        plugin_repo = tmp_path / "my-plugin"
        plugin_repo.mkdir()
        subprocess.run(["git", "init"], cwd=plugin_repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=plugin_repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=plugin_repo, check=True
        )

        # 添加插件文件
        (plugin_repo / ".plugin").mkdir()
        (plugin_repo / ".plugin" / "plugin.json").write_text(
            '{"name": "test-plugin", "version": "1.0.0", "description": "Test"}'
        )
        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=plugin_repo, check=True)

        # 拿来
        cache_dir = tmp_path / "cache"
        result = fetch_plugin(f"file://{plugin_repo}", cache_dir=cache_dir)

        assert result.exists()
        assert (result / ".plugin" / "plugin.json").exists()

    def test_fetch_caches_and_updates(self, tmp_path: Path):
        """测试获取缓存和更新是否正常工作。"""
        # 创建插件存储库
        plugin_repo = tmp_path / "plugin"
        plugin_repo.mkdir()
        subprocess.run(["git", "init"], cwd=plugin_repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=plugin_repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=plugin_repo, check=True
        )
        (plugin_repo / "version.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=plugin_repo, check=True)

        cache_dir = tmp_path / "cache"

        # 第一次获取
        result1 = fetch_plugin(f"file://{plugin_repo}", cache_dir=cache_dir)
        assert (result1 / "version.txt").read_text() == "v1"

        # 更新源
        (plugin_repo / "version.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=plugin_repo, check=True)

        # 使用 update=True 获取
        result2 = fetch_plugin(
            f"file://{plugin_repo}", cache_dir=cache_dir, update=True
        )
        assert result1 == result2  # 相同的缓存路径
        assert (result2 / "version.txt").read_text() == "v2"

    def test_fetch_with_ref(self, tmp_path: Path):
        """测试获取特定引用。"""
        # 使用标签创建插件存储库
        plugin_repo = tmp_path / "plugin"
        plugin_repo.mkdir()
        subprocess.run(["git", "init"], cwd=plugin_repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=plugin_repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=plugin_repo, check=True
        )

        # v1
        (plugin_repo / "version.txt").write_text("v1")
        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=plugin_repo, check=True)
        subprocess.run(["git", "tag", "v1.0.0"], cwd=plugin_repo, check=True)

        # v2
        (plugin_repo / "version.txt").write_text("v2")
        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=plugin_repo, check=True)

        cache_dir = tmp_path / "cache"

        # 获取 v1.0.0
        result = fetch_plugin(
            f"file://{plugin_repo}", cache_dir=cache_dir, ref="v1.0.0"
        )
        assert (result / "version.txt").read_text() == "v1"


class TestPluginFetchMethodIntegration:
    """集成测试用于 Plugin.fetch() 类方法。"""

    def test_fetch_and_load_plugin(self, tmp_path: Path):
        """测试完整的获取和加载工作流程。"""
        # 创建一个完整的插件
        plugin_repo = tmp_path / "complete-plugin"
        plugin_repo.mkdir()
        subprocess.run(["git", "init"], cwd=plugin_repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=plugin_repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=plugin_repo, check=True
        )

        # 创建插件结构
        (plugin_repo / ".plugin").mkdir()
        (plugin_repo / ".plugin" / "plugin.json").write_text(
            """{
            "name": "complete-plugin",
            "version": "1.0.0",
            "description": "A complete test plugin"
        }"""
        )

        subprocess.run(["git", "add", "."], cwd=plugin_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=plugin_repo, check=True)

        # 获取并加载
        cache_dir = tmp_path / "cache"
        plugin_path = Plugin.fetch(f"file://{plugin_repo}", cache_dir=cache_dir)
        plugin = Plugin.load(plugin_path)

        assert plugin.name == "complete-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "A complete test plugin"
