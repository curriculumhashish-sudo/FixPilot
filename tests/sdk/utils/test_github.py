"""测试 GitHub 效用函数。"""

from openhands.sdk.utils.github import ZWJ, sanitize_openhands_mentions


def test_sanitize_basic_mention():
    """测试基本的 @OpenHands 提及是否已清理。"""
    text = "Thanks @OpenHands for the help!"
    expected = f"Thanks @{ZWJ}OpenHands for the help!"
    assert sanitize_openhands_mentions(text) == expected


def test_sanitize_case_insensitive():
    """测试提及内容是否经过清理，无论大小写。"""
    test_cases = [
        ("Check @OpenHands here", f"Check @{ZWJ}OpenHands here"),
        ("Check @openhands here", f"Check @{ZWJ}openhands here"),
        ("Check @OPENHANDS here", f"Check @{ZWJ}OPENHANDS here"),
        ("Check @oPeNhAnDs here", f"Check @{ZWJ}oPeNhAnDs here"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_openhands_mentions(input_text) == expected


def test_sanitize_multiple_mentions():
    """测试同一文本中的多次提及。"""
    text = "Both @OpenHands and @openhands should be sanitized"
    expected = f"Both @{ZWJ}OpenHands and @{ZWJ}openhands should be sanitized"
    assert sanitize_openhands_mentions(text) == expected


def test_sanitize_with_punctuation():
    """测试提及后跟标点符号。"""
    test_cases = [
        ("Thanks @OpenHands!", f"Thanks @{ZWJ}OpenHands!"),
        ("Hello @OpenHands.", f"Hello @{ZWJ}OpenHands."),
        ("See @OpenHands,", f"See @{ZWJ}OpenHands,"),
        ("By @OpenHands:", f"By @{ZWJ}OpenHands:"),
        ("From @OpenHands;", f"From @{ZWJ}OpenHands;"),
        ("Hi @OpenHands?", f"Hi @{ZWJ}OpenHands?"),
        ("Use @OpenHands)", f"Use @{ZWJ}OpenHands)"),
        ("Try (@OpenHands)", f"Try (@{ZWJ}OpenHands)"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_openhands_mentions(input_text) == expected


def test_no_sanitize_partial_words():
    """测试部分单词匹配是否已被不清理。"""
    test_cases = [
        "OpenHandsTeam",
        "MyOpenHands",
        "OpenHandsBot",
        "#OpenHands",
    ]
    for text in test_cases:
        # 不带@的部分单词应保持不变
        assert sanitize_openhands_mentions(text) == text


def test_no_op_cases():
    """测试用例不应进行消毒的地方。"""
    test_cases = [
        "",
        "No mentions here",
        "Just some text",
        "@GitHub",
        "@Other",
        "OpenHands without @",
    ]
    for text in test_cases:
        assert sanitize_openhands_mentions(text) == text


def test_sanitize_at_line_boundaries():
    """测试在行首和行尾提及。"""
    test_cases = [
        ("@OpenHands at start", f"@{ZWJ}OpenHands at start"),
        ("at end @OpenHands", f"at end @{ZWJ}OpenHands"),
        ("@OpenHands", f"@{ZWJ}OpenHands"),
    ]
    for input_text, expected in test_cases:
        assert sanitize_openhands_mentions(input_text) == expected


def test_sanitize_multiline_text():
    """测试多行文本的清理。"""
    text = """Hello @OpenHands!

This is a test with @openhands mentioned.

Thanks @OPENHANDS for everything!"""

    expected = f"""Hello @{ZWJ}OpenHands!

This is a test with @{ZWJ}openhands mentioned.

Thanks @{ZWJ}OPENHANDS for everything!"""

    assert sanitize_openhands_mentions(text) == expected


def test_sanitize_with_urls():
    """测试 URLs 包含 OpenHands 的处理是否正确。"""
    test_cases = [
        # URL 不应消毒
        ("Visit https://github.com/OpenHands", "Visit https://github.com/OpenHands"),
        # 但提及应该被净化
        (
            "See @OpenHands at https://github.com/OpenHands",
            f"See @{ZWJ}OpenHands at https://github.com/OpenHands",
        ),
    ]
    for input_text, expected in test_cases:
        assert sanitize_openhands_mentions(input_text) == expected


def test_sanitize_preserves_whitespace():
    """测试空白是否被正确保留。"""
    text = "  @OpenHands  \n  @openhands  "
    expected = f"  @{ZWJ}OpenHands  \n  @{ZWJ}openhands  "
    assert sanitize_openhands_mentions(text) == expected


def test_zwj_constant():
    """测试 ZWJ 常量是否正确定义。"""
    assert ZWJ == "\u200d"
    assert len(ZWJ) == 1
    assert ord(ZWJ) == 0x200D
