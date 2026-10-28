<a id="bash-commands-and-bash-events"></a>

# Bash 命令和 bash 事件

消费者（ ）的非标准shell命令Agent Canvas 终端标签， SDK's `RemoteWorkspace`, 无须通过服务器运行智能体它们在会话事件流中从未出现，模型也从未见过它们。 每个命令是 `BashCommand` 事件后跟一个或多个 `BashOutput` stdout和stderr被切成了1个事件 MiB 分块，最后一个携带 `exit_code`), all 已持久化 as one JSON 按事件存储文件，之后可以搜索。 有两个具有独立历史记录的范围：全局 `/api/bash/...` 服务（默认为服务器进程的当前工作目录，任何允许的当前工作目录，实时帧） `WS /sockets/bash-events`) 和基于会话的 `/api/conversations/{id}/bash/...` 服务（默认为会话路径） 工作区并且必须留在其中，历史与对话一起存储，没有 socket)。

资料来源：`openhands-agent-server/openhands/agent_server/bash_router.py`、`openhands-agent-server/openhands/agent_server/bash_service.py`、`openhands-agent-server/openhands/agent_server/runtime_router.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-agent-server/openhands/agent_server/sockets.py`、`openhands-agent-server/openhands/agent_server/models.py`、`openhands-sdk/openhands/sdk/utils/command.py`、`openhands-sdk/openhands/sdk/workspace/remote/remote_workspace_mixin.py`、`clients/typescript/src/client/bash-client.ts`、`clients/typescript/src/events/bash-websocket-client.ts`

路线：`GET /api/conversations/{runtime_conversation_id}/bash/bash_events/search`，
`GET /api/conversations/{runtime_conversation_id}/bash/bash_events/{event_id}`,
`GET /api/conversations/{runtime_conversation_id}/bash/bash_events/`,
`POST /api/conversations/{runtime_conversation_id}/bash/start_bash_command`,
`POST /api/conversations/{runtime_conversation_id}/bash/execute_bash_command`,
`DELETE /api/conversations/{runtime_conversation_id}/bash/bash_events`,
`POST /api/conversations/{runtime_conversation_id}/bash/bash_commands/{command_id}/stop`,
`GET /api/bash/bash_events/search`, `GET /api/bash/bash_events/{event_id}`,
`GET /api/bash/bash_events/`, `POST /api/bash/start_bash_command`,
`POST /api/bash/execute_bash_command`, `DELETE /api/bash/bash_events`,
`POST /api/bash/bash_commands/{command_id}/stop`, `WS /sockets/bash-events`

<a id="sub-features"></a>

## 子功能

- `F13.auth`：每个 bash 路由都会在没有或有错误会话密钥的情况下回答 401（并且不运行任何内容）； `WS /sockets/bash-events` 由于密钥错误而以 4001 结束。
- `F13.execute-sync`: `POST /api/bash/execute_bash_command` 阻塞，直到命令退出并返回其最终的 `BashOutput` 以及真正的退出代码以及单独的 stdout 和 stderr； 没有 `command` 或非整数 `timeout` 的主体是 422。
- `F13.global-cwd`：默认情况下，全局命令在服务器进程中运行，接受任何显式的工作目录，并且不存在的工作目录会返回200状态码，并附带`exit_code` -1和`Error executing command`标准错误。
- `F13.env-sanitized`：命令在其环境中没有 `OH_SESSION_API_KEYS_*`、`SESSION_API_KEY` 和 `OH_SECRET_KEY` 且有 `AI_AGENT=openhands` 的情况下运行。
- `F13.env-config-credentials`只去除其他三个名字凭据- 配置变量`OH_TELEMETRY_HTTP_TOKEN`, `OH_WEBHOOKS_0_HEADERS`） 保留命令。
- `F13.start-async`：`POST /api/bash/start_bash_command`返回命令完成前的`BashCommand`； 其 `BashOutput` 和 `exit_code` 稍后出现在搜索中。
- `F13.ws-live`：`WS /sockets/bash-events` 流 `BashCommand` 和 `BashOutput` 帧用于通过 REST 启动的命令，`resend_mode=all` 在连接时重播存储的事件。
- `F13.ws-command`：形如`ExecuteBashRequest`的客户端框架在套接字上启动命令； 无效帧获取 `BashError` 帧并且套接字继续工作。
- `F13.ws-resend-all`：已弃用 `resend_all=true` 查询参数重播 `resend_mode=all` 等存储的事件（并记录弃用警告），而没有任何一个的连接不会重播任何内容。
- `F13.ws-subscriber-cap`：`WS /sockets/bash-events` 最多可容纳 50 个订阅者：其中 50 个开放，第 51 个订阅者关闭，其中 1013 个 `Too many bash event connections`，关闭一个可释放插槽。
- `F13.get-events`: `GET /api/bash/bash_events/{event_id}` 返回其十六进制ID（404表示未知）的事件，`GET /api/bash/bash_events/` 以一个包含JSON数组的请求体返回输入顺序的事件，`null` 用于缺失ID（422无体）。
- `F13.search`：按 `kind__eq`、`command_id__eq`（仅输出）、UTC `timestamp__gte`/`timestamp__lt` 窗口搜索过滤器，按 `sort_order` 排序，按 `limit`/`next_page_id` 进行页面排序，并使用 422 拒绝错误参数。
- `F13.timestamp-offset`：具有非 UTC 偏移量的 `timestamp__gte` 选择与其 UTC 拼写相同的时刻。
- `F13.output-chunks`：超过 1 MiB 的输出存储为 1048576 个字符的有序 `BashOutput` 块加上带有退出代码的最终块； `order__gt` 跳过看到的块，SDK 的 `RemoteWorkspace.execute_command` 重新组合它们。
- `F13.order-gt-paging`：`order__gt` 在 `limit` 应用之前进行过滤，因此轮询器在小页面的 N 阶之后请求输出即可获取它们。
- `F13.execute-large-output`: `execute_bash_command` 返回输出超过 1 MiB 的命令的完整标准输出。
- `F13.timeout`：比 `timeout` 寿命更长的命令与其进程组一起被终止，并报告 `exit_code` -1。
- `F13.stop`：通过 id 停止正在运行的命令仅终止该命令（最终 `exit_code` -15，进程消失），而另一个命令正常完成。
- `F13.stop-idempotent`：停止已完成的命令（十六进制或虚线 id）返回 200、未知 id 404 和非 UUID id 422。
- `F13.scoped-cwd`对话级命令在对话中运行工作区默认情况下，接受一个绝对的 cwd（也通过它） SDK's `runtime_conversation_id`), 并拒绝不在其范围内的工作目录，一个转义 `..` 路径或带有 422 的相对路径。
- `F13.scoped-routes`：对话级别的执行、开始、停止、获取、批量获取和搜索路由在对话的历史中工作，而命令的文件则存储在工作区。
- `F13.scoped-isolation` 本地事件对全局搜索、全局套接字、全局停止路由以及其他对话不可见，并存储在对话的目录下。
- `F13.scoped-unknown`：对于未知的对话 ID，每个对话范围的 bash 路由都会回答 404 `Conversation not found`。
- `F13.persist-restart`：全局和对话范围的 bash 历史记录在服务器重新启动后仍然存在。
- `F13.clear`：`DELETE .../bash_events`删除一个范围存储的事件和报告`cleared_count`； 另一个范围保持不变，并且不能再停止已清除的已完成命令（404）。
- `F13.retention`：设置 `bash_events_retention_seconds` 后，早于窗口的全局事件将在启动时清除，同时保留对话范围的历史记录。
- `F13.retention-rolling` 保留循环在服务器运行时持续清理：启动后写入的全局事件可以立即读取并随后消失（大约60秒），无需重启，而会话级别的事件则保持不变。
- `F13.scoped-bad-id`：对话范围内的 bash 路由，其对话 ID 为非 UUID，答案为 422。
- `F13.scoped-idle-eviction`：与正在运行的作用域命令的对话不会因为空闲而被驱逐，因此该命令会继续运行。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，全局范围：`POST /api/bash/execute_bash_command`（同步），
  `POST /api/bash/start_bash_command` (异步),
  `POST /api/bash/bash_commands/{command_id}/stop`,
  `GET /api/bash/bash_events/search`, `GET /api/bash/bash_events/{event_id}`,
  `GET /api/bash/bash_events/`（批处理，带有 JSON 数组体的 GET）和
  `DELETE /api/bash/bash_events`. 正文为 `ExecuteBashRequest`（`command`，可选 `cwd`、`timeout`，以整秒为单位，默认 300）。
