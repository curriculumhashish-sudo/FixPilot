<a id="server-settings-settings-schemas-and-the-secrets-store"></a>

# 服务器设置、设置模式和机密存储

服务器为每个持久化目录保留一个设置文档和一个名为机密的存储，每个使用者在构建智能体之前都会读取它们。
`GET /api/settings` 返回智能体设置（LLM、MCP、上下文压缩器、工具）、对话设置（`max_iterations`、确认、安全分析器）、活动 LLM、智能体和元配置文件指针以及不透明前端拥有的 `misc_settings`，以及机密已脱敏，除非调用者使用 `X-Expose-Secrets: plaintext` 或 `encrypted` 请求它们。 `PATCH /api/settings` 采用稀疏差异。 模式个路线描述了智能体和对话设置表单。 机密库是一个键值对的扁平映射：列表中不显示值，`GET /api/settings/secrets/{name}` 返回值的原始形式为`text/plain`（SDK's `LookupSecret` URLs 的目标），
`PUT` 更新插入。 这两个文件均使用服务器密码（`OH_SECRET_KEY`，回退到会话密钥）在 REST 处进行 Fernet 加密，并且在重新启动后仍然有效。 设置更改不会发出 WebSocket 事件。

Source: `openhands-agent-server/openhands/agent_server/settings_router.py`, `openhands-agent-server/openhands/agent_server/_secrets_exposure.py`, `openhands-agent-server/openhands/agent_server/persistence/models.py`, `openhands-agent-server/openhands/agent_server/persistence/store.py`, `openhands-sdk/openhands/sdk/settings/api_models.py`, `openhands-sdk/openhands/sdk/settings/model.py`, `openhands-sdk/openhands/sdk/utils/pydantic_secrets.py`, `openhands-sdk/openhands/sdk/utils/cipher.py`, `openhands-sdk/openhands/sdk/workspace/remote/base.py`, `openhands-sdk/openhands/sdk/workspace/repo.py`, `clients/typescript/src/client/settings-client.ts`

需求：`git`、`node`

Routes: `GET /api/settings/agent-schema`, `GET /api/settings/conversation-schema`,
`GET /api/settings`, `PATCH /api/settings`, `GET /api/settings/secrets`,
`GET /api/settings/secrets/{name}`, `PUT /api/settings/secrets`,
`DELETE /api/settings/secrets/{name}`

<a id="sub-features"></a>

## 子功能

- `F18.get-defaults`：在新的持久化目录上，`GET /api/settings` 返回 OpenHands 默认值（无 API 键，`llm_api_key_is_set: false`，每个指针 null，空 `misc_settings`），而不创建 `settings.json`。
- `F18.agent-schema`: `GET /api/settings/agent-schema` 返回 `AgentSettings` 表单模式，其中包含共享、`openhands` 和 `acp` 部分、标记的机密字段以及 `agent_settings` 中存在的每个 OpenHands 字段键。
- `F18.conversation-schema`: `GET /api/settings/conversation-schema` 返回 `ConversationSettings` 模式，其三个字段键和默认值与新服务器上的 `conversation_settings` 匹配。
- `F18.auth-required`：配置了会话密钥后，每个设置和机密都会将 401 路由应答到丢失或错误的 `X-Session-API-Key`，无论 `X-Expose-Secrets` 说什么。
- `F18.patch-llm`：`agent_settings_diff.llm` 的 PATCH 存储模型和密钥，翻转 `llm_api_key_is_set`，创建 `settings.json`，并回答已脱敏，即使发送 `X-Expose-Secrets: plaintext` 也是如此。
- `F18.expose-modes`：GET 默认情况下将机密编辑为 `**********`，使用 `plaintext` 返回原始值，使用 `encrypted`（以及旧版 `true`）返回 Fernet token，对于任何其他值返回 400。
- `F18.roundtrip`：回发加密的token保留真实密钥； 发回已脱敏占位符会将其清除。
- `F18.agent-diff-merge`：`agent_settings_diff` 稀疏合并（诸如键之类的同级幸存），`null` 取消设置字段（RFC 7386）。
- `F18.conversation-diff`：a `conversation_settings_diff`仅更新指定字段； 顶级 `null` 或超出范围的值为 422，不会改变任何内容。
- `F18.misc-settings-merge`：`misc_settings_diff`深度合并嵌套对象，替换列表，删除`null`上的嵌套键，并将顶级`null`存储为`null`。
- `F18.patch-validation`空或仅包含未知键 PATCH 状态码是400，无效值是422 `Settings validation failed` 不回显提交的机密，错误的指针返回 422，且没有任何内容存储。
- `F18.active-profile-pointer` PATCH `active_profile` 应用 LLM `agent_settings.llm`，未知 `llm` `null` 只清除指针。
- `F18.agent-kind-switch`：从新的 ACP 基础切换 `agent_kind` 到 `acp` 重建（无 `llm`，无密钥）； 切换回来会提供新的 OpenHands 默认值。
- `F18.secret-put-list-get`: `PUT /api/settings/secrets` 答案 `{name, description}`列表显示了名称和描述，但从未显示过值 GET 返回名称的原始值 `text/plain`, and a second PUT 覆盖值和描述。
- `F18.secret-delete`：DELETE答案`{"deleted": true}`； 之后的 GET 和第二个 DELETE 是 404 `Secret not found`，并且列表省略了名称。
- `F18.secret-name-validation`：与`^[a-zA-Z][a-zA-Z0-9_]{0,63}$`不匹配的名称在GET、PUT和DELETE上为422（接受64个字符，不接受65个字符）； 没有`value`的PUT是422； 未知的有效名称是 404。
- `F18.encrypted-at-rest`：`settings.json` 和 `secrets.json` 保留 Fernet token，而不是原始值，模式为 `0600`。
- `F18.secret-scope-agent-profile`: `?agent_profile_id=` 将列表限制为智能体配置文件的 `secret_refs`（`[]` 不列出任何内容，`secret_refs` 不列出所有内容）； 未知 ID 为 404 `Agent profile not found`。
- `F18.sdk-remote-workspace`: the SDK's `RemoteWorkspace.get_secrets()` 返回 `LookupSecret`whose URLs 将值解析为存储的值，和 `get_llm()` 返回存储的模型和键。
- `F18.sdk-clone-repos`: 服务器机密 `github_token` 存储，SDK's `RemoteWorkspace.clone_repos()` 从 `GET /api/settings/secrets/github_token` 读取并克隆（一个本地的 git 远程，只能通过 token-携带的 URL 访问），一个缺少 token 机密的提供者（`gitlab_token`），匿名克隆，以及 `get_repos_context()` 的名称。
- `F18.ts-client`：TypeScript `SettingsClient` 读取模式，读取设置已脱敏、`plaintext` 和 `encrypted`，应用第二次读取显示的稀疏 `updateSettings`、更新插入、列出（也使用 `agentProfileId`）、读取文本并删除机密，并使用 `HttpError` 拒绝未知的机密 (404)、错误名称 (422) 和错误密钥 (401)。
- `F18.persist-restart`：设置（明文密钥、模型、对话设置）和机密在使用相同的密钥重新启动后读回不变。
- `F18.corrupted-files`：无法解析的`settings.json`，GET默默地返回默认值，PATCH是409而不触及文件； 无法解析的 `secrets.json` 列表为空，GET 名称为 404，PUT 和 DELETE 500； 恢复文件会恢复值。
- `F18.no-cipher`：没有任何密钥，`X-Expose-Secrets: encrypted`是503，`plaintext`仍然有效，两个文件都存储明文，并且机密路由在没有密钥的情况下打开。
- `F18.secret-empty-value`: a PUT 其值为空、空白或脱敏使用占位符时返回422，并且既不擦除现有值，也不留下可读但未列出的值机密已由#5682修复。
- `F18.dangling-pointers`：PATCH 拒绝使用 404 指定任何内容的 `active_agent_profile_id` 或 `active_meta_profile`，就像专用激活路由所做的那样，并且不存储任何内容（由 #5847 修复）。
- `F18.secret-scope-profile-errors`: `GET /api/settings/secrets?agent_profile_id=` 命名一个智能体不符合文件的 profile，或者到达时不符合智能体-profile store's 锁必须回答在其他地方智能体-profile 路由（400和503），而不是未处理的500。
- `F18.secret-name-contract`：已发布的机密路由的 OpenAPI 描述命名了无效的机密名称实际获得的状态，422（由 #5846 修复）。
- `F18.secret-key-rotation`：重启后使用新的加密密钥，旧密钥丢失（不在`OH_PREVIOUS_SECRET_KEYS`中），读取性能下降，写入被拒绝，而是销毁旧密钥下的值，旋转回旧密钥后恢复它们。
- `F18.secret-key-previous-keys`重新启动，使用新的密钥和旧的密钥 `OH_PREVIOUS_SECRET_KEYS` (支持的旋转) 保持每个值可读和可写，并使用新密钥重新加密两个文件，因此，即使没有旧密钥，重启后仍然可以读取它们。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /api/settings`（可选`X-Expose-Secrets: plaintext | encrypted`；
  `true` 是 `encrypted`) 的旧别名，`PATCH /api/settings` 具有以下任意一个
  `agent_settings_diff`, `conversation_settings_diff`, `misc_settings_diff`,
  `active_profile`, `active_agent_profile_id`, `active_meta_profile`;
  `GET /api/settings/agent-schema` 和 `GET /api/settings/conversation-schema`。
- REST：`GET /api/settings/secrets`（可选`agent_profile_id`），
  `PUT /api/settings/secrets` `{"name", "value", "description"?}`,
  `GET /api/settings/secrets/{name}`（原始`text/plain`），
  `DELETE /api/settings/secrets/{name}`.
- 邻居用作安排步骤和第二个视图，由其他家庭拥有：
  `POST/DELETE /api/profiles/{name}` 和 `GET /api/profiles`（LLM 配置文件），
  `POST/GET/DELETE /api/agent-profiles/{name}` 和
  `POST /api/agent-profiles/{id}/activate`（智能体个人资料），
  `POST /api/meta-profiles/{name}/activate`（元配置文件）和
  `GET /openapi.json`（服务器状态）。 MCP 子路线 `/api/settings/mcp/{settings_key}` 属于 MCP 设置系列； `/api/settings` 处于休眠状态时属于 deferred-init 系列 (F03)。
- SDK：`RemoteWorkspace.get_llm()`和`get_mcp_config()`已读取
  `GET /api/settings` 与 `X-Expose-Secrets: plaintext`；
  `RemoteWorkspace.get_secrets(names=None, agent_profile_id=None)`列出名称并返回`LookupSecret(url=<host>/api/settings/secrets/<name>)`，服务器或客户端稍后解析； `clone_repos(repos, target_dir)` 读
  `github_token`、`gitlab_token` 或 `bitbucket_token` 至
  `_get_secret_value`（404 上的 `GET /api/settings/secrets/{name}`、`None`）并在客户端计算机上运行 `git clone`，并且 `get_repos_context()` 描述克隆（`openhands-sdk/openhands/sdk/workspace/remote/base.py`、
  `openhands-sdk/openhands/sdk/workspace/repo.py`). 食谱
  `F18.sdk-remote-workspace` 和 `F18.sdk-clone-repos` 通过 `control-agent-server exec` 行使此车道。
- TypeScript客户端：`SettingsClient.getAgentSchema()`，
  `getConversationSchema()`, `getSettings({exposeSecrets})`,
  `updateSettings(request)`, `listSecrets({agentProfileId})`,
  `upsertSecret(request)`, `getSecret(name)` (`responseType: 'text'`),
  `deleteSecret(name)` (`clients/typescript/src/client/settings-client.ts`); 拒绝以`HttpError`（`isHttpError`、`status`、`detail`）拒绝。 方案 `F18.ts-client` 使用 `node` 在构建的包 (`clients/typescript/dist`) 上运行它们。 同班的`createMcpServer`，
  `patchMcpServer` 和 `deleteMcpServer` 调用 MCP 设置系列的路由 (F19)，其 LLM-配置文件方法调用 LLM 配置文件系列 (F20)。
- 配置：`OH_PERSISTENCE_DIR` 保存 `settings.json` 和 `secrets.json`（否则 `~/.openhands`； 启动运行使用`<run>/home/.openhands`）；
  `OH_SECRET_KEY` 是密码，否则是第一个会话密钥； 如果两者都没有，机密将以明文形式存储（`launch --no-auth --no-secret-key`）。
  `OH_SESSION_API_KEYS_*` 每条路线都有门。
- Agent Canvas：设置页面呈现来自两个模式和 PATCH 差异的表单； 机密页面列出、更新插入和删除（仅限上下文）。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

**批评家检查前提条件。**

如果可用的授权 OpenHands (`openhands/…`) 或兼容 OpenHands LLM-代理配置文件，则无论用于 REST 的代理配置文件是什么，都应使用它进行关键检查。 启用评论家并且
`verification.critic_api_key` 取消设置，`OpenHandsAgentSettings.build_critic()` 重新使用所选的 LLM 配置文件的密钥； 不需要单独的批评者密钥。 默认评论家端点是 `https://llm-proxy.app.all-hands.dev/vllm`。 必须使用该部署兼容的批评端点而不是假设凭据在默认端点上工作。 之后恢复之前的配置文件和验证设置。 可用性不是评分结果：报告实际的服务响应，仅当授权的先决条件不可用时才记录`blocked`。 不要将不相关的提供商的密钥发送给评论家服务。

