"""
env_parser 模块的综合测试。

测试涵盖：
- 基本环境解析器（bool、int、float、str 等）
- 复杂解析器（列表、字典、联合、模型解析器）
- 具有嵌套属性和 Webhook 规范的配置类解析
- 自引用节点模型解析
- 枚举和字符串文字解析
- 模板生成（to_env 方法）
- 边缘情况和错误条件
"""

import json
import os
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from openhands.agent_server.config import Config, load_config
from openhands.agent_server.conversation_lease import DEFAULT_LEASE_TTL_SECONDS
from openhands.agent_server.env_parser import (
    MISSING,
    BoolEnvParser,
    DelayedParser,
    DictEnvParser,
    DiscriminatedUnionEnvParser,
    FloatEnvParser,
    IntEnvParser,
    ListEnvParser,
    LiteralEnvParser,
    ModelEnvParser,
    NoneEnvParser,
    StrEnvParser,
    UnionEnvParser,
    from_env,
    get_env_parser,
    merge,
    to_env,
)
from openhands.sdk.security.risk import SecurityRisk
from tests.sdk.utils.test_discriminated_union import Animal, Dog


class NodeModel(BaseModel):
    """用于测试基本递归解析的简单节点模型。"""

    name: str
    value: int = 0
    children: list["NodeModel"] = Field(default_factory=list)


class OptionalSubModel(BaseModel):
    title: str | None = None
    value: int | None = None


class OptionalModel(BaseModel):
    sub: OptionalSubModel | None = None


@pytest.fixture
def clean_env():
    """针对隔离环境快照运行每个测试。"""
    original_env = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.clear()
    os.environ.update(original_env)


def test_bool_env_parser(clean_env):
    """使用各种布尔表示法测试 BoolEnvParser。"""
    parser = BoolEnvParser()

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试真值值
    for value in ["1", "TRUE", "true", "True"]:
        os.environ["TEST_BOOL"] = value
        assert parser.from_env("TEST_BOOL") is True
        del os.environ["TEST_BOOL"]

    # 测试虚假值
    for value in ["0", "FALSE", "false", "False", ""]:
        os.environ["TEST_BOOL"] = value
        assert parser.from_env("TEST_BOOL") is False
        del os.environ["TEST_BOOL"]


def test_int_env_parser(clean_env):
    """使用各种整数值测试 IntEnvParser。"""
    parser = IntEnvParser()

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试有效整数
    os.environ["TEST_INT"] = "42"
    assert parser.from_env("TEST_INT") == 42

    os.environ["TEST_INT"] = "-123"
    assert parser.from_env("TEST_INT") == -123

    os.environ["TEST_INT"] = "0"
    assert parser.from_env("TEST_INT") == 0

    # 测试无效整数
    os.environ["TEST_INT"] = "not_a_number"
    with pytest.raises(ValueError):
        parser.from_env("TEST_INT")


def test_float_env_parser(clean_env):
    """使用各种浮点值测试 FloatEnvParser。"""
    parser = FloatEnvParser()

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试有效的浮点数
    os.environ["TEST_FLOAT"] = "3.14"
    assert parser.from_env("TEST_FLOAT") == 3.14

    os.environ["TEST_FLOAT"] = "-2.5"
    assert parser.from_env("TEST_FLOAT") == -2.5

    os.environ["TEST_FLOAT"] = "0.0"
    assert parser.from_env("TEST_FLOAT") == 0.0

    # 测试整数为浮点数
    os.environ["TEST_FLOAT"] = "42"
    assert parser.from_env("TEST_FLOAT") == 42.0

    # 测试无效的浮点数
    os.environ["TEST_FLOAT"] = "not_a_number"
    with pytest.raises(ValueError):
        parser.from_env("TEST_FLOAT")


def test_str_env_parser(clean_env):
    """使用各种字符串值测试 StrEnvParser。"""
    parser = StrEnvParser()

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试有效的字符串
    os.environ["TEST_STR"] = "hello world"
    assert parser.from_env("TEST_STR") == "hello world"

    os.environ["TEST_STR"] = ""
    assert parser.from_env("TEST_STR") == ""

    os.environ["TEST_STR"] = "123"
    assert parser.from_env("TEST_STR") == "123"


def test_none_env_parser(clean_env):
    """测试 NoneEnvParser 行为。"""
    parser = NoneEnvParser()

    # 测试丢失的密钥（应返回 MISSING）
    assert parser.from_env("SOME_VALUE") is MISSING

    # 测试当前密钥（应返回 None）
    os.environ["SOME_VALUE_IS_NONE"] = "1"
    assert parser.from_env("SOME_VALUE") is None


def test_dict_env_parser(clean_env):
    """使用 JSON 字典值测试 DictEnvParser。"""
    parser = DictEnvParser()

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试有效 JSON 字典
    test_dict = {"key1": "value1", "key2": 42, "key3": True}
    os.environ["TEST_DICT"] = json.dumps(test_dict)
    result = parser.from_env("TEST_DICT")
    assert result == test_dict

    # 测试空字典
    os.environ["TEST_DICT"] = "{}"
    assert parser.from_env("TEST_DICT") == {}

    # 测试无效JSON
    os.environ["TEST_DICT"] = "not_json"
    with pytest.raises(json.JSONDecodeError):
        parser.from_env("TEST_DICT")

    # 测试非字典 JSON
    os.environ["TEST_DICT"] = "[1, 2, 3]"
    with pytest.raises(AssertionError):
        parser.from_env("TEST_DICT")


def test_list_env_parser_with_json(clean_env):
    """使用 JSON 列表值测试 ListEnvParser。"""
    item_parser = StrEnvParser()
    parser = ListEnvParser(item_parser, str)

    # 测试JSON列表
    test_list = ["item1", "item2", "item3"]
    os.environ["TEST_LIST"] = json.dumps(test_list)
    result = parser.from_env("TEST_LIST")
    assert result == test_list

    # 测试空列表
    os.environ["TEST_LIST"] = "[]"
    assert parser.from_env("TEST_LIST") == []

    # 测试数字列表（表示长度）
    os.environ["TEST_LIST"] = "3"
    os.environ["TEST_LIST_0"] = "first"
    os.environ["TEST_LIST_1"] = "second"
    os.environ["TEST_LIST_2"] = "third"
    result = parser.from_env("TEST_LIST")
    assert result == ["first", "second", "third"]


