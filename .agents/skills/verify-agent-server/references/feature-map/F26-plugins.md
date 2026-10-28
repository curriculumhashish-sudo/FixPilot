<a id="plugins-catalog-install-and-marketplace"></a>

# 插件目录、安装和市场

插件打包技能、/slash命令（以`<plugin>:<command>`关键字技能的形式暴露）、子智能体钩子和MCP服务器。 消费者列出对话将自行加载的插件（用户目录、项目的
`.agents/plugins` 和 `.openhands/plugins`，并启用安装的插件），将插件从本地路径或git源安装到服务器的存储中，启用、禁用、刷新和卸载它们，并读取公共扩展市场插件的只读目录。 启用的已安装插件会在其第一条消息上合并到每个新对话中：它们的挂钩运行并且它们的命令激活。

资料来源：`openhands-agent-server/openhands/agent_server/plugins_router.py`、`openhands-agent-server/openhands/agent_server/plugins_service.py`、`openhands-sdk/openhands/sdk/plugin/`、`openhands-sdk/openhands/sdk/extensions/`、`openhands-sdk/openhands/sdk/marketplace/`、`clients/typescript/src/client/plugins-client.ts`

需求：`llm`、`git`、`node`、`network`

路线：`POST /api/plugins`、`POST /api/plugins/fetch`、`POST /api/plugins/install`、
`GET /api/plugins/installed`, `GET /api/plugins/installed/{plugin_name}`,
`PATCH /api/plugins/installed/{plugin_name}`,
`DELETE /api/plugins/installed/{plugin_name}`,
`POST /api/plugins/installed/{plugin_name}/refresh`,
`GET /api/plugins/marketplace`

<a id="sub-features"></a>

## 子功能

- `F26.auth`：每个插件路由都会在没有有效会话密钥的情况下回答 401 并且不安装任何内容。
- `F26.catalog-project`: `POST /api/plugins` 和 `project_dir` 列出了 `.agents/plugins` 和 `.openhands/plugins` 下的插件（也来自封闭的 git root）及其技能、命令技能和文件； `load_project: false`或没有`project_dir`列出None，并且没有JSON主体的请求是422。
- `F26.catalog-user-precedence`：`load_user`列出了`~/.agents/plugins`和`$OH_PERSISTENCE_DIR/plugins`下的插件； 项目插件胜过同名的用户插件，用户目录插件胜过已启用的同名安装插件。
- `F26.fetch-source`：严格使用 fetch 策略，并描述了一个无需安装的 Git 插件，重用已打上的缓存，拒绝未知引用，以类型为 422 的错误来逃避子路径或缺失机密。
- `F26.install-local` 安装本地 Claude Code 布局插件后，会返回 200 状态码，并包含其元数据、技能和文件，然后将其复制到商店，记录在 `.installed.json` 中，而环境目录则会列出它（而不是商店本身）。
- `F26.install-agent-plugins`：带有智能体插件 `$schema` 的根 `plugin.json` 与其 `skills/` 和 `dev.openhands/commands` 一起安装； 没有 `$schema` 的对象会回退到 Claude Code 布局并从其目录中推断元数据。
- `F26.install-git`：使用 `repo_path` 从 `file://` git 源安装会记录源、`repo_path` 和已解析的提交，并仅复制该子目录。
- `F26.install-repo-root-name`：没有 `repo_path` 且没有清单安装的 git 源以存储库命名，而不是以服务器的缓存目录命名。
- `F26.install-conflict`：同一插件的第二次安装是 409，没有任何变化； `force: true` 重新安装并保留启用标志。
- `F26.install-errors`：无法获取的源有 400 个，无效插件有 422 个，格式错误的主体有 422 个，其中 None 会在商店中留下任何内容。
- `F26.install-github`：带有 `repo_path` 的 GitHub 简写 `github:owner/repo` 将安装公共存储库的子目录及其已解析的提交。
- `F26.install-documented-source`：`InstallPluginRequest.source`的OpenAPI描述广告的GitHub源形式安装插件。
- `F26.enable-disable`：`PATCH`和`enabled`切换标志，单视图、列表和`.installed.json`显示； 禁用的插件会离开环境目录并在重新启用时返回。
- `F26.name-errors`：在获取、启用/禁用、卸载和刷新时，未知插件为 404，`^[a-z0-9]+(-[a-z0-9]+)*$` 之外的名称为 422。
- `F26.refresh`：刷新从记录的源（新提交、编辑的本地清单）重新获取，删除固定引用，并保留启用标志。
- `F26.self-heal`：复制到商店的目录对于单个视图来说是未知的，直到列表通过源`local`采用它； 列表还会忽略清单名称不同的目录，并删除目录消失的记录。
- `F26.refresh-unfetchable`刷新一个源消失的插件、一个源无效的插件，或者一个采用源的插件 `local`这是一个客户端错误，安装继续。
- `F26.uninstall`：卸载删除目录及记录； 单一视图、列表和环境目录不再显示，第二次卸载是404。
- `F26.conversation-ambient`：当新对话收到第一个消息时，它会加载一个启用的安装插件：`UserPromptSubmit`钩子运行（另一个`HookExecutionEvent`，也在事件套接字上运行），命令技能激活，技能在对话中显示。
- `F26.conversation-disabled`：禁用插件后开始的对话既不会加载其钩子，也不会加载其技能，而用户目录插件仍然加载。
- `F26.conversation-resume-disabled`：重新启动后，现有对话会完全删除已禁用的插件、其命令及其挂钩。
- `F26.restart-persist`：已安装的插件、它们的记录和启用的标志在重新启动后仍然存在。
- `F26.marketplace-local` 与本地替代的扩展仓库 `GET /api/plugins/marketplace` 列出只有 `./plugins/` 项（本地内容对应本地内容，本地内容对应本地内容的坐标）带有 `installed` 标志； 没有清单的存储库会提供未缓存的空目录。
- `F26.marketplace-cache`：从每个进程缓存提供非空目录（仅在重新启动后才会出现新的上游条目； 5 分钟的 TTL 本身不会等待结束），而 `installed` 保持新鲜。
- `F26.ts-client`：TypeScript 客户端的每个 `PluginsClient` 方法都对服务器起作用，并且错误显示为 `HttpError` 以及状态和详细信息。
- `F26.marketplace-public`：相对于真实的 `OpenHands/extensions` 存储库，目录准确地列出了其 `./plugins/` 条目及其内容。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，环境目录：`POST /api/plugins`和`PluginsRequest`（`load_user`和`load_project`默认为`true`，`project_dir`默认为None； 需要 JSON 主体，`{}` 就足够了）返回
  `{"plugins": [{name, version, description, path, skills, files}]}`，`project_dir` 中设置的对话将自动加载。 驱动由
  `F26.catalog-*` 子弹和每个突变的第二个视图。
- REST，严格获取：`POST /api/plugins/fetch`接受`source`，`ref`，
  `repo_path`、`secrets`和`timeout`，并返回已锁定缓存路径、已解决引用、源、元数据、技能和命令，而不安装或启用插件(`F26.fetch-source`)。 源错误包括键入
  `detail.code` 具有 422、502 或 504 状态的值。 这条路线是在#5987中添加的； 固定的 TypeScript 客户端还没有获取包装器。
- REST，已安装的插件：`POST /api/plugins/install`（`source`，`ref`，
  `repo_path`, `force`), `GET /api/plugins/installed`,
  `GET|PATCH|DELETE /api/plugins/installed/{plugin_name}`（`PATCH` 取
  `{"enabled": bool}`）和`POST /api/plugins/installed/{plugin_name}/refresh`。 响应带有已安装副本的`skills`（包括`<plugin>:<command>`技能）和`files`。 商店是`$OH_PERSISTENCE_DIR/plugins/installed/<name>/`，元数据是`.installed.json`； git 源缓存在
  `$OH_PERSISTENCE_DIR/cache/extensions/`.
- REST，市场：`GET /api/plugins/marketplace`读取公共扩展克隆，`$OH_PERSISTENCE_DIR/cache/skills/public-skills`（与技能目录共享，F25），并返回`./plugins/`条条目，`source`、`ref`、`repo_path`的附带坐标，`installed`
  `path`/`skills`/`files` 当条目是克隆的目录时。
- 对话：`LocalConversation._ensure_plugins_loaded` 在第一条消息或运行时将已启用的已安装插件、用户目录插件和工作区的项目插件合并到智能体中。 第二次意见：
  `GET /api/conversations/{id}?include_skills=true` (`agent.agent_context.skills`; 如果没有查询，技能就会被修剪），用户 `MessageEvent` 的
  `activated_skills` 和 `HookExecutionEvent` 已打开
  `/sockets/events/{conversation_id}`（均属于对话家族）。 显式附加（`POST /api/conversations` 上的 `plugins`）和
  `POST /api/conversations/{id}/load_plugin`属于F04和F09。
- TypeScript 客户端：`PluginsClient.getPlugins`、`getPluginsMarketplace`、
  `installPlugin`, `listInstalledPlugins`, `getInstalledPlugin`,
  `setPluginEnabled`、`uninstallPlugin`、`refreshPlugin`（也称为
  `OpenHandsClient.plugins`); 由`F26.ts-client`驱动。
