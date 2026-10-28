<a id="agent-profiles"></a>

# 智能体个人资料

请输出简体中文译文机密-免费启动规格，消费者只需一次保存，即可开始对话。 安智能体该字段是  OpenHands  智能体那是一个保存的名称 LLM profile (`llm_profile_ref`) 加上工具， persona, 提示词后缀，技能拒绝列表上下文压缩器 and critic policy, or an ACP  智能体那是一个名称 ACP backend (`acp_server`); 两种都携带一个 MCP 允许列表 (`mcp_server_refs`) and a 机密允许列表 (`secret_refs`). 每个角色都是一个 JSON 文件夹 `OH_PERSISTENCE_DIR/agent-profiles`以可重命名的名称键，由服务器管理稳定 `id` and a `revision` 每项覆盖都会增加。 服务器保留一个独立的活跃指针 (`settings.active_agent_profile_id`由 ID 设置，且从未复制到其他地方
`agent_settings`), 修复缺失或断开的指针到 `default`（当缺失时重新播种），预览不启动的启动 (`materialize`), 并在 `agent_profile_id` 开始对话时解决配置。 TypeScript
`AgentProfilesClient`和Agent Canvas的个人资料编辑者是消费者。

资料来源：`openhands-agent-server/openhands/agent_server/agent_profiles_router.py`、`openhands-agent-server/openhands/agent_server/launch.py`、`openhands-agent-server/openhands/agent_server/_secrets_exposure.py`、`openhands-sdk/openhands/sdk/profiles/`、`openhands-sdk/openhands/sdk/launch/`、`clients/typescript/src/client/agent-profiles-client.ts`

需求：`llm`

Routes: `GET /api/agent-profiles`, `GET /api/agent-profiles/{name}`,
`POST /api/agent-profiles/{name}`, `DELETE /api/agent-profiles/{name}`,
`POST /api/agent-profiles/{name}/rename`,
`POST /api/agent-profiles/{profile_id}/activate`,
`POST /api/agent-profiles/{name}/materialize`

<a id="sub-features"></a>

## 子功能

- `F21.auth-required`：每个智能体-profile 路由都会在没有有效 `X-Session-API-Key` 的情况下回答 401，并且不会写入任何内容（甚至没有写入惰性种子）。
- `F21.lazy-seed`在空存储中，第一个列表会初始化为一个 `default`  OpenHands profile (revision 0, `llm_profile_ref` = the active LLM profile), points `active_agent_profile_id` 继续使用它，稍后会列出其重用情况。 a 已持久化缺失或断开的指针被修复为默认值。
- `F21.seed-no-ghost-llm`在未配置的服务器上启动 `default` 保持柔软 `llm_profile_ref`  `default` 没有写密钥的 `default`  LLM 材料化报告未解决（profile）。 一旦上线 LLM 它有一个真正的密钥，下一个种子映射到一个密钥 `default`  LLM profile.
- `F21.seed-acp`：当 `agent_settings` 正在运行时，第一个列表会创建一个 ACP ACP `default` 的 LLM LLM。
- `F21.save-create`: `POST /api/agent-profiles/{name}` 回答 201 并将配置文件存储在版本 0 处具有服务器生成的 id 的路径名下（客户端 `id` 和主体 `name` 被忽略）； GET，清单摘要与文件一致。
- `F21.save-overwrite`：保存现有名称将替换整个配置文件（不合并），保留其 `id` 并将 `revision` 设置为先前的一加一，忽略客户端 `revision`。
- `F21.acp-kind`：ACP 配置文件（`agent_kind` `acp`、`acp_server`）以其 ACP 默认值保存并以 `llm_profile_ref` null 列出。
- `F21.save-validation`缺少的 `llm_profile_ref`另一个领域的字段或未知字段，无效 `acp_server` 或 `agent_kind`, 过新了 `schema_version` 非对象体返回422，并附有原因，而无数据被存储。
- `F21.name-rules`：每个名称路由上和 `new_name` 中的名称必须与 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` 匹配；接受 64 个字符，65 个字符，前导点或破折号和空格为 422 个； activate 的 id 最多为 128 个字符 (422)。
- `F21.not-found`: GET未知名称的重命名和存储化操作返回 404 `Agent profile '<name>' not found`未知ID或名称的激活请求返回404， DELETE 未知名称的值为200。
- `F21.activate`：`POST /api/agent-profiles/{profile_id}/activate`仅设置`active_agent_profile_id`（`agent_settings_applied`False）：列表和设置显示id，`agent_settings`不变。
- `F21.activate-corrupt-settings`：使用不可解析的 `settings.json`，激活答案 500 `Failed to activate agent profile`（其中 LLM 和元配置文件激活答案 409）并保持文件原样； 文件恢复后，相同的激活将再次起作用。
- `F21.rename`： 将用户移动到新名称，但保留相同的 [profile] `id` 和 `revision`保留活动指针，释放旧名称（404），对相同名称返回200 "未更改"，当目标存在时返回409。
- `F21.delete`：DELETE删除配置文件； 删除另一个配置文件会保留指针，删除活动配置文件会选择现有的默认配置文件，或者在不存在时重新设定它。
- `F21.delete-active-acp-reset`：在 `agent_settings` 为 ACP 时删除活动配置文件会将其重置为 OpenHands 默认值，保留服务器的 `mcp_config`，并选择默认配置文件。
- `F21.materialize-valid`生成一个存储的元数据，其引用解析为答案 `valid`  True 与 `llm_profile_resolved`, `llm_api_key_set`, the resolved MCP 钥匙和技能， 机密允许列表和 `resolved_settings` 使用密钥掩码（原始密钥不会出现在任何地方），并持久化。
- `F21.materialize-dangling` LLM, MCP 与元元信息和一个服务器无法运行的工具一起，返回状态码200 `valid`  False 在每一个问题上 `errors`在他们的字段中，还有未挂接的名称，以及没有 `resolved_settings`.
- `F21.materialize-draft`: 在路径名称下预览草稿体，但未保存：ACP 草稿报告其凭据机密名称，`disabled_skills` 从`resolved_skills` 移除技能，`mcp_server_refs` null 暴露所有配置的MCP 服务器，`[]` None，以及一个无效的草稿或一个顶级键是422。
- `F21.limit`：商店最多保存 50 个配置文件：创建第 51 个配置文件为 409，并且不写入任何内容，在上限覆盖一个配置文件仍然有效。
- `F21.corrupt-file`： 一个无效的配置文件 JSON 被列表跳过 GET存储的材料化和重命名操作返回错误码400 DELETE 仍然删除它。
- `F21.conversation-start`一场对话开始于 `agent_profile_id` 运行该配置的 LLM 记录了配置和工具选择（而不是实时设置）， `launched_agent_profile` 使用该ID和版本，以及该模型的统计信息和事件名称，将该运行后的配置模型命名为。
- `F21.secret-scope` `secret_refs` 只保留允许的名称机密一个对话成功开始，但没有错误，并且没有丢弃的名字已持久化 with the conversation; 一个没有 [profile] 的 `secret_refs` 保持它们的完整。
- `F21.launch-additions`一场对话开始于 `agent_profile_id` 和 `agent_launch_additions.system_message_suffix_append` 获取用户资料中附加的文字 `system_message_suffix` 在它的智能体 and its `SystemPromptEvent`添加的内容未存储在 `meta.json`, 并且存储的用户资料保持其修订版本。 未知的键或超过 32768 个字符的值是 422 并且不会创建任何内容。
- `F21.ts-client`: TypeScript `AgentProfilesClient` 列出了种子、保存、读取、重命名、激活（通过 ID）以及删除一个配置，预览草稿和存储的配置，`materializeAgentProfile` `AgentServerClient.agentProfiles` 读取相同的存储，`HttpError` 读取相同的存储，如果未知或无效名称，则以 404 或 422 响应。
- `F21.restart`：配置文件、它们的 id 和修订版本以及活动指针在重新启动后仍然存在。
- `F21.acp-skill-sourcing`: ACP 角色的生成不会在默认的 `acp_skill_sourcing` `native` 下注入任何技能，`qa-f21-skill` 一旦服务器运行在 `OH_ACP_SKILL_SOURCING=openhands_managed` (所附镜像集) 下，就会发现这个发现的目录。 OpenHands 配置文件以两种方式获取目录。
- `F21.store-busy`另一个进程持有用户存储时锁请求的端点回答了 503 `Profile store is busy` 30秒后锁超时，并且在时会再次工作锁免费的。
- `F21.launch-store-busy`另一个进程持有用户存储时锁，`POST /api/conversations` 与 `agent_profile_id` 答案为 503 `Agent profile store is busy` (重试) 30秒后锁超时并且创建了什么也没有 `/alive` 与此同时，它仍然回答事件循环).
- `F21.busy-blocks-server`：等待配置文件存储锁，不得拖延服务器的REST； `/alive` 持续及时回复。
- `F21.dangling-llm-report`: 报告如何显示一个悬空的 LLM 引用必须与服务器的种子代码文档相匹配：文档中提到的 `dangling_llm_profile_ref` 字段（即启动时的 422 带来的字段）在材料化体中，或者文档停止承诺它存在。
- `F21.ts-payload-types`: TypeScript客户端导出的 `AgentProfileSummary`、`AgentProfileDiagnostics`、`OpenHandsAgentProfile` 和 `ACPAgentProfile` 类型接受服务器发送的载荷，因为其生成的合同是这样的：服务器发送的每个字段都被声明，每个必填字段都被发送。
- `F21.json-suffix-identity` 保存以 `.json` 结尾的名称两次必须保留一个 `id` 并增加 `revision`，就像任何其他名称一样，而活动时删除它必须将指针移出它（移到 `default`）（或者名称必须拒绝返回 422 并存储什么）。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `GET /api/agent-profiles`（摘要 `{id, name, agent_kind, revision, llm_profile_ref, mcp_server_refs}` 和
  `active_agent_profile_id`; 修复未设置或悬空的指针，当缺失时则填充`default`
  `GET /api/agent-profiles/{name}` (`{name, profile}`),
  `POST /api/agent-profiles/{name}`（正文是配置文件；201 `{name, message}`没有id，所以用GET读回来），
  `DELETE /api/agent-profiles/{name}`,
  `POST /api/agent-profiles/{name}/rename` (`{"new_name": ...}`),
  `POST /api/agent-profiles/{profile_id}/activate`（uuid，不是名称），
  `POST /api/agent-profiles/{name}/materialize`（无正文或 `{}` 表示存储的配置文件，`{"profile": {...}}` 表示草稿）。 下面的每个配方都直接驱动这些路线。
- REST（其他系列，此处用作第二视图或设置）：
  `GET /api/settings` and `PATCH /api/settings` (`active_agent_profile_id`,
  `agent_settings`; F18)、`POST /api/conversations` 以及 `agent_profile_id` 和可选的 `agent_launch_additions` (F04； 到达通过
  `conversation start --agent-profile NAME`，将名称解析为带有列表路由的 id，或者当列表阻塞或需要 422 时使用 `api POST` 和 id），`GET /api/profiles` 和
  `POST /api/profiles/{name}/activate`（LLM简介； F20），以及
  `POST`/`DELETE/api/settings/mcp/{settings_key}`（MCP服务器； F19).
- WebSocket：配置文件路由不发出任何事件； 从配置文件开始的对话在 `/sockets/events/{conversation_id}` (F06) 上流式传输其事件，在此处通过重播进行检查。
- TypeScript客户端：`AgentProfilesClient.listAgentProfiles`，
  `getAgentProfile`, `saveAgentProfile`, `deleteAgentProfile`,
  `renameAgentProfile`、`activateAgentProfile(profileId)` 和
  `materializeAgentProfile(name, draft?)`; `ConversationManager.agentProfiles` 和 `AgentServerClient.agentProfiles` 公开相同的客户端。 驱动力
  `F21.ts-client`（针对已构建客户端的 `node` 程序）； 导出的载荷类型 (`AgentProfileSummary`, `AgentProfile`,
  `AgentProfileDiagnostics`) 根据实时载荷进行类型检查
  `F21.ts-payload-types`.
- 配置：`acp_skill_sourcing` (`OH_ACP_SKILL_SOURCING`, `native` 默认，`openhands_managed` 在智能体-服务器镜像中) 决定是否启用 ACP 启动及其材料化预览，以及获取服务器的技能目录 (`F21.acp-skill-sourcing`, 通过 `restart --env`)。 一个服务器，其
  `conversation_runtime` 为 `docker` 始终预览为 `openhands_managed`。
- SDK: `RemoteConversation.create(工作区，StartConversationRequest(...,
  agent_profile_id=...))` starts from a saved profile;
  `RemoteWorkspace.get_secrets(agent_profile_id=...)` 列出了个人资料可能看到的机密 (F18)。
- Agent Canvas：配置文件选择器和编辑器（列表、保存、物化预览、激活）； 仅适用于上下文。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已实时并已导出 (`launch --new`)，`doctor` 正常。 尚未调用 `GET /api/agent-profiles`（`doctor` 没有），因此配置文件存储为空。
- 设置`$DEEPSEEK_API_KEY`； 下面的块保存`deepseek-flash`（活动）和`deepseek-pro`，并在运行的私有`HOME`下写入一项用户技能`qa-f21-skill`以用于实现项目符号。 `jq`,
  `flock` (util-linux) 和 `node` 位于 `PATH` (`F21.ts-client` 构建
  当 `dist/` 缺失时为 `clients/typescript`）。
- 项目符号共享 `SEED`、`CODER`、`ACP` 和 `RUNNER`（id 用 GET 读回； `RUNNER` 及其配置文件 `qa-f21-runner` 来自对话开始项目符号，并由机密范围项目符号重用）。 ACP 重置项目符号离开 MCP 服务器 `qa-f21-mcp` 进入具体化项目符号； 草稿项目符号将其删除。 两个种子子弹分别发射和停止各自的服务器。
- `F21.activate-corrupt-settings` 覆盖运行的 `settings.json` 并放回原来的（失败时也是如此）。 `F21.acp-skill-sourcing` 重新启动运行两次（先使用 `OH_ACP_SKILL_SOURCING=openhands_managed`，然后使用 `--reset-config`）。 `F21.store-busy`、`F21.launch-store-busy` 和 `F21.busy-blocks-server` 分别按住锁约 30 秒。 三个已知错误子弹排在最后，然后
  `F21.json-suffix-identity`，它会激活自己的配置文件并通过删除它来结束，因此运行仍保持 `default` 处于活动状态。

```sh
control-agent-server llm preset deepseek
control-agent-server state ls 'home/.openhands/agent-profiles/*.json' --expect-count 0
mkdir -p "$AGENT_SERVER_VERIFY_RUN/home/.agents/skills/qa-f21-skill"
printf -- '---\nname: qa-f21-skill\ndescription: QA F21 user skill\n---\nQA_F21_SKILL_BODY\n' \
  > "$AGENT_SERVER_VERIFY_RUN/home/.agents/skills/qa-f21-skill/SKILL.md"
