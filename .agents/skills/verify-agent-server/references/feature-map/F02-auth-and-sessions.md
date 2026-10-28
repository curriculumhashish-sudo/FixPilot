<a id="authentication-and-workspace-sessions"></a>

# 身份验证和工作区会话

消费者如何证明自己是谁。 配置有会话 API 键的服务器在其 `/api/*` 路由上恰好接受一个 HTTP 凭据，
`X-Session-API-Key` 标头，并对其他所有内容回答 401。 它的 WebSockets 使用第一帧 `{"type": "auth", "session_api_key": ...}` 进行身份验证（查询参数和标头形式是已弃用，但仍然有效）。 多个密钥可以同时有效，因此可以在不停机的情况下轮换密钥，并且打开一个没有密钥的服务器。 浏览器无法为 `<iframe src>` 或 `<img src>` 添加头部，因此 `POST /api/auth/workspace-session` 交换头部为一个 HttpOnly 仅工作区文件路由认可的 cookie，`DELETE` 清除它。 CORS 决定哪个浏览器源可以使用凭据调用 API。

资料来源：`openhands-agent-server/openhands/agent_server/auth_router.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-agent-server/openhands/agent_server/middleware.py`、`openhands-agent-server/openhands/agent_server/sockets.py`、`openhands-agent-server/openhands/agent_server/config.py`、`openhands-agent-server/openhands/agent_server/env_parser.py`、`openhands-agent-server/openhands/agent_server/__main__.py`、`openhands-sdk/openhands/sdk/utils/command.py`

路线：`POST /api/auth/workspace-session`、`DELETE /api/auth/workspace-session`

<a id="sub-features"></a>

## 子功能

- `F02.http-key-required`：配置密钥后，`/api/*` 将答案 401 `{"detail": "Unauthorized"}` 路由到丢失或错误的 `X-Session-API-Key`，并服务携带运行密钥的请求。
- `F02.http-header-only`：常规 `/api/*` 路由仅接受标头中的密钥：工作区 cookie、`session_api_key` 查询参数和 `Authorization: Bearer` 都得到 401。
- `F02.ws-first-frame`：第一帧`{"type": "auth", "session_api_key": K}`验证`/sockets/events/{id}`、`/sockets/session/{id}`和`/sockets/bash-events`。
- `F02.ws-first-frame-reject`：在查找对话之前，错误的键、错误的 `type`、丢失的键或非对象第一帧会用 4001 `Authentication failed` 关闭套接字。
- `F02.ws-auth-timeout`：未发送第一帧的套接字在大约 10 秒后以 4001 关闭。
- `F02.ws-legacy-key`：已弃用`session_api_key`查询参数和`X-Session-API-Key`头仍然打开一个套接字，并且在它们之后发送的冗余验证帧被忽略。
- `F02.ws-legacy-reject`：错误的旧密钥会拒绝握手本身（HTTP 403，无关闭帧），即使随后会出现正确的第一帧。
- `F02.workspace-session-mint`：`POST /api/auth/workspace-session` 在 `Path=/api/conversations` 上返回 204，并设置带 HttpOnly `oh_workspace_session_key` 属性的 cookie；在回环主机上使用 `SameSite=none; Secure; Partitioned`；缺少有效请求头时返回 401 且不设置 cookie（cookie 自身不能签发另一个 cookie）。
- `F02.workspace-cookie-access`：单独创建的 cookie（cookie jar，无标头）加载工作区文件，也在重新启动后； 伪造的 cookie 或没有凭据会得到 401。
- `F02.workspace-session-delete`: `DELETE /api/auth/workspace-session` 在同一路径上使用 `Max-Age=0` cookie 回答 204，这会从 jar 中删除 cookie，因此工作区文件再次变为 401； 401 没有标题。
- `F02.multiple-keys`：每个配置的密钥（`OH_SESSION_API_KEYS_0`，`_1`，...）验证HTTP和WebSocket客户端； 未列出的密钥则不会。
- `F02.rotate-key` 重启后使用旋转的密钥，旧密钥在 HTTP 和 WebSockets 上会收到 401，其工作区 cookie 会停止工作，而新密钥则正常工作，而对话持久化会停止。
- `F02.keys-hidden-from-commands`：服务器运行的命令在其环境中看不到 `OH_SESSION_API_KEYS_*`、`SESSION_API_KEY` 或 `OH_SECRET_KEY`。
- `F02.cors-default-origins`：CORS 允许从 `localhost` 和 `127.0.0.1` 始发地（任何港口）出发的预检；凭据允许； 其他来源和 `Origin: null` 得到 400 `Disallowed CORS origin`，而简单的回复则不带有 `Access-Control-Allow-Origin`。
- `F02.cors-configured-origins`：`OH_ALLOW_CORS_ORIGINS_*`、`OH_ALLOW_CORS_ORIGIN_REGEX` 和 `DOCKER_HOST_ADDR` 重新启动后扩展允许的起始点。
- `F02.cors-workspace-routes`：工作区-会话和工作区文件路由允许任何带有凭据的http(s)源，但拒绝`Origin: null`，并且该通配符不会到达其他路由。
- `F02.no-auth-mode`：没有密钥的服务器提供没有标头的 `/api/*`（忽略任何标头），接受没有身份验证帧的套接字，并创建一个空的工作区 cookie。
- `F02.legacy-env-key`：旧的 `SESSION_API_KEY` 变量单独使用该键打开身份验证。
- `F02.default-bind`：未配置会话密钥时，没有 `--host` 启动的服务器在 `127.0.0.1` 上侦听；在配置会话密钥时，在 `0.0.0.0` 上侦听； `--host 0.0.0.0` 没有密钥仍然可以绑定，但会记录未经身份验证的绑定警告。
- `F02.workspace-cookie-root-path`在路径前缀后面`OH_WEB_URL` 带有路径)，通过前缀生成的 cookie URL 浏览器返回给前缀化的工作区文件 URLs.
- `F02.workspace-session-ipv6-loopback`：通过 IPv6 环回 (`Host: [::1]:PORT`) 到达的薄荷获得 `Secure; Partitioned`，如 `localhost` 和 `127.0.0.1`。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：当配置密钥时，每`/api/*`条路线都采用`X-Session-API-Key`。 探针和`/server_info`（F01）和`GET /api/init`不需要密钥； OpenAI兼容`/v1/*`网关也接受
  `Authorization: Bearer`（它自己的家族）。 即使没有密钥，未知的 `/api` 路径也是 404。
