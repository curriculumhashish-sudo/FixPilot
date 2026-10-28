"""Example: 具有本地和远程技能的混合市场

此示例演示了如何创建一个包含以下内容的市场：
1. 托管在您的项目目录中的本地技能
2. 来自 GitHub 的远程技能（OpenHands/扩展存储库）

marketplace.json 模式支持以下格式的源路径：
- 本地路径：./path、../path、/absolute/path、~/path、文件：///path
- GitHub URLs:  https://github.com/{owner}/{repo}/blob/{branch}/{path}

此模式对于想要实现以下目标的团队非常有用：
- 在本地维护自己的定制技能
- 参考远程存储库中的特定技能
- 为他们的特定工作流程创建精心策划的技能集

目录结构：
    04_mixed_marketplace_skills/ ├── .plugin/ │ └── marketplace.json # 包含本地和远程
    技能的市场 ├─
    ─ Skills/ │ └──greeting-helper/ │ └── SKILL.md # 本地技能内容 ├── main.py # 这个
    文件 └──
    README.md # 文档

用途：
    # 将市场中的所有技能安装到 ~/.openhands/skills/installed/
    python main.py --install

    # 强制重新安装（覆盖现有）
    python main.py --install --force

    # 显示已安装的技能
    python main.py --list
"""

import sys
from pathlib import Path

from openhands.sdk.marketplace import Marketplace
from openhands.sdk.skills import (
    install_skills_from_marketplace,
    list_installed_skills,
)


def main():
    script_dir = Path(__file__).parent

    if "--list" in sys.argv:
        # 列出已安装的技能
        print("=" * 80)
        print("Installed Skills")
        print("=" * 80)
        installed = list_installed_skills()
        if not installed:
            print("\nNo skills installed.")
            print("Run with --install to install skills from the marketplace.")
        else:
            for info in installed:
                desc = (info.description or "No description")[:60]
                print(f"\n  {info.name}")
                print(f"    Description: {desc}...")
                print(f"    Source: {info.source}")
        return

    if "--install" in sys.argv:
        # 从市场安装技能
        print("=" * 80)
        print("Installing Skills from Marketplace")
        print("=" * 80)
        print(f"\nMarketplace directory: {script_dir}")

        force = "--force" in sys.argv
        installed = install_skills_from_marketplace(script_dir, force=force)

        print(f"\n\nInstalled {len(installed)} skills:")
        for info in installed:
            print(f"  - {info.name}")

        # 显示所有已安装的技能
        print("\n" + "=" * 80)
        print("All Installed Skills")
        print("=" * 80)
        all_installed = list_installed_skills()
        for info in all_installed:
            desc = (info.description or "No description")[:50]
            print(f"  - {info.name}: {desc}...")
        return

    # 默认：显示市场信息
    print("=" * 80)
    print("Marketplace Information")
    print("=" * 80)
    print(f"\nMarketplace directory: {script_dir}")

    marketplace = Marketplace.load(script_dir)
    print(f"Name: {marketplace.name}")
    print(f"Description: {marketplace.description}")
    print(f"Skills defined: {len(marketplace.skills)}")

    print("\nSkills:")
    for entry in marketplace.skills:
        source_type = "remote" if entry.source.startswith("http") else "local"
        print(f"  - {entry.name} ({source_type})")
        print(f"    Source: {entry.source}")
        if entry.description:
            print(f"    Description: {entry.description}")

    print("\n" + "-" * 80)
    print("Usage:")
    print("  python main.py --install        # Install all skills")
    print("  python main.py --install --force # Force reinstall")
    print("  python main.py --list           # List installed skills")


if __name__ == "__main__":
    main()
    print("EXAMPLE_COST: 0")
