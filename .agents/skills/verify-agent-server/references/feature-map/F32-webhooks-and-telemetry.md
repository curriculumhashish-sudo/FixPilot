<a id="event-webhooks-and-product-telemetry"></a>

# 事件 Webhook 和产品遥测

服务器自行推出的内容，无需调用路由。 中的每个条目
`config.webhooks` (a `WebhookSpec`) 订阅所有对话：它缓冲对话事件，并将其作为 POSTs 数组发送到 JSON
`{base_url}/events/<conversation id hex>`，它 POSTs 对话
当创建、暂停、中断、更新或删除对话时，`ConversationInfo` 到 `{base_url}/conversations`。 请求携带配置的`headers`和服务器自己的会话密钥，批量刷新时
`event_buffer_size` 被到达或 `flush_delay` 秒后第一个排队事件（或当队列达到 `max_batch_bytes` 时）失败的批次将被重试并重新排队，队列限制会丢弃最老的事件，并在会话关闭时将排队事件刷新。 自动化和 OpenHands 应用程序服务器消耗这些。 另外，产品遥测技术还发送一小部分列入许可名单的经过净化的诊断事件（`agent_server.server_started`、
将 `conversation_created`、`conversation_finished` 等发送给导出器，但仅限已配置导出器*并且*已通过设置或环境获得同意时；设置 `DO_NOT_TRACK` 时绝不发送。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_service.py`、`openhands-agent-server/openhands/agent_server/pub_sub.py`、`openhands-agent-server/openhands/agent_server/config.py`、`openhands-agent-server/openhands/agent_server/env_parser.py`、`openhands-agent-server/openhands/agent_server/telemetry/`、`openhands-agent-server/openhands/agent_server/init_router.py`、`openhands-agent-server/openhands/agent_server/settings_router.py`、`openhands-agent-server/openhands/agent_server/api.py`

需求：`llm`

发射：`--webhook-sink`

路线：None

<a id="sub-features"></a>

## 子功能

- `F32.events-post`：运行的事件通过智能体的回复和 `finished` 状态更新以 JSON 数组的形式到达 `POST {base_url}/events/<conversation id hex, no dashes>`。
- `F32.events-session-key`：每个Webhook请求携带`Content-Type: application/json`，服务器的第一个会话密钥为`X-Session-API-Key`。
- `F32.events-full-state`：对话的每个附加（其创建以及重新启动后的首次使用）都会使用密钥 `full_state` 发布瞬态 `ConversationStateUpdateEvent`。
- `F32.events-no-deltas`：流式传输运行的 `StreamingDeltaEvent` 到达事件 WebSocket，但从未到达 Webhook。
- `F32.conversation-created`: 创建对话 POSTs `ConversationInfo` `{base_url}/conversations`。
- `F32.conversation-lifecycle`：暂停、中断、更新和删除对话，每次 POST 再次其信息（`paused`、`paused`、新标题、`deleting`）。
- `F32.custom-headers`：Webhook 的 `headers` 和 `base_url` 路径前缀适用于事件和对话帖子。
- `F32.buffer-size`：一旦 `event_buffer_size` 事件排队，它们就会立即发布，无需等待 `flush_delay`。
- `F32.buffer-stranded`：在批次运行期间到达的事件在缓冲区再次满时立即发布，直到 `flush_delay` 才保留（请参阅陷阱）。
- `F32.flush-delay`：部分缓冲区在第一个事件发生后 `flush_delay` 秒发布； 稍后的事件不会重新启动计时器。
- `F32.webhook-spec-docs`：OpenAPI 模式中发布的 `WebhookSpec` 字段描述（`POST /api/init` 的 `webhooks` 的项目类型）说明了真实事件路径和刷新计时器（请参阅陷阱）。
- `F32.flush-on-close`：删除会话在 `DELETE` 返回之前发布其排队事件，并且优雅的服务器停止发布每个会话的队列。
- `F32.backpressure`：`max_batch_bytes` 限制每个请求（大于单独发布的事件），`max_queue_size` 和 `max_queue_bytes` 删除最早的排队事件并发出警告。
- `F32.retry`：回答 500 的接收者在每个事件批次和每个对话帖子中获得 `num_retries + 1` 次尝试。
- `F32.requeue`：耗尽其重试的批次将被重新排队并在下一次刷新时再次发送，而不是被丢弃。
- `F32.slow-receiver`：缓慢的 Webhook 接收方不得保留报告 `finished` 接受新运行的对话（再现真实的 409； 请参阅陷阱）。
- `F32.env-config`: `OH_WEBHOOKS_0_*` 环境变量配置 Webhook 并逐个字段覆盖配置文件的第一个 Webhook 字段。
- `F32.telemetry-off-by-default`：没有出口商，或者`http`出口商未经同意，不发货。
- `F32.telemetry-lifecycle`：在 `http` 导出者并同意的情况下，`server_started` 启动时到达，`server_stopped` 正常停止，与 `{"schema_version": 1, "events": [...]}` 和配置的持有者令牌一样。
- `F32.telemetry-conversation`：运行在请求的 `user_id` 下发出 `conversation_created` 和 `conversation_finished`，带有假名 `conversation_ref`，但没有提示词或对话 ID。
- `F32.telemetry-request-failed`：未处理的500错误会 `request_failed` 路由模板（而不是具体的路径），异常类和响应的 `error_id`，由 `X-OpenHands-Telemetry-Distinct-Id` 传递，不包括异常消息。
- `F32.telemetry-conversation-failed`：以 `error` 结尾的运行发出 `conversation_failed` (`terminal_status` `error`) 和 `conversation_error`，错误代码为 `error_class`，但没有错误的详细文本。
- `F32.telemetry-usage-buckets`：`conversation_finished` 报告 token 以及运行实际使用情况的成本范围。
- `F32.telemetry-consent-settings`：通过 `PATCH /api/settings` 授予或拒绝同意 `misc_settings_diff` 立即开始或停止交付，已持久化同意在重新启动后启用遥测。
- `F32.telemetry-env-override`：`OH_TELEMETRY_CONSENT=denied` 和 `OH_TELEMETRY_CONSENT_MODE=override` 击败授予的设置。
- `F32.telemetry-kill-switch`: `DO_NOT_TRACK=1` 击败所有同意来源。
- `F32.telemetry-salt-and-kind`：没有盐 `conversation_ref` 由 `OH_SECRET_KEY` 键控（重新启动时相同的引用）； `OH_TELEMETRY_SALT` 重新设置密钥（在重新启动时同样如此），并且 `OH_TELEMETRY_DEPLOYMENT_KIND` 标记每个事件。
- `F32.telemetry-salt-docs`：OpenAPI模式中发布的`TelemetrySpec.salt`描述指出了真实的回退方案密钥（机密密钥）。
- `F32.deferred-init`：休眠 Pod 不发送任何内容，直到 `POST /api/init` 交付 `telemetry` 和 `webhooks`； 然后是`server_started`，对话遥测和Webhook流程。
- `F32.deferred-init-flag`：来自初始化的延迟 Pod 报告的事件 `deferred_init: true`（重现真正的错误标签； 请参阅陷阱）。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- 配置：JSON配置文件中的`webhooks`（`OPENHANDS_AGENT_SERVER_CONFIG_PATH`），每一个`WebhookSpec`：`base_url`，`headers`，`event_buffer_size`（5），
  `flush_delay` (30 s), `num_retries` (3), `retry_delay` (5 s),
  `max_queue_size`、`max_batch_bytes`、`max_queue_bytes`。 `发射
  --Webhook-sink` starts a recording sink named `Webhook` 并将其添加为
  `flush_delay` 1; `restart --config-json '{"webhooks": [...]}'` 替换列表。 每个菜谱都以 `sink read` 读取交货。 OpenAPI 文档 (`GET /openapi.json`) 发布了 `WebhookSpec` 和 `TelemetrySpec` 及其字段描述，作为 `POST /api/init` 正文 (`InitRequest`) 的一部分； `F32.webhook-spec-docs`和`F32.telemetry-salt-docs`在那里阅读它们。
- 环境：`OH_WEBHOOKS='[...]'`或`OH_WEBHOOKS_0_BASE_URL`，
  `OH_WEBHOOKS_0_EVENT_BUFFER_SIZE`, `OH_WEBHOOKS_0_FLUSH_DELAY`,
  `OH_WEBHOOKS_0_HEADERS`（JSON）等； 他们覆盖文件（`F32.env-config`）。
- REST（副作用，由其他家族拥有）：`POST /api/conversations`，
  `POST /api/conversations/{id}/events`, `/run`, `/pause`, `/interrupt`,
  `PATCH` 和 `DELETE /api/conversations/{id}` 进行交付； `PATCH /api/settings`与`misc_settings_diff.telemetry.consent`（`granted`、`denied`）是同意开关Agent Canvas翻转； `POST /api/init` 可以将 `webhooks` 和 `telemetry` 传送到延迟 Pod。
- 遥测配置：`OH_TELEMETRY_EXPORTER`（`none`、`http`、`posthog`）、
  `OH_TELEMETRY_HTTP_ENDPOINT`, `OH_TELEMETRY_HTTP_TOKEN`,
  `OH_TELEMETRY_FLUSH_DELAY`, `OH_TELEMETRY_EVENT_BUFFER_SIZE`,
  `OH_TELEMETRY_SALT`、`OH_TELEMETRY_DEPLOYMENT_KIND`（或配置文件中的`telemetry`）； `misc_settings.telemetry.consent` 的同意，
  `OH_TELEMETRY_CONSENT`（`granted`/`denied`) 与
  `OH_TELEMETRY_CONSENT_MODE`（`seed`，默认值或 `override`），以及
  `DO_NOT_TRACK` 终止开关。 食谱使用`restart --env`。
- SDK/TypeScript客户端：无客户端方法； `StartConversationRequest.user_id` 成为遥测 `distinct_id` 和 `X-OpenHands-Telemetry-Distinct-Id` 属性 `request_failed` 事件。 接收器是自动化服务和 OpenHands 应用服务器（`/events/{id}` 和 `/conversations`）。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用 `--webhook-sink` 启动的新运行已上线并导出：CLI 启动了名为 `webhooks` 的记录接收器并将其写入
  `config.webhooks` 和 `flush_delay` 1（默认 `event_buffer_size` 5，
  `num_retries` 3). `$DEEPSEEK_API_KEY` 已设置。 下面的块激活 deepseek-flash 并将接收器的 URL 保留在 `$WH` 中，以便重写 `webhooks` 的项目符号。
  ```sh
  control-agent-server llm preset deepseek
  WH=$(control-agent-server fixture http-sink --name webhooks --print-path)
  test -n "$WH"
  ```
- 在这一轮中，子弹从上到下运行。 几个项目符号 `restart` 使用新的 `webhooks` 列表（`restart --config-json` 替换整个列表）或新的遥测变量； 每个人都这么说。 异步等待 `sink read --wait N` 交付，轮询直到 `--expect-min` 成立，然后应用 `--expect-max`； 因此，准确的计数意味着“当最少的人到达时，没有更多的人到达”。

- **运行的事件到达 Webhook (`F32.events-post`)。**真正的 deepseek-flash 运行与启动 Webhook（`flush_delay` 1，缓冲区 5）。
  ```sh
  CID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with exactly: ok' --wait --print-id)
  HEX=${CID//-/}
  control-agent-server sink read --path "/events/$HEX" --contains '"key": "execution_status", "value": "finished"' --expect-min 1 --wait 15 --save F32.events-post/finished
  MID=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query source=agent --query sort_order=TIMESTAMP_DESC --query limit=1 --field items.0.id)
  test -n "$MID"
  control-agent-server sink read --path "/events/$HEX" --contains "\"id\": \"$MID\"" --expect-min 1 --expect-max 1
  control-agent-server sink read --path "/events/$HEX" --contains '"body": {' --expect-max 0
  control-agent-server sink read --path "/events/$CID" --expect-max 0
  ```
  交付任务 `/events/<id without dashes>` (None 交付给虚线 id)，所有内容都是 JSON 数组（没有对象体），其中一项携带了
  `execution_status` → `finished` 更新，智能体的最后存储事件（其回复，取决于模型是 `MessageEvent` 或 `finish` `ActionEvent`）恰好一次到达，返回的 id `GET .../events/search`。
- **每个请求的会话密钥和内容类型 (`F32.events-session-key`)。**接收方可以使用服务器自己的密钥进行回调。
  ```sh
  test -s "$AGENT_SERVER_VERIFY_RUN/private/session_api_key"
  TOTAL=$(control-agent-server sink read | python3 -c 'import json, sys; print(json.load(sys.stdin)["requests"])')
  test "$TOTAL" -ge 2
  control-agent-server sink read --contains "\"X-Session-API-Key\": \"$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")\"" --expect-min "$TOTAL" --save F32.events-session-key/all-requests
  control-agent-server sink read --contains '"Content-Type": "application/json"' --expect-min "$TOTAL"
  ```
  到目前为止，所有请求（事件批次和会话帖子）都记录了
  `X-Session-API-Key` 等于运行的密钥和 JSON 内容类型。 保存的证据显示标题为 `<redacted:session-api-key>`。
- **已创建对话 (`F32.conversation-created`)。**上面的运行发布了一次`ConversationInfo`。

  需要：`F32.events-post`
  ```sh
  control-agent-server sink read --path /conversations --contains "\"id\": \"$CID\"" --expect-min 1 --expect-max 1 --wait 15 --save F32.conversation-created/info
  control-agent-server sink read --path /conversations --contains '"body": [' --expect-max 0
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished
  ```
  `/conversations` 中只有一个对话对象体到达：运行的完成仅在事件 Webhook（上一个圆点）中报告，而不是作为第二个对话帖子。
- **每次连接时的完整状态快照 (`F32.events-full-state`)。**快照是暂时的：它被发送给订阅者，而不是被存储。 重新启动后，加载会话的第一个路由会重新附加 Webhook 并发送一个新的。

  需要：`F32.events-post`
  ```sh
  control-agent-server sink read --path "/events/$HEX" --contains '"key": "full_state"' --expect-min 2 --expect-max 2 --wait 15
  control-agent-server sink read --path "/events/$HEX" --contains '"api_key": "**********"' --expect-min 1
  test -n "$DEEPSEEK_API_KEY"
  control-agent-server sink read --contains "$DEEPSEEK_API_KEY" --expect-max 0
  control-agent-server conversation events "$CID" --key full_state --expect-count 0
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=1 --expect 200 --quiet
  control-agent-server sink read --path "/events/$HEX" --contains '"key": "full_state"' --expect-min 3 --expect-max 3 --wait 15 --save F32.events-full-state/after-restart
  ```
  在运行期间，有两个快照到达（一个在快照创建时，另一个在快照删除时） Webhook 在创建时附加，最终状态与之关联） 他们携带的智能体's LLM 配置文件 `api_key` 隐藏的，以及真实的 DeepSeek 密钥在交付中未出现。 None 它存在于存储的事件中，重启后产生的事件搜索产生了第三个。
- **对话生命周期帖子 (`F32.conversation-lifecycle`)。** Pause, interrupt, rename and delete an idle conversation (no model is needed).
  ```sh
  LID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_LIFE --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$LID/pause" --expect 200
  control-agent-server api GET "/api/conversations/$LID" --check execution_status eq paused
  control-agent-server sink read --path /conversations --contains '"execution_status": "paused"' --expect-min 1 --expect-max 1 --wait 15
  control-agent-server api POST "/api/conversations/$LID/interrupt" --expect 200
  control-agent-server sink read --path /conversations --contains '"execution_status": "paused"' --expect-min 2 --expect-max 2 --wait 15
  control-agent-server api PATCH "/api/conversations/$LID" --json '{"title": "QA_F32_TITLE"}' --expect 200
  control-agent-server api GET "/api/conversations/$LID" --check title eq QA_F32_TITLE
  control-agent-server api DELETE "/api/conversations/$LID" --expect 200
  control-agent-server api GET "/api/conversations/$LID" --expect 404
  control-agent-server sink read --path /conversations --contains "\"id\": \"$LID\"" --expect-min 5 --expect-max 5 --wait 15 --save F32.conversation-lifecycle/posts
  control-agent-server sink read --path /conversations --contains '"execution_status": "paused"' --expect-min 3 --expect-max 3
  control-agent-server sink read --path /conversations --contains '"title": "QA_F32_TITLE"' --expect-min 2 --expect-max 2
  control-agent-server sink read --path /conversations --contains '"execution_status": "deleting"' --expect-min 1 --expect-max 1
  ```
  五篇帖子：创建了（`idle`), paused, interrupted (still `paused`; 在执行下一个操作之前，因为这些帖子是无序的后台任务，所以已被重命名（仍然） `paused`, 新标题) 和 (删除)。 这是这条路径上目前唯一暂停或删除的对话，所以状态计数是准确的。
- **Webhook (`F32.events-no-deltas`) 上没有流式传输增量。** 流式传输运行，以事件 WebSocket 作为阳性对照。
  ```sh
  SID=$(control-agent-server conversation start --tools none --no-autotitle --llm-json '{"stream": true}' --no-run --prompt 'Count from 1 to 20 separated by spaces.' --print-id)
  control-agent-server ws start "/sockets/events/$SID" --name qa-f32-deltas --duration 180
  control-agent-server api POST "/api/conversations/$SID/run" --expect 200
  control-agent-server conversation wait "$SID" --until finished --timeout 120
  control-agent-server ws stop qa-f32-deltas --expect-kind StreamingDeltaEvent --wait 10 --save F32.events-no-deltas/socket
  control-agent-server sink read --path "/events/${SID//-/}" --contains '"key": "execution_status", "value": "finished"' --expect-min 1 --wait 15
  control-agent-server sink read --path "/events/${SID//-/}" --contains StreamingDeltaEvent --expect-max 0 --save F32.events-no-deltas/webhook
  ```
  端口接收到了 `StreamingDeltaEvent` frames 的 Webhook 通过接收到运行事件 `finished` 更新但没有差异。
- **自定义标头、路径前缀和缓冲区大小（`F32.custom-headers`、`F32.buffer-size`）。**在路径前缀、自定义标头下使用一个 Webhook 重新启动，
  `event_buffer_size` 2 和 600 s `flush_delay`，因此只有完整的缓冲区才能触发帖子。
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$WH/qa-f32-b\", \"event_buffer_size\": 2, \"flush_delay\": 600, \"headers\": {\"X-QA-F32\": \"qa-f32-header\"}}]}"
  BID=$(control-agent-server conversation start --placeholder-agent --no-autotitle --print-id)
  control-agent-server sink read --path "/qa-f32-b/events/${BID//-/}" --expect-max 0
  control-agent-server conversation send "$BID" --text QA_F32_BUFFER --no-run
  control-agent-server sink read --path "/qa-f32-b/events/${BID//-/}" --contains '"key": "full_state"' --expect-min 1 --expect-max 1 --wait 10 --save F32.buffer-size/first-batch
  control-agent-server sink read --path "/qa-f32-b/events/${BID//-/}" --contains SystemPromptEvent --expect-min 1 --expect-max 1
  control-agent-server sink read --path "/qa-f32-b/events/" --contains '"X-QA-F32": "qa-f32-header"' --expect-min 1 --save F32.custom-headers/events
  control-agent-server sink read --path /qa-f32-b/conversations --contains "\"id\": \"$BID\"" --expect-min 1
  control-agent-server sink read --path /qa-f32-b/conversations --contains '"X-QA-F32": "qa-f32-header"' --expect-min 1
  ```
  创建对话只截取了快照（1 < 2：没有发布）。 消息的第一个事件填充了缓冲区，`full_state`
  `SystemPromptEvent`) 已在几秒钟内发布，尽管计时器为 600 秒。 事件批次和对话帖子均已下架
  `/qa-f32-b/` 与 `X-QA-F32`（加上会话密钥）。
