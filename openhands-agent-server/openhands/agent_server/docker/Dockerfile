# syntax=docker/dockerfile:1.7

# 注意：LC_ALL/LANG 必须设置为 C.UTF-8，libtmux 才能正常工作
# PyInstaller 构建。 如果没有正确的区域设置，tmux 会转换 UTF-8 分隔符
# 字符转换为下划线，破坏了 libtmux 的格式解析。
ARG BASE_IMAGE=python-node-runtime
ARG USERNAME=openhands
ARG UID=10001
ARG GID=10001
ARG PORT=8000
ARG NPM_VERSION=11.21.0
# 选择 Vertex AI extra 的构建标志 (`openhands-sdk[vertex]`)。 出发时间：
# 默认保持发布的图像精简。 通过 `--build-arg ENABLE_VERTEX=1`
# 捆绑 google-cloud-aiplatform 以便生成的二进制文件支持
# `vertex_ai/*` 合作伙伴模型（MiniMax、Qwen、Kimi MaaS 端点）。
ARG ENABLE_VERTEX=0
# 以逗号分隔的 ACP 提供程序密钥（请参阅中的 ACP_INSTALL_CATALOG
# openhands-sdk/openhands/sdk/settings/acp_install_catalog.py)，固化到
# ACP-提供者阶段如下。 默认情况下会重现完整的提供程序集
# 今天发货 (DEFAULT_PREINSTALLED_ACP_PROVIDERS)； 未知密钥失败
# 构建而不是默默地安装任何东西。
ARG INSTALL_ACP_PROVIDERS=claude-code,codex,gemini-cli
# 以逗号分隔的功能键包含在下面的 `base-image` 阶段中
# （`base-image-minimal` 不受影响）。 默认转载今天的完整内容
# 内容； 未知密钥使构建失败。 GitHub CLI 预计
# 稍后加入此列表（参见 OpenHands/software-智能体-SDK#4645）——解析
# 下面的内容是单例添加，而不是签名更改。
ARG INSTALL_CAPABILITIES=vscode,browser,docker
ARG ENABLE_VSCODE=true

####################################################################################
# 规范 Python + 节点运行时
#
# 从 Debian 本身开始，仅复制官方的语言运行时
# 图像。 最后阶段仅安装 Python 所需的共享库
# 和节点； 开发人员和包管理器工具由智能体-服务器添加
# 需要时按以下步骤进行。 软件包升级会针对过时的快照进行解析，因此
# 新发布的 Debian 软件包有三天的观测结果期限。
####################################################################################
FROM python:3.13.15-slim-trixie AS python-runtime
FROM node:24.22.1-trixie-slim AS node-runtime

# pip 26.2.2 vendors urllib3 2.7.0 (CVE-2026-97689) and msgpack 1.1.2
# (GHSA-6v7p-g79w-8964)，并且还没有 pip 发布供应商修复版本。
# 它的pkg_resources（setuptools 70.3.0：CVE-2025-47273，CVE-2026-59890）是
# 已删除，因为 setuptools 在 82.0.0 中删除了它，但在 83.0.0 中修复了 CVE-2026-59890。
# pip imports it only for _PIP_USE_IMPORTLIB_METADATA=0, which raises ImportError.
# 使用 pip 自己的工具重新供应，以便其导入重写、修补和
# bom.cdx.json 保持一致； 使用源存档是因为 sdist
# 省略工具/供应商/补丁。 一旦 pip 发布修复程序，请放弃此阶段；
# tests/agent_server/docker_runtime/test_pip_revendoring_retirement.py 标记它。
# 3.13.17 捆绑 pip 26.2.2，其供应商证书已经不信任
# 受损的 eMudhra 根源。 3.13.15 捆绑 pip 26.2.1，仍然信任
# emSign ECC 根CA - G3，以及这个阶段的`venv` + `pip install vendoring`
# 在重新销售的轮子存在之前从 PyPI 获取 (GHSA-6q48-6c7w-9gw2)。
FROM python:3.13.17-trixie AS pip-revendored
ADD --checksum=sha256:b505949bb27827b32f54c9f1f5ca660a6fae3fde61cbe0a971975a3ed34a7ee1 \
    https://github.com/pypa/pip/archive/refs/tags/26.2.2.tar.gz /tmp/pip.tar.gz
