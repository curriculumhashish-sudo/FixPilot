<a id="conversation-runtime-info-sandbox-pause-and-credential-bindings"></a>

# 对话运行时信息、沙箱暂停和凭据绑定

沙箱编排器和客户端如何了解对话背后的运行时。 `GET .../runtime` 报告会话的运行时是否可用和可恢复（总是） `available` 对于在进程中的本地运行时， `reprovision` 仅仅重复。 在沙盒冻结之前， orchestrator 调用 `POST /api/conversations/prepare-for-sandbox-pause`每条加载的对话都被保存，任何正在进行的会话都被取消了 `paused`其所有权租赁文件被释放，从内存中被删除； 目录保留它，下一个事件访问会再次加载它。 ACP 法典对话可以让他们 `CODEX_AUTH_JSON` 文件凭据从外部版本化的
来源：`PUT .../credential-bindings/CODEX_AUTH_JSON` 探测来源，绑定
将其转换为一个已启动但尚未初始化的 ACP 智能体状态（擦除存储的副本并记录当前对话需要运行时绑定），或者将其标记为待加载或尚未创建的对话的备用状态。 需要绑定的对话拒绝再次加载（409，可重试； WebSocket close 1013) 暂停或重启后，直到再次激活绑定。 暂停和绑定路线在 OpenAPI 文档中是隐藏的。 两个运行时端行为使整个图更加完整：
`OH_CONVERSATION_RUNTIME=docker` 服务器为每个会话拥有一个容器，其 Docker 路由器替换了运行时路由，添加
`DELETE .../runtime` 和 `POST .../runtime/credentials`，代理一切
else into the container and refuses the operations it cannot proxy (501);
和一个沙箱，其控制平面设置为 `OH_LLM_API_KEY_REFRESH_URL` 和
当提供者通过 401 拒绝存储的密钥时，`OH_LLM_API_KEY_REFRESH_BASE_URLS` 重新获取托管的 LLM 密钥。

Source: `openhands-agent-server/openhands/agent_server/credential_binding.py`, `openhands-agent-server/openhands/agent_server/conversation_router.py`, `openhands-agent-server/openhands/agent_server/conversation_registry.py`, `openhands-agent-server/openhands/agent_server/conversation_service.py`, `openhands-agent-server/openhands/agent_server/event_service.py`, `openhands-agent-server/openhands/agent_server/conversation_lease.py`, `openhands-agent-server/openhands/agent_server/models.py`, `openhands-agent-server/openhands/agent_server/docker_runtime/`, `openhands-agent-server/openhands/agent_server/managed_llm_key.py`, `openhands-sdk/openhands/sdk/credential.py`, `openhands-sdk/openhands/sdk/agent/acp_file_credentials.py`

需求：`llm`、`node`、`network`

路线：`GET /api/conversations/{conversation_id}/runtime`，
`POST /api/conversations/{conversation_id}/runtime/reprovision`,
`POST /api/conversations/prepare-for-sandbox-pause`,
`PUT /api/conversations/{conversation_id}/credential-bindings/{secret_name}`,
`DELETE /api/conversations/{conversation_id}/runtime`,
`POST /api/conversations/{conversation_id}/runtime/credentials`

<a id="sub-features"></a>

## 子功能

- `F12.discovery`：OpenAPI文档列出了两个运行时路由，但没有列出暂停和凭据绑定路由，`/server_info`通告`credential_binding_v1`、`credential_binding_readiness_probe_v1`和`credential_binding_activation_guard_v1`。
- `F12.runtime-info`: `GET .../runtime` 对于本地对话返回 200 `{"runtime_status": "available", "can_resume": true, "runtime_error": null}`，并且对话的 GET、搜索和批量获取行嵌入与 `runtime_info` 相同的对象。
- `F12.runtime-reprovision`：`POST .../runtime/reprovision` 返回相同的运行时信息，忽略正文，并且不进行任何更改（状态、事件计数和租约生成保持不变）。
- `F12.runtime-errors`：两个运行时路由对于未知 id 都回答 404，对于非 UUID id 回答 422，对于没有会话密钥的 401。
- `F12.ts-client`built TypeScript 客户端的 `ConversationClient.getRuntime` 和 `reprovisionRuntime` 返回本地运行时信息 `getConversation()` 嵌入它 `runtime_info`并且这两种方法都拒绝未知的 id，返回 404 错误 `HttpError` 一个没有密钥的客户端，返回状态码401。
- `F12.sandbox-pause-releases`: `prepare-for-sandbox-pause` 以空体返回 204 状态码，删除所有 `owner_lease.json`，保留每条对话及其状态，是幂等的，并且拒绝返回 401 状态码（留下租约），不带密钥。
- `F12.runtime-cold`：运行时信息回答未加载的对话，在重新启动之前和之后，不加载它（不出现租赁文件）。
- `F12.sandbox-pause-rehydrate`：暂停一段时间后，下一个事件访问会加载对话（一个新的租期，相同的事件），然后一个新消息会运行到`finished`，这会触发一个真实模型，该模型会再次执行。
- `F12.sandbox-pause-running`：正在飞行中的模型调用会立即被取消，`paused`，`PauseEvent`，`InterruptEvent`，并且状态变化会推送到事件套接字上。
- `F12.sandbox-pause-websocket` 一个事件套接字或会话套接字，在暂停之前是打开的，要么由服务器关闭，要么继续接收会话的新事件。 它永远不会保持开放和沉默。
- `F12.binding-unsupported-secret`：只能绑定文件凭据：任何其他机密名称都会得到 404，而无需联系源。
- `F12.binding-validation`：带有额外键的体，没有 `url`，一个空或过长（4097+字符）的 `url`，一个空或过长的（8193+字符）头部值，或者超过16个头部，或者一个非 UUID id，会无源被返回 422，同时对于一个不支持的机密名称（体被首先验证）。 没有键会得到 401。
- `F12.binding-pending`：会话 id 的绑定，服务器在一次携带给定标头的探测 `GET` 后不知道答案 204； ID 仍然未知 (404)。
- `F12.binding-source-statuses`源端点的答案映射到激活状态：401/403为403，400/404/422为422，409为409，501为501，非200的状态 `{"value": str, "version": non-empty str}` 到422，和一个 URL 那不是 http(s) 到422，每间隔一个探针None 对于坏的 URL).
- `F12.binding-source-unavailable`：回答 5xx 的源被探测 3 次，并有退避（至少 0.75 秒），然后激活失败，返回 502； 无法访问的源也会给出 502。
- `F12.binding-native-too-late`：绑定已加载的常规（非 ACP）对话被 409 `Credential binding activation arrived after ACP initialization` 拒绝，并且不记录任何内容。
- `F12.binding-native-cold`：在未加载常规（非 ACP）对话时发送的绑定永远不会使该对话在下一次暂停后要求凭据绑定。
- `F12.binding-live-acp`：绑定尚未运行的已加载 ACP Codex 对话，回答 204，在 `meta.json` 中记录 `required_runtime_credential_bindings: ["CODEX_AUTH_JSON"]`，并删除存储的 `CODEX_AUTH_JSON` 机密。
- `F12.binding-rebind`：接受具有相同 URL 和新标头的第二次激活（探针携带新标头，这些标头永远不会写入磁盘）； 不同的 URL 被 409 拒绝。
- `F12.binding-required-after-pause` 之后，仍然会列出一个需要绑定的对话，并报告运行时 `available`，但事件访问和 `/run` 返回 409 `{"detail": "credential_binding_activation_required", "retryable": true}`，对话套接字关闭为 1013，直到一个新的激活，之后事件再次加载。
- `F12.binding-required-after-restart`：要求在重新启动后仍然存在（409 直到新激活，然后 200），并且删除此类对话不需要激活。
- `F12.binding-pending-on-create`当与该对话创建绑定时，一个待处理的绑定被消耗 `conversation_id`这之后还需要从开始进行绑定，并且不存储任何信息 `CODEX_AUTH_JSON`  机密。
- `F12.binding-pending-cleared`：暂停会删除挂起的绑定，因此随后使用该 id 创建的对话将保留其自己的 `CODEX_AUTH_JSON` 机密并且不需要绑定。
- `F12.binding-profile-scope`：从智能体配置文件启动的对话，其 `secret_refs` 排除 `CODEX_AUTH_JSON` 拒绝与 403 `Credential binding authorization was rejected` 绑定并且不记录任何内容。
- `F12.runtime-launched-profile`在本地服务器上启动的： `OH_RUNTIME_LAUNCHED_PROFILE` (已启动的配置文件) Docker 在每个会话容器中，如果没有创建会话，则会传递父级智能体记录该条记录为 profile `launched_agent_profile` and its `secret_refs` scope the 凭据 binding (403)，而从其自身发起的对话智能体 profile 保留自己的 profile (204)。
- `F12.managed-key-refresh`: `OH_LLM_API_KEY_REFRESH_URL`，`OH_LLM_API_KEY_REFRESH_BASE_URLS`命名LLM的`base_url`和`OH_LLM_API_KEY_REFRESH_HEADERS`（值来自服务器环境），模型调用以401拒绝，会执行一次`GET`刷新URL，并使用扩展的头信息，一次重试，运行结束。 获取的密钥不会写入服务器的状态。
- `F12.managed-key-scope`: an LLM whose `base_url` 不在允许列表中，或者任何其他情况 LLM 一旦允许列表为空，返回 401 错误`LLMAuthenticationError`, status `error` 一次模型调用和没有刷新请求。 空的允许列表被记录为“保持关闭”。
- `F12.managed-key-switch`：与 `switch_llm`（或 `switch_profile`）一起安装的范围内 LLM 通过刷新 URL 从 401 恢复，就像对话加载的 LLM 一样。
- `F12.docker-runtime-contract`：在 `OH_CONVERSATION_RUNTIME=docker` 和没有 Docker 服务进程的服务器上，fork、`switch_llm`、`switch_profile` 和凭据绑定在任何查找之前就返回 501（绑定源从不被联系）。 运行时路由 `DELETE .../runtime`、`POST .../runtime/credentials` 和 `/run` 对于未知 id 回答 404 `Conversation not found`，以及两个没有密钥的仅 Docker 路由 401； 对于未知 id，两个会话套接字均以 1008 关闭； create 会拒绝丢失的主体 (400)、非对象 (422)、非本地工作区 (422) 和错误的 `conversation_id` (400)，而无需编写运行时清单； 一个有效的创建答案502，留下一个缺少的manifest，其运行时信息为404，其重新配置为502，其套接字关闭为1011，直到`DELETE /api/conversations/{id}`移除它。
- `F12.docker-runtime`：使用 Docker 守护进程，创建使用配置的 `--memory`、`--cpus` 和 `--pids-limit` 启动一个容器，`OH_RUNTIME_LAUNCHED_PROFILE` 中启动的配置文件； `POST .../runtime/credentials` 返回容器的会话密钥，`DELETE .../runtime` 在对话保持可读时停止它 (204)，重新配置恢复工作区文件，携带 `X-Expose-Secrets` 的代理请求被拒绝为 422，归档运行时保留历史记录但拒绝重新配置为 410。
- `F12.docker-startup-timeout`缺少的容器 `conversation_container_startup_timeout` 它会返回502错误，并在响应时间内创建，移除失败的容器，并允许删除剩余的运行时映射。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `GET /api/conversations/{conversation_id}/runtime` 和
  `POST /api/conversations/{conversation_id}/runtime/reprovision`（均在OpenAPI文档中； 本地注册表总是回答 `available`）。
  `runtime_info` 也嵌入在 `GET /api/conversations/{id}` 中，
  `GET /api/conversations/search` 和 `GET /api/conversations?ids=...`。
