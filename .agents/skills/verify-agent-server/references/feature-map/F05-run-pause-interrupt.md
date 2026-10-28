<a id="run-pause-interrupt-and-status-transitions"></a>

# 运行、暂停、中断和状态转换

如何一个智能体或其主机驱动它智能体现有对话的循环：开始于待处理输入（`/run`, 该端点立即返回并后台运行，在下一步边界处停止`/pause`) 或取消飞行中的模型或工具调用 (`/interrupt`), and follow `execution_status` 通过
对话、状态过滤器和事件套接字上的 `idle`、`running`、`paused`、`finished`、`error` 和 `stuck`。 它还涵盖了消费者在边缘看到的内容：一个同时运行的第二运行（409），服务器的运行容量（429），停止循环智能体的每运行限制（检测滞留和 `max_iterations`），未知的ID，以及在服务器优雅停止或被杀掉时仍在运行的会话。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/conversation_service.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/api.py`、`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`、`openhands-sdk/openhands/sdk/conversation/state.py`

需求：`llm`、`tmux`

发射：`--config-json '{"max_concurrent_runs": 1}'`

路线：`POST /api/conversations/{conversation_id}/run`，
`POST /api/conversations/{conversation_id}/pause`,
`POST /api/conversations/{conversation_id}/interrupt`

<a id="sub-features"></a>

## 子功能

- `F05.run-queued`：带有`run: false`的消息离开会话`idle`； `POST /run` 立即返回 200，智能体在 DeepSeek 闪存上运行，经过 `running` 到 `finished`，两个转换都推送到事件套接字上。
- `F05.run-finished-noop`: `POST /run` 在没有新输入的情况下，`finished` 对话返回 200 并立即结束：没有 `execution_status` 换，仍然 `finished`，没有新的事件（没有模型调用）。
- `F05.run-new-input`：新的用户消息将 `finished` 对话移回 `idle`，`POST /run` 再次将其运行到 `finished`。
- `F05.pause-idle`：暂停空闲会话返回 200，在 GET 上报告 `paused`、状态搜索和计数以及事件套接字，并保留 1 `PauseEvent`。
- `F05.pause-repeat`：再次暂停 `paused` 对话将返回 200 并且不添加第二个 `PauseEvent`。
- `F05.run-resume-paused`：`POST /run` 通过 `running` 到 `finished` 恢复 `paused` 对话。
- `F05.interrupt-idle`：没有任何运行的中断回退到暂停：`paused`、一个 `PauseEvent`、无 `InterruptEvent`。
- `F05.run-error`：模型提供程序无法访问的运行以 `error` 和 `ConversationErrorEvent`（也在事件套接字上推送）结束，并由 `status=error` 列出。
- `F05.pause-terminal`：暂停并中断 `finished` 或 `error` 对话返回 200，并且既不更改状态也不更改事件日志。
- `F05.run-error-responsive`：失败的运行不会停止服务器：在处理错误时其他请求继续应答。
- `F05.unknown-id-run`: `POST /run` 对于未知的 id 返回 404。
- `F05.unknown-id-pause`：`POST /pause` 和 `POST /interrupt` 在未知 id 上返回记录的 404。
- `F05.control-errors`所有三个路由都返回401，有的没有，有的有错误的会话密钥，422表示无效的ID，他们所针对的闲聊仍然没有改变（仍然） `idle`, no `PauseEvent`).
- `F05.run-conflict`：`POST /run` 当运行处于活动状态时返回 409 `Conversation already running...`，并且活动运行继续进行，无需第二次模型调用。
- `F05.pause-running`：长时间模型调用期间暂停立即返回200； 事件套接字、状态搜索和事件日志显示 `paused` 和 `/run` 保持 409，而该步骤仍在进行中。
- `F05.pause-running-get`：在长时间模型调用期间暂停后，`GET /api/conversations/{id}` 和 `base_state.json` 与其他视图一样报告 `paused`。
- `F05.pause-running-release` 中断正在进行中的暂停对话（`InterruptEvent`），GET 捕获`paused`，运行槽重新可用（需要该槽的创建成功）。
- `F05.interrupt-running`：中断在服务器的 5 秒等待时间内取消挂起模型调用：200、`paused`、`InterruptEvent` 和无 `PauseEvent`，推送到事件套接字上。
- `F05.run-after-interrupt`：中断后立即接受`POST /run`，恢复运行到`finished`。
- `F05.pause-tool-step` 在一个工具调用运行时暂停，让该步骤完成（其观测结果被记录），然后在下一个模型调用之前停止循环：`paused`，`PauseEvent`，一个模型请求。
- `F05.interrupt-tool-call`：工具调用运行时中断，立即返回：`paused`、`InterruptEvent`、未完成调用的`AgentErrorEvent`（相同`tool_call_id`）和无观测结果； 恢复的运行将该错误作为工具结果发送到模型并完成。
- `F05.run-capacity`：当 `max_concurrent_runs` 1 时，第二个对话上的 `POST /run` 返回 429，而第一个对话保留该槽，将其保留为 `idle`，并在第一个对话中断后成功。
- `F05.stuck-detected`: with `stuck_detection` 在默认情况下，一个重复的模型运行将重复工具调用 ends `stuck` 在执行了四组完全相同的行动/观察对（四次模型调用）之后，没有 `ConversationErrorEvent`; GET, `status=stuck` 搜索、计数，以及事件socket说 `stuck`.
- `F05.stuck-rerun`：`POST /run` 在没有新输入的 `stuck` 对话中返回 200，转到 `running`，然后直接返回 `stuck`，无需模型调用。
- `F05.stuck-new-input`：新的用户消息将 `stuck` 对话移至 `idle`，`POST /run` 再次将其运行至 `finished`。
- `F05.max-iterations-stop`：使用 `max_iterations: 6` 和 `stuck_detection: false` 创建的会话，其模型永远不会完成，将进行 6 次模型调用（超过卡住阈值），并以 1 个 `ConversationErrorEvent` `code: MaxIterationsReached` 命名限制结束 `error`，在 REST 和事件套接字上，从不 `stuck`。
- `F05.max-iterations-resume`：`POST /run` 在 `MaxIterationsReached` 被接受并获得六个模型调用的新预算（第二个 `MaxIterationsReached`）后，一旦模型调用 `finish`，下一次运行就会结束 `finished`。
- `F05.restart-running-graceful`：正常重启时运行的对话返回 `paused`，带有 `PauseEvent` 和 `InterruptEvent`。
- `F05.restart-keeps-status`：`finished`、`paused` 和 `error` 状态在重新启动后保持不变。
- `F05.restart-hard-running`当服务器运行时的对话 SIGKILLed 回来 `error` 在下次启动时， `/run` 继续它。
- `F05.pause-running-crash`：模型调用期间接受的暂停在 SIGKILL 后继续存在：对话返回 `paused`，正如其已持久化 `PauseEvent` 和状态更新所说，而不是 `error`。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `POST /api/conversations/{conversation_id}/run`（无正文）。 一旦安排后台运行，就返回 200 `{"success": true}`； 404 表示未知 id（或另一个活动实例持有其租约的 id）； 409
  `Conversation already running. Wait for completion or pause first.`; 429
  `Conversation run limit reached. Retry the request later.`; 409
  `{"detail": "credential_binding_activation_required", "retryable": true}` 当所需的凭据绑定缺失时（凭据系列）；服务器关闭时返回 400。 `/run` 还恢复 `paused` 和 `error` 对话（`stuck` 仅在新输入后进行）并批准等待确认的操作。
- REST: `POST /api/conversations/{conversation_id}/pause` 和
  `POST /api/conversations/{conversation_id}/interrupt`（无正文），200
  `{"success": true}`； 404 表示未知 ID。 暂停翻转 `idle` 或
  将 `running` 和 `paused` 后添加 `PauseEvent`。 当前步骤首先完成。 中断取消正在进行的异步运行（`InterruptEvent`，未完成操作的合成错误观测结果），并在没有任何运行时回退到暂停。
- 第二种观点（其他家族拥有，此处用作证明）：
  `GET /api/conversations/{conversation_id}` (`execution_status`),
  `GET /api/conversations/search` 和 `/count` 以及 `status`，
  `GET /api/conversations/{conversation_id}/events/count` 具有完全限定的 `kind`、`agent_final_response` 和事件套接字
  `/sockets/events/{conversation_id}`：`ConversationStateUpdateEvent` 帧，`key` `execution_status`（加上连接时和每次运行后的 `full_state` 快照）、`PauseEvent`、`InterruptEvent`、`ConversationErrorEvent`。
- 开始运行的其他方式（其他系列）：`initial_message` on create and
  `POST /api/conversations/{conversation_id}/events` 与 `"run": true`。
- SDK: `RemoteConversation.run(blocking=True, poll_interval, timeout)` 条帖子
  `/run`（409 被记录并视为“已在运行”）并轮询直到运行结束； `RemoteConversation.pause()` 和 `interrupt()` 发布了另外两条路线 (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`)。
  `LocalConversation.run()/arun()/pause()/interrupt()` 实施过程中的转换。