前提条件：

- 全新运行（`launch --new`，默认标志），其持久化目录还没有 `settings.json`：首先不要运行 `llm preset`，`F18.get-defaults` 检查未更改的默认值。 不需要模型。 `jq`、`git`、`flock` 和
  `node` 在 `PATH` 上； TypeScript 客户端已构建 (`clients/typescript/dist`; `F18.ts-client` 在缺少 `npm ci && npm run build` 时使用它来构建它，这需要 npm 注册表）。
- 下面的块创建测试夹具目录，项目符号存储假值（`QA_F18_LLM_KEY` 代表 LLM 键，`QA_F18_SECRET` 代表命名的机密； 两者都导出，因此 `state grep --env-value` 可以搜索它们）和三个小型消费者程序：`sdk_probe.py` 驱动器 `RemoteWorkspace` 机密和 LLM (`F18.sdk-remote-workspace`)、`sdk_clone.py` 驱动器
  `RemoteWorkspace.clone_repos` (`F18.sdk-clone-repos`)，以及
  `ts_settings.mjs` 驱动 TypeScript `SettingsClient` (`F18.ts-client`)。
- 项目符号按顺序改变设置并恢复它们更改的内容。 已知的错误排在最后并且是独立的：每个错误都将其更改的内容放回 `EXIT` 陷阱中，因为子弹停在其 `# bug` 断言处。
  `F18.persist-restart`和`F18.secret-key-rotation`重新启动运行；
  `F18.no-cipher` 启动它自己的第二次运行 (`*-f18-nocipher`) 并停止它，因此它的 `--save` 证据位于该运行的 `evidence/` 目录中。

  ```sh
  F18="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f18"
  mkdir -p "$F18"
  export QA_F18_LLM_KEY=qa-f18-llm-key-5b1e7d
  export QA_F18_SECRET=qa-f18-secret-value-3d9a
  cat > "$F18/sdk_probe.py" <<'EOF'
  import os

  from openhands.sdk.workspace import RemoteWorkspace

  ws = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=os.environ["AGENT_SERVER_VERIFY_RUN"],
  )
  secrets = ws.get_secrets()
  token = secrets["QA_F18_TOKEN"]
  assert token.url == f"{ws.host}/api/settings/secrets/QA_F18_TOKEN", token.url
  assert token.description == "qa f18 token", token.description
  assert token.get_value() == os.environ["QA_F18_SECRET"], "LookupSecret value differs"
  assert set(ws.get_secrets(names=["QA_F18_TOKEN"])) == {"QA_F18_TOKEN"}
  llm = ws.get_llm()
  assert llm.model == "openai/qa-f18-model", llm.model
  assert llm.api_key is not None
  assert llm.api_key.get_secret_value() == os.environ["QA_F18_LLM_KEY"], "LLM key differs"
  print("QA_F18_SDK_OK", sorted(secrets))
  EOF
  cat > "$F18/sdk_clone.py" <<'EOF'
  import os
  from pathlib import Path

  from openhands.sdk.workspace import RemoteWorkspace

  target = Path(os.environ["QA_F18_CLONES"])
  ws = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=str(target),
  )
  assert ws._get_secret_value("github_token") == "qa-f18-gh-token"
  assert ws._get_secret_value("gitlab_token") is None
  result = ws.clone_repos(
      [
          "https://github.com/qa-owner/qa-gh-repo",
          {"url": "qa-owner/qa-gl-repo", "provider": "gitlab"},
      ],
      target_dir=target,
  )
  assert result.failed_repos == [], result.failed_repos
  assert result.success_count == 2, result.success_count
  for name in ("qa-gh-repo", "qa-gl-repo"):
      readme = target / name / "README.md"
      assert readme.read_text() == "qa f18 clone fixture\n", readme
  context = ws.get_repos_context(result.repo_mappings)
  assert "qa-gh-repo" in context and "qa-gl-repo" in context, context
  print("QA_F18_CLONE_OK", sorted(m.dir_name for m in result.repo_mappings.values()))
  EOF
  cat > "$F18/ts_settings.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const dist = (file) => pathToFileURL(resolve('clients/typescript/dist', file)).href;
  const { SettingsClient } = await import(dist('clients.js'));
  const { isHttpError } = await import(dist('index.js'));
  const host = process.env.AGENT_SERVER_URL;
  const client = new SettingsClient({ host, apiKey: process.env.SESSION_API_KEY });

  assert.equal((await client.getAgentSchema()).model_name, 'AgentSettings');
  const convSchema = await client.getConversationSchema();
  assert.equal(convSchema.model_name, 'ConversationSettings');
  assert.deepEqual(convSchema.sections.flatMap((s) => s.fields.map((f) => f.key)).sort(),
    ['confirmation_mode', 'max_iterations', 'security_analyzer']);

  assert.equal((await client.getSettings()).agent_settings.llm.api_key, '**********');
  const plain = await client.getSettings({ exposeSecrets: 'plaintext' });
  assert.equal(plain.agent_settings.llm.api_key, process.env.QA_F18_LLM_KEY);
  assert.equal(plain.agent_settings.llm.model, 'openai/qa-f18-model');
  assert.match((await client.getSettings({ exposeSecrets: 'encrypted' })).agent_settings.llm.api_key, /^gAAAAA/);

  const patched = await client.updateSettings({ agent_settings_diff: { llm: { temperature: 0.4 } } });
  assert.equal(patched.agent_settings.llm.temperature, 0.4);
  assert.equal(patched.agent_settings.llm.api_key, '**********');
  const reread = await client.getSettings({ exposeSecrets: 'plaintext' });
  assert.equal(reread.agent_settings.llm.temperature, 0.4);
  assert.equal(reread.agent_settings.llm.api_key, process.env.QA_F18_LLM_KEY);
  const unset = await client.updateSettings({ agent_settings_diff: { llm: { temperature: null } } });
  assert.equal(unset.agent_settings.llm.temperature ?? null, null);

  assert.deepEqual(await client.upsertSecret({ name: 'QA_F18_TS', value: 'qa-f18-ts-value', description: 'qa f18 ts' }),
    { name: 'QA_F18_TS', description: 'qa f18 ts' });
  const listed = await client.listSecrets();
  assert.deepEqual(listed.secrets.find((s) => s.name === 'QA_F18_TS'), { name: 'QA_F18_TS', description: 'qa f18 ts' });
  assert.ok(!JSON.stringify(listed).includes('qa-f18-ts-value'));
  assert.equal(await client.getSecret('QA_F18_TS'), 'qa-f18-ts-value');
  const scoped = await client.listSecrets({ agentProfileId: process.env.QA_F18_TS_PROFILE });
  assert.deepEqual(scoped.secrets.map((s) => s.name), ['QA_F18_TS']);
  assert.deepEqual(await client.deleteSecret('QA_F18_TS'), { deleted: true });
  await assert.rejects(client.getSecret('QA_F18_TS'),
    (err) => isHttpError(err) && err.status === 404 && err.detail === 'Secret not found');
  await assert.rejects(client.getSecret('1bad'), (err) => isHttpError(err) && err.status === 422);

  const stranger = new SettingsClient({ host, apiKey: 'qa-f18-wrong-key' });
  await assert.rejects(stranger.getSettings(),
    (err) => isHttpError(err) && err.status === 401 && err.detail === 'Unauthorized');
  stranger.close();
  client.close();
  console.log('QA_F18_TS_OK');
  JS
  ```

- **新的默认值 (`F18.get-defaults`)。**在写入设置之前先读取设置。
  ```sh
  control-agent-server api GET /api/settings --expect 200 --raw-out "$F18/settings-defaults.json" \
    --check agent_settings.agent_kind eq openhands --check agent_settings.llm.api_key missing \
    --check llm_api_key_is_set eq false --check active_profile missing --check active_agent_profile_id missing \
    --check active_meta_profile missing --check misc_settings len-eq 0 \
    --check conversation_settings.max_iterations eq 500 --save F18.get-defaults/get
  DEFAULT_MODEL=$(control-agent-server api GET /api/settings --field agent_settings.llm.model)
  test ! -e "$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  ```
  `DEFAULT_MODEL` 是 SDK 的默认模型，`settings.json` 未创建。
- **智能体设置模式（`F18.agent-schema`）。**阅读表格模式并将其字段键与设置文档进行比较。
  ```sh
  control-agent-server api GET /api/settings/agent-schema --expect 200 --raw-out "$F18/agent-schema.json" \
    --check model_name eq AgentSettings --check sections len-ge 5 --max-chars 300 --save F18.agent-schema/schema
  jq -e '[.sections[].variant] | (index("openhands") != null) and (index("acp") != null) and (index(null) != null)' "$F18/agent-schema.json"
  jq -e '[.sections[].fields[] | select(.secret == true) | .key] | (index("llm.api_key") != null) and (index("verification.critic_api_key") != null) and (index("llm.model") == null)' "$F18/agent-schema.json"
  jq -e --slurpfile s "$F18/settings-defaults.json" 'def haspath(p): if (p|length) == 1 then has(p[0]) else (.[p[0]] // {}) | haspath(p[1:]) end; [.sections[] | select(.variant != "acp") | .fields[].key | split(".") as $p | ($s[0].agent_settings | haspath($p))] | all' "$F18/agent-schema.json"
  ```
  章节 `variant` `null` （共享 `general`）， `openhands` (`llm`，
  `condenser`、`verification`、...) 和 `acp`； `llm.api_key` 和其他凭据被标记为 `secret`，`llm.model` 未被标记； 每个非 ACP 字段键（`llm.model`、`condenser.max_size`、...）都存在于默认值中
  `agent_settings`.
- **对话设置模式 (`F18.conversation-schema`).**将模式与 `F18.get-defaults` 中读取的默认值进行比较。
  ```sh
  control-agent-server api GET /api/settings/conversation-schema --expect 200 --raw-out "$F18/conversation-schema.json" \
    --check model_name eq ConversationSettings --save F18.conversation-schema/schema
  jq -e --slurpfile s "$F18/settings-defaults.json" '[.sections[].fields[] | .key as $k | .default == $s[0].conversation_settings[$k]] | (all and length == 3)' "$F18/conversation-schema.json"
  jq -e '[.sections[].fields[].key] | sort == ["confirmation_mode", "max_iterations", "security_analyzer"]' "$F18/conversation-schema.json"
  ```
  该模式确实有 `max_iterations` 和 `confirmation_mode`
  `security_analyzer`，每个默认值（`500`、`false`、`llm`）等于`conversation_settings`中的值。
- **需要密钥 (`F18.auth-required`)。**每条路线都没有钥匙、钥匙错误、有`X-Expose-Secrets: plaintext`但没有钥匙。
  ```sh
  control-agent-server api GET /api/settings --auth none --expect 401 --check detail eq Unauthorized --save F18.auth-required/settings-no-key
  control-agent-server api GET /api/settings --auth bad --header 'X-Expose-Secrets: plaintext' --expect 401 --save F18.auth-required/plaintext-wrong-key
  control-agent-server api GET /api/settings/agent-schema --auth none --expect 401
  control-agent-server api GET /api/settings/conversation-schema --auth none --expect 401
  control-agent-server api PATCH /api/settings --auth none --json '{"misc_settings_diff": {"qa_f18_noauth": 1}}' --expect 401
  control-agent-server api GET /api/settings/secrets --auth none --expect 401
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --auth bad --expect 401 --save F18.auth-required/secret-wrong-key
  control-agent-server api PUT /api/settings/secrets --auth none --json '{"name": "QA_F18_NOAUTH", "value": "qa-f18-noauth"}' --expect 401
  control-agent-server api DELETE /api/settings/secrets/QA_F18_TOKEN --auth none --expect 401
  control-agent-server api GET /api/settings --check misc_settings len-eq 0
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 0
  ```
  所有九个呼叫都是401 `{"detail": "Unauthorized"}`; 被拒绝的 PATCH 和 PUT 存储了 nothing。
- **设置LLM（`F18.patch-llm`）。** PATCH 模型和密钥，要求响应中提供明文，然后读回。
  ```sh
  control-agent-server api PATCH /api/settings --header 'X-Expose-Secrets: plaintext' \
    --json "{\"agent_settings_diff\": {\"llm\": {\"model\": \"openai/qa-f18-model\", \"api_key\": \"$QA_F18_LLM_KEY\"}}}" \
    --expect 200 --check agent_settings.llm.api_key eq '**********' --check agent_settings.llm.model eq openai/qa-f18-model \
    --check llm_api_key_is_set eq true --check . not-contains "$QA_F18_LLM_KEY" --save F18.patch-llm/patch
  control-agent-server api GET /api/settings --expect 200 --check agent_settings.llm.model eq openai/qa-f18-model \
    --check agent_settings.llm.api_key eq '**********' --check llm_api_key_is_set eq true --save F18.patch-llm/get
  test -f "$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  ```
  PATCH响应码为已脱敏，但请求的是纯文本。 GET 显示模型和`llm_api_key_is_set: true`，`settings.json`现在存在。
- **曝光模式 (`F18.expose-modes`).**阅读关键的四种方法。
  ```sh
  control-agent-server api GET /api/settings --check agent_settings.llm.api_key eq '**********' --save F18.expose-modes/redacted
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" --save F18.expose-modes/plaintext
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: encrypted' --check agent_settings.llm.api_key matches '^gAAAAA' \
    --check . not-contains "$QA_F18_LLM_KEY" --save F18.expose-modes/encrypted
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: true' --check agent_settings.llm.api_key matches '^gAAAAA' --save F18.expose-modes/legacy-true
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: qa-bogus' --expect 400 \
    --check detail contains 'Invalid X-Expose-Secrets header value' --save F18.expose-modes/bogus
  ```
  不带头信息 `**********`，`plaintext` 存储值，`encrypted`
  `true` a `gAAAAA...` Fernet token（CLI 将其打印为
  `<redacted:encrypted>`)，任何其他值 400。
