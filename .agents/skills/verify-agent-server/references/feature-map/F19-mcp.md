<a id="mcp-server-settings-connection-test-and-oauth"></a>

# MCP 服务器设置、连接测试和 OAuth

消费者如何添加  MCP 其服务器智能体它存储一个服务器已持久化设置（`agent_settings.mcp_config` 无需重新发送目录，通过客户端选择的名称来验证候选者，可以先通过连接测试来验证它，该测试会启动或连接到它，列出其工具， 甚至可以调用一个，对于 OAuth 保护的服务器，还会运行一个浏览器协调的同意作业，该作业的结果是  token 状态被保存回服务器端 `auth.state`. 凭据 (`env`, `headers`, `auth` 值和OAuth token) are 已脱敏在响应中，数据先在磁盘上加密，然后在连接之前解密。 从这些设置开始的对话连接到所有启用的服务器，并暴露其工具给它们智能体; 禁用的服务器会保留存储，但永远不会生成。 当会话刷新过期的 OAuth 时 token, 旋转的 token 被写回存储在服务器上的，或者，对于通过 inline 传递给服务器的智能体已发布到应用服务器的 Webhook.

资料来源：`openhands-agent-server/openhands/agent_server/mcp_router.py`、`openhands-agent-server/openhands/agent_server/mcp_oauth_store.py`、`openhands-agent-server/openhands/agent_server/settings_router.py`、`openhands-agent-server/openhands/agent_server/_secrets_exposure.py`、`openhands-sdk/openhands/sdk/mcp/`、`openhands-sdk/openhands/sdk/settings/api_models.py`、`openhands-sdk/openhands/sdk/utils/redact.py`、`openhands-sdk/openhands/sdk/workspace/remote/base.py`、`clients/typescript/src/client/mcp-client.ts`、`clients/typescript/src/client/settings-client.ts`

需求：`llm`

发射：`--webhook-sink`

Routes: `POST /api/mcp/test`, `POST /api/mcp/oauth/start`,
`GET /api/mcp/oauth/status/{job_id}`, `POST /api/mcp/oauth/callback/{job_id}`,
`POST /api/settings/mcp/{settings_key}`, `PATCH /api/settings/mcp/{settings_key}`,
`DELETE /api/settings/mcp/{settings_key}`

<a id="sub-features"></a>

## 子功能

- `F19.auth`：每个 F19 路由都会在没有或有错误会话密钥的情况下回答 401，并且不存储或生成任何内容。
- `F19.settings-create`: `POST /api/settings/mcp/{settings_key}` 保存了一个服务器（201，整个已脱敏 `SettingsResponse`），`GET /api/settings` 显示它已脱敏，`X-Expose-Secrets: plaintext` 返回凭据，硬盘上的文件已经加密了它们，创建一个现有的密钥是 409，不改变它。
- `F19.settings-validation`创建一个无 stdio 服务器 `command`一个没有远程服务器的 `url`, 一个未知字段或传输层，或 `auth` 在...旁边 `Authorization` header值为422，存储了空值。
- `F19.settings-empty-server`：既没有 `command` 也没有 `url` (`{}`) 的服务器主体会被拒绝并返回 422，而不是被存储。
- `F19.settings-patch`: `PATCH` 稀疏合并（`enabled: false` 保留 url 和标头，`null` 标头条目仅删除该条目，`enabled: null` 恢复 `true`）； 未知密钥为 404，未知字段或离开 HTTP 服务器而没有 `url` 的合并为 422。
- `F19.settings-delete`：`DELETE`删除一台服务器，并保持其他服务器及其凭据完好无损； 删除丢失的密钥是 404。
- `F19.test-stdio`: `POST /api/mcp/test` 生成一个 stdio 服务器，列出其工具，运行请求的 `tool_call` 并返回其文本，并且没有 stdio 子级在响应中幸存。
- `F19.test-tool-errors`：引发的工具、未公布的工具名称和比超时寿命更长的工具在 `tool_result` 中报告为 `is_error: true`，而 `ok` 保留为 `true`。
- `F19.test-connect-failures`：缺少可执行文件、关闭的端口和立即退出的命令，用 `ok: false`、`error` 和 `error_kind` 回答 200。
- `F19.test-timeout`：从未完成握手的 stdio 服务器产生接近请求的 `timeout` 的 `ok: false`、`error_kind: timeout`，并且其进程被终止。
- `F19.test-validation`：丢失的服务器、空命令、未知的传输层、外部的 `timeout`（0、120]、`Authorization` 标头旁边的顶级 `authentication` 和 `auth` 为 422。
- `F19.test-encrypted-env`：由设置API加密的`env`值在stdio服务器启动之前解密，并且子进程不会继承Agent Server自己的密钥。
- `F19.test-remote-bearer`：持有者令牌后面的可流式HTTP服务器与`auth.strategy: bearer`、`Authorization`标头（也作为`type: shttp`）或`auth.strategy: header`连接，以及错误的token答案`ok: false`。
- `F19.oauth-start-errors`：对于 stdio 或非 oauth2 服务器，OAuth 启动为 400，对于无法访问的服务器报告 `ok: false` 作业失败（其回调则为 409），对于不需要 OAuth 的服务器，在未经同意的情况下完成。
- `F19.oauth-unknown-job`：未知作业 ID 的状态和回调为 404，没有 `callback_url` 的回调为 422。
- `F19.oauth-flow`与本地受保护的OAuth认证对抗 MCP 服务器启动返回一个 `authorization_url`状态报告 `authorizing` 和 `callback_ready`, 并提交浏览器的重定向 URL 用工具、工具结果和加密的 `oauth_state`.
- `F19.oauth-callback-replay`：作业完成后再次提交回调，回答 200 作业状态，而不是 500，并且作业保持 `succeeded`。
- `F19.oauth-callback-bad-port`：端口在 0-65535 之外的回调 URL 被拒绝为 400，而不是 500。
- `F19.oauth-callback-validation`：在实时作业中，HTTPSURL、外部主机、另一个端口或另一个路径为 400，并且作业一直等待； 使用 `127.0.0.1` 而不是 `localhost` 的重定向 URL 完成了它。
- `F19.oauth-consent-denied`：提交当用户拒绝同意 (`error=access_denied`) 时提供商发送的重定向，回答 `ok: false` 并在没有 token 的情况下使作业失败。
- `F19.oauth-consent-timeout`：未在作业 `timeout` 内完成的同意会导致作业失败并显示 `error_kind: timeout`。
- `F19.oauth-inline-writeback`在对话中的 inline OAuth 服务器智能体 (不在设置中)的访问令牌当会话连接时，过期的会话会被刷新，工具保持不变，旋转后的密钥也会保持不变 token 与运行会话密钥一起发布的 Webhook's `/mcp-oauth-state`不在设置中存储。
- `F19.oauth-stored-state` 返回的 `oauth_state` 未经同意就被 `auth.state` 使用，连接时没有 `authorization_url`，存储在设置路由中，已脱敏加密后存储在磁盘上，解密后为 token。
- `F19.disabled-server` 从设置开始的对话会暴露已启用服务器的工具（包括其存储的 token OAuth 服务器），但不会暴露或启动一个已禁用的服务器。
- `F19.conversation-tool`：模型驱动的对话调用配置的 stdio 服务器的 `qa_echo` 工具，`ObservationEvent` (REST 和 WebSocket) 传递 `QA_MCP_ECHO:hi`，删除对话会停止 stdio 子进程。
- `F19.oauth-refresh-writeback`：当存储在服务器上的访问令牌过期时，下一个对话会刷新它，保留服务器的工具，并将旋转的token和新的过期时间写回设置（加密存储在磁盘上）而不将其发布到Webhook。
- `F19.conversation-secrets-at-rest`: 从设置开始的对话会保留智能体's MCP 凭据 (一个禁用服务器的 `env`，OAuth token) 加密的，而对话目录或服务器日志中没有 MCP 凭据这个家庭使用的。
- `F19.restart`：存储的 MCP 服务器及其凭据在重新启动后仍然存在（明文 GET 和 SDK 的 `RemoteWorkspace.get_mcp_config()`），而内存中的 OAuth 作业消失了 (404)。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，设置：`POST|PATCH|DELETE /api/settings/mcp/{settings_key}`（每次调用一台服务器，每次返回整个已脱敏 `SettingsResponse`），用 `GET /api/settings` 读回（`X-Expose-Secrets: plaintext|encrypted` 代表凭据）。 `PATCH /api/settings` 和 `agent_settings_diff.mcp_config` 是批量替代方案（设置系列）。 这里的所有食谱都使用每服务器路由。
- 保存前的 REST、验证：`POST /api/mcp/test`（接受原生形状 `{"command"|"url", "transport"}` 或旧形状 `type`：
  `stdio|http|shttp|streamable-http|sse`); 从不存储任何东西。
