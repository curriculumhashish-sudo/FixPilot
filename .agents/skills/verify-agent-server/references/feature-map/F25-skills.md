<a id="skills-catalog-install-and-marketplace"></a>

# 技能目录、安装和市场

技能是 Markdown 指令，智能体按名称、触发词或文件路径加载。 消费者向服务器请求智能体将获得的合并技能目录（沙箱主机、注册市场、公众
`OpenHands/extensions` 仓库、用户技能、组织仓库和项目目录，按名称合并到后续来源，强制刷新缓存的公共仓库，并管理用户的安装
技能：从本地目录或 git 源安装、列出、检查、启用
或禁用、从记录的源刷新并卸载。 启用的已安装技能加入目录和加载用户技能的对话的用户层，其中触发词激活它们。 市场目录列出了公共存储库的可安装条目，并带有新的 `installed` 标志。

资料来源：`openhands-agent-server/openhands/agent_server/skills_router.py`、`openhands-agent-server/openhands/agent_server/skills_service.py`、`openhands-sdk/openhands/sdk/skills/`、`openhands-sdk/openhands/sdk/extensions/`、`openhands-sdk/openhands/sdk/marketplace/`、`openhands-sdk/openhands/sdk/git/cached_repo.py`、`openhands-sdk/openhands/sdk/context/agent_context.py`、`openhands-sdk/openhands/sdk/workspace/remote/base.py`、`clients/typescript/src/client/skills-client.ts`

需求：`git`

路线：`POST /api/skills`、`GET /api/skills/catalog`、`POST /api/skills/sync`、`POST /api/skills/install`、
`GET /api/skills/installed`, `GET /api/skills/installed/{skill_name}`,
`PATCH /api/skills/installed/{skill_name}`,
`DELETE /api/skills/installed/{skill_name}`,
`POST /api/skills/installed/{skill_name}/refresh`,
`GET /api/skills/marketplace`

<a id="sub-features"></a>

## 子功能

- `F25.auth`：每个技能路线都回答 401，没有有效的会话密钥，并且未安装任何内容。
- `F25.public-repo` 与真实的公共扩展仓库（网络）对抗，同步将其克隆到公共缓存中，`POST /api/skills` `load_public` 列出从该克隆中加载的技能。
- `F25.marketplace-public`：针对真实的公共扩展存储库，`GET /api/skills/marketplace`列出了其可安装条目； 今天它返回一个空目录，因为存储库有 `.plugin/marketplace.json` 但没有 `marketplaces/default.json`。
- `F25.profile-catalog`：`GET /api/skills/catalog` 列出了可用于配置文件启动及其 `origin` 的公共和用户技能，不包括仅限项目的技能。
- `F25.catalog-project`: `POST /api/skills` 与 `project_dir` 一起 AgentSkills 项目 `agentskills` (`knowledge`)、`AGENTS.md`（`repo`）和 `sources.project`（SKILL.md）的名称无效。
- `F25.catalog-user-precedence`：`~/.agents/skills` 中的用户技能仅与 `load_user` 一起出现，并且项目技能会覆盖同名的用户技能。
- `F25.catalog-server-sources`: `sandbox_config` URLs 一个名为 `WORKER_*` 的持续运行 `work_hosts` 技能，`org_configs` 仓库是从一个 git URL (一个不可达的仓库没有任何贡献)。
- `F25.catalog-validation`：类型错误、不完整的`org_configs`条目或遍历市场`repo_path`为422。
- `F25.install-local` 安装本地技能目录会将其复制到已安装的商店中，记录元数据(`resolved_ref` null)，并且技能会出现在已安装列表、单视图(`.installed.json`)和用户层级(`POST /api/skills`)。
- `F25.enable-disable`：`PATCH {"enabled": false}`保留文件，但从目录中隐藏技能，`{"enabled": true}`恢复它，没有`enabled`的主体是422。
- `F25.install-conflict`：重新安装已安装的技能是409并且没有任何改变； `force: true` 重新安装它并保留禁用标志。
- `F25.install-errors`：一个不可获取的来源（缺少路径、不可解析的源、转义 `repo_path`）返回 400，一个无效的技能（缺少 SKILL.md、名称不匹配、无效目录名）返回 422，一个空源返回 422，以及没有安装任何内容。
- `F25.install-bad-frontmatter`：YAML 前置元数据格式错误的 SKILL.md 被视为无效技能 (422) 被拒绝，并且未安装任何内容。
- `F25.install-git`：具有 `repo_path` 的 `file://` git 源离线安装并记录源、`repo_path` 和已解析的提交 SHA。
- `F25.sdk-load-skills`: `RemoteWorkspace.load_skills_from_agent_server()` 合并其 `working_dir` 的目录后，生成 SDK 个对象（项目、用户和启用的安装技能，关键词触发器保留），以及一个 `Skill` 不会重新加载公共技能的 `AgentContext`。
- `F25.install-github`：工作 GitHub 形式（`github:OpenHands/extensions` 加 `repo_path`）在完全提交 SHA 时安装 github.com 中的公共技能，卸载它会将其删除。
- `F25.install-documented-sources`：`InstallSkillRequest.source` 的 OpenAPI 描述中的每个 GitHub 源都会宣传安装，包括 `github:owner/repo/<path>` 简写。
- `F25.refresh` 重置刷新从记录的源：新提交的 git 源更新 `resolved_ref` 和安装的文件，编辑本地源更新描述，启用标志保持不变。
- `F25.install-ref`：使用 `ref` 提交的引脚安装 git 源（`resolved_ref`，已安装的文件，`.installed.json` 中的 `requested_ref`）； 刷新将其移动到源的最新提交并删除`requested_ref`。
- `F25.install-unknown-ref`：git 源没有的 `ref` 是 400，并且对于第一个克隆和缓存源，安装保持不变。
- `F25.refresh-unfetchable`：刷新记录源不再存在的技能是客户端错误（400）并保留安装。
- `F25.name-errors`：获取、启用/禁用、卸载和刷新时，未知技能名称为 404，`^[a-z0-9]+(-[a-z0-9]+)*$` 之外的名称为 422。
- `F25.self-heal`：手动复制到存储中的技能目录对于单个视图是不可见的，直到列表调用使用源`local`发现它为止； 手动删除的跟踪目录通过列表调用从元数据中删除。
- `F25.sync`: `POST /api/skills/sync` 更新了从其源获取的缓存公共仓库，并清除60秒的公共技能缓存，因此，上游提交的技能立即列出（翻译：本地的git origin相当于GitHub）。
- `F25.sync-offline`：当无法获取公共存储库时，同步报告 `status: error` 并且过时的克隆保留在原处以进行离线加载。
- `F25.catalog-registered-marketplace`一个注册的市场 `auto_load` 添加其独立技能和插件技能（以及插件命令），并将其添加到目录中，目录是一个名称列表，从中选择一些 `auto_load: false` 或 `load_public: false` 添加 None.
- `F25.conversation-activation`在真实情况下 DeepSeek 加载用户技能的对话，触发词激活启用的安装技能： `activated_knowledge_skills`, 用户 `MessageEvent` (REST 和 WebSocket 重播）和系统提示词命名它。
- `F25.invoke-skill`：仅通过自动附加的 `invoke_skill` 工具才能访问不带触发器的启用的已安装 AgentSkill； 当智能体调用它时，观测结果携带技能体，并且会话在`invoked_skills`中列出该技能，而不是在`activated_knowledge_skills`中。
- `F25.restart-persist`：已安装的技能、其启用的标志和已解决的提交在服务器重新启动后仍然存在，并保持其目录可见性。
- `F25.catalog-server-marketplaces`服务器配置中的一条`registered_marketplaces`条目无需请求条目，同名的请求条目会替换它，另一个名称的条目会添加到它。
- `F25.marketplace-catalog`：目录列出公共仓库的条目（名称、描述、绝对源）`installed: false`，安装条目的`source`会立即将其翻转为`installed: true`（本地替代品，`marketplaces/default.json`）。
- `F25.ts-client`: the TypeScript  `SkillsClient` 安装、列出、读取、禁用和重新启用一个技能（从一个git源安装）`toggleSkill`, with `getSkills` 在标志后，刷新、同步、读取市场，并卸载它。 未知技能为404 `HttpError` 没有密钥的客户端会收到 401。
- `F25.marketplace-stale-cache`后，同步会将新条目添加到公共仓库中，同步会清除公共仓库的5分钟缓存，该缓存从不保存空结果。
- `F25.uninstall` 卸载会删除目录和元数据条目，单视图和第二次卸载都会返回 404，目录会删除技能，市场会读取 `installed: false` 一次。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，合并目录：`POST /api/skills`和`SkillsRequest`（`load_public`、`load_user`、`load_project`、`load_org`全部默认为
  `true`，加上 `project_dir`、`marketplace_path`、`registered_marketplaces`、
  `org_configs`, `sandbox_config`) 返回 `{"技能": [SkillInfo], "来源":
  {...}}`; `POST /api/skills/sync` force-updates the public repository clone.
  由 `F25.catalog-*` 和 `F25.sync*` 子弹驱动。