- **发回 GET 返回的内容 (`F18.roundtrip`)。**加密的 token，然后是已脱敏占位符。
  ```sh
  TOKEN=$(control-agent-server api GET /api/settings --header 'X-Expose-Secrets: encrypted' --field agent_settings.llm.api_key --unsafe-unredacted)
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"api_key\": \"$TOKEN\"}}}" \
    --expect 200 --check llm_api_key_is_set eq true --save F18.roundtrip/encrypted-back
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY"
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"llm": {"api_key": "**********"}}}' \
    --expect 200 --check llm_api_key_is_set eq false --save F18.roundtrip/redacted-back
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key missing \
    --check agent_settings.llm.model eq openai/qa-f18-model --save F18.roundtrip/after-redacted
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"api_key\": \"$QA_F18_LLM_KEY\"}}}" \
    --expect 200 --check llm_api_key_is_set eq true
  ```
  服务器解密了提交的 token因此，明文仍返回原始密钥。 Posting `**********` 清空密钥 (`api_key`  null,
  `llm_api_key_is_set: false`) 当模型保持不变时； 最后一个 PATCH 恢复密钥。
- **稀疏智能体差异和未设置 (`F18.agent-diff-merge`)。**添加两个 LLM 字段，然后用 `null` 删除它们。
  ```sh
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"llm": {"temperature": 0.3, "base_url": "http://127.0.0.1:9/v1"}}}' \
    --expect 200 --check agent_settings.llm.temperature eq 0.3 --check agent_settings.llm.base_url eq http://127.0.0.1:9/v1 \
    --check agent_settings.llm.model eq openai/qa-f18-model --check llm_api_key_is_set eq true --save F18.agent-diff-merge/sparse
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.temperature eq 0.3 \
    --check agent_settings.llm.base_url eq http://127.0.0.1:9/v1 --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY"
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"llm": {"base_url": null, "temperature": null}}}' \
    --expect 200 --check agent_settings.llm.base_url missing --check agent_settings.llm.temperature missing \
    --check llm_api_key_is_set eq true --save F18.agent-diff-merge/unset
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" \
    --check agent_settings.llm.model eq openai/qa-f18-model --check agent_settings.llm.base_url missing
  ```
  稀疏差异保留 `model` 和键； `null`复位`base_url`和
  `temperature` 恢复为默认值 (`null`)。
