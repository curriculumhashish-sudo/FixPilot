<a id="fork-navigate-condense-and-ask_agent"></a>

# 分叉、导航、压缩和 ask_agent

消费者如何在不重新开始的情况下分支和检查对话的历史记录。 `fork` 进行深度复制一个对话（包括整个事件日志，或者只复制到一个事件之前的分支）到一个新的独立的， `idle` 命名其来源的对话。 `navigate` 对话的 HEAD (`leaf_event_id`将事件回溯到较早的事件，或为空树，在位置上：没有被删除，下一个追加的事件开始一个兄弟分支。 `condense` 力量在于人上下文压缩现在步骤： 智能体'总结' 上下文压缩器要求其模型生成摘要，并记录下来 `Condensation` event. `ask_agent` asks the 智能体模型会回答与对话无关的问题，并不记录答案或更改状态。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/conversation_service.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/models.py`、`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`、`openhands-sdk/openhands/sdk/conversation/state.py`、`openhands-sdk/openhands/sdk/context/condenser/`

需求：`llm`

路线：`POST /api/conversations/{conversation_id}/ask_agent`，
`POST /api/conversations/{conversation_id}/condense`,
`POST /api/conversations/{conversation_id}/fork`,
`POST /api/conversations/{conversation_id}/navigate`

<a id="sub-features"></a>

## 子功能

- `F10.fork-whole`: `POST /fork` 无正文，返回201，并创建新 `idle` 命名其来源的对话 `forked_from_conversation_id`, 保持源的 HEAD 和工作目录，并保存了每个事件的副本（相同的ID） 持久化 directory 来源不变。
- `F10.fork-named`：分叉请求的 `id`、`title` 和 `tags` 成为分叉的 id、标题和响应中的标签，在 GET 和 `meta.json` 中； 标题没有添加标签。
- `F10.fork-tags-consistent`：当分叉请求没有给出任何标签时，GET和`meta.json`中的分叉标签均为空； 源的标签不会被继承。
- `F10.fork-from-event`: `from_event_id` 仅复制直到该事件（包括该事件）的分支，将分叉的 HEAD 和 `forked_from_event_id` 设置为其，并忽略后面的事件。
- `F10.fork-metrics`：默认情况下，fork的`stats`开始为空； `reset_metrics: false` 复制源的累计成本和词元用量。
- `F10.fork-independent`：附加到分叉的消息永远不会到达源，反之亦然； fork 的事件套接字重播复制的历史记录以及它自己的事件。
- `F10.fork-errors`：未知来源 404，未知 `from_event_id` 404，已取 `id` 409，无效标签键或标题超过200个字符 422，无效 ID 422，缺少键 401。 None 其中创建了一个对话。
- `F10.fork-keeps-credentials`：分叉的 `base_state.json` 保留智能体的（加密的）模型密钥，就像源的一样。
- `F10.fork-run-memory`：已完成的 DeepSeek 对话的一个分支运行到 `finished`，源的历史记录在上下文中（它回忆起只有源被告知的代号）。
- `F10.navigate-event`：`POST /navigate` 较早的 `event_id` 回答 200，`leaf_event_id` 设置为它； GET和`base_state.json`同意并且没有删除任何事件。
- `F10.navigate-branch`：导航后，下一个附加事件的 `parent_id` 是新的 HEAD（废弃分支的同级），实时推送到事件套接字上； HEAD 举动本身不被广播。
- `F10.navigate-empty`：`{}`或`{"event_id": null}`选择空树（磁盘上的`leaf_event_id`null、`head_is_empty`True）； 下一个附加事件成为新的根（`parent_id` `__root__`）。
- `F10.navigate-errors`：未知的`event_id`是404`Unknown event_id: ...`并且未知的对话404，丢失的主体422，丢失的密钥401； None 其中移动 HEAD。
- `F10.navigate-final-response`：在智能体的答案之前导航回来后，`agent_final_response` 报告活动分支（空），而不是放弃的答案。
- `F10.condense-llm`：在完成的 DeepSeek 对话 `POST /condense` 中，在记录一个 `CondensationRequest` 和一个 `Condensation` 以及摘要后回答 200 `{"success": true}`，并在事件套接字上实时推送； 状态保持`finished`。
- `F10.condense-no-condenser`：没有请求处理上下文压缩器（上下文压缩器禁用或 `no_op`）的智能体会出现错误，指出原因，并且不会记录 `CondensationRequest` 或其他事件。
- `F10.condense-status`：拒绝是客户端错误 (4xx)，而不是 500。
- `F10.condense-llm-failure`：当上下文压缩器的模型无法访问时，将答案 500 压缩为 `error_id`，将 `CondensationRequest` 保留为待处理状态，并且不记录 `Condensation`。
- `F10.condense-errors`：未知的 id 是 404 `Conversation not found`，格式错误的 id 422，丢失的密钥 401（并且没有记录）。
- `F10.ask-agent`: `POST /ask_agent` 询问了关于 DeepSeek (200 `{"response": ...}`) 的对话，没有记录消息，也没有推送消息到套接字，且状态不变。
- `F10.ask-agent-errors`：缺少的`question`是422，缺少的键是401，并且具有`error_id`的不可到达的模型500。
- `F10.ask-agent-running`：当运行等待其模型时，`ask_agent` 立即应答（它不等待步骤），不记录任何内容并保留状态 `running`。
- `F10.ask-agent-unknown`：未知会话id为404，作为路由文件。
- `F10.restart-persist` 重启后，forks 仍然保留 lineage、标题、标签、HEAD 和事件，一个名字为已持久化但尚未加载的 fork id 仍然为 409，而一个已导航的空 HEAD 仍然为空（下一个消息仍然是一个新的根）。
- `F10.restart-cold-calls`在重启后，压缩并 ask_agent 在对话中工作智能体尚未初始化，且 ask_agent 仍然看到历史（代号）。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`POST /api/conversations/{conversation_id}/fork`（可选主体
  `ForkConversationRequest`：`id`、`title`（最多 200）、`tags`（小写字母数字键）、`reset_metrics`（默认 `true`）、`from_event_id`； 查询`include_skills`），分叉的201`ConversationInfo`； 404、409、422。
- REST：`POST /api/conversations/{conversation_id}/navigate`（必填正文
  `{"event_id": "<id>" | null}`; `{}` 指 null； 查询 `include_skills`), 200 `ConversationInfo` 与新的 `leaf_event_id`; 404、422。
- REST：`POST /api/conversations/{conversation_id}/condense`（无正文），200
  `{"success": true}` 一旦上下文压缩步骤完成； 404、409（没有处理请求的上下文压缩器）、500。
- REST：`POST /api/conversations/{conversation_id}/ask_agent`（主体
  `{"question": "..."}`), 200 `{"response": "..."}`; 404, 422, 500.
- 这里使用的第二个视图：`GET /api/conversations/{conversation_id}`，
  `.../events/search`, `.../events/count`, `.../events/{event_id}`,
  `.../agent_final_response`（其他家庭），对话的
  `meta.json` 和 `base_state.json` (`state cat --conversation`)、`llm-stub` 收到的请求 (`sink read`) 以及事件套接字
  `/sockets/events/{conversation_id}`. `POST .../interrupt`（运行族）仅结束`F10.ask-agent-running`中的存根运行。
- SDK: `RemoteConversation.fork(标题=,标签=,reset_metrics=,
  from_event_id=, conversation_id=)` returns a `RemoteConversation` on the
  fork（通过 `agent=` 引发 `NotImplementedError`）；
  `RemoteConversation.navigate_to(event_id | None)`发布然后刷新缓存状态（HEAD不广播）； `RemoteConversation.condense()`;
  `RemoteConversation.ask_agent(question)` (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`).
  示例：`examples/02_remote_agent_server/11_conversation_fork.py`。