- REST、Docker 运行时模式（`OH_CONVERSATION_RUNTIME=docker` 或配置
  `conversation_runtime: docker`; `docker_runtime/routers.py`): Docker 路由器安装在目录的读取路由（`GET /api/conversations/{id}`、搜索、计数保持本地）之后和本地会话路由之前，因此它提供 `POST /api/conversations`（通过容器创建）、`GET .../runtime` 和 `POST .../runtime/reprovision`（容器状态）、本地应用程序没有的两条路由、`DELETE .../runtime`（停止容器，保持会话；204）和 `POST .../runtime/credentials`（容器的 `session_api_key`）、`DELETE /api/conversations/{id}` 和一个包罗万象的代理`/{conversation_id}/{tail}` 转发到容器中，`fork`、`switch_llm`、`switch_profile` 除外
  `credential-bindings` (501). `map routes`列出了仅在该模式下存在的路由（标记为`config: conversation_runtime=docker`）； 最后两个
  `Routes:` 条目是两个运行时控制条目，容器代理在 README 中列为未映射。
- REST，隐藏（`include_in_schema=False`，因此生成的 TypeScript 模式和 OpenAPI 工具都看不到它们； 由沙盒编排器使用）：`POST /api/conversations/prepare-for-sandbox-pause`（无主体，
  204) 和
  `PUT /api/conversations/{conversation_id}/credential-bindings/{secret_name}` 与 `{"url": "...", "headers": {"Name": "value"}}` (204)。 凭据来源必须用 `{"value": "<credential>", "version": "<opaque>"}` 回答 `GET url`，然后用 `{"expected_version", "value"}` 回答 `PUT url`（刷新同步； 如果没有正在运行的 Codex，则无法访问）。
- WebSocket: `/sockets/events/{conversation_id}` 和
  `/sockets/session/{conversation_id}` 结束于 1013
  `credential_binding_activation_required` 用于需要绑定的对话。 在 Docker 模式下，两者都桥接到容器中，并在未知对话时使用 1008 关闭，在容器无法启动时使用 1011 关闭。
- TypeScript 客户端：`ConversationClient.getRuntime(conversationId)` 和
  `reprovisionRuntime(conversationId)`; `ConversationInfo.runtime_info`（`F12.ts-client` 使用 `node` 针对构建的客户端运行它们）。 没有隐藏路由的客户端方法。
- SDK：此存储库中没有Python个这些路由的使用者；
  `RemoteWorkspace` 调用仅限 Docker 的 `.../runtime` 生命周期路由 (`DELETE .../runtime`、`POST .../runtime/credentials`)。
- 配置：`OH_LEASE_TTL_SECONDS`（默认45； `0`禁用暂停释放的租用文件）； `OH_CONVERSATION_RUNTIME` 与
  `conversation_image`, `conversation_container_memory`,
  `conversation_container_cpus`、`conversation_container_pids_limit` 和
  `conversation_container_startup_timeout`; `OH_RUNTIME_LAUNCHED_PROFILE`（每个容器中的 `LaunchedAgentProfile` JSON Docker 父集，在创建时由任何服务器读取）； `OH_LLM_API_KEY_REFRESH_URL`,
  `OH_LLM_API_KEY_REFRESH_BASE_URLS`（逗号分隔的 `base_url` 允许列表，必需）和 `OH_LLM_API_KEY_REFRESH_HEADERS`（JSON 对象，`$VAR` 和
  `${VAR}`从服务器环境扩展），加载会话时读取（`managed_llm_key.py`，在`EventService.start`中注册）。 刷新URL以纯文本正文形式回答当前密钥。
- `/server_info` `capabilities` 做广告 `credential_binding_v1`，
  `credential_binding_readiness_probe_v1` 和
  `credential_binding_activation_guard_v1`（F01 拥有该路线）。
- 食谱：`api` 驾驶每条路线； `fixture http-sink` 播放凭据源和管理密钥刷新 URL （一个回复状态对应一个接收者，因为接收者对每个请求都以相同方式回应）以及 `sink read` 计数其探针及其头部； 第二个服务器 (`launch --new --env ...`) 承载 Docker 模式、启动的配置文件和刷新变量； `state ls`和`state cat`改为`owner_lease.json`和`meta.json`； `fixture llm-stub` 在飞行中进行模型调用，并使用 401 拒绝过时密钥的提供者； `ws start`/`wslisten`观察套接字。 ACP Codex 对话是通过内联创建的
  `{"kind": "ACPAgent", "acp_command": ["codex-acp"], "acp_server": "codex"}`
  智能体：ACP 子进程仅在第一次运行时启动，因此没有 Codex 二进制文件
  这里的任何事情都需要。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行 (`launch --new`)，`doctor` 正常，`$DEEPSEEK_API_KEY` 设置； 下面的块保存 DeepSeek 配置文件。
- 块会创建：未知的 id `NOPE`, inline ACP Codex 智能体  `ACP_AGENT`, 健康的凭据来源 `SRC` (an) HTTP  `{"value": "{}", "version": "qa-v1"}`), 第二个健康来源
  `NEVER` 没有请求可以到达，`llm-stub` 将每个模型调用挂起 300 秒，并在其上有内联智能体 (`HANG_AGENT`)，常规对话
  DeepSeek 闪光灯上的 `N` 永远不会运行，而 DeepSeek 闪光灯上的对话 `R` 会回答一个微小的提示词并结束。 不需要任何工具 `tmux` (`--tools none`)。
- 多个项目符号调用 `prepare-for-sandbox-pause`，这会卸载运行中的每个对话，因此每个项目符号首先加载它需要的内容。
- 每次启动和停止自己的第二个服务器时，来自 `F12.runtime-launched-profile` 的项目符号（带有 `OH_RUNTIME_LAUNCHED_PROFILE` 或托管密钥变量的本地服务器，或者带有
  `OH_CONVERSATION_RUNTIME=docker`); 它们的接收器和存根是基线运行的测试夹具，因此 `sink read` 不需要 `--run`。 这些项目符号不需要 DeepSeek 密钥：它们的模型是 `llm-stub` 脚本，因为真正的提供者不能被告知拒绝一次密钥。

```sh
control-agent-server llm preset deepseek
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
ACP_AGENT='{"kind": "ACPAgent", "acp_command": ["codex-acp"], "acp_server": "codex"}'
SRC=$(control-agent-server fixture http-sink --name qa-f12-cred --status 200 --body '{"value": "{}", "version": "qa-v1"}' --print-path)
NEVER=$(control-agent-server fixture http-sink --name qa-f12-never --status 200 --body '{"value": "{}", "version": "qa-v1"}' --print-path)
HANG=$(control-agent-server fixture llm-stub --name qa-f12-hang --step hang:300 --print-path)
HANG_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG/v1\", \"num_retries\": 0}, \"tools\": []}"
N=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
R=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with the single word ok, then finish.' --wait --until finished --timeout 180 --print-id)
control-agent-server api GET "/api/conversations/$R" --check execution_status eq finished
```

- **发现 (`F12.discovery`).**阅读 OpenAPI 文档和功能标志。
  ```sh
  control-agent-server api GET /openapi.json --auth none --expect 200 --max-chars 200 \
    --check 'paths./api/conversations/{conversation_id}/runtime.get' exists \
    --check 'paths./api/conversations/{conversation_id}/runtime/reprovision.post' exists \
    --check 'paths./api/conversations/prepare-for-sandbox-pause' missing \
    --check 'paths./api/conversations/{conversation_id}/credential-bindings/{secret_name}' missing \
    --save F12.discovery/openapi
  control-agent-server api GET /server_info --auth none --expect 200 \
    --check capabilities contains credential_binding_v1 \
    --check capabilities contains credential_binding_readiness_probe_v1 \
    --check capabilities contains credential_binding_activation_guard_v1 --save F12.discovery/server-info
  ```
  运行时路由已文档化。 调度器路由不支持，但服务器通过其能力通告绑定合同。
- **运行时信息(`F12.runtime-info`)。**读取 `N` 的运行时，然后读取嵌入副本。
  ```sh
  control-agent-server api GET "/api/conversations/$N/runtime" --expect 200 \
    --check runtime_status eq available --check can_resume eq true --check runtime_error eq null \
    --save F12.runtime-info/runtime
  control-agent-server api GET "/api/conversations/$N" --expect 200 \
    --check runtime_info.runtime_status eq available --check runtime_info.can_resume eq true \
    --save F12.runtime-info/conversation
  control-agent-server api GET /api/conversations/search --query limit=100 --expect 200 --quiet \
    --check items.0.runtime_info.runtime_status eq available
  control-agent-server api GET /api/conversations --query "ids=$N" --expect 200 \
    --check 0.runtime_info.runtime_status eq available --check 0.runtime_info.can_resume eq true
  ```
  每张视图报告 `available`，可恢复，无错误。
- **重新配置(`F12.runtime-reprovision`)。**本地模式无需提供任何内容； 呼叫重新报告并且没有触及任何内容。
  ```sh
  EN=$(control-agent-server api GET "/api/conversations/$N/events/count" --field .)
  control-agent-server state cat owner_lease.json --conversation "$N" --check generation eq 1
  control-agent-server api POST "/api/conversations/$N/runtime/reprovision" --expect 200 \
    --check runtime_status eq available --check can_resume eq true --check runtime_error eq null \
    --save F12.runtime-reprovision/reprovision
  control-agent-server api POST "/api/conversations/$N/runtime/reprovision" --json '{"qa": "ignored"}' --expect 200 \
    --check runtime_status eq available
  control-agent-server api GET "/api/conversations/$N" --check execution_status eq idle
  control-agent-server api GET "/api/conversations/$N/events/count" --check . eq "$EN"
  control-agent-server state cat owner_lease.json --conversation "$N" --check generation eq 1
  ```
  两个调用返回相同的对象 `GET .../runtime`。 状态、事件计数和租约生成都未改变。
