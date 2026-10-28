<a id="hooks-sub-agents-and-tool-catalogs"></a>

# 挂钩、子智能体和工具目录

只读发现在配置或启动智能体之前路由客户端呼叫。 `POST /api/hooks` 读取工作区的 `.openhands/hooks.json` 并将其作为规范化的 `HookConfig`（或 `null`）返回，然后客户端在创建对话时将其作为 `hook_config` 传递； 只有这样钩子才会运行并发出 `HookExecutionEvent` 。 `POST /api/sub-agents` 列出了委托智能体和工作区提供的内容（项目、用户和内置 Markdown 定义，按名称优先）。 `GET /api/tools/` 列出了全局工具注册表中的名称，`GET /api/tools/catalog` 列出了客户端在配置智能体时可提供的工具，这些工具具有可选性、易用性和默认集成员资格。 None 其中改变状态。 该系列还涵盖了客户端通过创建请求注册的内容以及服务器的启动
flags：阻止工具调用或提示词的钩子，客户端工具
(`client_tools`) 客户执行的呼叫，转发子智能体定义(`agent_definitions`)，以及定制Python工具模块(`tool_module_qualnames`、`OH_EXTRA_PYTHON_PATH`、`--import-modules`)，以及内部`start_child_conversation`工具，当主机附加时。

资料来源：`openhands-agent-server/openhands/agent_server/tool_router.py`、`openhands-agent-server/openhands/agent_server/hooks_router.py`、`openhands-agent-server/openhands/agent_server/hooks_service.py`、`openhands-agent-server/openhands/agent_server/sub_agents_router.py`、`openhands-agent-server/openhands/agent_server/launch.py`、`openhands-agent-server/openhands/agent_server/__main__.py`、`openhands-sdk/openhands/sdk/tool/registry.py`、`openhands-sdk/openhands/sdk/tool/client_tool.py`、`openhands-sdk/openhands/sdk/hooks/`、`openhands-sdk/openhands/sdk/subagent/`、`openhands-tools/openhands/tools/preset/`、`openhands-tools/openhands/tools/task/`、`openhands-tools/openhands/tools/child_conversation/`、`openhands-tools/openhands/tools/browser_use/`、`clients/typescript/src/client/tool-client.ts`、`clients/typescript/src/client/hooks-client.ts`、`clients/typescript/src/client/sub-agents-client.ts`

需求：`llm`、`git`、`tmux`、`chromium`

路线：`GET /api/tools/`、`GET /api/tools/catalog`、`POST /api/sub-agents`、
`POST /api/hooks`

<a id="sub-features"></a>

## 子功能

- `F27.auth`：每条路由都回答401，没有会话密钥或会话密钥错误； `/api/tools` 的斜杠重定向在身份验证之前应答，但其目标仍然需要密钥。
- `F27.validation`：`POST /api/hooks` 和 `POST /api/sub-agents` 上缺少正文或输入错误的字段为 422。
- `F27.tools-list`: `GET /api/tools/` 列出注册的工具名称，包括默认工具 `browser_tool_set`, 任务和规划工具及其注册   `ClassifyAndSwitchLLMTool`).
- `F27.tools-redirect`：`GET /api/tools`（无尾部斜杠）回答 307 到 `/api/tools/`，`/api/tools/catalog/` 回答 307 到 `/api/tools/catalog`； CLI 不遵循重定向。
- `F27.catalog`: `GET /api/tools/catalog` 描述每个提供的工具 `user_selectable`, `usable`, `description` 和 `in_default_set`默认工具可选，默认设置项不可选，内置工具则以工具名显示。
- `F27.child-conversation-tool`：注册的内部工具可用，不可选择，不在默认设置范围内； 显式附加它可以让真实模型启动一个观测结果、父链接和共享工作区一致的子模型。
- `F27.hooks-project`：项目测试夹具的 `hooks.json`（带有 PascalCase 键的旧 `{"hooks": {...}}` 包装器）返回为 snake_case `HookConfig`，并填充了默认值。
- `F27.hooks-formats`: a snake_case  `hooks.json` 保留其匹配器超时和 `async` flag, a PascalCase 旁边的那个键是规范化后的 `prompt` hook 保持其提示词，一个匹配器缺失就会 `*`.
- `F27.hooks-absent`无 `project_dir`, 错拼的字段 (`projectDir`, 一个缺失的目录，一个没有文件的目录 `.openhands/hooks.json`, a `hooks.json` 仅限于 `.agents/`, 和一个空的 `{}` 返回200，并将文件全部返回 `hook_config: null`.
- `F27.hooks-invalid` 无法解析的 JSON，未知事件（PascalCase 或 snake_case），两种拼写相同的一个事件，以及一个没有命令返回的命令钩子，返回状态码 200 并附带 `hook_config: null` 和日志 `Failed to load hooks`。
- `F27.hooks-conversation`：配置返回，作为`POST /api/hooks`传递给项目中的`hook_config`对话，运行：一个DeepSeek，钩子的`HookExecutionEvent`在REST上出现，WebSocket回放，对话在重启后保持其`hook_config`。
- `F27.hooks-not-automatic`：同一项目中在没有 `hook_config` 的情况下启动的对话不会运行挂钩，尽管项目有 `hooks.json` 并且智能体使用了终端。
- `F27.hooks-block`: 一个 `PreToolUse` 挂起 2 次，终止智能体的终端调用（一个 `HookExecutionEvent` 与 `blocked: true`，一个 `UserRejectObservation` 从 `blocked_actions` 中，其标准错误作为原因，没有终端观测结果，没有文件）并记录动作直到智能体消耗它； 退出 2 的 `UserPromptSubmit` 钩子记录 `blocked_messages` 中排队的消息，并且运行立即完成，无需模型调用。
- `F27.subagents-builtin`：没有项目和用户智能体（关闭，或不存在的`project_dir`）目录正是四个内置函数（`bash-runner`，`code-explorer`，`general-purpose`，`web-researcher`），`level: builtin`和`is_builtin: true`，`mcp_servers`镜像`mcp_config`，`load_builtin: false`清空它。
- `F27.subagents-project`项目智能体从 `.agents/agents` 和 `.openhands/agents` 列出的 `level: project`, their `source` 文件，以及每一个前置元数据 tools, skills, color, permission mode, iteration limit, `<example>` 触发器，未知键 `metadata`, the body as `system_prompt`).
- `F27.subagents-user`：仅当`load_user`打开时，`~/.agents/agents`和`$OH_PERSISTENCE_DIR/agents`中的用户智能体与`level: user`一起列出，并且`load_project: false`隐藏项目的智能体。
- `F27.subagents-precedence`：名称是唯一的，第一个源获胜：项目智能体隐藏同名的内置和用户智能体，并且 `.agents/agents` 隐藏 `.openhands/agents`。
- `F27.subagents-invalid`不验证的定义（bad `permission_mode`, `max_iteration_per_run: 0` 被跳过，并记录警告 `README.md`, 子目录和非-`.md` 文件被忽略，但请求仍然返回200。
- `F27.subagents-bad-skill`: 一个项目智能体名称一个不存在的技能的 `skills` 不会破坏对话工作区：该目录列出它 (它只验证前置元数据)，对话会跳过它并记录警告，接受所有消息。
- `F27.catalog-sealed`：由会话 (`client_tools`) 注册的客户端工具是该会话智能体的一部分，但从未进入目录，该目录在启动时被密封。
- `F27.client-tool-call`: 当智能体调用客户端工具时，事件套接字会发送一个带有模型参数的 `ClientAction_<name>` `ActionEvent`，服务器会用 `Tool call dispatched to client.` 确认来回答，然后运行结束。 当会话重新启动后恢复时，该工具会再次注册； 在一次请求中重复的名称，与`terminal`冲突的名称，以及名称与模式不同但重复使用的名称，都会返回422错误，没有任何结果，而与模式相同的名称则会被接受。
- `F27.agent-definitions`: `agent_definitions` 在创建请求中添加那个子智能体可用作对话任务工具的一部分，该工具通过名称调用它（委托方运行命令， 代理方运行命令，   ) `TaskObservation` names it); 定义与会话一起存储，不会列出 `POST /api/sub-agents`.
- `F27.custom-tool-modules`: 以 `OH_EXTRA_PYTHON_PATH` 命名一个目录，`tool_module_qualnames` 在创建时导入该目录中的模块，智能体运行工具，`GET /api/tools/` 列出工具（密封的目录不报告映射）。 重新启动后，该工具就会消失，直到再次加载对话，并且有新消息再次运行它； 不可导入的模块是一个记录的警告，并且创建仍然成功。
- `F27.import-modules`：以`--import-modules`（和`OH_EXTRA_PYTHON_PATH`）启动的服务器在`GET /api/tools/`中列出模块的工具，并在任何对话存在之前将其提供在目录中； 无法导入的模块会在绑定其端口之前停止服务器。
- `F27.custom-tool-missing-on-resume` 当重启后无法导入会话的工具模块时，服务器应丢弃工具并警告，同时保持会话可读。 今天，其事件搜索和新消息为 500 (`Unknown kind`)。
- `F27.browser-playwright-path`：浏览器探测器在 `$PLAYWRIGHT_BROWSERS_PATH` 以及标准路径 `~/.cache/ms-playwright` 和 `PATH` 中找到 Playwright Chromium，并报告 `browser_tool_set` 可用。
- `F27.browser-probe`：如果没有 Chromium，服务器可以找到，目录报告 `browser_tool_set` 不可用，`/server_info` `usable_tools` 忽略它； 在服务器的 `~/.cache/ms-playwright` 中安装 Playwright Chromium 并重新启动后，目录报告它可用并 `usable_tools` 列出它。
- `F27.browser-disabled-launch`：从保存的设置（默认工具）发起的对话在重启后会 `browser_tool_set`，而服务器发现 Chromium 时则会 `enable_browser: false`。 之前创建的对话保留其存储的工具。
- `F27.browser-disabled`：`enable_browser: false` 目录报告 `browser_tool_set` 不可用，尽管存在 Chromium，而 `GET /api/tools/` 仍然列出它。
- `F27.server-info-browser-disabled`：与 `enable_browser: false`、`/server_info` `usable_tools` 与目录一致并省略 `browser_tool_set`，尽管存在 Chromium。
- `F27.subagents-browser-disabled`：与`enable_browser: false`相比，子智能体目录省略了仅限浏览器的`web-researcher`并保留其他内置内容。
- `F27.catalog-docker-runtime`: `conversation_runtime: docker`使用`browser_tool_set`时，虽然服务器找不到Chromium，但可以用于库存图片，但无法用于`-minimal`标签或`conversation_image_has_browser: false`。 `/server_info``usable_tools`对于浏览器来说遵循它。

