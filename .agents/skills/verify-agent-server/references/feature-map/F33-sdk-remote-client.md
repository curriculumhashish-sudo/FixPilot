<a id="python-sdk-remote-client-remoteconversation-remoteworkspace"></a>

# Python SDK 远程客户端 (RemoteConversation, RemoteWorkspace)

消费者通道：建立在该结帐 SDK 上的 Python 程序在驱动 Agent Server 时会观察到什么。 `RemoteWorkspace`（和
`AsyncRemoteWorkspace`) 运行命令、移动文件、读取 git 状态并获取服务器的 LLM 配置文件和 REST 上的机密引用；
`Conversation(agent, workspace=RemoteWorkspace(...))` 返回一个
`RemoteConversation` 创建或重新连接服务器会话，发送消息，运行到完成，同时流式传输事件到回调事件 WebSocket，并引导它（暂停、中断、确认、机密，询问、标题、分叉、关闭）。 同一程序携带服务器端钩子、客户端定义的工具、自定义工具模块、token流式传输和完成日志。 每个菜谱都运行一个真实的 SDK 程序
`control-agent-server exec`并随后通过RESTAPI检查服务器自己的视图，因此报告成功而服务器不同意的SDK在这里失败。

资料来源：`openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`、`openhands-sdk/openhands/sdk/workspace/remote/`、`openhands-sdk/openhands/sdk/conversation/conversation.py`、`openhands-sdk/openhands/sdk/workspace/workspace.py`、`openhands-sdk/openhands/sdk/workspace/models.py`、`openhands-sdk/openhands/sdk/tool/client_tool.py`、`openhands-sdk/openhands/sdk/tool/registry.py`、`openhands-sdk/openhands/sdk/llm/utils/telemetry.py`

需求：`llm`、`tmux`、`git`

路线：None

<a id="sub-features"></a>

## 子功能

- `F33.workspace-exec`: `Workspace(host=...)` 返回一个 `RemoteWorkspace`，其 `execute_command` 返回命令的退出码、标准输出和标准错误，运行在给定的 `cwd`，在 `timeout` 后退出，退出码为 `-1`，标准输出和标准错误为 `timeout_occurred`。 `alive` 和 `get_server_info()` 与服务器匹配。
- `F33.workspace-bad-key`: 有误 `api_key`, `execute_command` 和 `file_upload` 报告 401 失败，而不是抛出，创建对话会引发 401 `HTTPStatusError`, 服务器没有记录任何命令、文件或对话。
- `F33.workspace-background`: `start_command` 返回一个命令 ID，`get_command_output` 在运行时没有退出码，`stop_command` 结束它（没有后续输出），停止未知 ID 是无操作的。
- `F33.workspace-files`: `file_upload` (从路径或从字节)和 `file_download` 逐字传输二进制文件缺少远程文件或相对目的地报告 `success: false` 服务器返回 404 或 400 错误，不留下本地文件。
- `F33.workspace-git`：`git_changes`（相对于 `working_dir` 的路径）和 `git_diff` 返回服务器的 git 路由为具有已修改和未跟踪文件的存储库返回的内容。
- `F33.workspace-settings`: `get_llm()` 解决服务器的活动状态 LLM 具有可使用的密钥的凭证 `get_llm(profile_name=...)` 一个已知的 [unknown names raise] `FileNotFoundError`), `get_secrets()` 返回 `LookupSecret` 无值的引用，和 `get_mcp_config()` 在一台新的服务器上是空的。
- `F33.async-workspace`: `AsyncRemoteWorkspace` 运行命令，启动、读取和停止后台命令，上传和下载文件，读取 Git 改进，Git 差异和服务器信息，并在上下文退出时关闭其客户端。
- `F33.workspace-runtime-scope`：`RemoteWorkspace(runtime_conversation_id=...)` 路由通过 `/api/conversations/{id}/...`：命令默认为会话的工作区并进入其自己的 bash 历史记录，工作区之外的路径将被拒绝，返回 422，未知会话则返回 404。
- `F33.workspace-runtime-lifecycle`: 同步和异步 `get_runtime_session_key()` 获取验证真实子命令的不同工作密钥； `release_runtime()` 删除其容器，同时对话历史记录保持可读，并且重新配置允许第二个 SDK 变体重复生命周期。
- `F33.conversation-create`: `Conversation(agent, workspace=RemoteWorkspace)` 返回一个 `RemoteConversation`，它创建与智能体、工作目录、标签和 `max_iteration_per_run` 的服务器会话； `send_message` 存储消息而不运行，并且智能体的键不回显。
- `F33.conversation-create-request`：`RemoteConversation.create(workspace, StartConversationRequest(...))`使用服务器构建的`agent_settings`、标签和迭代限制中请求的id创建会话，并运行其`initial_message`； 重复相同的请求将返回相同的对话，并且不会添加任何对话或消息。
- `F33.conversation-create-profile`: `RemoteConversation.create(workspace, StartConversationRequest(agent_profile_id=...))` 构建了智能体从一个保存的智能体 profile (its LLM 记录启动的配置文件，并运行它 `initial_message` to `finished`; `get_secrets(agent_profile_id=...)` 只返回  `secret_refs`.
- `F33.conversation-run`：`send_message`加一个阻塞`run()`，一旦智能体完成就返回； 服务器报告`finished`并且智能体写入的文件存在。
- `F33.conversation-callbacks`：回调通过事件 WebSocket 实时接收运行事件，在 `run()` 之后，回调计数，`state.events` 与服务器的已持久化事件逐类匹配。
- `F33.conversation-stats`：`conversation_stats`和`state.execution_status`读回服务器的数字（智能体的LLM的累计成本和提示词token）。
- `F33.conversation-stop-hook`：使用拒绝第一个停止（出口 2）的 `Stop` 钩子，只有在额外的智能体强制转动钩子之后才会返回阻塞 `run()`：当 `run()` 返回时，服务器处于 `finished`，并且 `state.events` 已经持有停止 `HookExecutionEvent`（被阻止，然后允许）和钩子的反馈，逐一匹配服务器。
- `F33.client-tools`: `Conversation(client_tools=[ClientToolSpec(...)])` 将模型的调用交付给回调作为 `ClientAction_<name>` `ActionEvent`，服务器用 `ClientToolObservation` 回应，并完成，第二个程序则不 `client_tools` 重播这些事件。
- `F33.conversation-streaming`：使用 `stream=True` 智能体 LLM、回调实时接收运行的 `StreamingDeltaEvent` 个帧，服务器存储其中的 None 个帧。
- `F33.conversation-token-callbacks`：远程工作区上的 `Conversation(token_callbacks=[...])` 使用运行的流式增量调用 token 回调。
- `F33.conversation-streaming-state`：流式增量不存在于 `state.events` 范围内，它保持与服务器存储的事件匹配。
- `F33.completion-logs`: an 智能体  LLM 与 `log_completions=True` 在每次模型调用时，获取一个日志文件 `log_completions_folder`由客户端撰写的 `LLMCompletionLogEvent`服务器流式传输并存储数据（服务器不写入文件）。
- `F33.conversation-attach`：第二个程序通过 id 与 `RemoteConversation.attach()` 或 `Conversation(conversation_id=...)` 重新连接，并重播相同的历史记录而不创建任何内容； `attach()` 在未知 id 上引发 404，而 `Conversation(conversation_id=<new id>)` 创建该 id。
- `F33.conversation-attach-large`通过整个历史记录，附带与超过100条存储事件的对话。 `state.events` 它包含了服务器事件，按服务器顺序（加上一个未持久化的套接字快照），以及第一次读取 `state.confirmation_policy`, `state.security_analyzer`, `state.hook_config` 和 `state.agent` 等同于服务器。
- `F33.conversation-state-reread`：第二次读取`state.confirmation_policy`、`state.security_analyzer`、`state.agent`和`is_confirmation_mode_active`给出与第一次相同的答案。
- `F33.conversation-ask-title`：`ask_agent()`回答而不添加事件，`generate_title()`返回`max_length`内的标题而不添加事件，`set_title()`更改服务器的标题。
- `F33.conversation-fork`：`fork(title=..., tags=...)`返回`RemoteConversation`，表示具有相同历史记录、标题和标签的新服务器对话； `fork(agent=...)`被客户端拒绝。
- `F33.conversation-fork-branch`: `fork(from_event_id=..., reset_metrics=False)` 返回一个历史结束于该事件（其）的分支 HEAD) 与源的统计信息一起， `navigate_to(None)` 和 `navigate_to(event_id)` 移动叉子的 HEAD 不改变其事件。
- `F33.conversation-plugins-tag`: `Conversation(plugins=[PluginSource(...)])` with inline URL 凭据存储 `plugins` 标记，凭据被屏蔽，token 达到无服务器状态。
- `F33.conversation-confirmation`：`set_confirmation_policy(AlwaysConfirm())`使`run()`在`waiting_for_confirmation`处返回； `reject_pending_actions()` 记录 `UserRejectObservation`，从不运行该操作并离开对话 `idle`。
- `F33.conversation-pause`: `pause()` 从另一个线程在阻塞期间 `run()` 让工具在飞行中完成，使 `run()` 返回 `paused` and a `PauseEvent`, and a later `run()` 继续 `finished`.
- `F33.conversation-interrupt`: `interrupt()` 从另一个线程在阻塞状态下 `run()` 等待模型调用的操作 `run()` 立即返回，无需抛出异常 `paused` with one `InterruptEvent` 和没有 `PauseEvent`, and a later `run()` reaches `finished`.
- `F33.conversation-run-timeout` `run(timeout=...)` 在服务器继续运行时，会 `ConversationRunError` 包裹一个 `TimeoutError`，而另一个 `run()` 正在运行中（服务器的 409 不是错误），并在 `finished` 返回。
- `F33.conversation-run-join-long-tool`：第二个 `run()` 也加入当前工具调用持续时间超过 30 秒的运行，而不是加注。
- `F33.conversation-stuck`：当服务器的卡住检测器停止循环智能体时，`run()` 立即引发 `ConversationRunError`（“卡住”），并且服务器报告 `stuck`。
- `F33.conversation-secrets`：`update_secrets()` 具有纯值，并且具有来自 `get_secrets()` 的 `LookupSecret`，使得两者都可用于智能体的命令，在观测结果中屏蔽并且不以明文形式存储。
- `F33.conversation-run-error`：当模型提供者拒绝密钥时，`run()`提出携带服务器`ConversationErrorEvent`代码的`ConversationRunError`，并且服务器报告`error`。
- `F33.ws-unavailable`：当事件套接字无法连接时，`Conversation(...)` 在 `OPENHANDS_REMOTE_WS_READY_TIMEOUT` 秒后引发 `WebSocketConnectionError`（它创建的会话保留在服务器上）； `OPENHANDS_REMOTE_WS_READY_REQUIRED=false` 继续，`run()` 在服务器完成后约 30 秒通过 REST 回退方案在 `finished` 处返回，`state.events` 与服务器匹配。
- `F33.conversation-reconnect`：活动的 `RemoteConversation` 在服务器重新启动后仍然存在：其事件套接字重新连接，新消息运行到 `finished`，并且 `state.events` 再次与服务器匹配。
- `F33.conversation-reconnect-callbacks`：当活动 `RemoteConversation` 的事件套接字关闭时，服务器记录的事件在套接字恢复后到达其回调，而不仅仅是 `state.events`。
- `F33.conversation-restart`：重新启动后，新程序重新附加到已完成的对话，看到相同的历史记录，并继续到 `finished`。
- `F33.custom-tool-module`：在客户端进程中注册的工具作为`tool_module_qualnames`发送，由`OH_EXTRA_PYTHON_PATH`启动的服务器导入，并在智能体调用时在服务器上运行； 服务器无法导入的客户端注册模块只是记录的警告； 从没有模块的进程重新附加会引发 `ImportError` 命名该工具。
- `F33.custom-tool-module-unimportable`[a conversation whose] 智能体在创建时，如果服务器无法导入模块中的工具，则会拒绝，并以422命名工具和模块，而不是500。
- `F33.conversation-close`：`close()`在`delete_on_close=False`时保留服务器会话，并在`Conversation(...)`工厂默认`delete_on_close=True`适用时删除它。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- SDK 工作区：`Workspace(host=..., api_key=..., working_dir=...)` 或
  `RemoteWorkspace(...)` (`openhands.sdk.workspace`): `execute_command`,
  `start_command`, `get_command_output`, `stop_command`, `file_upload`,
  `file_download`, `git_changes`, `git_diff`, `get_server_info`, `alive`,
  `get_llm`、`get_secrets`、`get_mcp_config` 以及
  `runtime_conversation_id` 对话范围的变体加上
  `get_runtime_session_key` 和 `release_runtime`。 `AsyncRemoteWorkspace` 与 `await` 镜像了命令、文件、git 和 server-info 方法。
- SDK对话：`Conversation(agent=..., workspace=<RemoteWorkspace>, ...)`（工厂； `delete_on_close`默认为`True`）或`RemoteConversation(...)`（`delete_on_close`默认为`False`），`RemoteConversation.create(workspace, StartConversationRequest)`（与`agent_settings`或`agent_profile_id`）和`RemoteConversation.attach(workspace, id)`； 构造函数选项
  `hook_config`, `client_tools`, `callbacks`, `token_callbacks`, `plugins`,
  `tags`, `max_iteration_per_run`; 那么`send_message`,
  `run(blocking=..., timeout=...)`, `pause`, `interrupt`,
  `set_confirmation_policy`, `set_security_analyzer`,
  `reject_pending_actions`, `update_secrets`, `ask_agent`, `generate_title`,
  `set_title`, `fork(title, tags, from_event_id, reset_metrics)`,
  `navigate_to`、`close` 和读取侧 `state` (`execution_status`、
  `events`, `confirmation_policy`, `security_analyzer`, `hook_config`,
  `agent`、`refresh_from_server()`) 和 `conversation_stats`。 智能体端点选项会改变客户端看到的内容：LLM端点`stream=True`（`StreamingDeltaEvent`帧）或`log_completions=True`（客户端生成的完成日志文件），以及客户端注册的工具（发送为`tool_module_qualnames`）。 此处未驱动：`condense` 和
  `load_plugin`，路由 F10 和 F09 驱动器上的一调用包装器。
- 连线：工作区调用 `/api/bash/*`、`/api/file/*`、`/api/git/*`、
  `/server_info`, `/health`, `/api/settings`, `/api/profiles/{name}`,
  `/api/settings/secrets`（或 `/api/conversations/{id}/...` 范围副本）； 对话调用 `/api/conversations` 及其子路由并保持
  `WS /sockets/events/{conversation_id}` 使用第一帧身份验证打开。 那些路线属于他们自己的家族； 这个家庭拥有None。
- 客户端配置：`OPENHANDS_REMOTE_WS_READY_TIMEOUT`（等待事件套接字的秒数，默认 30）和
  `OPENHANDS_REMOTE_WS_READY_REQUIRED`（`false` 没有它继续），两者都由 `F33.ws-unavailable` 驱动。 在服务器上，`OH_EXTRA_PYTHON_PATH` 使自定义工具模块可导入 (`F33.custom-tool-module`)。