- **运行时错误 (`F12.runtime-errors`)。**未知 ID、格式错误的 ID、无密钥。
  ```sh
  control-agent-server api GET "/api/conversations/$NOPE/runtime" --expect 404 --check detail eq 'Not Found' --save F12.runtime-errors/unknown
  control-agent-server api POST "/api/conversations/$NOPE/runtime/reprovision" --expect 404 --check detail eq 'Not Found' --save F12.runtime-errors/unknown-reprovision
  control-agent-server api GET /api/conversations/not-a-uuid/runtime --expect 422 --check detail.0.type eq uuid_parsing
  control-agent-server api POST /api/conversations/not-a-uuid/runtime/reprovision --expect 422 --check detail.0.type eq uuid_parsing
  control-agent-server api GET "/api/conversations/$N/runtime" --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api POST "/api/conversations/$N/runtime/reprovision" --auth none --expect 401 --check detail eq Unauthorized
  ```
  404 `Not Found`、422 `uuid_parsing` 和 401 `Unauthorized`，对于所有路由。
- **TypeScript 客户端 (`F12.ts-client`).** `ConversationClient` 来自 `clients/typescript/dist` 中构建的客户端（缺失时在此处构建）。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  F="$AGENT_SERVER_VERIFY_RUN/fixtures"
  cat > "$F/qa-f12-ts.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { ConversationClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const [cid, nope] = process.argv.slice(2);
  const host = process.env.AGENT_SERVER_URL;
  const client = new ConversationClient({ host, apiKey: process.env.SESSION_API_KEY });
  const available = { runtime_status: 'available', can_resume: true, runtime_error: null };
  assert.deepEqual(await client.getRuntime(cid), available);
  assert.deepEqual(await client.reprovisionRuntime(cid), available);
  assert.deepEqual((await client.getConversation(cid)).runtime_info, available);
  await assert.rejects(client.getRuntime(nope), (e) => e.status === 404);
  await assert.rejects(client.reprovisionRuntime(nope), (e) => e.status === 404);
  await assert.rejects(new ConversationClient({ host }).getRuntime(cid), (e) => e.status === 401);
  console.log('TS_RUNTIME_OK');
  JS
  control-agent-server exec --expect-output TS_RUNTIME_OK --save F12.ts-client/program -- node "$F/qa-f12-ts.mjs" "$N" "$NOPE"
  ```
  每个断言都成立：同一个 `available` 对象可以从三个角度查看，404
  `HttpError` 表示两种方法中的未知 id，以及没有密钥的 401。
- **暂停释放一切(`F12.sandbox-pause-releases`)。** `N` 和
  `R` 已加载并持有租约； 首先是被拒绝的电话，然后是真正的电话。
  ```sh
  control-agent-server api GET "/api/conversations/$R/events/count" --expect 200
  control-agent-server state ls 'server/workspace/conversations/*/owner_lease.json' --expect-min 2
  ER=$(control-agent-server api GET "/api/conversations/$R/events/count" --field .)
  COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server state ls 'server/workspace/conversations/*/owner_lease.json' --expect-min 2
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204 --save F12.sandbox-pause-releases/pause \
    | jq -e '.response.body == ""'
  control-agent-server state ls 'server/workspace/conversations/*/owner_lease.json' --expect-count 0
  control-agent-server api GET "/api/conversations/$N" --expect 200 --check execution_status eq idle
  control-agent-server api GET "/api/conversations/$R" --expect 200 --check execution_status eq finished --save F12.sandbox-pause-releases/after
  control-agent-server api GET /api/conversations/count --check . eq "$COUNT"
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  ```
  401状态码会保留两个租约。 真实调用返回204无内容，所有租约文件都已消失，所有会话仍然列出，状态（从目录中获取）仍然有效，第二次调用是无操作的204。
- **卸载对话的运行时 (`F12.runtime-cold`)。**在未加载任何内容时以及重新启动后读取运行时。
  ```sh
  control-agent-server api GET "/api/conversations/$N/runtime" --expect 200 --check runtime_status eq available --save F12.runtime-cold/after-pause
  control-agent-server api POST "/api/conversations/$R/runtime/reprovision" --expect 200 --check runtime_status eq available
  control-agent-server state ls 'server/workspace/conversations/*/owner_lease.json' --expect-count 0
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$R/runtime" --expect 200 --check runtime_status eq available --check can_resume eq true --save F12.runtime-cold/after-restart
  control-agent-server state ls 'server/workspace/conversations/*/owner_lease.json' --expect-count 0
  ```
  运行时读取目录：在重启之前或之后没有租赁文件。
- **暂停后重新加载(`F12.sandbox-pause-rehydrate`)。**加载`R`，暂停（上一个圆点的重启不在中间），读取其事件，然后在DeepSeek闪屏上再次运行。
  ```sh
  ER=$(control-agent-server api GET "/api/conversations/$R/events/count" --field .)
  AR=$(control-agent-server conversation events "$R" --kinds ActionEvent,MessageEvent --contains '"source": "agent"' --expect-min 1 | jq -e '.matching')
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server state ls --conversation "$R" owner_lease.json --expect-count 0
  control-agent-server api GET "/api/conversations/$R/events/count" --expect 200 --check . eq "$ER" --save F12.sandbox-pause-rehydrate/events
  control-agent-server state cat owner_lease.json --conversation "$R" --check generation eq 1 --check owner_instance_id exists
  control-agent-server conversation send "$R" --text 'Reply with the single word again, then finish.' --wait --until finished --timeout 180
  control-agent-server api GET "/api/conversations/$R" --check execution_status eq finished --save F12.sandbox-pause-rehydrate/after-run
  control-agent-server api GET "/api/conversations/$R/events/count" --check . gt "$ER"
  control-agent-server conversation events "$R" --kinds ActionEvent,MessageEvent --contains '"source": "agent"' \
    | jq -e --argjson before "$AR" '.matching > $before'
  ```
  暂停会移除 `R`'s 资源租赁。 第一个事件读取后再次加载它（带有事件日志的新的租赁文件），并且对话继续进行
  `finished` 再次至少有一个新的智能体操作或消息，因此模型确实在重新加载的对话上运行。
- **暂停正在运行的对话 (`F12.sandbox-pause-running`)。** `H` 的模型调用挂起，因此当暂停到来时运行正在进行中。
  ```sh
  H=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
  control-agent-server ws start "/sockets/events/$H" --name f12-running --duration 300
  control-agent-server ws read f12-running --expect-kind ConversationStateUpdateEvent --wait 15
  control-agent-server conversation send "$H" --text 'QA_F12_RUNNING'
  control-agent-server conversation wait "$H" --until running --timeout 30
  control-agent-server sink read --name qa-f12-hang --expect-min 1 --wait 15
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204 --expect-max-ms 10000 --save F12.sandbox-pause-running/pause
  control-agent-server api GET "/api/conversations/$H" --check execution_status eq paused --save F12.sandbox-pause-running/after
  control-agent-server ws read f12-running --contains '"key": "execution_status", "value": "paused"' --wait 10
  control-agent-server ws stop f12-running --kinds PauseEvent,InterruptEvent --expect-min 2 --save F12.sandbox-pause-running/frames
  control-agent-server conversation events "$H" --kinds PauseEvent --expect-count 1
  control-agent-server conversation events "$H" --kinds InterruptEvent --expect-count 1
  ```
  暂停返回204状态码，但模型调用会持续300秒。 对话 `paused`，日志有 `PauseEvent` 和 `InterruptEvent`，套接字接收了两者，且 `paused` 状态。
- **暂停期间打开的套接字（`F12.sandbox-pause-websocket`），已知bug。**在暂停之前打开的事件套接字和会话套接字，暂停之后发送的消息，以及两种类型的新的套接字作为正控制。
  ```sh
  control-agent-server api GET "/api/conversations/$N/events/count" --expect 200
  control-agent-server ws start "/sockets/events/$N" --name f12-before --duration 300
  control-agent-server ws start "/sockets/session/$N" --name f12-before-session --duration 300
  control-agent-server ws read f12-before --expect-kind ConversationStateUpdateEvent --wait 15
  control-agent-server ws read f12-before-session --kinds sync --expect-min 1 --wait 15
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server ws start "/sockets/events/$N" --name f12-after --duration 300
  control-agent-server ws start "/sockets/session/$N" --name f12-after-session --duration 300
  control-agent-server ws read f12-after --expect-kind ConversationStateUpdateEvent --wait 15
  control-agent-server ws read f12-after-session --kinds sync --expect-min 1 --wait 15
  control-agent-server conversation send "$N" --text 'QA_F12_AFTER_PAUSE' --no-run
  control-agent-server ws stop f12-after --contains QA_F12_AFTER_PAUSE --expect-min 1 --wait 15 --save F12.sandbox-pause-websocket/fresh-socket
  control-agent-server ws stop f12-after-session --contains QA_F12_AFTER_PAUSE --expect-min 1 --wait 15 --save F12.sandbox-pause-websocket/fresh-session-socket
  OLD=$(control-agent-server ws stop f12-before --wait 5 --save F12.sandbox-pause-websocket/old-socket)
  OLD_SESSION=$(control-agent-server ws stop f12-before-session --wait 5 --save F12.sandbox-pause-websocket/old-session-socket)
  printf '%s\n%s\n' "$OLD" "$OLD_SESSION" | jq -c '{close, kinds}'
  echo "$OLD" | jq -c '{opened, close, messages: (.kinds.MessageEvent // 0)} | .closed_or_streaming = (.close != null or .messages >= 1)' \
    | control-agent-server assert --check closed_or_streaming eq true  # bug: value.opened eq True && value.close 缺少 && value.messages eq 0
  echo "$OLD_SESSION" | jq -c '{opened, close, messages: (.kinds["durable:MessageEvent"] // 0)} | .closed_or_streaming = (.close != null or .messages >= 1)' \
    | control-agent-server assert --check closed_or_streaming eq true  # bug: value.opened eq True && value.close 缺少 && value.messages eq 0
  ```
  正确的行为：在暂停之前打开的套接字由服务器关闭（因此客户端重新连接）或保持流式传输。 今天，两者都关闭且无声：`close` 是 `null`，两者都不接收
  `QA_F12_AFTER_PAUSE` 新套接字获取的消息（事件套接字保持其初始 `ConversationStateUpdateEvent`，会话套接字保持其 `sync` 帧和初始状态； 20 秒后还是一样）。 暂停关闭了会话的pub/sub，但没有关闭socket订阅者(`_WebSocketSubscriber`和会话socket的`_SessionSubscriber`继承了无操作`Subscriber.close()`)，留下客户端与一个被丢弃的`EventService`连接关联。 空闲驱逐通过从不驱逐与外部订户的对话来避免这种情况； 停顿没有这样的警卫。 两次捕获都在断言之前保存，因此证据同时成立。
- **不支持的机密名称 (`F12.binding-unsupported-secret`)。**仅
  `CODEX_AUTH_JSON` 是文件凭据。
  ```sh
  control-agent-server api PUT "/api/conversations/$NOPE/credential-bindings/GITHUB_TOKEN" --json "{\"url\": \"$NEVER/cred\"}" \
    --expect 404 --check detail eq 'Not Found' --save F12.binding-unsupported-secret/github-token
  control-agent-server api PUT "/api/conversations/$NOPE/credential-bindings/codex_auth_json" --json "{\"url\": \"$NEVER/cred\"}" --expect 404
  control-agent-server sink read --name qa-f12-never --expect-max 0
  ```
  两者都是404 `Not Found`（名称大小写敏感），源端点从未见过请求。
- **正文验证 (`F12.binding-validation`).**格式错误的请求永远不会到达源。
  ```sh
  B="/api/conversations/$NOPE/credential-bindings/CODEX_AUTH_JSON"
  control-agent-server api PUT "$B" --json "{\"url\": \"$NEVER/cred\", \"qa\": 1}" --expect 422 --check detail.0.type eq extra_forbidden --save F12.binding-validation/extra-key
  control-agent-server api PUT "$B" --json '{"headers": {}}' --expect 422 --check detail.0.type eq missing
  control-agent-server api PUT "$B" --json '{"url": ""}' --expect 422 --check detail.0.type eq string_too_short
  control-agent-server api PUT "$B" --json "{\"url\": \"$NEVER/cred\", \"headers\": {\"X-Qa\": \"\"}}" --expect 422 \
    --check detail.0.msg contains 'Invalid credential binding headers' --save F12.binding-validation/empty-header
  H17=$(python3 -c 'import json; print(json.dumps({f"X-Qa-{i}": "v" for i in range(17)}))')
  control-agent-server api PUT "$B" --json "{\"url\": \"$NEVER/cred\", \"headers\": $H17}" --expect 422 --check detail.0.msg contains 'Invalid credential binding headers'
  LONG_VALUE=$(python3 -c 'print("v" * 8193)')
  control-agent-server api PUT "$B" --json "{\"url\": \"$NEVER/cred\", \"headers\": {\"X-Qa\": \"$LONG_VALUE\"}}" --expect 422 --quiet \
    --check detail.0.msg contains 'Invalid credential binding headers'
  LONG_URL="$NEVER/$(python3 -c 'print("x" * 4096)')"
  control-agent-server api PUT "$B" --json "{\"url\": \"$LONG_URL\"}" --expect 422 --quiet --check detail.0.type eq string_too_long
  control-agent-server api PUT "/api/conversations/$NOPE/credential-bindings/GITHUB_TOKEN" --json '{}' --expect 422 --check detail.0.type eq missing
  control-agent-server api PUT /api/conversations/not-a-uuid/credential-bindings/CODEX_AUTH_JSON --json "{\"url\": \"$NEVER/cred\"}" --expect 422 --check detail.0.type eq uuid_parsing
  control-agent-server api PUT "$B" --auth none --json "{\"url\": \"$NEVER/cred\"}" --expect 401 --check detail eq Unauthorized
  control-agent-server sink read --name qa-f12-never --expect-max 0
  ```
  每个不完整的主体或ID都返回一个422，错误类型为Pydantic（在不支持的`GITHUB_TOKEN`名称下，一个不完整的主体是422，而不是404），没有键是401，源仍然没有请求。
- **待绑定未知 ID (`F12.binding-pending`)。**激活可以在对话之前进行。
  ```sh
  U1=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api PUT "/api/conversations/$U1/credential-bindings/CODEX_AUTH_JSON" \
    --json "{\"url\": \"$SRC/cred\", \"headers\": {\"Authorization\": \"Bearer qa-f12-pending\"}}" --expect 204 --save F12.binding-pending/put \
    | jq -e '.response.body == ""'
  control-agent-server sink read --name qa-f12-cred --contains 'Bearer qa-f12-pending' --expect-min 1 --expect-max 1 --save F12.binding-pending/probe
  control-agent-server sink read --name qa-f12-cred --path /cred --contains '"method": "GET"' --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f12-cred --expect-max 1
  control-agent-server api GET "/api/conversations/$U1" --expect 404
  ```
  204 无内容响应，携带 `GET /cred`
  `Authorization: Bearer qa-f12-pending`; 该对话仍然不存在。
- **来源答案 (`F12.binding-source-statuses`)。**每个回复一个接收器，因为接收器以相同的方式回答每个请求。
  ```sh
  B="/api/conversations/$NOPE/credential-bindings/CODEX_AUTH_JSON"
  S401=$(control-agent-server fixture http-sink --name qa-f12-src-401 --status 401 --body '{}' --print-path)
  S403=$(control-agent-server fixture http-sink --name qa-f12-src-403 --status 403 --body '{}' --print-path)
  S400=$(control-agent-server fixture http-sink --name qa-f12-src-400 --status 400 --body '{}' --print-path)
  S404=$(control-agent-server fixture http-sink --name qa-f12-src-404 --status 404 --body '{}' --print-path)
  S422=$(control-agent-server fixture http-sink --name qa-f12-src-422 --status 422 --body '{}' --print-path)
  S409=$(control-agent-server fixture http-sink --name qa-f12-src-409 --status 409 --body '{}' --print-path)
  S501=$(control-agent-server fixture http-sink --name qa-f12-src-501 --status 501 --body '{}' --print-path)
  SNOTJSON=$(control-agent-server fixture http-sink --name qa-f12-src-notjson --status 200 --body 'not-json' --print-path)
  SNOVERSION=$(control-agent-server fixture http-sink --name qa-f12-src-noversion --status 200 --body '{"value": "{}"}' --print-path)
  SEMPTY=$(control-agent-server fixture http-sink --name qa-f12-src-emptyversion --status 200 --body '{"value": "{}", "version": ""}' --print-path)
  SINT=$(control-agent-server fixture http-sink --name qa-f12-src-intvalue --status 200 --body '{"value": 1, "version": "v1"}' --print-path)
  control-agent-server api PUT "$B" --json "{\"url\": \"$S401/cred\"}" --expect 403 --check detail eq 'Credential binding authorization was rejected' --save F12.binding-source-statuses/source-401
  control-agent-server api PUT "$B" --json "{\"url\": \"$S403/cred\"}" --expect 403 --check detail eq 'Credential binding authorization was rejected' --save F12.binding-source-statuses/source-403
  control-agent-server api PUT "$B" --json "{\"url\": \"$S400/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/source-400
  control-agent-server api PUT "$B" --json "{\"url\": \"$S404/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/source-404
  control-agent-server api PUT "$B" --json "{\"url\": \"$S422/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/source-422
  control-agent-server api PUT "$B" --json "{\"url\": \"$S409/cred\"}" --expect 409 --check detail eq 'Credential binding source changed' --save F12.binding-source-statuses/source-409
  control-agent-server api PUT "$B" --json "{\"url\": \"$S501/cred\"}" --expect 501 --check exception eq '501: Credential binding source is unsupported' --save F12.binding-source-statuses/source-501
  control-agent-server api PUT "$B" --json "{\"url\": \"$SNOTJSON/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/source-not-json
  control-agent-server api PUT "$B" --json "{\"url\": \"$SNOVERSION/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/source-no-version
  control-agent-server api PUT "$B" --json "{\"url\": \"$SEMPTY/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid'
  control-agent-server api PUT "$B" --json "{\"url\": \"$SINT/cred\"}" --expect 422 --check detail eq 'Credential binding source is invalid'
  for name in 401 403 400 404 422 409 501 notjson noversion emptyversion intvalue; do
    control-agent-server sink read --name "qa-f12-src-$name" --path /cred --expect-min 1 --expect-max 1
  done
  control-agent-server api PUT "$B" --json '{"url": "ftp://127.0.0.1/cred"}' --expect 422 --check detail eq 'Credential binding source is invalid' --save F12.binding-source-statuses/ftp-url
  control-agent-server api PUT "$B" --json '{"url": "not a url"}' --expect 422 --check detail eq 'Credential binding source is invalid'
  ```
  每个源状态都按照列表所示映射，每个状态都经过一次探针（没有重试来表示肯定的答案）。 501的编号是
  `{"detail": "Internal Server Error", "exception": "501: ..."}` 就像每 5xx 个； 200个畸形的物体和非http(s) URLs的物体是422。
- **来源不可用 (`F12.binding-source-unavailable`)。**一个 503 源，然后一个关闭的端口。
  ```sh
  S=$(control-agent-server fixture http-sink --name qa-f12-src-503 --status 503 --body '{}' --print-path)
  control-agent-server api PUT "/api/conversations/$NOPE/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$S/cred\"}" \
    --expect 502 --check exception eq '502: Credential binding source is unavailable' --expect-max-ms 5000 \
    --save F12.binding-source-unavailable/source-503 | jq -e '.elapsed_ms >= 750'
  control-agent-server sink read --name qa-f12-src-503 --expect-min 3 --expect-max 3 --save F12.binding-source-unavailable/probes
  control-agent-server api PUT "/api/conversations/$NOPE/credential-bindings/CODEX_AUTH_JSON" --json '{"url": "http://127.0.0.1:9/cred"}' \
    --expect 502 --check exception eq '502: Credential binding source is unavailable' --expect-max-ms 5000 \
    --save F12.binding-source-unavailable/closed-port | jq -e '.elapsed_ms >= 750'
  ```
  三个探测器（分别在0.25秒和0.5秒之间进入，然后在5秒内有502个）。 拒绝连接会以同样的方式重试（至少需要0.75秒）。
- **常规对话，已加载 (`F12.binding-native-too-late`)。**加载`N`，然后尝试绑定它。
  ```sh
  control-agent-server api GET "/api/conversations/$N/events/count" --expect 200
  control-agent-server state ls --conversation "$N" owner_lease.json --expect-count 1
  control-agent-server api PUT "/api/conversations/$N/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" \
    --expect 409 --check detail eq 'Credential binding activation arrived after ACP initialization' --save F12.binding-native-too-late/put
  control-agent-server state cat meta.json --conversation "$N" --check required_runtime_credential_bindings len-eq 0
  ```
  409 无记录的需求。
- **常规对话，未加载(`F12.binding-native-cold`)。**卸载 `N` 时发送相同的绑定，然后加载并暂停。
  ```sh
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server api PUT "/api/conversations/$N/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" --expect 204,409 \
    --save F12.binding-native-cold/put
  control-agent-server api GET "/api/conversations/$N/events/count" --expect 200
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server api GET "/api/conversations/$N/events/count" --expect 200 --save F12.binding-native-cold/events-after-pause
  control-agent-server state cat meta.json --conversation "$N" --check required_runtime_credential_bindings len-eq 0
  ```
  常规对话要么拒绝绑定（409，就像在加载时一样），要么忽略它，然后在下一次暂停后保持可读。 未加载的 PUT 被接受为待处理（204），当 `N` 加载时被丢弃，因为只有 ACP 和 `meta.json` 会处理文件智能体的绑定：凭据保持不变
  `required_runtime_credential_bindings: []`，并且使用具有挂起绑定的 id 创建的常规对话保留其自己的
  `CODEX_AUTH_JSON` 机密。
- **绑定已加载的 ACP Codex 对话 (`F12.binding-live-acp`)。** `A`从未运行过，因此其ACP智能体尚未初始化。
  ```sh
  A=$(control-agent-server conversation start --body-json "{\"agent\": $ACP_AGENT}" --secret CODEX_AUTH_JSON=qa-f12-request-copy --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$A" --check agent.kind eq ACPAgent --check agent.acp_server eq codex
  control-agent-server state cat meta.json --conversation "$A" --check secrets.CODEX_AUTH_JSON exists --check required_runtime_credential_bindings len-eq 0
  control-agent-server api PUT "/api/conversations/$A/credential-bindings/CODEX_AUTH_JSON" \
    --json "{\"url\": \"$SRC/cred\", \"headers\": {\"Authorization\": \"Bearer qa-f12-first\"}}" --expect 204 --save F12.binding-live-acp/put
  control-agent-server sink read --name qa-f12-cred --contains 'Bearer qa-f12-first' --expect-min 1 --expect-max 1
  control-agent-server state cat meta.json --conversation "$A" \
    --check required_runtime_credential_bindings eq '["CODEX_AUTH_JSON"]' --check secrets.CODEX_AUTH_JSON missing
  control-agent-server state grep qa-f12-request-copy --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f12-request-copy --glob 'home/**/*' --expect-none
  control-agent-server api GET "/api/conversations/$A/events/count" --expect 200
  ```
  204; `meta.json` 现在记录需求，不再主持对话 `CODEX_AUTH_JSON`  机密 (因为加密存储过，所以明文grep的输出结果是一样的；) 的 `secrets` 检查就是证据，对话依然清晰。
- **重新绑定(`F12.binding-rebind`)。**与新标头相同的 URL，然后是不同的 URL。

  需要：`F12.binding-live-acp`
  ```sh
  control-agent-server api PUT "/api/conversations/$A/credential-bindings/CODEX_AUTH_JSON" \
    --json "{\"url\": \"$SRC/cred\", \"headers\": {\"Authorization\": \"Bearer qa-f12-second\"}}" --expect 204 --save F12.binding-rebind/same-url
  control-agent-server sink read --name qa-f12-cred --contains 'Bearer qa-f12-second' --expect-min 1 --expect-max 1
  control-agent-server api PUT "/api/conversations/$A/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/other\"}" \
    --expect 409 --check detail eq 'Credential binding activation arrived after ACP initialization' --save F12.binding-rebind/other-url
  control-agent-server state grep qa-f12-second --glob 'fixtures/**/*'
  control-agent-server state grep qa-f12-second --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f12-second --glob 'home/**/*' --expect-none
  control-agent-server state grep qa-f12-first --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f12-first --glob 'home/**/*' --expect-none
  control-agent-server logs --grep "$A" --expect-min 1
  control-agent-server logs --grep 'qa-f12-first|qa-f12-second' --expect-none
  ```
  相同的 URL 重新授权活绑定 (204，用新头字段探测)。 另一个 URL 带有通用的“太晚”消息的 409 错误。 没有写入到服务器的状态，它的 `HOME` 或其日志（其中包含对话的名称）。
- **暂停后需要 (`F12.binding-required-after-pause`)。**暂停一下，然后一路进去。

  需要：`F12.binding-live-acp`
  ```sh
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server api GET "/api/conversations/$A" --expect 200 --check id eq "$A"
  control-agent-server api GET "/api/conversations/$A/runtime" --expect 200 --check runtime_status eq available
  control-agent-server api GET "/api/conversations/$A/events/search" --expect 409 \
    --check detail eq credential_binding_activation_required --check retryable eq true --save F12.binding-required-after-pause/events
  control-agent-server api POST "/api/conversations/$A/run" --expect 409 --check detail eq credential_binding_activation_required
  control-agent-server ws listen "/sockets/events/$A" --expect-close 1013 --duration 10 --save F12.binding-required-after-pause/events-socket \
    | jq -e '.close.reason == "credential_binding_activation_required"'
  control-agent-server ws listen "/sockets/session/$A" --query after_seq=-1 --expect-close 1013 --duration 10
  control-agent-server state ls --conversation "$A" owner_lease.json --expect-count 0
  control-agent-server api PUT "/api/conversations/$A/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" --expect 204 --save F12.binding-required-after-pause/reactivate
  control-agent-server api GET "/api/conversations/$A/events/search" --expect 200 --save F12.binding-required-after-pause/events-after
  control-agent-server state ls --conversation "$A" owner_lease.json --expect-count 1
  ```
  虽然仍然回答，但加载被拒绝，返回409重试，并且两个套接字都关闭，返回1013（没有获取租约）。 在进行一次新的激活后，对话会加载。
- **重新启动后需要 (`F12.binding-required-after-restart`)。**要求在`meta.json`中，因此它存在； 删除是豁免的。

  需要：`F12.binding-live-acp`
  ```sh
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$A/events/count" --expect 409 --check retryable eq true --save F12.binding-required-after-restart/events
  control-agent-server api PUT "/api/conversations/$A/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" --expect 204
  control-agent-server api GET "/api/conversations/$A/events/count" --expect 200 --save F12.binding-required-after-restart/events-after
  control-agent-server state cat meta.json --conversation "$A" --check required_runtime_credential_bindings eq '["CODEX_AUTH_JSON"]'
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  control-agent-server api GET "/api/conversations/$A/events/count" --expect 409
  control-agent-server api DELETE "/api/conversations/$A" --expect 200 --save F12.binding-required-after-restart/delete
  control-agent-server api GET "/api/conversations/$A" --expect 404
  control-agent-server state ls --conversation "$A" meta.json --expect-count 0
  ```
  重启后为409，重新激活后为200，要求仍然记录在案。 即使没有绑定，也需要删除需要绑定的对话（其目录会被删除）。
- **创建时消耗的待定绑定 (`F12.binding-pending-on-create`)。**首先绑定，然后使用该 id 创建对话。
  ```sh
  U2=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api PUT "/api/conversations/$U2/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" --expect 204
  C2=$(control-agent-server conversation start --body-json "{\"conversation_id\": \"$U2\", \"agent\": $ACP_AGENT}" --secret CODEX_AUTH_JSON=qa-f12-create-copy --no-autotitle --print-id)
  test "$C2" = "$U2"
  control-agent-server state cat meta.json --conversation "$U2" \
    --check required_runtime_credential_bindings eq '["CODEX_AUTH_JSON"]' --check secrets.CODEX_AUTH_JSON missing
  control-agent-server state grep qa-f12-create-copy --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f12-create-copy --glob 'home/**/*' --expect-none
  ```
  对话诞生于束缚：需求被记录，请求本身也被记录 `CODEX_AUTH_JSON`  机密未存储。
- **暂停会删除挂起的绑定 (`F12.binding-pending-cleared`)。**绑定、暂停，然后创建。
  ```sh
  U3=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api PUT "/api/conversations/$U3/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" --expect 204
  control-agent-server api POST /api/conversations/prepare-for-sandbox-pause --expect 204
  C3=$(control-agent-server conversation start --body-json "{\"conversation_id\": \"$U3\", \"agent\": $ACP_AGENT}" --secret CODEX_AUTH_JSON=qa-f12-kept-copy --no-autotitle --print-id)
  test "$C3" = "$U3"
  control-agent-server state cat meta.json --conversation "$U3" \
    --check required_runtime_credential_bindings len-eq 0 --check secrets.CODEX_AUTH_JSON exists
  ```
  与 `F12.binding-pending-on-create` 比较：待绑定的会话已消失，因此对话保留了自己的（加密） 机密，无需绑定。
- **配置文件不包括机密 (`F12.binding-profile-scope`)。** ACP 法典智能体简介与 `secret_refs: []`。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f12-noscope --json '{"agent_kind": "acp", "acp_server": "codex", "secret_refs": []}' --expect 201
  P=$(control-agent-server conversation start --agent-profile qa-f12-noscope --no-autotitle --print-id)
  control-agent-server state cat meta.json --conversation "$P" --check launched_agent_profile.secret_refs len-eq 0
  control-agent-server api PUT "/api/conversations/$P/credential-bindings/CODEX_AUTH_JSON" --json "{\"url\": \"$SRC/cred\"}" \
    --expect 403 --check detail eq 'Credential binding authorization was rejected' --save F12.binding-profile-scope/put
  control-agent-server state cat meta.json --conversation "$P" --check required_runtime_credential_bindings len-eq 0
  control-agent-server api DELETE /api/agent-profiles/qa-f12-noscope --expect 200
  ```
  403（在源被探测后）且无记录。 之后，该档案被移除。
- **从运行时启动的配置文件`F12.runtime-launched-profile`).** 另一个本地服务器启动了 `OH_RUNTIME_LAUNCHED_PROFILE`，作为… Docker 父容器每开始一次会话。 翻译：变量在创建时由任何服务器读取，因此不需要容器。
  ```sh
  LPID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  LSRC=$(control-agent-server fixture http-sink --name qa-f12-lp-cred --status 200 --body '{"value": "{}", "version": "qa-v1"}' --print-path)
  LP=$(control-agent-server launch --new --name f12-launched-profile --print-run \
    --env "OH_RUNTIME_LAUNCHED_PROFILE={\"agent_profile_id\": \"$LPID\", \"revision\": 7, \"secret_refs\": [\"QA_F12_ALLOWED\"]}")
  trap 'control-agent-server stop --run "$LP" >/dev/null 2>&1 || true' EXIT
  L=$(control-agent-server conversation start --run "$LP" --body-json "{\"agent\": $ACP_AGENT}" --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$L" --run "$LP" --check launched_agent_profile.agent_profile_id eq "$LPID" \
    --check launched_agent_profile.revision eq 7 --check launched_agent_profile.secret_refs eq '["QA_F12_ALLOWED"]' \
    --save F12.runtime-launched-profile/conversation
  control-agent-server state cat meta.json --run "$LP" --conversation "$L" --check launched_agent_profile.agent_profile_id eq "$LPID"
  control-agent-server api POST /api/agent-profiles/qa-f12-own --run "$LP" --json '{"agent_kind": "acp", "acp_server": "codex", "secret_refs": ["CODEX_AUTH_JSON"]}' --expect 201
  O=$(control-agent-server conversation start --run "$LP" --agent-profile qa-f12-own --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$O" --run "$LP" --check launched_agent_profile.agent_profile_id ne "$LPID" \
    --check launched_agent_profile.secret_refs eq '["CODEX_AUTH_JSON"]'
  control-agent-server api PUT "/api/conversations/$O/credential-bindings/CODEX_AUTH_JSON" --run "$LP" --json "{\"url\": \"$LSRC/cred\"}" --expect 204
  control-agent-server api PUT "/api/conversations/$L/credential-bindings/CODEX_AUTH_JSON" --run "$LP" --json "{\"url\": \"$LSRC/cred\"}" \
    --expect 403 --check detail eq 'Credential binding authorization was rejected' --save F12.runtime-launched-profile/binding
  control-agent-server state cat meta.json --run "$LP" --conversation "$L" --check required_runtime_credential_bindings len-eq 0
  control-agent-server stop --run "$LP"
  ```
  没有配置的对话记录了运行时的运行时（id，修订7，`secret_refs`），因此绑定被拒绝，且没有记录。 对话从其自身的智能体记录开始，该记录包含了该记录，接受绑定（204）。 机密在创建请求本身中没有过滤：在Docker 模式下，先在父级进行过滤，然后再转发请求(`forward_to_runtime`)。
