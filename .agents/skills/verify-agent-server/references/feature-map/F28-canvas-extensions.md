<a id="canvas-apps-install-catalog-and-backend-lifecycle"></a>

# Canvas 应用程序：安装、目录和后端生命周期

Agent Canvas 应用程序（“画布扩展”）是服务器安装的 UI 捆绑包，
服务：具有 `canvas-extension.json` 清单 (模式 1) 的目录，
入口捆绑包、可选的 SVG 图标和可选的后端。 消费者从本地目录、git URL（包括 `file://`）或
`github:owner/repo` 简写； 它总是被禁用，由清单的 `name` 键入，并在每次读取时从磁盘重新验证其清单。 捆绑包和图标按字节提供。 声明了 `backend` 的应用会获得一个明确的、修订锁定的生命周期：`GET .../backend` 报告状态和修订号，`prepare` 验证其 sha256 哈希并提取它只读（批准），`start` 在自己的进程组中运行准备好的修订，只使用 `HOME`（加上 manifest 要继承的允许列表变量）作为环境变量，等待健康检查，`stop` 杀死组，`logs` 返回有界标准输出和标准错误
`DELETE .../backend/data` 擦除应用程序的可变数据。 重新启动后的安装和批准持久化； 运行后端则不会。

资料来源：`openhands-agent-server/openhands/agent_server/canvas_extensions_router.py`、`openhands-agent-server/openhands/agent_server/canvas_extensions/`、`openhands-sdk/openhands/sdk/extensions/`

需求：`git`、`node`

发射：`--env TZ=UTC`

Routes: `POST /api/canvas-extensions/install`, `GET /api/canvas-extensions/installed`,
`GET /api/canvas-extensions/installed/{extension_name}`,
`PATCH /api/canvas-extensions/installed/{extension_name}`,
`DELETE /api/canvas-extensions/installed/{extension_name}`,
`GET /api/canvas-extensions/installed/{extension_name}/backend`,
`POST /api/canvas-extensions/installed/{extension_name}/backend/prepare`,
`POST /api/canvas-extensions/installed/{extension_name}/backend/start`,
`POST /api/canvas-extensions/installed/{extension_name}/backend/stop`,
`GET /api/canvas-extensions/installed/{extension_name}/backend/logs`,
`DELETE /api/canvas-extensions/installed/{extension_name}/backend/data`,
`GET /api/canvas-extensions/installed/{extension_name}/bundle`,
`GET /api/canvas-extensions/installed/{extension_name}/icon`

<a id="sub-features"></a>

## 子功能