- TypeScript客户端：`ConversationClient.runConversation`，
  `pauseConversation`、`interruptConversation` (`clients/typescript/src/client/conversation-client.ts`) 和
  `RemoteConversation.run()` / `pause()` (`clients/typescript/src/conversation/remote-conversation.ts`).
- 配置：`max_concurrent_runs`（`OH_MAX_CONCURRENT_RUNS`，默认 10）上限并发运行和会话创建； 用`launch --config-json`设置。
- 每会话运行限制，设置为创建时的 F04，读回时的 GET：`max_iterations`（默认为 500，`ge=1`：智能体次运行，然后 `error`，`ConversationErrorEvent` `MaxIterationsReached`）
  `stuck_detection`（默认 True：重复模式结束运行
  `stuck`). SDK的`ConversationSettings.create_request()`将存储的`conversation_settings.max_iterations`复制到该字段中； 服务器本身不会在创建时读取存储的设置。
- 下面的食谱使用 REST 到 `api`，事件套接字到 `ws start`（在操作之前打开），真正的 DeepSeek flash 为每个快乐路径运行，
  `fixture llm-stub` 对于挂起的模型调用（按需在 `running` 中保持运行的唯一方法），对于运行慢速命令的精确 `terminal` 调用（在工具调用中保持运行的唯一方法）或相同
  `think` 一直调用（唯一的方法在需要时让模型循环，对于卡住的检测器和迭代次数限制），以及一个不可达的 `base_url`（提供者错误）。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 启动运行时设置了该系列的 `Launch:` 标志 (`launch --new --config-json '{"max_concurrent_runs": 1}'`)、`doctor` ok 和 `$DEEPSEEK_API_KEY`； 下面的块保存 DeepSeek 配置文件。 在每个运行槽中，每发开始运行的子弹必须找到空闲的槽位，因此子弹严格按顺序运行，每个持有槽位的子弹在结束前释放它（中断）。 `F05.run-capacity` 取决于 1 的极限。
- `tmux` 表示两个工具调用项目符号 (`F05.pause-tool-step`,
  `F05.interrupt-tool-call`)，其智能体具有 `terminal` 工具。 其他每个智能体都有 `tools: []`，仅保留内置 `finish` 和
  `think` 工具。 没有浏览器。
