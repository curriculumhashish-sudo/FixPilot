<a id="session-websocket-protocol"></a>

# 会话 WebSocket 协议

会话套接字是更新的、可恢复的会话流。 客户端连接到一个对话，使用第一帧进行身份验证，并接收由 `type` 区分的 JSON 个信封。 `sync` 帧始终先出现并宣布重播范围。 已持久化事件随后以 `durable` 个帧的形式到达，每个帧的 `seq` 是该事件在磁盘日志中的索引，因此客户端可以存储最后一个 `seq` 并重新连接到 `?after_seq=<seq>`，避免断点或重复。 未持久状态快照以 `transient` 帧形式到达，没有 `seq` 帧。 虽然流式传输 LLM 回答，但 `item_started`、`delta` 和 `item_aborted` 进度框显示键入内容。 套接字本身的问题以 `error` 帧的形式返回。 客户端发送与旧事件套接字上相同的 `Message` JSON，并且它发送的每条消息都会启动运行。 入场限制为
字节：过大的帧或停止的读取器获取关闭代码 1013 而不是
阻塞发布者，客户端通过重新连接其游标来恢复。

资料来源：`openhands-agent-server/openhands/agent_server/session_socket.py`、`openhands-agent-server/openhands/agent_server/session_protocol.py`、`openhands-agent-server/openhands/agent_server/sockets.py`、`openhands-agent-server/openhands/agent_server/pub_sub.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-sdk/openhands/sdk/agent/stream_context.py`

需求：`llm`

路线：`WS /sockets/session/{conversation_id}`

<a id="sub-features"></a>

## 子功能