- **对话设置(`F18.conversation-diff`)。**更改两个字段，然后
  try a top-level `null` and an invalid value.
  ```sh
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"max_iterations": 77, "confirmation_mode": true}}' \
    --expect 200 --check conversation_settings.max_iterations eq 77 --check conversation_settings.confirmation_mode eq true \
    --check conversation_settings.security_analyzer eq llm --save F18.conversation-diff/patch
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"confirmation_mode": null}}' \
    --expect 422 --check detail eq 'Settings validation failed' --save F18.conversation-diff/top-level-null
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"max_iterations": 0}}' --expect 422
  control-agent-server api GET /api/settings --check conversation_settings.max_iterations eq 77 \
    --check conversation_settings.confirmation_mode eq true --save F18.conversation-diff/get
  ```
  untouched `security_analyzer` keeps `llm` PATCHes 和 GET 都被拒绝了，状态码是 422，`77` 和 `true` 仍然显示（已恢复到 `F18.persist-restart`）。
- **不透明杂项设置 (`F18.misc-settings-merge`)。**合并两次，然后 null 整个密钥。
  ```sh
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18": {"theme": "dark", "keep": 1, "tags": ["a", "b"]}}}' \
    --expect 200 --check misc_settings.qa_f18.theme eq dark --check misc_settings.qa_f18.keep eq 1
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18": {"theme": "light", "tags": ["c"], "keep": null}}}' \
    --expect 200 --save F18.misc-settings-merge/merge
  control-agent-server api GET /api/settings --check misc_settings.qa_f18 eq '{"theme": "light", "tags": ["c"]}' --save F18.misc-settings-merge/get
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18": null}}' --expect 200 \
    --check misc_settings eq '{"qa_f18": null}' --save F18.misc-settings-merge/top-level-null
  control-agent-server api GET /api/settings --check misc_settings eq '{"qa_f18": null}'
  ```
  嵌套的 `theme` 被替换，列表 `["a", "b"]` becomes `["c"]`, the nested `null` removes `keep`. 顶级的 `null` 存储为 `null`客户端无法删除顶级节点 `misc_settings` key.
- **拒绝PATCH个机构(`F18.patch-validation`)。**空、仅有拼写错误、机密旁边的类型错误以及格式错误的指针。
  ```sh
  control-agent-server api PATCH /api/settings --json '{}' --expect 400 --check detail contains 'At least one of' --save F18.patch-validation/empty
  control-agent-server api PATCH /api/settings --json '{"qa_typo": 1}' --expect 400 --save F18.patch-validation/unknown-key
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"llm": {"temperature": "hot", "api_key": "qa-f18-leak-probe"}}}' \
    --expect 422 --check detail eq 'Settings validation failed' --check . not-contains qa-f18-leak-probe --save F18.patch-validation/bad-type
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": "qa-not-an-object"}' --expect 422
  control-agent-server api PATCH /api/settings --json '{"active_profile": "bad name!"}' --expect 422 --save F18.patch-validation/bad-profile-name
  control-agent-server api PATCH /api/settings --json '{"active_agent_profile_id": "not-a-uuid"}' --expect 422
  control-agent-server api PATCH /api/settings --json '{"active_meta_profile": "bad/name"}' --expect 422
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" \
    --check agent_settings.llm.temperature missing --check active_profile missing --check active_agent_profile_id missing --check active_meta_profile missing
  ```
  `{}` 和未知密钥体为 400 `At least one of ...`； 错误类型是 422，具有一般详细信息，并且没有发布密钥的痕迹； 强制执行指针模式（422）。 最终的GET显示没有任何改变。
- **活动 LLM 配置文件指针 (`F18.active-profile-pointer`)。**保存 LLM 配置文件（排列），将设置指向该配置文件，然后指向缺失的配置文件，然后清除。
  ```sh
  control-agent-server api POST /api/profiles/qa-f18-llm --json '{"llm": {"model": "openai/qa-f18-profile-model", "api_key": "qa-f18-profile-key-91c2"}}' --expect 201
  control-agent-server api PATCH /api/settings --json '{"active_profile": "qa-f18-llm"}' --expect 200 --check active_profile eq qa-f18-llm \
    --check agent_settings.llm.model eq openai/qa-f18-profile-model --check llm_api_key_is_set eq true --save F18.active-profile-pointer/activate
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq qa-f18-profile-key-91c2
  control-agent-server api GET /api/profiles --check active_profile eq qa-f18-llm --save F18.active-profile-pointer/profiles
  control-agent-server api PATCH /api/settings --json '{"active_profile": "qa-f18-nope"}' --expect 404 \
    --check detail eq "Profile 'qa-f18-nope' not found" --save F18.active-profile-pointer/unknown
  control-agent-server api GET /api/settings --check active_profile eq qa-f18-llm
  control-agent-server api PATCH /api/settings --json '{"active_profile": "qa-f18-llm", "agent_settings_diff": {"llm": {"model": "openai/qa-f18-explicit"}}}' \
    --expect 200 --check agent_settings.llm.model eq openai/qa-f18-explicit
  control-agent-server api PATCH /api/settings --json '{"active_profile": null}' --expect 200 --check active_profile missing \
    --check agent_settings.llm.model eq openai/qa-f18-explicit --save F18.active-profile-pointer/clear
  control-agent-server api GET /api/settings --check active_profile missing --check agent_settings.llm.model eq openai/qa-f18-explicit
  control-agent-server api GET /api/profiles --check active_profile missing --check profiles len-eq 1
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"model\": \"openai/qa-f18-model\", \"api_key\": \"$QA_F18_LLM_KEY\"}}}" --expect 200
  control-agent-server api DELETE /api/profiles/qa-f18-llm --expect 200
  control-agent-server api GET /api/profiles --check active_profile missing --check profiles len-eq 0
  ```
  指针复制了模型和密钥 `agent_settings.llm` 和 `GET /api/profiles`  未知名称为404，留下指针。 明确的 `llm` 在相同的地方 PATCH wins; `null` 清空指针（两者） GETs 同意，该档案本身仍然存在，并且保持了  LLM. 的 LLM 并且用户列表和用户档案恢复。
- **智能体种类开关 (`F18.agent-kind-switch`).**前往 ACP 并返回。

  需要：`F18.get-defaults`
  ```sh
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "acp", "acp_server": "claude-code"}}' \
    --expect 200 --check agent_settings.agent_kind eq acp --check agent_settings.acp_server eq claude-code \
    --check agent_settings.llm missing --check llm_api_key_is_set eq false --save F18.agent-kind-switch/to-acp
  control-agent-server api GET /api/settings --check agent_settings.agent_kind eq acp --check conversation_settings.max_iterations eq 77
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "openhands"}}' --expect 200 \
    --check agent_settings.agent_kind eq openhands --check agent_settings.llm.model eq "$DEFAULT_MODEL" \
    --check llm_api_key_is_set eq false --save F18.agent-kind-switch/back
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key missing
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"model\": \"openai/qa-f18-model\", \"api_key\": \"$QA_F18_LLM_KEY\"}}}" \
    --expect 200 --check llm_api_key_is_set eq true
  ```
  ACP 设置没有 `llm`，所以键就没了； 从头开始，从 OpenHands 的默认值（默认模型，没有密钥）开始，而不是从 LLM 的旧值。 会话设置未更改。 第四个 PATCH 修复了 LLM。
- **更新插入、列出并读取机密 (`F18.secret-put-list-get`)。**创建、列出、读取、覆盖、恢复。
  ```sh
  control-agent-server api GET /api/settings/secrets --expect 200 --check secrets len-eq 0
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" \
    --expect 200 --check name eq QA_F18_TOKEN --check description eq 'qa f18 token' --check value missing --save F18.secret-put-list-get/put
  control-agent-server api GET /api/settings/secrets --expect 200 --check secrets len-eq 1 --check secrets.0.name eq QA_F18_TOKEN \
    --check secrets.0.description eq 'qa f18 token' --check . not-contains "$QA_F18_SECRET" --save F18.secret-put-list-get/list
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" \
    --check-header content-type contains text/plain --save F18.secret-put-list-get/get
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_TOKEN", "value": "qa-f18-secret-v2"}' --expect 200 --check description missing
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq qa-f18-secret-v2 --save F18.secret-put-list-get/get-overwritten
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1 --check secrets.0.description missing
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" --expect 200
  ```
  PUT 返回 200 `{name, description}` 和没有值。 列表仅包含名称和描述。 GET 按名称回答 `text/plain` 原始值。 第二 PUT 替换值，并且由于没有描述，它会清除。 最后 PUT 恢复了所有子弹。