- PythonSDK：这些路由没有远程客户端； `openhands.sdk.plugin` (`install_plugin`, `list_installed_plugins`, `load_available_plugins`, ...) 是进程内运行的相同代码。
- 配置：`OH_PERSISTENCE_DIR`（存储和缓存）和`HOME`（`~/.agents/plugins`）在导入时读取，因此在启动之前设置它们（启动器将两者设置为运行专用）； `EXTENSIONS_REF` 固定公共存储库参考。
- Agent Canvas（仅限上下文）：插件市场页面安装并附加目录中的插件。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已实时并导出，`doctor` 正常，`$DEEPSEEK_API_KEY` 已设置并且
  `git` 和 `node` 已安装。 不需要启动标志。 仅 `F26.install-github` 需要出站 HTTPS 至 github.com (`network`)，
  `F26.install-documented-source`和`F26.marketplace-public`； 所有其他项目符号都脱机运行（DeepSeek 调用除外）。 `known bug` 个子弹在命令 `# bug` 执行之前就安排好了自己的状态和正控，所以每个子弹都独立运行 `map run --only`，如果安排失败（没有网络，没有模型），则报告 `fail`，而不是 `xfail`。
- 下面的块激活 `deepseek-flash` 并创建运行拥有的
  测试夹具：`qa-f26-inst`插件（其钩子与`QA_F26_INST_HOOK`相呼应），
  `qa-f26-src` git 源，`qa-f26-proj` 项目有两个项目插件，三个用户目录插件（一个是项目插件的副本，带有另一个描述； `qa-f26-user` 的钩子与 `QA_F26_USER_HOOK` 相呼应，一个智能体插件布局插件，错误情况下损坏的插件目录，以及一个没有市场清单的本地 git 存储库 `extensions`，该存储库被克隆到运行的公共技能缓存中，在 `F26.marketplace-public` 删除它之前它代表公共存储库。
  ```sh
  control-agent-server llm preset deepseek
  export GIT_CONFIG_GLOBAL="$AGENT_SERVER_VERIFY_RUN/home/.gitconfig"
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f26"
  I="$AGENT_SERVER_VERIFY_RUN/home/.openhands/plugins/installed"
  U="$AGENT_SERVER_VERIFY_RUN/home/.agents/plugins"
  O="$AGENT_SERVER_VERIFY_RUN/home/.openhands/plugins"
  PUB="$AGENT_SERVER_VERIFY_RUN/home/.openhands/cache/skills/public-skills"
  E="$F/extensions"
  PL=$(control-agent-server fixture plugin --name qa-f26-inst --print-path)
  G=$(control-agent-server fixture git-source --name qa-f26-src --print-path)
  H1=$(git -C "$G" rev-parse HEAD)
  P=$(control-agent-server fixture project --name qa-f26-proj --print-path)
  mkdir -p "$U" "$O" "$P/.agents/plugins" "$P/.openhands/plugins" "$P/sub" "$E/plugins" "$E/skills/qa-f26-pub-standalone" \
    "$F/qa-f26-ap/skills/qa-f26-ap-skill" "$F/qa-f26-ap/dev.openhands/commands" "$F/qa-f26-ap-noschema" \
    "$F/qa-f26-badjson/.plugin" "$F/Qa_Plugin/skills/qa-f26-x" "$F/qa-f26-badname/.plugin" "$F/qa-f26-noname/.plugin"
  cp -r "$(control-agent-server fixture plugin --name qa-f26-proj-plugin --print-path)" "$P/.agents/plugins/"
  cp -r "$(control-agent-server fixture plugin --name qa-f26-legacy-plugin --print-path)" "$P/.openhands/plugins/"
  cp -r "$(control-agent-server fixture plugin --name qa-f26-user --print-path)" "$U/"
  cp -r "$(control-agent-server fixture plugin --name qa-f26-oh --print-path)" "$O/"
  cp -r "$P/.agents/plugins/qa-f26-proj-plugin" "$U/"
  sed -i 's/"description": ".*"/"description": "QA user copy"/' "$U/qa-f26-proj-plugin/.plugin/plugin.json"
  sed -i 's/QA_PLUGIN_HOOK/QA_F26_INST_HOOK/' "$PL/hooks/hooks.json"
  sed -i 's/QA_PLUGIN_HOOK/QA_F26_USER_HOOK/' "$U/qa-f26-user/hooks/hooks.json"
  printf '{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "qa-f26-ap", "version": "0.2.0", "description": "QA Agent Plugins layout"}\n' > "$F/qa-f26-ap/plugin.json"
  printf -- '---\nname: qa-f26-ap-skill\ndescription: QA Agent Plugins skill\n---\nQA_AP_SKILL\n' > "$F/qa-f26-ap/skills/qa-f26-ap-skill/SKILL.md"
  printf -- '---\ndescription: QA Agent Plugins command\n---\nReply with QA_AP_RUN.\n' > "$F/qa-f26-ap/dev.openhands/commands/run.md"
  printf '{"name": "qa-f26-ap-noschema", "version": "0.2.0"}\n' > "$F/qa-f26-ap-noschema/plugin.json"
  printf '{bad json' > "$F/qa-f26-badjson/.plugin/plugin.json"
  printf -- '---\nname: qa-f26-x\ndescription: QA skill of a badly named plugin\n---\nBody\n' > "$F/Qa_Plugin/skills/qa-f26-x/SKILL.md"
  printf '{"name": "Bad_Name", "version": "0.1.0"}\n' > "$F/qa-f26-badname/.plugin/plugin.json"
  printf '{"version": "0.1.0"}\n' > "$F/qa-f26-noname/.plugin/plugin.json"
  cp -r "$(control-agent-server fixture plugin --name qa-f26-pub --print-path)" "$E/plugins/"
  printf -- '---\nname: qa-f26-pub-standalone\ndescription: QA standalone skill\n---\nQA_PUB_STANDALONE\n' > "$E/skills/qa-f26-pub-standalone/SKILL.md"
  printf '# QA extensions stand-in\n' > "$E/README.md"
  git -C "$E" init -q -b main
  git -C "$E" add -A
  git -C "$E" commit -q -m 'QA extensions stand-in without a manifest'
  git clone -q "$E" "$PUB"
  ```

- **需要会话密钥 (`F26.auth`)。**在没有钥匙的情况下呼叫每一条路线（钥匙错误的路线），然后使用钥匙呼叫一次。
  ```sh
  control-agent-server api POST /api/plugins --auth none --json '{}' --expect 401
  control-agent-server api POST /api/plugins/fetch --auth none --json '{"source": "'"$PL"'"}' --expect 401
  control-agent-server api POST /api/plugins/install --auth none --json '{"source": "'"$PL"'"}' --expect 401
  control-agent-server api GET /api/plugins/installed --auth bad --expect 401
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --auth none --expect 401
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --auth none --json '{"enabled": false}' --expect 401
  control-agent-server api DELETE /api/plugins/installed/qa-f26-inst --auth none --expect 401
  control-agent-server api POST /api/plugins/installed/qa-f26-inst/refresh --auth none --expect 401
  control-agent-server api GET /api/plugins/marketplace --auth none --expect 401 --check detail eq Unauthorized --save F26.auth/marketplace
  test ! -e "$I"
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 0
  ```
  所有九个答案都是`401 {"detail": "Unauthorized"}`，商店目录不存在，且带有键答案200的相同列表没有插件。