- 示例：`examples/02_remote_agent_server/`（01 带钩子的本地服务器、06 自定义工具、11 fork、12 设置和机密、13 `get_llm`、14 客户端工具）； Agent Canvas 和 TypeScript 客户端在没有此 SDK 的情况下到达相同的路由。
- 下面的每个食谱都运行一个heredoc程序
  `control-agent-server exec -- .venv/bin/python -`，注入
  `AGENT_SERVER_URL` 和 `SESSION_API_KEY` 并传递 `$DEEPSEEK_API_KEY`，然后使用 CLI 的 `api` 和 `conversation events` 动词检查服务器。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 基线运行已上线并已导出 (`launch --new`)，`doctor` 可以，
  设置 `$DEEPSEEK_API_KEY`，安装 `tmux` 和 `git`。 下面的块激活服务器上的 deepseek-flash（设置项目符号读取它）并写入 `$F33/f33.py`，每个探针导入的一个小助手（通过
  `--env PYTHONPATH="$F33"`): `workspace(name)` 使 `RemoteWorkspace` 开启
  `$F33/<name>` 与运行的键（`host=` 将其指向其他地方），
  `agent()` deepseek-flash 上的仅限终端智能体，有自己的密钥 (`usage_id` `qa-f33`; 关键字参数转到其 `LLM`），`kinds(events)` 按类别对事件进行计数，不带 `ConversationStateUpdateEvent`，并且
  `emit(name, ...)` 打印 JSON 行并将其保留为 `$F33/<name>.json` 以供 shell 检查。 `Proxy()` 是一个回环 TCP 重定向器，用于处理 socket-outage 短信：REST 通过，`block_ws` 拒绝使用 403 的事件-socket 升级（`refused` 计入），
  `drop_sockets()` 中止打开事件套接字，就像网络故障一样。 每个探针都断言 `assert`，因此失败退出非零并且项目符号失败。
- 它还创建了一个测试夹具（`REPO`，一个修改过的文件和一个未跟踪的文件），服务器机密（`QA_F33_LOOKUP`，由设置读取，机密条目删除，由机密条目）和四个`llm-stub`提供商，每个提供商都用于一个条目以模拟真实模型无法即时生产的提供商行为：`STUB`在每个完成中回答401（运行错误），`LONG_STUB`要求一个精确的`terminal`调用（90秒工具）超时，然后`finish`（运行长工具），`HANG_STUB`保持第一个完成300秒并回答`finish`（`HANG_LOG`是其请求日志）； 中断），并且 `LOOP_STUB` 永远重复一次 `think` 调用（卡住）。 在第一个消息之前，探针调用`set_title()`，这样服务器的自动标题，使用智能体's LLM，就不会消耗脚本步骤。
- run 项目符号的对话 (`CID`) 被 Attach、ask/title、fork 和 fork-branch 项目符号重用只读，并由重启项目符号继续； 创建项目符号的空闲对话 (`IDLE`) 由运行时范围项目符号使用。 已知错误项目符号只读之前记录了哪些正常项目符号（`stream.json`、`$BIG`、模块文件），并且没有设置任何后续项目符号使用。 重新连接、重新启动和自定义工具模块项目符号重新启动运行（最后一个带有
  `OH_EXTRA_PYTHON_PATH`，稍后重新启动 keep）。

  ```sh
  control-agent-server llm preset deepseek
  export F33="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f33"
  export OPENHANDS_SUPPRESS_BANNER=1
  mkdir -p "$F33"
  cat > "$F33/f33.py" <<'EOF'
  """F33 probe helpers: this checkout's SDK against the run exec exports."""
  import asyncio
  import json
  import os
  import threading
  from collections import Counter
  from urllib.parse import urlparse

  from pydantic import SecretStr

  from openhands.sdk import LLM, Agent, Tool
  from openhands.sdk.workspace import RemoteWorkspace
  from openhands.tools.terminal import TerminalTool

  URL = os.environ["AGENT_SERVER_URL"]
  KEY = os.environ["SESSION_API_KEY"]
  DIR = os.environ["F33"]


  def workspace(name, key=KEY, host=URL, **kwargs):
      path = os.path.join(DIR, name)
      os.makedirs(path, exist_ok=True)
      return RemoteWorkspace(host=host, api_key=key, working_dir=path, **kwargs)


  def agent(**llm):
      llm.setdefault("model", "deepseek/deepseek-flash")
      llm.setdefault("api_key", SecretStr(os.environ.get("DEEPSEEK_API_KEY", "")))
      return Agent(llm=LLM(usage_id="qa-f33", **llm), tools=[Tool(name=TerminalTool.name)])


  def kinds(events):
      names = (type(e).__name__ for e in events)
      return dict(Counter(n for n in names if n != "ConversationStateUpdateEvent"))


  def emit(name, **result):
      line = json.dumps(result, default=str, sort_keys=True)
      with open(os.path.join(DIR, f"{name}.json"), "w") as f:
          f.write(line + "\n")
      print(line, flush=True)


  class Proxy:
      """Loopback TCP forwarder to the server that can refuse and drop event sockets."""

      def __init__(self, block_ws=False):
          self.block_ws, self.refused, self.sockets = block_ws, 0, set()
          self.upstream = urlparse(URL)
          self.loop = asyncio.new_event_loop()
          started = threading.Event()

          def serve():
              asyncio.set_event_loop(self.loop)
              server = self.loop.run_until_complete(asyncio.start_server(self._handle, "127.0.0.1", 0))
              self.url = "http://127.0.0.1:%d" % server.sockets[0].getsockname()[1]
              started.set()
              self.loop.run_forever()

          threading.Thread(target=serve, daemon=True).start()
          assert started.wait(10), "proxy did not start"

      async def _handle(self, reader, writer):
          try:
              head = await reader.readuntil(b"\r\n\r\n")
          except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
              writer.close()
              return
          upgrade = b"upgrade: websocket" in head.lower()
          if upgrade and self.block_ws:
              self.refused += 1
              writer.write(b"HTTP/1.1 403 Forbidden\r\ncontent-length: 0\r\nconnection: close\r\n\r\n")
              await writer.drain()
              writer.close()
              return
          up_reader, up_writer = await asyncio.open_connection(self.upstream.hostname, self.upstream.port)
          up_writer.write(head)
          pair = (writer, up_writer)
          if upgrade:
              self.sockets.add(pair)

          async def pipe(src, dst):
              try:
                  while data := await src.read(65536):
                      dst.write(data)
                      await dst.drain()
              except (ConnectionError, OSError):
                  pass
              finally:
                  dst.close()

          await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
          self.sockets.discard(pair)

      def drop_sockets(self):
          def abort():
              for pair in list(self.sockets):
                  for side in pair:
                      side.transport.abort()

          self.loop.call_soon_threadsafe(abort)
  EOF
  REPO=$(control-agent-server fixture git-repo --name qa-f33-repo --print-path)
  export REPO
  STUB=$(control-agent-server fixture llm-stub --name qa-f33-stub --step status:401 --print-path)
  export STUB
  LONG_STUB=$(control-agent-server fixture llm-stub --name qa-f33-long \
    --step 'tool:terminal:{"command":"sleep 45; printf late > qa-f33-long.txt","timeout":90}' \
    --step 'tool:finish:{"message":"qa-f33 long done"}' --print-path)
  export LONG_STUB
  HANG_JSON=$(control-agent-server fixture llm-stub --name qa-f33-hang --step hang:300 --step 'tool:finish:{"message":"qa-f33 resumed"}')
  HANG_STUB=$(jq -r .url <<<"$HANG_JSON")
  HANG_LOG=$(jq -r .requests_log <<<"$HANG_JSON")
  export HANG_STUB HANG_LOG
  LOOP_STUB=$(control-agent-server fixture llm-stub --name qa-f33-loop --step 'tool:think:{"thought":"qa-f33 loop"}' --print-path)
  export LOOP_STUB
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F33_LOOKUP", "value": "qa-f33-lookup-value", "description": "qa f33 lookup"}' --expect 200
  ```

- **命令、服务器信息和活跃度 (`F33.workspace-exec`)。**通过 `RemoteWorkspace` 运行三个命令，然后读取服务器的 bash 历史记录。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-exec/probe -- .venv/bin/python - <<'PY'
  import os
  import time
  import f33
  from openhands.sdk.workspace import RemoteWorkspace, Workspace

  os.makedirs(os.path.join(f33.DIR, "exec"), exist_ok=True)
  ws = Workspace(host=f33.URL, api_key=f33.KEY, working_dir=os.path.join(f33.DIR, "exec"))
  assert isinstance(ws, RemoteWorkspace), type(ws)
  assert ws.alive and not RemoteWorkspace(host="http://127.0.0.1:9", working_dir="/tmp").alive
  r = ws.execute_command("echo qa-f33-out; echo qa-f33-err >&2; exit 3", cwd=ws.working_dir)
  assert (r.exit_code, r.stdout, r.stderr, r.timeout_occurred) == (3, "qa-f33-out\n", "qa-f33-err\n", False), r
  pwd = ws.execute_command("pwd", cwd=ws.working_dir)
  assert (pwd.exit_code, pwd.stdout) == (0, ws.working_dir + "\n"), pwd
  t0 = time.monotonic()
  slow = ws.execute_command("sleep 20", cwd=ws.working_dir, timeout=2)
  assert (slow.exit_code, slow.timeout_occurred) == (-1, True) and time.monotonic() - t0 < 10, slow
  f33.emit("exec", sha=ws.get_server_info()["build_git_sha"])
  PY
  control-agent-server api GET /server_info --auth none --check build_git_sha eq "$(jq -r .sha "$F33/exec.json")"
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand --query sort_order=TIMESTAMP_DESC --query limit=3 \
    --check items.0.command eq 'sleep 20' --check items.0.timeout eq 2 --check items.1.command eq pwd \
    --check items.2.command contains qa-f33-out --check items.2.cwd eq "$F33/exec" --save F33.workspace-exec/server-commands
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashOutput --query sort_order=TIMESTAMP_DESC --query limit=3 \
    --check items.2.exit_code eq 3 --check items.2.stderr contains qa-f33-err --check items.1.exit_code eq 0 \
    --check items.0.exit_code eq -1 --until-ok 15 --save F33.workspace-exec/server-outputs
  ```
  探测器通过； 服务器的最新三个命令是SDK的，`cwd`和`timeout`发送的，它们的输出包含退出码`3`
  `0`和`-1`（服务器也在2秒后停止`sleep 20`）。
- **会话密钥错误 (`F33.workspace-bad-key`)。**运行的关键是有效的（上面的项目符号）； 一个错误的决定不会改变任何事情。
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-bad-key/probe -- .venv/bin/python - <<'PY'
  import httpx
  import f33
  from openhands.sdk import Conversation

  bad = f33.workspace("badkey", key="qa-f33-wrong-key")
  r = bad.execute_command("echo qa-f33-bad-key", cwd=bad.working_dir)
  assert r.exit_code == -1 and "401" in r.stderr, r
  up = bad.file_upload(b"qa-f33-bad\n", bad.working_dir + "/qa-f33-bad.txt")
  assert not up.success and "401" in up.error, up
  try:
      Conversation(agent=f33.agent(), workspace=bad, visualizer=None)
      raise AssertionError("a conversation was created with a wrong key")
  except httpx.HTTPStatusError as e:
      assert e.response.status_code == 401, e
  f33.emit("badkey", stderr=r.stderr[:120])
  PY
  control-agent-server api GET /api/conversations/count --check . eq "$N0"
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand --query sort_order=TIMESTAMP_DESC --query limit=1 \
    --check items.0.command not-contains qa-f33-bad-key --save F33.workspace-bad-key/no-command
  test ! -e "$F33/badkey/qa-f33-bad.txt"
  ```
  `execute_command` 在 stderr 中返回 exit `-1` 和 `Remote execution error: Client error '401 Unauthorized'`（它永远不会引发），上传报告
  `success: false`、`Conversation(...)` 加注； 计数、最新命令和工作区不变。
- **后台命令(`F33.workspace-background`).**启动一个长命令，停止它，读取它的输出。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-background/probe -- .venv/bin/python - <<'PY'
  import time
  import f33

  ws = f33.workspace("bg")
  cmd = ws.start_command("echo qa-f33-bg-start; sleep 60; echo qa-f33-bg-late", cwd=ws.working_dir, timeout=120)
  running = ws.get_command_output(cmd)
  assert running is None or running.get("exit_code") is None, running
  ws.stop_command(cmd)
  deadline = time.monotonic() + 30
  while (out := ws.get_command_output(cmd)) is None or out.get("exit_code") is None:
      assert time.monotonic() < deadline, out
      time.sleep(0.5)
  assert "qa-f33-bg-start" in out["stdout"] and "qa-f33-bg-late" not in out["stdout"], out
  ws.stop_command("0" * 32)
  f33.emit("bg", command_id=cmd, exit_code=out["exit_code"])
  PY
  BG=$(jq -r .command_id "$F33/bg.json")
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashOutput --query command_id__eq="$BG" \
    --check items.-1.exit_code eq "$(jq .exit_code "$F33/bg.json")" --check items.-1.exit_code ne 0 \
    --check items contains qa-f33-bg-start --check items not-contains qa-f33-bg-late --save F33.workspace-background/outputs
  ```
  `start_command`立即返回； 停止的命令以负退出代码（`-15`，SIGTERM）结束，并且仅在停止之前打印输出； 未知的id被忽略（服务器的404被吞掉）。
- **文件往返 (`F33.workspace-files`).**上传 70 kB 的随机字节，下载它们，并与服务器提供的内容进行比较。
  ```sh
  head -c 70000 /dev/urandom > "$F33/qa-f33-upload.bin"
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-files/probe -- .venv/bin/python - <<'PY'
  import os
  import f33

  ws = f33.workspace("files")
  src = os.path.join(f33.DIR, "qa-f33-upload.bin")
  remote = os.path.join(ws.working_dir, "sub", "qa-f33-upload.bin")
  up = ws.file_upload(src, remote)
  assert up.success and up.destination_path == remote, up
  down = ws.file_download(remote, os.path.join(f33.DIR, "qa-f33-download.bin"))
  assert down.success and down.file_size == os.path.getsize(src), down
  mem = ws.file_upload(b"qa-f33-bytes\n", os.path.join(ws.working_dir, "qa-f33-bytes.txt"))
  assert mem.success, mem
  missing = ws.file_download(os.path.join(ws.working_dir, "qa-f33-missing.bin"), os.path.join(f33.DIR, "qa-f33-missing.bin"))
  assert not missing.success and "404" in missing.error, missing
  relative = ws.file_upload(b"qa-f33-relative\n", "qa-f33-relative.txt")
  assert not relative.success and "400" in relative.error, relative
  f33.emit("files", remote=remote, size=down.file_size)
  PY
  cmp "$F33/qa-f33-upload.bin" "$F33/qa-f33-download.bin"
  control-agent-server api GET /api/file/download --query path="$F33/files/sub/qa-f33-upload.bin" --expect 200 \
    --raw-out "$F33/qa-f33-rest.bin" --quiet --save F33.workspace-files/rest-download
  cmp "$F33/qa-f33-upload.bin" "$F33/qa-f33-rest.bin"
  test "$(cat "$F33/files/qa-f33-bytes.txt")" = qa-f33-bytes
  test ! -e "$F33/qa-f33-missing.bin"
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/qa-f33-relative.txt"
  ```
  两个副本与源完全相同。 缺少的文件会以404失败，而相对目的地会以400失败，因为服务器上没有文件工作目录 (`<run>/server`，即相对路径会指向的位置）。
- **Git 更改和差异 (`F33.workspace-git`).**通过 SDK 和 REST 阅读测试夹具存储库。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-git/probe -- .venv/bin/python - <<'PY'
  import os
  import f33
  from openhands.sdk.workspace import RemoteWorkspace

  repo = os.environ["REPO"]
  ws = RemoteWorkspace(host=f33.URL, api_key=f33.KEY, working_dir=os.path.dirname(repo))
  changes = sorted((c.status.value, str(c.path)) for c in ws.git_changes(os.path.basename(repo)))
  assert changes == [("ADDED", "notes.txt"), ("UPDATED", "README.md")], changes
  diff = ws.git_diff(os.path.join(repo, "README.md"))
  assert "Modified, not committed." in diff.modified and "Created by control-agent-server." in diff.original, diff
  f33.emit("git", changes=changes, modified=diff.modified)
  PY
  control-agent-server api GET /api/git/changes --query path="$REPO" --check . len-eq 2 --check . contains README.md \
    --check . contains notes.txt --save F33.workspace-git/changes
  control-agent-server api GET /api/git/diff --query path="$REPO/README.md" --check modified eq "$(jq -r .modified "$F33/git.json")" \
    --save F33.workspace-git/diff
  ```
  的 SDK 将相对仓库名称与之连接 `working_dir`; 两种观点都列出了 `README.md` as `UPDATED` 和 `notes.txt` as `ADDED` 同上。
- 来自服务器 (`F33.workspace-settings`) 的 **LLM 个配置文件、机密和 MCP。**
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.workspace-settings/probe -- .venv/bin/python - <<'PY'
  import os
  import f33

  ws = f33.workspace("settings")
  llm = ws.get_llm()
  assert (llm.model, llm.usage_id) == ("deepseek/deepseek-flash", "profile:deepseek-flash"), llm
  assert llm.api_key.get_secret_value() == os.environ["DEEPSEEK_API_KEY"]
  pro = ws.get_llm(profile_name="deepseek-pro", temperature=0.0)
  assert (pro.model, pro.usage_id, pro.temperature) == ("deepseek/deepseek-v4-pro", "profile:deepseek-pro", 0.0), pro
  try:
      ws.get_llm(profile_name="qa-f33-missing")
      raise AssertionError("an unknown profile resolved")
  except FileNotFoundError:
      pass
  secrets = ws.get_secrets(names=["QA_F33_LOOKUP"])
  lookup = secrets["QA_F33_LOOKUP"]
  assert list(secrets) == ["QA_F33_LOOKUP"] and lookup.url == f33.URL + "/api/settings/secrets/QA_F33_LOOKUP", secrets
  assert "qa-f33-lookup-value" not in lookup.model_dump_json(context={"expose_secrets": True})
  assert ws.get_mcp_config() == {}
  f33.emit("settings", model=llm.model, url=lookup.url)
  PY
  control-agent-server api GET /api/settings --check active_profile eq deepseek-flash --save F33.workspace-settings/settings
  control-agent-server api GET /api/settings/secrets --check secrets contains QA_F33_LOOKUP --check . not-contains qa-f33-lookup-value
  ```
  `get_llm()`跟在`active_profile`之后，携带配置文件的真实密钥； 查找引用包含 URL 和会话标头，而不是值。
- **异步工作区 (`F33.async-workspace`).**
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.async-workspace/probe -- .venv/bin/python - <<'PY'
  import asyncio
  import os
  import f33
  from openhands.sdk.workspace import AsyncRemoteWorkspace


  async def main():
      path = os.path.join(f33.DIR, "async")
      os.makedirs(path, exist_ok=True)
      async with AsyncRemoteWorkspace(host=f33.URL, api_key=f33.KEY, working_dir=path) as ws:
          r = await ws.execute_command("printf qa-f33-async; pwd >&2", cwd=path)
          assert (r.exit_code, r.stdout, r.stderr) == (0, "qa-f33-async", path + "\n"), r
          up = await ws.file_upload(b"qa-f33-async-bytes", os.path.join(path, "a.txt"))
          down = await ws.file_download(os.path.join(path, "a.txt"), os.path.join(f33.DIR, "async-down.txt"))
          assert up.success and down.success and down.file_size == 18, (up, down)
          changes = sorted(str(c.path) for c in await ws.git_changes(os.environ["REPO"]))
          assert changes == ["README.md", "notes.txt"], changes
          diff = await ws.git_diff(os.path.join(os.environ["REPO"], "README.md"))
          assert "Modified, not committed." in diff.modified, diff
          bg = await ws.start_command("echo qa-f33-async-bg; sleep 60; echo qa-f33-async-late", cwd=path, timeout=120)
          running = await ws.get_command_output(bg)
          assert running is None or running.get("exit_code") is None, running
          await ws.stop_command(bg)
          for _ in range(60):
              out = await ws.get_command_output(bg)
              if out is not None and out.get("exit_code") is not None:
                  break
              await asyncio.sleep(0.5)
          assert out and "qa-f33-async-bg" in out["stdout"] and "qa-f33-async-late" not in out["stdout"], out
          await ws.stop_command("0" * 32)
          info = await ws.get_server_info()
      assert ws._client is None
      return info["build_git_sha"], bg, out["exit_code"]


  sha, bg, code = asyncio.run(main())
  f33.emit("async", sha=sha, command_id=bg, exit_code=code)
  PY
  test "$(cat "$F33/async-down.txt")" = qa-f33-async-bytes
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand --query sort_order=TIMESTAMP_DESC --query limit=2 \
    --check items.1.command contains qa-f33-async --check items.1.cwd eq "$F33/async" \
    --check items.0.command contains qa-f33-async-bg --save F33.async-workspace/command
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashOutput --query command_id__eq="$(jq -r .command_id "$F33/async.json")" \
    --check items.-1.exit_code eq "$(jq .exit_code "$F33/async.json")" --check items.-1.exit_code ne 0 \
    --check items not-contains qa-f33-async-late --save F33.async-workspace/background
  ```
  每一次期待的调用都成功了：差异与测试夹具匹配，后台命令被停止（退出码为负数，只打印停止之前的内容），未知ID被忽略，上下文退出会关闭HTTP客户端。
- **创建对话而不运行它 (`F33.conversation-create`)。**
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-create/probe -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation, RemoteConversation

  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("idle"), visualizer=None,
                      delete_on_close=False, tags={"qaf33": "idle"}, max_iteration_per_run=7)
  assert isinstance(conv, RemoteConversation), type(conv)
  conv.send_message("qa-f33 pending message")
  assert conv.state.execution_status.value == "idle"
  f33.emit("idle", cid=str(conv.id))
  conv.close()
  PY
  IDLE=$(jq -r .cid "$F33/idle.json")
  control-agent-server api GET "/api/conversations/$IDLE" --check execution_status eq idle --check workspace.working_dir eq "$F33/idle" \
    --check tags.qaf33 eq idle --check max_iterations eq 7 --check agent.llm.model eq deepseek/deepseek-flash \
    --check agent.llm.usage_id eq qa-f33 --check agent.llm.api_key ne "$DEEPSEEK_API_KEY" --save F33.conversation-create/get
  control-agent-server conversation events "$IDLE" --kinds MessageEvent --contains 'qa-f33 pending message' --expect-count 1
  control-agent-server conversation events "$IDLE" --kinds ActionEvent --expect-count 0
  ```
  服务器存储 SDK 的智能体、工作目录标签和迭代限制。 消息是已持久化，但没有任何操作(`idle`)，GET返回LLM键已脱敏。
- **根据请求创建两次 (`F33.conversation-create-request`)。**服务器从`agent_settings`构建智能体； 然后使用相同的 `conversation_id` 再次提交相同的请求。
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-create-request/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import RemoteConversation, TextContent
  from openhands.sdk.conversation.request import SendMessageRequest, StartConversationRequest
  from openhands.sdk.event import MessageEvent
  from openhands.sdk.workspace import LocalWorkspace

  ws = f33.workspace("request")
  cid = uuid.uuid4()
  request = StartConversationRequest(
      agent_settings={"agent_kind": "openhands", "tools": [{"name": "terminal"}],
                      "llm": {"model": "deepseek/deepseek-flash", "api_key": os.environ["DEEPSEEK_API_KEY"], "usage_id": "qa-f33-settings"}},
      workspace=LocalWorkspace(working_dir=ws.working_dir), conversation_id=cid, tags={"qaf33": "request"}, max_iterations=9,
      initial_message=SendMessageRequest(content=[TextContent(text="qa-f33 create: reply with one word")], run=True),
  )
  first = RemoteConversation.create(ws, request, visualizer=None)
  again = RemoteConversation.create(ws, request, visualizer=None)
  assert first.id == again.id == cid, (first.id, again.id, cid)
  assert (first.agent.llm.model, first.agent.llm.usage_id, first.max_iteration_per_run) == ("deepseek/deepseek-flash", "qa-f33-settings", 9)
  assert first.delete_on_close is False
  users = [e for e in again.state.events if isinstance(e, MessageEvent) and e.source == "user"]
  assert len(users) == 1, users
  f33.emit("request", cid=str(cid))
  first.close()
  again.close()
  PY
  REQ=$(jq -r .cid "$F33/request.json")
  control-agent-server conversation wait "$REQ" --until finished --timeout 300
  control-agent-server api GET /api/conversations/count --check . eq $((N0 + 1))
  control-agent-server api GET "/api/conversations/$REQ" --check execution_status eq finished --check tags.qaf33 eq request \
    --check max_iterations eq 9 --check agent.llm.usage_id eq qa-f33-settings --check workspace.working_dir eq "$F33/request" \
    --save F33.conversation-create-request/get
  control-agent-server api GET "/api/conversations/$REQ/events/search" --query source=user --check items len-eq 1 \
    --check items.0.llm_message.content.0.text eq 'qa-f33 create: reply with one word' --save F33.conversation-create-request/user-messages
  ```
  两个调用都返回请求的 id。 智能体 (模型，`usage_id`) 和迭代次数从服务器返回。 存在一个对话和一个用户消息，`initial_message` 运行的服务器启动后，`finished`（不管服务器的 `run` 字段说什么）都运行。 请参阅陷阱）。
