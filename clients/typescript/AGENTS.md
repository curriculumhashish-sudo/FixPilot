<a id="agent-server-typescript-client-clientstypescript"></a>

# Agent Server TypeScript 客户端 (`clients/typescript`)

<a id="general-purpose"></a>

## 通用型

此目录包含 OpenHands Agent Server 的 TypeScript 客户端库。 它提供了一个完整的、类型安全的接口来与 OpenHands Agent Server API 交互，使开发者能够构建能够创建和管理 AI 智能体对话、工作区和实时事件流的应用程序。

客户端设计模仿了的结构和功能 Python  SDK 在这个单体仓库在提供自然语言的同时 TypeScript/JavaScript  APIs 具有完整类型安全性和现代开发工具。

<a id="cross-repository-boundaries"></a>

## 跨存储库边界

此目录拥有 OpenHands Agent Server API 的浏览器兼容的 TypeScript 客户端。 规范的 API 实现和行为位于此存储库的 Python SDK 和 Agent Server 包中； [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 使用此客户端来获取 Agent Canvas UI； [`OpenHands/extensions`](https://github.com/OpenHands/extensions) 拥有可重用的技能、插件、自动化和集成； [`OpenHands/automation`](https://github.com/OpenHands/automation) 拥有调度、Webhook、运行历史记录和调度。

正常流程是SDK/Agent Server→OpenAPI合约→该客户端→Agent Canvas。 保持后端行为和端点在Python SDK或Agent Server包中，API访问类型在本目录中，UI在Agent Canvas，自动化生命周期行为在`automation`。

所有拉取请求都必须遵循存储库的贡献和适用的代码审查指南。

<a id="key-features"></a>

## 主要特点

- **完整的 API 覆盖范围**：实现 OpenHands Agent Server OpenAPI 规范中的所有端点
- **类型安全**：全面TypeScript支持全面的接口和类型定义
- **实时事件**：WebSocket客户端用于流式传输对话事件和智能体状态更新
- **工作区管理**：文件操作、上传、下载和工作区状态管理
- **对话生命周期**：创建、启动、停止和管理 AI 智能体对话
- **错误处理**：使用自定义异常类和重试逻辑进行强大的错误处理
- **现代工具**：ESLint、Prettier、Vitest和GitHub Actions CI/CD

<a id="browser-compatibility-requirement"></a>

## 浏览器兼容性要求

** 本库中的所有代码都必须兼容浏览器。** 这是一个硬性约束——SDK 设计用于浏览器环境运行，并且必须永远不依赖于Node.js 特定的APIs。

**不使用：**

- `fs`、`fs/promises` 或任何文件系统 APIs
- `child_process`、`spawn`、`exec` 或任何进程执行 APIs
- `path`（Node.js 模块 — 使用字符串操作或 URL APIs 代替）
- `os`、`net`、`http`、`https`、`stream`、`buffer`（Node.js内置的），`crypto`（Node.js内置的），或者任何内置的Node.js模块
- 任何依赖于 Node.js 内置模块的 npm 包

**请使用：**

- `fetch` 用于 HTTP 个请求
- `WebSocket` 实时通讯
- Web 标准 APIs (`URL`, `Blob`, `File`, `FormData`, `TextEncoder`/`TextDecoder`, etc.)
- 仅与浏览器兼容的 npm 包

这适用于 `src/` 下的所有源代码。 测试文件 (`src/__tests__/`) 是一个例外，因为它们通过 Vitest 在 Node.js 中运行。

<a id="source-material"></a>

## 源材料

此 TypeScript 客户端基于以下源材料：

<a id="1-openapi-specification"></a>

### 1. OpenAPI 规格

- **来源**：固定的确切SDK版本的`openapi.json`工件
  `package.json` → `config.agentServerImage`
- **用途**：定义 OpenHands Agent Server 的完整 REST API 规范
- **用法**：生成`src/generated/agent-server-schema.ts`，其选定的操作和组件通过稳定别名暴露，并与手写客户端方法进行检查

<a id="2-python-sdk-reference-implementation"></a>

### 2. Python SDK 参考实现

- **来源**：`openhands-sdk/`在此存储库中
- **关键组件**：
  - `RemoteConversation`类-主会话管理
  - `RemoteWorkspace` 类 - 工作区文件操作
  - `RemoteState` 类 - 智能体状态和配置管理
- **目的**：提供架构方面的蓝图和API设计模式
- **用法**：确保跨语言实现的类名、方法签名和行为一致

<a id="3-agent-server-implementation"></a>

### 3. Agent Server 实施

- **来源**：`openhands-agent-server/`在此存储库中
- **目的**：该客户端与之通信的实际服务器实现
- **用法**：了解预期请求/响应格式和WebSocket事件结构的参考

<a id="architecture-alignment"></a>

## 架构对齐

TypeScript客户端保持架构方面的与PythonSDK的一致性：

```typescript
// TypeScript 客户端（本仓库）
const conversation = new RemoteConversation(config);
await conversation.start();
await conversation.workspace.write_file('/path/file.txt', 'content');
const state = conversation.state;
```

```python
# PythonSDK（参考实现）
conversation = RemoteConversation(config)
await conversation.start()
await conversation.workspace.write_file('/path/file.txt', 'content')
state = conversation.state
```

<a id="workspace-architecture"></a>

### 工作区架构

工作区模块遵循 Python SDK 的架构，具有通用接口和多种实现：

```
src/workspace/
├── base.ts           # 定义合约的 IWorkspace 接口
├── remote-workspace.ts  # RemoteWorkspace - 连接到远程 Agent Server
├── local-workspace.ts   # LocalWorkspace - 存根（抛出错误，定向到 RemoteWorkspace）
└── workspace.ts      # 工厂函数和工作区类（向后兼容）
```

**IWorkspace 接口**：定义所有工作区实现的通用契约：

- `executeCommand()` - 执行 bash 命令
- `fileUpload()` / `fileDownload()` - 文件操作
- `gitChanges()` / `gitDiff()` - Git 操作
- `close()` - 清理资源

**RemoteWorkspace**：完全实现的类，通过 HTTP API 连接到远程 OpenHands Agent Server。

**LocalWorkspace**：存根实现，抛出描述性错误，将用户引导至 RemoteWorkspace。

**工厂功能**：

- `createWorkspace({ type, options })` - 显式类型选择
- `createWorkspaceAuto(options)` - 根据 `host` 选项的存在自动检测

**Ergonomic API note**保持 `Workspace`/`RemoteWorkspace` 作为主要的用户界面入口远程执行。 bash底层端点访问应挂起 `workspace.bash`, while direct 端点-特定的客户端应归入次要部分 `@openhands/typescript-client/clients`  入口而不是根节点 SDK 表面。

<a id="llm-architecture"></a>

### LLM 架构

LLM模块提供了与大型语言模型交互的统一接口：

```
src/llm/
├── base.ts           # ILLM 接口和消息类型
├── openrouter-llm.ts # OpenRouterLLM - 使用@openrouter/sdk实现
├── llm.ts            # 工厂函数和 LLM 类
└── index.ts          # 模块出口
```

**ILLM接口**：定义所有LLM实现的通用契约：

- `chatCompletion()` - 发送聊天完成请求
- `chatCompletionStream()` - 流式传输聊天完成响应
- `generate()` - 单轮生成的简单助手
- `close()` - 清理资源

**OpenRouterLLM**：使用官方`@openrouter/sdk`包实现，提供对300多个模型的访问。

**使用示例**：

```typescript
import { createOpenRouterLLM } from '@openhands/typescript-client';

const llm = createOpenRouterLLM({
  apiKey: 'your-openrouter-api-key',
  defaultModel: 'anthropic/claude-3.5-sonnet',
});

// 简单生成
const response = await llm.generate('Hello, how are you?');

// 完整聊天完成
const completion = await llm.chatCompletion({
  messages: [{ role: 'user', content: 'Explain quantum computing' }],
  temperature: 0.7,
  maxTokens: 1000,
});

// 流式传输
for await (const chunk of llm.chatCompletionStream({ messages })) {
  process.stdout.write(chunk.choices[0]?.delta?.content || '');
}
```

<a id="conversation-architecture"></a>

### 对话架构

对话模块遵循与工作区相同的模式：

```
src/conversation/
├── base.ts               # 定义合约的 IConversation 接口
├── remote-conversation.ts   # RemoteConversation - 连接到远程 Agent Server
├── local-conversation.ts    # LocalConversation - 本地智能体执行 LLM
├── conversation.ts       # 工厂函数和Conversation类（向后兼容）
├── remote-state.ts       # 远程会话的状态管理
└── conversation-manager.ts  # 多个对话的管理器
```

**IConversation Interface**：定义所有对话实现的通用契约：

- `start()` - 初始化或恢复对话
- `sendMessage()` - 向智能体发送消息
- `run()` / `pause()` - 控制智能体执行
- `generateTitle()` - 使用 LLM 生成标题
- `close()` - 清理资源

**RemoteConversation**：完全实现的类，通过 HTTP/WebSocket 连接到远程 OpenHands Agent Server。

**LocalConversation**：用于本地智能体执行的完全实现的类：

- 与 ILLM 接口集成以进行 LLM 通信
- 通过工具调用支持实现智能体循环
- 内置工具：`execute_command`、`read_file`、`write_file`、`finish`
- 维护多轮对话的消息历史记录
- 支持暂停/恢复功能
- 支持回调的事件发射

**本地对话示例**：

```typescript
import { LocalWorkspace, LocalConversation, OpenRouterLLM } from '@openhands/typescript-client';

// 创建组件
const workspace = new LocalWorkspace({ workingDir: '/path/to/project' });
const llm = new OpenRouterLLM({
  apiKey: 'your-key',
  defaultModel: 'anthropic/claude-3.5-sonnet',
});

// 创建并运行对话
const conversation = new LocalConversation({ kind: 'local-agent' }, workspace, {
  llm,
  maxIterations: 50,
});

await conversation.start({ initialMessage: 'List all TypeScript files' });
await conversation.run();
await conversation.close();
```

**工厂功能**：

**人体工学 API提示 **: 将 `ConversationManager`设为主服务器范围内的入口。 服务器端/LLM/设置/技能/工具/VSCode的操作应该通过管理器命名空间，例如`manager.server`、`manager.llm`和`manager.vscode`访问。 ACP 特定操作应通过 `manager.acp` 访问。

- `createConversation({ type, agent, workspace, options })` - 显式类型选择
- `createConversationAuto(agent, workspace, options)` - 根据工作区类型自动检测

<a id="hooks-architecture"></a>

### 挂钩架构

hooks 模块为智能体-server 的钩子系统提供类型安全的接口。 钩子是事件驱动的脚本，会在智能体执行期间在特定的生命周期事件中执行，从而提供对智能体行为的可预测控制。

```
src/hooks/
├── types.ts          # 枚举（HookEventType、HookType、HookDecision）和接口（HookEvent、HookResult）
├── config.ts         # HookConfig接口和纯函数（匹配、归一化、合并）
└── index.ts          # 模块出口
```

**关键设计决策：**

- **浏览器兼容**：无文件 I/O 或子进程执行 — 钩子在服务器端执行
- **纯函数**：配置解析、匹配、合并都是对纯数据进行操作的纯函数
- **类型安全**：与 Python SDK 的 Pydantic 型号匹配的完整 TypeScript 接口
- **服务器端执行**：Hook命令在智能体-服务器上运行； 客户端仅发送配置并通过WebSocket接收`HookExecutionEvent`

**集成点：**

- `CreateConversationRequest.hook_config` - 创建对话时发送挂钩
- `RemoteConversation.loadHooks()` - 从服务器的 `.openhands/hooks.json` 加载钩子
- `RemoteConversation.getHookConfig()` - 从当前对话信息中获取钩子
- `HookExecutionEvent` - 当钩子在服务器端执行时通过 WebSocket 接收

**事件类型：** `HookExecutionEvent` 由服务器在每次钩子执行时发出，提供钩子结果的可观测性（成功、阻塞、stdout、stderr等）。

<a id="development-workflow"></a>

## 开发流程

1. **API变更**：当OpenAPI规范更新时，相应的TypeScript接口和客户端方法也应更新
2. **功能奇偶性**：添加到 Python SDK 的新功能应在此 TypeScript 客户端中实现
3. **测试**：所有功能都应该针对正在运行的OpenHands Agent Server实例进行测试
4. **文档**：API更改应反映在README.md和示例代码中

<a id="release-process"></a>

## 发布流程

TypeScript 客户端由单体仓库的发布流程使用 Python 包进行版本控制。 `.github/workflows/prepare-release.yml` 更新
`clients/typescript/package.json` 及其共享 `rel-X.Y.Z` 发布分支上的锁定文件。 合并该版本 PR 会发布 `vX.Y.Z` GitHub 版本。

发布 GitHub 发布触发器
`.github/workflows/typescript-client-npm-publish.yml` 和
`.github/workflows/typescript-client-github-packages-publish.yml`; 两个工作流程还接受 `workflow_dispatch` 版本进行手动恢复。 跟踪的 Agent Server 镜像版本保持独立，可能落后于客户端包版本。

<a id="tracking-the-agent-server--sdk-version"></a>

### 追踪智能体-服务器 / SDK 版本

该客户端是针对特定`software-agent-sdk`版本测试和文档的，该版本以智能体-server图像标签表示（`ghcr.io/openhands/agent-server:<version>-python`，其中`<version>`等于SDK版本`vX.Y.Z`）。 **真相来源**是`package.json` →
`config.agentServerImage`; README 和生成的模式应反映该引脚。

SDK 版本发布后，根 `.github/workflows/version-bump-prs.yml` 工作流程在此存储库中打开 `bump-typescript-agent-server-X.Y.Z` PR。 它更新固定图像和镜像，从发布的 `openapi.json` 重新生成传输层合约，并包含 API 更改摘要。 客户端 CI 和集成工作流程根据新映像验证 PR。 这与 npm 包版本无关——更改被跟踪的服务器**不会**削减客户端版本。

生成的传输层合约在
`src/generated/agent-server-schema.ts` 来自同一个引脚。 运行
`npm run generate:agent-server-api` 更改引脚后
`npm run check:agent-server-api` 强制执行清洁再生。 已发布的 SDK 版本使用 `openapi.json` 发布工件。 没有工件的旧版本将从精确固定图像的隔离临时容器中导出。 更改生成或漂移自动化时运行 `npm run test:agent-server-api-tooling`。 预定的 `agent-server-sdk-main-audit` 记录准确的 SDK 提交测试并报告即将发生的漂移信息； 普通的PRCI永远不会从那个移动目标中读取数据。 生成器从不读取未固定的
`latest` 端点。

<a id="local-setup-and-validation"></a>

## 本地设置和验证

从 `clients/typescript/` 运行客户端命令。 使用 `.github/workflows/typescript-client-ci.yml` 使用的相同命令安装依赖项：

```bash
npm ci
```

在提交之前，运行客户端 CI 检查：

```bash
npm run lint
npm run build
npm run test:coverage
npm run format:check
```

对于 Docker 支持的服务器覆盖范围，运行确定性集成子集
`.github/workflows/typescript-client-integration-tests.yml` 第一：

```bash
npm run test:integration:deterministic
```

LLM 支持集成测试额外需要 `LLM_API_KEY`，可选
`LLM_MODEL` 和 `LLM_BASE_URL` 覆盖。

<a id="testing"></a>

## 测试

<a id="unit-tests"></a>

### 单元测试

单元测试位于 `src/__tests__/` 中，无需外部服务即可测试基本功能：

```bash
npm test                  # 运行单元测试
npm run test:coverage     # 运行覆盖率报告
```

<a id="integration-tests"></a>

### 集成测试

集成测试在 `src/__tests__/integration/` 中，并且需要 Docker 中正在运行的智能体服务器：

```bash
# 设置环境
export LLM_API_KEY="your-api-key"
export LLM_MODEL="anthropic/claude-sonnet-4-5-20250929"

# 在 Docker 中启动智能体-服务器（与 package.json -> config.agentServerImage 中的固定图像匹配）
IMAGE=$(node -p "require('./package.json').config.agentServerImage")
docker run -d --name agent-server -p 127.0.0.1:8010:8000 \
  -v /tmp/agent-workspace:/workspace \
  "$IMAGE" --host 0.0.0.0

# 运行集成测试
npm run test:integration
```

集成测试封面：

- **workspace.integration.test.ts**：命令执行，文件上传/下载
- **conversation.integration.test.ts**：对话生命周期、消息传递、智能体执行
- **websocket.integration.test.ts**：实时事件流式传输
- **http-client.integration.test.ts**：HTTP客户端功能
- **e2e.integration.test.ts**：端到端智能体工作流程

### CI/CD

根 GitHub 操作工作流程
`.github/workflows/typescript-client-integration-tests.yml` 自动：

1. 启动一个已安装工作区的智能体服务器容器
2. 针对真实服务器运行所有集成测试
3. 报告结果并记录失败

必需的 GitHub 机密：

- `LLM_API_KEY`：LLM 提供商的 API 密钥
- `LLM_MODEL`（可选）：覆盖默认模型

<a id="ci-image-version"></a>

### CI 图片版本

- 智能体端点的TypeScript客户端的`package.json` → `config.agentServerImage`（而不是硬编码标签），这是生成模式和集成工作流所使用的事实上的来源。
- 保持 TypeScript 客户端测试严格针对已发布的服务器映像，而不是为较旧的预发布版本添加兼容性回退方案。

<a id="agent-behavior-guidelines"></a>

## 智能体行为准则

**重要**：智能体应该绝不启动服务器或浏览以查看应用程序，除非用户明确要求。 这包括：

- 运行开发服务器（e.g.、`npm run dev`、`npm start`）
- 打开浏览器或导航到应用 URLs
- 自动启动任何网络服务器或应用程序
- 在浏览器中查看正在运行的应用程序

智能体应侧重于代码开发、测试和文档任务。 仅当用户明确请求运行或查看应用程序时，智能体才应启动服务器或打开浏览器。

<a id="related-repositories"></a>

## 相关存储库

- **[OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)**：Agent Canvas应用
- **[OpenHands/docs](https://github.com/OpenHands/docs)**：用户文档

<a id="usage-context"></a>

## 用途上下文

该客户端适用于希望实现以下目标的开发人员：

- 构建与 OpenHands 智能体交互的 Web 应用程序
- 创建管理智能体个对话的 Node.js 个服务
- 将 OpenHands 功能集成到现有 TypeScript/JavaScript 应用程序中
- 为 OpenHands Agent Server 开发自定义前端

客户端抽象了 HTTP 请求、WebSocket 管理和 API 身份验证的复杂性，提供了一个干净、类型安全的接口来访问所有 OpenHands Agent Server 功能。

<a id="example-application"></a>

## 应用示例

`example/` 目录包含一个使用 Vite 构建的 React 应用程序，演示如何将 TypeScript SDK 集成到现代 Web 应用程序中。 此示例既作为参考实现又作为验证工具，以确保 SDK 在浏览器环境中正常工作。

该示例应用程序展示了：

- 与 ES 模块兼容性的正确 SDK 集成
- TypeScript客户端开发配置
- 构建在运行应用程序之前编译 SDK 的进程
- 所有主要 SDK 类和枚举的进口验证
- 使用 Vite 工具的现代 React 开发模式

这为开发人员提供了一个工作模板，用于使用 OpenHands Agent Server TypeScript 客户端构建自己的应用程序。
