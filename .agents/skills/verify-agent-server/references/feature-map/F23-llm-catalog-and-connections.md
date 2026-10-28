<a id="llm-catalog-and-provider-connections"></a>

# LLM 目录和提供商连接

多么好的模型选择器和凭据屏幕的读写能力。 目录包含三个只读列表，这些列表从安装的LiteLLM包中离线提供，以及SDK的精选列表：每个提供者的名字，每个模型（可选仅一个提供者的），以及按提供者分组的验证模型。 提供者连接是一个命名的、共享的凭据 (`display_name`, `provider`,
`api_key`，可选 `base_url`)，LLM 配置文件参考
`provider_connection_id` 而不是携带自己的密钥，因此下次激活时，一次密钥旋转即可到达每个链接的配置文件。 服务器生成 ID，从不返回密钥（只返回 `api_key_set`），在 REST 使用服务器的加密算法对其进行加密，拒绝读取它无法解密的文件，而不是丢弃密钥，将存储限制在 64 个连接，拒绝删除一个被配置文件或活动设置仍然引用的连接。 ACP 模型发现是一个独立的预对话请求：一个丢弃会话报告真实适配器的模型，而本地启动失败则返回结构化的错误。 两者都没有创建已持久化对话。

资料来源：`openhands-agent-server/openhands/agent_server/llm_router.py`、`openhands-agent-server/openhands/agent_server/provider_connections_router.py`、`openhands-agent-server/openhands/agent_server/acp_router.py`、`openhands-sdk/openhands/sdk/agent/acp_model_discovery.py`、`openhands-sdk/openhands/sdk/llm/provider_connection_store.py`、`openhands-sdk/openhands/sdk/llm/utils/unverified_models.py`、`openhands-sdk/openhands/sdk/llm/utils/verified_models.py`、`clients/typescript/src/client/llm-client.ts`、`clients/typescript/src/client/acp-client.ts`

需求：`llm`、`node`、`network`

Routes: `GET /api/llm/providers`, `GET /api/llm/models`,
`GET /api/llm/models/verified`, `GET /api/llm/provider-connections`,
`POST /api/llm/provider-connections`,
`PATCH /api/llm/provider-connections/{connection_id}`,
`DELETE /api/llm/provider-connections/{connection_id}`, `POST /api/acp/models`

<a id="sub-features"></a>

## 子功能

- `F23.acp-discovery-errors`：`POST /api/acp/models` 需要会话密钥，验证 `agent_settings`，并将丢失的本地可执行文件报告为 HTTP 200，`error.code: ACPSpawnError`，没有模型，也没有新对话； `refresh: true`报告同样的故障； `ACPClient.discoverModels`暴露了相同的结构错误并拒绝未经授权的调用。
- `F23.acp-discovery-live`：真实的 Claude Code ACP 适配器通过 REST 和 TypeScript `ACPClient.discoverModels` 报告其默认和提供的模型； 重复的请求和 `refresh: true` 返回相同的目录，而不保留任何对话或探测目录。
- `F23.auth-required`：所有七个路由均回答 401 `{"detail": "Unauthorized"}`，但没有有效的 `X-Session-API-Key`，并且不会创建任何内容。
- `F23.providers`: `GET /api/llm/providers` 返回 LiteLLM 的提供者名称，已排序且唯一，包括 `deepseek`、`openai` 和 `anthropic`。
- `F23.models`: `GET /api/llm/models` 返回每个 LiteLLM 模型，已排序且唯一，没有 `bedrock` 前缀的 id，包括 `deepseek/deepseek-flash`。
- `F23.models-filter`: `?provider=deepseek` 只返回 DeepSeek 模型（如带有前缀和裸体验证 ID 的模型，例如 ） `deepseek-chat`), `?provider=openrouter` 仅 `openrouter/` ids (a namespaced verified id like `deepseek/deepseek-chat` stays with DeepSeek), 以及一个未知的提供者为空列表。
- `F23.models-no-bedrock`：提供商过滤器列出没有 AWS 仅限基岩的模型 ID（`deepseek.r1-v1:0`、`anthropic.claude-...-v1:0`），因为路线承诺没有 AWS 凭据。
- `F23.verified-models`：`GET /api/llm/models/verified` 按提供商（`openhands`、`anthropic`、`openai`、`deepseek`、`openrouter`、...）对精选模型进行分组，每个列表非空且无重复项。
- `F23.catalog-ts-client`：TypeScript `LLMMetadataClient` 返回与 REST 相同的提供者、模型、过滤模型和验证组，并且错误的密钥会拒绝 `HttpError` 401。
- `F23.conn-create`: `POST /api/llm/provider-connections` 使用服务器生成的 32 十六进制 `id` 回答 201，字段等于 `created_at`/`updated_at` 和 `api_key_set: true`，而不是密钥； `provider`默认为`custom`； 该列表按创建顺序显示相同的条目。
- `F23.conn-key-encrypted`：连接文件`home/.openhands/provider-connections/provider_connections.json`为模式`600`，`schema_version`为1，Fernet`gAAAAA`token为`api_key`； 明文密钥不会出现在任何响应中，并且不会出现在服务器主目录下的任何文件中。
- `F23.no-cipher`: 在没有 `OH_SECRET_KEY` 和会话密钥（没有加密算法）的服务器上，连接的密钥以明文存储在 `600` 文件中，列表永远也不会返回它，激活关联的凭据会应用它。
- `F23.conn-create-validation`缺少或为空的 `api_key` 或 `display_name`，空的 `provider`，129个字符的 `display_name`，以及任何多余的字段 (`extra_headers`，客户端选择的 `id`)都会返回 422 并创建无内容。
- `F23.conn-create-blank-key`：纯空白或已脱敏占位符 (`**********`) `api_key` 会像空占位符一样被拒绝，而不是创建无密钥连接。
- `F23.linked-run`：用`provider_connection_id`保存的配置文件不存储内联键； 激活它会将连接的密钥写入 `agent_settings.llm`，并且从这些设置开始的对话在连接的 DeepSeek 键上运行并结束。
- `F23.conn-update`：`PATCH`重命名连接并设置或清除（`null`）其`base_url`，保留`id`、`created_at`和密钥； 该列表显示更改，并且链接配置文件的下一次激活将应用连接的 `base_url`（并将其清除）。
- `F23.conn-update-validation`：空体，`api_key: null`：“无法清除”，`null` `display_name` 或 `provider`，`display_name` 空的，额外字段返回 422，未知 id 返回 404，None 中的某个返回连接状态。
- `F23.conn-patch-blank-key`：一个 `PATCH`，其 `api_key` 为空、仅包含空白字符或已脱敏格式始终不替换存储的键：链接的下一个激活仍然应用先前的键。
- `F23.conn-rotate-key`：旋转`api_key`将已激活的设置保留在旧密钥上； `PATCH /api/settings` `active_profile` 或 `POST /api/profiles/{name}/activate` 的下一次激活会应用新的密钥，该密钥是提供者接收到的，而旋转回会使得对话重新开始。
- `F23.validate-linked-draft`: `POST /api/profiles/{name}/validate` 里引用了一个连接，它会检查连接的密钥，因此持有工作 DeepSeek 密钥的连接会像使用同一个密钥一样验证 `valid: true`。
- `F23.persist-restart`：连接（id、名称、时间戳、`api_key_set`）在重新启动后保持不变，并且链接的配置文件随后仍可解析密钥。
- `F23.strict-decrypt`：服务器的机密密钥更改后，列出、创建、更新和删除答案400 `api_key is encrypted but cannot be decrypted with the current cipher`并保持文件字节相同； 使用旧钥匙后，一切正常，钥匙完好无损。
- `F23.corrupt-file`：无效的连接文件JSON或具有更新的`schema_version`，使路由回答400而不重写文件； 恢复它会恢复连接。
- `F23.store-busy`：当另一个进程保存存储的锁时，创建等待 30 秒的锁超时并回答 503 `Profile store is busy. Please retry.` 而不创建任何内容。
- `F23.store-busy-responsive`：当连接请求等待存储锁时，服务器不断应答其他请求（3秒内`GET /alive`）。
- `F23.delete-guard`：删除LLM配置文件或活动`agent_settings.llm`引用的连接是409命名引用，并且连接保留。
- `F23.conn-delete`删除未引用的连接会返回 200，并包含其字段 `api_key_set: false`移除它从列表中，并且文件，以及一个第二删除或一个 `PATCH` 那个ID是404。
- `F23.conn-limit`：存储了 64 个连接，创建为 409 `Provider connection limit reached (64). Delete one before adding another.`； 删除一个会释放该插槽。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST（目录）：`GET /api/llm/providers`、`GET /api/llm/models` 以及可选的 `provider` 查询参数、`GET /api/llm/models/verified`。 没有身体； 答案来自已安装的 `litellm` 包和
  `VERIFIED_MODELS`，无需网络访问。
