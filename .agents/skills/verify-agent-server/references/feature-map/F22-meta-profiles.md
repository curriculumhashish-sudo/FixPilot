<a id="meta-profiles-model-router"></a>

# 元配置文件（模型路由器）

元配置文件是一个命名的、无机密的模型路由配置：
`classifier_model` 加上 `classes` 的有序列表（`{description, model}`，分类器回答类别号）或直接
`prompt_template` 包含 `{{ instance_text }}`（并且可选
`{{ model_table }}`），其中分类器回答 `{"model": "<name>"}`。 每个模型参考都是已保存的 LLM 配置文件的名称。 消费者列出、读取、保存（创建或覆盖）、删除和激活元配置文件； 每个是`OH_PERSISTENCE_DIR/meta-profiles`下的一个JSON文件，最多50个。 服务器设置和线路中的激活记录 `active_meta_profile`
`agent_settings`（`active_meta_profile`、`enable_classify_and_switch_llm_tool: true` 和 `meta_profile` 中的内联副本），因此每个对话都开始
from those settings gets the `route_task_to_model` tool
(`ClassifyAndSwitchLLMTool`). 当智能体调用它时，分类器配置文件会选择一个类，并且对话会切换到该类的 LLM 配置文件以进行后续步骤。 删除活动元配置文件会再次关闭路由。

资料来源：`openhands-agent-server/openhands/agent_server/meta_profiles_router.py`、`openhands-sdk/openhands/sdk/llm/meta_profile_store.py`、`openhands-sdk/openhands/sdk/tool/builtins/classify_and_switch_llm.py`、`openhands-agent-server/openhands/agent_server/persistence/models.py`、`clients/typescript/src/client/meta-profiles-client.ts`

需求：`llm`、`node`

Routes: `GET /api/meta-profiles`, `GET /api/meta-profiles/{name}`,
`POST /api/meta-profiles/{name}`, `DELETE /api/meta-profiles/{name}`,
`POST /api/meta-profiles/{name}/activate`

<a id="sub-features"></a>

## 子功能

- `F22.auth-required`：每个元配置文件路由都回答 401，没有有效的 `X-Session-API-Key`，并且不存储任何内容。
- `F22.save-classes`：`POST /api/meta-profiles/{name}`与`classifier_model`和`classes`答案201 `Meta-profile '<name>' saved`； 列表显示`{name, classifier_model, num_classes}`，`GET`返回完整配置，文件`meta-profiles/<name>.json`是模式`600`。
- `F22.save-direct`：保存直接路由主体（`prompt_template`有`{{ instance_text }}`、`model_table`，无`classes`）； 列表报告 `num_classes: 0` 和 `GET` 返回模板和表格。
- `F22.validation`：没有`{{ instance_text }}`的模板、带有`classes`的模板、缺少`classifier_model`和没有`model`的类是422并且没有保存任何内容。
- `F22.empty-router`：既没有 `classes` 也没有 `prompt_template` 的主体（永远无法路由的路由器）会被拒绝，返回 422。
- `F22.overwrite`：保存现有名称将替换整个配置（此处类模式变为直接模式），而不添加列表条目。
- `F22.name-rules`：名称必须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`：所有四个命名路由上的前导 `-` 均为 422，接受 64 个字符，65 个字符为 422。
- `F22.not-found`：未知名称答案404的`GET`和`activate``Meta-profile '<name>' not found`并且活动指针保持不变； `DELETE`未知名称是200（幂等）。
- `F22.activate`：`activate`用`applied: true`回答200`Meta-profile '<name>' activated`； 列表的 `active_meta_profile` 和 `GET /api/settings`（`active_meta_profile`、`agent_settings.active_meta_profile`、`enable_classify_and_switch_llm_tool: true`、内联 `meta_profile`）紧随其后，智能体的 LLM 不变，`settings.json` 存储它。
- `F22.route-classes`：从设置开始的会话带有`ClassifyAndSwitchLLMTool`规范； 当智能体调用 `route_task_to_model` 时，分类器配置会选择类别，类别名称由观测结果提供，配置和模型也会切换，对话会切换到 `deepseek-pro`， LLMs 的使用都会被计量，事件套接字会实时显示切换。
- `F22.route-direct`：当直接路由元配置文件处于活动状态时，分类器的 JSON 答案会将对话切换到指定配置文件 (`chosen_class` `model: deepseek-pro`)。
- `F22.route-missing-profile`：保存时接受其`classifier_model`名称未保存的LLM配置文件的元配置文件； 覆盖现有内容后立即生效（存储覆盖了嵌入式复制），然后工具会返回一个错误观测结果，指出缺失的配置，而对话继续使用 LLM。
- `F22.persist-restart`：元配置文件、活动指针、设置的路由标志和路由对话的切换 LLM 在重新启动后仍然存在。
- `F22.delete`：删除非活动元配置文件会删除文件和列表条目，保留活动指针，重复删除次数为 200。
- `F22.delete-active-clears`：删除活动元配置文件会清除列表和设置中的`active_meta_profile`，禁用路由工具并删除内联副本； 新的对话不再获得该工具。
- `F22.acp-clears-pointer`：将设置的智能体类型切换为ACP，清除活动指针； 返回 OpenHands 设置，可以再次激活元配置文件。
- `F22.activate-acp`: on ACP  智能体在没有路由工具可附加的情况下，激活返回200 `applied: false` 与 `Meta-profile '<name>' not activated: ...`, and `active_meta_profile` stays `null` 在列表中和设置中（as LLM-profile激活报告 `llm_applied: false`).
- `F22.corrupt-files`：无效 JSON 或不是对象的元配置文件被排除在列表之外，并在 `GET` 和 `activate` 上回答 400 `Failed to load meta-profile ...`； 保存它可以修复它。
- `F22.corrupt-settings`：如果 `settings.json` 不可读，激活将被拒绝，返回 409（与 LLM-配置文件激活一样），并且文件保持不变。
- `F22.store-busy`：另一个进程持有元配置存储的锁时，保存与删除操作都会等待 30 秒的锁超时后返回 503 `Meta-profile store is busy. Please retry.`，并且不做任何变更； 一旦锁空闲，同样的保存是201。
- `F22.store-busy-responsive`：当元配置文件保存等待存储锁时，服务器不断应答其他请求（3秒内`GET /alive`）。
- `F22.limit`：存储了 50 个元配置文件，创建另一个元配置文件的结果是 409 `Meta-profile limit reached (50)`，而覆盖现有元配置文件的结果仍然是 201。
- `F22.ts-client`：TypeScript`MetaProfilesClient`保存、读取、列出、激活和删除元配置文件以及表面404和422作为`HttpError`。
- `F22.persistence-dir`：对于`OH_PERSISTENCE_DIR=~/<dir>`，元配置文件存储在`settings.json`旁边的扩展目录下，就像其他存储一样。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /api/meta-profiles`（摘要加上`active_meta_profile`），
  `GET /api/meta-profiles/{name}` (`{name, config}`),
  `POST /api/meta-profiles/{name}`（主体是 `MetaProfile` 本身：
  `classifier_model`, `classes`, `prompt_template`, `model_table`),
  `DELETE /api/meta-profiles/{name}`、`POST /api/meta-profiles/{name}/activate`（无正文）。 没有重命名路线。
