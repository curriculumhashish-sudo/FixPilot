from abc import ABC, abstractmethod

from pydantic import field_validator

from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.utils.models import DiscriminatedUnionMixin


class ConfirmationPolicyBase(DiscriminatedUnionMixin, ABC):
    @abstractmethod
    def should_confirm(self, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        """确定具有给定风险级别的操作是否需要确认。

        此方法定义了在执行基于其安全风险级别的操作之前是否需要用户确认的核心逻辑。

        Args:
            risk: 待评估操作的安全风险级别。
                 如果未指定，则默认为 SecurityRisk.UNKNOWN。

        Returns:
            True 如果操作在执行前需要用户确认，False 如果操作无需确认即可继续。
        """


class AlwaysConfirm(ConfirmationPolicyBase):
    def should_confirm(
        self,
        risk: SecurityRisk = SecurityRisk.UNKNOWN,  # noqa: ARG002
    ) -> bool:
        return True


class NeverConfirm(ConfirmationPolicyBase):
    def should_confirm(
        self,
        risk: SecurityRisk = SecurityRisk.UNKNOWN,  # noqa: ARG002
    ) -> bool:
        return False


class ConfirmRisky(ConfirmationPolicyBase):
    threshold: SecurityRisk = SecurityRisk.HIGH
    confirm_unknown: bool = True

    @field_validator("threshold")
    def validate_threshold(cls, v: SecurityRisk) -> SecurityRisk:
        if v == SecurityRisk.UNKNOWN:
            raise ValueError("Threshold cannot be UNKNOWN")
        return v

    def should_confirm(self, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        if risk == SecurityRisk.UNKNOWN:
            return self.confirm_unknown

        # 默认情况下，这种比较是自反的，因此如果阈值是 HIGH，我们仍然需要确认 HIGH 风险
        # 操作。 由于阈值保证永远不会是 UNKNOWN（通过验证器），因此我们保证在这里得到一
        # 个布尔值。
        #
        return risk.is_riskier(self.threshold)