```

- **没有钥匙，无法访问 (`F21.auth-required`)。**在播种任何东西之前，每条路线都没有密钥（密钥错误）。
  ```sh
  control-agent-server api GET /api/agent-profiles --auth none --expect 401 --save F21.auth-required/list
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --auth bad --expect 401
  control-agent-server api POST /api/agent-profiles/qa-f21-coder --auth none --json '{"llm_profile_ref": "deepseek-flash"}' --expect 401
  control-agent-server api DELETE /api/agent-profiles/qa-f21-coder --auth none --expect 401
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/rename --auth none --json '{"new_name": "qa-f21-x"}' --expect 401
  control-agent-server api POST /api/agent-profiles/00000000-0000-4000-8000-000000000000/activate --auth none --expect 401
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/materialize --auth none --json '{}' --expect 401
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 404 --check detail eq "Agent profile 'qa-f21-coder' not found"
  control-agent-server state ls 'home/.openhands/agent-profiles/*.json' --expect-count 0
  control-agent-server api GET /api/settings --check active_agent_profile_id missing
  ```
  所有七个答案都返回401，而带有运行键的相同GET则成功到达商店（404：还没有保存）。 没有配置文件，也没有设置指向，所以拒绝列表没有播种。
- **懒惰种子 (`F21.lazy-seed`).**第一个经过验证的列表。
  ```sh
  SEED=$(control-agent-server api GET /api/agent-profiles --expect 200 --check profiles len-eq 1 \
    --check profiles.0.name eq default --check profiles.0.agent_kind eq openhands --check profiles.0.revision eq 0 \
    --check profiles.0.llm_profile_ref eq deepseek-flash --save F21.lazy-seed/first-list --field active_agent_profile_id)
  control-agent-server api GET /api/agent-profiles/default --check profile.id eq "$SEED" \
    --check profile.llm_profile_ref eq deepseek-flash --check profile.mcp_server_refs missing --check profile.disabled_skills len-eq 0
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$SEED" --check active_profile eq deepseek-flash
  control-agent-server state cat home/.openhands/agent-profiles/default.json --check id eq "$SEED" --check name eq default
  control-agent-server api GET /api/agent-profiles --check profiles len-eq 1 --check active_agent_profile_id eq "$SEED" --save F21.lazy-seed/second-list
  SETTINGS="$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  jq '.active_agent_profile_id = "00000000-0000-4000-8000-000000000000"' "$SETTINGS" > "$SETTINGS.tmp"
  mv "$SETTINGS.tmp" "$SETTINGS"
  control-agent-server api GET /api/agent-profiles --check profiles len-eq 1 --check active_agent_profile_id eq "$SEED" \
    --save F21.lazy-seed/repaired-pointer
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$SEED"
  ```
  只有一个`default`个角色，引用了活跃的LLM个角色
  `deepseek-flash`，并且指针在列表、设置和文件中命名其 id； 第二个列表返回相同的单个配置文件。 安排过时的已持久化指针后，下一个列表将在两个视图中恢复相同的默认 id (#5983)。
- **无重影 LLM 配置文件 (`F21.seed-no-ghost-llm`)。**第二个服务器从未配置过 LLM，然后是具有真实密钥的同一服务器。
  ```sh
  B=$(control-agent-server launch --new --name f21-seed --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null' EXIT
  control-agent-server api GET /api/agent-profiles --run "$B" --expect 200 --check profiles len-eq 1 \
    --check profiles.0.name eq default --check profiles.0.llm_profile_ref eq default --save F21.seed-no-ghost-llm/keyless-seed
  control-agent-server api GET /api/profiles --run "$B" --check profiles len-eq 0 --check active_profile missing
  control-agent-server state ls 'home/.openhands/profiles/*.json' --run "$B" --expect-count 0
  control-agent-server api POST /api/agent-profiles/default/materialize --run "$B" --json '{}' --expect 200 \
    --check valid eq false --check llm_profile_resolved eq false --check errors contains "LLM profile 'default' not found"
  control-agent-server api PATCH /api/settings --run "$B" \
    --json '{"agent_settings_diff": {"llm": {"model": "openai/qa-f21-model", "api_key": "qa-f21-fake-key"}}}' \
    --expect 200 --check llm_api_key_is_set eq true
  control-agent-server api DELETE /api/agent-profiles/default --run "$B" --expect 200
  RESEEDED=$(control-agent-server api GET /api/agent-profiles/default --run "$B" --field profile.id)
  control-agent-server api GET /api/settings --run "$B" --check active_agent_profile_id eq "$RESEEDED"
  control-agent-server api GET /api/agent-profiles --run "$B" --check profiles len-eq 1 --check profiles.0.llm_profile_ref eq default \
    --check active_agent_profile_id exists
  control-agent-server api GET /api/profiles --run "$B" --check profiles len-eq 1 --check profiles.0.name eq default \
    --check profiles.0.model eq openai/qa-f21-model --check profiles.0.api_key_set eq true --save F21.seed-no-ghost-llm/mirrored
  control-agent-server api POST /api/agent-profiles/default/materialize --run "$B" --json '{}' --expect 200 \
    --check llm_profile_resolved eq true --check llm_api_key_set eq true
  ```
  无密钥种子不写入任何 LLM 配置，并调用其引用时未解析。 在活的 LLM 获取密钥后，删除活跃的
  `default` 立即重新播种并选择其替换项，这次将 LLM 镜像到智能体配置文件解析的键控 `default` LLM 配置文件中。 服务器 B 在退出时停止。
- **ACP 种子 (`F21.seed-acp`).**第三台服务器的实时设置在列出配置文件之前已切换到 ACP。
  ```sh
  C=$(control-agent-server launch --new --name f21-seed-acp --print-run)
  trap 'control-agent-server stop --run "$C" >/dev/null' EXIT
  control-agent-server api PATCH /api/settings --run "$C" --expect 200 --check agent_settings.agent_kind eq acp \
    --json '{"agent_settings_diff": {"agent_kind": "acp", "acp_server": "codex", "acp_model": "gpt-5.5"}}'
  ACP_SEED=$(control-agent-server api GET /api/agent-profiles --run "$C" --expect 200 --check profiles len-eq 1 \
    --check profiles.0.name eq default --check profiles.0.agent_kind eq acp --check profiles.0.llm_profile_ref missing \
    --save F21.seed-acp/seed --field active_agent_profile_id)
  control-agent-server api GET /api/agent-profiles/default --run "$C" --check profile.id eq "$ACP_SEED" --check profile.revision eq 0 \
    --check profile.acp_server eq codex --check profile.acp_model eq gpt-5.5 --check profile.llm_profile_ref missing
  control-agent-server api GET /api/settings --run "$C" --check active_agent_profile_id eq "$ACP_SEED" --check agent_settings.agent_kind eq acp
  control-agent-server api GET /api/profiles --run "$C" --check profiles len-eq 0
  ```
  种子遵循活的智能体类型：ACP `default` `codex` `gpt-5.5`，在设置中指明，没有LLM的记录。 服务器C在退出时停止运行。
- **创建(`F21.save-create`)。**还携带一个客户端 `id` 和一个不同的 `name` 的身体。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-coder --expect 201 \
    --json '{"name": "qa-f21-body-name", "id": "11111111-1111-4111-8111-111111111111", "llm_profile_ref": "deepseek-pro", "tools": [], "mcp_server_refs": [], "system_message_suffix": "QA F21 suffix"}' \
    --check name eq qa-f21-coder --check message eq "Agent profile 'qa-f21-coder' saved" --save F21.save-create/save
  CODER=$(control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 200 \
    --check name eq qa-f21-coder --check profile.name eq qa-f21-coder --check profile.id ne 11111111-1111-4111-8111-111111111111 \
    --check profile.revision eq 0 --check profile.schema_version eq 3 --check profile.agent_kind eq openhands \
    --check profile.llm_profile_ref eq deepseek-pro --check profile.tools len-eq 0 --check profile.mcp_server_refs len-eq 0 \
    --check profile.system_message_suffix eq 'QA F21 suffix' --check profile.agent eq CodeActAgent \
    --save F21.save-create/get --field profile.id)
  control-agent-server api GET /api/agent-profiles/qa-f21-body-name --expect 404
  control-agent-server api GET /api/agent-profiles --field profiles \
    | jq -e --arg id "$CODER" 'map(select(.name == "qa-f21-coder" and .id == $id and .revision == 0 and .llm_profile_ref == "deepseek-pro")) | length == 1'
  control-agent-server state cat home/.openhands/agent-profiles/qa-f21-coder.json --check id eq "$CODER" --check name eq qa-f21-coder
  ```
  响应不带id； GET 显示了在路径名下由服务器自动生成的全新 ID，版本号为 0，而主体名则为空，列表摘要和文件内容一致。
- **覆盖(`F21.save-overwrite`)。**使用不同的主体和客户端再次保存相同的名称 `revision`。

  需要：`F21.save-create`
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-coder --expect 201 \
    --json '{"llm_profile_ref": "deepseek-pro", "tools": [], "mcp_server_refs": [], "persona": "QA F21 persona", "revision": 41}'
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --check profile.id eq "$CODER" --check profile.revision eq 1 \
    --check profile.persona eq 'QA F21 persona' --check profile.system_message_suffix missing --save F21.save-overwrite/get
  ```
  id未变，修订号为1（不是41），第一次保存的后缀已消失：覆盖了整个档案。
- **ACP个人资料(`F21.acp-kind`)。**
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-acp --expect 201 \
    --json '{"agent_kind": "acp", "acp_server": "codex", "acp_model": "gpt-5.5", "secret_refs": ["OPENAI_API_KEY"]}'
  ACP=$(control-agent-server api GET /api/agent-profiles/qa-f21-acp --check profile.agent_kind eq acp \
    --check profile.acp_server eq codex --check profile.acp_model eq gpt-5.5 --check profile.acp_prompt_timeout eq 1800 \
    --check profile.acp_startup_timeout eq 90 --check profile.llm_profile_ref missing --check profile.secret_refs contains OPENAI_API_KEY \
    --check profile.revision eq 0 --save F21.acp-kind/get --field profile.id)
  control-agent-server api GET /api/agent-profiles --field profiles \
    | jq -e --arg id "$ACP" 'map(select(.id == $id and .agent_kind == "acp" and .llm_profile_ref == null)) | length == 1'
  ```
  的 ACP profile 存储其后端和默认值超时 (1800 s 提示词90 秒启动，且没有 LLM 参考项 GET 或在列表中。
- **保存验证（`F21.save-validation`）。**坏身体归于同一个名字。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{}' --expect 422 \
    --check detail.0.loc contains llm_profile_ref --check detail.0.type eq missing --save F21.save-validation/missing-ref
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"agent_kind": "acp", "llm_profile_ref": "deepseek-flash"}' \
    --expect 422 --check detail.0.type eq extra_forbidden --check detail.0.loc contains llm_profile_ref
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"llm_profile_ref": "deepseek-flash", "acp_server": "codex"}' \
    --expect 422 --check detail.0.type eq extra_forbidden --check detail.0.loc contains acp_server
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"llm_profile_ref": "deepseek-flash", "qa_unknown": 1}' \
    --expect 422 --check detail.0.loc contains qa_unknown
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"agent_kind": "acp", "acp_server": "qa-nope"}' \
    --expect 422 --check detail.0.type eq literal_error --check detail.0.msg contains claude-code
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"agent_kind": "qa-nope"}' --expect 422 --check detail.0.type eq union_tag_invalid
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"llm_profile_ref": "deepseek-flash", "tool_concurrency_limit": 0}' \
    --expect 422 --check detail.0.type eq greater_than_equal --check detail.0.loc contains tool_concurrency_limit
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '{"llm_profile_ref": "deepseek-flash", "schema_version": 99}' \
    --expect 422 --check detail eq 'Invalid agent profile'
  control-agent-server api POST /api/agent-profiles/qa-f21-bad --json '["qa"]' --expect 422 --check detail.0.type eq dict_type
  control-agent-server api GET /api/agent-profiles/qa-f21-bad --expect 404
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-bad*' --expect-count 0
  ```
  每个都以 `loc`、`type` 和 `msg` 结尾（模式-版本失败只给出 `Invalid agent profile`），且没有 `qa-f21-bad` 文件存在。
- **命名规则(`F21.name-rules`).**每一条有名字的路线上都有边界和糟糕的形状。

  需要：`F21.save-create`
  ```sh
  L64=qa-f21-$(printf 'n%.0s' $(seq 1 57))
  test ${#L64} -eq 64
  control-agent-server api POST "/api/agent-profiles/$L64" --json '{"llm_profile_ref": "deepseek-flash"}' --expect 201
  control-agent-server api GET "/api/agent-profiles/$L64" --check profile.name eq "$L64"
  control-agent-server api DELETE "/api/agent-profiles/$L64" --expect 200
  control-agent-server api POST "/api/agent-profiles/${L64}n" --json '{"llm_profile_ref": "deepseek-flash"}' --expect 422 \
    --check detail.0.type eq string_too_long --save F21.name-rules/too-long
  control-agent-server api POST /api/agent-profiles/.qa-f21 --json '{"llm_profile_ref": "deepseek-flash"}' --expect 422 \
    --check detail.0.type eq string_pattern_mismatch --save F21.name-rules/leading-dot
  control-agent-server api POST /api/agent-profiles/-qa-f21 --json '{"llm_profile_ref": "deepseek-flash"}' --expect 422
  control-agent-server api POST '/api/agent-profiles/qa%20f21' --json '{"llm_profile_ref": "deepseek-flash"}' --expect 422
  control-agent-server api GET /api/agent-profiles/.qa-f21 --expect 422
  control-agent-server api DELETE /api/agent-profiles/.qa-f21 --expect 422
  control-agent-server api POST /api/agent-profiles/.qa-f21/materialize --json '{}' --expect 422
  control-agent-server api POST /api/agent-profiles/.qa-f21/rename --json '{"new_name": "qa-f21-ok"}' --expect 422
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/rename --json '{"new_name": ".qa-f21"}' --expect 422 \
    --check detail.0.loc contains new_name
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/rename --json '{}' --expect 422 --check detail.0.type eq missing
  ID129=$(printf 'a%.0s' $(seq 1 129))
  control-agent-server api POST "/api/agent-profiles/$ID129/activate" --expect 422 \
    --check detail.0.type eq string_too_long --check detail.0.loc contains profile_id
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --check profile.id eq "$CODER"
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-n*' --expect-count 0
  ```
  64个字符的名称往返传输；65个字符，前导点或划线和空格，保存时为422，前导点为422（GET、DELETE、materialize和重命名也是如此，每个名称路由共享一条路径验证器，前导点也是个坏的或缺失的`new_name`）。 Activate 接收一个没有模式的 id，最大长度为 128 个字符。 `qa-f21-coder`不变。
- **未知的名称和 ID (`F21.not-found`)。**

  需要：`F21.lazy-seed`
  ```sh
  control-agent-server api GET /api/agent-profiles/qa-f21-nope --expect 404 \
    --check detail eq "Agent profile 'qa-f21-nope' not found" --save F21.not-found/get
  control-agent-server api POST /api/agent-profiles/qa-f21-nope/rename --json '{"new_name": "qa-f21-nope2"}' --expect 404 \
    --check detail eq "Agent profile 'qa-f21-nope' not found"
  control-agent-server api POST /api/agent-profiles/qa-f21-nope/materialize --expect 404
  control-agent-server api POST /api/agent-profiles/qa-f21-nope/materialize --json '{}' --expect 404
  control-agent-server api POST /api/agent-profiles/00000000-0000-4000-8000-000000000000/activate --expect 404 \
    --check detail eq "Agent profile with id '00000000-0000-4000-8000-000000000000' not found"
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/activate --expect 404 \
    --check detail eq "Agent profile with id 'qa-f21-coder' not found" --save F21.not-found/activate-by-name
  control-agent-server api DELETE /api/agent-profiles/qa-f21-nope --expect 200 \
    --check message eq "Agent profile 'qa-f21-nope' deleted" --save F21.not-found/delete
  control-agent-server api GET /api/agent-profiles/qa-f21-nope2 --expect 404
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$SEED"
  ```
  GET 中的未知名称将返回 404 错误，重命名并材料化（如果有空体）； 激活键是 ID，所以名称也是 404。 DELETE 是幂等的，指针未被修改。
- **通过 ID 激活 (`F21.activate`)。**指向`qa-f21-coder`，其LLM（`deepseek-pro`）、工具和角色与实时设置不同。

  需要：`F21.save-create`
  ```sh
  BEFORE=$(control-agent-server api GET /api/settings --field agent_settings | jq -S -c .)
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200 --check id eq "$CODER" \
    --check agent_settings_applied eq false --save F21.activate/activate
  control-agent-server api GET /api/agent-profiles --check active_agent_profile_id eq "$CODER"
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$CODER" --check active_profile eq deepseek-flash \
    --check agent_settings.llm.model eq deepseek/deepseek-flash --save F21.activate/settings
  AFTER=$(control-agent-server api GET /api/settings --field agent_settings | jq -S -c .)
  test "$BEFORE" = "$AFTER"
  ```
  指针在两个视图中移动，`agent_settings`（仍然）
  `deepseek-flash`) 前后相同。
- **通过损坏的设置文件激活(`F21.activate-corrupt-settings`)。**设置文件被替换为文本，该文本不是JSON（因为崩溃或错误编辑会留下它），然后恢复。

  需要：`F21.save-create`
  ```sh
  SETTINGS="$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  KEEP="$AGENT_SERVER_VERIFY_RUN/private/qa-f21-settings.json"
  cp "$SETTINGS" "$KEEP"
  trap 'cp "$KEEP" "$SETTINGS" && rm -f "$KEEP"' EXIT
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200 --check id eq "$CODER"
  printf '{not json' > "$SETTINGS"
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 500 \
    --check exception contains 'Failed to activate agent profile' --save F21.activate-corrupt-settings/corrupt
  test "$(cat "$SETTINGS")" = '{not json'
  cp "$KEEP" "$SETTINGS"
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200 --check id eq "$CODER"
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$CODER" --check llm_api_key_is_set eq true \
    --check agent_settings.llm.model eq deepseek/deepseek-flash
  ```
  有可读文件时激活成功，返回状态码200。 在该腐败文件中，这是一个故意的500 (`exception` `500: Failed to activate agent profile`)。 LLM 角色激活和元激活在这里回答 409，F20 和 F22，而文件仍然保留着错误的文本：服务器拒绝用默认值替换它。 有了原始文件，激活码200又回来了，设置和密钥都完好无损。
- **重命名(`F21.rename`)。**重命名活动配置文件，然后重命名边缘情况。

  需要：`F21.save-create`、`F21.acp-kind`
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-coder/rename --json '{"new_name": "qa-f21-coder2"}' --expect 200 \
    --check name eq qa-f21-coder2 --check message eq "Agent profile 'qa-f21-coder' renamed to 'qa-f21-coder2'" --save F21.rename/rename
  control-agent-server api GET /api/agent-profiles/qa-f21-coder2 --check profile.id eq "$CODER" --check profile.name eq qa-f21-coder2 \
    --check profile.revision eq 1 --save F21.rename/get
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 404
  control-agent-server api GET /api/agent-profiles --check active_agent_profile_id eq "$CODER"
  control-agent-server state cat home/.openhands/agent-profiles/qa-f21-coder2.json --check name eq qa-f21-coder2 --check id eq "$CODER"
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-coder.json' --expect-count 0
  control-agent-server api POST /api/agent-profiles/qa-f21-coder2/rename --json '{"new_name": "qa-f21-coder2"}' --expect 200 \
    --check message eq "Agent profile 'qa-f21-coder2' unchanged (same name)"
  control-agent-server api POST /api/agent-profiles/qa-f21-coder2/rename --json '{"new_name": "qa-f21-acp"}' --expect 409 \
    --check detail eq "Agent profile 'qa-f21-acp' already exists" --save F21.rename/conflict
  control-agent-server api GET /api/agent-profiles/qa-f21-acp --check profile.id eq "$ACP"
  control-agent-server api POST /api/agent-profiles/qa-f21-coder2/rename --json '{"new_name": "qa-f21-coder"}' --expect 200
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --check profile.id eq "$CODER"
  ```
  文件的 id 和修订版本会随着文件一起移动（`name` 字段会被重写），指针仍然指向 id，旧名已释放，同名重命名是无操作，取名失败返回 409，两个配置都保留。 该条目被重命名，以便以后的列表项。
- **删除(`F21.delete`)。**一个不活跃的配置文件，然后一个是活跃的。

  需要：`F21.save-create`
  ```sh
  DEFAULT_ID=$(control-agent-server api GET /api/agent-profiles --field profiles | jq -r '.[] | select(.name == "default") | .id')
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200
  control-agent-server api POST /api/agent-profiles/qa-f21-tmp --json '{"llm_profile_ref": "deepseek-flash"}' --expect 201
  control-agent-server api DELETE /api/agent-profiles/qa-f21-tmp --expect 200 --check message eq "Agent profile 'qa-f21-tmp' deleted" \
    --save F21.delete/delete
  control-agent-server api GET /api/agent-profiles/qa-f21-tmp --expect 404
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-tmp.json' --expect-count 0
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$CODER"
  control-agent-server api POST /api/agent-profiles/qa-f21-doomed --json '{"llm_profile_ref": "deepseek-flash"}' --expect 201
  DOOMED=$(control-agent-server api GET /api/agent-profiles/qa-f21-doomed --field profile.id)
  control-agent-server api POST "/api/agent-profiles/$DOOMED/activate" --expect 200
  control-agent-server api DELETE /api/agent-profiles/qa-f21-doomed --expect 200
  control-agent-server api GET /api/agent-profiles --check active_agent_profile_id eq "$DEFAULT_ID" --save F21.delete/list-after-active \
    --field profiles | jq -e 'map(.name) | (index("qa-f21-doomed") == null) and (map(select(. == "default")) | length == 1)'
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$DEFAULT_ID" --check agent_settings.agent_kind eq openhands \
    --check agent_settings.llm.model eq deepseek/deepseek-flash
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200
  ```
  不活动的删除会删除文件，但会保留指针。 删除活跃的配置文件会选中两个视图中的现有默认配置，不会改变OpenHands的设置，并保留默认ID。 指针回到 `qa-f21-coder`。
- **活动 ACP 重置 (`F21.delete-active-acp-reset`)。** ACP 上的实时设置与一台 MCP 服务器，然后活动配置文件将被删除。

  需要：`F21.save-create`
  ```sh
  DEFAULT_ID=$(control-agent-server api GET /api/agent-profiles --field profiles | jq -r '.[] | select(.name == "default") | .id')
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "acp", "acp_server": "codex"}}' \
    --expect 200 --check agent_settings.agent_kind eq acp
  control-agent-server api POST /api/settings/mcp/qa-f21-mcp --expect 201 \
    --json '{"transport": "http", "url": "https://example.invalid/mcp", "description": "QA F21"}'
  control-agent-server api POST /api/agent-profiles/qa-f21-acp-active --json '{"agent_kind": "acp", "acp_server": "codex"}' --expect 201
  ACTIVE_ACP=$(control-agent-server api GET /api/agent-profiles/qa-f21-acp-active --field profile.id)
  control-agent-server api POST "/api/agent-profiles/$ACTIVE_ACP/activate" --expect 200
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$ACTIVE_ACP" --check agent_settings.agent_kind eq acp \
    --check agent_settings.mcp_config.qa-f21-mcp exists
  control-agent-server api DELETE /api/agent-profiles/qa-f21-acp-active --expect 200
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$DEFAULT_ID" --check agent_settings.agent_kind eq openhands \
    --check agent_settings.acp_server missing --check agent_settings.mcp_config.qa-f21-mcp.url eq https://example.invalid/mcp \
    --save F21.delete-active-acp-reset/settings
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200
  control-agent-server api GET /api/settings --check agent_settings.llm.model eq deepseek/deepseek-flash \
    --check llm_api_key_is_set eq true --check active_agent_profile_id eq "$CODER"
  ```
  删除后，指针选择 `default` 和 `agent_settings` 是新的 OpenHands 默认值，这些默认值仍然有效 `qa-f21-mcp`。 把的
  `deepseek-flash` LLM 配置文件和 `qa-f21-coder` 恢复运行。
- **具体化可解析的配置文件 (`F21.materialize-valid`)。**一个存储的配置文件，命名活动的 LLM 配置文件、`qa-f21-mcp` 和机密。

  需要：`F21.save-create`
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-preview --expect 201 \
    --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": ["qa-f21-mcp"], "secret_refs": ["QA_F21_ALLOWED"], "system_message_suffix": "QA F21 suffix"}'
  N_CONV=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /api/agent-profiles/qa-f21-preview/materialize --expect 200 --quiet \
    --check agent_kind eq openhands --check valid eq true --check errors len-eq 0 --check llm_profile_ref eq deepseek-flash \
    --check llm_profile_resolved eq true --check llm_api_key_set eq true --check resolved_mcp_config_keys contains qa-f21-mcp \
    --check dangling_mcp_server_refs len-eq 0 --check resolved_skills contains qa-f21-skill --check secret_refs contains QA_F21_ALLOWED \
    --check resolved_settings.llm.model eq deepseek/deepseek-flash --check resolved_settings.llm.api_key eq '**********' \
    --check resolved_settings.tools len-eq 0 --check resolved_settings.mcp_config.qa-f21-mcp.url eq https://example.invalid/mcp \
    --check resolved_settings.agent_context.system_message_suffix eq 'QA F21 suffix' --save F21.materialize-valid/stored
  RAW="$AGENT_SERVER_VERIFY_RUN/private/qa-f21-materialize.json"
  control-agent-server api POST /api/agent-profiles/qa-f21-preview/materialize --expect 200 --quiet --raw-out "$RAW"
  grep -q deepseek/deepseek-flash "$RAW"
  if grep -qF "$DEEPSEEK_API_KEY" "$RAW"; then false; fi
  rm -f "$RAW"
  control-agent-server api GET /api/agent-profiles/qa-f21-preview --check profile.revision eq 0
  control-agent-server api GET /api/conversations/count --check . eq "$N_CONV"
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$CODER"
  ```
  预览解决所有问题，列出`qa-f21-skill`作为技能，`resolved_settings`中的密钥被隐藏，原始体（保留在运行的私有目录中并被移除）从未包含密钥。 该用户的版本、对话次数和指针未改变。
- **悬空引用 (`F21.materialize-dangling`).**保存时不检查引用； 实现报告他们。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-dangling --expect 201 \
    --json '{"llm_profile_ref": "qa-f21-missing", "tools": [], "mcp_server_refs": ["qa-f21-mcp", "qa-f21-nomcp"], "enable_classify_and_switch_llm_tool": true, "meta_profile_ref": "qa-f21-nometa"}'
  control-agent-server api POST /api/agent-profiles/qa-f21-dangling/materialize --expect 200 --check valid eq false \
    --check errors contains "LLM profile 'qa-f21-missing' not found" --check errors contains 'MCP server(s) not configured: qa-f21-nomcp' \
    --check errors contains "Meta-profile 'qa-f21-nometa' not found" --check llm_profile_resolved eq false \
    --check dangling_mcp_server_refs len-eq 1 --check dangling_mcp_server_refs contains qa-f21-nomcp \
    --check resolved_mcp_config_keys contains qa-f21-mcp --check dangling_meta_profile_ref eq qa-f21-nometa \
    --check resolved_settings missing --save F21.materialize-dangling/stored
  control-agent-server api POST /api/agent-profiles/qa-f21-dangling/materialize --expect 200 \
    --json '{"profile": {"llm_profile_ref": "deepseek-flash", "tools": [{"name": "qa_no_such_tool"}], "mcp_server_refs": []}}' \
    --check valid eq false --check unusable_tools contains qa_no_such_tool \
    --check errors contains 'Tool(s) this server cannot run: qa_no_such_tool' --check resolved_settings missing --save F21.materialize-dangling/tool
  control-agent-server api DELETE /api/agent-profiles/qa-f21-dangling --expect 200
  ```
  两者都是200，`valid` False：缺失的三个参考项一起列出（`qa-f21-mcp`仍然有效），并且报告了一个未知工具不可用。
- **草稿预览(`F21.materialize-draft`)。**草稿永远不会保存。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-draft/materialize --expect 200 \
    --json '{"profile": {"name": "qa-f21-other", "agent_kind": "acp", "acp_server": "claude-code"}}' \
    --check agent_kind eq acp --check valid eq true --check acp_api_key_secret_name eq ANTHROPIC_API_KEY \
    --check acp_base_url_secret_name eq ANTHROPIC_BASE_URL --check llm_profile_ref missing \
    --check resolved_settings.acp_server eq claude-code --save F21.materialize-draft/acp
  control-agent-server api GET /api/agent-profiles/qa-f21-draft --expect 404
  control-agent-server api GET /api/agent-profiles/qa-f21-other --expect 404
  control-agent-server api POST /api/agent-profiles/qa-f21-acp/materialize --expect 200 \
    --check acp_api_key_secret_name eq OPENAI_API_KEY --check acp_file_secret_names contains CODEX_AUTH_JSON
  control-agent-server api POST /api/agent-profiles/qa-f21-preview/materialize --expect 200 --quiet \
    --json '{"profile": {"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": [], "disabled_skills": ["qa-f21-skill"]}}' \
    --check valid eq true --check disabled_skills contains qa-f21-skill --check resolved_skills not-contains qa-f21-skill \
    --check resolved_skills len-ge 1 --check resolved_mcp_config_keys len-eq 0 --save F21.materialize-draft/disabled-skill
  control-agent-server api POST /api/agent-profiles/qa-f21-preview/materialize --expect 200 --quiet \
    --json '{"profile": {"llm_profile_ref": "deepseek-flash", "tools": []}}' --check valid eq true --check mcp_server_refs missing \
    --check resolved_mcp_config_keys contains qa-f21-mcp --check resolved_settings.mcp_config.qa-f21-mcp.url eq https://example.invalid/mcp \
    --save F21.materialize-draft/all-mcp
  control-agent-server api GET /api/agent-profiles/qa-f21-preview --check profile.disabled_skills len-eq 0 \
    --check profile.mcp_server_refs contains qa-f21-mcp --check profile.revision eq 0
  control-agent-server api POST /api/agent-profiles/qa-f21-draft/materialize --json '{"profile": "qa"}' --expect 422 \
    --check detail.0.msg contains 'profile must be an object'
  control-agent-server api POST /api/agent-profiles/qa-f21-draft/materialize --expect 422 \
    --json '{"profile": {"agent_kind": "acp", "llm_profile_ref": "deepseek-flash"}}' --check detail.0.type eq extra_forbidden
  control-agent-server api POST /api/agent-profiles/qa-f21-draft/materialize --json '{"qa_extra": 1}' --expect 422 \
    --check detail.0.type eq extra_forbidden --save F21.materialize-draft/extra-key
  control-agent-server api DELETE /api/settings/mcp/qa-f21-mcp --expect 200
  ```
  ACP 份草稿报告了提供者的凭据机密名称（Claude
  代码：`ANTHROPIC_API_KEY`； 存储的 Codex 配置文件：`OPENAI_API_KEY` 或
  的 `CODEX_AUTH_JSON` 文件不存在，且两个名称下都没有存储任何内容。 存储中的草稿 `qa-f21-preview` drops `qa-f21-skill` 从技能（列出的预览存储）中，以及  `mcp_server_refs`  `[]`, resolves no MCP 服务器，而一个没有 [draft] 的 [server] `mcp_server_refs` (null) 解决了 `qa-f21-mcp`; 存储的配置文件保持原样。 非对象草稿、跨类字段和未知的顶级密钥是 422。 的 MCP 服务器已移除。
- **最多 50 (`F21.limit`)。**将商店装满。 每路大约有五十个API个电话，所以子弹大约需要一分钟。
  ```sh
  N=$(control-agent-server api GET /api/agent-profiles --field profiles | jq length)
  test "$N" -lt 50
  for i in $(seq "$N" 49); do
    control-agent-server api POST "/api/agent-profiles/qa-f21-fill-$i" --json '{"llm_profile_ref": "deepseek-flash"}' --expect 201 --quiet >/dev/null
  done
  control-agent-server api GET /api/agent-profiles --check profiles len-eq 50 --quiet
  control-agent-server api POST /api/agent-profiles/qa-f21-over --json '{"llm_profile_ref": "deepseek-flash"}' --expect 409 \
    --check detail eq 'Agent profile limit reached (50). Delete a profile before saving a new one.' --save F21.limit/over
  control-agent-server api GET /api/agent-profiles/qa-f21-over --expect 404
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-over.json' --expect-count 0
  control-agent-server api POST /api/agent-profiles/qa-f21-fill-49 --json '{"llm_profile_ref": "deepseek-pro"}' --expect 201
  control-agent-server api GET /api/agent-profiles/qa-f21-fill-49 --check profile.revision eq 1 --check profile.llm_profile_ref eq deepseek-pro
  for i in $(seq "$N" 49); do
    control-agent-server api DELETE "/api/agent-profiles/qa-f21-fill-$i" --expect 200 --quiet >/dev/null
  done
  control-agent-server api GET /api/agent-profiles --check profiles len-eq "$N" --quiet
  ```
  第51次创建为409，没有留下文件，而超过容量的覆盖为201； 填充物再次被删除。
- **损坏的文件 (`F21.corrupt-file`)。**存储中的文件不是 JSON（直接写入，因为崩溃或错误编辑会留下它）。
  ```sh
  printf '{not json' > "$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles/qa-f21-corrupt.json"
  control-agent-server api GET /api/agent-profiles --expect 200 --field profiles \
    | jq -e 'map(.name) | (index("qa-f21-corrupt") == null) and (index("qa-f21-coder") != null)'
  control-agent-server api GET /api/agent-profiles/qa-f21-corrupt --expect 400 \
    --check detail contains 'Failed to load profile' --save F21.corrupt-file/get
  control-agent-server api POST /api/agent-profiles/qa-f21-corrupt/materialize --json '{}' --expect 400 --check detail contains 'Failed to load profile'
  control-agent-server api POST /api/agent-profiles/qa-f21-corrupt/rename --json '{"new_name": "qa-f21-corrupt2"}' --expect 400
  control-agent-server api DELETE /api/agent-profiles/qa-f21-corrupt --expect 200
  control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-corrupt*' --expect-count 0
  ```
  列表跳过了文件，但仍然回答了。 阅读、预览或重命名它都会返回 JSON 错误。 DELETE删除它。
- **从个人资料开始对话 (`F21.conversation-start`)。**一个微小的 DeepSeek 在名为 `deepseek-pro` 的配置文件上运行，而
  `deepseek-flash` 保持活动状态 LLM。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-runner --json '{"llm_profile_ref": "deepseek-pro", "tools": [], "mcp_server_refs": []}' --expect 201
  RUNNER=$(control-agent-server api GET /api/agent-profiles/qa-f21-runner --field profile.id)
  control-agent-server api GET /api/settings --check active_profile eq deepseek-flash --check agent_settings.llm.model eq deepseek/deepseek-flash \
    --check agent_settings.tools missing
  RCID=$(control-agent-server conversation start --agent-profile qa-f21-runner --no-autotitle --prompt 'Reply with exactly: ok' \
    --wait --until finished,error,stuck --timeout 240 --print-id --save F21.conversation-start/start)
  control-agent-server api GET "/api/conversations/$RCID" --quiet --check execution_status eq finished \
    --check launched_agent_profile.agent_profile_id eq "$RUNNER" --check launched_agent_profile.revision eq 0 \
    --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.tools len-eq 0 \
    --check stats.usage_to_metrics.default.model_name eq deepseek/deepseek-v4-pro \
    --check stats.usage_to_metrics.default.accumulated_token_usage.prompt_tokens gt 0 --save F21.conversation-start/get
  control-agent-server conversation events "$RCID" --key stats --contains deepseek/deepseek-v4-pro --expect-min 1
  control-agent-server ws listen "/sockets/events/$RCID" --query resend_mode=all --expect-kind SystemPromptEvent \
    --expect-kind MessageEvent --duration 5 --save F21.conversation-start/ws-replay
  control-agent-server api POST /api/agent-profiles/qa-f21-runner --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": []}' --expect 201
  control-agent-server api GET /api/agent-profiles/qa-f21-runner --check profile.revision eq 1 --check profile.id eq "$RUNNER"
  control-agent-server api GET "/api/conversations/$RCID" --quiet --check launched_agent_profile.revision eq 0 \
    --check agent.llm.model eq deepseek/deepseek-v4-pro
  ```
  对话在`deepseek/deepseek-v4-pro`（LLM，而不是`deepseek-flash`的活跃状态）结束：智能体，统计数据，`stats`状态事件，以及WebSocket回放一致。 它的智能体包含空的工具列表，`tools`和null会提供服务器的标准工具，而`launched_agent_profile`则指定了版本0的配置文件ID。 之后编辑个人资料会增加其修订记录，但不会增加对话记录或模型。
- **机密范围(`F21.secret-scope`).**有作用域和无作用域配置文件上的两个启动时间相同机密； 两个对话都没有运行。

  需要：`F21.conversation-start`
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-scoped --expect 201 \
    --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": [], "secret_refs": ["QA_F21_ALLOWED"]}'
  SCID=$(control-agent-server conversation start --agent-profile qa-f21-scoped --no-autotitle \
    --secret QA_F21_ALLOWED=qa-f21-allowed-value --secret QA_F21_OTHER=qa-f21-other-value --print-id)
  UCID=$(control-agent-server conversation start --agent-profile qa-f21-runner --no-autotitle \
    --secret QA_F21_ALLOWED=qa-f21-allowed-value --secret QA_F21_OTHER=qa-f21-other-value --print-id)
  control-agent-server api PATCH "/api/conversations/$SCID" --json '{"tags": {"qa": "f21-scope"}}' --expect 200 --quiet
  control-agent-server api PATCH "/api/conversations/$UCID" --json '{"tags": {"qa": "f21-scope"}}' --expect 200 --quiet
  control-agent-server api GET "/api/conversations/$SCID" --quiet --check launched_agent_profile.secret_refs len-eq 1 \
    --check launched_agent_profile.secret_refs contains QA_F21_ALLOWED \
    --check secret_registry.secret_sources.QA_F21_ALLOWED.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F21_OTHER missing --save F21.secret-scope/scoped
  control-agent-server api GET "/api/conversations/$UCID" --quiet --check launched_agent_profile.agent_profile_id eq "$RUNNER" \
    --check launched_agent_profile.secret_refs missing \
    --check secret_registry.secret_sources.QA_F21_ALLOWED.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F21_OTHER.kind eq StaticSecret --save F21.secret-scope/unscoped
  control-agent-server state grep QA_F21_OTHER --glob "server/workspace/conversations/${UCID//-/}/base_state.json"
  control-agent-server state grep QA_F21_ALLOWED --glob "server/workspace/conversations/${SCID//-/}/base_state.json"
  control-agent-server state grep QA_F21_OTHER --glob "server/workspace/conversations/${SCID//-/}/**/*" --expect-none
  control-agent-server state grep qa-f21-other-value --glob 'server/**/*' --expect-none
  ```
  两者都创造了成功。 在每个会话的状态被标签编辑保存后，该会话的 scoped 会记录允许列表，并只保留 `QA_F21_ALLOWED`
  while the unscoped one (also launched from a profile, `qa-f21-runner`,
  没有 `secret_refs`) 保留两者，所以过滤器来自
  `secret_refs`. 磁盘上无范围对话的状态名称
  `QA_F21_OTHER` 和仅限范围内的姓名 `QA_F21_ALLOWED`（范围内对话的文件中没有提及删除的姓名）。 不存储明文机密值。
- **启动添加项 (`F21.launch-additions`)。**部署在启动时将文本附加到配置文件的提示词后缀； 对话收到一条排队消息并且不运行。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f21-additions --expect 201 \
    --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": [], "system_message_suffix": "QA F21 profile suffix"}'
  ADDID=$(control-agent-server api GET /api/agent-profiles/qa-f21-additions --check profile.revision eq 0 --field profile.id)
  ACID=$(control-agent-server conversation start --agent-profile qa-f21-additions --no-autotitle --no-run --prompt 'QA F21 additions, not run' \
    --body-json '{"agent_launch_additions": {"system_message_suffix_append": "QA_F21_APPENDED"}}' --print-id --save F21.launch-additions/start)
  control-agent-server api GET "/api/conversations/$ACID" --quiet --check launched_agent_profile.agent_profile_id eq "$ADDID" \
    --check launched_agent_profile.revision eq 0 --check agent_launch_additions missing \
    --check agent.agent_context.system_message_suffix eq "$(printf 'QA F21 profile suffix\n\nQA_F21_APPENDED')" --save F21.launch-additions/get
  control-agent-server conversation events "$ACID" --kinds SystemPromptEvent --contains QA_F21_APPENDED --expect-count 1
  control-agent-server state grep QA_F21_APPENDED --glob "server/workspace/conversations/${ACID//-/}/base_state.json"
  control-agent-server state grep QA_F21_APPENDED --glob "server/workspace/conversations/${ACID//-/}/meta.json" --expect-none
  control-agent-server state cat meta.json --conversation "$ACID" --check agent_launch_additions missing --check launched_agent_profile.agent_profile_id eq "$ADDID"
  control-agent-server api GET /api/agent-profiles/qa-f21-additions --check profile.id eq "$ADDID" --check profile.revision eq 0 \
    --check profile.system_message_suffix eq 'QA F21 profile suffix'
  N_CONV=$(control-agent-server api GET /api/conversations/count --field .)
  W="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f21-additions"
  mkdir -p "$W"
  control-agent-server api POST /api/conversations --expect 422 \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$ADDID\", \"agent_launch_additions\": {\"qa_unknown\": \"x\"}}" \
    --check detail.0.type eq extra_forbidden --check detail.0.loc contains qa_unknown --save F21.launch-additions/unknown-key
  LONG=$(printf 'a%.0s' $(seq 1 32769))
  control-agent-server api POST /api/conversations --expect 422 --quiet \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$ADDID\", \"agent_launch_additions\": {\"system_message_suffix_append\": \"$LONG\"}}" \
    --check detail.0.type eq string_too_long --check detail.0.loc contains system_message_suffix_append \
    --check detail.0.ctx.max_length eq 32768 --save F21.launch-additions/too-long
  control-agent-server api GET /api/conversations/count --check . eq "$N_CONV"
  ```
  启动智能体后缀是该文件的后缀，一个空行，然后是附加的文本，和  `SystemPromptEvent` （当消息被队列中存储时）携带它； 记录了版本0的用户资料。 文本在智能体 state (`base_state.json`) 但这些添加项不是存储的对话字段`meta.json` 该字段和文本都没有，存储的用户资料没有变化。 未知密钥和一个32769个字符的值（最大值为32768）为422，对话次数没有变化。
- **TypeScript 客户端 (`F21.ts-client`).**来自构建客户端的每个 `AgentProfilesClient` 方法（如果缺少，则在此处构建），加上通过 `AgentServerClient.agentProfiles` 到达的相同客户端。

  需要：`F21.lazy-seed`、`F21.save-create`
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server api POST "/api/agent-profiles/$CODER/activate" --expect 200
  F21TS="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f21-ts"
  mkdir -p "$F21TS"
  cat > "$F21TS/ts_agent_profiles.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { AgentProfilesClient, AgentServerClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const options = { host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY };
  const client = new AgentProfilesClient(options);
  const coder = process.env.QA_F21_CODER;
  const before = await client.listAgentProfiles();
  assert.equal(before.active_agent_profile_id, coder);
  assert.equal(before.profiles.filter((p) => p.name === 'default' && p.agent_kind === 'openhands').length, 1);
  const body = { agent_kind: 'openhands', llm_profile_ref: 'deepseek-flash', tools: [], mcp_server_refs: [] };
  assert.deepEqual(await client.saveAgentProfile('qa-f21-ts', body), { name: 'qa-f21-ts', message: "Agent profile 'qa-f21-ts' saved" });
  const saved = (await client.getAgentProfile('qa-f21-ts')).profile;
  assert.equal(saved.revision, 0);
  assert.equal(saved.llm_profile_ref, 'deepseek-flash');
  assert.equal((await client.renameAgentProfile('qa-f21-ts', 'qa-f21-ts2')).name, 'qa-f21-ts2');
  assert.equal((await client.getAgentProfile('qa-f21-ts2')).profile.id, saved.id);
  const activated = await client.activateAgentProfile(saved.id);
  assert.equal(activated.id, saved.id);
  assert.equal(activated.agent_settings_applied, false);
  const server = new AgentServerClient(options);
  assert.equal((await server.agentProfiles.listAgentProfiles()).active_agent_profile_id, saved.id);
  const draft = await client.materializeAgentProfile('qa-f21-ts2', { ...body, llm_profile_ref: 'deepseek-pro' });
  assert.equal(draft.valid, true);
  assert.equal(draft.llm_profile_ref, 'deepseek-pro');
  assert.equal(draft.resolved_settings.llm.model, 'deepseek/deepseek-v4-pro');
  const stored = await client.materializeAgentProfile('qa-f21-ts2');
  assert.equal(stored.valid, true);
  assert.equal(stored.resolved_settings.llm.model, 'deepseek/deepseek-flash');
  assert.equal((await client.getAgentProfile('qa-f21-ts2')).profile.revision, 0);
  assert.equal((await client.deleteAgentProfile('qa-f21-ts2')).message, "Agent profile 'qa-f21-ts2' deleted");
  assert.equal((await client.listAgentProfiles()).active_agent_profile_id, before.profiles.find((p) => p.name === 'default').id);
  assert.equal((await client.activateAgentProfile(coder)).id, coder);
  await assert.rejects(client.getAgentProfile('qa-f21-ts2'), (err) => err.name === 'HttpError' && err.status === 404);
  await assert.rejects(client.materializeAgentProfile('qa-f21-ts2'), (err) => err.name === 'HttpError' && err.status === 404);
  await assert.rejects(client.saveAgentProfile('-qa-f21-bad', body), (err) => err.name === 'HttpError' && err.status === 422);
  const after = await client.listAgentProfiles();
  assert.equal(after.active_agent_profile_id, coder);
  assert.equal(after.profiles.length, before.profiles.length);
  client.close();
  server.close();
  console.log('QA_F21_TS_OK');
  JS
  control-agent-server exec --env QA_F21_CODER="$CODER" --timeout 120 --expect-output QA_F21_TS_OK --save F21.ts-client/program \
    -- node "$F21TS/ts_agent_profiles.mjs"
  control-agent-server api GET /api/agent-profiles --check active_agent_profile_id eq "$CODER" --save F21.ts-client/list-after
  control-agent-server api GET /api/agent-profiles/qa-f21-ts --expect 404
  control-agent-server api GET /api/agent-profiles/qa-f21-ts2 --expect 404
  ```
  该程序打印 `QA_F21_TS_OK`列表已种子化 `default` 和 `qa-f21-coder` active 保存的配置在版本0时读取，通过重命名保持其ID，并通过该ID激活`agent_settings_applied`  False), which `AgentServerClient.agentProfiles` 看见太多。 草稿预览 `deepseek-pro` 在存储的配置仍然预览的情况下 `deepseek-flash` 在修订0（保存的草稿一无所获）。 删除活跃的配置文件会选中原始的默认配置。 after re-activating `qa-f21-coder`阅读或预览时会拒绝，并返回以下错误信息： `HttpError` 404 和一个无效的名称
  422. 之后的 REST 列表同意。
- **重新启动 (`F21.restart`)。**

  需要：`F21.lazy-seed`、`F21.save-create`、`F21.acp-kind`
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/agent-profiles --check active_agent_profile_id eq "$CODER" --save F21.restart/list
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --check profile.id eq "$CODER" --check profile.revision eq 1 \
    --check profile.persona eq 'QA F21 persona'
  control-agent-server api GET /api/agent-profiles/qa-f21-acp --check profile.id eq "$ACP" --check profile.agent_kind eq acp
  control-agent-server api GET /api/agent-profiles/default --check profile.id eq "$SEED"
  control-agent-server api GET /api/settings --check active_agent_profile_id eq "$CODER"
  control-agent-server doctor
  ```
  每个用户资料都保留其ID和修订版本，指针仍然命名
  `qa-f21-coder`; `doctor`重启后就ok了。
- **ACP 技能来源 (`F21.acp-skill-sourcing`).**存储的 Codex 配置文件 `qa-f21-acp` 和草稿 OpenHands，在默认情况下预览
  `native` 采购，在 `openhands_managed` 下，然后再次在默认下。 不需要 ACP 二进制文件：materialize 会在不启动智能体的情况下构建它。

  需要：`F21.acp-kind`
  ```sh
  OH_DRAFT='{"profile": {"llm_profile_ref": "deepseek-flash", "tools": [], "mcp_server_refs": []}}'
  control-agent-server api POST /api/agent-profiles/qa-f21-skills/materialize --expect 200 --quiet --json "$OH_DRAFT" \
    --check valid eq true --check resolved_skills contains qa-f21-skill --save F21.acp-skill-sourcing/openhands-native
  control-agent-server api POST /api/agent-profiles/qa-f21-acp/materialize --expect 200 --quiet --check agent_kind eq acp \
    --check valid eq true --check resolved_skills len-eq 0 --check resolved_settings.agent_context.skills len-eq 0 \
    --check resolved_settings.agent_context.load_user_skills eq false --check resolved_settings.agent_context.load_public_skills eq false \
    --save F21.acp-skill-sourcing/acp-native
  control-agent-server restart --env OH_ACP_SKILL_SOURCING=openhands_managed
  control-agent-server api POST /api/agent-profiles/qa-f21-acp/materialize --expect 200 --quiet --check agent_kind eq acp \
    --check valid eq true --check resolved_skills contains qa-f21-skill \
    --check resolved_settings.agent_context.skills contains '"name": "qa-f21-skill"' \
    --check resolved_settings.agent_context.load_project_skills eq false --save F21.acp-skill-sourcing/acp-managed
  control-agent-server api POST /api/agent-profiles/qa-f21-skills/materialize --expect 200 --quiet --json "$OH_DRAFT" \
    --check valid eq true --check resolved_skills contains qa-f21-skill
  control-agent-server restart --reset-config
  control-agent-server api POST /api/agent-profiles/qa-f21-acp/materialize --expect 200 --quiet --check valid eq true \
    --check resolved_skills len-eq 0 --save F21.acp-skill-sourcing/acp-native-again
  control-agent-server api GET /api/agent-profiles/qa-f21-acp --check profile.id eq "$ACP" --check profile.revision eq 0
  control-agent-server api GET /api/agent-profiles/qa-f21-skills --expect 404
  ```
  在 `native`（本地主机服务器：ACP CLI 读取自己的本地配置）下，ACP 预览没有技能和没有技能加载标志，而 OpenHands 同一服务器上的草稿则列出
  `qa-f21-skill`，所以目录就在那里。 与
  `OH_ACP_SKILL_SOURCING=openhands_managed` ACP 预览注入目录，`qa-f21-skill` 包含（项目技能保持关闭：CLI 读取
  `AGENTS.md`本身），OpenHands草案保持不变。 回到默认设置，ACP 预览再次为空； 存储的配置文件从未改变，草稿也没有保存任何内容。
- **[已弃用] 仓库繁忙`F21.store-busy`).** 子弹的自身弹壳储存了商店的文件锁 (`flock` 在文件描述符9上打开的锁文件服务器使用的文件，因为另一个进程共享持久化目录。

  需要：`F21.save-create`
  ```sh
  LOCK="$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles/.agent-profiles.lock"
  exec 9>>"$LOCK"
  flock -w 5 9
  T0=$SECONDS
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --timeout 90 --expect 503 \
    --check exception contains 'Profile store is busy' --save F21.store-busy/busy
  test $((SECONDS - T0)) -ge 25
  test $((SECONDS - T0)) -le 45
  flock -u 9
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 200 --check profile.id eq "$CODER"
  ```
  请求等待了30秒锁超时，然后返回了503（5xx体为 `{"detail": "Internal Server Error", "exception": "503: Profile store is busy. Please retry."}`)。 一旦锁发布，GET将变为200。 锁也会随着子弹壳的退出而消失。
