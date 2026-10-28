<a id="conversation-events-and-the-events-websocket"></a>

# 对话事件和事件WebSocket

每条对话都会记录一个追加事件日志：系统提示词，每个用户和智能体消息，每个工具操作和观测结果，以及一个状态更新（`execution_status`、`stats`、`last_user_message_id`）
...). Consumers append a user message with `POST .../events` (and optionally
启动智能体），通过搜索（过滤器、光标分页、排序）、计数、获取一和批量获取来读取历史记录，并实时跟踪对话
`/sockets/events/{conversation_id}`：第一帧验证，瞬态
`full_state` 快照，可选历史记录重播（`resend_mode=all` 或
`since`)，然后每个新事件作为原始JSON； 附加在套接字上发送的消息帧并运行智能体。

资料来源：`openhands-agent-server/openhands/agent_server/event_router.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/sockets.py`、`openhands-agent-server/openhands/agent_server/pub_sub.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-sdk/openhands/sdk/conversation/request.py`、`openhands-sdk/openhands/sdk/conversation/event_store.py`、`openhands-sdk/openhands/sdk/event/`

需求：`llm`

发射：`--env TZ=UTC`

路线：`GET /api/conversations/{conversation_id}/events/search`，
`GET /api/conversations/{conversation_id}/events/count`,
`GET /api/conversations/{conversation_id}/events/{event_id}`,
`GET /api/conversations/{conversation_id}/events`,
`POST /api/conversations/{conversation_id}/events`,
`WS /sockets/events/{conversation_id}`

<a id="sub-features"></a>

## 子功能

- `F06.send-no-run`：`POST .../events` 和 `run: false` 保留用户 `MessageEvent`（前面是第一条消息中的 `SystemPromptEvent`），返回 `{"success": true}` 并离开对话 `idle`。
- `F06.search-page`：搜索按日志顺序返回`{items, next_page_id}`； `limit` 加上包含的 `page_id` 光标翻页，`TIMESTAMP_DESC` 反转它，未知的 `page_id` 从第一个事件重新开始。
- `F06.search-validation`：搜索拒绝 `limit` 0 或 101、未知的 `sort_order` 以及无法解析的时间戳 422。
- `F06.search-filters`：`source`、`body`（不区分大小写，仅消息文本）和完全限定的 `kind` 过滤缩小搜索结果并合并。
- `F06.search-kind-short`：`kind=MessageEvent`，API文档和TypeScript客户端使用的短名称，通过线路过滤`kind`。
- `F06.search-time-window`：`timestamp__gte` 包含在内，`timestamp__lt` 不包含，带有 UTC 偏移量的值将转换为服务器时间。
- `F06.count`：count 返回一个裸整数，等于相同过滤器的搜索结果数。
- `F06.get-one`: `GET .../events/{event_id}` 返回搜索在该 id 下列出的事件，并且相同的事件在磁盘上。
- `F06.unknown-event`：未知事件 ID 从 get-one 返回 404，并从 batch-get 在其槽中返回 `null`。
- `F06.batch-get`: `GET .../events` 以 JSON id 数组作为主体，按请求顺序返回这些事件； 没有身体是 422。
- `F06.not-found-auth`：每个事件路由对于未知会话返回 404，对于格式错误的会话 ID 返回 422，对于没有有效会话密钥的情况返回 401。
- `F06.send-validation`：缺少正文、角色未知、字符串内容或未知内容类型的消息将被拒绝，返回 422，并且不会附加任何内容。
- `F06.send-image`包含文本部分和附件的[消息] `image` 部分 (a) `data:`  URL) is 已持久化与之 `image_urls` 完整且返回了相同的结果，通过搜索、获取单个和套接字重放。 一个 `image` 部分 `image_urls` 返回状态码 422 并无任何附加信息。
- `F06.send-non-user-role`：一个具有模式有效且非用户角色(`assistant`)的消息被拒绝为客户端错误（4xx），而不是500，并且不会留下任何事件（甚至空日志系统的提示词）。
- `F06.send-run`：`POST .../events`与`run: true`驱动真正的智能体转向`finished`，保持正常运行的类型（用户消息，`execution_status`运行并完成，`ActionEvent`/`ObservationEvent`对，`stats`）。
- `F06.ws-live`：在运行接收每个持久化事件之前，一个套接字被打开，持久化帧ID与已持久化日志匹配，随后跟随一个临时关闭的`full_state`快照。
- `F06.ws-streaming-deltas`：流式传输的真实模型回复实时发出瞬态 `StreamingDeltaEvent` 帧； REST 历史记录和套接字重放省略它们。
- `F06.search-timestamp-order`：使用工具运行后，`sort_order=TIMESTAMP` 按时间戳顺序列出事件，因此对列出的事件进行 `timestamp__gte` 或 `resend_mode=since` 剪切会保留其后列出的每个事件。
- `F06.send-resets-finished`：附加到 `finished` 对话的消息将其设置回 `idle`，并进行已持久化 `execution_status` 更新。
- `F06.ws-snapshot`：身份验证之后的第一帧是瞬态`full_state``ConversationStateUpdateEvent`，永远不会出现在搜索中； 如果没有`resend_mode`，则不会重播任何其他内容。
- `F06.ws-handshake`：套接字接受第一帧、已弃用查询和已弃用标头键； 错误的第一帧键，不是认证帧的第一帧，或者在10秒内没有认证帧，以4001码关闭；错误的已弃用查询或头键拒绝升级(HTTP 403码)；未知对话以4004码关闭。
- `F06.ws-delete-close`：删除会话将关闭其后面的套接字。
- `F06.ws-replay-all`: `resend_mode=all`（和已弃用 `resend_all=true`）在快照之后按搜索顺序重播已持久化日志。
- `F06.ws-replay-since`: `resend_mode=since` 和 `after_timestamp` 精确重播该时间戳或之后的事件； 如果没有 `after_timestamp`，它不会重播任何内容。
- `F06.ws-bad-frame`：无效的入站帧返回 `ServerErrorEvent`（`ValidationError`、`AssertionError`、`JSONDecodeError` 表示非 JSON 的文本），不附加任何内容并使套接字保持打开状态； 冗余的身份验证帧将被忽略。
- `F06.ws-send`：在套接字上发送的用户消息帧与已持久化和智能体运行，`finished`、流式传输在同一个套接字上运行。
- `F06.restart-persist`：事件 ID、顺序和计数在服务器重新启动后仍然存在，套接字重播相同的日志，并在其后附加新消息。
- `F06.send-run-limit`：对于每个运行槽，`POST .../events`和`run: true`返回429 `Message saved...`并且消息是已持久化； 套接字发送得到 `ConversationRunLimitExceeded` `ServerErrorEvent`。
- `F06.send-while-running`：对已在运行的对话使用 `run: true` 调用 `POST .../events`，会返回 200，而不是 `POST /run` 的 409；消息会持久化，对话保持 `running` 状态，且不会启动第二次运行。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `POST /api/conversations/{conversation_id}/events` 带有
  `SendMessageRequest`主体`{"role": "user", "content": [{"type": "text", "text": "..."}], "run": false}`返回`{"success": true}`； `run` 默认为 `false`，内容项是 `{"type": "text", "text": ...}` 或 `{"type": "image", "image_urls": [...]}`（HTTP 或 `data:` URLs)。 Python SDK `RemoteConversation.send_message()` 和 TypeScript `RemoteConversation.sendMessage()` 会发送 `run: false`，然后分别调用 `POST /run`。 `ConversationClient.sendEvent()` 将正文以给定的方式发布。 `api POST` 菜谱直接驱动了路线，因此，body和status就是客户端发送和看到的。 CLI的
  `conversation send` 为其他家庭包裹相同的路线。