- REST: `POST /api/auth/workspace-session` 和
  `DELETE /api/auth/workspace-session`（都需要标头，不需要正文，204）。 该cookie仅由`GET /api/conversations/{conversation_id}/workspace`和`GET /api/conversations/{conversation_id}/workspace/{file_path:path}`（工作区文件路由，由另一个家族拥有； 此处用作第二个视图）。
- WebSocket: `/sockets/events/{conversation_id}`,
  `/sockets/session/{conversation_id}` 和 `/sockets/bash-events` 共享一个身份验证助手（`sockets.py` 中的 `_accept_authenticated_websocket`）：第一帧，或已弃用 `?session_api_key=` / `X-Session-API-Key` 标头。
- SDK: `RemoteWorkspace(host=..., api_key=...)` 在每个请求上发送标头 (`openhands-sdk/openhands/sdk/workspace/remote/remote_workspace_mixin.py`)；
  `RemoteConversation` 的事件套接字发送第一个身份验证帧 (`remote_conversation.py`, `_client_loop`)。
- TypeScript客户端：`HttpClient`从`apiKey`发送`X-Session-API-Key`；
  `RemoteWorkspace.startWorkspaceSession(conversationId)` 和
  `deleteWorkspaceSession()` 调用两条路由
  `credentials: 'include'`并返回工作区基数URL；
  `ConversationEventStream` 使用第一帧进行身份验证，同时
  `BashWebSocketClient` 仍使用已弃用查询参数。
- 配置：`OH_SESSION_API_KEYS_0..N`（或配置文件中的`session_api_keys`），旧版`SESSION_API_KEY`； CORS: `OH_ALLOW_CORS_ORIGINS_0..N`,
  `OH_ALLOW_CORS_ORIGIN_REGEX`, `DOCKER_HOST_ADDR`; `OH_WEB_URL` with a path 设置应用程序的根路径。
- 命令行：`python -m openhands.agent_server [--host H] [--port 8000]` (`__main__.py`)。 如果没有 `--host`，绑定地址将跟随身份验证
  姿势：环回无按键，所有接口有按键。
- Agent Canvas 在嵌入之前生成 cookie 工作区  HTML, images and PDFs 从另一个来源的iframe中上下文只）。
- 配方：`api --auth none|bad|previous`和`--header`驱动HTTP个案例； `ws listen --auth first-frame|query|header|none|bad` 插座盒； 一个小的 cookie-jar 助手（`curl` 到 `control-agent-server exec`，用 `Preconditions:` 编写）在浏览器中播放 cookie 和 CORS 预检； `restart --env`、`restart --rotate-key`和第二服务器(`launch --new --no-auth`)到达其他模式； `bind.sh`（也在
  `Preconditions:`）在没有启动器的情况下启动服务器以查看其默认绑定地址。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已实时并导出 (`launch --new`)，`doctor` 可以。 不需要 LLM 配置文件。 `curl`和`jq`在`PATH`上。 `tmux` 仅由运行命令的配方需要（bash-events 框架，`execute_bash_command`）； 每个都声明了 `Needs: tmux`，因此没有它的机器仍然驱动 HTTP、cookie 和 CORS 配方。
- 下面的块创建一个工作区，其中包含一个 HTML 文件、一个从不运行的对话 (`CID`) 和 `jar.sh`：一个类似浏览器的 `curl` 请求，将 cookie 保留在 `<run>/fixtures/qa-f02-cookies.txt` 中，仅在被告知时发送运行密钥 `key`，打印标头、正文和状态，并且失败，除非状态匹配并且每个 `has:TEXT` / `lacks:TEXT`（不区分大小写）都保留。 通过`control-agent-server exec`运行它，注入
  `AGENT_SERVER_URL` 和 `SESSION_API_KEY` 用于所选运行。