- REST，配置文件启动目录：`GET /api/skills/catalog`返回
  `{"skills": [SkillCatalogEntry]}` 与 `origin: public|user`，匹配公共和用户源配置文件可以解决 (#6098)。 项目和组织来源需要对话上下文，并且被排除 (`F25.profile-catalog`)。
- REST、已装技能：`POST /api/skills/install`（`source`、`ref`、
  `repo_path`, `force`), `GET /api/skills/installed`,
  `GET|PATCH|DELETE /api/skills/installed/{skill_name}` 和
  `POST /api/skills/installed/{skill_name}/refresh`. 该商店是
  `$OH_PERSISTENCE_DIR/skills/installed/<name>/` 元数据位于
  `.installed.json`; git 源缓存在
  `$OH_PERSISTENCE_DIR/cache/extensions/`.
- REST，市场：`GET /api/skills/marketplace` 读取 `$OH_PERSISTENCE_DIR/cache/skills/public-skills` 处的公共存储库克隆。
- 对话：`agent_context.load_user_skills`为True的智能体获得已启用的已安装技能； 包含技能触发器的用户消息将其注入（`MessageEvent.activated_skills`，对话
  `activated_knowledge_skills`). AgentSkills 格式的技能还会获得附加到智能体的内置 `invoke_skill` 工具； 智能体通过名称来调用它，并且对话记录 `invoked_skills`（由驱动）
  `F25.invoke-skill`). 智能体配置文件在启动时解析用户和公共技能。 这些食谱在保存的设置中启用 `load_user_skills` 并从中启动对话，就像 `conversation start` 一样。
- SDK：`RemoteWorkspace.load_skills_from_agent_server()`（和
  `CloudWorkspace`) 使用显式标志调用 `POST /api/skills` 并
  `project_dir`，重试并在错误时返回 `[]`（由
  `F25.sdk-load-skills` 到 `exec`）。
- TypeScript 客户端：`SkillsClient.getSkills`、`syncSkills`、`installSkill`、
  `listInstalledSkills`, `getInstalledSkill`, `toggleSkill`, `uninstallSkill`,
  `refreshSkill`, `getMarketplace` (`clients/typescript/src/client/skills-client.ts`; 每个方法都由 `F25.ts-client` 驱动，`node` 程序基于构建的
  `clients/typescript/dist`).
- 配置：`OH_REGISTERED_MARKETPLACES`（或`registered_marketplaces`在配置文件中）添加了服务器默认注册，这些注册请求通过配置文件中的名称覆盖
  `F25.catalog-server-marketplaces`); `EXTENSIONS_REF` 固定公共存储库参考。
- WebSocket：`/sockets/events/{conversation_id}`携带用户
  `MessageEvent` 和 `activated_skills`（由事件家族拥有； 激活项目符号会用 `resend_mode=all` 重播它）。
- Agent Canvas（仅限上下文）：技能页面列出目录、安装、切换和删除技能，并显示“市场”选项卡。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已上线并已导出，`doctor` 正常，`git` 已安装。 对话项目符号需要`$DEEPSEEK_API_KEY`并激活DeepSeek预设； TypeScript 项目符号需要 `node`。 不需要启动标志。 `F25.public-repo` 和 `F25.install-github` 需要出站 HTTPS 到 github.com，它们为它们后面的两个项目符号安排网络状态（`F25.marketplace-public`，一个已知错误，以及 `F25.install-documented-sources`）； 所有其他项目符号都脱机运行（DeepSeek 调用除外）。 这些食谱各自声明它们需要什么（`Needs:`行），（`network`和`Requires:`行继承），因此，没有模型密钥、网络或`node`的机器只会报告那些被阻拦的食谱，并驱动REST。 `F25.ts-client` 构建
  仅当缺少 `clients/typescript/dist` 时才使用 `npm ci && npm run build`（该构建需要 npm 注册表）。
- 下面的块创建了测试夹具（`qa-f25-proj` 项目，该项目有无效的额外技能，`qa-f25-skill` 技能，`qa-f25-src` git 源，`qa-f25-mk` 市场，`HOME` 运行中的用户技能，错误情况下的技能目录，以及一个本地 git 仓库 `extensions`，后来用作公共仓库），并启用了 `load_user_skills`，这样从它们开始的对话会加载已安装的技能。
  ```sh
  export GIT_AUTHOR_NAME=QA
  export GIT_AUTHOR_EMAIL=qa@example.invalid
  export GIT_COMMITTER_NAME=QA
  export GIT_COMMITTER_EMAIL=qa@example.invalid
  P=$(control-agent-server fixture project --name qa-f25-proj --print-path)
  S=$(control-agent-server fixture skill --name qa-f25-skill --print-path)
  G=$(control-agent-server fixture git-source --name qa-f25-src --print-path)
  M=$(control-agent-server fixture marketplace --name qa-f25-mk --print-path)
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f25"
  U="$AGENT_SERVER_VERIFY_RUN/home/.agents/skills"
  I="$AGENT_SERVER_VERIFY_RUN/home/.openhands/skills/installed"
  PUB="$AGENT_SERVER_VERIFY_RUN/home/.openhands/cache/skills/public-skills"
  E="$F/extensions"
  mkdir -p "$P/.agents/skills/qa-f25-badname" "$U/qa-f25-user" "$U/qa-f25-proj-skill" "$F/qa-f25-nomd" \
    "$F/qa-f25-mismatch" "$F/qa-f25-badyaml" "$F/Qa_Bad" "$E/skills/qa-f25-pub" "$E/.plugin" "$E/marketplaces"
  printf -- '---\nname: Not_Kebab\ndescription: QA invalid name\n---\nQA_BAD_NAME_BODY\n' > "$P/.agents/skills/qa-f25-badname/SKILL.md"
  printf -- '---\nname: qa-f25-user\ndescription: QA user skill\n---\nQA_USER_BODY\n' > "$U/qa-f25-user/SKILL.md"
  printf -- '---\nname: qa-f25-proj-skill\ndescription: QA user copy\n---\nQA_USER_COPY\n' > "$U/qa-f25-proj-skill/SKILL.md"
  printf '# not a skill\n' > "$F/qa-f25-nomd/README.md"
  printf -- '---\nname: qa-f25-other\ndescription: QA wrong name\n---\nBody\n' > "$F/qa-f25-mismatch/SKILL.md"
  printf -- '---\nname: qa-f25-badyaml\ndescription: [unclosed\n---\nBody\n' > "$F/qa-f25-badyaml/SKILL.md"
  printf -- '---\ndescription: QA invalid directory name\n---\nBody\n' > "$F/Qa_Bad/SKILL.md"
  printf -- '---\nname: qa-f25-pub\ndescription: QA public stand-in skill\n---\nQA_PUBLIC_BODY\n' > "$E/skills/qa-f25-pub/SKILL.md"
  printf '{"name": "qa-f25-ext", "owner": {"name": "QA"}, "plugins": [{"name": "qa-f25-pub", "source": "./skills/qa-f25-pub", "description": "QA public stand-in skill"}]}\n' \
    | tee "$E/.plugin/marketplace.json" > "$E/marketplaces/default.json"
  git -C "$E" init -q -b main
  git -C "$E" add -A
  git -C "$E" commit -q -m 'QA extensions stand-in'
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_context": {"load_user_skills": true}}}' \
    --expect 200 --check agent_settings.agent_context.load_user_skills eq true
  ```

- **需要会话密钥 (`F25.auth`)。**呼叫每条没有钥匙的路线（钥匙错误的路线）。
  ```sh
  control-agent-server api POST /api/skills --auth none --json '{"load_public": false}' --expect 401
  control-agent-server api GET /api/skills/catalog --auth none --expect 401
  control-agent-server api POST /api/skills/sync --auth bad --expect 401
  control-agent-server api POST /api/skills/install --auth none --json '{"source": "'"$S"'"}' --expect 401
  control-agent-server api GET /api/skills/installed --auth none --expect 401
  control-agent-server api GET /api/skills/installed/qa-f25-skill --auth none --expect 401
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --auth none --json '{"enabled": false}' --expect 401
  control-agent-server api DELETE /api/skills/installed/qa-f25-skill --auth none --expect 401
  control-agent-server api POST /api/skills/installed/qa-f25-skill/refresh --auth none --expect 401
  control-agent-server api GET /api/skills/marketplace --auth none --expect 401 --save F25.auth/marketplace
  test ! -e "$I/qa-f25-skill"
  ```
  所有答案 `401 {"detail": "Unauthorized"}`，没有任何东西安装。
