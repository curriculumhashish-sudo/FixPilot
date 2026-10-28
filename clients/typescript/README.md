<a id="openhands-agent-server-typescript-client"></a>

# OpenHands Agent Server TypeScript 客户端

> ⚠️ **ALPHA SOFTWARE 警告** ⚠️
>
> 此 TypeScript SDK 当前处于 **alpha** 状态，并且 ** 不稳定 **。 API 可能会在版本之间发生重大变化，恕不另行通知。 该软件仅用于早期测试和开发目的。
>
> - 不兼容变更可能出现在任何版本中
> - 功能可能不完整或包含错误
> - 文档可能已过时或不完整
> - 不推荐用于生产用途
>
> 请谨慎使用并期待频繁更新。

OpenHands Agent Server API 的 TypeScript 客户端库。 镜像 Python [OpenHands 软件智能体 SDK](https://github.com/OpenHands/software-agent-sdk) 的结构和功能，但仅支持远程对话。

<a id="-browser-compatible"></a>

## ✨ 浏览器兼容

该客户端**完全与浏览器兼容**，并且无需Node.js依赖即可工作。 文件操作使用浏览器原生的APIs，如`Blob`、`File`和`FormData`，而不是文件系统操作。 非常适合 Web 应用程序、React 应用程序和其他基于浏览器的项目。

<a id="installation"></a>

## 安装

该软件包已发布到 npm 和 OpenHands 软件智能体 SDK 存储库的 `clients/typescript` 目录中的 GitHub 软件包。

<a id="option-1-configure-npmrc"></a>

### 选项 1：配置 .npmrc

将其添加到您的 `.npmrc` 文件中：

```
@openhands:registry=https://npm.pkg.github.com
```

然后正常安装：

```bash
npm install @openhands/typescript-client
```

<a id="option-2-direct-install-with-registry-flag"></a>

### 选项 2：使用注册表标志直接安装

```bash
npm install @openhands/typescript-client --registry=https://npm.pkg.github.com
```

<a id="agent-server-api-contract"></a>

## Agent ServerAPI合同

选定的手写客户端将根据生成的类型进行静态检查
`src/generated/agent-server-schema.ts`. 源是由 `package.json` → `config.agentServerImage` 配置的确切 Agent Server 版本。

```bash
npm run generate:agent-server-api
npm run check:agent-server-api
npm run test:agent-server-api-tooling
```

生成器下载匹配的 SDK 版本的 `openapi.json`。 对于那些预日期较早的旧版本，它会在一个临时 Docker 容器中启动精确的锁定镜像，没有主机挂载，导出 `/openapi.json`，并移除容器。 CI 重新生成文件，如果不同则失败。 在SDK开发期间，`AGENT_SERVER_OPENAPI_PATH=/path/to/openapi.json`可以提供本地候选合约，同时在生成的文件中保留固定图像元数据。

固定 PR CI 是可重复的并且是必需的。 单独的每周
`agent-server-sdk-main-audit` 工作流程从一个确切的 SDK 导出合同
`main` 提交，记录 SHA，并打开或更新信息漂移问题。 普通客户端 PR 永远不会从移动 SDK 分支生成。


<a id="repository-boundaries"></a>

## 存储库边界

此存储库中的 `clients/typescript` 包拥有 OpenHands Agent Server API 的浏览器兼容类型客户端。 此存储库中的 Python 包和 Agent Server 拥有规范的 API 实现和智能体行为； [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 使用此客户端来获取 Agent Canvas UI； [`OpenHands/extensions`](https://github.com/OpenHands/extensions) 拥有可重用的技能、插件、自动化和集成； [`OpenHands/automation`](https://github.com/OpenHands/automation) 拥有调度、Webhook、运行历史记录和调度。

正常流程是SDK/Agent Server→OpenAPI合约→该客户端→Agent Canvas。 在 `clients/typescript` 下添加类型化端点访问，在 Python SDK 或 Agent Server 包中添加后端行为，在 Canvas 中添加 UI，以及在 `automation` 中添加自动化生命周期行为。

<a id="quick-start"></a>

## 快速入门

<a id="start-an-agentserver"></a>

### 开始 AgentServer

您需要在某个地方运行一个 AgentServer 供客户端连接。 您可以在Docker中运行一个：

```bash
docker run -p 127.0.0.1:8000:8000 -p 127.0.0.1:8001:8001 \
  -e SESSION_API_KEY="$SESSION_API_KEY" \
  -e OH_ALLOW_CORS_ORIGINS='["*"]' \
  ghcr.io/openhands/agent-server:71b070d-python
```

<a id="creating-a-conversation"></a>

### 创建对话

```typescript
import { Conversation, Agent, Workspace } from '@openhands/typescript-client';

const agent = new Agent({
  llm: {
    model: 'gpt-4',
    api_key: 'your-openai-api-key',
  },
});

// 创建远程工作区
const workspace = new Workspace({
  host: 'http://localhost:3000',
  workingDir: '/tmp',
  apiKey: 'your-session-api-key',
});

const conversation = new Conversation(agent, workspace, {
  callback: (event) => {
    console.log('Received event:', event);
  },
});

// 用初始消息开始对话
await conversation.start({
  initialMessage: 'Hello, can you help me write some code?',
});

// 开始 WebSocket 获取实时事件
await conversation.startWebSocketClient();

// 发送消息并运行智能体
await conversation.sendMessage('Create a simple Python script that prints "Hello World"');
await conversation.run();
```

<a id="loading-an-existing-conversation"></a>

### 加载现有对话

```typescript
// 为现有对话创建远程工作区
const workspace = new Workspace({
  host: 'http://localhost:3000',
  workingDir: '/tmp',
  apiKey: 'your-session-api-key',
});

const conversation = new Conversation(agent, workspace, {
  conversationId: 'conversation-id-here',
});

// 连接到现有对话
await conversation.start();
```

<a id="using-the-workspace"></a>

### 使用工作区

```typescript
// 执行命令
const result = await conversation.workspace.executeCommand('ls -la');
console.log('Command output:', result.stdout);
console.log('Exit code:', result.exit_code);

// 从工作区访问较低级别的 bash APIs
const bashCommand = await conversation.workspace.bash.startCommand('ls -la');
const bashEvents = await conversation.workspace.bash.searchEvents({
  command_id__eq: bashCommand.id,
  limit: 20,
});

// 上传文件
const uploadResult = await conversation.workspace.fileUpload(
  './local-file.txt',
  '/remote/path/file.txt'
);

// 下载文件
const downloadResult = await conversation.workspace.fileDownload(
  '/remote/path/file.txt',
  './downloaded-file.txt'
);
```

<a id="server-wide-operations"></a>

### 服务器范围的操作

```typescript
import { ConversationManager } from '@openhands/typescript-client';

const manager = new ConversationManager({
  host: 'http://localhost:3000',
  apiKey: 'your-session-api-key',
});

const serverInfo = await manager.server.getServerInfo();
const providers = await manager.llm.getProviders();
const tools = await manager.tools.listTools();
const acpCount = await manager.acp.countConversations();
```

<a id="updating-mcp-settings"></a>

### 正在更新 MCP 设置

已持久化 MCP 服务器使用其设置映射密钥作为稳定身份。 创建、更新或删除一台服务器，无需获取并重新发送整个目录：

```typescript
const settings = manager.settings;

await settings.createMcpServer('github', {
  transport: 'http',
  url: 'https://example.test/mcp',
});

await settings.patchMcpServer('github', {
  url: 'https://example.test/mcp/v2',
});

await settings.deleteMcpServer('old-server');
```

省略的补丁字段保留其存储值，包括凭据。 提供一个值来替换它，并且 `null` 显式清除支持的可选字段或删除映射条目。 每个助手都会向相应的 Agent Server MCP 设置操作发送一个请求。

如果您直接需要较低级别的端点特定客户端，请从辅助入口导入它们：

```typescript
import { ServerClient, BashClient } from '@openhands/typescript-client/clients';
```

<a id="aggregate-agent-server-and-cloud-clients"></a>

### 聚合 Agent Server 和云客户端

`/clients` 入口还公开聚合客户端。 `AgentServerClient` 将每智能体服务器端点客户端命名空间包裹起来，`CloudClient` 覆盖 OpenHands 云应用 API（基于 Bearer 认证、组织范围和可选的运行时沙箱调用代理）：

```typescript
import { AgentServerClient, CloudClient } from '@openhands/typescript-client/clients';

const agentServer = new AgentServerClient({
  host: 'http://localhost:3000',
  apiKey: 'your-session-api-key',
});
const health = await agentServer.server.getHealth();
const conversations = await agentServer.conversations.searchConversations();

const cloud = new CloudClient({
  host: 'https://app.all-hands.dev',
  apiKey: 'your-cloud-api-key',
  orgId: 'optional-org-id', // 每个请求都作为 X-Org-Id 发送
  // 可选：带有 `hostOverride` 的请求（运行时沙箱调用）是
  // 通过此智能体-服务器的/api/cloud-proxy端点路由，而不是直接发送到主机。
  //
  proxy: { host: 'http://localhost:3000', apiKey: 'your-session-api-key' },
});
const orgs = await cloud.getOrganizations();
const created = await cloud.createConversation({ initial_message: 'Fix the bug' });
```

要以交互方式获取 Cloud API 密钥，请使用设备流帮助程序：

```typescript
import { startDeviceFlow, pollForToken } from '@openhands/typescript-client/clients';

const requestMetadata = {
  headers: { 'X-My-Client': 'my-client-name' },
};
const auth = await startDeviceFlow('https://app.all-hands.dev', requestMetadata);
console.log(`Approve this device at ${auth.verification_uri_complete}`);
const token = await pollForToken('https://app.all-hands.dev', auth.device_code, {
  interval: auth.interval,
  ...requestMetadata,
});
const cloud = new CloudClient({
  host: 'https://app.all-hands.dev',
  apiKey: token.access_token,
});
```

<a id="working-with-events"></a>

### 处理事件

```typescript
// 访问事件列表
const events = await conversation.state.events.getEvents();
console.log(`Total events: ${events.length}`);

// 迭代事件
for await (const event of conversation.state.events) {
  console.log(`Event: ${event.kind} at ${event.timestamp}`);
}
```

<a id="managing-conversation-state"></a>

### 管理对话状态

```typescript
// 获取对话状态
const status = await conversation.state.getAgentStatus();
console.log('Agent status:', status);

// 获取对话统计信息
const stats = await conversation.conversationStats();
console.log('Total events:', stats.total_events);

// 设置确认政策
await conversation.setConfirmationPolicy({ type: 'always' });

// 更新机密
await conversation.updateSecrets({
  API_KEY: 'secret-value',
  DATABASE_URL: () => process.env.DATABASE_URL || 'default-url',
});
```

<a id="api-reference"></a>

## API 参考资料

<a id="conversation"></a>

### 对话

创建与 OpenHands 智能体的对话的工厂函数。

<a id="constructor"></a>

#### 构造函数

- `new Conversation(agent, workspace, options?)` - 创建一个新的对话实例

<a id="instance-methods"></a>

#### 实例方法

- `start(options?)` - 开始对话（创建新对话或连接到现有对话）

- `sendMessage(message)` - 向智能体发送消息
- `run()` - 开始智能体执行
- `pause()` - 暂停智能体执行
- `setConfirmationPolicy(policy)` - 设置确认策略
- `sendConfirmationResponse(accept, reason?)` - 响应确认请求
- `updateSecrets(secrets)` - 更新对话机密
- `startWebSocketClient()` - 开始实时事件流式传输
- `stopWebSocketClient()` - 停止实时事件流式传输
- `conversationStats()` - 获取会话统计信息
- `close()` - 清理资源

<a id="properties"></a>

#### 属性

- `id` - 对话 ID
- `state` - RemoteState 用于访问对话状态的实例
- `workspace` - RemoteWorkspace 用于命令执行和文件操作的实例

### RemoteWorkspace

处理远程命令执行和文件操作。

<a id="methods"></a>

#### 方法

- `executeCommand(command, cwd?, timeout?)` - 执行 bash 命令
- `fileUpload(sourcePath, destinationPath)` - 上传文件
- `fileDownload(sourcePath, destinationPath)` - 下载文件
- `gitChanges(path)` - 获取路径的 git 更改
- `gitDiff(path)` - 获取路径的 git diff
- `close()` - 清理资源

### RemoteState

管理对话状态并提供对事件的访问。

<a id="properties-1"></a>

#### 属性

- `id` - 对话 ID
- `events` - RemoteEventsList 实例

<a id="methods-1"></a>

#### 方法

- `getAgentStatus()` - 获取当前智能体执行状态
- `getConfirmationPolicy()` - 获取当前确认政策
- `getActivatedKnowledgeSkills()` - 获取激活的知识技能
- `getAgent()` - 获取智能体配置
- `getWorkspace()` - 获取工作区配置
- `getPersistenceDir()` - 获取持久化目录
- `modelDump()` - 获取状态作为普通对象
- `modelDumpJson()` - 获取状态为 JSON 字符串

### RemoteEventsList

通过缓存和同步管理对话事件。

<a id="methods-2"></a>

#### 方法

- `addEvent(event)` - 将事件添加到缓存
- `length()` - 获取缓存事件的数量
- `getEvent(index)` - 按索引获取事件
- `getEvents(start?, end?)` - 获取事件切片
- `createDefaultCallback()` - 创建默认事件回调

### WebSocketCallbackClient

通过 WebSocket 处理实时事件流式传输。 它和 `BashWebSocketClient` 使用运行时的全局 `WebSocket`（浏览器，Node 22+），在套接字打开时查找； 在较旧的节点上，分配一个构造函数，例如 `ws` 包
`globalThis.WebSocket` 第一。

<a id="methods-3"></a>

#### 方法

- `start()` - 开始 WebSocket 连接
- `stop()` - 停止 WebSocket 连接

<a id="types"></a>

## 类型

该库包含全面的 TypeScript 类型定义：

- `ConversationID` - 会话标识符类型
- `Event` - 基础事件接口
- `Message` - 消息界面及内容
- `AgentBase`-智能体配置界面
- `CommandResult` - 命令执行结果
- `FileOperationResult` - 文件操作结果
- `ConversationStats` - 会话统计
- `AgentExecutionStatus` - 智能体状态枚举
- 还有更多...

<a id="error-handling"></a>

## 错误处理

当服务器返回错误状态时，客户端会抛出 `HttpError`：

```typescript
import { isHttpError } from '@openhands/typescript-client';

try {
  await conversation.sendMessage('Hello');
} catch (error) {
  if (isHttpError(error)) {
    console.error(`HTTP Error ${error.status}: ${error.statusText}`);
    // 服务器自己的消息，e.g。 “未找到配置文件‘丢失’”。
    console.error('Detail:', error.detail ?? 'none');
    console.error('Response:', error.response);
  } else {
    console.error('Unexpected error:', error);
  }
}
```

- `status`、`statusText`：HTTP状态。
- `response`：错误正文：服务器发送JSON时解析JSON，否则为文本，或
  `null` 当无法读取正文时。
- `message`：传输层日志文本，`HTTP request failed (<status> <text>): <body>`。
- `detail`：服务器可读的消息，或者当正文有None时为`undefined`：
  - `{"detail": "..."}` 给出字符串。
  - 验证错误主体（`{"detail": [{"loc", "msg", "type"}, ...]}`，通常是 422）给出单个条目的 `msg`。 多个条目用 `"; "` 连接，每个条目都以其字段名称（`loc` 中的最后一个字符串）、e.g 为前缀。
    `name: Field required; model: Field required`.
  - `{"detail": {"message": "...", ...}}` 给出 `message`。
  - 任何其他主体，例如代理的 HTML 错误页面，都会给出 `undefined`。
- `validationErrors`：验证错误主体的 `{ loc, msg, type }` 条目，或者
  `undefined`. 使用它将每条消息指向其表单字段。

`isHttpError(error)` 还识别此包的另一个副本抛出的 `HttpError` （例如，当应用程序和库各自捆绑自己时），其中
`error instanceof HttpError` 就是 False，只要该副本是包含 `isHttpError` 的版本（较旧的副本不会标记其错误）。 `instanceof` 在一份副本中仍然有效。

<a id="development"></a>

## 发展

<a id="building"></a>

### 建筑

```bash
npm run build
```

<a id="development-mode"></a>

### 发展模式

```bash
npm run dev
```

<a id="linting"></a>

### 静态检查

```bash
npm run lint
```

<a id="formatting"></a>

### 格式化

```bash
npm run format
```

<a id="testing"></a>

## 测试

<a id="unit-tests"></a>

### 单元测试

运行单元测试（不需要外部依赖项）：

```bash
npm test
```

<a id="integration-tests"></a>

### 集成测试

集成测试需要 Docker 中运行的智能体服务器并已安装工作区。 这些测试根据真实服务器验证完整功能。

<a id="prerequisites"></a>

#### 先决条件

1. Docker已安装并正在运行
2. LLM API 键（e.g.、Anthropic 或 OpenAI）

<a id="running-integration-tests-locally"></a>

#### 本地运行集成测试

1. 创建工作区目录：

   ```bash
   mkdir -p /tmp/agent-workspace
   chmod 777 /tmp/agent-workspace
   ```

2. 启动智能体-服务器容器（软件-智能体-SDK v1.44.0）：

   ```bash
   docker run -d \
     --name agent-server \
     -p 127.0.0.1:8010:8000 \
     -v /tmp/agent-workspace:/workspace \
     ghcr.io/openhands/agent-server:1.44.0-python --host 0.0.0.0
   ```

3. 等待服务器准备就绪：

   ```bash
   # 检查服务器健康状况
   curl http://localhost:8010/health
   ```

4. 运行集成测试：

   ```bash
   export LLM_API_KEY="your-api-key"
   export LLM_MODEL="anthropic/claude-sonnet-4-5-20250929"
   npm run test:integration
   ```

5. 清理：
   ```bash
   docker stop agent-server && docker rm agent-server
   ```

<a id="environment-variables"></a>

#### 环境变量

| 变量              | 必填 | 默认                 | 描述                                                   |
| --------------------- | -------- | ----------------------- | ------------------------------------------------------------- |
| `LLM_API_KEY`         | 是的      | -                       | LLM 提供商的 API 密钥                                  |
| `LLM_MODEL`           | 是的      | -                       | LLM 型号名称 (e.g., `anthropic/claude-sonnet-4-5-20250929`) |
| `LLM_BASE_URL`        | 否       | -                       | LLM API 的自定义底座 URL                                   |
| `AGENT_SERVER_URL`    | 否       | `http://localhost:8010` | Agent Server 中的 URL                                       |
| `HOST_WORKSPACE_DIR`  | 否       | `/tmp/agent-workspace`  | 主机上工作区的路径                                     |
| `AGENT_WORKSPACE_DIR` | 否       | `/workspace`            | 容器内工作区的路径                            |
| `TEST_TIMEOUT`        | 否       | `120000`                | 测试超时（以毫秒为单位）                                  |

<a id="integration-test-coverage"></a>

#### 集成测试覆盖范围

集成测试封面：

- **工作区操作**：命令执行、文件上传/下载、往返操作
- **对话生命周期**：创建、消息发送、运行智能体、暂停
- **事件流式传输**：WebSocket 个连接、事件回调、不同事件类型
- **HTTP客户端**：健康检查、GET/POST请求、错误处理
- **端到端任务**：通过智能体创建/修改/删除文件，多步骤任务

#### CI/CD

在以下情况下，集成测试在 GitHub 操作中自动运行：

- 推送到 `main` 或 `develop` 分支
- 向这些分支开放拉取请求
- 手动触发工作流程

该工作流程需要以下机密：

- `LLM_API_KEY`：LLM 提供商的 API 密钥
- `LLM_MODEL`（可选）：覆盖默认模型

<a id="running-all-tests"></a>

### 运行所有测试

```bash
npm run test:all
```

<a id="license"></a>

## 许可证

MIT

<a id="contributing"></a>

## 贡献

贡献欢迎！ 请随时提交 Pull 请求。

<a id="browser-conversation-event-streams"></a>

### 浏览器对话事件流

`@openhands/typescript-client/clients` 中的 `ConversationEventStream` 拥有 Agent Server 事件套接字传输层。 当应用程序已经管理对话状态并且需要原始事件框架和连接生命周期时使用它回调。 它首先进行身份验证，保留重播参数，当启用时，通过指数退避和抖动重连，以及在10秒后终止停滞的手动协商。 它不保留消息历史记录。

```typescript
import {
  ConversationEventStream,
  buildConversationEventStreamUrl,
} from '@openhands/typescript-client/clients';

const stream = new ConversationEventStream({
  url: buildConversationEventStreamUrl(agentServerUrl, conversationId),
  sessionApiKey,
  queryParams: { resend_mode: 'all' },
  reconnect: { enabled: true },
  onMessage: (frame) => handleEvent(JSON.parse(frame.data)),
  onStateChange: (state) => renderConnectionState(state),
});
stream.start();
// 当流打开时：
stream.send(JSON.stringify({ role: 'user', content: [{ type: 'text', text: 'Hello' }], run: true }));
// 当业主被处置时：
stream.stop();
```

`updateOptions`刷新回调和凭据而不重新连接； 新的凭据在下一次握手时生效。 `reconnect()` 替换活动套接字并重置重试预算。 `send()` 在断开连接时抛出异常，允许应用程序将 `ConversationClient.sendEvent` 用作 REST 回退方案。 客户端仅在启动时需要 Web 标准全局 `WebSocket`，并且没有特定于节点的导入。 通过凭据至`sessionApiKey`； 凭据中的套接字 URL 或查询参数被拒绝。
