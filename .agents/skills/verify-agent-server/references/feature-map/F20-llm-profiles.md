<a id="llm-profiles"></a>

# LLM 个人资料

LLM配置了消费者保存一次并切换的：保存一个模型、键和选项，列出保存的名称（当前的），读取一个（键隐藏、加密或根据请求显示），在保存之前检查草稿与实际提供者的一致性，将一个设置为服务器的设置的活动LLM，重命名它（当前的指针和智能体-profile参考跟随），以及删除它（在智能体配置仍然使用它时拒绝）。 每个配置文件都是 `OH_PERSISTENCE_DIR/profiles` 下的一个 JSON 文件，其密钥由服务器的密码加密，因此配置文件在重新启动后仍然存在。 飞行前 `validate` 路由发送一个真实的一对 token 完成，其中包含已发布的配置和答案 `valid` True 或 False； 它从不读取或写入存储。 SDK的`RemoteWorkspace.get_llm()`和TypeScript`ProfilesClient`是程序化消费者。

资料来源：`openhands-agent-server/openhands/agent_server/profiles_router.py`、`openhands-agent-server/openhands/agent_server/_secrets_exposure.py`、`openhands-sdk/openhands/sdk/llm/llm_profile_store.py`、`openhands-sdk/openhands/sdk/profiles/profile_refs.py`、`openhands-sdk/openhands/sdk/workspace/remote/base.py`、`clients/typescript/src/client/profiles-client.ts`

需求：`llm`、`node`

Routes: `GET /api/profiles`, `GET /api/profiles/{name}`,
`POST /api/profiles/{name}`, `POST /api/profiles/{name}/validate`,
`DELETE /api/profiles/{name}`, `POST /api/profiles/{name}/rename`,
`POST /api/profiles/{name}/activate`

<a id="sub-features"></a>

## 子功能

