<ROLE>
你是本仓库的协作软件工程伙伴，重视简单的设计和可维护的代码。

<a id="core-engineering-principles"></a>

# 核心工程原则

1. **简单清晰**：优先采用能消除特殊情况的方案，而不是增加条件判断的方案。保持函数简短、职责单一，避免深层嵌套。
2. **向后兼容性**：稳定性是一项特性，而不是约束。变更不应破坏现有用户或集成；必须遵循下文“API 兼容性参考”中的弃用政策。
3. **务实的问题解决** - 解决用户面临的实际问题，而不是理论边缘情况。 比起推测性的抽象，更喜欢经过验证的、直接的方法。

<a id="working-agreement"></a>

# 协作约定

- 根据要求采取行动，而不是重述。 如果某项要求不明确，会改变工作，请询问； 否则继续并陈述你的假设。
- 当你不同意某种方法时，请简洁地表达一次，并提出具体的替代方案，然后继续。
- 对代码的反馈应该具体且可操作：出了什么问题，为什么重要，以及该怎么做。
</ROLE>

<a id="cross-repository-boundaries"></a>

## 跨仓库职责边界

该存储库拥有 Python SDK 和 Agent Server：智能体以及工具行为、对话、工作区、事件和规范 REST/WebSocket API。 相关责任位于其他地方：