- `F07.sync-first`：第一个服务器帧为`{"type": "sync"}`； `from_seq` 与 `after_seq` 相呼应（仅实时时不存在），`through_seq` 是磁盘上的最后一个 `seq`（空日志时不存在）。
- `F07.snapshot-transient`：每个连接在 `sync` 之后（以及在运行时重播之后）获得一个 `transient` 帧，其中包含 `full_state` `ConversationStateUpdateEvent`，但没有 `seq`； 从来都不是已持久化。
- `F07.full-replay`: `after_seq=-1` （或任何低于它的值）都会重播已持久化事件 `durable` 框架与 `seq` 0..`through_seq`按照顺序，一次一个，使用相同的 ids REST 的回报。
- `F07.seq-on-disk`：持久帧的`seq`是事件的磁盘索引，`events/event-NNNNN-<event id>.json`中的`NNNNN`。
- `F07.resume-cursor`：`after_seq=k`完全重播`seq > k`的事件； `after_seq=through_seq` 不重播任何内容。
- `F07.live-durable`：在仅实时连接上，稍后附加的事件（带有 `run: false` 的 REST 消息）作为带有下一个 `seq` 的 `durable` 帧到达。
- `F07.live-order`：一个连接上的实时 `durable` 帧按 `seq` 升序到达。
- `F07.replay-then-live`: 当事件被追加时，与 `after_seq=-1` 的连接打开，接收追回和实时尾部的每个已持久化事件：其持久化 `seq` 值为 0..N-1，对于 N 个事件 REST 的计数。
- `F07.send-message`：在套接字上发送的 `Message` JSON 是作为用户 `MessageEvent` 的已持久化（作为 `durable` 帧回显）并运行智能体到 `finished`。
- `F07.error-frame`：JSON 不是有效的 `Message`，将获得 `error` 帧 (`code` `ValidationError`)； 连接保持打开状态，什么也没有已持久化。
- `F07.error-non-json`：不是JSON的文本框架会获得`error`框架和`code``JSONDecodeError`，二进制框架也会获得`error`框架； 连接保持打开状态。
- `F07.reject-non-user`：`role` 不是 `user` 的 `Message` 获得 `error` 帧 (`Only user messages are allowed to be sent to the agent.`)，但不是已持久化。
- `F07.auth-frame-ignored`：忽略身份验证之后的冗余`{"type": "auth", ...}`帧：没有`error`帧，没有已持久化。
- `F07.auth`：第一帧按键打开socket； 错误的密钥或在身份验证之前发送的消息会以 4001 关闭它（无任何内容已持久化）； 已弃用查询参数中的运行密钥将打开它，错误的密钥会导致握手失败并返回 HTTP 403。
- `F07.unknown-conversation`：一个格式良好的 ID，指定在身份验证之后没有对话以 4004 `Conversation not found` 结束。
- `F07.bad-handshake`：不是 UUID 的会话 ID，或者不是整数的 `after_seq`，握手失败，返回 HTTP 403。
- `F07.restart-resume`：`seq` 在服务器重新启动后仍然存在：使用相同的光标重新连接会以相同的 `seq` 值重播相同的事件 ID。
- `F07.progress-frames`: 在 `llm.stream` 开启的情况下，一个运行会流 `item_started`，然后流 `delta` 帧（`order` 0, 1, ...），并且每个项目都会被恰好一个 `durable` 帧所退休，该帧的 `event.id` 等于 `item_id`（或者由 `item_aborted`）。
- `F07.progress-not-replayed`：在流式运行后重新与 `after_seq=-1` 连接会重播持久消息，但不会重播 `item_started`、`delta` 或 `item_aborted` 帧。
- `F07.item-aborted`在流式回答正在生产时中断运行 `delta` 销毁具有唯一性的项目 `item_aborted` frame (same) `item_id` 和 `attempt`, `reason`  `cancelled`）且没有进一步进展。 无 `durable` frame or 已持久化事件携带该 ID，以及重连 `after_seq=-1` 回放没有进展帧。
- `F07.frame-too-large`：重放超过 4 MiB 的事件会关闭 1013 `frame_too_large` 的套接字； 该事件在 REST 上保持可读状态，并且光标经过它会重播 REST。
- `F07.slow-consumer`一个客户端在读取超过16个字节时停止 MiB 预算队列写入操作已关闭，错误代码为1013 `slow_consumer`而且对话继续服务于其他套接字。
- `F07.subscriber-limit`：事件扇出每个会话最多允许 50 个订阅者； 额外的套接字以 1013 `Too many connections for this conversation` 关闭，关闭套接字会释放其插槽。
- `F07.deleted-close`：删除会话将关闭附加到它的会话套接字。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- WebSocket: `/sockets/session/{conversation_id}` 带有查询参数
  `after_seq`（仅实时时省略，`-1` 表示完整历史记录，`k` 在 `seq` k 之后恢复）。 身份验证与其他套接字共享：第一帧 `{"type": "auth", "session_api_key": K}` 或已弃用
  `session_api_key` 查询参数或 `X-Session-API-Key` header (F02 拥有认证矩阵。 这里的所有食谱都直接驱动了 socket CLI's `ws listen` 和 `ws start`, 或者是小的 `websockets` 或原始套接字程序 under `exec` when the CLI 无法发送帧（非-）JSON 文本、二进制帧、一个读取器会阻塞、55个连接。
- 客户端到服务器：一个 `Message` JSON 对象 (`{"role": "user", "content": [{"type": "text", "text": "..."}]}`)。 额外的字段将被忽略，包括 `run`：每条消息都运行智能体 (`EventService.send_message(message, run=True)`)。
- 服务器到客户端：`sync`、`durable`、`transient`、`item_started`、`delta`、
  `item_aborted`, `error` (`session_protocol.py`). 框架是已序列化与
  `exclude_none`，因此缺少可选字段，而不是`null`。
- SDK和TypeScript客户端：都还没有消耗这个套接字；
  `RemoteConversation` 和 TypeScript 客户端使用 `/sockets/events/{id}`（F06 及其套接字系列）。 只有`tests/agent_server/test_session_socket.py`和`tests/agent_server/test_agent_server_wsproto.py`引用了它。
- REST 这里使用的第二个视图：`POST /api/conversations/{id}/events`（附加消息而不运行），`GET .../events/search` 和
  `GET .../events/count`（已持久化）和`GET`/`DELETE/api/conversations/{id}`（`agent.llm.stream`显示对话是否流式传输； `conversation start --llm-json '{"stream": true}'` 将其设置为一次对话）。 `F07.item-aborted`还调用`POST /api/conversations/{id}/interrupt`（F05的路由）作为其触发器。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已实时运行并已导出 (`launch --new`)，`doctor` 正常。
  设置 `$DEEPSEEK_API_KEY`（三个项目运行 deepseek-flash：一条发送的消息，一条流式回复，一条中断的流式答复）。
- `EMPTY` 是没有事件的对话。 `CID` 是一个包含五个已持久化事件的对话，在没有模型调用的情况下创建：附加有 `run: false` 的两个用户消息给出 `SystemPromptEvent` (seq 0)，
  `MessageEvent` QA_F07_ONE (1), `last_user_message_id` 更新 (2),
  `MessageEvent` QA_F07_TWO (3) 和 `last_user_message_id` 更新 (4)。
  `E0`..`E4`他们的 ID 来自 REST。 直到 `F07.live-durable` 的项目符号依赖于 `CID` 恰好具有这五个事件，因此它们持久化什么也没有。 两个对话都使用 `--tools none --no-autotitle`，因此不涉及标题订阅者或工具运行时。
  ```sh
  control-agent-server llm preset deepseek
  EMPTY=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  CID=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$CID/events" --json '{"role":"user","content":[{"type":"text","text":"QA_F07_ONE"}],"run":false}' --expect 200
  control-agent-server api POST "/api/conversations/$CID/events" --json '{"role":"user","content":[{"type":"text","text":"QA_F07_TWO"}],"run":false}' --expect 200
  control-agent-server api GET "/api/conversations/$CID/events/count" --expect 200 --check . eq 5
  E0=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.0.id)
  E1=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.1.id)
  E2=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.2.id)
  E3=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.3.id)
  E4=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.4.id)
  ```
- 捕获内容保存在以对话 id 结尾的名称下，因此
  `state cat evidence/...` 检查读取此重播写入的文件，即使是在之前重播该系列的运行中也是如此。

- **同步排在第一位 (`F07.sync-first`)。** 只读仅实时连接的第一帧，在空对话和非空对话上。
  ```sh
  control-agent-server ws listen "/sockets/session/$EMPTY" --count 1 --save "F07.sync-first/empty-$EMPTY"
  control-agent-server state cat "evidence/F07.sync-first/empty-$EMPTY.json" \
    --check frames.1.frame.type eq sync --check frames.1.frame.through_seq missing --check frames.1.frame.from_seq missing
  control-agent-server ws listen "/sockets/session/$CID" --count 1 --save "F07.sync-first/live-$CID"
  control-agent-server state cat "evidence/F07.sync-first/live-$CID.json" \
    --check frames.1.frame.type eq sync --check frames.1.frame.through_seq eq 4 --check frames.1.frame.from_seq missing
  ```
  空对话的第一个帧就是 `{"type": "sync"}`; `CID`'s 是 `{"type": "sync", "through_seq": 4}`.
- **状态快照(`F07.snapshot-transient`)。**仅实时连接的第二帧。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --count 2 --save "F07.snapshot-transient/live-$CID"
  control-agent-server state cat "evidence/F07.snapshot-transient/live-$CID.json" \
    --check frames.2.frame.type eq transient --check frames.2.frame.seq missing \
    --check frames.2.frame.event.kind eq ConversationStateUpdateEvent \
    --check frames.2.frame.event.key eq full_state --check frames.2.frame.event.value.id eq "$CID"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  快照是一个 `transient` 无框架 `seq` whose event is a
  `full_state`更新此对话，事件计数仍为5：快照不是已持久化。
- **完整回放 (`F07.full-replay`)。**连接`after_seq=-1`。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=-1 --duration 3 --expect-frames 7 --save "F07.full-replay/all-$CID"
  control-agent-server state cat "evidence/F07.full-replay/all-$CID.json" \
    --check frames.1.frame.from_seq eq -1 --check frames.1.frame.through_seq eq 4 \
    --check frames.2.frame.type eq durable --check frames.2.frame.seq eq 0 --check frames.2.frame.event.id eq "$E0" \
    --check frames.3.frame.seq eq 1 --check frames.3.frame.event.id eq "$E1" \
    --check frames.4.frame.seq eq 2 --check frames.4.frame.event.id eq "$E2" \
    --check frames.5.frame.seq eq 3 --check frames.5.frame.event.id eq "$E3" \
    --check frames.6.frame.seq eq 4 --check frames.6.frame.event.id eq "$E4" \
    --check frames.7.frame.type eq transient
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=-7 --duration 3 --expect-frames 7 --save "F07.full-replay/below-$CID"
  control-agent-server state cat "evidence/F07.full-replay/below-$CID.json" --check frames.1.frame.from_seq eq -7 \
    --check frames.2.frame.seq eq 0 --check frames.2.frame.event.id eq "$E0" --check frames.6.frame.seq eq 4
  ```
  七帧：`sync {from_seq: -1, through_seq: 4}`，五个具有`seq` 0到4的持久帧，按REST顺序携带REST ids，然后是快照。 `after_seq=-7` 重复了 `-7` 并重播了同样的历史。
- **Seq 是磁盘索引 (`F07.seq-on-disk`)。**按 `seq` 预测的名称读取事件文件。
  ```sh
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/events/event-00001-$E1.json" --check id eq "$E1" --contains QA_F07_ONE
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/events/event-00003-$E3.json" --check id eq "$E3" --contains QA_F07_TWO
  ```
  两个文件都以预测的名字存在，并且包含两个消息。
- **从光标处恢复 (`F07.resume-cursor`)。**在 `seq` 2 之后重新连接，然后在最后一个 `seq` 之后重新连接。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=2 --duration 3 --expect-frames 4 --save "F07.resume-cursor/after2-$CID"
  control-agent-server state cat "evidence/F07.resume-cursor/after2-$CID.json" \
    --check frames.1.frame.from_seq eq 2 --check frames.2.frame.seq eq 3 --check frames.2.frame.event.id eq "$E3" \
    --check frames.3.frame.seq eq 4 --check frames.3.frame.event.id eq "$E4" --check frames.4.frame.type eq transient
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=4 --duration 3 --expect-frames 2 --save "F07.resume-cursor/after4-$CID"
  control-agent-server state cat "evidence/F07.resume-cursor/after4-$CID.json" \
    --check frames.1.frame.from_seq eq 4 --check frames.1.frame.through_seq eq 4 --check frames.2.frame.type eq transient
  ```
  `after_seq=2` 仅重播 `seq` 3 和 4； `after_seq=4` 不重播任何内容并直接进入快照。
- **无效消息 (`F07.error-frame`)。**发送两个不是 `Message` 的 JSON 帧。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --send '{"content":"QA_F07_BAD"}' --send '[1, 2]' \
    --duration 5 --expect-frames 4 --expect-open --save "F07.error-frame/invalid-$CID"
  control-agent-server state cat "evidence/F07.error-frame/invalid-$CID.json" \
    --check frames.1.direction eq sent --check frames.2.direction eq sent \
    --check frames.5.frame.type eq error --check frames.5.frame.code eq ValidationError --check frames.5.frame.detail contains role \
    --check frames.6.frame.type eq error --check frames.6.frame.code eq ValidationError
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  五秒内恰好有四个帧：`sync`之后和快照之后有两帧
  `error` 帧（`ValidationError`，第一个命名缺失的 `role`），仅此而已； 第二个 `error` 显示套接字在第一个中幸存下来，最后它仍然打开，并且什么都没有已持久化。 保存的捕获首先列出了两个发送的帧，紧邻 `opened` 条目（`frames.1` 和 `frames.2`）。
- **非JSON和二进制帧(`F07.error-non-json`)。** CLI 的 `--send` 仅需要 JSON，因此一个短的 `websockets` 程序会发送原始帧。
  ```sh
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures"
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-raw-frames.py" <<'EOF'
  import json, os, sys
  from websockets.sync.client import connect

  url = os.environ["AGENT_SERVER_URL"].replace("http", "ws", 1) + "/sockets/session/" + sys.argv[1]
  with connect(url) as ws:
      ws.send(json.dumps({"type": "auth", "session_api_key": os.environ["SESSION_API_KEY"]}))
      ws.send("QA_F07 this is not JSON")
      ws.send(b"QA_F07 binary frame")
      ws.send("{}")
      frames = [json.loads(ws.recv(timeout=10)) for _ in range(5)]
  types = [f["type"] for f in frames]
  codes = [f.get("code") for f in frames if f["type"] == "error"]
  print("types", types, "codes", codes)
  assert types == ["sync", "transient", "error", "error", "error"], types
  assert codes[0] == "JSONDecodeError" and codes[2] == "ValidationError", codes
  print("QA_OK")
  EOF
  control-agent-server exec --expect-output QA_OK --save "F07.error-non-json/raw-$CID" -- .venv/bin/python "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-raw-frames.py" "$CID"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  三 `error` 按照顺序：  1.  `JSONDecodeError` 对于文本，还有一个二进制帧（今天 `KeyError`  `'text'`, and `ValidationError` 为了 `{}`这还证明了套接字在前两轮中存活了下来。
- **非用户角色 (`F07.reject-non-user`)。**发送 `assistant` 消息。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --send '{"role":"assistant","content":[{"type":"text","text":"QA_F07_ROLE"}]}' \
    --duration 5 --expect-frames 3 --expect-open --save "F07.reject-non-user/assistant-$CID"
  control-agent-server state cat "evidence/F07.reject-non-user/assistant-$CID.json" \
    --check frames.4.frame.type eq error --check frames.4.frame.detail contains 'Only user messages are allowed'
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq idle
  ```
  `sync`、快照和一 `error` 帧（今天的代码 `AssertionError`），仅此而已； 没有新事件，并且智能体不运行（对话仍然是 `idle`）。
- **冗余的认证帧 (`F07.auth-frame-ignored`).**首先使用头部认证，然后发送一个认证帧，就像一个既认证客户端一样，接着发送一个无效帧，其 `error`回复证明服务器读过了认证帧。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --auth header --send '{"type":"auth","session_api_key":"qa-redundant"}' \
    --send '{"content":"QA_F07_AFTER_AUTH"}' --duration 5 --expect-frames 3 --expect-kind error --expect-open \
    --save "F07.auth-frame-ignored/redundant-$CID"
  control-agent-server state cat "evidence/F07.auth-frame-ignored/redundant-$CID.json" \
    --check frames.3.frame.type eq sync --check frames.4.frame.type eq transient \
    --check frames.5.frame.type eq error --check frames.5.frame.code eq ValidationError \
    --check frames.5.frame.detail contains QA_F07_AFTER_AUTH --check frames.6.direction ne received
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  `sync`、快照和恰好一个 `error` 帧（`ValidationError`，引用 `QA_F07_AFTER_AUTH`）到达：对无效帧的回复，服务器在身份验证帧之后读取该回复。 认证帧本身没有回复（如果到达 `Message` 验证，则为 `ValidationError`，如 `F07.error-frame`，这将产生两个 `error` 帧），也没有添加事件。 冗余帧内的密钥不再被检查。
- **身份验证 (`F07.auth`).** F02 矩阵的会话套接字视图。
  ```sh
  control-agent-server ws listen "/sockets/session/$CID" --count 1 --expect-kind sync --expect-open --save "F07.auth/first-frame-$CID"
  control-agent-server ws listen "/sockets/session/$CID" --auth bad --expect-close 4001 --expect-frames 0 --save "F07.auth/bad-key-$CID"
  control-agent-server ws listen "/sockets/session/$CID" --auth none --send '{"role":"user","content":[{"type":"text","text":"QA_F07_NOAUTH"}]}' --expect-close 4001 --expect-frames 0
  control-agent-server ws listen "/sockets/session/$CID" --auth query --count 1 --expect-kind sync --expect-open
  control-agent-server ws listen "/sockets/session/$CID" --auth bad-query --duration 3 --expect-reject 403 --save "F07.auth/bad-query-$CID"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq 5
  ```
  `sync` 连接成功后，运行的键打开套接字。 错误的密钥和未发送的认证帧都以4001 `Authentication failed` 错误关闭，而未认证的消息在任何帧发送之前就已持久化。 在已弃用查询参数中，运行的密钥也会打开它，而错误的密钥在握手时会被拒绝(HTTP 403，没有关闭代码）。
- **未知对话 (`F07.unknown-conversation`).**一个有效的UUID，什么也没有提及。
  ```sh
  control-agent-server ws listen /sockets/session/00000000-0000-4000-8000-0000000000f7 --query after_seq=-1 --expect-close 4004 --expect-frames 0 \
    --save "F07.unknown-conversation/unknown-$CID"
  control-agent-server state cat "evidence/F07.unknown-conversation/unknown-$CID.json" --check summary.close.reason eq 'Conversation not found'
  ```
  关闭代码 4004，原因 `Conversation not found`，在成功认证帧之后。
- **格式错误的握手 (`F07.bad-handshake`)。**路径和查询验证在套接字被接受之前运行。
  ```sh
  control-agent-server ws listen /sockets/session/qa-not-a-uuid --duration 3 --expect-reject 403
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=qa --duration 3 --expect-reject 403
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=4 --count 1 --expect-kind sync --expect-open
  ```
  两者都是 HTTP 403握手拒绝，而不是关闭代码，而使用整数游标时，相同的路径打开。
- **Live耐用框架(`F07.live-durable`).**在后台捕获仅实时套接字，然后在不运行的情况下在 REST 上附加一条消息。
  ```sh
  control-agent-server ws start "/sockets/session/$CID" --name "live-$CID" --settle 2
  control-agent-server api POST "/api/conversations/$CID/events" --json '{"role":"user","content":[{"type":"text","text":"QA_F07_LIVE"}],"run":false}' --expect 200
  L5=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.5.id)
  L6=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query limit=100 --field items.6.id)
  control-agent-server conversation events "$CID" --kinds MessageEvent --contains QA_F07_LIVE --expect-kind MessageEvent
  control-agent-server ws read "live-$CID" --wait 10 --kinds durable:ConversationStateUpdateEvent --contains "\"seq\": 6, \"event\": {\"id\": \"$L6\""
  control-agent-server ws stop "live-$CID" --wait 10 --kinds durable:MessageEvent --contains "\"seq\": 5, \"event\": {\"id\": \"$L5\"" --save "F07.live-durable/live-$CID"
  control-agent-server state cat "evidence/F07.live-durable/live-$CID.json" \
    --check frames.1.frame.through_seq eq 4 --check frames.2.frame.type eq transient --check frames.5.direction ne received
  ```
  在 `sync` (`through_seq` 4) 和快照之后，两个持久帧到达：消息为 `seq` 5，其 id REST 在索引 5 处
  `last_user_message_id` 更新为 `seq` 6（id REST 在索引 6 处列出），没有其他内容：不重新发送 `through_seq` 或以下的帧。 已保存
  `ws stop` 捕获以 `opened` 条目开始，以 `stopped` 条目结束，因此 `frames.5.direction ne received` 表示正好有四个帧到达。
- **按序列顺序排列的实时帧 (`F07.live-order`)。**一个连接上的持久帧按 `seq` 顺序到达，就像重播一样。 用户消息在 `last_user_message_id` 更新之前发布：
  仅当消息到达发布回调后，`LocalConversation` 才会设置 `last_user_message_id`（立即追加并发布更新）。 存储了它看到的最高 `seq` 的客户端可以恢复
  from it without losing the message.
  ```sh
  ORD=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server ws start "/sockets/session/$ORD" --name "order-$ORD" --settle 2
  control-agent-server api POST "/api/conversations/$ORD/events" --json '{"role":"user","content":[{"type":"text","text":"QA_F07_ORDER"}],"run":false}' --expect 200
  control-agent-server conversation events "$ORD" --kinds MessageEvent --contains QA_F07_ORDER --expect-kind MessageEvent
  control-agent-server ws read "order-$ORD" --wait 10 --kinds durable:SystemPromptEvent --contains '"seq": 0,' --expect-min 1
  control-agent-server ws read "order-$ORD" --wait 10 --kinds durable:ConversationStateUpdateEvent --contains '"seq": 2,' --expect-min 1
  control-agent-server ws stop "order-$ORD" --wait 10 --kinds durable:MessageEvent --contains '"seq": 1,' --expect-min 1 --save "F07.live-order/order-$ORD"
  control-agent-server state cat "evidence/F07.live-order/order-$ORD.json" --contains QA_F07_ORDER --check frames.6.direction ne received \
    --check frames.1.frame.type eq sync --check frames.2.frame.type eq transient \
    --check frames.3.frame.type eq durable --check frames.4.frame.type eq durable --check frames.5.frame.type eq durable
  control-agent-server state cat "evidence/F07.live-order/order-$ORD.json" --check frames.3.frame.seq eq 0 --check frames.4.frame.seq eq 1 --check frames.5.frame.seq eq 2
  ```
  排列步骤和正控件都一样：消息是已持久化，捕获是`sync`，快照和恰好三个持久帧，这些帧携带`seq`0（系统提示词，1（消息），2（其`last_user_message_id`更新）。 只有最后一行决定顺序：0，1，2（消息，然后是更新），无论消息是通过REST发送的还是通过套接字发送的。
- **回放和实时尾，每个事件一次`F07.replay-then-live`).** 打开一个全历史捕获，同时有四条消息在后台被添加，连接应该在添加之前、期间或之后出现。 无论以哪种方式落地，重播和直播的结合都必须是整个日志一次。
  ```sh
  SEAM=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$SEAM/events" --json '{"role":"user","content":[{"type":"text","text":"QA_F07_SEAM_0"}],"run":false}' --expect 200
  (for i in 1 2 3 4; do
    control-agent-server api POST "/api/conversations/$SEAM/events" --json "{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"QA_F07_SEAM_$i\"}],\"run\":false}" --expect 200 >/dev/null
  done) &
  SEAMPID=$!
  control-agent-server ws start "/sockets/session/$SEAM" --name "seam-$SEAM" --query after_seq=-1 --settle 0
  wait "$SEAMPID"
  control-agent-server api GET "/api/conversations/$SEAM/events/count" --check . eq 11
  control-agent-server ws stop "seam-$SEAM" --wait 15 --kinds durable:SystemPromptEvent,durable:MessageEvent,durable:ConversationStateUpdateEvent \
    --expect-min 11 --save "F07.replay-then-live/seam-$SEAM"
  python3 - "$AGENT_SERVER_VERIFY_RUN/evidence/F07.replay-then-live/seam-$SEAM.json" 11 <<'EOF'
  import json, sys
  frames = [e["frame"] for e in json.load(open(sys.argv[1]))["frames"] if e["direction"] == "received"]
  durable = [f for f in frames if f["type"] == "durable"]
  assert frames[0]["type"] == "sync" and frames[0]["from_seq"] == -1, frames[0]
  assert sorted(f["seq"] for f in durable) == list(range(int(sys.argv[2]))), [f["seq"] for f in durable]
  assert len({f["event"]["id"] for f in durable}) == len(durable), "an event arrived twice"
  print("through_seq at connect:", frames[0].get("through_seq"), "durable seqs:", [f["seq"] for f in durable])
  EOF
  ```
  REST 记录了 11 个事件（系统提示词，五条消息，五条记录）
  `last_user_message_id` 更新）并且捕获携带 `seq` 0 到 10，每个一次，具有不同的事件 ID。 打印的 `through_seq` 显示连接着陆的位置（从 2 到 10 的任意值）； 实时尾部内的订单是 `F07.live-order` 的事，而不是这张支票的事。
- **在套接字上发送消息 (`F07.send-message`)。**一次微小的深度搜索闪光运行； 该消息由后台捕获在连接时发送。
  ```sh
  control-agent-server ws start "/sockets/session/$CID" --name "send-$CID" --settle 2 \
    --send '{"role":"user","content":[{"type":"text","text":"QA_F07_WS Reply with the single word: ok"}]}'
  control-agent-server conversation wait "$CID" --until finished --timeout 180
  control-agent-server ws read "send-$CID" --wait 15 --kinds durable:ConversationStateUpdateEvent --contains '"value": "finished"'
  control-agent-server ws stop "send-$CID" --kinds durable:MessageEvent --contains QA_F07_WS --expect-min 1 --save "F07.send-message/send-$CID"
  control-agent-server ws read "send-$CID" --kinds durable:MessageEvent,durable:ActionEvent --contains '"source": "agent"' --expect-min 1
  control-agent-server conversation events "$CID" --kinds MessageEvent --contains QA_F07_WS --expect-kind MessageEvent
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished
  ```
  端点会将用户消息作为持久帧回显，然后输出智能体（一个持久事件，包含`source`和`agent`，其回复，或者`finish`的行动）和持久`execution_status: finished`更新。 REST 列出了消息和报告 `finished`。 不需要`run`字段。
- **光标在重新启动后仍然存在 (`F07.restart-resume`)。**重新启动服务器，然后从同一光标恢复。
  ```sh
  T=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server restart
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=2 --duration 3 --save "F07.restart-resume/after2-$CID"
  control-agent-server state cat "evidence/F07.restart-resume/after2-$CID.json" --check summary.frames eq "$((T - 1))" \
    --check frames.1.frame.through_seq eq "$((T - 1))" \
    --check frames.2.frame.seq eq 3 --check frames.2.frame.event.id eq "$E3" \
    --check frames.3.frame.seq eq 4 --check frames.3.frame.event.id eq "$E4" \
    --check "frames.$((T - 2)).frame.seq" eq "$((T - 1))" --check "frames.$((T - 1)).frame.type" eq transient
  ```
  重启后，`through_seq` 仍然是最后一个在它之前的索引
  `seq` 3 和 4 仍然携带 `E3` 和 `E4`：`sync`、`T - 3` 持久帧和快照。
- **流式传输进度帧 (`F07.progress-frames`).** 开始与 `llm.stream` 会话（共享设置保持不变），然后在它的套接字上发送消息，并检查捕获的协议规则。
  ```sh
  SID=$(control-agent-server conversation start --tools none --no-autotitle --llm-json '{"stream": true}' --print-id)
  control-agent-server api GET "/api/conversations/$SID" --check agent.llm.stream eq true
  control-agent-server ws listen "/sockets/session/$SID" --send '{"role":"user","content":[{"type":"text","text":"Reply with the single word: ok"}]}' \
    --until-kind durable:ConversationStateUpdateEvent --until event.key=execution_status --until event.value=finished --duration 180 \
    --expect-kind item_started --expect-kind delta --save "F07.progress-frames/run-$SID"
  ITEM=$(python3 - "$AGENT_SERVER_VERIFY_RUN/evidence/F07.progress-frames/run-$SID.json" <<'EOF'
  import json, sys
  frames = [e["frame"] for e in json.load(open(sys.argv[1]))["frames"] if e["direction"] == "received"]
  started = [(i, f) for i, f in enumerate(frames) if f["type"] == "item_started"]
  assert started, "no item_started frame"
  durable_items = []
  for i, start in started:
      item, attempt = start["item_id"], start["attempt"]
      assert "seq" not in start, start
      mine = [f for f in frames if f["type"] == "delta" and f["item_id"] == item and f["attempt"] == attempt]
      early = [f for f in frames[:i] if f["type"] == "delta" and f["item_id"] == item and f["attempt"] == attempt]
      assert mine and not early, f"deltas of {item} missing or before item_started"
      assert [d["order"] for d in mine] == list(range(len(mine))), "delta order has a gap"
      retired = [f for f in frames[i + 1:] if (f["type"] == "durable" and f["event"]["id"] == item)
                 or (f["type"] == "item_aborted" and f["item_id"] == item)]
      assert len(retired) == 1, f"{item} retired {len(retired)} times"
      if retired[0]["type"] == "durable":
          assert retired[0]["seq"] > start.get("anchor_seq", -1), (retired[0]["seq"], start)
          durable_items.append(item)
  assert durable_items, "no item was retired by a durable frame"
  print(f"{len(started)} item(s); retired by durable: {durable_items}", file=sys.stderr)
  print(durable_items[0])
  EOF
  )
  test -n "$ITEM"
  ```
  至少有一个 `item_started`（没有 `seq`，有一个 `anchor_seq`），然后是它的
  `delta` 帧，`order` 0, 1, ...，以及后面的一个 `durable` 帧，其 `event.id` 是 `item_id`（智能体的回复）。 `ITEM` 就是那个 id。
- **进度永远不会重播 (`F07.progress-not-replayed`)。**重新连接到具有完整历史记录的流式对话。

  需要：`F07.progress-frames`
  ```sh
  test -n "$ITEM"
  control-agent-server ws listen "/sockets/session/$SID" --query after_seq=-1 --duration 3 \
    --expect-kind durable:MessageEvent --expect-no-kind item_started --expect-no-kind delta --expect-no-kind item_aborted \
    --save "F07.progress-not-replayed/replay-$SID"
  control-agent-server state cat "evidence/F07.progress-not-replayed/replay-$SID.json" --contains "\"id\": \"$ITEM\"" \
    --not-contains '"item_started"' --not-contains '"type": "delta"' --not-contains '"item_aborted"'
  ```
  回放携带持久回复（其ID为`ITEM`），没有任何类型的进度帧。
- **中断的流(`F07.item-aborted`)。**启动一个需要数十秒（数到 3000）的流式 deepseek-flash 答案，等待其 `delta` 帧在后台捕获上流动，然后中断 REST（`POST .../interrupt`、F05 的路线）上的运行并判断捕获上的项目帧。
  ```sh
  AB=$(control-agent-server conversation start --tools none --no-autotitle --llm-json '{"stream": true}' --print-id)
  control-agent-server ws start "/sockets/session/$AB" --name "abort-$AB" --settle 2 \
    --send '{"role":"user","content":[{"type":"text","text":"Count from 1 to 3000, one number per line. Output only the numbers."}]}'
  control-agent-server ws read "abort-$AB" --wait 120 --kinds delta --expect-min 3
  control-agent-server api POST "/api/conversations/$AB/interrupt" --expect 200 --save "F07.item-aborted/interrupt-$AB"
  control-agent-server conversation wait "$AB" --until paused --timeout 30
  control-agent-server ws stop "abort-$AB" --wait 15 --kinds item_aborted --contains '"reason": "cancelled"' --expect-min 1 --save "F07.item-aborted/abort-$AB"
  ABORTED=$(python3 - "$AGENT_SERVER_VERIFY_RUN/evidence/F07.item-aborted/abort-$AB.json" <<'EOF'
  import json, sys
  frames = [e["frame"] for e in json.load(open(sys.argv[1]))["frames"] if e["direction"] == "received"]
  aborted = [(i, f) for i, f in enumerate(frames) if f["type"] == "item_aborted"]
  assert len(aborted) == 1, f"{len(aborted)} item_aborted frames"
  i, abort = aborted[0]
  item, attempt = abort["item_id"], abort["attempt"]
  assert abort["reason"] == "cancelled", abort
  started = [f for f in frames[:i] if f["type"] == "item_started" and f["item_id"] == item]
  assert started and started[-1]["attempt"] == attempt, (started, abort)
  deltas = [f for f in frames[:i] if f["type"] == "delta" and f["item_id"] == item and f["attempt"] == attempt]
  assert deltas and [d["order"] for d in deltas] == list(range(len(deltas))), "deltas missing or with a gap"
  late = [f for f in frames[i + 1:] if f.get("item_id") == item]
  assert not late, f"progress for {item} after item_aborted: {late[0]}"
  assert not [f for f in frames if f["type"] == "durable" and f["event"]["id"] == item], "a durable frame carries the aborted id"
  print(f"{len(deltas)} deltas, then item_aborted {item}", file=sys.stderr)
  print(item)
  EOF
  )
  test -n "$ABORTED"
  control-agent-server api GET "/api/conversations/$AB" --check execution_status eq paused
  control-agent-server conversation events "$AB" --kinds InterruptEvent --expect-count 1
  control-agent-server conversation events "$AB" --contains "$ABORTED" --expect-count 0
  control-agent-server state grep 'Count from 1 to 3000' --glob "server/workspace/conversations/${AB//-/}/**/*"
  control-agent-server state grep "$ABORTED" --glob "server/workspace/conversations/${AB//-/}/**/*" --expect-none
  control-agent-server ws listen "/sockets/session/$AB" --query after_seq=-1 --duration 3 --expect-kind durable:InterruptEvent \
    --expect-no-kind item_started --expect-no-kind delta --expect-no-kind item_aborted --save "F07.item-aborted/replay-$AB"
  control-agent-server state cat "evidence/F07.item-aborted/replay-$AB.json" --not-contains "$ABORTED"
  ```
  捕获显示`item_started`，然后是该项的`delta`帧（`order`0, 1, ..., `kind`推理或文本），直到中断，然后是恰好一个
  `item_aborted`与`item_id`和`attempt`和`reason`相同
  `cancelled`，该项目仅此而已； 运行是 `paused` 与 1
  `InterruptEvent`. 已 abort 的 id 在 no  已持久化事件（搜索，以及硬盘上的对话文件，这些文件确实包含提示词) 并且在没有持久帧的情况下，完整的回放包含 `InterruptEvent` 但没有进展帧。