- REST，OAuth 安装：`POST /api/mcp/oauth/start`（与测试相同的主体，带有
  `server.auth.strategy: oauth2`), `GET /api/mcp/oauth/status/{job_id}`,
  `POST /api/mcp/oauth/callback/{job_id}` 通过重定向 URL 浏览器登陆。 然后客户端将`oauth_state`保存在服务器的
  `auth.state`通过设置路线。
- 对话：`POST /api/conversations` 与 `agent_settings` 来自
  `GET /api/settings`（`conversation start`和Agent Canvas做什么）携带
  `mcp_config`; 当智能体初始化（在第一条消息上、排队或运行）时，服务器会连接到已启用的服务器，并在第一个 `SystemPromptEvent` 中列出 MCP 工具。
- token 在对话期间刷新（无路由）：服务器的 MCP 工具提供者从存储的 `auth.state` 中提供 FastMCP's OAuth 客户端，并将刷新后的 token 写入设置中。 对于嵌入在智能体中的OAuth服务器，它会将它们保留在内存中，并POSTs
  `{"server_url", "oauth_state"}` 和 `X-Session-API-Key` 到每个配置的 Webhook 的 `<base_url>/mcp-oauth-state`，因此应用程序服务器可以持久化它们（由 `launch --webhook-sink` 和 `sink read` 驱动）。
- SDK: `RemoteWorkspace.get_mcp_config()` 读取存储的服务器（明文） 凭据 (已执行) `F19.restart` 通过 `exec`).
- TypeScript 客户端：`MCPClient.testServer`、`startOAuth`、`getOAuthStatus`、
  `submitOAuthCallback`（版本门控为 `mcp-test` 1.23.0 和 `mcp-oauth` 1.31.0）和 `SettingsClient.createMcpServer`、`patchMcpServer`、
  `deleteMcpServer`. 没有开车来这里； REST 食谱涵盖了相同的调用。
- Agent Canvas（仅限上下文）：“添加 MCP 服务器”对话框测试、运行 OAuth 弹出窗口并通过这些路由保存服务器。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用记录 Webhook 接收器启动的运行（`launch --new --webhook-sink`，家庭的 `Launch:` 标志； 仅 `F19.oauth-inline-writeback` 和
  `F19.oauth-refresh-writeback` 读取），`doctor` 确定，`$DEEPSEEK_API_KEY` 设置（仅 `F19.conversation-tool` 使用该模型），以及 `PATH` 上的 `jq`、`curl` 和 `pgrep`。
- CLI 的 stdio 测试夹具（`fixture mcp-server`、工具 `qa_echo`）加上下面写的三个本地配方测试夹具（它们不存在 CLI 动词）：具有 `qa_env`、`qa_sleep` 和 `qa_fail` 的 stdio 服务器，其第一个参数延迟 MCP 握手，具有三种模式的 HTTP FastMCP 服务器（`none`、`bearer` 具有静态 token `qa-f19-bearer`，`oauth` 具有FastMCP 的
  `InMemoryOAuthProvider`，批准每个授权请求）和一个 SDK 程序。 三个 HTTP 服务器在空闲端口上作为 `helper` 运行，因此它们的寿命比启动它们的先决条件项目符号长； 每个人都会在运行的 `/alive` 停止应答后 25 分钟或 60 秒后退出，最后一颗子弹停止它们，并且 `stop` 结束剩余的任何运行。
  ```sh
  control-agent-server llm preset deepseek
  MCP=$(control-agent-server fixture mcp-server --name qa-f19 | jq -c .mcp_server)
  MCP_CMDLINE=$(echo "$MCP" | jq -r '[.command] + .args | join(" ")')
  PY=$(echo "$MCP" | jq -r .command)
  test -x "$PY"
  F19=$AGENT_SERVER_VERIFY_RUN/fixtures/f19
  mkdir -p "$F19"
  cat > "$F19/qa_f19_tools.py" <<'EOF'
  """F19 stdio MCP fixture; argv[1] delays the MCP handshake by that many seconds."""
  import os
  import sys
  import time

  from mcp.server.fastmcp import FastMCP

  if len(sys.argv) > 1:
      time.sleep(float(sys.argv[1]))

  mcp = FastMCP("qa-f19-tools")


  @mcp.tool()
  def qa_env(name: str) -> str:
      """Return one environment variable of this MCP server process."""
      return "QA_ENV:" + os.environ.get(name, "<unset>")


  @mcp.tool()
  def qa_sleep(seconds: float) -> str:
      """Sleep, then answer."""
      time.sleep(seconds)
      return "QA_SLEPT"


  @mcp.tool()
  def qa_fail() -> str:
      """Always fail."""
      raise ValueError("QA_MCP_FAIL")


  if __name__ == "__main__":
      mcp.run()
  EOF
  cat > "$F19/qa_f19_http.py" <<'EOF'
  """F19 HTTP MCP fixture: argv = port, mode (none|bearer|oauth), ttl seconds, run /alive URL."""
  import os
  import sys
  import threading
  import time
  import urllib.request

  from fastmcp import FastMCP

  port, mode, ttl, alive_url = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), sys.argv[4]
  auth = None
  if mode == "bearer":
      from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

      auth = StaticTokenVerifier(tokens={"qa-f19-bearer": {"client_id": "qa", "scopes": []}})
  elif mode == "oauth":
      from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
      from mcp.server.auth.settings import ClientRegistrationOptions

      auth = InMemoryOAuthProvider(
          base_url=f"http://127.0.0.1:{port}",
          client_registration_options=ClientRegistrationOptions(
              enabled=True, valid_scopes=["mail.read"], default_scopes=["mail.read"]
          ),
          required_scopes=["mail.read"],
      )
  mcp = FastMCP("qa-f19-http", auth=auth)


  @mcp.tool()
  def read_subject(subject: str) -> str:
      """Return a marked subject line."""
      return f"QA_HTTP_SUBJECT:{subject}"


  def watchdog() -> None:
      opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
      started = last_ok = time.monotonic()
      while True:
          time.sleep(2)
          now = time.monotonic()
          try:
              opener.open(alive_url, timeout=2)
              last_ok = now
          except Exception:
              pass
          if now - started > ttl or now - last_ok > 60:
              os._exit(0)


  threading.Thread(target=watchdog, daemon=True).start()
  mcp.run(transport="http", host="127.0.0.1", port=port, path="/mcp", show_banner=False)
  EOF
  cat > "$F19/sdk_mcp_config.py" <<'EOF'
  import os

  from openhands.sdk.workspace import RemoteWorkspace

  ws = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=os.environ["AGENT_SERVER_VERIFY_RUN"],
  )
  cfg = ws.get_mcp_config()
  print("SDK_MCP_KEYS=" + ",".join(sorted(cfg)))
  server = cfg["qa-env"]
  token = (server.env or {})["QA_F19_TOKEN"].get_secret_value()
  print("SDK_MCP_ENV_OK=" + str(token == "qa-f19-env-secret" and server.enabled is False))
  EOF
  TOOLS_SRV=$(jq -nc --arg py "$PY" --arg s "$F19/qa_f19_tools.py" '{command: $py, args: [$s]}')
  RUN_URL=$(control-agent-server config | jq -r .url)
  free_port() { "$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }
  BEARER_PORT=$(free_port)
  OAUTH_PORT=$(free_port)
  NONE_PORT=$(free_port)
  DEAD_PORT=$(free_port)
  control-agent-server helper start --name qa-f19-http-bearer --log "$F19/http-bearer.log" \
    -- "$PY" "$F19/qa_f19_http.py" "$BEARER_PORT" bearer 1500 "$RUN_URL/alive" >/dev/null
  control-agent-server helper start --name qa-f19-http-oauth --log "$F19/http-oauth.log" \
    -- "$PY" "$F19/qa_f19_http.py" "$OAUTH_PORT" oauth 1500 "$RUN_URL/alive" >/dev/null
  control-agent-server helper start --name qa-f19-http-none --log "$F19/http-none.log" \
    -- "$PY" "$F19/qa_f19_http.py" "$NONE_PORT" none 1500 "$RUN_URL/alive" >/dev/null
  for port in "$BEARER_PORT" "$OAUTH_PORT" "$NONE_PORT"; do
    for i in $(seq 1 80); do curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$port/mcp" && break; sleep 0.25; done
  done
  test "$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$BEARER_PORT/mcp")" = 401
  test "$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$OAUTH_PORT/mcp")" = 401
  test "$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' "http://127.0.0.1:$NONE_PORT/mcp")" != 000
  OAUTH_SRV=$(jq -nc --arg url "http://127.0.0.1:$OAUTH_PORT/mcp" '{type: "http", url: $url, auth: {strategy: "oauth2", authentication: {type: "oauth", client_auth_method: "none", scopes: ["mail.read"]}}}')
  ```

