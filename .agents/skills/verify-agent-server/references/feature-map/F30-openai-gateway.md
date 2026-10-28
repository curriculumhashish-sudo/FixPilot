<a id="openai-compatible-gateway-v1"></a>

# OpenAI 兼容网关 (/v1)

一个 OpenAI 形状的门， OpenAI 客户（官方 SDKs，或者任何其他）
else that takes a `base_url`) can talk to the agent server. It is not an LLM
代理。 每条聊天或回复请求都会启动一个完整的已持久化  OpenHands  智能体从活跃的会话（或继续一个会话）构建的智能体带有的 LLM of the named LLM 个人信息和保存的会话设置。 的智能体在服务器上运行的工作区使用自己的工具，网关等待运行结束，并返回智能体作为最终答案的 OpenAI object. 模型 id 是 `openhands_<llm-profile-name>`一个保存的配置文件对应一个。 会话密钥的作用是 `X-Session-API-Key` or as
`Authorization: Bearer`. `X-OpenHands-ServerConversation-ID` 响应标头命名每个答案后面的对话，并在聊天完成时将其发回以继续该对话。

资料来源：`openhands-agent-server/openhands/agent_server/openai/`、`openhands-agent-server/openhands/agent_server/api.py`、`openhands-agent-server/openhands/agent_server/agent_profiles_router.py`、`openhands-agent-server/openhands/agent_server/dependencies.py`、`openhands-sdk/openhands/sdk/llm/llm_profile_store.py`、`openhands-sdk/openhands/sdk/conversation/response_utils.py`、`examples/02_remote_agent_server/15_openai_compatible_gateway.py`

需求：`llm`、`tmux`

路线：`GET /v1/models`、`POST /v1/chat/completions`、`POST /v1/responses`

<a id="sub-features"></a>

## 子功能

- `F30.models-list`: `GET /v1/models` 为每个保存的 LLM 配置文件列出一个 `{"id": "openhands_<profile>", "object": "model", "created": 0, "owned_by": "openhands"}`，按 ID 排序，并立即重命名和删除配置文件。
- `F30.auth-bearer-or-header`：配置了会话密钥后，所有三个路由都接受密钥作为 `Authorization: Bearer` 或者作为 `X-Session-API-Key`，并在验证主体之前，对缺少或错误的密钥返回 401 `Unauthorized`。`/api/*` 仍然拒绝 Bearer。
- `F30.auth-open-without-keys`：没有会话密钥的服务器服务`/v1`，没有任何凭据并且具有任何承载值。
- `F30.chat-basic`: `POST /v1/chat/completions`在真实模型上返回一个 `chat.completion`，该单一选择承载着智能体的最终答案，同时 `finish_reason` `stop`，回显模型，报告使用情况，并命名一个新的完成对话 `X-OpenHands-ServerConversation-ID`。
- `F30.active-agent-profile`: 新的网关对话保留了活跃智能体会话的标识符、工具和系统后缀，仅在启动时覆盖其LLM，不改变存储的会话，拒绝超出大小的指令，返回400，以及在活跃会话删除后回退到默认值。
- `F30.chat-system-suffix`：`system` 和 `developer` 消息成为新对话的 `agent_context.system_message_suffix`（在系统提示词中），并且永远不会显示为用户消息。
- `F30.chat-latest-user-only`：新会话仅接收`messages[]`的最后一条用户消息； 较早的用户和助理轮流被丢弃并存储在任何地方。
- `F30.chat-stream`：`stream: true`答案`text/event-stream`以及对话标题和框架角色，全部内容，`finish_reason``stop`，用法（仅与`stream_options.include_usage`）和`[DONE]`； 失败的流式传输请求是一个普通的 JSON 错误，而不是 SSE 帧。
- `F30.chat-reuse-header`：发回 `X-OpenHands-ServerConversation-ID` 将新用户消息附加到该对话中，重新运行它（在其事件套接字上实时运行）并返回相同的 id。
- `F30.chat-reuse-after-restart`：服务器重新启动后，标头仍继续已持久化会话。
- `F30.chat-header-new-id`：标头中格式良好但未知的 id 创建与该 id 完全相同的对话； 格式错误的 id 是 422 并且不会创建任何内容。
- `F30.chat-reuse-keeps-llm`：在继续对话时，请求的模型仍需存在（否则返回404），但不被应用：对话保留自己的LLM和系统后缀，而其他模式的提供者从不被调用。
- `F30.chat-usage-per-request`：`usage` 在连续对话中报告请求的 token，而不是对话的运行总计（重现真正的错误）。
- `F30.chat-reuse-concurrent` 在同一个对话中，两个重叠的请求分别得到它们各自回合的答案（重现了一个真实 bug：第一个请求返回了第二个请求的答案）。
- `F30.chat-agent-tools`：智能体在服务器工作区中运行自己的工具（那里出现一个文件），答案不带`tool_calls`，客户端的`tools`/`tool_choice`被忽略。
- `F30.chat-input-errors`：输入错误的聊天内容在任何对话之前都会失败：400 无用户消息或内容部分错误，404 对于没有 `openhands_` 前缀的模型或未知的用户，400 对于无效的用户名称，422 对于模式错误。
- `F30.observability-headers`: `X-OpenHands-Observability-*` 标头存储在新对话（聊天和响应）中； 在运行之前，无效值为 422。
- `F30.chat-run-error-500`：以 `error` 结尾的运行使用重写的正文 (`exception` `500: Agent run ended with status: error`) 回答 500，不带对话标头，并将对话保留在 `error` 中。
- `F30.chat-confirmation-409`：设置中保存确认模式，停止`waiting_for_confirmation`的新对话立即回答409。
- `F30.chat-reuse-confirmation`：停止 `waiting_for_confirmation` 的持续对话也会在几秒钟内回复 409，就像新的对话一样。
- `F30.chat-run-limit-429`：当`max_concurrent_runs`已满时，新的网关对话将被拒绝并返回429，并且不会创建任何内容； 一旦插槽空闲，相同的请求就会成功。
- `F30.chat-reuse-run-limit-429`：在持续对话中，429 也不会留下任何内容，因此客户端重试是安全的。
- `F30.chat-timeout-504`：超过固定 120 秒的运行会回答 504 `Agent run timed out`，并且运行将继续在服务器端进行。
- `F30.responses-basic`: `POST /v1/responses` 在实际模型中返回一个完成的 `response`，包含一个 `output_text` 消息，等于智能体的最终答案，重复 `instructions` 和 `metadata`，并将指令放入系统后缀。
- `F30.responses-stateless-replay`：每个响应调用都是一个新对话（对话标头被忽略）； 重播的项目成为包含在 `<message role="...">` 标记中的一条用户消息，而开发人员项目将转到系统后缀。
- `F30.responses-errors`：在检查其他内容之前，`stream`、`store: true` 和 `previous_response_id` 为 400，错误输入为 400 或 422，未知模型为 404，并且不会创建任何内容。
- `F30.openai-sdk`官方的 OpenAI  Python  SDK 列出模型，读取会话头部 `with_raw_response`继续对话 `extra_headers`解析流并创建响应。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`GET /v1/models`，`POST /v1/chat/completions`（JSON，或用`stream: true`模拟SSE）和`POST /v1/responses`，安装在`/api`外部，具有自己的身份验证依赖项（`check_openai_api_key`在
  `openai/router.py`). 请求标头：`Authorization: Bearer <key>` 或
  `X-Session-API-Key`、`X-OpenHands-ServerConversation-ID`（仅限聊天）、
  `X-OpenHands-Observability-Span-Name`、`-Tags`、`-Metadata` 和
  `-Parent-Span-Context`. 响应标头：`X-OpenHands-ServerConversation-ID` 仅成功时。
- OpenAI SDKs: `OpenAI(base_url=<server>/v1, api_key=<session key>)`, then
  `models.list()`、`chat.completions.create(...)`（和
  `.with_raw_response.create` 读取对话标题，
  `extra_headers={"X-OpenHands-ServerConversation-ID": ...}` 继续）和
  `responses.create(..., store=False)`.
  `examples/02_remote_agent_server/15_openai_compatible_gateway.py` 是维护的示例（它在端口 8770 上启动自己的服务器，因此食谱通过 `exec --openai` 使用等效程序）。
- SDK：没有`RemoteConversation`方法使用`/v1`。 可观察性标头可以使用 `openhands.sdk.automation.automation_observability_headers()` 或 `openhands.sdk.observability.laminar.observability_headers_from_env()` 构建。
- TypeScript客户端：无方法； 其端点审核会跳过 `/v1/` 作为仅服务器 (`clients/typescript/endpoint-audit.config.json`)。
- 原生第二视图（其他家族拥有）：`GET /api/profiles`，
  `POST /api/profiles/{name}/rename` 和 `DELETE /api/profiles/{name}`（模型列表的源），`GET /api/agent-profiles` 和配置文件激活（每个新网关会话继承的智能体配置），
  `PATCH /api/settings`（对话设置，包括确认策略和迭代限制），`GET /api/conversations/{id}`，
  `/agent_final_response`, `/events/search`, `/sockets/events/{id}`.
