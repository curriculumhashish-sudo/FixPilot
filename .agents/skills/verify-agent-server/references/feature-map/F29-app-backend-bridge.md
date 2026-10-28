<a id="canvas-app-backend-bridge-session-http-and-websocket-proxy"></a>

# Canvas App 后端桥（会话、HTTP 和 WebSocket 代理）

Agent Canvas iframe 如何从单独的浏览器源到达 Canvas 应用程序自己的后端进程。 当配置`app_backend_public_url`时，服务器在`/server_info`中通告它，Canvas页面交换它的
`X-Session-API-Key` 五分钟，应用程序范围，HttpOnly cookie
`POST /app-backends/{name}/session`（发送到入口主机，允许的控制 `Origin` 不是入口源）。 从那时起，所有 HTTP 方法和 WebSocket 下的 `/app-backends/{name}` 都会转发到回路的准备后端，仅通过那个 cookie：WebSockets 方法和 `Origin` 也必须携带 `Authorization` 等于入站源、cookie、`X-Session-API-Key` 和带有密钥的查询参数，这些参数在上游被去除，上游重定向变为 502，上游
`Set-Cookie` 被删除。 会话只存在于内存中，并在撤销、后端停止、禁用、后端或服务器重启时销毁，以及在它们的TTL时，这也会关闭它们的桥接WebSockets。 安装、准备和启动后端是 Canvas 应用程序系列 (F28)； 这个家庭安排了一个现成的后端并证明了桥梁。

资料来源：`openhands-agent-server/openhands/agent_server/canvas_extensions_bridge_router.py`、`openhands-agent-server/openhands/agent_server/canvas_extensions/bridge.py`、`openhands-agent-server/openhands/agent_server/docker_runtime/proxy.py`、`openhands-agent-server/openhands/agent_server/config.py`、`openhands-agent-server/openhands/agent_server/server_details_router.py`

需求：`git`

发射：`--canvas-ingress`

路线：`POST /app-backends/{extension_name}/session`，
`DELETE /app-backends/{extension_name}/session`,
`DELETE /app-backends/{extension_name}/{path:path}`,
`GET /app-backends/{extension_name}/{path:path}`,
`PATCH /app-backends/{extension_name}/{path:path}`,
`POST /app-backends/{extension_name}/{path:path}`,
`PUT /app-backends/{extension_name}/{path:path}`,
`DELETE /app-backends/{extension_name}`, `GET /app-backends/{extension_name}`,
`PATCH /app-backends/{extension_name}`, `POST /app-backends/{extension_name}`,
`PUT /app-backends/{extension_name}`,
`WS /app-backends/{extension_name}/{path:path}`,
`WS /app-backends/{extension_name}`

<a id="sub-features"></a>

## 子功能

- `F29.ingress-advertised`：设置`app_backend_public_url`后，`/server_info`将其报告为`app_backend_ingress_url`并列出`canvas_app_backend_bridge_v1`功能。
- `F29.ingress-config-errors`：在没有`app_backend_public_url`的服务器上，会话路由和HTTP代理会返回503 `Canvas App backend ingress is not configured`，WebSocket握手被拒绝返回403，而`/server_info`既没有URL也没有能力。 不是 http(s) URL 的值会回答 503 `... is misconfigured`，并且非环回主机上的普通 HTTP 入口拒绝创建会话 (503 `... require HTTPS or a loopback secure context`)。
- `F29.session-bootstrap`：`POST /app-backends/{name}/session`用按键和控件`Origin`返回`ingress_url`，`expires_at`提前约300秒和`iframe_sandbox`，并用`HttpOnly; Max-Age=300; Path=/app-backends/{name}; SameSite=none; Secure; Partitioned`设置`oh_app_backend_session`； cookie jar 将其重播到应用程序的代理，并且允许浏览器的 CORS 引导程序预检用于凭据的控制源。
- `F29.session-key-required`：引导程序对丢失或错误的 `X-Session-API-Key`、`Authorization: Bearer` 和应用程序会话 cookie 回答 401，没有 cookie。
- `F29.session-ingress-host`：引导程序或代理请求，其 `Host` 不是入口主机，回答 421，并且 `X-Forwarded-Host` 在 `trust_forwarded_headers` 关闭时不会更改。
- `F29.session-forwarded-proto`：`trust_forwarded_headers` 关闭时，客户端提供的 `X-Forwarded-Proto: https` 不会更改请求来源，因此普通 HTTP 入口上的引导程序仍然会成功。
- `F29.session-origin-rules`：缺失的、外部的或 `null` `Origin` 得到 403，入口源本身得到 409，两者都没有 cookie； 接受任何 `localhost` 或 `127.0.0.1` 来源。
- `F29.session-configured-control-origin`重启后，`allow_cors_origins`、`allow_cors_origin_regex`、`DOCKER_HOST_ADDR`和Docker主机地址成功（CORS预检也允许），而未列出的主机、列出的主机在另一个方案或端口上，或部分正则匹配，以及另一个地址返回403。 配置的控制源不计为不安全代理方法的入口 `Origin`，清除设置会再次拒绝这些源。
- `F29.session-backend-not-ready`：引导或代理后端未就绪的应用程序（未知应用程序）答案 503 `Canvas App backend is not ready`； 无效的应用程序名称会回答 422。
- `F29.proxy-get`：安全方法（GET、HEAD、OPTIONS），只有cookie通过方法、子路径和查询到达后端，包括`GET /session`； CORS 预检由服务器应答，并且永远不会到达后端。
- `F29.proxy-cookie-required`：不带 cookie、使用伪造 cookie、使用其他应用程序的 cookie 或仅使用会话密钥答案 401 的代理请求。
- `F29.proxy-unsafe-methods`：POST、PUT、PATCH和DELETE带着cookie和入口`Origin`通过它们的body到达后端； 如果没有`Origin`（或有控制源），他们会在检查 cookie 之前回答 403。
- `F29.proxy-root`：`/app-backends/{name}`和`/app-backends/{name}/`对于所有五个方法都到达后端的`/`，并且在`/app-backends/{name}/`上的`path`查询参数是普通参数。
- `F29.proxy-root-path-query`：在裸根路由（没有后缀斜杠）上，一个 `path` 查询参数会被转发为查询参数发送到后端的 `/`，就像其他参数一样。
- `F29.proxy-credentials-stripped`：后端永远看不到`Cookie`、`Authorization`、`X-Session-API-Key`或`session_api_key`、`X-Session-API-Key`和`Authorization`查询参数，而其他标头和参数则通过。
- `F29.proxy-request-framing`: 代理请求保持其封装：GET到达后端时没有`Transfer-Encoding`，而POST带有13字节JSON的请求体到达后端时则有`Content-Length: 13`，这与直接发送到后端时一样。
- `F29.proxy-response-filter`：上游重定向变为 502 `Upstream redirect is not allowed`，没有 `Location`，上游 `Set-Cookie` 永远不会到达客户端。
- `F29.proxy-response-headers`：代理响应携带单个 `Date` 和单个 `Server` 标头。
- `F29.proxy-path-traversal`：`.`/`..`段和反斜杠，在任何深度进行百分比编码，在HTTP和WebSocket上的任何凭据检查之前回答400 `Invalid backend path`。
- `F29.ws-bridge`: a WebSocket 带有 cookie 和 ingress `Origin` 它被桥接到后端，后端回显帧并接收不到 cookie `Origin`, 会话密钥或 `session_api_key` 参数； 后端未升级的路径（根路由）被接受，然后以 1011 关闭。
- `F29.ws-handshake-rejections`：没有入口 `Origin` 的 WebSocket，没有此应用程序的有效 cookie，或者只有会话密钥在与 403 握手时被拒绝。
- `F29.ws-subprotocol`：客户端请求的WebSocket子协议到达后端并通过网桥协商。
- `F29.session-revoke`: `DELETE /app-backends/{name}/session` 使用 `Max-Age=0` cookie 回答 204，关闭该会话的桥接 WebSocket 并使其 cookie 为 401，而应用程序的其他会话继续工作； 它需要密钥和控制源，但不需要 cookie。
- `F29.backend-lifecycle-revokes`：停止或禁用后端关闭桥接WebSockets并使桥接应答503； 后端在新端口上再次启动后，旧的 cookie 会返回 401，新的会话将正常工作。 `unhealthy` 当后端在准备就绪时崩溃时，状态轮询报告了 [exited]。之后，桥接器会返回 503，而当后端重新启动时，一个在崩溃之前创建的会话会收到 401，因为会话是绑定到后端端口的。
- `F29.backend-crash-detected`：一旦就绪的后端进程退出，桥接器就会应答 503 `Canvas App backend is not ready`，而不等待任何人轮询后端的状态。
- `F29.trusted-forwarded-headers`: 当 `trust_forwarded_headers` 时，请求的 `X-Forwarded-Host` 名为入站，而入站的 `Host` 不是，转发的 `https` 不匹配入站，答案为 421。 再次关闭，相同的标头将被忽略。
- `F29.sessions-not-persisted` 服务器重启后，后端停止（桥接返回 503），其准备的修订仍然存在，因此它不会启动新的准备，重启前 minted 的 cookie 会返回 401。
- `F29.session-ttl`：当引导后 300 秒会话过期时，空闲桥接 WebSocket 将被关闭，并且其 cookie 将变为 401。
- `F29.uninstall-revokes`：卸载应用程序会关闭其桥接 WebSockets，停止其后端并使桥接器对旧 cookie 和新引导程序应答 503。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- Config：`app_backend_public_url`（`OH_APP_BACKEND_PUBLIC_URL`），入口的单独浏览器来源； `launch --canvas-ingress` 将其设置为运行自己的 URL (`http://127.0.0.1:PORT`)，因此配方中使用的控制原点是 `http://localhost:3000`。 `trust_forwarded_headers` (`OH_TRUST_FORWARDED_HEADERS`) 让`X-Forwarded-Proto`/`X-Forwarded-Host`决定请求来源； `allow_cors_origins`,
  `allow_cors_origin_regex` 和 `DOCKER_HOST_ADDR` 环境变量将接受的控制源扩展到 `localhost` 和 `127.0.0.1` 之外。 桥接器使用自己的代码 (`_allowed_control_origin`) 检查它们，而不是通过读取相同设置的 CORS 中间件（`F29.session-configured-control-origin` 驱动两者）。