<a id="how-to-get-to-it-agent-pov"></a>

## 如何到达 (智能体 POV)

- REST，钩子：`POST /api/hooks` 与 `{"project_dir": "<abs path>"}` (`HooksRequest`) 返回 `{"hook_config": HookConfig | null}`。 仅
  `<project_dir>/.openhands/hooks.json` 已读取。 由`F27.hooks-*`子弹驱动。
- REST，对话（第二个视图，由对话家族拥有）：
  `StartConversationRequest.hook_config` 将返回的配置携带到
  `POST /api/conversations`; `GET /api/conversations/{id}` 回声
  `hook_config`、`GET /api/conversations/{id}/events/search` 和下面的 WebSocket 进位 `HookExecutionEvent` (`hook_event_type`,
  `hook_command`, `stdout`, `exit_code`, `blocked`, `action_id`). 服务器永远不会自行将项目的 `hooks.json` 加载到对话中。 由`F27.hooks-conversation`和`F27.hooks-not-automatic`驱动。 退出 2 个块的钩子：`PreToolUse` 将调用变成
  `UserRejectObservation` (`rejection_source: hook`), `UserPromptSubmit` 使下一次运行无需模型调用即可完成； 待处理的条目是
  `GET /api/conversations/{id}` 上的 `blocked_actions` 和 `blocked_messages` 以及 `ConversationStateUpdateEvent` 秒 (`F27.hooks-block`) 中。
- REST，创建时注册（第二个视图，路由由会话族拥有）：`StartConversationRequest.client_tools`（`ClientToolSpec`：`name`，`description`，对象`parameters`，
  `annotations`), `agent_definitions` (`AgentDefinition`列表，形状相同
  `POST /api/sub-agents` 返回）和 `tool_module_qualnames`（工具名称到模块路径，在创建时导入并在恢复时再次导入）。
  `GET /api/conversations/{id}` 呼应 `client_tools` 和
  `tool_module_qualnames`; `agent_definitions` 仅保留在`meta.json` 中。 注册错误为 `422`，原因在 `detail` 中。 驱动力
  `F27.client-tool-call`、`F27.agent-definitions` 和
  `F27.custom-tool-modules`.
- REST、子智能体：`POST /api/sub-agents` 和 `SubAgentsRequest`（`load_user`、`load_project`、`load_builtin`，全部默认 `true`，以及
  `project_dir`) 每次返回 `{"agents": [SubAgentInfo]}`
  `AgentDefinition` 字段加上 `level`、`source` 和 `is_builtin`。 由`F27.subagents-*`子弹驱动。
- REST，工具：`GET /api/tools/` 返回一个简单的 JSON 注册名称数组； `GET /api/tools/catalog` 返回 `{"tools": [ToolCatalogEntry]}`。
  `/server_info` `usable_tools`（由服务器状态系列拥有）是较旧的可用性视图； 工具项目符号将其与目录进行比较。
- 智能体工具：`start_child_conversation` 接受 `task`，可选 `title` 和
  `isolation` `worktree` 默认情况下，或者 `shared`。 服务器注册它，但不将其附加到默认工具集：主机必须将其包含在父级中智能体。 其内部认证启动器调用 F04 所拥有的子 REST 路由，并返回 `StartChildConversationObservation`，包含子 id、父 id、状态、工作区和隔离 (`F27.child-conversation-tool`)。
- WebSocket: `/sockets/events/{conversation_id}` 交付
  `HookExecutionEvent` 实时和回放 (`resend_mode=all`); 由事件家族拥有，由 `F27.hooks-conversation` 重播。 这也是客户端了解智能体调用其客户端工具之一的方式：
  `ActionEvent`，其动作 `kind` 为 `ClientAction_<name>` (`F27.client-tool-call`)。
- 服务器进程：`OH_EXTRA_PYTHON_PATH`（或`--extra-python-path`）将目录添加到`sys.path`； `--import-modules a,b` 在启动时、在目录被密封之前导入模块，导入失败是致命的。 记录的自定义工具图像集 `OH_EXTRA_PYTHON_PATH` (`examples/02_remote_agent_server/06_custom_tool/Dockerfile`)。
  `control-agent-server launch` 和 `restart` 传递环境变量但没有服务器参数，因此 `F27.import-modules` 在普通 shell 中启动该服务器并附加到它。
- 配置：`enable_browser`（配置文件，或`OH_ENABLE_BROWSER`）强制使目录的浏览器入口不可用，并从之后创建的对话的默认工具中删除浏览器的`F27.browser-disabled-launch`。 `conversation_runtime: docker` 没有任何内容被探测，浏览器可用性来自 `conversation_image` 和
  `conversation_image_has_browser`（`F27.catalog-docker-runtime`，不需要 Docker 守护进程，因为没有对话开始）。 浏览器探针读取服务器进程的`HOME`。
- TypeScript 客户端：`HooksClient.loadHooks()` 和
  `RemoteConversation.loadHooks(projectDir)`（默认为工作区的工作目录），`SubAgentsClient.getSubAgents()`（也可以
  `ConversationManager.subAgents` 和 `OpenHandsClient.subAgents`),
  `ToolClient.listTools()` 和 `ToolClient.getToolCatalog()`。 PythonSDK没有这些路线的方法； `RemoteConversation` 转发其进程的
  `tool_module_qualnames` 和创建时注册的智能体定义。 TypeScript 消费者通道及其构建在 TypeScript 客户端系列中运行； `HooksClient`被驱动到那里。
- Agent Canvas (上下文 only): 对话开始流程加载工作区的钩子，子智能体选择器读取子智能体目录，以及智能体-profile 工具选择器读取工具目录。

<a id="driving-it-with-control-agent-server"></a>

## 使用 control-智能体-server 驱动它

前提条件：

- 运行已实时并导出，`doctor` 正常，`$DEEPSEEK_API_KEY` 已设置，
  `git` 和 `tmux` 已安装，`control-agent-server capabilities` 报告服务器无法自行找到的 Chromium 二进制文件 (`machine.chromium`)：不在标准路径 (`/usr/bin/chromium`，
  `/usr/bin/google-chrome`，...）而不是在 `PATH` 上，例如 Playwright 安装在 `$PLAYWRIGHT_BROWSERS_PATH` 下（`launch` 不会传递该变量）。 否则，浏览器项目符号无法显示不可用状态（请参阅陷阱）。 不需要启动标志。 几个项目符号重新启动运行（`F27.hooks-conversation`、`F27.client-tool-call`，自定义工具项目符号为 `--env OH_EXTRA_PYTHON_PATH`，浏览器项目符号为
  `--env` 和 `--config-json`），重启会清空进程范围的工具和子智能体注册表； 浏览器项目符号排在最后。
  `F27.import-modules` 还在普通 shell 中的空闲环回端口上启动和停止此结帐的第二个服务器。
- 下面的块激活 `deepseek-flash`，创建 `qa-f27-proj` 项目测试夹具（其 `.agents/agents/qa-helper.md`，其
  `.openhands/hooks.json` 带有 `PreToolUse` 钩子 `echo QA_PROJECT_HOOK` 及其技能 `qa-f27-proj-skill`），在运行的 `HOME` 中添加更多项目智能体、用户智能体，`fixtures/qa-f27/` 下的 `hooks.json` 变体，
  `badskill` 项目的智能体命名了一个缺失的技能，一个由运行者拥有的 Playwright 浏览器目录，该目录链接了机器的 Chromium 二进制文件 `pytools/qa_f27_tools.py`一个自定义工具模块，用于注册工具 `qa_f27_echo` 在导入时（它回答了） `QA_F27_ECHO_RAN <marker>`).
  ```sh
  control-agent-server llm preset deepseek
  P=$(control-agent-server fixture project --name qa-f27-proj --print-path)
  F="$AGENT_SERVER_VERIFY_RUN/fixtures/qa-f27"
  H="$AGENT_SERVER_VERIFY_RUN/home"
  mkdir -p "$F/snake/.openhands" "$F/empty/.openhands" "$F/badjson/.openhands" "$F/unknown/.openhands" \
    "$F/snakeunknown/.openhands" "$F/both/.openhands" "$F/nocmd/.openhands" "$F/agentsdir/.agents" "$F/nohooks" \
    "$F/badskill/.agents/agents" "$P/.openhands/agents" "$P/.agents/agents/qa-nested-dir" "$H/.agents/agents" "$H/.openhands/agents"
  printf '%s\n' '{"pre_tool_use": [{"matcher": "terminal|file_editor", "hooks": [{"command": "echo QA_SNAKE", "timeout": 7, "async": true}]}], "Stop": [{"hooks": [{"type": "prompt", "prompt": "QA done?"}]}]}' > "$F/snake/.openhands/hooks.json"
  printf '%s\n' '{}' > "$F/empty/.openhands/hooks.json"
  printf '%s\n' '{bad' > "$F/badjson/.openhands/hooks.json"
  printf '%s\n' '{"PreToolUsage": [{"hooks": [{"command": "true"}]}]}' > "$F/unknown/.openhands/hooks.json"
  printf '%s\n' '{"pre_tool_usage": [{"hooks": [{"command": "true"}]}]}' > "$F/snakeunknown/.openhands/hooks.json"
  printf '%s\n' '{"PreToolUse": [{"hooks": [{"command": "true"}]}], "pre_tool_use": []}' > "$F/both/.openhands/hooks.json"
  printf '%s\n' '{"pre_tool_use": [{"hooks": [{"type": "command"}]}]}' > "$F/nocmd/.openhands/hooks.json"
  printf '%s\n' '{"pre_tool_use": [{"hooks": [{"command": "true"}]}]}' > "$F/agentsdir/.agents/hooks.json"
  printf -- '---\nname: qa-reviewer\ndescription: QA reviewer. <example>review the qa fixture</example>\ncolor: purple\ntools:\n  - terminal\n  - file_editor\nskills: qa-f27-proj-skill\npermission_mode: never_confirm\nmax_iteration_per_run: 5\nqa_extra: QA_META\n---\nYou are the QA reviewer. Say QA_REVIEWER_MARKER.\n' > "$P/.agents/agents/qa-reviewer.md"
  printf -- '---\nname: general-purpose\ndescription: QA override of a built-in\n---\nQA_OVERRIDE_BODY\n' > "$P/.agents/agents/general-purpose.md"
  printf -- '---\nname: qa-bad-mode\npermission_mode: sometimes\n---\nQA_BAD\n' > "$P/.agents/agents/qa-bad-mode.md"
  printf -- '---\nname: qa-bad-iter\nmax_iteration_per_run: 0\n---\nQA_BAD\n' > "$P/.agents/agents/qa-bad-iter.md"
  printf -- '---\nname: qa-readme\n---\nQA_README\n' > "$P/.agents/agents/README.md"
  printf -- '---\nname: qa-nested\n---\nQA_NESTED\n' > "$P/.agents/agents/qa-nested-dir/qa-nested.md"
  printf 'name: qa-notes\n' > "$P/.agents/agents/qa-notes.txt"
  printf -- '---\ndescription: QA legacy project agent\n---\nQA_LEGACY_AGENT\n' > "$P/.openhands/agents/qa-legacy-agent.md"
  printf -- '---\nname: qa-reviewer\ndescription: QA shadowed copy\n---\nQA_SHADOWED\n' > "$P/.openhands/agents/qa-reviewer.md"
  printf -- '---\nname: qa-helper\ndescription: QA user copy of qa-helper\n---\nQA_USER_COPY\n' > "$H/.agents/agents/qa-helper.md"
  printf -- '---\nname: qa-user-agent\ndescription: QA user agent\n---\nQA_USER_AGENT\n' > "$H/.agents/agents/qa-user-agent.md"
  printf -- '---\nname: qa-persist-agent\ndescription: QA persistence-dir agent\n---\nQA_PERSIST_AGENT\n' > "$H/.openhands/agents/qa-persist-agent.md"
  printf -- '---\nname: qa-bad-skill\ndescription: QA agent naming a missing skill\nskills: qa-f27-missing-skill\n---\nQA_BAD_SKILL\n' > "$F/badskill/.agents/agents/qa-bad-skill.md"
  CHROME=$(control-agent-server capabilities | jq -r '.machine.chromium.detail')
  PW="$F/playwright"
  mkdir -p "$PW/chromium-qa/chrome-linux"
  ln -sfn "$(readlink -f "$CHROME")" "$PW/chromium-qa/chrome-linux/chrome"
  test -x "$PW/chromium-qa/chrome-linux/chrome"
  mkdir -p "$F/pytools"
  cat > "$F/pytools/qa_f27_tools.py" <<'EOF'
  from pydantic import Field

  from openhands.sdk import Action, Observation, ToolDefinition
  from openhands.sdk.tool import ToolExecutor, register_tool


  class QaF27EchoAction(Action):
      marker: str = Field(description="The marker text to echo back.")


  class QaF27EchoObservation(Observation):
      pass


  class QaF27EchoExecutor(ToolExecutor):
      def __call__(self, action, conversation=None):
          return QaF27EchoObservation.from_text(text=f"QA_F27_ECHO_RAN {action.marker}")


  class QaF27EchoTool(ToolDefinition[QaF27EchoAction, QaF27EchoObservation]):
      @classmethod
      def create(cls, conv_state=None, **params):
          return [cls(description="QA echo tool: returns the marker it is given.", action_type=QaF27EchoAction,
                      observation_type=QaF27EchoObservation, executor=QaF27EchoExecutor())]


  register_tool("qa_f27_echo", QaF27EchoTool)
  EOF
  .venv/bin/python -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import qa_f27_tools' "$F/pytools"
  ```

