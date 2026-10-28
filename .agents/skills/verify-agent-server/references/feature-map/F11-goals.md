<a id="goal-loop"></a>

# 目标循环

A `/goal` 循环追求一个目标，该目标存在于现有的对话中：服务器将该目标作为用户消息发布，并运行它智能体，asks the 智能体自己的 LLM 与客观标准进行对比，并重新提示词直到法官说“完整”为止，`max_iterations`当到达该点，或者发生其他中断时。 一切都发生在对话自己的历史记录和事件流中（没有新的或分叉的对话）。 进展已持久化并推送为
`ConversationStateUpdateEvent` 行，其中 `key: "goal"` 的 `value` 为
`{active, status: running|complete|capped|interrupted, iteration, max_iterations, objective, verdict}`; 这是消费者可以读取目标状态的唯一位置，也是`/goal/resume`在重新启动后继续的地方。 `/goal/stop` 只取消循环，普通用户消息会取代它，循环在整个生命周期中都保留一个运行槽。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/models.py`、`openhands-sdk/openhands/sdk/conversation/goal/`

需求：`llm`、`tmux`

发射：`--config-json '{"max_concurrent_runs": 1}'`

路线：`POST /api/conversations/{conversation_id}/goal`，
`POST /api/conversations/{conversation_id}/goal/stop`,
`POST /api/conversations/{conversation_id}/goal/resume`

<a id="sub-features"></a>

## 子功能

- `F11.goal-validation`：空白或空白目标返回 400 `Goal objective must not be empty.`，低于 1 的 `max_iterations` 或缺失目标返回 422，并且不记录任何内容。
- `F11.goal-unknown-id`：所有三个路由对于未知的会话 ID 都返回 404，对于格式错误的会话 ID，则返回 422。
- `F11.goal-auth`：所有三个路由都返回 401，没有会话密钥或会话密钥错误，但接受正确的密钥。
- `F11.goal-stop-noop`: `/goal/stop` 没有活动循环返回 200 并且不记录任何内容。
- `F11.goal-resume-none`：`/goal/resume` 在从未有目标的对话中返回 400 `no_resumable_goal` 并且不记录任何内容。
- `F11.goal-complete`：在DeepSeek闪烁时，一个小目标运行到目标状态`complete`（`active: false`，与`complete: true`的判决），智能体的文件在工作区中，对话是`finished`。
- `F11.goal-ws`：事件套接字将目标状态推送为 `ConversationStateUpdateEvent` 帧，开头为 `key: "goal"`: `running`，然后是终端状态。
- `F11.goal-in-place`：循环不创建对话； 目标是用户消息，智能体的工具工作在同一对话的事件日志中。
- `F11.goal-followup`：`running`记录了`iteration: 1`的状态，然后发布了一条包含法官`missing`文本的跟进用户消息，并进行了一轮新的处理。
- `F11.goal-capped`：当没有判决说完成时，循环在 `max_iterations` 圆中停止，`status: capped`、`iteration` 等于上限，并且最后一个判决，恰好在每个圆中进行一次智能体和一次法官的呼叫。
- `F11.goal-resume-finished`：`/goal/resume` 在 `complete` 或 `capped` 目标后返回 400 `no_resumable_goal`。
- `F11.goal-busy`：当一轮进球正在进行时，第二轮`/goal`、`/goal/resume`和`/run`返回409并添加无进球状态； 省略的 `max_iterations` 默认为 10。
- `F11.goal-stop`: `/goal/stop` 在一个活跃的循环中一次性返回 200，并记录 `interrupted` (`active: false`)，但只取消循环：在途的回合会保持对话 `running` 直到被中断。
- `F11.goal-superseded`：循环处于活动状态时通过 `POST /events` 发布的用户消息会取消循环 (`interrupted`) 并被记录。
- `F11.goal-superseded-socket`：通过事件套接字发送的用户消息以相同的方式取消活动循环。
- `F11.goal-interrupt-run`：在目标回合期间打断对话将使其 `paused` 和目标 `interrupted`。
- `F11.goal-busy-run`：`/goal` 和 `/goal/resume` 当普通运行处于活动状态时返回 409 并添加无目标状态。
- `F11.goal-resume`：`/goal/resume` 停止后继续从已持久化目标、上限和迭代恢复提示词（不再是目标）并运行到 `complete`。
- `F11.goal-restart-resume`：中断的目标状态在重新启动后继续存在，并且 `/goal/resume` 之后继续。
- `F11.goal-run-error`：模型提供者无法访问的一轮以 `error`（带有 `ConversationErrorEvent`）和目标 `interrupted` 结束对话，目标保持可恢复。
- `F11.goal-judge-error`：成功回合后失败的判断调用记录 `interrupted` 并离开对话 `finished`。
- `F11.goal-capacity`：在回合之间（`finished`对话，飞行中的判官叫）循环保持忙碌（409在自己的对话中），并占用其运行槽，因此当容量满时，`/goal`和`/goal/resume`其他地方返回429并记录无事。 停止循环会释放槽。
- `F11.goal-delete-active` 删除一个正在进行循环的对话，会立即返回200，对话消失，循环的运行槽被返回（下一个`/goal`会被接受，而不是429）。
- `F11.goal-cap-overrun`：上一轮裁判调用失败后恢复的目标永远不会报告比 `max_iterations` 多的轮数（没有目标状态的 `iteration` 高于上限）。
- `F11.goal-restart-active`：服务器重新启动时处于活动状态的循环在重新启动后报告为 `interrupted` (`active: false`)，而不是 `running`。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `POST /api/conversations/{conversation_id}/goal` 与
  `{"objective": "...", "max_iterations": 3}` (`StartGoalRequest`;
  `max_iterations` 默认为 10，最小 1)。 返回 200
  `{"success": true}` 一旦循环被安排； 400
  `Goal objective must not be empty.`（空白目标）、404 未知 ID、409 `Conversation run or goal loop already running.`、429
  `Conversation run limit reached. Retry the request later.`, 422 表示身体或 ID 错误。
- REST：对于已知 id，`POST /api/conversations/{conversation_id}/goal/stop`（无正文）始终为 200 `{"success": true}`，无论循环是否处于活动状态； `POST /api/conversations/{conversation_id}/goal/resume`（没有主体）是200，或者400 `no_resumable_goal`（还没有进球，或者最后一球结束
  `complete`/`capped`), 409 and 429 like `/goal`.
- 第二种观点（其他家族拥有，此处用作证明）：
  `GET /api/conversations/{conversation_id}/events/search`（目标行为 `ConversationStateUpdateEvent` 和 `key: "goal"`；
  `control-agent-server conversation events <id> --key goal` 过滤它们），
  `GET /api/conversations/{conversation_id}/events/count` 与 `source` 和
  `body` 过滤器（目标、后续和恢复消息），
  `GET /api/conversations/{conversation_id}` (`execution_status`),
  `GET /api/conversations/count`、事件套接字
  `/sockets/events/{conversation_id}`（`key: "goal"`帧），对话工作区在磁盘上，并且模型请求记录`llm-stub`。
- 隐式入口：普通用户消息，通过
  `POST /api/conversations/{conversation_id}/events` 或事件套接字上的消息帧，停止活动循环（`F11.goal-superseded`，
  `F11.goal-superseded-socket`); `/interrupt` 结束当前回合及其循环； `DELETE /api/conversations/{conversation_id}` 关闭循环而不记录状态（`F11.goal-delete-active`）； 正常关闭也是如此，下一次加载会将过时的 `running` 状态记录为
  `interrupted` (`F11.goal-restart-active`).
- TypeScript 客户端：`ConversationClient.startGoal(conversationId,
  {objective, max_iterations})`, `stopGoal(conversationId)`,
  `resumeGoal(conversationId)` (`clients/typescript/src/client/conversation-client.ts`) 和
  `RemoteConversation.startGoal(objective, maxIterations?)`, `stopGoal()`,
  `resumeGoal()` (`clients/typescript/src/conversation/remote-conversation.ts`).
- SDK：Python`RemoteConversation`没有目标方法； SDK 的
  `run_goal(conversation, objective, judge_llm, max_iterations=...)` (`openhands-sdk/openhands/sdk/conversation/goal/runner.py`) 是相同 `GoalController` 上的进程内同步驱动程序，并判断服务器使用。 Agent Canvas 渲染来自 `goal` 状态事件的目标筹码。
- 配置：`max_concurrent_runs`（`OH_MAX_CONCURRENT_RUNS`，默认10）； 循环在其整个生命周期中保留一个槽。 该系列推出 1.
- 以下的食谱使用了 REST 通过 `api`, 通过事件套接字 `ws start` (在操作之前) `ws listen --send`, 实际的 DeepSeek flash 智能体对于快乐路径（`F11.goal-complete`, and `fixture llm-stub` 对于一个真正的模型无法即时完成的任务：一个精确的判决（总是不完整的，或者完全的），一个模型调用会挂起（用来维持比赛的进行），以及一个法官调用会失败或者挂起在一场好的比赛中。 一个 stub 的回复既是也是智能体答案和法官的判决。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用该系列的 `Launch:` 标志 (`launch --new --config-json '{"max_concurrent_runs": 1}'`) 启动运行，`doctor` ok，
  `$DEEPSEEK_API_KEY` 设置（下面的块保存 DeepSeek 配置文件）并且
  `tmux` 为真正的智能体的 `terminal` 工具。 每个发射子弹的弹壳必须找到一个空位，因此子弹严格按顺序运行，每个持有弹壳的子弹在它结束之前会释放弹壳（循环结束，或者`/interrupt`）。 `F11.goal-capacity` 取决于 1 的极限。
- 下面的块创建了一个未知的 id `$NOPE`，六个 stubs 和十三个没有初始消息的对话（一个对话需要一个空闲的槽位，而一个对话的开始需要一个初始消息）。 存根：`qa-f11-no`总是回答判决`{"score": 0.2, "complete": false, "missing": "QA_F11_MISSING"}`； `qa-f11-hang` 将每个呼叫挂起 300 秒，直到
  `F11.goal-resume` 将其重写为完整的判决； `qa-f11-judge` 和
  `qa-f11-judge2`回答一次，然后以500失败（因此本轮成功，判断失败）； `qa-f11-slot` 应答一次，然后挂起 60 秒（法官在飞行中呼叫）； `qa-f11-park` 每次通话都会挂断。 对话：使用 `terminal` 工具对 DeepSeek 闪光灯进行 `G`； `qa-f11-no` 上的 `X` 和 `W`； `H`,
  `qa-f11-hang` 上的 `U`、`V`、`I`； `E` 拒绝连接的提供商 (`127.0.0.1:9`)； `J`关于`qa-f11-judge`； `K`关于`qa-f11-slot`；
  `qa-f11-judge2` 上的 `J2`； `qa-f11-park` 上的 `D` 和 `R`。 每个存根智能体都有
  `tools: []` 和 `num_retries: 0`。

```sh
control-agent-server llm preset deepseek
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
OFFLINE_AGENT='{"llm": {"model": "openai/qa-offline", "api_key": "qa-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": []}'
NO=$(control-agent-server fixture llm-stub --name qa-f11-no --step 'reply:{"score": 0.2, "complete": false, "missing": "QA_F11_MISSING"}' --print-path)
NO_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$NO/v1\", \"num_retries\": 0}, \"tools\": []}"
HANG=$(control-agent-server fixture llm-stub --name qa-f11-hang --step hang:300 --print-path)
HANG_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG/v1\", \"num_retries\": 0}, \"tools\": []}"
JUDGE=$(control-agent-server fixture llm-stub --name qa-f11-judge --step reply:QA_F11_ROUND_DONE --step status:500 --print-path)
JUDGE_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$JUDGE/v1\", \"num_retries\": 0}, \"tools\": []}"
JUDGE2=$(control-agent-server fixture llm-stub --name qa-f11-judge2 --step reply:QA_F11_ROUND_DONE --step status:500 --print-path)
JUDGE2_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$JUDGE2/v1\", \"num_retries\": 0}, \"tools\": []}"
SLOT=$(control-agent-server fixture llm-stub --name qa-f11-slot --step reply:QA_F11_ROUND_DONE --step hang:60 --print-path)
SLOT_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$SLOT/v1\", \"num_retries\": 0}, \"tools\": []}"
PARK=$(control-agent-server fixture llm-stub --name qa-f11-park --step hang:300 --print-path)
PARK_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$PARK/v1\", \"num_retries\": 0}, \"tools\": []}"
G=$(control-agent-server conversation start --tools terminal --no-autotitle --print-id)
X=$(control-agent-server conversation start --body-json "{\"agent\": $NO_AGENT}" --no-autotitle --print-id)
W=$(control-agent-server conversation start --body-json "{\"agent\": $NO_AGENT}" --no-autotitle --print-id)
H=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
U=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
V=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
I=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
E=$(control-agent-server conversation start --body-json "{\"agent\": $OFFLINE_AGENT}" --no-autotitle --print-id)
J=$(control-agent-server conversation start --body-json "{\"agent\": $JUDGE_AGENT}" --no-autotitle --print-id)
K=$(control-agent-server conversation start --body-json "{\"agent\": $SLOT_AGENT}" --no-autotitle --print-id)
J2=$(control-agent-server conversation start --body-json "{\"agent\": $JUDGE2_AGENT}" --no-autotitle --print-id)
D=$(control-agent-server conversation start --body-json "{\"agent\": $PARK_AGENT}" --no-autotitle --print-id)
R=$(control-agent-server conversation start --body-json "{\"agent\": $PARK_AGENT}" --no-autotitle --print-id)
control-agent-server api GET /api/conversations/count --query status=idle --check . eq 13
```

- **无效的目标请求 (`F11.goal-validation`)。** `X` 上的坏尸体从未运行过。
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$X/events/count" --field .)
  control-agent-server api POST "/api/conversations/$X/goal" --json '{"objective": ""}' --expect 400 --check detail eq 'Goal objective must not be empty.' --save F11.goal-validation/empty
  control-agent-server api POST "/api/conversations/$X/goal" --json '{"objective": "   ", "max_iterations": 2}' --expect 400 --check detail eq 'Goal objective must not be empty.'
  control-agent-server api POST "/api/conversations/$X/goal" --json '{"objective": "QA_F11 x", "max_iterations": 0}' --expect 422 --check detail.0.loc.1 eq max_iterations --save F11.goal-validation/zero-rounds
  control-agent-server api POST "/api/conversations/$X/goal" --json '{"max_iterations": 2}' --expect 422 --check detail.0.loc.1 eq objective
  control-agent-server api POST "/api/conversations/$X/goal" --expect 422
  control-agent-server api GET "/api/conversations/$X/events/count" --check . eq "$N" --save F11.goal-validation/count
  control-agent-server api GET "/api/conversations/$X" --check execution_status eq idle
  ```
  空的目标是一个400（目标控制器接受任何字符串），一个0作为上限，或者一个缺失的目标是一个422（命名字段），而事件计数和`idle`状态保持不变。