- **授权 (`F19.auth`).**每条路线都没有钥匙，或者钥匙错误。
  ```sh
  control-agent-server api POST /api/mcp/test --auth none --json '{"server":{"command":"/bin/true"}}' --expect 401
  control-agent-server api POST /api/mcp/oauth/start --auth bad --json '{"server":{"command":"/bin/true"}}' --expect 401
  control-agent-server api GET /api/mcp/oauth/status/qa-f19-nope --auth none --expect 401
  control-agent-server api POST /api/mcp/oauth/callback/qa-f19-nope --auth none --json '{"callback_url":"http://localhost:1/callback"}' --expect 401
  control-agent-server api POST /api/settings/mcp/qa-f19-auth --auth none --json '{"command":"/bin/true"}' --expect 401
  control-agent-server api PATCH /api/settings/mcp/qa-f19-auth --auth bad --json '{"enabled":false}' --expect 401
  control-agent-server api DELETE /api/settings/mcp/qa-f19-auth --auth none --expect 401
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-f19-auth missing --save F19.auth/settings-after
  ```
  所有七个答案都返回401，没有存储名为`qa-f19-auth`的任何东西。
- **创建一台服务器 (`F19.settings-create`)。**具有两个标头凭据的远程服务器，然后又是相同的密钥。
  ```sh
  control-agent-server api POST /api/settings/mcp/qa-remote --expect 201 \
    --json '{"transport":"http","url":"https://example.invalid/mcp","headers":{"Authorization":"Bearer qa-f19-t0k","X-QA":"qa-f19-x"},"description":"QA remote"}' \
    --check agent_settings.mcp_config.qa-remote.headers.Authorization eq '**********' \
    --check agent_settings.mcp_config.qa-remote.enabled eq true \
    --check agent_settings.schema_version exists --save F19.settings-create/create
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-remote.url eq https://example.invalid/mcp \
    --check agent_settings.mcp_config.qa-remote.headers.X-QA eq '**********' --save F19.settings-create/get-redacted
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' \
    --check agent_settings.mcp_config.qa-remote.headers.Authorization eq 'Bearer qa-f19-t0k' \
    --check agent_settings.mcp_config.qa-remote.headers.X-QA eq qa-f19-x
  control-agent-server state cat home/.openhands/settings.json --not-contains qa-f19-t0k \
    --check agent_settings.mcp_config.qa-remote.headers.Authorization matches '^gAAAA'
  control-agent-server api POST /api/settings/mcp/qa-remote --json '{"transport":"http","url":"https://other.invalid/mcp"}' \
    --expect 409 --check detail eq "MCP server 'qa-remote' already exists" --save F19.settings-create/conflict
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-remote.url eq https://example.invalid/mcp
  ```
  创建操作返回 201 并包含整个设置文档以及两个头部值 `**********`。 GET 明文返回他们，`settings.json` 仅持有 Fernet 加密文本，第二个创建的 url 保持不变。
- **无效服务器 (`F19.settings-validation`)。**
  ```sh
  control-agent-server api POST /api/settings/mcp/qa-bad --json '{"transport":"stdio"}' --expect 422 --check detail.0.msg contains "require 'command'"
  control-agent-server api POST /api/settings/mcp/qa-bad --json '{"transport":"http"}' --expect 422 --check detail.0.msg contains "require 'url'"
  control-agent-server api POST /api/settings/mcp/qa-bad --json '{"url":"https://x.invalid/mcp","bogus":1}' --expect 422 --check detail.0.type eq extra_forbidden
  control-agent-server api POST /api/settings/mcp/qa-bad --json '{"type":"http","url":"https://x.invalid/mcp"}' --expect 422 --check detail.0.type eq extra_forbidden
  control-agent-server api POST /api/settings/mcp/qa-bad --json '{"transport":"websocket","url":"ws://x.invalid"}' --expect 422 --check detail.0.type eq literal_error
  control-agent-server api POST /api/settings/mcp/qa-bad --expect 422 --save F19.settings-validation/auth-and-header \
    --json '{"transport":"http","url":"https://x.invalid/mcp","headers":{"Authorization":"a"},"auth":{"strategy":"bearer","value":"b"}}' \
    --check detail.0.msg contains 'cannot be combined'
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-bad missing
  ```
  每个body都是422（设置路由使用`transport`，而不是测试路由的遗留`type`），`qa-bad`从未出现过。
- **既没有命令也没有 URL 的服务器 (`F19.settings-empty-server`)，已知错误。**
  一旦设置了 `transport`，`MCPServer` 只需要 `command` 或 `url`，因此 `{}` 与 201 一起存储为 `{"enabled": true}`。 在它存在的情况下，MCP 每个新对话的配置都会验证整体失败，并且智能体没有 MCP 实际工具，只有 `MCP server startup failed ... continuing without its tools` 在日志中显示的警告（旁边有一个有效的 stdio 服务器）。 断言的正确行为是 422； 失败时，同一行会删除失败之前存储的条目，因此后面的项目符号不受影响。
  ```sh
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-empty missing
  control-agent-server api POST /api/settings/mcp/qa-empty --json '{}' --expect 422 --save F19.settings-empty-server/create || { control-agent-server api DELETE /api/settings/mcp/qa-empty --expect 200,404 >/dev/null; false; }  # 错误：request.method eq DELETE && 状态 eq 200
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-empty missing
  ```
  今天，POST 返回 201 并且在返回的设置中是 `qa-empty: {"enabled": true}`，然后该条目又被删除了，最后的圆点报告了
  `xfail` 在 `# bug` 行。
- **稀疏补丁 (`F19.settings-patch`).**切换、编辑一个标头、恢复默认值，然后是错误情况。
  ```sh
  control-agent-server api PATCH /api/settings/mcp/qa-remote --json '{"enabled":false}' --expect 200 \
    --check agent_settings.mcp_config.qa-remote.enabled eq false \
    --check agent_settings.mcp_config.qa-remote.url eq https://example.invalid/mcp --save F19.settings-patch/disable
  control-agent-server api PATCH /api/settings/mcp/qa-remote --json '{"headers":{"X-QA":null,"X-New":"qa-f19-new"}}' --expect 200
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' \
    --check agent_settings.mcp_config.qa-remote.headers.Authorization eq 'Bearer qa-f19-t0k' \
    --check agent_settings.mcp_config.qa-remote.headers.X-New eq qa-f19-new \
    --check agent_settings.mcp_config.qa-remote.headers.X-QA missing \
    --check agent_settings.mcp_config.qa-remote.description eq 'QA remote' \
    --check agent_settings.mcp_config.qa-remote.enabled eq false --save F19.settings-patch/get-plaintext
  control-agent-server api PATCH /api/settings/mcp/qa-remote --json '{"enabled":null}' --expect 200 \
    --check agent_settings.mcp_config.qa-remote.enabled eq true
  control-agent-server api PATCH /api/settings/mcp/qa-remote --json '{"url":null}' --expect 422 --check detail eq 'Settings validation failed'
  control-agent-server api PATCH /api/settings/mcp/qa-remote --json '{"bogus":1}' --expect 422 --check detail.0.type eq extra_forbidden
  control-agent-server api PATCH /api/settings/mcp/qa-f19-nope --json '{"enabled":false}' --expect 404 \
    --check detail eq "MCP server 'qa-f19-nope' was not found" --save F19.settings-patch/unknown
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-remote.url eq https://example.invalid/mcp \
    --check agent_settings.mcp_config.qa-remote.enabled eq true \
    --check agent_settings.mcp_config.qa-f19-nope missing --save F19.settings-patch/get-after-errors
  ```
  第一个补丁保留了 url 和 headers。 头部 patch 只删除了 `X-QA`，还添加了 `X-New`，而 `Authorization` 仍然存在。 `enabled: null`带回来
  `true` （也见于最终读取） 三个坏补丁没有改变任何东西，404也没有创造任何东西。
- **删除一台服务器 (`F19.settings-delete`)。**具有 `env` 凭据的同级，然后将两者都删除。
  ```sh
  control-agent-server api POST /api/settings/mcp/qa-sibling --json '{"command":"/bin/true","env":{"QA_F19_SIBLING":"qa-f19-sib"}}' --expect 201
  control-agent-server api DELETE /api/settings/mcp/qa-remote --expect 200 \
    --check agent_settings.mcp_config.qa-remote missing --check agent_settings.mcp_config.qa-sibling exists --save F19.settings-delete/delete
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' \
    --check agent_settings.mcp_config.qa-remote missing \
    --check agent_settings.mcp_config.qa-sibling.env.QA_F19_SIBLING eq qa-f19-sib
  control-agent-server api DELETE /api/settings/mcp/qa-sibling --expect 200 --check agent_settings.mcp_config.qa-sibling missing
  control-agent-server api DELETE /api/settings/mcp/qa-sibling --expect 404 --check detail eq "MCP server 'qa-sibling' was not found"
  ```
  兄弟服务器在其他服务器被删除后仍然保留其解密的`env`值。 同一键的第二次删除返回404。 `mcp_config` 重新空了，这正是对话列表依赖的。
