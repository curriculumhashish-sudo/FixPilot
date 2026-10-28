<a id="agent-server-feature-map"></a>

# Agent Server 特征图

这是验证的维护源智能体-面向行为的 OpenHands  Agent Serverevery REST route and WebSocket (默认应用加上路由) Docker 运行时模式添加； `map routes` 包括它们的行为（）持久化，Webhook, auth, consumers). 在驱动服务器之前阅读此索引，然后使用匹配的系列文件作为配方。

维护基线：main@8ba966d1d3af49f08e04349c055009e1614b48d6（2026-10-07）。 第一关； 下一个维护阶段从此提交开始，一个阶段在其 PR 中提出下一个基线，并合并 PR 接受它。

该地图有 **950 个子要素**。

<a id="baseline-preconditions"></a>

## 基线前提条件

- `make build`（或`uv sync --dev`）已在存储库根目录中运行。
- `control-agent-server` 位于 `PATH` 上：
  `export PATH="$PWD/.agents/skills/verify-agent-server/scripts:$PATH"`.
- 此结帐运行已实时运行并导出：
  `export AGENT_SERVER_VERIFY_RUN=$(control-agent-server launch --new --print-run)`.
- `control-agent-server doctor`报道`ok: true`。
- 模型支持的配方：`$DEEPSEEK_API_KEY` 已设置并且
  `control-agent-server llm preset deepseek` 已运行（deepseek-flash 处于活动状态）。
- 切勿驱动此验证运行未启动或连接的服务器。

<a id="driving-conventions"></a>

## 驾驶惯例

- 从基线开始每个家庭，除非其 `Preconditions:` 另有说明； 它的子弹在一个弹壳中从上到下运行。
- 将每次运行的值捕获到 shell 变量中（`--print-id`、`--field`、
  `--print-path`); 切勿粘贴先前运行的 id。 子弹读取另一个子弹的变量或文件名 `Requires:` 一条线，一个需要机器能力的子弹，就给它起了一个名字 `Needs:` 线。
- 启动后面的项目符号使用 `helper start` 的后台进程； 普通的 `cmd &` 以其项目符号结尾。
- 将每个命令视为字面意思。 保持引用的 JSON 和标志不变。
- 前缀测试夹具且名称带有 `qa-` 或 `QA_`； 突变后恢复共享状态（活动配置文件、设置），除非后面的项目符号需要它。
- 断言状态代码、存储值、文件、事件类型和工具观测结果，而不是模型的措辞。

<a id="proof-and-skip-reporting"></a>

## 证明并跳过报告

- 突变通过只读第二个视图来证明：GET、WebSocket 帧、磁盘上的文件或 Webhook 交付。
- 用`--save <ID>/<name>`保存证明每个子特征的交换，并在`evidence add`中引用它。
- 使用尝试的命令和未满足的前提条件 (`blocked`) 报告无法到达的路径，切勿将其视为通过不同的入口。

<a id="family-entry-contract"></a>

## 家庭入境合同