- **项目插件 (`F26.catalog-project`).**仅列出测试夹具项目（从其根目录和子目录），然后将项目分层。
  ```sh
  control-agent-server api POST /api/plugins --json '{"load_user": false, "project_dir": "'"$P"'"}' --expect 200 \
    --check plugins len-eq 2 --check plugins.0.name eq qa-f26-proj-plugin --check plugins.0.version eq 0.1.0 \
    --check plugins.0.path eq "$P/.agents/plugins/qa-f26-proj-plugin" \
    --check plugins.0.skills contains '"name": "qa-f26-proj-plugin-skill"' \
    --check plugins.0.skills contains '"name": "qa-f26-proj-plugin:qa-hello", "description": "Say hello from the QA plugin"' \
    --check plugins.0.files contains .plugin/plugin.json --check plugins.0.files contains commands/qa-hello.md \
    --check plugins.0.files contains hooks/hooks.json --check plugins.1.name eq qa-f26-legacy-plugin \
    --check plugins.1.path eq "$P/.openhands/plugins/qa-f26-legacy-plugin" --save F26.catalog-project/project
  control-agent-server api POST /api/plugins --json '{"load_user": false, "project_dir": "'"$P/sub"'"}' --expect 200 \
    --check plugins len-eq 2 --check plugins.0.path eq "$P/.agents/plugins/qa-f26-proj-plugin" --save F26.catalog-project/git-root
  control-agent-server api POST /api/plugins --json '{"load_user": false, "load_project": false, "project_dir": "'"$P"'"}' --expect 200 --check plugins len-eq 0
  control-agent-server api POST /api/plugins --json '{"load_user": false}' --expect 200 --check plugins len-eq 0
  control-agent-server api POST /api/plugins --json '{"load_user": "maybe"}' --expect 422 --check detail.0.type eq bool_parsing
  control-agent-server api POST /api/plugins --expect 422 --check detail.0.type eq missing --check detail.0.loc.0 eq body \
    --save F26.catalog-project/no-body
  ```
  项目列出了 `qa-f26-proj-plugin`（来自 `.agents/plugins`）
  `qa-f26-legacy-plugin`（来自`.openhands/plugins`）； 每个都带有其技能、其命令（如技能 `<plugin>:qa-hello`）及其文件列表。 子目录 `sub` 中的相同插件来自 git 根目录。 如果没有项目层，或者没有 `project_dir`，则不会列出任何内容。 没有请求体的请求 `422` (`missing` 在 `body` 中)，尽管每个字段都有默认值。
- **用户插件和优先级 (`F26.catalog-user-precedence`)。**列出用户层，然后列出两个层； 然后安装具有另一个描述的用户目录插件 `qa-f26-oh` 的副本，再次列出，然后卸载它。
  ```sh
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins len-eq 3 --check plugins.0.name eq qa-f26-proj-plugin --check plugins.0.description eq 'QA user copy' \
    --check plugins.0.path eq "$U/qa-f26-proj-plugin" --check plugins.1.name eq qa-f26-user \
    --check plugins.1.path eq "$U/qa-f26-user" --check plugins.2.name eq qa-f26-oh \
    --check plugins.2.path eq "$O/qa-f26-oh" --save F26.catalog-user-precedence/user
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": true, "project_dir": "'"$P"'"}' --expect 200 \
    --check plugins len-eq 4 --check plugins.0.name eq qa-f26-proj-plugin \
    --check plugins.0.description eq 'QA fixture plugin qa-f26-proj-plugin' \
    --check plugins.0.path eq "$P/.agents/plugins/qa-f26-proj-plugin" --check plugins.3.name eq qa-f26-legacy-plugin \
    --save F26.catalog-user-precedence/merged
  cp -r "$O/qa-f26-oh" "$F/qa-f26-oh-copy"
  sed -i 's/"description": ".*"/"description": "QA installed copy"/' "$F/qa-f26-oh-copy/.plugin/plugin.json"
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/qa-f26-oh-copy"'"}' --expect 200 \
    --check name eq qa-f26-oh --check description eq 'QA installed copy' --check enabled eq true
  control-agent-server api GET /api/plugins/installed/qa-f26-oh --expect 200 --check description eq 'QA installed copy'
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins len-eq 3 --check plugins.2.name eq qa-f26-oh --check plugins.2.path eq "$O/qa-f26-oh" \
    --check plugins.2.description eq 'QA fixture plugin qa-f26-oh' --save F26.catalog-user-precedence/installed-shadowed
  control-agent-server api DELETE /api/plugins/installed/qa-f26-oh --expect 200
  test -d "$O/qa-f26-oh"
  ```
  用户层级列表 `~/.agents/plugins`（用户副本）
  `qa-f26-proj-plugin`、`qa-f26-user`) 和 `$OH_PERSISTENCE_DIR/plugins` (`qa-f26-oh`)。 在这两层中，项目的 `qa-f26-proj-plugin` 替换了用户副本（项目描述和路径），结果有四个插件。 安装了一个名为“用户目录插件”的启用插件（其单视图显示了这一点），但环境元目录仍然保留了目录插件（路径和描述），没有重复。 卸载副本不会影响目录插件。
- **从本地路径安装 (`F26.install-local`)。**安装测试夹具插件，然后以四种方式读回。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$PL"'"}' --expect 200 \
    --check name eq qa-f26-inst --check version eq 0.1.0 --check description eq 'QA fixture plugin qa-f26-inst' \
    --check enabled eq true --check source eq "$PL" --check resolved_ref eq null --check repo_path eq null \
    --check install_path eq "$I/qa-f26-inst" --check installed_at exists --check skills len-eq 2 \
    --check skills.0.name eq qa-f26-inst-skill --check skills.1.name eq qa-f26-inst:qa-hello \
    --check files len-eq 4 --check files contains hooks/hooks.json --save F26.install-local/install
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check source eq "$PL" \
    --check enabled eq true --check skills len-eq 2 --save F26.install-local/get
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 1 --check plugins.0.name eq qa-f26-inst
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json \
    --check extensions.qa-f26-inst.source eq "$PL" --check extensions.qa-f26-inst.enabled eq true
  test -f "$I/qa-f26-inst/.plugin/plugin.json"
  grep -q QA_F26_INST_HOOK "$I/qa-f26-inst/hooks/hooks.json"
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins len-eq 4 --check plugins.3.name eq qa-f26-inst --check plugins.3.path eq "$I/qa-f26-inst" \
    --check plugins not-contains '"name": "installed"' --save F26.install-local/ambient
  ```
  安装回答了 manifest 的名称、版本和描述，源（给出的），没有 `resolved_ref`（本地副本），存储路径，以及安装副本的技能和四个文件。 单一视图，列表，
  `.installed.json` 与复制的文件一致。 环境目录将已安装的插件附加在插件目录之后，并且不会将存储目录 `$OH_PERSISTENCE_DIR/plugins/installed` 误认为是插件。
- **无需安装即可获取 (`F26.fetch-source`)。** Pin a git plugin and read its metadata without adding it to the installed catalog.
  ```sh
  FETCH_SOURCE=$(control-agent-server fixture git-source --name qa-f26-fetch --print-path)
  FETCH_SHA=$(git -C "$FETCH_SOURCE" rev-parse HEAD)
  FETCH_BODY=$(jq -cn --arg source "file://$FETCH_SOURCE" --arg ref "$FETCH_SHA" \
    '{source:$source,ref:$ref,repo_path:"plugins/qa-f26-fetch-plugin"}')
  FETCH_PATH=$(control-agent-server api POST /api/plugins/fetch --json "$FETCH_BODY" --expect 200 \
    --check resolved_ref eq "$FETCH_SHA" --check manifest.name eq qa-f26-fetch-plugin \
    --check skills contains qa-f26-fetch-plugin-skill --check commands contains qa-hello \
    --save F26.fetch-source/fetched --field path)
  test -f "$FETCH_PATH/.plugin/plugin.json"
  control-agent-server api GET /api/plugins/installed/qa-f26-fetch-plugin --expect 404 \
    --save F26.fetch-source/not-installed
  control-agent-server api POST /api/plugins/fetch --json "$FETCH_BODY" --expect 200 \
    --check path eq "$FETCH_PATH" --check resolved_ref eq "$FETCH_SHA" --save F26.fetch-source/cached
  control-agent-server api POST /api/plugins/fetch \
    --json "$(jq -cn --arg source "file://$FETCH_SOURCE" '{source:$source,ref:"qa-no-such-ref",repo_path:"plugins/qa-f26-fetch-plugin"}')" \
    --expect 422 --check detail.code eq ref_not_found --save F26.fetch-source/unknown-ref
  control-agent-server api POST /api/plugins/fetch \
    --json "$(jq -cn --arg source "file://$FETCH_SOURCE" --arg ref "$FETCH_SHA" '{source:$source,ref:$ref,repo_path:"../outside"}')" \
    --expect 422 --check detail.code eq repo_path_not_found --save F26.fetch-source/outside
  control-agent-server api POST /api/plugins/fetch --json '{"source":"${QA_F26_MISSING_SOURCE}"}' \
    --expect 422 --check detail.code eq missing_secret --save F26.fetch-source/missing-secret
  control-agent-server api GET /api/plugins/installed/qa-f26-fetch-plugin --expect 404
  ```
  Fetch 返回缓存路径、元数据、技能名称和命令名称。 重复使用相同的 SHA 路径。 未知引用和逃逸子路径引发类型错误，缺少的源机密在 git 运行之前就被拒绝了。 None 个调用会安装或启用插件。
- **智能体插件布局 (`F26.install-agent-plugins`).**安装根
  `plugin.json` 与智能体插件 `$schema`，然后相同的清单没有它。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/qa-f26-ap"'"}' --expect 200 \
    --check name eq qa-f26-ap --check version eq 0.2.0 --check description eq 'QA Agent Plugins layout' \
    --check skills len-eq 2 --check skills.0.name eq qa-f26-ap-skill --check skills.1.name eq qa-f26-ap:run \
    --check files contains plugin.json --check files contains dev.openhands/commands/run.md \
    --save F26.install-agent-plugins/install
  control-agent-server api GET /api/plugins/installed/qa-f26-ap --expect 200 --check skills.1.name eq qa-f26-ap:run
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/qa-f26-ap-noschema"'"}' --expect 200 \
    --check name eq qa-f26-ap-noschema --check version eq 1.0.0 --check skills len-eq 0 \
    --save F26.install-agent-plugins/no-schema
  control-agent-server api GET /api/plugins/installed/qa-f26-ap-noschema --expect 200 \
    --check name eq qa-f26-ap-noschema --check files contains plugin.json
  control-agent-server api DELETE /api/plugins/installed/qa-f26-ap-noschema --expect 200
  control-agent-server api GET /api/plugins/installed/qa-f26-ap-noschema --expect 404
  ```
  智能体插件格式从根目录`plugin.json`检测到：技能来自`skills/`，命令来自`dev.openhands/commands/`(`qa-f26-ap:run`)。 一个没有 `$schema` 的 JSON 对象声明了格式，否则将回退到 Claude Code 格式，如 #5990 规定的。 它的根ifest被忽略，所以这个测试夹具使用目录名和版本`1.0.0`。 读确认在清理后安装保持后续目录计数不变。