- **真正的公共存储库(`F25.public-repo`).** 同步反对
  `github.com/OpenHands/extensions`（网络），将其克隆到公共缓存中，然后从该克隆加载公共层。

  需求：`network`
  ```sh
  control-agent-server api POST /api/skills/sync --timeout 240 --expect 200 --check status eq success --save F25.public-repo/sync
  test -d "$PUB/.git"
  test -s "$PUB/.plugin/marketplace.json"
  control-agent-server api POST /api/skills --json '{"load_public": true, "load_user": false, "load_project": false, "load_org": false}' \
    --timeout 240 --expect 200 --quiet --check sources.sdk_base ge 1 --check skills len-ge 1 \
    --check skills contains "$PUB/skills/" --save F25.public-repo/catalog
  ```
  第一同步倒数第二个克隆仓库（还没有克隆，所以这是克隆路径，而不是拉取）。 克隆持有`.plugin/marketplace.json`，而公众层列出`source`是`SKILL.md`的技能。 这是网络安排步骤的子弹
  `F25.marketplace-public`; 没有网络，这里就失败了。
- **公共市场目录 (`F25.marketplace-public`)，已知错误。**根据 `F25.public-repo` 制作的真实 `OpenHands/extensions` 存储库的克隆读取目录。

  需要：`F25.public-repo`
  ```sh
  control-agent-server api GET /api/skills/marketplace --timeout 180 --expect 200 --check skills len-ge 1 --save F25.marketplace-public/catalog  # bug：状态 eq 200 && response.body.skills len-eq 0
  ```
  该克隆持有 `.plugin/marketplace.json` 包含大约70个插件条目，其源代码为  `./skills/<name>`因此，目录应该列出它们。 今天返回 `{"skills": []}`: `_fetch_catalog_entries` 放弃时
  `marketplaces/default.json` 缺失（存储库提供
  `marketplaces/openhands-extensions.json` 和 `large-codebase.json` 代替），然后尝试 `Marketplace.load`，然后将空列表缓存 5 分钟。
- **项目技能 (`F25.catalog-project`).**仅加载测试夹具项目。
  ```sh
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_org": false, "project_dir": "'"$P"'"}' \
    --expect 200 --check sources.project eq 3 --check sources.sdk_base eq 0 --check sources.org eq 0 \
    --check sources.sandbox eq 0 --check sources.registered_marketplaces eq 0 --check skills len-eq 3 \
    --check skills contains '"name": "qa-f25-proj-skill", "type": "agentskills"' \
    --check skills contains '"name": "qa-legacy", "type": "knowledge"' \
    --check skills contains '"name": "agents", "type": "repo"' \
    --check skills contains '"triggers": ["qa-legacy"]' --check skills contains '"triggers": ["qa-f25-proj-skill"]' \
    --check skills contains '"is_agentskills_format": true' \
    --check skills not-contains QA_BAD_NAME_BODY --save F25.catalog-project/project
  ```
  有三个技能：AgentSkills目录（包含`is_agentskills_format`和True，名称作为触发器），`.openhands/skills/qa-legacy.md`和`AGENTS.md`（名称为`agents`，总是开启）。 `Not_Kebab` 技能仅在服务器日志中发出警告就跳过了。 请求仍然成功。
- **用户技能和优先级 (`F25.catalog-user-precedence`)。**加载用户层，然后加载项目的用户层。
  ```sh
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check sources.sdk_base eq 2 \
    --check skills contains '"name": "qa-f25-user", "type": "agentskills", "content": "QA_USER_BODY' \
    --check skills contains "\"source\": \"$U/qa-f25-user/SKILL.md\"" --save F25.catalog-user-precedence/user
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_org": false, "project_dir": "'"$P"'"}' \
    --expect 200 --check skills contains '"name": "qa-f25-user"' \
    --check skills contains "\"source\": \"$P/.agents/skills/qa-f25-proj-skill/SKILL.md\"" \
    --check skills not-contains QA_USER_COPY --save F25.catalog-user-precedence/project-wins
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_project": false, "load_org": false}' \
    --expect 200 --check skills len-eq 0
  ```
  用户层级拥有两个 `HOME` 技能。 与项目一起，项目的
  `qa-f25-proj-skill` 替换用户副本（`QA_USER_COPY` 消失）； 目录中的每个源都是空的。
- **测试和组织源(`F25.catalog-server-sources`).**暴露URLs，然后两个组织仓库（一个不可达）。
  ```sh
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_project": false, "load_org": false, "sandbox_config": {"exposed_urls": [{"name": "WORKER_1", "url": "http://localhost:12000", "port": 12000}, {"name": "VSCODE", "url": "http://localhost:12001", "port": 12001}]}}' \
    --expect 200 --check sources.sandbox eq 1 --check skills len-eq 1 --check skills.0.name eq work_hosts \
    --check skills.0.type eq repo --check skills.0.source missing \
    --check skills.0.content contains 'http://localhost:12000 (port 12000)' --check skills.0.content not-contains 12001 \
    --save F25.catalog-server-sources/sandbox
  ORG='[{"repository": "qa/org", "provider": "github", "org_repo_url": "file://'"$G"'", "org_name": "qa-f25-org"}, {"repository": "qa/gone", "provider": "github", "org_repo_url": "file:///nonexistent/qa-f25-gone", "org_name": "qa-f25-gone"}]'
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_project": false, "load_org": true, "org_configs": '"$ORG"'}' \
    --expect 200 --check sources.org eq 1 --check skills len-eq 1 --check skills.0.name eq qa-f25-src-skill \
    --save F25.catalog-server-sources/org
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_project": false, "load_org": false, "org_configs": '"$ORG"'}' \
    --expect 200 --check sources.org eq 0 --check skills len-eq 0
  ```
  只有`WORKER_*`的名字才能成为`work_hosts`技能（无来源，总是开启） 组织仓库浅克隆，`skills/` 目录加载，不可达的目录则默默跳过，`load_org: false` 两者都忽略。
- **请求验证 (`F25.catalog-validation`).**送来畸形尸体。
  ```sh
  control-agent-server api POST /api/skills --json '{"load_public": "x"}' --expect 422 --check detail.0.loc contains load_public
  control-agent-server api POST /api/skills --json '{"load_public": false, "org_configs": [{"repository": "qa/org", "provider": "github", "org_repo_url": "file:///x"}]}' \
    --expect 422 --check detail.0.loc contains org_name
  control-agent-server api POST /api/skills --json '{"load_public": false, "registered_marketplaces": [{"name": "qa", "source": "/x", "repo_path": "../up"}]}' \
    --expect 422 --check detail.0.msg contains traversal --save F25.catalog-validation/repo-path
  ```
  每个都是422，指代违规字段。
- **从本地目录安装 (`F25.install-local`)。**安装测试夹具技能并在每个视图中回读它。
  ```sh
  control-agent-server api POST /api/skills/install --json '{"source": "'"$S"'"}' --expect 200 \
    --check name eq qa-f25-skill --check enabled eq true --check source eq "$S" --check resolved_ref missing \
    --check install_path eq "$I/qa-f25-skill" --check installed_at exists --save F25.install-local/install
  test -f "$I/qa-f25-skill/SKILL.md"
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --check extensions.qa-f25-skill.source eq "$S"
  control-agent-server api GET /api/skills/installed --expect 200 --check skills len-eq 1 --check skills.0.name eq qa-f25-skill
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check enabled eq true \
    --check description contains QA_SKILL_MARKER --save F25.install-local/get
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check sources.sdk_base eq 3 --check skills contains "\"source\": \"$I/qa-f25-skill/SKILL.md\""
  ```
  响应、列表、单视图和 `.installed.json` 一致。 用户层级从两个技能增加到三个技能，新技能来自已安装的副本。
- **禁用和启用 (`F25.enable-disable`)。**切换已安装的技能。
  ```sh
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": false}' --expect 200 \
    --check name eq qa-f25-skill --check enabled eq false --save F25.enable-disable/disable
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check enabled eq false
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --check extensions.qa-f25-skill.enabled eq false
  test -f "$I/qa-f25-skill/SKILL.md"
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check skills not-contains '"name": "qa-f25-skill"' --save F25.enable-disable/catalog-disabled
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": true}' --expect 200 --check enabled eq true
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": true}' --expect 200 --check enabled eq true
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check skills contains '"name": "qa-f25-skill"'
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{}' --expect 422 --check detail.0.loc contains enabled
  ```
  该技能被禁用，但会留在磁盘上，但不会进入目录。 启用（两次：幂等）就回来了。 没有`enabled`的身体是422。
