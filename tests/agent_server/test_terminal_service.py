"""对 BashEventService bash 命令执行的全面测试。"""

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.models import BashCommand, BashOutput, ExecuteBashRequest
from openhands.agent_server.pub_sub import Subscriber


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="BashEventService tests require the Unix terminal backend.",
)


@pytest.fixture
def bash_service():
    """创建一个 BashEventService 实例用于测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        yield BashEventService(
            bash_events_dir=temp_path / "bash_events",
        )


class EventCollector(Subscriber):
    """收集所有事件的测试订阅者。"""

    def __init__(self):
        self.events: list[Any] = []
        self.commands: list[Any] = []
        self.outputs: list[Any] = []

    async def __call__(self, event):
        self.events.append(event)
        if isinstance(event, BashCommand):
            self.commands.append(event)
        elif isinstance(event, BashOutput):
            self.outputs.append(event)


@pytest.mark.asyncio
async def test_single_output_command(bash_service):
    """测试产生单个输出的 bash 命令。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 简单的 echo 命令 - 应该产生单个输出
    request = ExecuteBashRequest(command='echo "Hello World"', cwd="/tmp")
    command, task = await bash_service.start_bash_command(request)

    # 等待命令完成
    await task

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) == 1

    # 验证命令事件
    cmd_event = collector.commands[0]
    assert cmd_event.id == command.id
    assert cmd_event.command == 'echo "Hello World"'
    assert cmd_event.cwd == "/tmp"

    # 验证输出事件
    output_event = collector.outputs[0]
    assert output_event.command_id == command.id
    assert output_event.order == 0
    assert output_event.exit_code == 0
    assert output_event.stdout == "Hello World\n"
    assert output_event.stderr is None

    # 验证可以从存储中检索事件
    retrieved_cmd = await bash_service.get_bash_event(command.id.hex)
    assert retrieved_cmd is not None
    assert retrieved_cmd.id == command.id

    retrieved_output = await bash_service.get_bash_event(output_event.id.hex)
    assert retrieved_output is not None
    assert retrieved_output.id == output_event.id


@pytest.mark.asyncio
async def test_multiple_output_command(bash_service):
    """测试产生多条输出的 bash 命令。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 产生多行输出的命令
    request = ExecuteBashRequest(
        command='echo "Line 1"; echo "Line 2"; echo "Line 3"', cwd="/tmp"
    )
    command, task = await bash_service.start_bash_command(request)

    # 等待命令完成
    await task

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) >= 1  # 可以分成多个输出

    # 验证命令事件
    cmd_event = collector.commands[0]
    assert cmd_event.id == command.id
    assert "echo" in cmd_event.command

    # 验证所有输出都属于同一命令
    for output in collector.outputs:
        assert output.command_id == command.id
        assert output.exit_code == 0
        assert output.stderr is None

    # 验证输出的顺序是否正确
    orders = [output.order for output in collector.outputs]
    assert orders == sorted(orders)

    # 合并所有标准输出以验证完整的输出
    combined_stdout = "".join(
        output.stdout or ""
        for output in sorted(collector.outputs, key=lambda x: x.order)
    )
    assert "Line 1" in combined_stdout
    assert "Line 2" in combined_stdout
    assert "Line 3" in combined_stdout


@pytest.mark.asyncio
async def test_command_with_stderr(bash_service):
    """测试产生 stderr 输出的 bash 命令。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 写入 stderr 的命令
    request = ExecuteBashRequest(
        command='echo "stdout message" && echo "stderr message" >&2', cwd="/tmp"
    )
    command, task = await bash_service.start_bash_command(request)

    # 等待命令完成
    await task

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) >= 1

    # 使用 stdout 和 stderr 查找输出
    stdout_outputs = [o for o in collector.outputs if o.stdout]
    stderr_outputs = [o for o in collector.outputs if o.stderr]

    # 应该同时具有 stdout 和 stderr
    assert len(stdout_outputs) >= 1
    assert len(stderr_outputs) >= 1

    # 验证内容
    combined_stdout = "".join(o.stdout or "" for o in stdout_outputs)
    combined_stderr = "".join(o.stderr or "" for o in stderr_outputs)

    assert "stdout message" in combined_stdout
    assert "stderr message" in combined_stderr

    # 所有输出的退出代码应为 0
    for output in collector.outputs:
        assert output.exit_code == 0