- REST (ACP)：`POST /api/acp/models` 和 `agent_settings`，可选 `secrets` 和 `refresh`。 `available_models` 和 `current_model_id` 来自一次性的 ACP 会话； 启动失败使用响应的 `error` 字段。
  `F23.acp-discovery-errors` 涵盖拒绝请求和本地生成失败；
  `F23.acp-discovery-live` 使用与 F09 相同的 DeepSeek Anthropic 兼容凭据启动真正的 Claude Code 适配器。
- REST（连接）：`GET /api/llm/provider-connections`（JSON数组），
  `POST /api/llm/provider-connections` (`{"display_name": "...", "provider": "deepseek", "api_key": "...", "base_url": null}`, 201), `PATCH /api/llm/provider-connections/{connection_id}`（相同四个字段的任何子集； 只有 `base_url` 可能是 `null`），
  `DELETE /api/llm/provider-connections/{connection_id}`. 回应是
  `{id, display_name, provider, base_url, created_at, updated_at, api_key_set}`.
- 连接生效的地方（第二次查看、其他家庭的路线）：
  `POST /api/profiles/{name}` 与 `llm.provider_connection_id` 保存链接的配置文件（其内联 `api_key` 和 `base_url` 被删除）；
  `GET /api/profiles` 报告 `provider_connection_id`,
  来自连接的 `provider_connection_broken` 和 `api_key_set`；
  `POST /api/profiles/{name}/activate` 和 `PATCH /api/settings` 与
  `active_profile` 将连接解析为 `agent_settings.llm`（`GET /api/settings` 和 `X-Expose-Secrets: plaintext` 显示它）；
  `POST /api/conversations/{conversation_id}/switch_llm` 将其解析为正在运行的对话（模型切换系列），并且
  `POST /api/profiles/{name}/validate` 为草稿 (`F23.validate-linked-draft`) 的预检解决了该问题。
- SDK：没有Python客户端调用这些路由。 进程内代码使用
  `ProviderConnectionStore` 和 `LLMProfileStore(provider_store=...)` (`openhands-sdk/openhands/sdk/llm/`)。 链接配置文件的 `RemoteWorkspace.get_llm()` 通过读取其明文配置文件来解析连接（`F20.sdk-get-llm-linked`，由 #4952 修复）。
- TypeScript客户端：`LLMMetadataClient.getProviders()`、`getModels(provider?)`和`getVerifiedModels()`（`clients/typescript/src/client/llm-client.ts`）； 提供者连接只有生成类型（`clients/typescript/src/generated/agent-server-schema.ts`），没有客户端方法。 `ACPClient.discoverModels(request)`达到`POST /api/acp/models`； 两个 ACP 项目符号都执行此 TypeScript 入口。
- 配置：`OH_PERSISTENCE_DIR`（店铺位于
  `provider-connections/` 在其下，否则 `~/.openhands`), `OH_SECRET_KEY`（密码； 如果没有它，则使用会话密钥，并且没有密钥都不会以明文形式存储，`F23.no-cipher`）。
- Agent Canvas 从目录路由填充其模型选择器，并通过连接路由管理共享密钥（仅限上下文）。
- 食谱：`api` 驾驶每条路线； `state cat`/`state grep` read the store at rest; `restart`, `restart --rotate-机密-key` 和
  `restart --restore-secret-key`到达持久化并且密码改变；
  `launch --new --no-auth --no-secret-key` 给出没有密码的第二个服务器； `conversation start`证明已解析的密钥达到DeepSeek；
  `exec` 运行 TypeScript 程序，64 个连接填充为 `curl`。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行处于实时状态并已导出（`launch --new`，默认标志：会话密钥和 `OH_SECRET_KEY` 密码），`doctor` 正常，并且尚不存在提供者连接。
- 模型支持和真实关键连接项目符号需要 `$DEEPSEEK_API_KEY`；
  `F23.linked-run` 保存用于稍后将设置移出连接的 DeepSeek 预设。 下面的块创建测试夹具目录 `F23` 并写入 `ts_catalog.mjs`，即 TypeScript 客户端程序。 `node` 从构建的客户端运行它（`clients/typescript/dist`，缺失时由项目符号构建）； `jq`,
  `curl`、`flock` 和 `sha256sum` 位于 `PATH` 上。 当仍然需要构建客户端时，模型支持的项目符号和 npm 注册表的出站 HTTPS (`network`) 达到 DeepSeek。
- 项目符号从上到下运行：`F23.conn-create` 设置 `CONN`（DeepSeek 连接）和 `DEF`（带有假密钥的 `custom` 连接），直到
  `F23.conn-delete`; `F23.linked-run` 保存链接的配置文件
  `qa-f23-linked`，保持活动状态直到 `F23.delete-guard`。 `F23.no-cipher` 启动和停止第二个服务器； `F23.store-busy` 和
  `F23.store-busy-responsive`按住商店的锁（约34秒和16秒）并在结束前松开。

  ```sh
  F23="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f23"
  mkdir -p "$F23"
  CF="$AGENT_SERVER_VERIFY_RUN/home/.openhands/provider-connections/provider_connections.json"
  cat > "$F23/ts_catalog.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { LLMMetadataClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new LLMMetadataClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const providers = await client.getProviders();
  assert.equal(providers.length, Number(process.env.QA_PROVIDERS));
  assert.ok(providers.includes('deepseek'));
  const models = await client.getModels();
  assert.equal(models.length, Number(process.env.QA_MODELS));
  const deepseek = await client.getModels('deepseek');
  assert.equal(deepseek.length, Number(process.env.QA_DEEPSEEK_MODELS));
  assert.ok(deepseek.includes('deepseek/deepseek-flash'));
  const verified = await client.getVerifiedModels();
  assert.deepEqual(Object.keys(verified).sort(), process.env.QA_VERIFIED_KEYS.split(','));
  assert.ok(verified.deepseek.includes('deepseek-chat'));
  const stranger = new LLMMetadataClient({ host: process.env.AGENT_SERVER_URL, apiKey: 'qa-f23-wrong-key' });
  await assert.rejects(stranger.getProviders(), (err) => err.name === 'HttpError' && err.status === 401);
  console.log('QA_F23_TS_OK');
  JS
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 0
  ```

- **需要密钥 (`F23.auth-required`)。**呼叫每条没有钥匙的路线和一条错误钥匙的路线。
  ```sh
  control-agent-server api GET /api/llm/providers --auth none --expect 401 --check detail eq Unauthorized --save F23.auth-required/providers
  control-agent-server api GET /api/llm/models --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/models/verified --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/provider-connections --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/provider-connections --auth none --expect 401 --check detail eq Unauthorized \
    --json '{"display_name": "qa-f23-noauth", "api_key": "sk-qa-f23-noauth"}' --save F23.auth-required/create
  control-agent-server api PATCH /api/llm/provider-connections/qa-f23-any --auth none --expect 401 --check detail eq Unauthorized \
    --json '{"display_name": "qa-f23-noauth"}'
  control-agent-server api DELETE /api/llm/provider-connections/qa-f23-any --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 0
  ```
  每一条调用都是401 `{"detail": "Unauthorized"}`; 即使使用了运行的密钥，列表仍然为空。
