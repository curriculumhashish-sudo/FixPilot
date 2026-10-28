<a id="workspace-registry-and-parents"></a>

# 工作区注册表和家长

服务器保留了用户的工作区（Agent Canvas 提供的目录]）和工作区父目录（工作区提供的子目录作为候选工作区）的列表，因此每个服务器客户端看到的列表是相同的，而不是每个浏览器都保存自己的。 两个列表都位于一个 JSON 文档中，`workspaces.json` 位于持久化目录中，在文件锁下自动重写。 添加是幂等的`path`，删除是精确的`path`（没有匹配时为404），有线格式是camelCase（`workspaceParents`，`parentPath`）。 服务器无法解析的文件或由更新的文件模式编写的文件永远不会被覆盖：每条路由都会回答 409。 注册表不发出事件，Webhook 也不发出事件。

资料来源：`openhands-agent-server/openhands/agent_server/workspaces_router.py`、`openhands-agent-server/openhands/agent_server/persistence/models.py`、`openhands-agent-server/openhands/agent_server/persistence/store.py`、`openhands-sdk/openhands/sdk/utils/path.py`、`clients/typescript/src/client/workspaces-client.ts`

需求：`git`、`node`

路线：`GET /api/workspaces`、`POST /api/workspaces`、`DELETE /api/workspaces`、
`POST /api/workspaces/parents`, `DELETE /api/workspaces/parents`

<a id="sub-features"></a>

## 子功能

- `F17.list-empty`：在新的持久化目录上，`GET /api/workspaces` 返回 `{"workspaces": [], "workspaceParents": []}` 并且不创建 `workspaces.json`。
- `F17.noop-delete-no-file`：在新的持久化目录上，从任一列表中删除路径都会回答 404 并且不创建 `workspaces.json`，就像读取一样。
- `F17.add-workspaces`: `POST /api/workspaces` 按请求顺序注册一个 git 存储库和一个普通目录，并回答整个文档； `GET`和`workspaces.json`（模式`0600`、`schema_version`1）显示相同的条目。
- `F17.wire-format`：请求采用`parentPath`或`parent_path`； 响应和文件使用 `parentPath` 和 `workspaceParents`，省略未设置的 `parentPath` 而不是 `null`，并且删除未知项字段。
- `F17.idempotent-add` 重复注册的路径，或在一个请求体中重复同一个路径，返回 200 状态码，并保留一个条目，即第一条，保留其原始 `id` 和 `name`。
- `F17.delete-workspace`：`DELETE /api/workspaces?path=` 回答 `{"deleted": true}` 并仅从列表和文件中删除该条目，保持其他条目的顺序。
- `F17.delete-not-found`：删除未保存的路径工作区（已删除的路径，或带有尾部斜杠的险些错过的路径）是404 `Workspace not found`并且没有任何改变； 没有 `path` 的删除是 422。
- `F17.noop-write-untouched`：不更改任何内容的写入（重新发布已保存的工作区，删除未知的工作区或父级）使 `workspaces.json` 保持原样，具有相同的 inode 和修改时间。
- `F17.paths-opaque`：路径存储为给定的，不进行存在检查或规范化：缺失的目录和相对路径被接受，`/x` 和 `/x/` 是分别删除的两个条目，带有空格的路径，`&`、`?`、`#` 或非ASCII 字母的路径通过编码删除查询进行圆周运动。
- `F17.validation`没有`workspaces`或`parents`，一个非列表，一个缺少或空的`id`，`name`或`path`，或者超出其限制的字段（名称256，ID，路径和`parentPath`4096）返回422状态，并存储了空值，甚至没有相同体的合法项目。 极限值被接受。
- `F17.add-parents`：`POST /api/workspaces/parents` 注册父级，由 `path` 进行重复数据删除，如工作区，回答整个文档并保持 `workspaces` 不变。
- `F17.parent-children`：注册父目录会注册其子目录的None； 选择器会用 `GET /api/file/search_subdirs` 列出它们，只有在将 `parentPath` 设置为父项的情况下发布子项后，子项才会出现在 `workspaces` 中。
- `F17.delete-parent`：`DELETE /api/workspaces/parents?path=`回答`{"deleted": true}`并仅删除父级：其子级工作区与`parentPath`一起保留在列表中； 第二次删除是 404 `Workspace parent not found`，缺失的 `path` 422。
- `F17.lists-independent`：一条路径可以同时是工作区和父路径； 每个删除路由仅查看自己的列表（404 表示仅在另一个中的路径），并从一个删除离开另一个。
- `F17.persist-restart`：服务器重新启动后，两个列表按顺序和每个字段以相同的方式读回。
- `F17.auth-required`：配置会话密钥后，在验证请求之前，所有五个路由都会对丢失或错误的 `X-Session-API-Key` 做出 401 响应，并且不进行任何更改。
- `F17.concurrent-adds`：不同工作区的并行 `POST` 和一台服务器的父级全部土地，并且所有并行 `DELETE` 均适用。
- `F17.shared-dir`两个服务器在一个地方持久化目录共享注册表每个请求都会看到对方的写入（没有缓存），并行添加和删除在两个服务器上都发生（这些操作都发生在下一个请求中） `.workspaces.lock` 文件锁跨进程序列化它们。
- `F17.ts-client`：TypeScript`WorkspacesClient`通过这些路由列出、添加和删除工作区和父级，其未知路径的删除会被服务器的404拒绝。
- `F17.corrupted-file`：具有不可解析或空的 `workspaces.json`，所有五个路由均应答 409 `Workspaces file is corrupted` 并逐字节保留文件； 恢复文件会恢复列表。
- `F17.future-schema`：一个有效的文档，`schema_version` 更新时间大于1，或者不是整数，或者列表拼写错误，读写时返回409，并且不会被覆盖； 读取没有`schema_version`的同类手写文档，下一个写入标记`schema_version` 1。
- `F17.io-error`：当文件无法读取（文件夹取代）时，每条路由都会返回 500，并命名为失败步骤（`exception`、`Failed to read workspaces`、`Failed to save workspaces`、`Failed to update workspaces`），什么都不写，并且注册表会重新工作。
- `F17.noop-write-readonly`在持久化服务器无法写入的目录 `GET` 返回200，返回真实值500 `Failed to save workspaces`然而，一个不改变任何内容的写入仍然保持其正常答案：404 对于未知路径，200 对于重新发布。
- `F17.persistence-location`：没有`OH_PERSISTENCE_DIR`，注册表位于`<conversations_path>/../.openhands/workspaces.json` 中，与`OH_PERSISTENCE_DIR` 下的那个分开。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `GET /api/workspaces`（无参数）返回
  `{"workspaces": [{id, name, path, parentPath?}], "workspaceParents": [{id, name, path}]}`.
- REST：`POST /api/workspaces`与`{"workspaces": [{id, name, path, parentPath?}]}`和`POST /api/workspaces/parents`与`{"parents": [{id, name, path}]}`附加并回答整个文档（与`GET`形状相同）。
- REST: `DELETE /api/workspaces?path=...` 和
  `DELETE /api/workspaces/parents?path=...` 按确切路径删除一项并回答 `{"deleted": true}`。
