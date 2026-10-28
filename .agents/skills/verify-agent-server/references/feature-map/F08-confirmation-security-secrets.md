<a id="confirmation-policy-security-analyzer-and-conversation-secrets"></a>

# 确认策略、安全分析器和对话机密

实时对话的运行时安全性和凭据旋钮。 智能体的主机决定何时操作需要人类的批准（`confirmation_policy`：
`NeverConfirm`，`AlwaysConfirm`，`ConfirmRisky`，风险阈值），该分析器对每个动作的风险进行评级(`security_analyzer`，或None)，并用接受或拒绝来回答停驻动作(`events/respond_to_confirmation`)。 它还在运行时 (`secrets`) 处理名为机密的会话：提及机密名称的终端命令将其获取为环境变量，其值被屏蔽为
观测结果中的 `<secret-hidden>` 以及模型所看到的内容，并且在 REST 中加密。 开始时间 `confirmation_policy`、`security_analyzer` 和
`secrets` `POST /api/conversations` 的字段属于生命周期系列；
`POST .../run`（PythonSDK如何接受）属于run家族。

资料来源：`openhands-agent-server/openhands/agent_server/conversation_router.py`、`openhands-agent-server/openhands/agent_server/event_router.py`、`openhands-agent-server/openhands/agent_server/event_service.py`、`openhands-agent-server/openhands/agent_server/models.py`、`openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`、`openhands-sdk/openhands/sdk/conversation/secret_registry.py`、`openhands-sdk/openhands/sdk/conversation/state.py`、`openhands-sdk/openhands/sdk/security/`、`openhands-sdk/openhands/sdk/secret/secrets.py`、`openhands-agent-server/openhands/agent_server/local_secret_resolver.py`、`openhands-sdk/openhands/sdk/agent/agent.py`、`openhands-tools/openhands/tools/terminal/impl.py`

需求：`llm`、`tmux`

路线：`POST /api/conversations/{conversation_id}/events/respond_to_confirmation`，
`POST /api/conversations/{conversation_id}/secrets`,
`POST /api/conversations/{conversation_id}/confirmation_policy`,
`POST /api/conversations/{conversation_id}/security_analyzer`

<a id="sub-features"></a>

## 子功能

- `F08.policy-set`：`POST .../confirmation_policy`在`AlwaysConfirm`、`ConfirmRisky`（与`threshold`和`confirm_unknown`）和`NeverConfirm`之间切换； 事件套接字上的 GET、`base_state.json` 和 `confirmation_policy` 状态更新立即反映每个更改。
- `F08.policy-errors`：未知的策略种类，`UNKNOWN`的`threshold`或未知级别，以及缺失或空的`policy`为422； 未知对话是 404； 无键为 401； 存储的策略不变。
- `F08.always-confirm-wait`：在 `AlwaysConfirm` 的运行切换后，智能体的下一个终端动作会将对话推入 `waiting_for_confirmation`（推送到套接字中）并记录 `ActionEvent`，没有观测结果，也不执行命令。
- `F08.confirm-accept`：`accept: true` 运行待处理的命令（观测结果和磁盘上的文件），并继续运行到 `finished`。
- `F08.confirm-reject`：`accept: false`以给定原因（REST和套接字）记录一`UserRejectObservation`，并返回到`idle`，而不运行该命令； 第二次拒绝是无操作，稍后的接受仅恢复智能体。
- `F08.confirm-errors`：缺失或非布尔值 `accept` 以及格式错误的 id 为 422； 未知对话是 404； 没有键是401。
- `F08.confirm-capacity`：服务器的运行能力已满，accept 为 429 并将操作保留为待处理且未运行； 拒绝仍然有效； 在正在运行的对话上接受是 200 无操作。
- `F08.confirm-real`: `AlwaysConfirm` 下的 DeepSeek 闪烁在其终端命令之前停止，并在其操作被接受后完成任务。
- `F08.analyzer-set-clear`：`POST .../security_analyzer`设置`PatternSecurityAnalyzer`或`LLMSecurityAnalyzer`并用`null`清除； GET、`base_state.json`和套接字反映了每个变化。
- `F08.analyzer-errors`：缺失的`security_analyzer`字段和未知种类为422； 未知对话是 404； 无键为 401； 存储的分析器未更改。
- `F08.confirm-risky`：在`ConfirmRisky`和`PatternSecurityAnalyzer`下，低风险命令未经请求运行，`rm -rf`等待确认； 一旦分析器被清除，未评级的命令也会等待。
- `F08.secrets-update`：`POST .../secrets`接受纯字符串，`{"value": ...}`和`StaticSecret`对象（200）； 保存状态后，GET 会列出带有掩码值的名称，`base_state.json` 会对它们进行加密，而不是明文。
- `F08.secrets-visible`：运行时发布的机密立即由 GET 列出，无需等待另一个状态更改。
- `F08.secrets-errors`：缺失或非对象`secrets`、未知的机密种类和没有`url`的`LookupSecret`是422； 未知对话是 404； 无键为 401； 没有存储任何内容。
- `F08.secrets-bad-value`：数字、`null` 或布尔值作为机密值被拒绝为 422，而不是 500。
- `F08.secrets-terminal`：一个名称一个运行时的终端命令机密接收其值，而观测结果和接下来的请求到模型显示 `<secret-hidden>` 和文本存储在任何地方。
- `F08.secrets-override`：运行时间机密替换下一个命令的同名开始时间机密。
- `F08.secrets-lookup`：仅当命令命名时，运行时 `LookupSecret` 才会从其 URL 及其标头中获取； 该命令获取获取的文本，观测结果和模型参见 `<secret-hidden>`，GET 隐藏 `base_state.json` 保持加密的 `Authorization` 标头。
- `F08.secrets-lookup-self`: 一个运行时 `LookupSecret` 的 URL 是服务器的 `/api/settings/secrets/<name>` (无主机，从 `OH_INTERNAL_SERVER_URL` 绝对化，或在运行时的地址上绝对化) 在进程中从机密存储中回答，没有 HTTP 请求和没有会话密钥。 商店缺少的名称会下降到 HTTP（没有密钥的 401）并且该命令没有任何值。
- `F08.secrets-profile-scope`：对于从智能体配置文件与 `secret_refs` 启动的对话，列表之外的名称将被静默删除 (200)。
- `F08.secrets-no-cipher`：在没有密码（没有 `OH_SECRET_KEY`，没有会话密钥）的服务器上，运行时机密在会话存在时到达命令，已持久化仅作为脱敏占位符（服务器在启动时发出警告），并且在重新启动后为空，尽管 GET 仍然列出名称。
- `F08.secrets-restart`：达到`base_state.json`的运行时机密在服务器重新启动后仍会注入到命令中。
- `F08.secrets-unsaved-restart`：运行时机密在重新启动后仍然存在，即使在发布后对话中没有其他任何变化。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST：`POST /api/conversations/{conversation_id}/confirmation_policy`（主体`SetConfirmationPolicyRequest`：`{"policy": {"kind": "AlwaysConfirm"}}`，
  `{"kind": "NeverConfirm"}` 或 `{"kind": "ConfirmRisky", "threshold": "LOW|MEDIUM|HIGH", "confirm_unknown": true}`),
  `POST .../security_analyzer`（`{"security_analyzer": {"kind": "PatternSecurityAnalyzer"}}`或`null`； 其他种类：`LLMSecurityAnalyzer`、`PolicyRailSecurityAnalyzer`、
  `EnsembleSecurityAnalyzer`, `ToolShieldLLMSecurityAnalyzer`, `GraySwanAnalyzer`),
  `POST .../secrets` (`{"secrets": {"NAME": "value" | {"value": "..."} | {"kind": "StaticSecret", "value": "..."} | {"kind": "LookupSecret", "url": "...", "headers": {}}}}`)，其中 `LookupSecret` `url` 可能是无主机的（`/api/settings/secrets/NAME`，连接到 `OH_INTERNAL_SERVER_URL`，服务器自己的地址），以及 `POST .../events/respond_to_confirmation`（`{"accept": true}` 或
  `{"accept": false, "reason": "..."}`). 所有四人回答 `{"success": true}`。