- **需要会话密钥 (`F27.auth`)。**调用每条没有密钥和错误密钥的路线，然后将运行密钥的列表作为阳性对照。
  ```sh
  control-agent-server api GET /api/tools/ --auth none --expect 401 --save F27.auth/tools-no-key
  control-agent-server api GET /api/tools/ --auth bad --expect 401
  control-agent-server api GET /api/tools/catalog --auth none --expect 401
  control-agent-server api POST /api/sub-agents --auth none --json '{}' --expect 401
  control-agent-server api POST /api/hooks --auth none --json '{}' --expect 401
  control-agent-server api GET /api/tools/catalog --auth bad --expect 401
  control-agent-server api POST /api/sub-agents --auth bad --json '{}' --expect 401
  control-agent-server api POST /api/hooks --auth bad --json '{}' --expect 401
  NOSLASH=/api/tools
  control-agent-server api GET "$NOSLASH" --auth none --expect 307 --check-header location matches '/api/tools/$'
  control-agent-server api GET /api/tools/ --expect 200 --check . contains terminal
  ```
  没有有效密钥的每项请求 `401`。 使用密钥时，列表为 `200`。 斜杠 redirect 答案 `307` 无密钥（它什么也没揭示），目标是 `401` 上面的。
- **坏尸体 (`F27.validation`).**不发送正文且类型错误。
  ```sh
  control-agent-server api POST /api/hooks --expect 422 --check detail.0.loc.0 eq body --save F27.validation/hooks-no-body
  control-agent-server api POST /api/hooks --json '{"project_dir": 123}' --expect 422 --check detail.0.loc.1 eq project_dir
  control-agent-server api POST /api/sub-agents --expect 422 --check detail.0.loc.0 eq body
  control-agent-server api POST /api/sub-agents --json '{"load_user": "maybe"}' --expect 422 --check detail.0.loc.1 eq load_user \
    --save F27.validation/sub-agents-bad-bool
  control-agent-server api POST /api/sub-agents --json '{"project_dir": ["x"]}' --expect 422 --check detail.0.loc.1 eq project_dir
  ```
  每个答案是 `422`，并指出了违规地点。
- **注册工具(`F27.tools-list`)。**阅读原始资料注册表。
  ```sh
  control-agent-server api GET /api/tools/ --expect 200 --check . len-ge 10 --check . contains terminal \
    --check . contains file_editor --check . contains task_tracker --check . contains browser_tool_set \
    --check . contains task_tool_set --check . contains planning_file_editor --check . contains glob \
    --check . contains ClassifyAndSwitchLLMTool --save F27.tools-list/tools
  ```
  身体是一个按注册顺序排列的姓名的简单数组。 `browser_tool_set` 是否可用，都会列出；一些条目是类名(`ClassifyAndSwitchLLMTool`)，这些条目是工具名下的。
- **斜杠重定向 (`F27.tools-redirect`)。** Call both paths with the other trailing-slash form.
  ```sh
  NOSLASH=/api/tools
  control-agent-server api GET "$NOSLASH" --expect 307 --check-header location matches '/api/tools/$' --save F27.tools-redirect/no-slash
  control-agent-server api GET /api/tools/catalog/ --expect 307 --check-header location matches '/api/tools/catalog$'
  ```
  两者都是 `307` with a `Location` 在本服务器上。 `api` 报告重定向，而不是跟随。 HTTP 遵循重定向的客户端（） TypeScript 客户端调用 `/api/tools/` 直接）查看目标。
- **工具目录(`F27.catalog`).**阅读目录并与注册表进行比较。
  ```sh
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet --check tools len-ge 10 \
    --check tools matches '"name": "terminal", "user_selectable": true, "usable": true, "description": "[^"]+", "in_default_set": true' \
    --check tools matches '"name": "file_editor", "user_selectable": true, "usable": true, "description": "[^"]+", "in_default_set": true' \
    --check tools matches '"name": "task_tracker", "user_selectable": true, "usable": true, "description": "[^"]+", "in_default_set": true' \
    --check tools matches '"name": "grep", "user_selectable": true, "usable": true, "description": "[^"]+", "in_default_set": false' \
    --check tools matches '"name": "switch_llm", "user_selectable": true, "usable": true, "description": "[^"]+", "in_default_set": true' \
    --check tools matches '"name": "browser_tool_set", "user_selectable": true, "usable": (true|false), "description": "[^"]+", "in_default_set": true' \
    --check tools contains '{"name": "task", "user_selectable": false' \
    --check tools contains '{"name": "planning_file_editor", "user_selectable": false' \
    --check tools contains '{"name": "route_task_to_model", "user_selectable": false' \
    --check tools not-contains '"name": "ClassifyAndSwitchLLMTool"' \
    --check tools not-contains '"user_selectable": true, "usable": true, "description": ""' \
    --check tools not-contains '"user_selectable": true, "usable": false, "description": ""' --save F27.catalog/catalog
  ```
  `terminal`、`file_editor`、`task_tracker`和`switch_llm`（注册表中没有的内置）是可选的、可用的并且是默认设置；
  `glob`/`grep`可以选择，但不是默认的； `task`,
  `planning_file_editor` 和 `route_task_to_model`（注册为
  `ClassifyAndSwitchLLMTool`) 是内部的。 每个可选条目都有一个描述（内部条目有一个空条目）。
- **儿童对话工具(`F27.child-conversation-tool`).**服务器注册主机提供的工具，而不将其添加到用户可选择的默认集中。 明确地附加它并让一个真实的模型启动一个孩子。
  ```sh
  control-agent-server api GET /api/tools/ --expect 200 --check . contains start_child_conversation \
    --save F27.child-conversation-tool/registry
  control-agent-server api GET /api/tools/catalog --expect 200 \
    --check tools matches '"name": "start_child_conversation", "user_selectable": false, "usable": true, "description": "[^"]*", "in_default_set": false' \
    --save F27.child-conversation-tool/catalog
  CPARENT=$(control-agent-server conversation start --workspace "$F/nohooks" --tools start_child_conversation \
    --no-autotitle --max-iterations 5 \
    --prompt 'Call start_child_conversation exactly once with these arguments: {"title": "QA_F27_CHILD", "isolation": "shared", "task": "Reply with the single word ok. Do not use tools or create any child conversations."}. After the call returns, finish without any more tool calls.' \
    --wait --timeout 240 --print-id)
  CHILD_OBSERVATIONS=$(control-agent-server api GET "/api/conversations/$CPARENT/events/search" \
    --query kind=ObservationEvent --expect 200 --check items contains StartChildConversationObservation \
    --save F27.child-conversation-tool/observation --field items)
  CHILD=$(jq -er --arg parent "$CPARENT" '[.[] | select(.tool_name == "start_child_conversation")] |
    select(length == 1) | .[0].observation |
    select(.is_error == false and .parent_conversation_id == $parent and .isolation == "shared") |
    .conversation_id' <<< "$CHILD_OBSERVATIONS")
  control-agent-server conversation wait "$CHILD" --timeout 240
  control-agent-server api GET "/api/conversations/$CHILD" --expect 200 \
    --check parent_conversation_id eq "$CPARENT" --check title eq QA_F27_CHILD \
    --check workspace.working_dir eq "$F/nohooks" --check execution_status eq finished \
    --save F27.child-conversation-tool/child
  control-agent-server api GET "/api/conversations/$CPARENT" --expect 200 \
    --check sub_conversation_ids contains "$CHILD" --save F27.child-conversation-tool/parent
  control-agent-server api DELETE "/api/conversations/$CHILD" --expect 200
  control-agent-server api DELETE "/api/conversations/$CPARENT" --expect 200
  ```
  工具的观测结果和两个会话视图一致，都认为子 ID、父链接和共享工作区。 F04拥有REST路由的工作树、验证和容量案例。 这个子弹证明了通过服务器内部的认证启动器实现模型驱动调度。
