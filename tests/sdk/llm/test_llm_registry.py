from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock, patch

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_registry import LLMRegistry, RegistryEvent


class TestLLMRegistry(unittest.TestCase):
    def setUp(self):
        """每次测试前设置测试环境。"""
        # 创建注册表用于测试
        self.registry: LLMRegistry = LLMRegistry()

    def test_subscribe_and_notify(self):
        """测试订阅和通知系统。"""
        events_received = []

        def callback(event: RegistryEvent):
            events_received.append(event)

        # 订阅活动
        self.registry.subscribe(callback)

        # 创建模拟对象LLM并添加触发通知
        mock_llm = Mock(spec=LLM)
        mock_llm.usage_id = "notify-service"

        # 模拟对象RegistryEvent避免LLM属性访问
        with patch(
            "openhands.sdk.llm.llm_registry.RegistryEvent"
        ) as mock_registry_event:
            mock_registry_event.return_value = Mock()
            self.registry.add(mock_llm)

        # 应该收到新添加的通知 LLM
        self.assertEqual(len(events_received), 1)

        # 测试订阅者设置是否正确
        self.assertIsNotNone(self.registry.subscriber)

        # 直接使用模拟对象事件测试通知方法
        with patch.object(self.registry, "subscriber") as mock_subscriber:
            mock_event = MagicMock()
            self.registry.notify(mock_event)
            mock_subscriber.assert_called_once_with(mock_event)

    def test_registry_has_unique_id(self):
        """测试每个注册表实例是否具有唯一的 ID。"""
        registry2 = LLMRegistry()
        self.assertNotEqual(self.registry.registry_id, registry2.registry_id)
        self.assertTrue(len(self.registry.registry_id) > 0)
        self.assertTrue(len(registry2.registry_id) > 0)


def test_llm_registry_notify_exception_handling():
    """测试 LLM 注册表处理订户通知中的异常。"""

    # 创建引发异常的订阅者
    def failing_subscriber(event):
        raise ValueError("Subscriber failed")

    registry = LLMRegistry()
    registry.subscribe(failing_subscriber)

    # 模拟对象记录器捕获警告消息
    with patch("openhands.sdk.llm.llm_registry.logger") as mock_logger:
        # 创建模拟对象事件
        mock_event = Mock()

        # 这应该处理异常并记录警告（第 146-147 行）
        registry.notify(mock_event)

        # 应该记录警告
        mock_logger.warning.assert_called_once()
        assert "Failed to emit event:" in str(mock_logger.warning.call_args)


def test_llm_registry_list_usage_ids():
    """测试LLM注册表list_usage_ids方法。"""

    registry = LLMRegistry()

    # 创建模拟对象 LLM 个对象
    mock_llm1 = Mock(spec=LLM)
    mock_llm1.usage_id = "service1"
    mock_llm2 = Mock(spec=LLM)
    mock_llm2.usage_id = "service2"

    # 模拟对象RegistryEvent避免LLM属性访问
    with patch("openhands.sdk.llm.llm_registry.RegistryEvent") as mock_registry_event:
        mock_registry_event.return_value = Mock()

        # 添加一些 LLMs 使用新的 API
        registry.add(mock_llm1)
        registry.add(mock_llm2)

        # 测试 list_usage_ids
        usage_ids = registry.list_usage_ids()

        assert "service1" in usage_ids
        assert "service2" in usage_ids
        assert len(usage_ids) == 2


def test_llm_registry_remove_method():
    """remove() 删除已注册的使用 ID，并且在不存在时为无操作。"""

    registry = LLMRegistry()

    mock_llm = Mock(spec=LLM)
    mock_llm.usage_id = "service1"

    with patch("openhands.sdk.llm.llm_registry.RegistryEvent") as mock_registry_event:
        mock_registry_event.return_value = Mock()
        registry.add(mock_llm)

    assert "service1" in registry.list_usage_ids()

    registry.remove("service1")
    assert "service1" not in registry.list_usage_ids()

    # 删除未知 ID 是无操作，而不是错误。
    registry.remove("service1")
    registry.remove("never-registered")


def test_llm_registry_add_method():
    """测试新版本 add() 方法 for LLMRegistry."""
    registry = LLMRegistry()

    # 创建模拟对象 LLM
    mock_llm = Mock(spec=LLM)
    mock_llm.usage_id = "test-service"
    service_id = mock_llm.usage_id

    # 模拟对象RegistryEvent避免LLM属性访问
    with patch("openhands.sdk.llm.llm_registry.RegistryEvent") as mock_registry_event:
        mock_registry_event.return_value = Mock()

        # 测试添加 LLM
        registry.add(mock_llm)

        # 验证 LLM 已添加
        assert service_id in registry.usage_to_llm
        assert registry.usage_to_llm[service_id] is mock_llm

        # 验证 RegistryEvent 被调用
        mock_registry_event.assert_called_once_with(llm=mock_llm)

    # 测试添加相同的 usage_id 会引发 ValueError
    with unittest.TestCase().assertRaises(ValueError) as context:
        registry.add(mock_llm)

    assert "already exists in registry" in str(context.exception)


