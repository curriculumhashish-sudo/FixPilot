<a id="git-changes-diffs-commits-and-repository-search"></a>

# Git 更改、差异、提交和存储库搜索

只读 Agent Server 主机上目录的 git 视图，用于显示智能体所做操作的“更改”和“提交”选项卡。 `changes` 根据显示库列出工作树的文件（`UPDATED`、`ADDED`、`DELETED`； 未跟踪的文件是 `ADDED`，重命名是 `DELETED` 加 `ADDED`），按路径排序，包括嵌套在下一层的存储库。 `diff`返回完整的
一个文件的 `original` 和 `modified` 文本，无论是针对基础 (`ref`) 还是在一次提交时更改它 (`commit`)。 `commits`页历史可达
from `HEAD`, newest first, and `commits/{sha}/changes` lists the files one
提交针对其第一个父级发生了更改。 非存储库的路径给出空结果，而不是错误； 其他 git 失败是 400。 除了存储库搜索之外的所有操作也存在于
`/api/conversations/{runtime_conversation_id}/git/...`, where `path` 必须在对话中解决工作区。 仓库搜索与本地目录无关：它列出的是  GitHub  token 存储在服务器端的机密可以访问（`missing_token` 当有 None).

资料来源：`openhands-agent-server/openhands/agent_server/git_router.py`、`openhands-agent-server/openhands/agent_server/git_provider_service.py`、`openhands-agent-server/openhands/agent_server/runtime_router.py`、`openhands-sdk/openhands/sdk/git/`、`openhands-sdk/openhands/sdk/workspace/remote/remote_workspace_mixin.py`、`clients/typescript/src/workspace/remote-workspace.ts`、`clients/typescript/src/client/git-client.ts`

需求：`llm`、`git`、`node`

路线：`GET /api/conversations/{runtime_conversation_id}/git/changes`，
`GET /api/conversations/{runtime_conversation_id}/git/diff`,
`GET /api/conversations/{runtime_conversation_id}/git/commits`,
`GET /api/conversations/{runtime_conversation_id}/git/commits/{sha}/changes`,
`GET /api/git/repositories/search`, `GET /api/git/changes`,
`GET /api/git/diff`, `GET /api/git/commits`, `GET /api/git/commits/{sha}/changes`

<a id="sub-features"></a>

## 子功能

- `F15.auth`：每个全局和对话范围的 git 路由都会在没有有效会话密钥的情况下回答 401。
- `F15.changes`: `changes` 在测试夹具仓库列出已修改的跟踪文件为 `UPDATED` 以及未跟踪的文件作为 `ADDED`按路径排序，为仓库相对路径 POSIX 路径，匹配 `git status`.
- `F15.changes-statuses`：分阶段删除是`DELETED`，分阶段新文件`ADDED`，分阶段重命名`DELETED`旧路径加`ADDED`新路径。
- `F15.changes-base`: 无 `ref`，本地 `HEAD` 的显示基默认分支，本地 `main` 的分支点（已提交的工作仍可见）， `origin` 的默认分支的分支点，以及树脏的分支的上游。
- `F15.changes-ref`: `ref=HEAD` 提供 `git status` 样式的更改，较旧的提交添加其较晚提交的文件； 未知或选项形状的 `ref` 是 400 并且永远不会作为 git 选项运行； 没有`path`是422。
- `F15.changes-nested-repo`在请求的仓库层级以下的仓库内部更改将以嵌套目录作为前缀列出，而嵌套目录本身不会列出 `diff` 该条记录读取嵌套的仓库。
- `F15.changes-repo-below-path`：一个非仓库目录，它包含一个仓库（基于仓库的对话的布局）以目录为前缀列出该仓库的更改。
- `F15.changes-special-names`：名称中有空格或非ASCII字符的修改跟踪文件列在其真实名称下； 今天，一个空格使整个列表失败，结果为 400，并且非 ASCII 名称以损坏的 git-quoted 字符串形式返回。
- `F15.changes-subdir-paths`：对于仓库中的子目录，`changes` 仅列出该目录下已跟踪与未跟踪文件的变更，并使用相对于请求目录的路径。
- `F15.non-repo`：在普通目录、丢失目录和非存储库文件上，每个操作都会回答 200，结果为空（`[]`、`{"original": null, "modified": null}`、`{"commits": [], "has_more": false}`）； 没有提交的存储库将其文件列为 `ADDED` 并且没有提交。
- `F15.diff`：`diff` 对于已修改的文件，将基本文本返回为 `original`，将磁盘文本返回为 `modified`（两边都删除最后的换行符），未跟踪的文件具有 `original` `""`，并且显式 `ref` 移动基本文本。
- `F15.diff-commit`: `commit=<sha>` 返回该提交更改的文件，从 git 对象中读取：`original` 从第一个父提交（根提交为空，添加的文件则为空），`modified` 从该提交（删除的文件为空），也包括不再存储在磁盘上的文件和简短的SHAs。
- `F15.diff-errors`：`ref` 与 `commit` 一起为 400、非十六进制 `commit` 422、未知提交或引用 400、丢失文件 400、超过 1 MiB 400 的文件以及无 `path` 422。
- `F15.diff-whitespace`：带有前导缩进或后跟空格的未改动文件与`original`和`modified`完全相同，因此`changes`中未列出的文件没有差异。
- `F15.diff-deleted-file`：`changes` 列为 `DELETED` 的文件的工作树差异返回其基本文本为 `original`，`""` 为 `modified`； 磁盘上和底部都缺失的路径仍然是 400 `File does not exist`。
- `F15.commits`: `commits`按最新时间顺序列出，`sha`、`short_sha`、`subject`、`author`和一个ISO8601`timestamp`，`has_more`告诉`limit`是否切掉，`limit`不在1..200范围内是422。
- `F15.commit-changes`: `commits/{sha}/changes`列出了一次提交的文件及其第一个父提交（所有`ADDED`，一个重命名`DELETED`和`ADDED`）；接受简写SHAs，返回未知SHA的400状态码和非十六进制或短于4位的SHA的422状态码。
- `F15.scoped`：工作区是测试夹具存储库的会话上的四个会话范围路由返回的内容与全局路由返回的内容完全相同。
- `F15.scoped-guard`: 范围内的路由拒绝 `path` 从工作区外部（另一个目录、同前缀的兄弟、`..`、一个符号链接逃逸、一个相对路径、一个指向外部的第二个 `path` 参数）；而全局路由则提供它。 未知对话为 404，格式错误的 ID 为 422，并且没有范围存储库搜索。
- `F15.scoped-restart`：重新启动后，作用域路由仍解析对话的工作区并返回相同的更改。
- `F15.sdk-workspace`: the Python  SDK's `RemoteWorkspace.git_changes` 和 `git_diff` 将相对路径连接起来 `working_dir` 并返回相同的结果（全局和局部的）`runtime_conversation_id`), and the scoped 工作区拒绝了不在它范围内的路径，返回状态码 422。
- `F15.ts-client`: the TypeScript 客户端的 `RemoteWorkspace.gitChanges` (with `ref`) 和 `gitDiff` 返回相同的结果平平常常地 `conversationId`，该路径不在的范围内工作区，and `GitClient.searchRepositories` 返回 `missing_token` 页。
- `F15.agent-changes`：在实际模型运行后，工作区将文件写入仓库，`changes`会将其标记为`ADDED`，`diff`会显示写入的文本，而事件流会显示文件编辑器的观测结果。
- `F15.repo-search-token`：没有存储token，GitHub搜索为200次`{"items": [], "next_page_id": null, "missing_token": true}`； 名为 `github_token` 或 `GH_TOKEN` 的机密被选中（然后验证格式错误的 `page_id`，并以 400 拒绝），删除它即可恢复 `missing_token`。
- `F15.repo-search-errors`：`gitlab`和`bitbucket`为400（不支持），未知或缺失的`provider`为422，1..100之外的`limit`为422。
- `F15.repo-search-unreachable`：当无法到达 GitHub 时，搜索为 502，其中包含通用屏蔽主体且其中没有 token。
- `F15.repo-search-timeout`：当 GitHub 在 15 秒内没有回答时，搜索为 504，其中包含屏蔽正文 `GitHub repository search timed out`，并且其中没有 token。
- `F15.repo-search-github`：对于真实的 GitHub token，搜索会列出 token 的存储库，并带有 `page:offset` 游标和不区分大小写的 `query` 过滤器。
- `F15.repo-search-rejected-token`：提供商针对被拒绝的 token 的 HTTP 401 作为带有一般错误的 401 传递，而不暴露 token。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，全局：`GET /api/git/changes?path=<repo>&ref=<ref>`，
  `GET /api/git/diff?path=<file>&ref=<ref>|commit=<sha>`,
  `GET /api/git/commits?path=<repo>&limit=1..200`,
  `GET /api/git/commits/{sha}/changes?path=<repo>`. `path` 是服务器用户可以读取的任何绝对路径。 相对路径根据服务器进程的工作目录进行解析。 除了带瞄准镜的子弹外，每颗子弹都会驱动这些子弹。