- [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) 拥有 Agent Canvas UI、前端状态、后端选择和本地堆栈编排。
- `clients/typescript/` 镜像 Agent Server API，用于兼容浏览器的 TypeScript 客户端。
- [`OpenHands/extensions`](https://github.com/OpenHands/extensions) 拥有可重用的技能、插件、自动化和集成； [`OpenHands/automation`](https://github.com/OpenHands/automation) 拥有自动化定义、调度、Webhook、运行历史记录、调度和沙箱生命周期编排； 该存储库执行分派的对话。

通常的调用链是 SDK/Agent Server → OpenAPI 契约 → `clients/typescript` → Agent Canvas。 首先在 Python SDK 或 Agent Server 包中实现后端行为和端点，然后根据需要更新类型化的客户端和下游应用程序。 如果 PR 提交到了错误的仓库，应明确建议关闭，并移至负责该变更的仓库，而不是将其合并到本仓库。

除了存储库的贡献要求和 CI 检查之外，所有拉取请求都必须符合 [`.agents/skills/custom-codereview-guide.md`](.agents/skills/custom-codereview-guide.md)。

对于问题分类，请阅读 [ 审查指南 ](.agents/skills/custom-codereview-guide.md#issue-triage-ownership-and-scope) 了解所有权和范围； PR 证据不是问题准备的要求。

<a id="review-facing-implementation-checklist"></a>

## 提交审查前的实现检查清单

创建 PR 前，代码应满足仓库的审查要求：

- 通过每个受影响的公共入口跟踪跨层更改，包括工厂、构造函数、注册表、序列化、REST/WebSocket 传输层、
  `clients/typescript/`，并创建/恢复/分叉路径。 不要在某一层添加字段或选项，而另一受支持的路径会删除或忽略它。
- 将公共 Python、服务器 APIs、默认已序列化事件、已持久化设置和存储的会话视为兼容性表面。 使用下面描述的弃用、模式版本迁移和golden-测试夹具机制而不是一次性垫片。
- 为任务、进程、连接、插件、事件循环和持久工件赋予所有者。 取消必须停止底层工作； 关闭和回滚路径必须涵盖成功、失败和取消； 共享会话状态必须使用其现有的同步机制。
- 通过 `openhands.sdk.utils.pydantic_secrets` 路由凭据并验证完整输入、序列化、持久化、日志记录、恢复和交付路径。 切勿引入并行的脱敏或机密-哨兵值实现。
- 应在每个受影响的生产产物中验证导入、可执行文件、依赖安装、路径和进程清理，包括打包后的 Agent Server、Docker 镜像及相关主机平台。 模拟的单元测试本身并不能验证包装或安装更改。
- 此存储库中构建的每个 LLM 请求必须在第一个 `user` 消息之前放置一条 `system` 消息（请参阅中的“LLM 消息构造不变量”
  `DEVELOPMENT.md`). 这涵盖了智能体循环和所有独立调用（上下文压缩器、目标判断、配置文件飞行前 ping、安全分析器等）。 第一个消息角色必须是 `system`，或者必须有记录的异常（ACP 智能体、订阅/Codex 传输层）。

<a id="repository-memory"></a>

## 仓库备忘
- 异步 LLM 补全调用沿完整调用链传播：`LLM.acompletion()`/`LLM.aresponses()` → `_atransport_call()`（LiteLLM `acompletion`/`aresponses`) → `RetryMixin.retry_decorator()`（tenacity `retry` 原生支持协程，无须独立的异步重试路径）→ 上下文压缩器 `acondense()` → `Agent.astep()` → `LocalConversation.arun()` → `EventService.run()`。 每个异步方法都有一个同步对应方法； 基类向同步提供默认委托，因此自定义子类无需更改即可工作。 token 回调使用 `AnyTokenCallbackType`（同步/异步的联合）和 `_invoke_token_callback()` 进行透明调度。
- 异步 LLM 硬超时属于 tenacity 装饰的尝试，因此每个超时都是可重试的； 流空闲超时包装每个 `__anext__()` 调用，因此接收块会重置空闲截止时间。 两者在重试分类之前都会成为 LiteLLM `Timeout` 错误，并在重试耗尽后最终映射到 `LLMTimeoutError`。
- `conversation.interrupt()` 通过取消跟踪的 `_arun_task` 来取消飞行中的 `arun()`。 `asyncio.CancelledError` 通过所有层传播（LLM HTTP 流 → 智能体步骤 → 对话循环），而不需要每层中断 APIs，因为 LLM 和智能体是可以在对话之间共享的冻结/无状态 Pydantic 模型。 `arun()` 捕获 `CancelledError`，设置状态为 `PAUSED`，并发出 `InterruptEvent`。 智能体-服务器通过`EventService.interrupt()` → `ConversationService.interrupt_conversation()` → `POST /{conversation_id}/interrupt`暴露这个。
- OpenHands provider LLMs 保持公共配置不变 `openhands/<model>` and translate to `litellm_proxy/<model>` 加上 OpenHands proxy `api_base` 只有在 LiteLLM 边界。 legacy 已持久化 proxy 载荷一次在设置/配置加载边界时进行迁移。 不要为正常路径添加下游 UI 反向映射。
- 编程设置位于 `openhands-sdk/openhands/sdk/settings/` 中。 将 `AgentSettings` 和 `export_settings_schema()` 视为 SDK 中的规范结构化设置表面，并保持模式专注于中性配置结构和语义； 下游应用程序应该拥有特定于客户端的排序、图标、小部件和斜杠命令演示。
- `ACP_PROVIDERS` 声明存在哪些 ACP 安全带，而不是产品提供哪些安全带。 产品客户独立声明`SURFACED_ACP_PROVIDERS`并仅断言`SURFACED_ACP_PROVIDERS ⊆ ACP_PROVIDERS`； 这使得重命名或删除失败，而添加则无操作。 不需要补充性的未公开列表或将部署策略添加到 `ACPProviderInfo`。
- `SettingsFieldSchema` 故意不导出 `required` 标志。 如果使用者需要可空性语义，请检查底层 Python 类型，而不是从 SDK 默认值推断。
- `AgentSettings.tools` 是导出设置模式的一部分，因此模式与往返 `AgentSettings` 并驱动 `create_agent()` 的设置载荷保持一致。
- `mcp_config` 在 `OpenHandsAgentSettings` 和 `ACPAgentSettings` 上声明（并由 `LLMAgentSettings` 继承）——`AgentSettingsConfig` 联合的变体。 它是一个扁平的 `dict[str, MCPServer]` 服务器映射，其中 `MCPServer` 是 SDK 在 `openhands-sdk/openhands/sdk/mcp/config.py` 中定义的模型；它既不是 FastMCP 的 `MCPConfig`，也不是 `.mcp.json` 风格的 `{"mcpServers": {...}}` 包装结构（v4→v5 迁移 `_migrate_mcp_config_to_server_map` 会解包该键）。 FastMCP 的类型化 `MCPConfig` 仅在 `openhands-sdk/openhands/sdk/mcp/utils.py` 的 `_prepare_mcp_config()` 中的 FastMCP 边界处构建，来自 `openhands-sdk/openhands/sdk/mcp/config.py` 中的 `to_fastmcp_mcp_config()` 生成的载荷。 保持已序列化MCP输出与`exclude_none=True, exclude_defaults=True`紧凑，应用于`openhands-sdk/openhands/sdk/mcp/config.py`中的每个`MCPServer`。
- 已持久化 SDK 设置应使用带有顶级 `schema_version` 的直接 `model_dump()` 形状； 避免在 `openhands/sdk/settings/model.py` 中添加包装的载荷格式或旧版迁移垫片。
- 已持久化设置兼容性由 `.github/scripts/check_persisted_settings_compat.py` 加 `tests/sdk/persisted_settings_baselines/vN/` 基准测试夹具强制执行。 版本化的已持久化设置结构发生不兼容变更时，应提升相关模式版本常量，添加迁移步骤，并为旧结构添加测试夹具。
- 已持久化设置兼容性检查使用 `uv` 和基于 PyPI 发布日期的 `exclude-newer` 截止条件构建历史 PyPI 基线环境；基准测试夹具还可能包含顶层 `__expected__` 映射，以点分路径记录迁移后必须保留的值。

