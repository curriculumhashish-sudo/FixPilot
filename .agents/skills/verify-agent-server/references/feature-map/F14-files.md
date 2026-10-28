<a id="file-upload-download-archive-and-directory-helpers"></a>

# 文件上传、下载、归档和目录助手

Agent Server 主机及其周围的目录助手上的字节级文件传输。 消费者为每个多部分请求上传一个文件（字段 `file`，`path` 查询中的目标），将其作为一个文件下载回来
`application/octet-stream` 附件，创建目录 (`mkdir -p`), 将目录打包为 Git 拉取补丁或  `tar.gz` 为了持久化，并导出一个会话的已持久化轨迹就像一个.zip文件凭据已脱敏。 的工作区 picker 列出了服务器用户的家目录，以及任何绝对路径的子目录。 除了 ，所有操作都无效 `home` 和 `search_subdirs` 也存在于 `/api/conversations/{runtime_conversation_id}/file/...`，路径必须在那个对话中解析工作区; 全局路由接受任何绝对路径，因此会话密钥是它们唯一的保护。

资料来源：`openhands-agent-server/openhands/agent_server/file_router.py`、`openhands-agent-server/openhands/agent_server/runtime_router.py`、`openhands-agent-server/openhands/agent_server/_secret_redaction.py`、`openhands-sdk/openhands/sdk/git/utils.py`、`openhands-sdk/openhands/sdk/workspace/remote/remote_workspace_mixin.py`、`clients/typescript/src/client/file-client.ts`、`clients/typescript/src/workspace/remote-workspace.ts`

需求：`llm`、`git`、`node`

Routes: `GET /api/file/home`, `GET /api/file/search_subdirs`,
`POST /api/conversations/{runtime_conversation_id}/file/upload`,
`GET /api/conversations/{runtime_conversation_id}/file/download`,
`POST /api/conversations/{runtime_conversation_id}/file/create_directory`,
`GET /api/conversations/{runtime_conversation_id}/file/download-trajectory/{conversation_id}`,
`GET /api/conversations/{runtime_conversation_id}/file/archive`,
`POST /api/file/upload`, `GET /api/file/download`,
`POST /api/file/create_directory`,
`GET /api/file/download-trajectory/{conversation_id}`, `GET /api/file/archive`

<a id="sub-features"></a>

## 子功能

- `F14.auth`：每个全局和对话范围的文件路由都会在没有有效会话密钥的情况下回答 401，并且不写入任何内容。
- `F14.upload-download`：多部分上传创建缺失的父目录，下载返回以字节形式相同的字节作为`application/octet-stream`附件，且同一路径的第二次上传会替换内容。
- `F14.upload-errors`：没有`file`部分或没有`path`的上传是422，相对的`path`是400`Path must be absolute`。
- `F14.upload-onto-directory`：上传到现有目录或父级为文件的路径是客户端错误 (400)，正如 `create_directory` 对相同冲突的回答一样。
- `F14.upload-size`：SDK的`RemoteWorkspace.file_upload`和TypeScript`RemoteWorkspace.fileUpload`报告上传的`file_size`，与`LocalWorkspace.file_upload`一样； 上传响应将其携带为`{"success": true, "file_size": N}`。
- `F14.upload-atomic`：写入过程中失败的覆盖使前一个文件完好无损； 今天，目标在流式传输之前被截断并保留部分文件。
- `F14.download-errors`：下载缺失文件为404`File not found`，目录400`Path is not a file`，相对路径400。
- `F14.mkdir`: `create_directory` 创建缺失的父目录，是幂等的，并且保持现有内容。新的目录通过 `search_subdirs` 列出，且路径或运行在文件上会返回 400。
- `F14.home`: `GET /api/file/home` 报告服务器用户的 `HOME`其可见的顶级目录按不区分大小写的排序显示 `favorites` (没有文件，没有符号链接) `/` 作为唯一的位置，仅隐藏的目录只有 `include_hidden=true`.
- `F14.subdirs`: `search_subdirs` 只列出绝对路径的直接实际子目录（没有文件，没有符号链接，只有以 `include_hidden=true` 为隐藏标志），不区分大小写，以绝对路径排序。
- `F14.subdirs-pagination`：`limit`和`next_page_id`光标翻页条目； `limit` 1..100 之外是 422。
- `F14.subdirs-errors`: `search_subdirs` 在缺失目录上为 404，在文件上为 400，在相对路径上为 400。
- `F14.subdirs-case-pagination`：在两个仅大小写不同的目录（`Foo`，`foo`）中跟随`next_page_id`到达第二个目录，而不是永远重复第一页。
- `F14.archive-tar`: `format=tar.gz` 返回一个名为 `application/gzip` 的 `<dir>.tar.gz` 归档，根目录为 `<dir>/`，包含 `archive_manifest.json`，即仓库身份头，但没有 `X-Archive-Base-*`，即默认排除，`.git/` 和 `node_modules/`，软链接被跳过，且在父目录中没有留下临时文件。
- `F14.archive-excludes`: `use_default_excludes=false` 保留 `node_modules` 和 `.git` 内部结构，但从不 `.git/config` 或引用日志； `exclude=<glob>`（可重复）删除匹配的文件并记录在清单中。
- `F14.archive-git-delta`：默认的 `git-delta` 格式是 `base_ref=HEAD` 的 `text/x-patch`，适用于克隆的 HEAD 的未提交和未跟踪更改，包含 `X-Archive-Base-Commit`、`X-Archive-Base-Ref`、`X-Archive-Branch` 和 `X-Archive-Head-Commit`，且不会影响仓库的索引。 如果在无远程存储库上没有 `base_ref`，则该补丁是针对空树的，并且没有基本标头； 存储库的子目录仅生成该子树的增量。
- `F14.archive-auto-base`：没有`base_ref`，具有`origin`远程的克隆与`origin/<branch>`不同（补丁保存本地提交和未提交的编辑，适用于原始提示的克隆，并带有`X-Archive-Base-Ref: auto`，`X-Archive-Base-Commit` =原始提示和`X-Archive-Repo-Remote`）； 分离的HEAD与HEAD本身不同。
- `F14.archive-nested-repo`：归档一个恰好包含一个 git 存储库的非存储库目录，归档该存储库； 有两个存储库 `git-delta` 是 400，`tar.gz` 归档目录本身。
- `F14.archive-format-doc`: OpenAPI描述了`format`，这与一个只包含一个仓库归档的非仓库目录不一致：它没有承诺“整个目录”，只说内部的仓库是压缩的。
- `F14.archive-errors`：相对路径为400，缺失目录为404，文件为400，以`base_ref`开头的`-`为400，未知`base_ref`为400，未知`format`为422，以及非仓库目录的`git-delta`为400。
- `F14.trajectory`: `GET /api/file/download-trajectory/{id}` 返回 `<hex>.zip`，`meta.json`，`base_state.json`，每个事件一个文件，使用 LLM `api_key` 已脱敏到 `**********`，没有 Fernet 密文，对于带点和十六进制 ID，不会留下临时的 zip 文件。
- `F14.trajectory-errors`：未知对话 ID 为 404 `Conversation not found`，格式错误的 ID 422。
- `F14.trajectory-concurrent`：并发相同轨迹的下载每次返回200和一个有效的zip（五轮六次并行下载，总共30个）。
- `F14.trajectory-init-path`：在延迟初始化服务器上​​`POST /api/init`设置`conversations_path`之后，存储在那里的轨迹是可下载的。
- `F14.scoped-transfer`：对话范围的上传、下载和 `create_directory` 在对话的工作区内工作，范围下载返回智能体写入的文件。
- `F14.scoped-path-guard`: 范围内的路由拒绝路径之外的工作区（另一个对话的工作区、`..` 递归、符号链接逃逸、同前缀的兄弟、相对路径）并返回 422，而全局路由则提供相同的路径。
- `F14.scoped-conversation-errors`：未知会话的作用域路由为 404，不执行任何操作； 格式错误的对话 ID 为 422。
- `F14.scoped-trajectory-archive`：仅服务于其自身的会话（另一个或无效的ID是422），并且工作区包含智能体的文件，但拒绝路径之外的路径，返回422。
- `F14.sdk-workspace`：SDK 的 `RemoteWorkspace.file_upload`/`file_download` 通过全局路由的往返字节，以及 `runtime_conversation_id` 通过作用域路由的往返字节； 工作区之外的范围上传返回带有 422 的 `success=False` 并且不写入任何内容。
- `F14.restart`：重启后，上传的文件、范围下载和轨迹仍然有效。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，全局：`POST /api/file/upload?path=...`（多部分字段`file`），
  `GET /api/file/download?path=...`, `POST /api/file/create_directory?path=...`,
  `GET /api/file/archive?path=...&format=git-delta|tar.gz&base_ref=...&use_default_excludes=...&exclude=...`,
  `GET /api/file/download-trajectory/{conversation_id}`. 下面的每个食谱都驱动这些。