- TypeScript客户端：`ConversationClient.forkConversation`，
  `navigateConversation`、`condenseConversation`、`askAgent` (`clients/typescript/src/client/conversation-client.ts`) 和
  `RemoteConversation.fork`, `navigateTo`, `condense`, `askAgent` (`clients/typescript/src/conversation/remote-conversation.ts`).
- 下面的每个配方都直接驱动 REST 路线； SDK 和 TypeScript 方法是相同调用的瘦包装器。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用 `launch --new`（无特殊标志）启动运行，`doctor` ok，并且
  `$DEEPSEEK_API_KEY` 设置； 下面的块保存 DeepSeek 配置文件。 否
  `tmux`或浏览器：每个智能体都有`tools: []`（只有`finish`和`think`）。
- 下面的块按顺序创建： 未知 id `$NOPE`； `events/search` 和 `events/count` 过滤的完全限定事件类型； `S`，关于无法访问的占位符模型的对话，其中包含两条永远不会运行的用户消息（`$E1` = `QA_F10_M1`，`$E2` = `QA_F10_M2`）； `A`，DeepSeek的快速对话告诉了一个代号并跑到`finished`； `NC` 和
  `NOOP`、离线智能体（其上下文压缩器已禁用）或 `no_op`； `OFF`，离线智能体，默认总结上下文压缩器； 并且一个 `llm-stub` (`$SIDE_AGENT`)，其第一个调用挂起 300 秒，而其后续调用则回答 `QA_F10_SIDE`（一个等待其模型的运行无法通过真实模型保持打开）。 这里只有`A`调用了模型； `F10.ask-agent-running` 项目符号在需要它之前自行开始其存根对话。

```sh
control-agent-server llm preset deepseek
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
MSG=openhands.sdk.event.llm_convertible.message.MessageEvent
CREQ=openhands.sdk.event.condenser.CondensationRequest
COND=openhands.sdk.event.condenser.Condensation
OFFLINE_LLM='{"model": "openai/qa-offline", "api_key": "qa-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}'
S=$(control-agent-server conversation start --placeholder-agent --no-autotitle --no-run --prompt QA_F10_M1 --print-id)
control-agent-server api POST "/api/conversations/$S/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_M2"}], "run": false}' --expect 200 --quiet
E1=$(control-agent-server api GET "/api/conversations/$S/events/search" --query kind=$MSG --query body=QA_F10_M1 --check items len-eq 1 --field items.0.id)
E2=$(control-agent-server api GET "/api/conversations/$S/events/search" --query kind=$MSG --query body=QA_F10_M2 --check items len-eq 1 --field items.0.id)
A=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'The project codename is PELICAN. Reply with just: OK' --wait --until finished,error --timeout 180 --print-id)
control-agent-server api GET "/api/conversations/$A" --check execution_status eq finished --quiet
NC=$(control-agent-server conversation start --body-json "{\"agent_settings\": {\"agent_kind\": \"openhands\", \"llm\": $OFFLINE_LLM, \"tools\": [], \"condenser\": {\"enabled\": false}}}" --no-autotitle --no-run --prompt QA_F10_NC --print-id)
NOOP=$(control-agent-server conversation start --body-json "{\"agent_settings\": {\"agent_kind\": \"openhands\", \"llm\": $OFFLINE_LLM, \"tools\": [], \"condenser\": {\"condenser_kind\": \"no_op\"}}}" --no-autotitle --no-run --prompt QA_F10_NOOP --print-id)
OFF=$(control-agent-server conversation start --placeholder-agent --no-autotitle --no-run --prompt QA_F10_OFFLINE --print-id)
SIDE=$(control-agent-server fixture llm-stub --name qa-f10-side --step hang:300 --step reply:QA_F10_SIDE --print-path)
SIDE_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$SIDE/v1\", \"num_retries\": 0}, \"tools\": []}"
```