- REST，对话范围：同四下
  `/api/conversations/{runtime_conversation_id}/git/...`; 的
  `bind_local_conversation_runtime` 依赖拒绝非绝对的或无法在 `workspace.working_dir` 内解析的 `path`。 驱动力
  `F15.auth`、`F15.scoped`、`F15.scoped-guard`、`F15.scoped-restart` 和
  `F15.agent-changes`，并通过 `F15.sdk-workspace` 和客户端
  `F15.ts-client`.
- REST，提供商搜索（仅限全球）：
  `GET /api/git/repositories/search?provider=github&query=...&limit=1..100&page_id=...`; token 来自服务器的机密存储（`PUT /api/settings/secrets`、名称 `github_token`、`GITHUB_TOKEN`、`GH_TOKEN`、`github`，按顺序）。
- SDK：`RemoteWorkspace.git_changes(path)` 和 `git_diff(path)`（以及
  `AsyncRemoteWorkspace` 版本）加入相对的 `path` 到 `working_dir` 并调用全局路由，或者当工作区具有范围时调用范围路由
  `runtime_conversation_id`. 他们既不发送 `ref` 也不发送 `commit`，并且没有用于 `commits` 或存储库搜索的 SDK 方法。 驱动力
  `F15.sdk-workspace`（`exec` 程序）。
- TypeScript 客户端：`RemoteWorkspace.gitChanges(path, {ref})` 和
  `gitDiff(path, {ref})`（范围通过运行时传输层，当
  设置为`conversationId`）； `GitClient.searchRepositories({provider, query, limit, pageId})`. 由 `F15.ts-client` 驱动（`node` 程序
  `clients/typescript/dist`).
- Agent Canvas（仅限上下文）：“更改”选项卡（更改和比较）、“提交”选项卡（提交、提交更改、与 `commit` 比较）和存储库选取器（搜索）。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已实时并导出，`doctor` 正常，`git` 和 `node` 已安装，`$DEEPSEEK_API_KEY` 已设置（仅 `F15.agent-changes` 使用该模型； 只有 `F15.ts-client` 使用 `node`，如果 `clients/typescript/dist` 缺失，则使用 `npm ci && npm run build` 构建 TypeScript 客户端）。 不需要启动标志； `F15.repo-search-unreachable` 使用失效的代理重新启动运行并恢复它。
- 下方代码块启用 `deepseek-flash`，让 `git` 指向本次运行的私有配置（作者为 `QA Verify`，因此此处提交无须全局 Git 身份），并创建 `qa-f15-repo` 测试夹具（提交 `Initial commit` =
  `C1` 和 `Add util` = `C2`，修改后的 `README.md`，未跟踪的
  `notes.txt`）和一个从未运行的对话 `CID`，其工作区是该存储库。 改变存储库的项目符号在 `$F` 下的副本上工作。 运行目录不得位于任何 git 存储库中：非存储库项目符号会默默地测试封闭的目录（并且
  `F15.changes-repo-below-path` 会错误地通过），因此该块会以封闭存储库的路径停止（请参阅陷阱）。
  ```sh
  control-agent-server llm preset deepseek
  export GIT_CONFIG_GLOBAL="$AGENT_SERVER_VERIFY_RUN/home/.gitconfig"
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f15"
  rm -rf "$F"
  mkdir -p "$F"
  if ENCLOSING=$(git -C "$F" rev-parse --show-toplevel 2>/dev/null); then
    echo "environment: $F is inside the git repository $ENCLOSING; set AGENT_SERVER_VERIFY_HOME outside it" >&2
    exit 1
  fi
  REPO=$(control-agent-server fixture git-repo --name qa-f15-repo --print-path)
  C1=$(git -C "$REPO" rev-parse HEAD~1)
  C2=$(git -C "$REPO" rev-parse HEAD)
  CID=$(control-agent-server conversation start --workspace "$REPO" --tools none --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --check workspace.working_dir eq "$REPO"
  ```

- **需要会话密钥 (`F15.auth`)。**运行的关键进入（正控制）； 然后每条路线都没有钥匙（钥匙错误）。
  ```sh
  control-agent-server api GET /api/git/changes --query path="$REPO" --expect 200 --check . len-eq 2
  control-agent-server api GET "/api/conversations/$CID/git/changes" --query path="$REPO" --expect 200 --check . len-eq 2
  control-agent-server api GET /api/git/changes --auth none --query path="$REPO" --expect 401
  control-agent-server api GET /api/git/diff --auth none --query path="$REPO/README.md" --expect 401
  control-agent-server api GET /api/git/commits --auth bad --query path="$REPO" --expect 401
  control-agent-server api GET "/api/git/commits/$C2/changes" --auth none --query path="$REPO" --expect 401
  control-agent-server api GET /api/git/repositories/search --auth none --query provider=github --expect 401
  control-agent-server api GET "/api/conversations/$CID/git/changes" --auth none --query path="$REPO" --expect 401
  control-agent-server api GET "/api/conversations/$CID/git/diff" --auth none --query path="$REPO/README.md" --expect 401
  control-agent-server api GET "/api/conversations/$CID/git/commits" --auth none --query path="$REPO" --expect 401
  control-agent-server api GET "/api/conversations/$CID/git/commits/$C2/changes" --auth none --query path="$REPO" \
    --expect 401 --check detail eq Unauthorized --save F15.auth/scoped-commit-changes
  ```
  两个视图都返回了200。 没有九个答案
  `401 {"detail": "Unauthorized"}`.
- **工作树更改 (`F15.changes`).**创建时的测试夹具。
  ```sh
  control-agent-server api GET /api/git/changes --query path="$REPO" --expect 200 --check . len-eq 2 \
    --check 0.status eq UPDATED --check 0.path eq README.md --check 1.status eq ADDED --check 1.path eq notes.txt \
    --save F15.changes/fixture
  git -C "$REPO" status --porcelain > "$F/status.txt"
  grep -qx ' M README.md' "$F/status.txt"
  grep -qx '?? notes.txt' "$F/status.txt"
  test "$(wc -l < "$F/status.txt")" -eq 2
  ```
  `[{"status": "UPDATED", "path": "README.md"}, {"status": "ADDED", "path": "notes.txt"}]`次，`git status --porcelain`条相同的记录再次出现。
- **分阶段删除、添加和重命名 (`F15.changes-statuses`)。**在副本上，删除 `src/util.py`，重命名 `src/app.py`，暂存一个新文件。
  ```sh
  cp -r "$REPO" "$F/statuses"
  git -C "$F/statuses" rm -q src/util.py
  git -C "$F/statuses" mv src/app.py src/main.py
  printf 'staged\n' > "$F/statuses/staged.txt"
  git -C "$F/statuses" add staged.txt
  control-agent-server api GET /api/git/changes --query path="$F/statuses" --expect 200 --check . len-eq 6 \
    --check 0.path eq README.md --check 1.path eq notes.txt \
    --check 2.status eq DELETED --check 2.path eq src/app.py --check 3.status eq ADDED --check 3.path eq src/main.py \
    --check 4.status eq DELETED --check 4.path eq src/util.py --check 5.status eq ADDED --check 5.path eq staged.txt \
    --save F15.changes-statuses/staged
  ```
  重命名 `src/app.py -> src/main.py` 显示为 `DELETED src/app.py` 加上
  `ADDED src/main.py`; 列表保持按路径排序。 尽管枚举有，但实际上没有`MOVED`。