def test_list_env_parser_sequential(clean_env):
    """使用顺序环境变量测试 ListEnvParser。"""
    item_parser = StrEnvParser()
    parser = ListEnvParser(item_parser, str)

    # 测试没有基本键的连续项目
    os.environ["TEST_LIST_0"] = "first"
    os.environ["TEST_LIST_1"] = "second"
    os.environ["TEST_LIST_2"] = "third"
    result = parser.from_env("TEST_LIST")
    assert result == ["first", "second", "third"]

    # 测试有间隙（应该在第一次缺失时停止）
    del os.environ["TEST_LIST_1"]
    result = parser.from_env("TEST_LIST")
    assert result == ["first"]


def test_list_env_parser_with_complex_items(clean_env):
    """使用复杂的项目类型测试 ListEnvParser。"""
    item_parser = IntEnvParser()
    parser = ListEnvParser(item_parser, int)

    # 使用整数项进行测试
    os.environ["TEST_LIST_0"] = "10"
    os.environ["TEST_LIST_1"] = "20"
    os.environ["TEST_LIST_2"] = "30"
    result = parser.from_env("TEST_LIST")
    assert result == [10, 20, 30]


def test_union_env_parser(clean_env):
    """使用多种解析器类型测试 UnionEnvParser。"""
    parsers = {str: StrEnvParser(), int: IntEnvParser()}
    parser = UnionEnvParser(parsers)

    # 使用无法解析为 int 的字符串值进行测试 - 这将失败
    os.environ["TEST_UNION"] = "hello"
    with pytest.raises(ValueError):
        parser.from_env("TEST_UNION")

    # 使用整数值进行测试（两个解析器都成功，合并最后返回）
    os.environ["TEST_UNION"] = "42"
    result = parser.from_env("TEST_UNION")
    # 字符串解析器返回“42”，int解析器返回42，合并返回42
    assert result == 42

    # 使用兼容的解析器（str 和 bool）进行测试
    bool_str_parsers = {str: StrEnvParser(), bool: BoolEnvParser()}
    bool_str_parser = UnionEnvParser(bool_str_parsers)

    os.environ["TEST_UNION"] = "true"
    result = bool_str_parser.from_env("TEST_UNION")
    # 字符串解析器返回“True”，布尔解析器返回True，合并返回True
    assert result is True


def test_model_env_parser_simple(clean_env):
    """使用简单模型测试 ModelEnvParser。"""

    class SimpleModel(BaseModel):
        name: str = "default"
        count: int = 0

    field_parsers = {
        "name": StrEnvParser(),
        "count": IntEnvParser(),
    }
    descriptions = {}
    parser = ModelEnvParser(field_parsers, descriptions)

    # 使用各个字段覆盖进行测试
    os.environ["TEST_MODEL_NAME"] = "test_name"
    os.environ["TEST_MODEL_COUNT"] = "42"
    result = parser.from_env("TEST_MODEL")
    expected = {"name": "test_name", "count": 42}
    assert result == expected

    # 使用 JSON 基址和字段覆盖进行测试
    del os.environ["TEST_MODEL_NAME"]  # 清除之前的测试
    base_data = {"name": "json_name", "count": 10}
    os.environ["TEST_MODEL"] = json.dumps(base_data)
    os.environ["TEST_MODEL_COUNT"] = "99"  # 覆盖计数
    result = parser.from_env("TEST_MODEL")
    expected = {"name": "json_name", "count": 99}
    assert result == expected


def test_delayed_parser(clean_env):
    """测试 DelayedParser 处理循环依赖。"""
    delayed = DelayedParser()

    # 在不设置解析器的情况下进行测试（应该引发断言错误）
    with pytest.raises(AssertionError):
        delayed.from_env("TEST_KEY")

    # 使用解析器集进行测试
    delayed.parser = StrEnvParser()
    os.environ["TEST_KEY"] = "test_value"
    assert delayed.from_env("TEST_KEY") == "test_value"


def test_merge_function():
    """使用各种数据类型测试合并功能。"""
    # 使用 MISSING 值进行测试
    assert merge(MISSING, "value") == "value"
    assert merge("value", MISSING) == "value"
    assert merge(MISSING, MISSING) is MISSING

    # 测试简单的值（稍后会覆盖之前的值）
    assert merge("old", "new") == "new"
    assert merge(1, 2) == 2

    # 用字典测试
    dict1 = {"a": 1, "b": 2}
    dict2 = {"b": 3, "c": 4}
    expected = {"a": 1, "b": 3, "c": 4}
    assert merge(dict1, dict2) == expected

    # 使用嵌套字典进行测试
    dict1 = {"nested": {"a": 1, "b": 2}}
    dict2 = {"nested": {"b": 3, "c": 4}}
    expected = {"nested": {"a": 1, "b": 3, "c": 4}}
    assert merge(dict1, dict2) == expected

    # 使用列表进行测试
    list1 = [1, 2, 3]
    list2 = [10, 20]
    expected = [10, 20, 3]
    assert merge(list1, list2) == expected

    # 使用不同长度的列表进行测试（第二个列表更长） - 这将失败
    list1 = [1, 2]
    list2 = [10, 20, 30, 40]
    # 当前的实现有一个错误 - 它尝试分配给不存在的索引
    #
    with pytest.raises(IndexError):
        merge(list1, list2)

    # 使用不同长度的列表进行测试（第一个列表较长）
    list1 = [1, 2, 3, 4]
    list2 = [10, 20]
    expected = [10, 20, 3, 4]
    assert merge(list1, list2) == expected