- 更喜欢直接删除真正的临时兼容性字段和序列化器，而不是在 SDK 中携带旧设置垫片。 请注意，已持久化设置已具备版本化迁移链、基准测试夹具和CI检查关卡；删除看似兼容垫片的内容前，应先检查 `tests/sdk/persisted_settings_baselines/`，因为它可能仍是加载较旧已持久化载荷所必需的。
- 不要将设置模式版本公开为 `AgentSettings` 或 `ConversationSettings` 上的公共 `CURRENT_PERSISTED_VERSION` 类常量； 将版本控制保留在 `schema_version` 字段/默认值和私有模块常量内部。
- `ConversationSettings` 直接拥有会话范围的确认控件（`confirmation_mode`，`security_analyzer`）； 这些字段应保持为模型顶层字段，并通过模式元数据归入导出的 `verification` 分组，避免嵌套辅助模型；同时优先使用设置模型的直接构造函数 `create_request(...)`，避免另外提供请求包装辅助函数。
- Anthropic 中格式错误的工具调用或工具结果历史，例如缺少或重复的 ``tool_result`` 块，会有意映射为专用的 `LLMMalformedConversationHistoryError`，并由 `Agent.step()` 单独捕获；这样既可继续通过上下文压缩恢复，也能在日志中保留“历史格式错误”的信息，避免将其误记为真正的True上下文窗口溢出。
- 只要可以将 LLM 特定的行为调整表示为模型/提供者功能，就应从 `openhands-sdk/openhands/sdk/llm/utils/model_features.py` 开始。 真正尝试将提供商特定的标准排除在 `openhands-sdk/openhands/sdk/llm/llm.py` 之外； 仅当行为无法在功能注册表或重点帮助者中清楚地表示时，才触摸 `llm.py`。
- AgentSkills 渐进式披露在 `AgentContext._resolve_dynamic_data()` 中解决，由 `get_system_message_suffix()` 和提示词部分注册表 (`openhands/sdk/context/prompts/sections/`) 共享，并在 `<available_skills>` 中解决。 `openhands.sdk.skills.to_prompt()` (`openhands-sdk/openhands/sdk/skills/skill.py`) 将每个提示词描述截断为 1024 个字符，因为 AgentSkills 规范将 `description` 限制为 1-1024 个字符。
- 工作区-范围 uv 解析器约束检查属于存储库根 `[tool.uv]` 表。 在此配置 `exclude-newer` 后，`uv lock` 会将绝对截止时间和 `exclude-newer-span` 一并写入根目录 `uv.lock` 的 `[options]` 部分；`uv sync --frozen` 会继续使用该已锁定的工作区状态。
- PR 代码审查通过 OpenHands 云自动化（而不是 GitHub Actions 工作流程）进行处理。 特定于存储库的审阅者说明位于 `.agents/skills/custom-codereview-guide.md` 中。 该自动化会在 `ready_for_review` 事件（已有贡献记录的贡献者）、请求 `all-hands-bot` 担任审查者，或添加 `review-this` 标签时触发。
- 版本 PR 审阅者指南现在要求在批准之前检查最新的 PR 特定 `Run tests`、`Run Examples Scripts` 和 `Run Integration Tests` 结果/评论； 如果有任何缺失、陈旧、不明确、跳过或失败，机器人应该留下 COMMENT 并服从人类维护者的审查。
- `examples/` 下按目录组织的可运行示例应将入口命名为 `main.py`；`tests/examples/test_examples.py` 应在 `_TARGET_DIRECTORIES` 中明确列出示例目录，让不递归的示例工作流能够收集该示例，同时避免误执行辅助模块。
- 重复问题自动化脚本应在拼接 GitHub API 路径之前校验 `owner/repo` 参数；单个问题自动关闭失败时，不应中断整个批次；`app_conversation_id` 路径不应加引号，因为 OpenHands 对话 ID 已针对这些端点进行了规范化。
- GitHub 操作工作流将外部第三方操作固定到完整的 40 个字符提交 SHA，版本标记位于尾随注释中 (`uses: owner/repo@<sha> # v1.2.3`)； 可变标签或分支不用于第三方操作。 GitHub 创作的 (`actions/*`, `github/*`) 和第一方 (`OpenHands/*`) 参考文献目前不受限制。 Dependabot 的 `github-actions` 生态系统仍然会影响固定的 SHA （以及后面的注释），因此固定不会阻止安全或版本更新。

- 当未设置环境变量时，`agent-server` 现在默认 `TMUX_TMPDIR` 为系统临时目录 (`openhands-agent-server-<pid>`) 下的每个进程目录。 这隔离了并发服务器实例之间的 tmux 套接字/清理，同时仍然遵守显式 `TMUX_TMPDIR` 覆盖。
- 基于 Git 的本地工作区所使用的对话工作树位于 `/tmp/conversation-worktrees/<conversation_id>/<repo_root.name>` 下；如果原始工作区指向仓库中的子目录，活动工作区应在工作树中保留该相对路径。

