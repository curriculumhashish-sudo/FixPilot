<a id="deferred-init-warm-pool-dormant-mode"></a>

# 延迟初始化（暖池休眠模式）

Agent Server 温热池 * 可以启动 * 濒死状态 `OH_DEFERRED_INIT` 设置，生命周期开始启动无状态服务（VS Code、工具预加载、基础配置中的 telemetry），并标记 `/ready` 就绪，但永远不会进入对话、事件或 bash 服务。 直到`POST /api/init`提供每个用户的运行时配置，休眠门会关闭所有到达用户状态的入站：除了`/api/*`（包括`/api/init`的工作区静态文件路由），OpenAI-兼容`/v1`路由和`/app-backends`会返回门的原因，以及WebSocket（`/sockets/events`，`/sockets/session`）都会返回503
`/sockets/bash-events`) 在握手时被拒绝。 该门在身份验证之前运行，因此即使对于没有密钥的请求，休眠 Pod 也会响应 503。 只有`/api/init`、`GET /`、`/static`、文档和OpenAPI路由和状态路由保持开放：`/alive`、`/health`、`/ready`和`/server_info`保持200，这样调度器可以放置Pod。 `GET /api/init` 报告休眠/初始化/就绪状态，无需密钥； `POST /api/init` 由 `X-Init-API-Key`（休眠 `secret_key`，当 pod 有 None 时打开）控制，并且一次性应用 env，重建遥测，进入从合并配置构建的对话/注册表/bash 服务，将它们交换到 `app.state`，重新计算根路径和 VS Code token，并发出
`server_started`. 失败的 init 会回滚到休眠状态并记录错误，以便协调器可以重试； 第二个 init 是 400； 在非延迟服务器上，两条路由均为 404。 在交付的字段中，
`conversations_path`, `bash_events_dir`, `conversation_worktree_root`,
`max_concurrent_runs`、`webhooks`、`session_api_keys`、`web_url`和`env`生效，而`allow_cors_origins`永远不会到达启动时构建的CORS中间件； 这个家庭复制了它。

资料来源：`openhands-agent-server/openhands/agent_server/init_router.py`、`openhands-agent-server/openhands/agent_server/api.py`、`openhands-agent-server/openhands/agent_server/config.py`、`openhands-agent-server/openhands/agent_server/sockets.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-agent-server/openhands/agent_server/middleware.py`、`openhands-agent-server/openhands/agent_server/persistence/store.py`

需求：`git`、`llm`

发射：`--no-auth --deferred-init`

路线：`GET /api/init`、`POST /api/init`

<a id="sub-features"></a>

## 子功能

- `F03.dormant-boot`：延迟服务器正常启动，以 200 回答 `/alive`、`/ready`、`/server_info`、`GET /` 和 OpenAPI 文档，并在 `GET /api/init` 上报告 `{"state":"dormant","error":null}`。
- `F03.dormant-gates-api`every `/api/*` except `/api/init` 返回503状态码（读取、修改和单独挂载的） 工作区文件路由），并且主体携带了门的自身原因（`exception` = `503: server is in deferred-init state 'dormant'; call POST /api/init first`; `detail` 已被重写为 `Internal Server Error` 由 5xx 处理器。
- `F03.dormant-gates-sockets` 当bash-events、对话事件和会话 WebSockets 拒绝握手（门在1013之前关闭，客户端看到的是HTTP 403），因此永远不会读取认证帧。
- `F03.dormant-gates-v1`：当处于休眠状态时，OpenAI 兼容的 `GET /v1/models` 和 `POST /v1/chat/completions` 使用门的原因回答 503，Canvas 应用程序后端桥 (`/app-backends/...`) 也是如此。
- `F03.init-key-auth`：`POST /api/init`要求`X-Init-API-Key`等于休眠的`secret_key`； 丢失或错误的密钥是 401，在验证主体之前进行检查，并使状态处于休眠状态。
- `F03.init-validation`：未知字段、超出范围的值或空的传递会话密钥为 422，并且状态保持休眠状态。
- `F03.init-redacts-secret-input`：422 的回显输入带有包含机密的密钥（`Authorization` 标头），将其编辑为 `<redacted>`，并且原始值不会出现在响应中。
- `F03.init-failure-rollback`：如果初始化在构建过程中失败，返回500状态码，将状态回滚到`dormant`，门仍然关闭，记录错误在`GET /api/init`，以便可以重试。
- `F03.init-success`：有效的`POST /api/init`将服务器翻转到`ready`，新的对话存储在已传递的`conversations_path`下。
- `F03.init-delivered-webhooks`: `webhooks` 在启动时交付（在启动时启动的 pod 上交付） None接收新的对话 `ConversationInfo` at `{base_url}/conversations`, 包含交付的头部和交付的会话密钥。
- `F03.init-enforces-session-keys`：在没有密钥启动的 Pod 上，初始化后，`/api/*` 使用 401 拒绝丢失或错误的密钥，并使用 200 接受交付的会话密钥。
- `F03.init-applies-env`：在 init 处传递的 `env` 条目到达 `os.environ`，因此 bash 子进程，并且传递的 `bash_events_dir` 接收事件。
- `F03.init-keys-gate-bash-socket`：初始化后，`/sockets/bash-events` 对于没有交付密钥的客户端以 4001 关闭，并为使用它的客户端运行命令。
- `F03.init-opens-events-socket-and-v1`在休眠期间，拒绝的会话事件socket会打开并重播会话状态，如果没有，则会发送4001 `GET /v1/models` 没有密钥返回401，有密钥返回200 持有者令牌。
- `F03.init-web-url-root-path`: 一个已交付的 `web_url` 会成为根路径：带有 URLs 的服务，而 OpenAPI 文档会通告该前缀。
- `F03.init-delivered-worktree-root`：在 init 获取交付的 `conversation_worktree_root` 下的工作树后创建的 git 工作区上的 `worktree: true` 对话，而不是启动根目录。
- `F03.init-delivered-max-runs`：交付的 `max_concurrent_runs` 代替了默认值 (10)：第二次对话的 `/run` 是 429，而另一个运行占用该槽位，直到槽位空闲时才被接受。
- `F03.init-delivered-cors-origins`：在 `allow_cors_origins` 中交付的源必须在 init 之后通过 CORS 预检，正如该字段所承诺的那样（重现了一个真正的错误； 请参阅陷阱）。
- `F03.init-second-call-400`：`ready`之后的第二个`POST /api/init`被400拒绝，状态不变； 初始化密钥现已交付 `secret_key`，因此休眠引导密钥为 401。
- `F03.init-child-launcher`：在初始化时进行无密钥启动和密钥传递后，真实模型父级使用经过身份验证的内部启动器来启动子级。
- `F03.init-open-without-secret`：既不使用机密密钥也不使用会话密钥启动的 pod 接受 `POST /api/init`，但不使用 `X-Init-API-Key`； 之后，第一个交付的会话密钥是初始化密钥（无密钥重试是 401，带密钥的重试是 400）。
- `F03.init-state-not-persisted` 初始化状态只存在于内存中，因此重启后一个延迟的 Pod 会再次处于休眠状态（先前交付的键也会获得休眠的 503 状态），并且必须重新初始化。
- `F03.auth-before-gate`：已于 #5700 退休。 它断言，具有启动会话密钥的休眠 pod 在 503 门之前对丢失的密钥做出了 401 响应； 现在首先检查准备情况，请参阅`F03.gate-before-auth`。
- `F03.gate-before-auth`：当休眠配置已经包含会话密钥时，准备就绪检查在身份验证：缺少、错误或有效的密钥都会得到503休眠门（从不为401），在HTTP和WebSockets。
- `F03.not-deferred-404`：在非延迟服务器上，两个 `/api/init` 路由都返回 404，并且 `POST` 仍然在 404 之前验证 init 密钥。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- 配置/启动：`OH_DEFERRED_INIT=1`（`Config.deferred_init`）将服务器置于休眠模式； `control-agent-server launch --new --deferred-init` 设置它。 暖池 Pod 通常也无需会话密钥即可启动（它们到达 init 主体），`--no-auth` 建模； `--no-secret-key` 另外掉落
  `OH_SECRET_KEY`（开放初始化情况）。