- 它也写入了 `bind.sh` 为了 `F02.default-bind`： 在一个私有网络中启动命名空间 (`unshare -rn`因此，端口8000在每次重播中都是空闲的，所以这个检查点的服务器就像一个操作员一样运行`python -m openhands.agent_server`, no `--host` 除非另有指定，默认使用端口 8000，并且具有自己的 `HOME` and config, waits until
  `/proc/net/tcp` 显示侦听套接字，停止服务器，打印其日志和 `listening on ADDRESS:8000`，如果没有侦听，则失败。 需要 `unshare` (util-linux) 和非特权用户命名空间或 root。
- 多个项目符号重新启动此运行 (`restart --env`, `--rotate-key`)； 他们添加的环境会保留到以后的子弹中。 需要另一种服务器模式的子弹会启动第二次运行，并在子弹结束时停止。

  ```sh
  F02="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f02"
  mkdir -p "$F02/workspace"
  printf '<p>qa-f02-workspace-file</p>\n' > "$F02/workspace/qa-f02.html"
  cat > "$F02/jar.sh" <<'EOF'
  # jar.sh METHOD PATH key|nokey STATUS [has:TEXT|lacks:TEXT]... [-- CURL_ARGS...]
  method=$1 path=$2 auth=$3 want=$4
  shift 4
  checks=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do checks+=("$1"); shift; done
  [ "${1:-}" = "--" ] && shift
  if [ "$auth" = key ]; then set -- "$@" -H "X-Session-API-Key: $SESSION_API_KEY"; fi
  jar="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f02-cookies.txt"
  out=$(curl -sS --noproxy '*' -D - -b "$jar" -c "$jar" -X "$method" -w '\nstatus=%{http_code}\n' "$@" "$AGENT_SERVER_URL$path")
  printf '%s\n' "$out"
  printf '%s\n' "$out" | grep -qx "status=$want" || { echo "FAIL: status is not $want" >&2; exit 1; }
  for c in "${checks[@]}"; do
    case $c in
      has:*) printf '%s\n' "$out" | grep -qiF -- "${c#has:}" || { echo "FAIL: missing ${c#has:}" >&2; exit 1; } ;;
      lacks:*) if printf '%s\n' "$out" | grep -qiF -- "${c#lacks:}"; then echo "FAIL: unexpected ${c#lacks:}" >&2; exit 1; fi ;;
    esac
  done
  EOF
  cat > "$F02/bind.sh" <<'EOF'
  # bind.sh DIR [SERVER_ARGS...], inside `unshare -rn env -i PATH=... QA_F02_PYTHON=...`
  dir=$1; shift
  mkdir -p "$dir/home"
  cd "$dir" || exit 1
  printf '{"preload_tools": false, "enable_vscode": false}\n' > config.json
  HOME="$dir/home" OH_PERSISTENCE_DIR="$dir/home/.openhands" OPENHANDS_AGENT_SERVER_CONFIG_PATH="$dir/config.json" \
    COLUMNS=400 PYTHONUNBUFFERED=1 "$QA_F02_PYTHON" -m openhands.agent_server "$@" > server.log 2>&1 &
  pid=$!
  addr=
  for _ in $(seq 240); do
    addr=$(awk '$4 == "0A" && $2 ~ /:1F40$/ {print $2}' /proc/net/tcp)
    [ -n "$addr" ] && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  kill "$pid" 2>/dev/null
  wait "$pid"
  cat server.log
  case $addr in
    00000000:1F40) echo 'listening on 0.0.0.0:8000' ;;
    0100007F:1F40) echo 'listening on 127.0.0.1:8000' ;;
    *) echo "FAIL: no listening socket on port 8000 (${addr:-none})" >&2; exit 1 ;;
  esac
  EOF
  CID=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$F02/workspace" --print-id)
  control-agent-server api GET "/api/conversations/$CID/workspace/qa-f02.html" --expect 200
  ```

- **HTTP (`F02.http-key-required`) 上需要密钥。**呼叫路线时没有密钥、使用错误密钥以及使用运行密钥。
  ```sh
  control-agent-server api GET /api/conversations/count --auth none --expect 401 --check detail eq Unauthorized --save F02.http-key-required/no-key
  control-agent-server api GET /api/conversations/count --auth bad --expect 401 --check detail eq Unauthorized --save F02.http-key-required/wrong-key
  control-agent-server api GET "/api/conversations/$CID" --auth none --expect 401
  control-agent-server api GET /api/conversations/count --expect 200 --check . ge 1 --save F02.http-key-required/run-key
  ```
  两种错误调用都返回 401 `{"detail": "Unauthorized"}`。 使用密钥时，计数至少为1（来自`Preconditions:`的对话）。
- **仅标头 (`F02.http-header-only`)。**随处提供正确的钥匙
  except the header.
  ```sh
  KEY=$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")
  control-agent-server api GET "/api/conversations/$CID" --auth none --cookie "oh_workspace_session_key=$KEY" --expect 401 --save F02.http-header-only/cookie
  control-agent-server api GET /api/conversations/count --auth none --query "session_api_key=$KEY" --expect 401 --save F02.http-header-only/query
  control-agent-server api GET /api/conversations/count --auth none --header "Authorization: Bearer $KEY" --expect 401 --save F02.http-header-only/bearer
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --check id eq "$CID"
  unset KEY
  ```
  这三个都是401。 因为浏览器会将 cookie 发送到路径下的 `/api/conversations`，包括这个路径。
- **每个套接字上的第一帧身份验证 (`F02.ws-first-frame`)。** CLI默认`--auth first-frame`先发送`{"type": "auth", "session_api_key": K}`； 没有确认，因此每个套接字都通过接下来发送的内容来证明这一点。

  需求：`tmux`
  ```sh
  control-agent-server ws listen "/sockets/events/$CID" --until-kind ConversationStateUpdateEvent --duration 15 --save F02.ws-first-frame/events
  control-agent-server ws listen "/sockets/session/$CID" --query after_seq=-1 --until-kind sync --duration 15 --save F02.ws-first-frame/session
  control-agent-server ws listen /sockets/bash-events --send '{"command":"echo qa-f02-first-frame"}' --until-kind BashOutput --duration 20 --save F02.ws-first-frame/bash
  ```
  事件套接字发送全状态 `ConversationStateUpdateEvent`，会话套接字发送 `sync` 帧，bash 套接字运行 `BashCommand`，然后运行 `BashOutput`。
- **拒绝第一帧 (`F02.ws-first-frame-reject`)。**错误的密钥、错误的类型、丢失的密钥、不是对象以及不存在的对话的错误密钥。
  ```sh
  control-agent-server ws listen "/sockets/events/$CID" --auth bad --expect-close 4001 --duration 10 --save F02.ws-first-frame-reject/events-wrong-key \
    | jq -e '.close.reason == "Authentication failed"'
  control-agent-server ws listen "/sockets/session/$CID" --auth bad --expect-close 4001 --duration 10
  control-agent-server ws listen /sockets/bash-events --auth bad --send '{"command":"echo qa-f02-refused"}' --expect-close 4001 --expect-no-kind BashOutput --duration 10 --save F02.ws-first-frame-reject/bash-wrong-key
  control-agent-server ws listen /sockets/bash-events --auth none --send '{"type":"hello","session_api_key":"x"}' --expect-close 4001 --duration 10 --save F02.ws-first-frame-reject/wrong-type
  control-agent-server ws listen /sockets/bash-events --auth none --send '{"type":"auth"}' --expect-close 4001 --duration 10
  control-agent-server ws listen /sockets/bash-events --auth none --send '[1]' --expect-close 4001 --duration 10
  control-agent-server ws listen /sockets/events/00000000-0000-4000-8000-000000000000 --auth bad --expect-close 4001 --duration 10 --save F02.ws-first-frame-reject/unknown-unauthenticated
  control-agent-server ws listen /sockets/events/00000000-0000-4000-8000-000000000000 --expect-close 4004 --duration 10
  ```
  每个拒绝都是一个代码为4001且原因的闭合帧
  `Authentication failed`，并且在错误按键之后发送的命令永远不会运行（没有 `BashOutput`）。 未经身份验证的套接字进行未知对话也会得到 4001； 只有经过身份验证的人才能获知 4004
  `Conversation not found`.
- **授权超时 (`F02.ws-auth-timeout`).**连接起来，什么也不说。 服务器自己的 10 秒计时器正在测试中，因此项目符号对其进行测量。
  ```sh
  T0=$SECONDS
  control-agent-server ws listen /sockets/bash-events --auth none --expect-close 4001 --duration 25 --save F02.ws-auth-timeout/silent
  test $((SECONDS - T0)) -ge 9
  test $((SECONDS - T0)) -le 16
  ```
  大约10秒后，关闭操作以4001号结束，而不是立即进行，也不是在25秒的捕获结束时进行。
- **已弃用查询和标头键 (`F02.ws-legacy-key`)。**认证
  with `?session_api_key=` or the header and send a command as the very
  第一帧，然后在命令之前发送带有错误密钥的冗余身份验证帧。

  需求：`tmux`
  ```sh
  control-agent-server ws listen /sockets/bash-events --auth query --send '{"command":"echo qa-f02-query"}' --until-kind BashOutput --duration 20 --save F02.ws-legacy-key/query
  control-agent-server ws listen /sockets/bash-events --auth header --send '{"command":"echo qa-f02-header"}' --until-kind BashOutput --duration 20 --save F02.ws-legacy-key/header
  control-agent-server ws listen /sockets/bash-events --auth query --send '{"type":"auth","session_api_key":"qa-f02-ignored"}' --send '{"command":"echo qa-f02-legacy"}' --until-kind BashOutput --duration 20 --save F02.ws-legacy-key/redundant-frame
  control-agent-server ws listen "/sockets/events/$CID" --auth header --until-kind ConversationStateUpdateEvent --duration 15
  ```
  两种旧式表单在握手时都进行认证：第一个帧发送的命令（如果忽略旧式密钥，该帧会被读作失败的认证帧并关闭，返回4001）。 冗余的认证帧被跳过（其密钥从不检查），命令仍然运行。 服务器日志 `session_api_key passed via query param or header is deprecated`（跨多行显示）。 仅仅保持几秒钟的套接字并不能证明什么：一个未认证的套接字会等待最多10秒来发送其认证帧。
- **错误的旧密钥导致握手失败 (`F02.ws-legacy-reject`)。**错误的查询键，以及错误的查询键后跟正确的第一帧。
  ```sh
  control-agent-server ws listen /sockets/bash-events --auth none --query session_api_key=qa-f02-wrong --expect-reject 403 --duration 5 --save F02.ws-legacy-reject/wrong-query
  control-agent-server ws listen /sockets/bash-events --auth bad-header --expect-reject 403 --duration 5 --save F02.ws-legacy-reject/wrong-header
  control-agent-server ws listen /sockets/bash-events --query session_api_key=qa-f02-stale --send '{"command":"echo qa-f02-stale"}' \
    --expect-reject 403 --expect-frames 0 --duration 5 --save F02.ws-legacy-reject/stale-query-good-frame
  ```
  握手拒绝了 HTTP 403（服务器在接受之前关闭，客户端看到这像一个拒绝的升级，所以没有4001关闭帧，而且一个存在的旧密钥永远不会被正确的第一个帧覆盖）。
- **铸造工作区 cookie (`F02.workspace-session-mint`)。**薄荷有钥匙，没有钥匙，有错误的钥匙，只有cookie，以及被忽略的主体。
  ```sh
  control-agent-server api POST /api/auth/workspace-session --expect 204 --save F02.workspace-session-mint/loopback \
    | jq -e '.response.headers["set-cookie"] | startswith("oh_workspace_session_key=") and contains("HttpOnly") and contains("Max-Age=315360000") and contains("Path=/api/conversations") and contains("SameSite=none") and contains("Secure") and contains("Partitioned")'
  control-agent-server api POST /api/auth/workspace-session --auth none --expect 401 --check detail eq Unauthorized --save F02.workspace-session-mint/no-key \
    | jq -e '.response.headers["set-cookie"] == null'
  control-agent-server api POST /api/auth/workspace-session --auth bad --expect 401 --check detail eq Unauthorized | jq -e '.response.headers["set-cookie"] == null'
  KEY=$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")
  control-agent-server api POST /api/auth/workspace-session --auth none --cookie "oh_workspace_session_key=$KEY" --expect 401 --save F02.workspace-session-mint/cookie-only
  unset KEY
  control-agent-server api POST /api/auth/workspace-session --json '{"ignored": true}' --expect 204
  ```
  cookie值就是会话密钥本身（CLI打印它已脱敏)。 401响应不设置cookie。 该路由位于仅包含cookie的组中，因此，仅携带cookie的跨站请求无法创建或更新它。