- **提供商 (`F23.providers`).**提供商选择器。
  ```sh
  control-agent-server api GET /api/llm/providers --expect 200 --check providers contains deepseek \
    --check providers contains openai --check providers contains anthropic --check providers len-ge 50 --save F23.providers/providers
  control-agent-server api GET /api/llm/providers --field providers | jq -e '. == unique'
  ```
  列表包含超过50个名字，包括三个名字，排序后且去重（`jq -e` 不会失败）。
- **所有型号 (`F23.models`)。**未过滤的型号列表。
  ```sh
  control-agent-server api GET /api/llm/models --expect 200 --quiet --check models len-ge 1000 --save F23.models/all
  control-agent-server api GET /api/llm/models --field models \
    | jq -e '. == unique and all(.[]; startswith("bedrock") | not) and any(.[]; . == "deepseek/deepseek-flash")'
  ```
  有数千个按顺序排列且唯一的ID，None 从`bedrock`开始，`deepseek/deepseek-flash` 是其中的唯一ID。
- **提供商过滤器（`F23.models-filter`）。**一个提供商的模型。
  ```sh
  control-agent-server api GET /api/llm/models --query provider=deepseek --expect 200 --check models contains deepseek-chat --save F23.models-filter/deepseek
  control-agent-server api GET /api/llm/models --query provider=deepseek --field models \
    | jq -e 'length > 0 and . == unique and all(.[]; startswith("deepseek")) and ([.[] | select(. == "deepseek/deepseek-flash" or . == "deepseek/deepseek-chat" or . == "deepseek-chat")] | length == 3)'
  control-agent-server api GET /api/llm/models --query provider=openrouter --field models \
    | jq -e 'length > 0 and all(.[]; startswith("openrouter/")) and any(.[]; . == "openrouter/deepseek/deepseek-chat")'
  control-agent-server api GET /api/llm/models --query provider=qa-no-such-provider --expect 200 --check models len-eq 0 --save F23.models-filter/unknown
  ```
  DeepSeek 列只有 DeepSeek 个 id：`deepseek/deepseek-flash`，命名空间 `deepseek/deepseek-chat` 和裸体验证 `deepseek-chat`。 列表中的 OpenRouter 个 ID 只有 `openrouter/` 个
  `deepseek/deepseek-chat` 也是 OpenRouter 已验证的条目； 未知的提供者获得`{"models": []}`。
- **提供商 (`F23.models-no-bedrock`) 下没有基岩 ID。**该路线表示基岩模型在没有 AWS 凭据的情况下被排除在外。 两个列表首先显示为保存提供者自己的 ID（阳性对照），然后在每个列表中搜索基岩 ID，并在 `assert` 中打印。
  ```sh
  control-agent-server api GET /api/llm/models --query provider=deepseek --quiet --check models contains deepseek/deepseek-flash \
    --save F23.models-no-bedrock/deepseek
  control-agent-server api GET /api/llm/models --query provider=anthropic --quiet --check models len-ge 1 --save F23.models-no-bedrock/anthropic
  control-agent-server api GET /api/llm/models --query provider=anthropic --field models | jq -e 'any(.[]; startswith("claude-"))'
  control-agent-server api GET /api/llm/models --query provider=deepseek --field models | jq -c 'map(select(test("^deepseek\\.")))' | control-agent-server assert --check . len-eq 0
  control-agent-server api GET /api/llm/models --query provider=anthropic --field models | jq -c 'map(select(test("^anthropic\\.")))' | control-agent-server assert --check . len-eq 0
  ```
  在任何提供商下，Bedrock `vendor.model` 格式中都没有 ID。
  `get_supported_llm_models` 删除基岩提供商（`bedrock`、`bedrock_converse`、`bedrock_mantle`）下的每个 id LiteLLM 的模型成本地图文件，而不仅仅是 `bedrock` 前缀的 id，因此 `deepseek.r1-v1:0`，
  `anthropic.claude-...-v1:0`、`us.anthropic.*` 和 `amazon.nova-*` 不存在于没有 AWS 凭据的每个列表中。
- **已验证的模型 (`F23.verified-models`)。**精心策划的候选名单。
  ```sh
  control-agent-server api GET /api/llm/models/verified --expect 200 --check models.deepseek contains deepseek-chat \
    --check models.openai len-ge 1 --check models.anthropic len-ge 1 --check models.openhands len-ge 1 \
    --check models.openrouter contains deepseek/deepseek-chat --save F23.verified-models/verified
  control-agent-server api GET /api/llm/models/verified --field models | jq -e 'all(.[]; length > 0 and length == (unique | length))'
  ```
  每个提供者密钥映射到一个不为空且无重复的列表。 OpenRouter 列包含命名空间 ID (`deepseek/deepseek-chat`), 其他列是裸 ID。 列表是精选的，而不是排序的。