每个家庭文件都以 H1 标题、描述智能体可见行为的段落、`Source:` 行和 `Routes:` 行（请参阅
[mapping.md](../mapping.md#3-write-each-entry)). It then uses exactly four H2
部分按此顺序：`Sub-features`、`How to get to it (agent POV)`、
`Driving it with control-agent-server`（从 `Preconditions:` 开始），以及
`Gotchas`.

如何编写和证明新条目：[../mapping.md](../mapping.md). 如何保持诚实：[../maintenance.md](../maintenance.md).

<a id="families"></a>

## 家庭

| 身份证号 | 家庭 | 它涵盖什么 | 入口 | 需求 | 子功能 |
|---|---|---|---|---|---|
| F01 | [服务器状态、信息和合同](F01-server-status.md) | 存活性、健康、就绪状态、服务器信息及其`/`别名、可用性和空闲时间、OpenAPI文档、静态文件模式、DEBUG调用堆栈、工具预加载 | `GET /alive`, `/health`, `/ready`, `/server_info`, `/`, `/openapi.json` | 基线 | 11 |
| F02 | [身份验证和工作区会议](F02-auth-and-sessions.md) | HTTP 和 WebSockets（第一个帧，已弃用查询和头部形式，关闭代码），多个和旋转的密钥，无认证和遗留模式，默认绑定地址，工作区会话 cookie，CORS | 每个套接字上的 `X-Session-API-Key`、`POST`/`DELETE /api/auth/workspace-session`、WebSocket 身份验证 | 食谱：tmux | 21 |
| F03 | [延迟初始化（暖池休眠模式）](F03-deferred-init.md) | 热池休眠模式：`/api`、`/v1`、`/app-backends` 和每个套接字上的门（在身份验证之前检查）、init key auth、验证和脱敏、回滚、一次性 init 以及 init 主体提供的每个字段（keys、机密 key、paths、工作树 root、run limit、CORS、Webhook、env、web URL） | `GET`/`POST /api/init`, `X-Init-API-Key` | git； 发射`--no-auth --deferred-init` | 25 |
| F04 | [对话生命周期和目录](F04-conversation-lifecycle.md) | 从设置、智能体配置文件或内联智能体创建； 客户端 ID、父母、工作树、开始时间机密、422 脱敏； 获取、批量获取、搜索、计数； PATCH; 最终回应； DELETE; 重新启动 | `POST`/`GET`/`PATCH`/`DELETE /api/conversations[/{id}]`, `/search`, `/count`, `/agent_final_response`, `/children` | 法尔姆，吉特 | 36 |
| F05 | [运行、暂停、中断和状态转换](F05-run-pause-interrupt.md) | 模型期间运行、暂停和中断工具调用； 每个视图上的状态转换； 卡住检测并 max_iterations 停止； 409和429； 优雅地SIGKILL重新启动 | `POST /api/conversations/{id}/run`, `/pause`, `/interrupt` | 法学硕士，tmux； 发射`--config-json '{"max_concurrent_runs": 1}'` | 31 |
| F06 | [对话事件和事件WebSocket](F06-conversation-events.md) | 添加消息、事件搜索、计数、获取和批量获取，带有过滤和分页的事件 WebSocket（认证、快照、回放、实时帧），重启历史 | `POST`/`GET /api/conversations/{id}/events[...]`, `WS /sockets/events/{id}` | 法学硕士； 发射`--env TZ=UTC` | 29 |
| F07 | [会话WebSocket协议](F07-session-socket.md) | 可恢复会话套接字：同步，持久帧和临时帧，顺序重播，入站消息，错误和关闭代码，流式传输值，背压订阅容量 | `WS /sockets/session/{id}` | 勒姆 | 24 |
| F08 | [确认策略、安全分析器和对话机密](F08-confirmation-security-secrets.md) | 确认策略和接受/拒绝，安全分析器，运行时对话机密（静态、查找、掩码、加密、无密码），以及重启后幸存的内容 | `POST /api/conversations/{id}/confirmation_policy`, `/security_analyzer`, `/secrets`, `/events/respond_to_confirmation` | 法学硕士，tmux | 23 |
| F09 | [型号、配置文件和ACP切换； runtime plugins](F09-model-switching-plugins.md) | 交换智能体 LLM，切换到保存的配置文件，切换 ACP 模型，在运行时加载插件； 统计、挂钩和重启持久化 | `POST /api/conversations/{id}/switch_llm`, `/switch_profile`, `/switch_acp_model`, `/load_plugin` | llm，tmux，节点，网络 | 28 |
| F10 | [分叉、导航、压缩和 ask_agent](F10-fork-navigate-condense-ask.md) | fork，在分支之间导航，使用真正的摘要器进行压缩，询问智能体附带问题； 重启后状态 | `POST /api/conversations/{id}/fork`, `/navigate`, `/condense`, `/ask_agent` | 勒姆 | 25 |
| F11 | [目标循环](F11-goals.md) | 目标循环：开始、LLM-判断完成和上限、停止、恢复、取代、中断、失败、繁忙和容量限制 | `POST /api/conversations/{id}/goal`, `/goal/stop`, `/goal/resume` | 法学硕士，tmux； 发射`--config-json '{"max_concurrent_runs": 1}'` | 25 |
| F12 | [对话运行时信息、沙箱暂停和凭据绑定](F12-runtime-and-credentials.md) | 运行时信息和重置，准备进入沙盒暂停，凭据对于ACP 的绑定，智能体管理的LLM 密钥刷新，Docker 运行时模式的路由和合同 | `GET /api/conversations/{id}/runtime`、`POST .../runtime/reprovision`、`POST /api/conversations/prepare-for-sandbox-pause`、`PUT .../credential-bindings/{name}`、Docker 模式 `DELETE .../runtime`、`POST .../runtime/credentials` | llm、节点、网络 | 31 |
| F13 | [Bash 命令和 bash 事件](F13-bash.md) | 全局和对话范围的 shell 命令：执行、启动、停止、超时、大输出、事件搜索和清除、保留、bash 事件套接字 | `/api/bash/*`, `/api/conversations/{id}/bash/*`, `WS /sockets/bash-events` | 基线 | 29 |
| F14 | [文件上传、下载、存档和目录助手](F14-files.md) | 上传、下载、创建目录、搜索主页和子目录、git-delta和tar.gz归档、轨迹压缩、会话范围变体及其路径保护 | `/api/file/*`, `/api/conversations/{id}/file/*` | llm、git、节点 | 30 |
| F15 | [Git 更改、差异、提交和存储库搜索](F15-git.md) | 工作树更改和差异、显式引用、嵌套存储库、提交历史记录和每次提交更改、范围变体、GitHub 存储库搜索 | `/api/git/*`, `/api/conversations/{id}/git/*`, `GET /api/git/repositories/search` | llm、git、节点 | 29 |
| F16 | [工作区文件服务和 VS Code 端点](F16-workspace-serving-and-vscode.md) | 每个会话的静态工作区服务器（索引、内容类型、范围、遍历、cookie 身份验证）以及 VS Code 状态和 URL 路由 | `GET /api/conversations/{id}/workspace[/{path}]`, `/api/vscode/*`, `/api/conversations/{id}/vscode/*` | 法尔姆，吉特 | 26 |
| F17 | [工作区注册表和父母](F17-workspaces-registry.md) | 已保存的工作区和父项：添加、列出、删除、验证、持久化、并发作者、损坏的文件 | `GET`/`POST`/`DELETE /api/workspaces`, `/api/workspaces/parents` | git、节点 | 24 |
| F18 | [服务器设置、设置模式和机密商店](F18-settings-and-secrets.md) | 已持久化设置已脱敏、明文和加密公开、稀疏 PATCH、设置模式、命名机密存储、加密 REST、密码密钥更改 | `GET`/`PATCH /api/settings`, `/api/settings/agent-schema`, `/conversation-schema`, `/api/settings/secrets[/{name}]` | git、节点 | 30 |
| F19 | [MCP服务器设置、连接测试和 OAuth](F19-mcp.md) | MCP 服务器设置 CRUD、连接测试（stdio 和 HTTP）、安装时 OAuth 作业和 token 刷新、模型驱动 MCP 工具调用 | `/api/settings/mcp/{key}`, `POST /api/mcp/test`, `/api/mcp/oauth/*` | 法学硕士； 发射`--webhook-sink` | 28 |
| F20 | [LLM简介](F20-llm-profiles.md) | LLM 配置文件：保存、读取、针对真实和存根提供程序进行验证、激活、重命名、删除、命名规则、限制、存储争用、重新启动 | `/api/profiles[/{name}]`, `/validate`, `/activate`, `/rename` | LLM，节点 | 36 |
| F21 | [智能体个人资料](F21-agent-profiles.md) | 智能体个配置文件（OpenHands 和 ACP 种）：CRUD、默认种子、激活、重命名、删除、实现、从配置文件开始的对话、存储争用 | `/api/agent-profiles[/{name}]`, `/rename`, `/{id}/activate`, `/materialize` | 勒姆 | 32 |
| F22 | [元配置文件（模型路由器）](F22-meta-profiles.md) | 元配置文件（模型路由器）：保存、读取、激活、删除、设置反射、对话中的路由 | `/api/meta-profiles[/{name}]`, `/activate` | LLM，节点 | 24 |
| F23 | [LLM 目录和提供商连接](F23-llm-catalog-and-connections.md) | 提供者和模型目录、经过验证的模型、提供者连接（创建、旋转、删除、从配置文件中引用）、实时 ACP 发现和错误 | `GET /api/llm/providers`, `/api/llm/models[/verified]`, `/api/llm/provider-connections[/{id}]`, `POST /api/acp/models` | llm、节点、网络 | 28 |
| F24 | [OpenAIChatGPT订阅设备流程](F24-openai-subscription.md) | ChatGPT 订阅设备流程：型号、状态、设备启动和轮询、注销、上游故障 | `/api/llm/subscription/openai/*` | 节点、网络 | 20 |
| F25 | [技能目录、安装和市场](F25-skills.md) | 合并的技能目录，公共仓库同步，安装的技能（安装、启用、刷新、卸载），市场，对话中的触发词激活 | `POST /api/skills`, `/api/skills/sync`, `/api/skills/install`, `/api/skills/installed[/{name}]`, `/api/skills/marketplace` | git； 食谱：llm、网络、节点 | 34 |
| F26 | [插件目录、安装和市场](F26-plugins.md) | 插件目录、从路径或 git 源安装、启用、刷新、卸载、市场、将插件加载到对话中 | `POST /api/plugins`, `/api/plugins/install`, `/api/plugins/installed[/{name}]`, `/api/plugins/marketplace`, `/api/plugins/fetch` | llm、git、节点、网络 | 26 |
| F27 | [挂钩、子智能体和工具目录](F27-hooks-subagents-tools.md) | 钩子和子智能体目录、对话中的阻塞钩子、工具注册表和目录、客户端工具、转发智能体定义、自定义工具模块 | `POST /api/hooks`, `POST /api/sub-agents`, `GET /api/tools/`, `/api/tools/catalog` | llm、git、tmux、铬 | 32 |
| F28 | [画布应用：安装、编目和后端生命周期](F28-canvas-extensions.md) | Canvas 应用程序安装、目录、启用、卸载、捆绑和图标； 后端审批、准备、启动、停止、日志、数据、故障状态、重启 | `/api/canvas-extensions/install`, `/api/canvas-extensions/installed[/{name}][/backend...]` | git，节点； 发射`--env TZ=UTC` | 29 |
| F29 | [Canvas App 后端桥（会话、HTTP 和 WebSocket 代理）](F29-app-backend-bridge.md) | 应用程序后端桥：会话 cookie、来源和主机检查、代理 HTTP 方法和 WebSockets、撤销 | `/app-backends/{name}/session`, `/app-backends/{name}[/{path}]`, `WS /app-backends/{name}[/{path}]` | git； 发射`--canvas-ingress` | 29 |
| F30 | [OpenAI兼容网关（/v1)](F30-openai-gateway.md) | 兼容OpenAI的网关：模型、聊天完成（平和流式传输）；回复；对话重用；使用；官方OpenAI SDK | `GET /v1/models`, `POST /v1/chat/completions`, `/v1/responses` | 法学硕士，tmux | 27 |
| F31 | [持久化、重启恢复、租约和限制](F31-persistence-and-limits.md) | 生存优雅且 SIGKILL 重启、崩溃恢复、会话所有权租约和服务器之间的接管、空闲淘汰、运行容量、配置文件 vs 环境优先级 | 仅行为：`restart`、`restart --hard`、共享存储上的第二个服务器 | 法学硕士，tmux | 23 |
| F32 | [事件Webhook和产品遥测](F32-webhooks-and-telemetry.md) | 事件 Webhook（事件批次、会话更新、头信息、缓冲、刷新、限制、重试）以及产品 telemetry（默认关闭，导出生命周期， sanitized 载荷，同意） | 仅行为：`webhooks` / `OH_WEBHOOKS_*`, `OH_TELEMETRY_*` | 法学硕士； 发射`--webhook-sink` | 30 |
| F33 | [Python SDK 远程客户端 (RemoteConversation, RemoteWorkspace)](F33-sdk-remote-client.md) | Python SDK 在针对服务器的检查中：RemoteWorkspace 命令、文件、git 和设置读取器； RemoteConversation 创建、运行、回调、流式传输、重新附加、分叉、确认、暂停、中断、停止挂钩、客户端工具、完成日志 | 仅行为：`Workspace(host=...)`、`RemoteWorkspace`、`RemoteConversation` | LLM，tmux，git | 43 |
| F34 | [TypeScript 客户端（@）openhands/typescript-client)](F34-typescript-client.md) | 的 TypeScript 客户端与此结算：服务器和版本门工作区，bash, conversation, state, events and socket clients, hooks and MCP clients, 端点审计和漂移 | 仅行为：`@openhands/typescript-client` (`clients/typescript`) | llm、节点、uvx、git、tmux、网络 | 32 |

<a id="not-mapped"></a>

## 未映射

路线故意离开所有者，原因是：

- `GET /docs`、`GET /redoc`、`GET /docs/oauth2-redirect`：FastAPI 生成的文档页面，不是面向智能体的合约的一部分（`/openapi.json` 在 F01 中映射）。
- `POST /api/conversations/{conversation_id}`,
  `PUT /api/conversations/{conversation_id}`,
  `GET /api/conversations/{conversation_id}/{tail:path}`,
  `POST /api/conversations/{conversation_id}/{tail:path}`,
  `PUT /api/conversations/{conversation_id}/{tail:path}`,
  `PATCH /api/conversations/{conversation_id}/{tail:path}`,
  `DELETE /api/conversations/{conversation_id}/{tail:path}`：仅存在于 Docker 运行时模式 (`conversation_runtime: docker`) 中，在该模式下，它们将对话范围内的调用转发到对话的容器中。 他们转发的路线都映射在自己的家族中； 证明转发需要一个 Docker 守护进程和配置的子映像 (`F12.docker-runtime`)。 F12 拥有 Docker 模式自己的运行时控制路由。