- **连接测试体验证(`F19.test-validation`).**
  ```sh
  control-agent-server api POST /api/mcp/test --json '{}' --expect 422 --check detail.0.loc contains server
  control-agent-server api POST /api/mcp/test --json '{"server":{"transport":"stdio","command":""}}' --expect 422 --check detail.0.type eq string_too_short
  control-agent-server api POST /api/mcp/test --json '{"server":{"transport":"websocket","url":"ws://127.0.0.1:9"}}' --expect 422 --check detail.0.type eq union_tag_invalid
  control-agent-server api POST /api/mcp/test --json '{"server":{"command":"/bin/true"},"timeout":0}' --expect 422 --check detail.0.type eq greater_than
  control-agent-server api POST /api/mcp/test --json '{"server":{"command":"/bin/true"},"timeout":121}' --expect 422 --check detail.0.type eq less_than_equal
  control-agent-server api POST /api/mcp/test --json '{"server":{"url":"http://127.0.0.1:9/mcp","authentication":{"type":"oauth"}}}' --expect 422 \
    --check detail.0.msg contains auth.authentication
  control-agent-server api POST /api/mcp/test --expect 422 --save F19.test-validation/auth-and-header \
    --json '{"server":{"type":"http","url":"http://127.0.0.1:9/mcp","headers":{"Authorization":"Bearer a"},"auth":{"strategy":"bearer","value":"b"}}}' \
    --check detail.0.msg contains 'cannot be combined'
  ```
  所有七人都在任何东西被 spawn 或者接触之前是 422。
- **测试 stdio 服务器 (`F19.test-stdio`)。**列出，然后列出并调用
  `qa_echo`，然后寻找幸存的孩子。
  ```sh
  control-agent-server api POST /api/mcp/test --json "$(jq -nc --argjson s "$MCP" '{name: "qa-f19", server: $s, timeout: 30}')" \
    --expect 200 --check ok eq true --check tools contains qa_echo --check tool_result missing --save F19.test-stdio/list
  control-agent-server api POST /api/mcp/test --expect 200 --save F19.test-stdio/tool-call \
    --json "$(jq -nc --argjson s "$MCP" '{name: "qa-f19", server: ($s + {type: "stdio"}), timeout: 30, tool_call: {name: "qa_echo", arguments: {text: "hi"}}}')" \
    --check ok eq true --check tool_result.is_error eq false --check tool_result.text eq QA_MCP_ECHO:hi
  if pgrep -fx "$MCP_CMDLINE"; then echo 'a stdio MCP child survived the test' >&2; false; fi
  ```
  都用`tools: ["qa_echo"]`回答`ok: true`； 第二个（明确的）
  `type: stdio`) 返回 `QA_MCP_ECHO:hi`，并且没有留下具有测试夹具命令行的进程。
- **工具故障保留在 `tool_result` (`F19.test-tool-errors`) 中。**
  ```sh
  control-agent-server api POST /api/mcp/test --json "$(jq -nc --argjson s "$TOOLS_SRV" '{server: $s, timeout: 30, tool_call: {name: "qa_fail"}}')" \
    --expect 200 --check ok eq true --check tool_result.is_error eq true --check tool_result.text contains QA_MCP_FAIL --save F19.test-tool-errors/raises
  control-agent-server api POST /api/mcp/test --json "$(jq -nc --argjson s "$TOOLS_SRV" '{server: $s, timeout: 30, tool_call: {name: "qa_nope"}}')" \
    --expect 200 --check ok eq true --check tool_result.is_error eq true --check tool_result.text contains 'not advertised by server'
  control-agent-server api POST /api/mcp/test --timeout 20 --expect-max-ms 15000 --save F19.test-tool-errors/slow-tool \
    --json "$(jq -nc --argjson s "$TOOLS_SRV" '{server: $s, timeout: 3, tool_call: {name: "qa_sleep", arguments: {seconds: 30}}}')" \
    --expect 200 --check ok eq true --check tool_result.is_error eq true --check tool_result.text contains 'timed out after 3.0 seconds'
  ```
  `ok` 在所有三个中都保持 `true`，因为服务器已连接并列出； 慢速调用在请求的`timeout`处被切断（整个请求大约需要6秒； `--expect-max-ms` 如果 30 秒睡眠时间耗尽则失败）。
- **连接失败 (`F19.test-connect-failures`)。**始终 HTTP 200。
  ```sh
  control-agent-server api POST /api/mcp/test --json '{"name":"qa-bad","server":{"command":"/nonexistent/qa-f19-bin"},"timeout":10}' --expect 200 \
    --check ok eq false --check error_kind eq connection --check error contains 'No such file' --save F19.test-connect-failures/bad-command
  control-agent-server api POST /api/mcp/test --json "{\"server\":{\"type\":\"http\",\"url\":\"http://127.0.0.1:$DEAD_PORT/mcp\"},\"timeout\":5}" --expect 200 \
    --check ok eq false --check error_kind eq connection --save F19.test-connect-failures/closed-port
  control-agent-server api POST /api/mcp/test --json '{"server":{"command":"/bin/false"},"timeout":10}' --expect 200 \
    --check ok eq false --check error exists --check error_kind exists
  ```
  缺少的可执行文件和关闭的端口 `error_kind: connection`; 立即退出的命令 `ok: false` (today) `error_kind: unknown`,
  `McpError: Connection closed`).
- **握手超时 (`F19.test-timeout`).**工具测试夹具在说话 MCP 之前休眠 60 秒； 请求允许 3.
  ```sh
  SLOW_BODY=$(jq -nc --arg py "$PY" --arg s "$F19/qa_f19_tools.py" '{name: "qa-slow", server: {command: $py, args: [$s, "60"]}, timeout: 3}')
  T0=$SECONDS
  control-agent-server api POST /api/mcp/test --timeout 20 --expect 200 --expect-max-ms 12000 --save F19.test-timeout/slow-start --json "$SLOW_BODY" \
    --check ok eq false --check error_kind eq timeout --check error contains 'timed out after 3.0 seconds' &
  SLOW_REQ=$!
  for i in $(seq 1 40); do pgrep -fx "$PY $F19/qa_f19_tools.py 60" >/dev/null && break; sleep 0.1; done
  pgrep -fx "$PY $F19/qa_f19_tools.py 60"
  wait "$SLOW_REQ"
  test $((SECONDS - T0)) -ge 3
  if pgrep -fx "$PY $F19/qa_f19_tools.py 60"; then echo 'the slow stdio child survived the timeout' >&2; false; fi
  ```
  在请求进行中，睡着的孩子仍然存在（所以最终的）
  `pgrep`可以看到）； 答案在至少 3 秒且不到 12 秒（大约 5 秒）后到达 `error_kind: timeout`，然后孩子就消失了。
- **设置中的加密环境 (`F19.test-encrypted-env`)。**使用 `env` 凭据存储服务器，按照 Agent Canvas 的方式获取其密文 (`X-Expose-Secrets: encrypted`) 并用它进行测试。
  ```sh
  control-agent-server api POST /api/settings/mcp/qa-env --expect 201 \
    --json "$(jq -nc --argjson s "$TOOLS_SRV" '$s + {env: {QA_F19_TOKEN: "qa-f19-env-secret"}}')" \
    --check agent_settings.mcp_config.qa-env.env.QA_F19_TOKEN eq '**********'
  ENC=$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: encrypted' --field agent_settings.mcp_config.qa-env.env.QA_F19_TOKEN --unsafe-unredacted)
  test "${ENC#gAAAA}" != "$ENC"
  control-agent-server api POST /api/mcp/test --expect 200 --save F19.test-encrypted-env/decrypted \
    --json "$(jq -nc --argjson s "$TOOLS_SRV" --arg enc "$ENC" '{server: ($s + {env: {QA_F19_TOKEN: $enc}}), timeout: 30, tool_call: {name: "qa_env", arguments: {name: "QA_F19_TOKEN"}}}')" \
    --check ok eq true --check tool_result.text eq QA_ENV:qa-f19-env-secret
  control-agent-server api POST /api/mcp/test --expect 200 \
    --json "$(jq -nc --argjson s "$TOOLS_SRV" '{server: $s, timeout: 30, tool_call: {name: "qa_env", arguments: {name: "OH_SECRET_KEY"}}}')" \
    --check tool_result.text eq 'QA_ENV:<unset>'
  ```
  孩子看到解密后的值，而不是密文，并且看不到服务器的`OH_SECRET_KEY`。 `qa-env`为`F19.disabled-server`存储。