- REST，对话范围：下相同的五个操作
  `/api/conversations/{runtime_conversation_id}/file/...`; 依赖项 (`bind_local_conversation_runtime`) 解析 `path` 并拒绝 `workspace.working_dir` 之外的任何内容，并且轨迹 id 必须等于运行时 id。 由`F14.scoped-*`和`F14.restart`子弹驱动。
- REST，发现（仅限全局，没有范围变体）：
  `GET /api/file/home?include_hidden=...` 和
  `GET /api/file/search_subdirs?path=...&limit=...&page_id=...&include_hidden=...`.
- SDK: `RemoteWorkspace.file_upload()` / `file_download()`（和异步
  `AsyncRemoteWorkspace` 版本）调用 `/api/file/upload|download`，或者当工作区具有 `runtime_conversation_id` 时的作用域路由。 驱动力
  `F14.sdk-workspace`（`exec` 程序，两个范围）和 `F14.upload-size`（上传结果的 `file_size`，针对 `LocalWorkspace.file_upload`）。
- TypeScript 客户端：`FileClient.uploadFile`、`uploadTextFile`、`downloadFile`、
  `downloadTextFile`、`downloadTrajectory`（当设置 `conversationId` 时，其作用范围为运行时传输层）、`getHome`、
  `searchSubdirectories`; `RemoteConversation.downloadTrajectory()`采用全局轨迹路线； `RemoteWorkspace.fileUpload`/`fileDownload` 通话
  `/api/file/upload|download`（TypeScript`write_file`工具报告
  `fileUpload`'s `file_size`). `F14.upload-size` 驱动器
  `RemoteWorkspace.fileUpload`来自构建的`clients/typescript/dist`。
- Agent Canvas（仅上下文）：工作区选择器使用`home`和
  `search_subdirs`; 文件上传和“下载轨迹”使用传输路径。 `archive` 和 `create_directory` 没有回购内消费者； 托管应用程序在删除运行时之前将它们调用持久化 a 工作区。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已实时并导出，`doctor` 正常，`$DEEPSEEK_API_KEY` 已设置并且
  `git` 已安装。 不需要启动标志； init 项目符号启动并停止它自己的 deferred-init 服务器。
- 下面的块首先重新启动服务器
  `GIT_CEILING_DIRECTORIES` 设置为运行目录，因此服务器上的 git 无法发现运行之上的存储库（杂散 `/tmp/.git` 将每个“非存储库”测试夹具变成该存储库的一部分，并停止服务器
  `git init`ing工作区； 请参阅陷阱）。 它然后激活`deepseek-flash`，在`$AGENT_SERVER_VERIFY_RUN/fixtures/`下创建运行所有者测试夹具（一个70 kB的随机blob，一个小文本文件，`qa-f14-repo`的git测试夹具，`node_modules/`和`qa.log`添加），运行一个小型模型对话`CID`，其智能体写入
  `qa-f14-agent.txt` 使用文件编辑器（不需要 `tmux`），并使用它自己的工作区创建第二个从未运行的对话 `CID2`。
  ```sh
  control-agent-server restart --env GIT_CEILING_DIRECTORIES="$AGENT_SERVER_VERIFY_RUN"
  control-agent-server llm preset deepseek
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f14"
  mkdir -p "$F"
  head -c 70000 /dev/urandom > "$F/blob.bin"
  printf 'qa-f14 v2\n' > "$F/v2.txt"
  REPO=$(control-agent-server fixture git-repo --name qa-f14-repo --print-path)
  mkdir -p "$REPO/node_modules/pkg"
  printf 'j\n' > "$REPO/node_modules/pkg/j.js"
  printf 'log\n' > "$REPO/qa.log"
  CID=$(control-agent-server conversation start --tools file_editor --no-autotitle \
    --prompt 'Use the file_editor tool to create the file qa-f14-agent.txt in the current working directory containing exactly: hi' \
    --wait --until finished --timeout 300 --print-id)
  WS=$(control-agent-server api GET "/api/conversations/$CID" --field workspace.working_dir)
  control-agent-server conversation events "$CID" --kinds ObservationEvent --contains qa-f14-agent.txt --expect-kind ObservationEvent
  test -d "$WS/.git"
  CID2=$(control-agent-server conversation start --tools file_editor --no-autotitle --print-id)
  WS2=$(control-agent-server api GET "/api/conversations/$CID2" --field workspace.working_dir)
  ```

- **需要会话密钥 (`F14.auth`)。**呼叫每条没有钥匙的路线（钥匙错误的路线）。
  ```sh
  control-agent-server api GET /api/file/home --auth none --expect 401
  control-agent-server api GET /api/file/search_subdirs --auth none --query path="$F" --expect 401
  control-agent-server api POST /api/file/upload --auth none --query path="$F/noauth/x.bin" --file file="$F/blob.bin" --expect 401
  control-agent-server api GET /api/file/download --auth bad --query path="$F/blob.bin" --expect 401
  control-agent-server api POST /api/file/create_directory --auth none --query path="$F/noauth-dir" --expect 401
  control-agent-server api GET /api/file/archive --auth none --query path="$REPO" --expect 401
  control-agent-server api GET "/api/file/download-trajectory/$CID" --auth none --expect 401
  control-agent-server api POST "/api/conversations/$CID/file/upload" --auth none --query path="$WS/noauth.bin" --file file="$F/blob.bin" --expect 401
  control-agent-server api GET "/api/conversations/$CID/file/download" --auth none --query path="$WS/qa-f14-agent.txt" --expect 401
  control-agent-server api POST "/api/conversations/$CID/file/create_directory" --auth none --query path="$WS/noauth-dir" --expect 401
  control-agent-server api GET "/api/conversations/$CID/file/archive" --auth none --query path="$WS" --expect 401
  control-agent-server api GET "/api/conversations/$CID/file/download-trajectory/$CID" --auth none --expect 401 \
    --check detail eq Unauthorized --save F14.auth/scoped-trajectory
  test ! -e "$F/noauth"
  test ! -e "$F/noauth-dir"
  test ! -e "$WS/noauth.bin"
  test ! -e "$WS/noauth-dir"
  ```
  所有十二个答案都为`401 {"detail": "Unauthorized"}`，没有文件或目录出现。
- **上传和下载往返 (`F14.upload-download`)。**上传三个目录深的二进制 blob，下载它，然后覆盖它。
  ```sh
  control-agent-server api POST /api/file/upload --query path="$F/xfer/a/b/blob.bin" --file file="$F/blob.bin" \
    --expect 200 --check success eq true --save F14.upload-download/upload
  test -d "$F/xfer/a/b"
  control-agent-server api GET /api/file/download --query path="$F/xfer/a/b/blob.bin" --expect 200 \
    --check-header content-disposition eq 'attachment; filename="blob.bin"' \
    --check-header content-type eq application/octet-stream \
    --raw-out "$F/blob.out" --save F14.upload-download/download
  cmp "$F/blob.bin" "$F/blob.out"
  control-agent-server api POST /api/file/upload --query path="$F/xfer/a/b/blob.bin" --file file="$F/v2.txt" --expect 200
  control-agent-server api GET /api/file/download --query path="$F/xfer/a/b/blob.bin" --expect 200 \
    --raw-out "$F/v2.out" --save F14.upload-download/overwritten
  cmp "$F/v2.txt" "$F/v2.out"
  ```
  上传答案 `{"success": true}`（没有大小字段），父节点存在，下载的字节数等于70 kB的blob，响应是一个名为的附件
  `blob.bin`，第二次上传后，相同的路径保存文本文件。
- **上传验证（`F14.upload-errors`）。**缺少部分和相对路径。
  ```sh
  control-agent-server api POST /api/file/upload --query path="$F/xfer/no-part.txt" --expect 422 --check detail.0.loc contains file
  control-agent-server api POST /api/file/upload --file file="$F/blob.bin" --expect 422 --check detail.0.loc contains path
  control-agent-server api POST /api/file/upload --query path="$F/xfer/wrong-field.txt" --file upload="$F/blob.bin" --expect 422
  control-agent-server api POST /api/file/upload --query path=qa-f14-relative.txt --file file="$F/blob.bin" \
    --expect 400 --check detail eq 'Path must be absolute' --save F14.upload-errors/relative
  test ! -e "$F/xfer/no-part.txt"
  test ! -e "$F/xfer/wrong-field.txt"
  ```
  缺少 `file` 部分（或另一个字段名称下的缺失部分）
  `path` 为 422，缺少位置； 相对路径为 400。
