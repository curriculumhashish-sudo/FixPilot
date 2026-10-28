"""ACP npm 安装目录 —— 每个内置提供者已打上标签的 npm 的唯一事实来源 package(s), CLI
 入口还需要任何启动参数来调用它。

故意依赖完全消除（stdlib 仅限，无其他依赖） Pydantic:) 智能体-server Dockerfile的
``acp-providers`` 从裸机生成阶段构
建 ``python:*-bookworm`` 无图 OpenHands 因此，这个文件是安装的包 COPYed 独自进入那个
阶段并由系统执行 ``python3`` 渲染
 [to] ACP  载荷'npm-install/wrapper plan (see :func:```render_docker_install_plan` 和
``acp-providers`` 阶段
``openhands-agent-server/openhands/agent_server/docker/Dockerfile``). 它在导入（或作
为脚本运行）时必须
保持工作状态，除了 ``sys.path`` 上的标准库之外没有任何内容。

``acp_providers.py`` 中的：data:`ACP_PROVIDERS` 构建每个提供者的
``default_command``/``binary_name`` 来自此目录，因此仅需要在此处发生包/版本碰撞。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ACPPackagePin:
    """一个固定的 npm 包（名称 + 确切版本）。"""

    name: str
    version: str

    @property
    def pinned(self) -> str:
        """将 ``name@version`` token 传递给 ``npm``/``npx``."""
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class ACPInstallSpec:
    """通过 npm 安装和启动一个提供商的 ACP CLI 所需的一切。

    支持一个或多个独立固定的包 (e.g. Pi 的 ``pi-acp`` 适配器及其
    ``@earendil-works/pi-coding-agent`` 引擎）。
    """

    key: str
    """提供者密钥，匹配
    ：类：`~openhands.sdk.settings.acp_providers.ACPProviderInfo.key`。"""

    packages: tuple[ACPPackagePin, ...]
    """要固定和安装的一个或多个 npm 软件包。 永远不会空。"""

    binary_name: str
    """CLI 入口：智能体-服务器预安装的 ``PATH`` 包装器名称，
    以及（当：attr:`packages` 有多个条目时）位置命令
    ``npx`` 被告知要运行。"""

    trailing_args: tuple[str, ...] = field(default=())
    """Args 附加在：meth:`npx_command` (e.g.
    CLIgemini的``--acp``, opencode的``acp``。 CLIs中不需要子命令即可进入ACP模式的空值
    。
"""

    min_node_version: str | None = None
    """该提供商套餐中的最高 ``engines.node`` 楼层，当
    超过``>=20``的生态系统基线。

    智能体-服务器镜像将每个选定的提供程序安装在一个节点下，因此 Dockerfile 的 pin 必
    须清除此处的最高层（由
    ``tests/cross/test_agent_server_build_metadata.py``). 的 ``npx``  回退方案运行在
    *host's*
    Node，而不是一个未实现的楼层只以一个隐晦的中握手错误出现在  CLI自己的依赖项——这就
    是这个字段存在的原因。
    """

    def npx_command(self) -> tuple[str, ...]:
        """此提供程序的默认基于 ``npx`` 的启动命令。

        单个包以普通方式调用（``npx <pkg>@<ver>``）； 两个或多个使用
        ``npx --package=<pkg>@<ver> ... <binary_name>``，以便 ``npx`` 知道要运行哪个
        已安装软件包的 bin。
        """
        if len(self.packages) == 1:
            package_tokens: tuple[str, ...] = (self.packages[0].pinned,)
            entry: tuple[str, ...] = ()
        else:
            package_tokens = tuple(f"--package={p.pinned}" for p in self.packages)
            entry = (self.binary_name,)
        return (
            "npx",
            "-y",
            "--prefer-offline",
            *package_tokens,
            *entry,
            *self.trailing_args,
        )


# 内置 ACP 启动器的固定 npm 版本。 这里的凹凸是唯一需要的编辑 - ACP_PROVIDERS、
# Dockerfile 安装阶段和 TypeScript 镜像（通过 check-acp-drift.py --write）都源自下面的
# ACP_INSTALL_CATALOG。
#
CLAUDE_AGENT_ACP_VERSION = "0.63.0"
CODEX_ACP_VERSION = "2.2.2"
GEMINI_CLI_VERSION = "0.46.0"
KIMI_CODE_VERSION = "0.38.0"

# Pi 是唯一一个拥有两个独立引脚的提供商：pi-ACP 仅适应 ACP 并生成一个单独安装的 `pi` 引
# 擎关闭 PATH。
#
PI_ACP_VERSION = "0.0.33"
PI_CODING_AGENT_VERSION = "0.83.0"

OPENCODE_VERSION = "1.18.23"


ACP_INSTALL_CATALOG: Mapping[str, ACPInstallSpec] = {
    "claude-code": ACPInstallSpec(
        key="claude-code",
        packages=(
            ACPPackagePin(
                "@agentclientprotocol/claude-agent-acp", CLAUDE_AGENT_ACP_VERSION
            ),
        ),
        binary_name="claude-agent-acp",
    ),
    "codex": ACPInstallSpec(
        key="codex",
        packages=(ACPPackagePin("@agentclientprotocol/codex-acp", CODEX_ACP_VERSION),),
        binary_name="codex-acp",
    ),
    "gemini-cli": ACPInstallSpec(
        key="gemini-cli",
        packages=(ACPPackagePin("@google/gemini-cli", GEMINI_CLI_VERSION),),
        binary_name="gemini",
        trailing_args=("--acp",),
    ),
    "kimi-code": ACPInstallSpec(
        key="kimi-code",
        # 仅作用域包：未作用域的 npm ``kimi-code`` 是一个不相关的第三方工具，也附带一个
        # ``kimi`` bin。
        #
        packages=(ACPPackagePin("@moonshot-ai/kimi-code", KIMI_CODE_VERSION),),
        binary_name="kimi",
        trailing_args=("acp",),
        # @moonshot-ai/kimi-code declares `node >=22.19.0`.
        min_node_version="22.19.0",
    ),
    "pi": ACPInstallSpec(
        key="pi",
        # 适配器优先：实时一致性探测将 ``packages[0]`` 的版本与服务器报告的
        # ``agentInfo.version`` 版本进行比较，后者是 pi-ACP 的版本，而不是引擎的版本。
        #
        packages=(
            ACPPackagePin("pi-acp", PI_ACP_VERSION),
            ACPPackagePin("@earendil-works/pi-coding-agent", PI_CODING_AGENT_VERSION),
        ),
        binary_name="pi-acp",
        # @earendil-works/pi-coding-agent (and its undici dependency) declare
        # `node >=22.19.0`. 在它下面 pi-ACP 适配器仍然启动，所以  ACP 握手成功，失败仅发
        # 生在 `session/new` 如“Cannot call write after a stream was destroyed” — the
        # engine having already died on
        # `webidl.util.markAsUncloneable is not a function`.
        #
        min_node_version="22.19.0",
    ),
    "opencode": ACPInstallSpec(
        key="opencode",
        # 这是一个7.8KB的 shim，其postinstall会拉取一个匹配的平台特定编译二进制 (~184MB
        # unpacked) 从optionalDependency，因此`--ignore-scripts`留下了一个空壳，会出错。
        #
        packages=(ACPPackagePin("opencode-ai", OPENCODE_VERSION),),
        # shim 的 npm bin 是 ``opencode``，而不是包基本名称。
        binary_name="opencode",
        trailing_args=("acp",),
        # opencode-ai 或其平台包上没有 `engines` 字段：CLI 是编译后的 Bun 二进制文件，仅
        # 其 postinstall 在 Node 上运行。
        #
    ),
}
"""每个 ACP 提供程序都可以通过 npm 安装。 注册表会员资格仅使提供者 * 可选择 * (
``INSTALL_ACP_PROVIDERS``) — 参见
:data:`DEFAULT_PREINSTALLED_ACP_PROVIDERS` 实际运送的内容
默认图像。"""


DEFAULT_PREINSTALLED_ACP_PROVIDERS: tuple[str, ...] = (
    "claude-code",
    "codex",
    "gemini-cli",
)
"""提供商密钥已融入默认的智能体服务器映像（默认为 ``INSTALL_ACP_PROVIDERS``）。 与以
下物品分开存放
:data:`ACP_INSTALL_CATALOG` 所以注册一个新的 npm 提供者不会，
单独增长每个已发布的图像 - 加入此默认值是每个提供商单独的、深思熟虑的决定（请参阅
OpenHands/software-智能体-SDK#4820）。
"""


def render_docker_install_plan(
    keys: Iterable[str],
    catalog: Mapping[str, ACPInstallSpec] = ACP_INSTALL_CATALOG,
) -> tuple[list[str], list[str]]:
    """将提供程序 ``keys`` 解析为（npm 包、包装器 bin 名称）。

    软件包经过重复数据删除（保留首次看到的顺序），因此共享依赖项的两个提供程序仅安装
    一次。 当 ``keys`` 包含 ``catalog`` 中不存在的键时，引发：c
    lass:`ValueError` 列出有效键。
    """
    packages: list[str] = []
    wrapper_bins: list[str] = []
    seen: set[str] = set()
    for key in keys:
        spec = catalog.get(key)
        if spec is None:
            valid = ", ".join(catalog)
            raise ValueError(
                f"Unknown ACP provider {key!r} in INSTALL_ACP_PROVIDERS "
                f"(expected one of: {valid})"
            )
        for pkg in spec.packages:
            if pkg.pinned not in seen:
                seen.add(pkg.pinned)
                packages.append(pkg.pinned)
        wrapper_bins.append(spec.binary_name)
    return packages, wrapper_bins


def _main(argv: list[str] | None = None) -> int:
    """CLI 入口由 Dockerfile 的 ``acp-providers`` 构建阶段使用。

    打印 ``providers`` 中以逗号分隔的提供程序密钥的 shell-``eval``-able 计划 (
    ``PACKAGES="..."`` /
    ``WRAPPER_BINS="..."``)（空字符串安装 None）。 值需要用双引号包裹：如果不使用引号
    ，``eval``，则会将每行按空白字符分割重新分词，
    因此，一个多包的``PACKAGES=a b c``，会被解析为“赋值为 PACKAGES=a，然后运行命令 b
    传入 arg c”，而不是一个空格分隔的赋值。 包
    /bin 名称从不包含 ``"``。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "providers", help="Comma-separated ACP provider keys, or '' for none."
    )
    args = parser.parse_args(argv)
    keys = [k for k in (p.strip() for p in args.providers.split(",")) if k]
    try:
        packages, wrapper_bins = render_docker_install_plan(keys)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'PACKAGES="{" ".join(packages)}"')
    print(f'WRAPPER_BINS="{" ".join(wrapper_bins)}"')
    return 0


if __name__ == "__main__":
    sys.exit(_main())