- 以下块创建了以下内容：未知的 id `$NOPE`，`events/count` 和 `events/search` 过滤的完全合格事件类型，以及一个不可达的智能体（其提供者不可达 `$OFFLINE_AGENT`
  `127.0.0.1:9`)，一个将每个调用挂起 300 秒的 `llm-stub` (`$HANG_AGENT`)，第二个挂起的存根，`F05.run-after-interrupt` 后来重写为调用 `finish` (`$RESUME_AGENT`)，一个模型要求的存根
  `terminal` `sleep 6 && echo QA_F05_STEP_DONE` (`$STEP_AGENT`)，一个存根，其模型要求 `terminal` `sleep 30`，`F05.interrupt-tool-call` 稍后重写以调用 `finish` (`$TOOL_AGENT`)，两个存根，其模型调用
  `think` 每次调用都采用相同的思考方式，随后的分列表示为调用 `finish` (`$LOOP_AGENT` 用于检测滞留，`$CAP_AGENT` 用于迭代上限），以及所有十三个对话，没有初始消息（初始消息总是启动一个运行，创建对话需要一个免费的运行槽）：`A`、`B`、`C`、`Q` 在 DeepSeek 热启动、`E` 离线、`P`
  `G` 和 `K` 在悬垂钩上，`R` 在可恢复钩上，`W` 在步骤钩上，`T` 在工具钩上，`L` 在循环钩上，以及 `M` 在带有 `max_iterations: 6` 和 `stuck_detection: false` 的帽钩上。 一切开始`idle`。

```sh
control-agent-server llm preset deepseek
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
PAUSE_KIND=openhands.sdk.event.user_action.PauseEvent
INTERRUPT_KIND=openhands.sdk.event.user_action.InterruptEvent
ERROR_KIND=openhands.sdk.event.conversation_error.ConversationErrorEvent
ACTION_KIND=openhands.sdk.event.llm_convertible.action.ActionEvent
OBSERVATION_KIND=openhands.sdk.event.llm_convertible.observation.ObservationEvent
AGENT_ERROR_KIND=openhands.sdk.event.llm_convertible.observation.AgentErrorEvent
OFFLINE_AGENT='{"llm": {"model": "openai/qa-offline", "api_key": "qa-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": []}'
HANG=$(control-agent-server fixture llm-stub --name qa-f05-hang --step hang:300 --print-path)
HANG_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG/v1\", \"num_retries\": 0}, \"tools\": []}"
RESUME=$(control-agent-server fixture llm-stub --name qa-f05-resume --step hang:300 --print-path)
RESUME_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$RESUME/v1\", \"num_retries\": 0}, \"tools\": []}"
STEP=$(control-agent-server fixture llm-stub --name qa-f05-step --step 'tool:terminal:{"command":"sleep 6 && echo QA_F05_STEP_DONE"}' --print-path)
STEP_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$STEP/v1\", \"num_retries\": 0}, \"tools\": [{\"name\": \"terminal\"}]}"
TOOL=$(control-agent-server fixture llm-stub --name qa-f05-tool --step 'tool:terminal:{"command":"sleep 30"}' --print-path)
TOOL_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$TOOL/v1\", \"num_retries\": 0}, \"tools\": [{\"name\": \"terminal\"}]}"
LOOP=$(control-agent-server fixture llm-stub --name qa-f05-loop --step 'tool:think:{"thought":"QA_F05_LOOP"}' --print-path)
LOOP_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$LOOP/v1\", \"num_retries\": 0}, \"tools\": []}"
CAP=$(control-agent-server fixture llm-stub --name qa-f05-cap --step 'tool:think:{"thought":"QA_F05_CAP"}' --print-path)
CAP_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$CAP/v1\", \"num_retries\": 0}, \"tools\": []}"
A=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
B=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
C=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
Q=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
E=$(control-agent-server conversation start --body-json "{\"agent\": $OFFLINE_AGENT}" --no-autotitle --print-id)
P=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
G=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
K=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
R=$(control-agent-server conversation start --body-json "{\"agent\": $RESUME_AGENT}" --no-autotitle --print-id)
W=$(control-agent-server conversation start --body-json "{\"agent\": $STEP_AGENT}" --no-autotitle --print-id)
T=$(control-agent-server conversation start --body-json "{\"agent\": $TOOL_AGENT}" --no-autotitle --print-id)
L=$(control-agent-server conversation start --body-json "{\"agent\": $LOOP_AGENT}" --no-autotitle --print-id)
M=$(control-agent-server conversation start --body-json "{\"agent\": $CAP_AGENT, \"max_iterations\": 6, \"stuck_detection\": false}" --no-autotitle --print-id)
control-agent-server api GET /api/conversations/count --query status=idle --check . eq 13
```

- **在真实模型上运行排队输入 (`F05.run-queued`)。**附加一条消息而不运行，然后在事件套接字侦听时使用 `/run` 启动循环。
  ```sh
  control-agent-server conversation send "$A" --text 'Reply with the single word ok, then finish.' --no-run
  control-agent-server api GET "/api/conversations/$A" --check execution_status eq idle
  NA=$(control-agent-server api GET "/api/conversations/$A/events/count" --query source=agent --field .)
  control-agent-server ws start "/sockets/events/$A" --name f05-a-run --duration 300
  control-agent-server api POST "/api/conversations/$A/run" --expect 200 --check success eq true --expect-max-ms 2000 --save F05.run-queued/run
  control-agent-server conversation wait "$A" --until finished --timeout 180
  control-agent-server api GET "/api/conversations/$A" --check execution_status eq finished --save F05.run-queued/after
  control-agent-server api GET "/api/conversations/$A/events/count" --query source=agent --check . gt "$NA"
  control-agent-server ws read f05-a-run --contains '"key": "execution_status", "value": "finished"' --wait 30
  control-agent-server ws stop f05-a-run --contains '"key": "execution_status", "value": "running"' --save F05.run-queued/frames
  ```
  在追加后，状态保持为`idle`，`/run`返回200
  `{"success": true}` 在 2 秒内（它只安排运行），等待报告转换 `running`、`finished`，模型的答案添加了智能体事件（`finish` 调用或简单回复，无论模型选择哪个），并且套接字推送 `execution_status` `running` 和 `finished`。
- **无所事事地奔跑(`F05.run-finished-noop`)。**证明是不存在的，因此套接字首先证明后台运行已结束：服务器在连接时推送 `full_state` 快照，并在运行结束时推送另一个快照。
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$A/events/count" --field .)
  control-agent-server ws start "/sockets/events/$A" --name f05-a-noop --duration 300
  control-agent-server api POST "/api/conversations/$A/run" --expect 200 --check success eq true --save F05.run-finished-noop/run
  control-agent-server ws read f05-a-noop --contains '"key": "full_state"' --expect-min 2 --wait 30
  control-agent-server ws stop f05-a-noop --contains '"key": "execution_status"' --expect-none --save F05.run-finished-noop/frames
  control-agent-server api GET "/api/conversations/$A/events/count" --check . eq "$N" --save F05.run-finished-noop/count
  control-agent-server api GET "/api/conversations/$A" --check execution_status eq finished
  ```
  `/run` 返回 200，运行的结束 `full_state` 帧到达，之前没有单个 `execution_status` 帧，事件计数不变，状态仍为 `finished`：没有新输入的已完成对话在调用模型之前退出循环。
- **完成(`F05.run-new-input`)后的新输入。**用户消息重置
  `finished`至`idle`； `/run` 拾起它。
  ```sh
  control-agent-server conversation send "$A" --text 'Reply with the single word again, then finish.' --no-run
  control-agent-server api GET "/api/conversations/$A" --check execution_status eq idle --save F05.run-new-input/idle
  NA=$(control-agent-server api GET "/api/conversations/$A/events/count" --query source=agent --field .)
  control-agent-server api POST "/api/conversations/$A/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$A" --until finished --timeout 180
  control-agent-server api GET "/api/conversations/$A/events/count" --query source=agent --check . gt "$NA" --save F05.run-new-input/agent-events
  ```
  在追加后，状态显示为`idle`，在第二次运行后，状态显示为`finished`，追加了智能体个事件，以供新的答案。
- **暂停空闲对话 (`F05.pause-idle`)。** `B` 有待处理的输入并且从未运行。
  ```sh
  control-agent-server conversation send "$B" --text 'Reply with the single word ok, then finish.' --no-run
  control-agent-server ws start "/sockets/events/$B" --name f05-b-pause --duration 300
  control-agent-server api POST "/api/conversations/$B/pause" --expect 200 --check success eq true --save F05.pause-idle/pause
  control-agent-server api GET "/api/conversations/$B" --check execution_status eq paused --save F05.pause-idle/get
  control-agent-server api GET "/api/conversations/$B/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET /api/conversations/search --query status=paused --check items contains "$B"
  control-agent-server api GET /api/conversations/count --query status=paused --check . eq 1
  control-agent-server ws stop f05-b-pause --contains '"key": "execution_status", "value": "paused"' --save F05.pause-idle/frames
  control-agent-server ws read f05-b-pause --expect-kind PauseEvent
  ```
  每一张视图都同意 `paused`：GET，`search`/`count`，`status=paused`，`PauseEvent`，已持久化，`execution_status`
  `PauseEvent` 框架。
- **暂停两次 (`F05.pause-repeat`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$B/pause" --expect 200 --check success eq true --save F05.pause-repeat/pause
  control-agent-server api GET "/api/conversations/$B/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$B" --check execution_status eq paused
  ```
  第二个暂停被接受，但没有改变任何东西：仍然有一个 `PauseEvent`。
- **恢复暂停的对话 (`F05.run-resume-paused`)。**
  ```sh
  NA=$(control-agent-server api GET "/api/conversations/$B/events/count" --query source=agent --field .)
  control-agent-server ws start "/sockets/events/$B" --name f05-b-resume --duration 300
  control-agent-server api POST "/api/conversations/$B/run" --expect 200 --check success eq true --save F05.run-resume-paused/run
  control-agent-server conversation wait "$B" --until finished --timeout 180
  control-agent-server api GET "/api/conversations/$B/events/count" --query source=agent --check . gt "$NA" --save F05.run-resume-paused/agent-events
  control-agent-server ws read f05-b-resume --contains '"key": "execution_status", "value": "finished"' --wait 30
  control-agent-server ws stop f05-b-resume --contains '"key": "execution_status", "value": "running"' --save F05.run-resume-paused/frames
  ```
  暂停的对话会在 DeepSeek 硬盘（新的智能体事件）上运行，而套接字会显示 `running` 和 `finished`。
- **无任何运行的中断 (`F05.interrupt-idle`)。** `C` 空闲且无输入。
  ```sh
  control-agent-server api POST "/api/conversations/$C/interrupt" --expect 200 --check success eq true --save F05.interrupt-idle/interrupt
  control-agent-server api GET "/api/conversations/$C" --check execution_status eq paused
  control-agent-server api GET "/api/conversations/$C/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$C/events/count" --query kind=$INTERRUPT_KIND --check . eq 0 --save F05.interrupt-idle/interrupt-events
  ```
  中断回退到暂停：`paused`，一次`PauseEvent`，无
  `InterruptEvent`.
- **失败的运行 (`F05.run-error`)。** `E` 的提供者无法访问（连接被拒绝，重试否）。
  ```sh
  control-agent-server conversation send "$E" --text 'hi' --no-run
  control-agent-server ws start "/sockets/events/$E" --name f05-e-error --duration 300
  control-agent-server api POST "/api/conversations/$E/run" --expect 200 --check success eq true --save F05.run-error/run
  control-agent-server conversation wait "$E" --until error --timeout 120
  control-agent-server api GET "/api/conversations/$E/events/count" --query kind=$ERROR_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$E/events/search" --query kind=$ERROR_KIND \
    --check items.0.code exists --check items.0.detail exists --save F05.run-error/error-event
  control-agent-server api GET /api/conversations/search --query status=error --check items contains "$E"
  control-agent-server ws read f05-e-error --expect-kind ConversationErrorEvent --wait 30
  control-agent-server ws stop f05-e-error --contains '"key": "execution_status", "value": "error"' --save F05.run-error/frames
  ```
  `/run`仍然回答200（失败发生在后台）； 状态变为`error`，一个`ConversationErrorEvent`携带一个`code`（这里是`LLMServiceUnavailableError`）和一个`detail`、`status=error`列表
  `E`，套接字推送错误事件和 `error` 转换。
- **暂停和中断终端对话 (`F05.pause-terminal`)。**
  ```sh
  for CASE in "$A:finished" "$E:error"; do
    CID=${CASE%%:*}
    S=${CASE#*:}
    control-agent-server api GET "/api/conversations/$CID" --check execution_status eq "$S"
    N=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
    control-agent-server api POST "/api/conversations/$CID/pause" --expect 200 --check success eq true --save F05.pause-terminal/pause
    control-agent-server api POST "/api/conversations/$CID/interrupt" --expect 200 --check success eq true --save F05.pause-terminal/interrupt
    control-agent-server api GET "/api/conversations/$CID" --check execution_status eq "$S"
    control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$N"
  done
  ```
  `finished` 和 `error` 会话中都接受这两个调用，状态和事件计数都不会改变。
- ** 当运行失败时，响应 `F05.run-error-responsive`。** 重试 `E`，并继续探测 `/alive`，直到第二轮之后的第三轮
  `ConversationErrorEvent` 着陆（存储事件后记录故障）。 运行前的探针为阳性对照； 最后的断言是，故障期间没有探测花费了 1.5 秒（通常约为 100 毫秒）。
  ```sh
  NERR=$(control-agent-server api GET "/api/conversations/$E/events/count" --query kind=$ERROR_KIND --field .)
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 1500 --save F05.run-error-responsive/alive-before
  control-agent-server api POST "/api/conversations/$E/run" --expect 200
  SLOWEST=0
  AFTER=0
  for i in $(seq 1 60); do
    ALIVE=$(control-agent-server api GET /alive --auth none --expect 200 --timeout 60 --quiet)
    COUNT=$(control-agent-server api GET "/api/conversations/$E/events/count" --query kind=$ERROR_KIND --expect 200 --timeout 60)
    for OUT in "$ALIVE" "$COUNT"; do
      MS=$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["elapsed_ms"])')
      if [ "$MS" -gt "$SLOWEST" ]; then SLOWEST=$MS; fi
    done
    NOW=$(printf '%s' "$COUNT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["response"]["body"])')
    if [ "$NOW" -gt "$NERR" ]; then AFTER=$((AFTER + 1)); fi
    if [ "$AFTER" -ge 3 ]; then break; fi
  done
  test "$AFTER" -ge 3
  control-agent-server api GET "/api/conversations/$E" --check execution_status eq error --quiet --save F05.run-error-responsive/after
  echo "slowest probe while the run failed: $SLOWEST ms"
  control-agent-server assert --value "$SLOWEST" --check . le 1500
  ```
  预期：每个探测器在大约 100 毫秒内响应，使用默认控制台
  与 `LOG_JSON=true` 一样记录（Docker 图像的设置）。
  `_run_and_publish` 记录失败（“对话运行期间出错”
  `event_service.py`) 其回溯为纯文本而不是
  `exc_info`，因为默认的 Rich 控制台处理程序（`LOG_RICH_TRACEBACKS` 默认为 `openhands-sdk/openhands/sdk/logger/logger.py` 中的 True）将在事件循环上同步呈现链接 LLM 错误的丰富回溯，阻塞每个请求、套接字并运行大约 5 秒。