- `F28.install-local` 从本地目录安装时，会返回 200 状态码，即使身体说 `"enabled": true`，`resolved_ref` null 和验证过的 manifest，会将其复制到 `canvas-extensions/installed/<name>/`，并记录在 `.installed.json`，并且列表和 GET 视图都一致。
- `F28.install-git`：`file://` git URL 作为 git 源安装：`resolved_ref` 是存储库的 HEAD 提交，克隆缓存在 `cache/extensions/` 下。
- `F28.install-ref`: `ref`将git安装固定在该提交上(`version`和`resolved_ref`是被固定提交的，`.installed.json`记录了`requested_ref`），强制安装，没有`ref`，移动到分支头，源中从未被拉取的未知引用返回400并安装了什么。
- `F28.install-repo-path`：`repo_path`安装源的子目录并回显； 缺少子目录或转义源的子目录为 400，没有清单的源根目录为 422。
- `F28.install-errors`：无法读取的源为 400（缺少路径、无法解析的字符串、错误的 `github:` 简写、非存储库的 `file://` URL）、丢失或空的 `source` 或无效清单（错误的 JSON、错误的名称、转义或丢失入口、错误的 `schema_version`）为 422，没有密钥为 401，并且未安装任何内容。
- `F28.bundle`: `GET .../bundle` 以 `Cache-Control: no-cache`、`ETag` 和 JavaScript 内容类型逐字节服务已安装的入口，无论应用程序是否启用。
- `F28.icon`：`GET .../icon` 将声明的 SVG 逐字节服务为 `image/svg+xml`，并带有沙箱 CSP 和 `nosniff`； 没有图标的应用程序是 404。
- `F28.enable-disable`：`PATCH .../installed/{name}`切换`enabled`，GET和`.installed.json`都显示新值； 非布尔体是 422。
- `F28.unknown-name`：GET、PATCH、DELETE、包和图标上的未知名称为 404，每条路由上的非短横线命名为 422，并且路由需要会话密钥。
- `F28.list-discovery`一个有效的应用目录复制到 `installed/` 手动操作是不可见的 GET 直到一个列表调用注册为止，才按名称进行。  `source`  `local`), 并且一个列表调用会修剪一个目录被删除的条目。
- `F28.broken-install`：已安装的应用程序，其清单停止验证，或其入口成为包外的符号链接，仍与 `manifest` null 一起列出； 它的捆绑包和图标是 404，其后端报告 `missing`，而 PATCH 和 DELETE 仍然有效。 当清单和捆绑包保持有效时，成为包外符号链接的图标为 404。
- `F28.backend-status`: `GET .../backend` reports `missing` 对于未知的名字， `unsupported` 仅限浏览器的应用 `stopped` 修订版的后端应用（`sha256:<hex>` 本地安装的 manifest 中的 commit SHA 对于 Git 安装，永远不要 404。
- `F28.backend-approval-gate`：开始准备一个未准备的修订、准备一个错误的修订、准备一个被篡改的归档、准备一个带有转义成员的归档以及准备一个远程(`url`)无法下载的文件，所有这些都返回409，其中(None)个写入了批准或提取或保留了一个文件。
- `F28.backend-prepare`：准备当前修订版本时会验证校验和，提取该文件到一个只读 `artifacts/<name>/<sha256>/` 目录中，记录批准（显示为 `prepared_revision`），并且是幂等的。
- `F28.backend-start`：启动准备好的修订版本返回`ready`，并带有 pid 和端口； 后端在 `127.0.0.1:<port>` 上回答，从已安装的包目录在其自己的进程组中运行，其环境中仅 `HOME=<data>/home`； 重复启动会保持相同的 pid，不同的修订版是 409，强制安装或数据删除在运行时是 409。
- `F28.backend-stop`：`POST .../backend/stop`杀死进程组（后端分叉的子进程也死亡）并报告`stopped`； 港口关闭，第二站是无害的 200。
- `F28.force-reinstall`：安装已安装的应用程序，如果没有`force`，则为409，并且记录不变； `force: true` 替换文件（新的包字节和 ETag，新的 `installed_at`），保留之前的 `enabled` 值，删除后端审批，因此修订必须重新准备。
- `F28.backend-logs`: 当一个后端 `starting` stdout 和 stderr 的行是可读的 `[stdout] `/`[stderr] ` prefixes; `停止 ` abandons the pending start, the logs stay readable after it, `limit_bytes` bounds the tail and sets ` 被截断，值不在 1..262144 范围内为 422，而未知的应用没有日志。
- `F28.ts-client`: the TypeScript  `CanvasExtensionsClient` 将后端应用带入 `getBackendStatus`, `prepareBackend`, `startBackend`, `getBackendLogs`, `stopBackend` 和 `deleteBackendData` with the REST 结果、拒绝和拒绝作为 `HttpError` 带有服务器状态和详细信息，以及客户端超时短于后端健康检查的等待拒绝 `startBackend` 尽管服务器仍在后端 `starting`.
- `F28.backend-start-fails`：一个健康检查永远通过的后端 `unhealthy` 结束，`backend health check timed out` 一个在 `health.timeout_seconds` 后结束的，一个在退出时结束的，`unhealthy` 一个没有留下进程。
- `F28.backend-inherit-environment`：后端要求继承允许列表 (`OH_SECRET_KEY`) 之外的变量或命名 1 两次的清单在安装时被拒绝，返回值是 422，并且请求 `PATH`、`TZ` 和 `LANG` 的后端运行时恰好是 `HOME` 加上它所拥有的服务器值，即服务器的机密的 None。
- `F28.disable-stops-backend`：禁用正在运行的后端的应用程序会停止其进程组，并且后端报告`stopped`。
- `F28.restart-persistence` 在优雅重启后，安装、它们的`enabled` 值和后端审批仍然存在，但正在运行的后端已经消失了，`start` 仍然可以正常工作，没有新的`prepare`。
- `F28.uninstall`: `DELETE .../installed/{name}` 停止后端，移除包及其记录，保留后端数据、审批和成果，报告后端 `missing`, and a second DELETE 404; `DELETE .../backend/data` 然后删除数据目录。
- `F28.prepare-corrupt-archive`：非 gzip 存档且具有匹配 sha256 的工件会像任何其他不良工件一样被拒绝并返回 409。
- `F28.install-ref-cached`：未知的 `ref` 为 400，即使源的克隆已缓存，也不会影响已安装的应用程序。
- `F28.status-probe-latch`：一个后端服务因错过一次状态健康探针（它比1秒探针慢超时）而被报告 `ready` 一次，该后端服务在回答健康检查时再次被报告。
- `F28.status-exit-hang`：当后端的领导者进程退出而其分叉的子进程仍保留其标准输出时，`GET .../backend` 立即用 `unhealthy` 进行响应，`stop` 收获该子进程。
- `F28.hard-restart-orphan`当服务器运行时正在运行的后端 SIGKILLed 无法在服务器重启后存活。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST（目录）：`POST /api/canvas-extensions/install` 与
  `{"source", "ref", "repo_path", "force"}`, `GET /api/canvas-extensions/installed`,
  `GET|PATCH|DELETE /api/canvas-extensions/installed/{extension_name}`（`PATCH`主体`{"enabled": bool}`）、`GET .../bundle`和`GET .../icon`。 这里的每个食谱都直接驱动这些路线。
- REST（后端生命周期）：`GET .../backend`、`POST .../backend/prepare` 和
  `POST .../backend/start`（均为`{"revision": "<GET .../backend .revision>"}`），
  `POST .../backend/stop`、`GET .../backend/logs?limit_bytes=N` 和
  `DELETE .../backend/data`. 也可以直接驾驶。
- TypeScript 客户端：`OpenHandsClient.canvasExtensions`（`clients/typescript/src/client/canvas-extensions-client.ts` 中的 `CanvasExtensionsClient`）有
  `getBackendStatus`, `prepareBackend`, `startBackend`, `stopBackend`,
  `getBackendLogs`和`deleteBackendData`； 它没有安装、列出、启用、卸载、捆绑或图标方法。 它的默认 60 秒超时可以比清单的 `health.timeout_seconds` 短（最多 300 秒）：`startBackend` 然后在服务器保持启动的同时在客户端上拒绝。 驱动力
  `F28.ts-client`来自构建的`clients/typescript/dist`。 其
  `createAppBackendSession`/`revokeAppBackendSession`属于桥族(F29)。
- PythonSDK：无消费者； 路线环绕
  `openhands.agent_server.canvas_extensions.installed` 和 SDK 的通用
  `InstallationManager`（与插件和技能共享）。
- Agent Canvas 上下文只有：Canvas前端安装和切换应用，加载 `bundle` 和 `icon`，并在通过 `/app-backends` 桥接（另一个家族）将浏览器路由到后端之前运行准备和启动流程。
- 配置：所有内容都位于 `OH_PERSISTENCE_DIR` 下（`canvas-extensions/installed`、`canvas-extensions/backends/{approvals,artifacts,data,downloads,run}`、
  `cache/extensions`)，其中 `launch` 使运行 (`home/.openhands`) 私有。 后端仅在 Linux amd64/arm64 上运行。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行是实时的并已导出（`launch --new --env TZ=UTC`，系列的 `Launch:` 标志），`doctor` 可以。 不需要LLM配置文件； `git`和`python3`在`PATH`上。
- 测试夹具，全部由运行拥有：`fixture canvas-app --name qa-canvas`（仅限浏览器，带有图标； git 存储库），`--name qa-backend --backend ok`（带有 `/health` 和 echo 路由的 aiohttp 后端工件），
  `--name qa-unhealthy --backend unhealthy`（健康答案503）和
  `--name qa-exit --backend exit`（以代码 3 退出）。 CLI 没有测试夹具用于打印和挂起的后端，用于带有转义成员的档案，或者用于不是 gzip 的艺术品，因此下面的块会将小应用程序写入 `fixtures/f28/`，使用 Python 的这里行：`qa-f28-logs`（打印每条流的一行，然后无服务地睡眠 HTTP），`qa-f28-unsafe`（一个
  `../qa-f28-escape` 成员）、`qa-f28-notgz`（纯字节，正确的 sha256）和
  `qa-f28-flaky`（一个 stdlib HTTP 后端，其 `/slow` 和 `/fast` 路由使其运行状况检查需要 2 秒或立即回答，其 `/fork` 路由启动一个
  `/bin/sleep 300` 孩子共享其标准输出，并打印出孩子的进程 ID，以及 `/exit` 路由杀死领导者而没有回答的 `qa-f28-env`（同服务器，要求继承 `PATH`、`TZ` 和 `LANG`），`qa-f28-env-secret` 和 `qa-f28-env-dup`（要求 `OH_SECRET_KEY`，以及 `TZ` 两次）和
  `qa-f28-remote`（闭合环回 HTTPS 端口上的远程 `url` 工件）。 该系列以 `TZ=UTC` (`Launch:`) 启动，因此服务器有一个 `TZ` 来
  pass on. `node` runs the TypeScript client from `clients/typescript/dist`
  （没有它的签出会使用 `npm ci && npm run build` 构建它，这需要 npm 注册表）。 它还提交了一个两次提交的 git 应用程序 `qa-f28-git`（清单 `1.0.0`，然后 `2.0.0`）
  `ref` 个项目符号，其中 `GV1` 和 `GV2` 命名了两个提交。
  ```sh
  FX=$(control-agent-server fixture canvas-app --name qa-canvas --print-path)
  BX=$(control-agent-server fixture canvas-app --name qa-backend --backend ok --print-path)
  UX=$(control-agent-server fixture canvas-app --name qa-unhealthy --backend unhealthy --print-path)
  EX=$(control-agent-server fixture canvas-app --name qa-exit --backend exit --print-path)
  F28FX="$AGENT_SERVER_VERIFY_RUN/fixtures/f28"
  python3 - "$F28FX" <<'PY'
  import hashlib, io, json, pathlib, sys, tarfile
  root = pathlib.Path(sys.argv[1])
  def targz(*members):
      buffer = io.BytesIO()
      with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
          for name, data in members:
              info = tarfile.TarInfo(name)
              info.size, info.mode = len(data), 0o755
              tar.addfile(info, io.BytesIO(data))
      return buffer.getvalue()
  def app(name, archive, argv=("{artifact_dir}/run.sh", "{port}"), inherit=None):
      pkg = root / name
      (pkg / "dist").mkdir(parents=True, exist_ok=True)
      (pkg / "backend").mkdir(exist_ok=True)
      (pkg / "dist" / "index.js").write_text(f"export const app = {name!r};\n")
      (pkg / "backend" / "linux.tar.gz").write_bytes(archive)
      artifact = {"path": "backend/linux.tar.gz", "sha256": hashlib.sha256(archive).hexdigest()}
      manifest = {"schema_version": 1, "name": name, "display_name": name, "version": "0.1.0",
                  "entrypoint": "dist/index.js",
                  "backend": {"schema_version": 1,
                              "artifacts": {"linux-amd64": artifact, "linux-arm64": artifact},
                              "argv": list(argv),
                              "health": {"path": "/health", "timeout_seconds": 30, "interval_seconds": 0.2}}}
      if inherit is not None:
          manifest["backend"]["inherit_environment"] = list(inherit)
      (pkg / "canvas-extension.json").write_text(json.dumps(manifest, indent=2))
  app("qa-f28-logs", targz(("run.sh", b"#!/bin/sh\necho qa-f28-out\necho qa-f28-err >&2\nexec /bin/sleep 120\n")))
  app("qa-f28-unsafe", targz(("run.sh", b"#!/bin/sh\n"), ("../qa-f28-escape", b"x\n")))
  app("qa-f28-notgz", b"qa-f28 plain bytes, not a gzip archive\n")
  FLAKY = '''
  import http.server, os, subprocess, sys, time
  slow = False
  class Handler(http.server.BaseHTTPRequestHandler):
      def do_GET(self):
          global slow
          if self.path == "/exit":
              os._exit(0)
          slow = {"/slow": True, "/fast": False}.get(self.path, slow)
          body = b"ok"
          if self.path == "/fork":
              body = str(subprocess.Popen(["/bin/sleep", "300"]).pid).encode()
          if self.path == "/health" and slow:
              time.sleep(2)
          self.send_response(200)
          self.end_headers()
          self.wfile.write(body)
      def log_message(self, *args):
          pass
  http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
  '''
  app("qa-f28-flaky", targz(("run.py", f"#!{sys.executable}\n{FLAKY}".encode())), argv=("{artifact_dir}/run.py", "{port}"))
  for env_app, names in (("qa-f28-env", ["PATH", "TZ", "LANG"]), ("qa-f28-env-secret", ["TZ", "OH_SECRET_KEY"]),
                         ("qa-f28-env-dup", ["TZ", "TZ"])):
      app(env_app, targz(("run.py", f"#!{sys.executable}\n{FLAKY}".encode())), argv=("{artifact_dir}/run.py", "{port}"),
          inherit=names)
  remote = root / "qa-f28-remote"
  (remote / "dist").mkdir(parents=True, exist_ok=True)
  (remote / "dist" / "index.js").write_text("export const app = 'qa-f28-remote';\n")
  unreachable = {"url": "https://127.0.0.1:9/qa-f28.tar.gz", "sha256": "0" * 64}
  (remote / "canvas-extension.json").write_text(json.dumps({
      "schema_version": 1, "name": "qa-f28-remote", "display_name": "qa-f28-remote", "version": "0.1.0",
      "entrypoint": "dist/index.js",
      "backend": {"schema_version": 1, "argv": ["{artifact_dir}/run.sh"],
                  "artifacts": {"linux-amd64": unreachable, "linux-arm64": unreachable}}}))
  PY
  P="$AGENT_SERVER_VERIFY_RUN/home/.openhands"
  INST="$P/canvas-extensions/installed"
  BK="$P/canvas-extensions/backends"
  BHEAD=$(git -C "$BX" rev-parse HEAD)
  BSHA=$(sha256sum "$BX/backend/linux.tar.gz" | cut -d' ' -f1)
  test -f "$F28FX/qa-f28-notgz/canvas-extension.json" && test -f "$F28FX/qa-f28-flaky/canvas-extension.json"
  GX="$F28FX/qa-f28-git"
  if [ ! -d "$GX/.git" ]; then
    mkdir -p "$GX/dist" && printf 'export const v = 1;\n' > "$GX/dist/index.js"
    printf '{"schema_version": 1, "name": "qa-f28-git", "display_name": "QA git", "version": "1.0.0", "entrypoint": "dist/index.js"}' > "$GX/canvas-extension.json"
    git -C "$GX" init -q -b main && git -C "$GX" add -A
    git -C "$GX" -c user.name=QA -c user.email=qa@example.invalid -c commit.gpgsign=false commit -qm v1
    sed -i 's/"1.0.0"/"2.0.0"/' "$GX/canvas-extension.json"
    git -C "$GX" -c user.name=QA -c user.email=qa@example.invalid -c commit.gpgsign=false commit -qam v2
  fi
  GV1=$(git -C "$GX" rev-parse HEAD~1)
  GV2=$(git -C "$GX" rev-parse HEAD)
  ```

- **从本地目录安装 (`F28.install-local`)。**安装仅浏览器的应用程序，其主体要求 `enabled: true`。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$FX\", \"enabled\": true}" \
    --expect 200 --check name eq qa-canvas --check enabled eq false --check resolved_ref eq null \
    --check source eq "$FX" --check install_path eq "$INST/qa-canvas" \
    --check manifest.contributes.pages.0.path eq /qa-canvas --check manifest.icon eq assets/icon.svg \
    --save F28.install-local/install
  AT0=$(control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --field installed_at)
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --expect 200 \
    --check enabled eq false --check manifest.display_name eq 'QA qa-canvas' --save F28.install-local/get
  control-agent-server api GET /api/canvas-extensions/installed --expect 200 --check canvas_extensions len-eq 1 \
    --check canvas_extensions.0.name eq qa-canvas --check canvas_extensions.0.enabled eq false --save F28.install-local/list
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json \
    --check extensions.qa-canvas.enabled eq false --check extensions.qa-canvas.installed_at eq "$AT0"
  cmp "$INST/qa-canvas/dist/index.js" "$FX/dist/index.js"
  ```
  安装回答200，并且body请求的是`enabled: false`
  `true`（该字段被忽略），GET、列表和`.installed.json`一致，并将包复制到`installed/qa-canvas/`下。