- **cookie 单独打开工作区个文件 (`F02.workspace-cookie-access`)。**浏览器流程：mint 到 jar 中，然后加载不带标头的文件，也在重新启动后加载。
  ```sh
  control-agent-server exec --save F02.workspace-cookie-access/mint -- bash "$F02/jar.sh" POST /api/auth/workspace-session key 204 'has:set-cookie: oh_workspace_session_key='
  grep -q oh_workspace_session_key "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f02-cookies.txt"
  control-agent-server exec --save F02.workspace-cookie-access/file-with-cookie -- bash "$F02/jar.sh" GET "/api/conversations/$CID/workspace/qa-f02.html" nokey 200 'has:qa-f02-workspace-file'
  control-agent-server restart
  control-agent-server exec --save F02.workspace-cookie-access/after-restart -- bash "$F02/jar.sh" GET "/api/conversations/$CID/workspace/qa-f02.html" nokey 200 'has:qa-f02-workspace-file'
  control-agent-server api GET "/api/conversations/$CID/workspace/qa-f02.html" --auth none --cookie oh_workspace_session_key=qa-f02-bogus --expect 401 --save F02.workspace-cookie-access/bogus-cookie
  control-agent-server api GET "/api/conversations/$CID/workspace/qa-f02.html" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/workspace/qa-f02.html" --expect 200
  ```
  文件在重启前后加载，只有cookie（cookie是key，所以不会有服务器端会话丢失）。 一个伪造的 cookie 或 None 是 401； 单独的头部也有效。
