"""visualize_diff 功能的测试在 FileEditorObservation。"""

from rich.text import Text

from openhands.tools.file_editor.definition import FileEditorObservation
from openhands.tools.file_editor.utils.diff import (
    get_edit_groups,
    visualize_diff,
)


def test_visualize_diff_simple_replacement():
    """使用简单的字符串替换来测试 visualize_diff。"""
    old_content = """def hello():
    print("Hello, World!")
    return True"""

    new_content = """def hello():
    print("Hello, Universe!")
    return True"""

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )

    assert observation.path == "/test/file.py"
    diff = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    # 检查 diff 是否包含预期元素
    diff_str = str(diff)
    assert "[File /test/file.py edited with 1 changes.]" in diff_str
    assert "[begin of edit 1 / 1]" in diff_str
    assert "[end of edit 1 / 1]" in diff_str
    assert "(content before edit)" in diff_str
    assert "(content after edit)" in diff_str
    assert '-2|    print("Hello, World!")' in diff_str
    assert '+2|    print("Hello, Universe!")' in diff_str


def test_visualize_diff_no_changes():
    """当没有变化时测试visualize_diff。"""
    content = """def hello():
    print("Hello, World!")
    return True"""

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=content,
        new_content=content,
        prev_exist=True,
    )

    assert observation.path == "/test/file.py"
    diff = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    expected_msg = (
        "(no changes detected. Please make sure your edits change "
        "the content of the existing file.)\n"
    )
    assert isinstance(diff, Text)
    assert str(diff) == expected_msg


def test_visualize_diff_multiple_changes():
    """在同一块中进行多次更改来测试 visualize_diff。"""
    old_content = """def calculate(a, b):
    result = a + b
    print(f"Result: {result}")
    return result

def main():
    x = 5
    y = 10
    calculate(x, y)"""

    new_content = """def calculate(a, b):
    result = a * b  # Changed from + to *
    print(f"Product: {result}")  # Changed message
    return result

def main():
    x = 7  # Changed value
    y = 10
    calculate(x, y)"""

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/calc.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )
    assert observation.path == "/test/calc.py"
    diff = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    # 检查 diff 是否包含预期元素
    diff_str = str(diff)
    assert "[File /test/calc.py edited with 1 changes.]" in diff_str
    assert "-2|    result = a + b" in diff_str
    assert "+2|    result = a * b  # Changed from + to *" in diff_str
    assert '-3|    print(f"Result: {result}")' in diff_str
    assert '+3|    print(f"Product: {result}")  # Changed message' in diff_str
    assert "-7|    x = 5" in diff_str
    assert "+7|    x = 7  # Changed value" in diff_str


def test_visualize_diff_attempted_edit():
    """用 change_applied=False 测试 visualize_diff。"""
    old_content = "old line"
    new_content = "new line"

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )

    assert observation.path == "/test/file.py"
    diff = visualize_diff(
        observation.path,
        observation.old_content,
        observation.new_content,
        change_applied=False,
    )

    diff_str = str(diff)
    assert "[Changes are NOT applied to /test/file.py" in diff_str
    assert "ATTEMPTED edit" in diff_str
    assert "[begin of ATTEMPTED edit 1 / 1]" in diff_str
    assert "[end of ATTEMPTED edit 1 / 1]" in diff_str


def test_visualize_diff_caching():
    """测试差异可视化是否正确缓存。"""
    old_content = "old line"
    new_content = "new line"

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )

    # 第一次调用应该计算和缓存
    assert observation._diff_cache is None
    assert observation.path == "/test/file.py"
    diff1 = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    # 第二次调用应该使用缓存
    diff2 = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    assert diff1 == diff2


def test_visualize_diff_custom_context_lines():
    """使用自定义数量的上下文行测试 visualize_diff。"""
    old_content = """line1
line2
old_line
line4
line5
line6
line7"""

    new_content = """line1
line2
new_line
line4
line5
line6
line7"""

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )

    # 用 1上下文行测试
    assert observation.path == "/test/file.py"
    diff_1_context = visualize_diff(
        observation.path,
        observation.old_content,
        observation.new_content,
        n_context_lines=1,
    )

    # 重置缓存以测试不同的上下文
    observation._diff_cache = None

    # 使用 3 上下文行进行测试
    diff_3_context = visualize_diff(
        observation.path,
        observation.old_content,
        observation.new_content,
        n_context_lines=3,
    )

    # 由于不同的上下文，差异应该不同
    assert diff_1_context != diff_3_context


def test_get_edit_groups():
    """测试 get_edit_groups 方法。"""
    old_content = """line1
old_line2
line3"""

    new_content = """line1
new_line2
line3"""

    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=old_content,
        new_content=new_content,
        prev_exist=True,
    )
    assert observation.path == "/test/file.py"
    assert observation.old_content == old_content
    assert observation.new_content == new_content

    edit_groups = get_edit_groups(
        observation.old_content, observation.new_content, n_context_lines=1
    )

    assert len(edit_groups) == 1
    assert edit_groups[0].before_edits
    assert edit_groups[0].after_edits
    assert len(edit_groups[0].before_edits) == 3  # 1 上下文 + 1 变化 + 1 上下文
    assert len(edit_groups[0].after_edits) == 3


def test_get_edit_groups_no_content():
    """当 old_content 或 new_content 为 None 时测试 get_edit_groups。"""
    # 直接使用 None 值进行测试 - 应返回空列表
    edit_groups = get_edit_groups(None, "some content")
    assert edit_groups == []

    edit_groups = get_edit_groups("some content", None)
    assert edit_groups == []

    edit_groups = get_edit_groups(None, None)
    assert edit_groups == []

    # 使用空字符串与内容进行测试 - 应返回编辑组
    edit_groups = get_edit_groups("", "some content")
    assert len(edit_groups) == 1
    assert edit_groups[0].before_edits == ["-1|"]
    assert edit_groups[0].after_edits == ["+1|some content"]

    edit_groups = get_edit_groups("some content", "")
    assert len(edit_groups) == 1
    assert edit_groups[0].before_edits == ["-1|some content"]
    assert edit_groups[0].after_edits == ["+1|"]


def test_visualize_diff_none_content():
    """当内容为 None 时测试 visualize_diff。"""
    observation = FileEditorObservation(
        command="str_replace",
        path="/test/file.py",
        old_content=None,
        new_content=None,
        prev_exist=True,
    )

    # 不应崩溃并应返回“未检测到更改”消息
    assert observation.path == "/test/file.py"
    diff = visualize_diff(
        observation.path, observation.old_content, observation.new_content
    )

    # 当两个内容都为None时，视为没有变化
    expected_msg = (
        "(no changes detected. Please make sure your edits change "
        "the content of the existing file.)\n"
    )
    assert isinstance(diff, Text)
    assert str(diff) == expected_msg