- REST、会话范围：同7条路由下
  `/api/conversations/{runtime_conversation_id}/bash/...`, 广告
  `/server_info` 中的 `conversation_runtime_routes_v1` 能力。 他们根据对话的工作区采取行动并将其历史记录保存在
  `<conversations_path>/<conversation hex>/bash_events`.
- WebSocket: `/sockets/bash-events`（仅限全局范围），第一帧身份验证，
  `resend_mode=all`重播，客户端帧启动命令。
- PythonSDK:`RemoteWorkspace.execute_command()`（开始，然后轮询搜索
  with `kind__eq=BashOutput`, `command_id__eq` and `order__gt`, joining every
  chunk), `start_command()`, `get_command_output()`, `stop_command()` （将 404 视为已停止）； 与 `runtime_conversation_id=...` 相同的调用使用会话范围的前缀。 `AsyncRemoteWorkspace`反映了它们。
- TypeScript 客户端：`BashClient`（`searchEvents`、`getEvent`、`getEvents`、
  `batchGetEvents`, `startCommand`, `executeCommand`, `clearEvents`,
  `stopCommand`，范围为 `conversationId`)、`BashWebSocketClient`（查询参数键、`resendMode: 'all'`）和
  `RemoteWorkspace.executeCommand`，它调用 `execute_bash_command`，因此获得 `F13.execute-large-output` 的连接输出。
- 配置：`bash_events_dir` (`OH_BASH_EVENTS_DIR`) 和
  `bash_events_retention_seconds` (`OH_BASH_EVENTS_RETENTION_SECONDS`);
  `conversation_idle_ttl_seconds` 关闭对话的范围服务。
- Agent Canvas（仅限上下文）：终端选项卡通过这些路由启动和轮询命令。

REST和WebSocket直接驱动，还有两个小型SDK程序（`exec`）在两个范围内分别用于`RemoteWorkspace.execute_command`，还有一个持有51个套接字的`websockets`程序
`F13.ws-subscriber-cap` 在单个进程中。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已实时并导出 (`launch --new`)，`doctor` 可以。 不需要 LLM：下面的两个对话仅提供工作区，永远不会运行，并且命名一个永远不会被调用的模型。
- `jq`、`pgrep` 和 `sed` 位于 `PATH`（文件计数、服务器环境以及检查已终止命令的进程是否已消失）。
- `launch` 使用 cwd `<run>/server` 启动服务器，因此没有 cwd 的全局命令在那里运行。
  ```sh
  NOLLM='{"agent": {"llm": {"model": "openai/qa-f13-never-called", "usage_id": "qa-f13"}, "tools": []}}'
  CID=$(control-agent-server conversation start --body-json "$NOLLM" --no-run --no-autotitle --print-id)
  CID2=$(control-agent-server conversation start --body-json "$NOLLM" --no-run --no-autotitle --print-id)
  WS1=$(control-agent-server api GET "/api/conversations/$CID" --field workspace.working_dir)
  WS2=$(control-agent-server api GET "/api/conversations/$CID2" --field workspace.working_dir)
  SERVER_CWD="$AGENT_SERVER_VERIFY_RUN/server"
  test -d "$WS1" && test -d "$WS2" && test -d "$SERVER_CWD"
  ```

- **授权 (`F13.auth`).**所有十四 REST 条路线都没有密钥或密钥错误，并且套接字密钥错误，后跟命令帧。
  ```sh
  control-agent-server api POST /api/bash/execute_bash_command --auth none \
    --json '{"command": "echo QA_F13_NOAUTH"}' --expect 401 --save F13.auth/execute-no-key
  control-agent-server api POST /api/bash/start_bash_command --auth bad \
    --json '{"command": "echo QA_F13_NOAUTH"}' --expect 401
  control-agent-server api GET /api/bash/bash_events/search --auth bad --expect 401
  control-agent-server api GET /api/bash/bash_events/00000000000000000000000000000000 --auth none --expect 401
  control-agent-server api GET /api/bash/bash_events/ --auth none --json '[]' --expect 401
  control-agent-server api POST /api/bash/bash_commands/00000000000000000000000000000000/stop --auth none --expect 401
  control-agent-server api DELETE /api/bash/bash_events --auth bad --expect 401
  control-agent-server api POST "/api/conversations/$CID/bash/start_bash_command" --auth none \
    --json '{"command": "echo QA_F13_NOAUTH"}' --expect 401
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" --auth bad \
    --json '{"command": "echo QA_F13_NOAUTH"}' --expect 401
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/00000000000000000000000000000000" --auth bad --expect 401
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/" --auth none --json '[]' --expect 401
  control-agent-server api POST "/api/conversations/$CID/bash/bash_commands/00000000000000000000000000000000/stop" --auth none --expect 401
  control-agent-server api DELETE "/api/conversations/$CID/bash/bash_events" --auth none --expect 401
  control-agent-server ws listen /sockets/bash-events --auth bad --send '{"command": "echo QA_F13_NOAUTH"}' \
    --duration 5 --expect-close 4001 --save F13.auth/ws-bad-key
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --check items not-contains QA_F13_NOAUTH --save F13.auth/nothing-ran
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --check items len-eq 0
  ```
  没有有效密钥的每 REST 调用都会返回 401，并且套接字会关闭
  `4001 Authentication failed` 在读取命令帧之前，并且使用运行键都搜索答案 200，并且在任一范围内都没有 `QA_F13_NOAUTH` 命令。
- **同步 execute (`F13.execute-sync`).**退出代码、stdout 和 stderr 在一个响应中返回。
  ```sh
  EXEC_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_OUT; echo QA_F13_ERR >&2; exit 3", "timeout": 30}' --expect 200 \
    --check kind eq BashOutput --check exit_code eq 3 --check order eq 0 \
    --check stdout eq $'QA_F13_OUT\n' --check stderr eq $'QA_F13_ERR\n' \
    --save F13.execute-sync/execute --field command_id)
  control-agent-server api GET "/api/bash/bash_events/$EXEC_CMD" --check kind eq BashCommand \
    --check command eq 'echo QA_F13_OUT; echo QA_F13_ERR >&2; exit 3' --check timeout eq 30 --check . contains '"cwd": null' \
    --save F13.execute-sync/command-event
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$EXEC_CMD" \
    --check items len-eq 1 --check items.0.exit_code eq 3 --save F13.execute-sync/search
  control-agent-server api POST /api/bash/execute_bash_command --json '{"cwd": "/tmp"}' --expect 422
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command": "true", "timeout": "soon"}' --expect 422
  ```
  响应是最终的 `BashOutput` (`exit_code` 3、标准输出和标准错误分开处理） 存储的 `BashCommand` has `"cwd": null` (键存在)
  with a null value, not dropped) and `timeout: 30`;
  不带 `command` 或带文本超时的主体有 422 个。
