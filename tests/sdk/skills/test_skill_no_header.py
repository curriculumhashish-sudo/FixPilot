from openhands.sdk.context import Skill


def test_load_markdown_without_frontmatter(tmp_path):
    """测试加载不带前置元数据的 Markdown 文件。"""
    content = "# Test Content\nThis is a test markdown file without frontmatter."
    path = tmp_path / "test.md"
    path.write_text(content)

    skill = Skill.load(path=path)

    # 验证它是否已作为具有默认值的存储库技能加载
    assert skill.trigger is None
    assert skill.name == "test"  # 名字来自path.stem
    assert skill.content == content


def test_load_markdown_with_empty_frontmatter(tmp_path):
    """测试加载带有空前置元数据的 Markdown 文件。"""
    content = (
        "---\n---\n# Test Content\nThis is a test markdown file with empty frontmatter."
    )
    path = tmp_path / "test.md"
    path.write_text(content)

    skill = Skill.load(path=path)

    # 验证它是否已作为具有默认值的存储库技能加载
    assert skill.trigger is None
    assert skill.name == "test"  # 名字来自path.stem
    assert (
        skill.content
        == "# Test Content\nThis is a test markdown file with empty frontmatter."
    )


def test_load_markdown_with_partial_frontmatter(tmp_path):
    """测试加载带有部分前置元数据的 Markdown 文件。"""
    content = """---
name: custom_name
---
# Test Content
This is a test markdown file with partial frontmatter."""
    path = tmp_path / "test.md"
    path.write_text(content)

    skill = Skill.load(path=path)

    # 验证它使用提供的名称但其他字段的默认值
    assert skill.trigger is None
    assert skill.name == "custom_name"
    assert (
        skill.content
        == "# Test Content\nThis is a test markdown file with partial frontmatter."
    )


def test_load_markdown_with_full_frontmatter(tmp_path):
    """测试加载具有完整前置元数据的 Markdown 文件仍然有效。"""
    content = """---
name: test_agent
type: repo
agent: CustomAgent
version: 2.0.0
---
# Test Content
This is a test markdown file with full frontmatter."""
    path = tmp_path / "test.md"
    path.write_text(content)

    skill = Skill.load(path=path)

    # 验证所有提供的值均已使用
    assert skill.trigger is None
    assert skill.name == "test_agent"
    assert (
        skill.content
        == "# Test Content\nThis is a test markdown file with full frontmatter."
    )