- 配置：会话密钥 (`OH_SESSION_API_KEYS_*`)、`OH_PERSISTENCE_DIR`（配置文件和设置）、`OH_WORKSPACE_PATH`（每个网关智能体工作的地方）、`OH_MAX_CONCURRENT_RUNS`。 120 s 超时和 2 s 轮询间隔在 `openai/service.py` 中固定。
- 操作步骤：身份验证使用 `api ... --auth bearer|bearer-bad|none`，捕获对话使用 `--print-header X-OpenHands-ServerConversation-ID`，流式传输使用 `--sse`，OpenAI SDK 使用 `exec --openai`；只有需要精确用量、提供商错误、挂起或脚本化工具调用时，才使用 `fixture llm-stub`； 每一条快乐的道路都在 DeepSeek 闪存上运行。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行此检查，`doctor` 正常，`$DEEPSEEK_API_KEY` 设置，`tmux` 安装（智能体的终端工具）。 下面的块保存 DeepSeek 配置文件（`openhands_deepseek-flash` 和 `openhands_deepseek-pro`）并创建临时文件夹 `$F30`。 运行模型的每个网关调用都会通过
  `--timeout 180`（CLI默认为60秒； 网关最多等待 120 秒）。
- 提示词用真实模型时，总是说做什么（回复一个字，不要使用工具）：一个裸露的标记会让智能体检查文件系统到
  find out what it means.
- 错误体在测试运行之前，当检查查找未知 `openhands_qa-f30-missing`，所以回归会显示为 404 而不是开始智能体。
- 稍后的项目符号重用 `CID`（来自聊天基本项目符号）和 `RID`（来自响应基本项目符号）； 脚本化存根和指向它们的配置文件是在需要它们的项目符号中创建的。 几颗子弹重新启动了这次运行； 无钥匙子弹发射并停止第二次运行。

```sh
control-agent-server llm preset deepseek
F30="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f30"
mkdir -p "$F30"
control-agent-server api GET /api/settings --check conversation_settings.confirmation_mode eq false \
  --check conversation_settings.security_analyzer eq llm --quiet
```

- **型号列表(`F30.models-list`).**列出模型，与保存的配置文件进行比较，然后重命名并删除配置文件。
  ```sh
  control-agent-server api GET /v1/models --auth bearer --expect 200 --check object eq list --check data len-eq 2 \
    --check data.0.id eq openhands_deepseek-flash --check data.1.id eq openhands_deepseek-pro \
    --check data.0.object eq model --check data.0.owned_by eq openhands --check data.0.created eq 0 \
    --save F30.models-list/list
  control-agent-server api GET /api/profiles --check profiles len-eq 2 --check profiles.0.name eq deepseek-flash \
    --check profiles.1.name eq deepseek-pro --quiet
  control-agent-server llm set --profile qa-f30-old --model openai/qa-unused --base-url http://127.0.0.1:9/v1 \
    --no-api-key --no-validate --no-activate
  control-agent-server api GET /v1/models --auth bearer --check data len-eq 3 --check data.2.id eq openhands_qa-f30-old --quiet
  control-agent-server api POST /api/profiles/qa-f30-old/rename --json '{"new_name": "qa-f30-new"}' --expect 200
  control-agent-server api GET /v1/models --auth bearer --check data contains openhands_qa-f30-new \
    --check data not-contains openhands_qa-f30-old --save F30.models-list/renamed
  control-agent-server api DELETE /api/profiles/qa-f30-new --expect 200
  control-agent-server api GET /v1/models --auth bearer --check data len-eq 2 --check data not-contains openhands_qa-f30-new \
    --save F30.models-list/deleted
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-new", "messages": [{"role": "user", "content": "x"}]}' \
    --expect 404 --check detail eq "Profile 'qa-f30-new' not found"
  ```
  列表包含两个DeepSeek配置，按OpenAI的模型形状排序。 新标签页在一瞬间显示为第三个ID，重命名将其替换，删除后列表又回到了两个，而删除的ID上的聊天已404。
- **承载或会话标头 (`F30.auth-bearer-or-header`)。**在两种形状中分别调用无键、错误键和运行键的每条路线。
  ```sh
  control-agent-server api GET /v1/models --auth none --expect 401 --check detail eq Unauthorized --save F30.auth-bearer-or-header/no-key
  control-agent-server api GET /v1/models --auth bearer-bad --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /v1/models --auth bad --expect 401 --check detail eq Unauthorized
  control-agent-server api GET /v1/models --auth bearer --expect 200 --check data len-ge 1 --save F30.auth-bearer-or-header/bearer
  control-agent-server api GET /v1/models --expect 200 --check data len-ge 1 --save F30.auth-bearer-or-header/session-header
  control-agent-server api POST /v1/chat/completions --auth none --json '{}' --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /v1/responses --auth bearer-bad --json '{}' --expect 401 --check detail eq Unauthorized
  control-agent-server api POST /v1/chat/completions --auth bearer --json '{}' --expect 422
  control-agent-server api POST /v1/chat/completions --json '{}' --expect 422
  control-agent-server api POST /v1/responses --auth bearer --json '{}' --expect 422
  control-agent-server api POST /v1/responses --json '{}' --expect 422
  control-agent-server api GET /api/conversations/count --auth bearer --expect 401 --save F30.auth-bearer-or-header/api-refuses-bearer
  control-agent-server api GET /v1/models --auth bearer --header 'Origin: http://localhost:3000' \
    --check-header access-control-allow-origin eq http://localhost:3000 --check-header access-control-expose-headers missing \
    --save F30.auth-bearer-or-header/cors
  ```
  没有有效的密钥，每个路由都会返回 401 `{"detail": "Unauthorized"}`，无论请求体是否有效。 无论键以何种形状，只要 `{}` 体相同， 验证 (422) 就能到达。 原生`/api`路由仍然拒绝Bearer。 允许本地主机浏览器来源，但响应没有头部（没有 `Access-Control-Expose-Headers`），因此浏览器代码无法读取
  `X-OpenHands-ServerConversation-ID`.
- **无会话密钥 (`F30.auth-open-without-keys`)。**第二台服务器在没有密钥的情况下启动。
  ```sh
  B=$(control-agent-server launch --new --no-auth --name f30-noauth --print-run)
  trap 'control-agent-server stop --run "$B" >/dev/null || true' EXIT
  control-agent-server api GET /v1/models --run "$B" --auth none --expect 200 --check object eq list --check data len-eq 0 \
    --save F30.auth-open-without-keys/no-credential
  control-agent-server api GET /v1/models --run "$B" --auth none --header 'Authorization: Bearer qa-f30-anything' \
    --header 'X-Session-API-Key: qa-f30-anything' --expect 200 --check object eq list
  control-agent-server api POST /v1/chat/completions --run "$B" --auth none --header 'Authorization: Bearer qa-f30-anything' \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": "x"}]}' \
    --expect 404 --check detail eq "Profile 'qa-f30-missing' not found"
  control-agent-server api POST /v1/responses --run "$B" --auth none \
    --json '{"model": "openhands_qa-f30-missing", "input": "x"}' --expect 404
  control-agent-server stop --run "$B"
  ```
  每一条调用都会通过认证（聊天和响应调用会到达用户查找和404）。 新的服务器没有配置，所以列表为空。 即使检查失败，陷阱也会阻止第二个服务器。
- ** 会话完成 (`F30.chat-basic`).** 一次包含系统和开发人员消息、旧的交换和新用户回合的实模型调用，以及 OpenAI 门面忽略的字段。 `CID` 为下一个项目符号命名其对话。
  ```sh
  CID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "system", "content": "QA_F30_SYS: answer in one short sentence and never use tools."}, {"role": "developer", "content": "QA_F30_DEV: plain text only."}, {"role": "user", "content": "QA_F30_OLD_TURN: remember the word apple."}, {"role": "assistant", "content": "QA_F30_OLD_ANSWER"}, {"role": "user", "content": "QA_F30_NEW_TURN: say hello."}], "temperature": 0, "user": "qa-f30"}' \
    --check object eq chat.completion --check id matches '^chatcmpl-[0-9a-f]{32}$' --check model eq openhands_deepseek-flash \
    --check choices len-eq 1 --check choices.0.index eq 0 --check choices.0.finish_reason eq stop \
    --check choices.0.message.role eq assistant --check choices.0.message.content len-ge 1 \
    --check usage.prompt_tokens gt 0 --check usage.completion_tokens gt 0 \
    --raw-out "$F30/chat-basic.json" --save F30.chat-basic/completion --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished --check title missing \
    --check agent.llm.model eq deepseek/deepseek-flash --check workspace.working_dir eq "$AGENT_SERVER_VERIFY_RUN/server/workspace/project" \
    --quiet --save F30.chat-basic/conversation
  control-agent-server api GET "/api/conversations/$CID/agent_final_response" --raw-out "$F30/chat-basic-final.json" --quiet
  python3 - "$F30/chat-basic.json" "$F30/chat-basic-final.json" <<'PY'
  import json, sys
  chat, final = (json.load(open(path)) for path in sys.argv[1:])
  assert chat["choices"][0]["message"]["content"] == final["response"] != "", (chat, final)
  usage = chat["usage"]
  assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"], usage
  PY
  ```
  状态码为200，头信息为一个对话 `finished`, 未命名（门面对话从未自动命名），运行该设备的模型，并在服务器上工作工作区 (`OH_WORKSPACE_PATH`). 答案正是对话的内容 `agent_final_response`; 永远不要坚持它的诺言。