- TypeScript 客户端：`WorkspacesClient`（`clients/typescript/src/client/workspaces-client.ts`）：
  `listWorkspaces()`, `addWorkspaces(items)`, `deleteWorkspace(path)`,
  `addWorkspaceParents(items)`, `deleteWorkspaceParent(path)`. 每个调用首先读取 `/server_info` 并拒绝早于 1.23.0 的服务器。 驱动力
  `F17.ts-client`（`clients/typescript/dist` 上的 `node` 程序）。
- SDK：无Python消费者； `RemoteWorkspace` 不调用这些路由。
- 配置：`OH_PERSISTENCE_DIR`选择目录
  `workspaces.json`; 如果没有它，文件位于对话目录 (`F17.persistence-location`) 旁边。 指向一个目录的服务器共享一个注册表 (`F17.shared-dir`)。
- Agent Canvas：工作区选择器读取并编辑这些列表，并提供 `GET /api/file/search_subdirs` 中每个父目录的子目录（仅限上下文； 该路由属于文件系列，此处用作第二个视图）。
- 配方：每颗子弹都用`api`调用路线； `state cat` 读取存储的文件，`stat` 标记它以防止重写，内容相同，`chattr +i` 用纯shell重写或替换它（或API 冻结其目录）以达到损坏、未来的不可读和模式状态，没有任何只读调用可以产生。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行处于实时状态并已导出 (`launch --new`)，`doctor` 正常，并且尚未触及 `/api/workspaces`（`F17.list-empty` 需要一个新的持久化目录，`F17.noop-delete-no-file` 也需要）。 不需要 LLM 配置文件。 `git`（对于存储库测试夹具）和 `node`（对于
  `F17.ts-client`) 在 `PATH` 上； TypeScript 客户端已构建，如果
  `clients/typescript/dist` 缺失（`npm ci` 则需要 npm 注册表）。 `F17.noop-write-readonly` 运行 `chattr +i`，因此它需要 root 和具有不可变属性的文件系统。
- 下面的块创建了一个 git 仓库 (`REPO`), 一个普通的目录 (`PLAIN`), 和一个包含两个子目录的父目录 (`PARENT`), 写入了那些运行特定路径的请求体，并且 TypeScript 个程序。 `WS`是运行的`OH_PERSISTENCE_DIR`下存储的文件。
- 项目符号按顺序运行并建立在彼此的列表上； 每个都说明它留下的列表。 `F17.persist-restart`和`F17.persistence-location`重新启动运行； 最后一个恢复启动环境。 `F17.shared-dir` 在此运行的持久化目录中启动第二个服务器并将其停止。

  ```sh
  F17="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f17"
  PLAIN="$F17/plain"
  PARENT="$F17/parent"
  WS="$AGENT_SERVER_VERIFY_RUN/home/.openhands/workspaces.json"
  mkdir -p "$PLAIN" "$PARENT/alpha" "$PARENT/beta"
  REPO=$(control-agent-server fixture git-repo --name qa-f17-repo --print-path)
  test -d "$REPO/.git"
  cat > "$F17/add.json" <<EOF
  {"workspaces": [
    {"id": "$REPO", "name": "qa-f17-repo", "path": "$REPO"},
    {"id": "$PLAIN", "name": "qa-f17-plain", "path": "$PLAIN"}
  ]}
  EOF
  cat > "$F17/readd.json" <<EOF
  {"workspaces": [
    {"id": "qa-f17-other-id", "name": "qa-f17-renamed", "path": "$REPO"},
    {"id": "/qa-f17/dup", "name": "qa-f17-dup-first", "path": "/qa-f17/dup"},
    {"id": "qa-f17-dup-second", "name": "qa-f17-dup-second", "path": "/qa-f17/dup"}
  ]}
  EOF
  cat > "$F17/parents.json" <<EOF
  {"parents": [
    {"id": "$PARENT", "name": "qa-f17-parent", "path": "$PARENT"},
    {"id": "qa-f17-parent-dup", "name": "qa-f17-parent-dup", "path": "$PARENT"},
    {"id": "/qa-f17/other-parent", "name": "qa-f17-other-parent", "path": "/qa-f17/other-parent"}
  ]}
  EOF
  cat > "$F17/child.json" <<EOF
  {"workspaces": [{"id": "$PARENT/alpha", "name": "alpha", "path": "$PARENT/alpha", "parentPath": "$PARENT"}]}
  EOF
  cat > "$F17/plain-parent.json" <<EOF
  {"parents": [{"id": "$PLAIN", "name": "qa-f17-plain", "path": "$PLAIN"}]}
  EOF
  cat > "$F17/ts_workspaces.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { WorkspacesClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new WorkspacesClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const before = await client.listWorkspaces();
  const item = { id: '/qa-f17/ts', name: 'qa-f17-ts', path: '/qa-f17/ts', parentPath: '/qa-f17/ts-parent' };
  const added = await client.addWorkspaces([item]);
  assert.equal(added.workspaces.length, before.workspaces.length + 1);
  assert.deepEqual(added.workspaces.at(-1), item);
  const again = await client.addWorkspaces([{ ...item, name: 'qa-f17-ts-renamed' }]);
  assert.deepEqual(again.workspaces.at(-1), item);
  const parent = { id: '/qa-f17/ts-parent', name: 'qa-f17-ts-parent', path: '/qa-f17/ts-parent' };
  const withParent = await client.addWorkspaceParents([parent]);
  assert.deepEqual(withParent.workspaceParents.at(-1), parent);
  assert.equal(withParent.workspaces.length, before.workspaces.length + 1);
  assert.deepEqual(await client.deleteWorkspaceParent(parent.path), { deleted: true });
  assert.deepEqual(await client.deleteWorkspace(item.path), { deleted: true });
  await assert.rejects(client.deleteWorkspace(item.path), (err) => err.status === 404 && err.detail === 'Workspace not found');
  await assert.rejects(client.deleteWorkspaceParent(parent.path), (err) => err.status === 404 && err.detail === 'Workspace parent not found');
  assert.deepEqual(await client.listWorkspaces(), before);
  client.close();
  console.log('QA_F17_TS_OK');
  JS
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  ```

- **空注册表 (`F17.list-empty`).**列出新的持久化目录。
  ```sh
  control-agent-server api GET /api/workspaces --expect 200 \
    --check workspaces len-eq 0 --check workspaceParents len-eq 0 --save F17.list-empty/list
  control-agent-server state ls home/.openhands/workspaces.json --expect-count 0
  ```
  两个列表都为空，读取并未创建文件。
- **拒绝删除新目录 (`F17.noop-delete-no-file`)。**当 `workspaces.json` 尚不存在时，从每个列表中删除未知路径。
  ```sh
  control-agent-server state ls home/.openhands/workspaces.json --expect-count 0
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/never --expect 404 \
    --check detail eq 'Workspace not found' --save F17.noop-delete-no-file/delete
  control-agent-server api DELETE /api/workspaces/parents --query path=/qa-f17/never --expect 404 \
    --check detail eq 'Workspace parent not found'
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 0 --check workspaceParents len-eq 0
  control-agent-server state ls home/.openhands/workspaces.json --expect-count 0
  ```
  两个删除都是404，就像它们前面的读取一样，没有任何影响
  `workspaces.json`（当路由的`apply`返回文档不变时，`FileWorkspacesStore.update`会跳过保存），因此最后一个`state ls`找不到文件。 下一个项目符号的第一个添加将写入它。