- **在进行中的批次期间发布的事件 (`F32.buffer-stranded`)。**相同的对话：消息及其 `last_user_message_id` 更新是在第一批发布时发布的，因此缓冲区 (2) 再次满了，并且一旦 POST 返回，它们就会发布。 存储的事件是最先出现的，因此子弹只能在传递时失败。

  需要：`F32.custom-headers`
  ```sh
  control-agent-server conversation events "$BID" --kinds MessageEvent --contains QA_F32_BUFFER --expect-count 1
  control-agent-server conversation events "$BID" --key last_user_message_id --expect-count 1
  control-agent-server sink read --path "/qa-f32-b/events/${BID//-/}" --contains QA_F32_BUFFER --expect-min 1 --wait 10 --save F32.buffer-stranded/after-wait
  ```
  消息及其更新被存储，并且在第二个批次中，用户消息在10秒内到达了接收器，而没有等待600秒的计时器、下一个事件爆发，或者对话的结束。 请参阅陷阱。
- **删除和关闭时刷新 (`F32.flush-on-close`)。**使用 `event_buffer_size` 100 和 600 秒计时器重新启动，因此除非对话关闭，否则不会发布任何内容。 `sleep` 为错误的短计时器提供了触发的机会（服务器的计时器正在测试中）。 两次重启都是在测试中的关闭。

  需要：`F32.custom-headers`
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$WH/qa-f32-c\", \"event_buffer_size\": 100, \"flush_delay\": 600}]}"
  control-agent-server sink read --path "/qa-f32-b/events/${BID//-/}" --contains QA_F32_BUFFER --expect-min 1 --save F32.flush-on-close/stranded-after-stop
  DID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_DELETE --no-autotitle --print-id)
  ZID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_SHUTDOWN --no-autotitle --print-id)
  sleep 2
  control-agent-server sink read --path /qa-f32-c/events/ --expect-max 0
  control-agent-server api DELETE "/api/conversations/$DID" --expect 200
  control-agent-server sink read --path "/qa-f32-c/events/${DID//-/}" --contains QA_F32_DELETE --expect-min 1 --expect-max 1 --save F32.flush-on-close/after-delete
  control-agent-server sink read --path "/qa-f32-c/events/${ZID//-/}" --expect-max 0
  control-agent-server restart
  control-agent-server sink read --path "/qa-f32-c/events/${ZID//-/}" --contains QA_F32_SHUTDOWN --expect-min 1 --save F32.flush-on-close/after-restart
  control-agent-server api GET "/api/conversations/$ZID" --expect 200
  ```
  第一次重新启动后，`QA_F32_BUFFER` 位于 `/qa-f32-b/`（已由 `F32.buffer-stranded` 发布，或通过优雅停止发布）。 2 秒后没有发布任何新对话； `DELETE` 仅在排队事件（快照、系统提示词、消息及其
  `last_user_message_id` 更新）在一批中发布，第二个 `restart` 的优雅停止发布了另一个会话的队列，该队列之后仍然存在。
- **从第一个事件 (`F32.flush-delay`) 刷新计时器。**使用 6 秒计时器和大缓冲区重新启动。 第二个事件在第一个事件后 3 秒到达； 由它重置的计时器将在大约 9 秒后启动，第一个事件的计时器将在大约 6 秒后启动。
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$WH/qa-f32-d\", \"event_buffer_size\": 100, \"flush_delay\": 6}]}"
  T0=$SECONDS
  TID=$(control-agent-server conversation start --placeholder-agent --no-autotitle --print-id)
  sleep 3
  control-agent-server conversation send "$TID" --text QA_F32_TIMER --no-run
  control-agent-server sink read --path "/qa-f32-d/events/${TID//-/}" --expect-max 0
  control-agent-server sink read --path "/qa-f32-d/events/${TID//-/}" --expect-min 1 --wait 15
  ELAPSED=$((SECONDS - T0))
  test "$ELAPSED" -ge 5
  test "$ELAPSED" -le 8
  control-agent-server sink read --path "/qa-f32-d/events/${TID//-/}" --expect-min 1 --expect-max 1 --contains QA_F32_TIMER --save F32.flush-delay/one-batch
  control-agent-server sink read --path "/qa-f32-d/events/${TID//-/}" --contains '"key": "full_state"' --expect-min 1 --expect-max 1
  ```
  3秒后没有发布任何内容。 一个批次与快照和消息在创建后5到8秒到达，正如字段的描述所说。