- **运行未知 ID (`F05.unknown-id-run`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$NOPE/run" --expect 404 --check detail eq 'Not Found' --save F05.unknown-id-run/run
  ```
  404 `{"detail": "Not Found"}`.
- **暂停或中断未知 ID (`F05.unknown-id-pause`)。**两个路由都在 OpenAPI 文档中声明 404“未找到项目”（并且没有 400），就像 `/run` 和 `GET /api/conversations/{id}` 一样。
  ```sh
  control-agent-server api GET /openapi.json --auth none --max-chars 200 \
    --check 'paths./api/conversations/{conversation_id}/pause.post.responses.404' exists \
    --check 'paths./api/conversations/{conversation_id}/interrupt.post.responses.404' exists
  control-agent-server api GET "/api/conversations/$NOPE" --expect 404
  control-agent-server api POST "/api/conversations/$NOPE/pause" --expect 404 --save F05.unknown-id-pause/pause
  control-agent-server api POST "/api/conversations/$NOPE/interrupt" --expect 404 --save F05.unknown-id-pause/interrupt
  ```
  OpenAPI文档和GET（404）是控制。 两者都返回 404 `{"detail": "Not Found"}`，就像 `/run` 对于相同的 id：处理程序在服务找不到对话时会抛出 404。
- **身份验证和格式错误的 ID (`F05.control-errors`)。**目标是 `Q`，即 `idle`，因此接受的暂停或中断会明显地将其翻转为
  `paused`.
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$Q/events/count" --field .)
  control-agent-server api POST "/api/conversations/$Q/run" --auth none --expect 401 --check detail eq Unauthorized --save F05.control-errors/run-no-key
  control-agent-server api POST "/api/conversations/$Q/pause" --auth none --expect 401 --check detail eq Unauthorized --save F05.control-errors/pause-no-key
  control-agent-server api POST "/api/conversations/$Q/interrupt" --auth none --expect 401 --check detail eq Unauthorized --save F05.control-errors/interrupt-no-key
  control-agent-server api POST "/api/conversations/$Q/run" --auth bad --expect 401
  control-agent-server api POST "/api/conversations/$Q/pause" --auth bad --expect 401
  control-agent-server api POST "/api/conversations/$Q/interrupt" --auth bad --expect 401
  control-agent-server api POST /api/conversations/not-a-uuid/run --expect 422 --check detail.0.loc contains conversation_id --save F05.control-errors/run-malformed
  control-agent-server api POST /api/conversations/not-a-uuid/pause --expect 422 --check detail.0.loc contains conversation_id
  control-agent-server api POST /api/conversations/not-a-uuid/interrupt --expect 422 --check detail.0.loc contains conversation_id
  control-agent-server api GET "/api/conversations/$Q" --check execution_status eq idle --save F05.control-errors/untouched
  control-agent-server api GET "/api/conversations/$Q/events/count" --check . eq "$N"
  control-agent-server api GET "/api/conversations/$Q/events/count" --query kind=$PAUSE_KIND --check . eq 0
  ```
  每个路由都会拒绝缺少和错误的键，分别返回 401 错误和 422 错误，错误信息分别为 `conversation_id`。 `Q` 仍然 `idle`，没有任何新事件，而相同的会话密钥驱动了每个其他子弹（正控制）。
- **边跑边跑(`F05.run-conflict`)。** `P` 的模型调用挂起，因此运行保持在 `running` 状态。
  ```sh
  control-agent-server conversation send "$P" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$P/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$P" --until running --timeout 60
  control-agent-server sink read --name qa-f05-hang --expect-min 1
  control-agent-server api POST "/api/conversations/$P/run" --expect 409 \
    --check detail eq 'Conversation already running. Wait for completion or pause first.' --save F05.run-conflict/run-409
  control-agent-server api GET "/api/conversations/$P" --check execution_status eq running
  control-agent-server api GET /api/conversations/count --query status=running --check . eq 1
  control-agent-server sink read --name qa-f05-hang --expect-min 1 --expect-max 1
  ```
  第二个 `/run` 被拒绝了，返回状态码 409 并附带了该详细信息。 `P` 仍然在运行对话，而 stub 看到只有一个模型调用。
- **长时间模型调用期间暂停 (`F05.pause-running`)。**
  ```sh
  control-agent-server ws start "/sockets/events/$P" --name f05-p-pause --duration 300
  control-agent-server api POST "/api/conversations/$P/pause" --expect 200 --check success eq true --expect-max-ms 3000 --timeout 60 --save F05.pause-running/pause
  control-agent-server api GET "/api/conversations/$P/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET /api/conversations/search --query status=paused --check items contains "$P" --save F05.pause-running/search
  control-agent-server ws stop f05-p-pause --contains '"key": "execution_status", "value": "paused"' --save F05.pause-running/frames
  control-agent-server ws read f05-p-pause --expect-kind PauseEvent
  control-agent-server api POST "/api/conversations/$P/run" --expect 409 --save F05.pause-running/run-409
  ```
  暂停立即回答（运行循环释放网络等待的状态锁），一个 `PauseEvent` 是已持久化，`status=paused` 列出 `P`，套接字推送 `paused`，`PauseEvent` 推送。 模型调用仍在进行中，因此 `/run` 仍然为 409，尽管状态是 `paused`。
- **GET 通话中暂停 (`F05.pause-running-get`) 后，已知错误。**通过其详细路由及其状态文件读取相同的对话。
  ```sh
  control-agent-server api GET /api/conversations/search --query status=paused --check items contains "$P"
  control-agent-server api POST "/api/conversations/$P/run" --expect 409
  control-agent-server api GET "/api/conversations/$P" --check execution_status eq paused --quiet --save F05.pause-running-get/get  # bug：状态 eq 200 && 检查.0.实际 eq 正在运行
  control-agent-server state cat "server/workspace/conversations/$(echo "$P" | tr -d -)/base_state.json" --check execution_status eq paused  # bug: checks.0.actual eq running
  ```
  状态搜索（实时状态显示为 `paused`）和409（模型调用仍在飞行中）是中止通话控制。
  预期：`paused`，如套接字、事件日志和状态搜索。
  今天，他们俩都说 `running` 直到模型调用返回（这里为300秒）或被中断：暂停运行在运行循环的打开状态块中 `ConversationState._save_depth` 停留1秒 `arun()` 只释放锁对于网络等待， `_released_state_lock_during_io` 在
  `local_conversation.py`)，因此 `base_state.json` 的自动保存被推迟到步骤结束，并且 `GET /api/conversations/{id}` 从该文件中进行应答。 甚至 `search?status=paused`（根据实时状态进行过滤并列出 `P`）也会使用 `execution_status` `running` 返回 `P` 的项目。 暂停并轮询 GET 的消费者（如 `conversation wait` 和 SDK 轮询器所做的那样）会继续看到 `running`，并且该窗口中的崩溃会失去暂停 (`F05.pause-running-crash`)。
