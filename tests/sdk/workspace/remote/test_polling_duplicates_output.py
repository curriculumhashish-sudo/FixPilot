"""测试远程工作区轮询中的输出重复数据删除。

这些测试验证 RemoteWorkspaceMixin 中的轮询循环是否使用 order__gt 过滤正确地仅获取新事
件。

错误上下文：
- 以前，bash 事件搜索 API 在每次调用时返回全部个事件
- 如果没有过滤，输出会重复：A + B + A + B + C + ...
- 这导致轨迹捕获中base64解码失败

修复：
- 客户端现在传递 order__gt 参数以仅获取新事件
- API 过滤顺序 > last_order 的事件

在生产中观察到的错误消息：
- “无效的 Base64 编码字符串：数据字符数 (5352925) 不能多于 1 且大于 4 的倍数”
- “填充不正确”
"""

import base64
from unittest.mock import Mock, patch

import pytest

from openhands.sdk.workspace.remote.remote_workspace_mixin import RemoteWorkspaceMixin


class RemoteWorkspaceMixinHelper(RemoteWorkspaceMixin):
    """出于测试目的测试 RemoteWorkspaceMixin 的实现。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class TestPollingDeduplication:
    """在轮询循环中使用 order__gt 测试正确的事件过滤。"""

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_polling_should_not_duplicate_events_across_iterations(self, mock_time):
        """测试轮询是否使用 order__gt 仅获取新事件。

        当命令通过多次轮询迭代生成输出时，客户端应使用 order__gt 来仅请求比上次处理的
        事件更新的事件。

        预期正确输出： chunk1 + chunk2 + chunk3
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1, 2, 3, 4]
        mock_time.sleep = Mock()

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-123"}

        # 轮询 1：第一次轮询（无 order__gt），返回块 1
        poll_response_1 = Mock()
        poll_response_1.raise_for_status = Mock()
        poll_response_1.json.return_value = {
            "items": [
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "CHUNK1",
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 2：当 order__gt=0 时，API 仅返回块 2
        poll_response_2 = Mock()
        poll_response_2.raise_for_status = Mock()
        poll_response_2.json.return_value = {
            "items": [
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": "CHUNK2",
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 3：当 order__gt=1 时，API 仅返回块 3
        poll_response_3 = Mock()
        poll_response_3.raise_for_status = Mock()
        poll_response_3.json.return_value = {
            "items": [
                {
                    "id": "event-3",
                    "kind": "BashOutput",
                    "order": 2,
                    "stdout": "CHUNK3",
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator("test_command", None, 30.0)

        next(generator)
        generator.send(start_response)
        generator.send(poll_response_1)
        generator.send(poll_response_2)

        try:
            generator.send(poll_response_3)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 输出应该正好是 3 个块，没有重复
        assert result.stdout == "CHUNK1CHUNK2CHUNK3", (
            f"Expected 'CHUNK1CHUNK2CHUNK3' but got '{result.stdout}'. "
            "Events should be deduplicated across poll iterations."
        )

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_base64_output_should_decode_correctly(self, mock_time):
        """测试 Base64 输出是否未因轮询而损坏。

        此测试验证生产错误的修复：
        - “填充不正确”
        - “无效的 Base64 编码字符串”

        轨迹捕获运行：tar -czf - 工作区 | base64 然后解码为 base64.b64decode(标准输出
        )

        通过 order__gt 过滤，每个轮询仅返回新事件。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1, 2, 3, 4]
        mock_time.sleep = Mock()

        # 创建模拟 tar 输出的 Base64 数据
        original_data = b"Test data!" * 5
        base64_encoded = base64.b64encode(original_data).decode("ascii")

        # 分成块（模拟分块传输）
        chunk1 = base64_encoded[:17]
        chunk2 = base64_encoded[17:34]
        chunk3 = base64_encoded[34:]

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-456"}

        # 轮询 1：第一次轮询，返回块 1
        poll_response_1 = Mock()
        poll_response_1.raise_for_status = Mock()
        poll_response_1.json.return_value = {
            "items": [
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": chunk1,
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 2：当 order__gt=0 时，API 仅返回块 2
        poll_response_2 = Mock()
        poll_response_2.raise_for_status = Mock()
        poll_response_2.json.return_value = {
            "items": [
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": chunk2,
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 3：当 order__gt=1 时，API 仅返回块 3
        poll_response_3 = Mock()
        poll_response_3.raise_for_status = Mock()
        poll_response_3.json.return_value = {
            "items": [
                {
                    "id": "event-3",
                    "kind": "BashOutput",
                    "order": 2,
                    "stdout": chunk3,
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator(
            "tar -czf - workspace | base64", None, 30.0
        )

        next(generator)
        generator.send(start_response)
        generator.send(poll_response_1)
        generator.send(poll_response_2)

        try:
            generator.send(poll_response_3)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 输出应该是正确解码的有效 base64
        assert result.stdout == base64_encoded, (
            f"Expected valid base64 '{base64_encoded}' but got '{result.stdout}'. "
            "Output should not be corrupted by duplicate events."
        )

        # 验证它是否确实解码
        decoded = base64.b64decode(result.stdout)
        assert decoded == original_data

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_base64_decode_succeeds_with_order_filtering(self, mock_time):
        """使用 order__gt 过滤测试 Base64 解码是否正常工作。

        此测试验证 order__gt 修复是否可以防止生产日志中出现的错误：
        - 来自 base64.b64decode() 的“填充不正确”错误

        轨迹捕获代码运行：
            tar -czf - 工作区 | base64
        然后解码：
            base64.b64decode(stdout)

        通过 order__gt 过滤，输出不会重复并正确解码。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1, 2, 3, 4]
        mock_time.sleep = Mock()

        # 创建 base64 数据
        original_data = b"Test data!" * 5
        base64_encoded = base64.b64encode(original_data).decode("ascii")

        chunk1 = base64_encoded[:17]  # 17 个字符
        chunk2 = base64_encoded[17:34]  # 17 个字符
        chunk3 = base64_encoded[34:]  # 34 个字符

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-789"}

        # 轮询 1：第一次轮询，返回块 1
        poll_response_1 = Mock()
        poll_response_1.raise_for_status = Mock()
        poll_response_1.json.return_value = {
            "items": [
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": chunk1,
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 2：当 order__gt=0 时，API 仅返回块 2
        poll_response_2 = Mock()
        poll_response_2.raise_for_status = Mock()
        poll_response_2.json.return_value = {
            "items": [
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": chunk2,
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 轮询 3：当 order__gt=1 时，API 仅返回块 3
        poll_response_3 = Mock()
        poll_response_3.raise_for_status = Mock()
        poll_response_3.json.return_value = {
            "items": [
                {
                    "id": "event-3",
                    "kind": "BashOutput",
                    "order": 2,
                    "stdout": chunk3,
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator(
            "tar -czf - workspace | base64", None, 30.0
        )

        next(generator)
        generator.send(start_response)
        generator.send(poll_response_1)
        generator.send(poll_response_2)

        try:
            generator.send(poll_response_3)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 输出应为有效的 base64（68 个字符，68 % 4 = 0）
        assert result.stdout == base64_encoded, (
            f"Expected '{base64_encoded}' but got '{result.stdout}'"
        )

        # 解码应该成功（在修复之前，这会因“填充不正确”而失败）
        decoded = base64.b64decode(result.stdout)
        assert decoded == original_data, (
            f"base64.b64decode() should succeed and return original data. "
            f"Got {len(result.stdout)} chars (length % 4 = {len(result.stdout) % 4})"
        )

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_assertion_fires_on_duplicate_events(self, mock_time):
        """测试如果收到重复事件是否引发 AssertionError。

        这是一个安全检查 - API 应该通过 order__gt 过滤重复项，但如果没有，客户端应检
        测并快速失败，而不是默默地损坏输出。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1, 2, 3]
        mock_time.sleep = Mock()

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-999"}

        # 民意调查 1：返回 event-1
        poll_response_1 = Mock()
        poll_response_1.raise_for_status = Mock()
        poll_response_1.json.return_value = {
            "items": [
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "CHUNK1",
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 民意调查 2：API bug - 再次返回 event-1（重复！）
        poll_response_2 = Mock()
        poll_response_2.raise_for_status = Mock()
        poll_response_2.json.return_value = {
            "items": [
                {
                    "id": "event-1",  # 重复！
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "CHUNK1",
                    "stderr": None,
                    "exit_code": None,
                },
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": "CHUNK2",
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator("test_command", None, 30.0)

        next(generator)
        generator.send(start_response)
        generator.send(poll_response_1)

        # 断言被捕获并返回错误结果
        try:
            generator.send(poll_response_2)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 应返回带有重复事件消息的错误结果
        assert result.exit_code == -1
        assert "Duplicate event received: event-1" in result.stderr

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_single_poll_works_correctly(self, mock_time):
        """测试单个轮询迭代是否正常工作。

        当命令在一次轮询内完成时，就没有重复的机会。 这应该总是有效。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1]
        mock_time.sleep = Mock()

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-789"}

        # 单次轮询返回带有退出代码的所有事件
        poll_response = Mock()
        poll_response.raise_for_status = Mock()
        poll_response.json.return_value = {
            "items": [
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "CHUNK1",
                    "stderr": None,
                    "exit_code": None,
                },
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": "CHUNK2",
                    "stderr": None,
                    "exit_code": None,
                },
                {
                    "id": "event-3",
                    "kind": "BashOutput",
                    "order": 2,
                    "stdout": "CHUNK3",
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator("fast_command", None, 30.0)

        next(generator)
        generator.send(start_response)

        try:
            generator.send(poll_response)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        assert result.stdout == "CHUNK1CHUNK2CHUNK3"

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_mixed_event_types_with_kind_filtering(self, mock_time):
        """测试混合事件类型 (BashCommand + BashOutput) 是否正常工作。

        该测试验证：
        1. kind__eq=BashOutput 过滤器应用于服务器端
        2. 如果返回 BashCommand 个事件（API 不过滤），则忽略
        3. 仅为 stdout/stderr 处理 BashOutput 事件

        重复检测仅适用于 BashOutput 事件，因为 BashCommand 事件没有顺序字段。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1, 2, 3, 4]
        mock_time.sleep = Mock()

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-mixed"}

        # 轮询 1：返回 BashCommand（无顺序）+ BashOutput（顺序=0）
        # 注意：当kind__eq=BashOutput时，API应该只返回BashOutput
        # 但我们测试了无论如何都可能返回 BashCommand 的情况
        poll_response_1 = Mock()
        poll_response_1.raise_for_status = Mock()
        poll_response_1.json.return_value = {
            "items": [
                {
                    "id": "cmd-mixed",
                    "kind": "BashCommand",
                    "command": "echo test",
                    # BashCommand 事件没有订单字段
                },
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "CHUNK1",
                    "stderr": None,
                    "exit_code": None,
                },
            ]
        }

        # 民意调查2：再次返回BashCommand（无订单）+ BashOutput（订单=1）BashCommand将再
        # 次返回，因为它没有订单字段
        #
        poll_response_2 = Mock()
        poll_response_2.raise_for_status = Mock()
        poll_response_2.json.return_value = {
            "items": [
                {
                    "id": "cmd-mixed",
                    "kind": "BashCommand",
                    "command": "echo test",
                },
                {
                    "id": "event-2",
                    "kind": "BashOutput",
                    "order": 1,
                    "stdout": "CHUNK2",
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator("echo test", None, 30.0)

        next(generator)
        generator.send(start_response)
        generator.send(poll_response_1)

        try:
            generator.send(poll_response_2)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 输出应仅包含 BashOutput 个事件，不得重复
        assert result.stdout == "CHUNK1CHUNK2", (
            f"Expected 'CHUNK1CHUNK2' but got '{result.stdout}'. "
            "BashCommand events should be ignored, only BashOutput processed."
        )
        assert result.exit_code == 0

    @patch("openhands.sdk.workspace.remote.remote_workspace_mixin.time")
    def test_bash_command_events_are_ignored(self, mock_time):
        """测试 BashCommand 事件是否被正确忽略。

        BashCommand 事件没有 stdout/stderr/exit_code 字段，因此在处理过程中应跳过它们
        。
        """
        mixin = RemoteWorkspaceMixinHelper(
            host="http://localhost:8000", working_dir="workspace"
        )

        mock_time.time.side_effect = [0, 1]
        mock_time.sleep = Mock()

        start_response = Mock()
        start_response.raise_for_status = Mock()
        start_response.json.return_value = {"id": "cmd-ignore"}

        # 包含 BashCommand 和 BashOutput 事件的单次轮询
        poll_response = Mock()
        poll_response.raise_for_status = Mock()
        poll_response.json.return_value = {
            "items": [
                {
                    "id": "cmd-ignore",
                    "kind": "BashCommand",
                    "command": "ls -la",
                },
                {
                    "id": "event-1",
                    "kind": "BashOutput",
                    "order": 0,
                    "stdout": "file1.txt\nfile2.txt\n",
                    "stderr": None,
                    "exit_code": 0,
                },
            ]
        }

        generator = mixin._execute_command_generator("ls -la", None, 30.0)

        next(generator)
        generator.send(start_response)

        try:
            generator.send(poll_response)
            pytest.fail("Generator should have stopped")
        except StopIteration as e:
            result = e.value

        # 只有 BashOutput 内容应该出现在标准输出中
        assert result.stdout == "file1.txt\nfile2.txt\n"
        assert result.exit_code == 0