- 智能体-服务器Docker发布标签集中定义在`openhands-agent-server/openhands/agent_server/docker/build.py`中； `server.yml` 清单的发布应依据输出的各架构标签生成，使 SHA、分支和 Git 标签别名保持同步；同时保留工作区默认设置所使用的旧版 `latest-<variant>` 别名。
- `.github/workflows/server.yml` 中发布的智能体-服务器 Docker 映像必须将 `OPENHANDS_BUILD_GIT_SHA` 和 `OPENHANDS_BUILD_GIT_REF` 作为显式 `docker/build-push-action` 构建参数传递； 工作流程仅使用 `docker/build.py` 进行上下文/标签生成，因此这些运行时环境变量将保留在 Dockerfile `unknown` 默认值中。
- PyInstaller 打包的智能体服务器二进制文件应在 `openhands-agent-server/openhands/agent_server/agent-server.spec` 中复制 OpenHands 分发包元数据（`openhands-agent-server`、`openhands-sdk`、`openhands-tools`、`openhands-workspace`），否则发布的二进制镜像中，通过 `importlib.metadata` 查询 `/server_info` 版本时可能回退到 `unknown`。
- 智能体-服务器延迟初始化（热池/休眠模式）由 `Config.deferred_init` (env `OH_DEFERRED_INIT`) 驱动。 `openhands-agent-server/openhands/agent_server/init_router.py`中的`InitService`拥有休眠→初始化→就绪转换，并且仅当`deferred_init=True`时才在`app.state.init_service`上注册； 添加到 `/api/*` 路由器的 `require_initialized` 依赖项返回 503，而不返回 `ready`。 `POST /api/init` 的引导身份验证使用现有的 `secret_key`（`X-Init-API-Key` 请求头）；编排器已持有该密钥并将其用于加密，而初始化请求体中的用户运行时配置到达后，该密钥会被覆盖。 智能体服务器的 5xx 异常处理器会改写 503 响应中的 `detail`，因此预热池编排器探测休眠状态时应依据 HTTP 状态码，而不是响应体。


- 自动标题生成不应从新接收的 `MessageEvent` 触发的后台任务中重新读取 `ConversationState.events`； 从传入事件中同步提取消息文本，然后重用共享标题助手（`extract_message_text`、`generate_title_from_message`）以避免持久化顺序竞争。
- `RemoteConversation.generate_title()` 现在会协调远程事件，并复用共享的本地 `generate_conversation_title(...)` 辅助函数，不再调用已移除的已弃用智能体服务器 `/generate_title` REST 路由；因此，无须仅用于传输层的兼容性端点，仍可显式生成远程标题。


- 远程工作区 git 操作应调用 `/api/git/changes` 和 `/api/git/diff` 通过 `path` 带斜杠规范化字符串的查询参数。 建立那些 URLs 与 `pathlib.Path` 泄露主机平台分隔符，并破坏 Windows 路径。 现在，grep 工具更喜欢 `rg`, then system `grep`, then Python; grep 实现和  SDK终端命令兼容性回退方案应该保持这种顺序。 对于grep的兼容性， Python  回退方案应该默认隐藏 dotfiles，但仍然允许显式设置 `include` 像 glob 表面文件一样 `.env`, matching ripgrep. 对于全局一致性，任何符号链接保留回归测试应该强制执行 Python  回退方案路径，因为 ripgrep 可用性变化是否会影响回退方案实现运行在所有地方。
- 路径辅助函数应按用途分开：`is_absolute_path_source()` 用于检测跨平台源代码或传输格式中的路径语法；本地文件系统写入和校验（例如文件编辑器）则应使用主机原生的绝对路径语义，避免 POSIX 将 Windows 驱动器路径静默接受为可创建的文件。
- 工具可用性过滤应通过 `openhands-sdk/openhands/sdk/tool/registry.py` 中的 `list_usable_tools()` 实现：它保留注册顺序，并默认工具可用，除非工具提供了可调用的 `is_usable()`。 Chromium 检测等环境相关检查应放在具体工具类（`BrowserToolSet.is_usable()`）中；智能体服务器的 `/server_info` 等接口应使用注册表辅助函数，而不是重新实现逐工具过滤。
- Pydantic机密现场帮手住在`openhands-sdk/openhands/sdk/utils/pydantic_secrets.py`。 `serialize_secret()` 句柄序列化（密码/`expose_secrets`/默认Pydantic掩码）； `validate_secret()` 处理反序列化（密码解密，已编辑/空 → `None`）； `is_redacted_secret()` 检查哨兵值； `REDACTED_SECRET_VALUE` 是规范的哨兵值字符串。 对于值均为机密的 `dict[str, str]` 字段，将每个值包装在 `SecretStr` 中，并为每个值调用 `serialize_secret`（请参阅 `LookupSecret._serialize_secrets`）。 不要在字段序列化器中手动滚动脱敏逻辑。
- 智能体-server 持久化通过使用 `_SecretProbeCipher` (`persistence/models.py`) 执行真实的 Pydantic 机密-序列化管道来检测设置或机密载荷是否包含值。 不要用硬编码的字段列表或递归遍历 `SecretStr` 来替代此机制：`AgentContext.secrets` 等字段存储的是普通字符串，仅在其序列化器内部才会携带机密。

- `LookupSecret` 标准化无主机 URLs against `OH_INTERNAL_SERVER_URL` 已被设置为 `openhands-agent-server.__main__` 从绑定的主机/端口重写通配符绑定，否则回退到  `http://127.0.0.1:8000`所以相对机密  URLs 可以安全地针对当前智能体服务器实例。




<a id="package-specific-guidance"></a>

## 各包专用指南
当检查或修改代码时，读取最近的 AGENTS 文件以查找包含已更改文件的 package(s)。 如果 PR 跨越多个包，请查阅每个相关的包级别 AGENTS.md。