- **分叉整个日志 (`F10.fork-whole`)。**没有叉体的叉子 `S`。
  ```sh
  N_S=$(control-agent-server api GET "/api/conversations/$S/events/count" --field .)
  LEAF_S=$(control-agent-server api GET "/api/conversations/$S" --field leaf_event_id)
  WD_S=$(control-agent-server api GET "/api/conversations/$S" --field workspace.working_dir)
  test "$LEAF_S" = "$E2"
  FW=$(control-agent-server api POST "/api/conversations/$S/fork" --expect 201 \
    --check execution_status eq idle --check forked_from_conversation_id eq "$S" \
    --check . contains '"forked_from_event_id": null' --check leaf_event_id eq "$E2" \
    --check workspace.working_dir eq "$WD_S" --check . contains '"title": null' \
    --save F10.fork-whole/fork --field id)
  test "$FW" != "$S"
  control-agent-server api GET "/api/conversations/$FW" --quiet --check forked_from_conversation_id eq "$S" --check execution_status eq idle
  control-agent-server api GET "/api/conversations/$FW/events/count" --check . eq "$N_S" --save F10.fork-whole/count
  control-agent-server api GET "/api/conversations/$FW/events/$E2" --expect 200 --check id eq "$E2" --check parent_id eq "$E1"
  test "$(control-agent-server state ls 'events/event-*.json' --conversation "$FW" | python3 -c 'import json, sys; print(json.load(sys.stdin)["count"])')" = "$N_S"
  control-agent-server state cat meta.json --conversation "$FW" --check forked_from_conversation_id eq "${S//-/}"
  control-agent-server api GET "/api/conversations/$S" --quiet --check . contains '"forked_from_conversation_id": null' --check leaf_event_id eq "$E2"
  control-agent-server api GET "/api/conversations/$S/events/count" --check . eq "$N_S"
  ```
  分支有一个新的ID，是`idle`，指向`S`，有`S`的HEAD(`$E2`)和工作目录，以及和`event-*.json`文件一样数量的事件，存储在自己的目录下。 `S`不变。
  `forked_from_event_id` 和 `title` 存在，`null`（TypeScript 和 SDK 模型将它们视为可空字段）：`--check FIELD eq null` 也符合 `"key": null` 在已序列化的身体中。
- **命名叉 (`F10.fork-named`).**选择 ID、标题和标签。
  ```sh
  FN=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api POST "/api/conversations/$S/fork" \
    --json "{\"id\": \"$FN\", \"title\": \"QA F10 named fork\", \"tags\": {\"qa\": \"f10\"}}" --expect 201 \
    --check id eq "$FN" --check title eq 'QA F10 named fork' --check tags.qa eq f10 \
    --check tags.title missing --check forked_from_conversation_id eq "$S" --save F10.fork-named/fork
  control-agent-server api GET "/api/conversations/$FN" --quiet --check title eq 'QA F10 named fork' --check tags.qa eq f10 --save F10.fork-named/get
  control-agent-server state cat meta.json --conversation "$FN" --check title eq 'QA F10 named fork' --check tags.qa eq f10
  ```
  叉子回答`$FN`； 它们 `tags` 是请求的标签。 标题是分离的元数据，这是由#4814确定的，`meta.json` 存储了标题和请求的标签。
- **从事件中分叉 (`F10.fork-from-event`)。**分叉 `S` 直至其第一条消息。
  ```sh
  FE=$(control-agent-server api POST "/api/conversations/$S/fork" --json "{\"from_event_id\": \"$E1\"}" --expect 201 \
    --check forked_from_event_id eq "$E1" --check leaf_event_id eq "$E1" --save F10.fork-from-event/fork --field id)
  control-agent-server api GET "/api/conversations/$FE/events/count" --query kind=$MSG --check . eq 1 --save F10.fork-from-event/messages
  control-agent-server api GET "/api/conversations/$FE/events/count" --query body=QA_F10_M1 --check . eq 1
  control-agent-server api GET "/api/conversations/$FE/events/count" --query body=QA_F10_M2 --check . eq 0
  control-agent-server state cat base_state.json --conversation "$FE" --max-chars 200 --check leaf_event_id eq "$E1" --check head_is_empty eq false
  control-agent-server api GET "/api/conversations/$S/events/count" --query body=QA_F10_M2 --check . eq 1
  ```
  分支仅持有系统提示词和 `QA_F10_M1`，HEAD 在其中
  `$E1`; `S`还有`QA_F10_M2`。
- **分叉指标 (`F10.fork-metrics`)。** `A`有实际成本。
  ```sh
  control-agent-server api GET "/api/conversations/$A" --quiet --check stats.usage_to_metrics.default.accumulated_cost gt 0
  FK=$(control-agent-server api POST "/api/conversations/$A/fork" --json '{"reset_metrics": false}' --expect 201 --quiet \
    --check stats.usage_to_metrics.default.accumulated_cost gt 0 --save F10.fork-metrics/kept --field id)
  control-agent-server api GET "/api/conversations/$FK" --quiet --check stats.usage_to_metrics.default.accumulated_cost gt 0
  FR=$(control-agent-server api POST "/api/conversations/$A/fork" --expect 201 --quiet \
    --check stats.usage_to_metrics len-eq 0 --save F10.fork-metrics/reset --field id)
  control-agent-server api GET "/api/conversations/$FR" --quiet --check stats.usage_to_metrics len-eq 0
  ```
  `reset_metrics: false` fork 报告源代码的成本。 默认情况下
  `stats.usage_to_metrics` 是 `{}`。
- **分叉和源分歧 (`F10.fork-independent`)。**附加到每一侧并重放叉子的插座。

  需要：`F10.fork-whole`
  ```sh
  control-agent-server api POST "/api/conversations/$FW/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_ONLY_FORK"}], "run": false}' --expect 200 --quiet
  control-agent-server api POST "/api/conversations/$S/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_ONLY_SOURCE"}], "run": false}' --expect 200 --quiet
  control-agent-server api GET "/api/conversations/$FW/events/count" --query body=QA_F10_ONLY_FORK --check . eq 1 --save F10.fork-independent/fork-has-own
  control-agent-server api GET "/api/conversations/$S/events/count" --query body=QA_F10_ONLY_FORK --check . eq 0
  control-agent-server api GET "/api/conversations/$S/events/count" --query body=QA_F10_ONLY_SOURCE --check . eq 1
  control-agent-server api GET "/api/conversations/$FW/events/count" --query body=QA_F10_ONLY_SOURCE --check . eq 0 --save F10.fork-independent/fork-lacks-source
  control-agent-server ws start "/sockets/events/$FW" --name qa-f10-fork-replay --query resend_mode=all --duration 60
  control-agent-server ws stop qa-f10-fork-replay --wait 15 --kinds MessageEvent --contains QA_F10_ONLY_FORK --expect-min 1 --save F10.fork-independent/replay
  control-agent-server ws read qa-f10-fork-replay --kinds MessageEvent --contains QA_F10_M1 --expect-min 1
  control-agent-server ws read qa-f10-fork-replay --contains QA_F10_ONLY_SOURCE --expect-none
  ```
  每个边只看到自己的新消息。 分支的套接字会重放复制的 `QA_F10_M1` 和自己的 `QA_F10_ONLY_FORK`，而不是源的。
