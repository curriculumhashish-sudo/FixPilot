"""测试本地+已安装的插件发现。

覆盖 ``openhands.sdk.plugin.discovery`` — 用户/项目目录中的 *环境*插件集，以及启用的
已安装插件。 反映用户/项目技能发现测试。
"""

import json
from pathlib import Path

import pytest

from openhands.sdk.plugin import (
    disable_plugin,
    discovery,
    install_plugin,
    installed,
    load_available_plugins,
    load_project_plugins,
    load_user_plugins,
)


def _make_plugin(plugin_dir: Path, name: str, skill_name: str, content: str) -> Path:
    """创建一个包含单个技能的最小插件目录。"""
    manifest_dir = plugin_dir / ".plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "description": f"Plugin {name}"})
    )
    skills_dir = plugin_dir / "skills"
    skills_dir.mkdir(exist_ok=True)
    (skills_dir / f"{skill_name}.md").write_text(
        f"---\nname: {skill_name}\n---\n{content}"
    )
    return plugin_dir


@pytest.fixture
def installed_dir(tmp_path: Path) -> Path:
    """一个空的已安装插件商店。"""
    store = tmp_path / "installed-store"
    store.mkdir()
    return store


def test_load_user_plugins_discovers_directory_plugin(
    tmp_path: Path, installed_dir: Path, monkeypatch
):
    # 安排
    user_dir = tmp_path / ".agents" / "plugins"
    _make_plugin(user_dir / "weather", "weather", "weather-skill", "Weather content.")
    monkeypatch.setattr(discovery, "USER_PLUGINS_DIRS", [user_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_PLUGINS_DIR", installed_dir)

    # 法案
    plugins = load_user_plugins()

    # 断言
    assert [p.name for p in plugins] == ["weather"]


def test_load_user_plugins_filters_installed_by_enabled_flag(
    tmp_path: Path, installed_dir: Path, monkeypatch
):
    # 安排：安装两个插件，然后禁用一个。
    enabled_src = _make_plugin(tmp_path / "src-on", "enabled-plugin", "s1", "c1")
    disabled_src = _make_plugin(tmp_path / "src-off", "disabled-plugin", "s2", "c2")
    install_plugin(str(enabled_src), installed_dir=installed_dir)
    install_plugin(str(disabled_src), installed_dir=installed_dir)
    disable_plugin("disabled-plugin", installed_dir=installed_dir)
    monkeypatch.setattr(discovery, "USER_PLUGINS_DIRS", [tmp_path / "empty"])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_PLUGINS_DIR", installed_dir)

    # 法案
    names = {p.name for p in load_user_plugins()}

    # 断言
    assert "enabled-plugin" in names
    assert "disabled-plugin" not in names


def test_load_user_plugins_does_not_load_installed_store_as_plugin(
    tmp_path: Path, monkeypatch
):
    # 排列：用户插件目录包含一个真正的插件 AND 安装存储为
    # 名为“installed”的子目录。
    openhands_plugins = tmp_path / ".openhands" / "plugins"
    _make_plugin(openhands_plugins / "real-plugin", "real-plugin", "rs", "Real.")
    install_store = openhands_plugins / "installed"
    install_store.mkdir(parents=True)
    monkeypatch.setattr(discovery, "USER_PLUGINS_DIRS", [openhands_plugins])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_PLUGINS_DIR", install_store)

    # 法案
    names = {p.name for p in load_user_plugins()}

    # 断言：真正的插件加载； 安装存储没有被错误加载为
    # 名为“installed”的虚假插件。
    assert "real-plugin" in names
    assert "installed" not in names


def test_load_project_plugins_discovers_workspace_plugin(tmp_path: Path):
    # 安排
    work_dir = tmp_path / "workspace"
    _make_plugin(
        work_dir / ".agents" / "plugins" / "proj", "proj-plugin", "ps", "Project."
    )

    # 法案
    plugins = load_project_plugins(work_dir)

    # 断言
    assert "proj-plugin" in {p.name for p in plugins}


def test_load_available_plugins_project_overrides_user(
    tmp_path: Path, installed_dir: Path, monkeypatch
):
    # 排列：用户目录和项目目录中的插件名称相同
    # 提供独特的技能。
    user_dir = tmp_path / ".agents" / "plugins"
    _make_plugin(user_dir / "shared", "shared", "user-skill", "User.")
    work_dir = tmp_path / "workspace"
    _make_plugin(
        work_dir / ".agents" / "plugins" / "shared", "shared", "project-skill", "Proj."
    )
    monkeypatch.setattr(discovery, "USER_PLUGINS_DIRS", [user_dir])
    monkeypatch.setattr(installed, "DEFAULT_INSTALLED_PLUGINS_DIR", installed_dir)

    # 法案
    available = load_available_plugins(
        work_dir=work_dir, include_user=True, include_project=True
    )

    # 断言：项目赢得名称冲突。
    assert set(available) == {"shared"}
    skill_names = {s.name for s in available["shared"].skills}
    assert "project-skill" in skill_names
    assert "user-skill" not in skill_names