- **超大事件 (`F07.frame-too-large`)。**在 REST 上附加 5 MiB 条消息，然后重播它。
  ```sh
  BIG=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures"
  python3 -c 'import json, sys; json.dump({"role": "user", "content": [{"type": "text", "text": "QA_F07_BIG " + "x" * (5 * 1024 * 1024)}], "run": False}, open(sys.argv[1], "w"))' "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-5mib.json"
  control-agent-server api POST "/api/conversations/$BIG/events" --json-file "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-5mib.json" --expect 200 --quiet
  control-agent-server api GET "/api/conversations/$BIG/events/count" --check . eq 3
  control-agent-server ws listen "/sockets/session/$BIG" --query after_seq=-1 --duration 10 --expect-close 1013 --expect-frames 2 --save "F07.frame-too-large/replay-$BIG"
  control-agent-server state cat "evidence/F07.frame-too-large/replay-$BIG.json" --check summary.close.reason eq frame_too_large \
    --check frames.2.frame.seq eq 0
  control-agent-server api GET "/api/conversations/$BIG/events/count" --query body=QA_F07_BIG --check . eq 1
  control-agent-server ws listen "/sockets/session/$BIG" --query after_seq=1 --duration 3 --expect-open --expect-frames 3 --save "F07.frame-too-large/skip-$BIG"
  control-agent-server state cat "evidence/F07.frame-too-large/skip-$BIG.json" --check frames.2.frame.seq eq 2 --check frames.3.frame.type eq transient
  ```
  重播 `seq` 0 结束于 `frame_too_large` 1013 在第 MiB 个事件。 REST 仍然发现它（一个体过滤计数为1的） 搜索会打印出所有 5 MiB，而 `after_seq=1` 跳过它并重播 `seq` 2。
