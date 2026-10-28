<a id="conversation-lifecycle-and-catalog"></a>

# 对话生命周期和目录

如何一个智能体或其主机创建对话并找到它们：从保存的设置、存储的智能体个人资料或一个智能体（可选地，使用客户端选择的 id、父级、git 工作树、开始时间机密和可观测性头）启动对话，读取一个、几个或一页它们，按状态计数它们，重命名和重新标签它们，读取智能体的最终答案，并删除它们，同时保留工作区。 该目录在服务器重新启动后仍然存在。 运行、暂停和运行能力 (429) 存在于运行家族中； 事件套接字和事件搜索位于事件系列中。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/conversation_service.py`、`openhands-agent-server/openhands/agent_server/models.py`、`openhands-agent-server/openhands/agent_server/launch.py`、`openhands-sdk/openhands/sdk/conversation/request.py`、`openhands-sdk/openhands/sdk/conversation/response_utils.py`、`openhands-sdk/openhands/sdk/conversation/types.py`

需求：`llm`、`git`

Routes: `GET /api/conversations/search`, `GET /api/conversations/count`,
`GET /api/conversations/{conversation_id}`,
`GET /api/conversations/{conversation_id}/agent_final_response`,
`POST /api/conversations/{conversation_id}/children`,
`GET /api/conversations`, `POST /api/conversations`,
`DELETE /api/conversations/{conversation_id}`,
`PATCH /api/conversations/{conversation_id}`

<a id="sub-features"></a>

## 子功能

- `F04.create-settings`：从保存的设置中创建一个（`agent_settings` 加上 `secrets_encrypted`，即 Agent Canvas 路径）返回 201 `idle`，增加一个计数，只在 `base_state.json` 中持久化智能体，从不持久化 `meta.json`。
- `F04.create-inline-agent`：没有`kind`的内联`agent`被接受为`Agent`； API 键永远不会回显，并且响应会修剪内联技能。
- `F04.create-agent-profile`: `agent_profile_id` 解析存储的智能体配置文件及其 LLM 配置文件和记录 `launched_agent_profile`。
- `F04.create-validation`：缺少一个智能体源，两个智能体源，缺少一个工作区，标签键错误，`max_iterations` 0 和无效 `agent_settings` 均为 422； 未知的`agent_profile_id`是404； 具有悬空 LLM 参考的配置文件是 422 `unresolved_profile_references`； 无键为 401； 什么也没有被创造。
- `F04.create-validation-redaction`：由 LLM 键旁边的错误键入字段（在内联 `agent.llm` 和 `agent_settings.llm` 中）引起的 422 永远不会包含已发布的键； 如果错误与封闭对象相呼应，则键为 `<redacted>`。
- `F04.create-idempotent`：重新发布现有客户端 `conversation_id` 使用相同的对话返回 200，不会创建任何内容，并且不会重新发送初始消息。
- `F04.create-initial-message-run-false`：在不开始运行的情况下记录`initial_message`和`"run": false`（与`"run": true`运行相同的主体）。
- `F04.create-parent`：`parent_conversation_id`链接父级在`sub_conversation_ids`中列出的子级； 未知的父母、不同的工作区和自己的父母是422。
- `F04.create-worktree`: `worktree: true` 在 git 存储库内将对话移动到分支 `openhands/<id>` 上它自己的工作树中。
- `F04.create-observability`：`X-OpenHands-Observability-*` 标头经过验证（对于非对象元数据为 422）并存储在 `meta.json` 中。
- `F04.create-observability-precedence`: `observability_span_name`、`observability_tags`和`observability_parent_span_context`胜过头部，头部元数据合并到主体中（主体键胜出），当主体有None时，父-子跨度头部生效，过长或畸形的跨度名称头部、非标量头部元数据和空主体标签返回422。
- `F04.create-secrets`：开始时间 `StaticSecret` 值在创建响应中显示为掩码，并在 REST 处加密。
- `F04.create-secrets-get`：开始时间机密在创建后立即由`GET /api/conversations/{id}`列出。
- `F04.create-secrets-plain`：创建正文中的纯字符串机密值会被拒绝，并返回 422，而不是 500。
- `F04.run-real`：初始消息在DeepSeek闪存上运行到`finished`； 事件套接字重播运行，最终响应非空，并且自动标题命名对话。
- `F04.final-response`：`agent_final_response`在智能体应答之前为空，之后携带确切的`finish`消息，并且对于未知id为404。
- `F04.title-llm-profile`：使用 `title_llm_profile` 命名已保存的 LLM 配置文件，自动标题会调用该配置文件，而不是智能体的 LLM； 未知的用户头像名称会回退到智能体's LLM，从不失败创建。
- `F04.get`：`GET /api/conversations/{id}` 返回 `runtime_info`，修剪技能除非 `include_skills=true`，接受 32 十六进制 id 形式，并回答 404、422 和 401。
- `F04.batch-get`：`GET /api/conversations?ids=..` 返回与 id 对齐的列表，`null` 表示未知的列表，422 不带或带格式错误的 id。
- `F04.batch-get-limit`：一批中的 100 个 ID 因客户端错误而被拒绝，而不是 500。
- `F04.search-page`：`limit`、`next_page_id`页默认最新在前； `sort_order=CREATED_AT` 颠倒过来； 除非`include_skills=true`，否则技能将被削减； 错误限制和排序顺序为 422。
- `F04.search-filter`: `status` 过滤搜索并计数一致； 未知状态是 422。
- `F04.count`: `GET /api/conversations/count` 等于对话搜索列表的数量。
- `F04.patch-title`：PATCH `title` 被剥离，存储在 `meta.json` 中，碰撞 `updated_at` 并将对话移动到 `UPDATED_AT_DESC` 的顶部。
- `F04.patch-tags`: PATCH `tags` 替换 `meta.json` 和 `base_state.json` 中的整个映射，并在事件套接字上推送 `tags` 状态更新。
- `F04.patch-errors`：空的或 201 个字符的标题、错误的标签键和格式错误的 id 为 422； 无键为 401； 存储的值保持不变。
- `F04.patch-whitespace-title`：拒绝纯空白标题，而不是删除存储的标题。
- `F04.patch-unknown-id`: PATCH 对未知 id 回答 OpenAPI 文档声明的 404，而不是 200 `{"success": false}`。
- `F04.delete`: DELETE 停止一个正在进行的对话`PauseEvent`, `InterruptEvent`), 删除其状态，保留工作区移除一个工作树对话的工作树但是保留分支，孤儿子进程，并且稍后读取返回404（socket关闭4004）。 格式错误的 id 为 422，无密钥为 401。
- `F04.delete-unknown-id`: DELETE 对未知或已删除的 ID 回答 OpenAPI 文档声明的 404，而不是 400。
- `F04.restart-persist` 重启后，目录、状态、标题、标签、最终响应和事件回放都不会改变，删除的对话会保持删除状态。
- `F04.read-no-hydrate` 重启后，GET 批量获取、搜索和计数读取冷对话而不加载它（不`owner_lease.json`），而`agent_final_response` 加载它并声称租约。

- `F04.child-start`: `POST .../children` 开始一个真实模型任务，继承配置，并且有一个父链接，使用共享目录、隔离的 Git 工作树，或者共享的回退方案（非 Git 工作区）。
- `F04.child-unborn`：默认子启动在新的工作区中成功，其自动初始化的 git 存储库没有提交。
- `F04.child-errors`：缺失或无效的子启动字段为 422，未知的父启动字段为 404，无密钥为 401； 被拒绝的启动不会创建子项。
- `F04.child-capacity`：完全运行容量限制在创建对话或工作树之前拒绝 429 的子启动。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST: `POST /api/conversations`（主体 `StartConversationRequest`: `workspace`，恰好是 `agent_settings`、`agent_profile_id` 或 `agent` 之一，并且可选
  `conversation_id`, `parent_conversation_id`, `initial_message`, `worktree`,
  `secrets`, `secrets_encrypted`, `tags`, `max_iterations`, `autotitle`,
  `title_llm_profile`, `confirmation_policy`, `plugins`, `client_tools`,
  `observability_span_name`, `observability_tags`, `observability_metadata`,
  `observability_parent_span_context`, ...; 查询`include_skills`； 标头
  `X-OpenHands-Observability-Span-Name`, `-Tags`, `-Metadata`,
  `-Parent-Span-Context`在请求留空的主体字段中填充，而头部元数据则合并到主体之下。201表示新对话，200表示现有对话 `conversation_id`. `title_llm_profile` 命名 LLM 通过 [profile] 保存的 `POST /api/profiles/{name}` (the) LLM 家庭资料。 `llm set` here).
- REST 读取：`GET /api/conversations/{conversation_id}`，
  `GET /api/conversations?ids=..&ids=..`（小于100），
  `GET /api/conversations/search` (`page_id`, `limit` 1..100, `status`,
  `sort_order`, `include_skills`), `GET /api/conversations/count` (`status`),
  `GET /api/conversations/{conversation_id}/agent_final_response`.
- REST 写：`PATCH /api/conversations/{conversation_id}` (`title`, `tags`),
  `DELETE /api/conversations/{conversation_id}`.
- WebSocket（由事件系列拥有，此处用作第二个视图）：
  `/sockets/events/{conversation_id}` 重播初始消息并运行，按 PATCH、`PauseEvent` 上的 `ConversationStateUpdateEvent` 键 `tags` 并
  `InterruptEvent` 当正在运行的对话被删除时，并以 4004 关闭已删除的 ID。
- SDK: `RemoteConversation(agent=..., workspace=RemoteWorkspace(...))` 发布创建（并使用 `conversation_id` 重新附加），读取状态
  `GET /api/conversations/{id}`、`set_title()` 发送 PATCH 和 `close()`
  with `delete_on_close=True` sends the DELETE
  (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`).