- **删除工作区cookie (`F02.workspace-session-delete`)。**通过 API 清除它，然后通过罐子。
  ```sh
  control-agent-server api DELETE /api/auth/workspace-session --expect 204 --save F02.workspace-session-delete/delete \
    | jq -e '.response.headers["set-cookie"] | startswith("oh_workspace_session_key=\"\"") and contains("Max-Age=0") and contains("Path=/api/conversations") and contains("HttpOnly")'
  control-agent-server api DELETE /api/auth/workspace-session --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server exec --save F02.workspace-session-delete/jar-delete -- bash "$F02/jar.sh" DELETE /api/auth/workspace-session key 204 'has:max-age=0'
  if grep oh_workspace_session_key "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f02-cookies.txt"; then false; fi
  control-agent-server exec --save F02.workspace-session-delete/file-after-delete -- bash "$F02/jar.sh" GET "/api/conversations/$CID/workspace/qa-f02.html" nokey 401
  ```
  清除 cookie 的值为空 `Max-Age=0`，并且相同的路径，因此 jar 会丢弃它，然后下一个文件请求会返回 401。 删除仍然需要头部。
- **第二把钥匙 (`F02.multiple-keys`)。**添加 `OH_SESSION_API_KEYS_1` 和一个空的第三个条目并重新启动。 两个真正的钥匙都可以使用； 空条目无法进行身份验证。

  需求：`tmux`
  ```sh
  control-agent-server restart --env OH_SESSION_API_KEYS_1=qa-f02-second-key --env OH_SESSION_API_KEYS_2=
  control-agent-server api GET /api/conversations/count --auth none --header 'X-Session-API-Key: qa-f02-second-key' --expect 200 --save F02.multiple-keys/second-key
  control-agent-server api GET /api/conversations/count --expect 200
  control-agent-server api GET /api/conversations/count --auth none --header 'X-Session-API-Key: qa-f02-third-key' --expect 401
  control-agent-server api GET /api/conversations/count --auth none --header 'X-Session-API-Key:' --expect 401 --save F02.multiple-keys/empty-key
  control-agent-server ws listen /sockets/bash-events --auth none --send '{"type":"auth","session_api_key":""}' --expect-close 4001 --duration 10 --save F02.multiple-keys/ws-empty-key
  control-agent-server ws listen /sockets/bash-events --auth none --send '{"type":"auth","session_api_key":"qa-f02-second-key"}' --send '{"command":"echo qa-f02-second"}' --until-kind BashOutput --duration 20 --save F02.multiple-keys/ws-second-key
  control-agent-server doctor
  ```
  这两个密钥在 HTTP 和 socket 上都有效。 未列出或空的密钥被拒绝。 已配置的空值被丢弃，如 PR #5659 所述。
- **旋转钥匙 (`F02.rotate-key`)。**使用当前密钥创建一个 cookie，使用新密钥重新启动，然后在各处尝试旧密钥。

  需求：`tmux`
  ```sh
  control-agent-server exec -- bash "$F02/jar.sh" POST /api/auth/workspace-session key 204
  control-agent-server exec -- bash "$F02/jar.sh" GET "/api/conversations/$CID/workspace/qa-f02.html" nokey 200 'has:qa-f02-workspace-file'
  control-agent-server restart --rotate-key
  OLD_KEY=$(cat "$AGENT_SERVER_VERIFY_RUN/private/previous_session_api_key")
  control-agent-server api GET /api/conversations/count --auth previous --expect 401 --save F02.rotate-key/old-key
  control-agent-server ws listen /sockets/bash-events --auth none --send '{"type":"auth","session_api_key":"'"$OLD_KEY"'"}' --expect-close 4001 --duration 10 --save F02.rotate-key/ws-old-key
  unset OLD_KEY
  control-agent-server exec --save F02.rotate-key/old-cookie -- bash "$F02/jar.sh" GET "/api/conversations/$CID/workspace/qa-f02.html" nokey 401
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --check id eq "$CID" --save F02.rotate-key/new-key
  control-agent-server ws listen /sockets/bash-events --send '{"command":"echo qa-f02-rotated"}' --until-kind BashOutput --duration 20
  control-agent-server doctor
  ```
  旧密钥为401 HTTP，socket上为4001，用它生成的cookie（在重启前打开文件的）不再能打开文件，新的密钥读取相同的对话。
  `doctor` 确认轮出密钥被拒绝。
