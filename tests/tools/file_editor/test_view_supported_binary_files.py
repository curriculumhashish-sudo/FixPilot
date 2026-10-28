import tempfile
from pathlib import Path

from openhands.tools.file_editor import file_editor
from openhands.tools.file_editor.definition import FileEditorObservation

from .conftest import assert_successful_result


def test_view_simple_pdf_file():
    """测试查看基于 ASCII 的简单 PDF 文件是否有效。"""
    # 创建一个包含 ASCII 内容的临时 PDF 文件（无二进制流）
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        # 创建最少的 PDF 内容，其中大部分内容为 ASCII
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Printer-Friendly Caltrain Schedule) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
299
%%EOF"""  # noqa: W291
        f.write(pdf_content)
        test_file = f.name

    try:
        result = file_editor(command="view", path=test_file)

        assert isinstance(result, FileEditorObservation)
        assert_successful_result(result)
        assert f"Here's the result of running `cat -n` on {test_file}" in result.text

        # 检查 PDF 中存在的特定内容
        assert (
            result.text is not None
            and "Printer-Friendly Caltrain Schedule" in result.text
        )
    finally:
        # 清理临时文件
        Path(test_file).unlink(missing_ok=True)


def test_view_binary_pdf_file_returns_error():
    """测试查看二进制 PDF 文件是否返回错误观测结果。"""
    # 创建一个临时 PDF 文件，其中包含无法解码为文本的二进制内容
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        # 创建具有二进制内容的 PDF（具有非 UTF8 字节的压缩流）
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Filter /FlateDecode
/Length 100
>>
stream
\x78\x9c\x93\x00\x00\x00\x01\x00\x01\x78\x9c\x93\x00\x00\x00\x01\x00\x01
endstream
endobj

xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
400
%%EOF"""
        f.write(pdf_content)
        test_file = f.name

    try:
        result = file_editor(command="view", path=test_file)

        assert isinstance(result, FileEditorObservation)
        assert result.is_error is True
        assert result.text is not None
        # 错误可能来自 validate_file（二进制检测）或 _count_lines (UnicodeDecodeError)，
        # 两者都是有效的错误路径
        #
        assert (
            "binary" in result.text.lower()
            or "cannot be decoded" in result.text.lower()
        )
    finally:
        # 清理临时文件
        Path(test_file).unlink(missing_ok=True)
