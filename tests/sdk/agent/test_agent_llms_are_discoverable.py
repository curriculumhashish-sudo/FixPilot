from pydantic import Field

from openhands.sdk import LLM, Agent, LLMSummarizingCondenser
from openhands.sdk.llm.router import MultimodalRouter


def check_usage_id_exists(usage_id: str, llms: list[LLM]):
    usage_ids = [llm.usage_id for llm in llms]
    return usage_id in usage_ids


# 在模块级别定义 CustomAgent 以避免序列化测试期间出现“不支持本地类”错误。 局部类（在函数
# 内部定义）不能是已反序列化，因为它们在反序列化时可能不存在。
#
class CustomAgentWithRouters(Agent):
    """带有附加 LLM 路由器的自定义智能体，用于测试 LLM 发现。"""

    model_routers: list[LLM] = Field(default_factory=list)


def test_automatic_llm_discovery():
    llm_usage_id = "main-agent"
    agent = Agent(llm=LLM(model="test-model", usage_id=llm_usage_id))

    llms = list(agent.get_all_llms())
    assert len(llms) == 1
    assert check_usage_id_exists(llm_usage_id, llms)


def test_automatic_llm_discovery_for_multiple_llms():
    llm_usage_id = "main-agent"
    condenser_usage_id = "condenser"

    condenser = LLMSummarizingCondenser(
        llm=LLM(model="test-model", usage_id=condenser_usage_id)
    )

    agent = Agent(
        llm=LLM(model="test-model", usage_id=llm_usage_id), condenser=condenser
    )

    llms = list(agent.get_all_llms())
    assert len(llms) == 2
    assert check_usage_id_exists(llm_usage_id, llms)
    assert check_usage_id_exists(condenser_usage_id, llms)


def test_automatic_llm_discovery_for_custom_agent_with_duplicates():
    llm_usage_id = "main-agent"
    router_usage_id = "secondary_llm"
    router_usage_id_2 = "tertiary_llm"
    condenser_usage_id = "condenser"

    condenser = LLMSummarizingCondenser(
        llm=LLM(model="test-model", usage_id=condenser_usage_id)
    )

    agent_llm = LLM(model="test-model", usage_id=llm_usage_id)
    router_llm = LLM(model="test-model", usage_id=router_usage_id)
    router_llm_2 = LLM(model="test-model", usage_id=router_usage_id_2)

    agent = CustomAgentWithRouters(
        llm=agent_llm,
        condenser=condenser,
        model_routers=[agent_llm, router_llm, router_llm_2],
    )

    llms = list(agent.get_all_llms())
    assert len(llms) == 4
    assert check_usage_id_exists(llm_usage_id, llms)
    assert check_usage_id_exists(router_usage_id, llms)
    assert check_usage_id_exists(router_usage_id_2, llms)
    assert check_usage_id_exists(condenser_usage_id, llms)


def test_automatic_llm_discovery_with_multimodal_router():
    """测试 LLMs 和 MultimodalRouter 是否正确被发现。"""
    primary_usage_id = "primary-llm"
    secondary_usage_id = "secondary-llm"

    # 为路由器创建 LLMs
    primary_llm = LLM(model="test-primary-model", usage_id=primary_usage_id)
    secondary_llm = LLM(model="test-secondary-model", usage_id=secondary_usage_id)

    # 创建 MultimodalRouter with the LLMs
    multimodal_router = MultimodalRouter(
        usage_id="multimodal-router",
        llms_for_routing={"primary": primary_llm, "secondary": secondary_llm},
    )

    # 使用路由器创建智能体
    agent = Agent(llm=multimodal_router)

    # 获取所有 LLMs 并验证它们已发现
    llms = list(agent.get_all_llms())

    # 仅限原始 LLMs 应在路由器内部找到（而不是路由器本身）
    assert len(llms) == 2
    assert check_usage_id_exists(primary_usage_id, llms)
    assert check_usage_id_exists(secondary_usage_id, llms)


def test_automatic_llm_discovery_with_llm_as_base_class():
    class NewLLM(LLM):
        list_llms: list[LLM] = Field(default_factory=list)
        dict_llms: dict[str, LLM] = Field(default_factory=dict)
        raw_llm: LLM | None = None

    list_llm = LLM(model="list-model", usage_id="list-model")
    dict_llm = LLM(model="dict-model", usage_id="dict-model")
    raw_llm = LLM(model="raw_llm", usage_id="raw_llm")

    new_llm = NewLLM(
        model="new-llm-type",
        usage_id="new-llm-test",
        list_llms=[list_llm],
        dict_llms={"key": dict_llm},
        raw_llm=raw_llm,
    )

    agent = Agent(llm=new_llm)
    llms = list(agent.get_all_llms())

    assert len(llms) == 3