- REST: `GET /server_info` (`app_backend_ingress_url`, 能力
  `canvas_app_backend_bridge_v1`; F01 拥有该路线）。
- REST: `POST /app-backends/{extension_name}/session` 和
  `DELETE /app-backends/{extension_name}/session`：`X-Session-API-Key`、控制`Origin`、入口`Host`； 没有身体。
- REST（代理，仅 cookie，`include_in_schema=False`）：
  `GET|HEAD|OPTIONS|POST|PUT|PATCH|DELETE /app-backends/{extension_name}`和`/app-backends/{extension_name}/{path:path}`； 需要不安全的方法
  `Origin` 等于入口原点。 路由表列出了五种方法； HEAD 和 OPTIONS 骑在同一个处理程序上。
- WebSocket: `/app-backends/{extension_name}` 和
  `/app-backends/{extension_name}/{path:path}`，在握手时包含 cookie 和 ingress `Origin`。
- 撤销会话的后端生命周期（F28 拥有这些路由）：
  `POST /api/canvas-extensions/installed/{name}/backend/stop`,
  `PATCH /api/canvas-extensions/installed/{name}` 与 `{"enabled": false}`，
  `DELETE /api/canvas-extensions/installed/{name}`.
- TypeScript客户端：`CanvasExtensionsClient.createAppBackendSession(name, signal)`和`revokeAppBackendSession(name, signal)`（`clients/typescript/src/client/canvas-extensions-client.ts`）； 他们需要
  `appBackendIngressUrl` 来自 `/server_info`，而 `OpenHandsClient` 不
  pass to its `canvasExtensions`, and they rely on the browser adding `Origin`
  并保留 cookie (`credentials: 'include'`)。 这里没有开车。
- SDK: None. Agent Canvas (上下文)：在 iframe 中加载应用程序
  `ingress_url` 与返回的 `iframe_sandbox` 一起，在每个后端启动之后和 TTL 之前重新引导。
- 食谱使用 CLI 的 `api` 动词驱动每条路线（cookie 作为原始
  `--cookie` 值或 `--jar`、`Origin` 和 `Host` 作为 `--header`) 及其
  `ws listen`/`ws开始` verbs with `--auth None` and `--header` for the cookie and `Origin`; HEAD, OPTIONS and CORS preflights use `curl`, and the subprotocol check uses a `WebSocket` client through `exec`。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 使用该系列的 `Launch:` 标志 (`--canvas-ingress`) 启动的运行，因此入口是运行自己的 URL。 不需要LLM。
- `qa-backend`：CLI的`fixture canvas-app --backend ok`（aiohttp
  后端：`/health`、一个 `/ws` 文本回显应答 `echo:<frame>` 和一个
  包罗万象的 JSON 回显 `app`、`method`、`path`、`query`、`body` 和
  `cookie_forwarded`)、已安装、启用、准备并启动。
- `qa-headers`：相同的测试夹具，其后端被此处编写的诊断后端替换（回显每个请求标头，`/redirect` 回答 302，
  `/set-cookie` 设置了一个 cookie，`/ws` 接受子协议 `qa.v1`，并报告哪些头和查询到达了它，因为 CLI 测试夹具无法显示请求头、重定向或子协议。 该脚本保留测试夹具的shebang（结账的`.venv`Python，其中有aiohttp），重新打包`backend/linux.tar.gz`并重写清单的`sha256`； 然后，该应用程序将被安装、启用、准备并启动。
- `S` 是入口 URL，`P` 是其端口，`REV`/`REV2` 是已批准的修订版本。

```sh
control-agent-server api GET /server_info --auth none --check capabilities contains canvas_app_backend_bridge_v1 --quiet
S=$(control-agent-server api GET /server_info --auth none --field app_backend_ingress_url)
P=${S##*:}
APP=$(control-agent-server fixture canvas-app --name qa-backend --backend ok --print-path)
control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$APP\"}" --expect 200 --check name eq qa-backend --quiet
REV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --field revision)
control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": true}' --expect 200 --quiet
control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json "{\"revision\": \"$REV\"}" --expect 200 --quiet
control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" --expect 200 --check state eq ready --quiet
HDR=$(control-agent-server fixture canvas-app --name qa-headers --backend ok --print-path)
mkdir -p "$HDR/backend/qa"
{ head -1 "$HDR/backend/src/server.py"; cat <<'PY'; } > "$HDR/backend/qa/server.py"
import sys

from aiohttp import WSMsgType, web


def seen(request):
    return {k.lower(): v for k, v in request.headers.items()}


async def health(request):
    return web.Response(text="ok")


async def redirect(request):
    raise web.HTTPFound("https://example.com/")


async def set_cookie(request):
    response = web.json_response({"set_cookie": "sent"})
    response.set_cookie("qa_upstream", "1")
    return response


async def socket(request):
    ws = web.WebSocketResponse(protocols=("qa.v1",))
    await ws.prepare(request)
    headers = seen(request)
    async for message in ws:
        if message.type == WSMsgType.TEXT:
            await ws.send_json({
                "kind": "qa_ws_echo",
                "echo": message.data,
                "protocol": ws.ws_protocol or "none",
                "cookie": "present" if "cookie" in headers else "absent",
                "origin": headers.get("origin", "absent"),
                "session_key": "present" if "x-session-api-key" in headers else "absent",
                "query": request.query_string or "none",
            })
    return ws


async def echo(request):
    return web.json_response({
        "method": request.method,
        "path": request.path,
        "query": dict(request.query),
        "headers": seen(request),
        "body": await request.text(),
    })


app = web.Application()
app.router.add_get("/health", health)
app.router.add_get("/redirect", redirect)
app.router.add_get("/set-cookie", set_cookie)
app.router.add_get("/ws", socket)
app.router.add_route("*", "/{tail:.*}", echo)
web.run_app(app, host="127.0.0.1", port=int(sys.argv[1]), print=None)
PY
chmod 755 "$HDR/backend/qa/server.py"
tar -czf "$HDR/backend/linux.tar.gz" -C "$HDR/backend/qa" server.py
sed -i "s/[0-9a-f]\{64\}/$(sha256sum "$HDR/backend/linux.tar.gz" | cut -d' ' -f1)/g" "$HDR/canvas-extension.json"
control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$HDR\"}" --expect 200 --check name eq qa-headers --quiet
REV2=$(control-agent-server api GET /api/canvas-extensions/installed/qa-headers/backend --field revision)
control-agent-server api PATCH /api/canvas-extensions/installed/qa-headers --json '{"enabled": true}' --expect 200 --quiet
control-agent-server api POST /api/canvas-extensions/installed/qa-headers/backend/prepare --json "{\"revision\": \"$REV2\"}" --expect 200 --quiet
control-agent-server api POST /api/canvas-extensions/installed/qa-headers/backend/start --json "{\"revision\": \"$REV2\"}" --expect 200 --check state eq ready --quiet
```

- **Ingress 已发布广告 (`F29.ingress-advertised`)。**运行自己的 URL 是配置的入口。
  ```sh
  RUN_URL=$(control-agent-server config | python3 -c 'import json, sys; print(json.load(sys.stdin)["url"])')
  control-agent-server api GET /server_info --auth none --expect 200 \
    --check app_backend_ingress_url eq "$RUN_URL" \
    --check capabilities contains canvas_app_backend_bridge_v1 --save F29.ingress-advertised/server-info
  ```
  `app_backend_ingress_url` 为 `http://127.0.0.1:PORT`，并列出了功能。