- ** 从已保存的智能体角色（`F33.conversation-create-profile`）创建。** 这个角色允许使用两个服务器机密，没有工具，系统消息后缀，因此它的智能体与默认的不相同。
  ```sh
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F33_PROFILE_IN", "value": "qa-f33-in-value"}' --expect 200
  control-agent-server api PUT /api/settings/secrets --json '{"name": "QA_F33_PROFILE_OUT", "value": "qa-f33-out-value"}' --expect 200
  control-agent-server api POST /api/agent-profiles/qa-f33-profile --expect 201 \
    --json '{"llm_profile_ref": "deepseek-flash", "tools": [], "secret_refs": ["QA_F33_PROFILE_IN"], "system_message_suffix": "qa-f33 profile suffix"}'
  PROFILE=$(control-agent-server api GET /api/agent-profiles/qa-f33-profile --field profile.id)
  control-agent-server exec --env PYTHONPATH="$F33" --env PROFILE="$PROFILE" --save F33.conversation-create-profile/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import RemoteConversation, TextContent
  from openhands.sdk.conversation.request import SendMessageRequest, StartConversationRequest
  from openhands.sdk.workspace import LocalWorkspace

  ws = f33.workspace("profile")
  profile = uuid.UUID(os.environ["PROFILE"])
  everything = ws.get_secrets()
  scoped = ws.get_secrets(agent_profile_id=str(profile))
  assert {"QA_F33_PROFILE_IN", "QA_F33_PROFILE_OUT"} <= set(everything) and list(scoped) == ["QA_F33_PROFILE_IN"], (everything, scoped)
  request = StartConversationRequest(agent_profile_id=profile, workspace=LocalWorkspace(working_dir=ws.working_dir), autotitle=False,
                                     initial_message=SendMessageRequest(content=[TextContent(text="Reply with one word: ready")], run=True))
  conv = RemoteConversation.create(ws, request, visualizer=None)
  assert (conv.agent.llm.model, conv.agent.tools) == ("deepseek/deepseek-flash", []), conv.agent
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("profile", cid=str(conv.id))
  conv.close()
  PY
  PCID=$(jq -r .cid "$F33/profile.json")
  control-agent-server api GET "/api/conversations/$PCID" --check execution_status eq finished --check launched_agent_profile.agent_profile_id eq "$PROFILE" \
    --check launched_agent_profile.secret_refs len-eq 1 --check agent.tools len-eq 0 --check agent.llm.model eq deepseek/deepseek-flash \
    --save F33.conversation-create-profile/get
  control-agent-server conversation events "$PCID" --kinds SystemPromptEvent --contains 'qa-f33 profile suffix' --expect-count 1
  control-agent-server api GET /api/settings/secrets --query agent_profile_id="$PROFILE" --check secrets len-eq 1 \
    --check secrets.0.name eq QA_F33_PROFILE_IN --save F33.conversation-create-profile/scoped-secrets
  control-agent-server api DELETE /api/agent-profiles/qa-f33-profile --expect 200
  control-agent-server api DELETE /api/settings/secrets/QA_F33_PROFILE_IN --expect 200
  control-agent-server api DELETE /api/settings/secrets/QA_F33_PROFILE_OUT --expect 200
  ```
  `get_secrets()` 列出机密和 `get_secrets(agent_profile_id=...)`，仅列出配置文件的 `secret_refs`，就像服务器的作用域列表一样。 智能体会话是 [deepseek-flash] 的（不使用工具，系统中的后缀为提示词），服务器记录启动的会话，初始消息运行到 `finished`（`run()` 加入其中）。 此后，该配置文件和两者机密都会被删除。