- **全局cwd (`F13.global-cwd`).**默认、显式和缺少 cwd。
  ```sh
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command": "pwd"}' \
    --check exit_code eq 0 --check stdout eq "$SERVER_CWD"$'\n' --save F13.global-cwd/default
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command": "pwd", "cwd": "/tmp"}' \
    --check exit_code eq 0 --check stdout eq $'/tmp\n'
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command": "pwd", "cwd": "/nonexistent/qa-f13"}' \
    --expect 200 --check exit_code eq -1 --check stderr contains 'Error executing command' --check stdout missing \
    --save F13.global-cwd/missing-cwd
  ```
  `pwd`打印服务器的cwd，然后`/tmp`； 缺少的目录是 200，其 `BashOutput` 具有 `exit_code` -1 以及 stderr 中的生成错误。
- **消毒环境 (`F13.env-sanitized`)。**运行的服务器有
  `OH_SESSION_API_KEYS_0`和`OH_SECRET_KEY`； 重新启动会添加旧版本
  `SESSION_API_KEY`（在设置 `OH_SESSION_API_KEYS_0` 时忽略身份验证），因此所有三个实际上都在服务器环境中。
  ```sh
  control-agent-server restart --env SESSION_API_KEY=qa-f13-legacy-not-a-key
  control-agent-server config | jq -e '.server_env.OH_SESSION_API_KEYS_0 == "<set>" and .server_env.OH_SECRET_KEY == "<set>" and .server_env.SESSION_API_KEY == "<set>"'
  control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo keys=${OH_SESSION_API_KEYS_0:-unset} legacy=${SESSION_API_KEY:-unset} secret=${OH_SECRET_KEY:-unset} agent=$AI_AGENT home=$HOME"}' \
    --check exit_code eq 0 \
    --check stdout eq "keys=unset legacy=unset secret=unset agent=openhands home=$AGENT_SERVER_VERIFY_RUN/home"$'\n' \
    --save F13.env-sanitized/env
  ```
  在命令中，这三个凭据未设置，`AI_AGENT` 是
  `openhands`，而继承的`HOME`（run的私人家）表明服务器环境的REST确实到达了命令。
- **其他凭据变量 (`F13.env-config-credentials`).**第二次运行，其环境携带遥测 token 和 Webhook 标头（针对丢弃端口； 它没有对话，所以没有发布任何内容）。
  ```sh
  CRED=$(control-agent-server launch --new --name f13-envcred --env OH_TELEMETRY_HTTP_TOKEN=qa-f13-telemetry-tok \
    --env OH_WEBHOOKS_0_BASE_URL=http://127.0.0.1:9/qa-f13 \
    --env 'OH_WEBHOOKS_0_HEADERS={"Authorization": "Bearer qa-f13-webhook-tok"}' --print-run)
  trap 'control-agent-server stop --run "$CRED" > /dev/null 2>&1 || true' EXIT
  control-agent-server config --run "$CRED" | jq -e '.server_env.OH_SECRET_KEY == "<set>" and .server_env.OH_SESSION_API_KEYS_0 == "<set>"'
  control-agent-server api POST /api/bash/execute_bash_command --run "$CRED" \
    --json '{"command": "env | grep -E \"^(OH_TELEMETRY_HTTP_TOKEN|OH_WEBHOOKS_0_HEADERS|OH_SECRET_KEY|OH_SESSION_API_KEYS_0)=\" | sort"}' \
    --check exit_code eq 0 --check stdout not-contains OH_SECRET_KEY --check stdout not-contains OH_SESSION_API_KEYS_0 \
    --check stdout contains 'OH_TELEMETRY_HTTP_TOKEN=qa-f13-telemetry-tok' \
    --check stdout contains 'OH_WEBHOOKS_0_HEADERS={"Authorization": "Bearer qa-f13-webhook-tok"}' \
    --save F13.env-config-credentials/env
  ```
  会话和加密密钥在服务器的环境中，缺失
  from the command's, while the telemetry token and the webhook
  `Authorization` 标头逐字显示：`sanitized_env` (`openhands-sdk/openhands/sdk/utils/command.py`) 仅按名称进行剥离
  `SESSION_API_KEY`、`OH_SECRET_KEY` 和 `OH_SESSION_API_KEYS_` 前缀，凭据记录为解锁用户机密。 这记录的是当前合同，不是授权：部署将可重用的凭据（例如会话密钥）放入 Webhook 或刷新头，然后将其传递给每个 bash 命令，以及智能体的终端。 无论如何，剥离都是深度防御，因为命令以服务器用户身份运行并且可以读取`/proc/<server pid>/environ`。
- **异步开始(`F13.start-async`)。** start 在输出存在之前返回； 套接字重播等待最终输出。
  ```sh
  START_CMD=$(control-agent-server api POST /api/bash/start_bash_command \
    --json '{"command": "sleep 3; echo QA_F13_ASYNC", "timeout": 30}' --expect 200 --expect-max-ms 2000 \
    --check kind eq BashCommand --check timeout eq 30 --save F13.start-async/start --field id)
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$START_CMD" \
    --check items len-eq 0 --save F13.start-async/before
  control-agent-server ws listen /sockets/bash-events --query resend_mode=all --until-kind BashOutput \
    --until command_id="$START_CMD" --duration 20 --show 0
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$START_CMD" \
    --query kind__eq=BashOutput --check items len-eq 1 --check items.0.exit_code eq 0 \
    --check items.0.stdout eq $'QA_F13_ASYNC\n' --save F13.start-async/after
  ```
  启动在三秒内回答三个秒的命令，之后没有输出。 一旦命令的`BashOutput`帧到达，搜索就会显示有一个输出，`exit_code`为0。
- **实时和重播的套接字帧 (`F13.ws-live`)。**在后台捕获，通过 REST 启动命令，然后在新连接上重播历史记录。

  需要：`F13.execute-sync`
  ```sh
  control-agent-server ws start /sockets/bash-events --name f13-live --duration 120 \
    --send '{"command": "echo QA_F13_WS_PROBE"}'
  control-agent-server ws read f13-live --kinds BashOutput --contains QA_F13_WS_PROBE --wait 15 --show 0
  LIVE_CMD=$(control-agent-server api POST /api/bash/start_bash_command \
    --json '{"command": "echo QA_F13_LIVE"}' --field id)
  control-agent-server ws stop f13-live --kinds BashOutput --contains "$LIVE_CMD" --wait 15 --show 0 \
    --save F13.ws-live/live
  control-agent-server ws read f13-live --kinds BashCommand --contains "$LIVE_CMD" --show 0
  control-agent-server ws read f13-live --kinds BashOutput --contains QA_F13_LIVE --expect-min 1 --show 0
  control-agent-server ws listen /sockets/bash-events --query resend_mode=all --until-kind BashOutput \
    --until command_id="$EXEC_CMD" --duration 10 --show 0 --save F13.ws-live/replay
  ```
  捕获自己的探针命令返回到它自己，因此在 REST 开始之前订阅。 它随后持有 `BashCommand` 和另一个
  REST命令的`BashOutput`(`QA_F13_LIVE`)； 重播连接接收本次运行的第一个命令的输出，该输出在连接之前存储。
- **通过套接字的命令 (`F13.ws-command`)。**同一连接上出现一个无效帧，然后出现一个有效帧。
  ```sh
  control-agent-server ws listen /sockets/bash-events --send '{"cmd": "echo nope"}' \
    --until-kind BashError --until code=ValidationError --duration 10 --save F13.ws-command/error
  control-agent-server ws listen /sockets/bash-events --send '{"cmd": "echo nope"}' \
    --send '{"command": "echo QA_F13_WS_CMD", "timeout": 30}' --expect-kind BashError \
    --until-kind BashOutput --until exit_code=0 --duration 20 --save F13.ws-command/after-error
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query sort_order=TIMESTAMP_DESC --query limit=1 --check items.0.command eq 'echo QA_F13_WS_CMD' \
    --check items.0.timeout eq 30
  ```
  第一个连接 `{"kind": "BashError", "code": "ValidationError"}`。 第二个也得到了相同的 `BashError`，然后，同样的连接上，无效帧之后的命令仍然运行 (`BashOutput`，其中 `exit_code` 为 0)。 REST 查找看到它 `timeout`。