- **从 git 安装 URL (`F28.install-git`)。**安装后端应用程序
  from its `file://` URL.
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$BX\"}" \
    --expect 200 --check name eq qa-backend --check resolved_ref eq "$BHEAD" --check enabled eq false \
    --check source eq "file://$BX" --save F28.install-git/install
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend --check resolved_ref eq "$BHEAD"
  control-agent-server state ls 'home/.openhands/cache/extensions/qa-backend-*/canvas-extension.json' --expect-count 1
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json \
    --check extensions.qa-backend.resolved_ref eq "$BHEAD"
  ```
  `resolved_ref` 是响应中测试夹具的 HEAD 提交，GET 和
  `.installed.json`，并且一个克隆位于 `cache/extensions/qa-backend-<hash>/` 中。
- **固定 git 参考 (`F28.install-ref`)。**向 `qa-f28-git` 请求不存在的引用，固定其第一次提交，然后在没有引用的情况下重新安装它。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$GX\", \"ref\": \"qa-no-such-ref\"}" \
    --expect 400 --check detail contains 'Could not read canvas extension source' --save F28.install-ref/unknown-ref
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-git --expect 404
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$GX\", \"ref\": \"$GV1\"}" \
    --expect 200 --check name eq qa-f28-git --check version eq 1.0.0 --check resolved_ref eq "$GV1" \
    --check manifest.version eq 1.0.0 --save F28.install-ref/pinned
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-git --check version eq 1.0.0 --check resolved_ref eq "$GV1"
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json \
    --check extensions.qa-f28-git.requested_ref eq "$GV1" --check extensions.qa-f28-git.resolved_ref eq "$GV1"
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$GX\", \"force\": true}" \
    --expect 200 --check version eq 2.0.0 --check resolved_ref eq "$GV2" --save F28.install-ref/latest
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-git --check version eq 2.0.0 --check resolved_ref eq "$GV2"
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-git --expect 200
  ```
  在从未被获取的源中出现的未知引用返回 400 错误码 (`Could not read canvas extension source: Failed to fetch extension from file://...`)，且安装了什么也没有。 `ref` 设置为第一个提交，`1.0.0` 会安装为 `resolved_ref`，`requested_ref`。 强制安装而没有回退移动到分支尾端 (`2.0.0`)。 因此，因为应用程序再次卸载，所以目录计数没有改变。
- **安装子目录(`F28.install-repo-path`)。** `fixtures/f28/` 拥有多个应用程序，但没有自己的清单。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX\", \"repo_path\": \"qa-f28-logs\"}" \
    --expect 200 --check name eq qa-f28-logs --check repo_path eq qa-f28-logs --save F28.install-repo-path/install
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs --check repo_path eq qa-f28-logs
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX\", \"repo_path\": \"qa-f28-nope\"}" \
    --expect 400 --check detail contains 'not found' --save F28.install-repo-path/missing
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX\", \"repo_path\": \"../..\"}" \
    --expect 400 --check detail contains escapes --save F28.install-repo-path/escape
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX\"}" \
    --expect 422 --check detail contains canvas-extension.json --save F28.install-repo-path/root
  ```
  `qa-f28-logs`安装，`repo_path`被记录。 这三种不良变体分别是400 `... not found ...`、400 `... escapes ...`和422 `No canvas-extension.json found ...`。
- **安装错误 (`F28.install-errors`)。**无法阅读的来源、糟糕的身体和糟糕的清单； 不能安装任何东西。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json '{"source": "/nonexistent/qa-f28"}' \
    --expect 400 --check detail contains 'does not exist' --save F28.install-errors/missing-path
  control-agent-server api POST /api/canvas-extensions/install --json '{"source": "qa-not-a-source"}' \
    --expect 400 --check detail contains 'Unable to parse'
  control-agent-server api POST /api/canvas-extensions/install --json '{"source": "github:onlyowner"}' \
    --expect 400 --check detail contains 'Invalid GitHub shorthand'
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$F28FX\"}" --expect 400
  control-agent-server api POST /api/canvas-extensions/install --json '{"source": ""}' --expect 422
  control-agent-server api POST /api/canvas-extensions/install --json '{}' --expect 422 --check detail.0.loc.1 eq source
  BAD="$F28FX/qa-f28-bad"
  mkdir -p "$BAD/dist" && printf 'x\n' > "$BAD/dist/index.js"
  printf '{bad' > "$BAD/canvas-extension.json"
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$BAD\"}" \
    --expect 422 --check detail contains 'Invalid canvas extension' --save F28.install-errors/bad-json
  for MANIFEST in \
    '{"schema_version": 1, "name": "Bad_Name", "display_name": "x", "version": "1", "entrypoint": "dist/index.js"}' \
    '{"schema_version": 1, "name": "qa-f28-bad", "display_name": "x", "version": "1", "entrypoint": "../outside.js"}' \
    '{"schema_version": 1, "name": "qa-f28-bad", "display_name": "x", "version": "1", "entrypoint": "dist/missing.js"}' \
    '{"schema_version": 2, "name": "qa-f28-bad", "display_name": "x", "version": "1", "entrypoint": "dist/index.js"}'; do
    printf '%s' "$MANIFEST" > "$BAD/canvas-extension.json"
    control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$BAD\"}" \
      --expect 422 --check detail contains 'Invalid canvas extension' --quiet
  done
  control-agent-server api POST /api/canvas-extensions/install --auth none --json "{\"source\": \"$BAD\"}" --expect 401
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-bad --expect 404
  control-agent-server api GET /api/canvas-extensions/installed --check canvas_extensions len-eq 3
  test ! -e "$INST/qa-f28-bad"
  ```
  400系列包含 `Could not read canvas extension source: <reason>`, the Pydantic 422s name `source`每个坏的ifest都是422
  `Invalid canvas extension. Ensure the manifest is well-formed.`，并且目录仍然只包含三个早期的应用程序。
- **捆绑包 (`F28.bundle`).**下载（已禁用）应用程序的入口。
  ```sh
  BUNDLE="$AGENT_SERVER_VERIFY_RUN/fixtures/f28/bundle-v1.js"
  ETAG1=$(control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/bundle --expect 200 \
    --check-header cache-control eq no-cache --check-header content-type contains text/javascript \
    --check-header etag exists --raw-out "$BUNDLE" --print-header etag)
  cmp "$BUNDLE" "$FX/dist/index.js"
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/bundle --check-header etag eq "$ETAG1" \
    --quiet --save F28.bundle/bundle
  ```
  与体相同 `dist/index.js`, with `Cache-Control: no-cache`, a `text/javascript` 内容类型和一个稳定的 ETag。 该应用程序仍处于禁用状态。