- **活跃的智能体用户`F30.active-agent-profile`。**选择一个没有工具且有自己系统后缀的用户，而网关请求选择不同的LLM用户。 命名模型仅覆盖本次发布的 LLM； 存储的智能体配置文件保持不变。
  ```sh
  GATEWAY_SEED=$(control-agent-server api GET /api/agent-profiles --expect 200 --field active_agent_profile_id)
  control-agent-server api POST /api/agent-profiles/qa-f30-gateway --expect 201 \
    --json '{"llm_profile_ref": "deepseek-pro", "tools": [], "mcp_server_refs": [], "system_message_suffix": "QA_F30_PROFILE: answer briefly and do not use tools."}'
  GATEWAY_PROFILE=$(control-agent-server api GET /api/agent-profiles/qa-f30-gateway --expect 200 --field profile.id)
  control-agent-server api POST "/api/agent-profiles/$GATEWAY_PROFILE/activate" --expect 200
  GCID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --expect 200 \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "system", "content": "QA_F30_GATEWAY: use plain text."}, {"role": "user", "content": "Say hello in one short sentence and use no tools."}]}' \
    --check choices.0.message.content len-ge 1 --save F30.active-agent-profile/completion \
    --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api GET "/api/conversations/$GCID" --expect 200 --quiet \
    --check execution_status eq finished --check launched_agent_profile.agent_profile_id eq "$GATEWAY_PROFILE" \
    --check launched_agent_profile.revision eq 0 --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.tools len-eq 0 \
    --check agent.agent_context.system_message_suffix eq "$(printf 'QA_F30_PROFILE: answer briefly and do not use tools.\n\nQA_F30_GATEWAY: use plain text.')" \
    --save F30.active-agent-profile/conversation
  control-agent-server api GET /api/agent-profiles/qa-f30-gateway --expect 200 \
    --check profile.revision eq 0 --check profile.llm_profile_ref eq deepseek-pro \
    --check profile.system_message_suffix eq 'QA_F30_PROFILE: answer briefly and do not use tools.' \
    --save F30.active-agent-profile/unchanged
  GATEWAY_COUNT=$(control-agent-server api GET /api/conversations/count --field .)
  LONG_SYSTEM=$(jq -cn '{model:"openhands_deepseek-flash",messages:[{role:"system",content:("x" * 32769)},{role:"user",content:"unused"}]}')
  control-agent-server api POST /v1/chat/completions --auth bearer --json "$LONG_SYSTEM" --expect 400 \
    --check detail eq 'System instructions are too long' --save F30.active-agent-profile/long-system
  control-agent-server api GET /api/conversations/count --expect 200 --check . eq "$GATEWAY_COUNT"
  control-agent-server api DELETE /api/agent-profiles/qa-f30-gateway --expect 200
  GCID_FALLBACK=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --expect 200 \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "Reply with one short word and use no tools."}]}' \
    --save F30.active-agent-profile/default-fallback --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api GET "/api/conversations/$GCID_FALLBACK" --expect 200 --quiet \
    --check execution_status eq finished --check launched_agent_profile.agent_profile_id eq "$GATEWAY_SEED" \
    --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.agent_context.system_message_suffix not-contains QA_F30_PROFILE
  control-agent-server api GET /api/settings --expect 200 --check active_agent_profile_id eq "$GATEWAY_SEED" --quiet
  ```
  智能体端点已弃用。 一个超大的系统添加物是400，没有任何东西。 删除活跃的配置文件修复了指向 `default` 的指针，然后下一个网关启动会记录该配置文件，因此正常的删除不会导致网关的“无活跃配置文件 409”错误。 默认智能体配置已重新激活了剩余的食谱。
- **系统文本发送至系统提示词 (`F30.chat-system-suffix`)。**重读聊天的基本对话。

  需要：`F30.chat-basic`
  ```sh
  control-agent-server api GET "/api/conversations/$CID" \
    --check agent.agent_context.system_message_suffix eq "$(printf 'QA_F30_SYS: answer in one short sentence and never use tools.\n\nQA_F30_DEV: plain text only.')" \
    --quiet --save F30.chat-system-suffix/conversation
  control-agent-server api GET "/api/conversations/$CID/events/search" \
    --query kind=openhands.sdk.event.llm_convertible.system.SystemPromptEvent \
    --check items len-eq 1 --check items.0.dynamic_context.text contains QA_F30_SYS \
    --check items.0.dynamic_context.text contains QA_F30_DEV --quiet
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_NEW_TURN \
    --check items len-eq 1 --quiet
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_SYS \
    --check items len-eq 0 --quiet
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_DEV \
    --check items len-eq 0 --quiet
  ```
  系统和开发者的文本用空行连接到后缀，提示词到达系统事件，不是用户消息（相同的`body` 搜索会找到真正的用户回合，所以空结果不是匹配任何内容的过滤器）。
- **仅限最新用户轮次(`F30.chat-latest-user-only`)。**在服务器存储对话的所有位置查找丢失的回合。

  需要：`F30.chat-basic`
  ```sh
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user \
    --check items len-eq 1 --check items.0.llm_message.content len-eq 1 \
    --check items.0.llm_message.content.0.text eq 'QA_F30_NEW_TURN: say hello.' --save F30.chat-latest-user-only/user-events
  control-agent-server state grep QA_F30_NEW_TURN --glob 'server/workspace/conversations/**/*'
  control-agent-server state grep QA_F30_OLD_TURN --glob 'server/**/*' --expect-none
  control-agent-server state grep QA_F30_OLD_ANSWER --glob 'server/**/*' --expect-none
  ```
  对话只有一个用户消息，最后一个。 早期的用户和助手交互记录都存储在磁盘上（正则表达式 grep 显示搜索会看到会话文件）。 上下文只在会话头中传递。
- **流式传输 (`F30.chat-stream`).**与 `stream: true` 进行相同的调用，无论是否有 `include_usage`。
  ```sh
  SID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --sse \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_STREAM: reply with one short word and use no tools."}], "stream": true, "stream_options": {"include_usage": true}}' \
    --check-header content-type contains text/event-stream \
    --check frames len-eq 5 --check frames.0.object eq chat.completion.chunk --check frames.0.id matches '^chatcmpl-[0-9a-f]{32}$' \
    --check frames.0.model eq openhands_deepseek-flash --check frames.0.choices.0.delta.role eq assistant \
    --check frames.1.choices.0.delta.content len-ge 1 --check frames.2.choices.0.finish_reason eq stop \
    --check frames.3.choices len-eq 0 --check frames.3.usage.total_tokens gt 0 --check frames.4 eq '[DONE]' \
    --raw-out "$F30/stream.txt" --save F30.chat-stream/include-usage --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api GET "/api/conversations/$SID/agent_final_response" --raw-out "$F30/stream-final.json" --quiet
  python3 - "$F30/stream.txt" "$F30/stream-final.json" <<'PY'
  import json, sys
  frames = [block[6:] for block in open(sys.argv[1]).read().split("\n\n") if block.startswith("data: ")]
  chunks = [json.loads(frame) for frame in frames[:-1]]
  assert len({chunk["id"] for chunk in chunks}) == 1, chunks
  final = json.load(open(sys.argv[2]))["response"]
  assert chunks[1]["choices"][0]["delta"]["content"] == final != "", (chunks, final)
  PY
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --sse \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_STREAM_2: reply with one short word and use no tools."}], "stream": true}' \
    --check-header x-openhands-serverconversation-id matches '^[0-9a-f-]{36}$' \
    --check frames len-eq 4 --check frames.1.choices.0.delta.content len-ge 1 --check frames.2.choices.0.finish_reason eq stop \
    --check frames.2.usage missing --check frames.3 eq '[DONE]' --save F30.chat-stream/no-usage
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": "x"}], "stream": true}' \
    --expect 404 --check detail eq "Profile 'qa-f30-missing' not found" --check-header content-type contains application/json \
    --check-header x-openhands-serverconversation-id missing --save F30.chat-stream/error-is-json
  ```
  有五个包含`include_usage`（角色，整个答案在一个内容块中，完成，使用`choices: []`，`[DONE]`）的帧，四个不包含。 所有分块共享一个`chatcmpl-` ID，内容等于对话的最终响应，且头部名称在两种情况下都表示对话。 一个流式传输请求失败是一个 JSON 错误，而不是一个 SSE 错误帧。