- **上传到目录(`F14.upload-onto-directory`)。**调用者的路径是错误的，`create_directory` 对于相同的冲突报告为 400。
  ```sh
  mkdir -p "$F/xfer/is-a-dir"
  control-agent-server api POST /api/file/create_directory --query path="$F/v2.txt/child" --expect 400 \
    --check detail eq 'Path exists and is not a directory'
  control-agent-server api POST /api/file/upload --query path="$F/xfer/is-a-dir" --file file="$F/v2.txt" \
    --expect 400 --check detail eq 'Path is a directory' --save F14.upload-onto-directory/upload
  control-agent-server api POST /api/file/upload --query path="$F/v2.txt/child" --file file="$F/v2.txt" \
    --expect 400 --check detail eq 'A parent of the path is not a directory' --save F14.upload-onto-directory/parent-is-file
  test -d "$F/xfer/is-a-dir"
  ```
  上传到现有目录返回400 `Path is a directory`，而路径的父目录是一个文件 `$F/v2.txt/child` 时返回400 `A parent of the path is not a directory`。 它既不触及已经存在的东西。
- ** 消费者结果中的上传大小 (`F14.upload-size`)。** 同样的 70 kB 块通过 `LocalWorkspace.file_upload` (远程工作区镜像的合约)，SDK's `RemoteWorkspace.file_upload` 和 TypeScript 客户的 `RemoteWorkspace.fileUpload`。 每个程序逐字节检查上传的登陆并写入它得到的`file_size`。
  ```sh
  cat > "$F/sdk_size.py" <<'PY'
  import os
  import sys
  from pathlib import Path

  from openhands.sdk.workspace import LocalWorkspace
  from openhands.sdk.workspace.remote.base import RemoteWorkspace

  fixtures = Path(sys.argv[1])
  blob = (fixtures / "blob.bin").read_bytes()
  local = LocalWorkspace(working_dir=str(fixtures))
  done = local.file_upload(fixtures / "blob.bin", fixtures / "size" / "local.bin")
  assert done.success and done.file_size == len(blob), done
  remote = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=str(fixtures),
  )
  target = fixtures / "size" / "sdk.bin"
  up = remote.file_upload(fixtures / "blob.bin", target)
  assert up.success and up.error is None and target.read_bytes() == blob, up
  (fixtures / "sdk-size.txt").write_text(str(up.file_size))
  print("SDK_UPLOAD_OK")
  PY
  cat > "$F/ts_size.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { readFileSync, writeFileSync } from 'node:fs';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { RemoteWorkspace } = await import(pathToFileURL(resolve('clients/typescript/dist/index.js')).href);
  const [fixtures] = process.argv.slice(2);
  const blob = readFileSync(`${fixtures}/blob.bin`);
  const ws = new RemoteWorkspace({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY, workingDir: fixtures });
  const up = await ws.fileUpload(new Blob([blob]), `${fixtures}/size/ts.bin`, 'ts.bin');
  assert.equal(up.success, true);
  assert.ok(readFileSync(`${fixtures}/size/ts.bin`).equals(blob));
  writeFileSync(`${fixtures}/ts-size.txt`, String(up.file_size));
  console.log('TS_UPLOAD_OK');
  JS
  control-agent-server exec --expect-output SDK_UPLOAD_OK --save F14.upload-size/sdk -- .venv/bin/python "$F/sdk_size.py" "$F"
  control-agent-server exec --expect-output TS_UPLOAD_OK --save F14.upload-size/ts -- node "$F/ts_size.mjs" "$F"
  control-agent-server api POST /api/file/upload --query path="$F/size/rest.bin" --file file="$F/blob.bin" --expect 200 \
    --check success eq true --check file_size eq 70000 --save F14.upload-size/rest
  control-agent-server assert --value "$(cat "$F/sdk-size.txt")" --check . eq 70000
  control-agent-server assert --value "$(cat "$F/ts-size.txt")" --check . eq 70000
  ```
  预期：每次上传都完好无损，服务器应答
  `{"success": true, "file_size": 70000}`（它写入的字节），并且两个远程工作区都将 `file_size` 复制到其结果中，如下所示
  `LocalWorkspace` 报告它（TypeScript `write_file` 工具然后说
  `Successfully wrote 70000 bytes`).
- **覆盖失败 (`F14.upload-atomic`)，已知错误。**第二台服务器（被陷阱停止）的文件大小限制降低到 500 kB
  `prlimit`，整个磁盘或配额在中途写入失败，而 900 kB 上传会覆盖小文件。 在最终检查之前解除限制。
  ```sh
  B2=$(control-agent-server launch --new --name f14-atomic --print-run)
  trap 'control-agent-server stop --run "$B2" > /dev/null' EXIT
  AT="$B2/fixtures/qa-f14-atomic"
  mkdir -p "$AT"
  head -c 900000 /dev/urandom > "$AT/big.bin"
  control-agent-server api POST /api/file/upload --run "$B2" --query path="$AT/big-copy.bin" --file file="$AT/big.bin" --expect 200
  cmp "$AT/big.bin" "$AT/big-copy.bin"
  control-agent-server api POST /api/file/upload --run "$B2" --query path="$AT/target.txt" --file file="$F/v2.txt" --expect 200
  cmp "$F/v2.txt" "$AT/target.txt"
  B2_PID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$B2/run.json")
  prlimit --pid "$B2_PID" --fsize=500000:
  control-agent-server api POST /api/file/upload --run "$B2" --query path="$AT/target.txt" --file file="$AT/big.bin" \
    --expect 5xx --check exception contains 'File too large' --save F14.upload-atomic/failed-overwrite
  prlimit --pid "$B2_PID" --fsize=unlimited:
  control-agent-server doctor --run "$B2"
  control-agent-server assert --value "{\"same\": $(cmp -s "$F/v2.txt" "$AT/target.txt" && echo true || echo false), \"size\": $(wc -c < "$AT/target.txt")}" --check same eq true  # 错误：value.same eq False && value.size eq 500000
  ```
  没有限制的情况下，900 kB大小的文件可以完整上传（因此，大小本身不是问题），小文件也已到位。 在限值内，覆盖操作会失败，`500 ... [Errno 27] File too large`，而限值解除后服务器是健康的。 预期：失败的上传会留下 `target.txt` 持有之前的较小文件（写入临时文件，然后重命名）。
  实际：`_upload_file`在流式传输之前用`"wb"`打开目标，所以
  `target.txt` 现在保存 blob 的前 500000 个字节：旧内容消失了，留下了部分文件。
- **下载错误 (`F14.download-errors`)。**缺少文件、目录、相对路径、无路径。
  ```sh
  control-agent-server api GET /api/file/download --query path="$F/xfer/missing.bin" --expect 404 \
    --check detail eq 'File not found' --save F14.download-errors/missing
  control-agent-server api GET /api/file/download --query path="$F/xfer" --expect 400 --check detail eq 'Path is not a file'
  control-agent-server api GET /api/file/download --query path=xfer/a/b/blob.bin --expect 400 --check detail eq 'Path must be absolute'
  control-agent-server api GET /api/file/download --expect 422
  ```
  状态码为 404、400 和 422。
- **创建目录(`F14.mkdir`)。** `mkdir -p`、幂等、则碰撞
  with files.
  ```sh
  control-agent-server api POST /api/file/create_directory --query path="$F/tree/x/y/z" --expect 200 \
    --check success eq true --save F14.mkdir/create
  control-agent-server api POST /api/file/upload --query path="$F/tree/x/y/z/keep.txt" --file file="$F/v2.txt" --expect 200
  control-agent-server api POST /api/file/create_directory --query path="$F/tree/x/y/z" --expect 200 --check success eq true
  test -d "$F/tree/x/y/z"
  cmp "$F/v2.txt" "$F/tree/x/y/z/keep.txt"
  control-agent-server api GET /api/file/search_subdirs --query path="$F/tree/x/y" --expect 200 \
    --check items len-eq 1 --check items.0.name eq z --check items.0.path eq "$F/tree/x/y/z" --save F14.mkdir/listed
  control-agent-server api POST /api/file/create_directory --query path="$F/blob.bin" --expect 400 \
    --check detail eq 'Path exists and is not a directory'
  control-agent-server api POST /api/file/create_directory --query path="$F/blob.bin/sub" --expect 400 \
    --check detail eq 'Path exists and is not a directory'
  control-agent-server api POST /api/file/create_directory --query path=qa-f14/relative --expect 400 --check detail eq 'Path must be absolute'
  ```
  两个都创建了答案 `{"success": true}`，文件内部存活第二个，`search_subdirs` 列出了 `z` 的绝对路径，而一个在路途上（目标或父文件）是 400。
