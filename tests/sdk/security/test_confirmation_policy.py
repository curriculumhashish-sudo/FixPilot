"""测试 ConfirmationPolicy 类和序列化。"""

import pytest
from pydantic import BaseModel

from openhands.sdk.security.confirmation_policy import (
    AlwaysConfirm,
    ConfirmationPolicyBase,
    NeverConfirm,
)
from openhands.sdk.security.risk import SecurityRisk


class TestConfirmationPolicyBase:
    """对 ConfirmationPolicy 基类的测试。"""

    def test_cannot_instantiate_base_class(self) -> None:
        """测试基类不能直接实例化。"""
        with pytest.raises(TypeError):
            # 当然 mypy 不希望我们这样做，因此在我们确认运行时行为时忽略类型检查。
            #
            ConfirmationPolicyBase()  # type: ignore

    @pytest.mark.parametrize("cls", list(ConfirmationPolicyBase.__subclasses__()))
    def test_confirmation_policy_container_serialization(
        self, cls: type[ConfirmationPolicyBase]
    ) -> None:
        """测试以 ConfirmationPolicy 个实例作为字段的容器模型可以
        是已序列化。
        """

        class PolicyContainer(BaseModel):
            policy: ConfirmationPolicyBase

        container = PolicyContainer(policy=cls())

        container_dict = container.model_dump_json()
        restored_container = PolicyContainer.model_validate_json(container_dict)

        assert isinstance(restored_container.policy, cls)
        assert container.policy == restored_container.policy


class TestAlwaysConfirm:
    """测试 AlwaysConfirm 策略。"""

    @pytest.mark.parametrize("risk", list(SecurityRisk))
    def test_always_confirm(self, risk: SecurityRisk) -> None:
        """测试策略是否始终得到确认，无论输入如何。"""
        policy = AlwaysConfirm()
        assert policy.should_confirm(risk) is True

    def test_roundtrip_serialization(self) -> None:
        """测试 AlwaysConfirm 是否可以正确为已序列化和已反序列化。"""
        policy = AlwaysConfirm()
        policy_dict = policy.model_dump_json()
        restored_policy = AlwaysConfirm.model_validate_json(policy_dict)

        assert isinstance(restored_policy, AlwaysConfirm)

    def test_polymorphic_serialization(self) -> None:
        """测试多态序列化和反序列化。 这就需要我们
        反序列化使用基类。
        """
        policy: ConfirmationPolicyBase = AlwaysConfirm()
        policy_dict = policy.model_dump_json()
        restored_policy = ConfirmationPolicyBase.model_validate_json(policy_dict)

        assert isinstance(restored_policy, AlwaysConfirm)


class TestNeverConfirm:
    """测试 NeverConfirm 策略。"""

    @pytest.mark.parametrize("risk", list(SecurityRisk))
    def test_never_confirm(self, risk: SecurityRisk) -> None:
        """测试该策略永远不会确认，无论输入如何。"""
        policy = NeverConfirm()
        assert policy.should_confirm(risk) is False

    def test_roundtrip_serialization(self) -> None:
        """测试 NeverConfirm 是否可以正确为已序列化和已反序列化。"""
        policy = NeverConfirm()
        policy_dict = policy.model_dump_json()
        restored_policy = NeverConfirm.model_validate_json(policy_dict)

        assert isinstance(restored_policy, NeverConfirm)

    def test_polymorphic_serialization(self) -> None:
        """测试多态序列化和反序列化。 这就需要我们
        反序列化使用基类。
        """
        policy: ConfirmationPolicyBase = NeverConfirm()
        policy_dict = policy.model_dump_json()
        restored_policy = ConfirmationPolicyBase.model_validate_json(policy_dict)

        assert isinstance(restored_policy, NeverConfirm)