- **已弃用重播标志 (`F13.ws-resend-all`).** `resend_all=true`，然后是一个没有重播标志的连接，运行探测。

  需要：`F13.execute-sync`
  ```sh
  NDEP=$(control-agent-server logs --grep 'resend_all is deprecated' | jq .total_matching)
  control-agent-server ws listen /sockets/bash-events --query resend_all=true --until-kind BashOutput \
    --until command_id="$EXEC_CMD" --duration 10 --show 0 --save F13.ws-resend-all/replay
  control-agent-server logs --grep 'resend_all is deprecated' --expect-min $((NDEP + 1))
  control-agent-server ws listen /sockets/bash-events --send '{"command": "echo QA_F13_NO_REPLAY"}' \
    --until-kind BashOutput --until exit_code=0 --expect-frames 2 --duration 15 --save F13.ws-resend-all/no-replay
  ```
  已弃用标志重播了此运行的第一个命令（`EXEC_CMD`）的存储输出，以及服务器日志 `resend_all is deprecated`。 如果没有重放标志，连接只会收到其探针的 `BashCommand`
  `BashOutput`，两帧，历史记录中没有任何内容。
- **订阅者上限 (`F13.ws-subscriber-cap`)。**一个 Python 程序（
  `websockets` 从仓库的虚拟环境中的客户端运行 `exec`) 持有 50 个已认证的套接字，证明每个套接字都订阅了一个探针命令，然后打开第 51 个，关闭一个，再打开另一个`ws start` 成本高了一点 CLI 每个套接字大约有50 MB，所以会有50个，大约2.5 GB。
  ```sh
  NCAP=$(control-agent-server logs --grep 'Subscriber limit reached' | jq .total_matching)
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_ws_cap.py" <<'PY'
  import json, os, time
  from websockets.exceptions import ConnectionClosed
  from websockets.sync.client import connect
  URL = os.environ["AGENT_SERVER_URL"].replace("http", "ws", 1) + "/sockets/bash-events"
  KEY = os.environ["SESSION_API_KEY"]
  def subscribe():
      ws = connect(URL, open_timeout=10, max_size=None)
      ws.send(json.dumps({"type": "auth", "session_api_key": KEY}))
      return ws
  def probe(ws, marker):
      ws.send(json.dumps({"command": f"echo {marker}"}))
  def wait_output(ws, marker, timeout=20):
      deadline = time.monotonic() + timeout
      while True:
          frame = json.loads(ws.recv(timeout=max(0.1, deadline - time.monotonic())))
          if frame.get("kind") == "BashOutput" and marker in (frame.get("stdout") or ""):
              return
  socks = [subscribe() for _ in range(50)]
  probe(socks[-1], "QA_F13_CAP_FULL")
  for ws in socks:
      wait_output(ws, "QA_F13_CAP_FULL")
  extra = subscribe()
  try:
      extra.recv(timeout=10)
      raise SystemExit("51st socket was neither closed nor silent")
  except ConnectionClosed as exc:
      assert exc.rcvd is not None and exc.rcvd.code == 1013, exc.rcvd
      assert exc.rcvd.reason == "Too many bash event connections", exc.rcvd
  print("QA_F13_CAP_51ST_1013")
  socks.pop().close()
  for attempt in range(20):
      ws = subscribe()
      try:
          probe(ws, f"QA_F13_CAP_SLOT_{attempt}")
          wait_output(ws, f"QA_F13_CAP_SLOT_{attempt}")
          break
      except ConnectionClosed:
          time.sleep(0.5)
  else:
      raise SystemExit("no slot freed after closing one socket")
  socks.append(ws)
  for ws in socks:
      ws.close()
  print("QA_F13_CAP_OK")
  PY
  control-agent-server exec --timeout 120 --expect-output QA_F13_CAP_51ST_1013 --expect-output QA_F13_CAP_OK \
    --save F13.ws-subscriber-cap/program -- .venv/bin/python "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_ws_cap.py"
  control-agent-server logs --grep 'Subscriber limit reached' --expect-min $((NCAP + 1))
  control-agent-server ws listen /sockets/bash-events --send '{"command": "echo QA_F13_CAP_AFTER"}' \
    --until-kind BashOutput --until exit_code=0 --duration 15
  ```
  所有50个端口都接收探针的输出，因此所有端口都订阅了。 第51节以代码1013和原因`Too many bash event connections`（以及服务器日志`Subscriber limit reached`）关闭。 在其中一个套接字关闭后，会有一个新的套接字订阅并运行其探针，然后程序关闭它们后，CLI 个套接字又会工作起来。 上限是每台服务器
  for the global scope (`PubSub(max_subscribers=50)` in `bash_service.py`),
  因此共享服务器上的其他消费者的套接字对其不利。
- **单次和批量读取 (`F13.get-events`)。**按十六进制 id，然后是缺少 id 的批次。

  需要：`F13.execute-sync`
  ```sh
  OUT_ID=$(control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$EXEC_CMD" \
    --field items.0.id)
  control-agent-server api GET "/api/bash/bash_events/$EXEC_CMD" --check id eq "$EXEC_CMD" \
    --check kind eq BashCommand --save F13.get-events/command
  control-agent-server api GET "/api/bash/bash_events/$OUT_ID" --check kind eq BashOutput \
    --check command_id eq "$EXEC_CMD" --check exit_code eq 3
  control-agent-server api GET /api/bash/bash_events/00000000000000000000000000000000 --expect 404
  control-agent-server api GET /api/bash/bash_events/ \
    --json "[\"$OUT_ID\", \"00000000000000000000000000000000\", \"$EXEC_CMD\"]" --expect 200 \
    --check . len-eq 3 --check 0.kind eq BashOutput --check 1 missing --check 2.id eq "$EXEC_CMD" \
    --save F13.get-events/batch
  control-agent-server api GET /api/bash/bash_events/ --expect 422
  ```
  两个id都解析了，未知的id是404，批次保持输入顺序，`null`在中间槽位。
- **搜索(`F13.search`)。**过滤、排序、UTC 时间窗口、分页和验证，超过三个新命令。

  需要：`F13.execute-sync`
  ```sh
  T0=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)
  for n in 1 2 3; do
    control-agent-server api POST /api/bash/execute_bash_command --json "{\"command\": \"echo QA_F13_PAGE_$n\"}" \
      --check exit_code eq 0 --field command_id
  done
  T1=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query timestamp__gte="$T0" --query timestamp__lt="$T1" --check items len-eq 3 \
    --check items.0.command eq 'echo QA_F13_PAGE_1' --save F13.search/utc-window
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query timestamp__lt="$T0" --check items not-contains QA_F13_PAGE
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --check items not-contains BashOutput --check items.0.id eq "$EXEC_CMD"
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$EXEC_CMD" \
    --check items len-eq 1 --check items.0.kind eq BashOutput
  NEXT=$(control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query sort_order=TIMESTAMP_DESC --query limit=2 --check items len-eq 2 \
    --check items.0.command eq 'echo QA_F13_PAGE_3' --check items.1.command eq 'echo QA_F13_PAGE_2' \
    --save F13.search/page-1 --field next_page_id)
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query sort_order=TIMESTAMP_DESC --query limit=2 --query page_id="$NEXT" \
    --check items.0.command eq 'echo QA_F13_PAGE_1' --save F13.search/page-2
  control-agent-server api GET /api/bash/bash_events/search --query limit=0 --expect 422
  control-agent-server api GET /api/bash/bash_events/search --query limit=101 --expect 422
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashError --expect 422
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq=not-a-uuid --expect 422
  control-agent-server api GET /api/bash/bash_events/search --query sort_order=NEWEST --expect 422
  ```
  窗口恰好包含三个页面命令。 `kind__eq` 仅保留命令（升序，运行的第一个命令）
  `command_id__eq` 仅返回该命令的输出； 降序页面为 PAGE_3、PAGE_2，然后是 PAGE_1； 每个错误参数都是 422。