- **默认显示底座 (`F15.changes-base`)。**从本地 `main` 分叉出一个功能分支，然后使用推送分支克隆本地裸远程。
  ```sh
  cp -r "$REPO" "$F/branch"
  git -C "$F/branch" checkout -qb qa-feat
  printf 'feat\n' > "$F/branch/feat.txt"
  git -C "$F/branch" add feat.txt
  git -C "$F/branch" commit -qm 'QA feat'
  control-agent-server api GET /api/git/changes --query path="$F/branch" --expect 200 --check . len-eq 3 \
    --check 1.status eq ADDED --check 1.path eq feat.txt --save F15.changes-base/feature-branch
  control-agent-server api GET /api/git/diff --query path="$F/branch/feat.txt" --expect 200 \
    --check original eq '' --check modified eq feat
  git clone -q --bare "$REPO" "$F/origin.git"
  git clone -q "$F/origin.git" "$F/clone"
  git -C "$F/clone" checkout -qb qa-pr
  printf 'pr\n' > "$F/clone/pr.txt"
  git -C "$F/clone" add pr.txt
  git -C "$F/clone" commit -qm 'QA pr'
  git -C "$F/clone" push -q -u origin qa-pr
  control-agent-server api GET /api/git/changes --query path="$F/clone" --expect 200 --check . len-eq 1 \
    --check 0.status eq ADDED --check 0.path eq pr.txt --save F15.changes-base/pushed-clean
  printf 'edit\n' >> "$F/clone/pr.txt"
  control-agent-server api GET /api/git/changes --query path="$F/clone" --expect 200 --check . len-eq 1 \
    --check 0.status eq UPDATED --check 0.path eq pr.txt --save F15.changes-base/pushed-dirty
  ```
  在测试夹具的独立 `main`（没有远程）的情况下，基础是 `HEAD`，这就是为什么
  `F15.changes` 显示没有提交的文件。 关于`qa-feat`所承诺的
  `feat.txt` 保持可见（base = merge-base 与本地 `main`），其 diff 有一个空的 `original`。 在推动的、干净的`qa-pr`上，底座是`origin/main`的分叉点，因此PR的`pr.txt`是`ADDED`； 一旦树变脏，基部就会变成 `origin/qa-pr`，并且只有编辑显示 (`UPDATED`)。
- **显式基数及其错误 (`F15.changes-ref`).**
  ```sh
  control-agent-server api GET /api/git/changes --query path="$F/branch" --query ref=HEAD --expect 200 --check . len-eq 2 \
    --check 0.path eq README.md --check 1.path eq notes.txt --save F15.changes-ref/head
  control-agent-server api GET /api/git/changes --query path="$REPO" --query ref="$C1" --expect 200 --check . len-eq 3 \
    --check 2.status eq ADDED --check 2.path eq src/util.py --save F15.changes-ref/older-commit
  control-agent-server api GET /api/git/changes --query path="$REPO" --query ref=qa-f15-no-such-ref --expect 400 \
    --check detail contains 'Git command failed' --save F15.changes-ref/unknown
  control-agent-server api GET /api/git/changes --query path="$REPO" --query ref="--output=$F/injected" --expect 400
  test ! -e "$F/injected"
  control-agent-server api GET /api/git/changes --expect 422 --check detail.0.loc contains path
  ```
  `ref=HEAD` 删除功能分支的已提交 `feat.txt`； `ref=<C1>` 补充
  `src/util.py`（在`C1`之后提交）； 未知的参考值是 400
  `Git command failed: git --no-pager rev-parse --verify 'qa-f15-no-such-ref^{commit}'`; 选项形状的 ref 只能达到 `rev-parse --verify`
  `^{commit}`后缀，所以是400，什么也不写。
- **嵌套存储库 (`F15.changes-nested-repo`).**另一个副本中的测试夹具的副本。
  ```sh
  cp -r "$REPO" "$F/outer"
  cp -r "$REPO" "$F/outer/inner"
  control-agent-server api GET /api/git/changes --query path="$F/outer" --expect 200 --check . len-eq 4 \
    --check 0.path eq README.md --check 1.status eq UPDATED --check 1.path eq inner/README.md \
    --check 2.status eq ADDED --check 2.path eq inner/notes.txt --check 3.path eq notes.txt \
    --save F15.changes-nested-repo/outer
  git -C "$F/outer" status --porcelain | grep -qx '?? inner/'
  control-agent-server api GET /api/git/diff --query path="$F/outer/inner/README.md" --expect 200 \
    --check original eq "$(git -C "$F/outer/inner" show HEAD:README.md)" --check modified eq "$(cat "$F/outer/inner/README.md")" \
    --save F15.changes-nested-repo/inner-diff
  ```
  `git status` 外层仓库的版本显示 `?? inner/`; 的 API 而是列出内层仓库自己的更改 `inner/` 并且不是目录本身，而是目录的差异 `inner/README.md` 是从内层仓库读取的（其提交的文本与编辑）。
- ** 低于请求目录的仓库 (`F15.changes-repo-below-path`).** 一个只包含一个仓库的普通目录，就像一个仓库支持的对话的工作区一样 (`{base}/{repo}`).
  ```sh
  mkdir -p "$F/ws"
  cp -r "$REPO" "$F/ws/proj"
  if git -C "$F/ws" rev-parse --git-dir >/dev/null 2>&1; then false; fi
  control-agent-server api GET /api/git/changes --query path="$F/ws/proj" --expect 200 --check . len-eq 2 \
    --check 0.path eq README.md --check 1.path eq notes.txt
  control-agent-server api GET /api/git/changes --query path="$F/ws" --expect 200 --check . len-eq 2 \
    --check 0.path eq proj/README.md --check 1.path eq proj/notes.txt --save F15.changes-repo-below-path/ws
  ```
  `$F/ws` 本身不是存储库，它下面的存储库用它的两个更改（正控制）来回答。 目录以`proj/`中的两个更改排序，并按路径列出，就像一个嵌套仓库那样（`GET /api/file/archive`也解析了相同的布局），因此，使用仓库支持的对话根工作区的消费者可以看到其更改。 该目录本身没有做出任何更改。