- **未知且格式错误的 ID (`F11.goal-unknown-id`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$NOPE/goal" --json '{"objective": "QA_F11 x"}' --expect 404 --save F11.goal-unknown-id/goal
  control-agent-server api POST "/api/conversations/$NOPE/goal/stop" --expect 404 --save F11.goal-unknown-id/stop
  control-agent-server api POST "/api/conversations/$NOPE/goal/resume" --expect 404 --save F11.goal-unknown-id/resume
  control-agent-server api POST /api/conversations/not-a-uuid/goal --json '{"objective": "QA_F11 x"}' --expect 422
  control-agent-server api POST /api/conversations/not-a-uuid/goal/stop --expect 422
  control-agent-server api POST /api/conversations/not-a-uuid/goal/resume --expect 422
  ```
  每个未知的ID是一个404，每个畸形的ID是一个422。
- **身份验证 (`F11.goal-auth`).**正确的钥匙先进入； 那么在所有三条路线上都将拒绝无钥匙和错误钥匙。
  ```sh
  control-agent-server api POST "/api/conversations/$X/goal/stop" --expect 200 --check success eq true
  control-agent-server api POST "/api/conversations/$X/goal" --auth none --json '{"objective": "QA_F11 x"}' --expect 401 --save F11.goal-auth/goal-none
  control-agent-server api POST "/api/conversations/$X/goal" --auth bad --json '{"objective": "QA_F11 x"}' --expect 401
  control-agent-server api POST "/api/conversations/$X/goal/stop" --auth none --expect 401
  control-agent-server api POST "/api/conversations/$X/goal/stop" --auth bad --expect 401
  control-agent-server api POST "/api/conversations/$X/goal/resume" --auth none --expect 401
  control-agent-server api POST "/api/conversations/$X/goal/resume" --auth bad --expect 401 --save F11.goal-auth/resume-bad
  control-agent-server conversation events "$X" --key goal --expect-count 0
  ```
  带有键的调用返回200，其他调用返回401，`X`仍然没有目标状态。
- **无事可停 (`F11.goal-stop-noop`)。**
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$X/events/count" --field .)
  control-agent-server api POST "/api/conversations/$X/goal/stop" --expect 200 --check success eq true --save F11.goal-stop-noop/stop
  control-agent-server api GET "/api/conversations/$X/events/count" --check . eq "$N"
  control-agent-server conversation events "$X" --key goal --expect-count 0 --save F11.goal-stop-noop/goal-events
  ```
  停止码是200，没有任何记录：单独的答案并不能表明是否进行了循环。
- **没有目标地继续(`F11.goal-resume-none`)。**
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$X/events/count" --field .)
  control-agent-server api POST "/api/conversations/$X/goal/resume" --expect 400 --check detail eq no_resumable_goal --save F11.goal-resume-none/resume
  control-agent-server api GET "/api/conversations/$X/events/count" --check . eq "$N"
  control-agent-server api GET "/api/conversations/$X" --check execution_status eq idle
  ```
  400 `no_resumable_goal`，没有新的事件，仍然 `idle`。
- **真实模型上的目标 (`F11.goal-complete`)。** DeepSeek 闪光灯
  `terminal` 工具； 套接字从开始之前开始监听。
  ```sh
  GW=$(control-agent-server api GET "/api/conversations/$G" --field workspace.working_dir)
  NCONV=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server ws start "/sockets/events/$G" --name f11-g --duration 600
  control-agent-server api POST "/api/conversations/$G/goal" --json '{"objective": "Create a file named qa-goal.txt in the current directory containing exactly: hi. Then show its contents with cat.", "max_iterations": 3}' --expect 200 --check success eq true --expect-max-ms 2000 --save F11.goal-complete/start
  control-agent-server ws read f11-g --contains '"key": "goal", "value": {"active": false' --wait 400
  control-agent-server conversation events "$G" --key goal --contains '"active": false, "status": "complete"' --expect-count 1 --save F11.goal-complete/goal-events
  control-agent-server conversation events "$G" --key goal --contains '"complete": true' --expect-count 1
  control-agent-server api GET "/api/conversations/$G" --check execution_status eq finished --save F11.goal-complete/after
  test "$(cat "$GW/qa-goal.txt")" = hi
  ```
  `/goal` 2秒内回答（只调度循环）； 最后的目标状态是 `complete`，判决是 `complete: true`（通常在一轮之后），`qa-goal.txt` 保持 `hi`，对话是 `finished`。
- **套接字上的目标状态 (`F11.goal-ws`)。**
  ```sh
  control-agent-server ws read f11-g --kinds ConversationStateUpdateEvent --contains '"key": "goal", "value": {"active": true, "status": "running", "iteration": 0'
  control-agent-server ws stop f11-g --kinds ConversationStateUpdateEvent --contains '"key": "goal", "value": {"active": false, "status": "complete"' --expect-min 1 --save F11.goal-ws/frames
  ```
  socket在迭代0时推送了一个`running`帧，然后推送了另一个`complete`帧，与日志中持有的`ConversationStateUpdateEvent`行相同。
- **同样的对话，没有新的对话 (`F11.goal-in-place`)。**

  需要：`F11.goal-complete`
  ```sh
  control-agent-server api GET /api/conversations/count --check . eq "$NCONV" --save F11.goal-in-place/count
  control-agent-server api GET "/api/conversations/$G/events/count" --query source=user --query body='Create a file named qa-goal.txt' --check . ge 1
  control-agent-server conversation events "$G" --kinds ObservationEvent --contains qa-goal.txt --expect-kind ObservationEvent --save F11.goal-in-place/observations
  ```
  对话计数未变，目标是用户消息
  `G`，`G`自己的日志保存了接触过的`terminal`观测结果
  `qa-goal.txt`.
- **不完整判决重新提示词 (`F11.goal-followup`).** `X`的存根总是回答不完整的判决，因此它的循环需要每一轮； 盖 2.
  ```sh
  control-agent-server ws start "/sockets/events/$X" --name f11-x --duration 300
  control-agent-server api POST "/api/conversations/$X/goal" --json '{"objective": "QA_F11 audit objective", "max_iterations": 2}' --expect 200 --save F11.goal-followup/start
  control-agent-server ws read f11-x --contains '"key": "goal", "value": {"active": false' --wait 60
  control-agent-server conversation events "$X" --key goal --contains '"active": true, "status": "running", "iteration": 1, "max_iterations": 2, "objective": "QA_F11 audit objective", "verdict": {"score": 0.2, "complete": false, "missing": "QA_F11_MISSING"}' --expect-count 1 --save F11.goal-followup/round-1
  control-agent-server api GET "/api/conversations/$X/events/count" --query source=user --query body='audit iteration 1' --check . eq 1
  control-agent-server api GET "/api/conversations/$X/events/count" --query source=user --query body=QA_F11_MISSING --check . eq 1 --save F11.goal-followup/followup-count
  ```
  在第1轮后，循环记录了`running`和`iteration: 1`，然后发布了法官的判决，并发送了一条用户消息`The goal is NOT yet complete (audit iteration 1). Outstanding: QA_F11_MISSING ...`，然后运行了第2轮。
- **圆帽 (`F11.goal-capped`).**同样的循环结束。
  ```sh
  control-agent-server conversation events "$X" --key goal --contains '"active": false, "status": "capped", "iteration": 2, "max_iterations": 2' --expect-count 1 --save F11.goal-capped/goal-events
  control-agent-server conversation events "$X" --key goal --expect-count 3
  control-agent-server ws stop f11-x --contains '"key": "goal", "value": {"active": false, "status": "capped"' --save F11.goal-capped/frames
  control-agent-server sink read --name qa-f11-no --expect-min 4 --expect-max 4 --save F11.goal-capped/model-calls
  control-agent-server sink read --name qa-f11-no --contains 'auditing whether a long-running GOAL' --expect-min 2 --expect-max 2
  control-agent-server api GET "/api/conversations/$X" --check execution_status eq finished
  ```
  有三种目标状态（`running`在0，`running`在1，`capped`在2，最后一个判罚），socket上的`capped`帧，以及四个模型调用：两个智能体轮和两个裁判调用。
- **结束后无法恢复 (`F11.goal-resume-finished`)。**
  ```sh
  NG=$(control-agent-server conversation events "$G" --key goal | jq -e .matching)
  control-agent-server api POST "/api/conversations/$X/goal/resume" --expect 400 --check detail eq no_resumable_goal --save F11.goal-resume-finished/capped
  control-agent-server api POST "/api/conversations/$G/goal/resume" --expect 400 --check detail eq no_resumable_goal --save F11.goal-resume-finished/complete
  control-agent-server conversation events "$X" --key goal --expect-count 3
  control-agent-server conversation events "$G" --key goal | jq -e ".matching == $NG"
  ```
  两者都是400 `no_resumable_goal`，且不增加目标状态 (`G` 有一个目标状态)
  每轮 `running` 状态加上 `complete` 一个）。
- **一轮比赛正在进行时忙碌 (`F11.goal-busy`)。** `H` 的模型调用挂起，这使得第一轮保持开放。 没有发送`max_iterations`。
  ```sh
  control-agent-server ws start "/sockets/events/$H" --name f11-h --duration 300
  control-agent-server api POST "/api/conversations/$H/goal" --json '{"objective": "QA_F11 busy objective"}' --expect 200 --save F11.goal-busy/start
  control-agent-server conversation wait "$H" --until running --timeout 30
  control-agent-server api POST "/api/conversations/$H/goal" --json '{"objective": "QA_F11 second objective", "max_iterations": 1}' --expect 409 --check detail eq 'Conversation run or goal loop already running.' --save F11.goal-busy/second-goal
  control-agent-server api POST "/api/conversations/$H/goal/resume" --expect 409 --check detail eq 'Conversation run or goal loop already running.' --save F11.goal-busy/resume
  control-agent-server api POST "/api/conversations/$H/run" --expect 409 --check detail eq 'Conversation already running. Wait for completion or pause first.' --save F11.goal-busy/run
  control-agent-server conversation events "$H" --key goal --contains '"active": true, "status": "running", "iteration": 0, "max_iterations": 10, "objective": "QA_F11 busy objective"' --expect-count 1
  control-agent-server conversation events "$H" --key goal --expect-count 1 --save F11.goal-busy/goal-events
  control-agent-server sink read --name qa-f11-hang --expect-min 1 --expect-max 1
  ```
  第二 `/goal`、`/goal/resume` 和 `/run` 分别是 409，唯一的目标状态是第一个循环的 `running`，默认上限为 10，且 stub 实际上只调用了一次模型（仍然挂起）。
- **停止活动循环 (`F11.goal-stop`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$H/goal/stop" --expect 200 --check success eq true --expect-max-ms 3000 --save F11.goal-stop/stop
  control-agent-server ws read f11-h --contains '"key": "goal", "value": {"active": false, "status": "interrupted", "iteration": 0, "max_iterations": 10, "objective": "QA_F11 busy objective"' --wait 10
  control-agent-server conversation events "$H" --key goal --contains '"status": "interrupted"' --expect-count 1 --save F11.goal-stop/goal-events
  control-agent-server api GET "/api/conversations/$H" --check execution_status eq running --save F11.goal-stop/still-running
  control-agent-server api POST "/api/conversations/$H/goal/resume" --expect 409
  control-agent-server api POST "/api/conversations/$H/goal/stop" --expect 200
  control-agent-server conversation events "$H" --key goal --expect-count 2
  control-agent-server api POST "/api/conversations/$H/interrupt" --expect 200
  control-agent-server conversation wait "$H" --until paused --timeout 30
  control-agent-server ws stop f11-h --save F11.goal-stop/frames
  ```
  停止回答立即并记录 `interrupted`，目标、容量和迭代（推送到套接字）。 在飞行中的回合仍在继续（所以 `/goal/resume` 是 409），第二次停顿没有任何记录，`/interrupt` 结束了回合：`paused`。
- **用户消息取代循环 (`F11.goal-superseded`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$U/goal" --json '{"objective": "QA_F11 supersede objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$U" --until running --timeout 30
  control-agent-server conversation send "$U" --text 'QA_F11_USER_INTERJECTION' --no-run
  control-agent-server conversation events "$U" --key goal --contains '"active": false, "status": "interrupted", "iteration": 0, "max_iterations": 3, "objective": "QA_F11 supersede objective"' --expect-count 1 --save F11.goal-superseded/goal-events
  control-agent-server api GET "/api/conversations/$U/events/count" --query source=user --query body=QA_F11_USER_INTERJECTION --check . eq 1 --save F11.goal-superseded/message
  control-agent-server api POST "/api/conversations/$U/interrupt" --expect 200
  control-agent-server conversation wait "$U" --until paused --timeout 30
  ```
  `POST /events` 仅在循环取消后返回：目标是
  `interrupted` 并且该消息位于日志中。 然后，飞行中的子弹被中断以释放插槽。
- **一个套接字消息取代了循环`F11.goal-superseded-socket`).**
  ```sh
  control-agent-server api POST "/api/conversations/$V/goal" --json '{"objective": "QA_F11 socket objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$V" --until running --timeout 30
  control-agent-server ws listen "/sockets/events/$V" --send '{"role": "user", "content": [{"type": "text", "text": "QA_F11_SOCKET_INTERJECTION"}], "run": true}' --until-kind ConversationStateUpdateEvent --until key=goal --until value.status=interrupted --duration 20 --save F11.goal-superseded-socket/frames
  control-agent-server conversation events "$V" --key goal --contains '"active": false, "status": "interrupted", "iteration": 0, "max_iterations": 3, "objective": "QA_F11 socket objective"' --expect-count 1 --save F11.goal-superseded-socket/goal-events
  control-agent-server api GET "/api/conversations/$V/events/count" --query source=user --query body=QA_F11_SOCKET_INTERJECTION --check . eq 1
  control-agent-server api POST "/api/conversations/$V/interrupt" --expect 200
  control-agent-server conversation wait "$V" --until paused --timeout 30
  ```
  发送消息的套接字接收`interrupted`目标帧，日志记录状态和消息。
- **中断回合(`F11.goal-interrupt-run`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$I/goal" --json '{"objective": "QA_F11 interrupt objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$I" --until running --timeout 30
  control-agent-server ws start "/sockets/events/$I" --name f11-i --duration 120
  control-agent-server api POST "/api/conversations/$I/interrupt" --expect 200 --save F11.goal-interrupt-run/interrupt
  control-agent-server ws read f11-i --contains '"key": "goal", "value": {"active": false, "status": "interrupted"' --wait 20
  control-agent-server conversation wait "$I" --until paused --timeout 30
  control-agent-server conversation events "$I" --key goal --contains '"status": "interrupted"' --expect-count 1 --save F11.goal-interrupt-run/goal-events
  control-agent-server ws stop f11-i --contains '"key": "execution_status", "value": "paused"' --save F11.goal-interrupt-run/frames
  ```
  `paused` 圆结束，看到暂停的运行，记录了
  `interrupted`而不是评判它。
- **忙着普通的跑步(`F11.goal-busy-run`)。** `I` 现在有一个可恢复的目标； 对其进行普通运行。
  ```sh
  control-agent-server conversation send "$I" --text 'QA_F11 plain run'
  control-agent-server conversation wait "$I" --until running --timeout 30
  control-agent-server api POST "/api/conversations/$I/goal" --json '{"objective": "QA_F11 refused objective", "max_iterations": 1}' --expect 409 --check detail eq 'Conversation run or goal loop already running.' --save F11.goal-busy-run/goal
  control-agent-server api POST "/api/conversations/$I/goal/resume" --expect 409 --check detail eq 'Conversation run or goal loop already running.' --save F11.goal-busy-run/resume
  control-agent-server conversation events "$I" --key goal --expect-count 2
  control-agent-server api POST "/api/conversations/$I/interrupt" --expect 200
  control-agent-server conversation wait "$I" --until paused --timeout 30
  ```
  两者都是409，目标状态未变（先前的`running`和`interrupted`)。
- **恢复停止的循环 (`F11.goal-resume`)。** `qa-f11-hang` 现在给出了完整的裁决，因此恢复的回合及其审计立即完成。
  ```sh
  control-agent-server fixture llm-stub --name qa-f11-hang --step 'reply:{"score": 1.0, "complete": true, "missing": ""}'
  control-agent-server ws start "/sockets/events/$H" --name f11-h2 --duration 120
  control-agent-server api POST "/api/conversations/$H/goal/resume" --expect 200 --check success eq true --save F11.goal-resume/resume
  control-agent-server ws read f11-h2 --contains '"key": "goal", "value": {"active": false, "status": "complete", "iteration": 1, "max_iterations": 10, "objective": "QA_F11 busy objective"' --wait 60
  control-agent-server conversation events "$H" --key goal --contains '"active": true, "status": "running", "iteration": 0, "max_iterations": 10, "objective": "QA_F11 busy objective"' --expect-count 2 --save F11.goal-resume/goal-events
  control-agent-server api GET "/api/conversations/$H/events/count" --query source=user --query body='Resuming a goal that was paused or interrupted' --check . eq 1 --save F11.goal-resume/resume-prompt
  control-agent-server api GET "/api/conversations/$H/events/count" --query source=user --query body='QA_F11 busy objective' --check . eq 1
  control-agent-server api GET "/api/conversations/$H" --check execution_status eq finished
  control-agent-server ws stop f11-h2
  ```
  `running` 重置循环从存储的目标、上限和迭代状态开始，发送恢复提示词而不是目标（仍然发送一个目标消息），并在第 1 次迭代结束 `complete`。
- **重新启动后恢复 (`F11.goal-restart-resume`)。** `U`的目标被取代； 现在它的存根给出了完整的结论。
  ```sh
  control-agent-server restart
  control-agent-server conversation events "$U" --key goal --expect-count 2
  control-agent-server conversation events "$U" --key goal --contains '"active": false, "status": "interrupted"' --expect-count 1 --save F11.goal-restart-resume/after-restart
  control-agent-server ws start "/sockets/events/$U" --name f11-u --duration 120
  control-agent-server api POST "/api/conversations/$U/goal/resume" --expect 200 --save F11.goal-restart-resume/resume
  control-agent-server ws read f11-u --contains '"key": "goal", "value": {"active": false, "status": "complete", "iteration": 1, "max_iterations": 3, "objective": "QA_F11 supersede objective"' --wait 60
  control-agent-server conversation events "$U" --key goal --expect-count 4 --save F11.goal-restart-resume/goal-events
  control-agent-server ws stop f11-u
  ```
  已持久化状态会随对话返回，继续存储的目标和上限为 `complete`。
- **该回合的提供者失败 (`F11.goal-run-error`)。**
  ```sh
  control-agent-server ws start "/sockets/events/$E" --name f11-e --duration 300
  control-agent-server api POST "/api/conversations/$E/goal" --json '{"objective": "QA_F11 offline objective", "max_iterations": 3}' --expect 200 --save F11.goal-run-error/start
  control-agent-server ws read f11-e --contains '"key": "goal", "value": {"active": false, "status": "interrupted", "iteration": 0' --wait 60
  control-agent-server api GET "/api/conversations/$E" --check execution_status eq error --save F11.goal-run-error/after
  control-agent-server conversation events "$E" --kinds ConversationErrorEvent --expect-kind ConversationErrorEvent
  control-agent-server api POST "/api/conversations/$E/goal/resume" --expect 200 --save F11.goal-run-error/resume
  control-agent-server ws read f11-e --contains '"key": "goal", "value": {"active": false, "status": "interrupted"' --expect-min 2 --wait 60
  control-agent-server conversation events "$E" --key goal --expect-count 4 --save F11.goal-run-error/goal-events
  control-agent-server ws stop f11-e
  ```
  `error` 圆结束时，`ConversationErrorEvent` 目标是
  `interrupted` 没有判断调用，并且它保持可恢复：恢复是 200 并且以同样的方式失败（第二个 `running`/`interrupted` 对）。
- **法官失败(`F11.goal-judge-error`)。** `J` 的存根回答了该轮，然后将 500 返还给裁判。
  ```sh
  control-agent-server ws start "/sockets/events/$J" --name f11-j --duration 120
  control-agent-server api POST "/api/conversations/$J/goal" --json '{"objective": "QA_F11 judge objective", "max_iterations": 3}' --expect 200 --save F11.goal-judge-error/start
  control-agent-server ws read f11-j --contains '"key": "goal", "value": {"active": false, "status": "interrupted"' --wait 60
  control-agent-server conversation events "$J" --key goal --contains '"active": false, "status": "interrupted"' --expect-count 1 --save F11.goal-judge-error/goal-events
  control-agent-server conversation events "$J" --key goal --contains '"verdict": null' --expect-count 2
  control-agent-server api GET "/api/conversations/$J" --check execution_status eq finished
  control-agent-server sink read --name qa-f11-judge --contains 'auditing whether a long-running GOAL' --expect-min 1 --expect-max 1 --save F11.goal-judge-error/model-calls
  control-agent-server ws stop f11-j
  ```
  回合结束了，裁判员的计时失败了，计时器记录了
  `interrupted` 没有判决，而是绞刑或举报 `running`。
- **容量(`F11.goal-capacity`).** `K`'s round finishes and its judge call hangs 60 s: between rounds the conversation is `finished`, but the loop keeps the only run slot。
  ```sh
  control-agent-server ws start "/sockets/events/$K" --name f11-k --duration 300
  control-agent-server api POST "/api/conversations/$K/goal" --json '{"objective": "QA_F11 slot objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$K" --until finished --timeout 60
  control-agent-server api POST "/api/conversations/$K/goal" --json '{"objective": "QA_F11 second objective", "max_iterations": 1}' --expect 409 --check detail eq 'Conversation run or goal loop already running.' --save F11.goal-capacity/own-goal-409
  control-agent-server api POST "/api/conversations/$K/goal/resume" --expect 409 --check detail eq 'Conversation run or goal loop already running.'
  NE=$(control-agent-server api GET "/api/conversations/$E/events/count" --field .)
  control-agent-server api POST "/api/conversations/$W/goal" --json '{"objective": "QA_F11 refused objective", "max_iterations": 1}' --expect 429 --check detail eq 'Conversation run limit reached. Retry the request later.' --save F11.goal-capacity/goal-429
  control-agent-server api POST "/api/conversations/$E/goal/resume" --expect 429 --save F11.goal-capacity/resume-429
  control-agent-server sink read --name qa-f11-slot --contains 'auditing whether a long-running GOAL' --expect-min 1
  control-agent-server conversation events "$W" --key goal --expect-count 0
  control-agent-server api GET "/api/conversations/$E/events/count" --check . eq "$NE"
  control-agent-server api POST "/api/conversations/$K/goal/stop" --expect 200 --expect-max-ms 3000
  control-agent-server ws read f11-k --contains '"key": "goal", "value": {"active": false, "status": "interrupted"' --wait 10
  control-agent-server ws start "/sockets/events/$W" --name f11-w --duration 120
  control-agent-server api POST "/api/conversations/$W/goal" --json '{"objective": "QA_F11 admitted objective", "max_iterations": 1}' --expect 200 --save F11.goal-capacity/goal-after-stop
  control-agent-server ws read f11-w --contains '"key": "goal", "value": {"active": false, "status": "capped", "iteration": 1, "max_iterations": 1' --wait 60
  control-agent-server ws stop f11-k
  control-agent-server ws stop f11-w
  ```
  在法官指令运行时， `K` 是 `finished` 但它的自己 `/goal` 和
  `/goal/resume` 为 409（循环仍处于活动状态），`/goal` 为 `W` 和
  `E` 上的 `/goal/resume` 是 429，没有任何记录。 停止立即返回（放弃判断调用），然后承认 `W` 上的相同 `/goal` 并运行一轮到 `capped`。
- **删除处于活动循环状态的对话 (`F11.goal-delete-active`)。**
  `D`的回合挂起； 删除 `D` 会关闭其循环，并且唯一的运行槽必须返回。
  ```sh
  control-agent-server api POST "/api/conversations/$D/goal" --json '{"objective": "QA_F11 delete objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$D" --until running --timeout 30
  control-agent-server api DELETE "/api/conversations/$D" --expect 200 --expect-max-ms 5000 --save F11.goal-delete-active/delete
  control-agent-server api GET "/api/conversations/$D" --expect 404
  control-agent-server ws start "/sockets/events/$W" --name f11-w2 --duration 120
  control-agent-server api POST "/api/conversations/$W/goal" --json '{"objective": "QA_F11 after delete objective", "max_iterations": 1}' --expect 200 --save F11.goal-delete-active/goal-after-delete
  control-agent-server ws read f11-w2 --contains '"key": "goal", "value": {"active": false, "status": "capped", "iteration": 1, "max_iterations": 1, "objective": "QA_F11 after delete objective"' --wait 60
  control-agent-server ws stop f11-w2
  ```
  删除操作在5秒内返回200状态码（大约0.1秒）。 teardown 取消了循环和悬挂的 round)，`D` 是 404，且在一次运行中，下一个
  `W` 上的 `/goal` 被接纳并运行到 `capped`：已删除的循环没有保留其槽位。 `D` 没有任何记录（它不再存在）。