- ** 配置或不可用的入口 (`F29.ingress-config-errors`).** 无 `--canvas-ingress` 的第二次运行，重启时使用了两个不可用的入口值，并在子弹结束时停止。
  ```sh
  NOI=$(control-agent-server launch --new --name f29-no-ingress --print-run)
  trap 'control-agent-server stop --run "$NOI" >/dev/null' EXIT
  control-agent-server api GET /server_info --run "$NOI" --auth none --expect 200 \
    --check app_backend_ingress_url missing --check capabilities not-contains canvas_app_backend_bridge_v1
  control-agent-server api POST /app-backends/qa-backend/session --run "$NOI" --header 'Origin: http://localhost:3000' \
    --expect 503 --check exception eq '503: Canvas App backend ingress is not configured' \
    --check-header set-cookie missing --save F29.ingress-config-errors/session
  control-agent-server api DELETE /app-backends/qa-backend/session --run "$NOI" --header 'Origin: http://localhost:3000' \
    --expect 503 --check exception eq '503: Canvas App backend ingress is not configured'
  control-agent-server api GET /app-backends/qa-backend/echo --run "$NOI" --auth none --cookie oh_app_backend_session=qa-f29-any \
    --expect 503 --check exception eq '503: Canvas App backend ingress is not configured' --save F29.ingress-config-errors/proxy
  control-agent-server ws listen /app-backends/qa-backend/ws --run "$NOI" --auth none --header 'Origin: http://localhost:3000' \
    --header 'Cookie: oh_app_backend_session=qa-f29-any' --duration 5 --expect-reject 403
  control-agent-server api POST /app-backends/qa-backend/session --run "$NOI" --auth none --header 'Origin: http://localhost:3000' --expect 401
  control-agent-server restart --run "$NOI" --config-json '{"app_backend_public_url": "ftp://apps.qa.test"}'
  control-agent-server api GET /server_info --run "$NOI" --auth none --check app_backend_ingress_url eq ftp://apps.qa.test
  control-agent-server api POST /app-backends/qa-backend/session --run "$NOI" --header 'Origin: http://localhost:3000' \
    --expect 503 --check exception eq '503: Canvas App backend ingress is misconfigured' --save F29.ingress-config-errors/misconfigured
  control-agent-server api GET /app-backends/qa-backend/echo --run "$NOI" --auth none --cookie oh_app_backend_session=qa-f29-any \
    --expect 503 --check exception eq '503: Canvas App backend ingress is misconfigured'
  NOP=$(control-agent-server config --run "$NOI" | python3 -c 'import json, sys; print(json.load(sys.stdin)["url"].rsplit(":", 1)[1])')
  control-agent-server restart --run "$NOI" --config-json "{\"app_backend_public_url\": \"http://apps.qa.test:$NOP\"}"
  NAPP=$(control-agent-server fixture canvas-app --run "$NOI" --name qa-backend --backend ok --print-path)
  control-agent-server api POST /api/canvas-extensions/install --run "$NOI" --json "{\"source\": \"$NAPP\"}" --expect 200 --quiet
  NREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --run "$NOI" --field revision)
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --run "$NOI" --json '{"enabled": true}' --expect 200 --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --run "$NOI" \
    --json "{\"revision\": \"$NREV\"}" --expect 200 --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --run "$NOI" \
    --json "{\"revision\": \"$NREV\"}" --expect 200 --check state eq ready --quiet
  control-agent-server api POST /app-backends/qa-backend/session --run "$NOI" --header 'Origin: http://localhost:3000' \
    --header "Host: apps.qa.test:$NOP" --expect 503 \
    --check exception eq '503: Canvas App sessions require HTTPS or a loopback secure context' \
    --check-header set-cookie missing --save F29.ingress-config-errors/insecure-ingress
  control-agent-server api POST /app-backends/qa-backend/session --run "$NOI" --header 'Origin: http://localhost:3000' \
    --expect 421
  ```
  `/server_info`没有入口URL并且没有能力； 会话和代理路由返回 `exception` 中的原因，拒绝连接返回 403，而首先检查密钥（没有密钥时返回 401）。 使用 `ftp://` 入口重新启动后，`/server_info` 逐字通告它，并且网桥回答 503 `misconfigured`。 重新启动后
  `http://apps.qa.test:PORT`（非回环）和一个就绪的后端，一个针对该主机的 bootstrap（`Host: apps.qa.test:PORT`），通过主机、源和就绪检查，但被拒绝返回 503，因为 HTTP
  `Secure` cookie 无法通过普通 HTTP 传递到非环回主机； 运行自己的环回地址现在是错误的主机（421）。
- **会话引导程序 (`F29.session-bootstrap`).**像 Canvas 那样为每个应用程序创建一个 cookie，然后让类似浏览器的 jar 重放它。
  ```sh
  SC=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 \
    --check ingress_url eq "$S/app-backends/qa-backend/" \
    --check iframe_sandbox eq 'allow-forms allow-modals allow-popups allow-same-origin allow-scripts' \
    --check-header set-cookie matches '^oh_app_backend_session=[A-Za-z0-9_-]{20,};' \
    --check-header set-cookie contains HttpOnly --check-header set-cookie contains 'Max-Age=300;' \
    --check-header set-cookie contains 'Path=/app-backends/qa-backend;' --check-header set-cookie contains 'SameSite=none' \
    --check-header set-cookie contains Secure --check-header set-cookie contains Partitioned \
    --check-header access-control-allow-origin eq http://localhost:3000 \
    --check-header access-control-allow-credentials eq true --save F29.session-bootstrap/mint --print-header set-cookie)
  TOKEN=$(printf '%s' "$SC" | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$TOKEN"
  SC2=$(control-agent-server api POST /app-backends/qa-headers/session --header 'Origin: http://localhost:3000' --expect 200 \
    --check ingress_url eq "$S/app-backends/qa-headers/" \
    --check-header set-cookie contains 'Path=/app-backends/qa-headers;' --print-header set-cookie)
  T2=$(printf '%s' "$SC2" | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$T2" && test "$T2" != "$TOKEN"
  EXP=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --jar qa-f29 --expect 200 --field expires_at)
  LEFT=$(( $(date -d "$EXP" +%s) - $(date +%s) ))
  test "$LEFT" -ge 290 && test "$LEFT" -le 300
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --jar qa-f29 --expect 200 \
    --check app eq qa-backend --save F29.session-bootstrap/jar-replay
  PRE=$(curl -s -D - -o /dev/null --noproxy '*' -X OPTIONS -H 'Origin: http://localhost:3000' \
    -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: x-session-api-key' \
    "$S/app-backends/qa-backend/session")
  grep -q '^HTTP/1.1 200' <<<"$PRE"
  grep -qi '^access-control-allow-origin: http://localhost:3000' <<<"$PRE"
  grep -qi '^access-control-allow-credentials: true' <<<"$PRE"
  grep -qi '^access-control-allow-headers: .*x-session-api-key' <<<"$PRE"
  ```
  每个应用在其自己的路径上都有自己的 cookie。 `expires_at` 比实际时间快了300秒，一个只装了刚 minted 的饼干（没有钥匙）的罐子到达后端。 浏览器的 CORS 预检请求，用于 bootstrap（跨源）
  `POST` 和 `X-Session-API-Key`) 允许作为具有凭据的控制原点； 它通过 `curl` 因为 `map check` 不接受
  `api OPTIONS` 在这些路线上。
- **需要会话密钥 (`F29.session-key-required`)。**引导程序仅采用控制标头。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 \
    --check-header set-cookie contains oh_app_backend_session=
  control-agent-server api POST /app-backends/qa-backend/session --auth none --header 'Origin: http://localhost:3000' \
    --expect 401 --check detail eq Unauthorized --check-header set-cookie missing --save F29.session-key-required/no-key
  control-agent-server api POST /app-backends/qa-backend/session --auth bad --header 'Origin: http://localhost:3000' \
    --expect 401 --check-header set-cookie missing --save F29.session-key-required/bad-key
  control-agent-server api POST /app-backends/qa-backend/session --auth bearer --header 'Origin: http://localhost:3000' \
    --expect 401 --check-header set-cookie missing
  control-agent-server api POST /app-backends/qa-backend/session --auth none --header 'Origin: http://localhost:3000' \
    --cookie "oh_app_backend_session=$TOKEN" --expect 401 --check-header set-cookie missing
  ```
  运行的密钥生成了一个 cookie。 没有密钥，错误密钥，密钥作为持有者令牌，以及一个应用会话 cookie，每个密钥都会返回401并设置无 cookie。
- **入口主机(`F29.session-ingress-host`)。**引导程序和代理必须到达入口主机。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --header "Host: localhost:$P" \
    --expect 421 --check detail eq 'Canvas App request must use the configured ingress origin' \
    --check-header set-cookie missing --save F29.session-ingress-host/session
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --header "Host: localhost:$P" \
    --header "X-Forwarded-Host: 127.0.0.1:$P" --expect 421 --save F29.session-ingress-host/forwarded-host
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header 'Host: other.qa.test:1' --expect 421 --save F29.session-ingress-host/proxy
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --expect 200 --check app eq qa-backend
  ```
  `localhost:PORT` 是同一台服务器，但不是入口源，因此两条路由都回答 421，并且 `X-Forwarded-Host` 命名入口没有帮助； 入口主机上的相同 cookie 得到 200。
