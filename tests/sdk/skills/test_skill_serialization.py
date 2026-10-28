"""使用触发组合测试技能序列化。"""

import json

from pydantic import BaseModel, Field, SecretStr

from openhands.sdk.mcp.config import MCPServer
from openhands.sdk.skills import (
    KeywordTrigger,
    Skill,
    TaskTrigger,
)
from openhands.sdk.skills.types import InputMetadata
from openhands.sdk.utils.models import OpenHandsModel


def test_repo_skill_serialization():
    """使用触发器=None（始终有效）序列化测试技能。"""
    # 创建触发器=None的技能（始终有效）
    repo_skill = Skill(
        name="test-repo",
        content="Repository-specific instructions",
        source="test-repo.md",
        trigger=None,
    )

    # 测试序列化
    serialized = repo_skill.model_dump()
    assert serialized["trigger"] is None
    assert serialized["name"] == "test-repo"
    assert serialized["content"] == "Repository-specific instructions"
    assert serialized["source"] == "test-repo.md"
    assert serialized["mcp_tools"] is None

    # 测试 JSON 序列化
    json_str = repo_skill.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"] is None

    # 测试反序列化
    deserialized = Skill.model_validate(serialized)
    assert deserialized.trigger is None
    assert deserialized == repo_skill


def test_knowledge_skill_serialization():
    """使用 KeywordTrigger 序列化和反序列化测试技能。"""
    # 使用 KeywordTrigger 创建技能
    knowledge_skill = Skill(
        name="test-knowledge",
        content="Knowledge-based instructions",
        source="test-knowledge.md",
        trigger=KeywordTrigger(keywords=["python", "testing"]),
    )

    # 测试序列化
    serialized = knowledge_skill.model_dump()
    assert serialized["trigger"]["type"] == "keyword"
    assert serialized["name"] == "test-knowledge"
    assert serialized["content"] == "Knowledge-based instructions"
    assert serialized["trigger"]["keywords"] == ["python", "testing"]

    # 测试 JSON 序列化
    json_str = knowledge_skill.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"]["type"] == "keyword"

    # 测试反序列化
    deserialized = Skill.model_validate(serialized)
    assert deserialized == knowledge_skill


def test_task_skill_serialization():
    """使用 TaskTrigger 序列化和反序列化测试技能。"""
    # 使用 TaskTrigger 创建技能
    task_skill = Skill(
        name="test-task",
        content="Task-based instructions with ${variable}",
        source="test-task.md",
        trigger=TaskTrigger(triggers=["task", "automation"]),
        inputs=[
            InputMetadata(name="variable", description="A test variable"),
        ],
    )

    # 测试序列化
    serialized = task_skill.model_dump()
    assert serialized["trigger"]["type"] == "task"
    assert serialized["name"] == "test-task"
    assert "Task-based instructions with ${variable}" in serialized["content"]
    assert serialized["trigger"]["triggers"] == ["task", "automation"]
    assert len(serialized["inputs"]) == 1
    assert serialized["inputs"][0]["name"] == "variable"

    # 测试 JSON 序列化
    json_str = task_skill.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["trigger"]["type"] == "task"

    # 测试反序列化
    deserialized = Skill.model_validate(serialized)
    assert deserialized == task_skill


def test_skill_union_serialization_roundtrip():
    """测试所有触发器类型的完整序列化往返。"""
    # 每种触发类型的测试数据
    test_cases = [
        Skill(
            name="repo-test",
            content="Repo content",
            source="repo.md",
            trigger=None,
        ),
        Skill(
            name="knowledge-test",
            content="Knowledge content",
            source="knowledge.md",
            trigger=KeywordTrigger(keywords=["test"]),
        ),
        Skill(
            name="task-test",
            content="Task content with ${var}",
            source="task.md",
            trigger=TaskTrigger(triggers=["task"]),
            inputs=[InputMetadata(name="var", description="Test variable")],
        ),
    ]

    for original_skill in test_cases:
        # 序列化听写
        serialized = original_skill.model_dump()

        # 序列化到 JSON 字符串
        json_str = original_skill.model_dump_json()

        # 反序列化来自字典
        deserialized_from_dict = Skill.model_validate(serialized)

        # 反序列化来自 JSON 字符串
        deserialized_from_json = Skill.model_validate_json(json_str)

        # 验证所有版本是否等效
        assert deserialized_from_dict == original_skill
        assert deserialized_from_json == original_skill