- **文件名包含空格或非 ASCII 字符 (`F15.changes-special-names`)，已知错误。**
  ```sh
  mkdir -p "$F/names"
  git -C "$F/names" init -q -b main
  printf 'a\n' > "$F/names/my notes.md"
  printf 'b\n' > "$F/names/café.txt"
  git -C "$F/names" add -A
  git -C "$F/names" commit -qm 'QA names'
  printf 'u\n' > "$F/names/untracked note.md"
  control-agent-server api GET /api/git/changes --query path="$F/names" --expect 200 --check . len-eq 1 \
    --check 0.status eq ADDED --check 0.path eq 'untracked note.md'
  rm "$F/names/untracked note.md"
  printf 'a2\n' > "$F/names/my notes.md"
  control-agent-server api GET /api/git/changes --query path="$F/names" --expect 200 --check . len-eq 1 \
    --check 0.status eq UPDATED --check 0.path eq 'my notes.md' --save F15.changes-special-names/space  # bug：status eq 400 && response.body.detail 包含“意外的 git diff 输出格式”
  git -C "$F/names" checkout -q -- 'my notes.md'
  printf 'b2\n' > "$F/names/café.txt"
  control-agent-server api GET /api/git/changes --query path="$F/names" --expect 200 --check . len-eq 1 \
    --check 0.path eq café.txt --save F15.changes-special-names/non-ascii  # bug：状态 eq 200 && response.body.0.path 包含 303/251
  ```
  已提交的仓库对带有空格的未跟踪名称（正控制：名称中的路径和空格是独立有效的）做出了回应。 预期：每个修改后的文件应以其真实名称。 实际上，空间本身构成了整个列表 `400 {"detail": "Unexpected git diff output format: M\tmy notes.md"}` (`_parse_name_status` 分割成 `--name-status` 任何空白行上的行（例如，#），因此一个文件会隐藏其他所有更改； `GET /api/git/commits/{sha}/changes` 添加它的提交失败的方式相同。 已修改的 `café.txt` 返回为 `"\"caf/303/251.txt\""`git的C-quoted八进制形式（`core.quotePath`), 保留引号并将反斜杠转换为斜杠 POSIX path 序列化器。 带有空格的未跟踪名称是没问题的。 未跟踪的非-ASCII 名字也被同样的方式变形。
- **存储库的子目录 (`F15.changes-subdir-paths`)。**
  `path` 是带有修改过的 `src/app.py` 和未跟踪的副本的 `src/`
  `src/new.py`.
  ```sh
  cp -r "$REPO" "$F/subdir"
  printf 'def greet(name):\n    return name\n' > "$F/subdir/src/app.py"
  printf 'new\n' > "$F/subdir/src/new.py"
  control-agent-server api GET /api/git/changes --query path="$F/subdir" --expect 200 --check . len-eq 4 \
    --check 0.path eq README.md --check 1.path eq notes.txt --check 2.path eq src/app.py --check 3.path eq src/new.py
  control-agent-server api GET /api/git/changes --query path="$F/subdir/src" --expect 200 \
    --raw-out "$F/subdir.json" --save F15.changes-subdir-paths/src
  python3 - "$F/subdir.json" "$F/subdir/src" "$F/subdir" <<'PY' | control-agent-server assert --check paths eq '["app.py", "new.py"]' --check bases len-eq 1 --check 'bases.0' eq "$F/subdir/src"
  import json, os, sys
  changes = json.load(open(sys.argv[1]))
  paths = sorted(c["path"] for c in changes if c["status"] != "DELETED")
  bases = [b for b in sys.argv[2:] if all(os.path.exists(os.path.join(b, p)) for p in paths)]
  print(json.dumps({"paths": paths, "bases": bases}))
  PY
  ```
  仓库根目录列出所有四个更改（正控制）。 对于 `src/`，列表是 `[UPDATED app.py, ADDED new.py]`：只包括 `src/`（根的 `README.md` 和 `notes.txt` 被省略），每个路径相对于请求的目录，因此每个路径都连接到
  `path` 命名一个存在的文件。 `get_changes_in_repo` 运行
  `git diff --name-status --relative`，其范围和相对方式与未跟踪文件的 `git ls-files --others` 相同。
- **不是存储库，或尚未提交 (`F15.non-repo`)。**
  ```sh
  mkdir -p "$F/plain"
  printf 'x\n' > "$F/plain/x.txt"
  control-agent-server api GET /api/git/changes --query path="$F/plain" --expect 200 --check . len-eq 0 --save F15.non-repo/changes
  control-agent-server api GET /api/git/changes --query path="$F/no-such-dir" --expect 200 --check . len-eq 0
  control-agent-server api GET /api/git/diff --query path="$F/plain/x.txt" --expect 200 \
    --check original eq null --check modified eq null --save F15.non-repo/diff
  control-agent-server api GET /api/git/commits --query path="$F/plain" --expect 200 \
    --check commits len-eq 0 --check has_more eq false --save F15.non-repo/commits
  control-agent-server api GET "/api/git/commits/$C2/changes" --query path="$F/plain" --expect 200 --check . len-eq 0
  mkdir -p "$F/unborn"
  git -C "$F/unborn" init -q -b main
  printf 'x\n' > "$F/unborn/x.txt"
  control-agent-server api GET /api/git/changes --query path="$F/unborn" --expect 200 --check . len-eq 1 \
    --check 0.status eq ADDED --check 0.path eq x.txt --save F15.non-repo/unborn
  control-agent-server api GET /api/git/changes --query path="$F/unborn" --query ref=HEAD --expect 200 --check 0.path eq x.txt
  control-agent-server api GET /api/git/commits --query path="$F/unborn" --expect 200 --check commits len-eq 0 --check has_more eq false
  ```
  空目录和缺失目录 `[]`，不在任何仓库中的文件
  `{"original": null, "modified": null}`（不是 `""`），提交
  `{"commits": [], "has_more": false}`，提交更改 `[]`。 一个新鲜的
  `git init` 将其文件列为 `ADDED`（空树基，也用于
  `ref=HEAD`）并且历史记录为空。
- **每个文件差异 (`F15.diff`)。**修改后的文件和未跟踪的文件。
  ```sh
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --expect 200 \
    --check original eq "$(git -C "$REPO" show HEAD:README.md)" --check modified eq "$(cat "$REPO/README.md")" \
    --check original ne "$(cat "$REPO/README.md")" --save F15.diff/modified
  control-agent-server api GET /api/git/diff --query path="$REPO/notes.txt" --expect 200 \
    --check original eq '' --check modified eq 'untracked file' --save F15.diff/untracked
  control-agent-server api GET /api/git/diff --query path="$REPO/src/util.py" --expect 200 \
    --check original eq "$(cat "$REPO/src/util.py")" --check modified eq "$(cat "$REPO/src/util.py")"
  control-agent-server api GET /api/git/diff --query path="$REPO/src/util.py" --query ref="$C1" --expect 200 \
    --check original eq '' --check modified eq "$(cat "$REPO/src/util.py")" --save F15.diff/explicit-ref
  ```
  `original`是`# QA fixture repo\n\nCreated by control-agent-server.`（提交的文本，用`git show`读取），`modified`是磁盘上的文本； 两者都丢失了最后的换行符（shell 的 `$(...)` 也删除了它，因此检查比较类似）。 未跟踪的文件有 `original` `""`。 未更改的 `src/util.py` 与默认底座 (`HEAD`) 具有相同的边，并且 `ref=<C1>`（在 `src/util.py` 存在之前）移动底座，以便
  `original` 是 `""`。
- **一次提交的差异 (`F15.diff-commit`)。** 测试夹具的两个提交，然后是在副本上删除和重命名的提交。
  ```sh
  control-agent-server api GET /api/git/diff --query path="$REPO/src/util.py" --query commit="$C2" --expect 200 \
    --check original eq '' --check modified eq "$(git -C "$REPO" show "$C2:src/util.py")" --save F15.diff-commit/added
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --query commit="${C1:0:8}" --expect 200 \
    --check original eq '' --check modified eq "$(git -C "$REPO" show "$C1:README.md")"
  cp -r "$REPO" "$F/hist"
  git -C "$F/hist" rm -q src/util.py
  git -C "$F/hist" mv src/app.py src/main.py
  git -C "$F/hist" commit -qm 'QA delete and rename'
  C3=$(git -C "$F/hist" rev-parse HEAD)
  test ! -e "$F/hist/src/util.py"
  control-agent-server api GET /api/git/diff --query path="$F/hist/src/util.py" --query commit="$C3" --expect 200 \
    --check original eq "$(git -C "$REPO" show HEAD:src/util.py)" --check modified eq '' --save F15.diff-commit/deleted
  control-agent-server api GET /api/git/diff --query path="$F/hist/src/main.py" --query commit="$C3" --expect 200 \
    --check original eq '' --check modified eq "$(cat "$F/hist/src/main.py")"
  ```
  `Add util`添加`src/util.py`（`original``""`）； 添加了根提交，以 8 个字符的前缀命名；`README.md`； 删除提交呈现已删除文件的旧文本，尽管它已从磁盘中消失； 重命名的新路径是all `modified`。
- **差异错误 (`F15.diff-errors`).**
  ```sh
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --query ref=HEAD --query commit="$C2" \
    --expect 400 --check detail eq "'ref' and 'commit' are mutually exclusive" --save F15.diff-errors/ref-and-commit
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --query commit=zz --expect 422 --check detail.0.loc contains commit
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --query commit=deadbeefdeadbeef --expect 400 \
    --check detail contains 'Git command failed'
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --query ref=qa-f15-no-such-ref --expect 400 \
    --check detail contains 'Git command failed'
  control-agent-server api GET /api/git/diff --query path="$REPO/missing.txt" --expect 400 \
    --check detail eq "File does not exist: $REPO/missing.txt" --save F15.diff-errors/missing
  head -c 1100000 /dev/zero | tr '\0' a > "$F/big.txt"
  cp "$F/big.txt" "$F/statuses/big.txt"
  control-agent-server api GET /api/git/diff --query path="$F/statuses/big.txt" --expect 400 \
    --check detail eq 'File too large for git diff: 1100000 bytes (max: 1048576 bytes)' --save F15.diff-errors/too-large
  control-agent-server api GET /api/git/diff --expect 422 --check detail.0.loc contains path
  ```
  400, 422, 400, 400, 400 (消息中的绝对路径), 400 用于文件大小超过1 MiB, 和 422 无 `path`。
- **未更改的空白行（`F15.diff-whitespace`）。**提交带有前导缩进的文件，以及带有末尾空白行的文件，但不要做任何更改，要求显示它们的差异。
  ```sh
  mkdir -p "$F/ws-files"
  git -C "$F/ws-files" init -q -b main
  printf '  indented line\nbody\n' > "$F/ws-files/lead.txt"
  printf 'body\n\n\n' > "$F/ws-files/trail.txt"
  printf 'one\r\ntwo\r\n' > "$F/ws-files/crlf.txt"
  git -C "$F/ws-files" add -A
  git -C "$F/ws-files" commit -qm 'QA whitespace'
  test -z "$(git -C "$F/ws-files" status --porcelain)"
  control-agent-server api GET /api/git/changes --query path="$F/ws-files" --expect 200 --check . len-eq 0
  for name in crlf lead trail; do
    control-agent-server api GET /api/git/diff --query path="$F/ws-files/$name.txt" --query ref=HEAD --expect 200 \
      --check modified len-ge 1 --raw-out "$F/ws-$name.json" --save "F15.diff-whitespace/$name"
    jq '{original, modified, same: (.original == .modified)}' "$F/ws-$name.json" \
      | control-agent-server assert --check same eq true
  done
  ```
  预期：每个未更改文件的相同面（`changes` 是 `[]`）：
  `lead.txt`两边给出`"  indented line\nbody"`和`trail.txt``"body\n\n"`，CRLF文件`"one\ntwo"`：`get_git_diff`读取
  `git show` blob 逐字 (`strip=False`) 并将其规范化为
  `modified`, `"\n".join(text.splitlines())`. 提交模式 diff 会同时剥离两侧，因此它不会显示任何虚拟更改，但会丢失空格。
- **已删除文件的差异 (`F15.diff-deleted-file`)。** `changes`列出已删除的文件； “更改”选项卡打开的差异显示了删除。
  ```sh
  cp -r "$REPO" "$F/deleted"
  rm "$F/deleted/src/util.py"
  control-agent-server api GET /api/git/changes --query path="$F/deleted" --expect 200 \
    --check 2.status eq DELETED --check 2.path eq src/util.py
  control-agent-server api GET /api/git/diff --query path="$F/deleted/src/util.py" --expect 200 \
    --check original eq "$(git -C "$REPO" show HEAD:src/util.py)" --check modified eq '' --save F15.diff-deleted-file/diff
  ```
  预期：基础文本为 `original`，`""` 为 `modified`，
  提交模式 diff 对已删除的文件起作用； 工作树重命名的旧部分以同样的方式进行比较。 `get_git_diff` 读取磁盘中缺少的路径
  from the base ref and answers `File does not exist` only when the base has
  那里也没有文件（`F15.diff-errors/missing`）。
- **提交历史记录 (`F15.commits`).**
  ```sh
  control-agent-server api GET /api/git/commits --query path="$REPO" --expect 200 --check commits len-eq 2 \
    --check has_more eq false --check commits.0.sha eq "$C2" --check commits.0.subject eq 'Add util' \
    --check commits.0.short_sha eq "$(git -C "$REPO" log -1 --format=%h)" --check commits.0.author eq 'QA Verify' \
    --check commits.0.timestamp matches '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(Z|[+-]\d\d:\d\d)$' \
    --check commits.1.sha eq "$C1" --check commits.1.subject eq 'Initial commit' --save F15.commits/all
  control-agent-server api GET /api/git/commits --query path="$REPO" --query limit=1 --expect 200 --check commits len-eq 1 \
    --check commits.0.sha eq "$C2" --check has_more eq true --save F15.commits/limit-1
  control-agent-server api GET /api/git/commits --query path="$REPO" --query limit=2 --expect 200 --check commits len-eq 2 \
    --check has_more eq false
  control-agent-server api GET /api/git/commits --query path="$F/branch" --query limit=200 --expect 200 --check commits len-eq 3 \
    --check commits.0.subject eq 'QA feat' --check has_more eq false
  test "$(git -C "$REPO" log --format=%H | head -1)" = "$C2"
  control-agent-server api GET /api/git/commits --query path="$REPO" --query limit=0 --expect 422
  control-agent-server api GET /api/git/commits --query path="$REPO" --query limit=201 --expect 422
  ```
  按最新发布排序，匹配 `git log`。 `limit=1`报告`has_more: true`和
  `limit=2`（恰好是历史的长度）`has_more: false`； 功能分支的历史记录包括它自己的提交； 0和201是422。
- **一次提交的文件 (`F15.commit-changes`)。**

  需要：`F15.diff-commit`
  ```sh
  control-agent-server api GET "/api/git/commits/$C1/changes" --query path="$REPO" --expect 200 --check . len-eq 2 \
    --check 0.status eq ADDED --check 0.path eq README.md --check 1.status eq ADDED --check 1.path eq src/app.py \
    --save F15.commit-changes/root
  control-agent-server api GET "/api/git/commits/$C2/changes" --query path="$REPO" --expect 200 --check . len-eq 1 \
    --check 0.status eq ADDED --check 0.path eq src/util.py --save F15.commit-changes/add-util
  control-agent-server api GET "/api/git/commits/${C2:0:7}/changes" --query path="$REPO" --expect 200 --check 0.path eq src/util.py
  control-agent-server api GET "/api/git/commits/$C3/changes" --query path="$F/hist" --expect 200 --check . len-eq 3 \
    --check 0.status eq DELETED --check 0.path eq src/app.py --check 1.status eq ADDED --check 1.path eq src/main.py \
    --check 2.status eq DELETED --check 2.path eq src/util.py --save F15.commit-changes/delete-rename
  control-agent-server api GET /api/git/commits/deadbeefdeadbeef/changes --query path="$REPO" --expect 400 \
    --check detail contains 'Git command failed' --save F15.commit-changes/unknown
  control-agent-server api GET /api/git/commits/xyz/changes --query path="$REPO" --expect 422 --check detail.0.loc contains sha
  control-agent-server api GET /api/git/commits/abc/changes --query path="$REPO" --expect 422
  control-agent-server api GET "/api/git/commits/$C2/changes" --expect 422 --check detail.0.loc contains path
  ```
  根提交全部为 `ADDED`（与空树不同），`Add util` 添加一个文件，重命名为 `DELETED` 加 `ADDED`（按照 git 的顺序，未重新排序），解析 7 个字符的前缀，未知的 SHA 为 400，非十六进制或 3 字符的 SHA 和缺失的 `path` 为 422。
- **对话范围的视图 (`F15.scoped`)。**四个范围内的路线
  `CID`，逐字节与全局进行比较。
  ```sh
  control-agent-server api GET "/api/conversations/$CID/git/changes" --query path="$REPO" --expect 200 \
    --raw-out "$F/scoped-changes.json" --save F15.scoped/changes
  control-agent-server api GET /api/git/changes --query path="$REPO" --expect 200 --raw-out "$F/global-changes.json"
  cmp "$F/scoped-changes.json" "$F/global-changes.json"
  control-agent-server api GET "/api/conversations/$CID/git/diff" --query path="$REPO/README.md" --expect 200 \
    --raw-out "$F/scoped-diff.json" --save F15.scoped/diff
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --expect 200 --raw-out "$F/global-diff.json"
  cmp "$F/scoped-diff.json" "$F/global-diff.json"
  control-agent-server api GET "/api/conversations/$CID/git/commits" --query path="$REPO" --expect 200 \
    --raw-out "$F/scoped-commits.json" --save F15.scoped/commits
  control-agent-server api GET /api/git/commits --query path="$REPO" --expect 200 --raw-out "$F/global-commits.json"
  cmp "$F/scoped-commits.json" "$F/global-commits.json"
  control-agent-server api GET "/api/conversations/$CID/git/commits/$C2/changes" --query path="$REPO" --expect 200 \
    --check 0.path eq src/util.py --save F15.scoped/commit-changes
  control-agent-server api GET "/api/conversations/$CID/git/diff" --query path="$REPO/src/util.py" --query commit="$C2" \
    --expect 200 --check original eq ''
  ```
  更改、差异和提交的相同主体。 scoped commit changes 和 commit-mode diff 工作方式相同。
- **工作区守卫(`F15.scoped-guard`).**第二次从未进行过的对话
  `CID2` 在副本上，因此符号链接不在主测试夹具之外。 工作区本身首先回答（阳性对照），然后是每次逃逸。
  ```sh
  cp -r "$REPO" "$F/guard"
  cp -r "$REPO" "$F/guard-sibling"
  CID2=$(control-agent-server conversation start --workspace "$F/guard" --tools none --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$F/guard" --expect 200 --check . len-eq 2 \
    --check 0.path eq README.md --check 1.path eq notes.txt --save F15.scoped-guard/workspace
  control-agent-server api GET "/api/conversations/$CID2/git/diff" --query path="$F/guard/README.md" --expect 200 \
    --check modified eq "$(cat "$F/guard/README.md")"
  ln -s "$REPO" "$F/guard/qa-escape"
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$REPO" --expect 422 \
    --check detail eq 'path must be inside the conversation workspace' --save F15.scoped-guard/other-dir
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$F/guard-sibling" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$F/guard/../outer" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$F/guard/qa-escape" --expect 422 \
    --check detail eq 'path must be inside the conversation workspace' --save F15.scoped-guard/symlink
  control-agent-server api GET "/api/conversations/$CID2/git/diff" --query path="$F/guard/qa-escape/README.md" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/git/diff" --query path=README.md --expect 422
  control-agent-server api GET "/api/conversations/$CID2/git/changes" --query path="$F/guard" --query path="$REPO" --expect 422 \
    --check detail eq 'path must be inside the conversation workspace' --save F15.scoped-guard/duplicate-path
  control-agent-server api GET "/api/conversations/$CID2/git/commits" --query path="$REPO" --expect 422
  control-agent-server api GET "/api/conversations/$CID2/git/commits/$C2/changes" --query path="$REPO" --expect 422
  control-agent-server api GET /api/git/changes --query path="$F/guard/qa-escape" --expect 200 --check . len-eq 2
  control-agent-server api GET /api/conversations/00000000-0000-4000-8000-000000000000/git/changes --query path="$REPO" \
    --expect 404 --check detail contains 'Conversation not found' --save F15.scoped-guard/unknown-conversation
  control-agent-server api GET /api/conversations/not-a-uuid/git/changes --query path="$REPO" --expect 422
  control-agent-server api GET /openapi.json --auth none --expect 200 --quiet \
    --check 'paths./api/git/repositories/search' exists \
    --check 'paths./api/conversations/{runtime_conversation_id}/git/changes' exists \
    --check 'paths./api/conversations/{runtime_conversation_id}/git/repositories/search' missing
  ```
  的工作区文件中有200个。 另一个目录，与共享的目录兄弟工作区将名字作为前缀`guard-sibling`), a `..` 逃逸、一个符号链接，其位置在工作区却指向其外部（例如 `path` 以及它下面的文件），还有相对路径，全都
  `422 {"detail": "path must be inside the conversation workspace"}` 在每个作用域路由上，而全局路由遵循相同的符号链接。 重复的一个
  `path` (the) 工作区首先，然后是另一个外部仓库）也返回 422：守卫和处理器都读取了最后一个值，因此守卫无法通过发送第二个来绕过 `path`. 未知对话 404，非法ID 422，仓库搜索没有分页变体： OpenAPI 文档列出了全局搜索和受控搜索
  `changes` 但没有范围搜索路径。