def test_get_env_parser_basic_types():
    """使用基本类型测试 get_env_parser。"""
    parsers = {
        str: StrEnvParser(),
        int: IntEnvParser(),
        float: FloatEnvParser(),
        bool: BoolEnvParser(),
        type(None): NoneEnvParser(),
    }

    # 测试基本类型
    assert isinstance(get_env_parser(str, parsers), StrEnvParser)
    assert isinstance(get_env_parser(int, parsers), IntEnvParser)
    assert isinstance(get_env_parser(float, parsers), FloatEnvParser)
    assert isinstance(get_env_parser(bool, parsers), BoolEnvParser)
    assert isinstance(get_env_parser(type(None), parsers), NoneEnvParser)


def test_get_env_parser_complex_types():
    """使用复杂类型测试 get_env_parser。"""
    parsers = {
        str: StrEnvParser(),
        int: IntEnvParser(),
        float: FloatEnvParser(),
        bool: BoolEnvParser(),
        type(None): NoneEnvParser(),
    }

    # 测试列表类型
    list_parser = get_env_parser(list[str], parsers)
    assert isinstance(list_parser, ListEnvParser)
    assert isinstance(list_parser.item_parser, StrEnvParser)

    # 测试字典类型
    dict_parser = get_env_parser(dict[str, str], parsers)
    assert isinstance(dict_parser, DictEnvParser)

    # 测试联合类型
    union_parser = get_env_parser(str | int, parsers)  # type: ignore[arg-type]
    assert isinstance(union_parser, UnionEnvParser)
    assert len(union_parser.parsers) == 2


def test_get_env_parser_model_type():
    """使用 BaseModel 类型测试 get_env_parser。"""

    class TestModel(BaseModel):
        name: str
        value: int

    parsers = {
        str: StrEnvParser(),
        int: IntEnvParser(),
        float: FloatEnvParser(),
        bool: BoolEnvParser(),
        type(None): NoneEnvParser(),
    }
    model_parser = get_env_parser(TestModel, parsers)
    assert isinstance(model_parser, ModelEnvParser)
    assert "name" in model_parser.parsers
    assert "value" in model_parser.parsers
    assert isinstance(model_parser.parsers["name"], StrEnvParser)
    assert isinstance(model_parser.parsers["value"], IntEnvParser)


def test_config_class_parsing(clean_env):
    """测试解析具有嵌套属性和 Webhook 规范的 Config 类。"""
    # 测试基本配置解析
    os.environ["OH_SESSION_API_KEYS_0"] = "key1"
    os.environ["OH_SESSION_API_KEYS_1"] = "key2"
    os.environ["OH_ALLOW_CORS_ORIGINS_0"] = "http://localhost:3000"
    os.environ["OH_ALLOW_CORS_ORIGIN_REGEX"] = r"https://.*\.example\.com"
    os.environ["OH_CONVERSATIONS_PATH"] = "/custom/conversations"
    os.environ["OH_WORKSPACE_PATH"] = "/custom/workspace"
    os.environ["OH_ENABLE_VSCODE"] = "false"

    config = from_env(Config, "OH")

    assert config.session_api_keys == ["key1", "key2"]
    assert config.allow_cors_origins == ["http://localhost:3000"]
    assert config.allow_cors_origin_regex == r"https://.*\.example\.com"
    assert config.conversations_path == Path("/custom/conversations")
    assert config.workspace_path == Path("/custom/workspace")
    assert config.enable_vscode is False


def test_config_file_parsing(tmp_path, clean_env):
    """JSON 配置文件应填充与环境变量相同的配置字段。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "session_api_keys": ["file-key"],
                "allow_cors_origins": ["https://frontend.example.com"],
                "allow_cors_origin_regex": r"https://.*\.example\.com",
                "conversations_path": str(tmp_path / "conversations"),
                "workspace_path": str(tmp_path / "workspace"),
                "enable_vscode": False,
            }
        )
    )

    config = load_config(config_path)

    assert config.session_api_keys == ["file-key"]
    assert config.allow_cors_origins == ["https://frontend.example.com"]
    assert config.allow_cors_origin_regex == r"https://.*\.example\.com"
    assert config.conversations_path == tmp_path / "conversations"
    assert config.workspace_path == tmp_path / "workspace"
    assert config.enable_vscode is False


def test_config_file_parsing_with_env_override(tmp_path, clean_env):
    """环境变量应覆盖 JSON 配置文件值。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "allow_cors_origins": ["https://file.example.com"],
                "allow_cors_origin_regex": r"https://file\\..+",
            }
        )
    )
    os.environ["OH_ALLOW_CORS_ORIGINS_0"] = "https://env.example.com"
    os.environ["OH_ALLOW_CORS_ORIGIN_REGEX"] = r"https://env\\..+"

    config = load_config(config_path)

    assert config.allow_cors_origins == ["https://env.example.com"]
    assert config.allow_cors_origin_regex == r"https://env\\..+"


def test_config_webhook_specs_parsing(clean_env):
    """测试配置类中的Webhook规格。"""
    # 使用 JSON Webhook 规格进行测试
    webhook_data = [
        {
            "base_url": "https://webhook1.example.com",
            "headers": {"Authorization": "Bearer token1"},
            "event_buffer_size": 5,
            "flush_delay": 15.0,
            "num_retries": 2,
            "retry_delay": 3,
        },
        {
            "base_url": "https://webhook2.example.com",
            "headers": {"X-API-Key": "secret"},
            "event_buffer_size": 20,
            "flush_delay": 60.0,
        },
    ]
    os.environ["OH_WEBHOOKS"] = json.dumps(webhook_data)

    config = from_env(Config, "OH")

    assert len(config.webhooks) == 2
    assert config.webhooks[0].base_url == "https://webhook1.example.com"
    assert config.webhooks[0].headers == {"Authorization": "Bearer token1"}
    assert config.webhooks[0].event_buffer_size == 5
    assert config.webhooks[0].flush_delay == 15.0
    assert config.webhooks[0].num_retries == 2
    assert config.webhooks[0].retry_delay == 3

    assert config.webhooks[1].base_url == "https://webhook2.example.com"
    assert config.webhooks[1].headers == {"X-API-Key": "secret"}
    assert config.webhooks[1].event_buffer_size == 20
    assert config.webhooks[1].flush_delay == 60.0
    # 应使用默认值
    assert config.webhooks[1].num_retries == 3
    assert config.webhooks[1].retry_delay == 5