- **主页和收藏夹 (`F14.home`)。**启动器为服务器提供了一个私有的
  `HOME` 仅包含隐藏条目，因此收藏夹正是该项目符号创建的内容。
  ```sh
  H="$AGENT_SERVER_VERIFY_RUN/home"
  mkdir -p "$H/qa-f14-Beta" "$H/qa-f14-alpha" "$H/.qa-f14-hidden"
  ln -s "$H/qa-f14-alpha" "$H/qa-f14-link"
  printf 'x\n' > "$H/qa-f14-file.txt"
  control-agent-server api GET /api/file/home --expect 200 --check home eq "$H" \
    --check favorites len-eq 2 --check favorites.0.label eq qa-f14-alpha --check favorites.1.label eq qa-f14-Beta \
    --check favorites.0.path eq "$H/qa-f14-alpha" --check locations len-eq 1 --check locations.0.path eq / \
    --save F14.home/default
  control-agent-server api GET /api/file/home --query include_hidden=true --expect 200 \
    --check favorites contains .qa-f14-hidden --check favorites not-contains qa-f14-link \
    --check favorites not-contains qa-f14-file.txt --save F14.home/include-hidden
  ```
  `home` 是跑步者的私人住宅； `favorites` 是 `qa-f14-alpha` 那么
  `qa-f14-Beta`（不区分大小写的顺序），不带符号链接和文件；
  `locations` 是 `[{"label": "/", "path": "/"}]`。 使用 `include_hidden=true` 添加隐藏目录（`.qa-f14-hidden`、`.config`、...）。
- **列出子目录 (`F14.subdirs`).**一棵大小写混合的树，一个隐藏目录，一个文件和一个符号链接。
  ```sh
  T="$F/subdirs"
  mkdir -p "$T/b" "$T/A" "$T/c" "$T/.hid"
  printf 'f\n' > "$T/f.txt"
  ln -s "$T/A" "$T/lnk"
  control-agent-server api GET /api/file/search_subdirs --query path="$T" --expect 200 --check items len-eq 3 \
    --check items.0.name eq A --check items.1.name eq b --check items.2.name eq c \
    --check items.0.path eq "$T/A" --check next_page_id missing --save F14.subdirs/default
  control-agent-server api GET /api/file/search_subdirs --query path="$T" --query include_hidden=true --expect 200 \
    --check items len-eq 4 --check items.0.name eq .hid
  ```
  仅 `A`, `b`, `c`（不区分大小写，绝对路径，无文件名）
  `next_page_id`); `.hid` 与 `include_hidden=true` 一起首先出现。
- **分页 (`F14.subdirs-pagination`).**每页两个。

  需要：`F14.subdirs`
  ```sh
  NEXT=$(control-agent-server api GET /api/file/search_subdirs --query path="$T" --query limit=2 --expect 200 \
    --check items len-eq 2 --check items.1.name eq b --field next_page_id)
  test "$NEXT" = c
  control-agent-server api GET /api/file/search_subdirs --query path="$T" --query limit=2 --query page_id="$NEXT" \
    --expect 200 --check items len-eq 1 --check items.0.name eq c --check next_page_id missing \
    --save F14.subdirs-pagination/last-page
  control-agent-server api GET /api/file/search_subdirs --query path="$T" --query limit=0 --expect 422
  control-agent-server api GET /api/file/search_subdirs --query path="$T" --query limit=101 --expect 422
  ```
  第一页是 `A`、`b`，`next_page_id` `c`（下一个条目的小写字母名称）； 第二页是`c`，没有光标。 `limit` 0和101是422。
- **列出错误 (`F14.subdirs-errors`)。**缺少文件、相对路径、无路径。

  需要：`F14.subdirs`
  ```sh
  control-agent-server api GET /api/file/search_subdirs --query path="$T/missing" --expect 404 \
    --check detail eq 'Directory not found' --save F14.subdirs-errors/missing
  control-agent-server api GET /api/file/search_subdirs --query path="$T/f.txt" --expect 400 --check detail eq 'Path is not a directory'
  control-agent-server api GET /api/file/search_subdirs --query path=qa-f14 --expect 400 --check detail eq 'Path must be absolute'
  control-agent-server api GET /api/file/search_subdirs --expect 422
  ```
  状态码为 404、400 和 422。
- **分页经过仅案例双胞胎 (`F14.subdirs-case-pagination`)。**
  `Foo` 和 `foo` 每页一个条目。 领带按确切名称排序，所以
  `Foo` 排在第一位； 食谱仍然显示第一页，并期望第二页上有另一个双胞胎。
  ```sh
  CASE_DIR="$F/case"
  mkdir -p "$CASE_DIR/Foo" "$CASE_DIR/foo"
  CASE_FIRST=$(control-agent-server api GET /api/file/search_subdirs --query path="$CASE_DIR" --query limit=1 \
    --expect 200 --check items len-eq 1 --field items.0.name)
  CASE_NEXT=$(control-agent-server api GET /api/file/search_subdirs --query path="$CASE_DIR" --query limit=1 \
    --expect 200 --check next_page_id exists --field next_page_id)
  if test "$CASE_FIRST" = Foo; then CASE_OTHER=foo; else CASE_OTHER=Foo; fi
  test "$CASE_FIRST" = Foo -o "$CASE_FIRST" = foo
  control-agent-server api GET /api/file/search_subdirs --query path="$CASE_DIR" --query limit=1 --query page_id="$CASE_NEXT" \
    --expect 200 --check items len-eq 1 --check items.0.name eq "$CASE_OTHER" --check next_page_id missing \
    --save F14.subdirs-case-pagination/page-2
  ```
  页面一只有一个双胞胎和一个光标。 第二页恰好包含另一个双胞胎，没有光标：不区分大小写的精确名称匹配会打破双胞胎，光标是下一个条目的精确名称，因此它能区分双胞胎。
- **tar.gz 存档 (`F14.archive-tar`).**归档测试夹具存储库，然后是一个符号链接指向其内部和外部的普通树。

  需要：`F14.subdirs`
  ```sh
  control-agent-server api GET /api/file/archive --query path="$REPO" --query format=tar.gz --expect 200 \
    --check-header content-disposition eq 'attachment; filename="qa-f14-repo.tar.gz"' \
    --check-header content-type eq application/gzip \
    --check-header x-archive-head-commit eq "$(git -C "$REPO" rev-parse HEAD)" --check-header x-archive-branch eq main \
    --check-header x-archive-base-commit missing --raw-out "$F/repo.tgz" --save F14.archive-tar/repo
  tar tzf "$F/repo.tgz" > "$F/repo.list"
  grep -qx 'qa-f14-repo/README.md' "$F/repo.list"
  grep -qx 'qa-f14-repo/notes.txt' "$F/repo.list"
  grep -qx 'qa-f14-repo/src/util.py' "$F/repo.list"
  grep -qx 'qa-f14-repo/archive_manifest.json' "$F/repo.list"
  test -z "$(grep -E '/\.git/|node_modules' "$F/repo.list")"
  tar xzOf "$F/repo.tgz" qa-f14-repo/archive_manifest.json | python3 -c 'import json,sys; m=json.load(sys.stdin); assert m["format"] == "tar.gz" and m["source"] == "qa-f14-repo" and m["file_count"] == 5 and "node_modules/" in m["excludes"], m'
  ln -s /etc "$T/qa-f14-etc-link"
  control-agent-server api GET /api/file/archive --query path="$T" --query format=tar.gz --expect 200 --raw-out "$F/tree.tgz"
  tar tzf "$F/tree.tgz" > "$F/tree.list"
  grep -qx 'subdirs/f.txt' "$F/tree.list"
  grep -qx 'subdirs/A/' "$F/tree.list"
  test -z "$(grep -E 'lnk|etc-link' "$F/tree.list")"
  for i in 1 2 3 4 5; do test -z "$(find "$AGENT_SERVER_VERIFY_RUN/fixtures" "$F" -maxdepth 1 -name 'tmp*')" && break; sleep 0.2; done
  test -z "$(find "$AGENT_SERVER_VERIFY_RUN/fixtures" "$F" -maxdepth 1 -name 'tmp*')"
  ```
  仓库归档文件`qa-f14-repo.tar.gz`包含五个工作目录文件（已跟踪、修改、未跟踪的和`qa.log`），以及`file_count` 5的manifest，但没有`.git/`和`node_modules/`。 它携带了仓库标识 (`X-Archive-Head-Commit`, `X-Archive-Branch`)，但没有
  `X-Archive-Base-*`，仅描述一个补丁。 树存档包含 `f.txt` 和真实目录（也是空目录），但没有符号链接。 服务器在父目录中构建的临时存档已消失（短轮询等待服务器自己的响应后清理）。