- **Webhook 字段描述 (`F32.webhook-spec-docs`).**协调器从 OpenAPI 文档中学习 `WebhookSpec`，其中它是 `POST /api/init` 的 `webhooks` 的项目类型。 它的描述与`F32.events-post`和`F32.flush-delay`所证明的相符：事件发生到
  `{base_url}/events/<conversation id hex>`，并且计时器从第一个排队事件开始并且不重置。
  ```sh
  control-agent-server api GET /openapi.json --auth none --quiet --check 'components.schemas.InitRequest.properties.webhooks.anyOf.0.items.$ref' eq '#/components/schemas/WebhookSpec' --check components.schemas.WebhookSpec.properties.base_url.description exists --check components.schemas.WebhookSpec.properties.flush_delay.description exists
  control-agent-server api GET /openapi.json --auth none --quiet --check components.schemas.WebhookSpec.properties.flush_delay.description not-contains 'Timer is reset on each new event'
  control-agent-server api GET /openapi.json --auth none --quiet --check components.schemas.WebhookSpec.properties.base_url.description not-contains 'Events will be sent to {base_url}/events and'
  ```
  描述中说明了每条会话的路径（`{base_url}/events/{conversation_id.hex}`）以及一个从第一个排队事件开始计时的定时器，该定时器不会被后续事件重置。 一个检查失败时会打印发布的内容。 请参阅陷阱。