- REST:`GET .../events/search`(查询`page_id`,`limit`1到100,
  `kind`, `source`, `body`, `sort_order` `TIMESTAMP|TIMESTAMP_DESC`,
  `timestamp__gte`、`timestamp__lt`）和 `GET .../events/count`（相同的过滤器，没有分页）。 SDK 的 `RemoteEventsList` 将历史记录与搜索同步（`limit=100`，无过滤器）； 该TypeScript客户端有
  `ConversationClient.searchEvents()`、`getEventCount()` 和
  `RemoteEventsList.search()`/`count()`.`conversation events`中的CLI页通过搜索。
- REST: `GET .../events/{event_id}` (TypeScript `ConversationClient.getEvent()`,
  `RemoteEventsList.getEventById()`) 和 `GET .../events` 带有 JSON 数组体（批量获取； 没有 SDK 或 TypeScript 调用者，因为浏览器无法发送 GET
  body: TypeScript `getEvents()` 扇出到 get-1 并将 404 映射到
  `null`).
- WebSocket：`/sockets/events/{conversation_id}` 包含查询 `resend_mode`（`all` 或 `since`）、`after_timestamp`（ISO 8601，`since` 所需）以及已弃用 `resend_all=true` 和 `session_api_key`。 SDK 的
  `WebSocketCallbackClient`（`RemoteConversation`内）和TypeScript
  `ConversationEventStream` 使用第一帧进行验证
  `{"type": "auth", "session_api_key": "..."}` 并处理第一个
  `ConversationStateUpdateEvent` 为“准备就绪”； SDK 在 4001 和 4004 上停止重新连接，并在任何其他关闭后通过退避重新连接。 食谱使用
  `ws listen`（一个连接，可选`--send`帧）和`ws start`/
  `ws stop`（围绕 REST 操作的背景捕获）。
- 配置：`max_concurrent_runs` (`OH_MAX_CONCURRENT_RUNS`) 边界运行，因此 429 路径； 服务器的本地时区 (`TZ`) 是每个事件时间戳和朴素过滤器值的区域。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用该系列的 `Launch:` 标志（`--env TZ=UTC`，因此天真的事件时间戳为 UTC）启动的运行是实时的并已导出，并且 `doctor` 没问题。
- 设置`$DEEPSEEK_API_KEY`； 预设使 `deepseek-flash` 成为活动配置文件，其 `conversation start` 复制到每个对话中。
- `CID` 是一个没有自动标题和 `--tools none`（仅内置 `finish` 和 `think` 工具）的对话，创建时没有消息，因此其日志为空且完全确定，直到 `F06.ws-send` 项目符号在其上运行智能体。

  ```sh
  control-agent-server llm preset deepseek
  CID=$(control-agent-server conversation start --no-autotitle --tools none --print-id)
  QA_UNKNOWN=00000000-0000-4000-8000-0000000000f6
  ```

- **附加消息而不运行 (`F06.send-no-run`)。**日志开始为空； 第一条消息还创建系统提示词事件。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/search" --expect 200 \
    --check items len-eq 0 --check next_page_id missing
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"role":"user","content":[{"type":"text","text":"QA_F06_FIRST hello"}],"run":false}' \
    --expect 200 --check success eq true --save F06.send-no-run/post
  control-agent-server api GET "/api/conversations/$CID/events/search" --expect 200 \
    --check items len-eq 3 --check items.0.kind eq SystemPromptEvent --check items.0.source eq agent \
    --check items.1.kind eq MessageEvent --check items.1.source eq user \
    --check items.1.llm_message.content.0.text eq 'QA_F06_FIRST hello' \
    --check items.2.kind eq ConversationStateUpdateEvent --check items.2.key eq last_user_message_id \
    --save F06.send-no-run/search
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq idle
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"content":[{"type":"text","text":"QA_F06_SECOND again"}]}' --expect 200
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  日志记录如下 `SystemPromptEvent`, 用户 `MessageEvent` and a
  `last_user_message_id`状态更新； 第二条消息（角色和 `run` 保留默认值）添加 `MessageEvent` 和另一个更新，并且对话保持 `idle`。
- **分页和排序顺序 (`F06.search-page`)。**两页共五个事件。
  ```sh
  E0=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items.0.id)
  LAST=$(control-agent-server api GET "/api/conversations/$CID/events/search" --check items len-eq 5 --field items.4.id)
  P2=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=2 \
    --check items len-eq 2 --check items.0.id eq "$E0" --field next_page_id)
  P3=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=2 --query page_id="$P2" \
    --check items len-eq 2 --check items.0.id eq "$P2" --field next_page_id)
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=2 --query page_id="$P3" \
    --check items len-eq 1 --check items.0.id eq "$LAST" --check next_page_id missing --save F06.search-page/last-page
  control-agent-server api GET "/api/conversations/$CID/events/search" --query sort_order=TIMESTAMP_DESC --query limit=1 \
    --check items.0.id eq "$LAST" --check next_page_id exists --save F06.search-page/desc
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=2 --query page_id=qa-unknown-page \
    --expect 200 --check items.0.id eq "$E0"
  ASC_REVERSED=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items | jq -c '[.[].id] | reverse')
  DESC_IDS=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query sort_order=TIMESTAMP_DESC \
    --field items | jq -c '[.[].id]')
  test "$ASC_REVERSED" = "$DESC_IDS"
  ```
  `next_page_id` 指明了下一页的第一个事件（指针是包含在内）；`next_page_id` 第三页没有事件，且事件按降序排列与升序日志相反（从最新事件开始），且一个未知指针会自动从第一个事件重新开始。
- **错误的搜索参数 (`F06.search-validation`)。**
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=0 --expect 422 --check detail.0.loc contains limit
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=101 --expect 422 --save F06.search-validation/limit-101
  control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --expect 200
  control-agent-server api GET "/api/conversations/$CID/events/search" --query sort_order=qa-bogus --expect 422 --check detail.0.loc contains sort_order
  control-agent-server api GET "/api/conversations/$CID/events/search" --query timestamp__gte=not-a-date --expect 422 --check detail.0.loc contains timestamp__gte
  ```
  每个坏值都是一个422，`detail[0].loc` 名称参数。
- **过滤器 (`F06.search-filters`).**
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/search" \
    --query kind=openhands.sdk.event.llm_convertible.message.MessageEvent \
    --check items len-eq 2 --check items.0.kind eq MessageEvent --check items.1.kind eq MessageEvent --save F06.search-filters/kind-fqn
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user \
    --check items len-eq 2 --check items.0.source eq user --check items.1.source eq user
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=environment \
    --check items len-eq 2 --check items.0.kind eq ConversationStateUpdateEvent
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=qa-nonsense --expect 200 --check items len-eq 0
  control-agent-server api GET "/api/conversations/$CID/events/search" --query body=qa_f06_second \
    --check items len-eq 1 --check items.0.llm_message.content.0.text eq 'QA_F06_SECOND again' --save F06.search-filters/body
  control-agent-server api GET "/api/conversations/$CID/events/search" --query body=QA_F06 --query source=user \
    --query sort_order=TIMESTAMP_DESC --check items len-eq 2 --check items.0.llm_message.content.0.text eq 'QA_F06_SECOND again'
  ```
  `kind` 采用完全限定的类路径（或裸类名称，请参阅
  `F06.search-kind-short`) 是精确匹配（未知值为空）；`source` 是消息文本的不区分大小写的子串；`body` 过滤条件与排序顺序结合使用。