- 第二次浏览：`GET /api/conversations/{id}` (`execution_status`,
  `confirmation_policy`、`security_analyzer`、`secret_registry.secret_sources`（带屏蔽值）、事件历史记录（`ActionEvent`、`ObservationEvent`、
  `UserRejectObservation`、`ConversationStateUpdateEvent`键
  `execution_status`、`confirmation_policy`、`security_analyzer`），对话的 `base_state.json` 位于磁盘上。
- WebSocket（由事件系列拥有）：`/sockets/events/{conversation_id}` 推送上面的状态更新和 `UserRejectObservation` 直播。
- `POST /api/conversations` 的开始时间字段 (`confirmation_policy`,
  `security_analyzer`, `secrets`) 存储在 `meta.json` 中并在每次重新加载时重新应用； 这里的运行时路由仅更改实时状态。
- SDK (`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`):
  `RemoteConversation.set_confirmation_policy()`, `set_security_analyzer()`,
  `update_secrets()`（序列化 `SecretSource` 对象，调用可调用对象），以及
  `reject_pending_actions(reason)` (`accept: false`). SDK通过调用`run()`（`POST .../run`）接受； `respond_to_confirmation` 与
  `accept: true` 在服务器端做同样的事情。
- TypeScript客户端：`ConversationClient.setConfirmationPolicy`，
  `setSecurityAnalyzer`、`updateSecrets`、`respondToConfirmation` (`clients/typescript/src/client/conversation-client.ts`) 和
  `RemoteConversation.setConfirmationPolicy`, `setSecurityAnalyzer`,
  `updateSecrets`（始终发送 `StaticSecret` 个对象）和
  `sendConfirmationResponse(accept, reason)` (`clients/typescript/src/conversation/remote-conversation.ts`).
- Agent Canvas（仅限上下文）：待处理操作上的确认模式切换和批准/拒绝按钮调用这些路由。
- 以下的食谱使用 REST 到 `api`，socket 从 `ws start`/`ws 到 `, scripted terminal actions from `测试夹具 llm-stub` (one stub per scenario, because a stub's step counter never resets), `测试夹具 HTTP-sink` as the URL a `LookupSecret` points at, the settings secrets store (`PUT /api/settings/secrets`) 作为循环引用的目标
  `LookupSecret`，两个短暂的第二个服务器（其中一个带有
  `max_concurrent_runs` 1，没有密码），DeepSeek flash 用于真实模型确认路径。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行此检查，`doctor` ok，`$DEEPSEEK_API_KEY` set； 下面的块保存 DeepSeek 配置文件。
- `tmux` 已安装：这里的每个脚本智能体都有 `terminal` 工具，没有其他东西（加上内置的 `finish` 和 `think`）。
- 以下块会创建： 工作区根 `$W` 每个场景都包含一个文件夹（） `qa-f08-victim` 文件夹是  `rm -rf` 必须不能删除，未知的 id `$NOPE`, 一个离线 inline 智能体  `$OFFLINE_AGENT` （从不运行），以及一个脚本 `llm-stub`  智能体按场景。 每个存根按顺序应答其对话的模型调用并重复其最后一步：
  `$ACCEPT_AGENT`（写`qa-f08-accepted.txt`，完成），`$REJECT_AGENT`（`rm -rf qa-f08-victim`，完成），`$RISKY_AGENT`（低风险`echo`，
  `rm -rf qa-f08-victim`、`echo`、完成）、`$SECRET_AGENT`（写入
  `$QA_F08_TOKEN` 到文件并回显它，完成，两次），`$ROTATE_AGENT`（将 `$QA_F08_ROT` 写入文件，完成），`$LOOKUP_AGENT`（写入
  `$QA_F08_LOOKUP` 到文件并回显它，完成）和 `$SELF_AGENT` （写入
  `$QA_F08_HOSTLESS`、`$QA_F08_ABSOLUTE` 和 `$QA_F08_ABSENT` 到三个文件并回显第一个，完成）。 无密码子弹在自己的服务器上创建自己的存根。 最后，它创建了
  `$KID`，离线闲置对话智能体，旋钮、错误和机密形式项目符号共享。
- 每个 `known bug` 项目符号仅使用这些变量并排列 REST 本身（包括它自己的 `restart`），因此
  `map run --file F08 --only <ID> --fresh` 单独复制它，作为修复验证的需要。

```sh
control-agent-server llm preset deepseek
W="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f08"
mkdir -p "$W/knobs" "$W/accept" "$W/reject/qa-f08-victim" "$W/risky/qa-f08-victim" "$W/secret" "$W/rotate" \
  "$W/lookup" "$W/self" "$W/scoped" "$W/nocipher" "$W/real"
NOPE=$(python3 -c 'import uuid; print(uuid.uuid4())')
OFFLINE_AGENT='{"llm": {"model": "openai/qa-offline", "api_key": "qa-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": []}'
MSG='{"role": "user", "content": [{"type": "text", "text": "Run the command."}]}'
stub_agent() {
  printf '{"llm": {"model": "openai/qa-stub", "api_key": "qa-stub-key", "base_url": "%s/v1", "num_retries": 0}, "tools": [{"name": "terminal"}]}' \
    "$(control-agent-server fixture llm-stub --name "$@" --print-path)"
}
FINISH='tool:finish:{"message":"QA_F08_DONE"}'
ACCEPT_AGENT=$(stub_agent qa-f08-accept --step 'tool:terminal:{"command":"echo qa-accepted > qa-f08-accepted.txt"}' --step "$FINISH")
REJECT_AGENT=$(stub_agent qa-f08-reject --step 'tool:terminal:{"command":"rm -rf qa-f08-victim"}' --step "$FINISH")
RISKY_AGENT=$(stub_agent qa-f08-risky --step 'tool:terminal:{"command":"echo qa-low > qa-f08-low.txt"}' \
  --step 'tool:terminal:{"command":"rm -rf qa-f08-victim"}' --step 'tool:terminal:{"command":"echo qa-unrated > qa-f08-unrated.txt"}' --step "$FINISH")
SECRET_STEP='tool:terminal:{"command":"printf %s \"$QA_F08_TOKEN\" > qa-f08-token.txt; echo \"token=$QA_F08_TOKEN\""}'
SECRET_AGENT=$(stub_agent qa-f08-secret --step "$SECRET_STEP" --step "$FINISH" --step "$SECRET_STEP" --step "$FINISH")
ROTATE_STEP='tool:terminal:{"command":"printf %s \"$QA_F08_ROT\" > qa-f08-rot.txt"}'
ROTATE_AGENT=$(stub_agent qa-f08-rotate --step "$ROTATE_STEP" --step "$FINISH")
LOOKUP_STEP='tool:terminal:{"command":"printf %s \"$QA_F08_LOOKUP\" > qa-f08-lookup.txt; echo \"lookup=$QA_F08_LOOKUP\""}'
LOOKUP_AGENT=$(stub_agent qa-f08-lookup --step "$LOOKUP_STEP" --step "$FINISH")
SELF_STEP='tool:terminal:{"command":"printf %s \"$QA_F08_HOSTLESS\" > qa-f08-hostless.txt; printf %s \"$QA_F08_ABSOLUTE\" > qa-f08-absolute.txt; printf %s \"$QA_F08_ABSENT\" > qa-f08-absent.txt; echo \"self=$QA_F08_HOSTLESS\""}'
SELF_AGENT=$(stub_agent qa-f08-self --step "$SELF_STEP" --step "$FINISH")
REJECT_KIND=openhands.sdk.event.llm_convertible.observation.UserRejectObservation
OBSERVATION_KIND=openhands.sdk.event.llm_convertible.observation.ObservationEvent
KID=$(control-agent-server api POST /api/conversations \
  --json "{\"workspace\": {\"working_dir\": \"$W/knobs\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" --expect 201 --field id)
```

- **设置确认策略(`F08.policy-set`)。**空闲`$KID`从`NeverConfirm`开始并且没有分析器； 套接字捕获记录每个更改。
  ```sh
  control-agent-server api GET "/api/conversations/$KID" --check confirmation_policy.kind eq NeverConfirm --check security_analyzer eq null
  control-agent-server ws start "/sockets/events/$KID" --name qa-f08-policy --duration 120
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "AlwaysConfirm"}}' \
    --expect 200 --check success eq true --save F08.policy-set/always
  control-agent-server api GET "/api/conversations/$KID" --check confirmation_policy.kind eq AlwaysConfirm
  control-agent-server state cat "server/workspace/conversations/${KID//-/}/base_state.json" --max-chars 200 \
    --check confirmation_policy.kind eq AlwaysConfirm
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" \
    --json '{"policy": {"kind": "ConfirmRisky", "threshold": "MEDIUM", "confirm_unknown": false}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check confirmation_policy.kind eq ConfirmRisky \
    --check confirmation_policy.threshold eq MEDIUM --check confirmation_policy.confirm_unknown eq false --save F08.policy-set/risky
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "NeverConfirm"}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check confirmation_policy.kind eq NeverConfirm
  control-agent-server ws read qa-f08-policy --kinds ConversationStateUpdateEvent --contains '"threshold": "MEDIUM"' --wait 10
  control-agent-server ws stop qa-f08-policy --kinds ConversationStateUpdateEvent --contains '"key": "confirmation_policy"' \
    --expect-min 3 --save F08.policy-set/socket
  control-agent-server conversation events "$KID" --key confirmation_policy --contains ConfirmRisky
  ```
  每个POST都是200`{"success": true}`，下一个GET和`base_state.json`显示新的政策`ConfirmRisky`保持`threshold`和`MEDIUM`
  `confirm_unknown` `false`），并且套接字每次更改推送一次 `confirmation_policy` 状态更新（三），`ConfirmRisky` 一个及其阈值； 事件历史也有它们。
- **政策错误(`F08.policy-errors`)。**身体不好，身份不明，没有钥匙。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "SometimesConfirm"}}' \
    --expect 422 --check detail.0.msg contains 'Unknown kind' --save F08.policy-errors/unknown-kind
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "ConfirmRisky", "threshold": "UNKNOWN"}}' \
    --expect 422 --check detail.0.msg contains 'cannot be UNKNOWN'
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "ConfirmRisky", "threshold": "EXTREME"}}' \
    --expect 422 --check detail.0.loc contains threshold
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{}' --expect 422 --check detail.0.loc contains policy
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {}}' --expect 422
  control-agent-server api POST "/api/conversations/$NOPE/confirmation_policy" --json '{"policy": {"kind": "AlwaysConfirm"}}' --expect 404
  control-agent-server api POST "/api/conversations/$KID/confirmation_policy" --json '{"policy": {"kind": "AlwaysConfirm"}}' --auth none --expect 401
  control-agent-server api GET "/api/conversations/$KID" --check confirmation_policy.kind eq NeverConfirm
  ```
  每种状态都匹配，策略仍然 `NeverConfirm`。
- **等待确认(`F08.always-confirm-wait`)。**运行时切换到
  `AlwaysConfirm`，然后一条消息； 套接字是在消息之前捕获的。
  ```sh
  AID=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/accept\"}, \"agent\": $ACCEPT_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$AID/confirmation_policy" --json '{"policy": {"kind": "AlwaysConfirm"}}' --expect 200
  control-agent-server ws start "/sockets/events/$AID" --name qa-f08-wait --duration 120
  control-agent-server conversation send "$AID" --text 'Run the command.' --wait --until waiting_for_confirmation --timeout 120
  control-agent-server api GET "/api/conversations/$AID" --check execution_status eq waiting_for_confirmation \
    --check confirmation_policy.kind eq AlwaysConfirm --save F08.always-confirm-wait/waiting
  control-agent-server conversation events "$AID" --kinds ActionEvent --contains qa-f08-accepted.txt
  control-agent-server api GET "/api/conversations/$AID/events/count" --query kind="$OBSERVATION_KIND" --check . eq 0
  test ! -e "$W/accept/qa-f08-accepted.txt"
  control-agent-server ws stop qa-f08-wait --kinds ConversationStateUpdateEvent --contains waiting_for_confirmation --save F08.always-confirm-wait/socket
  ```
  对话等待终端 `ActionEvent` 记录，没有观测结果和文件。 插座推`execution_status`
  `waiting_for_confirmation`.
- **接受(`F08.confirm-accept`)。**批准待处理的命令。

  需要：`F08.always-confirm-wait`
  ```sh
  control-agent-server api POST "/api/conversations/$AID/events/respond_to_confirmation" --json '{"accept": true}' \
    --expect 200 --check success eq true --save F08.confirm-accept/accept
  control-agent-server conversation wait "$AID" --until finished --timeout 120
  test "$(cat "$W/accept/qa-f08-accepted.txt")" = qa-accepted
  control-agent-server conversation events "$AID" --kinds ObservationEvent --contains qa-f08-accepted.txt
  control-agent-server api GET "/api/conversations/$AID/agent_final_response" --check response eq QA_F08_DONE --save F08.confirm-accept/final
  ```
  命令运行（文件包含`qa-accepted`，终端记录观测结果），智能体完成并以`finish`消息结束。
- **拒绝 (`F08.confirm-reject`)。**创建的对话
  `AlwaysConfirm`在开始正文中提出`rm -rf qa-f08-victim`。
  ```sh
  RJ=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/reject\"}, \"agent\": $REJECT_AGENT, \"autotitle\": false, \"confirmation_policy\": {\"kind\": \"AlwaysConfirm\"}, \"initial_message\": $MSG}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$RJ" --until waiting_for_confirmation --timeout 120
  control-agent-server ws start "/sockets/events/$RJ" --name qa-f08-reject --duration 120
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" \
    --json '{"accept": false, "reason": "QA_F08 rejected"}' --expect 200 --save F08.confirm-reject/reject
  control-agent-server conversation wait "$RJ" --until idle --timeout 60
  test -d "$W/reject/qa-f08-victim"
  control-agent-server api GET "/api/conversations/$RJ/events/search" --query kind="$REJECT_KIND" \
    --check items len-eq 1 --check items.0.rejection_reason eq 'QA_F08 rejected' --check items.0.tool_name eq terminal \
    --save F08.confirm-reject/observation
  control-agent-server ws stop qa-f08-reject --kinds UserRejectObservation --contains 'QA_F08 rejected' --save F08.confirm-reject/socket
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" --json '{"accept": false, "reason": "again"}' --expect 200
  control-agent-server api GET "/api/conversations/$RJ/events/count" --query kind="$REJECT_KIND" --check . eq 1
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" --json '{"accept": true}' --expect 200
  control-agent-server conversation wait "$RJ" --until finished --timeout 120
  control-agent-server api GET "/api/conversations/$RJ/agent_final_response" --check response eq QA_F08_DONE
  test -d "$W/reject/qa-f08-victim"
  ```
  拒绝码是200，对话回到`idle`，1
  `UserRejectObservation` 包含原因（也推送到套接字上）并且受害者文件夹仍然存在。 第二次拒绝没有发现任何待处理的内容，也没有添加任何内容。 后面的接受也没有任何待处理的内容，因此它只运行智能体，从而完成； 被拒绝的命令永远不会运行。
- **确认错误(`F08.confirm-errors`)。**坏的机构、ID 和身份验证。

  需要：`F08.confirm-reject`
  ```sh
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" --json '{}' \
    --expect 422 --check detail.0.loc contains accept --save F08.confirm-errors/missing-accept
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" --json '{"accept": "maybe"}' --expect 422
  control-agent-server api POST /api/conversations/not-a-uuid/events/respond_to_confirmation --json '{"accept": false}' --expect 422
  control-agent-server api POST "/api/conversations/$NOPE/events/respond_to_confirmation" --json '{"accept": false}' \
    --expect 404 --check detail contains 'Conversation not found'
  control-agent-server api POST "/api/conversations/$RJ/events/respond_to_confirmation" --json '{"accept": false}' --auth none --expect 401
  ```
  所有状态都匹配。
- **接受满负荷运行的请求`F08.confirm-capacity`).** 第二个服务器仅限一个并发运行：对话 `X` 等待确认（停放的对话没有运行槽），挂起的会话占用唯一槽位，然后 `X` 已被接受。
  ```sh
  B=$(control-agent-server launch --new --name f08-cap --print-run --config-json '{"max_concurrent_runs": 1}')
  trap 'control-agent-server stop --run "$B" >/dev/null' EXIT
  CAP_STUB=$(control-agent-server fixture llm-stub --run "$B" --name qa-f08-cap \
    --step 'tool:terminal:{"command":"echo qa-cap > qa-f08-cap.txt"}' --step "$FINISH" --print-path)
  HANG_STUB=$(control-agent-server fixture llm-stub --run "$B" --name qa-f08-hang --step hang:300 --print-path)
  mkdir -p "$W/cap" "$W/hang"
  X=$(control-agent-server api POST /api/conversations --run "$B" \
    --json "{\"workspace\": {\"working_dir\": \"$W/cap\"}, \"agent\": {\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$CAP_STUB/v1\", \"num_retries\": 0}, \"tools\": [{\"name\": \"terminal\"}]}, \"autotitle\": false, \"confirmation_policy\": {\"kind\": \"AlwaysConfirm\"}, \"initial_message\": $MSG}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$X" --run "$B" --until waiting_for_confirmation --timeout 120
  Y=$(control-agent-server api POST /api/conversations --run "$B" \
    --json "{\"workspace\": {\"working_dir\": \"$W/hang\"}, \"agent\": {\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$HANG_STUB/v1\", \"num_retries\": 0}, \"tools\": []}, \"autotitle\": false, \"initial_message\": $MSG}" \
    --expect 201 --field id)
  control-agent-server conversation wait "$Y" --run "$B" --until running --timeout 60
  control-agent-server api POST "/api/conversations/$X/events/respond_to_confirmation" --run "$B" --json '{"accept": true}' \
    --expect 429 --check detail contains 'run limit' --save F08.confirm-capacity/accept-429
  control-agent-server api GET "/api/conversations/$X" --run "$B" --check execution_status eq waiting_for_confirmation
  test ! -e "$W/cap/qa-f08-cap.txt"
  control-agent-server api POST "/api/conversations/$X/events/respond_to_confirmation" --run "$B" --json '{"accept": false}' --expect 200
  control-agent-server conversation wait "$X" --run "$B" --until idle --timeout 60
  control-agent-server api GET "/api/conversations/$X/events/search" --run "$B" --query kind="$REJECT_KIND" \
    --check items len-eq 1 --check items.0.rejection_reason eq 'User rejected the action.'
  control-agent-server api POST "/api/conversations/$Y/events/respond_to_confirmation" --run "$B" --json '{"accept": true}' \
    --expect 200 --save F08.confirm-capacity/accept-running
  control-agent-server api GET "/api/conversations/$Y" --run "$B" --check execution_status eq running
  test ! -e "$W/cap/qa-f08-cap.txt"
  ```
  接受头是 429 `Conversation run limit reached` 和 `X` 仍在等待执行其命令。 拒绝不需要槽位且成功（一）
  `UserRejectObservation` 与默认原因 `User rejected the action.`，因为正文已发送 None）； 对正在运行的对话的接受是 200 无操作。 该陷阱会停止第二个服务器。
- **真实模型首先提出问题 (`F08.confirm-real`)。** DeepSeek 使用终端工具刷新和`AlwaysConfirm`； 它建议的每一个行动都会被接受，直到它完成。
  ```sh
  REAL=$(control-agent-server conversation start --tools terminal --no-autotitle --confirmation-policy always --workspace "$W/real" \
    --prompt 'Use the terminal tool to run exactly this one command, then finish: echo qa-f08-real > qa-f08-real.txt' \
    --wait --until waiting_for_confirmation --timeout 300 --save F08.confirm-real/start --print-id)
  test ! -e "$W/real/qa-f08-real.txt"
  control-agent-server conversation events "$REAL" --kinds ActionEvent --contains qa-f08-real
  for _ in 1 2 3 4 5 6 7 8; do
    STATUS=$(control-agent-server api GET "/api/conversations/$REAL" --field execution_status)
    if [ "$STATUS" = finished ]; then break; fi
    if [ "$STATUS" = waiting_for_confirmation ]; then
      control-agent-server api POST "/api/conversations/$REAL/events/respond_to_confirmation" --json '{"accept": true}' --expect 200 --field success
    fi
    control-agent-server conversation wait "$REAL" --until waiting_for_confirmation,finished,error --timeout 300
  done
  control-agent-server api GET "/api/conversations/$REAL" --check execution_status eq finished --save F08.confirm-real/finished
  test "$(cat "$W/real/qa-f08-real.txt")" = qa-f08-real
  ```
  模型的第一个终端动作在等待，尚未运行。 在接收文件后，`qa-f08-real` 保留，`finished` 会进行对话。 循环容忍一个模型，该模型添加了一个检查命令（每个命令都被接受），以及一个状态读取命令，该命令在接受后仍然 `waiting_for_confirmation` 正确。
- **设置和清除分析仪 (`F08.analyzer-set-clear`)。**从第一颗子弹开始的闲聊。
  ```sh
  control-agent-server ws start "/sockets/events/$KID" --name qa-f08-analyzer --duration 120
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{"security_analyzer": {"kind": "PatternSecurityAnalyzer"}}' \
    --expect 200 --check success eq true --save F08.analyzer-set-clear/pattern
  control-agent-server api GET "/api/conversations/$KID" --check security_analyzer.kind eq PatternSecurityAnalyzer \
    --check security_analyzer.high_patterns len-ge 1
  control-agent-server state cat "server/workspace/conversations/${KID//-/}/base_state.json" --max-chars 200 \
    --check security_analyzer.kind eq PatternSecurityAnalyzer
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{"security_analyzer": {"kind": "LLMSecurityAnalyzer"}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check security_analyzer.kind eq LLMSecurityAnalyzer
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{"security_analyzer": null}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check security_analyzer eq null --raw-out "$W/qa-f08-cleared.json" \
    --save F08.analyzer-set-clear/cleared
  jq -e 'has("security_analyzer") and .security_analyzer == null' "$W/qa-f08-cleared.json"
  control-agent-server ws read qa-f08-analyzer --kinds ConversationStateUpdateEvent --contains LLMSecurityAnalyzer --wait 10
  control-agent-server ws stop qa-f08-analyzer --kinds ConversationStateUpdateEvent --contains '"key": "security_analyzer"' \
    --expect-min 3 --save F08.analyzer-set-clear/socket
  ```
  GET 和 `base_state.json` 跟随每次更改 (`PatternSecurityAnalyzer` 返回默认的模式列表，然后明确地留下键，值为  `null` (`jq` 原始体告诉除了丢失的键之外，还有其他东西 `--check ... eq null` 不能），并且套接字推送了一个 `security_analyzer` 根据变更进行状态更新（第三项，最后一个）
  `value` `null`).
- **分析仪错误 (`F08.analyzer-errors`)。**即使要清除它也需要该字段。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{}' \
    --expect 422 --check detail.0.loc contains security_analyzer --save F08.analyzer-errors/missing
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{"security_analyzer": {"kind": "NopeAnalyzer"}}' \
    --expect 422 --check detail.0.msg contains 'Unknown kind'
  control-agent-server api POST "/api/conversations/$NOPE/security_analyzer" --json '{"security_analyzer": null}' --expect 404
  control-agent-server api POST "/api/conversations/$KID/security_analyzer" --json '{"security_analyzer": {"kind": "PatternSecurityAnalyzer"}}' \
    --auth none --expect 401
  control-agent-server api GET "/api/conversations/$KID" --check security_analyzer eq null
  ```
  所有状态都匹配，分析器仍然 `null`，尽管拒绝的未认证请求要求 `PatternSecurityAnalyzer`。
- **基于风险的确认(`F08.confirm-risky`)。** `ConfirmRisky`（默认阈值 `HIGH`、`confirm_unknown` True），`PatternSecurityAnalyzer` 在运行时设置； 存根建议`echo`，然后是`rm -rf qa-f08-victim`，然后是另一个`echo`。
  ```sh
  RK=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/risky\"}, \"agent\": $RISKY_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$RK/confirmation_policy" --json '{"policy": {"kind": "ConfirmRisky"}}' --expect 200
  control-agent-server api GET "/api/conversations/$RK" --check confirmation_policy.threshold eq HIGH --check confirmation_policy.confirm_unknown eq true
  control-agent-server api POST "/api/conversations/$RK/security_analyzer" --json '{"security_analyzer": {"kind": "PatternSecurityAnalyzer"}}' --expect 200
  control-agent-server conversation send "$RK" --text 'Run the commands.' --wait --until waiting_for_confirmation --timeout 120
  test "$(cat "$W/risky/qa-f08-low.txt")" = qa-low
  test -d "$W/risky/qa-f08-victim"
  control-agent-server conversation events "$RK" --kinds ActionEvent --show 1 --contains 'rm -rf' --save F08.confirm-risky/held
  control-agent-server api GET "/api/conversations/$RK/events/count" --query kind="$OBSERVATION_KIND" --check . eq 1
  control-agent-server api POST "/api/conversations/$RK/events/respond_to_confirmation" --json '{"accept": false, "reason": "QA_F08 high risk"}' --expect 200
  control-agent-server api POST "/api/conversations/$RK/security_analyzer" --json '{"security_analyzer": null}' --expect 200
  control-agent-server api POST "/api/conversations/$RK/events/respond_to_confirmation" --json '{"accept": true}' --expect 200
  control-agent-server conversation wait "$RK" --until waiting_for_confirmation --timeout 120
  test ! -e "$W/risky/qa-f08-unrated.txt"
  control-agent-server api POST "/api/conversations/$RK/events/respond_to_confirmation" --json '{"accept": true}' --expect 200
  control-agent-server conversation wait "$RK" --until finished --timeout 120
  test "$(cat "$W/risky/qa-f08-unrated.txt")" = qa-unrated
  test -d "$W/risky/qa-f08-victim"
  ```
  低风险的`echo`运行了，`rm -rf`（由模式分析器评级为`HIGH`）等待并被拒绝了，因此受害文件幸存下来。 在分析器清除后，下一个 `echo` 未评级（`UNKNOWN`）
  `confirm_unknown` 让它等待； 接受它即可让智能体完成。
- **更新机密（`F08.secrets-update`）。**闲谈中的三种接受的价值形式`$KID`。 标签 PATCH 强制首先保存状态（请参阅下一个项目符号了解原因）。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/secrets" \
    --json '{"secrets": {"QA_F08_PLAIN": "qa-f08-plain-value", "QA_F08_DICT": {"value": "qa-f08-dict-value"}, "QA_F08_STATIC": {"kind": "StaticSecret", "value": "qa-f08-static-value", "description": "qa static"}}}' \
    --expect 200 --check success eq true --save F08.secrets-update/post
  control-agent-server api PATCH "/api/conversations/$KID" --json '{"tags": {"qa": "f08-save"}}' --expect 200 --check success eq true
  control-agent-server api GET "/api/conversations/$KID" --expect 200 \
    --check secret_registry.secret_sources.QA_F08_PLAIN.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F08_PLAIN.value eq null \
    --check secret_registry.secret_sources.QA_F08_DICT.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F08_STATIC.description eq 'qa static' \
    --check secret_registry.secret_sources.QA_F08_STATIC.value eq null --save F08.secrets-update/get
  control-agent-server state cat "server/workspace/conversations/${KID//-/}/base_state.json" --max-chars 200 \
    --check secret_registry.secret_sources.QA_F08_PLAIN.value exists \
    --check secret_registry.secret_sources.QA_F08_PLAIN.value ne '**********' --not-contains qa-f08-plain-value
  control-agent-server state grep qa-f08-dict-value --glob 'server/**/*' --expect-none
  control-agent-server state grep qa-f08-static-value --glob 'server/**/*' --expect-none
  ```
  的 POST 是200。 在保存之后 GET 列出这三个名字
  `StaticSecret` 与 `value` `null`（屏蔽）并保留描述，以及
  `base_state.json` 包含密文：既不是明文也不是
  `**********` 占位符没有密码的服务器写入 (`F08.secrets-no-cipher`)。
- **运行时机密对GET(`F08.secrets-visible`)可见，已知bug。**正控件首先：一个机密后跟着一个标签PATCH（这会保存状态）被GET列出。 然后又发布了一篇机密，并且立即阅读了对话。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_VISIBLE_SAVED": "qa-f08-visible-saved"}}' --expect 200
  control-agent-server api PATCH "/api/conversations/$KID" --json '{"tags": {"qa": "f08-visible"}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check secret_registry.secret_sources.QA_F08_VISIBLE_SAVED.kind eq StaticSecret
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_FRESH": "qa-f08-fresh-value"}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check secret_registry.secret_sources.QA_F08_FRESH.kind eq StaticSecret \
    --save F08.secrets-visible/get  # bug：状态 eq 200 && 检查.0.实际 eq null && response.body.secret_registry.secret_sources.QA_F08_VISIBLE_SAVED.kind eq StaticSecret
  ```
  预期：GET 列出 `QA_F08_FRESH`，因为它列出了已保存的内容。 今天它没有：
  `LocalConversation.update_secrets` 变异
  `state.secret_registry.secret_sources` 到位，状态仅在属性分配时自动保存，GET 读取 `base_state.json` 快照。 该名称出现在下一次状态更改之后（PATCH、消息、策略更改）； 直到那时，实时注册表拥有它，但没有读者可以看到它，并且重新启动会丢失它（`F08.secrets-unsaved-restart`）。
- **机密错误 (`F08.secrets-errors`)。**身体不好，身份不明，没有钥匙。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{}' --expect 422 --check detail.0.loc contains secrets \
    --save F08.secrets-errors/missing
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": "qa"}' --expect 422 --check detail.0.type eq dict_type
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_BAD": {"kind": "NopeSecret", "value": "x"}}}' \
    --expect 422 --check detail.0.msg contains 'Unknown kind'
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_LOOKUP": {"kind": "LookupSecret"}}}' \
    --expect 422 --check detail.0.loc contains url
  control-agent-server api POST "/api/conversations/$NOPE/secrets" --json '{"secrets": {"QA_F08_X": "qa-x"}}' --expect 404
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_X": "qa-x"}}' --auth none --expect 401
  control-agent-server api PATCH "/api/conversations/$KID" --json '{"tags": {"qa": "f08-errors"}}' --expect 200
  control-agent-server api GET "/api/conversations/$KID" --check secret_registry.secret_sources.QA_F08_BAD missing \
    --check secret_registry.secret_sources.QA_F08_LOOKUP missing --check secret_registry.secret_sources.QA_F08_X missing \
    --check secret_registry.secret_sources.QA_F08_PLAIN exists
  ```
  每种状态都匹配，并且在保存后，None个拒绝的姓名会被存储，而机密个之前的姓名则保留。
- **非字符串机密值 (`F08.secrets-bad-value`)。**接受具有字符串值的相同主体（控件）； 然后是数值所属的数字、`null` 和 `true`。
  ```sh
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_STRING": "qa-f08-string-value"}}' --expect 200
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_NUMBER": 5}}' \
    --expect 422 --check detail.0.type eq model_attributes_type --save F08.secrets-bad-value/number
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_NULL": null}}' --expect 422
  control-agent-server api POST "/api/conversations/$KID/secrets" --json '{"secrets": {"QA_F08_BOOL": true}}' --expect 422
  ```
  每个都是标准的422 验证错误 (`model_attributes_type`)，就像任何其他无效的主体，而不是500。
  `UpdateSecretsRequest.convert_string_secrets` 仅转换字符串和 `{"value": ...}` 字典； 其他值按原样达到`SecretSource` 验证。
- 终端 (`F08.secrets-terminal`) 中的 **机密。**存根的命令将 `$QA_F08_TOKEN` 写入文件并回显它。
  ```sh
  SID=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/secret\"}, \"agent\": $SECRET_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$SID/secrets" --json '{"secrets": {"QA_F08_TOKEN": "qa-f08-token-value"}}' \
    --expect 200 --save F08.secrets-terminal/post
  control-agent-server conversation send "$SID" --text 'Run the command.' --wait --until finished --timeout 120
  test "$(cat "$W/secret/qa-f08-token.txt")" = qa-f08-token-value
  control-agent-server conversation events "$SID" --kinds ObservationEvent --contains 'token=<secret-hidden>' \
    --save F08.secrets-terminal/observation
  control-agent-server sink read --name qa-f08-secret --contains 'token=<secret-hidden>' --expect-min 1 --save F08.secrets-terminal/model-request
  control-agent-server sink read --name qa-f08-secret --contains qa-f08-token-value --expect-max 0
  control-agent-server state grep QA_F08_TOKEN --glob 'server/**/*'
  control-agent-server state grep qa-f08-token-value --glob 'server/**/*' --expect-none
  control-agent-server api GET "/api/conversations/$SID" --check secret_registry.secret_sources.QA_F08_TOKEN.kind eq StaticSecret
  ```
  文件实际上包含了真实值，所以命令将其当作环境变量; 的观测结果读取 `token=<secret-hidden>`stub记录的模型请求携带掩码文本，而不是值，而服务器文件中存储了文本（这是glob的正控制）。 运行保存了状态，所以 GET 列出名称。
- **覆盖开始时间机密 (`F08.secrets-override`)。**使用 `QA_F08_ROT` = `qa-f08-rot-old` 创建的对话，然后是新值的运行时 POST。
  ```sh
  ROT=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/rotate\"}, \"agent\": $ROTATE_AGENT, \"autotitle\": false, \"secrets\": {\"QA_F08_ROT\": {\"kind\": \"StaticSecret\", \"value\": \"qa-f08-rot-old\"}}}" \
    --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$ROT/secrets" --json '{"secrets": {"QA_F08_ROT": "qa-f08-rot-new"}}' \
    --expect 200 --save F08.secrets-override/post
  control-agent-server conversation send "$ROT" --text 'Run the command.' --wait --until finished --timeout 120
  test "$(cat "$W/rotate/qa-f08-rot.txt")" = qa-f08-rot-new
  ```
  命令写入了 `qa-f08-rot-new`：运行时值替换了解析时间值的注册表。
- **查找机密 (`F08.secrets-lookup`).**一个运行时 `LookupSecret`，其 URL 是一个回答 `qa-f08-lookup-value` 的 HTTP 接收器，具有
  `Authorization` 标头（一个看起来像机密的名称）和一个普通的标头。
  ```sh
  LOOKUP_URL=$(control-agent-server fixture http-sink --name qa-f08-lookup-src --body qa-f08-lookup-value --print-path)
  LK=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/lookup\"}, \"agent\": $LOOKUP_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$LK/secrets" \
    --json "{\"secrets\": {\"QA_F08_LOOKUP\": {\"kind\": \"LookupSecret\", \"url\": \"$LOOKUP_URL/qa-f08-secret\", \"headers\": {\"Authorization\": \"Bearer qa-f08-lookup-auth\", \"X-QA-F08\": \"qa-f08-header\"}}}}" \
    --expect 200 --check success eq true --save F08.secrets-lookup/post
  control-agent-server sink read --name qa-f08-lookup-src --expect-max 0
  control-agent-server conversation send "$LK" --text 'Run the command.' --wait --until finished --timeout 120
  test "$(cat "$W/lookup/qa-f08-lookup.txt")" = qa-f08-lookup-value
  control-agent-server sink read --name qa-f08-lookup-src --path /qa-f08-secret --contains 'Bearer qa-f08-lookup-auth' \
    --expect-min 1 --save F08.secrets-lookup/fetch
  control-agent-server sink read --name qa-f08-lookup-src --contains qa-f08-header --expect-min 1
  control-agent-server conversation events "$LK" --kinds ObservationEvent --contains 'lookup=<secret-hidden>' --save F08.secrets-lookup/observation
  control-agent-server sink read --name qa-f08-lookup --contains 'lookup=<secret-hidden>' --expect-min 1
  control-agent-server sink read --name qa-f08-lookup --contains qa-f08-lookup-value --expect-max 0
  control-agent-server api GET "/api/conversations/$LK" --check secret_registry.secret_sources.QA_F08_LOOKUP.kind eq LookupSecret \
    --check secret_registry.secret_sources.QA_F08_LOOKUP.url eq "$LOOKUP_URL/qa-f08-secret" \
    --check secret_registry.secret_sources.QA_F08_LOOKUP.headers.X-QA-F08 eq qa-f08-header \
    --check secret_registry.secret_sources.QA_F08_LOOKUP.headers.Authorization missing --save F08.secrets-lookup/get
  control-agent-server state cat "server/workspace/conversations/${LK//-/}/base_state.json" --max-chars 200 \
    --check secret_registry.secret_sources.QA_F08_LOOKUP.headers.Authorization exists --not-contains qa-f08-lookup-auth
  control-agent-server state grep qa-f08-lookup-value --glob 'server/**/*' --expect-none
  ```
  机密时，没有任何内容被获取。 命名的命令
  `QA_F08_LOOKUP` 使服务器 `GET` 成为具有两个标头的 URL，并接收接收器的文本，命令将其写入文件； 观测结果和模型的下一个请求显示 `lookup=<secret-hidden>`。 GET 返回 URL 和明文标头，但保留 `Authorization` 标头，`base_state.json` 将其保留为密文，并且获取的值不会存储在任何地方。
- **服务器自己的机密（`F08.secrets-lookup-self`）。**一个机密存储在`PUT /api/settings/secrets`（设置家族的路由，这里用来安排），然后三个没有头部的运行时`LookupSecret`，所以没有会话密钥：无主机URL
  `/api/settings/secrets/QA_F08_STORED`，相同的 URL 在运行地址上是绝对的，无主机的 URL 是未存储的名称。
  ```sh
  RUN_URL=$(control-agent-server config | jq -r .url)
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F08_STORED", "value": "qa-f08-stored-value"}' --expect 200
  SELF=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/self\"}, \"agent\": $SELF_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$SELF/secrets" \
    --json "{\"secrets\": {\"QA_F08_HOSTLESS\": {\"kind\": \"LookupSecret\", \"url\": \"/api/settings/secrets/QA_F08_STORED\"}, \"QA_F08_ABSOLUTE\": {\"kind\": \"LookupSecret\", \"url\": \"$RUN_URL/api/settings/secrets/QA_F08_STORED\"}, \"QA_F08_ABSENT\": {\"kind\": \"LookupSecret\", \"url\": \"/api/settings/secrets/QA_F08_NOT_STORED\"}}}" \
    --expect 200 --check success eq true --save F08.secrets-lookup-self/post
  control-agent-server conversation send "$SELF" --text 'Run the command.' --wait --until finished --timeout 120
  test "$(cat "$W/self/qa-f08-hostless.txt")" = qa-f08-stored-value
  test "$(cat "$W/self/qa-f08-absolute.txt")" = qa-f08-stored-value
  test -e "$W/self/qa-f08-absent.txt"
  test ! -s "$W/self/qa-f08-absent.txt"
  control-agent-server conversation events "$SELF" --kinds ObservationEvent --contains 'self=<secret-hidden>' \
    --save F08.secrets-lookup-self/observation
  control-agent-server api GET "/api/conversations/$SELF" \
    --check secret_registry.secret_sources.QA_F08_HOSTLESS.url eq "$RUN_URL/api/settings/secrets/QA_F08_STORED" \
    --check secret_registry.secret_sources.QA_F08_HOSTLESS.headers len-eq 0 \
    --check secret_registry.secret_sources.QA_F08_ABSENT.url eq "$RUN_URL/api/settings/secrets/QA_F08_NOT_STORED" \
    --save F08.secrets-lookup-self/get
  control-agent-server logs --grep 'secrets/QA_F08_STORED' --expect-none
  control-agent-server logs --grep 'QA_F08_NOT_STORED' --expect-min 1
  control-agent-server api GET /api/settings/secrets/QA_F08_STORED --auth none --expect 401 --save F08.secrets-lookup-self/no-key
  control-agent-server logs --grep 'secrets/QA_F08_STORED' --expect-min 1
  control-agent-server state grep qa-f08-stored-value --glob 'server/**/*' --expect-none
  control-agent-server api DELETE /api/settings/secrets/QA_F08_STORED --expect 200
  ```
  两者都使用存储名查找，命令为 `qa-f08-stored-value`（已隐藏）
  观测结果中的 `self=<secret-hidden>`），GET 显示在运行地址上绝对存储的无主机 URL（`OH_INTERNAL_SERVER_URL`，服务器从其绑定主机和端口设置）。 没有 HTTP 请求
  `QA_F08_STORED` 未到达服务器：直到该未认证的 GET 之后，该路径没有日志行，服务器以 401 状态码拒绝，并记录日志（日志检查的正控制），因此一个无头 HTTP 查找永远不可能返回该值； 进程内解析器从机密存储中读取它。 未存储的名称会变成真正的 HTTP 请求，服务器会回答 401（已记录）
  `QA_F08_NOT_STORED`)，并且该命令得到一个空值。 对话的状态永远不会保存存储的值； 该项目符号删除存储的机密。
- **智能体简介机密范围 (`F08.secrets-profile-scope`).**仅允许 `QA_F08_ALLOWED` 的智能体配置文件。
  ```sh
  control-agent-server api POST /api/agent-profiles/qa-f08-scoped \
    --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "secret_refs": ["QA_F08_ALLOWED"]}' --expect 201
  SCOPED_PROFILE=$(control-agent-server api GET /api/agent-profiles/qa-f08-scoped --field profile.id)
  PSC=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/scoped\"}, \"agent_profile_id\": \"$SCOPED_PROFILE\", \"autotitle\": false}" \
    --expect 201 --check launched_agent_profile.secret_refs contains QA_F08_ALLOWED --field id)
  control-agent-server api POST "/api/conversations/$PSC/secrets" \
    --json '{"secrets": {"QA_F08_ALLOWED": "qa-f08-allowed-value", "QA_F08_OTHER": "qa-f08-other-value"}}' --expect 200 --check success eq true
  control-agent-server api PATCH "/api/conversations/$PSC" --json '{"tags": {"qa": "f08-scope"}}' --expect 200
  control-agent-server api GET "/api/conversations/$PSC" --check secret_registry.secret_sources.QA_F08_ALLOWED.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F08_OTHER missing --save F08.secrets-profile-scope/get
  control-agent-server api DELETE /api/agent-profiles/qa-f08-scoped --expect 200
  ```
  POST 的值为 200，但 `QA_F08_ALLOWED` 也被存储：`secret_refs` 的机密运行时没有错误。
- **无密码 (`F08.secrets-no-cipher`)。**第二个服务器都没有
  `OH_SECRET_KEY` 也不是会话密钥，因此它没有密码。 它的存根密钥也作为 `OPENAI_API_KEY` 传递：没有密码智能体自己的
  保存时 `api_key` 也是已脱敏，否则重新启动后的运行将在任何命令之前以 `error` (`LLMAuthenticationError`) 结束。
  ```sh
  NC=$(control-agent-server launch --new --no-auth --no-secret-key --name f08-nocipher --print-run \
    --env OPENAI_API_KEY=qa-stub-key)
  trap 'control-agent-server stop --run "$NC" >/dev/null' EXIT
  NC_STEP='tool:terminal:{"command":"printf %s \"$QA_F08_NC\" > qa-f08-nc.txt"}'
  NC_STUB=$(control-agent-server fixture llm-stub --run "$NC" --name qa-f08-nocipher \
    --step "$NC_STEP" --step "$FINISH" --step "$NC_STEP" --step "$FINISH" --print-path)
  N=$(control-agent-server api POST /api/conversations --run "$NC" \
    --json "{\"workspace\": {\"working_dir\": \"$W/nocipher\"}, \"agent\": {\"llm\": {\"model\": \"openai/qa-stub\", \"api_key\": \"qa-stub-key\", \"base_url\": \"$NC_STUB/v1\", \"num_retries\": 0}, \"tools\": [{\"name\": \"terminal\"}]}, \"autotitle\": false}" \
    --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$N/secrets" --run "$NC" --json '{"secrets": {"QA_F08_NC": "qa-f08-nc-value"}}' \
    --expect 200 --save F08.secrets-no-cipher/post
  control-agent-server conversation send "$N" --run "$NC" --text 'Run the command.' --wait --until finished --timeout 120
  test "$(cat "$W/nocipher/qa-f08-nc.txt")" = qa-f08-nc-value
  control-agent-server state cat "server/workspace/conversations/${N//-/}/base_state.json" --run "$NC" --max-chars 200 \
    --check secret_registry.secret_sources.QA_F08_NC.value eq '**********' --not-contains qa-f08-nc-value
  control-agent-server state grep QA_F08_NC --run "$NC" --glob 'server/**/*'
  control-agent-server state grep qa-f08-nc-value --run "$NC" --glob 'server/**/*' --expect-none
  control-agent-server logs --run "$NC" --grep 'OH_SECRET_KEY was not defined' --expect-min 1
  rm "$W/nocipher/qa-f08-nc.txt"
  control-agent-server restart --run "$NC"
  control-agent-server conversation send "$N" --run "$NC" --text 'Run it again.' --wait --until finished --timeout 120
  test -e "$W/nocipher/qa-f08-nc.txt"
  test ! -s "$W/nocipher/qa-f08-nc.txt"
  control-agent-server api GET "/api/conversations/$N" --run "$NC" --check secret_registry.secret_sources.QA_F08_NC.kind eq StaticSecret \
    --check secret_registry.secret_sources.QA_F08_NC.value eq null --save F08.secrets-no-cipher/after-restart
  ```
  在对话期间，命令会 `qa-f08-nc-value`。
  `base_state.json` 保存脱敏占位符 `**********`，而不是值，并且日志携带 `OH_SECRET_KEY was not defined. Secrets will not be persisted between restarts.` 重新启动后，相同的命令以空 `$QA_F08_NC` 运行（文件存在且为空），但 GET 仍然列出 `QA_F08_NC`，与任何其他机密一样被屏蔽，因此客户端无法判断它已丢失。 这是已记录的设计 (`Config.secret_key`)； 该陷阱会停止第二个服务器。
- **使用已保存的机密 (`F08.secrets-restart`) 重新启动。** `$SID` 得到
  `QA_F08_TOKEN` 在运行时并在终端项目符号中运行命令（保存状态）； 重新启动并再次运行相同的命令。

  需要：`F08.secrets-terminal`
  ```sh
  rm "$W/secret/qa-f08-token.txt"
  control-agent-server restart
  control-agent-server doctor
  control-agent-server conversation send "$SID" --text 'Run it again.' --wait --until finished --timeout 120
  test "$(cat "$W/secret/qa-f08-token.txt")" = qa-f08-token-value
  control-agent-server api GET "/api/conversations/$SID" --check secret_registry.secret_sources.QA_F08_TOKEN.kind eq StaticSecret \
    --save F08.secrets-restart/after-restart
  ```
  重启后，服务器健康了，`QA_F08_TOKEN`（用运行时的`OH_SECRET_KEY`加密保存）又注入了。
- **未保存的机密重启(`F08.secrets-unsaved-restart`),已知bug.**一个机密被一个PATCH重启(正控件),另一个被发布，之后服务器重启。
  ```sh
  UNS=$(control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$W/knobs\"}, \"agent\": $OFFLINE_AGENT, \"autotitle\": false}" --expect 201 --field id)
  control-agent-server api POST "/api/conversations/$UNS/secrets" --json '{"secrets": {"QA_F08_SAVED": "qa-f08-saved-value"}}' --expect 200
  control-agent-server api PATCH "/api/conversations/$UNS" --json '{"tags": {"qa": "f08-saved"}}' --expect 200
  control-agent-server api POST "/api/conversations/$UNS/secrets" --json '{"secrets": {"QA_F08_UNSAVED": "qa-f08-unsaved-value"}}' --expect 200
  control-agent-server restart
  control-agent-server api PATCH "/api/conversations/$UNS" --json '{"tags": {"qa": "f08-after-restart"}}' --expect 200
  control-agent-server api GET "/api/conversations/$UNS" --check secret_registry.secret_sources.QA_F08_SAVED.kind eq StaticSecret
  control-agent-server api GET "/api/conversations/$UNS" --check secret_registry.secret_sources.QA_F08_UNSAVED.kind eq StaticSecret \
    --save F08.secrets-unsaved-restart/get  # bug：状态 eq 200 && 检查.0.实际 eq null && response.body.secret_registry.secret_sources.QA_F08_SAVED.kind eq StaticSecret
  ```
  预期：重启后的两个名称。 今天 `QA_F08_SAVED` 在那里并且
  `QA_F08_UNSAVED` 消失了：POST 从未到达 `base_state.json`（参见
  `F08.secrets-visible`) 和机密未写入 `meta.json`，因此，重启、空闲淘汰（默认 20 分钟）或在 `POST .../secrets` 后立即暂停沙箱会无声地丢弃它。

<a id="gotchas"></a>

## 陷阱

- `respond_to_confirmation` `accept: true` 确实是一个运行请求：它需要一个运行槽（429时满），在运行中的会话中是一个无操作，且没有待办事项时，它只是继续智能体。 `accept: false` 没有任何待处理的内容是 200 无操作。 接受后，GET 读取的状态可以停留在 `waiting_for_confirmation` 一段时间，因为运行在后台开始。
- 停在 `waiting_for_confirmation` 中的对话不包含运行槽； 智能体的运行在挂起操作处结束，新的运行在接受时开始，它执行挂起操作而不调用模型。
- `ActionEvent.security_risk` 是模型声明的风险（这里总是
  `UNKNOWN`，存根声明 None)； 分析器的评级（`PatternSecurityAnalyzer` 评级 `rm -rf` `HIGH`）未记录在事件中，因此客户端无法了解为何采取操作。
- 单个 `finish` 或 `think` 操作永远不需要确认，即使在
  `AlwaysConfirm`; 如果没有分析器，每个动作都会被评级 `UNKNOWN`，所以
  `ConfirmRisky` 要求执行每个操作，除非 `confirm_unknown` 是 False。
- 机密值在 GET（屏蔽）中以 `null` 形式返回，在
  `base_state.json`. 如果没有 `OH_SECRET_KEY` 且没有会话密钥，则没有密码：机密（以及智能体的 LLM `api_key`）被保存为
  `**********` 占位符和在重新启动后消失，而 GET 看起来相同 (`F08.secrets-no-cipher`)。 `launch` 设置两个键； 仅
  `launch --no-auth --no-secret-key` 给出没有密码的运行。
- `LookupSecret` 是通过 `httpx` 从服务器进程内部获取的，因此它的 URL 必须可以从服务器访问，而不是从客户端访问。 A
  `LookupSecret` 标头，其名称包含 `authorization`、`cookie`、
  `credential`、`key`、`password`、`secret`、`session` 或 `token`（不区分大小写，`is_secret_key`）被排除在 GET 之外并在 REST 处加密； 其他标头按给定返回。
- 当解析请求时，无主机 `LookupSecret` URL 被设为绝对，从 `OH_INTERNAL_SERVER_URL` （由 `--host`/`--port` 中的 `python -m openhands.agent_server` 设置，通配符绑定变为
  `127.0.0.1`; `http://127.0.0.1:8000` 未设置时），因此 GET 显示绝对值 URL。 `/api/settings/secrets/<name>` 下该地址上的 URL 在过程中从机密存储 (`local_secret_resolver.py`) 得到应答，永远不会超过 HTTP，因此它不需要会话密钥； 只有商店缺少的名称会作为真实请求发出，即 401 没有密钥。
- 仅当命令的文本提及机密的名称（不区分大小写的子字符串匹配）时，命令才会收到机密； 屏蔽适用于每个注册的机密的最后解析值，无论它出现在终端输出中的任何位置。
- 通过 `POST .../secrets` 进行的运行时机密更改仅存在于
  `base_state.json` 和 `meta.json` 从不写入，因此，只有在 `base_state.json` 写入后，一个运行时机密才能存活一次重载（重启、空闲过期、沙箱暂停）。 一个从未到达过的地方就会被丢弃。 参见`F08.secrets-restart`和`F08.secrets-unsaved-restart`。
- 未知对话在对话路由上回答 404 `{"detail": "Not Found"}`，在对话路由上回答 404 `Conversation not found: <id>`
  `respond_to_confirmation`（事件路线）。
- `events/search` 和 `events/count` 的事件 `kind` 过滤器采用裸类名或完全限定的类路径（配方使用后者，`$REJECT_KIND`、`$OBSERVATION_KIND`）； 参见`F06.search-kind-short`。