- **图标 (`F28.icon`).**下载声明的SVG； 没有图标的应用程序有 None。
  ```sh
  ICON="$AGENT_SERVER_VERIFY_RUN/fixtures/f28/icon.svg"
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/icon --expect 200 \
    --check-header content-type eq image/svg+xml --check-header content-security-policy contains sandbox \
    --check-header content-security-policy contains "default-src 'none'" \
    --check-header x-content-type-options eq nosniff --check-header cache-control eq no-cache \
    --raw-out "$ICON" --save F28.icon/icon
  cmp "$ICON" "$FX/assets/icon.svg"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/icon --expect 404 \
    --check detail contains 'icon not found' --save F28.icon/no-icon
  ```
  该 SVG 匹配测试夹具并携带
  `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`和`X-Content-Type-Options: nosniff`； `qa-f28-logs` 声明没有图标并得到 404。
- **启用和禁用 (`F28.enable-disable`)。**切换仅限浏览器的应用程序。
  ```sh
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-canvas --json '{"enabled": true}' \
    --expect 200 --check name eq qa-canvas --check enabled eq true --save F28.enable-disable/enable
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check enabled eq true
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json --check extensions.qa-canvas.enabled eq true
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-canvas --json '{"enabled": false}' \
    --expect 200 --check enabled eq false --save F28.enable-disable/disable
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check enabled eq false
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json --check extensions.qa-canvas.enabled eq false
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-canvas --json '{"enabled": "maybe"}' --expect 422
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-canvas --json '{}' --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check enabled eq false
  ```
  每个PATCH回答`{"name": "qa-canvas", "enabled": <value>}`，并且所有第二个视图都跟随它。 糟糕的身体是422，没有任何改变。 应用程序将被禁用。
- **未知且无效的名称 (`F28.unknown-name`)。** `qa-ghost` 从未安装； `Bad_Name` 不是烤肉串。
  ```sh
  control-agent-server api GET /api/canvas-extensions/installed/qa-ghost --expect 404 \
    --check detail eq "Canvas extension 'qa-ghost' is not installed" --save F28.unknown-name/get
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-ghost --json '{"enabled": true}' --expect 404
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-ghost --json '{"enabled": false}' --expect 404
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-ghost --expect 404
  control-agent-server api GET /api/canvas-extensions/installed/qa-ghost/bundle --expect 404 --check detail contains 'bundle not found'
  control-agent-server api GET /api/canvas-extensions/installed/qa-ghost/icon --expect 404
  control-agent-server api GET /api/canvas-extensions/installed/Bad_Name --expect 422
  control-agent-server api PATCH /api/canvas-extensions/installed/Bad_Name --json '{"enabled": true}' --expect 422
  control-agent-server api DELETE /api/canvas-extensions/installed/Bad_Name --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/Bad_Name/bundle --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/Bad_Name/icon --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/Bad_Name/backend --expect 422
  control-agent-server api POST /api/canvas-extensions/installed/Bad_Name/backend/prepare --json '{"revision": "qa-x"}' \
    --expect 422 --check detail.0.loc.1 eq extension_name
  control-agent-server api POST /api/canvas-extensions/installed/Bad_Name/backend/start --json '{"revision": "qa-x"}' \
    --expect 422 --check detail.0.loc.1 eq extension_name
  control-agent-server api POST /api/canvas-extensions/installed/Bad_Name/backend/stop --expect 422 --check detail.0.loc.1 eq extension_name
  control-agent-server api DELETE /api/canvas-extensions/installed/Bad_Name/backend/data --expect 422 --check detail.0.loc.1 eq extension_name
  control-agent-server api GET /api/canvas-extensions/installed/qa--x/backend/logs --expect 422
  control-agent-server api GET /api/canvas-extensions/installed --auth none --expect 401
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/bundle --auth none --expect 401
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/stop --auth none --expect 401
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/bundle --expect 200 --quiet
  ```
  404 `Canvas extension 'qa-ghost' is not installed` (`... bundle not found`,
  `... icon not found`), 422 对于所有十一条路线中的所有不良名称（后端的 blame `extension_name`，而不是身体），并且在带有键的同一套请求中是 200。
- **通过列表发现(`F28.list-discovery`)。**将有效的应用程序复制到
  `installed/` 手动，就像镜像构建一样，然后手动删除它。
  ```sh
  cp -r "$FX" "$INST/qa-f28-hand"
  sed -i 's/"name": "qa-canvas"/"name": "qa-f28-hand"/' "$INST/qa-f28-hand/canvas-extension.json"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-hand --expect 404
  control-agent-server api GET /api/canvas-extensions/installed --expect 200 --check canvas_extensions len-eq 4 \
    --check canvas_extensions.3.name eq qa-f28-hand --check canvas_extensions.3.source eq local \
    --check canvas_extensions.3.enabled eq false --save F28.list-discovery/discovered
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-hand --expect 200 --check source eq local
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json --check extensions.qa-f28-hand.enabled eq false
  rm -rf "$INST/qa-f28-hand"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-hand --expect 404
  control-agent-server api GET /api/canvas-extensions/installed --check canvas_extensions len-eq 3 \
    --check canvas_extensions not-contains qa-f28-hand --save F28.list-discovery/pruned
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json --check extensions.qa-f28-hand missing
  ```
  在调用列表之前，复制会返回 404。 它将它标记为已禁用
  `source: "local"`，然后 GET 找到它。 一旦目录消失，GET 就是 404，下一个列表将其从 `.installed.json` 中删除。
- **安装损坏 (`F28.broken-install`)。**损坏已安装应用程序的清单，恢复它，然后将其入口交换为包外的符号链接。
  ```sh
  KX=$(control-agent-server fixture canvas-app --name qa-broken --print-path)
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$KX\"}" --expect 200 --quiet
  printf '{bad' > "$INST/qa-broken/canvas-extension.json"
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken --expect 200 --check manifest missing \
    --check version eq 0.1.0 --save F28.broken-install/bad-manifest
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/bundle --expect 404
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/icon --expect 404
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/backend --check state eq missing
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-broken --json '{"enabled": true}' --expect 200
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken --check enabled eq true --check manifest missing
  cp "$KX/canvas-extension.json" "$INST/qa-broken/canvas-extension.json"
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/bundle --expect 200 --quiet
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/icon --expect 200 --quiet
  printf '<svg xmlns="http://www.w3.org/2000/svg"/>\n' > "$F28FX/outside.svg"
  rm "$INST/qa-broken/assets/icon.svg" && ln -s "$F28FX/outside.svg" "$INST/qa-broken/assets/icon.svg"
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/icon --expect 404 \
    --check detail contains 'icon not found' --save F28.broken-install/symlink-icon
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken --check manifest.icon eq assets/icon.svg
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/bundle --expect 200 --quiet
  printf 'outside\n' > "$F28FX/outside.js"
  rm "$INST/qa-broken/dist/index.js" && ln -s "$F28FX/outside.js" "$INST/qa-broken/dist/index.js"
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken/bundle --expect 404 --save F28.broken-install/symlink-bundle
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken --check manifest missing
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-broken --expect 200 \
    --check message eq "Canvas extension 'qa-broken' uninstalled"
  control-agent-server api GET /api/canvas-extensions/installed/qa-broken --expect 404
  test ! -e "$INST/qa-broken"
  ```
  即使manifest不可解析，记录仍然被服务（安装记录中的版本） `manifest: null`），bundle和icon是404，后端是 `missing`但是 PATCH works. 恢复的ifest文件再次为包和图标服务。 一个包外指向的图标导致404，而manifest（包括icon字段）和bundle仍然有效。 一个入口在包之外的软链在服务时为404，而manifest读取为 null. DELETE 仍然卸载它。
- **后端状态(`F28.backend-status`)。**读取缺失的、仅浏览器的和后端应用程序的生命周期状态。
  ```sh
  control-agent-server api GET /api/canvas-extensions/installed/qa-ghost/backend --expect 200 --check state eq missing \
    --check revision eq null --check detail contains 'not installed' --save F28.backend-status/missing
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/backend --expect 200 --check state eq unsupported \
    --check revision matches '^sha256:[0-9a-f]{64}$' --check detail contains 'does not declare a backend' \
    --save F28.backend-status/unsupported
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --expect 200 --check state eq stopped \
    --check revision eq "$BHEAD" --check prepared_revision eq null --check pid eq null --check port eq null \
    --save F28.backend-status/stopped
  ```
  `missing`（带有 `revision` null）表示未知名称，`unsupported` 带有
  `sha256:` 版本仅用于本地浏览器安装，`stopped` 带有
  git commit as the revision for the `file://` install, nothing prepared.
- **审批门 (`F28.backend-approval-gate`).**尝试每一个捷径
  `prepare`.
  ```sh
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 409 --check detail eq 'backend revision must be prepared before start' --save F28.backend-approval-gate/unprepared
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json '{"revision": "qa-wrong"}' \
    --expect 409 --check detail contains 'does not match installed revision'
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json '{}' --expect 422
  cp "$INST/qa-backend/backend/linux.tar.gz" "$F28FX/qa-backend.tar.gz.bak"
  printf x >> "$INST/qa-backend/backend/linux.tar.gz"
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json "{\"revision\": \"$BHEAD\"}" \
    --expect 409 --check detail eq 'backend artifact checksum does not match manifest' --save F28.backend-approval-gate/tampered
  cp "$F28FX/qa-backend.tar.gz.bak" "$INST/qa-backend/backend/linux.tar.gz"
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-unsafe\"}" --expect 200 --quiet
  UREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-unsafe/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-unsafe/backend/prepare --json "{\"revision\": \"$UREV\"}" \
    --expect 409 --check detail eq 'backend artifact contains an unsafe archive entry' --save F28.backend-approval-gate/unsafe
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-remote\"}" --expect 200 --quiet
  RREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-remote/backend --check state eq stopped --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-remote/backend/prepare --json "{\"revision\": \"$RREV\"}" \
    --expect 409 --check detail eq 'backend artifact download failed' --save F28.backend-approval-gate/download-failed
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check prepared_revision eq null
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-unsafe/backend --check prepared_revision eq null
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-remote/backend --check prepared_revision eq null
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/approvals/*' --expect-count 0
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/artifacts/**' --expect-count 0
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/downloads/*' --expect-count 0
  test -z "$(find "$P" -name qa-f28-escape)"
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-remote --expect 200 --quiet
  ```
  每个尝试都是409，原因，无体准备422，没有审批文件，没有提取或下载文件，没有写入逃脱成员。 `qa-f28-remote`声明了一个远程（`url`）的资源在封闭的环回（HTTPS）端口上，因此其准备阶段会使用下载路径，但在此处失败。 篡改的归档文件恢复后，远程应用也被卸载了，因此目录计数没有改变。