- **偏移时间戳 (`F13.timestamp-offset`).**用 `+02:00` 书写的同一时刻必须选择与其 `Z` 拼写相同的事件。
  ```sh
  TZ_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_TZ"}' --field command_id)
  GTE_UTC=$(date -u -d '-1 minute' +%Y-%m-%dT%H:%M:%SZ)
  GTE_PLUS2=$(TZ=Etc/GMT-2 date -d '-1 minute' +%Y-%m-%dT%H:%M:%S%:z)
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query timestamp__gte="$GTE_UTC" --check items contains "$TZ_CMD" --save F13.timestamp-offset/utc
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query timestamp__gte="$GTE_PLUS2" --check items contains "$TZ_CMD" --save F13.timestamp-offset/plus-two
  ```
  两个搜索都包含命令：the `Z` window 是阳性对照，service 将 aware 绑定转换为 UTC 在比较它与之前 UTC 文件名前缀 (`bash_service.py`  `_timestamp_to_str`, 所以
  `+02:00` 窗口选择同一时刻。 没有偏移量的边界读作 UTC。
- **输出块(`F13.output-chunks`)。**输出 1,100,012 个字符，通过搜索和 SDK 读回。
  ```sh
  BIG_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "yes a | head -c 1100000; echo QA_F13_TAIL", "timeout": 60}' \
    --expect 200 --check exit_code eq 0 --field command_id)
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$BIG_CMD" \
    --check items len-eq 2 --check items.0.order eq 0 --check items.0.stdout len-eq 1048576 \
    --check items.0.exit_code missing --check items.1.order eq 1 --check items.1.stdout len-eq 51436 \
    --check items.1.exit_code eq 0 --field items.1.order
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$BIG_CMD" \
    --query order__gt=0 --check items len-eq 1 --check items.0.order eq 1 \
    --check items.0.stdout contains QA_F13_TAIL --save F13.output-chunks/order-gt-0 --field items.0.order
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_sdk_big.py" <<'PY'
  import os
  from openhands.sdk.workspace import RemoteWorkspace
  ws = RemoteWorkspace(host=os.environ["AGENT_SERVER_URL"], api_key=os.environ["SESSION_API_KEY"], working_dir=os.environ["AGENT_SERVER_VERIFY_RUN"])
  r = ws.execute_command("yes a | head -c 1100000; echo QA_F13_TAIL", timeout=60)
  assert r.exit_code == 0 and len(r.stdout) == 1100012 and r.stdout.endswith("a\nQA_F13_TAIL\n"), (r.exit_code, len(r.stdout))
  print("QA_F13_SDK_BIG_OK", len(r.stdout))
  PY
  control-agent-server exec --expect-output QA_F13_SDK_BIG_OK --save F13.output-chunks/sdk -- \
    .venv/bin/python "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_sdk_big.py"
  ```
  搜索返回两个分块（1048576个字符，没有退出码，然后是51436个字符以`QA_F13_TAIL`结尾，`exit_code`为0）。 `order__gt=0` 只返回第二部分。 SDK输出`QA_F13_SDK_BIG_OK 1100012`。
- **排序过滤器和分页 (`F13.order-gt-paging`)。**看到顺序 0 的轮询器会请求下一个输出，每页一个。

  需要：`F13.output-chunks`
  ```sh
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$BIG_CMD" \
    --query order__gt=0 --query limit=2 --check items len-eq 1 --check items.0.order eq 1 \
    --check next_page_id missing --quiet --save F13.order-gt-paging/limit-2
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$BIG_CMD" \
    --query order__gt=0 --query limit=1 --check items len-eq 1 --check items.0.order eq 1 \
    --quiet --save F13.order-gt-paging/limit-1
  ```
  在页面上同时包含两个部分 `order__gt=0` 只保留了 chunk 1（阳性对照：过滤器有效）。 预期：单页应包含 chunk 1。 `_search_bash_events_sync` (`bash_service.py`) 丢弃输出 `order <= order__gt` 之前 `limit` 数它们，和
  `next_page_id` 命名下一个通过过滤器的事件。 的 Python  SDK polls with `order__gt` 和 `limit=100` and ignores `next_page_id`所以这就是它让 `RemoteWorkspace.execute_command` 获取第100个及以后的分块：每次轮询返回它已经看到的最高顺序之后的下一个100个分块。 端到端检查（`yes a | head -c 106000000; echo QA_F13_HUGE_TAIL`) 写了100 MiB 因为这是事件文件，所以这不是一个食谱。
- **通过执行(`F13.execute-large-output`).**获得大量输出同步路由必须返回命令打印的所有内容。
  ```sh
  control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "yes a | head -c 1100000; echo QA_F13_TAIL", "timeout": 60}' --expect 200 \
    --check exit_code eq 0 --check stdout len-eq 1100012 --quiet --save F13.execute-large-output/execute
  ```
  预期：`stdout` 包含全部 1,100,012 个字符，`exit_code` 为 0。
  处理程序 (`bash_router.py` `execute_bash_command`) 读取命令的 `BashOutput` 事件的每一页，分别连接 stdout 和 stderr
  `order`，并返回带有连接文本的最终块（此处为 `order` 1），因此 TS 客户端的 `RemoteWorkspace.executeCommand` 和
  `BashClient.executeCommand` 获取整个输出。 过去 100 个块的退出代码仍然是最终块的（`exit 7` 在 101 MiB 报告 7 之后），而不是 null。
- **超时 (`F13.timeout`).** 30 秒的睡眠时间为 2 秒超时。 sleep 不是 shell 的最后一个命令，因此 `/bin/sh` 将其作为子命令进行分叉； 它独特的持续时间使得该子进程可以通过 `pgrep` 找到，这证明整个进程组都被杀死，而不仅仅是 shell。 当 `pgrep` 看到子进程还活着时，执行在后台运行。
  ```sh
  SLP=30.$RANDOM
  BODY="{\"command\": \"echo QA_F13_STARTED; sleep $SLP; echo QA_F13_NOT_REACHED\", \"timeout\": 2}"
  ( control-agent-server api POST /api/bash/execute_bash_command --json "$BODY" \
    --expect 200 --timeout 20 --expect-max-ms 8000 --check exit_code eq -1 \
    --check stdout eq $'QA_F13_STARTED\n' --quiet --save F13.timeout/execute ) &
  EXEC_JOB=$!
  for i in $(seq 1 40); do pgrep -fx "sleep $SLP" > /dev/null && break; sleep 0.1; done
  pgrep -fx "sleep $SLP"
  wait "$EXEC_JOB"
  test -z "$(pgrep -fx "sleep $SLP" || true)"
  ```
  `sleep` 孩子在通话期间正在跑。 调用大约两秒钟后（不到八秒），返回值为 `exit_code` -1，输出在超时之前，子进程已经消失。