- **注册存储库和普通目录 (`F17.add-workspaces`)。**
  ```sh
  control-agent-server api POST /api/workspaces --json-file "$F17/add.json" --expect 200 \
    --check workspaces len-eq 2 --check workspaces.0.path eq "$REPO" --check workspaces.1.path eq "$PLAIN" \
    --check workspaceParents len-eq 0 --save F17.add-workspaces/post
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 2 \
    --check workspaces.0.id eq "$REPO" --check workspaces.0.name eq qa-f17-repo \
    --check workspaces.1.id eq "$PLAIN" --check workspaces.1.name eq qa-f17-plain --save F17.add-workspaces/get
  control-agent-server state cat home/.openhands/workspaces.json --mode 600 --check schema_version eq 1 \
    --check workspaces len-eq 2 --check workspaces.0.path eq "$REPO" --check workspaces.1.path eq "$PLAIN"
  ```
  响应是整个文档。 `GET` 和 `0600` 文件分别包含仓库的第一部分和普通目录的第二部分。 左表：`REPO`，`PLAIN`。
- **接线格式 (`F17.wire-format`).**使用 snake_case 发布一项
  `parent_path`，一个带有 `parentPath`，一个带有 `parentPath: null` 和一个未知字段。
  ```sh
  control-agent-server api POST /api/workspaces --expect 200 --json '{"workspaces": [
      {"id": "/qa-f17/snake", "name": "qa-f17-snake", "path": "/qa-f17/snake", "parent_path": "/qa-f17"},
      {"id": "/qa-f17/camel", "name": "qa-f17-camel", "path": "/qa-f17/camel", "parentPath": "/qa-f17"},
      {"id": "/qa-f17/null", "name": "qa-f17-null", "path": "/qa-f17/null", "parentPath": null, "qa_f17_extra": "x"}]}' \
    --check workspaces len-eq 5 --check workspaces.2.parentPath eq /qa-f17 --check workspaces.3.parentPath eq /qa-f17 \
    --check workspaces.4 not-contains parentPath --check workspaces.4 not-contains qa_f17_extra \
    --check workspaces.0 not-contains parentPath --check . not-contains parent_path --save F17.wire-format/post
  control-agent-server api GET /api/workspaces --check workspaceParents len-eq 0 \
    --check workspaces.2.parentPath eq /qa-f17 --check workspaces.4 not-contains parentPath --save F17.wire-format/get
  control-agent-server state cat home/.openhands/workspaces.json --not-contains parent_path \
    --check workspaceParents len-eq 0 --check workspaces.2.parentPath eq /qa-f17 --check workspaces.4 not-contains parentPath
  ```
  两个拼写都存储`parentPath: "/qa-f17"`； 第三项没有
  `parentPath` 键，无 `qa_f17_extra`，在线路上和磁盘上，其中父项列表存储为 `workspaceParents`。 左侧列表：`REPO`、`PLAIN`、
  `snake`, `camel`, `null`.
- **幂等重新添加 (`F17.idempotent-add`).**将存储库重新发布到另一个 id 和名称下，并在一个正文中两次使用一个新路径； 然后再次发布相同的身体。
  ```sh
  control-agent-server api POST /api/workspaces --json-file "$F17/readd.json" --expect 200 \
    --check workspaces len-eq 6 --check workspaces.0.id eq "$REPO" --check workspaces.0.name eq qa-f17-repo \
    --check workspaces.5.id eq /qa-f17/dup --check workspaces.5.name eq qa-f17-dup-first --save F17.idempotent-add/first
  control-agent-server api POST /api/workspaces --json-file "$F17/readd.json" --expect 200 --check workspaces len-eq 6
  control-agent-server api GET /api/workspaces --check workspaces len-eq 6 \
    --check . not-contains qa-f17-renamed --check . not-contains qa-f17-dup-second --save F17.idempotent-add/get
  ```
  两个帖子都是200，列表增长了一个条目，`/qa-f17/dup`，这是第一个ID和名称。 仓库保留其原始ID和名称。 列表左侧：`REPO`，`PLAIN`，`snake`，`camel`，`null`，`dup`。
- **删除工作区 (`F17.delete-workspace`)。**
  ```sh
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/camel --expect 200 --check deleted eq true \
    --save F17.delete-workspace/delete
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check . not-contains /qa-f17/camel \
    --check workspaces.2.path eq /qa-f17/snake --check workspaces.3.path eq /qa-f17/null \
    --check workspaces.4.path eq /qa-f17/dup --save F17.delete-workspace/get
  control-agent-server state cat home/.openhands/workspaces.json --not-contains /qa-f17/camel --check workspaces len-eq 5
  ```
  答案是b`{"deleted": true}`； 条目从列表、文件和其他地方消失了，而它们的顺序保持不变。 左列表：`REPO`，`PLAIN`,`snake`，
  `null`, `dup`.
- **未知路径 (`F17.delete-not-found`).**再次删除已删除的路径、已保存路径的尾部斜杠变体，并且根本不删除任何路径。
  ```sh
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/camel --expect 404 \
    --check detail eq 'Workspace not found' --save F17.delete-not-found/deleted-twice
  control-agent-server api DELETE /api/workspaces --query "path=$REPO/" --expect 404 --check detail eq 'Workspace not found'
  control-agent-server api DELETE /api/workspaces --expect 422 --check detail.0.type eq missing \
    --check detail.0.loc contains path --save F17.delete-not-found/no-path
  control-agent-server api GET /api/workspaces --check . eq "$BEFORE" --save F17.delete-not-found/unchanged
  ```
  两个删除请求都返回404 `Workspace not found`，裸删请求返回422，并且查询参数 `path` 名称。
- ** 无操作写入会保留文件的原始状态 (`F17.noop-write-untouched`)。** 打上文件戳记（inode和纳秒修改时间），读取，然后重新保存工作区，并从两个列表中删除未知路径。
  ```sh
  STAMP=$(stat -c '%i %y' "$WS")
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 5
  test "$(stat -c '%i %y' "$WS")" = "$STAMP"
  control-agent-server api POST /api/workspaces --json-file "$F17/readd.json" --expect 200 --check workspaces len-eq 5 \
    --check workspaces.0.name eq qa-f17-repo --save F17.noop-write-untouched/readd
  control-agent-server assert --value "$(stat -c '%i %y' "$WS")" --check . eq "$STAMP"
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/never --expect 404
  control-agent-server assert --value "$(stat -c '%i %y' "$WS")" --check . eq "$STAMP"
  control-agent-server api DELETE /api/workspaces/parents --query path=/qa-f17/never --expect 404
  control-agent-server assert --value "$(stat -c '%i %y' "$WS")" --check . eq "$STAMP"
  ```
  读取操作会留下印记，印记显示对比可以成立。 `readd.json`中的每条路径都已经保存了：200，还有五条记录，仓库的名字保持不变。重写会显示为一个新的inode（临时文件重命名）和一个新的mtime，
  with the same content, which is why only the stamp shows it. List left:
  `REPO`, `PLAIN`, `snake`, `null`, `dup`.