- **通过中断释放暂停的步骤 (`F05.pause-running-release`)。**
  ```sh
  control-agent-server ws start "/sockets/events/$P" --name f05-p-release --duration 300
  control-agent-server api POST "/api/conversations/$P/interrupt" --expect 200 --check success eq true --expect-max-ms 4000 --timeout 60 --save F05.pause-running-release/interrupt
  control-agent-server api GET "/api/conversations/$P" --check execution_status eq paused --save F05.pause-running-release/get
  control-agent-server api GET "/api/conversations/$P/events/count" --query kind=$INTERRUPT_KIND --check . eq 1
  control-agent-server api GET /api/conversations/count --query status=running --check . eq 0
  control-agent-server ws stop f05-p-release --expect-kind InterruptEvent --save F05.pause-running-release/frames
  X=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server api DELETE "/api/conversations/$X" --expect 200 --check success eq true
  ```
  中断会迅速结束挂起的呼叫，并在服务器等待5秒之前附加一个`InterruptEvent`（也附加在套接字上），GET现在读取
  `paused` 并且没有任何运行。 创建对话需要单次运行槽（它回答429，而运行时它保持不变），因此废弃的创建（被删除后再次创建）证明了槽是空的。
- **中断正在进行的对话 (`F05.interrupt-running`)。** `R` 的模型调用将挂起，直到其存根被重写。
  ```sh
  control-agent-server conversation send "$R" --text 'hi' --no-run
  control-agent-server ws start "/sockets/events/$R" --name f05-r-interrupt --duration 300
  control-agent-server api POST "/api/conversations/$R/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$R" --until running --timeout 60
  control-agent-server sink read --name qa-f05-resume --expect-min 1
  control-agent-server api POST "/api/conversations/$R/interrupt" --expect 200 --check success eq true --expect-max-ms 4000 --timeout 60 --save F05.interrupt-running/interrupt
  control-agent-server api GET "/api/conversations/$R" --check execution_status eq paused --save F05.interrupt-running/get
  control-agent-server api GET "/api/conversations/$R/events/count" --query kind=$INTERRUPT_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$R/events/count" --query kind=$PAUSE_KIND --check . eq 0
  control-agent-server ws stop f05-r-interrupt --expect-kind InterruptEvent --save F05.interrupt-running/frames
  control-agent-server ws read f05-r-interrupt --contains '"key": "execution_status", "value": "paused"'
  ```
  中断返回时间通常为4秒（正常情况下约为150毫秒）。 尽管模型调用会持续300秒，但服务器最多只会等待5秒。 GET 读取 `paused`，日志只有一个 `InterruptEvent`，没有其他
  `PauseEvent`，并且套接字同时推动了 `InterruptEvent` 和
  `paused` 过渡。
- **中断后恢复 (`F05.run-after-interrupt`)。**提供者现在通过 `finish` 调用进行应答（无法按需生产精确的工具调用真实模型）。
  ```sh
  control-agent-server fixture llm-stub --name qa-f05-resume --step 'tool:finish:{"message":"QA_F05_RESUMED"}'
  control-agent-server api POST "/api/conversations/$R/run" --expect 200 --check success eq true --save F05.run-after-interrupt/run
  control-agent-server conversation wait "$R" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$R/agent_final_response" --check response eq QA_F05_RESUMED --save F05.run-after-interrupt/final
  control-agent-server sink read --name qa-f05-resume --expect-min 2
  ```
  `/run` 立即被接受（没有延迟 409），恢复的运行再次调用模型并以存根的 `finish` 消息结束 `finished`。