- **对话范围工作区 (`F33.workspace-runtime-scope`).**将工作区绑定到 `IDLE` 并探测其边界。

  需要：`F33.conversation-create`
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$IDLE" --save F33.workspace-runtime-scope/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33

  cid = uuid.UUID(os.environ["CID"])
  ws = f33.workspace("idle", runtime_conversation_id=cid)
  assert ws.api_prefix == f"/api/conversations/{cid}"
  r = ws.execute_command("pwd; echo qa-f33-scoped")
  assert (r.exit_code, r.stdout) == (0, ws.working_dir + "\nqa-f33-scoped\n"), r
  inside = ws.file_upload(b"qa-f33-in\n", os.path.join(ws.working_dir, "qa-f33-in.txt"))
  assert inside.success, inside
  outside = ws.file_upload(b"qa-f33-out\n", os.path.join(f33.DIR, "qa-f33-outside.txt"))
  assert not outside.success and "422" in outside.error, outside
  escape = ws.execute_command("pwd", cwd=f33.DIR)
  assert escape.exit_code == -1 and "422" in escape.stderr, escape
  gone = f33.workspace("idle", runtime_conversation_id=uuid.uuid4()).execute_command("true")
  assert gone.exit_code == -1 and "404" in gone.stderr, gone
  f33.emit("scope", prefix=ws.api_prefix)
  PY
  control-agent-server api GET "/api/conversations/$IDLE/bash/bash_events/search" --query kind__eq=BashCommand --check items len-eq 1 \
    --check items.0.command contains qa-f33-scoped --save F33.workspace-runtime-scope/scoped-history
  control-agent-server api GET /api/bash/bash_events/search --query kind__eq=BashCommand --query sort_order=TIMESTAMP_DESC --query limit=1 \
    --check items.0.command not-contains qa-f33-scoped
  test -f "$F33/idle/qa-f33-in.txt"
  test ! -e "$F33/qa-f33-outside.txt"
  ```
  如果没有 `cwd`，则在会话的工作区中运行 scoped 命令。 它在会话的历史中，而不是在主机中。 上传和 `cwd` 之外的工作区都是 422，未知对话 404。
- **运行时按键和释放 (`F33.workspace-runtime-lifecycle`)。**
  需求：`docker`

  首先拉取选定的图像。 这使用隔离的 Docker 运行时服务器、与 F12 相同的固定最小图像和可选的 `AGENT_SERVER_VERIFY_DOCKER_IMAGE` 覆盖。 外部服务器和SDK使用此结帐； 孩子可以是发布的图像，因此它的身份和版本都被记录。 LLM 从未被调用过。
  ```sh
  IMAGE=${AGENT_SERVER_VERIFY_DOCKER_IMAGE:-ghcr.io/openhands/agent-server:1.55.1-python-minimal}
  docker image inspect "$IMAGE" >/dev/null
  DK=$(control-agent-server launch --new --name f33-docker-lifecycle --print-run \
    --config-json "$(jq -nc --arg image "$IMAGE" '{conversation_runtime:"docker",conversation_image:$image,enable_browser:false,conversation_container_memory:"1g"}')")
  trap 'control-agent-server stop --run "$DK" >/dev/null 2>&1 || true' EXIT
  control-agent-server doctor --run "$DK"
  control-agent-server exec --run "$DK" --save F33.workspace-runtime-lifecycle/image -- \
    docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$IMAGE"
  RUNTIME_CID=$(control-agent-server api POST /api/conversations --run "$DK" --expect 201 --timeout 180 --field id \
    --json '{"agent":{"llm":{"model":"openai/qa-no-call","api_key":"qa-placeholder"},"tools":[]},"autotitle":false}' \
    --save F33.workspace-runtime-lifecycle/create)
  control-agent-server api POST "/api/conversations/$RUNTIME_CID/events" --run "$DK" --expect 200 --check success eq true \
    --json '{"role":"user","content":[{"type":"text","text":"QA_F33_RUNTIME_RETAINED"}],"run":false}'
  RUNTIME_OWNER=$(python3 -c 'import hashlib,sys; r=sys.argv[1]; print(hashlib.sha256(f"{r}/server/workspace/conversations\0{r}/home/.openhands".encode()).hexdigest()[:24])' "$DK")
  for MODE in sync async; do
    if [ "$MODE" = async ]; then
      control-agent-server api POST "/api/conversations/$RUNTIME_CID/runtime/reprovision" --run "$DK" \
        --expect 200 --check runtime_status eq available --timeout 180 --save F33.workspace-runtime-lifecycle/reprovision
    fi
    CONTAINER=$(docker ps -q --filter "label=ai.openhands.runtime-owner=$RUNTIME_OWNER")
    control-agent-server assert --value "$CONTAINER" --check . matches '^[0-9a-f]{12}$'
    CHILD_URL="http://$(docker port "$CONTAINER" 8000/tcp)"
    control-agent-server exec --run "$DK" --env CID="$RUNTIME_CID" --env CHILD_URL="$CHILD_URL" --env MODE="$MODE" \
      --save "F33.workspace-runtime-lifecycle/$MODE-sdk" -- .venv/bin/python - <<'PY'
  import asyncio
  import json
  import os
  import uuid
  from openhands.sdk.workspace import AsyncRemoteWorkspace, RemoteWorkspace

  parent_key = os.environ["SESSION_API_KEY"]
  args = dict(host=os.environ["AGENT_SERVER_URL"], api_key=parent_key,
              working_dir="/workspace", runtime_conversation_id=uuid.UUID(os.environ["CID"]))

  async def asynchronous():
      async with AsyncRemoteWorkspace(**args) as ws:
          key = await ws.get_runtime_session_key()
          assert key and key != parent_key, "Expected a distinct child credential"
          async with AsyncRemoteWorkspace(host=os.environ["CHILD_URL"], api_key=key,
                                          working_dir="/workspace") as child:
              info = await child.get_server_info()
              result = await child.execute_command("printf qa-f33-runtime-key")
              assert (result.exit_code, result.stdout) == (0, "qa-f33-runtime-key"), result
          await ws.release_runtime()
          return info

  if os.environ["MODE"] == "async":
      info = asyncio.run(asynchronous())
  else:
      with RemoteWorkspace(**args) as ws:
          key = ws.get_runtime_session_key()
          assert key and key != parent_key, "Expected a distinct child credential"
          with RemoteWorkspace(host=os.environ["CHILD_URL"], api_key=key,
                               working_dir="/workspace") as child:
              info = child.get_server_info()
              result = child.execute_command("printf qa-f33-runtime-key")
              assert (result.exit_code, result.stdout) == (0, "qa-f33-runtime-key"), result
          ws.release_runtime()
  print(json.dumps(dict(mode=os.environ["MODE"], distinct_key=True, authenticated_command=True,
                        released=True, child_info=info)))
  PY
    control-agent-server api GET "/api/conversations/$RUNTIME_CID/runtime" --run "$DK" --expect 200 \
      --check runtime_status eq missing --check can_resume eq true --save "F33.workspace-runtime-lifecycle/$MODE-runtime-missing"
    control-agent-server api GET "/api/conversations/$RUNTIME_CID" --run "$DK" --expect 200 --quiet \
      --check id eq "$RUNTIME_CID" --save "F33.workspace-runtime-lifecycle/$MODE-catalog"
    control-agent-server api GET "/api/conversations/$RUNTIME_CID/events/search" --run "$DK" --expect 200 \
      --check items.1.llm_message.content.0.text eq QA_F33_RUNTIME_RETAINED --save "F33.workspace-runtime-lifecycle/$MODE-history"
    control-agent-server api GET "/api/conversations/$RUNTIME_CID/runtime" --run "$DK" --expect 200 \
      --check runtime_status eq missing --save "F33.workspace-runtime-lifecycle/$MODE-reads-did-not-resume"
    control-agent-server assert --value "$(docker ps -aq --filter "label=ai.openhands.runtime-owner=$RUNTIME_OWNER")" --check . eq ''
  done
  control-agent-server api DELETE "/api/conversations/$RUNTIME_CID" --run "$DK" --expect 200 --save F33.workspace-runtime-lifecycle/delete
  control-agent-server api GET "/api/conversations/$RUNTIME_CID" --run "$DK" --expect 404
  control-agent-server stop --run "$DK"
  ```
  两者 SDK variant获取一个独特的工作密钥，直接对子进程进行认证，然后释放它。 在每次发布后，其运行和停止的容器不存在，而目录和保留事件的读取成功，无需重新配置。 密钥始终驻留在进程内存中，并且从不打印或保存。 本地运行时服务器缺少这些生命周期路由（见陷阱）。
- **发送并运行完成（`F33.conversation-run`、`F33.conversation-callbacks`、`F33.conversation-stats`）。** 智能体写入文件； 探测器对其回调接收到的事件进行计数。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-run/probe -- .venv/bin/python - <<'PY'
  from collections import Counter
  import f33
  from openhands.sdk import Conversation

  seen = Counter()
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("run"), visualizer=None, delete_on_close=False,
                      callbacks=[lambda e: seen.update([type(e).__name__])])
  conv.send_message("Create the file qa-f33-run.txt in the current directory containing exactly: hi")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  assert seen["ActionEvent"] >= 1 and seen["ObservationEvent"] >= 1 and seen["ConversationStateUpdateEvent"] >= 1, seen
  metrics = conv.conversation_stats.get_combined_metrics()
  assert metrics.accumulated_token_usage.prompt_tokens > 0, metrics
  f33.emit("run", cid=str(conv.id), seen=dict(seen), local=f33.kinds(conv.state.events),
           cost=metrics.accumulated_cost, prompt_tokens=metrics.accumulated_token_usage.prompt_tokens)
  conv.close()
  PY
  CID=$(jq -r .cid "$F33/run.json")
  test "$(cat "$F33/run/qa-f33-run.txt")" = hi
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished --check workspace.working_dir eq "$F33/run" \
    --check stats.usage_to_metrics.qa-f33.accumulated_cost eq "$(jq .cost "$F33/run.json")" \
    --check stats.usage_to_metrics.qa-f33.accumulated_token_usage.prompt_tokens eq "$(jq .prompt_tokens "$F33/run.json")" \
    --save F33.conversation-run/get
  for K in SystemPromptEvent MessageEvent ActionEvent ObservationEvent; do
    test "$(jq ".seen.$K // 0" "$F33/run.json")" -eq "$(jq ".local.$K // 0" "$F33/run.json")"
    control-agent-server conversation events "$CID" --kinds $K --expect-count "$(jq ".local.$K // 0" "$F33/run.json")"
  done
  control-agent-server conversation events "$CID" --kinds ObservationEvent --contains qa-f33-run.txt --expect-kind ObservationEvent \
    --save F33.conversation-callbacks/observations
  ```
  一旦服务器为`finished`，`run()`就返回； 该文件包含 `hi`； 对于每种事件类型，回调计数、`state.events` 计数和服务器计数一致； 成本和提示词 token 等于服务器的 `stats`。
- **拒绝第一次停止的停止钩子 (`F33.conversation-stop-hook`)。**挂钩在服务器上运行（`hook_config` 在创建请求中传播）。 钩子在工作区计数调用次数，并在第一次调用时退出，因此服务器报告`finished`，运行钩子，切换到`running`，并用钩子的stderr作为反馈给智能体一次额外的机会。 探测器在 `run()` 返回时读取服务器的状态。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-stop-hook/probe -- .venv/bin/python - <<'PY'
  import os
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ActionEvent, HookExecutionEvent, MessageEvent
  from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher

  ws = f33.workspace("stophook")
  calls = os.path.join(ws.working_dir, "qa-f33-stop-calls")
  command = (f"echo call >> {calls}; if [ $(wc -l < {calls}) -eq 1 ]; then "
             "echo 'qa-f33 stop hook: first create the file qa-f33-stop.txt containing exactly: again' >&2; exit 2; fi")
  conv = Conversation(agent=f33.agent(), workspace=ws, visualizer=None, delete_on_close=False,
                      hook_config=HookConfig(stop=[HookMatcher(hooks=[HookDefinition(command=command)])]))
  conv.send_message("Reply with one word: ready")
  conv.run(timeout=300)
  status = conv.state.refresh_from_server()["execution_status"]
  events = list(conv.state.events)
  stops = [i for i, e in enumerate(events) if isinstance(e, HookExecutionEvent) and e.hook_event_type == "Stop"]
  assert status == "finished", status
  assert [(events[i].blocked, events[i].exit_code) for i in stops] == [(True, 2), (False, 0)], [events[i] for i in stops]
  feedback = next(i for i, e in enumerate(events) if isinstance(e, MessageEvent) and e.source == "environment"
                  and "qa-f33 stop hook" in e.llm_message.content[0].text)
  assert stops[0] < feedback < stops[1], (stops, feedback)
  turns = [e for e in events[feedback:stops[1]] if isinstance(e, (ActionEvent, MessageEvent)) and e.source == "agent"]
  assert turns, events[feedback:]
  with open(calls) as f:
      assert f.read().count("call") == 2
  f33.emit("stophook", cid=str(conv.id), local=f33.kinds(events), turns_after_feedback=len(turns))
  conv.close()
  PY
  HOOK=$(jq -r .cid "$F33/stophook.json")
  control-agent-server api GET "/api/conversations/$HOOK" --check execution_status eq finished \
    --check hook_config.stop.0.hooks.0.command contains qa-f33-stop-calls --save F33.conversation-stop-hook/get
  control-agent-server conversation events "$HOOK" --kinds HookExecutionEvent --contains '"blocked": true' --expect-count 1 \
    --save F33.conversation-stop-hook/blocked
  control-agent-server conversation events "$HOOK" --kinds HookExecutionEvent --contains '"exit_code": 0' --expect-count 1
  for K in HookExecutionEvent MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$HOOK" --kinds $K --expect-count "$(jq ".local.$K // 0" "$F33/stophook.json")"
  done
  ```
  当 `run()` 返回服务器已经报告 `finished`，并且
  `state.events` 保存被阻止的停止（出口 2）、钩子的反馈（
  `environment` 消息），之后至少一智能体圈，以及允许的停止（出口 0），每种计数与服务器相同。 在第一次 `finished` 状态更新时返回的客户端将在此处看到 `running` 以及最多一个挂钩事件（竞赛 `AGENTS.md` 描述）。
- **客户端定义的工具(`F33.client-tools`)。**该工具仅作为 JSON 规范存在； 服务器将其注入智能体并确认每个调用，客户端处理来自其回调的调用。 然后附加第二个程序，无需 `client_tools`。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.client-tools/probe -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ActionEvent, ObservationEvent
  from openhands.sdk.tool.client_tool import ClientToolObservation, ClientToolSpec

  spec = ClientToolSpec(name="qa_f33_notify", description="Show a notification to the user (qa-f33 client tool).",
                        parameters={"type": "object", "properties": {"message": {"type": "string", "description": "Notification text"}},
                                    "required": ["message"]})
  calls = []
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("clienttool"), visualizer=None, delete_on_close=False, client_tools=[spec],
                      callbacks=[lambda e: isinstance(e, ActionEvent) and e.tool_name == "qa_f33_notify" and calls.append(e)])
  conv.send_message("Call the qa_f33_notify tool exactly once with the message qa-f33-ping, then finish.")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  assert len(calls) == 1, calls
  action = calls[0].action
  assert type(action).__name__ == "ClientAction_qa_f33_notify" and isinstance(action.model_dump()["message"], str), action
  acks = [e for e in conv.state.events if isinstance(e, ObservationEvent) and e.tool_name == "qa_f33_notify"]
  assert len(acks) == 1 and isinstance(acks[0].observation, ClientToolObservation), acks
  assert acks[0].action_id == calls[0].id, (acks[0].action_id, calls[0].id)
  f33.emit("clienttool", cid=str(conv.id), action=calls[0].id, args=action.model_dump(), local=f33.kinds(conv.state.events))
  conv.close()
  PY
  CT=$(jq -r .cid "$F33/clienttool.json")
  control-agent-server api GET "/api/conversations/$CT" --check execution_status eq finished --check client_tools.0.name eq qa_f33_notify \
    --check agent.tools contains qa_f33_notify --save F33.client-tools/get
  control-agent-server conversation events "$CT" --kinds ActionEvent --contains '"kind": "ClientAction_qa_f33_notify"' --expect-count 1 \
    --save F33.client-tools/action
  control-agent-server conversation events "$CT" --kinds ObservationEvent --contains '"kind": "ClientToolObservation"' --expect-count 1
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CT" --save F33.client-tools/reattach -- .venv/bin/python - <<'PY'
  import json
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation, RemoteConversation
  from openhands.sdk.event import ActionEvent

  cid = uuid.UUID(os.environ["CID"])
  first = json.load(open(os.path.join(f33.DIR, "clienttool.json")))
  saved = RemoteConversation.attach(f33.workspace("clienttool"), cid, visualizer=None)
  same = Conversation(agent=f33.agent(), workspace=f33.workspace("clienttool"), conversation_id=cid, visualizer=None, delete_on_close=False)
  for conv in (saved, same):
      acts = [e for e in conv.state.events if isinstance(e, ActionEvent) and e.tool_name == "qa_f33_notify"]
      assert [(e.id, type(e.action).__name__, e.action.model_dump()) for e in acts] == [
          (first["action"], "ClientAction_qa_f33_notify", first["args"])], acts
      assert f33.kinds(conv.state.events) == first["local"], f33.kinds(conv.state.events)
  f33.emit("clienttool-reattach", replayed=len(acts))
  saved.close()
  same.close()
  PY
  ```
  回调接收一个 `ActionEvent`，其操作是打出来的
  `ClientAction_qa_f33_notify` 带有字符串 `message`； 服务器用 `ClientToolObservation`（“工具调用分派给客户端。”）回答它，然后运行完成。 一个从未声明工具的新进程会重播相同的动作，通过两个挂载路径（SDK 注册了服务器已持久化之前同步事件）。
