"""技能系统测试。"""

import tempfile
from pathlib import Path

import pytest

from openhands.sdk.context import (
    KeywordTrigger,
    Skill,
    SkillValidationError,
    TaskTrigger,
    load_project_skills,
    load_skills_from_dir,
)
from openhands.sdk.skills.utils import (
    find_regular_md_files,
    find_skill_md,
    find_skill_md_directories,
    find_third_party_files,
)
from openhands.sdk.utils.path import to_posix_path
from tests.platform_utils import require_case_sensitive_fs, symlink_or_skip


CONTENT = "# dummy header\ndummy content\n## dummy subheader\ndummy subcontent\n"


def test_legacy_micro_agent_load(tmp_path):
    """测试遗留技能的加载。"""
    legacy_file = tmp_path / ".openhands_instructions"
    legacy_file.write_text(CONTENT)

    # 通过 skill_dir（本例中为 tmp_path）进行加载
    skill = Skill.load(legacy_file, tmp_path)
    assert skill.trigger is None
    assert skill.name == ".openhands_instructions"  # 从文件名派生的名称
    # frontmatter.load() 去除尾随换行符
    assert skill.content == CONTENT.rstrip("\n")


@pytest.fixture
def temp_skills_dir():
    """创建一个带有测试技能的临时目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建测试知识智能体（从触发器推断的类型）
        knowledge_agent = """---
# type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers:
  - test
  - pytest
---

# Test Guidelines

Testing best practices and guidelines.
"""
        (root / "knowledge.md").write_text(knowledge_agent)

        # 创建测试存储库智能体（由于缺乏触发器而推断出的类型）
        repo_agent = """---
# type: repo
version: 1.0.0
agent: CodeActAgent
---

# Test Repository Agent