def test_skill_union_polymorphic_list():
    """测试技能列表是否可以包含不同的触发器类型。"""
    # 创建具有不同触发器类型的列表
    skills = [
        Skill(
            name="repo1",
            content="Repo content",
            source="repo1.md",
            trigger=None,
        ),
        Skill(
            name="knowledge1",
            content="Knowledge content",
            source="knowledge1.md",
            trigger=KeywordTrigger(keywords=["test"]),
        ),
        Skill(
            name="task1",
            content="Task content",
            source="task1.md",
            trigger=TaskTrigger(triggers=["task"]),
        ),
    ]

    # 序列化列表
    serialized_list = [skill.model_dump() for skill in skills]

    # 验证每个项目都有正确的触发器类型
    assert serialized_list[0]["trigger"] is None  # 永远活跃的技能
    assert serialized_list[1]["trigger"]["type"] == "keyword"
    assert serialized_list[2]["trigger"]["type"] == "task"

    # 测试列表的JSON序列化
    json_str = json.dumps(serialized_list)
    parsed_list = json.loads(json_str)

    assert len(parsed_list) == 3
    assert parsed_list[0]["trigger"] is None  # 永远活跃的技能
    assert parsed_list[1]["trigger"]["type"] == "keyword"
    assert parsed_list[2]["trigger"]["type"] == "task"

    # 从已序列化数据重建列表
    deserialized_list = [Skill.model_validate(item) for item in serialized_list]

    assert len(deserialized_list) == 3
    assert deserialized_list[0].trigger is None
    assert isinstance(deserialized_list[1].trigger, KeywordTrigger)
    assert isinstance(deserialized_list[2].trigger, TaskTrigger)
    assert deserialized_list[0] == skills[0]
    assert deserialized_list[1] == skills[1]
    assert deserialized_list[2] == skills[2]


def test_discriminated_union_with_openhands_model():
    """使用 OpenHandsModel 测试触发辨别功能。"""

    class TestModel(OpenHandsModel):
        skills: list[Skill] = Field(default_factory=list)

    # 使用不同的触发器类型创建测试数据
    test_data = {
        "skills": [
            {
                "kind": "Skill",
                "name": "test-repo",
                "content": "Repo content",
                "source": "repo.md",
                "trigger": None,  # 永远活跃的技能
                "mcp_tools": None,
            },
            {
                "kind": "Skill",
                "name": "test-knowledge",
                "content": "Knowledge content",
                "source": "knowledge.md",
                "trigger": {"type": "keyword", "keywords": ["test"]},
            },
            {
                "kind": "Skill",
                "name": "test-task",
                "content": "Task content",
                "source": "task.md",
                "trigger": {"type": "task", "triggers": ["task"]},
                "inputs": [],
            },
        ]
    }

    # 验证模型 - 这测试触发辨别力
    model = TestModel.model_validate(test_data)

    # 验证每个技能是否被正确区分
    assert len(model.skills) == 3
    assert model.skills[0].trigger is None
    assert isinstance(model.skills[1].trigger, KeywordTrigger)
    assert isinstance(model.skills[2].trigger, TaskTrigger)

    # 验证触发器类型是否正确第一个技能始终有效（触发器为 None）
    #
    assert model.skills[1].trigger.type == "keyword"
    assert model.skills[2].trigger.type == "task"