- `F20.auth-required`：每个配置文件路由都回答 401，没有有效的 `X-Session-API-Key`，并且没有任何变化。
- `F20.save`：`POST /api/profiles/{name}`带有DeepSeek模型和关键答案201`Profile '<name>' saved`； 该列表显示摘要 `{name, model, base_url, provider_connection_id, provider_connection_broken, api_key_set: true}` 和活动配置文件，`GET` 按名称返回配置。
- `F20.key-encrypted-at-rest`：profile文件`home/.openhands/profiles/<name>.json`为模式`600`，`schema_version`为1，Fernet`gAAAAA`token为`api_key`； 明文密钥不会出现在服务器主目录下的任何位置。
- `F20.get-secrets`：`GET /api/profiles/{name}` 默认情况下返回 `config.api_key: null` 和 `api_key_set: true`、原始密钥和 `X-Expose-Secrets: plaintext`、`gAAAAA` token 和 `encrypted`（或旧版 `true`），以及任何其他标头值的 400。
- `F20.save-encrypted-roundtrip`：从 `encrypted` 读取回发 `gAAAAA` token 存储原始密钥（服务器在重新加密之前对其进行解密），而不是 token。
- `F20.save-without-secrets`：`include_secrets: false`存储占位符`**********`而不是key； 列表和 `GET` 都报告 `api_key_set: false`，明文读取返回 `null`。
- `F20.not-found`：未知名称答案404 `Profile '<name>' not found`的`GET`、`activate`和`rename`，也用于同名重命名。
- `F20.name-rules`：名称必须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`：所有六个命名路由上的前导 `-` 均为 422，接受 64 个字符，65 个字符为 422； 没有 `llm` 的保存或验证主体，或者没有 `llm.model` 的保存，是 422 并且不保存任何内容。
- `F20.corrupt-files`：无效的配置文件JSON（或不是对象）被排除在列表之外，并在`GET`和`activate`上回答400 `Failed to load profile ...`，保存它修复它，并且不可读的`settings.json`使激活409而不触及文件。
- `F20.store-busy`：当另一个进程保存配置文件存储的锁时，保存会等待 30 秒锁超时并回答 503 `Profile store is busy. Please retry.` 而不保存； 一旦锁空闲，同样的保存是201。
- `F20.store-busy-responsive`：当配置文件请求等待存储锁时，服务器不断应答其他请求（3秒内`GET /alive`）。
- `F20.profile-limit`：存储了 50 个配置文件，创建另一个配置文件的结果是 409 `Profile limit reached (50)`，而覆盖现有配置文件的结果仍然是 201。
- `F20.validate-live`: `validate` 具有工作 DeepSeek 闪存配置答案 `{valid: true, error: null}`，同样当密钥是 `encrypted` 读取的 `gAAAAA` token 时； 草稿未保存。
- `F20.validate-rejects`: `validate` 回答 200 `valid: false`，其中提供者不提供服务的模型 (`LLMBadRequestError`) 和无效的 DeepSeek 密钥存在键入错误，但不回显该密钥。
- `F20.validate-bad-key-type`：无效的 DeepSeek 密钥（提供商 HTTP 401）被报告为 `LLMAuthenticationError`，与任何其他提供商的 401 一样。
- `F20.validate-provider-errors`：在重试关闭的情况下，提供者401是`valid: false``LLMAuthenticationError`，500或无法到达的`base_url`是`valid: false``LLMServiceUnavailableError`，瞬态429或每次尝试超时是`valid: true`； 超时判决是在发布的 `timeout` 一次尝试之后到达的，远远早于挂起的提供者会回答； 提供者接收系统消息`Reply with one token.`、用户`ping`和`max_tokens: 1`。
- `F20.validate-quota-exhausted`：JSON`error.type`和`error.code`为`insufficient_quota`的提供者429以`LLMRateLimitError`失败验证，即使人类可读消息不重复机器代码； 普通的 429 仍然是短暂的。
- `F20.validate-subscription-login`: 没有存储 OpenAI 订阅登录的服务器上的 `auth_type: subscription` 配置的 `validate` 立即回答 200 `valid: false` (`ValueError`, `OpenAI subscription login is required`)，而不是 500。
- `F20.validate-unreachable-bounded`：配置的 `validate`，其 `base_url` 拒绝使用默认重试策略在 30 秒内回答 `valid: false` 的连接。
- `F20.validate-hang-bounded`：提供者从不应答的配置的 `validate` 使用默认的超时和重试策略在 30 秒内返回判决。
- `F20.activate`：`POST /api/profiles/{name}/activate`回答200个`llm_applied: true`； `GET /api/settings` 然后在 `agent_settings.llm` 和 `active_profile` 中设置配置文件的 LLM（模型、密钥、选项），列表报告相同的 `active_profile`，并且 `settings.json` 保存加密的密钥。
- `F20.activate-conversation`：在激活配置文件的模型和选项上运行激活并完成后，从保存的设置开始对话。
- `F20.activate-acp`：使用 ACP 智能体设置，激活仅移动指针：200 `llm_applied: false`、`active_profile` 设置，无 `agent_settings.llm`。
- `F20.sdk-get-llm`：SDK的`RemoteWorkspace.get_llm(profile_name=...)`返回了存储的模型、选项和明文密钥，`usage_id` `profile:<name>`，`get_llm()`遵循`active_profile`，关键字覆盖获胜，未知名称引发`FileNotFoundError`。
- `F20.ts-client`: TypeScript `ProfilesClient` 列表、保存、读取（隐藏、`plaintext`、`encrypted`），验证、重命名、激活和删除一个配置，以及表面 404 和 422 为 `HttpError`。
- `F20.activate-dangling-provider` 一个与不存在的提供商连接关联的配置被保存，而没有其嵌入键。 `base_url`，被列出为 `provider_connection_broken: true`，读取正常，但激活状态为 422，没有移动激活指针。
- `F20.activate-linked-provider`：一个与现有提供商连接关联的模板保存时没有包含内联键，被列出和读取时使用`api_key_set: true`（连接的键）和`null`键，激活时将连接的键写入`agent_settings.llm`。
- `F20.sdk-get-llm-linked`： LLM 来自 `RemoteWorkspace.get_llm(profile_name=<linked profile>)` 的 SDK 对话在提供者连接的密钥上运行并结束。
- `F20.no-cipher`：在没有 `OH_SECRET_KEY` 和会话密钥（没有加密算法）的服务器上，保存的密钥以明文存储在 `600` 文件中，明文读取和激活工作，`X-Expose-Secrets: encrypted` 回应 503。
- `F20.persist-restart`：配置文件、它们的加密密钥、选项和活动指针在使用相同的机密密钥重新启动后仍然存在。
- `F20.rename`：`POST /api/profiles/{name}/rename`移动文件并保留密钥； 旧名称为 404，`active_profile` 遵循列表和设置中的重命名，智能体其 `llm_profile_ref` 引用旧名称的配置文件现在引用新名称。
- `F20.rename-errors`：重命名为现有名称为 409，且不进行任何更改；同名重命名为 200 `unchanged (same name)`；无效或缺失的 `new_name` 为 422。
- `F20.delete-guarded`：删除智能体配置文件引用的配置文件是409命名引用者，并且配置文件保留。
- `F20.delete`: `DELETE /api/profiles/{name}` 删除文件和列表项，并在两个视图中清除 `active_profile`，保留已应用的 `agent_settings.llm`，并再次返回 200 对于已经不存在的名称。
- `F20.json-alias-guard`一个带有名字的 `.json` 后缀处理相同的目标（`GET /api/profiles/<name>.json` 读取 `<name>`），并且通过该别名删除会被拒绝并返回 409，而智能体 [profile references] `<name>`，因为它的普通名称也是如此。
- `F20.secret-key-rotation`在服务器后方的机密更改了密钥，拒绝激活一个存储的密钥无法解密的配置，而不是默默地应用一个密钥 LLM.

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /api/profiles`、`GET /api/profiles/{name}`（可选
  `X-Expose-Secrets: plaintext|encrypted`), `POST /api/profiles/{name}` (`{"llm": {...LLM fields...}, "include_secrets": true}`),
  `POST /api/profiles/{name}/validate` (`{"llm": {...}}`; 路径名仅用于日志记录； `auth_type: subscription`首先加载存储的OpenAI订阅登录），`POST /api/profiles/{name}/activate`（无正文），
  `POST /api/profiles/{name}/rename` (`{"new_name": "..."}`),
  `DELETE /api/profiles/{name}`. 下面的每个食谱都驱动这些路线。
- 这里使用的第二个视图：`GET /api/settings` (`active_profile`,
  `agent_settings.llm`, `llm_api_key_is_set`; 设置系列），`home/.openhands/profiles/`（`state cat`）下的配置文件，以及
  `GET /api/agent-profiles/{name}` (`llm_profile_ref`; 智能体简介家族）。
  `PATCH /api/settings` 和 `active_profile` 是激活配置文件（设置系列）的第二种方法。 `POST` 和 `DELETE /api/llm/provider-connections`（提供商连接系列）排列链接配置文件项目符号。
- SDK: `RemoteWorkspace.get_llm(profile_name=...)` 读取
  `GET /api/profiles/{name}` 与 `X-Expose-Secrets: plaintext` 并构建一个
  `LLM`; 如果没有名称，它首先从 `GET /api/settings` 解析 `active_profile` (`openhands-sdk/openhands/sdk/workspace/remote/base.py`)。 驱动力
  `F20.sdk-get-llm` 和 `F20.sdk-get-llm-linked`（Python 程序运行
  `exec`). SDK 的本地 `LLMProfileStore` 与锁的文件格式相同，但没有服务器（`F20.store-busy` 用 `flock` 代替它）。
- TypeScript 客户端：`ProfilesClient.listProfiles`，`getProfile（名称，
  {exposeSecrets})`, `saveProfile`, `validateProfile`, `activateProfile`,
  `renameProfile`、`deleteProfile`（默认请求超时 60 秒），以及 `SettingsClient` 上的相同调用。 由 `F20.ts-client` 驱动（`clients/typescript/dist` 上的 `node` 程序）。
- 配置：`OH_SECRET_KEY`是REST处密钥的密码； 没有它，第一个会话密钥就是密码，没有它，就没有 None (`F20.no-cipher`, `launch --no-auth --no-secret-key`)。 `OH_PERSISTENCE_DIR` 成立`profiles/`。
- 对话：从保存的设置开始的对话（Agent Canvas路径，`conversation start`不包含智能体字段）使用了写入到`agent_settings.llm`（`F20.activate-conversation`）的最后激活。
- Agent Canvas（仅限上下文）：LLM 设置页面在保存草稿之前验证草稿，将键作为 `encrypted` token 往返，并激活所选配置文件。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  设置 `$DEEPSEEK_API_KEY`，`jq`、`flock` 和 `node` 在 `PATH` 上（如果 `clients/typescript/dist` 缺失，则构建 TypeScript 客户端）。 下面的块保存 DeepSeek 预设（`deepseek-flash`、活动和
  `deepseek-pro`) 和智能体配置文件 `qa-f20-agent`，其 `llm_profile_ref` 为 `qa-flash`； 该引用保持软状态，直到 `F20.save` 创建
  `qa-flash`、`F20.rename`和`F20.delete-guarded`依赖它。 它还编写了 SDK 和 TypeScript 程序 `F20.sdk-get-llm`，
  `F20.ts-client`和`F20.sdk-get-llm-linked`运行； 他们读
  `$DEEPSEEK_API_KEY` 从环境 `exec` 传递。
  `sdk_conversation.py <profile>` 运行单消息 SDK 对话（无工具，无可视化工具，本次运行测试夹具下的工作区）
  `RemoteWorkspace.get_llm(profile_name=<profile>)` 并打印 LLM 是否带有密钥。
- 携带真实密钥的主体通过管道从 shell 内置 `printf` 传输到 `api ... --stdin`，因此密钥永远不会出现在命令行上； CLI 从输出和证据中对其进行了编辑。
- `F20.store-busy`和`F20.store-busy-responsive`分别保持存储锁约34秒； `F20.validate-hang-bounded` 等待大约 15 秒以获取服务器的判决并硬重启运行，这样服务器端请求就不会比它更长久； `F20.no-cipher` 启动和停止第二个服务器；
  `F20.persist-restart`重新开始运行； `F20.secret-key-rotation` 使用新的机密密钥重新启动它，并且必须留在最后。

  ```sh
  control-agent-server llm preset deepseek
  control-agent-server api GET /api/profiles --expect 200 --check active_profile eq deepseek-flash --check profiles len-eq 2
  control-agent-server api POST /api/agent-profiles/qa-f20-agent --json '{"llm_profile_ref": "qa-flash"}' --expect 201
  F20="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f20"
  mkdir -p "$F20"
  cat > "$F20/sdk_get_llm.py" <<'EOF'
  import os

  from openhands.sdk.workspace import RemoteWorkspace

  ws = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=os.path.join(os.environ["AGENT_SERVER_VERIFY_RUN"], "fixtures/qa-f20"),
  )
  named = ws.get_llm(profile_name="qa-flash")
  assert named.model == "deepseek/deepseek-flash", named.model
  assert named.num_retries == 0, named.num_retries
  assert named.usage_id == "profile:qa-flash", named.usage_id
  assert named.api_key is not None
  assert named.api_key.get_secret_value() == os.environ["DEEPSEEK_API_KEY"], "key differs"
  active = ws.get_llm()
  assert active.usage_id == "profile:qa-flash", active.usage_id
  assert active.api_key is not None
  assert active.api_key.get_secret_value() == os.environ["DEEPSEEK_API_KEY"], "key differs"
  override = ws.get_llm(profile_name="qa-nokey", temperature=0.5)
  assert override.model == "openai/qa-nokey", override.model
  assert override.temperature == 0.5, override.temperature
  assert override.api_key is None, "qa-nokey has no stored key"
  try:
      ws.get_llm(profile_name="qa-missing")
  except FileNotFoundError:
      pass
  else:
      raise AssertionError("an unknown profile did not raise FileNotFoundError")
  print("QA_F20_SDK_OK")
  EOF
  cat > "$F20/sdk_conversation.py" <<'EOF'
  import os
  import sys

  from openhands.sdk import Agent, Conversation
  from openhands.sdk.workspace import RemoteWorkspace

  workdir = os.path.join(os.environ["AGENT_SERVER_VERIFY_RUN"], "fixtures/qa-f20/workspace")
  os.makedirs(workdir, exist_ok=True)
  ws = RemoteWorkspace(
      host=os.environ["AGENT_SERVER_URL"],
      api_key=os.environ["SESSION_API_KEY"],
      working_dir=workdir,
  )
  llm = ws.get_llm(profile_name=sys.argv[1])
  print("QA_F20_CONV_KEY_SET", llm.api_key is not None, flush=True)
  conversation = Conversation(agent=Agent(llm=llm, tools=[]), workspace=ws, visualizer=None)
  try:
      conversation.send_message("Reply with one word: pong")
      conversation.run()
      status = conversation.state.execution_status.value
      print("QA_F20_CONV_STATUS", status)
      assert status == "finished", status
  finally:
      conversation.close()
  print("QA_F20_CONV_OK")
  EOF
  cat > "$F20/ts_profiles.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { ProfilesClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new ProfilesClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const before = await client.listProfiles();
  assert.equal(before.active_profile, 'qa-flash');
  assert.deepEqual(await client.saveProfile('qa-ts', { llm: { model: 'openai/qa-ts', api_key: 'sk-qa-f20-ts' } }),
    { name: 'qa-ts', message: "Profile 'qa-ts' saved" });
  const hidden = await client.getProfile('qa-ts');
  assert.equal(hidden.config.api_key, null);
  assert.equal(hidden.api_key_set, true);
  const plain = await client.getProfile('qa-ts', { exposeSecrets: 'plaintext' });
  assert.equal(plain.config.api_key, 'sk-qa-f20-ts');
  const enc = await client.getProfile('qa-ts', { exposeSecrets: 'encrypted' });
  assert.match(enc.config.api_key, /^gAAAAA/);
  const verdict = await client.validateProfile('qa-ts', {
    llm: { model: 'openai/qa-ts', base_url: 'http://127.0.0.1:9/v1', api_key: 'sk-qa-f20-ts', num_retries: 0 },
  });
  assert.equal(verdict.valid, false);
  assert.equal(verdict.error.type, 'LLMServiceUnavailableError');
  assert.equal((await client.renameProfile('qa-ts', 'qa-ts2')).name, 'qa-ts2');
  assert.equal((await client.activateProfile('qa-ts2')).llm_applied, true);
  assert.equal((await client.listProfiles()).active_profile, 'qa-ts2');
  assert.equal((await client.activateProfile('qa-flash')).llm_applied, true);
  assert.equal((await client.deleteProfile('qa-ts2')).message, "Profile 'qa-ts2' deleted");
  await assert.rejects(client.getProfile('qa-ts2'), (err) => err.status === 404);
  await assert.rejects(client.saveProfile('-qa-bad', { llm: { model: 'openai/qa' } }), (err) => err.status === 422);
  const after = await client.listProfiles();
  assert.equal(after.active_profile, 'qa-flash');
  assert.equal(after.profiles.length, before.profiles.length);
  client.close();
  console.log('QA_F20_TS_OK');
  JS
  ```

- **需要密钥 (`F20.auth-required`)。**在没有钥匙或错误钥匙的情况下呼叫每条路线。
  ```sh
  control-agent-server api GET /api/profiles --auth none --expect 401 --check detail eq Unauthorized --save F20.auth-required/list
  control-agent-server api GET /api/profiles/deepseek-flash --auth bad --expect 401
  control-agent-server api POST /api/profiles/qa-noauth --auth none --json '{"llm": {"model": "openai/qa"}}' --expect 401
  control-agent-server api POST /api/profiles/qa-noauth/validate --auth none --json '{"llm": {"model": "openai/qa"}}' --expect 401
  control-agent-server api POST /api/profiles/deepseek-pro/activate --auth none --expect 401
  control-agent-server api POST /api/profiles/deepseek-pro/rename --auth none --json '{"new_name": "qa-noauth"}' --expect 401
  control-agent-server api DELETE /api/profiles/deepseek-pro --auth none --expect 401
  control-agent-server api GET /api/profiles --expect 200 --check active_profile eq deepseek-flash --check profiles len-eq 2 --check profiles contains '"name": "deepseek-pro"'
  ```
  每一条调用都是401 `{"detail": "Unauthorized"}`; 使用该密钥后，列表仍然保留两个预设的配置文件 `deepseek-flash` 仍然活跃。
- **保存(`F20.save`)。**使用真实密钥保存 DeepSeek flash 模型并
  `num_retries: 0`（后面的项目符号用来区分此配置文件的标记
  from the preset's `deepseek-flash`).
  ```sh
  printf '{"llm": {"model": "deepseek/deepseek-flash", "api_key": "%s", "num_retries": 0}}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/profiles/qa-flash --stdin --expect 201 \
      --check name eq qa-flash --check message eq "Profile 'qa-flash' saved" --save F20.save/save
  control-agent-server api GET /api/profiles --expect 200 --check profiles len-eq 3 --check active_profile eq deepseek-flash \
    --check profiles contains '"name": "qa-flash", "model": "deepseek/deepseek-flash", "base_url": null, "provider_connection_id": null, "provider_connection_broken": false, "api_key_set": true' \
    --save F20.save/list
  control-agent-server api GET /api/profiles/qa-flash --expect 200 --check name eq qa-flash \
    --check config.model eq deepseek/deepseek-flash --check config.num_retries eq 0 --check api_key_set eq true
  ```
  保存为201，列表包含三个用户  `qa-flash` 摘要和保存没有改变活跃的配置文件。
- **在 REST (`F20.key-encrypted-at-rest`) 处加密。**读取保存写入的文件。
  ```sh
  control-agent-server state cat home/.openhands/profiles/qa-flash.json --mode 600 \
    --check api_key matches '^gAAAAA' --check model eq deepseek/deepseek-flash --check schema_version eq 1
  control-agent-server state grep deepseek/deepseek-flash --glob 'home/**/*'
  control-agent-server state grep --env-value DEEPSEEK_API_KEY --glob 'home/**/*' --expect-none
  ```
  该文件是 `600`, 其它 `api_key` 是一个 Fernet token (printed as
  `<redacted:encrypted>`），并且服务器主目录下没有文件包含明文密钥（包括预设的配置文件和 `settings.json`）。 第一个 `state grep` 是阳性对照：相同的 glob 到达隐藏的 `home/.openhands/profiles/` 文件并在那里找到模型名称。
- **读取密钥 (`F20.get-secrets`)。**读取每种曝光模式下的配置文件。
  ```sh
  control-agent-server api GET /api/profiles/qa-flash --expect 200 --check config.api_key missing --check api_key_set eq true --save F20.get-secrets/default
  control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.api_key eq "$DEEPSEEK_API_KEY" --save F20.get-secrets/plaintext
  control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: encrypted' --expect 200 \
    --check config.api_key matches '^gAAAAA' --save F20.get-secrets/encrypted
  control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: true' --expect 200 --check config.api_key matches '^gAAAAA'
  control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: yes' --expect 400 \
    --check detail contains 'Invalid X-Expose-Secrets header value' --save F20.get-secrets/invalid-mode
  ```
  缺少 `config.api_key`，`null`；缺少 `api_key_set`，`true`。
  `plaintext` 返回 DeepSeek 键（输出中的已脱敏），`encrypted` 和旧版 `true` 为 `gAAAAA` token，`yes` 为 400。
- **加密往返 (`F20.save-encrypted-roundtrip`)。**保存一个副本，其键是来自 `encrypted` 读取的 token，如 Agent Canvas 一样。
  ```sh
  ENC=$(control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: encrypted' --field config.api_key --unsafe-unredacted)
  control-agent-server api POST /api/profiles/qa-flash-copy \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\"}}" --expect 201 --save F20.save-encrypted-roundtrip/save
  control-agent-server api GET /api/profiles/qa-flash-copy --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.api_key eq "$DEEPSEEK_API_KEY" --save F20.save-encrypted-roundtrip/plaintext
  control-agent-server state cat home/.openhands/profiles/qa-flash-copy.json --check api_key matches '^gAAAAA'
  control-agent-server api DELETE /api/profiles/qa-flash-copy --expect 200
  ```
  复制的明文密钥是 DeepSeek，而不是 token。 复制在末尾被删除。
- **不保存机密 (`F20.save-without-secrets`)。**使用密钥和 `include_secrets: false` 保存配置文件。
  ```sh
  control-agent-server api POST /api/profiles/qa-nokey \
    --json '{"llm": {"model": "openai/qa-nokey", "api_key": "sk-qa-f20-not-stored"}, "include_secrets": false}' \
    --expect 201 --save F20.save-without-secrets/save
  control-agent-server state cat home/.openhands/profiles/qa-nokey.json --check api_key eq '**********' --not-contains sk-qa-f20-not-stored
  control-agent-server api GET /api/profiles \
    --check profiles contains '"name": "qa-nokey", "model": "openai/qa-nokey", "base_url": null, "provider_connection_id": null, "provider_connection_broken": false, "api_key_set": false' \
    --save F20.save-without-secrets/list
  control-agent-server api GET /api/profiles/qa-nokey --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.api_key missing --check api_key_set eq false
  ```
  文件中包含`**********`，而不是发布的密钥。 列表显示没有设置密钥，`GET` 说读取明文返回 `null`。
- **未知名称 (`F20.not-found`)。**读取、激活和重命名从未保存的名称。
  ```sh
  control-agent-server api GET /api/profiles/qa-missing --expect 404 --check detail eq "Profile 'qa-missing' not found" --save F20.not-found/get
  control-agent-server api POST /api/profiles/qa-missing/activate --expect 404 --check detail eq "Profile 'qa-missing' not found" --save F20.not-found/activate
  control-agent-server api POST /api/profiles/qa-missing/rename --json '{"new_name": "qa-other"}' --expect 404 --save F20.not-found/rename
  control-agent-server api POST /api/profiles/qa-missing/rename --json '{"new_name": "qa-missing"}' --expect 404
  control-agent-server api GET /api/profiles/qa-other --expect 404
  control-agent-server api GET /api/profiles --check active_profile eq deepseek-flash
  ```
  所有都404，活跃的配置不变。
- **命名规则(`F20.name-rules`).**使用带有前导 `-` 的名称、64 个字符的限制以及不带 `llm` 或 `model` 的正文。
  ```sh
  control-agent-server api GET /api/profiles/-qa-bad --expect 422 --check detail.0.type eq string_pattern_mismatch --check detail.0.loc.1 eq name --save F20.name-rules/get
  control-agent-server api POST /api/profiles/-qa-bad --json '{"llm": {"model": "openai/qa"}}' --expect 422
  control-agent-server api POST /api/profiles/-qa-bad/validate --json '{"llm": {"model": "openai/qa"}}' --expect 422
  control-agent-server api POST /api/profiles/-qa-bad/activate --expect 422
  control-agent-server api POST /api/profiles/-qa-bad/rename --json '{"new_name": "qa-ok"}' --expect 422
  control-agent-server api DELETE /api/profiles/-qa-bad --expect 422
  LONG="qa-$(printf 'x%.0s' $(seq 61))"
  test "${#LONG}" = 64
  control-agent-server api POST "/api/profiles/$LONG" --json '{"llm": {"model": "openai/qa"}}' --expect 201
  control-agent-server api GET "/api/profiles/$LONG" --expect 200 --check name eq "$LONG" --check config.model eq openai/qa
  control-agent-server api GET "/api/profiles/${LONG}x" --expect 422 --check detail.0.type eq string_too_long --save F20.name-rules/too-long
  control-agent-server api DELETE "/api/profiles/$LONG" --expect 200
  control-agent-server api POST /api/profiles/qa-bad-body --json '{}' --expect 422 --check detail.0.loc.1 eq llm --save F20.name-rules/no-llm
  control-agent-server api POST /api/profiles/qa-bad-body --json '{"llm": {"api_key": "sk-qa-f20"}}' --expect 422 \
    --check detail.0.msg contains 'model must be specified' --save F20.name-rules/no-model
  control-agent-server api POST /api/profiles/qa-bad-body/validate --json '{}' --expect 422 --check detail.0.loc.1 eq llm \
    --save F20.name-rules/validate-no-llm
  control-agent-server api GET /api/profiles/qa-bad-body --expect 404
  control-agent-server api GET /api/profiles --check profiles len-eq 4
  ```
  Every `-qa-bad` 呼叫失败 `name` 路径参数，保存64个字符，65个字符为422 `string_too_long`这三个坏体是422，列表又回到了四个角色（两个预设） `qa-flash`, `qa-nokey`).
- **损坏的文件 (`F20.corrupt-files`).** 写一个截短的个人简介，一个个人简介 JSON 列出，然后是一个截断的 `settings.json` （安排在写入过程中出现崩溃或手动编辑），并驱动路由通过它们。
  ```sh
  P="$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles"
  printf '{"model": "openai/qa-corrupt", ' > "$P/qa-corrupt.json"
  printf '["not", "an", "object"]' > "$P/qa-notdict.json"
  control-agent-server api GET /api/profiles --expect 200 --check profiles len-eq 4 \
    --check profiles not-contains '"name": "qa-corrupt"' --check profiles not-contains '"name": "qa-notdict"' --save F20.corrupt-files/list
  control-agent-server api GET /api/profiles/qa-corrupt --expect 400 --check detail contains 'Failed to load profile `qa-corrupt`' --save F20.corrupt-files/get
  control-agent-server api GET /api/profiles/qa-notdict --expect 400 --check detail contains 'Failed to load profile `qa-notdict`'
  control-agent-server api POST /api/profiles/qa-corrupt/activate --expect 400 --check detail contains 'Failed to load profile' --save F20.corrupt-files/activate
  control-agent-server api GET /api/profiles --check active_profile eq deepseek-flash
  control-agent-server api POST /api/profiles/qa-corrupt --json '{"llm": {"model": "openai/qa-repaired"}}' --expect 201
  control-agent-server api GET /api/profiles/qa-corrupt --expect 200 --check config.model eq openai/qa-repaired
  control-agent-server api DELETE /api/profiles/qa-corrupt --expect 200
  control-agent-server api DELETE /api/profiles/qa-notdict --expect 200
  test ! -e "$P/qa-notdict.json"
  S="$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  cp -p "$S" "$S.qa-f20-bak"
  printf '{"agent_settings": ' > "$S"
  control-agent-server api POST /api/profiles/qa-nokey/activate --expect 409 \
    --check detail contains 'Settings file is corrupted or encrypted with a different key' --save F20.corrupt-files/corrupt-settings
  test "$(cat "$S")" = '{"agent_settings": '
  mv "$S.qa-f20-bak" "$S"
  control-agent-server api GET /api/profiles --check active_profile eq deepseek-flash --check profiles len-eq 4
  ```
  两个断开的配置都缺失了，`GET` 和 `activate` 都是 400，而不是 500，而活动配置仍然存在。 保存超过`qa-corrupt`次修复，同时两个删除都返回200。 由于截断了 `settings.json`，激活码为 409，文件是字节对字节写入的。 然后将原始内容放回。
- **[已弃用] 仓库繁忙`F20.store-busy`).** 另一个进程（这里 `flock`，代表 SDK's `LLMProfileStore` 或同一个服务器上的另一个持久化目录包含了的锁在收到保存后，持续播放34秒。 服务器自身的 30 秒锁超时正处于测试中，所以这个条目等待它。
  ```sh
  P="$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles"
  HELD="$F20/lock-held"
  rm -f "$HELD"
  flock -x "$P/.profiles.lock" sh -c "touch '$HELD'; sleep 34" &
  LOCKER=$!
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  T0=$SECONDS
  control-agent-server api POST /api/profiles/qa-busy --json '{"llm": {"model": "openai/qa-busy"}}' --timeout 60 --expect 503 \
    --check exception eq '503: Profile store is busy. Please retry.' --save F20.store-busy/save
  test $((SECONDS - T0)) -ge 29
  test $((SECONDS - T0)) -le 33
  wait "$LOCKER"
  control-agent-server api GET /api/profiles/qa-busy --expect 404
  control-agent-server api POST /api/profiles/qa-busy --json '{"llm": {"model": "openai/qa-busy"}}' --expect 201 --expect-max-ms 5000
  control-agent-server api DELETE /api/profiles/qa-busy --expect 200
  ```
  保存答案在29到33秒后（`detail`是通用的`Internal Server Error`）。 该路由的消息是 `exception`
  之后`qa-busy`不存在，当锁空闲时，相同的保存立即成功。
