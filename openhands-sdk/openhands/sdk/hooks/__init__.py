"""
OpenHands 挂钩系统 - 用于自动化和控制的事件驱动挂钩。

挂钩是事件驱动的脚本，在智能体执行期间在特定生命周期事件处执行，从而实现对智能体行为
的确定性控制。
"""

from openhands.sdk.hooks.config import (
    HOOK_EVENT_FIELDS,
    HookConfig,
    HookDefinition,
    HookMatcher,
    HookType,
)
from openhands.sdk.hooks.conversation_hooks import (
    HookEventProcessor,
    create_hook_callback,
)
from openhands.sdk.hooks.executor import HookExecutor, HookResult
from openhands.sdk.hooks.manager import HookManager
from openhands.sdk.hooks.types import HookDecision, HookEvent, HookEventType


__all__ = [
    "HOOK_EVENT_FIELDS",
    "HookConfig",
    "HookDefinition",
    "HookMatcher",
    "HookType",
    "HookExecutor",
    "HookResult",
    "HookManager",
    "HookEvent",
    "HookEventType",
    "HookDecision",
    "HookEventProcessor",
    "create_hook_callback",
]
