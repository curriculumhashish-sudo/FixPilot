<a id="workspace-file-serving-and-vs-code-endpoints"></a>

# 工作区文件服务和 VS Code 端点

浏览器或智能体消费者如何看待智能体生成的内容。 每个对话的工作区目录都是一个普通的静态站点，位于
`/api/conversations/{conversation_id}/workspace/`：一个文件以 `Content-Type` 的形式返回，`ETag` 和 `Last-Modified` 以及字节范围。一个目录提供其 `index.html` 或 404。任何超出工作区的东西（编码 `..`、绝对路径、软链接）返回 400。 这两条路由位于它们自己的身份验证组中：它们接受
`X-Session-API-Key` 头部或`oh_workspace_session_key` cookie，因此Agent Canvas 可以嵌入智能体-制作的HTML，图片和PDFs在`<iframe>`和`<img>`。 VS Code 路由报告捆绑的 OpenVSCode 服务器是否启用并运行，并构建其 URL（`tkn` 是第一个会话密钥，`folder` 是工作区）。 该会话范围的变体默认将文件夹设置为会话的工作区，并拒绝外部文件夹。 它们仅包含标题。

资料来源：`openhands-agent-server/openhands/agent_server/workspace_router.py`、`openhands-agent-server/openhands/agent_server/vscode_router.py`、`openhands-agent-server/openhands/agent_server/vscode_service.py`、`openhands-agent-server/openhands/agent_server/runtime_router.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-agent-server/openhands/agent_server/docker_runtime/routers.py`、`clients/typescript/src/client/vscode-client.ts`、`clients/typescript/src/workspace/remote-workspace.ts`

需求：`llm`、`git`

路线：`GET /api/conversations/{conversation_id}/workspace`，
`GET /api/conversations/{conversation_id}/workspace/{file_path:path}`,
`GET /api/conversations/{runtime_conversation_id}/vscode/url`,
`GET /api/conversations/{runtime_conversation_id}/vscode/status`,
`GET /api/vscode/url`, `GET /api/vscode/status`

<a id="sub-features"></a>

## 子功能

- `F16.root-index`：`GET .../workspace` 和 `.../workspace/` 将工作区根的 `index.html` 作为 `text/html; charset=utf-8`，内联（无 `Content-Disposition`）。
- `F16.file-bytes`：嵌套文件逐字节返回`Content-Length`、`ETag`、`Last-Modified`和`Accept-Ranges: bytes`； 百分号编码的名称（空格和非ASCII字符）解析。
- `F16.content-types`：`Content-Type`跟在扩展名(`.css`、`.json`、`.svg`、`.png`、`.txt`)之后，未知扩展名是`application/octet-stream`。
- `F16.dir-index`：子目录提供其自己的`index.html`，带或不带尾部斜杠； 没有文件的目录是 404 `No index.html in directory`（工作区根也是如此），缺少文件是 404 `File not found`。
- `F16.range`：`Range: bytes=0-5` 请求用 `Content-Range` 回答 206，并且仅回答这些字节。
- `F16.live-content`：磁盘上更改的文件立即重新提供，并带有新的`ETag`（无服务器端缓存）。
- `F16.traversal-rejected`：编码的`..`段和绝对路径（`//etc/hostname`，`%2Fetc%2Fhostname`）答案400 `Path is outside the workspace`； 留在里面的`..`被送达。
- `F16.symlink-escape`：在工作区之外解析的符号链接文件或目录为400； 提供指向其中文件的符号链接。
- `F16.unknown-conversation`：两个路由上的未知会话 ID 均为 404 `Conversation not found: <id>`，非 UUID ID 为 422，真实 ID 的无破折号十六进制形式有效。
- `F16.workspace-dir-missing`： 工作区目录被删除的对话应答 404 `Workspace directory does not exist`，并在目录恢复后再次提供服务。
- `F16.deleted-conversation`：在`DELETE /api/conversations/{id}`之后，不再提供工作区（404 `Conversation not found`），尽管文件保留在磁盘上。
- `F16.worktree-served`：一个`worktree: true`对话是通过其自己的git工作树：在那里的文件和已提交的内容，而不是源检出的未提交的编辑或未跟踪的文件。
- `F16.auth`：没有密钥或密钥错误，两条路由均为 401（也适用于未知对话）； 标头有效，单独的工作区 cookie 也有效，但值错误的 cookie 则无效。
- `F16.agent-artifact`：智能体使用文件编辑器写入的 HTML 文件在对话的工作区 URL 中提供，事件套接字显示创建它的观测结果。
- `F16.restart`：服务器重新启动后，将再次提供同一会话的工作区，其中包含标头和重新启动前创建的 cookie。
- `F16.vscode-disabled`：VS Code 关闭（启动器的默认设置）时，两个状态路由均应答 `{"running": false, "enabled": false, "message": "VSCode is disabled in configuration"}`，并且两个 URL 路由均应答 503。
- `F16.vscode-scoped-guards`：VS Code端点在没有对话时返回404，在非UUID ID时返回422，在相对或外部文件夹时返回422 `workspace_dir must be inside the conversation workspace`，在没有对话之前会先查看VS Code。
- `F16.vscode-auth`：所有四个 VS Code 路由都需要标头（否则为 401），并且工作区 cookie 的路径覆盖了作用域路由，因此不会打开它们。
- `F16.vscode-enabled-status`：`enable_vscode` 打开并且 VS Code 无法启动（其端口被占用，或没有二进制文件），两个状态路由均应答 `{"running": false, "enabled": true}` 并且服务器继续提供服务。
- `F16.vscode-url-shape`：VS Code运行时，URL为`http://localhost:<vscode_port>/?tkn=<first session key>&folder=workspace`； `base_url` 替换源，`workspace_dir` 设置文件夹，作用域路由将文件夹默认为对话的 `workspace.working_dir`，`vscode_base_path` 插入在源之后。
- `F16.vscode-url-not-running`：不得公布未运行的 VS Code：`url` 为 null，而 `running` 为 False，同样在使用会话密钥启动的服务器上。
- `F16.vscode-url-no-key`：没有会话密钥的服务器，启用了 VS Code 但未运行（无二进制文件），在两条 URL 路由上回答 `{"url": null}`。
- `F16.vscode-url-after-init`：延迟初始化服务器通过 `POST /api/init` 接收其会话密​​钥，启用 VS Code 但未运行（无二进制文件），答案 `{"url": null}`。
- `F16.vscode-folder-encoding`：URL 的 `folder` 参数解码回工作区路径，即使该路径包含 `&` 或 `#`。
- `F16.docker-root-cookie`: in Docker 无斜杠运行模式工作区根节点接受工作区像斜杠形式的cookie一样（已知bug：它落入了只包含头部的代理并返回401）。
- `F16.vscode-running`：安装了 OpenVSCode 服务器二进制文件并且其端口空闲，状态报告 `running: true` 和 URL 打开编辑器。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `GET /api/conversations/{conversation_id}/workspace`（根的
  `index.html`) 和 `GET /api/conversations/{conversation_id}/workspace/{file_path}`（任何文件，或目录的 `index.html`）。 授权：`X-Session-API-Key`，或
  `oh_workspace_session_key` 由 `POST /api/auth/workspace-session` 创建的 cookie（该路由和 cookie 的属性属于 auth 系列，F02； 这里的cookie只是凭据）。 `api --jar` 播放浏览器。