- **持有者令牌 (`F19.test-remote-bearer`) 后面的远程服务器。**
  ```sh
  control-agent-server api POST /api/mcp/test --expect 200 --save F19.test-remote-bearer/auth-bearer \
    --json "{\"name\":\"qa-http\",\"server\":{\"type\":\"http\",\"url\":\"http://127.0.0.1:$BEARER_PORT/mcp\",\"auth\":{\"strategy\":\"bearer\",\"value\":\"qa-f19-bearer\"}},\"timeout\":20,\"tool_call\":{\"name\":\"read_subject\",\"arguments\":{\"subject\":\"hi\"}}}" \
    --check ok eq true --check tools contains read_subject --check tool_result.text eq QA_HTTP_SUBJECT:hi
  control-agent-server api POST /api/mcp/test --expect 200 \
    --json "{\"server\":{\"type\":\"shttp\",\"url\":\"http://127.0.0.1:$BEARER_PORT/mcp\",\"headers\":{\"Authorization\":\"Bearer qa-f19-bearer\"}},\"timeout\":20}" \
    --check ok eq true --check tools contains read_subject
  control-agent-server api POST /api/mcp/test --expect 200 \
    --json "{\"server\":{\"transport\":\"http\",\"url\":\"http://127.0.0.1:$BEARER_PORT/mcp\",\"auth\":{\"strategy\":\"header\",\"headers\":{\"Authorization\":\"Bearer qa-f19-bearer\"}}},\"timeout\":20}" \
    --check ok eq true --check tools contains read_subject
  control-agent-server api POST /api/mcp/test --expect 200 --save F19.test-remote-bearer/wrong-token \
    --json "{\"server\":{\"transport\":\"http\",\"url\":\"http://127.0.0.1:$BEARER_PORT/mcp\",\"auth\":{\"strategy\":\"bearer\",\"value\":\"qa-f19-wrong\"}},\"timeout\":20}" \
    --check ok eq false --check error contains 401
  ```
  The right token 工作流程 `auth.strategy: bearer`通过一个简单的头部（带有遗留的） `shttp` and through `auth.strategy: header` （表格 422 为 `auth` plus an `Authorization` header recommends); 错误的答案 `ok: false` 命名 401。
- **OAuth 启动拒绝和早期结果 (`F19.oauth-start-errors`)。**
  ```sh
  control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$MCP" '{server: $s}')" --expect 400 \
    --check detail eq "MCP OAuth start requires auth.strategy='oauth2'" --save F19.oauth-start-errors/stdio
  control-agent-server api POST /api/mcp/oauth/start --expect 400 \
    --json "{\"server\":{\"type\":\"http\",\"url\":\"http://127.0.0.1:$BEARER_PORT/mcp\",\"auth\":{\"strategy\":\"bearer\",\"value\":\"qa-f19-bearer\"}}}"
  JU=$(control-agent-server api POST /api/mcp/oauth/start --expect 200 --save F19.oauth-start-errors/unreachable \
    --json "{\"server\":{\"type\":\"http\",\"url\":\"http://127.0.0.1:$DEAD_PORT/mcp\",\"auth\":{\"strategy\":\"oauth2\"}},\"timeout\":5}" \
    --check ok eq false --check error_kind eq connection --check job_id exists --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JU" --check ok eq false --check status eq failed --check callback_ready eq false
  control-agent-server api POST "/api/mcp/oauth/callback/$JU" --json '{"callback_url":"http://localhost:1/callback?code=x"}' --expect 409 \
    --check detail eq 'OAuth callback is not ready'
  JN=$(control-agent-server api POST /api/mcp/oauth/start --expect 200 --save F19.oauth-start-errors/no-consent-needed \
    --json "{\"server\":{\"type\":\"http\",\"url\":\"http://127.0.0.1:$NONE_PORT/mcp\",\"auth\":{\"strategy\":\"oauth2\"}},\"timeout\":10}" \
    --check ok eq true --check authorization_url missing --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JN" --check status eq succeeded --check tools contains read_subject --check oauth_state missing --until-ok 10
  ```
  标准输入和凭据服务器是400。 无法到达的服务器立即返回 `ok: false` 带有状态为的工作 ID `failed` 和他们的回调 409。 需要无OAuth的服务器一次性完成。 `ok: true`, 一个 job id 和没有 `authorization_url`, then `succeeded` 使用其工具。
- **未知职位 (`F19.oauth-unknown-job`)。**
  ```sh
  control-agent-server api GET /api/mcp/oauth/status/qa-f19-nope --expect 404 --check detail eq 'MCP OAuth job not found' --save F19.oauth-unknown-job/status
  control-agent-server api POST /api/mcp/oauth/callback/qa-f19-nope --json '{"callback_url":"http://127.0.0.1:1/callback"}' --expect 404 \
    --check detail eq 'MCP OAuth job not found'
  control-agent-server api POST /api/mcp/oauth/callback/qa-f19-nope --json '{}' --expect 422
  ```
  两个查找都返回 404（而不是 500）。 在查找之前，身体被验证。
- **完整的 OAuth 同意 (`F19.oauth-flow`).** 该食谱控制浏览器：它请求授权  URL 不遵循重定向并直接传递 `Location` 探针的 `http://localhost:<port>/callback?code=...`) to the 回调 route.
  ```sh
  J=$(control-agent-server api POST /api/mcp/oauth/start --expect 200 --save F19.oauth-flow/start \
    --json "$(jq -nc --argjson s "$OAUTH_SRV" '{name: "qa-oauth", server: $s, timeout: 60, tool_call: {name: "read_subject", arguments: {subject: "hi"}}}')" \
    --check ok eq true --check authorization_url matches "^http://127.0.0.1:$OAUTH_PORT/authorize\\?" --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$J" --check status eq authorizing --check callback_ready eq true --until-ok 20 --save F19.oauth-flow/authorizing
  AUTH_URL=$(control-agent-server api GET "/api/mcp/oauth/status/$J" --field authorization_url)
  CALLBACK=$(curl -s --noproxy '*' -o /dev/null -w '%{redirect_url}' "$AUTH_URL")
  test "${CALLBACK#http://localhost:}" != "$CALLBACK"
  control-agent-server api POST "/api/mcp/oauth/callback/$J" --json "$(jq -nc --arg u "$CALLBACK" '{callback_url: $u}')" --expect 200 --check ok eq true --save F19.oauth-flow/callback
  control-agent-server api GET "/api/mcp/oauth/status/$J" --until-ok 30 --save F19.oauth-flow/succeeded \
    --check status eq succeeded --check tools contains read_subject --check tool_result.text eq QA_HTTP_SUBJECT:hi \
    --check oauth_state.tokens.access_token matches '^gAAAA' --check oauth_state.tokens.refresh_token matches '^gAAAA' \
    --check oauth_state.client_info.client_id exists --check oauth_state.token_expires_at exists
  ```
  启动返回 `/authorize` URL (动态客户端注册已经发生)。 状态变为`authorizing`和`callback_ready: true`。 在回调之后，任务`succeeded`完成，并且结果是`read_subject`
  `QA_HTTP_SUBJECT:hi` 和 Fernet 加密 token（运行有
  `OH_SECRET_KEY`).
- **已重播回调 (`F19.oauth-callback-replay`).**探测完成后，其本地回调服务器将关闭。 第二次提交（或在浏览器已经到达回调之后的提交）不会被转发：路由返回200状态，显示已完成任务的状态。 第一个命令显示作业已完成，第二个命令显示重播，最后一个命令显示作业未更改。

  需要：`F19.oauth-flow`
  ```sh
  control-agent-server api GET "/api/mcp/oauth/status/$J" --check status eq succeeded --check callback_ready eq true
  RBODY=$(jq -nc --arg u "$CALLBACK" '{callback_url: $u}')
  control-agent-server api POST "/api/mcp/oauth/callback/$J" --json "$RBODY" --expect 200 --check status eq succeeded --save F19.oauth-callback-replay/replay
  control-agent-server api GET "/api/mcp/oauth/status/$J" --check status eq succeeded
  ```
  回调任务提交后，如果任务在超时上失败了，也会回答 `failed` 状态。 回调服务器已宕机的请求将返回409 `OAuth callback server is not listening`。
