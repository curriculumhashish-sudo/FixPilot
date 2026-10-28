from openhands.sdk.tool.builtins import BUILT_IN_TOOLS


def test_all_tools_property():
    # BUILT_IN_TOOLS包含工具类，所以我们需要实例化它们
    for tool_class in BUILT_IN_TOOLS:
        # 使用 .create() 方法创建工具实例
        tool_instances = tool_class.create()
        assert len(tool_instances) > 0, (
            f"{tool_class.__name__}.create() should return at least one tool"
        )

        # 检查所有实例的属性（通常只有一个）
        for tool in tool_instances:
            assert tool.description is not None
            assert tool.executor is not None
            assert tool.annotations is not None
            # 注释应具有特定提示内置工具应具有所有这些属性
            #
            assert tool.annotations.readOnlyHint
            assert not tool.annotations.destructiveHint
            assert tool.annotations.idempotentHint
            assert not tool.annotations.openWorldHint