- **锁 wait不会阻塞服务器`F20.store-busy-responsive`).** Probe `/alive` 一次与锁免费（阳性对照），保持锁再次在后台启动保存，并进行探查 `/alive` 在保存等待时。 只有五秒的暂停能让后台先保存（留有余地以应对慢速） CLI 在保存的 30 秒内，探针落在了保存的范围内锁等待。
  ```sh
  P="$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles"
  HELD="$F20/lock-held-2"
  rm -f "$HELD"
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000
  flock -x "$P/.profiles.lock" sh -c "touch '$HELD'; sleep 34" &
  LOCKER=$!
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  (control-agent-server api POST /api/profiles/qa-busy --json '{"llm": {"model": "openai/qa-busy"}}' --timeout 60 --expect 503 --quiet > "$F20/busy-save.json") &
  SAVER=$!
  sleep 5
  control-agent-server api GET /alive --auth none --expect 200 --timeout 60 --save F20.store-busy-responsive/alive | tee "$F20/busy-alive.json"
  wait "$SAVER"
  wait "$LOCKER"
  control-agent-server api GET /api/profiles/qa-busy --expect 404
  control-agent-server assert --json "$F20/busy-alive.json" --check elapsed_ms le 3000
  ```
  `/alive` 3 秒内回答，保存时也一样，就像锁免费：用户详情路由是基础的 `def` 因此，处理器 FastAPI 运行同步，file-locked `LLMProfileStore` 在它的线程池和锁等待永远不会持有事件循环 (`profiles_router.py`). 在检查绑定之前， `wait "$SAVER"` 证明后台保存确实等待并被拒绝了，状态码为503，两个后台进程都已经结束（所以后面的子弹会找到） 锁免费的，和 `qa-busy` 没有创建。
