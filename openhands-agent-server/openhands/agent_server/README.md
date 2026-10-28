# OpenHands Agent Server

OpenHands Agent Server 是一个最小的 REST API 和 WebSocket 服务器，提供用于与 OpenHands AI 智能体交互的编程接口。 它使用本地文件系统来存储对话、事件和工作区文件，使其成为开发、测试和轻量级部署的理想选择。

<a id="features"></a>

## 特点

- **REST API**：对话和事件的完整 CRUD 操作
- **WebSocket支持**：与智能体实时通信
- **本地存储**：基于文件的对话和工作区数据存储
- **CORS支持**：可配置的跨域资源共享
- **身份验证**：可选的基于会话的 API 密钥身份验证
- **Webhook**：可配置的 Webhook 事件通知
- **Auto-reload**：自动代码重新加载的开发模式

<a id="quick-start"></a>

## 快速入门

<a id="prerequisites"></a>

### 先决条件

在启动服务器之前，请确保构建项目并安装依赖项：

```bash
make build
```

<a id="starting-the-server"></a>

### 启动服务器

可以使用 Python 的模块执行来启动服务器：

```bash
# 使用默认设置启动（主机：0.0.0.0，端口：8000）
uv run python -m openhands.agent_server

# 从自定义主机和端口开始
uv run python -m openhands.agent_server --host localhost --port 3000

# 从自动重新加载开始（用于开发）
uv run python -m openhands.agent_server --reload
```

<a id="command-line-options"></a>

### 命令行选项

- `--host`：要绑定的主机（默认值：`0.0.0.0`）
- `--port`：要绑定的端口（默认值：`8000`）
- `--reload`：启用自动重新加载

<a id="configuration"></a>

## 配置

可以使用环境变量或 JSON 配置文件来配置服务器。

<a id="environment-variables"></a>

### 环境变量