- **对话开始时繁忙的商店`F21.launch-store-busy`).** 同理锁这次是基于用户头像的 `POST /api/conversations` (带有 id: [sent]) `conversation start --agent-profile` 通过列表路由解析名称，该路由也等待在同一个地方锁).

  需要：`F21.save-create`
  ```sh
  W="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f21-busy"
  mkdir -p "$W"
  N_CONV=$(control-agent-server api GET /api/conversations/count --field .)
  LOCK="$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles/.agent-profiles.lock"
  exec 9>>"$LOCK"
  flock -w 5 9
  T0=$SECONDS
  (exec 9>&-; control-agent-server api POST /api/conversations --timeout 90 --expect 503 \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$CODER\", \"autotitle\": false}" \
    --check exception contains 'Agent profile store is busy' --save F21.launch-store-busy/busy) &
  BUSY=$!
  sleep 5
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 2000 --save F21.launch-store-busy/alive
  wait "$BUSY"
  test $((SECONDS - T0)) -ge 25
  test $((SECONDS - T0)) -le 45
  flock -u 9
  control-agent-server api GET /api/conversations/count --check . eq "$N_CONV"
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 200 --check profile.id eq "$CODER"
  ```
  创建等待30秒锁超时并返回 503 (`exception`  `503: Agent profile store is busy` 重试失败的启动存储失败]，也没有创建对话。 像用户信息路由一样（`F21.busy-blocks-server`), 启动会解决该配置线程，so `/alive` 在创建时等待两秒钟，而答案则立即给出（裸体） `sleep 5` 只有创建请求才能到达服务器。