- **401 上的托管密钥刷新 (`F12.managed-key-refresh`)。**具有刷新变量的第二个服务器； 存根扮演一个托管代理，它拒绝存储的密钥一次（`status:401`），然后回答。
  ```sh
  FINISH_STEP='tool:finish:{"message": "done"}'
  KSRC=$(control-agent-server fixture http-sink --name qa-f12-keysrc --status 200 --body 'qa-f12-fresh-key' --print-path)
  KSTUB=$(control-agent-server fixture llm-stub --name qa-f12-keystub --step status:401 --step "$FINISH_STEP" --print-path)
  K=$(control-agent-server launch --new --name f12-keyrefresh --print-run \
    --env "OH_LLM_API_KEY_REFRESH_URL=$KSRC/key" --env "OH_LLM_API_KEY_REFRESH_BASE_URLS=$KSTUB/v1" \
    --env 'OH_LLM_API_KEY_REFRESH_HEADERS={"X-QA": "${QA_F12_REFRESH_TOKEN}"}' --env QA_F12_REFRESH_TOKEN=qa-f12-refresh-hdr)
  trap 'control-agent-server stop --run "$K" >/dev/null 2>&1 || true' EXIT
  KAGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-stale-key\", \"base_url\": \"$KSTUB/v1\", \"num_retries\": 0}, \"tools\": []}"
  KC=$(control-agent-server conversation start --run "$K" --body-json "{\"agent\": $KAGENT}" --no-autotitle --prompt 'QA_F12_KEY' \
    --wait --until finished --timeout 60 --print-id)
  control-agent-server api GET "/api/conversations/$KC" --run "$K" --check execution_status eq finished --save F12.managed-key-refresh/after
  control-agent-server sink read --name qa-f12-keysrc --path /key --contains '"X-QA": "qa-f12-refresh-hdr"' --expect-min 1 --expect-max 1 \
    --save F12.managed-key-refresh/key-fetch
  control-agent-server sink read --name qa-f12-keysrc --expect-max 1
  control-agent-server sink read --name qa-f12-keystub --contains '"call": 0, "step": {"status": 401}' --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f12-keystub --expect-min 2 --expect-max 2
  control-agent-server logs --run "$K" --grep 'Authentication error; refreshing' --expect-min 1
  control-agent-server state grep qa-f12-fresh-key --run "$K" --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f12-fresh-key --run "$K" --glob 'home/**/*' --expect-none
  control-agent-server stop --run "$K"
  ```
  第一次调用模型时返回401。 服务器一次获取密钥（`GET /key` carrying `X-QA: qa-f12-refresh-hdr`, expanded from
  `${QA_F12_REFRESH_TOKEN}` 在其环境中），重试调用一次并运行完成； 获取的密钥未写入服务器的状态或
  `HOME`. stub 不记录请求头，因此重试所携带的 fetched key 可以通过 SDK 的合约证明（它重试只有一个与存储的键不同的键），而不是观察到的。