- **转发的原型 (`F29.session-forwarded-proto`).**与
  `trust_forwarded_headers` 关闭（默认），请求自己的方案决定来源（`bridge.py` `_request_origin`，`config.py`），因此客户端提供的 `X-Forwarded-Proto: https` 不会更改它。
  ```sh
  FP=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 \
    --check ingress_url eq "$S/app-backends/qa-backend/" --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$FP"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$FP" --expect 200 \
    --check app eq qa-backend
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --header 'X-Forwarded-Proto: https' --expect 200 --check ingress_url eq "$S/app-backends/qa-backend/" \
    --save F29.session-forwarded-proto/session
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$FP" \
    --header 'X-Forwarded-Proto: https' --expect 200 --check app eq qa-backend --save F29.session-forwarded-proto/proxy
  ```
  相同的 bootstrap 和 proxied GET 在没有头信息的情况下，首先返回 200，同时在头信息中返回：服务器启动 uvicorn
  `proxy_headers` 仅当 `trust_forwarded_headers` 打开时 (`__main__.py`)，因此 uvicorn 不会在设置背后为环回对等点 (`FORWARDED_ALLOW_IPS`) 重写 `X-Forwarded-Proto` 中的方案。
- **起源规则(`F29.session-origin-rules`).**只有控制源可以引导，并且它必须与入口源不同。
  ```sh
  control-agent-server api POST /app-backends/qa-backend/session --expect 403 --check detail eq 'Origin is not allowed' \
    --check-header set-cookie missing --save F29.session-origin-rules/no-origin
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: https://evil.qa.test' --expect 403 \
    --check detail eq 'Origin is not allowed' --check-header set-cookie missing --save F29.session-origin-rules/foreign
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: null' --expect 403 --check-header set-cookie missing
  control-agent-server api POST /app-backends/qa-backend/session --header "Origin: $S" --expect 409 \
    --check detail eq 'Canvas App ingress must use a separate browser origin' \
    --check-header set-cookie missing --save F29.session-origin-rules/ingress-origin
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://127.0.0.1:5173' --expect 200 \
    --check-header set-cookie contains oh_app_backend_session=
  ```
  403 对于非欧洲和 `null` 原产地，409 对于入口原产地；没有 cookie。 又接受了一个环回端口。
- **后端未准备好(`F29.session-backend-not-ready`)。**没有运行后端且名称格式错误的应用程序。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api POST /app-backends/qa-nope/session --header 'Origin: http://localhost:3000' --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --check-header set-cookie missing \
    --save F29.session-backend-not-ready/session
  control-agent-server api GET /app-backends/qa-nope/echo --auth none --cookie "oh_app_backend_session=$TOKEN" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --save F29.session-backend-not-ready/proxy
  control-agent-server api POST /app-backends/QA_Bad/session --header 'Origin: http://localhost:3000' --expect 422 \
    --check detail.0.loc.1 eq extension_name
  control-agent-server api GET /app-backends/QA_Bad/echo --auth none --expect 422 --check detail.0.loc.1 eq extension_name
  ```
  一个未知的应用看起来像一个停止的应用（503，没有404）。 `^[a-z0-9]+(?:-[a-z0-9]+)*$`之外的名字是422。 已停止安装的后端被 `F29.backend-lifecycle-revokes` 覆盖。
- **代理安全方法 (`F29.proxy-get`)。**只有 cookie，没有密钥。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --query view=main --expect 200 --check app eq qa-backend --check method eq GET --check path eq /echo \
    --check query.view eq main --check cookie_forwarded eq false --save F29.proxy-get/get
  control-agent-server api GET /app-backends/qa-backend/assets/app.js --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --expect 200 --check path eq /assets/app.js
  test "$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' -I -H "Cookie: oh_app_backend_session=$TOKEN" "$S/app-backends/qa-backend/echo")" = 200
  OPT=$(curl -s --noproxy '*' -X OPTIONS -H "Cookie: oh_app_backend_session=$TOKEN" "$S/app-backends/qa-backend/echo")
  grep -q '"method": "OPTIONS"' <<<"$OPT"
  test "$(curl -s --noproxy '*' -X OPTIONS -H "Cookie: oh_app_backend_session=$TOKEN" -H "Origin: $S" \
    -H 'Access-Control-Request-Method: POST' "$S/app-backends/qa-backend/echo")" = OK
  control-agent-server api GET /app-backends/qa-backend/session --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --expect 200 --check path eq /session
  ```
  后端看到方法、子路径和查询，没有会话 cookie。 HEAD 答案为 200，并且是一个简单的 OPTIONS （不是） CORS preflight) 路径到达后端，而另一个 CORS preflight (with
  `Access-Control-Request-Method`) 由服务器的 CORS 中间件用普通的 `OK` 应答，并且永远不会到达后端。 HEAD 和 OPTIONS 遍历 `curl` 因为
  `map check` 的路由表仅列出了这些路由的五种方法 FastAPI 报告。 `/session`上只有POST和DELETE是桥自己的路线； `GET /session` 是后端的。
- **需要 Cookie (`F29.proxy-cookie-required`)。** cookie 是代理获取的唯一凭据，并且它绑定到一个应用程序。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --expect 401 --check detail eq Unauthorized \
    --save F29.proxy-cookie-required/none
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie oh_app_backend_session=qa-f29-bogus --expect 401
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$T2" --expect 401 \
    --save F29.proxy-cookie-required/other-app
  control-agent-server api GET /app-backends/qa-backend/echo --expect 401 --save F29.proxy-cookie-required/key-only
  control-agent-server api GET /app-backends/qa-headers/echo --auth none --cookie "oh_app_backend_session=$T2" --expect 200 \
    --check path eq /echo
  ```
  401 无cookie，有假cookie，有`qa-headers`的cookie
  `qa-backend`，并且只有 `X-Session-API-Key`； 该 cookie 在其自己的应用程序上运行。
- **不安全的方法 (`F29.proxy-unsafe-methods`).**入口 `Origin` 是除 GET、HEAD 和 OPTIONS 之外的任何东西的 CSRF 守卫。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"qa": "f29"}' --expect 200 --check method eq POST --check path eq /echo \
    --check body eq '{"qa":"f29"}' --save F29.proxy-unsafe-methods/post
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --json '{"qa": "f29"}' --expect 403 --check detail eq 'Origin is not allowed'
  control-agent-server api PUT /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"qa": "f29"}' --expect 200 --check method eq PUT --check path eq /echo \
    --check body eq '{"qa":"f29"}' --save F29.proxy-unsafe-methods/put
  control-agent-server api PUT /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --json '{"qa": "f29"}' --expect 403 --check detail eq 'Origin is not allowed'
  control-agent-server api PATCH /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"qa": "f29"}' --expect 200 --check method eq PATCH --check path eq /echo \
    --check body eq '{"qa":"f29"}' --save F29.proxy-unsafe-methods/patch
  control-agent-server api PATCH /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --json '{"qa": "f29"}' --expect 403 --check detail eq 'Origin is not allowed'
  control-agent-server api DELETE /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"qa": "f29"}' --expect 200 --check method eq DELETE --check path eq /echo \
    --check body eq '{"qa":"f29"}' --save F29.proxy-unsafe-methods/delete
  control-agent-server api DELETE /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --json '{"qa": "f29"}' --expect 403 --check detail eq 'Origin is not allowed'
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header 'Origin: http://localhost:3000' --expect 403 --save F29.proxy-unsafe-methods/control-origin
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --cookie oh_app_backend_session=qa-f29-bogus \
    --expect 403
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --header "Origin: $S" --expect 401
  ```
  每个方法都以 JSON 的体态到达后端。 如果没有`Origin`，或者使用Canvas控件的起源，它会返回403，而这个检查在cookie检查之前运行（一个无效的cookie和没有`Origin`，返回403，而不是401）。