def test_config_webhook_specs_sequential_parsing(clean_env):
    """使用顺序环境变量测试解析 Webhook 规范。"""
    # 使用顺序 Webhook 环境变量进行测试
    os.environ["OH_WEBHOOKS_0_BASE_URL"] = "https://webhook1.example.com"
    os.environ["OH_WEBHOOKS_0_EVENT_BUFFER_SIZE"] = "15"
    os.environ["OH_WEBHOOKS_0_FLUSH_DELAY"] = "25.5"
    os.environ["OH_WEBHOOKS_0_HEADERS"] = json.dumps({"Auth": "token1"})

    os.environ["OH_WEBHOOKS_1_BASE_URL"] = "https://webhook2.example.com"
    os.environ["OH_WEBHOOKS_1_NUM_RETRIES"] = "5"
    os.environ["OH_WEBHOOKS_1_RETRY_DELAY"] = "10"

    config = from_env(Config, "OH")

    assert len(config.webhooks) == 2
    assert config.webhooks[0].base_url == "https://webhook1.example.com"
    assert config.webhooks[0].event_buffer_size == 15
    assert config.webhooks[0].flush_delay == 25.5
    assert config.webhooks[0].headers == {"Auth": "token1"}

    assert config.webhooks[1].base_url == "https://webhook2.example.com"
    assert config.webhooks[1].num_retries == 5
    assert config.webhooks[1].retry_delay == 10


def test_config_mixed_webhook_parsing(clean_env):
    """使用混合 JSON 和单独覆盖测试解析 Webhook。"""
    # 将基数 JSON 设置为一 Webhook
    base_webhooks = [
        {
            "base_url": "https://base.example.com",
            "event_buffer_size": 10,
        }
    ]
    os.environ["OH_WEBHOOKS"] = json.dumps(base_webhooks)

    # 覆盖特定字段
    os.environ["OH_WEBHOOKS_0_FLUSH_DELAY"] = "45.0"
    os.environ["OH_WEBHOOKS_0_HEADERS"] = json.dumps({"Override": "header"})

    config = from_env(Config, "OH")

    assert len(config.webhooks) == 1
    # 第一个 Webhook：基础 + 覆盖
    assert config.webhooks[0].base_url == "https://base.example.com"
    assert config.webhooks[0].event_buffer_size == 10
    assert config.webhooks[0].flush_delay == 45.0
    assert config.webhooks[0].headers == {"Override": "header"}


def test_node_model_parsing(clean_env):
    """测试解析简单的节点模型。"""
    # 测试简单节点
    os.environ["TEST_NODE_NAME"] = "root"
    os.environ["TEST_NODE_VALUE"] = "42"

    node = from_env(NodeModel, "TEST_NODE")
    assert node.name == "root"
    assert node.value == 42


def test_node_model_parsing_with_recursion(clean_env):
    """测试解析简单的节点模型。"""
    # 测试简单节点
    os.environ["TEST_NODE_NAME"] = "root"
    os.environ["TEST_NODE_VALUE"] = "42"
    os.environ["TEST_NODE_CHILDREN_0_NAME"] = "child 1"
    os.environ["TEST_NODE_CHILDREN_1_NAME"] = "child 2"

    node = from_env(NodeModel, "TEST_NODE")
    assert node.name == "root"
    assert node.value == 42
    expected_children = [
        NodeModel(name="child 1"),
        NodeModel(name="child 2"),
    ]
    assert node.children == expected_children


def test_node_model_with_json(clean_env):
    """使用 JSON 测试解析 SimpleNode 模型。"""
    node_data = {
        "name": "json_node",
        "value": 100,
    }
    os.environ["TEST_NODE"] = json.dumps(node_data)

    node = from_env(NodeModel, "TEST_NODE")
    assert node.name == "json_node"
    assert node.value == 100


def test_node_model_mixed_parsing(clean_env):
    """使用混合 JSON 和 env 覆盖测试解析 SimpleNode 模型。"""
    # 基础JSON结构
    base_data = {
        "name": "base_name",
        "value": 10,
    }
    os.environ["TEST_NODE"] = json.dumps(base_data)

    # 覆盖值
    os.environ["TEST_NODE_VALUE"] = "99"

    node = from_env(NodeModel, "TEST_NODE")
    assert node.name == "base_name"
    assert node.value == 99


def test_from_env_with_defaults(clean_env):
    """当未设置环境变量时，使用默认值测试 from_env 函数。"""

    class DefaultModel(BaseModel):
        name: str = "default_name"
        count: int = 42
        enabled: bool = True

    # 未设置环境变量
    result = from_env(DefaultModel, "TEST")
    assert result.name == "default_name"
    assert result.count == 42
    assert result.enabled is True


def test_from_env_with_custom_parsers(clean_env):
    """使用自定义解析器覆盖测试 from_env 函数。"""

    class CustomModel(BaseModel):
        value: str

    # 始终返回“custom”的自定义解析器
    class CustomStrParser:
        def from_env(self, key: str):
            return "custom"

    custom_parsers = {str: CustomStrParser()}  # type: ignore[dict-item]
    os.environ["TEST_VALUE"] = "ignored"

    result = from_env(CustomModel, "TEST", custom_parsers)  # type: ignore[arg-type]
    assert result.value == "custom"


def test_error_handling_invalid_json(clean_env):
    """使用环境变量中的无效 JSON 测试错误处理。"""

    class TestModel(BaseModel):
        data: dict[str, str]

    os.environ["TEST_DATA"] = "invalid_json"

    with pytest.raises(json.JSONDecodeError):
        from_env(TestModel, "TEST")


def test_error_handling_unknown_type():
    """测试未知类型的错误处理。"""

    class UnknownType:
        pass

    parsers = {}
    with pytest.raises(ValueError, match="unknown_type"):
        get_env_parser(UnknownType, parsers)