- REST：`GET /api/vscode/status`和`GET /api/vscode/url?base_url=&workspace_dir=`（全局； `workspace_dir` 默认为相对的 `workspace` 并且未选中），并且会话范围
  `GET /api/conversations/{runtime_conversation_id}/vscode/status` 和
  `.../vscode/url`（文件夹默认为对话的
  `workspace.working_dir`; 显式 `workspace_dir` 必须是绝对的并且位于其内部）。 仅标题。
- TypeScript 客户端：`RemoteWorkspace.startWorkspaceSession(conversationId)` 为 iframe 创建 cookie 并返回 `${host}/api/conversations/{id}/workspace/`（始终带有尾部斜杠）；
  `deleteWorkspaceSession()` 清除它。 `VSCodeClient.getUrl({baseUrl, workspaceDir})` 和 `getStatus()`（也是 `OpenHandsClient.vscode`）调用全局路由，或者在使用 `conversationId` 构造并且服务器通告 `conversation_runtime_routes_v1` 时调用会话范围的路由。
- SDK (Python)：这些路由没有包装器； `RemoteWorkspace` 通过文件路由读取文件 (F14)。
- 配置：`enable_vscode`（`OH_ENABLE_VSCODE`，服务器中默认True，`launch`中关闭，除非`--vscode`），`vscode_port`（`OH_VSCODE_PORT`，默认8001； `launch` 选择一个免费的），
  `vscode_base_path` (`OH_VSCODE_BASE_PATH`), 会话密钥（第一个是 VS Code token。 在延迟初始化服务器上，它们到达时带有
  `POST /api/init`, F03). `OH_CONVERSATION_RUNTIME=docker` 将代理的工作区文件路由交换到对话的容器中。 以 `worktree: true` (F04) 开始的对话由其工作树提供服务。
- Agent Canvas 在创建 cookie 后将工作区个文件嵌入到 iframe 中，并从 URL 路由（仅上下文）打开 VS Code。
- 食谱使用 `api` 驱动每条路线，使用 `api --jar` 作为 cookie，
  `restart --config-json` 要启用 VS Code，[an] `http-sink`  测试夹具为了持有 VS Code 端口，需要一个模型对话和  `ws start`/`ws 停止` for the agent's artifact, a `git-repo` fixture for the worktree, and second runs (`--no-auth --vscode`, `--no-auth --deferred-init --vscode Docker 其他模式的运行时。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行是实时的并已导出（`launch --new`，没有额外的标志），`doctor` 可以，
  设置为`$DEEPSEEK_API_KEY`，`PATH` 上为`git`、`jq` 和`python3`。
- 下面的块激活 `deepseek-flash`（仅 `F16.agent-artifact` 运行模型）并构建运行拥有的工作区 `$F/ws`：一个 `index.html`、一个具有自己的 `index.html` 的子目录、一个没有子目录的目录、多种类型的文件、一个带有空格和非 ASCII 字母的名称，以及指向工作区内部文件、外部文件和外部目录的符号链接。 `CID` 是 `$F/ws` 上的一个永远不会运行的对话（没有工具，所以没有 `tmux`），`WS` 它
  `workspace.working_dir` 正如服务器报告的那样，`BARE` 是工作区上的第二个，没有 `index.html`。
  ```sh
  control-agent-server llm preset deepseek
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f16"
  mkdir -p "$F/ws/sub/docs" "$F/ws/empty-dir" "$F/bare" "$F/outside-dir"
  printf '<h1>qa-f16-root</h1>\n' > "$F/ws/index.html"
  printf '<p>qa-f16-sub</p>\n' > "$F/ws/sub/index.html"
  printf 'qa-f16 notes v1\n' > "$F/ws/sub/docs/notes.txt"
  printf '{"qa": "f16"}\n' > "$F/ws/data.json"
  printf '<svg xmlns="http://www.w3.org/2000/svg"/>\n' > "$F/ws/pic.svg"
  printf 'body{color:red}\n' > "$F/ws/style.css"
  head -c 4096 /dev/urandom > "$F/ws/img.png"
  printf 'qa-f16-blob' > "$F/ws/blob.qaunknown"
  printf 'qa-f16 spaced\n' > "$F/ws/my file é.txt"
  printf 'qa-f16-outside\n' > "$F/outside.txt"
  printf 'qa-f16-outside-dir\n' > "$F/outside-dir/file.txt"
  ln -sfn data.json "$F/ws/inside-link.json"
  ln -sfn ../outside.txt "$F/ws/escape-link.txt"
  ln -sfn ../outside-dir "$F/ws/dir-link"
  printf 'qa-f16-bare\n' > "$F/bare/readme.txt"
  CID=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$F/ws" --print-id)
  WS=$(control-agent-server api GET "/api/conversations/$CID" --field workspace.working_dir)
  BARE=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$F/bare" --print-id)
  test -n "$WS"
  ```