- REST: `GET /api/init`（未经身份验证的协调器状态轮询）和
  `POST /api/init`（使用 `X-Init-API-Key` 标头进行身份验证，其值为休眠 `secret_key` = `OH_SECRET_KEY`，否则为第一个启动会话密钥，否则什么都没有且路由打开）。 初始化主体覆盖一组狭窄的 `Config` 字段：`session_api_keys`、`secret_key`、
  `conversations_path`, `bash_events_dir`, `conversation_worktree_root`,
  `webhooks`, `web_url`, `allow_cors_origins`, `max_concurrent_runs`, `env`,
  `telemetry`. 这些配方提供除 `telemetry`（F32）之外的所有字段，并通过其控制的行为读回每个字段。
- REST（门控）：每隔一条 `/api/*` 路由在休眠时应答 503； 配方探针 `/api/settings`、`/api/conversations/search`、
  `/api/bash/bash_events/search`、`POST /api/bash/execute_bash_command` 和工作区文件路由 `/api/conversations/{id}/workspace`（安装在其自己的路由器上，带有相同的 `require_initialized` 门）。 `/v1`OpenAI兼容路由器和`/app-backends`网桥也带有它； 配方探针 `GET /v1/models`、`POST /v1/chat/completions` 和
  `GET /app-backends/{name}/{path}`.
- WebSocket：套接字路由器（`/sockets/events/{id}`，`/sockets/session/{id}`，
  `/sockets/bash-events`) 将gate作为路由器依赖项，因此休眠套接字在`accept()`之前被拒绝； 初始化后，配方驱动 bash 和事件套接字以显示它们打开，并且传递的密钥对它们进行门控。
- 休眠时打开：`GET /api/init`、`POST /api/init`、状态路由、
  `GET /`（`server_info` 别名）、`/static`（仅限静态文件模式）和
  `/openapi.json`, `/docs`, `/redoc`.
- REST（在 init 之后，作为交付字段的观察者； 这些路由属于各自的家族：`POST /api/conversations` `worktree: true` (工作树根)，`POST /api/conversations/{id}/run` 和 `/interrupt` (运行容量)，以及一个 CORS 预检 `OPTIONS /api/settings`，带有 `Origin` (CORS 允许列表）； 已交付的Webhook的交付是从HTTP接收器读取的。
- SDK/TypeScript客户端：没有消费者方法调用`/api/init`； 只有生成的 TypeScript 类型描述它 (`clients/typescript/src/generated/agent-server-schema.ts`)。 调用者是一个热池协调器。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 一个新的热池运行，以休眠状态启动且没有启动会话密钥，处于活动状态并导出：`control-智能体-server launch --new --no-auth
  --deferred-init`. `医生` is ok (a deferred run's `医生` uses `/alive`,
  因为 `/ready` 即使在休眠状态下也是 200）。 `$DEEPSEEK_API_KEY` 仅适用于子发射器子弹； 容量检查使用挂起的 `llm-stub`（按需保留运行槽的一种方法）。 工作树测试夹具需要 `git`。
- 下面的 `sh` 块首先运行：它读取运行的休眠状态
  `secret_key` (bootstrap) `X-Init-API-Key`, 从未打印过) `$SK`创建用户工作区成功小圆点所指向的目录，一个用于的 Git 仓库工作树 bullet (`$F03_REPO`), 一个stub提供者，每次调用都会阻塞300秒`$F03_HANG`) and a recording HTTP 交付的接收端 Webhook (`$F03_HOOKS`). (`api --auth init` 它发送相同的头，但在发送空值 `--no-auth` run; 请参阅陷阱。）
  ```sh
  SK="$(cat "$AGENT_SERVER_VERIFY_RUN/private/secret_key")"
  test -n "$SK"
  mkdir -p "$AGENT_SERVER_VERIFY_RUN/fixtures/conv" "$AGENT_SERVER_VERIFY_RUN/fixtures/bash" "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f03-workspace" "$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f03-worktrees"
  F03_REPO=$(control-agent-server fixture git-repo --name qa-f03-repo --print-path)
  test -d "$F03_REPO/.git"
  F03_HANG=$(control-agent-server fixture llm-stub --name qa-f03-hang --step hang:300 --print-path)
  F03_HOOKS=$(control-agent-server fixture http-sink --name qa-f03-hooks --print-path)
  ```
- 在这一轮中，子弹从上到下运行。 休眠状态的子弹首先出现； `F03.init-success` 是到 `ready` 的单向转换，并传递后面的项目符号读回的每个字段； open-init 项目符号使用自己的第二个服务器； 最后三颗子弹各
  `restart` 运行（将其重置为休眠状态，然后添加启动键，然后关闭延迟模式）并这样说。

- **休眠启动 (`F03.dormant-boot`)。** A deferred pod is up, ready to place, and reports dormant.
  ```sh
  control-agent-server api GET /alive --auth none --expect 200 --check status eq ok
  control-agent-server api GET /ready --auth none --expect 200 --check status eq ready
  control-agent-server api GET /api/init --auth none --expect 200 \
    --check state eq dormant --check error missing --save F03.dormant-boot/status
  control-agent-server logs --grep 'Server started in deferred-init mode' --expect-min 1
  control-agent-server api GET /openapi.json --auth none --max-chars 200 --check servers missing
  control-agent-server api GET /server_info --auth none --expect 200 --check version exists
  control-agent-server api GET / --auth none --expect 200 --check version exists
  ```
  虽然未进入会话服务，`/ready`为200，`GET /api/init`为`{"state":"dormant","error":null}`、`/server_info`及其
  `GET /` 门外别名应答，日志携带
  `Server started in deferred-init mode; awaiting POST /api/init`（由日志格式化程序包裹成两行，因此模式较短）。 OpenAPI 文档还没有 `servers`（之前的视图
  `F03.init-web-url-root-path`).