- **在工具调用 (`F05.pause-tool-step`) 期间暂停。** `W`的模型要求
  每次通话时 `terminal` `sleep 6 && echo QA_F05_STEP_DONE`； 命令运行时暂停。 在暂停之后以及运行结束时，套接字在连接时获得一个 `full_state` 帧，因此其中三个证明运行已停止。
  ```sh
  control-agent-server conversation send "$W" --text 'hi' --no-run
  control-agent-server ws start "/sockets/events/$W" --name f05-w-step --duration 300
  control-agent-server api POST "/api/conversations/$W/run" --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$W/events/count" --query kind=$ACTION_KIND --check . eq 1 --until-ok 30
  control-agent-server api POST "/api/conversations/$W/pause" --expect 200 --check success eq true --timeout 60 --save F05.pause-tool-step/pause
  control-agent-server ws read f05-w-step --contains '"key": "full_state"' --expect-min 3 --wait 30
  control-agent-server api GET "/api/conversations/$W" --check execution_status eq paused --save F05.pause-tool-step/get
  control-agent-server api GET "/api/conversations/$W/events/search" --query kind=$OBSERVATION_KIND \
    --check items len-eq 1 --check items.0.observation.content.0.text contains QA_F05_STEP_DONE --save F05.pause-tool-step/observation
  control-agent-server api GET "/api/conversations/$W/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$W/events/count" --query kind=$ACTION_KIND --check . eq 1
  control-agent-server sink read --name qa-f05-step --expect-min 1 --expect-max 1
  control-agent-server ws stop f05-w-step --contains '"key": "execution_status", "value": "paused"' --save F05.pause-tool-step/frames
  ```
  命令完成（观测结果持有`QA_F05_STEP_DONE`），然后循环停止：`paused`，一次`PauseEvent`，仍然一次动作和一次模型请求，以及套接字推送`paused`。 今天，`/pause` 请求只有在命令结束时返回（这里大约5秒）：运行循环持有状态锁全部工具调用，暂停等待它。
- **工具调用 (`F05.interrupt-tool-call`) 期间发生中断。** `T`的模型要求`terminal``sleep 30`； 中断在运行时发生。 然后存根被重写以调用 `finish` 并恢复运行。
  ```sh
  control-agent-server conversation send "$T" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$T/run" --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$T/events/count" --query kind=$ACTION_KIND --check . eq 1 --until-ok 30
  TCALL=$(control-agent-server api GET "/api/conversations/$T/events/search" --query kind=$ACTION_KIND --field items.0.tool_call_id)
  control-agent-server api POST "/api/conversations/$T/interrupt" --expect 200 --check success eq true --expect-max-ms 4000 --timeout 60 --save F05.interrupt-tool-call/interrupt
  control-agent-server api GET "/api/conversations/$T" --check execution_status eq paused
  control-agent-server api GET "/api/conversations/$T/events/search" --query kind=$AGENT_ERROR_KIND \
    --check items len-eq 1 --check items.0.tool_call_id eq "$TCALL" --save F05.interrupt-tool-call/agent-error
  control-agent-server api GET "/api/conversations/$T/events/count" --query kind=$INTERRUPT_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$T/events/count" --query kind=$OBSERVATION_KIND --check . eq 0
  control-agent-server fixture llm-stub --name qa-f05-tool --step 'tool:finish:{"message":"QA_F05_TOOL_RESUMED"}'
  control-agent-server api POST "/api/conversations/$T/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$T" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$T/agent_final_response" --check response eq QA_F05_TOOL_RESUMED
  control-agent-server sink read --name qa-f05-tool --contains 'Tool call interrupted before completion' --expect-min 1 --save F05.interrupt-tool-call/resumed-request
  ```
  尽管命令运行时间为30秒，中断却立即作出反应。
  `paused`、一个 `InterruptEvent`、一个 `AgentErrorEvent`（“工具调用在完成之前中断...”）回答操作的 `tool_call_id`，并且没有观测结果。 恢复的模型请求携带该错误作为工具结果，因此历史记录保持有效，并且 `T` 完成。
- **运行容量(`F05.run-capacity`).**一个插槽：`G` 将其保留在挂起的调用上，而 `Q` 则要求运行。
  ```sh
  control-agent-server conversation send "$Q" --text 'Reply with the single word ok, then finish.' --no-run
  control-agent-server conversation send "$G" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$G/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$G" --until running --timeout 60
  control-agent-server api POST "/api/conversations/$Q/run" --expect 429 \
    --check detail eq 'Conversation run limit reached. Retry the request later.' --save F05.run-capacity/run-429
  control-agent-server api GET "/api/conversations/$Q" --check execution_status eq idle --check last_user_message_id exists
  control-agent-server api GET /api/conversations/count --query status=running --check . eq 1
  control-agent-server api POST "/api/conversations/$G/interrupt" --expect 200 --check success eq true
  control-agent-server api POST "/api/conversations/$Q/run" --expect 200 --check success eq true --save F05.run-capacity/run-after-release
  control-agent-server conversation wait "$Q" --until finished --timeout 180
  ```
  `Q` 的运行被拒绝，返回 429，而 `G` 运行，其排队消息保留并保留在 `idle` 中； `G` 被中断后，相同的 `/run` 被接受并且
  `Q` 在 DeepSeek 闪烁时完成。
- **一个循环的运行结束 `stuck` (`F05.stuck-detected`).**  `L`该提供商对每通电话都以相同的方式回答 `think` 调用一个循环，一个真正的模型无法在需求时生成。 默认情况下，卡住检测处于启用状态。
  ```sh
  control-agent-server api GET "/api/conversations/$L" --check stuck_detection eq true --check execution_status eq idle
  control-agent-server conversation send "$L" --text 'hi' --no-run
  control-agent-server ws start "/sockets/events/$L" --name f05-l-stuck --duration 300
  control-agent-server api POST "/api/conversations/$L/run" --expect 200 --check success eq true --save F05.stuck-detected/run
  control-agent-server conversation wait "$L" --until stuck --timeout 60
  control-agent-server api GET "/api/conversations/$L" --check execution_status eq stuck --save F05.stuck-detected/get
  control-agent-server api GET /api/conversations/search --query status=stuck --check items len-eq 1 --check items.0.id eq "$L"
  control-agent-server api GET /api/conversations/count --query status=stuck --check . eq 1
  control-agent-server api GET "/api/conversations/$L/events/count" --query kind=$ACTION_KIND --check . eq 4
  control-agent-server api GET "/api/conversations/$L/events/count" --query kind=$OBSERVATION_KIND --check . eq 4
  control-agent-server api GET "/api/conversations/$L/events/count" --query kind=$ERROR_KIND --check . eq 0
  control-agent-server sink read --name qa-f05-loop --expect-min 4 --expect-max 4
  control-agent-server ws read f05-l-stuck --contains '"key": "full_state"' --expect-min 2 --wait 30
  control-agent-server ws stop f05-l-stuck --contains '"key": "execution_status", "value": "stuck"' --save F05.stuck-detected/frames
  control-agent-server ws read f05-l-stuck --kinds ConversationErrorEvent --expect-none
  ```
  在四次相同的 `think` actions 和观测结果循环在调用第五个模型之前就停止了。 GET, the `status=stuck` search (only `L`) and count say `stuck`, 该端点已弃用 `stuck` transition, and no
  `ConversationErrorEvent` 已记录（卡住不是错误）。