- TypeScript 客户端 (`clients/typescript/src/client/conversation-client.ts`)：
  `createConversation`（重试与服务器通告`idempotent_conversation_create_v1`时相同的`conversation_id`一次），
  `searchConversations`, `countConversations`, `getConversations`,
  `getConversation`, `getAgentFinalResponse`, `updateConversation`,
  `deleteConversation`; `ConversationManager` 包含它们（`getAllConversations` 通过搜索页面）。
- Agent Canvas（仅上下文）：新对话流程读取
  `GET /api/settings` 与 `X-Expose-Secrets: encrypted` 和帖子
  `agent_settings` 与 `secrets_encrypted: true`（什么
  `conversation start` 确实）； 侧边栏使用搜索、计数、标题和标签； 重命名和删除使用 PATCH 和 DELETE。
- 下面的食谱使用 REST 到 `api`、CLI 的 `conversation start`（Agent Canvas 创建路径）以及事件套接字到 `ws`。 批量获取重复密钥（`api --query ids=A --query ids=B`）； 99-id 和 100-id 批次会通过 `exec` 运行的一个小型 `urllib` 助手，因此该配方不会拼出 100 个标志。

- REST: `POST /api/conversations/{conversation_id}/children` 接受 `task`、可选的 `title` 和 `isolation`（默认为 `worktree`，或 `shared`），并返回 201 以及 `conversation_id`、`parent_conversation_id`、状态、标题、工作区和实际隔离。 子级继承父级的配置并仅接收新任务，而不接收父级的历史记录。 A 工作树从存储库的默认分支开始； 非 git 工作区则退回到共享。 该路由也是默认启动器
  `start_child_conversation` 工具 (F27)，由 PR #5126 引入。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已实时运行并已导出 (`launch --new`)，`doctor` 正常，并且
  设置`$DEEPSEEK_API_KEY`； 下面的块保存 DeepSeek 配置文件。
- `git` 已安装 (工作树测试夹具)。 不需要 `tmux` 或浏览器：这里的每个智能体都有 `tools: []` (`--tools none`)，它只保留内置的
  `finish` 和 `think` 工具。
- 下面的块按顺序创建：工作区 `$W`，一个未知的 id
  `$NOPE`，一个离线内联智能体 `$OFFLINE_AGENT`（无法访问`base_url`，从未联系过，因为这些对话从未运行，具有一项内联技能），一个总是用`QA_F04_DONE`（`$STUB_AGENT`）调用`finish`的`llm-stub`，一个挂起的`llm-stub`（`$HANG_AGENT`，用于删除正在运行的对话），两个自动标题文本回复存根（`qa-f04-title`，保存为LLM配置文件`qa-f04-title`而不激活它，以及
  `qa-f04-reply`、智能体 `$REPLY_AGENT`）、原始 422 个主体的目录 `$RAW`、git 存储库 `$REPO` 和批处理助手
  `$F/qa-f04-batch.py`（重复`ids`查询键； 当状态和对齐的 id 匹配时打印 `QA_BATCH_OK`）。 仅当配方需要精确回复或必须查看调用了哪个提供者时，存根才代表提供者； 真实模型运行是`F04.run-real`。

```sh
control-agent-server llm preset deepseek
F="$AGENT_SERVER_VERIFY_RUN/fixtures"
W="$F/qa-f04-ws"
mkdir -p "$W"
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
OFFLINE_AGENT='{"llm": {"model": "openai/qa-offline", "api_key": "qa-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": [], "agent_context": {"skills": [{"name": "qa-f04-skill", "content": "Answer briefly."}]}}'
STUB=$(control-agent-server fixture llm-stub --name qa-f04-stub --step 'tool:finish:{"message":"QA_F04_DONE"}' --print-path)
STUB_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$STUB/v1\", \"num_retries\": 0}, \"tools\": []}"
HANG=$(control-agent-server fixture llm-stub --name qa-f04-hang --step hang:300 --print-path)
HANG_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG/v1\", \"num_retries\": 0}, \"tools\": []}"
TSTUB=$(control-agent-server fixture llm-stub --name qa-f04-title --step 'reply:QA F04 profile title' --print-path)
control-agent-server llm set --profile qa-f04-title --model openai/qa-title --base-url "$TSTUB/v1" --no-api-key --num-retries 0 --no-activate --no-validate
control-agent-server api GET /api/profiles --check active_profile eq deepseek-flash --quiet
RSTUB=$(control-agent-server fixture llm-stub --name qa-f04-reply --step 'reply:QA F04 agent title' --print-path)
REPLY_AGENT="{\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$RSTUB/v1\", \"num_retries\": 0}, \"tools\": []}"
RAW="$F/qa-f04-422"
mkdir -p "$RAW"
REPO=$(control-agent-server fixture git-repo --name qa-f04-repo --print-path)
cat > "$F/qa-f04-batch.py" <<'EOF'
"""GET /api/conversations with repeated ids; prints QA_BATCH_OK on a match."""
import json, os, sys, urllib.error, urllib.parse, urllib.request

ids, statuses = sys.argv[1].split(","), {int(s) for s in sys.argv[2].split(",")}
want = sys.argv[3].split(",") if len(sys.argv) > 3 else None
query = urllib.parse.urlencode([("ids", i) for i in ids])
request = urllib.request.Request(
    f"{os.environ['AGENT_SERVER_URL']}/api/conversations?{query}",
    headers={"X-Session-API-Key": os.environ["SESSION_API_KEY"]},
)
try:
    with urllib.request.urlopen(request, timeout=60) as response:
        status, body = response.status, json.loads(response.read())
except urllib.error.HTTPError as error:
    status, body = error.code, json.loads(error.read() or b"null")
got = [item and item["id"] for item in body] if isinstance(body, list) else body
print(json.dumps({"sent": len(ids), "status": status, "body": got})[:1500])
ok = status in statuses and (want is None or got == [None if w == "null" else w for w in want])
print("QA_BATCH_OK" if ok else "QA_BATCH_MISMATCH")
sys.exit(0 if ok else 1)
EOF
```

- **从保存的设置创建 (`F04.create-settings`)。** Agent Canvas
  路径：`GET /api/settings` 中的 `agent_settings`（已加密），无提示词。
  ```sh
  N1=$(control-agent-server api GET /api/conversations/count --field .)
  START=$(control-agent-server conversation start --tools none --no-autotitle --tag qa=f04 --workspace "$W" --save F04.create-settings/start)
  CID=$(python3 -c 'import json, sys; d = json.loads(sys.argv[1]); assert d["status"] == 201 and d["execution_status"] == "idle", d; print(d["id"])' "$START")
  control-agent-server api GET "/api/conversations/$CID" --expect 200 --check execution_status eq idle \
    --check agent.kind eq Agent --check agent.llm.model eq deepseek/deepseek-flash --check agent.tools len-eq 0 \
    --check agent.llm.api_key ne "$DEEPSEEK_API_KEY" --check tags.qa eq f04 --check title missing \
    --check workspace.working_dir eq "$W" --save F04.create-settings/get
  control-agent-server api GET /api/conversations/count --check . eq $((N1 + 1))
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/meta.json" --max-chars 200 \
    --check agent missing --check secrets_encrypted eq true --check autotitle eq false --check tags.qa eq f04
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/base_state.json" --max-chars 200 \
    --check agent.llm.model eq deepseek/deepseek-flash --check execution_status eq idle
  ```
  创建的响应码是201，`idle`的计数增加了一，`meta.json`没有
  `agent` 和 `base_state.json` 保留它。
