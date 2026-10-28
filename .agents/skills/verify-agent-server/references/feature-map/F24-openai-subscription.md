<a id="openai-chatgpt-subscription-device-flow"></a>

# OpenAIChatGPT订阅设备流程

ChatGPT Plus/Pro 用户可以将 Agent Server 登录到其订阅中，以便具有 `auth_type: "subscription"` 的 LLM 配置文件在没有 API 密钥的情况下运行 Codex 模型。 服务器运行的是OpenAI的设备代码流程：客户端启动登录（服务器向`auth.openai.com`请求一次性用户代码并返回一个不可见的轮询token），显示用户代码和验证URL给人类，然后轮询直到人类批准。 然后服务器将 OAuth token 存储在 `OH_PERSISTENCE_DIR/auth/openai_oauth.json` 中并且永远不会返回它们。 状态指示是否存储了一个可用的登录（通过网络刷新过期的登录），注销会删除它并取消已请求的登录，而模型路由会列出订阅可以使用的Codex模型。

资料来源：`openhands-agent-server/openhands/agent_server/llm_router.py`、`openhands-sdk/openhands/sdk/llm/auth/openai.py`、`openhands-sdk/openhands/sdk/llm/auth/credentials.py`、`clients/typescript/src/client/llm-client.ts`

需求：`node`、`network`

路线：`GET /api/llm/subscription/openai/models`，
`GET /api/llm/subscription/openai/status`,
`POST /api/llm/subscription/openai/device/start`,
`POST /api/llm/subscription/openai/device/poll`,
`POST /api/llm/subscription/openai/logout`

<a id="sub-features"></a>

## 子功能