- **已直播 token (`F33.conversation-streaming`).** 智能体 LLM 与
  `stream=True`、token 回调和事件回调保持
  `StreamingDeltaEvent` 帧。 token 和 `state.events` 结果记录在这之后的两个项目符号中。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-streaming/probe -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import StreamingDeltaEvent

  tokens, deltas = [], []
  conv = Conversation(agent=f33.agent(stream=True), workspace=f33.workspace("stream"), visualizer=None, delete_on_close=False,
                      token_callbacks=[tokens.append], callbacks=[lambda e: isinstance(e, StreamingDeltaEvent) and deltas.append(e)])
  conv.set_title("qa-f33 stream")
  conv.send_message("Reply with one short sentence about the sea.")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  assert deltas and any(d.content or d.reasoning_content for d in deltas), deltas
  f33.emit("stream", cid=str(conv.id), deltas=len(deltas), tokens=len(tokens), local=f33.kinds(conv.state.events))
  conv.close()
  PY
  STREAM=$(jq -r .cid "$F33/stream.json")
  control-agent-server api GET "/api/conversations/$STREAM" --check execution_status eq finished --check agent.llm.stream eq true \
    --save F33.conversation-streaming/get
  control-agent-server conversation events "$STREAM" --kinds StreamingDeltaEvent --expect-count 0 --save F33.conversation-streaming/stored
  control-agent-server api GET "/api/conversations/$STREAM" --check stats.usage_to_metrics.qa-f33.accumulated_token_usage.completion_tokens gt 0
  ```
  回调接收运行的差分数据，这些差分数据通过事件套接字实时发送（一个句子中有几十个），而服务器存储的事件则包含None：这些差分数据是瞬态帧，而回复本身则被存储为一个
  `MessageEvent`（或 `finish` 操作）。
- **token 回调进行远程对话 (`F33.conversation-token-callbacks`)。** `Conversation(...)` 工厂将 `token_callbacks` 转发至
  `RemoteConversation`，它将事件套接字中的每个 `StreamingDeltaEvent` 帧作为 `LLMStreamChunk`（增量的 `content` 和
  `choices[0].delta` 中的 `reasoning_content`），因此他们收到运行的增量。

  需要：`F33.conversation-streaming`
  ```sh
  test "$(jq .deltas "$F33/stream.json")" -gt 0
  control-agent-server assert --json "$F33/stream.json" --check tokens gt 0
  ```
  回调事件获得了差异（控制权），而 token 和回调也都获得了这些差异。
- **Delta 被排除在 `state.events` (`F33.conversation-streaming-state`) 之外。**
  `RemoteConversation` 的默认值回调会跳过服务器从不存储的瞬态增量，因此它们仅到达回调，而 `state.events` 保持与服务器匹配。

  需要：`F33.conversation-streaming`
  ```sh
  test "$(jq '.local.MessageEvent // 0' "$F33/stream.json")" -eq "$(control-agent-server conversation events "$STREAM" --kinds MessageEvent | jq .matching)"
  control-agent-server assert --json "$F33/stream.json" --check local.StreamingDeltaEvent missing
  ```
  存储的类型一致，`state.events` 仍然成立，尽管 `StreamingDeltaEvent` 看到一个回调。
- **客户端上的完成日志 (`F33.completion-logs`)。**一个智能体 LLM
  with `log_completions=True` and a relative `log_completions_folder`. The
  服务器用 `LLMCompletionLogEvent` 替换文件日志记录； 客户端将它们写入自己的工作目录下，服务器的工作目录（`<run>/server`）将显示服务器自己编写的任何文件。
  ```sh
  mkdir -p "$F33/logs-client"
  control-agent-server exec --cwd "$F33/logs-client" --env PYTHONPATH="$F33" --save F33.completion-logs/probe -- "$PWD/.venv/bin/python" - <<'PY'
  import os
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import LLMCompletionLogEvent

  seen = []
  conv = Conversation(agent=f33.agent(log_completions=True, log_completions_folder="qa-f33-logs"), workspace=f33.workspace("logs"),
                      visualizer=None, delete_on_close=False, callbacks=[lambda e: isinstance(e, LLMCompletionLogEvent) and seen.append(e)])
  conv.set_title("qa-f33 logs")
  conv.send_message("Reply with one word: ready")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  files = sorted(os.listdir("qa-f33-logs"))
  assert files and files == sorted(e.filename for e in seen), (files, [e.filename for e in seen])
  assert all(e.usage_id == "qa-f33" and e.model_name == "deepseek/deepseek-flash" for e in seen), seen
  f33.emit("logs", cid=str(conv.id), files=files)
  conv.close()
  PY
  LOGS=$(jq -r .cid "$F33/logs.json")
  NLOGS=$(jq '.files | length' "$F33/logs.json")
  control-agent-server conversation events "$LOGS" --kinds LLMCompletionLogEvent --expect-count "$NLOGS" --save F33.completion-logs/stored
  for NAME in $(jq -r '.files[]' "$F33/logs.json"); do
    control-agent-server conversation events "$LOGS" --kinds LLMCompletionLogEvent --contains "$NAME" --expect-count 1
    test -s "$F33/logs-client/qa-f33-logs/$NAME"
  done
  test ! -e "$AGENT_SERVER_VERIFY_RUN/server/qa-f33-logs"
  control-agent-server state grep deepseek-flash --glob 'fixtures/qa-f33/logs-client/qa-f33-logs/*'
  ```
  每个模型调用都会将一个文件存储在客户端的`qa-f33-logs`，并根据套接字发送的事件命名。 服务器存储了相同的事件，并未生成自己的文件。`set_title()` 服务器的自动标题会引发一次额外的登录调用到智能体's LLM，通常在 `run()` 返回之后。
- **从第二个程序重新连接 (`F33.conversation-attach`)。**

  需要：`F33.conversation-run`
  ```sh
  N0=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CID" --save F33.conversation-attach/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import httpx
  import f33
  from openhands.sdk import Conversation, RemoteConversation
  from openhands.sdk.event import MessageEvent

  cid = uuid.UUID(os.environ["CID"])
  ws = f33.workspace("run")
  saved = RemoteConversation.attach(ws, cid, visualizer=None)
  same = Conversation(agent=f33.agent(), workspace=ws, conversation_id=cid, visualizer=None, delete_on_close=False)
  assert saved.id == same.id == cid
  assert f33.kinds(saved.state.events) == f33.kinds(same.state.events)
  first = next(e for e in saved.state.events if isinstance(e, MessageEvent) and e.source == "user")
  assert "qa-f33-run.txt" in first.llm_message.content[0].text, first
  assert saved.state.execution_status.value == "finished" and saved.agent.llm.model == "deepseek/deepseek-flash"
  try:
      RemoteConversation.attach(ws, uuid.uuid4(), visualizer=None)
      raise AssertionError("attach accepted an unknown id")
  except httpx.HTTPStatusError as e:
      assert e.response.status_code == 404, e
  wanted = uuid.uuid4()
  made = Conversation(agent=f33.agent(), workspace=ws, conversation_id=wanted, visualizer=None, delete_on_close=False)
  assert made.id == wanted, (made.id, wanted)
  f33.emit("attach", kinds=f33.kinds(saved.state.events), made=str(made.id))
  for conv in (saved, same, made):
      conv.close()
  PY
  control-agent-server api GET /api/conversations/count --check . eq $((N0 + 1))
  control-agent-server api GET "/api/conversations/$(jq -r .made "$F33/attach.json")" --check execution_status eq idle \
    --save F33.conversation-attach/created-by-id
  for K in MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$CID" --kinds $K --expect-count "$(jq ".kinds.$K" "$F33/attach.json")"
  done
  ```
  两条重新连接路径都会重放同一份历史（第一条用户消息、
  `finished`，保存的智能体）并且什么也不创建； 只有明确的新 ID 才会添加一个对话。
- **依附悠久的历史(`F33.conversation-attach-large`)。**种子程序设置确认策略、安全分析器和
  `PreToolUse`钩子，然后排队110条消息（无模型调用）； 服务器存储了200多个事件。 第二个程序附加两种方式并与服务器的分页搜索进行比较。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-attach-large/seed -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
  from openhands.sdk.security.confirmation_policy import AlwaysConfirm
  from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer

  hooks = HookConfig(pre_tool_use=[HookMatcher(matcher="terminal", hooks=[HookDefinition(command="true # qa-f33 large")])])
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("large"), visualizer=None, delete_on_close=False, hook_config=hooks)
  conv.set_title("qa-f33 large")
  conv.set_confirmation_policy(AlwaysConfirm())
  conv.set_security_analyzer(LLMSecurityAnalyzer())
  for i in range(110):
      conv.send_message(f"qa-f33 seed {i:03d}")
  f33.emit("large", cid=str(conv.id))
  conv.close()
  PY
  BIG=$(jq -r .cid "$F33/large.json")
  control-agent-server conversation events "$BIG" --kinds MessageEvent --expect-count 110
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$BIG" --save F33.conversation-attach-large/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import httpx
  import f33
  from openhands.sdk import Conversation, RemoteConversation
  from openhands.sdk.event import ConversationStateUpdateEvent, MessageEvent

  cid = uuid.UUID(os.environ["CID"])
  server, page = [], None
  with httpx.Client(base_url=f33.URL, headers={"X-Session-API-Key": f33.KEY}) as http:
      while True:
          body = http.get(f"/api/conversations/{cid}/events/search", params={"limit": 100, **({"page_id": page} if page else {})}).json()
          server += [e["id"] for e in body["items"]]
          if not (page := body.get("next_page_id")):
              break
      info = http.get(f"/api/conversations/{cid}").json()
  assert len(server) > 200, len(server)
  for conv in (RemoteConversation.attach(f33.workspace("large"), cid, visualizer=None),
               Conversation(agent=f33.agent(), workspace=f33.workspace("large"), conversation_id=cid, visualizer=None, delete_on_close=False)):
      snapshots = [e for e in conv.state.events if isinstance(e, ConversationStateUpdateEvent) and e.key == "full_state"]
      ids = [e.id for e in conv.state.events if e not in snapshots]
      assert len(snapshots) == 1 and ids == server, (len(snapshots), len(ids), len(server))
      seeds = [e.llm_message.content[0].text for e in conv.state.events if isinstance(e, MessageEvent)]
      assert seeds == [f"qa-f33 seed {i:03d}" for i in range(110)], seeds[:3]
      state = conv.state
      assert state.confirmation_policy.model_dump() == info["confirmation_policy"], state.confirmation_policy
      assert state.security_analyzer.model_dump() == info["security_analyzer"], state.security_analyzer
      assert state.hook_config.model_dump(mode="json", by_alias=True) == info["hook_config"], state.hook_config
      agent = state.agent
      assert (agent.llm.model, [t.name for t in agent.tools]) == (info["agent"]["llm"]["model"], [t["name"] for t in info["agent"]["tools"]])
      conv.close()
  f33.emit("attachlarge", events=len(server))
  PY
  control-agent-server api GET "/api/conversations/$BIG" --check confirmation_policy.kind eq AlwaysConfirm \
    --check security_analyzer.kind eq LLMSecurityAnalyzer --check hook_config.pre_tool_use.0.hooks.0.command eq 'true # qa-f33 large' \
    --check execution_status eq idle --save F33.conversation-attach-large/get
  test "$(control-agent-server conversation events "$BIG" | jq .total)" -eq "$(jq .events "$F33/attachlarge.json")"
  ```
  SDK 页显示了 100 个历史事件：`state.events` 包含服务器的顺序存储事件，以及连接时发送的全状态快照（已持久化从未出现），110 条消息按顺序排列，以及每个状态字段的第一次读取等于服务器的 GET。
- **读取状态两次(`F33.conversation-state-reread`)。**
  `RemoteState` 在每次读取时都会验证其缓存的会话信息，因此验证一个多态字段必须不改变它所给的字典：验证器 (`openhands/sdk/utils/models.py`) 在删除 `kind` 之前先复制了输入，而第二次读取会返回相同的值。

  需要：`F33.conversation-attach-large`
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$BIG" --save F33.conversation-state-reread/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import RemoteConversation


  def read(conv, name):
      try:
          value = getattr(conv.state, name) if name != "is_confirmation_mode_active" else conv.is_confirmation_mode_active
      except Exception as e:  # recorded, compared below
          return f"error: {type(e).__name__}"
      return value if isinstance(value, bool) else type(value).__name__


  cid = uuid.UUID(os.environ["CID"])
  reads = {}
  for name in ("confirmation_policy", "security_analyzer", "agent", "is_confirmation_mode_active"):
      conv = RemoteConversation.attach(f33.workspace("large"), cid, visualizer=None)
      reads[name] = [read(conv, name), read(conv, name)]
      conv.close()
  assert reads["confirmation_policy"][0] == "AlwaysConfirm" and reads["security_analyzer"][0] == "LLMSecurityAnalyzer", reads
  assert reads["agent"][0] == "Agent" and reads["is_confirmation_mode_active"][0] is True, reads
  f33.emit("reread", reads=reads, stable=all(first == second for first, second in reads.values()))
  PY
  control-agent-server assert --json "$F33/reread.json" --check stable eq true
  ```
  每个字段在每次新连接的会话上读取，并且每次读取的第一个字段是正确的（控制）。 第二读返回 `AlwaysConfirm`
  再次 `LLMSecurityAnalyzer` 和 `Agent`，`is_confirmation_mode_active` 仍为 `True`，中间没有套接字快照或 `state.refresh_from_server()`。
- **询问、生成并设置标题 (`F33.conversation-ask-title`)。**

  需要：`F33.conversation-run`
  ```sh
  E0=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CID" --save F33.conversation-ask-title/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation

  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("run"), conversation_id=uuid.UUID(os.environ["CID"]),
                      visualizer=None, delete_on_close=False)
  answer = conv.ask_agent("Answer with one word, yes or no: did you create a file?")
  assert isinstance(answer, str) and answer.strip(), answer
  title = conv.generate_title(max_length=40)
  assert isinstance(title, str) and 0 < len(title) <= 40, title
  conv.set_title("qa-f33 title")
  f33.emit("ask", answer=answer[:80], title=title)
  conv.close()
  PY
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$E0"
  control-agent-server api GET "/api/conversations/$CID" --check title eq 'qa-f33 title' --check execution_status eq finished \
    --save F33.conversation-ask-title/get
  ```
  答案和生成的标题都不为空。 事件计数保持不变，服务器标题为设置的值。
- **叉子 (`F33.conversation-fork`).**

  需要：`F33.conversation-run`
  ```sh
  E0=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CID" --save F33.conversation-fork/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation, RemoteConversation

  src = Conversation(agent=f33.agent(), workspace=f33.workspace("run"), conversation_id=uuid.UUID(os.environ["CID"]),
                     visualizer=None, delete_on_close=False)
  try:
      src.fork(agent=f33.agent())
      raise AssertionError("fork accepted an agent")
  except NotImplementedError:
      pass
  fork = src.fork(title="qa-f33 fork", tags={"qaf33": "fork"})
  assert isinstance(fork, RemoteConversation) and fork.id != src.id
  assert f33.kinds(fork.state.events) == f33.kinds(src.state.events)
  f33.emit("fork", fork=str(fork.id), kinds=f33.kinds(fork.state.events))
  fork.close()
  src.close()
  PY
  FORK=$(jq -r .fork "$F33/fork.json")
  control-agent-server api GET "/api/conversations/$FORK" --check title eq 'qa-f33 fork' --check tags.qaf33 eq fork \
    --check execution_status eq idle --save F33.conversation-fork/get
  for K in MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$FORK" --kinds $K --expect-count "$(jq ".kinds.$K" "$F33/fork.json")"
  done
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$E0" --save F33.conversation-fork/source-count
  ```
  fork是一个新的`idle`对话，包含源事件、标题和标签。 源码保留自己的 id 和事件计数。
- **从事件中分叉，然后移动 HEAD (`F33.conversation-fork-branch`)。**在第一个用户消息处分叉 `CID`，保留指标。

  需要：`F33.conversation-run`
  ```sh
  E0=$(control-agent-server api GET "/api/conversations/$CID/events/count" --field .)
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CID" --save F33.conversation-fork-branch/probe -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ConversationStateUpdateEvent, MessageEvent


  def stored(conv):
      return [e for e in conv.state.events if not (isinstance(e, ConversationStateUpdateEvent) and e.key == "full_state")]


  src = Conversation(agent=f33.agent(), workspace=f33.workspace("run"), conversation_id=uuid.UUID(os.environ["CID"]),
                     visualizer=None, delete_on_close=False)
  events = stored(src)
  first = next(e for e in events if isinstance(e, MessageEvent) and e.source == "user")
  branch = src.fork(from_event_id=first.id, reset_metrics=False, title="qa-f33 branch")
  kept = stored(branch)
  assert [e.id for e in kept] == [e.id for e in events if not isinstance(e, ConversationStateUpdateEvent)][: len(kept)], kept
  assert kept[-1].id == first.id and len(kept) < len(events), (len(kept), len(events))
  assert branch.state.refresh_from_server()["leaf_event_id"] == first.id
  assert branch.conversation_stats.model_dump() == src.conversation_stats.model_dump()
  branch.navigate_to(None)
  assert branch.state._cached_state["leaf_event_id"] is None
  branch.navigate_to(first.id)
  assert branch.state._cached_state["leaf_event_id"] == first.id
  f33.emit("branch", fork=str(branch.id), first=first.id, kept=len(kept),
           cost=src.conversation_stats.usage_to_metrics["qa-f33"].accumulated_cost)
  branch.close()
  src.close()
  PY
  BRANCH=$(jq -r .fork "$F33/branch.json")
  control-agent-server api GET "/api/conversations/$BRANCH" --check title eq 'qa-f33 branch' --check leaf_event_id eq "$(jq -r .first "$F33/branch.json")" \
    --check stats.usage_to_metrics.qa-f33.accumulated_cost eq "$(jq .cost "$F33/branch.json")" --save F33.conversation-fork-branch/get
  control-agent-server api GET "/api/conversations/$BRANCH/events/count" --check . eq "$(jq .kept "$F33/branch.json")"
  control-agent-server api GET "/api/conversations/$CID/events/count" --check . eq "$E0"
  ```
  分支包含源的事件，直到并包括第一个用户消息（系统提示词和消息），其HEAD是该消息，其统计信息等于源的； `navigate_to(None)`清空HEAD和
  `navigate_to(<message id>)` 恢复它（SDK 刷新缓存状态，因为 `leaf_event_id` 未推送到套接字上）。 来源不变。
- **插件源包含凭据（`F33.conversation-plugins-tag`）。**插件在首次运行时是懒加载的，因此一个从不运行的对话只会显示创建的存储。 没有网络。
  ```sh
  QA_F33_PLUGIN_TOKEN="qa-f33-plugin-token-$(date +%s%N)"
  export QA_F33_PLUGIN_TOKEN
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-plugins-tag/probe -- .venv/bin/python - <<'PY'
  import os
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.plugin import PluginSource

  token = os.environ["QA_F33_PLUGIN_TOKEN"]
  source = PluginSource(source=f"https://qa-f33-user:{token}@example.invalid/qa/plugin.git", ref="main")
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("plugins"), visualizer=None, delete_on_close=False,
                      plugins=[source], tags={"qaf33": "plugins"})
  info = conv.state.refresh_from_server()
  assert token not in str(info), "the plugin token is in the conversation info"
  f33.emit("plugins", cid=str(conv.id), tag=info["tags"]["plugins"])
  conv.close()
  PY
  PLUG=$(jq -r .cid "$F33/plugins.json")
  control-agent-server api GET "/api/conversations/$PLUG" --check tags.plugins eq 'https://****@example.invalid/qa/plugin.git' \
    --check tags.qaf33 eq plugins --check execution_status eq idle --save F33.conversation-plugins-tag/get
  printf %s "$QA_F33_PLUGIN_TOKEN" > "$F33/qa-f33-plugin-control.txt"
  control-agent-server state grep --env-value QA_F33_PLUGIN_TOKEN --glob 'fixtures/qa-f33/*'
  control-agent-server state grep --env-value QA_F33_PLUGIN_TOKEN --glob 'server/**/*' --expect-none
  control-agent-server state grep --env-value QA_F33_PLUGIN_TOKEN --glob 'home/**/*' --expect-none
  ```
  工厂添加了一个 `plugins` 在叫号人标签旁边添加标签， 用户和 token 被取代了 `****`, and the token 在服务器写入的任何文件中都没有（控制文件显示搜索找到了它）。 请求本身携带了掩码 URL 太 `PluginSource` masks `source` 在每次导出时，所以需要内联的源凭据无法通过服务器获取（见陷阱）。
- **确认或拒绝(`F33.conversation-confirmation`)。**
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-confirmation/probe -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.security.confirmation_policy import AlwaysConfirm

  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("confirm"), visualizer=None, delete_on_close=False)
  conv.set_confirmation_policy(AlwaysConfirm())
  conv.send_message("Run this exact shell command: printf no > qa-f33-confirm.txt")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "waiting_for_confirmation", conv.state.execution_status
  conv.reject_pending_actions("qa-f33 rejected")
  f33.emit("confirm", cid=str(conv.id))
  conv.close()
  PY
  CONF=$(jq -r .cid "$F33/confirm.json")
  control-agent-server api GET "/api/conversations/$CONF" --check confirmation_policy.kind eq AlwaysConfirm \
    --check execution_status eq idle --until-ok 30 --save F33.conversation-confirmation/get
  control-agent-server conversation events "$CONF" --kinds UserRejectObservation --contains 'qa-f33 rejected' --expect-count 1 \
    --save F33.conversation-confirmation/reject
  control-agent-server conversation events "$CONF" --kinds ObservationEvent --expect-count 0
  test ! -e "$F33/confirm/qa-f33-confirm.txt"
  ```
  `run()` 返回到 `waiting_for_confirmation`，且操作未决； 拒绝记录及其原因，不执行任何操作，对话是`idle`。