- **根索引 (`F16.root-index`).**打开带或不带尾部斜杠的工作区根目录。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace" --expect 200 --check . contains qa-f16-root \
    --check-header content-type eq 'text/html; charset=utf-8' --check-header content-disposition missing --save F16.root-index/root
  control-agent-server api GET "/api/conversations/$CID/workspace/" --expect 200 --check . contains qa-f16-root
  ```
  两者都返回 `<h1>qa-f16-root</h1>` 而不是 `text/html; charset=utf-8`
  `Content-Disposition`，因此浏览器将其呈现在 iframe 中。
- **文件字节和标头 (`F16.file-bytes`)。**下载二进制文件并将其与磁盘上的文件进行比较，然后得出百分比编码的名称。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace/img.png" --expect 200 --raw-out "$F/img.out" \
    --check-header content-length eq 4096 --check-header etag exists --check-header last-modified exists \
    --check-header accept-ranges eq bytes --save F16.file-bytes/png
  cmp "$F/img.out" "$F/ws/img.png"
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/docs/notes.txt" --expect 200 --check . contains 'qa-f16 notes v1' --check-header content-length eq 16
  control-agent-server api GET "/api/conversations/$CID/workspace/my%20file%20%C3%A9.txt" --expect 200 --check . contains 'qa-f16 spaced' --save F16.file-bytes/encoded-name
  ```
  4096字节与文件完全相同。 嵌套文本文件和编码名称 `my file é.txt` 都解析。
- **内容类型 (`F16.content-types`)。**每个分机一个请求。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace/style.css" --expect 200 --check-header content-type eq 'text/css; charset=utf-8' --save F16.content-types/css
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --expect 200 --check-header content-type eq application/json --check qa eq f16
  control-agent-server api GET "/api/conversations/$CID/workspace/pic.svg" --expect 200 --check-header content-type eq image/svg+xml --save F16.content-types/svg
  control-agent-server api GET "/api/conversations/$CID/workspace/img.png" --expect 200 --check-header content-type eq image/png \
    --check-header content-disposition missing
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/docs/notes.txt" --expect 200 --check-header content-type eq 'text/plain; charset=utf-8'
  control-agent-server api GET "/api/conversations/$CID/workspace/blob.qaunknown" --expect 200 --check-header content-type eq application/octet-stream \
    --check-header content-disposition missing --save F16.content-types/unknown
  ```
  每个类型都匹配其扩展名。 未知扩展名将回退到
  `application/octet-stream`. 即使是图像和未知类型也没有
  `Content-Disposition`，因此不会强制下载任何内容。
- **目录索引和丢失文件(`F16.dir-index`)。**一个带有 `index.html` 的目录，一个没有的目录，一个没有工作区的根目录，以及一个丢失的文件。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace/sub" --expect 200 --check . contains qa-f16-sub --save F16.dir-index/sub
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/" --expect 200 --check . contains qa-f16-sub
  control-agent-server api GET "/api/conversations/$CID/workspace/empty-dir" --expect 404 --check detail eq 'No index.html in directory' --save F16.dir-index/no-index
  control-agent-server api GET "/api/conversations/$BARE/workspace" --expect 404 --check detail eq 'No index.html in directory'
  control-agent-server api GET "/api/conversations/$BARE/workspace/readme.txt" --expect 200 --check . contains qa-f16-bare
  control-agent-server api GET "/api/conversations/$CID/workspace/qa-f16-missing.txt" --expect 404 --check detail eq 'File not found' --save F16.dir-index/missing
  ```
  `sub` 服务 `<p>qa-f16-sub</p>` 任一方式； `empty-dir` 和裸工作区根目录为 404 `No index.html in directory`（裸工作区的文件仍然可用），丢失的文件为 404 `File not found`。
- **字节范围 (`F16.range`).**请求前六个字节。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/docs/notes.txt" --header 'Range: bytes=0-5' --expect 206 \
    --check . eq qa-f16 --check-header content-range eq 'bytes 0-5/16' --save F16.range/first-six
  ```
  答案是206 `Partial Content`，带有`Content-Range: bytes 0-5/16`和`qa-f16`，这是PDF和视频观众依赖的内容。
- **直播内容 (`F16.live-content`).**提供一个文件，在磁盘上更改它，然后再次提供它。
  ```sh
  printf 'qa-f16-live v1\n' > "$F/ws/live.txt"
  E1=$(control-agent-server api GET "/api/conversations/$CID/workspace/live.txt" --expect 200 --check . contains 'qa-f16-live v1' --print-header etag)
  printf 'qa-f16-live v2 (longer)\n' > "$F/ws/live.txt"
  control-agent-server api GET "/api/conversations/$CID/workspace/live.txt" --expect 200 --check . contains 'qa-f16-live v2' \
    --check-header etag ne "$E1" --save F16.live-content/after-change
  ```
  第二个请求返回了新的内容和一个不同的 `ETag`。
- **遍历(`F16.traversal-rejected`).**编码的 `..` 段（CLI 按写入方式发送它们； 文字 `../` 将被客户端规范化）和绝对路径，然后是保留在内部的 `..`。
  ```sh
  test -f "$F/outside.txt"
  control-agent-server api GET "/api/conversations/$CID/workspace/%2e%2e/outside.txt" --expect 400 --check detail eq 'Path is outside the workspace' --save F16.traversal-rejected/dotdot
  control-agent-server api GET "/api/conversations/$CID/workspace/..%2Foutside.txt" --expect 400 --check detail eq 'Path is outside the workspace'
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/hostname" --expect 400
  control-agent-server api GET "/api/conversations/$CID/workspace//etc/hostname" --expect 400 --check detail eq 'Path is outside the workspace' --save F16.traversal-rejected/absolute
  control-agent-server api GET "/api/conversations/$CID/workspace/%2Fetc%2Fhostname" --expect 400 --check detail eq 'Path is outside the workspace'
  control-agent-server api GET "/api/conversations/$CID/workspace/sub/%2e%2e/data.json" --expect 200 --check qa eq f16 --save F16.traversal-rejected/inside-dotdot
  ```
  每种转义都是400 `Path is outside the workspace`，没有返回文件内容。 `sub/../data.json` 会内部解决，并被提供。
- **符号链接 (`F16.symlink-escape`).**一个指向外部的文件符号链接，一个指向外部的目录符号链接，以及一个位于内部的符号链接。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace/escape-link.txt" --expect 400 --check detail eq 'Path is outside the workspace' --save F16.symlink-escape/file-outside
  control-agent-server api GET "/api/conversations/$CID/workspace/dir-link/file.txt" --expect 400 --check detail eq 'Path is outside the workspace' --save F16.symlink-escape/dir-outside
  control-agent-server api GET "/api/conversations/$CID/workspace/inside-link.json" --expect 200 --check qa eq f16 --save F16.symlink-escape/inside
  ```
  两种转义链接都返回400（路径在检查之前就被解析了）。 连接到`data.json`。