- **未知、已采取且无效的输入 (`F10.fork-errors`)。**首先统计对话次数； None 其中可能会创建一个。

  需要：`F10.fork-named`
  ```sh
  C0=$(control-agent-server api GET /api/conversations/count --field .)
  LONG=$(python3 -c 'print("x" * 201)')
  control-agent-server api POST "/api/conversations/$NOPE/fork" --expect 404 --check detail eq 'Source conversation not found' --save F10.fork-errors/unknown-source
  control-agent-server api POST "/api/conversations/$S/fork" --json '{"from_event_id": "qa-f10-nope"}' --expect 404 \
    --check detail eq 'Unknown from_event_id: qa-f10-nope' --save F10.fork-errors/unknown-event
  control-agent-server api POST "/api/conversations/$S/fork" --json "{\"id\": \"$S\"}" --expect 409 \
    --check detail eq "Conversation with id $S already exists" --save F10.fork-errors/taken-by-source
  control-agent-server api POST "/api/conversations/$S/fork" --json "{\"id\": \"$FN\"}" --expect 409 --check detail eq "Conversation with id $FN already exists"
  control-agent-server api POST "/api/conversations/$S/fork" --json '{"tags": {"Bad-Key": "x"}}' --expect 422 --check detail.0.loc.1 eq tags --save F10.fork-errors/bad-tag
  control-agent-server api POST "/api/conversations/$S/fork" --json "{\"title\": \"$LONG\"}" --expect 422 --check detail.0.type eq string_too_long
  control-agent-server api POST /api/conversations/not-a-uuid/fork --expect 422 --check detail.0.loc.1 eq conversation_id
  control-agent-server api POST "/api/conversations/$S/fork" --auth none --expect 401
  control-agent-server api GET /api/conversations/count --check . eq "$C0" --save F10.fork-errors/count-after
  test "$(control-agent-server state ls 'server/workspace/conversations/*/meta.json' | python3 -c 'import json, sys; print(json.load(sys.stdin)["count"])')" = "$C0"
  ```
  404 `Source conversation not found`, 404 `Unknown from_event_id: qa-f10-nope`, 409 `Conversation with id ... already exists` 对于源的 id 和对于一个存在的 fork 的 id，422 为标签键，201 个字符的标题，以及不合法的 id，401 无键（带有键的请求成功了） `F10.fork-whole`). 对话数量和  `meta.json` 文件未更改。
- **派生标签应与已保存元数据一致（`F10.fork-tags-consistent`）。** 从带 `qa=src` 标签的对话派生新对话，指定标题但不指定标签，然后比较派生对话在 GET 上的 `qa` 标签及其 `meta.json` 中的对应标签。
  ```sh
  TS=$(control-agent-server conversation start --placeholder-agent --no-autotitle --no-run --tag qa=src --prompt QA_F10_TAGS --print-id)
  control-agent-server api GET "/api/conversations/$TS" --quiet --check tags.qa eq src
  control-agent-server state cat meta.json --conversation "$TS" --check tags.qa eq src
  TF=$(control-agent-server api POST "/api/conversations/$TS/fork" --json '{"title": "QA F10 tag fork"}' --expect 201 --quiet \
    --check title eq 'QA F10 tag fork' --save F10.fork-tags-consistent/fork --field id)
  TF_QA=$(control-agent-server api GET "/api/conversations/$TF" --field tags | python3 -c 'import json, sys; v = json.load(sys.stdin).get("qa"); print("null" if v is None else v)')
  control-agent-server state cat meta.json --conversation "$TF" --check title eq 'QA F10 tag fork' --check tags.qa eq "$TF_QA"
  control-agent-server api GET "/api/conversations/$TF" --quiet --check tags len-eq 0
  control-agent-server state cat meta.json --conversation "$TF" --check tags len-eq 0
  ```
  源代码显示 `qa=src` 在 GET 和 `meta.json` 中一致（两个视图可以一致）。 GET 和 `meta.json` 的分支都有空标签，标签的标题被单独存储。 `ConversationService.fork_conversation` 和
  `LocalConversation.fork` 都使用请求的标签，当提供 None 时默认为空集 (#4814)。
- **前叉保留模型密钥 (`F10.fork-keeps-credentials`)，已知错误。**分叉`S`，其占位符智能体具有模型密钥，并比较存储的智能体。
  ```sh
  KF=$(control-agent-server api POST "/api/conversations/$S/fork" --expect 201 --field id)
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check agent.llm.api_key exists --check agent.condenser.llm.api_key exists
  control-agent-server state cat base_state.json --conversation "$KF" --max-chars 200 --check agent.llm.api_key exists --check agent.condenser.llm.api_key exists  # bug: content.agent.llm.model 存在 && 检查.0.实际 eq null && 检查.1.实际 eq null
  ```
  预期：两个文件都保存密钥（使用服务器的密码加密；
  `state cat` 显示 `<redacted:encrypted>`）。 今天，源代码和分支根本没有 `api_key`（检查报告 `null`）：
  `LocalConversation.fork` 构建 fork 的
  `LocalConversation` 没有源的 `cipher`所以它的状态是已序列化与机密被丢弃，服务器随后加载了 fork 的智能体从那个文件（`ConversationService.fork_conversation` 启动 fork 的 `EventService` 没有智能体 of its own).
