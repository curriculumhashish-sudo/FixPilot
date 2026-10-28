"""钩子配置加载和管理。"""

import json
import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from openhands.sdk.hooks.types import HookEventType
from openhands.sdk.utils.path import get_user_persistence_dir


logger = logging.getLogger(__name__)


def _pascal_to_snake(name: str) -> str:
    """将 PascalCase 转换为 snake_case。"""
    # 在大写字母前插入下划线并将所有内容小写
    result = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return result


# 挂钩事件的有效 snake_case 字段名称。 这是挂钩事件类型的唯一事实来源。
#
HOOK_EVENT_FIELDS: frozenset[str] = frozenset(
    {
        "pre_tool_use",
        "post_tool_use",
        "user_prompt_submit",
        "session_start",
        "session_end",
        "stop",
    }
)


class HookType(StrEnum):
    """可以执行的钩子类型。"""

    COMMAND = "command"  # 通过子进程执行的 Shell 命令
    PROMPT = "prompt"  # 单次完成LLM评价
    AGENT = "agent"  # 具有工具访问权限的基于智能体的评估


class HookDefinition(BaseModel):
    """单个钩子定义。"""

    type: HookType = HookType.COMMAND
    name: str | None = None
    # `command` 保留为非空字符串，始终存在于已序列化输出中，并在JSON 模式（参见__
    # get_pydantic_json_schema__）中报告为必需。 这保留了 ConversationInfo.hook_config
    # 已发布的 REST 响应契约：使其可选/可空将被 oasdiff REST API 检查标记为不兼容变更。
    # 无命令钩子类型（PROMPT/AGENT）只需将其保留为“”。
    #
    command: str = ""
    prompt: str | None = None
    system_prompt: str | None = None
    tools: list[str] = Field(default_factory=list)
    timeout: int = 60
    max_iterations: int = 3
    async_: bool = Field(default=False, alias="async")  # “异步”是保留关键字

    model_config = {
        "populate_by_name": True,  # 输入中允许同时使用“异步”和“async_”
    }

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):  # type: ignore[override]
        # 将 `command` 报告为必需的非默认字符串，以保持已发布的 REST 响应合同与该字段没
        # 有默认值的版本相同。 运行时默认值（“”）仅简化无命令钩子类型的构造； 它永远不会
        # 在响应中以 null 的形式出现。
        #
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        command_schema = json_schema.get("properties", {}).get("command")
        if command_schema is not None:
            command_schema.pop("default", None)
        required = json_schema.setdefault("required", [])
        if "command" not in required:
            required.append("command")
        return json_schema

    @model_validator(mode="after")
    def _validate_type_fields(self) -> "HookDefinition":
        if self.type == HookType.COMMAND and not self.command:
            raise ValueError("'command' is required when type is 'command'")
        if self.type == HookType.PROMPT and not self.prompt:
            raise ValueError("'prompt' is required when type is 'prompt'")
        if self.type == HookType.PROMPT and self.command:
            raise ValueError("'command' must not be set when type is 'prompt'")
        if self.type == HookType.PROMPT and self.async_:
            raise ValueError("'async' is not supported for prompt hooks")
        if self.type == HookType.AGENT and self.command:
            raise ValueError(
                "'command' must not be set when type is 'agent'; "
                "use 'system_prompt' instead"
            )
        if self.type == HookType.AGENT and self.async_:
            raise ValueError("'async' is not supported for agent hooks")
        return self

    @property
    def display_command(self) -> str:
        """该挂钩在日志和事件中使用的人类可读标签。"""
        if self.command:
            return self.command
        prefix = f"{self.type.value}-hook"
        if self.name is not None:
            return f"{prefix}:{self.name}"
        if self.type == HookType.PROMPT and self.prompt:
            return f"{prefix}:{self.prompt[:20]}"
        if self.type == HookType.AGENT and self.system_prompt:
            return f"{prefix}:{self.system_prompt[:20]}"
        return f"{prefix}:{self.type.value}"