- **内嵌智能体 (`F04.create-inline-agent`).** `agent` 载荷没有
  `kind`.
  ```sh
  IID=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" \
    --expect 201 --check agent.kind eq Agent --check agent.llm.model eq openai/qa-offline \
    --check agent.llm.api_key ne qa-offline-key --check execution_status eq idle \
    --check agent.agent_context.skills len-eq 0 \
    --check launched_agent_profile missing --save F04.create-inline-agent/start --field id)
  control-agent-server api GET "/api/conversations/$IID" --expect 200 --check agent.kind eq Agent \
    --check agent.llm.base_url eq http://127.0.0.1:9/v1 --check agent.llm.api_key ne qa-offline-key
  ```
  两种观点都说`kind``Agent`； API键返回为`null`，并且创建响应会修剪`F04.get`显示存储的[inline skill]。
- **已存储智能体配置文件 (`F04.create-agent-profile`)。**引用已保存的 `deepseek-flash` LLM 配置文件的智能体配置文件。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f04-agent --json '{"llm_profile_ref": "deepseek-flash", "tools": []}' --expect 201
  PID=$(control-agent-server api GET /api/agent-profiles/qa-f04-agent --field profile.id)
  AID=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$PID\", \"autotitle\": false}" \
    --expect 201 --check launched_agent_profile.agent_profile_id eq "$PID" \
    --check agent.llm.model eq deepseek/deepseek-flash --check agent.tools len-eq 0 \
    --save F04.create-agent-profile/start --field id)
  control-agent-server api GET "/api/conversations/$AID" --check launched_agent_profile.agent_profile_id eq "$PID" \
    --check launched_agent_profile.revision exists --check agent.llm.model eq deepseek/deepseek-flash
  ```
  记录了用户ID，并运行了该用户的模型。
- **创建验证 (`F04.create-validation`).**每个错误的请求都会被拒绝，并且不会创建任何内容。

  需要：`F04.create-agent-profile`
  ```sh
  N2=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}}" \
    --expect 422 --check detail.0.msg contains 'must be provided' --save F04.create-validation/no-agent-source
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$PID\", \"agent_settings\": {}}" \
    --expect 422 --check detail.0.msg contains 'mutually exclusive'
  control-agent-server api POST /api/conversations --json "{\"agent\": $OFFLINE_AGENT}" --expect 422 --check detail.0.loc contains workspace
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"tags\": {\"Bad-Key\": \"x\"}}" \
    --expect 422 --check detail.0.msg contains 'lowercase alphanumeric'
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"max_iterations\": 0}" --expect 422
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_settings\": {\"agent_kind\": \"nope\"}}" --expect 422
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$NOPE\"}" \
    --expect 404 --check detail contains 'not found'
  control-agent-server api POST /api/agent-profiles/qa-f04-dangling --json '{"llm_profile_ref": "qa-f04-missing", "tools": []}' --expect 201
  DANGLING=$(control-agent-server api GET /api/agent-profiles/qa-f04-dangling --field profile.id)
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_profile_id\": \"$DANGLING\"}" \
    --expect 422 --check detail.code eq unresolved_profile_references \
    --check detail.dangling_llm_profile_ref eq qa-f04-missing --save F04.create-validation/dangling-profile
  control-agent-server api DELETE /api/agent-profiles/qa-f04-dangling --expect 200
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT}" --auth none --expect 401
  control-agent-server api GET /api/conversations/count --check . eq "$N2"
  ```
  所有状态匹配，计数不变。
- **422 个实体将 LLM 钥匙放在外面 (`F04.create-validation-redaction`)。**在内联中，在哨兵值键旁边输入错误的 `num_retries`
  `agent.llm` 和`agent_settings.llm` 中一次。

  需要：`F04.create-validation`
  ```sh
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": {\"llm\": {\"model\": \"openai/qa\", \"api_key\": \"QA-F04-KEY-SIBLING\", \"num_retries\": \"many\"}, \"tools\": []}}" \
    --expect 422 --check detail.0.loc contains num_retries --raw-out "$RAW/agent-sibling.json" --save F04.create-validation-redaction/agent-sibling
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent_settings\": {\"llm\": {\"model\": \"openai/qa\", \"api_key\": \"QA-F04-KEY-SETTINGS\", \"num_retries\": \"many\"}}}" \
    --expect 422 --check detail.0.msg contains num_retries --check detail.0.input.agent_settings.llm.api_key eq '<redacted>' \
    --raw-out "$RAW/settings-sibling.json" --save F04.create-validation-redaction/settings-sibling
  test -s "$RAW/agent-sibling.json"
  test -s "$RAW/settings-sibling.json"
  if grep -l 'QA-F04-KEY' "$RAW/agent-sibling.json" "$RAW/settings-sibling.json"; then false; fi
  control-agent-server api GET /api/conversations/count --check . eq "$N2"
  ```
  两个都是422命名`num_retries`； inline-智能体错误只携带坏值，而`agent_settings` 错误则会将整个主体回显
  `api_key` 替换为 `<redacted>`。 两个原始主体都不包含哨兵值。
- **使用客户端 ID 进行幂等创建 (`F04.create-idempotent`)。**两次相同的主体，带有一条初始消息，表明存根用 `finish` 进行答复。
  ```sh
  QID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  QBODY="{\"conversation_id\": \"$QID\", \"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $STUB_AGENT, \"autotitle\": false, \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"Finish now.\"}]}}"
  N3=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /api/conversations --json "$QBODY" --expect 201 --check id eq "$QID" --save F04.create-idempotent/first
  control-agent-server conversation wait "$QID" --until finished --timeout 60
  control-agent-server api POST /api/conversations --json "$QBODY" --expect 200 --check id eq "$QID" \
    --check execution_status eq finished --save F04.create-idempotent/second
  control-agent-server api GET /api/conversations/count --check . eq $((N3 + 1))
  control-agent-server api GET "/api/conversations/$QID/events/count" --query source=user --check . eq 1
  ```
  第二个 POST 是 200，完成对话后计数增加了一次，还有恰好一次用户事件。
- **`initial_message.run: false` (`F04.create-initial-message-run-false`)，已知错误。**相同的存根主体两次，首先使用 `"run": true`（控件：存根在窗口内完成得很好），然后使用 `"run": false`。
  ```sh
  YR=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $STUB_AGENT, \"autotitle\": false, \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"QA F04 run true.\"}], \"run\": true}}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$YR" --until finished --timeout 15
  NR=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $STUB_AGENT, \"autotitle\": false, \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"QA F04 run false.\"}], \"run\": false}}" \
    --expect 201 --save F04.create-initial-message-run-false/start --field id)
  control-agent-server conversation events "$NR" --kinds MessageEvent --contains 'QA F04 run false.' --expect-count 1
  sleep 15; control-agent-server api GET "/api/conversations/$NR" --check execution_status eq idle --save F04.create-initial-message-run-false/get  # response.body.execution_status 匹配 '^(running|finished)$'
  control-agent-server conversation events "$NR" --kinds ActionEvent --expect-count 0
  ```
  预期：消息被录制并且对话保持 `idle` 直到
  `run`（无智能体操作）。 今天，它在一秒钟内 `finished`：
  `start_conversation` 使用 `run=False` 发送初始消息，然后始终调用 `event_service.run()`，从不读取 `initial_message.run`（默认值为 `false`）。 该修复可能会从创建中删除该字段模式； 然后重写这个项目符号。
- **父级和子级 (`F04.create-parent`)。**一个内的链接工作区。

  需要：`F04.create-inline-agent`
  ```sh
  CHILD=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"parent_conversation_id\": \"$IID\"}" \
    --expect 201 --check parent_conversation_id eq "$IID" --field id)
  control-agent-server api GET "/api/conversations/$IID" --check sub_conversation_ids contains "$CHILD" --save F04.create-parent/parent
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W/other\"}, \"agent\": $OFFLINE_AGENT, \"parent_conversation_id\": \"$IID\"}" \
    --expect 422 --check detail contains 'different workspace'
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"parent_conversation_id\": \"$NOPE\"}" \
    --expect 422 --check detail contains 'not found'
  control-agent-server api POST /api/conversations --json "{\"conversation_id\": \"$NOPE\", \"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"parent_conversation_id\": \"$NOPE\"}" \
    --expect 422 --check detail contains 'own parent'
  ```
  父母列出孩子； 这三条无效链接的响应码是 422。
- **Git 工作树 (`F04.create-worktree`).** `worktree: true` 在存储库上。
  ```sh
  WT=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$REPO\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"worktree\": true}" \
    --expect 201 --check workspace.working_dir ne "$REPO" --field id)
  control-agent-server api GET "/api/conversations/$WT" \
    --check workspace.working_dir eq "$AGENT_SERVER_VERIFY_RUN/worktrees/$WT/qa-f04-repo" --save F04.create-worktree/get
  test -n "$(git -C "$REPO" branch --list "openhands/$WT")"
  git -C "$REPO" worktree list | grep -q "$AGENT_SERVER_VERIFY_RUN/worktrees/$WT/qa-f04-repo"
  test "$(git -C "$AGENT_SERVER_VERIFY_RUN/worktrees/$WT/qa-f04-repo" rev-parse HEAD)" = "$(git -C "$REPO" rev-parse HEAD)"
  ```
  `<worktree root>/<id>/qa-f04-repo` 在分支上工作
  `openhands/<id>`，在存储库的 HEAD 中签出。
- **可观测性标头 (`F04.create-observability`)。**标头元数据必须是 JSON 对象。
  ```sh
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT}" \
    --header 'X-OpenHands-Observability-Metadata: nope' --expect 422 --check detail contains 'must be a JSON object'
  OID=$(control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" \
    --header 'X-OpenHands-Observability-Metadata: {"team": "qa"}' --header 'X-OpenHands-Observability-Tags: qa-f04, nightly' \
    --header 'X-OpenHands-Observability-Span-Name: qa-f04-span' --expect 201 --field id)
  control-agent-server state cat "server/workspace/conversations/${OID//-/}/meta.json" --max-chars 200 \
    --check observability_metadata.team eq qa --check observability_tags len-eq 2 \
    --check observability_tags contains qa-f04 --check observability_span_name eq qa-f04-span
  ```
  非JSON元数据为422； 有效的头部位于`meta.json`（它们不是`ConversationInfo`的一部分）。
- ** 请求体 vs 头部 (`F04.create-observability-precedence`).** 如果在请求体和头部都设置了观察指标字段，那么只在父级SPAN头部，然后是无效的头部和请求体值。
  ```sh
  N6=$(control-agent-server api GET /api/conversations/count --field .)
  OB=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"observability_span_name\": \"qa-f04-body-span\", \"observability_tags\": [\"qa-body\"], \"observability_metadata\": {\"team\": \"body\", \"only_body\": \"b\"}, \"observability_parent_span_context\": \"qa-body-parent\"}" \
    --header 'X-OpenHands-Observability-Span-Name: qa-f04-header-span' --header 'X-OpenHands-Observability-Tags: qa-header' \
    --header 'X-OpenHands-Observability-Metadata: {"team": "header", "only_header": "h"}' \
    --header 'X-OpenHands-Observability-Parent-Span-Context: qa-header-parent' --expect 201 --field id)
  control-agent-server state cat "server/workspace/conversations/${OB//-/}/meta.json" --max-chars 200 \
    --check observability_span_name eq qa-f04-body-span --check observability_tags len-eq 1 --check observability_tags contains qa-body \
    --check observability_metadata.team eq body --check observability_metadata.only_body eq b --check observability_metadata.only_header eq h \
    --check observability_parent_span_context eq qa-body-parent
  OH=$(control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" \
    --header 'X-OpenHands-Observability-Parent-Span-Context: qa-header-parent' --expect 201 --field id)
  control-agent-server state cat "server/workspace/conversations/${OH//-/}/meta.json" --max-chars 200 \
    --check observability_parent_span_context eq qa-header-parent --check observability_span_name eq conversation --check observability_tags len-eq 0
  LONGSPAN=$(python3 -c 'print("s" * 129)')
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT}" \
    --header "X-OpenHands-Observability-Span-Name: $LONGSPAN" --expect 422 --check detail.0.msg contains 'maximum length of 128' --save F04.create-observability-precedence/long-span
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT}" \
    --header 'X-OpenHands-Observability-Span-Name: qa f04!' --expect 422 --check detail.0.msg contains 'may only contain'
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT}" \
    --header 'X-OpenHands-Observability-Metadata: {"nested": {"a": 1}}' --expect 422 --check detail.0.msg contains 'must be a scalar'
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"observability_tags\": [\"\"]}" \
    --expect 422 --check detail.0.msg contains 'non-empty strings'
  control-agent-server api GET /api/conversations/count --check . eq $((N6 + 2))
  ```
  在设置了这两个选项后，`meta.json` 保留了主体的 span 名称、标签和父 span 上下文，而 `only_header` 的元数据则保持不变，`team` 仍然为 `body`。 仅存储一个父级跨度头（跨度名称默认为 [span name]）
  `conversation`). 四个无效值是 422，不会产生任何结果。
- **开始时间机密 (`F04.create-secrets`).**创建主体中的 `StaticSecret`。
  ```sh
  SECID=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"secrets\": {\"QA_F04_TOKEN\": {\"kind\": \"StaticSecret\", \"value\": \"qa-f04-secret-value\"}}}" \
    --expect 201 --check secret_registry.secret_sources.QA_F04_TOKEN.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F04_TOKEN.value ne qa-f04-secret-value --save F04.create-secrets/start --field id)
  control-agent-server state cat "server/workspace/conversations/${SECID//-/}/meta.json" --max-chars 200 \
    --check secrets.QA_F04_TOKEN.kind eq StaticSecret --not-contains qa-f04-secret-value
  control-agent-server state cat "server/workspace/conversations/${SECID//-/}/base_state.json" --max-chars 200 --not-contains qa-f04-secret-value
  ```
  响应列出了机密及其值被遮罩。 在磁盘上，它是加密的。
- **开始时间机密对 GET (`F04.create-secrets-get`) 可见，已知错误。**阅读上一个项目符号中创建的对话。

  需要：`F04.create-secrets`
  ```sh
  control-agent-server api GET "/api/conversations/$SECID" --expect 200 \
    --check secret_registry.secret_sources.QA_F04_TOKEN.kind eq StaticSecret --save F04.create-secrets-get/get  # bug：状态 eq 200 && response.body.secret_registry.secret_sources 存在 && 检查.0.实际 eq null
  ```
  预期：GET 列出 `QA_F04_TOKEN`，就像创建响应一样。 今天
  它返回 `{"secret_sources": {}}`：开始时间机密应用于现场状态，无需自动保存，并且 GET 读取
  `base_state.json` 快照。 机密出现在下一个状态保存之后（标签 PATCH、消息），因此运行时本身仍然拥有它。
- **纯字符串机密值 (`F04.create-secrets-plain`).**
  `POST .../secrets` 接受 `{"NAME": "value"}`，但创建主体仅接受机密个对象，因此纯字符串会被拒绝，值为 422。
  ```sh
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"secrets\": {\"QA_F04_PLAIN\": \"qa-f04-plain-value\"}}" \
    --expect 422 --check detail.0.type eq model_attributes_type --check detail.0.loc.2 eq QA_F04_PLAIN \
    --save F04.create-secrets-plain/start
  ```
  答案是一个标准的422 验证错误
  `secrets.QA_F04_PLAIN` (`model_attributes_type`)，绝不是 500。
- **真实运行 (`F04.run-real`).** DeepSeek 闪答一行提示词； 自动标题已打开。
  ```sh
  RID=$(control-agent-server conversation start --tools none --workspace "$W/qa-real" \
    --prompt 'Reply with the single word: pong' --wait --until finished --timeout 300 --save F04.run-real/start --print-id)
  control-agent-server api GET "/api/conversations/$RID" --check execution_status eq finished \
    --check agent.llm.model eq deepseek/deepseek-flash --check stats.usage_to_metrics.default.model_name exists --save F04.run-real/get
  control-agent-server ws listen "/sockets/events/$RID" --query resend_mode=all --until-kind ConversationStateUpdateEvent \
    --until key=execution_status --until value=finished --duration 20 --save F04.run-real/replay
  control-agent-server conversation events "$RID" --kinds MessageEvent --contains 'single word: pong'
  control-agent-server api GET "/api/conversations/$RID/events/count" --query source=user --check . eq 1
  control-agent-server api GET "/api/conversations/$RID/agent_final_response" --expect 200 --check response matches '\S' --save F04.run-real/final-response
  control-agent-server api GET "/api/conversations/$RID" --check title exists --until-ok 60 --save F04.run-real/title
  ```
  运行结束，回放以 `execution_status` `finished` 结束，第提示词被记录一次作为用户的 `MessageEvent`，最终响应非空（模型选择的 `finish` 消息或纯回复），且标题出现（第二个 LLM 调用不发出事件，因此有界轮询）。
- **最终回复(`F04.final-response`)。**在智能体应答之前为空，然后是存根的 `finish` 消息。
  ```sh
  FID=$(control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $STUB_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api GET "/api/conversations/$FID/agent_final_response" --expect 200 --check response eq '' --save F04.final-response/empty
  control-agent-server conversation send "$FID" --text 'Finish now.' --wait --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$FID/agent_final_response" --expect 200 --check response eq QA_F04_DONE --save F04.final-response/finish
  control-agent-server conversation events "$FID" --kinds ActionEvent --contains FinishAction
  control-agent-server api GET "/api/conversations/$FID" --check execution_status eq finished --check title missing
  control-agent-server api GET "/api/conversations/$NOPE/agent_final_response" --expect 404
  control-agent-server api GET "/api/conversations/$FID/agent_final_response" --auth none --expect 401
  ```
  `{"response": ""}`，然后`{"response": "QA_F04_DONE"}`； `autotitle: false` 将标题留空； 未知 ID 为 404。
- **已保存的 LLM 个人资料中的标题 (`F04.title-llm-profile`)。** 智能体
  `$REPLY_AGENT` 回答 `QA F04 agent title` 每个电话，并且保存的个人资料 `qa-f04-title` 回答 `QA F04 profile title`，因此标题表明是哪个 LLM 写的； 两个存根都记录它们收到的请求。
  ```sh
  TP=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $REPLY_AGENT, \"title_llm_profile\": \"qa-f04-title\", \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"Name this QA conversation.\"}]}}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$TP" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$TP" --check title eq 'QA F04 profile title' --until-ok 30 --save F04.title-llm-profile/profile
  control-agent-server sink read --name qa-f04-title --contains 'Name this QA conversation' --expect-min 1
  control-agent-server sink read --name qa-f04-reply --contains 'Generate a title' --expect-max 0
  control-agent-server state cat "server/workspace/conversations/${TP//-/}/meta.json" --max-chars 200 --check title_llm_profile eq qa-f04-title
  TU=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $REPLY_AGENT, \"title_llm_profile\": \"qa-f04-missing\", \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"Name this other QA conversation.\"}]}}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$TU" --until finished --timeout 60
  control-agent-server api GET "/api/conversations/$TU" --check title eq 'QA F04 agent title' --until-ok 30 --save F04.title-llm-profile/missing-profile
  control-agent-server sink read --name qa-f04-reply --contains 'Generate a title' --expect-min 1
  ```
  该用户写了第一篇标题和智能体's LLM 未见标题请求。 在未知的配置下，创建仍然返回 201 智能体's LLM 写标题（现在它的草稿栏里有一个标题请求）。 标题中的任何空缺都会导致截断回退方案 (消息文本本身)
- **阅读一篇对话 (`F04.get`)。**技能修剪、身份形式和错误。

  需要：`F04.create-parent`
  ```sh
  control-agent-server api GET "/api/conversations/$IID" --expect 200 --check id eq "$IID" \
    --check runtime_info.runtime_status eq available --check runtime_info.can_resume eq true \
    --check agent.agent_context.skills len-eq 0 --check sub_conversation_ids contains "$CHILD" --save F04.get/default
  control-agent-server api GET "/api/conversations/$IID" --query include_skills=true \
    --check agent.agent_context.skills len-eq 1 --check agent.agent_context.skills.0.name eq qa-f04-skill --save F04.get/include-skills
  IHEX=${IID//-/}
  control-agent-server api GET "/api/conversations/$IHEX" --expect 200 --check id eq "$IID"
  control-agent-server api GET "/api/conversations/$NOPE" --expect 404 --save F04.get/unknown
  control-agent-server api GET /api/conversations/not-a-uuid --expect 422
  control-agent-server api GET "/api/conversations/$IID" --auth none --expect 401
  ```
  默认响应会修剪 inline 技能。 `include_skills=true`返回它。 32位十六进制形式解析为虚线 id。
- **批量获取(`F04.batch-get`).**结果与 id 对齐。

  需要：`F04.create-inline-agent`、`F04.final-response`
  ```sh
  control-agent-server api GET /api/conversations --query ids="$IID" --expect 200 --check . len-eq 1 \
    --check 0.id eq "$IID" --check 0.runtime_info.runtime_status eq available --check 0.agent.agent_context.skills len-eq 0 --save F04.batch-get/one
  control-agent-server api GET /api/conversations --query ids="$IID" --query include_skills=true --check 0.agent.agent_context.skills len-eq 1
  control-agent-server api GET /api/conversations --query ids="$IID" --query ids="$NOPE" --query ids="$FID" --expect 200 \
    --check . len-eq 3 --check 0.id eq "$IID" --check 1 eq null --check 2.id eq "$FID" --save F04.batch-get/aligned
  IDS99=$(python3 -c 'import uuid; print(",".join(str(uuid.uuid4()) for _ in range(99)))')
  NULLS99=$(python3 -c 'print(",".join(["null"] * 99))')
  control-agent-server exec --expect-output QA_BATCH_OK -- python3 "$F/qa-f04-batch.py" "$IDS99" 200 "$NULLS99"
  control-agent-server api GET /api/conversations --expect 422 --check detail.0.loc contains ids
  control-agent-server api GET /api/conversations --query ids=not-a-uuid --expect 422
  control-agent-server api GET /api/conversations --query ids="$IID" --auth none --expect 401
  ```
  返回三个 id `[IID, null, FID]`；未知 id 99 返回 99 个 null。 缺少或格式不正确的 ID 会导致 422 错误。
- **一批 100 个 ID (`F04.batch-get-limit`)。**路由器将批次限制为 99 个 id。
  ```sh
  IDS100=$(python3 -c 'import uuid; print(",".join(str(uuid.uuid4()) for _ in range(100)))')
  control-agent-server exec --expect-output QA_BATCH_OK --expect-output 'at most 99 items' --save F04.batch-get-limit/hundred -- python3 "$F/qa-f04-batch.py" "$IDS100" 422
  ```
  100 个 ID 是一个 422 错误，其详细信息指出了限制 ("列表最多只能有 99 个项目")。 OpenAPI 模式 `maxItems: 99` `ids`。
- **搜索页面(`F04.search-page`)。**两个新的对话使最新的两个对话具有确定性。
  ```sh
  S1=$(control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" --expect 201 --field id)
  S2=$(control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$W\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api GET /api/conversations/search --query limit=1 --expect 200 --check items len-eq 1 \
    --check items.0.id eq "$S2" --check items.0.runtime_info.runtime_status eq available \
    --check next_page_id eq "${S1//-/}" --save F04.search-page/first
  control-agent-server api GET /api/conversations/search --query limit=1 --query page_id="${S1//-/}" --check items.0.id eq "$S1" --save F04.search-page/second
  control-agent-server api GET /api/conversations/search --query sort_order=CREATED_AT --query limit=100 --check items.-1.id eq "$S2" --check next_page_id missing
  control-agent-server api GET /api/conversations/search --query limit=100 --check items not-contains qa-f04-skill --quiet
  control-agent-server api GET /api/conversations/search --query limit=100 --query include_skills=true --check items contains qa-f04-skill --quiet
  control-agent-server api GET /api/conversations/search --query limit=0 --expect 422
  control-agent-server api GET /api/conversations/search --query limit=101 --expect 422
  control-agent-server api GET /api/conversations/search --query sort_order=bogus --expect 422
  control-agent-server api GET /api/conversations/search --auth none --expect 401
  ```
  第一页包含 `S2` 并指向 `S1`（32-位）。 这一页的开头是
  `S1`; 升序排列以 `S2` 结束。 除非`include_skills=true`，否则列表中不存在内联技能`qa-f04-skill`。
- **状态过滤器(`F04.search-filter`).**已完成和空闲的对话
  from the bullets above.

  需要：`F04.create-inline-agent`、`F04.create-agent-profile`、`F04.create-idempotent`、`F04.final-response`
  ```sh
  control-agent-server api GET /api/conversations/search --query status=finished --check items contains "$FID" \
    --check items contains "$QID" --check items not-contains "$IID" --check items.0.execution_status eq finished --save F04.search-filter/finished
  NF=$(control-agent-server api GET /api/conversations/count --query status=finished --field .)
  control-agent-server api GET /api/conversations/search --query status=finished --query limit=100 --check items len-eq "$NF"
  control-agent-server api GET /api/conversations/search --query status=idle --check items contains "$AID" --check items not-contains "$FID"
  control-agent-server api GET /api/conversations/search --query status=bogus --expect 422
  control-agent-server api GET /api/conversations/count --query status=bogus --expect 422
  ```
  完成的页面包含和 DeepSeek 只包含会话，大小等于 `count?status=finished`. `contains` 在物品的任何地方匹配 JSON因此，正向检查名称为没有其他项目链接到的会话`$IID` 也会匹配其子节点 `parent_conversation_id`).
- **计数 (`F04.count`)。**总数与搜索一致。
  ```sh
  N=$(control-agent-server api GET /api/conversations/count --expect 200 --field .)
  control-agent-server api GET /api/conversations/search --query limit=100 --check items len-eq "$N" --save F04.count/search-all
  control-agent-server api GET /api/conversations/count --auth none --expect 401
  ```
  创建时计数增加（第一条横线），删除时计数减少（删除横线）。
- **重命名(`F04.patch-title`)。** SDK的`set_title()`请求。

  需要：`F04.create-settings`
  ```sh
  U0=$(control-agent-server api GET "/api/conversations/$CID" --field updated_at)
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"title": "  QA F04 title  "}' --expect 200 --check success eq true --save F04.patch-title/patch
  control-agent-server api GET "/api/conversations/$CID" --check title eq 'QA F04 title' --check updated_at ne "$U0" --check tags.qa eq f04 --save F04.patch-title/get
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/meta.json" --max-chars 200 --check title eq 'QA F04 title'
  control-agent-server api GET /api/conversations/search --query sort_order=UPDATED_AT_DESC --query limit=1 --check items.0.id eq "$CID"
  ```
  标题被去除并存储，标签未受影响，对话现在是最新的。
- **重新标记 (`F04.patch-tags`).**标签取代整个地图； 套接字看到它是实时的。

  需要：`F04.create-settings`
  ```sh
  control-agent-server ws start "/sockets/events/$CID" --name qa-f04-tags --duration 120
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"tags": {"env": "qa", "run": "one"}}' --check success eq true
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"tags": {"env": "prod"}}' --check success eq true --save F04.patch-tags/replace
  control-agent-server api GET "/api/conversations/$CID" --check tags.env eq prod --check tags.run missing --check tags.qa missing \
    --check title eq 'QA F04 title' --save F04.patch-tags/get
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/base_state.json" --max-chars 200 --check tags.env eq prod --check tags.run missing
  control-agent-server state cat "server/workspace/conversations/${CID//-/}/meta.json" --max-chars 200 --check tags.env eq prod
  control-agent-server ws stop qa-f04-tags --kinds ConversationStateUpdateEvent --contains '"key": "tags", "value": {"env": "prod"}' \
    --expect-min 1 --wait 15 --save F04.patch-tags/live
  control-agent-server ws listen "/sockets/events/$CID" --query resend_mode=all --until-kind ConversationStateUpdateEvent \
    --until key=tags --until value.env=prod --duration 15
  ```
  只剩下 `env=prod` 了，两个文件中都一样。 直播和回放都携带了 `tags` 状态更新。
- **PATCH 错误 (`F04.patch-errors`)。**被拒绝的更新没有任何变化。

  需要：`F04.create-settings`
  ```sh
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"title": ""}' --expect 422
  LONG=$(python3 -c 'print("x" * 201)')
  control-agent-server api PATCH "/api/conversations/$CID" --json "{\"title\": \"$LONG\"}" --expect 422
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"tags": {"Bad-Key": "x"}}' --expect 422
  control-agent-server api PATCH /api/conversations/not-a-uuid --json '{"title": "QA"}' --expect 422
  control-agent-server api PATCH "/api/conversations/$CID" --json '{"title": "QA"}' --auth none --expect 401
  control-agent-server api GET "/api/conversations/$CID" --check title eq 'QA F04 title' --check tags.env eq prod --save F04.patch-errors/get
  ```
  每一次拒绝的更新都会保留存储的标题和标签。 未知id情况 `F04.patch-unknown-id`。
- **纯空白标题 (`F04.patch-whitespace-title`)。**在子对话中，因此回归不能泄漏到后面的项目符号中。

  需要：`F04.create-parent`
  ```sh
  control-agent-server api PATCH "/api/conversations/$CHILD" --json '{"title": "QA F04 child"}' --check success eq true
  control-agent-server api PATCH "/api/conversations/$CHILD" --json '{"title": "   "}' --expect 422 --save F04.patch-whitespace-title/patch
  control-agent-server api GET "/api/conversations/$CHILD" --check title eq 'QA F04 child'
  ```
  如果标题为空格，将被以422（类似于空标题）拒绝，并且存储的标题将保留。 没有这一点，服务将存储
  `title.strip()`、`""`，这也会停止自动字幕。
- **PATCH 未知 ID (`F04.patch-unknown-id`)。** OpenAPI文档为该路由声明了404； GET 上的相同 ID 为 404。
  ```sh
  control-agent-server api GET /openapi.json --check 'paths./api/conversations/{conversation_id}.patch.responses.404' exists --quiet
  control-agent-server api GET "/api/conversations/$NOPE" --expect 404
  control-agent-server api PATCH "/api/conversations/$NOPE" --json '{"title": "QA nobody"}' --expect 404 --save F04.patch-unknown-id/unknown
  ```
  404 `{"detail": "Not Found"}`声明中所述：处理器返回 404 错误
  `update_conversation` 找不到任何对话，因此对丢失的对话进行重命名看起来永远不会成功。
- **删除(`F04.delete`)。**一个正在运行的对话（挂起的存根），其中有一个子进程及其工作区中的一个文件，以及工作树对话。

  需要：`F04.create-worktree`
  ```sh
  mkdir -p "$W/qa-del" && echo keep > "$W/qa-del/qa-f04-keep.txt"
  DEL=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/qa-del\"}, \"agent\": $HANG_AGENT, \"autotitle\": false, \"initial_message\": {\"role\": \"user\", \"content\": [{\"type\": \"text\", \"text\": \"Wait.\"}]}}" \
    --expect 201 --field id)
  DELCHILD=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/qa-del\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false, \"parent_conversation_id\": \"$DEL\"}" --expect 201 --field id)
  control-agent-server conversation wait "$DEL" --until running --timeout 30
  N4=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server ws start "/sockets/events/$DEL" --name qa-f04-delete --duration 60
  control-agent-server api DELETE "/api/conversations/$DEL" --expect 200 --check success eq true --timeout 30 --save F04.delete/delete
  control-agent-server ws read qa-f04-delete --kinds PauseEvent --expect-min 1 --wait 15
  control-agent-server ws stop qa-f04-delete --kinds InterruptEvent --expect-min 1 --wait 15 --save F04.delete/live
  control-agent-server api GET "/api/conversations/$DEL" --expect 404 --save F04.delete/get-after
  control-agent-server api GET "/api/conversations/$DEL/agent_final_response" --expect 404
  control-agent-server api GET /api/conversations --query ids="$DEL" --check 0 eq null
  control-agent-server api GET /api/conversations/count --check . eq $((N4 - 1))
  control-agent-server ws listen "/sockets/events/$DEL" --expect-close 4004 --duration 5
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations/${DEL//-/}"
  test -f "$W/qa-del/qa-f04-keep.txt"
  control-agent-server api GET "/api/conversations/$DELCHILD" --check parent_conversation_id eq "$DEL"
  control-agent-server api DELETE /api/conversations/not-a-uuid --expect 422
  control-agent-server api DELETE "/api/conversations/$DELCHILD" --auth none --expect 401
  control-agent-server api DELETE "/api/conversations/$WT" --expect 200 --check success eq true
  test ! -e "$AGENT_SERVER_VERIFY_RUN/worktrees/$WT/qa-f04-repo"
  if git -C "$REPO" worktree list | grep -q "worktrees/$WT/"; then false; fi
  test -n "$(git -C "$REPO" branch --list "openhands/$WT")"
  ```
  正在进行的对话被暂停并中断，从所有读视图和磁盘中消失。 工作区文件及其子进程（已断开连接的）
  `parent_conversation_id`) 保留。 工作树会话的工作树被删除（目录和 `git worktree` 条目），但其分支保留。 重复删除和未知 ID 是`F04.delete-unknown-id`。
- **DELETE 未知 ID (`F04.delete-unknown-id`)。** OpenAPI文档为该路由声明了404； 已删除的`$DEL`和从未创建的`$NOPE`在GET上都是404。

  需要：`F04.delete`
  ```sh
  control-agent-server api GET /openapi.json --check 'paths./api/conversations/{conversation_id}.delete.responses.404' exists --quiet
  control-agent-server api GET "/api/conversations/$DEL" --expect 404
  control-agent-server api GET "/api/conversations/$NOPE" --expect 404
  control-agent-server api DELETE "/api/conversations/$NOPE" --expect 404 --save F04.delete-unknown-id/unknown
  control-agent-server api DELETE "/api/conversations/$DEL" --expect 404 --save F04.delete-unknown-id/repeat
  ```
  404 `{"detail": "Not Found"}` 对于两者，如声明的那样，处理器在 404 时抛出异常 `delete_conversation` 找不到对话，因此“已经离开”与畸形请求（422）不同。 `/pause` 和 `/interrupt` 用同样的方式回答（家庭）。
- **重新启动 (`F04.restart-persist`)。**同一运行的优雅重启。

  需要：`F04.create-settings`、`F04.create-idempotent`、`F04.create-parent`、`F04.run-real`、`F04.final-response`、`F04.delete`
  ```sh
  N5=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server restart
  control-agent-server api GET /api/conversations/count --check . eq "$N5"
  control-agent-server api GET "/api/conversations/$RID" --check execution_status eq finished --check title exists --save F04.restart-persist/real-run
  control-agent-server api GET "/api/conversations/$RID/agent_final_response" --check response matches '\S'
  control-agent-server api GET "/api/conversations/$FID/agent_final_response" --check response eq QA_F04_DONE --save F04.restart-persist/final-response
  control-agent-server api GET "/api/conversations/$CID" --check title eq 'QA F04 title' --check tags.env eq prod --check execution_status eq idle
  control-agent-server api GET "/api/conversations/$IID" --check sub_conversation_ids contains "$CHILD"
  control-agent-server api GET /api/conversations/search --query status=finished --check items contains "$FID" --check items contains "$RID" --check items contains "$QID"
  control-agent-server api GET "/api/conversations/$DEL" --expect 404
  control-agent-server ws listen "/sockets/events/$FID" --query resend_mode=all --until-kind ActionEvent --until tool_name=finish --duration 15 --save F04.restart-persist/replay
  ```
  一切读取都一样，删除的对话会返回404，完成的对话事件会回放到它的`finish`操作。
- **冷读不会加载对话 (`F04.read-no-hydrate`)。**内联智能体对话`$IID`，自重启以来仅GET接触过。

  需要：`F04.create-inline-agent`
  ```sh
  LEASE="$AGENT_SERVER_VERIFY_RUN/server/workspace/conversations/${IID//-/}/owner_lease.json"
  test ! -e "$LEASE"
  control-agent-server api GET "/api/conversations/$IID" --expect 200 --check id eq "$IID" --quiet
  control-agent-server api GET /api/conversations --query ids="$IID" --check 0.id eq "$IID" --quiet
  control-agent-server api GET /api/conversations/search --query status=idle --check items contains "$IID" --quiet
  control-agent-server api GET /api/conversations/count --query status=idle --check . ge 1
  test ! -e "$LEASE"
  control-agent-server api GET "/api/conversations/$IID/agent_final_response" --expect 200 --check response eq '' --save F04.read-no-hydrate/final-response
  test -f "$LEASE"
  ```
  优雅重启释放每条租约。 这四次目录读取操作留下
  `$IID` 卸载，`agent_final_response` 加载它，声称
  `owner_lease.json`.

- **开始一个孩子 (`F04.child-start`)。**使用共享隔离、git-工作树隔离和非 git 工作区上的默认工作树请求启动任务。 每个孩子都会进行一个小小的真实模型转弯，并开始新的历史。
  ```sh
  for CHILD_CASE in shared worktree fallback; do
    CHILD_PARENT_WS="$REPO"
    CHILD_ISOLATION="$CHILD_CASE"
    CHILD_ACTUAL="$CHILD_CASE"
    if [ "$CHILD_CASE" = fallback ]; then
      CHILD_PARENT_WS="$F/qa-f04-child-fallback"
      mkdir -p "$CHILD_PARENT_WS"
      CHILD_ISOLATION=worktree
      CHILD_ACTUAL=shared
    fi
    CPARENT=$(control-agent-server conversation start --tools none --no-autotitle \
      --workspace "$CHILD_PARENT_WS" --max-iterations 7 --tag qa=f04-child \
      --secret QA_F04_CHILD_TOKEN=qa-f04-child-value --print-id)
    if [ "$CHILD_CASE" = fallback ]; then
      rm -rf "$CHILD_PARENT_WS/.git"
    fi
    control-agent-server api POST "/api/conversations/$CPARENT/events" \
      --json '{"role":"user","content":[{"type":"text","text":"QA_F04_PARENT_ONLY"}],"run":false}' --expect 200
    CCHILD=$(control-agent-server api POST "/api/conversations/$CPARENT/children" \
      --json "{\"task\":\"QA_F04_CHILD_TASK: reply with ok.\",\"title\":\"QA F04 child $CHILD_CASE\",\"isolation\":\"$CHILD_ISOLATION\"}" \
      --expect 201 --check parent_conversation_id eq "$CPARENT" --check isolation eq "$CHILD_ACTUAL" \
      --save "F04.child-start/$CHILD_CASE-create" --field conversation_id)
    control-agent-server conversation wait "$CCHILD" --until finished --timeout 180
    CHILD_EXPECTED_WS="$CHILD_PARENT_WS"
    if [ "$CHILD_ACTUAL" = worktree ]; then
      CHILD_EXPECTED_WS="$AGENT_SERVER_VERIFY_RUN/worktrees/$CCHILD/qa-f04-repo"
      git -C "$REPO" worktree list | grep -Fq "$CHILD_EXPECTED_WS"
      test "$(git -C "$CHILD_EXPECTED_WS" branch --show-current)" = "openhands/$CCHILD"
    fi
    control-agent-server api GET "/api/conversations/$CCHILD" --expect 200 \
      --check parent_conversation_id eq "$CPARENT" --check title eq "QA F04 child $CHILD_CASE" \
      --check tags.qa eq f04-child --check max_iterations eq 7 \
      --check agent.llm.model eq deepseek/deepseek-flash --check agent.tools len-eq 0 \
      --check secret_registry.secret_sources.QA_F04_CHILD_TOKEN.kind eq StaticSecret \
      --check secret_registry.secret_sources.QA_F04_CHILD_TOKEN.value ne qa-f04-child-value \
      --check workspace.working_dir eq "$CHILD_EXPECTED_WS" --save "F04.child-start/$CHILD_CASE-child"
    control-agent-server api GET "/api/conversations/$CPARENT" --expect 200 \
      --check sub_conversation_ids contains "$CCHILD" --check execution_status eq idle \
      --save "F04.child-start/$CHILD_CASE-parent"
    control-agent-server api GET "/api/conversations/$CCHILD/events/count" --query source=user --check . eq 1
    control-agent-server api GET "/api/conversations/$CCHILD/events/count" --query body=QA_F04_PARENT_ONLY --check . eq 0
    control-agent-server api GET "/api/conversations/$CCHILD/events/search" --query source=user --query body=QA_F04_CHILD_TASK \
      --check items len-eq 1 --save "F04.child-start/$CHILD_CASE-task"
    control-agent-server api DELETE "/api/conversations/$CCHILD" --expect 200
    control-agent-server api DELETE "/api/conversations/$CPARENT" --expect 200
  done
  ```
  响应报告了实际隔离，包括 `shared` 用于非 Git 回退方案。 GET 证明了继承模型、限制、标签和隐藏开始时间机密，以及父链接。 只有孩子的任务出现在用户历史中。 父节点处于空闲状态。 b工作树有自己的分支。 非Git用例移除了在父进程启动时创建的空 `.git`，因此它独立于下一个bug来测试预期的非Git 回退方案。
- **新的工作区 (`F04.child-unborn`) 中的默认子项，已知错误。**创建父级会在没有提交的情况下初始化 git。 默认子级隔离必须处理正常的工作区状态，就像显式共享子级所做的那样。
  ```sh
  UNBORN_WS="$F/qa-f04-child-unborn"
  mkdir -p "$UNBORN_WS"
  UPARENT=$(control-agent-server conversation start --tools none --no-autotitle \
    --workspace "$UNBORN_WS" --print-id)
  test -d "$UNBORN_WS/.git"
  if git -C "$UNBORN_WS" rev-parse --verify HEAD >/dev/null 2>&1; then false; fi
  SHARED_CHILD=$(control-agent-server api POST "/api/conversations/$UPARENT/children" \
    --json '{"task":"Reply with ok.","isolation":"shared"}' --expect 201 \
    --check isolation eq shared --save F04.child-unborn/shared --field conversation_id)
  control-agent-server conversation wait "$SHARED_CHILD" --until finished --timeout 180
  control-agent-server api DELETE "/api/conversations/$SHARED_CHILD" --expect 200
  control-agent-server api POST "/api/conversations/$UPARENT/children" \
    --json '{"task":"Reply with ok."}' --expect 201 --save F04.child-unborn/default  # bug：状态 eq 500 && response.body.exception 包含“git 工作树 add”
  UCHILD=$(jq -r .response.body.conversation_id "$AGENT_SERVER_VERIFY_RUN/evidence/F04.child-unborn/default.json")
  control-agent-server conversation wait "$UCHILD" --until finished --timeout 180
  control-agent-server api GET "/api/conversations/$UPARENT" --check sub_conversation_ids contains "$UCHILD"
  control-agent-server api DELETE "/api/conversations/$UCHILD" --expect 200
  control-agent-server api DELETE "/api/conversations/$UPARENT" --expect 200
  ```
  两个启动都应该返回201，并完成。 通过普通对话流程创建的工作区不应要求在父进程开始子进程之前手动进行 git commit。 今天共享控制成功了，但默认启动返回了500：工作树计划接受未出生的仓库，`git worktree add ... HEAD` 因此失败了
  `HEAD` 未解析为提交 ([OpenHands/software-智能体-SDK#6186](https://github.com/OpenHands/software-agent-sdk/issues/6186))。
- **子启动错误 (`F04.child-errors`)。**无效的输入和未知的父级不会创建子级； 身份验证为必填项。
  ```sh
  EPARENT=$(control-agent-server conversation start --placeholder-agent --tools none \
    --no-autotitle --workspace "$W" --print-id)
  CHILD_BEFORE=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST "/api/conversations/$EPARENT/children" --json '{}' --expect 422 --save F04.child-errors/missing-task
  control-agent-server api POST "/api/conversations/$EPARENT/children" --json '{"task":""}' --expect 422
  control-agent-server api POST "/api/conversations/$EPARENT/children" --json '{"task":"QA child","isolation":"other"}' --expect 422
  control-agent-server api POST "/api/conversations/$NOPE/children" --json '{"task":"QA child"}' --expect 404 --save F04.child-errors/missing-parent
  control-agent-server api POST /api/conversations/not-a-uuid/children --json '{"task":"QA child"}' --expect 422
  control-agent-server api POST "/api/conversations/$EPARENT/children" --auth none --json '{"task":"QA child"}' --expect 401
  control-agent-server api GET /api/conversations/count --check . eq "$CHILD_BEFORE"
  control-agent-server api GET "/api/conversations/$EPARENT" --check sub_conversation_ids len-eq 0 --save F04.child-errors/unchanged-parent
  control-agent-server api DELETE "/api/conversations/$EPARENT" --expect 200
  ```
  验证是 422，未知父节点是 404，缺少身份验证是 401。 目录计数和父目录的子目录列表未改变。
- **满载子发射 (`F04.child-capacity`)。**一个挂起的提供程序调用占用唯一的运行槽，因此子级在创建之前会被拒绝。
  ```sh
  CRUN=$(control-agent-server launch --new --name f04-child-capacity --config-json '{"max_concurrent_runs":1}' --print-run)
  trap 'control-agent-server stop --run "$CRUN" >/dev/null' EXIT
  control-agent-server doctor --run "$CRUN"
  FULL_PARENT=$(control-agent-server api POST /api/conversations --run "$CRUN" \
    --json "{\"workspace\":{\"working_dir\":\"$REPO\"},\"agent\":$HANG_AGENT,\"autotitle\":false,\"initial_message\":{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"Wait.\"}]}}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$FULL_PARENT" --run "$CRUN" --until running --timeout 30
  control-agent-server api POST "/api/conversations/$FULL_PARENT/children" --run "$CRUN" \
    --json '{"task":"QA child","isolation":"worktree"}' --expect 429 --save F04.child-capacity/rejected
  control-agent-server api GET /api/conversations/count --run "$CRUN" --check . eq 1 --save F04.child-capacity/count
  control-agent-server api GET "/api/conversations/$FULL_PARENT" --run "$CRUN" --check sub_conversation_ids len-eq 0
  test ! -d "$CRUN/worktrees" || test -z "$(ls -A "$CRUN/worktrees")"
  control-agent-server stop --run "$CRUN"
  ```
  没有孩子出现在目录中或其父项中，也没有存在工作树的孩子。

<a id="gotchas"></a>

## 陷阱

- 创建 `initial_message` 时总是启动运行 (`initial_message.run` 被忽略，`F04.create-initial-message-run-false`），创建响应会在运行被调度后立即组成，因此仍然可能说 `idle`。 等待`conversation wait`。 要在不运行的情况下创建，请省略 `initial_message` 并将消息发布到
  `.../events` 与 `"run": false`； `conversation start --prompt ... --no-run` 正是这样做的。
- `GET`、`search` 和批处理读取自动保存的 `base_state.json` 快照（加上 `meta.json`），而不是实时内存。 在没有自动保存的情况下应用的更改（开始时间机密、`POST .../secrets`）将保持不可见，直到下一个状态保存：请参阅 `F04.create-secrets-get`。
- 机密永远不会回来：`agent.llm.api_key` 是 REST 响应中的 `null`（屏蔽值被重新解析为“no 机密”），而 `**********` 是套接字的 `full_state` 帧中的。 使用 `ne` 断言，切勿通过打印密钥来断言。
- `next_page_id` 是下一个项目 id 的 32 十六进制形式，而项目则带有虚线 id。 未知的 `page_id` 在第一页默默地重新启动而不是失败。
- `count` 计数目录记录 (`meta.json`)； 搜索会跳过其记录
  `base_state.json` 丢失，因此在损坏的存储上两者可能不同。
- `agent.agent_context.skills` 在每条路线上都会被修剪为 `[]`，除非
  `include_skills=true`; 存储的智能体保留它们。
- 未知的 ids：GET、PATCH、DELETE 和 `agent_final_response` 均为 404，如 OpenAPI 文档列表； 重复的DELETE也是404。
- `GET /api/conversations` 最多 99 个 id； 更多的是422（参见
  `F04.batch-get-limit`). 每个 id 重复 `--query ids=...` 一次。
- PATCH`tags`替换整个地图； PATCH `title` 单独留下标签。 设置标题会停止自动标题。 PATCH、DELETE和`agent_final_response`加载（水合）一个冷对话，该对话声称其`owner_lease.json`； GET，搜索、计数和批量获取则不然（`F04.read-no-hydrate`）。
- 自动标题是第一条用户消息后的单独后台 LLM 调用； 它不发出任何事件，因此在运行后轮询`title`（有界）。 它使用
  `title_llm_profile` 当该配置文件加载时，否则智能体的 LLM，否则截断的消息； 未知的配置文件只是一个日志警告。 当第一条用户消息到达时（而不是创建时），配置文件会按名称加载。
- 可观测性标头填充请求未设置的正文字段：正文
  `observability_span_name`、`observability_tags` 或
  `observability_parent_span_context` 默默地赢得了它的标头，并且标头元数据被合并到正文的键下。 None 其中出现在
  `ConversationInfo`; 阅读`meta.json`。
- 422 sanitizer 按 `detail[].input` 内的键名称进行编辑。 切勿在负面测试中发布真正的密钥。
- `parent_conversation_id` 需要与父级相同的 `working_dir`。 DELETE 不级联：孩子们保持悬空 `parent_conversation_id`，并且工作树及其 `openhands/<id>` 分支留在后面。
- 在 DELETE 期间，一个已经打开的事件套接字接收暂停帧，并且保持打开状态，没有进一步的事件（在 10 秒内没有收到关闭帧，观察到实时）。 只有新连接才会收到 4004。 注意 REST 端的 404，而不是等待关闭。
- 已保存的 LLM 个配置文件无法在 `agent_settings` 中命名； 从一开始
  `agent_profile_id`（`llm_profile_ref` 为其命名的智能体配置文件），如 `F04.create-agent-profile` 中所示。
- 默认工具 (`tools: null`) 需要 `tmux`（用于终端）和 Chromium（用于浏览器）； `"tools": []` (`--tools none`) 仅保留 `finish` 和 `think`。 提供存根和离线智能体 `"num_retries": 0`，或 LLM 错误重试几分钟。
- 相对的 `working_dir` 是根据服务器的工作目录（运行的 `server/`）而不是调用者的来解析的。
- 启动请求没有标题字段； `conversation start --title` 发送了 PATCH 创建之后。
- 利用陷阱：`ws listen --until FIELD=VALUE` 断言仅与
  `--until-kind`; 没有它，永远看不到帧的聆听仍然会过去。
  当没有匹配项时，`ws stop --contains` 会失败，但添加 `--wait` 以便不会错过仍在飞行中的帧。 `api --check items contains X` 与项目 JSON 中的任意位置的 X 匹配，包括另一个对话的链接字段。
- 创建在初始化时保留一个 `max_concurrent_runs` 槽，因此即使对于没有提示词的创建（在运行系列中驱动），完整的服务器也会回答 429。