- **休眠门 (`F03.dormant-gates-api`).**除 `/api/init` 之外的所有 `/api/*` 路由在休眠时均为 503。
  ```sh
  control-agent-server api GET /api/settings --auth none --expect 503 \
    --check detail eq 'Internal Server Error' \
    --check exception contains "deferred-init state 'dormant'" --save F03.dormant-gates-api/settings
  control-agent-server api GET /api/conversations/search --auth none --expect 503 --check detail eq 'Internal Server Error'
  control-agent-server api GET /api/bash/bash_events/search --auth none --expect 503 --check exception contains 'call POST /api/init first'
  control-agent-server api POST /api/bash/execute_bash_command --auth none --json '{"command":"true"}' --expect 503 \
    --check exception contains 'call POST /api/init first'
  control-agent-server api GET /api/conversations/00000000-0000-0000-0000-0000000000f3/workspace --auth none --expect 503 \
    --check exception eq "503: server is in deferred-init state 'dormant'; call POST /api/init first" \
    --save F03.dormant-gates-api/workspace
  ```
  所有五人均返回了“门”的原因码 503。 真正的503详情由5xx处理器重写，因此需要断言状态和`exception`，后者携带`server is in deferred-init state 'dormant'; call POST /api/init first`。 工作区文件路由单独挂载在 `/api` 路由器上（基于 cookie 的认证），与 #5700 中的门限相同，因此它不再到达缺失的会话服务。
- **休眠套接字 (`F03.dormant-gates-sockets`)。**每个WebSocket在休眠时握手时都会被拒绝。
  ```sh
  F03_ZERO=00000000-0000-0000-0000-0000000000f3
  control-agent-server ws listen /sockets/bash-events --auth none --duration 5 --expect-reject 403 \
    --save F03.dormant-gates-sockets/bash-events
  control-agent-server ws listen "/sockets/events/$F03_ZERO" --auth none --duration 5 --expect-reject 403 \
    --save F03.dormant-gates-sockets/events
  control-agent-server ws listen "/sockets/session/$F03_ZERO" --auth none --duration 5 --expect-reject 403
  control-agent-server api GET /api/init --auth none --check state eq dormant
  ```
  `require_initialized` 提出了 `WebSocketException(1013)` 从 sockets 路由器的依赖中，之前 `accept()`所以， ASGI 服务器回应升级请求 HTTP 403 错误，套接字从不打开`opened: false`); 在这个无钥匙吊舱上，打开的插座将占据第一帧。 403 状态码也回答了一个未知的套接字路径，因此正控制是 init 后打开的事件和 bash 套接字`F03.init-keys-gate-bash-socket`,
  `F03.init-opens-events-socket-and-v1`).
- **休眠 /v1 和应用后端 (`F03.dormant-gates-v1`)。** OpenAI 兼容网关和应用程序后端桥也被门控。
  ```sh
  control-agent-server api GET /v1/models --auth none --expect 503 \
    --check exception contains "deferred-init state 'dormant'" --save F03.dormant-gates-v1/models
  control-agent-server api POST /v1/chat/completions --auth none \
    --json '{"model":"qa-f03","messages":[{"role":"user","content":"hi"}]}' --expect 503 \
    --check exception contains 'call POST /api/init first'
  control-agent-server api GET /app-backends/qa-f03-app/index.html --auth none --expect 503 \
    --check exception contains 'call POST /api/init first' --save F03.dormant-gates-v1/app-backends
  ```
  所有三个答案都以门的原因返回 503。 在没有钥匙的这个密钥 `/v1/models` 的情况下，原本应该是一个开放的 200（初始化后的新视图是 `F03.init-opens-events-socket-and-v1`）。
- **初始化密钥授权 (`F03.init-key-auth`).**在查看主体之前，需要引导密钥； 坏的是 401，状态没有改变。
  ```sh
  control-agent-server api POST /api/init --auth none --json '{}' --expect 401 --save F03.init-key-auth/no-header
  control-agent-server api POST /api/init --auth none --header 'X-Init-API-Key: qa-wrong-key' --json '{}' --expect 401
  control-agent-server api POST /api/init --auth none --header 'X-Init-API-Key: qa-wrong-key' --json '{"bogus":1}' --expect 401
  control-agent-server api GET /api/init --auth none --check state eq dormant
  ```
  三个职位都是401； 第三个包含一个由正确按键转换成422（下一句）的主体，因此按键被检查到。 `GET /api/init` 仍然处于休眠状态。 200是正确的键 `F03.init-success`.