- **路径是不透明字符串 (`F17.paths-opaque`)。**注册相对路径以及带有和不带有尾部斜杠的缺失目录。
  ```sh
  control-agent-server api GET /api/file/search_subdirs --query path=/qa-f17/missing --expect 404 --check detail eq 'Directory not found'
  control-agent-server api POST /api/workspaces --expect 200 --json '{"workspaces": [
      {"id": "qa-f17/relative", "name": "qa-f17-relative", "path": "qa-f17/relative"},
      {"id": "/qa-f17/missing/", "name": "qa-f17-missing-slash", "path": "/qa-f17/missing/"},
      {"id": "/qa-f17/missing", "name": "qa-f17-missing", "path": "/qa-f17/missing"}]}' \
    --check workspaces len-eq 8 --check workspaces.5.path eq qa-f17/relative \
    --check workspaces.6.path eq /qa-f17/missing/ --check workspaces.7.path eq /qa-f17/missing --save F17.paths-opaque/post
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/missing --expect 200 --check deleted eq true
  control-agent-server api GET /api/workspaces --check workspaces len-eq 7 --check workspaces.6.path eq /qa-f17/missing/ \
    --save F17.paths-opaque/after-delete
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/missing/ --expect 200
  control-agent-server api DELETE /api/workspaces --query path=qa-f17/relative --expect 200
  control-agent-server api POST /api/workspaces --expect 200 --check workspaces.5.path eq '/qa-f17/with space & ü?#frag' \
    --json '{"workspaces": [{"id": "/qa-f17/with space & ü?#frag", "name": "qa-f17-odd", "path": "/qa-f17/with space & ü?#frag"}]}'
  control-agent-server api DELETE /api/workspaces --query 'path=/qa-f17/with space & ü?#frag' --expect 200 --check deleted eq true \
    --save F17.paths-opaque/odd-characters
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check . not-contains qa-f17/relative \
    --check . not-contains qa-f17-odd
  ```
  服务器自己的目录列表显示`/qa-f17/missing`不存在，但实际上是三个都存在。 删除`/qa-f17/missing`个叶子
  `/qa-f17/missing/`. 包含空格、`&`、`?`、`#` 和非 ASCII 字母的路径将逐字存储并通过 URL 编码查询删除（CLI 编码 `--query`； 不这样做的客户端会删除错误的路径或得到 404）。 项目符号删除了它添加的内容。 左侧列表：`REPO`、`PLAIN`、
  `snake`, `null`, `dup`.
- **验证 (`F17.validation`).**畸形的主体、混合有效和无效项目的主体以及长度限制。
  ```sh
  N256=$(printf 'n%.0s' $(seq 256))
  P4096="/$(printf 'p%.0s' $(seq 4095))"
  control-agent-server api POST /api/workspaces --json '{}' --expect 422 \
    --check detail.0.type eq missing --check detail.0.loc contains workspaces --save F17.validation/no-list
  control-agent-server api POST /api/workspaces --json '{"workspaces": {"id": "/qa-f17/v", "name": "v", "path": "/qa-f17/v"}}' \
    --expect 422 --check detail.0.type eq list_type
  control-agent-server api POST /api/workspaces --expect 422 --json '{"workspaces": [
      {"id": "/qa-f17/batch-valid", "name": "qa-f17-batch-valid", "path": "/qa-f17/batch-valid"},
      {"id": "", "name": "qa-f17-empty-id", "path": "/qa-f17/empty-id"}]}' \
    --check detail.0.type eq string_too_short --check detail.0.loc contains id --save F17.validation/mixed-batch
  control-agent-server api POST /api/workspaces --json '{"workspaces": [{"id": "/qa-f17/v", "path": "/qa-f17/v"}]}' \
    --expect 422 --check detail.0.type eq missing --check detail.0.loc contains name
  control-agent-server api POST /api/workspaces --json '{"workspaces": [{"id": "/qa-f17/v", "name": "", "path": "/qa-f17/v"}]}' \
    --expect 422 --check detail.0.loc contains name
  control-agent-server api POST /api/workspaces --json '{"workspaces": [{"id": "/qa-f17/v", "name": "v", "path": ""}]}' \
    --expect 422 --check detail.0.loc contains path
  control-agent-server api POST /api/workspaces/parents --json '{"workspaces": []}' --expect 422 --check detail.0.loc contains parents
  control-agent-server api POST /api/workspaces/parents --json '{"parents": [{"id": "/qa-f17/v", "name": "v"}]}' \
    --expect 422 --check detail.0.loc contains path
  control-agent-server api POST /api/workspaces --expect 422 --check detail.0.type eq string_too_long --check detail.0.loc contains name \
    --json "{\"workspaces\": [{\"id\": \"/qa-f17/v\", \"name\": \"${N256}n\", \"path\": \"/qa-f17/v\"}]}"
  control-agent-server api POST /api/workspaces --expect 422 --check detail.0.type eq string_too_long --check detail.0.loc contains path \
    --json "{\"workspaces\": [{\"id\": \"/qa-f17/v\", \"name\": \"v\", \"path\": \"${P4096}p\"}]}"
  control-agent-server api POST /api/workspaces --expect 422 --check detail.0.type eq string_too_long --check detail.0.loc contains id \
    --json "{\"workspaces\": [{\"id\": \"${P4096}p\", \"name\": \"v\", \"path\": \"/qa-f17/v\"}]}"
  control-agent-server api POST /api/workspaces --expect 422 --check detail.0.type eq string_too_long --check detail.0.loc contains parentPath \
    --json "{\"workspaces\": [{\"id\": \"/qa-f17/v\", \"name\": \"v\", \"path\": \"/qa-f17/v\", \"parentPath\": \"${P4096}p\"}]}"
  control-agent-server api POST /api/workspaces/parents --expect 422 --check detail.0.type eq string_too_long \
    --json "{\"parents\": [{\"id\": \"${P4096}p\", \"name\": \"v\", \"path\": \"/qa-f17/v\"}]}"
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check workspaceParents len-eq 0 \
    --check . not-contains /qa-f17/v --check . not-contains batch-valid --save F17.validation/unchanged
  control-agent-server api POST /api/workspaces --expect 200 --quiet --check workspaces len-eq 6 \
    --check workspaces.5.name eq "$N256" --check workspaces.5.path eq "$P4096" --check workspaces.5.parentPath eq "$P4096" \
    --json "{\"workspaces\": [{\"id\": \"$P4096\", \"name\": \"$N256\", \"path\": \"$P4096\", \"parentPath\": \"$P4096\"}]}"
  control-agent-server api DELETE /api/workspaces --query "path=$P4096" --expect 200 --check deleted eq true
  ```
  每个格式错误的主体都会以422状态码附带错误字段 `detail[0].loc`。 混合体既不储存物品 A，也不储存物品 B。 接受长度为256个字符的名字、4096个字符的ID、路径以及`parentPath`。 左列表：
  `REPO`, `PLAIN`, `snake`, `null`, `dup`.