- **未知且格式错误的 ID (`F16.unknown-conversation`)。**随机 UUID、非 UUID 和无破折号形式的 `CID`。
  ```sh
  Z=00000000-0000-4000-8000-0000000000f6
  control-agent-server api GET "/api/conversations/$Z/workspace" --expect 404 --check detail eq "Conversation not found: $Z" --save F16.unknown-conversation/root
  control-agent-server api GET "/api/conversations/$Z/workspace/index.html" --expect 404 --check detail eq "Conversation not found: $Z"
  control-agent-server api GET /api/conversations/not-a-uuid/workspace --expect 422 --check detail.0.loc.1 eq conversation_id --save F16.unknown-conversation/not-uuid
  control-agent-server api GET /api/conversations/not-a-uuid/workspace/index.html --expect 422
  control-agent-server api GET "/api/conversations/${CID//-/}/workspace/data.json" --expect 200 --check qa eq f16
  ```
  id 在详情中的未知是 404UUID 422 在
  `conversation_id`路径参数，与32字符的十六进制id服务相同工作区。
- **工作区目录消失 (`F16.workspace-dir-missing`).**删除对话的工作区目录，然后将其放回去。
  ```sh
  mkdir -p "$F/gone"
  printf '<p>qa-f16-gone</p>\n' > "$F/gone/index.html"
  GID=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$F/gone" --print-id)
  control-agent-server api GET "/api/conversations/$GID/workspace" --expect 200 --check . contains qa-f16-gone
  rm -rf "$F/gone"
  control-agent-server api GET "/api/conversations/$GID/workspace" --expect 404 --check detail eq 'Workspace directory does not exist' --save F16.workspace-dir-missing/gone
  control-agent-server api GET "/api/conversations/$GID/workspace/index.html" --expect 404 --check detail eq 'Workspace directory does not exist'
  mkdir -p "$F/gone"
  printf '<p>qa-f16-back</p>\n' > "$F/gone/index.html"
  control-agent-server api GET "/api/conversations/$GID/workspace" --expect 200 --check . contains qa-f16-back --save F16.workspace-dir-missing/back
  ```
  目录中缺少两个路由，因此都是404
  `Workspace directory does not exist`; 对话仍然存在，并且立即提供重新创建的目录。
- **已删除的对话 (`F16.deleted-conversation`)。**删除上一个项目符号中的对话并请求其工作区。

  需要：`F16.workspace-dir-missing`
  ```sh
  control-agent-server api DELETE "/api/conversations/$GID" --expect 200
  control-agent-server api GET "/api/conversations/$GID" --expect 404
  control-agent-server api GET "/api/conversations/$GID/workspace" --expect 404 --check detail eq "Conversation not found: $GID" --save F16.deleted-conversation/root
  control-agent-server api GET "/api/conversations/$GID/workspace/index.html" --expect 404
  test -f "$F/gone/index.html"
  ```
  工作区 URL 会停止服务，但用户提供的目录及其文件会留在磁盘上。
- **工作树对话 (`F16.worktree-served`).**在 git 测试夹具上启动 `worktree: true` 对话，其签出有未提交的编辑
  `README.md`和未跟踪的`notes.txt`，然后将文件写入工作树。
  ```sh
  REPO=$(control-agent-server fixture git-repo --name qa-f16-repo --print-path)
  WT=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$REPO" --body-json '{"worktree": true}' --print-id)
  WTD=$(control-agent-server api GET "/api/conversations/$WT" --field workspace.working_dir)
  test "$WTD" != "$REPO" && test -f "$WTD/README.md" && test -f "$REPO/notes.txt"
  printf '<p>qa-f16-wt</p>\n' > "$WTD/qa-f16-wt.html"
  control-agent-server api GET "/api/conversations/$WT/workspace/qa-f16-wt.html" --expect 200 --check . contains qa-f16-wt --save F16.worktree-served/worktree-file
  git -C "$REPO" show HEAD:README.md > "$F/readme-head.md"
  if cmp -s "$F/readme-head.md" "$REPO/README.md"; then false; fi
  control-agent-server api GET "/api/conversations/$WT/workspace/README.md" --expect 200 --raw-out "$F/readme-served.md" --save F16.worktree-served/committed
  cmp "$F/readme-served.md" "$F/readme-head.md"
  control-agent-server api GET "/api/conversations/$WT/workspace/notes.txt" --expect 404 --check detail eq 'File not found' --save F16.worktree-served/untracked
  ```
  工作目录是工作树，不是测试夹具。 在那里写入的文件将被服务。 `README.md` 会被返回为已提交（检查出的编辑不同且未被服务），而未跟踪的 `notes.txt` 却是 404，尽管它存在于源检查出的版本中。