- **初始化验证 (`F03.init-validation`).**未知字段、超出范围的值和空传递的会话密钥为 422； 该状态保持休眠状态。
  ```sh
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json '{"bogus":1}' --expect 422 --check 'detail.0.type' eq extra_forbidden --save F03.init-validation/unknown-field
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json '{"max_concurrent_runs":0}' --expect 422 --check 'detail.0.type' eq greater_than_equal
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json '{"session_api_keys":[""]}' --expect 422 \
    --check detail eq 'session_api_keys cannot contain empty keys' --save F03.init-validation/empty-session-key
  control-agent-server api GET /api/init --auth none --check state eq dormant
  ```
  `InitRequest`是`extra="forbid"`，所以`bogus`是`extra_forbidden`；
  `max_concurrent_runs` 具有 `ge=1`，因此 `0` 未达到界限。 空的交付密钥在初始化之前会被拒绝 (PR #5659)。 None改变状态。
- **输入脱敏（`F03.init-redacts-secret-input`）。** 422 echo 编辑了包含机密的密钥。
  ```sh
  RAW_REDACTED="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f03-422-redacted.json"
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json '{"webhooks":[{"headers":{"Authorization":"Bearer QA-SENTINEL-7788"}}]}' \
    --expect 422 --check 'detail.0.loc.3' eq base_url --check 'detail.0.input.headers.Authorization' eq '<redacted>' \
    --raw-out "$RAW_REDACTED" --save F03.init-redacts-secret-input/redacted
  test -s "$RAW_REDACTED"
  if grep -q 'QA-SENTINEL-7788' "$RAW_REDACTED"; then false; fi
  control-agent-server api GET /api/init --auth none --check state eq dormant
  ```
  的 Webhook 缺少其必需的 `base_url`因此，422 等同于  Webhook 对象为 `input`; 的验证处理器将其通过 `sanitize_dict`所以， `Authorization` 值返回 `<redacted>` 和哨兵值不在原始响应字节中。
- **失败回滚(`F03.init-failure-rollback`)。**失败的 init 返回 500 并返回休眠状态并记录错误。
  ```sh
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json '{"conversations_path":"/proc/oh-cannot-create-f03"}' --expect 500 \
    --check exception contains oh-cannot-create-f03 --save F03.init-failure-rollback/failure
  control-agent-server api GET /api/init --auth none --check state eq dormant --check error contains oh-cannot-create-f03
  control-agent-server api GET /api/settings --auth none --expect 503
  ```
  不可写入的路径导致会话服务无法进入。 处理器将状态回滚到 `dormant`，保持门关闭，并存储
  `error` 下的 `<ExceptionType>: <message>`（在 Linux 上
  `FileNotFoundError: [Errno 2] ... '/proc/oh-cannot-create-f03'`），因此协调器可以重试。 成功的重试是下一个要点。
- **初始化成功(`F03.init-success`)。**有效主体将 Pod 翻转到 `ready`； 对话位于交付的目录中。 身体传递了后来的子弹读回的每一个字段。
  ```sh
  BODY="$(python3 -c "import json,os,sys;r=os.environ['AGENT_SERVER_VERIFY_RUN']+'/fixtures/';print(json.dumps({'session_api_keys':['qa-user-key'],'secret_key':'qa-f03-delivered-secret','conversations_path':r+'conv','bash_events_dir':r+'bash','conversation_worktree_root':r+'qa-f03-worktrees','webhooks':[{'base_url':sys.argv[1],'headers':{'X-QA-F03':'delivered-hook'},'flush_delay':1}],'web_url':'http://qa-f03.invalid/rt/qa-f03','allow_cors_origins':['https://qa-f03.example'],'max_concurrent_runs':1,'env':{'PROBE_VAR':'qa-hello'}}))" "$F03_HOOKS")"
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" \
    --json "$BODY" --expect 200 --check state eq ready --check error missing --save F03.init-success/post
  control-agent-server api GET /api/init --auth none --check state eq ready --check error missing --save F03.init-success/ready
  CONV_BODY="$(python3 -c "import json,os;print(json.dumps({'agent_settings':{'agent_kind':'openhands','llm':{'model':'openai/qa-placeholder','api_key':'qa-placeholder','base_url':'http://127.0.0.1:9/v1','num_retries':0},'tools':[]},'workspace':{'kind':'LocalWorkspace','working_dir':os.environ['AGENT_SERVER_VERIFY_RUN']+'/fixtures/qa-f03-workspace'},'autotitle':False}))")"
  F03_CID=$(control-agent-server api POST /api/conversations --auth none --header 'X-Session-API-Key: qa-user-key' --json "$CONV_BODY" --expect 2xx --field id)
  control-agent-server api GET "/api/conversations/$F03_CID" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 --check id eq "$F03_CID"
  test -d "$AGENT_SERVER_VERIFY_RUN/fixtures/conv/$(echo "$F03_CID" | tr -d -)"
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations/$(echo "$F03_CID" | tr -d -)"
  ```
  `{"state":"ready","error":null}` 返回，状态检查一致。 使用交付的密钥创建的对话（一个未被调用的占位符模型）存储在交付的 `conversations_path` 下
  `<id without dashes>/`，并且不在引导路径 (`server/workspace/conversations`) 下。
- **已交付 Webhook (`F03.init-delivered-webhooks`)。** init主体携带Webhook、`$F03_HOOKS`和标头`X-QA-F03: delivered-hook`； 启动配置有None。

  需要：`F03.init-success`
  ```sh
  if grep -q webhooks "$AGENT_SERVER_VERIFY_RUN/private/config.json"; then false; fi
  control-agent-server sink read --name qa-f03-hooks --path /conversations --contains "\"id\": \"$F03_CID\"" --expect-min 1 --wait 15 \
    --save F03.init-delivered-webhooks/conversation-created
  control-agent-server sink read --name qa-f03-hooks --path /conversations --contains '"X-QA-F03": "delivered-hook"' --expect-min 1
  control-agent-server sink read --name qa-f03-hooks --path /conversations --contains '"X-Session-API-Key": "qa-user-key"' --expect-min 1
  ```
  在之前的一条 bullet 中创建 `$F03_CID` 后，它 `ConversationInfo` 交付的 `{base_url}/conversations`，携带交付的标头和交付的会话密钥 `X-Session-API-Key: qa-user-key`：新的会话服务是通过合并配置构建的。
- **强制执行交付的密钥 (`F03.init-enforces-session-keys`)。** pod 无需钥匙即可启动； init 添加了它们。
  ```sh
  control-agent-server api GET /api/settings --auth none --expect 401 --save F03.init-enforces-session-keys/no-key
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-wrong-key' --expect 401
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200
  ```
  `/api/settings` 没有钥匙或钥匙错误现在是 401（之前是 503
  while dormant and would have been open on this no-auth pod before init); the
  交付的 `qa-user-key` 已被接受。