- **已安装 (`F25.install-conflict`)。**重新安装不带和带
  `force`.
  ```sh
  T1=$(control-agent-server api GET /api/skills/installed/qa-f25-skill --field installed_at)
  control-agent-server api POST /api/skills/install --json '{"source": "'"$S"'"}' --expect 409 \
    --check detail contains force=true --save F25.install-conflict/conflict
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check installed_at eq "$T1"
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": false}' --expect 200
  control-agent-server api POST /api/skills/install --json '{"source": "'"$S"'", "force": true}' --expect 200 \
    --check enabled eq false --check installed_at ne "$T1" --save F25.install-conflict/force
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check enabled eq false --check installed_at ne "$T1"
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": true}' --expect 200 --check enabled eq true
  ```
  409 `installed_at` 不变。 强制重新安装会得到一个新的
  `installed_at` 并保持技能禁用，直到再次启用。
- **安装错误 (`F25.install-errors`)。**无法获取资源，然后技能无效。
  ```sh
  control-agent-server api POST /api/skills/install --json '{"source": "/nonexistent/qa-f25"}' --expect 400 --check detail contains 'Failed to fetch'
  control-agent-server api POST /api/skills/install --json '{"source": "foo"}' --expect 400
  control-agent-server api POST /api/skills/install --json '{"source": "'"$S"'", "repo_path": "../.."}' --expect 400
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/qa-f25-nomd"'"}' --expect 422 \
    --check detail contains SKILL.md --save F25.install-errors/no-skill-md
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/qa-f25-mismatch"'"}' --expect 422
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/Qa_Bad"'"}' --expect 422
  control-agent-server api POST /api/skills/install --json '{"source": ""}' --expect 422 --check detail.0.loc contains source
  control-agent-server api GET /api/skills/installed --expect 200 --check skills len-eq 1
  test ! -e "$I/qa-f25-other" && test ! -e "$I/Qa_Bad" && test ! -e "$I/qa-f25-nomd"
  ```
  请求失败 `400 Failed to fetch skill source...`，无效技能
  `422 Invalid skill. Ensure the source contains a valid SKILL.md.`，而商店仍然只保留`qa-f25-skill`。
- **格式错误前置元数据 (`F25.install-bad-frontmatter`).**安装 YAML 不解析的 SKILL.md。
  ```sh
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/qa-f25-badyaml"'"}' --expect 422 \
    --save F25.install-bad-frontmatter/install
  test ! -e "$I/qa-f25-badyaml"
  ```
  一个无法解析的技能是文档中的
  `422 Invalid skill. Ensure the source contains a valid SKILL.md.`，与其他无效技能一样：安装加载程序将 YAML 错误变成
  `SkillValidationError`，并且没有任何内容复制到商店中。
- **从 git 源安装 (`F25.install-git`)。**通过`file://`安装`qa-f25-src`存储库的skill目录。
  ```sh
  H1=$(git -C "$G" rev-parse HEAD)
  control-agent-server api POST /api/skills/install --json '{"source": "file://'"$G"'", "repo_path": "skills/qa-f25-src-skill"}' \
    --expect 200 --check name eq qa-f25-src-skill --check source eq "file://$G" \
    --check repo_path eq skills/qa-f25-src-skill --check resolved_ref eq "$H1" --save F25.install-git/install
  control-agent-server api GET /api/skills/installed/qa-f25-src-skill --expect 200 --check resolved_ref eq "$H1"
  test -f "$I/qa-f25-src-skill/SKILL.md"
  ls -d "$AGENT_SERVER_VERIFY_RUN"/home/.openhands/cache/extensions/qa-f25-src-*/.git
  ```
  `file://` 被视为 git URL：存储库被克隆到扩展缓存中，`resolved_ref` 是测试夹具的 HEAD。
- **SDK 消费者 (`F25.sdk-load-skills`).** `RemoteWorkspace` 与
  `working_dir` 设置为测试夹具项目通过服务器加载技能，就像云对话一样，通过 `exec`。

  需要：`F25.install-local`、`F25.install-git`
  ```sh
  cat > "$F/qa_f25_sdk_skills.py" <<'PY'
  import json
  import os
  import sys

  from openhands.sdk.workspace import RemoteWorkspace

  project = sys.argv[1]
  ws = RemoteWorkspace(host=os.environ["AGENT_SERVER_URL"], api_key=os.environ["SESSION_API_KEY"], working_dir=project)
  skills, ctx = ws.load_skills_from_agent_server(load_public=False, load_org=False)
  by_name = {s.name: s for s in skills}
  print(json.dumps({n: [type(s.trigger).__name__, s.source] for n, s in sorted(by_name.items())}))
  assert set(by_name) == {"agents", "qa-legacy", "qa-f25-proj-skill", "qa-f25-user", "qa-f25-skill", "qa-f25-src-skill"}, by_name
  assert type(by_name["qa-legacy"].trigger).__name__ == "KeywordTrigger"
  assert by_name["agents"].trigger is None
  assert by_name["qa-f25-proj-skill"].source.startswith(project), by_name["qa-f25-proj-skill"].source
  assert "/skills/installed/qa-f25-skill/" in by_name["qa-f25-skill"].source
  assert ctx.load_public_skills is False
  assert {s.name for s in ctx.skills} == set(by_name)
  print("QA_F25_SDK_OK")
  PY
  control-agent-server exec --expect-output QA_F25_SDK_OK --save F25.sdk-load-skills/program -- uv run python "$F/qa_f25_sdk_skills.py" "$P"
  ```
  SDK 发送带有它被给予的标志的 `project_dir` = `working_dir`，并且得到六个项目、用户和安装的技能（项目副本的 `qa-f25-proj-skill` 赢了）。 关键词触发器在转换过程中存活
  `AGENTS.md` 一直保持在线状态，返回的上下文与 `load_public_skills` 有相同的技能 False。
- **从 GitHub (`F25.install-github`) 安装。**安装公众号
  `skills/github` 来自 github.com（网络）的技能以有效的形式，读回来，卸载它。

  需求：`network`
  ```sh
  control-agent-server api POST /api/skills/install --json '{"source": "github:OpenHands/extensions", "repo_path": "skills/github"}' \
    --timeout 240 --expect 200 --check name eq github --check source eq github:OpenHands/extensions \
    --check repo_path eq skills/github --check resolved_ref matches '^[0-9a-f]{40}$' --save F25.install-github/install
  control-agent-server api GET /api/skills/installed/github --expect 200 --check resolved_ref matches '^[0-9a-f]{40}$'
  test -f "$I/github/SKILL.md"
  control-agent-server api DELETE /api/skills/installed/github --expect 200
  control-agent-server api GET /api/skills/installed/github --expect 404
  ```
  简写名称指代仓库和 `repo_path` 技能目录仓库被克隆到了扩展缓存中 `resolved_ref` 是它的 HEAD 提交，技能又回到了商店。 这是网络安排步骤的子弹 `F25.install-documented-sources`它证明了 github.com 是可到达的 `skills/github` 安装。