- **重新启动后 (`F15.scoped-restart`)。**
  ```sh
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$CID/git/changes" --query path="$REPO" --expect 200 \
    --raw-out "$F/scoped-changes-restarted.json" --save F15.scoped-restart/changes
  cmp "$F/scoped-changes.json" "$F/scoped-changes-restarted.json"
  control-agent-server api GET "/api/conversations/$CID/git/commits" --query path="$REPO" --expect 200 --check commits.0.sha eq "$C2"
  control-agent-server doctor
  ```
  恢复的对话仍然绑定着工作区。 scoped更改与重启前的相同。
- **PythonSDK工作区(`F15.sdk-workspace`).** `RemoteWorkspace` 与
  `working_dir` 设置为测试夹具，一次是普通的，一次范围是 `CID` (`runtime_conversation_id`)，直到 `exec`。
  ```sh
  cat > "$F/sdk_git.py" <<'PY'
  import os
  import sys
  from uuid import UUID

  import httpx

  from openhands.sdk.workspace.remote.base import RemoteWorkspace

  repo, cid = sys.argv[1], sys.argv[2]
  host, key = os.environ["AGENT_SERVER_URL"], os.environ["SESSION_API_KEY"]
  plain = RemoteWorkspace(host=host, api_key=key, working_dir=repo)
  scoped = RemoteWorkspace(host=host, api_key=key, working_dir=repo, runtime_conversation_id=UUID(cid))
  for ws in (plain, scoped):
      changes = [(c.status.value, c.path.as_posix()) for c in ws.git_changes(".")]
      assert changes == [("UPDATED", "README.md"), ("ADDED", "notes.txt")], changes
      diff = ws.git_diff("README.md")
      assert diff.original == "# QA fixture repo\n\nCreated by control-agent-server.", diff
      assert diff.modified == "# QA fixture repo\n\nModified, not committed.", diff
  try:
      scoped.git_changes("/")
  except httpx.HTTPStatusError as e:
      assert e.response.status_code == 422, e
  else:
      raise AssertionError("scoped git_changes('/') was not refused")
  print("SDK_GIT_OK")
  PY
  control-agent-server exec --expect-output SDK_GIT_OK --save F15.sdk-workspace/program -- uv run python "$F/sdk_git.py" "$REPO" "$CID"
  ```
  相对路径 (`"."`, `"README.md"`) are joined to `working_dir` 在调用之前，两者工作区返回测试夹具的两个变化和 README diff，以及带有范围的版本会引发 422 错误 `HTTPStatusError` 为了 `/`.