- **简短种类名称 (`F06.search-kind-short`)。**查询参数的文档和 TypeScript 客户端说
  `kind=MessageEvent`，每个事件在其 `kind` 字段中携带的值。 完全限定的过滤器首先显示两条消息以及它们的
  `kind` 字段正是该短名称。

  需要：`F06.send-no-run`
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/search" \
    --query kind=openhands.sdk.event.llm_convertible.message.MessageEvent \
    --check items len-eq 2 --check items.0.kind eq MessageEvent --check items.1.kind eq MessageEvent
  control-agent-server api GET "/api/conversations/$CID/events/search" --query kind=MessageEvent --expect 200 \
    --check items len-eq 2 --save F06.search-kind-short/short-name
  control-agent-server api GET "/api/conversations/$CID/events/count" --query kind=MessageEvent --check . eq 2
  ```
  搜索返回了两个消息，计数显示为 `2`：服务 (`event_service.py`, `_event_matches_filters`) 接受裸消息
  class name or the fully-qualified `<module>.<ClassName>`.
- **时间窗口(`F06.search-time-window`)。** `T1` 是第一条消息的时间戳，一个简单的服务器本地（此处为 UTC）ISO 字符串。
  ```sh
  T1=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items.1.timestamp)
  E1=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items.1.id)
  control-agent-server api GET "/api/conversations/$CID/events/search" --query timestamp__gte="$T1" \
    --check items len-eq 4 --check items.0.id eq "$E1" --save F06.search-time-window/gte
  control-agent-server api GET "/api/conversations/$CID/events/search" --query timestamp__lt="$T1" \
    --check items len-eq 1 --check items.0.kind eq SystemPromptEvent
  T1_PLUS2=$(python3 -c 'import datetime as d, sys; t = d.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=d.timezone.utc); print(t.astimezone(d.timezone(d.timedelta(hours=2))).isoformat())' "$T1")
  control-agent-server api GET "/api/conversations/$CID/events/search" --query timestamp__gte="$T1_PLUS2" \
    --check items len-eq 4 --check items.0.id eq "$E1" --save F06.search-time-window/gte-offset
  control-agent-server api GET "/api/conversations/$CID/events/count" --query timestamp__gte="$T1" --query timestamp__lt="$T1_PLUS2" --check . eq 0
  ```
  `>=` 保留第一个消息本身， `<` 仅保留系统提示词同句式写成 `+02:00` 选择相同事件，并且一个空窗口计数为0。
- **计数 (`F06.count`)。**与搜索相同的过滤器，一个裸 JSON 整数。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/count" --expect 200 --check . eq 5 --save F06.count/all
  control-agent-server api GET "/api/conversations/$CID/events/search" --check items len-eq 5
  control-agent-server api GET "/api/conversations/$CID/events/count" --query source=user --check . eq 2
  control-agent-server api GET "/api/conversations/$CID/events/count" \
    --query kind=openhands.sdk.event.conversation_state.ConversationStateUpdateEvent --check . eq 2
  control-agent-server api GET "/api/conversations/$CID/events/count" --query body=qa_f06_first --check . eq 1
  control-agent-server api GET "/api/conversations/$CID/events/count" --query timestamp__lt=not-a-date --expect 422
  ```
  每计数等于匹配的搜索长度。
- **获取一个事件 (`F06.get-one`)。**第二条消息按 id，然后磁盘上有相同的事件。

  需要：`F06.send-no-run`
  ```sh
  E2=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query body=QA_F06_SECOND --field items.0.id)
  control-agent-server api GET "/api/conversations/$CID/events/$E2" --expect 200 --check id eq "$E2" \
    --check kind eq MessageEvent --check source eq user --check llm_message.content.0.text eq 'QA_F06_SECOND again' \
    --save F06.get-one/get
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/events/event-00003-$E2.json" \
    --check id eq "$E2" --check kind eq MessageEvent
  ```
  身体匹配搜索项。 不像搜索那样，它已序列化不会丢弃 `null` 字段。 在磁盘上它是 `event-00003-<id>.json`：文件索引是事件在日志中的位置。
- **未知事件 ID (`F06.unknown-event`)。**路线文档404和批量获取文档“null对于任何缺失的项目”； TypeScript
  `getEventById` 依赖于 404。 两条路由首先找到已知的 id `E2`。

  需要：`F06.get-one`
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/$E2" --expect 200 --check id eq "$E2"
  control-agent-server api GET "/api/conversations/$CID/events" --json "[\"$E2\"]" --expect 200 \
    --check . len-eq 1 --check 0.id eq "$E2"
  control-agent-server api GET "/api/conversations/$CID/events/00000000-0000-4000-8000-0000000000e6" --expect 404 \
    --save F06.unknown-event/get-one
  control-agent-server api GET "/api/conversations/$CID/events" --json "[\"$E2\", \"qa-missing-event\"]" --expect 200 \
    --check . len-eq 2 --check 0.id eq "$E2" --check 1 missing --save F06.unknown-event/batch
  ```
  未知的 id 是 404，批次 `[<event>, null]`：缺少的 id 读作 `None` (`event_service.py` `_get_event_sync`)，因此批次 REST 无法失败。
- **批量获取(`F06.batch-get`).**带有 JSON 数组体的 GET。

  需要：`F06.search-time-window`、`F06.get-one`
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events" --json "[\"$E2\", \"$E1\"]" --expect 200 \
    --check . len-eq 2 --check 0.id eq "$E2" --check 1.id eq "$E1" --save F06.batch-get/two
  control-agent-server api GET "/api/conversations/$CID/events" --expect 422 --check detail.0.loc contains body
  ```
  事件按请求顺序返回，而不是按日志顺序。 没有身体，路由会返回 422 `body: Field required`。