- **暂停阻塞运行 (`F33.conversation-pause`)。** `run()` a 线程中的块； 一旦智能体的第一个动作到达，主线程就会暂停。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-pause/probe -- .venv/bin/python - <<'PY'
  import threading
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ActionEvent

  acted = threading.Event()
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("pause"), visualizer=None, delete_on_close=False,
                      callbacks=[lambda e: isinstance(e, ActionEvent) and acted.set()])
  conv.send_message("Run this exact shell command: sleep 8; printf done > qa-f33-pause.txt")
  runner = threading.Thread(target=conv.run, kwargs={"timeout": 300})
  runner.start()
  assert acted.wait(180), "no ActionEvent"
  conv.pause()
  runner.join(120)
  assert not runner.is_alive(), "run() did not return after pause()"
  paused = conv.state.execution_status.value
  assert paused == "paused", paused
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("pause", cid=str(conv.id), paused=paused)
  conv.close()
  PY
  PAUSED=$(jq -r .cid "$F33/pause.json")
  test "$(cat "$F33/pause/qa-f33-pause.txt")" = done
  control-agent-server conversation events "$PAUSED" --kinds PauseEvent --expect-count 1 --save F33.conversation-pause/pause-event
  control-agent-server conversation events "$PAUSED" --key execution_status --contains paused --expect-min 1
  control-agent-server api GET "/api/conversations/$PAUSED" --check execution_status eq finished --save F33.conversation-pause/get
  ```
  命令在飞行中完成（文件存在），`run()` 返回
  `paused`，服务器已持久化一`PauseEvent`和一`paused`状态，第二`run()`完成。
- **中断阻塞运行 (`F33.conversation-interrupt`)。** 智能体的模型是`HANG_STUB`，其第一次完成挂起300秒； 一旦存根记录了该请求，main 线程就会中断。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-interrupt/probe -- .venv/bin/python - <<'PY'
  import os
  import threading
  import time
  import f33
  from openhands.sdk import Conversation

  stub = f33.agent(model="openai/qa-stub", base_url=os.environ["HANG_STUB"] + "/v1", api_key="qa-stub", num_retries=0)
  conv = Conversation(agent=stub, workspace=f33.workspace("interrupt"), visualizer=None, delete_on_close=False)
  conv.set_title("qa-f33 interrupt")
  conv.send_message("qa-f33 interrupt me")
  errors = []


  def run():
      try:
          conv.run(timeout=300)
      except Exception as e:  # recorded, asserted below
          errors.append(repr(e))


  runner = threading.Thread(target=run)
  runner.start()
  deadline = time.monotonic() + 60
  while not open(os.environ["HANG_LOG"]).read().strip():
      assert time.monotonic() < deadline, "the model call never started"
      time.sleep(0.2)
  t0 = time.monotonic()
  conv.interrupt()
  runner.join(60)
  returned = time.monotonic() - t0
  assert not runner.is_alive(), "run() did not return after interrupt()"
  assert not errors, errors
  interrupted = conv.state.execution_status.value
  assert interrupted == "paused" and returned < 15, (interrupted, returned)
  conv.run(timeout=120)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("interrupt", cid=str(conv.id), returned=round(returned, 1), interrupted=interrupted)
  conv.close()
  PY
  INT=$(jq -r .cid "$F33/interrupt.json")
  control-agent-server conversation events "$INT" --kinds InterruptEvent --expect-count 1 --save F33.conversation-interrupt/interrupt-event
  control-agent-server conversation events "$INT" --kinds PauseEvent --expect-count 0
  control-agent-server conversation events "$INT" --key execution_status --contains paused --expect-min 1
  control-agent-server api GET "/api/conversations/$INT" --check execution_status eq finished --save F33.conversation-interrupt/get
  control-agent-server sink read --name qa-f33-hang --path /v1/chat/completions --expect-min 2 --expect-max 2
  ```
  `interrupt()` 取消挂起模型调用：阻塞 `run()` 在 `paused` 处在一两秒内返回，而不引发； 服务器记录了一个`InterruptEvent`（没有`PauseEvent`），第二个`run()`发送存根的下一个完成（`finish`）并在`finished`处返回。 存根准确地看到了两个智能体调用（没有标题请求采取任何步骤）。
- **超时，然后再次等待 (`F33.conversation-run-timeout`)。** 智能体的命令比 `run(timeout=3)` 的寿命更长； 第二个 `run()` 等待相同的运行。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-run-timeout/probe -- .venv/bin/python - <<'PY'
  import time
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.conversation.exceptions import ConversationRunError

  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("timeout"), visualizer=None, delete_on_close=False)
  conv.send_message("Run this exact shell command: sleep 15; printf late > qa-f33-timeout.txt")
  t0 = time.monotonic()
  try:
      conv.run(timeout=3)
      raise AssertionError("run() returned before its timeout")
  except ConversationRunError as e:
      assert isinstance(e.original_exception, TimeoutError), repr(e.original_exception)
  waited = time.monotonic() - t0
  assert 3 <= waited < 10, waited
  status = conv.state.refresh_from_server()["execution_status"]
  assert status == "running", status
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("timeout", cid=str(conv.id), waited=waited, status_after_timeout=status)
  conv.close()
  PY
  TOUT=$(jq -r .cid "$F33/timeout.json")
  test "$(cat "$F33/timeout/qa-f33-timeout.txt")" = late
  control-agent-server api GET "/api/conversations/$TOUT" --check execution_status eq finished --save F33.conversation-run-timeout/get
  control-agent-server api GET "/api/conversations/$TOUT/events/search" --query source=user --check items len-eq 1
  ```
  第一个`run()`在3到10秒后出现，而服务器仍然报告
  `running`; 第二个 `run()` 发布 `/run`，得到 409（已在运行），继续等待并在 `finished` 返回； 15 s 命令写入的文件存在，并且对话有其一条用户消息。
- **在长跑期间加入跑步工具调用 (`F33.conversation-run-join-long-tool`)。** The same join as above, but the 智能体's command runs 45 s. 运行循环保存整个对话的状态锁工具调用（请参阅
  `F05.pause-tool-step`), and the SDK 给运行触发器设置 30 秒 HTTP  超时 (`remote_conversation.py`, `run()`). 服务器的 `/run` 在读取该状态之前，它会检查其活运行任务锁因此，它立即返回 409，并且第二个 `run()` 它加入了运行，而不是抛出
  `ConversationRunError` 包装 `ReadTimeout`。 智能体的模型为
  `LONG_STUB`，它要求使用 90 年代的工具进行 `terminal` 调用
  超时：真实模型选择自己的`timeout`，并且没有一个
  终端工具在 30 秒的静默后返回，这与 SDK 自己的 30 秒赛跑。 探测器记录第二个 `run()` 如何结束，并断言它在 `finished` 处等待并返回。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-run-join-long-tool/probe -- .venv/bin/python - <<'PY'
  import os
  import threading
  import time
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.conversation.exceptions import ConversationRunError
  from openhands.sdk.event import ActionEvent

  acted = threading.Event()
  stub = f33.agent(model="openai/qa-stub", base_url=os.environ["LONG_STUB"] + "/v1", api_key="qa-stub", num_retries=0)
  conv = Conversation(agent=stub, workspace=f33.workspace("longtool"), visualizer=None, delete_on_close=False,
                      callbacks=[lambda e: isinstance(e, ActionEvent) and e.tool_name == "terminal" and acted.set()])
  conv.set_title("qa-f33 long tool")
  conv.send_message("qa-f33 long tool call")
  conv.run(blocking=False)
  assert acted.wait(60), "no terminal ActionEvent"
  t0 = time.monotonic()
  try:
      conv.run(timeout=300)
      error = None
  except ConversationRunError as e:
      error = repr(e.original_exception)
  status = conv.state.execution_status.value
  f33.emit("longtool", cid=str(conv.id), waited=round(time.monotonic() - t0, 1), error=error, status=status,
           joined=error is None and status == "finished")
  conv.close()
  PY
  LONG=$(jq -r .cid "$F33/longtool.json")
  control-agent-server conversation wait "$LONG" --until finished --timeout 120
  test "$(cat "$F33/longtool/qa-f33-long.txt")" = late
  control-agent-server conversation events "$LONG" --kinds ActionEvent --contains '"timeout": 90.0' --expect-count 1
  control-agent-server api GET "/api/conversations/$LONG" --check execution_status eq finished --save F33.conversation-run-join-long-tool/get
  control-agent-server assert --json "$F33/longtool.json" --check joined eq true
  ```
  `run(blocking=False)`立即返回； 一旦 45 s 命令运行，阻塞 `run()` 就会等待它（大约 45 s，没有错误）并在
  `finished`; 文件出现并且对话结束。
