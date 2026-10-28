"""使用 DiscriminatedUnionMixin 测试智能体 JSON 序列化。"""

import json
from collections.abc import Mapping
from typing import Any
from unittest.mock import Mock

import mcp.types
import pytest
from pydantic import BaseModel

from openhands.sdk.agent import Agent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.llm import LLM
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import coerce_mcp_config, dump_mcp_config
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.tool.tool import ToolDefinition
from openhands.sdk.utils.models import OpenHandsModel


def mcp_config_model(config: Mapping[str, object]):
    servers = (
        config.get("mcpServers")
        if isinstance(config.get("mcpServers"), dict)
        else config
    )
    return coerce_mcp_config(servers)


def dump_agent_mcp_config(agent: AgentBase) -> dict[str, dict[str, Any]]:
    return dump_mcp_config(agent.mcp_config)


def create_mock_mcp_tool(name: str) -> MCPToolDefinition:
    # 创建模拟对象 MCP 工具和客户端
    mock_mcp_tool = mcp.types.Tool(
        name=name,
        description=f"A test MCP tool named {name}",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query parameter"}
            },
            "required": ["query"],
        },
    )
    mock_client = Mock(spec=MCPClient)
    tools = MCPToolDefinition.create(mock_mcp_tool, mock_client)
    return tools[0]  # 从序列中提取单个工具


def test_agent_supports_polymorphic_json_serialization() -> None:
    """测试智能体支持多态 JSON 序列化/反序列化。"""
    # 使用空工具创建一个简单的 LLM 实例和智能体
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 序列化到 JSON（不包括不可序列化字段）
    agent_json = agent.model_dump_json()

    # 反序列化来自 JSON 使用基类
    deserialized_agent = AgentBase.model_validate_json(agent_json)

    # 应该反序列化为正确的类型并具有相同的核心字段
    assert isinstance(deserialized_agent, Agent)
    assert deserialized_agent.model_dump() == agent.model_dump()


def test_mcp_tool_serialization():
    tool = create_mock_mcp_tool("test_mcp_tool_serialization")
    dumped = tool.model_dump_json()
    loaded = ToolDefinition.model_validate_json(dumped)
    assert loaded.model_dump_json() == dumped


def test_agent_serialization_redacts_mcp_config_by_default() -> None:
    """默认序列化期间，MCP SecretStr 值为已脱敏。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    config = {
        "mcpServers": {
            "dummy": {
                "command": "echo",
                "args": ["dummy-mcp"],
                "env": {"API_KEY": "super-secret-key", "DEBUG": "true"},
                "headers": {"Authorization": "Bearer secret-token"},
            },
        }
    }
    agent = Agent(llm=llm, tools=[], mcp_config=mcp_config_model(config))

    # mcp_config 应该可以在内存中通过完整的机密进行访问
    assert dump_agent_mcp_config(agent) == config["mcpServers"]
    dumped_env = dump_agent_mcp_config(agent)["dummy"]["env"]
    assert isinstance(dumped_env, dict)
    assert dumped_env["API_KEY"] == "super-secret-key"

    agent_dump = agent.model_dump(mode="json")
    serialized = json.dumps(agent_dump)
    assert "super-secret-key" not in serialized
    assert "secret-token" not in serialized
    server = agent_dump["mcp_config"]["dummy"]
    assert isinstance(server["env"], dict)
    assert isinstance(server["headers"], dict)
    assert server["env"]["API_KEY"] == "**********"
    assert server["headers"]["Authorization"] == "**********"


def test_agent_serialization_exposes_mcp_config_with_expose_secrets() -> None:
    """测试当expose_secrets=True时mcp_config暴露。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    config = {
        "mcpServers": {
            "dummy": {
                "command": "echo",
                "args": ["dummy-mcp"],
                "env": {"API_KEY": "super-secret-key"},
            },
        }
    }
    agent = Agent(llm=llm, tools=[], mcp_config=mcp_config_model(config))

    # 当 expose_secrets=True 时，mcp_config 应按原样返回
    agent_dump = agent.model_dump(mode="json", context={"expose_secrets": True})
    server = agent_dump["mcp_config"]["dummy"]
    assert isinstance(server["env"], dict)
    assert server["command"] == "echo"
    assert server["args"] == ["dummy-mcp"]
    assert server["env"]["API_KEY"] == "super-secret-key"

    # 往返应该保留配置
    agent_json = agent.model_dump_json(context={"expose_secrets": True})
    deserialized_agent = AgentBase.model_validate_json(agent_json)
    assert isinstance(deserialized_agent, Agent)
    assert dump_agent_mcp_config(deserialized_agent) == config["mcpServers"]


