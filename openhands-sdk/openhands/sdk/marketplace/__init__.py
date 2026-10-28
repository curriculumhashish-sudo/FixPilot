"""OpenHands SDK 的市场模块。

该模块提供插件和技能市场支持 - 列出可用插件和技能及其元数据和源位置的目录。

市场由 `.plugin/` 中的 `marketplace.json` 文件定义，或
存储库根目录的 `.claude-plugin/` 目录。 它列出了可安装的插件和技能，以及描述、版本和
作者等元数据。

示例marketplace.json：
```json
{
    "name": "company-tools",
    "owner": {"name": "DevTools Team"},
    "plugins": [
        {"name": "formatter", "source": "./plugins/formatter"}
    ],
    "skills": [
        {"name": "github", "source": "./skills/github"}
    ]
}
```
"""

from importlib import import_module
from typing import Any

from openhands.sdk.marketplace.registration import (
    MarketplaceRegistration as MarketplaceRegistration,
)


_TYPE_EXPORTS = {
    "MARKETPLACE_MANIFEST_DIRS",
    "MARKETPLACE_MANIFEST_FILE",
    "Marketplace",
    "MarketplaceEntry",
    "MarketplaceMetadata",
    "MarketplaceOwner",
    "MarketplacePluginEntry",
    "MarketplacePluginSource",
}
_REGISTRY_EXPORTS = {
    "AmbiguousPluginError",
    "FetchedMarketplace",
    "MarketplaceNotFoundError",
    "MarketplaceRegistry",
    "PluginNotFoundError",
    "PluginResolutionError",
}


__all__ = sorted(_TYPE_EXPORTS | _REGISTRY_EXPORTS | {"MarketplaceRegistration"})


def __getattr__(name: str) -> Any:
    if name in _TYPE_EXPORTS:
        return getattr(import_module("openhands.sdk.marketplace.types"), name)
    if name in _REGISTRY_EXPORTS:
        return getattr(import_module("openhands.sdk.marketplace.registry"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