- **锁等待不会停止服务器 (`F21.busy-blocks-server`)。**处理程序是简单的 `def`（并且 `materialize` 使用以下命令加载配置文件
  `asyncio.to_thread`），因此商店的同步 file-锁等待在工作线程线程中运行，而不是在事件循环中运行。
  ```sh
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 2000
  control-agent-server api GET /api/agent-profiles --expect 200 --quiet > /dev/null  # 在 --only 下创建存储目录
  LOCK="$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles/.agent-profiles.lock"
  exec 9>>"$LOCK"
  flock -w 5 9
  (exec 9>&- >/dev/null 2>&1; control-agent-server api GET /api/agent-profiles/qa-f21-coder --timeout 90 --quiet) &
  sleep 5
  control-agent-server api GET /alive --auth none --expect 200 --timeout 60 --expect-max-ms 2000 --save F21.busy-blocks-server/alive
  flock -u 9
  wait
  ```
  `/alive` 在两秒内回答问题，而个人信息请求则等待锁 (裸的) `sleep 5` 只有让请求到达服务器，，因此协调器探针继续传递，而另一个进程持有锁。 背景请求不继承锁因此，它会在 shell 释放后立即结束。
- **如何一个悬垂的 LLM 报告了参考`F21.dangling-llm-report`).** 服务器的种子代码 (`_seed_default_llm_profile` 在结算页面中，如何生成报告会显示种子 `default` whose LLM 该用户不存在。 `dangling_llm_profile_ref` 这是启动的422字段 `unresolved_profile_references` 详细内容（）F04); 仅当具体化发送种子代码时，种子代码才必须从具体化中承诺它。
  ```sh
  CHECKOUT=$(jq -r '.checkout // empty' "$AGENT_SERVER_VERIFY_RUN/run.json")
  SEEDSRC="${CHECKOUT:-$PWD}/openhands-agent-server/openhands/agent_server/agent_profiles_router.py"
  test -f "$SEEDSRC"
  RAW="$AGENT_SERVER_VERIFY_RUN/private/qa-f21-dangling-llm.json"
  trap 'rm -f "$RAW"' EXIT
  control-agent-server api POST /api/agent-profiles/qa-f21-draft/materialize --expect 200 --raw-out "$RAW" \
    --json '{"profile": {"llm_profile_ref": "qa-f21-missing", "tools": [], "mcp_server_refs": []}}' \
    --check valid eq false --check llm_profile_ref eq qa-f21-missing --check llm_profile_resolved eq false \
    --check errors contains "LLM profile 'qa-f21-missing' not found" --save F21.dangling-llm-report/materialize
  PROMISED=$(grep -c dangling_llm_profile_ref "$SEEDSRC" || true)
  jq -c --argjson promised "${PROMISED:-0}" '{promised: ($promised > 0), reported: .dangling_llm_profile_ref} | .agree = ((.promised | not) or .reported == "qa-f21-missing")' "$RAW" \
    | control-agent-server assert --check agree eq true
  ```
  正确的行为：两者一致，或者因为 `dangling_llm_profile_ref` 名称了 MCP 的悬空引用（因为它也命名了 `dangling_mcp_server_refs` 中的悬空服务器和元架构）
  `dangling_meta_profile_ref`）或者因为种子代码不再承诺它。 预览草稿而不保存，排列步骤证明参考已报告（`valid` False、`llm_profile_resolved` False、`errors` 条目）。 种子代码准确地描述了该报告（`valid` False、`llm_profile_resolved` False、`errors` 条目），但没有命名 `dangling_llm_profile_ref`，只有启动的 422 才会携带该名称（#5871）。