- **准备 (`F28.backend-prepare`).**批准安装的修订版。
  ```sh
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq stopped --check prepared_revision eq "$BHEAD" --save F28.backend-prepare/prepare
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check prepared_revision eq "$BHEAD"
  control-agent-server state cat home/.openhands/canvas-extensions/backends/approvals/qa-backend.json \
    --check revision eq "$BHEAD" --check artifact_sha256 eq "$BSHA" --check platform matches '^linux-(amd64|arm64)$' \
    --check artifact_dir eq "$BK/artifacts/qa-backend/$BSHA"
  control-agent-server state cat "home/.openhands/canvas-extensions/backends/artifacts/qa-backend/$BSHA/server.py" \
    --mode 555 --contains 'web.run_app' --max-chars 80
  test "$(stat -c %a "$BK/artifacts/qa-backend/$BSHA")" = 555
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check prepared_revision eq "$BHEAD" --expect-max-ms 3000
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/artifacts/**' --expect-count 1
  ```
  `prepared_revision` 等于响应中的修订，GET 和
  `approvals/qa-backend.json`（使用清单的 sha256）； `server.py` 作为 `r-xr-xr-x` 提取到以 sha256 命名的 `dr-xr-xr-x` 目录中，第二个立即准备答案，无需第二次提取。
- **开始 (`F28.backend-start`)。**启动（仍禁用）应用程序的准备修订版并查看其运行的进程。

  需要：`F28.install-local`
  ```sh
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --check pid exists --check port exists --check detail eq null \
    --save F28.backend-start/start
  BPID=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq ready --field pid)
  BPORT=$(control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --field port)
  test "$(curl -fsS "http://127.0.0.1:$BPORT/health")" = ok
  curl -fsS "http://127.0.0.1:$BPORT/qa-echo" | grep -F "\"data_dir\": \"$BK/data/qa-backend\""
  test "$(tr '\0' '\n' < "/proc/$BPID/environ")" = "HOME=$BK/data/qa-backend/home"
  test "$(readlink "/proc/$BPID/cwd")" = "$(cd "$INST/qa-backend" && pwd -P)"
  test "$(ps -o pgid= -p "$BPID" | tr -d ' ')" = "$BPID"
  test "$(pgrep -f "$BK/artifacts/qa-backend/")" = "$BPID"
  test -d "$BK/data/qa-backend/home"
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --check pid eq "$BPID"
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json '{"revision": "qa-other"}' \
    --expect 409 --check detail eq 'a different backend revision is already running'
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$FX\", \"force\": true}" \
    --expect 409 --check detail contains 'Stop running Canvas App backends' --save F28.backend-start/force-blocked
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-backend/backend/data \
    --expect 409 --check detail eq 'stop the backend before deleting its data'
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check installed_at eq "$AT0"
  kill -0 "$BPID"
  ```
  `ready` 带有 pid 和端口； 后端回答 `/health` 并报告其
  `{data_dir}`; 它的环境恰好是`HOME=<data>/qa-backend/home`（没有会话或机密键），它的cwd是已安装的包，并且它引导自己的进程组。 它是命令行保存运行的 `artifacts/qa-backend/` 路径的唯一进程，这是后面的 `pgrep` 检查剩余进程所依赖的。 重复启动返回相同的 pid，另一个修订版本为 409，并且在运行时强制安装任何应用程序和数据删除为 409。 启动不需要启用该应用程序。
- **停止(`F28.backend-stop`)。** Stop the running backend twice.

  需要：`F28.backend-start`
  ```sh
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/stop --expect 200 \
    --check state eq stopped --check pid eq null --check port eq null --expect-max-ms 7000 --save F28.backend-stop/stop
  if kill -0 "$BPID" 2>/dev/null; then false; fi
  if curl -s -m 2 "http://127.0.0.1:$BPORT/health"; then false; fi
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq stopped \
    --check prepared_revision eq "$BHEAD"
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/stop --expect 200 --check state eq stopped
  control-agent-server api POST /api/canvas-extensions/installed/qa-ghost/backend/stop --expect 200 --check state eq missing
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-flaky\"}" --expect 200 --quiet
  KREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/prepare --json "{\"revision\": \"$KREV\"}" --expect 200 --quiet
  KPORT=$(control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/start --json "{\"revision\": \"$KREV\"}" \
    --expect 200 --check state eq ready --field port)
  KCHILD=$(curl -fsS "http://127.0.0.1:$KPORT/fork")
  kill -0 "$KCHILD"
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/stop --expect 200 --check state eq stopped \
    --expect-max-ms 7000 --save F28.backend-stop/group
  if kill -0 "$KCHILD" 2>/dev/null; then false; fi
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-flaky --expect 200 --quiet
  ```
  该过程已不存在，其端口拒绝连接。 审批继续，再次停止（或停止一个未知的应用）是200无操作。 A
  `/bin/sleep` `qa-f28-flaky` 分叉的子进程在其领导者继续运行时与 `stop` 上的组一起死亡； 该应用程序被再次卸载，因此下面的目录计数没有变化。
- ** 重新安装 (`F28.force-reinstall`).** 启用仅浏览器的应用程序，重新安装它，不要 `force`，然后在源处更改其包，然后重新安装两个应用程序，使用 `force`。

  需要：`F28.install-local`、`F28.bundle`
  ```sh
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-canvas --json '{"enabled": true}' --expect 200
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$FX\"}" \
    --expect 409 --check detail eq 'Canvas extension already installed. Use force=true to overwrite.' \
    --save F28.force-reinstall/conflict
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check installed_at eq "$AT0" --check enabled eq true
  printf 'export const qaCanvasApp = "qa-f28-v2";\n' > "$FX/dist/index.js"
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$FX\", \"force\": true}" \
    --expect 200 --check enabled eq true --check installed_at ne "$AT0" --save F28.force-reinstall/force
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check enabled eq true --check installed_at ne "$AT0"
  BUNDLE2="$AGENT_SERVER_VERIFY_RUN/fixtures/f28/bundle-v2.js"
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas/bundle --expect 200 \
    --check-header etag ne "$ETAG1" --raw-out "$BUNDLE2" --quiet
  cmp "$BUNDLE2" "$FX/dist/index.js"
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$BX\", \"force\": true}" \
    --expect 200 --check enabled eq false --check resolved_ref eq "$BHEAD" --save F28.force-reinstall/force-backend
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq stopped \
    --check prepared_revision eq null --save F28.force-reinstall/approval-gone
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/approvals/qa-backend.json' --expect-count 0
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 409 --check detail contains 'must be prepared'
  ```
  缺少`force`，安装失败，记录保持`installed_at`。 强制安装已启用的应用，会以新状态返回
  `installed_at`，并且捆绑包在新的 ETag 下提供新字节。 后端应用程序的强制安装会使其保持禁用状态，删除其批准（`prepared_revision` null，无批准文件），因此拒绝 `start` 直到下一个 `prepare`。
- **启动时记录(`F28.backend-logs`)。** `qa-f28-logs` 打印但从不回答其健康检查（30 s 超时）； 在后台启动它，在 `starting` 时读取其日志，然后停止它。
  ```sh
  LREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-logs/backend/prepare --json "{\"revision\": \"$LREV\"}" \
    --expect 200 --check prepared_revision eq "$LREV" --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-logs/backend/start --json "{\"revision\": \"$LREV\"}" \
    --expect 200 --check state eq stopped --save F28.backend-logs/abandoned-start > /dev/null &
  START_JOB=$!
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend --until-ok 15 \
    --check state eq starting --check pid exists --save F28.backend-logs/starting
  LPID=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend --field pid)
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --until-ok 15 \
    --check logs contains '[stdout] qa-f28-out' --check logs contains '[stderr] qa-f28-err' --check truncated eq false \
    --save F28.backend-logs/logs
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-logs/backend/stop --expect 200 \
    --check state eq stopped --expect-max-ms 7000
  wait "$START_JOB"
  if kill -0 "$LPID" 2>/dev/null; then false; fi
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --expect 200 \
    --check logs contains qa-f28-out --check logs contains qa-f28-err
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --query limit_bytes=8 \
    --expect 200 --check logs len-eq 8 --check truncated eq true --save F28.backend-logs/limited
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --query limit_bytes=0 --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --query limit_bytes=262145 --expect 422
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend/logs --query limit_bytes=262144 --expect 200
  control-agent-server api GET /api/canvas-extensions/installed/qa-ghost/backend/logs --expect 200 \
    --check logs eq '' --check truncated eq false
  ```
  状态显示为 `starting`，进程 ID 为 [pid]，健康检查在运行，日志中显示 `[stdout] qa-f28-out` 和 `[stderr] qa-f28-err`。 `stop` 返回时间不到30秒超时，然后 [pending start] 回应200
  `stopped`，进程消失，日志仍然可读；
  `limit_bytes=8`与`truncated: true`一起返回最后8个字节，0和262145都是422。