- **项目挂钩 (`F27.hooks-project`).**加载测试夹具项目的钩子。
  ```sh
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$P"'"}' --expect 200 \
    --check hook_config.pre_tool_use len-eq 1 --check hook_config.pre_tool_use.0.matcher eq '*' \
    --check hook_config.pre_tool_use.0.hooks.0.type eq command \
    --check hook_config.pre_tool_use.0.hooks.0.command eq 'echo QA_PROJECT_HOOK' \
    --check hook_config.pre_tool_use.0.hooks.0.timeout eq 60 --check hook_config.pre_tool_use.0.hooks.0.async eq false \
    --check hook_config.post_tool_use len-eq 0 --check hook_config.stop len-eq 0 --save F27.hooks-project/hooks
  jq -e '.hooks.PreToolUse[0].hooks[0].command == "echo QA_PROJECT_HOOK"' "$P/.openhands/hooks.json"
  ```
  硬盘上的文件使用了旧的包装 `PreToolUse`。 答案是
  `pre_tool_use`、默认超时、`60`、`async: false` 以及其他五个事件的空列表。
- **格式 (`F27.hooks-formats`).**带有正则表达式匹配器的 snake_case 文件和旁边的 PascalCase `Stop`。
  ```sh
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/snake"'"}' --expect 200 \
    --check hook_config.pre_tool_use.0.matcher eq 'terminal|file_editor' \
    --check hook_config.pre_tool_use.0.hooks.0.type eq command \
    --check hook_config.pre_tool_use.0.hooks.0.command eq 'echo QA_SNAKE' \
    --check hook_config.pre_tool_use.0.hooks.0.timeout eq 7 --check hook_config.pre_tool_use.0.hooks.0.async eq true \
    --check hook_config.stop.0.matcher eq '*' --check hook_config.stop.0.hooks.0.type eq prompt \
    --check hook_config.stop.0.hooks.0.prompt eq 'QA done?' --check hook_config.stop.0.hooks.0.command eq '' \
    --save F27.hooks-formats/snake
  ```
  匹配器、超时和 `async` 仍然存活，`type` 默认为 `command`
  `Stop` 与匹配器 `*` 变为 `stop`，并且提示词钩子有一个空
  `command`.
- **无挂钩 (`F27.hooks-absent`)。**没有项目挂钩的各种方式。
  ```sh
  control-agent-server api POST /api/hooks --json '{}' --expect 200 --check hook_config missing --save F27.hooks-absent/no-project-dir
  control-agent-server api POST /api/hooks --json '{"project_dir": null}' --expect 200 --check hook_config missing
  control-agent-server api POST /api/hooks --json '{"projectDir": "'"$P"'"}' --expect 200 --check hook_config missing \
    --save F27.hooks-absent/misspelled-field
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/qa-missing-dir"'"}' --expect 200 --check hook_config missing
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/nohooks"'"}' --expect 200 --check hook_config missing
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/agentsdir"'"}' --expect 200 --check hook_config missing
  control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/empty"'"}' --expect 200 --check hook_config missing \
    --save F27.hooks-absent/empty-file
  test -s "$F/agentsdir/.agents/hooks.json"
  ```
  七个人都回答`200 {"hook_config": null}`； 下的有效文件
  `.agents/hooks.json` 未读。 `projectDir` 命名相同的项目
  `F27.hooks-project` 加载，但未知字段被忽略，因此请求读取为“无项目”。
- **损坏 hooks.json (`F27.hooks-invalid`).**错误被吞没
  `null`; 只有日志告诉他们“没有钩子”。
  ```sh
  H0=$(control-agent-server logs --grep 'Failed to load hooks' | jq -r .total_matching)
  for d in badjson unknown snakeunknown both nocmd; do
    control-agent-server api POST /api/hooks --json '{"project_dir": "'"$F/$d"'"}' --expect 200 --check hook_config missing \
      --save "F27.hooks-invalid/$d"
  done
  control-agent-server logs --grep 'Failed to load hooks' --expect-min "$((H0 + 5))"
  ```
  每个答案是 `200 {"hook_config": null}` 并且这五条请求添加了
  `Failed to load hooks from ...` 将每个警告记录到服务器日志中。 日志会在重新启动和重播期间附加，因此计数来自 `H0`。
- **子智能体内置函数 (`F27.subagents-builtin`).**仅列出内置函数，然后列出 None。
  ```sh
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_project": false}' --expect 200 \
    --check agents len-eq 4 --check agents.0.name eq bash-runner --check agents.1.name eq code-explorer \
    --check agents.2.name eq general-purpose --check agents.3.name eq web-researcher \
    --check agents.0.level eq builtin --check agents.0.is_builtin eq true --check agents.3.is_builtin eq true \
    --check agents.2.tools contains file_editor --check agents.3.tools.0 eq browser_tool_set \
    --check agents.3.mcp_config.fetch.command eq uvx --check agents.3.mcp_servers.fetch.command eq uvx \
    --check agents.0.source matches 'preset/subagents/bash_runner\.md$' --save F27.subagents-builtin/builtins
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "project_dir": "'"$F/qa-missing-dir"'"}' \
    --expect 200 --check agents len-eq 4 --check agents.0.name eq bash-runner
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_project": false, "load_builtin": false}' \
    --expect 200 --check agents len-eq 0
  ```
  四个内置函数（浏览器已启用），全部 `level: builtin` 带有其捆绑的源文件。 `web-researcher` needs `browser_tool_set` and an MCP 获取服务器。 A `project_dir` 不存在的东西不是错误，也没有什么意义。 没有内置函数，列表为空。
- **项目子智能体 (`F27.subagents-project`).**列出没有用户智能体的项目智能体。
  ```sh
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "project_dir": "'"$P"'"}' --expect 200 \
    --check agents len-eq 7 --check agents.1.name eq qa-helper --check agents.1.level eq project \
    --check agents.1.is_builtin eq false --check agents.1.system_prompt contains QA_SUBAGENT \
    --check agents.2.name eq qa-reviewer --check agents.2.source eq "$P/.agents/agents/qa-reviewer.md" \
    --check agents.2.color eq purple --check agents.2.tools len-eq 2 --check agents.2.skills.0 eq qa-f27-proj-skill \
    --check agents.2.permission_mode eq never_confirm --check agents.2.max_iteration_per_run eq 5 \
    --check agents.2.when_to_use_examples.0 eq 'review the qa fixture' --check agents.2.metadata.qa_extra eq QA_META \
    --check agents.2.model eq inherit --check agents.2.system_prompt eq 'You are the QA reviewer. Say QA_REVIEWER_MARKER.' \
    --check agents.3.name eq qa-legacy-agent --check agents.3.source eq "$P/.openhands/agents/qa-legacy-agent.md" \
    --check agents.4.name eq bash-runner --save F27.subagents-project/project
  ```
  项目智能体在文件顺序中排在第一位 (`.agents/agents` 然后)
  `.openhands/agents`)，然后是内置函数。 `qa-legacy-agent`的前置元数据中没有`name`，并以其文件命名； 未知的前置元数据键落在 `metadata` 中。
- **用户子智能体 (`F27.subagents-user`).**用户智能体独自一人，然后关机。
  ```sh
  control-agent-server api POST /api/sub-agents --json '{"load_project": false, "load_builtin": false, "project_dir": "'"$P"'"}' \
    --expect 200 --check agents len-eq 3 --check agents.0.name eq qa-helper --check agents.0.level eq user \
    --check agents.0.system_prompt eq QA_USER_COPY --check agents.1.name eq qa-user-agent \
    --check agents.2.name eq qa-persist-agent --check agents.2.source eq "$H/.openhands/agents/qa-persist-agent.md" \
    --save F27.subagents-user/user-only
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_builtin": false, "project_dir": "'"$P"'"}' \
    --expect 200 --check agents not-contains qa-user-agent --check agents not-contains qa-persist-agent \
    --check agents not-contains QA_USER_COPY
  ```
  `~/.agents/agents` 位于 `$OH_PERSISTENCE_DIR/agents` 之前（此处均位于运行的 `HOME` 下），每个条目都是 `level: user`，并且项目的智能体与 `load_project: false` 无关。 对于 `load_user: false`，未列出用户智能体。
- **Precedence (`F27.subagents-precedence`).**一切都在：项目、用户和内置名称发生冲突。
  ```sh
  control-agent-server api POST /api/sub-agents --json '{"project_dir": "'"$P"'"}' --expect 200 --check agents len-eq 9 \
    --check agents.0.name eq general-purpose --check agents.0.level eq project \
    --check agents.0.description eq 'QA override of a built-in' --check agents.0.is_builtin eq false \
    --check agents.1.name eq qa-helper --check agents.1.level eq project --check agents.1.system_prompt contains QA_SUBAGENT \
    --check agents.2.name eq qa-reviewer --check agents.2.system_prompt contains QA_REVIEWER_MARKER \
    --check agents not-contains QA_SHADOWED --check agents not-contains QA_USER_COPY \
    --check agents.4.name eq qa-user-agent --check agents.5.name eq qa-persist-agent \
    --check agents.6.name eq bash-runner --check agents.8.name eq web-researcher --save F27.subagents-precedence/all
  ```
  九个独特的名称：`general-purpose` 项目名称替换内置名称，`qa-helper` 项目名称隐藏用户副本，`.openhands/agents` `qa-reviewer` 的副本被`.agents/agents` 的副本隐藏。