- **注册家长(`F17.add-parents`)。**将一个父级在一个正文中发布两次，再加上另一个父级，然后以新名称重新发布第一个。
  ```sh
  control-agent-server api POST /api/workspaces/parents --json-file "$F17/parents.json" --expect 200 \
    --check workspaceParents len-eq 2 --check workspaceParents.0.id eq "$PARENT" \
    --check workspaceParents.0.name eq qa-f17-parent --check workspaceParents.1.path eq /qa-f17/other-parent \
    --check workspaces len-eq 5 --save F17.add-parents/post
  control-agent-server api POST /api/workspaces/parents --expect 200 --check workspaceParents len-eq 2 \
    --check workspaceParents.0.name eq qa-f17-parent \
    --json "{\"parents\": [{\"id\": \"qa-f17-again\", \"name\": \"qa-f17-renamed\", \"path\": \"$PARENT\"}]}"
  control-agent-server api GET /api/workspaces --check workspaceParents len-eq 2 --check workspaces len-eq 5 \
    --check . not-contains qa-f17-parent-dup --save F17.add-parents/get
  control-agent-server state cat home/.openhands/workspaces.json --check workspaceParents len-eq 2 \
    --check workspaceParents.0.path eq "$PARENT" --check workspaces len-eq 5
  ```
  存储了两个家长，第一个id和姓名保留，工作区列表不变。 父母左：`PARENT`，`/qa-f17/other-parent`。
- **父母的孩子 (`F17.parent-children`)。**父目录的子目录是候选目录，而不是工作区，直到发布为止。
  ```sh
  control-agent-server api GET /api/file/search_subdirs --query "path=$PARENT" --expect 200 \
    --check items len-eq 2 --check items.0.path eq "$PARENT/alpha" --check items.1.path eq "$PARENT/beta" \
    --save F17.parent-children/subdirs
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check . not-contains "$PARENT/alpha"
  control-agent-server api POST /api/workspaces --json-file "$F17/child.json" --expect 200 \
    --check workspaces len-eq 6 --check workspaces.5.path eq "$PARENT/alpha" --check workspaces.5.parentPath eq "$PARENT" \
    --save F17.parent-children/register-child
  control-agent-server api GET /api/workspaces --check workspaces.5.parentPath eq "$PARENT" --check . not-contains "$PARENT/beta"
  ```
  `search_subdirs` 优惠 `alpha` 和 `beta`； 工作区都不是，直到
  `alpha` 已发布，`parentPath` 设置为父级，`beta` 仍为候选。 左侧列表：`REPO`、`PLAIN`、`snake`、`null`、`dup`、`alpha`。
- **删除父项 (`F17.delete-parent`)。**
  ```sh
  control-agent-server api DELETE /api/workspaces/parents --query "path=$PARENT" --expect 200 --check deleted eq true \
    --save F17.delete-parent/delete
  control-agent-server api GET /api/workspaces --check workspaceParents len-eq 1 \
    --check workspaceParents.0.path eq /qa-f17/other-parent --check workspaces len-eq 6 \
    --check workspaces.5.parentPath eq "$PARENT" --save F17.delete-parent/after
  control-agent-server state cat home/.openhands/workspaces.json --check workspaceParents len-eq 1 \
    --check workspaces.5.parentPath eq "$PARENT"
  control-agent-server api DELETE /api/workspaces/parents --query "path=$PARENT" --expect 404 \
    --check detail eq 'Workspace parent not found' --save F17.delete-parent/again
  control-agent-server api DELETE /api/workspaces/parents --expect 422 --check detail.0.loc contains path
  ```
  父项从列表中消失，文件也被删除。 `alpha` 仍然是一个工作区的 `parentPath`。 父母离开：
  `/qa-f17/other-parent`.
- **两个独立的列表 (`F17.lists-independent`).**也将普通目录设为父目录，然后跨列表删除。
  ```sh
  control-agent-server api POST /api/workspaces/parents --json-file "$F17/plain-parent.json" --expect 200 \
    --check workspaceParents len-eq 2 --check workspaceParents.1.path eq "$PLAIN" \
    --check workspaces len-eq 6 --check workspaces.1.path eq "$PLAIN"
  control-agent-server api DELETE /api/workspaces/parents --query "path=$REPO" --expect 404 --check detail eq 'Workspace parent not found'
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/other-parent --expect 404 --check detail eq 'Workspace not found'
  control-agent-server api DELETE /api/workspaces --query "path=$PLAIN" --expect 200 --check deleted eq true
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check workspaces not-contains "$PLAIN" \
    --check workspaceParents len-eq 2 --check workspaceParents.1.path eq "$PLAIN" --save F17.lists-independent/after
  ```
  在父路径上，工作区路径是404，而父路径在工作区路径上也是404。 删除`PLAIN`作为工作区的子，它将作为父。 列表左侧：`REPO`，`snake`，`null`，`dup`，`alpha`。 父母
  `/qa-f17/other-parent`, `PLAIN`.
- **持久化重新启动 (`F17.persist-restart`)。**
  ```sh
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  control-agent-server restart
  control-agent-server api GET /api/workspaces --expect 200 --check . eq "$BEFORE" \
    --check workspaces.4.parentPath eq "$PARENT" --check workspaceParents.1.path eq "$PLAIN" --save F17.persist-restart/after
  ```
  重启后生成的文档与之前的一样，包括顺序和`parentPath`。
- **需要会话密钥 (`F17.auth-required`)。**每条路线无钥匙和有错误钥匙，则积极控制。
  ```sh
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  control-agent-server api GET /api/workspaces --auth none --expect 401 --check detail eq Unauthorized --save F17.auth-required/get-no-key
  control-agent-server api GET /api/workspaces --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /api/workspaces --auth none --expect 401 \
    --json '{"workspaces": [{"id": "/qa-f17/unauth", "name": "qa-f17-unauth", "path": "/qa-f17/unauth"}]}' --save F17.auth-required/post-no-key
  control-agent-server api POST /api/workspaces --auth bad --expect 401 \
    --json '{"workspaces": [{"id": "/qa-f17/unauth", "name": "qa-f17-unauth", "path": "/qa-f17/unauth"}]}'
  control-agent-server api DELETE /api/workspaces --auth none --query "path=$REPO" --expect 401
  control-agent-server api DELETE /api/workspaces --auth bad --query "path=$REPO" --expect 401
  control-agent-server api POST /api/workspaces/parents --auth none --expect 401 \
    --json '{"parents": [{"id": "/qa-f17/unauth", "name": "qa-f17-unauth", "path": "/qa-f17/unauth"}]}'
  control-agent-server api POST /api/workspaces/parents --auth bad --expect 401 \
    --json '{"parents": [{"id": "/qa-f17/unauth", "name": "qa-f17-unauth", "path": "/qa-f17/unauth"}]}'
  control-agent-server api DELETE /api/workspaces/parents --auth none --query "path=$PLAIN" --expect 401
  control-agent-server api DELETE /api/workspaces/parents --auth bad --query "path=$PLAIN" --expect 401
  control-agent-server api POST /api/workspaces --auth none --json '{}' --expect 401 --check detail eq Unauthorized
  control-agent-server api DELETE /api/workspaces --auth none --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /api/workspaces --expect 200 --check . eq "$BEFORE" --save F17.auth-required/unchanged
  control-agent-server state cat home/.openhands/workspaces.json --not-contains /qa-f17/unauth
  ```
  所有十二个调用都返回401 `{"detail": "Unauthorized"}`，包括一个无效的主体和一个没有 `path` 的删除（在请求验证之前检查了密钥）。 使用运行的密钥，文档未改变，也没有存储任何内容。