- **TypeScript  载荷 types (`F21.ts-payload-types`), 已知错误。** 客户端的手写输入在 `clients/typescript/src/models/agent-profile.ts` 与服务器发送的列表摘要和有关 OpenHands and an ACP 读取 [profile] 的信息 GET, 并生成一份材料报告。 每个载荷'的键变成了客户端自己的对象字面量 `tsc` 类型检查首先针对生成的合同进行`dist/generated/agent-server-schema.js`然后，对导出的类型进行测试。

  需要：`F21.save-create`、`F21.acp-kind`
  ```sh
  D="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f21-types"
  mkdir -p "$D"
  test -x clients/typescript/node_modules/.bin/tsc || (cd clients/typescript && npm ci)
  control-agent-server api GET /api/agent-profiles --expect 200 --quiet --raw-out "$D/list.json"
  control-agent-server api GET /api/agent-profiles/qa-f21-coder --expect 200 --quiet --raw-out "$D/openhands.json"
  control-agent-server api GET /api/agent-profiles/qa-f21-acp --expect 200 --quiet --raw-out "$D/acp.json"
  control-agent-server api POST /api/agent-profiles/qa-f21-acp/materialize --expect 200 --quiet --raw-out "$D/diagnostics.json" \
    --check resolved_mcp_config_keys exists --check resolved_skills exists --check resolved_mcp_servers missing
  printf '%s\n' 'export type RequiredKeys<T> = { [K in keyof T]-?: {} extends Pick<T, K> ? never : K }[keyof T];' \
    'export type Shape<T> = Record<RequiredKeys<T>, true> & Partial<Record<keyof T, true>>;' > "$D/shape.ts"
  SUMMARY=$(jq -c '.profiles[0] | with_entries(.value = true)' "$D/list.json")
  OPENHANDS=$(jq -c '.profile | with_entries(.value = true)' "$D/openhands.json")
  ACPKEYS=$(jq -c '.profile | with_entries(.value = true)' "$D/acp.json")
  DIAG=$(jq -c 'with_entries(.value = true)' "$D/diagnostics.json")
  DIST="$PWD/clients/typescript/dist"
  printf '%s\n' "import type { AgentProfileInfo, OpenHandsAgentProfile, AcpAgentProfile, AgentProfileDiagnostics } from '$DIST/generated/agent-server-schema.js';" \
    "import type { Shape } from './shape.js';" "export const summary: Shape<AgentProfileInfo> = $SUMMARY;" \
    "export const openhands: Shape<OpenHandsAgentProfile> = $OPENHANDS;" "export const acp: Shape<AcpAgentProfile> = $ACPKEYS;" \
    "export const diagnostics: Shape<AgentProfileDiagnostics> = $DIAG;" > "$D/contract.ts"
  printf '%s\n' "import type { AgentProfileSummary, OpenHandsAgentProfile, ACPAgentProfile, AgentProfileDiagnostics } from '$DIST/index.js';" \
    "import type { Shape } from './shape.js';" "export const summary: Shape<AgentProfileSummary> = $SUMMARY;" \
    "export const openhands: Shape<OpenHandsAgentProfile> = $OPENHANDS;" "export const acp: Shape<ACPAgentProfile> = $ACPKEYS;" \
    "export const diagnostics: Shape<AgentProfileDiagnostics> = $DIAG;" > "$D/exported.ts"
  TSC="clients/typescript/node_modules/.bin/tsc --noEmit --strict --skipLibCheck --target es2020 --module esnext --moduleResolution bundler"
  $TSC "$D/contract.ts"
  $TSC "$D/exported.ts" | control-agent-server assert --check . not-contains 'error TS'  # bug：值包含 TS2353 && 值包含 public_skills && 值包含 'Shape<OpenHandsAgentProfile>' && 值包含 'Shape<AgentProfileDiagnostics>'
  ```
  预期：两个文件都进行类型检查，因此 TypeScript 消费者 (智能体
  Canvas 的配置文件编辑器）可以读取服务器以其真实姓名发送的每个字段：`AgentProfileDiagnostics` 声明 `resolved_mcp_config_keys`，
  `resolved_skills`、`disabled_skills` 和元配置文件字段（并且没有
  `resolved_mcp_servers`), `OpenHandsAgentProfile` 声明
  `disabled_skills`、`meta_profile_ref` 和
  `enable_classify_and_switch_llm_tool`（并且没有 `skills`，保存会拒绝 422 `extra_forbidden`），并且 `ACPAgentProfile` 声明
  `acp_startup_timeout`. 客户的单元测试
  `agent-server-contract-types.test.ts` 针对生成的合约固定相同的密钥集。 稍后的 `public_skills` 字段现在存在于实时 OpenHands 配置文件和具体化报告以及生成的合同中，但在两种导出类型中均不存在。 生成的阳性对照仍然通过； 导出的类型失败，并显示 TS2353 命名 `public_skills` ([OpenHands/software-智能体-SDK#6183](https://github.com/OpenHands/software-agent-sdk/issues/6183))。
- **`.json` 名字保持不变 (`F21.json-suffix-identity`).** 商店去掉后缀 `.json` 从文件名和从配置的 `name`, so `x.json` 和 `x` 都是一个 [profile]。
  ```sh
  if control-agent-server api POST /api/agent-profiles/qa-f21-suffix.json --json '{"llm_profile_ref": "deepseek-flash"}' --expect 201 --quiet; then
    J1=$(control-agent-server api GET /api/agent-profiles/qa-f21-suffix.json --check profile.revision eq 0 \
      --check profile.llm_profile_ref eq deepseek-flash --field profile.id)
    control-agent-server api POST "/api/agent-profiles/$J1/activate" --expect 200
    control-agent-server api POST /api/agent-profiles/qa-f21-suffix.json --json '{"llm_profile_ref": "deepseek-pro"}' --expect 201
    control-agent-server api GET /api/agent-profiles/qa-f21-suffix.json --check profile.llm_profile_ref eq deepseek-pro \
      --save F21.json-suffix-identity/after-overwrite
    control-agent-server api GET /api/agent-profiles/qa-f21-suffix.json --check profile.id eq "$J1" --check profile.revision eq 1
    control-agent-server api DELETE /api/agent-profiles/qa-f21-suffix.json --expect 200
    DEF=$(control-agent-server api GET /api/agent-profiles/default --field profile.id)
    control-agent-server api GET /api/settings --check active_agent_profile_id ne "$J1" \
      --check active_agent_profile_id eq "$DEF"
  else
    control-agent-server api POST /api/agent-profiles/qa-f21-suffix.json --json '{"llm_profile_ref": "deepseek-flash"}' --expect 422
    control-agent-server state ls 'home/.openhands/agent-profiles/qa-f21-suffix*' --expect-count 0
  fi
  ```
  覆盖操作保持不变 `J1` 并且移动到修订1，删除活跃的配置文件会将指针移出 `J1` to `default`; or (the `else` 如果服务器拒绝名称，保存将返回 422 并存储空值。 安排步骤首先证明了覆盖已发生（第二步） GET serves `deepseek-pro`). 存储和列出的名字是 `qa-f21-suffix` 文件名前缀，以及身份查找和 DELETE 比较这个名称，所以  `.json` 拼写达到相同的 id。 这个圆点最后留着：它留下运行
  with `default` active.

<a id="gotchas"></a>

## 陷阱

- 在空的存储中，没有有效的指针时，`GET /api/agent-profiles` 不是只读：它可以写入 `agent-profiles/default.json` 和 `settings.json`，并且当没有 LLM 角色活跃时，会将一个键值的活 LLM 作为 `default` LLM 角色的镜像。 未设置或悬空的指针选择 `default`，在不存在时为其播种 (#5983)； 不可读的默认或完整存储会回退到另一个配置文件。 删除活动配置文件也会修复指针。 使用其他路线进行只读探测； `doctor`确实如此。
- 种子 `default` 引用活动的 LLM 配置文件，因此当智能体配置文件存在 (F20) 时，无法删除 LLM 配置文件 (409)。
- 激活采用稳定的 uuid； 所有其他路线均采用该名称。 保存响应没有 id：用 GET 读回它。
- 激活永远不会触及 `agent_settings`，并且以 `agent_profile_id` 开始的对话会在开始时解析配置文件； 活动指针只是一个 UI 选择。 `conversation start` 没有
  `--agent-profile`从`agent_settings`开始，而不是从指针开始。
- 创建保留客户端提供的 `revision`（带有 `"revision": 7` 的主体从 7 开始）； 仅覆盖忽略它。 食谱将其排除在创造之外。
- `PATCH /api/settings` 切换 `agent_kind` 重建
  `agent_settings` 来自新基地并掉落 `mcp_config` (F18)，因此 ACP 子弹在切换后添加 `qa-f21-mcp`； 相反，删除活动配置文件会保留它。
- Materialise 发现用户和公共技能； 公共目录可以在首次使用时从 GitHub 克隆到 `OH_PERSISTENCE_DIR/cache/skills`（离线时允许）。 食谱仅在运行时断言
  `qa-f21-skill` 和 `len-ge 1`。
- 配置文件始终在流式传输开启的情况下启动其 LLM； 仅当 `enable_classify_and_switch_llm_tool` 为 True 时才检查元配置文件引用。
- 对话开始时给出的机密保留在内存中并在重新启动后继续存在，但 `GET /api/conversations/{id}` 显示空
  `secret_registry` 直到再次保存对话状态（运行、标签编辑）； 机密范围项目符号首先编辑标签，就像 F08 一样。
- 有效的配置文件 JSON 但未列出有效的摘要（读取原始摘要） JSON)，但现在已经400岁了 GET. 通过其他家庭的路线，同样的配置是故意设置为500 `Could not load agent profile` 在 `POST /api/conversations`和一个未处理的500英镑
  `GET /api/settings/secrets?agent_profile_id=` (F18)，当商店繁忙时，它也会回答 500 而不是 503：它加载商店错误映射之外的配置文件。
- 5xx响应（忙503）携带`detail: "Internal Server Error"`和`exception`中的真实消息； 4xx直接携带`detail`。
- 除非另有说明，启动的运行使用 `acp_skill_sourcing` `native`，
  while the agent-server image sets `openhands_managed`: an ACP preview or
  本地运行的启动不包含 OpenHands 技能，而图像中的相同配置文件包含整个目录。 `restart --env` 优先于 `restart --reset-config` 之前的停留。
- 配置文件路由和 `POST /api/conversations` 等待工作器线程中的存储锁：保留的锁仅延迟需要存储的请求，从不延迟 `/alive` (`F21.busy-blocks-server`)。
- `agent_launch_additions` 一次只做：它们不是存储的对话字段，也不修改了用户资料，因此只有智能体状态（`base_state.json`，`SystemPromptEvent`）显示附加文本。
- `--check` 没有列表投影，因此在列表中查找名称的配方将 `--field profiles` 传输到 `jq -e`。