def test_agent_serialization_encrypts_mcp_config_with_cipher() -> None:
    """当提供密码上下文时，MCP SecretStr 值将被加密。"""
    from openhands.sdk.utils.cipher import Cipher

    llm = LLM(model="test-model", usage_id="test-llm")
    config = {
        "mcpServers": {
            "dummy": {
                "command": "echo",
                "args": ["dummy-mcp"],
                "env": {"API_KEY": "super-secret-key"},
            },
        }
    }
    agent = Agent(llm=llm, tools=[], mcp_config=mcp_config_model(config))
    cipher = Cipher(secret_key="test-encryption-key")

    agent_dump = agent.model_dump(mode="json", context={"cipher": cipher})
    env = agent_dump["mcp_config"]["dummy"]["env"]
    assert isinstance(env, dict)
    encrypted = env["API_KEY"]
    assert isinstance(encrypted, str)
    assert encrypted != "super-secret-key"
    decrypted = cipher.decrypt(encrypted)
    assert decrypted is not None
    assert decrypted.get_secret_value() == "super-secret-key"


def test_agent_mcp_config_encryption_decryption_roundtrip() -> None:
    """测试完整往返：在序列化上加密，在反序列化上解密。"""
    from openhands.sdk.utils.cipher import Cipher

    llm = LLM(model="test-model", usage_id="test-llm")
    config = {
        "mcpServers": {
            "fetch": {"command": "uvx", "args": ["mcp-fetch"]},
            "git": {
                "command": "uvx",
                "args": ["mcp-git", "--repo", "/tmp/test"],
                "env": {"GIT_TOKEN": "git-secret"},
            },
        }
    }
    agent = Agent(llm=llm, tools=[], mcp_config=mcp_config_model(config))
    cipher = Cipher(secret_key="test-encryption-key-roundtrip")

    # 序列化带密码
    agent_json = agent.model_dump_json(context={"cipher": cipher})

    # 反序列化具有相同的密码
    restored_agent = AgentBase.model_validate_json(
        agent_json, context={"cipher": cipher}
    )

    # mcp_config应该正确恢复
    assert isinstance(restored_agent, Agent)
    assert dump_agent_mcp_config(restored_agent) == config["mcpServers"]


def test_agent_mcp_config_accepts_plaintext_dict() -> None:
    mcp_config = {"fetch": {"command": "uvx", "args": ["fetch"]}}
    agent_dict = {
        "llm": {"model": "test-model", "usage_id": "test-llm"},
        "tools": [],
        "mcp_config": mcp_config,
        "kind": "Agent",
    }

    # 反序列化 - 无需密码即可工作
    agent = AgentBase.model_validate(agent_dict)

    assert isinstance(agent, Agent)
    assert dump_agent_mcp_config(agent) == mcp_config