- **上次审核失败后的简历保持在上限 (`F11.goal-cap-overrun`) 内。**
  `J2` 的裁判未能判定一轮进球； 然后它的存根回答了一个不完整的判决并且目标被恢复。 `max_iterations` 被记录为审计轮次的硬上限，`GoalStatus.iteration` 被记录为“迄今为止已完成的审计轮次”，因此任何状态都不能报告比上限更多的轮次。
  `GoalController.on_run_finished` 只有在法官作出裁决后，才将一次计数计入，因此失败的审计被记录为 `interrupted` 在 0 个 / 1 个（a `/goal/stop` 在法官呼叫期间，同样保持之前的计数，并重新运行该回合，然后结束 `capped` 1/1。 简历还保留了一张卡，当存储的次数已经达到上限时已持久化由于是旧服务器，所以上限了。
  ```sh
  control-agent-server ws start "/sockets/events/$J2" --name f11-j2 --duration 120
  control-agent-server api POST "/api/conversations/$J2/goal" --json '{"objective": "QA_F11 overrun objective", "max_iterations": 1}' --expect 200
  control-agent-server ws read f11-j2 --contains '"key": "goal", "value": {"active": false, "status": "interrupted"' --wait 60
  control-agent-server fixture llm-stub --name qa-f11-judge2 --step 'reply:{"score": 0.1, "complete": false, "missing": "QA_F11_MISSING"}'
  control-agent-server api POST "/api/conversations/$J2/goal/resume" --expect 200 --save F11.goal-cap-overrun/resume
  control-agent-server ws read f11-j2 --contains '"key": "goal", "value": {"active": false, "status": "capped"' --wait 60
  control-agent-server ws stop f11-j2
  control-agent-server conversation events "$J2" --key goal --contains '"active": false, "status": "interrupted"' --expect-count 1
  control-agent-server conversation events "$J2" --key goal --contains '"active": false, "status": "capped"' --expect-count 1
  control-agent-server conversation events "$J2" --key goal --show 50 --full --save F11.goal-cap-overrun/goal-events | jq -e '[.events[].value | select(.iteration > .max_iterations)] | length == 0'
  ```
  失败的审计记录有一个 `interrupted` 状态，恢复后有一个 `capped` 状态，没有状态报告
  `iteration`以上`max_iterations`（四种状态为`running`0/1，
  `interrupted` 0/1, `running` 0/1, `capped` 1/1).