- **再次运行卡住的对话 (`F05.stuck-rerun`)。**没有新的输入。
  ```sh
  control-agent-server ws start "/sockets/events/$L" --name f05-l-rerun --duration 300
  control-agent-server api POST "/api/conversations/$L/run" --expect 200 --check success eq true --save F05.stuck-rerun/run
  control-agent-server ws read f05-l-rerun --contains '"key": "full_state"' --expect-min 2 --wait 30
  control-agent-server ws read f05-l-rerun --contains '"key": "execution_status", "value": "running"'
  control-agent-server ws stop f05-l-rerun --contains '"key": "execution_status", "value": "stuck"' --save F05.stuck-rerun/frames
  control-agent-server api GET "/api/conversations/$L" --check execution_status eq stuck
  control-agent-server api GET "/api/conversations/$L/events/count" --query kind=$ACTION_KIND --check . eq 4
  control-agent-server sink read --name qa-f05-loop --expect-min 4 --expect-max 4
  ```
  `/run` 接受并立即结束运行（其关闭 `full_state` 帧）：套接字显示 `running` 然后 `stuck`，没有新的动作，也没有第五个模型请求。 卡住的检测器仅查看自上次用户消息以来的事件，因此 `/run` 单独重新检测相同的循环。
- **新输入将其解除粘连 (`F05.stuck-new-input`)。**提供商现在通过 `finish` 呼叫进行应答。
  ```sh
  control-agent-server fixture llm-stub --name qa-f05-loop --step 'tool:finish:{"message":"QA_F05_UNSTUCK"}'
  control-agent-server conversation send "$L" --text 'Try something else.' --no-run
  control-agent-server api GET "/api/conversations/$L" --check execution_status eq idle --save F05.stuck-new-input/idle
  control-agent-server api POST "/api/conversations/$L/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$L" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$L/agent_final_response" --check response eq QA_F05_UNSTUCK --save F05.stuck-new-input/final
  control-agent-server sink read --name qa-f05-loop --expect-min 5 --expect-max 5
  ```
  `stuck`重置为`idle`，然后下一个运行调用一个模型并结束`finished`，然后以`finish`消息结束。
- **迭代上限 (`F05.max-iterations-stop`).** `M` 允许每次运行 6 个步骤，并关闭检测； 它的提供者像 `L` 一样在 `think` 上循环。
  ```sh
  control-agent-server api GET "/api/conversations/$M" --check max_iterations eq 6 --check stuck_detection eq false --check execution_status eq idle
  control-agent-server conversation send "$M" --text 'hi' --no-run
  control-agent-server ws start "/sockets/events/$M" --name f05-m-cap --duration 300
  control-agent-server api POST "/api/conversations/$M/run" --expect 200 --check success eq true --save F05.max-iterations-stop/run
  control-agent-server ws read f05-m-cap --contains '"key": "full_state"' --expect-min 2 --wait 60
  control-agent-server api GET "/api/conversations/$M" --check execution_status eq error --save F05.max-iterations-stop/get
  control-agent-server api GET "/api/conversations/$M/events/search" --query kind=$ERROR_KIND \
    --check items len-eq 1 --check items.0.code eq MaxIterationsReached --check items.0.detail contains '(6)' --save F05.max-iterations-stop/error-event
  control-agent-server api GET "/api/conversations/$M/events/count" --query kind=$ACTION_KIND --check . eq 6
  control-agent-server sink read --name qa-f05-cap --expect-min 6 --expect-max 6
  control-agent-server api GET /api/conversations/search --query status=error --check items contains "$M"
  control-agent-server ws stop f05-m-cap --kinds ConversationErrorEvent --contains MaxIterationsReached --expect-min 1 --save F05.max-iterations-stop/frames
  control-agent-server ws read f05-m-cap --contains '"key": "execution_status", "value": "error"'
  control-agent-server ws read f05-m-cap --contains '"value": "stuck"' --expect-none
  ```
  `error` 运行程序执行了六个模型调用和六个动作（超过停滞阈值的两个动作，这里已经关闭），然后结束
  `ConversationErrorEvent` `MaxIterationsReached` (“智能体达到最大迭代限制 (6)。”) REST 和套接字； `status=error` 列出了 `M`，并且从未推送过 `stuck` 状态。
- **上限后恢复 (`F05.max-iterations-resume`)。**上限计算每次运行的步数，因此新的 `/run` 会获得新的 6 步。
  ```sh
  control-agent-server ws start "/sockets/events/$M" --name f05-m-resume --duration 300
  control-agent-server api POST "/api/conversations/$M/run" --expect 200 --check success eq true --save F05.max-iterations-resume/run
  control-agent-server ws read f05-m-resume --contains '"key": "full_state"' --expect-min 2 --wait 60
  control-agent-server ws stop f05-m-resume --contains '"key": "execution_status", "value": "running"' --save F05.max-iterations-resume/frames
  control-agent-server api GET "/api/conversations/$M/events/count" --query kind=$ERROR_KIND --check . eq 2
  control-agent-server sink read --name qa-f05-cap --expect-min 12 --expect-max 12
  control-agent-server fixture llm-stub --name qa-f05-cap --step 'tool:finish:{"message":"QA_F05_CAP_DONE"}'
  control-agent-server api POST "/api/conversations/$M/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$M" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$M/agent_final_response" --check response eq QA_F05_CAP_DONE --save F05.max-iterations-resume/final
  control-agent-server sink read --name qa-f05-cap --expect-min 13 --expect-max 13
  ```
  `error` 对话中的 `/run` 被接受，进入 `running` 并在一秒钟之前花费另外六次模型调用（总共十二次）
  `MaxIterationsReached`; 一旦提供者回答 `finish`，下一次运行将进行一次调用并结束 `finished`。
- **运行时平稳重启 (`F05.restart-running-graceful`)。**
  ```sh
  control-agent-server conversation send "$K" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$K/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$K" --until running --timeout 60
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$K" --check execution_status eq paused --save F05.restart-running-graceful/get
  control-agent-server api GET "/api/conversations/$K/events/count" --query kind=$PAUSE_KIND --check . eq 1
  control-agent-server api GET "/api/conversations/$K/events/count" --query kind=$INTERRUPT_KIND --check . eq 1
  control-agent-server doctor
  ```
  关闭会暂停正在进行的对话，并取消其步骤，因此 `K` 会返回 `paused` 一次 `PauseEvent` 和一次 `InterruptEvent`，重启的服务器是健康的。
- **重启后状态仍然存在 (`F05.restart-keeps-status`)。** 只读在上一个项目符号重新启动后进行检查。
  ```sh
  for CID in "$A" "$B" "$Q" "$R" "$T" "$L" "$M"; do
    control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished
  done
  for CID in "$C" "$P" "$G" "$W"; do
    control-agent-server api GET "/api/conversations/$CID" --check execution_status eq paused
  done
  control-agent-server api GET "/api/conversations/$E" --check execution_status eq error --save F05.restart-keeps-status/error
  control-agent-server api GET /api/conversations/count --query status=paused --check . eq 5 --save F05.restart-keeps-status/paused-count
  control-agent-server api GET /api/conversations/count --query status=finished --check . eq 7
  control-agent-server api GET /api/conversations/count --query status=error --check . eq 1
  control-agent-server api GET /api/conversations/count --query status=running --check . eq 0
  ```
  七场对话 `finished`, five `paused` (`C`, `P`, `G`, `W`,
  `K`)，`E` 仍然是 `error`，没有任何东西是 `running`。