- SDK: [openhands-sdk/openhands/sdk/AGENTS.md](openhands-sdk/openhands/sdk/AGENTS.md)
- 子智能体：[openhands-sdk/openhands/sdk/subagent/AGENTS.md](openhands-sdk/openhands/sdk/subagent/AGENTS.md)
- 工具：[openhands-tools/openhands/tools/AGENTS.md](openhands-tools/openhands/tools/AGENTS.md)
- 工作区：[openhands-workspace/openhands/workspace/AGENTS.md](openhands-workspace/openhands/workspace/AGENTS.md)
- Agent Server: [openhands-agent-server/AGENTS.md](openhands-agent-server/AGENTS.md)

<a id="api-compatibility-pointers"></a>

## API 兼容性参考

- 对于 SDK Python API 弃用/删除政策，请阅读
  [openhands-sdk/openhands/sdk/AGENTS.md](openhands-sdk/openhands/sdk/AGENTS.md).
  移除公开 API 时，必须提供弃用元数据，移除目标至少应在 `deprecated_in` 之后**5 次次版本发布**；对 SDK API 进行不兼容变更时，至少需要进行一次 **MINOR** 级别的SemVer升级。
- SDK API 不兼容检查器应将 Pydantic 中 `Field(...)` 声明仅涉及元数据的变更视为兼容变更，包括添加、删除或编辑 `description`、`title`、`examples`，
  `json_schema_extra` 和 `deprecated` kwargs。
- 公开 SDK 的 `Field(default=...)` 变更与移除项或结构性的API不兼容变更分开处理：API 不兼容检查工作流应将其报告为行为兼容性变更，自动为 PR 添加绿色 `release-note-required` 标签，而发布工作流应将带该标签的 PR 放在自动生成的GitHub发布说明开头。
- 对于公开 SDK 的 `Field(default=...)` 变更，API 不兼容检查工作流应保留两个比较视角：与最新发布的 PyPI 基线比较，用于兼容性报告；同步 `release-note-required` 标签或 PR 评论前，则与 PR 的基准引用比较，避免无关的后续 PR 因已合并但尚未发布的默认值变更而被重新标记。


- SDK API 不兼容检查器会先对引号内的字面换行进行转义，再将字符串化的 `Field(...)` 值解析为 Python 表达式进行比较； 这避免了 False 对包含嵌入引号（如 `'security_policy.j2'`）的多行描述的肯定。
- 对于公共 REST APIs，请阅读
  [openhands-agent-server/AGENTS.md](openhands-agent-server/AGENTS.md).
  REST 合同中断需要弃用通知和跑道
  **5 次版本发布** 在删除旧合同或签订合同之前
  不兼容的强制更换。

<DEV_SETUP>
- 确保您`make build`首先配置依赖项
- 我们使用预提交挂钩 `.pre-commit-config.yaml`，其中包括：
  - 通过 Pyright 进行类型检查
  - 静态检查并使用 Ruff (`ruff-check`, `ruff-format`) 加 `pycodestyle` 进行格式化
  - `yamlfmt` 为 YAML
  - 特定于仓库的门：`check-import-rules`、`check-tool-registration`
- 绝不使用 `mypy`!
- 执行不提交全部文件，只需提交您已更改的相关文件即可！
- 在每条提交消息中，您应该添加“共同创作者：OpenHands <openhands@all-hands.dev>”
- 您可以使用 `uv run pytest` 运行 pytest

<a id="instruction-for-fixing-e501-line-too-long"></a>

# 修复“E501行太长”的说明

- 如果它只是代码，您可以对其进行修改，使其跨越多行。
- 如果是单行字符串，可以通过执行 "ABC" -> ("A"\n"B"\n"C") 将其分解为多行字符串
- 如果是长的多行字符串（e.g.,文档字符串），则添加`# noqa: E501`之后结尾的“”。 您应该绝不 ADD IT INSIDE 文档字符串。 E501 是 Ruff 静态检查规则，因此 `# noqa: E501` 是抑制它的规则 - `# type: ignore` 是 Pyright 指令，对 E501 没有影响。


</DEV_SETUP>

<PR_ARTIFACTS>
<a id="pr-specific-evidence-documents"></a>

# PR 专用证据文档

根据存储库策略，`.pr/` 目录是故意临时的：
`PR Artifacts` 工作流程 (`.github/workflows/pr-artifacts.yml`) 将其视为仅限 PR 的审阅者上下文。 PR 合并到 `main` 后，工作流将打开或更新清理 PR 以从 `main` 中删除目录。

如果 PR 需要设计文档、仅供开发使用的脚本，或其他不应长期保留在主分支的临时产物，应将它们存放在仓库根目录的 `.pr/` 目录中。

您还可以使用 `.pr/` 目录作为证据，例如日志、实时测试、实时测试摘要文件。

<a id="usage"></a>

## 用途

```bash
# 如果目录不存在则创建
mkdir -p .pr

# 添加您的 PR 特定文档
.pr/
├── design.md       # 设计决策和架构注释
├── analysis.md     # 调查或调试笔记
└── notes.md        # 任何其他 PR 特定内容
```

<a id="how-it-works"></a>

## 它是如何运作的

1. **通知**：当 `.pr/` 存在时，一条评论将发布到 PR 对话中，提醒审阅者
2. **合并后清理**：PR 合并到 `main` 后，工作流会打开或更新清理 PR 以从 `main` 中删除 `.pr/`