- **阅读器停滞 (`F07.slow-consumer`)。**构建大约 47 MiB 条历史记录（十二条 3.9 MiB 消息，每条消息在 4 MiB 帧上限下），然后连接
  with `after_seq=-1` from a raw socket with a 64 KiB receive window that
  停止读取 5 秒。 CLI 总是读取，因此 stdlib 程序会进行握手并扫描到达的关闭帧。
  ```sh
  SLOW=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures"
  python3 -c 'import json, sys; json.dump({"role": "user", "content": [{"type": "text", "text": "QA_F07_SLOW " + "y" * 4089000}], "run": False}, open(sys.argv[1], "w"))' "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-3m9.json"
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    control-agent-server api POST "/api/conversations/$SLOW/events" --json-file "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-3m9.json" --expect 200 --quiet
  done
  control-agent-server api GET "/api/conversations/$SLOW/events/count" --check . eq 25
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-stalled-reader.py" <<'EOF'
  import base64, json, os, socket, sys, time
  from urllib.parse import urlparse

  server = urlparse(os.environ["AGENT_SERVER_URL"])
  cid, pause = sys.argv[1], float(sys.argv[2])
  sock = socket.socket()
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)  # before connect: a small window
  sock.connect((server.hostname, server.port))
  key = base64.b64encode(os.urandom(16)).decode()
  sock.sendall(
      f"GET /sockets/session/{cid}?after_seq=-1 HTTP/1.1\r\nHost: {server.netloc}\r\n"
      f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
      "Sec-WebSocket-Version: 13\r\n\r\n".encode()
  )
  head = b""
  while b"\r\n\r\n" not in head:
      head += sock.recv(1)
  assert b" 101 " in head.split(b"\r\n", 1)[0], head
  auth = json.dumps({"type": "auth", "session_api_key": os.environ["SESSION_API_KEY"]}).encode()
  mask = os.urandom(4)
  size = bytes([0x80 | len(auth)]) if len(auth) < 126 else bytes([0xFE]) + len(auth).to_bytes(2, "big")
  sock.sendall(b"\x81" + size + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(auth)))
  time.sleep(pause)  # stop reading while the server replays the history
  close = b"\x88\x0f\x03\xf5slow_consumer"  # close frame: code 1013, reason slow_consumer
  data = bytearray()
  sock.settimeout(20)
  try:
      while chunk := sock.recv(1 << 20):
          data += chunk
          if close in data[-(len(chunk) + len(close)):]:
              break
  except TimeoutError:
      pass
  print("bytes before the close frame:", len(data))
  assert close in data, "no 1013 slow_consumer close frame"
  print("QA_OK close 1013 slow_consumer")
  EOF
  control-agent-server exec --timeout 120 --expect-output 'QA_OK close 1013 slow_consumer' --save "F07.slow-consumer/stalled-$SLOW" -- python3 "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-stalled-reader.py" "$SLOW" 5
  control-agent-server ws listen "/sockets/session/$SLOW" --query after_seq=23 --count 3 --duration 20 --expect-open --save "F07.slow-consumer/resume-$SLOW"
  control-agent-server state cat "evidence/F07.slow-consumer/resume-$SLOW.json" --check frames.1.frame.through_seq eq 24 \
    --check frames.2.frame.seq eq 24 --check frames.3.frame.type eq transient
  ```
  停滞的读者接收了一些兆字节，然后是帧1013
  `slow_consumer`. 然后，正常客户端从同一个对话中的光标处继续，获取最后的事件，`seq` 24（这是一个小的状态更新，因此证据保持较小）。