Repository-specific test instructions.
"""
        (root / "repo.md").write_text(repo_agent)

        yield root


def test_knowledge_agent():
    """测试知识智能体功能。"""
    # 使用关键字触发器创建知识智能体
    agent = Skill(
        name="test",
        content="Test content",
        source="test.md",
        trigger=KeywordTrigger(keywords=["testing", "pytest"]),
    )

    assert agent.match_trigger("running a testing") == "testing"
    assert agent.match_trigger("using pytest") == "pytest"
    assert agent.match_trigger("no match here") is None
    assert isinstance(agent.trigger, KeywordTrigger)
    assert agent.trigger.keywords == ["testing", "pytest"]


def _skill_with_keywords(*keywords: str, task: bool = False) -> Skill:
    """构建一个技能，该技能的 (Keyword|Task) 触发器在给定的关键词上触发。"""
    trigger = (
        TaskTrigger(triggers=list(keywords))
        if task
        else KeywordTrigger(keywords=list(keywords))
    )
    return Skill(name="s", content="c", source="s.md", trigger=trigger)


# (关键字、消息、预期) 其中预期是匹配的关键字或 None。 回归 #3643 的覆盖范围：子字符串匹
# 配在 ``github`` 上触发 ``git``，在 ``tissue`` 上触发 ``issue``。 在alnum 边界上匹配必
# 须是整体token。
#
_MATCH_CASES = [
    # --- 整合匹配防火 ---
    pytest.param("git", "run git status", "git", id="word-in-middle"),
    pytest.param("git", "git", "git", id="whole-message"),
    pytest.param("git", "git status", "git", id="word-at-start"),
    pytest.param("git", "use git", "git", id="word-at-end"),
    pytest.param("git", "run git status twice, git", "git", id="repeated"),
    # --- 不区分大小写匹配，返回原始关键字 ---
    pytest.param("git", "GIT rocks", "git", id="uppercase-message"),
    pytest.param("git", "use Git today", "git", id="titlecase-message"),
    pytest.param("GIT", "run git status", "GIT", id="uppercase-keyword-preserved"),
    pytest.param("GitHub", "open github now", "GitHub", id="mixedcase-keyword"),
    # ---非alnum边界火灾---
    pytest.param("git", "git!", "git", id="trailing-bang"),
    pytest.param("git", "git.", "git", id="trailing-dot"),
    pytest.param("git", "(git)", "git", id="parenthesized"),
    pytest.param("git", "git:status", "git", id="colon-after"),
    pytest.param("git", "use-git-now", "git", id="hyphen-bounded"),
    pytest.param("git", "my_git_repo", "git", id="underscore-is-a-boundary"),
    pytest.param("git", "line1\ngit\nline2", "git", id="newline-bounded"),
    pytest.param("git", "tab\tgit\tend", "git", id="tab-bounded"),
    # --- 字母数字邻接块（#3643 False 正数）---
    pytest.param("git", "check out github.com", None, id="prefix-of-word"),
    pytest.param("git", "the digit five", None, id="suffix-of-word"),
    pytest.param("git", "a legitimate reason", None, id="inside-word"),
    pytest.param("git", "git2 branch", None, id="trailing-digit"),
    pytest.param("git", "2git branch", None, id="leading-digit"),
    pytest.param("issue", "hand me a tissue", None, id="issue-in-tissue"),
    # --- 没有匹配 ---
    pytest.param("git", "no match here", None, id="absent"),
    pytest.param("git", "", None, id="empty-message"),
    # --- 斜杠前缀关键字（为什么 alnum 边界，而不是 \\b）---
    pytest.param("/linear", "use /linear now", "/linear", id="slash-in-middle"),
    pytest.param("/linear", "/linear", "/linear", id="slash-whole-message"),
    pytest.param("/linear", "please /linear", "/linear", id="slash-at-end"),
    pytest.param("/linear", "run a linearization", None, id="slash-vs-bareword"),
    pytest.param("/linear", "src/linear.py", None, id="slash-after-alnum"),
    # --- 多词短语作为一个单元进行匹配 ---
    pytest.param("pull request", "open a pull request", "pull request", id="phrase"),
    pytest.param("pull request", "pull request!", "pull request", id="phrase-punct"),
    pytest.param("pull request", "pullrequest", None, id="phrase-no-space"),
    pytest.param("pull request", "pull requests", None, id="phrase-plural"),
    # --- re.escape 保留正则表达式元字符的文字 ---
    pytest.param("c++", "write c++ code", "c++", id="metachar-plus"),
    pytest.param("c++", "c++today", None, id="metachar-plus-adjacent"),
    pytest.param("a.b", "call a.b now", "a.b", id="metachar-dot-literal"),
    pytest.param("a.b", "call axb now", None, id="metachar-dot-not-wildcard"),
]


@pytest.mark.parametrize("task", [False, True], ids=["keyword", "task"])
@pytest.mark.parametrize(("keyword", "message", "expected"), _MATCH_CASES)
def test_match_trigger_whole_word(
    keyword: str, message: str, expected: str | None, task: bool
) -> None:
    """对于两种触发器类型，match_trigger 仅在整个 token 上触发。"""
    skill = _skill_with_keywords(keyword, task=task)
    assert skill.match_trigger(message) == expected


def test_match_trigger_returns_first_matching_keyword_in_list_order() -> None:
    """第一个匹配的关键字（按列表顺序）获胜，而不是最早的
    消息中出现的情况。"""
    skill = _skill_with_keywords("alpha", "beta")
    assert skill.match_trigger("beta then alpha") == "alpha"
    assert skill.match_trigger("only beta here") == "beta"


def test_match_trigger_empty_keyword_never_matches() -> None:
    """空的触发关键字不能匹配所有内容。"""
    skill = _skill_with_keywords("")
    assert skill.match_trigger("anything at all") is None
    assert skill.match_trigger("") is None


def test_match_trigger_no_trigger_returns_none() -> None:
    """没有 KeywordTrigger/TaskTrigger 的技能永远不会匹配。"""
    skill = Skill(name="s", content="c", source="s.md", trigger=None)
    assert skill.match_trigger("git issue linear") is None


def test_load_skills(temp_skills_dir):
    """测试从目录加载的技巧。"""
    repo_agents, knowledge_agents, _ = load_skills_from_dir(temp_skills_dir)

    # 检查知识智能体（名称源自文件名：knowledge.md -> '知识'）
    assert len(knowledge_agents) == 1
    agent_k = knowledge_agents["knowledge"]
    assert isinstance(agent_k, Skill)
    assert isinstance(agent_k.trigger, KeywordTrigger)  # 检查推断类型
    assert "test" in agent_k.trigger.keywords

    # 检查存储库智能体（名称源自文件名：repo.md -> 'repo'）
    assert len(repo_agents) == 1
    agent_r = repo_agents["repo"]
    assert agent_r.trigger is None
    assert agent_r.trigger is None  # 检查推断类型


def test_load_skills_with_nested_dirs(temp_skills_dir):
    """测试从嵌套目录加载的技巧。"""
    # 创建嵌套知识智能体
    nested_dir = temp_skills_dir / "nested" / "dir"
    nested_dir.mkdir(parents=True)
    nested_agent = """---