def test_discriminated_union_with_pydantic_model():
    """使用 Pydantic BaseModel 测试触发辨别功能。"""

    class TestModel(BaseModel):
        skills: list[Skill] = Field(default_factory=list)

    # 使用不同的触发器类型创建测试数据
    test_data = {
        "skills": [
            {
                "name": "test-repo",
                "content": "Repo content",
                "source": "repo.md",
                "trigger": None,  # 永远活跃的技能
                "mcp_tools": None,
            },
            {
                "name": "test-knowledge",
                "content": "Knowledge content",
                "source": "knowledge.md",
                "trigger": {"type": "keyword", "keywords": ["test"]},
            },
            {
                "name": "test-task",
                "content": "Task content",
                "source": "task.md",
                "trigger": {"type": "task", "triggers": ["task"]},
                "inputs": [],
            },
        ]
    }

    # 验证模型 - 这测试触发辨别力
    model = TestModel.model_validate(test_data)

    # 验证每个技能是否被正确区分
    assert len(model.skills) == 3
    assert model.skills[0].trigger is None
    assert isinstance(model.skills[1].trigger, KeywordTrigger)
    assert isinstance(model.skills[2].trigger, TaskTrigger)

    # 验证触发器类型是否正确第一个技能始终有效（触发器为 None）
    #
    assert model.skills[1].trigger.type == "keyword"
    assert model.skills[2].trigger.type == "task"


# mcp_tools 掩蔽测试的可清晰识别的机密值。
_MCP_SECRET = "ghp_SUPER_SECRET_TOKEN_SHOULD_NOT_LEAK"


def _skill_with_mcp_secret() -> Skill:
    return Skill(
        name="leaky",
        content="do stuff",
        mcp_tools={
            "svc": MCPServer(
                url="https://x.test",
                headers={"Authorization": SecretStr(f"Bearer {_MCP_SECRET}")},
                env={"API_KEY": SecretStr(_MCP_SECRET)},
            )
        },
    )


def test_mcp_tools_secrets_redacted_by_default():
    """mcp_tools env/headers 携带 MCP 凭据; 他们必须已脱敏在
    REST，就像设置 mcp_config 一样——不以明文形式转储。"""
    skill = _skill_with_mcp_secret()

    dumped = json.dumps(skill.model_dump(mode="json"))
    assert _MCP_SECRET not in dumped

    json_dumped = skill.model_dump_json()
    assert _MCP_SECRET not in json_dumped


def test_mcp_tools_secrets_exposed_under_expose_secrets():
    """选择加入暴露表面真实值（与 mcp_config 相同）。"""
    skill = _skill_with_mcp_secret()

    exposed = json.dumps(
        skill.model_dump(mode="json", context={"expose_secrets": "plaintext"})
    )
    assert _MCP_SECRET in exposed


def test_mcp_tools_secrets_encrypted_under_cipher():
    """使用上下文中的密码，机密被加密（不是明文，不是
    删除），以便它们可以在恢复时解密。"""
    from openhands.sdk.utils.cipher import Cipher

    skill = _skill_with_mcp_secret()
    cipher = Cipher(secret_key="test-encryption-key")

    encrypted = json.dumps(
        skill.model_dump(
            mode="json", context={"expose_secrets": "encrypted", "cipher": cipher}
        )
    )
    assert _MCP_SECRET not in encrypted
    # server/env/header 键仍然存在，并且只有机密值被转换。
    assert '"svc"' in encrypted
    assert "Authorization" in encrypted
    assert "headers" in encrypted
    assert "API_KEY" in encrypted


def test_mcp_tools_real_values_remain_accessible_in_memory():
    """屏蔽仅限序列化：live 属性保留真实值，因此
    运行时MCP的使用不受影响。"""
    skill = _skill_with_mcp_secret()

    assert skill.mcp_tools is not None
    env = skill.mcp_tools["svc"].env
    assert env is not None
    assert env["API_KEY"].get_secret_value() == _MCP_SECRET


def test_mcp_tools_none_round_trips_unchanged():
    """没有 mcp_tools 的技能仍将 mcp_tools 序列化为 None。"""
    skill = Skill(name="clean", content="hello")
    dumped = skill.model_dump(mode="json")
    assert dumped["mcp_tools"] is None
    assert Skill.model_validate(dumped) == skill