def test_optional_fields_parsing(clean_env):
    """使用可选字段测试解析模型。"""

    class OptionalModel(BaseModel):
        required_field: str
        optional_field: str | None = None
        optional_with_default: str = "default"

    os.environ["TEST_REQUIRED_FIELD"] = "required_value"
    # 不要设置可选字段

    result = from_env(OptionalModel, "TEST")
    assert result.required_field == "required_value"
    assert result.optional_field is None
    assert result.optional_with_default == "default"

    # 现在设置可选字段
    os.environ["TEST_OPTIONAL_FIELD"] = "optional_value"
    result = from_env(OptionalModel, "TEST")
    assert result.optional_field == "optional_value"


def test_complex_nested_structure(clean_env):
    """测试解析复杂的嵌套结构。"""

    class Address(BaseModel):
        street: str
        city: str
        zip_code: str

    class Person(BaseModel):
        name: str
        age: int
        addresses: list[Address]

    # 设置复杂的嵌套数据
    person_data = {
        "name": "John Doe",
        "age": 30,
        "addresses": [
            {"street": "123 Main St", "city": "Anytown", "zip_code": "12345"},
            {"street": "456 Oak Ave", "city": "Other City", "zip_code": "67890"},
        ],
    }
    os.environ["TEST_PERSON"] = json.dumps(person_data)

    # 覆盖一些嵌套值
    os.environ["TEST_PERSON_AGE"] = "35"
    os.environ["TEST_PERSON_ADDRESSES_0_CITY"] = "New City"
    os.environ["TEST_PERSON_ADDRESSES_1_ZIP_CODE"] = "99999"

    result = from_env(Person, "TEST_PERSON")
    assert result.name == "John Doe"
    assert result.age == 35  # 被覆盖
    assert len(result.addresses) == 2

    assert result.addresses[0].street == "123 Main St"
    assert result.addresses[0].city == "New City"  # 被覆盖
    assert result.addresses[0].zip_code == "12345"

    assert result.addresses[1].street == "456 Oak Ave"
    assert result.addresses[1].city == "Other City"
    assert result.addresses[1].zip_code == "99999"  # 被覆盖


def test_optional_parameter_parsing(clean_env):
    os.environ["OP_SUB_TITLE"] = "Present"
    os.environ["OP_SUB_VALUE"] = "10"
    model = from_env(OptionalModel, "OP")
    assert model == OptionalModel(sub=OptionalSubModel(title="Present", value=10))


def test_discriminated_union_parsing(clean_env):
    os.environ["A_KIND"] = "Dog"
    os.environ["A_NAME"] = "Bowser"
    os.environ["A_BARKING"] = "1"
    model = from_env(Animal, "A")
    assert model == Dog(name="Bowser", barking=True)


# ============================================================================
# ENUM PARSING TESTS
# ============================================================================


class SampleEnum(str, Enum):
    """用于解析测试的示例枚举。"""

    OPTION_A = "option_a"
    OPTION_B = "option_b"
    OPTION_C = "option_c"


def test_enum_env_parser_creation():
    """测试枚举类型是否使用正确的值创建 LiteralEnvParser。"""
    parsers = {}
    parser = get_env_parser(SampleEnum, parsers)

    assert isinstance(parser, LiteralEnvParser)
    assert parser.values == ("option_a", "option_b", "option_c")


def test_enum_parsing_valid_values(clean_env):
    """测试从环境变量中解析有效的枚举值。"""

    class EnumModel(BaseModel):
        risk_level: SecurityRisk = SecurityRisk.LOW
        test_option: SampleEnum = SampleEnum.OPTION_A

    # 测试 SecurityRisk 枚举
    os.environ["TEST_RISK_LEVEL"] = "HIGH"
    os.environ["TEST_TEST_OPTION"] = "option_b"

    result = from_env(EnumModel, "TEST")
    assert result.risk_level == SecurityRisk.HIGH
    assert result.test_option == SampleEnum.OPTION_B


def test_enum_parsing_invalid_values(clean_env):
    """测试从环境变量解析无效的枚举值。"""

    class EnumModel(BaseModel):
        risk_level: SecurityRisk = SecurityRisk.LOW

    # 测试无效的枚举值
    os.environ["TEST_RISK_LEVEL"] = "INVALID_RISK"

    # 当提供无效值时应使用默认值
    result = from_env(EnumModel, "TEST")
    assert result.risk_level == SecurityRisk.LOW


def test_enum_parsing_missing_values(clean_env):
    """当枚举环境变量缺失时测试解析。"""

    class EnumModel(BaseModel):
        risk_level: SecurityRisk = SecurityRisk.MEDIUM
        test_option: SampleEnum = SampleEnum.OPTION_C

    # 未设置环境变量 - 应使用默认值
    result = from_env(EnumModel, "TEST")
    assert result.risk_level == SecurityRisk.MEDIUM
    assert result.test_option == SampleEnum.OPTION_C


# ============================================================================
# STRING LITERAL PARSING TESTS
# ============================================================================


def test_literal_env_parser_creation():
    """测试文字类型是否使用正确的值创建 LiteralEnvParser。"""
    type_: type = Literal["red", "green", "blue"]  # type: ignore
    parsers = {}
    parser = get_env_parser(type_, parsers)

    assert isinstance(parser, LiteralEnvParser)
    assert parser.values == ("red", "green", "blue")


def test_literal_parsing_valid_values(clean_env):
    """测试解析环境变量中的有效文字值。"""

    class LiteralModel(BaseModel):
        color: Literal["red", "green", "blue"] = "red"
        size: Literal["small", "medium", "large"] = "medium"

    os.environ["TEST_COLOR"] = "blue"
    os.environ["TEST_SIZE"] = "large"

    result = from_env(LiteralModel, "TEST")
    assert result.color == "blue"
    assert result.size == "large"