# type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers:
  - nested
---

# Nested Test Guidelines

Testing nested directory loading.
"""
    (nested_dir / "nested.md").write_text(nested_agent)

    repo_agents, knowledge_agents, _ = load_skills_from_dir(temp_skills_dir)

    # 检查我们是否可以找到嵌套的智能体 （名称源自
    # 路径：nested/dir/nested.md -> 'nested/dir/nested')
    assert len(knowledge_agents) == 2  # 原始('知识') + 嵌套('nested/dir/nested')
    agent_n = knowledge_agents["nested/dir/nested"]
    assert isinstance(agent_n, Skill)
    assert isinstance(agent_n.trigger, KeywordTrigger)  # 检查推断类型
    assert "nested" in agent_n.trigger.keywords


def test_load_skills_with_trailing_slashes(temp_skills_dir):
    """测试目录路径尾部有斜杠时的加载技巧。"""
    # 创建一个带有斜杠的目录
    knowledge_dir = temp_skills_dir / "test_knowledge/"
    knowledge_dir.mkdir(exist_ok=True)
    knowledge_agent = """---
# type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers:
  - trailing
---

# Trailing Slash Test

Testing loading with trailing slashes.
"""
    (knowledge_dir / "trailing.md").write_text(knowledge_agent)

    repo_agents, knowledge_agents, _ = load_skills_from_dir(
        str(temp_skills_dir) + "/"  # 添加尾部斜杠进行测试
    )

    # 检查我们是否可以找到智能体，尽管尾部有斜杠（名称源自路径：test_knowledge/
    # trailing.md -> 'test_knowledge/trailing'）
    #
    assert len(knowledge_agents) == 2  # 原始('知识')+尾随('test_knowledge/尾随')
    agent_t = knowledge_agents["test_knowledge/trailing"]
    assert isinstance(agent_t, Skill)
    assert isinstance(agent_t.trigger, KeywordTrigger)  # 检查推断类型
    assert "trailing" in agent_t.trigger.keywords


def test_invalid_skill_type(temp_skills_dir, caplog):
    """测试加载具有无效触发器字段（不是列表）的技能。

    应跳过无效技能并发出警告，而不是引发异常。 这确保了弹性加载——一项糟糕的技能并不会
    破坏所有技能。
    """
    # 创建具有无效触发器的技能（应该是列表，而不是字符串）
    invalid_agent = """---
name: invalid_triggers_agent
version: 1.0.0
agent: CodeActAgent
triggers: not_a_list
---

# Invalid Triggers Test

This skill has invalid triggers format.
"""
    invalid_file = temp_skills_dir / "invalid_triggers.md"
    invalid_file.write_text(invalid_agent)

    # 不应该提高 - 无效技能会被跳过并发出警告
    repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(temp_skills_dir)

    # 无效技能应加载不
    all_skill_names = (
        list(repo_skills.keys())
        + list(knowledge_skills.keys())
        + list(agent_skills.keys())
    )
    assert "invalid_triggers_agent" not in all_skill_names

    # 检查是否记录了警告
    assert any("Triggers must be a list" in record.message for record in caplog.records)


def test_cursorrules_file_load(tmp_path):
    """测试将 .cursorrules 文件加载为 RepoSkill。"""
    cursorrules_content = """Always use Python for new files.