- **TypeScript 客户端 (`F23.catalog-ts-client`).** `LLMMetadataClient`针对同一服务器，与REST计数进行比较。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  QA_PROVIDERS=$(control-agent-server api GET /api/llm/providers --field providers | jq length)
  QA_MODELS=$(control-agent-server api GET /api/llm/models --field models | jq length)
  QA_DEEPSEEK_MODELS=$(control-agent-server api GET /api/llm/models --query provider=deepseek --field models | jq length)
  QA_VERIFIED_KEYS=$(control-agent-server api GET /api/llm/models/verified --field models | jq -r 'keys | join(",")')
  control-agent-server exec --timeout 120 --env "QA_PROVIDERS=$QA_PROVIDERS" --env "QA_MODELS=$QA_MODELS" \
    --env "QA_DEEPSEEK_MODELS=$QA_DEEPSEEK_MODELS" --env "QA_VERIFIED_KEYS=$QA_VERIFIED_KEYS" \
    --expect-output QA_F23_TS_OK --save F23.catalog-ts-client/program -- node "$F23/ts_catalog.mjs"
  ```
  该程序打印 `QA_F23_TS_OK`客户端的列表有  REST 长度相同，验证过的组具有相同的键，一个使用错误密钥的客户端会以代码拒绝 `HttpError` 状态为 401。
- **创建(`F23.conn-create`)。**从以下位置创建 DeepSeek 连接
  `$DEEPSEEK_API_KEY`（通过管道传输，因此该键永远不会出现在命令行中）和第二个不带 `provider` 的键。
  ```sh
  CONN=$(printf '{"display_name": "qa-f23-deepseek", "provider": "deepseek", "api_key": "%s"}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/llm/provider-connections --stdin --expect 201 --check id matches '^[0-9a-f]{32}$' \
      --check display_name eq qa-f23-deepseek --check provider eq deepseek --check base_url eq null \
      --check api_key_set eq true --check api_key missing --save F23.conn-create/create --field id)
  DEF=$(control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-default", "api_key": "sk-qa-f23-default"}' \
    --expect 201 --check provider eq custom --check api_key_set eq true --field id)
  CREATED=$(control-agent-server api GET /api/llm/provider-connections --field 0.created_at)
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 2 \
    --check 0.id eq "$CONN" --check 0.updated_at eq "$CREATED" --check 0.api_key_set eq true \
    --check 1.id eq "$DEF" --check 1.provider eq custom --save F23.conn-create/list
  ```
  两者都使用服务器生成的32位十六进制ID。 列表按创建顺序返回 them `api_key_set: true` 并且没有键字段。
- **密钥隐藏和加密 (`F23.conn-key-encrypted`)。**请阅读 REST 中的列表和商店。

  需要：`F23.conn-create`
  ```sh
  control-agent-server api GET /api/llm/provider-connections --check . not-contains "$DEEPSEEK_API_KEY" \
    --check . not-contains sk-qa-f23-default --check 0.api_key missing --save F23.conn-key-encrypted/list
  control-agent-server state cat home/.openhands/provider-connections/provider_connections.json --mode 600 \
    --check schema_version eq 1 --check connections.0.id eq "$CONN" --check connections.0.api_key matches '^gAAAAA' \
    --check connections.1.api_key matches '^gAAAAA' --not-contains "$DEEPSEEK_API_KEY" --not-contains sk-qa-f23-default
  control-agent-server state grep qa-f23-deepseek --glob 'home/**/*'
  control-agent-server state grep --env-value DEEPSEEK_API_KEY --glob 'home/**/*' --expect-none
  ```
  响应中没有键。 该文件是 `600` 并且使用了 Fernet 两个密钥 token (printed as `<redacted:encrypted>`); the first `state grep` 是阳性对照（同一glob到达隐藏）
  `provider-connections/` 文件），第二个在服务器主目录下找不到明文 DeepSeek 密钥。
- **无密码 (`F23.no-cipher`)。**启动第二个既没有会话密钥也没有 `OH_SECRET_KEY` 的服务器，在那里创建连接，将配置文件链接到它并激活它。
  ```sh
  B=$(control-agent-server launch --new --print-run --name f23-nocipher --no-auth --no-secret-key)
  trap 'control-agent-server stop --run "$B" > /dev/null 2>&1 || true' EXIT
  PLAIN=$(control-agent-server api POST /api/llm/provider-connections --run "$B" --expect 201 --check api_key_set eq true \
    --json '{"display_name": "qa-f23-plain", "api_key": "sk-qa-f23-plain-key"}' --save F23.no-cipher/create --field id)
  control-agent-server state cat home/.openhands/provider-connections/provider_connections.json --run "$B" --mode 600 \
    --check connections.0.id eq "$PLAIN" --check connections.0.api_key eq sk-qa-f23-plain-key
  control-agent-server api GET /api/llm/provider-connections --run "$B" --expect 200 --check 0.api_key_set eq true \
    --check . not-contains sk-qa-f23-plain-key --save F23.no-cipher/list
  control-agent-server api POST /api/profiles/qa-f23-plain --run "$B" --expect 201 \
    --json "{\"llm\": {\"model\": \"openai/qa-f23-plain\", \"provider_connection_id\": \"$PLAIN\"}}"
  control-agent-server api POST /api/profiles/qa-f23-plain/activate --run "$B" --expect 200 --check llm_applied eq true
  control-agent-server state cat home/.openhands/settings.json --run "$B" --max-chars 200 \
    --check agent_settings.llm.api_key eq sk-qa-f23-plain-key --check agent_settings.llm.provider_connection_id eq "$PLAIN"
  control-agent-server stop --run "$B"
  ```
  连接文件（模式 `600`) 以明文存储，列表报告 `api_key_set: true` 没有密钥，激活会将密钥写入 `settings.json`. 第二个服务器已停止，由  `trap` 当检查失败时也是如此。 的 `--save` 文件归档到它 `evidence/` directory. 主运行文件仍保持加密状态`F23.conn-key-encrypted`).
- **创建验证 (`F23.conn-create-validation`).**请求模型拒绝的主体。
  ```sh
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-bad"}' --expect 422 \
    --check detail.0.type eq missing --check detail.0.loc contains api_key --save F23.conn-create-validation/no-key
  control-agent-server api POST /api/llm/provider-connections --json '{"api_key": "sk-qa-f23-bad"}' --expect 422 \
    --check detail.0.type eq missing --check detail.0.loc contains display_name
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-bad", "api_key": ""}' --expect 422 \
    --check detail.0.type eq too_short --check detail.0.loc contains api_key
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "", "api_key": "sk-qa-f23-bad"}' --expect 422 \
    --check detail.0.type eq string_too_short --check detail.0.loc contains display_name
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-bad", "provider": "", "api_key": "sk-qa-f23-bad"}' --expect 422 \
    --check detail.0.type eq string_too_short --check detail.0.loc contains provider
  control-agent-server api POST /api/llm/provider-connections --expect 422 --check detail.0.type eq string_too_long \
    --json "{\"display_name\": \"$(printf 'q%.0s' $(seq 129))\", \"api_key\": \"sk-qa-f23-bad\"}"
  control-agent-server api POST /api/llm/provider-connections --expect 422 --check detail.0.type eq extra_forbidden --check detail.0.loc contains extra_headers \
    --json '{"display_name": "qa-f23-bad", "api_key": "sk-qa-f23-bad", "extra_headers": {"Authorization": "Bearer qa-f23"}}' --save F23.conn-create-validation/extra
  control-agent-server api POST /api/llm/provider-connections --expect 422 --check detail.0.type eq extra_forbidden --check detail.0.loc contains id \
    --json '{"id": "qa-f23-chosen", "display_name": "qa-f23-bad", "api_key": "sk-qa-f23-bad"}'
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 2 --check . not-contains qa-f23-bad
  ```
  每个都带有Pydantic错误类型和位置。 列表仍然有两条连接。
- **创建时的空白键 (`F23.conn-create-blank-key`)。**空钥匙被拒绝（阳性对照）； 然后使用仅空白键和已脱敏占位符创建，记录这两个状态，并将它们一起断言。 `EXIT` 陷阱会删除所创建的任何内容，但子弹会结束。

  需要：`F23.conn-create`
  ```sh
  trap 'BLANK=$(control-agent-server api GET /api/llm/provider-connections --field . \
      | jq -r "[.[] | select(.display_name | startswith(\"qa-f23-blank-\")) | .id] | join(\" \")") || true
    for id in $BLANK; do control-agent-server api DELETE "/api/llm/provider-connections/$id" --quiet > /dev/null 2>&1 || true; done' EXIT
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-blank-empty", "api_key": ""}' \
    --expect 422 --check detail.0.loc contains api_key
  S_SPACE=$(control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-blank-space", "api_key": "   "}' \
    --expect 201,422 --save F23.conn-create-blank-key/space | jq -r .status)
  S_MASK=$(control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-blank-mask", "api_key": "**********"}' \
    --expect 201,422 --save F23.conn-create-blank-key/placeholder | jq -r .status)
  control-agent-server api GET /api/llm/provider-connections --save F23.conn-create-blank-key/list
  echo "whitespace key: $S_SPACE, placeholder key: $S_MASK"
  control-agent-server assert --value "$S_SPACE $S_MASK" --check . eq '422 422'
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 2 --check . not-contains qa-f23-blank-
  ```
  两者都返回 422 `""`，没有任何东西被创建：列表仍然只包含 `F23.conn-create` 中的两个连接，因此连接总是有一个可用的键。 陷阱会删除任何回归会创建的东西，所以后来的子弹看到同样的两个连接。
- **关联配置通过连接运行（`F23.linked-run`）。** 保存一个关联到 `CONN` 且带有多余内联密钥的配置，激活后使用生成的设置运行一个小型对话。

  需要：`F23.conn-create`
  ```sh
  control-agent-server llm preset deepseek
  control-agent-server api POST /api/profiles/qa-f23-linked --expect 201 \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"provider_connection_id\": \"$CONN\", \"api_key\": \"sk-qa-f23-inline\"}}"
  control-agent-server state cat home/.openhands/profiles/qa-f23-linked.json --not-contains sk-qa-f23-inline \
    --check api_key missing --check provider_connection_id eq "$CONN"
  control-agent-server api GET /api/profiles \
    --check profiles contains "\"name\": \"qa-f23-linked\", \"model\": \"deepseek/deepseek-flash\", \"base_url\": null, \"provider_connection_id\": \"$CONN\", \"provider_connection_broken\": false, \"api_key_set\": true"
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200 --check llm_applied eq true
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check active_profile eq qa-f23-linked \
    --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --check agent_settings.llm.provider_connection_id eq "$CONN" --save F23.linked-run/settings
  CID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with one word: ok' --wait --timeout 180 --print-id)
  control-agent-server api GET "/api/conversations/$CID" --max-chars 300 --check execution_status eq finished \
    --check agent.llm.provider_connection_id eq "$CONN" --check agent.llm.model eq deepseek/deepseek-flash \
    --check stats.usage_to_metrics.default.accumulated_token_usage.completion_tokens gt 0 --save F23.linked-run/conversation
  control-agent-server conversation events "$CID" --kinds MessageEvent,ActionEvent --contains '"source": "agent"' --expect-min 1 --save F23.linked-run/reply
  ```
  该配置文件只保留连接标识。 该列表显示
  `api_key_set: true` 来自连接； 激活将DeepSeek密钥写入`agent_settings.llm`并保留`provider_connection_id`； 真实模型打开该键后对话结束（记录完成 token 并回答智能体，作为消息或通过
  `finish` 工具，以模型选择的为准）。
- **更新(`F23.conn-update`)。**重命名 `CONN` 并将其指向
  `base_url`，重新激活，然后清除`base_url`并恢复名称。

  需要：`F23.conn-create`
  ```sh
  CREATED=$(control-agent-server api GET /api/llm/provider-connections --field 0.created_at)
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --expect 200 \
    --json '{"display_name": "qa-f23-renamed", "base_url": "http://127.0.0.1:9/v1"}' \
    --check id eq "$CONN" --check display_name eq qa-f23-renamed --check provider eq deepseek \
    --check base_url eq http://127.0.0.1:9/v1 --check api_key_set eq true --check created_at eq "$CREATED" \
    --check updated_at gt "$CREATED" --save F23.conn-update/patch
  control-agent-server api GET /api/llm/provider-connections --check 0.display_name eq qa-f23-renamed \
    --check 0.base_url eq http://127.0.0.1:9/v1 --check 0.api_key_set eq true --save F23.conn-update/list
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check agent_settings.llm.base_url eq http://127.0.0.1:9/v1 --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY"
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --expect 200 --json '{"display_name": "qa-f23-deepseek", "base_url": null}' \
    --check display_name eq qa-f23-deepseek --check base_url eq null --check api_key_set eq true
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check agent_settings.llm.base_url eq null --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --save F23.conn-update/settings-cleared
  ```
  `PATCH` 保持不变，`id`、`created_at`、`provider` 和密钥，列表显示新值，每次激活都会应用连接的当前 `base_url`（设置，然后 `null`）。
- **更新验证 (`F23.conn-update-validation`).**机构和 ID
  `PATCH` 拒绝。

  需要：`F23.conn-create`
  ```sh
  BEFORE=$(control-agent-server api GET /api/llm/provider-connections --field .)
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{}' --expect 422 \
    --check detail eq 'Provide at least one provider connection field to update' --save F23.conn-update-validation/empty
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"api_key": null}' --expect 422 \
    --check detail eq 'api_key cannot be cleared; provide a new key to rotate it' --save F23.conn-update-validation/null-key
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"display_name": null}' --expect 422 \
    --check detail.0.msg eq 'Value error, display_name cannot be set to null'
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"provider": null}' --expect 422 \
    --check detail.0.msg eq 'Value error, provider cannot be set to null'
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"display_name": ""}' --expect 422 --check detail.0.type eq string_too_short
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"api_key_set": false}' --expect 422 --check detail.0.type eq extra_forbidden
  control-agent-server api PATCH /api/llm/provider-connections/qa-f23-missing --json '{"display_name": "qa-f23-x"}' --expect 404 \
    --check detail eq "Provider connection 'qa-f23-missing' not found" --save F23.conn-update-validation/unknown
  test "$(control-agent-server api GET /api/llm/provider-connections --field .)" = "$BEFORE"
  ```
  每个都被用引号中的消息拒绝。 之后，列表仍然是字节对字节相同的（没有 `updated_at` 增量）。
- **更新时空白键 (`F23.conn-patch-blank-key`)。**将探针配置文件链接到 `DEF`（键 `sk-qa-f23-default`），然后对于空的、仅空白的和占位符键：`PATCH`，激活探针，记录所应用的键，然后放回原始键。

  需要：`F23.conn-create`
  ```sh
  trap 'control-agent-server api PATCH "/api/llm/provider-connections/$DEF" --json "{\"api_key\": \"sk-qa-f23-default\"}" --quiet > /dev/null 2>&1 || true
    control-agent-server api POST /api/profiles/qa-f23-linked/activate --quiet > /dev/null 2>&1 || true
    control-agent-server api DELETE /api/profiles/qa-f23-probe --quiet > /dev/null 2>&1 || true' EXIT
  control-agent-server api POST /api/profiles/qa-f23-probe --expect 201 \
    --json "{\"llm\": {\"model\": \"openai/qa-f23-probe\", \"provider_connection_id\": \"$DEF\"}}"
  control-agent-server api POST /api/profiles/qa-f23-probe/activate --expect 200 --check llm_applied eq true
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check agent_settings.llm.api_key eq sk-qa-f23-default --check agent_settings.llm.provider_connection_id eq "$DEF"
  APPLIED=""
  I=0
  for k in '' '   ' '**********'; do
    I=$((I + 1))
    control-agent-server api PATCH "/api/llm/provider-connections/$DEF" --json "{\"api_key\": \"$k\"}" --expect 200,422 \
      --save "F23.conn-patch-blank-key/patch-$I" > /dev/null
    control-agent-server api POST /api/profiles/qa-f23-probe/activate --expect 200 --quiet > /dev/null
    APPLIED="$APPLIED[$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --field agent_settings.llm \
      | jq -r '.api_key // "null"')]"
    control-agent-server api PATCH "/api/llm/provider-connections/$DEF" --json '{"api_key": "sk-qa-f23-default"}' --expect 200 --quiet > /dev/null
  done
  echo "applied keys: $APPLIED"
  control-agent-server assert --value "$APPLIED" --check . eq '[sk-qa-f23-default][sk-qa-f23-default][sk-qa-f23-default]'
  ```
  在任何空白`PATCH`之前，激活探针会应用
  `sk-qa-f23-default`（阳性对照）。 每个 `PATCH` 都是 422，就像 `api_key: null` 一样，并且单独保留存储的密钥，因此所有三个激活都适用 `sk-qa-f23-default`。 `EXIT` 陷阱将密钥恢复为活动配置文件，将 `qa-f23-linked` 恢复为活动配置文件并删除探测器，但项目符号结束。
- ** 旋转密钥 `F23.conn-rotate-key`。** 旋转 `CONN` 到一个密钥 DeepSeek 会被拒绝，检查活动设置在下次激活前保留旧密钥，然后运行旋转后的密钥对话，然后旋转回原密钥。

  需要：`F23.conn-create`
  ```sh
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"api_key": "sk-qa-f23-rotated-QA23"}' --expect 200 \
    --check api_key_set eq true --save F23.conn-rotate-key/rotate
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY"
  control-agent-server api PATCH /api/settings --json '{"active_profile": "qa-f23-linked"}' --expect 200 --quiet
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check active_profile eq qa-f23-linked \
    --check agent_settings.llm.api_key eq sk-qa-f23-rotated-QA23 --save F23.conn-rotate-key/settings-rotated
  BAD=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with one word: ok' --wait --until error --timeout 180 --print-id)
  control-agent-server conversation events "$BAD" --kinds ConversationErrorEvent --contains QA23 --expect-kind ConversationErrorEvent \
    --full --save F23.conn-rotate-key/provider-rejects
  printf '{"api_key": "%s"}' "$DEEPSEEK_API_KEY" | control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --stdin --expect 200
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  GOOD=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with one word: ok' --wait --timeout 180 --print-id)
  control-agent-server api GET "/api/conversations/$GOOD" --max-chars 200 --check execution_status eq finished --save F23.conn-rotate-key/rotated-back
  ```
  旋转之后，`agent_settings.llm`仍然持有DeepSeek键（旋转时不复制任何内容）。 重新应用相同的配置通过
  `PATCH /api/settings` `active_profile` 解析旋转的密钥，下一个对话以 `error` 结束
  `ConversationErrorEvent`，其中 DeepSeek 命名其收到的密钥 (`****QA23`)。 随着真实钥匙旋转回来并通过`POST /api/profiles/{name}/activate`激活配置文件，新的对话结束。
- **验证链接草稿 (`F23.validate-linked-draft`)。**使用关键内联（正控制）预飞行相同的 DeepSeek 模型，然后作为链接到 `CONN` 的草稿。

  需要：`F23.conn-create`
  ```sh
  printf '{"llm": {"model": "deepseek/deepseek-flash", "api_key": "%s", "num_retries": 0}}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/profiles/qa-f23-draft/validate --stdin --timeout 120 --expect 200 --check valid eq true
  control-agent-server api POST /api/profiles/qa-f23-draft/validate --timeout 120 --expect 200 \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"provider_connection_id\": \"$CONN\", \"num_retries\": 0}}" \
    --save F23.validate-linked-draft/linked --check valid eq true --check error eq null
  ```
  预期：均为 `valid: true`。 `validate_profile` 解决
  `provider_connection_id` 到连接的 `api_key` 和 `base_url` 在预飞行之前，激活和 `switch_llm` 因此，客户端永远不需要密钥（连接永远不会返回它）。 一个悬空的
  `provider_connection_id` 是 422 命名丢失的连接。
- **重新启动 (`F23.persist-restart`)。**重新启动运行并读回所有内容。

  需要：`F23.conn-create`
  ```sh
  BEFORE=$(control-agent-server api GET /api/llm/provider-connections --field .)
  control-agent-server restart
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 2 --check 0.id eq "$CONN" \
    --check 0.api_key_set eq true --save F23.persist-restart/list
  test "$(control-agent-server api GET /api/llm/provider-connections --field .)" = "$BEFORE"
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --save F23.persist-restart/settings
  ```
  列表完全相同（id、名称、时间戳），重启后激活仍然解密并应用 DeepSeek 键。
- **机密密钥已更改 (`F23.strict-decrypt`)。**用新的重新启动
  `OH_SECRET_KEY`，尝试每条连接路线，然后恢复旧密钥。

  需要：`F23.conn-create`
  ```sh
  SUM=$(sha256sum "$CF" | cut -d' ' -f1)
  control-agent-server restart --rotate-secret-key
  control-agent-server api GET /api/llm/provider-connections --expect 400 \
    --check detail contains 'api_key is encrypted but cannot be decrypted with the current cipher' \
    --check detail contains OH_SECRET_KEY --save F23.strict-decrypt/list
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-rotated", "api_key": "sk-qa-f23-rotated"}' \
    --expect 400 --check detail contains 'cannot be decrypted with the current cipher'
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"display_name": "qa-f23-rotated"}' \
    --expect 400 --check detail contains 'cannot be decrypted with the current cipher'
  control-agent-server api DELETE "/api/llm/provider-connections/$DEF" --expect 400 \
    --check detail contains 'cannot be decrypted with the current cipher' --save F23.strict-decrypt/delete
  test "$(sha256sum "$CF" | cut -d' ' -f1)" = "$SUM"
  control-agent-server restart --restore-secret-key
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 2 --check 0.display_name eq qa-f23-deepseek
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --save F23.strict-decrypt/restored
  ```
  在新的密钥下，所有四个答案都是400，`OH_SECRET_KEY`，文件的SHA-256部分未变（没有被重写或删除）。 旧密钥返回后，两个连接都被列出，DeepSeek密钥仍然解析。
- **文件损坏 (`F23.corrupt-file`)。**截断存储，然后给它一个更新的模式，然后放回原来的。

  需要：`F23.conn-create`
  ```sh
  cp "$CF" "$F23/connections-backup.json"
  printf '{"schema_version": 1, "connections": [' > "$CF"
  control-agent-server api GET /api/llm/provider-connections --expect 400 \
    --check detail contains 'Provider connections file is unreadable' --save F23.corrupt-file/list
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-corrupt", "api_key": "sk-qa-f23-corrupt"}' \
    --expect 400 --check detail contains 'Provider connections file is unreadable'
  test "$(cat "$CF")" = '{"schema_version": 1, "connections": ['
  printf '{"schema_version": 2, "connections": []}' > "$CF"
  control-agent-server api GET /api/llm/provider-connections --expect 400 --check detail eq 'schema_version 2 is newer than supported 1' \
    --save F23.corrupt-file/newer-schema
  control-agent-server api DELETE "/api/llm/provider-connections/$DEF" --expect 400 --check detail eq 'schema_version 2 is newer than supported 1'
  test "$(cat "$CF")" = '{"schema_version": 2, "connections": []}'
  cp "$F23/connections-backup.json" "$CF"
  control-agent-server api GET /api/llm/provider-connections --expect 200 --check . len-eq 2 --check 0.id eq "$CONN"
  ```
  每次调用都会返回400，表示解析或版本错误，文件会保留它被给予的字节。 恢复的文件又可以供两个连接使用。
- **[已弃用] 仓库繁忙`F23.store-busy`).** 另一个进程（这里 `flock`, 作为同一服务器上的第二个服务器代替持久化目录包含了商店的锁在创建到达的34秒内。 服务器自身的 30 秒锁超时正处于测试中，所以这个条目等待它。
  ```sh
  HELD="$F23/lock-held"
  rm -f "$HELD"
  flock -x "$(dirname "$CF")/.provider-connections.lock" sh -c "touch '$HELD'; sleep 34" &
  LOCKER=$!
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  T0=$SECONDS
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-busy", "api_key": "sk-qa-f23-busy"}' \
    --timeout 60 --expect 503 --check exception eq '503: Profile store is busy. Please retry.' --save F23.store-busy/create
  test $((SECONDS - T0)) -ge 29
  test $((SECONDS - T0)) -le 33
  wait "$LOCKER"
  control-agent-server api GET /api/llm/provider-connections --expect 200 --expect-max-ms 5000 --check . len-eq 2 --check . not-contains qa-f23-busy
  ```
  创建答案在29到33秒后（`detail`是通用的`Internal Server Error`）返回503。 `exception` 中的路由消息，一旦锁释放，列表就会立即回答，而不会 `qa-f23-busy`。
- **锁等待不会阻塞服务器(`F23.store-busy-responsive`)。**
  `/alive` 3 秒内回答锁免费（阳性对照）。 然后握住锁在16秒内启动一个后台列表，并进行探测 `/alive` 尽管列表在等待。 只有五秒的暂停能让后台列表先到达服务器（留有慢速的余地） CLI 在（start），所以探针落在其锁 wait; 列表本身获取了锁当 `flock` 让我们进去，30秒之内超时，并且其持续时间（至少10秒）显示探针在运行并发 with a 锁等待。 安 `EXIT` 子弹等待背景进程，直到子弹结束，所以后来的子弹会找到它们锁免费的。
  ```sh
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000
  HELD="$F23/lock-held-2"
  rm -f "$HELD"
  LISTER=""
  flock -x "$(dirname "$CF")/.provider-connections.lock" sh -c "touch '$HELD'; sleep 16" &
  LOCKER=$!
  trap 'wait $LISTER $LOCKER > /dev/null 2>&1 || true' EXIT
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  T0=$SECONDS
  control-agent-server api GET /api/llm/provider-connections --timeout 60 --expect 200 --quiet --save F23.store-busy-responsive/list > /dev/null &
  LISTER=$!
  sleep 5
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000 --timeout 60 --save F23.store-busy-responsive/alive
  wait "$LISTER"
  test $((SECONDS - T0)) -ge 10
  wait "$LOCKER"
  ```
  `/alive` 在列表等待时，答案会在3秒内给出：连接路由是简单的 `def` 因此，处理器 FastAPI 运行同步，file-locked `ProviderConnectionStore` 在它的线程池和锁等待永远不会持有事件循环 (`provider_connections_router.py`; 相同的边界 `F20.store-busy-responsive` 对于存储 [profile store)。
- **删除防护(`F23.delete-guard`)。**尝试删除 `CONN`，同时
  `qa-f23-linked` 和活动设置使用它，而只有配置文件使用它，并且只有设置使用它。

  需要：`F23.conn-create`
  ```sh
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 409 --save F23.delete-guard/profile-and-settings \
    --check detail eq 'Provider connection cannot be deleted while it is referenced by LLM profile(s): qa-f23-linked and referenced by the active agent settings. Update those references before deleting it.'
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 409 --save F23.delete-guard/profile \
    --check detail eq 'Provider connection cannot be deleted while it is referenced by LLM profile(s): qa-f23-linked. Update those references before deleting it.'
  control-agent-server api POST /api/profiles/qa-f23-linked/activate --expect 200
  control-agent-server api DELETE /api/profiles/qa-f23-linked --expect 200
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 409 --save F23.delete-guard/settings \
    --check detail eq 'Provider connection cannot be deleted while it is referenced by the active agent settings. Update those references before deleting it.'
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 2 --check 0.id eq "$CONN" --check 0.api_key_set eq true
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200
  control-agent-server api GET /api/settings --check active_profile eq deepseek-flash --check agent_settings.llm.provider_connection_id eq null
  ```
  所有三个删除都返回409，并且名称完全匹配剩余的引用。 连接保持不变。 删除活跃关联的用户资料会清除
  `active_profile` 但将其已解析的 LLM （带有连接 ID）保留在
  `agent_settings.llm`，它仍然会阻止删除，直到激活另一个配置文件。
- **删除(`F23.conn-delete`)。**删除现在未引用的两个连接。

  需要：`F23.conn-create`
  ```sh
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 200 --check id eq "$CONN" \
    --check display_name eq qa-f23-deepseek --check provider eq deepseek --check api_key_set eq false --save F23.conn-delete/delete
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 1 --check . not-contains "$CONN" --check 0.id eq "$DEF"
  control-agent-server state cat home/.openhands/provider-connections/provider_connections.json --check connections len-eq 1 --not-contains "$CONN"
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 404 \
    --check detail eq "Provider connection '$CONN' not found" --save F23.conn-delete/again
  control-agent-server api PATCH "/api/llm/provider-connections/$CONN" --json '{"display_name": "qa-f23-x"}' --expect 404
  control-agent-server api DELETE "/api/llm/provider-connections/$DEF" --expect 200 --check api_key_set eq false
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 0
  ```
  删除操作会包含连接的字段，并且 `api_key_set: false`。 列表和文件都不再包含它。 重复删除和 `PATCH` 会返回 404。
- **限制 (`F23.conn-limit`).**将存储填充到 64 个连接（
  `curl` 到 `exec`，因此 64 个创建需要一秒钟），尝试第 65 个，释放一个插槽，然后将其全部删除。
  ```sh
  control-agent-server exec --env QA_FILL=64 --expect-output created=64 -- bash -c 'n=0; for i in $(seq "$QA_FILL"); do
    s=$(curl -sS --noproxy "*" -o /dev/null -w "%{http_code}" -H "X-Session-API-Key: $SESSION_API_KEY" -H "Content-Type: application/json" \
      -d "{\"display_name\": \"qa-f23-fill-$i\", \"api_key\": \"sk-qa-f23-fill\"}" "$AGENT_SERVER_URL/api/llm/provider-connections")
    test "$s" = 201 || exit 1; n=$((n + 1)); done; echo "created=$n"'
  control-agent-server api GET /api/llm/provider-connections --quiet --check . len-eq 64
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-over", "api_key": "sk-qa-f23-over"}' --expect 409 \
    --check detail eq 'Provider connection limit reached (64). Delete one before adding another.' --save F23.conn-limit/over
  control-agent-server api GET /api/llm/provider-connections --quiet --check . len-eq 64 --check . not-contains qa-f23-over
  FIRST=$(control-agent-server api GET /api/llm/provider-connections --field 0.id)
  control-agent-server api DELETE "/api/llm/provider-connections/$FIRST" --expect 200 --quiet
  control-agent-server api POST /api/llm/provider-connections --json '{"display_name": "qa-f23-over", "api_key": "sk-qa-f23-over"}' --expect 201 \
    --save F23.conn-limit/after-delete
  IDS=$(control-agent-server api GET /api/llm/provider-connections --field . | jq -r '[.[].id] | join(" ")')
  control-agent-server exec --env "QA_IDS=$IDS" --expect-output deleted=64 -- bash -c 'n=0; for id in $QA_IDS; do
    s=$(curl -sS --noproxy "*" -o /dev/null -w "%{http_code}" -X DELETE -H "X-Session-API-Key: $SESSION_API_KEY" "$AGENT_SERVER_URL/api/llm/provider-connections/$id")
    test "$s" = 200 || exit 1; n=$((n + 1)); done; echo "deleted=$n"'
  control-agent-server api GET /api/llm/provider-connections --check . len-eq 0
  ```
  第65个创建是409，没有添加任何内容。 删除后，同一创建请求返回201。 清理后，商店空了。

- **ACP发现错误(`F23.acp-discovery-errors`)。**请求发现缺少运行拥有的可执行文件，而无需启动提供程序或进行模型调用。
  ```sh
  ACP_COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  ACP_MISSING="{\"agent_settings\":{\"agent_kind\":\"acp\",\"acp_server\":\"custom\",\"acp_command\":[\"$AGENT_SERVER_VERIFY_RUN/qa-missing-acp\"]}}"
  control-agent-server api POST /api/acp/models --auth none --json '{}' --expect 401 --save F23.acp-discovery-errors/auth
  control-agent-server api POST /api/acp/models --json '{}' --expect 422 --save F23.acp-discovery-errors/validation
  control-agent-server api POST /api/acp/models --json "$ACP_MISSING" --expect 200 \
    --check error.code eq ACPSpawnError --check available_models len-eq 0 --check current_model_id missing --save F23.acp-discovery-errors/spawn
  control-agent-server api POST /api/acp/models --json "${ACP_MISSING%?},\"refresh\":true}" --expect 200 \
    --check error.code eq ACPSpawnError --save F23.acp-discovery-errors/refresh
  control-agent-server api GET /api/conversations/count --check . eq "$ACP_COUNT"
  ```
  响应记录了一个启动错误，而不是500，且没有对话已持久化。 以下的 TypeScript 消费者检查结构化失败正常解决，缺少会话密钥则返回 401。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  cat > "$F23/ts_acp_errors.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';
  const { ACPClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new ACPClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const unauthorized = new ACPClient({ host: process.env.AGENT_SERVER_URL });
  const request = { agent_settings: { agent_kind: 'acp', acp_server: 'custom', acp_command: [process.env.QA_F23_MISSING_ACP] } };
  try {
    const failed = await client.discoverModels(request);
    assert.equal(failed.error.code, 'ACPSpawnError');
    assert.deepEqual(failed.available_models, []);
    assert.equal(failed.current_model_id, null);
    assert.equal((await client.discoverModels({ ...request, refresh: true })).error.code, 'ACPSpawnError');
    await assert.rejects(unauthorized.discoverModels(request), (err) => err.name === 'HttpError' && err.status === 401);
    console.log('QA_F23_ACP_ERRORS_OK');
  } finally {
    client.close();
    unauthorized.close();
  }
  JS
  control-agent-server exec --env QA_F23_MISSING_ACP="$AGENT_SERVER_VERIFY_RUN/qa-missing-acp" --timeout 60 \
    --expect-output QA_F23_ACP_ERRORS_OK --save F23.acp-discovery-errors/typescript -- node "$F23/ts_acp_errors.mjs"
  control-agent-server api GET /api/conversations/count --check . eq "$ACP_COUNT"
  ```
