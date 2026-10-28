"""填充 ``ToolShieldLLMSecurityAnalyzer.safety_experiences`` 的助手。

这些助手与 ``toolshield`` PyPI 包集成（通过安装
``[toolshield]`` 可选额外）。 它们公开了四种使用模式：

1. :func:`safety_experiences_for_mcp_config` -- **推荐用于SDK
   agents**: 从智能体自己的工具表面导出
   ``AgentBase.mcp_config`` 加上其显式工具列表（无网络探测； 适用于 stdio 服务器和内
   置工具，例如
   ``FileEditorTool``).
2. :func:`default_safety_experiences` -- 我们默认提供带有终端+文件系统体验的种子。
3. :func:`load_safety_experiences` -- 加载工具体验的明确列表。
4. :func:`auto_detect_safety_experiences` -- 探测活动 MCP 服务器的本地主机，加载实际
运行的工具的体验。 为开发人员在手头没
有 ``mcp_config`` 的情况下进行探索性设置提供便利； 更喜欢服务器或智能体进程中的：func
:
`safety_experiences_for_mcp_config`。

所有四个都返回一个渲染字符串，准备插入
``ToolShieldLLMSecurityAnalyzer(safety_experiences=...)``. 想要注入自己手工编写的体验
的用户可以跳过这些助手并直接
传递任意字符串。

Example:
    >>> from openhands.sdk.security import ToolShieldLLMSecurityAnalyzer
    >>> from openhands.sdk.security.toolshield_helpers import (
    ...     default_safety_experiences,
    ...     auto_detect_safety_experiences,
    ...     safety_experiences_for_mcp_config,
    ... )
    >>>
    >>> # 默认种子
    >>> analyzer = ToolShieldLLMSecurityAnalyzer(
    ...     llm=guardrail_llm,
    ...     safety_experiences=default_safety_experiences(),
    ... )
    >>>
    >>> # 自动检测一切 MCP 服务器本地运行
    >>> analyzer = ToolShieldLLMSecurityAnalyzer(
    ...     llm=guardrail_llm,
    ...     safety_experiences=auto_detect_safety_experiences(),
    ... )
    >>>
    >>> # 或者，SDK 智能体优选：匹配智能体配置的
    >>> # 服务器和显式工具
    >>> analyzer = ToolShieldLLMSecurityAnalyzer(
    ...     llm=guardrail_llm,
    ...     safety_experiences=safety_experiences_for_mcp_config(
    ...         agent.mcp_config,
    ...         tool_names=[t.name for t in agent.tools],
    ...     ),
    ... )
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import re
from collections.abc import Sequence
from typing import Any

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


# 默认情况下播种的工具。 这些是我们捆绑的经验，涵盖了链接问题中评估的工具表面。
#
DEFAULT_TOOL_NAMES: list[str] = ["terminal-mcp", "filesystem-mcp"]


# 自动检测的默认端口范围。 匹配 toolshield 的 ``mcp_scan`` 默认值，它探测 localhost:8000
# -10000 是否有任何说话 MCP。 缩小此范围以便在已知部署中进行更快的扫描。
#
DEFAULT_SCAN_PORT_RANGE: tuple[int, int] = (8000, 10000)


# 没有要探测的端口的工具（终端是本地执行程序）。 我们无条件地将它们包含在自动检测结果中
# 。
#
ALWAYS_ACTIVE_TOOLS: list[str] = ["terminal-mcp"]


def _require_toolshield():
    """导入 toolshield 包或提出有用的 ImportError。"""
    try:
        import toolshield  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "toolshield is not installed. Install via "
            "`pip install openhands-sdk[toolshield]` to use these helpers, "
            "or pass a custom string to "
            "ToolShieldLLMSecurityAnalyzer(safety_experiences=...)."
        ) from e
    return toolshield


def load_safety_experiences(
    tool_names: list[str],
    model: str = "claude-sonnet-4.5",
) -> str:
    """加载经验以获取明确的工具名称列表。

    Args:
        tool_names: 工具体验标识符 (e.g. ``"terminal-mcp"``).
            必须与给定 ``model`` 子目录的 ``toolshield`` 包中捆绑的文件匹配。 这些被
            ``toolshield``用作文件名词干——仅
            传递可信的、经过验证的值（此模块中的配置/扫描助手在调用之前进行验证）。
        model: 设置使用哪个预先生成的经验。 默认为
            ``"claude-sonnet-4.5"``.

    Returns:
        为 ``safety_experiences=`` 准备的渲染字符串。
    """
    ts = _require_toolshield()
    experiences = ts.load_experiences(tool_names, model=model)
    return experiences.format_for_prompt()


def default_safety_experiences(model: str = "claude-sonnet-4.5") -> str:
    """默认种子：终端+文件系统体验。

    这是涵盖链接问题中评估的工具表面的起点。 具有不同工具表面的调用者应该使用
    :func:`load_safety_experiences` 或：func:`auto_detect_safety_experiences`
    相反。
    """
    return load_safety_experiences(DEFAULT_TOOL_NAMES, model=model)


# 体验名称由 toolshield 的加载程序用作文件名词干，因此仅接受保守的 slugs。 其他任何内容
# （路径分隔符、点、unicode 技巧）都会被丢弃而不是转发。
#
_EXPERIENCE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


# 已注册的 SDK 工具名称，其功能表面与捆绑的体验集匹配。 内置工具不会出现在
# ``mcp_config`` 中，因此如果没有此映射，智能体就会使用 e.g。 文件编辑器（并且没有文件系
# 统 MCP 服务器）不会从配置派生路径中获得任何文件系统体验。
#
# ``ToolDefinition.__init_subclass__`` 通过对类名进行蛇形命名并删除 ``_tool`` 后缀来派生
# 注册名称 (``FileEditorTool`` -> ``"file_editor"``)； ``Tool.name`` /
# ``agent.tools[*].name`` 带有那些 snake_case 名称。 CamelCase
# class names are accepted as aliases for hand-authored configs.
SDK_TOOL_EXPERIENCE_MAP: dict[str, str] = {
    "file_editor": "filesystem-mcp",
    "planning_file_editor": "filesystem-mcp",
    "terminal": "terminal-mcp",
    "browser_tool_set": "playwright-mcp",
    # CamelCase 类名别名。
    "FileEditorTool": "filesystem-mcp",
    "PlanningFileEditorTool": "filesystem-mcp",
    "TerminalTool": "terminal-mcp",
    "BrowserToolSet": "playwright-mcp",
}


def _experience_name_from_server_name(server_name: str) -> str:
    """从 MCP 服务器派生捆绑体验文件名
    自我报告``serverInfo.name``。

    镜像约定 ``toolshield`` 的 ``auto_discover`` 使用：
    ``tool_name = server["name"].lower(); exp_file = f"{tool_name}-mcp.json"``. E.g.
    服
    务器名称 ``"filesystem"`` -> 经验 ``"filesystem-mcp"``。 如果服务器名称已以
    ``-mcp`` 结尾，则按原样使用。
    """
    slug = server_name.lower().strip().replace(" ", "-").replace("_", "-")
    if slug.endswith("-mcp") or slug.endswith("mcp"):
        return slug if slug.endswith("-mcp") else slug[:-3] + "-mcp"
    return f"{slug}-mcp"


def mcp_tools_from_config(
    mcp_config: dict[str, Any],
    tool_names: Sequence[str] = (),
) -> list[str]:
    """从智能体的 ``mcp_config`` 和工具派生体验名称。

    这是首选的 SDK 集成路径：[the] 智能体已经声明了 MCP 表面 ``AgentBase.mcp_config``
     (
    ``{"mcpServers": {name: spec, ...}}``因此，我们可以直接将配置的服务器名称映射到体
    验名称，而无需进行网络探测，也不依赖于分析器构
    建时服务器是否可用，而且它适用于没有本地主机端口的stdio服务器。

    ``mcp_config`` 单独不描述了内置SDK 工具：使用``FileEditorTool`` 的智能体触及文件
    系统，而没有配置任何文件系统MCP 服务器。
    通过 ``tool_names`` (e.g.) 传递智能体的显式工具表面。
    ``[t.name for t in agent.tools]``) 涵盖那些； 名称
    通过映射
    :data:`SDK_TOOL_EXPERIENCE_MAP` 和未知名称将被忽略。

    无条件包含：data:`ALWAYS_ACTIVE_TOOLS`（终端）中的工具，因为无论 MCP 配置如何，智
    能体都会获得本地执行。

    Args:
        mcp_config: 智能体的MCP配置字典，同理
            形状为``AgentBase.mcp_config``。
        tool_names: 从智能体的显式注册 SDK 工具名称
            工具列表（``Tool.name`` 值）。 可选。

    Returns:
        经验标识符 (e.g. ``"terminal-mcp"``,
        ``"filesystem-mcp"``). 首先出现的是始终处于活动状态的工具。 不需要 toolshield
         导入——这是纯粹的名称映射。
    """
    names = list(ALWAYS_ACTIVE_TOOLS)
    servers = (mcp_config or {}).get("mcpServers", {}) or {}
    for server_name in servers:
        exp_name = _experience_name_from_server_name(str(server_name))
        if not _EXPERIENCE_NAME_RE.fullmatch(exp_name):
            logger.debug(f"Ignoring MCP server with unusable name: {server_name!r}")
            continue
        if exp_name not in names:
            names.append(exp_name)
    for tool_name in tool_names:
        exp_name = SDK_TOOL_EXPERIENCE_MAP.get(tool_name)
        if exp_name is None:
            logger.debug(f"No experience mapping for SDK tool {tool_name!r}")
            continue
        if exp_name not in names:
            names.append(exp_name)
    return names


def safety_experiences_for_mcp_config(
    mcp_config: dict[str, Any],
    model: str = "claude-sonnet-4.5",
    tool_names: Sequence[str] = (),
) -> str:
    """加载与智能体配置的 MCP 服务器/工具匹配的体验。

    为 SDK 智能体播种：class:`ToolShieldLLMSecurityAnalyzer` 的推荐方法：从智能体自己
    的工具表面派生出工具表面
    ``mcp_config``，``tool_names``，以及其显式内置工具，而不是扫描本地主机（func:
    `auto_detect_safety_experiences`仍可用作开发便利工具，用于探索性设置）。

    其派生体验名称没有 ``model`` 的捆绑文件的已配置服务器将被跳过并显示一条日志行。

    Example:
        >>> analyzer = ToolShieldLLMSecurityAnalyzer(
        ...     llm=guardrail_llm,
        ...     safety_experiences=safety_experiences_for_mcp_config(
        ...         agent.mcp_config,
        ...         tool_names=[t.name for t in agent.tools],
        ...     ),
        ... )

    Args:
        mcp_config: 智能体的MCP配置字典，同理
            形状为``AgentBase.mcp_config``。
        model: 经验集子目录。 默认为
            ``"claude-sonnet-4.5"``.
        tool_names: 从智能体的显式注册 SDK 工具名称
            工具列表——涵盖了``FileEditorTool``等从未出现在``mcp_config``中的内置工具
            。 参见
            ：数据：`SDK_TOOL_EXPERIENCE_MAP`。

    Returns:
        为 ``safety_experiences=`` 准备的渲染字符串。 如果没有配置的服务器或工具具有
        捆绑的体验文件，则为空字符串。
    """
    ts = _require_toolshield()
    wanted = mcp_tools_from_config(mcp_config, tool_names=tool_names)
    available = set(ts.ExperienceStore.list_bundled(model))
    runnable = [t for t in wanted if t in available]
    missing = [t for t in wanted if t not in available]
    if missing:
        logger.info(
            f"Skipping {len(missing)} configured MCP tool(s) without "
            f"bundled {model!r} experiences"
        )
        logger.debug(f"Tools without bundled experiences: {missing}")
    if not runnable:
        logger.warning(
            "No configured MCP server matches a bundled experience file; "
            "returning empty safety_experiences"
        )
        return ""
    logger.info(
        f"Loading safety experiences for {len(runnable)} configured MCP tool(s)"
    )
    logger.debug(f"Configured MCP tools with experiences: {runnable}")
    return load_safety_experiences(runnable, model=model)


def detect_active_mcp_tools(
    port_range: tuple[int, int] = DEFAULT_SCAN_PORT_RANGE,
    verbose: bool = False,
) -> list[str]:
    """扫描本地主机以查找 MCP 服务器并返回匹配的体验名称。

    使用 ``toolshield.mcp_scan`` 对范围内的每个开放端口执行完整的 MCP JSON-RPC 握手（
    ``initialize`` 超过 SSE）
    。 这是真实的检测：我们了解每个服务器的自我报告名称和版本，而不仅仅是“某些内容在
    端口 9090 上响应”。 需要
    ``toolshield`` 可选额外。

    :data:`ALWAYS_ACTIVE_TOOLS`（终端）中的工具会无条件返回，因为它们是本地执行程序而
    不是网络服务。

    并发使用不安全：捕获扫描仪的输出交换
    ``sys.stdout`` 进程范围内的扫描持续时间，因此该窗口期间的其他线程' 打印也将被捕获
    。 从单线程设置代码调用（或序列化调用）； 推荐的
    :func:`safety_experiences_for_mcp_config` 路径不扫描并且
    没有这样的限制。

    Args:
        port_range: 要扫描的包含 ``(start, end)`` 本地主机端口范围。
            默认匹配 toolshield 的约定 (``8000-10000``)。
        verbose: 在扫描输出中包括每个端口的探测尝试
            在 INFO 级别转发（否则为 DEBUG）。 扫描仪的标准输出始终通过 SDK 记录器捕
            获和路由； 这个助手永远不会写入主机进程的标准输出。

    Returns:
        经验标识符 (e.g. ``"terminal-mcp"``, ``"filesystem-mcp"``) 对应于服务器响应
        MCP 握手的工具。 首先出现
        的是始终处于活动状态的工具。
    """
    _require_toolshield()
    from toolshield.mcp_scan import main as _scan_main  # type: ignore[import-not-found]

    start_port, end_port = port_range
    # ``mcp_scan.main`` 是异步，并且必须通过 ``asyncio.run`` 运行，如果我们已经在事件循
    # 环内，则会引发此错误。 检查正在运行的循环之前创建协程 - 急切创建且从未等待的协程在
    #  GC 时发出 ``RuntimeWarning: coroutine ... was never awaited``（``-W error`` 下的
    # 硬故障）。 异步上下文中的调用者可以将此助手包装在 ``asyncio.to_thread`` 中。
    #
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 无运行循环； 安全地继续
    else:
        logger.warning(
            "MCP scan skipped (called from within a running event loop); "
            "returning always-active tools only"
        )
        return list(ALWAYS_ACTIVE_TOOLS)

    # ``mcp_scan.main`` 无条件地将扫描进度/结果打印到标准输出（toolshield<=0.1.3 无安静
    # 模式）。 库代码不得写入主机进程的标准输出，因此捕获它并通过 SDK 记录器转发。
    # ``redirect_stdout`` 互换
    # ``sys.stdout`` 进程范围内的持续时间； 扫描时间很短，并且该帮助程序是从同步设置代码
    # 中调用的，因此窗口很小。
    #
    scan_stdout = io.StringIO()
    coro = _scan_main(start_port, end_port, verbose=verbose)
    try:
        with contextlib.redirect_stdout(scan_stdout):
            found = asyncio.run(coro)
    except RuntimeError as e:
        # 腰带和大括号：关闭从未等待过的协程，这样无论引发什么，都不会在 GC 上触发
        # RuntimeWarning。
        #
        coro.close()
        logger.warning(f"MCP scan failed ({e}); returning always-active tools only")
        return list(ALWAYS_ACTIVE_TOOLS)
    finally:
        captured = scan_stdout.getvalue().strip()
        if captured:
            log = logger.info if verbose else logger.debug
            log(f"toolshield.mcp_scan output:\n{captured}")

    active = list(ALWAYS_ACTIVE_TOOLS)
    for server in found or []:
        name = server.get("name", "") or ""
        if not name or name == "unknown":
            logger.debug(
                f"MCP server at {server.get('url')} reported no name; skipping"
            )
            continue
        exp_name = _experience_name_from_server_name(name)
        if not _EXPERIENCE_NAME_RE.fullmatch(exp_name):
            # 服务器名称来自此处的网络 - 删除任何不符合安全文件名主干的内容。
            #
            logger.debug(
                f"MCP server at {server.get('url')} reported unusable "
                f"name {name!r}; skipping"
            )
            continue
        if exp_name in active:
            continue
        active.append(exp_name)
        logger.debug(
            f"MCP server {name!r} at {server.get('url')} -> experience {exp_name!r}"
        )
    return active


def auto_detect_safety_experiences(
    port_range: tuple[int, int] = DEFAULT_SCAN_PORT_RANGE,
    verbose: bool = False,
    model: str = "claude-sonnet-4.5",
    fallback_to_default: bool = True,
) -> str:
    """扫描本地主机以查找活动的 MCP 服务器并加载匹配的体验。

    使用 toolshield 的完整 MCP JSON-RPC 握手（通过
    ``toolshield.mcp_scan``）而不是盲目的TCP探测，因此我们只相信服务器*实际上*响应为
    MCP并自我报告名称的工具的经验。

    “检测”需要至少一台*联网*MCP服务器来响应
    -- 无条件包含的始终有效的工具 (e.g. 终端）
    不计为检测信号。 当检测不到网络工具时，会回退到：func:
    `default_safety_experiences` (终端 + 文件系统)，除非
    ``fallback_to_default=False``，在这种情况下返回空字符串，以避免调用者无操作路径悄
    悄要求 ``toolshield`` 安装。

    检测到其派生体验名称 (e.g. 服务器
    ``"filesystem"`` -> ``"filesystem-mcp"``) 没有捆绑文件
    ``model`` 被日志行跳过。 运营商可以将自己的 JSON 添加到
    ``toolshield/experiences/<model>/`` 下以扩大覆盖范围。

    Args:
        port_range: 包含 ``(start, end)`` 本地主机端口范围。
            默认 ``(8000, 10000)`` 与 toolshield 的扫描仪匹配。
        verbose: 记录每个端口的探测尝试。
        model: 经验集子目录。 默认为
            ``"claude-sonnet-4.5"``.
        fallback_to_default: 如果没有检测到 MCP 个服务器，则返回
            默认种子（终端+文件系统）而不是空。

    Returns:
        为 ``safety_experiences=`` 准备的渲染字符串。
    """
    try:
        active = detect_active_mcp_tools(port_range=port_range, verbose=verbose)
    except ImportError:
        if not fallback_to_default:
            # 遵守记录的无操作合同：如果没有安装 toolshield，
            # ``fallback_to_default=False`` 会降级为裸露的约束检查（空体验）而不是提升。
            #
            logger.warning(
                "toolshield is not installed and fallback_to_default=False; "
                "returning empty safety_experiences"
            )
            return ""
        # 请求回退方案后，回退方案本身需要 toolshield 来加载默认种子——显示有用的
        # ImportError。
        #
        raise
    networked_detected = [t for t in active if t not in ALWAYS_ACTIVE_TOOLS]

    if networked_detected:
        logger.info(f"Auto-detected {len(active)} active MCP tool(s)")
        logger.debug(f"Auto-detected active MCP tools: {active}")
        # 仅保留具有捆绑体验的工具 ``model``； 记录未命中情况，以便操作员了解覆盖范围差
        # 距。
        #
        from toolshield import (  # type: ignore[import-not-found]
            ExperienceStore,  # 懒惰； _require_toolshield 上面
        )

        available = set(ExperienceStore.list_bundled(model))
        runnable = [t for t in active if t in available]
        missing = [t for t in active if t not in available]
        if missing:
            logger.info(
                f"Skipping {len(missing)} detected tool(s) without "
                f"bundled {model!r} experiences"
            )
            logger.debug(f"Detected tools without bundled experiences: {missing}")
        if runnable:
            return load_safety_experiences(runnable, model=model)

    if fallback_to_default:
        logger.info(
            "No networked MCP tools detected; falling back to default seed "
            f"({DEFAULT_TOOL_NAMES})"
        )
        return default_safety_experiences(model=model)

    logger.warning(
        "No networked MCP tools detected and fallback_to_default=False; "
        "returning empty safety_experiences"
    )
    return ""