Follow the existing code style.
Add proper error handling."""

    cursorrules_path = tmp_path / ".cursorrules"
    cursorrules_path.write_text(cursorrules_content)

    # 测试直接加载.cursorrules文件
    agent = Skill.load(cursorrules_path)

    # 验证它是否已加载为 RepoSkill
    assert agent.trigger is None
    assert agent.name == "cursorrules"
    assert agent.content == cursorrules_content
    assert agent.trigger is None
    assert agent.source == to_posix_path(cursorrules_path)


def test_skill_version_as_integer(tmp_path):
    """测试加载版本为整数的技能（重现错误）。"""
    # 创建一个技能，其版本为不带引号的整数。这应该被 YAML 解析为整数，但由我们的代码转换
    # 为字符串
    #
    skill_content = """---
name: test_agent
type: knowledge
version: 2512312
agent: CodeActAgent
triggers:
  - test
---

# Test Agent

This is a test agent with integer version.
"""

    test_path = tmp_path / "test_agent.md"
    test_path.write_text(skill_content)

    # 即使版本是 YAML 中的整数，这也不应该引发错误
    agent = Skill.load(test_path)

    # 验证智能体已正确加载
    assert isinstance(agent, Skill)
    assert agent.name == "test_agent"
    # .metadata 在 V1 中为已弃用。 这个测试只是测试我们是向后兼容断言
    # agent.metadata.version == '2512312' # 应该转换为字符串
    #
    assert isinstance(agent.trigger, KeywordTrigger)


def test_skill_version_as_float(tmp_path):
    """测试加载版本为浮动的技能。"""
    # 创建一个技能，其版本为不带引号的浮点数
    skill_content = """---
name: test_agent_float
type: knowledge
version: 1.5
agent: CodeActAgent
triggers:
  - test
---

# Test Agent Float

This is a test agent with float version.
"""

    test_path = tmp_path / "test_agent_float.md"
    test_path.write_text(skill_content)

    # 即使版本是 YAML 中的浮点数，这也不应该引发错误
    agent = Skill.load(test_path)

    # 验证智能体已正确加载
    assert isinstance(agent, Skill)
    assert agent.name == "test_agent_float"
    assert isinstance(agent.trigger, KeywordTrigger)


def test_skill_version_as_string_unchanged(tmp_path):
    """测试加载版本为字符串的技能（应保持不变）。"""
    # 创建一个技能，并将版本作为带引号的字符串
    skill_content = """---
name: test_agent_string
type: knowledge
version: "1.0.0"
agent: CodeActAgent
triggers:
  - test
---

# Test Agent String

This is a test agent with string version.
"""

    test_path = tmp_path / "test_agent_string.md"
    test_path.write_text(skill_content)

    # 这应该可以正常工作
    agent = Skill.load(test_path)

    # 验证智能体已正确加载
    assert isinstance(agent, Skill)
    assert agent.name == "test_agent_string"
    assert isinstance(agent.trigger, KeywordTrigger)


@pytest.fixture
def temp_skills_dir_with_cursorrules():
    """创建一个包含测试技能和 .cursorrules 文件的临时目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建。openhands/skills 目录结构
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # 在存储库根目录中创建 .cursorrules 文件
        cursorrules_content = """Always use TypeScript for new files.
Follow the existing code style."""
        (root / ".cursorrules").write_text(cursorrules_content)

        # 创建测试仓库智能体
        repo_agent = """---
# type: repo
version: 1.0.0
agent: CodeActAgent
---

# Test Repository Agent

Repository-specific test instructions.
"""
        (skills_dir / "repo.md").write_text(repo_agent)

        yield root