- **重新启动时活动的循环以“中断”方式结束 (`F11.goal-restart-active`)。**正常关闭会取消循环而不记录状态（`_closing` 已设置）； 当对话再次加载（崩溃后也是如此）时，会跟随一个 `active: true` 的最后目标状态，然后是 `active: false`、`interrupted` 状态，这些状态具有相同的目标和计数，因此没有目标芯片显示不再运行的循环
  `/goal/resume`可以继续。
  ```sh
  control-agent-server api POST "/api/conversations/$R/goal" --json '{"objective": "QA_F11 restart objective", "max_iterations": 3}' --expect 200
  control-agent-server conversation wait "$R" --until running --timeout 30
  control-agent-server conversation events "$R" --key goal --contains '"active": true, "status": "running", "iteration": 0' --expect-count 1
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$R" --quiet --check execution_status eq paused --save F11.goal-restart-active/after-restart
  control-agent-server conversation events "$R" --key goal --expect-min 1
  control-agent-server conversation events "$R" --key goal --show 1 --full --save F11.goal-restart-active/goal-events | jq -e '.events[-1].value.active == false and .events[-1].value.status == "interrupted"'
  ```
  在重启之前，循环是活跃的（在第0次迭代时，`running`）。 在之后，对话 `paused` 结束了，目标行返回了，最后的目标状态是 `interrupted`，并且 `active: false`。