- **停止一个命令 (`F13.stop`)。**两个运行命令，一个停止。 与超时项目符号中一样，睡眠是一个具有独特持续时间的分叉子级。
  ```sh
  SLP=600.$RANDOM
  BODY="{\"command\": \"sleep $SLP; echo QA_F13_NOT_REACHED\"}"
  STOP_CMD=$(control-agent-server api POST /api/bash/start_bash_command --json "$BODY" --field id)
  OTHER_CMD=$(control-agent-server api POST /api/bash/start_bash_command \
    --json '{"command": "sleep 5; echo QA_F13_OTHER"}' --field id)
  for i in $(seq 1 40); do pgrep -fx "sleep $SLP" > /dev/null && break; sleep 0.1; done
  pgrep -fx "sleep $SLP"
  control-agent-server api POST "/api/bash/bash_commands/$STOP_CMD/stop" --expect 200 \
    --check success eq true --save F13.stop/stop
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$OTHER_CMD" \
    --check items len-eq 0
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$STOP_CMD" --until-ok 15 \
    --check items len-eq 1 --check items.0.exit_code eq -15 --check items.0.stdout missing \
    --save F13.stop/stopped-output
  test -z "$(pgrep -fx "sleep $SLP" || true)"
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$OTHER_CMD" --until-ok 15 \
    --check items len-eq 1 --check items.0.exit_code eq 0 --check items.0.stdout eq $'QA_F13_OTHER\n' \
    --save F13.stop/other-output
  ```
  停止命令的唯一输出是 `exit_code` -15 (SIGTERM 是其进程组) 和没有 stdout，而其子进程 `sleep` 已经不存在。 另外一条命令还在停止后继续运行，并打印 `QA_F13_OTHER`
  `exit_code` 0.
- **停止是幂等的 (`F13.stop-idempotent`)。**完成的、虚线的、未知的和格式错误的 ID。

  需要：`F13.execute-sync`、`F13.stop`
  ```sh
  control-agent-server api POST "/api/bash/bash_commands/$STOP_CMD/stop" --expect 200 \
    --check success eq true --save F13.stop-idempotent/again
  STOP_DASHED=$(echo "$STOP_CMD" | sed -E 's/(.{8})(.{4})(.{4})(.{4})(.{12})/\1-\2-\3-\4-\5/')
  control-agent-server api POST "/api/bash/bash_commands/$STOP_DASHED/stop" --expect 200
  control-agent-server api POST "/api/bash/bash_commands/$EXEC_CMD/stop" --expect 200
  control-agent-server api POST /api/bash/bash_commands/00000000000000000000000000000000/stop --expect 404 \
    --save F13.stop-idempotent/unknown
  control-agent-server api POST /api/bash/bash_commands/not-a-uuid/stop --expect 422
  ```
  `{"success": true}` 表示已完成的命令（通过十六进制或划线 ID 返回）。 一个从未启动的ID返回404（SDK和TS客户端将此视为已停止）。 非UUID是422。
- **作用域 cwd (`F13.scoped-cwd`).**默认、内部、外部、转义、相对以及 SDK 的作用域工作区。
  ```sh
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json '{"command": "pwd; mkdir -p qa-sub"}' --expect 200 --check exit_code eq 0 \
    --check stdout eq "$WS1"$'\n' --save F13.scoped-cwd/default
  test -d "$WS1/qa-sub"
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json "{\"command\": \"pwd\", \"cwd\": \"$WS1/qa-sub\"}" --check stdout eq "$WS1/qa-sub"$'\n'
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json "{\"command\": \"pwd\", \"cwd\": \"$WS2\"}" --expect 422 \
    --check detail eq 'cwd must be inside the conversation workspace' --save F13.scoped-cwd/other-workspace
  control-agent-server api POST "/api/conversations/$CID/bash/start_bash_command" \
    --json "{\"command\": \"pwd\", \"cwd\": \"$WS1/qa-sub/../..\"}" --expect 422 \
    --check detail eq 'cwd must be inside the conversation workspace'
  control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json '{"command": "pwd", "cwd": "qa-sub"}' --expect 422 \
    --check detail eq 'cwd must be inside the conversation workspace'
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_sdk_scoped.py" <<'PY'
  import os, sys
  from openhands.sdk.workspace import RemoteWorkspace
  ws = RemoteWorkspace(host=os.environ["AGENT_SERVER_URL"], api_key=os.environ["SESSION_API_KEY"],
                       working_dir=sys.argv[2], runtime_conversation_id=sys.argv[1])
  r = ws.execute_command("pwd", timeout=30)
  assert r.exit_code == 0 and r.stdout == sys.argv[2] + "\n", (r.exit_code, r.stdout, r.stderr)
  print("QA_F13_SDK_SCOPED_OK")
  PY
  control-agent-server exec --expect-output QA_F13_SDK_SCOPED_OK --save F13.scoped-cwd/sdk -- \
    .venv/bin/python "$AGENT_SERVER_VERIFY_RUN/fixtures/qa_f13_sdk_scoped.py" "$CID" "$WS1"
  ```
  `pwd` 打印工作区，然后打印 `qa-sub`； 另一个对话的工作区，转义路径和相对路径是422
  `cwd must be inside the conversation workspace`; SDK 与
  `runtime_conversation_id` 落在同一个工作区中。
- **范围内的路线 (`F13.scoped-routes`).**执行、读回、开始和停止内部对话 `CID`。
  ```sh
  SC_EXEC=$(control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json '{"command": "echo QA_F13_SCOPED > scoped.txt; cat scoped.txt"}' --check exit_code eq 0 \
    --check stdout eq $'QA_F13_SCOPED\n' --save F13.scoped-routes/execute --field command_id)
  test "$(cat "$WS1/scoped.txt")" = QA_F13_SCOPED
  SC_OUT=$(control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" \
    --query command_id__eq="$SC_EXEC" --check items len-eq 1 --save F13.scoped-routes/search --field items.0.id)
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/$SC_EXEC" \
    --check kind eq BashCommand --check cwd eq "$WS1" --save F13.scoped-routes/get
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/" \
    --json "[\"$SC_OUT\", \"00000000000000000000000000000000\"]" --check . len-eq 2 \
    --check 0.stdout eq $'QA_F13_SCOPED\n' --check 1 missing --save F13.scoped-routes/batch
  SLP=600.$RANDOM
  BODY="{\"command\": \"sleep $SLP; echo QA_F13_NOT_REACHED\"}"
  SC_LONG=$(control-agent-server api POST "/api/conversations/$CID/bash/start_bash_command" --json "$BODY" \
    --check cwd eq "$WS1" --field id)
  for i in $(seq 1 40); do pgrep -fx "sleep $SLP" > /dev/null && break; sleep 0.1; done
  pgrep -fx "sleep $SLP"
  control-agent-server api POST "/api/conversations/$CID/bash/bash_commands/$SC_LONG/stop" --expect 200 \
    --check success eq true --save F13.scoped-routes/stop
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --query command_id__eq="$SC_LONG" \
    --until-ok 15 --check items len-eq 1 --check items.0.exit_code eq -15 --save F13.scoped-routes/stopped
  test -z "$(pgrep -fx "sleep $SLP" || true)"
  ```
  命令在工作区中写入了`scoped.txt`。 搜索，得到
  `cwd`设置为工作区)并批量读回； 作用域停止以 `exit_code` -15 结束休眠命令，并且其子命令 `sleep` 消失。 没有套接字携带作用域事件，因此 `--until-ok` 轮询搜索直到写入最终输出。