- **应用程序根目录 (`F29.proxy-root`)。**没有子路径的路由。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api GET /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" --expect 200 \
    --check method eq GET --check path eq / --save F29.proxy-root/get
  control-agent-server api GET /app-backends/qa-backend/ --auth none --cookie "oh_app_backend_session=$TOKEN" --expect 200 \
    --check path eq /
  control-agent-server api GET /app-backends/qa-backend/ --query path=echo --auth none \
    --cookie "oh_app_backend_session=$TOKEN" --expect 200 --check path eq / --check query.path eq echo \
    --save F29.proxy-root/slash-path-query
  control-agent-server api POST /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"root": 1}' --expect 200 --check method eq POST --check path eq / \
    --save F29.proxy-root/post
  control-agent-server api PUT /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"root": 1}' --expect 200 --check method eq PUT --check path eq / \
    --save F29.proxy-root/put
  control-agent-server api PATCH /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"root": 1}' --expect 200 --check method eq PATCH --check path eq / \
    --save F29.proxy-root/patch
  control-agent-server api DELETE /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --header "Origin: $S" --json '{"root": 1}' --expect 200 --check method eq DELETE --check path eq / \
    --save F29.proxy-root/delete
  control-agent-server api POST /app-backends/qa-backend --auth none --cookie "oh_app_backend_session=$TOKEN" --expect 403
  control-agent-server api GET /app-backends/qa-backend --auth none --expect 401
  ```
  所有五种方法都达到b`/`； 相同的 `Origin` 和 cookie 规则适用。 开
  `/app-backends/qa-backend/`（形式`ingress_url`使用）`path`查询参数是后端`/`的普通参数。
- **根 `path` 参数 (`F29.proxy-root-path-query`).** 裸根路由没有 `{path}` 分段并忽略 `path` argument, so a `path` 查询参数是一个后端的普通参数 `/`.
  ```sh
  RP=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$RP"
  control-agent-server api GET /app-backends/qa-backend --query view=main --auth none \
    --cookie "oh_app_backend_session=$RP" --expect 200 --check path eq / --check query.view eq main
  control-agent-server api GET /app-backends/qa-backend/ --query path=echo --auth none \
    --cookie "oh_app_backend_session=$RP" --expect 200 --check path eq / --check query.path eq echo
  control-agent-server api GET /app-backends/qa-backend --query path=echo --auth none \
    --cookie "oh_app_backend_session=$RP" --expect 200 --check path eq / --check query.path eq echo \
    --save F29.proxy-root-path-query/get
  control-agent-server api GET /app-backends/qa-backend --query 'path=..' --auth none \
    --cookie "oh_app_backend_session=$RP" --expect 200 --check path eq / --check query.path eq ..
  control-agent-server ws listen /app-backends/qa-backend --query path=ws --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$RP" --send qa-f29-root --duration 5 --expect-close 1011 --expect-frames 0
  ```
  首先：裸根，另一个查询参数；末尾斜杠根，`?path=echo`；两者都以完整查询参数到达`/`。 裸根也这样做：`?path=echo` 和 `?path=..` 通过查询参数到达后端的 `/`，而根 WebSocket 也这样做
  `?path=ws` 的目标是 `/`，因此它以 1011 关闭并且没有框架，就像任何根 WebSocket (`F29.ws-bridge`) 一样，而不是到达后端的 `/ws`。
- **凭据已删除 (`F29.proxy-credentials-stripped`).** `qa-headers` 回显它收到的每个标头。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api POST /app-backends/qa-headers/echo --cookie "oh_app_backend_session=$T2; qa_other=1" \
    --header "Origin: $S" --header 'Authorization: Bearer qa-f29-bearer' --header 'X-QA-Custom: kept' \
    --query view=main --query session_api_key=qa-leak --query X-Session-API-Key=qa-leak --query Authorization=qa-leak \
    --json '{"qa": "body"}' --expect 200 \
    --check headers.cookie missing --check headers.authorization missing --check headers.x-session-api-key missing \
    --check headers.x-qa-custom eq kept --check headers.origin eq "$S" --check query.view eq main \
    --check query.session_api_key missing --check query.X-Session-API-Key missing --check query.Authorization missing \
    --check body eq '{"qa":"body"}' --save F29.proxy-credentials-stripped/echo
  ```
  请求携带了 cookie，run 的 `X-Session-API-Key`, a 持有者令牌以及三个带有名称的关键查询参数。 后端看到 None 他们之中，但确实看到了 `X-QA-Custom`, `Origin`, `view` and the body.