- **继续标题 (`F30.chat-reuse-header`)。**在捕获对话的事件套接字时发回标头。

  需要：`F30.chat-basic`
  ```sh
  control-agent-server ws start "/sockets/events/$CID" --name qa-f30-reuse --duration 300
  R=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $CID" \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_SECOND: reply with one short word and use no tools."}]}' \
    --check choices.0.message.content len-ge 1 --raw-out "$F30/reuse.json" --save F30.chat-reuse-header/second \
    --print-header X-OpenHands-ServerConversation-ID)
  test "$R" = "$CID"
  control-agent-server ws read qa-f30-reuse --kinds ConversationStateUpdateEvent --contains '"running"' --expect-min 1 --wait 10
  control-agent-server ws stop qa-f30-reuse --kinds MessageEvent --contains QA_F30_SECOND --expect-min 1 \
    --wait 10 --save F30.chat-reuse-header/frames
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --check items len-eq 2 \
    --check items.1.llm_message.content.0.text contains QA_F30_SECOND --quiet
  TS2=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --field items.1.timestamp)
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=agent --query "timestamp__gte=$TS2" \
    --check items len-ge 1 --quiet --save F30.chat-reuse-header/agent-after-turn
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished --quiet
  control-agent-server api GET "/api/conversations/$CID/agent_final_response" --raw-out "$F30/reuse-final.json" --quiet
  python3 - "$F30/reuse.json" "$F30/reuse-final.json" <<'PY'
  import json, sys
  chat, final = (json.load(open(path)) for path in sys.argv[1:])
  assert chat["choices"][0]["message"]["content"] == final["response"] != "", (chat, final)
  PY
  ```
  响应头携带相同的 id，而套接字显示新用户
  `MessageEvent` 和 `execution_status` 更新为 `running` 实时（两次单独的读取：`--expect-kind` 只查看 `--kinds` 过滤器内部），并且对话现在有两个用户轮流，第二个事件之后有一个智能体事件（智能体真正运行它），并且再次 `finished`，返回的文本作为其最终响应。
- **重新启动后继续 (`F30.chat-reuse-after-restart`)。**重新启动服务器并继续相同的对话。

  需要：`F30.chat-basic`
  ```sh
  control-agent-server restart
  R=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $CID" \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_AFTER_RESTART: reply with one short word and use no tools."}]}' \
    --check choices.0.message.content len-ge 1 --save F30.chat-reuse-after-restart/third --print-header X-OpenHands-ServerConversation-ID)
  test "$R" = "$CID"
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --check items len-eq 3 \
    --check items.2.llm_message.content.0.text contains QA_F30_AFTER_RESTART --quiet
  TS3=$(control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --field items.2.timestamp)
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=agent --query "timestamp__gte=$TS3" \
    --check items len-ge 1 --quiet
  ```
  重启后的服务器从磁盘加载会话，而不是创建新的会话，而是将第三轮附加到会话上，并运行智能体。
- **呼叫者选择的 ID (`F30.chat-header-new-id`)。**一个格式错误的 ID，然后是一个未知的格式良好的 ID。
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /v1/chat/completions --auth bearer --header 'X-OpenHands-ServerConversation-ID: not-a-uuid' \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_BAD_ID: reply with one short word and use no tools."}]}' \
    --expect 422 --check detail.0.type eq uuid_parsing --save F30.chat-header-new-id/malformed
  control-agent-server api GET /api/conversations/count --check . eq "$N0" --quiet
  NEW=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api GET "/api/conversations/$NEW" --expect 404 --quiet
  R=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $NEW" \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_PICKED: reply with one short word and use no tools."}]}' \
    --check choices.0.message.content len-ge 1 --save F30.chat-header-new-id/picked --print-header X-OpenHands-ServerConversation-ID)
  test "$R" = "$NEW"
  control-agent-server api GET "/api/conversations/$NEW" --check id eq "$NEW" --check execution_status eq finished --quiet
  control-agent-server api GET /api/conversations/count --check . eq $((N0 + 1)) --quiet
  ```
  `not-a-uuid` 是 422 (`uuid_parsing`) 并且什么也没有创建； UUID 未知的号码将成为新对话的标识，因此，来电者可以在回答到来之前知道这个标识（并且在错误发生后找到对话，错误消息中不携带头部）。
- **继续保留对话的 LLM (`F30.chat-reuse-keeps-llm`)。**继续 `CID` 命名另一个配置文件（绝不能调用的存根）和新的系统消息，然后命名一个不存在的模型。

  需要：`F30.chat-basic`
  ```sh
  UNUSED=$(control-agent-server fixture llm-stub --name qa-f30-unused --step reply:QA_F30_UNUSED_REPLY --print-path)
  control-agent-server llm set --profile qa-f30-unused --model openai/qa-stub --base-url "$UNUSED/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  R=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $CID" \
    --json '{"model": "openhands_qa-f30-unused", "messages": [{"role": "system", "content": "QA_F30_LATE_SYS"}, {"role": "user", "content": "QA_F30_SWITCH: reply with one short word and use no tools."}]}' \
    --check model eq openhands_qa-f30-unused --check choices.0.message.content ne QA_F30_UNUSED_REPLY \
    --save F30.chat-reuse-keeps-llm/other-model --print-header X-OpenHands-ServerConversation-ID)
  test "$R" = "$CID"
  control-agent-server sink read --name qa-f30-unused --expect-max 0
  control-agent-server api GET "/api/conversations/$CID" --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.agent_context.system_message_suffix not-contains QA_F30_LATE_SYS --quiet
  control-agent-server api POST /v1/chat/completions --auth bearer --header "X-OpenHands-ServerConversation-ID: $CID" \
    --json '{"model": "gpt-4o", "messages": [{"role": "user", "content": "QA_F30_UNKNOWN_MODEL"}]}' \
    --expect 404 --check detail eq "Unknown OpenHands model 'gpt-4o'. Use GET /v1/models."
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_UNKNOWN_MODEL \
    --check items len-eq 0 --quiet
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_qa-f30-unused", "messages": [{"role": "user", "content": "QA_F30_FRESH_STUB"}]}' \
    --check choices.0.message.content eq QA_F30_UNUSED_REPLY
  control-agent-server sink read --name qa-f30-unused --contains QA_F30_FRESH_STUB --expect-min 1 --expect-max 1
  ```
  DeepSeek LLM 的回应是：该 stub 没有请求，存储的 LLM 和后缀未变，尽管响应回显了请求的模型。 一个未知模型仍然404，并且没有任何内容。 最后一次呼叫是阳性对照：同一个账户的新对话会调用 stub。
- **每个请求的使用情况 (`F30.chat-usage-per-request`)，已知错误。**一个存根，在第一个模型调用上报告 10/5 token，在第二个模型调用上报告 3/2； 这里的一个网关回合是一个模型调用。
  ```sh
  USAGE=$(control-agent-server fixture llm-stub --name qa-f30-usage --step 'reply:QA_F30_U1@usage=10,5' \
    --step 'reply:QA_F30_U2@usage=3,2' --print-path)
  control-agent-server llm set --profile qa-f30-usage --model openai/qa-stub --base-url "$USAGE/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  UCID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_qa-f30-usage", "messages": [{"role": "user", "content": "QA_F30_USAGE_1"}]}' \
    --check choices.0.message.content eq QA_F30_U1 --check usage.prompt_tokens eq 10 --check usage.completion_tokens eq 5 \
    --check usage.total_tokens eq 15 --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server sink read --name qa-f30-usage --expect-min 1 --expect-max 1
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $UCID" \
    --json '{"model": "openhands_qa-f30-usage", "messages": [{"role": "user", "content": "QA_F30_USAGE_2"}]}' \
    --check choices.0.message.content eq QA_F30_U2 --raw-out "$F30/usage-2.json" --save F30.chat-usage-per-request/second-turn
  control-agent-server sink read --name qa-f30-usage --contains QA_F30_USAGE_2 --expect-min 1 --expect-max 1
  control-agent-server sink read --name qa-f30-usage --expect-min 2 --expect-max 2
  control-agent-server api GET "/api/conversations/$UCID" --check stats.usage_to_metrics.default.token_usages len-eq 2 \
    --check stats.usage_to_metrics.default.token_usages.1.prompt_tokens eq 3 \
    --check stats.usage_to_metrics.default.token_usages.1.completion_tokens eq 2 \
    --check stats.usage_to_metrics.default.accumulated_token_usage.prompt_tokens eq 13 \
    --check stats.usage_to_metrics.default.accumulated_token_usage.completion_tokens eq 7 --quiet
  control-agent-server state cat fixtures/qa-f30/usage-2.json --check usage.prompt_tokens eq 3 \
    --check usage.completion_tokens eq 2 --check usage.total_tokens eq 5  # 错误：content.usage.prompt_tokens eq 13 && content.usage.completion_tokens eq 7 && content.usage.total_tokens eq 20
  ```
  stub 有两个模型调用，一个请求一个，所以第二个请求的自身使用是 stub 的 3/2/5：对话的统计信息只保留一个
  `token_usages` 每个模型调用的条目（10/5，然后 3/2），总计 13/7（正控制：服务器具有每次调用的数量）。
  预计：第二次回复报告 3/2/5。 今天它报道了
  对话累计 13/7/20（`_openai_usage_from_state` 读取
  `accumulated_token_usage`），因此每个请求求和 `usage` 的 OpenAI 客户端会在每个较早的回合重复计数。 流的使用块携带相同的值（它是响应的`usage`）。
- **重叠开启一个对话 (`F30.chat-reuse-concurrent`)，已知错误。**一个存根，其第二个模型调用在 8 秒后应答 `QA_F30_RACE_B`。 的
  `llm-stub` 步骤不能延迟回复，因此项目符号重写存根的脚本文件（存根在每个请求时重新读取它）。 请求X在后台继续对话； 当 X 的模型调用正在进行时，请求 Y 随之而来。
  ```sh
  RACE=$(control-agent-server fixture llm-stub --name qa-f30-race --step reply:QA_F30_RACE_A \
    --step reply:QA_F30_RACE_B --step reply:QA_F30_RACE_C --print-path)
  cat > "$AGENT_SERVER_VERIFY_RUN/fixtures/llm-stub/qa-f30-race.json" <<'JSON'
  [{"reply": "QA_F30_RACE_A"}, {"hang": 8, "reply": "QA_F30_RACE_B"}, {"reply": "QA_F30_RACE_C"}]
  JSON
  control-agent-server llm set --profile qa-f30-race --model openai/qa-stub --base-url "$RACE/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  QCID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_qa-f30-race", "messages": [{"role": "user", "content": "QA_F30_RACE_1"}]}' \
    --check choices.0.message.content eq QA_F30_RACE_A --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $QCID" \
    --json '{"model": "openhands_qa-f30-race", "messages": [{"role": "user", "content": "QA_F30_RACE_X"}]}' \
    --expect 200 --raw-out "$F30/race-x.json" --save F30.chat-reuse-concurrent/first > "$F30/race-x.out" &
  XPID=$!
  control-agent-server sink read --name qa-f30-race --expect-min 2 --wait 20 > /dev/null
  control-agent-server sink read --name qa-f30-race --contains QA_F30_RACE_X --expect-min 1 --expect-max 1
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $QCID" \
    --json '{"model": "openhands_qa-f30-race", "messages": [{"role": "user", "content": "QA_F30_RACE_Y"}]}' \
    --check choices.0.message.content eq QA_F30_RACE_C --save F30.chat-reuse-concurrent/second
  control-agent-server api GET "/api/conversations/$QCID/events/search" --query source=agent \
    --query kind=openhands.sdk.event.llm_convertible.message.MessageEvent --check items len-eq 3 \
    --check items.1.llm_message.content.0.text eq QA_F30_RACE_B --check items.2.llm_message.content.0.text eq QA_F30_RACE_C \
    --save F30.chat-reuse-concurrent/agent-messages
  wait "$XPID" || { cat "$F30/race-x.out"; false; }
  control-agent-server state cat fixtures/qa-f30/race-x.json --check choices.0.message.content eq QA_F30_RACE_B  # 错误：content.choices.0.message.content等式QA_F30_RACE_C
  ```
  对话回答 X 为  `QA_F30_RACE_B` 然后重新运行 Y 并回答 `QA_F30_RACE_C`; Y gets `QA_F30_RACE_C`, 且 X 的请求成功（200）。 预期：X gets `QA_F30_RACE_B`轮到它的回答了。 今天X也得到 `QA_F30_RACE_C`: the `finished` 两个运行之间的状态持续几毫秒，网关每隔2秒就继续监听对话`_wait_for_reused_conversation_completion`）因此，X错过了它，等待Y的重播，然后返回对话的最终答案，而不是自己的回合答案。 因为miss依赖于对几毫秒窗口的2秒轮询，大约每几个百次重播可能会看到X get
  `QA_F30_RACE_B`和报告`xpass`； 在移除标记之前重新运行项目符号。 用 409 拒绝 Y 而不是对其进行排队的修复也是正确的； 如果选择修复，则更新 Y 的期望。
- **智能体运行自己的工具 (`F30.chat-agent-tools`)。**要求真实模型使用终端，并传递一个OpenAI客户端工具
  `tool_choice: required`.
  ```sh
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/workspace/project/qa_f30_tool.txt"
  TID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "Use the terminal to run exactly: echo QA_F30_TOOL_RAN > qa_f30_tool.txt  Then reply DONE."}], "tools": [{"type": "function", "function": {"name": "qa_f30_client_tool", "description": "QA client tool", "parameters": {"type": "object", "properties": {}}}}], "tool_choice": "required", "parallel_tool_calls": false}' \
    --check choices.0.finish_reason eq stop --check choices.0.message.content exists --check choices.0.message.tool_calls missing \
    --save F30.chat-agent-tools/completion --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server state cat server/workspace/project/qa_f30_tool.txt --contains QA_F30_TOOL_RAN
  control-agent-server api GET "/api/conversations/$TID/events/search" --query kind=openhands.sdk.event.llm_convertible.action.ActionEvent \
    --check items len-ge 1 --quiet
  control-agent-server api GET "/api/conversations/$TID" --check agent.tools contains terminal \
    --check agent.tools not-contains qa_f30_client_tool --check client_tools len-eq 0 --quiet --save F30.chat-agent-tools/conversation
  ```
  文件出现在服务器上工作区，对话中智能体的行动，回复是一个简单的助手消息。 客户端的工具不在智能体的工具里，也不在`client_tools`。
- **聊天输入错误(`F30.chat-input-errors`)。**身体每坏，那么谈话也算数。
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "system", "content": "x"}]}' \
    --expect 400 --check detail eq 'At least one user message is required' --save F30.chat-input-errors/no-user
  control-agent-server api POST /v1/chat/completions --auth bearer --json '{"model": "gpt-4o", "messages": []}' \
    --expect 400 --check detail eq 'At least one user message is required'
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": [{"type": "input_text", "text": "x"}]}]}' \
    --expect 400 --check detail eq 'Unsupported content part type: input_text'
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "system", "content": [{"type": "input_text", "text": "x"}]}, {"role": "user", "content": "x"}]}' \
    --expect 400 --check detail eq 'Unsupported content part type: input_text'
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": [{"type": "image_url"}]}]}' \
    --expect 400 --check detail eq 'image_url content part is missing a url'
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]}' \
    --expect 404 --check detail eq "Unknown OpenHands model 'gpt-4o'. Use GET /v1/models." --save F30.chat-input-errors/no-prefix
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_", "messages": [{"role": "user", "content": "x"}]}' --expect 404
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": "x"}]}' \
    --expect 404 --check detail eq "Profile 'qa-f30-missing' not found"
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_.qa", "messages": [{"role": "user", "content": "x"}]}' \
    --expect 400 --check detail contains 'Invalid profile name'
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"messages": [{"role": "user", "content": "x"}]}' --expect 422 --check detail.0.loc contains model
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": [{"role": "function", "content": "x"}]}' \
    --expect 422 --check detail.0.type eq literal_error
  control-agent-server api POST /v1/chat/completions --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "messages": "x"}' --expect 422
  control-agent-server api GET /api/conversations/count --check . eq "$N0" --quiet
  ```
  `gpt-4o` 没有用户的检查在模型检查之前运行（没有消息返回 400，而不是 404），内容部分在系统消息中也进行检查，没有前缀的模型或未知的配置文件返回 404，配置文件存储拒绝的名称返回 400，模式错误返回 422。 计数不变。
