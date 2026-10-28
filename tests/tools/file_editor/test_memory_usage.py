"""测试文件编辑器中的内存使用情况。"""

import gc
import os
import tempfile
from pathlib import Path

import psutil
import pytest
from filelock import FileLock

from openhands.tools.file_editor import file_editor
from tests.platform_utils import (
    can_fork_test_process,
    set_address_space_limit_if_available,
)

from .conftest import assert_successful_result


# 在支持的地方应用分叉标记并在工作人员之间执行序列化。
pytestmark = [pytest.mark.usefixtures("isolate_memory_usage_tests")]
if can_fork_test_process():
    pytestmark.append(pytest.mark.forked)


@pytest.fixture(scope="function")
def isolate_memory_usage_tests():
    """防止内存敏感测试并行执行。"""
    lock_path = Path(tempfile.gettempdir()) / "openhands_str_replace_memory.lock"
    with FileLock(lock_path):
        yield


def test_file_read_memory_usage(temp_file):
    """测试读取大文件是否有效地使用内存。"""
    # 创建一个大文件 (~5MB) 以强调内存，同时保持在限制以下
    file_size_mb = 5.0
    line_size = 100  # 每行大约字节数
    num_lines = int((file_size_mb * 1024 * 1024) // line_size)

    print(f"\nCreating test file with {num_lines} lines...")
    with open(temp_file, "w") as f:
        for i in range(num_lines):
            f.write(f"Line {i}: " + "x" * (line_size - 10) + "\n")

    actual_size = os.path.getsize(temp_file) / (1024 * 1024)
    print(f"File created, size: {actual_size:.2f} MB")

    # 强制 Python 释放文件句柄并清除缓冲区
    gc.collect()

    # 预热编辑器，以便将导入/缓存分配排除在测量之外
    warmup_result = file_editor(
        command="view",
        path=temp_file,
        view_range=[1, 1],
    )
    assert_successful_result(warmup_result)
    del warmup_result
    gc.collect()

    # 获取初始内存使用情况
    initial_memory = psutil.Process(os.getpid()).memory_info().rss
    print(f"Initial memory usage: {initial_memory / 1024 / 1024:.2f} MB")

    # 测试阅读特定行
    try:
        result = file_editor(
            command="view",
            path=temp_file,
            view_range=[5000, 5100],  # 从中间读取100行
        )
    except Exception as e:
        print(f"\nError during file read: {str(e)}")
        raise

    # 在测量之前拉出输出并删除参考以鼓励 GC
    assert_successful_result(result)
    content = result.text
    del result
    gc.collect()

    # 读取后检查内存使用情况
    current_memory = psutil.Process(os.getpid()).memory_info().rss
    memory_growth = current_memory - initial_memory
    print(
        f"Memory growth after reading 100 lines: {memory_growth / 1024 / 1024:.2f} MB"
    )

    # 内存增长应较小，因为我们只读取100行。允许一些额外开销，但应远小于文件大小。增加以
    # 考虑chardet的内存使用情况和环境差异
    #
    max_growth_mb = 6  # 考虑正常变化，最大增长 6MB
    assert memory_growth <= max_growth_mb * 1024 * 1024, (
        f"Memory growth too high: {memory_growth / 1024 / 1024:.2f} MB "
        f"(limit: {max_growth_mb} MB)"
    )

    # 验证我们得到了正确的行
    line_count = content.count("\n")
    assert line_count >= 99, f"Should have read at least 99 lines, got {line_count}"
    assert "Line 5000:" in content, "Should contain the first requested line"
    assert "Line 5099:" in content, "Should contain the last requested line"

    print("Test completed successfully")


@pytest.mark.skipif(
    os.environ.get("CI", "false").lower() == "true",
    reason="Skip memory leak test on CI since it will break due to memory limits",
)
def test_file_editor_memory_leak(temp_file):
    """测试以演示多个文件编辑期间的内存增长。"""
    print("\nStarting memory leak test...")

    # 创建足够大的初始内容以供测试但不会压倒将总文件大小保持在 10MB 以下以避免文件验证错
    # 误
    #
    base_content = (
        "Initial content with some reasonable length to make the file larger\n"
    )
    content = base_content * 100
    print(f"\nCreating initial file with {len(content)} bytes")
    with open(temp_file, "w") as f:
        f.write(content)
    print(f"Initial file created, size: {os.path.getsize(temp_file) / 1024:.1f} KB")

    # 强制 Python 释放文件句柄并清除缓冲区
    gc.collect()

    # 预热编辑器，以便将导入/缓存分配排除在测量之外
    warmup_result = file_editor(
        command="view",
        path=temp_file,
        view_range=[1, 1],
    )
    assert_successful_result(warmup_result)
    del warmup_result
    gc.collect()

    # 将内存限制设置为 170MB，以便更容易发现问题
    memory_limit = 170 * 1024 * 1024  # 170MB（字节）
    if set_address_space_limit_if_available(memory_limit):
        print("Memory limit set successfully")
    else:
        print("Address-space memory limit not available in this environment")

    initial_memory = psutil.Process(os.getpid()).memory_info().rss
    print(f"\nInitial memory usage: {initial_memory / 1024 / 1024:.2f} MB")

    # 存储内存读数以供分析
    memory_readings = []
    file_size_mb = 0.0

    try:
        # 以合理的内容大小进行编辑
        for i in range(500):  # 减少迭代以避免 CI 中的内存问题
            # 为每次编辑创建内容 - 保持较小的内容以避免文件大小限制
            old_content = f"content_{i}\n" * 5  # 每次编辑 5 行
            new_content = f"content_{i + 1}\n" * 5

            # 我们将替换内容以保持文件大小稳定，而不是附加
            with open(temp_file) as f:
                current_content = f.read()

            # 在随机位置插入 old_content，同时保持文件大小稳定
            insert_pos = len(current_content) // 2
            new_file_content = (
                current_content[:insert_pos]
                + old_content
                + current_content[insert_pos + len(old_content) :]
            )
            with open(temp_file, "w") as f:
                f.write(new_file_content)

            # 执行编辑
            try:
                if i == 0:
                    print(
                        f"\nInitial file size: "
                        f"{os.path.getsize(temp_file) / (1024 * 1024):.2f} MB"
                    )
                    print(f"Sample content to replace: {old_content[:100]}...")
                result = file_editor(
                    command="str_replace",
                    path=temp_file,
                    old_str=old_content,
                    new_str=new_content,
                )
                if i == 0:
                    content_str = result.text
                    print(f"First edit result: {content_str[:200]}...")
            except Exception as e:
                print(f"\nError during edit {i}:")
                print(f"File size: {os.path.getsize(temp_file) / (1024 * 1024):.2f} MB")
                print(f"Error: {str(e)}")
                raise

            if i % 25 == 0:  # 更频繁地检查
                try:
                    current_memory = psutil.Process(os.getpid()).memory_info().rss
                    memory_mb = current_memory / 1024 / 1024
                    memory_readings.append(memory_mb)
                except (psutil.Error, MemoryError, OSError) as e:
                    # 在资源受限的环境中（如 CI），psutil 可能会失败跳过内存监控但继续测
                    # 试
                    #
                    print(f"Warning: Could not get memory info: {e}")
                    continue

                # 获取当前文件大小
                file_size_mb = os.path.getsize(temp_file) / (1024 * 1024)

                # 仅当我们有内存读数时才进行内存分析
                if memory_readings:
                    print(f"\nIteration {i}:")
                    print(f"Memory usage: {memory_mb:.2f} MB")
                    print(f"File size: {file_size_mb:.2f} MB")

                    # 计算内存增长
                    memory_growth = current_memory - initial_memory
                    growth_percent = (memory_growth / initial_memory) * 100
                    print(
                        f"Memory growth: {memory_growth / 1024 / 1024:.2f} MB "
                        f"({growth_percent:.1f}%)"
                    )

                    # 如果内存增长过高则失败
                    assert memory_growth < memory_limit, (
                        f"Memory growth exceeded limit after {i} edits. "
                        f"Growth: {memory_growth / 1024 / 1024:.2f} MB"
                    )

                    # 检查生长模式是否一致
                    if len(memory_readings) >= 3:
                        # 计算最近 3 个读数之间的增长率
                        growth_rate = (memory_readings[-1] - memory_readings[-3]) / 2
                        print(f"Recent growth rate: {growth_rate:.2f} MB per 50 edits")

                        # 如果我们看到持续增长超过阈值，则失败允许初始分配和 CI 环境变化
                        # 有更多增长
                        #
                        max_growth = 3 if i < 100 else 2  # 每 50 次编辑 MB（增加容差）
                        if growth_rate > max_growth:
                            pytest.fail(
                                f"Consistent memory growth detected: "
                                f"{growth_rate:.2f} MB per 50 edits after {i} edits"
                            )
                else:
                    print(
                        f"\nIteration {i}: File size: {file_size_mb:.2f} MB "
                        f"(memory monitoring disabled)"
                    )

    except MemoryError:
        pytest.fail("Memory limit exceeded - possible memory leak detected")
    except Exception as e:
        if "Cannot allocate memory" in str(e):
            pytest.fail("Memory limit exceeded - possible memory leak detected")
        print(f"\nFinal file size: {file_size_mb:.2f} MB")
        raise

    # 打印最终统计数据
    print("\nMemory usage statistics:")
    if memory_readings:
        print(f"Initial memory: {memory_readings[0]:.2f} MB")
        print(f"Final memory: {memory_readings[-1]:.2f} MB")
        print(f"Total growth: {(memory_readings[-1] - memory_readings[0]):.2f} MB")
    else:
        print("Memory monitoring was disabled due to resource constraints")
    print(f"Final file size: {file_size_mb:.2f} MB")