- **从 git 源安装 (`F26.install-git`)。**安装 `file://` 测试夹具存储库的插件子目录。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "file://'"$G"'", "repo_path": "plugins/qa-f26-src-plugin"}' --expect 200 \
    --check name eq qa-f26-src-plugin --check source eq "file://$G" --check repo_path eq plugins/qa-f26-src-plugin \
    --check resolved_ref eq "$H1" --check install_path eq "$I/qa-f26-src-plugin" --check files len-eq 4 \
    --save F26.install-git/install
  control-agent-server api GET /api/plugins/installed/qa-f26-src-plugin --expect 200 --check resolved_ref eq "$H1" \
    --check repo_path eq plugins/qa-f26-src-plugin
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json \
    --check extensions.qa-f26-src-plugin.resolved_ref eq "$H1" --check extensions.qa-f26-src-plugin.requested_ref eq null
  control-agent-server state ls 'home/.openhands/cache/extensions/qa-f26-src-*/.git/HEAD' --expect-count 1
  test ! -e "$I/qa-f26-src-plugin/.git"
  test ! -e "$I/qa-f26-src-plugin/skills/qa-f26-src-skill"
  ```
  `cache/extensions/qa-f26-src-<hash>` 仓库克隆到，插件子目录仅复制到存储中，记录保留源、`repo_path` 和提交(`H1`); 没有请求裁判。
- **存储库根名称（`F26.install-repo-root-name`）。**安装整个测试夹具存储库（它的根目录下没有插件清单），将其删除，然后比较名称。
  ```sh
  N=$(control-agent-server api POST /api/plugins/install --json '{"source": "file://'"$G"'"}' --expect 200 \
    --check resolved_ref eq "$H1" --save F26.install-repo-root-name/install --field name)
  control-agent-server api DELETE "/api/plugins/installed/$N" --expect 200
  control-agent-server api GET "/api/plugins/installed/$N" --expect 404
  control-agent-server assert --value "$N" --check . eq qa-f26-src
  ```
  一个没有 manifest 的目录使用目录名，所以仓库安装为 `qa-f26-src`，而不是其名称
  `qa-f26-src-<hash>` 缓存目录：名称不取决于 URL 的拼写方式。 安装在比较之前被删除，因此后面的项目符号看不到它。
- **重复安装 (`F26.install-conflict`)。**再次安装相同的插件，然后在禁用时强制安装它。
  ```sh
  T1=$(control-agent-server api GET /api/plugins/installed/qa-f26-inst --field installed_at)
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$PL"'"}' --expect 409 \
    --check detail eq 'Plugin already installed. Use force=true to overwrite.' --save F26.install-conflict/conflict
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check installed_at eq "$T1"
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$PL"'", "force": true}' --expect 200 \
    --check enabled eq false --check installed_at ne "$T1" --save F26.install-conflict/force
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check enabled eq false --check installed_at ne "$T1"
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": true}' --expect 200
  ```
  第二安装是 `409` and leaves `installed_at` 单独的。 `force: true` 重新安装（新） `installed_at`) 并且保持插件禁用。 子弹重新启用了它。
- **安装错误 (`F26.install-errors`)。**无法获取的源、无效的插件和畸形的主体。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/qa-f26-missing"'"}' --expect 400 \
    --check detail eq 'Failed to fetch plugin source. Check that the source is valid.' --save F26.install-errors/missing-path
  control-agent-server api POST /api/plugins/install --json '{"source": "github:qa"}' --expect 400
  control-agent-server api POST /api/plugins/install --json '{"source": "qa-f26-not-a-source"}' --expect 400
  control-agent-server api POST /api/plugins/install --json '{"source": "file://'"$F/qa-f26-no-repo"'"}' --expect 400
  control-agent-server api POST /api/plugins/install --json '{"source": "file://'"$G"'", "repo_path": "plugins/qa-f26-missing"}' --expect 400
  control-agent-server api POST /api/plugins/install --json '{"source": "file://'"$G"'", "repo_path": "../.."}' --expect 400 \
    --save F26.install-errors/escaping-repo-path
  for D in qa-f26-badjson Qa_Plugin qa-f26-badname qa-f26-noname; do
    control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/$D"'"}' --expect 422 \
      --check detail eq 'Invalid plugin. Ensure it has a valid kebab-case name.' --save "F26.install-errors/$D"
  done
  control-agent-server api POST /api/plugins/install --json '{"source": ""}' --expect 422 --check detail.0.type eq string_too_short
  control-agent-server api POST /api/plugins/install --json '{}' --expect 422 --check detail.0.type eq missing
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$PL"'", "ref": 5}' --expect 422 --check detail.0.loc.1 eq ref
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 3 --save F26.install-errors/after
  test "$(find "$I" -mindepth 1 -maxdepth 1 | wc -l)" -eq 4
  ```
  缺少的路径，一个 GitHub 没有仓库的简写（解析器无网络调用就拒绝），不可解析的源，一个 `file://`  URL 那不是仓库，是一个缺失 `repo_path` and a `repo_path` 从仓库中爬出来的所有都是 `400 Failed to fetch plugin source`. 无效 JSON 在 `.plugin/plugin.json`一个名为 manifest-less 的空目录 `Qa_Plugin`, 一个 manifest 名称 `Bad_Name` 且没有名称的 manifest 都是 `422` 使用相同的驼峰式消息。 身体错误是 FastAPI  `422`s. 商店仍然保留了这三款插件
  `.installed.json`.
- **从 GitHub (`F26.install-github`) 安装。**安装公众号
  `plugins/city-weather` 插件带有 GitHub 简写和 `repo_path`（网络），读回它并卸载它。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "github:OpenHands/extensions", "repo_path": "plugins/city-weather"}' \
    --timeout 240 --expect 200 --check name eq city-weather --check source eq github:OpenHands/extensions \
    --check repo_path eq plugins/city-weather --check resolved_ref matches '^[0-9a-f]{40}$' \
    --check skills contains '"name": "city-weather:now"' --save F26.install-github/install
  control-agent-server api GET /api/plugins/installed/city-weather --expect 200 --check repo_path eq plugins/city-weather \
    --check resolved_ref matches '^[0-9a-f]{40}$' --save F26.install-github/get
  control-agent-server state ls 'home/.openhands/cache/extensions/extensions-*/.git/HEAD' --expect-count 1
  test ! -e "$I/city-weather/.git"
  control-agent-server api DELETE /api/plugins/installed/city-weather --expect 200
  control-agent-server api GET /api/plugins/installed/city-weather --expect 404
  ```
  缩写展开为 `https://github.com/OpenHands/extensions.git`，该值被复制到 `cache/extensions/extensions-<hash>`。 仅
  `plugins/city-weather` 被复制到存储中，并带有安装它的提交。 如果没有网络，安装是`400 Failed to fetch plugin source`。 该插件已被删除，因此稍后的项目符号会看到相同的商店。