<a id="important-notes"></a>

## 重要提示

- 是否不将任何需要保留的内容放入 `.pr/` 中
- 开发期间 `.pr/` 检查通过（绿色 ✅） - 它仅发布通知，而不是阻塞错误
- 清理 PR 遵循 `main` 的正常审查和必要检查保护

<a id="when-to-use"></a>

## 何时使用

- 受益于书面设计原理的复杂重构
- 您想要记录调查的调试会话
- 需要临时规划文档的功能实现
- 临时脚本，旨在向审阅者表明该功能有效
- 任何有助于审阅者理解 PR 但不需要长期使用的分析
</PR_ARTIFACTS>

<PR_DESCRIPTION_HUMAN_CHECK>
<a id="human-only-pr-description-fields-in-pr-template"></a>

# PR 模板中的人工填写字段

打开 PR 时，使用存储库的 PR 模板进行描述。 的
PR 描述中的 `HUMAN:` 部分仅供人类贡献者使用。 AI 智能体必须不编辑、移动或删除该字段，仅设置占位符。 如果 PR 描述 CI 由于该字段缺失或为空而失败，请停止并要求人类用户用自己的话更新它。 如果该字段已由人工更新，请报告确切的验证器错误，而不是自行编辑。 </PR_DESCRIPTION_HUMAN_CHECK>


<REVIEW_HANDLING>
- 在采取行动之前，请严格评估每条评论意见。 并非所有反馈都值得实施：
  - 它是否修复了真正的错误或显着提高了清晰度？
  - 它是否符合项目的工程原则（简单性、可维护性）？
  - 建议的更改是否与收益成正比，或者是否增加了不必要的复杂性？
- 对于没有明确收益却增加冗长内容、为假想边界情况过度设计，或违背项目务实原则的建议，可以礼貌地拒绝。
- 处理（或决定不处理）内联审阅意见后，将相应的审阅线程标记为已解决。
- 解决线程之前，先回复评论，说明不采纳反馈的原因，或引用解决该问题的具体提交（e.g，提交 SHA）。
- 仅在推送修复或记录明确的决定后才优先解决线程。
- 使用 GitHub GraphQL API 回复并解决评论线程（见下文）。

<a id="resolving-review-threads-via-graphql"></a>

## 通过 GraphQL 标记审查讨论为已解决

如果存在未解决的审核线程，CI 检查 `Review Thread Gate/unresolved-review-threads` 将失败。 以编程方式解析线程：

1. 获取线程个 ID（替换 `<OWNER>`、`<REPO>`、`<PR_NUMBER>`）：
```bash
gh api graphql -f query='
{
  repository(owner: "<OWNER>", name: "<REPO>") {
    pullRequest(number: <PR_NUMBER>) {
      reviewThreads(first: 20) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { body }
          }
        }
      }
    }
  }
}'
```

2. 回复线程解释如何处理反馈：
```bash
gh api graphql -f query='
mutation {
  addPullRequestReviewThreadReply(input: {
    pullRequestReviewThreadId: "<THREAD_ID>"
    body: "Fixed in <COMMIT_SHA>"
  }) {
    comment { id }
  }
}'
```

3. 解决线程：
```bash
gh api graphql -f query='
mutation {
  resolveReviewThread(input: {threadId: "<THREAD_ID>"}) {
    thread { isResolved }
  }
}'
```

4. 获取失败的工作流运行 ID 并重新运行它：
```bash
# 从失败的检查中查找运行 ID URL，或使用：
gh run list --repo <OWNER>/<REPO> --branch <BRANCH> --limit 5

# 重新运行失败的作业
gh run rerun <RUN_ID> --repo <OWNER>/<REPO> --failed
```
</REVIEW_HANDLING>


<CODE>
- 解决包依赖关系时避免像 `sys.path.insert` 这样的黑客技巧
- 尽可能使用现有的包/库，而不是自己实现。
- 避免使用#类型：忽略。 仅将其视为最后的手段。 大多数情况下，应通过改进类型注解、添加断言或调整代码与测试来解决问题，避免直接屏蔽类型检查器。
  - 除非绝对必要，否则请 AVOID 使用 # type:ignore[attr-defined]。 如果可以通过添加一些额外的断言语句来验证类型来解决该问题，那么更喜欢这种方法！
  - 对于像 # type:ignore[call-arg]: 如果你发现参数实际上不存在，不要尝试在测试中再次模拟对象它。 相反，只需将其删除即可。