- **请求帧 (`F29.proxy-request-framing`)。** `qa-headers` 回显它收到的帧头； 直接调用其环回端口是控制。
  ```sh
  FR=$(control-agent-server api POST /app-backends/qa-headers/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$FR"
  HPORT=$(control-agent-server api GET /api/canvas-extensions/installed/qa-headers/backend --field port)
  DIRECT_GET=$(curl -s --noproxy '*' "http://127.0.0.1:$HPORT/echo")
  grep -q '"method": "GET"' <<<"$DIRECT_GET"
  if grep -qi '"transfer-encoding"' <<<"$DIRECT_GET"; then false; fi
  DIRECT_POST=$(curl -s --noproxy '*' -H 'Content-Type: application/json' --data '{"qa":"body"}' "http://127.0.0.1:$HPORT/echo")
  grep -q '"content-length": "13"' <<<"$DIRECT_POST"
  if grep -qi '"transfer-encoding"' <<<"$DIRECT_POST"; then false; fi
  control-agent-server api GET /app-backends/qa-headers/echo --auth none --cookie "oh_app_backend_session=$FR" --expect 200 \
    --check method eq GET --check body eq '' --check headers.transfer-encoding missing \
    --save F29.proxy-request-framing/get
  control-agent-server api POST /app-backends/qa-headers/echo --auth none --cookie "oh_app_backend_session=$FR" \
    --header "Origin: $S" --json '{"qa": "body"}' --expect 200 --check body eq '{"qa":"body"}' \
    --check headers.content-length eq 13 --check headers.transfer-encoding missing \
    --save F29.proxy-request-framing/post
  ```
  直接，后端看不到 `Transfer-Encoding` 在 GET 上
  POST 上的 `Content-Length: 13`； 穿过桥，看到的都是一样的。
  `proxy_http` (`docker_runtime/proxy.py`）客户端发送了请求体，但服务器端没有发送任何内容 `Content-Length` nor `Transfer-Encoding`重新添加客户端的 `Content-Length` while still 流式传输 body，然后发送一个chunked客户端body chunked，因此服务器上的后端处理 chunked客户端body chunked 只读
  `Content-Length`（Python的`http.server`）也获得主体。
- **响应过滤器(`F29.proxy-response-filter`)。**直接调用后端的环回端口是控制。

  需要：`F29.session-bootstrap`
  ```sh
  HPORT=$(control-agent-server api GET /api/canvas-extensions/installed/qa-headers/backend --field port)
  test "$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' "http://127.0.0.1:$HPORT/redirect")" = 302
  control-agent-server api GET /app-backends/qa-headers/redirect --auth none --cookie "oh_app_backend_session=$T2" \
    --expect 502 --check exception eq '502: Upstream redirect is not allowed' --check-header location missing \
    --save F29.proxy-response-filter/redirect
  DIRECT=$(curl -s -D - -o /dev/null --noproxy '*' "http://127.0.0.1:$HPORT/set-cookie")
  grep -qi '^set-cookie: qa_upstream=1' <<<"$DIRECT"
  control-agent-server api GET /app-backends/qa-headers/set-cookie --auth none --cookie "oh_app_backend_session=$T2" \
    --expect 200 --check set_cookie eq sent --check-header set-cookie missing --save F29.proxy-response-filter/set-cookie
  ```
  后端返回302，并设置`qa_upstream`。 通过桥，重定向为502，没有`Location`，而体没有cookie。
- **一个日期头和服务器头 (`F29.proxy-response-headers`).** 代理会丢弃后端的 `Date` 和 `Server` 头，因为 uvicorn 会添加自己的，所以代理响应中只携带一个。
  ```sh
  control-agent-server api GET /server_info --auth none --expect 200 \
    --check-header date matches '^[A-Z][a-z]{2}, [0-9]{2} [A-Z][a-z]{2} [0-9]{4} [0-9:]{8} GMT$' --check-header server eq uvicorn
  BPORT=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --field port)
  DIRECT_HEADERS=$(curl -s -D - -o /dev/null --noproxy '*' "http://127.0.0.1:$BPORT/echo")
  test "$(grep -ci '^date:' <<<"$DIRECT_HEADERS")" = 1 && test "$(grep -ci '^server:' <<<"$DIRECT_HEADERS")" = 1
  RH=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$RH"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RH" --expect 200 \
    --check-header date matches '^[A-Z][a-z]{2}, [0-9]{2} [A-Z][a-z]{2} [0-9]{4} [0-9:]{8} GMT$' \
    --check-header server not-contains ', ' --all-headers --save F29.proxy-response-headers/echo
  ```
  控件：服务器回答一个 `Date`
  `server: uvicorn`，后端应答直接各发一份。 通过桥接器，响应携带 `Date` 和 `server: uvicorn`
  太：没有 `date: <uvicorn's>, <aiohttp's>`（RFC 9110 允许单个 `Date`）
  并且没有 `Python/3.x aiohttp/3.x` 公开后端堆栈。
- **路径遍历(`F29.proxy-path-traversal`)。**首先检查，所以不需要凭据来查看它。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server api GET '/app-backends/qa-backend/%2e%2e/secret' --auth none --expect 400 \
    --check detail eq 'Invalid backend path' --save F29.proxy-path-traversal/dotdot
  control-agent-server api GET '/app-backends/qa-backend/%252e%252e/secret' --auth none --expect 400 \
    --save F29.proxy-path-traversal/double-encoded
  control-agent-server api GET '/app-backends/qa-backend/%25252e%25252e/secret' --auth none --expect 400
  control-agent-server api GET '/app-backends/qa-backend/a%5cb' --auth none --expect 400
  control-agent-server api GET '/app-backends/qa-backend/%2e/x' --auth none --expect 400
  control-agent-server api POST '/app-backends/qa-backend/%2e%2e/x' --auth none --expect 400
  control-agent-server ws listen '/app-backends/qa-backend/%2e%2e/ws' --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$TOKEN" --duration 5 --expect-reject 403
  control-agent-server api GET '/app-backends/qa-backend/app%2Ejs' --auth none --cookie "oh_app_backend_session=$TOKEN" \
    --expect 200 --check path eq /app.js
  ```
  拒绝 `..`、`.` 和反斜杠在每个编码深度（400 在 HTTP，403 非法握手在 WebSocket）。 名称内的编码点被转发。
- **WebSocket 桥 (`F29.ws-bridge`).**握手时的 Cookie 和 ingress `Origin`。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$TOKEN" --send qa-f29-hello --until-kind str --until .=echo:qa-f29-hello \
    --duration 10 --save F29.ws-bridge/echo
  control-agent-server ws listen /app-backends/qa-headers/ws --auth header --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$T2; qa_other=1" --query view=main --query session_api_key=qa-leak \
    --send qa-f29-headers --until-kind qa_ws_echo --until echo=qa-f29-headers --until cookie=absent \
    --until origin=absent --until session_key=absent --until query=view=main --duration 10 --save F29.ws-bridge/headers
  control-agent-server ws listen /app-backends/qa-backend --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$TOKEN" --send qa-f29-root --duration 10 --expect-close 1011 \
    --expect-frames 0 --save F29.ws-bridge/root-refused
  control-agent-server ws listen /app-backends/qa-backend/no-socket-here --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$TOKEN" --duration 10 --expect-close 1011 --expect-frames 0
  ```
  `qa-backend` 答案 `echo:qa-f29-hello`； `qa-headers`报告说它的握手没有携带cookie，没有`Origin`，没有`X-Session-API-Key`并且只携带
  `view=main` as the query. 根路由 `/app-backends/qa-backend` 针对后端的 `/`, which is plain HTTP握手成功（桥接在拨号之前接受），则套接字以1011关闭，并无帧，就像后端没有升级的子路径一样。
- **握手拒绝 (`F29.ws-handshake-rejections`)。**每个在接受之前都被拒绝（服务器关闭 1008，客户端将其视为 HTTP 403）。

  需要：`F29.session-bootstrap`
  ```sh
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Cookie: oh_app_backend_session=$TOKEN" \
    --duration 5 --expect-reject 403 --save F29.ws-handshake-rejections/no-origin
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header 'Origin: http://localhost:3000' \
    --header "Cookie: oh_app_backend_session=$TOKEN" --duration 5 --expect-reject 403 --save F29.ws-handshake-rejections/control-origin
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" --duration 5 --expect-reject 403
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" \
    --header 'Cookie: oh_app_backend_session=qa-f29-bogus' --duration 5 --expect-reject 403
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$T2" --duration 5 --expect-reject 403 --save F29.ws-handshake-rejections/other-app
  control-agent-server ws listen /app-backends/qa-backend/ws --auth header --header "Origin: $S" --duration 5 --expect-reject 403
  control-agent-server ws listen /app-backends/qa-backend/ws --auth query --header "Origin: $S" --duration 5 --expect-reject 403
  ```
  403 无 `Origin`，控制源，无 cookie，有假的或另一个应用的 cookie，仅凭会话密钥（头或查询）。 接受的手势在上一个列表项中。
- **子协议 (`F29.ws-subprotocol`)，已知错误。** `qa-headers`' `/ws` 当客户提出要求时进行谈判 `qa.v1`； 直接连接就是控制。 双方都使用支持子协议的客户端（`websockets`
  `subprotocols=[...]`），因为 `ws listen --header 'Sec-WebSocket-Protocol: ...'` 拒绝服务器选择的任何子协议，因此永远看不到修复。
  ```sh
  SP=$(control-agent-server api POST /app-backends/qa-headers/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$SP"
  HPORT=$(control-agent-server api GET /api/canvas-extensions/installed/qa-headers/backend --field port)
  control-agent-server exec --expect-output 'subprotocol=qa.v1' -- "$PWD/.venv/bin/python" -c \
    'import sys; from websockets.sync.client import connect; ws = connect(sys.argv[1], subprotocols=["qa.v1"], proxy=None); print("subprotocol=" + str(ws.subprotocol)); ws.close()' \
    "ws://127.0.0.1:$HPORT/ws"
  control-agent-server exec --expect-output 'subprotocol=None' --expect-output '"echo": "qa-f29-plain"' -- "$PWD/.venv/bin/python" -c \
    'import sys; from websockets.sync.client import connect; ws = connect(sys.argv[1], origin=sys.argv[2], additional_headers={"Cookie": "oh_app_backend_session=" + sys.argv[3]}, proxy=None); print("subprotocol=" + str(ws.subprotocol)); ws.send("qa-f29-plain"); print(ws.recv(timeout=10)); ws.close()' \
    "ws://127.0.0.1:$P/app-backends/qa-headers/ws" "$S" "$SP"
  control-agent-server exec --expect-output 'subprotocol=qa.v1' --expect-output '"protocol": "qa.v1"' \
    --save F29.ws-subprotocol/bridged -- "$PWD/.venv/bin/python" -c \
    'import sys; from websockets.sync.client import connect; ws = connect(sys.argv[1], subprotocols=["qa.v1"], origin=sys.argv[2], additional_headers={"Cookie": "oh_app_backend_session=" + sys.argv[3]}, proxy=None); print("subprotocol=" + str(ws.subprotocol)); ws.send("qa-f29-proto"); print(ws.recv(timeout=10)); ws.close()' \
    "ws://127.0.0.1:$P/app-backends/qa-headers/ws" "$S" "$SP"  # bug: stdout_tail 包含 subprotocol=None && stdout_tail 包含 '"protocol": "None"'
  ```
  控件：直接，后端协商 `qa.v1`。 通过这座桥，同一个客户端，没有子协议，会收到一个新的cookie的回声。 预期：桥梁协商 `qa.v1`，后端报告
  `protocol: qa.v1`，就像直接做的那样。 实际：`subprotocol=None` 和
  `protocol: none`（回显帧仍然到达）； 网桥在接受时既不会向上游转发 `Sec-WebSocket-Protocol`，也不会选择其中之一。 浏览器无法完成这种握手（Chrome：「发送了非空的「Sec-WebSocket-Protocol」头部，但没有收到响应」），因此需要子协议的客户端（如 graphql-ws、许多终端协议）无法通过桥接连接。
- **撤销会话 (`F29.session-revoke`)。**一个应用程序的两个会话； 其中一个打开了桥接套接字。
  ```sh
  RA=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  RB=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$RA" && test -n "$RB"
  control-agent-server ws start /app-backends/qa-backend/ws --name f29-revoke --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$RA" --send qa-f29-before-revoke --duration 120
  control-agent-server ws read f29-revoke --contains echo:qa-f29-before-revoke --wait 10 --expect-open
  control-agent-server api DELETE /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --cookie "oh_app_backend_session=$RA" --expect 204 --check-header set-cookie contains 'oh_app_backend_session=""' \
    --check-header set-cookie contains 'Max-Age=0;' --check-header set-cookie contains 'Path=/app-backends/qa-backend;' \
    --save F29.session-revoke/delete
  control-agent-server ws stop f29-revoke --wait 10 --expect-close 1000 --save F29.session-revoke/socket-closed
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RA" --expect 401 \
    --save F29.session-revoke/revoked-cookie
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$RA" --duration 5 --expect-reject 403
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RB" --expect 200 \
    --check app eq qa-backend
  control-agent-server api DELETE /app-backends/qa-backend/session --auth none --header 'Origin: http://localhost:3000' \
    --cookie "oh_app_backend_session=$RB" --expect 401
  control-agent-server api DELETE /app-backends/qa-backend/session --header 'Origin: https://evil.qa.test' \
    --cookie "oh_app_backend_session=$RB" --expect 403
  control-agent-server api DELETE /app-backends/qa-backend/session --header "Origin: $S" \
    --cookie "oh_app_backend_session=$RB" --expect 409
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RB" --expect 200
  control-agent-server api DELETE /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 204 \
    --check-header set-cookie contains 'Max-Age=0;'
  ```
  撤销的 cookie 的套接字关闭（1000），并发送 401 和 403 响应。 第二个会话仍然有效，甚至在  DELETEs 缺少密钥（401）、外来来源（403）和入站来源（409）。 A DELETE 没有 cookie 仍然回答 204 并清除 cookie。
- **后端停止并禁用撤销(`F29.backend-lifecycle-revokes`)。** F28 的生命周期路线，通过桥梁看到。
  ```sh
  LC=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$LC"
  PORT1=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --field port)
  control-agent-server ws start /app-backends/qa-backend/ws --name f29-stop --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$LC" --send qa-f29-before-stop --duration 120
  control-agent-server ws read f29-stop --contains echo:qa-f29-before-stop --wait 10 --expect-open
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/stop --expect 200 --check state eq stopped
  control-agent-server ws stop f29-stop --wait 10 --expect-close 1000 --save F29.backend-lifecycle-revokes/stop-socket
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LC" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --save F29.backend-lifecycle-revokes/stopped-proxy
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --check-header set-cookie missing
  control-agent-server ws listen /app-backends/qa-backend/ws --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$LC" --duration 5 --expect-reject 403
  control-agent-server api DELETE /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --cookie "oh_app_backend_session=$LC" --expect 204
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready --check port ne "$PORT1"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LC" --expect 401 \
    --save F29.backend-lifecycle-revokes/after-restart
  LD=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  control-agent-server ws start /app-backends/qa-backend/ws --name f29-disable --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$LD" --send qa-f29-before-disable --duration 120
  control-agent-server ws read f29-disable --contains echo:qa-f29-before-disable --wait 10 --expect-open
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": false}' --expect 200 \
    --check enabled eq false
  control-agent-server ws stop f29-disable --wait 10 --expect-close 1000 --save F29.backend-lifecycle-revokes/disable-socket
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LD" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --save F29.backend-lifecycle-revokes/disabled-proxy
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state eq stopped
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": true}' --expect 200
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LD" --expect 401
  LE=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LE" --expect 200 \
    --check app eq qa-backend
  CRASH_PID=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --field pid)
  kill -TERM "$CRASH_PID"
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --until-ok 15 --expect 200 \
    --check state eq unhealthy --check detail contains 'exited' --check pid missing --save F29.backend-lifecycle-revokes/crash-status
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LE" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --save F29.backend-lifecycle-revokes/after-poll
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --check-header set-cookie missing
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LE" --expect 401 \
    --save F29.backend-lifecycle-revokes/crash-restart-old-cookie
  LF=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$LF" --expect 200 \
    --check app eq qa-backend
  ```
  停止并关闭每个已打开的套接字（1000），并将桥接设置为503（DELETE会继续回答204）。 在新的端口上重新启动后端，旧的 cookie 会返回 401，并且新的会话可以正常工作。 `unhealthy`（`Backend exited with code ...`，没有`pid`）报告了杀掉准备就绪后端进程（崩溃）的行为，之后桥接会用503响应旧的cookie和新的bootstrap。 崩溃无损，`LE` 仍然是一个活跃会话。 只有在后端重启后，它才会收到401，因为会话绑定到后端的端口，而一个新的会话是有效的。 桥在崩溃和那个调查之间回答的是 `F29.backend-crash-detected`。 后端端口已启用并就绪。
- **桥上看到的事故(`F29.backend-crash-detected`)。**同样的崩溃，但没有人在下一个代理请求之前轮询后端的状态。
  ```sh
  CC=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$CC"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$CC" --expect 200 \
    --check app eq qa-backend
  CRASH_PID=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state eq ready --field pid)
  kill -TERM "$CRASH_PID"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$CC" --until-ok 15 \
    --expect 503 --check exception eq '503: Canvas App backend is not ready' --save F29.backend-crash-detected/crashed
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state ne ready
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready
  ```
  这个cookie会一直有效到被杀掉。 在进程退出几秒钟后，桥接器返回503 `Canvas App backend is not ready`，就像任何不运行的后端一样：`ready_endpoint` `canvas_extensions/backend.py` 检查进程是否仍然存活，而不是仅仅存储 `ready` 状态。 存储状态会持续`ready`直到下一个F28状态报告`unhealthy`并重新捕获进程组(`F29.backend-lifecycle-revokes`)。 然后子弹启动后端，所以它被禁用并准备好。
- **配置的控制源(`F29.session-configured-control-origin`)。**托管 Canvas 在其自己的源上运行，运营商将其列出在
  `allow_cors_origins` 或与 `allow_cors_origin_regex` 匹配； Docker 中的 Canvas 从 `DOCKER_HOST_ADDR` 到达服务器。 桥接器使用自己的代码检查这些，因此子弹驱动引导程序及其 CORS 预检。 重新启动会停止后端，因此子弹会再次启动它们，并在结束之前清除设置。
  ```sh
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: https://qa-f29.example' --expect 403 \
    --check detail eq 'Origin is not allowed' --check-header set-cookie missing
  control-agent-server restart --config-json '{"allow_cors_origins": ["https://qa-f29.example"], "allow_cors_origin_regex": "https://[a-z]+\\.qa-f29re\\.example"}' \
    --env DOCKER_HOST_ADDR=10.254.0.9
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready --quiet
  CO=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: https://qa-f29.example' --expect 200 \
    --check ingress_url eq "$S/app-backends/qa-backend/" --check-header access-control-allow-origin eq https://qa-f29.example \
    --check-header access-control-allow-credentials eq true --save F29.session-configured-control-origin/listed \
    --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$CO"
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: https://app.qa-f29re.example' --expect 200 \
    --check-header set-cookie contains oh_app_backend_session= \
    --check-header access-control-allow-origin eq https://app.qa-f29re.example --save F29.session-configured-control-origin/regex
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://10.254.0.9:3000' --expect 200 \
    --check-header set-cookie contains oh_app_backend_session= \
    --check-header access-control-allow-origin eq http://10.254.0.9:3000 --save F29.session-configured-control-origin/docker-host
  for ORIGIN in https://qa-f29.example https://app.qa-f29re.example http://10.254.0.9:3000; do
    PRE=$(curl -s -D - -o /dev/null --noproxy '*' -X OPTIONS -H "Origin: $ORIGIN" -H 'Access-Control-Request-Method: POST' \
      -H 'Access-Control-Request-Headers: x-session-api-key' "$S/app-backends/qa-backend/session")
    grep -q '^HTTP/1.1 200' <<<"$PRE"
    grep -qi "^access-control-allow-origin: $ORIGIN" <<<"$PRE"
  done
  for ORIGIN in https://evil.qa.test https://qa-f29.example:8443 http://qa-f29.example https://app.qa-f29re.example.evil.test \
    https://qa-f29re.example http://10.254.0.90:3000; do
    control-agent-server api POST /app-backends/qa-backend/session --header "Origin: $ORIGIN" --expect 403 \
      --check detail eq 'Origin is not allowed' --check-header set-cookie missing --quiet
  done
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$CO" --expect 200 \
    --check app eq qa-backend
  control-agent-server api POST /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$CO" \
    --header 'Origin: https://qa-f29.example' --json '{"qa": "f29"}' --expect 403 --check detail eq 'Origin is not allowed' \
    --save F29.session-configured-control-origin/not-app-origin
  control-agent-server api DELETE /app-backends/qa-backend/session --header 'Origin: https://app.qa-f29re.example' \
    --cookie "oh_app_backend_session=$CO" --expect 204 --check-header set-cookie contains 'Max-Age=0;'
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$CO" --expect 401
  control-agent-server restart --config-json '{"allow_cors_origins": [], "allow_cors_origin_regex": null}' --env DOCKER_HOST_ADDR=
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-headers/backend/start --json "{\"revision\": \"$REV2\"}" \
    --expect 200 --check state eq ready --quiet
  for ORIGIN in https://qa-f29.example https://app.qa-f29re.example http://10.254.0.9:3000; do
    control-agent-server api POST /app-backends/qa-backend/session --header "Origin: $ORIGIN" --expect 403 \
      --check-header set-cookie missing --quiet
  done
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 \
    --check-header set-cookie contains oh_app_backend_session= --save F29.session-configured-control-origin/cleared
  ```
  在重启之前，托管的起源被拒绝（403）。 在这些设置下，列出的来源、完整的正则表达式匹配，以及 Docker 每个 mint 生成一个 host address (任何端口)，并生成一个 cookie CORS  中间件允许每个的预检操作凭据。 列出的主机使用其他端口，或位于
  `http`，带有后缀的正则表达式匹配，正则表达式的裸域和另一个地址被拒绝，返回 403，并且没有 cookie。 生成的 cookie 到达 GET 上的后端，但控制源不是入口源，因此使用它的不安全代理方法仍然是 403； 来自另一个配置的源的 DELETE 撤销会话。 清除设置后（`DOCKER_HOST_ADDR` 设置为空），三个来源将再次被拒绝，并且
  `localhost` 仍然有效。 两个后端都已准备就绪。
- **可信转发标头 (`F29.trusted-forwarded-headers`)。**在 `trust_forwarded_headers` 开启的情况下重新启动，就像在 TLS 终止代理后面一样，然后退出。 重新启动会停止后端，因此子弹会再次启动它们。
  ```sh
  control-agent-server restart --config-json '{"trust_forwarded_headers": true}'
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready --quiet
  FH=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --header "Host: localhost:$P" --header "X-Forwarded-Host: 127.0.0.1:$P" --expect 200 \
    --check ingress_url eq "$S/app-backends/qa-backend/" --check-header set-cookie contains Secure \
    --save F29.trusted-forwarded-headers/session --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$FH"
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$FH" \
    --header "Host: localhost:$P" --header "X-Forwarded-Host: 127.0.0.1:$P" --expect 200 --check path eq /echo \
    --save F29.trusted-forwarded-headers/proxy
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$FH" \
    --header "Host: localhost:$P" --expect 421
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --header 'X-Forwarded-Proto: https' --expect 421
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --header 'X-Forwarded-Host: apps.qa.test' --expect 421
  control-agent-server restart --config-json '{"trust_forwarded_headers": false}'
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-headers/backend/start --json "{\"revision\": \"$REV2\"}" \
    --expect 200 --check state eq ready --quiet
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' \
    --header "Host: localhost:$P" --header "X-Forwarded-Host: 127.0.0.1:$P" --expect 421 \
    --save F29.trusted-forwarded-headers/untrusted-again
  ```
  信任，  输出的中文译文保持原样 `X-Forwarded-Host: 127.0.0.1:PORT` makes a `localhost:PORT` 请求计数作为入站（a `Secure` cookie) 和代理，但没有它时，请求仍然是 421，而转发过来的请求是 421
  `https` 或外部主机与 `http` 入口 (421) 不匹配。 第二次重新启动后，标头将再次被忽略。 两个后端都已准备就绪。