- **真实ACP模型发现(`F23.acp-discovery-live`)。**通过其内置的 `npx` 命令使用真正的 Claude Code 适配器。 如F09中一样，DeepSeek的Anthropic兼容端点提供凭据和
  `IS_SANDBOX=1` 允许适配器以 root 身份运行时的会话模式。 Discovery 初始化一次性会话而不发送模型提示词。
  ```sh
  ACP_COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  printf '{"agent_settings":{"agent_kind":"acp","acp_server":"claude-code"},"secrets":{"ANTHROPIC_API_KEY":{"kind":"StaticSecret","value":"%s"},"ANTHROPIC_BASE_URL":{"kind":"StaticSecret","value":"https://api.deepseek.com/anthropic"},"IS_SANDBOX":{"kind":"StaticSecret","value":"1"}}}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/acp/models --stdin --timeout 180 --expect 200 \
      --check error missing --check agent_name exists --check current_model_id exists --check supports_runtime_model_switch eq true \
      --check available_models contains '"model_id": "sonnet"' --check available_models contains '"model_id": "haiku"' \
      --raw-out "$F23/acp-models.json" --save F23.acp-discovery-live/rest
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  cat > "$F23/ts_acp_live.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { readFileSync } from 'node:fs';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';
  const { ACPClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new ACPClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY, timeout: 180000 });
  const expected = JSON.parse(readFileSync(process.env.QA_F23_ACP_REFERENCE, 'utf8'));
  assert.ok(process.env.DEEPSEEK_API_KEY);
  const secret = (value) => ({ kind: 'StaticSecret', value });
  const request = {
    agent_settings: { agent_kind: 'acp', acp_server: 'claude-code' },
    secrets: {
      ANTHROPIC_API_KEY: secret(process.env.DEEPSEEK_API_KEY),
      ANTHROPIC_BASE_URL: secret('https://api.deepseek.com/anthropic'),
      IS_SANDBOX: secret('1'),
    },
  };
  try {
    assert.deepEqual(await client.discoverModels(request), expected);
    const refreshed = await client.discoverModels({ ...request, refresh: true });
    assert.equal(refreshed.error, null);
    assert.equal(refreshed.agent_name, expected.agent_name);
    assert.equal(refreshed.current_model_id, expected.current_model_id);
    assert.deepEqual(refreshed.available_models, expected.available_models);
    assert.equal(refreshed.supports_runtime_model_switch, true);
    console.log('QA_F23_ACP_LIVE_OK');
  } finally {
    client.close();
  }
  JS
  control-agent-server exec --env QA_F23_ACP_REFERENCE="$F23/acp-models.json" --timeout 240 \
    --expect-output QA_F23_ACP_LIVE_OK --save F23.acp-discovery-live/typescript -- node "$F23/ts_acp_live.mjs"
  control-agent-server api GET /api/conversations/count --check . eq "$ACP_COUNT"
  control-agent-server state ls 'server/workspace/conversations/.acp-model-discovery-*' --expect-count 0
  ```
  REST 报告了真实适配器的模型目录。 TypeScript 消费者在重复请求时会收到相同的响应，在进行明确刷新后会收到相同的默认和提供的模型。 对话计数保持不变，发现移除了临时探针目录。