- **订阅者上限 (`F07.subscriber-limit`)。**从一个程序一次为一个对话打开 55 个会话套接字，关闭它们，然后再次连接。
  ```sh
  LIM=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures"
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-many-sockets.py" <<'EOF'
  import asyncio, json, os, sys
  from websockets.asyncio.client import connect
  from websockets.exceptions import ConnectionClosed

  url = os.environ["AGENT_SERVER_URL"].replace("http", "ws", 1) + "/sockets/session/" + sys.argv[1]
  count = int(sys.argv[2])
  auth = json.dumps({"type": "auth", "session_api_key": os.environ["SESSION_API_KEY"]})

  async def attach(results, held):
      ws = await connect(url)
      await ws.send(auth)
      try:
          frame = json.loads(await asyncio.wait_for(ws.recv(), 15))
          results.append(("open", frame["type"]))
          held.append(ws)
      except ConnectionClosed as exc:
          results.append(("closed", exc.rcvd.code if exc.rcvd else None, exc.rcvd.reason if exc.rcvd else None))

  async def main():
      results, held = [], []
      await asyncio.gather(*(attach(results, held) for _ in range(count)))
      opened = [r for r in results if r[0] == "open"]
      refused = [r for r in results if r[0] == "closed"]
      print(f"opened={len(opened)} refused={len(refused)} {sorted(set(refused))}")
      assert {r[1] for r in opened} == {"sync"}, opened
      assert 40 <= len(opened) <= 50 and len(opened) + len(refused) == count
      assert set(refused) == {("closed", 1013, "Too many connections for this conversation")}, refused
      for ws in held:
          await ws.close()
      for _ in range(20):  # the server unsubscribes as each close lands
          async with connect(url) as ws:
              await ws.send(auth)
              try:
                  if json.loads(await asyncio.wait_for(ws.recv(), 15))["type"] == "sync":
                      print("QA_OK slot freed")
                      return
              except ConnectionClosed:
                  await asyncio.sleep(0.5)
      raise SystemExit("no slot freed")

  asyncio.run(main())
  EOF
  control-agent-server exec --timeout 120 --expect-output 'QA_OK slot freed' --save "F07.subscriber-limit/many-$LIM" -- .venv/bin/python "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f07-many-sockets.py" "$LIM" 55
  ```
  在40到50个套接字之间，`sync`（在基准运行中为49个）有一个套接字保持订阅，其余的套接字都以1013关闭
  `Too many connections for this conversation`，一旦它们关闭，新的套接字就会被接纳。
