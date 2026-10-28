"""测试顺序 execute_command 调用的命令输出隔离。

该测试验证了执行多个命令顺序执行时，生成的输出是隔离的，确保每个命令的结果只包含自己
的输出，而没有被前一个命令污染。
"""

from unittest.mock import Mock

from openhands.sdk.workspace.remote.remote_workspace_mixin import RemoteWorkspaceMixin


class _RemoteWorkspaceMixinForTest(RemoteWorkspaceMixin):
    """用于测试目的的RemoteWorkspaceMixin的具体实现。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


def test_multiple_commands_use_different_command_ids():
    """测试顺序命令在 API 参数中使用不同的命令 ID。

    验证了当多个命令按顺序执行时，每个命令都使用自己的 command_id 进行过滤事件，从而
    防止先前命令的输出污染。
    """
    mixin = _RemoteWorkspaceMixinForTest(
        host="http://localhost:8000", working_dir="/workspace"
    )

    # ==== 第一个命令 ====
    start_response_1 = Mock()
    start_response_1.raise_for_status = Mock()
    start_response_1.json.return_value = {"id": "cmd-001"}

    generator_1 = mixin._execute_command_generator("ls -l /workspace", None, 30.0)

    # 启动第一个命令
    start_kwargs_1 = next(generator_1)
    assert start_kwargs_1["method"] == "POST"

    # 获取第一个命令的轮询请求
    poll_kwargs_1 = generator_1.send(start_response_1)

    # 通过 cmd-001 验证第一个命令过滤器
    params_1 = poll_kwargs_1["params"]
    assert "command_id__eq" in params_1
    assert params_1["command_id__eq"] == "cmd-001", (
        "First command should filter events by its command ID 'cmd-001'"
    )

    # ==== 第二条命令 ====
    start_response_2 = Mock()
    start_response_2.raise_for_status = Mock()
    start_response_2.json.return_value = {"id": "cmd-002"}

    generator_2 = mixin._execute_command_generator("ls -l ./", None, 30.0)

    # 开始第二个命令
    start_kwargs_2 = next(generator_2)
    assert start_kwargs_2["method"] == "POST"

    # 获取第二个命令的轮询请求
    poll_kwargs_2 = generator_2.send(start_response_2)

    # 通过 cmd-002 (不 cmd-001) 验证第二个命令过滤器
    params_2 = poll_kwargs_2["params"]
    assert "command_id__eq" in params_2
    assert params_2["command_id__eq"] == "cmd-002", (
        "Second command should filter events by its OWN command ID 'cmd-002', "
        "not by the first command's ID. This ensures outputs are isolated."
    )

    # 验证两个命令使用不同的命令 ID
    assert params_1["command_id__eq"] != params_2["command_id__eq"], (
        "Sequential commands must use different command IDs to prevent "
        "output contamination"
    )


def test_command_id_filter_params_structure():
    """测试 command_id__eq 和 sort_order 是否是单独的参数。

    验证 API 搜索参数是否正确结构化，具有 command_id 过滤和 sort_order 的单独键，确保
    通过命令 ID 过滤事件。
    """
    mixin = _RemoteWorkspaceMixinForTest(
        host="http://localhost:8000", working_dir="/workspace"
    )

    start_response = Mock()
    start_response.raise_for_status = Mock()
    start_response.json.return_value = {"id": "cmd-123"}

    generator = mixin._execute_command_generator("echo test", None, 30.0)

    # 启动命令
    start_kwargs = next(generator)
    assert start_kwargs["method"] == "POST"

    # 发送开始响应，获取轮询请求
    poll_kwargs = generator.send(start_response)

    # 验证 params dict 具有用于过滤和排序的单独键
    params = poll_kwargs["params"]

    print(f"\nActual params: {params}")
    print(f"Params keys: {list(params.keys())}")

    # 验证params结构是否正确
    assert "command_id__eq" in params, (
        "Missing command_id__eq param for filtering events by command ID"
    )
    assert params["command_id__eq"] == "cmd-123", (
        "The command_id__eq param should filter by the command ID 'cmd-123'"
    )
    assert "sort_order" in params, (
        "Missing sort_order param for sorting events by timestamp"
    )
    assert params["sort_order"] == "TIMESTAMP", (
        "The sort_order param should be set to 'TIMESTAMP'"
    )
