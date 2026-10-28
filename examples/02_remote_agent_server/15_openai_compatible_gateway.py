"""通过 OpenAI 兼容的聊天完成客户端使用智能体服务器。

这是一个示例，启动了一个本地智能体服务器，存储了一个LLM配置，并通过它列出
``GET /v1/models``，然后用 OpenAI Python SDK 调用 ``POST /v1/chat/completions``。 返
回的
``X-OpenHands-ServerConversation-ID`` 标头将在第二次调用时传回，以继续相同的
OpenHands 对话。
"""

import os
from uuid import UUID

import httpx
from openai import OpenAI
from scripts.utils import ManagedAPIServer


# 网关运行完整的 OpenHands 智能体，但 OpenAI 客户端仍然需要一个正常的类似模型的名称。 我
# 们在下面创建一个 LLM 配置文件并将其公开为
# `openhands_<profile_name>` 到 `/v1/models`。

api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
assert api_key is not None, "Set LLM_API_KEY or OPENAI_API_KEY."

llm_model = os.getenv("LLM_MODEL", "gpt-5-nano")
llm_base_url = os.getenv("LLM_BASE_URL")
profile_name = "gateway_demo"
gateway_model = f"openhands_{profile_name}"

# 启动本地智能体-服务器进行演示。 `use_session_api_key=True`开启身份验证； 相同的密钥既
# 可用作本机智能体服务器路由的 `X-Session-API-Key`，也可用作 OpenAI SDK 调用的
# `Authorization: Bearer ...`。
#

with ManagedAPIServer(
    port=8770,
    use_session_api_key=True,
    extra_env={
        "OH_ENABLE_VSCODE": "0",
        "OH_PRELOAD_TOOLS": "0",
        "OH_SECRET_KEY": "example-secret-key-for-demo-only-32b",
        "OH_WEBHOOKS": "[]",
    },
    health_request_timeout=2.0,
) as server:
    session_api_key = (
        os.getenv("SESSION_API_KEY")
        or os.getenv("OH_SESSION_API_KEYS_0")
        or server.session_api_key
    )
    assert session_api_key is not None

    # 使用本机 REST API 一次来创建支持网关模型的配置文件。 此后，正常的 OpenAI SDK 呼叫
    # 足以满足聊天流量。
    #
    api_client = httpx.Client(
        base_url=server.base_url,
        headers={"X-Session-API-Key": session_api_key},
        timeout=120.0,
    )
    openai_client = OpenAI(
        api_key=session_api_key,
        base_url=f"{server.base_url}/v1",
        timeout=120.0,
    )

    llm_config = {"model": llm_model, "api_key": api_key}
    if llm_base_url:
        llm_config["base_url"] = llm_base_url

    # `gateway_demo` 对 OpenAI 客户端可见为 `openhands_gateway_demo`。
    profile_response = api_client.post(
        f"/api/profiles/{profile_name}",
        json={"llm": llm_config, "include_secrets": True},
    )
    assert profile_response.status_code == 201, profile_response.text

    models = openai_client.models.list()
    model_ids = [model.id for model in models.data]
    assert gateway_model in model_ids
    print(f"Gateway models include: {gateway_model}")

    # 通过OpenAISDK询问。 `with_raw_response` 让我们读取自定义响应标头，该标头标识了在此
    #  OpenAI 形状的请求背后创建的 OpenHands 对话。
    #

    first_response = openai_client.chat.completions.with_raw_response.create(
        model=gateway_model,
        messages=[
            {
                "role": "system",
                "content": "Answer directly and do not use tools.",
            },
            {
                "role": "user",
                "content": (
                    "In one sentence, explain what an OpenAI-compatible "
                    "agent-server gateway does."
                ),
            },
        ],
    )
    first_completion = first_response.parse()
    conversation_id = first_response.headers.get("X-OpenHands-ServerConversation-ID")
    assert conversation_id is not None
    UUID(conversation_id)

    first_answer = first_completion.choices[0].message.content
    print(f"First answer: {first_answer}")
    print(f"OpenHands conversation ID: {conversation_id}")

    persisted_response = api_client.get(f"/api/conversations/{conversation_id}")
    assert persisted_response.status_code == 200, persisted_response.text

    # 网关默认保留对话。 传回标头可以让另一个 OpenAI 兼容的请求继续相同的服务器端智能体
    # 对话，而不是重新开始。
    #

    second_completion = openai_client.chat.completions.create(
        model=gateway_model,
        messages=[
            {
                "role": "user",
                "content": "Now answer in five words or fewer: what did I ask about?",
            }
        ],
        extra_headers={"X-OpenHands-ServerConversation-ID": conversation_id},
    )
    second_answer = second_completion.choices[0].message.content
    print(f"Second answer using same conversation: {second_answer}")

    conversation_response = api_client.get(f"/api/conversations/{conversation_id}")
    assert conversation_response.status_code == 200, conversation_response.text
    stats = conversation_response.json().get("stats") or {}
    usage_to_metrics = stats.get("usage_to_metrics") or {}
    accumulated_cost = sum(
        metrics.get("accumulated_cost", 0.0) for metrics in usage_to_metrics.values()
    )

    # 清理演示资源。 真实应用程序可以保留对话 ID，并在以后通过本机智能体-服务器 API 检查
    # 它。
    #
    api_client.delete(f"/api/conversations/{conversation_id}")
    api_client.delete(f"/api/profiles/{profile_name}")
    api_client.close()

    print(f"EXAMPLE_COST: {accumulated_cost}")