- **初始化环境到达 bash (`F03.init-applies-env`)。** `env` entries are set before the services boot, so 子进程 see them, and the delivered `bash_events_dir` is used.
  ```sh
  control-agent-server api POST /api/bash/execute_bash_command --auth none --header 'X-Session-API-Key: qa-user-key' \
    --json '{"command":"echo PROBE=$PROBE_VAR"}' --expect 200 --check stdout contains 'PROBE=qa-hello' --save F03.init-applies-env/env
  test -n "$(ls -A "$AGENT_SERVER_VERIFY_RUN/fixtures/bash")"
  ```
  该命令打印 `PROBE=qa-hello`（初始化交付的环境），现在交付的 bash-events 目录包含了命令和输出事件。
- **交付的密钥控制 bash 套接字 (`F03.init-keys-gate-bash-socket`)。**初始化后，套接字使用传递的密钥进行身份验证。
  ```sh
  SOCK_PROBE="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f03-ws-after-init.txt"
  rm -f "$SOCK_PROBE"
  control-agent-server ws listen /sockets/bash-events --auth none \
    --send "{\"command\": \"echo no-key > $SOCK_PROBE\"}" --duration 5 --expect-close 4001 --save F03.init-keys-gate-bash-socket/no-key
  test ! -f "$SOCK_PROBE"
  control-agent-server ws listen /sockets/bash-events --auth key --key qa-user-key \
    --send "{\"command\": \"echo with-key > $SOCK_PROBE\"}" --until-kind BashOutput --until exit_code=0 --duration 20 \
    --expect-kind BashCommand --save F03.init-keys-gate-bash-socket/with-key
  grep -qx with-key "$SOCK_PROBE"
  ```
  没有密钥，命令帧被当作失败的第一帧认证，然后在任何东西运行之前，套接字就会以4001的状态关闭。 使用 `qa-user-key` 会产生 `BashCommand` 和 `BashOutput` (`exit_code` 0) 并写入文件。 握手时，该端点处于休眠状态，被拒绝连接 (`F03.dormant-gates-sockets`)。
- **事件套接字和 /v1 在 init (`F03.init-opens-events-socket-and-v1`) 后打开。**休眠套接字和 `/v1` 门的阳性对照。
  需要：`F03.init-success`
  ```sh
  control-agent-server ws listen "/sockets/events/$F03_CID" --auth key --key qa-user-key --query resend_mode=all \
    --until-kind ConversationStateUpdateEvent --duration 15 --expect-kind ConversationStateUpdateEvent \
    --save F03.init-opens-events-socket-and-v1/events-socket
  control-agent-server ws listen "/sockets/events/$F03_CID" --auth none \
    --send '{"role":"user","content":[{"type":"text","text":"hi"}],"run":false}' --duration 5 --expect-close 4001
  control-agent-server api GET /v1/models --auth none --expect 401
  control-agent-server api GET /v1/models --auth none --header 'Authorization: Bearer qa-user-key' --expect 200 \
    --check object eq list --save F03.init-opens-events-socket-and-v1/models
  ```
  使用交付的密钥后，`$F03_CID` 的事件套接字打开并回放其`ConversationStateUpdateEvent`。 没有密钥时，第一个帧被当作认证失败，并且套接字关闭，返回状态码 4001（不再是一个握手 403）。 `/v1/models` 现在由交付的密钥保护：没有密钥时，为401
  `{"object": "list", ...}` 表示以 OpenAI 方式发送的已交付密钥。
- **传送的网页URL设置根路径(`F03.init-web-url-root-path`)。** init主体携带`web_url``http://qa-f03.invalid/rt/qa-f03`。
  ```sh
  PREFIX=/rt/qa-f03
  control-agent-server api GET "$PREFIX/alive" --auth none --expect 200 --check status eq ok --save F03.init-web-url-root-path/prefixed-alive
  control-agent-server api GET "$PREFIX/api/settings" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200
  OTHER_PREFIX=/rt/qa-other
  control-agent-server api GET "$OTHER_PREFIX/alive" --auth none --expect 404
  control-agent-server api GET /openapi.json --auth none --max-chars 200 --check servers.0.url eq /rt/qa-f03
  control-agent-server api GET /alive --auth none --expect 200
  ```
  只有 URL 的路径（主机永远不会被联系到）：`/rt/qa-f03/...` 服务应用，另一个前缀是 404，未前缀的路径继续工作，而 OpenAPI 文档现在列出了 `servers: [{"url": "/rt/qa-f03"}]`（它原来没有）
  `servers` 休眠时）。 带前缀的路径经过 `$PREFIX` 因为
  `map check` 根据无前缀路由表验证文字路径。
- **已交付工作树根 (`F03.init-delivered-worktree-root`)。** init体携带`conversation_worktree_root``<run>/fixtures/qa-f03-worktrees`； 启动配置指向`<run>/worktrees`。
  ```sh
  grep -qF "\"conversation_worktree_root\": \"$AGENT_SERVER_VERIFY_RUN/worktrees\"" "$AGENT_SERVER_VERIFY_RUN/private/config.json"
  WT_BODY="$(python3 -c "import json,sys;print(json.dumps({'agent_settings':{'agent_kind':'openhands','llm':{'model':'openai/qa-placeholder','api_key':'qa-placeholder','base_url':'http://127.0.0.1:9/v1','num_retries':0},'tools':[]},'workspace':{'kind':'LocalWorkspace','working_dir':sys.argv[1]},'worktree':True,'autotitle':False}))" "$F03_REPO")"
  WT_CID=$(control-agent-server api POST /api/conversations --auth none --header 'X-Session-API-Key: qa-user-key' --json "$WT_BODY" --expect 2xx --field id)
  WT_DIR="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f03-worktrees/$WT_CID/qa-f03-repo"
  control-agent-server api GET "/api/conversations/$WT_CID" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 \
    --check workspace.working_dir eq "$WT_DIR" --save F03.init-delivered-worktree-root/get
  test "$(git -C "$WT_DIR" rev-parse --abbrev-ref HEAD)" = "openhands/$WT_CID"
  git -C "$F03_REPO" worktree list | grep -qF "$WT_DIR"
  test -z "$(ls -A "$AGENT_SERVER_VERIFY_RUN/worktrees" 2>/dev/null)"
  ```
  对话的工作区是
  `<delivered root>/<conversation id>/qa-f03-repo`，分支 `openhands/<conversation id>` 上测试夹具存储库的真实工作树，引导根目录保持为空。 没有调用任何模型。