- **TypeScript 客户端 (`F15.ts-client`).** `RemoteWorkspace.gitChanges` 和
  `gitDiff` 普通且带有 `conversationId`，并且
  `GitClient.searchRepositories`，来自内置客户端
  `clients/typescript/dist`（缺失时在此构建）。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  cat > "$F/ts_git.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const dist = (name) => pathToFileURL(resolve('clients/typescript/dist', name)).href;
  const { RemoteWorkspace } = await import(dist('index.js'));
  const { GitClient } = await import(dist('clients.js'));
  const [repo, cid, c1] = process.argv.slice(2);
  const host = process.env.AGENT_SERVER_URL;
  const apiKey = process.env.SESSION_API_KEY;
  for (const conversationId of [undefined, cid]) {
    const ws = new RemoteWorkspace({ host, apiKey, workingDir: repo, conversationId });
    assert.deepEqual(await ws.gitChanges(repo), [
      { status: 'UPDATED', path: 'README.md' },
      { status: 'ADDED', path: 'notes.txt' },
    ]);
    assert.deepEqual(await ws.gitChanges(repo, { ref: c1 }), [
      { status: 'UPDATED', path: 'README.md' },
      { status: 'ADDED', path: 'notes.txt' },
      { status: 'ADDED', path: 'src/util.py' },
    ]);
    const diff = await ws.gitDiff(`${repo}/README.md`);
    assert.equal(diff.modified, '# QA fixture repo\n\nModified, not committed.');
  }
  const scoped = new RemoteWorkspace({ host, apiKey, workingDir: repo, conversationId: cid });
  await assert.rejects(scoped.gitChanges('/'), /422|inside the conversation workspace/);
  const page = await new GitClient({ host, apiKey }).searchRepositories({ provider: 'github' });
  assert.deepEqual(page, { items: [], next_page_id: null, missing_token: true });
  console.log('TS_GIT_OK');
  JS
  control-agent-server exec --expect-output TS_GIT_OK --save F15.ts-client/program -- node "$F/ts_git.mjs" "$REPO" "$CID" "$C1"
  ```
  两者工作区返回相同的变化和差异。 `ref: C1` 它会通过（它添加） `src/util.py`, 默认的基底 `HEAD` 没有显示，因此已丢弃 `ref` 如果失败，则受控的拒绝 `/` 并且
  `searchRepositories` 返回 `missing_token` 页（此时尚未存储 token）。
- **智能体改变了什么 (`F15.agent-changes`)。**真实模型在测试夹具的新副本中写入一个文件，然后范围视图显示它。
  ```sh
  AREPO=$(control-agent-server fixture git-repo --name qa-f15-agent-repo --print-path)
  ACID=$(control-agent-server conversation start --workspace "$AREPO" --tools file_editor --no-autotitle \
    --prompt 'Use the file_editor tool to create the file qa-f15-agent.txt in the current working directory containing exactly: hi' \
    --wait --until finished --timeout 300 --print-id)
  control-agent-server conversation events "$ACID" --kinds ObservationEvent --contains qa-f15-agent.txt --expect-kind ObservationEvent
  control-agent-server api GET "/api/conversations/$ACID/git/changes" --query path="$AREPO" --expect 200 --check . len-eq 3 \
    --check 2.status eq ADDED --check 2.path eq qa-f15-agent.txt --save F15.agent-changes/changes
  control-agent-server api GET "/api/conversations/$ACID/git/diff" --query path="$AREPO/qa-f15-agent.txt" --expect 200 \
    --check original eq '' --check modified eq hi --save F15.agent-changes/diff
  ```
  文件编辑器观测结果为文件命名。 `changes`补充道
  `ADDED qa-f15-agent.txt` 在测试夹具的两个条目之后，其差异为
  `""` 反对 `hi`。
- **token查找(`F15.repo-search-token`).**没有 token，然后是两个接受的机密名称中的每一个。 在没有网络的情况下观察到 token 的存在：
  仅当找到 token 后才会解析 `page_id`。
  ```sh
  control-agent-server api GET /api/git/repositories/search --query provider=github --expect 200 \
    --check items len-eq 0 --check next_page_id eq null --check missing_token eq true --save F15.repo-search-token/none
  control-agent-server api GET /api/git/repositories/search --query provider=github --query page_id=abc --expect 200 \
    --check missing_token eq true
  control-agent-server api PUT /api/settings/secrets --json '{"name": "github_token", "value": "qa-f15-not-a-real-token"}' --expect 200
  control-agent-server api GET /api/git/repositories/search --query provider=github --query page_id=abc --expect 400 \
    --check detail eq 'Invalid repository page_id' --save F15.repo-search-token/github-token
  control-agent-server api GET /api/git/repositories/search --query provider=github --query page_id=1:-1 --expect 400
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  control-agent-server api PUT /api/settings/secrets --json '{"name": "GH_TOKEN", "value": "qa-f15-not-a-real-token"}' --expect 200
  control-agent-server api GET /api/git/repositories/search --query provider=github --query page_id=0 --expect 400 \
    --check detail eq 'Invalid repository page_id' --save F15.repo-search-token/gh-token
  control-agent-server api DELETE /api/settings/secrets/GH_TOKEN --expect 200
  control-agent-server api GET /api/git/repositories/search --query provider=github --query page_id=abc --expect 200 \
    --check missing_token eq true --save F15.repo-search-token/deleted
  ```
  没有 token，答案是 `missing_token: true`，垃圾 `page_id` 被忽略。 `github_token` 或 `GH_TOKEN` 存储的 `page_id` 是 400（没有请求到达 GitHub）。 删除之后，它又变成了`missing_token`。
- **提供者和参数验证 (`F15.repo-search-errors`).**
  ```sh
  control-agent-server api GET /api/git/repositories/search --query provider=gitlab --expect 400 \
    --check detail eq "Repository discovery is not supported for provider 'gitlab'" --save F15.repo-search-errors/gitlab
  control-agent-server api GET /api/git/repositories/search --query provider=bitbucket --expect 400
  control-agent-server api GET /api/git/repositories/search --query provider=qa-nope --expect 422 --check detail.0.loc contains provider
  control-agent-server api GET /api/git/repositories/search --expect 422 --check detail.0.loc contains provider
  control-agent-server api GET /api/git/repositories/search --query provider=github --query limit=0 --expect 422
  control-agent-server api GET /api/git/repositories/search --query provider=github --query limit=101 --expect 422
  ```
  `gitlab`和`bitbucket`是未经发现的已知提供者(400)； 未知或缺失的提供商和 `limit` 0 或 101 为 422。
- **GitHub 无法访问（`F15.repo-search-unreachable`）。** 将 token 存储起来，然后用指向关闭端口的 HTTPS 代理重启服务器，这样对任何机器的调用都会在 `api.github.com` 失败。 之后恢复。
  ```sh
  control-agent-server api PUT /api/settings/secrets --json '{"name": "github_token", "value": "qa-f15-not-a-real-token"}' --expect 200
  control-agent-server restart --env HTTPS_PROXY=http://127.0.0.1:9 --env https_proxy=http://127.0.0.1:9 \
    --env NO_PROXY=localhost --env no_proxy=localhost
  control-agent-server api GET /api/git/repositories/search --query provider=github --expect 502 \
    --check detail eq 'Internal Server Error' --check exception eq '502: GitHub repository search failed' \
    --check . not-contains qa-f15-not-a-real-token --save F15.repo-search-unreachable/dead-proxy
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  control-agent-server restart --reset-config
  control-agent-server api GET /api/git/repositories/search --query provider=github --expect 200 --check missing_token eq true
  control-agent-server doctor
  ```
  502 由于服务器的5xx头部被隐藏 (`{"detail": "Internal Server Error", "exception": "502: GitHub repository search failed"}`, without the token. `restart --reset-config` 再次丢弃了死代理（运行没有失去的启动标志），搜索又回到了这里
  `missing_token` 一旦机密被删除。
- **GitHub  超时 (`F15.repo-search-timeout`).** 一个本地监听器，接受连接但从不回应，代表了  HTTPS proxy，所以调用 GitHub 击中服务器的自身 15 秒超时 (定时器在测试中，所以子弹测量等待时间) 监听器是普通的 `python3`在后台启动，在结束时被杀死。
  ```sh
  python3 -c 'import socket, time; s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(8); print(s.getsockname()[1], flush=True); time.sleep(90)' \
    > "$F/hang-port" 2>/dev/null < /dev/null &
  HANG_PID=$!
  for i in $(seq 50); do test -s "$F/hang-port" && break; sleep 0.1; done
  HANG="http://127.0.0.1:$(cat "$F/hang-port")"
  control-agent-server api PUT /api/settings/secrets --json '{"name": "github_token", "value": "qa-f15-not-a-real-token"}' --expect 200
  control-agent-server restart --env HTTPS_PROXY="$HANG" --env https_proxy="$HANG" --env NO_PROXY=localhost --env no_proxy=localhost
  T0=$SECONDS
  control-agent-server api GET /api/git/repositories/search --query provider=github --expect 504 --expect-max-ms 30000 \
    --check detail eq 'Internal Server Error' --check exception eq '504: GitHub repository search timed out' \
    --check . not-contains qa-f15-not-a-real-token --save F15.repo-search-timeout/silent-proxy
  test $((SECONDS - T0)) -ge 14
  kill "$HANG_PID"
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  control-agent-server restart --reset-config
  control-agent-server doctor
  ```
  大约15秒后（14到30之间），带有掩码的5xx主体
  `{"detail": "Internal Server Error", "exception": "504: GitHub repository search timed out"}` 中没有 token。
- **实时GitHub列表(`F15.repo-search-github`)。**
  需求：`network`

  将 `$QA_GITHUB_TOKEN` 设置为 GitHub token，对至少​​三个存储库具有读取权限，其中包括一个名为 `agent-sdk` 的存储库。 出口必须允许
  `GET https://api.github.com/user/repos`. token 通过 stdin 传输； 命令范围的 `OPENHANDS_API_KEY` 还向 CLI 的编辑器注册该值，因此交换和失败都不会打印它。 这个菜谱只有GitHub； 它的设置写入在拥有的本地运行上。
  ```sh
  : "${QA_GITHUB_TOKEN:?Set a repository-read token before running this recipe}"
  trap 'control-agent-server api DELETE /api/settings/secrets/github_token --expect 200 >/dev/null 2>&1 || true' EXIT
  python3 -c 'import json, os; print(json.dumps({"name":"github_token","value":os.environ["QA_GITHUB_TOKEN"]}))' \
    | env OPENHANDS_API_KEY="$QA_GITHUB_TOKEN" control-agent-server api PUT /api/settings/secrets --stdin --expect 200 --quiet
  NEXT=$(control-agent-server api GET /api/git/repositories/search --query provider=github --query limit=2 --expect 200 \
    --check missing_token eq false --check items len-eq 2 --check items.0.git_provider eq github \
    --check next_page_id eq 1:2 --save F15.repo-search-github/page-1 --field next_page_id)
  control-agent-server api GET /api/git/repositories/search --query provider=github --query limit=2 --query page_id="$NEXT" \
    --expect 200 --check items len-ge 1 --save F15.repo-search-github/page-2
  control-agent-server api GET /api/git/repositories/search --query provider=github --query query=AGENT-SDK --query limit=5 \
    --expect 200 --check items.0.full_name matches '(?i)agent-sdk'
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  trap - EXIT
  ```
  每页有两个仓库，带有`1:2`游标（第1页，偏移量2），继续列出，并且是不区分大小写的`query`匹配`full_name`。 一些管理的出口代理在请求提供无效的 token 时仍然注入凭据。 使用以下确定性提供者拒绝来独立证明服务器的401行为，不受该环境策略的影响。