<a id="gotchas"></a>

## 陷阱

- 目标的状态仅作为 `ConversationStateUpdateEvent` 行存在
  `key: "goal"`（当前最新）； `ConversationInfo` 没有球门场。 `events/search` 和 `events/count` 通过完全限定的类路径 (F06) 过滤 `kind`，因此使用
  `conversation events <id> --key goal` 或套接字。
- `/goal`、`/goal/resume` 和 `/goal/stop` 在任何事情发生之前返回。 等待目标状态（行动前的 `ws start`，然后
  `ws read --contains ... --wait`)，不在 `execution_status` 上：轮次之间的对话是 `finished`，而循环仍在判断。
- 即使没有任何活动，`/goal/stop` 也是 200，并且它仅取消
  循环：飞行中的一轮持续运行（并保留其运行槽），直到它
  结束或中断。 也可使用 `/interrupt` 停止智能体。
- 在轮次之间，只有 `/goal` 和 `/goal/resume` 将实时循环视为繁忙 (409)； `/run` `finished` 对话被接受 (200)，不进行模型调用并且不停止循环。
- 任何普通用户消息（REST `POST /events` 与 `run` True 或 False，或套接字消息帧）首先取消活动循环。 套接字消息还请求运行，但在旧一轮运行时会被拒绝。
- 法官是智能体自己的LLM（非流式传输），因此每一轮都会花费一次额外的模型调用以及整个成绩单； 不是 JSON 的判断答案算作不完整（得分 0），失败的判断调用会结束循环 `interrupted`。 使用存根，相同的回复既是智能体的答案，也是结论，这就是这些食谱脚本 `complete` 和
  `capped`.