@pytest.mark.asyncio
async def test_command_with_error_exit_code(bash_service):
    """测试退出并显示错误代码的 bash 命令。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 因错误而退出的命令
    request = ExecuteBashRequest(command="exit 42", cwd="/tmp")
    _, task = await bash_service.start_bash_command(request)

    # 等待命令完成
    await task

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) >= 1

    # 验证退出代码是否已传播
    for output in collector.outputs:
        assert output.exit_code == 42


@pytest.mark.asyncio
async def test_command_timeout(bash_service):
    """测试超时的 bash 命令。"""
    import time

    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 应该超时的命令（睡眠时间长于超时）
    request = ExecuteBashRequest(command="sleep 10", cwd="/tmp", timeout=1)
    start_time = time.time()
    _, task = await bash_service.start_bash_command(request)

    # 等待超时发生
    await task
    end_time = time.time()

    # 验证命令是否快速终止（在 3 秒内以允许开销）
    execution_time = end_time - start_time
    assert execution_time < 3, f"Command took {execution_time:.2f}s, expected < 3s"

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) >= 1

    # 验证命令是否正确启动
    cmd_event = collector.commands[0]
    assert cmd_event.command == "sleep 10"

    # 验证超时导致退出代码 -1
    final_output = collector.outputs[-1]  # 最后的输出应该有退出代码
    assert final_output.exit_code == -1, (
        f"Expected exit code -1, got {final_output.exit_code}"
    )


@pytest.mark.asyncio
async def test_large_output_chunking(bash_service):
    """测试大输出是否被正确分块。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 使用应该在任何地方都适用的简单命令生成大量输出创建大于 MAX_CONTENT_CHAR_LENGTH (
    # 1MB) 的字符串
    #
    large_size = 1024 * 1024 + 1000  # 略高于1MB
    request = ExecuteBashRequest(command=f'yes "x" | head -c {large_size}', cwd="/tmp")
    command, task = await bash_service.start_bash_command(request)

    # 等待命令完成
    await task

    # 验证事件已发布
    assert len(collector.commands) == 1
    assert len(collector.outputs) >= 1  # 如果足够大，应该分块

    # 验证所有块都属于同一命令并且已排序
    for i, output in enumerate(collector.outputs):
        assert output.command_id == command.id
        assert output.order == i
        # 只有最终输出设置为exit_code，中间输出可能为None
        if i == len(collector.outputs) - 1:
            assert output.exit_code == 0

    # 验证总输出大小是否足够
    total_stdout = "".join(
        output.stdout or ""
        for output in sorted(collector.outputs, key=lambda x: x.order)
    )
    assert len(total_stdout) > 1000  # 应该有可观的产出


@pytest.mark.asyncio
async def test_concurrent_commands(bash_service):
    """测试多个并发 bash 命令。"""
    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 同时启动多个命令
    requests = [
        ExecuteBashRequest(command=f'echo "Command {i}"', cwd="/tmp") for i in range(3)
    ]

    # 启动所有命令
    results = await asyncio.gather(
        *[bash_service.start_bash_command(req) for req in requests]
    )

    # 等待全部完成
    await asyncio.gather(*[task for _, task in results])

    # 验证所有命令均已执行
    assert len(collector.commands) == 3
    assert len(collector.outputs) >= 3

    # 验证每个命令都有相应的输出
    command_ids = {cmd.id for cmd, _ in results}
    output_command_ids = {output.command_id for output in collector.outputs}
    assert command_ids == output_command_ids


@pytest.mark.asyncio
async def test_event_persistence(bash_service):
    """测试事件是否正确地已持久化到文件。"""
    # 执行命令
    request = ExecuteBashRequest(command='echo "persistence test"', cwd="/tmp")
    command, task = await bash_service.start_bash_command(request)

    # 等待完成
    await task

    # 验证命令是否可以检索
    retrieved_cmd = await bash_service.get_bash_event(command.id.hex)
    assert retrieved_cmd is not None
    assert retrieved_cmd.command == 'echo "persistence test"'

    # 验证批量检索工作
    batch_results = await bash_service.batch_get_bash_events([command.id.hex])
    assert len(batch_results) == 1
    assert batch_results[0] is not None
    assert batch_results[0].id == command.id


@pytest.mark.asyncio
async def test_search_bash_events(bash_service):
    """测试搜索 bash 事件。"""
    # 执行多个命令
    requests = [
        ExecuteBashRequest(command='echo "first"', cwd="/tmp"),
        ExecuteBashRequest(command='echo "second"', cwd="/tmp"),
    ]

    results = await asyncio.gather(
        *[bash_service.start_bash_command(req) for req in requests]
    )

    # 等待完成
    await asyncio.gather(*[task for _, task in results])

    # 搜索活动
    page = await bash_service.search_bash_events()
    assert len(page.items) >= 4  # 至少 2 个命令 + 2 个输出

    # 验证我们可以找到命令和输出
    command_events = [e for e in page.items if isinstance(e, BashCommand)]
    output_events = [e for e in page.items if isinstance(e, BashOutput)]

    assert len(command_events) >= 2
    assert len(output_events) >= 2


@pytest.mark.asyncio
async def test_service_lifecycle(bash_service):
    """测试服务生命周期方法。"""
    # 测试上下文管理器用法
    async with bash_service:
        request = ExecuteBashRequest(command='echo "lifecycle test"', cwd="/tmp")
        command, task = await bash_service.start_bash_command(request)
        await task

    # 服务应在上下文管理器验证我们仍然可以检索已持久化事件后关闭
    #
    retrieved = await bash_service.get_bash_event(command.id.hex)
    assert retrieved is not None


@pytest.mark.asyncio
async def test_clear_all_events_empty_storage(bash_service):
    """当存储为空时测试清除事件。"""
    # 从空存储中清除事件
    count = await bash_service.clear_all_events()
    assert count == 0


@pytest.mark.asyncio
async def test_clear_all_events_with_data(bash_service):
    """当存储包含数据时测试清除事件。"""
    # 执行一些命令来创建事件
    requests = [
        ExecuteBashRequest(command='echo "first"', cwd="/tmp"),
        ExecuteBashRequest(command='echo "second"', cwd="/tmp"),
    ]

    results = await asyncio.gather(
        *[bash_service.start_bash_command(req) for req in requests]
    )

    # 等待完成
    await asyncio.gather(*[task for _, task in results])

    # 清除前验证事件是否存在
    page = await bash_service.search_bash_events()
    initial_count = len(page.items)
    assert initial_count > 0  # 至少应该有一些事件

    # 清除所有事件
    cleared_count = await bash_service.clear_all_events()
    assert cleared_count == initial_count

    # 验证事件已消失
    page_after = await bash_service.search_bash_events()
    assert len(page_after.items) == 0

    # 验证无法检索单个事件
    for cmd, _ in results:
        retrieved = await bash_service.get_bash_event(cmd.id.hex)
        assert retrieved is None


@pytest.mark.asyncio
async def test_clear_all_events_partial_failure(bash_service):
    """测试某些文件无法删除时的清除事件。"""
    # 执行命令来创建事件
    request = ExecuteBashRequest(command='echo "test"', cwd="/tmp")
    command, task = await bash_service.start_bash_command(request)
    await task

    # 验证事件是否存在
    retrieved = await bash_service.get_bash_event(command.id.hex)
    assert retrieved is not None

    # 清除事件（即使某些文件有问题也应该成功）
    cleared_count = await bash_service.clear_all_events()
    assert cleared_count >= 1  # 至少应该清除命令事件

    # 验证事件已消失
    page = await bash_service.search_bash_events()
    assert len(page.items) == 0


@pytest.mark.asyncio
async def test_search_with_filtering(bash_service):
    """测试使用 kind 和 command_id 过滤搜索 bash 事件。"""
    # 执行两条命令
    request1 = ExecuteBashRequest(command='echo "first"', cwd="/tmp")
    request2 = ExecuteBashRequest(command='echo "second"', cwd="/tmp")

    command1, task1 = await bash_service.start_bash_command(request1)
    command2, task2 = await bash_service.start_bash_command(request2)

    # 等待两者都完成
    await asyncio.gather(task1, task2)

    # 搜索所有事件 - 应该得到 4：2 个命令 + 2 个输出
    all_events = await bash_service.search_bash_events()
    assert len(all_events.items) >= 4

    # 按 kind="BashCommand" 过滤 - 应该只获取 2 个命令事件
    command_events = await bash_service.search_bash_events(kind__eq="BashCommand")
    assert len(command_events.items) == 2
    for event in command_events.items:
        assert isinstance(event, BashCommand)

    # 按 kind="BashOutput" 过滤 - 应该只获得 2 个输出事件
    output_events = await bash_service.search_bash_events(kind__eq="BashOutput")
    assert len(output_events.items) == 2
    for event in output_events.items:
        assert isinstance(event, BashOutput)

    # 按 command_id 过滤 - 应该仅获得 command1 的输出
    command1_outputs = await bash_service.search_bash_events(command_id__eq=command1.id)
    # 应该得到至少 1 个输出（可以分成多个）
    assert len(command1_outputs.items) >= 1
    for event in command1_outputs.items:
        if isinstance(event, BashOutput):
            assert event.command_id == command1.id

    # 组合过滤器：kind="BashOutput" AND command_id=command1.id
    command1_only_outputs = await bash_service.search_bash_events(
        kind__eq="BashOutput", command_id__eq=command1.id
    )
    assert len(command1_only_outputs.items) >= 1
    for event in command1_only_outputs.items:
        assert isinstance(event, BashOutput)
        assert event.command_id == command1.id


@pytest.mark.asyncio
async def test_search_pagination(bash_service):
    """测试 bash 事件搜索中的分页。"""
    # 执行多个命令以生成足够的事件
    requests = [
        ExecuteBashRequest(command=f'echo "command{i}"', cwd="/tmp") for i in range(5)
    ]

    results = await asyncio.gather(
        *[bash_service.start_bash_command(req) for req in requests]
    )

    # 等待全部完成
    await asyncio.gather(*[task for _, task in results])

    # 小限制搜索以测试分页
    page1 = await bash_service.search_bash_events(limit=3)
    assert len(page1.items) == 3
    assert page1.next_page_id is not None

    # 获取下一页
    page2 = await bash_service.search_bash_events(limit=3, page_id=page1.next_page_id)
    assert len(page2.items) > 0

    # 验证页面之间的项目是否不同
    page1_ids = {event.id for event in page1.items}
    page2_ids = {event.id for event in page2.items}
    assert len(page1_ids.intersection(page2_ids)) == 0  # 无重叠


@pytest.mark.asyncio
async def test_terminal_does_not_expose_session_api_key(bash_service, monkeypatch):
    """验证 bash 命令无法访问 SESSION_API_KEY。

    这是一个安全测试：SESSION_API_KEY 通过 SaaS API 向用户机密授予访问权限。 如果 LLM
     驱动的智能体可以通过终端命令读取此环境变量，则它可
    以渗透所有用户机密。 sanitized_env() 函数必须在将环境传递给子进程之前删除此变量。
    """
    # 模拟自动化服务将 SESSION_API_KEY 注入 os.environ
    secret_value = "super-secret-session-key-12345"
    monkeypatch.setenv("SESSION_API_KEY", secret_value)

    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    # 智能体可能会尝试通过 echo 或 printenv 读取环境变量
    request = ExecuteBashRequest(
        command='echo "SESSION_API_KEY=$SESSION_API_KEY"',
        cwd="/tmp",
    )
    command, task = await bash_service.start_bash_command(request)
    await task

    # 收集输出
    assert len(collector.outputs) >= 1
    combined_stdout = "".join(
        output.stdout or ""
        for output in sorted(collector.outputs, key=lambda x: x.order)
    )

    # 机密值应不出现在输出中
    assert secret_value not in combined_stdout, (
        f"SESSION_API_KEY was exposed to terminal command! Output: {combined_stdout}"
    )
    # 环境变量应该为空/未设置
    assert (
        "SESSION_API_KEY=$" in combined_stdout
        or "SESSION_API_KEY=\n" in combined_stdout
    ), f"SESSION_API_KEY should be unset in subprocess. Output: {combined_stdout}"


@pytest.mark.asyncio
async def test_terminal_does_not_expose_session_api_key_via_env_command(
    bash_service, monkeypatch
):
    """验证 SESSION_API_KEY 未出现在“env”命令输出中。

    智能体可能会运行“env”或“printenv”来发现可用的环境变量。 SESSION_API_KEY 不得可见
    。
    """
    secret_value = "another-secret-key-67890"
    monkeypatch.setenv("SESSION_API_KEY", secret_value)
    # 还设置一个安全变量来确认 env 命令有效
    monkeypatch.setenv("SAFE_TEST_VAR", "visible-value")

    collector = EventCollector()
    await bash_service.subscribe_to_events(collector)

    request = ExecuteBashRequest(
        command="env | grep -E '(SESSION_API_KEY|SAFE_TEST_VAR)' || true",
        cwd="/tmp",
    )
    command, task = await bash_service.start_bash_command(request)
    await task

    assert len(collector.outputs) >= 1
    combined_stdout = "".join(
        output.stdout or ""
        for output in sorted(collector.outputs, key=lambda x: x.order)
    )

    # SESSION_API_KEY 根本不应该出现
    assert "SESSION_API_KEY" not in combined_stdout, (
        f"SESSION_API_KEY appeared in env output! Output: {combined_stdout}"
    )
    assert secret_value not in combined_stdout, (
        f"Secret value leaked! Output: {combined_stdout}"
    )
    # 但 SAFE_TEST_VAR 应该可见（确认 env 命令有效）
    assert "SAFE_TEST_VAR=visible-value" in combined_stdout, (
        f"Safe var not found - env command may have failed. Output: {combined_stdout}"
    )