def test_load_skills_with_cursorrules(temp_skills_dir_with_cursorrules):
    """测试 .cursorrules 文件存在时的加载技巧。"""
    # 第三方文件由load_project_skills()加载，而不是load_skills_from_dir()
    skills = load_project_skills(temp_skills_dir_with_cursorrules)
    skills_by_name = {s.name: s for s in skills}

    # 验证 .cursorrules 文件是否已作为 RepoSkill 加载
    assert len(skills_by_name) == 2  # repo.md + .cursorrules
    assert "repo" in skills_by_name
    assert "cursorrules" in skills_by_name

    # 检查.cursorrules 智能体
    cursorrules_agent = skills_by_name["cursorrules"]
    assert cursorrules_agent.trigger is None
    assert cursorrules_agent.name == "cursorrules"
    assert "Always use TypeScript for new files" in cursorrules_agent.content
    assert cursorrules_agent.trigger is None


@pytest.fixture
def temp_skills_dir_with_context_files():
    """创建一个包含 CLAUDE.md 和 GEMINI.md 文件的临时目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建。openhands/skills 目录结构
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # 在存储库根目录中创建 claude.md 文件（小写以匹配模式）
        claude_content = """# Claude-Specific Instructions

These are instructions specifically for Claude AI."""
        (root / "claude.md").write_text(claude_content)

        # 在存储库根目录中创建 gemini.md 文件（小写以匹配模式）
        gemini_content = """# Gemini-Specific Instructions

These are instructions specifically for Google Gemini AI."""
        (root / "gemini.md").write_text(gemini_content)

        # 创建测试仓库智能体
        repo_agent = """---
# type: repo
version: 1.0.0
agent: CodeActAgent
---

# Test Repository Agent

Repository-specific test instructions.
"""
        (skills_dir / "repo.md").write_text(repo_agent)

        yield root


def test_load_skills_with_claude_gemini(temp_skills_dir_with_context_files):
    """测试claude.md和gemini.md文件存在时的加载技巧。"""
    # 第三方文件由load_project_skills()加载，而不是load_skills_from_dir()
    skills = load_project_skills(temp_skills_dir_with_context_files)
    skills_by_name = {s.name: s for s in skills}

    # 验证 claude.md 和 gemini.md 文件是否已加载为 RepoSkills
    assert len(skills_by_name) == 3  # repo.md + claude.md + gemini.md
    assert "repo" in skills_by_name
    assert "claude" in skills_by_name
    assert "gemini" in skills_by_name

    # 检查 CLAUDE.md 智能体
    claude_agent = skills_by_name["claude"]
    assert claude_agent.trigger is None
    assert claude_agent.name == "claude"
    assert "Claude-Specific Instructions" in claude_agent.content
    assert claude_agent.trigger is None

    # 检查 GEMINI.md 智能体
    gemini_agent = skills_by_name["gemini"]
    assert gemini_agent.trigger is None
    assert gemini_agent.name == "gemini"
    assert "Gemini-Specific Instructions" in gemini_agent.content
    assert gemini_agent.trigger is None


@pytest.fixture
def temp_skills_dir_with_uppercase_context_files():
    """创建一个包含 CLAUDE.MD 和 GEMINI.MD 文件（大写）的临时目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建。openhands/skills 目录结构
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # 在存储库根目录中创建 CLAUDE.MD 文件（全部大写）
        claude_content = """# Claude-Specific Instructions

These are instructions specifically for Claude AI."""
        (root / "CLAUDE.MD").write_text(claude_content)

        # 在存储库根目录中创建 GEMINI.MD 文件（全部大写）
        gemini_content = """# Gemini-Specific Instructions

These are instructions specifically for Google Gemini AI."""
        (root / "GEMINI.MD").write_text(gemini_content)

        # 创建测试仓库智能体
        repo_agent = """---
# type: repo
version: 1.0.0
agent: CodeActAgent
---

# Test Repository Agent

Repository-specific test instructions.
"""
        (skills_dir / "repo.md").write_text(repo_agent)

        yield root