- `stuck` 轮不会结束循环（由法官决定），但 `paused` 和 `error` 会结束循环（`interrupted`）。 目标可以在 `interrupted` 之后（以及在过时的 `running` 之后）恢复，而不能在 `complete` 或 `capped` 之后恢复。
- `/goal/resume` 发送固定的恢复提示词，而不是目标，并保留存储的迭代计数，因此恢复的循环剩余的轮数更少。 仅在判断调用返回后才对一轮进行计数，因此失败或停止的审核不会计入，并且简历永远不会超过上限（`F11.goal-cap-overrun`）。
- 循环在开始时保留一个运行槽并一直保留到结束，包括轮次之间的判断调用； 达到 `max_concurrent_runs` 时，
  `/goal`和`/goal/resume`都是429，什么也没有记录。 创建对话还需要一个空闲槽，因此食谱首先创建所有的槽。
- 对话删除会取消活动循环而不录制
  `interrupted` (`F11.goal-delete-active`); 优雅的重启也会如此，然后重新加载会将过时的 `running` 状态记录为 `interrupted` (`F11.goal-restart-active`)； 当循环处于活动状态时，空闲驱逐永远不会发生。
- 空白目标检查存在于目标控制器中，而不是请求模型中，因此它是带有 `Goal objective must not be empty.` 的 400，而不是 422。