- **批次和队列限制 (`F32.backpressure`)。**一次重新启动后三个 Webhook，全部具有大缓冲区和 600 秒计时器：一个具有
  `max_batch_bytes` 1（每个事件都更大），有一个`max_queue_size` 2，还有一个`max_queue_bytes` 1500（两个小事件一起大约800字节，单独的快照大约3KB）。 删除会刷新仍在排队的所有内容。
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$WH/qa-f32-bytes\", \"event_buffer_size\": 100, \"flush_delay\": 600, \"max_batch_bytes\": 1}, {\"base_url\": \"$WH/qa-f32-queue\", \"event_buffer_size\": 100, \"flush_delay\": 600, \"max_queue_size\": 2}, {\"base_url\": \"$WH/qa-f32-qbytes\", \"event_buffer_size\": 100, \"flush_delay\": 600, \"max_queue_bytes\": 1500}]}"
  PID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_LIMITS --no-autotitle --print-id)
  control-agent-server conversation events "$PID" --expect-count 3
  control-agent-server api DELETE "/api/conversations/$PID" --expect 200
  control-agent-server sink read --path "/qa-f32-bytes/events/${PID//-/}" --expect-min 4 --expect-max 4 --wait 10 --save F32.backpressure/one-event-per-request
  control-agent-server sink read --path "/qa-f32-bytes/events/${PID//-/}" --contains '"key": "full_state"' --expect-min 1 --expect-max 1
  control-agent-server sink read --path "/qa-f32-bytes/events/${PID//-/}" --contains SystemPromptEvent --expect-min 1 --expect-max 1
  control-agent-server sink read --path "/qa-f32-bytes/events/${PID//-/}" --contains QA_F32_LIMITS --expect-min 1 --expect-max 1
  control-agent-server sink read --path "/qa-f32-queue/events/${PID//-/}" --contains QA_F32_LIMITS --expect-min 1 --expect-max 1 --wait 10 --save F32.backpressure/trimmed-queue
  control-agent-server sink read --path "/qa-f32-queue/events/${PID//-/}" --contains '"key": "full_state"' --expect-max 0
  control-agent-server sink read --path "/qa-f32-qbytes/events/${PID//-/}" --contains QA_F32_LIMITS --expect-min 1 --expect-max 1 --wait 10 --save F32.backpressure/byte-trimmed-queue
  control-agent-server sink read --path "/qa-f32-qbytes/events/${PID//-/}" --expect-max 1
  control-agent-server sink read --path "/qa-f32-qbytes/events/${PID//-/}" --contains '"key": "full_state"' --expect-max 0
  control-agent-server sink read --path "/qa-f32-qbytes/events/${PID//-/}" --contains SystemPromptEvent --expect-max 0
  control-agent-server logs --grep 'Webhook queue exceeded' --expect-min 2
  ```
  这三类存储事件以及瞬时快照到达了第一个 Webhook 作为四个请求，一个事件（仅限快照，系统） 提示词单独的内容，单独的消息）。 第二 Webhook 获取了一个批次：最新的事件，带有消息，但没有快照，这是最早的，被丢弃了。 第三 Webhook 还收到一个批次的消息，但没有快照和系统提示词 （大约18 KB）：每个都超过了自己的字节限制，并在被队列化后立即丢弃。 每个有限的 Webhook 登录成功 `Webhook queue exceeded its configured count or byte limit` 警告（第一滴） 稍后的记录每100条记录记录一次。 第一个 Webhook在相同对话中，是正控件，即快照和系统提示词已经被发布。
- **重试针对失败的接收器 (`F32.retry`)。**一个接收器回答 500、`num_retries` 2 并且没有重试延迟； 600 秒计时器使事件批次保持排队状态，直到删除关闭对话。
  ```sh
  FAIL=$(control-agent-server fixture http-sink --name qa-f32-fail --status 500 --print-path)
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$FAIL\", \"event_buffer_size\": 100, \"flush_delay\": 600, \"num_retries\": 2, \"retry_delay\": 0}]}"
  RID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_RETRY --no-autotitle --print-id)
  control-agent-server sink read --name qa-f32-fail --path /events/ --expect-max 0
  control-agent-server api DELETE "/api/conversations/$RID" --expect 200
  control-agent-server sink read --name qa-f32-fail --path "/events/${RID//-/}" --contains QA_F32_RETRY --expect-min 3 --expect-max 3 --save F32.retry/event-attempts
  control-agent-server sink read --name qa-f32-fail --path /conversations --contains "\"id\": \"$RID\"" --expect-min 6 --expect-max 6 --wait 15 --save F32.retry/conversation-attempts
  ```
  关闭的刷新进行了3次（1 + `num_retries`)，与同一个批次的每条会话帖子（创建或删除）进行了3次，总共进行了6次。 `DELETE`仍然回答200。
- **失败的批次重新排队了`F32.requeue`).** 相同的失败 sink，1 秒计时器和 `num_retries` 1 (每刷新两次尝试丢弃的批次，每刷新一次重新排队的批次)。

  需要：`F32.retry`
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$FAIL\", \"event_buffer_size\": 100, \"flush_delay\": 1, \"num_retries\": 1, \"retry_delay\": 0}]}"
  QID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_REQUEUE --no-autotitle --print-id)
  control-agent-server sink read --name qa-f32-fail --path "/events/${QID//-/}" --contains QA_F32_REQUEUE --expect-min 6 --wait 30 --save F32.requeue/attempts
  control-agent-server sink read --name qa-f32-fail --path "/events/${QID//-/}" --contains '"key": "full_state"' --expect-min 6
  control-agent-server api DELETE "/api/conversations/$QID" --expect 200
  ```
  至少重发了三次相同的队列，包括最早的事件（快照）。 删除操作会在最后一个循环后结束，并且仍然返回200。
- **缓慢的接收器会阻止下一次运行 (`F32.slow-receiver`)，这是已知错误。** `llm-stub` 测试夹具代表 Webhook 接收器，需要 15 秒才能应答（其 `hang` 步骤； `http-sink`不能拖延）。 它需要聊天完成主体，因此挂起后它会删除事件批处理连接，并且服务器会记录失败的尝试； 15 秒，而不是失败，才是保持运行的原因。 对于 `event_buffer_size` 1，运行事件会内联发布，并且其发布会等待接收者。 相同的替代者首先立即回答（`reply:ok`）：该运行是正控制，因此 409 是接收器的延迟，而不是其他。 `trap` 使替身再次变得快速，因此以后的重新启动不会减慢。
  ```sh
  SLOW=$(control-agent-server fixture llm-stub --name qa-f32-slow --step reply:ok --print-path)
  trap 'control-agent-server fixture llm-stub --name qa-f32-slow --step reply:ok >/dev/null' EXIT
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$SLOW\", \"event_buffer_size\": 1, \"flush_delay\": 600, \"num_retries\": 0}]}"
  FASTID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with exactly: ok' --wait --print-id)
  control-agent-server api POST "/api/conversations/$FASTID/run" --expect 200 --save F32.slow-receiver/control-fast-receiver
  control-agent-server fixture llm-stub --name qa-f32-slow --step hang:15
  WCID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with exactly: ok' --wait --print-id)
  control-agent-server api GET "/api/conversations/$WCID" --check execution_status eq finished
  control-agent-server sink read --name qa-f32-slow --path "/events/${WCID//-/}" --expect-min 1
  control-agent-server api POST "/api/conversations/$WCID/run" --expect 200 --save F32.slow-receiver/run-after-finished  # bug：状态 eq 409 && response.body.detail 包含“对话已在运行”
  ```
  随着快速替补登场 `POST .../run` 立刻 `finished` 200 表示对话已结束，因此无需调用模型。
  预期：与缓慢替身相同。 实际：409`对话
  已经运行`直到接收器应答（这里大约 15 秒； 最多 30 秒），因为运行任务在清除自身之前会等待挂起的 Webhook 发布。 请参阅陷阱。