RUN set -eux; \
    mkdir /tmp/pip; \
    tar -xzf /tmp/pip.tar.gz -C /tmp/pip --strip-components=1; \
    cd /tmp/pip; \
    sed -i -E \
        -e 's/^( +)urllib3==2\.7\.0$/\1urllib3==2.8.0/' \
        -e 's/^msgpack==1\.1\.2$/msgpack==1.2.1/' \
        -e '/^setuptools==70\.3\.0$/d' \
        src/pip/_vendor/vendor.txt; \
    grep -qx '    urllib3==2.8.0' src/pip/_vendor/vendor.txt; \
    grep -qx 'msgpack==1.2.1' src/pip/_vendor/vendor.txt; \
    if grep -q '^setuptools==' src/pip/_vendor/vendor.txt; then exit 1; fi; \
    rm tools/vendoring/patches/pkg_resources.patch; \
    python -m venv /tmp/vendoring; \
    /tmp/vendoring/bin/pip install --no-cache-dir vendoring==1.4.0; \
    /tmp/vendoring/bin/vendoring sync; \
    python -m pip wheel --no-deps --no-cache-dir --wheel-dir /dist .

FROM debian:trixie-slim AS python-node-runtime
ARG NPM_VERSION
# 20261021 是其 ca 证书的最旧快照（20250419+deb13u1，
# trixie-security) 删除 emSign ECC 根 CA - G3； 20261019 仍在发货
# 20250419，它信任受感染的根（GHSA-6q48-6c7w-9gw2）。
ARG DEBIAN_SNAPSHOT=20261021T000000Z

COPY --from=python-runtime /usr/local /usr/local
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN node /usr/local/lib/node_modules/npm/bin/npm-cli.js install --global "npm@${NPM_VERSION}"