- **拒绝的提供商 token (`F15.repo-search-rejected-token`).**本地 TLS 测试夹具通过拥有的 CONNECT 代理接收服务器的 GitHub 请求并返回提供者 401。 它从不接触GitHub并且只使用假的token； 上述秘方证明了真正提供商的成功之路。
  ```sh
  cat > "$F/reject-github.py" <<'PY'
  import datetime, json, pathlib, socketserver, ssl, sys
  from cryptography import x509
  from cryptography.hazmat.primitives import hashes, serialization
  from cryptography.hazmat.primitives.asymmetric import rsa
  from cryptography.x509.oid import NameOID
  root = pathlib.Path(sys.argv[1])
  key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
  name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'api.github.com')])
  now = datetime.datetime.now(datetime.timezone.utc)
  cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
      .public_key(key.public_key()).serial_number(x509.random_serial_number())
      .not_valid_before(now - datetime.timedelta(minutes=1))
      .not_valid_after(now + datetime.timedelta(days=1))
      .add_extension(x509.SubjectAlternativeName([x509.DNSName('api.github.com')]), critical=False)
      .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
      .sign(key, hashes.SHA256()))
  (root / 'reject-cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
  (root / 'reject-key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
      serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
  context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
  context.load_cert_chain(root / 'reject-cert.pem', root / 'reject-key.pem')
  def headers(conn):
      value = b''
      while b'\r\n\r\n' not in value:
          chunk = conn.recv(4096)
          if not chunk: raise ConnectionError('incomplete request')
          value += chunk
      return value.decode('latin1')
  class Handler(socketserver.BaseRequestHandler):
      def handle(self):
          if not headers(self.request).startswith('CONNECT api.github.com:443 '):
              self.request.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
              return
          self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
          with context.wrap_socket(self.request, server_side=True) as conn:
              request = headers(conn)
              assert request.startswith('GET /user/repos?')
              assert 'authorization: bearer qa-f15-rejected-token' in request.lower()
              (root / 'reject-observed.json').write_text(json.dumps({'request': 'GET /user/repos', 'fake_token_received': True, 'returned_status': 401}))
              body = b'{"message":"Bad credentials"}'
              conn.sendall(b'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
  with socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler) as server:
      (root / 'reject-port').write_text(str(server.server_address[1]))
      server.serve_forever()
  PY
  uv run --quiet python "$F/reject-github.py" "$F" > "$F/reject-log" 2>&1 &
  REJECT_PID=$!
  trap 'kill "$REJECT_PID" 2>/dev/null || true; control-agent-server api DELETE /api/settings/secrets/github_token --expect 200 >/dev/null 2>&1 || true; control-agent-server restart --reset-config >/dev/null 2>&1 || true' EXIT
  for i in $(seq 1 100); do test -s "$F/reject-port" && break; sleep 0.1; done
  REJECT_PROXY="http://127.0.0.1:$(cat "$F/reject-port")"
  control-agent-server api PUT /api/settings/secrets --json '{"name":"github_token","value":"qa-f15-rejected-token"}' --expect 200
  control-agent-server restart --env HTTPS_PROXY="$REJECT_PROXY" --env https_proxy="$REJECT_PROXY" \
    --env HTTP_PROXY="$REJECT_PROXY" --env http_proxy="$REJECT_PROXY" \
    --env "SSL_CERT_FILE=$F/reject-cert.pem" --env NO_PROXY=localhost,127.0.0.1 --env no_proxy=localhost,127.0.0.1
  control-agent-server doctor
  control-agent-server api GET /api/git/repositories/search --query provider=github --expect 401 \
    --check detail eq 'GitHub repository search failed' --check . not-contains qa-f15-rejected-token --save F15.repo-search-rejected-token/rejected
  control-agent-server assert --json "$F/reject-observed.json" --check request eq 'GET /user/repos' \
    --check fake_token_received eq true --check returned_status eq 401
  cp "$F/reject-observed.json" "$AGENT_SERVER_VERIFY_RUN/evidence/F15.repo-search-rejected-token/provider.json"
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  kill "$REJECT_PID"
  wait "$REJECT_PID" || true
  control-agent-server restart --reset-config
  control-agent-server doctor
  trap - EXIT
  ```
  测试夹具确认伪造的凭据已经到达提供者，并且返回了 401。 活服务器保留了该状态，并只返回通用错误。 源策略还保留了403状态码，将其他4xx状态码映射为400状态码，将5xx状态码映射为502状态码。 连接失败和超时已在上面覆盖。