- **无效定义 (`F27.subagents-invalid`)。**该项目包含两个无效的智能体、一个README、一个嵌套目录和一个文本文件。
  ```sh
  W0=$(control-agent-server logs --grep 'Failed to load agent definition' | jq -r .total_matching)
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_builtin": false, "project_dir": "'"$P"'"}' \
    --expect 200 --check agents len-eq 4 --check agents not-contains qa-bad-mode --check agents not-contains qa-bad-iter \
    --check agents not-contains qa-readme --check agents not-contains qa-nested --check agents not-contains qa-notes \
    --save F27.subagents-invalid/project-only
  test -f "$P/.agents/agents/qa-bad-mode.md"
  control-agent-server logs --grep 'Failed to load agent definition' --expect-min "$((W0 + 2))"
  ```
  只列出四个有效的项目智能体。 这个请求添加了两个
  `Failed to load agent definition from ...` 向日志发出警告，每个无效文件发出一个警告（文件名换行到下一个日志行）。 每个早期读取该项目的请求也会记录它们，因此计数来自 `W0`。
- **智能体缺少技能 (`F27.subagents-bad-skill`)。**目录接受智能体； 工作区中的对话会跳过它并接收消息。
  ```sh
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_builtin": false, "project_dir": "'"$F/badskill"'"}' \
    --expect 200 --check agents len-eq 1 --check agents.0.name eq qa-bad-skill --check agents.0.skills.0 eq qa-f27-missing-skill
  GCID=$(control-agent-server conversation start --workspace "$F/nohooks" --no-run --tools terminal --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$GCID/events" \
    --json '{"role": "user", "content": [{"type": "text", "text": "hi"}], "run": false}' --expect 2xx \
    --save F27.subagents-bad-skill/send-control
  BCID=$(control-agent-server conversation start --workspace "$F/badskill" --no-run --tools terminal --no-autotitle --print-id)
  control-agent-server api POST "/api/conversations/$BCID/events" --json '{"role": "user", "content": [{"type": "text", "text": "hi"}], "run": false}' --expect 2xx --save F27.subagents-bad-skill/send
  control-agent-server api POST "/api/conversations/$BCID/events" --json '{"role": "user", "content": [{"type": "text", "text": "again"}], "run": false}' --expect 2xx --save F27.subagents-bad-skill/send-again
  control-agent-server logs --grep 'Skipping file-based agent' --expect-min 1
  ```
  同一消息发送到一个 [conversation] 工作区没有项目智能体被接受（控制）。 对话记录每个项目和用户智能体在第一次消息中，文件。 一个无法注册的定义（这里 `Skill 'qa-f27-missing-skill' not found but was given to agent 'qa-bad-skill'.`) 成本仅此而已子智能体跳过
  `Skipping file-based agent ...` 警告命名其文件（智能体名称换行到下一个日志行），另一个智能体寄存器。 插件智能体以同样的方式被跳过。
- **对话中的挂钩 (`F27.hooks-conversation`)。**加载项目的钩子，与它们开始 DeepSeek 对话，然后查找钩子。
  ```sh
  HC=$(control-agent-server api POST /api/hooks --json '{"project_dir": "'"$P"'"}' --field hook_config)
  HCID=$(control-agent-server conversation start --workspace "$P" --tools terminal --no-autotitle \
    --body-json '{"hook_config": '"$HC"'}' --prompt 'Run this exact shell command with the terminal tool: ls' \
    --wait --timeout 300 --print-id)
  control-agent-server conversation events "$HCID" --kinds ObservationEvent --contains AGENTS.md --expect-kind ObservationEvent
  control-agent-server conversation events "$HCID" --kinds HookExecutionEvent --contains '"hook_event_type": "PreToolUse"' \
    --expect-kind HookExecutionEvent
  control-agent-server conversation events "$HCID" --kinds HookExecutionEvent --contains '"stdout": "QA_PROJECT_HOOK\n"' \
    --expect-kind HookExecutionEvent --full --save F27.hooks-conversation/hook-events
  control-agent-server ws listen "/sockets/events/$HCID" --query resend_mode=all --until-kind HookExecutionEvent \
    --expect-kind HookExecutionEvent --duration 20 --save F27.hooks-conversation/ws-replay
  control-agent-server restart
  control-agent-server api GET "/api/conversations/$HCID" --expect 200 --check hook_config.pre_tool_use.0.matcher eq '*' \
    --check hook_config.pre_tool_use.0.hooks.0.command eq 'echo QA_PROJECT_HOOK' --quiet --save F27.hooks-conversation/after-restart
  ```
  智能体的`ls` 观测结果列表`AGENTS.md`，以及`HookExecutionEvent`
  with `hook_event_type: PreToolUse`, `tool_name: terminal`, `hook_command:
  echo QA_PROJECT_HOOK`, the command's output in `stdout` and `exit_code: 0`
  位于事件日志和 WebSocket 重播中。 重启后对话仍然报告相同的`hook_config`。
- **挂钩不会隐式加载 (`F27.hooks-not-automatic`)。**与提示词相同的项目，没有`hook_config`。
  ```sh
  NCID=$(control-agent-server conversation start --workspace "$P" --tools terminal --no-autotitle \
    --prompt 'Run this exact shell command with the terminal tool: ls' --wait --timeout 300 --print-id)
  control-agent-server conversation events "$NCID" --kinds ObservationEvent --contains AGENTS.md --expect-kind ObservationEvent
  control-agent-server conversation events "$NCID" --kinds HookExecutionEvent --expect-count 0 --save F27.hooks-not-automatic/no-hooks
  control-agent-server api GET "/api/conversations/$NCID" --expect 200 --check hook_config missing --quiet
  ```
  终端运行了（`AGENTS.md`），但没有（`HookExecutionEvent`），且`hook_config`是`null`：一个想要项目钩子的客户端必须调用
  `POST /api/hooks` 并传递结果，就像 `RemoteConversation.loadHooks` 调用者所做的那样。
- **阻塞挂钩 (`F27.hooks-block`).** `terminal` 上的 `PreToolUse` 挂钩退出 2，然后是 `UserPromptSubmit` 挂钩在排队消息上退出 2。
  ```sh
  mkdir -p "$F/blockws"
  BLK=$(control-agent-server conversation start --workspace "$F/blockws" --tools terminal --no-autotitle --max-iterations 6 \
    --body-json '{"hook_config": {"pre_tool_use": [{"matcher": "terminal", "hooks": [{"command": "echo QA_F27_DENIED >&2; exit 2"}]}]}}' \
    --prompt 'If the terminal call is blocked, do not retry and finish. Run this exact shell command with the terminal tool: touch qa_f27_blocked.txt' \
    --wait --timeout 300 --print-id)
  control-agent-server api GET "/api/conversations/$BLK" --expect 200 --check execution_status eq finished --check blocked_actions len-eq 0 --quiet
  control-agent-server conversation events "$BLK" --kinds ActionEvent --contains 'touch qa_f27_blocked.txt' --expect-kind ActionEvent
  control-agent-server conversation events "$BLK" --kinds HookExecutionEvent --contains '"blocked": true' --expect-min 1 \
    --full --save F27.hooks-block/pre-tool-use
  control-agent-server conversation events "$BLK" --kinds HookExecutionEvent --contains '"exit_code": 2' --expect-min 1
  control-agent-server conversation events "$BLK" --kinds UserRejectObservation --contains '"rejection_source": "hook"' --expect-min 1
  control-agent-server conversation events "$BLK" --kinds UserRejectObservation --contains '"rejection_reason": "QA_F27_DENIED"' --expect-min 1
  control-agent-server conversation events "$BLK" --key blocked_actions --contains QA_F27_DENIED --expect-min 1
  control-agent-server conversation events "$BLK" --kinds ObservationEvent --contains '"tool_name": "terminal"' --expect-count 0
  test ! -e "$F/blockws/qa_f27_blocked.txt"
  UPS=$(control-agent-server conversation start --workspace "$F/blockws" --tools terminal --no-autotitle --no-run \
    --body-json '{"hook_config": {"user_prompt_submit": [{"hooks": [{"command": "echo QA_F27_PROMPT_DENIED >&2; exit 2"}]}]}}' \
    --prompt 'Run this exact shell command with the terminal tool: touch qa_f27_prompt.txt' --print-id)
  control-agent-server api GET "/api/conversations/$UPS" --expect 200 --check execution_status eq idle \
    --check blocked_messages matches QA_F27_PROMPT_DENIED --quiet --save F27.hooks-block/prompt-blocked
  control-agent-server conversation events "$UPS" --kinds HookExecutionEvent --contains '"hook_event_type": "UserPromptSubmit"' --expect-count 1
  control-agent-server conversation events "$UPS" --kinds HookExecutionEvent --contains '"blocked": true' --expect-count 1
  control-agent-server api POST "/api/conversations/$UPS/run" --expect 200
  control-agent-server conversation wait "$UPS" --until finished,error,stuck --timeout 60
  control-agent-server api GET "/api/conversations/$UPS" --expect 200 --check execution_status eq finished --check blocked_messages len-eq 0 --quiet
  control-agent-server conversation events "$UPS" --kinds MessageEvent --contains '"source": "user"' --expect-count 1
  control-agent-server conversation events "$UPS" --kinds ActionEvent,MessageEvent --contains '"source": "agent"' --expect-count 0 \
    --save F27.hooks-block/prompt-no-agent-turn
  test ! -e "$F/blockws/qa_f27_prompt.txt"
  ```
  智能体要求终端（它的`ActionEvent` 在那里），钩子首先运行了`blocked: true` 和`exit_code: 2`，然后智能体得到了一个
  `UserRejectObservation` 与 `rejection_source: hook` 且钩子的 stderr 为 `rejection_reason`； 不存在终端观测结果并且未创建文件。 `blocked_actions` 在步骤运行时保存操作 ID（a
  `ConversationStateUpdateEvent`），一旦智能体消耗它，它就为空，因此客户端从事件中读取它，而不是从后面的 GET 中读取它。 当对话空闲时，被阻止的提示词被保存在 `blocked_messages` 中（由消息 ID 键入）； 运行它会消耗该条目并在没有智能体事件和模型调用的情况下完成。 阳性对照是
  `F27.hooks-conversation`：带有退出 0 的钩子的相同终端调用运行。
