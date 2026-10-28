from collections.abc import Sequence
from typing import ClassVar
from unittest.mock import patch

import pytest
from pydantic import Field
from rich.text import Text

from openhands.sdk import LLM, Conversation
from openhands.sdk.agent import Agent
from openhands.sdk.llm.message import ImageContent, TextContent
from openhands.sdk.tool import ToolDefinition
from openhands.sdk.tool.registry import register_tool
from openhands.sdk.tool.spec import Tool
from openhands.sdk.tool.tool import Action, Observation, ToolExecutor


class _Action(Action):
    text: str


class _Obs(Observation):
    out: str

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text=self.out)]


class _Exec(ToolExecutor[_Action, _Obs]):
    def __call__(self, action: _Action, conversation=None) -> _Obs:
        return _Obs(out=action.text.upper())


class _UpperTool(ToolDefinition[_Action, _Obs]):
    """用于大写测试的具体工具。"""

    name: ClassVar[str] = "upper"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["_UpperTool"]:
        return [
            cls(
                description="Uppercase",
                action_type=_Action,
                observation_type=_Obs,
                executor=_Exec(),
            )
        ]


def test_agent_initializes_tools_from_toolspec_locally(monkeypatch):
    # 通过注册表注册一个简单的本地工具
    register_tool("upper", _UpperTool)

    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[Tool(name="upper")])

    # 建立对话； 智能体 init 是惰性的（推迟到第一次运行/send_message）
    conv = Conversation(agent=agent, visualizer=None)

    # 通过调用 _ensure_agent_ready() 触发智能体初始化这是必需的，因为 agent.tools_map 需
    # 要初始化
    #
    conv._ensure_agent_ready()

    # 通过一个小垫片访问智能体的运行时工具（我们不依赖私有内部结构； 我们通过检查
    # agent.step 可以无错误地访问工具来验证 init_state 生成了包含工具的系统提示词。）
    #
    with patch.object(Agent, "step", wraps=agent.step):
        runtime_tools = agent.tools_map
        assert "upper" in runtime_tools
        assert "finish" in runtime_tools
        assert "think" in runtime_tools


def test_agent_include_only_finish_tool():
    """测试只能包含完成工具（认为排除工具）。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[], include_default_tools=["FinishTool"])

    conv = Conversation(agent=agent, visualizer=None)
    # 触发延迟智能体初始化
    conv._ensure_agent_ready()

    with patch.object(Agent, "step", wraps=agent.step):
        runtime_tools = agent.tools_map
        assert "finish" in runtime_tools
        assert "think" not in runtime_tools


def test_agent_include_only_think_tool():
    """测试是否只能包含 think 工具（不包括 finish 工具）。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[], include_default_tools=["ThinkTool"])

    conv = Conversation(agent=agent, visualizer=None)
    # 触发延迟智能体初始化
    conv._ensure_agent_ready()

    with patch.object(Agent, "step", wraps=agent.step):
        runtime_tools = agent.tools_map
        assert "finish" not in runtime_tools
        assert "think" in runtime_tools


def test_agent_disable_all_default_tools():
    """测试是否可以使用 include_default_tools=[] 禁用所有默认工具。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[], include_default_tools=[])

    conv = Conversation(agent=agent, visualizer=None)
    # 触发延迟智能体初始化
    conv._ensure_agent_ready()

    with patch.object(Agent, "step", wraps=agent.step):
        runtime_tools = agent.tools_map
        assert "finish" not in runtime_tools
        assert "think" not in runtime_tools


def test_runtime_tools_cannot_replace_existing_tool():
    register_tool("upper", _UpperTool)
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[Tool(name="upper")], include_default_tools=[])
    conv = Conversation(agent=agent, visualizer=None)
    conv._ensure_agent_ready()

    runtime_tool = _UpperTool.create()[0]
    with pytest.raises(ValueError, match="Duplicate tool names"):
        agent.add_runtime_tools([runtime_tool])


# 用于测试更换的定制完成工具
class _CustomFinishAction(Action):
    result: str = Field(description="The result of the task.")
    success: bool = Field(description="Whether the task was successful.")

    @property
    def visualize(self) -> Text:
        return Text(f"Custom Finish: {self.result} (success={self.success})")


class _CustomFinishObs(Observation):
    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        return [TextContent(text="Task completed.")]


class _CustomFinishExec(ToolExecutor[_CustomFinishAction, _CustomFinishObs]):
    def __call__(
        self, action: _CustomFinishAction, conversation=None
    ) -> _CustomFinishObs:
        return _CustomFinishObs.from_text(text="Task completed.")


class _CustomFinishTool(ToolDefinition[_CustomFinishAction, _CustomFinishObs]):
    """具有结构化输出的自定义完成工具。"""

    name: ClassVar[str] = "finish"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["_CustomFinishTool"]:
        return [
            cls(
                description="Custom finish tool with structured output.",
                action_type=_CustomFinishAction,
                observation_type=_CustomFinishObs,
                executor=_CustomFinishExec(),
            )
        ]


def test_agent_replace_finish_with_custom_tool():
    """测试完成工具是否可以替换为自定义实现。"""
    register_tool("custom_finish", _CustomFinishTool)

    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(
        llm=llm,
        tools=[Tool(name="custom_finish")],
        include_default_tools=["ThinkTool"],  # 只包含ThinkTool，排除FinishTool
    )

    conv = Conversation(agent=agent, visualizer=None)
    # 触发延迟智能体初始化
    conv._ensure_agent_ready()

    with patch.object(Agent, "step", wraps=agent.step):
        runtime_tools = agent.tools_map
        # 自定义完成工具应以名称“完成”出现
        assert "finish" in runtime_tools
        # 通过检查操作类型来验证它是我们的自定义工具
        finish_tool = runtime_tools["finish"]
        assert finish_tool.action_type == _CustomFinishAction
        # 认为工具应该仍然存在
        assert "think" in runtime_tools