- **配置文件限制 (`F20.profile-limit`)。**将存储填充到 50，然后创建并覆盖。
  ```sh
  N=$(control-agent-server api GET /api/profiles --field profiles | jq length)
  for i in $(seq $((N + 1)) 50); do
    control-agent-server api POST "/api/profiles/qa-cap-$i" --json '{"llm": {"model": "openai/qa-cap"}}' --expect 201 --field name
  done
  control-agent-server api GET /api/profiles --check profiles len-eq 50 --max-chars 200
  control-agent-server api POST /api/profiles/qa-cap-51 --json '{"llm": {"model": "openai/qa-cap"}}' --expect 409 \
    --check detail eq 'Profile limit reached (50). Delete a profile before saving a new one.' --save F20.profile-limit/create-51st
  control-agent-server api GET /api/profiles/qa-cap-51 --expect 404
  control-agent-server api POST /api/profiles/qa-nokey --json '{"llm": {"model": "openai/qa-nokey", "temperature": 0.25}, "include_secrets": false}' \
    --expect 201 --save F20.profile-limit/overwrite-at-cap
  control-agent-server api GET /api/profiles/qa-nokey --check config.temperature eq 0.25
  for i in $(seq $((N + 1)) 50); do
    control-agent-server api DELETE "/api/profiles/qa-cap-$i" --expect 200 --field name
  done
  control-agent-server api GET /api/profiles --check profiles len-eq "$N"
  ```
  第51个配置项为409，未创建。 在顶点处覆盖 `qa-nokey` 的值为 201，其新 `temperature` 的读取结果为； 填充物的模板又删除了。
- **验证工作配置 (`F20.validate-live`)。**预飞行真实 DeepSeek flash 模型，一次使用纯文本密钥，一次使用
  `qa-flash` 中的 `encrypted` token。
  ```sh
  printf '{"llm": {"model": "deepseek/deepseek-flash", "api_key": "%s", "num_retries": 0}}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/profiles/qa-draft/validate --stdin --timeout 120 --expect 200 \
      --check valid eq true --check error missing --save F20.validate-live/plaintext-key
  ENC=$(control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: encrypted' --field config.api_key --unsafe-unredacted)
  control-agent-server api POST /api/profiles/qa-draft/validate --timeout 120 --expect 200 \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"api_key\": \"$ENC\", \"num_retries\": 0}}" \
    --check valid eq true --save F20.validate-live/encrypted-key
  control-agent-server api GET /api/profiles/qa-draft --expect 404
  control-agent-server api GET /api/profiles --check profiles len-eq 4
  ```
  答案 `{"valid": true, "error": null}` （token 在通话之前已被解密） DeepSeek 未经处理就发送，会拒绝它；`qa-draft` 从未保存过。
- **验证拒绝 (`F20.validate-rejects`)。**飞行前模型 DeepSeek 不可用，然后是无效密钥。
  ```sh
  printf '{"llm": {"model": "deepseek/qa-no-such-model", "api_key": "%s", "num_retries": 0}}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/profiles/qa-draft/validate --stdin --timeout 120 --expect 200 \
      --check valid eq false --check error.type eq LLMBadRequestError --save F20.validate-rejects/unknown-model
  control-agent-server api POST /api/profiles/qa-draft/validate --timeout 120 --expect 200 \
    --json '{"llm": {"model": "deepseek/deepseek-flash", "api_key": "sk-qa-f20-invalid-key", "num_retries": 0}}' \
    --check valid eq false --check error.type exists --check error.message not-contains sk-qa-f20-invalid-key \
    --save F20.validate-rejects/invalid-key
  control-agent-server api GET /api/profiles/qa-draft --expect 404
  ```
  两者都是200，带有`valid: false`和`error`。 提供商的消息通过已脱敏传递，不包含发布的密钥。
- **DeepSeek 401 类型 (`F20.validate-bad-key-type`)，已知错误。**无效的 DeepSeek 密钥应像任何提供者 401 一样进行分类。
  ```sh
  control-agent-server api POST /api/profiles/qa-draft/validate --timeout 120 --expect 200 \
    --json '{"llm": {"model": "deepseek/deepseek-flash", "api_key": "sk-qa-f20-invalid-key", "num_retries": 0}}' \
    --check valid eq false --check error.message contains authentication_error --check error.message not-contains sk-qa-f20-invalid-key \
    --save F20.validate-bad-key-type/deepseek-401 | tee "$F20/bad-key.json"
  control-agent-server assert --json "$F20/bad-key.json" --check response.body.error.type eq LLMAuthenticationError  # value.status 等于 200 并且 value.response.body.error.type 等于 LLMBadRequestError
  ```
  该呼叫本身证明了这一点： `valid: false`, 以及提供商的错误通过传递 `error.message` 是 DeepSeek'typed'
  `"type":"authentication_error"`. 预计 `error.type`
  `LLMAuthenticationError`（与 OpenAI 兼容的 401 给出的内容
  `F20.validate-provider-errors`). 今天是 `LLMBadRequestError`，因此标记为 `# bug` 的检查失败：DeepSeek 回答 HTTP 401
  `Authentication Fails, Your api key: ... is invalid`, LiteLLM 将其提升为
  `BadRequestError` 和 SDK 的身份验证启发式（`AUTH_PATTERNS` 中
  `openhands-sdk/openhands/sdk/llm/exceptions/classifier.py`) 既不匹配该文本，也不匹配 `authentication_error` 类型，因此客户端无法区分错误密钥和错误请求。