- **刷新范围(`F12.managed-key-scope`)。**相同的设置，在允许列表之外有第二个存根，然后是一个空的允许列表。
  ```sh
  FINISH_STEP='tool:finish:{"message": "done"}'
  SSRC=$(control-agent-server fixture http-sink --name qa-f12-keysrc-scope --status 200 --body 'qa-f12-fresh-key' --print-path)
  MSTUB=$(control-agent-server fixture llm-stub --name qa-f12-managed --step status:401 --step "$FINISH_STEP" \
    --step status:401 --step "$FINISH_STEP" --print-path)
  BYOK=$(control-agent-server fixture llm-stub --name qa-f12-byok --step status:401 --step "$FINISH_STEP" --print-path)
  K=$(control-agent-server launch --new --name f12-keyscope --print-run \
    --env "OH_LLM_API_KEY_REFRESH_URL=$SSRC/key" --env "OH_LLM_API_KEY_REFRESH_BASE_URLS=$MSTUB/v1")
  trap 'control-agent-server stop --run "$K" >/dev/null 2>&1 || true' EXIT
  MAGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-stale-key\", \"base_url\": \"$MSTUB/v1\", \"num_retries\": 0}, \"tools\": []}"
  BAGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-byok-key\", \"base_url\": \"$BYOK/v1\", \"num_retries\": 0}, \"tools\": []}"
  control-agent-server conversation start --run "$K" --body-json "{\"agent\": $MAGENT}" --no-autotitle --prompt 'QA_F12_MANAGED' \
    --wait --until finished --timeout 60
  control-agent-server sink read --name qa-f12-keysrc-scope --expect-min 1 --expect-max 1
  BC=$(control-agent-server conversation start --run "$K" --body-json "{\"agent\": $BAGENT}" --no-autotitle --prompt 'QA_F12_BYOK' \
    --wait --until error --timeout 60 --print-id)
  control-agent-server api GET "/api/conversations/$BC" --run "$K" --check execution_status eq error --save F12.managed-key-scope/byok
  control-agent-server conversation events "$BC" --run "$K" --kinds ConversationErrorEvent --contains LLMAuthenticationError --expect-count 1
  control-agent-server sink read --name qa-f12-byok --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f12-keysrc-scope --expect-max 1
  control-agent-server restart --run "$K" --env 'OH_LLM_API_KEY_REFRESH_BASE_URLS='
  EC=$(control-agent-server conversation start --run "$K" --body-json "{\"agent\": $MAGENT}" --no-autotitle --prompt 'QA_F12_EMPTY' \
    --wait --until error --timeout 60 --print-id)
  control-agent-server conversation events "$EC" --run "$K" --kinds ConversationErrorEvent --contains LLMAuthenticationError --expect-count 1
  control-agent-server sink read --name qa-f12-managed --expect-min 3 --expect-max 3
  control-agent-server sink read --name qa-f12-keysrc-scope --expect-max 1 --save F12.managed-key-scope/no-fetch
  control-agent-server logs --run "$K" --grep 'stays off' --expect-min 1
  control-agent-server stop --run "$K"
  ```
  在范围内的 LLM 刷新 (阳性对照：一次请求，完成)。 的 LLM 在其他情况下 `base_url` 以结尾 `error` 与
  `LLMAuthenticationError` 在一次模型调用之后并且没有获取，尽管它的存根会回答重试。 在重启后，允许列表为空的情况下，同一个管理的 `base_url` 没有钩子（失败关闭，记录为“管理 LLM 密钥刷新保持关闭”）：又一个 401，没有获取，`error`。