- **Webhook 来自环境 (`F32.env-config`)。**将失败的接收器与 1 s 计时器一起放入配置文件中，并仅覆盖 `base_url` 和
  `webhooks[0]` 的 `headers` 通过环境。

  需要：`F32.retry`
  ```sh
  control-agent-server restart --config-json "{\"webhooks\": [{\"base_url\": \"$FAIL\", \"flush_delay\": 1}]}" --env "OH_WEBHOOKS_0_BASE_URL=$WH/qa-f32-env" --env 'OH_WEBHOOKS_0_HEADERS={"X-QA-F32-Env": "qa-f32-env"}'
  EID=$(control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_ENV --no-autotitle --print-id)
  control-agent-server sink read --path "/qa-f32-env/events/${EID//-/}" --contains QA_F32_ENV --expect-min 1 --wait 15 --save F32.env-config/events
  control-agent-server sink read --path "/qa-f32-env/events/${EID//-/}" --contains '"X-QA-F32-Env": "qa-f32-env"' --expect-min 1
  control-agent-server sink read --path /qa-f32-env/conversations --contains "\"id\": \"$EID\"" --expect-min 1
  control-agent-server sink read --name qa-f32-fail --path "/events/${EID//-/}" --expect-max 0
  control-agent-server sink read --name qa-f32-fail --path /conversations --contains "\"id\": \"$EID\"" --expect-max 0
  control-agent-server api DELETE "/api/conversations/$EID" --expect 200
  ```
  事件和对话在文件的 URL 环境中，带有其头部，经过 1 秒的文件定时器（文件的其他字段仍然有效），而这个对话没有到达文件中指定的失败接收器。
- **遥测默认关闭 (`F32.telemetry-off-by-default`)。**
  `restart --reset-config` 删除启动 Webhook 和每个较早的覆盖。 首先是端点并未经出口商同意，然后
  `http` 已同意的出口商（空值表示不同意）。
  ```sh
  TS=$(control-agent-server fixture http-sink --name qa-f32-telemetry --print-path)
  control-agent-server restart --reset-config --env "OH_TELEMETRY_HTTP_ENDPOINT=$TS/v1/events" --env OH_TELEMETRY_FLUSH_DELAY=1 --env OH_TELEMETRY_CONSENT=granted
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_OFF --body-json '{"user_id": "qa-f32-off"}' --no-autotitle
  control-agent-server restart --env OH_TELEMETRY_EXPORTER=http --env OH_TELEMETRY_CONSENT=
  control-agent-server logs --grep 'enabled=False \(default\)' --expect-min 1
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_OFF --body-json '{"user_id": "qa-f32-off"}' --no-autotitle
  control-agent-server restart
  control-agent-server sink read --name qa-f32-telemetry --expect-max 0 --save F32.telemetry-off-by-default/nothing
  ```
  两分钟后，两个服务器生命周期和两个会话后， 端点没有收到任何东西。 日志显示导出器已构建 `enabled=False (default)`. 下一个圆点是同一组的阳性对照端点。
- **服务器生命周期事件 (`F32.telemetry-lifecycle`)。**获得环境的同意并添加 token。

  需要：`F32.telemetry-off-by-default`
  ```sh
  control-agent-server restart --env OH_TELEMETRY_CONSENT=granted --env OH_TELEMETRY_HTTP_TOKEN=qa-f32-token
  control-agent-server logs --grep 'enabled=True \(env_seed\)' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains '{"schema_version": 1, "events": [{"event": "agent_server.server_started", "distinct_id": "anon:' --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-lifecycle/started
  control-agent-server sink read --name qa-f32-telemetry --contains '"Authorization": "Bearer qa-f32-token"' --expect-min 1
  control-agent-server restart
  control-agent-server sink read --name qa-f32-telemetry --contains agent_server.server_stopped --expect-min 1 --expect-max 1 --save F32.telemetry-lifecycle/stopped
  control-agent-server sink read --name qa-f32-telemetry --contains agent_server.server_started --expect-min 2 --expect-max 2 --wait 15
  ```
  `server_started` 与 `schema_version` 1 一起到达，匿名
  `distinct_id` 和持有者令牌； 优雅地停下来
  `server_stopped`在重启返回之前，新进程发送了自己的`server_started`。
- **对话遥测已清理 (`F32.telemetry-conversation`)。**使用 `user_id`、自动化标签和提示词中的标记进行实际运行。

  需要：`F32.telemetry-lifecycle`
  ```sh
  UCID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with exactly: ok QA_F32_PRIVATE' --body-json '{"user_id": "qa-f32-user"}' --tag automationid=qa-f32 --wait --print-id)
  control-agent-server sink read --name qa-f32-telemetry --contains '"event": "agent_server.conversation_finished", "distinct_id": "qa-f32-user"' --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-conversation/finished
  control-agent-server sink read --name qa-f32-telemetry --contains '"event": "agent_server.conversation_created", "distinct_id": "qa-f32-user"' --expect-min 1 --expect-max 1 --save F32.telemetry-conversation/created
  REF=$(python3 -c 'import json, sys; print(next(e["properties"]["conversation_ref"] for line in sys.stdin for e in json.loads(line)["body"]["events"] if e["distinct_id"] == "qa-f32-user"))' < "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f32-telemetry.jsonl")
  test "${#REF}" -eq 32
  control-agent-server sink read --name qa-f32-telemetry --contains "\"conversation_ref\": \"$REF\", \"llm_model_family\": \"deepseek\", \"agent_kind\"" --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f32-telemetry --contains "\"conversation_ref\": \"$REF\", \"terminal_status\": \"finished\"" --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"llm_model_family": "deepseek"}' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"is_automation": true' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains QA_F32_PRIVATE --expect-max 0
  control-agent-server sink read --name qa-f32-telemetry --contains "$UCID" --expect-max 0
  control-agent-server sink read --name qa-f32-telemetry --contains "${UCID//-/}" --expect-max 0
  ```
  两个事件都使用 `qa-f32-user` 作为 `distinct_id`，并且都携带相同的 32-十六进制数据
  `conversation_ref` 而不是对话 id：`conversation_created` 带有模型系列（和自动化标志），`conversation_finished` 带有 `terminal_status` `finished` 以及系列作为其最后一个属性。 提示词和 id（虚线或非虚线）都没有出现在端点收到的内容中。 这些检查与每个事件自己的属性顺序相匹配，因此它们保存两个事件是一批还是两批到达。
