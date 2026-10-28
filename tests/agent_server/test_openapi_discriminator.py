"""
测试 OpenAPI 中的可区分联合模式是否具有适当的鉴别器字段。

这确保 Swagger UI 能正确显示枚举类型，而不是显示为 "object | object | object..."。
"""

import pytest
from fastapi.testclient import TestClient

from openhands.agent_server.api import create_app


@pytest.fixture
def client():
    """为 API 创建一个测试客户端。"""
    return TestClient(create_app())


def test_action_schema_has_discriminator(client):
    """测试 Action 模式是否具有正确的鉴别器字段。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()

    # 检查操作模式是否存在
    assert "components" in openapi_schema
    assert "schemas" in openapi_schema["components"]
    schemas = openapi_schema["components"]["schemas"]

    names = ["Action"] if "Action" in schemas else ["Action-Input", "Action-Output"]
    for name in names:
        assert name in schemas, f"{name} schema should be in components/schemas"
        action_schema = schemas[name]

        assert "oneOf" in action_schema, f"{name} should have oneOf field"
        assert action_schema["oneOf"], f"{name} should have at least one variant"
        for variant in action_schema["oneOf"]:
            assert "$ref" in variant, f"Each variant should be a $ref, got: {variant}"

        assert "discriminator" in action_schema, (
            f"{name} should have discriminator field for proper OpenAPI documentation"
        )
        assert action_schema["discriminator"]["propertyName"] == "kind"


def test_observation_schema_has_discriminator(client):
    """测试观测结果模式是否具有正确的鉴别器字段。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()
    schemas = openapi_schema["components"]["schemas"]

    # 观测结果模式也应该存在并且有鉴别器
    if "Observation" in schemas:
        observation_schema = schemas["Observation"]

        if "oneOf" in observation_schema:
            # 检查它是否有鉴别器
            assert "discriminator" in observation_schema, (
                "Observation should have discriminator field"
            )

            discriminator = observation_schema["discriminator"]
            assert "propertyName" in discriminator, (
                "discriminator should have propertyName field"
            )
            assert discriminator["propertyName"] == "kind", (
                "discriminator propertyName should be 'kind'"
            )


def test_event_schema_has_discriminator(client):
    """如果事件模式使用 oneOf，则测试它是否具有正确的鉴别器字段。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()
    schemas = openapi_schema["components"]["schemas"]

    # 事件模式也可能是受歧视的工会
    if "Event" in schemas:
        event_schema = schemas["Event"]

        if "oneOf" in event_schema:
            # 检查它是否有鉴别器
            assert "discriminator" in event_schema, (
                "Event should have discriminator field"
            )

            discriminator = event_schema["discriminator"]
            assert "propertyName" in discriminator, (
                "discriminator should have propertyName field"
            )
            assert discriminator["propertyName"] == "kind", (
                "discriminator propertyName should be 'kind'"
            )


def test_action_variants_have_proper_schemas(client):
    """测试操作变体（FinishAction 等）是否具有正确的模式。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()
    schemas = openapi_schema["components"]["schemas"]

    action_schema = schemas.get("Action", {})
    one_of = action_schema.get("oneOf", [])

    # 从 $refs 中提取操作类型名称
    action_types = []
    for variant in one_of:
        ref = variant.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            type_name = ref.split("/")[-1]
            action_types.append(type_name)

    # 检查引用的模式是否存在并且是正确的对象
    for action_type in action_types:
        assert action_type in schemas, f"{action_type} should be in schemas"

        type_schema = schemas[action_type]

        # 应该是一个对象
        assert type_schema.get("type") == "object", f"{action_type} should be an object"

        # 应该有属性
        assert "properties" in type_schema, f"{action_type} should have properties"

        # 应该有 kind 字段，其 const 值与类型名称匹配
        properties = type_schema["properties"]
        assert "kind" in properties, f"{action_type} should have 'kind' field"

        kind_field = properties["kind"]
        assert "const" in kind_field or "enum" in kind_field, (
            f"{action_type}.kind should have const or enum"
        )

        # 如果是 const，它应该与类型名称匹配
        if "const" in kind_field:
            assert kind_field["const"] == action_type, (
                f"{action_type}.kind const should be '{action_type}'"
            )

        # 应该有标题
        assert "title" in type_schema, (
            f"{action_type} should have title for better docs"
        )


def test_conversation_contracts_use_unified_acp_capable_endpoint(client):
    """主要对话端点接受 OpenHands 和 ACP 智能体。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()
    schemas = openapi_schema["components"]["schemas"]

    request = schemas["StartConversationRequest"]
    agent_property = request["properties"]["agent"]
    agent_ref = agent_property.get("$ref") or agent_property["anyOf"][0]["$ref"]
    agent_schema = schemas[agent_ref.split("/")[-1]]
    assert "oneOf" in agent_schema
    refs = {variant["$ref"] for variant in agent_schema["oneOf"]}
    assert "#/components/schemas/Agent-Input" in refs
    assert "#/components/schemas/ACPAgent-Input" in refs
    assert "agent_settings" in request["properties"]
    assert "agent" not in request.get("required", [])

    response_schema = schemas["ConversationInfo"]
    response_agent_schema = schemas[
        response_schema["properties"]["agent"]["$ref"].split("/")[-1]
    ]
    assert "oneOf" in response_agent_schema
    response_refs = {variant["$ref"] for variant in response_agent_schema["oneOf"]}
    assert "#/components/schemas/Agent-Output" in response_refs
    assert "#/components/schemas/ACPAgent-Output" in response_refs
    assert "ACPConversationInfo" not in schemas

    page_schema = schemas["ConversationPage"]
    page_items = page_schema["properties"]["items"]["items"]
    assert page_items["$ref"] == "#/components/schemas/ConversationInfo"

    assert "/api/v2/conversations" not in openapi_schema["paths"]
    assert "/api/conversations" in openapi_schema["paths"]
    # 已弃用 /api/acp/conversations 路由在 v1.27.0 中被删除。
    assert "/api/acp/conversations" not in openapi_schema["paths"]
