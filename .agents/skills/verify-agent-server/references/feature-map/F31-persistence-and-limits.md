<a id="persistence-restart-recovery-leases-and-limits"></a>

# 持久化、重启恢复、租约和限制

消费者可以依赖的服务器生命周期中的所有内容，包括对话、设置、机密和 LLM 角色，都存储在磁盘上，并在优雅重启或崩溃后以不变的形式读取。 进程终止时处于中间工具调用的对话返回 `error`，并应答了中断的呼叫； 每个加载的对话都通过一个拥有
`owner_lease.json` 租约，因此共享相同对话目录的第二个服务器可以读取它，但不能驱动它，直到所有者死亡或停止更新； 空闲会话在 TTL 之后被卸载，并在访问时再次加载； 创建对话需要一个空闲槽位； 机密不以明文形式存储任何内容； 并且设置这些限制的配置文件和 `OH_*` 变量在启动时应用（或拒绝）。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_lease.py`、`openhands-agent-server/openhands/agent_server/conversation_service.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/config.py`、`openhands-agent-server/openhands/agent_server/env_parser.py`、`openhands-agent-server/openhands/agent_server/api.py`、`openhands-agent-server/openhands/agent_server/persistence/`、`openhands-agent-server/openhands/agent_server/storage/`、`openhands-sdk/openhands/sdk/conversation/state.py`、`openhands-sdk/openhands/sdk/conversation/event_store.py`

需求：`llm`、`tmux`

路线：None

<a id="sub-features"></a>

## 子功能

- `F31.lease-claimed`：加载会话在其目录中写入 `owner_lease.json`，其中包含第 1 代、服务器的 pid 和主机，以及提前约 45 秒的到期时间。
- `F31.lease-renewed`：当服务器存在时，租约的 `expires_at` 在 15 秒内向前移动，具有相同的所有者和代。
- `F31.lease-released-graceful`：优雅重启会删除所有加载对话的租约，库读取不会再次声称它，而是在新的 pid 下生成 1。
- `F31.lease-dead-owner-takeover`：在SIGKILL之后，租约仍然命名失效的pid； 重新启动的服务器在第 2 代的第一次加载时接管它并记录接管。
- `F31.crash-tool-call`对话 SIGKILLed during a 工具调用在启动时再次加载，然后回来 `error` with one `AgentErrorEvent` 接听中断的电话和没有观测结果，并将错误传递给模型。
- `F31.state-survives-restarts`：对话标题、标签和事件，设置，一个已存储的机密，以及在优雅重启后和SIGKILL后读取不变的LLM用户资料。
- `F31.no-plaintext-at-rest`在实际模型运行之后，提供者密钥，一个存储的机密 and a conversation 机密在运行中从未出现过已持久化文件或服务器日志，但服务器仍然发放提供商密钥和存储的密钥机密并保持对话机密加密的注册表。
- `F31.second-instance-catalog`：另一个共享会话目录列表、计数和读取会话的服务器，它在启动时存在会话，但不声称他们的租约。
- `F31.second-instance-lease-held`：当主人活着时，第二台服务器无法加载对话：事件读取、发送消息、`/run`和`agent_final_response`返回404，PATCH返回`success: false`，暂停、中断和DELETE返回400，其事件套接字返回4004，没有任何变化。
- `F31.second-instance-takeover` 当拥有者是 SIGKILLed 时，第二台服务器立刻接管对话（生成 2，其 pid），并重启的拥有者现在拒绝了。
- `F31.takeover-keeps-metadata`：在第二个服务器启动后，所有者存储的标题在第二个服务器接管后仍然存在，在其 GET 和 `meta.json` 中。
- `F31.lease-expiry-fencing` 一旦拥有者停止续费（冻结状态，pid存活），租约在到期后就会失效，并且在恢复写操作时会被拒绝，且永远不会写入磁盘。
- `F31.fenced-write-no-trace`：因失去所有权而被拒绝的写入会回答 4xx 并且不留下任何痕迹：陈旧所有者自己的 GET 不会报告被拒绝的标题。
- `F31.lease-disabled`：`lease_ttl_seconds` 0 时不写入租约文件，第二个服务器同时加载和写入相同的会话。
- `F31.idle-eviction`: 在其 TTL (租约被删除，`Evicted idle` 登记) 后，一个空闲对话在第一次过期后被卸载，保留其标题和状态，下次访问时以相同事件重新加载。
- `F31.eviction-skips-busy`：同一通道与打开的事件套接字和加载的正在运行的套接字保持对话； 一旦套接字关闭并且运行中断，下一次就会卸载两者。
- `F31.create-capacity`：每占用一个运行槽，`POST /api/conversations` 都会回答 429 并且不会在磁盘或目录中创建任何内容； 一旦插槽空闲，相同的请求就会成功。
- `F31.config-precedence`：应用配置文件，并且 `OH_*` 变量覆盖同一字段（通过租约 TTL 查看）。
- `F31.config-null-override`: `OH_<FIELD>_IS_NONE=1` 清除配置文件设置的值，因为非 null `OH_*` 值替换它（通过 `/server_info` 中的 `app_backend_public_url` 看到）。
- `F31.config-invalid-fails-fast`：配置文件中的非数字 `OH_MAX_CONCURRENT_RUNS` 或超出范围的限制会在启动期间停止服务器，而不是使用默认值提供服务。
- `F31.config-silent-env`：除了`OH_*`布尔值之外，`1`/`true`读作False（它会覆盖配置文件中的`true`），而`Literal`变量不在其选项范围内则会回退到默认值。 无论哪种方式，服务器都会启动，而文件中相同的无效选择会停止启动。
- `F31.tmux-dir-cleanup`：默认为每个进程 `TMUX_TMPDIR` 的服务器在停止时会删除该目录。
- `F31.storage-retention`: 在Docker运行时，`conversation_storage_retention_days`停止对话会保留超过限制的事件（可读、恢复和代理路由410，运行目录消失），`conversation_storage_disk_budget`停止工作区的git忽略目录，同时保留其文件、忽略的单独文件和嵌套的Git检查出。 运行时仍然是可恢复的。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- 没有自己的路由：每颗子弹都结合了其他家庭拥有的路由（对话及其事件，PATCH，`/run`，暂停，中断，DELETE，事件套接字，设置，机密，LLM 角色）以及消费者仅作为操作员遇到的过程事件：优雅重启（`restart`），崩溃（`restart --hard`），冻结进程（`kill -STOP`），以及同一个对话目录上的第二个服务器（`launch --new --share-conversations-from RUN`）。
- 已持久化布局，用 `state ls|cat|grep` 阅读：每个对话
  `<conversations_path>/<id hex>/meta.json`（标题、标签、加密机密），
  `base_state.json`（执行状态，智能体，加密机密注册表），
  `events/`，并且在加载时，`owner_lease.json` (`owner_instance_id`, `generation`, `expires_at`, `owner_host`,
  `owner_pid`）由`.owner_lease.lock`守护； 下 `OH_PERSISTENCE_DIR`
  `settings.json`、`secrets.json` 和 `profiles/`。 服务器日志（`logs --grep`）是驱逐和接管的唯一视图。
- 配置（`OPENHANDS_AGENT_SERVER_CONFIG_PATH` 处的 JSON 文件，被 `OH_*` 变量覆盖）：`lease_ttl_seconds` /
  `OH_LEASE_TTL_SECONDS`（45；0 禁用租赁），
  `conversation_idle_ttl_seconds` / `OH_CONVERSATION_IDLE_TTL_SECONDS` (1200;
  `null` 或 `OH_CONVERSATION_IDLE_TTL_SECONDS_IS_NONE=1`，禁用驱逐），
  `max_concurrent_runs` / `OH_MAX_CONCURRENT_RUNS` (10)、`OH_SECRET_KEY`（REST 处机密的密码）、`TMUX_TMPDIR`，并且仅 Docker 运行时 `conversation_storage_retention_days` 和
  `conversation_storage_disk_budget`（默认情况下未设置）。 如何解析任何 `OH_*` 布尔值或选择可以通过 `deferred_init` / 查看
  `OH_DEFERRED_INIT` 和 `conversation_runtime` / `OH_CONVERSATION_RUNTIME` (`F31.config-silent-env`)。 CLI写入文件(`launch|restart --config-json`)并传递变量(`--env`)；
  `control-agent-server config` 显示两者。
- SDK和TypeScript客户端：没有自己的方法。 `RemoteConversation` 重新启动后重新连接其事件套接字，并查看这些项目符号断言的状态和事件； 在共享存储上运行多台服务器的编排器依靠租约来为每个对话保留一个所有者。
- Agent Canvas（仅限上下文）：沙箱重新启动后列出的对话，以及当沙箱达到其运行限制时列出的 `429`。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  设置 `$DEEPSEEK_API_KEY`（在 `F31.no-plaintext-at-rest` 中运行一个真实模型），
  `tmux` 已安装（`F31.crash-tool-call` 中的终端工具），`jq` 位于 `PATH` 上。
- 许多项目符号重新启动此运行（`restart`、`restart --hard`、
  `restart --reset-config --config-json ...`); 后面的项目符号设置了他们需要的配置，因此运行以其默认值结束。 需要第二个服务器的项目符号用 `--share-conversations-from` 启动它并在结束之前停止它（如果命令首先失败，则 `trap` 停止它）； 证据保存于
  `--run "$B"` 落在该运行的 `evidence/` 中。
- 服务器的 pid 来自运行的 `run.json` （没有动词打印它），并且
  `kill -STOP`/`kill -CONT` 冻结并恢复此运行自己的服务器
  `F31.lease-expiry-fencing`.
- 下面的块设置 DeepSeek 闪存、两个机密值、事件类型、两个 `llm-stub` 提供程序（`qa-f31-tool` 请求 `terminal` `sleep 300`；
  `qa-f31-hang` 将每个调用挂起 600 秒），每个调用都有一个内联智能体、一个工作区目录和 `T`，即工具存根上的对话。

  ```sh
  control-agent-server llm preset deepseek
  export QA_F31_STORED=qa-f31-stored-secret-8c41
  export QA_F31_CONV=qa-f31-conversation-secret-5e07
  ACTION_KIND=openhands.sdk.event.llm_convertible.action.ActionEvent
  OBSERVATION_KIND=openhands.sdk.event.llm_convertible.observation.ObservationEvent
  AGENT_ERROR_KIND=openhands.sdk.event.llm_convertible.observation.AgentErrorEvent
  TOOL=$(control-agent-server fixture llm-stub --name qa-f31-tool --step 'tool:terminal:{"command":"sleep 300"}' --print-path)
  TOOL_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$TOOL/v1\", \"num_retries\": 0}, \"tools\": [{\"name\": \"terminal\"}]}"
  HANG=$(control-agent-server fixture llm-stub --name qa-f31-hang --step hang:600 --print-path)
  HANG_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG/v1\", \"num_retries\": 0}, \"tools\": []}"
  QA_WS="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f31-workspace"
  mkdir -p "$QA_WS"
  T=$(control-agent-server conversation start --body-json "{\"agent\": $TOOL_AGENT}" --no-autotitle --print-id)
  ```

- **负载时索赔的租赁 (`F31.lease-claimed`)。**创建对话会加载它。
  ```sh
  L=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  NOW=$(date +%s)
  PID=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  control-agent-server state cat owner_lease.json --conversation "$L" --check generation eq 1 --check owner_pid eq "$PID" \
    --check owner_host eq "$(hostname)" --check owner_instance_id matches '^[0-9a-f]{32}$' \
    --check expires_at gt "$((NOW + 40))" --check expires_at le "$((NOW + 46))"
  ```
  租户为服务器的 pid 和 host，生成版本 1，并且大约在创建后 45 秒后过期。
- **续租 (`F31.lease-renewed`).**服务器的更新计时器（每 15 秒）正在测试中，因此此项目符号每秒轮询一次文件。

  需要：`F31.lease-claimed`
  ```sh
  E1=$(control-agent-server state cat owner_lease.json --conversation "$L" | jq -r .content.expires_at)
  OWNER=$(control-agent-server state cat owner_lease.json --conversation "$L" | jq -r .content.owner_instance_id)
  T0=$SECONDS
  until control-agent-server state cat owner_lease.json --conversation "$L" --check expires_at gt "$E1" >/dev/null; do
    test $((SECONDS - T0)) -le 17
    sleep 1
  done
  control-agent-server state cat owner_lease.json --conversation "$L" --check expires_at gt "$E1" --check owner_instance_id eq "$OWNER" \
    --check generation eq 1 --check expires_at gt "$(($(date +%s) + 40))"
  ```
  `expires_at` 17秒后，大约在45秒后。 所有者和生成体都存在。
- **优雅释放(`F31.lease-released-graceful`)。**重新启动，从目录中读取对话，然后加载它。

  需要：`F31.lease-claimed`
  ```sh
  PID1=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  control-agent-server restart
  PID2=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  test "$PID2" != "$PID1"
  control-agent-server state ls --conversation "$L" owner_lease.json --expect-count 0
  control-agent-server api GET "/api/conversations/$L" --expect 200 --check id eq "$L" --quiet
  control-agent-server state ls --conversation "$L" owner_lease.json --expect-count 0
  control-agent-server api PATCH "/api/conversations/$L" --json '{"title": "QA F31 lease"}' --expect 200 --check success eq true
  control-agent-server state cat owner_lease.json --conversation "$L" --check generation eq 1 --check owner_pid eq "$PID2"
  ```
  关闭删除了租约。 GET (一次目录读取) 不加载对话。 PATCH 它加载了它，并在新的 pid 下声称了一个全新的生成 1。
- **死亡所有者接管 (`F31.lease-dead-owner-takeover`)。** SIGKILL 业主； 没有任何内容释放租约。

  需要：`F31.lease-claimed`
  ```sh
  DEAD=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  NT=$(control-agent-server logs --grep 'Taking over conversation' | jq .total_matching)
  control-agent-server restart --hard
  if kill -0 "$DEAD" 2>/dev/null; then false; fi
  PID3=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  control-agent-server state cat owner_lease.json --conversation "$L" --check owner_pid eq "$DEAD" --check generation eq 1 \
    --check expires_at gt "$(date +%s)"
  control-agent-server api GET "/api/conversations/$L/events/count" --expect 200 --save F31.lease-dead-owner-takeover/first-load
  control-agent-server state cat owner_lease.json --conversation "$L" --check owner_pid eq "$PID3" --check generation eq 2
  control-agent-server logs --grep 'Taking over conversation' --expect-min $((NT + 1))
  ```
  剩余的租约指定了死的 pid，并且仍然有效。 重启后的第一次加载就立刻接管了（同一个主机，进程消失），并记录了 `Taking over conversation lease ... from dead owner`。
- **在工具调用 (`F31.crash-tool-call`) 期间发生崩溃。** `T`的模型要求
  `terminal` `sleep 300`; 当服务器运行时，端点 SIGKILLed，然后重写 stub 以调用 `finish`，然后运行继续。
  ```sh
  control-agent-server conversation send "$T" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$T/run" --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$T/events/count" --query kind=$ACTION_KIND --check . eq 1 --until-ok 30
  TCALL=$(control-agent-server api GET "/api/conversations/$T/events/search" --query kind=$ACTION_KIND --field items.0.tool_call_id)
  control-agent-server state cat base_state.json --conversation "$T" --check execution_status eq running
  control-agent-server restart --hard
  PIDT=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  control-agent-server state cat owner_lease.json --conversation "$T" --check owner_pid eq "$PIDT"
  control-agent-server api GET "/api/conversations/$T" --check execution_status eq error --quiet --save F31.crash-tool-call/get
  control-agent-server api GET "/api/conversations/$T/events/search" --query kind=$AGENT_ERROR_KIND --check items len-eq 1 \
    --check items.0.tool_call_id eq "$TCALL" --check items.0.error contains 'A restart occurred while this tool was in progress' \
    --save F31.crash-tool-call/agent-error
  control-agent-server api GET "/api/conversations/$T/events/count" --query kind=$OBSERVATION_KIND --check . eq 0
  control-agent-server fixture llm-stub --name qa-f31-tool --step 'tool:finish:{"message":"QA_F31_RESUMED"}'
  control-agent-server api POST "/api/conversations/$T/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$T" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$T/agent_final_response" --check response eq QA_F31_RESUMED
  control-agent-server sink read --name qa-f31-tool --contains 'A restart occurred while this tool was in progress' --expect-min 1 \
    --save F31.crash-tool-call/resumed-request
  ```
  `base_state.json`表示`running`服务器死亡时。 在任何请求之前，startup加载`T`（它的租约已经命名了新的pid），标记它
  `error` 并为打开的 `tool_call_id` 添加一个 `AgentErrorEvent`（“此工具正在进行时发生了重新启动......”），没有观测结果。 恢复的模型请求携带该错误作为工具结果，并且 `T` 完成。
- **状态在重启后存活`F31.state-survives-restarts`).** 一个对话，一个设置字段，一个存储机密 and the two DeepSeek 在优雅重启后读取的配置，以及再次在重启后读取的配置 SIGKILL.
  ```sh
  ST=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 state' --tag env=qa-f31 --prompt 'qa-f31-state-marker' --no-run --print-id)
  NS=$(control-agent-server api GET "/api/conversations/$ST/events/count" --field .)
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f31": "kept"}}' --expect 200 --check misc_settings.qa_f31 eq kept
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F31_STORED\", \"value\": \"$QA_F31_STORED\"}" --expect 200
  for MODE in graceful hard; do
    if [ "$MODE" = hard ]; then control-agent-server restart --hard; else control-agent-server restart; fi
    control-agent-server api GET "/api/conversations/$ST" --check title eq 'QA F31 state' --check tags.env eq qa-f31 \
      --check execution_status eq idle --quiet --save "F31.state-survives-restarts/conversation-$MODE"
    control-agent-server api GET "/api/conversations/$ST/events/count" --check . eq "$NS"
    control-agent-server conversation events "$ST" --kinds MessageEvent --contains qa-f31-state-marker --expect-count 1
    control-agent-server api GET /api/settings --check misc_settings.qa_f31 eq kept --check agent_settings.llm.model eq deepseek/deepseek-flash --quiet
    control-agent-server api GET /api/settings/secrets/QA_F31_STORED --check . eq "$QA_F31_STORED"
    control-agent-server api GET /api/profiles --check active_profile eq deepseek-flash --check profiles len-eq 2 --save "F31.state-survives-restarts/profiles-$MODE"
  done
  ```
  两次读取标题、标签、`idle` 状态、事件计数和排队消息、misc 设置、active 模型，以及机密的值，两次读取都未改变。
- **明文中没有任何内容机密 (`F31.no-plaintext-at-rest`)。**真实的 DeepSeek 与对话机密一起运行，然后搜索服务器写入的每个文件（`home/`，其中保存 `OH_PERSISTENCE_DIR`，`server/`，其中保存对话）和服务器日志。
  ```sh
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F31_STORED\", \"value\": \"$QA_F31_STORED\"}" --expect 200
  M=$(control-agent-server conversation start --tools none --no-autotitle --secret "QA_F31_CONV=$QA_F31_CONV" \
    --prompt 'Reply with the single word ok, then finish.' --wait --until finished --timeout 180 --print-id)
  control-agent-server api GET "/api/conversations/$M" --check execution_status eq finished --quiet
  control-agent-server state cat base_state.json --conversation "$M" --check secret_registry.secret_sources.QA_F31_CONV.value exists \
    --not-contains "$QA_F31_CONV"
  control-agent-server state grep QA_F31_CONV --glob 'server/workspace/conversations/**/*'
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --quiet
  control-agent-server api GET /api/settings/secrets/QA_F31_STORED --check . eq "$QA_F31_STORED"
  for NAME in DEEPSEEK_API_KEY QA_F31_STORED QA_F31_CONV; do
    control-agent-server state grep --env-value "$NAME" --glob 'home/**/*' --expect-none
    control-agent-server state grep --env-value "$NAME" --glob 'server/**/*' --expect-none
  done
  control-agent-server logs --grep "$DEEPSEEK_API_KEY" --expect-none
  control-agent-server logs --grep "$QA_F31_STORED" --expect-none
  control-agent-server logs --grep "$QA_F31_CONV" --expect-none
  ```
  运行已完成在 DeepSeek flash. 的机密注册表存储对话机密其值（加密过的） 机密该名称存在于会话文件中（搜索功能可用），服务器仍然发放提供者密钥和存储的密钥机密。 None 这三种值中的任何一种都出现在这里已持久化文件 (设置，) 机密，profiles, `meta.json`,
  `base_state.json`，事件）或在服务器日志中。 没有路由读回对话机密，因此此处未观察到其解密。
- **第二个服务器读取目录 (`F31.second-instance-catalog`)。** `X` 已加载到该服务器上； `B` 从相同的对话目录开始。
  ```sh
  X=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 shared' --prompt 'qa-f31-shared-marker' --no-run --print-id)
  COLD=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$X/events/count" --expect 200
  PIDA=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  NC=$(control-agent-server api GET /api/conversations/count --field .)
  B=$(control-agent-server launch --new --name f31-catalog --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  control-agent-server api GET /api/conversations/count --run "$B" --check . eq "$NC" --save F31.second-instance-catalog/count
  control-agent-server api GET /api/conversations/search --run "$B" --query limit=100 --check items contains "$X" --check items contains "$COLD" --quiet
  control-agent-server api GET "/api/conversations/$X" --run "$B" --expect 200 --check title eq 'QA F31 shared' --check execution_status eq idle \
    --save F31.second-instance-catalog/get
  control-agent-server api GET "/api/conversations/$COLD" --run "$B" --expect 200 --check id eq "$COLD" --quiet
  control-agent-server state cat owner_lease.json --conversation "$X" --check owner_pid eq "$PIDA" --check generation eq 1
  control-agent-server state ls --conversation "$COLD" owner_lease.json --expect-count 0
  control-agent-server stop --run "$B"
  trap - EXIT
  ```
  `B` 统计并列出相同的对话，并从磁盘读取 `X` 的标题和状态。 它的读取没有声明任何内容：`X` 的租约仍然命名该服务器，并且 `COLD`（自重新启动后已卸载）仍然没有租约。
- **当主人活着时第二个服务器被拒绝(`F31.second-instance-lease-held`)。**新的 `B` 尝试了各种加载方式 `X`。

  需要：`F31.second-instance-catalog`
  ```sh
  B=$(control-agent-server launch --new --name f31-held --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  OWNER=$(control-agent-server state cat owner_lease.json --conversation "$X" | jq -r .content.owner_instance_id)
  NX=$(control-agent-server api GET "/api/conversations/$X/events/count" --field .)
  control-agent-server api GET "/api/conversations/$X/events/search" --run "$B" --expect 404 --check detail eq "Conversation not found: $X" \
    --save F31.second-instance-lease-held/events-search
  control-agent-server api GET "/api/conversations/$X/events/count" --run "$B" --expect 404
  control-agent-server api POST "/api/conversations/$X/events" --run "$B" --json '{"role": "user", "content": [{"type": "text", "text": "qa-f31-from-b"}], "run": false}' --expect 404
  control-agent-server api POST "/api/conversations/$X/run" --run "$B" --expect 404 --save F31.second-instance-lease-held/run
  control-agent-server api GET "/api/conversations/$X/agent_final_response" --run "$B" --expect 404
  control-agent-server api PATCH "/api/conversations/$X" --run "$B" --json '{"title": "QA F31 from B"}' --expect 200 --check success eq false \
    --save F31.second-instance-lease-held/patch
  control-agent-server api POST "/api/conversations/$X/pause" --run "$B" --expect 400
  control-agent-server api POST "/api/conversations/$X/interrupt" --run "$B" --expect 400
  control-agent-server api DELETE "/api/conversations/$X" --run "$B" --expect 400 --save F31.second-instance-lease-held/delete
  control-agent-server ws listen "/sockets/events/$X" --run "$B" --expect-close 4004 --duration 10 --save F31.second-instance-lease-held/socket
  control-agent-server api GET "/api/conversations/$X" --run "$B" --expect 200 --check title eq 'QA F31 shared' --quiet
  control-agent-server state cat owner_lease.json --conversation "$X" --check owner_instance_id eq "$OWNER" --check generation eq 1
  control-agent-server api GET "/api/conversations/$X" --check title eq 'QA F31 shared' --quiet
  control-agent-server api GET "/api/conversations/$X/events/count" --check . eq "$NX"
  control-agent-server state grep qa-f31-shared-marker --glob "server/workspace/conversations/${X//-/}/**/*"
  control-agent-server state grep qa-f31-from-b --glob "server/workspace/conversations/${X//-/}/**/*" --expect-none
  control-agent-server stop --run "$B"
  trap - EXIT
  ```
  `B` 上的每次加载调用都会报告对话缺失（404、400 或其他错误）
  `success: false`，socket close 4004 `Conversation not found`），未知 id 得到的答案相同，尽管 `B` 的 GET 仍然从目录中读取它。 业主的租约、标题、事件计数和事件日志均未更改，并且 `X` 未被删除。
- **继承 `F31.second-instance-takeover`).**  `B` 等待此服务器  SIGKILLed 并且重启了。

  需要：`F31.second-instance-catalog`
  ```sh
  B=$(control-agent-server launch --new --name f31-takeover --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  PIDB=$(jq -r .pid "$B/run.json")
  NX=$(control-agent-server api GET "/api/conversations/$X/events/count" --field .)
  NB=$(control-agent-server logs --run "$B" --grep 'Taking over conversation' | jq .total_matching)
  control-agent-server api GET "/api/conversations/$X/events/count" --run "$B" --expect 404
  control-agent-server restart --hard
  control-agent-server api GET "/api/conversations/$X/events/count" --run "$B" --expect 200 --check . eq "$NX" --save F31.second-instance-takeover/events-count
  control-agent-server state cat owner_lease.json --conversation "$X" --check owner_pid eq "$PIDB" --check generation eq 2
  control-agent-server logs --run "$B" --grep 'Taking over conversation' --expect-min $((NB + 1))
  control-agent-server conversation events "$X" --run "$B" --kinds MessageEvent --contains qa-f31-shared-marker --expect-count 1
  control-agent-server api GET "/api/conversations/$X/events/count" --expect 404 --save F31.second-instance-takeover/old-owner-refused
  control-agent-server stop --run "$B"
  trap - EXIT
  control-agent-server state ls --conversation "$X" owner_lease.json --expect-count 0
  ```
  在那一刻之前，拒绝了 `B` loads `X` 在...之后 SIGKILL (同主机，已死亡的进程ID，租约未过期)与生成2版本相同，但包含相同的事件。 重启的拥有者现在会收到 404。 `B`优雅的停顿释放了租约。
- **接管保留更新的元数据 (`F31.takeover-keeps-metadata`)，已知错误。**所有者在`B`启动后重命名`Y`； 然后主人死了并且`B`拿走了
  `Y` 结束。
  ```sh
  Y=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 before B' --no-run --print-id)
  B=$(control-agent-server launch --new --name f31-meta --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  PIDB=$(jq -r .pid "$B/run.json")
  control-agent-server api PATCH "/api/conversations/$Y" --json '{"title": "QA F31 after B"}' --expect 200 --check success eq true
  control-agent-server state cat meta.json --conversation "$Y" --check title eq 'QA F31 after B'
  control-agent-server restart --hard
  control-agent-server api GET "/api/conversations/$Y/events/count" --run "$B" --expect 200
  control-agent-server state cat owner_lease.json --conversation "$Y" --check owner_pid eq "$PIDB" --check generation eq 2
  control-agent-server state cat meta.json --conversation "$Y" --check title eq 'QA F31 after B'  # bug content.title eq 'QA F31 在 B' 之前
  control-agent-server api GET "/api/conversations/$Y" --run "$B" --check title eq 'QA F31 after B' --save F31.takeover-keeps-metadata/get-after-takeover  # bug：状态 eq 200 && response.body.title eq 'QA F31 before B'
  ```
  预期：`B` 报告并保留所有者最后存储的标题。 的
  所有者的重命名已达到 `meta.json`，并且 `B` 的第一次加载在两个 `# bug` 断言之前接管了 `Y`（`B` 的 pid 下的第 2 代）。 今天
  `B` 从它在启动时读取的目录快照加载 `Y` 并立即保存它（`_start_event_service` 调用 `save_meta()`； 没有任何内容调用 `EventService.load_meta()`)，因此 `meta.json` 被重写为
  `QA F31 before B`（第一个断言在那里失败）并且`B`的GET也报告了这一点：所有者后来的所有权（和`updated_at`）丢失了。 不需要接管：所有者释放后，`B` 上的普通第 1 代负载
  `Y` 通过正常重启（或空闲驱逐）以同样的方式恢复它。 `trap` 停止 `B`。
- **租约到期限制了冻结的所有者 (`F31.lease-expiry-fencing`)。**租约 20 秒后，该服务器被 SIGSTOP 冻结，因此停止续订
  while its pid stays alive.
  ```sh
  control-agent-server restart --reset-config --config-json '{"lease_ttl_seconds": 20}'
  F=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 fenced' --prompt 'qa-f31-fence-marker' --no-run --print-id)
  PIDA=$(jq -r .pid "$AGENT_SERVER_VERIFY_RUN/run.json")
  control-agent-server state cat owner_lease.json --conversation "$F" --check owner_pid eq "$PIDA" --check generation eq 1 \
    --check expires_at le "$(($(date +%s) + 21))"
  B=$(control-agent-server launch --new --name f31-fence --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --print-run)
  thaw_and_stop() {
    kill -CONT "$PIDA" 2>/dev/null || true
    control-agent-server stop --run "$B" >/dev/null 2>&1 || true
  }
  trap thaw_and_stop EXIT
  PIDB=$(jq -r .pid "$B/run.json")
  NF=$(control-agent-server api GET "/api/conversations/$F/events/count" --field .)
  control-agent-server api GET "/api/conversations/$F/events/count" --run "$B" --expect 404
  kill -STOP "$PIDA"
  T0=$SECONDS
  until control-agent-server state cat owner_lease.json --conversation "$F" --check expires_at lt "$(date +%s)" >/dev/null; do
    test $((SECONDS - T0)) -le 30
    sleep 1
  done
  control-agent-server api GET "/api/conversations/$F/events/count" --run "$B" --expect 200 --check . eq "$NF"
  control-agent-server state cat owner_lease.json --conversation "$F" --check owner_pid eq "$PIDB" --check generation eq 2
  kill -CONT "$PIDA"
  control-agent-server api GET /alive --auth none --expect 200
  control-agent-server api POST "/api/conversations/$F/events" --json '{"role": "user", "content": [{"type": "text", "text": "qa-f31-stale-write"}], "run": false}' \
    --expect 4xx,5xx --save F31.lease-expiry-fencing/stale-write
  control-agent-server api GET "/api/conversations/$F/events/count" --check . eq "$NF"
  control-agent-server state grep qa-f31-fence-marker --glob "server/workspace/conversations/${F//-/}/**/*"
  control-agent-server state grep qa-f31-stale-write --glob "server/workspace/conversations/${F//-/}/**/*" --expect-none
  control-agent-server api GET "/api/conversations/$F/events/count" --run "$B" --check . eq "$NF"
  control-agent-server api PATCH "/api/conversations/$F" --run "$B" --json '{"title": "QA F31 new owner"}' --expect 200 --check success eq true
  control-agent-server state cat meta.json --conversation "$F" --check title eq 'QA F31 new owner'
  control-agent-server stop --run "$B"
  trap - EXIT
  ```
  `B` 在租约有效期间被拒绝； 一旦过期（冻结的 pid 仍然存在，因此没有早期接管）`B` 接管 `F` 作为第 2 代。 恢复后，旧所有者仍然加载了 `F`，但其消息被拒绝：没有任何内容到达磁盘或旧所有者自己的事件计数，而
  `B` 的写入区域。 任何错误状态都会通过这里； 状态本身（409）由`F31.fenced-write-no-trace`检查。 `B` 的停止释放租约。
- **拒绝写入不留下痕迹(`F31.fenced-write-no-trace`)。**上一个项目符号的旧所有者尝试重命名 `F`。

  需要：`F31.lease-expiry-fencing`
  ```sh
  PS=$(control-agent-server api PATCH "/api/conversations/$F" --json '{"title": "QA F31 stale owner"}' --expect 4xx,5xx \
    --save F31.fenced-write-no-trace/patch | jq .status)
  control-agent-server state cat meta.json --conversation "$F" --check title eq 'QA F31 new owner'
  control-agent-server api GET "/api/conversations/$F" --check title ne 'QA F31 stale owner' --save F31.fenced-write-no-trace/get
  echo "refused PATCH answered $PS"
  control-agent-server assert --value "$PS" --check . eq 409
  ```
  的 PATCH 返回 409 `detail`  `Conversation is owned by another agent server instance; the write was refused`，一切都毫无变化：老赖自己还是老赖 GET 它保留了原来的标题，因为元数据只有在受保护的保存成功后才会存储在内存中。 拒绝本身（任何错误状态）和 `meta.json` keeping `QA F31 new owner` 是阳性对照：受控保存拒绝写入。 的 PATCH 状态，保留 `PS`最后一个检查。  这个过期的拥有者会一直加载会话，并且以同样的方式拒绝所有的写操作，即使新拥有者停止了，租赁文件也不存在，同时它会继续提供其过期的内存事件（新拥有者会追加）。
- **禁用租赁 (`F31.lease-disabled`)。**两台服务器都运行
  `lease_ttl_seconds` 0.
  ```sh
  control-agent-server restart --reset-config --config-json '{"lease_ttl_seconds": 0}'
  D=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 unleased' --prompt 'qa-f31-unleased-marker' --no-run --print-id)
  control-agent-server state ls --conversation "$D" meta.json --expect-count 1
  control-agent-server state ls --conversation "$D" owner_lease.json --expect-count 0
  ND=$(control-agent-server api GET "/api/conversations/$D/events/count" --field .)
  B=$(control-agent-server launch --new --name f31-unleased --share-conversations-from "$AGENT_SERVER_VERIFY_RUN" --config-json '{"lease_ttl_seconds": 0}' --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  control-agent-server api POST "/api/conversations/$D/events" --run "$B" --json '{"role": "user", "content": [{"type": "text", "text": "qa-f31-from-b"}], "run": false}' \
    --expect 200 --save F31.lease-disabled/second-server-write
  control-agent-server api GET "/api/conversations/$D/events/count" --run "$B" --check . gt "$ND"
  control-agent-server state grep qa-f31-from-b --glob "server/workspace/conversations/${D//-/}/**/*"
  control-agent-server api PATCH "/api/conversations/$D" --json '{"title": "QA F31 unleased A"}' --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$D/events/count" --check . eq "$ND"
  control-agent-server state ls --conversation "$D" owner_lease.json --expect-count 0
  control-agent-server stop --run "$B"
  trap - EXIT
  ```
  从不写入租约文件。 `B` loads `D` 同时在磁盘上也添加一条消息，而这个服务器则保持它加载并重命名它。 它们的内存视图
  不同（该服务器仍然计数 `ND` 个事件）：租赁是唯一安全的
  每个对话目录只有一台服务器。
- **闲置驱逐 (`F31.idle-eviction`).**空闲 5 秒 TTL； 逐出循环每 `max(60, ttl/2)` 秒运行一次，首先是启动后约 60 秒，因此此项目符号轮询最多 90 秒。 它还在传递之前安排下一个项目符号的两个繁忙对话：`WB` 具有打开的事件套接字，`R` 在挂起的存根上运行。
  ```sh
  control-agent-server restart --reset-config --config-json '{"conversation_idle_ttl_seconds": 5}'
  NE=$(control-agent-server logs --grep 'Evicted idle' | jq .total_matching)
  I=$(control-agent-server conversation start --tools none --no-autotitle --title 'QA F31 idle' --prompt 'qa-f31-idle-marker' --no-run --print-id)
  NI=$(control-agent-server api GET "/api/conversations/$I/events/count" --field .)
  WB=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  R=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
  control-agent-server ws start "/sockets/events/$WB" --name f31-subscribed --duration 300
  control-agent-server conversation send "$R" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$R/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$R" --until running --timeout 60
  control-agent-server state ls --conversation "$I" owner_lease.json --expect-count 1
  T0=$SECONDS
  until control-agent-server state ls --conversation "$I" owner_lease.json --expect-count 0 >/dev/null; do
    test $((SECONDS - T0)) -le 90
    sleep 2
  done
  control-agent-server logs --grep 'Evicted idle' --expect-min $((NE + 1))
  control-agent-server api GET "/api/conversations/$I" --check title eq 'QA F31 idle' --check execution_status eq idle --quiet --save F31.idle-eviction/get-evicted
  control-agent-server api GET /api/conversations/search --query status=idle --query limit=100 --check items contains "$I" --quiet
  control-agent-server state ls --conversation "$I" owner_lease.json --expect-count 0
  control-agent-server api GET "/api/conversations/$I/events/count" --check . eq "$NI" --save F31.idle-eviction/events-after-reload
  control-agent-server conversation events "$I" --kinds MessageEvent --contains qa-f31-idle-marker --expect-count 1
  control-agent-server state cat owner_lease.json --conversation "$I" --check generation eq 1
  ```
  第一次遍历卸载了 `I`（其租约被删除，并且 `Evicted idle conversation` 被记录）； GET 但搜索仍然以标题列出它
  `idle` 状态而不加载它，并且下一个事件读取使用相同的事件再次加载它（新的第 1 代租约）。
- **保留繁忙的对话 (`F31.eviction-skips-busy`)。**就在卸载通道之后 `I`； 然后两者都被释放并等待下一次传递（最多约 60 秒后）。

  需要：`F31.idle-eviction`
  ```sh
  control-agent-server state ls --conversation "$WB" owner_lease.json --expect-count 1
  control-agent-server state ls --conversation "$R" owner_lease.json --expect-count 1
  control-agent-server ws read f31-subscribed --expect-open
  control-agent-server api GET "/api/conversations/$R" --check execution_status eq running --quiet
  control-agent-server ws stop f31-subscribed --expect-kind ConversationStateUpdateEvent --save F31.eviction-skips-busy/socket
  control-agent-server api POST "/api/conversations/$R/interrupt" --expect 200 --check success eq true
  T0=$SECONDS
  until control-agent-server state ls --conversation "$WB" owner_lease.json --expect-count 0 >/dev/null; do
    test $((SECONDS - T0)) -le 75
    sleep 2
  done
  control-agent-server state ls --conversation "$R" owner_lease.json --expect-count 0
  control-agent-server api GET "/api/conversations/$R" --check execution_status eq paused --quiet --save F31.eviction-skips-busy/released
  ```
  他们都通过了驱逐 `I`（一个附着的事件套接字和一个活跃的运行块驱逐）的端点。 一旦套接字关闭并运行中断，下一个循环将卸载两者。 `R`保持为
  `paused`.
- **按容量创建 (`F31.create-capacity`)。**一个运行槽位，由悬挂存根上的对话保持。
  ```sh
  control-agent-server restart --reset-config --config-json '{"max_concurrent_runs": 1}'
  C=$(control-agent-server conversation start --body-json "{\"agent\": $HANG_AGENT}" --no-autotitle --print-id)
  NC=$(control-agent-server api GET /api/conversations/count --field .)
  NM=$(control-agent-server state ls 'server/workspace/conversations/*/meta.json' | jq .count)
  control-agent-server conversation send "$C" --text 'hi' --no-run
  control-agent-server api POST "/api/conversations/$C/run" --expect 200 --check success eq true
  control-agent-server conversation wait "$C" --until running --timeout 60
  NEW=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api POST /api/conversations --json "{\"conversation_id\": \"$NEW\", \"workspace\": {\"working_dir\": \"$QA_WS\"}, \"agent\": $HANG_AGENT}" \
    --expect 429 --check detail eq 'Conversation run limit reached. Retry the request later.' --save F31.create-capacity/create-429
  control-agent-server api GET "/api/conversations/$NEW" --expect 404
  control-agent-server api GET /api/conversations/count --check . eq "$NC"
  control-agent-server state ls 'server/workspace/conversations/*/meta.json' --expect-count "$NM"
  control-agent-server state ls --conversation "$NEW" '**/*' --expect-count 0
  control-agent-server api POST "/api/conversations/$C/interrupt" --expect 200 --check success eq true
  control-agent-server api POST /api/conversations --json "{\"conversation_id\": \"$NEW\", \"workspace\": {\"working_dir\": \"$QA_WS\"}, \"agent\": $HANG_AGENT}" \
    --expect 201 --check id eq "$NEW" --save F31.create-capacity/create-after-release
  control-agent-server api GET /api/conversations/count --check . eq "$((NC + 1))"
  control-agent-server api DELETE "/api/conversations/$NEW" --expect 200 --check success eq true
  ```
  在 `C` 运行时，创建返回 429 并带有重试提示，没有任何内容
  对话：id为404，计数和`meta.json`个文件为
  未更改且未创建目录。 中断释放槽后，相同的请求创建`NEW`（再次删除）。
- **配置文件和环境（`F31.config-precedence`）。**配置文件中设置的租约 TTL，然后被 `OH_LEASE_TTL_SECONDS` 覆盖。
  ```sh
  control-agent-server restart --reset-config --config-json '{"lease_ttl_seconds": 30}'
  control-agent-server config | jq -e '.config_file.lease_ttl_seconds == 30 and .server_env.OH_LEASE_TTL_SECONDS == null'
  P1=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  NOW=$(date +%s)
  control-agent-server state cat owner_lease.json --conversation "$P1" --check expires_at gt "$((NOW + 25))" --check expires_at le "$((NOW + 31))"
  control-agent-server restart --env OH_LEASE_TTL_SECONDS=90
  control-agent-server config | jq -e '.config_file.lease_ttl_seconds == 30 and .server_env.OH_LEASE_TTL_SECONDS == "90"'
  P2=$(control-agent-server conversation start --tools none --no-autotitle --print-id)
  NOW=$(date +%s)
  control-agent-server state cat owner_lease.json --conversation "$P2" --check expires_at gt "$((NOW + 85))" --check expires_at le "$((NOW + 91))"
  ```
  仅凭文件，新的租赁约30秒后到期。 文件仍然显示30，变量显示90，大约90秒后。
- **null 来自环境 (`F31.config-null-override`)。**该文件设置 `app_backend_public_url`（`/server_info` 报告为
  `app_backend_ingress_url`，可空字段的即时视图）； 一个非 null 变量替换它，那么 `_IS_NONE=1` 应该清除它。
  ```sh
  control-agent-server restart --reset-config --config-json '{"app_backend_public_url": "http://qa-f31-file.invalid:9"}'
  control-agent-server api GET /server_info --auth none --check app_backend_ingress_url eq http://qa-f31-file.invalid:9 \
    --check capabilities contains canvas_app_backend_bridge_v1
  control-agent-server restart --env OH_APP_BACKEND_PUBLIC_URL=http://qa-f31-env.invalid:9
  control-agent-server api GET /server_info --auth none --check app_backend_ingress_url eq http://qa-f31-env.invalid:9
  control-agent-server restart --reset-config --config-json '{"app_backend_public_url": "http://qa-f31-file.invalid:9"}' \
    --env OH_APP_BACKEND_PUBLIC_URL_IS_NONE=1
  control-agent-server config | jq -e '.config_file.app_backend_public_url == "http://qa-f31-file.invalid:9" and .server_env.OH_APP_BACKEND_PUBLIC_URL_IS_NONE == "1"'
  control-agent-server api GET /server_info --auth none --check app_backend_ingress_url missing \
    --check capabilities not-contains canvas_app_backend_bridge_v1 --save F31.config-null-override/server-info
  ```
  文件值被服务，而一个非null变量取代了它（阳性对照）。 配置显示文件值和`_IS_NONE`变量都提前发送到服务器。 与
  `OH_APP_BACKEND_PUBLIC_URL_IS_NONE=1` 字段为 null，桥接功能消失：`load_config` 将环境合并到文件上
  with `merge(..., none_overrides=True)`, so an explicit null from the
  环境清除文件值。 这同样适用于
  `conversation_idle_ttl_seconds`：文件中带有TTL，
  `OH_CONVERSATION_IDLE_TTL_SECONDS_IS_NONE=1` 禁用驱逐。 下一个项目符号将重置配置。
- **无效限制停止启动 (`F31.config-invalid-fails-fast`)。**一个非数字变量，然后是低于文件中最小值的限制； 然后运行将恢复到默认值。
  ```sh
  N1=$(control-agent-server logs --grep "invalid literal for int\(\) with base 10: 'qa-f31-nan'" | jq .total_matching)
  if control-agent-server restart --reset-config --env OH_MAX_CONCURRENT_RUNS=qa-f31-nan --timeout 60; then false; fi
  control-agent-server runs | jq -e --arg r "$AGENT_SERVER_VERIFY_RUN" '.runs[] | select(.run == $r) | .alive == false'
  control-agent-server logs --grep "invalid literal for int\(\) with base 10: 'qa-f31-nan'" --expect-min $((N1 + 1))
  N2=$(control-agent-server logs --grep 'greater_than_equal, input_value=0' | jq .total_matching)
  N3=$(control-agent-server logs --grep '^max_concurrent_runs$' | jq .total_matching)
  if control-agent-server restart --reset-config --config-json '{"max_concurrent_runs": 0}' --timeout 60; then false; fi
  control-agent-server runs | jq -e --arg r "$AGENT_SERVER_VERIFY_RUN" '.runs[] | select(.run == $r) | .alive == false'
  control-agent-server logs --grep 'greater_than_equal, input_value=0' --expect-min $((N2 + 1))
  control-agent-server logs --grep '^max_concurrent_runs$' --expect-min $((N3 + 1))
  control-agent-server restart --reset-config
  control-agent-server doctor
  ```
  重启都失败了，返回码是 `Server exited with code 1 during startup`，进程也不在运行。 日志显示 `ValueError: invalid literal for int() with base 10: 'qa-f31-nan'` 和 Pydantic 错误 `Input should be greater than or equal to 1 [type=greater_than_equal, input_value=0, ...]`
  `max_concurrent_runs`. 没有覆盖的重新启动又恢复正常了。
- **无法识别的布尔值和选择无论如何都会开始（`F31.config-silent-env`）。**第二台服务器，其配置文件设置为 `deferred_init` True（因此它开始休眠）； 然后是布尔值 `OH_DEFERRED_INIT=yes`，然后是
  `Literal` `OH_CONVERSATION_RUNTIME` 拼写为 `Docker`，每个都在同一服务器上的阳性对照之后。
  ```sh
  B=$(control-agent-server launch --new --name f31-env --config-json '{"deferred_init": true}' --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  control-agent-server api GET /api/conversations/count --run "$B" --expect 503 --check exception contains "deferred-init state 'dormant'"
  control-agent-server restart --run "$B" --env OH_DEFERRED_INIT=yes
  control-agent-server config --run "$B" | jq -e '.config_file.deferred_init == true and .server_env.OH_DEFERRED_INIT == "yes"'
  control-agent-server api GET /api/conversations/count --run "$B" --expect 200 --save F31.config-silent-env/bool-yes
  if command -v docker >/dev/null; then
    control-agent-server restart --run "$B" --reset-config --env OH_CONVERSATION_RUNTIME=docker
    control-agent-server api GET /server_info --run "$B" --auth none --check conversation_runtime eq docker --quiet
  fi
  control-agent-server restart --run "$B" --reset-config --env OH_CONVERSATION_RUNTIME=Docker
  control-agent-server config --run "$B" | jq -e '.server_env.OH_CONVERSATION_RUNTIME == "Docker"'
  control-agent-server api GET /server_info --run "$B" --auth none --check conversation_runtime eq local --quiet \
    --save F31.config-silent-env/literal-fallback
  NL=$(control-agent-server logs --run "$B" --grep "input_value='Docker'" | jq .total_matching)
  if control-agent-server restart --run "$B" --reset-config --config-json '{"conversation_runtime": "Docker"}' --timeout 60; then false; fi
  control-agent-server logs --run "$B" --grep "input_value='Docker'" --expect-min $((NL + 1))
  control-agent-server stop --run "$B"
  trap - EXIT
  ```
  该文件的`true`使服务器休眠（503 `deferred-init state 'dormant'`)。 `OH_DEFERRED_INIT=yes` 添加后，它开始并运行
  `/api/*`：布尔解析器仅将 `1` 和 `true`（任何情况）读取为 True，因此 `yes` 被读取为 False 并覆盖文件的 `true`，而不是被拒绝。 `OH_CONVERSATION_RUNTIME=docker` 很荣幸（`/server_info` 说
  `docker`; 启动时只警告它无法连接到守护进程，并且控制运行在 `docker` CLI 安装的地方，这是这个模式在启动时调用的，但 `Docker` 不在 `Literal` 选项中，默默地回退到 `local`。 在配置文件中的相同`Docker`会导致启动失败，因为Pydantic的`literal_error`，因为一个非数字整型变量(`F31.config-invalid-fails-fast`)：只有环境解析器对布尔值和选择项是宽容的。
- **停止时删除每个进程 tmux 目录 (`F31.tmux-dir-cleanup`)。**第二次运行的 `TMUX_TMPDIR` 为空，因此服务器选择自己的。
  ```sh
  B=$(control-agent-server launch --new --name f31-tmux --env TMUX_TMPDIR= --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null 2>&1 || true' EXIT
  PIDB=$(jq -r .pid "$B/run.json")
  TD="$(python3 -c 'import tempfile; print(tempfile.gettempdir())')/openhands-agent-server-$PIDB"
  control-agent-server logs --run "$B" --grep 'TMUX_TMPDIR not set' --expect-min 1
  test -d "$TD"
  control-agent-server stop --run "$B" | jq -e '.server == "terminated"'
  trap 'rm -rf -- "$TD" || true' EXIT
  control-agent-server assert --value "$([ -e "$TD" ] && echo true || echo false)" --check . eq false
  trap - EXIT
  ```
  预期：目录在正常停止后消失（`stop`报告
  `terminated`，而不是 `killed`，因此寿命关闭运行）。 `B` 运行时存在的日志行和目录是阳性对照。 服务器记录`TMUX_TMPDIR not set; defaulting to per-server tmux directory /tmp/openhands-agent-server-<pid>`，创建它，并在关闭时（`api_lifespan`）恢复变量并删除该目录。 A
  `TMUX_TMPDIR` 所提供的用户将被保留且永远不会被删除。 如果断言失败，`trap` 会删除剩余部分。
- **存储保留和磁盘预算 (`F31.storage-retention`)。**
  需求：`docker`

  首先拉取选定的图像。 这使用相同的固定最小图像和
  `AGENT_SERVER_VERIFY_DOCKER_IMAGE` 覆盖为 F12。 两个独立的 Docker 服务器同时执行单独的策略，而不调用 LLM。 外部服务器使用此结帐，并且子映像可能是一个版本。 真正的 300 秒维护计时器保持不变。
  ```sh
  IMAGE=${AGENT_SERVER_VERIFY_DOCKER_IMAGE:-ghcr.io/openhands/agent-server:1.55.1-python-minimal}
  docker image inspect "$IMAGE" >/dev/null
  RET=
  BUD=
  trap 'for R in "$RET" "$BUD"; do if [ -n "$R" ]; then control-agent-server stop --run "$R" >/dev/null 2>&1 || true; fi; done' EXIT
  RET=$(control-agent-server launch --new --name f31-retention --print-run \
    --config-json "$(jq -nc --arg image "$IMAGE" '{conversation_runtime:"docker",conversation_image:$image,enable_browser:false,conversation_container_memory:"1g",conversation_storage_retention_days:0.00001}')")
  BUD=$(control-agent-server launch --new --name f31-disk-budget --print-run \
    --config-json "$(jq -nc --arg image "$IMAGE" '{conversation_runtime:"docker",conversation_image:$image,enable_browser:false,conversation_container_memory:"1g",conversation_storage_disk_budget:0.01}')")
  for R in "$RET" "$BUD"; do control-agent-server doctor --run "$R"; done
  control-agent-server exec --run "$RET" --save F31.storage-retention/image -- \
    docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$IMAGE"
  CREATE='{"agent":{"llm":{"model":"openai/qa-no-call","api_key":"qa-placeholder"},"tools":[]},"autotitle":false}'
  RCID=$(control-agent-server api POST /api/conversations --run "$RET" --json "$CREATE" \
    --expect 201 --timeout 180 --field id --save F31.storage-retention/retention-create)
  BCID=$(control-agent-server api POST /api/conversations --run "$BUD" --json "$CREATE" \
    --expect 201 --timeout 180 --field id --save F31.storage-retention/budget-create)
  control-agent-server api POST "/api/conversations/$RCID/events" --run "$RET" --expect 200 --check success eq true \
    --json '{"role":"user","content":[{"type":"text","text":"QA_F31_RETAINED_HISTORY"}],"run":false}'
  control-agent-server api GET "/api/conversations/$RCID/events/search" --run "$RET" --expect 200 \
    --check items.1.llm_message.content.0.text eq QA_F31_RETAINED_HISTORY --save F31.storage-retention/history-before
  FILL=$(cat <<'SH'
  set -e
  cd /workspace
  git init -q
  printf 'node_modules/\n.venv/\nbuild/\n.env\nvendor/\n' > .gitignore
  printf 'tracked\n' > main.txt
  git add .gitignore main.txt
  git -c user.name=qa -c user.email=qa@example.invalid commit -qm initial
  printf 'untracked\n' > notes.txt
  printf 'ignored file\n' > .env
  mkdir -p node_modules/dep .venv/lib build vendor/lib
  printf 'rebuild\n' > node_modules/dep/index.js
  printf 'rebuild\n' > .venv/lib/site.py
  printf 'rebuild\n' > build/out.o
  git -C vendor/lib init -q
  printf 'nested checkout\n' > vendor/lib/lib.txt
  SH
  )
  control-agent-server api POST "/api/conversations/$BCID/bash/execute_bash_command" --run "$BUD" \
    --json "$(jq -nc --arg command "$FILL" '{command:$command}')" --expect 200 --check exit_code eq 0 --save F31.storage-retention/budget-fill
  BROOT="$BUD/home/.openhands/runtime-data/${BCID//-/}/workspace"
  control-agent-server exec --run "$BUD" --env ROOT="$BROOT" --save F31.storage-retention/budget-before -- .venv/bin/python - <<'PY'
  import json, os, shutil
  from pathlib import Path
  root = Path(os.environ["ROOT"])
  usage = shutil.disk_usage(root)
  fraction = usage.used / (usage.used + usage.free)
  assert fraction > 0.01, "Filesystem must exceed the configured 1% budget"
  for name in ("node_modules/dep/index.js", ".venv/lib/site.py", "build/out.o", "main.txt", "notes.txt", ".env", "vendor/lib/lib.txt"):
      assert (root / name).is_file(), name
  print(json.dumps(dict(over_budget=True, disk_usage_fraction=fraction, all_fixture_files_present=True)))
  PY
  control-agent-server api DELETE "/api/conversations/$RCID/runtime" --run "$RET" --expect 204
  control-agent-server api DELETE "/api/conversations/$BCID/runtime" --run "$BUD" --expect 204
  control-agent-server api GET "/api/conversations/$RCID/runtime" --run "$RET" --expect 200 \
    --until-ok 330 --check runtime_status eq missing --check can_resume eq false --save F31.storage-retention/archived
  control-agent-server state ls --run "$RET" "home/.openhands/runtime-control/${RCID//-/}.archived.json" --expect-count 1
  control-agent-server exec --run "$RET" --env ROOT="$RET/home/.openhands/runtime-data/${RCID//-/}" \
    --save F31.storage-retention/runtime-directory-gone -- .venv/bin/python - <<'PY'
  import json, os
  from pathlib import Path
  assert not Path(os.environ["ROOT"]).exists()
  print(json.dumps(dict(runtime_directory_exists=False)))
  PY
  control-agent-server api GET "/api/conversations/$RCID/events/search" --run "$RET" --expect 200 \
    --check items.1.llm_message.content.0.text eq QA_F31_RETAINED_HISTORY --save F31.storage-retention/history-after
  control-agent-server api POST "/api/conversations/$RCID/run" --run "$RET" --expect 410 \
    --check detail eq 'Conversation runtime was archived; its history is read-only' --save F31.storage-retention/run-410
  control-agent-server api POST "/api/conversations/$RCID/events" --run "$RET" --expect 410 \
    --json '{"role":"user","content":[{"type":"text","text":"must not persist"}],"run":false}' --save F31.storage-retention/message-410
  control-agent-server api GET "/api/conversations/$RCID/file/download" --run "$RET" --query path=/workspace/main.txt \
    --expect 410 --save F31.storage-retention/proxy-410
  control-agent-server api POST "/api/conversations/$RCID/runtime/reprovision" --run "$RET" --expect 410
  control-agent-server logs --run "$RET" --grep 'Conversation storage: freed' --expect-min 1
  control-agent-server exec --run "$BUD" --env ROOT="$BROOT" --timeout 350 \
    --save F31.storage-retention/budget-after -- .venv/bin/python - <<'PY'
  import json, os, time
  from pathlib import Path
  root = Path(os.environ["ROOT"])
  shed = ("node_modules", ".venv", "build")
  deadline = time.monotonic() + 330
  while any((root / name).exists() for name in shed) and time.monotonic() < deadline:
      time.sleep(1)
  for name in shed:
      assert not (root / name).exists(), name
  kept = {"main.txt": "tracked\n", "notes.txt": "untracked\n", ".env": "ignored file\n", "vendor/lib/lib.txt": "nested checkout\n"}
  for name, contents in kept.items():
      assert (root / name).read_text() == contents, name
  assert (root / ".git/HEAD").is_file() and (root / "vendor/lib/.git/HEAD").is_file()
  print(json.dumps(dict(shed=list(shed), kept_exact_contents=list(kept), git_checkouts_preserved=True)))
  PY
  control-agent-server logs --run "$BUD" --grep 'Conversation storage: freed' --expect-min 1
  control-agent-server api GET "/api/conversations/$BCID/runtime" --run "$BUD" --expect 200 \
    --check runtime_status eq missing --check can_resume eq true --save F31.storage-retention/budget-still-resumable
  control-agent-server api POST "/api/conversations/$BCID/runtime/reprovision" --run "$BUD" --expect 200 \
    --check runtime_status eq available --timeout 180 --save F31.storage-retention/budget-reprovision
  control-agent-server api POST "/api/conversations/$BCID/bash/execute_bash_command" --run "$BUD" --expect 200 --check exit_code eq 0 \
    --json '{"command":"cd /workspace && test ! -e node_modules && test ! -e .venv && test ! -e build && test -f vendor/lib/.git/HEAD && cat main.txt notes.txt .env vendor/lib/lib.txt"}' \
    --check stdout eq $'tracked\nuntracked\nignored file\nnested checkout\n' --save F31.storage-retention/resumed-content
  control-agent-server api DELETE "/api/conversations/$RCID" --run "$RET" --expect 200
  control-agent-server api DELETE "/api/conversations/$BCID" --run "$BUD" --expect 200
  for R in "$RET" "$BUD"; do control-agent-server stop --run "$R"; done
  ```
  保留会移除运行时目录，并留下可读的事件历史和一个可读的存档标记。 写入、续传和代理工作区访问
  410. 单独的磁盘预算策略仅删除已停止的工作区
  gitignored 依赖目录。 跟踪和未跟踪的文件、忽略的单个文件和嵌套签出保留其确切内容； 对话仍然可以恢复，并且这些文件在恢复后仍可读。 在测试之前会根据实际文件系统使用情况检查预算。

<a id="gotchas"></a>

## 陷阱

- 租用文件仅在加载对话时存在。 GET，批量获取、搜索和计数读取目录并且从不加载（参见
  `F04.read-no-hydrate`); PATCH、DELETE、事件读取和写入、`/run`、暂停、中断、`agent_final_response` 和事件套接字执行的操作。 驱逐和接管在 API 中是不可见的：请阅读 `owner_lease.json` 和日志。
- 服务器日志由 Rich 包装：一条长消息被分成几行。 grep 短语（`Taking over conversation`, `Evicted idle`,
  `TMUX_TMPDIR not set`)，并计数前后匹配，因为日志保留了运行的每个较早开始。
