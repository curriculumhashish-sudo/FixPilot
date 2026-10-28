<a id="typescript-client-openhandstypescript-client"></a>

# TypeScript 客户端（@）openhands/typescript-client)

浏览器和 Node 消费者通道：在 `clients/typescript` 中的 TypeScript 客户端上构建的程序在驱动 Agent Server 时观察到的情况。
`ConversationManager`（或聚合`AgentServerClient`）读取服务器状态并列出、加载、更新和删除对话； `RemoteWorkspace` 运行命令、移动文件并生成工作区 cookie，全局或仅限于一个对话； `RemoteConversation` 创建或重新附加服务器会话、发送消息、运行它并通过以下方式读取其状态和事件
`RemoteState`和`RemoteEventsList`； `ConversationEventStream`,
`WebSocketCallbackClient` 和 `BashWebSocketClient` 事件流。 小型客户端包裹钩子 MCP 测试和工作区注册表在服务器版本上。 和 `HttpError` 拒绝了所有请求。 客户端被固定在已发布的服务器上`package.json`  `config.agentServerImage`, 所以它的自己端点审计在此被重放，以验证此检查点的合同。 每道菜都会运行一个真实的程序（ ）`clients/typescript/dist`) through `control-agent-server exec` 并检查服务器自己的视图通过了 REST  API, the WebSocket 或者之后的磁盘。

资料来源：`clients/typescript/src/`、`clients/typescript/scripts/endpoint-audit.mjs`、`clients/typescript/scripts/generate-agent-server-api.mjs`、`clients/typescript/endpoint-audit.config.json`、`clients/typescript/package.json`

需求：`llm`、`node`、`uvx`、`git`、`tmux`、`network`

路线：None

<a id="sub-features"></a>

## 子功能

