<a id="server-status-info-and-contract"></a>

# 服务器状态、信息和合同

消费者在读取任何东西之前都会读取的探针和元数据：`/server_info`（和它的`/`别名）用于版本和构建标识，可用工具，功能标志和空闲时间，以及客户端生成类型文档的OpenAPI文档。 即使身份验证打开，它们也都无需会话密钥即可应答。 这三种服务器级设置改变了这些表面显示的内容：`static_files_path` 将 `/` 转换为一个无认证 `/static` 路由，`preload_tools` 在 `/ready` 之前运行一个工具预加载，以及 `DEBUG` 在 5xx 响应体中添加一个堆栈跟踪。

资料来源：`openhands-agent-server/openhands/agent_server/server_details_router.py`、`openhands-agent-server/openhands/agent_server/api.py`、`openhands-agent-server/openhands/agent_server/openapi.py`、`openhands-agent-server/openhands/agent_server/tool_preload_service.py`、`openhands-agent-server/openhands/agent_server/config.py`

路线：`GET /alive`、`GET /health`、`GET /ready`、`GET /server_info`、`GET /`、
`GET /openapi.json`

<a id="sub-features"></a>

## 子功能

- `F01.alive`：`GET /alive` 在没有会话密钥的情况下返回 200 `{"status": "ok"}`，而受保护的路由拒绝相同的无密钥请求。
- `F01.health`: `GET /health` 返回 200 `{"status": "ok"}`，没有会话密钥。
- `F01.ready`: `GET /ready` 启动完成后返回 200 `{"status": "ready"}`，无需会话密钥。
- `F01.server-info`：`GET /server_info` 报告包版本，`build_git_sha` 等于所提供的结账、可用工具和功能标志，没有会话密钥。
- `F01.root-info`：没有静态文件，`GET /` 返回与 `/server_info` 相同的服务器信息文档（除时钟之外的每个字段）。
- `F01.uptime-restart`：`uptime` 在进程生存期间增长，并在重新启动后从零开始。
- `F01.idle-time`：`idle_time` 在没有任何反应时增长，并在文件操作运行时重置。
- `F01.openapi`：`GET /openapi.json` 为 OpenAPI 文档提供会话路由，但不包含 WebSockets。
- `F01.static-files`: `static_files_path`设置为一个现有的目录，`GET /`返回302，`/static/index.html`（或`/static/`没有`index.html`）；`/static/*`不使用会话密钥服务目录，拒绝逃逸它，`/api/*`仍然需要密钥，`/server_info`没有改变。 丢失的目录保留 `/` 作为服务器信息。
- `F01.debug-tracebacks`：`DEBUG=true` 5xx 主体在 `detail` 和 `exception` 旁边带有 `traceback`； 没有它，或者在 4xx 上，它不会。
- `F01.preload-tools`：`preload_tools` 打开时，启动会在 `/ready` 回答 200 之前运行工具预加载； 当服务器找不到Chromium时，预加载失败，记录并跳过，但服务器仍然提供服务，并且有Chromium时，预加载成功。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /alive`、`GET /health`、`GET /ready`（Kubernetes型探针； 启动器和 `doctor` 使用它们）、`GET /server_info` 和 `GET /`。
- REST: `GET /openapi.json`; `/docs` 和 `/redoc` 为人类渲染它（未映射）。
- 静态挂载：`GET /static/{path}`，仅当 `static_files_path` (env `OH_STATIC_FILES_PATH`) 命名现有目录时出现； 它是一个 Starlette 的 mount，所以 `map routes` 不会列出它。 `scripts/agent_server_ui/run.sh` 使用它来提供捆绑的 UI。
- 配置：`preload_tools`（环境`OH_PRELOAD_TOOLS`，生产中默认`true`； `launch` 写入 `false`，除非 `--preload-tools`），并且进程环境变量 `DEBUG`（在导入时读取一次）
  `openhands.sdk.logger`; Docker 运行时将其转发到容器中）。
- SDK: `RemoteWorkspace` 健康检查和 Docker/API 工作区民意调查
  使用服务器之前的`/alive`和`/ready`； Agent Canvas 读
  `/server_info` 控制 `capabilities` 和版本上的功能。
- TypeScript客户端：`clients/typescript/src/generated/`中生成的模式是根据固定服务器版本的OpenAPI文档构建的。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已实时并导出 (`launch --new`)，`doctor` 可以。 不需要 LLM 配置文件。
- 命令从存储库根运行，因此 `git rev-parse HEAD` 命名所提供的结账。 `jq` 已安装。
- 静态文件、DEBUG 和预加载项目符号重新启动运行
  `--config-json`/`--env` 并以 `restart --reset-config` 结尾，所以它们排在最后。 下面的块创建每个项目符号写入的运行拥有的测试夹具目录（绝不是共享的 `/tmp` 路径）。
  ```sh
  F01="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f01"
  mkdir -p "$F01"
  ```

- **活跃度 (`F01.alive`).**无需钥匙的探头； 受保护的路由拒绝相同的无密钥请求，因此身份验证打开。
  ```sh
  control-agent-server api GET /api/conversations/count --auth none --expect 401
  control-agent-server api GET /alive --auth none --expect 200 --check status eq ok --save F01.alive/alive
  ```
  受保护路由为`401`； `/alive` 和 `200`，尽管没有发送 `{"status": "ok"}`。
- **健康 (`F01.health`).**无需钥匙即可探测。
  ```sh
  control-agent-server api GET /health --auth none --expect 200 --check status eq ok --save F01.health/health
  ```
  状态为`200`，内容为`{"status": "ok"}`。
- **准备就绪 (`F01.ready`).**启动后无需钥匙即可探测。
  ```sh
  control-agent-server api GET /ready --auth none --expect 200 --check status eq ready --save F01.ready/ready
  ```
  身体是b`{"status": "ready"}`。
- **服务器信息(`F01.server-info`)。**无需密钥即可读取构建标识和功能。
  ```sh
  control-agent-server api GET /server_info --auth none --expect 200 \
    --check build_git_sha eq "$(git rev-parse HEAD)" \
    --check capabilities contains idempotent_conversation_create_v1 \
    --check capabilities contains tool_catalog_v1 \
    --check capabilities contains agent_launch_pipeline_v1 \
    --check capabilities contains profile_public_skills_v1 \
    --check usable_tools contains terminal \
    --check conversation_runtime eq local \
    --check sdk_version exists --save F01.server-info/info
  ```
  每一张支票都通过了； 保存的主体也包含 `version` 和 `tools_version`
  `workspace_version`.
- **根别名 (`F01.root-info`).** `/` 提供相同的文档。
  ```sh
  control-agent-server api GET /server_info --auth none --expect 200 --quiet --raw-out "$F01/server_info.json"
  control-agent-server api GET / --auth none --expect 200 --check build_git_sha eq "$(git rev-parse HEAD)" \
    --raw-out "$F01/root.json" --save F01.root-info/root
  diff <(jq -S 'del(.uptime, .idle_time)' "$F01/server_info.json") <(jq -S 'del(.uptime, .idle_time)' "$F01/root.json")
  ```
  `diff` 不打印任何内容：除了两个时钟之外，两个主体都是相同的。
- **重新启动后的正常运行时间 (`F01.uptime-restart`)。**服务器自己的时钟正在接受测试，所以这颗子弹休眠了。
  ```sh
  U0=$(control-agent-server api GET /server_info --auth none --field uptime)
  sleep 3
  U1=$(control-agent-server api GET /server_info --auth none --check uptime gt "$U0" --check uptime ge 3 --field uptime)
  T0=$SECONDS
  control-agent-server restart
  control-agent-server api GET /server_info --auth none --check uptime lt "$U1" --check uptime le "$((SECONDS - T0))" \
    --save F01.uptime-restart/after-restart
  control-agent-server doctor
  ```
  `uptime` 在整个睡眠过程中增长，`U1` 至少为 `3.0`； 重启后
  `uptime` 不大于自重新启动开始以来的秒数（未重新启动的时钟至少会大 `U1`），并且 `doctor` 再次正常。
- **空闲时间(`F01.idle-time`)。**状态探测不是活动； 文件操作是。
  ```sh
  rm -rf "$F01/idle"
  sleep 3
  I1=$(control-agent-server api GET /server_info --auth none --field idle_time)
  control-agent-server api GET /server_info --auth none --check idle_time ge 3
  test ! -e "$F01/idle"
  control-agent-server api POST /api/file/create_directory --query "path=$F01/idle" --expect 200
  test -d "$F01/idle"
  control-agent-server api GET /server_info --auth none --check idle_time lt "$I1" --save F01.idle-time/after-mkdir
  ```
  `idle_time` 至少 `3.0`，尽管在之间运行了探针，目录在之前不存在，之后在磁盘上存在，`idle_time` 在创建后消失。
- **OpenAPI文档(`F01.openapi`).**客户生成的合同。
  ```sh
  control-agent-server api GET /openapi.json --auth none --expect 200 --max-chars 200 \
    --check 'paths./api/conversations.post.operationId' matches start_conversation \
    --check 'paths./api/conversations/{conversation_id}/pause' exists \
    --check 'paths./sockets/events/{conversation_id}' missing --save F01.openapi/openapi
  ```
  所有的检查都通过了。 WebSockets 都不是我们的一部分 OpenAPI 文档。
  `control-agent-server map routes --module sockets` 列出了它们。
- **静态文件(`F01.static-files`)。**在运行拥有的目录上使用 `static_files_path` 重新启动，无需密钥读取它，尝试转义它，删除
  `index.html`，然后将设置指向丢失的目录并恢复。
  ```sh
  S="$F01/static"
  mkdir -p "$S"
  printf '<!doctype html><title>qa-f01</title>QA_F01_STATIC\n' > "$S/index.html"
  printf '{"qa": "f01-static"}\n' > "$S/qa.json"
  printf '{"qa": "f01-outside"}\n' > "$F01/server_info"
  M=/static  # 挂载，而不是路线：地图检查无法匹配其路径，因此它们通过变量
  control-agent-server restart --config-json "{\"static_files_path\": \"$S\"}"
  control-agent-server api GET / --auth none --expect 302 --check-header location eq /static/index.html \
    --save F01.static-files/root-redirect
  control-agent-server api GET "$M/index.html" --auth none --expect 200 --check-header content-type contains text/html \
    --raw-out "$F01/index.got"
  cmp "$S/index.html" "$F01/index.got"
  control-agent-server api GET "$M/qa.json" --auth none --expect 200 --check qa eq f01-static --save F01.static-files/file
  control-agent-server api GET "$M/%2e%2e/server_info" --auth none --expect 404 --save F01.static-files/escape
  control-agent-server api GET /api/conversations/count --auth none --expect 401
  control-agent-server api GET /api/conversations/count --expect 200
  control-agent-server api GET /server_info --auth none --expect 200 --check build_git_sha eq "$(git rev-parse HEAD)" \
    --check capabilities contains tool_catalog_v1
  mv "$S/index.html" "$S/index.moved"
  control-agent-server api GET / --auth none --expect 302 --check-header location eq /static/ --save F01.static-files/no-index
  control-agent-server api GET "$M/" --auth none --expect 404
  mv "$S/index.moved" "$S/index.html"
  control-agent-server restart --config-json "{\"static_files_path\": \"$F01/static-missing\"}"
  control-agent-server api GET / --auth none --expect 200 --check build_git_sha eq "$(git rev-parse HEAD)" \
    --save F01.static-files/missing-dir
  control-agent-server api GET "$M/qa.json" --auth none --expect 404
  control-agent-server restart --reset-config
  control-agent-server api GET / --auth none --expect 200 --check title eq 'OpenHands Agent Server'
  ```
  `/` 是 302 到 `/static/index.html`，两个静态文件都是逐字节提供的，无需密钥。 转义尝试是 404：服务器将其解码为 `/static/../server_info`，挂载拒绝（它将服务
  `qa-f01/server_info` 如果它遵循 `..`，并且规范化路径的客户端或路由器将到达真实的 `/server_info`，无论哪种方式都是 200）。
  `/api/*` 仍然拒绝无密钥调用并接受运行密钥，并且
  `/server_info` is unchanged. 没有 `index.html` 重定向目标
  `/static/`，即 404（挂载不渲染目录索引）。 不存在的 `static_files_path` 将 `/` 保留为服务器信息并且不安装任何内容。
- **DEBUG 回溯 (`F01.debug-tracebacks`).**有意的 5xx（工作区注册表文件被目录替换，如 `F17.io-error` 中）在使用和不使用 `DEBUG` 的情况下进行读取。
  ```sh
  WS="$AGENT_SERVER_VERIFY_RUN/home/.openhands/workspaces.json"
  test ! -e "$WS"
  mkdir -p "$WS"
  control-agent-server api GET /api/workspaces --expect 500 --check exception contains 'Failed to read workspaces' \
    --check traceback missing --save F01.debug-tracebacks/off
  N=$(control-agent-server logs --grep 'DEBUG mode: ENABLED' | jq .total_matching)
  control-agent-server restart --env DEBUG=true
  control-agent-server logs --grep 'DEBUG mode: ENABLED' --expect-min $((N + 1))
  control-agent-server api GET /api/workspaces --expect 500 --check detail eq 'Internal Server Error' \
    --check exception contains 'Failed to read workspaces' \
    --check traceback contains 'HTTPException: 500: Failed to read workspaces' --save F01.debug-tracebacks/on
  control-agent-server api GET /api/conversations/count --auth none --expect 401 --check traceback missing
  control-agent-server restart --reset-config
  control-agent-server api GET /api/workspaces --expect 500 --check traceback missing
  rmdir "$WS"
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 0
  ```
  缺少`DEBUG`，500状态码仅包含`detail`、`exception`和其它。 与
  `DEBUG=true`服务器打印`DEBUG mode: ENABLED`并且同样的500添加了一个
  `traceback` 字符串，其最后一行是 `HTTPException`，而 401 仍然是 `{"detail": ...}`。 在 `--reset-config` 之后，跟踪再次消失，并且一旦删除目录，注册表就会正常读取。
- **刀具预紧 (`F01.preload-tools`).**打开 `preload_tools` 重新启动，首先使用服务器自己找到的任何 Chromium，然后将计算机的 Chromium 链接到运行的 Playwright 缓存（当计算机有一个缓存时），然后恢复。
  ```sh
  control-agent-server logs --grep 'Tool preload service is disabled' --expect-min 1
  STARTED=$(control-agent-server logs --grep 'Tool preload service started' | jq .total_matching)
  FAILED=$(control-agent-server logs --grep 'Tool preload service failed to start' | jq .total_matching)
  control-agent-server restart --config-json '{"preload_tools": true}'
  control-agent-server config | jq -e '.config_file.preload_tools == true'
  control-agent-server api GET /ready --auth none --expect 200 --check status eq ready --save F01.preload-tools/ready
  control-agent-server api GET /api/conversations/count --expect 200
  if control-agent-server api GET /server_info --auth none --check usable_tools not-contains browser_tool_set >/dev/null; then
    control-agent-server logs --grep 'Tool preload service failed to start' --expect-min $((FAILED + 1))
    control-agent-server logs --grep 'Error preloading' --expect-min 1
    test "$(control-agent-server logs --grep 'Tool preload service started' | jq .total_matching)" -eq "$STARTED"
  else
    control-agent-server logs --grep 'Tool preload service started' --expect-min $((STARTED + 1))
  fi
  if [ "$(control-agent-server capabilities | jq -r '.machine.chromium.available')" = true ]; then
    CHROME=$(control-agent-server capabilities | jq -r '.machine.chromium.detail')
    PW="$AGENT_SERVER_VERIFY_RUN/home/.cache/ms-playwright/chromium-qa-f01"
    mkdir -p "$PW/chrome-linux"
    ln -sfn "$(readlink -f "$CHROME")" "$PW/chrome-linux/chrome"
    test -x "$PW/chrome-linux/chrome"
    STARTED=$(control-agent-server logs --grep 'Tool preload service started' | jq .total_matching)
    control-agent-server restart
    control-agent-server logs --grep 'Tool preload service started' --expect-min $((STARTED + 1))
    control-agent-server logs --grep 'Chromium is available' --expect-min 1
    control-agent-server api GET /ready --auth none --expect 200 --check status eq ready --save F01.preload-tools/ready-chromium
    rm -r "$PW"
  fi
  control-agent-server restart --reset-config
  control-agent-server config | jq -e '.config_file.preload_tools == false'
  ```
  在子弹之前，日志显示预加载已禁用。 然后所取的计数使得之后的每一条日志检查都关于随后的重启。 与
  `preload_tools`开启，重启（等待`/ready`）返回，`/ready`为200，`/api/*`发球。 找不到 Chromium 的服务器（没有
  `usable_tools`中的`browser_tool_set`； 在这台机器上，唯一的 Chromium 位于 `$PLAYWRIGHT_BROWSERS_PATH` 下，`launch` 不会传递）使用安装提示和 `Tool preload service failed to start - skipping` 记录 `Error preloading chromium`，并且仍然可以使用。 将机器的 Chromium 链接到运行的 `~/.cache/ms-playwright` 后，下一个启动日志 `Chromium is available for browser operations` 和另一个 `Tool preload service started successfully`。 最后重启又写`preload_tools: false`。

<a id="gotchas"></a>

## 陷阱

- `/ready` 返回 503 `{"status": "initializing"}` 直到启动完成（工具预加载、VS Code）； `launch` 等待它，因此启动运行时出现 503 意味着出现问题。 在 deferred-init 模式下 `/ready` 为 200，而 pod 仍处于休眠状态（可放置）； `GET /api/init` 报告真实状态（请参阅延迟 init 系列）。
- `idle_time` 仅在会话事件（除了状态更新）和bash命令的启动、执行和停止、文件上传、下载、目录创建和归档，以及git更改和差异路由上重置。 不在状态探测或其他读取上。 编排者使用它来获取闲置的沙箱。
- `build_git_sha` 和 `build_git_ref` 来自 `OPENHANDS_BUILD_GIT_SHA` 和
  `OPENHANDS_BUILD_GIT_REF`; `launch` 从结账时设置它们。 服务器以另一种方式启动报告 `unknown`，这就是为什么 `doctor` 仅比较已启动的运行的 SHA。
- `uptime` 和 `idle_time` 是整秒已序列化作为浮点数 (`12.0`)； 将它们与 `--check ... lt` 进行比较，而不是与 shell 的整数 `test` 进行比较。
- 点式 `--check` 和 `--field` 路径可以包含斜杠和大括号 (`paths./api/conversations.post`)，因为只有点分隔段。
- `static_files_path` 在启动时检查一次：稍后创建的目录需要重新启动，而 `index.html` 在每个 `GET /` 上查找。 的
  `/static` mount 位于每个身份验证组之外，因此该目录中的任何内容都是公共的。
- 预加载仅检查 Chromium 并构建浏览器执行器和工具操作类型； 它不启动浏览器进程（浏览器在第一个浏览器操作时启动）。 失败的预加载永远不会阻止启动，但转义预加载任务的异常会（`api.py` 重新引发它）。 服务器日志有 80 列，因此 grep 可以显示短语（`Tool preload service started`，而不是整个句子）。
- `DEBUG`在导入时被读取一次，并且还将日志级别变为`DEBUG`； 它会泄漏 5xx 主体中的文件路径和源代码行，因此它永远不会用于生产。 未处理的异常在其 `error_id` 旁边获得相同的 `traceback` 字段； 地图上未处理的 500 要么需要对话，要么是已知的错误，因此这个家族驾驶的是 deliberate `HTTPException` 500，最便宜的稳定 5xx。