def test_literal_parsing_invalid_values(clean_env):
    """测试解析环境变量中的无效文字值。"""

    class LiteralModel(BaseModel):
        color: Literal["red", "green", "blue"] = "red"

    # 测试无效的文字值
    os.environ["TEST_COLOR"] = "purple"

    # 当提供无效值时应使用默认值
    result = from_env(LiteralModel, "TEST")
    assert result.color == "red"


def test_literal_parsing_missing_values(clean_env):
    """当文字环境变量丢失时测试解析。"""

    class LiteralModel(BaseModel):
        color: Literal["red", "green", "blue"] = "green"
        size: Literal["small", "medium", "large"] = "small"

    # 未设置环境变量 - 应使用默认值
    result = from_env(LiteralModel, "TEST")
    assert result.color == "green"
    assert result.size == "small"


def test_literal_env_parser_direct():
    """直接用各种场景测试LiteralEnvParser。"""
    parser = LiteralEnvParser(("alpha", "beta", "gamma"))

    # 测试钥匙丢失
    assert parser.from_env("MISSING_KEY") is MISSING

    # 测试有效值
    os.environ["TEST_LITERAL"] = "alpha"
    assert parser.from_env("TEST_LITERAL") == "alpha"

    os.environ["TEST_LITERAL"] = "beta"
    assert parser.from_env("TEST_LITERAL") == "beta"

    # 测试无效值
    os.environ["TEST_LITERAL"] = "invalid"
    assert parser.from_env("TEST_LITERAL") is MISSING

    # 清理
    del os.environ["TEST_LITERAL"]


# ============================================================================
# TEMPLATE GENERATION (to_env) TESTS
# ============================================================================


def test_bool_env_parser_to_env():
    """测试 BoolEnvParser 模板生成。"""
    parser = BoolEnvParser()
    output = StringIO()

    # 测试True值
    parser.to_env("TEST_BOOL", True, output)
    assert output.getvalue() == "TEST_BOOL=1\n"

    # 测试False值
    output = StringIO()
    parser.to_env("TEST_BOOL", False, output)
    assert output.getvalue() == "TEST_BOOL=0\n"


def test_none_env_parser_to_env():
    """测试 NoneEnvParser 模板生成。"""
    parser = NoneEnvParser()
    output = StringIO()

    # 测试None值
    parser.to_env("TEST_VALUE", None, output)
    assert output.getvalue() == "TEST_VALUE_IS_NONE=1\n"

    # 测试非 None 值（不应产生输出）
    output = StringIO()
    parser.to_env("TEST_VALUE", "not_none", output)
    assert output.getvalue() == ""


def test_literal_env_parser_to_env():
    """测试 LiteralEnvParser 模板生成。"""
    parser = LiteralEnvParser(("red", "green", "blue"))
    output = StringIO()

    parser.to_env("TEST_COLOR", "red", output)
    result = output.getvalue()

    # 应包括允许值注释和实际值
    assert "# Permitted Values: red, green, blue" in result
    assert "TEST_COLOR=red\n" in result


def test_list_env_parser_to_env():
    """测试 ListEnvParser 模板生成。"""
    item_parser = StrEnvParser()
    parser = ListEnvParser(item_parser, str)
    output = StringIO()

    test_list = ["item1", "item2", "item3"]
    parser.to_env("TEST_LIST", test_list, output)
    result = output.getvalue()

    # 应该生成索引环境变量
    assert "TEST_LIST_0=item1\n" in result
    assert "TEST_LIST_1=item2\n" in result
    assert "TEST_LIST_2=item3\n" in result


def test_model_env_parser_to_env():
    """测试 ModelEnvParser 模板生成。"""

    class TestModel(BaseModel):
        name: str = Field(description="The name field")
        count: int = Field(description="The count field")
        enabled: bool = True

    # 创建模型实例
    model = TestModel(name="test", count=42, enabled=False)

    # 生成模板
    template = to_env(model, "TEST_MODEL")

    # 应包括字段描述和值
    assert "# The name field" in template
    assert "# The count field" in template
    assert "TEST_MODEL_NAME=test" in template
    assert "TEST_MODEL_COUNT=42" in template
    assert "TEST_MODEL_ENABLED=0" in template


def test_union_env_parser_to_env():
    """测试 UnionEnvParser 模板生成。"""
    parsers = {str: StrEnvParser(), int: IntEnvParser()}
    parser = UnionEnvParser(parsers)
    output = StringIO()

    # 使用字符串值进行测试
    parser.to_env("TEST_UNION", "hello", output)
    result = output.getvalue()

    # 应包括实际值和注释样本
    assert "TEST_UNION=hello\n" in result


def test_to_env_function_with_enum():
    """使用枚举值测试主 to_env 函数。"""

    class EnumModel(BaseModel):
        risk: SecurityRisk = SecurityRisk.LOW
        option: SampleEnum = SampleEnum.OPTION_A

    model = EnumModel(risk=SecurityRisk.HIGH, option=SampleEnum.OPTION_B)
    template = to_env(model, "TEST")

    # 应为枚举字段生成模板
    assert "TEST_RISK=HIGH" in template
    assert "TEST_OPTION=option_b" in template
    # 应包括允许的值注释
    assert "Permitted Values:" in template


def test_to_env_function_with_literal():
    """使用文字值测试 main to_env 函数。"""

    class LiteralModel(BaseModel):
        color: Literal["red", "green", "blue"] = "red"
        size: Literal["small", "medium", "large"] = "medium"

    model = LiteralModel(color="blue", size="large")
    template = to_env(model, "TEST")

    # 应该为文字字段生成模板
    assert "TEST_COLOR=blue" in template
    assert "TEST_SIZE=large" in template
    # 应包括允许的值注释
    assert "Permitted Values:" in template