def test_load_skills_with_uppercase_claude_gemini(
    temp_skills_dir_with_uppercase_context_files,
):
    """测试CLAUDE.MD和GEMINI.MD文件存在（大写）时的加载技巧。"""
    # 第三方文件由load_project_skills()加载，而不是load_skills_from_dir()
    skills = load_project_skills(temp_skills_dir_with_uppercase_context_files)
    skills_by_name = {s.name: s for s in skills}

    # 验证 CLAUDE.MD 和 GEMINI.MD 文件是否已加载为 RepoSkills
    assert len(skills_by_name) == 3  # repo.md + CLAUDE.MD + GEMINI.MD
    assert "repo" in skills_by_name
    assert "claude" in skills_by_name
    assert "gemini" in skills_by_name

    # 检查 CLAUDE.MD 智能体
    claude_agent = skills_by_name["claude"]
    assert claude_agent.trigger is None
    assert claude_agent.name == "claude"
    assert "Claude-Specific Instructions" in claude_agent.content

    # 检查 GEMINI.MD 智能体
    gemini_agent = skills_by_name["gemini"]
    assert gemini_agent.trigger is None
    assert gemini_agent.name == "gemini"
    assert "Gemini-Specific Instructions" in gemini_agent.content


@pytest.fixture
def temp_skills_dir_with_large_context_file():
    """创建一个临时目录，其中包含一个非常大的CLAUDE.md文件来测试
    截断。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # 创建。openhands/skills 目录结构
        skills_dir = root / ".openhands" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        # 创建一个非常大的 CLAUDE.md 文件（15,000 个字符，超过 10,000 个限制）
        # 模式：重复“CLAUDEINSTRUCTIONX\n”多次
        claude_content = "# Claude Instructions - Start\n\n"
        for i in range(800):  # 这将创建约 15,000 多个角色
            claude_content += (
                f"Claude instruction line {i:04d}: Follow this guideline carefully.\n"
            )
        claude_content += "\n# Claude Instructions - End\n"

        (root / "claude.md").write_text(claude_content)

        # 创建测试仓库智能体
        repo_agent = """---
# type: repo
version: 1.0.0
agent: CodeActAgent
---

# Test Repository Agent

Repository-specific test instructions.
"""
        (skills_dir / "repo.md").write_text(repo_agent)

        yield root, len(claude_content)


def test_repo_skill_with_mcp_tools(tmp_path):
    """测试使用 mcp_tools 配置加载存储库技能。"""
    # 创建前置元数据中包含mcp_tools的回购技能
    skill_content = """---
name: default-tools
type: repo
version: 1.0.0
agent: CodeActAgent
mcp_tools:
  fetch:
    command: uvx
    args: ["mcp-server-fetch"]
---

# Default Tools

This is a repo skill that includes MCP tools.
"""

    test_path = tmp_path / "default-tools.md"
    test_path.write_text(skill_content)

    # 加载技能
    agent = Skill.load(test_path)

    # 验证它是否已加载为 RepoSkill
    assert agent.trigger is None
    assert agent.name == "default-tools"
    assert agent.trigger is None
    assert agent.mcp_tools is not None

    fetch_server = agent.mcp_tools["fetch"]
    assert fetch_server.command == "uvx"
    assert fetch_server.args == ["mcp-server-fetch"]


def test_repo_skill_with_mcp_tools_dict_format(tmp_path):
    """测试使用 mcp_tools 作为字典（类似 JSON 的格式）加载存储库技能。"""
    # 使用 mcp_tools 以类似 JSON 的字典格式创建存储库技能
    skill_content = """---
name: default-tools-dict
type: repo
version: 1.0.0
agent: CodeActAgent
mcp_tools: {
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}
---

# Default Tools Dict

This is a repo skill that includes MCP tools in dict format.
"""

    test_path = tmp_path / "default-tools-dict.md"
    test_path.write_text(skill_content)

    # 加载技能
    agent = Skill.load(test_path)

    # 验证它是否已加载为 RepoSkill
    assert agent.trigger is None
    assert agent.name == "default-tools-dict"
    assert agent.trigger is None
    assert agent.mcp_tools is not None

    fetch_server = agent.mcp_tools["fetch"]
    assert fetch_server.command == "uvx"
    assert fetch_server.args == ["mcp-server-fetch"]


def test_repo_skill_without_mcp_tools(tmp_path):
    """测试加载没有 mcp_tools 的存储库技能（应该是 None）。"""
    # 创建一个没有 mcp_tools 的仓库技能
    skill_content = """---