- **端口超出范围 (`F19.oauth-callback-bad-port`)。**
  `_validate_callback_url` 读取 `urlparse(...).port`，这会引发
  `ValueError` 代表 `99999` 或非数字端口； 该路由将其转换为与任何其他不匹配的端口相同的 400。 项目符号使用其自己的正在等待同意的作业，因此仅测试 URL 检查。 在范围内的错误端口是控制端口。
  ```sh
  JB=$(control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$OAUTH_SRV" '{server: $s, timeout: 30}')" \
    --check authorization_url exists --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JB" --check callback_ready eq true --until-ok 20
  control-agent-server api POST "/api/mcp/oauth/callback/$JB" --json '{"callback_url":"http://localhost:1/callback?code=x"}' --expect 400 \
    --check detail eq 'Unexpected OAuth callback URL'
  control-agent-server api POST "/api/mcp/oauth/callback/$JB" --json '{"callback_url":"http://localhost:99999/callback?code=x"}' --expect 400 \
    --check detail eq 'Unexpected OAuth callback URL' --save F19.oauth-callback-bad-port/port-99999
  control-agent-server api POST "/api/mcp/oauth/callback/$JB" --json '{"callback_url":"http://localhost:abc/callback?code=x"}' --expect 400 \
    --check detail eq 'Unexpected OAuth callback URL' --save F19.oauth-callback-bad-port/port-abc
  control-agent-server api GET "/api/mcp/oauth/status/$JB" --check status eq authorizing
  ```
  两个帖子都返回 400 `Unexpected OAuth callback URL`，就像端口 `0` 和任何在范围内的其他端口，都不匹配，工作将继续等待。
- **回调 URL 在一个活的作业上进行检查(`F19.oauth-callback-validation`).** 一个新鲜的作业，四个错误(URLs)，然后是正确的作业(`127.0.0.1`).
  ```sh
  JV=$(control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$OAUTH_SRV" '{server: $s, timeout: 60}')" \
    --check authorization_url exists --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JV" --check callback_ready eq true --until-ok 20
  VCB=$(curl -s --noproxy '*' -o /dev/null -w '%{redirect_url}' "$(control-agent-server api GET "/api/mcp/oauth/status/$JV" --field authorization_url)")
  VPORT=$(echo "$VCB" | sed -E 's#^http://localhost:([0-9]+)/.*#\1#')
  control-agent-server api POST "/api/mcp/oauth/callback/$JV" --json "{\"callback_url\":\"https://localhost:$VPORT/callback?code=x\"}" --expect 400 \
    --check detail eq 'Invalid OAuth callback URL' --save F19.oauth-callback-validation/https
  control-agent-server api POST "/api/mcp/oauth/callback/$JV" --json "{\"callback_url\":\"http://qa-f19.example:$VPORT/callback?code=x\"}" --expect 400 \
    --check detail eq 'Invalid OAuth callback URL'
  control-agent-server api POST "/api/mcp/oauth/callback/$JV" --json "{\"callback_url\":\"http://localhost:$VPORT/qa-other?code=x\"}" --expect 400 \
    --check detail eq 'Unexpected OAuth callback URL'
  control-agent-server api POST "/api/mcp/oauth/callback/$JV" --json '{"callback_url":"http://localhost:1/callback?code=x"}' --expect 400 \
    --check detail eq 'Unexpected OAuth callback URL'
  control-agent-server api GET "/api/mcp/oauth/status/$JV" --check status eq authorizing
  VCB_IP=$(echo "$VCB" | sed 's#//localhost:#//127.0.0.1:#')
  VBODY=$(jq -nc --arg u "$VCB_IP" '{callback_url: $u}')
  control-agent-server api POST "/api/mcp/oauth/callback/$JV" --json "$VBODY" \
    --expect 200 --check ok eq true --save F19.oauth-callback-validation/loopback-ip
  control-agent-server api GET "/api/mcp/oauth/status/$JV" --check status eq succeeded --until-ok 30
  ```
  方案和主机检查回答 `Invalid OAuth callback URL`，端口和路径检查回答 `Unexpected OAuth callback URL`。 None 个端点干扰了等待的任务，而回环 IP 端点完成了它。
- **拒绝同意 (`F19.oauth-consent-denied`)。** 测试夹具的提供者批准一切，因此配方扮演拒绝的提供者：它将探针的回调端口和 `state` 保留在真实重定向中，并用 `error=access_denied` 替换代码，就像用户单击“拒绝”时提供者所做的那样。
  ```sh
  JDN=$(control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$OAUTH_SRV" '{server: $s, timeout: 60}')" \
    --check authorization_url exists --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JDN" --check callback_ready eq true --until-ok 20
  DAU=$(control-agent-server api GET "/api/mcp/oauth/status/$JDN" --field authorization_url)
  DCB=$(curl -s --noproxy '*' -o /dev/null -w '%{redirect_url}' "$DAU")
  DSTATE=$(echo "$DCB" | sed -nE 's#.*[?&]state=([^&]*).*#\1#p')
  test -n "$DSTATE"
  DENY_URL="$(echo "$DCB" | sed 's#?.*##')?error=access_denied&error_description=QA%20denied&state=$DSTATE"
  DENY_BODY=$(jq -nc --arg u "$DENY_URL" '{callback_url: $u}')
  control-agent-server api POST "/api/mcp/oauth/callback/$JDN" --json "$DENY_BODY" --expect 200 --save F19.oauth-consent-denied/callback \
    --check ok eq false --check status eq failed --check error eq 'OAuth callback returned HTTP 400' --check error_kind eq connection
  control-agent-server api GET "/api/mcp/oauth/status/$JDN" --until-ok 15 --save F19.oauth-consent-denied/status \
    --check status eq failed --check ok eq false --check error contains 'Access was denied' --check oauth_state missing --check tools missing
  ```
  回调路由报告探针的回调页面返回了 400。 那么，整个任务就会以 `Client failed to connect: Access was denied by the authorization server.` (`error_kind: connection`) 结束，并且不会持有 token。
- **同意超时 (`F19.oauth-consent-timeout`).** 4秒的工作
  `timeout` 谁的授权 URL 无人访问； 探头自身的计时器正在测试中。
  ```sh
  T0=$SECONDS
  JT=$(control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$OAUTH_SRV" '{server: $s, timeout: 4}')" \
    --check authorization_url exists --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JT" --check status eq authorizing
  control-agent-server api GET "/api/mcp/oauth/status/$JT" --until-ok 30 --save F19.oauth-consent-timeout/failed \
    --check status eq failed --check ok eq false --check error_kind eq timeout --check error contains 'timed out after 4.0 seconds'
  test $((SECONDS - T0)) -ge 4
  test $((SECONDS - T0)) -le 15
  ```
  该任务在 `authorizing` 等待，然后在启动后大约四秒（大约四秒）后，`failed`，`error_kind: timeout`。 用户需要重新开始。
- **内联 OAuth 服务器刷新 (`F19.oauth-inline-writeback`)。**主办的
  案例：应用程序服务器在智能体上内联传递 OAuth 服务器，而不是
  将其存储在这里。 该配方采用获得的token集`F19.oauth-callback-validation`（作业`JV`），将其标记为过期（`token_expires_at: 1`，客户端
  值：提供者仍会接受 token）并开始对话
  使用占位符模型和该服务器，对提示词进行排队而不运行它，因此仅发生 MCP 连接。 设置中尚无具有此 URL 的服务器。

  需要：`F19.oauth-callback-validation`
  ```sh
  ISTATE=$(control-agent-server api GET "/api/mcp/oauth/status/$JV" --check oauth_state.tokens.refresh_token exists --field oauth_state --unsafe-unredacted)
  INLINE=$(jq -nc --argjson s "$OAUTH_SRV" --argjson st "$ISTATE" '$s | .auth.state = ($st | .token_expires_at = 1) | .transport = .type | del(.type)')
  IBODY=$(jq -nc --argjson srv "$INLINE" '{agent_settings: {agent_kind: "openhands", llm: {model: "openai/qa-placeholder", api_key: "qa-placeholder", base_url: "http://127.0.0.1:9/v1", num_retries: 0}, tools: [], mcp_config: {"qa-inline": $srv}}, secrets_encrypted: true}')
  control-agent-server sink read --path /mcp-oauth-state --expect-max 0
  ICID=$(control-agent-server conversation start --body-json "$IBODY" --no-autotitle --prompt 'Say hi' --no-run --print-id)
  control-agent-server api GET "/api/conversations/$ICID/events/search" --query limit=1 --max-chars 300 --until-ok 30 \
    --check items.0.kind eq SystemPromptEvent --check . contains read_subject --save F19.oauth-inline-writeback/system-prompt
  IW=$(control-agent-server sink read --path /mcp-oauth-state --contains "\"server_url\": \"http://127.0.0.1:$OAUTH_PORT/mcp\"" \
    --expect-min 2 --wait 20 --save F19.oauth-inline-writeback/webhook | jq -r .saved)
  jq -e --argjson now "$(date +%s)" '[.requests[] | select(.headers["X-Session-API-Key"] == "<redacted:session-api-key>")
    | .body.oauth_state | select(.tokens.access_token and .tokens.refresh_token and .client_info.client_id) | .token_expires_at] | max > $now' "$IW"
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-inline missing
  control-agent-server api DELETE "/api/conversations/$ICID" --expect 200
  ```
  对话列表 `read_subject`; 的 Webhook 在该路径之前，已空的接收器 `POST /mcp-oauth-state` 对于服务器的 URL, 携带本次会话密钥和一个 `oauth_state` with new token客户端注册和一个未来的过期日期（这两次帖子中的第一次仍然有旧的过期日期） `1.0`; 第二行刷新了。 设置中没有存储任何内容。 posted token 都是明文：应用服务器预期会加密它持久化的数据。