- **交付运行容量 (`F03.init-delivered-max-runs`)。** init体携带`max_concurrent_runs`1； 启动配置没有设置它，所以它是默认的 10。 `$F03_HOLD` 保留模型调用上的一个槽，该槽在 `$F03_WAITER` 要求运行时挂起。
  ```sh
  if grep -q max_concurrent_runs "$AGENT_SERVER_VERIFY_RUN/private/config.json"; then false; fi
  HANG_BODY="$(python3 -c "import json,os,sys;print(json.dumps({'agent_settings':{'agent_kind':'openhands','llm':{'model':'openai/qa-stub','api_key':'qa-stub-key','base_url':sys.argv[1]+'/v1','num_retries':0},'tools':[]},'workspace':{'kind':'LocalWorkspace','working_dir':os.environ['AGENT_SERVER_VERIFY_RUN']+'/fixtures/qa-f03-workspace'},'autotitle':False}))" "$F03_HANG")"
  F03_HOLD=$(control-agent-server api POST /api/conversations --auth none --header 'X-Session-API-Key: qa-user-key' --json "$HANG_BODY" --expect 2xx --field id)
  F03_WAITER=$(control-agent-server api POST /api/conversations --auth none --header 'X-Session-API-Key: qa-user-key' --json "$HANG_BODY" --expect 2xx --field id)
  control-agent-server api POST "/api/conversations/$F03_HOLD/events" --auth none --header 'X-Session-API-Key: qa-user-key' \
    --json '{"role":"user","content":[{"type":"text","text":"hi"}],"run":false}' --expect 200
  control-agent-server api POST "/api/conversations/$F03_WAITER/events" --auth none --header 'X-Session-API-Key: qa-user-key' \
    --json '{"role":"user","content":[{"type":"text","text":"hi"}],"run":false}' --expect 200
  control-agent-server api POST "/api/conversations/$F03_HOLD/run" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$F03_HOLD" --auth none --header 'X-Session-API-Key: qa-user-key' --check execution_status eq running --until-ok 30
  control-agent-server api POST "/api/conversations/$F03_WAITER/run" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 429 \
    --check detail eq 'Conversation run limit reached. Retry the request later.' --save F03.init-delivered-max-runs/run-429
  control-agent-server api GET "/api/conversations/$F03_WAITER" --auth none --header 'X-Session-API-Key: qa-user-key' --check execution_status eq idle
  control-agent-server api GET /api/conversations/count --auth none --header 'X-Session-API-Key: qa-user-key' --query status=running --check . eq 1
  control-agent-server api POST "/api/conversations/$F03_HOLD/interrupt" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 --check success eq true
  control-agent-server api POST "/api/conversations/$F03_WAITER/run" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 \
    --check success eq true --until-ok 30 --save F03.init-delivered-max-runs/run-after-release
  control-agent-server api GET "/api/conversations/$F03_WAITER" --auth none --header 'X-Session-API-Key: qa-user-key' --check execution_status eq running --until-ok 30
  control-agent-server api POST "/api/conversations/$F03_WAITER/interrupt" --auth none --header 'X-Session-API-Key: qa-user-key' --expect 200 --check success eq true
  control-agent-server api GET /api/conversations/count --auth none --header 'X-Session-API-Key: qa-user-key' --query status=running --check . eq 0 --until-ok 30
  ```
  在一次对话进行中，第二个 `/run` 是 429 `Conversation run limit reached...`，然后它 `idle`。 默认的限制是10，本应接受它。 一旦持有人被中断，相同的`/run`被接受（阳性对照），然后子弹又中断它，因此没有残留物。 两个会话在任何一方运行之前都已创建，因为一个创建会同时预留一个槽位。
- **交付 CORS origins (`F03.init-delivered-cors-origins`), 已知错误。** 初始化体携带了 `allow_cors_origins`  `["https://qa-f03.example"]`, documented as [ ]CORS 允许添加到现有本地回环地址白名单中的原始。 今天，来自该来源的预检被拒绝，因此这是预期的失败。
  ```sh
  control-agent-server api OPTIONS /api/settings --auth none --header 'Origin: http://localhost:3000' --header 'Access-Control-Request-Method: GET' \
    --expect 200 --check-header access-control-allow-origin eq http://localhost:3000
  control-agent-server api OPTIONS /api/settings --auth none --header 'Origin: https://qa-f03-other.example' --header 'Access-Control-Request-Method: GET' \
    --expect 400 --check-header access-control-allow-origin missing
  control-agent-server api OPTIONS /api/settings --auth none --header 'Origin: https://qa-f03.example' --header 'Access-Control-Request-Method: GET' --expect 200 --check-header access-control-allow-origin eq https://qa-f03.example --save F03.init-delivered-cors-origins/preflight  # bug：状态 eq 400 && response.body 包含“不允许的 CORS 来源”
  ```
  本地回环预检被允许（始终启用的允许白名单，正向控制），而没有被送达的源被拒绝返回400（中间件用于区分）。 应回显交付的源头
  `access-control-allow-origin` 200； 今天它得到同样的 400
  `Disallowed CORS origin` 作为未交付的，因为 `CORSDispatcher` 在构建应用程序时复制了启动配置的 `allow_cors_origins`。
- **第二个初始化为 400 (`F03.init-second-call-400`)。** Init 是一次性的，交付的 `secret_key` 现在是 init 密钥。
  ```sh
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" --json '{}' --expect 401 --save F03.init-second-call-400/old-key
  control-agent-server api POST /api/init --auth none --header 'X-Init-API-Key: qa-f03-delivered-secret' \
    --json '{}' --expect 400 --check detail contains 'already in state: ready' --save F03.init-second-call-400/already-ready
  control-agent-server api GET /api/init --auth none --check state eq ready
  ```
  `check_init_api_key` 读取合并的配置，因此休眠引导键
  `$SK`现在是401，交付的`qa-f03-delivered-secret`达到一次性400`server already in state: ready`； 状态不变。
