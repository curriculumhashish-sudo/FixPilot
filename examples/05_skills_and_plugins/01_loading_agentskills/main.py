"""Example: 从磁盘加载技能（AgentSkills标准）

此示例演示如何按照 AgentSkills 标准加载技能
from a directory on disk.

技能是模块化的、独立的包，通过提供专业知识、工作流程和工具来扩展智能体的功能。 它们遵
循 AgentSkills 标准，其中包括：
- SKILL.md 个文件，包含前置元数据个元数据（名称、描述、触发器）
- 可选资源目录：scripts/、references/、assets/

example_skills/目录包含两个技能：
- rot13-加密：具有触发器（加密、解密）- 在 <available_skills> AND 中列出，触发时自动
注入内容
- 代码风格指南：无触发器 - 在 <available_skills> 中列出用于按需访问

所有 SKILL.md 文件都遵循 AgentSkills 渐进式披露模型：它们在 <available_skills> 中列出
，并包含名称、描述和位置。 带触发器的技能可
以两全其美：触发时自动注入内容，而且智能体可以随时主动读取它们。
"""

import os
import sys
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk import LLM, Agent, AgentContext, Conversation
from openhands.sdk.skills import (
    discover_skill_resources,
    load_skills_from_dir,
)
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool


# 获取包含该脚本的目录
script_dir = Path(__file__).parent
example_skills_dir = script_dir / "example_skills"

# =========================================================================
# 第 1 部分：从目录加载技能
# =========================================================================
print("=" * 80)
print("Part 1: Loading Skills from a Directory")
print("=" * 80)

print(f"Loading skills from: {example_skills_dir}")

# 发现技能目录中的资源
skill_subdir = example_skills_dir / "rot13-encryption"
resources = discover_skill_resources(skill_subdir)
print("\nDiscovered resources in rot13-encryption/:")
print(f"  - scripts: {resources.scripts}")
print(f"  - references: {resources.references}")
print(f"  - assets: {resources.assets}")

# 从目录加载技能
repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(example_skills_dir)

print("\nLoaded skills from directory:")
print(f"  - Repo skills: {list(repo_skills.keys())}")
print(f"  - Knowledge skills: {list(knowledge_skills.keys())}")
print(f"  - Agent skills (SKILL.md): {list(agent_skills.keys())}")

# 访问加载的技能并显示所有 AgentSkills 个标准字段
if agent_skills:
    skill_name = next(iter(agent_skills))
    loaded_skill = agent_skills[skill_name]
    print(f"\nDetails for '{skill_name}' (AgentSkills standard fields):")
    print(f"  - Name: {loaded_skill.name}")
    desc = loaded_skill.description or ""
    print(f"  - Description: {desc[:70]}...")
    print(f"  - License: {loaded_skill.license}")
    print(f"  - Compatibility: {loaded_skill.compatibility}")
    print(f"  - Metadata: {loaded_skill.metadata}")
    if loaded_skill.resources:
        print("  - Resources:")
        print(f"    - Scripts: {loaded_skill.resources.scripts}")
        print(f"    - References: {loaded_skill.resources.references}")
        print(f"    - Assets: {loaded_skill.resources.assets}")
        print(f"    - Skill root: {loaded_skill.resources.skill_root}")

# =========================================================================
# 第 2 部分：使用智能体的技能
# =========================================================================
print("\n" + "=" * 80)
print("Part 2: Using Skills with an Agent")
print("=" * 80)

# 检查API键
api_key = os.getenv("LLM_API_KEY")
if not api_key:
    print("Skipping agent demo (LLM_API_KEY not set)")
    print("\nTo run the full demo, set the LLM_API_KEY environment variable:")
    print("  export LLM_API_KEY=your-api-key")
    sys.exit(0)

# 配置LLM
model = os.getenv("LLM_MODEL", "gpt-5.5")
llm = LLM(
    usage_id="skills-demo",
    model=model,
    api_key=SecretStr(api_key),
    base_url=os.getenv("LLM_BASE_URL"),
)

# 使用已加载的技能创建智能体上下文
agent_context = AgentContext(
    skills=list(agent_skills.values()),
    # 禁用此演示的公共技能以保持输出重点
    load_public_skills=False,
)

# 使用工具创建智能体，以便它可以读取技能资源
tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
]
agent = Agent(llm=llm, tools=tools, agent_context=agent_context)

# 创建对话
conversation = Conversation(agent=agent, workspace=os.getcwd())

# 测试技能（由“加密”关键字触发） 该技能提供 ROT13 加密的说明和脚本
#
print("\nSending message with 'encrypt' keyword to trigger skill...")
conversation.send_message("Encrypt the message 'hello world'.")
conversation.run()

print(f"\nTotal cost: ${llm.metrics.accumulated_cost:.4f}")
print(f"EXAMPLE_COST: {llm.metrics.accumulated_cost:.4f}")