- **存储的 OAuth 状态 (`F19.oauth-stored-state`)。**重用来自的状态
  `F19.oauth-flow` 用于测试、启动和存储的服务器。

  需要：`F19.oauth-flow`
  ```sh
  STATE=$(control-agent-server api GET "/api/mcp/oauth/status/$J" --field oauth_state --unsafe-unredacted)
  OSTATE_SRV=$(jq -nc --argjson s "$OAUTH_SRV" --argjson st "$STATE" '$s | .auth.state = $st')
  control-agent-server api POST /api/mcp/test --expect 200 --save F19.oauth-stored-state/test \
    --json "$(jq -nc --argjson s "$OSTATE_SRV" '{server: $s, timeout: 15, tool_call: {name: "read_subject", arguments: {subject: "again"}}}')" \
    --check ok eq true --check tool_result.text eq QA_HTTP_SUBJECT:again --check oauth_state.tokens.access_token exists
  JS=$(control-agent-server api POST /api/mcp/oauth/start --json "$(jq -nc --argjson s "$OSTATE_SRV" '{server: $s, timeout: 15}')" \
    --expect 200 --check ok eq true --check authorization_url missing --field job_id)
  control-agent-server api GET "/api/mcp/oauth/status/$JS" --check status eq succeeded --check tools contains read_subject --until-ok 10
  control-agent-server api POST /api/settings/mcp/qa-oauth --expect 201 --save F19.oauth-stored-state/settings-create \
    --json "$(jq -nc --argjson s "$OSTATE_SRV" '$s | .transport = .type | del(.type)')" \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token eq '**********' \
    --check agent_settings.mcp_config.qa-oauth.auth.state.client_info.client_id exists
  TOKEN=$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --field agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token --unsafe-unredacted)
  test -n "$TOKEN"
  test "${TOKEN#gAAAA}" = "$TOKEN"
  control-agent-server state cat home/.openhands/settings.json --not-contains "$TOKEN" \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token matches '^gAAAA'
  ```
  测试和启动连接到存储 token without any 授权  URL. 将加密状态不变地发布到设置端点，会存储真实  token (plaintext GET 不是密文) 已脱敏在响应中和加密存储在磁盘上。
- **禁用的服务器保持关闭状态`F19.disabled-server`).** 存储  CLI'stdio 测试夹具，disable `qa-env`查看新对话的工具，无需运行模型：对话从队列中开始提示词 (`--no-run`), 因为智能体，以及它所包含的每一个 MCP 连接在接收到第一个消息时初始化，而不是在创建时。

  需要：`F19.test-encrypted-env`、`F19.oauth-stored-state`
  ```sh
  control-agent-server api POST /api/settings/mcp/qa-f19 --json "$MCP" --expect 201
  control-agent-server api PATCH /api/settings/mcp/qa-env --json '{"enabled":false}' --expect 200 --check agent_settings.mcp_config.qa-env.enabled eq false
  DCID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Say hi' --no-run --print-id)
  control-agent-server api GET "/api/conversations/$DCID" --check execution_status eq idle
  control-agent-server api GET "/api/conversations/$DCID/events/search" --query limit=1 --max-chars 300 --save F19.disabled-server/system-prompt \
    --check items.0.kind eq SystemPromptEvent --check . contains qa_echo --check . contains read_subject --check . not-contains qa_env
  pgrep -fx "$MCP_CMDLINE"
  if pgrep -f "^$PY $F19/qa_f19_tools.py"; then echo 'the disabled server was spawned' >&2; false; fi
  control-agent-server api DELETE "/api/conversations/$DCID" --expect 200
  for i in $(seq 1 20); do pgrep -fx "$MCP_CMDLINE" >/dev/null || break; sleep 0.5; done
  if pgrep -fx "$MCP_CMDLINE"; then echo 'the stdio child outlived its conversation' >&2; false; fi
  ```
  第一个事件列表 `qa-f19_qa_echo` 和 `qa-oauth_read_subject` (两个启用的服务器，因此名称带有服务器前缀)，以及 [nothing]
  `qa-env`; 启用的 stdio 服务器运行，而禁用的 stdio 服务器永远不会启动，并且删除会话会停止子进程。
- **智能体使用 MCP 工具 (`F19.conversation-tool`)。** DeepSeek 回合，在事件套接字上实时捕获。

  需要：`F19.disabled-server`
  ```sh
  CID=$(control-agent-server conversation start --tools none --no-autotitle --no-run --print-id)
  control-agent-server ws start "/sockets/events/$CID" --name f19-live --duration 300
  control-agent-server conversation send "$CID" --text 'Call the MCP tool whose name ends with qa_echo, with text hi. Then finish.' --wait --until finished --timeout 240
  control-agent-server conversation events "$CID" --kinds ObservationEvent --contains QA_MCP_ECHO:hi --expect-kind ObservationEvent --save F19.conversation-tool/observation
  control-agent-server ws stop f19-live --kinds ObservationEvent --contains QA_MCP_ECHO:hi --expect-kind ObservationEvent --expect-min 1 --wait 15 --save F19.conversation-tool/ws-frames
  pgrep -fx "$MCP_CMDLINE"
  control-agent-server api DELETE "/api/conversations/$CID" --expect 200
  for i in $(seq 1 20); do pgrep -fx "$MCP_CMDLINE" >/dev/null || break; sleep 0.5; done
  if pgrep -fx "$MCP_CMDLINE"; then echo 'the stdio child outlived its conversation' >&2; false; fi
  ```
  运行结束，一个 `ObservationEvent` (an) `MCPToolObservation` 为了
  `qa-f19_qa_echo`) 在 REST 事件列表中携带 `QA_MCP_ECHO:hi`，并且作为 WebSocket 帧，stdio 子级在会话期间存在，并在删除后消失。
- **存储的 OAuth token 刷新 (`F19.oauth-refresh-writeback`)。**使用稀疏补丁使存储的 `qa-oauth` token 过期（仅限客户端过期），然后
  let a new conversation connect.

  需要：`F19.oauth-stored-state`、`F19.oauth-inline-writeback`
  ```sh
  N0=$(control-agent-server sink read --path /mcp-oauth-state --expect-min 1 | jq .requests)
  control-agent-server api PATCH /api/settings/mcp/qa-oauth --json '{"auth":{"strategy":"oauth2","state":{"token_expires_at":1}}}' --expect 200 \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token eq '**********'
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --save F19.oauth-refresh-writeback/expired \
    --check agent_settings.mcp_config.qa-oauth.auth.state.token_expires_at eq 1 \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token eq "$TOKEN" \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.refresh_token exists \
    --check agent_settings.mcp_config.qa-oauth.auth.state.client_info.client_id exists
  RCID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Say hi' --no-run --print-id)
  control-agent-server api GET "/api/conversations/$RCID/events/search" --query limit=1 --max-chars 300 --until-ok 30 \
    --check items.0.kind eq SystemPromptEvent --check . contains read_subject
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --until-ok 15 --save F19.oauth-refresh-writeback/refreshed \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token ne "$TOKEN" \
    --check agent_settings.mcp_config.qa-oauth.auth.state.token_expires_at gt "$(date +%s)"
  TOKEN=$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --field agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token --unsafe-unredacted)
  test -n "$TOKEN"
  control-agent-server state cat home/.openhands/settings.json --not-contains "$TOKEN" \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token matches '^gAAAA' \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.refresh_token matches '^gAAAA'
  N1=$(control-agent-server sink read --path /mcp-oauth-state --save F19.oauth-refresh-writeback/webhook | jq .requests)
  test "$N1" -eq "$N0"
  control-agent-server api DELETE "/api/conversations/$RCID" --expect 200
  ```
  该补丁保留了  token 仅更新客户端注册和更改。 对话仍然列出 `read_subject`, 服务器上存储的现在是不同的访问令牌有效期在未来，加密在磁盘上。 的 Webhook 收到没有新内容，因为服务器在设置中。 `TOKEN` 现在命名旋转的 token, which `F19.restart` 读取。