- **按键不受命令影响 (`F02.keys-hidden-from-commands`)。**通过服务器（全局 bash 路由）运行 `env`，并配置两个索引键和一个机密键。

  需求：`tmux`
  ```sh
  KEY=$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")
  SECRET=$(cat "$AGENT_SERVER_VERIFY_RUN/private/secret_key")
  control-agent-server api POST /api/bash/execute_bash_command --json '{"command":"env"}' --expect 200 \
    --check exit_code eq 0 --check stdout contains PATH= \
    --check stdout not-contains OH_SESSION_API_KEYS --check stdout not-contains SESSION_API_KEY \
    --check stdout not-contains OH_SECRET_KEY --check stdout not-contains qa-f02-second-key \
    --check stdout not-contains "$KEY" --check stdout not-contains "$SECRET" --save F02.keys-hidden-from-commands/env
  unset KEY SECRET
  ```
  命令的环境有 None 关键变量或值（运行的当前键，第二个从...） `F02.multiple-keys` 和机密此时，所有密钥都已在服务器进程中设置。
- **默认 CORS 来源 (`F02.cors-default-origins`)。**预检来自本地来源、外国来源和`null`，然后来自外国来源的简单请求。
  ```sh
  control-agent-server exec --save F02.cors-default-origins/localhost -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 200 \
    'has:access-control-allow-origin: http://localhost:3001' 'has:access-control-allow-credentials: true' -- \
    -H 'Origin: http://localhost:3001' -H 'Access-Control-Request-Method: GET' -H 'Access-Control-Request-Headers: x-session-api-key'
  control-agent-server exec -- bash "$F02/jar.sh" OPTIONS /api/settings nokey 200 'has:access-control-allow-origin: http://127.0.0.1:5173' -- \
    -H 'Origin: http://127.0.0.1:5173' -H 'Access-Control-Request-Method: PATCH'
  control-agent-server exec --save F02.cors-default-origins/foreign -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 400 \
    'has:Disallowed CORS origin' 'lacks:access-control-allow-origin' -- -H 'Origin: https://qa-evil.example' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 400 'has:Disallowed CORS origin' -- \
    -H 'Origin: null' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec --save F02.cors-default-origins/simple-foreign -- bash "$F02/jar.sh" GET /api/conversations/count key 200 \
    'lacks:access-control-allow-origin' -- -H 'Origin: https://qa-evil.example'
  ```
  本地来源会被回显为 `access-control-allow-credentials: true`。 一个来自国外的端点，`null` 会返回 400 `Disallowed CORS origin`，GET 从国外返回成功，但没有 `access-control-allow-origin`，所以浏览器会隐藏它。
- **已配置 CORS 来源 (`F02.cors-configured-origins`)。**使用一个确切的来源、一个正则表达式和一个 Docker 主机地址重新启动。
  ```sh
  control-agent-server restart --env OH_ALLOW_CORS_ORIGINS_0=https://qa-canvas.example \
    --env 'OH_ALLOW_CORS_ORIGIN_REGEX=https://[a-z0-9-]+\.qa-regex\.example' --env DOCKER_HOST_ADDR=10.254.0.7
  control-agent-server exec --save F02.cors-configured-origins/exact -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 200 \
    'has:access-control-allow-origin: https://qa-canvas.example' -- -H 'Origin: https://qa-canvas.example' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec --save F02.cors-configured-origins/regex -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 200 \
    'has:access-control-allow-origin: https://app-1.qa-regex.example' -- -H 'Origin: https://app-1.qa-regex.example' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec --save F02.cors-configured-origins/docker-host -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 200 \
    'has:access-control-allow-origin: http://10.254.0.7:3000' -- -H 'Origin: http://10.254.0.7:3000' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec -- bash "$F02/jar.sh" OPTIONS /api/conversations/count nokey 400 'has:Disallowed CORS origin' -- \
    -H 'Origin: https://qa-other.example' -H 'Access-Control-Request-Method: GET'
  ```
  已配置的三个源被回显。 另一个无关的来源仍然返回400。
- **工作区路线接受任何起点 (`F02.cors-workspace-routes`)。** cookie 路由回显任何 http(s) 来源，但不回显 `null`，并且仅在这些路径上。
  ```sh
  control-agent-server exec --save F02.cors-workspace-routes/session -- bash "$F02/jar.sh" OPTIONS /api/auth/workspace-session nokey 200 \
    'has:access-control-allow-origin: https://qa-anywhere.example' 'has:access-control-allow-credentials: true' -- \
    -H 'Origin: https://qa-anywhere.example' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: x-session-api-key'
  control-agent-server exec --save F02.cors-workspace-routes/file -- bash "$F02/jar.sh" OPTIONS "/api/conversations/$CID/workspace/qa-f02.html" nokey 200 \
    'has:access-control-allow-origin: https://qa-anywhere.example' -- -H 'Origin: https://qa-anywhere.example' -H 'Access-Control-Request-Method: GET'
  control-agent-server exec --save F02.cors-workspace-routes/null-origin -- bash "$F02/jar.sh" OPTIONS /api/auth/workspace-session nokey 400 'has:Disallowed CORS origin' -- \
    -H 'Origin: null' -H 'Access-Control-Request-Method: POST'
  control-agent-server exec --save F02.cors-workspace-routes/not-elsewhere -- bash "$F02/jar.sh" OPTIONS "/api/conversations/$CID" nokey 400 'has:Disallowed CORS origin' -- \
    -H 'Origin: https://qa-anywhere.example' -H 'Access-Control-Request-Method: GET'
  ```
  两个 cookie 路由都会返回原始值凭据。 `null` 被拒绝，对话本身也拒绝了相同的来源。