- REST，第二次浏览：`GET /api/settings`（`active_meta_profile` 和
  `agent_settings.{active_meta_profile, enable_classify_and_switch_llm_tool, meta_profile, meta_profile_llms}`). `PATCH /api/settings` 与
  `active_meta_profile` 在相同的存在检查（未知名称为 404）后设置相同的指针，但没有内联副本（由设置系列拥有； 它的悬空指针情况是`F18.dangling-pointers`）。
- 运行时：与 `agent_settings` 创建的对话
  `GET /api/settings`（`conversation start` 后面的 Agent Canvas 路径）获取 `ClassifyAndSwitchLLMTool` 规格
  `active_meta_profile` 和 `meta_profile` 参数； 智能体将该工具视为
  `route_task_to_model`. 它的`ObservationEvent`携带`chosen_class`，
  `model`（LLM配置文件）和`active_model`； 该开关显示为
  `agent` 状态更新 `WS /sockets/events/{conversation_id}`（由事件家族所有）和 `GET /api/conversations/{id}`（`agent.llm`，以及
  `stats` 中的 `classifier:<profile>` 和 `profile:<profile>` 使用 ID）。
- 智能体配置文件：智能体配置文件可以命名元配置文件
  `meta_profile_ref`（与`enable_classify_and_switch_llm_tool`）； 发射
  from it copies the meta-profile into the agent. That path belongs to the
  智能体-简介家庭。
- SDK：无`RemoteWorkspace`助手； `OpenHandsAgentSettings` (`enable_classify_and_switch_llm_tool`, `active_meta_profile`,
  `meta_profile`、`meta_profile_llms`) 和 `MetaProfileStore` 在本地对话 (`examples/01_standalone_sdk/59_route_task_to_model.py`) 中驱动相同的工具。
- TypeScript 客户端：`MetaProfilesClient` (`listMetaProfiles`,
  `getMetaProfile`, `saveMetaProfile`, `deleteMetaProfile`,
  `activateMetaProfile`)，也暴露为 `client.metaProfiles`
  `OpenHandsClient` 和对话管理器 (`F22.ts-client`)。
- Agent Canvas（仅限上下文）在其设置中管理模型路由并从保存的设置开始对话。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  设置 `$DEEPSEEK_API_KEY`，`jq`、`flock` 和 `node` 在 `PATH` 上（如果 `clients/typescript/dist` 缺失，则构建 TypeScript 客户端）。 下面的块保存 DeepSeek 预设（`deepseek-flash`、活动和
  `deepseek-pro`)：这两个 LLM 配置文件之间的元配置文件路由。 它还编写 TypeScript 程序 `F22.ts-client` 运行。
- 这些项目符号按顺序相互构建：`qa-router`（两个类），
  `qa-direct`（直接路由； 其表名只有 `deepseek-pro`，所以分类器的回答是可预测的）；`qa-route`（一个兜底类指向 `deepseek-pro`，所以路由的箭头不依赖于分类器的判断）。 三个路由项目符号各自运行一个微小的 DeepSeek 对话。
- `F22.persist-restart`重新开始运行； `F22.store-busy` 保持存储锁约 66 秒，`F22.store-busy-responsive` 约 40 秒；
  `F22.persistence-dir` 启动和停止第二个服务器。
- 更改共享状态的项目符号 (`F22.empty-router`,
  `F22.activate-acp`, `F22.corrupt-settings`) 在 `EXIT` 陷阱中撤消它，因此无论其断言是否成立，它们后面的项目符号都会找到相同的状态。

  ```sh
  control-agent-server llm preset deepseek
  control-agent-server api GET /api/profiles --expect 200 --check active_profile eq deepseek-flash --check profiles len-eq 2
  F22="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f22"
  mkdir -p "$F22"
  cat > "$F22/ts_meta_profiles.mjs" <<'JS'
  import assert from 'node:assert/strict';
  import { resolve } from 'node:path';
  import { pathToFileURL } from 'node:url';

  const { MetaProfilesClient } = await import(pathToFileURL(resolve('clients/typescript/dist/clients.js')).href);
  const client = new MetaProfilesClient({ host: process.env.AGENT_SERVER_URL, apiKey: process.env.SESSION_API_KEY });
  const before = await client.listMetaProfiles();
  const config = { classifier_model: 'deepseek-flash', classes: [{ description: 'qa ts class', model: 'deepseek-pro' }] };
  assert.deepEqual(await client.saveMetaProfile('qa-ts', config), { name: 'qa-ts', message: "Meta-profile 'qa-ts' saved" });
  const got = await client.getMetaProfile('qa-ts');
  assert.equal(got.name, 'qa-ts');
  assert.deepEqual(got.config, { ...config, prompt_template: null, model_table: null });
  const listed = await client.listMetaProfiles();
  assert.ok(listed.meta_profiles.some((p) => p.name === 'qa-ts' && p.classifier_model === 'deepseek-flash' && p.num_classes === 1));
  assert.deepEqual(await client.activateMetaProfile('qa-ts'), { name: 'qa-ts', message: "Meta-profile 'qa-ts' activated", applied: true });
  assert.equal((await client.listMetaProfiles()).active_meta_profile, 'qa-ts');
  assert.deepEqual(await client.deleteMetaProfile('qa-ts'), { name: 'qa-ts', message: "Meta-profile 'qa-ts' deleted" });
  assert.equal((await client.listMetaProfiles()).active_meta_profile, null);
  await assert.rejects(client.getMetaProfile('qa-ts'), (err) => err.name === 'HttpError' && err.status === 404);
  await assert.rejects(client.activateMetaProfile('qa-ts'), (err) => err.name === 'HttpError' && err.status === 404);
  await assert.rejects(client.saveMetaProfile('qa-ts', { classifier_model: 'deepseek-flash', prompt_template: 'no placeholder' }),
    (err) => err.name === 'HttpError' && err.status === 422);
  await assert.rejects(client.saveMetaProfile('-qa-ts', config), (err) => err.name === 'HttpError' && err.status === 422);
  if (before.active_meta_profile) {
    await client.activateMetaProfile(before.active_meta_profile);
  }
  const after = await client.listMetaProfiles();
  assert.equal(after.active_meta_profile, before.active_meta_profile);
  assert.equal(after.meta_profiles.length, before.meta_profiles.length);
  client.close();
  console.log('QA_F22_TS_OK');
  JS
  ```