def test_agent_mcp_config_decrypts_nested_env_and_headers_with_cipher() -> None:
    """加密的每个值 MCP 环境/标头设置在智能体验证处解密。"""
    from pydantic import SecretStr

    from openhands.sdk.utils.cipher import Cipher

    cipher = Cipher(secret_key="test-per-value-mcp-key")
    encrypted_env = cipher.encrypt(SecretStr("ghp-plaintext-token"))
    encrypted_header = cipher.encrypt(SecretStr("Bearer plaintext-token"))
    agent_dict = {
        "llm": {"model": "test-model", "usage_id": "test-llm"},
        "tools": [],
        "mcp_config": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": encrypted_env,
                    "DEBUG": "true",
                    "PORT": "1234",
                },
                "headers": {"Authorization": encrypted_header},
            }
        },
        "kind": "Agent",
    }

    agent = AgentBase.model_validate(agent_dict, context={"cipher": cipher})

    assert isinstance(agent, Agent)
    server = dump_agent_mcp_config(agent)["github"]
    env = server["env"]
    headers = server["headers"]
    assert isinstance(env, dict)
    assert isinstance(headers, dict)
    assert env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp-plaintext-token"
    assert env["DEBUG"] == "true"
    assert env["PORT"] == "1234"
    assert headers["Authorization"] == "Bearer plaintext-token"
    assert (
        agent_dict["mcp_config"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"]
        == encrypted_env
    )


def test_agent_mcp_config_rejects_non_dict_plaintext_config() -> None:
    agent_dict = {
        "llm": {"model": "test-model", "usage_id": "test-llm"},
        "tools": [],
        "mcp_config": [],
        "kind": "Agent",
    }

    with pytest.raises(ValueError, match="Input should be a valid dictionary"):
        AgentBase.model_validate(agent_dict)


def test_agent_mcp_config_rejects_malformed_secret_containers() -> None:
    from openhands.sdk.utils.cipher import Cipher

    cipher = Cipher(secret_key="test-per-value-mcp-key")
    agent_dict = {
        "llm": {"model": "test-model", "usage_id": "test-llm"},
        "tools": [],
        "mcp_config": {"github": {"env": "not-a-dict"}},
        "kind": "Agent",
    }

    with pytest.raises(ValueError, match=r"mcp_config\.github\.env"):
        AgentBase.model_validate(agent_dict, context={"cipher": cipher})


def test_agent_supports_polymorphic_field_json_serialization() -> None:
    """测试智能体在用作字段时是否支持多态 JSON 序列化。"""

    class Container(BaseModel):
        agent: Agent  # 直接使用智能体类型而不是 DiscriminatedUnionType

    # 使用智能体创建容器
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    container = Container(agent=agent)

    # 序列化到 JSON（不包括不可序列化字段）
    container_json = container.model_dump_json()

    # 反序列化来自 JSON
    deserialized_container = Container.model_validate_json(container_json)

    # 应保留智能体类型和核心字段
    assert isinstance(deserialized_container.agent, Agent)
    assert deserialized_container.agent.model_dump() == agent.model_dump()


def test_agent_supports_nested_polymorphic_json_serialization() -> None:
    """测试智能体支持嵌套多态 JSON 序列化。"""

    class NestedContainer(BaseModel):
        agents: list[Agent]  # 使用直接智能体类型

    # 创建具有多个智能体的容器
    llm1 = LLM(model="model-1", usage_id="test-llm")
    llm2 = LLM(model="model-2", usage_id="test-llm")
    agent1 = Agent(llm=llm1, tools=[])
    agent2 = Agent(llm=llm2, tools=[])
    container = NestedContainer(agents=[agent1, agent2])

    # 序列化到 JSON（不包括不可序列化字段）
    container_json = container.model_dump_json()

    # 反序列化来自 JSON
    deserialized_container = NestedContainer.model_validate_json(container_json)

    # 应保留所有智能体类型和核心字段
    assert len(deserialized_container.agents) == 2
    assert isinstance(deserialized_container.agents[0], Agent)
    assert isinstance(deserialized_container.agents[1], Agent)
    assert deserialized_container.agents[0].model_dump() == agent1.model_dump()
    assert deserialized_container.agents[1].model_dump() == agent2.model_dump()


def test_agent_model_validate_json_dict() -> None:
    """测试 Agent.model_validate 是否适用于 JSON 中的 dict。"""
    # 创建智能体
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 序列化到JSON，然后解析为dict
    agent_json = agent.model_dump_json()
    agent_dict = json.loads(agent_json)

    # 反序列化来自字典
    deserialized_agent = AgentBase.model_validate(agent_dict)

    assert deserialized_agent.model_dump() == agent.model_dump()
    assert isinstance(deserialized_agent, Agent)


def test_agent_fallback_behavior_json() -> None:
    """测试智能体是否能够在 JSON 中优雅地处理未知类型。"""
    # 创建类型未知的 JSON
    agent_dict = {"llm": {"model": "test-model"}, "kind": "UnknownAgentType"}
    agent_json = json.dumps(agent_dict)

    # 应该抛出验证错误
    with pytest.raises(ValueError):
        AgentBase.model_validate_json(agent_json)


def test_agent_preserves_pydantic_parameters_json() -> None:
    """测试智能体是否保留 Pydantic 到 JSON 序列化的参数。"""
    # 使用额外数据创建智能体
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 序列化至JSON
    agent_json = agent.model_dump_json()

    # 反序列化来自 JSON
    deserialized_agent = AgentBase.model_validate_json(agent_json)

    assert deserialized_agent.model_dump() == agent.model_dump()
    assert isinstance(deserialized_agent, Agent)


def test_agent_type_annotation_works_json() -> None:
    """测试 AgentType 注释是否与 JSON 一起正常工作。"""
    # 创建智能体
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 使用AgentType注释
    class TestModel(OpenHandsModel):
        agent: AgentBase

    model = TestModel(agent=agent)

    # 序列化至JSON
    model_json = model.model_dump_json()

    # 反序列化来自 JSON
    deserialized_model = TestModel.model_validate_json(model_json)

    # 应该可以正常工作
    assert isinstance(deserialized_model.agent, Agent)
    assert deserialized_model.agent.model_dump() == agent.model_dump()
    assert deserialized_model.model_dump() == model.model_dump()


def test_agent_type_annotation_on_basemodel_works_json() -> None:
    """测试 AgentType 注释是否与 JSON 一起正常工作。"""
    # 创建智能体
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 使用AgentType注释
    class TestModel(BaseModel):
        agent: AgentBase

    model = TestModel(agent=agent)

    # 序列化至JSON
    model_json = model.model_dump_json()

    # 反序列化来自 JSON
    deserialized_model = TestModel.model_validate_json(model_json)

    # 应该可以正常工作
    assert isinstance(deserialized_model.agent, Agent)
    assert deserialized_model.agent.model_dump() == agent.model_dump()
    assert deserialized_model.model_dump() == model.model_dump()


def test_include_default_tools_serialization_default() -> None:
    """测试 include_default_tools 使用默认值是否正确序列化。"""
    llm = LLM(model="test-model", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])

    # 序列化至JSON
    agent_json = agent.model_dump_json()
    agent_dict = json.loads(agent_json)

    # 默认应包含 FinishTool 和 ThinkTool 作为字符串
    assert "include_default_tools" in agent_dict
    assert set(agent_dict["include_default_tools"]) == {"FinishTool", "ThinkTool"}