- **服务器重新启动(`F29.sessions-not-persisted`)。**会话和正在运行的后端都在内存中。
  ```sh
  RS=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RS" --expect 200
  control-agent-server restart
  control-agent-server api GET /server_info --auth none --check app_backend_ingress_url eq "$S"
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state eq stopped \
    --check prepared_revision eq "$REV" --save F29.sessions-not-persisted/backend-after-restart
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RS" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready'
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$REV\"}" \
    --expect 200 --check state eq ready
  control-agent-server api POST /api/canvas-extensions/installed/qa-headers/backend/start --json "{\"revision\": \"$REV2\"}" \
    --expect 200 --check state eq ready
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RS" --expect 401 \
    --save F29.sessions-not-persisted/old-cookie
  RT=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$RT" --expect 200 \
    --check app eq qa-backend
  ```
  重启后，两个后端都 `stopped`，桥接器返回 503。 他们再次开始，但没有新的准备，预重启 cookie 会返回 401 并且新的会话可以工作。
- **会话到期 (`F29.session-ttl`)。**服务器自己的 300 秒计时器是被测试的东西，所以这个子弹等待它（大约五分钟）。
  ```sh
  T0=$SECONDS
  TTL=$(control-agent-server api POST /app-backends/qa-headers/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$TTL"
  control-agent-server ws start /app-backends/qa-headers/ws --name f29-ttl --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$TTL" --send qa-f29-ttl --duration 400
  control-agent-server ws read f29-ttl --contains qa-f29-ttl --wait 10 --expect-open
  control-agent-server api GET /app-backends/qa-headers/echo --auth none --cookie "oh_app_backend_session=$TTL" --expect 200
  control-agent-server ws read f29-ttl --wait 330 --expect-close 1000 --save F29.session-ttl/socket-closed
  ELAPSED=$((SECONDS - T0))
  test "$ELAPSED" -ge 295 && test "$ELAPSED" -le 320
  control-agent-server ws stop f29-ttl
  control-agent-server api GET /app-backends/qa-headers/echo --auth none --cookie "oh_app_backend_session=$TTL" --expect 401 \
    --save F29.session-ttl/expired-cookie
  ```
  在295到320秒之间，idle socket关闭（1000），期间没有流量，然后cookie返回401。