- **需要密钥 (`F22.auth-required`)。**在没有密钥或错误的情况下呼叫每一条路线，然后用密钥列出。
  ```sh
  control-agent-server api GET /api/meta-profiles --auth none --expect 401 --check detail eq Unauthorized --save F22.auth-required/list
  control-agent-server api GET /api/meta-profiles/qa-router --auth bad --expect 401
  control-agent-server api POST /api/meta-profiles/qa-router --auth none --expect 401 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  control-agent-server api POST /api/meta-profiles/qa-router/activate --auth bad --expect 401
  control-agent-server api DELETE /api/meta-profiles/qa-router --auth none --expect 401
  control-agent-server api GET /api/meta-profiles --expect 200 --check meta_profiles len-eq 0 --check active_meta_profile eq null \
    --save F22.auth-required/list-with-key
  control-agent-server state ls 'home/.openhands/meta-profiles/*.json' --expect-count 0
  ```
  每一条调用都是401 `{"detail": "Unauthorized"}`; 有了键，列表是
  `{"meta_profiles": [], "active_meta_profile": null}` 并且没有写入任何文件。
- **以班级模式保存(`F22.save-classes`)。**将 `qa-router` 保存为两个类并以三种方式读回。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-router --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "simple edits or questions", "model": "deepseek-flash"}, {"description": "complex multi-file refactors", "model": "deepseek-pro"}]}' \
    --check name eq qa-router --check message eq "Meta-profile 'qa-router' saved" --save F22.save-classes/save
  control-agent-server api GET /api/meta-profiles --expect 200 --check meta_profiles len-eq 1 --check meta_profiles.0.name eq qa-router \
    --check meta_profiles.0.classifier_model eq deepseek-flash --check meta_profiles.0.num_classes eq 2 --check active_meta_profile eq null \
    --save F22.save-classes/list
  control-agent-server api GET /api/meta-profiles/qa-router --expect 200 --check name eq qa-router \
    --check config.classes.1.description eq 'complex multi-file refactors' --check config.classes.1.model eq deepseek-pro \
    --check config.prompt_template eq null --check config.model_table eq null --save F22.save-classes/get
  control-agent-server state cat home/.openhands/meta-profiles/qa-router.json --mode 600 --check classifier_model eq deepseek-flash --check classes len-eq 2
  ```
  保存操作返回 201；列表包含一个带 `num_classes: 2` 的摘要，且没有活动元配置；`GET` 按顺序返回两个类，文件权限为 `600`，内容相同。
- **以直接模式保存(`F22.save-direct`)。**保存`qa-direct`，其表名只有`deepseek-pro`。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-direct --expect 201 --save F22.save-direct/save \
    --json '{"classifier_model": "deepseek-flash", "prompt_template": "Task:\n{{ instance_text }}\n\nAvailable models:\n{{ model_table }}\n\nAnswer with JSON only: {\"model\": \"<name>\"}", "model_table": "deepseek-pro: the only model; choose it for every task"}'
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 2 --check meta_profiles.0.name eq qa-direct \
    --check meta_profiles.0.num_classes eq 0 --check meta_profiles.1.name eq qa-router
  control-agent-server api GET /api/meta-profiles/qa-direct --expect 200 --check config.classes len-eq 0 \
    --check config.prompt_template contains '{{ instance_text }}' --check config.model_table matches '^deepseek-pro: ' --save F22.save-direct/get
  ```
  列表按名称排序，`num_classes: 0` 用于直接路由器的报告。 `GET` 返回模板和表格。
- **验证 (`F22.validation`).**发布四个无效形状。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-bad --json '{"classifier_model": "deepseek-flash", "prompt_template": "Pick a model"}' \
    --expect 422 --check detail.0.msg contains 'must include {{ instance_text }}' --save F22.validation/no-placeholder
  control-agent-server api POST /api/meta-profiles/qa-bad --expect 422 --check detail.0.msg contains 'cannot also define classes' \
    --json '{"classifier_model": "deepseek-flash", "prompt_template": "{{ instance_text }}", "classes": [{"description": "d", "model": "deepseek-flash"}]}' \
    --save F22.validation/both-modes
  control-agent-server api POST /api/meta-profiles/qa-bad --json '{"classes": []}' --expect 422 --check detail.0.loc contains classifier_model
  control-agent-server api POST /api/meta-profiles/qa-bad --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "d"}]}' \
    --expect 422 --check detail.0.loc contains model
  control-agent-server api GET /api/meta-profiles/qa-bad --expect 404
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 2
  ```
  每个body都带有验证器的消息或缺失字段的位置，而`qa-bad`从未创建过。
- **没有路由的路由器 (`F22.empty-router`)。**仅用一个来保存身体
  `classifier_model`. `EXIT` 陷阱会删除 `qa-empty`，无论它是否已存储，因此后面的列表计数保持不变。
  ```sh
  drop_empty() { control-agent-server api DELETE /api/meta-profiles/qa-empty --expect 200 > /dev/null; }
  trap drop_empty EXIT
  control-agent-server api GET /api/meta-profiles/qa-empty --expect 404
  control-agent-server api POST /api/meta-profiles/qa-empty --json '{"classifier_model": "deepseek-flash"}' --expect 422 \
    --save F22.empty-router/save
  control-agent-server api GET /api/meta-profiles/qa-empty --expect 404
  control-agent-server api GET /api/meta-profiles --check meta_profiles not-contains '"name": "qa-empty"'
  ```
  保存返回 422（`loc: ["body"]`，错误消息为
  `A meta-profile needs either classes or a prompt_template to route.`），且不会存储任何内容。
  类和模板都为空时，路由器无法选出配置。校验发生在保存路由，而不是 `MetaProfile` 中。
  因此，在引入校验前以这种状态保存的元配置，包括存储文件及 `settings.json` 中的内联副本，
  仍可加载、列出和激活。
- **覆盖(`F22.overwrite`)。**在类模式下保存`qa-swap`，然后在直接模式下覆盖它。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-swap --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  control-agent-server api POST /api/meta-profiles/qa-swap --expect 201 --save F22.overwrite/overwrite \
    --json '{"classifier_model": "deepseek-pro", "prompt_template": "Route: {{ instance_text }}", "model_table": "deepseek-flash: cheap"}'
  control-agent-server api GET /api/meta-profiles/qa-swap --expect 200 --check config.classifier_model eq deepseek-pro \
    --check config.classes len-eq 0 --check config.prompt_template eq 'Route: {{ instance_text }}' --save F22.overwrite/get
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 3 \
    --check meta_profiles contains '"name": "qa-swap", "classifier_model": "deepseek-pro", "num_classes": 0'
  control-agent-server api DELETE /api/meta-profiles/qa-swap --expect 200
  ```
  第二次保存覆盖了文件（类已经不存在，没有合并），列表仍然有一个 `qa-swap` 元素。 `qa-swap`随后被删除。