def test_to_env_function_with_complex_model():
    """使用复杂的嵌套模型测试 main to_env 函数。"""

    class Address(BaseModel):
        street: str = Field(description="Street address")
        city: str = Field(description="City name")
        zip_code: str = "00000"

    class Person(BaseModel):
        name: str = Field(description="Person's name")
        age: int = Field(description="Person's age")
        addresses: list[Address] = Field(
            default_factory=list, description="List of addresses"
        )
        risk_level: SecurityRisk = SecurityRisk.LOW

    # 创建复杂模型实例
    person = Person(
        name="John Doe",
        age=30,
        addresses=[
            Address(street="123 Main St", city="Anytown", zip_code="12345"),
            Address(street="456 Oak Ave", city="Other City", zip_code="67890"),
        ],
        risk_level=SecurityRisk.MEDIUM,
    )

    template = to_env(person, "PERSON")

    # 应包含字段描述
    assert "# Person's name" in template
    assert "# Person's age" in template
    assert "# List of addresses" in template
    assert "# Street address" in template
    assert "# City name" in template

    # 应包含嵌套结构
    assert "PERSON_NAME=John Doe" in template
    assert "PERSON_AGE=30" in template
    assert "PERSON_ADDRESSES_0_STREET=123 Main St" in template
    assert "PERSON_ADDRESSES_0_CITY=Anytown" in template
    assert "PERSON_ADDRESSES_0_ZIP_CODE=12345" in template
    assert "PERSON_ADDRESSES_1_STREET=456 Oak Ave" in template
    assert "PERSON_ADDRESSES_1_CITY=Other City" in template
    assert "PERSON_ADDRESSES_1_ZIP_CODE=67890" in template
    assert "PERSON_RISK_LEVEL=MEDIUM" in template


def test_to_env_function_with_none_values():
    """使用 None 值测试主 to_env 函数。"""

    class OptionalModel(BaseModel):
        required_field: str
        optional_field: str | None = None
        another_optional: int | None = None

    model = OptionalModel(
        required_field="required", optional_field=None, another_optional=42
    )

    template = to_env(model, "TEST")

    # 应处理带有 _IS_NONE 后缀的 None 值
    assert "TEST_REQUIRED_FIELD=required" in template
    assert "TEST_OPTIONAL_FIELD_IS_NONE=1" in template
    assert "TEST_ANOTHER_OPTIONAL=42" in template


def test_to_env_function_with_boolean_values():
    """使用布尔值测试 main to_env 函数。"""

    class BoolModel(BaseModel):
        enabled: bool = True
        disabled: bool = False
        maybe: bool | None = None

    model = BoolModel(enabled=True, disabled=False, maybe=None)
    template = to_env(model, "BOOL_TEST")

    # 应将布尔值转换为 1/0
    assert "BOOL_TEST_ENABLED=1" in template
    assert "BOOL_TEST_DISABLED=0" in template
    assert "BOOL_TEST_MAYBE_IS_NONE=1" in template


# ============================================================================
# DISCRIMINATED UNION ENV PARSER TESTS
# ============================================================================