- **提供商失败 (`F20.validate-provider-errors`)。**编写脚本
  `llm-stub` 应答 401、500、瞬态 429 并挂起，并用重试关闭它并指向关闭的端口。
  ```sh
  BEFORE_PROFILES=$(control-agent-server api GET /api/profiles --field profiles)
  STUB=$(control-agent-server fixture llm-stub --name qa-f20-stub --step status:401 --print-path)
  STUB_LLM="{\"model\": \"openai/qa-stub\", \"base_url\": \"$STUB/v1\", \"api_key\": \"qa-stub-key\", \"num_retries\": 0}"
  control-agent-server api POST /api/profiles/qa-stub/validate --json "{\"llm\": $STUB_LLM}" --timeout 60 --expect 200 \
    --check valid eq false --check error.type eq LLMAuthenticationError --save F20.validate-provider-errors/401
  control-agent-server sink read --name qa-f20-stub --contains 'Reply with one token.' --expect-min 1 --save F20.validate-provider-errors/stub-request
  control-agent-server sink read --name qa-f20-stub --contains '"max_tokens": 1' --expect-min 1
  control-agent-server sink read --name qa-f20-stub --expect-min 1 \
    --contains '"role": "system"}, {"content": [{"type": "text", "text": "ping"}], "role": "user"}'
  control-agent-server fixture llm-stub --name qa-f20-stub --step status:500
  control-agent-server api POST /api/profiles/qa-stub/validate --json "{\"llm\": $STUB_LLM}" --timeout 60 --expect 200 \
    --check valid eq false --check error.type eq LLMServiceUnavailableError --save F20.validate-provider-errors/500
  control-agent-server fixture llm-stub --name qa-f20-stub --step status:429
  control-agent-server api POST /api/profiles/qa-stub/validate --json "{\"llm\": $STUB_LLM}" --timeout 60 --expect 200 \
    --check valid eq true --check error missing --save F20.validate-provider-errors/429
  control-agent-server fixture llm-stub --name qa-f20-stub --step hang:30
  control-agent-server api POST /api/profiles/qa-stub/validate --timeout 60 --expect 200 --expect-max-ms 15000 \
    --json "{\"llm\": {\"model\": \"openai/qa-stub\", \"base_url\": \"$STUB/v1\", \"api_key\": \"qa-stub-key\", \"num_retries\": 0, \"timeout\": 3}}" \
    --check valid eq true --save F20.validate-provider-errors/timeout
  control-agent-server sink read --name qa-f20-stub --contains '"hang": 30' --expect-min 1 --expect-max 1
  control-agent-server api POST /api/profiles/qa-unreachable/validate --timeout 60 --expect 200 \
    --json '{"llm": {"model": "openai/qa-unreachable", "base_url": "http://127.0.0.1:9/v1", "api_key": "qa-key", "num_retries": 0}}' \
    --check valid eq false --check error.type eq LLMServiceUnavailableError --save F20.validate-provider-errors/unreachable
  control-agent-server api GET /api/profiles --check profiles eq "$BEFORE_PROFILES"
  ```
  stub的第一个请求携带系统消息 `Reply with one token.` 直接在用户之前 `ping` 该仓库的系统第一不变量，and `max_tokens: 1`401 对应
  `LLMAuthenticationError`、500 和关闭的端口
  `LLMServiceUnavailableError` (`valid: false`). 瞬态 429 和 3 秒超时保持非阻塞 (`valid: true`)。 超时判决大约在3秒内（在15秒的限制内）到达（尽管在`hang`步骤中，该桩记录了恰好一次请求，它只会在30秒后回答）。 忽略发布的 `timeout` 的服务器将等待该回复并导致绑定失败。 什么都没有保存。