- **并发写入 (`F17.concurrent-adds`).**八个工作区和八个家长同时发布，然后所有十六个同时删除。
  ```sh
  PIDS=""
  for i in 1 2 3 4 5 6 7 8; do
    (control-agent-server api POST /api/workspaces --quiet --expect 200 \
      --json "{\"workspaces\": [{\"id\": \"/qa-f17/par-$i\", \"name\": \"qa-f17-par-$i\", \"path\": \"/qa-f17/par-$i\"}]}" > "$F17/par-ws-$i.json") &
    PIDS="$PIDS $!"
    (control-agent-server api POST /api/workspaces/parents --quiet --expect 200 \
      --json "{\"parents\": [{\"id\": \"/qa-f17/ppar-$i\", \"name\": \"qa-f17-ppar-$i\", \"path\": \"/qa-f17/ppar-$i\"}]}" > "$F17/par-parent-$i.json") &
    PIDS="$PIDS $!"
  done
  for p in $PIDS; do wait "$p"; done
  control-agent-server api GET /api/workspaces --check workspaces len-eq 13 --check workspaceParents len-eq 10 \
    --check workspaces contains /qa-f17/par-8 --check workspaceParents contains /qa-f17/ppar-8 --save F17.concurrent-adds/after-adds
  control-agent-server state cat home/.openhands/workspaces.json --check workspaces len-eq 13 --check workspaceParents len-eq 10
  PIDS=""
  for i in 1 2 3 4 5 6 7 8; do
    (control-agent-server api DELETE /api/workspaces --quiet --query "path=/qa-f17/par-$i" --expect 200 --check deleted eq true > "$F17/del-ws-$i.json") &
    PIDS="$PIDS $!"
    (control-agent-server api DELETE /api/workspaces/parents --quiet --query "path=/qa-f17/ppar-$i" --expect 200 --check deleted eq true > "$F17/del-parent-$i.json") &
    PIDS="$PIDS $!"
  done
  for p in $PIDS; do wait "$p"; done
  control-agent-server api GET /api/workspaces --check workspaces len-eq 5 --check workspaceParents len-eq 2 \
    --check . not-contains /qa-f17/par- --check . not-contains /qa-f17/ppar- --save F17.concurrent-adds/after-deletes
  ```
  每个并行调用都成功（每个`wait`都返回其退出状态）。 添加后，列表中分别有13和10个条目，删除后又恢复到5和2个条目。 一个进程依次运行这些处理器（它们会 `async`，阻塞事件循环以读取和写入文件），因此这个条目证明，一个服务器上的并行调用者不会失去任何东西，而不是说文件锁工作。 `F17.shared-dir` 将另一个进程放在同一个文件上。
- **两台服务器，一个文件(`F17.shared-dir`)。**第二台服务器，其
  `OH_PERSISTENCE_DIR` 是本次运行的，然后并行写入分为两者。
  ```sh
  SHARED=$(control-agent-server launch --new --name f17-shared --print-run \
    --env OH_PERSISTENCE_DIR="$AGENT_SERVER_VERIFY_RUN/home/.openhands")
  trap 'control-agent-server stop --run "$SHARED" >/dev/null' EXIT
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  control-agent-server api GET /api/workspaces --run "$SHARED" --expect 200 --check . eq "$BEFORE"
  control-agent-server api POST /api/workspaces --run "$SHARED" --expect 200 --check workspaces len-eq 6 \
    --json '{"workspaces": [{"id": "/qa-f17/from-b", "name": "qa-f17-from-b", "path": "/qa-f17/from-b"}]}'
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 6 \
    --check workspaces.5.path eq /qa-f17/from-b --save F17.shared-dir/a-reads-b
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/from-b --expect 200 --check deleted eq true
  control-agent-server api GET /api/workspaces --run "$SHARED" --expect 200 --check . eq "$BEFORE"
  PIDS=""
  for i in 1 2 3 4 5 6 7 8; do
    (control-agent-server api POST /api/workspaces --quiet --expect 200 \
      --json "{\"workspaces\": [{\"id\": \"/qa-f17/via-a-$i\", \"name\": \"qa-f17-via-a-$i\", \"path\": \"/qa-f17/via-a-$i\"}]}" > "$F17/shared-a-$i.json") &
    PIDS="$PIDS $!"
    (control-agent-server api POST /api/workspaces --run "$SHARED" --quiet --expect 200 \
      --json "{\"workspaces\": [{\"id\": \"/qa-f17/via-b-$i\", \"name\": \"qa-f17-via-b-$i\", \"path\": \"/qa-f17/via-b-$i\"}]}" > "$F17/shared-b-$i.json") &
    PIDS="$PIDS $!"
  done
  for p in $PIDS; do wait "$p"; done
  control-agent-server api GET /api/workspaces --check workspaces len-eq 21 --check workspaces contains /qa-f17/via-a-8 \
    --check workspaces contains /qa-f17/via-b-8 --save F17.shared-dir/after-adds
  control-agent-server api GET /api/workspaces --run "$SHARED" --check workspaces len-eq 21
  PIDS=""
  for i in 1 2 3 4 5 6 7 8; do
    (control-agent-server api DELETE /api/workspaces --run "$SHARED" --quiet --query "path=/qa-f17/via-a-$i" --expect 200 > "$F17/shared-del-a-$i.json") &
    PIDS="$PIDS $!"
    (control-agent-server api DELETE /api/workspaces --quiet --query "path=/qa-f17/via-b-$i" --expect 200 > "$F17/shared-del-b-$i.json") &
    PIDS="$PIDS $!"
  done
  for p in $PIDS; do wait "$p"; done
  control-agent-server api GET /api/workspaces --expect 200 --check . eq "$BEFORE" --save F17.shared-dir/after-deletes
  control-agent-server stop --run "$SHARED"
  ```
  第二个服务器列出了这个运行的注册表如是； 一个添加的条目在这里列出 `GET`, 一个在这里被删除的就不见了。 所有十六个并行加法器（每个服务器八个）都落到了一起，每个服务器的列表有21个条目，通过另一个服务器删除所有条目会返回注册表 to `BEFORE`. 丢失更新会在添加后消失，或者在删除后留下。 在圆点处，第二个服务器停止了（并且由于） `trap` 如果检查失败。
- **TypeScript 客户端 (`F17.ts-client`).**每个`WorkspacesClient`方法
  from the built client.
  ```sh
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  control-agent-server exec --timeout 120 --expect-output QA_F17_TS_OK --save F17.ts-client/program -- node "$F17/ts_workspaces.mjs"
  control-agent-server api GET /api/workspaces --check . eq "$BEFORE" --check . not-contains /qa-f17/ts --save F17.ts-client/after
  ```
  程序打印`QA_F17_TS_OK`：添加的工作区和父项原样返回，重新命名添加会保留第一个，两者都会删除答案
  `{deleted: true}`，重复删除拒绝 `HttpError`，其
  `status`是404，`detail`是服务器的消息，最后的列表等于第一个。 服务器端的读取证实了这一点。