def test_discriminated_union_single_kind_uses_parser_directly(clean_env):
    """测试 DiscriminatedUnionEnvParser 是否直接使用解析器
    只有一种。"""
    # 创建单个解析器
    single_parser = ModelEnvParser(
        parsers={"name": StrEnvParser(), "barking": BoolEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(parsers={"Dog": single_parser})

    # 设置环境不带KIND
    os.environ["TEST_NAME"] = "Fido"
    os.environ["TEST_BARKING"] = "1"

    # 应该直接使用单个解析器而不需要 KIND
    result = parser.from_env("TEST")
    assert result == {"name": "Fido", "barking": True, "kind": "Dog"}


def test_discriminated_union_multiple_kinds_requires_kind(clean_env):
    """测试当有多个时 DiscriminatedUnionEnvParser 返回 MISSING
    种类且未设置 KIND。"""
    # 创建多个解析器
    dog_parser = ModelEnvParser(
        parsers={"name": StrEnvParser(), "barking": BoolEnvParser()},
        descriptions={},
    )
    cat_parser = ModelEnvParser(
        parsers={"name": StrEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(parsers={"Dog": dog_parser, "Cat": cat_parser})

    # 设置环境不带KIND
    os.environ["TEST_NAME"] = "Fido"
    os.environ["TEST_BARKING"] = "1"

    # 应返回 MISSING，因为有多种且未设置 KIND
    result = parser.from_env("TEST")
    assert result is MISSING


def test_discriminated_union_multiple_kinds_with_kind_set(clean_env):
    """测试 KIND 时 DiscriminatedUnionEnvParser 是否正常工作
    明确设定。"""
    # 创建多个解析器
    dog_parser = ModelEnvParser(
        parsers={"name": StrEnvParser(), "barking": BoolEnvParser()},
        descriptions={},
    )
    cat_parser = ModelEnvParser(
        parsers={"name": StrEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(parsers={"Dog": dog_parser, "Cat": cat_parser})

    # 使用 KIND 设置环境
    os.environ["TEST_KIND"] = "Dog"
    os.environ["TEST_NAME"] = "Fido"
    os.environ["TEST_BARKING"] = "1"

    result = parser.from_env("TEST")
    assert result == {"name": "Fido", "barking": True, "kind": "Dog"}


def test_discriminated_union_zero_kinds_returns_missing(clean_env):
    """测试当没有种类时 DiscriminatedUnionEnvParser 返回 MISSING。"""
    parser = DiscriminatedUnionEnvParser(parsers={})

    os.environ["TEST_NAME"] = "Fido"

    # 应该返回 MISSING 因为没有解析器
    result = parser.from_env("TEST")
    assert result is MISSING


def test_discriminated_union_full_class_name_imports_and_registers(clean_env):
    """测试 DiscriminatedUnionEnvParser 是否处理带点的完整类名。"""
    # 从空解析器开始
    parser = DiscriminatedUnionEnvParser(parsers={})

    # 将 KIND 设置为完整的类名（使用测试 Dog 类）
    os.environ["TEST_KIND"] = "tests.sdk.utils.test_discriminated_union.Dog"
    os.environ["TEST_NAME"] = "Fido"
    os.environ["TEST_BARKING"] = "1"

    result = parser.from_env("TEST")

    # 应该导入类，创建解析器并返回数据
    assert result == {"name": "Fido", "barking": True, "kind": "Dog"}
    # 现在应该使用非限定类名注册解析器
    assert "Dog" in parser.parsers


def test_discriminated_union_full_class_name_already_registered(clean_env):
    """测试类已注册时完整的类名是否有效。"""
    # 预注册一个 Dog 解析器
    dog_parser = ModelEnvParser(
        parsers={"name": StrEnvParser(), "barking": BoolEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(parsers={"Dog": dog_parser})

    # 将 KIND 设置为已注册类的完整类名
    os.environ["TEST_KIND"] = "tests.sdk.utils.test_discriminated_union.Dog"
    os.environ["TEST_NAME"] = "Rex"
    os.environ["TEST_BARKING"] = "0"

    result = parser.from_env("TEST")

    # 应该使用现有的解析器（而不是重新导入）
    assert result == {"name": "Rex", "barking": False, "kind": "Dog"}


def test_discriminated_union_full_class_name_different_classes(clean_env):
    """测试是否可以使用多个完整类名来导入不同的类。"""
    parser = DiscriminatedUnionEnvParser(parsers={})

    # 首先，使用完整的类名导入 Dog
    os.environ["TEST_KIND"] = "tests.sdk.utils.test_discriminated_union.Dog"
    os.environ["TEST_NAME"] = "Fido"
    os.environ["TEST_BARKING"] = "1"

    result = parser.from_env("TEST")
    assert result == {"name": "Fido", "barking": True, "kind": "Dog"}
    assert "Dog" in parser.parsers

    # 清理干净以备下次测试
    del os.environ["TEST_BARKING"]

    # 现在使用完整的类名导入 Cat
    os.environ["TEST_KIND"] = "tests.sdk.utils.test_discriminated_union.Cat"
    os.environ["TEST_NAME"] = "Whiskers"

    result = parser.from_env("TEST")
    assert result == {"name": "Whiskers", "kind": "Cat"}
    assert "Cat" in parser.parsers
    # 两个解析器现在都应该注册
    assert len(parser.parsers) == 2


def test_discriminated_union_full_class_name_invalid_module(clean_env):
    """测试无效模块名称是否引发 ImportError。"""
    parser = DiscriminatedUnionEnvParser(parsers={})

    os.environ["TEST_KIND"] = "nonexistent.module.SomeClass"
    os.environ["TEST_NAME"] = "Test"

    with pytest.raises(ModuleNotFoundError):
        parser.from_env("TEST")


def test_discriminated_union_full_class_name_invalid_class(clean_env):
    """测试无效的类名是否引发 AttributeError。"""
    parser = DiscriminatedUnionEnvParser(parsers={})

    os.environ["TEST_KIND"] = (
        "tests.sdk.utils.test_discriminated_union.NonexistentClass"
    )
    os.environ["TEST_NAME"] = "Test"

    with pytest.raises(AttributeError):
        parser.from_env("TEST")


def test_discriminated_union_kind_only_no_other_variables(clean_env):
    """测试 DiscriminatedUnionEnvParser 处理仅定义一种的类型
    没有任何其他变量。"""
    # 创建一个没有附加字段的解析器（返回 MISSING 的空解析器）
    empty_parser = ModelEnvParser(parsers={}, descriptions={})
    parser = DiscriminatedUnionEnvParser(parsers={"EmptyKind": empty_parser})

    # 设置 KIND，但没有其他环境变量
    os.environ["TEST_KIND"] = "EmptyKind"

    # 应该只返回类型，而不是 MISSING
    result = parser.from_env("TEST")
    assert result == {"kind": "EmptyKind"}


def test_discriminated_union_kind_only_multiple_kinds(clean_env):
    """测试当KIND设置为多种类型中无字段的类型时，
    它仍然可以正常工作。"""
    # 创建解析器 - 一种带有字段，一种不带有字段
    empty_parser = ModelEnvParser(parsers={}, descriptions={})
    dog_parser = ModelEnvParser(
        parsers={"name": StrEnvParser(), "barking": BoolEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(
        parsers={"EmptyKind": empty_parser, "Dog": dog_parser}
    )

    # 将KIND设置为空类型
    os.environ["TEST_KIND"] = "EmptyKind"

    # 应该返回那种
    result = parser.from_env("TEST")
    assert result == {"kind": "EmptyKind"}


def test_discriminated_union_no_kind_no_variables_returns_missing(clean_env):
    """测试当 KIND 未设置并且解析器返回 MISSING 时，
    结果是 MISSING （不是没有类型的空字典）。"""
    # 创建一个没有附加字段的解析器
    empty_parser = ModelEnvParser(parsers={}, descriptions={})
    non_empty_parser = ModelEnvParser(
        parsers={"name": StrEnvParser()},
        descriptions={},
    )
    parser = DiscriminatedUnionEnvParser(
        parsers={"EmptyKind": empty_parser, "NonEmpty": non_empty_parser}
    )

    # 不要设置KIND或任何其他变量应该返回MISSING，因为有多种并且没有设置KIND
    #
    result = parser.from_env("TEST")
    assert result is MISSING


def test_discriminated_union_single_empty_kind_no_variables(clean_env):
    """测试当只有一种空类型并且没有设置环境变量时，
    结果是 MISSING（该条目未配置）。"""
    # 创建一个空解析器
    empty_parser = ModelEnvParser(parsers={}, descriptions={})
    parser = DiscriminatedUnionEnvParser(parsers={"EmptyKind": empty_parser})

    # 不要设置任何环境变量（甚至 KIND），单个类型应该尝试解析器，但仍然返回 MISSING，因
    # 为没有迹象表明这个条目已配置
    #
    result = parser.from_env("TEST")
    assert result is MISSING


def test_config_lease_ttl_seconds_default(clean_env):
    config = from_env(Config, "OH")
    assert config.lease_ttl_seconds == DEFAULT_LEASE_TTL_SECONDS


def test_config_lease_ttl_seconds_env_var(clean_env):
    os.environ["OH_LEASE_TTL_SECONDS"] = "0"
    config = from_env(Config, "OH")
    assert config.lease_ttl_seconds == 0.0
