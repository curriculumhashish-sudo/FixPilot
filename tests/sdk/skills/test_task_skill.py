from openhands.sdk.skills import Skill, TaskTrigger
from openhands.sdk.skills.types import InputMetadata


def test_task_skill_prompt_appending():
    """使用 TaskTrigger 测试技能是否正确附加缺失的变量提示词。"""
    # 使用 TaskTrigger 和内容中的变量创建技能
    task_skill = Skill(
        name="test-task",
        content="Task with ${variable1} and ${variable2}",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
    )

    # 检查是否附加了提示词
    expected_prompt = (
        "\n\nIf the user didn't provide any of these variables, ask the user to "
        "provide them first before the agent can proceed with the task."
    )
    assert expected_prompt in task_skill.content

    # 使用TaskTrigger创建技能，不带变量但有输入
    task_skill_with_inputs = Skill(
        name="test-task-inputs",
        content="Task without variables",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
        inputs=[InputMetadata(name="input1", description="Test input")],
    )

    # 检查是否附加了提示词
    assert expected_prompt in task_skill_with_inputs.content

    # 使用 TaskTrigger 创建技能，无需变量或输入
    task_skill_no_vars = Skill(
        name="test-task-no-vars",
        content="Task without variables or inputs",
        source="test.md",
        trigger=TaskTrigger(triggers=["task"]),
    )

    # 检查提示词是否已附加不
    assert expected_prompt not in task_skill_no_vars.content
