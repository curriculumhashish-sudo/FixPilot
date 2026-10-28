"""为提示词-注册表测试共享 fake :class:`PromptSection`。"""

from dataclasses import dataclass

from openhands.sdk.context.prompts.section import CacheTier, PromptContext


@dataclass
class FakeSection:
    """最小：class:`PromptSection` 双精度，具有可调保护/渲染输出。"""

    name: str
    cache_tier: CacheTier
    text: str | None = None
    enabled: bool = True

    def guard(self, ctx: PromptContext) -> bool:
        return self.enabled

    def render(self, ctx: PromptContext) -> str | None:
        return self.text