- **客户端工具不在目录中 (`F27.catalog-sealed`)。**通过对话注册客户端工具（无需模型）。
  ```sh
  CCID=$(control-agent-server conversation start --no-run --no-autotitle --tools terminal \
    --body-json '{"client_tools": [{"name": "qa_f27_client_tool", "description": "QA client-side tool"}]}' --print-id)
  control-agent-server api GET "/api/conversations/$CCID" --expect 200 --check agent.tools contains qa_f27_client_tool --quiet
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet --check tools not-contains qa_f27_client_tool \
    --check tools contains '"name": "terminal"' --save F27.catalog-sealed/catalog
  ```
  智能体会话中的客户端工具（其规格见 `params`） 服务器启动时封存的目录。
- **客户端工具调用 (`F27.client-tool-call`).**客户注册
  `qa_f27_call_tool`（一个必需的 `marker` 参数），侦听事件套接字并运行对话； 然后是注册错误； 然后重新启动并第二次调用。 该对话没有服务器工具（`--tools none`），因此客户端工具是它唯一可以调用的工具。
  ```sh
  CTW="$F/clienttool"
  mkdir -p "$CTW"
  CTSPEC='{"name": "qa_f27_call_tool", "description": "Record a QA marker in the client. Call it exactly once when asked.", "parameters": {"type": "object", "properties": {"marker": {"type": "string", "description": "The marker text."}}, "required": ["marker"]}}'
  CT=$(control-agent-server conversation start --workspace "$CTW" --tools none --no-autotitle --no-run \
    --body-json '{"client_tools": ['"$CTSPEC"']}' \
    --prompt 'Call the qa_f27_call_tool tool exactly once with marker set to QA_F27_CALL, then finish.' --print-id)
  control-agent-server ws start "/sockets/events/$CT" --name qa-f27-client --duration 300
  control-agent-server api POST "/api/conversations/$CT/run" --expect 200
  control-agent-server conversation wait "$CT" --until finished,error,stuck --timeout 300
  control-agent-server ws stop qa-f27-client --kinds ActionEvent --contains ClientAction_qa_f27_call_tool --expect-min 1 --wait 15 \
    --save F27.client-tool-call/ws
  control-agent-server api GET "/api/conversations/$CT" --expect 200 --check execution_status eq finished \
    --check client_tools.0.name eq qa_f27_call_tool --check agent.tools contains qa_f27_call_tool --quiet
  control-agent-server conversation events "$CT" --kinds ActionEvent --contains '"marker": "QA_F27_CALL"' --expect-kind ActionEvent
  control-agent-server conversation events "$CT" --kinds ObservationEvent --contains 'Tool call dispatched to client.' \
    --expect-kind ObservationEvent --full --save F27.client-tool-call/ack
  OFF='{"llm": {"model": "openai/qa-f27-offline", "api_key": "qa-f27-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": []}'
  N1=$(control-agent-server api GET /api/conversations/count --field .)
  control-agent-server api POST /api/conversations --json "{\"workspace\": {\"working_dir\": \"$CTW\"}, \"agent\": $OFF, \"client_tools\": [$CTSPEC]}" \
    --expect 201 --check client_tools.0.name eq qa_f27_call_tool --quiet
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$CTW\"}, \"agent\": $OFF, \"client_tools\": [{\"name\": \"qa_f27_dup\", \"description\": \"a\"}, {\"name\": \"qa_f27_dup\", \"description\": \"b\"}]}" \
    --expect 422 --check detail contains 'Duplicate client tool name' --save F27.client-tool-call/duplicate
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$CTW\"}, \"agent\": $OFF, \"client_tools\": [{\"name\": \"terminal\", \"description\": \"QA shadow\"}]}" \
    --expect 422 --check detail contains 'collides with an existing non-client tool' --save F27.client-tool-call/server-name
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$CTW\"}, \"agent\": $OFF, \"client_tools\": [{\"name\": \"qa_f27_call_tool\", \"description\": \"QA\", \"parameters\": {\"type\": \"object\", \"properties\": {\"other\": {\"type\": \"integer\"}}}}]}" \
    --expect 422 --check detail contains 'already registered with a different parameters schema' --save F27.client-tool-call/schema-conflict
  control-agent-server api GET /api/conversations/count --expect 200 --check . eq "$((N1 + 1))"
  control-agent-server api GET /api/tools/ --expect 200 --check . contains qa_f27_call_tool --check . not-contains qa_f27_dup --quiet
  control-agent-server restart
  control-agent-server api GET /api/tools/ --expect 200 --check . not-contains qa_f27_call_tool --quiet
  control-agent-server conversation send "$CT" --text 'Call the qa_f27_call_tool tool exactly once more with marker set to QA_F27_AGAIN, then finish.' \
    --wait --timeout 300
  control-agent-server conversation events "$CT" --kinds ActionEvent --contains '"marker": "QA_F27_AGAIN"' --expect-kind ActionEvent \
    --save F27.client-tool-call/after-restart
  control-agent-server api GET /api/tools/ --expect 200 --check . contains qa_f27_call_tool --quiet
  ```
  客户端在套接字上看到它的工具调用作为 `ActionEvent`
  `tool_name: qa_f27_call_tool`，善意的行动
  `ClientAction_qa_f27_call_tool` 和模型的 `marker`； 服务器立即用 `ClientToolObservation` (`Tool call dispatched to client.`) 回答它，并且智能体完成，因此客户端自己的结果永远不会通过此路径到达模型。 第二次创建显示接受同名同模式； 重复项、服务器工具名称和更改的模式均为 `422`，并附有原因，并且计数仅随着创建的一项而增长。 重新启动后，在加载其对话之前，不会注册该工具； 下一条消息从存储的 `client_tools` 中重新注册它，并且智能体再次调用它。 叉子保持
  `client_tools` 太（叉族）。
- ** 子智能体定义（`F27.agent-definitions`）。** 客户在创建请求中将 `qa-f27-delegate` 通过任务工具转发给智能体。
  ```sh
  DW="$F/delegate"
  mkdir -p "$DW"
  DCID=$(control-agent-server conversation start --workspace "$DW" --tools task_tool_set --no-autotitle --max-iterations 10 \
    --body-json '{"agent_definitions": [{"name": "qa-f27-delegate", "description": "QA delegate that creates files on request.", "tools": ["terminal"], "system_prompt": "You are the QA delegate. Do exactly what the task asks with the terminal tool, then finish."}]}' \
    --prompt 'Use the task tool with subagent_type qa-f27-delegate and this prompt: "Run this exact shell command with the terminal tool: echo QA_F27_DELEGATED > qa_f27_delegated.txt". Do not run anything yourself. Then finish.' \
    --wait --timeout 400 --print-id)
  control-agent-server api GET "/api/conversations/$DCID" --expect 200 --check execution_status eq finished --quiet
  control-agent-server conversation events "$DCID" --kinds SystemPromptEvent --contains 'QA delegate that creates files on request.' --expect-count 1
  control-agent-server conversation events "$DCID" --kinds ActionEvent --contains '"subagent_type": "qa-f27-delegate"' --expect-kind ActionEvent
  control-agent-server conversation events "$DCID" --kinds ObservationEvent --contains '"subagent": "qa-f27-delegate"' --expect-kind ObservationEvent \
    --full --save F27.agent-definitions/task
  grep -qx QA_F27_DELEGATED "$DW/qa_f27_delegated.txt"
  control-agent-server state grep qa-f27-delegate --glob "server/workspace/conversations/${DCID//-/}/meta.json"
  control-agent-server api POST /api/sub-agents --json '{"project_dir": "'"$DW"'"}' --expect 200 --check agents contains bash-runner \
    --check agents not-contains qa-f27-delegate --save F27.agent-definitions/catalog
  ```
  对话系统中的任务工具描述提示词列出了
  `qa-f27-delegate` 使用转发的描述，智能体的 `task` 操作为其命名，`TaskObservation` 报告 `subagent: qa-f27-delegate`； 委托人在同一个工作区中运行命令，因此文件包含 `QA_F27_DELEGATED`。 该定义存储在对话的`meta.json`中用于恢复，而子智能体目录仅读取文件和内置文件，不会列出它。