- **未知对话、错误 ID、无密钥 (`F06.not-found-auth`)。**

  需要：`F06.get-one`
  ```sh
  control-agent-server api GET "/api/conversations/$QA_UNKNOWN/events/search" --expect 404 \
    --check detail contains 'Conversation not found' --save F06.not-found-auth/search-404
  control-agent-server api GET "/api/conversations/$QA_UNKNOWN/events/count" --expect 404
  control-agent-server api GET "/api/conversations/$QA_UNKNOWN/events/$E2" --expect 404
  control-agent-server api GET "/api/conversations/$QA_UNKNOWN/events" --json "[\"$E2\"]" --expect 404
  control-agent-server api POST "/api/conversations/$QA_UNKNOWN/events" --json '{"content":[{"type":"text","text":"QA_F06_X"}]}' --expect 404
  control-agent-server api GET /api/conversations/qa-not-a-uuid/events/search --expect 422 --check detail.0.loc contains conversation_id
  control-agent-server api POST /api/conversations/qa-not-a-uuid/events --json '{"content":[{"type":"text","text":"QA_F06_X"}]}' \
    --expect 422 --check detail.0.loc contains conversation_id
  control-agent-server api GET "/api/conversations/$CID/events/search" --auth none --expect 401 --save F06.not-found-auth/no-key
  control-agent-server api GET "/api/conversations/$CID/events/count" --auth bad --expect 401
  control-agent-server api GET "/api/conversations/$CID/events/$E2" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/events" --json "[\"$E2\"]" --auth bad --expect 401
  control-agent-server api POST "/api/conversations/$CID/events" --auth none \
    --json '{"content":[{"type":"text","text":"QA_F06_NOAUTH"}]}' --expect 401
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  404 `Conversation not found: <id>` 在所有五条路线中，422人未通过UUID 在读和写路由器上，401状态码，或者在所有五个中没有或错误的密钥，以及未认证的 POST 存储了 nothing。
- **Message 验证 (`F06.send-validation`).**
  ```sh
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"role":"qa-invalid","content":[{"type":"text","text":"QA_F06_BADROLE"}]}' --expect 422 \
    --check detail.0.loc contains role --save F06.send-validation/role
  control-agent-server api POST "/api/conversations/$CID/events" --json '{"content":"QA_F06_PLAIN"}' --expect 422 \
    --check detail.0.loc contains content
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"content":[{"type":"qa-unknown","text":"QA_F06_BADTYPE"}]}' --expect 422
  control-agent-server api POST "/api/conversations/$CID/events" --expect 422 --check detail.0.loc contains body
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  `content` 必须是文本或图像项的列表，且正文为必填项； 没有附加任何内容。
- **图像内容 (`F06.send-image`).** 一个像素的 PNG 作为 `data:` URL，单独的对话 `QA_IMG`（永远不会运行，因此不需要视觉模型，并且 `CID`'s 计数保持不变）。
  ```sh
  QA_IMG=$(control-agent-server conversation start --no-autotitle --tools none --print-id)
  QA_PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  control-agent-server api POST "/api/conversations/$QA_IMG/events" \
    --json "{\"content\":[{\"type\":\"text\",\"text\":\"QA_F06_IMAGE\"},{\"type\":\"image\",\"image_urls\":[\"$QA_PNG\"]}]}" \
    --expect 200 --check success eq true --save F06.send-image/post
  IMG_ID=$(control-agent-server api GET "/api/conversations/$QA_IMG/events/search" --query source=user \
    --check items len-eq 1 --check items.0.llm_message.content.0.text eq QA_F06_IMAGE \
    --check items.0.llm_message.content.1.type eq image --check items.0.llm_message.content.1.image_urls len-eq 1 \
    --check items.0.llm_message.content.1.image_urls.0 eq "$QA_PNG" --save F06.send-image/search --field items.0.id)
  control-agent-server api GET "/api/conversations/$QA_IMG/events/$IMG_ID" --expect 200 \
    --check llm_message.content.1.type eq image --check llm_message.content.1.image_urls.0 eq "$QA_PNG"
  IMG_WS=$(control-agent-server ws listen "/sockets/events/$QA_IMG" --query resend_mode=all --duration 3 \
    --save F06.send-image/replay | jq -r .saved)
  jq -e --arg id "$IMG_ID" --arg url "$QA_PNG" '[.frames[] | select(.direction == "received") | .frame | select(.id == $id) | .llm_message.content[1].image_urls] == [[$url]]' "$IMG_WS"
  control-agent-server api POST "/api/conversations/$QA_IMG/events" --json '{"content":[{"type":"image"}]}' --expect 422 \
    --check detail.2.loc contains ImageContent --check detail.2.loc contains image_urls --check detail.2.type eq missing \
    --save F06.send-image/no-urls
  control-agent-server api GET "/api/conversations/$QA_IMG/events/count" --query source=user --check . eq 1
  ```
  图像部分保留`type: image`和`data:`的精确URL，在搜索、获取-一和回放`MessageEvent`帧（不截断或遮罩基础64载荷）。 缺少`image_urls`，主体匹配的内容类型：422列出的`TextContent`错误首先，然后
  `ImageContent.image_urls: Field required`，并且没有存储第二条用户消息。
- **Non-user role (`F06.send-non-user-role`), known bug.** `role`接受
  模式中的`user`、`system`、`assistant`和`tool`，但对话仅接收用户消息。 `QA_ROLE` 是第二个对话，其日志仍为空（计数 0）； `CID`已经与`F06.send-no-run`中的角色`user`采用了相同的身体。
  ```sh
  QA_ROLE=$(control-agent-server conversation start --no-autotitle --tools none --print-id)
  control-agent-server api GET "/api/conversations/$QA_ROLE/events/count" --check . eq 0
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"role":"assistant","content":[{"type":"text","text":"QA_F06_ASSISTANT"}]}' --expect 4xx \
    --save F06.send-non-user-role/assistant  # bug：status eq 500 && response.body.exception 包含“仅允许用户消息”
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  control-agent-server api POST "/api/conversations/$QA_ROLE/events" \
    --json '{"role":"assistant","content":[{"type":"text","text":"QA_F06_ASSISTANT"}]}' --expect 4xx \
    --save F06.send-non-user-role/assistant-empty-log  # bug：status eq 500 && response.body.exception 包含“仅允许用户消息”
  control-agent-server api GET "/api/conversations/$QA_ROLE/events/count" --check . eq 0 \
    --save F06.send-non-user-role/empty-log-count  # 错误：状态 eq 200 && response.body eq 1
  ```
  正确行为：4xx 客户端错误，无附加内容。 今天是500
  `{"exception": "Only user messages are allowed to be sent to the agent."}`:
  `LocalConversation.send_message`断言`role == "user"`并且
  `AssertionError` 到达包罗万象的处理程序。 `CID` 无内容被追加，但断言会在智能体初始化后运行，因此在空日志的对话中拒绝的消息仍然写入了
  `SystemPromptEvent`（计数1，而不是0）； 当 500 持续时，重播会在第一个标记的 POST 处停止，因此仅更改状态的修复在最后一个标记的计数处仍然会失败。
- **第一帧是状态快照 (`F06.ws-snapshot`)。**
  ```sh
  control-agent-server ws listen "/sockets/events/$CID" --count 1 --until-kind ConversationStateUpdateEvent \
    --until key=full_state --until value.execution_status=idle --duration 10 --save F06.ws-snapshot/first-frame
  control-agent-server ws listen "/sockets/events/$CID" --duration 3 --save F06.ws-snapshot/no-replay \
    | jq -e '.frames == 1 and .kinds.ConversationStateUpdateEvent == 1'
  control-agent-server api GET "/api/conversations/$CID/events/search" --check items not-contains full_state
  ```
  第一个且唯一的帧为 `{"kind": "ConversationStateUpdateEvent", "key": "full_state", "value": {...whole state, execution_status idle...}}`，具有新的 id。 它不是已持久化，也没有`resend_mode`就没有历史回放。