- **TypeScript 客户端 (`F28.ts-client`).**构建的每个后端方法
  `CanvasExtensionsClient`，在自己的后端应用程序上，然后 `startBackend` 比客户端 `qa-f28-logs` 上的超时更持久（上面已准备好； 它从未通过 30 秒的健康检查）。
  ```sh
  TX=$(control-agent-server fixture canvas-app --name qa-f28-ts --backend ok --print-path)
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$TX\"}" --expect 200 --quiet
  cat > "$F28FX/ts_canvas.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { CanvasExtensionsClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const options = { host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY };
  const client = new CanvasExtensionsClient(options);
  const httpError = (status, detail) => (err) =>
    err.name === 'HttpError' && err.status === status && (detail === undefined || err.detail === detail);
  const app = 'qa-f28-ts';
  let status = await client.getBackendStatus(app);
  assert.equal(status.state, 'stopped');
  assert.equal(status.prepared_revision, null);
  const revision = status.revision;
  await assert.rejects(client.startBackend(app, revision), httpError(409, 'backend revision must be prepared before start'));
  await assert.rejects(client.prepareBackend(app, 'qa-wrong'),
    httpError(409, 'approval revision does not match installed revision'));
  assert.equal((await client.prepareBackend(app, revision)).prepared_revision, revision);
  status = await client.startBackend(app, revision);
  assert.equal(status.state, 'ready');
  assert.ok(status.pid > 0 && status.port > 0);
  const pid = status.pid;
  assert.equal((await client.getBackendStatus(app)).pid, pid);
  const logs = await client.getBackendLogs(app);
  assert.equal(logs.name, app);
  assert.equal(typeof logs.logs, 'string');
  await assert.rejects(client.deleteBackendData(app), httpError(409, 'stop the backend before deleting its data'));
  status = await client.stopBackend(app);
  assert.equal(status.state, 'stopped');
  assert.equal(status.pid, null);
  assert.equal((await client.deleteBackendData(app)).state, 'stopped');
  await assert.rejects(client.getBackendStatus('Bad_Name'), httpError(422));
  assert.equal((await client.getBackendStatus('qa-ghost')).state, 'missing');

  const slow = 'qa-f28-logs';
  const slowRevision = (await client.getBackendStatus(slow)).revision;
  assert.equal((await client.prepareBackend(slow, slowRevision)).prepared_revision, slowRevision);
  const impatient = new CanvasExtensionsClient({ ...options, timeout: 2000 });
  const started = Date.now();
  await assert.rejects(impatient.startBackend(slow, slowRevision),
    (err) => err.name !== 'HttpError' && err.message === 'Request timeout after 2000ms');
  assert.ok(Date.now() - started < 10000);
  status = await client.getBackendStatus(slow);
  assert.equal(status.state, 'starting');
  assert.ok(status.pid > 0);
  let slowLogs;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    slowLogs = await client.getBackendLogs(slow);
    if (slowLogs.logs.includes('[stderr] qa-f28-err') && slowLogs.logs.includes('[stdout] qa-f28-out')) break;
    await new Promise((done) => setTimeout(done, 200));
  }
  assert.ok(slowLogs.logs.includes('[stdout] qa-f28-out') && slowLogs.logs.includes('[stderr] qa-f28-err'));
  const tail = await client.getBackendLogs(slow, 8);
  assert.equal(tail.logs.length, 8);
  assert.equal(tail.truncated, true);
  assert.equal((await client.getBackendStatus(slow)).state, 'starting');
  assert.equal((await client.stopBackend(slow)).state, 'stopped');
  client.close();
  impatient.close();
  console.log(`QA_F28_TS_OK ready_pid=${pid} starting_pid=${status.pid}`);
  JS
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server exec --timeout 120 --expect-output QA_F28_TS_OK --save F28.ts-client/program -- node "$F28FX/ts_canvas.mjs"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-logs/backend --check state eq stopped --check pid eq null
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-ts/backend --check state eq stopped \
    --check prepared_revision exists --check pid eq null
  if pgrep -f "$BK/artifacts/qa-f28-logs/"; then false; fi
  if pgrep -f "$BK/artifacts/qa-f28-ts/"; then false; fi
  test ! -e "$BK/data/qa-f28-ts"
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-ts --expect 200 --quiet
  ```
  程序打印 `QA_F28_TS_OK`: `getBackendStatus`, `prepareBackend`
  `startBackend`、`getBackendLogs`、`stopBackend`和`deleteBackendData`返回REST子弹断言的`stopped`、`ready`和`stopped`状态，以及拒绝请求时携带服务器状态和详情的`HttpError`（409未准备启动、错误修订和运行中数据删除；422为坏名称）。 使用 `timeout: 2000` 构建的客户端拒绝
  `startBackend` 2 秒后 `Request timeout after 2000ms`（简单的
  `Error`，不是 `HttpError`），而服务器保留后端
  `starting` 其日志可读直到 `stopBackend`：对于 `health.timeout_seconds` 更长（最多 300）的清单，默认 60 秒超时也会发生同样的情况。 服务器端读取确认两个后端均已消失且数据目录已删除； 该应用程序已卸载，因此下面的目录计数不变。