- **卡住了智能体 (`F33.conversation-stuck`)。** 智能体的模型为
  `LOOP_STUB`，它重复相同的 `think` 调用，因此服务器的卡住检测器停止运行。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-stuck/probe -- .venv/bin/python - <<'PY'
  import os
  import time
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.conversation.exceptions import ConversationRunError

  stub = f33.agent(model="openai/qa-stub", base_url=os.environ["LOOP_STUB"] + "/v1", api_key="qa-stub", num_retries=0)
  conv = Conversation(agent=stub, workspace=f33.workspace("stuck"), visualizer=None, delete_on_close=False)
  conv.set_title("qa-f33 stuck")
  conv.send_message("qa-f33 loop forever")
  t0 = time.monotonic()
  try:
      conv.run(timeout=120)
      raise AssertionError("run() returned although the agent is stuck")
  except ConversationRunError as e:
      detail = str(e.original_exception)
      assert e.conversation_error is None and "stuck" in detail, (detail, e.conversation_error)
  waited = time.monotonic() - t0
  assert waited < 30, waited
  f33.emit("stuck", cid=str(conv.id), waited=round(waited, 1), detail=detail)
  conv.close()
  PY
  STUCK=$(jq -r .cid "$F33/stuck.json")
  control-agent-server api GET "/api/conversations/$STUCK" --check execution_status eq stuck --save F33.conversation-stuck/get
  control-agent-server conversation events "$STUCK" --kinds ActionEvent --contains qa-f33 --expect-min 3
  control-agent-server conversation events "$STUCK" --kinds ConversationErrorEvent --expect-count 0
  ```
  检测器在进行几组相同的`think`调用后停止循环。 `run()` 会在几秒钟内引发 `ConversationRunError` ("远程对话卡住了")，没有 `conversation_error`（没有 `ConversationErrorEvent` 记录在卡住的运行中），服务器报告 `stuck`。
- **机密为智能体 (`F33.conversation-secrets`)。**新鲜的纯值和服务器机密`QA_F33_LOOKUP`引用； 智能体门店只存储哈希前缀，因为模型拒绝回显机密。
  ```sh
  QA_F33_TOKEN="qa-f33-$(date +%s%N)"
  export QA_F33_TOKEN
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-secrets/probe -- .venv/bin/python - <<'PY'
  import os
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ObservationEvent

  value = os.environ["QA_F33_TOKEN"]
  seen = []
  ws = f33.workspace("secret")
  conv = Conversation(agent=f33.agent(), workspace=ws, visualizer=None, delete_on_close=False,
                      callbacks=[lambda e: isinstance(e, ObservationEvent) and seen.append(e.model_dump_json())])
  conv.update_secrets({"QA_F33_TOKEN": value, **ws.get_secrets(names=["QA_F33_LOOKUP"])})
  conv.send_message('Run this exact shell command, which stores only hash prefixes, then stop: '
                    'for v in "$QA_F33_TOKEN" "$QA_F33_LOOKUP"; do printf %s "$v" | sha256sum | cut -c1-16; done > qa-f33-secret.sha')
  conv.run(timeout=300)
  assert seen and not any(value in o or "qa-f33-lookup-value" in o for o in seen), seen
  f33.emit("secret", cid=str(conv.id), observations=len(seen))
  conv.close()
  PY
  SEC=$(jq -r .cid "$F33/secret.json")
  { printf %s "$QA_F33_TOKEN" | sha256sum | cut -c1-16; printf %s qa-f33-lookup-value | sha256sum | cut -c1-16; } > "$F33/qa-f33-expected.sha"
  cmp "$F33/qa-f33-expected.sha" "$F33/secret/qa-f33-secret.sha"
  control-agent-server conversation events "$SEC" --kinds ObservationEvent --expect-min 1 --save F33.conversation-secrets/observations
  printf %s "$QA_F33_TOKEN" > "$F33/qa-f33-grep-control.txt"
  control-agent-server state grep --env-value QA_F33_TOKEN --glob 'fixtures/qa-f33/*'
  control-agent-server state grep --env-value QA_F33_TOKEN --glob 'server/workspace/conversations/**/*' --expect-none
  env QA_F33_SESSION_KEY="$(cat "$AGENT_SERVER_VERIFY_RUN/private/session_api_key")" \
    control-agent-server state grep --env-value QA_F33_SESSION_KEY --glob 'server/workspace/conversations/**/*' --expect-none
  control-agent-server api DELETE /api/settings/secrets/QA_F33_LOOKUP --expect 200
  ```
  两个哈希匹配，所以智能体的壳看到了这两个值。 没有观测结果的值。 grep找到了控制文件中的值（正控制），但也没有找到普通值或会话密钥
  `LookupSecret` 作为标头以明文形式发送到磁盘上的对话存储中。 服务器机密随后被删除。
- **提供者错误表面（`F33.conversation-run-error`）。**存根回答 401，就像提供者拒绝密钥一样。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-run-error/probe -- .venv/bin/python - <<'PY'
  import os
  import time
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.conversation.exceptions import ConversationRunError

  conv = Conversation(agent=f33.agent(model="openai/qa-stub", base_url=os.environ["STUB"] + "/v1", api_key="qa-stub", num_retries=0),
                      workspace=f33.workspace("error"), visualizer=None, delete_on_close=False)
  conv.send_message("hello")
  t0 = time.monotonic()
  try:
      conv.run(timeout=120)
      raise AssertionError("run() returned although the provider failed")
  except ConversationRunError as e:
      assert e.conversation_error is not None and e.conversation_error.code == "LLMAuthenticationError", e
  assert time.monotonic() - t0 < 60, time.monotonic() - t0
  assert conv.state.execution_status.value == "error"
  f33.emit("error", cid=str(conv.id))
  conv.close()
  PY
  ERR=$(jq -r .cid "$F33/error.json")
  control-agent-server api GET "/api/conversations/$ERR" --check execution_status eq error --save F33.conversation-run-error/get
  control-agent-server conversation events "$ERR" --kinds ConversationErrorEvent --contains LLMAuthenticationError --expect-min 1
  control-agent-server sink read --name qa-f33-stub --path /v1/chat/completions --expect-min 1
  ```
  `run()` 在几秒钟内引发服务器记录的结构化错误； 存根看到服务器的模型请求。
- **无事件套接字 (`F33.ws-unavailable`)。**探针通过 `f33.Proxy(block_ws=True)`: REST 到达服务器，每个事件套接字升级都会被拒绝并返回 403。 首先使用默认设置和 3 秒准备时间超时，然后使用 `OPENHANDS_REMOTE_WS_READY_REQUIRED=false`； 观察者线程直接轮询服务器，以根据服务器报告 `finished` 的时刻返回时间 `run()`。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.ws-unavailable/probe -- .venv/bin/python - <<'PY'
  import os
  import threading
  import time
  import httpx
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.conversation.exceptions import WebSocketConnectionError

  proxy = f33.Proxy(block_ws=True)
  ws = f33.workspace("nows", host=proxy.url)
  assert ws.alive, "REST does not pass the proxy"
  os.environ["OPENHANDS_REMOTE_WS_READY_TIMEOUT"] = "3"
  t0 = time.monotonic()
  try:
      Conversation(agent=f33.agent(), workspace=ws, visualizer=None, delete_on_close=False)
      raise AssertionError("a conversation connected without its events socket")
  except WebSocketConnectionError as e:
      refused_cid, ready_wait = str(e.conversation_id), time.monotonic() - t0
  assert 3 <= ready_wait < 10 and proxy.refused >= 1, (ready_wait, proxy.refused)
  os.environ["OPENHANDS_REMOTE_WS_READY_REQUIRED"] = "false"
  seen = []
  conv = Conversation(agent=f33.agent(), workspace=ws, visualizer=None, delete_on_close=False, callbacks=[seen.append])
  conv.set_title("qa-f33 no socket")
  conv.send_message("Reply with one word: ready")
  finished_at = []


  def watch():
      with httpx.Client(base_url=f33.URL, headers={"X-Session-API-Key": f33.KEY}) as http:
          while not finished_at:
              if http.get(f"/api/conversations/{conv.id}").json()["execution_status"] == "finished":
                  finished_at.append(time.monotonic())
              time.sleep(0.25)


  threading.Thread(target=watch, daemon=True).start()
  conv.run(timeout=300)
  lag = time.monotonic() - finished_at[0]
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  assert 29 <= lag <= 40, lag
  assert not seen and not proxy.sockets, (len(seen), proxy.sockets)
  f33.emit("nows", refused_cid=refused_cid, ready_wait=round(ready_wait, 1), cid=str(conv.id), lag=round(lag, 1),
           local=f33.kinds(conv.state.events))
  conv.close()
  PY
  NOWS=$(jq -r .cid "$F33/nows.json")
  control-agent-server api GET "/api/conversations/$(jq -r .refused_cid "$F33/nows.json")" --check execution_status eq idle \
    --save F33.ws-unavailable/left-behind
  control-agent-server api GET "/api/conversations/$NOWS" --check execution_status eq finished --save F33.ws-unavailable/get
  for K in SystemPromptEvent MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$NOWS" --kinds $K --expect-count "$(jq ".local.$K // 0" "$F33/nows.json")"
  done
  ```
  有了套接字，`Conversation(...)` 将会提升
  `WebSocketConnectionError` 3 秒后超时，但它首先创建的对话仍保留在服务器上 (`idle`)。 与
  `OPENHANDS_REMOTE_WS_READY_REQUIRED=false` 它继续没有
  套接字：回调什么也没得到，`run()`等待运行后套接字
  快照永远不会出现，然后在服务器报告 `finished`（硬回退方案）、协调和 30 秒后接受 REST 状态
  `state.events` 逐一匹配服务器。
- **跨重启的实时对话`F33.conversation-reconnect`).** 探针在后台运行，发送信号 `reconnect-ready`，并在 shell 重新启动服务器并创建后继续 `reconnect-go`.
  ```sh
  rm -f "$F33/reconnect-ready" "$F33/reconnect-go"
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-reconnect/probe -- .venv/bin/python - > "$F33/reconnect-exec.json" <<'PY' &
  import os
  import time
  from collections import Counter
  import f33
  from openhands.sdk import Conversation

  seen = Counter()
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("reconnect"), visualizer=None, delete_on_close=False,
                      callbacks=[lambda e: seen.update([type(e).__name__])])
  before = seen["ConversationStateUpdateEvent"]
  open(os.path.join(f33.DIR, "reconnect-ready"), "w").write(str(conv.id))
  deadline = time.monotonic() + 300
  while not os.path.exists(os.path.join(f33.DIR, "reconnect-go")):
      assert time.monotonic() < deadline, "no reconnect-go"
      time.sleep(0.2)
  conv.send_message("Run this exact shell command: printf back > qa-f33-reconnect.txt")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  assert seen["ConversationStateUpdateEvent"] > before, seen
  f33.emit("reconnect", cid=str(conv.id), local=f33.kinds(conv.state.events), seen=dict(seen))
  conv.close()
  PY
  PROBE=$!
  for i in $(seq 240); do test -e "$F33/reconnect-ready" && break; sleep 0.5; done
  test -e "$F33/reconnect-ready"
  control-agent-server restart
  touch "$F33/reconnect-go"
  wait "$PROBE"
  RECON=$(jq -r .cid "$F33/reconnect.json")
  test "$(cat "$F33/reconnect/qa-f33-reconnect.txt")" = back
  for K in SystemPromptEvent MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$RECON" --kinds $K --expect-count "$(jq ".local.$K // 0" "$F33/reconnect.json")"
  done
  control-agent-server api GET "/api/conversations/$RECON" --check execution_status eq finished --save F33.conversation-reconnect/get
  ```
  在重启之前创建的同一个`RemoteConversation`对象，会运行`finished`消息。 它的套接字再次交付了状态更新，`run()` 后，它的 `state.events` 与服务器类型一一匹配。
- **回调重新连接后 (`F33.conversation-reconnect-callbacks`)。** SDK 的事件套接字重试进行退避（1 秒加倍到 30 秒）并重新订阅，无需 `resend_mode`； 重新连接时会协调
  `state.events` 越过 REST，并按顺序将回调未见过的事件传递给它们，每个事件一次。 探针通过`f33.Proxy()`与服务器通信，因此故障是精确的，而不是与重启时间赛跑：连接时发送的第一个消息到达回调（控制）。 然后代理丢弃了套接字并拒绝重连，客户端看起来在重试，发送了第二条消息并存储在没有套接字打开的状态下，代理让套接字重新开放。 没有模型调用。
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-reconnect-callbacks/probe -- .venv/bin/python - <<'PY'
  import time
  import f33
  from openhands.sdk import Conversation
  from openhands.sdk.event import ConversationStateUpdateEvent, MessageEvent

  proxy = f33.Proxy()
  seen = []
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("gap", host=proxy.url), visualizer=None,
                      delete_on_close=False, callbacks=[seen.append])


  def updates():
      return sum(isinstance(e, ConversationStateUpdateEvent) for e in seen)


  def users():
      return [e for e in conv.state.events if isinstance(e, MessageEvent) and e.source == "user"]


  def wait(condition, seconds, why):
      deadline = time.monotonic() + seconds
      while not condition():
          assert time.monotonic() < deadline, why
          time.sleep(0.1)


  assert len(proxy.sockets) == 1, proxy.sockets
  conv.send_message("qa-f33 sent while connected")
  wait(lambda: any(isinstance(e, MessageEvent) and e.source == "user" for e in seen), 15, "the control message never reached the callback")
  proxy.block_ws = True
  proxy.drop_sockets()
  wait(lambda: proxy.refused >= 1, 30, "the client never tried to reconnect")
  before = updates()
  conv.send_message("qa-f33 sent while the socket reconnects")
  assert not proxy.sockets and updates() == before, (proxy.sockets, updates(), before)
  proxy.block_ws = False
  wait(lambda: updates() > before, 60, "the socket never came back")
  assert len(users()) == 2, users()
  missed = users()[1].id
  deadline = time.monotonic() + 15
  while missed not in {e.id for e in seen} and time.monotonic() < deadline:
      time.sleep(0.2)
  f33.emit("gap", cid=str(conv.id), message=missed, refused=proxy.refused, callback_got_message=missed in {e.id for e in seen})
  conv.close()
  PY
  GAP=$(jq -r .cid "$F33/gap.json")
  control-agent-server api GET "/api/conversations/$GAP/events/search" --query source=user --check items len-eq 2 \
    --check items.1.id eq "$(jq -r .message "$F33/gap.json")" --save F33.conversation-reconnect-callbacks/server-message
  control-agent-server assert --json "$F33/gap.json" --check callback_got_message eq true
  ```
  服务器存储了这两个消息，`state.events` 之后又存储了这两个。 回调先活了下来，`true` 在`callback_got_message`的套接字恢复后才活了下来。 重启服务器填补了同样的空隙，`F33.conversation-reconnect`的客户端也是这样做的。
- **重新启动后重新连接并继续 (`F33.conversation-restart`)。**

  需要：`F33.conversation-run`
  ```sh
  control-agent-server restart
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$CID" --save F33.conversation-restart/probe -- .venv/bin/python - <<'PY'
  import json
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation

  before = json.load(open(os.path.join(f33.DIR, "run.json")))["local"]
  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("run"), conversation_id=uuid.UUID(os.environ["CID"]),
                      visualizer=None, delete_on_close=False)
  assert f33.kinds(conv.state.events) == before, (f33.kinds(conv.state.events), before)
  assert conv.state.execution_status.value == "finished"
  conv.send_message("Create the file qa-f33-after-restart.txt in the current directory containing exactly: again")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("restart", local=f33.kinds(conv.state.events))
  conv.close()
  PY
  test "$(cat "$F33/run/qa-f33-after-restart.txt")" = again
  control-agent-server api GET "/api/conversations/$CID" --check execution_status eq finished --save F33.conversation-restart/get
  test "$(jq .local.MessageEvent "$F33/restart.json")" -gt "$(jq .local.MessageEvent "$F33/run.json")"
  for K in MessageEvent ActionEvent ObservationEvent; do
    control-agent-server conversation events "$CID" --kinds $K --expect-count "$(jq ".local.$K" "$F33/restart.json")"
  done
  ```
  重启后的历史读取与在重启前记录的一样，继续的对话会结束并写入第二个文件。