- **文件损坏 (`F17.corrupted-file`)。**备份文件，用损坏的JSON覆盖它，调用每个路由，然后恢复它。
  ```sh
  cp "$WS" "$F17/workspaces.good.json"
  printf '{"workspaces": [qa-f17-corrupt\n' > "$WS"
  control-agent-server api GET /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted' --save F17.corrupted-file/get
  control-agent-server api POST /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted' \
    --json '{"workspaces": [{"id": "/qa-f17/c", "name": "qa-f17-c", "path": "/qa-f17/c"}]}' --save F17.corrupted-file/post
  control-agent-server api DELETE /api/workspaces --query "path=$REPO" --expect 409 --check detail eq 'Workspaces file is corrupted' \
    --save F17.corrupted-file/delete
  control-agent-server api POST /api/workspaces/parents --expect 409 --check detail eq 'Workspaces file is corrupted' \
    --json '{"parents": [{"id": "/qa-f17/c", "name": "qa-f17-c", "path": "/qa-f17/c"}]}'
  control-agent-server api DELETE /api/workspaces/parents --query "path=$PLAIN" --expect 409 --check detail eq 'Workspaces file is corrupted'
  printf '{"workspaces": [qa-f17-corrupt\n' | cmp - "$WS"
  : > "$WS"
  control-agent-server api GET /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted' --save F17.corrupted-file/empty-get
  control-agent-server api POST /api/workspaces --expect 409 \
    --json '{"workspaces": [{"id": "/qa-f17/c", "name": "qa-f17-c", "path": "/qa-f17/c"}]}'
  test -f "$WS" && test ! -s "$WS"
  cp "$F17/workspaces.good.json" "$WS"
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 5 --check workspaces.0.path eq "$REPO" \
    --check workspaceParents.1.path eq "$PLAIN" --save F17.corrupted-file/restored
  ```
  所有五条路线都返回409 `Workspaces file is corrupted`，`cmp` 会忽略损坏的字节，一个零字节文件以同样的方式拒绝，然后保持空无一物，而恢复后的文件会列出一切。
- **未来或无效模式 (`F17.future-schema`).**有效的 JSON 服务器不得解释：较新的 `schema_version`、字符串 `schema_version`、错误键入的列表。
  ```sh
  printf '{"schema_version": 2, "workspaces": [], "workspaceParents": []}\n' > "$WS"
  control-agent-server api GET /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted' --save F17.future-schema/get-v2
  control-agent-server api POST /api/workspaces --expect 409 \
    --json '{"workspaces": [{"id": "/qa-f17/f", "name": "qa-f17-f", "path": "/qa-f17/f"}]}' --save F17.future-schema/post-v2
  control-agent-server api DELETE /api/workspaces/parents --query "path=$PLAIN" --expect 409
  printf '{"schema_version": 2, "workspaces": [], "workspaceParents": []}\n' | cmp - "$WS"
  printf '{"schema_version": "1", "workspaces": [], "workspaceParents": []}\n' > "$WS"
  control-agent-server api GET /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted'
  control-agent-server api POST /api/workspaces/parents --expect 409 \
    --json '{"parents": [{"id": "/qa-f17/f", "name": "qa-f17-f", "path": "/qa-f17/f"}]}'
  printf '{"schema_version": "1", "workspaces": [], "workspaceParents": []}\n' | cmp - "$WS"
  printf '{"schema_version": 1, "workspaces": "qa-f17-not-a-list"}\n' > "$WS"
  control-agent-server api GET /api/workspaces --expect 409 --check detail eq 'Workspaces file is corrupted'
  control-agent-server api DELETE /api/workspaces --query "path=$REPO" --expect 409
  printf '{"schema_version": 1, "workspaces": "qa-f17-not-a-list"}\n' | cmp - "$WS"
  control-agent-server logs --grep 'Failed to load workspaces' --expect-min 7
  printf '{"workspaces": [{"id": "/qa-f17/legacy", "name": "qa-f17-legacy", "path": "/qa-f17/legacy"}]}\n' > "$WS"
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 1 --check workspaces.0.path eq /qa-f17/legacy \
    --check workspaceParents len-eq 0 --save F17.future-schema/unversioned
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/legacy --expect 200 --check deleted eq true
  control-agent-server state cat home/.openhands/workspaces.json --check schema_version eq 1 --check workspaces len-eq 0
  cp "$F17/workspaces.good.json" "$WS"
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 5 --save F17.future-schema/restored
  ```
  每个变体在读取和写入时都是409，`cmp` 表示文件没有被重写。 每个拒绝的负载都记录了`Failed to load workspaces`，因此`doctor`的可选`log-tracebacks`检查在这一条之后报告它们（不失败`doctor`）。 正控件是一份手写文档，没有`schema_version`，正常读取，`schema_version` 1 删除标记。 恢复备份会恢复列表。
- ** 无法读取的文件 (`F17.io-error`).** 将空目录放在文件的位置（权限不会阻止根服务器），然后调用每个路由，最后再放回文件。
  ```sh
  mv "$WS" "$F17/workspaces.moved.json"
  mkdir "$WS"
  control-agent-server api GET /api/workspaces --expect 500 --check exception contains 'Failed to read workspaces' --save F17.io-error/get
  control-agent-server api POST /api/workspaces --expect 500 --check exception contains 'Failed to save workspaces' \
    --json '{"workspaces": [{"id": "/qa-f17/io", "name": "qa-f17-io", "path": "/qa-f17/io"}]}' --save F17.io-error/post
  control-agent-server api DELETE /api/workspaces --query "path=$REPO" --expect 500 --check exception contains 'Failed to update workspaces' \
    --save F17.io-error/delete
  control-agent-server api POST /api/workspaces/parents --expect 500 --check exception contains 'Failed to save workspaces' \
    --json '{"parents": [{"id": "/qa-f17/io", "name": "qa-f17-io", "path": "/qa-f17/io"}]}'
  control-agent-server api DELETE /api/workspaces/parents --query "path=$PLAIN" --expect 500 --check exception contains 'Failed to update workspaces'
  control-agent-server state ls 'home/.openhands/workspaces.tmp*' --expect-count 0
  control-agent-server logs --grep 'Cannot access workspaces file' --expect-min 5
  rmdir "$WS"
  mv "$F17/workspaces.moved.json" "$WS"
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 5 --check workspaces.0.path eq "$REPO" \
    --check . not-contains /qa-f17/io --save F17.io-error/restored
  ```
  每条路由都返回 500 `detail`  `Internal Server Error` (服务器的5xx重写)和步骤 `exception` (`500: Failed to read workspaces`);
  `rmdir` 成功，因为目录中没有写入任何内容，旁边没有留下任何临时文件，并且恢复的文件再次列出了所有内容。 日志每调用一次记录一条 `Cannot access workspaces file: [Errno 21] Is a directory` ERROR 行，没有堆栈跟踪：500 状态码是故意的
  `HTTPException`，服务器在没有堆栈的情况下记录它。