- **凭据 at REST (`F19.conversation-secrets-at-rest`).** 当前设置下的新对话`qa-f19`禁用 `qa-env` 与之 `env`  机密，`qa-oauth` 与之 token），然后搜索服务器写入的所有内容。

  需要：`F19.oauth-refresh-writeback`、`F19.disabled-server`
  ```sh
  SCID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Say hi' --no-run --print-id)
  control-agent-server api GET "/api/conversations/$SCID/events/search" --query limit=1 --max-chars 300 --until-ok 30 \
    --check items.0.kind eq SystemPromptEvent --check . contains read_subject
  control-agent-server state cat base_state.json --conversation "$SCID" --max-chars 300 \
    --check agent.mcp_config.qa-env.enabled eq false \
    --check agent.mcp_config.qa-env.env.QA_F19_TOKEN matches '^gAAAA' \
    --check agent.mcp_config.qa-oauth.auth.state.tokens.access_token matches '^gAAAA' \
    --check agent.mcp_config.qa-oauth.auth.state.tokens.refresh_token matches '^gAAAA'
  test "$(control-agent-server state grep qa-oauth --glob 'server/workspace/conversations/**/*' | jq .matches)" -ge 1
  control-agent-server state grep qa-f19-env-secret --glob 'server/workspace/conversations/**/*' --expect-none
  control-agent-server state grep "$TOKEN" --glob 'server/workspace/conversations/**/*' --expect-none
  control-agent-server state grep qa-f19-env-secret --glob 'home/**/*' --expect-none
  control-agent-server logs --grep 'MCP OAuth authorization URL' --expect-min 1
  control-agent-server logs --grep 'qa-f19-env-secret|qa-f19-t0k|qa-f19-x|qa-f19-sib|qa-f19-bearer|qa-f19-wrong|test_access_token|test_refresh_token' --expect-none
  control-agent-server api DELETE "/api/conversations/$SCID" --expect 200
  ```
  对话的 `base_state.json` 将智能体的 `mcp_config` 与每个凭据保留为 Fernet 密文（包括禁用的服务器），在对话目录或运行的主目录下找不到明文 env 机密和访问令牌（而服务器密钥 `qa-oauth` 是，因此搜索会看到这些文件），并且此系列中使用的标头、env、承载或 OAuth token 值的 None 到达服务器日志（它确实保存了 OAuth 作业）线）。
- **重新启动 (`F19.restart`)。**设置是持久的，OAuth 作业则不然。

  需要：`F19.oauth-flow`、`F19.oauth-refresh-writeback`、`F19.disabled-server`
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --save F19.restart/after-restart \
    --check agent_settings.mcp_config.qa-env.env.QA_F19_TOKEN eq qa-f19-env-secret \
    --check agent_settings.mcp_config.qa-env.enabled eq false \
    --check agent_settings.mcp_config.qa-oauth.auth.state.tokens.access_token eq "$TOKEN" \
    --check agent_settings.mcp_config.qa-f19.command eq "$PY"
  control-agent-server exec --expect-output 'SDK_MCP_ENV_OK=True' --save F19.restart/sdk -- "$PY" "$F19/sdk_mcp_config.py"
  control-agent-server api GET "/api/mcp/oauth/status/$J" --expect 404 --check detail eq 'MCP OAuth job not found'
  control-agent-server helper stop qa-f19-http-bearer qa-f19-http-oauth qa-f19-http-none >/dev/null
  for key in qa-f19 qa-env qa-oauth; do control-agent-server api DELETE "/api/settings/mcp/$key" --expect 200 >/dev/null; done
  control-agent-server api GET /api/settings --check agent_settings.mcp_config.qa-oauth missing --check agent_settings.mcp_config.qa-f19 missing
  ```
  在重启后，环境机密、禁用标志和 OAuth token 读取结果保持不变（通过 `RemoteWorkspace.get_mcp_config()`），完成的任务 ID 为 404，子弹删除了测试夹具和三个服务器。

<a id="gotchas"></a>

## 陷阱

- `POST /api/mcp/test` 和 OAuth 开始答案 HTTP 每个连接 200
  问题：断言`ok`和`error_kind`，永远不要单独使用状态码。 A
  错误的持有者令牌（`HTTPStatusError ... 401`）和立即退出的命令（`McpError: Connection closed`）被分类为`unknown`，而不是
  `connection`.
- `tool_call` 真实运行该工具并共享请求 `timeout`； 选择一个只读工具。 `ok` 仅反映连接和列表。
- Stdio 子级获取 MCP SDK 的默认环境 (`HOME`, `PATH`, ...) 加上 `env`，Agent Server 中没有任何内容； 使用绝对解释器路径。 CLI的测试夹具使用结帐的`.venv`Python； 结帐时没有
  `.venv` 测试夹具命令是 `uv run ...`，这个系列的
  `test -x "$PY"` 前提条件失败。
- 带有纯子字符串的 `pgrep -f` 也与运行的 `bash -c` 匹配
  配方（其文本包含模式）：将整个命令行与
  `pgrep -fx`，或用 `^` 锚定。
- 会话延迟连接到其 MCP 服务器：`POST /api/conversations` 没有 `initial_message` 不会生成任何内容，也不记录任何事件； 第一条消息（甚至与 `run: false` 一起排队）初始化智能体，生成 std​​io 子级并使用 MCP 工具写入 `SystemPromptEvent`。
- 对于两个或多个启用的服务器，会话工具名称带有服务器密钥作为前缀（`qa-f19_qa_echo`）； 对于一台服务器，它们是裸露的（`qa_echo`）。 提示词和 `--contains` 检查不应依赖于哪一个。
- 无法访问的服务器仅花费其自己的工具进行对话，但整个配置失败验证（空服务器）
  `F19.settings-empty-server`) 删除每个 MCP 工具，仅显示日志警告（`MCP server startup failed for <every key>; continuing without its tools`，包含多个日志行，因此 grep for `MCP server startup`）。
- 设置路由使用 `transport`（`extra="forbid"`，因此测试路由的旧版 `type` 为 422）。 键路径上的尾部斜杠重定向 (307)，空键为 404。
- 将已脱敏占位符 `**********` 发送回 `PATCH` 会删除该标头或环境条目，而不是保留它。 往返凭据与
  `X-Expose-Secrets: encrypted` 值（如 `F19.test-encrypted-env` 所做的那样）或将它们排除在补丁之外。
- OAuth 作业在进程内存中保留 15 分钟，并在重新启动时丢失。
  `authorization_url`出现后，`callback_ready`稍微转动True； 较早提交的是 409，因此首先使用 `--until-ok` 来轮询状态。
- 玩浏览器时，读取重定向 `Location`，而不遵循它 (`curl -w '%{redirect_url}'`)。 接下来，它直接将代码传递给探针，完成作业，稍后的回调 POST仅报告已完成的作业（`F19.oauth-callback-replay`）。 整个同意（包括用户的登录）必须在请求的 `timeout`（默认 15 秒，最多 120 秒）内完成，否则作业将失败并显示 `error_kind: timeout`。
- 当服务器有 `OH_SECRET_KEY`（每次启动的运行都有）时，`oauth_state` 是 Fernet 加密的，否则是明文； 将其原封不动地发布到
  设置路线的 `auth.state` 是到达持久化的预期方式。
- `auth.state.token_expires_at` 是客户端对过期的视图：一个过去的值会导致下一个连接刷新 token，尽管提供者仍然会接受它，这是刷新配方触发刷新的方式。 `{"auth":{"strategy":"oauth2","state":{"token_expires_at":1}}}` 的稀疏 `PATCH` 深度合并并保留 token 和客户端注册。 刷新会轮换两个 token（测试夹具提供者撤销旧的），因此比较存储的 token 的配方必须在之后重新读取它。
- 刷新 token 被写入设置服务器的 `url` 等于连接的 URL; 服务器通过内联传递的智能体只在没有相同存储服务器的情况下匹配 URL，其刷新状态会发送到 Webhook (`/mcp-oauth-state`每刷新两次发布一条帖子。 token, 以及过期时间（如果有的话）。 Without a Webhook 在配置文件中，它只存在于内存中，只针对那个会话。
- HTTP 测试夹具是本地配方 `helper`，而不是 CLI 测试夹具：
  `helper start` 在各自的会话中运行，并将结果注册给运行，因此它会超过预条件条目（一个普通的 `cmd &` 会以该条目的进程组结束）。 最后一颗子弹的 `helper stop` 或
  `control-agent-server stop` 结束它们，并且每个也在运行的 `/alive` 停止应答后 25 分钟或 60 秒后退出； 他们的日志位于 `fixtures/f19/` 下。