- **模型切换后刷新 (`F12.managed-key-switch`)。**刷新一次的范围内对话，然后 `switch_llm` 到同一托管 `base_url` 上的另一个 LLM。
  ```sh
  FINISH_STEP='tool:finish:{"message": "done"}'
  WSRC=$(control-agent-server fixture http-sink --name qa-f12-keysrc-switch --status 200 --body 'qa-f12-fresh-key' --print-path)
  WSTUB=$(control-agent-server fixture llm-stub --name qa-f12-switch --step status:401 --step "$FINISH_STEP" \
    --step status:401 --step "$FINISH_STEP" --print-path)
  K=$(control-agent-server launch --new --name f12-keyswitch --print-run \
    --env "OH_LLM_API_KEY_REFRESH_URL=$WSRC/key" --env "OH_LLM_API_KEY_REFRESH_BASE_URLS=$WSTUB/v1")
  trap 'control-agent-server stop --run "$K" >/dev/null 2>&1 || true' EXIT
  WAGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-stale-key\", \"base_url\": \"$WSTUB/v1\", \"num_retries\": 0}, \"tools\": []}"
  WC=$(control-agent-server conversation start --run "$K" --body-json "{\"agent\": $WAGENT}" --no-autotitle --prompt 'QA_F12_SWITCH_1' \
    --wait --until finished --timeout 60 --print-id)
  control-agent-server sink read --name qa-f12-keysrc-switch --expect-min 1 --expect-max 1
  control-agent-server api POST "/api/conversations/$WC/switch_llm" --run "$K" \
    --json "{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-switched-key\", \"base_url\": \"$WSTUB/v1\", \"num_retries\": 0, \"usage_id\": \"qa-f12-switched\"}}" \
    --expect 200 --save F12.managed-key-switch/switch
  control-agent-server api GET "/api/conversations/$WC" --run "$K" --check agent.llm.usage_id eq qa-f12-switched --check agent.llm.base_url eq "$WSTUB/v1"
  control-agent-server conversation send "$WC" --run "$K" --text 'QA_F12_SWITCH_2'
  control-agent-server sink read --name qa-f12-switch --expect-min 3 --wait 30
  control-agent-server conversation wait "$WC" --run "$K" --until finished,error --timeout 60
  control-agent-server sink read --name qa-f12-keysrc-switch --expect-min 2 --expect-max 2 --save F12.managed-key-switch/key-fetch
  control-agent-server api GET "/api/conversations/$WC" --run "$K" --check execution_status eq finished
  control-agent-server stop --run "$K"
  ```
  第一次刷新（阳性对照）。 LLM 通过允许列表 `base_url` 连接，所以它的 401 错误被刷新，就像第一个一样：一次请求，一次重试，然后 `finished`。 `LocalConversation.switch_llm`（`switch_profile`和智能体的LLM对象也安装） 服务器在对话的`agent`发生变化时重新注册刷新钩子，因此钩子不会等待下一次加载（#5890）。