<a id="gotchas"></a>

## 陷阱

- 不带 `ref` 的 `changes` 和 `diff` 使用 *display* 基本策略 (`get_valid_ref(..., purpose="display")`)，该策略与 `GET /api/file/archive` (`git-delta`) 的 *export* 策略不同：在无远程测试夹具上，“更改”选项卡与 `HEAD` 进行比较，而存档补丁与空树进行比较。 不要指望他们会同意。
- 具有 `origin` 但没有 `origin/HEAD` 的存储库会运行基本检测
  `git remote show origin`，一个 30 秒的网络调用超时。 使用无远程测试夹具或使用 `git clone` 克隆的本地裸远程（记录 `origin/HEAD`），如 `F15.changes-base` 那样。
- 非仓库 `path` 这不是错误。 `changes` 是 `[]` 除非一个仓库直接位于其下方，否则请忽略此仓库 `F15.changes-repo-below-path`), 没有提交 `diff` 是 `{"original": null, "modified": null}` (null, not `""`). 仓库中缺少的文件返回 400，超过 1 的文件也返回 400 MiB.
- “不是存储库”意味着没有祖先拥有 `.git`：git 向上搜索，`diff` 在 Python 中向上走。 运行主目录上方的杂散 `.git`（例如，在 `/tmp` 中运行的 `git init`）将每个测试夹具变成该存储库的一部分：`F15.non-repo` 然后将 `x.txt` 列为 `ADDED` 并
  `F15.changes-repo-below-path` 因错误原因而通过。 先决条件块拒绝这样的运行； 启动与
  `AGENT_SERVER_VERIFY_HOME` 位于封闭存储库之外（例如在 `/var/tmp` 下），或者让其所有者删除杂散的 `.git`。
- 全局路由上的相对 `path` 根据服务器进程的工作目录（`launch` 的运行目录）进行解析； 始终发送绝对路径。 SDK 在调用之前连接到 `working_dir` 的相对路径。
- diff 双方都删除了最后的换行符，并且行结尾被标准化（`\r\n` 变为 `\n`，因此唯一更改为 LF 到 CRLF 的文件被列为
  `UPDATED` 但与相同的边不同）。 其他前导和尾随空白保留在两侧 (`F15.diff-whitespace`)； 提交模式差异将其从两者中剥离。
- 存储库内的目录上的 `diff` 不会被拒绝：它会返回
  `git show` 的树列表 (`"tree <sha>:src\n\napp.py\nutil.py"`) 为
  `original` 和 `""` 为 `modified`。
- 嵌套存储库仅扫描 `path` (`./*/.git`) 以下一级，无论 `path` 本身是否是存储库； 更深的目录显示为未跟踪的目录条目（或者根本不在非存储库 `path` 之下）。
- `commits/{sha}/changes` 保持 git 的输出顺序（重命名为
  `DELETED`+`ADDED`对），与`changes`不同，它是按路径排序的。
- Git调用reset`idle_time`(`update_last_execution_time`)，就像文件操作一样； 参见`F01.idle-time`。
- 存储库搜索不是本地目录扫描：它需要服务器的机密存储中的 GitHub token（使用 `OH_SECRET_KEY` 加密）并调用
  `https://api.github.com/user/repos`通过服务器自带的代理环境。 仅当 token 存在时，垃圾 `page_id` 才会被拒绝。 GitHub状态：401和403通过，其他4xx是400、5xx和传输层错误502（屏蔽为`Internal Server Error`，原因在
  `exception`), a 超时 504.
- `restart --env` 值持久化用于稍后重新启动运行； 像 `F15.repo-search-unreachable` 一样用 `restart --reset-config` 清除它们（这也会删除 `Launch:` 标志，该系列有 None 个标志）。