- **分叉使用源内存 (`F10.fork-run-memory`) 运行，这是已知错误。**分叉已完成的 DeepSeek 对话 `A` 并询问分叉只告诉消息来源的内容。
  ```sh
  N_A_MSG=$(control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$MSG --field .)
  AF=$(control-agent-server api POST "/api/conversations/$A/fork" --json '{"title": "QA F10 memory fork"}' --expect 201 --field id)
  control-agent-server conversation send "$AF" --text 'What is the project codename I told you? Answer with the codename only.' --wait --until finished,error --timeout 180
  control-agent-server conversation events "$AF" --kinds ConversationErrorEvent --contains LLMAuthenticationError --expect-count 0 --save F10.fork-run-memory/auth-errors  # bug：匹配 ge 1
  control-agent-server api GET "/api/conversations/$AF" --quiet --check execution_status eq finished --save F10.fork-run-memory/status
  control-agent-server api GET "/api/conversations/$AF/agent_final_response" --check response matches '(?i)pelican' --save F10.fork-run-memory/final
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$MSG --check . eq "$N_A_MSG"
  ```
  `A` 本身在同一配置文件（先决条件）上运行到 `finished`，因此密钥有效。 预期：分支的运行记录不应有身份验证错误，运行到`finished`，答案应使用复制历史中的codename（只有源方知道，而不是用词）。 `agent_final_response` 读取以消息形式或通过 `finish` 给出的回复，并且 `A` 没有获得任何消息
  from the fork's run. Today the fork's run ends in `error` within seconds
  带有 `ConversationErrorEvent` `LLMAuthenticationError`（“您的 LLM API 密钥似乎无效或已过期。”），因为前叉丢失了型号密钥 (`F10.fork-keeps-credentials`)； 标记的检查在该事件上失败。 任何其他故障（提供商中断、错误答案）都会在稍后的、未标记的检查中失败并报告 `fail`，而不是 `xfail`。 模型需要密钥的任何对话分支都无法运行。
- **导航到较早的事件 (`F10.navigate-event`)。**将 `S` 的 HEAD 移回其第一条消息。
  ```sh
  N=$(control-agent-server api GET "/api/conversations/$S/events/count" --field .)
  control-agent-server api POST "/api/conversations/$S/navigate" --json "{\"event_id\": \"$E1\"}" --expect 200 \
    --check id eq "$S" --check leaf_event_id eq "$E1" --quiet --save F10.navigate-event/navigate
  control-agent-server api GET "/api/conversations/$S" --quiet --check leaf_event_id eq "$E1" --save F10.navigate-event/get
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check leaf_event_id eq "$E1" --check head_is_empty eq false
  control-agent-server api GET "/api/conversations/$S/events/count" --check . eq "$N"
  control-agent-server api GET "/api/conversations/$S/events/$E2" --expect 200 --check id eq "$E2"
  ```
  GET 和 `base_state.json` 都携带 `leaf_event_id` `$E1`。 事件计数保持不变，废弃的`$E2`仍然可读。
- **下一个事件分支 (`F10.navigate-branch`)。**在导航和追加时观察套接字。
  ```sh
  control-agent-server ws start "/sockets/events/$S" --name qa-f10-branch --duration 120
  control-agent-server ws read qa-f10-branch --wait 15 --kinds ConversationStateUpdateEvent --contains full_state --expect-min 1
  control-agent-server api POST "/api/conversations/$S/navigate" --json "{\"event_id\": \"$E1\"}" --expect 200 --quiet
  control-agent-server api POST "/api/conversations/$S/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_M3"}], "run": false}' --expect 200 --quiet
  control-agent-server ws stop qa-f10-branch --wait 15 --kinds MessageEvent --contains "\"parent_id\": \"$E1\"" --expect-min 1 --save F10.navigate-branch/frames
  control-agent-server ws read qa-f10-branch --kinds ConversationStateUpdateEvent --contains '"key": "last_user_message_id"' --expect-min 1
  control-agent-server ws read qa-f10-branch --contains '"key": "leaf_event_id"' --expect-none
  E3=$(control-agent-server api GET "/api/conversations/$S/events/search" --query kind=$MSG --query body=QA_F10_M3 \
    --check items.0.parent_id eq "$E1" --save F10.navigate-branch/new-event --field items.0.id)
  control-agent-server api GET "/api/conversations/$S/events/$E2" --check parent_id eq "$E1"
  control-agent-server api GET "/api/conversations/$S" --quiet --check leaf_event_id eq "$E3"
  ```
  `QA_F10_M3` 与 `parent_id` `$E1` 一起到达套接字，与 `$E2` 具有相同的父级：两个兄弟分支。 状态变化确实会随着
  `ConversationStateUpdateEvent` 帧由字段键控（此处为 `last_user_message_id`），但没有帧宣布 HEAD 移动，这就是 SDK 和 TypeScript `navigate` 方法使用 GET 刷新其状态的原因。 HEAD 现在坐在新消息上。
- **导航到空树 (`F10.navigate-empty`)。** `{}` 和
  `{"event_id": null}` 是相同的请求。
  ```sh
  control-agent-server api POST "/api/conversations/$S/navigate" --json '{}' --expect 200 --quiet --check . contains '"leaf_event_id": null' --save F10.navigate-empty/navigate
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check leaf_event_id eq null --check head_is_empty eq true
  control-agent-server api POST "/api/conversations/$S/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_ROOT"}], "run": false}' --expect 200 --quiet
  control-agent-server api GET "/api/conversations/$S/events/search" --query kind=$MSG --query body=QA_F10_ROOT --check items.0.parent_id eq __root__ --save F10.navigate-empty/new-root
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check head_is_empty eq false
  control-agent-server api POST "/api/conversations/$S/navigate" --json '{"event_id": null}' --expect 200 --quiet --check . contains '"leaf_event_id": null'
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check head_is_empty eq true
  ```
  HEAD 在 `null` 和 `head_is_empty: true` 上。 接下来的消息是一个新的根节点 (`parent_id` `__root__`)，并清除标志。 显式形式 `null` 为空，再次 HEAD 空 (它 `F10.restart-persist` 保持为空)。
- **未知、缺失且未经身份验证 (`F10.navigate-errors`)。** HEAD 与上一个项目符号相比是空的，并且必须保持原样。
  ```sh
  control-agent-server api POST "/api/conversations/$S/navigate" --json '{"event_id": "qa-f10-nope"}' --expect 404 \
    --check detail eq 'Unknown event_id: qa-f10-nope' --save F10.navigate-errors/unknown-event
  control-agent-server api POST "/api/conversations/$NOPE/navigate" --json '{}' --expect 404 --check detail eq 'Conversation not found' --save F10.navigate-errors/unknown-conversation
  control-agent-server api POST "/api/conversations/$S/navigate" --expect 422 --check detail.0.loc.0 eq body --check detail.0.type eq missing
  control-agent-server api POST /api/conversations/not-a-uuid/navigate --json '{}' --expect 422 --check detail.0.loc.1 eq conversation_id
  control-agent-server api POST "/api/conversations/$S/navigate" --json "{\"event_id\": \"$E1\"}" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$S" --quiet --check . contains '"leaf_event_id": null'
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check head_is_empty eq true
  ```
  404 `Unknown event_id: qa-f10-nope`，404 `Conversation not found`，422 无正文（空体不是 `{}`）和非法ID，401 无密钥（带有密钥的请求在 `F10.navigate-event` 工作）。 HEAD仍然是空的。