- **Docker 没有守护程序的运行时模式 (`F12.docker-runtime-contract`)。**第二台服务器带有 `OH_CONVERSATION_RUNTIME=docker`。 翻译：路由器自己的答案不需要 Docker 守护进程（启动仅警告它无法列出容器）； 需要运行容器的一切都是`F12.docker-runtime`。 `DELETE .../runtime` 和
  `POST .../runtime/credentials`仅存在于该模式下。 跑步的
  `DOCKER_HOST` 指向不存在的私有套接字，因此即使在安装了 Docker 的主机上，这仍然是无守护程序检查。
  ```sh
  DK=$(control-agent-server launch --new --name f12-docker --env OH_CONVERSATION_RUNTIME=docker \
    --env "DOCKER_HOST=unix://$AGENT_SERVER_VERIFY_RUN/private/no-docker.sock" --print-run)
  trap 'control-agent-server stop --run "$DK" >/dev/null 2>&1 || true' EXIT
  control-agent-server api GET /server_info --run "$DK" --auth none --expect 200 --check conversation_runtime eq docker
  Z=$(python3 -c 'import uuid; print(uuid.uuid4())')
  U=$(python3 -c 'import uuid; print(uuid.uuid4())')
  DOCKER_501='501: This operation is unavailable in Docker runtime mode'
  control-agent-server api POST "/api/conversations/$Z/fork" --run "$DK" --json '{}' --expect 501 --check exception eq "$DOCKER_501" \
    --save F12.docker-runtime-contract/fork
  control-agent-server api POST "/api/conversations/$Z/switch_llm" --run "$DK" --json '{}' --expect 501 --check exception eq "$DOCKER_501"
  control-agent-server api POST "/api/conversations/$Z/switch_profile" --run "$DK" --json '{}' --expect 501 --check exception eq "$DOCKER_501"
  control-agent-server api PUT "/api/conversations/$Z/credential-bindings/CODEX_AUTH_JSON" --run "$DK" --json "{\"url\": \"$NEVER/cred\"}" \
    --expect 501 --check exception eq "$DOCKER_501" --save F12.docker-runtime-contract/credential-binding
  control-agent-server api PUT "/api/conversations/$Z/credential-bindings/GITHUB_TOKEN" --run "$DK" --json '{}' --expect 501
  control-agent-server sink read --name qa-f12-never --expect-max 0
  control-agent-server api POST "/api/conversations/$Z/run" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server api GET "/api/conversations/$Z/runtime" --run "$DK" --expect 404 --check detail eq 'Conversation not found' \
    --save F12.docker-runtime-contract/runtime-unknown
  control-agent-server api POST "/api/conversations/$Z/runtime/reprovision" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server api DELETE "/api/conversations/$Z/runtime" --run "$DK" --expect 404 --check detail eq 'Conversation not found' --save F12.docker-runtime-contract/release-unknown
  control-agent-server api POST "/api/conversations/$Z/runtime/credentials" --run "$DK" --expect 404 --check detail eq 'Conversation not found' \
    --save F12.docker-runtime-contract/credentials-unknown
  control-agent-server api DELETE "/api/conversations/$Z/runtime" --run "$DK" --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api POST "/api/conversations/$Z/runtime/credentials" --run "$DK" --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server ws listen "/sockets/events/$Z" --run "$DK" --expect-close 1008 --duration 10
  control-agent-server ws listen "/sockets/session/$Z" --run "$DK" --expect-close 1008 --duration 10
  control-agent-server api POST /api/conversations --run "$DK" --expect 400 --check detail eq 'Invalid JSON body'
  control-agent-server api POST /api/conversations --run "$DK" --json '[1]' --expect 422 --check detail eq 'Expected a JSON object'
  control-agent-server api POST /api/conversations --run "$DK" --json '{"workspace": {"kind": "RemoteWorkspace", "host": "http://127.0.0.1:9"}}' \
    --expect 422 --check detail eq 'Docker conversations require a local workspace'
  control-agent-server api POST /api/conversations --run "$DK" --json '{"conversation_id": "not-a-uuid"}' --expect 400 --check detail eq 'Invalid conversation_id'
  control-agent-server state ls --run "$DK" 'home/.openhands/runtime-control/*.json' --expect-count 0
  control-agent-server api POST /api/conversations --run "$DK" \
    --json "{\"conversation_id\": \"$U\", \"agent\": {\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-f12-docker-key\"}, \"tools\": []}}" \
    --expect 502 --check exception eq '502: Could not create conversation container' --save F12.docker-runtime-contract/create
  control-agent-server state ls --run "$DK" "home/.openhands/runtime-control/${U//-/}.json" --expect-count 1
  control-agent-server api GET "/api/conversations/$U/runtime" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server api POST "/api/conversations/$U/runtime/reprovision" --run "$DK" --expect 502 \
    --check exception eq '502: Could not start conversation container'
  control-agent-server ws listen "/sockets/events/$U" --run "$DK" --expect-close 1011 --duration 10
  control-agent-server api DELETE "/api/conversations/$U" --run "$DK" --expect 200 --save F12.docker-runtime-contract/delete
  control-agent-server state ls --run "$DK" "home/.openhands/runtime-control/${U//-/}.json" --expect-count 0
  control-agent-server api DELETE "/api/conversations/$U" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server stop --run "$DK"
  ```
  这四个不可代理的操作是 501（在 `exception` 中，类似于所有 5xx），对于不存在的 ID，甚至对于本地路由会拒绝的体，以及绑定源从不被联系。 未知的id是404
  `Conversation not found`（Docker路由器的写法； 本地运行时路由显示为 `Not Found`），套接字以 1008 关闭。 在写入任何内容之前，格式错误的创建都会被拒绝。 格式良好的创建会写入运行时清单，无法启动容器（502）并留下
  清单：对话还没有 `meta.json`，因此运行时信息为 404，
  while reprovision and the socket try to start the container (502, close
  1011). 删除对话会删除清单。