- **自定义工具模块(`F27.custom-tool-modules`)。**记录的自定义工具部署：`OH_EXTRA_PYTHON_PATH` 命名模块目录，客户端发送 `tool_module_qualnames`。
  ```sh
  MW="$F/modulews"
  mkdir -p "$MW"
  control-agent-server api GET /api/tools/ --expect 200 --check . contains terminal --check . not-contains qa_f27_echo --quiet
  X0=$(control-agent-server logs --grep 'Extended sys.path with 1 directory' | jq -r .total_matching)
  control-agent-server restart --env OH_EXTRA_PYTHON_PATH="$F/pytools"
  control-agent-server logs --grep 'Extended sys.path with 1 directory' --expect-min "$((X0 + 1))"
  control-agent-server api GET /api/tools/ --expect 200 --check . not-contains qa_f27_echo --quiet
  MCID=$(control-agent-server conversation start --workspace "$MW" --tools qa_f27_echo --no-autotitle \
    --body-json '{"tool_module_qualnames": {"qa_f27_echo": "qa_f27_tools"}}' \
    --prompt 'Call the qa_f27_echo tool exactly once with marker QA_F27_MODULE, then finish.' --wait --timeout 300 --print-id)
  control-agent-server api GET "/api/conversations/$MCID" --expect 200 --check execution_status eq finished \
    --check tool_module_qualnames.qa_f27_echo eq qa_f27_tools --check agent.tools contains qa_f27_echo --quiet
  control-agent-server conversation events "$MCID" --kinds ObservationEvent --contains '"kind": "QaF27EchoObservation"' --expect-count 1
  control-agent-server conversation events "$MCID" --kinds ObservationEvent --contains 'QA_F27_ECHO_RAN QA_F27_MODULE' --expect-min 1 \
    --save F27.custom-tool-modules/observation
  control-agent-server api GET /api/tools/ --expect 200 --check . contains qa_f27_echo --quiet --save F27.custom-tool-modules/tools
  control-agent-server api GET /api/tools/catalog --expect 200 --check tools not-contains qa_f27_echo --check tools contains '"name": "terminal"' --quiet
  M0=$(control-agent-server logs --grep 'qa_f27_missing_module' | jq -r .total_matching)
  OFF='{"llm": {"model": "openai/qa-f27-offline", "api_key": "qa-f27-offline-key", "base_url": "http://127.0.0.1:9/v1", "num_retries": 0}, "tools": []}'
  control-agent-server api POST /api/conversations \
    --json "{\"workspace\": {\"working_dir\": \"$MW\"}, \"agent\": $OFF, \"tool_module_qualnames\": {\"qa_f27_missing\": \"qa_f27_missing_module\"}}" \
    --expect 201 --check tool_module_qualnames.qa_f27_missing eq qa_f27_missing_module --quiet --save F27.custom-tool-modules/missing-module
  control-agent-server logs --grep 'qa_f27_missing_module' --expect-min "$((M0 + 1))"
  control-agent-server restart
  control-agent-server api GET /api/tools/ --expect 200 --check . not-contains qa_f27_echo --quiet
  control-agent-server conversation send "$MCID" --text 'Call the qa_f27_echo tool exactly once more with marker QA_F27_RESUMED, then finish.' \
    --wait --timeout 300
  control-agent-server conversation events "$MCID" --kinds ObservationEvent --contains 'QA_F27_ECHO_RAN QA_F27_RESUMED' --expect-min 1 \
    --save F27.custom-tool-modules/after-restart
  control-agent-server api GET /api/tools/ --expect 200 --check . contains qa_f27_echo --quiet
  ```
  `OH_EXTRA_PYTHON_PATH`仅扩展`sys.path`（在启动时记录）； create 导入 `qa_f27_tools`，其导入注册 `qa_f27_echo`，智能体的调用返回模块的 `QaF27EchoObservation`。 对话报告映射，而注册表列出了此后每个呼叫者的工具，而启动时封存的目录则没有提供。 不可导入的模块只是一个警告：创建是 `201` 并保留映射（一个创建，其智能体将该工具命名为 422，
  `F33.custom-tool-module-unimportable`). 重新启动后，注册表不再有该工具； 加载下一条消息的对话再次导入模块并且工具运行。
- **启动时导入了`F27.import-modules`。** `--import-modules` 是由拥有者控制的 shell-and-attach 工作流传递的服务器参数：子弹启动这个检查点的服务器，以纯 shell 形式，带有私有 `HOME`、状态目录和密钥，连接到它，然后在子弹结束之前停止它； 缺少模块的第二次启动必定会失败。
  ```sh
  QA_PY="$(jq -r .checkout "$AGENT_SERVER_VERIFY_RUN/run.json")/.venv/bin/python"
  IMP="$F/import-server"
  mkdir -p "$IMP/home" "$F/import-missing/home"
  IPORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  (cd "$IMP" && exec env -i PATH="$PATH" HOME="$IMP/home" OH_PERSISTENCE_DIR="$IMP/persist" TMUX_TMPDIR="$IMP/tmux" \
    OH_SESSION_API_KEYS_0=qa-f27-import-key OH_EXTRA_PYTHON_PATH="$F/pytools" NO_PROXY=127.0.0.1,localhost COLUMNS=400 \
    timeout 300 "$QA_PY" -m openhands.agent_server --host 127.0.0.1 --port "$IPORT" --import-modules qa_f27_tools) > "$IMP/server.log" 2>&1 &
  IPID=$!
  IRUN=""
  trap 'if [ -n "$IRUN" ]; then control-agent-server stop --run "$IRUN" > /dev/null 2>&1; fi; kill -TERM "$IPID" 2>/dev/null || true' EXIT
  export QA_F27_IMPORT_KEY=qa-f27-import-key
  IRUN=$(control-agent-server attach --url "http://127.0.0.1:$IPORT" --key-env QA_F27_IMPORT_KEY --name f27-import --print-run)
  curl -s --noproxy '*' --retry 60 --retry-connrefused --retry-delay 1 --retry-max-time 120 -o /dev/null "http://127.0.0.1:$IPORT/alive"
  control-agent-server api GET /api/tools/ --run "$IRUN" --expect 200 --check . contains qa_f27_echo --check . contains terminal \
    --quiet --save F27.import-modules/tools
  control-agent-server api GET /api/tools/catalog --run "$IRUN" --expect 200 --quiet \
    --check tools contains '{"name": "qa_f27_echo", "user_selectable": true, "usable": true' --save F27.import-modules/catalog
  control-agent-server api GET /api/conversations/count --run "$IRUN" --expect 200 --check . eq 0
  control-agent-server api GET /api/tools/ --run "$IRUN" --auth none --expect 401
  grep -q 'Imported module: qa_f27_tools' "$IMP/server.log"
  control-agent-server stop --run "$IRUN"
  kill -TERM "$IPID"
  wait "$IPID" || true
  MPORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  if (cd "$F/import-missing" && exec env -i PATH="$PATH" HOME="$F/import-missing/home" OH_PERSISTENCE_DIR="$F/import-missing/persist" \
    OH_SESSION_API_KEYS_0=qa-f27-import-key OH_EXTRA_PYTHON_PATH="$F/pytools" NO_PROXY=127.0.0.1,localhost COLUMNS=400 \
    timeout 120 "$QA_PY" -m openhands.agent_server --host 127.0.0.1 --port "$MPORT" --import-modules qa_f27_missing_module) > "$F/import-missing/server.log" 2>&1; then false; fi
  grep -q "ModuleNotFoundError: No module named 'qa_f27_missing_module'" "$F/import-missing/server.log"
  if grep -q 'Uvicorn running' "$F/import-missing/server.log"; then false; fi
  test ! -e "$F/import-missing/persist"
  ```
  `--import-modules qa_f27_tools` 时，工具在应用启动前已注册：`GET /api/tools/` 列出 `qa_f27_echo`，服务器上没有对话，启动后封存的目录提供它作为可选择和可用的工具（有一个空的 `description`：工具设置为空）
  `catalog_description`). 缺少的模块是致命的：进程在 uvicorn 启动之前以非零值 `ModuleNotFoundError` 退出，因此没有提供任何服务，也没有写入任何状态。 `api --until-ok` 放弃拒绝的连接，因此 `curl --retry-connrefused` 等待。