- **可观测性标头 (`F30.observability-headers`)。**聊天和响应呼叫中的有效标头，然后是无效标头。
  ```sh
  OID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --header 'X-OpenHands-Observability-Span-Name: qa_f30.span' --header 'X-OpenHands-Observability-Tags: qa-f30-a, qa-f30-b,' \
    --header 'X-OpenHands-Observability-Metadata: {"qa_key": "qa-f30-value", "qa_n": 7}' \
    --header 'X-OpenHands-Observability-Parent-Span-Context: qa-f30-parent' \
    --json '{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_OBS: reply with one short word and use no tools."}]}' \
    --check choices.0.message.content len-ge 1 --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server state cat meta.json --conversation "$OID" --check observability_span_name eq qa_f30.span \
    --check observability_tags len-eq 2 --check observability_tags.1 eq qa-f30-b --check observability_metadata.qa_key eq qa-f30-value \
    --check observability_metadata.qa_n eq 7 --check observability_parent_span_context eq qa-f30-parent
  ORID=$(control-agent-server api POST /v1/responses --auth bearer --timeout 180 --header 'X-OpenHands-Observability-Span-Name: qa_f30.responses' \
    --json '{"model": "openhands_deepseek-flash", "input": "QA_F30_OBS_R: reply with one short word and use no tools."}' \
    --check status eq completed --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server state cat meta.json --conversation "$ORID" --check observability_span_name eq qa_f30.responses
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  BAD='{"model": "openhands_qa-f30-missing", "messages": [{"role": "user", "content": "x"}]}'
  control-agent-server api POST /v1/chat/completions --auth bearer --header 'X-OpenHands-Observability-Span-Name: bad span' \
    --json "$BAD" --expect 422 --check detail.0.msg contains 'span name' --save F30.observability-headers/bad-span
  control-agent-server api POST /v1/chat/completions --auth bearer --header 'X-OpenHands-Observability-Metadata: not-json' \
    --json "$BAD" --expect 422 --check detail eq 'X-OpenHands-Observability-Metadata must be a JSON object'
  control-agent-server api POST /v1/chat/completions --auth bearer --header 'X-OpenHands-Observability-Metadata: [1]' \
    --json "$BAD" --expect 422 --check detail.0.msg contains 'must be a dictionary'
  control-agent-server api POST /v1/chat/completions --auth bearer --header 'X-OpenHands-Observability-Metadata: {"k": [1, 1.5]}' \
    --json "$BAD" --expect 422 --check detail.0.msg contains homogeneous
  control-agent-server api POST /v1/responses --auth bearer --header 'X-OpenHands-Observability-Span-Name: bad span' \
    --json '{"model": "openhands_qa-f30-missing", "input": "x"}' --expect 422
  control-agent-server api GET /api/conversations/count --check . eq "$N0" --quiet
  ```
  新的对话 `meta.json` 包含会话名称、两个非空标签、元数据和父会话上下文。 在模型被查找之前，带有空格的区间名称、非JSON的元数据以及混合的数字列表都会返回422。