<a id="gotchas"></a>

## 陷阱

- `litellm` 版本决定了目录答案（数千个 ID，随着每次升级而变化），以及 `VERIFIED_MODELS`（经过筛选，每条模型线的最新版本）。 断言成员资格、排序和过滤，而不是精确计数或特定的新模型。
- `GET /api/llm/models?provider=`（空值）不是“无过滤器”：它返回无法识别提供者的 ID（例如 LiteLLM 图像大小）。 经过验证的裸 ID (`deepseek-chat`) 归因于其经过验证的提供商； 未知前缀 (`moonshotai/...`) 到 None。
- `?provider=X` 只过滤已安装的 ID LiteLLM 知道一个已验证的模型 LiteLLM 不列出（`deepseek-v4.1-flash`, `deepseek-v3.2-reasoner` 下 `deepseek`) 只出现在 `GET /api/llm/models/verified`因此，选择器需要两个路由。
- 连接 ID 由服务器创建（uuid4 十六进制）； 客户选择的
  `id` 是 422。 单个连接没有 `GET`：阅读列表。
- `PATCH` 将主体复制到存储的连接上，而不重新运行其验证器，因此请求模型本身拒绝空白和 `**********` 键（`F23.conn-create-blank-key`、`F23.conn-patch-blank-key`）； 响应是根据该副本构建的，而不是通过重读构建的。
- 分辨率是在使用时读取的：旋转或 `base_url` 更改仅在下一次激活时才到达配置文件（或 `PATCH /api/settings`
  `active_profile` 或 `switch_llm`）； `agent_settings.llm` 保留激活时制作的副本，已经运行的对话保留其副本。 连接的 `base_url` 总是获胜，包括 `null`。