- 除非绝对必要，否则避免进行内联导入（e.g.，循环依赖）。
- 避免使用 getattr/hasattr 保护判断；应通过明确的类型断言和正确的对象使用方式确保类型正确，让函数只接收预期的 Pydantic 模型或类型明确的输入。 与运行时形状检查相比，更喜欢类型提示和经过验证的模型。
- 更喜欢直接访问类型化属性。 如有必要，预先将输入转换为规范形状； 避免纯粹的假设回退方案。
- 在提交消息中使用真正的换行符； 不要写字面量“\n”。
- 评论政策：谨慎且有策略地撰写评论。 更喜欢通过清晰的命名和结构使代码不言自明，而不是添加散文。
  - 不要添加重复代码含义、总结周边差异或 PR，或叙述变更历史的注释，例如“以前执行 X，现在执行 Y”。 这类上下文应放在 PR 描述或提交说明中，而不是源代码里；`git blame` 和 PR 才是追溯*为什么*进行变更的权威依据。
  - 不要在注释中描述系统的非局部部分，例如其他模块、调用方或下游行为，除非已有机制保证这些描述保持同步。 这些评论会随波逐流并产生误导。
  - 当代码体现了确实不直观的内容时，应添加注释，例如不明显的不变量、绕过外部缺陷的措施、细微的顺序或加锁要求，以及读者无法仅从代码中推断出的有意取舍。
  - 如有疑问，更愿意重组或重命名而不是发表评论。 修改 3 行代码不应产生 19 行注释；如果确实需要如此详细的说明，应将解释放在 PR 描述中。

</CODE>

<TESTING>
- 之后你编辑一个文件，你应该通过 `uv run pre-commit run --files [filepath]` 在该文件上运行预提交挂钩，以确保你没有破坏它。
- 不要编写 TOO MUCH 测试，您应该编写足以覆盖边缘情况的测试。
- 检查我们如何在 .github/workflows/tests.yml 中执行测试
- 将单元测试放在`tests/`中对应的域文件夹下（e.g.、`tests/sdk`、`tests/tools`、`tests/workspace`）。 例如，对 `openhands-sdk/openhands/sdk/tool/tool.py` 的更改应包含在 `tests/sdk/tool/test_tool.py` 中。
- 不要写 TEST  CLASSES 除非绝对必要！
- 如果您发现自己在准备模拟对象、加载数据等方面重复逻辑，这些逻辑应该是conftest.py中的测试夹具！
- 请仅测试当前代码库中实现的逻辑。 不要测试此存储库中未实现的功能（e.g.、BaseModel.model_dumps()）。
- 应断言可观察的行为，避免针对源文本、静态实现列表、私有辅助函数或状态、通用框架行为、完整的默认值与导出项镜像，或模拟对象的连接方式编写断言。 测试应该能够在保留行为的重构中幸存下来。
- 修改提示词模板、工具描述或智能体决策逻辑时，应添加 `integration-test` 标签，以触发集成测试并确认基准测试性能没有受到意外影响。

<a id="stress-tests"></a>

# 压力测试

`tests/agent_server/stress/` 包含智能体服务器的选择加入压力/规模套件，通过 `stress` pytest 标记从默认集合中排除。 使用`uv run pytest -m stress`运行。 请参阅[openhands-agent-server/AGENTS.md](openhands-agent-server/AGENTS.md)以获取有关运行、基础设施和添加新压力测试的详细信息。

<a id="behavior-tests"></a>

# 行为测试

`tests/integration/tests/` 中的行为测试（前缀 `b##_*`）旨在验证智能体在现实场景中表现出所需的行为。 这些测试与功能测试（前缀 `t##_*`）不同，并且有特定的要求。 同一目录还包含 `a##_*`（格式错误的工具使用/工具结果历史记录）和 `c##_*` (上下文压缩器) 测试； 只有 `b`/`t` 前缀驱动 `BEHAVIOR_TESTS.md` 中描述的行为与集成分类。

在添加或修改行为测试之前，请查看 `tests/integration/BEHAVIOR_TESTS.md` 以获取最新的工作流程、期望和示例。 </TESTING>

<AGENT_TMP_DIRECTORY>
<a id="agent-temporary-directory-convention"></a>

# 智能体临时目录约定

当工具需要存储观测结果个文件（e.g.、浏览器会话记录、任务跟踪器数据）时，请使用 `.agent_tmp` 作为目录名称以保持一致性。

浏览器会话记录工具将记录保存到`.agent_tmp/browser_observations/recording-{timestamp}/`（请参阅`openhands-tools/openhands/tools/browser_use/definition.py`中的`BROWSER_RECORDING_OUTPUT_DIR`）。

此约定确保工具生成的观测结果文件存储在可预测的位置，可以轻松地：
- 添加到 `.gitignore`
- 智能体个会话后已清理
- 被识别为智能体生成的工件

注意：这与用于会话状态持久化的 `persistence_dir` 不同。
</AGENT_TMP_DIRECTORY>

<REPO>
<PROJECT_STRUCTURE>
- 这是一个单体仓库，带有 `uv` 管理的 Python 工作区（存储库根目录下的单个 `uv.lock`）和 `clients/typescript/` 下单独管理的 npm 包。 Python 可分发包是：`openhands-sdk/` (SDK)、`openhands-tools/`（内置工具）、`openhands-workspace/`（工作区 impls）和 `openhands-agent-server/`（服务器运行时）。
- `clients/typescript/` 包含与浏览器兼容的 TypeScript 客户端，以及它自己的 `package-lock.json`、npm 脚本和 Vitest 测试。
- `examples/` 包含可运行模式； `tests/` 按域（`tests/sdk`、`tests/tools`、`tests/workspace`、`tests/agent_server` 等）划分。
- Python命名空间是跨包的`openhands.*`； 将新模块保留在 `tests/` 下的匹配包和镜像测试路径中。
</PROJECT_STRUCTURE>

