"""测试 Agent._extract_security_risk 方法。

该模块测试处理从工具参数中提取安全风险参数的 _extract_security_risk 方法和验证方法。
"""

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import LLM
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.security.risk import SecurityRisk


class MockNonLLMAnalyzer(SecurityAnalyzerBase):
    """模拟对象一个不是 LLMSecurityAnalyzer 的安全分析器。"""

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        return SecurityRisk.LOW


@pytest.fixture
def mock_llm():
    """创建模拟对象 LLM 进行测试。"""
    return LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )


@pytest.fixture
def agent_with_llm_analyzer(mock_llm):
    """创建一个智能体与 LLMSecurityAnalyzer."""
    agent = Agent(llm=mock_llm)
    return agent, LLMSecurityAnalyzer()


@pytest.fixture
def agent_with_non_llm_analyzer(mock_llm):
    """使用非 LLM 安全分析器创建智能体。"""
    agent = Agent(llm=mock_llm)
    return agent, MockNonLLMAnalyzer()


@pytest.fixture
def agent_without_analyzer(mock_llm):
    """创建一个不带安全分析器的智能体。"""
    agent = Agent(llm=mock_llm)
    return agent, None


@pytest.mark.parametrize(
    "agent_fixture,security_risk_value,expected_result,should_raise",
    [
        # 案例1：LLM分析器设置，安全风险已通过，正确提取
        ("agent_with_llm_analyzer", "LOW", SecurityRisk.LOW, False),
        ("agent_with_llm_analyzer", "MEDIUM", SecurityRisk.MEDIUM, False),
        ("agent_with_llm_analyzer", "HIGH", SecurityRisk.HIGH, False),
        ("agent_with_llm_analyzer", "UNKNOWN", SecurityRisk.UNKNOWN, False),
        # 情况2：非LLM分析器设置，安全风险通过，正确提取
        ("agent_with_non_llm_analyzer", "LOW", SecurityRisk.LOW, False),
        ("agent_with_non_llm_analyzer", "MEDIUM", SecurityRisk.MEDIUM, False),
        ("agent_with_non_llm_analyzer", "HIGH", SecurityRisk.HIGH, False),
        ("agent_with_non_llm_analyzer", "UNKNOWN", SecurityRisk.UNKNOWN, False),
        # 情况3：未设置分析器，安全风险已通过，应忽略（返回UNKNOWN）
        #
        ("agent_without_analyzer", "LOW", SecurityRisk.UNKNOWN, False),
        ("agent_without_analyzer", "MEDIUM", SecurityRisk.UNKNOWN, False),
        ("agent_without_analyzer", "HIGH", SecurityRisk.UNKNOWN, False),
        ("agent_without_analyzer", "UNKNOWN", SecurityRisk.UNKNOWN, False),
        # 情况 4：安全风险未通过 -> 无论分析器如何，默认为 UNKNOWN
        ("agent_with_llm_analyzer", None, SecurityRisk.UNKNOWN, False),
        ("agent_with_non_llm_analyzer", None, SecurityRisk.UNKNOWN, False),
        ("agent_without_analyzer", None, SecurityRisk.UNKNOWN, False),
        # 情况5：传递的安全风险值无效
        # - 使用 LLM 分析器：ValueError 因无效枚举而引发
        # - 对于非 LLM 分析器：ValueError 因无效枚举而引发
        # - 没有分析器：忽略，返回 UNKNOWN（未尝试验证）
        ("agent_with_llm_analyzer", "INVALID", None, True),
        ("agent_with_non_llm_analyzer", "INVALID", None, True),
        ("agent_without_analyzer", "INVALID", SecurityRisk.UNKNOWN, False),
    ],
)
def test_extract_security_risk(
    request, agent_fixture, security_risk_value, expected_result, should_raise
):
    """使用各种场景测试 _extract_security_risk 方法。"""
    # 获取智能体测试夹具
    agent, security_analyzer = request.getfixturevalue(agent_fixture)

    # 准备论点
    arguments = {"some_param": "value"}
    if security_risk_value is not None:
        arguments["security_risk"] = security_risk_value

    if should_raise:
        with pytest.raises(ValueError):
            agent._extract_security_risk(arguments, False, security_analyzer)
    else:
        result = agent._extract_security_risk(arguments, False, security_analyzer)
        assert result == expected_result

        # 验证 security_risk 是否已从参数中弹出
        assert "security_risk" not in arguments
        # 验证其他参数是否仍然存在
        assert arguments["some_param"] == "value"


def test_extract_security_risk_arguments_mutation():
    """测试参数 dict 是否正确变异（security_risk 被弹出）。"""
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )

    # 使用 security_risk 存在但没有分析器进行测试（应忽略）
    arguments = {"param1": "value1", "security_risk": "LOW", "param2": "value2"}
    original_args = arguments.copy()

    result = agent._extract_security_risk(arguments, False, None)

    # 未设置分析器时验证结果为 UNKNOWN（security_risk 被忽略）
    assert result == SecurityRisk.UNKNOWN

    # 验证 security_risk 已弹出
    assert "security_risk" not in arguments

    # 验证其他参数是否仍然有效
    assert arguments["param1"] == original_args["param1"]
    assert arguments["param2"] == original_args["param2"]
    assert len(arguments) == 2  # 只应保留 2 个参数


def test_extract_security_risk_with_empty_arguments():
    """使用空参数 dict 测试 _extract_security_risk。"""
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )

    arguments = {}
    result = agent._extract_security_risk(arguments, False, None)

    # 当没有分析器且没有 security_risk 时应返回 UNKNOWN
    assert result == SecurityRisk.UNKNOWN
    assert arguments == {}  # 应保持为空


def test_extract_security_risk_with_read_only_tool():
    """使用只读工具测试 _extract_security_risk。"""
    agent = Agent(
        llm=LLM(
            usage_id="test-llm",
            model="test-model",
            api_key=SecretStr("test-key"),
            base_url="http://test",
        )
    )

    # 使用 readOnlyHint=True 进行测试 - 无论 security_risk 为何，都应返回 UNKNOWN
    arguments = {"param1": "value1", "security_risk": "HIGH"}
    result = agent._extract_security_risk(arguments, True, LLMSecurityAnalyzer())

    # 当 read_only_tool 为 True 时应返回 UNKNOWN
    assert result == SecurityRisk.UNKNOWN
    # security_risk 仍应从参数中弹出
    assert "security_risk" not in arguments
    assert arguments["param1"] == "value1"