- **工具模块在恢复时消失（`F27.custom-tool-missing-on-resume`），已知错误。**在没有 `OH_EXTRA_PYTHON_PATH` 的情况下重新启动运行并使用以下对话
  `F27.custom-tool-modules`，其事件包括 `qa_f27_echo` 个调用。

  需要：`F27.custom-tool-modules`
  ```sh
  W0=$(control-agent-server logs --grep 'Failed to import module' | jq -r .total_matching)
  control-agent-server restart --reset-config
  control-agent-server api GET "/api/conversations/$MCID" --expect 200 --check tool_module_qualnames.qa_f27_echo eq qa_f27_tools --quiet
  control-agent-server api POST "/api/conversations/$MCID/events" --json '{"role": "user", "content": [{"type": "text", "text": "Reply with the single word ok."}], "run": false}' --expect 2xx,4xx --save F27.custom-tool-missing-on-resume/send  # bug：状态 eq 500 && response.body.exception 包含“未知种类 'QaF27EchoObservation'”
  control-agent-server logs --grep 'Failed to import module' --expect-min "$((W0 + 1))"
  control-agent-server api GET "/api/conversations/$MCID/events/search" --expect 200 --check items len-ge 1 --quiet  # 错误：状态 eq 500
  ```
  `_prepare_persisted_runtime` 记录“无法导入模块‘qa_f27_tools’”
  ... Tool will not be available.` and promises to go on without the tool.
  今天，对话根本无法加载：其存储的事件包含
  `QaF27EchoObservation`，其类仅由该模块定义，因此消息 `POST` 和 `GET .../events/search` 是 `500` 和 `Unknown kind 'QaF27EchoObservation'`。 只有`GET /api/conversations/{id}`，在不加载的情况下读取元数据，仍然回答。 删除或重命名自定义工具模块的部署会丢失使用该模块的每个对话。
- **剧作家浏览器目录(`F27.browser-playwright-path`)。**通过以下方式将服务器指向运行拥有的 Playwright 目录
  仅 `PLAYWRIGHT_BROWSERS_PATH`。
  ```sh
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false'
  control-agent-server restart --env PLAYWRIGHT_BROWSERS_PATH="$PW"
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet --check tools contains '{"name": "terminal", "user_selectable": true, "usable": true'
  control-agent-server api GET /api/tools/catalog --expect 200 --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": true' --save F27.browser-playwright-path/catalog
  ```
  第一个检查发现，该服务器没有在自己的系统上找到Chromium（没有标准路径，也没有在私有路径中找到） `~/.cache/ms-playwright`). Playwright 安装浏览器到 `$PLAYWRIGHT_BROWSERS_PATH` 当设置时，探针也会检查那里（在默认缓存之前）：重启后，目录报告 `usable: true` 浏览器工具可以以那个二进制文件启动。 Playwright的特殊值 `0` （安装包内的浏览器）不是一个目录，也不进行探测。
- **浏览器探针 `F27.browser-probe`。** 重启而不使用之前的配置，然后让浏览器不可用，然后将探针查看的 Chromium 重新放回服务器端 `HOME`，再重启一次。
  ```sh
  control-agent-server restart --reset-config
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false' \
    --save F27.browser-probe/catalog-before
  control-agent-server api GET /server_info --auth none --expect 200 --check usable_tools contains terminal \
    --check usable_tools not-contains browser_tool_set
  mkdir -p "$H/.cache"
  ln -sfn "$PW" "$H/.cache/ms-playwright"
  control-agent-server restart
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": true' \
    --save F27.browser-probe/catalog
  control-agent-server api GET /server_info --auth none --expect 200 --check usable_tools contains browser_tool_set \
    --save F27.browser-probe/server-info
  ```
  在链接之前，两个视图都离开了浏览器。 在之后，目录报告浏览器可用，并且 `usable_tools` 列出了它。 探针结果按进程缓存，因此，当服务器运行时安装的Chromium只在重启后才会显示。
- **默认工具遵循浏览器设置 (`F27.browser-disabled-launch`)。**使用运行拥有的 Chromium 链接从保存的设置（否 `--tools`，因此服务器选择默认工具集）开始对话，然后在重新启动后使用 `enable_browser: false`。 在本地设置正控制，以便在不存在浏览器负前提条件时该通道也可以工作。
  ```sh
  mkdir -p "$H/.cache"
  ln -sfn "$PW" "$H/.cache/ms-playwright"
  control-agent-server restart --reset-config
  BON=$(control-agent-server conversation start --no-run --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$BON" --expect 200 --check agent.tools contains browser_tool_set \
    --check agent.tools contains terminal --quiet --save F27.browser-disabled-launch/enabled
  control-agent-server restart --config-json '{"enable_browser": false}'
  BOFF=$(control-agent-server conversation start --no-run --no-autotitle --print-id)
  control-agent-server api GET "/api/conversations/$BOFF" --expect 200 --check agent.tools not-contains browser_tool_set \
    --check agent.tools contains terminal --check agent.tools contains file_editor --quiet --save F27.browser-disabled-launch/disabled
  control-agent-server api GET "/api/conversations/$BON" --expect 200 --check agent.tools contains browser_tool_set --quiet
  test -L "$H/.cache/ms-playwright"
  ```
  找到了Chromium，默认设置为`terminal`，`file_editor`
  `task_tracker`和`browser_tool_set`； 与 `enable_browser: false` 相同的请求仅获得前三个，尽管 Chromium 仍然存在。 该设置在创建对话时应用：较早的对话将浏览器保留在其存储的智能体中。 物化智能体配置文件的解析工具是智能体配置文件系列的视图。
- **浏览器被配置禁用(`F27.browser-disabled`)。**同一台机器，
  `enable_browser: false`; 即使该子弹单独运行，运行的 Chromium 链接也提供了积极的探测先决条件。
  ```sh
  mkdir -p "$H/.cache"
  ln -sfn "$PW" "$H/.cache/ms-playwright"
  control-agent-server restart --config-json '{"enable_browser": false}'
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false' \
    --save F27.browser-disabled/catalog
  control-agent-server api GET /api/tools/ --expect 200 --check . contains browser_tool_set
  test -L "$H/.cache/ms-playwright"
  ```
  尽管前一子弹的探针发现是Chromium，但目录强制`usable: false`，而原始注册表仍然列出
  `browser_tool_set`（工具在导入时注册，始终通过浏览器注册）。
- **禁用浏览器时可用的工具 (`F27.server-info-browser-disabled`)。**将 `/server_info` 与同一服务器上的目录进行比较。

  需要：`F27.browser-probe`、`F27.browser-disabled`
  ```sh
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false'
  control-agent-server api GET /server_info --auth none --expect 200 --check usable_tools contains terminal --check usable_tools not-contains browser_tool_set --save F27.server-info-browser-disabled/server-info
  ```
  在本服务器上进行的对话从未得到浏览器，且目录也这么说。 `usable_tools` 一致同意并省略了 `browser_tool_set`，尽管 Chromium 检测到 `/server_info` 也应用了相同的配置决策 (`configured_browser_available`)。
- **仅限浏览器子智能体，禁用浏览器 (`F27.subagents-browser-disabled`)。**使用 `enable_browser: false` 列出服务器上的内置程序（重新启动也使配方保持在 `--only` 下）。
  ```sh
  control-agent-server restart --config-json '{"enable_browser": false}'
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false'
  control-agent-server api POST /api/sub-agents --json '{"load_user": false, "load_project": false}' --expect 200 --check agents contains '"name": "bash-runner"' --check agents not-contains '"name": "web-researcher"' --save F27.subagents-browser-disabled/builtins
  ```
  该路由通过配置的浏览器可用性（即目录的）
  `configured_browser_available`) 到 `discover_builtin_agents`，所以
  `web-researcher`，其唯一的工具是`browser_tool_set`，被排除在外，并且客户绝不会在没有可用工具的情况下提供子智能体； 其他三个内置组件保留。 服务器还注册内置智能体以进行对话
  `enable_browser=True` 在导入 (`tool_router.py`) 时，因此根据源，会话的任务工具读取的委托注册表仍然有效
  `web-researcher`（此处未驱动）。
- **Docker 对话运行时间 (`F27.catalog-docker-runtime`).**删除 Chromium 链接并作为协调器重新启动，其对话将在容器中运行； 没有容器启动，因此不需要 Docker 守护进程。
  ```sh
  rm -f "$H/.cache/ms-playwright"
  control-agent-server restart --reset-config \
    --config-json '{"conversation_runtime": "docker", "conversation_image": "ghcr.io/openhands/agent-server:1.2.3-python-minimal"}'
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false' \
    --save F27.catalog-docker-runtime/minimal-image
  control-agent-server restart --reset-config \
    --config-json '{"conversation_runtime": "docker", "conversation_image_has_browser": false}'
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": false'
  control-agent-server restart --reset-config --config-json '{"conversation_runtime": "docker"}'
  control-agent-server api GET /server_info --auth none --expect 200 --check conversation_runtime eq docker \
    --check usable_tools contains browser_tool_set
  control-agent-server api GET /api/tools/catalog --expect 200 --quiet \
    --check tools contains '{"name": "browser_tool_set", "user_selectable": true, "usable": true' \
    --check tools contains '{"name": "terminal", "user_selectable": true, "usable": true' \
    --save F27.catalog-docker-runtime/stock-image
  test ! -e "$H/.cache/ms-playwright"
  ```
  `-minimal` 标签和`conversation_image_has_browser: false` 会使浏览器无法使用。 股票图片（默认）
  `conversation_image`) 使其可用，尽管当记录的浏览器否定先决条件成立时，服务器进程没有 Chromium，并且
  `/server_info` `usable_tools` 遵循浏览器的目录，因此这里也列出了 `browser_tool_set`。 它的其他条目仍然来自服务器进程自己的探测。

<a id="gotchas"></a>

## 陷阱

- `POST /api/hooks` 从不报告错误：缺失、空或损坏
  `hooks.json` 与 `{"hook_config": null}` 相同。 检查服务器日志 (`logs --grep 'Failed to load hooks'`) 以区分它们。
- 该路由仅读取 `<project_dir>/.openhands/hooks.json`。 SDK 的
  `HookConfig.load()` 也会回退到 `$OH_PERSISTENCE_DIR/hooks.json`，但路由不会，并且对话不会加载钩子，除非 `hook_config` （或插件）带来它们。
- 钩子事件键是响应中的 snake_case (`pre_tool_use`, ...)； PascalCase 和 `{"hooks": {...}}` 包装器在磁盘上被接受。 `HookExecutionEvent` 报告 PascalCase 名称 (`hook_event_type: PreToolUse`)。 `async` 标志是已序列化和 `async`。
- 子智能体目录仅验证前置元数据。 它没有解决
  `skills`、`tools` 或 `model`（配置文件名称）； 当对话注册智能体 (`F27.subagents-bad-skill`) 时，会跳过缺少的技能并发出警告，而当它生成一项时，其他技能会失败。 插件智能体和编程注册未列出。
- `$OH_PERSISTENCE_DIR/agents` 替换用户智能体的 `~/.openhands/agents`； 在发射的运行中，两者都是`<run>/home/.openhands/agents`，因此子弹无法区分两者。
- `web-researcher` 的 MCP `env` 值返回时被屏蔽 (`**********`)，甚至 `${TAVILY_API_KEY}` 占位符，因为 MCP 环境值为机密。
- 目录条目没有稳定的索引（注册顺序），因此配方将条目的已序列化前缀与 `--check tools contains` 或
  `matches`; 场序为 `name`、`user_selectable`、`usable`、
  `description`, `in_default_set`.
- 浏览器可用性取决于机器：标准路径（`/usr/bin/chromium`、`/usr/bin/google-chrome`、...）或服务器上的 Chromium
  `PATH` 总是能找到。 在这样的机器上，负控制
  `F27.browser-probe` 失败，第一次检查也失败
  `F27.browser-playwright-path`; 运行 Chromium 仅位于 Playwright 目录中的家族（`capabilities` 对其进行命名）。 `launch` 不
  pass `$PLAYWRIGHT_BROWSERS_PATH` on to the server, so the server sees only
  食谱给出的内容是`--env`。 探针按进程缓存 (`functools.cache`)，因此在更改安装内容后重新启动。 对于`conversation_runtime: docker`，没有任何东西被探测，并且每个工具都被报告为可用，除非图像设置所示。
- 客户端工具在对话开始和消失时在整个进程范围内进行注册
  `GET /api/tools/` 重启后，直到他们的对话重新加载。 目录从未显示过它们。 一个像注册服务器工具的客户端工具`terminal`, `file_editor`) makes `POST /api/conversations` 422，另一个过程中的不同会话注册的名字也一样 `parameters`  模式生成的动作类型
  `ClientAction_<name>` 是进程全局的）； 重新启动可以清除该问题。
- 服务器确认客户端工具调用本身 (`Tool call dispatched to client.`)，并且智能体循环继续； 没有路由将客户端的结果返回到该调用中。
- `blocked_actions` 在钩子阻塞的同一个智能体步骤中被消耗，因此运行后 GET 显示 `{}`； 使用键 `blocked_actions`（或 `UserRejectObservation`）读取 `ConversationStateUpdateEvent`。
  仅当被阻止的消息等待运行时，`blocked_messages` 才保持可见。 模型可能重试阻塞调用； 配方允许多次被阻止的尝试 (`--expect-min`)。
- `tool_module_qualnames` 更改流程范围注册表，并且自定义工具的事件需要其模块更改反序列化 (`F27.custom-tool-missing-on-resume`)。 服务器日志包含长行，因此配方 grep 可以查找短语 (`Extended sys.path with 1 directory`, `Failed to import module`)。
- `OH_EXTRA_PYTHON_PATH`仅扩展`sys.path`； 在创建命名模块或 `--import-modules` 在启动时执行操作之前，不会导入任何内容。 启动的运行使用 `restart --env` 获取变量，但 `--import-modules` 需要在 `launch` (`F27.import-modules`) 之外启动服务器。
- `GET /api/tools`和`/api/tools/catalog/`在身份验证之前重定向(307)； `map check` 根据路由表验证配方路径，因此配方通过 shell 变量调用无斜杠路径。
