"""测试 system_prompt_filename 中的绝对路径支持。"""

import os
import tempfile

import pytest
from pydantic import SecretStr

from openhands.sdk.agent.agent import Agent
from openhands.sdk.context.prompts.prompt import render_template
from openhands.sdk.llm import LLM


def test_render_template_with_relative_path():
    """测试 render_template 是否解析相对于 prompt_dir 的相对名称。

    内置 .j2 模板已移植到提示词注册表中，因此在临时目录中使用一次性模板来执行相对路径
    解析。
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        template_name = "relative_template.j2"
        with open(os.path.join(tmp_dir, template_name), "w") as f:
            f.write("Relative render of {{ subject }}.")

        result = render_template(
            prompt_dir=tmp_dir,
            template_name=template_name,
            subject="a template",
        )

    assert result == "Relative render of a template."


def test_render_template_with_absolute_path():
    """测试 render_template 是否适用于绝对路径。"""
    # 创建临时模板文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".j2", delete=False) as tmp_file:
        tmp_file.write("Hello {{ name }}! This is a test template.")
        tmp_path = tmp_file.name

    try:
        # 使用绝对路径渲染
        result = render_template(
            prompt_dir="/unused/dir",  # 对于绝对路径，应忽略这一点
            template_name=tmp_path,
            name="World",
        )

        assert result == "Hello World! This is a test template."
    finally:
        # 清理
        os.unlink(tmp_path)


def test_agent_with_absolute_system_prompt_path():
    """测试智能体是否可以使用 system_prompt_filename 的绝对路径。"""
    # 创建临时模板文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".j2", delete=False) as tmp_file:
        tmp_file.write(
            "You are a test assistant. CLI mode: {{ cli_mode|default(false) }}"
        )
        tmp_path = tmp_file.name

    try:
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )

        # 使用系统提示词的绝对路径创建智能体
        agent = Agent(
            llm=llm,
            tools=[],
            system_prompt_filename=tmp_path,
            system_prompt_kwargs={"cli_mode": True},
        )

        # 获取系统消息
        system_message = agent.static_system_message

        # 验证消息是否正确呈现
        assert "You are a test assistant" in system_message
        assert "CLI mode: True" in system_message
    finally:
        # 清理
        os.unlink(tmp_path)


def test_agent_with_relative_system_prompt_path():
    """测试智能体是否仍然适用于相对路径 (向后兼容性)。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")

    # 使用默认相对路径创建智能体
    agent = Agent(
        llm=llm,
        tools=[],
        system_prompt_filename="system_prompt.j2",  # 相对路径
    )

    # 获取系统消息
    system_message = agent.static_system_message

    # 验证消息是否正确呈现
    assert isinstance(system_message, str)
    assert len(system_message) > 0


def test_render_template_with_nonexistent_absolute_path():
    """测试 render_template 因绝对路径不存在而引发错误。"""  # noqa: E501
    nonexistent_path = "/nonexistent/directory/template.j2"

    with pytest.raises(FileNotFoundError, match="Prompt file"):
        render_template(
            prompt_dir="/unused/dir",
            template_name=nonexistent_path,
            name="Test",
        )


def test_render_template_with_nonexistent_relative_path():
    """测试 render_template 因相对路径不存在而引发错误。"""  # noqa: E501
    with tempfile.TemporaryDirectory() as tmp_dir:
        with pytest.raises(FileNotFoundError, match="Prompt file"):
            render_template(
                prompt_dir=tmp_dir,
                template_name="nonexistent_template.j2",
                name="Test",
            )