- **返回后的最终响应 (`F10.navigate-final-response`)。**使用 `A` 的叉子，以便 `A` 保留其压缩子弹的历史记录。
  ```sh
  AN=$(control-agent-server api POST "/api/conversations/$A/fork" --expect 201 --field id)
  U1=$(control-agent-server api GET "/api/conversations/$AN/events/search" --query kind=$MSG --query source=user --check items len-eq 1 --field items.0.id)
  control-agent-server api GET "/api/conversations/$AN/agent_final_response" --check response matches '\S'
  control-agent-server api POST "/api/conversations/$AN/navigate" --json "{\"event_id\": \"$U1\"}" --expect 200 --quiet --check leaf_event_id eq "$U1"
  control-agent-server api GET "/api/conversations/$AN/agent_final_response" --check response eq '' --save F10.navigate-final-response/after-navigate
  ```
  一旦HEAD出现在用户的消息中，活跃分支没有智能体答案，所以`agent_final_response`是`""`：像智能体的上下文，标题生成、待办事项检查和停滞检查，它只读取活跃分支，而不是被弃用的答案(`OK`)。 状态保持`finished`，所以
  `POST /run` 在这样的导航之后什么也不做； 发送新消息以重新生成。
- **与DeepSeek（`F10.condense-llm`）压缩。** `A`使用默认的
  `LLMSummarizingCondenser` on DeepSeek flash.
  ```sh
  control-agent-server api GET "/api/conversations/$A" --quiet --check agent.condenser.kind eq LLMSummarizingCondenser
  control-agent-server ws start "/sockets/events/$A" --name qa-f10-condense --duration 180
  control-agent-server ws read qa-f10-condense --wait 15 --kinds ConversationStateUpdateEvent --contains full_state --expect-min 1
  control-agent-server api POST "/api/conversations/$A/condense" --expect 200 --check success eq true --timeout 180 --save F10.condense-llm/condense
  control-agent-server ws stop qa-f10-condense --wait 30 --kinds Condensation --expect-min 1 --save F10.condense-llm/frames
  control-agent-server ws read qa-f10-condense --kinds CondensationRequest --expect-min 1
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$CREQ --check . eq 1
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$COND --check . eq 1
  control-agent-server api GET "/api/conversations/$A/events/search" --query kind=$COND \
    --check items.0.summary matches '\S' --check items.0.forgotten_event_ids len-ge 1 --save F10.condense-llm/condensation
  control-agent-server api GET "/api/conversations/$A" --quiet --check execution_status eq finished
  ```
  调用后返回：`CondensationRequest`和`Condensation`（非空`summary`，至少有一个忘记的事件ID），都推送到socket。 `A`还是`finished`。
- **无请求处理上下文压缩器 (`F10.condense-no-condenser`)。** `NC` 的上下文压缩器被禁用，`NOOP` 的 `no_op` 被禁用。
  ```sh
  control-agent-server api GET "/api/conversations/$NC" --quiet --check agent.condenser eq null
  control-agent-server api GET "/api/conversations/$NOOP" --quiet --check agent.condenser.kind eq NoOpCondenser
  N_NC=$(control-agent-server api GET "/api/conversations/$NC/events/count" --field .)
  N_NOOP=$(control-agent-server api GET "/api/conversations/$NOOP/events/count" --field .)
  control-agent-server api POST "/api/conversations/$NC/condense" --expect 4xx,5xx --check . matches 'No condenser configured' --save F10.condense-no-condenser/disabled
  control-agent-server api POST "/api/conversations/$NOOP/condense" --expect 4xx,5xx --check . matches 'NoOpCondenser does not handle condensation requests' --save F10.condense-no-condenser/no-op
  control-agent-server api GET "/api/conversations/$NC/events/count" --check . eq "$N_NC"
  control-agent-server api GET "/api/conversations/$NOOP/events/count" --check . eq "$N_NOOP"
  control-agent-server api GET "/api/conversations/$NOOP/events/count" --query kind=$CREQ --check . eq 0
  control-agent-server api GET "/api/conversations/$NC" --quiet --check execution_status eq idle
  ```
  两个调用都失败了，原因如下：`Cannot condense conversation: No condenser configured` / `Condenser NoOpCondenser does not handle condensation requests` 检查读取整个主体部分），并且两个对话都没有事件。
- **拒绝状态(`F10.condense-status`)。**缺少上下文压缩器是调用者的配置，而不是服务器故障。
  ```sh
  control-agent-server api GET "/api/conversations/$NC" --quiet --check execution_status eq idle
  control-agent-server api POST "/api/conversations/$NC/condense" --expect 409 --check detail contains 'No condenser configured' --save F10.condense-status/disabled
  control-agent-server api POST "/api/conversations/$NOOP/condense" --expect 409 --check detail contains 'NoOpCondenser does not handle condensation requests' --save F10.condense-status/no-op
  ```
  两个答案都返回状态码409，并附带原因 `detail` (`Cannot condense`)
  对话：...`) and log no traceback: `EventService.condense` 检查
  智能体的上下文压缩器在单步执行之前，将拒绝的路由映射到 409，因为一旦智能体有一个处理请求的上下文压缩器，相同的请求就会成功。
- **无法访问上下文压缩器模型 (`F10.condense-llm-failure`)。** `OFF` 在无法访问的占位符模型上使用默认汇总上下文压缩器。
  ```sh
  control-agent-server api GET "/api/conversations/$OFF" --quiet --check agent.condenser.kind eq LLMSummarizingCondenser
  control-agent-server api POST "/api/conversations/$OFF/condense" --expect 500 --check error_id exists --timeout 120 --save F10.condense-llm-failure/condense
  control-agent-server api GET "/api/conversations/$OFF/events/count" --query kind=$CREQ --check . eq 1
  control-agent-server api GET "/api/conversations/$OFF/events/count" --query kind=$COND --check . eq 0
  control-agent-server api GET "/api/conversations/$OFF" --quiet --check execution_status eq idle
  ```
  500 错误，`error_id`（`exception` 读作 `Unable to compute forgotten events`：总结呼叫和硬复位重试都失败了）。 的
  `CondensationRequest` 保留在日志中未处理，因此下一个智能体步骤将首先尝试压缩； 不存在 `Condensation`，状态仍为 `idle`。
- **未知、格式错误且未经身份验证 (`F10.condense-errors`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$NOPE/condense" --expect 404 --check detail eq 'Conversation not found' --save F10.condense-errors/unknown
  control-agent-server api POST /api/conversations/not-a-uuid/condense --expect 422 --check detail.0.loc.1 eq conversation_id
  control-agent-server api POST "/api/conversations/$A/condense" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$CREQ --check . eq 1
  ```
  404 `Conversation not found`, 422, 401; `A`还有一个
  `CondensationRequest`.