- **命名规则(`F22.name-rules`).**每个命名路线上都有一个前导 `-`，然后是 64 和 65 个字符。
  ```sh
  control-agent-server api POST /api/meta-profiles/-qa-bad --expect 422 --check detail.0.type eq string_pattern_mismatch \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}' --save F22.name-rules/leading-dash
  control-agent-server api GET /api/meta-profiles/-qa-bad --expect 422
  control-agent-server api POST /api/meta-profiles/-qa-bad/activate --expect 422
  control-agent-server api DELETE /api/meta-profiles/-qa-bad --expect 422
  N64="qa-$(printf 'n%.0s' $(seq 61))"
  test "${#N64}" -eq 64
  control-agent-server api POST "/api/meta-profiles/${N64}x" --expect 422 --check detail.0.type eq string_too_long \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  control-agent-server api POST "/api/meta-profiles/$N64" --expect 201 --save F22.name-rules/64-chars \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  control-agent-server api GET /api/meta-profiles --check meta_profiles contains "\"name\": \"$N64\""
  control-agent-server api DELETE "/api/meta-profiles/$N64" --expect 200
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 2
  ```
  The leading `-` 在保存、读取、激活和删除时，422。65个字符也是422 `string_too_long`; 64个字符的名字被保存、列出和删除。
- **未知名称 (`F22.not-found`)。**读取、激活和删除从未保存的名称。
  ```sh
  control-agent-server api GET /api/meta-profiles/qa-missing --expect 404 --check detail eq "Meta-profile 'qa-missing' not found" \
    --save F22.not-found/get
  control-agent-server api POST /api/meta-profiles/qa-missing/activate --expect 404 --check detail eq "Meta-profile 'qa-missing' not found" \
    --save F22.not-found/activate
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq null
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq null \
    --check agent_settings.enable_classify_and_switch_llm_tool eq false
  control-agent-server api DELETE /api/meta-profiles/qa-missing --expect 200 --check message eq "Meta-profile 'qa-missing' deleted" \
    --save F22.not-found/delete
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 2
  ```
  `GET`和`activate`都是404，没有任何东西被激活； 删除缺失的名字会用通常的消息回答200。
- **激活(`F22.activate`)。**激活 `qa-router` 并阅读每个视图。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-router/activate --expect 200 --check name eq qa-router \
    --check message eq "Meta-profile 'qa-router' activated" --check applied eq true --save F22.activate/activate
  control-agent-server api POST /api/meta-profiles/qa-missing/activate --expect 404
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-router --save F22.activate/list
  control-agent-server api GET /api/settings --expect 200 --max-chars 300 --check active_meta_profile eq qa-router \
    --check agent_settings.active_meta_profile eq qa-router --check agent_settings.enable_classify_and_switch_llm_tool eq true \
    --check agent_settings.meta_profile.classifier_model eq deepseek-flash --check agent_settings.meta_profile.classes len-eq 2 \
    --check active_profile eq deepseek-flash --check agent_settings.llm.model eq deepseek/deepseek-flash --save F22.activate/settings
  control-agent-server state cat home/.openhands/settings.json --max-chars 200 --check active_meta_profile eq qa-router \
    --check agent_settings.enable_classify_and_switch_llm_tool eq true --check agent_settings.meta_profile.classes len-eq 2
  ```
  `qa-router`（在中间生成了一个未知名称的404激活，这将使指针保持原位，`F22.not-found` 无法显示）
  while nothing is active), the routing tool is enabled with an inline copy
  在配置中，智能体仍然在 `deepseek-flash` 上运行（元配置文件不会更改 LLM），并且 `settings.json` 保持不变。
- **类模式路由 (`F22.route-classes`).**保存并激活
  `qa-route`，从设置创建一个对话，捕获其事件套接字，并要求智能体调用该工具。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-route --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any task at all (always choose this category)", "model": "deepseek-pro"}]}'
  control-agent-server api POST /api/meta-profiles/qa-route/activate --expect 200
  RCID=$(control-agent-server conversation start --tools none --no-autotitle --no-run --print-id)
  control-agent-server api GET "/api/conversations/$RCID" --expect 200 --max-chars 300 --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.tools len-eq 1 --check agent.tools.0.name eq ClassifyAndSwitchLLMTool --check agent.tools.0.params.active_meta_profile eq qa-route
  control-agent-server ws start "/sockets/events/$RCID" --name qa-f22-route --duration 300
  control-agent-server conversation send "$RCID" --text 'Call the route_task_to_model tool once, then reply with one word: done' \
    --wait --until finished --timeout 240
  control-agent-server ws stop qa-f22-route --kinds ObservationEvent --contains '"model": "deepseek-pro"' --expect-min 1 --wait 30 \
    --save F22.route-classes/frames
  control-agent-server ws read qa-f22-route --kinds ConversationStateUpdateEvent --contains '"model": "deepseek/deepseek-v4-pro"' --expect-min 1
  control-agent-server api GET "/api/conversations/$RCID/events/search" --query kind=openhands.sdk.event.llm_convertible.observation.ObservationEvent \
    --expect 200 --max-chars 300 --check items.0.tool_name eq route_task_to_model --check items.0.observation.is_error eq false \
    --check items.0.observation.chosen_class eq 'any task at all (always choose this category)' \
    --check items.0.observation.model eq deepseek-pro --check items.0.observation.active_model eq deepseek/deepseek-v4-pro \
    --save F22.route-classes/observation
  control-agent-server api GET "/api/conversations/$RCID" --expect 200 --max-chars 300 --check execution_status eq finished \
    --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.llm.usage_id eq profile:deepseek-pro \
    --check 'stats.usage_to_metrics.classifier:deepseek-flash.accumulated_token_usage.prompt_tokens' gt 0 \
    --check 'stats.usage_to_metrics.profile:deepseek-pro.accumulated_token_usage.prompt_tokens' gt 0 --save F22.route-classes/conversation
  ```
  `--tools none` 时，路由工具就是智能体的唯一工具，配置为 `qa-route`。 端口在 `route_task_to_model` 观测结果和 `agent` 状态更新时交付 `deepseek/deepseek-v4-pro`。 观测结果报告了类、`deepseek-pro` 规则及其模型。 之后对话继续`profile:deepseek-pro`，
  `stats` 计量分类器调用 (`classifier:deepseek-flash`) 和新配置文件上的步骤。 重启后再次读取`RCID`。