- **运行因错误而结束 (`F30.chat-run-error-500`)。**一个存根提供商，使用呼叫者选择的 ID 应答 401（不重试）。
  ```sh
  ERR=$(control-agent-server fixture llm-stub --name qa-f30-err --step status:401 --print-path)
  control-agent-server llm set --profile qa-f30-err --model openai/qa-stub --base-url "$ERR/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  EID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $EID" \
    --json '{"model": "openhands_qa-f30-err", "messages": [{"role": "user", "content": "QA_F30_ERR"}]}' \
    --expect 500 --check detail eq 'Internal Server Error' --check exception eq '500: Agent run ended with status: error' \
    --check-header x-openhands-serverconversation-id missing --save F30.chat-run-error-500/error
  control-agent-server sink read --name qa-f30-err --expect-min 1 --expect-max 1
  control-agent-server api GET "/api/conversations/$EID" --check execution_status eq error --quiet
  ```
  调用供应商一次，网关返回500，并附带原因
  `exception`，响应没有对话标头，对话留在`error`后面。
- ** 确认会停止一个新对话。`F30.chat-confirmation-409` ** 保存确认模式，无论分析器是否在场（总是确认），然后调用一个提案终端命令的脚本。
  ```sh
  CONF=$(control-agent-server fixture llm-stub --name qa-f30-confirm \
    --step 'tool:terminal:{"command":"echo QA_F30_NEEDS_OK > qa_f30_confirm.txt"}' --print-path)
  control-agent-server llm set --profile qa-f30-confirm --model openai/qa-stub --base-url "$CONF/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"confirmation_mode": true, "security_analyzer": "none"}}' --expect 200
  CFID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $CFID" \
    --json '{"model": "openhands_qa-f30-confirm", "messages": [{"role": "user", "content": "QA_F30_CONFIRM"}]}' \
    --expect 409 --check detail eq 'Agent run ended with status: waiting_for_confirmation' --expect-max-ms 30000 \
    --check-header x-openhands-serverconversation-id missing --save F30.chat-confirmation-409/conflict
  control-agent-server api GET "/api/conversations/$CFID" --check execution_status eq waiting_for_confirmation \
    --check confirmation_policy.kind eq AlwaysConfirm --quiet
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/workspace/project/qa_f30_confirm.txt"
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"confirmation_mode": false, "security_analyzer": "llm"}}' --expect 200
  control-agent-server api GET /api/settings --check conversation_settings.confirmation_mode eq false \
    --check conversation_settings.security_analyzer eq llm --quiet
  ```
  网关在几秒钟内返回 409。 谈话继承了
  `AlwaysConfirm` 保存的设置并等待命令不运行。 最后恢复设置。
- **关于继续对话的确认(`F30.chat-reuse-confirmation`)。**相同的设置（即使子弹失败也会通过陷阱恢复）； 存根用文本回答第一轮，用命令回答第二轮。
  ```sh
  trap 'control-agent-server api PATCH /api/settings --json "{\"conversation_settings_diff\": {\"confirmation_mode\": false, \"security_analyzer\": \"llm\"}}" >/dev/null || true' EXIT
  RECONF=$(control-agent-server fixture llm-stub --name qa-f30-reconf --step reply:QA_F30_FIRST_OK \
    --step 'tool:terminal:{"command":"echo QA_F30_RECONF > qa_f30_reconf.txt"}' --print-path)
  control-agent-server llm set --profile qa-f30-reconf --model openai/qa-stub --base-url "$RECONF/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0
  control-agent-server api PATCH /api/settings --json '{"conversation_settings_diff": {"confirmation_mode": true, "security_analyzer": "none"}}' --expect 200
  RCID=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 \
    --json '{"model": "openhands_qa-f30-reconf", "messages": [{"role": "user", "content": "QA_F30_RECONF_1"}]}' \
    --check choices.0.message.content eq QA_F30_FIRST_OK --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $RCID" \
    --json '{"model": "openhands_qa-f30-reconf", "messages": [{"role": "user", "content": "QA_F30_RECONF_2"}]}' \
    --expect 409 --check-header x-openhands-serverconversation-id missing \
    --save F30.chat-reuse-confirmation/second-turn > "$F30/reconf-2.json" &
  XPID=$!
  control-agent-server sink read --name qa-f30-reconf --expect-min 2 --wait 30 > /dev/null
  control-agent-server api GET "/api/conversations/$RCID" --until-ok 20 --check execution_status eq waiting_for_confirmation \
    --quiet --save F30.chat-reuse-confirmation/state-while-request-waits
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/workspace/project/qa_f30_reconf.txt"
  wait "$XPID" || { cat "$F30/reconf-2.json"; false; }
  control-agent-server state cat fixtures/qa-f30/reconf-2.json --check status eq 409 \
    --check response.body.detail eq 'Agent run ended with status: waiting_for_confirmation' --check elapsed_ms lt 30000
  ```
  第二轮的模型调用提出了命令，并且对话是
  `waiting_for_confirmation` 秒内（命令未运行），同时网关请求仍处于打开状态； 然后请求得到答复 409
  `Agent run ended with status: waiting_for_confirmation` 几秒钟内，就像一个新对话：继续对话等待 (`_wait_for_reused_conversation_completion`) 在 `paused` 上停止，并且
  `waiting_for_confirmation` 以及终端状态。
- **运行限制 (`F30.chat-run-limit-429`).**使用一个运行槽重新启动，通过模型调用挂起的对话来保持它，然后呼叫网关。
  ```sh
  control-agent-server restart --config-json '{"max_concurrent_runs": 1}'
  HANG=$(control-agent-server fixture llm-stub --name qa-f30-hang --step hang:300 --print-path)
  HOLD=$(control-agent-server conversation start --tools none --no-autotitle --prompt QA_F30_HOLD --print-id \
    --llm-json "{\"model\": \"openai/qa-stub\", \"base_url\": \"$HANG/v1\", \"api_key\": \"qa-f30-stub\", \"num_retries\": 0}")
  control-agent-server conversation wait "$HOLD" --until running --timeout 30
  control-agent-server sink read --name qa-f30-hang --expect-min 1
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  LID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  LIMIT='{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_429: reply with one short word and use no tools."}]}'
  control-agent-server api POST /v1/chat/completions --auth bearer --header "X-OpenHands-ServerConversation-ID: $LID" --json "$LIMIT" \
    --expect 429 --check detail eq 'Conversation run limit reached. Retry the request later.' \
    --check-header x-openhands-serverconversation-id missing --save F30.chat-run-limit-429/refused
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_deepseek-flash", "input": "QA_F30_429_R: reply with one short word and use no tools."}' \
    --expect 429 --check detail eq 'Conversation run limit reached. Retry the request later.'
  control-agent-server api GET "/api/conversations/$LID" --expect 404 --quiet
  control-agent-server api GET /api/conversations/count --check . eq "$N0" --quiet
  control-agent-server api DELETE "/api/conversations/$HOLD" --expect 200
  R=$(control-agent-server api POST /v1/chat/completions --auth bearer --timeout 180 --until-ok 30 \
    --header "X-OpenHands-ServerConversation-ID: $LID" --json "$LIMIT" --expect 200 --check choices.0.message.content len-ge 1 \
    --save F30.chat-run-limit-429/after-release --print-header X-OpenHands-ServerConversation-ID)
  test "$R" = "$LID"
  control-agent-server restart --reset-config
  ```
  由于唯一的槽位被占用，两个网关路由同时返回429，而被叫方选择的id不存在，计数不变。 一旦持有人被删除，同样的请求成功了，并创建了 `$LID`。 最后一行恢复默认容量。