RUN set -eux; \
    ln -sfn ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sfn ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    ln -sfn ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack; \
    printf '%s\n' \
        'Types: deb' \
        "URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/" \
        'Suites: trixie' \
        'Components: main' \
        'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
        'Check-Valid-Until: no' \
        '' \
        'Types: deb' \
        "URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/" \
        'Suites: trixie-security' \
        'Components: main' \
        'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
        'Check-Valid-Until: no' \
        > /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get upgrade -y; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libbz2-1.0 \
        libdb5.3t64 \
        libffi8 \
        libgcc-s1 \
        libgdbm6t64 \
        liblzma5 \
        libncursesw6 \
        libreadline8t64 \
        libsqlite3-0 \
        libssl3t64 \
        libstdc++6 \
        libtinfo6 \
        libuuid1 \
        libzstd1 \
        netbase \
        tzdata \
        zlib1g; \
    rm -rf /var/lib/apt/lists/*; \
    python3 --version; \
    node --version; \
    npm --version

RUN --mount=type=bind,from=pip-revendored,source=/dist,target=/tmp/pip-dist \
    set -eux; \
    # 安装单个重新销售的轮子，无论其版本如何：它会取代
    # 与基础镜像捆绑的pip，其版本不需要匹配。
    python3 -m pip install --no-deps --no-index --no-cache-dir --force-reinstall \
        --disable-pip-version-check --root-user-action=ignore \
        /tmp/pip-dist/pip-*-py3-none-any.whl

####################################################################################
# 生成器（源模式）
# 我们在这里复制源代码+构建一个 venv 用于本地开发和调试。
#
# SELF-CONTAINED /agent-server CONTRACT:
# uv installs python-build-standalone into /agent-server/uv-managed-python and
# 针对它创建 .venv。 两者都位于 /agent-server 下，所以位于下游
# 消费者可以 COPY /agent-server 到任何基础镜像上，并且 venv 可以工作。
#
# uv >= 0.11.5 pulls python-build-standalone >= 20260408, which ships
# libpython 不带 PT_GNU_STACK PF_X（可执行堆栈）。 早期版本
# 由于 LLVM/BOLT 错误而设置了此标志，导致 glibc >= 2.41 且
# DinD/sysbox/seccomp 以“无法启用可执行文件”来拒绝 dlopen()
# 堆栈”。 固定版本不需要消毒剂或解决方法。
# 请参阅OpenHands/软件-智能体-SDK#2761。
####################################################################################
FROM python:3.13-bookworm AS builder
ARG USERNAME UID GID ENABLE_VERTEX
ENV UV_PROJECT_ENVIRONMENT=/agent-server/.venv
ENV UV_PYTHON_INSTALL_DIR=/agent-server/uv-managed-python

# uv 0.11.5+ embeds python-build-standalone 20260408 metadata, which is the
# 修复了 PT_GNU_STACK 的第一个版本。 固定到 0.13.5（最新符合条件的时间
# write) 而不是：latest 所以构建是可重现的。
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

RUN groupadd -g ${GID} ${USERNAME} \
 && useradd -m -u ${UID} -g ${GID} -s /usr/sbin/nologin ${USERNAME} \
 && mkdir -p /agent-server/uv-managed-python \
 && chown -R ${USERNAME}:${USERNAME} /agent-server
USER ${USERNAME}
WORKDIR /agent-server
# 缓存友好：锁定文件优先
COPY --chown=${USERNAME}:${USERNAME} pyproject.toml uv.lock README.md LICENSE ./
COPY --chown=${USERNAME}:${USERNAME} openhands-sdk ./openhands-sdk
COPY --chown=${USERNAME}:${USERNAME} openhands-tools ./openhands-tools
COPY --chown=${USERNAME}:${USERNAME} openhands-workspace ./openhands-workspace
COPY --chown=${USERNAME}:${USERNAME} openhands-agent-server ./openhands-agent-server
RUN --mount=type=cache,target=/home/${USERNAME}/.cache,uid=${UID},gid=${GID} \
    EXTRA_FLAGS=""; \
    if [ "$ENABLE_VERTEX" = "1" ]; then EXTRA_FLAGS="--extra vertex"; fi; \
    uv python install 3.13 && \
    uv venv --python-preference only-managed --python 3.13 .venv && \
    uv sync --frozen --no-editable --managed-python --extra boto3 $EXTRA_FLAGS && \
    readlink -f .venv/bin/python | grep -q '^/agent-server/uv-managed-python/'

####################################################################################
# 二进制生成器（二进制模式）
# 我们在这里运行 PyInstaller 来生成 OpenHands-智能体-server
####################################################################################
FROM builder AS binary-builder
ARG USERNAME UID GID ENABLE_VERTEX

# We need --dev for pyinstaller
RUN --mount=type=cache,target=/home/${USERNAME}/.cache,uid=${UID},gid=${GID} \
    EXTRA_FLAGS=""; \
    if [ "$ENABLE_VERTEX" = "1" ]; then EXTRA_FLAGS="--extra vertex"; fi; \
    uv sync --frozen --dev --no-editable --extra boto3 $EXTRA_FLAGS

RUN --mount=type=cache,target=/home/${USERNAME}/.cache,uid=${UID},gid=${GID} \
    uv run pyinstaller openhands-agent-server/openhands/agent_server/agent-server.spec
# Fail fast if the expected binary is missing
RUN test -x /agent-server/dist/openhands-agent-server

####################################################################################
# ACP providers (parent-independent)
#
# Built from a fixed base rather than ${BASE_IMAGE} so that COPY --from=acp-providers
# 下面为每个基本图像最小构建生成完全相同的压缩层，
# 无论它落在哪个 BASE_IMAGE 上。 这就是让 ~600MB 提供商
# 载荷在每个实例评估映像构建之间共享，而不是
# 每个实例重新安装（并重新上传）一次。
#
# 这里的失败是致命的：对于损坏的构建，没有 per-BASE_IMAGE 回退方案
# 共享载荷本身（请参阅 base-image-minimal 中的兼容性探测
# 每个目标图像回退方案）。
#
# 下面的节点引脚是地板，而不是首选项：此阶段安装每个
# 在一个运行时下选择的提供程序，因此它必须清除最高的
# ACP_INSTALL_CATALOG 中的 `min_node_version`（由
# tests/cross/test_agent_server_build_metadata.py).
####################################################################################
FROM python:3.13-bookworm AS acp-providers
ARG INSTALL_ACP_PROVIDERS
ARG NPM_VERSION
# 一个新的顶级路径，不嵌套在目录下（e.g. /opt) 那个基地
# 图像通常已经填充（SWE-工作台图像船/opt/miniconda3):
# COPY --from=<stage> 只产生跨不同字节的相同层
# BASE_IMAGE 父母，当目的地本身不存在于
# 父级，镜像 /agent-server's 构建器中自己的顶级放置
# 上面的阶段。
ENV ACP_NODE_DIR=/acp-node
# 该目录模块依赖于stdlib，因此它可以 COPYed
# 进入这个裸 `python` 图像并按原样运行 - 无需 pip 安装，也不需要
# 拉入 SDK 源的 REST（这会破坏零上下文
# 快速路径 `build.py` 用于 `base-image-minimal` 目标）。 添加一个
# npm provider is a catalog edit only; this stage never needs to change.
COPY openhands-sdk/openhands/sdk/settings/acp_install_catalog.py /tmp/acp_install_catalog.py
RUN set -eux; \
    ACP_WRAPPER_DIR=/opt/acp-wrappers; \
    mkdir -p "$ACP_NODE_DIR" "$ACP_WRAPPER_DIR"; \
    PLAN=$(python3 /tmp/acp_install_catalog.py "$INSTALL_ACP_PROVIDERS") || exit 1; \
    eval "$PLAN"; \
    if [ -z "$PACKAGES" ]; then \
      echo "INSTALL_ACP_PROVIDERS is empty; no ACP providers will be installed"; \
      exit 0; \
    fi; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        ca-certificates curl xz-utils; \
    rm -rf /var/lib/apt/lists/*; \
    ARCH=$(uname -m); \
    case "$ARCH" in \
      x86_64|amd64) NARCH=x64; NODE_SHA256=6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6;; \
      aarch64|arm64) NARCH=arm64; NODE_SHA256=dbabf7a1cbf947e6059ffad2c27b80041db97dea1e553b62afdee7f13fca336e;; \
      *) echo "Unsupported architecture for ACP providers: '$ARCH'" >&2; exit 1;; \
    esac; \
    NODE_TARBALL="/tmp/node-v24.22.1-linux-${NARCH}.tar.xz"; \
    curl -fsSL --retry 5 --retry-delay 2 --retry-connrefused \
        "https://nodejs.org/dist/v24.22.1/node-v24.22.1-linux-${NARCH}.tar.xz" -o "$NODE_TARBALL"; \
    echo "$NODE_SHA256  $NODE_TARBALL" | sha256sum -c -; \
    tar -xJ --strip-components=1 -C "$ACP_NODE_DIR" -f "$NODE_TARBALL"; \
    rm -f "$NODE_TARBALL"; \
    "$ACP_NODE_DIR/bin/node" --version; \
    PATH="$ACP_NODE_DIR/bin:$PATH" "$ACP_NODE_DIR/bin/npm" install --global "npm@${NPM_VERSION}"; \
    PATH="$ACP_NODE_DIR/bin:$PATH" "$ACP_NODE_DIR/bin/npm" install --global $PACKAGES; \
    for bin in $WRAPPER_BINS; do \
      # 构建失败而不是发送执行缺失目标的包装器：
      # 错误的 binary_name 是不可见的，直到有人启动
      # 提供者，因为包装器只是一个 shell 脚本，我们 chmod +x。
      [ -x "$ACP_NODE_DIR/bin/$bin" ] || { \
        echo "ACP wrapper target not installed: $ACP_NODE_DIR/bin/$bin" >&2; \
        echo "(check binary_name in acp_install_catalog.py against the package's npm bin)" >&2; \
        exit 1; \
      }; \
      printf '#!/bin/sh\nPATH="%s/bin:$PATH" exec "%s/bin/%s" "$@"\n' \
        "$ACP_NODE_DIR" "$ACP_NODE_DIR" "$bin" \
        > "$ACP_WRAPPER_DIR/$bin"; \
      chmod +x "$ACP_WRAPPER_DIR/$bin"; \
    done; \
    printf '%s\n' $WRAPPER_BINS > "$ACP_NODE_DIR/acp-wrappers.txt"

####################################################################################
# 基础图像（最小）
# 它仅包含运行 Agent Server 及其 Bash 所需的软件包
# 和 Git APIs。 开发工具和可选功能位于基础映像中。
####################################################################################
FROM ${BASE_IMAGE} AS base-image-minimal
ARG USERNAME UID GID PORT ENABLE_VSCODE
ENV OH_ENABLE_VSCODE=${ENABLE_VSCODE}

ARG OPENHANDS_BUILD_GIT_SHA=unknown
ARG OPENHANDS_BUILD_GIT_REF=unknown
ENV OPENHANDS_BUILD_GIT_SHA=${OPENHANDS_BUILD_GIT_SHA}
ENV OPENHANDS_BUILD_GIT_REF=${OPENHANDS_BUILD_GIT_REF}

# 安装基础包并创建用户
RUN set -eux; \
    # 在最常见的包管理器中安装基础包，因为
    # 基准测试基础镜像并不总是基于 Debian。 `tini` 来自
    # apt/apk 上的发行版； rpm/zypper 系列的基础上没有 tini
    # repos，因此这些路径会进入下面的静态二进制安装。
    # 每条路径都必须以 PATH 上的工作 `tini` 结尾，因为 ENTRYPOINT
    # 该图像的的会无条件地调用它。
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get -o Acquire::Retries=5 update; \
        apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            bash ca-certificates git tini tmux; \
        rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache bash ca-certificates git shadow tini tmux; \
    elif command -v microdnf >/dev/null 2>&1; then \
        microdnf install -y bash ca-certificates curl git shadow-utils tmux; \
        microdnf clean all; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y bash ca-certificates curl git shadow-utils tmux; \
        dnf clean all; \
    elif command -v yum >/dev/null 2>&1; then \
        yum install -y bash ca-certificates curl git shadow-utils tmux; \
        yum clean all; \
    elif command -v zypper >/dev/null 2>&1; then \
        zypper --non-interactive install --no-recommends \
            bash ca-certificates curl git shadow tmux; \
        zypper clean --all; \
    else \
        echo "Unsupported base image: no known package manager found" >&2; \
        exit 1; \
    fi; \
    # 静态 tini 回退方案用于不提供它的包管理器。 已固定
    # 到每个拱门发布的 sha256，镜像上面的节点载荷。
    if ! command -v tini >/dev/null 2>&1; then \
        ARCH=$(uname -m); \
        case "$ARCH" in \
          x86_64|amd64) TARCH=amd64; TINI_SHA256=c5b0666b4cb676901f90dfcb37106783c5fe2077b04590973b885950611b30ee;; \
          aarch64|arm64) TARCH=arm64; TINI_SHA256=eae1d3aa50c48fb23b8cbdf4e369d0910dfc538566bfd09df89a774aa84a48b9;; \
          *) echo "Unsupported architecture for tini: '$ARCH'" >&2; exit 1;; \
        esac; \
        curl -fsSL --retry 5 --retry-delay 2 --retry-connrefused \
            "https://github.com/krallin/tini/releases/download/v0.19.0/tini-static-${TARCH}" \
            -o /usr/local/bin/tini; \
        echo "$TINI_SHA256  /usr/local/bin/tini" | sha256sum -c -; \
        chmod 755 /usr/local/bin/tini; \
    fi; \
    # 使构建失败，而不是发送 ENTRYPOINT 无法执行的映像。
    tini --version; \
    grep -Eq "^[^:]*:[^:]*:${GID}:" /etc/group || groupadd -g "${GID}" "${USERNAME}"; \
    grep -Eq "^${USERNAME}:" /etc/passwd || \
        useradd -m -u "${UID}" -g "${GID}" -s /bin/bash "${USERNAME}"; \
    mkdir -p /workspace/project; \
    chown -R "${USERNAME}:${USERNAME}" /workspace

# 安装 INSTALL_ACP_PROVIDERS 选择的 ACP 个服务器（参见上一阶段）。
# 载荷本身（Node.js 24 + ACP npm 包，在 $ACP_NODE_DIR 下）是
# 在上面的 ACP-providers 阶段构建一次，独立于 BASE_IMAGE，并且
# 复制到此处，以便该层在其着陆的每个基本图像上都是字节相同的
# 上。 只有下面的兼容性探测与真实的 BASE_IMAGE 运行。
#
# Node.js 24 存在于专用前缀中，因此 ACP 包可以获得现代运行时
# WITHOUT 覆盖测试套件所依赖的特定于存储库的 Node.js。
# SWE-bench 映像发布 NVM/apt-management Node 8-14，无法运行 ACP 包。
ENV ACP_NODE_DIR=/acp-node
COPY --from=acp-providers /acp-node /acp-node
COPY --from=acp-providers /opt/acp-wrappers/. /usr/local/bin/

# 该探针是尽力而为的：SWE-Bench Pro 基础镜像来自许多发行版
# 有些有旧的 glibc （或使用 musl），无法运行上游 Node 24
# glibc 构建。 上面的载荷已构建并针对固定的 sha256 进行了验证，
# glibc-modern 阶段，所以这里的失败意味着“与这个特定的不兼容”
# BASE_IMAGE”，而不是“ACP 安装失败”。 当这种情况发生时，我们删除
# 复制了载荷和包装器，因此构建的 REST （和非 ACP 智能体）
# 仍然可以工作，而不是将二进制文件留在无法执行的地方。 的
# 包装器名称来自 ACP-providers 阶段编写的清单，因此
# 跟踪 INSTALL_ACP_PROVIDERS 而不是每个提供商都过时的列表。
RUN if ! "$ACP_NODE_DIR/bin/node" --version >/dev/null 2>&1; then \
      echo "Warning: ACP Node 24 runtime is not compatible with this base image (likely older glibc or musl libc); ACP agents will not be available" >&2; \
      if [ -f "$ACP_NODE_DIR/acp-wrappers.txt" ]; then \
        while read -r bin; do rm -f "/usr/local/bin/$bin"; done \
          < "$ACP_NODE_DIR/acp-wrappers.txt"; \
      fi; \
      rm -rf "$ACP_NODE_DIR"/*; \
    fi

# 配置 Claude Code 托管设置以进行无头操作：
# 允许所有工具权限（循环中没有人批准）。
RUN mkdir -p /etc/claude-code && \
    echo '{"permissions":{"allow":["Edit","Read","Bash"]}}' > /etc/claude-code/managed-settings.json

USER ${USERNAME}
WORKDIR /
# libtmux 与 PyInstaller 版本一起使用所需的区域设置
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV LOG_JSON=true
# ACP CLIs 在这里没有用户的主机家，所以OpenHands 提供了
# 他们无法自己阅读托管技能目录（#4019）。
ENV OH_ACP_SKILL_SOURCING=openhands_managed
EXPOSE ${PORT}

####################################################################################
# 基础图像（完整）
# 它还包括 Docker、浏览器和 VSCode Web。
####################################################################################
FROM base-image-minimal AS base-image
ARG USERNAME
ARG INSTALL_CAPABILITIES

USER root

# 完整映像是通用开发环境。 保留编译器，
# 包/存储库帮助程序，以及二进制最小的命令行实用程序。
RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
        apt-get -o Acquire::Retries=5 update; \
        apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
            apt-transport-https apt-utils build-essential coreutils curl \
            findutils gnupg grep jq lsb-release procps sed sudo tar util-linux \
            wget xz-utils; \
        rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache \
            build-base coreutils curl findutils gnupg grep jq procps sudo tar \
            util-linux wget xz; \
    elif command -v microdnf >/dev/null 2>&1; then \
        microdnf install -y \
            coreutils curl findutils gcc gcc-c++ gnupg2 grep jq make procps-ng \
            sed sudo tar util-linux wget xz; \
        microdnf clean all; \
    elif command -v dnf >/dev/null 2>&1; then \
        dnf install -y \
            coreutils curl findutils gcc gcc-c++ gnupg2 grep jq make procps-ng \
            sed sudo tar util-linux wget xz; \
        dnf clean all; \
    elif command -v yum >/dev/null 2>&1; then \
        yum install -y \
            coreutils curl findutils gcc gcc-c++ gnupg2 grep jq make procps-ng \
            sed sudo tar util-linux wget xz; \
        yum clean all; \
    elif command -v zypper >/dev/null 2>&1; then \
        zypper --non-interactive install --no-recommends \
            coreutils curl findutils gcc gcc-c++ gpg2 grep jq make procps sed \
            sudo tar util-linux wget xz; \
        zypper clean --all; \
    fi; \
    usermod -aG sudo "${USERNAME}" 2>/dev/null || true; \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# 将 uv 保留为完整开发环境的一部分，但不是最小二进制。
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# 在花费任何时间在功能名称上之前，快速失败
# 安装如下（每个块仅检查 ITS OWN 关键字的存在，因此
# 否则，无法识别的错误将被默默地忽略而不是出错）。
RUN set -eux; \
    for capability in $(echo "$INSTALL_CAPABILITIES" | tr ',' ' '); do \
      case "$capability" in \
        vscode|browser|docker) ;; \
        *) echo "Unknown capability '$capability' in INSTALL_CAPABILITIES" \
             "(expected one of: vscode, browser, docker)" >&2; exit 1;; \
      esac; \
    done

# --- VSCode 网页 ---
# EDITOR/VISUAL/GIT_EDITOR/OPENVSCODE_SERVER_ROOT 无条件声明：
# nothing execs `code` 除非 VSCode Web本身在运行，所以是一个悬空的
# 排除 `vscode` 时的路径是无害的（与 CHROME_BIN 的推理相同）
# below, applied to VSCode).
ENV EDITOR=code \
    VISUAL=code \
    GIT_EDITOR="code --wait" \
    OPENVSCODE_SERVER_ROOT=/openhands/.openvscode-server
ARG RELEASE_TAG="openvscode-server-v1.109.5"
ARG RELEASE_ORG="gitpod-io"
# 下面扩展 RUN 上的 --mount=from=builder 是无条件的
# Dockerfile 级别，因此 BuildKit 仍然构建完整的 `builder` 阶段
# （整个 SDK venv）即使 `vscode` 被排除在外
# INSTALL_CAPABILITIES — 每个 RUN 内的案例检查仅决定什么
# 落在 THIS 图像中，而不是作为依赖项构建的图像。 排除 vscode
# 缩小结果，而不是构建时间。
RUN set -eux; \
    case ",$INSTALL_CAPABILITIES," in \
      *,vscode,*) ;; \
      *) echo "INSTALL_CAPABILITIES excludes vscode; skipping OpenVSCode Server"; exit 0;; \
    esac; \
    \
    # 创建必要的目录
    mkdir -p $(dirname ${OPENVSCODE_SERVER_ROOT}); \
    \
    # 确定架构
    arch=$(uname -m); \
    if [ "${arch}" = "x86_64" ]; then \
        arch="x64"; \
    elif [ "${arch}" = "aarch64" ]; then \
        arch="arm64"; \
    elif [ "${arch}" = "armv7l" ]; then \
        arch="armhf"; \
    fi; \
    \
    # 下载并安装 VSCode 服务器
    wget https://github.com/${RELEASE_ORG}/openvscode-server/releases/download/${RELEASE_TAG}/${RELEASE_TAG}-linux-${arch}.tar.gz; \
    tar -xzf ${RELEASE_TAG}-linux-${arch}.tar.gz; \
    if [ -d "${OPENVSCODE_SERVER_ROOT}" ]; then rm -rf "${OPENVSCODE_SERVER_ROOT}"; fi; \
    mv ${RELEASE_TAG}-linux-${arch} ${OPENVSCODE_SERVER_ROOT}; \
    cp ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/openvscode-server ${OPENVSCODE_SERVER_ROOT}/bin/remote-cli/code; \
    rm -f ${RELEASE_TAG}-linux-${arch}.tar.gz; \
    \
    # 将捆绑的 Node.js（v1.109.5 中的 22.21.1）替换为 22.23.4，其中
    # 修复了 Brotli 解码器溢出 CVE-2026-111497。 没有 OpenVSCode 服务器
    # 发布捆绑了一个固定的节点； 一旦有人这样做，就放弃这个。
    case "${arch}" in \
      x64) NARCH=x64; NODE_SHA256=1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce;; \
      arm64) NARCH=arm64; NODE_SHA256=6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b;; \
      armhf) NARCH=armv7l; NODE_SHA256=c9057c6a3b8fbb9651ed115c1e96d4a7281b7b9c9ca89fa05865c98ed7ffd437;; \
      *) echo "Unsupported architecture for OpenVSCode Node: '${arch}'" >&2; exit 1;; \
    esac; \
    NODE_TARBALL="/tmp/node-v22.23.4-linux-${NARCH}.tar.xz"; \
    wget -nv -O "$NODE_TARBALL" "https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-${NARCH}.tar.xz"; \
    echo "$NODE_SHA256  $NODE_TARBALL" | sha256sum -c -; \
    tar -xJf "$NODE_TARBALL" -O "node-v22.23.4-linux-${NARCH}/bin/node" > ${OPENVSCODE_SERVER_ROOT}/node; \
    chmod 755 ${OPENVSCODE_SERVER_ROOT}/node; \
    rm -f "$NODE_TARBALL"; \
    ${OPENVSCODE_SERVER_ROOT}/node --version; \
    \
    # 设置适当的所有权
    chown -R ${USERNAME}:${USERNAME} ${OPENVSCODE_SERVER_ROOT}

# 保留为自己的 RUN，与上面的 tarball 下载分开：扩展
# 是主动编辑的本地源代码（与固定的版本 tarball 不同），因此
# 拆分它们可以防止仅扩展的更改使 ~100MB 无效
# 下载的缓存层。
RUN --mount=type=bind,from=builder,source=/agent-server/openhands-agent-server/openhands/agent_server/vscode_extensions,target=/tmp/vscode_extensions \
    set -eux; \
    case ",$INSTALL_CAPABILITIES," in \
      *,vscode,*) ;; \
      *) exit 0;; \
    esac; \
    \
    # 尾部斜杠很重要：OpenVSCode 服务器的 tarball 已经发布了
    # 自己的扩展/目录，因此裸露的 `cp -r src dst` 会将 src 嵌套在
    # 现有的 dst 而不是像 `COPY` 那样合并到其中。
    mkdir -p ${OPENVSCODE_SERVER_ROOT}/extensions; \
    cp -r /tmp/vscode_extensions/. ${OPENVSCODE_SERVER_ROOT}/extensions/; \
    chown -R ${USERNAME}:${USERNAME} ${OPENVSCODE_SERVER_ROOT}/extensions

# --- Docker ---
RUN set -eux; \
    case ",$INSTALL_CAPABILITIES," in \
      *,docker,*) ;; \
      *) echo "INSTALL_CAPABILITIES excludes docker; skipping Docker Engine"; exit 0;; \
    esac; \
    \
    # 确定操作系统类型并相应地安装 Docker
    if grep -q "ubuntu" /etc/os-release; then \
        # 处理Ubuntu
        install -m 0755 -d /etc/apt/keyrings; \
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; \
        chmod a+r /etc/apt/keyrings/docker.asc; \
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null; \
    else \
        # 处理 Debian
        install -m 0755 -d /etc/apt/keyrings; \
        curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc; \
        chmod a+r /etc/apt/keyrings/docker.asc; \
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null; \
    fi; \
    # 安装 Docker Engine、containerd 和 Docker Compose
    apt-get update; \
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    \
    # 将 Docker 守护进程配置为 MTU 1450 以防止数据包碎片问题
    mkdir -p /etc/docker; \
    echo '{"mtu": 1450}' > /etc/docker/daemon.json

# --- GitHub CLI ---
RUN set -eux; \
    mkdir -p -m 755 /etc/apt/keyrings; \
    wget -nv -O /etc/apt/keyrings/githubcli-archive-keyring.gpg \
        https://cli.github.com/packages/githubcli-archive-keyring.gpg; \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list; \
    apt-get update; \
    apt-get install -y gh; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# --- 浏览器 ---
# Chromium for BrowserToolSet. 由 `browser` 能力选择。
ENV CHROME_BIN=/usr/bin/chromium \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu"

# 上面的CHROME_BIN/PUPPETEER_EXECUTABLE_PATH是无条件声明的
# 无论选择哪种功能。 这个仓库中没有任何东西值得信任
# 将它们作为可用性信号 — browser_use 的铬检测
# (openhands-tools/openhands/tools/browser_use/impl.py它自己有文件系统
# 标准安装路径的探测 - 因此当 `browser` 被排除时，这些简单
# 指向不存在的路径，而不是导致 False“可用”
# 信号下游。
RUN set -eux; \
    case ",$INSTALL_CAPABILITIES," in \
      *,browser,*) \
        apt-get update; \
        apt-get install -y --no-install-recommends \
          "$(if grep -q "ubuntu" /etc/os-release; then echo "chromium-browser"; else echo "chromium"; fi)"; \
        apt-get clean; rm -rf /var/lib/apt/lists/*; \
        ;; \
    esac

USER ${USERNAME}
WORKDIR /
ENV LOG_JSON=true
# ACP CLIs 在这里没有用户的主机家，所以OpenHands 提供了
# 他们无法自己阅读托管技能目录（#4019）。
ENV OH_ACP_SKILL_SOURCING=openhands_managed
EXPOSE ${PORT}


####################################################################################
####################################################################################
# 建立目标
####################################################################################
####################################################################################

############################
# 目标A：来源
# 本地开发和调试模式：从构建器复制源代码+ venv
############################
FROM base-image AS source
ARG USERNAME
COPY --chown=${USERNAME}:${USERNAME} --from=builder /agent-server /agent-server
ENTRYPOINT ["tini", "--", "/agent-server/.venv/bin/python", "-m", "openhands.agent_server"]

FROM base-image-minimal AS source-minimal
ARG USERNAME
COPY --chown=${USERNAME}:${USERNAME} --from=builder /agent-server /agent-server
ENTRYPOINT ["tini", "--", "/agent-server/.venv/bin/python", "-m", "openhands.agent_server"]

############################
# 目标 B：二进制运行时
# 生产模式：在Docker内构建二进制文件并将其复制进去。
# 注意：不再支持外部工件上下文。
############################
FROM base-image AS binary
ARG USERNAME

COPY --chown=${USERNAME}:${USERNAME} --from=binary-builder /agent-server/dist/openhands-agent-server /usr/local/bin/openhands-agent-server
RUN chmod +x /usr/local/bin/openhands-agent-server
# 修复库路径以使用系统 GCC 库而不是捆绑库
ENV LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:/usr/lib:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
ENTRYPOINT ["tini", "--", "/usr/local/bin/openhands-agent-server"]

FROM base-image-minimal AS binary-minimal
ARG USERNAME
COPY --chown=${USERNAME}:${USERNAME} --from=binary-builder /agent-server/dist/openhands-agent-server /usr/local/bin/openhands-agent-server
RUN chmod +x /usr/local/bin/openhands-agent-server
# 修复库路径以使用系统 GCC 库而不是捆绑库
ENV LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:/usr/lib:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
ENTRYPOINT ["tini", "--", "/usr/local/bin/openhands-agent-server"]