- **用尽配额 (`F20.validate-quota-exhausted`), 已知 bug.** 一个兼容 OpenAI 的提供者通过响应的结构化 `error.type` 和 `error.code` 区分了临时的 429 错误和用尽配额。
  ```sh
  QUOTA_PROFILES=$(control-agent-server api GET /api/profiles --field profiles)
  QUOTA_STUB=$(control-agent-server fixture llm-stub --name qa-f20-quota --step status:429 --print-path)
  QUOTA_LLM="{\"model\":\"openai/qa-quota\",\"base_url\":\"$QUOTA_STUB/v1\",\"api_key\":\"qa-quota-key\",\"num_retries\":0}"
  control-agent-server api POST /api/profiles/qa-quota/validate --json "{\"llm\":$QUOTA_LLM}" --timeout 60 --expect 200 \
    --check valid eq true --check error missing --save F20.validate-quota-exhausted/transient-control
  control-agent-server fixture llm-stub --name qa-f20-quota \
    --step 'status:429:{"error":{"message":"You exceeded your current quota, please check your plan and billing details.","type":"insufficient_quota","code":"insufficient_quota"}}'
  control-agent-server api POST /api/profiles/qa-quota/validate --json "{\"llm\":$QUOTA_LLM}" --timeout 60 --expect 200 \
    --save F20.validate-quota-exhausted/quota-exhausted > "$F20/quota-result.json"
  control-agent-server sink read --name qa-f20-quota --contains insufficient_quota --expect-min 1 --expect-max 1 \
    --save F20.validate-quota-exhausted/provider-request
  control-agent-server api GET /api/profiles --check profiles eq "$QUOTA_PROFILES"
  control-agent-server assert --json "$F20/quota-result.json" --check response.body.valid eq false \
    --check response.body.error.type eq LLMRateLimitError  # bug: value.status eq 200 && value.response.body.valid eq True && value.response.body.error 缺失
  ```
  预期：配额块已耗尽验证 (#5768)，并出现键入错误，
  while the transient positive control succeeds and neither draft is saved.
  今天，真正的 HTTP 错误已减少为之前人类可读的消息
  `is_quota_exhaustion_error` 检查 `insufficient_quota`。 结构化代码丢失，因此此响应错误地返回 `valid: true`，并且没有错误 ([OpenHands/software-智能体-SDK#6185](https://github.com/OpenHands/software-agent-sdk/issues/6185))。 现有的单元测试将 JSON 代码直接嵌入到模拟的异常字符串中，并且不执行提供者到 SDK 的映射。
- ** 无登录的订阅 (`F20.validate-subscription-login`).** 预飞行 ChatGPT-订阅配置 (`auth_type: subscription`, 私有家中的 Agent Canvas 订阅路径) 在此运行，该订阅没有 OpenAI 登录。
  ```sh
  control-agent-server api POST /api/profiles/qa-sub/validate --timeout 60 --expect 200 --expect-max-ms 10000 \
    --json '{"llm": {"model": "openai/gpt-5-mini", "auth_type": "subscription"}}' \
    --check valid eq false --check error.type eq ValueError --check error.message eq 'OpenAI subscription login is required' \
    --save F20.validate-subscription-login/no-login
  control-agent-server api GET /api/profiles/qa-sub --expect 404
  ```
  服务器在调用任何提供商之前会查找存储的订阅凭据，找到了 None，并用工厂的答案 `valid: false`
  `ValueError` 一秒内（处理程序将凭据错误映射到判决而不是 500）。 此路径不需要真正的订阅登录； 使用 1 进行验证超出了此处的范围。
- **无法立即回复端点个答案 (`F20.validate-unreachable-bounded`)。**与默认重试策略相同的关闭端口（正文中没有 `num_retries`）。
  ```sh
  control-agent-server api POST /api/profiles/qa-unreachable/validate --timeout 240 --expect 200 \
    --json '{"llm": {"model": "openai/qa-unreachable", "base_url": "http://127.0.0.1:9/v1", "api_key": "qa-key"}}' \
    --check valid eq false --check error.type eq LLMServiceUnavailableError \
    --save F20.validate-unreachable-bounded/default-retries | tee "$F20/unreachable.json"
  control-agent-server assert --json "$F20/unreachable.json" --check elapsed_ms le 30000
  ```
  客户端等待服务器的回应足够长，因此调用证明服务器是正常的，并且它的判断是正确的`valid: false`,
  `LLMServiceUnavailableError`); 然后边界检查花费了多长时间。 判决在一秒内到来： `validate` 与发布的副本进行 ping LLM 那一次尝试（没有成功） 重试，什么也不做 `num_retries` 被限制在15秒内或比当前发布的更短 `timeout`因此，该程序的运行时重试默认情况下，策略（五次尝试，每次等待8到64秒）从未生效。 因为  CLI 等待答案，服务器端请求不会超过子弹。
- **挂起的提供者得到有界判决（`F20.validate-hang-bounded`）。**永远不会回答的 `llm-stub`，默认为超时和重试。
  ```sh
  HANG=$(control-agent-server fixture llm-stub --name qa-f20-hang --step hang:900 --print-path)
  RC=0
  control-agent-server api POST /api/profiles/qa-hang/validate --timeout 30 --expect 200 \
    --json "{\"llm\": {\"model\": \"openai/qa-stub\", \"base_url\": \"$HANG/v1\", \"api_key\": \"qa-stub-key\"}}" \
    --check valid exists --save F20.validate-hang-bounded/default-timeout | tee "$F20/hang.json" || RC=$?
  control-agent-server sink read --name qa-f20-hang --contains '"hang": 900' --expect-min 1 --save F20.validate-hang-bounded/stub-request
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000
  control-agent-server restart --hard
  control-agent-server api GET /api/profiles --expect 200 --check active_profile eq deepseek-flash
  test "$RC" = 0 || jq -e '.exit == 3 and (.error // "" | startswith("ReadTimeout"))' "$F20/hang.json"
  control-agent-server assert --json "$F20/hang.json" --check ok eq true
  ```
  判决在30秒内到来（CLI的`--timeout 30`是上限）：大约15秒，`valid: true`。 预飞行尝试被限制在15秒，而不是LLM的300秒`timeout`，并且不会重试，因此代理只记录一个请求，超时这个请求被视为临时，会回答
  `valid: true`. 在最后检查之前的行意味着失败： stub 登录了请求（服务器到达了提供者） `/alive` 答案立即给出（服务器正在运行） 事件循环免费），只有当它是客户端时，检查器才接受失败的调用 `ReadTimeout` （拒绝连接、5xx错误或错误判决将击碎子弹）。 的 `restart --hard` (SIGKILL) 取消了一个超时的服务器端请求。 配置文件和设置位于磁盘上并且返回时保持不变。
- **激活(`F20.activate`)。**将 `qa-flash` 设为活动 LLM 并读回设置。
  ```sh
  control-agent-server api POST /api/profiles/qa-flash/activate --expect 200 --check name eq qa-flash --check llm_applied eq true \
    --check message eq "Profile 'qa-flash' activated and applied to current settings" --save F20.activate/activate
  control-agent-server api GET /api/profiles --check active_profile eq qa-flash --save F20.activate/list
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --expect 200 --max-chars 300 \
    --check active_profile eq qa-flash --check agent_settings.llm.model eq deepseek/deepseek-flash \
    --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --check agent_settings.llm.num_retries eq 0 \
    --check llm_api_key_is_set eq true --save F20.activate/settings
  control-agent-server state cat home/.openhands/settings.json --max-chars 300 \
    --check active_profile eq qa-flash --check agent_settings.llm.api_key matches '^gAAAAA'
  ```
  响应说 LLM 已应用。 设置携带 `qa-flash` 的模型、密钥和 `num_retries: 0`（预设的配置有 5 个），而 `settings.json` 则将密钥加密存储。
- **激活驱动对话 (`F20.activate-conversation`)。**从保存的设置开始对话，无需任何工具和一个词提示词。
  ```sh
  CID=$(control-agent-server conversation start --tools none --no-autotitle --prompt 'Reply with one word: pong' --wait --timeout 180 --print-id)
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --max-chars 300 \
    --check execution_status eq finished --check agent.llm.model eq deepseek/deepseek-flash --check agent.llm.num_retries eq 0 \
    --check stats.usage_to_metrics.default.model_name eq deepseek/deepseek-flash \
    --check stats.usage_to_metrics.default.accumulated_token_usage.prompt_tokens gt 0 --save F20.activate-conversation/conversation
  control-agent-server api DELETE "/api/conversations/$CID" --expect 200
  ```
  对话将在 `deepseek/deepseek-flash` 结束
  `num_retries: 0`（因此智能体来自 `qa-flash`，而不是预设），其使用指标显示真实的提示词 token。 对话被删除。
- **ACP设置(`F20.activate-acp`)。**将智能体种类切换为ACP，激活，然后恢复。
  ```sh
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "acp"}}' --expect 200 --max-chars 200 \
    --check agent_settings.agent_kind eq acp
  control-agent-server api POST /api/profiles/qa-nokey/activate --expect 200 --check llm_applied eq false \
    --check message eq "Profile 'qa-nokey' activated" --save F20.activate-acp/activate
  control-agent-server api GET /api/settings --expect 200 --max-chars 200 --check active_profile eq qa-nokey \
    --check agent_settings.agent_kind eq acp --check agent_settings.llm missing --save F20.activate-acp/settings
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "openhands"}}' --expect 200 --max-chars 200 \
    --check agent_settings.agent_kind eq openhands
  control-agent-server api POST /api/profiles/qa-flash/activate --expect 200 --check llm_applied eq true
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check active_profile eq qa-flash \
    --check agent_settings.llm.model eq deepseek/deepseek-flash --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY"
  ```
  在 ACP 设置激活答案 `llm_applied: false`，只移动
  `active_profile`; 返回 OpenHands 设置 `qa-flash` 为下一个项目符号重新激活。
- **SDK 消费者 (`F20.sdk-get-llm`).** `RemoteWorkspace.get_llm()` 按名字，
  from the active pointer, with an override, and for an unknown name.
  ```sh
  control-agent-server exec --env OPENHANDS_SUPPRESS_BANNER=1 --timeout 120 --expect-output QA_F20_SDK_OK \
    --save F20.sdk-get-llm/program -- .venv/bin/python "$F20/sdk_get_llm.py"
  ```
  程序打印 `QA_F20_SDK_OK`：`get_llm(profile_name="qa-flash")` 是
  `deepseek/deepseek-flash` 与 `num_retries: 0`、DeepSeek 键和
  `usage_id` `profile:qa-flash`; `get_llm()` 解决主动`qa-flash`；
  `temperature=0.5` 覆盖 `qa-nokey` 存储的 `0.25`（并且其密钥保持未设置状态）； `qa-missing` 从服务器的 404 引发 `FileNotFoundError`。
- **TypeScript 客户端 (`F20.ts-client`).**每个`ProfilesClient`方法
  from the built client (built here when missing).
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server exec --timeout 120 --expect-output QA_F20_TS_OK --save F20.ts-client/program -- node "$F20/ts_profiles.mjs"
  control-agent-server api GET /api/profiles --check active_profile eq qa-flash --check profiles len-eq 4 \
    --check profiles not-contains '"name": "qa-ts' --save F20.ts-client/list-after
  ```
  程序打印 `QA_F20_TS_OK`：保存的密钥被隐藏，明文和
  `gAAAAA`在三个读取中，`validateProfile`针对关闭的端口是
  `valid: false` `LLMServiceUnavailableError`，重命名和激活移动 `active_profile`，以及删除的名称和无效名称拒绝 `HttpError` 状态 404 和 422。 随后的列表具有相同的四个配置文件并且 `qa-flash` 再次处于活动状态。
- **悬挂的提供商链接 (`F20.activate-dangling-provider`)。**使用内联密钥和 `base_url` 保存链接到不存在的提供商连接 ID 的配置文件。
  ```sh
  control-agent-server api POST /api/profiles/qa-linked --expect 201 \
    --json '{"llm": {"model": "openai/qa-linked", "api_key": "sk-qa-f20-linked", "base_url": "http://127.0.0.1:9/v1", "provider_connection_id": "qa-no-such-connection"}}'
  control-agent-server state cat home/.openhands/profiles/qa-linked.json --not-contains sk-qa-f20-linked \
    --check provider_connection_id eq qa-no-such-connection --check api_key missing --check base_url missing
  control-agent-server api GET /api/profiles \
    --check profiles contains '"name": "qa-linked", "model": "openai/qa-linked", "base_url": null, "provider_connection_id": "qa-no-such-connection", "provider_connection_broken": true, "api_key_set": false' \
    --save F20.activate-dangling-provider/list
  control-agent-server api GET /api/profiles/qa-linked --expect 200 \
    --check config.provider_connection_id eq qa-no-such-connection --check config.api_key missing --check api_key_set eq false
  control-agent-server api GET /api/profiles/qa-linked --header 'X-Expose-Secrets: plaintext' --expect 422 \
    --check detail eq "Profile 'qa-linked' references provider connection 'qa-no-such-connection', which does not exist. Update the profile or recreate the connection."
  control-agent-server api POST /api/profiles/qa-linked/activate --expect 422 \
    --check detail eq "Profile 'qa-linked' references provider connection 'qa-no-such-connection', which does not exist. Update the profile or recreate the connection." \
    --save F20.activate-dangling-provider/activate
  control-agent-server api GET /api/profiles --check active_profile eq qa-flash
  control-agent-server api DELETE /api/profiles/qa-linked --expect 200
  ```
  inline key 和 `base_url` 在保存时，如果被丢弃（连接拥有它们），则列表标记链接为断开 `GET` 仍然有效，同时支持纯文本 `GET` (这解决了链接问题，因为#4952) 和激活都返回422状态码，带有相同的消息， `qa-flash` 仍然活跃。
- **关联的提供者(`F20.activate-linked-provider`).**创建一个提供者连接，该连接持有DeepSeek密钥（安排），将一个外露的标签键与它关联起来，并激活它。
  ```sh
  CONN=$(printf '{"display_name": "qa-f20-conn", "provider": "deepseek", "api_key": "%s"}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/llm/provider-connections --stdin --expect 201 --field id)
  control-agent-server api POST /api/profiles/qa-linked-live --expect 201 \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"provider_connection_id\": \"$CONN\", \"api_key\": \"sk-qa-f20-inline\", \"num_retries\": 0}}"
  control-agent-server state cat home/.openhands/profiles/qa-linked-live.json --not-contains sk-qa-f20-inline \
    --check api_key missing --check provider_connection_id eq "$CONN"
  control-agent-server api GET /api/profiles --save F20.activate-linked-provider/list \
    --check profiles contains "\"name\": \"qa-linked-live\", \"model\": \"deepseek/deepseek-flash\", \"base_url\": null, \"provider_connection_id\": \"$CONN\", \"provider_connection_broken\": false, \"api_key_set\": true"
  control-agent-server api GET /api/profiles/qa-linked-live --expect 200 \
    --check config.api_key missing --check config.provider_connection_id eq "$CONN" --check api_key_set eq true --save F20.activate-linked-provider/get
  control-agent-server api GET /api/profiles/qa-linked-live --header 'X-Expose-Secrets: plaintext' --expect 200 --quiet \
    --check config.api_key eq "$DEEPSEEK_API_KEY" --check config.provider_connection_id eq "$CONN"
  control-agent-server api POST /api/profiles/qa-linked-live/activate --expect 200 --check llm_applied eq true --save F20.activate-linked-provider/activate
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check active_profile eq qa-linked-live \
    --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" --check agent_settings.llm.provider_connection_id eq "$CONN" \
    --check llm_api_key_is_set eq true --save F20.activate-linked-provider/settings
  control-agent-server api POST /api/profiles/qa-flash/activate --expect 200 --check llm_applied eq true
  control-agent-server api DELETE /api/profiles/qa-linked-live --expect 200
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 200
  control-agent-server api GET /api/profiles --check active_profile eq qa-flash --check profiles len-eq 4
  ```
  文件只保留连接标识（没有内联键）。 列表和 `GET` 报告 `api_key_set: true` 从连接中。 默认的 `GET` 展示了一个
  `null` 密钥，明文 `GET` 解析链接并返回连接的密钥（自 #4952 起）； 激活解析连接并将其密钥写入 `agent_settings.llm`，保留 `provider_connection_id`。
  `qa-flash` 被重新激活，然后配置文件和连接被删除。
- **关联配置上的 SDK（`F20.sdk-get-llm-linked`）。** 从某个关联配置的 `get_llm()` 构建 SDK 对话，其连接持有 DeepSeek 密钥；此前，同一程序已在普通
  `qa-flash` 配置文件（阳性对照：相同的密钥、模型和程序）。
  ```sh
  CONN=$(printf '{"display_name": "qa-f20-sdk-conn", "provider": "deepseek", "api_key": "%s"}' "$DEEPSEEK_API_KEY" \
    | control-agent-server api POST /api/llm/provider-connections --stdin --expect 201 --field id)
  control-agent-server api POST /api/profiles/qa-linked-sdk --expect 201 \
    --json "{\"llm\": {\"model\": \"deepseek/deepseek-flash\", \"provider_connection_id\": \"$CONN\", \"num_retries\": 0}}"
  control-agent-server exec --env OPENHANDS_SUPPRESS_BANNER=1 --timeout 180 --expect-output 'QA_F20_CONV_KEY_SET True' \
    --expect-output QA_F20_CONV_OK --save F20.sdk-get-llm-linked/plain-profile -- .venv/bin/python "$F20/sdk_conversation.py" qa-flash
  control-agent-server exec --env OPENHANDS_SUPPRESS_BANNER=1 --timeout 180 --expect-output 'QA_F20_CONV_KEY_SET True' \
    --expect-output QA_F20_CONV_OK --save F20.sdk-get-llm-linked/program -- .venv/bin/python "$F20/sdk_conversation.py" qa-linked-sdk
  control-agent-server api DELETE /api/profiles/qa-linked-sdk --expect 200
  control-agent-server api DELETE "/api/llm/provider-connections/$CONN" --expect 200
  ```
  链接的对话会在连接的密钥上结束，就像普通对话控制一样：`get_llm()` 读取 `GET /api/profiles/{name}`
  `X-Expose-Secrets: plaintext`，自 #4952 以来解析 `provider_connection_id`（在此之前它返回无密钥 LLM 和 `run()` 失败，并显示
  `LLMAuthenticationError`).
- **没有密码算法 (`F20.no-cipher`).** 启动一个没有会话密钥也没有 `OH_SECRET_KEY` (因此没有密码算法)的第二个服务器，保存一个带密钥的配置，读取它并在那里激活它。
  ```sh
  B=$(control-agent-server launch --new --print-run --name f20-nocipher --no-auth --no-secret-key)
  trap 'control-agent-server stop --run "$B" > /dev/null 2>&1 || true' EXIT
  control-agent-server api POST /api/profiles/qa-plain --run "$B" --expect 201 \
    --json '{"llm": {"model": "openai/qa-plain", "api_key": "sk-qa-f20-plain-key"}}' --save F20.no-cipher/save
  control-agent-server state cat home/.openhands/profiles/qa-plain.json --run "$B" --mode 600 --check api_key eq sk-qa-f20-plain-key
  control-agent-server api GET /api/profiles --run "$B" --check profiles contains '"name": "qa-plain", "model": "openai/qa-plain", "base_url": null, "provider_connection_id": null, "provider_connection_broken": false, "api_key_set": true'
  control-agent-server api GET /api/profiles/qa-plain --run "$B" --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.api_key eq sk-qa-f20-plain-key --save F20.no-cipher/plaintext
  control-agent-server api GET /api/profiles/qa-plain --run "$B" --header 'X-Expose-Secrets: encrypted' --expect 503 \
    --check exception contains 'Encryption not available: OH_SECRET_KEY is not configured' --save F20.no-cipher/encrypted
  control-agent-server api POST /api/profiles/qa-plain/activate --run "$B" --expect 200 --check llm_applied eq true
  control-agent-server state cat home/.openhands/settings.json --run "$B" --max-chars 200 --check agent_settings.llm.api_key eq sk-qa-f20-plain-key
  control-agent-server stop --run "$B"
  ```
  配置文件（模式 `600`) 和 `settings.json` 将密钥以明文形式保存，明文读取后返回它，和  `encrypted` 读取操作返回 503（消息内容） `exception`). 第二个服务器已停止，由  `trap` 当检查失败时也是如此，一个失败的子弹永远不会泄露它。 主运行文件保持加密状态`F20.key-encrypted-at-rest`). 的 `--save` 这些文件落在了第二个运行的第二轮 `evidence/` directory.
- **重新启动 (`F20.persist-restart`)。**重新启动运行并读回所有内容。
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/profiles --expect 200 --check active_profile eq qa-flash --check profiles len-eq 4 \
    --check profiles contains '"name": "qa-flash", "model": "deepseek/deepseek-flash", "base_url": null, "provider_connection_id": null, "provider_connection_broken": false, "api_key_set": true' \
    --check profiles contains '"name": "qa-nokey", "model": "openai/qa-nokey", "base_url": null, "provider_connection_id": null, "provider_connection_broken": false, "api_key_set": false' \
    --save F20.persist-restart/list
  control-agent-server api GET /api/profiles/qa-flash --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.api_key eq "$DEEPSEEK_API_KEY" --check config.num_retries eq 0 --save F20.persist-restart/plaintext
  control-agent-server api GET /api/profiles/qa-nokey --check config.temperature eq 0.25
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 \
    --check active_profile eq qa-flash --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY"
  ```
  四个配置文件，`qa-flash`的解密密钥和选项，`qa-nokey`的覆盖和活动指针都存活。
- **重命名(`F20.rename`)。**重命名 `qa-f20-agent` 引用的活动配置文件。
  ```sh
  control-agent-server api POST /api/profiles/qa-flash/rename --json '{"new_name": "qa-fast"}' --expect 200 --check name eq qa-fast \
    --check message eq "Profile 'qa-flash' renamed to 'qa-fast'" --save F20.rename/rename
  control-agent-server api GET /api/profiles/qa-flash --expect 404
  control-agent-server api GET /api/profiles/qa-fast --header 'X-Expose-Secrets: plaintext' --expect 200 \
    --check config.model eq deepseek/deepseek-flash --check config.api_key eq "$DEEPSEEK_API_KEY"
  control-agent-server api GET /api/profiles --check active_profile eq qa-fast --check profiles not-contains '"name": "qa-flash"' --save F20.rename/list
  control-agent-server api GET /api/settings --max-chars 200 --check active_profile eq qa-fast --check agent_settings.llm.model eq deepseek/deepseek-flash
  control-agent-server api GET /api/agent-profiles/qa-f20-agent --expect 200 --max-chars 200 --check profile.llm_profile_ref eq qa-fast \
    --save F20.rename/agent-profile
  test -f "$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles/qa-fast.json"
  test ! -e "$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles/qa-flash.json"
  ```
  旧名已消失，新名保留了密钥，`active_profile` 是
  列表和设置中的 `qa-fast`，以及智能体配置文件的
  `llm_profile_ref`如下。
- **重命名错误 (`F20.rename-errors`)。**重命名为已用名称、自身名称以及无效名称。
  ```sh
  control-agent-server api POST /api/profiles/qa-fast/rename --json '{"new_name": "qa-nokey"}' --expect 409 \
    --check detail eq "Profile 'qa-nokey' already exists" --save F20.rename-errors/conflict
  control-agent-server api GET /api/profiles/qa-nokey --check config.model eq openai/qa-nokey --check config.temperature eq 0.25
  control-agent-server api POST /api/profiles/qa-fast/rename --json '{"new_name": "qa-fast"}' --expect 200 \
    --check message eq "Profile 'qa-fast' unchanged (same name)" --save F20.rename-errors/same-name
  control-agent-server api POST /api/profiles/qa-fast/rename --json '{"new_name": ".qa-hidden"}' --expect 422 --check detail.0.loc.1 eq new_name
  control-agent-server api POST /api/profiles/qa-fast/rename --json '{}' --expect 422 --check detail.0.type eq missing
  control-agent-server api GET /api/profiles --check active_profile eq qa-fast --check profiles len-eq 4
  ```
  冲突是409，两个配置都未更改。 同名重命名是一个200无操作。 坏的身体是422。
- **受保护的删除 (`F20.delete-guarded`)。**删除个人资料
  `qa-f20-agent`仍然引用。
  ```sh
  control-agent-server api DELETE /api/profiles/qa-fast --expect 409 \
    --check detail eq 'LLM profile is referenced by 1 agent profile(s): qa-f20-agent' --save F20.delete-guarded/delete
  control-agent-server api GET /api/profiles/qa-fast --expect 200
  control-agent-server api GET /api/profiles --check active_profile eq qa-fast
  control-agent-server api DELETE /api/agent-profiles/qa-f20-agent --expect 200
  ```
  删除操作返回409，指定了referrer和profile仍然有效。 然后删除了该智能体资料，这样`F20.delete`就可以继续了。
- **删除(`F20.delete`)。**删除活动配置文件两次。
  ```sh
  control-agent-server api DELETE /api/profiles/qa-fast --expect 200 --check name eq qa-fast \
    --check message eq "Profile 'qa-fast' deleted" --save F20.delete/delete
  control-agent-server api GET /api/profiles/qa-fast --expect 404
  control-agent-server api GET /api/profiles --check active_profile missing --check profiles len-eq 3 \
    --check profiles not-contains '"name": "qa-fast"' --save F20.delete/list
  control-agent-server api GET /api/settings --header 'X-Expose-Secrets: plaintext' --max-chars 200 --check active_profile missing \
    --check agent_settings.llm.model eq deepseek/deepseek-flash --check agent_settings.llm.api_key eq "$DEEPSEEK_API_KEY" \
    --save F20.delete/settings
  test ! -e "$AGENT_SERVER_VERIFY_RUN/home/.openhands/profiles/qa-fast.json"
  control-agent-server api DELETE /api/profiles/qa-fast --expect 200 --check message eq "Profile 'qa-fast' deleted" --save F20.delete/repeat
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200 --check llm_applied eq true
  ```
  该文件和其配置已丢失 `active_profile` 是 `null` 在两种视图中，都 `agent_settings.llm` 仍然保留了删除的用户模型和密钥。 重复删除是200次。 `deepseek-flash` 重新激活以恢复预设状态。
- **通过`.json`别名删除(`F20.json-alias-guard`)。**保存 `qa-alias`，从新的智能体配置文件中引用它，并将其删除为
  `qa-alias.json`.
  ```sh
  control-agent-server api POST /api/profiles/qa-alias --json '{"llm": {"model": "openai/qa-alias"}}' --expect 201
  control-agent-server api POST /api/agent-profiles/qa-f20-alias-agent --json '{"llm_profile_ref": "qa-alias"}' --expect 201
  control-agent-server api DELETE /api/profiles/qa-alias --expect 409 \
    --check detail eq 'LLM profile is referenced by 1 agent profile(s): qa-f20-alias-agent'
  control-agent-server api GET /api/profiles/qa-alias.json --expect 200 --check config.model eq openai/qa-alias
  control-agent-server api DELETE /api/profiles/qa-alias.json --expect 409 \
    --check detail eq 'LLM profile is referenced by 1 agent profile(s): qa-f20-alias-agent' \
    --save F20.json-alias-guard/delete
  control-agent-server api GET /api/profiles/qa-alias --expect 200 --check config.model eq openai/qa-alias \
    --save F20.json-alias-guard/after
  control-agent-server api DELETE /api/agent-profiles/qa-f20-alias-agent --expect 200
  control-agent-server api DELETE /api/profiles/qa-alias --expect 200
  control-agent-server api GET /api/profiles --check profiles not-contains '"name": "qa-alias"'
  ```
  别名删除与普通删除一样，都返回 409 错误（正控制：
  `DELETE /api/profiles/qa-alias` 是 409，`GET .../qa-alias.json` 读取相同的配置文件），`qa-alias` 保留下来。 商店删除了 `.json` 后缀（`_get_profile_path`
  `openhands-sdk/openhands/sdk/llm/llm_profile_store.py`），并且 FK 扫描（`openhands-sdk/openhands/sdk/profiles/profile_refs.py` 中的 `_scan_referrers`）和 `_set_active_profile_if_matches` (`profiles_router.py`) 比较相同的存储密钥，因此别名删除或重命名也会清除或移动
  `active_profile` 和级联 `llm_profile_ref`。 清理会删除智能体配置文件和配置文件，并检查列表中不再有它。
- **机密密钥轮换 (`F20.secret-key-rotation`)，已知错误。**保存配置文件，使用新的机密密钥重新启动，然后激活它。
  ```sh
  control-agent-server api POST /api/profiles/qa-rotate --json '{"llm": {"model": "openai/qa-rotate", "api_key": "sk-qa-f20-rotate"}}' --expect 201
  control-agent-server api GET /api/profiles/qa-rotate --header 'X-Expose-Secrets: plaintext' --expect 200 --check config.api_key eq sk-qa-f20-rotate
  control-agent-server api GET /api/settings --max-chars 200 --check active_profile eq deepseek-flash --check llm_api_key_is_set eq true
  control-agent-server restart --rotate-secret-key
  control-agent-server state cat home/.openhands/profiles/qa-rotate.json --check api_key matches '^gAAAAA'
  control-agent-server api GET /api/profiles/qa-rotate --header 'X-Expose-Secrets: plaintext' --expect 2xx,4xx --save F20.secret-key-rotation/detail
  control-agent-server api GET /api/profiles --expect 2xx,4xx --save F20.secret-key-rotation/list
  control-agent-server api POST /api/profiles/qa-rotate/activate --expect 4xx --save F20.secret-key-rotation/activate  # bug：状态 eq 200 && response.body.message 包含“已激活并已应用”
  control-agent-server api GET /api/settings --max-chars 200 --check active_profile eq deepseek-flash
  control-agent-server state cat home/.openhands/settings.json --max-chars 200 --check agent_settings.llm.api_key matches '^gAAAAA'
  ```
  在重启之前，密钥会读回，并且`deepseek-flash`是激活的，带有密钥（正控制）。 预期激活会被拒绝（4xx）
  while the stored key cannot be decrypted, leaving `deepseek-flash` active
  以及设置的旧密文。 今天，该文件仍然保留旧的 token，`GET` 的名称是 `api_key_set: false`，带有 `null` 键，而列表仍然是 `api_key_set: true`，并且激活标记为
  在设置的存储密钥上写入 LLM 和 `api_key: null` 后，`# bug` 回答 200 `activated and applied to current settings`（`llm_api_key_is_set` 变为 `false`），因此提供商的下一次对话失败。 对于无法解密的 token，密码返回 `None`，而不是引发 (`openhands-sdk/openhands/sdk/utils/cipher.py`)，并且配置文件存储会静默加载该密码。 `OH_SECRET_KEY` 时，同样的情况发生，因为只有会话密钥旋转，那么第一个会话密钥就变成了加密密钥（在`launch --no-secret-key`次运行中：`restart --rotate-key`读取明文后返回`null`和`api_key_set: false`）。 最后运行：此运行的每个存储的机密现在都无法读取。

<a id="gotchas"></a>

## 陷阱

- DeepSeek 闪存型号字符串是 `deepseek/deepseek-flash`（什么是
  `deepseek` 预设保存）。 `deepseek/deepseek-v4.1-flash` 保存得很好（保存时不会检查模型），但 `validate` 回答 `valid: false`，
  `LLMBadRequestError`：DeepSeek仅服务于`deepseek-flash`并且
  `deepseek-v4-pro`.
- `validate` 使用发布的 LLM 自己的重试和超时策略（默认
  `num_retries` 5, `retry_min_wait` 8, `retry_max_wait` 64, `timeout` 300). 除非持续时间是您所测试的，否则始终发送 `"num_retries": 0`（以及针对存根的小 `timeout`），并为 CLI 提供比保单更长的 `--timeout`； `llm set` 和 `llm preset` 使用 120 秒的客户端进行验证超时。 请求CLI放弃在服务器中继续运行，直到策略结束。
- `validate` 从不读取存储的配置文件：主体的 `llm` 是必需的，路径名仅出现在日志中。 要预检存储的配置文件，请使用 `X-Expose-Secrets: encrypted` 读取它并将该配置发回。
- 速率限制和超时视为瞬态并回答 `valid: true`； 提供者 503 或拒绝的连接是 `valid: false`。 因此，`valid: true` 并不能证明提供者已回答。
- 真正的 DeepSeek 坏键是 `LLMBadRequestError`，而不是
  `LLMAuthenticationError` (`F20.validate-bad-key-type`); 当提供者为 DeepSeek 时，匹配 `valid`，而不是 `error.type`。
- 列表的 `api_key_set` 是根据原始文件计算出来的，无需解密（除 `**********` 之外的任何非空值都计数），而 `GET` 按名称解密； 当 token 无法解密时，他们不同意 (`F20.secret-key-rotation`)。 链接的提供商连接的密钥在两者中都算作配置文件的密钥。
- 即使活动配置文件已保存，保存也不会改变 `active_profile`
  覆盖：`agent_settings.llm` 保留旧副本，直到配置文件被修改
  再次激活。 删除活动配置文件会清除指针，但会将应用的 LLM 保留在 `agent_settings.llm` 中。
- 激活 ACP 设置只会移动指针。 切换
  `agent_kind` 返回 `openhands`，`PATCH /api/settings` 重置
  `agent_settings.llm` 保持默认值 `active_profile` 保持命名，所以 `RemoteWorkspace.get_llm()` (这遵循指针)以及从设置开始的对话，直到用户激活了个人资料。
- `GET /api/agent-profiles`（列表）播种 `default` 智能体配置文件，当智能体-配置文件存储为空时，该配置文件引用活动的 LLM 配置文件； 之后，删除活动的 LLM 配置文件为 409。 这个家族只读取智能体个个人资料的名字，没有任何种子。
- 以 `.json` 结尾的名称存储时不带后缀，因此 `foo` 和
  `foo.json`与`GET`相同的配置文件，保存、删除和重命名，包括智能体配置文件删除防护、重命名级联和
  `active_profile`指针，始终记录普通名称（`F20.json-alias-guard`）。
- `launch` 设置 `OH_SECRET_KEY`。 `--no-secret-key` 仍然留下一个从第一个会话密钥派生的密码（并且 `restart --rotate-key` 然后丢失每个存储的密钥，如 `F20.secret-key-rotation` 中所示）； 仅
  `--no-auth --no-secret-key` 给出没有密码的服务器 (`F20.no-cipher`)。
- 来自这些路由的 5xx 应答（503 存储繁忙，503 加密不可用）携带 `detail: "Internal Server Error"`； 路由自己的消息位于 `exception` 中（服务器的 5xx 处理程序重写 `detail`）。 断言状态和 `exception`，而不是 `detail`。
- 锁门店等待线程的路由，因此锁仅延迟了超时秒的 REST（即服务器的 `F20.store-busy-responsive`）。 不过，握住锁（`flock` 放在 `profiles/.profiles.lock`）上的时间永远不要超过子弹所需的时间。
- 列表会跳过损坏的配置文件，不会出现错误（日志中出现警告），但名称 `GET` 和 `activate` 为 400。 同时
  `settings.json` 不可读，`GET /api/profiles` 报告
  `active_profile: null`，激活为 409。
- 链接到提供商连接的配置文件默认不显示密钥
  `GET /api/profiles/{name}`; `X-Expose-Secrets: plaintext` 解析连接并返回其密钥（自 #4952 起），这是使用 `get_llm(profile_name=...)` 的 SDK 程序所依赖的 (`F20.sdk-get-llm-linked`)。
- 配置文件路由不发出 WebSocket 事件； 第二个观点是
  `GET /api/settings`，磁盘上的列表和文件。
- 关闭的端口 `127.0.0.1:9` 代表无法访问的提供者； 如果你的机器上有东西监听，请选择另一个关闭的端口。