- **问一个附带问题 (`F10.ask-agent`)。**询问`A`它自己的历史
  while its socket is open.
  ```sh
  N_MSG=$(control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$MSG --field .)
  N_ALL=$(control-agent-server api GET "/api/conversations/$A/events/count" --field .)
  N_PELICAN=$(control-agent-server api GET "/api/conversations/$A/events/count" --query body=PELICAN --query source=agent --field .)
  control-agent-server ws start "/sockets/events/$A" --name qa-f10-ask --duration 120
  control-agent-server ws read qa-f10-ask --wait 15 --kinds ConversationStateUpdateEvent --contains full_state --expect-min 1
  control-agent-server api POST "/api/conversations/$A/ask_agent" --json '{"question": "What is the project codename? Answer with the codename only."}' \
    --expect 200 --check response matches '(?i)pelican' --timeout 120 --save F10.ask-agent/ask
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$MSG --check . eq "$N_MSG" --save F10.ask-agent/messages
  control-agent-server api GET "/api/conversations/$A/events/count" --query body=PELICAN --query source=agent --check . eq "$N_PELICAN"
  control-agent-server api GET "/api/conversations/$A/events/count" --check . eq "$N_ALL"
  control-agent-server api GET "/api/conversations/$A" --quiet --check execution_status eq finished
  control-agent-server ws stop qa-f10-ask --kinds MessageEvent,ActionEvent --expect-none --save F10.ask-agent/frames
  ```
  答案指出了代号，只有对话的历史才能知道（这一点是基于事实，而不是措辞）。 没有任何记录：消息计数，计数智能体提及代号的事件（源运行的回复或理由可能已经提及，因此检查之前调用的计数）和总事件计数保持不变。 没有推送：调用之前，套接字是活的（它的
  `full_state` 快照已到达，同类套接字已交付
  `F10.condense-llm` 中的 `Condensation` 帧），`A` 仍然是 `finished`。
- **输入错误、无密钥、无法访问模型 (`F10.ask-agent-errors`)。**
  ```sh
  control-agent-server api POST "/api/conversations/$A/ask_agent" --json '{}' --expect 422 --check detail.0.loc.1 eq question --save F10.ask-agent-errors/missing-question
  control-agent-server api POST "/api/conversations/$A/ask_agent" --json '{"question": "hi"}' --auth none --expect 401
  control-agent-server api POST "/api/conversations/$OFF/ask_agent" --json '{"question": "Reply with one word."}' --expect 500 \
    --check error_id exists --timeout 120 --save F10.ask-agent-errors/offline
  control-agent-server api GET "/api/conversations/$OFF" --quiet --check execution_status eq idle
  ```
  422、401 和 500 状态码，带有 `error_id` 的 `exception`，其中 `question` 携带提供商的连接错误。 `OFF`保持`idle`。
- **在运行中的一個問題`F10.ask-agent-running`).** 开始 `R` 在悬挂的钩子上等待，直到模型上该步骤被阻塞（该钩子已经收到一个调用），然后询问。
  ```sh
  R=$(control-agent-server conversation start --body-json "{\"agent\": $SIDE_AGENT}" --no-autotitle --prompt QA_F10_BUSY --print-id)
  control-agent-server conversation wait "$R" --until running --timeout 30
  control-agent-server sink read --name qa-f10-side --expect-min 1 --expect-max 1 --wait 30
  N_R=$(control-agent-server api GET "/api/conversations/$R/events/count" --field .)
  control-agent-server api POST "/api/conversations/$R/ask_agent" --json '{"question": "QA_F10_SIDE_Q"}' --expect 200 \
    --check response eq QA_F10_SIDE --expect-max-ms 15000 --timeout 60 --save F10.ask-agent-running/ask
  control-agent-server api GET "/api/conversations/$R" --quiet --check execution_status eq running --save F10.ask-agent-running/still-running
  control-agent-server api GET "/api/conversations/$R/events/count" --check . eq "$N_R"
  control-agent-server sink read --name qa-f10-side --contains QA_F10_SIDE_Q --expect-min 1 --expect-max 1
  control-agent-server api POST "/api/conversations/$R/interrupt" --expect 200 --quiet
  control-agent-server conversation wait "$R" --until paused --timeout 30
  control-agent-server api GET "/api/conversations/$R/events/count" --query body=QA_F10_SIDE --check . eq 0
  ```
  当问题到达时，stub的第一个调用（run的步骤）仍然在挂起。 第二个调用在几秒钟内就携带了问题和答案 `QA_F10_SIDE`，因此 `ask_agent` 既不保留状态锁也不等待它。 `R` 仍然 `running`，事件计数不变，中断后（释放运行槽）没有事件携带侧答案。
- **未知对话 (`F10.ask-agent-unknown`).**路线文件404，如压缩和导航。
  ```sh
  control-agent-server api GET /openapi.json --auth none --quiet \
    --check 'paths./api/conversations/{conversation_id}/ask_agent.post.responses.404' exists
  control-agent-server api POST "/api/conversations/$NOPE/ask_agent" --json '{"question": "hi"}' --expect 404 --check detail eq 'Conversation not found' --save F10.ask-agent-unknown/unknown
  ```
  预期：404 `{"detail": "Conversation not found"}`，相同的答案
  condense 给出（对于未知 id，`ConversationService.ask_agent` 返回 `None`，路由器将其映射到 404）。