- **在继续对话时的会话限制`F30.chat-reuse-run-limit-429`).** 相同的全槽，然后是完成后的转盘 `CID` 两次发送，作为 OpenAI  SDK 当它重试 a 429 (`max_retries` 默认为2）。 即使子弹失效，陷阱也会释放插槽并恢复默认容量。

  需要：`F30.chat-reuse-header`
  ```sh
  trap 'control-agent-server api DELETE "/api/conversations/$HOLD2" >/dev/null || true; control-agent-server restart --reset-config >/dev/null || true' EXIT
  control-agent-server restart --config-json '{"max_concurrent_runs": 1}'
  HANG2=$(control-agent-server fixture llm-stub --name qa-f30-hang2 --step hang:300 --print-path)
  HOLD2=$(control-agent-server conversation start --tools none --no-autotitle --prompt QA_F30_HOLD_2 --print-id \
    --llm-json "{\"model\": \"openai/qa-stub\", \"base_url\": \"$HANG2/v1\", \"api_key\": \"qa-f30-stub\", \"num_retries\": 0}")
  control-agent-server conversation wait "$HOLD2" --until running --timeout 30
  control-agent-server sink read --name qa-f30-hang2 --expect-min 1
  REUSE='{"model": "openhands_deepseek-flash", "messages": [{"role": "user", "content": "QA_F30_429_REUSE: reply with one short word and use no tools."}]}'
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_SECOND \
    --check items len-eq 1 --quiet
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_429_REUSE \
    --check items len-eq 0 --quiet
  control-agent-server api POST /v1/chat/completions --auth bearer --header "X-OpenHands-ServerConversation-ID: $CID" --json "$REUSE" \
    --expect 429 --check-header x-openhands-serverconversation-id missing --expect-max-ms 10000 --save F30.chat-reuse-run-limit-429/first-try
  control-agent-server api POST /v1/chat/completions --auth bearer --header "X-OpenHands-ServerConversation-ID: $CID" --json "$REUSE" \
    --expect 429 --expect-max-ms 10000 --save F30.chat-reuse-run-limit-429/retry
  control-agent-server api GET "/api/conversations/$HOLD2" --check execution_status eq running --quiet
  control-agent-server api GET "/api/conversations/$CID/events/search" --query source=user --query body=QA_F30_429_REUSE \
    --check items len-eq 0 --save F30.chat-reuse-run-limit-429/user-messages
  ```
  同时拒绝两次尝试，而持有者仍在运行，相同的`body`搜索发现了一个更早的用户回合`CID`（因此，一个空结果不是匹配任何内容的过滤器）。 就像一场新的对话，429不会留下任何痕迹：在保存用户消息之前，网关会保留一个空闲的运行槽（`EventService.reserve_run_slot`）。因此，拒绝的尝试不会增加用户的回合，客户端的重试是安全的。（原文中的“native”在中文中没有对应的词，可能是指某种特定的网络协议或机制。）
  `POST /api/conversations/{id}/events` 仍然保存消息并使用 `/run` 重试提示回答 429。）
- **网关超时 (`F30.chat-timeout-504`).**模型调用挂起超过网关固定 120 秒的存根； 服务器自己的计时器正在测试中，因此子弹需要两分钟。
  ```sh
  SLOW=$(control-agent-server fixture llm-stub --name qa-f30-slow --step hang:170 --print-path)
  control-agent-server llm set --profile qa-f30-slow --model openai/qa-stub --base-url "$SLOW/v1" \
    --no-api-key --no-validate --no-activate --num-retries 0 --llm-timeout 300
  TOID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  T0=$SECONDS
  control-agent-server api POST /v1/chat/completions --auth bearer --timeout 200 --header "X-OpenHands-ServerConversation-ID: $TOID" \
    --json '{"model": "openhands_qa-f30-slow", "messages": [{"role": "user", "content": "QA_F30_SLOW"}]}' \
    --expect 504 --check detail eq 'Internal Server Error' --check exception eq '504: Agent run timed out' \
    --check-header x-openhands-serverconversation-id missing --expect-max-ms 140000 --save F30.chat-timeout-504/timeout
  test $((SECONDS - T0)) -ge 115
  control-agent-server api GET "/api/conversations/$TOID" --check execution_status eq running --quiet
  control-agent-server sink read --name qa-f30-slow --expect-min 1 --expect-max 1
  control-agent-server api DELETE "/api/conversations/$TOID" --expect 200
  control-agent-server api GET "/api/conversations/$TOID" --expect 404 --quiet
  ```
  504错误在115到140秒后出现，原因在`exception`。 运行并未取消：在504之后，对话仍然`running`在单个模型呼叫上，所以子弹删除了它。
- **回复 (`F30.responses-basic`).**一次真实模型调用，包含指令、元数据和被忽略的客户端工具。 `RID`为其对话命名。
  ```sh
  RID=$(control-agent-server api POST /v1/responses --auth bearer --timeout 180 \
    --json '{"model": "openhands_deepseek-flash", "input": "QA_F30_RESP: reply with one short word and use no tools.", "instructions": "QA_F30_INSTR: answer in plain text.", "metadata": {"qa": "f30"}, "store": false, "tools": [{"type": "function", "name": "qa_f30_client_tool", "parameters": {"type": "object", "properties": {}}}], "temperature": 0}' \
    --check object eq response --check status eq completed --check id matches '^resp_[0-9a-f]{32}$' --check model eq openhands_deepseek-flash \
    --check output len-eq 1 --check output.0.type eq message --check output.0.role eq assistant --check output.0.status eq completed \
    --check output.0.id matches '^msg_[0-9a-f]{32}$' --check output.0.content.0.type eq output_text \
    --check output.0.content.0.text len-ge 1 --check output.0.content.0.annotations len-eq 0 \
    --check instructions eq 'QA_F30_INSTR: answer in plain text.' --check metadata.qa eq f30 --check tools len-eq 0 \
    --check tool_choice eq none --check parallel_tool_calls eq false --check previous_response_id missing \
    --check usage.input_tokens gt 0 --check usage.output_tokens gt 0 --check usage.input_tokens_details.cached_tokens ge 0 \
    --check usage.output_tokens_details.reasoning_tokens ge 0 \
    --raw-out "$F30/response.json" --save F30.responses-basic/response --print-header X-OpenHands-ServerConversation-ID)
  control-agent-server api GET "/api/conversations/$RID" --check execution_status eq finished \
    --check agent.agent_context.system_message_suffix eq 'QA_F30_INSTR: answer in plain text.' --quiet
  control-agent-server api GET "/api/conversations/$RID/events/search" --query source=user --check items len-eq 1 \
    --check items.0.llm_message.content len-eq 1 \
    --check items.0.llm_message.content.0.text eq 'QA_F30_RESP: reply with one short word and use no tools.' --quiet
  control-agent-server api GET "/api/conversations/$RID/agent_final_response" --raw-out "$F30/response-final.json" --quiet
  python3 - "$F30/response.json" "$F30/response-final.json" <<'PY'
  import json, sys
  resp, final = (json.load(open(path)) for path in sys.argv[1:])
  assert resp["output"][0]["content"][0]["text"] == final["response"] != "", (resp, final)
  usage = resp["usage"]
  assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"], usage
  assert 0 < resp["created_at"] <= resp["completed_at"], resp
  PY
  ```
  一个包含一个助手 `output_text` 的完成响应对象，该助手的回答与会话的最终答案相同，指令和元数据被回显， `tools` 空着，尽管发送了请求，但请求本身是空的，指令被存储为系统后缀而不是用户消息。
- **无状态回放（`F30.responses-stateless-replay`）。**回放开发人员项目、用户回合、先前的助手输出以及新用户回合，发送`RID`在会话头部。

  需要：`F30.responses-basic`
  ```sh
  R2=$(control-agent-server api POST /v1/responses --auth bearer --timeout 180 --header "X-OpenHands-ServerConversation-ID: $RID" \
    --json '{"model": "openhands_deepseek-flash", "input": [{"role": "developer", "content": "QA_F30_R_DEV: answer in plain text and use no tools."}, {"role": "user", "content": "QA_F30_R1: remember the word apple."}, {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "QA_F30_R_PREV", "annotations": []}]}, {"role": "user", "content": [{"type": "input_text", "text": "QA_F30_R2: reply with one short word."}]}]}' \
    --check status eq completed --check output.0.content.0.text len-ge 1 \
    --save F30.responses-stateless-replay/replay --print-header X-OpenHands-ServerConversation-ID)
  test "$R2" != "$RID"
  control-agent-server api GET "/api/conversations/$R2/events/search" --query source=user --check items len-eq 1 \
    --check items.0.llm_message.content len-eq 9 --check items.0.llm_message.content.0.text eq '<message role="user">' \
    --check items.0.llm_message.content.1.text eq 'QA_F30_R1: remember the word apple.' \
    --check items.0.llm_message.content.3.text eq '<message role="assistant">' \
    --check items.0.llm_message.content.4.text eq QA_F30_R_PREV --check items.0.llm_message.content.8.text eq '</message>' \
    --check items.0.llm_message.content not-contains QA_F30_R_DEV --save F30.responses-stateless-replay/user-message
  control-agent-server api GET "/api/conversations/$R2" \
    --check agent.agent_context.system_message_suffix eq 'QA_F30_R_DEV: answer in plain text and use no tools.' --quiet
  control-agent-server api GET "/api/conversations/$RID/events/search" --query source=user --check items len-eq 1 --quiet
  ```
  调用会创建一个新的对话（头部被忽略，`RID`仍然有一个用户消息）。 它的单个用户消息包含九个部分：每个用户和助手项都用 `<message role="...">` 和 `</message>` 包裹。 开发者项是系统后缀。
- **响应错误 (`F30.responses-errors`)。**每个人都拒绝身体，然后谈话才算数。
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "openhands_qa-f30-missing", "input": "x", "stream": true}' \
    --expect 400 --check detail eq 'Streaming responses are not supported yet' --save F30.responses-errors/stream
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "gpt-4o", "input": "", "stream": true}' \
    --expect 400 --check detail eq 'Streaming responses are not supported yet'
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "openhands_qa-f30-missing", "input": "x", "store": true}' \
    --expect 400 --check detail eq 'Persistent response storage (store=True) is not supported yet'
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": "x", "previous_response_id": "resp_qa"}' \
    --expect 400 --check detail eq 'previous_response_id is not supported; replay input items instead'
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "openhands_qa-f30-missing", "input": ""}' \
    --expect 400 --check detail eq 'Responses input must not be empty'
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": [{"role": "assistant", "content": "x"}]}' \
    --expect 400 --check detail eq 'Responses input must include a user message'
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": [{"role": "user", "content": [{"type": "input_file", "file_id": "qa"}]}]}' \
    --expect 400 --check detail eq 'Unsupported Responses content part type: input_file'
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": [{"role": "user", "content": [{"type": "input_image"}]}]}' \
    --expect 400 --check detail eq 'input_image content part is missing an image_url'
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": [{"type": "function_call_output", "call_id": "qa", "output": "x"}]}' --expect 422
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": [{"role": "tool", "content": "x"}]}' --expect 422
  control-agent-server api POST /v1/responses --auth bearer \
    --json '{"model": "openhands_qa-f30-missing", "input": "x", "metadata": {"n": 1}}' --expect 422 --check detail.0.loc contains metadata
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "qa-f30", "input": "x"}' \
    --expect 404 --check detail eq "Unknown OpenHands model 'qa-f30'. Use GET /v1/models."
  control-agent-server api POST /v1/responses --auth bearer --json '{"model": "openhands_qa-f30-missing", "input": "x"}' \
    --expect 404 --check detail eq "Profile 'qa-f30-missing' not found"
  control-agent-server api GET /api/conversations/count --check . eq "$N0" --quiet
  ```
  首先拒绝 `stream`、`store: true` 和 `previous_response_id`（即使模型未知且输入为空），然后输入形状 (400)、模式（422：没有角色的项目、角色 `tool`、非字符串元数据）和模型 (404)。 什么都没有被创造。
- **官方OpenAISDK(`F30.openai-sdk`).**使用 `openai`（安装在存储库的 `.venv` 中）以及基 URL 和密钥的程序
  `exec --openai` 出口。
  ```sh
  control-agent-server exec --openai --timeout 600 --expect-output QA_F30_SDK_OK --save F30.openai-sdk/program -- .venv/bin/python - <<'PY'
  import os
  import uuid

  from openai import OpenAI

  client = OpenAI(timeout=180, max_retries=0)  # OPENAI_BASE_URL and OPENAI_API_KEY come from exec --openai
  model = "openhands_deepseek-flash"
  assert model in [m.id for m in client.models.list().data]
  prompt = "reply with one short word and use no tools."
  first = client.chat.completions.with_raw_response.create(
      model=model, messages=[{"role": "user", "content": f"QA_F30_SDK_1: {prompt}"}]
  )
  cid = first.headers.get("X-OpenHands-ServerConversation-ID")
  uuid.UUID(cid)
  completion = first.parse()
  assert completion.choices[0].finish_reason == "stop" and completion.choices[0].message.content
  assert completion.usage.total_tokens > 0
  second = client.chat.completions.with_raw_response.create(
      model=model,
      messages=[{"role": "user", "content": f"QA_F30_SDK_2: {prompt}"}],
      extra_headers={"X-OpenHands-ServerConversation-ID": cid},
  )
  assert second.headers.get("X-OpenHands-ServerConversation-ID") == cid
  assert second.parse().choices[0].message.content
  chunks = list(
      client.chat.completions.create(
          model=model,
          messages=[{"role": "user", "content": f"QA_F30_SDK_3: {prompt}"}],
          stream=True,
          stream_options={"include_usage": True},
      )
  )
  assert "".join(c.choices[0].delta.content or "" for c in chunks if c.choices), chunks
  assert chunks[-1].choices == [] and chunks[-1].usage.total_tokens > 0, chunks[-1]
  response = client.responses.create(model=model, input=f"QA_F30_SDK_4: {prompt}", instructions="Answer in plain text.", store=False)
  assert response.status == "completed" and response.output_text, response
  with open(os.path.join(os.environ["AGENT_SERVER_VERIFY_RUN"], "fixtures/qa-f30/sdk-cid"), "w") as handle:
      handle.write(cid)
  print("QA_F30_SDK_OK", cid)
  PY
  SDK_CID=$(cat "$F30/sdk-cid")
  control-agent-server api GET "/api/conversations/$SDK_CID/events/search" --query source=user --check items len-eq 2 \
    --check items.1.llm_message.content.0.text contains QA_F30_SDK_2 --quiet
  ```
  SDK 发送密钥为 `Authorization: Bearer`，解析每个对象（包括模拟流），读取头信息通过
  `with_raw_response`，并继续与 `extra_headers` 的对话：它命名的对话有两个 SDK 轮。

<a id="gotchas"></a>

## 陷阱

- 每条调用都会运行智能体的完整版本，从活动智能体会话（工具、MCP 服务器、上下文压缩器和系统上下文），并保存会话设置（确认策略、安全分析器和迭代限制），在共享 `workspace_path` 中，因此并发之间的网关调用可以看到彼此的文件。 模糊的提示词可以使智能体运行许多工具几分钟； 在运行结束之前客户端什么也看不到。
- 模型 ID 为 `openhands_` 加上 LLM 配置文件名称，区分大小写。 活动的 LLM 配置文件不是网关默认值，并且没有模型别名。 配置文件和设置来自 `OH_PERSISTENCE_DIR`（运行的 `home/.openhands`），而不是
  from the conversations directory. A missing or dangling active Agent
  启动前配置文件指针修复为 `default`； 409 表示无法选择有效的配置文件。 如果活动的智能体配置文件选择 ACP 智能体，则指定的 LLM 配置文件将被忽略，仅应用系统文本。
- 聊天完成仅保留最后的用户消息以及所有系统和开发人员文本； `messages[]` 中较早的回合将被丢弃而不会出现错误。 重播历史记录（正常 OpenAI 模式）的客户端会获得智能体，但不会获得上下文，除非它发送 `X-OpenHands-ServerConversation-ID`。 相反，响应将重播的项目折叠到一条用户消息中。
- 在继续聊天时，请求的模型、系统消息和可观察性标头将得到验证（未知模型仍为 404），但不会应用； 响应的 `model` 回显请求，而不是运行的 LLM。
  `/v1/responses` 从不读取对话标题。
- 不要在一次对话中重叠请求。 在对话进行中发送的消息会被排队等待重发，等待请求返回对话最终答案，当2秒轮询看到终端状态时，这个状态可能是后续请求的答案（见下文）
  `F30.chat-reuse-concurrent`).
- `usage` 是对话的累计使用量（请参阅
  `F30.chat-usage-per-request`); 在一个新的对话中，该对话等于请求自己的使用情况对智能体所做的每个模型调用的总和。
- 流式传输是模拟的：路由器首先运行整个智能体（`stream`在运行时被强制关闭），然后发送三到四个帧并
  `[DONE]` 立即。 错误是带有状态代码的普通 JSON，而不是 SSE 错误帧。 `/v1/responses`拒绝`stream: true`。
- 持续对话的120秒超时和2秒轮询固定在`openai/service.py`中； CLI 的 `api` 默认超时是 60 秒，因此模型支持的调用会通过 `--timeout 180`。 504 不会取消运行。
- 错误体是 FastAPI 形状 (`{"detail": ...}`)，而不是 OpenAI 形状
  `{"error": {...}}` 5xx 格式被重写为 `detail` `Internal Server Error`，真实原因在 `exception` (`"504: Agent run timed out"`)，因此 OpenAI SDKs 会生成一个通用的 `InternalServerError`。 无论创建了对话，`X-OpenHands-ServerConversation-ID` 错误响应也不会携带。 在头部发送一个 UUID，以便提前知道ID，或者按状态搜索对话。
- 验证订单（聊天）：无用户消息 400，内容部分 400（系统消息太多），模型前缀 404，用户名 400 或缺失用户名 404，然后运行。 响应：首先是 `stream`/`store`/`previous_response_id` 400，然后是输入检查，然后是模型。 Auth 401 优先于一切。
- 网关对话与其他对话一样需要一个运行槽； 当
  `max_concurrent_runs` （默认10）一次性返回429，而不是排队。 对于新对话，429 不会创建任何内容，因此重试相同的请求（即使使用相同的呼叫者选择的 ID）是安全的。 同样适用于持续对话`F30.chat-reuse-run-limit-429`): 因为429错误在用户消息保存之前就出现了，所以  OpenAI  SDKs自动 429 重试不要添加重复的轮次。
- 网关对话没有标题（`autotitle` 关闭）并且永远不会被删除；
  `store: false` 不是保留控件。 删除它们
  `DELETE /api/conversations/{id}`.
- 可观察性标签以逗号分隔，并删除空格并接受任何其他文本，因此标签永远不会导致 422； 解析但不是对象的元数据获取 Pydantic 422 列表，而不可解析的 JSON 获取
  `must be a JSON object` 消息。
- CORS 中间件不公开任何自定义标头，因此跨源浏览器客户端无法读取 `X-OpenHands-ServerConversation-ID`。
- `examples/02_remote_agent_server/15_openai_compatible_gateway.py` 使用调用者的 `HOME` 在固定端口 8770 上启动自己的服务器并写入
  `gateway_demo` 个人资料； 不要在没有隔离 `HOME`、`OH_PERSISTENCE_DIR` 和工作目录的情况下将其与其他运行一起运行。
- 总是通过 `--no-validate` (验证会调用 stub 并将脚本延迟 8 到 64 秒，每次重试 5xx 错误，可以将运行推过网关超时)，以及 `--num-retries 0` (重试 5xx 错过 8 到 64 s，每次重试 5xx 会等待 8 到 64s)。 每个脚本使用新的存根名称：步计数器属于存根进程。