- **排除控件 (`F14.archive-excludes`)。**完全捕获，然后是一个额外的 glob。
  ```sh
  control-agent-server api GET /api/file/archive --query path="$REPO" --query format=tar.gz --query use_default_excludes=false \
    --expect 200 --raw-out "$F/full.tgz" --save F14.archive-excludes/full
  tar tzf "$F/full.tgz" > "$F/full.list"
  grep -qx 'qa-f14-repo/node_modules/pkg/j.js' "$F/full.list"
  grep -qx 'qa-f14-repo/.git/HEAD' "$F/full.list"
  test -f "$REPO/.git/config"
  test -d "$REPO/.git/logs"
  test -z "$(grep -E '\.git/(config|logs/)' "$F/full.list")"
  control-agent-server api GET /api/file/archive --query path="$REPO" --query format=tar.gz --query 'exclude=*.log' \
    --expect 200 --raw-out "$F/nolog.tgz" --save F14.archive-excludes/exclude-log
  tar tzf "$F/nolog.tgz" > "$F/nolog.list"
  grep -qx 'qa-f14-repo/notes.txt' "$F/nolog.list"
  test -z "$(grep 'qa.log' "$F/nolog.list")"
  tar xzOf "$F/nolog.tgz" qa-f14-repo/archive_manifest.json | python3 -c 'import json,sys; m=json.load(sys.stdin); assert m["excludes"][-1] == "*.log" and ".git/" in m["excludes"], m'
  control-agent-server api GET /api/file/archive --query path="$REPO" --query format=tar.gz --query 'exclude=*.log' \
    --query exclude=notes.txt --expect 200 --raw-out "$F/two-ex.tgz" --save F14.archive-excludes/exclude-two
  tar tzf "$F/two-ex.tgz" > "$F/two-ex.list"
  grep -qx 'qa-f14-repo/README.md' "$F/two-ex.list"
  test -z "$(grep -E 'qa\.log|notes\.txt' "$F/two-ex.list")"
  ```
  完整的捕获 `node_modules/pkg/j.js` 和 `.git/HEAD`，但没有
  `.git/config` 和无 `.git/logs/`，尽管两者都存在于磁盘上； `exclude=*.log` 删除 `qa.log`，保留默认值，清单最后列出 `*.log`。
  `exclude` 是可重复的：`*.log` 和 `notes.txt` 两个文件都消失了。
- **git-delta 补丁 (`F14.archive-git-delta`).**默认格式反对
  `HEAD`，然后对着自动基地。
  ```sh
  HEAD_SHA=$(git -C "$REPO" rev-parse HEAD)
  control-agent-server api GET /api/file/archive --query path="$REPO" --query base_ref=HEAD --expect 200 \
    --check-header content-disposition eq 'attachment; filename="qa-f14-repo.patch"' \
    --check-header content-type matches '^text/x-patch' \
    --check-header x-archive-base-commit eq "$HEAD_SHA" --check-header x-archive-base-ref eq HEAD \
    --check-header x-archive-branch eq main --check-header x-archive-head-commit eq "$HEAD_SHA" \
    --check-header x-archive-repo-root eq "$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$REPO")" \
    --check-header x-archive-repo-remote missing --raw-out "$F/head.patch" --save F14.archive-git-delta/base-head
  grep -q '^diff --git a/README.md b/README.md' "$F/head.patch"
  grep -q '^diff --git a/notes.txt b/notes.txt' "$F/head.patch"
  grep -q '^diff --git a/qa.log b/qa.log' "$F/head.patch"
  test -z "$(grep -E '^diff --git a/(src/|node_modules/)' "$F/head.patch")"
  git clone -q "$REPO" "$F/clone"
  git -C "$F/clone" apply --check "$F/head.patch"
  git -C "$REPO" diff --cached --quiet
  control-agent-server api GET /api/file/archive --query path="$REPO" --expect 200 \
    --check-header x-archive-branch eq main --check-header x-archive-base-commit missing \
    --check-header x-archive-base-ref missing --raw-out "$F/auto.patch" --save F14.archive-git-delta/auto
  grep -q '^diff --git a/src/app.py b/src/app.py' "$F/auto.patch"
  control-agent-server api GET /api/file/archive --query path="$REPO/src" --query base_ref=HEAD~1 --expect 200 \
    --check-header content-disposition eq 'attachment; filename="src.patch"' \
    --check-header x-archive-base-commit eq "$(git -C "$REPO" rev-parse HEAD~1)" \
    --raw-out "$F/src.patch" --save F14.archive-git-delta/subdir
  test "$(grep -c '^diff --git' "$F/src.patch")" = 1
  grep -q '^diff --git a/src/util.py b/src/util.py' "$F/src.patch"
  ```
  与 `base_ref=HEAD` patch (`qa-f14-repo.patch`, `text/x-patch`) 持有修改后的 `README.md` and the untracked `notes.txt` 和 `qa.log`不是已承诺的 `src/` 文件或 `node_modules`; 它适用于新克隆的仓库，而测试夹具'索引之后没有要提交的更改。' headers命名基础和头部提交 `HEAD` 和 `main`, and `X-Archive-Repo-Root` 是百分号编码的仓库路径。 的测试夹具没有远程，所以没有
  `X-Archive-Repo-Remote`. 如果没有 `base_ref`，基数就是空的
  树：每个文件都显示为新文件，并且没有 `X-Archive-Base-*` 标头
  （带有遥控器的克隆是`F14.archive-auto-base`）。 `src` 仓库的一个子目录，`HEAD~1` 与之相对，`src.patch` 仅包含该子目录的更改，`src/util.py` 路径仍然相对于仓库根目录
  `README.md`、`notes.txt` 和 `qa.log` 在其旁边发生变化。
- **带遥控器的自动底座 (`F14.archive-auto-base`)。**生产
  路径：在删除运行时之前归档克隆存储库。 克隆人
  测试夹具的（其 `origin` 是测试夹具路径）获得一个本地提交和一个未提交的编辑，然后是具有分离的 HEAD 的相同克隆。
  ```sh
  AB="$F/auto-clone"
  git clone -q "$REPO" "$AB"
  ORIGIN_TIP=$(git -C "$AB" rev-parse origin/main)
  printf 'local\n' > "$AB/local.txt"
  git -C "$AB" add local.txt
  git -C "$AB" -c user.name=qa-f14 -c user.email=qa-f14@example.invalid commit -qm 'qa-f14 local commit'
  printf 'edit\n' >> "$AB/README.md"
  LOCAL_HEAD=$(git -C "$AB" rev-parse HEAD)
  test "$LOCAL_HEAD" != "$ORIGIN_TIP"
  control-agent-server api GET /api/file/archive --query path="$AB" --expect 200 \
    --check-header x-archive-base-ref eq auto --check-header x-archive-base-commit eq "$ORIGIN_TIP" \
    --check-header x-archive-head-commit eq "$LOCAL_HEAD" --check-header x-archive-branch eq main \
    --check-header x-archive-repo-remote eq "$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$REPO")" \
    --raw-out "$F/auto-clone.patch" --save F14.archive-auto-base/origin
  grep -q '^diff --git a/local.txt b/local.txt' "$F/auto-clone.patch"
  grep -q '^diff --git a/README.md b/README.md' "$F/auto-clone.patch"
  test -z "$(grep -E '^diff --git a/src/' "$F/auto-clone.patch")"
  git clone -q "$REPO" "$F/auto-replay"
  test "$(git -C "$F/auto-replay" rev-parse HEAD)" = "$ORIGIN_TIP"
  git -C "$F/auto-replay" apply --check "$F/auto-clone.patch"
  git -C "$AB" checkout -q --detach
  control-agent-server api GET /api/file/archive --query path="$AB" --expect 200 \
    --check-header x-archive-base-ref eq auto --check-header x-archive-base-commit eq "$LOCAL_HEAD" \
    --check-header x-archive-branch eq DETACHED --raw-out "$F/detached.patch" --save F14.archive-auto-base/detached
  test "$(grep -c '^diff --git' "$F/detached.patch")" = 1
  grep -q '^diff --git a/README.md b/README.md' "$F/detached.patch"
  ```
  在分支中，缺失的部分 `base_ref` 解析为 `origin/main`: 该补丁包含了已提交但未推送的 `local.txt` 和 `README.md` 编辑，但 None of the `src/` 双方都共享的文件，以及适用于从源头获取的最新克隆。 headers says `X-Archive-Base-Ref: auto`, 起始点 `X-Archive-Base-Commit`, 当前本地提交为 `X-Archive-Head-Commit`百分编码的起源 URL as `X-Archive-Repo-Remote`. 与 HEAD 在本地提交上脱离的，基线是 HEAD 它（不是起源点）：
  `X-Archive-Base-Commit` 是本地提交，`X-Archive-Branch` 是
  `DETACHED`、`X-Archive-Base-Ref` 仍然是 `auto`，并且补丁仅包含未提交的 `README.md` 编辑。