- **删除机密 (`F18.secret-delete`)。**创建一个一次性的机密，删除它两次。
  ```sh
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_DOOMED", "value": "qa-f18-doomed-value"}' --expect 200
  control-agent-server api DELETE /api/settings/secrets/QA_F18_DOOMED --expect 200 --check deleted eq true --save F18.secret-delete/delete
  control-agent-server api GET /api/settings/secrets/QA_F18_DOOMED --expect 404 --check detail eq 'Secret not found' --save F18.secret-delete/get-after
  control-agent-server api DELETE /api/settings/secrets/QA_F18_DOOMED --expect 404 --check detail eq 'Secret not found' --save F18.secret-delete/delete-again
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1 --check secrets not-contains QA_F18_DOOMED
  ```
  `{"deleted": true}`，然后 404 `Secret not found` 读取和重复删除； 仅列出`QA_F18_TOKEN`。
- **机密名称 (`F18.secret-name-validation`).**每条路线上的名称无效、值缺失、有效名称未知。
  ```sh
  control-agent-server api GET /api/settings/secrets/1bad --expect 422 --check detail contains 'Invalid secret name format' --save F18.secret-name-validation/get
  control-agent-server api GET /api/settings/secrets/bad-name --expect 422
  control-agent-server api DELETE /api/settings/secrets/bad-name --expect 422 --save F18.secret-name-validation/delete
  control-agent-server api PUT /api/settings/secrets --json '{"name": "1bad", "value": "qa-f18-x"}' --expect 422 --save F18.secret-name-validation/put
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"A$(printf 'a%.0s' $(seq 64))\", \"value\": \"qa-f18-x\"}" --expect 422
  LONG64="A$(printf 'a%.0s' $(seq 63))"
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"$LONG64\", \"value\": \"qa-f18-x\"}" --expect 200 --check name eq "$LONG64"
  control-agent-server api GET "/api/settings/secrets/$LONG64" --expect 200 --check . eq qa-f18-x
  control-agent-server api DELETE "/api/settings/secrets/$LONG64" --expect 200 --check deleted eq true
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_NOVALUE"}' --expect 422 --save F18.secret-name-validation/no-value
  control-agent-server api GET /api/settings/secrets/QA_F18_UNKNOWN --expect 404 --check detail eq 'Secret not found'
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1
  ```
  以数字开头的名称，包含 `-` 长度超过64个字符的请求将返回422 `Invalid secret name format ...` (the) 文档字符串说400； 代码显示返回 422，而存储的名称为 64 个字符。 身体没有
  `value`是请求-验证422； 未知的有效名称是 404。 仅
  `QA_F18_TOKEN` 仍然存在。
- **在 REST (`F18.encrypted-at-rest`) 处加密。**检查两个文件。
  ```sh
  control-agent-server state cat home/.openhands/settings.json --check agent_settings.llm.api_key matches '^gAAAAA' \
    --check schema_version exists --not-contains "$QA_F18_LLM_KEY" --mode 600
  control-agent-server state cat home/.openhands/secrets.json --check custom_secrets.QA_F18_TOKEN.secret matches '^gAAAAA' \
    --check custom_secrets.QA_F18_TOKEN.description eq 'qa f18 token' --not-contains "$QA_F18_SECRET" --mode 600
  control-agent-server state grep openai/qa-f18-model --glob 'home/**/*'
  control-agent-server state grep QA_F18_TOKEN --glob 'home/**/*'
  control-agent-server state grep --env-value QA_F18_LLM_KEY --glob 'home/**/*' --expect-none
  control-agent-server state grep --env-value QA_F18_SECRET --glob 'home/**/*' --expect-none
  ```
  两者机密字段 `gAAAAA...`  token 并且两个文件都是 `0600`. 通配符确实匹配了这两个文件（模型和数据） 机密名字以明文存储并可找到，但运行中的任何值都未出现
  `HOME`.
- **机密范围受智能体配置文件 (`F18.secret-scope-agent-profile`) 限制。**添加第二个机密和两个智能体配置文件（排列）具有不同的
  `secret_refs`.
  ```sh
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_OTHER", "value": "qa-f18-other-value"}' --expect 200
  control-agent-server api POST /api/agent-profiles/qa-f18-scoped --json '{"llm_profile_ref": "qa-f18-llm", "secret_refs": ["QA_F18_TOKEN"]}' --expect 201
  control-agent-server api POST /api/agent-profiles/qa-f18-none --json '{"llm_profile_ref": "qa-f18-llm", "secret_refs": []}' --expect 201
  control-agent-server api POST /api/agent-profiles/qa-f18-all --json '{"llm_profile_ref": "qa-f18-llm"}' --expect 201
  SCOPED=$(control-agent-server api GET /api/agent-profiles/qa-f18-scoped --field profile.id)
  NONE=$(control-agent-server api GET /api/agent-profiles/qa-f18-none --field profile.id)
  ALL=$(control-agent-server api GET /api/agent-profiles/qa-f18-all --check profile.secret_refs missing --field profile.id)
  control-agent-server api GET /api/settings/secrets --query "agent_profile_id=$SCOPED" --expect 200 --check secrets len-eq 1 \
    --check secrets.0.name eq QA_F18_TOKEN --save F18.secret-scope-agent-profile/scoped
  control-agent-server api GET /api/settings/secrets --query "agent_profile_id=$NONE" --expect 200 --check secrets len-eq 0 --save F18.secret-scope-agent-profile/none
  control-agent-server api GET /api/settings/secrets --query "agent_profile_id=$ALL" --expect 200 --check secrets len-eq 2 --save F18.secret-scope-agent-profile/all
  control-agent-server api GET /api/settings/secrets --expect 200 --check secrets len-eq 2
  control-agent-server api GET /api/settings/secrets --query agent_profile_id=00000000-0000-4000-8000-0000000000f1 --expect 404 \
    --check detail eq 'Agent profile not found' --save F18.secret-scope-agent-profile/unknown
  control-agent-server api DELETE /api/agent-profiles/qa-f18-scoped --expect 200
  control-agent-server api DELETE /api/agent-profiles/qa-f18-none --expect 200
  control-agent-server api DELETE /api/agent-profiles/qa-f18-all --expect 200
  control-agent-server api DELETE /api/settings/secrets/QA_F18_OTHER --expect 200
  control-agent-server api GET /api/settings --check active_agent_profile_id missing
  ```
  `secret_refs: ["QA_F18_TOKEN"]`仅列出机密，`[]`列出None，没有`secret_refs`的配置文件（null，“全部”）并且没有过滤器都列出两个； 未知 ID 为 404。 配置文件和第二个机密被删除，并且没有智能体配置文件变为活动状态。
- **SDK 消费者 (`F18.sdk-remote-workspace`).** `RemoteWorkspace` 将机密列为 `LookupSecret`，解析其中之一，并根据设置构建 LLM。
  ```sh
  control-agent-server exec --env QA_F18_SECRET="$QA_F18_SECRET" --env QA_F18_LLM_KEY="$QA_F18_LLM_KEY" --env OPENHANDS_SUPPRESS_BANNER=1 \
    --expect-output QA_F18_SDK_OK --save F18.sdk-remote-workspace/probe -- .venv/bin/python "$F18/sdk_probe.py"
  ```
  该程序打印 `QA_F18_SDK_OK ['QA_F18_TOKEN']`: the `LookupSecret`  URL 是 `<server>/api/settings/secrets/QA_F18_TOKEN`, 它解决了  HTTP 到存储的值上，和 `get_llm()` 返回 `openai/qa-f18-model` 使用存储的密钥（读取时） `X-Expose-Secrets: plaintext`).
- **SDK 克隆与存储的 token (`F18.sdk-clone-repos`).**翻译：“GitHub”和“GitLab”这里是两个本地裸存储库。 私有 git 配置（`GIT_CONFIG_GLOBAL`，仅传递给程序）重写
  `https://qa-f18-gh-token@github.com/` 和匿名者
  `https://gitlab.com/`，因此只有当 URL 携带服务器存储的 token 时，GitHub 克隆才会成功，而 GitLab 克隆只有在携带 None 时才成功。 存储`github_token`（排列），运行程序，删除它。
  ```sh
  G="$F18/git"
  rm -rf "$G" "$F18/clones"
  mkdir -p "$G/src"
  git -C "$G/src" init -q -b main
  printf 'qa f18 clone fixture\n' > "$G/src/README.md"
  git -C "$G/src" add README.md
  git -C "$G/src" -c user.name=qa-f18 -c user.email=qa-f18@example.invalid commit -q -m 'qa f18 clone fixture'
  git clone -q --bare "$G/src" "$G/gh/qa-owner/qa-gh-repo"
  git clone -q --bare "$G/src" "$G/gl/qa-owner/qa-gl-repo.git"
  printf '[url "file://%s/gh/"]\n\tinsteadOf = https://qa-f18-gh-token@github.com/\n[url "file://%s/gl/"]\n\tinsteadOf = https://gitlab.com/\n' "$G" "$G" > "$F18/gitconfig"
  control-agent-server api GET /api/settings/secrets --check secrets not-contains github_token --check secrets not-contains gitlab_token
  control-agent-server api PUT /api/settings/secrets --json '{"name": "github_token", "value": "qa-f18-gh-token"}' --expect 200
  control-agent-server exec --env GIT_CONFIG_GLOBAL="$F18/gitconfig" --env GIT_CONFIG_NOSYSTEM=1 --env GIT_TERMINAL_PROMPT=0 \
    --env QA_F18_CLONES="$F18/clones" --env OPENHANDS_SUPPRESS_BANNER=1 --timeout 120 \
    --expect-output QA_F18_CLONE_OK --save F18.sdk-clone-repos/program -- .venv/bin/python "$F18/sdk_clone.py"
  test "$(git -C "$F18/clones/qa-gl-repo" log -1 --format=%s)" = 'qa f18 clone fixture'
  control-agent-server api DELETE /api/settings/secrets/github_token --expect 200
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1 --check secrets.0.name eq QA_F18_TOKEN
  ```
  程序打印`QA_F18_CLONE_OK ['qa-gh-repo', 'qa-gl-repo']`：
  `_get_secret_value` 返回存储的 `github_token` 和 `None` 缺少的 `gitlab_token`两个克隆成功进入以仓库命名的目录中（短） `owner/repo` form with `provider: gitlab` gets
  `.git` 附加），`get_repos_context()` 命名两者。 之后机密又消失了。