- **打开不带机密 (`F03.init-open-without-secret`) 的 init。**第二台无钥匙、无秘密的休眠服务器停在了子弹的末端。
  ```sh
  OPEN=$(control-agent-server launch --new --no-auth --no-secret-key --deferred-init --name f03-open --print-run)
  trap 'control-agent-server stop --run "$OPEN" >/dev/null' EXIT
  control-agent-server api GET /api/init --run "$OPEN" --auth none --expect 200 --check state eq dormant
  control-agent-server api POST /api/init --run "$OPEN" --auth none --json '{"session_api_keys":["qa-open-key"],"secret_key":""}' \
    --expect 200 --check state eq ready --save F03.init-open-without-secret/open
  control-agent-server api GET /api/settings --run "$OPEN" --auth none --expect 401
  control-agent-server api GET /api/settings --run "$OPEN" --auth none --header 'X-Session-API-Key: qa-open-key' --expect 200
  control-agent-server api POST /api/init --run "$OPEN" --auth none --json '{}' --expect 401
  control-agent-server api POST /api/init --run "$OPEN" --auth none --header 'X-Init-API-Key: qa-open-key' --json '{}' \
    --expect 400 --check detail contains 'already in state: ready' --save F03.init-open-without-secret/retry
  control-agent-server stop --run "$OPEN"
  ```
  未配置 `secret_key` 时（`check_init_api_key`："未配置密钥 → 端点为开放状态。 对于开发人员来说，第一个帖子不需要头部，并且会应用传递的密钥。 显空的`secret_key`被规范化，因此合并配置的`secret_key` fallback到`qa-open-key`，所以无键的重试现在是401，带有`qa-open-key`的重试现在达到一次性400。
- **初始化后的孩子启动器（）`F03.init-child-launcher`).** 一个单独的Pod在启动时没有会话密钥，但在初始化时接收到一个，当一个实际的模型调用明确附带的子启动工具时，它会使用这个密钥。
  ```sh
  CHILD_RUN=$(control-agent-server launch --new --no-auth --no-secret-key --deferred-init --name f03-child --print-run)
  trap 'control-agent-server stop --run "$CHILD_RUN" >/dev/null' EXIT
  control-agent-server doctor --run "$CHILD_RUN"
  control-agent-server api POST /api/init --run "$CHILD_RUN" --auth none \
    --json '{"session_api_keys":["qa-f03-child-key"],"max_concurrent_runs":2}' \
    --expect 200 --check state eq ready --save F03.init-child-launcher/init
  control-agent-server api GET /api/settings --run "$CHILD_RUN" --auth none --expect 401
  CHILD_BODY=$(python3 - "$CHILD_RUN" <<'PY'
  import json, os, sys
  print(json.dumps({
      "agent": {"llm": {"model": "deepseek/deepseek-flash", "api_key": os.environ["DEEPSEEK_API_KEY"]},
                "tools": [{"name": "start_child_conversation"}]},
      "workspace": {"working_dir": sys.argv[1] + "/fixtures/child-workspace"},
      "autotitle": False, "max_iterations": 5,
      "initial_message": {"role": "user", "content": [{"type": "text", "text":
          'Call start_child_conversation exactly once with these arguments: {"title": "QA_F03_CHILD", "isolation": "shared", "task": "Reply with the single word ok. Do not use tools or create any child conversations."}. After the call returns, finish without any more tool calls.'}]},
  }))
  PY
  )
  mkdir -p "$CHILD_RUN/fixtures/child-workspace"
  DPARENT=$(control-agent-server api POST /api/conversations --run "$CHILD_RUN" --auth none \
    --header 'X-Session-API-Key: qa-f03-child-key' --json "$CHILD_BODY" --expect 201 --field id)
  for attempt in $(seq 1 120); do
    DSTATUS=$(control-agent-server api GET "/api/conversations/$DPARENT" --run "$CHILD_RUN" --auth none \
      --header 'X-Session-API-Key: qa-f03-child-key' --field execution_status)
    [ "$DSTATUS" = finished ] && break
    [ "$DSTATUS" != error ]
    sleep 2
  done
  test "$DSTATUS" = finished
  DOBS=$(control-agent-server api GET "/api/conversations/$DPARENT/events/search" --run "$CHILD_RUN" --auth none \
    --header 'X-Session-API-Key: qa-f03-child-key' --query kind=ObservationEvent \
    --check items contains StartChildConversationObservation --save F03.init-child-launcher/observation --field items)
  DCHILD=$(jq -er --arg parent "$DPARENT" '[.[] | select(.tool_name == "start_child_conversation")] |
    select(length == 1) | .[0].observation |
    select(.is_error == false and .parent_conversation_id == $parent and .isolation == "shared") |
    .conversation_id' <<< "$DOBS")
  for attempt in $(seq 1 120); do
    DSTATUS=$(control-agent-server api GET "/api/conversations/$DCHILD" --run "$CHILD_RUN" --auth none \
      --header 'X-Session-API-Key: qa-f03-child-key' --field execution_status)
    [ "$DSTATUS" = finished ] && break
    [ "$DSTATUS" != error ]
    sleep 2
  done
  control-agent-server api GET "/api/conversations/$DCHILD" --run "$CHILD_RUN" --auth none \
    --header 'X-Session-API-Key: qa-f03-child-key' --check execution_status eq finished \
    --check parent_conversation_id eq "$DPARENT" --check title eq QA_F03_CHILD \
    --save F03.init-child-launcher/child
  control-agent-server api GET "/api/conversations/$DPARENT" --run "$CHILD_RUN" --auth none \
    --header 'X-Session-API-Key: qa-f03-child-key' --check sub_conversation_ids contains "$DCHILD"
  control-agent-server stop --run "$CHILD_RUN"
  ```
  儿童工具的观测结果和目录链接证明内部启动器接收到初始化交付的会话密钥。 只提供空启动凭据的服务器将拒绝该内部请求，返回 401。