- **记录的安装源 (`F25.install-documented-sources`)，已知错误。**在 OpenAPI 描述的每个 GitHub 中安装相同的技能
  `InstallSkillRequest.source` 做广告。

  需要：`F25.install-github`
  ```sh
  DOC=$(control-agent-server api GET /openapi.json --auth none --field components.schemas.InstallSkillRequest.properties.source.description)
  for SRC in github:OpenHands/extensions/skills/github https://github.com/OpenHands/extensions/tree/main/skills/github; do
    case "$DOC" in
      *"'$SRC'"*)
        control-agent-server api POST /api/skills/install --json '{"source": "'"$SRC"'"}' --timeout 240 --expect 200 \
          --check name eq github --save F25.install-documented-sources/documented  # bug: status eq 422 && response.body.detail eq '技能无效。 确保源包含有效的 SKILL.md。
        control-agent-server api DELETE /api/skills/installed/github --expect 200
        ;;
    esac
  done
  ```
  `F25.install-github` 证明当子路径明确时，技能会从 github.com 安装。 速记应该安装相同的技能，但目前回答 422：安装管理器处理省略的
  `repo_path` 作为存储库根安装并从名为 `extensions` 的临时目录加载获取的 `github` 技能。 技能验证拒绝结果目录/名称不匹配。 此回归在 [OpenHands/software-智能体-SDK#6184](https://github.com/OpenHands/software-agent-sdk/issues/6184) 中跟踪。 早期的解析器拒绝已在 #5909 中修复； 当前的速记克隆
  `owner/repo` 并将 `<path>` 用作 `repo_path`（同时传递两者是 `400`）。 该循环还覆盖 `/tree/<ref>/<path>` URL，以防再次记录； 该表单未被解析（它将被克隆为
  `.../tree/main/skills/github.git`），所以不做广告。
- **从源刷新 (`F25.refresh`)。**提交 git 源并编辑本地源，然后刷新两者。

  需要：`F25.install-local`、`F25.install-git`
  ```sh
  control-agent-server fixture git-source --name qa-f25-src
  H2=$(git -C "$G" rev-parse HEAD)
  test "$H2" != "$H1"
  control-agent-server api POST /api/skills/installed/qa-f25-src-skill/refresh --expect 200 \
    --check message eq "Skill 'qa-f25-src-skill' updated" --check skill.resolved_ref eq "$H2" \
    --check skill.repo_path eq skills/qa-f25-src-skill --save F25.refresh/git
  control-agent-server api GET /api/skills/installed/qa-f25-src-skill --expect 200 --check resolved_ref eq "$H2"
  grep -q Revision "$I/qa-f25-src-skill/SKILL.md"
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": false}' --expect 200
  sed -i 's/^description: .*/description: QA fixture skill v2/' "$S/SKILL.md"
  control-agent-server api POST /api/skills/installed/qa-f25-skill/refresh --expect 200 \
    --check skill.description eq 'QA fixture skill v2' --check skill.enabled eq false --save F25.refresh/local
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check description eq 'QA fixture skill v2' --check enabled eq false
  grep -q 'QA fixture skill v2' "$I/qa-f25-skill/SKILL.md"
  control-agent-server api PATCH /api/skills/installed/qa-f25-skill --json '{"enabled": true}' --expect 200
  ```
  第二 `fixture git-source` 调用会提交更改。 刷新会重新安装 HEAD. 编辑后的本地描述在响应、单视图和安装的文件中到达，技能在刷新后保持禁用（之后会重新启用）。
- **在参考处安装 (`F25.install-ref`)。** Reinstall the git skill pinned to the first commit, then refresh it.

  需要：`F25.refresh`
  ```sh
  control-agent-server api POST /api/skills/install --json '{"source": "file://'"$G"'", "repo_path": "skills/qa-f25-src-skill", "ref": "'"$H1"'", "force": true}' \
    --expect 200 --check resolved_ref eq "$H1" --check enabled eq true --save F25.install-ref/pinned
  control-agent-server api GET /api/skills/installed/qa-f25-src-skill --expect 200 --check resolved_ref eq "$H1"
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --check extensions.qa-f25-src-skill.requested_ref eq "$H1"
  if grep -q Revision "$I/qa-f25-src-skill/SKILL.md"; then exit 1; fi
  control-agent-server api POST /api/skills/installed/qa-f25-src-skill/refresh --expect 200 \
    --check skill.resolved_ref eq "$H2" --save F25.install-ref/refresh
  grep -q Revision "$I/qa-f25-src-skill/SKILL.md"
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --check extensions.qa-f25-src-skill.requested_ref missing
  ```
  `H1`端点已弃用。 `ref` 会被重新安装，按照设计（最新版本），所以技能又回到了 `Revision`
  `H2` 和 `requested_ref` 消失了。
- **未知参考文献 (`F25.install-unknown-ref`).**请求两个 git 源都没有的引用：首先请求从未克隆的源，然后请求缓存的 `qa-f25-src` 源。

  需要：`F25.install-git`
  ```sh
  G2=$(control-agent-server fixture git-source --name qa-f25-ref --print-path)
  control-agent-server api POST /api/skills/install --json '{"source": "file://'"$G2"'", "repo_path": "skills/qa-f25-ref-skill", "ref": "qa-f25-no-such-ref"}' \
    --expect 400 --check detail contains 'Failed to fetch' --save F25.install-unknown-ref/first-clone
  test ! -e "$I/qa-f25-ref-skill"
  T2=$(control-agent-server api GET /api/skills/installed/qa-f25-src-skill --field installed_at)
  ls -d "$AGENT_SERVER_VERIFY_RUN"/home/.openhands/cache/extensions/qa-f25-src-*/.git
  control-agent-server api POST /api/skills/install --json '{"source": "file://'"$G"'", "repo_path": "skills/qa-f25-src-skill", "ref": "qa-f25-no-such-ref", "force": true}' \
    --expect 400 --save F25.install-unknown-ref/cached
  control-agent-server api GET /api/skills/installed/qa-f25-src-skill --expect 200 --check installed_at eq "$T2"
  ```
  第一个克隆失败了(`git clone --branch qa-f25-no-such-ref`)，所以安装是`400`，没有安装。 `qa-f25-src`克隆项在扩展缓存中。 它还会返回 `400`，并保留已安装的副本
  `H2`，及其先前的 `installed_at` 值。 在签出之前会获取不在缓存中的有效引用。 如果获取失败，安装将返回
  `400`并保留先前的安装。
- **刷新已消失的源 (`F25.refresh-unfetchable`)。**从临时目录安装，删除它，刷新。
  ```sh
  mkdir -p "$F/tmp/qa-f25-gone"
  printf -- '---\nname: qa-f25-gone\ndescription: QA source that disappears\n---\nGone soon\n' > "$F/tmp/qa-f25-gone/SKILL.md"
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/tmp/qa-f25-gone"'"}' --expect 200
  rm -rf "$F/tmp/qa-f25-gone"
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/tmp/qa-f25-gone"'"}' --expect 400 --check detail contains 'Failed to fetch'
  control-agent-server api POST /api/skills/installed/qa-f25-gone/refresh --expect 400,422 --save F25.refresh-unfetchable/refresh
  control-agent-server api GET /api/skills/installed/qa-f25-gone --expect 200 --check enabled eq true
  ```
  源码无法获取：再次从消失的路径安装是
  `400 Failed to fetch skill source`（正控制），因此刷新路由也会报告客户端错误并保留已安装的副本：
  `refresh_skill_endpoint` 将 `SkillFetchError`/`ExtensionFetchError` 映射到
  `400` 和 `SkillValidationError` 到 `422`，与安装一样。 `F25.self-heal`（来源`local`）发现的技能没有任何可借鉴之处，并且`400`也是如此。
- **未知且无效的名称 (`F25.name-errors`)。**解决未安装的技能，然后命名打破模式。
  ```sh
  control-agent-server api GET /api/skills/installed/qa-f25-ghost --expect 404 --check detail eq "Skill 'qa-f25-ghost' is not installed"
  control-agent-server api PATCH /api/skills/installed/qa-f25-ghost --json '{"enabled": false}' --expect 404
  control-agent-server api DELETE /api/skills/installed/qa-f25-ghost --expect 404
  control-agent-server api POST /api/skills/installed/qa-f25-ghost/refresh --expect 404 --save F25.name-errors/refresh-unknown
  control-agent-server api GET /api/skills/installed/Bad_Name --expect 422 --check detail.0.loc contains skill_name
  control-agent-server api PATCH /api/skills/installed/Bad_Name --json '{"enabled": false}' --expect 422
  control-agent-server api DELETE /api/skills/installed/Bad_Name --expect 422
  control-agent-server api POST /api/skills/installed/Bad_Name/refresh --expect 422 --save F25.name-errors/bad-name
  ```
  不知名的名字是`404 Skill '<name>' is not installed`； `Bad_Name` 在所有四个路由上都失败了路径验证 (`string_pattern_mismatch`)。
- **手工复制和手工删除的目录(`F25.self-heal`)。**将技能复制到商店中，阅读它，然后手动将其删除。
  ```sh
  mkdir -p "$I/qa-f25-manual"
  printf -- '---\nname: qa-f25-manual\ndescription: QA manual copy\n---\nManual\n' > "$I/qa-f25-manual/SKILL.md"
  control-agent-server api GET /api/skills/installed/qa-f25-manual --expect 404
  control-agent-server api GET /api/skills/installed --expect 200 --check skills contains '"name": "qa-f25-manual"' --save F25.self-heal/discovered
  control-agent-server api GET /api/skills/installed/qa-f25-manual --expect 200 --check source eq local --check enabled eq true
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --check extensions.qa-f25-manual.source eq local
  rm -rf "$I/qa-f25-manual"
  control-agent-server api GET /api/skills/installed --expect 200 --check skills not-contains qa-f25-manual
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --not-contains qa-f25-manual
  ```
  单视图不同步元数据，因此直到列表调用记录目录与源 `local` 时，它才会 404。 删除目录后，下次调用会修剪条目。
- **同步公共存储库 (`F25.sync`).**翻译：缓存的克隆被本地 `extensions` 存储库的克隆替换，因此同步获取
  from a local origin instead of GitHub through the same code path.
  ```sh
  rm -rf "$PUB"
  git clone -q "$E" "$PUB"
  control-agent-server api POST /api/skills/sync --expect 200 --check status eq success
  Q='{"load_public": true, "load_user": false, "load_project": false, "load_org": false, "marketplace_path": null}'
  control-agent-server api POST /api/skills --json "$Q" --expect 200 --check skills contains '"name": "qa-f25-pub"' --check skills not-contains qa-f25-pub-new
  mkdir -p "$E/skills/qa-f25-pub-new"
  printf -- '---\nname: qa-f25-pub-new\ndescription: QA new upstream skill\n---\nQA_PUBLIC_NEW\n' > "$E/skills/qa-f25-pub-new/SKILL.md"
  git -C "$E" add -A
  git -C "$E" commit -q -m 'Add a new upstream skill'
  control-agent-server api POST /api/skills --json "$Q" --expect 200 --check skills not-contains qa-f25-pub-new
  control-agent-server api POST /api/skills/sync --expect 200 --check status eq success \
    --check message eq 'Skills repository synced successfully' --save F25.sync/sync
  test "$(git -C "$PUB" rev-parse HEAD)" = "$(git -C "$E" rev-parse HEAD)"
  control-agent-server api POST /api/skills --json "$Q" --expect 200 \
    --check skills contains '"name": "qa-f25-pub-new", "type": "agentskills", "content": "QA_PUBLIC_NEW' --save F25.sync/after-sync
  control-agent-server api POST /api/skills --json '{"load_public": true, "load_user": false, "load_project": false, "load_org": false}' \
    --expect 200 --check skills contains '"name": "qa-f25-pub"' --check skills not-contains qa-f25-pub-new
  ```
  在同步之前，新的上游技能会被隐藏，这需要60秒的在途缓存（服务器的计时器，因此没有等待）。 在它之后，克隆的 HEAD 等于原点的，技能列表。 使用默认值
  `marketplace_path` 仅加载 `marketplaces/default.json` 的条目，因此
  `qa-f25-pub-new` 留在外面。
- **配置文件启动目录(`F25.profile-catalog`)。**使用同步配方和用户测试夹具中的本地公共存储库。 配置文件目录不需要项目目录并显式标记两个源。

  需要：`F25.sync`
  ```sh
  mkdir -p "$P/.agents/skills/qa-f25-project-only"
  printf -- '---\nname: qa-f25-project-only\ndescription: QA project-only skill\n---\nQA_PROJECT_ONLY\n' > "$P/.agents/skills/qa-f25-project-only/SKILL.md"
  control-agent-server api POST /api/skills --json '{"load_public":false,"load_user":false,"load_org":false,"project_dir":"'"$P"'"}' \
    --expect 200 --check skills contains qa-f25-project-only
  PROFILE_CATALOG=$(control-agent-server api GET /api/skills/catalog --expect 200 \
    --save F25.profile-catalog/catalog --field skills)
  jq -e 'any(.name == "qa-f25-pub" and .origin == "public") and any(.name == "qa-f25-user" and .origin == "user") and all(.origin == "public" or .origin == "user") and all(.name != "qa-f25-project-only")' <<< "$PROFILE_CATALOG"
  rm -r "$P/.agents/skills/qa-f25-project-only"
  ```
  阳性对照显示了项目技能通过了工作区 catalog. 该目录包括公共和用户测试夹具带有预期的起源，但省略了该项目的技能。
- **同步没有可到达的原点 (`F25.sync-offline`)。**将克隆体的原点指向缺失的路径，同步，退出时恢复它。

  需要：`F25.sync`
  ```sh
  trap 'git -C "$PUB" remote set-url origin "$E"' EXIT
  git -C "$PUB" remote set-url origin "$F/qa-f25-unreachable"
  if git -C "$PUB" fetch -q origin 2>/dev/null; then false; fi
  control-agent-server api POST /api/skills/sync --expect 200 --check status eq error --save F25.sync-offline/sync
  ```
  源不可达（`git fetch` 空白符在同步之前失败），服务器的请求也失败了（日志显示 `Failed to fetch updates`），强制刷新没有发生，响应说 `{"status": "error", "message": "Failed to sync skills repository"}`。 b同步问
  `update_skills_repository` 用于严格更新，因此失败的获取不会报告为同步； 过时的克隆保留在磁盘上，并且技能加载继续使用它。 一旦克隆存在，同样的情况也适用于GitHub。
- **注册市场技能 (`F25.catalog-registered-marketplace`)。**在请求中注册`qa-f25-mk` 测试夹具（公共层现在是离线替代层）。

  需要：`F25.sync`
  ```sh
  control-agent-server api POST /api/skills --json '{"load_public": true, "load_user": false, "load_project": false, "load_org": false, "registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": true}]}' \
    --expect 200 --check sources.registered_marketplaces eq 3 --check skills contains '"name": "qa-f25-mk-skill"' \
    --check skills contains '"name": "qa-f25-mk-plugin-skill"' --check skills contains '"name": "qa-f25-mk-plugin:qa-hello"' \
    --check skills contains '"name": "qa-f25-pub"' --save F25.catalog-registered-marketplace/auto-load
  control-agent-server api POST /api/skills --json '{"load_public": true, "load_user": false, "load_project": false, "load_org": false, "registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": ["qa-f25-mk-skill"]}]}' \
    --expect 200 --check sources.registered_marketplaces eq 1 --check skills contains '"name": "qa-f25-mk-skill"' \
    --check skills not-contains qa-f25-mk-plugin
  control-agent-server api POST /api/skills --json '{"load_public": true, "load_user": false, "load_project": false, "load_org": false, "registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": false}]}' \
    --expect 200 --check sources.registered_marketplaces eq 0
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": false, "load_project": false, "load_org": false, "registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": true}]}' \
    --expect 200 --check sources.registered_marketplaces eq 0 --check skills len-eq 0
  ```
  `auto_load: true` 在公共技能旁边添加独立技能、插件技能和插件命令（名为 `qa-f25-mk-plugin:qa-hello` 的 `knowledge` 技能）； 名单仅选择独立技能；
  `false` 或 `load_public: false` 不添加任何内容。
- **在对话中安装的技能`F25.conversation-activation`).** 启动 DeepSeek 保存设置中的会话，其第一个消息携带安装的技能触发词。

  需要：`F25.install-local`
  需求：`llm`
  ```sh
  control-agent-server llm preset deepseek
  CID=$(control-agent-server conversation start --tools none --no-autotitle \
    --prompt 'qa-f25-skill: reply with one short sentence.' --wait --until finished,idle --timeout 300 --print-id)
  control-agent-server api GET "/api/conversations/$CID" --expect 200 \
    --check activated_knowledge_skills contains qa-f25-skill --save F25.conversation-activation/conversation
  control-agent-server conversation events "$CID" --kinds MessageEvent --contains '"activated_skills": ["qa-f25-skill"]' \
    --save F25.conversation-activation/message
  control-agent-server conversation events "$CID" --kinds MessageEvent --contains 'skills/installed/qa-f25-skill/SKILL.md'
  control-agent-server conversation events "$CID" --kinds SystemPromptEvent --contains '<name>qa-f25-skill</name>'
  control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=all --until-kind MessageEvent \
    --until activated_skills.0=qa-f25-skill --duration 15 --save F25.conversation-activation/ws
  ```
  对话列出了系统提示词的技能
  `<available_skills>`，用户`MessageEvent`有`activated_skills：
  ["qa-f25-skill"]` with the skill body injected from the installed copy's
  路径（在 REST 事件搜索和 WebSocket 重放中类似），以及
  `activated_knowledge_skills`为其命名。 模型的回复未断言。
