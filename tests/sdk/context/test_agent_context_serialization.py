"""测试 AgentContext、序列化和反序列化。"""

import json
from base64 import urlsafe_b64encode

from pydantic import SecretStr

from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.secret import SecretSource, StaticSecret
from openhands.sdk.skills import (
    KeywordTrigger,
    Skill,
    TaskTrigger,
)
from openhands.sdk.skills.types import InputMetadata
from openhands.sdk.utils.cipher import Cipher


def test_agent_context_serialization_roundtrip():
    """确保通过 dict 和 JSON 序列化进行 AgentContext 往返。"""

    repo_skill = Skill(
        name="repo-guidelines",
        content="Repository guidelines",
        source="repo.md",
        trigger=None,
    )
    knowledge_skill = Skill(
        name="python-help",
        content="Use type hints in Python code",
        source="knowledge.md",
        trigger=KeywordTrigger(keywords=["python"]),
    )
    task_skill = Skill(
        name="run-task",
        content="Execute the task with ${param}",
        source="task.md",
        trigger=TaskTrigger(triggers=["run"]),
        inputs=[InputMetadata(name="param", description="Task parameter")],
    )

    context = AgentContext(
        skills=[repo_skill, knowledge_skill, task_skill],
        system_message_suffix="System suffix",
        user_message_suffix="User suffix",
    )

    serialized = context.model_dump()
    assert serialized["system_message_suffix"] == "System suffix"
    assert serialized["user_message_suffix"] == "User suffix"
    # 第一个技能的触发器=None（始终有效），其他技能有特定的触发器
    assert serialized["skills"][0]["trigger"] is None
    assert serialized["skills"][1]["trigger"]["type"] == "keyword"
    assert serialized["skills"][2]["trigger"]["type"] == "task"

    json_str = context.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["system_message_suffix"] == "System suffix"
    assert parsed["user_message_suffix"] == "User suffix"
    assert parsed["skills"][2]["inputs"][0]["name"] == "param"

    deserialized_from_dict = AgentContext.model_validate(serialized)
    assert isinstance(deserialized_from_dict.skills[0], Skill)
    assert deserialized_from_dict.skills[0].trigger is None
    assert deserialized_from_dict.skills[0] == repo_skill
    assert isinstance(deserialized_from_dict.skills[1], Skill)
    assert isinstance(deserialized_from_dict.skills[1].trigger, KeywordTrigger)
    assert deserialized_from_dict.skills[1] == knowledge_skill
    assert isinstance(deserialized_from_dict.skills[2], Skill)
    assert isinstance(deserialized_from_dict.skills[2].trigger, TaskTrigger)
    assert deserialized_from_dict.skills[2] == task_skill
    assert deserialized_from_dict.system_message_suffix == "System suffix"
    assert deserialized_from_dict.user_message_suffix == "User suffix"

    deserialized_from_json = AgentContext.model_validate_json(json_str)
    assert isinstance(deserialized_from_json.skills[0], Skill)
    assert deserialized_from_json.skills[0].trigger is None
    assert deserialized_from_json.skills[0] == repo_skill
    assert isinstance(deserialized_from_json.skills[1], Skill)
    assert isinstance(deserialized_from_json.skills[1].trigger, KeywordTrigger)
    assert deserialized_from_json.skills[1] == knowledge_skill
    assert isinstance(deserialized_from_json.skills[2], Skill)
    assert isinstance(deserialized_from_json.skills[2].trigger, TaskTrigger)
    assert deserialized_from_json.skills[2] == task_skill
    assert deserialized_from_json.model_dump() == serialized


def test_memory_context_excluded_from_serialization():
    """memory_context 是运行时解析的状态，不能是已持久化。"""
    context = AgentContext(load_memory=True).model_copy(
        update={"memory_context": "- remembered fact"}
    )

    serialized = context.model_dump()
    assert serialized["load_memory"] is True
    assert "memory_context" not in serialized
    assert "memory_context" not in context.model_dump_json()

    restored = AgentContext.model_validate(serialized)
    assert restored.load_memory is True
    assert restored.memory_context is None


def test_agent_context_secrets_round_trip_through_cipher_context():
    """``AgentContext.secrets`` 原始字符串值必须干净地往返
    当用密码重新验证时。

    回归与任何带有机密的字典字段 (e.g. MCP ``env``/``headers``): 该字段有一个
    ``field_serializer`` 在密码上下文下
    加密（通过：func:`serialize_secret`），但到目前为止没有匹配的 ``field_validator``
    。 所以密文得以幸存
    ``StoredConversation.model_validate(..., context={'cipher': ...})`` 在对话开始流
    程中，并作为
    ``gAAAA...`` 而到达智能体的系统提示词，而不是配置的值。
    """
    cipher = Cipher(urlsafe_b64encode(b"a" * 32).decode("ascii"))
    plaintext = {"GITHUB_TOKEN": "ghp-real-token", "DB_PASS": "pw"}

    ctx = AgentContext(secrets=plaintext)
    dumped = ctx.model_dump(mode="json", context={"cipher": cipher})
    # 健全性检查：转储产生 Fernet 密文，而不是明文。
    for key, raw_value in plaintext.items():
        stored = dumped["secrets"][key]
        assert isinstance(stored, str)
        assert stored != raw_value
        assert stored.startswith("gAAAA")

    restored = AgentContext.model_validate(dumped, context={"cipher": cipher})
    assert restored.secrets == plaintext


def test_agent_context_secrets_plaintext_passes_through_with_cipher():
    """老客户端的第一个写入带有明文。 他们必须验证
    当密码存在于上下文中时干净利落地（没有 FERNET_TOKEN_PREFIX，没有尝试解密）。
    """
    cipher = Cipher(urlsafe_b64encode(b"a" * 32).decode("ascii"))
    ctx = AgentContext.model_validate(
        {"secrets": {"FOO": "plaintext-value"}},
        context={"cipher": cipher},
    )
    assert ctx.secrets == {"FOO": "plaintext-value"}


def test_agent_context_secrets_secret_source_passes_through_with_cipher():
    """``SecretSource`` 条目序列化到线上的字典，所以它们
    必须完好无损地通过 ``validate_secret_dict`` 的 ``isinstance(value, str)`` 门，同
    时原始字符串同级仍被解密。

    锁在不变量的 ``_decrypt_secrets``  文档字符串描述：如果 ``SecretSource``  序列化
    从未生产过裸字符串，str-门将会默默地开
    始篡改它，密文可能会到达提示词。
    """
    cipher = Cipher(urlsafe_b64encode(b"a" * 32).decode("ascii"))
    source = StaticSecret(value=SecretStr("source-secret"))
    ctx = AgentContext(secrets={"RAW": "plaintext", "SRC": source})

    dumped = ctx.model_dump(mode="json", context={"cipher": cipher})
    # 原始字符串被加密为 Fernet token； SecretSource 仍然是一个字典（它自己的嵌套
    # ``value`` 是被加密的部分）。
    #
    assert dumped["secrets"]["RAW"].startswith("gAAAA")
    assert isinstance(dumped["secrets"]["SRC"], dict)

    restored = AgentContext.model_validate(dumped, context={"cipher": cipher})
    assert restored.secrets is not None
    assert restored.secrets["RAW"] == "plaintext"
    assert isinstance(restored.secrets["SRC"], SecretSource)
    assert restored.secrets["SRC"].get_value() == "source-secret"