- **范围隔离 (`F13.scoped-isolation`).**从所有其他作用域看到的作用域命令。
  ```sh
  control-agent-server ws start /sockets/bash-events --name f13-iso --duration 120 \
    --send '{"command": "echo QA_F13_ISO_PROBE"}'
  control-agent-server ws read f13-iso --kinds BashOutput --contains QA_F13_ISO_PROBE --wait 15 --show 0
  MARK=QA_F13_ISO_$RANDOM
  ISO_CMD=$(control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json "{\"command\": \"echo $MARK\"}" --check exit_code eq 0 --field command_id)
  FLUSH_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_FLUSH"}' --field command_id)
  control-agent-server ws stop f13-iso --kinds BashOutput --contains "$FLUSH_CMD" --wait 15 --show 0 \
    --save F13.scoped-isolation/global-socket
  control-agent-server ws read f13-iso --contains "$MARK" --expect-none --show 0
  control-agent-server ws read f13-iso --contains "$ISO_CMD" --expect-none --show 0
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --query sort_order=TIMESTAMP_DESC --check items not-contains "$MARK" --save F13.scoped-isolation/global-search
  control-agent-server api GET "/api/bash/bash_events/$ISO_CMD" --expect 404
  control-agent-server api POST "/api/bash/bash_commands/$ISO_CMD/stop" --expect 404
  control-agent-server api GET "/api/conversations/$CID2/bash/bash_events/search" --check items len-eq 0 \
    --save F13.scoped-isolation/other-conversation
  control-agent-server api GET "/api/conversations/$CID2/bash/bash_events/$ISO_CMD" --expect 404
  control-agent-server state ls "bash_events/*_BashCommand_$ISO_CMD" --conversation "$CID" --expect-count 1
  control-agent-server state ls "server/workspace/bash_events/*$ISO_CMD*" --expect-count 0
  ```
  全局套接字已订阅（其探针返回），并看到了flush命令，但没有带有命名标记或命令ID的帧。 全局搜索、获取和停止以及第二对话都不认识命令。 它的事件文件位于对话的`bash_events`目录下，而不是全局目录下。
- **未知对话 (`F13.scoped-unknown`).**每个范围内的路由都有一个格式良好的 id，但不命名任何会话。
  ```sh
  NOCID=00000000-0000-0000-0000-000000000000
  control-agent-server api GET "/api/conversations/$NOCID/bash/bash_events/search" --expect 404 \
    --check detail contains 'Conversation not found' --save F13.scoped-unknown/search
  control-agent-server api GET "/api/conversations/$NOCID/bash/bash_events/00000000000000000000000000000000" --expect 404
  control-agent-server api GET "/api/conversations/$NOCID/bash/bash_events/" --json '["x"]' --expect 404
  control-agent-server api POST "/api/conversations/$NOCID/bash/start_bash_command" \
    --json '{"command": "echo QA_F13_NOCONV"}' --expect 404
  control-agent-server api POST "/api/conversations/$NOCID/bash/execute_bash_command" \
    --json '{"command": "echo QA_F13_NOCONV"}' --expect 404 --save F13.scoped-unknown/execute
  control-agent-server api DELETE "/api/conversations/$NOCID/bash/bash_events" --expect 404
  control-agent-server api POST "/api/conversations/$NOCID/bash/bash_commands/00000000000000000000000000000000/stop" --expect 404
  ```
  所有七人都404 `Conversation not found: 00000000-...`.
- **重新启动 (`F13.persist-restart`)。**两个范围的历史记录都在磁盘上。

  需要：`F13.execute-sync`、`F13.scoped-routes`
  ```sh
  control-agent-server restart
  control-agent-server api GET "/api/bash/bash_events/$EXEC_CMD" --check kind eq BashCommand \
    --save F13.persist-restart/global-get
  control-agent-server api GET /api/bash/bash_events/search --query command_id__eq="$EXEC_CMD" \
    --check items.0.exit_code eq 3 --check items.0.stdout eq $'QA_F13_OUT\n'
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --query command_id__eq="$SC_EXEC" \
    --check items.0.stdout eq $'QA_F13_SCOPED\n' --save F13.persist-restart/scoped-search
  control-agent-server api POST "/api/bash/bash_commands/$EXEC_CMD/stop" --expect 200
  ```
  重启后，全局命令的输出和局部输出仍然可读，完成的命令停止时仍然能找到它。
- **清除(`F13.clear`)。**首先是全局，然后是对话的历史。

  需要：`F13.execute-sync`、`F13.scoped-routes`
  ```sh
  N_GLOBAL=$(control-agent-server state ls 'server/workspace/bash_events/*' | jq .count)
  test "$N_GLOBAL" -ge 20
  control-agent-server api DELETE /api/bash/bash_events --expect 200 --check cleared_count eq "$N_GLOBAL" \
    --save F13.clear/global
  control-agent-server api GET /api/bash/bash_events/search --check items len-eq 0 --save F13.clear/global-empty
  control-agent-server state ls 'server/workspace/bash_events/*' --expect-count 0
  control-agent-server api POST "/api/bash/bash_commands/$EXEC_CMD/stop" --expect 404
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --query command_id__eq="$SC_EXEC" \
    --check items len-eq 1
  N_SCOPED=$(control-agent-server state ls 'bash_events/*' --conversation "$CID" | jq .count)
  test "$N_SCOPED" -ge 8
  control-agent-server api DELETE "/api/conversations/$CID/bash/bash_events" --expect 200 \
    --check cleared_count eq "$N_SCOPED" --save F13.clear/scoped
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --check items len-eq 0
  control-agent-server state ls 'bash_events/*' --conversation "$CID" --expect-count 0
  control-agent-server api DELETE /api/bash/bash_events --check cleared_count eq 0
  ```
  全局清报精确显示全球事件文件的数量，搜索和目录为空，且使已完成的`EXEC_CMD`无法停止（404），而受限制的输出则存活。 该端点会清除会话目录中的所有报告，并删除所有文件，从而在全局存储中留下没有任何新内容。
- **保留 (`F13.retention`)。**服务器自己的清除窗口正在测试中，因此这颗子弹会越过它。
  ```sh
  RET_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_RETAIN"}' --field command_id)
  SC_RET=$(control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json '{"command": "echo QA_F13_RETAIN_SCOPED"}' --field command_id)
  sleep 2
  control-agent-server restart --config-json '{"bash_events_retention_seconds": 1}'
  control-agent-server api GET "/api/bash/bash_events/$RET_CMD" --expect 404 --save F13.retention/global-purged
  control-agent-server api GET /api/bash/bash_events/search --check items len-eq 0
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/$SC_RET" --expect 200 \
    --check command eq 'echo QA_F13_RETAIN_SCOPED' --save F13.retention/scoped-kept
  control-agent-server restart --config-json '{"bash_events_retention_seconds": null}'
  ```
  在启动时，清理操作会移除两秒前的全局事件。 对话事件未受影响。 最后一次重新启动会再次关闭保留。
- **滚动保持力 (`F13.retention-rolling`).**同样的一秒窗口，现在用于启动后写入的事件。 循环在启动时运行，然后每 `max(60, retention / 2)` = 60 秒运行一次； 该计时器正在测试中，因此子弹轮询最多 90 秒，中间不会重新启动。
  ```sh
  control-agent-server restart --config-json '{"bash_events_retention_seconds": 1}'
  ROLL_CMD=$(control-agent-server api POST /api/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_ROLLING"}' --check exit_code eq 0 --field command_id)
  SC_ROLL=$(control-agent-server api POST "/api/conversations/$CID/bash/execute_bash_command" \
    --json '{"command": "echo QA_F13_ROLLING_SCOPED"}' --check exit_code eq 0 --field command_id)
  UP0=$(control-agent-server api GET /server_info --field uptime)
  control-agent-server api GET "/api/bash/bash_events/$ROLL_CMD" --expect 200 --check command eq 'echo QA_F13_ROLLING' \
    --save F13.retention-rolling/fresh
  T0=$SECONDS
  control-agent-server api GET "/api/bash/bash_events/$ROLL_CMD" --expect 404 --until-ok 90 \
    --save F13.retention-rolling/purged
  test $((SECONDS - T0)) -ge 20
  control-agent-server api GET /server_info --check uptime gt "$UP0"
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand \
    --check items not-contains QA_F13_ROLLING
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/$SC_ROLL" --expect 200 \
    --check command eq 'echo QA_F13_ROLLING_SCOPED' --save F13.retention-rolling/scoped-kept
  control-agent-server restart --config-json '{"bash_events_retention_seconds": null}'
  ```
  新的全球命令运行后立即可读，然后在下一次运行后大约10秒后返回404（而不是立即返回）
  `/server_info` 正常运行时间持续增长（未发生重启）； 同时写入的作用域命令仍然存在。 最后一次重新启动会再次关闭保留。