- **删除会关闭套接字 (`F07.deleted-close`)，已知错误。**应该告知附加到被删除的对话的客户。 在 DELETE 之前订阅后台捕获（其 `full_state` 快照到达并且已打开）； 在判断打开捕获之前，DELETE、REST 上的 404 和新会话套接字的 4004 都成功。
  ```sh
  DEL=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server ws start "/sockets/session/$DEL" --name "del-$DEL" --settle 2 --duration 60
  control-agent-server ws read "del-$DEL" --wait 10 --kinds transient:ConversationStateUpdateEvent --contains '"key": "full_state"' --expect-min 1 --expect-open
  control-agent-server api DELETE "/api/conversations/$DEL" --expect 200 --save "F07.deleted-close/delete-$DEL"
  control-agent-server api GET "/api/conversations/$DEL" --expect 404
  control-agent-server ws listen "/sockets/session/$DEL" --duration 5 --expect-close 4004 --expect-frames 0
  control-agent-server ws stop "del-$DEL" --save "F07.deleted-close/socket-$DEL" | control-agent-server assert --check close.code exists  # bug: value.opened eq True && value.stopped eq 停止 && value.close 缺失
  ```
  正确行为：服务器关闭已打开的套接字（使用任何关闭代码）
  while it deletes the conversation; `EventService.close()` awaits
  `PubSub.close()` 在 DELETE 应答之前，因此在捕获停止时已结束。 今天捕获仍然打开，没有关闭帧（`close: null`），之后也没有任何内容，尽管REST返回404，一个新的套接字返回4004：`PubSub.close()`调用
  `Subscriber.close()`，其中`_SessionSubscriber`没有实现(`pub_sub.py`，`session_socket.py`)，所以客户端永远等待。 同样的错误使遗留事件套接字保持打开状态（`F06.ws-delete-close`）。

