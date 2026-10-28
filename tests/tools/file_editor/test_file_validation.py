from pathlib import Path

import pytest
from binaryornot.check import is_binary

from openhands.sdk import ImageContent
from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.exceptions import (
    FileValidationError,
)


def test_validate_large_file(tmp_path):
    """测试大文件是否被拒绝。"""
    editor = FileEditor()
    large_file = tmp_path / "large.txt"

    # 创建一个刚刚超过 10MB 的文件
    file_size = 10 * 1024 * 1024 + 1024  # 10MB+1KB
    with open(large_file, "wb") as f:
        f.write(b"0" * file_size)

    with pytest.raises(FileValidationError) as exc_info:
        editor.validate_file(large_file)
    assert "File is too large" in str(exc_info.value)
    assert "10.0MB" in str(exc_info.value)


def test_validate_binary_file(tmp_path):
    """测试二进制文件是否被拒绝。"""
    editor = FileEditor()
    binary_file = tmp_path / "binary.bin"

    # 创建一个包含 null 字节的二进制文件
    with open(binary_file, "wb") as f:
        f.write(b"Some text\x00with binary\x00content")

    with pytest.raises(FileValidationError) as exc_info:
        editor.validate_file(binary_file)
    assert "file appears to be binary" in str(exc_info.value).lower()


def test_validate_text_file(tmp_path):
    """测试是否接受有效的文本文件。"""
    editor = FileEditor()
    text_file = tmp_path / "valid.txt"

    # 创建有效的文本文件
    with open(text_file, "w") as f:
        f.write("This is a valid text file\nwith multiple lines\n")

    # 不应引发任何异常
    editor.validate_file(text_file)


def test_validate_directory():
    """测试验证中的目录是否被跳过。"""
    editor = FileEditor()
    # 不应该对目录引发任何异常
    editor.validate_file(Path("/tmp"))


def test_validate_nonexistent_file():
    """测试验证不存在的文件。"""
    editor = FileEditor()
    nonexistent = Path("/nonexistent/file.txt")
    # 不应引发 FileValidationError，因为 validate_path 将处理这种情况
    editor.validate_file(nonexistent)


def test_validate_pdf_file(tmp_path):
    """测试 PDF 文件是否被检测为二进制文件。"""
    editor = FileEditor()

    # 创建一个假的 PDF 文件
    pdf_file = tmp_path / "sample.pdf"
    # 创建一个带有 PDF 标头的文件，但使其类似于文本以进行测试
    with open(pdf_file, "w") as f:
        f.write("%PDF-1.4\nThis is a fake PDF file for testing")

    # binaryornot 按扩展名/签名将任何 .pdf 分类为二进制文件，因此文件编辑器必须回退到基
    # 于内容的文本检测。
    #
    assert is_binary(str(pdf_file))

    # 当内容为文本时，PDF 是受支持的文件类型，因此不应引发异常
    #
    editor.validate_file(pdf_file)


def test_validate_short_non_utf8_text_file(tmp_path):
    """非 UTF-8 的短文件不得作为二进制文件被拒绝。

    它们低于编码检测器的置信度阈值，因此检测到的编码是 utf-8 并且使用它进行解码失败。
     编辑器仍然必须通过候选编解码器恢复它们。
    """
    editor = FileEditor()

    latin1_file = tmp_path / "latin1.txt"
    latin1_file.write_bytes(b"Caf\xe9 r\xe9sum\xe9\n")

    cp1251_file = tmp_path / "cp1251.txt"
    cp1251_file.write_bytes("Привет мир, это тест\n".encode("cp1251"))

    for path in (latin1_file, cp1251_file):
        assert is_binary(str(path)), f"{path.name} should be flagged by binaryornot"
        editor.validate_file(path)
        assert editor.read_file(path)


def test_validate_image_file(tmp_path):
    """测试图像文件是否被检测为二进制文件。"""
    editor = FileEditor()

    # 创建一个假的二进制图像文件
    image_file = tmp_path / "test_image.png"
    # 创建一个带有 PNG 标头的文件以使其成为二进制文件
    with open(image_file, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01")

    assert is_binary(str(image_file))

    # 不支持图像，因此不应引发异常
    editor.validate_file(image_file)


def test_view_image_file_returns_image_content(tmp_path):
    """测试查看图像文件是否返回 ImageContent，且不会出现错误。"""
    editor = FileEditor()
    image_file = tmp_path / "test.png"

    # 创建最小有效 1x1 PNG 图像（红色像素）这是一个完整、有效的 PNG 文件
    #
    png_data = (
        b"\x89PNG\r\n\x1a\n"  # PNG 签名
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"  # IHDR 块 (1x1)
        b"\x08\x02\x00\x00\x00\x90wS\xde"  # IHDR 数据 + CRC
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01"  # IDAT 块
        b"\x00\x18\xdd\x8d\xb4"  # IDAT CRC
        b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND 块
    )

    with open(image_file, "wb") as f:
        f.write(png_data)

    # 查看图像文件 - 应返回 ImageContent
    result = editor(command="view", path=str(image_file))

    # 验证结果包含ImageContent
    assert result is not None
    assert hasattr(result, "content")
    assert len(result.content) == 2  # TextContent 包含消息 + ImageContent
    assert any(isinstance(c, ImageContent) for c in result.content)

    # 获取 ImageContent 并验证它有 image_urls
    image_content = [c for c in result.content if isinstance(c, ImageContent)][0]
    assert len(image_content.image_urls) == 1
    assert image_content.image_urls[0].startswith("data:image/png;base64,")