- 删除活动的链接配置文件不会释放连接：活动的 `agent_settings.llm` 保留 `provider_connection_id`，因此激活另一个配置文件（或 `PATCH /api/settings`）
  `{"agent_settings_diff": {"llm": {"provider_connection_id": null}}}`）首先。 ACP 智能体设置永远不会阻止删除。
- 配置文件保存从不检查 `provider_connection_id` 是否存在； 悬空链接被列为 `provider_connection_broken: true`，其激活值为 422（LLM 配置文件系列）。 `GET /api/profiles` 和 `GET /api/profiles/{name}` 也因为链接的配置文件被损坏而返回 400。因为链接的配置文件和链接的配置文件都从连接存储（读取时不加密，所以更改机密的密钥不会破坏列表）中读取。
- 严格解密是故意的数据丢失保护（设置、机密和配置文件存储会默默降级）：
  `OH_SECRET_KEY`更改每个连接路由为400，直到旧密钥回来或文件被删除。 400 `detail` 引用了密文的截断片段，如果没有密钥，这也是无害的。
- 旋转项目符号 (`F23.conn-rotate-key`) 依赖于 DeepSeek 在其错误中命名被拒绝密钥 (`****QA23`) 的最后四个字符； 如果提供商更改了该消息，请在将其称为产品故障之前手动检查 `ConversationErrorEvent`。
- 连接路由等待商店锁在工作者线程中，因此，被延迟的锁只会延迟连接请求（最多 30 秒超时），而不是服务器 `F23.store-busy-responsive` 的 REST。 不过，永远不要按住锁 (`flock`
  `provider-connections/.provider-connections.lock`) 比项目符号需要的时间长，并且不要与 `F23.store-busy` 并行运行其他项目符号。
- `provider_connections.json` 通过手写 `F23.corrupt-file` 是本次私家住宅的安排步骤。 始终在子弹结束之前恢复备份。
- 这些路由中 None 个会发出 WebSocket 个事件或 Webhook：第二个视图是列表，磁盘上的存储， `GET /api/settings` 激活后，以及一个已解决键上的会话运行。