- **运行时崩溃 (`F05.restart-hard-running`)。** SIGKILL 叶子
  `running` 在磁盘上。
  ```sh
  control-agent-server api POST "/api/conversations/$K/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$K" --until running --timeout 60
  control-agent-server state cat "server/workspace/conversations/$(echo "$K" | tr -d -)/base_state.json" --check execution_status eq running
  control-agent-server restart --hard
  control-agent-server api GET "/api/conversations/$K" --check execution_status eq error --save F05.restart-hard-running/get
  control-agent-server conversation events "$K" --kinds ConversationStateUpdateEvent --key execution_status --contains '"error"' --save F05.restart-hard-running/status-events
  control-agent-server api GET /api/conversations/count --query status=running --check . eq 0
  control-agent-server api POST "/api/conversations/$K/run" --expect 200 --check success eq true --save F05.restart-hard-running/rerun
  control-agent-server conversation wait "$K" --until running --timeout 60
  control-agent-server api POST "/api/conversations/$K/interrupt" --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$K" --check execution_status eq paused
  control-agent-server doctor
  ```
  被杀死的服务器留下了 `running` 和 `base_state.json`。 下一个开始时接管了死主人的租约，并标记了 `K` `error` （一个已持久化）
  `execution_status`更新），`running`什么也没有，`/run`恢复`K`（再次中断以释放插槽）。
- **通话中暂停后崩溃 (`F05.pause-running-crash`)，已知错误。**
  `K` 再次陷入悬挂的钩子，模型调用在飞行中暂停，服务器是 SIGKILLed。 最后一颗子弹，所以一切都不取决于它留下了什么。
  ```sh
  H=$(control-agent-server sink read --name qa-f05-hang | python3 -c 'import json, sys; print(json.load(sys.stdin)["requests"])')
  control-agent-server api POST "/api/conversations/$K/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$K" --until running --timeout 60
  control-agent-server sink read --name qa-f05-hang --expect-min $((H + 1)) --wait 30
  control-agent-server api POST "/api/conversations/$K/pause" --expect 200 --check success eq true --expect-max-ms 3000
  control-agent-server api GET /api/conversations/search --query status=paused --check items contains "$K"
  control-agent-server api GET "/api/conversations/$K/events/count" --query kind=$PAUSE_KIND --check . eq 2
  control-agent-server restart --hard
  control-agent-server api GET "/api/conversations/$K/events/count" --query kind=$PAUSE_KIND --check . eq 2
  control-agent-server api GET "/api/conversations/$K" --check execution_status eq paused --quiet --save F05.pause-running-crash/get  # bug: 状态 eq 200 && 检查.0.实际 eq 错误
  ```
  stub的新请求证明暂停落地时模型调用仍在进行中，第二 `PauseEvent` 崩溃后，该控制仍在事件日志中。 预计： `paused`服务器接受的最后状态和已持久化在事件日志（the `PauseEvent` 和
  `execution_status` `paused` 更新均在磁盘上）。 今天`K`回来了
  `error`：暂停从未达到
  `base_state.json` (`F05.pause-running-get`)，因此重新启动会看到 `running` 并将对话视为运行中崩溃。

<a id="gotchas"></a>

## 陷阱

- 创建时的 `initial_message` 总是开始运行，无论其 `run` 字段表示什么（`_start_conversation` 在发送后调用 `run()`； 已知的错误
  `F04.create-initial-message-run-false`). 要暂存待处理的输入，请在没有输入的情况下创建并附加
  `conversation send --no-run`（`POST .../events`与`"run": false`）；
  `conversation start --prompt ... --no-run` 正是这样做的。
- 创建对话也需要一个运行槽（按照设计，创建路径像运行一样被允许：`tests/agent_server/test_run_admission.py`）。 与
  `max_concurrent_runs` 1 和正在进行的运行，`POST /api/conversations` 本身返回 429，因此在第一次运行持有槽之前创建配方所需的每个对话。
- `GET /api/conversations/{id}` 从自动保存的内容中组成答案
  `base_state.json`，而事件套接字、搜索和计数的状态过滤器以及事件日志来自内存。 当一个步骤在飞行中并且某些东西改变了步骤中的状态时，它们是不同的（`F05.pause-running-get`）。
- 暂停不会停止正在进行的模型调用：状态会翻转为
  `paused` 立即，但该步骤首先完成，直到那时 `/run` 回答 409“等待完成或先暂停”，尽管对话已暂停。 `/interrupt` 取消通话（这是出路）； 它最多等待运行任务 5 秒，如果任务尚未结束，则 `/run` 保持 409 直到结束。
- 工具调用期间的暂停是不同的：运行循环保持整个工具调用的状态锁（它仅在模型调用周围释放它），因此
  `/pause` 请求本身会阻塞，直到工具返回，然后回答 200，步骤完成。 具有短 HTTP 超时的消费者会在暂停时看到超时，稍后生效； `/interrupt`立即接听，将未完成的通话变成`AgentErrorEvent`（`F05.pause-tool-step`、`F05.interrupt-tool-call`）。
- `/run` 在任何事情发生之前返回； 观察结果
  `conversation wait`，事件套接字或事件日志。 提供者失败是来自 `/run` 的 200，后跟 `error` 和 `ConversationErrorEvent`。
- `events/count` 和 `events/search` 按完全合格的筛选 `kind`
  class path (`openhands.sdk.event.user_action.PauseEvent`) or the short
  `kind` 事件携带的值 (`PauseEvent`, `F06.search-kind-short`)。
- 每个状态变化也是已持久化作为 `ConversationStateUpdateEvent`，因此计算特定类型而不是总事件，除非证明什么也没发生 (`F05.run-finished-noop`)。
- 正常关闭会暂停并取消正在运行的对话（`PauseEvent`，然后是 `InterruptEvent`）； SIGKILL 将 `running` 留在磁盘上，下一次启动会将其变成 `error`，并为未完成的工具调用（如果有）附加 `AgentErrorEvent`。 同一主机上的死进程持有的租约将立即被接管； 来自另一台主机的租约必须首先到期（`OH_LEASE_TTL_SECONDS`，默认值 45），在此之前 `/run` 会回答 404。
- `F05.run-error-responsive` 仅表示默认控制台的内容
  日志记录（`launch` 既不设置 `LOG_JSON` 也不设置 `LOG_RICH_TRACEBACKS`）：
  事件循环上呈现的丰富回溯仅使服务器停顿在那里，而不是
  with `LOG_JSON=true` or `LOG_RICH_TRACEBACKS=false`. Any such stall also
  延迟套接字的错误帧，因此用 `ws read --wait` 等待它们。
- 运行结束在套接字上显示为 `full_state`
  `ConversationStateUpdateEvent`; 服务器还在连接时以及每次暂停和中断后发送一个。 对它们进行计数 (`--expect-min`) 是配方在没有状态变化时证明运行结束的方式 (`F05.run-finished-noop`,
  `F05.pause-tool-step`).
- `stuck` 不是错误：没有 `ConversationErrorEvent` 和 `/run`
  `stuck` 对话对自上次用户消息以来的事件重新运行检测器，因此它会立即返回到 `stuck`，而无需模型调用。 只有新的输入（或使用`stuck_detection: false`创建的对话）才能让循环继续（`F05.stuck-rerun`，`F05.stuck-new-input`）。
- 每次运行 `max_iterations` 计数智能体步，而不是每次对话：每次
  `/run` 从零 (`F05.max-iterations-resume`) 开始。 在最后一次允许的迭代中以 `finish` 结尾的步骤将保留为 `finished`。
- SDK 的每次运行成本上限 (`MaxBudgetReached`) 无法通过此 API 达到：`EventService` 构建对话时无需
  `max_budget_per_run`，仅子智能体个定义集 (F27)。
- `/run` 在等待确认的对话中批准待处理的操作； `/goal` 循环的暂停、中断、暂停和恢复、暂停和中断上的会话 Webhook 以及凭据绑定都由它们自己的系列涵盖。
- SDK 和 TypeScript `RemoteConversation.run()` 发布相同的 `/run`； 端点 SDK 接收一个 409 作为“已经运行”，而不是失败，而是等待那个运行结束，因此在这里可见的状态只有 409 配方。