<a id="gotchas"></a>

## 陷阱

- SDK 和 TypeScript 客户端都尚未使用此套接字，因此这里的回归不会破坏任何已发货消费者的测试； 只有这些食谱和
  `tests/agent_server/test_session_socket.py` 通知。
- 的 CLI 命名会话帧 `<type>:<EventKind>` 当它携带事件(`durable:MessageEvent`, `durable:ConversationStateUpdateEvent`,
  `transient:ConversationStateUpdateEvent`)，否则为裸 `type` (`sync`, `item_started`, `delta`, `item_aborted`, `error`)。 `--kinds`,
  `--expect-kind` 和 `--until-kind` 与该名称完全匹配，所以一个裸露的
  `durable` 不匹配任何内容。 使用框架的紧凑型 JSON 上的 `--until FIELD=VALUE` (`event.key=execution_status`) 或 `--contains` 进一步缩小范围（`"seq": 5, "event": {"id": "..."}`，服务器发送的关键顺序）。
- 已保存捕获的 `frames` 列表包含每个条目，而不仅仅是接收到的
  帧：打开的套接字的每次捕获都以 `opened` 开头
  条目 (`frames.0`)、`ws listen --save` 将 `--send` 帧放在下一个并以 `ended` 或 `closed` 条目结束，`ws stop --save` 捕获以 `stopped` 条目结束。 因此第一个接收到的帧是`frames.1`，或者稍后发送帧时。 使用 `ws listen --expect-frames N`（或 `summary.frames`）对接收到的帧进行计数，或检查 `frames.N.direction ne received`；
  `frames len-eq` 因额外条目而关闭。 `state cat --contains` 读取已保存的文件，该文件缩进 JSON（`"seq": 5,` 在其自己的行上），因此将紧凑框架 JSON 与 `ws read|stop --contains` 匹配。
