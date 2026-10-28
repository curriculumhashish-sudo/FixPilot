"""测试截断实用函数。"""

from openhands.sdk.utils import (
    DEFAULT_TEXT_CONTENT_LIMIT,
    DEFAULT_TRUNCATE_NOTICE,
    maybe_truncate,
)


def test_maybe_truncate_no_limit():
    """测试在没有设置限制的情况下maybe_truncate是否返回原始内容。"""
    content = "This is a test string"
    result = maybe_truncate(content, truncate_after=None)
    assert result == content


def test_maybe_truncate_under_limit():
    """测试 maybe_truncate 在低于限制时返回原始内容。"""
    content = "Short string"
    result = maybe_truncate(content, truncate_after=100)
    assert result == content


def test_maybe_truncate_over_limit():
    """使用头尾测试 maybe_truncate 在超过限制时截断内容。"""  # noqa: E501
    content = "A" * 1000
    limit = 200  # 使用更大的限制来容纳通知
    result = maybe_truncate(content, truncate_after=limit)

    # 计算预期的头和尾
    notice_len = len(DEFAULT_TRUNCATE_NOTICE)
    available_chars = limit - notice_len
    half = available_chars // 2
    head_chars = half + (available_chars % 2)
    tail_chars = half
    expected = content[:head_chars] + DEFAULT_TRUNCATE_NOTICE + content[-tail_chars:]

    assert result == expected
    assert len(result) == limit


def test_maybe_truncate_custom_notice():
    """测试 maybe_truncate 使用带有头尾的自定义截断通知。"""
    content = "A" * 100
    limit = 50
    custom_notice = " [TRUNCATED]"
    result = maybe_truncate(
        content, truncate_after=limit, truncate_notice=custom_notice
    )

    # 使用自定义通知计算预期的头部和尾部
    notice_len = len(custom_notice)
    available_chars = limit - notice_len
    half = available_chars // 2
    head_chars = half + (available_chars % 2)
    tail_chars = half
    expected = content[:head_chars] + custom_notice + content[-tail_chars:]

    assert result == expected
    assert len(result) == limit


def test_maybe_truncate_exact_limit():
    """测试 maybe_truncate 在恰好达到极限时不会被截断。"""
    content = "A" * 50
    limit = 50
    result = maybe_truncate(content, truncate_after=limit)
    assert result == content


def test_default_limits():
    """测试默认限制是否合理。"""
    assert DEFAULT_TEXT_CONTENT_LIMIT == 50_000
    assert isinstance(DEFAULT_TRUNCATE_NOTICE, str)
    assert len(DEFAULT_TRUNCATE_NOTICE) > 0


def test_maybe_truncate_empty_string():
    """测试 maybe_truncate 是否正确处理空字符串。"""
    result = maybe_truncate("", truncate_after=100)
    assert result == ""


def test_maybe_truncate_zero_limit():
    """测试 maybe_truncate 是否正确处理零限制。"""
    content = "test"
    result = maybe_truncate(content, truncate_after=0)
    # 零限制被视为无限制（与 None 相同）
    assert result == content


def test_maybe_truncate_head_and_tail():
    """测试 maybe_truncate 保留头部和尾部内容。"""
    content = "BEGINNING" + "X" * 100 + "ENDING"
    limit = 50
    custom_notice = "[MIDDLE_TRUNCATED]"
    result = maybe_truncate(
        content, truncate_after=limit, truncate_notice=custom_notice
    )

    # 应保留开头和结尾
    assert result.startswith("BEGINNING")
    assert result.endswith("ENDING")
    assert custom_notice in result
    assert len(result) == limit


def test_maybe_truncate_notice_too_large():
    """测试截断通知大于限制时的行为。"""
    content = "A" * 100
    limit = 10
    large_notice = "X" * 20  # 大于限制
    result = maybe_truncate(content, truncate_after=limit, truncate_notice=large_notice)

    # 应该只返回截断的通知
    assert result == large_notice[:limit]
    assert len(result) == limit


def test_maybe_truncate_file_deduplication(tmp_path):
    """测试相同的内容是否会创建相同的文件并且不会重复。"""
    content = "A" * 1000
    limit = 200
    save_dir = str(tmp_path)

    # 第一次调用应该创建一个文件
    result1 = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 具有相同内容的第二次调用应引用相同的文件
    result2 = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 两个结果应该相同（引用相同的文件）
    assert result1 == result2
    assert "<response clipped>" in result1

    # 检查是否只创建了一个文件
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 1

    # 验证文件包含完整内容
    saved_file = files[0]
    assert saved_file.read_text() == content