- **格式错误的对话 ID (`F13.scoped-bad-id`)。**非 UUID 对话 ID 必定是验证错误。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/bash/bash_events/search" --expect 200
  control-agent-server api GET /api/conversations/not-a-uuid/bash/bash_events/search --expect 422 \
    --save F13.scoped-bad-id/search
  control-agent-server api POST /api/conversations/not-a-uuid/bash/execute_bash_command \
    --json '{"command": "echo QA_F13_BADID"}' --expect 422
  ```
  同样的搜索，使用真实对话ID，返回200（正控制）。 每个受控的bash路由都返回422 `not-a-uuid`, 采用标准验证错误发生在 `["path", "runtime_conversation_id"]`就像受控文件、git 和 vscode 路由，以及不记录堆栈跟踪。 没有运行。
- **空闲驱逐会杀死正在运行的命令（`F13.scoped-idle-eviction`），已知错误。**第二次运行有 5 秒空闲 TTL 和两个从未运行的对话：
  `EV_CID` 带有正在运行的作用域命令，然后 `EV_IDLE` 没有任何内容，即正控制。 驱逐循环自己的 60 秒计时器正在测试中，因此子弹会进行轮询（最多 100 秒），直到通行证被驱逐 `EV_IDLE`。
  ```sh
  EV=$(control-agent-server launch --new --name f13-evict --config-json '{"conversation_idle_ttl_seconds": 5}' --print-run)
  trap 'control-agent-server stop --run "$EV" > /dev/null 2>&1 || true' EXIT
  EV_CID=$(control-agent-server conversation start --run "$EV" --body-json "$NOLLM" --no-run --no-autotitle --print-id)
  EV_MARK=QA_F13_EVICT_$RANDOM
  EV_CMD=$(control-agent-server api POST "/api/conversations/$EV_CID/bash/start_bash_command" --run "$EV" \
    --json "{\"command\": \"sleep 600 # $EV_MARK\"}" --field id)
  EV_IDLE=$(control-agent-server conversation start --run "$EV" --body-json "$NOLLM" --no-run --no-autotitle --print-id)
  for i in $(seq 1 20); do pgrep -f "$EV_MARK" > /dev/null && break; sleep 0.25; done
  pgrep -f "$EV_MARK"
  control-agent-server state ls owner_lease.json --run "$EV" --conversation "$EV_IDLE" --expect-count 1
  control-agent-server logs --run "$EV" --grep 'Evicted idle' --expect-none
  T0=$SECONDS
  until control-agent-server state ls owner_lease.json --run "$EV" --conversation "$EV_IDLE" --expect-count 0 > /dev/null; do
    test $((SECONDS - T0)) -le 100
    sleep 2
  done
  control-agent-server logs --run "$EV" --grep 'Evicted idle' --expect-min 1
  sleep 3
  control-agent-server assert --value "$(pgrep -fc "$EV_MARK")" --check . ge 1  # 错误：值 eq 0
  control-agent-server api POST "/api/conversations/$EV_CID/bash/bash_commands/$EV_CMD/stop" --run "$EV" --expect 200
  control-agent-server api GET "/api/conversations/$EV_CID/bash/bash_events/search" --run "$EV" \
    --query command_id__eq="$EV_CMD" --until-ok 15 --check items.-1.exit_code eq -15
  ```
  在等待之前没有记录到驱逐。 然后，闲聊的租期结束，`Evicted idle conversation` 被记录，因此有驱逐过程。 `EV_CID` 是第一个创建的，所以相同的 pass 会先到达它。 这三个人的安排涵盖了REST。 预期：通过该命令后，应该仍然在运行（然后小圆点会停止它，并且最终输出会报告 -15）。 今天 `EV_CID` 在同一遍中被驱逐，其作用域的服务被关闭，`sleep` 是 SIGKILLed，并且从不写入 `BashOutput`。
  `EventService.is_idle_evictable()` 忽略正在运行的 bash 命令。

<a id="gotchas"></a>

## 陷阱

- 命令通过 `/bin/sh -c` 运行（Debian 和 Ubuntu 上为破折号），而不是 bash：
  `{1..3}`、`[[ ]]` 和 `source` 失败。 不涉及tmux； 这个家庭不需要任何超出底线的东西。
- 每个载荷中的 ID 都是 32 个字符的十六进制。 `GET .../bash_events/{event_id}` 与 `_<event_id>` 后缀匹配文件，因此虚线 UUID 是 404，
  while the stop route parses any UUID spelling.
- `command_id__eq` 只返回 `BashOutput` 事件：`BashCommand` 文件名不包含命令 ID。 通过 id 获取命令本身。
- 批量读取的是GET，带有JSON数组体，需要尾部斜杠； 浏览器`fetch`无法发送（TS客户端`batchGetEvents`仅在Node下工作）。
- 未知的 `page_id` 在第一页默默地重新启动。 `order__gt` 在 `limit` 应用 (`F13.order-gt-paging`) 之前进行过滤，因此只有最后一页较短； 按照`next_page_id`直到`null`。
- `timestamp__gte`/`__lt`接受任何UTC偏移量； 没有界限的界限被读作UTC（参见`F13.timestamp-offset`）。
- 退出代码：实际代码，`-1` 表示超时或生成错误（缺少 cwd），`-15`（或 1 秒升级后的 `-9`）停止时。 因服务器关闭或空闲驱逐而终止的命令根本没有最终结果`BashOutput`； 轮询器等待永远不会出现的退出代码。
- 全局cwd不受限制并且相对于服务器进程cwd。 一个受控的 CWD 必须是绝对路径：一个相对路径会被解析为服务器进程的 CWD 并以 422 错误拒绝，即使该目录存在于工作区。
- `/sockets/bash-events` 是服务器范围的：每个客户端都能看到每个全局命令（按 `command_id` 过滤帧），没有连接时间帧，帧保留 `null` 字段，最多接受 50 个订阅者（第 51 个订阅者以 1013 关闭，`F13.ws-subscriber-cap`）。 会话范围的命令没有套接字； 轮询范围搜索（Python SDK 始终轮询）。
- `execute_bash_command` 保持 HTTP 请求对整个命令开放； 给出的 `api --timeout` 多于命令的 `timeout`。
- `DELETE .../bash_events` 不停止运行命令； 他们后来的输出仍然被写下来。
- `bash_events_retention_seconds`的保留期只适用于全局存储，启动时运行，然后每`max(60, N/2)`秒（`F13.retention-rolling`），因此事件可能会超出其窗口的时间，最多延迟一个间隔。
- 在 Docker 运行时模式 (`OH_CONVERSATION_RUNTIME=docker`) 下
  `/api/conversations/{id}/...` 路由被代理到会话的容器 (`docker_runtime/routers.py`) 中，因此作用域 cwd 值是容器路径，而 `/api/bash` 仍然在外部主机上运行。 该映射仅涵盖本地运行时。
- 5xx 主体被屏蔽为 `{"detail": "Internal Server Error", "exception": "..."}`； 断言 `exception` 为 500。