- **未处理的错误 (`F32.telemetry-request-failed`)。**没有上下文压缩器的对话会使 `POST .../condense` 引发未处理的问题
  `ValueError` (500; condense 系列的一个已知错误，此处仅用作可靠的未处理异常）。 标头扮演浏览器的分析身份。
  ```sh
  RFC=$(control-agent-server conversation start --body-json '{"agent_settings": {"agent_kind": "openhands", "llm": {"model": "openai/qa-placeholder", "api_key": "qa-placeholder", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": [], "condenser": {"enabled": false}}}' --no-autotitle --no-run --prompt QA_F32_RF --print-id)
  ERR=$(control-agent-server api POST "/api/conversations/$RFC/condense" --header 'X-OpenHands-Telemetry-Distinct-Id: qa-f32-browser' --expect 500 --field error_id)
  test -n "$ERR"
  control-agent-server sink read --name qa-f32-telemetry --contains "\"error_id\": \"$ERR\"" --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-request-failed/event
  control-agent-server sink read --name qa-f32-telemetry --contains '"event": "agent_server.request_failed", "distinct_id": "qa-f32-browser"' --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"route_template": "/api/conversations/{conversation_id}/condense", "method": "POST", "status_code": 500, "error_class": "ValueError"' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains "$RFC" --expect-max 0
  control-agent-server logs --grep 'ValueError: Cannot condense' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains 'Cannot condense' --expect-max 0
  ```
  一 `request_failed` 事件携带相同的信息 `error_id` 作为500条记录，头部的身份，路由模板，方法，状态和
  `ValueError`; 会话 ID 和异常文本（服务器日志显示）均未到达端点。 如果压缩路由停止应答 500，请查找另一个未处理的异常：未报告 `HTTPException` 5xx。
- **token 和实际使用的成本区间 (`F32.telemetry-usage-buckets`)。**上面的运行使用了token； 它的结果事件应该这样说。

  需要：`F32.telemetry-conversation`
  ```sh
  control-agent-server api GET "/api/conversations/$UCID" --check stats.usage_to_metrics.default.accumulated_token_usage.prompt_tokens gt 0
  control-agent-server sink read --name qa-f32-telemetry --contains '"total_tokens_bucket": "' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"total_tokens_bucket": "unknown"' --expect-max 0 --save F32.telemetry-usage-buckets/outcome
  ```
  结果 token 个桶，如 `1000-10000`
  `cost_bucket` 除 `unknown` 之外，来自对话的统计信息。
- **运行失败 (`F32.telemetry-conversation-failed`)。**同样无法访问的模型，这次是运行，因此对话以
  `error` 没有模型调用。 存储的 `ConversationErrorEvent` 是第二个视图：它的 `code` 必须到达，而它的 `detail` 一定不会。
  ```sh
  FAILID=$(control-agent-server conversation start --body-json '{"user_id": "qa-f32-failed", "agent_settings": {"agent_kind": "openhands", "llm": {"model": "openai/qa-placeholder", "api_key": "qa-placeholder", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": [], "condenser": {"enabled": false}}}' --no-autotitle --prompt QA_F32_FAILED_RUN --wait --until error --timeout 120 --print-id)
  CODE=$(control-agent-server api GET "/api/conversations/$FAILID/events/search" --query kind=openhands.sdk.event.conversation_error.ConversationErrorEvent --field items.0.code)
  DETAIL=$(control-agent-server api GET "/api/conversations/$FAILID/events/search" --query kind=openhands.sdk.event.conversation_error.ConversationErrorEvent --field items.0.detail)
  test -n "$CODE"
  test -n "$DETAIL"
  control-agent-server sink read --name qa-f32-telemetry --contains '"event": "agent_server.conversation_failed", "distinct_id": "qa-f32-failed"' --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-conversation-failed/failed
  control-agent-server sink read --name qa-f32-telemetry --contains '"terminal_status": "error"' --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"event": "agent_server.conversation_error", "distinct_id": "qa-f32-failed"' --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-conversation-failed/error
  control-agent-server sink read --name qa-f32-telemetry --contains "\"error_class\": \"$CODE\"" --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains "$DETAIL" --expect-max 0
  control-agent-server sink read --name qa-f32-telemetry --contains QA_F32_FAILED_RUN --expect-max 0
  control-agent-server sink read --name qa-f32-telemetry --contains "${FAILID//-/}" --expect-max 0
  ```
  `conversation_failed` 报告 `terminal_status` `error`，以及
  `conversation_error`携带存储事件的`code`（类名，例如`LLMServiceUnavailableError`）作为`error_class`； 存储的 `detail`（提供者的错误文本）、提示词和对话 ID 永远不会到达端点。
- **设置同意 (`F32.telemetry-consent-settings`)。**清除环境的同意，然后像Agent Canvas一样用`PATCH /api/settings`切换它。 重新授予会话是对被拒绝会话的积极控制：接收器的队列是先进先出的。
  ```sh
  control-agent-server restart --env OH_TELEMETRY_CONSENT=
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"telemetry": {"consent": "granted"}}}' --expect 200 --check misc_settings.telemetry.consent eq granted --save F32.telemetry-consent-settings/grant
  control-agent-server api GET /api/settings --check misc_settings.telemetry.consent eq granted
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_GRANT --body-json '{"user_id": "qa-f32-granted"}' --no-autotitle
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-granted"' --expect-min 1 --wait 15
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"telemetry": {"consent": "denied"}}}' --expect 200 --check misc_settings.telemetry.consent eq denied
  control-agent-server logs --grep 'Telemetry disabled \(settings\)' --expect-min 1
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_DENY --body-json '{"user_id": "qa-f32-denied"}' --no-autotitle
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"telemetry": {"consent": "granted"}}}' --expect 200
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_REGRANT --body-json '{"user_id": "qa-f32-regranted"}' --no-autotitle
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-regranted"' --expect-min 1 --wait 15
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-denied"' --expect-max 0 --save F32.telemetry-consent-settings/denied
  control-agent-server restart
  control-agent-server logs --grep 'enabled=True \(settings\)' --expect-min 1
  control-agent-server sink read --name qa-f32-telemetry --contains agent_server.server_started --expect-min 3 --expect-max 3 --wait 15
  ```
  授予在重启后对下一个对话生效，拒绝立即停止交付（虽然后来的对话到达了，但拒绝的对话并未到达），重启后对已持久化  `granted` `enabled=True (settings)`) and a third `server_started`. 运行时获得的授权不会发出 `server_started` 运行中的进程。
- **环境覆盖节拍设置 (`F32.telemetry-env-override`)。**设置仍然显示`granted`。
  ```sh
  control-agent-server restart --env OH_TELEMETRY_CONSENT=denied --env OH_TELEMETRY_CONSENT_MODE=override
  control-agent-server logs --grep 'enabled=False \(env_override\)' --expect-min 1
  control-agent-server api GET /api/settings --check misc_settings.telemetry.consent eq granted
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_OVERRIDE --body-json '{"user_id": "qa-f32-override"}' --no-autotitle
  control-agent-server restart --env OH_TELEMETRY_CONSENT_MODE=seed
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_SEED --body-json '{"user_id": "qa-f32-seed"}' --no-autotitle
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-seed"' --expect-min 1 --wait 15
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-override"' --expect-max 0 --save F32.telemetry-env-override/nothing
  ```
  `override`和`denied`在服务器整个生命周期（包括关闭时的刷新）中击败了`granted`。 作为 `seed` 的，相同的值丢失了，接下来的对话被传递了。
- **终止开关 (`F32.telemetry-kill-switch`).** `DO_NOT_TRACK` 针对授予的环境覆盖。
  ```sh
  control-agent-server restart --env DO_NOT_TRACK=1 --env OH_TELEMETRY_CONSENT=granted --env OH_TELEMETRY_CONSENT_MODE=override
  control-agent-server logs --grep 'enabled=False \(kill_switch\)' --expect-min 1
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_DNT --body-json '{"user_id": "qa-f32-dnt"}' --no-autotitle
  control-agent-server restart --env DO_NOT_TRACK=
  control-agent-server logs --grep 'enabled=True \(env_override\)' --expect-min 1
  control-agent-server conversation start --placeholder-agent --no-run --prompt QA_F32_AFTER_DNT --body-json '{"user_id": "qa-f32-after-dnt"}' --no-autotitle
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-after-dnt"' --expect-min 1 --wait 15
  control-agent-server sink read --name qa-f32-telemetry --contains '"distinct_id": "qa-f32-dnt"' --expect-max 0 --save F32.telemetry-kill-switch/nothing
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"telemetry": {"consent": null}}}' --expect 200 --check misc_settings.telemetry.consent missing
  ```
  `DO_NOT_TRACK=1` 战胜了 `granted` + `override` (`kill_switch`)； 随着它清空，相同的覆盖传递了下一个对话。 最后一次调用会再次删除存储的同意。