- **TypeScript 客户端 (`F18.ts-client`).**保存范围的智能体配置文件
  `QA_F18_TS`（排列），运行`SettingsClient`程序，然后读取服务器自己的视图。
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server api POST /api/agent-profiles/qa-f18-ts --json '{"llm_profile_ref": "qa-f18-llm", "secret_refs": ["QA_F18_TS"]}' --expect 201
  TSPROF=$(control-agent-server api GET /api/agent-profiles/qa-f18-ts --field profile.id)
  control-agent-server exec --env QA_F18_LLM_KEY="$QA_F18_LLM_KEY" --env QA_F18_TS_PROFILE="$TSPROF" --timeout 120 \
    --expect-output QA_F18_TS_OK --save F18.ts-client/program -- node "$F18/ts_settings.mjs"
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1 --check secrets.0.name eq QA_F18_TOKEN --save F18.ts-client/secrets-after
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.temperature missing \
    --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" --save F18.ts-client/settings-after
  control-agent-server api DELETE /api/agent-profiles/qa-f18-ts --expect 200
  control-agent-server api GET /api/settings --check active_agent_profile_id missing
  ```
  该程序打印 `QA_F18_TS_OK`两者模式 load `getSettings()` 返回 `**********`, `plaintext` 存储的密钥和 `encrypted` a
  `gAAAAA...` token; `updateSettings` 用新的答案回答已脱敏
  `temperature`，明文读取将其显示在未触及的键旁边，并且
  `null` 取消设置； 通过 `upsertSecret` 的机密往返，
  `listSecrets`（仅限名称和描述，并且仅限 `QA_F18_TS`
  `agentProfileId`)、`getSecret`（原始文本）和`deleteSecret`； 然后
  `getSecret` 用 `HttpError` 404 `Secret not found` 拒绝，用 422 拒绝一个坏名字，用 401 `Unauthorized` 拒绝客户端持有错误的密钥。 之后服务器仅列出`QA_F18_TOKEN`，`temperature`被取消设置并且密钥不变。
- **持久化重新启动 (`F18.persist-restart`)。**使用相同的密钥重新启动，读回所有内容，然后恢复对话设置。
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check agent_settings.llm.model eq openai/qa-f18-model --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" \
    --check conversation_settings.max_iterations eq 77 --check conversation_settings.confirmation_mode eq true \
    --check misc_settings eq '{"qa_f18": null}' --save F18.persist-restart/settings
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.persist-restart/secret
  control-agent-server api GET /api/settings/secrets --check secrets len-eq 1 --check secrets.0.description eq 'qa f18 token'
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"max_iterations": 500, "confirmation_mode": false}}' \
    --expect 200 --check conversation_settings.max_iterations eq 500 --check conversation_settings.confirmation_mode eq false
  ```
  重启前写入的所有值读取回来时不变。
- **损坏的文件 (`F18.corrupted-files`)。**备份这两个文件，用损坏的 JSON 覆盖它们，驱动每条路线，恢复。

  需要：`F18.get-defaults`
  ```sh
  P="$AGENT_SERVER_VERIFY_RUN/home/.openhands"
  cp "$P/settings.json" "$F18/settings.json.bak"
  cp "$P/secrets.json" "$F18/secrets.json.bak"
  cat > "$P/settings.json" <<'EOF'
  {"qa-f18-corrupt":
  EOF
  cat > "$P/secrets.json" <<'EOF'
  {"custom_secrets": [qa-f18-corrupt
  EOF
  control-agent-server api GET /api/settings --expect 200 --check llm_api_key_is_set eq false \
    --check agent_settings.llm.model eq "$DEFAULT_MODEL" --save F18.corrupted-files/get-settings
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18_probe": 1}}' --expect 409 \
    --check detail contains 'Settings file is corrupted or encrypted with a different key' --save F18.corrupted-files/patch
  control-agent-server state cat home/.openhands/settings.json --contains qa-f18-corrupt
  control-agent-server api GET /api/settings/secrets --expect 200 --check secrets len-eq 0 --save F18.corrupted-files/list-secrets
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 404
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_PROBE", "value": "qa-f18-probe"}' --expect 500 \
    --check exception contains 'Secrets file is corrupted or encrypted with a different key' --save F18.corrupted-files/put-secret
  control-agent-server api DELETE /api/settings/secrets/QA_F18_TOKEN --expect 500 --save F18.corrupted-files/delete-secret
  control-agent-server state cat home/.openhands/secrets.json --contains qa-f18-corrupt
  cp "$F18/settings.json.bak" "$P/settings.json"
  cp "$F18/secrets.json.bak" "$P/secrets.json"
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY"
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.corrupted-files/restored
  ```
  一个断开的 `settings.json` 读取为默认值 (200，无错误)，而 PATCH 则拒绝并返回 409 而不是覆盖它。 一个 `secrets.json` 为空，并隐藏了所有值（404）。 PUT 和 DELETE 回拒绝，状态码为 500，原因见 `exception`。 两份文件都没有被修改，恢复它们不会重启。
- **无密码 (`F18.no-cipher`)。**第二次运行没有 `OH_SECRET_KEY` 和会话密钥 (`launch --no-auth --no-secret-key`)，在项目符号结束时停止。
  ```sh
  NOCIPHER=$(control-agent-server launch --new --no-auth --no-secret-key --name f18-nocipher --print-run)
  trap 'control-agent-server stop --run "$NOCIPHER" >/dev/null' EXIT
  control-agent-server api PATCH /api/settings --run "$NOCIPHER" --json '{"agent_settings_diff": {"llm": {"api_key": "qa-f18-nocipher-key"}}}' \
    --expect 200 --check llm_api_key_is_set eq true
  control-agent-server api PUT /api/settings/secrets --run "$NOCIPHER" --json '{"name": "QA_F18_NOCIPHER", "value": "qa-f18-nocipher-secret"}' --expect 200
  control-agent-server api GET /api/settings --run "$NOCIPHER" --header 'X-Expose-Secrets: encrypted' --expect 503 \
    --check exception contains 'OH_SECRET_KEY is not configured' --save F18.no-cipher/encrypted
  control-agent-server api GET /api/settings --run "$NOCIPHER" --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check agent_settings.llm.api_key eq qa-f18-nocipher-key --save F18.no-cipher/plaintext
  control-agent-server api GET /api/settings/secrets/QA_F18_NOCIPHER --run "$NOCIPHER" --auth none --expect 200 \
    --check . eq qa-f18-nocipher-secret --save F18.no-cipher/secret-without-key
  control-agent-server state cat home/.openhands/settings.json --run "$NOCIPHER" --check agent_settings.llm.api_key eq qa-f18-nocipher-key --mode 600
  control-agent-server state cat home/.openhands/secrets.json --run "$NOCIPHER" \
    --check custom_secrets.QA_F18_NOCIPHER.secret eq qa-f18-nocipher-secret --mode 600
  ```
  `encrypted` 是 503（`detail` 重写为 `Internal Server Error`，`exception` 中的原因），`plaintext` 仍然有效，两个文件都保存原始值（仍然是 `0600`； 服务器记录 `Saving ... in PLAINTEXT (no cipher configured)`），并且没有会话密钥，任何人都可以读取机密的值。
- **占位符机密值 (`F18.secret-empty-value`).** PUT 现有机密上的脱敏占位符，这是仅编辑描述的表单发回的内容。
  需要：`F18.secret-put-list-get`
  ```sh
  restore_token() {
    control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" --expect 200 >/dev/null
  }
  trap 'restore_token || true' EXIT
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET"
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_TOKEN", "value": "**********", "description": "qa f18 edited"}' \
    --expect 422 --check detail eq 'Secret value must not be empty or redacted' --save F18.secret-empty-value/put-placeholder
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.secret-empty-value/get-after-placeholder
  control-agent-server api GET /api/settings/secrets --check secrets contains QA_F18_TOKEN --check . not-contains 'qa f18 edited'
  ```
  读回的值在之前 PUT (控制) 占位符 PUT 被拒绝，状态码为 422 `Secret value must not be empty or redacted` (5682)，存储的值和描述未受影响。 在#5682之前，它返回了200，并默默地擦除了值（`CustomSecret`'s 验证器 turns
  `**********` 和 `""` 进入 `null`)，留下列出的机密，其读取为
  404. 如果 PUT 成功，陷阱会将机密放回去。
