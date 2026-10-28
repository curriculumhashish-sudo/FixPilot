"""单元测试为编码模块。"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from openhands.tools.file_editor import file_editor
from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.utils.encoding import (
    EncodingManager,
    with_encoding,
)


@pytest.fixture
def temp_file():
    """创建一个临时文件用于测试。"""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield Path(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def encoding_manager():
    """创建一个 EncodingManager 实例用于测试。"""
    return EncodingManager()


def test_detect_encoding_nonexistent_file(encoding_manager):
    """测试检测不存在文件的编码。"""
    nonexistent_path = Path("/nonexistent/file.txt")
    encoding = encoding_manager.detect_encoding(nonexistent_path)
    assert encoding == encoding_manager.default_encoding


def test_detect_encoding_utf8(encoding_manager, temp_file):
    """测试检测 UTF-8 编码。"""
    # 创建UTF-8编码文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Hello, world! UTF-8 encoded text.")

    encoding = encoding_manager.detect_encoding(temp_file)
    assert encoding.lower() in ("utf-8", "ascii")


def test_detect_encoding_utf8_with_icon(encoding_manager, temp_file):
    """测试使用单词和表情符号检测 UTF-8 编码。"""
    # 创建一个包含单个单词和表情符号的 UTF-8 编码文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Hello 😊")

    encoding = encoding_manager.detect_encoding(temp_file)
    assert encoding.lower() == "utf-8"


def test_detect_encoding_prefers_valid_utf8(encoding_manager, temp_file):
    temp_file.write_text('{"title": "用户研究"}', encoding="utf-8")

    with patch(
        "charset_normalizer.detect",
        return_value={"encoding": "windows-1251", "confidence": 1.0},
    ):
        encoding = encoding_manager.detect_encoding(temp_file)

    assert encoding.lower() == "utf-8"


@pytest.mark.parametrize("guess", ["windows-1251", "windows-1252", "iso-8859-1"])
def test_get_encoding_prefers_valid_utf8(encoding_manager, temp_file, guess):
    temp_file.write_text('{"title": "用户研究"}', encoding="utf-8")

    with patch(
        "charset_normalizer.detect",
        return_value={"encoding": guess, "confidence": 1.0},
    ):
        encoding = encoding_manager.get_encoding(temp_file)

    assert encoding.lower() == "utf-8"


def test_detect_encoding_cp1251(encoding_manager, temp_file):
    """测试检测 CP1251 编码。"""
    # 创建带有西里尔字符的 CP1251 编码文件
    with open(temp_file, "wb") as f:
        f.write("Привет, мир! Текст в кодировке CP1251.".encode("cp1251"))

    encoding = encoding_manager.detect_encoding(temp_file)
    assert encoding.lower() in ("windows-1251", "cp1251")


def test_detect_encoding_low_confidence(encoding_manager, temp_file):
    """当置信度较低时，测试回退方案为默认编码。"""
    # 创建一个混合编码的文件来迷惑检测器
    with open(temp_file, "wb") as f:
        f.write(b"\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f")

    # 模拟对象 chardet.detect 返回低置信度
    with patch(
        "charset_normalizer.detect",
        return_value={"encoding": "ascii", "confidence": 0.3},
    ):
        encoding = encoding_manager.detect_encoding(temp_file)
        assert encoding == encoding_manager.default_encoding


def test_detect_encoding_none_result(encoding_manager, temp_file):
    """当 chardet 返回 None 进行编码时，测试回退方案为默认编码。"""
    with open(temp_file, "wb") as f:
        f.write(b"\x00\x01\x02\x03")  # 二进制数据

    # 模拟对象chardet.detect返回None进行编码
    with patch(
        "charset_normalizer.detect", return_value={"encoding": None, "confidence": 0.0}
    ):
        encoding = encoding_manager.detect_encoding(temp_file)
        assert encoding == encoding_manager.default_encoding


def test_get_encoding_cache_hit(encoding_manager, temp_file):
    """测试 get_encoding 是否使用可用的缓存值。"""
    # 创建文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Hello, world!")

    # 第一次调用应该检测编码
    with patch.object(
        encoding_manager, "detect_encoding", return_value="utf-8"
    ) as mock_detect:
        encoding1 = encoding_manager.get_encoding(temp_file)
        assert encoding1 == "utf-8"
        mock_detect.assert_called_once()

    # 第二次调用应该使用缓存
    with patch.object(
        encoding_manager, "detect_encoding", return_value="utf-8"
    ) as mock_detect:
        encoding2 = encoding_manager.get_encoding(temp_file)
        assert encoding2 == "utf-8"
        mock_detect.assert_not_called()


def test_get_encoding_cache_invalidation(encoding_manager, temp_file):
    """测试文件修改时缓存是否失效。"""
    # 创建文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Hello, world!")

    # 第一次调用应该检测编码
    encoding1 = encoding_manager.get_encoding(temp_file)
    assert encoding1.lower() in ("utf-8", "ascii")

    # 稍等一下，确保修改时间会有所不同
    time.sleep(0.1)

    # 修改文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Modified content")

    # 模拟对象 detect_encoding 验证是否再次调用
    with patch.object(
        encoding_manager, "detect_encoding", return_value="utf-8"
    ) as mock_detect:
        encoding2 = encoding_manager.get_encoding(temp_file)
        assert encoding2 == "utf-8"
        mock_detect.assert_called_once()


def test_with_encoding_decorator():
    """测试 with_encoding 装饰器。"""

    # 创建一个带有将被修饰的方法的模拟对象类
    class MockEditor:
        def __init__(self):
            self._encoding_manager: EncodingManager = EncodingManager()

        @with_encoding
        def read_file(self, path, encoding="utf-8"):
            return f"Reading file with encoding: {encoding}"

    editor = MockEditor()

    # 使用目录进行测试
    with patch.object(Path, "is_dir", return_value=True):
        with patch.object(
            editor._encoding_manager, "get_encoding"
        ) as mock_get_encoding:
            result = editor.read_file(Path("/some/dir"))
            assert result == "Reading file with encoding: utf-8"
            mock_get_encoding.assert_not_called()

    # 使用不存在的文件进行测试
    with patch.object(Path, "is_dir", return_value=False):
        with patch.object(Path, "exists", return_value=False):
            result = editor.read_file(Path("/nonexistent/file.txt"))
            assert (
                result == f"Reading file with encoding: "
                f"{editor._encoding_manager.default_encoding}"
            )

    # 使用现有文件进行测试
    with patch.object(Path, "is_dir", return_value=False):
        with patch.object(Path, "exists", return_value=True):
            with patch.object(
                editor._encoding_manager, "get_encoding", return_value="latin-1"
            ):
                result = editor.read_file(Path("/existing/file.txt"))
                assert result == "Reading file with encoding: latin-1"


def test_with_encoding_respects_provided_encoding():
    """测试 with_encoding 装饰器是否遵循显式提供的编码。"""
    # with_encoding 的当前实现始终调用 get_encoding，但如果 kwargs 中存在提供的编码，则
    # 不会覆盖它
    #

    class MockEditor:
        def __init__(self):
            self._encoding_manager: EncodingManager = EncodingManager()

        @with_encoding
        def read_file(self, path, encoding="utf-8"):
            return f"Reading file with encoding: {encoding}"

    editor = MockEditor()

    # 使用显式提供的编码进行测试
    with patch.object(Path, "is_dir", return_value=False):
        with patch.object(Path, "exists", return_value=True):
            with patch.object(
                editor._encoding_manager,
                "get_encoding",
                return_value="detected-encoding",
            ):
                result = editor.read_file(Path("/some/file.txt"), encoding="iso-8859-1")
                # 应使用提供的编码，而不是检测到的编码
                assert result == "Reading file with encoding: iso-8859-1"


def test_cache_size_limit(encoding_manager, temp_file):
    """测试缓存大小是否有限并且 LRU 条目被逐出。"""
    # 创建一个小缓存用于测试
    encoding_manager = EncodingManager(max_cache_size=3)

    # 创建文件
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write("Test file")

    # 创建4个不同的路径（使用相同的文件但具有不同的路径）
    paths = [Path(f"{temp_file}.{i}") for i in range(4)]

    # 模拟对象存在且getmtime返回值一致
    with patch.object(Path, "exists", return_value=True):
        with patch.object(os.path, "getmtime", return_value=123456):
            with patch.object(
                encoding_manager, "detect_encoding", return_value="utf-8"
            ):
                # 访问路径顺序为0、1、2、3
                for i, path in enumerate(paths):
                    encoding_manager.get_encoding(path)

                # 添加第 4 个项目后，缓存应该仍然有 3 个项目
                assert len(encoding_manager._encoding_cache) == 3
                # 路径 0 应该被驱逐 (LRU)
                assert str(paths[0]) not in encoding_manager._encoding_cache
                # 路径 1、2、3 仍应在缓存中
                for j in range(1, 4):
                    assert str(paths[j]) in encoding_manager._encoding_cache


@pytest.fixture
def temp_non_utf8_file():
    """创建一个 cp1251 编码的临时文件用于测试。"""
    fd, path = tempfile.mkstemp()
    os.close(fd)

    # 创建包含俄语文本的 cp1251 编码文件
    with open(path, "wb") as f:
        f.write("# -*- coding: cp1251 -*-\n\n".encode("cp1251"))
        f.write("# Тестовый файл с кириллицей\n".encode("cp1251"))
        f.write('text = "Привет, мир!"\n'.encode("cp1251"))
        f.write("numbers = [1, 2, 3, 4, 5]\n".encode("cp1251"))
        f.write('message = "Это тестовая строка"\n'.encode("cp1251"))

    yield Path(path)
    os.unlink(path)


def test_view_non_utf8_file(temp_non_utf8_file):
    """测试查看非 UTF-8 编码的文件。"""
    # 查看文件
    result = file_editor(
        command="view",
        path=str(temp_non_utf8_file),
    )

    # 解析结果解析结果 - 现在使用直接访问
    #

    # 验证内容读取正确
    assert result.text is not None and "Привет, мир!" in result.text
    assert result.text is not None and "Тестовый файл с кириллицей" in result.text
    assert result.text is not None and "Это тестовая строка" in result.text


def test_view_range_non_utf8_file(temp_non_utf8_file):
    """测试查看特定范围的非 UTF-8 编码文件。"""
    # 仅查看第 3-5 行
    result = file_editor(
        command="view",
        path=str(temp_non_utf8_file),
        view_range=[3, 5],
    )

    # 解析结果解析结果 - 现在使用直接访问
    #

    # 验证内容读取正确
    assert result.text is not None and "Тестовый файл с кириллицей" in result.text
    assert result.text is not None and "Привет, мир!" in result.text

    # 验证是否不包括第 6 行
    assert result.text is not None and "Это тестовая строка" not in result.text


def test_str_replace_non_utf8_file(temp_non_utf8_file):
    """测试替换非 UTF-8 编码文件中的文本。"""
    # 替换文本
    result = file_editor(
        command="str_replace",
        path=str(temp_non_utf8_file),
        old_str="Привет, мир!",
        new_str="Здравствуй, мир!",
    )

    # 解析结果解析结果 - 现在使用直接访问
    #

    # 验证更换是否成功
    assert result.text is not None and "Здравствуй, мир!" in result.text
    assert result.text is not None and "Привет, мир!" not in result.text

    # 验证文件是否使用正确的编码保存
    with open(temp_non_utf8_file, "rb") as f:
        content = f.read()

    try:
        decoded = content.decode("cp1251")
        assert "Здравствуй, мир!" in decoded
    except UnicodeDecodeError:
        pytest.fail("File was not saved with the correct encoding")


def test_insert_non_utf8_file(temp_non_utf8_file):
    """测试在非 UTF-8 编码文件中插入文本。"""
    # 在第 4 行后插入文本
    result = file_editor(
        command="insert",
        path=str(temp_non_utf8_file),
        insert_line=4,
        new_str='new_var = "Новая переменная"',
    )

    # 解析结果解析结果 - 现在使用直接访问
    #

    # 验证插入是否成功
    assert result.text is not None and "Новая переменная" in result.text

    # 验证文件是否使用正确的编码保存
    with open(temp_non_utf8_file, "rb") as f:
        content = f.read()

    try:
        decoded = content.decode("cp1251")
        assert "Новая переменная" in decoded
    except UnicodeDecodeError:
        pytest.fail("File was not saved with the correct encoding")


@pytest.mark.parametrize(
    "content, read_encoding",
    [
        # cp1251 无法编码 U+2192 -> 必须升级到 UTF-8 而不是截断。
        ("status \u2192 ok", "utf-8"),
        # cp1251 中可表示的内容 -> 保留原始编码。
        ("Привет, мир!", "cp1251"),
    ],
)
def test_write_file_falls_back_to_utf8_only_when_needed(
    tmp_path, content, read_encoding
):
    """Regression: 写入文件编码无法表示的内容不得
    截断文件； 它升级到UTF-8。 该编码所能表示的内容保持原来的编码。 编码是强制的（不
    是嗅探），因此跨平台的测试是确定性的。
    """
    editor = FileEditor(workspace_root=str(tmp_path))
    path = tmp_path / "doc.txt"
    path.write_text("seed", encoding="ascii")

    editor.write_file(path, content, encoding="cp1251")

    assert path.read_bytes(), "file was truncated/destroyed by a failed write"
    assert path.read_text(encoding=read_encoding) == content


def test_write_failure_leaves_original_file_intact(temp_non_utf8_file, monkeypatch):
    """Regression: 写入期间失败必须保留原始文件
    不受影响（原子写入）并且不会留下杂散的临时文件。"""
    before = temp_non_utf8_file.read_bytes()

    def boom(src, dst):
        raise OSError("simulated os.replace failure")

    monkeypatch.setattr(os, "replace", boom)

    result = file_editor(
        command="str_replace",
        path=str(temp_non_utf8_file),
        old_str="numbers = [1, 2, 3, 4, 5]",
        new_str="numbers = [9, 9, 9]",
    )

    assert result.is_error is True
    assert temp_non_utf8_file.read_bytes() == before
    leftovers = list(
        temp_non_utf8_file.parent.glob(f".{temp_non_utf8_file.name}.*.tmp")
    )
    assert leftovers == [], f"stray temp files left behind: {leftovers}"


def test_create_non_utf8_file():
    """测试创建一个包含非 UTF-8 内容的新文件。"""
    # 创建临时路径
    fd, path = tempfile.mkstemp()
    os.close(fd)
    os.unlink(path)  # 删除该文件，以便我们可以使用编辑器创建它

    try:
        # 使用俄语字符创建内容
        content = "# -*- coding: cp1251 -*-\n\n"
        content += "# Новый файл с кириллицей\n"
        content += 'greeting = "Привет из нового файла!"\n'

        # 创建文件
        result = file_editor(
            command="create",
            path=path,
            file_text=content,
        )

        # 解析结果解析结果 - 现在使用直接访问
        #

        # 验证文件创建成功
        assert result.text is not None and "File created successfully" in result.text

        # 读取cp1251编码的文件，验证内容
        encoding_manager = EncodingManager()
        encoding = encoding_manager.detect_encoding(Path(path))

        with open(path, encoding=encoding) as f:
            file_content = f.read()

        assert "Привет из нового файла!" in file_content
        assert "Новый файл с кириллицей" in file_content

    finally:
        # 清理
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def test_undo_edit_non_utf8_file(temp_non_utf8_file):
    """测试撤消非 UTF-8 编码文件中的编辑。"""
    # 首先，做出改变
    file_editor(
        command="str_replace",
        path=str(temp_non_utf8_file),
        old_str="Привет, мир!",
        new_str="Здравствуй, мир!",
    )

    # 现在撤消更改
    result = file_editor(
        command="undo_edit",
        path=str(temp_non_utf8_file),
    )

    # 解析结果解析结果 - 现在使用直接访问
    #

    # 验证撤消是否成功
    assert result.text is not None and "undone successfully" in result.text

    # 验证原始内容是否已使用正确的编码恢复
    with open(temp_non_utf8_file, "rb") as f:
        content = f.read()

    try:
        decoded = content.decode("cp1251")
        assert "Привет, мир!" in decoded
        assert "Здравствуй, мир!" not in decoded
    except UnicodeDecodeError:
        pytest.fail("File was not restored with the correct encoding")


def test_complex_workflow_non_utf8_file(temp_non_utf8_file):
    """在非 UTF-8 编码文件上测试具有多个操作的复杂工作流程。"""
    # 1. 查看文件
    result = file_editor(
        command="view",
        path=str(temp_non_utf8_file),
    )
    # 解析结果 - 现在使用直接访问
    assert result.text is not None and "Привет, мир!" in result.text

    # 2. 替换文本
    result = file_editor(
        command="str_replace",
        path=str(temp_non_utf8_file),
        old_str="Привет, мир!",
        new_str="Здравствуй, мир!",
    )
    # 解析结果 - 现在使用直接访问
    assert result.text is not None and "Здравствуй, мир!" in result.text

    # 3. 插入文字
    result = file_editor(
        command="insert",
        path=str(temp_non_utf8_file),
        insert_line=5,
        new_str="# Добавленная строка\nboolean_var = True",
    )
    # 解析结果 - 现在使用直接访问
    assert result.text is not None and "Добавленная строка" in result.text

    # 4. 查看具体范围
    result = file_editor(
        command="view",
        path=str(temp_non_utf8_file),
        view_range=[5, 7],
    )
    # 解析结果 - 现在使用直接访问
    assert result.text is not None and "Добавленная строка" in result.text
    assert result.text is not None and "boolean_var = True" in result.text

    # 5. 撤消上次编辑
    result = file_editor(
        command="undo_edit",
        path=str(temp_non_utf8_file),
    )
    # 解析结果 - 现在使用直接访问
    assert result.text is not None and "undone successfully" in result.text

    # 6. 所有操作完成后验证文件内容
    with open(temp_non_utf8_file, "rb") as f:
        content = f.read()

    try:
        decoded = content.decode("cp1251")
        assert "Здравствуй, мир!" in decoded  # 从步骤 2 开始
        assert "Добавленная строка" not in decoded  # 在步骤 5 中撤消
    except UnicodeDecodeError:
        pytest.fail("File was not maintained with the correct encoding")


def test_mixed_encoding_workflow():
    """使用不同编码的文件测试工作流程。"""
    # 创建两个不同编码的临时文件
    fd1, path1 = tempfile.mkstemp()
    fd2, path2 = tempfile.mkstemp()
    os.close(fd1)
    os.close(fd2)

    try:
        # 创建cp1251编码文件
        with open(path1, "wb") as f:
            f.write("# -*- coding: cp1251 -*-\n".encode("cp1251"))
            f.write('text_cp1251 = "Текст в кодировке CP1251"\n'.encode("cp1251"))

        # 创建UTF-8编码文件
        with open(path2, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write('text_utf8 = "Текст в кодировке UTF-8"\n')

        # 1. 查看cp1251文件
        result1 = file_editor(
            command="view",
            path=path1,
        )
        # 解析结果 - 现在使用直接访问
        assert "Текст в кодировке CP1251" in result1.text

        # 2. 查看UTF-8文件
        result2 = file_editor(
            command="view",
            path=path2,
        )
        # 解析结果 - 现在使用直接访问
        assert "Текст в кодировке UTF-8" in result2.text

        # 3. 编辑cp1251文件
        result3 = file_editor(
            command="str_replace",
            path=path1,
            old_str="Текст в кодировке CP1251",
            new_str="Измененный текст в CP1251",
        )
        # 解析结果 - 现在使用直接访问
        assert "Измененный текст в CP1251" in result3.text

        # 4. 编辑UTF-8文件
        result4 = file_editor(
            command="str_replace",
            path=path2,
            old_str="Текст в кодировке UTF-8",
            new_str="Измененный текст в UTF-8",
        )
        # 解析结果 - 现在使用直接访问
        assert "Измененный текст в UTF-8" in result4.text

        # 5. 验证两个文件都保持其原始编码
        with open(path1, "rb") as f:
            content1 = f.read()
        with open(path2, "rb") as f:
            content2 = f.read()

        # CP1251 文件应可使用 CP1251 进行解码
        try:
            decoded1 = content1.decode("cp1251")
            assert "Измененный текст в CP1251" in decoded1
        except UnicodeDecodeError:
            pytest.fail("CP1251 file was not saved with the correct encoding")

        # UTF-8 文件应该可以用 UTF-8 解码
        try:
            decoded2 = content2.decode("utf-8")
            assert "Измененный текст в UTF-8" in decoded2
        except UnicodeDecodeError:
            pytest.fail("UTF-8 file was not saved with the correct encoding")

    finally:
        # 清理
        try:
            os.unlink(path1)
            os.unlink(path2)
        except FileNotFoundError:
            pass