- 第二个服务器在其自身启动时读取一次目录。 之后在所有者上创建的对话都是 404，直到它重新启动，并且它的元数据副本变得陈旧； 第一次加载此类对话（无论是否接管）时，它会将过时的副本写入 `meta.json` (`F31.takeover-keeps-metadata`)。
- 在租约在其他地方的对话看起来像第二个服务器上的未知ID（404, 400, `success: false`, 4004关闭），而其GET是200从目录。 只有租赁文件才能区分两者。
- 到期前的接管需要记录的所有者位于同一主机上且具有失效 pid。 冻结或挂起的所有者（pid 处于活动状态）、另一台主机上的所有者或来自不带 `owner_host`/`owner_pid` 的旧服务器的租用文件仅在 `expires_at` 之后才被接管。 低于 15 秒的更新间隔的 TTL 在更新之间到期。
- 一个租户失去租赁后，会保持对话加载，并在写入时回复 409 直到空闲回收或重启关闭它，其读取则服务内存中的过时状态。 每次尝试都算作活动，因此重试推迟驱逐。 它的更新循环仅每 15 秒记录一次 `Conversation lease lost while renewing`。
- 正常关闭会暂停正在运行的对话（`F05.restart-running-graceful`）； a SIGKILL 将 `running` 留在磁盘上，下次启动时将变成
  `error` (`F05.restart-hard-running`, `F31.crash-tool-call`). 正在运行的对话是唯一一种在启动时急切加载的对话。