- `F24.models`：`GET /api/llm/subscription/openai/models` 答案 `vendor: openai` 和 SDK 的订阅许可名单 (`OPENAI_CODEX_MODELS`)，已排序。
- `F24.status-disconnected`：没有存储的登录，状态回答200 `connected: false`，`account_email`和`expires_at` null，没有网络，`auth/`目录被收紧到模式700，但不创建凭据文件。
- `F24.status-connected`：存储的、未过期的登录显示 `connected: true` 及其 `expires_at`； token 都不会出现在响应中，并且 `account_email` 仍保留为 null。
- `F24.auth-required`：所有五个路由都在没有密钥或密钥错误的情况下回答 401，并且拒绝注销会保留存储的登录信息。
- `F24.status-restart`：存储的登录名在服务器重新启动后仍然存在。
- `F24.logout`：注销删除存储的凭据文件和答案`connected: false`； 状态同意，第二次注销且未存储任何内容时仍为 200。
- `F24.status-refresh-rejected`：60秒内过期的登录使状态尝试在`auth.openai.com`处进行token刷新； 当 OpenAI 拒绝刷新令牌时，状态回答 200 `connected: false` 并保持文件不变。
- `F24.status-invalid-file`：无效 JSON 或缺少字段的凭据文件读取为 `connected: false`，状态将其删除。
- `F24.device-poll-invalid`：没有正文、没有 `device_code` 或带有非字符串答案 422 的民意调查。
- `F24.device-poll-unknown`：轮询token服务器从未发出答案404`Subscription device login not found or expired`。
- `F24.device-start`: `device/start` 以一个 43 个字符的 `device_code` 和 `user_code` 回答 200。`verification_uri` `https://auth.openai.com/codex/device` `verification_uri_complete` null `expires_at` 前 15 分钟和 `interval_seconds` 至少 1，存储在磁盘上。
- `F24.device-poll-pending`：在任何人批准之前轮询已启动的登录，回答 200 `connected: false`，token 在下一次轮询中保持可用，并且不写入凭据。
- `F24.logout-cancels-pending`：注销后，轮询在回答404之前发出的token。
- `F24.pending-lost-on-restart`：待处理的登录存在于服务器内存中，因此重新启动后，token 会等待答案 404。
- `F24.ts-client`：TypeScript`LLMMetadataClient`订阅方法列出模型、读取状态、启动、轮询和注销，并将 404 和 401 表面为 `HttpError` 状态。
- `F24.offline-safe`：没有通往 `auth.openai.com` 的路由，型号，状态没有过期登录，未知 - token 民意调查和注销仍然正常回答。
- `F24.device-poll-outage`：一个调用 OpenAI 失败的投票（网络在 `device/start` 后断开连接）返回 5xx，但保持登录状态：一旦 OpenAI 可用，相同的 token 会再次调用 200 `connected: false`。
- `F24.status-offline`：登录过期且没有到 `auth.openai.com` 的路由，状态回答 200 `connected: false`，与拒绝刷新的情况相同。
- `F24.device-start-offline`：没有到 `auth.openai.com`、`device/start` 的路由，并且在中断之前启动的登录轮询回答网关错误（502、503 或 504），而不是未处理的 500。
- `F24.login-complete`: 一个ChatGPT账户的`connected: true`人批准了用户代码后，`expires_at`会回答`auth/openai_oauth.json`，使用模式600，消耗token（下一个poll是404），并且状态显示登录。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /api/llm/subscription/openai/models`和`GET /api/llm/subscription/openai/status`（无正文）；
  `POST /api/llm/subscription/openai/device/start`（无正文）返回
  `{device_code, user_code, verification_uri, verification_uri_complete, expires_at (ms), interval_seconds}`;
  `POST /api/llm/subscription/openai/device/poll` 需要
  `{"device_code": "<token from start>"}`; `POST /api/llm/subscription/openai/logout`（无正文）。 状态、轮询和注销都回答相同的 `{vendor, connected, account_email, expires_at}` 形状。 每条路线都需要`X-Session-API-Key`，就像`/api/*`中的REST一样。
- TypeScript客户端：`LLMMetadataClient`（`clients/typescript/src/client/llm-client.ts`，从`clients.ts`导出）：`getOpenAISubscriptionModels()`，
  `getOpenAISubscriptionStatus()`, `startOpenAISubscriptionDeviceLogin()`,
  `pollOpenAISubscriptionDeviceLogin(deviceCode)`,
  `logoutOpenAISubscription()`. `F24.ts-client` 驱动所有五个。
- SDK：这些路由没有 `RemoteWorkspace` 包装器。 过程中，
  `OpenAISubscriptionAuth` 和 `LLM.subscription_login(供应商=“OpenAI”，
  auth_method="device_code")` run the same OpenAI flow locally and use the
  同一个凭据商店。 在服务器上，LLM 配置为
  `auth_type: "subscription"`（个人资料，对话的智能体）加载该家庭通过`create_subscription_llm_from_config`存储的登录信息； 此类配置的配置文件验证映射在 F20 (`F20.validate-subscription-login`) 中。
- 配置：`OH_PERSISTENCE_DIR`决定登录信息的存储位置（`<dir>/auth/openai_oauth.json`，否则`~/.openhands/auth/`）； 启动的运行将其保持在运行下的 `home/.openhands/auth/`。 出站调用遵循服务器的 `HTTPS_PROXY`/`https_proxy` 和 CA 变量，`launch` 转发。
- 前端登录 (Agent Canvas) 是预期的调用者：它启动登录、显示代码、轮询，然后保存配置文件
  `auth_type: "subscription"`（仅限上下文； 请参阅中的评论
  `profiles_router.py` 的验证处理程序）。
- 配方对每个路由使用 `api`，对存储的登录使用 `state ls|cat` 和 `stat`，对刷新尝试使用 `logs --grep`，对持久化使用 `restart`，对于离线情况使用无法访问的代理启动第二次运行，在运行拥有的 CONNECT 代理 (`netgate`) 后面运行第二次运行，可以在中断情况下切断和恢复而无需重新启动，以及 `exec -- node` 用于 TypeScript 客户端。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行处于实时状态并已导出 (`launch --new`)，`doctor` 正常，并且尚未触及 `home/.openhands/auth/`。 不需要 LLM 配置文件。
  `jq`和`node`在`PATH`上； TypeScript 客户端已构建（`clients/typescript/dist/clients.js`，缺失时在其项目符号中构建）。
- 服务器到达 `https://auth.openai.com`（通过此 shell 导出的代理，如果有）：`device/start`、挂起的轮询和 token 刷新是对 OpenAI 的实际调用。 他们创建一次性设备代码，这些代码会在 15 分钟后过期，并且不会让任何人登录。
- 真正的登录需要一个拥有ChatGPT帐户的人，因此大多数项目符号读取的存储登录名排列为：`write-login.sh RUN OFFSET_MS`写入
  `auth/openai_oauth.json` 与假 token (`qa-f24-access-token`,
  `qa-f24-refresh-token`) 从现在起 `OFFSET_MS` 到期，就像完成的设备登录将离开它一样，并打印其 `expires_at`。
  `ts_subscription.mjs` 是TypeScript-客户端程序。
  `EXPECTED_MODELS` 是 SDK 的 `OPENAI_CODEX_MODELS`，模型路由返回的许可名单以及检查订阅配置文件的许可名单。
- 离线子弹启动了自己的第二次运行
  `HTTPS_PROXY=https_proxy=http://127.0.0.1:9`（那里什么也听不到）并在子弹结束时停止。
- 中断子弹需要在登录等待期间断开网络，并且重新启动将丢失登录。 他们的第二次运行将其 HTTPS 通过
  `netgate.py`，空闲环回端口上的 CONNECT 代理，中继到此 shell 的 `HTTPS_PROXY`（或在有 None 时直接连接）。
  `netgate.sh up|down PORT` 启动它并打印其端口，或停止它以便拒绝与该端口的连接，与端口 9 的故障相同。

  ```sh
  F24="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f24"
  AUTH_DIR="$AGENT_SERVER_VERIFY_RUN/home/.openhands/auth"
  mkdir -p "$F24"
  cat > "$F24/write-login.sh" <<'EOF'
  # write-login.sh RUN_DIR OFFSET_MS: store a ChatGPT login with fake tokens
  # that expires OFFSET_MS from now, where a completed device login leaves it.
  auth="$1/home/.openhands/auth"
  exp=$(( $(date +%s) * 1000 + $2 ))
  mkdir -p "$auth"
  printf '{"type": "oauth", "vendor": "openai", "access_token": "qa-f24-access-token", "refresh_token": "qa-f24-refresh-token", "expires_at": %s}\n' "$exp" > "$auth/openai_oauth.json"
  chmod 600 "$auth/openai_oauth.json"
  echo "$exp"
  EOF
  cat > "$F24/ts_subscription.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { LLMMetadataClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const host = process.env.AGENT_SERVER_URL;
  const client = new LLMMetadataClient({ host, apiKey: process.env.SESSION_API_KEY });
  const disconnected = { vendor: 'openai', connected: false, account_email: null, expires_at: null };
  assert.deepEqual(await client.getOpenAISubscriptionModels(), JSON.parse(process.argv[2]));
  assert.deepEqual(await client.getOpenAISubscriptionStatus(), disconnected);
  const start = await client.startOpenAISubscriptionDeviceLogin();
  assert.match(start.device_code, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(start.verification_uri, 'https://auth.openai.com/codex/device');
  assert.ok(start.interval_seconds >= 1);
  assert.deepEqual(await client.pollOpenAISubscriptionDeviceLogin(start.device_code), disconnected);
  assert.deepEqual(await client.logoutOpenAISubscription(), disconnected);
  await assert.rejects(client.pollOpenAISubscriptionDeviceLogin(start.device_code), (err) => err.status === 404);
  const wrongKey = new LLMMetadataClient({ host, apiKey: 'qa-f24-wrong-key' });
  await assert.rejects(wrongKey.getOpenAISubscriptionStatus(), (err) => err.status === 401);
  wrongKey.close();
  client.close();
  console.log('QA_F24_TS_OK');
  JS
  cat > "$F24/netgate.py" <<'PY'
  # netgate.py PORT PORT_FILE: CONNECT proxy on 127.0.0.1:PORT (0 = free port)
  # that relays to $HTTPS_PROXY when set (no proxy credentials), else connects
  # directly; writes the bound port to PORT_FILE once it listens.
  import asyncio, os, sys
  from urllib.parse import urlsplit

  UPSTREAM = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")

  async def pipe(reader, writer):
      try:
          while data := await reader.read(65536):
              writer.write(data)
              await writer.drain()
      except OSError:
          pass
      finally:
          writer.close()

  async def handle(client_r, client_w):
      try:
          if UPSTREAM:
              url = urlsplit(UPSTREAM)
              up_r, up_w = await asyncio.open_connection(url.hostname, url.port or 80)
          else:
              head = await client_r.readuntil(b"\r\n\r\n")
              host, _, port = head.split()[1].decode().rpartition(":")
              up_r, up_w = await asyncio.open_connection(host, int(port))
              client_w.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
          await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
      except (OSError, ValueError, asyncio.IncompleteReadError):
          client_w.close()

  async def main():
      server = await asyncio.start_server(handle, "127.0.0.1", int(sys.argv[1]), reuse_address=True)
      with open(sys.argv[2] + ".tmp", "w") as f:
          f.write(str(server.sockets[0].getsockname()[1]))
      os.replace(sys.argv[2] + ".tmp", sys.argv[2])
      async with server:
          await server.serve_forever()

  asyncio.run(main())
  PY
  cat > "$F24/netgate.sh" <<'SH'
  # netgate.sh up PORT | down PORT: start netgate.py on 127.0.0.1:PORT (0 picks
  # a free one) and print the port once it listens, or stop it and return once
  # connections to PORT are refused.
  dir=$(dirname "$0")
  if [ "$1" = up ]; then
    rm -f "$dir/netgate.port"
    .venv/bin/python -I "$dir/netgate.py" "$2" "$dir/netgate.port" >>"$dir/netgate.log" 2>&1 &
    echo $! >"$dir/netgate.pid"
    for _ in $(seq 100); do
      if [ -s "$dir/netgate.port" ]; then cat "$dir/netgate.port"; exit 0; fi
      sleep 0.1
    done
    exit 1
  fi
  kill "$(cat "$dir/netgate.pid" 2>/dev/null)" 2>/dev/null
  for _ in $(seq 100); do
    (exec 3<>"/dev/tcp/127.0.0.1/$2") 2>/dev/null || exit 0
    sleep 0.1
  done
  exit 1
  SH
  EXPECTED_MODELS=$(OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -c 'import json; from openhands.sdk.llm.auth import OPENAI_CODEX_MODELS; print(json.dumps(sorted(OPENAI_CODEX_MODELS)))')
  test "$EXPECTED_MODELS" != '[]'
  ```

- **订阅模型 (`F24.models`).**列出订阅可以使用的模型。
  ```sh
  control-agent-server api GET /api/llm/subscription/openai/models --expect 200 --check vendor eq openai \
    --check models len-ge 1 --check models eq "$EXPECTED_MODELS" --save F24.models/models
  ```
  `models` 等于排序后的 `OPENAI_CODEX_MODELS` (`gpt-5.5`, ...,
  `gpt-6.1-sol` 在撰写本文时）。
- **未登录状态(`F24.status-disconnected`)。**首先松开 `auth/` 目录，因此读取显示服务器将其收紧。
  ```sh
  mkdir -p "$AUTH_DIR" && chmod 755 "$AUTH_DIR"
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check vendor eq openai \
    --check connected eq false --check account_email eq null --check expires_at eq null --save F24.status-disconnected/status
  test "$(stat -c %a "$AUTH_DIR")" = 700
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  ```
  正文是 `{"vendor": "openai", "connected": false, "account_email": null, "expires_at": null}`，目录模式变为 700，仍然空着。
- **已存储的登录状态 (`F24.status-connected`)。**存储一个小时内有效的登录信息。
  ```sh
  EXP=$(bash "$F24/write-login.sh" "$AGENT_SERVER_VERIFY_RUN" 3600000)
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq true \
    --check expires_at eq "$EXP" --check account_email eq null \
    --check . not-contains qa-f24-access-token --check . not-contains qa-f24-refresh-token --save F24.status-connected/status
  ```
  `connected`是`true`，`expires_at`是以毫秒为单位存储的值，token都不在主体中。 对于未过期的登录，不会进行任何网络调用。
- **需要密钥 (`F24.auth-required`)。**每一条没有密钥和错误密钥的路线，同时存储上一个项目符号的登录信息。

  需要：`F24.status-connected`
  ```sh
  control-agent-server api GET /api/llm/subscription/openai/models --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/subscription/openai/models --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/subscription/openai/status --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/llm/subscription/openai/status --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/device/start --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/device/start --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/device/poll --auth none --json '{"device_code": "qa-f24-unknown"}' --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/device/poll --auth bad --json '{"device_code": "qa-f24-unknown"}' --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/logout --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/llm/subscription/openai/logout --auth bad --expect 401 --check detail eq Unauthorized \
    --save F24.auth-required/logout-bad-key
  control-agent-server state ls home/.openhands/auth/openai_oauth.json --expect-count 1
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq true --check expires_at eq "$EXP"
  ```
  所有十个呼叫都是401 `{"detail": "Unauthorized"}`; 运行的密钥仍然读取登录信息，因此拒绝的登出操作没有删除任何内容。
- **通过重新启动登录 (`F24.status-restart`)。**重新启动并再次读取状态。

  需要：`F24.status-connected`
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq true \
    --check expires_at eq "$EXP" --save F24.status-restart/after-restart
  ```
  登录信息存储在磁盘上，因此重启后的服务器报告没有变化。
- **注销(`F24.logout`)。**注销，读回，再次注销。
  ```sh
  control-agent-server api POST /api/llm/subscription/openai/logout --expect 200 --check vendor eq openai \
    --check connected eq false --check expires_at eq null --save F24.logout/logout
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false --save F24.logout/status-after
  control-agent-server api POST /api/llm/subscription/openai/logout --expect 200 --check connected eq false --save F24.logout/logout-again
  ```
  文件已丢失，状态为断开连接，第二次无任何存储的登出返回状态码200，且请求体相同。
- ** 拒绝刷新请求 (`F24.status-refresh-rejected`).** 保存一个有效期为30秒的登录（在60秒的安全窗口内，因此可以视为已过期）, 刷新令牌 OpenAI 不知道。
  ```sh
  N0=$(control-agent-server logs --grep 'Refreshing OpenAI access token' | jq .total_matching)
  EXP=$(bash "$F24/write-login.sh" "$AGENT_SERVER_VERIFY_RUN" 30000)
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false \
    --check expires_at eq null --save F24.status-refresh-rejected/status
  N1=$(control-agent-server logs --grep 'Refreshing OpenAI access token' | jq .total_matching)
  test "$N1" -gt "$N0"
  control-agent-server state cat home/.openhands/auth/openai_oauth.json --check expires_at eq "$EXP" \
    --check access_token eq qa-f24-access-token --check refresh_token eq qa-f24-refresh-token
  control-agent-server api POST /api/llm/subscription/openai/logout --expect 200
  ```
  `Refreshing OpenAI access token`、OpenAI拒绝了刷新令牌，答案是`connected: false`。 该存储的文件保留原样（没有新的token，还是`expires_at`）。直到注销时才会被删除。
- **无效的凭据文件 (`F24.status-invalid-file`)。**一个文件缺少必填字段，然后一个文件不存在 JSON。
  ```sh
  printf '{"type": "oauth", "vendor": "openai"}\n' > "$AUTH_DIR/openai_oauth.json"
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false \
    --save F24.status-invalid-file/missing-fields
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  printf 'qa-f24-not-json' > "$AUTH_DIR/openai_oauth.json"
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false \
    --save F24.status-invalid-file/not-json
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  ```
  两个读取都是 `connected: false`，每次服务器删除不可读文件。
- **格式错误的民意调查 (`F24.device-poll-invalid`)。**没有身体，一个空物体，一个数字。
  ```sh
  control-agent-server api POST /api/llm/subscription/openai/device/poll --expect 422 --check detail.0.type eq missing \
    --check detail.0.loc eq '["body"]'
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json '{}' --expect 422 --check detail.0.type eq missing \
    --check detail.0.loc eq '["body", "device_code"]' --save F24.device-poll-invalid/missing-code
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json '{"device_code": 123}' --expect 422 \
    --check detail.0.type eq string_type --save F24.device-poll-invalid/number
  ```
  所有三个都带有字段名为 `detail[0].loc` 的 422 错误。
- **未知 token (`F24.device-poll-unknown`).**轮询token服务器从未发出。
  ```sh
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json '{"device_code": "qa-f24-unknown"}' --expect 404 \
    --check detail eq 'Subscription device login not found or expired' --save F24.device-poll-unknown/unknown
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  ```
  在没有调用 OpenAI 的情况下，返回 404。
- **开始登录 (`F24.device-start`)。**询问设备代码。
  ```sh
  T0=$(date +%s)
  START=$(control-agent-server api POST /api/llm/subscription/openai/device/start --expect 200 \
    --check device_code matches '^[A-Za-z0-9_-]{43}$' --check user_code matches '^[A-Z0-9]+-[A-Z0-9]+$' \
    --check verification_uri eq https://auth.openai.com/codex/device --check verification_uri_complete eq null \
    --check expires_at ge "$((T0 * 1000 + 900000))" --check expires_at le "$(((T0 + 60) * 1000 + 900000))" \
    --check interval_seconds ge 1 --save F24.device-start/start)
  DC=$(jq -r .response.body.device_code <<<"$START")
  INTERVAL=$(jq -r .response.body.interval_seconds <<<"$START")
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false
  ```
  的 `device_code` 服务器自身的随机 token (OpenAI's
  `device_auth_id` 保留在服务器上），`user_code` 看起来像
  `ABCD-12345`、`expires_at` 是请求后 15 分钟，并且
  `interval_seconds` 是 OpenAI 的轮询间隔（今天为 5）。 未存储任何内容，状态仍为断开连接。
- **等待登录 (`F24.device-poll-pending`)。**轮询两次，等待服务器按照协议要求返回的时间间隔。

  需要：`F24.device-start`
  ```sh
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$DC\"}" --expect 200 \
    --check connected eq false --check expires_at eq null --save F24.device-poll-pending/first
  sleep "$INTERVAL"
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$DC\"}" --expect 200 \
    --check connected eq false --save F24.device-poll-pending/second
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  ```
  两个调查都是200 `connected: false` (OpenAI 答案是“pending”，所以  token 第一个之后又放了回来。 无凭据 appear.
- **注销会取消待处理的登录 (`F24.logout-cancels-pending`)。**退出
  while `DC` is pending.

  需要：`F24.device-start`
  ```sh
  control-agent-server api POST /api/llm/subscription/openai/logout --expect 200 --check connected eq false
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$DC\"}" --expect 404 \
    --check detail eq 'Subscription device login not found or expired' --save F24.logout-cancels-pending/poll-after-logout
  ```
  刚才还在的 token 现在是 404。
- **等待登录和重新启动 (`F24.pending-lost-on-restart`)。**开始登录，查看待处理状态，重新启动，再次轮询。
  ```sh
  DC2=$(control-agent-server api POST /api/llm/subscription/openai/device/start --expect 200 --field device_code)
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$DC2\"}" --expect 200 \
    --check connected eq false
  control-agent-server restart
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$DC2\"}" --expect 404 \
    --check detail eq 'Subscription device login not found or expired' --save F24.pending-lost-on-restart/poll-after-restart
  ```
  在重启之前，该轮询仍在进行中。 在它之后 token 是未知的，因此客户端必须重新开始（并且批准旧代码的人没有人签入）。
- **TypeScript 客户端 (`F24.ts-client`).**各订阅方式
  `LLMMetadataClient` 来自构建的客户端（缺失时在此处构建）。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server exec --timeout 120 --expect-output QA_F24_TS_OK --save F24.ts-client/program -- node "$F24/ts_subscription.mjs" "$EXPECTED_MODELS"
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq false
  control-agent-server state ls 'home/.openhands/auth/*' --expect-count 0
  ```
  该程序打印 `QA_F24_TS_OK`模型等于白名单，状态为断开连接，一个开始的登录请求为 `connected: false`登出回答断开，已登出的 token 拒绝 `HttpError` 状态码为404，且带有错误的密钥。
- **离线安全路线 (`F24.offline-safe`).**第二次运行的唯一出路是关闭端口上的代理。
  ```sh
  OFF=$(control-agent-server launch --new --name f24-offline --env HTTPS_PROXY=http://127.0.0.1:9 --env https_proxy=http://127.0.0.1:9 --print-run)
  trap 'control-agent-server stop --run "$OFF" >/dev/null' EXIT
  if control-agent-server api POST /api/llm/subscription/openai/device/start --run "$OFF" --expect 200 --quiet; then false; fi
  control-agent-server api GET /api/llm/subscription/openai/models --run "$OFF" --expect 200 --check models eq "$EXPECTED_MODELS"
  control-agent-server api GET /api/llm/subscription/openai/status --run "$OFF" --expect 200 --check connected eq false \
    --save F24.offline-safe/status-no-login
  control-agent-server api POST /api/llm/subscription/openai/device/poll --run "$OFF" --json '{"device_code": "qa-f24-unknown"}' --expect 404
  bash "$F24/write-login.sh" "$OFF" 3600000 >/dev/null
  control-agent-server api GET /api/llm/subscription/openai/status --run "$OFF" --expect 200 --check connected eq true
  control-agent-server api POST /api/llm/subscription/openai/logout --run "$OFF" --expect 200 --check connected eq false \
    --save F24.offline-safe/logout
  control-agent-server state ls --run "$OFF" 'home/.openhands/auth/*' --expect-count 0
  ```
  `device/start` 无法成功在那里（因此网络真的被切断了），而没有登录或过期的模型、未知的token 汇报和登出都像在线运行一样。
- **待登录期间中断 (`F24.device-poll-outage`)。** `netgate` 之后第二次运行：开始登录，切断网络，轮询，恢复它，再次轮询相同的 token。
  ```sh
  OUTAGE=""
  GP=$(bash "$F24/netgate.sh" up 0)
  trap 'if [ -n "$OUTAGE" ]; then control-agent-server stop --run "$OUTAGE" >/dev/null; fi; bash "$F24/netgate.sh" down "$GP"' EXIT
  OUTAGE=$(control-agent-server launch --new --name f24-outage --env "HTTPS_PROXY=http://127.0.0.1:$GP" --env "https_proxy=http://127.0.0.1:$GP" --print-run)
  START3=$(control-agent-server api POST /api/llm/subscription/openai/device/start --run "$OUTAGE" --expect 200)
  DC3=$(jq -r .response.body.device_code <<<"$START3")
  bash "$F24/netgate.sh" down "$GP"
  control-agent-server api POST /api/llm/subscription/openai/device/poll --run "$OUTAGE" --json "{\"device_code\": \"$DC3\"}" --expect 5xx \
    --save F24.device-poll-outage/poll-offline
  bash "$F24/netgate.sh" up "$GP" >/dev/null
  sleep "$(jq -r .response.body.interval_seconds <<<"$START3")"
  control-agent-server api POST /api/llm/subscription/openai/device/poll --run "$OUTAGE" --json "{\"device_code\": \"$DC3\"}" --expect 200 \
    --check connected eq false --save F24.device-poll-outage/poll-online
  control-agent-server state ls --run "$OUTAGE" 'home/.openhands/auth/*' --expect-count 0
  ```
  在停机期间进行的调查失败（今天是500，`"exception": "All connection attempts failed"`）。 `F24.device-start-offline` 确认网关状态应为 `finally`，路由器的 token
  back：网络返回后，同样的token仍然处于pending状态（200
  `connected: false`，而不是 404）。 在下一次真正调用 OpenAI 之前，睡眠会尊重 `interval_seconds`。
- **登录过期离线状态(`F24.status-offline`)。**像`F24.offline-safe`一样离线第二次运行。 首先有两个控制：网络确实被切断（`device/start`无法成功）并且相同的运行读取未过期的登录作为连接。 然后是一秒钟前过期的登录。
  ```sh
  OFF=$(control-agent-server launch --new --name f24-offline --env HTTPS_PROXY=http://127.0.0.1:9 --env https_proxy=http://127.0.0.1:9 --print-run)
  trap 'control-agent-server stop --run "$OFF" >/dev/null' EXIT
  if control-agent-server api POST /api/llm/subscription/openai/device/start --run "$OFF" --expect 200 --quiet; then false; fi
  EXP5=$(bash "$F24/write-login.sh" "$OFF" 3600000)
  control-agent-server api GET /api/llm/subscription/openai/status --run "$OFF" --expect 200 --check connected eq true \
    --check expires_at eq "$EXP5"
  EXP6=$(bash "$F24/write-login.sh" "$OFF" -1000)
  control-agent-server api GET /api/llm/subscription/openai/status --run "$OFF" --expect 200 --check connected eq false \
    --save F24.status-offline/status
  control-agent-server state cat --run "$OFF" home/.openhands/auth/openai_oauth.json --check expires_at eq "$EXP6" \
    --check refresh_token eq qa-f24-refresh-token
  control-agent-server logs --run "$OFF" --grep 'Refreshing OpenAI access token' --expect-min 1
  control-agent-server logs --run "$OFF" --grep 'Unhandled exception on GET' --expect-none
  ```
  预期：刷新尝试后，答案为 200 `connected: false`
  当 OpenAI 拒绝刷新 (`F24.status-refresh-rejected`) 时给出状态，并且 GET 没有回溯（`device/start` 控件留下自己的
  `Unhandled exception on POST`, `F24.device-start-offline`).
  `get_openai_subscription_status` 处理 httpx 传输层错误
  `refresh_if_needed()` 就像被拒绝的刷新 (`llm_router.py`); 存储的文件保持原样，因此状态重试会在网络恢复后刷新。
- **启动并轮询离线登录 (`F24.device-start-offline`)，已知bug。**第二次运行落后于 `netgate`：在线时启动登录并查看其状态（控制台），切断网络，然后再次启动并轮询第一个。
  ```sh
  OUTAGE=""
  GP=$(bash "$F24/netgate.sh" up 0)
  trap 'if [ -n "$OUTAGE" ]; then control-agent-server stop --run "$OUTAGE" >/dev/null; fi; bash "$F24/netgate.sh" down "$GP"' EXIT
  OUTAGE=$(control-agent-server launch --new --name f24-outage --env "HTTPS_PROXY=http://127.0.0.1:$GP" --env "https_proxy=http://127.0.0.1:$GP" --print-run)
  DC4=$(control-agent-server api POST /api/llm/subscription/openai/device/start --run "$OUTAGE" --expect 200 --field device_code)
  control-agent-server api POST /api/llm/subscription/openai/device/poll --run "$OUTAGE" --json "{\"device_code\": \"$DC4\"}" \
    --expect 200 --check connected eq false
  bash "$F24/netgate.sh" down "$GP"
  control-agent-server api POST /api/llm/subscription/openai/device/start --run "$OUTAGE" --expect 502,503,504 \
    --save F24.device-start-offline/start  # bug：status eq 500 && response.body.exception 包含“所有连接尝试均失败”
  control-agent-server api POST /api/llm/subscription/openai/device/poll --run "$OUTAGE" --json "{\"device_code\": \"$DC4\"}" \
    --expect 502,503,504 --save F24.device-start-offline/poll  # bug：status eq 500 && response.body.exception 包含“所有连接尝试均失败”
  control-agent-server logs --run "$OUTAGE" --grep 'Unhandled exception' --expect-none
  ```
  预期：告诉客户端的网关状态（502、503 或 504）OpenAI
  无法访问，因为 `credential_binding.py` 和 `git_provider_service.py` 对于不可用的上游回答 502 或 504。 两个标记的调用都会对该错误进行编码，因此在两条路线都得到修复之前，该项目符号仍然是一个已知的错误。 今天标记的 `device/start` 是 500 `Internal Server Error`
  `exception: "All connection attempts failed"` 和 `Unhandled exception` 回溯，轮询 (`F24.device-poll-outage`) 也是如此：两者都不是
  `start_openai_subscription_device_login` 也不
  `poll_openai_subscription_device_login` 映射上游错误，因此传输层错误和 OpenAI 的非 2xx 答案（`RuntimeError` 来自
  `_request_device_code` 和 `_poll_device_code_once`) 所有表面均为通用 500。
- **完成登录 (`F24.login-complete`)，已被阻止。**需要 ChatGPT Plus/Pro 帐户以及在 15 分钟内打开 `verification_uri`、登录并进入 `user_code` 的人员； 这台机器两者都没有。 对于有人可以批准的运行，命令如下：
  ```sh
  LOGIN=$(control-agent-server api POST /api/llm/subscription/openai/device/start --expect 200 --save F24.login-complete/start)
  LDC=$(jq -r .response.body.device_code <<<"$LOGIN")
  jq -r '.response.body | "Open \(.verification_uri) and enter \(.user_code)"' <<<"$LOGIN"
  for _ in $(seq 1 180); do
    if control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$LDC\"}" --expect 200 --check connected eq true --quiet; then break; fi
    sleep 5
  done
  control-agent-server state cat home/.openhands/auth/openai_oauth.json --mode 600 --check vendor eq openai --check expires_at exists >/dev/null
  control-agent-server api POST /api/llm/subscription/openai/device/poll --json "{\"device_code\": \"$LDC\"}" --expect 404
  control-agent-server api GET /api/llm/subscription/openai/status --expect 200 --check connected eq true --check expires_at exists \
    --save F24.login-complete/status
  ```
  预期：轮询将 `connected: true` 变为 `expires_at`，文件为
  模式600，token被消耗(404)，状态为连接。 之后注销 (`F24.logout`) 会再次删除真正的登录。

<a id="gotchas"></a>

## 陷阱

- 模型路由返回 `OPENAI_CODEX_MODELS` (`openhands-sdk/openhands/sdk/llm/auth/openai.py`)，而不是 `codex` ACP 提供者的已弃用 `available_models`。 这两个列表一直匹配，直到 #5436 仅将 `gpt-6-sol`、`gpt-6-luna` 和 `gpt-6.1-sol` 添加到允许列表中； 从允许列表中得出期望，而不是从粘贴的列表中得出。
- 这些路由从服务器进程调用 `https://auth.openai.com`：
  `device/start` 和待定 token 的每次轮询始终为状态，仅当存储的登录在 60 秒内过期时才显示。 在没有出站 HTTPS、`F24.device-start`、`F24.device-poll-pending` 的计算机上，
  `F24.logout-cancels-pending`, `F24.pending-lost-on-restart`,
  `F24.ts-client`、`F24.device-poll-outage` 和
  `F24.status-refresh-rejected` 因 500 个离线错误而失败，并且
  `F24.device-start-offline` 在其在线 `device/start` 排列步骤中失败（`fail`，而不是 `xfail`）； `Needs: network` 命名了该先决条件。
  `netgate` 在没有凭据的情况下中继到 shell 的 `HTTPS_PROXY`，因此需要它们的代理会破坏中断子弹。
- 要切断网络，请同时设置 `HTTPS_PROXY` 和 `https_proxy`：Python 的代理查找首选小写名称，而 `launch` 则从调用者的 shell 转发两者。
- 未完成的登录在服务器进程中被保留`_PENDING_OPENAI_DEVICE_LOGINS`：重启会丢失他们，他们将在15分钟后过期 `start` (`DEVICE_CODE_TIMEOUT_SECONDS`在启动时按需修剪，并进行轮询。
- 启动响应中的 `device_code` 是服务器的不透明轮询 token，而不是 OpenAI 的 `device_auth_id`。 `user_code` 是一个15分钟内有效的实时一次登录代码：它在`F24.device-start`证据中，因此在有效期内不要发布该证据（设备代码是钓鱼的目标）。
- 荣誉 `interval_seconds` 在选举之间。 快速投票今天有效，但  OpenAI 除了成功、403或404（429或5xx），以及任何其他传输层错误，变为 500 `poll` 在  token 仍处于待定状态（）`F24.device-poll-outage` 显示了网络断开的情况。 同时到达的另一个相同类型的调查 token 正在飞行的答案
  `connected: false` 而不是 404。
- 注销会发生一个纪元：注销运行时已经与 OpenAI 进行对话的轮询以 `connected: false` 结束，并且不存储它获得的凭据。
- 60 秒内过期的登录将被视为过期。 当 OpenAI 拒绝刷新时，死文件将保留，因此每个状态调用都会再次访问网络，直到注销。 成功刷新会使用新的 token 和 `expires_in` 重写文件（默认 3600 秒）。
- `account_email` 始终是 `null`； 服务器永远不会解码 token。
- 登录信息以明文 JSON 形式存储（未使用 `OH_SECRET_KEY` 加密）； 服务器在写入文件时将文件模式设置为 600，并在每次访问（包括普通状态读取）时将 `auth/` 目录模式设置为 700。 不可读的文件将在下次读取状态时以静默方式删除。
- 路由不发出 WebSocket 事件。 当 deferred-init 服务器处于休眠状态时，它们会像每个 `/api/*` 路由 (F03) 一样回答 503。
- `F24.ts-client` 导入构建的 `clients/typescript/dist` 并仅在缺少时构建它：更改 `clients/typescript/src` 后，运行
  `npm run build` 首先，或者子弹证明了旧版本。
- 5xx 主体被服务器的异常处理程序重写为
  `{"detail": "Internal Server Error", "exception": ..., "error_id": ...}`，因此客户端只能通过状态来区分 OpenAI 中断和服务器崩溃。