- **已记录的安装源 `F26.install-documented-source`。**首先在工作形式中安装公共插件（正控：现在该服务器可达），然后在 GitHub形式中 GitHub插件的 OpenAPI描述 `InstallPluginRequest.source`广告（网络）。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "github:OpenHands/extensions", "repo_path": "plugins/city-weather", "force": true}' \
    --timeout 240 --expect 200 --check name eq city-weather --save F26.install-documented-source/working-form
  control-agent-server api DELETE /api/plugins/installed/city-weather --expect 200
  DOC=$(control-agent-server api GET /openapi.json --auth none --field components.schemas.InstallPluginRequest.properties.source.description)
  case "$DOC" in
    *"'github:OpenHands/extensions/plugins/city-weather'"*)
      control-agent-server api POST /api/plugins/install --json '{"source": "github:OpenHands/extensions/plugins/city-weather"}' \
        --timeout 240 --expect 200 --check name eq city-weather --save F26.install-documented-source/documented
      control-agent-server api DELETE /api/plugins/installed/city-weather --expect 200
      ;;
  esac
  ```
  工作表（`github:OpenHands/extensions` plus `repo_path`，例如
  `F26.install-github`) 安装并再次删除，因此此时可以从该服务器访问 GitHub； 记录的示例
  `github:OpenHands/extensions/plugins/city-weather` 安装相同的插件：简写克隆 `OpenHands/extensions` 并使用 REST 作为
  `repo_path`（两者都通过就是`400`）。 如果没有网络，阳性对照首先会失败，因此子弹报告`fail`。
- **启用和禁用 (`F26.enable-disable`)。**禁用该插件，在各处读回它，然后再次启用它。
  ```sh
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200 \
    --check name eq qa-f26-inst --check enabled eq false --save F26.enable-disable/disable
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check enabled eq false
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins.0.name eq qa-f26-inst \
    --check plugins.0.enabled eq false --check plugins.1.enabled eq true
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json --check extensions.qa-f26-inst.enabled eq false
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins not-contains '"name": "qa-f26-inst"' --check plugins contains '"name": "qa-f26-ap"' \
    --save F26.enable-disable/ambient-disabled
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200 --check enabled eq false
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{}' --expect 422 --check detail.0.loc.1 eq enabled
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": true}' --expect 200 --check enabled eq true
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check enabled eq true
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins contains '"name": "qa-f26-inst"' --save F26.enable-disable/ambient-enabled
  ```
  `PATCH` 答案 `{"name": "qa-f26-inst", "enabled": false}`； 只有一个视图、列表（其他插件保持启用状态）和`.installed.json`显示旗帜，而`qa-f26-ap`的环境目录则会删除插件，但仍然列出启用的插件。 禁用两次是 200 无操作，身体没有
  `enabled` 是 422，启用后会将其恢复。
- **未知且无效的名称 (`F26.name-errors`)。**解决未安装的插件，然后命名打破模式的名称。
  ```sh
  control-agent-server api GET /api/plugins/installed/qa-f26-ghost --expect 404 \
    --check detail eq "Plugin 'qa-f26-ghost' is not installed" --save F26.name-errors/get
  control-agent-server api PATCH /api/plugins/installed/qa-f26-ghost --json '{"enabled": true}' --expect 404 \
    --check detail eq "Plugin 'qa-f26-ghost' is not installed"
  control-agent-server api DELETE /api/plugins/installed/qa-f26-ghost --expect 404 --check detail eq "Plugin 'qa-f26-ghost' is not installed"
  control-agent-server api POST /api/plugins/installed/qa-f26-ghost/refresh --expect 404 \
    --check detail eq "Plugin 'qa-f26-ghost' is not installed"
  control-agent-server api GET /api/plugins/installed/Bad_Name --expect 422 --check detail.0.type eq string_pattern_mismatch \
    --save F26.name-errors/bad-name
  control-agent-server api PATCH /api/plugins/installed/Bad_Name --json '{"enabled": true}' --expect 422 \
    --check detail.0.type eq string_pattern_mismatch
  control-agent-server api DELETE /api/plugins/installed/Bad_Name --expect 422 --check detail.0.type eq string_pattern_mismatch
  control-agent-server api POST /api/plugins/installed/Bad_Name/refresh --expect 422 --check detail.0.type eq string_pattern_mismatch
  control-agent-server api DELETE /api/plugins/installed/qa--f26 --expect 422
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 3
  ```
  每一个不知名的名字都是`404 Plugin '<name>' is not installed`； `Bad_Name` 和 `qa--f26` 在处理器运行之前就失败了，路径模式 `422`。
- **刷新(`F26.refresh`)。**向 git 源提交新的清单描述并刷新禁用的 git 插件； 编辑本地源并刷新本地插件； 然后将 git 插件固定到 `H1` 并刷新它。
  ```sh
  sed -i 's/"description": ".*"/"description": "QA git plugin v2"/' "$G/plugins/qa-f26-src-plugin/.plugin/plugin.json"
  git -C "$G" commit -q -am 'QA plugin v2'
  H2=$(git -C "$G" rev-parse HEAD)
  control-agent-server api PATCH /api/plugins/installed/qa-f26-src-plugin --json '{"enabled": false}' --expect 200
  control-agent-server api POST /api/plugins/installed/qa-f26-src-plugin/refresh --expect 200 \
    --check message eq "Plugin 'qa-f26-src-plugin' updated" --check plugin.resolved_ref eq "$H2" \
    --check plugin.description eq 'QA git plugin v2' --check plugin.enabled eq false \
    --check plugin.repo_path eq plugins/qa-f26-src-plugin --save F26.refresh/git
  control-agent-server api GET /api/plugins/installed/qa-f26-src-plugin --expect 200 --check resolved_ref eq "$H2" --check enabled eq false
  grep -q 'QA git plugin v2' "$I/qa-f26-src-plugin/.plugin/plugin.json"
  sed -i 's/"description": ".*"/"description": "QA local plugin v2"/' "$PL/.plugin/plugin.json"
  control-agent-server api POST /api/plugins/installed/qa-f26-inst/refresh --expect 200 \
    --check plugin.description eq 'QA local plugin v2' --check plugin.enabled eq true --check plugin.source eq "$PL" \
    --save F26.refresh/local
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check description eq 'QA local plugin v2'
  control-agent-server api POST /api/plugins/install \
    --json '{"source": "file://'"$G"'", "repo_path": "plugins/qa-f26-src-plugin", "ref": "'"$H1"'", "force": true}' --expect 200 \
    --check resolved_ref eq "$H1" --check description eq 'QA fixture plugin qa-f26-src-plugin' --check enabled eq false \
    --save F26.refresh/pinned
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json --check extensions.qa-f26-src-plugin.requested_ref eq "$H1"
  control-agent-server api POST /api/plugins/installed/qa-f26-src-plugin/refresh --expect 200 \
    --check plugin.resolved_ref eq "$H2" --check plugin.description eq 'QA git plugin v2' --save F26.refresh/unpinned
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json --check extensions.qa-f26-src-plugin.requested_ref eq null
  control-agent-server api PATCH /api/plugins/installed/qa-f26-src-plugin --json '{"enabled": true}' --expect 200
  ```
  刷新会重新获取记录的源，并将其 `repo_path` 移动到 `H2`，同时保持禁用状态； 本地插件会读取编辑后的元数据。 `ref` `H1` 进行一次力安装，会检查出旧的提交并记录 `requested_ref`。 刷新操作按设计会丢弃 ref 并重新安装（即“最新版本”），因此插件会恢复到
  `H2` 和 `requested_ref` 消失了。 最后再次启用 git 插件。
- ** 手动编辑的商店 (`F26.self-heal`).** 复制插件目录到商店中，添加一个 manifest 名称不同于其目录的插件，然后删除跟踪的插件目录。 然后阅读列表前后的单个视图。
  ```sh
  cp -r "$(control-agent-server fixture plugin --name qa-f26-healed --print-path)" "$I/"
  mkdir -p "$I/qa-f26-mismatch/.plugin" "$F/qa-f26-stale/.plugin"
  printf '{"name": "qa-f26-other", "version": "0.1.0"}\n' > "$I/qa-f26-mismatch/.plugin/plugin.json"
  printf '{"name": "qa-f26-stale", "version": "0.1.0"}\n' > "$F/qa-f26-stale/.plugin/plugin.json"
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/qa-f26-stale"'"}' --expect 200
  rm -rf "$I/qa-f26-stale"
  control-agent-server api GET /api/plugins/installed/qa-f26-healed --expect 404 --save F26.self-heal/before-list
  control-agent-server api DELETE /api/plugins/installed/qa-f26-healed --expect 404
  control-agent-server api GET /api/plugins/installed/qa-f26-stale --expect 404
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 4 \
    --check plugins.3.name eq qa-f26-healed --check plugins.3.source eq local --check plugins.3.enabled eq true \
    --check plugins not-contains qa-f26-stale --check plugins not-contains qa-f26-other --save F26.self-heal/list
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json --check extensions.qa-f26-healed.source eq local \
    --check extensions.qa-f26-stale missing --check extensions.qa-f26-mismatch missing --check extensions.qa-f26-other missing
  control-agent-server api GET /api/plugins/installed/qa-f26-healed --expect 200 --check source eq local --save F26.self-heal/after-list
  test -d "$I/qa-f26-mismatch"
  rm -rf "$I/qa-f26-mismatch"
  ```
  只有被跟踪的插件才计入单个视图和卸载，所以复制的是这些插件
  `qa-f26-healed` 是 `404`（卸载按设计拒绝未跟踪的目录），直到列表将其与源 `local` 一起采用。 该列表还删除了 `qa-f26-stale` 的记录（它的目录消失了）并跳过
  `qa-f26-mismatch`（清单名称 `qa-f26-other`），将其保留在磁盘上。
  `POST /api/plugins` 和新对话以相同的方式协调，因此会加载复制的插件，尽管其单一视图显示 404。
- **无法获取的刷新 (`F26.refresh-unfetchable`)。** Install two plugins from temporary directories and adopt a third copied into the store; 然后删除第一个源，破坏第二个源的清单，然后刷新所有三个源。 子弹会自行安排一切，因此它也可以单独运行（`map run --only`）。
  ```sh
  mkdir -p "$F/tmp/qa-f26-gone/.plugin" "$F/tmp/qa-f26-broken/.plugin"
  printf '{"name": "qa-f26-gone", "version": "0.1.0"}\n' > "$F/tmp/qa-f26-gone/.plugin/plugin.json"
  printf '{"name": "qa-f26-broken", "version": "0.1.0"}\n' > "$F/tmp/qa-f26-broken/.plugin/plugin.json"
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/tmp/qa-f26-gone"'"}' --expect 200
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$F/tmp/qa-f26-broken"'"}' --expect 200
  cp -r "$(control-agent-server fixture plugin --name qa-f26-adopted --print-path)" "$I/"
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins contains '"name": "qa-f26-adopted"'
  control-agent-server api GET /api/plugins/installed/qa-f26-adopted --expect 200 --check source eq local
  rm -rf "$F/tmp/qa-f26-gone"
  printf '{bad json' > "$F/tmp/qa-f26-broken/.plugin/plugin.json"
  control-agent-server api POST /api/plugins/installed/qa-f26-gone/refresh --expect 400,422 --save F26.refresh-unfetchable/vanished
  control-agent-server api GET /api/plugins/installed/qa-f26-gone --expect 200 --check enabled eq true
  control-agent-server api POST /api/plugins/installed/qa-f26-broken/refresh --expect 422 --save F26.refresh-unfetchable/invalid
  control-agent-server api GET /api/plugins/installed/qa-f26-broken --expect 200 --check version eq 0.1.0
  control-agent-server api POST /api/plugins/installed/qa-f26-adopted/refresh --expect 400,422 --save F26.refresh-unfetchable/local
  control-agent-server api GET /api/plugins/installed/qa-f26-adopted --expect 200 --check source eq local
  ```
  安装路由返回400给不可获取的来源，返回422给无效插件。 刷新路由也做了同样的事情，并且保持了安装的
  复制：消失的来源和采用的 `local` 来源是 `400`（什么都没有）
  可以获取），损坏的清单 `422`。 每次刷新后的读取都会检查安装是否已保留。
- **卸载(`F26.uninstall`)。**把智能体Plugins布局插件去掉，到处读回来，再去掉； 然后清除先前子弹的剩余部分。
  ```sh
  control-agent-server api DELETE /api/plugins/installed/qa-f26-ap --expect 200 \
    --check message eq "Plugin 'qa-f26-ap' uninstalled" --save F26.uninstall/delete
  control-agent-server api GET /api/plugins/installed/qa-f26-ap --expect 404
  test ! -e "$I/qa-f26-ap"
  test -f "$F/qa-f26-ap/plugin.json"
  control-agent-server state cat home/.openhands/plugins/installed/.installed.json --check extensions.qa-f26-ap missing
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins not-contains '"name": "qa-f26-ap"'
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins not-contains '"name": "qa-f26-ap"' --save F26.uninstall/ambient
  control-agent-server api DELETE /api/plugins/installed/qa-f26-ap --expect 404 --check detail eq "Plugin 'qa-f26-ap' is not installed"
  for N in qa-f26-healed qa-f26-gone qa-f26-broken qa-f26-adopted; do
    control-agent-server api DELETE "/api/plugins/installed/$N" --expect 200,404 --quiet
  done
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 2 \
    --check plugins.0.name eq qa-f26-inst --check plugins.1.name eq qa-f26-src-plugin
  ```
  目录和记录都消失了（源目录未受影响），没有列出插件，再次卸载后 `404`。 之后，商店持有`qa-f26-inst`和`qa-f26-src-plugin`，两者都启用。
- **对话中的环境负载 (`F26.conversation-ambient`)。**创建一个没有消息的对话，捕获其事件套接字，然后发送插件的命令； 还可以用普通的提示词开始第二次对话。
  ```sh
  CID=$(control-agent-server conversation start --tools none --no-autotitle --no-run --print-id)
  control-agent-server ws start "/sockets/events/$CID" --name qa-f26-live --duration 300
  control-agent-server conversation send "$CID" --text '/qa-f26-inst:qa-hello' --wait --timeout 240
  control-agent-server ws stop qa-f26-live --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-min 1 --wait 30 \
    --save F26.conversation-ambient/frames
  control-agent-server conversation events "$CID" --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-count 1 \
    --save F26.conversation-ambient/hook
  control-agent-server conversation events "$CID" --kinds HookExecutionEvent --contains QA_F26_USER_HOOK --expect-count 1
  control-agent-server conversation events "$CID" --kinds MessageEvent --contains '"activated_skills": ["qa-f26-inst:qa-hello"]' \
    --expect-count 1 --save F26.conversation-ambient/activated
  control-agent-server api GET "/api/conversations/$CID" --query include_skills=true --expect 200 --check execution_status eq finished \
    --check agent.agent_context.skills contains '"name": "qa-f26-inst-skill"' \
    --check agent.agent_context.skills contains '"name": "qa-f26-inst:qa-hello"' \
    --check agent.agent_context.skills contains '"name": "qa-f26-user-skill"' --save F26.conversation-ambient/conversation
  CIDP=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with the single word: ok' --wait --timeout 240 --print-id)
  control-agent-server conversation events "$CIDP" --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-count 1
  control-agent-server api GET "/api/conversations/$CIDP" --query include_skills=true --expect 200 \
    --check agent.agent_context.skills contains '"name": "qa-f26-inst:qa-hello"'
  ```
  安装的插件的`UserPromptSubmit`钩子只对消息运行一次（一个包含`stdout` `QA_F26_INST_HOOK` `HookExecutionEvent`的推送消息，存储在套接字上），就像用户目录插件的。 用户
  `MessageEvent` 列出 `activated_skills: ["qa-f26-inst:qa-hello"]`，对话的智能体上下文现在包含插件的技能和命令。 以提示词开始的对话以相同的方式加载插件。 模型的回复未被断言。
- **在新对话中禁用插件 (`F26.conversation-disabled`)。**禁用插件，然后在捕获套接字时将其命令发送到新对话。
  ```sh
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200
  CID2=$(control-agent-server conversation start --tools none --no-autotitle --no-run --print-id)
  control-agent-server ws start "/sockets/events/$CID2" --name qa-f26-disabled --duration 300
  control-agent-server conversation send "$CID2" --text '/qa-f26-inst:qa-hello' --wait --timeout 240
  control-agent-server ws read qa-f26-disabled --kinds HookExecutionEvent --contains QA_F26_USER_HOOK --expect-min 1 --wait 30
  control-agent-server ws read qa-f26-disabled --kinds MessageEvent --contains '"text": "/qa-f26-inst:qa-hello"' --expect-min 1 --wait 30
  control-agent-server ws read qa-f26-disabled --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-none
  control-agent-server ws stop qa-f26-disabled --kinds MessageEvent --contains '"activated_skills": ["qa-f26-inst:qa-hello"]' --expect-none \
    --save F26.conversation-disabled/frames
  control-agent-server api GET "/api/conversations/$CID2" --query include_skills=true --expect 200 \
    --check agent.agent_context.skills not-contains qa-f26-inst --check agent.agent_context.skills contains '"name": "qa-f26-user-skill"' \
    --save F26.conversation-disabled/conversation
  control-agent-server conversation events "$CID2" --kinds HookExecutionEvent --contains QA_F26_USER_HOOK --expect-count 1
  control-agent-server conversation events "$CID2" --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-count 0
  control-agent-server conversation events "$CID2" --kinds MessageEvent --contains '"activated_skills": ["qa-f26-inst:qa-hello"]' \
    --expect-count 0 --save F26.conversation-disabled/stored
  ```
  用户目录插件的钩子运行，且其技能存在（钩子和环境加载工作，且用户消息到达），而禁用的插件既没有钩子，也没有激活的命令，也没有技能。 负向检查读取了套接字捕获(`--expect-none`)和存储的事件(`--expect-count 0`)，每个事件类型都受到限制(`full_state`帧嵌入钩配置)。 插件启用时，相同的读取结果在`F26.conversation-ambient`。 该插件保持禁用状态。
- **禁用后恢复 (`F26.conversation-resume-disabled`)，已知错误。**安装并启用插件（`force`，因此项目符号也可以单独运行
  `map run --only`), 让对话加载它为一个简单的提示词，禁用插件，重启服务器，然后第一次向那个对话发送命令。
  ```sh
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$PL"'", "force": true}' --expect 200
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": true}' --expect 200
  CIDR=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with the single word: ok' --wait --timeout 240 --print-id)
  control-agent-server conversation events "$CIDR" --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-count 1
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200
  control-agent-server restart
  control-agent-server ws start "/sockets/events/$CIDR" --name qa-f26-resume --duration 300
  control-agent-server conversation send "$CIDR" --text '/qa-f26-inst:qa-hello' --wait --timeout 240
  control-agent-server ws read qa-f26-resume --kinds HookExecutionEvent --contains QA_F26_USER_HOOK --expect-min 1 --wait 30
  control-agent-server ws read qa-f26-resume --kinds MessageEvent --contains '"text": "/qa-f26-inst:qa-hello"' --expect-min 1 --wait 30
  control-agent-server ws read qa-f26-resume --kinds HookExecutionEvent --contains QA_F26_INST_HOOK --expect-none
  control-agent-server ws stop qa-f26-resume --kinds MessageEvent --contains '"activated_skills": ["qa-f26-inst:qa-hello"]' --expect-none \
    --save F26.conversation-resume-disabled/frames  # bug：匹配 ge 1
  control-agent-server api GET "/api/conversations/$CIDR" --query include_skills=true --expect 200 \
    --check agent.agent_context.skills not-contains qa-f26-inst --save F26.conversation-resume-disabled/conversation  # bug：状态 eq 200 && response.body.agent.agent_context.skills 包含 qa-f26-inst
  ```
  对话在禁用之前加载了插件（其钩子运行了） 提示词). 环境插件不被固定到对话中。 在恢复时，它们“从磁盘或当前启用状态重新发现”`LocalConversation._ensure_plugins_loaded`), 因此，重置后的回合应该像 `F26.conversation-disabled`. 它确实运行了用户钩子，而不是禁用插件的钩子，但禁用插件的命令仍然激活了`activated_skills: ["qa-f26-inst:qa-hello"]` 在用户消息中，第一个标记的检查，以及智能体上下文仍然列出其
  技能（第二个）：它们被合并到智能体和已持久化中
  `base_state.json`，所以只有它的钩子遵循当前状态（通过相同的路径，从源读取并且不在这里驱动，它的 MCP 服务器也保留）。 该命令首次在此处发送，因为每个对话都会激活一次关键字技能 (`activated_knowledge_skills`)。 该插件保持禁用状态。
- **持久化重新启动 (`F26.restart-persist`)。**禁用
  `qa-f26-inst`（之后是无操作），重启，读取存储，然后重新启用插件。

  需要：`F26.refresh`
  ```sh
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": false}' --expect 200
  control-agent-server restart
  control-agent-server doctor
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 2 \
    --check plugins.0.name eq qa-f26-inst --check plugins.0.enabled eq false --check plugins.0.description eq 'QA local plugin v2' \
    --check plugins.1.name eq qa-f26-src-plugin --check plugins.1.resolved_ref eq "$H2" --check plugins.1.enabled eq true \
    --save F26.restart-persist/list
  control-agent-server api POST /api/plugins --json '{"load_user": true, "load_project": false}' --expect 200 \
    --check plugins not-contains '"name": "qa-f26-inst"' --check plugins contains '"name": "qa-f26-src-plugin"'
  control-agent-server api PATCH /api/plugins/installed/qa-f26-inst --json '{"enabled": true}' --expect 200
  control-agent-server api GET /api/plugins/installed/qa-f26-inst --expect 200 --check enabled eq true --save F26.restart-persist/re-enabled
  ```
  两个插件都返回了更新后的元数据，禁用标志仍然存活（环境元数据仍然跳过`qa-f26-inst`），插件在最后重新启用。
- **市场与本地替代品对抗`F26.marketplace-local`).** 在临时替代品没有 manifest 时读取目录，然后使用本地插件、独立技能和另一个仓库中的插件创建 manifest，再次读取它，然后从其坐标安装本地条目。
  ```sh
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins len-eq 0 --save F26.marketplace-local/no-manifest
  test -d "$PUB/.git"
  mkdir -p "$E/.plugin"
  cat > "$E/.plugin/marketplace.json" <<EOF
  {"name": "qa-f26-ext", "owner": {"name": "QA"}, "plugins": [
    {"name": "qa-f26-pub", "source": "./plugins/qa-f26-pub", "description": "QA public plugin"},
    {"name": "qa-f26-pub-standalone", "source": "./skills/qa-f26-pub-standalone", "description": "QA standalone skill"},
    {"name": "qa-f26-src-plugin", "source": {"source": "url", "url": "file://$G", "path": "plugins/qa-f26-src-plugin"}, "description": "QA plugin in another repository"}
  ]}
  EOF
  git -C "$E" add -A
  git -C "$E" commit -q -m 'QA marketplace manifest'
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins len-eq 2 \
    --check plugins.0.name eq qa-f26-pub --check plugins.0.description eq 'QA public plugin' \
    --check plugins.0.source eq "$PUB/plugins/qa-f26-pub" --check plugins.0.path eq "$PUB/plugins/qa-f26-pub" \
    --check plugins.0.ref eq null --check plugins.0.repo_path eq null --check plugins.0.installed eq false \
    --check plugins.0.skills contains '"name": "qa-f26-pub:qa-hello"' --check plugins.0.files contains .plugin/plugin.json \
    --check plugins.1.name eq qa-f26-src-plugin --check plugins.1.source eq "file://$G" \
    --check plugins.1.repo_path eq plugins/qa-f26-src-plugin --check plugins.1.installed eq true \
    --check plugins.1.path eq null --check plugins.1.skills eq null --check plugins.1.files eq null \
    --check plugins not-contains qa-f26-pub-standalone --save F26.marketplace-local/catalog
  SRC=$(control-agent-server api GET /api/plugins/marketplace --field plugins.0.source)
  control-agent-server api POST /api/plugins/install --json '{"source": "'"$SRC"'"}' --expect 200 \
    --check name eq qa-f26-pub --check source eq "$PUB/plugins/qa-f26-pub"
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins.0.installed eq true \
    --save F26.marketplace-local/installed
  ```
  没有 `.plugin/marketplace.json` （不含以下）
  `marketplaces/default.json`  回退方案) 该目录是 `{"plugins": []}`，并且空答案不会被缓存：接下来的调用，提交之后再次获取备用答案，并列出两个 `./plugins/`-style entries。 本地条目解析为克隆中包含技能和文件的目录； 另一个仓库中的条目包含附件坐标 (`source` + `repo_path`) 且没有本地内容，是一个 `installed` 因为那个插件已经在商店里了。 的 `./skills/`  从目录中安装 `source` 复制克隆的目录，然后下一次读取显示 `installed: true`.
- **目录缓存 (`F26.marketplace-cache`)。**将第二个本地插件提交到替身，读取目录，卸载目录插件，再次读取，然后重新启动。
  ```sh
  cp -r "$E/plugins/qa-f26-pub" "$E/plugins/qa-f26-pub2"
  sed -i 's/"name": "qa-f26-pub"/"name": "qa-f26-pub2"/' "$E/plugins/qa-f26-pub2/.plugin/plugin.json"
  sed -i 's#\]}#, {"name": "qa-f26-pub2", "source": "./plugins/qa-f26-pub2", "description": "QA second plugin"}]}#' "$E/.plugin/marketplace.json"
  git -C "$E" add -A
  git -C "$E" commit -q -m 'QA second plugin'
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins len-eq 2 --check plugins not-contains qa-f26-pub2 \
    --check plugins.0.installed eq true --save F26.marketplace-cache/cached
  control-agent-server api DELETE /api/plugins/installed/qa-f26-pub --expect 200
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins len-eq 2 --check plugins.0.installed eq false
  control-agent-server restart
  control-agent-server api GET /api/plugins/marketplace --expect 200 --check plugins len-eq 3 \
    --check plugins.2.name eq qa-f26-pub2 --check plugins.2.skills contains '"name": "qa-f26-pub2:qa-hello"' \
    --save F26.marketplace-cache/after-restart
  ```
  在最后一次获取之后的五分钟内，目录结构来自过程缓存，因此新的上游条目缺失，`installed` 会立即跟随存储。 重启后，目录又被重新获取，并列出 `qa-f26-pub2`。 TTL（`_PLUGIN_CATALOG_TTL_SECONDS = 300`）在这里不是被定时读取的。
- **TypeScript 客户端 (`F26.ts-client`).**构建客户端中的每个 `PluginsClient` 方法都有自己的插件。
  ```sh
  TSP=$(control-agent-server fixture plugin --name qa-f26-ts --print-path)
  cat > "$F/ts_plugins.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { PluginsClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new PluginsClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const source = process.env.QA_F26_TS_SOURCE;
  const ambient = (await client.getPlugins({ load_user: true, load_project: false })).plugins.map((p) => p.name);
  const installed = await client.installPlugin({ source });
  assert.equal(installed.name, 'qa-f26-ts');
  assert.equal(installed.enabled, true);
  assert.equal(installed.source, source);
  assert.equal((await client.getInstalledPlugin('qa-f26-ts')).install_path, installed.install_path);
  assert.ok((await client.listInstalledPlugins()).plugins.some((p) => p.name === 'qa-f26-ts'));
  const withTs = (await client.getPlugins({ load_user: true, load_project: false })).plugins.map((p) => p.name);
  assert.deepEqual(withTs, [...ambient, 'qa-f26-ts']);
  assert.deepEqual(await client.setPluginEnabled('qa-f26-ts', false), { name: 'qa-f26-ts', enabled: false });
  assert.equal((await client.getInstalledPlugin('qa-f26-ts')).enabled, false);
  assert.deepEqual((await client.getPlugins({ load_user: true, load_project: false })).plugins.map((p) => p.name), ambient);
  const refreshed = await client.refreshPlugin('qa-f26-ts');
  assert.equal(refreshed.message, "Plugin 'qa-f26-ts' updated");
  assert.equal(refreshed.plugin.enabled, false);
  const market = await client.getPluginsMarketplace();
  assert.deepEqual(market.plugins.map((p) => p.name), ['qa-f26-pub', 'qa-f26-src-plugin', 'qa-f26-pub2']);
  assert.deepEqual(await client.uninstallPlugin('qa-f26-ts'), { message: "Plugin 'qa-f26-ts' uninstalled" });
  await assert.rejects(client.getInstalledPlugin('qa-f26-ts'),
    (err) => err.name === 'HttpError' && err.status === 404 && err.detail === "Plugin 'qa-f26-ts' is not installed");
  await assert.rejects(client.installPlugin({ source: `${source}-missing` }),
    (err) => err.name === 'HttpError' && err.status === 400 && err.detail === 'Failed to fetch plugin source. Check that the source is valid.');
  client.close();
  console.log('QA_F26_TS_OK');
  JS
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server exec --env QA_F26_TS_SOURCE="$TSP" --timeout 180 --expect-output QA_F26_TS_OK --save F26.ts-client/program -- node "$F/ts_plugins.mjs"
  control-agent-server api GET /api/plugins/installed/qa-f26-ts --expect 404
  control-agent-server api GET /api/plugins/installed --expect 200 --check plugins len-eq 2
  ```
  该程序打印`QA_F26_TS_OK`：安装、获取、列出以及环境库一致，切换回答`{name, enabled}`，插件从环境库中移出，刷新将其禁用，市场应用列出替代品的三个插件，卸载回答其消息，错误拒绝，错误码为`HttpError`，错误码的`status`（以及`detail`）是服务器的。 服务器端确认插件已不存在。
- **公共市场 (`F26.marketplace-public`).**删除替代克隆，重新启动，然后从真实的 `OpenHands/extensions` 存储库（网络）中读取目录。
  ```sh
  rm -rf "$PUB" "$PUB.lock"
  control-agent-server restart
  control-agent-server api GET /api/plugins/marketplace --timeout 240 --expect 200 --check plugins len-ge 1 --quiet \
    --save F26.marketplace-public/catalog
  test -s "$PUB/.plugin/marketplace.json"
  N=$(python3 -c 'import json, sys; m = json.load(open(sys.argv[1])); print(sum(1 for p in m["plugins"] if str(p.get("source")).startswith("./plugins/")))' "$PUB/.plugin/marketplace.json")
  ALL=$(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["plugins"]))' "$PUB/.plugin/marketplace.json")
  FIRST=$(python3 -c 'import json, sys; m = json.load(open(sys.argv[1])); print(next(p["name"] for p in m["plugins"] if str(p.get("source")).startswith("./plugins/")))' "$PUB/.plugin/marketplace.json")
  test "$N" -ge 1
  test "$ALL" -gt "$N"
  control-agent-server api GET /api/plugins/marketplace --expect 200 --quiet --check plugins len-eq "$N" \
    --check plugins.0.name eq "$FIRST" --check plugins.0.path eq "$PUB/plugins/$FIRST" --check plugins.0.files len-ge 1 \
    --check plugins.0.installed eq false
  ```
  该克隆的 `.plugin/marketplace.json` 包含70条记录，大部分是技能`./skills/<name>`); 该目录具有  `./plugins/` 九（当时写作） `city-weather` 首先，每个分支都有自己的目录和文件。 没有网络，克隆缺失，子弹在读取时就失败了。

<a id="gotchas"></a>

## 陷阱

- 存储和缓存：安装的插件存在于
  `$OH_PERSISTENCE_DIR/plugins/installed/<manifest name>/` 与
  `.installed.json`; git 源被克隆到
  `$OH_PERSISTENCE_DIR/cache/extensions/<repo>-<hash>/`; 市场显示为`$OH_PERSISTENCE_DIR/cache/skills/public-skills`（与F25共享）。 用户目录是 `~/.agents/plugins` 和 `$OH_PERSISTENCE_DIR/plugins`（`installed/` 子目录被跳过）。 所有这些都是在导入时固定的。
- Claude Code布局是回退方案对于任何目录：一个没有 manifest 的目录会安装在它的名字下（一个 git 仓库的根目录，对应仓库的名字）版本 `1.0.0`, 并且整个目录被复制（一个没有 git 源的完整目录） `repo_path` 复制了克隆版本 `.git`, which `files` hides). 请勿安装如 [large directory] [such as] [example] [directory] [example] [directory] 的大目录 `/tmp` 测试这个。
- 没有 `$schema` 的根 `plugin.json` 对象回退到 Claude Code 布局 (#5990)； 格式错误的 JSON 或不受支持的显式 `$schema` 仍会被智能体插件格式拒绝。
- 加载插件时的每个 `ValueError`（无效 JSON、不受支持的 `$schema`、智能体插件模式违规、非 kebab-case 名称）都会得到相同的答案
  `422 Invalid plugin. Ensure it has a valid kebab-case name.`; 真正的原因不在响应中，也不在服务器日志（日志重复了相同的信息），所以通过测试夹具来区分缺陷，一项缺陷一项缺陷地报告。 智能体插件模式允许的点式名称 (`qa.f26-dotted`) 被商店的 kebab-case 规则拒绝，并具有相同的 422。
- 安装名称来自清单，而不是来自源目录； 现有插件的 409 是在获取后决定的，因此冲突的 git 安装仍然会克隆。
- 只有列表调用、`PATCH`、`POST /api/plugins`、市场（其 `installed` 标志）和对话才能与磁盘协调 `.installed.json`； 单一视图、`DELETE` 和刷新则不然，因此手动编辑的顺序很重要 (`F26.self-heal`)。
- 刷新从记录的 `source` 和 `repo_path` 重新安装，并删除引用。 从市场入口安装的插件会记录公共克隆的绝对路径，因此刷新会复制克隆持有的内容（只由后续的目录检索刷新）。 从磁盘采用的插件具有源`local`并且无法刷新：其刷新为`400`（`F26.refresh-unfetchable`）。
- 市场始终显示为 `https://github.com/OpenHands/extensions`
  `EXTENSIONS_REF`（默认`main`）； 现有的克隆是从它自己的克隆更新的
  `origin`，这就是本地替身工作的原因。 每个进程都会缓存一个非空目录五分钟（重新启动即可清除）； 空的则不被缓存。 `installed` 仅按名称：任何已安装的该名称插件都有效，无论其来源如何。
- 环境插件在每个对话的第一条消息或运行时加载一次。 禁用或卸载插件不会将其从已运行的对话中卸载； 重新启动后，它的钩子消失了，但它的技能和命令仍然存在（`F26.conversation-resume-disabled`）。
- `GET /api/conversations/{id}` 修剪 `agent.agent_context.skills` 除非
  `include_skills=true`，所以简单的 `GET` 显示没有插件技能。
- `POST /api/plugins` 需要 JSON 主体； 如果没有，则为 422（TypeScript 客户端发送 `{}`）。
- 通过“对话事件 --kinds K --contains X”断言缺席
  --expect-count 0` (stored events) or `读取 ws|停止 --种类 K --包含 X
  --expect-None`（套接字捕获），紧邻相同的读取匹配位置
  插件已启用。 始终使用 `--kinds` 限制此类检查：
  连接上发送的 `full_state` 帧嵌入对话的 `hook_config`，包括挂钩命令。
- 错误 500 在 `exception` 字段中携带异常文本； 的
  `known bug` 子弹将其保存为证据。
