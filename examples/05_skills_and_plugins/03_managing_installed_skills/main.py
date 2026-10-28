"""Example: 安装和管理技能

此示例演示了 SDK 中已安装的技能生命周期操作：

1. 将技能从本地路径安装到持久存储中
2. 列出跟踪的技能并仅加载启用的技能
3. 检查 `.installed.json` 元数据文件和 `enabled` 标志
4. 禁用并重新启用技能，无需重新安装
5. 卸载技能，同时保留其他已安装的技能可用

有关市场安装流程，请参阅：
`examples/05_skills_and_plugins/04_mixed_marketplace_skills/`.
"""

import json
import tempfile
from pathlib import Path

from openhands.sdk.skills import (
    disable_skill,
    enable_skill,
    install_skill,
    list_installed_skills,
    load_installed_skills,
    uninstall_skill,
)


script_dir = Path(__file__).resolve().parent
example_skills_dir = script_dir.parent / "01_loading_agentskills" / "example_skills"


def print_state(label: str, installed_dir: Path) -> None:
    """打印跟踪、加载和已持久化技能状态。"""
    print(f"\n{label}")
    print("-" * len(label))

    installed = list_installed_skills(installed_dir=installed_dir)
    print("Tracked skills:")
    for info in installed:
        print(f"  - {info.name} (enabled={info.enabled}, source={info.source})")

    loaded = load_installed_skills(installed_dir=installed_dir)
    print(f"Loaded skills: {[skill.name for skill in loaded]}")

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    print("Metadata file:")
    print(json.dumps(metadata, indent=2))


def demo_install_skills(installed_dir: Path) -> list[str]:
    """将示例技能安装到隔离的安装目录中。"""
    print("\n" + "=" * 60)
    print("DEMO 1: Installing local skills")
    print("=" * 60)

    installed_names: list[str] = []
    for skill_dir in sorted(example_skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        info = install_skill(source=str(skill_dir), installed_dir=installed_dir)
        installed_names.append(info.name)
        print(f"✓ Installed: {info.name}")
        print(f"  Source: {info.source}")
        print(f"  Path: {info.install_path}")

    return installed_names


def demo_list_and_load_skills(installed_dir: Path) -> None:
    """列出跟踪的技能并将其加载为运行时技能对象。"""
    print("\n" + "=" * 60)
    print("DEMO 2: Listing and loading installed skills")
    print("=" * 60)

    installed = list_installed_skills(installed_dir=installed_dir)
    print("Tracked skills:")
    for info in installed:
        desc = (info.description or "No description")[:60]
        print(f"  - {info.name} (enabled={info.enabled})")
        print(f"    Description: {desc}...")

    loaded = load_installed_skills(installed_dir=installed_dir)
    print(f"\nLoaded {len(loaded)} skill(s):")
    for skill in loaded:
        desc = (skill.description or "No description")[:60]
        print(f"  - {skill.name}: {desc}...")


def demo_enable_disable_skill(installed_dir: Path, skill_name: str) -> None:
    """禁用然后重新启用技能并显示已持久化元数据。"""
    print("\n" + "=" * 60)
    print("DEMO 3: Disabling and re-enabling a skill")
    print("=" * 60)

    print_state("Before disable", installed_dir)

    assert disable_skill(skill_name, installed_dir=installed_dir) is True
    print_state("After disable", installed_dir)
    assert skill_name not in [
        skill.name for skill in load_installed_skills(installed_dir=installed_dir)
    ]

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert metadata["skills"][skill_name]["enabled"] is False

    assert enable_skill(skill_name, installed_dir=installed_dir) is True
    print_state("After re-enable", installed_dir)

    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert metadata["skills"][skill_name]["enabled"] is True
    assert skill_name in [
        skill.name for skill in load_installed_skills(installed_dir=installed_dir)
    ]


def demo_uninstall_skill(
    installed_dir: Path, skill_name: str, remaining_skill_name: str
) -> None:
    """卸载一项技能并确认另一项技能仍然可用。"""
    print("\n" + "=" * 60)
    print("DEMO 4: Uninstalling a skill")
    print("=" * 60)

    assert uninstall_skill(skill_name, installed_dir=installed_dir) is True
    print_state("After uninstall", installed_dir)

    assert not (installed_dir / skill_name).exists()
    metadata = json.loads((installed_dir / ".installed.json").read_text())
    assert skill_name not in metadata["skills"]
    assert remaining_skill_name in metadata["skills"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmpdir:
        installed_dir = Path(tmpdir) / "installed-skills"
        installed_dir.mkdir(parents=True)

        installed_names = demo_install_skills(installed_dir)
        demo_list_and_load_skills(installed_dir)
        demo_enable_disable_skill(installed_dir, skill_name="rot13-encryption")
        demo_uninstall_skill(
            installed_dir,
            skill_name="rot13-encryption",
            remaining_skill_name="code-style-guide",
        )

        remaining_names = [
            info.name for info in list_installed_skills(installed_dir=installed_dir)
        ]
        assert remaining_names == ["code-style-guide"]
        assert sorted(installed_names) == ["code-style-guide", "rot13-encryption"]

    print("\nEXAMPLE_COST: 0")