- **通过`invoke_skill`（`F25.invoke-skill`）调用的技能。**安装不带触发器的 AgentSkill，然后要求 DeepSeek 对话按名称调用它； 之后卸载它。

  需求：`llm`
  ```sh
  control-agent-server llm preset deepseek
  mkdir -p "$F/qa-f25-invoke"
  printf -- '---\nname: qa-f25-invoke\ndescription: QA skill without triggers\n---\nQA_INVOKE_BODY\n' > "$F/qa-f25-invoke/SKILL.md"
  control-agent-server api POST /api/skills/install --json '{"source": "'"$F/qa-f25-invoke"'"}' --expect 200 --check name eq qa-f25-invoke
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check skills contains '"name": "qa-f25-invoke", "type": "agentskills", "content": "QA_INVOKE_BODY' \
    --check skills contains '"triggers": [], "source": "'"$I/qa-f25-invoke/SKILL.md"'"'
  CID2=$(control-agent-server conversation start --tools none --no-autotitle \
    --prompt 'Call the invoke_skill tool with name "qa-f25-invoke", then finish.' --wait --until finished,idle --timeout 300 --print-id)
  control-agent-server conversation events "$CID2" --kinds SystemPromptEvent --contains '<name>qa-f25-invoke</name>'
  control-agent-server conversation events "$CID2" --kinds SystemPromptEvent --contains '"kind": "InvokeSkillTool"'
  control-agent-server conversation events "$CID2" --kinds ActionEvent --contains '"name": "qa-f25-invoke", "kind": "InvokeSkillAction"' \
    --save F25.invoke-skill/action
  control-agent-server conversation events "$CID2" --kinds ObservationEvent --contains '"skill_name": "qa-f25-invoke"' \
    --save F25.invoke-skill/observation
  control-agent-server conversation events "$CID2" --kinds ObservationEvent --contains '"skill_name": "qa-f25-invoke"' --full \
    | grep QA_INVOKE_BODY > /dev/null
  control-agent-server conversation events "$CID2" --kinds MessageEvent --contains '"activated_skills": ["qa-f25-invoke"]' --expect-count 0
  control-agent-server api GET "/api/conversations/$CID2" --expect 200 --check invoked_skills contains qa-f25-invoke \
    --check activated_knowledge_skills not-contains qa-f25-invoke --save F25.invoke-skill/conversation
  control-agent-server api DELETE /api/skills/installed/qa-f25-invoke --expect 200
  ```
  该技能没有触发器（）`"triggers": []`, 所以提示词命名它没有任何效果（no `MessageEvent` 它有吗 `activated_skills`): 系统提示词列出它 `<available_skills>` 并带有自动附加的 `InvokeSkillTool`, the 智能体's `InvokeSkillAction` 返回一个 `InvokeSkillObservation` (`skill_name`) 与技能体及其安装位置，以及记录该技能的对话记录
  仅 `invoked_skills`。 模型的回复未断言。