- **空机密值 (`F18.secret-empty-value`)。** PUT 一个新的机密，其值为空字符串，然后是一个仅包含空格的字符串。
  需要：`F18.secret-put-list-get`
  ```sh
  trap 'control-agent-server api DELETE /api/settings/secrets/QA_F18_EMPTY --expect 200,404 >/dev/null || true' EXIT
  control-agent-server api GET /api/settings/secrets --check secrets contains QA_F18_TOKEN --check secrets not-contains QA_F18_EMPTY
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET"
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_EMPTY", "value": ""}' \
    --expect 422 --check detail eq 'Secret value must not be empty or redacted' --save F18.secret-empty-value/put-empty
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_EMPTY", "value": "   "}' --expect 422
  control-agent-server api GET /api/settings/secrets --check secrets not-contains QA_F18_EMPTY --save F18.secret-empty-value/list-empty
  control-agent-server api GET /api/settings/secrets/QA_F18_EMPTY --expect 404
  ```
  一个机密可读（控制：`QA_F18_TOKEN`）。 以空值或空白值请求时，会返回状态码422，并且没有任何东西留下：名称不在列表中，读取请求返回状态码404。 在#5682之前，PUT返回了200，并列出了一个不可读的`QA_F18_EMPTY`。 该陷阱在 PUT 成功的情况下会删除它。
- **悬空智能体-轮廓指针 (`F18.dangling-pointers`)。**激活路由以及 LLM 配置文件名称的 PATCH 本身会拒绝不存在的目标； PATCH 和 `active_agent_profile_id` 没有提及任何名称。
  ```sh
  clear_pointers() {
    control-agent-server api PATCH /api/settings --json '{"active_agent_profile_id": null, "active_meta_profile": null}' --expect 200 >/dev/null
  }
  trap 'clear_pointers || true' EXIT
  control-agent-server api POST /api/agent-profiles/00000000-0000-4000-8000-0000000000f1/activate --expect 404 \
    --check detail contains 'not found' --save F18.dangling-pointers/activate-agent-profile
  control-agent-server api PATCH /api/settings --json '{"active_profile": "qa-f18-nope"}' --expect 404 --check detail eq "Profile 'qa-f18-nope' not found"
  control-agent-server api PATCH /api/settings --json '{"active_agent_profile_id": "00000000-0000-4000-8000-0000000000f1"}' \
    --expect 404 --check detail eq "Agent profile with id '00000000-0000-4000-8000-0000000000f1' not found" --save F18.dangling-pointers/agent-profile-id
  ```
  `POST /api/agent-profiles/{id}/activate` 回答 404 `智能体带有 id 的个人资料
  ... not found`, and PATCH refuses an unknown `active_profile` with 404.
  PATCH 以相同的方式拒绝未知的智能体配置文件 ID（404，与激活路由相同的详细信息）并且不存储任何内容； 在 #5847 之前，它回答 200 并存储指针，这也抑制了惰性默认配置文件种子。 如果 PATCH 成功，陷阱将清除指针。
- **悬空元配置文件指针 (`F18.dangling-pointers`)。**与`active_meta_profile`相同。
  ```sh
  clear_pointers() {
    control-agent-server api PATCH /api/settings --json '{"active_agent_profile_id": null, "active_meta_profile": null}' --expect 200 >/dev/null
  }
  trap 'clear_pointers || true' EXIT
  control-agent-server api POST /api/meta-profiles/qa-f18-no-router/activate --expect 404 \
    --check detail eq "Meta-profile 'qa-f18-no-router' not found" --save F18.dangling-pointers/activate-meta-profile
  control-agent-server api GET /api/settings --check active_meta_profile missing --check agent_settings.enable_classify_and_switch_llm_tool eq false
  control-agent-server api PATCH /api/settings --json '{"active_meta_profile": "qa-f18-no-router"}' --expect 404 \
    --check detail eq "Meta-profile 'qa-f18-no-router' not found" --save F18.dangling-pointers/meta-profile
  control-agent-server api GET /api/settings --check active_meta_profile missing --check agent_settings.enable_classify_and_switch_llm_tool eq false
  ```
  激活路由和PATCH都返回404，切换工具仍然关闭。 在 #5847 之前，PATCH 回答了 200，并存储了指针，然后开启
  `enable_classify_and_switch_llm_tool` 后面没有元配置文件。 如果 PATCH 成功，陷阱将清除指针。