- **嵌套存储库 (`F14.archive-nested-repo`).**一个非仓库父级，其中一份仓库副本向下两层，然后是第二个副本。
  ```sh
  P="$F/parent"
  mkdir -p "$P/group"
  cp -r "$REPO" "$P/group/proj"
  printf 'top\n' > "$P/top.txt"
  control-agent-server api GET /api/file/archive --query path="$P" --query base_ref=HEAD --expect 200 \
    --check-header content-disposition eq 'attachment; filename="proj.patch"' \
    --raw-out "$F/parent.patch" --save F14.archive-nested-repo/one-repo
  grep -q '^diff --git a/notes.txt b/notes.txt' "$F/parent.patch"
  control-agent-server api GET /api/file/archive --query path="$P" --query format=tar.gz --expect 200 --raw-out "$F/parent.tgz"
  tar tzf "$F/parent.tgz" > "$F/parent.list"
  grep -qx 'proj/notes.txt' "$F/parent.list"
  test -z "$(grep 'top.txt' "$F/parent.list")"
  cp -r "$REPO" "$P/proj2"
  control-agent-server api GET /api/file/archive --query path="$P" --query base_ref=HEAD --expect 400 \
    --check detail contains 'Not a git repository' --save F14.archive-nested-repo/two-repos
  control-agent-server api GET /api/file/archive --query path="$P" --query format=tar.gz --expect 200 --raw-out "$F/parent2.tgz"
  tar tzf "$F/parent2.tgz" > "$F/parent2.list"
  grep -qx 'parent/top.txt' "$F/parent2.list"
  grep -qx 'parent/proj2/notes.txt' "$F/parent2.list"
  ```
  在它下面有一个仓库，两种格式都支持 `group/proj` (named)
  `proj.patch` / `proj.tar.gz`，植根于 `proj/`) 和父级自己的
  `top.txt` 不在 tar 中。 有了两个，服务器就拒绝猜测：
  `git-delta` 是 400，`tar.gz` 归档给定的父级。
- **What `format` promises (`F14.archive-format-doc`).** 的 OpenAPI 端点描述 `format` 参数，与相反 `tar.gz` 一个非仓库目录，包含一个仓库和一个自己的文件。
  ```sh
  control-agent-server api GET /openapi.json --expect 200 --quiet --raw-out "$F/openapi.json"
  DOC_FORMAT=$(python3 -c 'import json,sys; ps=json.load(open(sys.argv[1]))["paths"]["/api/file/archive"]["get"]["parameters"]; print(next(p["description"] for p in ps if p["name"] == "format"))' "$F/openapi.json")
  test -n "$DOC_FORMAT"
  DOCP="$F/doc-parent"
  mkdir -p "$DOCP"
  cp -r "$REPO" "$DOCP/proj"
  printf 'top\n' > "$DOCP/top.txt"
  control-agent-server api GET /api/file/archive --query path="$DOCP" --query format=tar.gz --expect 200 \
    --raw-out "$F/doc-parent.tgz" --save F14.archive-format-doc/tar
  tar tzf "$F/doc-parent.tgz" > "$F/doc-parent.list"
  grep -q 'proj/notes.txt$' "$F/doc-parent.list"
  jq -n --arg doc "$DOC_FORMAT" --rawfile list "$F/doc-parent.list" '{doc_entire_directory: ($doc | contains("entire directory")), tar_has_top: ($list | contains("top.txt"))} | .agree = (.tar_has_top or (.doc_entire_directory | not))' \
    | control-agent-server assert --check agree eq true
  ```
  描述和归档一致：tar只包含`proj/`，而不是
  `top.txt`，且`format`（`path`）描述说，一个恰好包含一个git仓库（最多向下三层）的非仓库路径会被作为该仓库进行归档，因此，除了它之外的文件不会被包括，而是承诺“整个目录”。 对嵌套存储库的解析是经过深思熟虑的（参见`archive_directory`）。
- **存档验证 (`F14.archive-errors`).**

  需要：`F14.subdirs`
  ```sh
  control-agent-server api GET /api/file/archive --query path=qa-f14/relative --expect 400 --check detail eq 'Path must be absolute'
  control-agent-server api GET /api/file/archive --query path="$F/missing-dir" --expect 404 \
    --check detail eq 'Directory not found' --save F14.archive-errors/missing
  control-agent-server api GET /api/file/archive --query path="$REPO/README.md" --expect 400 --check detail eq 'Path is not a directory'
  control-agent-server api GET /api/file/archive --query path="$REPO" --query base_ref=--output=/tmp/qa-f14-injected \
    --expect 400 --check detail eq "base_ref must not start with '-'"
  test ! -e /tmp/qa-f14-injected
  control-agent-server api GET /api/file/archive --query path="$REPO" --query base_ref=qa-f14-no-such-ref --expect 400 \
    --check detail contains 'could not be resolved'
  control-agent-server api GET /api/file/archive --query path="$REPO" --query format=zip --expect 422
  control-agent-server api GET /api/file/archive --query path="$T" --expect 400 --check detail contains 'Not a git repository'
  control-agent-server api GET /api/file/archive --expect 422
  ```
  400, 404, 400, 400 (an option-shaped) `base_ref` 永远无法到达 git)，400，422`format` 是 `git-delta` 或 `tar.gz`, 400和422。
- **轨迹拉链 (`F14.trajectory`).**下载模型对话的轨迹并将其与事件计数和磁盘上的文件进行比较。
  ```sh
  HEX=$(printf '%s' "$CID" | tr -d -)
  NEV=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server api GET "/api/file/download-trajectory/$CID" --expect 200 \
    --check-header content-disposition eq "attachment; filename=\"$HEX.zip\"" --raw-out "$F/traj.zip" --save F14.trajectory/zip
  python3 -c 'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); h=sys.argv[2]; n=z.namelist(); assert h+"/meta.json" in n and h+"/base_state.json" in n, n; ev=[m for m in n if m.startswith(h+"/events/event-")]; assert len(ev) == int(sys.argv[3]), (len(ev), sys.argv[3]); s=json.loads(z.read(h+"/base_state.json")); assert s["agent"]["llm"]["api_key"] == "**********", "api_key not redacted"; assert not any(b"gAAAAA" in z.read(m) for m in n), "Fernet ciphertext in the zip"' "$F/traj.zip" "$HEX" "$NEV"
  grep -q '"api_key": *"gAAAAA' "$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations/$HEX/base_state.json"
  control-agent-server api GET "/api/file/download-trajectory/$HEX" --expect 200 --raw-out "$F/traj-hex.zip"
  python3 -m zipfile -t "$F/traj-hex.zip" > /dev/null
  for i in 1 2 3 4 5; do test -z "$(find "$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations" -maxdepth 1 -name '*.zip')" && break; sleep 0.2; done
  test -z "$(find "$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations" -maxdepth 1 -name '*.zip')"
  ```
  `<hex>.zip`个压缩包，`<hex>/meta.json`个，`<hex>/base_state.json`个，还有每个事件一个`events/event-*.json`（数量与`events/count`相符）。 在磁盘上，LLM键是fernet密文(`gAAAAA...`)。 在拉链里
  `**********` 并且任何地方都没有留下密文。 十六进制形式的 id 也可以使用，并且对话目录下的临时 zip 会被删除。
- **轨迹误差 (`F14.trajectory-errors`)。**
  ```sh
  control-agent-server api GET /api/file/download-trajectory/00000000-0000-4000-8000-00000000f14a --expect 404 \
    --check detail eq 'Conversation not found' --save F14.trajectory-errors/unknown
  control-agent-server api GET /api/file/download-trajectory/qa-f14-not-a-uuid --expect 422
  ```
  404 未知 ID，422 错误的 ID。
- ** 并发轨迹下载 (`F14.trajectory-concurrent`)，已知 bug。** 实际上，最多可以进行五轮六平行下载（两个浏览器标签或一个重试就足够了）。 在第一轮下载失败后，爆发就会停止，因此该错误几乎肯定会重现，并且需要 30 次干净的并发下载。
  ```sh
  CC="$F/concurrent"
  mkdir -p "$CC"
  control-agent-server api GET "/api/file/download-trajectory/$CID" --expect 200 --raw-out "$CC/single.zip"
  python3 -m zipfile -t "$CC/single.zip" > /dev/null
  cat > "$CC/burst.sh" <<'SH'
  for r in 1 2 3 4 5; do
    for i in 1 2 3 4 5 6; do
      curl -sS -o "$CC/$r-$i.zip" -w '%{http_code}' -H "X-Session-API-Key: $SESSION_API_KEY" \
        "$AGENT_SERVER_URL/api/file/download-trajectory/$CID" > "$CC/$r-$i.status" 2> "$CC/$r-$i.err" &
    done
    wait
    for i in 1 2 3 4 5 6; do
      if [ "$(cat "$CC/$r-$i.status")" != 200 ] || ! python3 -m zipfile -t "$CC/$r-$i.zip" > /dev/null 2>&1; then
        echo "round $r: download $i is broken"; exit 0
      fi
    done
    echo "round $r: six valid zips"
  done
  SH
  control-agent-server exec --env CID="$CID" --env CC="$CC" --save F14.trajectory-concurrent/burst -- sh "$CC/burst.sh"
  test -s "$CC/1-6.status"
  BROKEN=$(for s in "$CC"/[1-5]-[1-6].status; do n=$(basename "$s" .status); z="${s%.status}.zip"; c=$(cat "$s"); if [ "$c" != 200 ]; then echo "$n:$c"; elif ! test -s "$z"; then echo "$n:200-empty"; elif ! python3 -m zipfile -t "$z" > /dev/null 2>&1; then echo "$n:200-badzip"; fi; done)
  control-agent-server assert --value="$BROKEN" --check . eq ''  # bug: value matches ':(500|200-empty|200-badzip)'
  ```
  单个下载是有效的 zip。 预期：每并发次下载都应为 200 状态码，并且是有效的 zip 文件，在所有五轮中。 实际上，每个处理器都会写同一个临时文件 `<conversations_path>/<hex>.zip`，并在发送后删除它，因此一些请求会收到 500 `File at path ... does not exist`（或删除的 `FileNotFoundError`），一些响应会被截断，有时甚至没有内容，因此 curl 会写入一个文件 `curl: (18) transfer closed with ... bytes remaining`，在日志中也会出现 `Response content longer than Content-Length`。 通常第一轮就已经出现下载失败。 `<round>-<n>.err` 持有 curl 的错误。