- **重新启动 (`F25.restart-persist`)。**禁用一项技能后重新启动。

  需要：`F25.refresh`
  ```sh
  control-agent-server api PATCH /api/skills/installed/qa-f25-src-skill --json '{"enabled": false}' --expect 200
  control-agent-server restart
  control-agent-server doctor
  control-agent-server api GET /api/skills/installed --expect 200 --check skills contains '"name": "qa-f25-skill"' \
    --check skills contains '"name": "qa-f25-src-skill"' --save F25.restart-persist/list
  control-agent-server api GET /api/skills/installed/qa-f25-src-skill --expect 200 --check enabled eq false --check resolved_ref eq "$H2"
  control-agent-server api GET /api/skills/installed/qa-f25-skill --expect 200 --check enabled eq true --check description eq 'QA fixture skill v2'
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check skills contains '"name": "qa-f25-skill"' --check skills not-contains '"name": "qa-f25-src-skill"'
  ```
  安装状态存储在磁盘上，因此重启后的服务器会报告相同的技能、标志和提交，而被禁用的技能则不会出现在目录中。 此外，重启还会清空在途的元数据缓存，即 in-process catalog caches
  `F25.marketplace-catalog` 依赖。
- **默认市场（`F25.catalog-server-marketplaces`）。** 重启时，使用配置文件中注册的 `qa-f25-mk` 测试夹具，然后按名称覆盖它，并从请求中添加第二个注册。
  ```sh
  control-agent-server restart --config-json '{"registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": ["qa-f25-mk-skill"]}]}'
  control-agent-server doctor
  B='"load_public": true, "load_user": false, "load_project": false, "load_org": false'
  control-agent-server api POST /api/skills --json "{$B}" --expect 200 --check sources.registered_marketplaces eq 1 \
    --check skills contains '"name": "qa-f25-mk-skill"' --check skills not-contains qa-f25-mk-plugin \
    --save F25.catalog-server-marketplaces/config-only
  control-agent-server api POST /api/skills --json "{$B"', "registered_marketplaces": [{"name": "qa-f25-mk", "source": "'"$M"'", "auto_load": false}]}' \
    --expect 200 --check sources.registered_marketplaces eq 0 --check skills not-contains qa-f25-mk \
    --save F25.catalog-server-marketplaces/override
  control-agent-server api POST /api/skills --json "{$B"', "registered_marketplaces": [{"name": "qa-f25-mk-2", "source": "'"$M"'", "auto_load": ["qa-f25-mk-plugin"]}]}' \
    --expect 200 --check sources.registered_marketplaces eq 3 --check skills contains '"name": "qa-f25-mk-skill"' \
    --check skills contains '"name": "qa-f25-mk-plugin-skill"' --save F25.catalog-server-marketplaces/union
  control-agent-server restart --reset-config
  control-agent-server api POST /api/skills --json "{$B}" --expect 200 --check sources.registered_marketplaces eq 0
  ```
  配置注册本身就添加了其选择的独立技能。 一个名为`qa-f25-mk`的请求条目取代了它（这里用`auto_load: false`，所以没有变化）。 旁边添加了一个请求条目，名称不同（插件的技能和命令，加上配置的技能）。 在 `--reset-config` 后，服务器没有默认注册。 这是相同的归并
  `OH_REGISTERED_MARKETPLACES` 供稿。
- **市场目录 (`F25.marketplace-catalog`).**翻译过来就是：公共克隆是本地替代品，它有`marketplaces/default.json`。 阅读目录，安装其条目，然后再阅读。

  需要：`F25.sync`
  ```sh
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills len-eq 1 --check skills.0.name eq qa-f25-pub \
    --check skills.0.description eq 'QA public stand-in skill' --check skills.0.source eq "$PUB/skills/qa-f25-pub" \
    --check skills.0.installed eq false --save F25.marketplace-catalog/before
  SRC=$(control-agent-server api GET /api/skills/marketplace --field skills.0.source)
  control-agent-server api POST /api/skills/install --json '{"source": "'"$SRC"'"}' --expect 200 --check name eq qa-f25-pub
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills.0.installed eq true --save F25.marketplace-catalog/after-install
  ```
  一个相对的入口源成为克隆中的绝对路径，安装路由将其接受为本地源。 `installed` 每次调用都会重新计算，因此立即翻转。
