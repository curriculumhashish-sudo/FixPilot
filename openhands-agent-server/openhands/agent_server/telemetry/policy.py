"""解决*是否*可以传送遥测数据。

这里没有部署“模式”，也没有云的概念。 智能体-服务器解决一件事 - **有效同意** - 并且交
付还需要配置导出器。

同意位于 ``misc_settings.telemetry.consent``。 该容器对智能体-服务器是透明的，而命名
空间是唯一的例外：前端拥有值，智能体-服务器只读取
它，形状在这里被文档而不是推断。

托管部署通过 * * 这些杂乱设置来 ``consent = granted`` ``managed = true``，而不是通过
智能体服务器对其进行特殊处理。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal


__all__ = [
    "CONSENT_ENV",
    "CONSENT_MODE_ENV",
    "DO_NOT_TRACK_ENV",
    "LEGACY_CONSENT_KEY",
    "LEGACY_MISC_NAMESPACE",
    "MISC_CONSENT_KEY",
    "MISC_MANAGED_KEY",
    "MISC_NAMESPACE",
    "ConsentMode",
    "TelemetryConsent",
    "TelemetryDecision",
    "kill_switch_engaged",
    "read_consent",
    "read_legacy_consent",
    "resolve",
]


class TelemetryConsent(StrEnum):
    """用户的记录选择。 ``UNSET``为默认值，不同意。"""

    GRANTED = "granted"
    DENIED = "denied"
    UNSET = "unset"


class ConsentMode(StrEnum):
    """``OH_TELEMETRY_CONSENT`` 如何与已持久化值交互。"""

    SEED = "seed"
    OVERRIDE = "override"


# ：智能体服务器读取的不透明``misc_settings``容器内的命名空间。 由前端拥有，记录在此处。
#
MISC_NAMESPACE: Final[str] = "telemetry"
MISC_CONSENT_KEY: Final[str] = "consent"
MISC_MANAGED_KEY: Final[str] = "managed"

# ：使用命名空间键前的画布。 读作回退方案，这样现有用户就不会：默默地重置为不同意； 从未
# 回信。
#
LEGACY_MISC_NAMESPACE: Final[str] = "app_preferences"
LEGACY_CONSENT_KEY: Final[str] = "user_consents_to_analytics"

DO_NOT_TRACK_ENV: Final[str] = "DO_NOT_TRACK"
CONSENT_ENV: Final[str] = "OH_TELEMETRY_CONSENT"
CONSENT_MODE_ENV: Final[str] = "OH_TELEMETRY_CONSENT_MODE"

_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class TelemetryDecision:
    """已解决的答案，保留了记录的出处和 API。"""

    consent: TelemetryConsent
    enabled: bool
    reason: Literal[
        "kill_switch",
        "env_override",
        "settings",
        "legacy_settings",
        "env_seed",
        "default",
    ]
    managed: bool = False

    @property
    def is_locked(self) -> bool:
        """True 当用户无法更改设置的结果时。"""
        return self.managed or self.reason in ("kill_switch", "env_override")


def kill_switch_engaged(env: Mapping[str, str] | None = None) -> bool:
    """操作员是否通过 ``DO_NOT_TRACK`` 强制关闭遥测。"""
    source = os.environ if env is None else env
    value = source.get(DO_NOT_TRACK_ENV)
    return value is not None and value.strip().lower() in _TRUTHY


def _coerce_consent(value: Any) -> TelemetryConsent | None:
    """接受记录的字符串以及遗留的布尔形状。"""
    if isinstance(value, bool):
        return TelemetryConsent.GRANTED if value else TelemetryConsent.DENIED
    if isinstance(value, str):
        try:
            return TelemetryConsent(value.strip().lower())
        except ValueError:
            return None
    return None


def _namespace(misc_settings: Mapping[str, Any] | None, name: str) -> Mapping[str, Any]:
    if not isinstance(misc_settings, Mapping):
        return {}
    section = misc_settings.get(name)
    return section if isinstance(section, Mapping) else {}


def read_consent(
    misc_settings: Mapping[str, Any] | None,
) -> tuple[TelemetryConsent | None, bool]:
    """读取 ``misc_settings.telemetry`` -> ``(consent, managed)``。

    当命名空间不存在或格式不正确时，返回 ``None``，这样调用者可以 fallback 到旧密钥或
    环境种子，而不是将一个破值视为一个决定。
    """
    section = _namespace(misc_settings, MISC_NAMESPACE)
    consent = _coerce_consent(section.get(MISC_CONSENT_KEY))
    managed = bool(section.get(MISC_MANAGED_KEY) is True)
    return consent, managed


def read_legacy_consent(
    misc_settings: Mapping[str, Any] | None,
) -> TelemetryConsent | None:
    """读取命名空间之前的 Canvas 键。 回退方案仅； 从来没有写过。"""
    section = _namespace(misc_settings, LEGACY_MISC_NAMESPACE)
    return _coerce_consent(section.get(LEGACY_CONSENT_KEY))


def _env_consent(
    env: Mapping[str, str],
) -> tuple[TelemetryConsent | None, ConsentMode]:
    consent = _coerce_consent(env.get(CONSENT_ENV))
    raw_mode = (env.get(CONSENT_MODE_ENV) or "").strip().lower()
    # 默认为 `seed`：操作员默认值不得默默地否决用户已经做出的选择。
    #
    mode = (
        ConsentMode.OVERRIDE if raw_mode == ConsentMode.OVERRIDE else ConsentMode.SEED
    )
    return consent, mode


def resolve(
    misc_settings: Mapping[str, Any] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> TelemetryDecision:
    """解决来自设置和环境的有效同意。

    Precedence: 终止开关，然后是 env *override*，然后是已持久化值，
    然后是旧密钥，然后是 env *seed*，然后是 ``unset``。
    """
    source = os.environ if env is None else env

    if kill_switch_engaged(source):
        return TelemetryDecision(
            consent=TelemetryConsent.DENIED, enabled=False, reason="kill_switch"
        )

    env_value, env_mode = _env_consent(source)
    if env_value is not None and env_mode is ConsentMode.OVERRIDE:
        return TelemetryDecision(
            consent=env_value,
            enabled=env_value is TelemetryConsent.GRANTED,
            reason="env_override",
        )

    settings_value, managed = read_consent(misc_settings)
    if settings_value is not None and settings_value is not TelemetryConsent.UNSET:
        return TelemetryDecision(
            consent=settings_value,
            enabled=settings_value is TelemetryConsent.GRANTED,
            reason="settings",
            managed=managed,
        )

    legacy_value = read_legacy_consent(misc_settings)
    if legacy_value is not None and legacy_value is not TelemetryConsent.UNSET:
        return TelemetryDecision(
            consent=legacy_value,
            enabled=legacy_value is TelemetryConsent.GRANTED,
            reason="legacy_settings",
            managed=managed,
        )

    if env_value is not None:
        return TelemetryDecision(
            consent=env_value,
            enabled=env_value is TelemetryConsent.GRANTED,
            reason="env_seed",
            managed=managed,
        )

    return TelemetryDecision(
        consent=TelemetryConsent.UNSET,
        enabled=False,
        reason="default",
        managed=managed,
    )
