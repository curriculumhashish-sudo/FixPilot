"""将注册的：class:`PromptSection` 单位组装到 ``SystemPromptEvent`` 消耗的
``(static, dynamic)`` 对中。

故意不是智能体字段：智能体保留现有的提示词自定义界面； 模块级默认值注册表是覆盖点。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Final

from openhands.sdk.context.prompts.section import (
    CacheTier,
    PromptBlocks,
    PromptContext,
    PromptSection,
)


__all__ = ["PromptRegistry"]

_SECTION_SEPARATOR: Final[str] = "\n\n"


@dataclass(slots=True, eq=False)
class PromptRegistry:
    """提示词个部分的有序集合，按注册顺序组装。"""

    _sections: dict[str, PromptSection] = field(default_factory=dict, init=False)

    def register(self, section: PromptSection) -> None:
        """添加一个新的部分。 引发重复名称（使用：meth:`replace`）。"""
        if section.name in self._sections:
            raise ValueError(
                f"A prompt section named {section.name!r} is already registered; "
                "use replace() to override it."
            )
        self._sections[section.name] = section

    def replace(self, section: PromptSection) -> None:
        """添加 ``section``，或覆盖同名的。"""
        self._sections[section.name] = section

    def build(self, ctx: PromptContext) -> PromptBlocks:
        """渲染受保护的部分，在注册中按 ``cache_tier`` 分组
        订单。 ``static`` 始终是一个字符串； 当为空时，``dynamic`` 为 ``None``。
        """
        buckets: defaultdict[CacheTier, list[str]] = defaultdict(list)
        for section in self._sections.values():
            if not section.guard(ctx):
                continue
            text = section.render(ctx)
            if text is None:
                continue
            text = text.strip()
            if not text:
                continue
            buckets[section.cache_tier].append(text)

        return PromptBlocks(
            static=_SECTION_SEPARATOR.join(buckets[CacheTier.STATIC]),
            dynamic=_SECTION_SEPARATOR.join(buckets[CacheTier.DYNAMIC]) or None,
        )
