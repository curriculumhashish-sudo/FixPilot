"""插件模块的类型定义。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import frontmatter
from pydantic import BaseModel, Field, field_serializer, field_validator

from openhands.sdk.utils.path import to_posix_path
from openhands.sdk.utils.redact import redact_url_credentials


class PluginSource(BaseModel):
    """要加载的插件的规范。

    该模型描述了在哪里可以找到插件，并被 load_plugins() 用于从各种来源获取和加载插件
    。

    Examples:
        >>> # GitHub 仓库
        >>> PluginSource(source="github:owner/repo", ref="v1.0.0")

        >>> # 单体仓库子目录下的插件
        >>> PluginSource(
        ...     source="github:owner/monorepo",
        ...     repo_path="plugins/my-plugin"
        ... )

        >>> # 本地路径
        >>> PluginSource(source="/path/to/plugin")
    """

    source: str = Field(
        description="Plugin source: 'github:owner/repo', any git URL, or local path"
    )
    ref: str | None = Field(
        default=None,
        description="Optional branch, tag, or commit (only for git sources)",
    )
    repo_path: str | None = Field(
        default=None,
        description=(
            "Subdirectory path within the git repository "
            "(e.g., 'plugins/my-plugin' for monorepos). "
            "Only relevant for git sources, not local paths."
        ),
    )

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v: str | None) -> str | None:
        """验证 repo_path 是存储库内的安全相对路径。"""
        if v is None:
            return v
        # 必须是相对路径（无绝对路径）
        if v.startswith("/"):
            raise ValueError("repo_path must be relative, not absolute")
        # 没有父目录遍历
        if ".." in Path(v).parts:
            raise ValueError(
                "repo_path cannot contain '..' (parent directory traversal)"
            )
        return v

    @field_serializer("source", when_used="always")
    def _redact_source(self, source: str) -> str:
        """转储时掩码内联 URL 凭据； ${VAR} 裁判仍然存在（不是机密）。

        原始值保留在获取/克隆的属性上 - 仅已序列化表单（已持久化状态、插件标签、远程
        载荷）被屏蔽。
        """
        return redact_url_credentials(source, preserve_placeholders=True)

    @property
    def source_url(self) -> str | None:
        """将插件源转换为规范 URL。

        将'GitHub方便的前缀，但并非完整的 URL. 对于已经存在的源 URLs返回它们。 本地路
        径返回 None (不兼容)

        Returns:
            URL 字符串，或 None 表示本地路径。

        Examples:
            >>> PluginSource(source="github:owner/repo").source_url
            ' https://github.com/owner/repo'

            >>> PluginSource(source="github:owner/repo", ref="v1.0").source_url
            ' https://github.com/owner/repo/tree/v1.0'

            >>> PluginSource(source="https://github.com/owner/repo").source_url
            ' https://github.com/owner/repo'

            >>> PluginSource(source="/local/path").source_url
            None
        """
        # Handle GitHub：简写 - 我们支持的唯一方便前缀
        if self.source.startswith("github:"):
            repo_part = self.source[7:]  # 删除 'GitHub:' 前缀
            base_url = f"https://github.com/{repo_part}"
            if self.ref or self.repo_path:
                ref = self.ref or "main"
                if self.repo_path:
                    return f"{base_url}/tree/{ref}/{self.repo_path}"
                return f"{base_url}/tree/{ref}"
            return base_url

        # 已经是 URL - 按原样返回
        if self.source.startswith(("https://", "http://", "git@", "git://")):
            return self.source

        # 本地路径 - 不可移植，返回 None
        return None


class ResolvedPluginSource(BaseModel):
    """具有解析引用的插件源（固定到提交 SHA）。

    用于持久化以确保暂停/恢复期间的确定性行为。 当对话恢复时，解析的引用确保我们获得
    与对话开始时使用的插件版本完全相同的插件版本。

    resolved_ref 是获取的实际提交 SHA，即使原始引用是像“main”这样的分支名称。 这可以
    防止在暂停和恢复之间更新分支时发生漂移。

    安全注意事项：
        通过 from_plugin_source() 创建时，源 URL 为已脱敏，以防止凭据在已持久化状态下
        曝光。 将原URL（e.g.、
        https://oauth2:TOKEN@host ）中的任意凭据替换为“****”（e.g.、
        https://****@host ）。 这是安全的，因为
        ：
        1. 插件已获取并缓存之前该对象已创建
        2. resolved_ref（提交SHA）唯一标识确切的版本
        3. 恢复操作可以使用SHA从本地缓存中重新获取
    """

    source: str = Field(
        description=(
            "Plugin source: 'github:owner/repo', any git URL, or local path. "
            "Note: Credentials are redacted for security when persisted."
        )
    )
    resolved_ref: str | None = Field(
        default=None,
        description=(
            "Resolved commit SHA (for git sources). None for local paths. "
            "This is the actual commit that was checked out, even if the "
            "original ref was a branch name."
        ),
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the git repository",
    )
    original_ref: str | None = Field(
        default=None,
        description="Original ref from PluginSource (for debugging/display)",
    )

    @classmethod
    def from_plugin_source(
        cls, plugin_source: PluginSource, resolved_ref: str | None
    ) -> ResolvedPluginSource:
        """从 PluginSource 和已解析的引用创建 ResolvedPluginSource。

        源 URL 自动为已脱敏，以防止已持久化状态下的凭据曝光。 这是安全的，因为在创建
        ResolvedPluginSource 之前应该已经获取并缓存了插件。
        """
        return cls(
            source=redact_url_credentials(plugin_source.source),
            resolved_ref=resolved_ref,
            repo_path=plugin_source.repo_path,
            original_ref=plugin_source.ref,
        )

    def to_plugin_source(self) -> PluginSource:
        """使用已解析的引用转换回 PluginSource。

        从持久化加载时，使用 resolved_ref 确保我们获得与最初获取的版本完全相同的版本
        。

        Note: 源 URL 可能有已脱敏凭据。 这是因为
        该插件应该已经在本地缓存中，并且 resolved_ref（提交 SHA）允许提取而无需重新验
        证。
        """
        return PluginSource(
            source=self.source,
            ref=self.resolved_ref,  # 使用已解决的 SHA，而不是原始参考
            repo_path=self.repo_path,
        )


# 市场插件条目配置的类型别名这些提供了比 dict[str、Any] 更好的文档，同时保持灵活性
#

# ：MCP服务器配置字典。 键是服务器名称，值是服务器配置。 ：每个配置应该有“command”（str
# ）、可选的“args”（list[str]）、“env”。 ：参见
# https://gofastmcp.com/clients/client#configuration-format
#
type McpServersDict = dict[str, dict[str, Any]]

# ：LSP服务器配置字典。 密钥是服务器名称，值是服务器配置。：每个服务器配置都应包含 '
# command'（str）和可选的 'args'（list[str]），：'extensionToLanguage'（映射文件扩展名到
# 语言ID的字典）。：请参阅 https://github.com/OpenHands/software-agent-sdk/issues/1745
# 以了解LSP支持。
#
type LspServersDict = dict[str, dict[str, Any]]

# : 钩子配置字典，匹配 HookConfig.to_dict() 结构。: 应包含 'hooks' 键，键值对为事件类型
# 映射到匹配器列表。: 查看 openhands.sdk.hooks.HookConfig 获取完整结构。
#
type HooksConfigDict = dict[str, Any]


if TYPE_CHECKING:
    from openhands.sdk.skills.skill import Skill


class PluginAuthor(BaseModel):
    """插件的作者信息。"""

    # 可选：智能体插件模式允许没有名称的作者对象，
    # 因此在这里要求它会拒绝一致的清单。
    name: str = Field(default="", description="Author's name")
    email: str | None = Field(default=None, description="Author's email address")
    url: str | None = Field(
        default=None, description="Author's URL (e.g., GitHub profile)"
    )

    @classmethod
    def from_string(cls, author_str: str) -> PluginAuthor:
        """从字符串格式“名称 <email>”解析作者。"""
        if "<" in author_str and ">" in author_str:
            name = author_str.split("<")[0].strip()
            email = author_str.split("<")[1].split(">")[0].strip()
            return cls(name=name, email=email)
        return cls(name=author_str.strip())


class PluginManifest(BaseModel):
    """插件清单来自 plugin.json。"""

    name: str = Field(description="Plugin name")
    version: str = Field(default="1.0.0", description="Plugin version")
    description: str = Field(default="", description="Plugin description")
    author: PluginAuthor | None = Field(default=None, description="Plugin author")
    entry_command: str | None = Field(
        default=None,
        description=(
            "Default command to invoke when launching this plugin. "
            "Should match a command name from the commands/ directory. "
            "Example: 'now' for a command defined in commands/now.md"
        ),
    )

    model_config = {"extra": "allow"}


class CommandDefinition(BaseModel):
    """从 Markdown 文件加载命令定义。

    命令是用户可以直接调用的斜杠命令。 它们定义了智能体要遵循的指令。
    """

    name: str = Field(description="Command name (from filename, e.g., 'review')")
    description: str = Field(default="", description="Command description")
    argument_hint: str | None = Field(
        default=None, description="Hint for command arguments"
    )
    allowed_tools: list[str] = Field(
        default_factory=list, description="List of allowed tools for this command"
    )
    content: str = Field(default="", description="Command instructions/content")
    source: str | None = Field(
        default=None, description="Source file path for this command"
    )
    # Raw 前置元数据用于任何其他字段
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata from frontmatter"
    )

    @classmethod
    def load(cls, command_path: Path) -> CommandDefinition:
        """从 Markdown 文件加载命令定义。

        命令 Markdown 文件有 YAML 前置元数据，其中：
        - description: 命令说明
        - argument-hint：命令参数的提示（字符串或列表）
        - allowed-tools：允许的工具列表

        Markdown的正文是命令指令。

        Args:
            command_path: 命令 Markdown 文件的路径。

        Returns:
            已加载 CommandDefinition 实例。
        """
        with open(command_path, encoding="utf-8") as f:
            post = frontmatter.load(f)

        # 使用正确的类型处理提取前置元数据字段
        fm = post.metadata
        name = command_path.stem  # 来自文件名的命令名称
        description = str(fm.get("description", ""))
        argument_hint_raw = fm.get("argument-hint") or fm.get("argumentHint")
        allowed_tools_raw = fm.get("allowed-tools") or fm.get("allowedTools") or []

        # 将 argument_hint 处理为列表（用空格连接）或字符串
        argument_hint: str | None
        if isinstance(argument_hint_raw, list):
            argument_hint = " ".join(str(h) for h in argument_hint_raw)
        elif argument_hint_raw is not None:
            argument_hint = str(argument_hint_raw)
        else:
            argument_hint = None

        # 确保 allowed_tools 是字符串列表
        allowed_tools: list[str]
        if isinstance(allowed_tools_raw, str):
            allowed_tools = [allowed_tools_raw]
        elif isinstance(allowed_tools_raw, list):
            allowed_tools = [str(t) for t in allowed_tools_raw]
        else:
            allowed_tools = []

        # 从元数据中删除已知字段以获得额外内容
        known_fields = {
            "description",
            "argument-hint",
            "argumentHint",
            "allowed-tools",
            "allowedTools",
        }
        metadata = {k: v for k, v in fm.items() if k not in known_fields}

        return cls(
            name=name,
            description=description,
            argument_hint=argument_hint,
            allowed_tools=allowed_tools,
            content=post.content.strip(),
            source=to_posix_path(command_path),
            metadata=metadata,
        )

    def to_skill(self, plugin_name: str) -> Skill:
        """将此命令转换为关键字触发的技能。

        使用 Claude Code 命名空间创建带有 KeywordTrigger 的技能
        format: /<plugin-name>:<command-name>

        Args:
            plugin_name: 该命令所属插件的名称。

        Returns:
            具有命令内容和 KeywordTrigger 的技能对象。

        Example:
            对于带有命令“now”的插件“city-weather”：
            - 触发关键字：“/city-weather:now"
            - 当用户输入“/city-weather:now东京”时，技能激活
        """
        from openhands.sdk.skills.skill import Skill
        from openhands.sdk.skills.trigger import KeywordTrigger

        # 以 Claude Code 命名空间格式构建触发关键字
        trigger_keyword = f"/{plugin_name}:{self.name}"

        # 使用 $ARGUMENTS 占位符上下文构建技能内容
        content_parts = []
        if self.description:
            content_parts.append(f"## {self.name}\n\n{self.description}\n")

        if self.argument_hint:
            content_parts.append(
                f"**Arguments**: `$ARGUMENTS` - {self.argument_hint}\n"
            )

        if self.content:
            content_parts.append(f"\n{self.content}")

        skill_content = "\n".join(content_parts).strip()

        return Skill(
            name=f"{plugin_name}:{self.name}",
            content=skill_content,
            description=self.description or f"Command {self.name} from {plugin_name}",
            trigger=KeywordTrigger(keywords=[trigger_keyword]),
            source=self.source,
            allowed_tools=self.allowed_tools if self.allowed_tools else None,
        )