- **卸载(`F29.uninstall-revokes`)。** F28的卸载路线，通过桥看到的。 最后，因为它删除了 `qa-backend`。
  ```sh
  UC=$(control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 200 --print-header set-cookie | sed -n 's/^oh_app_backend_session=\([^;]*\);.*/\1/p')
  test -n "$UC"
  control-agent-server ws start /app-backends/qa-backend/ws --name f29-uninstall --auth none --header "Origin: $S" \
    --header "Cookie: oh_app_backend_session=$UC" --send qa-f29-before-uninstall --duration 120
  control-agent-server ws read f29-uninstall --contains echo:qa-f29-before-uninstall --wait 10 --expect-open
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-backend --expect 200
  control-agent-server ws stop f29-uninstall --wait 10 --expect-close 1000 --save F29.uninstall-revokes/socket-closed
  control-agent-server api GET /app-backends/qa-backend/echo --auth none --cookie "oh_app_backend_session=$UC" --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --save F29.uninstall-revokes/proxy
  control-agent-server api POST /app-backends/qa-backend/session --header 'Origin: http://localhost:3000' --expect 503 \
    --check exception eq '503: Canvas App backend is not ready' --check-header set-cookie missing
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state eq missing \
    --check pid missing --save F29.uninstall-revokes/backend
  ```
  卸载会关闭打开的套接字（1000），停止后端（`missing`，没有`pid`），桥接器会以与从未安装过的应用程序相同的方式回答旧的cookie和新的bootstrap，即桥接器会以与从未启动过的应用程序相同的方式回答旧的 cookie 和新的 bootstrap。

<a id="gotchas"></a>

## 陷阱

- 两个凭据，两个主机的规则：引导程序 (`POST`/`DELETE .../session`) 采用 `X-Session-API-Key` 和一个控制
  `Origin` 与入站源不同，而代理路由仅使用 cookie，对于 WebSockets 和 `Origin`，则等于入站源。 两者都必须到达入口主机。 与
  `--canvas-ingress`入口是运行自己的`http://127.0.0.1:PORT`，因此使用`http://localhost:3000`（另一个端口上的任何环回源）作为控制源； 入口原点本身为 409。
- 来自网桥的 5xx 答案通过服务器的通用 5xx 处理程序：
  `detail`是`Internal Server Error`，原因在`exception`（`503: Canvas App backend is not ready`）中。 对`exception`断言。
- 未知的应用程序和已安装的后端已停止、正在启动或不健康的应用程序看起来相同（503 未就绪）； 该桥永远不会透露哪些应用程序存在。 只有具有实时进程的 `state == ready` 才有效。 只有当有人调用 F28 状态、停止或启动路由时，存储状态才会改变，但一个在准备就绪时崩溃的后端不会在之间被调用（503，`F29.backend-crash-detected`)。 拒绝连接的实时后端会回答 502 `Canvas App backend unreachable`。
- 会话绑定到应用名称和后端的当前回环端口：任何后端重启（新端口）都会 invalidate 会话 cookie，还包括停止、禁用、卸载、`DELETE .../session` 和服务器重启（会话在内存中）。 Canvas 必须在每次启动后和 300 秒之前再次引导 TTL； TTL 是一个常量，不可配置。
- 关闭并重置了代码为1000（正常关闭）的断开连接，而不是策略代码，并且一个撤销 `DELETE` 等待这些断开连接完成关闭（大约需要一秒）。
- 从 shell 发送，cookie 必须显式传递 (`--cookie`) 或通过 CLI `--jar`； jar 与浏览器一样，将 `127.0.0.1` 视为安全的上下文并向其重播 `Secure` cookie。 `curl` 自己的 cookie jar 可能不会。 jar 通过前缀匹配路径，因此它也会将 cookie 重播到
  `/app-backends/<name>-other`; 浏览器没有。
- 代理请求保留了客户端的主体框架 (`F29.proxy-request-framing`): 无主体的请求到达，固定长度的主体带有 `Content-Length`，以及仅包含分块的客户端主体。
- 上游 `Set-Cookie` 被删除，上游重定向变为 502，因此应用程序后端两者都不能使用； 页面必须使用 URLs 相对
  `ingress_url`（以 `/` 结尾，与裸根路由不同）。
- `/app-backends/<name>/session` 上的 `POST` 和 `DELETE` 是网桥的会话路由，永远不会到达后端； 该路径上的 `GET`、`PUT`、`PATCH`、`HEAD` 和 `OPTIONS` 被代理。 CORS 预检（`OPTIONS` 与
  `Origin` 和 `Access-Control-Request-Method`) 由 CORS 中间件应答，并且也永远不会到达后端。
- HTTP 客户端在发送之前规范化文字 `.` 和 `..` 段（`/app-backends/<name>/./x` 作为 `/x` 到达），因此遍历配方使用百分比编码形式； 桥解码直到值停止变化。
- uvicorn 的 `proxy_headers` （信任 `X-Forwarded-Proto` 和
  `X-Forwarded-For` 来自 `FORWARDED_ALLOW_IPS` 对等点，默认环回）仅当 `trust_forwarded_headers` 为时才打开； 关闭它后，两个标头都不会更改请求方案或客户端地址，并且 `X-Forwarded-Host` 也永远不会被遵守。
- 来自 `allow_cors_origins` 的控制源必须在规范化后与列出的源完全匹配（方案、主机和端口； `allow_cors_origin_regex` 必须匹配整个 `Origin` 值，`DOCKER_HOST_ADDR` 必须匹配 `http` 或 `https` 上的主机，以及任何端口。 它们在启动时生效，因此配方会更改它们
  `restart`，这也会停止每个后端并丢弃每个会话。 要在运行时清除 `DOCKER_HOST_ADDR`，请使用 `--env DOCKER_HOST_ADDR=`（空）重新启动。
- 未被驱动到这里：二进制 WebSocket frames (the ) CLI 仅发送文本帧，以及  TypeScript 客户端会话方法，需要浏览器才能添加 `Origin` 并保持 cookie。
- 这些配方保存的证据包含实时 `oh_app_backend_session` 值（CLI 编辑运行的密钥，而不是应用程序 cookie）。 它们会在五分钟内过期，并且仅到达测试夹具后端。