- **标头或 cookie (`F16.auth`)。**没有密钥、错误的密钥、标头，然后是类似浏览器的 jar 中的 cookie，以及具有错误值的 cookie。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/workspace" --auth none --expect 401 --check detail eq Unauthorized --save F16.auth/no-key
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/conversations/00000000-0000-4000-8000-0000000000f6/workspace/data.json --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --expect 200 --check qa eq f16
  control-agent-server api POST /api/auth/workspace-session --jar qa-f16 --expect 204 --check-header set-cookie contains oh_workspace_session_key=
  control-agent-server api GET "/api/conversations/$CID/workspace" --auth none --jar qa-f16 --expect 200 --check . contains qa-f16-root --save F16.auth/cookie-root
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --auth none --jar qa-f16 --expect 200 --check qa eq f16 --save F16.auth/cookie-file
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --auth none --cookie 'oh_workspace_session_key=qa-f16-wrong' --expect 401 --save F16.auth/wrong-cookie
  ```
  在查找对话之前，缺少和错误的密钥会导致401 `Unauthorized`。 仅凭头信息和cookie（没有头信息）都会打开两个端点，且cookie的值不是会话密钥时返回401。
- **智能体自己的神器(`F16.agent-artifact`)。**一个小型模型运行会写入一个 HTML 文件； 事件套接字被实时捕获，工作区路由为文件提供服务。
  ```sh
  mkdir -p "$F/agent"
  AID=$(control-agent-server conversation start --no-run --tools file_editor --no-autotitle --workspace "$F/agent" --print-id)
  control-agent-server ws start "/sockets/events/$AID" --name qa-f16-agent --duration 300
  control-agent-server conversation send "$AID" --text 'Use the file_editor tool to create the file qa-f16-agent.html in the current working directory containing exactly: <p>qa-f16-agent</p>' \
    --wait --until finished --timeout 300
  control-agent-server ws stop qa-f16-agent --kinds ObservationEvent --contains qa-f16-agent.html --expect-min 1 --wait 20 --save F16.agent-artifact/events
  control-agent-server api GET "/api/conversations/$AID/workspace/qa-f16-agent.html" --expect 200 --check . contains qa-f16-agent \
    --check-header content-type eq 'text/html; charset=utf-8' --save F16.agent-artifact/served
  test -f "$F/agent/qa-f16-agent.html"
  ```
  端口承载着文件编辑器的 `ObservationEvent`
  `qa-f16-agent.html`，工作区URL充当HTML； 该文件位于磁盘上的对话工作区中。
- **重新启动 (`F16.restart`)。**重新启动服务器并提供相同对话的文件。
  ```sh
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$CID/workspace/data.json" --expect 200 --check qa eq f16 --save F16.restart/header
  control-agent-server api GET "/api/conversations/$CID/workspace" --auth none --jar qa-f16 --expect 200 --check . contains qa-f16-root --save F16.restart/cookie
  control-agent-server doctor
  ```
  持久化会话恢复，工作区会话被服务。 重启之前 minted 的 cookie 仍然有效（其值是不变的会话密钥）。
- **VS 代码已禁用 (`F16.vscode-disabled`)。**启动器的默认值。
  ```sh
  control-agent-server config | jq -e '.config_file.enable_vscode == false'
  control-agent-server api GET /api/vscode/status --expect 200 --check running eq false --check enabled eq false \
    --check message eq 'VSCode is disabled in configuration' --save F16.vscode-disabled/status
  control-agent-server api GET "/api/conversations/$CID/vscode/status" --expect 200 --check running eq false --check enabled eq false \
    --check message eq 'VSCode is disabled in configuration'
  control-agent-server api GET /api/vscode/url --expect 503 --check detail eq 'Internal Server Error' \
    --check exception contains 'VSCode is disabled in configuration' --save F16.vscode-disabled/url
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --expect 503 --check exception contains 'Set enable_vscode=true to enable'
  ```
  状态显示已禁用，并有消息。 URL 路由返回 503 状态码，而 5xx 路由的正文是 `{"detail": "Internal Server Error", "exception": "503: VSCode is disabled in configuration. Set enable_vscode=true to enable."}`。
- **范围守卫 (`F16.vscode-scoped-guards`).**错误的对话和错误的文件夹，而 VS Code 仍然处于禁用状态。
  ```sh
  Z=00000000-0000-4000-8000-0000000000f6
  control-agent-server api GET "/api/conversations/$Z/vscode/status" --expect 404 --check detail eq "Conversation not found: $Z" --save F16.vscode-scoped-guards/unknown
  control-agent-server api GET "/api/conversations/$Z/vscode/url" --expect 404
  control-agent-server api GET /api/conversations/not-a-uuid/vscode/status --expect 422 --check detail.0.loc.1 eq runtime_conversation_id
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query workspace_dir=/etc --expect 422 \
    --check detail eq 'workspace_dir must be inside the conversation workspace' --save F16.vscode-scoped-guards/outside
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query workspace_dir=sub --expect 422 --check detail eq 'workspace_dir must be inside the conversation workspace'
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query "workspace_dir=$WS/sub/../../outside-dir" --expect 422
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query "workspace_dir=$WS/dir-link" --expect 422
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query "workspace_dir=$WS/sub" --expect 503
  ```
  未知是 404，不是一个UUID 422 对于 `status`; 一个相对的文件夹，一个外部的文件夹，一个爬出的文件夹 `..` 和一个指向的符号链接工作区 422。 在里有一个文件夹工作区通过了检查并到达了禁用检查（503）。
- **VS Code 路由仅包含标头 (`F16.vscode-auth`)。**所有四个路由上都没有键，然后是范围内的 `F16.auth` 中的工作区 cookie。
  ```sh
  control-agent-server api GET /api/vscode/status --auth none --expect 401 --save F16.vscode-auth/status-no-key
  control-agent-server api GET /api/vscode/url --auth bad --expect 401
  control-agent-server api GET "/api/conversations/$CID/vscode/status" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID/workspace" --auth none --jar qa-f16 --expect 200
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --auth none --jar qa-f16 --expect 401 --check detail eq Unauthorized --save F16.vscode-auth/cookie-url
  control-agent-server api GET "/api/conversations/$CID/vscode/status" --auth none --jar qa-f16 --expect 401
  ```
  没有头信息时，每个 VS Code 路由都是 401。 罐子的cookie路径
  `/api/conversations`，因此浏览器将其发送到作用域路由）仍然打开工作区，但不会打开携带会话密钥的 URL。
- **已启用但未运行(`F16.vscode-enabled-status`).**持有带有HTTP源的端口，然后在该端口上启用VS Code，这样无论二进制是否安装，都无法启动。
  ```sh
  SINK=$(control-agent-server fixture http-sink --name qa-f16-vscode-port | jq -r .url)
  VPORT=${SINK##*:}
  control-agent-server restart --config-json '{"enable_vscode": true, "vscode_port": '"$VPORT"'}'
  control-agent-server logs --grep 'VSCode service failed to start' --expect-min 1
  control-agent-server api GET /api/vscode/status --expect 200 --check . eq '{"running": false, "enabled": true}' --save F16.vscode-enabled-status/status
  control-agent-server api GET "/api/conversations/$CID/vscode/status" --expect 200 --check . eq '{"running": false, "enabled": true}'
  control-agent-server doctor
  ```
  日志显示`VSCode service failed to start, continuing without VSCode`； 两个状态路由都返回 `{"running": false, "enabled": true}`（没有 `message`），且服务器其他方面都健康。
- **URL shape (`F16.vscode-url-shape`).** 全球和全局 URLs带有和不带覆盖项，然后带有基础路径。 A URL 仅被广告
  while VS Code runs (`F16.vscode-url-not-running`), so this needs the
  OpenVSCode 服务器二进制文件（参见 `F16.vscode-running`）。 首先在空闲端口上启动 VS Code，然后将保留的端口放回最后。

  需要：`F16.vscode-enabled-status`
  需求：`vscode`
  ```sh
  URL_PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  control-agent-server restart --config-json '{"vscode_port": '"$URL_PORT"'}'
  control-agent-server doctor
  control-agent-server api GET /api/vscode/status --expect 200 --check running eq true
  KEY=$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")
  control-agent-server api GET /api/vscode/url --expect 200 --check url eq "http://localhost:$URL_PORT/?tkn=$KEY&folder=workspace" --save F16.vscode-url-shape/global
  control-agent-server api GET /api/vscode/url --query base_url=https://qa-f16.example:9443/ --query workspace_dir=/qa/f16 --expect 200 \
    --check url eq "https://qa-f16.example:9443/?tkn=$KEY&folder=/qa/f16"
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --expect 200 --check url eq "http://localhost:$URL_PORT/?tkn=$KEY&folder=$WS" --save F16.vscode-url-shape/scoped
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query "workspace_dir=$WS/sub" --expect 200 --check url eq "http://localhost:$URL_PORT/?tkn=$KEY&folder=$WS/sub"
  control-agent-server restart --config-json '{"vscode_base_path": "/qa-f16/vscode/"}'
  control-agent-server doctor
  control-agent-server api GET /api/vscode/url --expect 200 --check url eq "http://localhost:$URL_PORT/qa-f16/vscode/?tkn=$KEY&folder=workspace" --save F16.vscode-url-shape/base-path
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --query base_url=https://qa-f16.example --expect 200 \
    --check url eq "https://qa-f16.example/qa-f16/vscode/?tkn=$KEY&folder=$WS"
  unset KEY
  control-agent-server restart --reset-config --config-json '{"enable_vscode": true, "vscode_port": '"$VPORT"'}'
  ```
  的 token 这是会话密钥（已脱敏在输出和证据中，端口是 `vscode_port`, `base_url` 失去尾部斜杠后，该文件夹将默认指向对话框工作目录，并且基础路径位于起源和 `/?tkn=`.
- **不运行，不做广告 (`F16.vscode-url-not-running`)。**读取键控运行的状态和 URL，其中 VS Code 未运行。

  需要：`F16.vscode-enabled-status`
  ```sh
  control-agent-server api GET /api/vscode/status --expect 200 --check enabled eq true --check running eq false
  control-agent-server api GET /api/vscode/url --expect 200 --check . eq '{"url": null}' --save F16.vscode-url-not-running/global
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --expect 200 --check . eq '{"url": null}'
  ```
  `running` 为 False，因此两个路由的响应体都严格为 `{"url": null}`；无密钥服务器（`F16.vscode-url-no-key`）和通过 `POST /api/init` 收到完全相同密钥的服务器（`F16.vscode-url-after-init`）均如此。 `get_vscode_service()` 种子 token 来自
  `session_api_keys[0]` 之前 `start()` 运行，但 `get_vscode_url` 返回一个 URL 只有在服务器运行时，所以不会发放“服务器不存在的”死“打开 VS Code”链接（以及没有会话密钥）。
- **包含 `&` 和 `#` (`F16.vscode-folder-encoding`) 的文件夹。**像浏览器一样解析范围 URL，首先解析正常的工作区，然后解析名为 `qa f16&x=1#frag` 的工作区。 需要运行 VS Code（OpenVSCode 服务器二进制文件，请参阅 `F16.vscode-running`）：未运行的服务器不会通告 URL。

  需要：`F16.vscode-enabled-status`
  需求：`vscode`
  ```sh
  ENCODING_PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  control-agent-server restart --reset-config --config-json '{"enable_vscode": true, "vscode_port": '"$ENCODING_PORT"'}'
  control-agent-server doctor
  control-agent-server api GET /api/vscode/status --expect 200 --check running eq true
  ROUNDTRIP='import sys, urllib.parse as u; p = u.urlsplit(sys.stdin.read().strip()); q = u.parse_qs(p.query); sys.exit(0 if q.get("folder") == [sys.argv[1]] and not p.fragment else 1)'
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --expect 200 --field url | python3 -c "$ROUNDTRIP" "$WS"
  mkdir -p "$F/qa f16&x=1#frag"
  ODD=$(control-agent-server conversation start --no-run --tools none --no-autotitle --workspace "$F/qa f16&x=1#frag" --print-id)
  OWS=$(control-agent-server api GET "/api/conversations/$ODD" --field workspace.working_dir)
  control-agent-server api GET "/api/conversations/$ODD/vscode/url" --expect 200 --save F16.vscode-folder-encoding/odd-folder
  control-agent-server api GET "/api/conversations/$ODD/vscode/url" --expect 200 --field url \
    | python3 -c 'import sys, json, urllib.parse as u; p = u.urlsplit(sys.stdin.read().strip()); print(json.dumps({"folder": u.parse_qs(p.query).get("folder"), "fragment": p.fragment}))' \
    | control-agent-server assert --check folder len-eq 1 --check folder.0 eq "$OWS" --check fragment eq ''
  control-agent-server restart --reset-config --config-json '{"enable_vscode": true, "vscode_port": '"$VPORT"'}'
  ```
  正常的工作区次往返。 对于那个特殊的 `folder` 参数解码后为 `.../qa f16&x=1#frag`，没有片段：查询值是百分编码的 (`/` 保持不变)，因此解析器不会读取
  `folder=.../qa f16`、一个额外的 `x=1` 参数和一个 `#frag` 片段。
- **没有钥匙，没有URL（`F16.vscode-url-no-key`）。**第二个服务器没有会话密钥，在接收器仍然保留的端口上启用了 VS Code。

  需要：`F16.vscode-enabled-status`
  ```sh
  NK=$(control-agent-server launch --new --no-auth --vscode --name f16-nokey --config-json '{"vscode_port": '"$VPORT"'}' --print-run)
  trap 'control-agent-server stop --run "$NK" >/dev/null' EXIT
  mkdir -p "$NK/fixtures/qa-f16-ws"
  NC=$(control-agent-server conversation start --run "$NK" --no-run --tools none --no-autotitle --workspace "$NK/fixtures/qa-f16-ws" --print-id)
  control-agent-server api GET /api/vscode/status --run "$NK" --auth none --expect 200 --check enabled eq true --check running eq false
  control-agent-server api GET /api/vscode/url --run "$NK" --auth none --expect 200 --check . eq '{"url": null}' --save F16.vscode-url-no-key/global
  control-agent-server api GET "/api/conversations/$NC/vscode/url" --run "$NK" --auth none --expect 200 --check . eq '{"url": null}'
  control-agent-server stop --run "$NK"
  ```
  没有密钥，且端口被持有，所有 URL 路由都响应
  `{"url": null}` 而 `running` 是 False（请参阅在具有二进制文件的计算机上创建 token 的陷阱）。 第二次运行的证据位于其自己的运行目录下。
- **由 init 传递的密钥，无 URL (`F16.vscode-url-after-init`)。**延迟初始化服务器在没有密钥的情况下启动，在保留的端口上启用 VS Code，然后使用会话密钥进行初始化，就像热池一样。

  需要：`F16.vscode-enabled-status`
  ```sh
  DI=$(control-agent-server launch --new --no-auth --deferred-init --vscode --name f16-deferred --config-json '{"vscode_port": '"$VPORT"'}' --print-run)
  trap 'control-agent-server stop --run "$DI" >/dev/null' EXIT
  control-agent-server api POST /api/init --run "$DI" --auth none --header "X-Init-API-Key: $(cat "$DI/private/secret_key")" \
    --json '{"session_api_keys": ["qa-f16-init-key"]}' --expect 200 --check state eq ready
  control-agent-server api GET /api/vscode/url --run "$DI" --auth none --expect 401
  control-agent-server api GET /api/vscode/status --run "$DI" --auth none --header 'X-Session-API-Key: qa-f16-init-key' --expect 200 \
    --check enabled eq true --check running eq false --save F16.vscode-url-after-init/status
  control-agent-server api GET /api/vscode/url --run "$DI" --auth none --header 'X-Session-API-Key: qa-f16-init-key' --expect 200 \
    --check . eq '{"url": null}' --save F16.vscode-url-after-init/url
  control-agent-server stop --run "$DI"
  ```
  交付的密钥被强制执行（401状态，缺少密钥）
  `{"running": false, "enabled": true}`. 的 URL 是 null: `/api/init` 只有当它运行时，才将钥匙交给VS Code`set_connection_token`), 且一个未运行的服务器不提供任何 URL像键启动一样
  `F16.vscode-url-not-running`.
