<a id="model-profile-and-acp-switching-runtime-plugins"></a>

# 型号、配置文件和ACP切换； 运行时插件

消费者在已经存在的对话中所做的任何更改：交换智能体's LLM 对于用户自定义配置（inline key，一种密码） token 从一个 `encrypted` 读取，或者保存的提供商连接），将其切换为保存的 LLM 配置文件，更改型号 ACP 对话的子进程运行插件，并从会话注册的市场places中加载插件到实时环境中智能体 （其技能、命令和钩子）。 每个开关都回答了 `{"success": true}`被写入会话的
`base_state.json`，出现在 `GET /api/conversations/{id}` 中并作为
`ConversationStateUpdateEvent` 在事件套接字上，并且在重新启动后仍然存在； 下一回合在新模型上运行，其使用情况记录在新的 LLM 的 `usage_id` 下。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/_secrets_exposure.py`、`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`、`openhands-sdk/openhands/sdk/llm/llm_registry.py`、`openhands-sdk/openhands/sdk/llm/llm_profile_store.py`、`openhands-sdk/openhands/sdk/marketplace/`、`openhands-sdk/openhands/sdk/plugin/`、`openhands-sdk/openhands/sdk/agent/acp_agent.py`

需求：`llm`、`tmux`、`node`、`network`

路线：`POST /api/conversations/{conversation_id}/switch_profile`，
`POST /api/conversations/{conversation_id}/switch_llm`,
`POST /api/conversations/{conversation_id}/load_plugin`,
`POST /api/conversations/{conversation_id}/switch_acp_model`

<a id="sub-features"></a>

## 子功能

- `F09.auth-required`：所有四个路由均在没有有效会话密钥的情况下回答 401，并且不进行任何更改。
- `F09.switch-llm`：`switch_llm`用新鲜的`usage_id`回答200个`{"success": true}`； `GET`和`base_state.json`显示了新模型，`usage_id`显示了反映旧模型的上下文压缩器LLM，并且密钥永远不会回显或以明文形式存储。
- `F09.switch-llm-ws`：开关用键 `agent` 和事件套接字上的新模型推送 `ConversationStateUpdateEvent`，键被屏蔽。
- `F09.switch-llm-errors`：未知会话为 404，没有 `llm` 或没有 `llm.model` 的正文为 422，悬空的 `provider_connection_id` 为 422； 安装的LLM没有改变。
- `F09.switch-llm-encrypted-key`：对话中，`api_key` 是从 `encrypted` 配置文件读取的 `gAAAAA` token 的开关在安装前解密； 下一回合在 DeepSeek 上运行，其使用情况记录在新的 `usage_id` 下。
- `F09.switch-llm-provider-connection`：引用已保存的提供者连接而不是密钥的开关将使用连接的密钥运行下一回合； `GET` 显示 `provider_connection_id` 并且没有键。
- `F09.switch-llm-registered-usage-id`: 在智能体初始化之后，一个已注册的开关（`usage_id`配置已经保存的`default`配置）安装了帖子中的LLM，而不是无声的200无操作。
- `F09.switch-llm-before-first-run`：会话第一次运行之前的开关由该运行使用，并且该运行的词元用量记录在切换的LLM的`usage_id`下。
- `F09.switch-llm-mid-run`: 当一个 `switch_llm` 正在运行（智能体位于一个 20 秒的工具调用）时，会回答 200，然后套接字推送新的 `agent`，而同一个运行的下一个 LLM 调用已经使用了切换后的 LLM（在两个 `usage_id` 中都使用），运行结束。
- `F09.switch-llm-mid-run-get`：在中间运行开关回答 200 之后，`GET` 和 `base_state.json` 显示已切换的 LLM，就像套接字已经做的那样。
- `F09.switch-profile`：`switch_profile`对已保存的`deepseek-pro`配置文件回答200，将其安装在`usage_id``profile:deepseek-pro`下，下一回合在`deepseek/deepseek-v4-pro`上运行，其使用情况记录在该id下。
- `F09.switch-profile-errors`：未知的配置文件为 404 `Profile '<name>' not found`，无效的名称和损坏的配置文件为 400，丢失的 `profile_name` 为 422，未知的对话为 404； 安装的LLM没有改变。
- `F09.switch-profile-edited`：编辑配置文件后再次切换到配置文件会安装编辑后的配置，而不是第一次切换时缓存的副本。
- `F09.acp-model-native`： `switch_acp_model` 在常规（非 ACP）对话中为 400 `switch_acp_model is only supported for ACP conversations.`； 缺失的 `model` 为 422，未知对话为 404。
- `F09.acp-model-deferred`：在尚未运行的 ACP 对话中，`switch_acp_model` 在不启动子进程的情况下回答 200，并将模型保留为 `agent.acp_model`、`agent_state.acp_current_model_id` 和 `current_model_id`。
- `F09.acp-model-blank`：在第一次运行之前拒绝空白或仅包含空格的 ACP 模型，因为它是在实时会话中，并且保留存储的模型。
- `F09.switch-llm-acp-refused`：ACP 对话中的 `switch_llm` 和 `switch_profile` 被拒绝，因为 `switch_acp_model` 是常规对话，并且保留 ACP 智能体的占位符 LLM (`usage_id` `acp-managed`)。
- `F09.acp-model-live`：在 ACP 与实时会话的对话中，`switch_acp_model` 将子进程的模型切换到位（相同的 ACP 会话），并且 `current_model_id`、`acp_model` 和 `base_state.json` 跟随； 一个空模型是400，提供者没有提供的模型被拒绝，并且不会改变任何东西，下一个回合会切换到同一个会话中的其他模型。
- `F09.acp-model-live-unknown`：实时切换到提供商未提供的模型 ID（不在 `available_models` 中）是客户端错误（400，对于空白模型），而不是 500。
- `F09.acp-model-live-timeout`：一个实时开关，其 `session/set_model` 往返时间比 `acp_prompt_timeout` 长，`detail` `Internal Server Error` 为 504，并且模型保持不变。
- `F09.ts-client`: TypeScript客户端的`ConversationClient.switchLLM`、`switchProfile`、`switchAcpModel`和`ConversationManager.switchProfile`到达路由：每个交换机解析并读回`getConversation`，未知的配置拒绝返回404，`switchAcpModel`在常规对话中返回400，没有密钥的呼叫返回401，`switchAcpModel`在没有运行的ACP对话中解析并存储模型。
- `F09.ts-client-acp-docs`: TypeScript客户端的`switchAcpModel` 文档字符串在一次ACP会话开始之前描述服务器做了什么（200，模型存储在第一次会话中），而不是409。
- `F09.load-plugin`: `load_plugin` 和 `<plugin>@<marketplace>` 来自在智能体的 `agent_context` 上注册的本地市场，回答 200 并将插件的技能、其命令及其挂钩合并到实时智能体中，在 `GET`、`base_state.json` 和套接字上可见。
- `F09.load-plugin-hook-runs`：运行时加载后，下一个用户轮流运行插件的 `UserPromptSubmit` 挂钩（`HookExecutionEvent` 及其输出）并完成。
- `F09.load-plugin-errors`没有注册的市场和没有智能体上下文 400：已注册的市场，来源缺失；400：未知市场或插件；404：空或格式错误的引用；400：缺失 `plugin_ref` 状态码为422，未知对话为404。 裸露的插件名称可以在注册的市场中解析。
- `F09.load-plugin-twice`：加载同一个插件两次会留下其钩子的一份副本，因此它们仍然每条消息运行一次。
- `F09.load-plugin-sdk`: Python SDK 的 `RemoteConversation.load_plugin(ref)`，在 `RemoteConversation.attach` 重新连接的对话中，`HTTPStatusError` 404 错误，然后加载该插件，其技能和钩子 `GET` 显示。
- `F09.restart-persist` 重启后，LLM 仍然生效，ACP 仍然生效，加载的插件的技能和钩子仍然在。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，此处拥有（主体是单个嵌入字段）：
  `POST /api/conversations/{id}/switch_llm` `{"llm": {...LLM fields...}}`,
  `POST /api/conversations/{id}/switch_profile` `{"profile_name": "..."}`,
  `POST /api/conversations/{id}/switch_acp_model` `{"model": "..."}`,
  `POST /api/conversations/{id}/load_plugin` `{"plugin_ref": "<plugin>[@<marketplace>]"}`. 每个答案`{"success": true}`； 下面的每一个食谱都会驱动他们。
- 第二次浏览：`GET /api/conversations/{id}` (`agent.llm`, `agent.condenser.llm`,
  `stats.usage_to_metrics.<usage_id>`, `current_model_id`, `agent.acp_model`,
  `agent_state`、`hook_config` 和 `agent.agent_context.skills` 以及
  `include_skills=true`), 对话的 `base_state.json` (`state cat`),
  `WS /sockets/events/{conversation_id}`（`ConversationStateUpdateEvent`键
  `agent` 和 `hook_config`），以及 `HookExecutionEvent` 插件钩子发出。
- 设置其他家庭拥有的路线：`POST /api/profiles/{name}` 和
  `GET /api/profiles/{name}` 与 `X-Expose-Secrets: encrypted`（LLM 个配置文件），
  `POST`/`DELETE/api/llm/provider-connections`（提供商连接），
  `POST /api/conversations` 和 `POST /api/conversations/{id}/events`（对话和运行）。
- SDK: `LocalConversation.switch_llm(llm)`, `switch_profile(name)`,
  `switch_acp_model(model)` 和 `load_plugin(ref)` 是路由的名称； 超过 HTTP `RemoteConversation.load_plugin(ref)` 个帖子到 `load_plugin`（`F09.load-plugin-sdk` 驱动它）。
  `RemoteConversation` 没有 `switch_llm`、`switch_profile` 或
  `switch_acp_model` 方法； Python 消费者直接发布到路线。
- TypeScript客户端：`ConversationClient.switchProfile(id, name)`，
  `switchLLM(id, llm)`, `switchAcpModel(id, model)`;
  `RemoteConversation.switchProfile`, `switchLlm`, `switchAcpModel`;
  `ConversationManager.switchProfile`. 没有TypeScript`loadPlugin`。
  `F09.ts-client` 驱动 `ConversationClient` 方法并且
  `ConversationManager.switchProfile`（`RemoteConversation`方法将相同的主体发布到相同的路线）。
- Agent Canvas（仅上下文）：每个对话模型选择器调用
  `switch_profile`（或 `switch_llm` 具有可能引用提供商连接的配置文件配置），以及 `switch_acp_model` 用于 ACP 对话，选择
  from `available_models`.

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  设置 `$DEEPSEEK_API_KEY`，`jq` 在 `PATH` 上，安装 `tmux`（中间运行项目符号为智能体提供终端工具）。 实时 ACP 项目符号需要 `node`（`npx` 启动 Claude Code 适配器）和出站 HTTPS 到 npm 注册表和 `api.deepseek.com`； TypeScript 项目符号需要
  `node`（仅当 `clients/typescript/dist` 缺失时才使用网络 `npm`）。 下面的块保存 DeepSeek 预设（`deepseek-flash` 活动，`deepseek-pro`），读取
  `deepseek-flash` 密钥返回作为密码 token (`ENC`)，创建本地市场测试夹具 `qa-f09-mkt`（一个带有技能、命令和
  `UserPromptSubmit` 挂钩，打印 `QA_PLUGIN_HOOK`)，并启动 `CID`，这是一个从未运行的保存设置中的空闲对话。

  ```sh
  control-agent-server llm preset deepseek
  ENC=$(control-agent-server api GET /api/profiles/deepseek-flash --header 'X-Expose-Secrets: encrypted' --field config.api_key --unsafe-unredacted)
  test "${ENC#gAAAAA}" != "$ENC"
  MKT=$(control-agent-server fixture marketplace --name qa-f09-mkt --print-path)
  CID=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$CID" --check agent.llm.model eq deepseek/deepseek-flash --check agent.llm.usage_id eq default --quiet
  ```

- **需要密钥 (`F09.auth-required`)。**无需钥匙即可呼叫每条路线。
  ```sh
  control-agent-server api POST "/api/conversations/$CID/switch_llm" --auth none --json '{"llm": {"model": "openai/qa-f09-noauth", "usage_id": "qa-f09-noauth"}}' --expect 401 --check detail eq Unauthorized --save F09.auth-required/switch-llm
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --auth none --json '{"profile_name": "deepseek-pro"}' --expect 401
  control-agent-server api POST "/api/conversations/$CID/switch_acp_model" --auth bad --json '{"model": "opus"}' --expect 401
  control-agent-server api POST "/api/conversations/$CID/load_plugin" --auth none --json '{"plugin_ref": "qa-f09-mkt-plugin@qa-f09-mkt"}' --expect 401
  control-agent-server api GET "/api/conversations/$CID" --check agent.llm.model eq deepseek/deepseek-flash --check agent.llm.usage_id eq default --quiet
  ```
  每次调用都返回401 `{"detail": "Unauthorized"}`，对话仍在继续 `deepseek-flash`。

- **切换到调用者提供的 LLM (`F09.switch-llm`)。**在空闲 `CID` 上安装一个无法访问的占位符模型，该模型具有自己的 `usage_id`。
  ```sh
  control-agent-server api POST "/api/conversations/$CID/switch_llm" \
    --json '{"llm": {"model": "openai/qa-f09-switched", "api_key": "sk-qa-f09-switched", "base_url": "http://127.0.0.1:9/v1", "usage_id": "qa-f09-switched"}}' \
    --expect 200 --check success eq true --save F09.switch-llm/switch
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --quiet \
    --check agent.llm.model eq openai/qa-f09-switched --check agent.llm.usage_id eq qa-f09-switched \
    --check agent.llm.base_url eq http://127.0.0.1:9/v1 --check agent.llm.api_key missing \
    --check agent.condenser.llm.model eq openai/qa-f09-switched --check agent.condenser.llm.usage_id eq condenser \
    --check execution_status eq idle --save F09.switch-llm/get
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/base_state.json" --max-chars 200 \
    --check agent.llm.model eq openai/qa-f09-switched --check agent.llm.api_key matches '^gAAAAA' --not-contains sk-qa-f09-switched
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/meta.json" --max-chars 200 --check agent missing
  control-agent-server state grep sk-qa-f09-switched --glob 'server/**/*' --expect-none
  ```
  交换机为200`{"success": true}`。 b`GET`是新型号，
  `usage_id` 和 `base_url` 与 `api_key: null`； 总结性的上下文压缩器，其LLM反映了智能体的，现在在其自己的下运行相同的模型
  `usage_id` `condenser`. `base_state.json` 作为 Fernet token 持有钥匙，
  `meta.json` 没有智能体，并且明文密钥在磁盘上不存在。
- **开关的插座视图 (`F09.switch-llm-ws`)。**再次切换时捕获事件套接字。
  ```sh
  control-agent-server ws start "/sockets/events/$CID" --name qa-f09-switch --duration 120
  control-agent-server api POST "/api/conversations/$CID/switch_llm" \
    --json '{"llm": {"model": "openai/qa-f09-ws", "api_key": "sk-qa-f09-ws", "base_url": "http://127.0.0.1:9/v1", "usage_id": "qa-f09-ws"}}' --expect 200
  control-agent-server ws read qa-f09-switch --kinds ConversationStateUpdateEvent --contains openai/qa-f09-ws --expect-min 1 --wait 20 --save F09.switch-llm-ws/frames
  control-agent-server ws read qa-f09-switch --kinds ConversationStateUpdateEvent \
    --contains '"key": "agent", "value": {"llm": {"model": "openai/qa-f09-ws", "api_key": "**********"' --expect-min 1
  control-agent-server ws read qa-f09-switch --contains 'redacted:encrypted' --expect-none
  control-agent-server ws stop qa-f09-switch --contains sk-qa-f09-ws --expect-none
  control-agent-server api GET "/api/conversations/$CID" --quiet --check agent.llm.model eq openai/qa-f09-ws --check agent.llm.usage_id eq qa-f09-ws
  ```
  `ConversationStateUpdateEvent` `key: "agent"` 到达，其值携带 `openai/qa-f09-ws` `api_key` `**********` 在同一帧中（正检查：捕获通过 CLI 的红actor 转换运行的键 `$DEEPSEEK_API_KEY` 和每个 `gAAAAA` token 为]
  `<redacted:...>`，因此携带密码 token 而不是掩码的帧会使它失败，并且 `redacted:encrypted` 读取找不到这样的帧）。
  `sk-qa-f09-ws` 不是编辑器知道的值，因此最后一次读取是真正检查没有帧包含明文密钥。
- **开关错误 (`F09.switch-llm-errors`)。**未知的对话、坏人以及不存在的提供商连接。
  ```sh
  control-agent-server api POST /api/conversations/00000000-0000-4000-8000-000000000000/switch_llm \
    --json '{"llm": {"model": "openai/qa-f09-x", "usage_id": "qa-f09-x"}}' --expect 404 --save F09.switch-llm-errors/unknown-conversation
  control-agent-server api POST "/api/conversations/$CID/switch_llm" --json '{}' --expect 422 --check detail.0.loc.1 eq llm --save F09.switch-llm-errors/no-llm
  control-agent-server api POST "/api/conversations/$CID/switch_llm" --json '{"llm": {"api_key": "sk-qa-f09", "usage_id": "qa-f09-nomodel"}}' \
    --expect 422 --check detail.0.msg contains 'model must be specified'
  control-agent-server api POST "/api/conversations/$CID/switch_llm" \
    --json '{"llm": {"model": "openai/qa-f09-dangling", "provider_connection_id": "qa-f09-missing", "usage_id": "qa-f09-dangling"}}' \
    --expect 422 --check detail contains "provider connection 'qa-f09-missing', which does not exist" --save F09.switch-llm-errors/dangling-connection
  control-agent-server api GET "/api/conversations/$CID" --quiet --check agent.llm.model eq openai/qa-f09-ws --check agent.llm.usage_id eq qa-f09-ws
  ```
  404 对于未知的 id，422 对于缺少 `llm` 和 `model`，以及 422 命名断开的连接。 `CID`仍然在`openai/qa-f09-ws`上。
- ** 与密码的中间对话切换 token (`F09.switch-llm-encrypted-key`)。** 在 `deepseek-flash` 进行一轮，切换到新的 `usage_id`，使用 `ENC` token 作为密钥进行新一轮。
  ```sh
  RID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with the single word: ok' --wait --until finished --timeout 240 --print-id)
  control-agent-server api GET "/api/conversations/$RID" --quiet --check stats.usage_to_metrics.default.model_name eq deepseek/deepseek-flash
  control-agent-server api POST "/api/conversations/$RID/switch_llm" \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\", \"usage_id\": \"qa-f09-enc\", \"num_retries\": 0}}" \
    --expect 200 --save F09.switch-llm-encrypted-key/switch
  control-agent-server api GET "/api/conversations/$RID" --quiet --check agent.llm.usage_id eq qa-f09-enc --check agent.llm.api_key missing
  control-agent-server conversation send "$RID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$RID" --until-ok 60 --quiet --check execution_status eq finished \
    --check stats.usage_to_metrics.qa-f09-enc.model_name eq deepseek/deepseek-flash \
    --check stats.usage_to_metrics.qa-f09-enc.accumulated_token_usage.prompt_tokens gt 0 --save F09.switch-llm-encrypted-key/stats
  ```
  第二转弯结束，其token被记录在`qa-f09-enc`中。 原样发送，token 会被 DeepSeek 拒绝。 它在安装 LLM 之前，用服务器的加密密钥解密了路由。
- **切换到提供商连接（）`F09.switch-llm-provider-connection`).** 保存  DeepSeek 将 key 视为提供者连接和切换的手段 `RID` 使用它而不是引用它。

  需要：`F09.switch-llm-encrypted-key`
  ```sh
  CONN=$(printf '{"display_name": "QA F09", "provider": "deepseek", "api_key": "%s"}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/llm/provider-connections --stdin --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$RID/switch_llm" \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"provider_connection_id\": \"$CONN\", \"usage_id\": \"qa-f09-conn\", \"num_retries\": 0}}" \
    --expect 200 --save F09.switch-llm-provider-connection/switch
  control-agent-server api GET "/api/conversations/$RID" --quiet --check agent.llm.provider_connection_id eq "$CONN" \
    --check agent.llm.usage_id eq qa-f09-conn --check agent.llm.api_key missing
  control-agent-server conversation send "$RID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$RID" --until-ok 60 --quiet --check execution_status eq finished \
    --check stats.usage_to_metrics.qa-f09-conn.accumulated_token_usage.prompt_tokens gt 0 --save F09.switch-llm-provider-connection/stats
  CONN1=$(control-agent-server api GET "/api/conversations/$RID" --field stats.usage_to_metrics.qa-f09-conn.accumulated_token_usage.prompt_tokens)
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 200
  control-agent-server conversation send "$RID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$RID" --until-ok 60 --quiet --check execution_status eq finished \
    --check stats.usage_to_metrics.qa-f09-conn.accumulated_token_usage.prompt_tokens gt "$CONN1"
  ```
  会话结束在连接的密钥上（服务器不会继承）
  `DEEPSEEK_API_KEY`，因此没有其他可以使用的密钥）。 连接在交换机处解析一次：删除后，下一回合仍在已安装的 LLM 上运行，并且其词元数量增长。
- **切换到已保存的配置文件 (`F09.switch-profile`)。**将 `RID` 移至预设的 `deepseek-pro` 配置文件并对其运行一圈。

  需要：`F09.switch-llm-encrypted-key`
  ```sh
  control-agent-server api POST "/api/conversations/$RID/switch_profile" --json '{"profile_name": "deepseek-pro"}' \
    --expect 200 --check success eq true --save F09.switch-profile/switch
  control-agent-server api GET "/api/conversations/$RID" --quiet --check agent.llm.model eq deepseek/deepseek-v4-pro \
    --check agent.llm.usage_id eq profile:deepseek-pro --check agent.llm.api_key missing --save F09.switch-profile/get
  control-agent-server state cat "server/workspace/conversations/${RID//-/}/base_state.json" --max-chars 200 \
    --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.llm.usage_id eq profile:deepseek-pro
  control-agent-server conversation send "$RID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$RID" --until-ok 60 --quiet --check execution_status eq finished \
    --check 'stats.usage_to_metrics.profile:deepseek-pro.model_name' eq deepseek/deepseek-v4-pro \
    --check 'stats.usage_to_metrics.profile:deepseek-pro.accumulated_token_usage.prompt_tokens' gt 0 --save F09.switch-profile/stats
  PRO1=$(control-agent-server api GET "/api/conversations/$RID" --field 'stats.usage_to_metrics.profile:deepseek-pro.accumulated_token_usage.prompt_tokens')
  ```
  对话现在运行在 `deepseek/deepseek-v4-pro` 下 `usage_id`
  `profile:deepseek-pro`，并且该用法 ID 具有回合的 token。 `PRO1` 保留 `F09.restart-persist` 的计数。
- **配置文件切换错误 (`F09.switch-profile-errors`)。**未知、无效和损坏的配置文件、缺失字段和未知对话
  `CID`.
  ```sh
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --json '{"profile_name": "qa-f09-missing"}' \
    --expect 404 --check detail eq "Profile 'qa-f09-missing' not found" --save F09.switch-profile-errors/unknown-profile
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --json '{"profile_name": "../profiles/deepseek-pro"}' \
    --expect 400 --check detail contains 'Invalid profile name' --save F09.switch-profile-errors/invalid-name
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --json '{"profile_name": ""}' --expect 400 --check detail contains 'Invalid profile name'
  printf '{not json' > "$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles/qa-f09-corrupt.json"
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --json '{"profile_name": "qa-f09-corrupt"}' \
    --expect 400 --check detail contains 'Failed to load profile `qa-f09-corrupt`' --save F09.switch-profile-errors/corrupted
  rm "$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles/qa-f09-corrupt.json"
  control-agent-server api POST "/api/conversations/$CID/switch_profile" --json '{}' --expect 422 --check detail.0.loc.1 eq profile_name
  control-agent-server api POST /api/conversations/00000000-0000-4000-8000-000000000000/switch_profile --json '{"profile_name": "deepseek-pro"}' --expect 404
  control-agent-server api GET "/api/conversations/$CID" --quiet --check agent.llm.model eq openai/qa-f09-ws --check agent.llm.usage_id eq qa-f09-ws
  ```
  404 表示配置文件名称，400 表示类似路径或空名称，以及非 JSON 的配置文件（直接写入运行的配置文件目录并再次删除），422 和 404 表示 REST； `CID`保持
  `openai/qa-f09-ws`.
- **切换到已编辑的配置文件 (`F09.switch-profile-edited`)，已知错误。**将离线对话切换到个人资料，编辑个人资料，然后再次切换。
  ```sh
  trap 'control-agent-server api DELETE /api/profiles/qa-f09-edit >/dev/null' EXIT
  EID=$(control-agent-server conversation start --placeholder-agent --tools none --no-autotitle --print-id)
  control-agent-server api POST /api/profiles/qa-f09-edit --json '{"llm": {"model": "openai/qa-f09-edit-1", "api_key": "sk-qa-f09-edit", "base_url": "http://127.0.0.1:9/v1"}}' --expect 201
  control-agent-server api POST "/api/conversations/$EID/switch_profile" --json '{"profile_name": "qa-f09-edit"}' --expect 200
  control-agent-server api GET "/api/conversations/$EID" --quiet --check agent.llm.model eq openai/qa-f09-edit-1
  control-agent-server api POST /api/profiles/qa-f09-edit --json '{"llm": {"model": "openai/qa-f09-edit-2", "api_key": "sk-qa-f09-edit", "base_url": "http://127.0.0.1:9/v1"}}' --expect 201
  control-agent-server api GET /api/profiles/qa-f09-edit --quiet --check config.model eq openai/qa-f09-edit-2
  control-agent-server api POST "/api/conversations/$EID/switch_profile" --json '{"profile_name": "qa-f09-edit"}' --expect 200 --save F09.switch-profile-edited/switch-again
  control-agent-server api GET "/api/conversations/$EID" --quiet --check agent.llm.model eq openai/qa-f09-edit-2 --save F09.switch-profile-edited/get  # bug：状态 eq 200 && 检查.0.实际 eq openai/qa-f09-edit-1
  ```
  第一个开关安装了 `openai/qa-f09-edit-1`，然后该配置被读取回为 `openai/qa-f09-edit-2`。 预期：第二个开关会安装编辑后的配置。 今天回答200，并重新安装`qa-f09-edit-1`。
  `LocalConversation.switch_profile` 在对话的`profile:<name>`中查找LLM，注册表第一次且唯一读取了会话文件，因此固定密钥或模型永远不会到达在会话中使用过该文件的对话。 SDK 文档字符串页指出缓存（“缓存于注册表中，`profile:{profile_name}` 之后第一次加载”），但路由文档一无所知，也没有提供刷新的方式，因此，REST 消费者只能通过 `switch_llm` 和 `usage_id` 进行编辑。 退出时删除该配置。
- **切换到已注册的使用 ID (`F09.switch-llm-registered-usage-id`)。**转发保存的 `deepseek-pro` 配置文件的配置，读取
  `X-Expose-Secrets: encrypted` (按会话模型切换路由的) 文档字符串描述），与两个离线对话相关：一个是新鲜的，另一个是的智能体由队列消息初始化的。
  ```sh
  PRO=$(control-agent-server api GET /api/profiles/deepseek-pro --header 'X-Expose-Secrets: encrypted' --check config.usage_id eq default --field config --unsafe-unredacted)
  FID=$(control-agent-server conversation start --placeholder-agent --tools none --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$FID/switch_llm" --json "{\"llm\": $PRO}" --expect 200
  control-agent-server api GET "/api/conversations/$FID" --quiet --check agent.llm.model eq deepseek/deepseek-v4-pro
  KID=$(control-agent-server conversation start --placeholder-agent --tools none --no-autotitle --prompt 'Reply with the single word: ok' --no-run --print-id)
  control-agent-server api GET "/api/conversations/$KID" --quiet --check agent.llm.usage_id eq default --check execution_status eq idle
  control-agent-server api POST "/api/conversations/$KID/switch_llm" --json "{\"llm\": $PRO}" --expect 200 --save F09.switch-llm-registered-usage-id/switch
  control-agent-server api GET "/api/conversations/$KID" --quiet --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.llm.usage_id eq default --save F09.switch-llm-registered-usage-id/get
  ```
  配置文件携带了  `usage_id: default`, 并且新的对话切换到 `deepseek/deepseek-v4-pro`. 初始化的那个也切换了，尽管 `default` 已经处于其 LLM  注册表 (智能体初始化已注册。 `switch_llm` 重复使用一个注册的 LLM 只有当其配置等于发布的配置时，才替换条目，否则保留记录的使用 `usage_id` 在 `stats.usage_to_metrics`. 这正是转发配置文件，它携带的内容 `default` （也称为
  当省略 `usage_id` 时，默认为 `LLM`），处理已收到消息的对话。
- **在第一次运行 (`F09.switch-llm-before-first-run`) 之前切换，已知错误。**从模型无法访问的智能体开始，在运行任何内容之前切换到 DeepSeek，然后运行。
  ```sh
  BID=$(control-agent-server conversation start --placeholder-agent --tools none --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$BID/switch_llm" \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\", \"usage_id\": \"qa-f09-early\", \"num_retries\": 0}}" \
    --expect 200 --save F09.switch-llm-before-first-run/switch
  control-agent-server conversation send "$BID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$BID" --quiet --check execution_status eq finished --check agent.llm.usage_id eq qa-f09-early
  control-agent-server api GET "/api/conversations/$BID" --until-ok 20 --quiet \
    --check stats.usage_to_metrics.qa-f09-early.accumulated_token_usage.prompt_tokens gt 0 --save F09.switch-llm-before-first-run/stats  # bug：状态 eq 200 && 检查.0.实际 eq null
  ```
  运行结束，只有切换模型才能完成（注释中的点指向一个关闭的端口）。 预期：它的 token 被记录在
  `qa-f09-early`. 今天 `stats.usage_to_metrics` 只有 `condenser`： LLM 已经注册了注册表的 LLMs，而智能体的初始化跳过了 `usage_id` 已经注册的 LLM，所以 `ConversationStats` 的 `F09.switch-llm-encrypted-key` 从不被添加，对话的成本和 token 总额都漏掉了它所打的所有电话。 同一个开关在接收到第8个消息后被计数。
- **在跑步转弯时切换 (`F09.switch-llm-mid-run`)。**启动第一个操作是 20 秒命令的运行，一旦该操作存在就切换，然后让运行完成。
  ```sh
  MID=$(control-agent-server conversation start --tools terminal --no-autotitle --prompt 'Run this exact shell command and nothing else: sleep 20' --print-id)
  control-agent-server ws start "/sockets/events/$MID" --name qa-f09-midrun --duration 300
  control-agent-server ws read qa-f09-midrun --kinds ActionEvent --contains 'sleep 20' --expect-min 1 --wait 120
  control-agent-server api POST "/api/conversations/$MID/switch_llm" \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\", \"usage_id\": \"qa-f09-midrun\", \"num_retries\": 0}}" \
    --expect 200 --check success eq true --save F09.switch-llm-mid-run/switch
  control-agent-server conversation wait "$MID" --until finished,error --timeout 240
  control-agent-server ws stop qa-f09-midrun --kinds ConversationStateUpdateEvent --contains qa-f09-midrun --expect-min 1 --wait 20 --save F09.switch-llm-mid-run/frames
  control-agent-server api GET "/api/conversations/$MID" --until-ok 60 --quiet --check execution_status eq finished \
    --check agent.llm.usage_id eq qa-f09-midrun \
    --check stats.usage_to_metrics.default.accumulated_token_usage.prompt_tokens gt 0 \
    --check stats.usage_to_metrics.qa-f09-midrun.accumulated_token_usage.prompt_tokens gt 0 --save F09.switch-llm-mid-run/stats
  ```
  开关状态为200 `sleep 20` 今天立即运行（无需等待工具），socket携带状态更新 `qa-f09-midrun`, 并且运行结束。 两者 `usage_id`我们有 token选择的呼叫
  `sleep 20` 在 `default` 上运行，观测结果之后的调用
  `qa-f09-midrun`，因此该开关应用于同一运行内。
- **GET 在运行中切换 (`F09.switch-llm-mid-run-get`) 之后，已知错误。**同样的情况，立刻回读。
  ```sh
  GID=$(control-agent-server conversation start --tools terminal --no-autotitle --prompt 'Run this exact shell command and nothing else: sleep 20' --print-id)
  trap 'control-agent-server conversation wait "$GID" --until finished,error --timeout 240 >/dev/null 2>&1 || true; control-agent-server ws stop qa-f09-midget >/dev/null 2>&1 || true' EXIT
  control-agent-server ws start "/sockets/events/$GID" --name qa-f09-midget --duration 150
  control-agent-server ws read qa-f09-midget --kinds ActionEvent --contains 'sleep 20' --expect-min 1 --wait 120
  control-agent-server api POST "/api/conversations/$GID/switch_llm" \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\", \"usage_id\": \"qa-f09-midget\", \"num_retries\": 0}}" \
    --expect 200 --save F09.switch-llm-mid-run-get/switch
  control-agent-server ws read qa-f09-midget --kinds ConversationStateUpdateEvent --contains '"usage_id": "qa-f09-midget"' --expect-min 1 --wait 10 --save F09.switch-llm-mid-run-get/frames
  control-agent-server api GET "/api/conversations/$GID" --quiet --check execution_status eq running
  control-agent-server api GET "/api/conversations/$GID" --quiet --check agent.llm.usage_id eq qa-f09-midget --save F09.switch-llm-mid-run-get/get  # bug：状态 eq 200 && 检查.0.实际 eq 默认值
  control-agent-server state cat "server/workspace/conversations/${GID//-/}/base_state.json" --max-chars 200 --check agent.llm.usage_id eq qa-f09-midget  # bug：checks.0.actual eq默认值
  control-agent-server conversation wait "$GID" --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$GID" --quiet --check execution_status eq finished --check agent.llm.usage_id eq qa-f09-midget
  ```
  断路器为200，`sleep 20`运行时，`agent`和`usage_id`、`qa-f09-midget`同时被插座推入。 预期：`GET` 从那时起显示 `qa-f09-midget`。 今天下一个b`GET`(和
  `base_state.json`，它所服务的）仍然在运行时报告 `default`
  `running`，并保持到运行步骤结束，大约20秒后，尽管内存中的智能体已经切换了。（第一个`GET`是控制读操作落在步骤中的控制； 标记的`GET`是应该成立的断言。 失败时，`EXIT` 陷阱等待运行并停止捕获。）路由在事件循环线程上调用 `LocalConversation.switch_llm`； `arun()` 在该步骤期间在同一线程上保持可重入状态锁，因此开关重新进入它，并且其自动保存被推迟到该步骤的退出（
  `arun()` 评论说不相关的突变必须经过
  `run_in_executor`; `load_plugin`和`switch_acp_model`做）。 `GET` 检查者看到旧模型运行时，工具在 `restart --hard` 窗口中丢失确认的切换（实际示例：`GET` 在重启后显示 `default`）。
- **ACP开启常规对话(`F09.acp-model-native`)。** `CID`运行OpenHands`Agent`。
  ```sh
  control-agent-server api POST "/api/conversations/$CID/switch_acp_model" --json '{"model": "opus"}' \
    --expect 400 --check detail eq 'switch_acp_model is only supported for ACP conversations.' --save F09.acp-model-native/native
  control-agent-server api POST "/api/conversations/$CID/switch_acp_model" --json '{}' --expect 422 --check detail.0.loc.1 eq model
  control-agent-server api POST /api/conversations/00000000-0000-4000-8000-000000000000/switch_acp_model --json '{"model": "opus"}' --expect 404
  control-agent-server api GET "/api/conversations/$CID" --quiet --check agent.kind eq Agent --check agent.llm.model eq openai/qa-f09-ws --check current_model_id missing
  ```
  400带有确切的错误信息，422不带`model`，404对于未知的ID。 对话没有改变。
- **ACP 第一次运行之前的模型 (`F09.acp-model-deferred`)。**创建与 `acp_model: sonnet` 和无提示词的 Claude Code ACP 对话（在跑步之前无子进程开始），然后切换它。
  ```sh
  AID=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet"}}' --print-id)
  control-agent-server api GET "/api/conversations/$AID" --quiet --check agent.kind eq ACPAgent --check agent.acp_model eq sonnet \
    --check current_model_id eq sonnet --check execution_status eq idle
  control-agent-server api POST "/api/conversations/$AID/switch_acp_model" --json '{"model": "opus"}' --expect 200 --check success eq true --save F09.acp-model-deferred/switch
  control-agent-server api GET "/api/conversations/$AID" --quiet --check agent.acp_model eq opus --check current_model_id eq opus \
    --check agent_state.acp_current_model_id eq opus --check agent_state.acp_session_id missing --check execution_status eq idle --save F09.acp-model-deferred/get
  control-agent-server state cat "server/workspace/conversations/${AID//-/}/base_state.json" --max-chars 200 \
    --check agent.acp_model eq opus --check agent_state.acp_current_model_id eq opus
  ```
  开关状态为200，但没有ACP会话（`acp_session_id`不存在）。 `acp_model``agent_state.acp_current_model_id`和
  `current_model_id` 都说 `opus`，所以第一个会话将从它开始。
- **空白ACP模型(`F09.acp-model-blank`)。**尚未运行的第二个 ACP 对话。
  ```sh
  AID2=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet"}}' --print-id)
  control-agent-server api GET "/api/conversations/$AID2" --quiet --check agent.kind eq ACPAgent --check agent.acp_model eq sonnet --check execution_status eq idle
  control-agent-server api POST "/api/conversations/$AID2/switch_acp_model" --json '{"model": "   "}' --expect 400,422 --save F09.acp-model-blank/blank
  control-agent-server api GET "/api/conversations/$AID2" --quiet --check agent.acp_model eq sonnet --check current_model_id eq sonnet
  ```
  端口拒绝请求，返回状态码 400，类似于在会话中，`model must be a non-empty string` 和 `agent.acp_model` 和 `current_model_id` 保持不变
  `sonnet`.
- **LLM 打开 ACP 对话 (`F09.switch-llm-acp-refused`)，已知错误。**尚未运行的第三个 ACP 对话； 它的智能体带有一个占位符 LLM，仅命名模型。
  ```sh
  AID3=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet"}}' --print-id)
  control-agent-server api GET "/api/conversations/$AID3" --quiet --check agent.llm.usage_id eq acp-managed --check agent.llm.model eq sonnet
  control-agent-server api POST "/api/conversations/$AID3/switch_profile" --json '{"profile_name": "deepseek-pro"}' --expect 400,409,422 --save F09.switch-llm-acp-refused/switch-profile  # 错误：状态 eq 200 && response.body.success eq True
  control-agent-server api POST "/api/conversations/$AID3/switch_llm" \
    --json '{"llm": {"model": "openai/qa-f09-acp", "api_key": "sk-qa-f09-acp", "base_url": "http://127.0.0.1:9/v1", "usage_id": "qa-f09-acp"}}' \
    --expect 400,409,422 --save F09.switch-llm-acp-refused/switch-llm  # 错误：状态 eq 200 && response.body.success eq True
  control-agent-server api GET "/api/conversations/$AID3" --quiet --check agent.llm.usage_id eq acp-managed --check agent.acp_model eq sonnet  # bug：状态 eq 200 && 检查.0.实际 eq qa-f09-ACP && 检查.1.ok eq True
  ```
  ACP 智能体开始于 `usage_id` `acp-managed`，模型名
  `sonnet`. 预期：两个交换机都被 4xx 拒绝（400 将镜像
  `switch_acp_model` 在常规谈话中； ACP 子进程进行自己的模型调用，`LocalConversation.switch_acp_model` 说
  `switch_llm` 这不会影响它。 今天，答案都是200，并替换占位符 `base_state.json` with the posted LLM (`GET` 仍然显示 `model: sonnet`因为  ACP  智能体覆盖了模型名称为 `acp_model` 当加载时，但
  `usage_id` 变为 `profile:deepseek-pro`，然后变为 `qa-f09-acp`）。 子进程运行没有任何变化，并且 `acp-managed` 标记
  `title_utils`用来避免调用的占位符消失了。
- **实时ACP开关(`F09.acp-model-live`)。**翻译后的环境：ACP 提供者是真正的 Claude Code 适配器（`claude-code`，服务器使用 `npx` 启动它，因此需要 `node` 和网络），DeepSeek 的 Anthropic 兼容 API 代表 Anthropic 帐户（`ANTHROPIC_BASE_URL` `https://api.deepseek.com/anthropic`，DeepSeek 密钥作为 `ANTHROPIC_API_KEY`，作为会话机密传递，适配器尊重）。 `IS_SANDBOX=1` 允许 Claude Code 在以 root 身份运行时接受服务器的 `bypassPermissions` 会话模式（如果没有它，`Mode bypassPermissions is not available in this session` 会出现运行错误）。 协议切换、会话和持久化都是真实的； 只有AnthropicAPI背后的模型不同。
  ```sh
  LID=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet"}}' \
    --secret ANTHROPIC_API_KEY="$DEEPSEEK_API_KEY" --secret ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic --secret IS_SANDBOX=1 \
    --prompt 'Reply with the single word: ok' --wait --until finished --timeout 300 --print-id)
  SESS=$(control-agent-server api GET "/api/conversations/$LID" --check supports_runtime_model_switch eq true --check current_model_id eq sonnet \
    --check available_models contains '"model_id": "haiku"' --check stats.usage_to_metrics.acp-managed.accumulated_token_usage.completion_tokens gt 0 \
    --field agent_state.acp_session_id)
  test -n "$SESS"
  LC1=$(control-agent-server api GET "/api/conversations/$LID" --field stats.usage_to_metrics.acp-managed.accumulated_token_usage.completion_tokens)
  control-agent-server api POST "/api/conversations/$LID/switch_acp_model" --json '{"model": "haiku"}' --expect 200 --check success eq true --save F09.acp-model-live/switch
  control-agent-server api GET "/api/conversations/$LID" --quiet --check current_model_id eq haiku --check agent.acp_model eq haiku \
    --check agent_state.acp_current_model_id eq haiku --check agent_state.acp_session_id eq "$SESS" --save F09.acp-model-live/get
  control-agent-server state cat "server/workspace/conversations/${LID//-/}/base_state.json" --max-chars 200 --check agent.acp_model eq haiku --check agent_state.acp_current_model_id eq haiku
  control-agent-server api POST "/api/conversations/$LID/switch_acp_model" --json '{"model": "   "}' --expect 400 --check detail eq 'model must be a non-empty string'
  control-agent-server api POST "/api/conversations/$LID/switch_acp_model" --json '{"model": "qa-f09-nope"}' --expect 4xx,5xx --save F09.acp-model-live/unknown-model
  control-agent-server api GET "/api/conversations/$LID" --quiet --check current_model_id eq haiku --check agent.acp_model eq haiku
  control-agent-server conversation send "$LID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 300
  control-agent-server api GET "/api/conversations/$LID" --until-ok 30 --quiet --check execution_status eq finished --check agent_state.acp_session_id eq "$SESS" \
    --check stats.usage_to_metrics.acp-managed.model_name eq haiku \
    --check stats.usage_to_metrics.acp-managed.accumulated_token_usage.completion_tokens gt "$LC1" --save F09.acp-model-live/second-turn
  ```
  在第一次轮次之后，对话报告
  `supports_runtime_model_switch: true` 和适配器的
  `available_models` (`default`, `opus[1m]`, `sonnet`, `sonnet[1m]`,
  `haiku`），关于 `sonnet`。 切换到`haiku`是200和`current_model_id`，
  `agent.acp_model`、`agent_state.acp_current_model_id` 和
  `base_state.json` 跟随，具有相同的 `acp_session_id`（切换到位，而不是新会话）。 空白模型为 400 `model must be a non-empty string`。 适配器未提供的 ID 将被拒绝，并且模型保持 `haiku`（被拒绝的状态是
  `F09.acp-model-live-unknown`). 下一回合在同一会话中完成，其使用情况记录在 `acp-managed` 和 `model_name` 上
  `haiku`. 每个内置提供程序都声明运行时切换，因此它们无法访问路由的其他 400 (`does not support runtime model switching`)。
- **实时会话中的未知模型 (`F09.acp-model-live-unknown`)，已知错误。**
  `LID` 来自上面的项目符号，其适配器列出了其型号。

  需要：`F09.acp-model-live`
  ```sh
  control-agent-server api GET "/api/conversations/$LID" --quiet --check supports_runtime_model_switch eq true \
    --check available_models contains '"model_id": "sonnet"' --check available_models not-contains qa-f09-nope
  control-agent-server api POST "/api/conversations/$LID/switch_acp_model" --json '{"model": "qa-f09-nope"}' --expect 400,422 --save F09.acp-model-live-unknown/switch  # bug：状态 eq 500 && response.body.exception 包含“内部错误”
  ```
  预期：客户端错误，如 `ACPAgent.set_acp_model` 文档（“ACP
  服务器拒绝模型切换调用（e.g. ... 无效的型号 ID）” 是
  `ValueError`，路线变成 400) 并且作为空白模型已经是。 今天是500 `Internal Server Error`，`exception` `Internal error`：claude-智能体-ACP 以一个它不提供 id 的方式回答 `set_config_option(model)`，-32603，然后 JSON-RPC -32603 作为服务器端失败，而不是 `ValueError`，尽管会话的 `set_acp_model`
  `available_models` 已显示未提供该 ID。 错误输入模型的消费者会看到一个看起来可重试的 500，该请求永远不会成功。 无论哪种方式都不会改变（`F09.acp-model-live` 检查模型是否保持 `haiku`）。
- **实时切换超时 (`F09.acp-model-live-timeout`)。**同一个翻译提供商，在与创建的对话中
  `acp_prompt_timeout: 0.001`：测试的是服务器自己的定时器。 第一回合的提示词也超时（运行以 `error` 结束），但它创建的会话仍然有效。
  ```sh
  TOID=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet", "acp_prompt_timeout": 0.001}}' \
    --secret ANTHROPIC_API_KEY="$DEEPSEEK_API_KEY" --secret ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic --secret IS_SANDBOX=1 \
    --prompt 'Reply with the single word: ok' --wait --until finished,error --timeout 300 --print-id)
  control-agent-server api GET "/api/conversations/$TOID" --quiet --check agent_state.acp_session_id exists --check current_model_id eq sonnet --check agent.acp_prompt_timeout eq 0.001
  control-agent-server api POST "/api/conversations/$TOID/switch_acp_model" --json '{"model": "haiku"}' --expect 504 --check detail eq 'Internal Server Error' --save F09.acp-model-live-timeout/switch
  control-agent-server api GET "/api/conversations/$TOID" --quiet --check current_model_id eq sonnet --check agent.acp_model eq sonnet --check agent_state.acp_current_model_id eq sonnet
  ```
  适配器在1毫秒内无法回答模型切换，因此路由返回了`detail`重写为`Internal Server Error`（服务器的5xx处理器）； `exception` 是 `504: `，对话继续
  `sonnet` 无处不在：超时切换不会在本地改变任何内容。
- **TypeScript 客户端 (`F09.ts-client`).** `ConversationClient` 和
  `ConversationManager` 从 `clients/typescript/dist` 中的内置客户端 (当缺失时，这里会构建，需要 `npm` 和网络)，在一次全新的占位符对话 `TID` 和一次全新的 ACP 对话 `AID4` 中运行。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  TID=$(control-agent-server conversation start --placeholder-agent --tools none --no-autotitle --print-id)
  AID4=$(control-agent-server conversation start --no-autotitle --body-json '{"agent_settings": {"agent_kind": "acp", "acp_server": "claude-code", "acp_model": "sonnet"}}' --print-id)
  F="$AGENT_SERVER_VERIFY_RUN/fixtures"
  cat > "$F/qa-f09-ts.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const dist = (name) => import(pathToFileURL(resolve('clients/typescript/dist', name)).href);
  const { ConversationClient } = await dist('clients.js');
  const { ConversationManager } = await dist('index.js');
  const [tid, acp] = process.argv.slice(2);
  const host = process.env.AGENT_SERVER_URL;
  const apiKey = process.env.SESSION_API_KEY;
  const client = new ConversationClient({ host, apiKey });
  const llm = { model: 'openai/qa-f09-ts', api_key: 'sk-qa-f09-ts', base_url: 'http://127.0.0.1:9/v1', usage_id: 'qa-f09-ts' };
  await client.switchLLM(tid, llm);
  let info = await client.getConversation(tid);
  assert.equal(info.agent.llm.model, 'openai/qa-f09-ts');
  assert.equal(info.agent.llm.usage_id, 'qa-f09-ts');
  await new ConversationManager({ host, apiKey }).switchProfile(tid, 'deepseek-pro');
  info = await client.getConversation(tid);
  assert.equal(info.agent.llm.model, 'deepseek/deepseek-v4-pro');
  assert.equal(info.agent.llm.usage_id, 'profile:deepseek-pro');
  await client.switchProfile(tid, 'deepseek-flash');
  assert.equal((await client.getConversation(tid)).agent.llm.usage_id, 'profile:deepseek-flash');
  await assert.rejects(client.switchProfile(tid, 'qa-f09-missing'), (e) => e.status === 404);
  await assert.rejects(client.switchAcpModel(tid, 'opus'), (e) => e.status === 400);
  await assert.rejects(new ConversationClient({ host }).switchLLM(tid, llm), (e) => e.status === 401);
  assert.equal((await client.getConversation(tid)).agent.llm.usage_id, 'profile:deepseek-flash');
  await client.switchAcpModel(acp, 'opus');
  info = await client.getConversation(acp);
  assert.equal(info.agent.acp_model, 'opus');
  assert.equal(info.current_model_id, 'opus');
  console.log('TS_SWITCH_OK');
  JS
  control-agent-server exec --expect-output TS_SWITCH_OK --save F09.ts-client/program -- node "$F/qa-f09-ts.mjs" "$TID" "$AID4"
  control-agent-server api GET "/api/conversations/$TID" --quiet --check agent.llm.model eq deepseek/deepseek-flash --check agent.llm.usage_id eq profile:deepseek-flash
  control-agent-server state cat "server/workspace/conversations/${AID4//-/}/base_state.json" --max-chars 200 --check agent.acp_model eq opus
  ```
  每个断言都成立：`switchLLM`、`ConversationManager.switchProfile`和`switchProfile`都解析，`getConversation`显示模型
  `usage_id` 他们安装了； 未知配置文件是 `HttpError` 404，ACP 开启常规对话 400 和无密钥客户端 401，其中 None 已更改 `TID`； `switchAcpModel` 尚未运行的 ACP 对话解析（否 409），`acp_model` 和 `current_model_id` 变为
  `opus`，也在`base_state.json`中。
- **TypeScript 文档字符串用于预运行 ACP 开关 (`F09.ts-client-acp-docs`)。** `switchAcpModel` 两种方法都存在； 他们的文档字符串不应该承诺服务器永远不会发送 409。
  ```sh
  grep -n 'async switchAcpModel(' clients/typescript/src/client/conversation-client.ts
  grep -n 'async switchAcpModel(' clients/typescript/src/conversation/remote-conversation.ts
  control-agent-server assert --value "$(cat clients/typescript/src/client/conversation-client.ts clients/typescript/src/conversation/remote-conversation.ts | grep -c 'returns 409 before the first message')" --check . eq 0
  control-agent-server assert --value "$(cat clients/typescript/src/client/conversation-client.ts clients/typescript/src/conversation/remote-conversation.ts | grep -c 'the first session. Non-ACP conversations get 400.')" --check . eq 2
  ```
  预期：`ConversationClient.switchAcpModel` 的文档字符串和
  `RemoteConversation.switchAcpModel` 说什么 `F09.acp-model-deferred` 和
  `F09.ts-client` 观察：在第一次运行之前，服务器回答 200 并存储第一个会话的模型，并且非 ACP 会话得到
  400. 两者都没有承诺 409。
- **加载插件 (`F09.load-plugin`).** 开始 `PID` 从保存的设置中 `qa-f09-mkt` 其市场 [注册] 在其上 `agent_context` (未自动加载)，然后在捕获套接字时加载插件。
  ```sh
  AS=$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: encrypted' --field agent_settings --unsafe-unredacted \
    | jq -c --arg m "$MKT" '.tools = [] | .agent_context.registered_marketplaces = [{"name": "qa-f09-mkt", "source": $m}]')
  PID=$(control-agent-server conversation start --no-autotitle --body-json "{\"agent_settings\": $AS, \"secrets_encrypted\": true}" --print-id)
  control-agent-server api GET "/api/conversations/$PID" --query include_skills=true --quiet \
    --check agent.agent_context.registered_marketplaces.0.name eq qa-f09-mkt --check agent.agent_context.skills len-eq 0 --check hook_config missing
  control-agent-server ws start "/sockets/events/$PID" --name qa-f09-plugin --duration 120
  control-agent-server api POST "/api/conversations/$PID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin@qa-f09-mkt"}' \
    --expect 200 --check success eq true --save F09.load-plugin/load
  control-agent-server api GET "/api/conversations/$PID" --query include_skills=true --quiet \
    --check agent.agent_context.skills len-eq 2 --check agent.agent_context.skills contains qa-f09-mkt-plugin-skill \
    --check agent.agent_context.skills contains 'qa-f09-mkt-plugin:qa-hello' \
    --check hook_config.user_prompt_submit len-eq 1 --check hook_config.user_prompt_submit.0.hooks.0.command eq 'echo QA_PLUGIN_HOOK' \
    --save F09.load-plugin/get
  control-agent-server state cat "server/workspace/conversations/${PID//-/}/base_state.json" --max-chars 200 \
    --contains qa-f09-mkt-plugin-skill --check hook_config.user_prompt_submit len-eq 1
  control-agent-server ws read qa-f09-plugin --kinds ConversationStateUpdateEvent --contains qa-f09-mkt-plugin-skill --expect-min 1 --wait 20 --save F09.load-plugin/agent-frame
  control-agent-server ws stop qa-f09-plugin --kinds ConversationStateUpdateEvent --contains QA_PLUGIN_HOOK --expect-min 1 --wait 20
  ```
  在负载之前智能体没有技能，也没有钩子。 之后， `GET` (with `include_skills=true`) 列出了插件的技能及其命令（即技能） `qa-f09-mkt-plugin:qa-hello`), `hook_config` 该插件的
  `UserPromptSubmit` 钩子，`base_state.json` 两者都有，并且套接字推送了 `agent` 和 `hook_config` 的状态更新。
- **加载的钩子运行（`F09.load-plugin-hook-runs`）。**开机运行一圈
  `PID`.

  需要：`F09.load-plugin`
  ```sh
  control-agent-server conversation send "$PID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$PID" --quiet --check execution_status eq finished
  control-agent-server conversation events "$PID" --kinds HookExecutionEvent --contains '"stdout": "QA_PLUGIN_HOOK' --expect-count 1 --save F09.load-plugin-hook-runs/hook-events
  ```
  一个`HookExecutionEvent`(`hook_event_type``UserPromptSubmit``stdout`
  `QA_PLUGIN_HOOK`) 在前，而转接在此结束。
- ** 插件加载错误 (`F09.load-plugin-errors`)。** 没有市场或没有智能体上下文的对话，然后在 `QID` 上有坏的引用； 裸名是阳性对照。

  需要：`F09.acp-model-deferred`、`F09.load-plugin`
  ```sh
  control-agent-server api POST "/api/conversations/$CID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin"}' \
    --expect 400 --check detail contains 'No marketplaces registered' --save F09.load-plugin-errors/no-marketplaces
  control-agent-server api POST "/api/conversations/$AID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin"}' \
    --expect 400 --check detail contains 'No agent context available' --save F09.load-plugin-errors/no-agent-context
  GONE=$(printf '%s' "$AS" | jq -c --arg m "$MKT-gone" '.agent_context.registered_marketplaces = [{"name": "qa-f09-gone", "source": $m}]')
  NID=$(control-agent-server conversation start --no-autotitle --body-json "{\"agent_settings\": $GONE, \"secrets_encrypted\": true}" --print-id)
  control-agent-server api POST "/api/conversations/$NID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin@qa-f09-gone"}' \
    --expect 400 --check detail contains 'Local plugin path does not exist' --save F09.load-plugin-errors/unfetchable-marketplace
  control-agent-server api GET "/api/conversations/$NID" --query include_skills=true --quiet --check agent.agent_context.skills len-eq 0 --check hook_config missing
  QID=$(control-agent-server conversation start --no-autotitle --body-json "{\"agent_settings\": $AS, \"secrets_encrypted\": true}" --print-id)
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin@qa-f09-other"}' \
    --expect 404 --check detail eq "Marketplace 'qa-f09-other' is not registered" --save F09.load-plugin-errors/unknown-marketplace
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-nope@qa-f09-mkt"}' \
    --expect 404 --check detail eq "Plugin 'qa-f09-nope' not found in marketplace 'qa-f09-mkt'"
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-nope"}' \
    --expect 404 --check detail eq "Plugin 'qa-f09-nope' not found in any registered marketplace"
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": ""}' --expect 400 --check detail eq 'Plugin reference must not be empty'
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin@"}' --expect 400 --check detail contains 'plugin-name@marketplace-name'
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{}' --expect 422 --check detail.0.loc.1 eq plugin_ref
  control-agent-server api POST /api/conversations/00000000-0000-4000-8000-000000000000/load_plugin --json '{"plugin_ref": "qa-f09-mkt-plugin"}' --expect 404
  control-agent-server api GET "/api/conversations/$QID" --query include_skills=true --quiet --check agent.agent_context.skills len-eq 0 --check hook_config missing
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin"}' --expect 200 --save F09.load-plugin-errors/bare-name
  control-agent-server api GET "/api/conversations/$QID" --query include_skills=true --quiet \
    --check agent.agent_context.skills contains qa-f09-mkt-plugin-skill --check hook_config.user_prompt_submit len-eq 1
  ```
  400 无市场 (`CID`) 和无智能体上下文 (the ACP)
  `AID`), 400 `Local plugin path does not exist: ...` 时，表示唯一注册的市场目录缺失（`NID`，该目录没有技能或钩子），404 未注册市场，以及未知插件（有或无市场目录），400 为空或半引用，422 无字段，404 未知对话。 其中 None 发生了更改 `QID`，然后裸名称 `qa-f09-mkt-plugin` 通过唯一注册的市场和负载进行解析。
- **加载相同的插件两次（`F09.load-plugin-twice`），已知错误。**再次将插件加载到 `QID` 中，现在使用其完整参考。

  需要：`F09.load-plugin-errors`
  ```sh
  control-agent-server api POST "/api/conversations/$QID/load_plugin" --json '{"plugin_ref": "qa-f09-mkt-plugin@qa-f09-mkt"}' --expect 200 --save F09.load-plugin-twice/second-load
  control-agent-server api GET "/api/conversations/$QID" --query include_skills=true --quiet \
    --check agent.agent_context.skills len-eq 2 --check agent.agent_context.skills contains qa-f09-mkt-plugin-skill --check hook_config.user_prompt_submit len-ge 1
  control-agent-server api GET "/api/conversations/$QID" --quiet --check hook_config.user_prompt_submit len-eq 1 --save F09.load-plugin-twice/get  # bug：状态 eq 200 && 检查.0.实际包含“echo QA_PLUGIN_HOOK”
  ```
  第二个加载是200，技能没有重复（仍然有两个）。
  预期：还有一份钩子副本。 今天 `hook_config.user_prompt_submit`
  有两个完全相同的条目，因为`_merge_runtime_plugin_hooks`在`HookConfig.merge`后不进行去重，然后钩子就会在每条消息上运行两次（见实时：一个`HookExecutionEvent`对应两个用户消息）。 一个客户端重试 `load_plugin` 将每个钩子的副作用加倍。
- **从 Python SDK (`F09.load-plugin-sdk`) 加载插件。**与注册市场的新对话 `SID`，从 SDK 程序重新附加。

  需要：`F09.load-plugin`
  ```sh
  SID=$(control-agent-server conversation start --no-autotitle --body-json "{\"agent_settings\": $AS, \"secrets_encrypted\": true}" --print-id)
  control-agent-server api GET "/api/conversations/$SID" --query include_skills=true --quiet --check agent.agent_context.skills len-eq 0 --check hook_config missing
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f09-sdk"
  control-agent-server exec --env SID="$SID" --env WD="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f09-sdk" --expect-output SDK_LOAD_PLUGIN_OK \
    --save F09.load-plugin-sdk/program -- .venv/bin/python - <<'PY'
  import os
  import uuid

  import httpx

  from openhands.sdk import RemoteConversation, RemoteWorkspace

  ws = RemoteWorkspace(host=os.environ["AGENT_SERVER_URL"], api_key=os.environ["SESSION_API_KEY"], working_dir=os.environ["WD"])
  conv = RemoteConversation.attach(ws, uuid.UUID(os.environ["SID"]), visualizer=None)
  try:
      conv.load_plugin("qa-f09-nope@qa-f09-mkt")
      raise AssertionError("load_plugin accepted an unknown plugin")
  except httpx.HTTPStatusError as e:
      assert e.response.status_code == 404, e
  conv.load_plugin("qa-f09-mkt-plugin@qa-f09-mkt")
  print("SDK_LOAD_PLUGIN_OK")
  conv.close()
  PY
  control-agent-server api GET "/api/conversations/$SID" --query include_skills=true --quiet \
    --check agent.agent_context.skills contains qa-f09-mkt-plugin-skill --check hook_config.user_prompt_submit len-eq 1 --save F09.load-plugin-sdk/get
  ```
  未知插件引发 `httpx.HTTPStatusError` 状态为 404 (找不到) SDK 它会记录日志并重新抛出异常，真正的 ref 返回 `None`, and `GET` 然后显示插件的技能和一个 `UserPromptSubmit` hook.
- **重新启动 (`F09.restart-persist`)。**重新启动服务器并读回每个切换的对话； 然后运行一圈`RID`。

  需要：`F09.switch-profile`、`F09.acp-model-deferred`、`F09.load-plugin`
  ```sh
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$CID" --quiet --check agent.llm.model eq openai/qa-f09-ws --check agent.llm.usage_id eq qa-f09-ws --save F09.restart-persist/cid
  control-agent-server api GET "/api/conversations/$AID" --quiet --check agent.acp_model eq opus --check current_model_id eq opus --save F09.restart-persist/aid
  control-agent-server api GET "/api/conversations/$PID" --query include_skills=true --quiet \
    --check agent.agent_context.skills contains qa-f09-mkt-plugin-skill --check hook_config.user_prompt_submit len-eq 1 --save F09.restart-persist/pid
  control-agent-server api GET "/api/conversations/$RID" --quiet --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.llm.usage_id eq profile:deepseek-pro
  control-agent-server conversation send "$RID" --text 'Reply with the single word: ok' --wait --until finished,error --timeout 240
  control-agent-server api GET "/api/conversations/$RID" --until-ok 60 --quiet --check execution_status eq finished \
    --check 'stats.usage_to_metrics.profile:deepseek-pro.accumulated_token_usage.prompt_tokens' gt "$PRO1" --save F09.restart-persist/rid-stats
  ```
  所有四次对话都以切换的形式返回，重启后第一次发言又回到了`deepseek-pro`（词元数量的增长超过了）
  `PRO1`).

<a id="gotchas"></a>

## 陷阱

- 每个开关都回答 `{"success": true}`，仅此而已； 使用 `GET /api/conversations/{id}` 读回结果（它服务于自动保存的
  `base_state.json`，因此在空闲对话中它会立即显示切换）或带有键 `agent` 的 `ConversationStateUpdateEvent`。 当步骤运行时，`GET` 保留旧的 LLM 直到步骤结束 (`F09.switch-llm-mid-run-get`)； 套接字和运行本身立即切换，因此在断言 `GET` 之前等待运行（或读取套接字）。
- `switch_llm` 与已注册的 `usage_id`（默认
  `default` once the 智能体初始化，或者在注册之前使用的任何 id 安装配置，当配置不同时替换注册的条目，并保留该 id 的使用 `stats.usage_to_metrics` (`F09.switch-llm-registered-usage-id`); 一个完全相同的配置会复用注册的 LLM所以切换回是便宜的。 `switch_profile` 重用了缓存的副本 `profile:<name>` 在首次使用时（`F09.switch-profile-edited`).
- 按使用情况计 `usage_id` 在 `stats.usage_to_metrics`但仅限于 LLMs 注册后智能体已初始化 (`F09.switch-llm-before-first-run`); 当成本很重要时，在切换之前发送一条消息（或使用初始消息创建）。
- 智能体由第一条消息初始化（`conversation send
  --no-run` 就足够了）或运行，而不是通过创建； ACP 智能体仅在
  第一次运行，即子进程开始时。
- LLM 等于智能体的汇总上下文压缩器随之切换（相同模型，`usage_id` `condenser`）； 具有自己配置的上下文压缩器被保留。
- `switch_llm` 使用服务器的密码解密 `api_key` 中的 `gAAAAA` token 和其他机密字段，因此配置读取为
  `X-Expose-Secrets: encrypted` 可以按原样发回。 A
  `provider_connection_id` 在交换机处解析一次，解析后的密钥与智能体一起存储（加密）； 稍后删除连接不会影响已安装的LLM，即使重新启动也是如此。
- 配置文件从 `OH_PERSISTENCE_DIR/profiles` 读取（此处
  `home/.openhands/profiles`); 配置文件名称遵循 LLM 配置文件规则 (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)，此处打破这些规则的名称是 400（而不是 `/api/profiles/{name}` 中的 422）。
- `load_plugin` 仅搜索在对话智能体的 `agent_context.registered_marketplaces` 中注册的市场（在 `agent_settings.agent_context` 中开始与它们的对话）； 不参考服务器配置的 `registered_marketplaces` 和 `/api/plugins` 安装。 注册`auto_load: true`（如
  `fixture marketplace` 打印的 `registration`）在智能体初始化（第一条消息）时加载市场的插件和独立技能，没有任何 `load_plugin`； 这个系列在没有它的情况下注册，因此负载是添加插件的原因。
- 插件命令变成名为 `<plugin>:<command>` 的技能，并且
  `GET /api/conversations/{id}` 将 `agent.agent_context.skills` 修剪为 `[]`，除非 `include_skills=true`。
- `switch_acp_model` 第一次运行之前仅保留模型； 提供商的能力 (`supports_runtime_model_switch`) 和
  在会话开始之前，`available_models` 是未知的（`false`、`[]`）。 来自实时交换机的 504 将其 `detail` 重写为 `Internal Server Error`； 阅读`exception`。 TypeScript 客户端的 `switchAcpModel` 文档字符串记录了这个 200-and-defer 行为（`F09.acp-model-deferred`，
  `F09.ts-client`, `F09.ts-client-acp-docs`).
- 实时 ACP 会话需要提供商的 CLI 及其帐户。 对于
  `claude-code`、DeepSeek 的 Anthropic 兼容 API 作为帐户（机密 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` 和
  `ANTHROPIC_API_KEY=$DEEPSEEK_API_KEY`），并且作为 root 克劳德代码也需要
  `IS_SANDBOX=1` 或会话拒绝服务器请求的 `bypassPermissions` 模式。 每个这样的回合都会发送 Claude Code 自己的系统提示词（大约 36k 提示词 token）。 ACP智能体记录了其用法
  `usage_id` `acp-managed`，带电开关后面有 `model_name`。
- 占位符对话 (`conversation start --placeholder-agent`) 指向 `http://127.0.0.1:9/v1`，因此在切换后完成的运行证明切换后的模型已运行。