- **未经身份验证模式 (`F02.no-auth-mode`)。**第二台服务器启动
  with `--no-auth`.

  需求：`tmux`
  ```sh
  NOAUTH=$(control-agent-server launch --new --no-auth --name f02-noauth --print-run)
  trap 'control-agent-server stop --run "$NOAUTH" >/dev/null' EXIT
  control-agent-server api GET /api/conversations/count --run "$NOAUTH" --auth none --expect 200 --save F02.no-auth-mode/no-key
  control-agent-server api GET /api/conversations/count --run "$NOAUTH" --auth none --header 'X-Session-API-Key: qa-f02-anything' --expect 200
  control-agent-server ws listen /sockets/bash-events --run "$NOAUTH" --auth none --send '{"command":"echo qa-f02-open"}' --until-kind BashOutput --duration 20 --save F02.no-auth-mode/ws
  control-agent-server api POST /api/auth/workspace-session --run "$NOAUTH" --auth none --expect 204 --save F02.no-auth-mode/mint \
    | jq -e '.response.headers["set-cookie"] | startswith("oh_workspace_session_key=\"\"")'
  control-agent-server api DELETE /api/auth/workspace-session --run "$NOAUTH" --auth none --expect 204
  control-agent-server stop --run "$NOAUTH"
  ```
  一切无需密钥即可回答，任何头信息都被忽略，套接字运行其第一个帧发送的命令，生成的 cookie 为空。 第二次运行的证据位于其自己的运行目录下。
- **旧版 `SESSION_API_KEY` (`F02.legacy-env-key`).**第二个服务器，其唯一键是旧变量。

  需求：`tmux`
  ```sh
  LEGACY=$(control-agent-server launch --new --no-auth --name f02-legacy --env SESSION_API_KEY=qa-f02-legacy-key --print-run)
  trap 'control-agent-server stop --run "$LEGACY" >/dev/null' EXIT
  control-agent-server api GET /api/conversations/count --run "$LEGACY" --auth none --expect 401 --save F02.legacy-env-key/no-key
  control-agent-server api GET /api/conversations/count --run "$LEGACY" --auth none --header 'X-Session-API-Key: qa-f02-legacy-key' --expect 200 --save F02.legacy-env-key/legacy-key
  control-agent-server ws listen /sockets/bash-events --run "$LEGACY" --auth none --send '{"type":"auth","session_api_key":"qa-f02-legacy-key"}' --send '{"command":"echo qa-f02-legacy-ws"}' --until-kind BashOutput --duration 20
  control-agent-server api POST /api/bash/execute_bash_command --run "$LEGACY" --auth none --header 'X-Session-API-Key: qa-f02-legacy-key' \
    --json '{"command":"env"}' --expect 200 --check exit_code eq 0 --check stdout contains PATH= \
    --check stdout not-contains qa-f02-legacy-key --check stdout not-contains SESSION_API_KEY --save F02.legacy-env-key/env
  control-agent-server stop --run "$LEGACY"
  ```
  身份验证遗产密钥启用（401 无此密钥，有此密钥则为 200，且套接字接受此密钥）。 `env` 运行（退出状态码为0，`PATH=` 作为输出的一部分），既不显示变量，也不显示其值。
- ** 默认绑定地址 (`F02.default-bind`).** 开始这个检查点的服务器三次，作为操作员那样，每次都在各自的私有网络中：没有密钥和没有 `--host`，有密钥和没有命名空间
  `--host`，并且没有带有显式 `--host 0.0.0.0` 的键。
  ```sh
  QA_F02_PYTHON="$(jq -r .checkout "$AGENT_SERVER_VERIFY_RUN/run.json")/.venv/bin/python"
  control-agent-server exec --save F02.default-bind/no-key --expect-output 'Starting OpenHands Agent Server on 127.0.0.1:8000' \
    --expect-output 'listening on 127.0.0.1:8000' --reject-output 'Binding to all interfaces' -- \
    unshare -rn env -i PATH="$PATH" QA_F02_PYTHON="$QA_F02_PYTHON" bash "$F02/bind.sh" "$F02/bind-no-key"
  control-agent-server exec --save F02.default-bind/with-key --expect-output 'Starting OpenHands Agent Server on 0.0.0.0:8000' \
    --expect-output 'listening on 0.0.0.0:8000' --reject-output 'Binding to all interfaces' -- \
    unshare -rn env -i PATH="$PATH" QA_F02_PYTHON="$QA_F02_PYTHON" OH_SESSION_API_KEYS_0=qa-f02-bind-key bash "$F02/bind.sh" "$F02/bind-key"
  control-agent-server exec --save F02.default-bind/wildcard-no-key --expect-output 'listening on 0.0.0.0:8000' \
    --expect-output 'Binding to all interfaces (0.0.0.0) without a session API key' -- \
    unshare -rn env -i PATH="$PATH" QA_F02_PYTHON="$QA_F02_PYTHON" bash "$F02/bind.sh" "$F02/bind-wildcard" --host 0.0.0.0
  ```
  没有密钥时，服务器只监听 `127.0.0.1:8000`。 与
  `OH_SESSION_API_KEYS_0` 它监听每个接口 (`0.0.0.0`)，并且都不记录警告。 没有密钥的显式 `--host 0.0.0.0` 会受到尊重（它侦听 `0.0.0.0`）并记录 `Binding to all interfaces (0.0.0.0) without a session API key`。 该地址来自内核的套接字表（`/proc/net/tcp`），而不仅仅是来自启动行。 命名空间使未经身份验证的通配符服务器无法从外部访问，`env -i` 使该 shell 的 `OH_*` 变量远离它。