- **Docker-mode root 和 cookie (`F16.docker-root-cookie`), 已知错误。** 第二个服务器有 `OH_CONVERSATION_RUNTIME=docker`. 已翻译：无 Docker 需要守护进程，因为路由表及其认证组在启动时是固定的（这只会警告它无法列出容器，而不会显示哪个组回答了）。
  ```sh
  DK=$(control-agent-server launch --new --name f16-docker --env OH_CONVERSATION_RUNTIME=docker --print-run)
  trap 'control-agent-server stop --run "$DK" >/dev/null' EXIT
  Z=00000000-0000-4000-8000-0000000000f6
  control-agent-server api GET "/api/conversations/$Z/workspace/" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server api GET "/api/conversations/$Z/workspace" --run "$DK" --expect 404 --check detail eq 'Conversation not found'
  control-agent-server api GET "/api/conversations/$Z/workspace/" --run "$DK" --auth none --expect 401
  control-agent-server api POST /api/auth/workspace-session --run "$DK" --jar qa-f16-docker --expect 204
  control-agent-server api GET "/api/conversations/$Z/workspace/" --run "$DK" --auth none --jar qa-f16-docker --expect 404 --save F16.docker-root-cookie/slash
  control-agent-server api GET "/api/conversations/$Z/workspace" --run "$DK" --auth none --jar qa-f16-docker --expect 404 --save F16.docker-root-cookie/slashless  # bug: status eq 401
  control-agent-server stop --run "$DK"
  ```
  两个表单都到达了 Docker 路由（404）。 一无所有，
  `workspace/` 是 401。 仅使用 cookie，`workspace/` 会传递工作区身份验证组 (404)，但无斜线 `workspace` 会回答 401：`docker_workspace_router` 只定义
  `/{conversation_id}/workspace/{file_path:path}`，因此根属于仅标头会话代理。 在本地模式下，无斜杠根接受 cookie (`F16.auth`)。 使用尾部斜杠的客户端（TypeScript 客户端使用）不受影响。