def test_llm_registry_get_method():
    """测试新版本 get() 方法 for LLMRegistry."""
    registry = LLMRegistry()

    # 创建模拟对象 LLM
    mock_llm = Mock(spec=LLM)
    mock_llm.usage_id = "test-service"
    service_id = mock_llm.usage_id

    # 模拟对象RegistryEvent避免LLM属性访问
    with patch("openhands.sdk.llm.llm_registry.RegistryEvent") as mock_registry_event:
        mock_registry_event.return_value = Mock()

        # 首先添加LLM
        registry.add(mock_llm)

        # 测试获取 LLM
        retrieved_llm = registry.get(service_id)
        assert retrieved_llm is mock_llm

    # 测试获得不存在的服务提升 KeyError
    with unittest.TestCase().assertRaises(KeyError) as context:
        registry.get("non-existent-service")

    assert "not found in registry" in str(context.exception)


def test_llm_registry_add_get_workflow():
    """测试完整的添加/获取工作流程。"""
    registry = LLMRegistry()

    # 创建模拟对象 LLMs
    llm1 = Mock(spec=LLM)
    llm1.usage_id = "service1"
    llm2 = Mock(spec=LLM)
    llm2.usage_id = "service2"

    # 模拟对象RegistryEvent避免LLM属性访问
    with patch("openhands.sdk.llm.llm_registry.RegistryEvent") as mock_registry_event:
        mock_registry_event.return_value = Mock()

        # 添加多个 LLMs
        registry.add(llm1)
        registry.add(llm2)

        # 验证我们可以找回它们
        assert registry.get("service1") is llm1
        assert registry.get("service2") is llm2

        # 验证 list_usage_ids 有效
        usage_ids = registry.list_usage_ids()
        assert "service1" in usage_ids
        assert "service2" in usage_ids
        assert len(usage_ids) == 2

        # 验证 usage_id 设置正确
        assert llm1.usage_id == "service1"
        assert llm2.usage_id == "service2"


def test_llm_registry_ensures_independent_metrics_for_copied_llms():
    """测试注册表确保了 LLMs 通过 model_copy 创建的独立指标。

    这对于创建一个上下文压缩器 LLM 从智能体 LLM 的场景非常重要，每个都应该独立跟踪自
    己的使用情况。 如果没有这个修复，指标将共享给原始和复制的 LLM，导致当
     LLMs 都使用时指标被双计数。

    See: https://github.com/OpenHands/software-agent-sdk/issues/418
    """
    from pydantic import SecretStr

    registry = LLMRegistry()

    # 创作原创LLM
    original = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="original-llm",
    )

    # 复制并更新 usage_id（模拟创建上下文压缩器 LLM）
    # 注意：model_copy()默认对私有属性进行浅拷贝，
    # 因此复制的 LLM 与原始数据共享相同的指标对象
    copied = original.model_copy(update={"usage_id": "copied-llm"})

    # 在注册之前，他们共享相同的指标（这是我们正在修复的错误）
    assert original.metrics is copied.metrics

    # 注册 LLMs - 注册表应该检测并修复共享指标
    registry.add(original)
    registry.add(copied)

    # 注册后，他们应该有不同的指标对象
    assert original.metrics is not copied.metrics
    assert id(original.metrics) != id(copied.metrics)

    # 验证指标是独立的 - 对一个指标的更改不会影响另一个指标
    original.metrics.add_cost(1.0)
    assert original.metrics.accumulated_cost == 1.0
    assert copied.metrics.accumulated_cost == 0.0

    copied.metrics.add_cost(2.0)
    assert original.metrics.accumulated_cost == 1.0
    assert copied.metrics.accumulated_cost == 2.0


def test_llm_registry_ensures_independent_telemetry_for_copied_llms():
    """测试注册表确保了 LLMs 的独立度度量 model_copy。

    遥测对象引用指标对象，因此还必须重新创建它才能使用新的指标实例。
    """
    from pydantic import SecretStr

    registry = LLMRegistry()

    # 创作原创LLM
    original = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="original-llm",
    )

    # 复制并更新 usage_id
    copied = original.model_copy(update={"usage_id": "copied-llm"})

    # 在注册之前，他们共享相同的遥测数据
    assert original.telemetry is copied.telemetry

    # 注册 LLMs
    registry.add(original)
    registry.add(copied)

    # 注册后，他们应该有不同的遥测对象
    assert original.telemetry is not copied.telemetry
    assert id(original.telemetry) != id(copied.telemetry)


def test_llm_registry_does_not_reset_metrics_for_independent_llms():
    """注册表的测试不重置 LLMs 的独立指标。"""
    from pydantic import SecretStr

    registry = LLMRegistry()

    # 创建两个独立的 LLMs（不通过 model_copy）
    llm1 = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="llm1",
    )
    llm2 = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="llm2",
    )

    # 在注册之前向 llm1 的指标添加一些成本
    llm1.metrics.add_cost(5.0)
    original_metrics = llm1.metrics

    # 注册 LLMs
    registry.add(llm1)
    registry.add(llm2)

    # llm1 的指标不应重置（未共享）
    assert llm1.metrics is original_metrics
    assert llm1.metrics.accumulated_cost == 5.0

    # llm2应该有自己独立的指标
    assert llm2.metrics is not llm1.metrics
    assert llm2.metrics.accumulated_cost == 0.0