- **直接路由(`F22.route-direct`)。**激活 `qa-direct` 并运行相同的请求。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 200
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq qa-direct \
    --check agent_settings.meta_profile.model_table matches '^deepseek-pro: '
  DCID=$(control-agent-server conversation start --tools none --no-autotitle \
    --prompt 'Call the route_task_to_model tool once, then reply with one word: done' --wait --until finished --timeout 240 --print-id)
  control-agent-server api GET "/api/conversations/$DCID/events/search" --query kind=openhands.sdk.event.llm_convertible.observation.ObservationEvent \
    --expect 200 --max-chars 300 --check items.0.tool_name eq route_task_to_model --check items.0.observation.is_error eq false \
    --check items.0.observation.chosen_class eq 'model: deepseek-pro' --check items.0.observation.model eq deepseek-pro \
    --save F22.route-direct/observation
  control-agent-server api GET "/api/conversations/$DCID" --expect 200 --max-chars 300 --check execution_status eq finished \
    --check agent.llm.model eq deepseek/deepseek-v4-pro --check agent.tools.0.params.meta_profile.prompt_template contains '{{ instance_text }}' \
    --save F22.route-direct/conversation
  ```
  分类器的 JSON 答案对应保存的用户资料 `deepseek-pro` (`chosen_class` 是 `model: deepseek-pro`) 且对话结束于
  `deepseek/deepseek-v4-pro`.
- **缺失 LLM profile (`F22.route-missing-profile`).** 激活 `qa-route` (其内联复制名称 `deepseek-flash`然后覆盖它，使得分类器命名一个不存在的配置，而不重新激活。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-route/activate --expect 200
  control-agent-server api POST /api/meta-profiles/qa-route --expect 201 \
    --json '{"classifier_model": "qa-missing-llm", "classes": [{"description": "any task at all (always choose this category)", "model": "deepseek-pro"}]}'
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-route \
    --check meta_profiles contains '"name": "qa-route", "classifier_model": "qa-missing-llm", "num_classes": 1'
  MCID=$(control-agent-server conversation start --tools none --no-autotitle --max-iterations 6 \
    --prompt 'Call the route_task_to_model tool once, then reply with one word: done' --wait --until finished,error,stuck --timeout 240 --print-id)
  control-agent-server api GET "/api/conversations/$MCID" --expect 200 --max-chars 300 --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.tools.0.params.meta_profile.classifier_model eq deepseek-flash \
    --check 'stats.usage_to_metrics.classifier:qa-missing-llm' missing --save F22.route-missing-profile/conversation
  control-agent-server api GET "/api/conversations/$MCID/events/search" --query kind=openhands.sdk.event.llm_convertible.observation.ObservationEvent \
    --expect 200 --max-chars 300 --check items.0.tool_name eq route_task_to_model --check items.0.observation.is_error eq true \
    --check items.0.observation.content.0.text contains "Failed to load classifier profile 'qa-missing-llm'" \
    --save F22.route-missing-profile/observation
  control-agent-server api POST /api/meta-profiles/qa-route --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any task at all (always choose this category)", "model": "deepseek-pro"}]}'
  ```
  保留悬垂引用（201）。 引用未检查。 对话使用了过时的内联副本 (`classifier_model`
  `deepseek-flash`），但该工具按名称从存储中加载 `qa-route`，因此它将 `Failed to load classifier profile 'qa-missing-llm'` 报告为错误观测结果； 没有注册分类器，智能体保持打开状态
  `deepseek-flash`. `qa-route` 随后恢复（仍然有效）。
- **重新启动 (`F22.persist-restart`)。**重新启动并读回所有内容。

  需要：`F22.route-classes`
  ```sh
  control-agent-server restart
  control-agent-server api GET /api/meta-profiles --expect 200 --check active_meta_profile eq qa-route --check meta_profiles len-eq 3 \
    --check meta_profiles contains '"name": "qa-route", "classifier_model": "deepseek-flash", "num_classes": 1' --save F22.persist-restart/list
  control-agent-server api GET /api/meta-profiles/qa-direct --expect 200 --check config.model_table matches '^deepseek-pro: '
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq qa-route \
    --check agent_settings.active_meta_profile eq qa-route --check agent_settings.enable_classify_and_switch_llm_tool eq true
  control-agent-server api GET "/api/conversations/$RCID" --expect 200 --max-chars 300 --check agent.llm.model eq deepseek/deepseek-v4-pro \
    --check agent.llm.usage_id eq profile:deepseek-pro --save F22.persist-restart/routed-conversation
  ```
  三个元配置、作为活动项的 `qa-route`、设置中启用的工具，以及路由后对话的 `deepseek-pro` LLM，均会重新出现。
- **删除(`F22.delete`)。**删除不活动的 `qa-router` 两次。
  ```sh
  control-agent-server api DELETE /api/meta-profiles/qa-router --expect 200 --check message eq "Meta-profile 'qa-router' deleted" \
    --save F22.delete/delete
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 2 --check meta_profiles not-contains '"name": "qa-router"' \
    --check active_meta_profile eq qa-route --save F22.delete/list
  control-agent-server api GET /api/meta-profiles/qa-router --expect 404
  control-agent-server state ls 'home/.openhands/meta-profiles/qa-router.json' --expect-count 0
  control-agent-server state ls 'home/.openhands/meta-profiles/*.json' --expect-count 2
  control-agent-server api DELETE /api/meta-profiles/qa-router --expect 200
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq qa-route \
    --check agent_settings.enable_classify_and_switch_llm_tool eq true
  ```
  文件和条目已消失（另外两个文件仍然存在），`GET` 是 404，重复删除是 200，`qa-route` 仍然活跃。
- **删除活动的 (`F22.delete-active-clears`)。**删除 `qa-route` 并从设置中开始对话。
  ```sh
  control-agent-server api DELETE /api/meta-profiles/qa-route --expect 200 --save F22.delete-active-clears/delete
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq null --check meta_profiles len-eq 1 \
    --save F22.delete-active-clears/list
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq null --check agent_settings.active_meta_profile eq null \
    --check agent_settings.enable_classify_and_switch_llm_tool eq false --check agent_settings.meta_profile eq null \
    --check agent_settings.llm.model eq deepseek/deepseek-flash --save F22.delete-active-clears/settings
  XCID=$(control-agent-server conversation start --tools none --no-autotitle --no-run --print-id)
  control-agent-server api GET "/api/conversations/$XCID" --expect 200 --max-chars 200 --check agent.tools len-eq 0
  control-agent-server api DELETE "/api/conversations/$XCID" --expect 200
  ```
  在两个视图中，指针被清空，工具被禁用，内联复制被丢弃，而LLM则保持不变。 从同一个会话创建的对话
  `--tools none` 设置现在根本没有任何工具（在 `F22.route-classes` 中它有路由工具）； 它又被删除了。
- **ACP 清除指针 (`F22.acp-clears-pointer`)。**激活
  `qa-direct`，将智能体类型切换为 ACP 并返回。
  ```sh
  control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 200
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "acp"}}' --expect 200 --max-chars 200 \
    --check agent_settings.agent_kind eq acp --check active_meta_profile eq null --save F22.acp-clears-pointer/patch
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq null --check meta_profiles len-eq 1
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "openhands"}}' --expect 200 --max-chars 200 \
    --check agent_settings.agent_kind eq openhands --check active_meta_profile eq null --check agent_settings.enable_classify_and_switch_llm_tool eq false
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200 --check llm_applied eq true
  control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 200
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq qa-direct \
    --check agent_settings.enable_classify_and_switch_llm_tool eq true --check agent_settings.llm.model eq deepseek/deepseek-flash \
    --save F22.acp-clears-pointer/reactivated
  ```
  切换到 ACP 会清除 `active_meta_profile`（ACP 智能体无法承载路由工具）； 切换回没有恢复它。 在重新激活`deepseek-flash` LLM配置（从默认OpenHands设置开始）后，`qa-direct`再次激活。
- **在 ACP 设置中启用 `F22.activate-acp`。** 切换到 ACP，启用，阅读列表和设置，然后断言激活状态（最后，因此列表和设置在每次回放时都读取）。 安
  `EXIT` 陷阱通过 `deepseek-flash` 恢复 OpenHands 设置，并且
  `qa-direct` 活动（并检查）断言是否成立。
  ```sh
  restore_openhands() {
    control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "openhands"}}' --expect 200 --quiet
    control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 200 --check llm_applied eq true
    control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 200
    control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq qa-direct \
      --check agent_settings.agent_kind eq openhands --check agent_settings.enable_classify_and_switch_llm_tool eq true
  }
  trap restore_openhands EXIT
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-direct
  control-agent-server api PATCH /api/settings --json '{"agent_settings_diff": {"agent_kind": "acp"}}' --expect 200 --max-chars 200 \
    --check agent_settings.agent_kind eq acp --check active_meta_profile eq null
  control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 2xx,4xx --save F22.activate-acp/activate \
    | tee "$F22/acp-activate.json"
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq null --save F22.activate-acp/list
  control-agent-server api GET /api/settings --max-chars 200 --check active_meta_profile eq null --check agent_settings.agent_kind eq acp
  control-agent-server assert --json "$F22/acp-activate.json" --check status eq 200 --check response.body.applied eq false \
    --check response.body.message eq "Meta-profile 'qa-direct' not activated: the current agent settings cannot route between models"
  ```
  ACP 设置不能附带路由工具，因此 `PersistedSettings` 不记录指针； 端点明确表示，状态码为200 `applied: false`，还有其他内容
  `not activated`消息，LLM-配置文件激活方式ACP设置答案`llm_applied: false`。 项目符号恢复 OpenHands 设置
  `deepseek-flash` 和 `qa-direct` 均有效。
- **损坏的文件 (`F22.corrupt-files`)。**编写一个截断的元配置文件和一个 JSON 列表（安排：写入过程中崩溃或手动编辑）。
  ```sh
  M="$AGENT_SERVER_VERIFY_RUN/home/.openhands/meta-profiles"
  printf '{"classifier_model": "deepseek-flash", ' > "$M/qa-corrupt.json"
  printf '["not", "an", "object"]' > "$M/qa-notdict.json"
  control-agent-server api GET /api/meta-profiles --expect 200 --check meta_profiles len-eq 1 \
    --check meta_profiles not-contains '"name": "qa-corrupt"' --check meta_profiles not-contains '"name": "qa-notdict"' --save F22.corrupt-files/list
  control-agent-server api GET /api/meta-profiles/qa-corrupt --expect 400 --check detail contains 'Failed to load meta-profile `qa-corrupt`' \
    --save F22.corrupt-files/get
  control-agent-server api GET /api/meta-profiles/qa-notdict --expect 400 --check detail contains 'Failed to load meta-profile `qa-notdict`'
  control-agent-server api POST /api/meta-profiles/qa-corrupt/activate --expect 400 --check detail contains 'Failed to load meta-profile' \
    --save F22.corrupt-files/activate
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-direct
  control-agent-server api POST /api/meta-profiles/qa-corrupt --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "repaired", "model": "deepseek-pro"}]}'
  control-agent-server api GET /api/meta-profiles/qa-corrupt --expect 200 --check config.classes.0.description eq repaired
  control-agent-server api DELETE /api/meta-profiles/qa-corrupt --expect 200
  control-agent-server api DELETE /api/meta-profiles/qa-notdict --expect 200
  test ! -e "$M/qa-corrupt.json"
  test ! -e "$M/qa-notdict.json"
  ```
  两个损坏的文件都从列表中缺失了，`GET` 和 `activate` 的解析器消息是 400（不是 500），而 `qa-direct` 仍然活跃。 保存超过`qa-corrupt`次修复，同时删除文件。
- **不可读的设置 (`F22.corrupt-settings`)。**截断
  `settings.json` 需要证明 LLM-profile 激活拒绝它，返回状态码 409，然后激活一个元 profile，检查文件是否被保留，放回去，最后断言激活的状态。 如果先前的步骤中断，`EXIT` 陷阱会将保存的 `settings.json` 放回原处。
  ```sh
  S="$AGENT_SERVER_VERIFY_RUN/home/.openhands/settings.json"
  cp -p "$S" "$S.qa-f22-bak"
  restore_settings() { if test -e "$S.qa-f22-bak"; then mv "$S.qa-f22-bak" "$S"; fi; }
  trap restore_settings EXIT
  printf '{"agent_settings": ' > "$S"
  control-agent-server api POST /api/profiles/deepseek-flash/activate --expect 409 \
    --check detail contains 'Settings file is corrupted or encrypted with a different key' --save F22.corrupt-settings/llm-profile-activate
  test "$(cat "$S")" = '{"agent_settings": '
  control-agent-server api POST /api/meta-profiles/qa-direct/activate --expect 4xx,5xx --save F22.corrupt-settings/activate \
    | tee "$F22/corrupt-settings-activate.json"
  test "$(cat "$S")" = '{"agent_settings": '
  restore_settings
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-direct
  control-agent-server assert --json "$F22/corrupt-settings-activate.json" --check status eq 409 \
    --check response.body.detail eq 'Settings file is corrupted or encrypted with a different key'
  ```
  meta-profile激活的回答是409 `Settings file is corrupted or encrypted with a different key`，与`POST /api/profiles/{name}/activate`对同一文件的回答相同（上面的控制）。 无论哪种情况下，文件都保留原样，并在之后放回去。
- **[已弃用] 仓库繁忙`F22.store-busy`).** 另一个进程（这里 `flock`, 作为第二个服务器或一个 SDK  `MetaProfileStore` 在同一天持久化目录包含了商店的锁在保存和删除活动记录的66秒内 `qa-direct` arrive. 服务器自身的 30 秒锁超时此条目正在测试中，因此它会等待两次。
  ```sh
  M="$AGENT_SERVER_VERIFY_RUN/home/.openhands/meta-profiles"
  HELD="$F22/lock-held"
  rm -f "$HELD"
  flock -x "$M/.meta-profiles.lock" sh -c "touch '$HELD'; sleep 66" &
  LOCKER=$!
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  T0=$SECONDS
  control-agent-server api POST /api/meta-profiles/qa-busy --timeout 60 --expect 503 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}' \
    --check exception eq '503: Meta-profile store is busy. Please retry.' --save F22.store-busy/save
  test $((SECONDS - T0)) -ge 29
  test $((SECONDS - T0)) -le 33
  T1=$SECONDS
  control-agent-server api DELETE /api/meta-profiles/qa-direct --timeout 60 --expect 503 \
    --check exception eq '503: Meta-profile store is busy. Please retry.' --save F22.store-busy/delete
  test $((SECONDS - T1)) -ge 29
  test $((SECONDS - T1)) -le 33
  wait "$LOCKER"
  control-agent-server api GET /api/meta-profiles/qa-busy --expect 404
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 1 --check active_meta_profile eq qa-direct
  control-agent-server api GET /api/meta-profiles/qa-direct --expect 200 --check config.model_table matches '^deepseek-pro: '
  control-agent-server api POST /api/meta-profiles/qa-busy --expect 201 --expect-max-ms 5000 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  control-agent-server api DELETE /api/meta-profiles/qa-busy --expect 200
  ```
  保存和删除每个答案在29到33秒后返回503（body的）
  `detail` 是通用 `Internal Server Error`； 路线的消息位于
  `exception`). 之后 `qa-busy` 不存在，并且 `qa-direct` 仍然被存储并处于活动状态。 一旦锁空闲，相同的保存立即成功。