- **对只读存储 (`F17.noop-write-readonly`) 进行无操作写入。**使持久化目录不可变（`chattr +i`，代表只读安装：服务器拥有该目录并在每次保存之前重新应用模式 `0700`，因此权限不会阻止它），然后写入。
  ```sh
  PDIR="$AGENT_SERVER_VERIFY_RUN/home/.openhands"
  BEFORE=$(control-agent-server api GET /api/workspaces --field .)
  chattr +i "$PDIR"
  trap 'chattr -i "$PDIR"' EXIT
  control-agent-server api GET /api/workspaces --expect 200 --check . eq "$BEFORE" --save F17.noop-write-readonly/get
  control-agent-server api POST /api/workspaces --expect 500 --check exception contains 'Failed to save workspaces' \
    --json '{"workspaces": [{"id": "/qa-f17/ro", "name": "qa-f17-ro", "path": "/qa-f17/ro"}]}' --save F17.noop-write-readonly/real-add
  control-agent-server state ls 'home/.openhands/workspaces.tmp*' --expect-count 0
  control-agent-server api DELETE /api/workspaces --query path=/qa-f17/never --expect 404 \
    --check detail eq 'Workspace not found' --save F17.noop-write-readonly/delete-unknown
  control-agent-server api POST /api/workspaces --json-file "$F17/readd.json" --expect 200 --check workspaces len-eq 5
  control-agent-server api DELETE /api/workspaces/parents --query path=/qa-f17/never --expect 404
  control-agent-server api POST /api/workspaces/parents --json-file "$F17/plain-parent.json" --expect 200 \
    --check workspaceParents len-eq 2
  chattr -i "$PDIR"
  trap - EXIT
  control-agent-server api GET /api/workspaces --expect 200 --check . eq "$BEFORE" --check . not-contains /qa-f17/ro
  ```
  仍然读取存储的文档，并且实际添加是500 `Failed to save workspaces` 没有临时文件留下，这表明存储空间已满只读。 删除未知路径仍然返回 404 错误，并重新提交已保存的内容工作区 or the saved `PLAIN` 父节点仍然返回 200，由于 None 他们中没有人能写什么（保存时会返回 500 错误） `Failed to update workspaces` 或 `Failed to save workspaces` 在 `exception`). 的 `trap` 清除标志，子弹是否通过或失败，以及列表保持不变。 需要 root (`CAP_LINUX_IMMUTABLE`以及一个具有 immutable 属性的文件系统（ext4、xfs、btrfs）； 没有他们
  `chattr` 是失败的命令，项目符号报告 `fail`，而不是
  `xfail`.
- **没有`OH_PERSISTENCE_DIR`（`F17.persistence-location`）的位置。**重新启动变量为空，写入，然后恢复启动环境。
  ```sh
  control-agent-server restart --env OH_PERSISTENCE_DIR=
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 0 --check workspaceParents len-eq 0 \
    --save F17.persistence-location/empty
  control-agent-server api POST /api/workspaces --expect 200 --check workspaces len-eq 1 \
    --json '{"workspaces": [{"id": "/qa-f17/moved", "name": "qa-f17-moved", "path": "/qa-f17/moved"}]}' --save F17.persistence-location/post
  control-agent-server state cat server/workspace/.openhands/workspaces.json --mode 600 --check workspaces.0.path eq /qa-f17/moved
  control-agent-server state cat home/.openhands/workspaces.json --not-contains /qa-f17/moved --check workspaces.0.path eq "$REPO"
  control-agent-server restart --reset-config
  control-agent-server api GET /api/workspaces --expect 200 --check workspaces len-eq 5 --check . not-contains /qa-f17/moved \
    --save F17.persistence-location/restored
  ```
  当变量为空时，服务器读取和写入
  `server/workspace/.openhands/workspaces.json`（运行的父级
  `conversations_path`，加上 `.openhands`) 并将文件保留在 `home/` 下； 在`restart --reset-config`之后，原始列表又回来了。

<a id="gotchas"></a>

## 陷阱

- 工作区库是一个全局单例，首次请求时创建（`get_workspaces_store`），因此文件位置在整个进程生命周期内固定：更改 `OH_PERSISTENCE_DIR` 需要重启。 如果没有它，位置将遵循 `conversations_path`，对于默认相对 `workspace/conversations` 来说，位置是服务器工作目录下的 `./workspace/.openhands`。 内容不会被缓存：每个请求都会读取文件，因此手动编辑或同一目录上的另一个服务器会在下次调用时显示（`F17.shared-dir`）。
- 仅当某些内容发生更改时，写入路由才会重写整个文件：
  `FileWorkspacesStore.update` 跳过保存操作 `apply` 返回它所给的文档，所以是 404 `DELETE` 在创建一个新目录时，不会发生什么 `workspaces.json` (`F17.noop-delete-no-file`), 一个重试操作或 404 错误 `DELETE` 不修改文件`F17.noop-write-untouched`, 以及在目录下，服务器无法写入这些无用请求，它们仍然保持 404/200 答案`F17.noop-write-readonly`需要 root 权限的 `chattr +i`). 任何写入路由，包括拒绝的删除，仍然使用该端点锁因此，它创建了 `.workspaces.lock`. 仅 `GET` [401, 422, 409的409，500的不可读文件]都让磁盘完全不受影响。 `F17.list-empty` 和 `F17.noop-delete-no-file` 在任何其他调用之前运行，以确保文件尚未存在。 一个零字节 `workspaces.json` 这算数
  损坏：注册表保持 409，直到有人修复或删除该文件。
- 匹配是 `path` 上的精确字符串比较：没有规范化，没有存在检查，允许相对路径。 `/x` 和 `/x/` 是单独的条目，并且 `id` 没有进行唯一检查（如果两个条目的路径不同，则它们可能共享一个 id）。 GUI 设置 `id` 等于 `path`（参见 `WorkspaceItem` 的注释）； `search_subdirs` 返回没有尾部斜杠的路径，因此从中进行选择可以避免接近重复。
- 删除父级不会触及 `parentPath` 为其命名的工作区； 客户必须容忍悬空`parentPath`。
- 未知字段被默默丢弃（Pydantic's默认值`ignore`），在网络和磁盘上，因此客户端无法通过注册表传递额外的元数据。
- 对于每个拒绝，409 详细信息都是 `Workspaces file is corrupted`，包括来自较新的文档模式：API 不区分“损坏”和“太新”。 无法读取的文件为 500，5xx 处理程序将 `detail` 替换为 `Internal Server Error`：从以下位置读取步骤
  `exception` (`F17.io-error`). 在创建任何临时文件之前，加载时写入失败。
- 路由位于常规的`/api`依赖之后：401缺少会话密钥，503在休眠的延迟初始化服务器上（见延迟初始化家族）。 它们不发出 WebSocket 事件，也不发出 Webhook，因此唯一的第二个视图是 `GET /api/workspaces` 和文件。
- TypeScript 客户端在每次调用之前检查 `/server_info` 并抛出异常
  `AgentServerVersionError` 适用于 1.23.0 之前的服务器。 `F17.ts-client` 导入构建的 `clients/typescript/dist` 并仅当它是时才构建它
  缺失：更改`clients/typescript/src`后，运行`npm run build`
  首先还是对老客户进行子弹测试。