- **会话范围的传输 (`F14.scoped-transfer`)。**读取智能体编写的文件，然后上传、下载并在工作区中创建一个目录。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS/qa-f14-agent.txt" --expect 200 \
    --raw-out "$F/agent.txt" --save F14.scoped-transfer/agent-file
  grep -qx hi "$F/agent.txt"
  control-agent-server api POST "/api/conversations/$CID/file/upload" --query path="$WS/qa-f14-up/blob.bin" --file file="$F/blob.bin" \
    --expect 200 --check success eq true --save F14.scoped-transfer/upload
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS/qa-f14-up/blob.bin" --expect 200 --raw-out "$F/scoped.bin"
  cmp "$F/blob.bin" "$F/scoped.bin"
  control-agent-server api GET /api/file/download --query path="$WS/qa-f14-up/blob.bin" --expect 200 --raw-out "$F/scoped-global.bin"
  cmp "$F/blob.bin" "$F/scoped-global.bin"
  control-agent-server api POST "/api/conversations/$CID/file/create_directory" --query path="$WS/qa-f14-dir/sub" --expect 200 --check success eq true
  test -d "$WS/qa-f14-dir/sub"
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS/qa-f14-missing.txt" --expect 404 --check detail eq 'File not found'
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS" --expect 400 --check detail eq 'Path is not a file'
  ```
  该端点返回智能体's `hi`。 scoped upload 落在了工作区（全局路由读取相同字节）。 的作用域
  `create_directory` 创建嵌套目录； 在工作区内，处理程序自己的 404 和 400 适用。
- **工作区路径守卫 (`F14.scoped-path-guard`).** Address `CID`'s 工作区 through `CID2`'s scope in every way that should escape.
  ```sh
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path="$WS/qa-f14-agent.txt" --expect 422 \
    --check detail eq 'path must be inside the conversation workspace' --save F14.scoped-path-guard/other-workspace
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path="$WS2/../$(basename "$WS")/qa-f14-agent.txt" --expect 422
  ln -s "$WS" "$WS2/qa-f14-escape"
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path="$WS2/qa-f14-escape/qa-f14-agent.txt" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path="${WS2}-sibling/x.txt" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path=qa-f14-agent.txt --expect 422
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS/qa-f14-up/../qa-f14-agent.txt" --expect 200
  control-agent-server api POST "/api/conversations/$CID2/file/upload" --query path="$WS/qa-f14-intruder.txt" --file file="$F/v2.txt" --expect 422
  control-agent-server api POST "/api/conversations/$CID2/file/create_directory" --query path="$WS/qa-f14-intruder-dir" --expect 422
  test ! -e "$WS/qa-f14-intruder.txt"
  test ! -e "$WS/qa-f14-intruder-dir"
  control-agent-server api GET /api/file/download --query path="$WS2/qa-f14-escape/qa-f14-agent.txt" --expect 200 \
    --save F14.scoped-path-guard/global-same-path
  ```
  另一个工作区，`..` 在内部的导航，一个符号链接 `WS2` 指向的那部分
  `WS`、共享`WS2`前缀的同级目录和相对路径都是
  `422 path must be inside the conversation workspace`（依赖项在处理程序之前运行，因此这里的相对路径是 422，而不是 400）； 被拒绝的上传和目录永远不会出现。 守卫解析路径而不是拒绝每个 `..`：`$WS/qa-f14-up/../qa-f14-agent.txt` 到 `CID` 自己的范围是 200。 全局路由与 200 提供相同的符号链接路径。
- **未知或格式错误的对话 (`F14.scoped-conversation-errors`)。**
  ```sh
  control-agent-server api GET /api/conversations/00000000-0000-4000-8000-00000000f14b/file/download --query path="$WS/qa-f14-agent.txt" \
    --expect 404 --check detail contains 'Conversation not found' --save F14.scoped-conversation-errors/unknown
  control-agent-server api POST /api/conversations/00000000-0000-4000-8000-00000000f14b/file/create_directory --query path="$F/unknown-scope" --expect 404
  test ! -e "$F/unknown-scope"
  control-agent-server api GET /api/conversations/qa-f14-not-a-uuid/file/download --query path="$WS/qa-f14-agent.txt" --expect 422
  control-agent-server api GET "/api/conversations/$CID/file/download" --expect 422
  ```
  一个未知的运行时对话是 404 并且创建了 nothing。 一个非法的 id 和一个缺失的 `path` 是 422。
- **范围轨迹和存档 (`F14.scoped-trajectory-archive`)。**
  ```sh
  control-agent-server api GET "/api/conversations/$CID/file/download-trajectory/$CID" --expect 200 \
    --raw-out "$F/scoped-traj.zip" --save F14.scoped-trajectory-archive/trajectory
  python3 -m zipfile -t "$F/scoped-traj.zip" > /dev/null
  control-agent-server api GET "/api/conversations/$CID/file/download-trajectory/$CID2" --expect 422 \
    --check detail eq 'Trajectory must belong to the selected conversation'
  control-agent-server api GET "/api/conversations/$CID/file/download-trajectory/qa-f14-not-a-uuid" --expect 422 \
    --check detail eq 'Invalid trajectory conversation id'
  control-agent-server api GET "/api/conversations/$CID/file/archive" --query path="$WS" --expect 200 \
    --raw-out "$F/ws.patch" --save F14.scoped-trajectory-archive/git-delta
  grep -q '^diff --git a/qa-f14-agent.txt b/qa-f14-agent.txt' "$F/ws.patch"
  control-agent-server api GET "/api/conversations/$CID/file/archive" --query path="$WS" --query format=tar.gz --expect 200 --raw-out "$F/ws.tgz"
  tar tzf "$F/ws.tgz" > "$F/ws.list"
  grep -qx "$(basename "$WS")/qa-f14-agent.txt" "$F/ws.list"
  grep -qx "$(basename "$WS")/qa-f14-up/blob.bin" "$F/ws.list"
  control-agent-server api GET "/api/conversations/$CID/file/archive" --query path="$REPO" --expect 422 \
    --check detail eq 'path must be inside the conversation workspace'
  control-agent-server api GET "/api/conversations/$CID2/file/archive" --query path="$WS" --query format=tar.gz --expect 422
  ```
  该对话的自身轨迹下载为有效的压缩包。 `CID2`通过 [id] `CID`其作用范围和非法的ID都是422。 服务器 `git init`在每一场对话中工作区没有提交，所以这个 scoped `git-delta` 与空树对立，并列出智能体's `qa-f14-agent.txt` 作为新文件。 的 `tar.gz` 它持有它和上传的blob。 归档测试夹具 repo 或者另一个工作区通过此范围是 422。
- **SDK工作区(`F14.sdk-workspace`).** `RemoteWorkspace.file_upload` 和
  `file_download`，首先在主机 (`/api/file/...`) 上，然后作用域为 `CID` (`runtime_conversation_id`, `/api/conversations/{id}/file/...`)。
  ```sh
  cat > "$F/sdk_files.py" <<'PY'
  import os
  import sys
  from pathlib import Path
  from uuid import UUID

  from openhands.sdk.workspace.remote.base import RemoteWorkspace

  fixtures, ws, cid = Path(sys.argv[1]), Path(sys.argv[2]), UUID(sys.argv[3])
  host, key = os.environ["AGENT_SERVER_URL"], os.environ["SESSION_API_KEY"]
  blob = (fixtures / "blob.bin").read_bytes()
  plain = RemoteWorkspace(host=host, api_key=key, working_dir=str(fixtures))
  scoped = RemoteWorkspace(host=host, api_key=key, working_dir=str(ws), runtime_conversation_id=cid)
  for name, w, remote in (
      ("plain", plain, fixtures / "sdk" / "blob.bin"),
      ("scoped", scoped, ws / "qa-f14-sdk" / "blob.bin"),
  ):
      up = w.file_upload(fixtures / "blob.bin", remote)
      assert up.success and up.error is None, (name, up)
      assert remote.read_bytes() == blob, name
      local = fixtures / f"sdk-{name}.out"
      down = w.file_download(remote, local)
      assert down.success and down.file_size == len(blob), (name, down)
      assert local.read_bytes() == blob, name
  refused = scoped.file_upload(fixtures / "v2.txt", fixtures / "sdk-outside.txt")
  assert not refused.success and "422" in (refused.error or ""), refused
  assert not (fixtures / "sdk-outside.txt").exists()
  print("SDK_FILES_OK")
  PY
  control-agent-server exec --expect-output SDK_FILES_OK --save F14.sdk-workspace/program -- .venv/bin/python "$F/sdk_files.py" "$F" "$WS" "$CID"
  ```
  两者工作区上传 blob（硬盘上的文件匹配），并按字节下载它。 的作用域工作区'上传外部 `WS` 返回
  `success=False` 与 `error` 中的 422（SDK 将 HTTP 个错误吞入结果中）并且不写入任何内容。
- **重新启动 (`F14.restart`)。**重新启动服务器并读回所有内容。

  需要：`F14.trajectory`
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/file/download --query path="$F/xfer/a/b/blob.bin" --expect 200 --raw-out "$F/after-restart.out"
  cmp "$F/v2.txt" "$F/after-restart.out"
  control-agent-server api GET "/api/conversations/$CID/file/download" --query path="$WS/qa-f14-up/blob.bin" --expect 200 \
    --raw-out "$F/after-restart-scoped.bin" --save F14.restart/scoped-download
  cmp "$F/blob.bin" "$F/after-restart-scoped.bin"
  control-agent-server api GET "/api/conversations/$CID/file/download-trajectory/$CID" --expect 200 \
    --raw-out "$F/after-restart.zip" --save F14.restart/trajectory
  python3 -c 'import sys,zipfile; n=zipfile.ZipFile(sys.argv[1]).namelist(); ev=[m for m in n if m.startswith(sys.argv[2]+"/events/event-")]; assert len(ev) >= int(sys.argv[3]), (len(ev), sys.argv[3])' "$F/after-restart.zip" "$HEX" "$NEV"
  control-agent-server api GET "/api/conversations/$CID2/file/download" --query path="$WS/qa-f14-agent.txt" --expect 422
  control-agent-server doctor
  ```
  重写全局文件、受控上传以及轨迹（至少与之前相同数量的事件）在重启后被服务，恢复的对话仍然绑定其范围（保护仍然拒绝 `WS`）
  `CID2`），`doctor` 即可。