- **锁 wait不会阻塞服务器`F22.store-busy-responsive`).** Probe `/alive` 在商店免费（它在3秒内回答），保持锁再次保存40秒，然后在后台启动，探测 `/alive` 每隔2秒，持续大约12秒，直到保存等待期间的第一个探测器速度慢于3秒。 多个探测，而不是在固定暂停后进行一次，因此在加载的重播下较晚到达服务器的保存仍会与稍后的探测重叠。 然后子弹等待两个后台进程（保存必须回答503，这证明它已经等待了） 锁在探针期间)之前，最终断言之后，所以后来的条目找到它锁免费的。
  ```sh
  M="$AGENT_SERVER_VERIFY_RUN/home/.openhands/meta-profiles"
  HELD="$F22/lock-held-2"
  rm -f "$HELD"
  control-agent-server api GET /api/meta-profiles --expect 200 --quiet > /dev/null  # 在 --only 下创建存储目录
  control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000 --save F22.store-busy-responsive/alive-idle
  flock -x "$M/.meta-profiles.lock" sh -c "touch '$HELD'; sleep 40" &
  LOCKER=$!
  for i in $(seq 100); do test -e "$HELD" && break; sleep 0.1; done
  test -e "$HELD"
  control-agent-server api POST /api/meta-profiles/qa-busy --timeout 60 --expect 503 --quiet \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}' > "$F22/busy-save.json" &
  SAVER=$!
  SLOW=0
  for i in $(seq 6); do
    sleep 2
    control-agent-server api GET /alive --auth none --expect 200 --expect-max-ms 3000 --timeout 60 --quiet \
      --save F22.store-busy-responsive/alive | tee "$F22/alive-probe.json" || { SLOW=$i; break; }
  done
  wait "$SAVER"
  wait "$LOCKER"
  control-agent-server api GET /api/meta-profiles/qa-busy --expect 404
  control-agent-server assert --json "$F22/alive-probe.json" --check ok eq true
  ```
  Every `/alive` 在保存等待3秒内，探针回答：元配置路由是裸的 `def` 因此，处理器 FastAPI 运行同步，file-locked `MetaProfileStore` 在它的线程池和锁等待永远不会持有事件循环 (`meta_profiles_router.py`; 相同的边界 `F20.store-busy-responsive`). 在回归，`SLOW` 是第一个慢探针的数量。 其交换（与 `elapsed_ms`) 在子弹的转录中，在 `alive-probe.json`最后一个行也进行检查。