- ** `F32.telemetry-salt-and-kind`（伪名密钥和部署类型）** `F32.telemetry-conversation-failed`（不可达模型：一次运行就出错，没有模型调用）在三个服务器生命周期内被重新运行。 每次运行都会发出 `conversation_error` 及其 `conversation_ref`。 这些引用在这里重新计算，就像服务器文档中所述的那样，`blake2s` 个字节的会话 ID，16 字节的散列，根据盐或 32 字节的密钥
  `blake2s` 超过 32 字节的密钥）。 读取运行的机密键
  from its private file inside the one-liner and never printed.

  需要：`F32.telemetry-conversation-failed`
  ```sh
  FREF=$(python3 -c 'import hashlib, os, sys, uuid; k = open(os.environ["AGENT_SERVER_VERIFY_RUN"] + "/private/secret_key").read().strip().encode(); k = k if len(k) <= 32 else hashlib.blake2s(k, digest_size=32).digest(); print(hashlib.blake2s(uuid.UUID(sys.argv[1]).bytes, key=k, digest_size=16).hexdigest())' "$FAILID")
  SREF=$(python3 -c 'import hashlib, sys, uuid; print(hashlib.blake2s(uuid.UUID(sys.argv[1]).bytes, key=b"qa-f32-salt", digest_size=16).hexdigest())' "$FAILID")
  test "${#FREF}" -eq 32
  test "$FREF" != "$SREF"
  control-agent-server sink read --name qa-f32-telemetry --contains "\"conversation_ref\": \"$FREF\", \"terminal_status\": \"error\"" --expect-min 1 --expect-max 1
  control-agent-server api POST "/api/conversations/$FAILID/run" --expect 200 --quiet
  control-agent-server sink read --name qa-f32-telemetry --contains "\"deployment_kind\": \"local\", \"source\": \"openhands-agent-server\", \"conversation_ref\": \"$FREF\", \"error_class\"" --expect-min 2 --expect-max 2 --wait 30 --save F32.telemetry-salt-and-kind/secret-key-ref
  control-agent-server restart --env OH_TELEMETRY_SALT=qa-f32-salt --env OH_TELEMETRY_DEPLOYMENT_KIND=remote
  NL=$(control-agent-server sink read --name qa-f32-telemetry --contains '"deployment_kind": "local"' | python3 -c 'import json, sys; print(json.load(sys.stdin)["requests"])')
  test "$NL" -ge 1
  control-agent-server sink read --name qa-f32-telemetry --contains '"deployment_kind": "remote", "source": "openhands-agent-server"}}' --expect-min 1 --expect-max 1 --wait 15 --save F32.telemetry-salt-and-kind/started-remote
  control-agent-server api POST "/api/conversations/$FAILID/run" --expect 200 --quiet
  control-agent-server sink read --name qa-f32-telemetry --contains "\"deployment_kind\": \"remote\", \"source\": \"openhands-agent-server\", \"conversation_ref\": \"$SREF\", \"error_class\"" --expect-min 1 --expect-max 1 --wait 30 --save F32.telemetry-salt-and-kind/salted-ref
  control-agent-server restart
  control-agent-server api POST "/api/conversations/$FAILID/run" --expect 200 --quiet
  control-agent-server sink read --name qa-f32-telemetry --contains "\"deployment_kind\": \"remote\", \"source\": \"openhands-agent-server\", \"conversation_ref\": \"$SREF\", \"error_class\"" --expect-min 2 --expect-max 2 --wait 30 --save F32.telemetry-salt-and-kind/salted-ref-after-restart
  control-agent-server sink read --name qa-f32-telemetry --contains '"deployment_kind": "remote", "source": "openhands-agent-server"}}' --expect-min 3 --expect-max 3 --wait 15
  control-agent-server sink read --name qa-f32-telemetry --contains '"deployment_kind": "local"' --expect-max "$NL"
  control-agent-server sink read --name qa-f32-telemetry --contains "\"conversation_ref\": \"$FREF\", \"error_class\"" --expect-max 2
  ```
  没有盐，上一次运行的 ref 被键值为的 run 关键 `OH_SECRET_KEY`, 以及稍后重启运行报告了相同的 ref，带有标签 `deployment_kind`  `local`. 与 `OH_TELEMETRY_SALT` 同一个对话在重启后也会使用盐生成 ref。 的机密-key ref不再出现。 从加盐重启开始，每个事件都是 `remote` (both `server_started` 事件和
  `server_stopped`他们之间，以及对话错误）并没有新的
  `local` 一个到达。 变量在运行的 REST 中保持设置。
- **盐描述 (`F32.telemetry-salt-docs`).**的
  `TelemetrySpec` 模式（`POST /api/init` 的 `telemetry` 的类型）描述了回退方案的前一个项目证明：没有盐，服务器使用其机密密钥来密钥假名​​。
  ```sh
  control-agent-server api GET /openapi.json --auth none --quiet --check 'components.schemas.InitRequest.properties.telemetry.anyOf.0.$ref' eq '#/components/schemas/TelemetrySpec' --check components.schemas.TelemetrySpec.properties.salt.description exists
  control-agent-server api GET /openapi.json --auth none --quiet --check components.schemas.TelemetrySpec.properties.salt.description matches '(?i)secret'
  ```
  描述指出了机密-key 回退方案 (`OH_SECRET_KEY`默认为第一个会话 API key) 说，然后 ref 会跨重启链接起来； 仅在没有其他选择时，才使用单个进程的随机密钥机密 key either. 如果代码有任何改变，都必须是随机的回退方案，the 机密-key ref 检查
  `F32.telemetry-salt-and-kind` 失败，两个项目符号都需要更新。
- **延迟 Pod 从 `/api/init` (`F32.deferred-init`) 获取遥测数据和 Webhook。**第二台休眠服务器在已配置遥测的情况下启动（以
  `/boot` 在本次运行的接收器上）并在其初始化主体中接收不同的端点 (`/init`) 和 Webhook。
  ```sh
  DTS=$(control-agent-server fixture http-sink --name qa-f32-deferred --print-path)
  DEFERRED=$(control-agent-server launch --new --deferred-init --name f32-deferred --env OH_TELEMETRY_EXPORTER=http --env "OH_TELEMETRY_HTTP_ENDPOINT=$DTS/boot" --env OH_TELEMETRY_CONSENT=granted --env OH_TELEMETRY_FLUSH_DELAY=1 --print-run)
  trap 'control-agent-server stop --run "$DEFERRED" >/dev/null' EXIT
  control-agent-server api GET /api/init --run "$DEFERRED" --auth none --check state eq dormant
  control-agent-server api POST /api/init --run "$DEFERRED" --auth init --json "{\"telemetry\": {\"exporter\": \"http\", \"http_endpoint\": \"$DTS/init\", \"flush_delay\": 1}, \"webhooks\": [{\"base_url\": \"$WH/qa-f32-dinit\", \"flush_delay\": 1}]}" --expect 200 --check state eq ready --save F32.deferred-init/init
  control-agent-server sink read --name qa-f32-deferred --path /init --contains agent_server.server_started --expect-min 1 --expect-max 1 --wait 15 --save F32.deferred-init/started
  control-agent-server sink read --name qa-f32-deferred --path /boot --expect-max 0
  XCID=$(control-agent-server conversation start --run "$DEFERRED" --placeholder-agent --no-run --prompt QA_F32_DEFERRED --body-json '{"user_id": "qa-f32-deferred"}' --no-autotitle --print-id)
  control-agent-server sink read --path "/qa-f32-dinit/events/${XCID//-/}" --contains QA_F32_DEFERRED --expect-min 1 --wait 15 --save F32.deferred-init/webhook
  control-agent-server sink read --path /qa-f32-dinit/conversations --contains "\"id\": \"$XCID\"" --expect-min 1
  control-agent-server sink read --name qa-f32-deferred --path /init --contains '"distinct_id": "qa-f32-deferred"' --expect-min 1 --wait 15
  control-agent-server stop --run "$DEFERRED"
  ```
  休眠的 pod 没有向其启动端发送任何信息端点 （甚至在初始化时，当启动泵被排空并替换后） 之后 `POST /api/init` 它发送了恰好一个 `server_started` 并将其会话 telemetry 交付给接收方端点以及对话事件和信息的交付 Webhook. 第二台服务器已停止（） `trap` 此外，如果命令失败，也会停止它。
- **延迟 Pod 被标记为这样的 (`F32.deferred-init-flag`)，已知错误。**上面发送的初始化 pod 的事件应该表明它已延迟启动。
  ```sh
  control-agent-server sink read --name qa-f32-deferred --path /init --contains agent_server.server_started --expect-min 1
  control-agent-server sink read --name qa-f32-deferred --path /init --contains '"deferred_init": ' --expect-min 1
  control-agent-server sink read --name qa-f32-deferred --path /init --contains '"deferred_init": true' --expect-min 1 --save F32.deferred-init-flag/events  # bug：请求 eq 0
  ```
  预期：运行时属性中的 `deferred_init: true`。 实际：`false`
  在每个事件上，因为 `/api/init` 从合并的配置构建遥测接收器，这会清除 `deferred_init`。 请参阅陷阱。

<a id="gotchas"></a>

## 陷阱

- **字段描述 (`F32.webhook-spec-docs`).**事件批次转到
  `{base_url}/events/{conversation_id.hex}` 和会话信息发送到 `{base_url}/conversations`，并且刷新计时器从第一个排队事件开始：`_start_flush_timer` 只在 None 运行时启动计时器（`test_flush_delay_not_reset_on_new_event` 确保）。 的
  `WebhookSpec`字段描述与OpenAPI文档中的说法相同；
  `F32.events-post`和`F32.flush-delay`证明了代码。 TypeScript 客户端生成的模式遵循其固定版本，因此它会保留旧文本，直到下一个智能体服务器碰撞。
- 服务器将其自己的第一个会话密钥转发给每个 Webhook，如下所示
  `X-Session-API-Key`（事件批次和对话帖子类似），因此接收者可以回拨服务器。 点Webhook仅针对受信任的接收者。 `sink read` 输出并保存证据并对其进行编辑； 原始录音 `<run>/fixtures/<sink>.jsonl` 保留它（`stop --purge-private` 删除测试夹具）。
- `model_dump(mode="json")` 体是事件，null 字段包括在内，还包括每附着时的临时 `full_state` 拍照：创建时，每运行结束时，以及每次加载闲置或重启的对话时（事件搜索加载它；] `GET /api/conversations/{id}` 答案来自目录，但没有）。 快照包括智能体的配置，其中机密被屏蔽 (`**********`)。 接收方应按事件 ID 进行重复数据删除，并且不得依赖交付订单：在记录的每个批次中
  while mapping this family, a `last_user_message_id` update was posted
  在它命名的 `MessageEvent` 之前，尽管事件存储（和
  `timestamp`) 首先有消息。