- **TypeScript 客户端 (`F25.ts-client`).** `SkillsClient` 从 `clients/typescript/dist` (在缺少时这里构建) 的客户端中走过了安装技能生命周期，然后 REST 读取结果。

  需求：`node`
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  G3=$(control-agent-server fixture git-source --name qa-f25-ts --print-path)
  H3=$(git -C "$G3" rev-parse HEAD)
  cat > "$F/qa_f25_ts.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { SkillsClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const [src, head] = process.argv.slice(2);
  const host = process.env.AGENT_SERVER_URL;
  const client = new SkillsClient({ host, apiKey: process.env.SESSION_API_KEY });
  const name = 'qa-f25-ts-skill';
  const userTier = { load_public: false, load_user: true, load_project: false, load_org: false };
  const inCatalog = async () => (await client.getSkills(userTier)).skills.some((s) => s.name === name);

  const info = await client.installSkill({ source: `file://${src}`, repo_path: `skills/${name}` });
  assert.equal(info.name, name);
  assert.equal(info.enabled, true);
  assert.equal(info.resolved_ref, head);
  assert.ok((await client.listInstalledSkills()).skills.some((s) => s.name === name));
  assert.equal((await client.getInstalledSkill(name)).resolved_ref, head);
  assert.ok(await inCatalog());
  assert.deepEqual(await client.toggleSkill(name, false), { name, enabled: false });
  assert.equal((await client.getInstalledSkill(name)).enabled, false);
  assert.equal(await inCatalog(), false);
  assert.deepEqual(await client.toggleSkill(name, true), { name, enabled: true });
  assert.ok(await inCatalog());
  const refreshed = await client.refreshSkill(name);
  assert.equal(refreshed.message, `Skill '${name}' updated`);
  assert.equal(refreshed.skill.resolved_ref, head);
  assert.equal(refreshed.skill.enabled, true);
  assert.equal((await client.syncSkills()).status, 'success');
  const pub = (await client.getMarketplace()).skills.find((s) => s.name === 'qa-f25-pub');
  assert.equal(pub.installed, true);
  assert.deepEqual(await client.uninstallSkill(name), { message: `Skill '${name}' uninstalled` });
  await assert.rejects(client.getInstalledSkill(name), (e) => e.status === 404);
  await assert.rejects(new SkillsClient({ host }).listInstalledSkills(), (e) => e.status === 401);
  console.log('QA_F25_TS_OK');
  JS
  control-agent-server exec --timeout 180 --expect-output QA_F25_TS_OK --save F25.ts-client/program -- node "$F/qa_f25_ts.mjs" "$G3" "$H3"
  control-agent-server api GET /api/skills/installed --expect 200 --check skills not-contains qa-f25-ts-skill
  test ! -e "$I/qa-f25-ts-skill"
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills.0.name eq qa-f25-pub --check skills.0.installed eq true
  ```
  每个客户端方法都返回匹配的REST路由返回的内容：源的HEAD安装，`toggleSkill`隐藏和恢复技能，`getSkills`刷新使其保持启用，成功同步的替代克隆，由`F25.marketplace-catalog`市场安装的入口，然后REST卸载确认。 未知技能返回404 `HttpError`。 客户端没有
  `apiKey` 得到 401。
- **同步 (`F25.marketplace-stale-cache`).** 之后的目录预热目录，列出上游的第二个条目，同步，读取目录。

  需要：`F25.sync`
  ```sh
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills not-contains qa-f25-pub-extra
  mkdir -p "$E/skills/qa-f25-pub-extra"
  printf -- '---\nname: qa-f25-pub-extra\ndescription: QA second catalog entry\n---\nQA_PUBLIC_EXTRA\n' > "$E/skills/qa-f25-pub-extra/SKILL.md"
  printf '{"name": "qa-f25-ext", "owner": {"name": "QA"}, "plugins": [{"name": "qa-f25-pub", "source": "./skills/qa-f25-pub", "description": "QA public stand-in skill"}, {"name": "qa-f25-pub-extra", "source": "./skills/qa-f25-pub-extra", "description": "QA second catalog entry"}]}\n' \
    | tee "$E/.plugin/marketplace.json" > "$E/marketplaces/default.json"
  git -C "$E" add -A
  git -C "$E" commit -q -m 'List a second catalog entry'
  control-agent-server api POST /api/skills/sync --expect 200 --check status eq success
  test -f "$PUB/skills/qa-f25-pub-extra/SKILL.md"
  grep -q '"name": "qa-f25-pub-extra"' "$PUB/marketplaces/default.json"
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills contains '"name": "qa-f25-pub-extra"' \
    --save F25.marketplace-stale-cache/after-sync
  ```
  同步带来了新条目，将其添加到克隆中，并且一个成功的同步清除了目录的模块级 5 分钟缓存，因此下一次读取会列出它。 就像公共技能缓存一样，目录不会缓存一个空结果，因此，下一次读取时，第一次离线调用会重试。
- **卸载(`F25.uninstall`)。**消除市场技能和本地技能。
  ```sh
  control-agent-server api DELETE /api/skills/installed/qa-f25-pub --expect 200 \
    --check message eq "Skill 'qa-f25-pub' uninstalled" --save F25.uninstall/delete
  control-agent-server api GET /api/skills/installed/qa-f25-pub --expect 404
  test ! -e "$I/qa-f25-pub"
  control-agent-server state cat home/.openhands/skills/installed/.installed.json --not-contains '"qa-f25-pub"'
  control-agent-server api DELETE /api/skills/installed/qa-f25-pub --expect 404
  control-agent-server api GET /api/skills/marketplace --expect 200 --check skills.0.name eq qa-f25-pub --check skills.0.installed eq false
  control-agent-server api DELETE /api/skills/installed/qa-f25-skill --expect 200
  control-agent-server api GET /api/skills/installed --expect 200 --check skills not-contains '"name": "qa-f25-skill"' \
    --check skills not-contains '"name": "qa-f25-pub"' --save F25.uninstall/list
  control-agent-server api POST /api/skills --json '{"load_public": false, "load_user": true, "load_project": false, "load_org": false}' \
    --expect 200 --check skills not-contains '"name": "qa-f25-skill"'
  ```
  目录和元数据条目不见了，再次卸载404，市场入口再次显示`installed: false`，用户等级也不再显示`qa-f25-skill`。 `qa-f25-src-skill` 和 `qa-f25-gone` 仍然安装在本次运行中。

<a id="gotchas"></a>

## 陷阱

- `load_public`、`load_user`、`load_project` 和 `load_org` 均默认为
  `true`：一个空的 `POST /api/skills` 主体克隆 `github.com/OpenHands/extensions`（git、网络、长达 120 秒的克隆超时）。 离线菜谱发送
  `load_public: false`，或像 `F25.sync` 一样先播种克隆。
- 技能路径在导入时被冻结（`Path.home()` 和
  `OH_PERSISTENCE_DIR`): 用户技能 `~/.agents/skills`,
  `$OH_PERSISTENCE_DIR/skills`和`.../microagents`； 安装的商店
  `$OH_PERSISTENCE_DIR/skills/installed`; 公共克隆
  `$OH_PERSISTENCE_DIR/cache/skills/public-skills`. `launch` 每次运行设置它们； 在实时服务器上更改它们没有任何效果。
- 项目发现会走到最近的 `.git`，因此另一个结帐内的 `project_dir` 也会加载该结帐的 `AGENTS.md` 和技能。 的
  因此，`fixture project` 目录是它自己的存储库。
- SKILL.md 目录是严格的：前置元数据 `name`（如果有）必须等于目录名称并匹配 `^[a-z0-9]+(-[a-z0-9]+)*$`。 在目录中，不良技能会被跳过，仅显示日志警告； 安装答案 422。
- `sources` 计数在合并名称之前是按等级的（`sdk_base` 是公开的用户和已启用的安装技能的总和），所以它们的总和可以超过技能的数量。
- 注册市场仅在 `load_public` 为 True 时贡献； 服务器默认注册 (`OH_REGISTERED_MARKETPLACES`) 与请求合并，请求以名称获胜。
- 公共技能缓存的寿命为 60 秒（对于标签或 SHA 来说永远有效）
  `EXTENSIONS_REF`) 并仅缓存非空结果； `/api/skills/sync` 清除它。 市场目录有自己的 5 分钟缓存，也仅在非空时保留，成功的同步也会清除 (`F25.marketplace-stale-cache`)。
- 通过自身的 `origin`，公共克隆被更新，这正是本地替代品工作的原因：将 `public-skills` 替换为本地仓库的克隆使 `load_public`、同步和市场目录离线且确定。 真正的存储库没有`marketplaces/default.json`，所以
  `load_public` 加载其中的每个 `skills/` 条目，同时目录保持为空 (`F25.marketplace-public`)。
- 安装源：复制纯绝对路径； `file://` 和其他URLs 被复制到`$OH_PERSISTENCE_DIR/cache/extensions/`。
  `github:OpenHands/extensions/skills/github` 与安装相同
  获取层支持 `{"source": "github:OpenHands/extensions", "repo_path": "skills/github"}`，但安装目前会以 422 拒绝这种简写，因为加载器会将技能目录改名为仓库名（`F25.install-documented-sources`，
  [OpenHands/software-agent-sdk#6184](https://github.com/OpenHands/software-agent-sdk/issues/6184)). Use the
  显式 `repo_path` 形式直到修复。 A GitHub `/tree/<ref>/<path>` URL 未被解析。
- 现有技能的 409 是在获取后决定的，因此存在冲突
  git install still clones. `version` is always `1.0.0` (the frontmatter
  `version` 未读）。 刷新会在删除 `ref` 的情况下重新安装，因此安装在标签上的技能会移至默认分支 (`F25.install-ref`)。 A
  无法在已缓存的克隆中检出的 `ref` 会返回客户端错误，并使已安装的技能保持不变 (`F25.install-unknown-ref`)。
- 仅列表调用和 `PATCH` 与磁盘协调 `.installed.json`； 单一视图、`DELETE` 和刷新则不然，因此手动编辑的顺序很重要 (`F25.self-heal`)。
- 只有安装了的技能才会加载对话 `agent_context.load_user_skills` 是 True; 默认设置里有它 False因此，有 `PATCH /api/settings` 预条件。 智能体 profiles (`conversation start --agent-profile default`) 在启动时，我们优先解决用户和公共技能，但它们的默认工具包括终端，其 tmux socket路径在长时间运行的目录下超过了Unix的限制`launch --name` 超过几个字符。
  设置路径上的 `--tools none` 避免 tmux。
- 智能体的上下文中的 AgentSkills 格式技能会自动附加内置 `invoke_skill` 工具，即使带有 `--tools none` 也是如此。 SKILL.md 无
  `triggers` 永远不会被关键字激活，因此智能体只能通过 `invoke_skill` 到达它，它记录 `invoked_skills` 而不是
  `activated_knowledge_skills` (`F25.invoke-skill`). 模型倾向于在回复中呼应技能主体，因此根据其选择 `InvokeSkillObservation`
  `skill_name` 在查找正文之前。
- 网络：只有`F25.public-repo`和`F25.install-github`到达github.com。 它们是普通子弹，因此它们后面的两个已知错误子弹开始
  from a proven clone or install, and those bullets `Require` them; without
  网络所有四个都被报告`blocked`，而不是失败或报告误导性`xfail`。
- 当没有选定的事件包含文本时，`conversation events --contains` 会失败，因此它会自行断言内容。 `ws listen`没有内容过滤器；
  `--until-kind K --until FIELD=VALUE` 失败，除非具有该字段的类型 `K` 的帧在 `--duration` 内到达，这就是激活项目符号断言 WebSocket 重放的方式。
- 错误 500 在 `exception` 字段中携带异常文本； 的
  `known bug` 子弹将其保存为证据。