- 没有初始消息的对话根本没有事件，所以它
  `sync`没有`through_seq`； 第一个 `POST .../events` 写的是
  消息之前的 `SystemPromptEvent` (seq 0)。 服务器忽略
  `POST /api/conversations` 上的 `initial_message.run`：初始消息始终运行智能体，即使有 `"run": false`（F04 的已知错误
  `F04.create-initial-message-run-false`). 因此，CLI 的 `conversation start --prompt ... --no-run` 创建了没有 1 的对话，并向提示词附加了 `POST .../events` 和 `"run": false`，就像这里的测试夹具手动所做的那样。
- 在套接字上发送的消息始终运行：`Message` 忽略未知字段，因此
  `"run": false` 在帧中被无声丢弃。 如果不运行此套接字，则无法进行追加。
- 冗余身份验证帧将被忽略，无论其携带什么密钥； 仅检查第一帧（或旧查询/标头键）。
- `error` 帧是关于套接字的，而不是已持久化，并且连接在它们之后保持打开状态。 除 `user` 之外的 `role` 被拒绝
  `LocalConversation.send_message`中的`assert`（代码`AssertionError`）； 下
  `python -O` 该检查将消失（请参阅 F06 中的 REST 变体）。
- 4 MiB 帧上限和 16 MiB 每个连接写入预算在 `session_protocol.py` 中标记为临时。 任何超过4 MiB 的事件都无法通过这个套接字发送：每条到达它的重播都会以1013关闭，因此客户端必须跳过它并从REST重新读取。
- 是否停滞的读者触发了16 MiB 预算取决于内核缓冲区的大小：服务器的套接字发送缓冲区（）`net.ipv4.tcp_wmem` 最大值为4 MiB 加上一个正在飞行的帧和一个 uvicorn 的传输层。 该食谱大约使用了47 MiB 历史的一部分和64 KiB 客户端窗口应保持高于那个水平。 在具有更大发送缓冲区的主机上，增加消息计数。 A `websockets` 客户端是一个劣质的缓冲区：即使在读取过程中，它也一直读取到自己的缓冲区 `max_queue=1`.
- 因连接而丢失的持久帧（超大、缓慢的消费者）不会
  丢失：重新连接，并将 `after_seq` 设置为最后收到的 `seq`； 直播
  帧按 `seq` 顺序 (`F07.live-order`) 到达。 根据设计，进度帧永远不会重播。
- 开放的流式传输项目以 `durable` 框架结束，其
  `event.id`是其`item_id`或与一个`item_aborted`。 中止 `reason` 是中断 (`F07.item-aborted`) 的 `cancelled`，异常的
  class name when the step fails mid-stream (a provider error), and
  `no_durable_event` 当步骤结束但未声明 id (`stream_context.py`) 时。 从未产生增量的项目从未被打开，因此它根本没有框架。
- 每个对话的订阅者上限为 50 人，并与旧版共享
  `/sockets/events/{id}` 套接字和内部订阅者（autotitle，Webhook）； 基线对话中已占用一个时段。 流进度扇出有自己的上限 50； 当它已满时，套接字仍会打开，但不会键入帧。
- 源可以发送的其他接近的代码，但这些食谱无法到达：1013 `credential_binding_activation_required`（一个凭据绑定等待中的对话）和1011 `subscribe_failed`（订阅调用引发）。
- `ws start` 等待 `--settle` 秒（默认 1）以进行捕获连接； 在已加载的机器上，在触发操作之前使用 `--settle 2` 或更多，否则捕获会错过它。 在停止捕获之前，使用 `ws read|stop --wait S` 和 `--kinds`/`--contains` 过滤器等待所需的帧； 已经显示事件的 REST 视图并不意味着帧已到达捕获。
- 在日志的最后 `seq` 以上没有 `after_seq` 被拒绝：`sync` 用较小的 `through_seq` 重放它，没有重放，但后来的事件仍然以实时方式到达，尽管它们的 `seq` 不在光标上方。 客户端应将 `from_seq > through_seq` 视为陈旧游标。
- `api` 将请求体的整个内容输出到结果中，因此上述多兆字节的POSTs使用`--quiet`来保持映射运行的转录较小（`--expect`和`--check`仍然能看到请求体）。 `--max-chars` 只修剪非JSON 响应体。
