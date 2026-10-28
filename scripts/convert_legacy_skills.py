#!/usr/bin/env python3
"""将旧 OpenHands 技能转换为 AgentSkills 标准格式。

此脚本将单个 .md 技能文件转换为 AgentSkills 目录格式：
- 使用 SKILL.md 创建技能名称/目录
- 将 mcp_tools 前置元数据转换为 .mcp.json 文件
- 保留 OpenHands 特定字段（触发器、输入）以实现兼容性

用途：
    # 转换单个技能文件
    python convert_legacy_skills.py skill.md --output-dir ./converted/

    # 转换目录中的所有技能
    python convert_legacy_skills.py ./skills/ --output-dir ./converted/

    # 试运行（显示将转换的内容）
    python convert_legacy_skills.py ./skills/ --output-dir ./converted/ --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import frontmatter


# AgentSkills 名称验证图案
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def normalize_skill_name(name: str) -> str:
    """标准化技能名称以符合 AgentSkills 规范。

    转换为小写，用连字符替换下划线，并删除无效字符。
    """
    normalized = name.lower()
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized


def validate_skill_name(name: str) -> list[str]:
    """根据 AgentSkills 规范验证技能名称。"""
    errors = []
    if not name:
        errors.append("Name cannot be empty")
        return errors
    if len(name) > 64:
        errors.append(f"Name exceeds 64 characters: {len(name)}")
    if not SKILL_NAME_PATTERN.match(name):
        errors.append(
            "Name must be lowercase alphanumeric with single hyphens "
            "(e.g., 'my-skill', 'pdf-tools')"
        )
    return errors


def generate_description(
    content: str,
    triggers: list[str] | None = None,
    name: str | None = None,
) -> str:
    """从内容或触发器生成技能的描述。"""
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        return stripped[:1024]

    if triggers:
        trigger_str = ", ".join(triggers[:5])
        if len(triggers) > 5:
            trigger_str += f" (+{len(triggers) - 5} more)"
        return f"Activated by: {trigger_str}"[:1024]

    if name:
        return f"Skill: {name}"[:1024]

    return "A skill for OpenHands agent."


def convert_legacy_skill(
    source_path: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """将旧的 OpenHands 技能转换为 AgentSkills 格式。"""
    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}", file=sys.stderr)
        return None

    if source_path.name == "README.md":
        return None

    with open(source_path) as f:
        file_content = f.read()

    file_io = io.StringIO(file_content)
    loaded = frontmatter.load(file_io)
    content = loaded.content
    metadata = dict(loaded.metadata) if loaded.metadata else {}

    original_name = metadata.get("name", source_path.stem)
    skill_name = normalize_skill_name(str(original_name))

    name_errors = validate_skill_name(skill_name)
    if name_errors:
        print(
            f"Warning: Skill name '{original_name}' -> '{skill_name}' "
            f"has issues: {'; '.join(name_errors)}",
            file=sys.stderr,
        )
        skill_name = normalize_skill_name(source_path.stem)
        if validate_skill_name(skill_name):
            print(
                f"Error: Cannot normalize skill name for {source_path}",
                file=sys.stderr,
            )
            return None

    skill_dir = output_dir / skill_name
    skill_md_path = skill_dir / "SKILL.md"
    mcp_json_path = skill_dir / ".mcp.json"

    print(f"Converting: {source_path} -> {skill_dir}/")

    if dry_run:
        return skill_dir

    skill_dir.mkdir(parents=True, exist_ok=True)

    new_metadata: dict[str, Any] = {}
    new_metadata["name"] = skill_name

    triggers_raw = metadata.get("triggers", [])
    triggers: list[str] = triggers_raw if isinstance(triggers_raw, list) else []
    description = metadata.get("description") or generate_description(
        content, triggers, skill_name
    )
    new_metadata["description"] = description

    if "license" in metadata:
        new_metadata["license"] = metadata["license"]
    if "compatibility" in metadata:
        new_metadata["compatibility"] = metadata["compatibility"]

    extra_metadata: dict[str, str] = {}
    if "version" in metadata:
        extra_metadata["version"] = str(metadata["version"])
    if "author" in metadata:
        extra_metadata["author"] = str(metadata["author"])
    if "agent" in metadata:
        extra_metadata["agent"] = str(metadata["agent"])
    if "type" in metadata:
        extra_metadata["type"] = str(metadata["type"])

    if "metadata" in metadata and isinstance(metadata["metadata"], dict):
        for k, v in metadata["metadata"].items():
            extra_metadata[str(k)] = str(v)

    if extra_metadata:
        new_metadata["metadata"] = extra_metadata

    if triggers:
        new_metadata["triggers"] = triggers
    if "inputs" in metadata:
        new_metadata["inputs"] = metadata["inputs"]
    if "allowed-tools" in metadata:
        new_metadata["allowed-tools"] = metadata["allowed-tools"]
    if "allowed_tools" in metadata:
        new_metadata["allowed-tools"] = metadata["allowed_tools"]

    mcp_tools = metadata.get("mcp_tools")

    new_post = frontmatter.Post(content, **new_metadata)
    with open(skill_md_path, "w") as f:
        f.write(frontmatter.dumps(new_post))

    if mcp_tools and isinstance(mcp_tools, dict):
        with open(mcp_json_path, "w") as f:
            json.dump(mcp_tools, f, indent=2)
            f.write("\n")

    return skill_dir


def convert_skills_directory(
    source_dir: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    """将目录中的所有旧技能转换为 AgentSkills 格式。"""
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        return []

    converted: list[Path] = []

    md_files = [
        f
        for f in source_dir.glob("*.md")
        if f.name != "README.md" and f.name.lower() != "skill.md"
    ]

    print(f"Found {len(md_files)} skill files to convert")

    for md_file in sorted(md_files):
        result = convert_legacy_skill(md_file, output_dir, dry_run=dry_run)
        if result:
            converted.append(result)

    print(f"Converted {len(converted)} skills")
    return converted


def main():
    parser = argparse.ArgumentParser(
        description="Convert legacy OpenHands skills to AgentSkills standard format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source skill file (.md) or directory containing skill files",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Output directory for converted skills",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be converted without writing files",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove output directory before converting",
    )

    args = parser.parse_args()

    if args.clean and args.output_dir.exists() and not args.dry_run:
        print(f"Cleaning output directory: {args.output_dir}")
        shutil.rmtree(args.output_dir)

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.source.is_file():
        result = convert_legacy_skill(
            args.source, args.output_dir, dry_run=args.dry_run
        )
        if result:
            print(f"\nSuccess: Created {result}")
        else:
            sys.exit(1)
    elif args.source.is_dir():
        results = convert_skills_directory(
            args.source, args.output_dir, dry_run=args.dry_run
        )
        if not results:
            print("No skills were converted", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Source not found: {args.source}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