- **Docker 带有守护程序的运行时 (`F12.docker-runtime`)。**
  需求：`docker`

  前提条件：在本菜谱之前拉取所选镜像。 默认为
  发布的最小图像，在没有浏览器堆栈的情况下执行相同的Docker生命周期。 覆盖 `AGENT_SERVER_VERIFY_DOCKER_IMAGE` 以测试不同的构建图像。 记录其摘要和孩子的
  `/server_info`：外部结帐和内部图像可能有所不同。 该配方创建对话但不调用它们的LLM。
  ```sh
  IMAGE=${AGENT_SERVER_VERIFY_DOCKER_IMAGE:-ghcr.io/openhands/agent-server:1.55.1-python-minimal}
  docker image inspect "$IMAGE" >/dev/null
  DK=$(control-agent-server launch --new --name f12-docker-live --print-run \
    --config-json "$(jq -nc --arg image "$IMAGE" '{conversation_runtime:"docker",conversation_image:$image,enable_browser:false,conversation_container_memory:"1g",conversation_container_cpus:1,conversation_container_pids_limit:256}')")
  INNER=
  trap 'if [ -n "$INNER" ]; then control-agent-server stop --run "$INNER" >/dev/null 2>&1 || true; fi; control-agent-server stop --run "$DK" >/dev/null 2>&1 || true' EXIT
  control-agent-server doctor --run "$DK"
  control-agent-server exec --run "$DK" --save F12.docker-runtime/image -- docker image inspect \
    --format '{{.Id}} {{json .RepoDigests}}' "$IMAGE"
  control-agent-server api POST /api/profiles/qa-docker-llm --run "$DK" \
    --json '{"llm":{"model":"openai/qa-no-call","api_key":"qa-docker-placeholder"}}' --expect 201
  control-agent-server api POST /api/agent-profiles/qa-docker-profile --run "$DK" \
    --json '{"llm_profile_ref":"qa-docker-llm","tools":[],"mcp_server_refs":[]}' --expect 201
  PROFILE_ID=$(control-agent-server api GET /api/agent-profiles/qa-docker-profile --run "$DK" --expect 200 --field profile.id)
  CID=$(control-agent-server api POST /api/conversations --run "$DK" \
    --json "{\"agent_profile_id\":\"$PROFILE_ID\",\"autotitle\":false}" --expect 201 --field id --timeout 180 --save F12.docker-runtime/create)
  OWNER=$(python3 -c 'import hashlib,sys; r=sys.argv[1]; print(hashlib.sha256(f"{r}/server/workspace/conversations\0{r}/home/.openhands".encode()).hexdigest()[:24])' "$DK")
  CONTAINER=$(docker ps -q --filter "label=ai.openhands.runtime-owner=$OWNER")
  control-agent-server assert --value "$CONTAINER" --check . matches '^[0-9a-f]{12}$'
  control-agent-server exec --run "$DK" --save F12.docker-runtime/resources \
    --expect-output '1073741824 1000000000 256 ["ALL"] ["no-new-privileges"]' -- \
    docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.HostConfig.PidsLimit}} {{json .HostConfig.CapDrop}} {{json .HostConfig.SecurityOpt}}' "$CONTAINER"
  control-agent-server api GET "/api/conversations/$CID/runtime" --run "$DK" --expect 200 \
    --check runtime_status eq available --check can_resume eq true --save F12.docker-runtime/runtime-available
  QA_DOCKER_KEY=$(control-agent-server api POST "/api/conversations/$CID/runtime/credentials" --run "$DK" --expect 200 --field session_api_key --unsafe-unredacted)
  export QA_DOCKER_KEY
  control-agent-server assert --value "${#QA_DOCKER_KEY}" --check . ge 32
  INNER=$(control-agent-server attach --url "http://$(docker port "$CONTAINER" 8000/tcp)" --key-env QA_DOCKER_KEY --name f12-docker-child --print-run)
  unset QA_DOCKER_KEY
  control-agent-server api GET "/api/conversations/$CID" --run "$INNER" --expect 200 --quiet \
    --check launched_agent_profile.agent_profile_id eq "$PROFILE_ID" --check launched_agent_profile.revision eq 0 --save F12.docker-runtime/credential-auth-profile
  control-agent-server api GET /server_info --run "$INNER" --auth none --expect 200 --save F12.docker-runtime/child-info
  control-agent-server api POST "/api/conversations/$CID/events" --run "$DK" \
    --json '{"role":"user","content":[{"type":"text","text":"QA_DOCKER_RETAINED_EVENT"}],"run":false}' \
    --expect 200 --check success eq true --save F12.docker-runtime/message
  control-agent-server api GET "/api/conversations/$CID/events/search" --run "$DK" --expect 200 \
    --check items.1.llm_message.content.0.text eq QA_DOCKER_RETAINED_EVENT --save F12.docker-runtime/history-before
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" --run "$DK" \
    --json '{"command":"printf qa-docker-live > /workspace/qa-docker-live.txt"}' --expect 200 --check exit_code eq 0 --save F12.docker-runtime/write
  control-agent-server api GET "/api/conversations/$CID/file/download" --run "$DK" --query path=/workspace/qa-docker-live.txt \
    --expect 200 --save F12.docker-runtime/file-before
  control-agent-server api GET "/api/conversations/$CID/file/download" --run "$DK" --query path=/workspace/qa-docker-live.txt \
    --header 'X-Expose-Secrets: plaintext' --expect 422 --check detail eq 'Runtime secret exposure is unsupported' --save F12.docker-runtime/expose-refused
  control-agent-server api DELETE "/api/conversations/$CID/runtime" --run "$DK" --expect 204 --save F12.docker-runtime/release
  control-agent-server stop --run "$INNER"
  INNER=
  control-agent-server api GET "/api/conversations/$CID/runtime" --run "$DK" --expect 200 \
    --check runtime_status eq missing --check can_resume eq true --save F12.docker-runtime/runtime-missing
  control-agent-server api GET "/api/conversations/$CID" --run "$DK" --expect 200 --quiet --check id eq "$CID" --save F12.docker-runtime/catalog-after-release
  control-agent-server api GET "/api/conversations/$CID/events/search" --run "$DK" --expect 200 \
    --check items.1.llm_message.content.0.text eq QA_DOCKER_RETAINED_EVENT --save F12.docker-runtime/history-after-release
  control-agent-server api GET "/api/conversations/$CID/runtime" --run "$DK" --expect 200 --check runtime_status eq missing --save F12.docker-runtime/reads-did-not-resume
  control-agent-server api POST "/api/conversations/$CID/runtime/reprovision" --run "$DK" --expect 200 \
    --check runtime_status eq available --timeout 180 --save F12.docker-runtime/reprovision
  control-agent-server api GET "/api/conversations/$CID/file/download" --run "$DK" --query path=/workspace/qa-docker-live.txt \
    --expect 200 --raw-out "$DK/evidence/F12.docker-runtime/file-content.txt" --save F12.docker-runtime/file-after
  control-agent-server exec --run "$DK" --save F12.docker-runtime/content-proof --expect-output qa-docker-live -- \
    cat "$DK/evidence/F12.docker-runtime/file-content.txt"
  control-agent-server api DELETE "/api/conversations/$CID/runtime" --run "$DK" --expect 204
  control-agent-server restart --run "$DK" --config-json '{"conversation_storage_retention_days":0.00001}'
  control-agent-server doctor --run "$DK"
  control-agent-server api GET "/api/conversations/$CID/runtime" --run "$DK" --expect 200 --check can_resume eq false \
    --until-ok 330 --timeout 20 --save F12.docker-runtime/archive-runtime
  control-agent-server api GET "/api/conversations/$CID" --run "$DK" --expect 200 --quiet --save F12.docker-runtime/archive-catalog
  control-agent-server api GET "/api/conversations/$CID/events/search" --run "$DK" --expect 200 \
    --check items.1.llm_message.content.0.text eq QA_DOCKER_RETAINED_EVENT --save F12.docker-runtime/archive-history
  control-agent-server api POST "/api/conversations/$CID/runtime/reprovision" --run "$DK" --expect 410 \
    --check detail eq 'Conversation runtime was archived; its history is read-only' --save F12.docker-runtime/archive-refuses-resume
  control-agent-server api DELETE "/api/conversations/$CID" --run "$DK" --expect 200 --save F12.docker-runtime/delete
  control-agent-server api GET "/api/conversations/$CID" --run "$DK" --expect 404 --save F12.docker-runtime/deleted
  control-agent-server stop --run "$DK"
  ```
  运行时发布保留了工作区、配置来源和可读历史。 reprovision恢复文件字节。 运行时的五分钟维护定时器是故意被最后的检查执行的。 保留后，运行时不可恢复，但历史得以保留，删除仍然成功。 凭据直接捕获并用于认证子访问。 不要保存或打印原始凭据交换。 容器检查仅限于此运行的主人标签。

  事件历史记录由外部已持久化目录 (PR #5429) 提供，因此其路由不再证明代理的 `X-Expose-Secrets` 拒绝。 上面的文件下载路由遍历代理并验证了422。

- **Docker 运行时启动截止时间 (`F12.docker-startup-timeout`).**
  需求：`docker`

  将选定的图像拉到配方之前。
  ```sh
  IMAGE=${AGENT_SERVER_VERIFY_DOCKER_IMAGE:-ghcr.io/openhands/agent-server:1.55.1-python-minimal}
  docker image inspect "$IMAGE" >/dev/null
  BAD=$(control-agent-server launch --new --name f12-docker-short-deadline --print-run \
    --config-json "$(jq -nc --arg image "$IMAGE" '{conversation_runtime:"docker",conversation_image:$image,enable_browser:false,conversation_container_memory:"1g",conversation_container_startup_timeout:0.01}')")
  trap 'control-agent-server stop --run "$BAD" >/dev/null 2>&1 || true' EXIT
  control-agent-server doctor --run "$BAD"
  SHORT_CID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api POST /api/conversations --run "$BAD" \
    --json "{\"conversation_id\":\"$SHORT_CID\",\"agent\":{\"llm\":{\"model\":\"openai/qa-no-call\",\"api_key\":\"qa\"},\"tools\":[]}}" \
    --expect 502 --check exception eq '502: Could not create conversation container' \
    --expect-max-ms 45000 --timeout 60 --save F12.docker-startup-timeout/startup-deadline
  control-agent-server logs --run "$BAD" --grep 'failed to become healthy in time' --expect-min 1
  SHORT_OWNER=$(python3 -c 'import hashlib,sys; r=sys.argv[1]; print(hashlib.sha256(f"{r}/server/workspace/conversations\0{r}/home/.openhands".encode()).hexdigest()[:24])' "$BAD")
  control-agent-server exec --run "$BAD" --save F12.docker-startup-timeout/startup-cleanup -- \
    docker ps -aq --filter "label=ai.openhands.runtime-owner=$SHORT_OWNER"
  control-agent-server assert --value "$(docker ps -aq --filter "label=ai.openhands.runtime-owner=$SHORT_OWNER")" --check . eq ''
  control-agent-server api DELETE "/api/conversations/$SHORT_CID" --run "$BAD" --expect 200 --save F12.docker-startup-timeout/failed-create-delete
  control-agent-server state ls --run "$BAD" "home/.openhands/runtime-control/${SHORT_CID//-/}.json" --expect-count 0
  control-agent-server stop --run "$BAD"
  ```
  同一个真实图像被故意设置为10毫秒的不可达健康期限。 502和超时日志确定原因。 45s 响应绑定包括 Docker 启动和关闭开销。 容器失败之前，映像就已经被删除了。 这是一次准备就绪失败测试，而不是说每个主机都能在10毫秒内初始化容器。

<a id="gotchas"></a>

## 陷阱

- 在本地运行时模式下，`GET /api/conversations/{id}`和运行时路由读取目录并且从不加载对话； 事件路由、`/run`、消息发布和套接字都可以。 Docker 模式还可以从其外部目录提供已持久化事件历史记录，而无需启动容器 (#5429)。 `owner_lease.json` 文件（在名为 id 无下划线的会话目录中的文件）仅存在于已加载的会话中，因此它们是可见的“已加载”信号。 租赁本身（续约、接管、第二次）是F31。
- 本地运行时始终报告 `available` / `can_resume: true`，即使对于在凭据绑定到达之前每次加载都被拒绝的会话也是如此； 运行时视图不是绑定的准备信号。
- `prepare-for-sandbox-pause` 在独占生命周期锁下立即卸载服务器的每个会话； 每次飞行运行最多等待 10 秒。 关闭一个会话失败后，其他会话关闭后会显示为 500，然后保留挂起的绑定。 打开的套接字保持连接到已关闭的服务 (`F12.sandbox-pause-websocket`)，因此客户端必须在暂停后自行重新连接。
- `sink read --wait` 进行投票，直到 `--expect-min` 成立； 在 `F12.sandbox-pause-running` 中的在途模型调用，在 LLM's 的调用
  在断言任何内容之前都会以这种方式等待 `F12.managed-key-switch`。
- 绑定路由在查看对话之前会探测源，因此即使是 403（配置文件范围）或 409（太晚）也会花费一个源请求。 它验证机密名称之前的正文（名称不受支持的错误正文是 422，而不是 404）。
- 从绑定路由返回的 204 不意味着对话存在：未知的 id 会得到一个待绑定的会话，该会话会保留在内存中直到创建或加载该 id，暂停，或者服务器停止。
- “太晚”409 消息 (`... arrived after ACP initialization`) 还用于现有绑定上的不同 URL 和常规智能体。
- 5xx 答案被服务器的异常处理程序重写为
  `{"detail": "Internal Server Error", "exception": "<status>: <detail>"}`，所以501和502把原因放在`exception`中。
- 从服务器进程通过 `httpx` 到达源； Launched 运行 put `127.0.0.1` 和 `localhost` in `NO_PROXY`，环回源需要在代理后面。
- HTTP 汇流管每次请求都返回相同的状态，因此每个源行为需要有自己的汇流管，且序列（503 然后 200）无法编程。
- 刷新凭据（`PUT url` 与 `expected_version`）仅发生在正在运行的 Codex ACP 会话内； 如果没有 Codex ACP 二进制文件和 OpenAI 登录，则无法访问它，因此该系列仅证明激活、清理、持久化和重新加载防护。
- Docker 运行时模式在启动时选择：Docker 路由器在本地会话路由之前挂载（`api.py`），因此在这样的服务器上，本地运行时、绑定、fork 和 switch 处理程序不可达（被遮蔽，而不是从代码中移除）。 `map routes` 添加了只在Docker运行时模式中存在的路由，因此这两个运行时控制路由位于这个家族的`Routes:`线上，而配方会通过字面路径调用它们。
- 如果没有守护进程，Docker模式的创建仍然会写入
  `runtime-control/<id>.json`（加密会话和密码密钥）在容器启动失败之前； 只有`DELETE /api/conversations/{id}`将其删除。 Docker 路由器的 404 表示 `Conversation not found`，本地路由器
  `Not Found`.
- 每次加载对话（创建、暂停或重启后首次访问）时，管理密钥变量从服务器环境读取。因此，`restart --env` 会改变它们。 只有已解析的 `base_url`（不带尾部斜杠）位于允许列表中的 LLM 才会获得钩子； 刷新 URL 必须以文本形式回答裸密钥，而返回存储密钥的刷新则不需要重试。 `llm-stub` 通过书号回答问题，而不是通过关键字，且不记录请求头：stub的401表示“过期的书号”，而recipes计数器则会调用并执行，而不是读取重试的书号。