- `F34.server-client`：`ServerClient`（通过`ConversationManager.server`和`AgentServerClient.server`）使用服务器自己的值读取`/alive`，`/health`，`/ready`，`/server_info`和`/`，没有密钥的探针； 版本控制的客户端（`HooksClient`、`WorkspacesClient`、`MCPClient`）每传输层读取`/server_info`一次，接受该服务器并返回其数据。
- `F34.http-errors`缺少或错误的密钥会被拒绝 `HttpError` (`status` 401, `detail`  `Unauthorized`被识别为 `isHttpError`404和422都携带服务器的响应 `detail` 和 `validationErrors`，而一个不可达的主机和一个客户端超时拒绝时返回原始错误。
- `F34.workspace-exec`: `RemoteWorkspace.executeCommand` 返回 stdout、stderr 和给定 `cwd` 中运行的命令的退出代码，一旦命令自己的超时杀死它，则退出 `-1`。
- `F34.workspace-files`：`RemoteWorkspace.uploadText`/`fileUpload`和`downloadAsText`以及`FileClient.downloadFile`/`uploadTextFile`，往返文件（字节精确到`FileClient`）； 丢失的文件、相对路径和目录拒绝服务器的 404 和 400。
- `F34.workspace-binary-download`: `RemoteWorkspace.downloadAsBlob` 按字节返回二进制文件。
- `F34.workspace-scoped`：带有 `conversationId` 的 `RemoteWorkspace` 路由通过 `/api/conversations/{id}/bash|file/...`：命令默认为对话的工作区并落在其自己的 bash 历史记录中，其外部的路径和 `cwd` 得到 422，未知对话 404。
- `F34.workspace-git`: `RemoteWorkspace.gitChanges` 和 `gitDiff` 返回服务器的更改和差异，全局和通过 `/api/conversations/{id}/git/...` 对于一个 scoped 工作区，并将 422 (路径超出对话范围) 处理工作区) 或 401 在一个 `Error` whose `cause` is the `HttpError`.
- `F34.workspace-git-types`：状态 `gitChanges` 返回类型检查作为导出的 `GitChange['status']`，就像它们针对客户端生成的合约所做的那样。
- `F34.bash-client`: `RemoteWorkspace.bash` 启动后台命令，查找其输出 `searchEvents`, 逐条读取事件，并按批次（未知 ID 的事件）处理 `null`), 停止一个运行中的命令，将未知的ID视为已停止，以及 `clearEvents` 清空历史。
- `F34.bash-websocket`：Node 中的 `BashWebSocketClient` 将命令的 bash 事件（使用 `resendMode: 'all'` 重播）传递到其回调，没有错误。
- `F34.workspace-session`: `startWorkspaceSession(id)` 回答为工作区 base URL 该端点服务会话的文件 `deleteWorkspaceSession()` 成功后，未匹配的命名空间ID将被拒绝，而没有提供密钥则返回401。
- `F34.conversation-create`: `RemoteConversation.start()` 创建与客户端的智能体（LLM、工具）、工作目录和 `max_iterations` 的服务器会话，并将其工作区重新绑定到新会话。
- `F34.conversation-run`重新连接 `RemoteConversation` 存储了 `sendMessage` 无需运行 `run()` 驱动一个真实模型 `finished`, the `hookConfig` 在创建时运行，但在运行工具调用并被报告为 `getHookConfig()`客户端读取了智能体文件、统计信息、最终响应和轨迹 ZIP, and `RemoteState` 报告服务器状态智能体，工作区，policy and 持久化 directory.
- `F34.events-list`: `RemoteEventsList` 计数、搜索（源、完全限定类型、正文、页面）、按 id 获取事件并迭代服务器存储的相同事件。
- `F34.events-unknown-id`：`RemoteEventsList.getEventById` 拒绝未知事件 ID，返回 404 `HttpError`，`getEventsById` 将 `null` 放入其槽中。
- `F34.events-search-kind`：`RemoteEventsList.search({kind: 'MessageEvent'})`和`count({kind: 'MessageEvent'})`，其自己的文档显示的简短类型（`ActionEvent, MessageEvent`），找到与完全限定类型相同的事件。
- Node 全局 `WebSocket` 上的 `F34.event-stream`: `ConversationEventStream` 使用第一帧进行身份验证，使用 `resend_mode: 'all'` 重放存储的事件，发送一条在同一套接字上运行智能体到 `finished` 的用户消息，并报告错误密钥作为 4001 关闭。
- Node 中的 `F34.ws-callback-client`: `RemoteConversation.startWebSocketClient()` 将会话的事件传递到会话回调，没有错误。
- `F34.conversation-controls`：`setTitle`和`setConfirmationPolicy`更改服务器的标题和策略。
- `F34.conversation-confirm`: 在 `AlwaysConfirm` 中，`sendConfirmationResponse(false, reason)` 会记录一个 `UserRejectObservation` 以该原因，并且不执行命令，`sendConfirmationResponse(true)` 执行待命的命令，`updateSecrets` (一个字符串和一个函数值) 将这两个值放入该命令的 shell 中，但没有事件包含它们。
- `F34.conversation-branching`：`fork({title})`返回绑定到fork的`RemoteConversation`（其id，fork的工作区和智能体，复制的事件），`navigateTo`将缓存状态刷新为新的`leaf_event_id`，`askAgent`回答而不将事件添加到源。
- `F34.manager`: `ConversationManager` 带有分页搜索，按状态计数，批量获取（未知ID） `null`, 列出所有，加载与服务器的对话工作目录创建和删除一个，以及一个未知的ID会返回404。
- `F34.manager-update-result`: `ConversationManager.updateConversation` 存储新标题并使用输入返回的更新后的 `ConversationInfo` 进行解析。
- `F34.manager-create-options`：`ConversationManager.createConversation(agent, {maxIterations, stuckDetection})` 使用这些设置创建对话。
- `F34.manager-acp`: `ConversationManager.acp` 为内联 ACP 智能体（及其 `maxIterations`）创建一个对话，并使用其 ACP 智能体字段获取、批量获取、列表和计数。
- `F34.hooks-client`：`HooksClient.loadHooks` 和 `RemoteConversation.loadHooks` 将项目的 `.openhands/hooks.json` 读取为 snake_case `HookConfig` 客户端的钩子助手理解，`null` 读取没有钩子的目录。
- `F34.mcp-client`: `MCPClient.testServer` 列出了 stdio MCP 服务器的工具，并运行了一个工具调用，报告一个无法启动的服务器 `{ok: false}`，并用 `error_kind` 的命令报告一个空命令拒绝。
- `F34.restart-reload`：服务器重新启动后，新的 `ConversationManager` 加载相同的对话及其状态、标题、事件、挂钩配置和工作区文件。
- `F34.event-stream-reconnect`: a `ConversationEventStream` 与 `reconnect: {enabled: true}` 和 `queryParams: {resend_mode: 'all'}`, on the `ws` 该包的构造函数在服务器重启后会自动重连，再次以相同的查询重播历史，并发送重启后发布的消息。
- `F34.event-stream-reconnect-native`：节点全局 `WebSocket` 上的同一流也会在服务器重新启动后重新连接。
- `F34.endpoint-audit`客户端的端点检查的公共审计 OpenAPI 合同找不到客户端调用，服务器缺少，从该合同生成客户端类型也不会删除导出类型。
- `F34.version-gate-old`：针对真正的 1.22.0 智能体服务器版本，门控方法拒绝 `AgentServerVersionError`（必需版本和实际版本），并且从不调用门控路由。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- 包：`@openhands/typescript-client`（仅ESM），主条目
  `dist/index.js` (`ConversationManager`, `RemoteConversation`/`Conversation`,
  `RemoteWorkspace`/`Workspace`, `RemoteState`, `RemoteEventsList`, `Agent`,
  `HttpClient`, `HttpError`, `isHttpError`, `WebSocketCallbackClient`,
  `BashWebSocketClient`, `HooksClient`, `MCPClient`, `WorkspacesClient`,
  `assertAgentServerSupports`，钩子助手）和辅助条目
  `dist/clients.js` (`ServerClient`, `FileClient`, `ConversationEventStream`,
  `buildConversationEventStreamUrl`、`AgentServerClient` 和每个端点客户端）。 食谱按路径从存储库根导入构建的文件。
- 服务器状态：`ServerClient.getAlive|getHealth|getReady|getServerInfo|getRoot`（`GET /alive`、`/health`、`/ready`、`/server_info`、`/`）。
- 对话：`RemoteConversation.start()`（`POST /api/conversations`，或
  `GET /api/conversations/{id}` 当用 `conversationId` 构造时），
  `sendMessage`（`POST .../events` 和 `run: false`）、`run`、`pause`、
  `setTitle` (`PATCH`), `setConfirmationPolicy`, `sendConfirmationResponse` (`POST .../events/respond_to_confirmation`), `updateSecrets` (`POST
  .../secrets`, every value wrapped as a `StaticSecret`, a function value
  首先调用），`fork`（`POST .../fork`，返回绑定到fork的新`RemoteConversation`），`navigateTo`（`POST .../navigate`，然后刷新缓存状态），`askAgent`（`POST .../ask_agent`），`conversationStats`，
  `getAgentFinalResponse`, `downloadTrajectory`, `getHookConfig`, `loadHooks` (`POST /api/hooks`), `startWebSocketClient`; `ConversationManager`
  `searchConversations`, `countConversations`, `getConversations` (`GET /api/conversations?ids=`), `getAllConversations`, `getConversation`,
  `loadConversation`, `createConversation`, `updateConversation`,
  `deleteConversation` 和 `acp` 命名空间 (`createConversation`,
  `getConversation`, `getConversations`, `getAllConversations`,
  `countConversations`、`searchConversations`) 为 ACP 智能体。 `pause`、压缩、目标和配置文件或模型切换是薄包装器，其路线由各自的系列驱动（F05、F09、F10、F11）； 这家人不打电话给他们。
- 状态和事件：`RemoteState`（`GET /api/conversations/{id}`，缓存 2 秒）、`RemoteEventsList.search|count|getEventById|getEventsById|getEvents`（`GET .../events/search`、`.../events/count`、`.../events/{event_id}`）。
- 工作区：`RemoteWorkspace.executeCommand` (`POST /api/bash/execute_bash_command`), `uploadText`/`fileUpload` (`POST /api/file/upload`), `downloadAsText`/`downloadAsBlob`/`fileDownload` (`GET /api/file/download`), `gitChanges`/`gitDiff` (`GET /api/git/changes`,
  `/api/git/diff`）、`bash.*`（`BashClient`：开始、搜索、获取、批量获取、停止、清除）、`startWorkspaceSession`/`deleteWorkspaceSession`（`/api/auth/workspace-session`）。 使用 `conversationId` bash、文件和
  git calls go to `/api/conversations/{id}/bash/...`, `.../file/...` and
  `.../git/...` 当
  `/server_info` 通告 `conversation_runtime_routes_v1`（否则为 `cid` 查询参数）。 `FileClient` 下载为 `ArrayBuffer`。
- WebSockets：`ConversationEventStream`（`/sockets/events/{id}`，第一帧身份验证，`queryParams`，可选重新连接）使用全局`WebSocket`，除非给定`createWebSocket`； `WebSocketCallbackClient`（使用者
  `RemoteConversation.startWebSocketClient`) 和 `BashWebSocketClient` (`/sockets/bash-events`, 已弃用 `session_api_key` 查询验证) 查找
  `globalThis.WebSocket` 每次连接（浏览器、节点 22+）。
- 版本门：`HooksClient`、`WorkspacesClient`和`MCPClient`调用
  `assertAgentServerSupports`（挂钩、工作区和 MCP 测试需要 1.23.0、MCP OAuth 1.31.0），每个 `HttpClient` 缓存一个 `/server_info`。
- 合同工具：`npm run audit:endpoints`（`scripts/endpoint-audit.mjs`）和`npm run generate:agent-server-api`，这需要
  `AGENT_SERVER_OPENAPI_PATH`（和 `AGENT_SERVER_GENERATED_OUTPUT`）针对从源导出的合约离线运行
  `.github/scripts/export_agent_server_openapi.py`.
- Agent Canvas (`OpenHands/OpenHands`) 消耗此包； 仅上下文。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  `node`（22 或更高版本，对于全局 `WebSocket`）位于 `PATH` 上并且
  设置为`$DEEPSEEK_API_KEY`。 块在客户端依赖项缺失时安装它们（需要 `npm`），在缺失或任何文件在 `src/` 或 `package.json` 中较旧时重建 `clients/typescript/dist`，因此，带有客户端更改的检查总是与过时的构建进行验证。
- 该块保存 DeepSeek 配置文件，使用 `lib.mjs` 创建 `qa-f34` 测试夹具目录（导入入口和导出 `host`，
  每个程序的 `apiKey`、`F34`、`NOPE`、`sleep`、`waitFor` 和 `assert`）、`reconnect.mjs`（两个重新连接子弹的观察者：一个
  `ConversationEventStream` 指定模式下，`ws` 通过 `ws` 包的构造函数或 `native` Node 的全局 `WebSocket`，记录每个进程是否下线、重启后是否恢复以及是否在重启后收到消息，以及在没有返回的流上不会抛出异常，一个项目有 `.openhands/hooks.json`，一个 stdio MCP 服务器，以及 `SCID`：一个永远不会运行的对话（占位符智能体，工作区）
  `$F34/scoped`，一条排队的用户消息），范围工作区项目符号和每个已知错误项目符号都使用它，因此已知错误上的 `map run --only` 除了这个块之外什么都不需要。 程序按每个项目符号写入 `$F34` 并运行
  `control-agent-server exec`，注入 `AGENT_SERVER_URL` 和
  `SESSION_API_KEY`; 后面的项目符号需要的值（对话 ID）将写入 `$F34` 下的文件中。 已知缺陷的程序只观察到以下内容：它断言其正控件，将客户端返回的内容写入 JSON 文件下的 `$F34`，并打印出来，而标记为 `# bug` 的行（`jq -e` 或 `tsc`）断言正确的值，因此 `map run` 只在断言失败时报告缺陷。
- `F34.version-gate-old` 从 PyPI 和 `uvx` 下载 1.22.0 智能体-服务器版本（大约 200 个包，第一次后缓存）。

  ```sh
  test -d clients/typescript/node_modules/typescript || (cd clients/typescript && npm ci --silent)
  if [ ! -f clients/typescript/dist/index.js ] || \
    [ -n "$(find clients/typescript/src clients/typescript/package.json -newer clients/typescript/dist/index.js -print -quit)" ]; then
    (cd clients/typescript && npm run build --silent)
  fi
  test -z "$(find clients/typescript/src -newer clients/typescript/dist/index.js -print -quit)"
  control-agent-server llm preset deepseek
  F34="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f34"
  mkdir -p "$F34/work" "$F34/files" "$F34/scoped"
  SCID=$(control-agent-server conversation start --no-run --placeholder-agent --tools none --no-autotitle --workspace "$F34/scoped" \
    --prompt 'qa-f34-scoped: never run' --print-id)
  control-agent-server api GET "/api/conversations/$SCID" --expect 200 --check execution_status eq idle --check workspace.working_dir eq "$F34/scoped"
  cat > "$F34/lib.mjs" <<'JS'
  import assert from 'node:assert/strict';
  const root = 'file://' + process.cwd() + '/';
  export const m = await import(new URL('clients/typescript/dist/index.js', root).href);
  export const c = await import(new URL('clients/typescript/dist/clients.js', root).href);
  export const host = process.env.AGENT_SERVER_URL;
  export const apiKey = process.env.SESSION_API_KEY;
  export const F34 = process.env.AGENT_SERVER_VERIFY_RUN + '/fixtures/qa-f34';
  export const NOPE = '00000000-0000-0000-0000-000000000000';
  export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  export async function waitFor(fn, ms = 60000, step = 250) {
    const end = Date.now() + ms;
    for (;;) {
      const value = await fn();
      if (value) return value;
      if (Date.now() > end) throw new Error('waitFor timed out');
      await sleep(step);
    }
  }
  export { assert };
  JS
  cat > "$F34/reconnect.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { c, host, apiKey, F34, sleep } from './lib.mjs';
  const { WebSocket: WS } = await import(new URL('clients/typescript/node_modules/ws/wrapper.mjs', 'file://' + process.cwd() + '/').href);
  const [cid, out, ...modes] = process.argv.slice(2);
  const until = async (ok, ms) => { for (const end = Date.now() + ms; !ok() && Date.now() < end;) await sleep(50); return ok(); };
  const watch = (mode) => {
    const r = { mode, frames: [], states: [] };
    r.stream = new c.ConversationEventStream({ url: c.buildConversationEventStreamUrl(host, cid), sessionApiKey: apiKey,
      queryParams: { resend_mode: 'all' }, reconnect: { enabled: true },
      ...(mode === 'ws' ? { createWebSocket: (url) => new WS(url) } : {}),
      onMessage: (f) => r.frames.push({ at: r.states.length, frame: JSON.parse(f.data) }),
      onStateChange: (s) => r.states.push(s) });
    r.stream.start();
    return r;
  };
  const seen = (r, text, after = -1) => r.frames.filter((f) => f.at > after && f.frame.kind === 'MessageEvent' &&
    JSON.stringify(f.frame).includes(text)).length;
  const streams = modes.map(watch);
  if (!(await until(() => streams.every((r) => seen(r, 'qa-f34-reconnect: never run')), 15000))) throw new Error('no first replay');
  writeFileSync(`${F34}/reconnect-ready`, '');
  const results = await Promise.all(streams.map(async (r) => {
    const down = () => r.states.findIndex((s) => !s.isConnected && s.isReconnecting);
    const up = () => (down() < 0 ? -1 : r.states.findIndex((s, i) => i > down() && s.isConnected));
    await until(() => down() >= 0, 60000);
    await until(() => up() >= 0 && seen(r, 'qa-f34-after-restart', up()) > 0, 60000);
    const last = r.states.at(-1);
    r.stream.stop();
    return [r.mode, { went_down: down() >= 0, reconnected: up() >= 0, attempts: Math.max(...r.states.map((s) => s.attemptCount)),
      replayed_after: up() < 0 ? 0 : seen(r, 'qa-f34-reconnect: never run', up()),
      sent_after: up() < 0 ? 0 : seen(r, 'qa-f34-after-restart', up()),
      last_state: { ...last, error: last.error && last.error.message } }];
  }));
  writeFileSync(out, JSON.stringify(Object.fromEntries(results)));
  console.log('QA_F34_RECONNECT_WATCHED');
  JS
  PROJECT=$(control-agent-server fixture project --name qa-f34-project --print-path)
  test -f "$PROJECT/.openhands/hooks.json"
  control-agent-server fixture mcp-server --name qa-f34-mcp
  test -f "$AGENT_SERVER_VERIFY_RUN/fixtures/mcp/qa-f34-mcp.py"
  ```

- **服务器状态和版本门(`F34.server-client`)。**没有密钥的探针，有一个服务器信息，通过两者入口； 然后是门控客户端，该服务器对于它来说已经足够新了。
  ```sh
  VERSION=$(control-agent-server api GET /server_info --auth none --field version)
  cat > "$F34/server.mjs" <<'JS'
  import { m, c, host, apiKey, assert } from './lib.mjs';
  const version = process.argv[2];
  const anonymous = new c.ServerClient({ host });
  assert.deepEqual(await anonymous.getAlive(), { status: 'ok' });
  assert.deepEqual(await anonymous.getHealth(), { status: 'ok' });
  assert.deepEqual(await anonymous.getReady(), { status: 'ready' });
  assert.equal((await anonymous.getRoot()).version, version);
  const manager = new m.ConversationManager({ host, apiKey });
  const info = await manager.server.getServerInfo();
  assert.equal(info.version, version);
  assert.ok(info.capabilities.includes('conversation_runtime_routes_v1'));
  assert.ok(info.usable_tools.includes('file_editor'));
  const aggregate = new c.AgentServerClient({ host, apiKey });
  assert.deepEqual(await aggregate.server.getHealth(), { status: 'ok' });
  console.log('QA_F34_SERVER_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_SERVER_OK --save F34.server-client/program -- node "$F34/server.mjs" "$VERSION"
  N=$(control-agent-server api GET /api/workspaces --field workspaces | jq length)
  cat > "$F34/gate.mjs" <<'JS'
  import { m, host, apiKey, assert } from './lib.mjs';
  const [version, count] = process.argv.slice(2);
  const http = new m.HttpClient({ baseUrl: host, apiKey });
  for (const requirement of Object.values(m.AgentServerFeatureRequirements)) {
    assert.equal((await m.assertAgentServerSupports(http, requirement)).version, version);
    assert.ok(m.compareAgentServerVersions(version, requirement.minVersion) >= 0);
  }
  assert.equal(await m.getCachedAgentServerInfo(http), await m.getCachedAgentServerInfo(http));
  const listed = await new m.WorkspacesClient({ host, apiKey }).listWorkspaces();
  assert.equal(listed.workspaces.length, Number(count));
  assert.ok(Array.isArray(listed.workspaceParents));
  assert.deepEqual(await new m.HooksClient({ host, apiKey }).loadHooks({ project_dir: '/qa-f34-no-project' }), { hook_config: null });
  console.log('QA_F34_GATE_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_GATE_OK --save F34.server-client/gate -- node "$F34/gate.mjs" "$VERSION" "$N"
  ```
  第一个程序打印 `QA_F34_SERVER_OK`：探针回答
  `ok`/`ready`、`/` 和 `/server_info` 报告 CLI 读取的版本。 第二个打印 `QA_F34_GATE_OK`：每个要求 (`workspaces`,
  `hooks`, `mcp-test` 1.23.0, `mcp-oauth` 1.31.0) 传递该服务器的版本，缓存的 `/server_info` 是同一个对象两次，门控调用返回服务器的数据（注册表大小 REST 报告，没有针对丢失项目的钩子）。
- **错误 (`F34.http-errors`)。**客户端的每一次拒绝都会在同一台服务器上进行积极的控制。
  ```sh
  cat > "$F34/errors.mjs" <<'JS'
  import { m, host, apiKey, NOPE, assert } from './lib.mjs';
  const manager = new m.ConversationManager({ host, apiKey });
  assert.equal(typeof (await manager.countConversations()), 'number');
  await assert.rejects(new m.ConversationManager({ host }).countConversations(), (e) =>
    m.isHttpError(e) && e.status === 401 && e.detail === 'Unauthorized' &&
    e.message === 'HTTP request failed (401 Unauthorized): {"detail":"Unauthorized"}');
  await assert.rejects(new m.ConversationManager({ host, apiKey: 'qa-f34-wrong-key' }).countConversations(),
    (e) => m.isHttpError(e) && e.status === 401 && e.detail === 'Unauthorized');
  await assert.rejects(manager.getConversation(NOPE), (e) => e.status === 404 && e.detail === 'Not Found');
  await assert.rejects(manager.getConversation('qa-f34-not-a-uuid'), (e) =>
    e.status === 422 && e.validationErrors.length === 1 && e.validationErrors[0].type === 'uuid_parsing' &&
    e.validationErrors[0].loc.join('.') === 'path.conversation_id' && e.detail === e.validationErrors[0].msg);
  const http = new m.HttpClient({ baseUrl: host, apiKey });
  await assert.rejects(http.post('/api/file/upload', {}), (e) =>
    e.status === 422 && e.validationErrors.length === 2 &&
    e.detail === e.validationErrors.map((v) => `${v.loc.at(-1)}: ${v.msg}`).join('; '));
  await assert.rejects(new m.HttpClient({ baseUrl: 'http://127.0.0.1:9' }).get('/alive'),
    (e) => !m.isHttpError(e) && e.message.startsWith('Request failed: '));
  const slow = new m.HttpClient({ baseUrl: host, apiKey, timeout: 500 });
  const started = Date.now();
  await assert.rejects(slow.post('/api/bash/execute_bash_command', { command: 'sleep 2', timeout: 10 }),
    (e) => !m.isHttpError(e) && e.message === 'Request timeout after 500ms');
  assert.ok(Date.now() - started < 1800, `timeout took ${Date.now() - started} ms`);
  console.log('QA_F34_ERRORS_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_ERRORS_OK --save F34.http-errors/program -- node "$F34/errors.mjs"
  control-agent-server api GET /api/conversations/count --auth none --expect 401 --check detail eq Unauthorized
  ```
  程序打印 `QA_F34_ERRORS_OK`：401 状态码都是 `HttpError`
  `detail``Unauthorized`和传输层`message`； 未知的 ID 是 404
  `Not Found`; 格式错误的 id 是 422，其单个 `uuid_parsing` 条目是 `detail`，并且缺少两个字段的正文将它们连接为
  `path: Field required; file: Field required`; 关闭的端口和 500 ms 客户端超时会在 2 s 命令结束之前用普通的 `Error` 拒绝，超时 。
- **工作区命令 (`F34.workspace-exec`).**输出，`cwd`，退出代码和命令本身的超时。
  ```sh
  cat > "$F34/exec.mjs" <<'JS'
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const dir = `${F34}/work`;
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: dir });
  const command = 'echo qa-f34-out; echo qa-f34-err >&2; pwd; printf qa-f34-exec > qa-f34-exec.txt';
  assert.deepEqual(await workspace.executeCommand(command, dir), {
    command, exit_code: 0, stdout: `qa-f34-out\n${dir}\n`, stderr: 'qa-f34-err\n', timeout_occurred: false,
  });
  assert.equal((await workspace.executeCommand('exit 3')).exit_code, 3);
  const started = Date.now();
  const killed = await workspace.executeCommand('sleep 5', dir, 1);
  assert.equal(killed.exit_code, -1);
  assert.ok(Date.now() - started < 4500, `took ${Date.now() - started} ms`);
  console.log('QA_F34_EXEC_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_EXEC_OK --save F34.workspace-exec/program -- node "$F34/exec.mjs"
  test "$(cat "$F34/work/qa-f34-exec.txt")" = qa-f34-exec
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand --query sort_order=TIMESTAMP_DESC --query limit=3 \
    --check items.0.command eq 'sleep 5' --check items.0.timeout eq 1 --check items.1.command eq 'exit 3' \
    --check items.2.command contains qa-f34-out --check items.2.cwd eq "$F34/work" --save F34.workspace-exec/history
  ```
  第一个结果是精确的； `exit 3`报告3； `sleep 5` 1秒后返回，超时 4秒后返回，`-1` 2秒后返回，`timeout_occurred` 3秒后返回
  `false`，参见陷阱）。 命令写入的文件位于磁盘上，服务器的 bash 历史记录列出了三个命令及其 `cwd` 和超时。
- **工作区个文件 (`F34.workspace-files`).**文本和字节，然后是拒绝。
  ```sh
  cat > "$F34/files.mjs" <<'JS'
  import { m, c, host, apiKey, F34, assert } from './lib.mjs';
  const dir = `${F34}/files`;
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: dir });
  const uploaded = await workspace.uploadText('qa-f34 text\n', `${dir}/up.txt`);
  assert.equal(uploaded.success, true);
  assert.equal(uploaded.destination_path, `${dir}/up.txt`);
  assert.equal(uploaded.file_size, Buffer.byteLength('qa-f34 text\n'));
  assert.equal(await workspace.downloadAsText(`${dir}/up.txt`), 'qa-f34 text\n');
  await workspace.fileUpload(new Blob([new Uint8Array([0xff, 0x00, 0x80, 0xfe, 0x41])]), `${dir}/nested/bin.dat`);
  const files = new c.FileClient({ host, apiKey });
  assert.deepEqual([...new Uint8Array(await files.downloadFile(`${dir}/nested/bin.dat`))], [255, 0, 128, 254, 65]);
  assert.equal(await files.downloadTextFile(`${dir}/up.txt`), 'qa-f34 text\n');
  assert.deepEqual(await files.uploadTextFile('qa-f34 via FileClient', `${dir}/fc.txt`),
    { success: true, file_size: Buffer.byteLength('qa-f34 via FileClient') });
  await assert.rejects(workspace.downloadAsText(`${dir}/missing.txt`), (e) => e.status === 404 && e.detail === 'File not found');
  await assert.rejects(workspace.uploadText('x', 'qa-f34-relative.txt'), (e) => e.status === 400 && e.detail === 'Path must be absolute');
  await assert.rejects(workspace.downloadAsText(dir), (e) => e.status === 400 && e.detail === 'Path is not a file');
  console.log('QA_F34_FILES_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_FILES_OK --save F34.workspace-files/program -- node "$F34/files.mjs"
  test "$(cat "$F34/files/up.txt")" = 'qa-f34 text'
  test "$(od -An -tx1 "$F34/files/nested/bin.dat" | tr -d ' \n')" = ff0080fe41
  control-agent-server api GET /api/file/download --query "path=$F34/files/fc.txt" --expect 200 --raw-out "$F34/files/fc.copy"
  test "$(cat "$F34/files/fc.copy")" = 'qa-f34 via FileClient'
  ```
  文本回退，上传创建了缺失的`nested/`目录，磁盘上五字完全与发送的一致，`FileClient`读取后未变。 两者都报告了上传响应中添加的字节数
  #5856，服务器自己的下载服务于`FileClient`上传。
- **通过 RemoteWorkspace (`F34.workspace-binary-download`) 进行二进制下载，已知错误。**
  `RemoteWorkspace.fileDownload` 让传输层解析
  `application/octet-stream` 正文为文本，因此 `downloadAsBlob` 和
  `fileDownload`返回UTF-8解码字节（`clients/typescript/src/workspace/remote-workspace.ts:183`，无`responseType`）； `FileClient.downloadFile`要求`arrayBuffer`并且是正确的。 子弹自己写五个字，程序首先通过`FileClient`（正控制）读回这些字，然后记录`downloadAsBlob`和`fileDownload`返回的内容。
  ```sh
  printf '\377\000\200\376A' > "$F34/files/qa-f34-bin.dat"
  test "$(od -An -tx1 "$F34/files/qa-f34-bin.dat" | tr -d ' \n')" = ff0080fe41
  cat > "$F34/binary.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, c, host, apiKey, F34, assert } from './lib.mjs';
  const path = `${F34}/files/qa-f34-bin.dat`;
  assert.deepEqual([...new Uint8Array(await new c.FileClient({ host, apiKey }).downloadFile(path))], [255, 0, 128, 254, 65]);
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: `${F34}/files` });
  const blob = [...new Uint8Array(await (await workspace.downloadAsBlob(path)).arrayBuffer())];
  const { file_size: fileSize } = await workspace.fileDownload(path);
  writeFileSync(`${F34}/binary.json`, JSON.stringify({ blob, file_size: fileSize }));
  console.log('QA_F34_BINARY_READ');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_BINARY_READ --save F34.workspace-binary-download/program -- node "$F34/binary.mjs"
  cat "$F34/binary.json"
  control-agent-server assert --json "$F34/binary.json" --check blob eq '[255, 0, 128, 254, 65]' --check file_size eq 5  # bug: value.file_size 等于 11 且 value.blob 等于 '[239, 191, 189, 0, 239, 191, 189, 239, 191, 189, 65]'
  ```
  预期：相同的 5 个字节和 `file_size` 5。 今天该团块持有 11
  bytes（`[239,191,189,0,239,191,189,239,191,189,65]`：每个无效字节都变成了U+FFFD），`file_size`是11，而磁盘上的文件有5。
- **对话范围工作区 (`F34.workspace-scoped`).** 工作区绑定到 `SCID`，来自 `Preconditions:` 的对话永远不会运行。
  ```sh
  cat > "$F34/scoped.mjs" <<'JS'
  import { m, host, apiKey, F34, NOPE, assert } from './lib.mjs';
  const scid = process.argv[2];
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: '/qa-f34-ignored', conversationId: scid });
  assert.equal((await workspace.executeCommand('pwd')).stdout, `${F34}/scoped\n`);
  await workspace.uploadText('qa-f34-scoped', `${F34}/scoped/qa-f34-scoped.txt`);
  assert.equal(await workspace.downloadAsText(`${F34}/scoped/qa-f34-scoped.txt`), 'qa-f34-scoped');
  await assert.rejects(workspace.uploadText('x', `${F34}/qa-f34-outside.txt`),
    (e) => e.status === 422 && e.detail === 'path must be inside the conversation workspace');
  await assert.rejects(workspace.executeCommand('pwd', '/tmp'),
    (e) => e.status === 422 && e.detail === 'cwd must be inside the conversation workspace');
  await assert.rejects(workspace.client.get('/api/file/download?path=/etc/hostname'), /separate query parameters/);
  const unknown = new m.RemoteWorkspace({ host, apiKey, workingDir: '/x', conversationId: NOPE });
  await assert.rejects(unknown.executeCommand('pwd'), (e) => e.status === 404);
  console.log('QA_F34_SCOPED_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_SCOPED_OK --save F34.workspace-scoped/program -- node "$F34/scoped.mjs" "$SCID"
  test "$(cat "$F34/scoped/qa-f34-scoped.txt")" = qa-f34-scoped
  test ! -e "$F34/qa-f34-outside.txt"
  control-agent-server api GET "/api/conversations/$SCID/bash/bash_events/search" --query kind__eq=BashCommand \
    --check items len-eq 1 --check items.0.command eq pwd --check items.0.cwd eq "$F34/scoped" --save F34.workspace-scoped/history
  ```
  工作区的`workingDir`被忽略：`pwd`打印会话的工作区，上传会到达那里，外部路径和
  `cwd` 为 422，外部未写入任何内容，路径中的查询字符串在任何请求之前都会被客户端拒绝，未知会话为
  404. 只有 `pwd` 位于对话自己的 bash 历史记录中。
- **通过 RemoteWorkspace (`F34.workspace-git`).** `git-repo` 测试夹具（一个已修改的文件，一个未跟踪的文件），全局且通过 `SCID` 的工作区内的副本。
  ```sh
  REPO=$(control-agent-server fixture git-repo --name qa-f34-repo --print-path)
  test -d "$F34/scoped/qa-f34-repo" || cp -r "$REPO" "$F34/scoped/qa-f34-repo"
  cat > "$F34/git.mjs" <<'JS'
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const [repo, scid] = process.argv.slice(2);
  const fixture = [{ status: 'UPDATED', path: 'README.md' }, { status: 'ADDED', path: 'notes.txt' }];
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: repo });
  assert.deepEqual(await workspace.gitChanges(repo), fixture);
  assert.deepEqual(await workspace.gitChanges(repo, { ref: 'HEAD' }), fixture);
  assert.deepEqual(await workspace.gitDiff(`${repo}/README.md`), {
    original: '# QA fixture repo\n\nCreated by control-agent-server.',
    modified: '# QA fixture repo\n\nModified, not committed.',
  });
  const scoped = new m.RemoteWorkspace({ host, apiKey, workingDir: '/qa-f34-ignored', conversationId: scid });
  assert.deepEqual(await scoped.gitChanges(`${F34}/scoped/qa-f34-repo`), fixture);
  await assert.rejects(scoped.gitChanges(repo), (e) => !m.isHttpError(e) && e.message.startsWith('Failed to get git changes: ') &&
    m.isHttpError(e.cause) && e.cause.status === 422 && e.cause.detail === 'path must be inside the conversation workspace');
  await assert.rejects(new m.RemoteWorkspace({ host, workingDir: repo }).gitDiff(`${repo}/README.md`),
    (e) => e.message.startsWith('Failed to get git diff: ') && m.isHttpError(e.cause) && e.cause.status === 401);
  console.log('QA_F34_GIT_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_GIT_OK --save F34.workspace-git/program -- node "$F34/git.mjs" "$REPO" "$SCID"
  control-agent-server api GET /api/git/changes --query path="$REPO" --expect 200 --check . len-eq 2 \
    --check 0.status eq UPDATED --check 0.path eq README.md --check 1.status eq ADDED --check 1.path eq notes.txt --save F34.workspace-git/changes
  control-agent-server api GET "/api/conversations/$SCID/git/diff" --query path="$F34/scoped/qa-f34-repo/README.md" --expect 200 \
    --check modified contains 'Modified, not committed.' --check original contains 'Created by control-agent-server.'
  ```
  `gitChanges` 返回未更改的服务器列表（`UPDATED README.md`，
  `ADDED notes.txt`，与`ref: 'HEAD'`相同），`gitDiff`原始和修改后的文本，范围工作区通过读取副本
  `/api/conversations/{id}/git/...`（只有该路由在对话工作区之外为测试夹具自己的路径应答 422）。 这两种方法都将拒绝包装在简单的 `Error` 中（“无法获取 git 更改：
  ...`) whose `cause` is the `HttpError`: 422 for a path outside the
  对话工作区，401，无需密钥。 REST 同意。
- **Git状态类型(`F34.workspace-git-types`).**导出的`GitChange`类型`status`为生成合约的`GitChangeStatus`(`'MOVED' | 'ADDED' | 'DELETED' | 'UPDATED'`),服务器发送的值，因此一个TypeScript消费者将值与网络值进行比较。 程序将返回值写入三个小文件，客户端自己进行类型检查：生成合同的返回状态和导出的路径（正例）：`gitChanges`、`.mts`、`tsc`、`GitChange`
  控制：相同的编译器、标志和导入解析），然后是状态
  针对导出的`GitChange`。
  ```sh
  REPO=$(control-agent-server fixture git-repo --name qa-f34-repo --print-path)
  cat > "$F34/git-types.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const repo = process.argv[2];
  const changes = await new m.RemoteWorkspace({ host, apiKey, workingDir: repo }).gitChanges(repo);
  const statuses = changes.map((c) => c.status);
  assert.deepEqual(statuses, ['UPDATED', 'ADDED']);
  const dist = process.cwd() + '/clients/typescript/dist';
  writeFileSync(`${F34}/git-contract.mts`, `import type { GitChangeStatus } from '${dist}/generated/agent-server-schema.js';\n` +
    `export const statuses: GitChangeStatus[] = ${JSON.stringify(statuses)};\n`);
  writeFileSync(`${F34}/git-paths.mts`, `import type { GitChange } from '${dist}/index.js';\n` +
    `export const paths: Array<GitChange['path']> = ${JSON.stringify(changes.map((c) => c.path))};\n`);
  writeFileSync(`${F34}/git-types.mts`, `import type { GitChange } from '${dist}/index.js';\n` +
    `export const statuses: Array<GitChange['status']> = ${JSON.stringify(statuses)};\n`);
  console.log('QA_F34_GIT_TYPES_WRITTEN');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_GIT_TYPES_WRITTEN --save F34.workspace-git-types/program -- node "$F34/git-types.mjs" "$REPO"
  TSC="node clients/typescript/node_modules/typescript/bin/tsc --noEmit --strict --skipLibCheck --module nodenext --moduleResolution nodenext --target es2022"
  $TSC "$F34/git-contract.mts"
  $TSC "$F34/git-paths.mts"
  $TSC "$F34/git-types.mts" | control-agent-server assert --check . eq ''
  ```
  预期：所有三个文件都进行类型检查，状态均针对
  生成的合同和导出的`GitChange`。
- **Bash 客户端 (`F34.bash-client`).**后台命令、查找、停止和清除，将套接字和 REST 历史记录作为第二视图。
  ```sh
  cat > "$F34/bash.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, NOPE, assert, waitFor } from './lib.mjs';
  const bash = new m.RemoteWorkspace({ host, apiKey, workingDir: '/tmp' }).bash;
  const done = (id) => async () => (await bash.searchEvents({ command_id__eq: id, kind__eq: 'BashOutput' }))
    .items.find((e) => e.exit_code !== null && e.exit_code !== undefined);
  const command = await bash.startCommand('echo qa-f34-bash', `${F34}/work`);
  assert.equal(command.kind, 'BashCommand');
  const output = await waitFor(done(command.id), 30000);
  assert.equal(output.stdout, 'qa-f34-bash\n');
  assert.equal(output.exit_code, 0);
  assert.equal((await bash.getEvent(command.id)).command, 'echo qa-f34-bash');
  assert.deepEqual((await bash.batchGetEvents([output.id, NOPE.replaceAll('-', '')])).map((e) => e && e.kind), ['BashOutput', null]);
  assert.deepEqual((await bash.getEvents([command.id, NOPE.replaceAll('-', '')])).map((e) => e && e.kind), ['BashCommand', null]);
  const started = Date.now();
  const sleeper = await bash.startCommand('sleep 30');
  await bash.stopCommand(sleeper.id);
  const stopped = await waitFor(done(sleeper.id), 15000);
  assert.notEqual(stopped.exit_code, 0);
  assert.ok(Date.now() - started < 15000);
  await bash.stopCommand(NOPE);
  await bash.stopCommand(command.id);
  writeFileSync(`${F34}/bash-command-id`, command.id);
  console.log('QA_F34_BASH_OK');
  JS
  control-agent-server exec --timeout 90 --expect-output QA_F34_BASH_OK --save F34.bash-client/program -- node "$F34/bash.mjs"
  BCMD=$(cat "$F34/bash-command-id")
  control-agent-server api GET "/api/bash/bash_events/$BCMD" --expect 200 --check command eq 'echo qa-f34-bash' --check cwd eq "$F34/work"
  control-agent-server ws listen /sockets/bash-events --query resend_mode=all --expect-kind BashCommand --expect-kind BashOutput \
    --duration 3 --save F34.bash-client/socket
  cat > "$F34/bash-clear.mjs" <<'JS'
  import { m, host, apiKey, assert } from './lib.mjs';
  const { cleared_count } = await new m.RemoteWorkspace({ host, apiKey, workingDir: '/tmp' }).bash.clearEvents();
  assert.ok(cleared_count >= 4, `cleared ${cleared_count}`);
  console.log('QA_F34_BASH_CLEAR_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_BASH_CLEAR_OK -- node "$F34/bash-clear.mjs"
  control-agent-server api GET /api/bash/bash_events/search --check items len-eq 0 --save F34.bash-client/cleared
  control-agent-server api GET "/api/bash/bash_events/$BCMD" --expect 404
  ```
  命令的输出以0作为退出码，查找命令和其输出以`null`标识未知ID，30秒`sleep`内停止，且非零退出码。停止一个未知或已完成的命令有效。 REST 用其 `cwd` 命令，bash 会重播这两种类型，并在 `clearEvents` 后历史为空，命令为 404。
- **来自 Node 的 Bash 事件套接字 (`F34.bash-websocket`).**
  `BashWebSocketClient` 使用 Node 的全局 `WebSocket` 打开其套接字，在连接时间 (`clients/typescript/src/events/global-websocket.ts`) 进行查找。 子弹运行自己的命令，CLI 首先在同一个套接字上重放其输出（正控制）； 然后程序给客户端 10 秒的时间并记录它看到的输出和错误。
  ```sh
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command": "echo qa-f34-bash-ws", "cwd": "/tmp"}' \
    --expect 200 --check stdout contains qa-f34-bash-ws
  control-agent-server ws start /sockets/bash-events --query resend_mode=all --name qa-f34-bash-ws --duration 30
  control-agent-server ws stop qa-f34-bash-ws --kinds BashOutput --contains qa-f34-bash-ws --expect-kind BashOutput --wait 10 \
    --save F34.bash-websocket/cli
  cat > "$F34/bash-ws.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, sleep } from './lib.mjs';
  const events = [];
  const errors = [];
  const client = new m.BashWebSocketClient({ host, apiKey, resendMode: 'all',
    callback: (e) => events.push(e), onError: (e) => errors.push(e.message) });
  const seen = () => events.some((e) => e.kind === 'BashOutput' && e.stdout === 'qa-f34-bash-ws\n');
  client.start();
  for (const end = Date.now() + 10000; Date.now() < end && !seen();) await sleep(100);
  client.stop();
  writeFileSync(`${F34}/bash-ws.json`, JSON.stringify({ saw_output: seen(), frames: events.length, errors: [...new Set(errors)] }));
  console.log('QA_F34_BASH_WS_DONE');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_BASH_WS_DONE --save F34.bash-websocket/program -- node "$F34/bash-ws.mjs"
  cat "$F34/bash-ws.json"
  control-agent-server assert --json "$F34/bash-ws.json" --check saw_output eq true --check errors len-eq 0
  ```
  预期：重播的`BashOutput`到达回调并且`onError`是
  从来没有打电话过。
- **工作区会话 (`F34.workspace-session`).**饼干薄荷及其底座 URL； Node 的 `fetch` 没有保留 cookie jar，因此 URL 是通过标头获取的（F02 证明了 cookie 本身）。
  ```sh
  cat > "$F34/session.mjs" <<'JS'
  import { m, host, apiKey, NOPE, assert } from './lib.mjs';
  const scid = process.argv[2];
  const workspace = new m.RemoteWorkspace({ host, apiKey, workingDir: '/qa-f34-ignored' });
  const base = await workspace.startWorkspaceSession(scid);
  assert.equal(base, `${host}/api/conversations/${scid}/workspace/`);
  const file = await fetch(base + 'qa-f34-scoped.txt', { headers: { 'X-Session-API-Key': apiKey } });
  assert.equal(file.status, 200);
  assert.equal(await file.text(), 'qa-f34-scoped');
  await workspace.deleteWorkspaceSession();
  const scoped = new m.RemoteWorkspace({ host, apiKey, workingDir: '/x', conversationId: scid });
  await assert.rejects(scoped.startWorkspaceSession(NOPE), /Workspace session must belong to the selected runtime/);
  assert.equal(await scoped.startWorkspaceSession(scid), base);
  await assert.rejects(new m.RemoteWorkspace({ host, workingDir: '/x' }).startWorkspaceSession(scid), (e) => e.status === 401);
  await assert.rejects(new m.RemoteWorkspace({ host, workingDir: '/x' }).deleteWorkspaceSession(), (e) => e.status === 401);
  console.log('QA_F34_SESSION_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_SESSION_OK --save F34.workspace-session/program -- node "$F34/session.mjs" "$SCID"
  control-agent-server api GET "/api/conversations/$SCID/workspace/qa-f34-scoped.txt" --expect 200 --raw-out "$F34/session.copy"
  test "$(cat "$F34/session.copy")" = qa-f34-scoped
  ```
  铸造器处理完毕 `<host>/api/conversations/<id>/workspace/`该端点用于服务文件。 删除解析到204； 一个 scoped 工作区拒绝另一个会话的 ID 无请求。 两个路由都返回401，没有密钥。
- **创建对话 (`F34.conversation-create`)。**一个真实的 DeepSeek 智能体，带有一个工具和一个钩子配置，已创建但未运行。
  ```sh
  cat > "$F34/create.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const agent = new m.Agent({
    llm: { model: 'deepseek/deepseek-flash', api_key: process.env.DEEPSEEK_API_KEY, usage_id: 'agent' },
    tools: [{ name: 'file_editor' }],
  });
  const hookConfig = { pre_tool_use: [{ matcher: '*', hooks: [{ type: 'command', command: 'echo qa-f34-hook' }] }] };
  const conversation = new m.RemoteConversation(agent, new m.RemoteWorkspace({ host, apiKey, workingDir: `${F34}/work` }), { hookConfig });
  assert.throws(() => conversation.id, /Call start\(\)/);
  await conversation.start({ maxIterations: 20 });
  assert.match(conversation.id, /^[0-9a-f-]{36}$/);
  assert.equal(conversation.workspace.conversationId, conversation.id);
  assert.equal(conversation.workspace.workingDir, `${F34}/work`);
  writeFileSync(`${F34}/cid`, conversation.id);
  console.log('QA_F34_CREATE_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_CREATE_OK --save F34.conversation-create/program -- node "$F34/create.mjs"
  CID=$(cat "$F34/cid")
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --max-chars 300 --check execution_status eq idle \
    --check workspace.working_dir eq "$F34/work" --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.tools.0.name eq file_editor --check max_iterations eq 20 --save F34.conversation-create/server
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 0
  ```
  `id` 在 `start()` 之前抛出； 之后，对话存在`idle`与客户端的模型、工具、工作目录和迭代限制，并且还没有事件。 钩子配置也被存储，但仅在智能体启动后才显示在对话中（在下一个项目符号中检查）。
- **发送并运行 (`F34.conversation-run`)。**第二个程序通过 id 重新连接，发送一个小任务并在 deepseek-flash 上运行它。

  需要：`F34.conversation-create`
  ```sh
  cat > "$F34/run.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert, waitFor } from './lib.mjs';
  const cid = process.argv[2];
  const placeholder = new m.Agent({ llm: { model: 'qa-f34/unused' } });
  const conversation = new m.RemoteConversation(placeholder,
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/qa-f34-ignored' }), { conversationId: cid });
  await conversation.start();
  assert.equal(conversation.workspace.workingDir, `${F34}/work`);
  await conversation.sendMessage('Use the file_editor tool to create the file qa-f34.txt in the current working directory containing exactly: hi. Then finish.');
  assert.equal((await conversation.state.refresh()).execution_status, 'idle');
  await conversation.run();
  const status = await waitFor(async () => {
    const value = (await conversation.state.refresh()).execution_status;
    return ['finished', 'error', 'stuck'].includes(value) && value;
  }, 240000, 1000);
  assert.equal(status, 'finished');
  assert.equal((await conversation.getHookConfig()).pre_tool_use[0].hooks[0].command, 'echo qa-f34-hook');
  assert.equal((await conversation.workspace.downloadAsText(`${F34}/work/qa-f34.txt`)).trim(), 'hi');
  const stats = await conversation.conversationStats();
  assert.ok(stats.usage_to_metrics.agent.accumulated_token_usage.prompt_tokens > 0);
  const response = await conversation.getAgentFinalResponse();
  assert.equal(typeof response, 'string');
  writeFileSync(`${F34}/final-client.json`, JSON.stringify({ response }));
  const zip = await conversation.downloadTrajectory();
  assert.deepEqual([...new Uint8Array(await zip.slice(0, 2).arrayBuffer())], [0x50, 0x4b]);
  console.log('QA_F34_RUN_OK');
  JS
  control-agent-server exec --timeout 300 --expect-output QA_F34_RUN_OK --save F34.conversation-run/program -- node "$F34/run.mjs" "$CID"
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check execution_status eq finished \
    --check hook_config.pre_tool_use.0.hooks.0.command eq 'echo qa-f34-hook' --save F34.conversation-run/server
  grep -qx hi "$F34/work/qa-f34.txt"
  control-agent-server api GET "/api/conversations/$CID/agent_final_response" --expect 200 --raw-out "$F34/final-rest.json"
  jq -e --slurpfile client "$F34/final-client.json" '.response == $client[0].response' "$F34/final-rest.json"
  control-agent-server api GET "/api/conversations/$CID/events/count" --query source=user --check . eq 1
  control-agent-server conversation events "$CID" --kinds ObservationEvent --contains qa-f34.txt
  control-agent-server conversation events "$CID" --kinds HookExecutionEvent --contains qa-f34-hook
  cat > "$F34/state.mjs" <<'JS'
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const cid = process.argv[2];
  const conversation = new m.RemoteConversation(new m.Agent({ llm: { model: 'qa-f34/unused' } }),
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/x' }), { conversationId: cid });
  await conversation.start();
  const state = conversation.state;
  assert.equal(state.id, cid);
  assert.equal(await state.getExecutionStatus(), 'finished');
  assert.equal(await state.getAgentStatus(), 'finished');
  assert.equal((await state.getAgent()).llm.model, 'deepseek/deepseek-flash');
  assert.deepEqual(await state.getWorkspace(), { kind: 'LocalWorkspace', working_dir: `${F34}/work` });
  assert.deepEqual(await state.getConfirmationPolicy(), { kind: 'NeverConfirm' });
  assert.ok((await state.getPersistenceDir()).endsWith(cid.replaceAll('-', '')));
  assert.equal(JSON.parse(await state.modelDumpJson()).id, cid);
  assert.ok(Array.isArray(await state.getActivatedKnowledgeSkills()));
  await assert.rejects(state.setAgentStatus('running'), /has no effect/);
  console.log('QA_F34_STATE_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_STATE_OK --save F34.conversation-run/state -- node "$F34/state.mjs" "$CID"
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check execution_status eq finished --check confirmation_policy.kind eq NeverConfirm
  ```
  `start()` 带有 id 将工作区重新绑定到服务器的工作目录； 消息本身就离开了对话 `idle`； `run()`达到`finished`； 客户端读取它在创建时发送的钩子配置，
  `hi` 来自智能体的文件，词元用量用于 `agent` LLM，最终响应（无论其形式如何：`finish` 消息或最后一个智能体消息，与 REST 所服务的相同）和 ZIP 轨迹 (`PK`)。 服务器同意：`finished`、钩子配置、一条用户消息、命名文件的 `file_editor` 观测结果和 `echo qa-f34-hook` 的 `HookExecutionEvent`。 第三个程序读取每个 `RemoteState` 访问器（状态、智能体模型、工作区、
  `NeverConfirm`，以 id 命名的持久化目录）和
  `setAgentStatus` 拒绝`Setting execution_status on RemoteState has no effect`。
- **事件列表(`F34.events-list`).**针对存储的日志进行计数、过滤、分页和查找。

  需要：`F34.conversation-create`
  ```sh
  TOTAL=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  cat > "$F34/events.mjs" <<'JS'
  import { m, host, apiKey, assert } from './lib.mjs';
  const [cid, total] = process.argv.slice(2);
  const events = new m.RemoteEventsList({ baseUrl: host, apiKey }, cid);
  assert.equal(await events.count(), Number(total));
  const all = await events.getEvents();
  assert.equal(all.length, Number(total));
  assert.equal(new Set(all.map((e) => e.id)).size, all.length);
  const users = await events.search({ source: 'user' });
  assert.deepEqual(users.items.map((e) => e.kind), ['MessageEvent']);
  const actions = await events.search({ kind: 'openhands.sdk.event.llm_convertible.action.ActionEvent' });
  assert.ok(actions.items.length >= 1 && actions.items.every((e) => e.kind === 'ActionEvent'));
  assert.ok((await events.search({ body: 'QA-F34.TXT' })).items.length >= 1);
  const first = await events.search({ limit: 2 });
  assert.equal(first.items.length, 2);
  const second = await events.search({ limit: 2, page_id: first.next_page_id });
  assert.ok(!first.items.some((e) => second.items.some((s) => s.id === e.id)));
  assert.equal((await events.getEventById(all[0].id)).id, all[0].id);
  assert.deepEqual((await events.getEventsById([all[1].id, all[2].id])).map((e) => e.id), [all[1].id, all[2].id]);
  let iterated = 0;
  for await (const event of events) iterated += event.id ? 1 : 0;
  assert.equal(iterated, Number(total));
  console.log('QA_F34_EVENTS_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_EVENTS_OK --save F34.events-list/program -- node "$F34/events.mjs" "$CID" "$TOTAL"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$TOTAL"
  ```
  `count`、`getEvents` 和异步迭代器都看到 `TOTAL` 个不同的事件； 用户过滤器返回一条消息，全称的唯一动作，正文过滤器不区分大小写，页面不重叠，通过ID查找返回存储的事件。
- **未知事件 ID (`F34.events-unknown-id`)。** `F06.unknown-event` 通过客户端到达：`getEventById` 期望记录的 404 和
  `getEventsById` 将其映射到 `null` (`clients/typescript/src/events/remote-events-list.ts:110`)。 运行于
  `SCID`，其第一个事件由id先读回（正控）； 程序记录每次通话的结算方式。
  ```sh
  cat > "$F34/unknown-event.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, NOPE, assert } from './lib.mjs';
  const events = new m.RemoteEventsList({ baseUrl: host, apiKey }, process.argv[2]);
  const [first] = (await events.search({ limit: 1 })).items;
  assert.equal((await events.getEventById(first.id)).id, first.id);
  const settle = (promise) => promise.then((value) => ({ value }),
    (e) => ({ http_error: m.isHttpError(e), status: e.status, response: e.response }));
  const single = await settle(events.getEventById(NOPE).then((e) => e.id));
  const batch = await settle(events.getEventsById([first.id, NOPE]).then((list) => list.map((e) => e && e.id)));
  writeFileSync(`${F34}/unknown-event.json`, JSON.stringify({ first: first.id, single, batch }));
  console.log('QA_F34_UNKNOWN_EVENT_READ');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_UNKNOWN_EVENT_READ --save F34.events-unknown-id/program -- node "$F34/unknown-event.mjs" "$SCID"
  cat "$F34/unknown-event.json"
  control-agent-server assert --json "$F34/unknown-event.json" --check single.http_error eq true --check single.status eq 404
  control-agent-server assert --json "$F34/unknown-event.json" --check batch.value len-eq 2 --check batch.value.0 eq "$(jq -r .first "$F34/unknown-event.json")" \
    --check batch.value.1 missing
  ```
  `getEventById` 拒绝并返回 404 `HttpError`，`getEventsById` 解析为 `[<event>, null]`，因此缺少一个 id 不会导致批次失败。
- **短事件类型 (`F34.events-search-kind`).** `F06.search-kind-short`通过客户端到达：路由和`EventSearchOptions.kind`(`clients/typescript/src/events/remote-events-list.ts`)文档
  `ActionEvent, MessageEvent`，服务器接受该裸类名以及 `<module>.<ClassName>`。 在 `SCID` 的排队用户消息上运行； 完全合格的类型首先找到它（阳性对照）。
  ```sh
  cat > "$F34/kind.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const events = new m.RemoteEventsList({ baseUrl: host, apiKey }, process.argv[2]);
  const qualified = 'openhands.sdk.event.llm_convertible.message.MessageEvent';
  const full = await events.search({ kind: qualified });
  assert.deepEqual(full.items.map((e) => [e.kind, e.source]), [['MessageEvent', 'user']]);
  assert.equal(await events.count({ kind: qualified }), 1);
  const short = (await events.search({ kind: 'MessageEvent' })).items.map((e) => e.id);
  writeFileSync(`${F34}/kind.json`, JSON.stringify({ full: full.items.map((e) => e.id), short,
    short_count: await events.count({ kind: 'MessageEvent' }) }));
  console.log('QA_F34_KIND_READ');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_KIND_READ --save F34.events-search-kind/program -- node "$F34/kind.mjs" "$SCID"
  cat "$F34/kind.json"
  control-agent-server assert --json "$F34/kind.json" --check short len-eq 1 --check short.0 eq "$(jq -r '.full[0]' "$F34/kind.json")" --check short_count eq 1
  ```
  短名找到相同的消息并计数 `1`。
- **节点 WebSocket (`F34.event-stream`) 上的事件流。**重播、通过套接字发送的回合以及错误的密钥。

  需要：`F34.conversation-create`
  ```sh
  TOTAL=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  cat > "$F34/stream.mjs" <<'JS'
  import { m, c, host, apiKey, assert, waitFor } from './lib.mjs';
  const [cid, total] = process.argv.slice(2);
  const stored = (await new m.RemoteEventsList({ baseUrl: host, apiKey }, cid).getEvents()).map((e) => e.id);
  assert.equal(stored.length, Number(total));
  const url = c.buildConversationEventStreamUrl(host, cid);
  assert.equal(url, `${host.replace('http', 'ws')}/sockets/events/${cid}`);
  const frames = [];
  let state = {};
  const stream = new c.ConversationEventStream({ url, sessionApiKey: apiKey, queryParams: { resend_mode: 'all' },
    onMessage: (frame) => frames.push(JSON.parse(frame.data)), onStateChange: (next) => { state = next; } });
  assert.throws(() => stream.send('{}'), /not open/);
  stream.start();
  await waitFor(() => state.isConnected, 10000, 50);
  await waitFor(() => { const seen = new Set(frames.map((f) => f.id)); return stored.every((id) => seen.has(id)); }, 15000, 100);
  stream.send(JSON.stringify({ role: 'user', content: [{ type: 'text', text: 'qa-f34-stream: reply with the single word ok, then finish.' }] }));
  const sent = await waitFor(() => frames.findIndex((f) => f.kind === 'MessageEvent' && f.source === 'user' &&
    JSON.stringify(f).includes('qa-f34-stream')) + 1, 15000, 100);
  await waitFor(() => frames.slice(sent).some((f) => f.kind === 'ConversationStateUpdateEvent' &&
    f.key === 'execution_status' && f.value === 'finished'), 240000, 250);
  stream.stop();
  assert.equal(state.isConnected, false);
  const errors = [];
  const bad = new c.ConversationEventStream({ url, sessionApiKey: 'qa-f34-wrong-key',
    onStateChange: (next) => { if (next.error) errors.push(next.error.message); } });
  bad.start();
  await waitFor(() => errors.length, 10000, 50);
  bad.stop();
  assert.equal(errors[0], 'WebSocket closed with code 4001: Authentication failed');
  const leaky = new c.ConversationEventStream({ url: `${url}?session_api_key=${apiKey}`,
    onStateChange: (next) => { if (next.error) errors.push(next.error.message); } });
  leaky.start();
  leaky.stop();
  assert.equal(errors.at(-1), 'Use sessionApiKey for first-frame authentication, not URL credentials');
  console.log('QA_F34_STREAM_OK');
  JS
  control-agent-server exec --timeout 300 --expect-output QA_F34_STREAM_OK --save F34.event-stream/program -- node "$F34/stream.mjs" "$CID" "$TOTAL"
  control-agent-server api GET "/api/conversations/$CID/events/search" --query body=qa-f34-stream --check items len-ge 1 \
    --check items.0.source eq user --save F34.event-stream/message
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check execution_status eq finished
  control-agent-server api GET "/api/conversations/$CID/events/count" --query source=user --check . eq 2
  ```
  `send` 在套接字打开之前抛出； 一旦打开，所有存储的事件ID（通过`RemoteEventsList`读取）都会被重播，发送的消息会以用户`MessageEvent`的形式返回，运行它会到达`finished`相同的套接字。 错误的键结尾为
  `WebSocket closed with code 4001: Authentication failed`，并且URL中的密钥在连接之前被拒绝。 REST 显示第二条用户消息
  `finished`.
- **来自节点 (`F34.ws-callback-client`) 的会话回调套接字。**
  `RemoteConversation.startWebSocketClient()` 使用的 `WebSocketCallbackClient` 与 Node 的全局 `WebSocket` 连接，并在连接时间 (`clients/typescript/src/events/global-websocket.ts`) 中查找。 服务器向每个新订阅者发送状态快照，如 CLI 首先显示的
  `SCID`（阳性对照）； 然后程序给客户端 10 秒的时间并记录它看到的事件类型和错误。
  ```sh
  control-agent-server ws listen "/sockets/events/$SCID" --expect-kind ConversationStateUpdateEvent --duration 3 --save F34.ws-callback-client/cli
  cat > "$F34/callback.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, sleep } from './lib.mjs';
  const events = [];
  const errors = [];
  const conversation = new m.RemoteConversation(new m.Agent({ llm: { model: 'qa-f34/unused' } }),
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/x' }),
    { conversationId: process.argv[2], callback: (e) => events.push(e), onError: (e) => errors.push(e.message) });
  await conversation.start();
  await conversation.startWebSocketClient();
  const seen = () => events.some((e) => e.kind === 'ConversationStateUpdateEvent');
  for (const end = Date.now() + 10000; Date.now() < end && !seen();) await sleep(100);
  await conversation.close();
  writeFileSync(`${F34}/callback.json`, JSON.stringify({ kinds: [...new Set(events.map((e) => e.kind))], errors: [...new Set(errors)] }));
  console.log('QA_F34_CALLBACK_DONE');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_CALLBACK_DONE --save F34.ws-callback-client/program -- node "$F34/callback.mjs" "$SCID"
  cat "$F34/callback.json"
  control-agent-server assert --json "$F34/callback.json" --check kinds contains ConversationStateUpdateEvent --check errors len-eq 0
  ```
  预期：快照到达对话回调和 `onError`
  从来没有打电话过。
- **标题和确认政策(`F34.conversation-controls`)。**两个突变，每个突变都读回REST； 政策已恢复。

  需要：`F34.conversation-create`
  ```sh
  cat > "$F34/controls.mjs" <<'JS'
  import { m, host, apiKey, assert } from './lib.mjs';
  const conversation = new m.RemoteConversation(new m.Agent({ llm: { model: 'qa-f34/unused' } }),
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/x' }), { conversationId: process.argv[2] });
  await conversation.start();
  await conversation.setTitle('qa-f34-title');
  await conversation.setConfirmationPolicy({ kind: 'AlwaysConfirm' });
  assert.deepEqual((await conversation.state.refresh()).confirmation_policy, { kind: 'AlwaysConfirm' });
  console.log('QA_F34_CONTROLS_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_CONTROLS_OK --save F34.conversation-controls/program -- node "$F34/controls.mjs" "$CID"
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check title eq qa-f34-title \
    --check confirmation_policy.kind eq AlwaysConfirm --save F34.conversation-controls/server
  control-agent-server api POST "/api/conversations/$CID/confirmation_policy" --json '{"policy": {"kind": "NeverConfirm"}}' --expect 200
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check confirmation_policy.kind eq NeverConfirm
  ```
  服务器报告了新的标题和 `AlwaysConfirm`。 REST恢复`NeverConfirm`放回去。
- **对话管理器 (`F34.manager`).**列出、查找、加载、创建和删除。

  需要：`F34.conversation-create`
  ```sh
  COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  FINISHED=$(control-agent-server api GET /api/conversations/count --query status=finished --field .)
  cat > "$F34/manager.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, NOPE, assert } from './lib.mjs';
  const [cid, scid, count, finished] = process.argv.slice(2);
  const manager = new m.ConversationManager({ host, apiKey });
  assert.equal(await manager.countConversations(), Number(count));
  assert.equal(await manager.countConversations({ status: 'finished' }), Number(finished));
  const first = await manager.searchConversations({ limit: 1 });
  assert.equal(first.items.length, 1);
  assert.ok(first.next_page_id);
  assert.deepEqual((await manager.getAllConversations()).map((x) => x.id).sort(), [cid, scid].sort());
  assert.deepEqual((await manager.getConversations([cid, NOPE, scid])).map((x) => x && x.id), [cid, null, scid]);
  assert.equal((await manager.getConversation(cid)).execution_status, 'finished');
  const loaded = await manager.loadConversation(cid);
  assert.equal(loaded.id, cid);
  assert.equal(loaded.workspace.workingDir, `${F34}/work`);
  await assert.rejects(manager.loadConversation(NOPE), (e) => e.status === 404);
  const created = await manager.createConversation(new m.Agent({ llm: { model: 'qa-f34/unreachable' } }), { workingDir: `${F34}/scoped` });
  assert.equal((await manager.getConversation(created.id)).execution_status, 'idle');
  assert.equal(await manager.countConversations(), Number(count) + 1);
  await manager.deleteConversation(created.id);
  await assert.rejects(manager.getConversation(created.id), (e) => e.status === 404);
  writeFileSync(`${F34}/deleted-id`, created.id);
  console.log('QA_F34_MANAGER_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_MANAGER_OK --save F34.manager/program -- node "$F34/manager.mjs" "$CID" "$SCID" "$COUNT" "$FINISHED"
  control-agent-server api GET "/api/conversations/$(cat "$F34/deleted-id")" --expect 404 --save F34.manager/deleted
  control-agent-server api GET /api/conversations/count --check . eq "$COUNT"
  ```
  计数匹配 REST，第一页的第一个页面有 `next_page_id`
  `getAllConversations` 翻阅了两段对话，批次保持输入顺序为  `null` 对于未知的 id，加载的会话携带其服务器工作目录，且创建的对话在删除后就消失了（404，倒数回去） `COUNT`).
- **更新结果（`F34.manager-update-result`).**  `PATCH /api/conversations/{id}` 答案 `Success` (`{"success": true}`，也在客户端生成的合约中），所以 `ConversationManager.updateConversation` 和 `ConversationClient.updateConversation` 重读对话后 PATCH 并用更新后的解决 `ConversationInfo` 它们被设计成返回。 程序检查标题是否已存储（正控，也通过） REST记录调用的结果。
  ```sh
  cat > "$F34/update.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const scid = process.argv[2];
  const manager = new m.ConversationManager({ host, apiKey });
  const result = await manager.updateConversation(scid, { title: 'qa-f34-renamed' });
  assert.equal((await manager.getConversation(scid)).title, 'qa-f34-renamed');
  writeFileSync(`${F34}/update.json`, JSON.stringify(result));
  console.log('QA_F34_UPDATE_READ');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_UPDATE_READ --save F34.manager-update-result/program -- node "$F34/update.mjs" "$SCID"
  control-agent-server api GET "/api/conversations/$SCID" --max-chars 300 --check title eq qa-f34-renamed
  cat "$F34/update.json"
  control-agent-server assert --json "$F34/update.json" --check id eq "$SCID" --check title eq qa-f34-renamed
  ```
  预期：存储的标题和带有对话的 `ConversationInfo`
  `id` 和新标题。
- **创建选项 (`F34.manager-create-options`)。**
  `ConversationManager.createConversation` 转发 `maxIterations` 并
  `stuckDetection`到`start()`，所以服务器存储调用者的
  `max_iterations`和`stuck_detection`，同
  `RemoteConversation.start({maxIterations, stuckDetection})`，程序首先检查（阳性对照）。 它记录服务器为经理的对话存储的内容，删除两个对话，并 REST 确认它们已经消失。
  ```sh
  cat > "$F34/create-options.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const manager = new m.ConversationManager({ host, apiKey });
  const agent = new m.Agent({ llm: { model: 'qa-f34/unreachable' } });
  const direct = new m.RemoteConversation(agent, new m.RemoteWorkspace({ host, apiKey, workingDir: `${F34}/scoped` }));
  await direct.start({ maxIterations: 7, stuckDetection: false });
  const control = await manager.getConversation(direct.id);
  await manager.deleteConversation(direct.id);
  assert.deepEqual([control.max_iterations, control.stuck_detection], [7, false]);
  const created = await manager.createConversation(agent, { workingDir: `${F34}/scoped`, maxIterations: 7, stuckDetection: false });
  const info = await manager.getConversation(created.id);
  await manager.deleteConversation(created.id);
  writeFileSync(`${F34}/create-options.json`, JSON.stringify({ ids: [direct.id, created.id],
    max_iterations: info.max_iterations, stuck_detection: info.stuck_detection }));
  console.log('QA_F34_CREATE_OPTIONS_READ');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_CREATE_OPTIONS_READ --save F34.manager-create-options/program -- node "$F34/create-options.mjs"
  for ID in $(jq -r '.ids[]' "$F34/create-options.json"); do control-agent-server api GET "/api/conversations/$ID" --expect 404; done
  cat "$F34/create-options.json"
  control-agent-server assert --json "$F34/create-options.json" --check max_iterations eq 7 --check stuck_detection eq false
  ```
  预期：`max_iterations` 7 和 `stuck_detection: false`，作为
  直接`start()`获取。 两条对话均被删除。
- **ACP对话(`F34.manager-acp`)。** `ConversationManager.acp` 与内联ACP Codex 智能体 F12 使用； ACP 子进程仅在第一次运行时启动，因此不会运行任何内容，也不需要 Codex 二进制文件。
  ```sh
  COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  mkdir -p "$F34/acp"
  cat > "$F34/acp.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, NOPE, assert } from './lib.mjs';
  const count = Number(process.argv[2]);
  const manager = new m.ConversationManager({ host, apiKey });
  const agent = { kind: 'ACPAgent', acp_command: ['codex-acp'], acp_server: 'codex' };
  const created = await manager.acp.createConversation(agent, { workingDir: `${F34}/acp`, maxIterations: 9 });
  writeFileSync(`${F34}/acp-id`, created.id);
  assert.deepEqual([created.agent.kind, created.agent.acp_server, created.max_iterations], ['ACPAgent', 'codex', 9]);
  const got = await manager.acp.getConversation(created.id);
  assert.deepEqual(got.agent.acp_command, ['codex-acp']);
  assert.equal(got.workspace.working_dir, `${F34}/acp`);
  assert.deepEqual((await manager.acp.getConversations([created.id, NOPE])).map((x) => x && x.agent.kind), ['ACPAgent', null]);
  assert.ok((await manager.acp.getAllConversations()).some((x) => x.id === created.id && x.agent.kind === 'ACPAgent'));
  assert.equal(await manager.acp.countConversations(), count + 1);
  assert.equal((await manager.acp.searchConversations({ limit: 100 })).items.filter((x) => x.agent.kind === 'ACPAgent').length, 1);
  console.log('QA_F34_ACP_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_ACP_OK --save F34.manager-acp/program -- node "$F34/acp.mjs" "$COUNT"
  ACPID=$(cat "$F34/acp-id")
  control-agent-server api GET "/api/conversations/$ACPID" --max-chars 300 --check agent.kind eq ACPAgent --check agent.acp_server eq codex \
    --check max_iterations eq 9 --check execution_status eq idle --save F34.manager-acp/server
  control-agent-server api DELETE "/api/conversations/$ACPID" --expect 200
  control-agent-server api GET /api/conversations/count --check . eq "$COUNT"
  ```
  命名空间会创建与 ACP 智能体的对话
  `max_iterations` 9（不同于 `createConversation`，它转发选项），以及 get、批量 get (`null` 对于未知 id）、list、count 和 search 都会以 ACP 字段的形式返回。 REST 同意，并且删除将计数恢复。
- **分叉、导航和询问 (`F34.conversation-branching`)。**在`CID`上，完成DeepSeek对话； 叉子最后被删除。

  需要：`F34.conversation-create`
  ```sh
  TOTAL=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  cat > "$F34/branching.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const [cid, total] = process.argv.slice(2);
  const conversation = new m.RemoteConversation(new m.Agent({ llm: { model: 'qa-f34/unused' } }),
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/x' }), { conversationId: cid });
  await conversation.start();
  const fork = await conversation.fork({ title: 'qa-f34-fork' });
  writeFileSync(`${F34}/fork-id`, fork.id);
  assert.ok(fork instanceof m.RemoteConversation && fork.id !== cid);
  assert.equal(fork.workspace.conversationId, fork.id);
  assert.equal(fork.workspace.workingDir, `${F34}/work`);
  assert.equal(fork.agent.llm.model, 'deepseek/deepseek-flash');
  assert.equal(await fork.state.events.count(), Number(total));
  const before = await fork.state.refresh();
  assert.equal(before.title, 'qa-f34-fork');
  const [first] = (await fork.state.events.search({ limit: 1 })).items;
  assert.notEqual(before.leaf_event_id, first.id);
  await fork.navigateTo(first.id);
  assert.equal((await fork.state.modelDump()).leaf_event_id, first.id);
  writeFileSync(`${F34}/fork-leaf`, first.id);
  assert.equal(typeof (await conversation.askAgent('In one short sentence: which file did you create?')), 'string');
  assert.equal(await conversation.state.events.count(), Number(total));
  console.log('QA_F34_BRANCHING_OK');
  JS
  control-agent-server exec --timeout 180 --expect-output QA_F34_BRANCHING_OK --save F34.conversation-branching/program -- node "$F34/branching.mjs" "$CID" "$TOTAL"
  FORK=$(cat "$F34/fork-id")
  control-agent-server api GET "/api/conversations/$FORK" --max-chars 300 --check forked_from_conversation_id eq "$CID" \
    --check title eq qa-f34-fork --check leaf_event_id eq "$(cat "$F34/fork-leaf")" --save F34.conversation-branching/fork
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check execution_status eq finished --check leaf_event_id ne "$(cat "$F34/fork-leaf")"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$TOTAL"
  control-agent-server api DELETE "/api/conversations/$FORK" --expect 200
  ```
  `fork` 返回绑定到 fork 的 `RemoteConversation`：它自己的 id、在源的工作目录中限定其范围的工作区、源的智能体模型以及所有 `TOTAL` 复制的事件。 对于之前缓存的状态，`navigateTo(<first event>)` 将缓存的状态保留在新的 HEAD 上，GET 确认了这一点（源的 HEAD 没有移动）。 `askAgent` 使用字符串进行解析，并且不向源添加任何事件，该源仍然是
  `finished`.
- **确认和机密 (`F34.conversation-confirm`).**与 `AlwaysConfirm` 下的 `terminal` 工具进行 DeepSeek 对话； 两个运行时机密（一个字符串和一个函数值），其哈希值是第一个命令写入的。 程序接受第一个任务的所有提案，直到智能体完成，然后拒绝第二个任务的提案（一个真正的模型被要求重试一个被拒绝的命令经常拒绝，所以拒绝在最后）。 它只等待状态和观测结果计数，而不等待模型的措辞。
  ```sh
  export QA_F34_SECRET="qa-f34-secret-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  mkdir -p "$F34/confirm"
  cat > "$F34/confirm.mjs" <<'JS'
  import { writeFileSync } from 'node:fs';
  import { m, host, apiKey, F34, assert, waitFor } from './lib.mjs';
  const secret = process.env.QA_F34_SECRET;
  const REJECT = 'openhands.sdk.event.llm_convertible.observation.UserRejectObservation';
  const OBSERVATION = 'openhands.sdk.event.llm_convertible.observation.ObservationEvent';
  const agent = new m.Agent({
    llm: { model: 'deepseek/deepseek-flash', api_key: process.env.DEEPSEEK_API_KEY, usage_id: 'agent' },
    tools: [{ name: 'terminal' }],
  });
  const conversation = new m.RemoteConversation(agent, new m.RemoteWorkspace({ host, apiKey, workingDir: `${F34}/confirm` }));
  await conversation.start({ maxIterations: 20 });
  writeFileSync(`${F34}/confirm-id`, conversation.id);
  await conversation.setConfirmationPolicy({ kind: 'AlwaysConfirm' });
  await conversation.updateSecrets({ QA_F34_TOKEN: secret, QA_F34_TOKEN_FN: () => `${secret}-fn` });
  const settled = (wanted) => waitFor(async () => {
    const status = (await conversation.state.refresh()).execution_status;
    if (['error', 'stuck'].includes(status)) throw new Error(`conversation ${status}`);
    return wanted.includes(status) && status;
  }, 240000, 500);
  const observations = () => conversation.state.events.count({ kind: OBSERVATION });
  const command = 'printf %s "$QA_F34_TOKEN" | sha256sum | cut -c1-16 > qa-f34-confirm.txt; ' +
    'printf %s "$QA_F34_TOKEN_FN" | sha256sum | cut -c1-16 >> qa-f34-confirm.txt';
  await conversation.sendMessage(`Use the terminal tool to run exactly this one command, then finish: ${command}`);
  await conversation.run();
  let accepted = 0;
  while ((await settled(['waiting_for_confirmation', 'finished'])) === 'waiting_for_confirmation' && accepted < 8) {
    const observed = await observations();
    await conversation.sendConfirmationResponse(true);
    accepted += 1;
    await waitFor(async () => (await observations()) > observed, 120000, 500);
  }
  assert.ok(accepted >= 1, 'the agent never asked for confirmation');
  assert.equal((await conversation.state.refresh()).execution_status, 'finished');
  const before = await observations();
  await conversation.sendMessage('Use the terminal tool to run exactly this one command, then finish: echo qa-f34-rejected > qa-f34-rejected.txt');
  await conversation.run();
  assert.equal(await settled(['waiting_for_confirmation', 'finished']), 'waiting_for_confirmation');
  await conversation.sendConfirmationResponse(false, 'qa-f34 rejected');
  assert.equal(await settled(['idle']), 'idle');
  const rejected = await conversation.state.events.search({ kind: REJECT });
  assert.deepEqual(rejected.items.map((e) => e.rejection_reason), ['qa-f34 rejected']);
  assert.equal(await observations(), before);
  console.log('QA_F34_CONFIRM_OK');
  JS
  control-agent-server exec --timeout 600 --env QA_F34_SECRET="$QA_F34_SECRET" --expect-output QA_F34_CONFIRM_OK \
    --save F34.conversation-confirm/program -- node "$F34/confirm.mjs"
  CFID=$(cat "$F34/confirm-id")
  control-agent-server api GET "/api/conversations/$CFID" --max-chars 300 --check execution_status eq idle \
    --check confirmation_policy.kind eq AlwaysConfirm --save F34.conversation-confirm/server
  control-agent-server api GET "/api/conversations/$CFID/events/search" \
    --query kind=openhands.sdk.event.llm_convertible.observation.UserRejectObservation \
    --check items len-eq 1 --check items.0.rejection_reason eq 'qa-f34 rejected' --check items.0.tool_name eq terminal \
    --save F34.conversation-confirm/rejected
  control-agent-server conversation events "$CFID" --kinds ActionEvent --contains qa-f34-rejected.txt --expect-min 1
  test ! -e "$F34/confirm/qa-f34-rejected.txt"
  test "$(wc -l < "$F34/confirm/qa-f34-confirm.txt")" -eq 2
  test "$(sed -n 1p "$F34/confirm/qa-f34-confirm.txt")" = "$(printf %s "$QA_F34_SECRET" | sha256sum | cut -c1-16)"
  test "$(sed -n 2p "$F34/confirm/qa-f34-confirm.txt")" = "$(printf %s "$QA_F34_SECRET-fn" | sha256sum | cut -c1-16)"
  control-agent-server conversation events "$CFID" --kinds ActionEvent --contains QA_F34_TOKEN_FN --expect-min 1
  control-agent-server conversation events "$CFID" --contains "$QA_F34_SECRET" --expect-count 0
  control-agent-server state grep --env-value QA_F34_SECRET --glob 'server/**/*' --expect-none
  control-agent-server state grep --env-value QA_F34_SECRET --glob 'home/**/*' --expect-none
  ```
  每条接受都会运行 pending 命令和智能体完成； 文件包含16个字符 SHA-256 个前缀机密值，所以字符串和函数值都到达了shell，而提案只提到变量：没有事件，没有文件的服务器已持久化包含值。 第二项提案等待确认。 拒绝记录一条 `UserRejectObservation` 与 `qa-f34 rejected` (REST 同意：终端工具），运行什么（没有新的观测结果，no
  `qa-f34-rejected.txt`) 并离开对话 `idle`。
- **挂钩 (`F34.hooks-client`).**项目挂钩 `HooksClient` 和
  `RemoteConversation.loadHooks`.

  需要：`F34.conversation-create`
  ```sh
  cat > "$F34/hooks.mjs" <<'JS'
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const [cid, project] = process.argv.slice(2);
  const hooks = new m.HooksClient({ host, apiKey });
  const { hook_config: config } = await hooks.loadHooks({ project_dir: project });
  assert.ok(m.hasHooksForEvent(config, m.HookEventType.PRE_TOOL_USE));
  assert.ok(!m.hasHooksForEvent(config, m.HookEventType.STOP));
  assert.deepEqual(m.getHooksForEvent(config, m.HookEventType.PRE_TOOL_USE, 'terminal').map((h) => h.command), ['echo QA_PROJECT_HOOK']);
  assert.deepEqual(await hooks.loadHooks({ project_dir: `${F34}/files` }), { hook_config: null });
  const conversation = new m.RemoteConversation(new m.Agent({ llm: { model: 'qa-f34/unused' } }),
    new m.RemoteWorkspace({ host, apiKey, workingDir: '/x' }), { conversationId: cid });
  await conversation.start();
  assert.deepEqual(await conversation.loadHooks(project), config);
  console.log('QA_F34_HOOKS_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_HOOKS_OK --save F34.hooks-client/program -- node "$F34/hooks.mjs" "$CID" "$PROJECT"
  control-agent-server api POST /api/hooks --json "{\"project_dir\": \"$PROJECT\"}" --expect 200 \
    --check hook_config.pre_tool_use.0.hooks.0.command eq 'echo QA_PROJECT_HOOK'
  ```
  `PreToolUse` `hooks.json` 的 `pre_tool_use` 条记录被 `hasHooksForEvent` 和 `getHooksForEvent` 读取。 一个没有钩子的目录 `{hook_config: null}`。 `loadHooks` 会话返回相同的配置。
- **MCP测试(`F34.mcp-client`)。** stdio 测试夹具，a 工具调用，一个死掉的服务器和一个坏的身体。
  ```sh
  MCPN=$(control-agent-server api GET /api/settings --field agent_settings.mcp_config | jq length)
  cat > "$F34/mcp.mjs" <<'JS'
  import { m, host, apiKey, assert } from './lib.mjs';
  const script = process.env.AGENT_SERVER_VERIFY_RUN + '/fixtures/mcp/qa-f34-mcp.py';
  const server = { type: 'stdio', command: process.cwd() + '/.venv/bin/python', args: [script] };
  const mcp = new m.MCPClient({ host, apiKey });
  assert.deepEqual(await mcp.testServer({ name: 'qa-f34-mcp', server, timeout: 60 }), { ok: true, tools: ['qa_echo'] });
  const called = await mcp.testServer({ server, timeout: 60, tool_call: { name: 'qa_echo', arguments: { text: 'qa-f34' } } });
  assert.deepEqual(called.tool_result, { is_error: false, text: 'QA_MCP_ECHO:qa-f34' });
  const failed = await mcp.testServer({ server: { type: 'stdio', command: '/bin/false', args: [] }, timeout: 20 });
  assert.equal(failed.ok, false);
  assert.ok(['timeout', 'connection', 'unknown'].includes(failed.error_kind) && failed.error.length > 0);
  await assert.rejects(mcp.testServer({ server: { type: 'stdio', command: '' } }),
    (e) => e.status === 422 && e.detail === 'String should have at least 1 character');
  console.log('QA_F34_MCP_OK');
  JS
  control-agent-server exec --timeout 180 --expect-output QA_F34_MCP_OK --save F34.mcp-client/program -- node "$F34/mcp.mjs"
  control-agent-server api GET /api/settings --max-chars 300 --check agent_settings.mcp_config.qa-f34-mcp missing \
    --check agent_settings.mcp_config len-eq "$MCPN"
  ```
  的测试夹具列表 `qa_echo` 和工具调用返回其文本。 `/bin/false` 这是一个200 `{ok: false}` 与一个 `error_kind`; 空命令为422
  `HttpError` 与验证器的消息。 测试没有任何结果：设置的平面 `mcp_config` 服务器映射没有 `qa-f34-mcp` 条目，并且大小与以前相同。
- **重新启动 (`F34.restart-reload`)。**重新启动，然后是一个新的客户端。

  需要：`F34.conversation-create`
  ```sh
  TOTAL=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server restart
  cat > "$F34/restart.mjs" <<'JS'
  import { m, host, apiKey, F34, assert } from './lib.mjs';
  const [cid, total] = process.argv.slice(2);
  const manager = new m.ConversationManager({ host, apiKey });
  const conversation = await manager.loadConversation(cid);
  assert.equal(await conversation.state.getExecutionStatus(), 'finished');
  assert.equal((await manager.getConversation(cid)).title, 'qa-f34-title');
  assert.equal(await conversation.state.events.count(), Number(total));
  assert.equal((await conversation.getHookConfig()).pre_tool_use[0].hooks[0].command, 'echo qa-f34-hook');
  assert.equal((await conversation.workspace.downloadAsText(`${F34}/work/qa-f34.txt`)).trim(), 'hi');
  console.log('QA_F34_RESTART_OK');
  JS
  control-agent-server exec --timeout 60 --expect-output QA_F34_RESTART_OK --save F34.restart-reload/program -- node "$F34/restart.mjs" "$CID" "$TOTAL"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$TOTAL"
  ```
  重启后，对话仍然 `finished`，标题，所有 `TOTAL` 事件，钩子配置，以及智能体的文件。
- **事件流重新连接 (`F34.event-stream-reconnect`)。**一个
  `ConversationEventStream` 与 `reconnect: {enabled: true}` 和
  `resend_mode: 'all'`，在`ws`包的构造器(`createWebSocket`，用于没有可用的原生套接字的环境的适配器)中，监视自己的对话，该对话从不运行。 观察者来自
  `Preconditions:`在后台运行； 一旦流重播了排队的消息，CLI 就会重新启动服务器并发布第二条消息 (`run: false`)。
  ```sh
  RCID=$(control-agent-server conversation start --no-run --placeholder-agent --tools none --no-autotitle --workspace "$F34/scoped" \
    --prompt 'qa-f34-reconnect: never run' --print-id)
  rm -f "$F34/reconnect-ready"
  control-agent-server exec --timeout 300 --expect-output QA_F34_RECONNECT_WATCHED --save F34.event-stream-reconnect/program \
    -- node "$F34/reconnect.mjs" "$RCID" "$F34/reconnect-ws.json" ws &
  RPID=$!
  for _ in $(seq 150); do if [ -e "$F34/reconnect-ready" ]; then break; fi; sleep 0.2; done
  test -e "$F34/reconnect-ready"
  control-agent-server restart
  control-agent-server api POST "/api/conversations/$RCID/events" \
    --json '{"role": "user", "content": [{"type": "text", "text": "qa-f34-after-restart"}], "run": false}' --expect 200
  wait "$RPID"
  cat "$F34/reconnect-ws.json"
  jq -e '.ws | .went_down and .attempts >= 1 and .reconnected and .replayed_after >= 1 and .sent_after >= 1' "$F34/reconnect-ws.json"
  control-agent-server api GET "/api/conversations/$RCID/events/count" --query source=user --check . eq 2 --save F34.event-stream-reconnect/server
  control-agent-server api GET "/api/conversations/$RCID" --max-chars 300 --check execution_status eq idle
  ```
  重启会关闭套接字 (1012)，并让流自动重连。 拒绝的尝试以1006关闭，并且会回退（1, 2, 4, 8秒加上抖动）直到服务器恢复，然后重新连接。 `resend_mode=all` 重连发送了，因此队列中的消息被重新发送到新的套接字上，重启后发布的消息也到达了它（如果是活的，或者在重播中）。 REST 显示了用户消息以及对话仍然 `idle`。
- **在节点自身上重连 WebSocket (`F34.event-stream-reconnect-native`), 已知 bug。** 两个流并排重启： `ws`-backed 的一个（正控）和一个在节点全局 `WebSocket` 上的
  `F34.event-stream` 使用并且 README 呈现为所有流需求。 此回归配方固定节点 22.22.0 (undici 6.23.0)，[upstream #5651](https://github.com/OpenHands/software-agent-sdk/issues/5651) 中受影响的运行时； 主要消费者通道可以使用机器当前的Node。 预热会在观察者准备就绪超时开始之前记录版本。 在此 Node 版本中，与拒绝触发的端口握手
  `error` 但从不 `close`，并且流仅调度其重试
  from `onclose` (`clients/typescript/src/client/conversation-event-stream.ts:145`);
  它自己的 10 秒握手中止仅调用 `close()`，这不会触发
  `close` 要么。 因此，重新启动期间第一个被拒绝的尝试是最后一个。
  ```sh
  control-agent-server exec --timeout 120 --expect-output v22.22.0 --save F34.event-stream-reconnect-native/runtime -- \
    npm exec --yes --package=node@22.22.0 -- node --version
  RNID=$(control-agent-server conversation start --no-run --placeholder-agent --tools none --no-autotitle --workspace "$F34/scoped" \
    --prompt 'qa-f34-reconnect: never run' --print-id)
  rm -f "$F34/reconnect-ready"
  control-agent-server exec --timeout 300 --expect-output QA_F34_RECONNECT_WATCHED --save F34.event-stream-reconnect-native/program \
    -- npm exec --yes --package=node@22.22.0 -- node "$F34/reconnect.mjs" "$RNID" "$F34/reconnect-native.json" ws native &
  RPID=$!
  for _ in $(seq 150); do if [ -e "$F34/reconnect-ready" ]; then break; fi; sleep 0.2; done
  test -e "$F34/reconnect-ready"
  control-agent-server restart
  control-agent-server api POST "/api/conversations/$RNID/events" \
    --json '{"role": "user", "content": [{"type": "text", "text": "qa-f34-after-restart"}], "run": false}' --expect 200
  wait "$RPID"
  cat "$F34/reconnect-native.json"
  jq -e '.ws.reconnected and .ws.sent_after >= 1 and .native.went_down' "$F34/reconnect-native.json"
  control-agent-server assert --json "$F34/reconnect-native.json" --check native.reconnected eq true --check native.sent_after ge 1  # 错误：value.native.reconnected eq False && value.native.last_state.attemptCount eq 1
  ```
  预期：两个流都会返回并看到在
  重新启动。 在 Node 22.22.0 上，`ws` 支持的流会执行此操作，而本机流则保留
  `{"isConnected": false, "isReconnecting": true, "attemptCount": 1}` 观察者在整个分钟内给出它，从不重试。 节点 24.19.0 (undici 7.29.0) 在握手错误后发出 `close`，因此 BASE 和 TARGET 都以字节相同的客户端代码传递到那里； 该环境结果不会使 Node 22 退役回归。
- **端点对此结帐进行审核 (`F34.endpoint-audit`)。**客户端自己的漂移工具，离线，位于测试夹具目录中（没有任何内容写入 `clients/typescript`）。
  ```sh
  A="$F34/audit"
  mkdir -p "$A/home"
  HOME="$A/home" OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python .github/scripts/export_agent_server_openapi.py --output "$A/openapi.json" > "$A/export.log" 2>&1
  jq -e '.paths["/api/conversations"].post and .paths["/api/bash/execute_bash_command"].post' "$A/openapi.json" > /dev/null
  for f in package.json src .prettierrc; do ln -sfn "$PWD/clients/typescript/$f" "$A/$f"; done
  rm -f "$A/endpoint-audit.config.json"
  jq '.allowClientOnly |= map(select(.endpoints | index("GET /alive")))' clients/typescript/endpoint-audit.config.json > "$A/endpoint-audit.config.json"
  control-agent-server exec --cwd "$A" --env AGENT_SERVER_OPENAPI_PATH="$A/openapi.json" --timeout 120 \
    --expect-output 'endpoint audit passed' --save F34.endpoint-audit/audit -- node "$PWD/clients/typescript/scripts/endpoint-audit.mjs"
  jq -e '.clientOnly == [] and .client > 100' "$A/.audit/endpoint-audit.json"
  jq -e '[.allowedClientOnly[].endpoint] == ["GET /", "GET /alive", "GET /health", "GET /ready", "GET /server_info"]' "$A/.audit/endpoint-audit.json"
  jq -r '.serverOnly[]' "$A/.audit/endpoint-audit.json" > "$A/server-only.txt"
  control-agent-server exec --env AGENT_SERVER_OPENAPI_PATH="$A/openapi.json" --env AGENT_SERVER_GENERATED_OUTPUT="$A/agent-server-schema.ts" \
    --timeout 180 --save F34.endpoint-audit/generate -- node clients/typescript/scripts/generate-agent-server-api.mjs
  node clients/typescript/scripts/summarize-agent-server-api.mjs --before clients/typescript/src/generated/agent-server-schema.ts \
    --after "$A/agent-server-schema.ts" --output "$A/summary.md"
  grep -Eqx 'No generated TypeScript contract changes\.|- Removed exported types: none' "$A/summary.md"
  ```
  `.github/scripts/export_agent_server_openapi.py` 编写与未发布版本相同的公共合约 CI。 审计运行时带有以下副本
  `endpoint-audit.config.json` `allowClientOnly` 只保留了公共合同遗漏的五条运营路线(F01 证明了它们)，因此其客户端前置异常（元配置、配置验证）也被检查。 仅报告门在仅客户端调用上永远不会失败，这就是配方在 JSON 本身上断言 `clientOnly == []` 的原因。 它报告没有仅限客户端的呼叫（此结账时存在每个手写呼叫）；
  `server-only.txt` 列出了没有文字客户端调用的操作（基线上的 43：会话范围的 bash、文件、git 和 VS Code 别名，客户端通过在运行时重写路径来到达）、画布扩展路由、其后端调用帮助程序构建、提供程序连接、`/api/init`、`GET .../events` 批处理、存档、提交、
  `create_directory` 和 `load_plugin`）。 重新生成客户端的类型
  from this checkout removes no exported type (on the baseline the diff is
  `+13 / -1`lines：画布后端工件的两个新字段）。
- **旧服务器版本(`F34.version-gate-old`)。** Agent Server 的真实 1.22.0 版本，与 `uvx` 一起安装，附加并停止在子弹内部。 FastAPI 固定到中的版本
  [v1.22.0 release lock](https://github.com/OpenHands/software-agent-sdk/blob/v1.22.0/uv.lock):
  在测试版本控制行为之前，较新的 FastAPI 版本会在导入期间拒绝历史服务器的 `Query(lte=...)`。
  ```sh
  OLD="$F34/old-server"
  mkdir -p "$OLD/home" "$OLD/persist"
  OLDPORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  (cd "$OLD" && HOME="$OLD/home" OH_PERSISTENCE_DIR="$OLD/persist" OH_SESSION_API_KEYS_0=qa-f34-old-key COLUMNS=400 exec timeout 600 \
    uvx --python 3.13 --from 'openhands-agent-server==1.22.0' --with 'openhands-sdk==1.22.0' --with 'openhands-tools==1.22.0' \
    --with 'openhands-workspace==1.22.0' --with 'fastapi==0.129.0' python -m openhands.agent_server --host 127.0.0.1 --port "$OLDPORT" > "$OLD/server.log" 2>&1) &
  OLDPID=$!
  OLDRUN=""
  trap 'if [ -n "$OLDRUN" ]; then control-agent-server stop --run "$OLDRUN" > /dev/null 2>&1; fi; kill -TERM -- "-$OLDPID" 2>/dev/null || kill -TERM "$OLDPID" 2>/dev/null || true' EXIT
  export QA_F34_OLD_KEY=qa-f34-old-key
  OLDRUN=$(control-agent-server attach --url "http://127.0.0.1:$OLDPORT" --key-env QA_F34_OLD_KEY --name f34-old --print-run)
  curl -s --noproxy '*' --retry 150 --retry-connrefused --retry-delay 2 --retry-max-time 300 -o /dev/null "http://127.0.0.1:$OLDPORT/alive"
  control-agent-server api GET /server_info --run "$OLDRUN" --auth none --expect 200 --check version eq 1.22.0 --save F34.version-gate-old/info
  cat > "$F34/gate-old.mjs" <<'JS'
  import { m, assert } from './lib.mjs';
  const host = process.argv[2];
  const apiKey = process.env.QA_F34_OLD_KEY;
  const old = (min) => (e) => m.isAgentServerVersionError(e) && e.code === 'AGENT_SERVER_VERSION_TOO_OLD' &&
    e.requiredVersion === min && e.actualVersion === '1.22.0' && !m.isHttpError(e);
  await assert.rejects(new m.HooksClient({ host, apiKey }).loadHooks({}), old('1.23.0'));
  await assert.rejects(new m.WorkspacesClient({ host, apiKey }).listWorkspaces(), old('1.23.0'));
  const mcp = new m.MCPClient({ host, apiKey });
  await assert.rejects(mcp.testServer({ server: { type: 'stdio', command: '/bin/true' } }), old('1.23.0'));
  await assert.rejects(mcp.getOAuthStatus('qa-f34-job'), old('1.31.0'));
  const ungated = new m.ConversationManager({ host, apiKey });
  assert.equal(await ungated.countConversations(), 0);
  console.log('QA_F34_GATE_OLD_OK');
  JS
  control-agent-server exec --run "$OLDRUN" --timeout 60 --env QA_F34_OLD_KEY=qa-f34-old-key --expect-output QA_F34_GATE_OLD_OK \
    --save F34.version-gate-old/program -- node "$F34/gate-old.mjs" "http://127.0.0.1:$OLDPORT"
  grep -q '"GET /server_info HTTP' "$OLD/server.log"
  grep -q '"GET /api/conversations/count HTTP' "$OLD/server.log"
  if grep -Eq '/api/hooks|/api/workspaces|/api/mcp/' "$OLD/server.log"; then false; fi
  control-agent-server stop --run "$OLDRUN"
  kill -TERM -- "-$OLDPID" 2>/dev/null || kill -TERM "$OLDPID"
  trap - EXIT
  ```
  `curl --retry-connrefused` 等待端口（CLI 的 `--until-ok` 不重试拒绝连接）。 旧服务器报告`1.22.0`； 每个门控方法都会拒绝
  `AgentServerVersionError`（`AGENT_SERVER_VERSION_TOO_OLD`，必填
  `1.23.0` 或 `1.31.0`，实际 `1.22.0`），而不是 `HttpError`，而非门控调用仍然有效。 旧服务器的访问日志有
  `/server_info` 探测和计数，但没有门控路线。

<a id="gotchas"></a>

## 陷阱

- 包裹只有 ESM。 导入 `clients/typescript/dist/index.js`（大多数类）和 `dist/clients.js`（`ServerClient`、`FileClient`、
  `ConversationEventStream`, `AgentServerClient`); `ConversationEventStream` 不从主条目导出。 `dist/` 被 git 忽略，并且不会被 `clients/typescript` 中除 `npm run build` 之外的任何东西重建； 过时的构建会默默地验证旧的客户端代码，这就是为什么每当 `src/` 更新时 `Preconditions:` 都会重建。
- 在 Node 中，`ConversationEventStream`、`WebSocketCallbackClient` (`RemoteConversation.startWebSocketClient()`) 和 `BashWebSocketClient` 都使用全局 `WebSocket`（Node 22 或更高版本），在套接字打开时查找。 只有 `ConversationEventStream` 采用构造函数 (`createWebSocket`)； 在较旧的节点上，回调客户端需要将一个分配给 `globalThis.WebSocket`，否则它们会通过 `onError` 报告“WebSocket 实现不可用”。 `WebSocketCallbackClient` 通过 `ConversationEventStream` 重新连接，因此下面的拒绝握手陷阱也适用于它。
- 当节点22的全局`WebSocket`（undici 6）拒绝握手时，`error`，但`close`。因此，`ConversationEventStream`后，它会停止重试（因为服务器重启总是会产生一个）。它会一直`isReconnecting`（`F34.event-stream-reconnect-native`）。 将 `ws` 包的构造函数作为 `createWebSocket` 传递给必须在重新启动后继续存在的 Node 使用者 (`F34.event-stream-reconnect`)。
- 一个显示真实模型的 `UserRejectObservation` 通常拒绝再次提出相同的命令（“故意阻塞”），因此一个需要接受和拒绝的 `F34.conversation-confirm` 首先接受，然后拒绝一个不同的提议。 拒绝后对话是
  `idle`，而不是 `finished`。
- 通过事件套接字发送的消息始终运行智能体（服务器忽略 `run`），与发布 `run: false` 的 `sendMessage` 不同。 不要将套接字帧发送到智能体无法到达模型的会话。
- `RemoteState`缓存`GET /api/conversations/{id}`2秒； 民意调查
  `state.refresh()` 等待状态时。
- `executeCommand` 始终报告 `timeout_occurred: false`； 被自己的超时杀死的命令显示退出 `-1`（服务器不发送超时标记），并且
  当服务器发送None时，`exit_code`为-1。 HTTP 请求等待 `timeout + 10` 秒。
- `executeCommand` 返回服务器的拼接输出：超过1 MiB 的部分会被存储为多个分块服务器端 (`bash.searchEvents` 列表它们)，`execute_bash_command` 连接它们 (`F13.execute-large-output`)。
- `RemoteWorkspace.fileDownload`、`downloadAsBlob` 和 `downloadAsText` 将正文解码为文本 (`F34.workspace-binary-download`)； 使用
  `FileClient.downloadFile` 代表字节。
- `GitChange['status']`（主条目，也导出为`GitChangeStatus`）是服务器的`UPDATED|ADDED|DELETED|MOVED`，而不是小写单词（`F34.workspace-git-types`）。
  `gitChanges` 和 `gitDiff` 将每个拒绝包装在普通的 `Error` 中，因此从 `isHttpError(e.cause)` 而不是从 `e` 读取状态。
- `RemoteEventsList.search`和`count`的`kind`过滤器取裸
  class name or the fully-qualified class path (`F34.events-search-kind`,
  `F06.search-kind-short`).
- 带有 `conversationId` 的 `RemoteWorkspace` 每传输层检查一次 `/server_info`，然后才选择会话范围的路由； 它拒绝带有查询字符串或 `..` 和 `cid` 客户端参数的路径。
- `Agent` 将额外选项复制到请求中，因此 `tools`（以及任何其他智能体字段）可以直接传递； 没有`tools`，服务器智能体有None。 `RemoteConversation.start()` 发送 `max_iterations` 500 和
  `stuck_detection: true` 除非另有说明。
- `PATCH /api/conversations/{id}` 仅回答 `{success: true}`；
  `updateConversation` 用第二个 `GET` (`F34.manager-update-result`) 读回对话。
- 版本门只从`/server_info`读取`version`； 服务器报告 `unknown`（没有包元数据的构建）每个门控调用都失败。 `F34.version-gate-old` 1.22.0 版本需要 PyPI（或缓存的 `uvx` 环境）； 离线时，它会在 `curl` 等待端口处失败。
- 端点审核仅看到 `src/client` 中的文字 `HttpClient` 调用，
  `src/conversation`和`src/workspace`； 对话级别的别名（通过运行时重写路径到达）以及由辅助函数构建的路径调用（`CanvasExtensionsClient`的后端路由）显示为服务器专用。 它将 `.audit/` 写入其工作目录，这就是配方从带有符号链接的测试夹具目录运行它的原因。
- `npm run check:agent-server-api` 生成 `src/generated/` 在原地下载已 pinned 的合约。 该食谱调用生成器 `AGENT_SERVER_GENERATED_OUTPUT` 而是，结账过程中的任何内容都不会改变。 原始的 `/openapi.json` 运行中的服务器的端点不是公共合同（它包括） `/v1` and internal 模式因此，从它重新生成会显示成千上万条无关的更改。
