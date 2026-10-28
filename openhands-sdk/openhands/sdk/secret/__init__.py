"""机密用于处理敏感数据的管理模块。

该模块提供了用于管理OpenHands中的机密的类和类型。
"""

from openhands.sdk.secret.secrets import (
    LocalSecretResolver,
    LookupSecret,
    SecretSource,
    SecretValue,
    StaticSecret,
    register_local_secret_resolver,
    unregister_local_secret_resolver,
)


__all__ = [
    "LocalSecretResolver",
    "SecretSource",
    "StaticSecret",
    "LookupSecret",
    "SecretValue",
    "register_local_secret_resolver",
    "unregister_local_secret_resolver",
]