def test_maybe_truncate_different_content_different_files(tmp_path):
    """测试不同的内容创建不同的文件。"""
    content1 = "A" * 1000
    content2 = "B" * 1000
    limit = 500
    save_dir = str(tmp_path)

    # 第一次调用内容1
    result1 = maybe_truncate(
        content1, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 第二次调用内容2
    result2 = maybe_truncate(
        content2, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 结果应该不同（引用的文件不同）
    assert result1 != result2
    assert "<response clipped>" in result1
    assert "<response clipped>" in result2

    assert len(result1) == limit
    assert len(result2) == limit

    # 检查是否创建了两个文件
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 2

    # 验证每个文件包含正确的内容
    file_contents = {f.read_text() for f in files}
    assert file_contents == {content1, content2}


def test_maybe_truncate_same_content_different_prefix_different_files(tmp_path):
    """测试具有不同前缀的相同内容会创建不同的文件。"""
    content = "A" * 1000
    limit = 400
    save_dir = str(tmp_path)

    # 第一次调用前缀为“bash”
    result1 = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="bash"
    )

    # 第二次调用带有前缀“editor”
    result2 = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="editor"
    )

    # 结果应该不同（由于前缀不同而导致不同的文件）
    assert result1 != result2
    assert "<response clipped>" in result1
    assert "<response clipped>" in result2

    # 检查两个文件是否使用不同的前缀创建
    bash_files = list(tmp_path.glob("bash_output_*.txt"))
    editor_files = list(tmp_path.glob("editor_output_*.txt"))
    assert len(bash_files) == 1
    assert len(editor_files) == 1

    # 验证两个文件包含相同的内容
    assert bash_files[0].read_text() == content
    assert editor_files[0].read_text() == content


def test_maybe_truncate_hash_based_filename(tmp_path):
    """测试文件名是否基于内容哈希，而不是时间戳。"""
    import hashlib

    content = "Test content for hashing " * 20  # 使内容足够长以触发截断
    limit = 300  # 强制截断但为截断通知留出空间
    save_dir = str(tmp_path)

    # 计算预期哈希值
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    expected_filename = f"test_output_{expected_hash}.txt"

    # 致电 maybe_truncate
    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 检查是否创建了预期的文件
    expected_file_path = tmp_path / expected_filename
    assert expected_file_path.exists()
    assert expected_file_path.read_text() == content

    # 检查结果是否引用了正确的文件
    assert str(expected_file_path) in result


def test_maybe_truncate_persist_notice_exceeds_limit(tmp_path):
    """测试增强持久化通知长度超过截断限制时的行为。"""
    content = "A" * 1000
    limit = 50  # 限制非常小（增强通知大于 113 个字符）
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 应截断基本通知本身以适应限制
    assert len(result) == limit
    # 由于基本通知不适合，因此未创建文件（如果我们无法告诉用户，则没有必要保存）
    #
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 0


def test_maybe_truncate_persist_head_char_moves_since_remaining_less_than_proposed_head(
    tmp_path,
):
    """
    测试当通知最初适合但由于小于剩余空间而导致头字符移动时的行为
    """
    content = "A" * 1000
    limit = 500  # 选择中间的限制将触发条件
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    assert len(result) == limit
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 1
    # 不应包含任何尾部内容，因为头字符占用了所有剩余空间
    assert result.endswith("</NOTE>")


def test_maybe_truncate_persist_notice_leaves_minimal_room(tmp_path):
    """测试持久化通知何时为头/尾内容留出最小空间。"""
    content = "BEGINNING" + "X" * 1000 + "ENDING"
    # 设置限制，使持久化通知仅留下几个字符作为内容
    limit = 300  # 根据典型的持久化通知长度进行调整
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    assert len(result) == limit
    # 如果可能的话，仍然应该尝试包括一些头/尾
    assert "test_output_" in result  # 文件路径应该在结果中
    # 验证文件已创建
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 1
    assert files[0].read_text() == content


def test_maybe_truncate_line_number_accuracy(tmp_path):
    """测试持久化通知中的行号是否准确。"""
    import re

    # 创建具有已知行结构的内容
    lines = [f"Line {i}\n" for i in range(1, 101)]
    content = "".join(lines)
    limit = 500  # 强制截断
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 从结果中提取行号
    match = re.search(r"line (\d+)", result)
    assert match is not None
    line_num = int(match.group(1))

    # 验证行号是否合理（应该在中间的某个位置）
    assert 1 <= line_num <= len(lines)


def test_maybe_truncate_short_content_with_persistence(tmp_path):
    """测试短内容不会不必要地获得已持久化。"""
    content = "Short"
    limit = 100  # 比内容大得多
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    # 应返回原始内容而不被截断或保存
    assert result == content
    # 由于未发生截断，因此不应创建任何文件
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 0


def test_maybe_truncate_unicode_content_persistence(tmp_path):
    """使用 Unicode 内容测试持久化。"""
    content = "Hello 世界 🌍 " * 100  # ASCII、中文和表情符号的混合
    limit = 200
    save_dir = str(tmp_path)

    result = maybe_truncate(
        content, truncate_after=limit, save_dir=save_dir, tool_prefix="test"
    )

    assert len(result) == limit
    # 验证文件已创建并包含正确的 Unicode 内容
    files = list(tmp_path.glob("test_output_*.txt"))
    assert len(files) == 1
    saved_content = files[0].read_text(encoding="utf-8")
    assert saved_content == content