- **初始状态不是已持久化 (`F03.init-state-not-persisted`)。**该项目符号重新启动运行； 延迟的 pod 恢复休眠状态。
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/init --auth none --check state eq dormant --check error missing --save F03.init-state-not-persisted/after-restart
  control-agent-server api GET /api/settings --auth none --expect 503
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-user-key' --expect 503 \
    --check exception contains "deferred-init state 'dormant'"
  ```
  重生的热容器只存在于记忆中，因此，重新启动的容器又会处于休眠状态，必须重新初始化。 即使是之前交付的
  `qa-user-key`满足休眠503。
- **准备先于验证 (`F03.gate-before-auth`).**此项目符号使用启动会话密钥重新启动运行，但仍然延迟。 它取代了退役的 `F03.auth-before-gate`（大门前的 401），其顺序 #5700 颠倒了。
  ```sh
  control-agent-server restart --env OH_SESSION_API_KEYS_0=qa-boot-key
  control-agent-server api GET /api/init --auth none --expect 200 --check state eq dormant
  control-agent-server api GET /api/settings --auth none --expect 503 \
    --check exception contains 'call POST /api/init first' --save F03.gate-before-auth/no-key
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-wrong-key' --expect 503 \
    --check exception contains 'call POST /api/init first' --save F03.gate-before-auth/wrong-key
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-boot-key' --expect 503
  control-agent-server api GET /v1/models --auth none --header 'Authorization: Bearer qa-wrong-key' --expect 503
  control-agent-server ws listen /sockets/bash-events --auth bad --duration 5 --expect-reject 403 \
    --save F03.gate-before-auth/socket-bad-key
  ```
  `require_initialized` 在 `/api` 路由器上列在 `check_session_api_key` 之前，并且 `/v1` 和套接字路由器在其自己的身份验证之前进行控制，因此
  while dormant a missing, wrong or valid boot key all get the same 503 (and a
  bad-key 套接字握手 403，而不是就绪服务器的 4001 关闭）：休眠的 Pod 不会透露它持有哪些密钥。 初始化后，密钥将照常强制执行 (`F03.init-enforces-session-keys`)。
- **未推迟的是 404 (`F03.not-deferred-404`)。**此项目符号在关闭延迟模式的情况下重新启动运行（上一个项目符号的启动键保持不变）。
  ```sh
  control-agent-server restart --config-json '{"deferred_init": false}'
  control-agent-server api GET /api/init --auth none --expect 404 --check detail contains 'deferred_init=True' --save F03.not-deferred-404/get
  control-agent-server api POST /api/init --auth none --json '{}' --expect 401
  control-agent-server api POST /api/init --auth none --header "X-Init-API-Key: $SK" --json '{}' --expect 404
  control-agent-server api GET /api/settings --auth none --header 'X-Session-API-Key: qa-boot-key' --expect 200
  ```
  没有 `InitService` 和 `app.state`，`GET /api/init` 的值为 404。 `POST` 仍然首先检查初始化密钥（401 无此密钥，404 有此密钥），而REST 的API 正常工作。

<a id="gotchas"></a>

## 陷阱

- `/ready` 在休眠时（pod 可放置）为 200，因此就绪探针不是初始化检查 — 轮询 `GET /api/init` 来获取真实状态。 出于同样的原因，延迟运行中的 `doctor` 使用 `/alive`。
- 休眠的503的`detail`被5xx异常处理程序重写为`Internal Server Error`； 原因仅在`exception`中存在。 键入状态代码，而不是 `detail` 文本。 同一处理程序将初始化失败的异常字符串（包括路径）放入 500 正文中。
- 休眠的 WebSocket 在 `accept()` 之前用 1013 关闭，它以 HTTP 403 握手拒绝 (`ws listen --expect-reject 403`) 的形式到达客户端，而不是作为 1013 关闭帧。 未知的套接字路径也是 403，因此将休眠检查与 init 后打开的相同套接字配对。
- 自 #5700 (`F03.gate-before-auth`) 以来，该门先于每次身份验证检查，因此
  while dormant a 503 says nothing about the key; prove a key only after init.
  在 #5700 之前，工作区静态文件路由、套接字、`/v1` 和
  `/app-backends`在门外（#5661，#5700关闭了他们）； 比 PR 更早的基线结账对这些食谱的回答不同。
- 启动脚本 `X-Init-API-Key` 是沉睡的 `secret_key`，默认为第一个会话密钥 `OH_SECRET_KEY` 未设置且是 **对任何人开放** 当 neither 也不设置时（`F03.init-open-without-secret`). `control-agent-server launch` sets `OH_SECRET_KEY` 除非 `--no-secret-key` 已给出，因此主运行的 `POST /api/init` 是密钥保护的。
- 线束：`api --auth init` 读取为 `<run>/private/secret_key`，但在
  `--no-auth` run 它根本不发送标头（当运行没有会话密钥时，身份验证助手会提前返回），因此这些配方显式传递 `--header "X-Init-API-Key: $SK"`。 `doctor` 读取 init `state`：休眠时检查 503 HTTP 和 403 套接字门； 在 init 之后，它使用运行配置的凭据检查普通身份验证。
- Init 是一次性的并且是内存中的：在重新启动 (`F03.init-state-not-persisted`) 时它不会持久化，并且第二次调用是 400（`已经在
  状态：准备好`； 当另一个呼叫仍在构建时落地的呼叫得到
  `already in state: initializing`, 初始化速度太快，无法按需显示。 如果初始化体设置 `secret_key`, 或者如果休眠的配置  None 并且会交付会话密钥，bootstrap密钥也会改变，并且会生成一个新的重试使用旧密钥时，返回状态码为401，而不是400。
- 失败的 init 仅回滚状态：它应用的 `env` 条目保留在
  `os.environ`（观察到：只有在尝试失败时才发送的变量在成功重试后对bash可见，而它在失败前进入的服务在失败后没有退出。） `InitRequest.env`记录`os.environ.update`，而不是回滚； 在重试上重新发送完整的环境。
- `OH_DEFERRED_INIT` 必须是 `1`/`true`（不区分大小写）； `yes` 解析为False。
- init 交付的 `allow_cors_origins` 是无操作 (`F03.init-delivered-cors-origins`)：`create_app` 将 `CORSDispatcher` 添加到启动配置列表中，它会复制该列表，并且不会在 init 处重建它。 启动配置中的相同源 (`restart --config-json '{"deferred_init": false, "allow_cors_origins": ["https://qa-f03.example"]}'`) 通过相同的预检，值为 200（实时观察； 此处未断言）。
- 当交付的 `max_concurrent_runs` 为 1 时，`POST /api/conversations` 在初始化时也会占用该槽，因此在开始运行之前创建每个对话 (`F03.init-delivered-max-runs`)。
- 测试框架：`conversation` 命令使用本次运行自身的会话密钥进行身份验证，且不接受 `--header`；因此在本次 `--no-auth` 运行中，初始化后的步骤使用 `api ... --header 'X-Session-API-Key: qa-user-key'` 创建并驱动对话。
- 该系列未断言的已知警告：`web_url` 无条件应用，尽管其“仅在尚未设置时”描述； 此处未断言已交付 Webhook 的事件交付 (`/events/{id}`)（F32 拥有交付语义）； init-delivered `telemetry` 和 deferred `server_started` 事件属于遥测系列 (F32)。