- **飞行中的事件POST (`F32.buffer-stranded`)。**当缓冲区填满时，在`_post_lock`被保留的同时，批次被内联过帐； 在此期间发布的事件 POST 仅启动刷新计时器并返回。
  `_post_events` 在开始时队列的内容耗尽后，重新检查缓冲区，并在缓冲区再次满时继续发送，因此这些事件会在正在传输的 POST 之后发送，而不是在 `flush_delay` 之后发送。 计时器仍然覆盖未满的缓冲区，并在队列耗尽时被取消。 失败的 POST 会再次为重新排队的事件准备计时器，因为在其期间触发的计时器发现空队列并退出。 它显示在每次对话的第一条消息上：
  `SystemPromptEvent` 填充缓冲区 2，并且消息及其 `last_user_message_id` 更新在此 POST 期间发布。
- **接收器速度慢 (`F32.slow-receiver`)。**在缓冲区已满的情况下，POST 在该事件的扇出内运行，因此其发布未来仍处于待定状态
  while the receiver is slow (httpx timeout 30 s per attempt, plus
  `num_retries` × `retry_delay`). 跑步的 `finally` 等待最多 30 秒进行未完成的发布`wait_for_pending(30.0)` 在 `event_service.py`在清除任务之前 `POST .../run` 答案为 409 `Conversation already running` 那段时间 `GET` 已经报告了 `finished`. 使用的消息是 `run: true` 在那个窗口重新启动。 中低
  严重性：链式运行的自动化会看到虚假的 409。 与
  `event_buffer_size` 1 缓慢的接收器也会消耗连接时间
  快照：其内联 POST 在 0.5 秒初始推送超时内运行
  (`INITIAL_STATE_PUSH_TIMEOUT_SECONDS`), 被取消（日志显示
  `Initial state push ... timed out after 0.5s`）并且不会重试。
- 对话帖子是即发即忘的任务（无序、从不等待、没有保留参考），因此食谱会对它们进行轮询。 它们在创建（仅限新 ID）、暂停、中断、`PATCH` 和 `DELETE`（状态强制为 `deleting`）时发送； 运行的完成情况不会发布在那里，仅作为
  `execution_status` 事件。 创建帖子报告 `POST /api/conversations` 返回时的状态（`idle` 即使
  `initial_message`开始跑步）。
- 限制：`max_batch_bytes` 是一个触发器，也是一个上限。 大小达到已序列化的队列会立即发布，就像一个完整的缓冲区一样，因此 `max_batch_bytes` 1 在到达时发布每个事件（受上面的搁浅影响）。 `max_queue_size`和`max_queue_bytes`首先删除最旧的事件，新事件包括：大于的事件
  `max_queue_bytes` 一旦进入队列就会被丢弃并且永远不会被传递。 该警告每 Webhook 次对话记录一次，然后每 100 次记录一次。 映射时测量的大小，紧凑 JSON：占位符对话的 `full_state` 大约 3 KB，其
  `SystemPromptEvent` 约 18 KB，短 `MessageEvent` 约 0.5 KB，短
  `last_user_message_id` 更新约 0.3 KB。
- 重试：`num_retries + 1` 次尝试，间隔 `retry_delay` 秒。 一个失败的事件批次会被重新排队（如果超过`max_queue_size`或`max_queue_bytes`个最旧的事件，会警告地丢弃），并且在每轮定时器刷新时重新发送，永远持续，直到对话结束。 失败的对话帖子将被记录并删除。 遥测则执行相反的操作并丢弃失败的批次。 交付至少一次（如果接收者读取后 POST 失败，则重新发送批次），并且删除或关闭时的刷新是一个单周期操作：如果失败，队列中的事件就消失了。
- `OH_WEBHOOKS_0_*` 变量将字段逐个合并到文件中
  `webhooks[0]`; `restart --env` 保留它们以供以后重新启动，直到
  `--reset-config`，这也会删除启动的 `--webhook-sink` 条目。
- 遥测与 LLM 完成日志和层流/OTel 跟踪是分开的。 默认值：导出器 `none`、`event_buffer_size` 20、`flush_delay` 30 秒（配方设置 `OH_TELEMETRY_FLUSH_DELAY=1`）。 同意优先：
  `DO_NOT_TRACK` → `OH_TELEMETRY_CONSENT` 与模式 `override` →
  `misc_settings.telemetry.consent` → 遗产
  `misc_settings.app_preferences.user_consents_to_analytics` →
  `OH_TELEMETRY_CONSENT` 作为种子 → 取消设置（关闭）。 日志行“遥测”
  初始化：导出器=... enabled=... (<reason>)` 被日志包裹
  格式化程序，因此 grep `enabled=... (<reason>)` 部分。
- **笔名密钥（`F32.telemetry-salt-and-kind`、`F32.telemetry-salt-docs`）。**
  `conversation_ref` 是 `blake2s(conversation_id.bytes, key, digest_size=16)`，其中键是 `telemetry.salt` (`OH_TELEMETRY_SALT`)，否则
  `OH_SECRET_KEY`（超过 32 字节的密钥首先用 32 字节减少
  `blake2s`)，否则为每个进程的随机值。 具有会话密钥但没有显式机密密钥的服务器使用第一个会话密钥作为其机密密钥，因此随机回退方案只会在两者都没有的情况下发生。 因此，参考在重新启动后保持稳定，并随着 `restart --rotate-secret-key` 的变化而变化。 的
  `salt`描述（也在OpenAPI模式中）这么说； 设置盐来重新设置它们的密钥。
- 一个会话报告给每个订阅者一个终端结果：在重启后，如果存储状态已经是终端状态的会话被重新启动，那么会报告该结果，因此重新运行它会发出`conversation_error`事件，但不会发出第二个`conversation_failed`或`conversation_finished`事件。
- `server_started` 每个进程在启动时（或成功 `/api/init` 之后）发出一次，并且仅在启用遥测时发出； 稍后授予的同意不会发出它，并且 `server_stopped` 仅在发出开始之后。 匿名 `distinct_id` (`anon:<hex>`) 是针对每个进程的； 请求的 `user_id` 逐字传递。
- ** 使用桶 (`F32.telemetry-usage-buckets`).** 订阅者在看到第一个终端状态时发出结果，这在实时运行中是裸字符串 `execution_status` 更新，发布在最终更新之前
  `full_state` 快照。 因此，用法来自 `stats` 更新
  `EventService` 在每个发布后 LLM call (and from any `full_state` snapshot); 结果与最新总数相匹配。
- **`deferred_init`标签(`F32.deferred-init-flag`)。**
  `_build_initialized_config` 设置了 `deferred_init=False` 和 `/api/init`，它们从合并配置中构建了该端点，包括运行时属性（其 `server_started` 被隐藏，其 `/api/*` 路由返回 503）。 因此，延迟 Pod 发送的每个事件的属性都是 `false`； README 将其列在运行时属性中，但没有定义它，因此“延迟启动”是该项目符号假定的读数。 严重性低（分析质量）。
- `request_failed` 仅针对未处理的异常发出； 不会报告引发 `HTTPException(500)` 的路由（例如不可读文件上的工作区注册表）。 `F32.telemetry-request-failed`借用了condense路线的未处理的`ValueError`，这本身就是condense家族的一个已知bug。
- 此处未驱动：`posthog` 导出器（需要 `[posthog]` 额外项和项目密钥； 如果没有它们，它会降级为带有日志行的无操作）。
- `launch`将环回主机添加到`NO_PROXY`； httpx 遵循 `HTTP(S)_PROXY`，因此以其他方式启动的服务器可能永远不会到达环回接收器。
- `sink read --contains` 与 JSON 整个记录请求（方法、路径、头部、正文）的文本匹配，使用 `", "` 和 `": "` 分隔符，因此两字段匹配依赖于键顺序 (`"key": "execution_status", "value": "finished"`)。 这个系列中的确切计数假设新一轮比赛按顺序重播； 同一接收器路径上的较早交付会改变它们。 `--wait`只等待`--expect-min`。