- **一个自定义工具模块 (`F33.custom-tool-module`).** 从 SDK 所见的自定义工具部署文档：该模块 `qa_f33_tool` 注册 `qa_f33_echo`，服务器重启了
  `OH_EXTRA_PYTHON_PATH` 命名模块的目录，并且探测器导入相同的模块，因此 SDK 在不被告知的情况下将其发送到 `tool_module_qualnames` 中。 该工具在工作区中记录它是否在Agent Server的进程中运行。 第二个模块 `qa_f33_ghost` 位于只有客户端可以导入它的位置。
  ```sh
  mkdir -p "$F33/tools" "$F33/clientonly"
  cat > "$F33/tools/qa_f33_tool.py" <<'EOF'
  """qa-f33 custom tool: records where it ran in qa-f33-tool.txt in the workspace."""
  import os
  import sys

  from pydantic import Field

  from openhands.sdk import Action, Observation, ToolDefinition
  from openhands.sdk.tool import ToolExecutor, register_tool


  class QaF33EchoAction(Action):
      message: str = Field(description="Text to record")


  class QaF33EchoObservation(Observation):
      pass


  class QaF33EchoExecutor(ToolExecutor):
      def __init__(self, working_dir):
          self.working_dir = working_dir

      def __call__(self, action, conversation=None):
          where = "agent-server" if "openhands.agent_server" in sys.modules else "client"
          with open(os.path.join(self.working_dir, "qa-f33-tool.txt"), "w") as f:
              f.write(where)
          return QaF33EchoObservation.from_text(f"qa-f33 recorded {action.message!r} on the {where}")


  class QaF33EchoTool(ToolDefinition[QaF33EchoAction, QaF33EchoObservation]):
      name = "qa_f33_echo"

      @classmethod
      def create(cls, conv_state, **params):
          return [cls(description="Record a message (qa-f33 test tool).", action_type=QaF33EchoAction,
                      observation_type=QaF33EchoObservation, executor=QaF33EchoExecutor(conv_state.workspace.working_dir))]


  register_tool("qa_f33_echo", QaF33EchoTool)
  EOF
  sed -e 's/qa_f33_echo/qa_f33_ghost/g; s/QaF33Echo/QaF33Ghost/g' "$F33/tools/qa_f33_tool.py" > "$F33/clientonly/qa_f33_ghost.py"
  X0=$(control-agent-server logs --grep 'Extended sys.path with 1 directory' | jq -r .total_matching)
  control-agent-server restart --env OH_EXTRA_PYTHON_PATH="$F33/tools"
  control-agent-server logs --grep 'Extended sys.path with 1 directory' --expect-min "$((X0 + 1))"
  control-agent-server exec --env PYTHONPATH="$F33:$F33/tools" --save F33.custom-tool-module/probe -- .venv/bin/python - <<'PY'
  import f33
  import qa_f33_tool  # noqa: F401  registers qa_f33_echo in this process
  from openhands.sdk import Conversation, Tool
  from openhands.sdk.event import ObservationEvent
  from openhands.sdk.tool.registry import get_tool_module_qualnames

  assert get_tool_module_qualnames()["qa_f33_echo"] == "qa_f33_tool"
  agent = f33.agent()
  agent = agent.model_copy(update={"tools": [*agent.tools, Tool(name="qa_f33_echo")]})
  conv = Conversation(agent=agent, workspace=f33.workspace("customtool"), visualizer=None, delete_on_close=False)
  conv.send_message("Call the qa_f33_echo tool once with the message qa-f33-custom, then finish.")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  ran = [e for e in conv.state.events if isinstance(e, ObservationEvent) and e.tool_name == "qa_f33_echo"]
  assert ran and all("on the agent-server" in e.observation.text for e in ran), ran
  f33.emit("customtool", cid=str(conv.id), calls=len(ran))
  conv.close()
  PY
  TOOLCID=$(jq -r .cid "$F33/customtool.json")
  test "$(cat "$F33/customtool/qa-f33-tool.txt")" = agent-server
  control-agent-server api GET "/api/conversations/$TOOLCID" --check execution_status eq finished \
    --check tool_module_qualnames.qa_f33_echo eq qa_f33_tool --check tool_module_qualnames.terminal exists \
    --check agent.tools contains qa_f33_echo --save F33.custom-tool-module/get
  control-agent-server conversation events "$TOOLCID" --kinds ObservationEvent --contains '"kind": "QaF33EchoObservation"' \
    --expect-count "$(jq .calls "$F33/customtool.json")" --save F33.custom-tool-module/observations
  control-agent-server exec --env PYTHONPATH="$F33" --env CID="$TOOLCID" --save F33.custom-tool-module/reattach -- .venv/bin/python - <<'PY'
  import os
  import uuid
  import f33
  from openhands.sdk import Conversation, RemoteConversation

  cid = uuid.UUID(os.environ["CID"])
  errors = []
  for attach in (lambda: RemoteConversation.attach(f33.workspace("customtool"), cid, visualizer=None),
                 lambda: Conversation(agent=f33.agent(), workspace=f33.workspace("customtool"), conversation_id=cid,
                                      visualizer=None, delete_on_close=False)):
      try:
          attach().close()
          raise AssertionError("attached without the tool module")
      except ImportError as e:
          errors.append(str(e))
  assert all("'qa_f33_echo'" in e and "'qa_f33_tool'" in e for e in errors), errors
  f33.emit("customtool-reattach", errors=errors)
  PY
  W0=$(control-agent-server logs --grep 'Failed to import' | jq -r .total_matching)
  control-agent-server exec --env PYTHONPATH="$F33:$F33/tools:$F33/clientonly" --save F33.custom-tool-module/unused-ghost -- .venv/bin/python - <<'PY'
  import f33
  import qa_f33_ghost  # noqa: F401  registered here, not importable by the server
  from openhands.sdk import Conversation

  conv = Conversation(agent=f33.agent(), workspace=f33.workspace("ghostunused"), visualizer=None, delete_on_close=False)
  conv.send_message("Reply with one word: ready")
  conv.run(timeout=300)
  assert conv.state.execution_status.value == "finished", conv.state.execution_status
  f33.emit("ghostunused", cid=str(conv.id))
  conv.close()
  PY
  control-agent-server logs --grep 'Failed to import' --expect-min "$((W0 + 1))"
  control-agent-server api GET "/api/conversations/$(jq -r .cid "$F33/ghostunused.json")" --check execution_status eq finished \
    --check tool_module_qualnames.qa_f33_ghost eq qa_f33_ghost --save F33.custom-tool-module/unused-ghost-get
  control-agent-server api GET /api/tools/ --check . contains qa_f33_echo --check . not-contains qa_f33_ghost
  ```
  SDK 发送其进程中注册的所有工具，因此 `qa_f33_echo`（包含 `terminal` 和 REST）到达 `tool_module_qualnames`。 服务器导入了模块 `OH_EXTRA_PYTHON_PATH`，智能体的调用在服务器进程中运行（文件中说 `agent-server`），并返回一个
  `QaF33EchoObservation`. 没有该模块的进程无法重新附加：`attach()` 和 `Conversation(conversation_id=...)` 都引发
  `ImportError` 命名工具和模块。 服务器无法导入的客户端注册模块仅是一个登录名 `Failed to import module` 警告时智能体它不使用其工具：该对话正常运行，服务器的响应正常注册表 never lists `qa_f33_ghost`.
- **服务器无法导入的智能体工具 (`F33.custom-tool-module-unimportable`)。** 智能体现在命名为 `qa_f33_ghost`。 创建答案 422，带有
  `detail` 命名服务器无法导入的工具和模块，并且不会创建任何对话：永远无法构建智能体，因为
  `resolve_tool` 会在第一条消息上引发 `KeyError: "ToolDefinition 'qa_f33_ghost' is not registered"`。 调用者可以采取行动的客户端错误，而不是 500。

  需要：`F33.custom-tool-module`
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33:$F33/clientonly" --save F33.custom-tool-module-unimportable/probe -- .venv/bin/python - <<'PY'
  import httpx
  import f33
  import qa_f33_ghost  # noqa: F401
  from openhands.sdk import Conversation, Tool

  agent = f33.agent()
  agent = agent.model_copy(update={"tools": [*agent.tools, Tool(name="qa_f33_ghost")]})
  statuses, cid = {}, None
  try:
      conv = Conversation(agent=agent, workspace=f33.workspace("ghost"), visualizer=None, delete_on_close=False)
      statuses["create"], cid = 201, str(conv.id)
      try:
          conv.send_message("Reply with one word: ready")
          statuses["message"] = 200
      except httpx.HTTPStatusError as e:
          statuses["message"] = e.response.status_code
      conv.close()
  except httpx.HTTPStatusError as e:
      statuses["create"] = e.response.status_code
  f33.emit("ghost", cid=cid, statuses=statuses, server_errors=sum(s >= 500 for s in statuses.values()))
  PY
  control-agent-server api GET /api/tools/ --check . contains terminal --check . not-contains qa_f33_ghost
  control-agent-server assert --json "$F33/ghost.json" --check server_errors eq 0 --check statuses.create eq 422
  ```
  服务器的注册表缺乏 `qa_f33_ghost`（控制）。 探针记录
  `{"create": 422}`; 服务器日志仅包含 `Failed to import module` 警告。
- **关闭保留或删除(`F33.conversation-close`)。**
  ```sh
  control-agent-server exec --env PYTHONPATH="$F33" --save F33.conversation-close/probe -- .venv/bin/python - <<'PY'
  import f33
  from openhands.sdk import Conversation

  ws = f33.workspace("close")
  keep = Conversation(agent=f33.agent(), workspace=ws, visualizer=None, delete_on_close=False)
  gone = Conversation(agent=f33.agent(), workspace=ws, visualizer=None)
  assert (keep.delete_on_close, gone.delete_on_close) == (False, True)
  keep.close()
  gone.close()
  f33.emit("close", keep=str(keep.id), gone=str(gone.id))
  PY
  control-agent-server api GET "/api/conversations/$(jq -r .keep "$F33/close.json")" --expect 200 --save F33.conversation-close/kept
  control-agent-server api GET "/api/conversations/$(jq -r .gone "$F33/close.json")" --expect 404 --save F33.conversation-close/deleted
  ```
  对话以 `delete_on_close=False` 仍在提供结束。 工厂默认删除了另一个。

<a id="gotchas"></a>

## 陷阱

- `exec` 在 `stdout_tail` 中报告探针的标准输出，在 `evidence/<ID>/probe.json` 中报告完整的转录本； SDK 日志（并且，没有
  `visualizer=None`，标准输出上的丰富面板）有噪音，因此探针通过
  `visualizer=None`和导出的前提条件`OPENHANDS_SUPPRESS_BANNER=1`。 每个探针导入 SDK 大约需要 8 秒。
- `Conversation(...)`出厂默认为`delete_on_close=True`，
  `RemoteConversation` 类到 `False` ：一个程序调用 `close()` 会删除服务器上的内容，因此，另一个程序会重新附上的程序必须传递
  `delete_on_close=False`. `close()` 也从 `__del__` 运行，但在解释器退出时不可靠。
- `RemoteWorkspace.execute_command` 无 `cwd` 发送 `cwd`：主机 bash 服务则使用服务器进程的目录（运行的 `server/`），而不是 `working_dir`（运行时的工作区使用会话的工作区）。 `LocalWorkspace`默认为`working_dir`； 远程遗漏是故意的（`tests/sdk/workspace/remote/test_remote_workspace_mixin.py`），因此明确传递`cwd`。
- `execute_command`、`file_upload` 和 `file_download` 从未在 HTTP 上加注
  错误：它们在 stderr 中返回 exit `-1` 和 `Remote execution error: ...`，
  或 `success: false` 以及 `error` 中的 httpx 消息。 检查结果。
  `git_changes`、`git_diff`、`get_llm` 和对话方法确实提出了。
- 在命令超时上，SDK 停止轮询并返回 exit `-1`
  `Command timed out after N seconds` 和空标准输出，即使服务器记录了在其自己的超时之前打印的输出。
- `file_upload` 报告 `file_size: null`（服务器仅应答
  `{"success": true}`)，其目的地必须是绝对的（相对路径是 400），而 `git_changes`/`git_diff` 将相对路径与
  `working_dir`.
- 服务器保存字段级别的 `ConversationStateUpdateEvent`s (`execution_status`, `stats`, ...)，但连接和每次运行后发送的全状态快照已持久化
  `len(conversation.state.events)` 不是服务器的事件计数； 像食谱一样，比较状态更新以外的类型。 计数种类
  `conversation events --kinds` 或 `events/count?kind=ActionEvent`（服务器接受短名称或完整的 `<module>.<Class>` 名称，请参阅
  `F06.search-kind-short`).
- 直播 `RemoteConversation` 在服务器重启或断开连接后，它会使用指数退避（1秒加倍到30秒）重新连接事件套接字。 在它重新连接之前发出的事件 `state.events` 通过 REST 重连和之后的核对 `run()`, 重连时客户端会传递这些值回调未曾见过他们，一次又一次，按顺序`F33.conversation-reconnect-callbacks`; 客户端不使用服务器的 `resend_mode=since` replay). 事件落在空隙中的数量取决于重试时间，因此断开连接的弹出框只断开连接 `state.events`, and the 回调子弹使停机时间精确到秒 `f33.Proxy` 而不是重启（重启的窗口从“服务器就绪”到下一个） 重试从几秒到几分钟。
- `run()` 帖子 `/run` 的时间为 30 秒超时。 当智能体的工具调用正在执行时，运行循环保持会话的状态锁（`/pause` 等待它）； `/run` 从实时运行任务中回答 409，而不采用锁，因此 `run()` 加入运行，无论其当前命令的长度如何（`F33.conversation-run-join-long-tool`、`F33.conversation-run-timeout`）。
- `RemoteConversation.create(...)` 和 `initial_message` 开始在服务器上运行，无论 `initial_message.run` 说什么（参见 F04）； 使用相同的 `conversation_id` 重复请求将返回现有对话，而无需再次发送消息。
- `RemoteWorkspace(runtime_conversation_id=...).get_runtime_session_key()` 和 `release_runtime()` 调用 `POST .../runtime/credentials` 和
  `DELETE .../runtime`，仅 Docker 会话运行时提供服务； 本地服务器回答 404 和 405，并且 SDK 对两者都加注（它仅将 `release_runtime` 中的 404 视为已发布）。
- `RemoteConversation.attach()`从服务器重建智能体，其LLM密钥返回已脱敏：用它来读取或引导，并使用
  `Conversation(agent=<your agent>, conversation_id=...)` 当客户端必须调用模型本身时（`generate_title()` 与智能体的 LLM 一起在客户端上运行，除非给出另一个）。
- `run()` 仅将服务器的运行后全状态套接字快照视为完成； 如果没有它，它会在 30 秒后接受 REST 确认的终端状态，因此损坏的套接字会使每次运行至少持续 30 秒 (`F33.ws-unavailable`)。 `ERROR` 和 `STUCK` 立即加注 `ConversationRunError` (`F33.conversation-run-error`, `F33.conversation-stuck`)。
- 由于需要套接字（默认），`Conversation(...)` 在等待套接字之前创建服务器会话，因此
  `WebSocketConnectionError` 留下 `idle` 条对话； 它的 id 位于异常 (`conversation_id`) 上。
- 对于没有标题的对话的第一条用户消息，服务器的自动标题在智能体自己的 LLM 上运行（除非创建名称 `title_llm_profile`）。 对于 `llm-stub` 智能体，它需要一个脚本化的步骤，与智能体的第一次调用进行竞争； 使用 `log_completions` 它会再记录一次调用，通常是在 `run()` 返回之后； 其成本落在智能体的范围内
  `usage_to_metrics`. `RemoteConversation` 不发送 `autotitle` 字段，因此在第一条消息之前调用 `set_title()`，以保留存根脚本和智能体自己的调用计数。
- `tool_module_qualnames` 是在创建时在客户端进程中注册的每个工具，不仅仅是智能体的工具，并且稍后附加导入所有
  它们：无法导入这些模块之一的程序无法附加，
  即使智能体从未使用过该工具（`ImportError` 列出了第一个缺失的工具）。 服务器无法导入的客户端注册模块只是一个警告，直到智能体为其工具命名（然后创建是 422，
  `F33.custom-tool-module-unimportable`). `OH_EXTRA_PYTHON_PATH`仅扩展服务器的`sys.path`； F27 驱动服务器端（`F27.custom-tool-modules` 和 `F27.custom-tool-missing-on-resume` 表示消失的模块）。
- 客户端工具没有服务器执行器：服务器对每个调用都立即返回 `Tool call dispatched to client.`，而智能体不等待客户端的处理器。 客户端只能通过回调了解该调用，因此处理程序会错过在套接字关闭时调用的客户端工具（上面的重新连接间隙）。
- 对于 `stream=True` LLM，事件套接字还携带
  `StreamingDeltaEvent`帧：回调获取它们，服务器存储None，并且它们远离`state.events`（`F33.conversation-streaming-state`）；
  `token_callbacks` 传递到 `Conversation(...)` 接收相同的增量 (`F33.conversation-token-callbacks`)。
- 远程智能体上的 `log_completions=True` 将日志文件写入客户端（相对文件夹根据客户端的工作目录进行解析），
  from `LLMCompletionLogEvent`s that the server also stores and serves like
  任何事件。
- `fork()` 返回使用默认可视化工具构建的 `RemoteConversation`，而不返回回调，无论使用什么源：丰富的面板都会转到标准输出以获取 fork 的事件，除非程序将其自己的 fork 传递给更安静的程序
  `Conversation(conversation_id=...)`.
- `PluginSource` 在每次导出时，包括创建请求，都会覆盖 URL 凭据，因此服务器接收到 `https://****@host/...`。需要凭据的插件无法从 token（仅客户端 `source` 属性保持它）远程服务器获取。
- 模型拒绝将机密打印或复制到文件中； 使用在 shell 中计算的哈希前缀来证明机密交付，如机密项目符号所做的那样。