- **初始时对话路径 (`F14.trajectory-init-path`).**第二台服务器开始休眠；
  `POST /api/init`（`--auth init` 发送该运行的机密键
  `X-Init-API-Key`) 将其对话移动到测试夹具目录。 即使断言失败，陷阱也会停止第二个服务器； 它的证据保留在它自己的运行目录中。
  ```sh
  B=$(control-agent-server launch --new --name f14-init --deferred-init --print-run)
  trap 'control-agent-server stop --run "$B" > /dev/null' EXIT
  BP="$B/fixtures/qa-f14-conversations"
  mkdir -p "$BP"
  control-agent-server api POST /api/init --run "$B" --auth init \
    --json "{\"conversations_path\": \"$BP\"}" --expect 200 --check state eq ready
  control-agent-server llm preset deepseek --run "$B"
  BCID=$(control-agent-server conversation start --run "$B" --tools file_editor --no-autotitle --print-id)
  test -d "$BP/$(printf '%s' "$BCID" | tr -d -)"
  control-agent-server api GET "/api/conversations/$BCID" --run "$B" --expect 200 --check id eq "$BCID"
  control-agent-server api GET "/api/file/download-trajectory/$BCID" --run "$B" --expect 200 --save F14.trajectory-init-path/global
  control-agent-server api GET "/api/conversations/$BCID/file/download-trajectory/$BCID" --run "$B" --expect 200 \
    --save F14.trajectory-init-path/scoped
  ```
  对话在初始化路径下已持久化，而 `GET` 找到了它。 两者轨迹路线都返回其 zip：`download_trajectory` 读取
  `conversations_path` 来自安装的配置 `POST /api/init`
  `app.state`，不是启动时默认值。

<a id="gotchas"></a>

## 陷阱

- 上传目的地是`path`查询参数，而不是表单字段，并且多部分字段必须命名为`file`。 响应是
  `{"success": true, "file_size": N}`，写入的字节数； SDK和TypeScript的消费者报告说`file_size`(`F14.upload-size`)。
- 上传会在流式传输之前截断目标，因此上传失败可能会留下部分文件； 它不是原子的（`F14.upload-atomic`）。 该配方降低了第二个服务器的 `RLIMIT_FSIZE` 和 `prlimit`（util-linux，仅限 Linux）； Python 忽略 `SIGXFSZ`，因此写入失败并显示 `EFBIG`，而不是终止服务器。 小于 1 MB 的主体保留在 Starlette 的内存中假脱机中，因此该限制会影响处理程序的写入，而不是多部分解析器。
- 全局路由接受服务器用户可以到达的任何绝对路径（包括`/etc`）； 只有受保护的路由才能限制路径。 将测试夹具保留在运行目录或 `/tmp/qa-f14-*` 下。
- 作用域路径检查发生在路由器依赖项中：相对路径和外部路径为 422，而全局路由上的相同相对路径为 400。
  `home` 和 `search_subdirs` 没有作用域变体。
- `search_subdirs`' 光标是下一个条目的确切名称（小写光标仍然不区分大小写地恢复）； 未知的 `page_id` 默默地从第一页重新开始。 仅案例双胞胎分页 (`F14.subdirs-case-pagination`)。 `home` 最多列出 50 个收藏夹，没有分页。 403 (`Permission denied`) 无法以 root 身份复制。
- `F14.home` 准确计算收藏夹：它依赖于启动器的私有
  `HOME` 仅保存隐藏条目（`.config`、`.gitconfig`、`.openhands`）。
- `archive` 解决仓库以归档：如果 `path` 不是仓库，但位于仓库的最上层（跳过隐藏和 vendored 目录），两种格式归档的只是那个仓库，因此仓库以外的文件不在 `tar.gz`。 `format` 和 `path` 的描述是这样说的 (`F14.archive-format-doc`)。 需要一切的调用者必须传递包含零个或多个存储库或存储库本身的路径。
- `git-delta` 尊重存储库的 `.gitignore`（临时索引上的 `git add -A`）；
  `tar.gz` 不适用且仅适用排除 glob。 自动底座是
  `origin/<branch>`，然后是 `origin/<default branch>` 或与之合并的基础，然后是空树，因此无远程存储库会提供完整存储库补丁，除非 `base_ref=HEAD`； 分离的 HEAD 使用 `HEAD` (`F14.archive-auto-base`)。 不管怎样，`X-Archive-Base-Ref`就是`auto`。
- 存储库身份标头（`X-Archive-Repo-Root`、`-Branch`、
  `-Head-Commit`, `-Repo-Remote`) 仅当归档目录本身包含 `.git` 时才发送； 归档存储库的子目录返回
  `X-Archive-Base-*` 标头，但没有身份标头。
- 诸如 `X-Archive-Repo-Root` 之类的标头值是百分比编码的。
  `api --check-header` 在任何响应头（保存的交换仅保留少数几个，除非`--all-headers`给出）上进行断言，而重复的`--query`标志会保留每个值，因此`exclude=a&exclude=b`是两个`--query exclude=`标志。
- git discovery 从 `path` 开始。 如果任何运行家的祖先是一个仓库（一个工作区的`/tmp`会离开`/tmp/.git`，因为服务器`git init`的工作区不在一个仓库内），一个普通的目录“在仓库内”：`git-delta`会返回200，并带有相对于那个祖先的补丁，服务器跳过`git init`，对于新的工作区，所以 scoped patches会携带长的祖先相对路径。 因此，前提条件是重新启动运行
  `GIT_CEILING_DIRECTORIES=<run>` 并检查 `CID` 的工作区是否有自己的
  `.git`; 仅将该行放在运行主目录上方没有存储库的计算机上。
- 该档案的临时文件创建在 `path`其父目录（当父目录不可写时为系统临时目录）和在响应后移除。 的范围存档工作区它生活在外部工作区。
- 每个会话工作区都会在启动时由服务器进行 `git init` 编辑（无提交），因此工作区的范围 `git-delta` 存档始终针对空树。
- `download-trajectory`仅检查`<conversations_path>/<hex>/`是否存在，而不检查对话是否已加载； 它包括租赁文件和每个事件文件，跳过顶级 `acp/` 目录，并编辑 JSON/JSONL 凭据字段以及任何 Fernet token。 它写入固定的临时名称（`F14.trajectory-concurrent`）并从实时读取`conversations_path`
  `app.state.config`，因此它遵循初始化时路径 (`F14.trajectory-init-path`)。
- 没有文件路由发出对话事件或 WebSocket 帧； 他们的第二个视图是下载、列表、档案和磁盘。
- 在 deferred-init 服务器上，这里的每条路由都是 503 直到 `POST /api/init`（deferred-init 系列拥有该门）。
- 智能体只得到`file_editor`（`conversation start --tools file_editor`），所以家庭不需要`tmux`； 模型的一项工作就是编写
  `qa-f14-agent.txt`，然后由范围下载和存档读取。