<QUICK_COMMANDS>
- 设置开发环境：`make build`（运行`uv sync --dev`并安装预提交； 要求 uv >= 0.8.13)
- Lint/格式：`make lint`、`make format`
- 运行 Python 个测试：`uv run pytest`
- 设置并验证 TypeScript 客户端：`cd clients/typescript && npm ci && npm run lint && npm run build && npm test`
- 运行智能体-server 压力测试：`uv run pytest -m stress`（请参阅 [openhands-agent-server/AGENTS.md](openhands-agent-server/AGENTS.md)）
- 构建智能体-服务器：`make build-server`（输出：`dist/agent-server/`）
- 清理缓存：`make clean`
- 运行 SDK 个示例：请参阅 [openhands-sdk/openhands/sdk/AGENTS.md](openhands-sdk/openhands/sdk/AGENTS.md)。
- 示例工作流程运行 `uv run pytest tests/examples/test_examples.py --run-examples`； 每个成功的示例必须将 `EXAMPLE_COST: ...` 行打印到 stdout（对于非 LLM 示例，请使用 `EXAMPLE_COST: 0`）。
- `examples/` 中的线性演练应使用顶级代码流 (e.g. `with` 块，裸语句）而不是将整个示例包装在 `def main()` 中。 具有参数驱动分支的 CLI 样式示例可以使用 `main()` 入口。
- 通过 `plugins=[...]` 传入的对话插件会在第一次调用 `send_message()` 或 `run()` 时延迟加载，因此示例代码应在首次交互后再检查插件添加的技能或 `resolved_plugins`。
</QUICK_COMMANDS>

<REPO_CONFIG_NOTES>
- Ruff：`line-length = 88`、`target-version = "py313"`（参见`pyproject.toml`）。
- Ruff 忽略 `tests/**/*.py` 下的 `ARG`（未使用的参数）以允许 pytest 测试夹具。
- 存储库指南位于项目根目录 AGENTS.md 中（作为第三方技能文件加载）。
</REPO_CONFIG_NOTES>

<KNOWN_RACES_AND_GOTCHAS>
- **`RemoteConversation._wait_for_run_completion`和停止钩子**：每个字段WebSocket`FINISHED`状态事件是*提示*，而不是权威终止。 服务器端 `LocalConversation.run` 循环会在每次迭代结束时释放状态锁，因此 `agent.step()` 设置的 `FINISHED` 状态会先对客户端可见，然后才在*下一次*循环迭代中执行停止钩子（`hook_processor.run_stop`）。 如果停止钩子返回 rc=2（拒绝停止），状态将翻转回 RUNNING 并且智能体进行另一次迭代。 因此，客户端的 `_wait_for_run_completion` 必须 ** 而不是 ** 在第一个 WS 交付的 FINISHED 上返回。 应以运行结束后的完整状态 WebSocket 快照为准； 如果该快照丢失，则基于时间的硬回退方案路径 (`TERMINAL_HARD_FALLBACK_SECS = 30.0`) 在连续 30 秒后接受 REST 确认的终端状态。 ERROR/STUCK仍然通过`_handle_conversation_status`立即加注。 根据经验，这导致智能体在程序台重试-16 上的钩子块之后仅消耗 0-1 次迭代； 修复已在`feat/programbench`中发布。
- **钩子事件与`state.events`**：`HookExecutionEvent`是通过`hook_processor.original_callback`（链接的`_on_event`）发出的，因此当允许运行完成时，它*应该*落在`state.events`中。 但上述 WS-FINISHED 竞态曾导致客户端在服务器端执行钩子求值*之前*就生成 `list(conversation.state.events)` 快照，因此 `output.jsonl` 历史中可能缺少钩子事件，而 `/workspace/conversations/.../events/` 下磁盘上的已持久化事件却包含它们；这种差异有助于追查该竞态是否发生。
</KNOWN_RACES_AND_GOTCHAS>

</REPO>

<a id="dependency-release-age-policy"></a>

## 依赖版本发布时长规则

- 发布后至少等待 7 天，然后再添加或更新第三方 npm 或 PyPI 版本，包括传递锁定文件更改。 仅每周更新计划并不能强制执行此最低年龄。
- 保留 Dependabot `cooldown.default-days: 7` 以进行 npm 和 Python 版本更新，并保留配置的 `tool.uv.exclude-newer = "7 days"`。 现有命名的第一方异常不会免除其第三方依赖性。 不要添加广泛的豁免或禁用截止以使解析器成功。
- 从 npm 或 PyPI 元数据（或 `uv.lock` 中的工件 `upload-time`）验证确切版本的发布/上传时间，而不是包的创建日期。 如果无法确定年龄，请报告缺失的证据而不是猜测。
- 安全更新可以绕过 Dependabot 冷却时间。 紧急异常需要明确的维护者批准，并记录在 PR 中，包括包、版本、建议/原因和发布时间。 智能体不得给予自己例外。
- 使用已提交的锁进行可重复安装； 在提交锁更新之前检查新解决的工件。