- **启动失败 (`F28.backend-start-fails`)。** `qa-unhealthy` 用 503 (15 s 超时) 回答其健康检查； `qa-exit` 以代码 3 退出。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$UX\"}" --expect 200 --quiet
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$EX\"}" --expect 200 --quiet
  HREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-unhealthy/backend --field revision)
  XREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-exit/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-unhealthy/backend/prepare --json "{\"revision\": \"$HREV\"}" --expect 200 --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-exit/backend/prepare --json "{\"revision\": \"$XREV\"}" --expect 200 --quiet
  T0=$SECONDS
  control-agent-server api POST /api/canvas-extensions/installed/qa-unhealthy/backend/start --json "{\"revision\": \"$HREV\"}" \
    --expect 200 --check state eq unhealthy --check detail eq 'backend health check timed out' --check pid eq null \
    --expect-max-ms 25000 --save F28.backend-start-fails/timeout
  test $((SECONDS - T0)) -ge 14
  control-agent-server api GET /api/canvas-extensions/installed/qa-unhealthy/backend --check state eq unhealthy --check pid eq null
  if pgrep -f "$BK/artifacts/qa-unhealthy/"; then false; fi
  control-agent-server api POST /api/canvas-extensions/installed/qa-exit/backend/start --json "{\"revision\": \"$XREV\"}" \
    --expect 200 --check state eq unhealthy --check detail eq 'backend exited with code 3' --check pid eq null \
    --save F28.backend-start-fails/exit
  control-agent-server api GET /api/canvas-extensions/installed/qa-exit/backend --check state eq unhealthy \
    --check detail eq 'backend exited with code 3'
  if pgrep -f "$BK/artifacts/qa-exit/"; then false; fi
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-unhealthy/backend/data --expect 200 --check state eq unhealthy
  test ! -e "$BK/data/qa-unhealthy"
  ```
  不健康的后端启动大约持续了15秒的健康检查超时，然后结束 `unhealthy` / `backend health check timed out`。 退出的那个结束了
  `unhealthy` / `backend exited with code 3`. 任何一个进程都不会保留，并且故障后端的数据可以被删除。
- **继承环境(`F28.backend-inherit-environment`)。**安装`inherit_environment`清单模式拒绝的两个应用程序，然后启动`qa-f28-env`，它要求`PATH`、`TZ`和`LANG`，并将其环境与服务器进程自己的环境进行比较。
  ```sh
  for BADENV in secret dup; do
    control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-env-$BADENV\"}" \
      --expect 422 --check detail contains 'Invalid canvas extension' --save "F28.backend-inherit-environment/refused-$BADENV"
    control-agent-server api GET "/api/canvas-extensions/installed/qa-f28-env-$BADENV" --expect 404
    test ! -e "$INST/qa-f28-env-$BADENV"
  done
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-env\"}" --expect 200 \
    --check manifest.backend.inherit_environment len-eq 3 --save F28.backend-inherit-environment/install
  VREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-env/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-env/backend/prepare --json "{\"revision\": \"$VREV\"}" --expect 200 --quiet
  VPID=$(control-agent-server api POST /api/canvas-extensions/installed/qa-f28-env/backend/start --json "{\"revision\": \"$VREV\"}" \
    --expect 200 --check state eq ready --field pid)
  SPID=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["pid"])' "$AGENT_SERVER_VERIFY_RUN/run.json")
  test "$(tr '\0' '\n' < "/proc/$SPID/cmdline" | grep -cx openhands.agent_server)" = 1
  test "$(tr '\0' '\n' < "/proc/$SPID/environ" | grep -c '^OH_SECRET_KEY=')" = 1
  test "$(tr '\0' '\n' < "/proc/$SPID/environ" | grep -c '^PATH=')" = 1
  EXPECTED_ENV=$( (echo "HOME=$BK/data/qa-f28-env/home"; tr '\0' '\n' < "/proc/$SPID/environ" | grep -E '^(PATH|TZ|LANG)=') | sort)
  tr '\0' '\n' < "/proc/$VPID/environ" | cut -d= -f1 | sort | paste -sd ' ' -
  test "$(tr '\0' '\n' < "/proc/$VPID/environ" | sort)" = "$EXPECTED_ENV"
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-env/backend/stop --expect 200 --check state eq stopped --quiet
  sed -i 's/"LANG"/"OH_SECRET_KEY"/' "$INST/qa-f28-env/canvas-extension.json"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-env --check manifest missing
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-env/backend/start --json "{\"revision\": \"$VREV\"}" \
    --expect 200 --check state eq missing --check pid eq null --save F28.backend-inherit-environment/edited-on-disk
  if pgrep -f "$BK/artifacts/qa-f28-env/"; then false; fi
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-env --expect 200 --quiet
  ```
  两种坏的ifests都是422 `Invalid canvas extension ...`，没有任何影响
  安装：`OH_SECRET_KEY` 位于允许列表之外（`LANG`、`LC_ALL`、
  `LC_CTYPE`、`PATH`、`TMPDIR`、`TZ`）甚至在允许的名称旁边，并且列出两次的名称也会被拒绝。 启动的后端环境恰好是`HOME=<data>/qa-f28-env/home`加上服务器自己的所请求名称的值（`PATH`总是，`TZ=UTC`来自家族的
  `Launch:`行，`LANG`仅当服务器有时），而服务器进程持有`OH_SECRET_KEY`（检查不打印）； 打印行仅列出后端的变量名称。 该应用程序已停止并卸载，因此下面的目录计数不变。 在此之前，在磁盘上编辑其安装的清单以请求 `OH_SECRET_KEY`：它停止验证 (`manifest: null`)，因此 `start` 回答 `missing` 并且不运行任何内容； `_environment` 中的开始时间检查永远不会通过 API 到达。
- **Disable 停止后端 (`F28.disable-stops-backend`)。**再次准备（强制安装撤销批准），启用，启动，然后禁用。
  ```sh
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/prepare --json "{\"revision\": \"$BHEAD\"}" --expect 200 --quiet
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": true}' --expect 200
  DPID=$(control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --field pid)
  kill -0 "$DPID"
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": false}' \
    --expect 200 --check enabled eq false --expect-max-ms 7000 --save F28.disable-stops-backend/disable
  if kill -0 "$DPID" 2>/dev/null; then false; fi
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq stopped --check pid eq null \
    --save F28.disable-stops-backend/status
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend --check enabled eq false
  ```
  只有在后端组消失后，禁用答案才返回 200。 状态为`stopped`。
- **持久化重新启动 (`F28.restart-persistence`)。**启用并启动后端应用程序，然后正常重新启动服务器。
  ```sh
  control-agent-server api PATCH /api/canvas-extensions/installed/qa-backend --json '{"enabled": true}' --expect 200
  RPID=$(control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --field pid)
  control-agent-server restart
  if kill -0 "$RPID" 2>/dev/null; then false; fi
  control-agent-server api GET /api/canvas-extensions/installed --check canvas_extensions len-eq 6 --quiet
  control-agent-server api GET /api/canvas-extensions/installed/qa-canvas --check enabled eq true --save F28.restart-persistence/canvas
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend --check enabled eq true --check resolved_ref eq "$BHEAD"
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq stopped \
    --check prepared_revision eq "$BHEAD" --check pid eq null --save F28.restart-persistence/backend
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --check pid ne "$RPID" --save F28.restart-persistence/start-again
  control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/stop --expect 200 --check state eq stopped
  ```
  优雅的关闭停止了后端。 6个安装，都是
  `enabled: true` 值和批准返回，后端读取
  `stopped` 和 `start` 成功使用新的 pid，无需另一个 `prepare`。
- **卸载(`F28.uninstall`)。**启动后端，卸载应用程序，然后删除其数据。
  ```sh
  QPID=$(control-agent-server api POST /api/canvas-extensions/installed/qa-backend/backend/start --json "{\"revision\": \"$BHEAD\"}" \
    --expect 200 --check state eq ready --field pid)
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-backend --expect 200 \
    --check message eq "Canvas extension 'qa-backend' uninstalled" --save F28.uninstall/delete
  if kill -0 "$QPID" 2>/dev/null; then false; fi
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend --expect 404
  control-agent-server api GET /api/canvas-extensions/installed --check canvas_extensions len-eq 5 \
    --check canvas_extensions not-contains qa-backend --quiet
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json --check extensions.qa-backend missing --max-chars 100
  test ! -e "$INST/qa-backend"
  control-agent-server api GET /api/canvas-extensions/installed/qa-backend/backend --check state eq missing \
    --check prepared_revision eq "$BHEAD" --save F28.uninstall/backend-missing
  test -d "$BK/data/qa-backend/home"
  test -d "$BK/artifacts/qa-backend/$BSHA"
  control-agent-server state cat home/.openhands/canvas-extensions/backends/approvals/qa-backend.json --check revision eq "$BHEAD"
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-backend --expect 404
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-backend/backend/data --expect 200 \
    --check state eq missing --save F28.uninstall/delete-data
  test ! -e "$BK/data/qa-backend"
  ```
  卸载会停止运行的后端并移除包及其记录。 后端读取`missing`，数据目录、提取的成果和批准仍然存在，第二个DELETE是404，然后数据路由则删除`backends/data/qa-backend`。
- **非gzip的文件 (`F28.prepare-corrupt-archive`).** 包含与manifest的sha256哈希值匹配的字节，但不是gzip压缩文件的文件将被拒绝，就像所有其他坏文件一样（409），并且没有任何内容写入。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-notgz\"}" --expect 200 --quiet
  NREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-notgz/backend --field revision)
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-notgz/backend --check state eq stopped
  test "$(sha256sum "$INST/qa-f28-notgz/backend/linux.tar.gz" | cut -d' ' -f1)" = \
    "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["backend"]["artifacts"]["linux-amd64"]["sha256"])' "$INST/qa-f28-notgz/canvas-extension.json")"
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-notgz/backend/prepare --json "{\"revision\": \"$NREV\"}" \
    --expect 409 --check detail contains 'not a valid gzip tar archive' --save F28.prepare-corrupt-archive/prepare
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/approvals/qa-f28-notgz.json' --expect-count 0
  control-agent-server state ls 'home/.openhands/canvas-extensions/backends/artifacts/qa-f28-notgz/**' --expect-count 0
  ```
  安装的 artifact 的 sha256 与 manifest 匹配，因此校验码门通过，只有归档格式有误：prepare 409
  `backend artifact is not a valid gzip tar archive`，并且不会留下任何批准或提取的工件。
- **缓存源上的未知引用 (`F28.install-ref-cached`)。** Pin `qa-f28-git`（缓存其克隆），然后强制使用不存在的引用。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$GX\", \"ref\": \"$GV1\", \"force\": true}" \
    --expect 200 --check resolved_ref eq "$GV1" --quiet
  control-agent-server state ls 'home/.openhands/cache/extensions/qa-f28-git-*/canvas-extension.json' --expect-count 1
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"file://$GX\", \"ref\": \"qa-no-such-ref\", \"force\": true}" \
    --expect 400 --check detail contains 'Could not read canvas extension source' --save F28.install-ref-cached/unknown-ref
  control-agent-server state cat home/.openhands/canvas-extensions/installed/.installed.json \
    --check extensions.qa-f28-git.requested_ref eq "$GV1" --check extensions.qa-f28-git.resolved_ref eq "$GV1"
  control-agent-server api DELETE /api/canvas-extensions/installed/qa-f28-git --expect 200 --quiet
  ```
  锁定安装留下了源的唯一一个缓存克隆。 未知引用返回了400，类似于第一次请求 (`F28.install-ref`)。 请求和已解决的引用仍然停留在之前的 pinned 命名提交。
- **运行状况探针锁存器 (`F28.status-probe-latch`)。**使正在运行的后端应答一个状态探测的速度比 1 秒探测超时慢，然后再次加快。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-flaky\"}" --expect 200,409 --quiet
  FREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/prepare --json "{\"revision\": \"$FREV\"}" --expect 200 --quiet
  FPORT=$(control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/start --json "{\"revision\": \"$FREV\"}" \
    --expect 200 --check state eq ready --field port)
  curl -fsS "http://127.0.0.1:$FPORT/slow"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --expect 200 --check pid exists \
    --save F28.status-probe-latch/slow-probe
  curl -fsS "http://127.0.0.1:$FPORT/fast"
  test "$(curl -fsS -m 3 "http://127.0.0.1:$FPORT/health")" = ok
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --until-ok 5 --check state eq ready \
    --save F28.status-probe-latch/after-recovery
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/stop --expect 200 --check state eq stopped --quiet
  ```
  预期：一旦`/health`再次及时回答（直接`curl`显示它
  ），状态返回到 `ready`（无论是否报告了慢速探测）。 慢速探测状态未断言，因此容忍一个慢速探测的服务器也会通过。 今天，慢速探针读取`unhealthy`（“后端运行状况探针失败”，保存为`slow-probe`），具有相同的pid； 以后的每个状态调用都会再次探测该实时进程，因此状态会读取
  `ready` 一旦 `/health` 及时答复，并且具有相同修订版本的 `start` 会重新探测相同的 pid，而不是重新启动它。 进程退出的后端将保持 `unhealthy` 直到 `stop` 或 `start`。