- **智能体配置文件不再加载 (`F18.secret-scope-profile-errors`)。**保存范围为 `QA_F18_TOKEN`（排列）的智能体配置文件，破坏其文件，使其不再验证（`secret_refs` 为字符串而不是列表），然后列出其 id 范围的机密。
  需要：`F18.secret-put-list-get`
  ```sh
  AP="$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles"
  trap 'rm -f "$AP/qa-f18-broken.json" || true' EXIT
  control-agent-server api POST /api/agent-profiles/qa-f18-broken --json '{"llm_profile_ref": "qa-f18-llm", "secret_refs": ["QA_F18_TOKEN"]}' --expect 201
  BROKEN=$(control-agent-server api GET /api/agent-profiles/qa-f18-broken --field profile.id)
  control-agent-server api GET /api/settings/secrets --query "agent_profile_id=$BROKEN" --expect 200 --check secrets len-eq 1
  jq '.secret_refs = "QA_F18_TOKEN"' "$AP/qa-f18-broken.json" > "$F18/qa-f18-broken.json"
  cp "$F18/qa-f18-broken.json" "$AP/qa-f18-broken.json"
  control-agent-server api GET /api/agent-profiles/qa-f18-broken --expect 400 \
    --check detail contains 'Failed to load profile' --save F18.secret-scope-profile-errors/agent-profile-route
  control-agent-server api GET /api/settings/secrets --query "agent_profile_id=$BROKEN" --expect 400 \
    --check detail contains 'Failed to load profile' --save F18.secret-scope-profile-errors/unloadable
  ```
  在有效期内，范围工作（一个机密）。 智能体-profile 路由报告断开的文件为 400 `Failed to load profile`
  ...`. The scoped list answers the same 400 with the load error in
  `detail`: `list_secrets` 读取 `store_errors()` 内的配置文件，就像智能体-配置文件路由一样。 该陷阱会删除配置文件。
- **智能体-profile store busy (`F18.secret-scope-profile-errors`).** 另一个进程（这里 `flock`, 作为同一服务器上的第二个服务器代替持久化目录）包含智能体-profile store's 锁持续了75秒。 服务器自身的 30 秒锁超时正在测试中，所以圆点会等待它两次，然后等待锁即将发布。
  ```sh
  AP="$AGENT_SERVER_VERIFY_RUN/home/.openhands/agent-profiles"
  HELD="$F18/agent-profiles-lock-held"
  rm -f "$HELD"
  flock -x "$AP/.agent-profiles.lock" sh -c "touch '$HELD'; sleep 75" >/dev/null 2>&1 &
  LOCKER=$!
  trap 'wait "$LOCKER" || true' EXIT
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  control-agent-server api GET /api/agent-profiles/qa-f18-busy --timeout 60 --expect 503 \
    --check exception eq '503: Profile store is busy. Please retry.' --save F18.secret-scope-profile-errors/agent-profile-busy
  control-agent-server api GET /api/settings/secrets --query agent_profile_id=00000000-0000-4000-8000-0000000000f1 --timeout 60 \
    --expect 503 --check exception eq '503: Profile store is busy. Please retry.' --save F18.secret-scope-profile-errors/secrets-busy
  ```
  30秒后，智能体-profile路由返回503 `Profile store is busy. Please retry.`，scoped 机密列表在相同等待时间后也返回相同的503。 陷阱直到`flock`松手。
- **无效名称的记录状态 (`F18.secret-name-contract`)。**阅读已发布的 OpenAPI 描述所承诺的无效机密名称的状态，然后发送一个。
  ```sh
  control-agent-server api GET /openapi.json --expect 200 --quiet --raw-out "$F18/openapi.json"
  CLAIMED=$(jq -r '.paths["/api/settings/secrets/{name}"].get.description // ""' "$F18/openapi.json" | sed -n 's/.* \([0-9][0-9][0-9]\) if name format is invalid.*/\1/p')
  control-agent-server api GET /api/settings/secrets/1bad --expect "${CLAIMED:-422}" --save F18.secret-name-contract/invalid-name
  ```
  预期：记录的情况与实际情况相符。 的描述
  `GET` 和 `DELETE /api/settings/secrets/{name}` 说 `422 if name format is invalid`（`PUT /api/settings/secrets` 说 `422 if the name or value is invalid`），每个人都回答 422（`F18.secret-name-validation`），因此从 OpenAPI 文档生成的客户端得到了正确的承诺。
- **密钥丢失 (`F18.secret-key-rotation`)。**存储一个机密和一个LLM键； 轮换密钥而不保留旧密钥，然后轮换回来，中间不写入（控制）； 然后再次旋转，在新的key下写一些不相关的东西，然后旋转回来。
  ```sh
  restore_values() {
    control-agent-server api DELETE /api/settings/secrets/QA_F18_ROTATED --expect 200,404 >/dev/null
    control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" --expect 200 >/dev/null
    control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"api_key\": \"$QA_F18_LLM_KEY\"}}}" --expect 200 >/dev/null
  }
  trap 'restore_values || true' EXIT
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" --expect 200
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"api_key\": \"$QA_F18_LLM_KEY\"}}}" --expect 200 --check llm_api_key_is_set eq true
  control-agent-server state cat home/.openhands/secrets.json --check custom_secrets.QA_F18_TOKEN.secret matches '^gAAAAA'
  control-agent-server state cat home/.openhands/settings.json --check agent_settings.llm.api_key matches '^gAAAAA'
  control-agent-server restart --rotate-secret-key
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200,404,409,500 --save F18.secret-key-rotation/read-under-new-key
  control-agent-server api GET /api/settings --expect 200,409,500 --save F18.secret-key-rotation/settings-under-new-key
  control-agent-server restart --restore-secret-key
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.secret-key-rotation/control-rotated-back
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY"
  control-agent-server restart --rotate-secret-key
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_ROTATED", "value": "qa-f18-rotated-value"}' --expect 500 --save F18.secret-key-rotation/put-under-new-key
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18_rotated": true}}' --expect 409 --check detail contains 'encrypted with a different key' --check detail contains OH_PREVIOUS_SECRET_KEYS --save F18.secret-key-rotation/patch-under-new-key
  control-agent-server restart --restore-secret-key
  control-agent-server state cat home/.openhands/secrets.json --check custom_secrets.QA_F18_TOKEN.secret matches '^gAAAAA'
  control-agent-server state cat home/.openhands/settings.json --check agent_settings.llm.api_key matches '^gAAAAA'
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.secret-key-rotation/after-rotating-back
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" --save F18.secret-key-rotation/settings-after-rotating-back
  ```
  在新的密钥下，每读取操作都会无声地降级：机密是 404 `Secret not found`，`llm_api_key_is_set` 是 `false`，日志显示 `Failed to decrypt secret value`。 旋转后再次读取这两个值（控制）。 使用新密钥进行写入时，会拒绝（409，PATCH的详情说要恢复密钥或添加到）该商店的“使用不同密钥加密”保护
  `OH_PREVIOUS_SECRET_KEYS`； 500 为机密 PUT, #5622) 并保持两个文件不变，因此在旋转回原始密钥后读取
  再次`QA_F18_TOKEN.secret`和`llm.api_key`。 该陷阱会再次存储这两个值，并在写入完成时删除 `QA_F18_ROTATED`。
- **支持密钥轮换 (`F18.secret-key-previous-keys`)。**存储一个机密和一个LLM键； 轮换密钥，保持旧密钥不变
  `OH_PREVIOUS_SECRET_KEYS_0`，在新密钥下读写，然后在没有旧密钥的情况下重新启动。
  ```sh
  trap 'control-agent-server api DELETE /api/settings/secrets/QA_F18_PREVIOUS --expect 200,404,409,500 >/dev/null || true' EXIT
  control-agent-server api PUT /api/settings/secrets --json "{\"name\": \"QA_F18_TOKEN\", \"value\": \"$QA_F18_SECRET\", \"description\": \"qa f18 token\"}" --expect 200
  control-agent-server api PATCH /api/settings --json "{\"agent_settings_diff\": {\"llm\": {\"api_key\": \"$QA_F18_LLM_KEY\"}}}" --expect 200 --check llm_api_key_is_set eq true
  control-agent-server restart --rotate-secret-key --keep-previous-secret-key
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.secret-key-previous-keys/read-under-new-key
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" --save F18.secret-key-previous-keys/settings-under-new-key
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F18_PREVIOUS", "value": "qa-f18-previous-value"}' --expect 200 --save F18.secret-key-previous-keys/put-under-new-key
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18_previous": true}}' --expect 200 --save F18.secret-key-previous-keys/patch-under-new-key
  control-agent-server restart
  control-agent-server api GET /api/settings/secrets/QA_F18_TOKEN --expect 200 --check . eq "$QA_F18_SECRET" --save F18.secret-key-previous-keys/read-without-old-key
  control-agent-server api GET /api/settings/secrets/QA_F18_PREVIOUS --expect 200 --check . eq qa-f18-previous-value
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --check agent_settings.llm.api_key eq "$QA_F18_LLM_KEY" --check misc_settings.qa_f18_previous eq true --save F18.secret-key-previous-keys/settings-without-old-key
  control-agent-server api PATCH /api/settings --json '{"misc_settings_diff": {"qa_f18_previous": null}}' --expect 200
  ```
  使用旧密钥 `OH_PREVIOUS_SECRET_KEYS` 每次读写都通过新的密钥进行：服务器先使用新的密钥解密，然后依次使用之前的密钥，最后只使用新的密钥加密。 在启动时也会重新加密 `settings.json` 和 `secrets.json` 在新的密钥下（日志显示） `Re-encrypted the settings store under the current key`, 所以之后是裸的 `restart`这会再次丢弃之前的键，但文件仍然可以读取。 其他加密文件（对话，） LLM 只有在下次保存时，(profile，提供商连接)才会重新加密，因此在它们有意义时，保留旧的密钥。 当 `OH_SECRET_KEY` 未设置时，密码是第一个会话
  密钥：旋转该密钥是相同的操作，旧的会话密钥在
  `OH_PREVIOUS_SECRET_KEYS`.

<a id="gotchas"></a>

## 陷阱

- 设置和机密位于 `OH_PERSISTENCE_DIR` 中（启动运行：
  `<run>/home/.openhands/settings.json` 和 `secrets.json`），不在对话旁边。 存储会根据每个请求重新读取文件，因此heredoc编辑无需重新启动即可生效。
- 密码为 `OH_SECRET_KEY`，否则为第一个会话密钥，否则为 None（明文位于 REST、`encrypted` 503）。 因此，在不设置 `OH_SECRET_KEY` 的情况下轮换会话密钥也会更改密码 (`F18.secret-key-rotation`)； 保持旧密钥可读
  `OH_PREVIOUS_SECRET_KEYS`（`重新启动--旋转-机密-键
  --keep-previous-机密-key`, `F18.secret-key-previous-keys`)，其中
  后来 plain `restart` 再次下降。 返回运行之前的密码
  with `restart --restore-secret-key`, not `restart --env OH_SECRET_KEY=...`:
  `--env` 覆盖会坚持以后的每次重新启动，并默默地将后来的 `--rotate-secret-key` 变为无操作。
- `**********`（和一个空字符串）作为机密发布意味着设置 PATCH 中的“无机密”，它会清除该键； 自 #5682 (`F18.secret-empty-value`) 以来，a 机密 PUT 以 422 拒绝它（和空白值）。 与 `X-Expose-Secrets: encrypted` 的往返，服务器解密。
- PATCH 响应始终为已脱敏，而 `conversation_settings` 始终为已脱敏，无论 `X-Expose-Secrets` 说什么。 任何经过身份验证的呼叫者都可以要求 `plaintext`； 没有角色划分，并且没有会话密钥，机密路由对任何人开放。
- `agent_settings_diff` 是 RFC 7386（`null` 任何地方都未设置）；
  `conversation_settings_diff` 和 `misc_settings_diff` 只能取消嵌套项，因此顶级 `null` 是对话设置的 422 错误，而 `null` 存储在 `misc_settings`（客户端无法删除顶级 misc 键）。 `update_settings` 文档字符串（“三个差异深度合并”）和
  `SettingsUpdateRequest` 文档字符串（“与
  `agent_settings_diff`") 都夸大了这一点。
- 更改 `agent_kind` 从目标变体的新基础开始，因此切换到 ACP 并返回会删除 LLM 及其密钥。
- 损坏的 `settings.json` 与 GET 上的“从未配置”无法区分； 只有 PATCH (409) 揭示了它。 损坏的 `secrets.json` 列表为空； PUT和DELETE回答500。
- 5xx主体被重写为`{"detail": "Internal Server Error", "exception": "<code>: <reason>"}`； 断言状态和 `exception`。
- 无效的机密名称是 422，如路由文档字符串所示，OpenAPI 描述也是如此，例如 (`F18.secret-name-contract`)。 404 详细信息始终为 `Secret not found`，对于存储的 `null` 值也是如此。
- `?agent_profile_id=` 在商店错误下加载智能体配置文件
  映射：不再验证答案 400 的配置文件，以及锁
  由另一个进程保留 30 秒答案为 503，如智能体-配置文件路由 (`F18.secret-scope-profile-errors`) 上一样。 范围机密列表和设置更新等待工作人员线程中的配置文件存储锁，因此在保留这些锁时，其他请求仍保持响应。
- `RemoteWorkspace.clone_repos` 在客户端运行，而不是在服务器上，`git` 会留下token在克隆的`remote.origin.url`中（`https://<github_token>@github.com/...`）。 因此，本地替代者需要在客户端进行 git 配置 (`exec --env GIT_CONFIG_GLOBAL=...`)； `owner/repo`简短形式会 `.git`追加，URLs完整形式不会。
- 已知错误项目符号停在 `set -e` 下的 `# bug` 行，因此它们更改的状态被 `EXIT` 陷阱放回，该陷阱的命令以
  `|| true`：陷阱内的失败命令将被记录为子弹的失败命令。
- 当 None 存在时，`GET /api/agent-profiles` 惰性地播种默认的智能体配置文件（并且可以写入 `default` LLM 配置文件和 `active_agent_profile_id`）； 这个家族避免称呼它，所以 `active_agent_profile_id` 保留为 null。 使用`GET /api/agent-profiles/{name}`读取id。
- 设置和机密更改不会发出 WebSocket 事件，并且仅影响之后创建的对话； 第二个视图始终是另一个 GET、磁盘上的文件或消费者 (`RemoteWorkspace`)。
- CLI 将 Fernet token 打印为 `<redacted:encrypted>`，`--field` 也对它们进行编辑； `--check`看到真正的价值。 反馈 token 的配方将 `--unsafe-unredacted` 添加到其 `--field` 读数 (`TOKEN=$(... --field ... --unsafe-unredacted)`) 中，并使其远离证据。
