---
name: cross-repo-testing
description: This skill should be used when the user asks to "test a saas cross-repo feature", "deploy a feature branch to staging", "test SDK against OH Cloud branch", "e2e test a cloud workspace feature", "test secrets saas inheritance", or when changes span the SDK and OpenHands enterprise and need end-to-end validation against a staging deployment.
---

<a id="cross-repo-testing-sdk--openhands-cloud"></a>

# 跨存储库测试：SDK ↔ OpenHands 云

如何端到端测试跨越 `OpenHands/software-agent-sdk` 和 `OpenHands/OpenHands`（云后端）的功能。

<a id="repository-map"></a>

## 存储库地图

| 回购协议 | 角色 | 这里住着什么 |
|------|------|-----------------|
| [`software-agent-sdk`](https://github.com/OpenHands/software-agent-sdk) | 智能体核心 | `openhands-sdk`、`openhands-workspace`、`openhands-tools` 个包。 `OpenHandsCloudWorkspace` 住在这里。 |
| [`OpenHands`](https://github.com/OpenHands/OpenHands) | 云后台 | FastAPI 服务器 (`openhands/app_server/`)、沙箱管理、身份验证、企业集成。 部署为 OH 云。 |
| [`deploy`](https://github.com/OpenHands/deploy) | 基础设施 | Helm 图表 + GitHub 构建企业 Docker 映像并部署到登台/生产的操作。 |

**数据流：**SDK客户端→OH Cloud API（`/api/v1/...`）→沙箱智能体-服务器（运行时容器内）

<a id="when-you-need-this"></a>

## 当你需要时

根据依赖关系的走向，有 ** 两个流 **：

| 流量 | 当 | 示例 |
|------|------|---------|
| **A — SDK 客户端 → 新云 API** | SDK 调用生产中尚不存在的 API | `workspace.get_llm()` 呼叫 `GET /api/v1/users/me?expose_secrets=true` |
| **B — OH 服务器 → 新 SDK 代码 ** | 云服务器需要未发布的 SDK 软件包或新的智能体服务器映像 | 服务器使用 SDK 中的新工具、智能体行为或工作区方法 |

流程A只需要部署服务器PR。 流程 B 需要使用 SDK PR 的智能体服务器映像将 SDK 固定到服务器 PR ** 和 ** 中未发布的提交。 两种流程可以同时应用。

---

<a id="flow-a-sdk-client-tests-against-new-cloud-api"></a>

## 流程 A：SDK 针对新云的客户端测试 API

当 SDK 调用仅存在于服务器 PR 分支上的端点时，请使用此选项。

<a id="a1-write-and-test-the-server-side-changes"></a>

### A1. 编写并测试服务器端更改

在 `OpenHands` 存储库中，实现新的 API endpoint(s)。 运行单元测试：

```bash
cd OpenHands
poetry run pytest tests/unit/app_server/test_<relevant>.py -v
```

推PR。 等待 **“推送企业映像”(Docker) CI 作业 ** 成功 — 这将构建 `ghcr.io/openhands/enterprise-server:sha-<COMMIT>`。

<a id="a2-write-the-sdk-side-changes"></a>

### A2. 写入SDK端的修改

在 `software-agent-sdk` 中，实现客户端代码（e.g.，`OpenHandsCloudWorkspace` 上的新方法）。 运行SDK单元测试：

```bash
cd software-agent-sdk
pip install -e openhands-sdk -e openhands-workspace
pytest tests/ -v
```

推PR。 SDK CI 是独立的——它不需要服务器更改来通过单元测试。

<a id="a3-deploy-the-server-pr-to-staging"></a>

### A3. 将服务器 PR 部署到暂存区

请参阅下面的[部署到暂存功能环境](#deploying-to-a-staging-feature-environment)。

<a id="a4-run-the-sdk-e2e-test-against-staging"></a>

### A4. 针对登台运行 SDK e2e 测试

请参阅下面的[针对分期运行E2E测试](#running-e2e-tests-against-staging)。

---

<a id="flow-b-oh-server-needs-unreleased-sdk-code"></a>

## 流程 B：OH 服务器需要未发布的 SDK 代码

使用此选项，当云服务器依赖于  SDK 尚未发布的更改 PyPI yet. 服务器的运行时容器运行  `agent-server` 由构建的图像 SDK repo，所以服务器 PR 必须配置为使用 SDK  PR's image and packages。

<a id="b1-get-the-sdk-pr-merged-or-identify-the-commit"></a>

### B1. 合并 SDK PR（或识别提交）

SDK PR 必须具有 CI 通行证，以便构建其智能体-服务器 Docker 映像。 该图像被标记为来自 GitHub 操作的 ** 合并提交 SHA ** - 不头提交 SHA，如 PR 中所示。

找到正确的图像标签：
- 检查 `AGENT_SERVER_IMAGES` 部分的 SDK PR 描述
- 或者检查 `"short_sha": "<tag>"` 的“整合构建信息”CI 作业

<a id="b2-pin-sdk-packages-to-the-commit-in-the-openhands-pr"></a>

### B2. 将 SDK 包固定到 OpenHands PR 中的提交

在 `OpenHands` 存储库 PR 中，更新 3 个文件 + 重新生成 3 个锁文件（有关完整详细信息，请参阅 `update-sdk` 技能）：

**`pyproject.toml`** — 将所有 3 SDK 封装固定在 **** `dependencies` 和 `[tool.poetry.dependencies]` 中：
```toml
# 依赖项数组 (PEP 508)
"openhands-sdk @ git+https://github.com/OpenHands/software-agent-sdk.git@<COMMIT>#subdirectory=openhands-sdk",
"openhands-agent-server @ git+https://github.com/OpenHands/software-agent-sdk.git@<COMMIT>#subdirectory=openhands-agent-server",
"openhands-tools @ git+https://github.com/OpenHands/software-agent-sdk.git@<COMMIT>#subdirectory=openhands-tools",

# [tool.poetry.dependencies]
openhands-sdk = { git = "https://github.com/OpenHands/software-agent-sdk.git", rev = "<COMMIT>", subdirectory = "openhands-sdk" }
openhands-agent-server = { git = "https://github.com/OpenHands/software-agent-sdk.git", rev = "<COMMIT>", subdirectory = "openhands-agent-server" }
openhands-tools = { git = "https://github.com/OpenHands/software-agent-sdk.git", rev = "<COMMIT>", subdirectory = "openhands-tools" }
```

**`openhands/app_server/sandbox/sandbox_spec_service.py`** — 使用 SDK 的合并提交 SHA：
```python
AGENT_SERVER_IMAGE = 'ghcr.io/openhands/agent-server:<merge-commit-sha>-python'
```

**重新生成锁个文件：**
```bash
poetry lock && uv lock && cd enterprise && poetry lock && cd ..
```

<a id="b3-wait-for-the-openhands-enterprise-image-to-build"></a>

### B3. 等待OpenHands企业形象打造

推送固定的更改。 OpenHands CI 将构建一个新的企业 Docker 映像 (`ghcr.io/openhands/enterprise-server:sha-<OH_COMMIT>`)，该映像捆绑未发布的 SDK。 等待“推企业形象”工作成功。

<a id="b4-deploy-and-test"></a>

### B4. 部署和测试

使用新的 OpenHands 提交 SHA 按照 [ 部署到暂存功能环境 ](#deploying-to-a-staging-feature-environment) 进行操作。

<a id="b5-before-merging-remove-the-pin"></a>

### B5. 合并前：移除销钉

**CI守卫：如果`[tool.poetry.dependencies]`包含`rev`字段，**`check-package-versions.yml`块合并到`main`。 在OpenHandsPR可以合并之前，SDKPR必须合并并发布到PyPI，然后pin必须替换为发布的版本号。

---

<a id="deploying-to-a-staging-feature-environment"></a>

## 部署到暂存功能环境

`deploy` 存储库从 OpenHands PR 创建预览环境。

**选项 A — GitHub 操作 UI（首选）：**
转到 `OpenHands/deploy` → 操作 → “创建 OpenHands 预览 PR” → 输入 OpenHands PR 数字。 这将创建一个分支 `ohpr-<PR>-<random>` 并打开一个部署 PR。

**选项 B — 更新现有功能分支：**
```bash
cd deploy
git checkout ohpr-<PR>-<random>
# 在.github/workflows/deploy.yaml中，更新BOTH：
#   OPENHANDS_SHA: "<full-40-char-commit>"
#   OPENHANDS_RUNTIME_IMAGE_TAG：“<same-commit>-尼古拉克”
git commit -am "Update OPENHANDS_SHA to <commit>" && git push
```

**更新SHA**之前，验证企业Docker镜像是否存在：
```bash
gh api repos/OpenHands/OpenHands/actions/runs \
  --jq '.workflow_runs[] | select(.head_sha=="<COMMIT>") | "\(.name): \(.conclusion)"' \
  | grep Docker
# 必须显示：“Docker：成功”
```

部署 CI 自动触发并在以下位置创建环境：
```
https://ohpr-<PR>-<random>.staging.all-hands.dev
```

** 等它上线：**
```bash
curl -s -o /dev/null -w "%{http_code}" https://ohpr-<PR>-<random>.staging.all-hands.dev/api/v1/health
# 401 = server is up (auth required). DNS may take 1-2 min on first deploy.
```

<a id="running-e2e-tests-against-staging"></a>

## 针对分期运行 E2E 测试

**严重：功能部署有自己的 Keycloak 实例。** `app.all-hands.dev` 或 `$OPENHANDS_API_KEY` 中的 API 个键将不起作用。 您需要用于特定功能部署的测试 API 密钥。 用户必须提供一份。

```python
from openhands.workspace import OpenHandsCloudWorkspace

STAGING = "https://ohpr-<PR>-<random>.staging.all-hands.dev"

with OpenHandsCloudWorkspace(
    cloud_api_url=STAGING,
    cloud_api_key="<test-api-key-for-this-deployment>",
) as workspace:
    # 测试新功能
    llm = workspace.get_llm()
    secrets = workspace.get_secrets()
    print(f"LLM: {llm.model}, secrets: {list(secrets.keys())}")
```

或者运行示例脚本：
```bash
OPENHANDS_CLOUD_API_KEY="<key>" \
OPENHANDS_CLOUD_API_URL="https://ohpr-<PR>-<random>.staging.all-hands.dev" \
python examples/02_remote_agent_server/10_cloud_workspace_saas_credentials.py
```

<a id="recording-results"></a>

### 记录结果

将测试输出推送到 SDK PR 的 `.pr/logs/` 目录：
```bash
cd software-agent-sdk
python test_script.py 2>&1 | tee .pr/logs/<test_name>.log
git add -f .pr/logs/<test_name>.log .pr/README.md
git commit -m "docs: add e2e test results" && git push
```

对 ** 两个 PR** 进行评论，并提供通过/失败摘要和日志链接。

<a id="key-gotchas"></a>

## 关键问题

| 陷阱 | 详情 |
|--------|---------|
| **功能环境身份验证被隔离** | 每个 `ohpr-*` 部署都有自己的 Keycloak。 生产 API 键不起作用。 |
| **两 SHAs deploy.yaml** | `OPENHANDS_SHA` 和 `OPENHANDS_RUNTIME_IMAGE_TAG` 都必须更新。 运行时标签是`<sha>-nikolaik`。 |
| **企业形象必须存在** | OpenHands PR 上的 Docker CI 作业必须成功才能部署。 如果它还没有运行，则推送一个空提交来触发它。 |
| **DNS传播** | DNS 首次部署新分支需要 1-2 分钟。 后续部署是即时的。 |
| **合并提交 SHA ≠ head SHA** | SDK CI 标签 Docker 图像具有 GitHub 操作的合并提交 SHA，而不是 PR 头 SHA。 检查 SDK PR 描述或 CI 日志以获取正确的标签。 |
| **SDK 引脚块合并** | `check-package-versions.yml` 防止合并 `[tool.poetry.dependencies]` 中具有 `rev` 字段的 OpenHands PR。 SDK必须首先释放到PyPI。 |
| **流程A：库存智能体-服务器正常** | 当只有云 API 发生变化时，`OpenHandsCloudWorkspace` 与云服务器通信，而不是与智能体服务器通信。 无需自定义图像。 |
| **流程 B：智能体-需要服务器映像** | 当服务器需要运行时容器内的新 SDK 代码时，您必须固定到 SDK PR 的智能体服务器映像。 |