- **leader退出后的状态（`F28.status-exit-hang`）。**后端分叉一个继承其标准输出的子级，然后其领导者退出。
  ```sh
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$F28FX/qa-f28-flaky\"}" --expect 200,409 --quiet
  FREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/prepare --json "{\"revision\": \"$FREV\"}" --expect 200 --quiet
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/stop --expect 200 --quiet
  FPORT=$(control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/start --json "{\"revision\": \"$FREV\"}" \
    --expect 200 --check state eq ready --field port)
  FPID=$(control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --check state eq ready --field pid)
  CHILD=$(curl -fsS "http://127.0.0.1:$FPORT/fork")
  trap 'kill "$CHILD" 2>/dev/null || true' EXIT
  kill -0 "$CHILD"
  curl -s -m 3 "http://127.0.0.1:$FPORT/exit" || true
  for _ in $(seq 50); do kill -0 "$FPID" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "$FPID" 2>/dev/null; then false; fi
  kill -0 "$CHILD"
  control-agent-server api GET /api/canvas-extensions/installed/qa-f28-flaky/backend --until-ok 10 --timeout 10 \
    --check state eq unhealthy --check detail eq 'Backend exited with code 0' --save F28.status-exit-hang/status
  control-agent-server api POST /api/canvas-extensions/installed/qa-f28-flaky/backend/stop --timeout 10 --expect 200 --check state eq stopped
  if kill -0 "$CHILD" 2>/dev/null; then false; fi
  ```
  `/bin/sleep` 子进程仍然在运行，而领导已经离开（服务器杀死了它）。 状态报告立即报告退出(`unhealthy`, `Backend exited with code 0`)，`stop` 会杀死剩余的子进程。
  `--until-ok` 覆盖了状态查询，该查询在服务器注意到退出之前就完成了（它会读取到） `Backend health probe failed` once); 一个 `api` 超时则结束重试。 在 #5689 之前，状态调用会等待子进程关闭管道（最多 300 秒），而它持有应用的锁，so `stop`, `logs`, `prepare`, `start` 并且该应用的数据路由超时了，而孩子仍在运行（基准） `3dcb27b2` 它被重复测试了两次，#5689 成功了两次。 子弹的子弹头如果被出口陷阱杀死回归留下它。
- **后端不会崩溃 (`F28.hard-restart-orphan`)。**启动后端，SIGKILL 服务器并在相同状态下重新启动它。
  ```sh
  OX=$(control-agent-server fixture canvas-app --name qa-orphan --backend ok --print-path)
  control-agent-server api POST /api/canvas-extensions/install --json "{\"source\": \"$OX\"}" --expect 200 --quiet
  OREV=$(control-agent-server api GET /api/canvas-extensions/installed/qa-orphan/backend --field revision)
  control-agent-server api POST /api/canvas-extensions/installed/qa-orphan/backend/prepare --json "{\"revision\": \"$OREV\"}" --expect 200 --quiet
  OPID=$(control-agent-server api POST /api/canvas-extensions/installed/qa-orphan/backend/start --json "{\"revision\": \"$OREV\"}" \
    --expect 200 --check state eq ready --field pid)
  test "$(pgrep -f "$BK/artifacts/qa-orphan/")" = "$OPID"
  control-agent-server restart --hard
  control-agent-server api GET /api/canvas-extensions/installed/qa-orphan/backend --check state eq stopped \
    --check pid eq null --save F28.hard-restart-orphan/status-after-crash
  control-agent-server assert --value "$(pgrep -f "$BK/artifacts/qa-orphan/" || true)" --check . eq ''
  ```
  预期：一旦服务器恢复，死服务器的后端进程就不再保留
  回来。 `backends/run/` 中记录了服务器启动的每个后端（进程组、领导者启动时间及其自己的进程 ID 和启动时间），以及在启动之前，停止了所有服务器已消失但领导者仍然匹配（相同启动时间、命令行）的记录组
  `artifacts/<name>/`)，然后删除该记录。 重启后的服务器报告`stopped`，没有进程了，一个新的`start`启动了数据目录中的唯一进程，而`DELETE .../backend/data`则没有活的后端。 剩余的检查匹配运行专用工件路径而不是 pid，因此回收的 pid 无法伪造幸存者； 崩溃之前的 `pgrep` 显示该模式找到了实时后端。

<a id="gotchas"></a>

## 陷阱

- `file://` 是 git URL，不是本地路径：`file:///plain/dir` 不是存储库，是 400。 使用裸绝对路径进行本地安装。 相对源和 `~` 源根据服务器的 cwd 和私有 `HOME`（而不是调用者的）进行解析。
- 全新安装始终被禁用，并且主体没有 `enabled` 字段（额外的字段将被忽略）。 `force` 保留了之前的`enabled`值，删除了后端审批，并且在任何应用的后端启动或运行时被拒绝，而不是这个应用。
- `GET /installed` 写入：它注册有效的手动复制目录（禁用，`source: "local"`）并修剪目录已消失的记录。 GET按名称、捆绑包、图标和后端路由不发现； 他们 404（或报告 `missing`）直到列表调用运行。
- `ref` 遍历 SDK 的缓存 git 克隆 (`cache/extensions/<name>-<hash>`)。 未知的引用返回 400，并在第一次获取和缓存的源上保持已安装的应用程序不变 (`F28.install-ref-cached`)。 每次 git fetch 失败都会读取
  `Could not read canvas extension source: Failed to fetch extension from <url>` 没有命名引用，尽管路由器故意避免“无法获取”措辞（Canvas 客户端将其视为网络中断）。
- 每次读取都会重新验证已安装的清单和入口的遏制； `manifest: null` 是磁盘上的安装已损坏的信号。 非 `.svg` 图标会在解析时默默删除，并且应用程序保持有效。
- 后端路由从不返回 404：未知或损坏的应用报告 `missing`，仅浏览器的应用报告 `unsupported`，以及准备/启动/停止/日志/数据的应用返回 200 并报告该状态。 只有非 kebab 大小写的名称是 422。
- 修订版是 git 安装的 git 提交
  `sha256:<hash of the manifest JSON>` 对于本地安装，因此编辑本地安装的已安装清单会更改修订版（并且需要新的准备），
  while a git install's revision does not change.
- `prepare`和`start`不参考`enabled`：可以准备并启动禁用的应用程序（README使`prepare`具有精确的修订版显式门； 禁用和卸载会停止后端）。 `prepare`也不检查后端是否正在运行。
- `start` 会阻塞，直到健康检查通过或 `health.timeout_seconds`（最多 300）用完，因此为 `api` 提供足够长的 `--timeout`（默认 60 秒）以降低测试夹具的速度。 `stop` 放弃一个待定的开始，然后回答
  `stopped`.
- 后端不会得到 `PATH` 除非他们询问：环境只是
  `HOME=<data>/<name>/home` 加上服务器的名称值
  `inherit_environment` 从其允许列表中列出 (`LANG`, `LC_ALL`,
  `LC_CTYPE`, `PATH`, `TMPDIR`, `TZ`; 其他的都是安装时的 422，
  `F28.backend-inherit-environment`)，因此脚本需要绝对的 shebang 和二进制文件。 Python 到管道的标准输出是块缓冲的：刷新，或者 `logs` 保持为空。 CLI 的 aiohttp 测试夹具不打印任何内容，这就是日志项目符号使用自己的 shell 后端的原因。
- 日志在停止或启动失败后保留，并由下一次清除
  `start`; 每个读取块（不是每行）都以 `[stdout] ` 或
  `[stderr] `.
- 提取的工件是只读 (`0555`) 并且永远不会被垃圾收集，即使在卸载时也不会； `DELETE .../backend/data`仅删除`backends/data/<name>`。 运行状态的非根 `rm -rf` 需要 `chmod -R u+w`
  `canvas-extensions/backends/artifacts` 第一。
- 后端在自己的会话中运行，因此它们会一个  SIGKILLed 直到服务器重启到相同状态为止`F28.hard-restart-orphan`).
  `control-agent-server stop` 收获 `HOME` 在运行中的剩余物。
- `ready` 后端的每个 `GET .../backend` 用 1 s 超时探测其健康路径。 一个缓慢的答案读取 `unhealthy`，直到稍后的探测及时回答 (`F28.status-probe-latch`)，因此测试夹具后端必须回答
  `/health` 来自线程服务器，永远不会落后于缓慢的请求。 在 #5689 之前，一个后端的孩子在领导者死亡后保持其标准输出打开，楔入了该应用程序的生命周期路线； 服务器现在收获它们（`F28.status-exit-hang`）。
- 在途的 `start` 另一个命令必须以后台模式运行 `api` call (`... &`, then `START_JOB=$!`) 并且被收集起来 `wait "$START_JOB"`所以它的自己 `--expect`/`--check` 仍然未能击中目标`F28.backend-logs`).
- 直接探测后端（`curl 127.0.0.1:<port>`、`/proc/<pid>`）需要一台 Linux 主机，其中 CLI 和服务器共享网络和 pid 命名空间； 无法通过这种方式检查连接的远程服务器。 到后端（`/app-backends/...`）的浏览器路由属于桥系列。