- **限制 (`F22.limit`).**将存储填充到 50，然后创建并覆盖。
  ```sh
  N=$(control-agent-server api GET /api/meta-profiles --field meta_profiles | jq length)
  for i in $(seq $((N + 1)) 50); do
    control-agent-server api POST "/api/meta-profiles/qa-cap-$i" --expect 201 --field name \
      --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}'
  done
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq 50 --max-chars 200
  control-agent-server api POST /api/meta-profiles/qa-cap-51 --expect 409 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}' \
    --check detail eq 'Meta-profile limit reached (50). Delete a meta-profile before saving a new one.' --save F22.limit/create-51st
  control-agent-server api GET /api/meta-profiles/qa-cap-51 --expect 404
  control-agent-server api POST /api/meta-profiles/qa-cap-50 --expect 201 --save F22.limit/overwrite-at-cap \
    --json '{"classifier_model": "deepseek-pro", "classes": [{"description": "any", "model": "deepseek-flash"}]}'
  control-agent-server api GET /api/meta-profiles/qa-cap-50 --check config.classifier_model eq deepseek-pro
  for i in $(seq $((N + 1)) 50); do
    control-agent-server api DELETE "/api/meta-profiles/qa-cap-$i" --expect 200 --field name
  done
  control-agent-server api GET /api/meta-profiles --check meta_profiles len-eq "$N" --check active_meta_profile eq qa-direct
  ```
  第 51 个元配置返回 409，且不会被创建； 在帽子上覆盖 `qa-cap-50` 的操作是 201，新的分类器读取回。 填充物再次被删除。