- **实际运行的 VS Code (`F16.vscode-running`).**
  需求：`vscode`

  需要 OpenVSCode 服务器二进制文件
  `/openhands/.openvscode-server/bin/openvscode-server`（路径是硬编码的；
  `control-agent-server capabilities` 报告 `vscode`）。
  ```sh
  control-agent-server restart --reset-config --config-json '{"enable_vscode": true}'
  control-agent-server doctor
  control-agent-server api GET /api/vscode/status --expect 200 --check enabled eq true --check running eq true
  control-agent-server api GET "/api/conversations/$CID/vscode/url" --expect 200 --check url contains "folder=$WS"
  control-agent-server api GET /api/vscode/url --field url --unsafe-unredacted \
    | xargs curl -sS --noproxy '*' --location \
      --cookie-jar "$AGENT_SERVER_VERIFY_RUN/private/qa-f16-vscode-cookies" \
      --cookie "$AGENT_SERVER_VERIFY_RUN/private/qa-f16-vscode-cookies" \
      -o "$AGENT_SERVER_VERIFY_RUN/private/qa-f16-vscode-editor.html" -w '%{http_code}\n' \
    | control-agent-server assert --check . eq 200
  control-agent-server exec --save F16.vscode-running/editor -- python3 -c \
    'import json,pathlib,sys; body=pathlib.Path(sys.argv[1]).read_text(); assert "workbench" in body; print(json.dumps({"editor_html":True}))' \
    "$AGENT_SERVER_VERIFY_RUN/private/qa-f16-vscode-editor.html"
  ```
  带有二进制和一个免费的 `vscode_port`，状态报告 `running: true` 和广告 URL 的回答将以 200 响应。