- 空闲逐出不能快于每分钟一次传递 (`max(60, ttl/2)`)，并且第一次传递在启动后运行约 60 秒。
  `OH_CONVERSATION_IDLE_TTL_SECONDS=null`停止启动(`float('null')`); 使用文件中的 `null` 禁用驱逐，或者使用
  `OH_CONVERSATION_IDLE_TTL_SECONDS_IS_NONE=1`，它还会覆盖文件集 TTL (`F31.config-null-override`)。
- 创建对话需要一个运行槽，例如 `/run` (`F05.run-capacity`)：当 `max_concurrent_runs` 个槽繁忙时，在第一次运行开始之前创建配方所需的每个对话。
- `OH_*` 不解析的整数和浮点数，以及字段边界之外的值，以退出代码 1 停止启动； 布尔值（只有 `1` 和 `true` 是 True，因此 `yes` 或 `on` 读作 False 并覆盖文件的 `true`）和
  `Literal` 字段（在其选择之外：默认）改为静默启动（`env_parser.py`、`F31.config-silent-env`）。 配置文件经过严格验证。 `launch` 和 `restart` 将失败报告为退出 3 `Server exited ... during startup`。
- 启动器总是设置一个短的每次运行 `TMUX_TMPDIR` 并在
  `stop`; `--env TMUX_TMPDIR=`（空）使服务器选择自己的。 启动会终止 `openhands` 个套接字上的 tmux 个会话
  `TMUX_TMPDIR` 它得到了，所以永远不要在服务器之间共享一个。
- 使用 `--share-conversations-from` 启动的第二次运行有其自己的
  `OH_SECRET_KEY`，设置，机密和机密：因为不共享所有者的密钥，所以上述的条目只适用于没有机密的对话。