name: no-mcp-tools
type: repo
version: 1.0.0
agent: CodeActAgent
---

# No MCP Tools

This is a repo skill without MCP tools.
"""

    test_path = tmp_path / "no-mcp-tools.md"
    test_path.write_text(skill_content)

    # 加载技能
    agent = Skill.load(test_path)

    # 验证它是否已加载为 RepoSkill
    assert agent.trigger is None
    assert agent.name == "no-mcp-tools"
    assert agent.trigger is None
    assert agent.mcp_tools is None


def test_repo_skill_with_invalid_mcp_tools(tmp_path):
    """测试加载具有无效 mcp_tools 配置的存储库技能。"""
    # 创建一个真正无效的回购技能 mcp_tools（错误类型）
    skill_content = """---
name: invalid-mcp-tools
type: repo
version: 1.0.0
agent: CodeActAgent
mcp_tools: "this should be a FastMCP config mapping, not a string"
---

# Invalid MCP Tools

This is a repo skill with invalid MCP tools configuration.
"""

    test_path = tmp_path / "invalid-mcp-tools.md"
    test_path.write_text(skill_content)

    # 对于无效的 mcp_tools 类型，加载应引发 SkillValidationError
    with pytest.raises(SkillValidationError) as excinfo:
        Skill.load(test_path)

    # 检查错误消息是否包含有用信息
    error_msg = str(excinfo.value)
    assert "mcp_tools must be a dictionary or None" in error_msg


def test_malformed_yaml_frontmatter_does_not_block_siblings(temp_skills_dir, caplog):
    """应跳过具有无效 YAML 前置元数据的 SKILL.md，而不是中止
    整个目录扫描。

    修复之前，`frontmatter.load()` 引发了 `yaml.scanner.ScannerError`，但
    `(SkillError, OSError)` 处理程序未捕获该问题，导致目录中所有剩余技能丢失。
    """
    # 创建一个 AgentSkills 格式的技能，其中 YAML 已损坏（不匹配的引号）
    bad_skill_dir = temp_skills_dir / "bad-yaml"
    bad_skill_dir.mkdir()
    (bad_skill_dir / "SKILL.md").write_text(
        "---\nname: bad-yaml\ndescription: 'unclosed quote\n---\nBroken skill.\n"
    )

    # 创建有效的 AgentSkills 格式技能
    good_skill_dir = temp_skills_dir / "good-skill"
    good_skill_dir.mkdir()
    (good_skill_dir / "SKILL.md").write_text(
        "---\nname: good-skill\ndescription: A valid skill\n---\nGood content.\n"
    )

    repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(temp_skills_dir)

    all_names = (
        list(repo_skills.keys())
        + list(knowledge_skills.keys())
        + list(agent_skills.keys())
    )

    # 有效技能仍需加载
    assert "good-skill" in all_names
    # 破损的技能必须跳过
    assert "bad-yaml" not in all_names
    # 因技能不佳而发出警告
    assert any("Failed to load skill" in r.message for r in caplog.records)


def test_malformed_yaml_regular_md_does_not_block_siblings(temp_skills_dir, caplog):
    """应跳过具有无效 YAML 前置元数据的常规 .md 文件
    而不中止对剩余 .md 文件的扫描。"""
    # 编写一个带有损坏的 YAML 前置元数据的常规 .md
    (temp_skills_dir / "broken.md").write_text(
        "---\nname: broken\ntriggers: [unclosed\n---\nBroken.\n"
    )

    repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(temp_skills_dir)

    all_names = (
        list(repo_skills.keys())
        + list(knowledge_skills.keys())
        + list(agent_skills.keys())
    )

    # `temp_skills_dir` 测试夹具中预先存在的有效技能必须保留
    assert len(all_names) >= 2  # 来自测试夹具的知识 + 回购
    assert "broken" not in all_names


def test_find_third_party_files_skips_symlink_duplicates(tmp_path):
    """符号链接的 CLAUDE.md → AGENTS.md 不应产生两个条目。"""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My repo guide")
    claude_md = tmp_path / "CLAUDE.md"
    symlink_or_skip(agents_md, claude_md)

    files = find_third_party_files(tmp_path, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME)

    # 只应返回一个文件，因为 CLAUDE.md 是 AGENTS.md 的符号链接
    assert len(files) == 1


def test_load_project_skills_symlinked_claude_to_agents(tmp_path):
    """当 CLAUDE.md 是 AGENTS.md 的符号链接时，仅加载一项技能。"""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My repo guide\nShared instructions.")
    claude_md = tmp_path / "CLAUDE.md"
    symlink_or_skip(agents_md, claude_md)

    skills = load_project_skills(tmp_path)

    # 应该只加载一项技能，而不是两项
    assert len(skills) == 1
    # 内容只能出现一次
    loaded_skill = skills[0]
    assert "Shared instructions" in loaded_skill.content


def test_find_third_party_files_keeps_distinct_files(tmp_path):
    """内容不同的非符号链接的CLAUDE.md和AGENTS.md都被保留。"""
    (tmp_path / "AGENTS.md").write_text("# Agents instructions")
    (tmp_path / "CLAUDE.md").write_text("# Claude instructions")

    files = find_third_party_files(tmp_path, Skill.PATH_TO_THIRD_PARTY_SKILL_NAME)

    # 两个文件都应该返回，因为它们是不同的
    assert len(files) == 2


# 确定性发现排序（问题#3607）。 Monkeypatches 强制颠倒顺序，因此如果 sorted() 包装器被删
# 除，每个测试都会失败。
#


def test_find_skill_md_directories_sorted(tmp_path, monkeypatch):
    """SKILL.md 目录按排序顺序发现。"""
    for n in ["zebra", "alpha", "mango", "beta"]:
        (tmp_path / n).mkdir()
        (tmp_path / n / "SKILL.md").write_text(f"# {n}")
    real = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda self: reversed(sorted(real(self))))
    results = find_skill_md_directories(tmp_path)
    assert [p.parent.name for p in results] == ["alpha", "beta", "mango", "zebra"]


def test_find_regular_md_files_sorted(tmp_path, monkeypatch):
    """常规 .md 文件按排序顺序发现。"""
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c")
    real = Path.rglob
    monkeypatch.setattr(Path, "rglob", lambda self, p: reversed(sorted(real(self, p))))
    results = find_regular_md_files(tmp_path, set())
    assert [p.name for p in results] == ["a.md", "b.md", "c.md"]


def test_find_skill_md_collision_winner_deterministic(tmp_path, monkeypatch):
    """SKILL.md/skill.md 碰撞确定性地选择“SKILL.md”(S < s)。"""
    require_case_sensitive_fs(tmp_path)
    (tmp_path / "skill.md").write_text("lower")
    (tmp_path / "SKILL.md").write_text("upper")
    # iterdir 呈现小写优先； sorted() 仍必须选择 SKILL.md。
    entries = [tmp_path / "skill.md", tmp_path / "SKILL.md"]
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(entries))
    found = find_skill_md(tmp_path)
    assert found is not None and found.read_text() == "upper"


def test_find_third_party_files_collision_winner_deterministic(tmp_path, monkeypatch):
    """AGENTS.md/agents.md 碰撞确定性地选择“AGENTS.md”。"""
    require_case_sensitive_fs(tmp_path)
    (tmp_path / "agents.md").write_text("lower")
    (tmp_path / "AGENTS.md").write_text("upper")
    entries = [tmp_path / "agents.md", tmp_path / "AGENTS.md"]
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(entries))
    files = find_third_party_files(tmp_path, {"agents.md": "agents"})
    assert [f.name for f in files] == ["AGENTS.md"]