class HookMatcher(BaseModel):
    """根据模式将事件与挂钩匹配。

    支持精确匹配、通配符 (*) 和正则表达式（自动检测或 /pattern/).
    """

    matcher: str = "*"
    hooks: list[HookDefinition] = Field(default_factory=list)

    # 指示模式的正则表达式元字符应被视为正则表达式
    _REGEX_METACHARACTERS = set("|.*+?[]()^$\\")

    def matches(self, tool_name: str | None) -> bool:
        """检查此匹配器是否与给定的工具名称匹配。"""
        # 通配符匹配所有内容
        if self.matcher == "*" or self.matcher == "":
            return True

        if tool_name is None:
            return self.matcher in ("*", "")

        # 检查显式正则表达式模式（包含在 /) 中）
        is_regex = (
            self.matcher.startswith("/")
            and self.matcher.endswith("/")
            and len(self.matcher) > 2
        )
        if is_regex:
            pattern = self.matcher[1:-1]
            try:
                return bool(re.fullmatch(pattern, tool_name))
            except re.error:
                return False

        # 自动检测正则表达式：如果匹配器包含元字符，则视为正则表达式
        if any(c in self.matcher for c in self._REGEX_METACHARACTERS):
            try:
                return bool(re.fullmatch(self.matcher, tool_name))
            except re.error:
                # 正则表达式无效，无法完全匹配
                pass

        # 精确匹配
        return self.matcher == tool_name