- **握手：验证和关闭代码 (`F06.ws-handshake`).** 10 秒的第一帧超时是服务器自己的计时器，因此捕获会等待它。
  ```sh
  control-agent-server ws listen "/sockets/events/$CID" --auth bad --expect-close 4001 --duration 10 --save F06.ws-handshake/bad-key
  control-agent-server ws listen "/sockets/events/$CID" --auth none --send '{"type":"qa-hello","session_api_key":"qa"}' \
    --expect-close 4001 --duration 10 --save F06.ws-handshake/not-auth-frame
  T0=$SECONDS
  control-agent-server ws listen "/sockets/events/$CID" --auth none --expect-close 4001 --duration 15 --save F06.ws-handshake/no-frame
  test $((SECONDS - T0)) -ge 9
  test $((SECONDS - T0)) -le 14
  control-agent-server ws listen "/sockets/events/$CID" --auth query --until-kind ConversationStateUpdateEvent --until key=full_state --duration 10
  control-agent-server ws listen "/sockets/events/$CID" --auth header --until-kind ConversationStateUpdateEvent --until key=full_state --duration 10
  control-agent-server ws listen "/sockets/events/$CID" --auth bad-query --expect-reject 403 --duration 5 \
    --save F06.ws-handshake/bad-query-key
  control-agent-server ws listen "/sockets/events/$CID" --auth bad-header --expect-reject 403 --duration 5 \
    --save F06.ws-handshake/bad-header-key
  control-agent-server ws listen "/sockets/events/$QA_UNKNOWN" --expect-close 4004 --duration 10 --save F06.ws-handshake/unknown
  ```
  错误的第一帧键，另一个第一帧 `type`, 并且一切静默，4001结束 `Authentication failed`; 服务器的10秒计时器结束后，沉默关闭（捕获时间大约为10到11秒）。 的已弃用查询和头部键被接受（服务器会记录一个 ） 弃用警告），升级之前，错误的查询或头信息会被拒绝 HTTP 因此客户端看不到关闭代码。 在未知对话中使用有效的密钥认证后，会收到 4004 `Conversation not found`.
- ** 删除一个对话会关闭其套接字 (`F06.ws-delete-close`)，这是一个已知的 bug。** 背景捕获已订阅（其 `full_state` 拍照已到达并打开）之前 DELETE。 在判断开放捕获之前，DELETE、REST上的 404 和新套接字的 4004 都成功。
  ```sh
  QA_DEL=$(control-agent-server conversation start --no-autotitle --tools none --print-id)
  control-agent-server ws start "/sockets/events/$QA_DEL" --name f06-del --duration 60
  control-agent-server ws read f06-del --kinds ConversationStateUpdateEvent --contains '"key": "full_state"' \
    --expect-open --wait 10
  control-agent-server api DELETE "/api/conversations/$QA_DEL" --expect 200 --save F06.ws-delete-close/delete
  control-agent-server api GET "/api/conversations/$QA_DEL" --expect 404
  control-agent-server ws listen "/sockets/events/$QA_DEL" --expect-close 4004 --duration 5
  control-agent-server ws stop f06-del --save F06.ws-delete-close/socket | control-agent-server assert --check close.code exists  # bug: value.opened eq True && value.stopped eq 停止 && value.close 缺失
  ```
  正确行为：服务器关闭已打开的套接字（使用任何关闭代码）
  while it deletes the conversation; `EventService.close()` awaits
  `PubSub.close()` 在 DELETE 应答之前，因此在捕获停止时已结束。 今天，捕获仍然处于打开状态，没有关闭帧 (`close: null`)，尽管 REST 回答了 404 并且获得了新的套接字
  4004：`PubSub.close()`调用`Subscriber.close()`，其中
  `_WebSocketSubscriber` 未实现 (`pub_sub.py`, `sockets.py`)，因此 SDK 或 TypeScript 客户端会一直等待不再存在的会话。
- **重播所有内容 (`F06.ws-replay-all`)。**
  ```sh
  IDS=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items | jq -c '[.[].id]')
  ALL=$(control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=all --duration 3 \
    --save F06.ws-replay-all/all | jq -r .saved)
  jq -e --argjson ids "$IDS" '[.frames[] | select(.direction == "received") | .frame] | (.[0].key == "full_state") and ([.[1:][].id] == $ids)' "$ALL"
  LEGACY=$(control-agent-server ws listen "/sockets/events/$CID" --query resend_all=true --duration 3 \
    --save F06.ws-replay-all/resend-all-legacy | jq -r .saved)
  jq -e --argjson ids "$IDS" '[.frames[] | select(.direction == "received") | .frame] | [.[1:][].id] == $ids' "$LEGACY"
  ```
  在快照之后，回放的搜索ID顺序与快照中的顺序完全相同
  for both spellings.
- **自时间戳 (`F06.ws-replay-since`) 以来重播。** `T2` 是第二条消息的时间戳； 重播具有包容性。
  ```sh
  T2=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query body=QA_F06_SECOND --field items.0.timestamp)
  SINCE_IDS=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query timestamp__gte="$T2" \
    --check items len-eq 2 --field items | jq -c '[.[].id]')
  SINCE=$(control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=since --query after_timestamp="$T2" \
    --duration 3 --save F06.ws-replay-since/since | jq -r .saved)
  jq -e --argjson ids "$SINCE_IDS" '[.frames[] | select(.direction == "received") | .frame] | (.[0].key == "full_state") and ([.[1:][].id] == $ids)' "$SINCE"
  control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=since --duration 3 \
    --save F06.ws-replay-since/no-timestamp | jq -e '.frames == 1'
  ```
  回放是第二个消息及其状态更新，与搜索的 `timestamp__gte` 保持一致。 `since` 无 `after_timestamp` 重放，服务器只会记录警告。