- **重新启动后的状态 (`F10.restart-persist`)。**重新启动，然后将叉子和 `S` 的空 HEAD 读回。

  需要：`F10.fork-whole`、`F10.fork-named`、`F10.fork-from-event`
  ```sh
  control-agent-server restart
  control-agent-server api POST "/api/conversations/$S/fork" --json "{\"id\": \"$FE\"}" --expect 409 \
    --check detail eq "Conversation with id $FE already exists" --save F10.restart-persist/taken-by-unloaded
  control-agent-server api GET "/api/conversations/$FN" --quiet --check forked_from_conversation_id eq "$S" \
    --check title eq 'QA F10 named fork' --check tags.qa eq f10 --check execution_status eq idle --save F10.restart-persist/named-fork
  control-agent-server api GET "/api/conversations/$FE" --quiet --check forked_from_event_id eq "$E1" --check leaf_event_id eq "$E1"
  control-agent-server api GET "/api/conversations/$FW/events/count" --query body=QA_F10_ONLY_FORK --check . eq 1
  control-agent-server api GET "/api/conversations/$S" --quiet --check . contains '"leaf_event_id": null' --save F10.restart-persist/source
  control-agent-server state cat base_state.json --conversation "$S" --max-chars 200 --check head_is_empty eq true
  control-agent-server api POST "/api/conversations/$S/events" --json '{"role": "user", "content": [{"type": "text", "text": "QA_F10_ROOT2"}], "run": false}' --expect 200 --quiet
  control-agent-server api GET "/api/conversations/$S/events/search" --query kind=$MSG --query body=QA_F10_ROOT2 --check items.0.parent_id eq __root__
  control-agent-server doctor
  ```
  重启后什么都没有加载 `FE` 然而，一个请求的分支 `FE`它的 ID 仍然为 409（服务器检查其目录中的） 已持久化除了已加载的会话之外，还有未加载的会话 `FE` 完整。 分支返回时，它们带着分支线，标题，标签 HEAD 和事件； `S`'s HEAD 它仍然为空，所以重启后第一个消息是一个新的根。
- **在冷漠的对话中进行浓缩和提问 (`F10.restart-cold-calls`)。**重新启动后，`A` 的智能体尚未初始化。
  ```sh
  N_COND=$(control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$COND --field .)
  control-agent-server api POST "/api/conversations/$A/condense" --expect 200 --check success eq true --timeout 180 --save F10.restart-cold-calls/condense
  control-agent-server api GET "/api/conversations/$A/events/count" --query kind=$COND --check . eq $((N_COND + 1))
  control-agent-server api POST "/api/conversations/$A/ask_agent" --json '{"question": "What is the project codename? Answer with the codename only."}' \
    --expect 200 --check response matches '(?i)pelican' --timeout 120 --save F10.restart-cold-calls/ask
  control-agent-server api GET "/api/conversations/$A" --quiet --check execution_status eq finished
  ```
  第二 `Condensation` 已被记录 ask_agent 仍然指代代号
  from the reloaded history (the condenser keeps the first two events, the
  系统提示词和用户的消息）； `A` 保留为 `finished`。

<a id="gotchas"></a>

## 陷阱

- `fork` 使用原始 id 复制事件，因此源和每个 fork 中都存在相同的事件 id； 始终通过对话来确定事件查找范围。
- 分叉共享源的工作目录 (`workspace.working_dir`)：一侧的智能体写入的文件对另一侧可见。 分叉仅获得自己的持久化目录、租约和事件日志。
- 在响应和已持久化元数据中，分叉的 `tags` 是请求的标签，如果省略，则为空集。 标题单独存储并且不添加标签（#4814）。 其他存储的配置（机密、插件、
  `parent_conversation_id`，客户端工具）是从源复制的。 叉子的 `last_user_message_id` 开始于 `null`。
- fork 的 `base_state.json` 编码没有服务器的加密，因此 fork 的智能体模型密钥被丢弃了 (`F10.fork-keeps-credentials`)，并且 fork 无法调用其模型 (`F10.fork-run-memory`)。
- `navigate` 和 `{}` 静默选择空树（智能体在下次运行时丢失所有上下文），因为 `event_id` 默认为 `null`； 根本没有正文的请求是 422。 `head_is_empty` 不属于
  `ConversationInfo`; 从`base_state.json`中读取它。
- HEAD 移动不会在事件套接字上广播（`leaf_event_id` 和
  `head_is_empty` 状态更改会跳过更改回调)； 客户在`navigate`之后重新阅读对话。
- `condense` 为同步，并等待正在运行的步骤完成（它采用状态锁），因此它可能需要与一次模型调用一样长的时间。 它需要一个模型：没有一个可以回答的模型，它就像一个 500 留下了一个悬而未决的问题
  日志中的 `CondensationRequest`。
- `ask_agent` 初始化智能体，因此在没有事件的情况下（未创建消息）与 `SystemPromptEvent` 的第一次运行会写入，即使模型调用失败。 使用消息创建的对话已包含该事件。 与 `condense` 不同，在运行期间它不会等待步骤 (`F10.ask-agent-running`)，
  `fork` 和 `navigate`，采用状态锁（来自源； 这里不开车）。 在尚未重新加载的对话中，它根本不记录任何事件（`F10.ask-agent` 检查总数）。 重启后重新加载时，每次调用都会记录并推送 `stats` `ConversationStateUpdateEvent`，其 `usage_to_metrics` 包含 `ask-agent-llm` 条目，而 GET 的
  `stats` 仅保留存储的 `default` 和 `condenser` 用法（见 DeepSeek； 未断言）。 它将智能体的工具传递给模型，并返回第一个文本块，因此在没有消息的对话中，DeepSeek 的答案是以一个空 `response`（200）的形式返回的。
- `fork` 和 `navigate` 返回 `ConversationInfo`
  `agent.agent_context.skills` 清空，除非 `?include_skills=true`（存储状态保留它们）； `condense` 和 `ask_agent` 没有返回对话。
