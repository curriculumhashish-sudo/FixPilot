# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 规范 OpenHands Agent Server，具有 PEP 420（隐式命名空间）布局。
"""

from pathlib import Path
import os
import site
import sys
from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    collect_data_files,
    copy_metadata,
)

# Windows PE 文件上的 GNU 剥离（尤其是 python3XX.dll）可能会损坏二进制文件并导致
# LoadLibrary 在运行时失败，并显示“对内存位置的访问无效”。
#
IS_WINDOWS = sys.platform == "win32"

# 可选的 Vertex AI 捆绑包。 默认构建保持精简； 当二进制文件应支持 vertex_ai/* 合作伙伴模
# 型时，首先安装 OpenHands-SDK[vertex] 额外部分，或将 ENABLE_VERTEX=1 传递给 Docker 构建
# 。
#
import importlib.util as _vertex_importlib_util

_VERTEX_AVAILABLE = _vertex_importlib_util.find_spec("vertexai") is not None

_vertex_pkgs = (
    "vertexai",
    "google.cloud.aiplatform",
    "google.cloud.aiplatform_v1",
    "google.cloud.aiplatform_v1beta1",
    "google.cloud.bigquery",
    "google.cloud.storage",
    "google.cloud.resourcemanager",
    "google.api_core",
    "google.auth",
    "google.rpc",
    "google.genai",
    "proto",
    "grpc_status",
)
_vertex_datas = []
_vertex_binaries = []
_vertex_hiddenimports = []
if _VERTEX_AVAILABLE:
    for _pkg in _vertex_pkgs:
        _d, _b, _h = collect_all(_pkg)
        _vertex_datas.extend(_d)
        _vertex_binaries.extend(_b)
        _vertex_hiddenimports.extend(_h)
    # google.rpc.status_pb2 是动态导入的 gRPC proto 存根； 仅当 SDK 实际存在时才将其固定
    # 。
    #
    _vertex_hiddenimports.append("google.rpc.status_pb2")
else:
    print(
        "[agent-server.spec] vertexai not installed; "
        "skipping Vertex AI bundle collection. "
        "Install openhands-sdk[vertex] before building to include it."
    )

# 获取项目根目录（运行PyInstaller时当前工作目录）
project_root = Path.cwd()
# 命名空间根路径必须在 pathex 中，PyInstaller 才能找到 'openhands/...'
PATHEX = [
    project_root / "openhands-agent-server",
    project_root / "openhands-sdk",
    project_root / "openhands-tools",
    project_root / "openhands-workspace",
]

# Agent Server 包的入口脚本 (命名空间：openhands/agent_server/__main__.py)
ENTRY = str(project_root / "openhands-agent-server" / "openhands" / "agent_server" / "__main__.py")

# 查找 fakeredis 包位置以获取具有正确路径的 commands.json
def get_fakeredis_data():
    """获取具有正确目录结构的 fakeredis 数据文件。

    fakeredis/model/_command_info.py 使用 Path(__file__).parent.parent / "
    commands.json"
     这意味着访问时预计 commands.json 位于 fakeredis/commands.json
    from fakeredis/model/. We need to ensure the model/ subdirectory exists in the bundle.
    """  # noqa: E501
    import fakeredis
    fakeredis_dir = Path(fakeredis.__file__).parent
    commands_json = fakeredis_dir / "commands.json"
    
    data_files = []
    if commands_json.exists():
        # 将 commands.json 添加到 fakeredis/ 目录
        data_files.append((str(commands_json), "fakeredis"))
    
    # 添加占位符文件以创建模型/子目录结构这确保了 Path(__file__).parent.parent适用于模型
    # /模块
    #
    model_dir = fakeredis_dir / "model"
    if model_dir.exists():
        # 在 model/ 中查找要包含的任何 .py 文件（PyInstaller 需要至少一个文件）
        for py_file in model_dir.glob("*.py"):
            # 我们实际上并不需要 .py 文件（它们已编译），但我们需要 __init__.py 来创建目
            # 录结构
            #
            if py_file.name == "__init__.py":
                data_files.append((str(py_file), "fakeredis/model"))
                break
    
    return data_files

a = Analysis(
    [ENTRY],
    pathex=PATHEX,
    binaries=[
        # Vertex AI SDK 二进制文件（通过上面的 collect_all 收集）
        *_vertex_binaries,
    ],
    datas=[
        # 传送数据的第三方包
        *collect_data_files("tiktoken"),
        *collect_data_files("tiktoken_ext"),
        *collect_data_files("litellm"),
        *collect_data_files("fastmcp"),
        *collect_data_files("mcp"),
        *collect_data_files("fakeredis"),  # fakeredis ACL 使用的 commands.json 是必需的
        *get_fakeredis_data(),  # 确保 fakeredis/model/ 目录结构存在
        # binaryornot >=0.5 通过 importlib.resources 从 binaryornot.data 加载
        # binary_formats.csv / binary_extensions.csv / encodings.csv。 如果没有这些，导
        # 入 openhands.tools.file_editor 会提高
        # ModuleNotFoundError：冻结版本中没有名为“binaryornot.data”的模块。
        *collect_data_files("binaryornot"),

        # OpenHands SDK 提示词模板（针对浅命名空间布局进行调整）
        *collect_data_files("openhands.sdk.context.condenser", includes=["prompts/*.j2"]),
        *collect_data_files("openhands.sdk.context.prompts", includes=["templates/*.j2"]),

        # 插件/MCP格式模式，从模块旁边的磁盘读取
        *collect_data_files("openhands.sdk.plugin.format", includes=["schemas/*.json"]),

        # OpenHands 工具模板
        *collect_data_files("openhands.tools.delegate", includes=["templates/*.j2"]),

        # OpenHands 工具浏览器录制JS文件
        *collect_data_files("openhands.tools.browser_use", includes=["js/*.js"]),

        # register_builtins_agents() 在智能体服务器启动时使用内置子智能体定义。 如果没有
        # 这些，注册表在 PyInstaller 构建中保持为空，并且下游客户端会看到未填充的
        # task_tool_set 描述。
        #
        *collect_data_files("openhands.tools.preset", includes=["subagents/*.md"]),

        # importlib.metadata 的包元数据
        *copy_metadata("openhands-agent-server"),
        *copy_metadata("openhands-sdk"),
        *copy_metadata("openhands-tools"),
        *copy_metadata("openhands-workspace"),
        *copy_metadata("fastmcp"),
        *copy_metadata("litellm"),

        # Vertex AI SDK 数据（通过上述 collect_all 收集）
        *_vertex_datas,
    ],
    hiddenimports=[
        # 从命名空间中拉出所有 OpenHands 模块（一旦 pathex 正确，PEP 420 安全）
        *collect_submodules("openhands.sdk"),
        *collect_submodules("openhands.tools"),
        *collect_submodules("openhands.workspace"),
        *collect_submodules("openhands.agent_server"),

        # 第三方动态导入
        *collect_submodules("tiktoken"),
        *collect_submodules("tiktoken_ext"),
        *collect_submodules("litellm"),
        *collect_submodules("fastmcp"),
        *collect_submodules("fakeredis"),
        *collect_submodules("lupa"),  # fakeredis[lua] Lua 脚本支持所需
        # rich._unicode_data.unicodeX_Y_Z是根据unicodedata.unidata_version动态导入的（
        # e.g. unicode17_0_0 Python 3.13）。
        #
        *collect_submodules("rich"),

        # Vertex AI SDK 隐藏导入（通过上面的 collect_all 收集； 如果 OpenHands-SDK[
        # vertex] 未安装在构建环境中，则为空）。
        #
        *_vertex_hiddenimports,

        # MCP 运行时使用的子包（避免 CLI）
        "mcp.types",
        "mcp.client",
        "mcp.server",
        "mcp.shared",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 修剪尺寸
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        # 排除 MCP CLI 引入打字机/额外部门的部分
        "mcp.cli",
        "mcp.cli.cli",
    ],
    noarchive=False,
    # 重要：不要使用optimize=2 (-OO)； 它删除了解析器所需的文档字符串 (e.g., PLY/bashlex
    # )
    optimize=0,
)

# 删除必须来自运行时映像而不是构建器的系统库。 PyInstaller 二进制文件提取到 /tmp/_MEI*/
# 并在那里设置 LD_LIBRARY_PATH。 子进程 (e.g. tmux) 继承它并选择捆绑的库而不是运行时的系
# 统库，导致版本不匹配：
#  - libgcc_s.so：构建器可能缺少运行时期望的 GCC_14.0 符号
#  - libtinfo/libncurses：构建器的 ncurses 早于运行时的 tmux 预期
_EXCLUDE_LIB_PREFIXES = ('libgcc_s.so', 'libtinfo.so', 'libncurses')
a.binaries = [x for x in a.binaries if not x[0].startswith(_EXCLUDE_LIB_PREFIXES)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="openhands-agent-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=not IS_WINDOWS,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