- ** 网络套接字上出现了坏帧 (`F06.ws-bad-frame`).** 一个不是 JSON 的对象，不是 `Message` 的消息，重复的认证帧，然后是文本，不是 JSON 的（最后发送的，因此其回复证明了在读取并跳过之前就已存在的认证帧）。
  ```sh
  BAD=$(control-agent-server ws listen "/sockets/events/$CID" \
    --send '{"kind":"MessageEvent","text":"QA_F06_BAD"}' \
    --send '{"role":"assistant","content":[{"type":"text","text":"QA_F06_BAD"}]}' \
    --send '{"type":"auth","session_api_key":"qa-ignored"}' \
    --send 'qa-f06-not-json' \
    --duration 4 --expect-open --save F06.ws-bad-frame/frames | jq -r .saved)
  jq -e '[.frames[] | select(.direction == "received") | .frame | select(.kind == "ServerErrorEvent") | .code] == ["ValidationError", "AssertionError", "JSONDecodeError"]' "$BAD"
  control-agent-server api GET "/api/conversations/$CID/events/count" --query body=QA_F06_BAD --check . eq 0
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  三个 `ServerErrorEvent` 帧 (`code` `ValidationError`, 然后)
  `AssertionError` 与 `Only user messages are allowed...`，则
  `JSONDecodeError`), None 对于身份验证控制消息，套接字保持打开状态并且没有附加任何内容。
- **通过套接字发送消息 (`F06.ws-send`)。**每个套接字消息都运行智能体； 这会花费一小DeepSeek圈。
  ```sh
  WS_RUN=$(control-agent-server ws listen "/sockets/events/$CID" \
    --send '{"role":"user","content":[{"type":"text","text":"QA_F06_WS: reply with the single word ok"}]}' \
    --expect-kind MessageEvent \
    --until-kind ConversationStateUpdateEvent --until value=finished --duration 180 --save F06.ws-send/run | jq -r .saved)
  jq -e '[.frames[] | select(.direction == "received") | .frame] | (map(select(.kind == "MessageEvent" and .source == "user") | .llm_message.content[0].text) | any(startswith("QA_F06_WS"))) and (map(select(.key == "execution_status") | .value) | index("running") != null)' "$WS_RUN"
  jq -e '[.frames[] | select(.direction == "received") | .frame | select(.source == "agent" and (.kind == "MessageEvent" or .kind == "ActionEvent"))] | length >= 1' "$WS_RUN"
  WS_T=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F06_WS \
    --check items len-eq 1 --save F06.ws-send/persisted --field items.0.timestamp)
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished
  control-agent-server api GET "/api/conversations/$CID/events/count" --query source=agent --query timestamp__gte="$WS_T" \
    --check . ge 1
  ```
  同一个套接字流 `MessageEvent` 和 `execution_status`
  `running`，智能体的回合（至少一个智能体 `MessageEvent` 或
  `ActionEvent` 帧）和 `finished`； REST 显示已持久化消息以及其后的至少一个智能体事件（`MessageEvent` 回复或 `finish` `ActionEvent`：智能体两者都有，因此模型选择哪一个）。
- **跑一圈并观看直播 (`F06.send-run`, `F06.ws-live`)。**捕获在消息发送之前开始； 智能体只有文件编辑器（不需要 tmux）。
  ```sh
  LIVE=$(control-agent-server conversation start --no-autotitle --tools file_editor --print-id)
  control-agent-server ws start "/sockets/events/$LIVE" --name f06-live
  control-agent-server api POST "/api/conversations/$LIVE/events" \
    --json '{"content":[{"type":"text","text":"Create qa.txt containing exactly: QA_F06_LIVE"}],"run":true}' \
    --expect 200 --check success eq true --save F06.send-run/post
  control-agent-server conversation wait "$LIVE" --until finished --timeout 240
  control-agent-server ws stop f06-live --wait 30 \
    --kinds ConversationStateUpdateEvent --contains '"key": "full_state"' --expect-min 2 --save F06.ws-live/frames
  control-agent-server ws read f06-live --kinds ActionEvent --expect-min 1
  LIVE_IDS=$(control-agent-server api GET "/api/conversations/$LIVE/events/search" --field items | jq -c '[.[].id]')
  control-agent-server ws read f06-live --kinds MessageEvent --contains QA_F06_LIVE
  control-agent-server ws read f06-live --kinds ConversationStateUpdateEvent --contains '"value": "running"'
  control-agent-server ws read f06-live --kinds ObservationEvent --contains '"tool_name": "file_editor"'
  control-agent-server ws read f06-live --kinds ConversationStateUpdateEvent --contains '"value": "finished"'
  LIVE_FRAMES=$(control-agent-server ws read f06-live --save F06.ws-live/all-frames | jq -r .saved)
  jq -e --argjson ids "$LIVE_IDS" '[.frames[] | select(.direction == "received") | .frame | select(.key != "full_state" and .kind != "StreamingDeltaEvent") | .id] | (length > 0) and (. - $ids == [])' "$LIVE_FRAMES"
  control-agent-server conversation events "$LIVE" --kinds ObservationEvent --contains file_editor --save F06.send-run/observations
  control-agent-server api GET "/api/conversations/$LIVE/events/count" \
    --query kind=openhands.sdk.event.llm_convertible.action.ActionEvent --check . ge 1
  control-agent-server api GET "/api/conversations/$LIVE/events/count" \
    --query kind=openhands.sdk.event.llm_convertible.observation.ObservationEvent --check . ge 1
  control-agent-server conversation events "$LIVE" --key stats --expect-min 1
  LIVE_WS=$(control-agent-server api GET "/api/conversations/$LIVE" --field workspace.working_dir)
  grep -q QA_F06_LIVE "$LIVE_WS/qa.txt"
  ```
  POST 返回 200，`finished` 运行到达。 只有在第二个 `full_state` 快照到达后，捕获才会停止（运行任务在 REST 状态已经显示 `finished` 之后发布它，所以停止在等待之后会与它发生冲突）。 端口显示用户消息
  `execution_status` `running`、`ActionEvent` 及其 `file_editor`
  `ObservationEvent`s, `finished` 并且关闭快照； 每个持久帧 ID 都在已持久化在捕获停止后读取日志，因为事件已经发生已持久化在它发布之前，也具有 `stats` 更新，以及智能体 wrote `qa.txt`. 的 `full_state` snapshots and
  流式传输次运行的 `StreamingDeltaEvent` 帧是瞬态的。 典型的日志：
  `SystemPromptEvent`、`MessageEvent`（用户）、状态更新
  `last_user_message_id` 和 `execution_status=running`，然后每一步
  `ActionEvent`、`ObservationEvent` 和 `stats`，以 `finish` 操作和 `execution_status=finished` 结束。
- **日志顺序为时间戳顺序(`F06.search-timestamp-order`)。**搜索以追加顺序遍历日志，其文档字符串依赖于时间戳顺序 (`_search_events_sync`)； `after_timestamp` 记录为“REST 获取历史记录，套接字从该点继续”。 上一个项目符号中的 `LIVE` 至少有一个工具步骤，因此其第一个 `ObservationEvent` 之后有后续事件。

  需要：`F06.send-run`
  ```sh
  OBS_ID=$(control-agent-server api GET "/api/conversations/$LIVE/events/search" \
    --query kind=openhands.sdk.event.llm_convertible.observation.ObservationEvent --check items len-ge 1 --field items.0.id)
  OBS_T=$(control-agent-server api GET "/api/conversations/$LIVE/events/$OBS_ID" --check id eq "$OBS_ID" --field timestamp)
  FROM_OBS=$(control-agent-server api GET "/api/conversations/$LIVE/events/search" --field items \
    | jq -e --arg id "$OBS_ID" '[.[].id] | length - index($id)')
  test "$FROM_OBS" -ge 2
  COUNT_SINCE=$(control-agent-server api GET "/api/conversations/$LIVE/events/count" --query timestamp__gte="$OBS_T" \
    --save F06.search-timestamp-order/count-since-observation --field .)
  control-agent-server assert --value="$((COUNT_SINCE - FROM_OBS))" --check . ge 0
  SINCE=$(control-agent-server ws listen "/sockets/events/$LIVE" --query resend_mode=since --query after_timestamp="$OBS_T" \
    --duration 3 --save F06.search-timestamp-order/replay-since-observation | jq .frames)
  control-agent-server assert --value="$((SINCE - 1 - FROM_OBS))" --check . ge 0
  control-agent-server api GET "/api/conversations/$LIVE/events/search" --field items \
    | jq -c '[range(1; length) as $i | select(.[$i].timestamp < .[$i - 1].timestamp) | (.[$i].key // .[$i].kind)]' | control-agent-server assert --check . len-eq 0
  ```
  正确行为：在第一处剪切 `ObservationEvent` 保留它及其之后的所有内容`FROM_OBS` events), over REST 并且在套接字上，没有一个已列出的事件的戳记比它前面的戳记还要早。 的 `stats` 每次模型调用的更新是在模型回答时构建的，在步骤中，然后由一个等待状态的执行器添加锁 (`_setup_stats_streaming`, `_emit_event_from_thread` 在 `event_service.py`); 当附加时，它被盖章，因此在步骤的动作之后携带时间戳观测结果因此，加载历史的客户端如下 REST 并重新连接
  `resend_mode=since` 明白了。
- **一条消息重新打开已完成的对话 (`F06.send-resets-finished`)。**

  需要：`F06.send-run`
  ```sh
  control-agent-server api GET "/api/conversations/$LIVE" --check execution_status eq finished
  control-agent-server api POST "/api/conversations/$LIVE/events" \
    --json '{"content":[{"type":"text","text":"QA_F06_FOLLOWUP"}],"run":false}' --expect 200
  control-agent-server api GET "/api/conversations/$LIVE" --check execution_status eq idle --save F06.send-resets-finished/after
  control-agent-server api GET "/api/conversations/$LIVE/events/search" --query sort_order=TIMESTAMP_DESC --query limit=3 \
    --check items.2.key eq execution_status --check items.2.value eq idle \
    --check items.1.kind eq MessageEvent --check items.0.key eq last_user_message_id --save F06.send-resets-finished/tail
  ```
  状态是 `idle` 再次，日志以结束
  `execution_status=idle`，新消息及其`last_user_message_id`更新； 没有运行开始。
- **重启后历史仍然存在 (`F06.restart-persist`)。**
  ```sh
  BEFORE=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items | jq -c '[.[].id]')
  COUNT=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$COUNT" --save F06.restart-persist/count
  AFTER=$(control-agent-server api GET "/api/conversations/$CID/events/search" --field items | jq -c '[.[].id]')
  test "$BEFORE" = "$AFTER"
  REPLAY=$(control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=all --duration 3 \
    --save F06.restart-persist/replay | jq -r .saved)
  jq -e --argjson ids "$AFTER" '[.frames[] | select(.direction == "received") | .frame | select(.key != "full_state") | .id] == $ids' "$REPLAY"
  control-agent-server api POST "/api/conversations/$CID/events" \
    --json '{"content":[{"type":"text","text":"QA_F06_AFTER_RESTART"}]}' --expect 200
  control-agent-server api GET "/api/conversations/$CID/events/search" --query sort_order=TIMESTAMP_DESC --query limit=2 \
    --check items.1.llm_message.content.0.text eq QA_F06_AFTER_RESTART
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . gt "$COUNT"
  ```
  重启后第一次读取会重新激活对话。 id、订单和计数保持不变，socket重播相同的日志，新的消息落在之后。
- ** 运行容量满 (`F06.send-run-limit`).** 重启运行，使用一个运行槽，并持有该槽，由一个挂起的脚本化提供者提供（一个真正的模型无法在需求下挂起）。 下一颗子弹会重复使用支架并释放它。 首先创建等待会话，因为创建会话也需要运行槽。
  ```sh
  control-agent-server restart --config-json '{"max_concurrent_runs": 1}'
  QA_STUB=$(control-agent-server fixture llm-stub --name qa-f06-hang --step hang:120 --print-path)
  control-agent-server llm set --profile qa-f06-hang --model openai/qa-stub --base-url "$QA_STUB/v1" --no-api-key --no-validate
  WAITING=$(control-agent-server conversation start --no-autotitle --tools none --print-id)
  HOLD=$(control-agent-server conversation start --no-autotitle --tools none --prompt 'QA_F06_HOLD' --print-id)
  control-agent-server conversation wait "$HOLD" --until running --timeout 30
  control-agent-server api POST "/api/conversations/$WAITING/events" \
    --json '{"content":[{"type":"text","text":"QA_F06_429"}],"run":true}' --expect 429 \
    --check detail contains 'Message saved, but the conversation run limit was reached' --save F06.send-run-limit/post-429
  control-agent-server api GET "/api/conversations/$WAITING/events/search" --query source=user --query body=QA_F06_429 \
    --check items len-eq 1 --save F06.send-run-limit/saved
  control-agent-server api GET "/api/conversations/$WAITING" --check execution_status eq idle
  control-agent-server ws listen "/sockets/events/$WAITING" \
    --send '{"role":"user","content":[{"type":"text","text":"QA_F06_LIMIT_WS"}]}' \
    --until-kind ServerErrorEvent --until code=ConversationRunLimitExceeded --duration 15 --save F06.send-run-limit/ws
  control-agent-server api GET "/api/conversations/$WAITING/events/count" --query body=QA_F06_LIMIT_WS --check . eq 1
  ```
  的 POST 返回 429 `Message saved, but the conversation run limit was reached. Retry POST /api/conversations/<id>/run without resending the message.`消息已记录在日志中，对话继续 `idle`; socket发送获取的细节与相同 `ServerErrorEvent` 与 `code`
  `ConversationRunLimitExceeded` 并且它的消息也被保存。
- **智能体运行时的一条消息 (`F06.send-while-running`)。**最后一颗子弹。 上一个项目符号中的 `HOLD` 是 `running`，卡在挂起存根上的第一个模型调用中，因此存根的请求日志计数会运行。

  需要：`F06.send-run-limit`
  ```sh
  control-agent-server api GET "/api/conversations/$HOLD" --check execution_status eq running
  control-agent-server sink read --name qa-f06-hang --path /v1/chat/completions --expect-min 1 --expect-max 1
  control-agent-server api POST "/api/conversations/$HOLD/events" \
    --json '{"content":[{"type":"text","text":"QA_F06_MIDRUN"}],"run":true}' --expect 200 --check success eq true \
    --save F06.send-while-running/post
  control-agent-server api GET "/api/conversations/$HOLD/events/search" --query source=user --query body=QA_F06_MIDRUN \
    --check items len-eq 1 --save F06.send-while-running/persisted
  control-agent-server api GET "/api/conversations/$HOLD" --check execution_status eq running
  control-agent-server api POST "/api/conversations/$HOLD/run" --expect 409
  control-agent-server api POST "/api/conversations/$HOLD/interrupt" --expect 200
  control-agent-server conversation wait "$HOLD" --until paused --timeout 60
  if control-agent-server sink read --name qa-f06-hang --path /v1/chat/completions --expect-min 2 --wait 10; then false; fi
  control-agent-server api GET "/api/conversations/$HOLD" --check execution_status eq paused
  control-agent-server sink read --name qa-f06-hang --path /v1/chat/completions --expect-max 1 \
    --save F06.send-while-running/model-requests
  control-agent-server llm preset deepseek
  ```
  的 POST 尽管一次可以回答200个问题 `POST /run` 在同一个对话中是 409 `Conversation already running...`; 消息已记录在日志中，对话继续 `running`. 在中断之后，stub在10秒窗口内没有收到第二次模型请求
  `sink read --wait` 将在一个到达后立即返回）并且对话仍然是 `paused`，因此不会启动第二次运行：运行循环在下一步中拾取消息，并且停止的重新运行将被丢弃，因为中断在运行任务结束之前将其清除（`EventService.interrupt`）。 较早的 `--expect-min 1 --expect-max 1` 读取是同一接收器查询的正控制。 中断支架可释放插槽并恢复预设 `deepseek-flash`。

- ** 流式差异是临时的（`F06.ws-streaming-deltas`）。** 实际流式回复发送token 差异，而REST 历史和稍后的套接字回放仅包含持久事件。
  ```sh
  STREAM_CID=$(control-agent-server conversation start --tools none --no-autotitle \
    --llm-json '{"stream":true}' --print-id)
  control-agent-server ws start "/sockets/events/$STREAM_CID" --name "stream-$STREAM_CID" --settle 1
  control-agent-server api POST "/api/conversations/$STREAM_CID/events" \
    --json '{"role":"user","content":[{"type":"text","text":"Write one short sentence about ocean waves. Reply in plain text without calling tools."}],"run":true}' \
    --expect 200 --save F06.ws-streaming-deltas/send
  control-agent-server conversation wait "$STREAM_CID" --until finished --timeout 180
  control-agent-server ws read "stream-$STREAM_CID" --kinds ConversationStateUpdateEvent \
    --contains '"key": "full_state"' --expect-min 2 --wait 30
  STREAM_CAPTURE=$(control-agent-server ws stop "stream-$STREAM_CID" --kinds StreamingDeltaEvent --expect-min 1 \
    --save F06.ws-streaming-deltas/live | jq -r .saved)
  jq -e '[.frames[] | select(.direction == "received") | .frame | select(.kind == "StreamingDeltaEvent")] | length > 0 and any(.content != null or .reasoning_content != null)' "$STREAM_CAPTURE"
  control-agent-server api GET "/api/conversations/$STREAM_CID/events/count" --query kind=StreamingDeltaEvent \
    --check . eq 0 --save F06.ws-streaming-deltas/not-persisted
  control-agent-server ws listen "/sockets/events/$STREAM_CID" --query resend_mode=all --duration 3 \
    --expect-kind MessageEvent --expect-no-kind StreamingDeltaEvent --save F06.ws-streaming-deltas/replay
  control-agent-server api DELETE "/api/conversations/$STREAM_CID" --expect 200
  ```
  `content` 或 `reasoning_content` 的活帧包含。 None 应该被存储或回放：客户端在重连后使用最终持久化消息，并从事件日志缓存中移除临时消息 token。

<a id="gotchas"></a>

## 陷阱

- `kind` 过滤器采用 `kind` (`MessageEvent`) 中携带的裸类名事件或完全限定的类路径 (`openhands.sdk.event.llm_convertible.message.MessageEvent`,
  `openhands.sdk.event.conversation_state.ConversationStateUpdateEvent`); 未知或部分名称 (`message.MessageEvent`) 返回空页，而不是错误 (`F06.search-kind-short`)。
- `page_id` 是包容的，也是未知的 `page_id` 默默地从第一个事件（最新的一次）开始重启 `TIMESTAMP_DESC`因此，一个过期的游标看起来像一个新鲜的第一页。
- 与字符串相比，时间戳是朴素的服务器本地 ISO 字符串。 菜谱使用 `TZ=UTC` 运行服务器； 带有偏移量的值首先转换为服务器时间。 搜索按日志顺序进行，即时间戳顺序：在操作之后，一个 `stats` 更新被追加，其观测结果会被标记，因此在该观测结果的时间戳上进行 `timestamp__gte` 或 `resend_mode=since` 切片，可以保留 `F06.search-timestamp-order`。
- 每个对话的事件总线最多需要 50 个订阅者，包括内部订阅者（Webhook，自动标题）； 又一个套接字以 1013 关闭
  `Too many connections for this conversation`，SDK 将其视为可重试（来自源； 不驱动，因为 50 个捕获消耗太多内存）。
- 搜索删除 `null` 个字段 (`exclude_none`)； get-one 和batch-get 保留它们。 比较 ids，而不是原始的 JSON。
- 未知事件 ID 为 404，并且 `null` 位于批次的槽 (`F06.unknown-event`) 中； batch-get 是一个带有 JSON 主体的 GET，浏览器无法发送该主体。
- `SystemPromptEvent` 写在第一条消息上，而不是创建时； 创建的没有消息的对话具有空日志且计数为 0。
- `POST .../events` 与 `run: false` 永远不会运行，即使在空闲对话中也是如此； 发送至 `finished` 或 `stuck` 对话的消息将其设置为
  `idle`. 普通消息还会取消活动的 `/goal` 循环。
- 创建对话也需要一个运行槽，所以
  `max_concurrent_runs` 达到 `POST /api/conversations` 本身的答案 429。 来自 `POST .../events` 的 429 表示消息已保存：重试
  `POST /run`，从来没有消息。
- 在套接字上发送的每个帧都运行智能体（`run=True` 是硬编码的）； 使用 REST 追加而不运行。 错误以 `ServerErrorEvent` 帧的形式返回，其中 `code` 是 Python 异常类名称，并且套接字保持打开状态。
- 快照会在任何重播之前推送，且实时事件不会被屏蔽
  from replayed ones: during a run a reconnect with `resend_mode=all` can
  传递一个事件两次或乱序，因此按 ID 进行重复数据删除。 在实时运行的帧中也不严格按照时间戳顺序（a
  `last_user_message_id` 更新可以在其消息之前到达）。
- 身份验证失败的路径看起来有所不同：升级后第一帧身份验证以 4001 结束； 升级之前拒绝错误的已弃用查询或标头密钥（HTTP 403，无关闭代码），SDK 不会将其视为致命的。
- 删除会话不会关闭其打开的套接字 (`F06.ws-delete-close`)； 它们保持打开状态，不再有任何帧，而新连接会收到 4004。
- 仅当智能体的 LLM 有 `stream: true` 时，`StreamingDeltaEvent` 帧才到达此套接字； 它们从来都不是已持久化，所以搜索永远不会返回它们。
- 每个字段的 `execution_status=finished` 帧是一个提示，而不是运行的结束：停止钩子可以将其设置回 `running`。 运行后发布的`full_state`快照是权威的（SDK等待它）； 在 `finished` 处停止的食谱会重新读取 REST 处的状态。
- `running` 对话中的 `POST .../events` 与 `run: true` 是 200，而不是 `POST /run` 的 409：消息加入运行循环。 想要知道新的运行是否开始的客户端必须监视套接字。
- 正文是必需的（没有正文是 422），但每个字段都有一个默认值：
  `{}` 是一个有效的请求，并附加一个空的用户 `MessageEvent`
  `content`.
- 智能体仅获取文件编辑器（加上内置的 `finish` 和
  `think`）所以家庭不需要`tmux`。 旧版本的这个套件把tmux端口放在运行目录下，而一个新版本的`map run`则使路径超过了Unix套接字的限制，终端工具因此失败了
  `File name too long`; `launch` 现在使用一个短的 `/tmp/ohv-*` 目录。
