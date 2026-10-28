<a id="release-automation-workflows"></a>

# 发布自动化工作流程

本文档描述了 OpenHands 软件智能体 SDK 的自动发布工作流程。

<a id="overview"></a>

## 概述

发布流程使用 `create-release.yml` 作为其唯一的协调器：

1. **prepare-release.yml** 准备了具有同步包版本的发行版 PR。
2. 合并版本 PR 运行 **create-release.yml**，这会创建 GitHub 版本并根据其不可变标签显式分派每个发布者。
3. 分派的工作流发布 Python 包、TypeScript 客户端、智能体服务器映像和发布二进制文件。

发布者工作流程不侦听 GitHub 发布事件。 这避免了依赖于`GITHUB_TOKEN`创建的事件，GitHub不用于触发下游工作流。

<a id="how-to-create-a-new-release"></a>

## 如何创建新版本

<a id="step-1-trigger-the-prepare-release-workflow"></a>

### 第 1 步：触发准备发布工作流程

1. 转至 [“操作”选项卡](https://github.com/OpenHands/software-agent-sdk/actions)
2. 从左侧边栏中选择 **“准备发布”** 工作流程
3. 单击**“运行工作流程”**按钮
4. 输入版本号（e.g.、`1.2.3`） - 格式必须为 `X.Y.Z`
5. 单击 **“运行工作流程”**

工作流程将自动：
- ✅ 创建一个名为 `rel-X.Y.Z` 的新分支
- ✅ 使用 `make set-package-version` 更新所有软件包版本
- ✅ 将 TypeScript 客户端固定到 `agent-server:X.Y.Z-python` 并从分支的 OpenAPI 合约重新生成其类型，因此 npm 包与其版本相匹配
- ✅ 提交更改
- ✅推树枝
- ✅ 创建一个带有标签 `integration-tests` 和 `test-examples` 的 PR

<a id="step-2-review-the-pr"></a>

### 第 2 步：查看 PR

创建的 PR 将包含一个清单。 完成以下内容：

- [ ] 修正任何弃用个截止日期（如果存在）
- []验证集成测试通过（由`integration-tests`标签触发）
- [ ] 验证示例检查通过（由 `test-examples` 标签触发）
- [ ] 确认任何合并的 `release-note-required` PR 在最终的发布说明中被准确调用
- [ ] 审核并批准 PR

<a id="step-3-merge-the-release-pr"></a>

### 第 3 步：合并版本 PR

合并版本 PR 运行 **create-release.yml**，其中：

- 在合并提交时创建标签并 GitHub 释放 `vX.Y.Z`；
- 显式分发版本 `X.Y.Z` 的 PyPI 出版物；
- 明确地将 TypeScript 发布到 npm 和 GitHub 包版本 `X.Y.Z`。
- 显式调度版本化的智能体-针对标签 `vX.Y.Z` 构建的服务器映像；
- 针对标签 `vX.Y.Z` 显式调度发布二进制文件。

每个发布者都会在发布之前验证其签出的包版本是否与请求的版本匹配。 在 [“操作”选项卡 ](https://github.com/OpenHands/software-agent-sdk/actions) 中监视已分派的工作流。

<a id="step-4-release-binaries--docker-smoke-test-automated"></a>

### 第 4 步：发布二进制文件 + Docker 冒烟测试（自动）

**release-binaries.yml** 已明确调度以进行发布。 它还会在每次按下 `main` 时运行，作为持续的烟雾覆盖。 它：

- ✅ 在 5 运行器矩阵（linux x86_64/arm64、macOS x86_64/arm64、windows x86_64）上构建智能体-server PyInstaller 二进制文件，并分别进行冒烟测试
- ✅ 导出并验证确定性公共 Agent Server 合约
  `openapi.json`，其中 `info.version` 与发布版本匹配
- ✅ 生成组合的 `SHA256SUMS` 并附加二进制文件和
  发布/手动运行时的 `openapi.json` 到 GitHub 版本
- ✅ 验证多架构 Docker 清单
  `ghcr.io/openhands/agent-server:<image-tag>-<variant>` 发表者
  `server.yml` 涵盖每个变体的 `linux/amd64` 和 `linux/arm64`（`python`、`java`、`golang`）
- ✅ 使用 `--platform=linux/<arch>` 拉取每个架构上的每个变体，启动容器，并断言 `/health` 响应

对于 `push` 事件，`<image-tag>` 是 7 个字符的提交 SHA 和二进制文件加上
`openapi.json` 仅保留为工作流程工件。 在发布/手动运行时，
`<image-tag>` 是发布版本，二进制文件加上 `openapi.json` 将上传到 GitHub 版本。

<a id="build-time--runner-expectations"></a>

#### 构建时间/跑步者期望

| 舞台 | 运行时间（典型） | 跑步者 |
|---|---|---|
| 二进制构建（5 路矩阵，并行） | Linux 上约为 10–15 分钟，macOS 上约为 12–18 分钟 | `ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-14`, `windows-2022` |
| `publish-binaries`（下载+校验+上传） | 约 1–2 分钟 | `ubuntu-24.04` |
| `docker-smoke-test`（6路矩阵，并行） | 最多 45 分钟（主要轮询 Docker 图像） | `ubuntu-24.04` 对于 amd64，`ubuntu-24.04-arm` 对于 arm64 |

<a id="qemu--buildx-requirements"></a>

#### QEMU/buildx 要求

冒烟测试 ** 不 ** 需要 QEMU：每个（变体，arch）作业在架构与 `--platform=linux/<arch>` 匹配的运行器上运行，因此容器在本机运行。 我们仍然设置 Docker Buildx，以便我们可以调用
多架构清单列表中的 `docker buildx imagetools inspect`。

多架构清单的等待窗口为 45 分钟 — 足够长以吸收完整的 `server.yml` 矩阵运行时间（`build-and-push-image` + 约 25–30 分钟）
`merge-manifests`) 当此工作流与相应的 `server.yml` 运行竞争发布标签或主分支推送时。

如果匹配的清单已在 GHCR 中，则等待步骤立即退出。

<a id="step-5-version-bump-prs-automated"></a>

### 第 5 步：版本更新 PR（自动）

成功发布 PyPI 后，工作流程将自动创建 PR 以更新下游存储库中的 SDK 版本：

- **[自动化](https://github.com/OpenHands/automation)** - 更新 `openhands-sdk` 和 `openhands-workspace` 版本。 以开始 `fix:` 标题：请在repo的release-please分支上发布一个补丁版本，发布一个  `openhands-automation` 锁定此构建 SDK (which the 智能体-canvas `sdk-version-sync` 检查。
- **TypeScript 客户端 (`clients/typescript`)** - 通常无操作：版本 PR 已固定客户端。 如果客户端落后于版本，它只会在此存储库中打开 PR。 它等待确切的 GHCR 映像并发布 `openapi.json`、更新 `config.agentServerImage`、重新生成签入的传输层类型，并包含 API 更改摘要。

这些 PR 将：
- 使用分支名称 `bump-sdk-X.Y.Z` 自动创建（`bump-agent-server-X.Y.Z` 表示 TypeScript-客户端）
- 包含返回 SDK 版本的链接
- 包含针对确切发布版本生成的 Agent Server 合同更改，而不仅仅是更改图像标签
- 需要维护者审核并合并

<a id="step-6-post-release-tasks"></a>

### 第 6 步：发布后任务

- [ ] 将版本 PR 合并到主版本
- [ ] 审核并合并自动化创建的版本更新 PR，以及客户端 TypeScript（合并自动化 PR 会触发其发布，请发布 PR）。 也将其合并以发布固定的 `openhands-automation`）
- [ ] 宣布发布

<a id="manual-publication-recovery"></a>

## 手动出版物恢复

对于重试注册表发布者，运行 `main` 中的最新工作流程并传递不带前导 `v` 的发布版本。 工作流程在发布之前检查相应的不可变 `vX.Y.Z` 标签并验证其包版本。 例如，恢复`v1.45.0`，版本输入`1.45.0`； 切勿从移动分支发布包内容。

可独立重试的发布者工作流程包括：

- **发布PyPI的所有OpenHands个包(uv)**；
- **将TypeScript客户端发布到npm**；
- **将TypeScript客户端发布到GitHub包**；
- **Agent Server** 用于版本化容器镜像；
- **发布智能体-二进制文件的服务器发布工件**和`openapi.json`。

<a id="workflow-files"></a>

## 工作流程文件

- `.github/workflows/prepare-release.yml` - 自动发布准备
- `.github/workflows/create-release.yml` - GitHub 发布创建和唯一发布者协调器
- `.github/workflows/pypi-release.yml` - 仅调度 PyPI 包发布
- `.github/workflows/typescript-client-npm-publish.yml` - 仅调度 npm 发布
- `.github/workflows/typescript-client-github-packages-publish.yml` - 仅调度 GitHub 包发布
- `.github/workflows/server.yml` - 智能体-服务器构建用于 PR、主要和显式发布调度
- `.github/workflows/release-binaries.yml` - 多架构二进制发布和 Docker 对主要和显式发布调度的明显冒烟测试

<a id="troubleshooting"></a>

## 故障排除

<a id="version-format-error"></a>

### 版本格式错误

如果出现版本格式错误，请确保使用格式 `X.Y.Z` (e.g., `1.2.3`)，而不是 `vX.Y.Z`。

<a id="pr-creation-failed"></a>

### PR 创建失败

如果PR创建失败，请检查：
- 该分支尚不存在
- 您有适当的权限
- `GITHUB_TOKEN`有足够的权限

<a id="pypi-publication-failed"></a>

### PyPI 发布失败

如果 PyPI 发布失败：
- 检查`PYPI_TOKEN_OPENHANDS`机密配置是否正确
- 验证 PyPI 上尚不存在该版本
- 检查工作流日志中的特定错误消息

<a id="release-binaries-failed"></a>

### 发布二进制文件失败

如果 `release-binaries.yml` 失败：
- **二进制构建失败**：重新运行失败的矩阵作业； PyInstaller 薄片很少见，但也是可能的。 如果问题仍然存在，则问题可能出现在 `agent-server.spec` 中。
- **`docker-smoke-test` 等待清单超时**：`server.yml` 未发布匹配发布标记或提交的多架构映像 SHA。 检查工作流程的相应运行并在需要时重新触发。
- **`/health`从未响应**：打开失败的作业； 清理陷阱转储容器的最后 100 行 `docker logs`。
- 可以通过以下方式针对现有标签重新运行发布/手动运行
  `workflow_dispatch` 与 `release_tag` 输入 (e.g. `v1.20.1`);
  `gh release upload --clobber` 使这变得安全。

<a id="previous-manual-process"></a>

## 以前的手动流程

作为参考，之前的手动发布清单是：

- [ ] 签出 SDK 存储库，使用 `make set-package-version version=x.x.x` 设置版本
- [ ] 推送到类似 `rel-x.x.x` 的分支并启动 PR
- [ ] 修复任何“弃用截止日期”（如果存在）
- [ ] 标记“集成测试”并确保集成测试全部通过
- [ ] 标记“test-examples”并确保示例检查全部通过
- [ ] 起草新版本
- [ ] 使用工作流程发布到标签 `v1.X.X` 上的 PyPI

大多数这些步骤现在都是自动化的！