- **Cookie路径忽略前缀(`F02.workspace-cookie-root-path`),已知bug。**另一个带有`OH_WEB_URL=http://127.0.0.1/qa-f02-prefix`的服务器，通过带有URLs的前缀路径代理的方式使用，就像浏览器一样。
  ```sh
  PREFIXED=$(control-agent-server launch --new --name f02-prefix --env OH_WEB_URL=http://127.0.0.1/qa-f02-prefix --print-run)
  trap 'control-agent-server stop --run "$PREFIXED" >/dev/null' EXIT
  PCID=$(control-agent-server conversation start --run "$PREFIXED" --no-run --tools none --no-autotitle --workspace "$F02/workspace" --print-id)
  control-agent-server api GET /openapi.json --run "$PREFIXED" --auth none --max-chars 200 --check servers.0.url eq /qa-f02-prefix
  control-agent-server exec --run "$PREFIXED" -- bash "$F02/jar.sh" GET "/qa-f02-prefix/api/conversations/$PCID/workspace/qa-f02.html" key 200 'has:qa-f02-workspace-file'
  control-agent-server exec --run "$PREFIXED" --save F02.workspace-cookie-root-path/mint -- bash "$F02/jar.sh" POST /qa-f02-prefix/api/auth/workspace-session key 204
  grep -q oh_workspace_session_key "$PREFIXED/fixtures/qa-f02-cookies.txt"
  control-agent-server exec --run "$PREFIXED" -- bash "$F02/jar.sh" GET "/api/conversations/$PCID/workspace/qa-f02.html" nokey 200 'has:qa-f02-workspace-file'
  control-agent-server exec --run "$PREFIXED" --save F02.workspace-cookie-root-path/file-with-cookie -- bash "$F02/jar.sh" GET "/qa-f02-prefix/api/conversations/$PCID/workspace/qa-f02.html" nokey 200 'has:qa-f02-workspace-file'  # bug: exit_code eq 1 && stdout_tail 包含 status=401
  control-agent-server stop --run "$PREFIXED"
  ```
  服务器声明 `servers: [{"url": "/qa-f02-prefix"}]` 并在前缀下提供文件。 被铸造的饼干落在了第二个运行的容器中，并且是一个有效的凭据（未前缀的 URL，一个前缀剥离代理会转发，加载文件并将其加载）。 预期： cookie 也应出现在预缀文件 URL 中，即浏览器实际使用的那个。 今天，无论根路径如何，它都被限制在`Path=/api/conversations`，不像`CORSDispatcher`，它会去除`root_path`，所以jar不发送它，文件是401。 bTypeScript客户端
  `startWorkspaceSession()` 返回 `${host}/api/conversations/{id}/workspace/`该前缀总是与之一起携带 `host` 所做的。
- **IPv6 环回是安全的上下文 (`F02.workspace-session-ipv6-loopback`)。** Mint 作为 IPv4 环回名称的浏览器，然后作为浏览器
  `http://[::1]:PORT` 会。
  ```sh
  control-agent-server api POST /api/auth/workspace-session --header 'Host: 127.0.0.1:8000' --expect 204 \
    --check-header set-cookie contains SameSite=none --check-header set-cookie contains Secure --check-header set-cookie contains Partitioned
  control-agent-server api POST /api/auth/workspace-session --header 'Host: localhost:8000' --expect 204 \
    --check-header set-cookie contains Secure --check-header set-cookie contains Partitioned
  control-agent-server api POST /api/auth/workspace-session --header 'Host: [::1]:8000' --expect 204 --save F02.workspace-session-ipv6-loopback/ipv6-host \
    --check-header set-cookie contains SameSite=none --check-header set-cookie contains Secure --check-header set-cookie contains Partitioned
  ```
  `127.0.0.1`、`localhost` 和 `Host: [::1]:8000` 铸币厂都得到
  `SameSite=none; Secure; Partitioned`，由于 `::1` 在服务器的环回列表中，因此工作区嵌入了客户端的工作
  `http://[::1]:PORT`. `request.url.hostname` 返回不带括号的 IPv6 地址 (`::1`)，因此 `_request_is_secure_context` 仅从带括号的主机或带有单个冒号的主机中删除 `:port` 后缀。

<a id="gotchas"></a>

## 陷阱

- cookie 值是会话密钥本身（HttpOnly，十年
  `Max-Age`). 没有服务器端会话：`DELETE` 只告诉浏览器丢弃它，复制的 cookie 在密钥旋转后仍然有效，而旋转密钥会一次 invalidate 所有 cookie。
- `Path=/api/conversations` 使浏览器将 cookie 发送到每个会话路由，而不仅仅是工作区个文件； 服务器在那里忽略它（`F02.http-header-only`）。 保持这种方式：遵守它将会打开通往 CSRF 的路线。
- 在接受 WebSocket 之前，错误的旧密钥（查询或标头）会被拒绝，因此客户端会看到 HTTP 403 握手失败，而不是 4001 关闭。 `ws listen`记为`close.http_status`； 断言它与
  `--expect-reject 403`（`--expect-close 4001` 失败）。
- 第一帧认证没有确认帧，且有10秒的超时：连接并等待其他事物的客户端会被关闭，返回4001。 证明套接字通过其后发送的帧进行身份验证。
- bash 套接字将任何后面的 `{"type": "auth", ...}` 帧视为无操作，无论其键是什么； 其他帧必须是`ExecuteBashRequest` JSON。
- CORS 预检在路由和身份验证之前由中间件应答，因此
  `OPTIONS` 请求永远不会得到 401。 没有 `Origin` 和
  `Access-Control-Request-Method` 它到达路由并得到 405。 `curl` 帮助程序为这些和 cookie 扮演一个独立的浏览器（路径匹配，`Max-Age=0` 删除）； `api OPTIONS`、`--check-header` 和
  `--jar` 达到 CLI 内的相同情况。
- 从命令环境中剥离关键变量是深度防御：命令以服务器用户身份运行并且可以读取 `/proc/<server pid>/environ`。
- `restart --env` 值持久化用于稍后重新启动同一运行； 该族在运行时留下 `OH_SESSION_API_KEYS_1` 和 CORS 变量。
- 配置了密钥并且没有`--host`，服务器绑定`0.0.0.0`； 没有钥匙，`127.0.0.1` (`F02.default-bind`)。 启动器总是通过
  `--host 127.0.0.1`，因此只有 `F02.default-bind` 看到默认值。