<a id="gotchas"></a>

## 陷阱

- 5xx 答案由服务器的异常处理程序重写：
  `detail` 始终是 `Internal Server Error`，真正的原因在于
  `exception` (`"503: VSCode is disabled ..."`). 检查`exception`，没有
  `detail`.
- VS Code URL 中的 `tkn` 是第一个会话密钥。 CLI 在输出、证据和 `--field url` 输出中对其进行了编辑。 仅当将 URL 直接输送到其 HTTP 使用者时才使用 `--unsafe-unredacted`，正如编辑器检查所做的那样； 它的 cookies 和 HTML 保留在运行的私有目录中。
  `map run` 保存了每个变量 `map-run/*.state.sh` 为子弹所分配的值，因此一个 URL 或 `F16.vscode-url-shape` 保持在变量中的键会存入磁盘 (`KEY` 会取消）。
- VS Code 仅在 `/openhands/.openvscode-server/bin/openvscode-server` 存在且 `vscode_port` 空闲时启动，并且仅在启动时启动； 它从来没有重试。 日志行 `VSCode server binary not found, VSCode will be disabled` 并不意味着 `enabled: false`：状态仍然显示 `enabled: true`。 该服务是一个从配置文件和环境构建的进程单例，可以通过 `restart --config-json`（在重启后覆盖累积）来切换
  `--reset-config`).
- 对于隔离的功能通道，请使用存储库 Dockerfile 中固定的 OpenVSCode 版本并验证其版本资产校验和。 将其解压到任务工具目录并将其绑定到一次性容器内的固定路径。 以普通用户身份运行源 checkout 及其 Python 环境，并使用 `doctor` 验证目标构建 SHA； 基础映像的捆绑服务器不是正在测试的源。
- URL 仅在 VS Code 运行时 (`F16.vscode-url-not-running`) 才会公布，因此 `F16.vscode-url-shape` 和 `F16.vscode-folder-encoding` 仅在安装了 OpenVSCode 二进制文件时才可观察，如 `F16.vscode-running`； 在没有它的机器上，它们会被阻止。
- null URL 在整个主体 (`--check . eq '{"url": null}'`) 上被断言：
  当密钥不存在时，`--check url missing`和`--check url eq null`也会通过，这会破坏期望它的SDK和TypeScript模型。
- 随着 OpenVSCode binary `start()` 生成随机数 token 在端口检查之前（`tests/agent_server/test_vscode_service.py::test_start_port_unavailable`), 因此，一个无密钥或延迟服务器，其 VS Code 在持有的端口上失败了，持有  token 太； `F16.vscode-url-no-key` 和 `F16.vscode-url-after-init` still answer `{"url": null}` 那是因为  URL 需要运行中的服务器。
- 范围内的 VS Code 路由运行对话查找，并且
  `workspace_dir` 在启用检查之前进行防护，因此它们的 404 和 422 答案不依赖于配置。 全局`/api/vscode/url`不检查
  `workspace_dir` 完全没有。
- `api` 发送已由 HTTP 客户端规范化的文字 `..` 段； 遍历探针必须对它们进行百分比编码（`%2e%2e`、`..%2F`）或使用双斜杠作为绝对路径。
- 工作区文件由实时对话提供
  `workspace.working_dir`（工作树对话的工作树）； 点文件（例如 `.git/config` 或 `.env`）与任何其他文件一样提供。
- 没有条件请求支持：`If-None-Match` 与当前
  `ETag` 仍然返回 200，带有内容，`HEAD` 是 405（FastAPI 和 GET 路由不添加 HEAD）。
- 工作区路由安装在它们自己的路由器上（标头或 cookie 身份验证），该路由器也带有休眠门； 在 deferred-init 模式下，它们在任何身份验证之前都会使用门的原因回答 503（请参阅 F03）。 在Docker运行模式下，`workspace/{file_path}`被代理到会话的容器中，而本地处理器的`Conversation workspace is not local`分支不可达（本地注册表只接受）
  `LocalWorkspace`).
- CORS 在工作区路线上，任何 http(s) 源都会凭据 (F02.cors-工作区-routes)，因此这些路由所服务的内容对任何持有分区 cookie 的页面都是可读的。