| 变量 | 描述 | 默认 |
|----------|-------------|---------|
| `OPENHANDS_AGENT_SERVER_CONFIG_PATH` | JSON 配置文件的路径 | `workspace/openhands_agent_server_config.json` |
| `SESSION_API_KEY` | API 键用于身份验证（可选） | None |
| `OH_SECRET_KEY` | 机密密钥，用于加密存储的对话中的敏感数据（LLM API 密钥，机密）。 **重新启动后持久化需要。**返回到第一个会话 API 键。 | None |
| `OH_PREVIOUS_SECRET_KEYS` | 早期的机密密钥，仅用于解密，作为 JSON 列表（或 `OH_PREVIOUS_SECRET_KEYS_0`、`_1`，...）。 请参阅[旋转钥匙](#rotating-the-key)。 | None |
| `OH_ALLOW_CORS_ORIGIN_REGEX` | 其他允许的 CORS 来源的正则表达式。 使用 `https?://.+` 允许任何 HTTP(S) 原点，同时回显具体原点。 | None |
| `OH_TELEMETRY_EXPORTER` | 事件去向：`none`、`posthog` 或 `http`。 请参阅[遥测](#telemetry)。 | `none` |
| `OH_TELEMETRY_POSTHOG_API_KEY` | PostHog项目API关键。 `posthog` 出口商要求。 | None |
| `OH_TELEMETRY_POSTHOG_HOST` | PostHog摄取主机。 | `https://us.i.posthog.com` |
| `OH_TELEMETRY_HTTP_ENDPOINT` | 端点 `http` 导出 POSTs 清洗批次。 | None |
| `OH_TELEMETRY_HTTP_TOKEN` | 持有者令牌用于 `http` 出口商（如果需要）。 | None |
| `OH_TELEMETRY_CONSENT` | `granted` 或 `denied`。 播种或覆盖已持久化同意值。 | 取消设置 |
| `OH_TELEMETRY_CONSENT_MODE` | `seed`（仅在同意为 `unset` 时适用）或 `override`（胜过设置）。 | `seed` |
| `OH_TELEMETRY_SALT` | 用于对对话 ID 进行假名化的密钥。 回落到 `OH_SECRET_KEY`，然后回落到每个进程的随机盐。 | None |
| `DO_NOT_TRACK` | 将 `1` 设置为强制关闭 telemetry，覆盖同意和环境。 | 取消设置 |

<a id="configuration-file"></a>

### 配置文件

创建 JSON 配置文件（默认值：`workspace/openhands_agent_server_config.json`）：

```json
{
  "session_api_key": "your-secret-api-key",
  "allow_cors_origins": ["https://your-frontend.com"],
  "allow_cors_origin_regex": null,
  "conversations_path": "workspace/conversations",
  "webhooks": [
    {
      "webhook_url": "https://your-webhook-endpoint.com/events",
      "method": "POST",
      "event_buffer_size": 10,
      "num_retries": 3,
      "retry_delay": 5,
      "headers": {
        "Authorization": "Bearer your-webhook-token"
      }
    }
  ]
}
```

<a id="configuration-options"></a>

### 配置选项

- **`session_api_key`**：用于保护服务器的可选 API 密钥。 如果设置，所有请求都必须在 `Authorization` 标头中包含此键作为 `Bearer <key>`
- **`allow_cors_origins`**：允许的 CORS 来源列表（始终允许 localhost）
- **`allow_cors_origin_regex`**：其他允许的 CORS 来源的正则表达式。 使用`https?://.+`允许任何HTTP(S)的来源，同时保持凭据-兼容的来源回显。
- **`webhooks`**：事件通知的 Webhook 个配置数组

**注意**：目录配置（`working_dir`）将在会话级别而不是全局进行处理。 这些目录是在通过 API 开始对话时指定的。

<a id="telemetry"></a>

### 遥测

Agent Server 可以向 PostHog 发出一小组 **product-analytics** 事件。 默认情况下**禁用**，并且除非部署选择加入，否则不会执行任何操作。

<a id="this-is-not-the-same-as-the-other-two-observability-features"></a>

#### 这与其他两个可观察性特征不同

| 特点 | 它收集什么 | 它去哪里 |
|---|---|---|
| **遥测**（本节） | 列入白名单的生命周期/故障事件。 绝不是提示词、消息、文件内容、路径、机密、请求/响应主体或回溯。 | PostHog，配置后 |
| **LLM完成日志记录** (`log_completions`) | 完整提示词、响应和原始提供程序载荷 — 故意提高调试保真度。 | 仅本地磁盘 |
| **层流/OpenTelemetry追踪** | 用于延迟分析的分布式跟踪和跨度。 | 您的 OTel/Laminar 后端 |

完成日志记录或跟踪中的任何内容都不会转发到遥测。

<a id="consent"></a>

#### 同意

没有部署“模式”，智能体-服务器特殊情况下也没有托管部署。 它解决了一件事 - **有效同意** - 并且交付还需要配置导出器。

`misc_settings.telemetry.consent` `granted` | `denied` |
`unset`），带有可选的 `misc_settings.telemetry.managed = true` 将选项标记为管理员管理，以便 UI 可以呈现它只读。 Canvas 像任何其他前端首选项一样通过 `PATCH /api/settings` 写入它：

```
PATCH /api/settings
{"misc_settings_diff": {"telemetry": {"consent": "granted"}}}
```

否则，`misc_settings` 对于智能体服务器来说是不透明的。 **这个命名空间是记录的异常**：前端仍然拥有该值，服务器只读取它。 容器中的任何其他内容都不会被解释。

因为它是普通的 `misc_settings`，同意在免费重新启动后仍然有效，并且不需要更改设置模式。

优先级，最高的在前：

1. `DO_NOT_TRACK=1` — 操作员终止开关，覆盖一切。
2. `OH_TELEMETRY_CONSENT` 当 `OH_TELEMETRY_CONSENT_MODE=override` 时。
3. `misc_settings.telemetry.consent`.
4. 旧的 `misc_settings.app_preferences.user_consents_to_analytics` 键，只读作为回退方案，因此现有用户不会重置。 没写过。
5. `OH_TELEMETRY_CONSENT` 作为种子（默认模式）——仅在已持久化值为 `unset` 时适用，因此运算符默认值永远不会默默地否决显式选择。
6. 否则`unset`，即**不**同意。

撤销在设置请求返回之前生效：传送停止，并且已经排队的任何内容都被**丢弃**，而不是刷新。

<a id="exporters"></a>

#### 出口商

`OH_TELEMETRY_EXPORTER` 选择传输层：

- **`none`**（默认）— 未交付任何内容。 这就是图书馆和无头消费者所获得的，并且不需要供应商依赖。
- **`posthog`** — 需要 `OH_TELEMETRY_POSTHOG_API_KEY` 和可选
  `[posthog]`额外。 如果没有其中任何一个，遥测技术将记录一行并保持不活动状态。
- **`http`** — POSTs sanitized batches to `OH_TELEMETRY_HTTP_ENDPOINT`. 旨在前端一个后端，该后端在转发之前会验证授权和同意，所以没有供应商凭据需要在沙盒里生活。 载荷 shape:

```
POST <endpoint>
Content-Type: application/json
Authorization: Bearer <OH_TELEMETRY_HTTP_TOKEN>   # only when configured

{
  "schema_version": 1,
  "events": [
    {
      "event": "agent_server.conversation_finished",
      "distinct_id": "<user id, or anon:...>",
      "occurred_at": "2026-07-21T10:00:00+00:00",
      "properties": { ... allowlisted properties ... }
    }
  ]
}
```

这三者共享相同的有界队列、失败时丢弃和上限关闭行为。

<a id="hosted-deployments"></a>

#### 托管部署

托管部署通过              **seeding** 在任何对话开始之前，沙盒的其他设置`consent = granted`, `managed = true`, not by the 智能体服务器知道这件事。 该种子位于该存储库之外。

<a id="what-is-sent"></a>

#### 发送了什么

事件：`conversation_created`、`conversation_finished`、`conversation_failed`、
`conversation_error`、`request_failed`、`server_started`、`server_stopped` — 全部以 `agent_server.` 为前缀。

属性仅限于：

- **信封** — `schema_version`、`source`。
- **发布/运行时** — `server_version`、`sdk_version`、`tools_version`、
  `build_git_sha`, `build_git_ref`, `python_version`, `platform`,
  `deferred_init`.
- **对话形式** — `conversation_ref`、`llm_model_family`、`agent_kind`、
  `tool_count`, `is_fork`, `has_agent_profile`, `workspace_kind`,
  `confirmation_policy`.
- **结果（分桶）** — `terminal_status`、`duration_bucket`、
  `event_count_bucket`, `total_tokens_bucket`, `cost_bucket`.
- **失败** — `error_class`、`error_category`、`error_fingerprint`、
  `error_origin_module`, `error_origin_lineno`, `is_first_party`,
  `is_terminal`, `tool_name`, `error_id`.
- **请求失败** - `route_template`（参数化路线，而不是具体路径），`method`，`status_code`。

幅度是分桶的而不是精确的，因为与时间戳连接的原始计数是一个重新识别向量。 `conversation_ref` 是密钥摘要，而不是原始对话 UUID。 *消息*和堆栈跟踪从不读取——失败被按异常类型和自定义模块/行对计算的指纹分组。

<a id="identity"></a>

#### 身份

事件逐字使用部署提供的 `user_id` 作为 PostHog
`distinct_id`，因此它们会附加到您的产品已识别的人员。 导出器仅调用 `capture()` — 绝不会调用 `identify()`、`alias()` 或
`group_identify()` - 因此它不能创建重复的身份或不可逆地合并两个。 如果没有 `user_id`，则使用内存中的 `anon:<hex>` id，该 ID 在重新启动时重置并进行标记，因此 PostHog 不会创建人员配置文件。

`user_id` 无对话的请求-失败的请求和LLM-用户创建的未来事件，仍可以通过在`X-OpenHands-Telemetry-Distinct-Id`头`headers["X-OpenHands-Telemetry-Distinct-Id"] = posthog.get_distinct_id()`中发送前端的PostHogID来归因。 如果不存在，这些事件将回退到匿名 ID。 标头的信任方式与 `user_id` 相同：前端负责正确设置它。

<a id="installation"></a>

#### 安装

PostHog 客户端是可选的额外功能：

```bash
pip install 'openhands-agent-server[posthog]'
```

如果没有它，遥测技术将记录一个警告并保持不活动状态； 服务器正常启动。

<a id="secret-encryption"></a>

### 机密加密

将对话存储到磁盘时，服务器会对敏感数据（例如 LLM API 密钥和对话机密）进行加密。 要启用此加密并确保机密持久化跨服务器重新启动，您 ** 必须 ** 设置 `OH_SECRET_KEY` 环境变量。

<a id="setting-oh_secret_key"></a>

#### 设置 OH_SECRET_KEY

```bash
# 生成安全随机密钥（推荐）
export OH_SECRET_KEY=$(openssl rand -hex 32)

# 或者设置自定义键
export OH_SECRET_KEY="your-secret-key-here"
```


**重要安全说明：**
- 使用具有至少 256 位熵的强随机生成密钥
- 安全地存储此密钥（e.g.，在机密管理器中或环境变量）
- **如果您更改此密钥而不在 `OH_PREVIOUS_SECRET_KEYS` 中列出旧密钥，则之前加密的机密无法解密**（见下文）
- 如果没有 `OH_SECRET_KEY`，机密将是已脱敏（未加密）并且将在重新启动时丢失

<a id="rotating-the-key"></a>

#### 旋转钥匙

要旋转，请将新密钥设置为 `OH_SECRET_KEY`，将旧密钥设置为 `OH_PREVIOUS_SECRET_KEYS`，然后重新启动：

```bash
export OH_PREVIOUS_SECRET_KEYS="[\"$OLD_KEY\"]"   # 或 OH_PREVIOUS_SECRET_KEYS_0="$OLD_KEY"
export OH_SECRET_KEY=$(openssl rand -hex 32)
```

服务器仅使用 `OH_SECRET_KEY` 加密并首先使用它解密，然后按顺序使用每个先前的密钥。 使用先前密钥保存的值在下次保存时将使用新密钥重新加密； 设置和机密存储在启动时重新加密。 其他加密文件（对话、LLM 个人资料、提供商连接）下次保存时会移动到新的密钥，因此请保留旧密钥，直到它们仍然有意义。

`OH_SECRET_KEY` 无 API 会加密密钥，因此旋转会话密钥也会旋转加密密钥：将旧会话密钥放入 `OH_PREVIOUS_SECRET_KEYS`。 设置 `OH_SECRET_KEY` 显式保持两者独立，建议这样做。

如果使用任何配置的密钥都无法解密一个存储的值，读取操作将返回它为未设置，写入设置和机密存储时将被拒绝（对于`PATCH /api/settings`，返回409）。

<a id="what-gets-encrypted"></a>

#### 什么被加密

当设置 `OH_SECRET_KEY` 时，以下字段将被加密：
- LLM API 键 (`agent.llm.api_key`)
- AWS 凭据 (`agent.llm.aws_access_key_id`, `agent.llm.aws_secret_access_key`)
- 对话机密（来自对话请求中的 `secrets` 字段）

<a id="behavior-without-oh_secret_key"></a>

#### 没有 OH_SECRET_KEY 的行为

如果未设置 `OH_SECRET_KEY`：
- 服务器将记录警告：`⚠️ OH_SECRET_KEY was not defined. Secrets will not be persisted between restarts.`
- 在存储的对话中，机密将变为已脱敏（屏蔽）
- 当服务器重新启动时，加密的机密无法解密，将变为`None`
- 需要使用新的 API 键重新创建对话

<a id="webhook-configuration"></a>

### Webhook 配置

每个 Webhook 可以配置为：
- **`webhook_url`**：接收事件通知的端点URL
- **`method`**：HTTP 方法（POST、PUT 或 PATCH）
- **`event_buffer_size`**：发送前要缓冲的事件数（默认值：10）
- **`num_retries`**：尝试失败的次数重试（默认值：3）
- **`retry_delay`**：重试之间的延迟（以秒为单位）（默认值：5）
- **`headers`**：要包含在 Webhook 请求中的自定义标头

<a id="optional-canvas-app-backends"></a>

### 可选的 Canvas 应用程序后端

模式-1 `canvas-extension.json` 可以添加版本化的 `backend` 块。 没有此块的应用程序仍仅在浏览器中运行，并且不需要生命周期调用。

```json
{
  "schema_version": 1,
  "name": "managed-vscode",
  "display_name": "Managed VS Code",
  "version": "1.0.0",
  "entrypoint": "dist/index.js",
  "backend": {
    "schema_version": 1,
    "artifacts": {
      "linux-amd64": {
        "path": "backend/linux-amd64.tar.gz",
        "sha256": "<64 lowercase hex characters>"
      },
      "linux-arm64": {
        "path": "backend/linux-arm64.tar.gz",
        "sha256": "<64 lowercase hex characters>"
      }
    },
    "argv": [
      "{artifact_dir}/bin/server",
      "--host=127.0.0.1",
      "--port={port}",
      "--data-dir={data_dir}"
    ],
    "health": {
      "path": "/health",
      "timeout_seconds": 30,
      "interval_seconds": 0.1
    },
    "inherit_environment": ["LANG", "PATH", "TZ"]
  }
}
```

可执行文件必须位于 `{artifact_dir}` 内。 通用`{port}`，
`{data_dir}` 和 `{artifact_dir}` 占位符让启动器使用准备好的工件，而进程工作目录保留已安装的包。 准备阶段验证了选定平台归档的SHA-256，安全地将常规文件和目录提取到内容地址化的只读位置，并记录了对确切安装版本的批准。 更新或更换应用程序将使该批准无效。

安装、启用和捆绑安装从不执行后端代码。 客户端必须先调用 `prepare`，然后调用 `start`，每个调用都会返回由
`GET .../backend`. 生命周期端点是：

- `GET /api/canvas-extensions/installed/{name}/backend`
- `POST .../backend/prepare` 与 `{"revision": "..."}`
- `POST .../backend/start` 与 `{"revision": "..."}`
- `POST .../backend/stop`
- `GET .../backend/logs?limit_bytes=65536`
- `DELETE .../backend/data`

状态是 `missing`、`stopped`、`starting`、`ready`、`unhealthy` 之一，或
`unsupported`. 声明匹配的工件时，支持 Linux amd64 和 arm64。 服务器为每个安装的应用程序运行一个自己的进程组，持续清除有限的日志，并在禁用、卸载、启动失败或服务器关闭时停止它。 禁用和卸载保留可变数据； 只有单独的数据端点才会删除它。

后端不接收周围的智能体服务器环境。 清单只能继承受支持的非凭据变量（`LANG`、`LC_ALL`、`LC_CTYPE`、
`PATH`、`TMPDIR` 和 `TZ`）。 后端子进程属于这些启动规则并受这些启动规则的约束，但它们不是与操作系统隔离的； 操作不受信任的代码时使用沙盒 Agent Server。 到就绪后端的经过身份验证的 HTTP/WebSocket 路由有意位于此生命周期契约之外。

<a id="api-documentation"></a>

## API 文档

服务器运行后，您可以访问交互式 OpenAPI 文档：

```
http://localhost:8000/docs
```

这为所有可用的端点、请求/响应模式提供了完整的参考，并允许您直接从浏览器测试 API。

<a id="key-api-endpoints"></a>

### 键 API 端点

- **`GET /conversations/search`**：搜索并列出对话
- **`POST /conversations`**：创建新对话
- **`GET /conversations/{conversation_id}`**：获取对话详细信息
- **`DELETE /conversations/{conversation_id}`**：删除对话
- **`GET /conversations/{conversation_id}/events`**：获取对话事件
- **`POST /conversations/{conversation_id}/events`**：发送消息至智能体
- **`WebSocket /conversations/{conversation_id}/events/socket`**：实时事件流式传输

<a id="event-schema-compatibility"></a>

### 事件模式兼容性

事件端点在其 OpenAPI 响应模式中使用可扩展的可区分联合。 随着平台的发展，可能会添加新的事件、操作观测结果或工具变体。

如果你构建了生成的或手写的客户端，将 discriminator 值，如 `kind` 视为开放的：**跳过或忽略未知变体，而不是假设当前集合是全面的**。 当服务器开始返回更新的事件类型时，这可以使客户端保持向前兼容。


<a id="websocket-communication"></a>

## WebSocket 通讯

服务器支持 WebSocket 个连接与智能体进行实时通信：

```javascript
const ws = new WebSocket('ws://localhost:8000/conversations/{conversation_id}/events/socket');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received event:', data);
};

// 发送消息至智能体
ws.send(JSON.stringify({
    type: 'message',
    content: 'Hello, agent!'
}));
```

<a id="directory-structure"></a>

## 目录结构

服务器创建并管理以下目录结构：

```
workspace/
├── openhands_agent_server_config.json    # 配置文件
├── conversations/               # 会话存储
│   ├── {conversation_id}/
│   │   ├── metadata.json       # 对话元数据
│   │   └── events.jsonl        # 事件日志
└── project/                    # 智能体工作区
    └── (agent files and outputs)
```

<a id="development"></a>

## 发展

对于开发，服务器运行时默认启用自动重新加载。 对源代码的任何更改都会自动重新启动服务器。

<a id="running-tests"></a>

### 运行测试

```bash
# 运行所有 Agent Server 测试
uv run pytest tests/agent_server/

# 覆盖范围内运行
uv run pytest tests/agent_server/ --cov=openhands.agent_server
```

<a id="security-considerations"></a>

## 安全考虑

- **身份验证**：在生产环境中使用`session_api_key`
- **机密加密**：在生产中始终设置`OH_SECRET_KEY`以加密敏感数据
- **CORS**：根据您的用例适当配置`allow_cors_origins`
- **网络**：服务器默认绑定到`0.0.0.0` - 根据需要限制访问
- **文件系统**：服务器对配置的工作区目录具有完全访问权限

<a id="troubleshooting"></a>

## 故障排除

<a id="common-issues"></a>

### 常见问题

1. **端口已在使用中**：使用`--port`选项更改端口
2. **权限被拒绝**：确保用户对工作区目录具有写权限
3. **未找到配置**：检查`OPENHANDS_AGENT_SERVER_CONFIG_PATH` 环境变量
4. **CORS 错误**：将您的前端域添加到 `allow_cors_origins`
5. **LLMAPI键重新启动后为None**：当`OH_SECRET_KEY`未设置或已更改时会发生这种情况。 在启动服务器加密之前设置`OH_SECRET_KEY`和持久化机密。 注意：如果更改密钥，则之前加密的机密无法解密。

<a id="logs"></a>

### 日志

服务器将重要事件记录到标准输出。 对于调试，请检查：
- 服务器启动消息
- 配置加载
- API 请求/响应日志
- WebSocket 连接事件