class HookConfig(BaseModel):
    """所有钩子的配置。

    可以通过从 `.openhands/hooks.json` 加载或直接使用类型化字段实例化来配置挂钩：

        # 使用类型化字段直接实例化（推荐）：
        config = HookConfig(
            pre_tool_use=[
                HookMatcher(
                    matcher="terminal",
                    hooks=[HookDefinition(command="block_dangerous.sh")]
                )
            ]
        )

        # 从 JSON 文件加载：
        config = HookConfig.load(".openhands/hooks.json")
    """

    model_config = {
        "extra": "forbid",
    }

    pre_tool_use: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run before tool execution",
    )
    post_tool_use: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run after tool execution",
    )
    user_prompt_submit: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run when user submits a prompt",
    )
    session_start: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run when a session starts",
    )
    session_end: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run when a session ends",
    )
    stop: list[HookMatcher] = Field(
        default_factory=list,
        description="Hooks that run when the agent attempts to stop",
    )

    def is_empty(self) -> bool:
        """检查此配置是否没有配置钩子。"""
        return not any(
            [
                self.pre_tool_use,
                self.post_tool_use,
                self.user_prompt_submit,
                self.session_start,
                self.session_end,
                self.stop,
            ]
        )

    @model_validator(mode="before")
    @classmethod
    def _normalize_hooks_input(cls, data: Any) -> Any:
        """支持带有 PascalCase 键和“hooks”包装的 JSON 格式。

        我们有意继续支持这些格式，以实现与现有集成的互操作性 (e.g. 克劳德代码插件挂钩
        文件）。
        """
        if not isinstance(data, dict):
            return data

        # 解开旧格式：{"hooks": {"PreToolUse": [...]}}
        if "hooks" in data:
            if len(data) != 1:
                logger.warning(
                    'HookConfig legacy wrapper format should be {"hooks": {...}}. '
                    "Extra top-level keys will be ignored."
                )
            data = data["hooks"]

        # 将 PascalCase 键转换为 snake_case 字段名称
        normalized: dict[str, Any] = {}
        seen_fields: set[str] = set()

        for key, value in data.items():
            snake_key = _pascal_to_snake(key)
            is_pascal_case = snake_key != key

            if is_pascal_case:
                # 验证 PascalCase 键映射到已知字段
                if snake_key not in HOOK_EVENT_FIELDS:
                    valid_types = ", ".join(sorted(HOOK_EVENT_FIELDS))
                    raise ValueError(
                        f"Unknown event type '{key}'. Valid types: {valid_types}"
                    )

            # 检查重复的键（同时提供 PascalCase 和 snake_case）
            if snake_key in seen_fields:
                raise ValueError(
                    f"Duplicate hook event: both '{key}' and its snake_case "
                    f"equivalent '{snake_key}' were provided"
                )
            seen_fields.add(snake_key)
            normalized[snake_key] = value

        # 保留向后兼容性而不弃用任何支持的格式。 传统的“hooks”包装器和 PascalCase 键被接
        # 受以实现互操作性，并且不应发出弃用警告。
        #

        return normalized

    @classmethod
    def load(
        cls, path: str | Path | None = None, working_dir: str | Path | None = None
    ) -> "HookConfig":
        """从路径加载配置，或搜索 openhands/hooks.json 位置。

        Args:
            path: hooks.json 文件的显式路径。 如果提供，working_dir 将被忽略。
            working_dir: openhands/hooks.json. 发现项目的目录
                如果未提供，则回退到 cwd。
        """
        if path is None:
            # 在标准位置搜索 hooks.json
            base_dir = Path(working_dir) if working_dir else Path.cwd()
            search_paths = [
                base_dir / ".openhands" / "hooks.json",
                get_user_persistence_dir() / "hooks.json",
            ]
            for search_path in search_paths:
                if search_path.exists():
                    path = search_path
                    break

        if path is None:
            return cls()

        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = json.load(f)
        # 使用 model_validate 触发 model_validator
        return cls.model_validate(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HookConfig":
        """从字典创建 HookConfig。

        支持带有“hooks”包装器的传统格式和直接格式：
            # 旧格式：
            {"hooks": {"PreToolUse": [...]}}

            # 直接格式：
            {"PreToolUse": [...]}
        """
        return cls.model_validate(data)

    def _get_matchers_for_event(self, event_type: HookEventType) -> list[HookMatcher]:
        """获取事件类型的匹配器。"""
        match event_type:
            case HookEventType.PRE_TOOL_USE:
                return self.pre_tool_use
            case HookEventType.POST_TOOL_USE:
                return self.post_tool_use
            case HookEventType.USER_PROMPT_SUBMIT:
                return self.user_prompt_submit
            case HookEventType.SESSION_START:
                return self.session_start
            case HookEventType.SESSION_END:
                return self.session_end
            case HookEventType.STOP:
                return self.stop
            case _:
                raise RuntimeError(f"Unhandled hook event type: {event_type}")

    def get_hooks_for_event(
        self, event_type: HookEventType, tool_name: str | None = None
    ) -> list[HookDefinition]:
        """获取应该为事件运行的所有挂钩。"""
        matchers = self._get_matchers_for_event(event_type)

        result: list[HookDefinition] = []
        for matcher in matchers:
            if matcher.matches(tool_name):
                result.extend(matcher.hooks)

        return result

    def has_hooks_for_event(self, event_type: HookEventType) -> bool:
        """检查是否有为事件类型配置的任何钩子。"""
        matchers = self._get_matchers_for_event(event_type)
        return len(matchers) > 0

    def save(self, path: str | Path) -> None:
        """使用 snake_case 字段名称将挂钩配置保存到 JSON 文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json", exclude_defaults=True), f, indent=2)

    @classmethod
    def merge(cls, configs: list["HookConfig"]) -> "HookConfig | None":
        """通过连接每个事件类型的处理程序来合并多个挂钩配置。

        每个挂钩配置可能有多种事件类型（pre_tool_use、post_tool_use 等）。 此方法组合
        了每个事件类型的所有配置中的所有匹配器。

        Args:
            configs: 要合并的 HookConfig 个对象的列表。

        Returns:
            所有匹配器连接在一起的合并 HookConfig，如果没有配置或结果为空，则为 None
            。

        Example:
            >>> config1 = HookConfig(pre_tool_use=[HookMatcher(matcher="*")])
            >>> config2 = HookConfig(pre_tool_use=[HookMatcher(matcher="terminal")])
            >>> merged = HookConfig.merge([config1, config2])
            >>> len(merged.pre_tool_use)  # 两者结合使用
            2
        """
        if not configs:
            return None

        merged = cls(
            pre_tool_use=[m for c in configs for m in c.pre_tool_use],
            post_tool_use=[m for c in configs for m in c.post_tool_use],
            user_prompt_submit=[m for c in configs for m in c.user_prompt_submit],
            session_start=[m for c in configs for m in c.session_start],
            session_end=[m for c in configs for m in c.session_end],
            stop=[m for c in configs for m in c.stop],
        )

        # 如果合并的配置为空，则返回 None
        if merged.is_empty():
            return None

        return merged