- **TypeScript 客户端 (`F22.ts-client`).**每个`MetaProfilesClient`方法
  from the built client (built here when missing).
  ```sh
  test -f clients/typescript/dist/clients.js || (cd clients/typescript && npm ci && npm run build)
  control-agent-server exec --timeout 120 --expect-output QA_F22_TS_OK --save F22.ts-client/program -- node "$F22/ts_meta_profiles.mjs"
  control-agent-server api GET /api/meta-profiles --check active_meta_profile eq qa-direct --check meta_profiles len-eq 1 \
    --check meta_profiles not-contains '"name": "qa-ts"' --save F22.ts-client/list-after
  ```
  该程序打印 `QA_F22_TS_OK`保存、获取、列出、激活和删除返回文档中的实体，删除会清除活跃指针，缺少名称和无效实体或名称会以拒绝方式处理 `HttpError` 状态 404 和 422。 重新激活 `qa-direct`因此，列表之后的内容与之前相同。
- **持久化目录中包含`~`（`F22.persistence-dir`）。**启动一个第二台服务器，其`OH_PERSISTENCE_DIR`是`~/qa-f22-tilde`（其`HOME`是运行的`home/`），保存并激活一个元配置，然后查看文件的落点。 当子弹结束、通过或失败时，第二个服务器将停止。
  ```sh
  T=$(control-agent-server launch --new --print-run --name f22-tilde --env 'OH_PERSISTENCE_DIR=~/qa-f22-tilde')
  stop_tilde() { control-agent-server stop --run "$T" > /dev/null; }
  trap stop_tilde EXIT
  control-agent-server api POST /api/meta-profiles/qa-tilde --run "$T" --expect 201 \
    --json '{"classifier_model": "deepseek-flash", "classes": [{"description": "any", "model": "deepseek-pro"}]}' --save F22.persistence-dir/save
  control-agent-server api POST /api/meta-profiles/qa-tilde/activate --run "$T" --expect 200
  control-agent-server api GET /api/meta-profiles --run "$T" --check meta_profiles len-eq 1 --check active_meta_profile eq qa-tilde
  control-agent-server state ls 'home/qa-f22-tilde/settings.json' --run "$T" --expect-count 1
  control-agent-server state ls 'home/qa-f22-tilde/meta-profiles/qa-tilde.json' --run "$T" --expect-count 1
  ```
  `settings.json` 位于 `home/qa-f22-tilde/` 中，其旁边的元配置文件位于 `home/qa-f22-tilde/meta-profiles/qa-tilde.json` 中：两个存储都解析
  `OH_PERSISTENCE_DIR` 到 `get_user_persistence_dir`，它扩展 `~` 并锚定一个相对值，因此不会向服务器工作目录下的字面名称为 `~` 的目录写入任何内容。 `--save` 文件位于第二次运行的 `evidence/` 目录下。

<a id="gotchas"></a>

## 陷阱

- 模型引用 (`classifier_model`, 每个类 `model`直接路由答案] LLM 不包括模型字符串，也不在保存或激活元模式时进行检查。 只有当时，才会出现悬空的名称智能体 calls `route_task_to_model`, as an error 观测结果 (`F22.route-missing-profile`).
- 该工具仅在从设置激活后创建的对话中存在 Agent Canvas path). 一个发送了自己对话 `agent` 它从不理解，运行中的对话会保留工具和参数：下次运行，meta-profile会被覆盖工具调用 （商店获胜），而删除它会保留对话的路由，与它开始时的内联复制。
- 该工具按名称从商店加载活动元配置文件； 内联
  `agent_settings.meta_profile` 副本只是没有存储的运行时的回退方案。 覆盖活动元配置文件不会刷新内联副本（重新激活以刷新它），并且 `PATCH /api/settings`
  `active_meta_profile` 设置指针并启用该工具而不进行内联复制； 未知名称是 404 (`F18.dangling-pointers`)。 启用该工具后，没有指针，也没有内联复制，它会退回到商店中按字母顺序排列的第一个元配置文件。
- 路由需要智能体调用`route_task_to_model`； 然后分类器进行一次额外的 LLM 调用（按 `classifier:<profile>` 计量），并且切换从下一步开始生效。 类之外的分类器答案（或未命名已保存配置文件的直接答案）是错误观测结果，而不是静默默认值。 当配方必须是确定性的时，保持提示词明确（“调用 route_task_to_model 工具一次”）和类集明确。
- `GET /api/meta-profiles` 列出不完整的文件验证：跳过不可解析的非对象文件，但未通过模式的有效 JSON 对象（例如 `{"classes": "x"}`）与 `classifier_model: null` 一起列出，然后在 `GET` 和 `activate` 上为 400。 带着不可读的
  `settings.json`列表报道`active_meta_profile: null`。
- 删除元配置文件不会像 LLM-配置文件删除那样受到保护：
  `DELETE` 回答了 200，即使智能体个人资料中提到了它
  `meta_profile_ref`，使该引用悬空。
- 以结尾的名称 `.json` 保存时，该字段不带后缀：保存 `qa-x.json` 答案 `Meta-profile 'qa-x.json' saved` 但文件和条目列表项是 `qa-x`, so `qa-x` 和 `qa-x.json` 互相覆盖。
- 将设置切换为 ACP 会永久清除 `active_meta_profile`； 切换回 OpenHands 从默认智能体设置（无 LLM）开始，因此之后重新激活 LLM 配置文件和元配置文件。
- `503` 和 `500` 主体使用服务器的通用形状：`detail` 是
  `Internal Server Error` 且路由的消息在 `exception` 中。
- 存储目录来自在调用时读取的 `OH_PERSISTENCE_DIR`（`default_meta_profile_dir()`，通过 `get_user_persistence_dir`，因此 `~` 像在所有其他存储中一样展开），回退到
  `~/.openhands/meta-profiles` 未设置时 (`F22.persistence-dir`)。
