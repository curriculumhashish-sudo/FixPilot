// 生成的文件。 不要手动编辑。
// 来源：ghcr.io/openhands/agent-server：1.58.2-Python
// 重新生成： npm rungenerate:智能体-server-API 该文件由 @hey-api/openapi-ts 自动生成
//

export type ClientOptions = {
  baseUrl: `${string}://${string}` | (string & {});
};

/**
 * ACPAgent
 *
 * 智能体委托给 ACP 兼容的子进程服务器。
 */
export type AcpAgentInput = {
  /**
   * ACP 参数
   *
   * ACP 服务器命令的附加参数
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 启动命令 ACP 请输出简体中文译文 e.g. ['npx', '-y', '@agentclientprotocol/claude-智能体-ACP']
   */
  acp_command: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留“文件内容”凭据机密，以便在启动子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 SDK 拥有该机制（在运行时 pod 中写入文件、设置环境变量、seed-if-absent）； 这些规格就是政策。 默认为内置支持的提供程序； 下游应用程序可以覆盖或扩展它以支持具有不同文件身份验证方案的其他ACP服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 ``HOME``。 当 True 和提供者被识别时，指向其 data-dir env var (``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR`` / ``HOME``; 参见 ``<persistence_dir>/acp/<provider>`` 处的 ``ACPProviderInfo.data_dir_env_var``）——使用相同的每个对话树具体化文件 - 机密。 ``SandboxGroupingStrategy != NO_GROUPING`` 该端点用于确保用户多个会话共享一个沙箱时的正确性，否则它们会同时在一组 CLI auth/config/cache/lock 文件上竞争（参见 #1019）。 默认关闭：每个对话一个沙箱，共享 HOME 已经是私有的，重新定位它会隐藏预先存在的交互式登录。 下游策略决定何时启用； SDK 拥有根所在的位置。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * ACP 服务器使用的模型 (e.g. “十四行诗”或“gpt-5.5”）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 如果为 None，则服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 呼叫处于不活动状态超时秒。 截止日期在每次更新后重置（ACP服务器，token，工具调用进度，使用），因此一个持续进展的智能体会一直运行，只要它继续进展。 提示词仅在这么多秒后才中止，根本没有任何活动。 当 ACP 服务器停止响应时，防止无限期挂起，而不终止合法的长时间运行的工作。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 恢复会话 ID
   *
   * 要恢复的可选显式 ACP 会话 ID。 设置后，优先于 ``state.agent_state`` 中的 id 已持久化，并用于调用 ACP 服务器上的 ``session/load``。 专为每次会话文件系统（因此``base_state.json``）在重新启动后无法保留的环境而设计（e.g。 云沙箱回收），但 ID 已镜像到其他地方的持久存储中。 如果服务器无法加载 ID，则回退到新会话。 被视为线路上的机密 — 拥有 id 足以恢复底层 ACP 会话，因此默认序列化会对其进行编辑； 当值必须跨越序列化边界时，传递 ``expose_secrets='plaintext'``（可信后端）或 ``expose_secrets='encrypted'`` 加密码（前端往返）。
   */
  acp_resume_session_id?: string | null;
  /**
   * ACP 服务器
   *
   * 提供商注册表  ACP  CLI this 智能体 runs (any ACP_PROVIDERS key，或者 'custom'。 None when the 智能体直接构建，而不是通过 ACPAgentSettings. 设置为 ACPAgentSettings.create_agent() from ACPAgentSettings.acp_server 因此，权威密钥会传递给智能体 — 于是，我们继续前进 ConversationInfo.agent — 因为在中的启动命令 acp_command 不可靠地反向映射到提供者。 仅供参考：消费者使用它来解析提供商品牌标签/型号列表； 的子进程仍然从这里启动 acp_command.
   */
  acp_server?: string | null;
  /**
   * ACP 会话模式
   *
   * 创建会话后设置的会话模式 ID。 如果为 None（默认），则从 ACP 服务器类型自动检测：“bypassPermissions”用于 claude-智能体-ACP，“智能体-full-access”用于 codex-ACP； 没有这种模式的提供者（pi-ACP）会跳过调用。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时以秒为单位 ACP 服务器启动：生成子进程、初始化/身份验证握手和 new_session()/load_session(). 与 acp_prompt_timeout 不同，这是一个硬截止时间而不是空闲截止时间，因为启动没有中间进度信号来重置它。 当 ACP 服务器在身份验证 (e.g. 已过期token），从未筹集资金。
   */
  acp_startup_timeout?: number;
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextInput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseInput | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseInput | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind?: 'ACPAgent';
  llm?: LlmInput;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInput;
  };
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   */
  tools?: Array<ToolInput>;
};

/**
 * ACPAgent
 *
 * 智能体委托给 ACP 兼容的子进程服务器。
 */
export type AcpAgentOutput = {
  /**
   * ACP 参数
   *
   * ACP 服务器命令的附加参数
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 启动命令 ACP 请输出简体中文译文 e.g. ['npx', '-y', '@agentclientprotocol/claude-智能体-ACP']
   */
  acp_command: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留“文件内容”凭据机密，以便在启动子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 SDK 拥有该机制（在运行时 pod 中写入文件、设置环境变量、seed-if-absent）； 这些规格就是政策。 默认为内置支持的提供程序； 下游应用程序可以覆盖或扩展它以支持具有不同文件身份验证方案的其他ACP服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 ``HOME``。 当 True 和提供者被识别时，指向其 data-dir env var (``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR`` / ``HOME``; 参见 ``<persistence_dir>/acp/<provider>`` 处的 ``ACPProviderInfo.data_dir_env_var``）——使用相同的每个对话树具体化文件 - 机密。 ``SandboxGroupingStrategy != NO_GROUPING`` 该端点用于确保用户多个会话共享一个沙箱时的正确性，否则它们会同时在一组 CLI auth/config/cache/lock 文件上竞争（参见 #1019）。 默认关闭：每个对话一个沙箱，共享 HOME 已经是私有的，重新定位它会隐藏预先存在的交互式登录。 下游策略决定何时启用； SDK 拥有根所在的位置。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * ACP 服务器使用的模型 (e.g. “十四行诗”或“gpt-5.5”）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 如果为 None，则服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 呼叫处于不活动状态超时秒。 截止日期在每次更新后重置（ACP服务器，token，工具调用进度，使用），因此一个持续进展的智能体会一直运行，只要它继续进展。 提示词仅在这么多秒后才中止，根本没有任何活动。 当 ACP 服务器停止响应时，防止无限期挂起，而不终止合法的长时间运行的工作。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 恢复会话 ID
   *
   * 要恢复的可选显式 ACP 会话 ID。 设置后，优先于 ``state.agent_state`` 中的 id 已持久化，并用于调用 ACP 服务器上的 ``session/load``。 专为每次会话文件系统（因此``base_state.json``）在重新启动后无法保留的环境而设计（e.g。 云沙箱回收），但 ID 已镜像到其他地方的持久存储中。 如果服务器无法加载 ID，则回退到新会话。 被视为线路上的机密 — 拥有 id 足以恢复底层 ACP 会话，因此默认序列化会对其进行编辑； 当值必须跨越序列化边界时，传递 ``expose_secrets='plaintext'``（可信后端）或 ``expose_secrets='encrypted'`` 加密码（前端往返）。
   */
  acp_resume_session_id?: string | null;
  /**
   * ACP 服务器
   *
   * 提供商注册表  ACP  CLI this 智能体 runs (any ACP_PROVIDERS key，或者 'custom'。 None when the 智能体直接构建，而不是通过 ACPAgentSettings. 设置为 ACPAgentSettings.create_agent() from ACPAgentSettings.acp_server 因此，权威密钥会传递给智能体 — 于是，我们继续前进 ConversationInfo.agent — 因为在中的启动命令 acp_command 不可靠地反向映射到提供者。 仅供参考：消费者使用它来解析提供商品牌标签/型号列表； 的子进程仍然从这里启动 acp_command.
   */
  acp_server?: string | null;
  /**
   * ACP 会话模式
   *
   * 创建会话后设置的会话模式 ID。 如果为 None（默认），则从 ACP 服务器类型自动检测：“bypassPermissions”用于 claude-智能体-ACP，“智能体-full-access”用于 codex-ACP； 没有这种模式的提供者（pi-ACP）会跳过调用。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时以秒为单位 ACP 服务器启动：生成子进程、初始化/身份验证握手和 new_session()/load_session(). 与 acp_prompt_timeout 不同，这是一个硬截止时间而不是空闲截止时间，因为启动没有中间进度信号来重置它。 当 ACP 服务器在身份验证 (e.g. 已过期token），从未筹集资金。
   */
  acp_startup_timeout?: number;
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextOutput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseOutput | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseOutput | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind: 'ACPAgent';
  llm?: LlmOutput;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  };
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   */
  tools?: Array<OpenhandsSdkToolSpecTool>;
};

/**
 * ACPAgentProfile
 *
 * ``agent_kind="acp"`` 配置文件 — 命名 ACP 后端，不存储凭据。
 *
 * 没有 ``llm_profile_ref`` 也没有嵌入的凭据：ACP
 * 子进程进行自己的模型调用，以及提供者的凭据
 * (env-var name) 是通过：attr:`acp_server` 派生的
 * ：数据：`~openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 注册表。 的
 * 价值取决于对话机密渠道，而不是个人资料。
 */
export type AcpAgentProfile = {
  /**
   * ACP 参数
   *
   * 附加到 ACP 服务器命令的其他参数。
   */
  acp_args?: Array<string> | null;
  /**
   * ACP 命令
   *
   * 用于启动 ACP 子进程的可选显式命令。 留空以使用 ``acp_server`` 的默认值。
   */
  acp_command?: string | null;
  /**
   * ACP 型号
   *
   * ACP 服务器的型号标识符 (e.g. 'claude-opus-4-8'). 留空以让服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 次往返不活动超时（秒）； 每次服务器更新时都会重置。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 服务器
   *
   * 要启动哪个 ACP 兼容后端。 提供者的凭据环境变量名称是通过 ACP_PROVIDERS 注册表派生而来。
   */
  acp_server?: 'claude-code' | 'codex' | 'gemini-cli' | 'kimi-code' | 'pi' | 'opencode' | 'custom';
  /**
   * ACP 会话模式
   *
   * 会话模式 ID (e.g. 'bypassPermissions'). 留空以从 ACP 服务器类型自动检测。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时（秒）用于 ACP 服务器启动：生成、初始化/身份验证和 new_session()/load_session().
   */
  acp_startup_timeout?: number;
  /**
   * 智能体种类
   *
   * ``AgentProfile`` 联合的鉴别器。 ``'acp'`` 选择 ACP 委托智能体。
   */
  agent_kind?: 'acp';
  /**
   * 身份证号
   *
   * 此配置文件的稳定出处句柄。 对话记录了这个UUID； 即使配置文件被重命名，它也永远不会改变。
   */
  id?: string;
  /**
   * MCP 服务器参考
   *
   * 要公开用户的哪些全局配置的 MCP 服务器。 null = 全部； [] = None; 非 null 列表 = 指定键的过滤器。
   */
  mcp_server_refs?: Array<string> | null;
  /**
   * 名称
   *
   * 配置文件选择器中显示的面向人的可重命名键。
   */
  name: string;
  /**
   * 修订版
   *
   * 单调修订计数器，每次保存的编辑都会发生碰撞。
   */
  revision?: number;
  /**
   * 模式版本
   */
  schema_version?: number;
  /**
   * 机密参考文献
   *
   * 用户保存的哪个机密要公开给这个智能体。 null=全部； [] = None; 非 null 列表 = 指定键的过滤器。 严格：不添加任何内容。 ACP 配置文件必须列出自己的提供者凭据才能接收它。
   */
  secret_refs?: Array<string> | null;
};

/**
 * ACPAgentSettings
 *
 * ACP（智能体客户端协议）智能体的设置。
 *
 * ``create_agent()`` 返回一个：class:`ACPAgent` ，该类委托给
 * 子进程 ACP 服务器。 ACP服务器管理自己的系统提示词，
 * 工具、MCP 和（主要）LLM 调用； 这些字段来自
 * :class:`OpenHandsAgentSettings` 不适用于此处。
 *
 * :attr:`acp_model` 是模型标识。 创建的``ACPAgent``保持其
 * 自己的指标LLM，因此标题生成可以告诉它永远不可调用。
 * 提供商凭据参与对话机密频道
 * (``request.secrets`` / ``agent_context.secrets`` → ``state.secret_registry``)
 * 由提供者的环境变量名称 (:attr:`api_key_env_var`) 键入。
 */
export type AcpAgentSettings = {
  /**
   * ACP 参数
   *
   * 附加到 ACP 服务器命令的其他参数。
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 用于启动 ACP 子进程的可选显式命令。 留空以使用：attr:`acp_server` (e.g. ``npx -y @agentclientprotocol/claude-agent-acp`` 为 ``claude-code``）。 当：attr:`acp_server`为``'custom'``时必须设置。
   */
  acp_command?: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留的“文件内容”凭据机密 SDK 在启动 ACP 子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 默认为内置支持的提供程序； 覆盖以支持具有不同文件身份验证方案的其他 ACP 服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 HOME。 转发到：attr:`~openhands.sdk.agent.ACPAgent.acp_isolate_data_dir`; 默认关闭。 当多个对话共享一个沙箱时从部署应用程序启用（请参阅#1019）。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * 要使用的 ACP 服务器的型号标识符 (e.g. ``'sonnet'``或``'gpt-5.5'``）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 留空以让服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 次往返的不活动状态超时（秒）。 ACP 服务器的每次更新都会重置截止日期，因此稳定进展的智能体会继续运行； 提示词仅在这么多秒后才会中止，根本没有任何活动。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 服务器
   *
   * 要启动哪个 ACP 兼容后端。 每个选择都映射到默认的子进程命令（请参阅 ``acp_command`` 进行覆盖）。
   */
  acp_server?: 'claude-code' | 'codex' | 'gemini-cli' | 'kimi-code' | 'pi' | 'opencode' | 'custom';
  /**
   * ACP 会话模式
   *
   * 会话模式 ID (e.g. ``bypassPermissions``). 留空以从 ACP 服务器类型自动检测。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时（秒）用于ACP服务器启动：启动子进程，初始化/认证握手，以及new_session()/load_session().（硬性截止日期），不同于acp_prompt_timeout，因为启动没有中间进度信号来重置它。
   */
  acp_startup_timeout?: number;
  /**
   * 提示词-仅上下文用于 ACP 服务器。 这里的``secrets``被通告到智能体（名称/描述）并通过``state.secret_registry``到达子进程环境：``LocalConversation``种子``agent_context.secrets``在对话初始化时进入注册表（低于``request.secrets``），因此调用者在Python之外构建请求（e.g。 canvas-local) 也被覆盖，而不仅仅是 ``create_request`` 路径。 提供者凭据属于此处（或在 ``request.secrets`` 中），由提供者的环境变量名称键入。
   */
  agent_context?: AgentContextInput | null;
  /**
   * 智能体种类
   *
   * ``AgentSettings`` 联合的鉴别器。 ``'acp'`` 选择 ACP 委托智能体。
   */
  agent_kind?: 'acp';
  /**
   * MCP 配置
   *
   * MCP 向提供的服务器 ACP  子进程。 Unlike the OpenHands  智能体 — 这些成为在进程中的 MCP 工具 —— 服务器被转发到  ACP 在会话创建时，服务器拥有连接。 只有当时，远程（HTTP/HTTPS）服务器才会被转发 ACP 服务器支持那个传输层; stdio 服务器（在运行时内运行）始终被转发。
   */
  mcp_config?: {
    [key: string]: McpServerInput;
  };
  /**
   * 模式版本
   */
  schema_version?: number;
};

/**
 * ACPFileSecretSpec
 *
 * 从保留的“文件内容”机密到凭据的声明性映射
 * 文件 ACP 子进程进行身份验证。
 *
 * 一些供应商阅读他们的凭据从一个 *磁盘上的文件* 而不是
 * 环境变量：Codex 读取 ``$CODEX_HOME/auth.json``； Gemini (Vertex AI) 读取
 * ``GOOGLE_APPLICATION_CREDENTIALS`` 指向的服务帐户 JSON。 的
 * 用户提供凭据作为粘贴的 blob — 名为的保留机密
 * :attr:`secret_name` — 和：class:`~openhands.sdk.agent.ACPAgent` 实现
 * 它到对话的持久每个对话根下的：attr:`filename`
 * (seed-if-absent)，然后设置：attr:`env_var` 以便 CLI 可以找到它。
 *
 * 物化已关闭：attr：`secret_name`（不是启动命令），
 * 因此，只要保留，自定义或别名 ``acp_command`` 仍然有效
 * 提供机密。
 *
 * SDK拥有*机制*（在runtime pod中写入文件，设置
 * 环境变量、种子（如果不存在）、权限）； * 政策 * — 其中机密映射
 * CLIs 对应的文件在这些规范中。 内置默认值
 * 覆盖支持的提供程序，但下游应用程序可以覆盖
 * :attr:`~openhands.sdk.agent.ACPAgent.acp_file_secrets` 支持其他 ACP
 * 具有不同文件身份验证方案的服务器，无需 SDK 更改。
 */
export type AcpFileSecretSpec = {
  /**
   * 环境指向
   */
  env_points_to?: 'dir' | 'file';
  /**
   * 环境变量
   */
  env_var: string;
  /**
   * 文件名
   */
  filename: string;
  /**
   * 机密姓名
   */
  secret_name: string;
  /**
   * 子目录
   */
  subdir: string;
  /**
   * 如果未设置则发出警告
   */
  warn_if_unset?: Array<string>;
};

/**
 * ACPModelDiscovery
 *
 * 在任何对话之前，ACP 服务器报告新会话的内容。
 */
export type AcpModelDiscovery = {
  /**
   * 智能体姓名
   *
   * 服务器名称来自 ``initialize``。
   */
  agent_name?: string | null;
  /**
   * 智能体版本
   *
   * 服务器版本来自``initialize``。
   */
  agent_version?: string | null;
  /**
   * 可用型号
   *
   * 服务器为给定的凭据提供的模型。 当服务器不报告任何内容时为空。
   */
  available_models?: Array<AcpModelInfo>;
  /**
   * 当前型号 ID
   *
   * 请求 None 时服务器选择的模型 - 对于给定的凭据，它自己的默认值。 可能是不透明的别名，例如 ``"default"``； 将其与 ``available_models`` 匹配作为标签。
   */
  current_model_id?: string | null;
  /**
   * 设置服务器无法启动会话的时间。
   */
  error?: AcpModelDiscoveryError | null;
  /**
   * 支持运行时模型切换
   *
   * 对话是否可以在这些模型之间实时切换。
   */
  supports_runtime_model_switch?: boolean;
};

/**
 * ACPModelDiscoveryError
 *
 * 为什么 ACP 服务器无法报告其型号。
 */
export type AcpModelDiscoveryError = {
  /**
   * 代码
   *
   * 与对话冷启动 ``ConversationErrorEvent`` 相同的代码：``ACPAuthRequired``、``ACPStartupTimeout``、``ACPSpawnError`` 或 ``ACPInitError``。
   */
  code: string;
  /**
   * 详情
   *
   * 人类可读、无机密的原因。
   */
  detail: string;
};

/**
 * ACPModelDiscoveryRequest
 */
export type AcpModelDiscoveryRequest = {
  /**
   * ACP智能体问。 仅使用发射场； ``acp_model``、MCP 服务器和智能体上下文被忽略。
   */
  agent_settings: AcpAgentSettings;
  /**
   * 刷新
   *
   * 再次询问服务器而不是重复使用结果。
   */
  refresh?: boolean;
  /**
   * 机密
   *
   * 凭据对于服务器，其形状与对话开始请求的 ``secrets`` 相同（通常 ``LookupSecret`` 引用该服务器存储的机密）。
   */
  secrets?: {
    [key: string]: SecretSourceInput;
  };
};

/**
 * ACPModelInfo
 *
 * ACP 服务器为会话提供的一种模型。
 *
 * ACP 协议 ``ModelInfo`` 的标准化、稳定的镜像。 的
 * 协议 ``models`` 功能被标记为 **UNSTABLE**，因此我们重新映射它
 * 在 SDK 边界处转换为我们自己的类型，而不是重新序列化
 * 供应商 ``acp.schema`` 类型到智能体服务器的公共 API — 客户端
 * 无论上游协议变动如何，都能获得稳定的形状。
 *
 * 携带客户端渲染选择器和解析问题所需的一切
 * ``current_model_id`` 到显示标签 * 本身 *； the SDK deliberately
 * 没有名字策展。
 */
export type AcpModelInfo = {
  /**
   * 描述
   *
   * 服务器提供的可选较长描述。
   */
  description?: string | null;
  /**
   * 型号 ID
   *
   * 服务器分配的模型标识符。 可能是具体的（e.g. ``"gpt-5.6"``) 或不透明别名 (e.g. ``"default"``, ``"auto"``). 这是要传递回服务器以切换到此模型的值。
   */
  model_id: string;
  /**
   * 名称
   *
   * 人类可读的标签，e.g。 ``"GPT-5.5"``.
   */
  name?: string | null;
};

/**
 * ACPToolCallEvent
 *
 * 表示 ACP 服务器执行的工具调用的事件。
 *
 * 从 ACP 捕获工具名称、输入、输出和状态
 * ``ToolCallStart`` / ``ToolCallProgress`` 通知，以便他们可以
 * 显示在 OpenHands 事件流和可视化工具中。
 *
 * 这 * 不是 *， ``LLMConvertibleEvent`` — ACP 工具调用不是
 * 参与LLM消息转换。
 */
export type AcpToolCallEvent = {
  /**
   * 内容
   */
  content?: Array<unknown> | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 是错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'ACPToolCallEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 原始输入
   */
  raw_input?: unknown | null;
  /**
   * 原始输出
   */
  raw_output?: unknown | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 状态
   */
  status?: string | null;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 标题
   */
  title: string;
  /**
   * 工具调用身份证号
   */
  tool_call_id: string;
  /**
   * 工具种类
   */
  tool_kind?: string | null;
};

/**
 * APIBasedCritic
 */
export type ApiBasedCriticInput = {
  /**
   * 智能体问题标签
   */
  agent_issue_labels?: Array<string>;
  /**
   * API 钥匙
   *
   * API 用于通过 vLLM 服务进行身份验证的密钥
   */
  api_key: string;
  /**
   * 有成功标签
   *
   * 模型是否预测索引 0 处的成功标签
   */
  has_success_label?: boolean;
  /**
   * 基础设施标签
   */
  infra_labels?: Array<string>;
  /**
   * 问题门槛
   *
   * APIBasedCritic特定的概率阈值，用于智能体问题标签，以触发迭代的细化。
   */
  issue_threshold?: number;
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind?: 'APIBasedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
  /**
   * 型号名称
   *
   * 使用的型号名称
   */
  model_name?: string;
  /**
   * 传递工具定义
   *
   * 是否将工具定义传递给模型
   */
  pass_tools_definitions?: boolean;
  /**
   * 情绪标签
   */
  sentiment_labels?: Array<string>;
  /**
   * 情绪图
   */
  sentiment_map?: {
    [key: string]: string;
  };
  /**
   * 服务器网址
   *
   * vLLM 分类服务的基础 URL
   */
  server_url?: string;
  /**
   * 超时秒
   *
   * 超时对模型的请求
   */
  timeout_seconds?: number;
  /**
   * 分词器名称
   *
   * HuggingFace 用于加载聊天模板的分词器名称
   */
  tokenizer_name?: string;
  /**
   * 用户跟进标签
   */
  user_followup_labels?: Array<string>;
};

/**
 * APIBasedCritic
 */
export type ApiBasedCriticOutput = {
  /**
   * 智能体问题标签
   */
  agent_issue_labels?: Array<string>;
  /**
   * API 钥匙
   *
   * API 用于通过 vLLM 服务进行身份验证的密钥
   */
  api_key: string;
  /**
   * 有成功标签
   *
   * 模型是否预测索引 0 处的成功标签
   */
  has_success_label?: boolean;
  /**
   * 基础设施标签
   */
  infra_labels?: Array<string>;
  /**
   * 问题门槛
   *
   * APIBasedCritic特定的概率阈值，用于智能体问题标签，以触发迭代的细化。
   */
  issue_threshold?: number;
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind: 'APIBasedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
  /**
   * 型号名称
   *
   * 使用的型号名称
   */
  model_name?: string;
  /**
   * 传递工具定义
   *
   * 是否将工具定义传递给模型
   */
  pass_tools_definitions?: boolean;
  /**
   * 情绪标签
   */
  sentiment_labels?: Array<string>;
  /**
   * 情绪图
   */
  sentiment_map?: {
    [key: string]: string;
  };
  /**
   * 服务器网址
   *
   * vLLM 分类服务的基础 URL
   */
  server_url?: string;
  /**
   * 超时秒
   *
   * 超时对模型的请求
   */
  timeout_seconds?: number;
  /**
   * 分词器名称
   *
   * HuggingFace 用于加载聊天模板的分词器名称
   */
  tokenizer_name?: string;
  /**
   * 用户跟进标签
   */
  user_followup_labels?: Array<string>;
};

export type Action =
  | ({
      kind: 'openhands__sdk__mcp__definition__MCPToolAction-Output__1';
    } & McpToolAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__classify_and_switch_llm__ClassifyAndSwitchLLMAction-Output__1';
    } & ClassifyAndSwitchLlmAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__finish__FinishAction-Output__1';
    } & FinishAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__invoke_skill__InvokeSkillAction-Output__1';
    } & InvokeSkillAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__switch_llm__SwitchLLMAction-Output__1';
    } & SwitchLlmAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__think__ThinkAction-Output__1';
    } & ThinkAction)
  | ({
      kind: 'openhands__sdk__tool__builtins__vision_inspect__VisionInspectAction-Output__1';
    } & VisionInspectAction)
  | ({
      kind: 'openhands__tools__ask_oracle__definition__AskOracleAction-Output__1';
    } & AskOracleAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserAction-Output__1';
    } & BrowserAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserClickAction-Output__1';
    } & BrowserClickAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserCloseTabAction-Output__1';
    } & BrowserCloseTabAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetContentAction-Output__1';
    } & BrowserGetContentAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStateAction-Output__1';
    } & BrowserGetStateAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStorageAction-Output__1';
    } & BrowserGetStorageAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGoBackAction-Output__1';
    } & BrowserGoBackAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserListTabsAction-Output__1';
    } & BrowserListTabsAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserNavigateAction-Output__1';
    } & BrowserNavigateAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserScrollAction-Output__1';
    } & BrowserScrollAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSetStorageAction-Output__1';
    } & BrowserSetStorageAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStartRecordingAction-Output__1';
    } & BrowserStartRecordingAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStopRecordingAction-Output__1';
    } & BrowserStopRecordingAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSwitchTabAction-Output__1';
    } & BrowserSwitchTabAction)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserTypeAction-Output__1';
    } & BrowserTypeAction)
  | ({
      kind: 'openhands__tools__child_conversation__definition__StartChildConversationAction-Output__1';
    } & StartChildConversationAction)
  | ({
      kind: 'openhands__tools__delegate__definition__DelegateAction-Output__1';
    } & DelegateAction)
  | ({
      kind: 'openhands__tools__file_editor__definition__FileEditorAction-Output__1';
    } & FileEditorAction)
  | ({
      kind: 'openhands__tools__gemini__edit__definition__EditAction-Output__1';
    } & EditAction)
  | ({
      kind: 'openhands__tools__gemini__list_directory__definition__ListDirectoryAction-Output__1';
    } & ListDirectoryAction)
  | ({
      kind: 'openhands__tools__gemini__read_file__definition__ReadFileAction-Output__1';
    } & ReadFileAction)
  | ({
      kind: 'openhands__tools__gemini__write_file__definition__WriteFileAction-Output__1';
    } & WriteFileAction)
  | ({
      kind: 'openhands__tools__glob__definition__GlobAction-Output__1';
    } & GlobAction)
  | ({
      kind: 'openhands__tools__grep__definition__GrepAction-Output__1';
    } & GrepAction)
  | ({
      kind: 'openhands__tools__planning_file_editor__definition__PlanningFileEditorAction-Output__1';
    } & PlanningFileEditorAction)
  | ({
      kind: 'openhands__tools__task__definition__TaskAction-Output__1';
    } & TaskAction)
  | ({
      kind: 'openhands__tools__task_tracker__definition__TaskTrackerAction-Output__1';
    } & TaskTrackerAction)
  | ({
      kind: 'openhands__tools__terminal__definition__TerminalAction-Output__1';
    } & TerminalAction)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowAction-Output__1';
    } & WorkflowAction);

/**
 * ActionEvent
 */
export type ActionEvent = {
  /**
   * LLM 返回单个工具调用（None 不可执行时）
   */
  action?: Action | null;
  /**
   * 对此行动和之前历史的可选评论家评价。
   */
  critic_result?: CriticResult | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'ActionEvent';
  /**
   * Llm 响应 ID
   *
   * 生成此 eventE.g 的 LLM 响应的完成或响应 ID。可用于对同一 LLM 响应中的相关操作进行分组。 这有助于跟踪和管理来自同一 LLM 响应的并行函数调用的结果。
   */
  llm_response_id: string;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 推理内容
   *
   * 来自推理模型的中级推理/思维内容
   */
  reasoning_content?: string | null;
  /**
   * OpenAI 模型输出的响应推理项
   */
  responses_reasoning_item?: ReasoningItemModel | null;
  /**
   * LLM对此行为的安全风险评估。
   */
  security_risk?: SecurityRisk;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 总结
   *
   * LLM 提供了此操作的作用的简明摘要（大约 10 个字），以便于解释和调试。 示例：| 编辑部署设置配置文件 | 搜索代码库中的函数定义 | 从包管理器的依赖项列表安装必需的依赖项 | 运行测试以验证 bug 修复身份验证查看目录结构以查找源文件
   */
  summary?: string | null;
  /**
   * 思维块
   *
   * LLM 响应的 Anthropic 思维障碍
   */
  thinking_blocks?: Array<ThinkingBlock | RedactedThinkingBlock>;
  /**
   * 思想
   *
   * 智能体采取此行动之前的思考过程
   */
  thought: Array<TextContent>;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 从 LLM 响应收到的工具调用。 我们保留了一份副本，这样更容易将其构造为 LLM messageThis 可能与 `action` 不同：e.g。 `tool_call` 可能包含 `security_risk` 由 LLM 预测的风险分析器启用时 LLM 的字段，而 `action` 不包含。
   */
  tool_call: MessageToolCall;
  /**
   * 工具调用身份证号
   *
   * LLM API 为此工具调用返回的唯一 ID
   */
  tool_call_id: string;
  /**
   * 工具名称
   *
   * 被调用的工具的名称
   */
  tool_name: string;
};

/**
 * ActivateAgentProfileResponse
 */
export type ActivateAgentProfileResponse = {
  /**
   * 智能体已应用设置
   */
  agent_settings_applied?: boolean;
  /**
   * 身份证号
   */
  id: string;
  /**
   * 留言
   */
  message: string;
};

/**
 * ActivateMetaProfileResponse
 */
export type ActivateMetaProfileResponse = {
  /**
   * 应用
   */
  applied?: boolean;
  /**
   * 留言
   */
  message: string;
  /**
   * 名称
   */
  name: string;
};

/**
 * ActivateProfileResponse
 *
 * 配置文件激活的响应模型。
 */
export type ActivateProfileResponse = {
  /**
   * 应用法学硕士
   */
  llm_applied?: boolean;
  /**
   * 留言
   */
  message: string;
  /**
   * 名称
   */
  name: string;
};

/**
 * AddWorkspaceParentsRequest
 */
export type AddWorkspaceParentsRequest = {
  /**
   * 家长
   */
  parents: Array<WorkspaceParentItem>;
};

/**
 * AddWorkspacesRequest
 */
export type AddWorkspacesRequest = {
  /**
   * 工作区
   */
  workspaces: Array<WorkspaceItem>;
};

/**
 * 智能体
 *
 * OpenHands 的主要智能体实现。
 *
 * 智能体类提供运行 AI 智能体的核心功能，可以
 * 与工具交互、处理消息并执行操作。 它继承自
 * AgentBase并实现智能体执行逻辑。 评论家相关功能
 * 由CriticMixin提供。
 *
 * 属性：
 * llm：用于推理的语言模型实例。
 * 工具： 智能体可用的工具列表。
 * system_prompt：内联系统提示词字符串。 当提供智能体
 * 逐字使用此文本而不是从模板渲染。
 * 与非默认 ``system_prompt_filename`` 互斥。
 * **不推荐**，除非您知道自己在做什么（e.g。
 * 为完全不同的任务定制智能体行为）—
 * 这将覆盖OpenHands'内置系统指令。
 * system_prompt_filename：Jinja2 模板文件名相对于解析
 * 智能体的提示词目录，或绝对路径。 默认为
 * ``"system_prompt.j2"``.
 * system_prompt_kwargs：额外的 kwargs 转发到 Jinja2 模板。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM、智能体、工具
 * 从 Pydantic 导入 SecretStr
 *
 * llm = LLM(型号=“gpt-5.6”，api_key=SecretStr(“密钥”))
 * 工具 = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
 * 智能体 = Agent(llm=llm, tools=tools)
 * ```
 *
 * 要完全覆盖系统提示词：
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=工具，
 * system_prompt="你是一位有用的编码助手。",
 * )
 */
export type AgentInput = {
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextInput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseInput | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseInput | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   *
   * 要包含的默认工具类名称列表。 默认情况下，智能体包括“FinishTool”和“ThinkTool”。 设置为空列表以禁用所有默认工具，或提供一个子集以仅包含特定工具。 示例：include_default_tools=['FinishTool'] 仅包含 FinishTool，或 include_default_tools=[] 禁用所有默认工具。
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind?: 'Agent';
  /**
   * LLM配置为智能体。
   */
  llm: LlmInput;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInput;
  };
  /**
   * 人格面具
   *
   * 替换系统提示词的 OpenHands' 内置角色和编码工作流程部分的角色文本。 能力与策略部分（内存、安全策略、风险评估、浏览器、外部服务、过程管理、模型特定指导）以及动态上下文仍然适用。 设置`system_prompt`时忽略； 自定义模板将其作为 `persona` kwarg 接收。
   */
  persona?: string | null;
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   *
   * 用于初始化的工具列表智能体。
   */
  tools?: Array<ToolInput>;
};

/**
 * 智能体
 *
 * OpenHands 的主要智能体实现。
 *
 * 智能体类提供运行 AI 智能体的核心功能，可以
 * 与工具交互、处理消息并执行操作。 它继承自
 * AgentBase并实现智能体执行逻辑。 评论家相关功能
 * 由CriticMixin提供。
 *
 * 属性：
 * llm：用于推理的语言模型实例。
 * 工具： 智能体可用的工具列表。
 * system_prompt：内联系统提示词字符串。 当提供智能体
 * 逐字使用此文本而不是从模板渲染。
 * 与非默认 ``system_prompt_filename`` 互斥。
 * **不推荐**，除非您知道自己在做什么（e.g。
 * 为完全不同的任务定制智能体行为）—
 * 这将覆盖OpenHands'内置系统指令。
 * system_prompt_filename：Jinja2 模板文件名相对于解析
 * 智能体的提示词目录，或绝对路径。 默认为
 * ``"system_prompt.j2"``.
 * system_prompt_kwargs：额外的 kwargs 转发到 Jinja2 模板。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM、智能体、工具
 * 从 Pydantic 导入 SecretStr
 *
 * llm = LLM(型号=“gpt-5.6”，api_key=SecretStr(“密钥”))
 * 工具 = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
 * 智能体 = Agent(llm=llm, tools=tools)
 * ```
 *
 * 要完全覆盖系统提示词：
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=工具，
 * system_prompt="你是一位有用的编码助手。",
 * )
 */
export type AgentOutput = {
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextOutput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseOutput | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseOutput | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   *
   * 要包含的默认工具类名称列表。 默认情况下，智能体包括“FinishTool”和“ThinkTool”。 设置为空列表以禁用所有默认工具，或提供一个子集以仅包含特定工具。 示例：include_default_tools=['FinishTool'] 仅包含 FinishTool，或 include_default_tools=[] 禁用所有默认工具。
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind: 'Agent';
  /**
   * LLM配置为智能体。
   */
  llm: LlmOutput;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  };
  /**
   * 人格面具
   *
   * 替换系统提示词的 OpenHands' 内置角色和编码工作流程部分的角色文本。 能力与策略部分（内存、安全策略、风险评估、浏览器、外部服务、过程管理、模型特定指导）以及动态上下文仍然适用。 设置`system_prompt`时忽略； 自定义模板将其作为 `persona` kwarg 接收。
   */
  persona?: string | null;
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   *
   * 用于初始化的工具列表智能体。
   */
  tools?: Array<OpenhandsSdkToolSpecTool>;
};

export type AgentBaseInput =
  | ({
      kind: 'openhands__sdk__agent__acp_agent__ACPAgent-Input__1';
    } & AcpAgentInput)
  | ({
      kind: 'openhands__sdk__agent__agent__Agent-Input__1';
    } & AgentInput);

export type AgentBaseOutput =
  | ({
      kind: 'openhands__sdk__agent__acp_agent__ACPAgent-Output__1';
    } & AcpAgentOutput)
  | ({
      kind: 'openhands__sdk__agent__agent__Agent-Output__1';
    } & AgentOutput);

/**
 * AgentContext
 *
 * 用于管理提示词扩展的中央结构。
 *
 * AgentContext 统一了塑造系统如何运作的所有上下文输入
 * 扩展并解释用户提示词。 它结合了静态环境
 * 细节和动态的、用户激活的技能扩展。
 *
 * 具体来说，它规定：
 * - **存储库上下文/存储库技能**：有关活动代码库的信息，
 * 分支，以及由回购技能贡献的回购特定指令。
 * - **运行时上下文**：当前执行环境（主机、工作环境）
 * 目录、机密、日期等）。
 * - **对话说明**：可选的特定于任务或频道的规则
 * 限制或指导智能体在整个会话中的行为。
 * - **知识技能**：可以由用户输入触发的可扩展组件
 * 注入知识或特定领域的指导。
 *
 * 这些元素一起使 AgentContext 成为负责的主容器
 * 用于组装、格式化和将所有提示词相关的上下文注入
 * LLM 互动。
 */
export type AgentContextInput = {
  /**
   * 当前日期时间
   *
   * 提供给智能体的当前日期和时间信息。 可以是日期时间对象（将格式化为 ISO 8601）或预先格式化的字符串。 提供后，该信息将包含在系统提示词中，以使智能体了解当前时间上下文。 默认为当前（时区感知）日期时间。
   */
  current_datetime?: string | string | null;
  /**
   * 残疾人技能
   *
   * 从这个上下文中移除EXCLUDE的技能名——一个在每个技能源加载后应用的拒绝列表（自动加载的用户/公共、显式和懒加载的项目技能）。 加载集中不存在的列出名称是无害的无操作。 []（默认）保留所有技能。 这是单一的、容忍偏差的技能选择机制（智能体配置文件从他们自己的拒绝列表中设置它；#4017）。
   */
  disabled_skills?: Array<string>;
  /**
   * 加载内存
   *
   * 是否将持久智能体内存（~/.openhands/memory/和<workspace>/.openhands/memory/)下的MEMORY.md索引加载到系统提示词中。 与load_project_skills一样，该标志不由AgentContext本身解析（工作区路径在验证时未知）； LocalConversation 在第一个 send_message() / run() 上延迟解析它，并将结果存储在 memory_context 中。
   */
  load_memory?: boolean;
  /**
   * 加载项目技能
   *
   * 是否自动加载对话中的项目技能工作区 (e.g. .openhands/skills/, AGENTS.md). 不像 load_user_skills / load_public_skills这个标志不会被解析 AgentContext 它自身（[the]） 工作区路径未知验证时间。 LocalConversation 在第一次解析时懒加载 send_message() / run(), when the 工作区已被知。 也不同于 load_user_skills / load_public_skills （这些技能会优先于明示的冲突技能），已解决的项目技能具有权威性：一个项目技能会覆盖一个已存在的同名技能 `skills`.
   */
  load_project_skills?: boolean;
  /**
   * 加载公共技能
   *
   * 是否自动从  https://github.com/OpenHands/extensions.  处的公共 OpenHands 技能存储库加载技能这使您无需 SDK 更新即可获取最新技能。
   */
  load_public_skills?: boolean;
  /**
   * 加载用户技能
   *
   * 是否自动从 ~/.openhands/skills/ 和 ~/.openhands/microagents/ 加载用户技能（对于向后兼容性）。
   */
  load_user_skills?: boolean;
  /**
   * 市场路径
   *
   * 公共技能存储库内的相对市场 JSON 路径。 设置为 None 以加载所有公共技能而不进行市场过滤。
   */
  marketplace_path?: string | null;
  /**
   * 内存上下文
   *
   * 已解析的内存索引文本呈现到 <MEMORY_CONTEXT> 提示词块中。 当设置 load_memory 时，通过 model_copy 由 LocalConversation 填充； 从序列化中排除，因为它在每个会话中从磁盘重新解析，并且不得使已持久化会话状态膨胀。
   */
  memory_context?: string | null;
  /**
   * 注册市场
   *
   * 插件解析的市场注册。 auto_load=True 或插件名称列表的注册在启动时由 LocalConversation 解析。
   */
  registered_marketplaces?: Array<MarketplaceRegistration>;
  /**
   * 机密
   *
   * 机密个键值对或机密来源的字典。 机密用于身份验证和敏感数据处理。 值可以是字符串，也可以是SecretSource的实例（str | SecretSource)。
   */
  secrets?: {
    [key: string]: string | SecretSourceInput;
  } | null;
  /**
   * 技能
   *
   * 可以扩展用户输入的可用技能列表。
   */
  skills?: Array<SkillInput>;
  /**
   * 系统消息后缀
   *
   * 附加到系统的可选后缀提示词。
   */
  system_message_suffix?: string | null;
  /**
   * 用户消息后缀
   *
   * 用于附加到用户消息的可选后缀。
   */
  user_message_suffix?: string | null;
};

/**
 * AgentContext
 *
 * 用于管理提示词扩展的中央结构。
 *
 * AgentContext 统一了塑造系统如何运作的所有上下文输入
 * 扩展并解释用户提示词。 它结合了静态环境
 * 细节和动态的、用户激活的技能扩展。
 *
 * 具体来说，它规定：
 * - **存储库上下文/存储库技能**：有关活动代码库的信息，
 * 分支，以及由回购技能贡献的回购特定指令。
 * - **运行时上下文**：当前执行环境（主机、工作环境）
 * 目录、机密、日期等）。
 * - **对话说明**：可选的特定于任务或频道的规则
 * 限制或指导智能体在整个会话中的行为。
 * - **知识技能**：可以由用户输入触发的可扩展组件
 * 注入知识或特定领域的指导。
 *
 * 这些元素一起使 AgentContext 成为负责的主容器
 * 用于组装、格式化和将所有提示词相关的上下文注入
 * LLM 互动。
 */
export type AgentContextOutput = {
  /**
   * 当前日期时间
   *
   * 提供给智能体的当前日期和时间信息。 可以是日期时间对象（将格式化为 ISO 8601）或预先格式化的字符串。 提供后，该信息将包含在系统提示词中，以使智能体了解当前时间上下文。 默认为当前（时区感知）日期时间。
   */
  current_datetime?: string | string | null;
  /**
   * 残疾人技能
   *
   * 从这个上下文中移除EXCLUDE的技能名——一个在每个技能源加载后应用的拒绝列表（自动加载的用户/公共、显式和懒加载的项目技能）。 加载集中不存在的列出名称是无害的无操作。 []（默认）保留所有技能。 这是单一的、容忍偏差的技能选择机制（智能体配置文件从他们自己的拒绝列表中设置它；#4017）。
   */
  disabled_skills?: Array<string>;
  /**
   * 加载内存
   *
   * 是否将持久智能体内存（~/.openhands/memory/和<workspace>/.openhands/memory/)下的MEMORY.md索引加载到系统提示词中。 与load_project_skills一样，该标志不由AgentContext本身解析（工作区路径在验证时未知）； LocalConversation 在第一个 send_message() / run() 上延迟解析它，并将结果存储在 memory_context 中。
   */
  load_memory?: boolean;
  /**
   * 加载项目技能
   *
   * 是否自动加载对话中的项目技能工作区 (e.g. .openhands/skills/, AGENTS.md). 不像 load_user_skills / load_public_skills这个标志不会被解析 AgentContext 它自身（[the]） 工作区路径未知验证时间。 LocalConversation 在第一次解析时懒加载 send_message() / run(), when the 工作区已被知。 也不同于 load_user_skills / load_public_skills （这些技能会优先于明示的冲突技能），已解决的项目技能具有权威性：一个项目技能会覆盖一个已存在的同名技能 `skills`.
   */
  load_project_skills?: boolean;
  /**
   * 加载公共技能
   *
   * 是否自动从  https://github.com/OpenHands/extensions.  处的公共 OpenHands 技能存储库加载技能这使您无需 SDK 更新即可获取最新技能。
   */
  load_public_skills?: boolean;
  /**
   * 加载用户技能
   *
   * 是否自动从 ~/.openhands/skills/ 和 ~/.openhands/microagents/ 加载用户技能（对于向后兼容性）。
   */
  load_user_skills?: boolean;
  /**
   * 市场路径
   *
   * 公共技能存储库内的相对市场 JSON 路径。 设置为 None 以加载所有公共技能而不进行市场过滤。
   */
  marketplace_path?: string | null;
  /**
   * 注册市场
   *
   * 插件解析的市场注册。 auto_load=True 或插件名称列表的注册在启动时由 LocalConversation 解析。
   */
  registered_marketplaces?: Array<MarketplaceRegistration>;
  /**
   * 机密
   *
   * 机密个键值对或机密来源的字典。 机密用于身份验证和敏感数据处理。 值可以是字符串，也可以是SecretSource的实例（str | SecretSource)。
   */
  secrets?: {
    [key: string]: unknown;
  } | null;
  /**
   * 技能
   *
   * 可以扩展用户输入的可用技能列表。
   */
  skills?: Array<SkillOutput>;
  /**
   * 系统消息后缀
   *
   * 附加到系统的可选后缀提示词。
   */
  system_message_suffix?: string | null;
  /**
   * 用户消息后缀
   *
   * 用于附加到用户消息的可选后缀。
   */
  user_message_suffix?: string | null;
};

/**
 * AgentDefinition
 *
 * 从 Markdown 文件加载智能体定义。
 *
 * 智能体是可以根据以下条件触发的特殊配置
 * 用户输入模式。 他们定义自定义系统提示词和工具访问。
 */
export type AgentDefinition = {
  /**
   * 颜色
   *
   * 智能体的显示颜色
   */
  color?: string | null;
  /**
   * 上下文上下文压缩器为子智能体。 None应用默认总结上下文压缩器； 设置 NoOpCondenser 以禁用上下文压缩。
   */
  condenser?: CondenserBaseInput | null;
  /**
   * 描述
   *
   * 智能体说明
   */
  description?: string;
  /**
   * 此智能体的挂钩配置
   */
  hooks?: HookConfig | null;
  /**
   * 级别
   *
   * 发现智能体的范围。 在发现期间设置； None 直接从文件加载时。
   */
  level?: 'project' | 'user' | 'builtin' | 'plugin' | 'programmatic' | null;
  /**
   * 每次运行的最大预算
   *
   * 此子智能体每次运行的最大累积成本 (USD)。 必须严格为正，否则 None 无预算。
   */
  max_budget_per_run?: number | null;
  /**
   * 每次运行的最大迭代次数
   *
   * 每次运行的最大迭代次数。 它必须严格为正数，或者默认为 None。
   */
  max_iteration_per_run?: number | null;
  /**
   * MCP 配置
   *
   * MCP 用于此的服务器智能体。 当它作为代理运行时被忽略子智能体它总是继承其父类 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInput;
  } | null;
  /**
   * 元数据
   *
   * 来自前置元数据的附加元数据
   */
  metadata?: {
    [key: string]: unknown;
  };
  /**
   * 型号
   *
   * 要使用的模型（“继承”使用父模型）
   */
  model?: string;
  /**
   * 名称
   *
   * 智能体名称（来自前置元数据或文件名）
   */
  name: string;
  /**
   * 权限模式
   *
   * 子智能体如何处理权限。 None 继承父级策略；'always_confirm' 要求每个操作都确认，'never_confirm' 跳过全部确认，'confirm_risky' 仅确认风险超过阈值的操作。
   */
  permission_mode?: string | null;
  /**
   * 配置文件存储目录
   *
   * 存储 LLM 个配置文件的目录路径。 如果 None，则使用默认配置文件存储目录。
   */
  profile_store_dir?: string | null;
  /**
   * 技能
   *
   * 此技能名称列表智能体。 从项目/用户目录解决。
   */
  skills?: Array<string>;
  /**
   * 来源
   *
   * 此智能体的源文件路径
   */
  source?: string | null;
  /**
   * 系统提示词
   *
   * 系统提示词内容
   */
  system_prompt?: string;
  /**
   * 工具
   *
   * 允许使用的工具列表智能体
   */
  tools?: Array<string>;
  /**
   * 何时使用示例
   *
   * 何时使用此智能体的示例（用于触发）
   */
  when_to_use_examples?: Array<string>;
};

/**
 * AgentErrorEvent
 *
 * 由智能体触发的错误。
 *
 * 注意：此事件不应包含模型“thought”或“reasoning_content”。 它
 * 表示由代理/支架产生的错误，而不是模型输出。
 */
export type AgentErrorEvent = {
  /**
   * 为 API 消费者提供安全的结构化错误语义。
   */
  classification?: ErrorClassification | null;
  /**
   * 错误
   *
   * 来自脚手架的错误消息
   */
  error: string;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'AgentErrorEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具调用身份证号
   *
   * 此观测结果正在响应的工具调用 id
   */
  tool_call_id: string;
  /**
   * 工具名称
   *
   * 此观测结果响应的工具名称
   */
  tool_name: string;
};

/**
 * AgentFinishedCritic
 *
 * 评估智能体是否正确完成任务的批评者。
 *
 * 这位批评家检查了两个主要标准：
 * 1. 智能体的最后一个动作是 FinishAction（正确完成）
 * 2. 生成的git补丁非空（实际进行了更改）
 */
export type AgentFinishedCriticInput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind?: 'AgentFinishedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * AgentFinishedCritic
 *
 * 评估智能体是否正确完成任务的批评者。
 *
 * 这位批评家检查了两个主要标准：
 * 1. 智能体的最后一个动作是 FinishAction（正确完成）
 * 2. 生成的git补丁非空（实际进行了更改）
 */
export type AgentFinishedCriticOutput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind: 'AgentFinishedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * AgentLaunchAdditions
 *
 * 在智能体解析后添加部署上下文。
 */
export type AgentLaunchAdditions = {
  /**
   * 法学硕士简介参考
   *
   * LLM 配置文件启动 OpenHands 智能体配置文件而不是其自己的 `llm_profile_ref`。 记载于`launched_agent_profile`； 存储的配置文件不会被修改。 仅对 `agent_profile_id` 有效。
   */
  llm_profile_ref?: string | null;
  /**
   * 技能
   *
   * 部署提供的技能合并到已解决的智能体的上下文中。 对于自己拥有技能目录的客户端来说，无法依赖服务器，因此：``agent_profile_id`` 启动没有 ``agent_settings``，只能这样提供给他们。 ——以名称合并 ——已解决的智能体已经具备了这项技能，因此获胜，而该角色的``disabled_skills``拒绝列表仍然有效，所以这无法重新引入该角色已关闭的功能。 None（默认）不添加任何内容。
   */
  skills?: Array<SkillInput> | null;
  /**
   * 系统消息后缀追加
   *
   * 部署控制的文本附加到已解析的智能体的系统消息后缀。
   */
  system_message_suffix_append?: string | null;
};

/**
 * AgentProfileDetailResponse
 */
export type AgentProfileDetailResponse = {
  /**
   * 名称
   */
  name: string;
  /**
   * 公司简介
   */
  profile: {
    [key: string]: unknown;
  };
};

/**
 * AgentProfileDiagnostics
 *
 * 关于：func:`resolve_agent_profile` 会做什么的无副作用报告。
 *
 * 由 ``POST /{id}/materialize`` (#3719) 和画布编辑器使用。 的
 * 结论 (:attr:`valid`) 和悬空引用列表与真实的完全匹配
 * 解决产生； :attr:`resolved_settings` 是已脱敏设置转储
 * （仅当：attr:`valid` 时出现）。
 */
export type AgentProfileDiagnostics = {
  /**
   * ACP API 键机密名称
   */
  acp_api_key_secret_name?: string | null;
  /**
   * ACP 基本网址机密名称
   */
  acp_base_url_secret_name?: string | null;
  /**
   * ACP 文件机密名称
   */
  acp_file_secret_names?: Array<string>;
  /**
   * 智能体种类
   */
  agent_kind: string;
  /**
   * 悬空 MCP 服务器参考
   */
  dangling_mcp_server_refs?: Array<string>;
  /**
   * 悬挂元配置文件 Llm 参考文献
   */
  dangling_meta_profile_llm_refs?: Array<string>;
  /**
   * 悬挂元配置文件参考
   */
  dangling_meta_profile_ref?: string | null;
  /**
   * 残疾人技能
   */
  disabled_skills?: Array<string>;
  /**
   * 错误
   */
  errors?: Array<string>;
  /**
   * Llm API 按键设置
   */
  llm_api_key_set?: boolean;
  /**
   * 法学硕士简介参考
   */
  llm_profile_ref?: string | null;
  /**
   * 法学硕士简介已解决
   */
  llm_profile_resolved?: boolean;
  /**
   * MCP 服务器参考
   */
  mcp_server_refs?: Array<string> | null;
  /**
   * 元配置文件参考
   */
  meta_profile_ref?: string | null;
  /**
   * 公共技能
   */
  public_skills?: Array<string> | null;
  /**
   * 已解决 MCP 配置键
   */
  resolved_mcp_config_keys?: Array<string>;
  /**
   * 已解决的设置
   */
  resolved_settings?: {
    [key: string]: unknown;
  } | null;
  /**
   * 已解决的技能
   */
  resolved_skills?: Array<string>;
  /**
   * 机密参考文献
   */
  secret_refs?: Array<string> | null;
  /**
   * 无法使用的工具
   *
   * 运行时无法运行选定的工具。 不可用的浏览器将被排除在启动之外； 任何其他此类工具都无法启动或在智能体使用它时失败。
   */
  unusable_tools?: Array<string>;
  /**
   * 有效
   */
  valid?: boolean;
};

/**
 * AgentProfileInfo
 *
 * 已存储配置文件的摘要投影（无机密实例化）。
 */
export type AgentProfileInfo = {
  /**
   * 智能体种类
   */
  agent_kind?: string;
  /**
   * 身份证号
   */
  id?: string | null;
  /**
   * 法学硕士简介参考
   */
  llm_profile_ref?: string | null;
  /**
   * MCP 服务器参考
   */
  mcp_server_refs?: Array<string> | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 修订版
   */
  revision?: number | null;
};

/**
 * AgentProfileListResponse
 *
 * ``GET /api/agent-profiles`` 返回的响应正文。
 */
export type AgentProfileListResponse = {
  /**
   * 活动智能体配置文件 ID
   */
  active_agent_profile_id?: string | null;
  /**
   * 型材
   */
  profiles: Array<AgentProfileInfo>;
};

/**
 * AgentProfileMutationResponse
 */
export type AgentProfileMutationResponse = {
  /**
   * 留言
   */
  message: string;
  /**
   * 名称
   */
  name: string;
};

/**
 * AgentResponseResult
 *
 * 智能体对对话的最终响应。
 *
 * 包含最后一个智能体完成消息或文本响应的文本。
 * 如果智能体尚未产生最终响应，则为空字符串。
 */
export type AgentResponseResult = {
  /**
   * 回应
   *
   * 智能体的最终响应文本。 从 FinishAction 消息或最后一个智能体 MessageEvent 中提取。 如果没有最终响应可用，则为空字符串。
   */
  response: string;
};

/**
 * AgentSettings
 */
export type AgentSettings = {
  /**
   * 智能体种类
   */
  agent_kind?: 'openhands' | 'acp' | null;
  mcp_config: McpConfig;
  /**
   * 模式版本
   */
  schema_version?: number | null;
  [key: string]: unknown;
};

/**
 * AgentSettingsPatch
 */
export type AgentSettingsPatch = {
  mcp_config?: McpConfigPatch | null;
  [key: string]: unknown;
};

/**
 * AlwaysConfirm
 */
export type AlwaysConfirmInput = {
  /**
   * 种类
   */
  kind?: 'AlwaysConfirm';
};

/**
 * AlwaysConfirm
 */
export type AlwaysConfirmOutput = {
  /**
   * 种类
   */
  kind: 'AlwaysConfirm';
};

/**
 * AskAgentRequest
 *
 * 载荷问智能体一个简单的问题。
 */
export type AskAgentRequest = {
  /**
   * 问题
   *
   * 要问的问题智能体
   */
  question: string;
};

/**
 * AskAgentResponse
 *
 * 包含智能体的答案的响应。
 */
export type AskAgentResponse = {
  /**
   * 回应
   *
   * 智能体对问题的回答
   */
  response: string;
};

/**
 * AskOracleAction
 *
 * 向 Oracle 寻求建议的行动。
 */
export type AskOracleAction = {
  /**
   * 上下文
   *
   * 可选的额外上下文，例如已经尝试过的方法、限制或您正在考虑的建议。
   */
  context?: string | null;
  /**
   * 种类
   */
  kind: 'AskOracleAction';
  /**
   * 问题
   *
   * 向 Oracle 询问的具体问题或困境。 当您陷入困境、不确定或需要第二意见时，请使用此方法。
   */
  question: string;
};

/**
 * AskOracleObservation
 *
 * 观测结果由Oracle协商返回。
 */
export type AskOracleObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'AskOracleObservation';
};

/**
 * AskOracleTool
 *
 * 用于咨询 Oracle 的工具（名为“oracle”的已保存 LLM 配置文件）。
 */
export type AskOracleTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'AskOracleTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BackendLogs
 *
 * 有界的组合 stdout 和 stderr 输出。
 */
export type BackendLogs = {
  /**
   * 日志
   */
  logs: string;
  /**
   * 名称
   */
  name: string;
  /**
   * 截断的
   */
  truncated: boolean;
};

/**
 * BackendRevisionRequest
 *
 * 明确批准一项确切安装的修订版。
 */
export type BackendRevisionRequest = {
  /**
   * 修订版
   */
  revision: string;
};

/**
 * BackendStatus
 *
 * 已安装 Canvas 应用程序后端的当前状态。
 */
export type BackendStatus = {
  /**
   * 详情
   */
  detail?: string | null;
  /**
   * 名称
   */
  name: string;
  /**
   * PID
   */
  pid?: number | null;
  /**
   * 港口
   */
  port?: number | null;
  /**
   * 准备修订
   */
  prepared_revision?: string | null;
  /**
   * 修订版
   */
  revision?: string | null;
  /**
   * 状态
   */
  state: 'missing' | 'stopped' | 'starting' | 'ready' | 'unhealthy' | 'unsupported';
};

export type BaseWorkspace =
  | ({
      kind: 'openhands__sdk__workspace__local__LocalWorkspace-Output__1';
    } & LocalWorkspaceOutput)
  | ({
      kind: 'openhands__sdk__workspace__remote__base__RemoteWorkspace-Output__1';
    } & RemoteWorkspace);

/**
 * BashCommand
 */
export type BashCommand = {
  /**
   * 命令
   *
   * 要执行的 bash 命令
   */
  command: string;
  /**
   * 西德
   *
   * 当前工作目录
   */
  cwd?: string | null;
  /**
   * 身份证号
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'BashCommand';
  /**
   * 超时
   *
   * 允许命令运行的最大秒数。
   */
  timeout?: number;
  /**
   * 时间戳
   */
  timestamp?: string;
};

/**
 * BashError
 */
export type BashError = {
  /**
   * 代码
   *
   * 错误代码 - 通常是错误类型
   */
  code: string;
  /**
   * 详情
   *
   * 有关错误的详细信息
   */
  detail: string;
  /**
   * 身份证号
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'BashError';
  /**
   * 时间戳
   */
  timestamp?: string;
};

export type BashEventBase =
  | ({
      kind: 'openhands__agent_server__models__BashCommand-Output__1';
    } & BashCommand)
  | ({
      kind: 'openhands__agent_server__models__BashError-Output__1';
    } & BashError)
  | ({
      kind: 'openhands__agent_server__models__BashOutput-Output__1';
    } & BashOutput);

/**
 * BashEventPage
 */
export type BashEventPage = {
  /**
   * 项目
   */
  items: Array<BashEventBase>;
  /**
   * 下一页 ID
   */
  next_page_id?: string | null;
};

/**
 * BashEventSortOrder
 */
export type BashEventSortOrder = 'TIMESTAMP' | 'TIMESTAMP_DESC';

/**
 * BashOutput
 *
 * bash 命令的输出。 单个命令可能有多个输出
 * 取决于输出有多大。
 */
export type BashOutput = {
  /**
   * 命令 ID
   */
  command_id: string;
  /**
   * 退出代码
   *
   * 退出代码 None 表示该命令仍在运行。
   */
  exit_code?: number | null;
  /**
   * 身份证号
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'BashOutput';
  /**
   * 订单
   *
   * 此输出的顺序，从 0 开始依次
   */
  order?: number;
  /**
   * 斯特德尔
   *
   * 命令的错误输出
   */
  stderr?: string | null;
  /**
   * 标准输出
   *
   * 命令的标准输出
   */
  stdout?: string | null;
  /**
   * 时间戳
   */
  timestamp?: string;
};

/**
 * Body_load_conversation_plugin_api_conversations__conversation_id__load_plugin_post
 */
export type BodyLoadConversationPluginApiConversationsConversationIdLoadPluginPost = {
  /**
   * 插件参考
   */
  plugin_ref: string;
};

/**
 * Body_switch_conversation_acp_model_api_conversations__conversation_id__switch_acp_model_post
 */
export type BodySwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPost = {
  /**
   * 型号
   */
  model: string;
};

/**
 * Body_switch_conversation_llm_api_conversations__conversation_id__switch_llm_post
 */
export type BodySwitchConversationLlmApiConversationsConversationIdSwitchLlmPost = {
  llm: LlmInput;
};

/**
 * Body_switch_conversation_profile_api_conversations__conversation_id__switch_profile_post
 */
export type BodySwitchConversationProfileApiConversationsConversationIdSwitchProfilePost = {
  /**
   * 个人资料名称
   */
  profile_name: string;
};

/**
 * Body_upload_file_query_api_conversations__runtime_conversation_id__file_upload_post
 */
export type BodyUploadFileQueryApiConversationsRuntimeConversationIdFileUploadPost = {
  /**
   * 文件
   */
  file: Blob | File;
};

/**
 * Body_upload_file_query_api_file_upload_post
 */
export type BodyUploadFileQueryApiFileUploadPost = {
  /**
   * 文件
   */
  file: Blob | File;
};

/**
 * BrowserAction
 *
 * 所有浏览器操作的基类。
 *
 * 该基类充当所有与浏览器相关的操作的父类，
 * 启用正确的类型层次结构并消除对联合类型的需要。
 */
export type BrowserAction = {
  /**
   * 种类
   */
  kind: 'BrowserAction';
};

/**
 * BrowserClickAction
 *
 * 模式用于点击元素。
 */
export type BrowserClickAction = {
  /**
   * 索引
   *
   * 要单击的元素的索引（来自 browser_get_state）
   */
  index: number;
  /**
   * 种类
   */
  kind: 'BrowserClickAction';
  /**
   * 新标签
   *
   * 是否在新选项卡中打开任何结果导航。 默认值：False
   */
  new_tab?: boolean;
};

/**
 * BrowserClickTool
 *
 * 用于单击浏览器元素的工具。
 */
export type BrowserClickTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserClickTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserCloseTabAction
 *
 * 模式用于关闭浏览器选项卡。
 */
export type BrowserCloseTabAction = {
  /**
   * 种类
   */
  kind: 'BrowserCloseTabAction';
  /**
   * 选项卡 ID
   *
   * 要关闭的选项卡的 4 个字符选项卡 ID（来自 browser_list_tabs）
   */
  tab_id: string;
};

/**
 * BrowserCloseTabTool
 *
 * 用于关闭浏览器选项卡的工具。
 */
export type BrowserCloseTabTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserCloseTabTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserGetContentAction
 *
 * 模式用于获取Markdown中的页面内容。
 */
export type BrowserGetContentAction = {
  /**
   * 提取链接
   *
   * 内容中是否包含链接（默认：False）
   */
  extract_links?: boolean;
  /**
   * 种类
   */
  kind: 'BrowserGetContentAction';
  /**
   * 从字符开始
   *
   * 页面内容中开始的字符索引（默认值：0）
   */
  start_from_char?: number;
};

/**
 * BrowserGetContentTool
 *
 * 用于获取Markdown中页面内容的工具。
 */
export type BrowserGetContentTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetContentTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserGetStateAction
 *
 * 模式用于获取浏览器状态。
 */
export type BrowserGetStateAction = {
  /**
   * 包括屏幕截图
   *
   * 是否包含当前页面的屏幕截图。 默认值：False
   */
  include_screenshot?: boolean;
  /**
   * 种类
   */
  kind: 'BrowserGetStateAction';
};

/**
 * BrowserGetStateTool
 *
 * 获取浏览器状态的工具。
 */
export type BrowserGetStateTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetStateTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserGetStorageAction
 *
 * 模式用于获取浏览器存储（cookie、本地存储、会话存储）。
 */
export type BrowserGetStorageAction = {
  /**
   * 种类
   */
  kind: 'BrowserGetStorageAction';
};

/**
 * BrowserGetStorageTool
 *
 * 用于获取浏览器存储空间的工具。
 */
export type BrowserGetStorageTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetStorageTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserGoBackAction
 *
 * 模式用于返回浏览器历史记录。
 */
export type BrowserGoBackAction = {
  /**
   * 种类
   */
  kind: 'BrowserGoBackAction';
};

/**
 * BrowserGoBackTool
 *
 * 用于返回浏览器历史记录的工具。
 */
export type BrowserGoBackTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGoBackTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserListTabsAction
 *
 * 模式用于列出浏览器选项卡。
 */
export type BrowserListTabsAction = {
  /**
   * 种类
   */
  kind: 'BrowserListTabsAction';
};

/**
 * BrowserListTabsTool
 *
 * 用于列出浏览器选项卡的工具。
 */
export type BrowserListTabsTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserListTabsTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserNavigateAction
 *
 * 模式用于浏览器导航。
 */
export type BrowserNavigateAction = {
  /**
   * 种类
   */
  kind: 'BrowserNavigateAction';
  /**
   * 新标签
   *
   * 是否在新选项卡中打开。 默认值：False
   */
  new_tab?: boolean;
  /**
   * 网址
   *
   * 要导航到的 URL
   */
  url: string;
};

/**
 * BrowserNavigateTool
 *
 * 浏览器导航工具。
 */
export type BrowserNavigateTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserNavigateTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserObservation
 *
 * 浏览器操作的基址观测结果。
 */
export type BrowserObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 完整输出保存目录
   *
   * 保存完整输出文件的目录
   */
  full_output_save_dir?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'BrowserObservation';
  /**
   * 截图数据
   *
   * Base64 屏幕截图数据（如果有）
   */
  screenshot_data?: string | null;
};

/**
 * BrowserScrollAction
 *
 * 模式用于滚动页面。
 */
export type BrowserScrollAction = {
  /**
   * 方向
   *
   * 滚动方向。 选项：“向上”、“向下”。 默认值：“向下”
   */
  direction?: 'up' | 'down';
  /**
   * 种类
   */
  kind: 'BrowserScrollAction';
};

/**
 * BrowserScrollTool
 *
 * 用于滚动浏览器页面的工具。
 */
export type BrowserScrollTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserScrollTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserSetStorageAction
 *
 * 模式用于设置浏览器存储（cookie、本地存储、会话存储）。
 */
export type BrowserSetStorageAction = {
  /**
   * 种类
   */
  kind: 'BrowserSetStorageAction';
  /**
   * 存储状态
   *
   * 包含“cookies”和“origins”的存储状态字典（来自browser_get_storage）
   */
  storage_state: {
    [key: string]: unknown;
  };
};

/**
 * BrowserSetStorageTool
 *
 * 用于设置浏览器存储的工具。
 */
export type BrowserSetStorageTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserSetStorageTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserStartRecordingAction
 *
 * 模式用于启动浏览器会话记录。
 */
export type BrowserStartRecordingAction = {
  /**
   * 种类
   */
  kind: 'BrowserStartRecordingAction';
};

/**
 * BrowserStartRecordingTool
 *
 * 用于启动浏览器会话记录的工具。
 */
export type BrowserStartRecordingTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserStartRecordingTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserStopRecordingAction
 *
 * 模式用于停止浏览器会话记录。
 */
export type BrowserStopRecordingAction = {
  /**
   * 种类
   */
  kind: 'BrowserStopRecordingAction';
};

/**
 * BrowserStopRecordingTool
 *
 * 用于停止浏览器会话记录的工具。
 */
export type BrowserStopRecordingTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserStopRecordingTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserSwitchTabAction
 *
 * 模式用于切换浏览器选项卡。
 */
export type BrowserSwitchTabAction = {
  /**
   * 种类
   */
  kind: 'BrowserSwitchTabAction';
  /**
   * 选项卡 ID
   *
   * 4 字符要切换到的选项卡 ID（从 browser_list_tabs）
   */
  tab_id: string;
};

/**
 * BrowserSwitchTabTool
 *
 * 用于切换浏览器选项卡的工具。
 */
export type BrowserSwitchTabTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserSwitchTabTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserToolSet
 *
 * 一组所有浏览器工具。
 *
 * 该工具集包括所有可用的浏览器相关工具
 * 用于与网页交互。
 *
 * 该工具集自动检查 Chromium 可用性
 * 创建时会自动安装，如果丢失则自动安装。
 */
export type BrowserToolSet = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * BrowserTypeAction
 *
 * 模式用于将文本输入到元素中。
 */
export type BrowserTypeAction = {
  /**
   * 索引
   *
   * 输入元素的索引（来自browser_get_state）
   */
  index: number;
  /**
   * 种类
   */
  kind: 'BrowserTypeAction';
  /**
   * 文字
   *
   * 要输入的文本
   */
  text: string;
};

/**
 * BrowserTypeTool
 *
 * 用于在浏览器元素中输入文本的工具。
 */
export type BrowserTypeTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserTypeTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * CanvasExtensionBackend
 *
 * 模式-1 Canvas 应用程序的可选可信后端声明。
 */
export type CanvasExtensionBackend = {
  /**
   * 精氨酸
   */
  argv: Array<string>;
  /**
   * 文物
   */
  artifacts: {
    [key: string]: CanvasExtensionBackendArtifact;
  };
  health?: CanvasExtensionBackendHealth;
  /**
   * 继承环境
   */
  inherit_environment?: Array<string>;
  /**
   * 模式版本
   */
  schema_version: 1;
};

/**
 * CanvasExtensionBackendArtifact
 *
 * 一个平台的不可变本地或 HTTPS 后端工件。
 */
export type CanvasExtensionBackendArtifact = {
  /**
   * 路径
   *
   * 包相关的 .tar.gz 工件路径
   */
  path: string;
  /**
   * 沙256
   *
   * 小写 SHA-256 校验和
   */
  sha256: string;
  /**
   * 条带组件
   *
   * 要删除的主要存档路径组件
   */
  strip_components?: number;
  /**
   * 网址
   *
   * 公共 HTTPS .tar.gz 工件 URL
   */
  url?: string | null;
};

/**
 * CanvasExtensionBackendHealth
 *
 * 后端进程的环回 HTTP 就绪探测。
 */
export type CanvasExtensionBackendHealth = {
  /**
   * 间隔秒数
   */
  interval_seconds?: number;
  /**
   * 路径
   */
  path?: string;
  /**
   * 超时秒
   */
  timeout_seconds?: number;
};

/**
 * CanvasExtensionContributes
 *
 * 贡献 Canvas UI 的扩展。
 */
export type CanvasExtensionContributes = {
  /**
   * 页数
   *
   * 贡献给 Canvas 导航的页面
   */
  pages?: Array<CanvasExtensionPage>;
};

/**
 * CanvasExtensionManifest
 *
 * 画布扩展清单 (``canvas-extension.json``)。
 */
export type CanvasExtensionManifest = {
  /**
   * 可选的显式准备并启动后端服务
   */
  backend?: CanvasExtensionBackend | null;
  /**
   * 贡献此扩展适用于 Canvas UI
   */
  contributes?: CanvasExtensionContributes;
  /**
   * 描述
   *
   * 扩展说明
   */
  description?: string;
  /**
   * 显示名称
   *
   * 人类可读的扩展名
   */
  display_name: string;
  /**
   * 入口
   *
   * 相对于扩展包根目录的捆绑包入口文件的路径
   */
  entrypoint: string;
  /**
   * 图标
   *
   * 相对于扩展包根目录，到 SVG 图标的路径
   */
  icon?: string | null;
  /**
   * 名称
   *
   * 扩展名（kebab-case）
   */
  name: string;
  /**
   * 模式版本
   *
   * 清单模式版本
   */
  schema_version: number;
  /**
   * 版本
   *
   * 扩展版本
   */
  version: string;
};

/**
 * CanvasExtensionPage
 *
 * 通过扩展向 Canvas UI 提供单个页面。
 */
export type CanvasExtensionPage = {
  /**
   * 身份证号
   *
   * 扩展内的唯一贡献 ID
   */
  id: string;
  /**
   * 路径
   *
   * 页面安装的路由，e.g。 '/dashboard'
   */
  path: string;
  /**
   * 标题
   *
   * Canvas 导航中显示的页面标题
   */
  title: string;
};

/**
 * ClassifyAndSwitchLLMAction
 *
 * 触发当前任务的分类并切换LLM配置文件。
 */
export type ClassifyAndSwitchLlmAction = {
  /**
   * 种类
   */
  kind: 'ClassifyAndSwitchLLMAction';
};

/**
 * ClassifyAndSwitchLLMObservation
 *
 * 对任务进行分类并切换 LLM 配置文件的结果。
 */
export type ClassifyAndSwitchLlmObservation = {
  /**
   * 主动模型
   *
   * 由激活的配置文件配置的模型（如果可用）。
   */
  active_model?: string | null;
  /**
   * 所选班级
   *
   * 匹配类的描述，或者当没有类匹配且工具返回错误时为 None。
   */
  chosen_class?: string | null;
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'ClassifyAndSwitchLLMObservation';
  /**
   * 型号
   *
   * 已激活的 LLM 配置文件的名称。
   */
  model?: string | null;
};

/**
 * ClassifyAndSwitchLLMTool
 *
 * 对任务进行分类并切换到元配置文件的 LLM 的工具。
 */
export type ClassifyAndSwitchLlmTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ClassifyAndSwitchLLMTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * ClientTool
 *
 * 其执行被推迟到外部客户端的工具。
 *
 * 在对话开始时从：class:`ClientToolSpec` 创建。 智能体
 * 将其视为普通工具并可以调用它； ActionEvent 被发射
 * 超过 WebSocket 供客户端处理。
 */
export type ClientTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 客户端工具名称
   *
   * 每个实例的工具名称来自 ClientToolSpec。
   */
  client_tool_name: string;
  /**
   * 描述
   */
  description: string;
  /**
   * 输入模式
   *
   * 原来的JSON模式为工具的参数，由客户端提供。 将工具导出到 LLM 时逐字使用，以便保留客户端定义的约束（枚举、嵌套对象、边界、additionalProperties、...）。
   */
  input_schema: {
    [key: string]: unknown;
  };
  /**
   * 种类
   */
  kind: 'ClientTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * ClientToolObservation
 *
 * 调用客户端工具时返回观测结果。
 *
 * 实际执行发生在客户端； SDK 返回
 * 这个确认使得智能体循环可以继续。
 */
export type ClientToolObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'ClientToolObservation';
};

/**
 * ClientToolSpec
 *
 * 由客户端定义的工具，在外部执行（不是由 SDK）。
 *
 * 客户端在 ``POST /conversations`` 中传递这些规范来注册工具
 * 其执行是在 SDK (e.g.) 之外由前端处理
 * 监听 ActionEvents 超过 WebSocket）。
 */
export type ClientToolSpecInput = {
  /**
   * 该工具的可选 MCP 样式注释。 当省略时，该工具将被保守地对待（而不是只读），因此要求智能体在调用它之前预测安全风险。
   */
  annotations?: ToolAnnotationsInput | null;
  /**
   * 描述
   *
   * LLM 中显示的说明解释了何时以及如何使用此工具。
   */
  description: string;
  /**
   * 名称
   *
   * 智能体将使用唯一的工具名称来调用该工具。
   */
  name: string;
  /**
   * 参数
   *
   * JSON 模式描述工具的输入参数。 必须是一个对象模式。
   */
  parameters?: {
    [key: string]: unknown;
  };
};

/**
 * ClientToolSpec
 *
 * 由客户端定义的工具，在外部执行（不是由 SDK）。
 *
 * 客户端在 ``POST /conversations`` 中传递这些规范来注册工具
 * 其执行是在 SDK (e.g.) 之外由前端处理
 * 监听 ActionEvents 超过 WebSocket）。
 */
export type ClientToolSpecOutput = {
  /**
   * 该工具的可选 MCP 样式注释。 当省略时，该工具将被保守地对待（而不是只读），因此要求智能体在调用它之前预测安全风险。
   */
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   *
   * LLM 中显示的说明解释了何时以及如何使用此工具。
   */
  description: string;
  /**
   * 名称
   *
   * 智能体将使用唯一的工具名称来调用该工具。
   */
  name: string;
  /**
   * 参数
   *
   * JSON 模式描述工具的输入参数。 必须是一个对象模式。
   */
  parameters?: {
    [key: string]: unknown;
  };
};

/**
 * CmdOutputMetadata
 *
 * 从 PS1 捕获的其他元数据
 */
export type CmdOutputMetadata = {
  /**
   * 退出代码
   *
   * 最后执行的命令的退出代码。
   */
  exit_code?: number;
  /**
   * 主机名
   *
   * 机器的主机名。
   */
  hostname?: string | null;
  /**
   * PID
   *
   * 最后执行的命令的进程 ID。
   */
  pid?: number;
  /**
   * 前缀
   *
   * 添加到命令输出的前缀
   */
  prefix?: string;
  /**
   * Py解释器路径
   *
   * 当前 Python 解释器的路径（如果有）。
   */
  py_interpreter_path?: string | null;
  /**
   * 后缀
   *
   * 添加到命令输出的后缀
   */
  suffix?: string;
  /**
   * 用户名
   *
   * 当前用户的用户名。
   */
  username?: string | null;
  /**
   * 工作目录
   *
   * 当前工作目录。
   */
  working_dir?: string | null;
};

/**
 * 上下文压缩
 *
 * 此操作表示对话历史记录的上下文压缩正在发生。
 */
export type Condensation = {
  /**
   * 忘记事件 ID
   *
   * 被遗忘的事件的 ID（从给予 LLM 的 `View` 中删除）。
   */
  forgotten_event_ids?: Array<string>;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'Condensation';
  /**
   * Llm 响应 ID
   *
   * 生成此事件的 LLM 响应的完成或响应 ID
   */
  llm_response_id: string;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 总结
   *
   * 事件的简要总结。
   */
  summary?: string | null;
  /**
   * 摘要偏移量
   *
   * 到结果视图开始处的可选偏移量（删除被遗忘的事件后），指示应插入摘要的位置。 如果未提供，摘要将不会插入到视图中。
   */
  summary_offset?: number | null;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * CondensationRequest
 *
 * 此操作用于请求对话历史记录的上下文压缩。
 *
 * 属性：
 * action (str)：动作类型，即ActionType.CONDENSATION_REQUEST。
 */
export type CondensationRequest = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'CondensationRequest';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * CondensationSummaryEvent
 *
 * 该事件代表上下文压缩器生成的摘要。
 */
export type CondensationSummaryEvent = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'CondensationSummaryEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 总结
   */
  summary: string;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

export type CondenserBaseInput =
  | ({
      kind: 'openhands__sdk__context__condenser__llm_summarizing_condenser__LLMSummarizingCondenser-Input__1';
    } & LlmSummarizingCondenserInput)
  | ({
      kind: 'openhands__sdk__context__condenser__no_op_condenser__NoOpCondenser-Input__1';
    } & NoOpCondenserInput)
  | ({
      kind: 'openhands__sdk__context__condenser__pipeline_condenser__PipelineCondenser-Input__1';
    } & PipelineCondenserInput);

export type CondenserBaseOutput =
  | ({
      kind: 'openhands__sdk__context__condenser__llm_summarizing_condenser__LLMSummarizingCondenser-Output__1';
    } & LlmSummarizingCondenserOutput)
  | ({
      kind: 'openhands__sdk__context__condenser__no_op_condenser__NoOpCondenser-Output__1';
    } & NoOpCondenserOutput)
  | ({
      kind: 'openhands__sdk__context__condenser__pipeline_condenser__PipelineCondenser-Output__1';
    } & PipelineCondenserOutput);

/**
 * ConfirmRisky
 */
export type ConfirmRiskyInput = {
  /**
   * 确认未知
   */
  confirm_unknown?: boolean;
  /**
   * 种类
   */
  kind?: 'ConfirmRisky';
  threshold?: SecurityRisk;
};

/**
 * ConfirmRisky
 */
export type ConfirmRiskyOutput = {
  /**
   * 确认未知
   */
  confirm_unknown?: boolean;
  /**
   * 种类
   */
  kind: 'ConfirmRisky';
  threshold?: SecurityRisk;
};

export type ConfirmationPolicyBaseInput =
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__AlwaysConfirm-Input__1';
    } & AlwaysConfirmInput)
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__ConfirmRisky-Input__1';
    } & ConfirmRiskyInput)
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__NeverConfirm-Input__1';
    } & NeverConfirmInput);

export type ConfirmationPolicyBaseOutput =
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__AlwaysConfirm-Output__1';
    } & AlwaysConfirmOutput)
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__ConfirmRisky-Output__1';
    } & ConfirmRiskyOutput)
  | ({
      kind: 'openhands__sdk__security__confirmation_policy__NeverConfirm-Output__1';
    } & NeverConfirmOutput);

/**
 * ConfirmationResponseRequest
 *
 * 载荷接受或拒绝待处理的操作。
 */
export type ConfirmationResponseRequest = {
  /**
   * 接受
   */
  accept: boolean;
  /**
   * 原因
   */
  reason?: string;
};

/**
 * ConversationContainerOptions
 *
 * 对话容器的资源。
 *
 * 只有 Docker 运行时在创建对话时应用它们
 * 容器； 本地对话会忽略它们。 未设置的字段保留
 * 服务器配置的限制； 一套取代它并且不受它限制。
 */
export type ConversationContainerOptions = {
  /**
   * 浏览器
   *
   * False 关闭浏览器。 True 无法为没有图像的图像打开它。
   */
  browser?: boolean;
  /**
   * 中央处理器
   *
   * 容器可以使用的 CPUs 数量 (`docker run --cpus`)。 取代服务器的限制并且不受其限制。
   */
  cpus?: number | null;
  /**
   * 内存
   *
   * `docker run --memory` 语法中的容器内存限制； 取代服务器的限制并且不受其限制。
   */
  memory?: string | null;
};

/**
 * ConversationErrorEvent
 *
 * 会话级失败即被不发送回LLM。
 *
 * 当出现意外情况时，对话运行时会发出此事件
 * 异常冒出并阻止运行循环继续。 它是
 * 供客户端应用程序（e.g.、UI）显示顶级错误
 * 状态，并让编排做出反应。 它不是观测结果，而是
 * 不可转换为 LLM。
 *
 * 与AgentErrorEvent的区别：
 * - 不依赖于任何tool_name/tool_call_id（AgentErrorEvent是一个工具
 * 观测结果).
 * - 通常 source='environment' 并且运行循环移动到 ERROR 状态，
 * 而 AgentErrorEvent 的 source='智能体' 并且对话可以
 * 继续。
 */
export type ConversationErrorEvent = {
  /**
   * 为 API 消费者提供安全的结构化错误语义。
   */
  classification?: ErrorClassification | null;
  /**
   * 代码
   *
   * 错误代码 - 通常是一种类型
   */
  code: string;
  /**
   * 详情
   *
   * 有关错误的详细信息
   */
  detail: string;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'ConversationErrorEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   *
   * 本次活动的来源
   */
  source: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * ConversationExecutionStatus
 *
 * 枚举代表会话当前的执行状态。
 */
export type ConversationExecutionStatus =
  | 'idle'
  | 'running'
  | 'paused'
  | 'waiting_for_confirmation'
  | 'finished'
  | 'error'
  | 'stuck'
  | 'deleting';

/**
 * ConversationInfo
 *
 * 有关在没有运行时沙箱的情况下本地运行的对话的信息。
 */
export type ConversationInfo = {
  /**
   * 激活知识技能
   *
   * 激活知识技能名称列表
   */
  activated_knowledge_skills?: Array<string>;
  /**
   * 对话中运行的智能体。
   */
  agent: AgentBaseOutput;
  /**
   * 智能体状态
   *
   * 用于在迭代中持续存在的智能体特定运行时状态的字典。
   */
  agent_state?: {
    [key: string]: unknown;
  };
  /**
   * 可用型号
   *
   * 对 ACP 服务器为此会话提供的模型进行建模，从 ``ACPAgent.available_models``（ACP 会话响应上的 ``models.availableModels`` 字段）开始。 每个条目都包含``model_id``和一个可选的``name``/``description``.，Surfaced verbatim，客户端可以自行渲染模型选择器并解析``current_model_id``，服务器不做名称校验。 对于不具备 (UNSTABLE) 功能的 ACP 服务器和本机 OpenHands 智能体为空。 客户端合同：``current_model_id`` 应该不确保是一个成员 —— 强制 ``acp_model`` 重写可能会忽略不在列表中的模型 —— 因此，缺失时显示 '原始 ID'。 有些条目是不透明的别名，其人类身份存在于 ``description`` (e.g. 克劳德-智能体-ACP的``"default"`` -> ``"Opus 4.7 with 1M context · ..."``）。
   */
  available_models?: Array<AcpModelInfo>;
  /**
   * 被阻止的操作
   *
   * 被 PreToolUse 挂钩阻止的操作，由操作 ID 键入
   */
  blocked_actions?: {
    [key: string]: string;
  };
  /**
   * 被阻止的消息
   *
   * 消息被 UserPromptSubmit 挂钩阻止，由消息 ID 键入
   */
  blocked_messages?: {
    [key: string]: string;
  };
  /**
   * 客户端工具
   *
   * 为此对话注册的客户定义的工具规格。 这样，客户端通过会话ID重新连接时，可以在同步已持久化事件之前注册动态的 ClientAction_* 动作类型，从而避免 '未知类型' 反序列化错误。
   */
  client_tools?: Array<ClientToolSpecOutput>;
  confirmation_policy?: ConfirmationPolicyBaseOutput;
  /**
   * 创建于
   */
  created_at?: string;
  /**
   * 当前型号 ID
   *
   * 本次会议实际使用的模型是智能体。 对于 ACP 智能体，它从 ``ACPAgent.current_model_id`` 中解除（从 ACP 会话响应上的 ``models.currentModelId`` 字段填充，或者当调用者强制覆盖时从 ``acp_model`` 填充）。 可能是不透明的别名（e.g. 克劳德-智能体-ACP的``"default"``); 将其与 ``available_models`` 进行匹配以获得显示标签。 ``None`` 适用于未显示该字段的旧 ACP 服务器，或者智能体仍在初始化时。 Native OpenHands 智能体留下这个 ``None`` — 消费者应该阅读 ``agent.llm.model`` 来了解这些。
   */
  current_model_id?: string | null;
  execution_status?: ConversationExecutionStatus;
  /**
   * 从对话 ID 分叉
   *
   * 此会话的分叉 ID。 ``None`` 用于直接创建的对话（不通过 fork）。
   */
  forked_from_conversation_id?: string | null;
  /**
   * 从事件 ID 分叉
   *
   * 此对话分叉的事件 ID。 ``None`` 用于非分叉对话或整个对话分叉。
   */
  forked_from_event_id?: string | null;
  /**
   * 此对话的挂钩配置。 包括 PreToolUse、PostToolUse、UserPromptSubmit、SessionStart、SessionEnd 和 Stop 挂钩的定义。
   */
  hook_config?: HookConfig | null;
  /**
   * 身份证号
   *
   * 唯一的对话ID
   */
  id: string;
  /**
   * 调用技能
   *
   * 通过 `invoke_skill` 工具明确调用的渐进式披露技能的名称。
   */
  invoked_skills?: Array<string>;
  /**
   * 最后用户消息 ID
   *
   * 用于钩子块检查的最新用户 MessageEvent ID。 发出用户消息时进行更新，以便 Agent.step 可以弹出 blocked_messages，而无需扫描事件日志。 如果是None，则跳过钩子阻止检查（遗留对话）。
   */
  last_user_message_id?: string | null;
  /**
   * 启动此对话的智能体配置文件的出处快照。 在创建时通过 ``agent_profile_id`` 开始对话时设置； ``None`` 用于直接从 ``agent`` 或 ``agent_settings`` 开始的对话。 客户端使用它来识别哪个智能体配置文件是最新的，而无需进行脆弱的设置比较。
   */
  launched_agent_profile?: LaunchedAgentProfile | null;
  /**
   * 叶事件 ID
   *
   * 对话树的 HEAD：下一个附加事件的父级。 ``None`` 表示空树（或者，对于预告片对话，线性尾部）。 通过 ``navigate`` 移动它会重新定位智能体运行的活动分支。
   */
  leaf_event_id?: string | null;
  /**
   * 最大迭代次数
   *
   * 智能体在单次运行中可以执行的最大迭代次数。
   */
  max_iterations?: number;
  metrics?: MetricsSnapshot | null;
  /**
   * 家长对话 ID
   *
   * 拥有此对话的 ID。 ``None`` 用于高层对话。
   */
  parent_conversation_id?: string | null;
  /**
   * 持久化目录
   *
   * 用于持久会话状态和事件的目录。 如果为 None，则对话将不是已持久化。
   */
  persistence_dir?: string | null;
  /**
   * 执行运行时的可用性。 当托管服务器管理运行时生命周期时，目录响应将填充此内容。
   */
  runtime_info?: ConversationRuntimeInfo | null;
  /**
   * 注册表用于处理机密和敏感数据
   */
  secret_registry?: SecretRegistry;
  /**
   * 可选的安全分析器来评估操作风险。
   */
  security_analyzer?: SecurityAnalyzerBaseOutput | null;
  /**
   * 用于跟踪 LLM 指标的对话统计信息
   */
  stats?: ConversationStats;
  /**
   * 卡住检测
   *
   * 是否启用智能体卡住检测。
   */
  stuck_detection?: boolean;
  /**
   * 子对话 ID
   *
   * 将此对话命名为其父级的对话 ID。 源自服务器目录； Webhook 载荷上为空。 名称反映了 Cloud API 字段。
   */
  sub_conversation_ids?: Array<string>;
  /**
   * 支持运行时模型切换
   *
   * 是否尝试在本次对话中的实时切换模型 - 会告诉内联选择器是否提供实时切换控制。 镜像 SDK 的切换门：``True`` 表示已知的具有切换能力的提供商； ``False`` 对于未知/自定义 ACP 服务器，因为它们的通用配置写入不能保证实时切换原语。 ``False`` 对于本机 OpenHands 智能体，对于声明不支持的已知提供商，并且在对话开始会话之前。
   */
  supports_runtime_model_switch?: boolean;
  /**
   * 标签
   *
   * 对话的键值标签。 键必须是小写字母数字。 值是最多 256 个字符的任意字符串。
   */
  tags?: {
    [key: string]: string;
  };
  /**
   * 标题
   *
   * 用户定义的对话标题
   */
  title?: string | null;
  /**
   * 工具模块 Qualnames
   *
   * 映射到可导入模块限定名的工具名称。 SDK 客户端使用此元数据来恢复附加时反序列化对话工具事件所需的注册。
   */
  tool_module_qualnames?: {
    [key: string]: string;
  };
  /**
   * 更新于
   */
  updated_at?: string;
  /**
   * 工作区被智能体用来执行命令和读/写文件。 不是流程工作目录。
   */
  workspace: BaseWorkspace;
};

/**
 * ConversationPage
 */
export type ConversationPage = {
  /**
   * 项目
   */
  items: Array<ConversationInfo>;
  /**
   * 下一页 ID
   */
  next_page_id?: string | null;
};

/**
 * ConversationRuntimeError
 *
 * 最新运行时生命周期故障的结构化详细信息。
 */
export type ConversationRuntimeError = {
  /**
   * 代码
   */
  code: string;
  /**
   * 留言
   */
  message: string;
};

/**
 * ConversationRuntimeInfo
 *
 * 对话的运行时可用性和恢复信息。
 */
export type ConversationRuntimeInfo = {
  /**
   * 可以恢复
   */
  can_resume: boolean;
  runtime_error?: ConversationRuntimeError | null;
  runtime_status: ConversationRuntimeStatus;
};

/**
 * ConversationRuntimeStatus
 *
 * 执行对话的运行时的可用性。
 */
export type ConversationRuntimeStatus =
  'available' | 'starting' | 'missing' | 'ownership_lost' | 'error';

/**
 * ConversationSortOrder
 *
 * 枚举用于对话排序选项。
 */
export type ConversationSortOrder =
  'CREATED_AT' | 'UPDATED_AT' | 'CREATED_AT_DESC' | 'UPDATED_AT_DESC';

/**
 * ConversationStateUpdateEvent
 *
 * 包含对话状态更新的事件。
 *
 * 每当对话状态发生变化时，都会通过 WebSocket 发送此事件，
 * 允许远程客户端停留在同步中而不进行 REST API 调用。
 *
 * 所有字段都是相应 ConversationState 字段的已序列化版本
 * 以确保与WebSocket传输的兼容性。
 */
export type ConversationStateUpdateEvent = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 钥匙
   *
   * 此状态更新事件的唯一键
   */
  key?: string;
  /**
   * 种类
   */
  kind: 'ConversationStateUpdateEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 价值
   *
   * 已序列化对话状态更新
   */
  value?: unknown;
};

export type ConversationStats = {
  [key: string]: unknown;
};

/**
 * ConversationWorktreeOptions
 *
 * 服务器如何创建对话的工作树 (``worktree=True``)。
 */
export type ConversationWorktreeOptions = {
  /**
   * 基地
   *
   * 工作树从什么分支而来； `ref` 使用 `ref`。
   */
  base?: 'default_branch' | 'head' | 'ref';
  /**
   * 分支前缀
   *
   * 工作树分支名称的开头； 对话 ID 结束。
   */
  branch_prefix?: string;
  /**
   * 参考号
   *
   * 从 `base` 为 `ref` 时开始分支、标记或提交到分支。
   */
  ref?: string | null;
};

export type CriticBaseInput =
  | ({
      kind: 'openhands__sdk__critic__impl__agent_finished__AgentFinishedCritic-Input__1';
    } & AgentFinishedCriticInput)
  | ({
      kind: 'openhands__sdk__critic__impl__api__critic__APIBasedCritic-Input__1';
    } & ApiBasedCriticInput)
  | ({
      kind: 'openhands__sdk__critic__impl__empty_patch__EmptyPatchCritic-Input__1';
    } & EmptyPatchCriticInput)
  | ({
      kind: 'openhands__sdk__critic__impl__pass_critic__PassCritic-Input__1';
    } & PassCriticInput);

export type CriticBaseOutput =
  | ({
      kind: 'openhands__sdk__critic__impl__agent_finished__AgentFinishedCritic-Output__1';
    } & AgentFinishedCriticOutput)
  | ({
      kind: 'openhands__sdk__critic__impl__api__critic__APIBasedCritic-Output__1';
    } & ApiBasedCriticOutput)
  | ({
      kind: 'openhands__sdk__critic__impl__empty_patch__EmptyPatchCritic-Output__1';
    } & EmptyPatchCriticOutput)
  | ({
      kind: 'openhands__sdk__critic__impl__pass_critic__PassCritic-Output__1';
    } & PassCriticOutput);

/**
 * CriticResult
 *
 * 评论家的结果是一个分数和一条消息。
 */
export type CriticResult = {
  /**
   * 留言
   *
   * 解释分数的可选消息。
   */
  message: string | null;
  /**
   * 元数据
   *
   * 有关评论家评估的可选元数据。 可以包含 event_ids 和 categorized_features 以进行可视化。
   */
  metadata?: {
    [key: string]: unknown;
  } | null;
  /**
   * 分数
   *
   * 预测成功的概率介于 0 和 1 之间。
   */
  score: number;
};

/**
 * DelegateAction
 *
 * 模式用于委托操作。
 */
export type DelegateAction = {
  /**
   * 智能体类型
   *
   * `spawn`命令的可选参数。 每个 ID 的智能体类型列表（e.g.、[“研究员”、“程序员”]）。 如果 ID 被省略或留空，则使用默认的通用智能体。
   */
  agent_types?: Array<string> | null;
  /**
   * 命令
   *
   * 要运行的命令。 允许的选项有：`spawn`、`delegate`。
   */
  command: 'spawn' | 'delegate';
  /**
   * 识别号
   *
   * `spawn`命令的必需参数。 用于初始化子智能体的标识符列表。
   */
  ids?: Array<string> | null;
  /**
   * 种类
   */
  kind: 'DelegateAction';
  /**
   * 任务
   *
   * `delegate`命令的必需参数。 将子智能体标识符映射到任务描述的字典。
   */
  tasks?: {
    [key: string]: string;
  } | null;
};

/**
 * DelegateObservation
 *
 * 观测结果来自授权操作。
 */
export type DelegateObservation = {
  /**
   * 命令
   *
   * 执行的命令
   */
  command: 'spawn' | 'delegate';
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'DelegateObservation';
};

/**
 * DeleteResponse
 */
export type DeleteResponse = {
  /**
   * 已删除
   */
  deleted?: boolean;
};

/**
 * EditAction
 *
 * 模式用于编辑操作。
 */
export type EditAction = {
  /**
   * 预期替代品
   *
   * 预计替换数量。 默认为 1。 当您想要替换多个匹配项时使用。 如果实际计数不匹配，编辑将失败。
   */
  expected_replacements?: number;
  /**
   * 文件路径
   *
   * 要修改的文件的路径。
   */
  file_path: string;
  /**
   * 种类
   */
  kind: 'EditAction';
  /**
   * 新弦
   *
   * 要替换它的文本。
   */
  new_string: string;
  /**
   * 旧弦
   *
   * 要替换的文本。 要创建新文件，请使用空字符串。 必须与文件中的确切文本（包括空格）匹配。
   */
  old_string: string;
};

/**
 * EditObservation
 *
 * 观测结果来自编辑文件。
 */
export type EditObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 文件路径
   *
   * 已编辑的文件路径。
   */
  file_path?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 是新文件
   *
   * 是否创建了新文件。
   */
  is_new_file?: boolean;
  /**
   * 种类
   */
  kind: 'EditObservation';
  /**
   * 新内容
   *
   * 编辑后的内容。
   */
  new_content?: string | null;
  /**
   * 旧内容
   *
   * 编辑前的内容。
   */
  old_content?: string | null;
  /**
   * 更换件
   *
   * 实际更换的数量。
   */
  replacements_made?: number;
};

/**
 * EditTool
 *
 * 通过查找/替换编辑文件的工具。
 */
export type EditTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'EditTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * EmptyPatchCritic
 *
 * 只评估 git 补丁是否非空的批评家。
 *
 * 这位批评家只检查一个标准：
 * - 生成的git补丁非空（实际进行了更改）
 *
 * 与AgentFinishedCritic不同，这个批评家不检查是否正确
 * 智能体用 FinishAction 完成。
 */
export type EmptyPatchCriticInput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind?: 'EmptyPatchCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * EmptyPatchCritic
 *
 * 只评估 git 补丁是否非空的批评家。
 *
 * 这位批评家只检查一个标准：
 * - 生成的git补丁非空（实际进行了更改）
 *
 * 与AgentFinishedCritic不同，这个批评家不检查是否正确
 * 智能体用 FinishAction 完成。
 */
export type EmptyPatchCriticOutput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind: 'EmptyPatchCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * EnsembleSecurityAnalyzer
 *
 * 将多个分析仪连接在一起并承担最坏情况的风险。
 *
 * 使用它作为您在对话中设置的顶级分析器。 它
 * 呼叫每个儿童分析员，收集他们的风险评估，以及
 * 返回最高的具体风险。 它不执行任何检测，
 * 提取，或自身标准化。
 *
 * UNKNOWN 的工作原理（默认，``propagate_unknown=False``）：if *all*
 * 子项返回 UNKNOWN，集合返回 UNKNOWN（其中
 * ``ConfirmRisky`` 默认确认）。 如果任何孩子返回
 * 具体级别，UNKNOWN 结果被过滤掉，最高的
 * 实体层面获胜。
 *
 * 对于 ``propagate_unknown=True``：如果 *any* 子级返回 UNKNOWN，则
 * 无论其他结果如何，ensemble 都会返回 UNKNOWN。 使用这个
 * 更严格的环境，应触发不完整的评估
 * 确认。
 *
 * 如果子分析器引发异常，它会贡献 HIGH
 * （失败关闭，记录）。 这可以防止损坏的分析仪默默地
 * 降低安全性。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 (
 * EnsembleSecurityAnalyzer,
 * PatternSecurityAnalyzer,
 * PolicyRailSecurityAnalyzer,
 * ConfirmRisky,
 * SecurityRisk,
 * )
 *
 * 分析仪 = EnsembleSecurityAnalyzer(
 * 分析仪=[
 * PolicyRailSecurityAnalyzer(),
 * PatternSecurityAnalyzer(),
 * ]
 * )
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type EnsembleSecurityAnalyzerInput = {
  /**
   * 分析仪
   *
   * 通过最大严重性组合评估的分析器
   */
  analyzers: Array<SecurityAnalyzerBaseInput>;
  /**
   * 种类
   */
  kind?: 'EnsembleSecurityAnalyzer';
  /**
   * 传播未知
   *
   * 当 True 时，任何返回 UNKNOWN 的子项都会导致整体返回 UNKNOWN。 当 False（默认）时，如果任何子级返回具体级别，则 UNKNOWN 会被过滤掉。
   */
  propagate_unknown?: boolean;
};

/**
 * EnsembleSecurityAnalyzer
 *
 * 将多个分析仪连接在一起并承担最坏情况的风险。
 *
 * 使用它作为您在对话中设置的顶级分析器。 它
 * 呼叫每个儿童分析员，收集他们的风险评估，以及
 * 返回最高的具体风险。 它不执行任何检测，
 * 提取，或自身标准化。
 *
 * UNKNOWN 的工作原理（默认，``propagate_unknown=False``）：if *all*
 * 子项返回 UNKNOWN，集合返回 UNKNOWN（其中
 * ``ConfirmRisky`` 默认确认）。 如果任何孩子返回
 * 具体级别，UNKNOWN 结果被过滤掉，最高的
 * 实体层面获胜。
 *
 * 对于 ``propagate_unknown=True``：如果 *any* 子级返回 UNKNOWN，则
 * 无论其他结果如何，ensemble 都会返回 UNKNOWN。 使用这个
 * 更严格的环境，应触发不完整的评估
 * 确认。
 *
 * 如果子分析器引发异常，它会贡献 HIGH
 * （失败关闭，记录）。 这可以防止损坏的分析仪默默地
 * 降低安全性。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 (
 * EnsembleSecurityAnalyzer,
 * PatternSecurityAnalyzer,
 * PolicyRailSecurityAnalyzer,
 * ConfirmRisky,
 * SecurityRisk,
 * )
 *
 * 分析仪 = EnsembleSecurityAnalyzer(
 * 分析仪=[
 * PolicyRailSecurityAnalyzer(),
 * PatternSecurityAnalyzer(),
 * ]
 * )
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type EnsembleSecurityAnalyzerOutput = {
  /**
   * 分析仪
   *
   * 通过最大严重性组合评估的分析器
   */
  analyzers: Array<SecurityAnalyzerBaseOutput>;
  /**
   * 种类
   */
  kind: 'EnsembleSecurityAnalyzer';
  /**
   * 传播未知
   *
   * 当 True 时，任何返回 UNKNOWN 的子项都会导致整体返回 UNKNOWN。 当 False（默认）时，如果任何子级返回具体级别，则 UNKNOWN 会被过滤掉。
   */
  propagate_unknown?: boolean;
};

/**
 * ErrorClassification
 *
 * 唯一跨越事件/API 边界的失败元数据。
 *
 * 它是故意很小的。 ``detail`` 仅在本地检查以进行映射
 * 这个封闭词汇表存在广泛的第三方错误； 它永远不会被复制
 * 此处或发送至遥测。
 */
export type ErrorClassification = {
  /**
   * 错误编号
   */
  error_id?: string | null;
  kind: FailureKind;
  /**
   * 可重试
   */
  retryable: boolean;
  /**
   * 用户操作
   */
  user_action?: 'none' | 'retry' | 'settings';
};

export type Event =
  | ({
      kind: 'openhands__agent_server__models__ServerErrorEvent-Output__1';
    } & ServerErrorEvent)
  | ({
      kind: 'openhands__sdk__event__acp_tool_call__ACPToolCallEvent-Output__1';
    } & AcpToolCallEvent)
  | ({
      kind: 'openhands__sdk__event__condenser__Condensation-Output__1';
    } & Condensation)
  | ({
      kind: 'openhands__sdk__event__condenser__CondensationRequest-Output__1';
    } & CondensationRequest)
  | ({
      kind: 'openhands__sdk__event__condenser__CondensationSummaryEvent-Output__1';
    } & CondensationSummaryEvent)
  | ({
      kind: 'openhands__sdk__event__conversation_error__ConversationErrorEvent-Output__1';
    } & ConversationErrorEvent)
  | ({
      kind: 'openhands__sdk__event__conversation_state__ConversationStateUpdateEvent-Output__1';
    } & ConversationStateUpdateEvent)
  | ({
      kind: 'openhands__sdk__event__hook_execution__HookExecutionEvent-Output__1';
    } & HookExecutionEvent)
  | ({
      kind: 'openhands__sdk__event__llm_completion_log__LLMCompletionLogEvent-Output__1';
    } & LlmCompletionLogEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__action__ActionEvent-Output__1';
    } & ActionEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__message__MessageEvent-Output__1';
    } & MessageEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__AgentErrorEvent-Output__1';
    } & AgentErrorEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__ObservationEvent-Output__1';
    } & ObservationEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__UserRejectObservation-Output__1';
    } & UserRejectObservation)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__system__SystemPromptEvent-Output__1';
    } & SystemPromptEvent)
  | ({
      kind: 'openhands__sdk__event__security__SecurityAnalysisEvent-Output__1';
    } & SecurityAnalysisEvent)
  | ({
      kind: 'openhands__sdk__event__streaming_delta__StreamingDeltaEvent-Output__1';
    } & StreamingDeltaEvent)
  | ({
      kind: 'openhands__sdk__event__token__TokenEvent-Output__1';
    } & TokenEvent)
  | ({
      kind: 'openhands__sdk__event__user_action__InterruptEvent-Output__1';
    } & InterruptEvent)
  | ({
      kind: 'openhands__sdk__event__user_action__PauseEvent-Output__1';
    } & PauseEvent);

/**
 * EventSortOrder
 *
 * 枚举用于事件排序选项。
 */
export type EventSortOrder = 'TIMESTAMP' | 'TIMESTAMP_DESC';

/**
 * ExecuteBashRequest
 */
export type ExecuteBashRequest = {
  /**
   * 命令
   *
   * 要执行的 bash 命令
   */
  command: string;
  /**
   * 西德
   *
   * 当前工作目录
   */
  cwd?: string | null;
  /**
   * 超时
   *
   * 允许命令运行的最大秒数。
   */
  timeout?: number;
};

/**
 * ExposedUrl
 *
 * 代表沙盒中暴露的 URL。
 */
export type ExposedUrl = {
  /**
   * 名称
   */
  name: string;
  /**
   * 港口
   */
  port: number;
  /**
   * 网址
   */
  url: string;
};

/**
 * FailureKind
 */
export type FailureKind =
  | 'auth'
  | 'quota'
  | 'rate_limit'
  | 'config'
  | 'transient'
  | 'agent_action'
  | 'internal'
  | 'unknown';

/**
 * FallbackStrategy
 *
 * 封装 LLM 调用的回退方案行为。
 *
 * 当主节点 LLM 因暂时性错误而失败时（在重试之后），
 * 该策略尝试从 LLMProfileStore 配置文件中加载备用 LLMs。
 * 回退方案是每次调用：每个新请求都从主模型开始。
 */
export type FallbackStrategy = {
  /**
   * 回退方案法学硕士
   *
   * 有序的 LLM 个配置文件名称列表以尝试解决暂时性故障。
   */
  fallback_llms: Array<string>;
  /**
   * 配置文件存储目录
   *
   * 包含配置文件的目录的路径。 如果未指定，则默认为 `.openhands/profiles`。
   */
  profile_store_dir?: string | string | null;
};

/**
 * FetchPluginRequest
 *
 * 请求正文严格获取插件而不安装它。
 */
export type FetchPluginRequest = {
  /**
   * 参考号
   *
   * 分支、标记或提交
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径（对于 monorepos）
   */
  repo_path?: string | null;
  /**
   * 机密
   *
   * 机密用于扩展源和参考中的 ${VAR} 占位符
   */
  secrets?: {
    [key: string]: SecretSourceInput;
  };
  /**
   * 来源
   *
   * 插件git源
   */
  source: string;
  /**
   * 超时
   *
   * Git 超时秒
   */
  timeout?: number;
};

/**
 * FetchPluginResponse
 *
 * 严格获取插件源的响应。
 */
export type FetchPluginResponse = {
  /**
   * 命令
   */
  commands: Array<string>;
  /**
   * 清单
   */
  manifest: {
    [key: string]: JsonValue;
  };
  /**
   * 路径
   */
  path: string;
  /**
   * 回购路径
   */
  repo_path: string | null;
  /**
   * 已解决的参考
   */
  resolved_ref: string | null;
  /**
   * 技能
   */
  skills: Array<string>;
  /**
   * 来源
   */
  source: string;
};

/**
 * FileBrowserEntry
 */
export type FileBrowserEntry = {
  /**
   * 标签
   */
  label: string;
  /**
   * 路径
   */
  path: string;
};

/**
 * FileEditorAction
 *
 * 模式用于文件编辑器操作。
 */
export type FileEditorAction = {
  /**
   * 命令
   *
   * 要运行的命令。 允许的选项有：`view`、`create`、`str_replace`、`insert`、`undo_edit`。
   */
  command: 'view' | 'create' | 'str_replace' | 'insert' | 'undo_edit';
  /**
   * 文件文本
   *
   * `create`命令必需的参数，包含要创建的文件的内容。
   */
  file_text?: string | null;
  /**
   * 插入行
   *
   * `insert`命令的必需参数。 `new_str` 将插入之后 `path` 的第 `insert_line` 行。
   */
  insert_line?: number | null;
  /**
   * 种类
   */
  kind: 'FileEditorAction';
  /**
   * 新街
   *
   * `str_replace`命令的可选参数包含新字符串（如果未给出，则不会添加任何字符串）。 `insert` 命令的必需参数，包含要插入的字符串。
   */
  new_str?: string | null;
  /**
   * 老街
   *
   * `str_replace` 命令的必需参数包含要替换的 `path` 中的字符串。
   */
  old_str?: string | null;
  /**
   * 路径
   *
   * 文件或目录的绝对路径。
   */
  path: string;
  /**
   * 视野范围
   *
   * 当`path`指向文件时，`view`命令的可选参数。 如果给出 None，则显示完整文件。 如果提供，该文件将显示在指定的行号范围 e.g 中。 [11, 12] 将显示第 11 行和第 12 行。 索引从 1 开始。 设置 `[start_line, -1]` 显示从 `start_line` 到文件末尾的所有行。
   */
  view_range?: Array<number> | null;
};

/**
 * FileEditorObservation
 *
 * 可以呈现为 CLI 输出的 ToolResult。
 */
export type FileEditorObservation = {
  /**
   * 命令
   *
   * 运行的命令：`view`、`create`、`str_replace`、`insert` 或 `undo_edit`。
   */
  command: 'view' | 'create' | 'str_replace' | 'insert' | 'undo_edit';
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'FileEditorObservation';
  /**
   * 新内容
   *
   * 编辑后的文件内容。
   */
  new_content?: string | null;
  /**
   * 旧内容
   *
   * 编辑前的文件内容。
   */
  old_content?: string | null;
  /**
   * 路径
   *
   * 已编辑的文件路径。
   */
  path?: string | null;
  /**
   * 上一个存在
   *
   * 指示该文件以前是否存在。 如果没有，它就被创建了。
   */
  prev_exist?: boolean;
};

/**
 * FileEditorTool
 *
 * 自动初始化 FileEditorExecutor 的 ToolDefinition 子类。
 */
export type FileEditorTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'FileEditorTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * FileEntry
 *
 * 有关文件或目录的信息。
 */
export type FileEntry = {
  /**
   * 是目录
   *
   * 该条目是否是一个目录
   */
  is_directory: boolean;
  /**
   * 修改时间
   *
   * 最后修改时间戳
   */
  modified_time: string;
  /**
   * 名称
   *
   * 文件或目录的名称
   */
  name: string;
  /**
   * 路径
   *
   * 文件或目录的绝对路径
   */
  path: string;
  /**
   * 尺寸
   *
   * 文件大小（以字节为单位）（0 表示目录）
   */
  size: number;
};

/**
 * FileUploadResult
 */
export type FileUploadResult = {
  /**
   * 文件大小
   *
   * 写入目标的字节数
   */
  file_size: number;
  /**
   * 成功
   */
  success?: boolean;
};

/**
 * FinishAction
 */
export type FinishAction = {
  /**
   * 种类
   */
  kind: 'FinishAction';
  /**
   * 留言
   *
   * 发送给用户的最终消息。
   */
  message: string;
};

/**
 * FinishObservation
 *
 * 观测结果完成任务后返回。
 * FinishAction本身包含发送给用户的消息，所以没有
 * 这里需要额外的字段。
 */
export type FinishObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'FinishObservation';
};

/**
 * FinishTool
 *
 * 用于发出任务或对话完成信号的工具。
 */
export type FinishTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'FinishTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * ForkConversationRequest
 *
 * 载荷分叉对话。
 */
export type ForkConversationRequest = {
  /**
   * 来自事件 ID
   *
   * 如果设置，则仅分叉直到并包括此事件的分支，并在那里设置分叉的 HEAD。 如果 null（默认），则复制整个对话。
   */
  from_event_id?: string | null;
  /**
   * 身份证号
   *
   * 分叉对话的 ID（如果 null，则自动生成）
   */
  id?: string | null;
  /**
   * 重置指标
   *
   * 如果 True，则成本/代币统计数据在分叉上重新开始。 如果为 False，则从源复制指标。
   */
  reset_metrics?: boolean;
  /**
   * 标签
   *
   * 分叉对话的可选标签。 键必须是小写字母数字。
   */
  tags?: {
    [key: string]: string;
  } | null;
  /**
   * 标题
   *
   * 分叉对话的可选标题
   */
  title?: string | null;
};

/**
 * GitChange
 */
export type GitChange = {
  /**
   * 路径
   */
  path: string;
  status: GitChangeStatus;
};

/**
 * GitChangeStatus
 */
export type GitChangeStatus = 'MOVED' | 'ADDED' | 'DELETED' | 'UPDATED';

/**
 * GitCommit
 */
export type GitCommit = {
  /**
   * 作者
   */
  author: string;
  /**
   * 沙
   */
  sha: string;
  /**
   * 短煞
   */
  short_sha: string;
  /**
   * 主题
   */
  subject: string;
  /**
   * 时间戳
   */
  timestamp: string;
};

/**
 * GitCommitsPage
 */
export type GitCommitsPage = {
  /**
   * 提交
   */
  commits: Array<GitCommit>;
  /**
   * 还有更多
   */
  has_more: boolean;
};

/**
 * GitDiff
 */
export type GitDiff = {
  /**
   * 修改
   */
  modified: string | null;
  /**
   * 原创
   */
  original: string | null;
};

/**
 * GitProvider
 *
 * 支持的 git 托管提供商。
 */
export type GitProvider = 'github' | 'gitlab' | 'bitbucket' | 'azure_devops';

/**
 * GitProviderRepository
 */
export type GitProviderRepository = {
  /**
   * 全名
   */
  full_name: string;
  /**
   * Git 提供者
   */
  git_provider: string;
  /**
   * 身份证号
   */
  id: string;
  /**
   * 是公开的
   */
  is_public: boolean;
  /**
   * 总行
   */
  main_branch?: string | null;
  /**
   * 推向
   */
  pushed_at?: string | null;
  /**
   * 观星者计数
   */
  stargazers_count?: number | null;
};

/**
 * GitProviderRepositoryPage
 */
export type GitProviderRepositoryPage = {
  /**
   * 项目
   */
  items: Array<GitProviderRepository>;
  /**
   * 失踪token
   */
  missing_token?: boolean;
  /**
   * 下一页 ID
   */
  next_page_id?: string | null;
};

/**
 * GlobAction
 *
 * 模式用于全局模式匹配操作。
 */
export type GlobAction = {
  /**
   * 种类
   */
  kind: 'GlobAction';
  /**
   * 路径
   *
   * 要搜索的目录（绝对路径）。 默认为当前工作目录。
   */
  path?: string | null;
  /**
   * 图案
   *
   * 匹配文件的 glob 模式 (e.g., "***.js", "src***.ts")
   */
  pattern: string;
};

/**
 * GlobObservation
 *
 * 观测结果来自全局模式匹配操作。
 */
export type GlobObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 文件
   *
   * 按修改时间排序的匹配文件路径列表
   */
  files: Array<string>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'GlobObservation';
  /**
   * 图案
   *
   * 使用的 glob 模式
   */
  pattern: string;
  /**
   * 搜索路径
   *
   * 搜索到的目录
   */
  search_path: string;
  /**
   * 截断的
   *
   * 结果是否被截断为 100 个文件
   */
  truncated?: boolean;
};

/**
 * GlobTool
 *
 * 自动初始化 GlobExecutor 的 ToolDefinition 子类。
 */
export type GlobTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'GlobTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * GraySwanAnalyzer
 *
 * 使用 GraySwan 的 Cygnal API 进行 AI 安全监控的安全分析器。
 *
 * 该分析器将对话历史记录和待处理操作发送到 GraySwan
 * Cygnal API 用于安全分析。 API 返回违规分数，即
 * 映射到 SecurityRisk 级别。
 *
 * 环境变量：
 * GRAYSWAN_API_KEY：GraySwan 身份验证所需的 API 键
 * GRAYSWAN_POLICY_ID：自定义 GraySwan 策略的可选策略 ID
 *
 * 示例：
 * >>> 从 openhands.sdk.security.grayswan 导入 GraySwanAnalyzer
 * >>> 分析器 = GraySwanAnalyzer()
 * >>> risk = analyzer.security_risk(action_event)
 */
export type GraySwanAnalyzerInput = {
  /**
   * API 钥匙
   *
   * GraySwan API 键（通过 GRAYSWAN_API_KEY 环境变量）
   */
  api_key?: null;
  /**
   * API 网址
   *
   * GraySwan 辛格纳尔 API 端点
   */
  api_url?: string;
  /**
   * 历史限制
   *
   * 要包含为上下文的最近事件数
   */
  history_limit?: number;
  /**
   * 种类
   */
  kind?: 'GraySwanAnalyzer';
  /**
   * 低门槛
   *
   * LOW 分类的风险阈值（分数 <= 阈值）
   */
  low_threshold?: number;
  /**
   * 最大消息字符数
   *
   * 对话处理的最大字符数
   */
  max_message_chars?: number;
  /**
   * 中等门槛
   *
   * MEDIUM 分类的风险阈值（分数 <= 阈值）
   */
  medium_threshold?: number;
  /**
   * 策略 ID
   *
   * GraySwan 策略 ID（通过 GRAYSWAN_POLICY_ID 环境变量）
   */
  policy_id?: string | null;
  /**
   * 超时
   *
   * 请求超时（秒）
   */
  timeout?: number;
};

/**
 * GraySwanAnalyzer
 *
 * 使用 GraySwan 的 Cygnal API 进行 AI 安全监控的安全分析器。
 *
 * 该分析器将对话历史记录和待处理操作发送到 GraySwan
 * Cygnal API 用于安全分析。 API 返回违规分数，即
 * 映射到 SecurityRisk 级别。
 *
 * 环境变量：
 * GRAYSWAN_API_KEY：GraySwan 身份验证所需的 API 键
 * GRAYSWAN_POLICY_ID：自定义 GraySwan 策略的可选策略 ID
 *
 * 示例：
 * >>> 从 openhands.sdk.security.grayswan 导入 GraySwanAnalyzer
 * >>> 分析器 = GraySwanAnalyzer()
 * >>> risk = analyzer.security_risk(action_event)
 */
export type GraySwanAnalyzerOutput = {
  /**
   * API 钥匙
   *
   * GraySwan API 键（通过 GRAYSWAN_API_KEY 环境变量）
   */
  api_key?: null;
  /**
   * API 网址
   *
   * GraySwan 辛格纳尔 API 端点
   */
  api_url?: string;
  /**
   * 历史限制
   *
   * 要包含为上下文的最近事件数
   */
  history_limit?: number;
  /**
   * 种类
   */
  kind: 'GraySwanAnalyzer';
  /**
   * 低门槛
   *
   * LOW 分类的风险阈值（分数 <= 阈值）
   */
  low_threshold?: number;
  /**
   * 最大消息字符数
   *
   * 对话处理的最大字符数
   */
  max_message_chars?: number;
  /**
   * 中等门槛
   *
   * MEDIUM 分类的风险阈值（分数 <= 阈值）
   */
  medium_threshold?: number;
  /**
   * 策略 ID
   *
   * GraySwan 策略 ID（通过 GRAYSWAN_POLICY_ID 环境变量）
   */
  policy_id?: string | null;
  /**
   * 超时
   *
   * 请求超时（秒）
   */
  timeout?: number;
};

/**
 * GrepAction
 *
 * 模式用于 grep 内容搜索操作。
 */
export type GrepAction = {
  /**
   * 包括
   *
   * 用于过滤要搜索的文件的可选文件模式（e.g.、“*.js”、“*.{ts,tsx}”）
   */
  include?: string | null;
  /**
   * 种类
   */
  kind: 'GrepAction';
  /**
   * 路径
   *
   * 要搜索的目录（绝对路径）。 默认为当前工作目录。
   */
  path?: string | null;
  /**
   * 图案
   *
   * 要在文件内容中搜索的正则表达式模式
   */
  pattern: string;
};

/**
 * GrepObservation
 *
 * 观测结果来自 grep 内容搜索操作。
 */
export type GrepObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 包含模式
   *
   * 使用的文件模式过滤器
   */
  include_pattern?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'GrepObservation';
  /**
   * 火柴
   *
   * 包含模式的文件路径列表
   */
  matches: Array<string>;
  /**
   * 图案
   *
   * 使用的正则表达式模式
   */
  pattern: string;
  /**
   * 搜索路径
   *
   * 搜索到的目录
   */
  search_path: string;
  /**
   * 截断的
   *
   * 结果是否被截断为 100 个文件
   */
  truncated?: boolean;
};

/**
 * GrepTool
 *
 * 自动初始化 GrepExecutor 的 ToolDefinition 子类。
 */
export type GrepTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'GrepTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * HTTPValidationError
 */
export type HttpValidationError = {
  /**
   * 详情
   */
  detail?: Array<ValidationError>;
};

/**
 * HomeResponse
 */
export type HomeResponse = {
  /**
   * 收藏夹
   */
  favorites?: Array<FileBrowserEntry>;
  /**
   * 首页
   */
  home: string;
  /**
   * 地点
   */
  locations?: Array<FileBrowserEntry>;
};

/**
 * HookConfig
 *
 * 所有钩子的配置。
 *
 * 可以通过从 `.openhands/hooks.json` 加载或
 * 通过直接用类型字段实例化：
 *
 * # 使用类型化字段直接实例化（推荐）：
 * 配置 = HookConfig(
 * pre_tool_use=[
 * HookMatcher(
 * 匹配器=“终端”，
 * 钩子=[HookDefinition(命令=“block_dangerous.sh”)]
 * )
 * ]
 * )
 *
 * # 从 JSON 文件加载：
 * 配置文件为 HookConfig.load(".openhands/hooks.json")
 */
export type HookConfig = {
  /**
   * 后期工具使用
   *
   * 工具执行后运行的挂钩
   */
  post_tool_use?: Array<HookMatcher>;
  /**
   * 工具使用前
   *
   * 在工具执行之前运行的挂钩
   */
  pre_tool_use?: Array<HookMatcher>;
  /**
   * 会议结束
   *
   * 会话结束时运行的挂钩
   */
  session_end?: Array<HookMatcher>;
  /**
   * 会话开始
   *
   * 会话开始时运行的挂钩
   */
  session_start?: Array<HookMatcher>;
  /**
   * 停止
   *
   * 当智能体尝试停止时运行的钩子
   */
  stop?: Array<HookMatcher>;
  /**
   * 用户提示词提交
   *
   * 当用户提交提示词时运行的钩子
   */
  user_prompt_submit?: Array<HookMatcher>;
};

/**
 * HookDefinition
 *
 * 单个钩子定义。
 */
export type HookDefinition = {
  /**
   * 异步
   */
  async?: boolean;
  /**
   * 命令
   */
  command: string;
  /**
   * 最大迭代次数
   */
  max_iterations?: number;
  /**
   * 名称
   */
  name?: string | null;
  /**
   * 提示词
   */
  prompt?: string | null;
  /**
   * 系统提示词
   */
  system_prompt?: string | null;
  /**
   * 超时
   */
  timeout?: number;
  /**
   * 工具
   */
  tools?: Array<string>;
  type?: HookType;
};

/**
 * HookExecutionEvent
 *
 * 执行钩子时发出事件。
 *
 * 此事件提供了对钩子执行的可观察性，包括：
 * - 触发了哪种钩子类型
 * - 运行的命令
 * - 结果（成功/阻止/错误）
 * - 钩子的任何输出
 *
 * 这允许客户端通过事件流跟踪钩子执行。
 */
export type HookExecutionEvent = {
  /**
   * 操作 ID
   *
   * 与此挂钩关联的操作的 ID (PreToolUse/PostToolUse)
   */
  action_id?: string | null;
  /**
   * 附加上下文
   *
   * 由钩子注入的附加上下文 (e.g., for UserPromptSubmit)
   */
  additional_context?: string | null;
  /**
   * 被阻止
   *
   * 钩子是否阻止了操作（退出代码2或拒绝）
   */
  blocked?: boolean;
  /**
   * 错误
   *
   * 如果钩子执行失败，则出现错误消息
   */
  error?: string | null;
  /**
   * 退出代码
   *
   * 从钩子命令中退出代码
   */
  exit_code: number;
  /**
   * 挂钩命令
   *
   * 执行的钩子命令
   */
  hook_command: string;
  /**
   * 挂钩事件类型
   *
   * 触发本次执行的钩子事件类型
   */
  hook_event_type:
    'PreToolUse' | 'PostToolUse' | 'UserPromptSubmit' | 'SessionStart' | 'SessionEnd' | 'Stop';
  /**
   * 挂钩输入
   *
   * 传递给钩子的输入数据
   */
  hook_input?: {
    [key: string]: unknown;
  } | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'HookExecutionEvent';
  /**
   * 消息编号
   *
   * 与此挂钩关联的消息的 ID (UserPromptSubmit)
   */
  message_id?: string | null;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 原因
   *
   * 钩子提供的原因（用于阻塞）
   */
  reason?: string | null;
  /**
   * 来源
   *
   * 钩子执行事件的源始终是“钩子”
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 斯特德尔
   *
   * 钩子的标准错误
   */
  stderr?: string;
  /**
   * 标准输出
   *
   * 钩子的标准输出
   */
  stdout?: string;
  /**
   * 成功
   *
   * hook是否执行成功
   */
  success: boolean;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具名称
   *
   * PreToolUse/PostToolUse 挂钩的工具名称
   */
  tool_name?: string | null;
};

/**
 * HookMatcher
 *
 * 根据模式将事件与挂钩匹配。
 *
 * 支持精确匹配、通配符 (*) 和正则表达式（自动检测或 /pattern/).
 */
export type HookMatcher = {
  /**
   * 挂钩
   */
  hooks?: Array<HookDefinition>;
  /**
   * 匹配器
   */
  matcher?: string;
};

/**
 * HookType
 *
 * 可以执行的钩子类型。
 */
export type HookType = 'command' | 'prompt' | 'agent';

/**
 * HooksRequest
 *
 * 加载钩子的请求主体。
 */
export type HooksRequest = {
  /**
   * 项目目录
   *
   * 工作区项目挂钩的目录路径
   */
  project_dir?: string | null;
};

/**
 * HooksResponse
 *
 * 包含钩子配置的响应。
 */
export type HooksResponse = {
  /**
   * 钩子配置从工作区加载，如果没有找到则从 None 加载
   */
  hook_config?: HookConfig | null;
};

/**
 * 图标
 *
 * 用于在用户界面中显示的图标。
 */
export type Icon = {
  /**
   * 模仿型
   */
  mimeType?: string | null;
  /**
   * 尺寸
   */
  sizes?: Array<string> | null;
  /**
   * 源代码
   */
  src: string;
  [key: string]: unknown;
};

/**
 * ImageContent
 */
export type ImageContent = {
  /**
   * 缓存提示词
   */
  cache_prompt?: boolean;
  /**
   * 图片网址
   */
  image_urls: Array<string>;
  /**
   * 类型
   */
  type?: 'image';
};

/**
 * InitRequest
 *
 * 运行时配置在 /api/init 时间交付。
 *
 * 每个字段都是可选的，并且会覆盖休眠中的等效字段
 * ``Config``. 未提供的字段保留服务器构建时的值
 * with（通常来自 pod 启动时的环境变量）。 可重写的集合
 * 领域故意狭窄——它涵盖了今天的价值观
 * “env-var Shape”并且必须针对每个用户进行更改，而不是在映像构建时更改
 * 配置（Python deps、插件集等），它保持绑定到
 * 温水池的味道。
 */
export type InitRequest = {
  /**
   * 允许 Cors 起源
   *
   * CORS origins 添加到现有的本地主机白名单。
   */
  allow_cors_origins?: Array<string> | null;
  /**
   * Bash 活动目录
   *
   * bash 事件所在的目录已持久化。 通常位于已安装的用户内部工作区。
   */
  bash_events_dir?: string | null;
  /**
   * 对话工作树根
   *
   * 对话 git 工作树的根目录。 覆盖它以指向已安装的用户工作区。
   */
  conversation_worktree_root?: string | null;
  /**
   * 对话路径
   *
   * 对话所在目录为已持久化。 覆盖它以指向已安装的用户工作区。
   */
  conversations_path?: string | null;
  /**
   * 环境
   *
   * 在会话服务开始之前进行设置的处理环境变量。 对于被工具消耗的凭据很有用 (e.g. GITHUB_TOKEN). 这些适用于``os.environ.update``； 现有值被覆盖。
   */
  env?: {
    [key: string]: string;
  } | null;
  /**
   * 最多并发次运行
   *
   * 覆盖对话步骤并发限制。
   */
  max_concurrent_runs?: number | null;
  /**
   * 上一个机密键
   *
   * secret_key 的早期值（或它回退到的第一个 session_api_key 的值），仅用于解密保存在其下的值； 下次保存时，它们将使用当前密钥重新加密。
   */
  previous_secret_keys?: Array<unknown> | null;
  /**
   * 机密钥匙
   *
   * 对称机密用于加密已持久化机密。 如果未提供，则回退到第一个 session_api_key（与默认配置行为匹配）。
   */
  secret_key?: null;
  /**
   * 会话 API 键
   *
   * 每用户会话 API 键。 如果提供，所有后续 /api* 请求都必须通过 X-Session-API-Key 标头使用这些密钥之一进行身份验证。
   */
  session_api_keys?: Array<string> | null;
  /**
   * 此 Pod 的产品分析政策。 如果没有这个，暖池 Pod 会保留其启动时使用的任何模式（通常“禁用”），因此需要遥测的部署必须在此处提供它。
   */
  telemetry?: TelemetrySpec | null;
  /**
   * 网址
   *
   * 可访问此服务器的外部 URL，用于根路径计算。 仅当尚未在休眠配置中设置时才受到尊重。
   */
  web_url?: string | null;
  /**
   * Webhook
   *
   * 每个用户 Webhook (e.g. 对于流式传输事件返回）。
   */
  webhooks?: Array<WebhookSpec> | null;
};

/**
 * InitStatus
 */
export type InitStatus = {
  /**
   * 错误
   *
   * 如果之前的 /api/init 尝试失败，则会显示错误消息。 状态回滚到 ``dormant``，因此可以重试 /api/init。
   */
  error?: string | null;
  /**
   * 状态
   *
   * ``dormant`` — 服务器已启动，但正在等待 /api/init. ``initializing`` — 已收到 /api/init，服务正在启动。 ``ready``——初始化完成； 所有 /api* 条路线均已上线。
   */
  state: 'dormant' | 'initializing' | 'ready';
};

/**
 * InputMetadata
 *
 * 任务技能输入的元数据。
 */
export type InputMetadata = {
  /**
   * 描述
   *
   * 输入参数说明
   */
  description: string;
  /**
   * 名称
   *
   * 输入参数名称
   */
  name: string;
};

/**
 * InstallCanvasExtensionRequest
 *
 * 安装画布扩展的请求正文。
 */
export type InstallCanvasExtensionRequest = {
  /**
   * 力
   *
   * 如果 True，则覆盖现有安装
   */
  force?: boolean;
  /**
   * 参考号
   *
   * 可选的分支、标记或提交安装
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径（对于 monorepos）
   */
  repo_path?: string | null;
  /**
   * 来源
   *
   * Canvas 扩展源 - git URL、GitHub 简写或本地路径。 示例：“GitHub：所有者/仓库”、“/path/to/extension'”
   */
  source: string;
};

/**
 * InstallPluginRequest
 *
 * 安装插件的请求正文。
 */
export type InstallPluginRequest = {
  /**
   * 力
   *
   * 如果 True，则覆盖现有安装
   */
  force?: boolean;
  /**
   * 参考号
   *
   * 可选的分支、标记或提交安装
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径（对于 monorepos）
   */
  repo_path?: string | null;
  /**
   * 来源
   *
   * 插件源 - git URL、GitHub 简写（GitHub:owner/repo，可选地后跟存储库中插件的路径）或本地路径。 示例： 'GitHub:OpenHands/extensions/plugins/city-weather', '/path/to/plugin'
   */
  source: string;
};

/**
 * InstallSkillRequest
 *
 * 安装技能的请求正文。
 */
export type InstallSkillRequest = {
  /**
   * 力
   *
   * 如果 True，则覆盖现有安装
   */
  force?: boolean;
  /**
   * 参考号
   *
   * 可选的分支、标记或提交安装
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径（对于 monorepos）
   */
  repo_path?: string | null;
  /**
   * 来源
   *
   * 技能来源 - git URL、GitHub 简写（GitHub:owner/repo，可选地后跟存储库中技能的路径）或本地路径。 示例： 'GitHub:OpenHands/extensions/skills/github'、' https://github.com/OpenHands/extensions.git'  和 repo_path 'skills/github'、'/path/to/skill'
   */
  source: string;
};

/**
 * InstalledCanvasExtensionResponse
 *
 * 包含已安装画布扩展信息的响应。
 */
export type InstalledCanvasExtensionResponse = {
  /**
   * 描述
   *
   * 画布扩展说明
   */
  description?: string;
  /**
   * 启用
   *
   * 是否启用canvas扩展
   */
  enabled?: boolean;
  /**
   * 安装路径
   *
   * 扩展安装路径
   */
  install_path: string;
  /**
   * 安装于
   *
   * ISO 8601 安装时间戳
   */
  installed_at: string;
  /**
   * 扩展程序的已验证清单（display_name、contributes.pages、...）。 None 如果无法再读取已安装的清单。
   */
  manifest?: CanvasExtensionManifest | null;
  /**
   * 名称
   *
   * 画布扩展名
   */
  name: string;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径
   */
  repo_path?: string | null;
  /**
   * 请求的参考号
   *
   * 安装时请求的分支、标记或提交。 None 表示没有请求引用（跟踪源的默认分支）。
   */
  requested_ref?: string | null;
  /**
   * 已解决的参考
   *
   * 已解决 git 提交 SHA
   */
  resolved_ref?: string | null;
  /**
   * 来源
   *
   * 原始来源 (e.g., 'GitHub:owner/repo')
   */
  source: string;
  /**
   * 版本
   *
   * 画布扩展版本
   */
  version?: string;
};

/**
 * InstalledCanvasExtensionsListResponse
 *
 * 包含已安装画布扩展列表的响应。
 */
export type InstalledCanvasExtensionsListResponse = {
  /**
   * 画布扩展
   */
  canvas_extensions: Array<InstalledCanvasExtensionResponse>;
};

/**
 * InstalledPluginResponse
 *
 * 包含已安装插件信息的响应。
 */
export type InstalledPluginResponse = {
  /**
   * 描述
   *
   * 插件说明
   */
  description?: string;
  /**
   * 启用
   *
   * 插件是否启用
   */
  enabled?: boolean;
  /**
   * 文件
   *
   * 插件文件，相对于 install_path（如果加载失败则为 None）
   */
  files?: Array<string> | null;
  /**
   * 安装路径
   *
   * 插件安装路径
   */
  install_path: string;
  /**
   * 安装于
   *
   * ISO 8601 安装时间戳
   */
  installed_at: string;
  /**
   * 名称
   *
   * 插件名称
   */
  name: string;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径
   */
  repo_path?: string | null;
  /**
   * 已解决的参考
   *
   * 已解决 git 提交 SHA
   */
  resolved_ref?: string | null;
  /**
   * 技能
   *
   * 插件中捆绑的技能（如果加载失败则为None）
   */
  skills?: Array<PluginSkillSummary> | null;
  /**
   * 来源
   *
   * 原始来源 (e.g., 'GitHub:owner/repo')
   */
  source: string;
  /**
   * 版本
   *
   * 插件版本
   */
  version?: string;
};

/**
 * InstalledPluginsListResponse
 *
 * 包含已安装插件列表的响应。
 */
export type InstalledPluginsListResponse = {
  /**
   * 插件
   */
  plugins: Array<InstalledPluginResponse>;
};

/**
 * InstalledSkillResponse
 *
 * 包含已安装技能信息的响应。
 */
export type InstalledSkillResponse = {
  /**
   * 描述
   *
   * 技能说明
   */
  description?: string;
  /**
   * 启用
   *
   * 技能是否开启
   */
  enabled?: boolean;
  /**
   * 安装路径
   *
   * 技能安装路径
   */
  install_path: string;
  /**
   * 安装于
   *
   * ISO 8601 安装时间戳
   */
  installed_at: string;
  /**
   * 名称
   *
   * 技能名称
   */
  name: string;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径
   */
  repo_path?: string | null;
  /**
   * 已解决的参考
   *
   * 已解决 git 提交 SHA
   */
  resolved_ref?: string | null;
  /**
   * 来源
   *
   * 原始来源 (e.g., 'GitHub:owner/repo')
   */
  source: string;
  /**
   * 版本
   *
   * 技能版本
   */
  version?: string;
};

/**
 * InstalledSkillsListResponse
 *
 * 包含已安装技能列表的响应。
 */
export type InstalledSkillsListResponse = {
  /**
   * 技能
   */
  skills: Array<InstalledSkillResponse>;
};

/**
 * InterruptEvent
 *
 * 指示智能体在操作过程中中断的事件。
 *
 * 与：class:`PauseEvent` 不同，它在智能体个步骤之间生效，
 * 中断会立即取消正在进行的 LLM 调用。 的
 * 对话状态设置为 PAUSED，以便稍后可以恢复。
 */
export type InterruptEvent = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'InterruptEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * InvokeSkillAction
 */
export type InvokeSkillAction = {
  /**
   * 种类
   */
  kind: 'InvokeSkillAction';
  /**
   * 名称
   *
   * 要调用的已加载技能的名称。
   */
  name: string;
};

/**
 * InvokeSkillObservation
 */
export type InvokeSkillObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'InvokeSkillObservation';
  /**
   * 技能名称
   *
   * 此观测结果对应的技能名称。
   */
  skill_name: string;
};

/**
 * InvokeSkillTool
 *
 * 用于显式调用渐进式披露技能的内置工具。
 */
export type InvokeSkillTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'InvokeSkillTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * IterativeRefinementConfig
 *
 * 基于评论家反馈的迭代细化配置。
 *
 * 当附加到 CriticBase 时，Conversation.run() 方法将
 * 如果批评分数低于阈值，则自动重试任务。
 *
 * 示例：
 * critic = APIBasedCritic(
 * server_url="...",
 * api_key="...",
 * model_name=“评论家”，
 * iterative_refinement=IterativeRefinementConfig(
 * success_threshold=0.7,
 * max_iterations=3,
 * ),
 * )
 * 智能体 = Agent(llm=llm, tools=tools, critic=critic)
 * 对话 = Conversation(agent=agent, workspace=workspace)
 * conversation.send_message(“创建一个计算器模块...”)
 * conversation.run() # 如果评论分数 < 0.7 将自动重试
 */
export type IterativeRefinementConfig = {
  /**
   * 最大迭代次数
   *
   * 放弃之前的最大迭代次数。
   */
  max_iterations?: number;
  /**
   * 成功门槛
   *
   * 认为任务成功的分数阈值 (0-1)。
   */
  success_threshold?: number;
};

export type JsonValue =
  | string
  | number
  | number
  | boolean
  | Array<JsonValue>
  | {
      [key: string]: JsonValue;
    }
  | null;

/**
 * KeywordTrigger
 *
 * 触发基于关键字的技能。
 *
 * 当用户查询中出现特定关键字时，这些技能就会被激活。
 */
export type KeywordTrigger = {
  /**
   * 关键词
   */
  keywords: Array<string>;
  /**
   * 类型
   */
  type?: 'keyword';
};

/**
 * LLM
 *
 * OpenHands 智能体的语言模型接口。
 *
 * LLM类提供了与各种交互的统一接口
 * 通过 LiteLLM 库的语言模型。 它处理模型配置，
 * API 身份验证、重试逻辑和工具调用功能。
 *
 * 属性：
 * model：型号名称（e.g.，“gpt-5.6”）。
 * api_key：API键用于身份验证。
 * base_url：自定义 API 基础 URL。
 * num_retries：失败请求的重试次尝试次数。
 * 超时：请求超时（以秒为单位）。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM
 * 从 Pydantic 导入 SecretStr
 *
 * 勒姆 = LLM(
 * 型号=“gpt-5.6”，
 * api_key=SecretStr("你的-API-密钥"),
 * usage_id="我的-智能体"
 * )
 * # 与智能体或对话一起使用
 * ```
 */
export type LlmInput = {
  /**
   * API 钥匙
   *
   * API 键。
   */
  api_key?: string | null;
  /**
   * API 模式
   *
   * LLM API 端点模式。 'auto' 从模型元数据和 SDK 回退方案解析； 使用“聊天”或“响应”来覆盖代理别名和新发布模型的端点选择。
   */
  api_mode?: 'auto' | 'chat' | 'responses';
  /**
   * API 版本
   *
   * API 版本（e.g.，Azure）。
   */
  api_version?: string | null;
  /**
   * 验证类型
   *
   * 身份验证模式为LLM。
   */
  auth_type?: 'api_key' | 'subscription';
  /**
   * AWS 访问密钥 ID
   */
  aws_access_key_id?: string | null;
  /**
   * AWS 基岩运行时端点
   */
  aws_bedrock_runtime_endpoint?: string | null;
  /**
   * AWS 配置文件名称
   */
  aws_profile_name?: string | null;
  /**
   * AWS 区域名称
   */
  aws_region_name?: string | null;
  /**
   * AWS 角色名称
   */
  aws_role_name?: string | null;
  /**
   * AWS 机密访问密钥
   */
  aws_secret_access_key?: string | null;
  /**
   * AWS 会话名称
   */
  aws_session_name?: string | null;
  /**
   * 哦会话令牌
   */
  aws_session_token?: string | null;
  /**
   * 基本网址
   *
   * 定制基地URL。
   */
  base_url?: string | null;
  /**
   * 缓存提示词
   *
   * 启用提示词的缓存。
   */
  caching_prompt?: boolean;
  /**
   * 能力覆盖
   *
   * 显式模型功能覆盖。 支持的键包括 supports_reasoning_effort、thinking_mode（自适应、手动、None 或未知）、supports_sampling_params、supports_prompt_cache、supports_stop_words、supports_responses_api、supports_vision 和 supports_prompt_cache_retention。 覆盖优先于 LiteLLM 元数据和 SDK 回退方案。
   */
  capability_overrides?: {
    [key: string]: boolean | string;
  };
  /**
   * 自定义分词器
   *
   * 用于 token 计数的自定义分词器。
   */
  custom_tokenizer?: string | null;
  /**
   * 禁用停用词
   *
   * 禁用停用词的使用。
   */
  disable_stop_word?: boolean | null;
  /**
   * 禁用视力
   *
   * 如果模型具有视觉功能，则此选项允许禁用图像处理（对于降低成本很有用）。
   */
  disable_vision?: boolean | null;
  /**
   * 删除参数
   */
  drop_params?: boolean;
  /**
   * 启用加密推理
   *
   * 如果是 True，则要求在响应 API 中包含 ['reasoning.encrypted_content']。
   */
  enable_encrypted_reasoning?: boolean;
  /**
   * 扩展思维预算
   *
   * 遗留词元预算模型确认使用手册Anthropic扩展思维。 自适应思维模型被忽略。 对于新集成，首选 reasoning_effort。
   */
  extended_thinking_budget?: number | null;
  /**
   * 额外标头
   *
   * 用于转发到 LiteLLM 请求的可选 HTTP 标头。
   */
  extra_headers?: {
    [key: string]: string;
  } | null;
  /**
   * 回退方案选项：尝试在临时失败时使用备用 LLMs。 FallbackStrategy(fallback_llms=[...]).序列化不包括。 加载后必须重新配置。
   */
  fallback_strategy?: FallbackStrategy | null;
  /**
   * 强制字符串序列化器
   *
   * 发送到 LLM API 时强制使用字符串内容序列化器。 如果为 None（默认），则根据型号自动检测。 对于不支持列表内容的提供者很有用，例如 HuggingFace 和 Groq。
   */
  force_string_serializer?: boolean | null;
  /**
   * 内嵌图像 URL
   *
   * 如果 True, fetch any http(s) image URL 在发送的消息中和消息内嵌入它作为 base64 ``data:``  URL 在发送之前。 如果 None (默认)，根据模型自动检测（某些） APIs 例如 Moonshot 的公共 Kimi 端点拒绝 URL-需要格式化后的图片，且要求使用 base64。 在通过隐藏底层提供者的代理别名到达模型时，显式设置此值e.g. ``litellm_proxy/<custom-alias>``). 仅在时才运行 ``vision_is_active()`` 是 True因此，别名仍然必须被视作具备视觉能力的 SDK feature 注册表或代理模型元数据。
   */
  inline_image_urls?: boolean | null;
  /**
   * 每 token 的投入成本
   *
   * 每个输入的成本 token。 这将在用户日志中可用。
   */
  input_cost_per_token?: number | null;
  /**
   * LiteLLM 额外本体
   *
   * 传递给的附加键值对 LiteLLM's extra_body 参数。 这很有用，用于自定义推理端点需要配置参数、路由或高级功能的额外参数。 注意：并非所有 LLM 提供商支持 extra_body 参数。 一些提供商 (e.g., OpenAI) 可以拒绝未识别的选项请求。 这通常由：- 支持 LiteLLM 代理服务器（路由元数据、追踪） - vLLM 端点 (return_token_ids, etc.) - Custom inference clusters Examples: - Proxy routing: {'trace_version'version': '1.0.0', 'tags': '' ['智能体我的-智能体']} - vLLM features: {'return_token_ids': True}
   */
  litellm_extra_body?: {
    [key: string]: unknown;
  };
  /**
   * 记录完成情况
   *
   * 启用完成记录。
   */
  log_completions?: boolean;
  /**
   * 记录完成文件夹
   *
   * 将 LLM 个完成情况记录到的文件夹。 如果 log_completions 为 True，则为必填项。
   */
  log_completions_folder?: string;
  /**
   * 最大输入 token
   *
   * 最大输入数量token。 请注意，当前未使用该值，运行时的值实际上是 OpenAI 中的总计 token（e.g.128,000 token for GPT-4）。
   */
  max_input_tokens?: number | null;
  /**
   * 最大消息字符数
   *
   * 发送到 LLM 的每个事件/内容的大约最大字符数。
   */
  max_message_chars?: number;
  /**
   * 最大输出 token
   *
   * 最大输出数量token。 这被发送到LLM。
   */
  max_output_tokens?: number | null;
  /**
   * 型号
   *
   * 型号名称。
   */
  model?: string;
  /**
   * 型号规范名称
   *
   * 用于特征注册表查找的可选规范模型名称。 OpenHands SDK 维护一个模型功能注册表，将模型名称映射到功能（e.g.、视觉支持、提示词缓存、响应 API 支持）。 当使用代理或别名的模型标识时，将此字段设置为可唯一标识的模型名称（e.g，'openai/gpt-4o'）以确保正确的能力检测。 如果未提供，“模型”字段将用于功能查找。
   */
  model_canonical_name?: string | null;
  /**
   * 原生工具调用
   *
   * 是否使用原生工具调用。
   */
  native_tool_calling?: boolean;
  /**
   * 数量重试
   */
  num_retries?: number;
  /**
   * 奥拉马基地网址
   */
  ollama_base_url?: string | null;
  /**
   * Openrouter应用程序名称
   */
  openrouter_app_name?: string;
  /**
   * Openrouter 站点 URL
   */
  openrouter_site_url?: string;
  /**
   * 每 token 的输出成本
   *
   * 每个输出的成本 token。 这将在用户日志中可用。
   */
  output_cost_per_token?: number | null;
  /**
   * 提示词缓存保留
   *
   * 提示词缓存的保留策略。 仅针对受支持的型号发送（GPT-5+ 和 GPT-4.1，不包括 Azure 部署）； 明确地为所有其他人剥离。
   */
  prompt_cache_retention?: string | null;
  /**
   * 提供商连接 ID
   *
   * 可选的提供程序连接，每次加载此 LLM 配置文件（使用时读取）时，都会解析并应用其共享 API 密钥和基 URL。 设置后，配置文件不存储其自己的内联 api_key 或 base_url。
   */
  provider_connection_id?: string | null;
  /**
   * 推理努力
   *
   * 提供者中立的推理工作。 常见的值包括 'None'、'最小'、'低'、'中'、'高'、'x高' 和 '最大'。 SDK 接受未来的提供者值并让 LiteLLM 翻译它们。
   */
  reasoning_effort?: 'low' | 'medium' | 'high' | 'xhigh' | 'none' | null;
  /**
   * 推理总结
   *
   * 推理摘要的详细程度。 这是一个字符串，可以是“auto”、“concise”或“detailed”之一。 需要经过验证的 OpenAI 组织。 仅在明确设置时发送。
   */
  reasoning_summary?: 'auto' | 'concise' | 'detailed' | null;
  /**
   * 重试最长等待时间
   */
  retry_max_wait?: number;
  /**
   * 重试最短等待时间
   */
  retry_min_wait?: number;
  /**
   * 重试乘数
   */
  retry_multiplier?: number;
  /**
   * 种子
   *
   * 用于生成随机数的种子。
   */
  seed?: number | null;
  /**
   * 串流
   *
   * 启用来自 LLM 的流式传输响应。 启用后，将为 token 的每个块调用 .completions 和 .responses 中提供的 `on_token` 回调。
   */
  stream?: boolean;
  /**
   * 流空闲超时
   *
   * 异步流式传输响应中块之间的最大秒数。 默认为300s（5分钟）； 设置为 None 禁用。
   */
  stream_idle_timeout?: number | null;
  /**
   * 订阅供应商
   *
   * 用于订阅支持的 LLM 访问的订阅提供商。
   */
  subscription_vendor?: 'openai' | null;
  /**
   * 温度
   *
   * 用于生成响应的采样温度。 默认为 None（使用提供商默认温度）。 设置为 0.0 以获得确定性输出，或设置为更高值 (0.7-1.0) 以获得更有创意的响应。
   */
  temperature?: number | null;
  /**
   * 超时
   *
   * HTTP 和硬每次尝试超时（以秒为单位）。 默认值为 300 秒（5 分钟）。 设置为 None 以禁用硬超时。
   */
  timeout?: number | null;
  /**
   * 前K
   */
  top_k?: number | null;
  /**
   * 顶P
   *
   * 核采样参数。 默认为 None（使用提供程序默认值）。 设置为 0 到 1 之间的值以控制输出的多样性。
   */
  top_p?: number | null;
  /**
   * 使用 ID
   *
   * LLM 的唯一使用标识符。 用于注册表查找、遥测和支出跟踪。
   */
  usage_id?: string;
};

/**
 * LLM
 *
 * OpenHands 智能体的语言模型接口。
 *
 * LLM类提供了与各种交互的统一接口
 * 通过 LiteLLM 库的语言模型。 它处理模型配置，
 * API 身份验证、重试逻辑和工具调用功能。
 *
 * 属性：
 * model：型号名称（e.g.，“gpt-5.6”）。
 * api_key：API键用于身份验证。
 * base_url：自定义 API 基础 URL。
 * num_retries：失败请求的重试次尝试次数。
 * 超时：请求超时（以秒为单位）。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM
 * 从 Pydantic 导入 SecretStr
 *
 * 勒姆 = LLM(
 * 型号=“gpt-5.6”，
 * api_key=SecretStr("你的-API-密钥"),
 * usage_id="我的-智能体"
 * )
 * # 与智能体或对话一起使用
 * ```
 */
export type LlmOutput = {
  /**
   * API 钥匙
   *
   * API 键。
   */
  api_key?: string | null;
  /**
   * API 模式
   *
   * LLM API 端点模式。 'auto' 从模型元数据和 SDK 回退方案解析； 使用“聊天”或“响应”来覆盖代理别名和新发布模型的端点选择。
   */
  api_mode?: 'auto' | 'chat' | 'responses';
  /**
   * API 版本
   *
   * API 版本（e.g.，Azure）。
   */
  api_version?: string | null;
  /**
   * 验证类型
   *
   * 身份验证模式为LLM。
   */
  auth_type?: 'api_key' | 'subscription';
  /**
   * AWS 访问密钥 ID
   */
  aws_access_key_id?: string | null;
  /**
   * AWS 基岩运行时端点
   */
  aws_bedrock_runtime_endpoint?: string | null;
  /**
   * AWS 配置文件名称
   */
  aws_profile_name?: string | null;
  /**
   * AWS 区域名称
   */
  aws_region_name?: string | null;
  /**
   * AWS 角色名称
   */
  aws_role_name?: string | null;
  /**
   * AWS 机密访问密钥
   */
  aws_secret_access_key?: string | null;
  /**
   * AWS 会话名称
   */
  aws_session_name?: string | null;
  /**
   * 哦会话令牌
   */
  aws_session_token?: string | null;
  /**
   * 基本网址
   *
   * 定制基地URL。
   */
  base_url?: string | null;
  /**
   * 缓存提示词
   *
   * 启用提示词的缓存。
   */
  caching_prompt?: boolean;
  /**
   * 能力覆盖
   *
   * 显式模型功能覆盖。 支持的键包括 supports_reasoning_effort、thinking_mode（自适应、手动、None 或未知）、supports_sampling_params、supports_prompt_cache、supports_stop_words、supports_responses_api、supports_vision 和 supports_prompt_cache_retention。 覆盖优先于 LiteLLM 元数据和 SDK 回退方案。
   */
  capability_overrides?: {
    [key: string]: boolean | string;
  };
  /**
   * 自定义分词器
   *
   * 用于 token 计数的自定义分词器。
   */
  custom_tokenizer?: string | null;
  /**
   * 禁用停用词
   *
   * 禁用停用词的使用。
   */
  disable_stop_word?: boolean | null;
  /**
   * 禁用视力
   *
   * 如果模型具有视觉功能，则此选项允许禁用图像处理（对于降低成本很有用）。
   */
  disable_vision?: boolean | null;
  /**
   * 删除参数
   */
  drop_params?: boolean;
  /**
   * 启用加密推理
   *
   * 如果是 True，则要求在响应 API 中包含 ['reasoning.encrypted_content']。
   */
  enable_encrypted_reasoning?: boolean;
  /**
   * 扩展思维预算
   *
   * 遗留词元预算模型确认使用手册Anthropic扩展思维。 自适应思维模型被忽略。 对于新集成，首选 reasoning_effort。
   */
  extended_thinking_budget?: number | null;
  /**
   * 额外标头
   *
   * 用于转发到 LiteLLM 请求的可选 HTTP 标头。
   */
  extra_headers?: {
    [key: string]: string;
  } | null;
  /**
   * 强制字符串序列化器
   *
   * 发送到 LLM API 时强制使用字符串内容序列化器。 如果为 None（默认），则根据型号自动检测。 对于不支持列表内容的提供者很有用，例如 HuggingFace 和 Groq。
   */
  force_string_serializer?: boolean | null;
  /**
   * 内嵌图像 URL
   *
   * 如果 True, fetch any http(s) image URL 在发送的消息中和消息内嵌入它作为 base64 ``data:``  URL 在发送之前。 如果 None (默认)，根据模型自动检测（某些） APIs 例如 Moonshot 的公共 Kimi 端点拒绝 URL-需要格式化后的图片，且要求使用 base64。 在通过隐藏底层提供者的代理别名到达模型时，显式设置此值e.g. ``litellm_proxy/<custom-alias>``). 仅在时才运行 ``vision_is_active()`` 是 True因此，别名仍然必须被视作具备视觉能力的 SDK feature 注册表或代理模型元数据。
   */
  inline_image_urls?: boolean | null;
  /**
   * 每 token 的投入成本
   *
   * 每个输入的成本 token。 这将在用户日志中可用。
   */
  input_cost_per_token?: number | null;
  /**
   * 是订阅
   *
   * 此 LLM 是否使用基于订阅的身份验证。 已序列化以便特定于订阅的请求处理能够传输层保存到远程智能体服务器。
   */
  readonly is_subscription: boolean;
  /**
   * LiteLLM 额外本体
   *
   * 传递给的附加键值对 LiteLLM's extra_body 参数。 这很有用，用于自定义推理端点需要配置参数、路由或高级功能的额外参数。 注意：并非所有 LLM 提供商支持 extra_body 参数。 一些提供商 (e.g., OpenAI) 可以拒绝未识别的选项请求。 这通常由：- 支持 LiteLLM 代理服务器（路由元数据、追踪） - vLLM 端点 (return_token_ids, etc.) - Custom inference clusters Examples: - Proxy routing: {'trace_version'version': '1.0.0', 'tags': '' ['智能体我的-智能体']} - vLLM features: {'return_token_ids': True}
   */
  litellm_extra_body?: {
    [key: string]: unknown;
  };
  /**
   * 记录完成情况
   *
   * 启用完成记录。
   */
  log_completions?: boolean;
  /**
   * 记录完成文件夹
   *
   * 将 LLM 个完成情况记录到的文件夹。 如果 log_completions 为 True，则为必填项。
   */
  log_completions_folder?: string;
  /**
   * 最大输入 token
   *
   * 最大输入数量token。 请注意，当前未使用该值，运行时的值实际上是 OpenAI 中的总计 token（e.g.128,000 token for GPT-4）。
   */
  max_input_tokens?: number | null;
  /**
   * 最大消息字符数
   *
   * 发送到 LLM 的每个事件/内容的大约最大字符数。
   */
  max_message_chars?: number;
  /**
   * 最大输出 token
   *
   * 最大输出数量token。 这被发送到LLM。
   */
  max_output_tokens?: number | null;
  /**
   * 型号
   *
   * 型号名称。
   */
  model?: string;
  /**
   * 型号规范名称
   *
   * 用于特征注册表查找的可选规范模型名称。 OpenHands SDK 维护一个模型功能注册表，将模型名称映射到功能（e.g.、视觉支持、提示词缓存、响应 API 支持）。 当使用代理或别名的模型标识时，将此字段设置为可唯一标识的模型名称（e.g，'openai/gpt-4o'）以确保正确的能力检测。 如果未提供，“模型”字段将用于功能查找。
   */
  model_canonical_name?: string | null;
  /**
   * 原生工具调用
   *
   * 是否使用原生工具调用。
   */
  native_tool_calling?: boolean;
  /**
   * 数量重试
   */
  num_retries?: number;
  /**
   * 奥拉马基地网址
   */
  ollama_base_url?: string | null;
  /**
   * Openrouter应用程序名称
   */
  openrouter_app_name?: string;
  /**
   * Openrouter 站点 URL
   */
  openrouter_site_url?: string;
  /**
   * 每 token 的输出成本
   *
   * 每个输出的成本 token。 这将在用户日志中可用。
   */
  output_cost_per_token?: number | null;
  /**
   * 提示词缓存保留
   *
   * 提示词缓存的保留策略。 仅针对受支持的型号发送（GPT-5+ 和 GPT-4.1，不包括 Azure 部署）； 明确地为所有其他人剥离。
   */
  prompt_cache_retention?: string | null;
  /**
   * 提供商连接 ID
   *
   * 可选的提供程序连接，每次加载此 LLM 配置文件（使用时读取）时，都会解析并应用其共享 API 密钥和基 URL。 设置后，配置文件不存储其自己的内联 api_key 或 base_url。
   */
  provider_connection_id?: string | null;
  /**
   * 推理努力
   *
   * 提供者中立的推理工作。 常见的值包括 'None'、'最小'、'低'、'中'、'高'、'x高' 和 '最大'。 SDK 接受未来的提供者值并让 LiteLLM 翻译它们。
   */
  reasoning_effort?: 'low' | 'medium' | 'high' | 'xhigh' | 'none' | null;
  /**
   * 推理总结
   *
   * 推理摘要的详细程度。 这是一个字符串，可以是“auto”、“concise”或“detailed”之一。 需要经过验证的 OpenAI 组织。 仅在明确设置时发送。
   */
  reasoning_summary?: 'auto' | 'concise' | 'detailed' | null;
  /**
   * 重试最长等待时间
   */
  retry_max_wait?: number;
  /**
   * 重试最短等待时间
   */
  retry_min_wait?: number;
  /**
   * 重试乘数
   */
  retry_multiplier?: number;
  /**
   * 种子
   *
   * 用于生成随机数的种子。
   */
  seed?: number | null;
  /**
   * 串流
   *
   * 启用来自 LLM 的流式传输响应。 启用后，将为 token 的每个块调用 .completions 和 .responses 中提供的 `on_token` 回调。
   */
  stream?: boolean;
  /**
   * 流空闲超时
   *
   * 异步流式传输响应中块之间的最大秒数。 默认为300s（5分钟）； 设置为 None 禁用。
   */
  stream_idle_timeout?: number | null;
  /**
   * 订阅供应商
   *
   * 用于订阅支持的 LLM 访问的订阅提供商。
   */
  subscription_vendor?: 'openai' | null;
  /**
   * 温度
   *
   * 用于生成响应的采样温度。 默认为 None（使用提供商默认温度）。 设置为 0.0 以获得确定性输出，或设置为更高值 (0.7-1.0) 以获得更有创意的响应。
   */
  temperature?: number | null;
  /**
   * 超时
   *
   * HTTP 和硬每次尝试超时（以秒为单位）。 默认值为 300 秒（5 分钟）。 设置为 None 以禁用硬超时。
   */
  timeout?: number | null;
  /**
   * 前K
   */
  top_k?: number | null;
  /**
   * 顶P
   *
   * 核采样参数。 默认为 None（使用提供程序默认值）。 设置为 0 到 1 之间的值以控制输出的多样性。
   */
  top_p?: number | null;
  /**
   * 使用 ID
   *
   * LLM 的唯一使用标识符。 用于注册表查找、遥测和支出跟踪。
   */
  usage_id?: string;
};

/**
 * LLMCompletionLogEvent
 *
 * 包含 LLM 完成日志数据的事件。
 *
 * 当远程会话中LLM配置为log_completions=True时，
 * 此事件通过 WebSocket 将完成日志数据流式传输回客户端
 * 而不是将其写入 Docker 容器内的文件。
 */
export type LlmCompletionLogEvent = {
  /**
   * 文件名
   *
   * 该日志的预期文件名（相对于日志目录）
   */
  filename: string;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'LLMCompletionLogEvent';
  /**
   * 记录数据
   *
   * 要写入文件的 JSON 编码的日志数据
   */
  log_data: string;
  /**
   * 型号名称
   *
   * 上下文的型号名称
   */
  model_name?: string;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 使用 ID
   *
   * 生成此日志的 LLM usage_id
   */
  usage_id?: string;
};

/**
 * LLMSecurityAnalyzer
 *
 * LLM基于安全分析器。
 *
 * 该分析器尊重可以由 LLM 设置的 security_risk 属性
 * 在生成动作时，类似于 OpenHands LLMRiskAnalyzer。
 *
 * 它提供了一种利用 LLM 的轻量级安全分析方法
 * 了解行动上下文和潜在风险。
 */
export type LlmSecurityAnalyzerInput = {
  /**
   * 种类
   */
  kind?: 'LLMSecurityAnalyzer';
};

/**
 * LLMSecurityAnalyzer
 *
 * LLM基于安全分析器。
 *
 * 该分析器尊重可以由 LLM 设置的 security_risk 属性
 * 在生成动作时，类似于 OpenHands LLMRiskAnalyzer。
 *
 * 它提供了一种利用 LLM 的轻量级安全分析方法
 * 了解行动上下文和潜在风险。
 */
export type LlmSecurityAnalyzerOutput = {
  /**
   * 种类
   */
  kind: 'LLMSecurityAnalyzer';
};

/**
 * LLMSummarizingCondenser
 *
 * 基于 LLM 的上下文压缩器总结了被遗忘的事件。
 *
 * 使用独立的 LLM（存储在 `llm` 属性中）来生成摘要
 * 被遗忘的事件。 传递给 condense() 的可选 `agent_llm` 参数是
 * LLM 被智能体用于 token 计数目的，并且您不应该假设
 * 与上下文压缩器中定义的相同。
 */
export type LlmSummarizingCondenserInput = {
  /**
   * 硬上下文重置上下文缩放
   */
  hard_context_reset_context_scaling?: number;
  /**
   * 硬上下文重置最大重试
   */
  hard_context_reset_max_retries?: number;
  /**
   * 保持第一
   */
  keep_first?: number;
  /**
   * 种类
   */
  kind?: 'LLMSummarizingCondenser';
  llm: LlmInput;
  /**
   * 最大尺寸
   */
  max_size?: number;
  /**
   * 最大 token
   */
  max_tokens?: number | null;
  /**
   * 最低进度
   */
  minimum_progress?: number;
};

/**
 * LLMSummarizingCondenser
 *
 * 基于 LLM 的上下文压缩器总结了被遗忘的事件。
 *
 * 使用独立的 LLM（存储在 `llm` 属性中）来生成摘要
 * 被遗忘的事件。 传递给 condense() 的可选 `agent_llm` 参数是
 * LLM 被智能体用于 token 计数目的，并且您不应该假设
 * 与上下文压缩器中定义的相同。
 */
export type LlmSummarizingCondenserOutput = {
  /**
   * 硬上下文重置上下文缩放
   */
  hard_context_reset_context_scaling?: number;
  /**
   * 硬上下文重置最大重试
   */
  hard_context_reset_max_retries?: number;
  /**
   * 保持第一
   */
  keep_first?: number;
  /**
   * 种类
   */
  kind: 'LLMSummarizingCondenser';
  llm: LlmOutput;
  /**
   * 最大尺寸
   */
  max_size?: number;
  /**
   * 最大 token
   */
  max_tokens?: number | null;
  /**
   * 最低进度
   */
  minimum_progress?: number;
};

/**
 * LLMSummarizingCondenserSettings
 *
 * 设置为默认LLM总结上下文压缩器。
 */
export type LlmSummarizingCondenserSettings = {
  /**
   * 上下文压缩器种类
   *
   * 上下文压缩器设置联合的鉴别器。 ``'llm_summarizing'`` 选择默认的 LLM 汇总上下文压缩器。
   */
  condenser_kind?: 'llm_summarizing';
  /**
   * 启用
   *
   * 启用对话记忆上下文压缩。
   */
  enabled?: boolean;
  /**
   * 硬上下文重置上下文缩放
   *
   * 用于在硬上下文重置汇总失败后减少事件字符串大小的因素。
   */
  hard_context_reset_context_scaling?: number;
  /**
   * 硬上下文重置最大重试
   *
   * 引发错误之前尝试硬上下文重置的次数。
   */
  hard_context_reset_max_retries?: number;
  /**
   * 保持第一
   *
   * 上下文压缩之前要保留的最小初始事件数。
   */
  keep_first?: number;
  /**
   * 最大尺寸
   *
   * 上下文压缩器运行之前保留的最大事件数。 保留基本设置类以实现兼容性； 当这不适用时，具体的上下文压缩器-设置变体可以选择退出。
   */
  max_size?: number;
  /**
   * 最大 token
   *
   * 上下文压缩器运行之前允许的最大 token 数量。 未设置时，上下文压缩仅基于事件计数。
   */
  max_tokens?: number | null;
  /**
   * 最低进度
   *
   * 为使上下文压缩被视为成功而必须压缩的事件的最小部分。
   */
  minimum_progress?: number;
};

/**
 * LaunchedAgentProfile
 *
 * 智能体配置文件启动对话时记录的来源快照。
 *
 * 存储在 ``StoredConversation`` 上并投影到 ``ConversationInfo`` 上，所以
 * ts-client ``deriveSwitchPlan`` 可以识别哪个智能体配置文件是当前的
 * 没有脆弱的设置比较。 参见#3720。
 */
export type LaunchedAgentProfile = {
  /**
   * 智能体个人资料 ID
   *
   * 启动对话的智能体配置文件的稳定 ID。
   */
  agent_profile_id: string;
  /**
   * 法学硕士简介参考
   *
   * 每次启动 LLM 配置文件都会覆盖 `agent_launch_additions`。 null 表示使用了配置文件自己的 `llm_profile_ref`。
   */
  llm_profile_ref?: string | null;
  /**
   * 修订版
   *
   * 在启动时修订智能体配置文件。
   */
  revision: number;
  /**
   * 机密参考文献
   *
   * 机密允许列表在启动时捕获，也在恢复时强制执行。 null 保留旧对话的不受限制的行为。
   */
  secret_refs?: Array<string> | null;
};

/**
 * ListDirectoryAction
 *
 * 模式用于列表目录操作。
 */
export type ListDirectoryAction = {
  /**
   * 目录路径
   *
   * 要列出的目录的路径。 默认为当前目录。
   */
  dir_path?: string;
  /**
   * 种类
   */
  kind: 'ListDirectoryAction';
  /**
   * 递归
   *
   * 是否递归列出子目录（最多 2 级）。
   */
  recursive?: boolean;
};

/**
 * ListDirectoryObservation
 *
 * 观测结果来自列出目录。
 */
export type ListDirectoryObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 目录路径
   *
   * 列出的目录路径。
   */
  dir_path?: string | null;
  /**
   * 参赛作品
   *
   * 找到的文件和目录的列表。
   */
  entries?: Array<FileEntry>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 被截断
   *
   * 列表是否因条目太多而被截断。
   */
  is_truncated?: boolean;
  /**
   * 种类
   */
  kind: 'ListDirectoryObservation';
  /**
   * 总计数
   *
   * 找到的条目总数。
   */
  total_count?: number;
};

/**
 * ListDirectoryTool
 *
 * 用于列出带有元数据的目录内容的工具。
 */
export type ListDirectoryTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ListDirectoryTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * LocalWorkspace
 *
 * 在主机文件系统上运行的本地工作区实现。
 *
 * LocalWorkspace 提供对本地文件系统和命令执行的直接访问
 * 环境。 它适用于智能体的开发和测试场景
 * 应直接在主机系统上运行。
 *
 * 示例：
 * >>> 工作区 = LocalWorkspace(working_dir="/path/to/project")
 * >>> 与工作区：
 * ... 结果 = workspace.execute_command("ls -la")
 * ... 内容 = workspace.read_file("README.md")
 */
export type LocalWorkspaceInput = {
  /**
   * 种类
   */
  kind?: 'LocalWorkspace';
  /**
   * 工作目录
   *
   * 工作目录用于智能体操作和工具执行。 接受字符串路径和 Path 对象。 路径对象会自动转换为字符串。
   */
  working_dir: string;
};

/**
 * LocalWorkspace
 *
 * 在主机文件系统上运行的本地工作区实现。
 *
 * LocalWorkspace 提供对本地文件系统和命令执行的直接访问
 * 环境。 它适用于智能体的开发和测试场景
 * 应直接在主机系统上运行。
 *
 * 示例：
 * >>> 工作区 = LocalWorkspace(working_dir="/path/to/project")
 * >>> 与工作区：
 * ... 结果 = workspace.execute_command("ls -la")
 * ... 内容 = workspace.read_file("README.md")
 */
export type LocalWorkspaceOutput = {
  /**
   * 种类
   */
  kind: 'LocalWorkspace';
  /**
   * 工作目录
   *
   * 工作目录用于智能体操作和工具执行。 接受字符串路径和 Path 对象。 路径对象会自动转换为字符串。
   */
  working_dir: string;
};

/**
 * LookupSecret
 *
 * A 机密从某个外部 url 查找
 */
export type LookupSecretInput = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 种类
   */
  kind?: 'LookupSecret';
  /**
   * 网址
   */
  url: string;
};

/**
 * LookupSecret
 *
 * A 机密从某个外部 url 查找
 */
export type LookupSecretOutput = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 种类
   */
  kind: 'LookupSecret';
  /**
   * 网址
   */
  url: string;
};

/**
 * MCPApiKeyAuthCredential
 */
export type McpApiKeyAuthCredentialInput = {
  /**
   * 标头名称
   */
  header_name?: string | null;
  /**
   * 策略
   */
  strategy: 'api_key';
  /**
   * 价值
   */
  value?: null;
};

/**
 * MCPApiKeyAuthCredential
 */
export type McpApiKeyAuthCredentialOutput = {
  /**
   * 标头名称
   */
  header_name?: string | null;
  /**
   * 策略
   */
  strategy: 'api_key';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * MCPAuthCredential
 */
export type McpAuthCredential =
  | ({
      strategy: 'none';
    } & McpNoneAuthCredential)
  | ({
      strategy: 'api_key';
    } & McpApiKeyAuthCredentialOutput)
  | ({
      strategy: 'bearer';
    } & McpBearerAuthCredentialOutput)
  | ({
      strategy: 'basic';
    } & McpBasicAuthCredentialOutput)
  | ({
      strategy: 'header';
    } & McpHeaderAuthCredentialOutput)
  | ({
      strategy: 'oauth2';
    } & McpoAuthAuthCredentialOutput);

/**
 * MCPBasicAuthCredential
 */
export type McpBasicAuthCredentialInput = {
  /**
   * 密码
   */
  password?: null;
  /**
   * 策略
   */
  strategy: 'basic';
  /**
   * 用户名
   */
  username: string;
};

/**
 * MCPBasicAuthCredential
 */
export type McpBasicAuthCredentialOutput = {
  /**
   * 密码
   */
  password?: string | null;
  /**
   * 策略
   */
  strategy: 'basic';
  /**
   * 用户名
   */
  username: string;
};

/**
 * MCPBearerAuthCredential
 */
export type McpBearerAuthCredentialInput = {
  /**
   * 策略
   */
  strategy: 'bearer';
  /**
   * 价值
   */
  value?: null;
};

/**
 * MCPBearerAuthCredential
 */
export type McpBearerAuthCredentialOutput = {
  /**
   * 策略
   */
  strategy: 'bearer';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * MCPConfig
 *
 * 由稳定服务器名称键入的规范已持久化 MCP 服务器映射。
 */
export type McpConfig = {
  [key: string]: McpServerOutput;
};

/**
 * MCPConfigPatch
 *
 * 稀疏MCP地图补丁； null 映射值删除该指定服务器。
 */
export type McpConfigPatch = {
  [key: string]: McpServerPatch | null;
};

/**
 * MCPHeaderAuthCredential
 */
export type McpHeaderAuthCredentialInput = {
  /**
   * 策略
   */
  strategy: 'header';
};

/**
 * MCPHeaderAuthCredential
 */
export type McpHeaderAuthCredentialOutput = {
  /**
   * 标头
   */
  headers?: {
    [key: string]: string | null;
  };
  /**
   * 策略
   */
  strategy: 'header';
};

/**
 * MCPNoneAuthCredential
 */
export type McpNoneAuthCredential = {
  /**
   * 策略
   */
  strategy: 'none';
};

/**
 * MCPOAuthAuthCredential
 */
export type McpoAuthAuthCredentialInput = {
  authentication?: McpoAuthAuthenticationInput | null;
  state?: McpoAuthStateInput | null;
  /**
   * 策略
   */
  strategy: 'oauth2';
};

/**
 * MCPOAuthAuthCredential
 */
export type McpoAuthAuthCredentialOutput = {
  authentication?: McpoAuthAuthenticationOutput | null;
  state?: McpoAuthStateOutput | null;
  /**
   * 策略
   */
  strategy: 'oauth2';
};

/**
 * MCPOAuthAuthentication
 */
export type McpoAuthAuthenticationInput = {
  /**
   * 附加客户端元数据
   */
  additional_client_metadata?: {
    [key: string]: unknown;
  } | null;
  /**
   * 客户端认证方式
   */
  client_auth_method?:
    'none' | 'client_secret_post' | 'client_secret_basic' | 'private_key_jwt' | null;
  /**
   * 客户端 ID
   */
  client_id?: string | null;
  /**
   * 客户端元数据 URL
   */
  client_metadata_url?: string | null;
  /**
   * 客户名称
   */
  client_name?: string | null;
  /**
   * 客户机密
   */
  client_secret?: null;
  /**
   * 范围
   */
  scopes?: string | Array<string> | null;
  /**
   * 类型
   */
  type: 'oauth';
};

/**
 * MCPOAuthAuthentication
 */
export type McpoAuthAuthenticationOutput = {
  /**
   * 附加客户端元数据
   */
  additional_client_metadata?: {
    [key: string]: unknown;
  } | null;
  /**
   * 客户端认证方式
   */
  client_auth_method?:
    'none' | 'client_secret_post' | 'client_secret_basic' | 'private_key_jwt' | null;
  /**
   * 客户端 ID
   */
  client_id?: string | null;
  /**
   * 客户端元数据 URL
   */
  client_metadata_url?: string | null;
  /**
   * 客户名称
   */
  client_name?: string | null;
  /**
   * 客户机密
   */
  client_secret?: string | null;
  /**
   * 范围
   */
  scopes?: string | Array<string> | null;
  /**
   * 类型
   */
  type: 'oauth';
};

/**
 * MCPOAuthCallbackRequest
 *
 * 回调 URL 从浏览器 OAuth 重定向复制。
 */
export type McpoAuthCallbackRequest = {
  /**
   * 回调网址
   */
  callback_url: string;
};

/**
 * MCPOAuthClientInfoState
 */
export type McpoAuthClientInfoStateInput = {
  /**
   * 客户机密
   */
  client_secret?: null;
  [key: string]: unknown;
};

/**
 * MCPOAuthClientInfoState
 */
export type McpoAuthClientInfoStateOutput = {
  /**
   * 客户机密
   */
  client_secret?: string | null;
  [key: string]: unknown;
};

/**
 * MCPOAuthStartResponse
 *
 * 启动安装时 OAuth MCP 探测的响应。
 */
export type McpoAuthStartResponse = {
  /**
   * 授权网址
   */
  authorization_url?: string | null;
  /**
   * 错误
   */
  error?: string | null;
  /**
   * 错误类型
   */
  error_kind?: 'timeout' | 'connection' | 'unknown' | null;
  /**
   * 职位编号
   */
  job_id?: string | null;
  /**
   * 好的
   */
  ok: boolean;
};

/**
 * MCPOAuthState
 */
export type McpoAuthStateInput = {
  client_info?: McpoAuthClientInfoStateInput | null;
  /**
   * token 到期时间
   */
  token_expires_at?: number | null;
  tokens?: McpoAuthTokenStateInput | null;
};

/**
 * MCPOAuthState
 */
export type McpoAuthStateOutput = {
  client_info?: McpoAuthClientInfoStateOutput | null;
  /**
   * token 到期时间
   */
  token_expires_at?: number | null;
  tokens?: McpoAuthTokenStateOutput | null;
};

/**
 * MCPOAuthStateResponse
 */
export type McpoAuthStateResponse = {
  /**
   * 客户信息
   */
  client_info?: {
    /**
     * 客户机密
     */
    client_secret?: string | null;
    [key: string]: unknown;
  } | null;
  /**
   * token 到期时间
   */
  token_expires_at?: number | null;
  /**
   * token
   */
  tokens?: {
    /**
     * 访问令牌
     */
    access_token?: string | null;
    /**
     * 刷新令牌
     */
    refresh_token?: string | null;
    [key: string]: unknown;
  } | null;
};

/**
 * MCPOAuthStatusResponse
 *
 * 安装时 OAuth MCP 探测的当前状态。
 */
export type McpoAuthStatusResponse = {
  /**
   * 授权网址
   */
  authorization_url?: string | null;
  /**
   * 回调准备好
   */
  callback_ready?: boolean;
  /**
   * 错误
   */
  error?: string | null;
  /**
   * 错误类型
   */
  error_kind?: 'timeout' | 'connection' | 'unknown' | null;
  /**
   * 职位编号
   */
  job_id: string;
  oauth_state?: McpoAuthStateResponse | null;
  /**
   * 好的
   */
  ok: boolean;
  /**
   * 状态
   */
  status: 'pending' | 'authorizing' | 'succeeded' | 'failed';
  tool_result?: McpToolCallResult | null;
  /**
   * 工具
   */
  tools?: Array<string> | null;
};

/**
 * MCPOAuthTokenState
 */
export type McpoAuthTokenStateInput = {
  /**
   * 访问令牌
   */
  access_token?: null;
  /**
   * 刷新令牌
   */
  refresh_token?: null;
  [key: string]: unknown;
};

/**
 * MCPOAuthTokenState
 */
export type McpoAuthTokenStateOutput = {
  /**
   * 访问令牌
   */
  access_token?: string | null;
  /**
   * 刷新令牌
   */
  refresh_token?: string | null;
  [key: string]: unknown;
};

/**
 * MCPServer
 *
 * 设置 DataModel 中的一台 MCP 服务器。
 */
export type McpServer = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialOutput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialOutput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialOutput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialOutput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialOutput)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 该服务器是否暴露于智能体。 一个已禁用的服务器仍然完全配置，包括其机密，但在MCP工具创建时和服务器转发到ACP 子进程时被跳过。
   */
  enabled?: boolean;
  /**
   * 环境
   */
  env?: {
    [key: string]: string | null;
  } | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string | null;
  } | null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPServer
 *
 * 设置 DataModel 中的一台 MCP 服务器。
 */
export type McpServerInput = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInput)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 该服务器是否暴露于智能体。 一个已禁用的服务器仍然完全配置，包括其机密，但在MCP工具创建时和服务器转发到ACP 子进程时被跳过。
   */
  enabled?: boolean;
  /**
   * 环境
   */
  env?: null;
  /**
   * 标头
   */
  headers?: null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPServer
 *
 * 设置 DataModel 中的一台 MCP 服务器。
 */
export type McpServerOutput = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialOutput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialOutput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialOutput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialOutput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialOutput)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 该服务器是否暴露于智能体。 一个已禁用的服务器仍然完全配置，包括其机密，但在MCP工具创建时和服务器转发到ACP 子进程时被跳过。
   */
  enabled?: boolean;
  /**
   * 环境
   */
  env?: {
    [key: string]: string | null;
  } | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string | null;
  } | null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPServerPatch
 *
 * 适用于一台已持久化 MCP 服务器的稀疏 RFC 7386 合并补丁。
 */
export type McpServerPatch = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInput)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 关闭服务器 (False) 或重新打开 (True)，而不触及其配置的 REST。 null 清除覆盖，从而恢复规范默认值（启用）。
   */
  enabled?: boolean | null;
  /**
   * 环境
   */
  env?: {
    [key: string]: null;
  } | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: null;
  } | null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPTestFailure
 *
 * 候选服务器无法连接或列出工具时的响应。
 *
 * 端点在成功和失败的情况下都会返回 HTTP 200：
 * 这里的失败是验证用户提供的*预期*结果
 * 配置错误，不是服务器端错误。 结构化的形状让一切变得简单
 * 让 UI 呈现可操作的消息。
 */
export type McpTestFailure = {
  /**
   * 错误
   *
   * 人类可读的错误消息。
   */
  error: string;
  /**
   * 错误类型
   *
   * 粗略错误分类，对于分支 UI 很有用。
   */
  error_kind: 'timeout' | 'connection' | 'unknown';
  /**
   * 好的
   */
  ok?: false;
};

/**
 * MCPTestRequest
 *
 * ``POST /api/mcp/test`` 的主体。
 */
export type McpTestRequest = {
  /**
   * 名称
   *
   * 用于临时 MCP 服务器映射内的服务器的名称。 仅影响错误消息——不需要匹配任何已持久化设置。
   */
  name?: string;
  /**
   * 服务器
   */
  server:
    | ({
        type: 'stdio';
      } & StdioMcpServerSpec)
    | ({
        type: 'http' | 'shttp' | 'sse' | 'streamable-http';
      } & RemoteMcpServerSpec);
  /**
   * 超时
   *
   * 等待连接+工具/列表完成的秒数。
   */
  timeout?: number;
  /**
   * 列出成功后要调用的可选只读工具，以便调用者可以验证凭据服务器仅执行工具调用。 其结果在 `tool_result` 中逐字报告，不影响 `ok`。
   */
  tool_call?: McpToolCallSpec | null;
};

/**
 * MCPTestResponse
 */
export type McpTestResponse =
  | ({
      ok: true;
    } & McpTestSuccess)
  | ({
      ok: false;
    } & McpTestFailure);

/**
 * MCPTestSuccess
 *
 * 当候选服务器连接并列出其工具时的响应。
 */
export type McpTestSuccess = {
  /**
   * 已序列化探针获取或刷新的 OAuth 状态。 客户端应在测试服务器的 auth.state 下持久化。
   */
  oauth_state?: McpoAuthStateResponse | null;
  /**
   * 好的
   */
  ok?: true;
  /**
   * 已解决 MCP 服务器
   *
   * 已弃用旧客户端的兼容性字段，期望在测试响应中解析 MCP 服务器元数据。
   *
   * @已弃用
   */
  resolved_mcp_servers?: Array<{
    [key: string]: unknown;
  }> | null;
  /**
   * 当提供一个时，所请求的 `tool_call` 的结果。
   */
  tool_result?: McpToolCallResult | null;
  /**
   * 工具
   *
   * MCP 服务器公布的工具名称。
   */
  tools?: Array<string>;
};

/**
 * MCPToolAction
 *
 * 模式用于 MCP 输入操作。
 *
 * 它只是一个简单的 JSON 原生包装
 * 不做任何验证。
 *
 * 验证将由 MCPTool.__call__ 执行
 * 通过构建动态创建的 Pydantic 模型
 * 来自 MCP 工具输入模式。
 */
export type McpToolAction = {
  /**
   * 数据
   *
   * 来自工具调用的动态数据字段
   */
  data?: {
    [key: string]: unknown;
  };
  /**
   * 种类
   */
  kind: 'MCPToolAction';
};

/**
 * MCPToolCallResult
 *
 * 所请求的逐字结果``tool_call``。
 *
 * 端点保持提供商中立：许多服务器报告上游
 * 失败（e.g. Slack 的 ``{"ok": false, "error": "invalid_auth"}``）
 * 作为未设置 ``isError`` 的普通文本内容，因此解释
 * 载荷是调用者的工作。
 */
export type McpToolCallResult = {
  /**
   * 是错误
   *
   * 结果的 MCP 级 isError 标志。
   */
  is_error: boolean;
  /**
   * 文字
   *
   * 结果的串联文本内容。
   */
  text: string;
};

/**
 * MCPToolCallSpec
 *
 * 作为连接测试的一部分运行的单个工具调用。
 *
 * 列表工具不行使凭据许多服务器仅使用
 * 在工具处理程序内部，因此调用者可以在工具处理程序之后命名要调用的工具
 * 上市成功。 调用者负责选择只读工具；
 * 端点逐字执行它。
 */
export type McpToolCallSpec = {
  /**
   * 论点
   *
   * 传递给工具的参数保持不变。
   */
  arguments?: {
    [key: string]: unknown;
  };
  /**
   * 名称
   *
   * 要调用的工具的名称
   */
  name: string;
};

/**
 * MCPToolDefinition
 *
 * MCP 包装 MCP 客户端并提供工具功能的工具。
 */
export type McpToolDefinition = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'MCPToolDefinition';
  /**
   * MCP 工具定义。
   */
  mcp_tool: McpTypesTool;
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * MCPToolObservation
 *
 * 观测结果来自 MCP 工具执行。
 */
export type McpToolObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'MCPToolObservation';
  /**
   * 工具名称
   *
   * 调用的工具的名称
   */
  tool_name: string;
};

/**
 * MarketplacePluginInfo
 *
 * 市场目录中的 True 插件，带有附加坐标。
 */
export type MarketplacePluginInfo = {
  /**
   * 描述
   */
  description: string | null;
  /**
   * 文件
   */
  files?: Array<string> | null;
  /**
   * 已安装
   */
  installed: boolean;
  /**
   * 名称
   */
  name: string;
  /**
   * 路径
   */
  path?: string | null;
  /**
   * 参考号
   */
  ref?: string | null;
  /**
   * 回购路径
   */
  repo_path?: string | null;
  /**
   * 技能
   */
  skills?: Array<PluginSkillSummary> | null;
  /**
   * 来源
   */
  source: string;
};

/**
 * MarketplaceRegistration
 *
 * 注册用于插件解析的市场源。
 */
export type MarketplaceRegistration = {
  /**
   * 自动加载
   *
   * 是否在对话开始时加载市场插件和独立技能。 使用 True 表示全部，使用 False 或 [] 表示 None，或使用插件/技能名称列表进行选择性加载。
   */
  auto_load?: boolean | Array<string>;
  /**
   * 名称
   *
   * 此市场注册的标识符
   */
  name: string;
  /**
   * 参考号
   *
   * git 源的可选分支、标签或提交
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 包含市场的 git 存储库中的子目录路径。 仅与 git 源相关。
   */
  repo_path?: string | null;
  /**
   * 来源
   *
   * 市场来源：'GitHub:owner/repo'、git URL 或本地路径
   */
  source: string;
};

/**
 * MarketplaceSkillInfo
 *
 * 有关市场目录中技能的信息。
 */
export type MarketplaceSkillInfo = {
  /**
   * 描述
   */
  description: string | null;
  /**
   * 已安装
   */
  installed: boolean;
  /**
   * 名称
   */
  name: string;
  /**
   * 来源
   */
  source: string;
};

/**
 * MaterializeAgentProfileRequest
 */
export type MaterializeAgentProfileRequest = {
  /**
   * 公司简介
   *
   * 要评估的草稿配置文件而不是存储的配置文件。 路径名称覆盖草稿名称。
   */
  profile?: OpenHandsAgentProfile | AcpAgentProfile | null;
};

/**
 * 留言
 */
export type Message = {
  /**
   * 内容
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 名称
   */
  name?: string | null;
  /**
   * 推理内容
   *
   * 来自推理模型的中级推理/思维内容
   */
  reasoning_content?: string | null;
  /**
   * OpenAI 模型输出的响应推理项
   */
  responses_reasoning_item?: ReasoningItemModel | null;
  /**
   * 角色
   */
  role: 'user' | 'system' | 'assistant' | 'tool';
  /**
   * 思维块
   *
   * 用于扩展思维功能的原始 Anthropic 思维块
   */
  thinking_blocks?: Array<ThinkingBlock | RedactedThinkingBlock>;
  /**
   * 工具调用身份证号
   */
  tool_call_id?: string | null;
  /**
   * 工具调用
   */
  tool_calls?: Array<MessageToolCall> | null;
};

/**
 * MessageEvent
 *
 * 来自智能体或用户的消息。
 *
 * 这原本是“MessageAction”，但它假设不是工具调用。
 */
export type MessageEvent = {
  /**
   * 激活技能
   *
   * 激活技能名称列表
   */
  activated_skills?: Array<string>;
  /**
   * 对此消息和之前历史的可选评论家评估。
   */
  critic_result?: CriticResult | null;
  /**
   * 扩展内容
   *
   * 智能体上下文添加的内容列表
   */
  extended_content?: Array<TextContent>;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'MessageEvent';
  /**
   * 此消息事件的确切 LLM 消息
   */
  llm_message: Message;
  /**
   * Llm 响应 ID
   *
   * 生成此 eventIf 源的 LLM 响应的完成或响应 ID != '智能体'，此字段为 None
   */
  llm_response_id?: string | null;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 发件人
   *
   * 发件人的可选标识符。 可用于在多智能体场景中跟踪消息来源。
   */
  sender?: string | null;
  /**
   * 来源
   */
  source: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * MessageToolCall
 *
 * 传输层-不可知的工具调用表示。
 *
 * 一个规范 ID 用于跨操作/观察进行链接，
 * 对于响应 function_call_output call_id。
 */
export type MessageToolCall = {
  /**
   * 论点
   *
   * JSON 参数字符串
   */
  arguments: string;
  /**
   * 身份证号
   *
   * 规范工具调用 id
   */
  id: string;
  /**
   * 名称
   *
   * 工具/功能名称
   */
  name: string;
  /**
   * 产地
   *
   * 起源API家庭
   */
  origin: 'completion' | 'responses';
  /**
   * 回复项目 ID
   *
   * 原始回复 function_call.id，重播时逐字回显
   */
  responses_item_id?: string | null;
};

/**
 * MetaProfile
 *
 * 声明性模型路由配置。
 */
export type MetaProfile = {
  /**
   * 课程
   *
   * 任务类别及其目标配置文件的有序列表。
   */
  classes?: Array<MetaProfileClass>;
  /**
   * 分类器模型
   *
   * 用于对任务进行分类的已保存 LLM 配置文件的名称。
   */
  classifier_model: string;
  /**
   * 型号表
   *
   * 插入 `{{ model_table }}` 的可选文本用于直接路由提示词。
   */
  model_table?: string | null;
  /**
   * 提示词模板
   *
   * 可选的直接路由提示词模板。 设置后，分类器接收此呈现的提示词，并应返回 JSON 和 `model` 字段而不是类号。
   */
  prompt_template?: string | null;
};

/**
 * MetaProfileClass
 *
 * 单个任务类别和应处理该任务的 LLM 配置文件。
 */
export type MetaProfileClass = {
  /**
   * 描述
   *
   * 本课程涵盖的任务类型的自然语言描述 (e.g. “任务是面向 UI 的或需要查看图像”）。
   */
  description: string;
  /**
   * 型号
   *
   * 已保存的 LLM 配置文件的名称，要切换到与此类匹配的任务。
   */
  model: string;
};

/**
 * MetaProfileDetailResponse
 */
export type MetaProfileDetailResponse = {
  config: MetaProfile;
  /**
   * 名称
   */
  name: string;
};

/**
 * MetaProfileInfo
 */
export type MetaProfileInfo = {
  /**
   * 分类器模型
   */
  classifier_model?: string | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 班级数
   */
  num_classes?: number;
};

/**
 * MetaProfileListResponse
 */
export type MetaProfileListResponse = {
  /**
   * 活动元配置文件
   */
  active_meta_profile?: string | null;
  /**
   * 元配置文件
   */
  meta_profiles: Array<MetaProfileInfo>;
};

/**
 * MetaProfileMutationResponse
 */
export type MetaProfileMutationResponse = {
  /**
   * 留言
   */
  message: string;
  /**
   * 名称
   */
  name: string;
};

/**
 * MetricsSnapshot
 *
 * 某个时间点的指标快照。
 *
 * 不包括单独成本、延迟或 token 使用情况的列表。
 */
export type MetricsSnapshot = {
  /**
   * 累计成本
   *
   * 总累计成本，必须为非负数
   */
  accumulated_cost?: number;
  /**
   * 所有通话累计词元用量
   */
  accumulated_token_usage?: TokenUsage | null;
  /**
   * 每个任务的最大预算
   *
   * 每个任务的最大预算
   */
  max_budget_per_task?: number | null;
  /**
   * 型号名称
   *
   * 型号名称
   */
  model_name?: string;
};

/**
 * ModelsResponse
 *
 * 包含可用 LLM 模型列表的响应。
 */
export type ModelsResponse = {
  /**
   * 型号
   */
  models: Array<string>;
};

/**
 * NavigateConversationRequest
 *
 * 载荷将对话的 HEAD 移至现有事件。
 */
export type NavigateConversationRequest = {
  /**
   * 事件 ID
   *
   * 生成新 HEAD 的事件，重新确定智能体运行所在的活动分支。 所有分支都保留在磁盘上； 这不会产生新的对话。 ``None`` 选择空树。
   */
  event_id?: string | null;
};

/**
 * NeverConfirm
 */
export type NeverConfirmInput = {
  /**
   * 种类
   */
  kind?: 'NeverConfirm';
};

/**
 * NeverConfirm
 */
export type NeverConfirmOutput = {
  /**
   * 种类
   */
  kind: 'NeverConfirm';
};

/**
 * NoOpCondenser
 *
 * 简单上下文压缩器返回未操作的视图。
 *
 * 主要用于测试目的。
 */
export type NoOpCondenserInput = {
  /**
   * 种类
   */
  kind?: 'NoOpCondenser';
};

/**
 * NoOpCondenser
 *
 * 简单上下文压缩器返回未操作的视图。
 *
 * 主要用于测试目的。
 */
export type NoOpCondenserOutput = {
  /**
   * 种类
   */
  kind: 'NoOpCondenser';
};

/**
 * NoOpCondenserSettings
 *
 * 上下文压缩器的设置使对话视图保持不变。
 */
export type NoOpCondenserSettings = {
  /**
   * 上下文压缩器种类
   *
   * 上下文压缩器设置联合的鉴别器。 ``'no_op'`` 选择上下文压缩器，保持对话视图不变。
   */
  condenser_kind?: 'no_op';
  /**
   * 启用
   *
   * 启用对话记忆上下文压缩。
   */
  enabled?: boolean;
};

export type Observation =
  | ({
      kind: 'openhands__sdk__mcp__definition__MCPToolObservation-Output__1';
    } & McpToolObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__classify_and_switch_llm__ClassifyAndSwitchLLMObservation-Output__1';
    } & ClassifyAndSwitchLlmObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__finish__FinishObservation-Output__1';
    } & FinishObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__invoke_skill__InvokeSkillObservation-Output__1';
    } & InvokeSkillObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__switch_llm__SwitchLLMObservation-Output__1';
    } & SwitchLlmObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__think__ThinkObservation-Output__1';
    } & ThinkObservation)
  | ({
      kind: 'openhands__sdk__tool__builtins__vision_inspect__VisionInspectObservation-Output__1';
    } & VisionInspectObservation)
  | ({
      kind: 'openhands__sdk__tool__client_tool__ClientToolObservation-Output__1';
    } & ClientToolObservation)
  | ({
      kind: 'openhands__tools__ask_oracle__definition__AskOracleObservation-Output__1';
    } & AskOracleObservation)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserObservation-Output__1';
    } & BrowserObservation)
  | ({
      kind: 'openhands__tools__child_conversation__definition__StartChildConversationObservation-Output__1';
    } & StartChildConversationObservation)
  | ({
      kind: 'openhands__tools__delegate__definition__DelegateObservation-Output__1';
    } & DelegateObservation)
  | ({
      kind: 'openhands__tools__file_editor__definition__FileEditorObservation-Output__1';
    } & FileEditorObservation)
  | ({
      kind: 'openhands__tools__gemini__edit__definition__EditObservation-Output__1';
    } & EditObservation)
  | ({
      kind: 'openhands__tools__gemini__list_directory__definition__ListDirectoryObservation-Output__1';
    } & ListDirectoryObservation)
  | ({
      kind: 'openhands__tools__gemini__read_file__definition__ReadFileObservation-Output__1';
    } & ReadFileObservation)
  | ({
      kind: 'openhands__tools__gemini__write_file__definition__WriteFileObservation-Output__1';
    } & WriteFileObservation)
  | ({
      kind: 'openhands__tools__glob__definition__GlobObservation-Output__1';
    } & GlobObservation)
  | ({
      kind: 'openhands__tools__grep__definition__GrepObservation-Output__1';
    } & GrepObservation)
  | ({
      kind: 'openhands__tools__planning_file_editor__definition__PlanningFileEditorObservation-Output__1';
    } & PlanningFileEditorObservation)
  | ({
      kind: 'openhands__tools__task__definition__TaskObservation-Output__1';
    } & TaskObservation)
  | ({
      kind: 'openhands__tools__task_tracker__definition__TaskTrackerObservation-Output__1';
    } & TaskTrackerObservation)
  | ({
      kind: 'openhands__tools__terminal__definition__TerminalObservation-Output__1';
    } & TerminalObservation)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowObservation-Output__1';
    } & WorkflowObservation);

/**
 * ObservationEvent
 */
export type ObservationEvent = {
  /**
   * 操作 ID
   *
   * 此观测结果正在响应的操作 ID
   */
  action_id: string;
  /**
   * 扩展内容
   *
   * 智能体上下文添加的内容 (e.g. 由所触及的文件触发的路径范围规则），附加在 to_llm_message 中的工具结果之后。
   */
  extended_content?: Array<TextContent>;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'ObservationEvent';
  /**
   * 将观测结果 (工具调用) 发送至 LLM
   */
  observation: Observation;
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具调用身份证号
   *
   * 此观测结果正在响应的工具调用 id
   */
  tool_call_id: string;
  /**
   * 工具名称
   *
   * 此观测结果响应的工具名称
   */
  tool_name: string;
};

/**
 * OpenHandsAgentProfile
 *
 * ``agent_kind="openhands"`` 配置文件 — 按名称引用 LLM 配置文件。
 *
 * 镜像可配置表面
 * :class:`~openhands.sdk.settings.model.OpenHandsAgentSettings`，除了
 * 具体 ``llm`` 被替换为：attr:`llm_profile_ref` （解决了
 * LLM 配置文件存储）和 ``mcp_config`` 由继承
 * ：属性：`~AgentProfileBase.mcp_server_refs`。
 */
export type OpenHandsAgentProfile = {
  /**
   * 智能体
   *
   * 智能体类构建。
   */
  agent?: string;
  /**
   * 智能体种类
   *
   * ``AgentProfile`` 联合的鉴别器。 ``'openhands'`` 选择标准内置 OpenHands 智能体。
   */
  agent_kind?: 'openhands';
  /**
   * 上下文压缩器
   *
   * 智能体的上下文压缩器设置。
   */
  condenser?: LlmSummarizingCondenserSettings | NoOpCondenserSettings;
  /**
   * 残疾人技能
   *
   * 服务器发现的技能名称从智能体的提示词更改为 EXCLUDE — 已发现目录的拒绝列表。 []（默认）=所有发现的技能； 目录中不存在的列出名称只是一个空操作，因此当目录漂移时，该字段永远不会失败。 替换之前的允许列表 ``skill_refs`` (#4017)：技能来自许多不完整的来源，因此排除是唯一不能悬空的选择模型。
   */
  disabled_skills?: Array<string>;
  /**
   * 启用分类和切换 Llm 工具
   *
   * 启用内置 route_task_to_model 工具，该工具使用 `meta_profile_ref` 命名的元配置文件将任务路由到 LLM 配置文件。
   */
  enable_classify_and_switch_llm_tool?: boolean;
  /**
   * 身份证号
   *
   * 此配置文件的稳定出处句柄。 对话记录了这个UUID； 即使配置文件被重命名，它也永远不会改变。
   */
  id?: string;
  /**
   * 法学硕士简介参考
   *
   * 要为此智能体解析的已保存 LLM 配置文件的名称。 配置文件本身不存储 LLM 凭据 — 它存在于引用的 LLM 配置文件中。
   */
  llm_profile_ref: string;
  /**
   * MCP 服务器参考
   *
   * 要公开用户的哪些全局配置的 MCP 服务器。 null = 全部； [] = None; 非 null 列表 = 指定键的过滤器。
   */
  mcp_server_refs?: Array<string> | null;
  /**
   * 元配置文件参考
   *
   * 路由工具使用的已保存元配置文件的名称。 启动会将其及其路由到的 LLM 配置文件复制到智能体中，因此没有存储的运行时仍然可以路由。 null 让工具回退到运行时存储中的第一个元配置文件。
   */
  meta_profile_ref?: string | null;
  /**
   * 名称
   *
   * 配置文件选择器中显示的面向人的可重命名键。
   */
  name: string;
  /**
   * 人格面具
   *
   * 替换 OpenHands' 内置角色和编码工作流程指南的角色文本。 还包括能力与策略指导（内存、安全策略、风险评估、浏览器、外部服务、过程管理、模型特定注释）和动态上下文。 None 保留内置角色。
   */
  persona?: string | null;
  /**
   * 公共技能
   *
   * 要加载哪些公共目录技能。 null = 全部； [] = None; 列表 = 仅指定技能，忽略目录中缺少的名称。 用户和项目技能不受影响，并且 `disabled_skills` 仍然适用于每项技能。
   */
  public_skills?: Array<string> | null;
  /**
   * 修订版
   *
   * 单调修订计数器，每次保存的编辑都会发生碰撞。
   */
  revision?: number;
  /**
   * 模式版本
   */
  schema_version?: number;
  /**
   * 机密参考文献
   *
   * 用户保存的哪个机密要公开给这个智能体。 null=全部； [] = None; 非 null 列表 = 指定键的过滤器。 严格：不添加任何内容。 ACP 配置文件必须列出自己的提供者凭据才能接收它。
   */
  secret_refs?: Array<string> | null;
  /**
   * 系统消息后缀
   *
   * 附加到系统的可选后缀提示词。
   */
  system_message_suffix?: string | null;
  /**
   * 工具并发限制
   *
   * 每个智能体步骤同时执行的最大工具调用数量。 1 = 顺序（默认）。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   *
   * 刀具选择已解决智能体。 None（默认）=服务器的标准工具集； [] = 明确裸露的智能体； 完全按照给定的方式使用非空列表。
   */
  tools?: Array<ToolInput> | null;
  /**
   * 批评/验证政策（机密-免费； 没有critic_api_key）。
   */
  verification?: ProfileVerificationSettings;
};

/**
 * OrgConfig
 *
 * 用于加载组织级技能的配置。
 */
export type OrgConfig = {
  /**
   * 组织名称
   *
   * 组织名称
   */
  org_name: string;
  /**
   * 组织回购网址
   *
   * 组织存储库的预验证 Git URL。 含有敏感物质凭据 - 小心处理并避免记录。
   */
  org_repo_url: string;
  /**
   * 提供商
   *
   * Git 提供程序类型：GitHub、GitLab、azure、bitbucket
   */
  provider: string;
  /**
   * 存储库
   *
   * 选定的存储库（e.g.，'所有者/存储库'）
   */
  repository: string;
};

/**
 * PassCritic
 *
 * 总是返回成功的批评者。
 *
 * 当不需要评估或当
 * 无论输出如何，所有实例都应被视为成功。
 */
export type PassCriticInput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind?: 'PassCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * PassCritic
 *
 * 总是返回成功的批评者。
 *
 * 当不需要评估或当
 * 无论输出如何，所有实例都应被视为成功。
 */
export type PassCriticOutput = {
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind: 'PassCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
};

/**
 * PathTrigger
 *
 * 触发路径范围的技能（“规则”）。
 *
 * 当智能体触及路径匹配的文件时，这些技能被激活
 * ``paths`` glob 模式之一（gitignore 风格 ``**`` 语义）。
 */
export type PathTrigger = {
  /**
   * 路径
   */
  paths: Array<string>;
  /**
   * 类型
   */
  type?: 'path';
};

/**
 * PatternSecurityAnalyzer
 *
 * 通过确定性签名扫描捕获危险的智能体操作。
 *
 * 当您需要快速、本地、无网络威胁检测时，请使用此选项
 * 动作边界。 它返回 ``SecurityRisk.HIGH``、``MEDIUM`` 或 ``LOW``。
 * 当shell扫描无法解析相关时返回``UNKNOWN``
 * 破坏性结构。 将其与 ``ConfirmRisky`` 配对来决定得到什么
 * 已确认。
 *
 * 关键的设计选择：外壳破坏性模式仅扫描
 * 智能体将*执行*（工具参数），而不是它*想到的*
 * (reasoning text). 注射模式扫描一切，因为
 * “忽略所有先前的指示”无论出现​​在哪里都是危险的。
 *
 * 标准化始终开启——不可见字符和全角
 * 替换在匹配之前折叠。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 PatternSecurityAnalyzer, ConfirmRisky
 *
 * 分析器 = PatternSecurityAnalyzer()
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type PatternSecurityAnalyzerInput = {
  /**
   * 高图案
   *
   * HIGH 仅针对可执行字段扫描模式
   */
  high_patterns?: Array<[string, string, string]>;
  /**
   * 注塑高模
   *
   * HIGH 针对所有字段扫描的模式
   */
  injection_high_patterns?: Array<[string, string, string]>;
  /**
   * 注射介质模式
   *
   * MEDIUM 针对所有字段扫描的模式
   */
  injection_medium_patterns?: Array<[string, string, string]>;
  /**
   * 种类
   */
  kind?: 'PatternSecurityAnalyzer';
  /**
   * 中等图案
   *
   * MEDIUM 仅针对可执行字段扫描模式
   */
  medium_patterns?: Array<[string, string, string]>;
};

/**
 * PatternSecurityAnalyzer
 *
 * 通过确定性签名扫描捕获危险的智能体操作。
 *
 * 当您需要快速、本地、无网络威胁检测时，请使用此选项
 * 动作边界。 它返回 ``SecurityRisk.HIGH``、``MEDIUM`` 或 ``LOW``。
 * 当shell扫描无法解析相关时返回``UNKNOWN``
 * 破坏性结构。 将其与 ``ConfirmRisky`` 配对来决定得到什么
 * 已确认。
 *
 * 关键的设计选择：外壳破坏性模式仅扫描
 * 智能体将*执行*（工具参数），而不是它*想到的*
 * (reasoning text). 注射模式扫描一切，因为
 * “忽略所有先前的指示”无论出现​​在哪里都是危险的。
 *
 * 标准化始终开启——不可见字符和全角
 * 替换在匹配之前折叠。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 PatternSecurityAnalyzer, ConfirmRisky
 *
 * 分析器 = PatternSecurityAnalyzer()
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type PatternSecurityAnalyzerOutput = {
  /**
   * 高图案
   *
   * HIGH 仅针对可执行字段扫描模式
   */
  high_patterns?: Array<[string, string, string]>;
  /**
   * 注塑高模
   *
   * HIGH 针对所有字段扫描的模式
   */
  injection_high_patterns?: Array<[string, string, string]>;
  /**
   * 注射介质模式
   *
   * MEDIUM 针对所有字段扫描的模式
   */
  injection_medium_patterns?: Array<[string, string, string]>;
  /**
   * 种类
   */
  kind: 'PatternSecurityAnalyzer';
  /**
   * 中等图案
   *
   * MEDIUM 仅针对可执行字段扫描模式
   */
  medium_patterns?: Array<[string, string, string]>;
};

/**
 * PauseEvent
 *
 * 指示智能体执行已根据用户请求暂停的事件。
 */
export type PauseEvent = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'PauseEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * PipelineCondenser
 *
 * 按顺序应用上下文压缩器序列的上下文压缩器。
 *
 * 所有上下文压缩器主要由它们的 `condense` 方法定义，该方法采用
 * `View` 和一个可选的 `agent_llm` 参数，返回一个新的 `View` 或一个
 * `Condensation` 事件。 这意味着我们可以通过以下方式将多个上下文压缩器链接在一起
 * 如果任何上下文压缩器返回 `Condensation`，则传递 `View` 并提前退出。
 *
 * 例如：
 *
 * # 使用管道上下文压缩器将多个其他上下文压缩器链接在一起
 * 上下文压缩器 = PipelineCondenser(上下文压缩器=[
 * CondenserA(...),
 * CondenserB(...),
 * CondenserC(...),
 * ])
 *
 * 结果= condenser.condense（视图，agent_llm=agent_llm）
 *
 * # 在没有管道上下文压缩器的情况下做同样的事情需要更多样板
 * # 对于单子链
 * other_result = 查看
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserA(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserB(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserC(...).condense(other_result, agent_llm=agent_llm)
 *
 * 断言结果 == other_result
 */
export type PipelineCondenserInput = {
  /**
   * 上下文压缩器
   */
  condensers: Array<CondenserBaseInput>;
  /**
   * 种类
   */
  kind?: 'PipelineCondenser';
};

/**
 * PipelineCondenser
 *
 * 按顺序应用上下文压缩器序列的上下文压缩器。
 *
 * 所有上下文压缩器主要由它们的 `condense` 方法定义，该方法采用
 * `View` 和一个可选的 `agent_llm` 参数，返回一个新的 `View` 或一个
 * `Condensation` 事件。 这意味着我们可以通过以下方式将多个上下文压缩器链接在一起
 * 如果任何上下文压缩器返回 `Condensation`，则传递 `View` 并提前退出。
 *
 * 例如：
 *
 * # 使用管道上下文压缩器将多个其他上下文压缩器链接在一起
 * 上下文压缩器 = PipelineCondenser(上下文压缩器=[
 * CondenserA(...),
 * CondenserB(...),
 * CondenserC(...),
 * ])
 *
 * 结果= condenser.condense（视图，agent_llm=agent_llm）
 *
 * # 在没有管道上下文压缩器的情况下做同样的事情需要更多样板
 * # 对于单子链
 * other_result = 查看
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserA(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserB(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserC(...).condense(other_result, agent_llm=agent_llm)
 *
 * 断言结果 == other_result
 */
export type PipelineCondenserOutput = {
  /**
   * 上下文压缩器
   */
  condensers: Array<CondenserBaseOutput>;
  /**
   * 种类
   */
  kind: 'PipelineCondenser';
};

/**
 * PlanningFileEditorAction
 *
 * 模式用于规划文件编辑器操作。
 *
 * 继承自 FileEditorAction，但仅限编辑 PLAN.md。
 * 允许查看任何文件，但只能编辑 PLAN.md。
 */
export type PlanningFileEditorAction = {
  /**
   * 命令
   *
   * 要运行的命令。 允许的选项有：`view`、`create`、`str_replace`、`insert`、`undo_edit`。
   */
  command: 'view' | 'create' | 'str_replace' | 'insert' | 'undo_edit';
  /**
   * 文件文本
   *
   * `create`命令必需的参数，包含要创建的文件的内容。
   */
  file_text?: string | null;
  /**
   * 插入行
   *
   * `insert`命令的必需参数。 `new_str` 将插入之后 `path` 的第 `insert_line` 行。
   */
  insert_line?: number | null;
  /**
   * 种类
   */
  kind: 'PlanningFileEditorAction';
  /**
   * 新街
   *
   * `str_replace`命令的可选参数包含新字符串（如果未给出，则不会添加任何字符串）。 `insert` 命令的必需参数，包含要插入的字符串。
   */
  new_str?: string | null;
  /**
   * 老街
   *
   * `str_replace` 命令的必需参数包含要替换的 `path` 中的字符串。
   */
  old_str?: string | null;
  /**
   * 路径
   *
   * 文件或目录的绝对路径。
   */
  path: string;
  /**
   * 视野范围
   *
   * 当`path`指向文件时，`view`命令的可选参数。 如果给出 None，则显示完整文件。 如果提供，该文件将显示在指定的行号范围 e.g 中。 [11, 12] 将显示第 11 行和第 12 行。 索引从 1 开始。 设置 `[start_line, -1]` 显示从 `start_line` 到文件末尾的所有行。
   */
  view_range?: Array<number> | null;
};

/**
 * PlanningFileEditorObservation
 *
 * 观测结果来自规划文件编辑器的操作。
 *
 * 继承自 FileEditorObservation - 结构相同，只是类型不同。
 */
export type PlanningFileEditorObservation = {
  /**
   * 命令
   *
   * 运行的命令：`view`、`create`、`str_replace`、`insert` 或 `undo_edit`。
   */
  command: 'view' | 'create' | 'str_replace' | 'insert' | 'undo_edit';
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'PlanningFileEditorObservation';
  /**
   * 新内容
   *
   * 编辑后的文件内容。
   */
  new_content?: string | null;
  /**
   * 旧内容
   *
   * 编辑前的文件内容。
   */
  old_content?: string | null;
  /**
   * 路径
   *
   * 已编辑的文件路径。
   */
  path?: string | null;
  /**
   * 上一个存在
   *
   * 指示该文件以前是否存在。 如果没有，它就被创建了。
   */
  prev_exist?: boolean;
};

/**
 * PlanningFileEditorTool
 *
 * 具有只读、仅限 edit-PLAN.md 访问权限的规划文件编辑器工具。
 */
export type PlanningFileEditorTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'PlanningFileEditorTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * PluginInfo
 *
 * 可用插件的摘要。
 */
export type PluginInfo = {
  /**
   * 描述
   */
  description?: string;
  /**
   * 文件
   *
   * 插件文件，相对于插件目录
   */
  files?: Array<string>;
  /**
   * 名称
   */
  name: string;
  /**
   * 路径
   *
   * 插件目录的路径
   */
  path?: string;
  /**
   * 技能
   *
   * 插件中捆绑的技能
   */
  skills?: Array<PluginSkillSummary>;
  /**
   * 版本
   */
  version?: string;
};

/**
 * PluginSkillSummary
 *
 * 插件中捆绑的技能摘要。
 */
export type PluginSkillSummary = {
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 名称
   */
  name: string;
};

/**
 * PluginSource
 *
 * 要加载的插件的规范。
 *
 * 该模型描述了在哪里可以找到插件并由 load_plugins() 使用
 * 从各种来源获取和加载插件。
 *
 * 示例：
 * >>> # GitHub 存储库
 * >>> PluginSource（来源=“GitHub：所有者/回购”，参考=“v1.0.0”）
 *
 * >>> # 来自单体仓库子目录的插件
 * >>> PluginSource(
 * ... 来源=“GitHub：所有者/monorepo”，
 * ... repo_path="插件/我的插件"
 * ... )
 *
 * >>> # 本地路径
 * >>> PluginSource（来源=“/path/to/plugin")
 */
export type PluginSource = {
  /**
   * 参考号
   *
   * 可选分支、标签或提交（仅适用于 git 源）
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * git 存储库中的子目录路径（e.g., 'plugins/my-plugin' for monorepos）。 仅与 git 源相关，与本地路径无关。
   */
  repo_path?: string | null;
  /**
   * 来源
   *
   * 插件源：'GitHub:owner/repo'、任何 git URL 或本地路径
   */
  source: string;
};

/**
 * PluginsRequest
 *
 * 列出本地可用插件的请求正文。
 */
export type PluginsRequest = {
  /**
   * 加载项目
   *
   * 从工作区加载项目插件
   */
  load_project?: boolean;
  /**
   * 加载用户
   *
   * 加载用户插件（~/.agents/plugins等）
   */
  load_user?: boolean;
  /**
   * 项目目录
   *
   * 工作区项目插件的目录路径
   */
  project_dir?: string | null;
};

/**
 * PluginsResponse
 *
 * 包含本地可用插件的响应。
 */
export type PluginsResponse = {
  /**
   * 插件
   */
  plugins: Array<PluginInfo>;
};

/**
 * PolicyRailSecurityAnalyzer
 *
 * 捕获由 shell 命令结构定义的威胁。
 *
 * 命名rails使用shell语法来检测危险操作，例如
 * 网络获取通过管道传输到下游命令。 每段评估保留
 * 威胁模型可解释并阻止来自不同字段的文本
 * 形成一场比赛。
 *
 * 仅评估原始可执行段——推理文本永远不会
 * 已扫描。
 *
 * 当铁轨起火时返回 ``SecurityRisk.HIGH``，当铁轨起火时返回 ``UNKNOWN``
 * 无法解析相关的shell结构。 ``LOW`` 表示没有
 * 配置的轨道匹配并且不存在相关的不确定性。 它不
 * 建立一般安全或授权。 与 ``ConfirmRisky`` 和
 * 通过 ``EnsembleSecurityAnalyzer`` 撰写。
 *
 * v1 Rails：获取执行、原始磁盘操作、灾难性删除。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 PolicyRailSecurityAnalyzer
 *
 * 分析器 = PolicyRailSecurityAnalyzer()
 * # 风险 = analyzer.security_risk(行动)
 */
export type PolicyRailSecurityAnalyzerInput = {
  /**
   * 种类
   */
  kind?: 'PolicyRailSecurityAnalyzer';
};

/**
 * PolicyRailSecurityAnalyzer
 *
 * 捕获由 shell 命令结构定义的威胁。
 *
 * 命名rails使用shell语法来检测危险操作，例如
 * 网络获取通过管道传输到下游命令。 每段评估保留
 * 威胁模型可解释并阻止来自不同字段的文本
 * 形成一场比赛。
 *
 * 仅评估原始可执行段——推理文本永远不会
 * 已扫描。
 *
 * 当铁轨起火时返回 ``SecurityRisk.HIGH``，当铁轨起火时返回 ``UNKNOWN``
 * 无法解析相关的shell结构。 ``LOW`` 表示没有
 * 配置的轨道匹配并且不存在相关的不确定性。 它不
 * 建立一般安全或授权。 与 ``ConfirmRisky`` 和
 * 通过 ``EnsembleSecurityAnalyzer`` 撰写。
 *
 * v1 Rails：获取执行、原始磁盘操作、灾难性删除。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 PolicyRailSecurityAnalyzer
 *
 * 分析器 = PolicyRailSecurityAnalyzer()
 * # 风险 = analyzer.security_risk(行动)
 */
export type PolicyRailSecurityAnalyzerOutput = {
  /**
   * 种类
   */
  kind: 'PolicyRailSecurityAnalyzer';
};

/**
 * ProfileDetailResponse
 *
 * 除非通过 X-Expose-机密明确请求，否则机密为空。
 */
export type ProfileDetailResponse = {
  /**
   * API 按键设置
   */
  api_key_set?: boolean;
  /**
   * 配置
   */
  config: {
    [key: string]: unknown;
  };
  /**
   * 名称
   */
  name: string;
};

/**
 * ProfileInfo
 */
export type ProfileInfo = {
  /**
   * API 按键设置
   */
  api_key_set?: boolean;
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 型号
   */
  model?: string | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 提供商连接中断
   */
  provider_connection_broken?: boolean;
  /**
   * 提供商连接 ID
   */
  provider_connection_id?: string | null;
};

/**
 * ProfileListResponse
 */
export type ProfileListResponse = {
  /**
   * 活动档案
   */
  active_profile?: string | null;
  /**
   * 型材
   */
  profiles: Array<ProfileInfo>;
};

/**
 * ProfileMutationResponse
 */
export type ProfileMutationResponse = {
  /**
   * 留言
   */
  message: string;
  /**
   * 名称
   */
  name: string;
};

/**
 * ProfileVerificationSettings
 *
 * 机密-个人资料的免费评论家/细化政策。
 *
 * 的非凭据子集
 * ：类：`~openhands.sdk.settings.model.VerificationSettings`：``critic_api_key``
 * 被省略，因此配置文件不包含机密。 批评家重用了已解决的问题
 * LLM 配置文件的密钥（现有的 ``critic_api_key=None`` 行为）。
 */
export type ProfileVerificationSettings = {
  /**
   * 启用评论家
   */
  critic_enabled?: boolean;
  /**
   * 批评模式
   */
  critic_mode?: 'finish_and_message' | 'all_actions';
  /**
   * 评论家模型名称
   */
  critic_model_name?: string | null;
  /**
   * 评论家服务器 URL
   */
  critic_server_url?: string | null;
  /**
   * 批评阈值
   */
  critic_threshold?: number;
  /**
   * 启用迭代细化
   */
  enable_iterative_refinement?: boolean;
  /**
   * 最大细化迭代次数
   */
  max_refinement_iterations?: number;
};

/**
 * ProviderConnectionCreateRequest
 */
export type ProviderConnectionCreateRequest = {
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 显示名称
   */
  display_name: string;
  /**
   * 提供商
   */
  provider?: string;
};

/**
 * ProviderConnectionResponse
 */
export type ProviderConnectionResponse = {
  /**
   * API 按键设置
   */
  api_key_set?: boolean;
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 创建于
   */
  created_at: number;
  /**
   * 显示名称
   */
  display_name: string;
  /**
   * 身份证号
   */
  id: string;
  /**
   * 提供商
   */
  provider: string;
  /**
   * 更新于
   */
  updated_at: number;
};

/**
 * ProviderConnectionUpdateRequest
 */
export type ProviderConnectionUpdateRequest = {
  /**
   * API 钥匙
   */
  api_key?: null;
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 显示名称
   */
  display_name?: string | null;
  /**
   * 提供商
   */
  provider?: string | null;
};

/**
 * ProvidersResponse
 *
 * 包含可用 LLM 提供商列表的响应。
 */
export type ProvidersResponse = {
  /**
   * 供应商
   */
  providers: Array<string>;
};

/**
 * ReadFileAction
 *
 * 模式用于读文件操作。
 */
export type ReadFileAction = {
  /**
   * 文件路径
   *
   * 要读取的文件的路径。
   */
  file_path: string;
  /**
   * 种类
   */
  kind: 'ReadFileAction';
  /**
   * 限制
   *
   * 可选：要读取的最大行数。 与“offset”一起使用可对大文件进行分页。
   */
  limit?: number | null;
  /**
   * 偏移量
   *
   * 可选：从 0 开始读取的行号。 用于对大文件进行分页。
   */
  offset?: number | null;
};

/**
 * ReadFileObservation
 *
 * 观测结果读取文件。
 */
export type ReadFileObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 文件内容
   *
   * 从文件中读取的内容。
   */
  file_content?: string;
  /**
   * 文件路径
   *
   * 读取的文件路径。
   */
  file_path: string;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 被截断
   *
   * 内容是否因大小限制而被截断。
   */
  is_truncated?: boolean;
  /**
   * 种类
   */
  kind: 'ReadFileObservation';
  /**
   * 显示线路
   *
   * 如果被截断，则显示的行范围（开始、结束） - 1 索引。
   */
  lines_shown?: [number, number] | null;
  /**
   * 总行数
   *
   * 文件中的总行数。
   */
  total_lines?: number | null;
};

/**
 * ReadFileTool
 *
 * 用于读取文件内容并支持分页的工具。
 */
export type ReadFileTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ReadFileTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * ReasoningItemModel
 *
 * OpenAI 响应推理项（非流，我们使用的子集）。
 *
 * 不记录或渲染 encrypted_content。
 */
export type ReasoningItemModel = {
  /**
   * 内容
   */
  content?: Array<string> | null;
  /**
   * 加密内容
   */
  encrypted_content?: string | null;
  /**
   * 身份证号
   */
  id?: string | null;
  /**
   * 状态
   */
  status?: string | null;
  /**
   * 总结
   */
  summary?: Array<string>;
};

/**
 * RedactedThinkingBlock
 *
 * 已脱敏先前回复的思维障碍，没有扩展思考。
 *
 * 这用作生成的辅助消息的占位符
 * 在启用扩展思维之前。
 */
export type RedactedThinkingBlock = {
  /**
   * 数据
   *
   * 已脱敏思考内容
   */
  data: string;
  /**
   * 类型
   */
  type?: 'redacted_thinking';
};

/**
 * RemoteMCPServer
 *
 * 传统远程 MCP 服务器规范已被公众接受 REST API。
 */
export type RemoteMcpServer = {
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInput)
    | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 类型
   */
  type: 'http' | 'shttp' | 'streamable-http' | 'sse';
  /**
   * 网址
   */
  url: string;
};

/**
 * RemoteWorkspace
 *
 * 连接到 OpenHands Agent Server 的远程工作区实现。
 *
 * RemoteWorkspace 提供对远程运行的沙盒环境的访问
 * OpenHands Agent Server. 这是生产部署的推荐方法
 * 因为它提供了更好的隔离和安全性。
 *
 * 支持通过环境变量退出时可选的完成回调：
 * - ``AUTOMATION_CALLBACK_URL`` — URL 至 POST 完成状态
 * - ``AUTOMATION_CALLBACK_API_KEY`` — 持有者令牌用于回调身份验证（可选）
 * - ``AUTOMATION_RUN_ID`` — 要包含在回调载荷中的运行 ID（可选）
 *
 * 示例：
 * >>> 工作区 = RemoteWorkspace(
 * ... 主机=“ https://agent-server.example.com",
 * ...     working_dir="/workspace"
 * ... )
 * >>> 与工作区：
 * ... 结果 = workspace.execute_command("ls -la")
 * ... 内容 = workspace.read_file("README.md")
 */
export type RemoteWorkspace = {
  /**
   * API 钥匙
   *
   * API 用于与远程主机进行身份验证的密钥。
   */
  api_key?: string | null;
  /**
   * 主持人
   *
   * 远程主机URL为工作区。
   */
  host: string;
  /**
   * 种类
   */
  kind: 'RemoteWorkspace';
  /**
   * 最大连接数
   *
   * httpx.Client 的最大连接数。 None 表示没有限制，对于并行运行多个对话很有用。
   */
  max_connections?: number | null;
  /**
   * 阅读超时
   *
   * 超时以秒为单位读取 httpx.Client 操作。
   */
  read_timeout?: number;
  /**
   * 运行时对话 ID
   *
   * 会话运行时范围； None 使用主机工作区。
   */
  runtime_conversation_id?: string | null;
  /**
   * 工作目录
   *
   * 工作目录用于智能体操作和工具执行。
   */
  working_dir: string;
};

/**
 * RenameAgentProfileRequest
 */
export type RenameAgentProfileRequest = {
  /**
   * 新名称
   */
  new_name: string;
};

/**
 * RenameProfileRequest
 */
export type RenameProfileRequest = {
  /**
   * 新名称
   */
  new_name: string;
};

/**
 * SandboxConfig
 *
 * 用于加载沙箱特定技能的配置。
 */
export type SandboxConfig = {
  /**
   * 暴露的网址
   *
   * 暴露的列表 URLs 从沙盒
   */
  exposed_urls?: Array<ExposedUrl>;
};

/**
 * SaveProfileRequest
 */
export type SaveProfileRequest = {
  /**
   * 包括机密
   *
   * 是否使用配置文件持久化 API 键。
   */
  include_secrets?: boolean;
  llm: LlmInput;
};

/**
 * SecretCreateRequest
 *
 * 请求 PUT /api/settings/secrets. 的模型
 *
 * 使用给定名称和值创建或更新机密。
 */
export type SecretCreateRequest = {
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 名称
   */
  name: string;
};

/**
 * SecretItemResponse
 *
 * 机密项的响应模型（无值）。
 *
 * 用于列表响应以及作为创建/更新操作的响应。
 */
export type SecretItemResponse = {
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 名称
   */
  name: string;
};

/**
 * SecretRegistry
 *
 * 管理机密并在需要时将它们注入到 bash 命令中。
 *
 * 机密注册表存储机密键到 SecretSources 的映射
 * 检索实际的机密值。 当 bash 命令即将执行时
 * 执行时，它会扫描命令中的任何机密键并注入相应的
 * 环境变量。
 *
 * 机密来源将酌情编辑/加密其敏感值
 * 序列化，取决于上下文的内容。 如果存在上下文
 * 并包含一个“密码”对象，用于加密。 如果它包含一个
 * 设置为 True、机密的布尔“expose_secrets”标志以纯文本形式转储。
 * 否则机密为已脱敏。
 *
 * 此外，它还跟踪最新导出的值以实现一致的屏蔽
 * 即使可调用机密在后续调用中失败。
 */
export type SecretRegistry = {
  /**
   * 机密来源
   */
  secret_sources?: {
    [key: string]: SecretSourceOutput;
  };
};

export type SecretSourceInput =
  | ({
      kind: 'openhands__sdk__secret__secrets__LookupSecret-Input__1';
    } & LookupSecretInput)
  | ({
      kind: 'openhands__sdk__secret__secrets__StaticSecret-Input__1';
    } & StaticSecretInput);

export type SecretSourceOutput =
  | ({
      kind: 'openhands__sdk__secret__secrets__LookupSecret-Output__1';
    } & LookupSecretOutput)
  | ({
      kind: 'openhands__sdk__secret__secrets__StaticSecret-Output__1';
    } & StaticSecretOutput);

/**
 * SecretsListResponse
 *
 * GET /api/settings/secrets. 的响应模型
 *
 * 列出所有可用的机密及其名称和描述。
 * 值永远不会包含在列表响应中。
 */
export type SecretsListResponse = {
  /**
   * 机密
   */
  secrets: Array<SecretItemResponse>;
};

/**
 * SecurityAnalysisEvent
 *
 * 已配置的安全分析器分配给待处理操作的风险级别。
 *
 * 每当智能体即将执行的每批操作发出一次
 * 安全分析器在会话上配置，无论是否
 * 然后确认策略要求确认。 这使得
 * 即使策略被执行，分析器的结论也会在事件日志和 UI 中可见
 * （例如 ``NeverConfirm``）从不查阅它。
 *
 * 该事件不会发送到 LLM。
 */
export type SecurityAnalysisEvent = {
  /**
   * 分析仪
   *
   * 产生这些风险的安全分析器的种类。
   */
  analyzer: string;
  /**
   * 详情
   *
   * 每个操作的可选分析器特定详细信息，由 ActionEvent id 键入（例如概率、置信度或基本原理）。
   */
  details?: {
    [key: string]: {
      [key: string]: unknown;
    };
  };
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'SecurityAnalysisEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 政策
   *
   * 分析操作时有效的确认策略类型。
   */
  policy: string;
  /**
   * 风险
   *
   * 每个分析操作的风险级别，以 ActionEvent id 为键。
   */
  risks: {
    [key: string]: SecurityRisk;
  };
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

export type SecurityAnalyzerBaseInput =
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__pattern__PatternSecurityAnalyzer-Input__1';
    } & PatternSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__policy_rails__PolicyRailSecurityAnalyzer-Input__1';
    } & PolicyRailSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__ensemble__EnsembleSecurityAnalyzer-Input__1';
    } & EnsembleSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__grayswan__analyzer__GraySwanAnalyzer-Input__1';
    } & GraySwanAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__llm_analyzer__LLMSecurityAnalyzer-Input__1';
    } & LlmSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__toolshield_llm_analyzer__ToolShieldLLMSecurityAnalyzer-Input__1';
    } & ToolShieldLlmSecurityAnalyzerInput);

export type SecurityAnalyzerBaseOutput =
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__pattern__PatternSecurityAnalyzer-Output__1';
    } & PatternSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__policy_rails__PolicyRailSecurityAnalyzer-Output__1';
    } & PolicyRailSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__ensemble__EnsembleSecurityAnalyzer-Output__1';
    } & EnsembleSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__grayswan__analyzer__GraySwanAnalyzer-Output__1';
    } & GraySwanAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__llm_analyzer__LLMSecurityAnalyzer-Output__1';
    } & LlmSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__toolshield_llm_analyzer__ToolShieldLLMSecurityAnalyzer-Output__1';
    } & ToolShieldLlmSecurityAnalyzerOutput);

/**
 * SecurityRisk
 *
 * 操作的安全风险级别。
 *
 * 基于 OpenHands 安全风险级别，但适用于智能体-SDK。
 * 整数值可以轻松比较和排序。
 */
export type SecurityRisk = 'UNKNOWN' | 'LOW' | 'MEDIUM' | 'HIGH';

/**
 * SendMessageRequest
 *
 * 载荷向智能体发送消息。
 */
export type SendMessageRequest = {
  /**
   * 内容
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 角色
   */
  role?: 'user' | 'system' | 'assistant' | 'tool';
  /**
   * 运行
   *
   * 如果智能体循环不运行，是否自动运行
   */
  run?: boolean;
};

/**
 * ServerErrorEvent
 *
 * 发生服务器级错误时由 Agent Server 发出的事件。
 *
 * 此事件用于源自 Agent Server 本身的错误，
 * 例如 MCP 连接失败、WebSocket 错误或其他基础设施
 * 问题。 不像 ConversationErrorEvent 这是针对会话级失败的
 * 此事件表明服务器环境存在问题。
 */
export type ServerErrorEvent = {
  /**
   * 代码
   *
   * 错误代码 - 通常是错误类型
   */
  code: string;
  /**
   * 详情
   *
   * 有关错误的详细信息
   */
  detail: string;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'ServerErrorEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   *
   * 本次活动的来源
   */
  source: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * SetConfirmationPolicyRequest
 *
 * 载荷设置对话的确认策略。
 */
export type SetConfirmationPolicyRequest = {
  /**
   * 要设置的确认策略
   */
  policy: ConfirmationPolicyBaseInput;
};

/**
 * SetSecurityAnalyzerRequest
 *
 * 载荷为对话设置安全分析器
 */
export type SetSecurityAnalyzerRequest = {
  /**
   * 安全分析器设置
   */
  security_analyzer: SecurityAnalyzerBaseInput | null;
};

/**
 * SettingProminence
 */
export type SettingProminence = 'critical' | 'major' | 'minor';

/**
 * SettingsChoice
 */
export type SettingsChoice = {
  /**
   * 标签
   */
  label: string;
  /**
   * 价值
   */
  value: boolean | number | number | string;
};

/**
 * SettingsFieldSchema
 */
export type SettingsFieldSchema = {
  /**
   * 选择
   */
  choices?: Array<SettingsChoice>;
  /**
   * 默认
   */
  default?: unknown;
  /**
   * 取决于
   */
  depends_on?: Array<string>;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 钥匙
   */
  key: string;
  /**
   * 标签
   */
  label: string;
  prominence?: SettingProminence;
  /**
   * 机密
   */
  secret?: boolean;
  /**
   * 部分
   */
  section: string;
  /**
   * 部分标签
   */
  section_label: string;
  /**
   * 值类型
   */
  value_type: 'string' | 'integer' | 'number' | 'boolean' | 'array' | 'object';
  /**
   * 变体
   *
   * 设置后，该字段仅适用于指定的 ``AgentSettings`` 变体（``'openhands'`` 或 ``'acp'``）。 GUI 按用户当前的变体过滤字段； 无论如何，都会显示带有 ``variant=None`` 的字段。
   */
  variant?: string | null;
};

/**
 * SettingsResponse
 *
 * GET /api/settings. 的响应模型
 *
 * 包含完整设置载荷，包括智能体配置，
 * 对话设置、活动 LLM 配置文件、前端拥有的其他内容
 * 设置，以及一个标志，指示 LLM API 键是否已设置。
 *
 * ``agent_settings`` 和 ``conversation_settings`` 字段是原始字典
 * 因为服务器通过上下文控制机密序列化。 使用
 * 验证的类型化访问器方法：
 *
 * 示例：:
 *
 * 响应 = SettingsResponse.model_validate(api_response.json())
 * 智能体 = response.get_agent_settings() # 返回 AgentSettingsConfig
 * 转换 = response.get_conversation_settings() # 返回 ConversationSettings
 *
 * ``misc_settings`` 是前端拥有的数据的不透明容器，
 * 智能体-服务器持续存在但不解释 - 请参阅文档字符串
 * ：类：`PersistedSettings.misc_settings`。
 */
export type SettingsResponse = {
  /**
   * 活动智能体配置文件 ID
   *
   * 当前活动的稳定 ID AgentProfile（如果已设置）。
   */
  active_agent_profile_id?: string | null;
  /**
   * 活动元配置文件
   *
   * 当前活动元配置文件的名称（如果已选择）。
   */
  active_meta_profile?: string | null;
  /**
   * 活动档案
   *
   * 当前活动的 LLM 配置文件的名称（如果已选择）。
   */
  active_profile?: string | null;
  /**
   * _AgentSettingsContract
   */
  agent_settings: {
    /**
     * 智能体种类
     */
    agent_kind?: 'openhands' | 'acp' | null;
    mcp_config: McpConfig;
    /**
     * 模式版本
     */
    schema_version?: number | null;
    [key: string]: unknown;
  };
  /**
   * 对话设置
   */
  conversation_settings: {
    [key: string]: unknown;
  };
  /**
   * Llm API 键已设置
   */
  llm_api_key_is_set: boolean;
  /**
   * 其他设置
   */
  misc_settings?: {
    [key: string]: unknown;
  };
};

/**
 * SettingsSchema
 */
export type SettingsSchema = {
  /**
   * 型号名称
   */
  model_name: string;
  /**
   * 部分
   */
  sections: Array<SettingsSectionSchema>;
};

/**
 * SettingsSectionSchema
 */
export type SettingsSectionSchema = {
  /**
   * 领域
   */
  fields: Array<SettingsFieldSchema>;
  /**
   * 钥匙
   */
  key: string;
  /**
   * 标签
   */
  label: string;
  /**
   * 变体
   *
   * 设置后，此部分仅适用于命名的 ``AgentSettings`` 变体 (e.g. ``'openhands'``或``'acp'``）。 GUI 按当前 ``agent_kind`` 值过滤部分； 始终显示带有 ``variant=None`` 的部分。
   */
  variant?: string | null;
};

/**
 * SettingsUpdateRequest
 *
 * 请求 PATCH /api/settings. 的模型
 *
 * 支持通过深度合并的 diff 对象进行部分更新
 * 现有设置。 ``misc_settings_diff`` 深度合并到
 * 已持久化 ``misc_settings`` 块具有相同的语义
 * ``agent_settings_diff`` 和 ``conversation_settings_diff``：嵌套字典
 * 递归合并，列表被批量替换而不是合并。
 * 因为 ``misc_settings`` 对智能体服务器不透明，所以调用者
 * 负责他们存储在那里的东西的形状。
 */
export type SettingsUpdateRequest = {
  /**
   * 活动智能体配置文件 ID
   *
   * 活动的稳定 ID AgentProfile 至持久化； null 清除它。
   */
  active_agent_profile_id?: string | null;
  /**
   * 活动元配置文件
   *
   * 活动元配置文件的名称为持久化； null 清除它。
   */
  active_meta_profile?: string | null;
  /**
   * 活动档案
   *
   * 活动 LLM 配置文件的名称到持久化； null 清除它。
   */
  active_profile?: string | null;
  /**
   * 智能体设置差异
   */
  agent_settings_diff?: {
    mcp_config?: McpConfigPatch | null;
    [key: string]: unknown;
  } | null;
  /**
   * 对话设置差异
   */
  conversation_settings_diff?: {
    [key: string]: unknown;
  } | null;
  /**
   * 杂项设置差异
   */
  misc_settings_diff?: {
    [key: string]: unknown;
  } | null;
};

/**
 * 技能
 *
 * 技能提供专业知识或功能。
 *
 * 技能行为取决于格式（is_agentskills_format）和触发器：
 *
 * AgentSkills 格式（SKILL.md 个文件）：
 * - 始终在 <available_skills> 中列出，包含名称、描述、位置
 * - 智能体按需阅读完整内容（渐进式披露）
 * - 如果有触发器：触发时内容会自动注入 ALSO
 *
 * 旧版 OpenHands 格式：
 * - 带触发器：列在<available_skills>中，在触发器上注入内容
 * - 无触发器 (None)：<REPO_CONTEXT> 中的完整内容，始终处于活动状态
 *
 * 该模型支持 OpenHands 特定字段和 AgentSkills 标准
 * 用于跨平台兼容性的字段（ https://agentskills.io/specification ）。
 */
export type SkillInput = {
  /**
   * 允许使用的工具
   *
   * 此技能的预先批准的工具列表。 AgentSkills 标准字段（从空格分隔的字符串解析）。
   */
  allowed_tools?: Array<string> | null;
  /**
   * 兼容性
   *
   * 该技能的环境要求或兼容性说明。 AgentSkills 标准字段（e.g., '需要 git 和 Docker'）。
   */
  compatibility?: string | null;
  /**
   * 内容
   */
  content: string;
  /**
   * 描述
   *
   * 简要描述该技能的作用以及何时使用它。 超过 MAX_DESCRIPTION_LENGTH 的描述将被截断，并带有指向技能源路径的通知。
   */
  description?: string | null;
  /**
   * 禁用模型调用
   *
   * 该技能是否只能通过触发匹配来激活，并且不应发布到模型以直接调用。
   */
  disable_model_invocation?: boolean;
  /**
   * 输入
   *
   * 输入技能的元数据（仅限任务技能）
   */
  inputs?: Array<InputMetadata>;
  /**
   * 是 Agentskills 格式
   *
   * 该技能是否是从遵循 AgentSkills 标准的 SKILL.md 文件加载的。 AgentSkills-格式技能使用渐进式披露：始终在 <available_skills> 中列出，并包含名称、描述和位置。 如果该技能也有触发器，则触发时会自动注入内容AND智能体可以随时读取文件。
   */
  is_agentskills_format?: boolean;
  /**
   * 许可证
   *
   * 分发技能所依据的许可证。 AgentSkills 标准字段（e.g.、“Apache-2.0”、“MIT”）。
   */
  license?: string | null;
  /**
   * MCP 工具
   *
   * MCP 技能服务器（仅限仓库技能）。
   */
  mcp_tools?: {
    [key: string]: McpServerInput;
  } | null;
  /**
   * 元数据
   *
   * 技能的任意键值元数据。 AgentSkills 可扩展性的标准字段。
   */
  metadata?: {
    [key: string]: string;
  } | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 技能的资源目录（scripts/、references/、assets/）。 AgentSkills 标准字段。 仅针对 SKILL.md 目录格式进行填充。
   */
  resources?: SkillResources | null;
  /**
   * 来源
   *
   * 技能的源路径或标识符。 当它为 None 时，它被视为以编程方式定义的技能。
   */
  source?: string | null;
  /**
   * 触发
   *
   * 触发器决定何时自动注入技能内容。 None = 无自动注入（对于 AgentSkills：智能体按需读取； 对于遗留：完整内容始终在系统中提示词）。 KeywordTrigger = 当关键字出现在用户消息中时自动注入。 TaskTrigger = 针对特定任务自动注入，可能需要用户输入。
   */
  trigger?:
    | ({
        type: 'keyword';
      } & KeywordTrigger)
    | ({
        type: 'task';
      } & TaskTrigger)
    | ({
        type: 'path';
      } & PathTrigger)
    | null;
  /**
   * 版本
   *
   * 技能版本（AgentSkills标准字段）。
   */
  version?: string;
};

/**
 * 技能
 *
 * 技能提供专业知识或功能。
 *
 * 技能行为取决于格式（is_agentskills_format）和触发器：
 *
 * AgentSkills 格式（SKILL.md 个文件）：
 * - 始终在 <available_skills> 中列出，包含名称、描述、位置
 * - 智能体按需阅读完整内容（渐进式披露）
 * - 如果有触发器：触发时内容会自动注入 ALSO
 *
 * 旧版 OpenHands 格式：
 * - 带触发器：列在<available_skills>中，在触发器上注入内容
 * - 无触发器 (None)：<REPO_CONTEXT> 中的完整内容，始终处于活动状态
 *
 * 该模型支持 OpenHands 特定字段和 AgentSkills 标准
 * 用于跨平台兼容性的字段（ https://agentskills.io/specification ）。
 */
export type SkillOutput = {
  /**
   * 允许使用的工具
   *
   * 此技能的预先批准的工具列表。 AgentSkills 标准字段（从空格分隔的字符串解析）。
   */
  allowed_tools?: Array<string> | null;
  /**
   * 兼容性
   *
   * 该技能的环境要求或兼容性说明。 AgentSkills 标准字段（e.g., '需要 git 和 Docker'）。
   */
  compatibility?: string | null;
  /**
   * 内容
   */
  content: string;
  /**
   * 描述
   *
   * 简要描述该技能的作用以及何时使用它。 超过 MAX_DESCRIPTION_LENGTH 的描述将被截断，并带有指向技能源路径的通知。
   */
  description?: string | null;
  /**
   * 禁用模型调用
   *
   * 该技能是否只能通过触发匹配来激活，并且不应发布到模型以直接调用。
   */
  disable_model_invocation?: boolean;
  /**
   * 输入
   *
   * 输入技能的元数据（仅限任务技能）
   */
  inputs?: Array<InputMetadata>;
  /**
   * 是 Agentskills 格式
   *
   * 该技能是否是从遵循 AgentSkills 标准的 SKILL.md 文件加载的。 AgentSkills-格式技能使用渐进式披露：始终在 <available_skills> 中列出，并包含名称、描述和位置。 如果该技能也有触发器，则触发时会自动注入内容AND智能体可以随时读取文件。
   */
  is_agentskills_format?: boolean;
  /**
   * 许可证
   *
   * 分发技能所依据的许可证。 AgentSkills 标准字段（e.g.、“Apache-2.0”、“MIT”）。
   */
  license?: string | null;
  /**
   * MCP 工具
   *
   * MCP 技能服务器（仅限仓库技能）。
   */
  mcp_tools?: {
    [key: string]: {
      [key: string]: unknown;
    };
  } | null;
  /**
   * 元数据
   *
   * 技能的任意键值元数据。 AgentSkills 可扩展性的标准字段。
   */
  metadata?: {
    [key: string]: string;
  } | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 技能的资源目录（scripts/、references/、assets/）。 AgentSkills 标准字段。 仅针对 SKILL.md 目录格式进行填充。
   */
  resources?: SkillResources | null;
  /**
   * 来源
   *
   * 技能的源路径或标识符。 当它为 None 时，它被视为以编程方式定义的技能。
   */
  source?: string | null;
  /**
   * 触发
   *
   * 触发器决定何时自动注入技能内容。 None = 无自动注入（对于 AgentSkills：智能体按需读取； 对于遗留：完整内容始终在系统中提示词）。 KeywordTrigger = 当关键字出现在用户消息中时自动注入。 TaskTrigger = 针对特定任务自动注入，可能需要用户输入。
   */
  trigger?:
    | ({
        type: 'keyword';
      } & KeywordTrigger)
    | ({
        type: 'task';
      } & TaskTrigger)
    | ({
        type: 'path';
      } & PathTrigger)
    | null;
  /**
   * 版本
   *
   * 技能版本（AgentSkills标准字段）。
   */
  version?: string;
};

/**
 * SkillCatalogEntry
 *
 * 智能体 Profile launch 可加载的技能。
 */
export type SkillCatalogEntry = {
  /**
   * 内容
   */
  content: string;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 禁用模型调用
   */
  disable_model_invocation?: boolean;
  /**
   * 是 Agentskills 格式
   */
  is_agentskills_format?: boolean;
  /**
   * 名称
   */
  name: string;
  /**
   * 产地
   *
   * `public`：公共扩展目录。 `user`：用户自身的技能，包括市场安装。
   */
  origin: 'public' | 'user';
  /**
   * 来源
   */
  source?: string | null;
  /**
   * 触发器
   */
  triggers?: Array<string>;
  /**
   * 类型
   */
  type: 'repo' | 'knowledge' | 'agentskills';
};

/**
 * SkillCatalogResponse
 *
 * ``GET /api/skills/catalog`` 的响应。
 */
export type SkillCatalogResponse = {
  /**
   * 技能
   */
  skills: Array<SkillCatalogEntry>;
};

/**
 * SkillInfo
 *
 * 技能基本信息的轻量级表示。
 *
 * 此类为技能元数据提供标准化、可序列化的格式
 * 可以在系统的不同组件中使用。
 */
export type SkillInfo = {
  /**
   * 内容
   */
  content: string;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 禁用模型调用
   */
  disable_model_invocation?: boolean;
  /**
   * 是 Agentskills 格式
   */
  is_agentskills_format?: boolean;
  /**
   * 名称
   */
  name: string;
  /**
   * 来源
   */
  source?: string | null;
  /**
   * 触发器
   */
  triggers?: Array<string>;
  /**
   * 类型
   */
  type: 'repo' | 'knowledge' | 'agentskills';
};

/**
 * SkillResources
 *
 * 技能的资源目录（AgentSkills 标准）。
 *
 * 根据 AgentSkills 规范，技能可以包括：
 * - scripts/: 智能体可以运行的可执行脚本
 * -references/：参考文档和示例
 * - asset/：静态资产（图像、数据文件等）
 */
export type SkillResources = {
  /**
   * 资产
   *
   * asset/目录下的资源文件列表（相对路径）
   */
  assets?: Array<string>;
  /**
   * 参考文献
   *
   * References/ 目录中的参考文件列表（相对路径）
   */
  references?: Array<string>;
  /**
   * 脚本
   *
   * script/ 目录中的脚本文件列表（相对路径）
   */
  scripts?: Array<string>;
  /**
   * 技能根源
   *
   * 技能根目录（绝对路径）
   */
  skill_root: string;
};

/**
 * SkillsRequest
 *
 * 请求主体加载技能。
 */
export type SkillsRequest = {
  /**
   * 加载组织
   *
   * 加载组织级技能
   */
  load_org?: boolean;
  /**
   * 加载项目
   *
   * 从工作区加载项目技能
   */
  load_project?: boolean;
  /**
   * 加载公共
   *
   * 从 OpenHands/extensions 存储库加载公共技能
   */
  load_public?: boolean;
  /**
   * 加载用户
   *
   * 从 ~/.openhands/skills/ 加载用户技能
   */
  load_user?: boolean;
  /**
   * 市场路径
   *
   * 公共技能的相对市场 JSON 路径。 设置为null加载所有公共技能。
   */
  marketplace_path?: string | null;
  /**
   * 组织配置
   *
   * 同时加载的组织/用户技能存储库
   */
  org_configs?: Array<OrgConfig> | null;
  /**
   * 项目目录
   *
   * 工作区项目技能目录路径
   */
  project_dir?: string | null;
  /**
   * 注册市场
   *
   * 基于插件的技能加载的市场注册。 使用 auto_load=True 或插件名称列表注册将其技能添加到公共技能中。
   */
  registered_marketplaces?: Array<MarketplaceRegistration>;
  /**
   * 沙盒技能配置
   */
  sandbox_config?: SandboxConfig | null;
};

/**
 * SkillsResponse
 *
 * 包含所有可用技能的响应。
 */
export type SkillsResponse = {
  /**
   * 技能
   */
  skills: Array<SkillInfo>;
  /**
   * 来源
   *
   * 从每个来源加载的技能计数
   */
  sources?: {
    [key: string]: number;
  };
};

/**
 * StartChildConversationAction
 *
 * 在父级后端启动子级对话的操作。
 */
export type StartChildConversationAction = {
  /**
   * 隔离
   *
   * 当工作区是 git 存储库时，“工作树”为子级提供自己的 git 工作树和分支； “共享”在同一目录中运行它。
   */
  isolation?: 'worktree' | 'shared';
  /**
   * 种类
   */
  kind: 'StartChildConversationAction';
  /**
   * 任务
   *
   * 为孩子提供的独立简介：目标、相关文件或路径、约束条件以及预期的交付成果。 孩子无法看到此对话的历史记录。
   */
  task: string;
  /**
   * 标题
   *
   * 孩子对话的可选简短标题。
   */
  title?: string | null;
};

/**
 * StartChildConversationObservation
 *
 * 子对话启动的结果。
 */
export type StartChildConversationObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 对话 ID
   */
  conversation_id?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 隔离
   */
  isolation?: 'worktree' | 'shared' | null;
  /**
   * 种类
   */
  kind: 'StartChildConversationObservation';
  /**
   * 家长对话 ID
   */
  parent_conversation_id?: string | null;
  /**
   * 状态
   */
  status?: string | null;
  /**
   * 标题
   */
  title?: string | null;
  /**
   * 网址
   */
  url?: string | null;
  /**
   * 工作区
   */
  workspace?: string | null;
};

/**
 * StartChildConversationRequest
 *
 * 载荷在与其父级相同的后端启动子级对话。
 *
 * 由 ``start_child_conversation`` 工具发送到子启动端点：
 * 默认情况下智能体-服务器的 ``POST /api/conversations/{id}/children``，或者
 * 由托管父级的后端提供的等效启动器。
 */
export type StartChildConversationRequest = {
  /**
   * 隔离
   *
   * 工作区孩子的隔离。 当工作区是一个 git 存储库时，“工作树”在从父级工作区中提取的 git 工作树中运行它； “共享”在父目录中运行它。 自己管理工作区的后端可能会忽略这一点。
   */
  isolation?: 'worktree' | 'shared';
  /**
   * 任务
   *
   * 作为第一条用户消息传递给孩子的独立简介。
   */
  task: string;
  /**
   * 标题
   *
   * 子对话的可选标题。
   */
  title?: string | null;
};

/**
 * StartChildConversationResponse
 *
 * 子对话启动的结果，返回给父级智能体。
 */
export type StartChildConversationResponse = {
  /**
   * 对话 ID
   */
  conversation_id: string;
  /**
   * 隔离
   *
   * 工作区已知时实际应用的隔离。
   */
  isolation?: 'worktree' | 'shared' | null;
  /**
   * 家长对话 ID
   */
  parent_conversation_id: string;
  /**
   * 状态
   *
   * 后端报告的初始启动状态。
   */
  status: string;
  /**
   * 标题
   */
  title?: string | null;
  /**
   * 网址
   *
   * 当后端知道时，链接到子对话。
   */
  url?: string | null;
  /**
   * 工作区
   *
   * 孩子的工作目录，当已知时。
   */
  workspace?: string | null;
};

/**
 * StartChildConversationTool
 *
 * 启动同后端子对话的工具。
 */
export type StartChildConversationTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'StartChildConversationTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * StartConversationRequest
 *
 * 载荷创建一个新对话。
 *
 * 使用智能体源扩展：class:`ConversationConfig`：存储的智能体
 * 配置文件 (``agent_profile_id``)，已解决智能体设置
 * (``agent_settings``) 或 ``agent`` 内置代码。 的
 * 服务器在启动时将源转换为对话的智能体； 这个型号
 * 只检查是否给出了确切的一个来源。
 *
 * 注意：智能体根据 * 请求 * 存在于此处，故意不存在
 * ``ConversationConfig``. 已持久化记录 (``StoredConversation``) 确实
 * 不携带智能体 — 它的唯一事实来源是 ``ConversationState`` /
 * ``base_state.json``.
 */
export type StartConversationRequest = {
  agent?: AgentBaseInput;
  /**
   * 智能体定义
   *
   * 智能体来自客户端注册表的定义。 这些在服务器上注册，以便任务工具可以看到用户注册的子智能体。
   */
  agent_definitions?: Array<AgentDefinition>;
  /**
   * 在智能体或智能体配置文件解析后应用部署上下文。 存储的智能体配置文件未修改。
   */
  agent_launch_additions?: AgentLaunchAdditions | null;
  /**
   * 智能体个人资料 ID
   *
   * 已存储要启动的智能体配置文件。 服务器用自己的存储来解决它。 与其他智能体来源相互排斥。
   */
  agent_profile_id?: string | null;
  /**
   * 智能体设置
   *
   * 无参考智能体设置，使用 AgentSettingsBase `agent_kind` 鉴别器进行验证。 服务器在启动时根据它们构建智能体。 设置 `agent` 时忽略。
   */
  agent_settings?: {
    [key: string]: unknown;
  } | null;
  /**
   * 自动标题
   *
   * 如果是 True，则从第一条用户消息中自动生成对话标题。 优先级：title_llm_profile（如果设置并加载）→ agent.llm→消息截断。
   */
  autotitle?: boolean;
  /**
   * 客户端工具
   *
   * 客户端通过 JSON 规范定义的工具。 这些工具没有服务器端执行器 - 当智能体调用它们时，会通过 WebSocket 发出 ActionEvent，并且客户端处理执行。 SDK 立即返回确认信息观测结果。
   */
  client_tools?: Array<ClientToolSpecInput>;
  /**
   * 控制对话在继续之前何时将用户提示词。 默认为从不。
   */
  confirmation_policy?: ConfirmationPolicyBaseInput;
  /**
   * 对话容器的资源（Docker 运行时）。
   */
  container?: ConversationContainerOptions | null;
  /**
   * 对话 ID
   *
   * 可选的对话 ID。 如果未提供，将生成随机 UUID。
   */
  conversation_id?: string | null;
  /**
   * 对话运行时
   *
   * 执行此对话的运行时。 取消设置使用服务器配置的`conversation_runtime`； 仅当服务器在 `available_conversation_runtimes` 中列出另一个值时才接受它。
   */
  conversation_runtime?: 'local' | 'docker' | null;
  /**
   * 此对话的可选挂钩配置。 挂钩是在关键生命周期事件（PreToolUse、PostToolUse、UserPromptSubmit、Stop 等）处运行的 shell 脚本。 如果同时提供了 hook_config 和插件，它们将与在插件挂钩之前运行的显式挂钩合并。
   */
  hook_config?: HookConfig | null;
  /**
   * 要传递到 LLM 的初始消息
   */
  initial_message?: SendMessageRequest | null;
  /**
   * 最大迭代次数
   *
   * 如果设置，则智能体在停止之前将运行的最大迭代次数。 这对于防止无限循环很有用。
   */
  max_iterations?: number;
  /**
   * 可观测性元数据
   *
   * 附加到可观察性后端的跟踪级元数据。 值必须是 OpenTelemetry 支持的标量或齐次标量列表。
   */
  observability_metadata?: {
    [key: string]: TraceMetadataValue;
  };
  /**
   * 可观测性父跨度上下文
   *
   * 已序列化父范围上下文用于将此对话附加到上游自动化或集成跟踪。
   */
  observability_parent_span_context?: string | null;
  /**
   * 可观测性跨度名称
   *
   * 在对话根下发出的可选命名子范围。 使用稳定的、低基数的名称，因为可观察性后端可能使用跨度名称进行分组或信号路由。
   */
  observability_span_name?: string;
  /**
   * 可观察性标签
   *
   * 附加到对话根可观察性范围的标签。
   */
  observability_tags?: Array<string>;
  /**
   * 家长对话 ID
   *
   * 拥有此对话的现有对话的可选 ID。 父级必须已经存在并共享此对话的工作区。
   */
  parent_conversation_id?: string | null;
  /**
   * 插件
   *
   * 为此对话加载的插件列表。 插件已加载，其技能/MCP 配置已合并到智能体中。 钩子被提取并存储以供运行时执行。
   */
  plugins?: Array<PluginSource> | null;
  /**
   * 提示词
   *
   * 可选提示词，替换默认的标题生成用户消息。 使用 {conversation_content} 放置第一条用户消息，使用 {max_length} 放置标题长度限制。 如果省略对话占位符，则会自动附加消息。 空或未设置的值使用默认值提示词。
   */
  prompt?: string | null;
  /**
   * 机密
   *
   * 机密在对话中可用
   */
  secrets?: {
    [key: string]: SecretSourceInput;
  };
  /**
   * 机密加密
   *
   * 如果 True, indicates that 机密在智能体配置信息是通过加密的，应由服务器解密后使用。 这允许通过不可信客户端进行设置的加密往返e.g., 前端) 接收加密值的端点机密 header. 流程：客户端调用 GET  /api/settings 带有 X-Expose-机密加密以接收加密的密文机密然后将它们传递给智能体配置文件 secrets_encrypted=True 因此服务器可以解密它们。
   */
  secrets_encrypted?: boolean;
  /**
   * 可选的安全分析器来评估操作风险。
   */
  security_analyzer?: SecurityAnalyzerBaseInput | null;
  /**
   * 卡住检测
   *
   * 如果为 True，对话将使用卡住检测来防止无限循环。
   */
  stuck_detection?: boolean;
  /**
   * 标签
   *
   * 对话的键值标签。 键必须是小写字母数字。 值是最多 256 个字符的任意字符串。
   */
  tags?: {
    [key: string]: string;
  };
  /**
   * 标题法学硕士简介
   *
   * 用于标题生成的可选 LLM 配置文件名称。 LLM 若设置，则从 LLMProfileStore 加载 (~/.openhands/profiles/) 用于 LLM-基于标题生成)。 这使得无论智能体的主要模型如何，都可以使用快速/廉价的模型来生成标题。 如果没有设置（或配置加载失败），标题生成将回退到智能体的LLM。
   */
  title_llm_profile?: string | null;
  /**
   * 工具模块 Qualnames
   *
   * 将工具名称映射到客户端的注册表的模块限定名。 这些模块将动态导入到服务器上以注册用于此对话的工具。
   */
  tool_module_qualnames?: {
    [key: string]: string;
  };
  /**
   * 用户 ID
   *
   * 托管部署提供的可选用户 ID，用于将此对话与部署已建立的身份相关联。 当设置时，它被传递到 Laminar.set_trace_user_id() 这样可以由用户查询日志， 当主机启用了产品分析时，它会被重用为分析关联标识，从而事件与现有的人相关联而不是创建一个重复的身份。 它从未由生成 SDK，且当未设置时完全省略。
   */
  user_id?: string | null;
  /**
   * 工作目录用于智能体操作和工具执行。
   */
  workspace: LocalWorkspaceInput;
  /**
   * 工作树
   *
   * 如果 True 和工作区已位于 git 存储库内，请在 `/tmp/conversation-worktrees/<conversation_id>/<project_name>` 下为此对话创建专用的 git 工作树。
   */
  worktree?: boolean;
  /**
   * 工作树是如何创建的 (`worktree=True`)； 未设置：默认值。
   */
  worktree_options?: ConversationWorktreeOptions | null;
};

/**
 * StartGoalRequest
 *
 * 载荷在对话中启动 ``/goal`` 循环。
 */
export type StartGoalRequest = {
  /**
   * 最大迭代次数
   *
   * 放弃之前的最大审核轮次。
   */
  max_iterations?: number;
  /**
   * 目的
   *
   * 目标目标追求和审核。
   */
  objective: string;
};

/**
 * StaticSecret
 *
 * A 机密存储在本地
 */
export type StaticSecretInput = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 种类
   */
  kind?: 'StaticSecret';
  /**
   * 价值
   */
  value?: null;
};

/**
 * StaticSecret
 *
 * A 机密存储在本地
 */
export type StaticSecretOutput = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 种类
   */
  kind: 'StaticSecret';
  /**
   * 价值
   */
  value?: null;
};

/**
 * StdioMCPServer
 *
 * 传统 stdio MCP 服务器规范已被公众接受 REST API。
 */
export type StdioMcpServer = {
  /**
   * 参数
   */
  args?: Array<string>;
  /**
   * 命令
   *
   * 执行调用的可执行文件
   */
  command: string;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 环境
   */
  env?: {
    [key: string]: string;
  };
  /**
   * 类型
   */
  type?: 'stdio';
};

/**
 * StreamingDeltaEvent
 *
 * 实时 WebSocket 传送的瞬态 LLM token 增量。
 *
 * 对话事件日志中没有已持久化：这些事件已发布
 * 直接写入 PubSub，绕过写入的回调链
 * ConversationState.events. 中途重新连接的客户端将收到
 * 历史上最后的MessageEvent，但产生的三角洲的None
 * 它——增量是一种用户体验可供性，而不是持久对话的一部分
 * 记录。
 */
export type StreamingDeltaEvent = {
  /**
   * 内容
   */
  content?: string | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'StreamingDeltaEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 推理内容
   */
  reasoning_content?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * SubAgentInfo
 *
 * API 返回的 ``AgentDefinition`` 的无损视图。
 *
 * 每个前置元数据字段加上发现的 ``level``/``source``，一个
 * ``is_builtin`` 标志，以及内联 ``system_prompt``（Markdown 主体），因此
 * 详细视图不需要额外的获取。
 */
export type SubAgentInfo = {
  /**
   * 颜色
   */
  color?: string | null;
  condenser?: CondenserBaseOutput | null;
  /**
   * 描述
   */
  description?: string;
  hooks?: HookConfig | null;
  /**
   * 是内置的
   */
  is_builtin?: boolean;
  /**
   * 级别
   */
  level?: 'project' | 'user' | 'builtin' | 'plugin' | 'programmatic' | null;
  /**
   * 每次运行的最大预算
   */
  max_budget_per_run?: number | null;
  /**
   * 每次运行的最大迭代次数
   */
  max_iteration_per_run?: number | null;
  /**
   * MCP 配置
   *
   * MCP 服务器定义声明。 委托的子智能体忽略它们并继承其父级的 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  } | null;
  /**
   * MCP 服务器
   *
   * 已弃用 mcp_config 的兼容性别名。 对于新客户，请使用 mcp_config。
   *
   * @已弃用
   */
  mcp_servers?: {
    [key: string]: McpServerOutput;
  } | null;
  /**
   * 元数据
   */
  metadata?: {
    [key: string]: unknown;
  };
  /**
   * 型号
   */
  model?: string;
  /**
   * 名称
   */
  name: string;
  /**
   * 权限模式
   */
  permission_mode?: string | null;
  /**
   * 配置文件存储目录
   */
  profile_store_dir?: string | null;
  /**
   * 技能
   */
  skills?: Array<string>;
  /**
   * 来源
   */
  source?: string | null;
  /**
   * 系统提示词
   */
  system_prompt?: string;
  /**
   * 工具
   */
  tools?: Array<string>;
  /**
   * 何时使用示例
   */
  when_to_use_examples?: Array<string>;
};

/**
 * SubAgentsRequest
 *
 * 请求正文列出子智能体。
 */
export type SubAgentsRequest = {
  /**
   * 负载内置
   *
   * 加载 SDK 内置智能体（通用、代码浏览器、...）
   */
  load_builtin?: boolean;
  /**
   * 加载项目
   *
   * 从工作区加载项目智能体
   */
  load_project?: boolean;
  /**
   * 加载用户
   *
   * 从 ~/.agents/agents 和 ~/.openhands/agents 加载用户智能体
   */
  load_user?: boolean;
  /**
   * 项目目录
   *
   * 工作区项目智能体的目录路径
   */
  project_dir?: string | null;
};

/**
 * SubAgentsResponse
 *
 * 响应包含所有可用的子智能体。
 */
export type SubAgentsResponse = {
  /**
   * 智能体
   */
  agents: Array<SubAgentInfo>;
};

/**
 * SubdirectoryEntry
 */
export type SubdirectoryEntry = {
  /**
   * 名称
   */
  name: string;
  /**
   * 路径
   */
  path: string;
};

/**
 * SubdirectoryPage
 */
export type SubdirectoryPage = {
  /**
   * 项目
   */
  items: Array<SubdirectoryEntry>;
  /**
   * 下一页 ID
   */
  next_page_id?: string | null;
};

/**
 * SubscriptionDevicePollRequest
 *
 * 对先前启动的订阅设备登录的轮询请求。
 */
export type SubscriptionDevicePollRequest = {
  /**
   * 设备代码
   */
  device_code: string;
};

/**
 * SubscriptionDeviceStartResponse
 *
 * 浏览器登录的设备代码质询详细信息。
 */
export type SubscriptionDeviceStartResponse = {
  /**
   * 设备代码
   *
   * 不透明的服务器端轮询token。
   */
  device_code: string;
  /**
   * 到期时间
   */
  expires_at: number;
  /**
   * 间隔秒数
   */
  interval_seconds: number;
  /**
   * 用户代码
   */
  user_code: string;
  /**
   * 验证Uri
   */
  verification_uri: string;
  /**
   * 验证 URI 完成
   */
  verification_uri_complete?: string | null;
};

/**
 * SubscriptionModelsResponse
 *
 * 通过订阅提供商提供的模型。
 */
export type SubscriptionModelsResponse = {
  /**
   * 型号
   */
  models: Array<string>;
  /**
   * 供应商
   */
  vendor?: string;
};

/**
 * SubscriptionStatusResponse
 *
 * 安全订阅身份验证状态。
 */
export type SubscriptionStatusResponse = {
  /**
   * 账户邮箱
   */
  account_email?: string | null;
  /**
   * 已连接
   */
  connected: boolean;
  /**
   * 到期时间
   */
  expires_at?: number | null;
  /**
   * 供应商
   */
  vendor?: string;
};

/**
 * 成功
 */
export type Success = {
  /**
   * 成功
   */
  success?: boolean;
};

/**
 * SwitchLLMAction
 *
 * 用于将此对话切换到已保存的 LLM 配置文件的操作。
 */
export type SwitchLlmAction = {
  /**
   * 种类
   */
  kind: 'SwitchLLMAction';
  /**
   * 个人资料名称
   *
   * 已保存的 LLM 配置文件的名称，用于将来的智能体步骤。
   */
  profile_name: string;
  /**
   * 原因
   *
   * 此配置文件更适合下一步的简要原因。
   */
  reason: string;
};

/**
 * SwitchLLMObservation
 *
 * 切换此对话的 LLM 个人资料后返回观测结果。
 */
export type SwitchLlmObservation = {
  /**
   * 主动模型
   *
   * 由激活的配置文件配置的模型（如果可用）。
   */
  active_model?: string | null;
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'SwitchLLMObservation';
  /**
   * 个人资料名称
   *
   * 该工具尝试激活的配置文件的名称。
   */
  profile_name: string;
  /**
   * 原因
   *
   * 智能体给出的尝试此 LLM 配置文件切换的原因。
   */
  reason?: string | null;
};

/**
 * SwitchLLMTool
 *
 * 用于将对话切换到已保存的 LLM 配置文件的工具。
 */
export type SwitchLlmTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'SwitchLLMTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * SyncResponse
 *
 * 技能同步操作的响应。
 */
export type SyncResponse = {
  /**
   * 留言
   */
  message: string;
  /**
   * 状态
   */
  status: 'success' | 'error';
};

/**
 * SystemPromptEvent
 *
 * 系统提示词由智能体添加。
 *
 * 系统提示词可以选择包括动态上下文，其变化范围为
 * 对话。 当提供 ``dynamic_context`` 时，它被包含为
 * 同一系统消息中的第二个内容块。 缓存标记为不
 * 此处应用 - 它们由 ``LLM._apply_prompt_caching()`` 应用，当
 * 启用缓存，确保仅添加特定于提供者的缓存控制
 * 在适当的时候。
 *
 * 属性：
 * system_prompt：静态系统提示词文本（可跨对话缓存）
 * 工具：列出可用工具的列表
 * dynamic_context：可选的每个会话上下文（主机、存储库信息等）
 * 作为系统消息内的第二个 TextContent 块发送。
 */
export type SystemPromptEvent = {
  /**
   * 可选的动态每次对话上下文（运行时信息、存储库上下文、机密）。 提供后，它将作为第二个内容块包含在系统消息中（未缓存）。
   */
  dynamic_context?: TextContent | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'SystemPromptEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 系统提示词文本
   */
  system_prompt: TextContent;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具
   *
   * 作为 ToolDefinition 对象的工具列表
   */
  tools: Array<ToolDefinition>;
};

/**
 * TaskAction
 *
 * 模式用于启动子智能体任务。
 */
export type TaskAction = {
  /**
   * 描述
   *
   * 任务的简短（3-5 个词）描述。
   */
  description?: string | null;
  /**
   * 种类
   */
  kind: 'TaskAction';
  /**
   * 提示词
   *
   * 智能体要执行的任务。
   */
  prompt: string;
  /**
   * 简历
   *
   * 要从中恢复的任务的任务 ID。
   */
  resume?: string | null;
  /**
   * 子智能体类型
   *
   * 用于此任务的专用智能体的类型。
   */
  subagent_type?: string;
};

/**
 * TaskItem
 */
export type TaskItem = {
  /**
   * 注释
   *
   * 有关任务的其他详细信息或注释。
   */
  notes?: string;
  /**
   * 状态
   *
   * 任务的当前状态。 “todo”、“in_progress”或“done”之一。
   */
  status?: 'todo' | 'in_progress' | 'done';
  /**
   * 标题
   *
   * 任务的简短标题。
   */
  title: string;
};

/**
 * TaskObservation
 *
 * 观测结果来自任务执行。
 */
export type TaskObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'TaskObservation';
  /**
   * 状态
   *
   * 任务的状态。
   */
  status: string;
  /**
   * 子智能体
   *
   * 任务的子智能体。
   */
  subagent: string;
  /**
   * 任务编号
   *
   * 任务的唯一标识符。
   */
  task_id: string;
};

/**
 * TaskTool
 *
 * 用于启动（阻止）子智能体任务的工具。
 */
export type TaskTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * TaskToolSet
 *
 * 任务工具集。
 *
 * 创建由共享 TaskManager 支持的任务工具。
 *
 * 用途：
 * 从 openhands.tools.task 导入 TaskToolSet
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=[
 * Tool(name=TerminalTool.name),
 * Tool(name=FileEditorTool.name),
 * Tool(name=TaskToolSet.name),
 * ],
 * )
 */
export type TaskToolSet = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * TaskTrackerAction
 *
 * 智能体写入或更新任务列表以进行任务管理的操作。
 */
export type TaskTrackerAction = {
  /**
   * 命令
   *
   * 要执行的命令。 `view`显示当前任务列表。 `plan` 根据提供的要求和进度创建或更新任务列表。 在进行更改之前始终 `view` 当前列表。
   */
  command?: 'view' | 'plan';
  /**
   * 种类
   */
  kind: 'TaskTrackerAction';
  /**
   * 任务清单
   *
   * 完整的任务列表。 `plan`命令的必需参数。
   */
  task_list?: Array<TaskItem>;
};

/**
 * TaskTrackerObservation
 *
 * 该数据类表示任务跟踪操作的结果。
 */
export type TaskTrackerObservation = {
  /**
   * 命令
   *
   * 执行的命令：“查看”或“计划”。
   */
  command: 'view' | 'plan';
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'TaskTrackerObservation';
  /**
   * 任务清单
   *
   * 当前任务列表
   */
  task_list?: Array<TaskItem>;
};

/**
 * TaskTrackerTool
 *
 * 自动初始化 TaskTrackerExecutor 的 ToolDefinition 子类。
 */
export type TaskTrackerTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskTrackerTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * TaskTrigger
 *
 * 触发特定任务技能。
 *
 * 这些技能针对特定任务类型而激活，并且可以修改提示词。
 */
export type TaskTrigger = {
  /**
   * 触发器
   */
  triggers: Array<string>;
  /**
   * 类型
   */
  type?: 'task';
};

/**
 * TelemetrySpec
 *
 * 部署提供的产品分析传输层设置。
 *
 * 它带有传输层加上非识别部署标签。 是否
 * 可以提供遥测数据已征得同意
 * (``misc_settings.telemetry.consent``, 可选择播种或覆盖
 * ``OH_TELEMETRY_CONSENT``).
 */
export type TelemetrySpec = {
  /**
   * 部署类型
   *
   * 附加到诊断事件的部署类型。 对于托管 OpenHands 使用“远程”，对于自托管或开发人员运行使用“本地”。
   */
  deployment_kind?: 'local' | 'remote';
  /**
   * 事件缓冲区大小
   *
   * 每个交付批次的最大事件数。
   */
  event_buffer_size?: number;
  /**
   * 出口商
   *
   * 出口商使用。 None（默认值）从不发送，这是库和无头消费者所获得的。 'posthog' 需要额外的 [posthog]。 HTTP POSTs 清洗了 telemetry_http_endpoint 批次。
   */
  exporter?: 'none' | 'posthog' | 'http';
  /**
   * 冲洗延迟
   *
   * 刷新部分批次之前等待的秒数。
   */
  flush_delay?: number;
  /**
   * HTTP 端点
   *
   * 端点 "HTTP" 导出器 POSTs 会清理事件批次。 旨在前端后端在转发之前重新验证身份验证和同意。
   */
  http_endpoint?: string | null;
  /**
   * HTTP token
   *
   * 持有者令牌由“HTTP”出口商发送（如果需要）。
   */
  http_token?: null;
  /**
   * 最大队列大小
   *
   * 缓冲诊断事件的上限。 队列在摄取时受到限制：超过这么多事件，最旧的事件将被丢弃，因此失败的导出器无法无限制地增加内存。
   */
  max_queue_size?: number;
  /**
   * 数量重试
   *
   * 重试在批次被删除之前。
   */
  num_retries?: number;
  /**
   * Posthog API 钥匙
   *
   * PostHog项目API关键。 “posthog”出口商要求； 如果没有它，遥测将保持不活动状态。
   */
  posthog_api_key?: null;
  /**
   * 邮差主机
   *
   * PostHog摄取主机。
   */
  posthog_host?: string;
  /**
   * 重试延迟
   *
   * 传送之间的基本秒数重试。
   */
  retry_delay?: number;
  /**
   * 盐
   *
   * 用于对对话标识符进行假名化的密钥。 fallback to the server's 机密 key (OH_SECRET_KEY, which defaults to the first session API key)，因此匿名者保持稳定且可链接，直到该键发生变化。 仅当没有机密密钥时，每个进程才会生成随机密钥，这使得假名在运行中不可链接。
   */
  salt?: null;
};

/**
 * TerminalAction
 *
 * 模式用于终端命令执行。
 */
export type TerminalAction = {
  /**
   * 命令
   *
   * 要执行的 shell 命令。 当上一个退出代码为 `-1` 时，可以为空字符串以查看其他日志。 当 `is_input` 为 True 时，可以是特殊键名称：`C-c` (Ctrl+C)、`C-d` (Ctrl+D/EOF)、`C-z` (Ctrl+Z) 或任何用于 Ctrl 序列的 `C-<letter>`； 导航键 `UP`、`DOWN`、`LEFT`、`RIGHT`、`HOME`、`END`、`PGUP`、`PGDN`； 和 `TAB`、`ESC`、`BS`（退格键）、`ENTER`。 您一次只能执行一个命令。 链接命令时，请使用工具说明中描述的适合平台的 shell 语法。
   */
  command: string;
  /**
   * 是输入
   *
   * 如果为 True，则该命令是正在运行的进程的输入。 如果为 False，则该命令在终端会话中执行。 默认值为 False。
   */
  is_input?: boolean;
  /**
   * 种类
   */
  kind: 'TerminalAction';
  /**
   * 重置
   *
   * 如果 True，则通过创建新会话来重置终端。 仅当终端无响应时才使用此选项。 请注意，重置后所有先前设置的环境变量和会话状态都将丢失。 不能与 is_input=True 一起使用。
   */
  reset?: boolean;
  /**
   * 超时
   *
   * 可选。 设置运行命令的最大时间限制（以秒为单位）。 如果该命令花费的时间超过此限制，系统会询问您是继续还是停止它。 如果您未设置值，则该命令将在 30 秒内没有产生新输出时暂停并要求确认。 如果命令预计耗时较长（如安装或测试），或者有已知固定持续时间（如睡眠），则使用较高值。
   */
  timeout?: number | null;
};

/**
 * TerminalObservation
 *
 * 可以呈现为 CLI 输出的 ToolResult。
 */
export type TerminalObservation = {
  /**
   * 命令
   *
   * 执行的 shell 命令。 如果观测结果来自先前点击软超时的命令并且尚未完成，则可以为空字符串。
   */
  command: string | null;
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 退出代码
   *
   * 命令的退出代码。 -1 表示进程到达软超时并且尚未完成。
   */
  exit_code?: number | null;
  /**
   * 完整输出保存目录
   *
   * 保存完整输出文件的目录
   */
  full_output_save_dir?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'TerminalObservation';
  /**
   * 命令执行后从 PS1 捕获的其他元数据。
   */
  metadata?: CmdOutputMetadata;
  /**
   * 超时
   *
   * 命令执行是否超时。
   */
  timeout?: boolean;
};

/**
 * TerminalTool
 *
 * 通过自动检测自动初始化 TerminalExecutor 的 ToolDefinition 子类。
 */
export type TerminalTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TerminalTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * TextContent
 */
export type TextContent = {
  /**
   * 缓存提示词
   */
  cache_prompt?: boolean;
  /**
   * 文字
   */
  text: string;
  /**
   * 类型
   */
  type?: 'text';
};

/**
 * ThinkAction
 *
 * 用于记录想法而不进行任何更改的操作。
 */
export type ThinkAction = {
  /**
   * 种类
   */
  kind: 'ThinkAction';
  /**
   * 思想
   *
   * 记录的想法。
   */
  thought: string;
};

/**
 * ThinkObservation
 *
 * 观测结果记录想法后返回。
 * ThinkAction 本身包含记录的想法，因此没有额外的内容
 * 这里需要字段。
 */
export type ThinkObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'ThinkObservation';
};

/**
 * ThinkTool
 *
 * 用于记录想法而不进行更改的工具。
 */
export type ThinkTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ThinkTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * ThinkingBlock
 *
 * Anthropic 思维块用于扩展思维功能。
 *
 * 这代表 Anthropic 模型返回的原始思维块
 * 当扩展思维被启用时。 必须保留这些块
 * 并传回API以获取工具使用场景。
 */
export type ThinkingBlock = {
  /**
   * 签名
   *
   * 思维块的加密签名
   */
  signature?: string | null;
  /**
   * 思考
   *
   * 思考内容
   */
  thinking: string;
  /**
   * 类型
   */
  type?: 'thinking';
};

/**
 * TokenEvent
 *
 * 来自 VLLM 的事件代表 LLM 交互中使用的 token 个 ID。
 */
export type TokenEvent = {
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'TokenEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 提示词 token ID
   *
   * 此消息事件的确切提示词 token ID
   */
  prompt_token_ids: Array<number>;
  /**
   * 响应 token ID
   *
   * 此消息事件的确切响应 token ID
   */
  response_token_ids: Array<number>;
  /**
   * 来源
   */
  source: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
};

/**
 * TokenUsage
 *
 * 每次完成调用的指标跟踪详细信息词元用量。
 */
export type TokenUsage = {
  /**
   * 缓存读取 token
   *
   * 缓存读取 token 必须为非负数
   */
  cache_read_tokens?: number;
  /**
   * 缓存写入 token
   *
   * 缓存写入token必须是非负数
   */
  cache_write_tokens?: number;
  /**
   * 已完成 token
   *
   * 补全 token 必须是非负数
   */
  completion_tokens?: number;
  /**
   * 上下文窗口
   *
   * 上下文窗口必须是非负数
   */
  context_window?: number;
  /**
   * 型号
   */
  model?: string;
  /**
   * 每回合 token
   *
   * 每转 token 必须为非负数
   */
  per_turn_token?: number;
  /**
   * 提示词 token
   *
   * 提示词 token 必须为非负数
   */
  prompt_tokens?: number;
  /**
   * 推理 token
   *
   * 推理 token 必须是非负的
   */
  reasoning_tokens?: number;
  /**
   * 响应 ID
   */
  response_id?: string;
};

/**
 * 工具
 *
 * 定义要为智能体初始化的工具。
 *
 * 这仅在智能体-SDK 中用于服务器使用的类型模式。
 */
export type ToolInput = {
  /**
   * 名称
   *
   * 工具类的名称，e.g.，“TerminalTool”。 从 `openhands.tools.<module>` 子包导入它。
   */
  name: string;
  /**
   * 参数
   *
   * 该工具的 .create() 方法的参数，e.g., {'working_dir': '/app'}
   */
  params?: {
    [key: string]: unknown;
  };
};

/**
 * openhands.sdk.tool.tool.ToolAnnotations
 *
 * 提供有关工具行为的提示的注释。
 *
 * 根据模型上下文协议(MCP)说明：
 * https://github.com/modelcontextprotocol/modelcontextprotocol/blob/caf3424488b10b4a7b1f8cb634244a450a1f4400/schema/2025-06-18/schema.ts#L838
 */
export type ToolAnnotationsInput = {
  /**
   * 破坏性暗示
   *
   * 如果 True，该工具可能对其环境执行破坏性更新。 如果是 False，则该工具仅执行附加更新。 （该属性仅当`readOnlyHint == false`时才有意义）默认：True
   */
  destructiveHint?: boolean;
  /**
   * 幂等性
   *
   * True 如果重复使用相同的参数调用工具，对它的环境将没有任何额外影响。（只有在`readOnlyHint == false`时才有意义）默认：False
   */
  idempotentHint?: boolean;
  /**
   * 开放世界提示
   *
   * 如果 True，则该工具可以与外部实体的“开放世界”进行交互。 如果是False，则该工具的交互域是封闭的。 例如，网络搜索工具的世界是开放的，而记忆工具的世界则不是。 默认值：True
   */
  openWorldHint?: boolean;
  /**
   * 只读提示
   *
   * 如果为 True，则该工具不会修改其环境。 默认值：False
   */
  readOnlyHint?: boolean;
  /**
   * 标题
   *
   * 该工具的人类可读标题。
   */
  title?: string | null;
};

/**
 * ToolCatalogEntry
 *
 * 为配置智能体的客户端提供的注册工具。
 */
export type ToolCatalogEntry = {
  /**
   * 描述
   */
  description?: string;
  /**
   * 在默认设置中
   */
  in_default_set?: boolean;
  /**
   * 名称
   */
  name: string;
  /**
   * 可用
   */
  usable?: boolean;
  /**
   * 用户可选择
   */
  user_selectable?: boolean;
};

/**
 * ToolCatalogResponse
 */
export type ToolCatalogResponse = {
  /**
   * 工具
   */
  tools: Array<ToolCatalogEntry>;
};

export type ToolDefinition =
  | ({
      kind: 'openhands__sdk__mcp__tool__MCPToolDefinition-Output__1';
    } & McpToolDefinition)
  | ({
      kind: 'openhands__sdk__tool__builtins__classify_and_switch_llm__ClassifyAndSwitchLLMTool-Output__1';
    } & ClassifyAndSwitchLlmTool)
  | ({
      kind: 'openhands__sdk__tool__builtins__finish__FinishTool-Output__1';
    } & FinishTool)
  | ({
      kind: 'openhands__sdk__tool__builtins__invoke_skill__InvokeSkillTool-Output__1';
    } & InvokeSkillTool)
  | ({
      kind: 'openhands__sdk__tool__builtins__switch_llm__SwitchLLMTool-Output__1';
    } & SwitchLlmTool)
  | ({
      kind: 'openhands__sdk__tool__builtins__think__ThinkTool-Output__1';
    } & ThinkTool)
  | ({
      kind: 'openhands__sdk__tool__builtins__vision_inspect__VisionInspectTool-Output__1';
    } & VisionInspectTool)
  | ({
      kind: 'openhands__sdk__tool__client_tool__ClientTool-Output__1';
    } & ClientTool)
  | ({
      kind: 'openhands__tools__ask_oracle__definition__AskOracleTool-Output__1';
    } & AskOracleTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserClickTool-Output__1';
    } & BrowserClickTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserCloseTabTool-Output__1';
    } & BrowserCloseTabTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetContentTool-Output__1';
    } & BrowserGetContentTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStateTool-Output__1';
    } & BrowserGetStateTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStorageTool-Output__1';
    } & BrowserGetStorageTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGoBackTool-Output__1';
    } & BrowserGoBackTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserListTabsTool-Output__1';
    } & BrowserListTabsTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserNavigateTool-Output__1';
    } & BrowserNavigateTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserScrollTool-Output__1';
    } & BrowserScrollTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSetStorageTool-Output__1';
    } & BrowserSetStorageTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStartRecordingTool-Output__1';
    } & BrowserStartRecordingTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStopRecordingTool-Output__1';
    } & BrowserStopRecordingTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSwitchTabTool-Output__1';
    } & BrowserSwitchTabTool)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserToolSet-Output__1';
    } & BrowserToolSet)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserTypeTool-Output__1';
    } & BrowserTypeTool)
  | ({
      kind: 'openhands__tools__child_conversation__definition__StartChildConversationTool-Output__1';
    } & StartChildConversationTool)
  | ({
      kind: 'openhands__tools__file_editor__definition__FileEditorTool-Output__1';
    } & FileEditorTool)
  | ({
      kind: 'openhands__tools__gemini__edit__definition__EditTool-Output__1';
    } & EditTool)
  | ({
      kind: 'openhands__tools__gemini__list_directory__definition__ListDirectoryTool-Output__1';
    } & ListDirectoryTool)
  | ({
      kind: 'openhands__tools__gemini__read_file__definition__ReadFileTool-Output__1';
    } & ReadFileTool)
  | ({
      kind: 'openhands__tools__gemini__write_file__definition__WriteFileTool-Output__1';
    } & WriteFileTool)
  | ({
      kind: 'openhands__tools__glob__definition__GlobTool-Output__1';
    } & GlobTool)
  | ({
      kind: 'openhands__tools__grep__definition__GrepTool-Output__1';
    } & GrepTool)
  | ({
      kind: 'openhands__tools__planning_file_editor__definition__PlanningFileEditorTool-Output__1';
    } & PlanningFileEditorTool)
  | ({
      kind: 'openhands__tools__task__definition__TaskTool-Output__1';
    } & TaskTool)
  | ({
      kind: 'openhands__tools__task__definition__TaskToolSet-Output__1';
    } & TaskToolSet)
  | ({
      kind: 'openhands__tools__task_tracker__definition__TaskTrackerTool-Output__1';
    } & TaskTrackerTool)
  | ({
      kind: 'openhands__tools__terminal__definition__TerminalTool-Output__1';
    } & TerminalTool)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowTool-Output__1';
    } & WorkflowTool)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowToolSet-Output__1';
    } & WorkflowToolSet);

/**
 * ToolExecution
 *
 * 工具的与执行相关的属性。
 */
export type ToolExecution = {
  /**
   * 任务支持
   */
  taskSupport?: 'forbidden' | 'optional' | 'required' | null;
  [key: string]: unknown;
};

/**
 * ToolShieldLLMSecurityAnalyzer
 *
 * 通过单独的约束检查 LLM 评估每个操作。
 *
 * 与现有的``ConfirmRisky``政策不变：这
 * 分析器仅 * 分配 * 风险级别； ``ConfirmRisky`` 决定
 * 是否暂停以供用户确认。
 *
 * 默认情况下，分析器作为裸机约束检查运行（没有蒸馏
 * safety experiences). 要启用 ToolShield 种子，请安装
 * ``pip install openhands-sdk[toolshield]`` 并传递渲染的
 * 通过 ``safety_experiences`` 字段获得的经验——通常通过
 * 助手之一 (``default_safety_experiences()``,
 * ``load_safety_experiences(...)``, ``auto_detect_safety_experiences()``).
 * 针对 ``toolshield>=0.1.3,<0.2`` 进行测试。
 *
 * 注：``reasoning_content``和``thinking_blocks``来自扩展-
 * 思维模型被故意排除在约束检查之外
 * 上下文。 风险信号存在于工具调用的名字中，并且
 * 论据； 包括推理文本会使提示词膨胀
 * 无比例安全增益。 需要推理的子类
 * 可见性应覆盖：func:`_format_action_for_guardrail`。
 *
 * 生命周期：实例维护最近的每个会话双端队列
 * 约束检查上下文的操作（``history_window`` 项）。 每个
 * 实例供 SINGLE-CONVERSATION 使用。 重复使用一个
 * 跨多个对话的分析器实例将泄漏操作
 * 他们之间的历史，这都是隐私问题（对话
 * A 的工具参数在对话 B 中可见约束检查提示词)
 * 以及正确性问题（约束检查评估对话 B 的
 * 针对无关历史的行动）。 每构建一个分析器
 * 对话，或在对话中致电：meth:`reset_history`
 * 边界。
 *
 * 最近的操作上下文在分析器之间的传播（这个，
 * :class:`LLMSecurityAnalyzer`, :class:`GraySwanAnalyzer`) 被跟踪
 * 为了在单独的后续行动中收敛； 直到着陆，
 * 单一对话的生命周期就是契约。
 *
 * 故障模式是一致的并且是整体安全的——两者都是
 * 基础设施错误（网络、速率限制）和解析失败
 * （约束检查响应，但其输出没有可解析的
 * ``RISK:`` 标签）返回 ``SecurityRisk.UNKNOWN``。 ``ConfirmRisky``
 * 用 ``confirm_unknown=True`` 然后暂停以供用户确认，
 * 匹配保守的姿态而不占主导地位``max()``
 * 整体融合。
 */
export type ToolShieldLlmSecurityAnalyzerInput = {
  /**
   * 历史窗口
   *
   * 要包含为上下文的先前操作的数量。
   */
  history_window?: number;
  /**
   * 种类
   */
  kind?: 'ToolShieldLLMSecurityAnalyzer';
  /**
   * LLM用作约束检查。 可以是比演员更小/更便宜的模型LLM； 只有模型对行动风险进行分类的能力才是重要的。
   */
  llm: LlmInput;
  /**
   * Safety Experiences
   *
   * 预先生成的安全指南已注入约束检查的系统提示词。
   * - ``""``（默认）：裸约束检查 -- 没有经验。 分析器仍然将参与者和判断者分开； 它只是在没有特定工具指导的情况下进行分类。
   * - 任何非空字符串：按原样使用。 预期的模式是调用需要 ``[toolshield]`` 可选额外 (``pip install openhands-sdk[toolshield]``) 的助手 (``default_safety_experiences()``、``load_safety_experiences(tool_names)``、``auto_detect_safety_experiences()``) 之一。 拥有自己的指南来源的调用者可以传递任何自定义字符串。
   */
  safety_experiences?: string;
};

/**
 * ToolShieldLLMSecurityAnalyzer
 *
 * 通过单独的约束检查 LLM 评估每个操作。
 *
 * 与现有的``ConfirmRisky``政策不变：这
 * 分析器仅 * 分配 * 风险级别； ``ConfirmRisky`` 决定
 * 是否暂停以供用户确认。
 *
 * 默认情况下，分析器作为裸机约束检查运行（没有蒸馏
 * safety experiences). 要启用 ToolShield 种子，请安装
 * ``pip install openhands-sdk[toolshield]`` 并传递渲染的
 * 通过 ``safety_experiences`` 字段获得的经验——通常通过
 * 助手之一 (``default_safety_experiences()``,
 * ``load_safety_experiences(...)``, ``auto_detect_safety_experiences()``).
 * 针对 ``toolshield>=0.1.3,<0.2`` 进行测试。
 *
 * 注：``reasoning_content``和``thinking_blocks``来自扩展-
 * 思维模型被故意排除在约束检查之外
 * 上下文。 风险信号存在于工具调用的名字中，并且
 * 论据； 包括推理文本会使提示词膨胀
 * 无比例安全增益。 需要推理的子类
 * 可见性应覆盖：func:`_format_action_for_guardrail`。
 *
 * 生命周期：实例维护最近的每个会话双端队列
 * 约束检查上下文的操作（``history_window`` 项）。 每个
 * 实例供 SINGLE-CONVERSATION 使用。 重复使用一个
 * 跨多个对话的分析器实例将泄漏操作
 * 他们之间的历史，这都是隐私问题（对话
 * A 的工具参数在对话 B 中可见约束检查提示词)
 * 以及正确性问题（约束检查评估对话 B 的
 * 针对无关历史的行动）。 每构建一个分析器
 * 对话，或在对话中致电：meth:`reset_history`
 * 边界。
 *
 * 最近的操作上下文在分析器之间的传播（这个，
 * :class:`LLMSecurityAnalyzer`, :class:`GraySwanAnalyzer`) 被跟踪
 * 为了在单独的后续行动中收敛； 直到着陆，
 * 单一对话的生命周期就是契约。
 *
 * 故障模式是一致的并且是整体安全的——两者都是
 * 基础设施错误（网络、速率限制）和解析失败
 * （约束检查响应，但其输出没有可解析的
 * ``RISK:`` 标签）返回 ``SecurityRisk.UNKNOWN``。 ``ConfirmRisky``
 * 用 ``confirm_unknown=True`` 然后暂停以供用户确认，
 * 匹配保守的姿态而不占主导地位``max()``
 * 整体融合。
 */
export type ToolShieldLlmSecurityAnalyzerOutput = {
  /**
   * 历史窗口
   *
   * 要包含为上下文的先前操作的数量。
   */
  history_window?: number;
  /**
   * 种类
   */
  kind: 'ToolShieldLLMSecurityAnalyzer';
  /**
   * LLM用作约束检查。 可以是比演员更小/更便宜的模型LLM； 只有模型对行动风险进行分类的能力才是重要的。
   */
  llm: LlmOutput;
  /**
   * Safety Experiences
   *
   * 预先生成的安全指南已注入约束检查的系统提示词。
   * - ``""``（默认）：裸约束检查 -- 没有经验。 分析器仍然将参与者和判断者分开； 它只是在没有特定工具指导的情况下进行分类。
   * - 任何非空字符串：按原样使用。 预期的模式是调用需要 ``[toolshield]`` 可选额外 (``pip install openhands-sdk[toolshield]``) 的助手 (``default_safety_experiences()``、``load_safety_experiences(tool_names)``、``auto_detect_safety_experiences()``) 之一。 拥有自己的指南来源的调用者可以传递任何自定义字符串。
   */
  safety_experiences?: string;
};

export type TraceMetadataValue =
  | string
  | boolean
  | number
  | number
  | Array<string>
  | Array<boolean>
  | Array<number>
  | Array<number>;

/**
 * UninstallCanvasExtensionResponse
 *
 * 来自画布扩展卸载的响应。
 */
export type UninstallCanvasExtensionResponse = {
  /**
   * 留言
   */
  message: string;
};

/**
 * UninstallPluginResponse
 *
 * 插件卸载的响应。
 */
export type UninstallPluginResponse = {
  /**
   * 留言
   */
  message: string;
};

/**
 * UninstallSkillResponse
 *
 * 技能卸载操作的响应。
 */
export type UninstallSkillResponse = {
  /**
   * 留言
   */
  message: string;
};

/**
 * UpdateCanvasExtensionStateRequest
 *
 * 用于更新画布扩展状态（启用/禁用）的请求正文。
 */
export type UpdateCanvasExtensionStateRequest = {
  /**
   * 启用
   */
  enabled: boolean;
};

/**
 * UpdateCanvasExtensionStateResponse
 *
 * 来自画布扩展状态更新的响应。
 */
export type UpdateCanvasExtensionStateResponse = {
  /**
   * 启用
   */
  enabled: boolean;
  /**
   * 名称
   */
  name: string;
};

/**
 * UpdateConversationRequest
 *
 * 载荷更新对话元数据。
 */
export type UpdateConversationRequest = {
  /**
   * 标签
   *
   * 要在对话上设置的键值标记。 键必须是小写字母数字。 值是最多 256 个字符的任意字符串。 替换所有现有标签（如果提供）。
   */
  tags?: {
    [key: string]: string;
  } | null;
  /**
   * 标题
   *
   * 新对话标题
   */
  title?: string | null;
};

/**
 * UpdatePluginResponse
 *
 * 来自插件刷新/更新的响应。
 */
export type UpdatePluginResponse = {
  /**
   * 留言
   */
  message: string;
  plugin: InstalledPluginResponse;
};

/**
 * UpdatePluginStateRequest
 *
 * 用于更新插件状态（启用/禁用）的请求正文。
 */
export type UpdatePluginStateRequest = {
  /**
   * 启用
   */
  enabled: boolean;
};

/**
 * UpdatePluginStateResponse
 *
 * 来自插件状态更新的响应。
 */
export type UpdatePluginStateResponse = {
  /**
   * 启用
   */
  enabled: boolean;
  /**
   * 名称
   */
  name: string;
};

/**
 * UpdateSecretsRequest
 *
 * 载荷更新对话中的机密。
 */
export type UpdateSecretsRequest = {
  /**
   * 机密
   *
   * 字典将机密键映射到值
   */
  secrets: {
    [key: string]: SecretSourceInput;
  };
};

/**
 * UpdateSkillResponse
 *
 * 技能更新操作的响应。
 */
export type UpdateSkillResponse = {
  /**
   * 留言
   */
  message: string;
  skill: InstalledSkillResponse;
};

/**
 * UpdateSkillStateRequest
 *
 * 更新技能状态的请求正文（启用/禁用）。
 */
export type UpdateSkillStateRequest = {
  /**
   * 启用
   */
  enabled: boolean;
};

/**
 * UpdateSkillStateResponse
 *
 * 技能状态更新操作的响应。
 */
export type UpdateSkillStateResponse = {
  /**
   * 启用
   */
  enabled: boolean;
  /**
   * 名称
   */
  name: string;
};

/**
 * UserRejectObservation
 *
 * 观测结果当操作被用户或挂钩拒绝时。
 *
 * 该事件在以下情况下发出：
 * - 用户在确认模式期间拒绝操作（rejection_source=“用户”）
 * - PreToolUse 钩子阻止一个动作 (rejection_source="hook")
 */
export type UserRejectObservation = {
  /**
   * 操作 ID
   *
   * 此观测结果正在响应的操作 ID
   */
  action_id: string;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'UserRejectObservation';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 拒绝原因
   *
   * 拒绝行动的原因
   */
  rejection_reason?: string;
  /**
   * 拒绝源
   *
   * 拒绝来源：“user”用于确认模式拒绝，“hook”用于 PreToolUse 挂钩块
   */
  rejection_source?: 'user' | 'hook';
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具调用身份证号
   *
   * 此观测结果正在响应的工具调用 id
   */
  tool_call_id: string;
  /**
   * 工具名称
   *
   * 此观测结果响应的工具名称
   */
  tool_name: string;
};

/**
 * VSCodeUrlResponse
 *
 * VSCode URL 的响应模型。
 */
export type VsCodeUrlResponse = {
  /**
   * 网址
   */
  url: string | null;
};

/**
 * ValidateProfileError
 *
 * 验证失败时返回结构化错误。
 */
export type ValidateProfileError = {
  /**
   * 留言
   */
  message: string;
  /**
   * 类型
   */
  type: string;
};

/**
 * ValidateProfileRequest
 *
 * LLM 飞行前验证的请求正文。
 *
 * 接受一个 LLM 配置(相同的形状 ``SaveProfileRequest.llm``) 所以就
 * 前端可以在保留草稿之前*验证它*。
 */
export type ValidateProfileRequest = {
  llm: LlmInput;
};

/**
 * ValidateProfileResponse
 *
 * LLM 飞行前检查的结果。
 */
export type ValidateProfileResponse = {
  error?: ValidateProfileError | null;
  /**
   * 有效
   */
  valid: boolean;
};

/**
 * ValidationError
 */
export type ValidationError = {
  /**
   * 上下文
   */
  ctx?: {
    [key: string]: unknown;
  };
  /**
   * 输入
   */
  input?: unknown;
  /**
   * 地点
   */
  loc: Array<string | number>;
  /**
   * 留言
   */
  msg: string;
  /**
   * 错误类型
   */
  type: string;
};

/**
 * VerifiedModelsResponse
 *
 * 响应包含由提供商组织的经过验证的 LLM 模型。
 */
export type VerifiedModelsResponse = {
  /**
   * 型号
   */
  models: {
    [key: string]: Array<string>;
  };
};

/**
 * VisionInspectAction
 *
 * 向视觉模型询问附加图像的操作。
 */
export type VisionInspectAction = {
  /**
   * 图片索引
   *
   * 要从最新用户消息中检查的图像的从零开始的索引。
   */
  image_index: number;
  /**
   * 种类
   */
  kind: 'VisionInspectAction';
  /**
   * 个人资料名称
   *
   * 可选的已保存的视觉功能 LLM 配置文件名称。 如果省略，则使用工具描述中列出的第一个可用的视觉配置文件。
   */
  profile_name?: string | null;
  /**
   * 问题
   *
   * 向视觉模型询问有关所选图像的问题。
   */
  question: string;
};

/**
 * VisionInspectObservation
 *
 * 观测结果在视觉模型检查图像后返回。
 */
export type VisionInspectObservation = {
  /**
   * 回答
   *
   * 视觉模型返回的文本答案。
   */
  answer?: string | null;
  /**
   * 基本网址
   *
   * 用于检查的视觉功能 LLM 端点。
   */
  base_url?: string | null;
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 图片索引
   *
   * 检查的图像索引。
   */
  image_index: number;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'VisionInspectObservation';
  /**
   * 型号
   *
   * 用于检查的具有视觉功能的模型。
   */
  model?: string | null;
  /**
   * 个人资料名称
   *
   * 用于检查的视觉轮廓。
   */
  profile_name?: string | null;
  /**
   * 问题
   *
   * 关于视觉模型的问题。
   */
  question: string;
};

/**
 * VisionInspectTool
 *
 * 通过保存的视觉配置文件进行一次性图像检查的工具。
 */
export type VisionInspectTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'VisionInspectTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * WebhookSpec
 *
 * 规范创建 Webhook。 所有 Webhook 请求都使用 POST 方法。
 */
export type WebhookSpec = {
  /**
   * 基本网址
   *
   * Webhook 服务的基 URL。 事件批次发送至 {base_url}/events/{conversation_id.hex}（不带破折号的对话 ID），对话信息发送至 {base_url}/conversations
   */
  base_url: string;
  /**
   * 事件缓冲区大小
   *
   * 在发布到 Webhook 之前要在本地缓冲的事件数
   */
  event_buffer_size?: number;
  /**
   * 冲洗延迟
   *
   * 延迟（以秒为单位），之后缓冲的事件将刷新到 Webhook，即使缓冲区未满。 计时器在第一个事件排队时启动，并且不会被后续事件重置。
   */
  flush_delay?: number;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 最大批次字节数
   *
   * 每个 Webhook 请求的已序列化大小的上限。 大于此限制的单个事件将自行发送。
   */
  max_batch_bytes?: number;
  /**
   * 最大队列字节数
   *
   * 为传送而缓冲的事件大小的上限已序列化。 当队列超过此界限时，最旧的事件将被删除。
   */
  max_queue_bytes?: number;
  /**
   * 最大队列大小
   *
   * 缓冲传递的事件数量的上限。 最旧的事件将被丢弃超过此界限，以防止内存无限增长。
   */
  max_queue_size?: number;
  /**
   * 数量重试
   *
   * post操作失败时返回重试的次数
   */
  num_retries?: number;
  /**
   * 重试延迟
   *
   * 重试之间的延迟
   */
  retry_delay?: number;
};

/**
 * WorkflowAction
 *
 * 模式用于运行 Python 动态工作流脚本。
 */
export type WorkflowAction = {
  /**
   * 种类
   */
  kind: 'WorkflowAction';
  /**
   * 最大并发
   *
   * 同时运行的最大子智能体个任务数。 对于 LLM 密集的工作流程请考虑 2-4，以避免达到 API 速率限制。
   */
  max_concurrency?: number;
  /**
   * 名称
   *
   * 此工作流运行的简称。
   */
  name: string;
  /**
   * 脚本
   *
   * Python 要运行的工作流脚本。 它必须定义 `async def main(wf):` 并仅通过提供的 `wf` 对象协调工作。
   */
  script: string;
};

/**
 * WorkflowObservation
 *
 * 观测结果来自动态工作流程运行。
 */
export type WorkflowObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 种类
   */
  kind: 'WorkflowObservation';
  /**
   * 名称
   *
   * 执行的工作流名称。
   */
  name: string;
  /**
   * 状态
   *
   * 工作流执行状态。
   */
  status: 'completed' | 'error';
};

/**
 * WorkflowTool
 *
 * 用于显式执行程序注入的低级工具。
 *
 * 首选 ``WorkflowToolSet`` 标准 SDK 自动创建用法。
 * 当需要注入自定义执行器时使用``WorkflowTool``
 * （e.g.，在测试或扩展中）。
 */
export type WorkflowTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WorkflowTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * WorkflowToolSet
 *
 * 创建动态工作流程工具的工具集。
 */
export type WorkflowToolSet = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WorkflowToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * WorkspaceItem
 */
export type WorkspaceItem = {
  /**
   * 身份证号
   */
  id: string;
  /**
   * 名称
   */
  name: string;
  /**
   * 父路径
   */
  parentPath?: string | null;
  /**
   * 路径
   */
  path: string;
};

/**
 * WorkspaceParentItem
 */
export type WorkspaceParentItem = {
  /**
   * 身份证号
   */
  id: string;
  /**
   * 名称
   */
  name: string;
  /**
   * 路径
   */
  path: string;
};

/**
 * WorkspacesListResponse
 */
export type WorkspacesListResponse = {
  /**
   * 工作空间父母
   */
  workspaceParents?: Array<WorkspaceParentItem>;
  /**
   * 工作区
   */
  workspaces?: Array<WorkspaceItem>;
};

/**
 * WriteFileAction
 *
 * 模式用于写文件操作。
 */
export type WriteFileAction = {
  /**
   * 内容
   *
   * 要写入文件的内容。
   */
  content: string;
  /**
   * 文件路径
   *
   * 要写入的文件的路径。
   */
  file_path: string;
  /**
   * 种类
   */
  kind: 'WriteFileAction';
};

/**
 * WriteFileObservation
 *
 * 观测结果来自写入文件。
 */
export type WriteFileObservation = {
  /**
   * 内容
   *
   * 从工具返回的内容作为 TextContent/ImageContent 对象的列表。 当出现错误时，应将其写入此字段。
   */
  content?: Array<TextContent | ImageContent>;
  /**
   * 文件路径
   *
   * 写入的文件路径。
   */
  file_path?: string | null;
  /**
   * 是错误
   *
   * 观测结果是否表示错误
   */
  is_error?: boolean;
  /**
   * 是新文件
   *
   * 是否创建了新文件。
   */
  is_new_file?: boolean;
  /**
   * 种类
   */
  kind: 'WriteFileObservation';
  /**
   * 新内容
   *
   * 新内容写入文件。
   */
  new_content?: string | null;
  /**
   * 旧内容
   *
   * 文件的先前内容（如果存在）。
   */
  old_content?: string | null;
};

/**
 * WriteFileTool
 *
 * 用于写入完整文件内容的工具。
 */
export type WriteFileTool = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WriteFileTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
  /**
   * 标题
   */
  readonly title: string;
};

/**
 * _RemoteMCPServerSpec
 *
 * 传统远程 MCP 服务器规范已被公众接受 REST API。
 */
export type RemoteMcpServerSpec = {
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInput)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInput)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInput)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInput)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInput)
    | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 类型
   */
  type: 'http' | 'shttp' | 'streamable-http' | 'sse';
  /**
   * 网址
   */
  url: string;
};

/**
 * _StdioMCPServerSpec
 *
 * 传统 stdio MCP 服务器规范已被公众接受 REST API。
 */
export type StdioMcpServerSpec = {
  /**
   * 参数
   */
  args?: Array<string>;
  /**
   * 命令
   *
   * 执行调用的可执行文件
   */
  command: string;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 环境
   */
  env?: {
    [key: string]: string;
  };
  /**
   * 类型
   */
  type?: 'stdio';
};

/**
 * 工具
 *
 * 客户端可以调用的工具的定义。
 */
export type McpTypesTool = {
  /**
   * 元
   */
  _meta?: {
    [key: string]: unknown;
  } | null;
  annotations?: McpTypesToolAnnotations | null;
  /**
   * 描述
   */
  description?: string | null;
  execution?: ToolExecution | null;
  /**
   * 图标
   */
  icons?: Array<Icon> | null;
  /**
   * 输入模式
   */
  inputSchema: {
    [key: string]: unknown;
  };
  /**
   * 名称
   */
  name: string;
  /**
   * 输出模式
   */
  outputSchema?: {
    [key: string]: unknown;
  } | null;
  /**
   * 标题
   */
  title?: string | null;
  [key: string]: unknown;
};

/**
 * ToolAnnotations
 *
 * 向客户端描述工具的附加属性。
 *
 * 注意：ToolAnnotations中的所有属性都是**提示**。
 * 他们不保证提供忠实的描述
 * 工具行为（包括 `title` 等描述性属性）。
 *
 * 客户永远不应根据 ToolAnnotations 做出工具使用决策
 * 从不受信任的服务器收到。
 */
export type McpTypesToolAnnotations = {
  /**
   * 破坏性暗示
   */
  destructiveHint?: boolean | null;
  /**
   * 幂等性
   */
  idempotentHint?: boolean | null;
  /**
   * 开放世界提示
   */
  openWorldHint?: boolean | null;
  /**
   * 只读提示
   */
  readOnlyHint?: boolean | null;
  /**
   * 标题
   */
  title?: string | null;
  [key: string]: unknown;
};

/**
 * MarketplaceCatalogResponse
 *
 * 包含插件市场目录的响应。
 */
export type OpenhandsAgentServerPluginsRouterMarketplaceCatalogResponse = {
  /**
   * 插件
   */
  plugins: Array<MarketplacePluginInfo>;
};

/**
 * MarketplaceCatalogResponse
 *
 * 包含市场目录的响应。
 */
export type OpenhandsAgentServerSkillsRouterMarketplaceCatalogResponse = {
  /**
   * 技能
   */
  skills: Array<MarketplaceSkillInfo>;
};

/**
 * 工具
 *
 * 定义要为智能体初始化的工具。
 *
 * 这仅在智能体-SDK 中用于服务器使用的类型模式。
 */
export type OpenhandsSdkToolSpecTool = {
  /**
   * 名称
   *
   * 工具类的名称，e.g.，“TerminalTool”。 从 `openhands.tools.<module>` 子包导入它。
   */
  name: string;
  /**
   * 参数
   *
   * 该工具的 .create() 方法的参数，e.g., {'working_dir': '/app'}
   */
  params?: {
    [key: string]: unknown;
  };
};

/**
 * openhands.sdk.tool.tool.ToolAnnotations
 *
 * 提供有关工具行为的提示的注释。
 *
 * 根据模型上下文协议(MCP)说明：
 * https://github.com/modelcontextprotocol/modelcontextprotocol/blob/caf3424488b10b4a7b1f8cb634244a450a1f4400/schema/2025-06-18/schema.ts#L838
 */
export type OpenhandsSdkToolToolToolAnnotations = {
  /**
   * 破坏性暗示
   *
   * 如果 True，该工具可能对其环境执行破坏性更新。 如果是 False，则该工具仅执行附加更新。 （该属性仅当`readOnlyHint == false`时才有意义）默认：True
   */
  destructiveHint?: boolean;
  /**
   * 幂等性
   *
   * True 如果重复使用相同的参数调用工具，对它的环境将没有任何额外影响。（只有在`readOnlyHint == false`时才有意义）默认：False
   */
  idempotentHint?: boolean;
  /**
   * 开放世界提示
   *
   * 如果 True，则该工具可以与外部实体的“开放世界”进行交互。 如果是False，则该工具的交互域是封闭的。 例如，网络搜索工具的世界是开放的，而记忆工具的世界则不是。 默认值：True
   */
  openWorldHint?: boolean;
  /**
   * 只读提示
   *
   * 如果为 True，则该工具不会修改其环境。 默认值：False
   */
  readOnlyHint?: boolean;
  /**
   * 标题
   *
   * 该工具的人类可读标题。
   */
  title?: string | null;
};

/**
 * ACPAgent
 *
 * 智能体委托给 ACP 兼容的子进程服务器。
 */
export type AcpAgentInputWritable = {
  /**
   * ACP 参数
   *
   * ACP 服务器命令的附加参数
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 启动命令 ACP 请输出简体中文译文 e.g. ['npx', '-y', '@agentclientprotocol/claude-智能体-ACP']
   */
  acp_command: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留“文件内容”凭据机密，以便在启动子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 SDK 拥有该机制（在运行时 pod 中写入文件、设置环境变量、seed-if-absent）； 这些规格就是政策。 默认为内置支持的提供程序； 下游应用程序可以覆盖或扩展它以支持具有不同文件身份验证方案的其他ACP服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 ``HOME``。 当 True 和提供者被识别时，指向其 data-dir env var (``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR`` / ``HOME``; 参见 ``<persistence_dir>/acp/<provider>`` 处的 ``ACPProviderInfo.data_dir_env_var``）——使用相同的每个对话树具体化文件 - 机密。 ``SandboxGroupingStrategy != NO_GROUPING`` 该端点用于确保用户多个会话共享一个沙箱时的正确性，否则它们会同时在一组 CLI auth/config/cache/lock 文件上竞争（参见 #1019）。 默认关闭：每个对话一个沙箱，共享 HOME 已经是私有的，重新定位它会隐藏预先存在的交互式登录。 下游策略决定何时启用； SDK 拥有根所在的位置。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * ACP 服务器使用的模型 (e.g. “十四行诗”或“gpt-5.5”）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 如果为 None，则服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 呼叫处于不活动状态超时秒。 截止日期在每次更新后重置（ACP服务器，token，工具调用进度，使用），因此一个持续进展的智能体会一直运行，只要它继续进展。 提示词仅在这么多秒后才中止，根本没有任何活动。 当 ACP 服务器停止响应时，防止无限期挂起，而不终止合法的长时间运行的工作。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 恢复会话 ID
   *
   * 要恢复的可选显式 ACP 会话 ID。 设置后，优先于 ``state.agent_state`` 中的 id 已持久化，并用于调用 ACP 服务器上的 ``session/load``。 专为每次会话文件系统（因此``base_state.json``）在重新启动后无法保留的环境而设计（e.g。 云沙箱回收），但 ID 已镜像到其他地方的持久存储中。 如果服务器无法加载 ID，则回退到新会话。 被视为线路上的机密 — 拥有 id 足以恢复底层 ACP 会话，因此默认序列化会对其进行编辑； 当值必须跨越序列化边界时，传递 ``expose_secrets='plaintext'``（可信后端）或 ``expose_secrets='encrypted'`` 加密码（前端往返）。
   */
  acp_resume_session_id?: string | null;
  /**
   * ACP 服务器
   *
   * 提供商注册表  ACP  CLI this 智能体 runs (any ACP_PROVIDERS key，或者 'custom'。 None when the 智能体直接构建，而不是通过 ACPAgentSettings. 设置为 ACPAgentSettings.create_agent() from ACPAgentSettings.acp_server 因此，权威密钥会传递给智能体 — 于是，我们继续前进 ConversationInfo.agent — 因为在中的启动命令 acp_command 不可靠地反向映射到提供者。 仅供参考：消费者使用它来解析提供商品牌标签/型号列表； 的子进程仍然从这里启动 acp_command.
   */
  acp_server?: string | null;
  /**
   * ACP 会话模式
   *
   * 创建会话后设置的会话模式 ID。 如果为 None（默认），则从 ACP 服务器类型自动检测：“bypassPermissions”用于 claude-智能体-ACP，“智能体-full-access”用于 codex-ACP； 没有这种模式的提供者（pi-ACP）会跳过调用。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时以秒为单位 ACP 服务器启动：生成子进程、初始化/身份验证握手和 new_session()/load_session(). 与 acp_prompt_timeout 不同，这是一个硬截止时间而不是空闲截止时间，因为启动没有中间进度信号来重置它。 当 ACP 服务器在身份验证 (e.g. 已过期token），从未筹集资金。
   */
  acp_startup_timeout?: number;
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextInputWritable | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseInputWritable | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseInputWritable | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind?: 'ACPAgent';
  llm?: LlmInputWritable;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInputWritable;
  };
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   */
  tools?: Array<ToolInput>;
};

/**
 * ACPAgent
 *
 * 智能体委托给 ACP 兼容的子进程服务器。
 */
export type AcpAgentOutputWritable = {
  /**
   * ACP 参数
   *
   * ACP 服务器命令的附加参数
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 启动命令 ACP 请输出简体中文译文 e.g. ['npx', '-y', '@agentclientprotocol/claude-智能体-ACP']
   */
  acp_command: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留“文件内容”凭据机密，以便在启动子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 SDK 拥有该机制（在运行时 pod 中写入文件、设置环境变量、seed-if-absent）； 这些规格就是政策。 默认为内置支持的提供程序； 下游应用程序可以覆盖或扩展它以支持具有不同文件身份验证方案的其他ACP服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 ``HOME``。 当 True 和提供者被识别时，指向其 data-dir env var (``CODEX_HOME`` / ``CLAUDE_CONFIG_DIR`` / ``HOME``; 参见 ``<persistence_dir>/acp/<provider>`` 处的 ``ACPProviderInfo.data_dir_env_var``）——使用相同的每个对话树具体化文件 - 机密。 ``SandboxGroupingStrategy != NO_GROUPING`` 该端点用于确保用户多个会话共享一个沙箱时的正确性，否则它们会同时在一组 CLI auth/config/cache/lock 文件上竞争（参见 #1019）。 默认关闭：每个对话一个沙箱，共享 HOME 已经是私有的，重新定位它会隐藏预先存在的交互式登录。 下游策略决定何时启用； SDK 拥有根所在的位置。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * ACP 服务器使用的模型 (e.g. “十四行诗”或“gpt-5.5”）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 如果为 None，则服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 呼叫处于不活动状态超时秒。 截止日期在每次更新后重置（ACP服务器，token，工具调用进度，使用），因此一个持续进展的智能体会一直运行，只要它继续进展。 提示词仅在这么多秒后才中止，根本没有任何活动。 当 ACP 服务器停止响应时，防止无限期挂起，而不终止合法的长时间运行的工作。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 恢复会话 ID
   *
   * 要恢复的可选显式 ACP 会话 ID。 设置后，优先于 ``state.agent_state`` 中的 id 已持久化，并用于调用 ACP 服务器上的 ``session/load``。 专为每次会话文件系统（因此``base_state.json``）在重新启动后无法保留的环境而设计（e.g。 云沙箱回收），但 ID 已镜像到其他地方的持久存储中。 如果服务器无法加载 ID，则回退到新会话。 被视为线路上的机密 — 拥有 id 足以恢复底层 ACP 会话，因此默认序列化会对其进行编辑； 当值必须跨越序列化边界时，传递 ``expose_secrets='plaintext'``（可信后端）或 ``expose_secrets='encrypted'`` 加密码（前端往返）。
   */
  acp_resume_session_id?: string | null;
  /**
   * ACP 服务器
   *
   * 提供商注册表  ACP  CLI this 智能体 runs (any ACP_PROVIDERS key，或者 'custom'。 None when the 智能体直接构建，而不是通过 ACPAgentSettings. 设置为 ACPAgentSettings.create_agent() from ACPAgentSettings.acp_server 因此，权威密钥会传递给智能体 — 于是，我们继续前进 ConversationInfo.agent — 因为在中的启动命令 acp_command 不可靠地反向映射到提供者。 仅供参考：消费者使用它来解析提供商品牌标签/型号列表； 的子进程仍然从这里启动 acp_command.
   */
  acp_server?: string | null;
  /**
   * ACP 会话模式
   *
   * 创建会话后设置的会话模式 ID。 如果为 None（默认），则从 ACP 服务器类型自动检测：“bypassPermissions”用于 claude-智能体-ACP，“智能体-full-access”用于 codex-ACP； 没有这种模式的提供者（pi-ACP）会跳过调用。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时以秒为单位 ACP 服务器启动：生成子进程、初始化/身份验证握手和 new_session()/load_session(). 与 acp_prompt_timeout 不同，这是一个硬截止时间而不是空闲截止时间，因为启动没有中间进度信号来重置它。 当 ACP 服务器在身份验证 (e.g. 已过期token），从未筹集资金。
   */
  acp_startup_timeout?: number;
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextOutput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseOutputWritable | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseOutputWritable | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind: 'ACPAgent';
  llm?: LlmOutputWritable;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  };
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   */
  tools?: Array<OpenhandsSdkToolSpecTool>;
};

/**
 * ACPAgentSettings
 *
 * ACP（智能体客户端协议）智能体的设置。
 *
 * ``create_agent()`` 返回一个：class:`ACPAgent` ，该类委托给
 * 子进程 ACP 服务器。 ACP服务器管理自己的系统提示词，
 * 工具、MCP 和（主要）LLM 调用； 这些字段来自
 * :class:`OpenHandsAgentSettings` 不适用于此处。
 *
 * :attr:`acp_model` 是模型标识。 创建的``ACPAgent``保持其
 * 自己的指标LLM，因此标题生成可以告诉它永远不可调用。
 * 提供商凭据参与对话机密频道
 * (``request.secrets`` / ``agent_context.secrets`` → ``state.secret_registry``)
 * 由提供者的环境变量名称 (:attr:`api_key_env_var`) 键入。
 */
export type AcpAgentSettingsWritable = {
  /**
   * ACP 参数
   *
   * 附加到 ACP 服务器命令的其他参数。
   */
  acp_args?: Array<string>;
  /**
   * ACP 命令
   *
   * 用于启动 ACP 子进程的可选显式命令。 留空以使用：attr:`acp_server` (e.g. ``npx -y @agentclientprotocol/claude-agent-acp`` 为 ``claude-code``）。 当：attr:`acp_server`为``'custom'``时必须设置。
   */
  acp_command?: Array<string>;
  /**
   * ACP 文件机密
   *
   * 保留的“文件内容”凭据机密 SDK 在启动 ACP 子进程 (e.g. 法典 auth.json、Gemini Vertex SA JSON）。 默认为内置支持的提供程序； 覆盖以支持具有不同文件身份验证方案的其他 ACP 服务器。
   */
  acp_file_secrets?: Array<AcpFileSecretSpec>;
  /**
   * ACP 隔离数据目录
   *
   * 为 ACP 子进程提供每个会话 CLI 数据/配置根目录，而不是共享用户 HOME。 转发到：attr:`~openhands.sdk.agent.ACPAgent.acp_isolate_data_dir`; 默认关闭。 当多个对话共享一个沙箱时从部署应用程序启用（请参阅#1019）。
   */
  acp_isolate_data_dir?: boolean;
  /**
   * ACP 型号
   *
   * 要使用的 ACP 服务器的型号标识符 (e.g. ``'sonnet'``或``'gpt-5.5'``）。 通过协议应用 - set_config_option（模型）用于基于 configOptions 的服务器（codex，claude），其他 set_session_model。 留空以让服务器选择其默认值。
   */
  acp_model?: string | null;
  /**
   * ACP 提示词超时
   *
   * 单次 ACP prompt() 次往返的不活动状态超时（秒）。 ACP 服务器的每次更新都会重置截止日期，因此稳定进展的智能体会继续运行； 提示词仅在这么多秒后才会中止，根本没有任何活动。
   */
  acp_prompt_timeout?: number;
  /**
   * ACP 服务器
   *
   * 要启动哪个 ACP 兼容后端。 每个选择都映射到默认的子进程命令（请参阅 ``acp_command`` 进行覆盖）。
   */
  acp_server?: 'claude-code' | 'codex' | 'gemini-cli' | 'kimi-code' | 'pi' | 'opencode' | 'custom';
  /**
   * ACP 会话模式
   *
   * 会话模式 ID (e.g. ``bypassPermissions``). 留空以从 ACP 服务器类型自动检测。
   */
  acp_session_mode?: string | null;
  /**
   * ACP 启动超时
   *
   * 超时（秒）用于ACP服务器启动：启动子进程，初始化/认证握手，以及new_session()/load_session().（硬性截止日期），不同于acp_prompt_timeout，因为启动没有中间进度信号来重置它。
   */
  acp_startup_timeout?: number;
  /**
   * 提示词-仅上下文用于 ACP 服务器。 这里的``secrets``被通告到智能体（名称/描述）并通过``state.secret_registry``到达子进程环境：``LocalConversation``种子``agent_context.secrets``在对话初始化时进入注册表（低于``request.secrets``），因此调用者在Python之外构建请求（e.g。 canvas-local) 也被覆盖，而不仅仅是 ``create_request`` 路径。 提供者凭据属于此处（或在 ``request.secrets`` 中），由提供者的环境变量名称键入。
   */
  agent_context?: AgentContextInputWritable | null;
  /**
   * 智能体种类
   *
   * ``AgentSettings`` 联合的鉴别器。 ``'acp'`` 选择 ACP 委托智能体。
   */
  agent_kind?: 'acp';
  /**
   * MCP 配置
   *
   * MCP 向提供的服务器 ACP  子进程。 Unlike the OpenHands  智能体 — 这些成为在进程中的 MCP 工具 —— 服务器被转发到  ACP 在会话创建时，服务器拥有连接。 只有当时，远程（HTTP/HTTPS）服务器才会被转发 ACP 服务器支持那个传输层; stdio 服务器（在运行时内运行）始终被转发。
   */
  mcp_config?: {
    [key: string]: McpServerInputWritable;
  };
  /**
   * 模式版本
   */
  schema_version?: number;
};

/**
 * ACPModelDiscoveryRequest
 */
export type AcpModelDiscoveryRequestWritable = {
  /**
   * ACP智能体问。 仅使用发射场； ``acp_model``、MCP 服务器和智能体上下文被忽略。
   */
  agent_settings: AcpAgentSettingsWritable;
  /**
   * 刷新
   *
   * 再次询问服务器而不是重复使用结果。
   */
  refresh?: boolean;
  /**
   * 机密
   *
   * 凭据对于服务器，其形状与对话开始请求的 ``secrets`` 相同（通常 ``LookupSecret`` 引用该服务器存储的机密）。
   */
  secrets?: {
    [key: string]: SecretSourceInputWritable;
  };
};

/**
 * APIBasedCritic
 */
export type ApiBasedCriticInputWritable = {
  /**
   * 智能体问题标签
   */
  agent_issue_labels?: Array<string>;
  /**
   * API 钥匙
   *
   * API 用于通过 vLLM 服务进行身份验证的密钥
   */
  api_key: string | string;
  /**
   * 有成功标签
   *
   * 模型是否预测索引 0 处的成功标签
   */
  has_success_label?: boolean;
  /**
   * 基础设施标签
   */
  infra_labels?: Array<string>;
  /**
   * 问题门槛
   *
   * APIBasedCritic特定的概率阈值，用于智能体问题标签，以触发迭代的细化。
   */
  issue_threshold?: number;
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind?: 'APIBasedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
  /**
   * 型号名称
   *
   * 使用的型号名称
   */
  model_name?: string;
  /**
   * 传递工具定义
   *
   * 是否将工具定义传递给模型
   */
  pass_tools_definitions?: boolean;
  /**
   * 情绪标签
   */
  sentiment_labels?: Array<string>;
  /**
   * 情绪图
   */
  sentiment_map?: {
    [key: string]: string;
  };
  /**
   * 服务器网址
   *
   * vLLM 分类服务的基础 URL
   */
  server_url?: string;
  /**
   * 超时秒
   *
   * 超时对模型的请求
   */
  timeout_seconds?: number;
  /**
   * 分词器名称
   *
   * HuggingFace 用于加载聊天模板的分词器名称
   */
  tokenizer_name?: string;
  /**
   * 用户跟进标签
   */
  user_followup_labels?: Array<string>;
};

/**
 * APIBasedCritic
 */
export type ApiBasedCriticOutputWritable = {
  /**
   * 智能体问题标签
   */
  agent_issue_labels?: Array<string>;
  /**
   * API 钥匙
   *
   * API 用于通过 vLLM 服务进行身份验证的密钥
   */
  api_key: string | string;
  /**
   * 有成功标签
   *
   * 模型是否预测索引 0 处的成功标签
   */
  has_success_label?: boolean;
  /**
   * 基础设施标签
   */
  infra_labels?: Array<string>;
  /**
   * 问题门槛
   *
   * APIBasedCritic特定的概率阈值，用于智能体问题标签，以触发迭代的细化。
   */
  issue_threshold?: number;
  /**
   * 用于迭代细化的可选配置。 设置后，如果评论分数低于 success_threshold，最高可达 max_iterations，Conversation.run() 将自动重试任务。
   */
  iterative_refinement?: IterativeRefinementConfig | null;
  /**
   * 种类
   */
  kind: 'APIBasedCritic';
  /**
   * 模式
   *
   * 何时进行评论家评估：
   * - 'finish_and_message'：评估 FinishAction 和智能体 MessageEvent（默认，对性能影响最小）
   * -“all_actions”：在每个智能体操作后进行评估（警告：由于每个操作都调用 API，速度明显变慢）
   */
  mode?: 'finish_and_message' | 'all_actions';
  /**
   * 型号名称
   *
   * 使用的型号名称
   */
  model_name?: string;
  /**
   * 传递工具定义
   *
   * 是否将工具定义传递给模型
   */
  pass_tools_definitions?: boolean;
  /**
   * 情绪标签
   */
  sentiment_labels?: Array<string>;
  /**
   * 情绪图
   */
  sentiment_map?: {
    [key: string]: string;
  };
  /**
   * 服务器网址
   *
   * vLLM 分类服务的基础 URL
   */
  server_url?: string;
  /**
   * 超时秒
   *
   * 超时对模型的请求
   */
  timeout_seconds?: number;
  /**
   * 分词器名称
   *
   * HuggingFace 用于加载聊天模板的分词器名称
   */
  tokenizer_name?: string;
  /**
   * 用户跟进标签
   */
  user_followup_labels?: Array<string>;
};

/**
 * 智能体
 *
 * OpenHands 的主要智能体实现。
 *
 * 智能体类提供运行 AI 智能体的核心功能，可以
 * 与工具交互、处理消息并执行操作。 它继承自
 * AgentBase并实现智能体执行逻辑。 评论家相关功能
 * 由CriticMixin提供。
 *
 * 属性：
 * llm：用于推理的语言模型实例。
 * 工具： 智能体可用的工具列表。
 * system_prompt：内联系统提示词字符串。 当提供智能体
 * 逐字使用此文本而不是从模板渲染。
 * 与非默认 ``system_prompt_filename`` 互斥。
 * **不推荐**，除非您知道自己在做什么（e.g。
 * 为完全不同的任务定制智能体行为）—
 * 这将覆盖OpenHands'内置系统指令。
 * system_prompt_filename：Jinja2 模板文件名相对于解析
 * 智能体的提示词目录，或绝对路径。 默认为
 * ``"system_prompt.j2"``.
 * system_prompt_kwargs：额外的 kwargs 转发到 Jinja2 模板。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM、智能体、工具
 * 从 Pydantic 导入 SecretStr
 *
 * llm = LLM(型号=“gpt-5.6”，api_key=SecretStr(“密钥”))
 * 工具 = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
 * 智能体 = Agent(llm=llm, tools=tools)
 * ```
 *
 * 要完全覆盖系统提示词：
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=工具，
 * system_prompt="你是一位有用的编码助手。",
 * )
 */
export type AgentInputWritable = {
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextInputWritable | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseInputWritable | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseInputWritable | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   *
   * 要包含的默认工具类名称列表。 默认情况下，智能体包括“FinishTool”和“ThinkTool”。 设置为空列表以禁用所有默认工具，或提供一个子集以仅包含特定工具。 示例：include_default_tools=['FinishTool'] 仅包含 FinishTool，或 include_default_tools=[] 禁用所有默认工具。
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind?: 'Agent';
  /**
   * LLM配置为智能体。
   */
  llm: LlmInputWritable;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInputWritable;
  };
  /**
   * 人格面具
   *
   * 替换系统提示词的 OpenHands' 内置角色和编码工作流程部分的角色文本。 能力与策略部分（内存、安全策略、风险评估、浏览器、外部服务、过程管理、模型特定指导）以及动态上下文仍然适用。 设置`system_prompt`时忽略； 自定义模板将其作为 `persona` kwarg 接收。
   */
  persona?: string | null;
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   *
   * 用于初始化的工具列表智能体。
   */
  tools?: Array<ToolInput>;
};

/**
 * 智能体
 *
 * OpenHands 的主要智能体实现。
 *
 * 智能体类提供运行 AI 智能体的核心功能，可以
 * 与工具交互、处理消息并执行操作。 它继承自
 * AgentBase并实现智能体执行逻辑。 评论家相关功能
 * 由CriticMixin提供。
 *
 * 属性：
 * llm：用于推理的语言模型实例。
 * 工具： 智能体可用的工具列表。
 * system_prompt：内联系统提示词字符串。 当提供智能体
 * 逐字使用此文本而不是从模板渲染。
 * 与非默认 ``system_prompt_filename`` 互斥。
 * **不推荐**，除非您知道自己在做什么（e.g。
 * 为完全不同的任务定制智能体行为）—
 * 这将覆盖OpenHands'内置系统指令。
 * system_prompt_filename：Jinja2 模板文件名相对于解析
 * 智能体的提示词目录，或绝对路径。 默认为
 * ``"system_prompt.j2"``.
 * system_prompt_kwargs：额外的 kwargs 转发到 Jinja2 模板。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM、智能体、工具
 * 从 Pydantic 导入 SecretStr
 *
 * llm = LLM(型号=“gpt-5.6”，api_key=SecretStr(“密钥”))
 * 工具 = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
 * 智能体 = Agent(llm=llm, tools=tools)
 * ```
 *
 * 要完全覆盖系统提示词：
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=工具，
 * system_prompt="你是一位有用的编码助手。",
 * )
 */
export type AgentOutputWritable = {
  /**
   * 可选的 AgentContext，用于用特定的上下文初始化智能体。
   */
  agent_context?: AgentContextOutput | null;
  /**
   * 可选的上下文压缩器用于压缩对话历史记录。
   */
  condenser?: CondenserBaseOutputWritable | null;
  /**
   * EXPERIMENTAL：可选评论家实时评估智能体行为和消息。 API 并且行为可能会发生变化，恕不另行通知。 可能会影响性能，尤其是在“all_actions”模式下。
   */
  critic?: CriticBaseOutputWritable | null;
  /**
   * 过滤工具正则表达式
   *
   * 可选的正则表达式，用于按名称过滤智能体可用的工具。 这在添加 `tools` 中提供的任何工具和添加任何 MCP 工具后应用。
   */
  filter_tools_regex?: string | null;
  /**
   * 包括默认工具
   *
   * 要包含的默认工具类名称列表。 默认情况下，智能体包括“FinishTool”和“ThinkTool”。 设置为空列表以禁用所有默认工具，或提供一个子集以仅包含特定工具。 示例：include_default_tools=['FinishTool'] 仅包含 FinishTool，或 include_default_tools=[] 禁用所有默认工具。
   */
  include_default_tools?: Array<string>;
  /**
   * 种类
   */
  kind: 'Agent';
  /**
   * LLM配置为智能体。
   */
  llm: LlmOutputWritable;
  /**
   * MCP 配置
   *
   * 作为工具公开的可选 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  };
  /**
   * 人格面具
   *
   * 替换系统提示词的 OpenHands' 内置角色和编码工作流程部分的角色文本。 能力与策略部分（内存、安全策略、风险评估、浏览器、外部服务、过程管理、模型特定指导）以及动态上下文仍然适用。 设置`system_prompt`时忽略； 自定义模板将其作为 `persona` kwarg 接收。
   */
  persona?: string | null;
  /**
   * 安全策略文件名
   *
   * 安全策略文件名。 默认的 'security_policy.j2' 是一个兼容性哨兵值（文件已被移除），它从提示词注册表中选择内置默认策略。它不会从磁盘加载。 任何其他值都会命名一个自定义策略文件，其内容将逐字插入（不呈现为 Jinja 模板）。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'custom_security_policy.md')
   * - 绝对路径 (e.g., '/path/to/custom_security_policy.md')
   * - 空字符串以禁用安全策略
   */
  security_policy_filename?: string;
  /**
   * 系统提示词
   *
   * 内联系统提示词字符串。 如果提供，智能体会逐字使用该文本作为系统消息，而不是从 `system_prompt_filename` 渲染。 与非默认的互斥`system_prompt_filename`。
   *
   * **警告**：除非你知道你在做什么，否则这不是推荐的做法e.g. 为完全不同的任务定制智能体行为）。 设置此项将覆盖 OpenHands 控制默认智能体行为的内置系统指令。
   */
  system_prompt?: string | null;
  /**
   * 系统提示词文件名
   *
   * 系统提示词模板文件名。 可以是：
   * - 从智能体的提示词目录加载的相对文件名 (e.g., 'system_prompt.j2')
   * - 绝对路径 (e.g., '/path/to/custom_prompt.j2')
   */
  system_prompt_filename?: string;
  /**
   * 系统提示词夸格斯
   *
   * 传递给系统提示词 Jinja2 模板的可选 kwargs。
   */
  system_prompt_kwargs?: {
    [key: string]: unknown;
  };
  /**
   * 工具并发限制
   *
   * 在单个智能体步骤内同时执行的最大工具调用数。 默认值为 1（顺序）。 值 > 1 启用并行执行； 并发工具共享会话对象、文件系统和工作目录，因此共享状态的突变可能会发生竞争。
   */
  tool_concurrency_limit?: number;
  /**
   * 工具
   *
   * 用于初始化的工具列表智能体。
   */
  tools?: Array<OpenhandsSdkToolSpecTool>;
};

export type AgentBaseInputWritable =
  | ({
      kind: 'openhands__sdk__agent__acp_agent__ACPAgent-Input__1';
    } & AcpAgentInputWritable)
  | ({
      kind: 'openhands__sdk__agent__agent__Agent-Input__1';
    } & AgentInputWritable);

export type AgentBaseOutputWritable =
  | ({
      kind: 'openhands__sdk__agent__acp_agent__ACPAgent-Output__1';
    } & AcpAgentOutputWritable)
  | ({
      kind: 'openhands__sdk__agent__agent__Agent-Output__1';
    } & AgentOutputWritable);

/**
 * AgentContext
 *
 * 用于管理提示词扩展的中央结构。
 *
 * AgentContext 统一了塑造系统如何运作的所有上下文输入
 * 扩展并解释用户提示词。 它结合了静态环境
 * 细节和动态的、用户激活的技能扩展。
 *
 * 具体来说，它规定：
 * - **存储库上下文/存储库技能**：有关活动代码库的信息，
 * 分支，以及由回购技能贡献的回购特定指令。
 * - **运行时上下文**：当前执行环境（主机、工作环境）
 * 目录、机密、日期等）。
 * - **对话说明**：可选的特定于任务或频道的规则
 * 限制或指导智能体在整个会话中的行为。
 * - **知识技能**：可以由用户输入触发的可扩展组件
 * 注入知识或特定领域的指导。
 *
 * 这些元素一起使 AgentContext 成为负责的主容器
 * 用于组装、格式化和将所有提示词相关的上下文注入
 * LLM 互动。
 */
export type AgentContextInputWritable = {
  /**
   * 当前日期时间
   *
   * 提供给智能体的当前日期和时间信息。 可以是日期时间对象（将格式化为 ISO 8601）或预先格式化的字符串。 提供后，该信息将包含在系统提示词中，以使智能体了解当前时间上下文。 默认为当前（时区感知）日期时间。
   */
  current_datetime?: string | string | null;
  /**
   * 残疾人技能
   *
   * 从这个上下文中移除EXCLUDE的技能名——一个在每个技能源加载后应用的拒绝列表（自动加载的用户/公共、显式和懒加载的项目技能）。 加载集中不存在的列出名称是无害的无操作。 []（默认）保留所有技能。 这是单一的、容忍偏差的技能选择机制（智能体配置文件从他们自己的拒绝列表中设置它；#4017）。
   */
  disabled_skills?: Array<string>;
  /**
   * 加载内存
   *
   * 是否将持久智能体内存（~/.openhands/memory/和<workspace>/.openhands/memory/)下的MEMORY.md索引加载到系统提示词中。 与load_project_skills一样，该标志不由AgentContext本身解析（工作区路径在验证时未知）； LocalConversation 在第一个 send_message() / run() 上延迟解析它，并将结果存储在 memory_context 中。
   */
  load_memory?: boolean;
  /**
   * 加载项目技能
   *
   * 是否自动加载对话中的项目技能工作区 (e.g. .openhands/skills/, AGENTS.md). 不像 load_user_skills / load_public_skills这个标志不会被解析 AgentContext 它自身（[the]） 工作区路径未知验证时间。 LocalConversation 在第一次解析时懒加载 send_message() / run(), when the 工作区已被知。 也不同于 load_user_skills / load_public_skills （这些技能会优先于明示的冲突技能），已解决的项目技能具有权威性：一个项目技能会覆盖一个已存在的同名技能 `skills`.
   */
  load_project_skills?: boolean;
  /**
   * 加载公共技能
   *
   * 是否自动从  https://github.com/OpenHands/extensions.  处的公共 OpenHands 技能存储库加载技能这使您无需 SDK 更新即可获取最新技能。
   */
  load_public_skills?: boolean;
  /**
   * 加载用户技能
   *
   * 是否自动从 ~/.openhands/skills/ 和 ~/.openhands/microagents/ 加载用户技能（对于向后兼容性）。
   */
  load_user_skills?: boolean;
  /**
   * 市场路径
   *
   * 公共技能存储库内的相对市场 JSON 路径。 设置为 None 以加载所有公共技能而不进行市场过滤。
   */
  marketplace_path?: string | null;
  /**
   * 内存上下文
   *
   * 已解析的内存索引文本呈现到 <MEMORY_CONTEXT> 提示词块中。 当设置 load_memory 时，通过 model_copy 由 LocalConversation 填充； 从序列化中排除，因为它在每个会话中从磁盘重新解析，并且不得使已持久化会话状态膨胀。
   */
  memory_context?: string | null;
  /**
   * 注册市场
   *
   * 插件解析的市场注册。 auto_load=True 或插件名称列表的注册在启动时由 LocalConversation 解析。
   */
  registered_marketplaces?: Array<MarketplaceRegistration>;
  /**
   * 机密
   *
   * 机密个键值对或机密来源的字典。 机密用于身份验证和敏感数据处理。 值可以是字符串，也可以是SecretSource的实例（str | SecretSource)。
   */
  secrets?: {
    [key: string]: string | SecretSourceInputWritable;
  } | null;
  /**
   * 技能
   *
   * 可以扩展用户输入的可用技能列表。
   */
  skills?: Array<SkillInputWritable>;
  /**
   * 系统消息后缀
   *
   * 附加到系统的可选后缀提示词。
   */
  system_message_suffix?: string | null;
  /**
   * 用户消息后缀
   *
   * 用于附加到用户消息的可选后缀。
   */
  user_message_suffix?: string | null;
};

/**
 * AgentDefinition
 *
 * 从 Markdown 文件加载智能体定义。
 *
 * 智能体是可以根据以下条件触发的特殊配置
 * 用户输入模式。 他们定义自定义系统提示词和工具访问。
 */
export type AgentDefinitionWritable = {
  /**
   * 颜色
   *
   * 智能体的显示颜色
   */
  color?: string | null;
  /**
   * 上下文上下文压缩器为子智能体。 None应用默认总结上下文压缩器； 设置 NoOpCondenser 以禁用上下文压缩。
   */
  condenser?: CondenserBaseInputWritable | null;
  /**
   * 描述
   *
   * 智能体说明
   */
  description?: string;
  /**
   * 此智能体的挂钩配置
   */
  hooks?: HookConfig | null;
  /**
   * 级别
   *
   * 发现智能体的范围。 在发现期间设置； None 直接从文件加载时。
   */
  level?: 'project' | 'user' | 'builtin' | 'plugin' | 'programmatic' | null;
  /**
   * 每次运行的最大预算
   *
   * 此子智能体每次运行的最大累积成本 (USD)。 必须严格为正，否则 None 无预算。
   */
  max_budget_per_run?: number | null;
  /**
   * 每次运行的最大迭代次数
   *
   * 每次运行的最大迭代次数。 它必须严格为正数，或者默认为 None。
   */
  max_iteration_per_run?: number | null;
  /**
   * MCP 配置
   *
   * MCP 用于此的服务器智能体。 当它作为代理运行时被忽略子智能体它总是继承其父类 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerInputWritable;
  } | null;
  /**
   * 元数据
   *
   * 来自前置元数据的附加元数据
   */
  metadata?: {
    [key: string]: unknown;
  };
  /**
   * 型号
   *
   * 要使用的模型（“继承”使用父模型）
   */
  model?: string;
  /**
   * 名称
   *
   * 智能体名称（来自前置元数据或文件名）
   */
  name: string;
  /**
   * 权限模式
   *
   * 子智能体如何处理权限。 None 继承父级策略；'always_confirm' 要求每个操作都确认，'never_confirm' 跳过全部确认，'confirm_risky' 仅确认风险超过阈值的操作。
   */
  permission_mode?: string | null;
  /**
   * 配置文件存储目录
   *
   * 存储 LLM 个配置文件的目录路径。 如果 None，则使用默认配置文件存储目录。
   */
  profile_store_dir?: string | null;
  /**
   * 技能
   *
   * 此技能名称列表智能体。 从项目/用户目录解决。
   */
  skills?: Array<string>;
  /**
   * 来源
   *
   * 此智能体的源文件路径
   */
  source?: string | null;
  /**
   * 系统提示词
   *
   * 系统提示词内容
   */
  system_prompt?: string;
  /**
   * 工具
   *
   * 允许使用的工具列表智能体
   */
  tools?: Array<string>;
  /**
   * 何时使用示例
   *
   * 何时使用此智能体的示例（用于触发）
   */
  when_to_use_examples?: Array<string>;
};

/**
 * AgentLaunchAdditions
 *
 * 在智能体解析后添加部署上下文。
 */
export type AgentLaunchAdditionsWritable = {
  /**
   * 法学硕士简介参考
   *
   * LLM 配置文件启动 OpenHands 智能体配置文件而不是其自己的 `llm_profile_ref`。 记载于`launched_agent_profile`； 存储的配置文件不会被修改。 仅对 `agent_profile_id` 有效。
   */
  llm_profile_ref?: string | null;
  /**
   * 技能
   *
   * 部署提供的技能合并到已解决的智能体的上下文中。 对于自己拥有技能目录的客户端来说，无法依赖服务器，因此：``agent_profile_id`` 启动没有 ``agent_settings``，只能这样提供给他们。 ——以名称合并 ——已解决的智能体已经具备了这项技能，因此获胜，而该角色的``disabled_skills``拒绝列表仍然有效，所以这无法重新引入该角色已关闭的功能。 None（默认）不添加任何内容。
   */
  skills?: Array<SkillInputWritable> | null;
  /**
   * 系统消息后缀追加
   *
   * 部署控制的文本附加到已解析的智能体的系统消息后缀。
   */
  system_message_suffix_append?: string | null;
};

/**
 * AgentSettingsPatch
 */
export type AgentSettingsPatchWritable = {
  mcp_config?: McpConfigPatchWritable | null;
  [key: string]: unknown;
};

/**
 * AskOracleTool
 *
 * 用于咨询 Oracle 的工具（名为“oracle”的已保存 LLM 配置文件）。
 */
export type AskOracleToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'AskOracleTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * Body_switch_conversation_llm_api_conversations__conversation_id__switch_llm_post
 */
export type BodySwitchConversationLlmApiConversationsConversationIdSwitchLlmPostWritable = {
  llm: LlmInputWritable;
};

/**
 * BrowserClickTool
 *
 * 用于单击浏览器元素的工具。
 */
export type BrowserClickToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserClickTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserCloseTabTool
 *
 * 用于关闭浏览器选项卡的工具。
 */
export type BrowserCloseTabToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserCloseTabTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserGetContentTool
 *
 * 用于获取Markdown中页面内容的工具。
 */
export type BrowserGetContentToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetContentTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserGetStateTool
 *
 * 获取浏览器状态的工具。
 */
export type BrowserGetStateToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetStateTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserGetStorageTool
 *
 * 用于获取浏览器存储空间的工具。
 */
export type BrowserGetStorageToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGetStorageTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserGoBackTool
 *
 * 用于返回浏览器历史记录的工具。
 */
export type BrowserGoBackToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserGoBackTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserListTabsTool
 *
 * 用于列出浏览器选项卡的工具。
 */
export type BrowserListTabsToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserListTabsTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserNavigateTool
 *
 * 浏览器导航工具。
 */
export type BrowserNavigateToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserNavigateTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserScrollTool
 *
 * 用于滚动浏览器页面的工具。
 */
export type BrowserScrollToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserScrollTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserSetStorageTool
 *
 * 用于设置浏览器存储的工具。
 */
export type BrowserSetStorageToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserSetStorageTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserStartRecordingTool
 *
 * 用于启动浏览器会话记录的工具。
 */
export type BrowserStartRecordingToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserStartRecordingTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserStopRecordingTool
 *
 * 用于停止浏览器会话记录的工具。
 */
export type BrowserStopRecordingToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserStopRecordingTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserSwitchTabTool
 *
 * 用于切换浏览器选项卡的工具。
 */
export type BrowserSwitchTabToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserSwitchTabTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserToolSet
 *
 * 一组所有浏览器工具。
 *
 * 该工具集包括所有可用的浏览器相关工具
 * 用于与网页交互。
 *
 * 该工具集自动检查 Chromium 可用性
 * 创建时会自动安装，如果丢失则自动安装。
 */
export type BrowserToolSetWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * BrowserTypeTool
 *
 * 用于在浏览器元素中输入文本的工具。
 */
export type BrowserTypeToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'BrowserTypeTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * ClassifyAndSwitchLLMTool
 *
 * 对任务进行分类并切换到元配置文件的 LLM 的工具。
 */
export type ClassifyAndSwitchLlmToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ClassifyAndSwitchLLMTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * ClientTool
 *
 * 其执行被推迟到外部客户端的工具。
 *
 * 在对话开始时从：class:`ClientToolSpec` 创建。 智能体
 * 将其视为普通工具并可以调用它； ActionEvent 被发射
 * 超过 WebSocket 供客户端处理。
 */
export type ClientToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 客户端工具名称
   *
   * 每个实例的工具名称来自 ClientToolSpec。
   */
  client_tool_name: string;
  /**
   * 描述
   */
  description: string;
  /**
   * 输入模式
   *
   * 原来的JSON模式为工具的参数，由客户端提供。 将工具导出到 LLM 时逐字使用，以便保留客户端定义的约束（枚举、嵌套对象、边界、additionalProperties、...）。
   */
  input_schema: {
    [key: string]: unknown;
  };
  /**
   * 种类
   */
  kind: 'ClientTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

export type CondenserBaseInputWritable =
  | ({
      kind: 'openhands__sdk__context__condenser__llm_summarizing_condenser__LLMSummarizingCondenser-Input__1';
    } & LlmSummarizingCondenserInputWritable)
  | ({
      kind: 'openhands__sdk__context__condenser__no_op_condenser__NoOpCondenser-Input__1';
    } & NoOpCondenserInput)
  | ({
      kind: 'openhands__sdk__context__condenser__pipeline_condenser__PipelineCondenser-Input__1';
    } & PipelineCondenserInputWritable);

export type CondenserBaseOutputWritable =
  | ({
      kind: 'openhands__sdk__context__condenser__llm_summarizing_condenser__LLMSummarizingCondenser-Output__1';
    } & LlmSummarizingCondenserOutputWritable)
  | ({
      kind: 'openhands__sdk__context__condenser__no_op_condenser__NoOpCondenser-Output__1';
    } & NoOpCondenserOutput)
  | ({
      kind: 'openhands__sdk__context__condenser__pipeline_condenser__PipelineCondenser-Output__1';
    } & PipelineCondenserOutputWritable);

/**
 * ConversationInfo
 *
 * 有关在没有运行时沙箱的情况下本地运行的对话的信息。
 */
export type ConversationInfoWritable = {
  /**
   * 激活知识技能
   *
   * 激活知识技能名称列表
   */
  activated_knowledge_skills?: Array<string>;
  /**
   * 对话中运行的智能体。
   */
  agent: AgentBaseOutputWritable;
  /**
   * 智能体状态
   *
   * 用于在迭代中持续存在的智能体特定运行时状态的字典。
   */
  agent_state?: {
    [key: string]: unknown;
  };
  /**
   * 可用型号
   *
   * 对 ACP 服务器为此会话提供的模型进行建模，从 ``ACPAgent.available_models``（ACP 会话响应上的 ``models.availableModels`` 字段）开始。 每个条目都包含``model_id``和一个可选的``name``/``description``.，Surfaced verbatim，客户端可以自行渲染模型选择器并解析``current_model_id``，服务器不做名称校验。 对于不具备 (UNSTABLE) 功能的 ACP 服务器和本机 OpenHands 智能体为空。 客户端合同：``current_model_id`` 应该不确保是一个成员 —— 强制 ``acp_model`` 重写可能会忽略不在列表中的模型 —— 因此，缺失时显示 '原始 ID'。 有些条目是不透明的别名，其人类身份存在于 ``description`` (e.g. 克劳德-智能体-ACP的``"default"`` -> ``"Opus 4.7 with 1M context · ..."``）。
   */
  available_models?: Array<AcpModelInfo>;
  /**
   * 被阻止的操作
   *
   * 被 PreToolUse 挂钩阻止的操作，由操作 ID 键入
   */
  blocked_actions?: {
    [key: string]: string;
  };
  /**
   * 被阻止的消息
   *
   * 消息被 UserPromptSubmit 挂钩阻止，由消息 ID 键入
   */
  blocked_messages?: {
    [key: string]: string;
  };
  /**
   * 客户端工具
   *
   * 为此对话注册的客户定义的工具规格。 这样，客户端通过会话ID重新连接时，可以在同步已持久化事件之前注册动态的 ClientAction_* 动作类型，从而避免 '未知类型' 反序列化错误。
   */
  client_tools?: Array<ClientToolSpecOutput>;
  confirmation_policy?: ConfirmationPolicyBaseOutput;
  /**
   * 创建于
   */
  created_at?: string;
  /**
   * 当前型号 ID
   *
   * 本次会议实际使用的模型是智能体。 对于 ACP 智能体，它从 ``ACPAgent.current_model_id`` 中解除（从 ACP 会话响应上的 ``models.currentModelId`` 字段填充，或者当调用者强制覆盖时从 ``acp_model`` 填充）。 可能是不透明的别名（e.g. 克劳德-智能体-ACP的``"default"``); 将其与 ``available_models`` 进行匹配以获得显示标签。 ``None`` 适用于未显示该字段的旧 ACP 服务器，或者智能体仍在初始化时。 Native OpenHands 智能体留下这个 ``None`` — 消费者应该阅读 ``agent.llm.model`` 来了解这些。
   */
  current_model_id?: string | null;
  execution_status?: ConversationExecutionStatus;
  /**
   * 从对话 ID 分叉
   *
   * 此会话的分叉 ID。 ``None`` 用于直接创建的对话（不通过 fork）。
   */
  forked_from_conversation_id?: string | null;
  /**
   * 从事件 ID 分叉
   *
   * 此对话分叉的事件 ID。 ``None`` 用于非分叉对话或整个对话分叉。
   */
  forked_from_event_id?: string | null;
  /**
   * 此对话的挂钩配置。 包括 PreToolUse、PostToolUse、UserPromptSubmit、SessionStart、SessionEnd 和 Stop 挂钩的定义。
   */
  hook_config?: HookConfig | null;
  /**
   * 身份证号
   *
   * 唯一的对话ID
   */
  id: string;
  /**
   * 调用技能
   *
   * 通过 `invoke_skill` 工具明确调用的渐进式披露技能的名称。
   */
  invoked_skills?: Array<string>;
  /**
   * 最后用户消息 ID
   *
   * 用于钩子块检查的最新用户 MessageEvent ID。 发出用户消息时进行更新，以便 Agent.step 可以弹出 blocked_messages，而无需扫描事件日志。 如果是None，则跳过钩子阻止检查（遗留对话）。
   */
  last_user_message_id?: string | null;
  /**
   * 启动此对话的智能体配置文件的出处快照。 在创建时通过 ``agent_profile_id`` 开始对话时设置； ``None`` 用于直接从 ``agent`` 或 ``agent_settings`` 开始的对话。 客户端使用它来识别哪个智能体配置文件是最新的，而无需进行脆弱的设置比较。
   */
  launched_agent_profile?: LaunchedAgentProfile | null;
  /**
   * 叶事件 ID
   *
   * 对话树的 HEAD：下一个附加事件的父级。 ``None`` 表示空树（或者，对于预告片对话，线性尾部）。 通过 ``navigate`` 移动它会重新定位智能体运行的活动分支。
   */
  leaf_event_id?: string | null;
  /**
   * 最大迭代次数
   *
   * 智能体在单次运行中可以执行的最大迭代次数。
   */
  max_iterations?: number;
  metrics?: MetricsSnapshot | null;
  /**
   * 家长对话 ID
   *
   * 拥有此对话的 ID。 ``None`` 用于高层对话。
   */
  parent_conversation_id?: string | null;
  /**
   * 持久化目录
   *
   * 用于持久会话状态和事件的目录。 如果为 None，则对话将不是已持久化。
   */
  persistence_dir?: string | null;
  /**
   * 执行运行时的可用性。 当托管服务器管理运行时生命周期时，目录响应将填充此内容。
   */
  runtime_info?: ConversationRuntimeInfo | null;
  /**
   * 注册表用于处理机密和敏感数据
   */
  secret_registry?: SecretRegistryWritable;
  /**
   * 可选的安全分析器来评估操作风险。
   */
  security_analyzer?: SecurityAnalyzerBaseOutputWritable | null;
  /**
   * 用于跟踪 LLM 指标的对话统计信息
   */
  stats?: ConversationStats;
  /**
   * 卡住检测
   *
   * 是否启用智能体卡住检测。
   */
  stuck_detection?: boolean;
  /**
   * 子对话 ID
   *
   * 将此对话命名为其父级的对话 ID。 源自服务器目录； Webhook 载荷上为空。 名称反映了 Cloud API 字段。
   */
  sub_conversation_ids?: Array<string>;
  /**
   * 支持运行时模型切换
   *
   * 是否尝试在本次对话中的实时切换模型 - 会告诉内联选择器是否提供实时切换控制。 镜像 SDK 的切换门：``True`` 表示已知的具有切换能力的提供商； ``False`` 对于未知/自定义 ACP 服务器，因为它们的通用配置写入不能保证实时切换原语。 ``False`` 对于本机 OpenHands 智能体，对于声明不支持的已知提供商，并且在对话开始会话之前。
   */
  supports_runtime_model_switch?: boolean;
  /**
   * 标签
   *
   * 对话的键值标签。 键必须是小写字母数字。 值是最多 256 个字符的任意字符串。
   */
  tags?: {
    [key: string]: string;
  };
  /**
   * 标题
   *
   * 用户定义的对话标题
   */
  title?: string | null;
  /**
   * 工具模块 Qualnames
   *
   * 映射到可导入模块限定名的工具名称。 SDK 客户端使用此元数据来恢复附加时反序列化对话工具事件所需的注册。
   */
  tool_module_qualnames?: {
    [key: string]: string;
  };
  /**
   * 更新于
   */
  updated_at?: string;
  /**
   * 工作区被智能体用来执行命令和读/写文件。 不是流程工作目录。
   */
  workspace: BaseWorkspace;
};

/**
 * ConversationPage
 */
export type ConversationPageWritable = {
  /**
   * 项目
   */
  items: Array<ConversationInfoWritable>;
  /**
   * 下一页 ID
   */
  next_page_id?: string | null;
};

export type CriticBaseInputWritable =
  | ({
      kind: 'openhands__sdk__critic__impl__agent_finished__AgentFinishedCritic-Input__1';
    } & AgentFinishedCriticInput)
  | ({
      kind: 'openhands__sdk__critic__impl__api__critic__APIBasedCritic-Input__1';
    } & ApiBasedCriticInputWritable)
  | ({
      kind: 'openhands__sdk__critic__impl__empty_patch__EmptyPatchCritic-Input__1';
    } & EmptyPatchCriticInput)
  | ({
      kind: 'openhands__sdk__critic__impl__pass_critic__PassCritic-Input__1';
    } & PassCriticInput);

export type CriticBaseOutputWritable =
  | ({
      kind: 'openhands__sdk__critic__impl__agent_finished__AgentFinishedCritic-Output__1';
    } & AgentFinishedCriticOutput)
  | ({
      kind: 'openhands__sdk__critic__impl__api__critic__APIBasedCritic-Output__1';
    } & ApiBasedCriticOutputWritable)
  | ({
      kind: 'openhands__sdk__critic__impl__empty_patch__EmptyPatchCritic-Output__1';
    } & EmptyPatchCriticOutput)
  | ({
      kind: 'openhands__sdk__critic__impl__pass_critic__PassCritic-Output__1';
    } & PassCriticOutput);

/**
 * EditTool
 *
 * 通过查找/替换编辑文件的工具。
 */
export type EditToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'EditTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * EnsembleSecurityAnalyzer
 *
 * 将多个分析仪连接在一起并承担最坏情况的风险。
 *
 * 使用它作为您在对话中设置的顶级分析器。 它
 * 呼叫每个儿童分析员，收集他们的风险评估，以及
 * 返回最高的具体风险。 它不执行任何检测，
 * 提取，或自身标准化。
 *
 * UNKNOWN 的工作原理（默认，``propagate_unknown=False``）：if *all*
 * 子项返回 UNKNOWN，集合返回 UNKNOWN（其中
 * ``ConfirmRisky`` 默认确认）。 如果任何孩子返回
 * 具体级别，UNKNOWN 结果被过滤掉，最高的
 * 实体层面获胜。
 *
 * 对于 ``propagate_unknown=True``：如果 *any* 子级返回 UNKNOWN，则
 * 无论其他结果如何，ensemble 都会返回 UNKNOWN。 使用这个
 * 更严格的环境，应触发不完整的评估
 * 确认。
 *
 * 如果子分析器引发异常，它会贡献 HIGH
 * （失败关闭，记录）。 这可以防止损坏的分析仪默默地
 * 降低安全性。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 (
 * EnsembleSecurityAnalyzer,
 * PatternSecurityAnalyzer,
 * PolicyRailSecurityAnalyzer,
 * ConfirmRisky,
 * SecurityRisk,
 * )
 *
 * 分析仪 = EnsembleSecurityAnalyzer(
 * 分析仪=[
 * PolicyRailSecurityAnalyzer(),
 * PatternSecurityAnalyzer(),
 * ]
 * )
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type EnsembleSecurityAnalyzerInputWritable = {
  /**
   * 分析仪
   *
   * 通过最大严重性组合评估的分析器
   */
  analyzers: Array<SecurityAnalyzerBaseInputWritable>;
  /**
   * 种类
   */
  kind?: 'EnsembleSecurityAnalyzer';
  /**
   * 传播未知
   *
   * 当 True 时，任何返回 UNKNOWN 的子项都会导致整体返回 UNKNOWN。 当 False（默认）时，如果任何子级返回具体级别，则 UNKNOWN 会被过滤掉。
   */
  propagate_unknown?: boolean;
};

/**
 * EnsembleSecurityAnalyzer
 *
 * 将多个分析仪连接在一起并承担最坏情况的风险。
 *
 * 使用它作为您在对话中设置的顶级分析器。 它
 * 呼叫每个儿童分析员，收集他们的风险评估，以及
 * 返回最高的具体风险。 它不执行任何检测，
 * 提取，或自身标准化。
 *
 * UNKNOWN 的工作原理（默认，``propagate_unknown=False``）：if *all*
 * 子项返回 UNKNOWN，集合返回 UNKNOWN（其中
 * ``ConfirmRisky`` 默认确认）。 如果任何孩子返回
 * 具体级别，UNKNOWN 结果被过滤掉，最高的
 * 实体层面获胜。
 *
 * 对于 ``propagate_unknown=True``：如果 *any* 子级返回 UNKNOWN，则
 * 无论其他结果如何，ensemble 都会返回 UNKNOWN。 使用这个
 * 更严格的环境，应触发不完整的评估
 * 确认。
 *
 * 如果子分析器引发异常，它会贡献 HIGH
 * （失败关闭，记录）。 这可以防止损坏的分析仪默默地
 * 降低安全性。
 *
 * 示例：:
 *
 * 从 openhands.sdk.security 导入 (
 * EnsembleSecurityAnalyzer,
 * PatternSecurityAnalyzer,
 * PolicyRailSecurityAnalyzer,
 * ConfirmRisky,
 * SecurityRisk,
 * )
 *
 * 分析仪 = EnsembleSecurityAnalyzer(
 * 分析仪=[
 * PolicyRailSecurityAnalyzer(),
 * PatternSecurityAnalyzer(),
 * ]
 * )
 * 策略 = ConfirmRisky(阈值=SecurityRisk.MEDIUM)
 */
export type EnsembleSecurityAnalyzerOutputWritable = {
  /**
   * 分析仪
   *
   * 通过最大严重性组合评估的分析器
   */
  analyzers: Array<SecurityAnalyzerBaseOutputWritable>;
  /**
   * 种类
   */
  kind: 'EnsembleSecurityAnalyzer';
  /**
   * 传播未知
   *
   * 当 True 时，任何返回 UNKNOWN 的子项都会导致整体返回 UNKNOWN。 当 False（默认）时，如果任何子级返回具体级别，则 UNKNOWN 会被过滤掉。
   */
  propagate_unknown?: boolean;
};

export type EventWritable =
  | ({
      kind: 'openhands__agent_server__models__ServerErrorEvent-Output__1';
    } & ServerErrorEvent)
  | ({
      kind: 'openhands__sdk__event__acp_tool_call__ACPToolCallEvent-Output__1';
    } & AcpToolCallEvent)
  | ({
      kind: 'openhands__sdk__event__condenser__Condensation-Output__1';
    } & Condensation)
  | ({
      kind: 'openhands__sdk__event__condenser__CondensationRequest-Output__1';
    } & CondensationRequest)
  | ({
      kind: 'openhands__sdk__event__condenser__CondensationSummaryEvent-Output__1';
    } & CondensationSummaryEvent)
  | ({
      kind: 'openhands__sdk__event__conversation_error__ConversationErrorEvent-Output__1';
    } & ConversationErrorEvent)
  | ({
      kind: 'openhands__sdk__event__conversation_state__ConversationStateUpdateEvent-Output__1';
    } & ConversationStateUpdateEvent)
  | ({
      kind: 'openhands__sdk__event__hook_execution__HookExecutionEvent-Output__1';
    } & HookExecutionEvent)
  | ({
      kind: 'openhands__sdk__event__llm_completion_log__LLMCompletionLogEvent-Output__1';
    } & LlmCompletionLogEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__action__ActionEvent-Output__1';
    } & ActionEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__message__MessageEvent-Output__1';
    } & MessageEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__AgentErrorEvent-Output__1';
    } & AgentErrorEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__ObservationEvent-Output__1';
    } & ObservationEvent)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__observation__UserRejectObservation-Output__1';
    } & UserRejectObservation)
  | ({
      kind: 'openhands__sdk__event__llm_convertible__system__SystemPromptEvent-Output__1';
    } & SystemPromptEventWritable)
  | ({
      kind: 'openhands__sdk__event__security__SecurityAnalysisEvent-Output__1';
    } & SecurityAnalysisEvent)
  | ({
      kind: 'openhands__sdk__event__streaming_delta__StreamingDeltaEvent-Output__1';
    } & StreamingDeltaEvent)
  | ({
      kind: 'openhands__sdk__event__token__TokenEvent-Output__1';
    } & TokenEvent)
  | ({
      kind: 'openhands__sdk__event__user_action__InterruptEvent-Output__1';
    } & InterruptEvent)
  | ({
      kind: 'openhands__sdk__event__user_action__PauseEvent-Output__1';
    } & PauseEvent);

/**
 * FetchPluginRequest
 *
 * 请求正文严格获取插件而不安装它。
 */
export type FetchPluginRequestWritable = {
  /**
   * 参考号
   *
   * 分支、标记或提交
   */
  ref?: string | null;
  /**
   * 回购路径
   *
   * 存储库内的子目录路径（对于 monorepos）
   */
  repo_path?: string | null;
  /**
   * 机密
   *
   * 机密用于扩展源和参考中的 ${VAR} 占位符
   */
  secrets?: {
    [key: string]: SecretSourceInputWritable;
  };
  /**
   * 来源
   *
   * 插件git源
   */
  source: string;
  /**
   * 超时
   *
   * Git 超时秒
   */
  timeout?: number;
};

/**
 * FileEditorTool
 *
 * 自动初始化 FileEditorExecutor 的 ToolDefinition 子类。
 */
export type FileEditorToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'FileEditorTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * FinishTool
 *
 * 用于发出任务或对话完成信号的工具。
 */
export type FinishToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'FinishTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * GlobTool
 *
 * 自动初始化 GlobExecutor 的 ToolDefinition 子类。
 */
export type GlobToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'GlobTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * GraySwanAnalyzer
 *
 * 使用 GraySwan 的 Cygnal API 进行 AI 安全监控的安全分析器。
 *
 * 该分析器将对话历史记录和待处理操作发送到 GraySwan
 * Cygnal API 用于安全分析。 API 返回违规分数，即
 * 映射到 SecurityRisk 级别。
 *
 * 环境变量：
 * GRAYSWAN_API_KEY：GraySwan 身份验证所需的 API 键
 * GRAYSWAN_POLICY_ID：自定义 GraySwan 策略的可选策略 ID
 *
 * 示例：
 * >>> 从 openhands.sdk.security.grayswan 导入 GraySwanAnalyzer
 * >>> 分析器 = GraySwanAnalyzer()
 * >>> risk = analyzer.security_risk(action_event)
 */
export type GraySwanAnalyzerInputWritable = {
  /**
   * API 钥匙
   *
   * GraySwan API 键（通过 GRAYSWAN_API_KEY 环境变量）
   */
  api_key?: string | null;
  /**
   * API 网址
   *
   * GraySwan 辛格纳尔 API 端点
   */
  api_url?: string;
  /**
   * 历史限制
   *
   * 要包含为上下文的最近事件数
   */
  history_limit?: number;
  /**
   * 种类
   */
  kind?: 'GraySwanAnalyzer';
  /**
   * 低门槛
   *
   * LOW 分类的风险阈值（分数 <= 阈值）
   */
  low_threshold?: number;
  /**
   * 最大消息字符数
   *
   * 对话处理的最大字符数
   */
  max_message_chars?: number;
  /**
   * 中等门槛
   *
   * MEDIUM 分类的风险阈值（分数 <= 阈值）
   */
  medium_threshold?: number;
  /**
   * 策略 ID
   *
   * GraySwan 策略 ID（通过 GRAYSWAN_POLICY_ID 环境变量）
   */
  policy_id?: string | null;
  /**
   * 超时
   *
   * 请求超时（秒）
   */
  timeout?: number;
};

/**
 * GraySwanAnalyzer
 *
 * 使用 GraySwan 的 Cygnal API 进行 AI 安全监控的安全分析器。
 *
 * 该分析器将对话历史记录和待处理操作发送到 GraySwan
 * Cygnal API 用于安全分析。 API 返回违规分数，即
 * 映射到 SecurityRisk 级别。
 *
 * 环境变量：
 * GRAYSWAN_API_KEY：GraySwan 身份验证所需的 API 键
 * GRAYSWAN_POLICY_ID：自定义 GraySwan 策略的可选策略 ID
 *
 * 示例：
 * >>> 从 openhands.sdk.security.grayswan 导入 GraySwanAnalyzer
 * >>> 分析器 = GraySwanAnalyzer()
 * >>> risk = analyzer.security_risk(action_event)
 */
export type GraySwanAnalyzerOutputWritable = {
  /**
   * API 钥匙
   *
   * GraySwan API 键（通过 GRAYSWAN_API_KEY 环境变量）
   */
  api_key?: string | null;
  /**
   * API 网址
   *
   * GraySwan 辛格纳尔 API 端点
   */
  api_url?: string;
  /**
   * 历史限制
   *
   * 要包含为上下文的最近事件数
   */
  history_limit?: number;
  /**
   * 种类
   */
  kind: 'GraySwanAnalyzer';
  /**
   * 低门槛
   *
   * LOW 分类的风险阈值（分数 <= 阈值）
   */
  low_threshold?: number;
  /**
   * 最大消息字符数
   *
   * 对话处理的最大字符数
   */
  max_message_chars?: number;
  /**
   * 中等门槛
   *
   * MEDIUM 分类的风险阈值（分数 <= 阈值）
   */
  medium_threshold?: number;
  /**
   * 策略 ID
   *
   * GraySwan 策略 ID（通过 GRAYSWAN_POLICY_ID 环境变量）
   */
  policy_id?: string | null;
  /**
   * 超时
   *
   * 请求超时（秒）
   */
  timeout?: number;
};

/**
 * GrepTool
 *
 * 自动初始化 GrepExecutor 的 ToolDefinition 子类。
 */
export type GrepToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'GrepTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * InitRequest
 *
 * 运行时配置在 /api/init 时间交付。
 *
 * 每个字段都是可选的，并且会覆盖休眠中的等效字段
 * ``Config``. 未提供的字段保留服务器构建时的值
 * with（通常来自 pod 启动时的环境变量）。 可重写的集合
 * 领域故意狭窄——它涵盖了今天的价值观
 * “env-var Shape”并且必须针对每个用户进行更改，而不是在映像构建时更改
 * 配置（Python deps、插件集等），它保持绑定到
 * 温水池的味道。
 */
export type InitRequestWritable = {
  /**
   * 允许 Cors 起源
   *
   * CORS origins 添加到现有的本地主机白名单。
   */
  allow_cors_origins?: Array<string> | null;
  /**
   * Bash 活动目录
   *
   * bash 事件所在的目录已持久化。 通常位于已安装的用户内部工作区。
   */
  bash_events_dir?: string | null;
  /**
   * 对话工作树根
   *
   * 对话 git 工作树的根目录。 覆盖它以指向已安装的用户工作区。
   */
  conversation_worktree_root?: string | null;
  /**
   * 对话路径
   *
   * 对话所在目录为已持久化。 覆盖它以指向已安装的用户工作区。
   */
  conversations_path?: string | null;
  /**
   * 环境
   *
   * 在会话服务开始之前进行设置的处理环境变量。 对于被工具消耗的凭据很有用 (e.g. GITHUB_TOKEN). 这些适用于``os.environ.update``； 现有值被覆盖。
   */
  env?: {
    [key: string]: string;
  } | null;
  /**
   * 最多并发次运行
   *
   * 覆盖对话步骤并发限制。
   */
  max_concurrent_runs?: number | null;
  /**
   * 上一个机密键
   *
   * secret_key 的早期值（或它回退到的第一个 session_api_key 的值），仅用于解密保存在其下的值； 下次保存时，它们将使用当前密钥重新加密。
   */
  previous_secret_keys?: Array<string> | null;
  /**
   * 机密钥匙
   *
   * 对称机密用于加密已持久化机密。 如果未提供，则回退到第一个 session_api_key（与默认配置行为匹配）。
   */
  secret_key?: string | null;
  /**
   * 会话 API 键
   *
   * 每用户会话 API 键。 如果提供，所有后续 /api* 请求都必须通过 X-Session-API-Key 标头使用这些密钥之一进行身份验证。
   */
  session_api_keys?: Array<string> | null;
  /**
   * 此 Pod 的产品分析政策。 如果没有这个，暖池 Pod 会保留其启动时使用的任何模式（通常“禁用”），因此需要遥测的部署必须在此处提供它。
   */
  telemetry?: TelemetrySpecWritable | null;
  /**
   * 网址
   *
   * 可访问此服务器的外部 URL，用于根路径计算。 仅当尚未在休眠配置中设置时才受到尊重。
   */
  web_url?: string | null;
  /**
   * Webhook
   *
   * 每个用户 Webhook (e.g. 对于流式传输事件返回）。
   */
  webhooks?: Array<WebhookSpec> | null;
};

/**
 * InvokeSkillTool
 *
 * 用于显式调用渐进式披露技能的内置工具。
 */
export type InvokeSkillToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'InvokeSkillTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

export type JsonValueWritable =
  | string
  | number
  | number
  | boolean
  | Array<JsonValueWritable>
  | {
      [key: string]: JsonValueWritable;
    }
  | null;

/**
 * LLM
 *
 * OpenHands 智能体的语言模型接口。
 *
 * LLM类提供了与各种交互的统一接口
 * 通过 LiteLLM 库的语言模型。 它处理模型配置，
 * API 身份验证、重试逻辑和工具调用功能。
 *
 * 属性：
 * model：型号名称（e.g.，“gpt-5.6”）。
 * api_key：API键用于身份验证。
 * base_url：自定义 API 基础 URL。
 * num_retries：失败请求的重试次尝试次数。
 * 超时：请求超时（以秒为单位）。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM
 * 从 Pydantic 导入 SecretStr
 *
 * 勒姆 = LLM(
 * 型号=“gpt-5.6”，
 * api_key=SecretStr("你的-API-密钥"),
 * usage_id="我的-智能体"
 * )
 * # 与智能体或对话一起使用
 * ```
 */
export type LlmInputWritable = {
  /**
   * API 钥匙
   *
   * API 键。
   */
  api_key?: string | string | null;
  /**
   * API 模式
   *
   * LLM API 端点模式。 'auto' 从模型元数据和 SDK 回退方案解析； 使用“聊天”或“响应”来覆盖代理别名和新发布模型的端点选择。
   */
  api_mode?: 'auto' | 'chat' | 'responses';
  /**
   * API 版本
   *
   * API 版本（e.g.，Azure）。
   */
  api_version?: string | null;
  /**
   * 验证类型
   *
   * 身份验证模式为LLM。
   */
  auth_type?: 'api_key' | 'subscription';
  /**
   * AWS 访问密钥 ID
   */
  aws_access_key_id?: string | string | null;
  /**
   * AWS 基岩运行时端点
   */
  aws_bedrock_runtime_endpoint?: string | null;
  /**
   * AWS 配置文件名称
   */
  aws_profile_name?: string | null;
  /**
   * AWS 区域名称
   */
  aws_region_name?: string | null;
  /**
   * AWS 角色名称
   */
  aws_role_name?: string | null;
  /**
   * AWS 机密访问密钥
   */
  aws_secret_access_key?: string | string | null;
  /**
   * AWS 会话名称
   */
  aws_session_name?: string | null;
  /**
   * 哦会话令牌
   */
  aws_session_token?: string | string | null;
  /**
   * 基本网址
   *
   * 定制基地URL。
   */
  base_url?: string | null;
  /**
   * 缓存提示词
   *
   * 启用提示词的缓存。
   */
  caching_prompt?: boolean;
  /**
   * 能力覆盖
   *
   * 显式模型功能覆盖。 支持的键包括 supports_reasoning_effort、thinking_mode（自适应、手动、None 或未知）、supports_sampling_params、supports_prompt_cache、supports_stop_words、supports_responses_api、supports_vision 和 supports_prompt_cache_retention。 覆盖优先于 LiteLLM 元数据和 SDK 回退方案。
   */
  capability_overrides?: {
    [key: string]: boolean | string;
  };
  /**
   * 自定义分词器
   *
   * 用于 token 计数的自定义分词器。
   */
  custom_tokenizer?: string | null;
  /**
   * 禁用停用词
   *
   * 禁用停用词的使用。
   */
  disable_stop_word?: boolean | null;
  /**
   * 禁用视力
   *
   * 如果模型具有视觉功能，则此选项允许禁用图像处理（对于降低成本很有用）。
   */
  disable_vision?: boolean | null;
  /**
   * 删除参数
   */
  drop_params?: boolean;
  /**
   * 启用加密推理
   *
   * 如果是 True，则要求在响应 API 中包含 ['reasoning.encrypted_content']。
   */
  enable_encrypted_reasoning?: boolean;
  /**
   * 扩展思维预算
   *
   * 遗留词元预算模型确认使用手册Anthropic扩展思维。 自适应思维模型被忽略。 对于新集成，首选 reasoning_effort。
   */
  extended_thinking_budget?: number | null;
  /**
   * 额外标头
   *
   * 用于转发到 LiteLLM 请求的可选 HTTP 标头。
   */
  extra_headers?: {
    [key: string]: string;
  } | null;
  /**
   * 回退方案选项：尝试在临时失败时使用备用 LLMs。 FallbackStrategy(fallback_llms=[...]).序列化不包括。 加载后必须重新配置。
   */
  fallback_strategy?: FallbackStrategy | null;
  /**
   * 强制字符串序列化器
   *
   * 发送到 LLM API 时强制使用字符串内容序列化器。 如果为 None（默认），则根据型号自动检测。 对于不支持列表内容的提供者很有用，例如 HuggingFace 和 Groq。
   */
  force_string_serializer?: boolean | null;
  /**
   * 内嵌图像 URL
   *
   * 如果 True, fetch any http(s) image URL 在发送的消息中和消息内嵌入它作为 base64 ``data:``  URL 在发送之前。 如果 None (默认)，根据模型自动检测（某些） APIs 例如 Moonshot 的公共 Kimi 端点拒绝 URL-需要格式化后的图片，且要求使用 base64。 在通过隐藏底层提供者的代理别名到达模型时，显式设置此值e.g. ``litellm_proxy/<custom-alias>``). 仅在时才运行 ``vision_is_active()`` 是 True因此，别名仍然必须被视作具备视觉能力的 SDK feature 注册表或代理模型元数据。
   */
  inline_image_urls?: boolean | null;
  /**
   * 每 token 的投入成本
   *
   * 每个输入的成本 token。 这将在用户日志中可用。
   */
  input_cost_per_token?: number | null;
  /**
   * LiteLLM 额外本体
   *
   * 传递给的附加键值对 LiteLLM's extra_body 参数。 这很有用，用于自定义推理端点需要配置参数、路由或高级功能的额外参数。 注意：并非所有 LLM 提供商支持 extra_body 参数。 一些提供商 (e.g., OpenAI) 可以拒绝未识别的选项请求。 这通常由：- 支持 LiteLLM 代理服务器（路由元数据、追踪） - vLLM 端点 (return_token_ids, etc.) - Custom inference clusters Examples: - Proxy routing: {'trace_version'version': '1.0.0', 'tags': '' ['智能体我的-智能体']} - vLLM features: {'return_token_ids': True}
   */
  litellm_extra_body?: {
    [key: string]: unknown;
  };
  /**
   * 记录完成情况
   *
   * 启用完成记录。
   */
  log_completions?: boolean;
  /**
   * 记录完成文件夹
   *
   * 将 LLM 个完成情况记录到的文件夹。 如果 log_completions 为 True，则为必填项。
   */
  log_completions_folder?: string;
  /**
   * 最大输入 token
   *
   * 最大输入数量token。 请注意，当前未使用该值，运行时的值实际上是 OpenAI 中的总计 token（e.g.128,000 token for GPT-4）。
   */
  max_input_tokens?: number | null;
  /**
   * 最大消息字符数
   *
   * 发送到 LLM 的每个事件/内容的大约最大字符数。
   */
  max_message_chars?: number;
  /**
   * 最大输出 token
   *
   * 最大输出数量token。 这被发送到LLM。
   */
  max_output_tokens?: number | null;
  /**
   * 型号
   *
   * 型号名称。
   */
  model?: string;
  /**
   * 型号规范名称
   *
   * 用于特征注册表查找的可选规范模型名称。 OpenHands SDK 维护一个模型功能注册表，将模型名称映射到功能（e.g.、视觉支持、提示词缓存、响应 API 支持）。 当使用代理或别名的模型标识时，将此字段设置为可唯一标识的模型名称（e.g，'openai/gpt-4o'）以确保正确的能力检测。 如果未提供，“模型”字段将用于功能查找。
   */
  model_canonical_name?: string | null;
  /**
   * 原生工具调用
   *
   * 是否使用原生工具调用。
   */
  native_tool_calling?: boolean;
  /**
   * 数量重试
   */
  num_retries?: number;
  /**
   * 奥拉马基地网址
   */
  ollama_base_url?: string | null;
  /**
   * Openrouter应用程序名称
   */
  openrouter_app_name?: string;
  /**
   * Openrouter 站点 URL
   */
  openrouter_site_url?: string;
  /**
   * 每 token 的输出成本
   *
   * 每个输出的成本 token。 这将在用户日志中可用。
   */
  output_cost_per_token?: number | null;
  /**
   * 提示词缓存保留
   *
   * 提示词缓存的保留策略。 仅针对受支持的型号发送（GPT-5+ 和 GPT-4.1，不包括 Azure 部署）； 明确地为所有其他人剥离。
   */
  prompt_cache_retention?: string | null;
  /**
   * 提供商连接 ID
   *
   * 可选的提供程序连接，每次加载此 LLM 配置文件（使用时读取）时，都会解析并应用其共享 API 密钥和基 URL。 设置后，配置文件不存储其自己的内联 api_key 或 base_url。
   */
  provider_connection_id?: string | null;
  /**
   * 推理努力
   *
   * 提供者中立的推理工作。 常见的值包括 'None'、'最小'、'低'、'中'、'高'、'x高' 和 '最大'。 SDK 接受未来的提供者值并让 LiteLLM 翻译它们。
   */
  reasoning_effort?: 'low' | 'medium' | 'high' | 'xhigh' | 'none' | null;
  /**
   * 推理总结
   *
   * 推理摘要的详细程度。 这是一个字符串，可以是“auto”、“concise”或“detailed”之一。 需要经过验证的 OpenAI 组织。 仅在明确设置时发送。
   */
  reasoning_summary?: 'auto' | 'concise' | 'detailed' | null;
  /**
   * 重试最长等待时间
   */
  retry_max_wait?: number;
  /**
   * 重试最短等待时间
   */
  retry_min_wait?: number;
  /**
   * 重试乘数
   */
  retry_multiplier?: number;
  /**
   * 种子
   *
   * 用于生成随机数的种子。
   */
  seed?: number | null;
  /**
   * 串流
   *
   * 启用来自 LLM 的流式传输响应。 启用后，将为 token 的每个块调用 .completions 和 .responses 中提供的 `on_token` 回调。
   */
  stream?: boolean;
  /**
   * 流空闲超时
   *
   * 异步流式传输响应中块之间的最大秒数。 默认为300s（5分钟）； 设置为 None 禁用。
   */
  stream_idle_timeout?: number | null;
  /**
   * 订阅供应商
   *
   * 用于订阅支持的 LLM 访问的订阅提供商。
   */
  subscription_vendor?: 'openai' | null;
  /**
   * 温度
   *
   * 用于生成响应的采样温度。 默认为 None（使用提供商默认温度）。 设置为 0.0 以获得确定性输出，或设置为更高值 (0.7-1.0) 以获得更有创意的响应。
   */
  temperature?: number | null;
  /**
   * 超时
   *
   * HTTP 和硬每次尝试超时（以秒为单位）。 默认值为 300 秒（5 分钟）。 设置为 None 以禁用硬超时。
   */
  timeout?: number | null;
  /**
   * 前K
   */
  top_k?: number | null;
  /**
   * 顶P
   *
   * 核采样参数。 默认为 None（使用提供程序默认值）。 设置为 0 到 1 之间的值以控制输出的多样性。
   */
  top_p?: number | null;
  /**
   * 使用 ID
   *
   * LLM 的唯一使用标识符。 用于注册表查找、遥测和支出跟踪。
   */
  usage_id?: string;
};

/**
 * LLM
 *
 * OpenHands 智能体的语言模型接口。
 *
 * LLM类提供了与各种交互的统一接口
 * 通过 LiteLLM 库的语言模型。 它处理模型配置，
 * API 身份验证、重试逻辑和工具调用功能。
 *
 * 属性：
 * model：型号名称（e.g.，“gpt-5.6”）。
 * api_key：API键用于身份验证。
 * base_url：自定义 API 基础 URL。
 * num_retries：失败请求的重试次尝试次数。
 * 超时：请求超时（以秒为单位）。
 *
 * 示例：
 * ```Python
 * 从 openhands.sdk 导入 LLM
 * 从 Pydantic 导入 SecretStr
 *
 * 勒姆 = LLM(
 * 型号=“gpt-5.6”，
 * api_key=SecretStr("你的-API-密钥"),
 * usage_id="我的-智能体"
 * )
 * # 与智能体或对话一起使用
 * ```
 */
export type LlmOutputWritable = {
  /**
   * API 钥匙
   *
   * API 键。
   */
  api_key?: string | string | null;
  /**
   * API 模式
   *
   * LLM API 端点模式。 'auto' 从模型元数据和 SDK 回退方案解析； 使用“聊天”或“响应”来覆盖代理别名和新发布模型的端点选择。
   */
  api_mode?: 'auto' | 'chat' | 'responses';
  /**
   * API 版本
   *
   * API 版本（e.g.，Azure）。
   */
  api_version?: string | null;
  /**
   * 验证类型
   *
   * 身份验证模式为LLM。
   */
  auth_type?: 'api_key' | 'subscription';
  /**
   * AWS 访问密钥 ID
   */
  aws_access_key_id?: string | string | null;
  /**
   * AWS 基岩运行时端点
   */
  aws_bedrock_runtime_endpoint?: string | null;
  /**
   * AWS 配置文件名称
   */
  aws_profile_name?: string | null;
  /**
   * AWS 区域名称
   */
  aws_region_name?: string | null;
  /**
   * AWS 角色名称
   */
  aws_role_name?: string | null;
  /**
   * AWS 机密访问密钥
   */
  aws_secret_access_key?: string | string | null;
  /**
   * AWS 会话名称
   */
  aws_session_name?: string | null;
  /**
   * 哦会话令牌
   */
  aws_session_token?: string | string | null;
  /**
   * 基本网址
   *
   * 定制基地URL。
   */
  base_url?: string | null;
  /**
   * 缓存提示词
   *
   * 启用提示词的缓存。
   */
  caching_prompt?: boolean;
  /**
   * 能力覆盖
   *
   * 显式模型功能覆盖。 支持的键包括 supports_reasoning_effort、thinking_mode（自适应、手动、None 或未知）、supports_sampling_params、supports_prompt_cache、supports_stop_words、supports_responses_api、supports_vision 和 supports_prompt_cache_retention。 覆盖优先于 LiteLLM 元数据和 SDK 回退方案。
   */
  capability_overrides?: {
    [key: string]: boolean | string;
  };
  /**
   * 自定义分词器
   *
   * 用于 token 计数的自定义分词器。
   */
  custom_tokenizer?: string | null;
  /**
   * 禁用停用词
   *
   * 禁用停用词的使用。
   */
  disable_stop_word?: boolean | null;
  /**
   * 禁用视力
   *
   * 如果模型具有视觉功能，则此选项允许禁用图像处理（对于降低成本很有用）。
   */
  disable_vision?: boolean | null;
  /**
   * 删除参数
   */
  drop_params?: boolean;
  /**
   * 启用加密推理
   *
   * 如果是 True，则要求在响应 API 中包含 ['reasoning.encrypted_content']。
   */
  enable_encrypted_reasoning?: boolean;
  /**
   * 扩展思维预算
   *
   * 遗留词元预算模型确认使用手册Anthropic扩展思维。 自适应思维模型被忽略。 对于新集成，首选 reasoning_effort。
   */
  extended_thinking_budget?: number | null;
  /**
   * 额外标头
   *
   * 用于转发到 LiteLLM 请求的可选 HTTP 标头。
   */
  extra_headers?: {
    [key: string]: string;
  } | null;
  /**
   * 强制字符串序列化器
   *
   * 发送到 LLM API 时强制使用字符串内容序列化器。 如果为 None（默认），则根据型号自动检测。 对于不支持列表内容的提供者很有用，例如 HuggingFace 和 Groq。
   */
  force_string_serializer?: boolean | null;
  /**
   * 内嵌图像 URL
   *
   * 如果 True, fetch any http(s) image URL 在发送的消息中和消息内嵌入它作为 base64 ``data:``  URL 在发送之前。 如果 None (默认)，根据模型自动检测（某些） APIs 例如 Moonshot 的公共 Kimi 端点拒绝 URL-需要格式化后的图片，且要求使用 base64。 在通过隐藏底层提供者的代理别名到达模型时，显式设置此值e.g. ``litellm_proxy/<custom-alias>``). 仅在时才运行 ``vision_is_active()`` 是 True因此，别名仍然必须被视作具备视觉能力的 SDK feature 注册表或代理模型元数据。
   */
  inline_image_urls?: boolean | null;
  /**
   * 每 token 的投入成本
   *
   * 每个输入的成本 token。 这将在用户日志中可用。
   */
  input_cost_per_token?: number | null;
  /**
   * LiteLLM 额外本体
   *
   * 传递给的附加键值对 LiteLLM's extra_body 参数。 这很有用，用于自定义推理端点需要配置参数、路由或高级功能的额外参数。 注意：并非所有 LLM 提供商支持 extra_body 参数。 一些提供商 (e.g., OpenAI) 可以拒绝未识别的选项请求。 这通常由：- 支持 LiteLLM 代理服务器（路由元数据、追踪） - vLLM 端点 (return_token_ids, etc.) - Custom inference clusters Examples: - Proxy routing: {'trace_version'version': '1.0.0', 'tags': '' ['智能体我的-智能体']} - vLLM features: {'return_token_ids': True}
   */
  litellm_extra_body?: {
    [key: string]: unknown;
  };
  /**
   * 记录完成情况
   *
   * 启用完成记录。
   */
  log_completions?: boolean;
  /**
   * 记录完成文件夹
   *
   * 将 LLM 个完成情况记录到的文件夹。 如果 log_completions 为 True，则为必填项。
   */
  log_completions_folder?: string;
  /**
   * 最大输入 token
   *
   * 最大输入数量token。 请注意，当前未使用该值，运行时的值实际上是 OpenAI 中的总计 token（e.g.128,000 token for GPT-4）。
   */
  max_input_tokens?: number | null;
  /**
   * 最大消息字符数
   *
   * 发送到 LLM 的每个事件/内容的大约最大字符数。
   */
  max_message_chars?: number;
  /**
   * 最大输出 token
   *
   * 最大输出数量token。 这被发送到LLM。
   */
  max_output_tokens?: number | null;
  /**
   * 型号
   *
   * 型号名称。
   */
  model?: string;
  /**
   * 型号规范名称
   *
   * 用于特征注册表查找的可选规范模型名称。 OpenHands SDK 维护一个模型功能注册表，将模型名称映射到功能（e.g.、视觉支持、提示词缓存、响应 API 支持）。 当使用代理或别名的模型标识时，将此字段设置为可唯一标识的模型名称（e.g，'openai/gpt-4o'）以确保正确的能力检测。 如果未提供，“模型”字段将用于功能查找。
   */
  model_canonical_name?: string | null;
  /**
   * 原生工具调用
   *
   * 是否使用原生工具调用。
   */
  native_tool_calling?: boolean;
  /**
   * 数量重试
   */
  num_retries?: number;
  /**
   * 奥拉马基地网址
   */
  ollama_base_url?: string | null;
  /**
   * Openrouter应用程序名称
   */
  openrouter_app_name?: string;
  /**
   * Openrouter 站点 URL
   */
  openrouter_site_url?: string;
  /**
   * 每 token 的输出成本
   *
   * 每个输出的成本 token。 这将在用户日志中可用。
   */
  output_cost_per_token?: number | null;
  /**
   * 提示词缓存保留
   *
   * 提示词缓存的保留策略。 仅针对受支持的型号发送（GPT-5+ 和 GPT-4.1，不包括 Azure 部署）； 明确地为所有其他人剥离。
   */
  prompt_cache_retention?: string | null;
  /**
   * 提供商连接 ID
   *
   * 可选的提供程序连接，每次加载此 LLM 配置文件（使用时读取）时，都会解析并应用其共享 API 密钥和基 URL。 设置后，配置文件不存储其自己的内联 api_key 或 base_url。
   */
  provider_connection_id?: string | null;
  /**
   * 推理努力
   *
   * 提供者中立的推理工作。 常见的值包括 'None'、'最小'、'低'、'中'、'高'、'x高' 和 '最大'。 SDK 接受未来的提供者值并让 LiteLLM 翻译它们。
   */
  reasoning_effort?: 'low' | 'medium' | 'high' | 'xhigh' | 'none' | null;
  /**
   * 推理总结
   *
   * 推理摘要的详细程度。 这是一个字符串，可以是“auto”、“concise”或“detailed”之一。 需要经过验证的 OpenAI 组织。 仅在明确设置时发送。
   */
  reasoning_summary?: 'auto' | 'concise' | 'detailed' | null;
  /**
   * 重试最长等待时间
   */
  retry_max_wait?: number;
  /**
   * 重试最短等待时间
   */
  retry_min_wait?: number;
  /**
   * 重试乘数
   */
  retry_multiplier?: number;
  /**
   * 种子
   *
   * 用于生成随机数的种子。
   */
  seed?: number | null;
  /**
   * 串流
   *
   * 启用来自 LLM 的流式传输响应。 启用后，将为 token 的每个块调用 .completions 和 .responses 中提供的 `on_token` 回调。
   */
  stream?: boolean;
  /**
   * 流空闲超时
   *
   * 异步流式传输响应中块之间的最大秒数。 默认为300s（5分钟）； 设置为 None 禁用。
   */
  stream_idle_timeout?: number | null;
  /**
   * 订阅供应商
   *
   * 用于订阅支持的 LLM 访问的订阅提供商。
   */
  subscription_vendor?: 'openai' | null;
  /**
   * 温度
   *
   * 用于生成响应的采样温度。 默认为 None（使用提供商默认温度）。 设置为 0.0 以获得确定性输出，或设置为更高值 (0.7-1.0) 以获得更有创意的响应。
   */
  temperature?: number | null;
  /**
   * 超时
   *
   * HTTP 和硬每次尝试超时（以秒为单位）。 默认值为 300 秒（5 分钟）。 设置为 None 以禁用硬超时。
   */
  timeout?: number | null;
  /**
   * 前K
   */
  top_k?: number | null;
  /**
   * 顶P
   *
   * 核采样参数。 默认为 None（使用提供程序默认值）。 设置为 0 到 1 之间的值以控制输出的多样性。
   */
  top_p?: number | null;
  /**
   * 使用 ID
   *
   * LLM 的唯一使用标识符。 用于注册表查找、遥测和支出跟踪。
   */
  usage_id?: string;
};

/**
 * LLMSummarizingCondenser
 *
 * 基于 LLM 的上下文压缩器总结了被遗忘的事件。
 *
 * 使用独立的 LLM（存储在 `llm` 属性中）来生成摘要
 * 被遗忘的事件。 传递给 condense() 的可选 `agent_llm` 参数是
 * LLM 被智能体用于 token 计数目的，并且您不应该假设
 * 与上下文压缩器中定义的相同。
 */
export type LlmSummarizingCondenserInputWritable = {
  /**
   * 硬上下文重置上下文缩放
   */
  hard_context_reset_context_scaling?: number;
  /**
   * 硬上下文重置最大重试
   */
  hard_context_reset_max_retries?: number;
  /**
   * 保持第一
   */
  keep_first?: number;
  /**
   * 种类
   */
  kind?: 'LLMSummarizingCondenser';
  llm: LlmInputWritable;
  /**
   * 最大尺寸
   */
  max_size?: number;
  /**
   * 最大 token
   */
  max_tokens?: number | null;
  /**
   * 最低进度
   */
  minimum_progress?: number;
};

/**
 * LLMSummarizingCondenser
 *
 * 基于 LLM 的上下文压缩器总结了被遗忘的事件。
 *
 * 使用独立的 LLM（存储在 `llm` 属性中）来生成摘要
 * 被遗忘的事件。 传递给 condense() 的可选 `agent_llm` 参数是
 * LLM 被智能体用于 token 计数目的，并且您不应该假设
 * 与上下文压缩器中定义的相同。
 */
export type LlmSummarizingCondenserOutputWritable = {
  /**
   * 硬上下文重置上下文缩放
   */
  hard_context_reset_context_scaling?: number;
  /**
   * 硬上下文重置最大重试
   */
  hard_context_reset_max_retries?: number;
  /**
   * 保持第一
   */
  keep_first?: number;
  /**
   * 种类
   */
  kind: 'LLMSummarizingCondenser';
  llm: LlmOutputWritable;
  /**
   * 最大尺寸
   */
  max_size?: number;
  /**
   * 最大 token
   */
  max_tokens?: number | null;
  /**
   * 最低进度
   */
  minimum_progress?: number;
};

/**
 * ListDirectoryTool
 *
 * 用于列出带有元数据的目录内容的工具。
 */
export type ListDirectoryToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ListDirectoryTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * MCPApiKeyAuthCredential
 */
export type McpApiKeyAuthCredentialInputWritable = {
  /**
   * 标头名称
   */
  header_name?: string | null;
  /**
   * 策略
   */
  strategy: 'api_key';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * MCPBasicAuthCredential
 */
export type McpBasicAuthCredentialInputWritable = {
  /**
   * 密码
   */
  password?: string | null;
  /**
   * 策略
   */
  strategy: 'basic';
  /**
   * 用户名
   */
  username: string;
};

/**
 * MCPBearerAuthCredential
 */
export type McpBearerAuthCredentialInputWritable = {
  /**
   * 策略
   */
  strategy: 'bearer';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * MCPConfigPatch
 *
 * 稀疏MCP地图补丁； null 映射值删除该指定服务器。
 */
export type McpConfigPatchWritable = {
  [key: string]: McpServerPatchWritable | null;
};

/**
 * MCPHeaderAuthCredential
 */
export type McpHeaderAuthCredentialInputWritable = {
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 策略
   */
  strategy: 'header';
};

/**
 * MCPOAuthAuthCredential
 */
export type McpoAuthAuthCredentialInputWritable = {
  authentication?: McpoAuthAuthenticationInputWritable | null;
  state?: McpoAuthStateInputWritable | null;
  /**
   * 策略
   */
  strategy: 'oauth2';
};

/**
 * MCPOAuthAuthentication
 */
export type McpoAuthAuthenticationInputWritable = {
  /**
   * 附加客户端元数据
   */
  additional_client_metadata?: {
    [key: string]: unknown;
  } | null;
  /**
   * 客户端认证方式
   */
  client_auth_method?:
    'none' | 'client_secret_post' | 'client_secret_basic' | 'private_key_jwt' | null;
  /**
   * 客户端 ID
   */
  client_id?: string | null;
  /**
   * 客户端元数据 URL
   */
  client_metadata_url?: string | null;
  /**
   * 客户名称
   */
  client_name?: string | null;
  /**
   * 客户机密
   */
  client_secret?: string | null;
  /**
   * 范围
   */
  scopes?: string | Array<string> | null;
  /**
   * 类型
   */
  type: 'oauth';
};

/**
 * MCPOAuthClientInfoState
 */
export type McpoAuthClientInfoStateInputWritable = {
  /**
   * 客户机密
   */
  client_secret?: string | null;
  [key: string]: unknown;
};

/**
 * MCPOAuthState
 */
export type McpoAuthStateInputWritable = {
  client_info?: McpoAuthClientInfoStateInputWritable | null;
  /**
   * token 到期时间
   */
  token_expires_at?: number | null;
  tokens?: McpoAuthTokenStateInputWritable | null;
};

/**
 * MCPOAuthTokenState
 */
export type McpoAuthTokenStateInputWritable = {
  /**
   * 访问令牌
   */
  access_token?: string | null;
  /**
   * 刷新令牌
   */
  refresh_token?: string | null;
  [key: string]: unknown;
};

/**
 * MCPServer
 *
 * 设置 DataModel 中的一台 MCP 服务器。
 */
export type McpServerInputWritable = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInputWritable)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInputWritable)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInputWritable)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInputWritable)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInputWritable)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 该服务器是否暴露于智能体。 一个已禁用的服务器仍然完全配置，包括其机密，但在MCP工具创建时和服务器转发到ACP 子进程时被跳过。
   */
  enabled?: boolean;
  /**
   * 环境
   */
  env?: {
    [key: string]: string;
  } | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  } | null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPServerPatch
 *
 * 适用于一台已持久化 MCP 服务器的稀疏 RFC 7386 合并补丁。
 */
export type McpServerPatchWritable = {
  /**
   * 参数
   */
  args?: Array<string> | null;
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInputWritable)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInputWritable)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInputWritable)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInputWritable)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInputWritable)
    | null;
  /**
   * 命令
   */
  command?: string | null;
  /**
   * 西德
   */
  cwd?: string | null;
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 启用
   *
   * 关闭服务器 (False) 或重新打开 (True)，而不触及其配置的 REST。 null 清除覆盖，从而恢复规范默认值（启用）。
   */
  enabled?: boolean | null;
  /**
   * 环境
   */
  env?: {
    [key: string]: string | null;
  } | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string | null;
  } | null;
  /**
   * 图标
   */
  icon?: string | null;
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 传输层
   */
  transport?: 'stdio' | 'http' | 'sse' | 'streamable-http' | null;
  /**
   * 网址
   */
  url?: string | null;
};

/**
 * MCPTestRequest
 *
 * ``POST /api/mcp/test`` 的主体。
 */
export type McpTestRequestWritable = {
  /**
   * 名称
   *
   * 用于临时 MCP 服务器映射内的服务器的名称。 仅影响错误消息——不需要匹配任何已持久化设置。
   */
  name?: string;
  /**
   * 服务器
   */
  server:
    | ({
        type: 'stdio';
      } & StdioMcpServerSpec)
    | ({
        type: 'http' | 'shttp' | 'sse' | 'streamable-http';
      } & RemoteMcpServerSpecWritable);
  /**
   * 超时
   *
   * 等待连接+工具/列表完成的秒数。
   */
  timeout?: number;
  /**
   * 列出成功后要调用的可选只读工具，以便调用者可以验证凭据服务器仅执行工具调用。 其结果在 `tool_result` 中逐字报告，不影响 `ok`。
   */
  tool_call?: McpToolCallSpec | null;
};

/**
 * MCPToolDefinition
 *
 * MCP 包装 MCP 客户端并提供工具功能的工具。
 */
export type McpToolDefinitionWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'MCPToolDefinition';
  /**
   * MCP 工具定义。
   */
  mcp_tool: McpTypesTool;
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * PipelineCondenser
 *
 * 按顺序应用上下文压缩器序列的上下文压缩器。
 *
 * 所有上下文压缩器主要由它们的 `condense` 方法定义，该方法采用
 * `View` 和一个可选的 `agent_llm` 参数，返回一个新的 `View` 或一个
 * `Condensation` 事件。 这意味着我们可以通过以下方式将多个上下文压缩器链接在一起
 * 如果任何上下文压缩器返回 `Condensation`，则传递 `View` 并提前退出。
 *
 * 例如：
 *
 * # 使用管道上下文压缩器将多个其他上下文压缩器链接在一起
 * 上下文压缩器 = PipelineCondenser(上下文压缩器=[
 * CondenserA(...),
 * CondenserB(...),
 * CondenserC(...),
 * ])
 *
 * 结果= condenser.condense（视图，agent_llm=agent_llm）
 *
 * # 在没有管道上下文压缩器的情况下做同样的事情需要更多样板
 * # 对于单子链
 * other_result = 查看
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserA(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserB(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserC(...).condense(other_result, agent_llm=agent_llm)
 *
 * 断言结果 == other_result
 */
export type PipelineCondenserInputWritable = {
  /**
   * 上下文压缩器
   */
  condensers: Array<CondenserBaseInputWritable>;
  /**
   * 种类
   */
  kind?: 'PipelineCondenser';
};

/**
 * PipelineCondenser
 *
 * 按顺序应用上下文压缩器序列的上下文压缩器。
 *
 * 所有上下文压缩器主要由它们的 `condense` 方法定义，该方法采用
 * `View` 和一个可选的 `agent_llm` 参数，返回一个新的 `View` 或一个
 * `Condensation` 事件。 这意味着我们可以通过以下方式将多个上下文压缩器链接在一起
 * 如果任何上下文压缩器返回 `Condensation`，则传递 `View` 并提前退出。
 *
 * 例如：
 *
 * # 使用管道上下文压缩器将多个其他上下文压缩器链接在一起
 * 上下文压缩器 = PipelineCondenser(上下文压缩器=[
 * CondenserA(...),
 * CondenserB(...),
 * CondenserC(...),
 * ])
 *
 * 结果= condenser.condense（视图，agent_llm=agent_llm）
 *
 * # 在没有管道上下文压缩器的情况下做同样的事情需要更多样板
 * # 对于单子链
 * other_result = 查看
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserA(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserB(...).condense(other_result, agent_llm=agent_llm)
 *
 * 如果isinstance(other_result, View)：
 * other_result = CondenserC(...).condense(other_result, agent_llm=agent_llm)
 *
 * 断言结果 == other_result
 */
export type PipelineCondenserOutputWritable = {
  /**
   * 上下文压缩器
   */
  condensers: Array<CondenserBaseOutputWritable>;
  /**
   * 种类
   */
  kind: 'PipelineCondenser';
};

/**
 * PlanningFileEditorTool
 *
 * 具有只读、仅限 edit-PLAN.md 访问权限的规划文件编辑器工具。
 */
export type PlanningFileEditorToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'PlanningFileEditorTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * ProviderConnectionCreateRequest
 */
export type ProviderConnectionCreateRequestWritable = {
  /**
   * API 钥匙
   */
  api_key: string;
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 显示名称
   */
  display_name: string;
  /**
   * 提供商
   */
  provider?: string;
};

/**
 * ProviderConnectionUpdateRequest
 */
export type ProviderConnectionUpdateRequestWritable = {
  /**
   * API 钥匙
   */
  api_key?: string | null;
  /**
   * 基本网址
   */
  base_url?: string | null;
  /**
   * 显示名称
   */
  display_name?: string | null;
  /**
   * 提供商
   */
  provider?: string | null;
};

/**
 * ReadFileTool
 *
 * 用于读取文件内容并支持分页的工具。
 */
export type ReadFileToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ReadFileTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * RemoteMCPServer
 *
 * 传统远程 MCP 服务器规范已被公众接受 REST API。
 */
export type RemoteMcpServerWritable = {
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInputWritable)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInputWritable)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInputWritable)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInputWritable)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInputWritable)
    | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 类型
   */
  type: 'http' | 'shttp' | 'streamable-http' | 'sse';
  /**
   * 网址
   */
  url: string;
};

/**
 * SaveProfileRequest
 */
export type SaveProfileRequestWritable = {
  /**
   * 包括机密
   *
   * 是否使用配置文件持久化 API 键。
   */
  include_secrets?: boolean;
  llm: LlmInputWritable;
};

/**
 * SecretCreateRequest
 *
 * 请求 PUT /api/settings/secrets. 的模型
 *
 * 使用给定名称和值创建或更新机密。
 */
export type SecretCreateRequestWritable = {
  /**
   * 描述
   */
  description?: string | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 价值
   */
  value: string;
};

/**
 * SecretRegistry
 *
 * 管理机密并在需要时将它们注入到 bash 命令中。
 *
 * 机密注册表存储机密键到 SecretSources 的映射
 * 检索实际的机密值。 当 bash 命令即将执行时
 * 执行时，它会扫描命令中的任何机密键并注入相应的
 * 环境变量。
 *
 * 机密来源将酌情编辑/加密其敏感值
 * 序列化，取决于上下文的内容。 如果存在上下文
 * 并包含一个“密码”对象，用于加密。 如果它包含一个
 * 设置为 True、机密的布尔“expose_secrets”标志以纯文本形式转储。
 * 否则机密为已脱敏。
 *
 * 此外，它还跟踪最新导出的值以实现一致的屏蔽
 * 即使可调用机密在后续调用中失败。
 */
export type SecretRegistryWritable = {
  /**
   * 机密来源
   */
  secret_sources?: {
    [key: string]: SecretSourceOutputWritable;
  };
};

export type SecretSourceInputWritable =
  | ({
      kind: 'openhands__sdk__secret__secrets__LookupSecret-Input__1';
    } & LookupSecretInput)
  | ({
      kind: 'openhands__sdk__secret__secrets__StaticSecret-Input__1';
    } & StaticSecretInputWritable);

export type SecretSourceOutputWritable =
  | ({
      kind: 'openhands__sdk__secret__secrets__LookupSecret-Output__1';
    } & LookupSecretOutput)
  | ({
      kind: 'openhands__sdk__secret__secrets__StaticSecret-Output__1';
    } & StaticSecretOutputWritable);

export type SecurityAnalyzerBaseInputWritable =
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__pattern__PatternSecurityAnalyzer-Input__1';
    } & PatternSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__policy_rails__PolicyRailSecurityAnalyzer-Input__1';
    } & PolicyRailSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__ensemble__EnsembleSecurityAnalyzer-Input__1';
    } & EnsembleSecurityAnalyzerInputWritable)
  | ({
      kind: 'openhands__sdk__security__grayswan__analyzer__GraySwanAnalyzer-Input__1';
    } & GraySwanAnalyzerInputWritable)
  | ({
      kind: 'openhands__sdk__security__llm_analyzer__LLMSecurityAnalyzer-Input__1';
    } & LlmSecurityAnalyzerInput)
  | ({
      kind: 'openhands__sdk__security__toolshield_llm_analyzer__ToolShieldLLMSecurityAnalyzer-Input__1';
    } & ToolShieldLlmSecurityAnalyzerInputWritable);

export type SecurityAnalyzerBaseOutputWritable =
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__pattern__PatternSecurityAnalyzer-Output__1';
    } & PatternSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__defense_in_depth__policy_rails__PolicyRailSecurityAnalyzer-Output__1';
    } & PolicyRailSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__ensemble__EnsembleSecurityAnalyzer-Output__1';
    } & EnsembleSecurityAnalyzerOutputWritable)
  | ({
      kind: 'openhands__sdk__security__grayswan__analyzer__GraySwanAnalyzer-Output__1';
    } & GraySwanAnalyzerOutputWritable)
  | ({
      kind: 'openhands__sdk__security__llm_analyzer__LLMSecurityAnalyzer-Output__1';
    } & LlmSecurityAnalyzerOutput)
  | ({
      kind: 'openhands__sdk__security__toolshield_llm_analyzer__ToolShieldLLMSecurityAnalyzer-Output__1';
    } & ToolShieldLlmSecurityAnalyzerOutputWritable);

/**
 * SetSecurityAnalyzerRequest
 *
 * 载荷为对话设置安全分析器
 */
export type SetSecurityAnalyzerRequestWritable = {
  /**
   * 安全分析器设置
   */
  security_analyzer: SecurityAnalyzerBaseInputWritable | null;
};

/**
 * SettingsUpdateRequest
 *
 * 请求 PATCH /api/settings. 的模型
 *
 * 支持通过深度合并的 diff 对象进行部分更新
 * 现有设置。 ``misc_settings_diff`` 深度合并到
 * 已持久化 ``misc_settings`` 块具有相同的语义
 * ``agent_settings_diff`` 和 ``conversation_settings_diff``：嵌套字典
 * 递归合并，列表被批量替换而不是合并。
 * 因为 ``misc_settings`` 对智能体服务器不透明，所以调用者
 * 负责他们存储在那里的东西的形状。
 */
export type SettingsUpdateRequestWritable = {
  /**
   * 活动智能体配置文件 ID
   *
   * 活动的稳定 ID AgentProfile 至持久化； null 清除它。
   */
  active_agent_profile_id?: string | null;
  /**
   * 活动元配置文件
   *
   * 活动元配置文件的名称为持久化； null 清除它。
   */
  active_meta_profile?: string | null;
  /**
   * 活动档案
   *
   * 活动 LLM 配置文件的名称到持久化； null 清除它。
   */
  active_profile?: string | null;
  /**
   * 智能体设置差异
   */
  agent_settings_diff?: {
    mcp_config?: McpConfigPatchWritable | null;
    [key: string]: unknown;
  } | null;
  /**
   * 对话设置差异
   */
  conversation_settings_diff?: {
    [key: string]: unknown;
  } | null;
  /**
   * 杂项设置差异
   */
  misc_settings_diff?: {
    [key: string]: unknown;
  } | null;
};

/**
 * 技能
 *
 * 技能提供专业知识或功能。
 *
 * 技能行为取决于格式（is_agentskills_format）和触发器：
 *
 * AgentSkills 格式（SKILL.md 个文件）：
 * - 始终在 <available_skills> 中列出，包含名称、描述、位置
 * - 智能体按需阅读完整内容（渐进式披露）
 * - 如果有触发器：触发时内容会自动注入 ALSO
 *
 * 旧版 OpenHands 格式：
 * - 带触发器：列在<available_skills>中，在触发器上注入内容
 * - 无触发器 (None)：<REPO_CONTEXT> 中的完整内容，始终处于活动状态
 *
 * 该模型支持 OpenHands 特定字段和 AgentSkills 标准
 * 用于跨平台兼容性的字段（ https://agentskills.io/specification ）。
 */
export type SkillInputWritable = {
  /**
   * 允许使用的工具
   *
   * 此技能的预先批准的工具列表。 AgentSkills 标准字段（从空格分隔的字符串解析）。
   */
  allowed_tools?: Array<string> | null;
  /**
   * 兼容性
   *
   * 该技能的环境要求或兼容性说明。 AgentSkills 标准字段（e.g., '需要 git 和 Docker'）。
   */
  compatibility?: string | null;
  /**
   * 内容
   */
  content: string;
  /**
   * 描述
   *
   * 简要描述该技能的作用以及何时使用它。 超过 MAX_DESCRIPTION_LENGTH 的描述将被截断，并带有指向技能源路径的通知。
   */
  description?: string | null;
  /**
   * 禁用模型调用
   *
   * 该技能是否只能通过触发匹配来激活，并且不应发布到模型以直接调用。
   */
  disable_model_invocation?: boolean;
  /**
   * 输入
   *
   * 输入技能的元数据（仅限任务技能）
   */
  inputs?: Array<InputMetadata>;
  /**
   * 是 Agentskills 格式
   *
   * 该技能是否是从遵循 AgentSkills 标准的 SKILL.md 文件加载的。 AgentSkills-格式技能使用渐进式披露：始终在 <available_skills> 中列出，并包含名称、描述和位置。 如果该技能也有触发器，则触发时会自动注入内容AND智能体可以随时读取文件。
   */
  is_agentskills_format?: boolean;
  /**
   * 许可证
   *
   * 分发技能所依据的许可证。 AgentSkills 标准字段（e.g.、“Apache-2.0”、“MIT”）。
   */
  license?: string | null;
  /**
   * MCP 工具
   *
   * MCP 技能服务器（仅限仓库技能）。
   */
  mcp_tools?: {
    [key: string]: McpServerInputWritable;
  } | null;
  /**
   * 元数据
   *
   * 技能的任意键值元数据。 AgentSkills 可扩展性的标准字段。
   */
  metadata?: {
    [key: string]: string;
  } | null;
  /**
   * 名称
   */
  name: string;
  /**
   * 技能的资源目录（scripts/、references/、assets/）。 AgentSkills 标准字段。 仅针对 SKILL.md 目录格式进行填充。
   */
  resources?: SkillResources | null;
  /**
   * 来源
   *
   * 技能的源路径或标识符。 当它为 None 时，它被视为以编程方式定义的技能。
   */
  source?: string | null;
  /**
   * 触发
   *
   * 触发器决定何时自动注入技能内容。 None = 无自动注入（对于 AgentSkills：智能体按需读取； 对于遗留：完整内容始终在系统中提示词）。 KeywordTrigger = 当关键字出现在用户消息中时自动注入。 TaskTrigger = 针对特定任务自动注入，可能需要用户输入。
   */
  trigger?:
    | ({
        type: 'keyword';
      } & KeywordTrigger)
    | ({
        type: 'task';
      } & TaskTrigger)
    | ({
        type: 'path';
      } & PathTrigger)
    | null;
  /**
   * 版本
   *
   * 技能版本（AgentSkills标准字段）。
   */
  version?: string;
};

/**
 * StartChildConversationTool
 *
 * 启动同后端子对话的工具。
 */
export type StartChildConversationToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'StartChildConversationTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * StartConversationRequest
 *
 * 载荷创建一个新对话。
 *
 * 使用智能体源扩展：class:`ConversationConfig`：存储的智能体
 * 配置文件 (``agent_profile_id``)，已解决智能体设置
 * (``agent_settings``) 或 ``agent`` 内置代码。 的
 * 服务器在启动时将源转换为对话的智能体； 这个型号
 * 只检查是否给出了确切的一个来源。
 *
 * 注意：智能体根据 * 请求 * 存在于此处，故意不存在
 * ``ConversationConfig``. 已持久化记录 (``StoredConversation``) 确实
 * 不携带智能体 — 它的唯一事实来源是 ``ConversationState`` /
 * ``base_state.json``.
 */
export type StartConversationRequestWritable = {
  agent?: AgentBaseInputWritable;
  /**
   * 智能体定义
   *
   * 智能体来自客户端注册表的定义。 这些在服务器上注册，以便任务工具可以看到用户注册的子智能体。
   */
  agent_definitions?: Array<AgentDefinitionWritable>;
  /**
   * 在智能体或智能体配置文件解析后应用部署上下文。 存储的智能体配置文件未修改。
   */
  agent_launch_additions?: AgentLaunchAdditionsWritable | null;
  /**
   * 智能体个人资料 ID
   *
   * 已存储要启动的智能体配置文件。 服务器用自己的存储来解决它。 与其他智能体来源相互排斥。
   */
  agent_profile_id?: string | null;
  /**
   * 智能体设置
   *
   * 无参考智能体设置，使用 AgentSettingsBase `agent_kind` 鉴别器进行验证。 服务器在启动时根据它们构建智能体。 设置 `agent` 时忽略。
   */
  agent_settings?: {
    [key: string]: unknown;
  } | null;
  /**
   * 自动标题
   *
   * 如果是 True，则从第一条用户消息中自动生成对话标题。 优先级：title_llm_profile（如果设置并加载）→ agent.llm→消息截断。
   */
  autotitle?: boolean;
  /**
   * 客户端工具
   *
   * 客户端通过 JSON 规范定义的工具。 这些工具没有服务器端执行器 - 当智能体调用它们时，会通过 WebSocket 发出 ActionEvent，并且客户端处理执行。 SDK 立即返回确认信息观测结果。
   */
  client_tools?: Array<ClientToolSpecInput>;
  /**
   * 控制对话在继续之前何时将用户提示词。 默认为从不。
   */
  confirmation_policy?: ConfirmationPolicyBaseInput;
  /**
   * 对话容器的资源（Docker 运行时）。
   */
  container?: ConversationContainerOptions | null;
  /**
   * 对话 ID
   *
   * 可选的对话 ID。 如果未提供，将生成随机 UUID。
   */
  conversation_id?: string | null;
  /**
   * 对话运行时
   *
   * 执行此对话的运行时。 取消设置使用服务器配置的`conversation_runtime`； 仅当服务器在 `available_conversation_runtimes` 中列出另一个值时才接受它。
   */
  conversation_runtime?: 'local' | 'docker' | null;
  /**
   * 此对话的可选挂钩配置。 挂钩是在关键生命周期事件（PreToolUse、PostToolUse、UserPromptSubmit、Stop 等）处运行的 shell 脚本。 如果同时提供了 hook_config 和插件，它们将与在插件挂钩之前运行的显式挂钩合并。
   */
  hook_config?: HookConfig | null;
  /**
   * 要传递到 LLM 的初始消息
   */
  initial_message?: SendMessageRequest | null;
  /**
   * 最大迭代次数
   *
   * 如果设置，则智能体在停止之前将运行的最大迭代次数。 这对于防止无限循环很有用。
   */
  max_iterations?: number;
  /**
   * 可观测性元数据
   *
   * 附加到可观察性后端的跟踪级元数据。 值必须是 OpenTelemetry 支持的标量或齐次标量列表。
   */
  observability_metadata?: {
    [key: string]: TraceMetadataValue;
  };
  /**
   * 可观测性父跨度上下文
   *
   * 已序列化父范围上下文用于将此对话附加到上游自动化或集成跟踪。
   */
  observability_parent_span_context?: string | null;
  /**
   * 可观测性跨度名称
   *
   * 在对话根下发出的可选命名子范围。 使用稳定的、低基数的名称，因为可观察性后端可能使用跨度名称进行分组或信号路由。
   */
  observability_span_name?: string;
  /**
   * 可观察性标签
   *
   * 附加到对话根可观察性范围的标签。
   */
  observability_tags?: Array<string>;
  /**
   * 家长对话 ID
   *
   * 拥有此对话的现有对话的可选 ID。 父级必须已经存在并共享此对话的工作区。
   */
  parent_conversation_id?: string | null;
  /**
   * 插件
   *
   * 为此对话加载的插件列表。 插件已加载，其技能/MCP 配置已合并到智能体中。 钩子被提取并存储以供运行时执行。
   */
  plugins?: Array<PluginSource> | null;
  /**
   * 提示词
   *
   * 可选提示词，替换默认的标题生成用户消息。 使用 {conversation_content} 放置第一条用户消息，使用 {max_length} 放置标题长度限制。 如果省略对话占位符，则会自动附加消息。 空或未设置的值使用默认值提示词。
   */
  prompt?: string | null;
  /**
   * 机密
   *
   * 机密在对话中可用
   */
  secrets?: {
    [key: string]: SecretSourceInputWritable;
  };
  /**
   * 机密加密
   *
   * 如果 True, indicates that 机密在智能体配置信息是通过加密的，应由服务器解密后使用。 这允许通过不可信客户端进行设置的加密往返e.g., 前端) 接收加密值的端点机密 header. 流程：客户端调用 GET  /api/settings 带有 X-Expose-机密加密以接收加密的密文机密然后将它们传递给智能体配置文件 secrets_encrypted=True 因此服务器可以解密它们。
   */
  secrets_encrypted?: boolean;
  /**
   * 可选的安全分析器来评估操作风险。
   */
  security_analyzer?: SecurityAnalyzerBaseInputWritable | null;
  /**
   * 卡住检测
   *
   * 如果为 True，对话将使用卡住检测来防止无限循环。
   */
  stuck_detection?: boolean;
  /**
   * 标签
   *
   * 对话的键值标签。 键必须是小写字母数字。 值是最多 256 个字符的任意字符串。
   */
  tags?: {
    [key: string]: string;
  };
  /**
   * 标题法学硕士简介
   *
   * 用于标题生成的可选 LLM 配置文件名称。 LLM 若设置，则从 LLMProfileStore 加载 (~/.openhands/profiles/) 用于 LLM-基于标题生成)。 这使得无论智能体的主要模型如何，都可以使用快速/廉价的模型来生成标题。 如果没有设置（或配置加载失败），标题生成将回退到智能体的LLM。
   */
  title_llm_profile?: string | null;
  /**
   * 工具模块 Qualnames
   *
   * 将工具名称映射到客户端的注册表的模块限定名。 这些模块将动态导入到服务器上以注册用于此对话的工具。
   */
  tool_module_qualnames?: {
    [key: string]: string;
  };
  /**
   * 用户 ID
   *
   * 托管部署提供的可选用户 ID，用于将此对话与部署已建立的身份相关联。 当设置时，它被传递到 Laminar.set_trace_user_id() 这样可以由用户查询日志， 当主机启用了产品分析时，它会被重用为分析关联标识，从而事件与现有的人相关联而不是创建一个重复的身份。 它从未由生成 SDK，且当未设置时完全省略。
   */
  user_id?: string | null;
  /**
   * 工作目录用于智能体操作和工具执行。
   */
  workspace: LocalWorkspaceInput;
  /**
   * 工作树
   *
   * 如果 True 和工作区已位于 git 存储库内，请在 `/tmp/conversation-worktrees/<conversation_id>/<project_name>` 下为此对话创建专用的 git 工作树。
   */
  worktree?: boolean;
  /**
   * 工作树是如何创建的 (`worktree=True`)； 未设置：默认值。
   */
  worktree_options?: ConversationWorktreeOptions | null;
};

/**
 * StaticSecret
 *
 * A 机密存储在本地
 */
export type StaticSecretInputWritable = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 种类
   */
  kind?: 'StaticSecret';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * StaticSecret
 *
 * A 机密存储在本地
 */
export type StaticSecretOutputWritable = {
  /**
   * 描述
   *
   * 此机密的可选描述
   */
  description?: string | null;
  /**
   * 种类
   */
  kind: 'StaticSecret';
  /**
   * 价值
   */
  value?: string | null;
};

/**
 * SubAgentInfo
 *
 * API 返回的 ``AgentDefinition`` 的无损视图。
 *
 * 每个前置元数据字段加上发现的 ``level``/``source``，一个
 * ``is_builtin`` 标志，以及内联 ``system_prompt``（Markdown 主体），因此
 * 详细视图不需要额外的获取。
 */
export type SubAgentInfoWritable = {
  /**
   * 颜色
   */
  color?: string | null;
  condenser?: CondenserBaseOutputWritable | null;
  /**
   * 描述
   */
  description?: string;
  hooks?: HookConfig | null;
  /**
   * 是内置的
   */
  is_builtin?: boolean;
  /**
   * 级别
   */
  level?: 'project' | 'user' | 'builtin' | 'plugin' | 'programmatic' | null;
  /**
   * 每次运行的最大预算
   */
  max_budget_per_run?: number | null;
  /**
   * 每次运行的最大迭代次数
   */
  max_iteration_per_run?: number | null;
  /**
   * MCP 配置
   *
   * MCP 服务器定义声明。 委托的子智能体忽略它们并继承其父级的 MCP 服务器。
   */
  mcp_config?: {
    [key: string]: McpServerOutput;
  } | null;
  /**
   * MCP 服务器
   *
   * 已弃用 mcp_config 的兼容性别名。 对于新客户，请使用 mcp_config。
   *
   * @已弃用
   */
  mcp_servers?: {
    [key: string]: McpServerOutput;
  } | null;
  /**
   * 元数据
   */
  metadata?: {
    [key: string]: unknown;
  };
  /**
   * 型号
   */
  model?: string;
  /**
   * 名称
   */
  name: string;
  /**
   * 权限模式
   */
  permission_mode?: string | null;
  /**
   * 配置文件存储目录
   */
  profile_store_dir?: string | null;
  /**
   * 技能
   */
  skills?: Array<string>;
  /**
   * 来源
   */
  source?: string | null;
  /**
   * 系统提示词
   */
  system_prompt?: string;
  /**
   * 工具
   */
  tools?: Array<string>;
  /**
   * 何时使用示例
   */
  when_to_use_examples?: Array<string>;
};

/**
 * SubAgentsResponse
 *
 * 响应包含所有可用的子智能体。
 */
export type SubAgentsResponseWritable = {
  /**
   * 智能体
   */
  agents: Array<SubAgentInfoWritable>;
};

/**
 * SwitchLLMTool
 *
 * 用于将对话切换到已保存的 LLM 配置文件的工具。
 */
export type SwitchLlmToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'SwitchLLMTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * SystemPromptEvent
 *
 * 系统提示词由智能体添加。
 *
 * 系统提示词可以选择包括动态上下文，其变化范围为
 * 对话。 当提供 ``dynamic_context`` 时，它被包含为
 * 同一系统消息中的第二个内容块。 缓存标记为不
 * 此处应用 - 它们由 ``LLM._apply_prompt_caching()`` 应用，当
 * 启用缓存，确保仅添加特定于提供者的缓存控制
 * 在适当的时候。
 *
 * 属性：
 * system_prompt：静态系统提示词文本（可跨对话缓存）
 * 工具：列出可用工具的列表
 * dynamic_context：可选的每个会话上下文（主机、存储库信息等）
 * 作为系统消息内的第二个 TextContent 块发送。
 */
export type SystemPromptEventWritable = {
  /**
   * 可选的动态每次对话上下文（运行时信息、存储库上下文、机密）。 提供后，它将作为第二个内容块包含在系统消息中（未缓存）。
   */
  dynamic_context?: TextContent | null;
  /**
   * 身份证号
   *
   * 唯一事件 ID (ULID/UUID)
   */
  id?: string;
  /**
   * 种类
   */
  kind: 'SystemPromptEvent';
  /**
   * 家长 ID
   *
   * 对话树中的父事件 ID。 None 对于根，或者对于树之前的遗留事件（请参阅 EventLog 的有效父规则）。 共享 parent_id 的事件是同级分支。
   */
  parent_id?: string | null;
  /**
   * 来源
   */
  source?: 'agent' | 'user' | 'environment' | 'hook';
  /**
   * 系统提示词文本
   */
  system_prompt: TextContent;
  /**
   * 时间戳
   *
   * 事件时间戳
   */
  timestamp?: string;
  /**
   * 工具
   *
   * 作为 ToolDefinition 对象的工具列表
   */
  tools: Array<ToolDefinitionWritable>;
};

/**
 * TaskTool
 *
 * 用于启动（阻止）子智能体任务的工具。
 */
export type TaskToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * TaskToolSet
 *
 * 任务工具集。
 *
 * 创建由共享 TaskManager 支持的任务工具。
 *
 * 用途：
 * 从 openhands.tools.task 导入 TaskToolSet
 *
 * 智能体 = 智能体(
 * llm=llm,
 * 工具=[
 * Tool(name=TerminalTool.name),
 * Tool(name=FileEditorTool.name),
 * Tool(name=TaskToolSet.name),
 * ],
 * )
 */
export type TaskToolSetWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * TaskTrackerTool
 *
 * 自动初始化 TaskTrackerExecutor 的 ToolDefinition 子类。
 */
export type TaskTrackerToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TaskTrackerTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * TelemetrySpec
 *
 * 部署提供的产品分析传输层设置。
 *
 * 它带有传输层加上非识别部署标签。 是否
 * 可以提供遥测数据已征得同意
 * (``misc_settings.telemetry.consent``, 可选择播种或覆盖
 * ``OH_TELEMETRY_CONSENT``).
 */
export type TelemetrySpecWritable = {
  /**
   * 部署类型
   *
   * 附加到诊断事件的部署类型。 对于托管 OpenHands 使用“远程”，对于自托管或开发人员运行使用“本地”。
   */
  deployment_kind?: 'local' | 'remote';
  /**
   * 事件缓冲区大小
   *
   * 每个交付批次的最大事件数。
   */
  event_buffer_size?: number;
  /**
   * 出口商
   *
   * 出口商使用。 None（默认值）从不发送，这是库和无头消费者所获得的。 'posthog' 需要额外的 [posthog]。 HTTP POSTs 清洗了 telemetry_http_endpoint 批次。
   */
  exporter?: 'none' | 'posthog' | 'http';
  /**
   * 冲洗延迟
   *
   * 刷新部分批次之前等待的秒数。
   */
  flush_delay?: number;
  /**
   * HTTP 端点
   *
   * 端点 "HTTP" 导出器 POSTs 会清理事件批次。 旨在前端后端在转发之前重新验证身份验证和同意。
   */
  http_endpoint?: string | null;
  /**
   * HTTP token
   *
   * 持有者令牌由“HTTP”出口商发送（如果需要）。
   */
  http_token?: string | null;
  /**
   * 最大队列大小
   *
   * 缓冲诊断事件的上限。 队列在摄取时受到限制：超过这么多事件，最旧的事件将被丢弃，因此失败的导出器无法无限制地增加内存。
   */
  max_queue_size?: number;
  /**
   * 数量重试
   *
   * 重试在批次被删除之前。
   */
  num_retries?: number;
  /**
   * Posthog API 钥匙
   *
   * PostHog项目API关键。 “posthog”出口商要求； 如果没有它，遥测将保持不活动状态。
   */
  posthog_api_key?: string | null;
  /**
   * 邮差主机
   *
   * PostHog摄取主机。
   */
  posthog_host?: string;
  /**
   * 重试延迟
   *
   * 传送之间的基本秒数重试。
   */
  retry_delay?: number;
  /**
   * 盐
   *
   * 用于对对话标识符进行假名化的密钥。 fallback to the server's 机密 key (OH_SECRET_KEY, which defaults to the first session API key)，因此匿名者保持稳定且可链接，直到该键发生变化。 仅当没有机密密钥时，每个进程才会生成随机密钥，这使得假名在运行中不可链接。
   */
  salt?: string | null;
};

/**
 * TerminalTool
 *
 * 通过自动检测自动初始化 TerminalExecutor 的 ToolDefinition 子类。
 */
export type TerminalToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'TerminalTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * ThinkTool
 *
 * 用于记录想法而不进行更改的工具。
 */
export type ThinkToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'ThinkTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

export type ToolDefinitionWritable =
  | ({
      kind: 'openhands__sdk__mcp__tool__MCPToolDefinition-Output__1';
    } & McpToolDefinitionWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__classify_and_switch_llm__ClassifyAndSwitchLLMTool-Output__1';
    } & ClassifyAndSwitchLlmToolWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__finish__FinishTool-Output__1';
    } & FinishToolWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__invoke_skill__InvokeSkillTool-Output__1';
    } & InvokeSkillToolWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__switch_llm__SwitchLLMTool-Output__1';
    } & SwitchLlmToolWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__think__ThinkTool-Output__1';
    } & ThinkToolWritable)
  | ({
      kind: 'openhands__sdk__tool__builtins__vision_inspect__VisionInspectTool-Output__1';
    } & VisionInspectToolWritable)
  | ({
      kind: 'openhands__sdk__tool__client_tool__ClientTool-Output__1';
    } & ClientToolWritable)
  | ({
      kind: 'openhands__tools__ask_oracle__definition__AskOracleTool-Output__1';
    } & AskOracleToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserClickTool-Output__1';
    } & BrowserClickToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserCloseTabTool-Output__1';
    } & BrowserCloseTabToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetContentTool-Output__1';
    } & BrowserGetContentToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStateTool-Output__1';
    } & BrowserGetStateToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGetStorageTool-Output__1';
    } & BrowserGetStorageToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserGoBackTool-Output__1';
    } & BrowserGoBackToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserListTabsTool-Output__1';
    } & BrowserListTabsToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserNavigateTool-Output__1';
    } & BrowserNavigateToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserScrollTool-Output__1';
    } & BrowserScrollToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSetStorageTool-Output__1';
    } & BrowserSetStorageToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStartRecordingTool-Output__1';
    } & BrowserStartRecordingToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserStopRecordingTool-Output__1';
    } & BrowserStopRecordingToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserSwitchTabTool-Output__1';
    } & BrowserSwitchTabToolWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserToolSet-Output__1';
    } & BrowserToolSetWritable)
  | ({
      kind: 'openhands__tools__browser_use__definition__BrowserTypeTool-Output__1';
    } & BrowserTypeToolWritable)
  | ({
      kind: 'openhands__tools__child_conversation__definition__StartChildConversationTool-Output__1';
    } & StartChildConversationToolWritable)
  | ({
      kind: 'openhands__tools__file_editor__definition__FileEditorTool-Output__1';
    } & FileEditorToolWritable)
  | ({
      kind: 'openhands__tools__gemini__edit__definition__EditTool-Output__1';
    } & EditToolWritable)
  | ({
      kind: 'openhands__tools__gemini__list_directory__definition__ListDirectoryTool-Output__1';
    } & ListDirectoryToolWritable)
  | ({
      kind: 'openhands__tools__gemini__read_file__definition__ReadFileTool-Output__1';
    } & ReadFileToolWritable)
  | ({
      kind: 'openhands__tools__gemini__write_file__definition__WriteFileTool-Output__1';
    } & WriteFileToolWritable)
  | ({
      kind: 'openhands__tools__glob__definition__GlobTool-Output__1';
    } & GlobToolWritable)
  | ({
      kind: 'openhands__tools__grep__definition__GrepTool-Output__1';
    } & GrepToolWritable)
  | ({
      kind: 'openhands__tools__planning_file_editor__definition__PlanningFileEditorTool-Output__1';
    } & PlanningFileEditorToolWritable)
  | ({
      kind: 'openhands__tools__task__definition__TaskTool-Output__1';
    } & TaskToolWritable)
  | ({
      kind: 'openhands__tools__task__definition__TaskToolSet-Output__1';
    } & TaskToolSetWritable)
  | ({
      kind: 'openhands__tools__task_tracker__definition__TaskTrackerTool-Output__1';
    } & TaskTrackerToolWritable)
  | ({
      kind: 'openhands__tools__terminal__definition__TerminalTool-Output__1';
    } & TerminalToolWritable)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowTool-Output__1';
    } & WorkflowToolWritable)
  | ({
      kind: 'openhands__tools__workflow__definition__WorkflowToolSet-Output__1';
    } & WorkflowToolSetWritable);

/**
 * ToolShieldLLMSecurityAnalyzer
 *
 * 通过单独的约束检查 LLM 评估每个操作。
 *
 * 与现有的``ConfirmRisky``政策不变：这
 * 分析器仅 * 分配 * 风险级别； ``ConfirmRisky`` 决定
 * 是否暂停以供用户确认。
 *
 * 默认情况下，分析器作为裸机约束检查运行（没有蒸馏
 * safety experiences). 要启用 ToolShield 种子，请安装
 * ``pip install openhands-sdk[toolshield]`` 并传递渲染的
 * 通过 ``safety_experiences`` 字段获得的经验——通常通过
 * 助手之一 (``default_safety_experiences()``,
 * ``load_safety_experiences(...)``, ``auto_detect_safety_experiences()``).
 * 针对 ``toolshield>=0.1.3,<0.2`` 进行测试。
 *
 * 注：``reasoning_content``和``thinking_blocks``来自扩展-
 * 思维模型被故意排除在约束检查之外
 * 上下文。 风险信号存在于工具调用的名字中，并且
 * 论据； 包括推理文本会使提示词膨胀
 * 无比例安全增益。 需要推理的子类
 * 可见性应覆盖：func:`_format_action_for_guardrail`。
 *
 * 生命周期：实例维护最近的每个会话双端队列
 * 约束检查上下文的操作（``history_window`` 项）。 每个
 * 实例供 SINGLE-CONVERSATION 使用。 重复使用一个
 * 跨多个对话的分析器实例将泄漏操作
 * 他们之间的历史，这都是隐私问题（对话
 * A 的工具参数在对话 B 中可见约束检查提示词)
 * 以及正确性问题（约束检查评估对话 B 的
 * 针对无关历史的行动）。 每构建一个分析器
 * 对话，或在对话中致电：meth:`reset_history`
 * 边界。
 *
 * 最近的操作上下文在分析器之间的传播（这个，
 * :class:`LLMSecurityAnalyzer`, :class:`GraySwanAnalyzer`) 被跟踪
 * 为了在单独的后续行动中收敛； 直到着陆，
 * 单一对话的生命周期就是契约。
 *
 * 故障模式是一致的并且是整体安全的——两者都是
 * 基础设施错误（网络、速率限制）和解析失败
 * （约束检查响应，但其输出没有可解析的
 * ``RISK:`` 标签）返回 ``SecurityRisk.UNKNOWN``。 ``ConfirmRisky``
 * 用 ``confirm_unknown=True`` 然后暂停以供用户确认，
 * 匹配保守的姿态而不占主导地位``max()``
 * 整体融合。
 */
export type ToolShieldLlmSecurityAnalyzerInputWritable = {
  /**
   * 历史窗口
   *
   * 要包含为上下文的先前操作的数量。
   */
  history_window?: number;
  /**
   * 种类
   */
  kind?: 'ToolShieldLLMSecurityAnalyzer';
  /**
   * LLM用作约束检查。 可以是比演员更小/更便宜的模型LLM； 只有模型对行动风险进行分类的能力才是重要的。
   */
  llm: LlmInputWritable;
  /**
   * Safety Experiences
   *
   * 预先生成的安全指南已注入约束检查的系统提示词。
   * - ``""``（默认）：裸约束检查 -- 没有经验。 分析器仍然将参与者和判断者分开； 它只是在没有特定工具指导的情况下进行分类。
   * - 任何非空字符串：按原样使用。 预期的模式是调用需要 ``[toolshield]`` 可选额外 (``pip install openhands-sdk[toolshield]``) 的助手 (``default_safety_experiences()``、``load_safety_experiences(tool_names)``、``auto_detect_safety_experiences()``) 之一。 拥有自己的指南来源的调用者可以传递任何自定义字符串。
   */
  safety_experiences?: string;
};

/**
 * ToolShieldLLMSecurityAnalyzer
 *
 * 通过单独的约束检查 LLM 评估每个操作。
 *
 * 与现有的``ConfirmRisky``政策不变：这
 * 分析器仅 * 分配 * 风险级别； ``ConfirmRisky`` 决定
 * 是否暂停以供用户确认。
 *
 * 默认情况下，分析器作为裸机约束检查运行（没有蒸馏
 * safety experiences). 要启用 ToolShield 种子，请安装
 * ``pip install openhands-sdk[toolshield]`` 并传递渲染的
 * 通过 ``safety_experiences`` 字段获得的经验——通常通过
 * 助手之一 (``default_safety_experiences()``,
 * ``load_safety_experiences(...)``, ``auto_detect_safety_experiences()``).
 * 针对 ``toolshield>=0.1.3,<0.2`` 进行测试。
 *
 * 注：``reasoning_content``和``thinking_blocks``来自扩展-
 * 思维模型被故意排除在约束检查之外
 * 上下文。 风险信号存在于工具调用的名字中，并且
 * 论据； 包括推理文本会使提示词膨胀
 * 无比例安全增益。 需要推理的子类
 * 可见性应覆盖：func:`_format_action_for_guardrail`。
 *
 * 生命周期：实例维护最近的每个会话双端队列
 * 约束检查上下文的操作（``history_window`` 项）。 每个
 * 实例供 SINGLE-CONVERSATION 使用。 重复使用一个
 * 跨多个对话的分析器实例将泄漏操作
 * 他们之间的历史，这都是隐私问题（对话
 * A 的工具参数在对话 B 中可见约束检查提示词)
 * 以及正确性问题（约束检查评估对话 B 的
 * 针对无关历史的行动）。 每构建一个分析器
 * 对话，或在对话中致电：meth:`reset_history`
 * 边界。
 *
 * 最近的操作上下文在分析器之间的传播（这个，
 * :class:`LLMSecurityAnalyzer`, :class:`GraySwanAnalyzer`) 被跟踪
 * 为了在单独的后续行动中收敛； 直到着陆，
 * 单一对话的生命周期就是契约。
 *
 * 故障模式是一致的并且是整体安全的——两者都是
 * 基础设施错误（网络、速率限制）和解析失败
 * （约束检查响应，但其输出没有可解析的
 * ``RISK:`` 标签）返回 ``SecurityRisk.UNKNOWN``。 ``ConfirmRisky``
 * 用 ``confirm_unknown=True`` 然后暂停以供用户确认，
 * 匹配保守的姿态而不占主导地位``max()``
 * 整体融合。
 */
export type ToolShieldLlmSecurityAnalyzerOutputWritable = {
  /**
   * 历史窗口
   *
   * 要包含为上下文的先前操作的数量。
   */
  history_window?: number;
  /**
   * 种类
   */
  kind: 'ToolShieldLLMSecurityAnalyzer';
  /**
   * LLM用作约束检查。 可以是比演员更小/更便宜的模型LLM； 只有模型对行动风险进行分类的能力才是重要的。
   */
  llm: LlmOutputWritable;
  /**
   * Safety Experiences
   *
   * 预先生成的安全指南已注入约束检查的系统提示词。
   * - ``""``（默认）：裸约束检查 -- 没有经验。 分析器仍然将参与者和判断者分开； 它只是在没有特定工具指导的情况下进行分类。
   * - 任何非空字符串：按原样使用。 预期的模式是调用需要 ``[toolshield]`` 可选额外 (``pip install openhands-sdk[toolshield]``) 的助手 (``default_safety_experiences()``、``load_safety_experiences(tool_names)``、``auto_detect_safety_experiences()``) 之一。 拥有自己的指南来源的调用者可以传递任何自定义字符串。
   */
  safety_experiences?: string;
};

/**
 * UpdateSecretsRequest
 *
 * 载荷更新对话中的机密。
 */
export type UpdateSecretsRequestWritable = {
  /**
   * 机密
   *
   * 字典将机密键映射到值
   */
  secrets: {
    [key: string]: SecretSourceInputWritable;
  };
};

/**
 * ValidateProfileRequest
 *
 * LLM 飞行前验证的请求正文。
 *
 * 接受一个 LLM 配置(相同的形状 ``SaveProfileRequest.llm``) 所以就
 * 前端可以在保留草稿之前*验证它*。
 */
export type ValidateProfileRequestWritable = {
  llm: LlmInputWritable;
};

/**
 * VisionInspectTool
 *
 * 通过保存的视觉配置文件进行一次性图像检查的工具。
 */
export type VisionInspectToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'VisionInspectTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * WorkflowTool
 *
 * 用于显式执行程序注入的低级工具。
 *
 * 首选 ``WorkflowToolSet`` 标准 SDK 自动创建用法。
 * 当需要注入自定义执行器时使用``WorkflowTool``
 * （e.g.，在测试或扩展中）。
 */
export type WorkflowToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WorkflowTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * WorkflowToolSet
 *
 * 创建动态工作流程工具的工具集。
 */
export type WorkflowToolSetWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WorkflowToolSet';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * WriteFileTool
 *
 * 用于写入完整文件内容的工具。
 */
export type WriteFileToolWritable = {
  /**
   * 动作类型
   */
  action_type: string;
  annotations?: OpenhandsSdkToolToolToolAnnotations | null;
  /**
   * 描述
   */
  description: string;
  /**
   * 种类
   */
  kind: 'WriteFileTool';
  /**
   * 元
   */
  meta?: {
    [key: string]: unknown;
  } | null;
  /**
   * 观测结果类型
   */
  observation_type?: string | null;
};

/**
 * _RemoteMCPServerSpec
 *
 * 传统远程 MCP 服务器规范已被公众接受 REST API。
 */
export type RemoteMcpServerSpecWritable = {
  /**
   * 授权
   */
  auth?:
    | ({
        strategy: 'none';
      } & McpNoneAuthCredential)
    | ({
        strategy: 'api_key';
      } & McpApiKeyAuthCredentialInputWritable)
    | ({
        strategy: 'bearer';
      } & McpBearerAuthCredentialInputWritable)
    | ({
        strategy: 'basic';
      } & McpBasicAuthCredentialInputWritable)
    | ({
        strategy: 'header';
      } & McpHeaderAuthCredentialInputWritable)
    | ({
        strategy: 'oauth2';
      } & McpoAuthAuthCredentialInputWritable)
    | null;
  /**
   * 标头
   */
  headers?: {
    [key: string]: string;
  };
  /**
   * 保持活力
   */
  keep_alive?: boolean | null;
  /**
   * 读超时
   */
  sse_read_timeout?: number | null;
  /**
   * 超时
   */
  timeout?: number | null;
  /**
   * 类型
   */
  type: 'http' | 'shttp' | 'streamable-http' | 'sse';
  /**
   * 网址
   */
  url: string;
};

export type DiscoverModelsApiAcpModelsPostData = {
  body: AcpModelDiscoveryRequestWritable;
  path?: never;
  query?: never;
  url: '/api/acp/models';
};

export type DiscoverModelsApiAcpModelsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DiscoverModelsApiAcpModelsPostError =
  DiscoverModelsApiAcpModelsPostErrors[keyof DiscoverModelsApiAcpModelsPostErrors];

export type DiscoverModelsApiAcpModelsPostResponses = {
  /**
   * 成功回应
   */
  200: AcpModelDiscovery;
};

export type DiscoverModelsApiAcpModelsPostResponse =
  DiscoverModelsApiAcpModelsPostResponses[keyof DiscoverModelsApiAcpModelsPostResponses];

export type ListAgentProfilesApiAgentProfilesGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/agent-profiles';
};

export type ListAgentProfilesApiAgentProfilesGetResponses = {
  /**
   * 成功回应
   */
  200: AgentProfileListResponse;
};

export type ListAgentProfilesApiAgentProfilesGetResponse =
  ListAgentProfilesApiAgentProfilesGetResponses[keyof ListAgentProfilesApiAgentProfilesGetResponses];

export type DeleteAgentProfileApiAgentProfilesNameDeleteData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/agent-profiles/{name}';
};

export type DeleteAgentProfileApiAgentProfilesNameDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteAgentProfileApiAgentProfilesNameDeleteError =
  DeleteAgentProfileApiAgentProfilesNameDeleteErrors[keyof DeleteAgentProfileApiAgentProfilesNameDeleteErrors];

export type DeleteAgentProfileApiAgentProfilesNameDeleteResponses = {
  /**
   * 成功回应
   */
  200: AgentProfileMutationResponse;
};

export type DeleteAgentProfileApiAgentProfilesNameDeleteResponse =
  DeleteAgentProfileApiAgentProfilesNameDeleteResponses[keyof DeleteAgentProfileApiAgentProfilesNameDeleteResponses];

export type GetAgentProfileApiAgentProfilesNameGetData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/agent-profiles/{name}';
};

export type GetAgentProfileApiAgentProfilesNameGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetAgentProfileApiAgentProfilesNameGetError =
  GetAgentProfileApiAgentProfilesNameGetErrors[keyof GetAgentProfileApiAgentProfilesNameGetErrors];

export type GetAgentProfileApiAgentProfilesNameGetResponses = {
  /**
   * 成功回应
   */
  200: AgentProfileDetailResponse;
};

export type GetAgentProfileApiAgentProfilesNameGetResponse =
  GetAgentProfileApiAgentProfilesNameGetResponses[keyof GetAgentProfileApiAgentProfilesNameGetResponses];

export type SaveAgentProfileApiAgentProfilesNamePostData = {
  /**
   * 身体
   */
  body: {
    [key: string]: unknown;
  };
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/agent-profiles/{name}';
};

export type SaveAgentProfileApiAgentProfilesNamePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SaveAgentProfileApiAgentProfilesNamePostError =
  SaveAgentProfileApiAgentProfilesNamePostErrors[keyof SaveAgentProfileApiAgentProfilesNamePostErrors];

export type SaveAgentProfileApiAgentProfilesNamePostResponses = {
  /**
   * 成功回应
   */
  201: AgentProfileMutationResponse;
};

export type SaveAgentProfileApiAgentProfilesNamePostResponse =
  SaveAgentProfileApiAgentProfilesNamePostResponses[keyof SaveAgentProfileApiAgentProfilesNamePostResponses];

export type MaterializeAgentProfileApiAgentProfilesNameMaterializePostData = {
  /**
   * 身体
   */
  body?: MaterializeAgentProfileRequest | null;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/agent-profiles/{name}/materialize';
};

export type MaterializeAgentProfileApiAgentProfilesNameMaterializePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type MaterializeAgentProfileApiAgentProfilesNameMaterializePostError =
  MaterializeAgentProfileApiAgentProfilesNameMaterializePostErrors[keyof MaterializeAgentProfileApiAgentProfilesNameMaterializePostErrors];

export type MaterializeAgentProfileApiAgentProfilesNameMaterializePostResponses = {
  /**
   * 成功回应
   */
  200: AgentProfileDiagnostics;
};

export type MaterializeAgentProfileApiAgentProfilesNameMaterializePostResponse =
  MaterializeAgentProfileApiAgentProfilesNameMaterializePostResponses[keyof MaterializeAgentProfileApiAgentProfilesNameMaterializePostResponses];

export type RenameAgentProfileApiAgentProfilesNameRenamePostData = {
  body: RenameAgentProfileRequest;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/agent-profiles/{name}/rename';
};

export type RenameAgentProfileApiAgentProfilesNameRenamePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type RenameAgentProfileApiAgentProfilesNameRenamePostError =
  RenameAgentProfileApiAgentProfilesNameRenamePostErrors[keyof RenameAgentProfileApiAgentProfilesNameRenamePostErrors];

export type RenameAgentProfileApiAgentProfilesNameRenamePostResponses = {
  /**
   * 成功回应
   */
  200: AgentProfileMutationResponse;
};

export type RenameAgentProfileApiAgentProfilesNameRenamePostResponse =
  RenameAgentProfileApiAgentProfilesNameRenamePostResponses[keyof RenameAgentProfileApiAgentProfilesNameRenamePostResponses];

export type ActivateAgentProfileApiAgentProfilesProfileIdActivatePostData = {
  body?: never;
  path: {
    /**
     * 配置文件 ID
     */
    profile_id: string;
  };
  query?: never;
  url: '/api/agent-profiles/{profile_id}/activate';
};

export type ActivateAgentProfileApiAgentProfilesProfileIdActivatePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ActivateAgentProfileApiAgentProfilesProfileIdActivatePostError =
  ActivateAgentProfileApiAgentProfilesProfileIdActivatePostErrors[keyof ActivateAgentProfileApiAgentProfilesProfileIdActivatePostErrors];

export type ActivateAgentProfileApiAgentProfilesProfileIdActivatePostResponses = {
  /**
   * 成功回应
   */
  200: ActivateAgentProfileResponse;
};

export type ActivateAgentProfileApiAgentProfilesProfileIdActivatePostResponse =
  ActivateAgentProfileApiAgentProfilesProfileIdActivatePostResponses[keyof ActivateAgentProfileApiAgentProfilesProfileIdActivatePostResponses];

export type DeleteWorkspaceSessionApiAuthWorkspaceSessionDeleteData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/auth/workspace-session';
};

export type DeleteWorkspaceSessionApiAuthWorkspaceSessionDeleteResponses = {
  /**
   * Cookie 已清除
   */
  204: void;
};

export type DeleteWorkspaceSessionApiAuthWorkspaceSessionDeleteResponse =
  DeleteWorkspaceSessionApiAuthWorkspaceSessionDeleteResponses[keyof DeleteWorkspaceSessionApiAuthWorkspaceSessionDeleteResponses];

export type CreateWorkspaceSessionApiAuthWorkspaceSessionPostData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/auth/workspace-session';
};

export type CreateWorkspaceSessionApiAuthWorkspaceSessionPostErrors = {
  /**
   * X-Session-API-Key 标头丢失或无效
   */
  401: unknown;
};

export type CreateWorkspaceSessionApiAuthWorkspaceSessionPostResponses = {
  /**
   * 饼干套装
   */
  204: void;
};

export type CreateWorkspaceSessionApiAuthWorkspaceSessionPostResponse =
  CreateWorkspaceSessionApiAuthWorkspaceSessionPostResponses[keyof CreateWorkspaceSessionApiAuthWorkspaceSessionPostResponses];

export type StopBashCommandApiBashBashCommandsCommandIdStopPostData = {
  body?: never;
  path: {
    /**
     * 命令 ID
     */
    command_id: string;
  };
  query?: never;
  url: '/api/bash/bash_commands/{command_id}/stop';
};

export type StopBashCommandApiBashBashCommandsCommandIdStopPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type StopBashCommandApiBashBashCommandsCommandIdStopPostError =
  StopBashCommandApiBashBashCommandsCommandIdStopPostErrors[keyof StopBashCommandApiBashBashCommandsCommandIdStopPostErrors];

export type StopBashCommandApiBashBashCommandsCommandIdStopPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type StopBashCommandApiBashBashCommandsCommandIdStopPostResponse =
  StopBashCommandApiBashBashCommandsCommandIdStopPostResponses[keyof StopBashCommandApiBashBashCommandsCommandIdStopPostResponses];

export type ClearAllBashEventsApiBashBashEventsDeleteData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/bash/bash_events';
};

export type ClearAllBashEventsApiBashBashEventsDeleteResponses = {
  /**
   * 响应清除所有 Bash 事件 API Bash Bash 事件删除
   *
   * 成功回应
   */
  200: {
    [key: string]: number;
  };
};

export type ClearAllBashEventsApiBashBashEventsDeleteResponse =
  ClearAllBashEventsApiBashBashEventsDeleteResponses[keyof ClearAllBashEventsApiBashBashEventsDeleteResponses];

export type BatchGetBashEventsApiBashBashEventsGetData = {
  /**
   * 事件 ID
   */
  body: Array<string>;
  path?: never;
  query?: never;
  url: '/api/bash/bash_events/';
};

export type BatchGetBashEventsApiBashBashEventsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type BatchGetBashEventsApiBashBashEventsGetError =
  BatchGetBashEventsApiBashBashEventsGetErrors[keyof BatchGetBashEventsApiBashBashEventsGetErrors];

export type BatchGetBashEventsApiBashBashEventsGetResponses = {
  /**
   * 响应批量获取 Bash 事件 API Bash Bash 事件获取
   *
   * 成功回应
   */
  200: Array<BashEventBase | null>;
};

export type BatchGetBashEventsApiBashBashEventsGetResponse =
  BatchGetBashEventsApiBashBashEventsGetResponses[keyof BatchGetBashEventsApiBashBashEventsGetResponses];

export type SearchBashEventsApiBashBashEventsSearchGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 种类情商
     */
    kind__eq?: 'BashCommand' | 'BashOutput' | null;
    /**
     * 命令 ID 等式
     */
    command_id__eq?: string | null;
    /**
     * 时间戳GTE
     */
    timestamp__gte?: string | null;
    /**
     * 时间戳LT
     */
    timestamp__lt?: string | null;
    /**
     * 过滤顺序大于此值的事件
     *
     * 仅返回顺序 > 该值的 BashOutput 个事件。 对于轮询来说非常有用，可以仅获取自上次轮询以来的新事件。
     */
    order__gt?: number | null;
    sort_order?: BashEventSortOrder;
    /**
     * 先前返回的页面中的可选 next_page_id
     */
    page_id?: string | null;
    /**
     * 页面中的最大结果数
     */
    limit?: number;
  };
  url: '/api/bash/bash_events/search';
};

export type SearchBashEventsApiBashBashEventsSearchGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SearchBashEventsApiBashBashEventsSearchGetError =
  SearchBashEventsApiBashBashEventsSearchGetErrors[keyof SearchBashEventsApiBashBashEventsSearchGetErrors];

export type SearchBashEventsApiBashBashEventsSearchGetResponses = {
  /**
   * 成功回应
   */
  200: BashEventPage;
};

export type SearchBashEventsApiBashBashEventsSearchGetResponse =
  SearchBashEventsApiBashBashEventsSearchGetResponses[keyof SearchBashEventsApiBashBashEventsSearchGetResponses];

export type GetBashEventApiBashBashEventsEventIdGetData = {
  body?: never;
  path: {
    /**
     * 事件 ID
     */
    event_id: string;
  };
  query?: never;
  url: '/api/bash/bash_events/{event_id}';
};

export type GetBashEventApiBashBashEventsEventIdGetErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetBashEventApiBashBashEventsEventIdGetError =
  GetBashEventApiBashBashEventsEventIdGetErrors[keyof GetBashEventApiBashBashEventsEventIdGetErrors];

export type GetBashEventApiBashBashEventsEventIdGetResponses = {
  /**
   * 成功回应
   */
  200: BashEventBase;
};

export type GetBashEventApiBashBashEventsEventIdGetResponse =
  GetBashEventApiBashBashEventsEventIdGetResponses[keyof GetBashEventApiBashBashEventsEventIdGetResponses];

export type ExecuteBashCommandApiBashExecuteBashCommandPostData = {
  body: ExecuteBashRequest;
  path?: never;
  query?: never;
  url: '/api/bash/execute_bash_command';
};

export type ExecuteBashCommandApiBashExecuteBashCommandPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ExecuteBashCommandApiBashExecuteBashCommandPostError =
  ExecuteBashCommandApiBashExecuteBashCommandPostErrors[keyof ExecuteBashCommandApiBashExecuteBashCommandPostErrors];

export type ExecuteBashCommandApiBashExecuteBashCommandPostResponses = {
  /**
   * 成功回应
   */
  200: BashOutput;
};

export type ExecuteBashCommandApiBashExecuteBashCommandPostResponse =
  ExecuteBashCommandApiBashExecuteBashCommandPostResponses[keyof ExecuteBashCommandApiBashExecuteBashCommandPostResponses];

export type StartBashCommandApiBashStartBashCommandPostData = {
  body: ExecuteBashRequest;
  path?: never;
  query?: never;
  url: '/api/bash/start_bash_command';
};

export type StartBashCommandApiBashStartBashCommandPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type StartBashCommandApiBashStartBashCommandPostError =
  StartBashCommandApiBashStartBashCommandPostErrors[keyof StartBashCommandApiBashStartBashCommandPostErrors];

export type StartBashCommandApiBashStartBashCommandPostResponses = {
  /**
   * 成功回应
   */
  200: BashCommand;
};

export type StartBashCommandApiBashStartBashCommandPostResponse =
  StartBashCommandApiBashStartBashCommandPostResponses[keyof StartBashCommandApiBashStartBashCommandPostResponses];

export type InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostData = {
  body: InstallCanvasExtensionRequest;
  path?: never;
  query?: never;
  url: '/api/canvas-extensions/install';
};

export type InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostErrors = {
  /**
   * 无法读取画布扩展源
   */
  400: unknown;
  /**
   * 画布扩展已安装（使用force=True）
   */
  409: unknown;
  /**
   * 无效的画布扩展（错误的清单等）
   */
  422: unknown;
};

export type InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostResponses = {
  /**
   * 成功回应
   */
  200: InstalledCanvasExtensionResponse;
};

export type InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostResponse =
  InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostResponses[keyof InstallCanvasExtensionEndpointApiCanvasExtensionsInstallPostResponses];

export type ListInstalledCanvasExtensionsEndpointApiCanvasExtensionsInstalledGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/canvas-extensions/installed';
};

export type ListInstalledCanvasExtensionsEndpointApiCanvasExtensionsInstalledGetResponses = {
  /**
   * 成功回应
   */
  200: InstalledCanvasExtensionsListResponse;
};

export type ListInstalledCanvasExtensionsEndpointApiCanvasExtensionsInstalledGetResponse =
  ListInstalledCanvasExtensionsEndpointApiCanvasExtensionsInstalledGetResponses[keyof ListInstalledCanvasExtensionsEndpointApiCanvasExtensionsInstalledGetResponses];

export type UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteData = {
  body?: never;
  path: {
    /**
     * 分机名称
     *
     * 画布扩展名（小写字母数字，连字符）
     */
    extension_name: string;
  };
  query?: never;
  url: '/api/canvas-extensions/installed/{extension_name}';
};

export type UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteErrors =
  {
    /**
     * 画布扩展未安装
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteError =
  UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteErrors[keyof UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteErrors];

export type UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteResponses =
  {
    /**
     * 成功回应
     */
    200: UninstallCanvasExtensionResponse;
  };

export type UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteResponse =
  UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteResponses[keyof UninstallCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameDeleteResponses];

export type GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetData = {
  body?: never;
  path: {
    /**
     * 分机名称
     *
     * 画布扩展名（小写字母数字，连字符）
     */
    extension_name: string;
  };
  query?: never;
  url: '/api/canvas-extensions/installed/{extension_name}';
};

export type GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetErrors =
  {
    /**
     * 画布扩展未安装
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetError =
  GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetErrors[keyof GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetErrors];

export type GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetResponses =
  {
    /**
     * 成功回应
     */
    200: InstalledCanvasExtensionResponse;
  };

export type GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetResponse =
  GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetResponses[keyof GetInstalledCanvasExtensionEndpointApiCanvasExtensionsInstalledExtensionNameGetResponses];

export type SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchData = {
  body: UpdateCanvasExtensionStateRequest;
  path: {
    /**
     * 分机名称
     *
     * 画布扩展名（小写字母数字，连字符）
     */
    extension_name: string;
  };
  query?: never;
  url: '/api/canvas-extensions/installed/{extension_name}';
};

export type SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchErrors =
  {
    /**
     * 画布扩展未安装
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchError =
  SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchErrors[keyof SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchErrors];

export type SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchResponses =
  {
    /**
     * 成功回应
     */
    200: UpdateCanvasExtensionStateResponse;
  };

export type SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchResponse =
  SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchResponses[keyof SetCanvasExtensionEnabledEndpointApiCanvasExtensionsInstalledExtensionNamePatchResponses];

export type GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetData =
  {
    body?: never;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/backend';
  };

export type GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetError =
  GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetErrors[keyof GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetErrors];

export type GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetResponses =
  {
    /**
     * 成功回应
     */
    200: BackendStatus;
  };

export type GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetResponse =
  GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetResponses[keyof GetCanvasExtensionBackendStatusEndpointApiCanvasExtensionsInstalledExtensionNameBackendGetResponses];

export type DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteData =
  {
    body?: never;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/backend/data';
  };

export type DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteErrors =
  {
    /**
     * 必须先停止后端
     */
    409: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteError =
  DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteErrors[keyof DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteErrors];

export type DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteResponses =
  {
    /**
     * 成功回应
     */
    200: BackendStatus;
  };

export type DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteResponse =
  DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteResponses[keyof DeleteCanvasExtensionBackendDataEndpointApiCanvasExtensionsInstalledExtensionNameBackendDataDeleteResponses];

export type GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetData =
  {
    body?: never;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: {
      /**
       * 限制字节数
       */
      limit_bytes?: number;
    };
    url: '/api/canvas-extensions/installed/{extension_name}/backend/logs';
  };

export type GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetError =
  GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetErrors[keyof GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetErrors];

export type GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetResponses =
  {
    /**
     * 成功回应
     */
    200: BackendLogs;
  };

export type GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetResponse =
  GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetResponses[keyof GetCanvasExtensionBackendLogsEndpointApiCanvasExtensionsInstalledExtensionNameBackendLogsGetResponses];

export type PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostData =
  {
    body: BackendRevisionRequest;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/backend/prepare';
  };

export type PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostErrors =
  {
    /**
     * 修订或校验和批准冲突
     */
    409: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostError =
  PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostErrors[keyof PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostErrors];

export type PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostResponses =
  {
    /**
     * 成功回应
     */
    200: BackendStatus;
  };

export type PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostResponse =
  PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostResponses[keyof PrepareCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendPreparePostResponses];

export type StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostData =
  {
    body: BackendRevisionRequest;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/backend/start';
  };

export type StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostErrors =
  {
    /**
     * 修订未准备好或无法开始
     */
    409: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostError =
  StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostErrors[keyof StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostErrors];

export type StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostResponses =
  {
    /**
     * 成功回应
     */
    200: BackendStatus;
  };

export type StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostResponse =
  StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostResponses[keyof StartCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStartPostResponses];

export type StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostData =
  {
    body?: never;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/backend/stop';
  };

export type StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostError =
  StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostErrors[keyof StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostErrors];

export type StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostResponses =
  {
    /**
     * 成功回应
     */
    200: BackendStatus;
  };

export type StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostResponse =
  StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostResponses[keyof StopCanvasExtensionBackendEndpointApiCanvasExtensionsInstalledExtensionNameBackendStopPostResponses];

export type GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetData =
  {
    body?: never;
    path: {
      /**
       * 分机名称
       *
       * 画布扩展名（小写字母数字，连字符）
       */
      extension_name: string;
    };
    query?: never;
    url: '/api/canvas-extensions/installed/{extension_name}/bundle';
  };

export type GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetErrors =
  {
    /**
     * 找不到画布扩展或捆绑包
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetError =
  GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetErrors[keyof GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetErrors];

export type GetCanvasExtensionBundleEndpointApiCanvasExtensionsInstalledExtensionNameBundleGetResponses =
  {
    /**
     * 成功回应
     */
    200: unknown;
  };

export type GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetData = {
  body?: never;
  path: {
    /**
     * 分机名称
     *
     * 画布扩展名（小写字母数字，连字符）
     */
    extension_name: string;
  };
  query?: never;
  url: '/api/canvas-extensions/installed/{extension_name}/icon';
};

export type GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetErrors = {
  /**
   * 找不到画布扩展或图标
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetError =
  GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetErrors[keyof GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetErrors];

export type GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetResponses =
  {
    /**
     * 成功回应
     */
    200: Blob | File;
  };

export type GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetResponse =
  GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetResponses[keyof GetCanvasExtensionIconEndpointApiCanvasExtensionsInstalledExtensionNameIconGetResponses];

export type BatchGetConversationsApiConversationsGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 识别号
     */
    ids: Array<string>;
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations';
};

export type BatchGetConversationsApiConversationsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type BatchGetConversationsApiConversationsGetError =
  BatchGetConversationsApiConversationsGetErrors[keyof BatchGetConversationsApiConversationsGetErrors];

export type BatchGetConversationsApiConversationsGetResponses = {
  /**
   * 响应批量获取对话 API 对话获取
   *
   * 成功回应
   */
  200: Array<ConversationInfo | null>;
};

export type BatchGetConversationsApiConversationsGetResponse =
  BatchGetConversationsApiConversationsGetResponses[keyof BatchGetConversationsApiConversationsGetResponses];

export type StartConversationApiConversationsPostData = {
  body: StartConversationRequestWritable;
  headers?: {
    /**
     * X-OpenHands-可观测性-跨度-名称
     */
    'X-OpenHands-Observability-Span-Name'?: string | null;
    /**
     * X-OpenHands-可观察性-标签
     */
    'X-OpenHands-Observability-Tags'?: string | null;
    /**
     * X-OpenHands-可观测性-元数据
     */
    'X-OpenHands-Observability-Metadata'?: string | null;
    /**
     * X-OpenHands-可观察性-父跨度-上下文
     */
    'X-OpenHands-Observability-Parent-Span-Context'?: string | null;
  };
  path?: never;
  query?: {
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations';
};

export type StartConversationApiConversationsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 服务器会话运行容量已满
   */
  429: unknown;
};

export type StartConversationApiConversationsPostError =
  StartConversationApiConversationsPostErrors[keyof StartConversationApiConversationsPostErrors];

export type StartConversationApiConversationsPostResponses = {
  /**
   * 成功回应
   */
  200: ConversationInfo;
};

export type StartConversationApiConversationsPostResponse =
  StartConversationApiConversationsPostResponses[keyof StartConversationApiConversationsPostResponses];

export type CountConversationsApiConversationsCountGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 按对话执行状态进行可选过滤
     */
    status?: ConversationExecutionStatus | null;
  };
  url: '/api/conversations/count';
};

export type CountConversationsApiConversationsCountGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CountConversationsApiConversationsCountGetError =
  CountConversationsApiConversationsCountGetErrors[keyof CountConversationsApiConversationsCountGetErrors];

export type CountConversationsApiConversationsCountGetResponses = {
  /**
   * 响应计数对话 API 对话计数获取
   *
   * 成功回应
   */
  200: number;
};

export type CountConversationsApiConversationsCountGetResponse =
  CountConversationsApiConversationsCountGetResponses[keyof CountConversationsApiConversationsCountGetResponses];

export type SearchConversationsApiConversationsSearchGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 先前返回的页面中的可选 next_page_id
     */
    page_id?: string | null;
    /**
     * 页面中的最大结果数
     */
    limit?: number;
    /**
     * 按对话执行状态进行可选过滤
     */
    status?: ConversationExecutionStatus | null;
    /**
     * 对话的排序顺序
     */
    sort_order?: ConversationSortOrder;
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations/search';
};

export type SearchConversationsApiConversationsSearchGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SearchConversationsApiConversationsSearchGetError =
  SearchConversationsApiConversationsSearchGetErrors[keyof SearchConversationsApiConversationsSearchGetErrors];

export type SearchConversationsApiConversationsSearchGetResponses = {
  /**
   * 成功回应
   */
  200: ConversationPage;
};

export type SearchConversationsApiConversationsSearchGetResponse =
  SearchConversationsApiConversationsSearchGetResponses[keyof SearchConversationsApiConversationsSearchGetResponses];

export type DeleteConversationApiConversationsConversationIdDeleteData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}';
};

export type DeleteConversationApiConversationsConversationIdDeleteErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteConversationApiConversationsConversationIdDeleteError =
  DeleteConversationApiConversationsConversationIdDeleteErrors[keyof DeleteConversationApiConversationsConversationIdDeleteErrors];

export type DeleteConversationApiConversationsConversationIdDeleteResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type DeleteConversationApiConversationsConversationIdDeleteResponse =
  DeleteConversationApiConversationsConversationIdDeleteResponses[keyof DeleteConversationApiConversationsConversationIdDeleteResponses];

export type GetConversationApiConversationsConversationIdGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: {
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations/{conversation_id}';
};

export type GetConversationApiConversationsConversationIdGetErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetConversationApiConversationsConversationIdGetError =
  GetConversationApiConversationsConversationIdGetErrors[keyof GetConversationApiConversationsConversationIdGetErrors];

export type GetConversationApiConversationsConversationIdGetResponses = {
  /**
   * 成功回应
   */
  200: ConversationInfo;
};

export type GetConversationApiConversationsConversationIdGetResponse =
  GetConversationApiConversationsConversationIdGetResponses[keyof GetConversationApiConversationsConversationIdGetResponses];

export type UpdateConversationApiConversationsConversationIdPatchData = {
  body: UpdateConversationRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}';
};

export type UpdateConversationApiConversationsConversationIdPatchErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UpdateConversationApiConversationsConversationIdPatchError =
  UpdateConversationApiConversationsConversationIdPatchErrors[keyof UpdateConversationApiConversationsConversationIdPatchErrors];

export type UpdateConversationApiConversationsConversationIdPatchResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type UpdateConversationApiConversationsConversationIdPatchResponse =
  UpdateConversationApiConversationsConversationIdPatchResponses[keyof UpdateConversationApiConversationsConversationIdPatchResponses];

export type GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetData =
  {
    body?: never;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{conversation_id}/agent_final_response';
  };

export type GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetErrors =
  {
    /**
     * 找不到对话
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetError =
  GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetErrors[keyof GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetErrors];

export type GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetResponses =
  {
    /**
     * 成功回应
     */
    200: AgentResponseResult;
  };

export type GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetResponse =
  GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetResponses[keyof GetConversationAgentFinalResponseApiConversationsConversationIdAgentFinalResponseGetResponses];

export type AskAgentApiConversationsConversationIdAskAgentPostData = {
  body: AskAgentRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/ask_agent';
};

export type AskAgentApiConversationsConversationIdAskAgentPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type AskAgentApiConversationsConversationIdAskAgentPostError =
  AskAgentApiConversationsConversationIdAskAgentPostErrors[keyof AskAgentApiConversationsConversationIdAskAgentPostErrors];

export type AskAgentApiConversationsConversationIdAskAgentPostResponses = {
  /**
   * 成功回应
   */
  200: AskAgentResponse;
};

export type AskAgentApiConversationsConversationIdAskAgentPostResponse =
  AskAgentApiConversationsConversationIdAskAgentPostResponses[keyof AskAgentApiConversationsConversationIdAskAgentPostResponses];

export type StartChildConversationApiConversationsConversationIdChildrenPostData = {
  body: StartChildConversationRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/children';
};

export type StartChildConversationApiConversationsConversationIdChildrenPostErrors = {
  /**
   * 找不到家长对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 服务器会话运行容量已满
   */
  429: unknown;
};

export type StartChildConversationApiConversationsConversationIdChildrenPostError =
  StartChildConversationApiConversationsConversationIdChildrenPostErrors[keyof StartChildConversationApiConversationsConversationIdChildrenPostErrors];

export type StartChildConversationApiConversationsConversationIdChildrenPostResponses = {
  /**
   * 已创建儿童对话
   */
  201: StartChildConversationResponse;
};

export type StartChildConversationApiConversationsConversationIdChildrenPostResponse =
  StartChildConversationApiConversationsConversationIdChildrenPostResponses[keyof StartChildConversationApiConversationsConversationIdChildrenPostResponses];

export type CondenseConversationApiConversationsConversationIdCondensePostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/condense';
};

export type CondenseConversationApiConversationsConversationIdCondensePostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 智能体没有上下文压缩器处理请求
   */
  409: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CondenseConversationApiConversationsConversationIdCondensePostError =
  CondenseConversationApiConversationsConversationIdCondensePostErrors[keyof CondenseConversationApiConversationsConversationIdCondensePostErrors];

export type CondenseConversationApiConversationsConversationIdCondensePostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type CondenseConversationApiConversationsConversationIdCondensePostResponse =
  CondenseConversationApiConversationsConversationIdCondensePostResponses[keyof CondenseConversationApiConversationsConversationIdCondensePostResponses];

export type SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostData =
  {
    body: SetConfirmationPolicyRequest;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{conversation_id}/confirmation_policy';
  };

export type SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostErrors =
  {
    /**
     * 未找到项目
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostError =
  SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostErrors[keyof SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostErrors];

export type SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostResponses =
  {
    /**
     * 成功回应
     */
    200: Success;
  };

export type SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostResponse =
  SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostResponses[keyof SetConversationConfirmationPolicyApiConversationsConversationIdConfirmationPolicyPostResponses];

export type BatchGetConversationEventsApiConversationsConversationIdEventsGetData = {
  /**
   * 事件 ID
   */
  body: Array<string>;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/events';
};

export type BatchGetConversationEventsApiConversationsConversationIdEventsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type BatchGetConversationEventsApiConversationsConversationIdEventsGetError =
  BatchGetConversationEventsApiConversationsConversationIdEventsGetErrors[keyof BatchGetConversationEventsApiConversationsConversationIdEventsGetErrors];

export type BatchGetConversationEventsApiConversationsConversationIdEventsGetResponses = {
  /**
   * 响应批量获取对话事件 API 对话对话 ID 事件获取
   *
   * 成功回应
   */
  200: Array<Event | null>;
};

export type BatchGetConversationEventsApiConversationsConversationIdEventsGetResponse =
  BatchGetConversationEventsApiConversationsConversationIdEventsGetResponses[keyof BatchGetConversationEventsApiConversationsConversationIdEventsGetResponses];

export type SendMessageApiConversationsConversationIdEventsPostData = {
  body: SendMessageRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/events';
};

export type SendMessageApiConversationsConversationIdEventsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 消息已保存，但服务器运行容量已满
   */
  429: unknown;
};

export type SendMessageApiConversationsConversationIdEventsPostError =
  SendMessageApiConversationsConversationIdEventsPostErrors[keyof SendMessageApiConversationsConversationIdEventsPostErrors];

export type SendMessageApiConversationsConversationIdEventsPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type SendMessageApiConversationsConversationIdEventsPostResponse =
  SendMessageApiConversationsConversationIdEventsPostResponses[keyof SendMessageApiConversationsConversationIdEventsPostResponses];

export type CountConversationEventsApiConversationsConversationIdEventsCountGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: {
    /**
     * 按事件种类/类型的可选过滤器（e.g.、ActionEvent、MessageEvent）
     */
    kind?: string | null;
    /**
     * 可选按事件源过滤（e.g.、智能体、用户、环境）
     */
    source?: string | null;
    /**
     * 可选按消息内容过滤（不区分大小写）
     */
    body?: string | null;
    /**
     * 过滤器：事件时间戳 >= 此日期时间
     */
    timestamp__gte?: string | null;
    /**
     * 过滤器：事件时间戳 < 此日期时间
     */
    timestamp__lt?: string | null;
  };
  url: '/api/conversations/{conversation_id}/events/count';
};

export type CountConversationEventsApiConversationsConversationIdEventsCountGetErrors = {
  /**
   * 找不到对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CountConversationEventsApiConversationsConversationIdEventsCountGetError =
  CountConversationEventsApiConversationsConversationIdEventsCountGetErrors[keyof CountConversationEventsApiConversationsConversationIdEventsCountGetErrors];

export type CountConversationEventsApiConversationsConversationIdEventsCountGetResponses = {
  /**
   * 响应计数对话事件 API 对话对话 ID 事件计数获取
   *
   * 成功回应
   */
  200: number;
};

export type CountConversationEventsApiConversationsConversationIdEventsCountGetResponse =
  CountConversationEventsApiConversationsConversationIdEventsCountGetResponses[keyof CountConversationEventsApiConversationsConversationIdEventsCountGetResponses];

export type RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostData =
  {
    body: ConfirmationResponseRequest;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{conversation_id}/events/respond_to_confirmation';
  };

export type RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostErrors =
  {
    /**
     * 未找到项目
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
    /**
     * 服务器会话运行容量已满
     */
    429: unknown;
  };

export type RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostError =
  RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostErrors[keyof RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostErrors];

export type RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostResponses =
  {
    /**
     * 成功回应
     */
    200: Success;
  };

export type RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostResponse =
  RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostResponses[keyof RespondToConfirmationApiConversationsConversationIdEventsRespondToConfirmationPostResponses];

export type SearchConversationEventsApiConversationsConversationIdEventsSearchGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: {
    /**
     * 先前返回的页面中的可选 next_page_id
     */
    page_id?: string | null;
    /**
     * 页面中的最大结果数
     */
    limit?: number;
    /**
     * 按事件种类/类型的可选过滤器（e.g.、ActionEvent、MessageEvent）
     */
    kind?: string | null;
    /**
     * 可选按事件源过滤（e.g.、智能体、用户、环境）
     */
    source?: string | null;
    /**
     * 可选按消息内容过滤（不区分大小写）
     */
    body?: string | null;
    /**
     * 事件排序
     */
    sort_order?: EventSortOrder;
    /**
     * 过滤器：事件时间戳 >= 此日期时间
     */
    timestamp__gte?: string | null;
    /**
     * 过滤器：事件时间戳 < 此日期时间
     */
    timestamp__lt?: string | null;
  };
  url: '/api/conversations/{conversation_id}/events/search';
};

export type SearchConversationEventsApiConversationsConversationIdEventsSearchGetErrors = {
  /**
   * 找不到对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SearchConversationEventsApiConversationsConversationIdEventsSearchGetError =
  SearchConversationEventsApiConversationsConversationIdEventsSearchGetErrors[keyof SearchConversationEventsApiConversationsConversationIdEventsSearchGetErrors];

export type SearchConversationEventsApiConversationsConversationIdEventsSearchGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type GetConversationEventApiConversationsConversationIdEventsEventIdGetData = {
  body?: never;
  path: {
    /**
     * 事件 ID
     */
    event_id: string;
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/events/{event_id}';
};

export type GetConversationEventApiConversationsConversationIdEventsEventIdGetErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetConversationEventApiConversationsConversationIdEventsEventIdGetError =
  GetConversationEventApiConversationsConversationIdEventsEventIdGetErrors[keyof GetConversationEventApiConversationsConversationIdEventsEventIdGetErrors];

export type GetConversationEventApiConversationsConversationIdEventsEventIdGetResponses = {
  /**
   * 成功回应
   */
  200: Event;
};

export type GetConversationEventApiConversationsConversationIdEventsEventIdGetResponse =
  GetConversationEventApiConversationsConversationIdEventsEventIdGetResponses[keyof GetConversationEventApiConversationsConversationIdEventsEventIdGetResponses];

export type ForkConversationApiConversationsConversationIdForkPostData = {
  body?: ForkConversationRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: {
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations/{conversation_id}/fork';
};

export type ForkConversationApiConversationsConversationIdForkPostErrors = {
  /**
   * 未找到源对话
   */
  404: unknown;
  /**
   * 分叉 ID 已被使用
   */
  409: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ForkConversationApiConversationsConversationIdForkPostError =
  ForkConversationApiConversationsConversationIdForkPostErrors[keyof ForkConversationApiConversationsConversationIdForkPostErrors];

export type ForkConversationApiConversationsConversationIdForkPostResponses = {
  /**
   * 创建了分叉对话
   */
  201: ConversationInfo;
};

export type ForkConversationApiConversationsConversationIdForkPostResponse =
  ForkConversationApiConversationsConversationIdForkPostResponses[keyof ForkConversationApiConversationsConversationIdForkPostResponses];

export type StartGoalInConversationApiConversationsConversationIdGoalPostData = {
  body: StartGoalRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/goal';
};

export type StartGoalInConversationApiConversationsConversationIdGoalPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 对话运行或目标循环已在运行
   */
  409: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 服务器会话运行容量已满
   */
  429: unknown;
};

export type StartGoalInConversationApiConversationsConversationIdGoalPostError =
  StartGoalInConversationApiConversationsConversationIdGoalPostErrors[keyof StartGoalInConversationApiConversationsConversationIdGoalPostErrors];

export type StartGoalInConversationApiConversationsConversationIdGoalPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type StartGoalInConversationApiConversationsConversationIdGoalPostResponse =
  StartGoalInConversationApiConversationsConversationIdGoalPostResponses[keyof StartGoalInConversationApiConversationsConversationIdGoalPostResponses];

export type ResumeGoalInConversationApiConversationsConversationIdGoalResumePostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/goal/resume';
};

export type ResumeGoalInConversationApiConversationsConversationIdGoalResumePostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 对话运行或目标循环已在运行
   */
  409: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 服务器会话运行容量已满
   */
  429: unknown;
};

export type ResumeGoalInConversationApiConversationsConversationIdGoalResumePostError =
  ResumeGoalInConversationApiConversationsConversationIdGoalResumePostErrors[keyof ResumeGoalInConversationApiConversationsConversationIdGoalResumePostErrors];

export type ResumeGoalInConversationApiConversationsConversationIdGoalResumePostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type ResumeGoalInConversationApiConversationsConversationIdGoalResumePostResponse =
  ResumeGoalInConversationApiConversationsConversationIdGoalResumePostResponses[keyof ResumeGoalInConversationApiConversationsConversationIdGoalResumePostResponses];

export type StopGoalInConversationApiConversationsConversationIdGoalStopPostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/goal/stop';
};

export type StopGoalInConversationApiConversationsConversationIdGoalStopPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type StopGoalInConversationApiConversationsConversationIdGoalStopPostError =
  StopGoalInConversationApiConversationsConversationIdGoalStopPostErrors[keyof StopGoalInConversationApiConversationsConversationIdGoalStopPostErrors];

export type StopGoalInConversationApiConversationsConversationIdGoalStopPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type StopGoalInConversationApiConversationsConversationIdGoalStopPostResponse =
  StopGoalInConversationApiConversationsConversationIdGoalStopPostResponses[keyof StopGoalInConversationApiConversationsConversationIdGoalStopPostResponses];

export type InterruptConversationApiConversationsConversationIdInterruptPostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/interrupt';
};

export type InterruptConversationApiConversationsConversationIdInterruptPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type InterruptConversationApiConversationsConversationIdInterruptPostError =
  InterruptConversationApiConversationsConversationIdInterruptPostErrors[keyof InterruptConversationApiConversationsConversationIdInterruptPostErrors];

export type InterruptConversationApiConversationsConversationIdInterruptPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type InterruptConversationApiConversationsConversationIdInterruptPostResponse =
  InterruptConversationApiConversationsConversationIdInterruptPostResponses[keyof InterruptConversationApiConversationsConversationIdInterruptPostResponses];

export type LoadConversationPluginApiConversationsConversationIdLoadPluginPostData = {
  body: BodyLoadConversationPluginApiConversationsConversationIdLoadPluginPost;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/load_plugin';
};

export type LoadConversationPluginApiConversationsConversationIdLoadPluginPostErrors = {
  /**
   * 无效的插件参考或非活动对话
   */
  400: unknown;
  /**
   * 未找到对话或插件
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type LoadConversationPluginApiConversationsConversationIdLoadPluginPostError =
  LoadConversationPluginApiConversationsConversationIdLoadPluginPostErrors[keyof LoadConversationPluginApiConversationsConversationIdLoadPluginPostErrors];

export type LoadConversationPluginApiConversationsConversationIdLoadPluginPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type LoadConversationPluginApiConversationsConversationIdLoadPluginPostResponse =
  LoadConversationPluginApiConversationsConversationIdLoadPluginPostResponses[keyof LoadConversationPluginApiConversationsConversationIdLoadPluginPostResponses];

export type NavigateConversationApiConversationsConversationIdNavigatePostData = {
  body: NavigateConversationRequest;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: {
    /**
     * 响应中是否包含``agent.agent_context.skills``。 ``false`` 默认值：不兼容变更版本：技能仅在 ``[]`` 响应中被截断，因为没有已知的消费者从 HTTP 响应中读取它们。智能体通常每次请求会 inline ~260 KB 的技能内容。 通过 ``true`` 选择回到传统的完整载荷形状 - 仅对于仍然依赖 ``RemoteConversation.agent.agent_context.skills`` 线路往返的调用者有用。 无论哪种方式，磁盘上的已持久化会话状态和内存中的运行时副本都保持不变。
     */
    include_skills?: boolean;
  };
  url: '/api/conversations/{conversation_id}/navigate';
};

export type NavigateConversationApiConversationsConversationIdNavigatePostErrors = {
  /**
   * 未找到对话或事件
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type NavigateConversationApiConversationsConversationIdNavigatePostError =
  NavigateConversationApiConversationsConversationIdNavigatePostErrors[keyof NavigateConversationApiConversationsConversationIdNavigatePostErrors];

export type NavigateConversationApiConversationsConversationIdNavigatePostResponses = {
  /**
   * 成功回应
   */
  200: ConversationInfo;
};

export type NavigateConversationApiConversationsConversationIdNavigatePostResponse =
  NavigateConversationApiConversationsConversationIdNavigatePostResponses[keyof NavigateConversationApiConversationsConversationIdNavigatePostResponses];

export type PauseConversationApiConversationsConversationIdPausePostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/pause';
};

export type PauseConversationApiConversationsConversationIdPausePostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type PauseConversationApiConversationsConversationIdPausePostError =
  PauseConversationApiConversationsConversationIdPausePostErrors[keyof PauseConversationApiConversationsConversationIdPausePostErrors];

export type PauseConversationApiConversationsConversationIdPausePostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type PauseConversationApiConversationsConversationIdPausePostResponse =
  PauseConversationApiConversationsConversationIdPausePostResponses[keyof PauseConversationApiConversationsConversationIdPausePostResponses];

export type RunConversationApiConversationsConversationIdRunPostData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/run';
};

export type RunConversationApiConversationsConversationIdRunPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 对话已经开始
   */
  409: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * 服务器会话运行容量已满
   */
  429: unknown;
};

export type RunConversationApiConversationsConversationIdRunPostError =
  RunConversationApiConversationsConversationIdRunPostErrors[keyof RunConversationApiConversationsConversationIdRunPostErrors];

export type RunConversationApiConversationsConversationIdRunPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type RunConversationApiConversationsConversationIdRunPostResponse =
  RunConversationApiConversationsConversationIdRunPostResponses[keyof RunConversationApiConversationsConversationIdRunPostResponses];

export type GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/runtime';
};

export type GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetError =
  GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetErrors[keyof GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetErrors];

export type GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetResponses = {
  /**
   * 成功回应
   */
  200: ConversationRuntimeInfo;
};

export type GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetResponse =
  GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetResponses[keyof GetLocalConversationRuntimeApiConversationsConversationIdRuntimeGetResponses];

export type ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostData =
  {
    body?: never;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{conversation_id}/runtime/reprovision';
  };

export type ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostError =
  ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostErrors[keyof ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostErrors];

export type ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostResponses =
  {
    /**
     * 成功回应
     */
    200: ConversationRuntimeInfo;
  };

export type ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostResponse =
  ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostResponses[keyof ReprovisionLocalConversationRuntimeApiConversationsConversationIdRuntimeReprovisionPostResponses];

export type UpdateConversationSecretsApiConversationsConversationIdSecretsPostData = {
  body: UpdateSecretsRequestWritable;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/secrets';
};

export type UpdateConversationSecretsApiConversationsConversationIdSecretsPostErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UpdateConversationSecretsApiConversationsConversationIdSecretsPostError =
  UpdateConversationSecretsApiConversationsConversationIdSecretsPostErrors[keyof UpdateConversationSecretsApiConversationsConversationIdSecretsPostErrors];

export type UpdateConversationSecretsApiConversationsConversationIdSecretsPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type UpdateConversationSecretsApiConversationsConversationIdSecretsPostResponse =
  UpdateConversationSecretsApiConversationsConversationIdSecretsPostResponses[keyof UpdateConversationSecretsApiConversationsConversationIdSecretsPostResponses];

export type SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostData =
  {
    body: SetSecurityAnalyzerRequestWritable;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{conversation_id}/security_analyzer';
  };

export type SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostErrors =
  {
    /**
     * 未找到项目
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostError =
  SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostErrors[keyof SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostErrors];

export type SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostResponses =
  {
    /**
     * 成功回应
     */
    200: Success;
  };

export type SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostResponse =
  SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostResponses[keyof SetConversationSecurityAnalyzerApiConversationsConversationIdSecurityAnalyzerPostResponses];

export type SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostData = {
  body: BodySwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPost;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/switch_acp_model';
};

export type SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostErrors = {
  /**
   * 智能体不是 ACP，或者提供商无法切换型号
   */
  400: unknown;
  /**
   * 找不到对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
  /**
   * ACP服务器未及时应答模型切换
   */
  504: unknown;
};

export type SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostError =
  SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostErrors[keyof SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostErrors];

export type SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostResponse =
  SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostResponses[keyof SwitchConversationAcpModelApiConversationsConversationIdSwitchAcpModelPostResponses];

export type SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostData = {
  body: BodySwitchConversationLlmApiConversationsConversationIdSwitchLlmPostWritable;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/switch_llm';
};

export type SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostErrors = {
  /**
   * 找不到对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostError =
  SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostErrors[keyof SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostErrors];

export type SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostResponse =
  SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostResponses[keyof SwitchConversationLlmApiConversationsConversationIdSwitchLlmPostResponses];

export type SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostData = {
  body: BodySwitchConversationProfileApiConversationsConversationIdSwitchProfilePost;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/switch_profile';
};

export type SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostErrors = {
  /**
   * 配置文件无效或损坏
   */
  400: unknown;
  /**
   * 找不到对话或个人资料
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostError =
  SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostErrors[keyof SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostErrors];

export type SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostResponse =
  SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostResponses[keyof SwitchConversationProfileApiConversationsConversationIdSwitchProfilePostResponses];

export type ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/workspace';
};

export type ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetErrors = {
  /**
   * 找不到文件或对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetError =
  ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetErrors[keyof ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetErrors];

export type ServeWorkspaceRootApiConversationsConversationIdWorkspaceGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
    /**
     * 文件路径
     */
    file_path: string;
  };
  query?: never;
  url: '/api/conversations/{conversation_id}/workspace/{file_path}';
};

export type ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetErrors = {
  /**
   * 找不到文件或对话
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetError =
  ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetErrors[keyof ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetErrors];

export type ServeWorkspaceFileApiConversationsConversationIdWorkspaceFilePathGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostData =
  {
    body?: never;
    path: {
      /**
       * 命令 ID
       */
      command_id: string;
      /**
       * 运行时对话 ID
       */
      runtime_conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{runtime_conversation_id}/bash/bash_commands/{command_id}/stop';
  };

export type StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostErrors =
  {
    /**
     * 未找到项目
     */
    404: unknown;
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostError =
  StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostErrors[keyof StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostErrors];

export type StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostResponses =
  {
    /**
     * 成功回应
     */
    200: Success;
  };

export type StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostResponse =
  StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostResponses[keyof StopBashCommandApiConversationsRuntimeConversationIdBashBashCommandsCommandIdStopPostResponses];

export type ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{runtime_conversation_id}/bash/bash_events';
};

export type ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteError =
  ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteErrors[keyof ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteErrors];

export type ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteResponses = {
  /**
   * 响应清除所有 Bash 事件 API 对话运行时对话 ID Bash Bash 事件删除
   *
   * 成功回应
   */
  200: {
    [key: string]: number;
  };
};

export type ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteResponse =
  ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteResponses[keyof ClearAllBashEventsApiConversationsRuntimeConversationIdBashBashEventsDeleteResponses];

export type BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetData = {
  /**
   * 事件 ID
   */
  body: Array<string>;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{runtime_conversation_id}/bash/bash_events/';
};

export type BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetError =
  BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetErrors[keyof BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetErrors];

export type BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetResponses = {
  /**
   * 响应批量获取 Bash 事件 API 对话运行时对话 Id Bash Bash 事件获取
   *
   * 成功回应
   */
  200: Array<BashEventBase | null>;
};

export type BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetResponse =
  BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetResponses[keyof BatchGetBashEventsApiConversationsRuntimeConversationIdBashBashEventsGetResponses];

export type SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: {
    /**
     * 种类情商
     */
    kind__eq?: 'BashCommand' | 'BashOutput' | null;
    /**
     * 命令 ID 等式
     */
    command_id__eq?: string | null;
    /**
     * 时间戳GTE
     */
    timestamp__gte?: string | null;
    /**
     * 时间戳LT
     */
    timestamp__lt?: string | null;
    /**
     * 过滤顺序大于此值的事件
     *
     * 仅返回顺序 > 该值的 BashOutput 个事件。 对于轮询来说非常有用，可以仅获取自上次轮询以来的新事件。
     */
    order__gt?: number | null;
    sort_order?: BashEventSortOrder;
    /**
     * 先前返回的页面中的可选 next_page_id
     */
    page_id?: string | null;
    /**
     * 页面中的最大结果数
     */
    limit?: number;
  };
  url: '/api/conversations/{runtime_conversation_id}/bash/bash_events/search';
};

export type SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetError =
  SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetErrors[keyof SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetErrors];

export type SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetResponses =
  {
    /**
     * 成功回应
     */
    200: BashEventPage;
  };

export type SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetResponse =
  SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetResponses[keyof SearchBashEventsApiConversationsRuntimeConversationIdBashBashEventsSearchGetResponses];

export type GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetData = {
  body?: never;
  path: {
    /**
     * 事件 ID
     */
    event_id: string;
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{runtime_conversation_id}/bash/bash_events/{event_id}';
};

export type GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetErrors = {
  /**
   * 未找到项目
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetError =
  GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetErrors[keyof GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetErrors];

export type GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetResponses = {
  /**
   * 成功回应
   */
  200: BashEventBase;
};

export type GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetResponse =
  GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetResponses[keyof GetBashEventApiConversationsRuntimeConversationIdBashBashEventsEventIdGetResponses];

export type ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostData =
  {
    body: ExecuteBashRequest;
    path: {
      /**
       * 运行时对话 ID
       */
      runtime_conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{runtime_conversation_id}/bash/execute_bash_command';
  };

export type ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostError =
  ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostErrors[keyof ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostErrors];

export type ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostResponses =
  {
    /**
     * 成功回应
     */
    200: BashOutput;
  };

export type ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostResponse =
  ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostResponses[keyof ExecuteBashCommandApiConversationsRuntimeConversationIdBashExecuteBashCommandPostResponses];

export type StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostData = {
  body: ExecuteBashRequest;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{runtime_conversation_id}/bash/start_bash_command';
};

export type StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostError =
  StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostErrors[keyof StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostErrors];

export type StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostResponses =
  {
    /**
     * 成功回应
     */
    200: BashCommand;
  };

export type StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostResponse =
  StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostResponses[keyof StartBashCommandApiConversationsRuntimeConversationIdBashStartBashCommandPostResponses];

export type ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * 要归档的目录的绝对路径。 如果不是git仓库，而是恰好有一个git仓库（最多向下三个层级），则该仓库将被归档，无论格式。 传递存储库本身或包含零个或多个存储库的目录来控制存档的内容。
     */
    path: string;
    /**
     * 格式
     *
     * 存档格式：“git-delta”，用于针对基本引用更改工作树的 git 补丁（需要 git 存储库）； 'tar.gz' 用于文件的 gzip tarball（也适用于非 git 目录）。 两种格式都记录了路径下的目录，但有一个非仓库路径（最多向下三层，跳过隐藏和 vendored 目录），它包含的仓库会被记录，因此，它旁边的所有文件都不包括在内。 对于零个或多个存储库，目录按给定方式存档。
     */
    format?: 'git-delta' | 'tar.gz';
    /**
     * 基本参考
     *
     * 仅适用于 format='git-delta'：要进行比较的基本参考。 默认为自动检测的比较引用（原始分支、合并基础或新存储库的空树）。 忽略 format='tar.gz'。
     */
    base_ref?: string | null;
    /**
     * 使用默认排除
     *
     * 是否应用内置默认排除模式（node_modules/、.venv/、缓存、构建输出等）。 对于紧凑档案，默认为 True； 设置 False 以允许完整的工作区捕获，包括 fat 目录。
     */
    use_default_excludes?: boolean;
    /**
     * 排除
     *
     * 要排除的其他 glob 模式（可重复，e.g.?exclude=foo&exclude=*.bin）。 结合内置默认排除当use_default_excludes=True时； 当use_default_excludes=False时单独使用。
     */
    exclude?: Array<string> | null;
  };
  url: '/api/conversations/{runtime_conversation_id}/file/archive';
};

export type ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetError =
  ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetErrors[keyof ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetErrors];

export type ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetResponses = {
  /**
   * 成功回应
   */
  200: Blob | File;
};

export type ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetResponse =
  ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetResponses[keyof ArchiveDirectoryApiConversationsRuntimeConversationIdFileArchiveGetResponses];

export type CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * 创建的绝对目录路径
     */
    path: string;
  };
  url: '/api/conversations/{runtime_conversation_id}/file/create_directory';
};

export type CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostError =
  CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostErrors[keyof CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostErrors];

export type CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostResponse =
  CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostResponses[keyof CreateDirectoryApiConversationsRuntimeConversationIdFileCreateDirectoryPostResponses];

export type DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * 绝对文件路径
     */
    path: string;
  };
  url: '/api/conversations/{runtime_conversation_id}/file/download';
};

export type DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetError =
  DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetErrors[keyof DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetErrors];

export type DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetResponses = {
  /**
   * 成功回应
   */
  200: Blob | File;
};

export type DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetResponse =
  DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetResponses[keyof DownloadFileQueryApiConversationsRuntimeConversationIdFileDownloadGetResponses];

export type DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetData =
  {
    body?: never;
    path: {
      /**
       * 对话 ID
       */
      conversation_id: string;
      /**
       * 运行时对话 ID
       */
      runtime_conversation_id: string;
    };
    query?: never;
    url: '/api/conversations/{runtime_conversation_id}/file/download-trajectory/{conversation_id}';
  };

export type DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetError =
  DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetErrors[keyof DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetErrors];

export type DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetResponses =
  {
    /**
     * 成功回应
     */
    200: Blob | File;
  };

export type DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetResponse =
  DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetResponses[keyof DownloadTrajectoryApiConversationsRuntimeConversationIdFileDownloadTrajectoryConversationIdGetResponses];

export type UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostData = {
  body: BodyUploadFileQueryApiConversationsRuntimeConversationIdFileUploadPost;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * 绝对文件路径
     */
    path: string;
  };
  url: '/api/conversations/{runtime_conversation_id}/file/upload';
};

export type UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostError =
  UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostErrors[keyof UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostErrors];

export type UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostResponses = {
  /**
   * 成功回应
   */
  200: FileUploadResult;
};

export type UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostResponse =
  UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostResponses[keyof UploadFileQueryApiConversationsRuntimeConversationIdFileUploadPostResponses];

export type GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * git 存储库路径
     */
    path: string;
    /**
     * 参考号
     *
     * 可选的 git ref 来比较 (e.g. 'HEAD' 用于 git 状态样式更改，或提交哈希）。 省略时，将自动检测上游/默认分支。
     */
    ref?: string | null;
  };
  url: '/api/conversations/{runtime_conversation_id}/git/changes';
};

export type GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetError =
  GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetErrors[keyof GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetErrors];

export type GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetResponses = {
  /**
   * 响应 Git 更改查询 API 对话运行时对话 ID Git 更改获取
   *
   * 成功回应
   */
  200: Array<GitChange>;
};

export type GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetResponse =
  GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetResponses[keyof GitChangesQueryApiConversationsRuntimeConversationIdGitChangesGetResponses];

export type GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * git 存储库路径
     */
    path: string;
    /**
     * 限制
     *
     * 最大承诺返回
     */
    limit?: number;
  };
  url: '/api/conversations/{runtime_conversation_id}/git/commits';
};

export type GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetError =
  GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetErrors[keyof GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetErrors];

export type GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetResponses = {
  /**
   * 成功回应
   */
  200: GitCommitsPage;
};

export type GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetResponse =
  GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetResponses[keyof GitCommitsQueryApiConversationsRuntimeConversationIdGitCommitsGetResponses];

export type GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetData =
  {
    body?: never;
    path: {
      /**
       * 沙
       *
       * 提交 SHA
       */
      sha: string;
      /**
       * 运行时对话 ID
       */
      runtime_conversation_id: string;
    };
    query: {
      /**
       * 路径
       *
       * git 存储库路径
       */
      path: string;
    };
    url: '/api/conversations/{runtime_conversation_id}/git/commits/{sha}/changes';
  };

export type GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetErrors =
  {
    /**
     * 验证错误
     */
    422: HttpValidationError;
  };

export type GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetError =
  GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetErrors[keyof GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetErrors];

export type GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetResponses =
  {
    /**
     * 响应 Git 提交更改查询 API 对话运行时对话 ID Git 提交 Sha 更改获取
     *
     * 成功回应
     */
    200: Array<GitChange>;
  };

export type GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetResponse =
  GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetResponses[keyof GitCommitChangesQueryApiConversationsRuntimeConversationIdGitCommitsShaChangesGetResponses];

export type GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query: {
    /**
     * 路径
     *
     * 获取 diff 的文件路径
     */
    path: string;
    /**
     * 参考号
     *
     * 可选的 git ref 来比较 (e.g. 'HEAD' 用于 git 状态样式更改，或提交哈希）。 省略时，将自动检测上游/默认分支。
     */
    ref?: string | null;
    /**
     * 提交
     *
     * 可选提交 SHA。 设置后，差异是提交引入的更改（相对于其第一个父级），完全从 git 对象读取，因此删除的文件仍然呈现。 与“ref”互斥。
     */
    commit?: string | null;
  };
  url: '/api/conversations/{runtime_conversation_id}/git/diff';
};

export type GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetError =
  GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetErrors[keyof GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetErrors];

export type GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetResponses = {
  /**
   * 成功回应
   */
  200: GitDiff;
};

export type GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetResponse =
  GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetResponses[keyof GitDiffQueryApiConversationsRuntimeConversationIdGitDiffGetResponses];

export type GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: never;
  url: '/api/conversations/{runtime_conversation_id}/vscode/status';
};

export type GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetError =
  GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetErrors[keyof GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetErrors];

export type GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetResponses = {
  /**
   * 响应获取 Vscode 状态 API 对话运行时对话 ID Vscode 状态获取
   *
   * 成功回应
   */
  200: {
    [key: string]: boolean | string;
  };
};

export type GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetResponse =
  GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetResponses[keyof GetVscodeStatusApiConversationsRuntimeConversationIdVscodeStatusGetResponses];

export type GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetData = {
  body?: never;
  path: {
    /**
     * 运行时对话 ID
     */
    runtime_conversation_id: string;
  };
  query?: {
    /**
     * 基本网址
     */
    base_url?: string | null;
    /**
     * 工作区目录
     */
    workspace_dir?: string | null;
  };
  url: '/api/conversations/{runtime_conversation_id}/vscode/url';
};

export type GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetError =
  GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetErrors[keyof GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetErrors];

export type GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetResponses = {
  /**
   * 成功回应
   */
  200: VsCodeUrlResponse;
};

export type GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetResponse =
  GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetResponses[keyof GetRuntimeVscodeUrlApiConversationsRuntimeConversationIdVscodeUrlGetResponses];

export type ArchiveDirectoryApiFileArchiveGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 要归档的目录的绝对路径。 如果不是git仓库，而是恰好有一个git仓库（最多向下三个层级），则该仓库将被归档，无论格式。 传递存储库本身或包含零个或多个存储库的目录来控制存档的内容。
     */
    path: string;
    /**
     * 格式
     *
     * 存档格式：“git-delta”，用于针对基本引用更改工作树的 git 补丁（需要 git 存储库）； 'tar.gz' 用于文件的 gzip tarball（也适用于非 git 目录）。 两种格式都记录了路径下的目录，但有一个非仓库路径（最多向下三层，跳过隐藏和 vendored 目录），它包含的仓库会被记录，因此，它旁边的所有文件都不包括在内。 对于零个或多个存储库，目录按给定方式存档。
     */
    format?: 'git-delta' | 'tar.gz';
    /**
     * 基本参考
     *
     * 仅适用于 format='git-delta'：要进行比较的基本参考。 默认为自动检测的比较引用（原始分支、合并基础或新存储库的空树）。 忽略 format='tar.gz'。
     */
    base_ref?: string | null;
    /**
     * 使用默认排除
     *
     * 是否应用内置默认排除模式（node_modules/、.venv/、缓存、构建输出等）。 对于紧凑档案，默认为 True； 设置 False 以允许完整的工作区捕获，包括 fat 目录。
     */
    use_default_excludes?: boolean;
    /**
     * 排除
     *
     * 要排除的其他 glob 模式（可重复，e.g.?exclude=foo&exclude=*.bin）。 结合内置默认排除当use_default_excludes=True时； 当use_default_excludes=False时单独使用。
     */
    exclude?: Array<string> | null;
  };
  url: '/api/file/archive';
};

export type ArchiveDirectoryApiFileArchiveGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ArchiveDirectoryApiFileArchiveGetError =
  ArchiveDirectoryApiFileArchiveGetErrors[keyof ArchiveDirectoryApiFileArchiveGetErrors];

export type ArchiveDirectoryApiFileArchiveGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type CreateDirectoryApiFileCreateDirectoryPostData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 创建的绝对目录路径
     */
    path: string;
  };
  url: '/api/file/create_directory';
};

export type CreateDirectoryApiFileCreateDirectoryPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CreateDirectoryApiFileCreateDirectoryPostError =
  CreateDirectoryApiFileCreateDirectoryPostErrors[keyof CreateDirectoryApiFileCreateDirectoryPostErrors];

export type CreateDirectoryApiFileCreateDirectoryPostResponses = {
  /**
   * 成功回应
   */
  200: Success;
};

export type CreateDirectoryApiFileCreateDirectoryPostResponse =
  CreateDirectoryApiFileCreateDirectoryPostResponses[keyof CreateDirectoryApiFileCreateDirectoryPostResponses];

export type DownloadFileQueryApiFileDownloadGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 绝对文件路径
     */
    path: string;
  };
  url: '/api/file/download';
};

export type DownloadFileQueryApiFileDownloadGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DownloadFileQueryApiFileDownloadGetError =
  DownloadFileQueryApiFileDownloadGetErrors[keyof DownloadFileQueryApiFileDownloadGetErrors];

export type DownloadFileQueryApiFileDownloadGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetData = {
  body?: never;
  path: {
    /**
     * 对话 ID
     */
    conversation_id: string;
  };
  query?: never;
  url: '/api/file/download-trajectory/{conversation_id}';
};

export type DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetError =
  DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetErrors[keyof DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetErrors];

export type DownloadTrajectoryApiFileDownloadTrajectoryConversationIdGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type GetHomeDirectoryApiFileHomeGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 包括隐藏
     *
     * 在 `favorites` 中包含隐藏的顶级目录
     */
    include_hidden?: boolean;
  };
  url: '/api/file/home';
};

export type GetHomeDirectoryApiFileHomeGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetHomeDirectoryApiFileHomeGetError =
  GetHomeDirectoryApiFileHomeGetErrors[keyof GetHomeDirectoryApiFileHomeGetErrors];

export type GetHomeDirectoryApiFileHomeGetResponses = {
  /**
   * 成功回应
   */
  200: HomeResponse;
};

export type GetHomeDirectoryApiFileHomeGetResponse =
  GetHomeDirectoryApiFileHomeGetResponses[keyof GetHomeDirectoryApiFileHomeGetResponses];

export type SearchSubdirsApiFileSearchSubdirsGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 列出子目录的绝对目录路径
     */
    path: string;
    /**
     * 先前返回的页面中的可选 next_page_id
     */
    page_id?: string | null;
    /**
     * 页面中的最大结果数
     */
    limit?: number;
    /**
     * 包括隐藏的子目录（名称以“.”开头）
     */
    include_hidden?: boolean;
  };
  url: '/api/file/search_subdirs';
};

export type SearchSubdirsApiFileSearchSubdirsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SearchSubdirsApiFileSearchSubdirsGetError =
  SearchSubdirsApiFileSearchSubdirsGetErrors[keyof SearchSubdirsApiFileSearchSubdirsGetErrors];

export type SearchSubdirsApiFileSearchSubdirsGetResponses = {
  /**
   * 成功回应
   */
  200: SubdirectoryPage;
};

export type SearchSubdirsApiFileSearchSubdirsGetResponse =
  SearchSubdirsApiFileSearchSubdirsGetResponses[keyof SearchSubdirsApiFileSearchSubdirsGetResponses];

export type UploadFileQueryApiFileUploadPostData = {
  body: BodyUploadFileQueryApiFileUploadPost;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 绝对文件路径
     */
    path: string;
  };
  url: '/api/file/upload';
};

export type UploadFileQueryApiFileUploadPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UploadFileQueryApiFileUploadPostError =
  UploadFileQueryApiFileUploadPostErrors[keyof UploadFileQueryApiFileUploadPostErrors];

export type UploadFileQueryApiFileUploadPostResponses = {
  /**
   * 成功回应
   */
  200: FileUploadResult;
};

export type UploadFileQueryApiFileUploadPostResponse =
  UploadFileQueryApiFileUploadPostResponses[keyof UploadFileQueryApiFileUploadPostResponses];

export type GitChangesQueryApiGitChangesGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * git 存储库路径
     */
    path: string;
    /**
     * 参考号
     *
     * 可选的 git ref 来比较 (e.g. 'HEAD' 用于 git 状态样式更改，或提交哈希）。 省略时，将自动检测上游/默认分支。
     */
    ref?: string | null;
  };
  url: '/api/git/changes';
};

export type GitChangesQueryApiGitChangesGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitChangesQueryApiGitChangesGetError =
  GitChangesQueryApiGitChangesGetErrors[keyof GitChangesQueryApiGitChangesGetErrors];

export type GitChangesQueryApiGitChangesGetResponses = {
  /**
   * 响应 Git Changes 查询 API Git Changes Get
   *
   * 成功回应
   */
  200: Array<GitChange>;
};

export type GitChangesQueryApiGitChangesGetResponse =
  GitChangesQueryApiGitChangesGetResponses[keyof GitChangesQueryApiGitChangesGetResponses];

export type GitCommitsQueryApiGitCommitsGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * git 存储库路径
     */
    path: string;
    /**
     * 限制
     *
     * 最大承诺返回
     */
    limit?: number;
  };
  url: '/api/git/commits';
};

export type GitCommitsQueryApiGitCommitsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitCommitsQueryApiGitCommitsGetError =
  GitCommitsQueryApiGitCommitsGetErrors[keyof GitCommitsQueryApiGitCommitsGetErrors];

export type GitCommitsQueryApiGitCommitsGetResponses = {
  /**
   * 成功回应
   */
  200: GitCommitsPage;
};

export type GitCommitsQueryApiGitCommitsGetResponse =
  GitCommitsQueryApiGitCommitsGetResponses[keyof GitCommitsQueryApiGitCommitsGetResponses];

export type GitCommitChangesQueryApiGitCommitsShaChangesGetData = {
  body?: never;
  path: {
    /**
     * 沙
     *
     * 提交 SHA
     */
    sha: string;
  };
  query: {
    /**
     * 路径
     *
     * git 存储库路径
     */
    path: string;
  };
  url: '/api/git/commits/{sha}/changes';
};

export type GitCommitChangesQueryApiGitCommitsShaChangesGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitCommitChangesQueryApiGitCommitsShaChangesGetError =
  GitCommitChangesQueryApiGitCommitsShaChangesGetErrors[keyof GitCommitChangesQueryApiGitCommitsShaChangesGetErrors];

export type GitCommitChangesQueryApiGitCommitsShaChangesGetResponses = {
  /**
   * 响应 Git Commit Changes 查询 API Git Commits Sha Changes Get
   *
   * 成功回应
   */
  200: Array<GitChange>;
};

export type GitCommitChangesQueryApiGitCommitsShaChangesGetResponse =
  GitCommitChangesQueryApiGitCommitsShaChangesGetResponses[keyof GitCommitChangesQueryApiGitCommitsShaChangesGetResponses];

export type GitDiffQueryApiGitDiffGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 获取 diff 的文件路径
     */
    path: string;
    /**
     * 参考号
     *
     * 可选的 git ref 来比较 (e.g. 'HEAD' 用于 git 状态样式更改，或提交哈希）。 省略时，将自动检测上游/默认分支。
     */
    ref?: string | null;
    /**
     * 提交
     *
     * 可选提交 SHA。 设置后，差异是提交引入的更改（相对于其第一个父级），完全从 git 对象读取，因此删除的文件仍然呈现。 与“ref”互斥。
     */
    commit?: string | null;
  };
  url: '/api/git/diff';
};

export type GitDiffQueryApiGitDiffGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitDiffQueryApiGitDiffGetError =
  GitDiffQueryApiGitDiffGetErrors[keyof GitDiffQueryApiGitDiffGetErrors];

export type GitDiffQueryApiGitDiffGetResponses = {
  /**
   * 成功回应
   */
  200: GitDiff;
};

export type GitDiffQueryApiGitDiffGetResponse =
  GitDiffQueryApiGitDiffGetResponses[keyof GitDiffQueryApiGitDiffGetResponses];

export type GitRepositoriesSearchApiGitRepositoriesSearchGetData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 要搜索的 Git 提供商
     */
    provider: GitProvider;
    /**
     * 查询
     *
     * 可选的存储库名称过滤器
     */
    query?: string | null;
    /**
     * 限制
     *
     * 返回的最大存储库数
     */
    limit?: number;
    /**
     * 页面 ID
     *
     * 特定于提供商的页面光标
     */
    page_id?: string | null;
  };
  url: '/api/git/repositories/search';
};

export type GitRepositoriesSearchApiGitRepositoriesSearchGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GitRepositoriesSearchApiGitRepositoriesSearchGetError =
  GitRepositoriesSearchApiGitRepositoriesSearchGetErrors[keyof GitRepositoriesSearchApiGitRepositoriesSearchGetErrors];

export type GitRepositoriesSearchApiGitRepositoriesSearchGetResponses = {
  /**
   * 成功回应
   */
  200: GitProviderRepositoryPage;
};

export type GitRepositoriesSearchApiGitRepositoriesSearchGetResponse =
  GitRepositoriesSearchApiGitRepositoriesSearchGetResponses[keyof GitRepositoriesSearchApiGitRepositoriesSearchGetResponses];

export type GetHooksApiHooksPostData = {
  body: HooksRequest;
  path?: never;
  query?: never;
  url: '/api/hooks';
};

export type GetHooksApiHooksPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetHooksApiHooksPostError =
  GetHooksApiHooksPostErrors[keyof GetHooksApiHooksPostErrors];

export type GetHooksApiHooksPostResponses = {
  /**
   * 成功回应
   */
  200: HooksResponse;
};

export type GetHooksApiHooksPostResponse =
  GetHooksApiHooksPostResponses[keyof GetHooksApiHooksPostResponses];

export type GetInitStatusApiInitGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/init';
};

export type GetInitStatusApiInitGetResponses = {
  /**
   * 成功回应
   */
  200: InitStatus;
};

export type GetInitStatusApiInitGetResponse =
  GetInitStatusApiInitGetResponses[keyof GetInitStatusApiInitGetResponses];

export type InitializeServerApiInitPostData = {
  body: InitRequestWritable;
  path?: never;
  query?: never;
  url: '/api/init';
};

export type InitializeServerApiInitPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type InitializeServerApiInitPostError =
  InitializeServerApiInitPostErrors[keyof InitializeServerApiInitPostErrors];

export type InitializeServerApiInitPostResponses = {
  /**
   * 成功回应
   */
  200: InitStatus;
};

export type InitializeServerApiInitPostResponse =
  InitializeServerApiInitPostResponses[keyof InitializeServerApiInitPostResponses];

export type ListModelsApiLlmModelsGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 提供商
     *
     * 按提供商过滤模型（e.g.、“OpenAI”、“Anthropic”）
     */
    provider?: string | null;
  };
  url: '/api/llm/models';
};

export type ListModelsApiLlmModelsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ListModelsApiLlmModelsGetError =
  ListModelsApiLlmModelsGetErrors[keyof ListModelsApiLlmModelsGetErrors];

export type ListModelsApiLlmModelsGetResponses = {
  /**
   * 成功回应
   */
  200: ModelsResponse;
};

export type ListModelsApiLlmModelsGetResponse =
  ListModelsApiLlmModelsGetResponses[keyof ListModelsApiLlmModelsGetResponses];

export type ListVerifiedModelsApiLlmModelsVerifiedGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/models/verified';
};

export type ListVerifiedModelsApiLlmModelsVerifiedGetResponses = {
  /**
   * 成功回应
   */
  200: VerifiedModelsResponse;
};

export type ListVerifiedModelsApiLlmModelsVerifiedGetResponse =
  ListVerifiedModelsApiLlmModelsVerifiedGetResponses[keyof ListVerifiedModelsApiLlmModelsVerifiedGetResponses];

export type ListProviderConnectionsApiLlmProviderConnectionsGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/provider-connections';
};

export type ListProviderConnectionsApiLlmProviderConnectionsGetResponses = {
  /**
   * 响应列表提供商连接 API Llm 提供商连接获取
   *
   * 成功回应
   */
  200: Array<ProviderConnectionResponse>;
};

export type ListProviderConnectionsApiLlmProviderConnectionsGetResponse =
  ListProviderConnectionsApiLlmProviderConnectionsGetResponses[keyof ListProviderConnectionsApiLlmProviderConnectionsGetResponses];

export type CreateProviderConnectionApiLlmProviderConnectionsPostData = {
  body: ProviderConnectionCreateRequestWritable;
  path?: never;
  query?: never;
  url: '/api/llm/provider-connections';
};

export type CreateProviderConnectionApiLlmProviderConnectionsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CreateProviderConnectionApiLlmProviderConnectionsPostError =
  CreateProviderConnectionApiLlmProviderConnectionsPostErrors[keyof CreateProviderConnectionApiLlmProviderConnectionsPostErrors];

export type CreateProviderConnectionApiLlmProviderConnectionsPostResponses = {
  /**
   * 成功回应
   */
  201: ProviderConnectionResponse;
};

export type CreateProviderConnectionApiLlmProviderConnectionsPostResponse =
  CreateProviderConnectionApiLlmProviderConnectionsPostResponses[keyof CreateProviderConnectionApiLlmProviderConnectionsPostResponses];

export type DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteData = {
  body?: never;
  path: {
    /**
     * 连接 ID
     */
    connection_id: string;
  };
  query?: never;
  url: '/api/llm/provider-connections/{connection_id}';
};

export type DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteError =
  DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteErrors[keyof DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteErrors];

export type DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteResponses = {
  /**
   * 成功回应
   */
  200: ProviderConnectionResponse;
};

export type DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteResponse =
  DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteResponses[keyof DeleteProviderConnectionApiLlmProviderConnectionsConnectionIdDeleteResponses];

export type UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchData = {
  body: ProviderConnectionUpdateRequestWritable;
  path: {
    /**
     * 连接 ID
     */
    connection_id: string;
  };
  query?: never;
  url: '/api/llm/provider-connections/{connection_id}';
};

export type UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchError =
  UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchErrors[keyof UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchErrors];

export type UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchResponses = {
  /**
   * 成功回应
   */
  200: ProviderConnectionResponse;
};

export type UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchResponse =
  UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchResponses[keyof UpdateProviderConnectionApiLlmProviderConnectionsConnectionIdPatchResponses];

export type ListProvidersApiLlmProvidersGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/providers';
};

export type ListProvidersApiLlmProvidersGetResponses = {
  /**
   * 成功回应
   */
  200: ProvidersResponse;
};

export type ListProvidersApiLlmProvidersGetResponse =
  ListProvidersApiLlmProvidersGetResponses[keyof ListProvidersApiLlmProvidersGetResponses];

export type PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostData = {
  body: SubscriptionDevicePollRequest;
  path?: never;
  query?: never;
  url: '/api/llm/subscription/openai/device/poll';
};

export type PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostError =
  PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostErrors[keyof PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostErrors];

export type PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostResponses = {
  /**
   * 成功回应
   */
  200: SubscriptionStatusResponse;
};

export type PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostResponse =
  PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostResponses[keyof PollOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDevicePollPostResponses];

export type StartOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDeviceStartPostData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/subscription/openai/device/start';
};

export type StartOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDeviceStartPostResponses = {
  /**
   * 成功回应
   */
  200: SubscriptionDeviceStartResponse;
};

export type StartOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDeviceStartPostResponse =
  StartOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDeviceStartPostResponses[keyof StartOpenaiSubscriptionDeviceLoginApiLlmSubscriptionOpenaiDeviceStartPostResponses];

export type LogoutOpenaiSubscriptionApiLlmSubscriptionOpenaiLogoutPostData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/subscription/openai/logout';
};

export type LogoutOpenaiSubscriptionApiLlmSubscriptionOpenaiLogoutPostResponses = {
  /**
   * 成功回应
   */
  200: SubscriptionStatusResponse;
};

export type LogoutOpenaiSubscriptionApiLlmSubscriptionOpenaiLogoutPostResponse =
  LogoutOpenaiSubscriptionApiLlmSubscriptionOpenaiLogoutPostResponses[keyof LogoutOpenaiSubscriptionApiLlmSubscriptionOpenaiLogoutPostResponses];

export type ListOpenaiSubscriptionModelsApiLlmSubscriptionOpenaiModelsGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/subscription/openai/models';
};

export type ListOpenaiSubscriptionModelsApiLlmSubscriptionOpenaiModelsGetResponses = {
  /**
   * 成功回应
   */
  200: SubscriptionModelsResponse;
};

export type ListOpenaiSubscriptionModelsApiLlmSubscriptionOpenaiModelsGetResponse =
  ListOpenaiSubscriptionModelsApiLlmSubscriptionOpenaiModelsGetResponses[keyof ListOpenaiSubscriptionModelsApiLlmSubscriptionOpenaiModelsGetResponses];

export type GetOpenaiSubscriptionStatusApiLlmSubscriptionOpenaiStatusGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/llm/subscription/openai/status';
};

export type GetOpenaiSubscriptionStatusApiLlmSubscriptionOpenaiStatusGetResponses = {
  /**
   * 成功回应
   */
  200: SubscriptionStatusResponse;
};

export type GetOpenaiSubscriptionStatusApiLlmSubscriptionOpenaiStatusGetResponse =
  GetOpenaiSubscriptionStatusApiLlmSubscriptionOpenaiStatusGetResponses[keyof GetOpenaiSubscriptionStatusApiLlmSubscriptionOpenaiStatusGetResponses];

export type SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostData = {
  body: McpoAuthCallbackRequest;
  path: {
    /**
     * 职位编号
     */
    job_id: string;
  };
  query?: never;
  url: '/api/mcp/oauth/callback/{job_id}';
};

export type SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostError =
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostErrors[keyof SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostErrors];

export type SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponses = {
  /**
   * 成功回应
   */
  200: McpoAuthStatusResponse;
};

export type SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponse =
  SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponses[keyof SubmitMcpOauthCallbackApiMcpOauthCallbackJobIdPostResponses];

export type StartMcpOauthApiMcpOauthStartPostData = {
  body: McpTestRequestWritable;
  path?: never;
  query?: never;
  url: '/api/mcp/oauth/start';
};

export type StartMcpOauthApiMcpOauthStartPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type StartMcpOauthApiMcpOauthStartPostError =
  StartMcpOauthApiMcpOauthStartPostErrors[keyof StartMcpOauthApiMcpOauthStartPostErrors];

export type StartMcpOauthApiMcpOauthStartPostResponses = {
  /**
   * 成功回应
   */
  200: McpoAuthStartResponse;
};

export type StartMcpOauthApiMcpOauthStartPostResponse =
  StartMcpOauthApiMcpOauthStartPostResponses[keyof StartMcpOauthApiMcpOauthStartPostResponses];

export type GetMcpOauthStatusApiMcpOauthStatusJobIdGetData = {
  body?: never;
  path: {
    /**
     * 职位编号
     */
    job_id: string;
  };
  query?: never;
  url: '/api/mcp/oauth/status/{job_id}';
};

export type GetMcpOauthStatusApiMcpOauthStatusJobIdGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetMcpOauthStatusApiMcpOauthStatusJobIdGetError =
  GetMcpOauthStatusApiMcpOauthStatusJobIdGetErrors[keyof GetMcpOauthStatusApiMcpOauthStatusJobIdGetErrors];

export type GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponses = {
  /**
   * 成功回应
   */
  200: McpoAuthStatusResponse;
};

export type GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponse =
  GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponses[keyof GetMcpOauthStatusApiMcpOauthStatusJobIdGetResponses];

export type TestMcpServerApiMcpTestPostData = {
  body: McpTestRequestWritable;
  path?: never;
  query?: never;
  url: '/api/mcp/test';
};

export type TestMcpServerApiMcpTestPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type TestMcpServerApiMcpTestPostError =
  TestMcpServerApiMcpTestPostErrors[keyof TestMcpServerApiMcpTestPostErrors];

export type TestMcpServerApiMcpTestPostResponses = {
  /**
   * 响应测试 MCP 服务器 API MCP 测试帖子
   *
   * 成功回应
   */
  200:
    | ({
        ok: true;
      } & McpTestSuccess)
    | ({
        ok: false;
      } & McpTestFailure);
};

export type TestMcpServerApiMcpTestPostResponse =
  TestMcpServerApiMcpTestPostResponses[keyof TestMcpServerApiMcpTestPostResponses];

export type ListMetaProfilesApiMetaProfilesGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/meta-profiles';
};

export type ListMetaProfilesApiMetaProfilesGetResponses = {
  /**
   * 成功回应
   */
  200: MetaProfileListResponse;
};

export type ListMetaProfilesApiMetaProfilesGetResponse =
  ListMetaProfilesApiMetaProfilesGetResponses[keyof ListMetaProfilesApiMetaProfilesGetResponses];

export type DeleteMetaProfileApiMetaProfilesNameDeleteData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/meta-profiles/{name}';
};

export type DeleteMetaProfileApiMetaProfilesNameDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteMetaProfileApiMetaProfilesNameDeleteError =
  DeleteMetaProfileApiMetaProfilesNameDeleteErrors[keyof DeleteMetaProfileApiMetaProfilesNameDeleteErrors];

export type DeleteMetaProfileApiMetaProfilesNameDeleteResponses = {
  /**
   * 成功回应
   */
  200: MetaProfileMutationResponse;
};

export type DeleteMetaProfileApiMetaProfilesNameDeleteResponse =
  DeleteMetaProfileApiMetaProfilesNameDeleteResponses[keyof DeleteMetaProfileApiMetaProfilesNameDeleteResponses];

export type GetMetaProfileApiMetaProfilesNameGetData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/meta-profiles/{name}';
};

export type GetMetaProfileApiMetaProfilesNameGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetMetaProfileApiMetaProfilesNameGetError =
  GetMetaProfileApiMetaProfilesNameGetErrors[keyof GetMetaProfileApiMetaProfilesNameGetErrors];

export type GetMetaProfileApiMetaProfilesNameGetResponses = {
  /**
   * 成功回应
   */
  200: MetaProfileDetailResponse;
};

export type GetMetaProfileApiMetaProfilesNameGetResponse =
  GetMetaProfileApiMetaProfilesNameGetResponses[keyof GetMetaProfileApiMetaProfilesNameGetResponses];

export type SaveMetaProfileApiMetaProfilesNamePostData = {
  body: MetaProfile;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/meta-profiles/{name}';
};

export type SaveMetaProfileApiMetaProfilesNamePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SaveMetaProfileApiMetaProfilesNamePostError =
  SaveMetaProfileApiMetaProfilesNamePostErrors[keyof SaveMetaProfileApiMetaProfilesNamePostErrors];

export type SaveMetaProfileApiMetaProfilesNamePostResponses = {
  /**
   * 成功回应
   */
  201: MetaProfileMutationResponse;
};

export type SaveMetaProfileApiMetaProfilesNamePostResponse =
  SaveMetaProfileApiMetaProfilesNamePostResponses[keyof SaveMetaProfileApiMetaProfilesNamePostResponses];

export type ActivateMetaProfileApiMetaProfilesNameActivatePostData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/meta-profiles/{name}/activate';
};

export type ActivateMetaProfileApiMetaProfilesNameActivatePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ActivateMetaProfileApiMetaProfilesNameActivatePostError =
  ActivateMetaProfileApiMetaProfilesNameActivatePostErrors[keyof ActivateMetaProfileApiMetaProfilesNameActivatePostErrors];

export type ActivateMetaProfileApiMetaProfilesNameActivatePostResponses = {
  /**
   * 成功回应
   */
  200: ActivateMetaProfileResponse;
};

export type ActivateMetaProfileApiMetaProfilesNameActivatePostResponse =
  ActivateMetaProfileApiMetaProfilesNameActivatePostResponses[keyof ActivateMetaProfileApiMetaProfilesNameActivatePostResponses];

export type GetPluginsApiPluginsPostData = {
  body: PluginsRequest;
  path?: never;
  query?: never;
  url: '/api/plugins';
};

export type GetPluginsApiPluginsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetPluginsApiPluginsPostError =
  GetPluginsApiPluginsPostErrors[keyof GetPluginsApiPluginsPostErrors];

export type GetPluginsApiPluginsPostResponses = {
  /**
   * 成功回应
   */
  200: PluginsResponse;
};

export type GetPluginsApiPluginsPostResponse =
  GetPluginsApiPluginsPostResponses[keyof GetPluginsApiPluginsPostResponses];

export type FetchPluginEndpointApiPluginsFetchPostData = {
  body: FetchPluginRequestWritable;
  path?: never;
  query?: never;
  url: '/api/plugins/fetch';
};

export type FetchPluginEndpointApiPluginsFetchPostErrors = {
  /**
   * 插件源、引用、路径或插件无效
   */
  422: unknown;
  /**
   * 插件源不可用
   */
  502: unknown;
  /**
   * 插件获取超时
   */
  504: unknown;
};

export type FetchPluginEndpointApiPluginsFetchPostResponses = {
  /**
   * 成功回应
   */
  200: FetchPluginResponse;
};

export type FetchPluginEndpointApiPluginsFetchPostResponse =
  FetchPluginEndpointApiPluginsFetchPostResponses[keyof FetchPluginEndpointApiPluginsFetchPostResponses];

export type InstallPluginEndpointApiPluginsInstallPostData = {
  body: InstallPluginRequest;
  path?: never;
  query?: never;
  url: '/api/plugins/install';
};

export type InstallPluginEndpointApiPluginsInstallPostErrors = {
  /**
   * 获取插件源失败
   */
  400: unknown;
  /**
   * 插件已安装（使用force=True）
   */
  409: unknown;
  /**
   * 无效的插件（名称错误等）
   */
  422: unknown;
};

export type InstallPluginEndpointApiPluginsInstallPostResponses = {
  /**
   * 成功回应
   */
  200: InstalledPluginResponse;
};

export type InstallPluginEndpointApiPluginsInstallPostResponse =
  InstallPluginEndpointApiPluginsInstallPostResponses[keyof InstallPluginEndpointApiPluginsInstallPostResponses];

export type ListInstalledPluginsEndpointApiPluginsInstalledGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/plugins/installed';
};

export type ListInstalledPluginsEndpointApiPluginsInstalledGetResponses = {
  /**
   * 成功回应
   */
  200: InstalledPluginsListResponse;
};

export type ListInstalledPluginsEndpointApiPluginsInstalledGetResponse =
  ListInstalledPluginsEndpointApiPluginsInstalledGetResponses[keyof ListInstalledPluginsEndpointApiPluginsInstalledGetResponses];

export type UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteData = {
  body?: never;
  path: {
    /**
     * 插件名称
     *
     * 插件名称（小写字母数字，连字符）
     */
    plugin_name: string;
  };
  query?: never;
  url: '/api/plugins/installed/{plugin_name}';
};

export type UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteErrors = {
  /**
   * 插件未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteError =
  UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteErrors[keyof UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteErrors];

export type UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteResponses = {
  /**
   * 成功回应
   */
  200: UninstallPluginResponse;
};

export type UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteResponse =
  UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteResponses[keyof UninstallPluginEndpointApiPluginsInstalledPluginNameDeleteResponses];

export type GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetData = {
  body?: never;
  path: {
    /**
     * 插件名称
     *
     * 插件名称（小写字母数字，连字符）
     */
    plugin_name: string;
  };
  query?: never;
  url: '/api/plugins/installed/{plugin_name}';
};

export type GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetErrors = {
  /**
   * 插件未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetError =
  GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetErrors[keyof GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetErrors];

export type GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetResponses = {
  /**
   * 成功回应
   */
  200: InstalledPluginResponse;
};

export type GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetResponse =
  GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetResponses[keyof GetInstalledPluginEndpointApiPluginsInstalledPluginNameGetResponses];

export type SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchData = {
  body: UpdatePluginStateRequest;
  path: {
    /**
     * 插件名称
     *
     * 插件名称（小写字母数字，连字符）
     */
    plugin_name: string;
  };
  query?: never;
  url: '/api/plugins/installed/{plugin_name}';
};

export type SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchErrors = {
  /**
   * 插件未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchError =
  SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchErrors[keyof SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchErrors];

export type SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchResponses = {
  /**
   * 成功回应
   */
  200: UpdatePluginStateResponse;
};

export type SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchResponse =
  SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchResponses[keyof SetPluginEnabledEndpointApiPluginsInstalledPluginNamePatchResponses];

export type RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostData = {
  body?: never;
  path: {
    /**
     * 插件名称
     *
     * 插件名称（小写字母数字，连字符）
     */
    plugin_name: string;
  };
  query?: never;
  url: '/api/plugins/installed/{plugin_name}/refresh';
};

export type RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostErrors = {
  /**
   * 无法获取插件的记录源
   */
  400: unknown;
  /**
   * 插件未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostError =
  RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostErrors[keyof RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostErrors];

export type RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostResponses = {
  /**
   * 成功回应
   */
  200: UpdatePluginResponse;
};

export type RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostResponse =
  RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostResponses[keyof RefreshPluginEndpointApiPluginsInstalledPluginNameRefreshPostResponses];

export type GetMarketplaceCatalogApiPluginsMarketplaceGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/plugins/marketplace';
};

export type GetMarketplaceCatalogApiPluginsMarketplaceGetResponses = {
  /**
   * 成功回应
   */
  200: OpenhandsAgentServerPluginsRouterMarketplaceCatalogResponse;
};

export type GetMarketplaceCatalogApiPluginsMarketplaceGetResponse =
  GetMarketplaceCatalogApiPluginsMarketplaceGetResponses[keyof GetMarketplaceCatalogApiPluginsMarketplaceGetResponses];

export type ListProfilesApiProfilesGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/profiles';
};

export type ListProfilesApiProfilesGetResponses = {
  /**
   * 成功回应
   */
  200: ProfileListResponse;
};

export type ListProfilesApiProfilesGetResponse =
  ListProfilesApiProfilesGetResponses[keyof ListProfilesApiProfilesGetResponses];

export type DeleteProfileApiProfilesNameDeleteData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}';
};

export type DeleteProfileApiProfilesNameDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteProfileApiProfilesNameDeleteError =
  DeleteProfileApiProfilesNameDeleteErrors[keyof DeleteProfileApiProfilesNameDeleteErrors];

export type DeleteProfileApiProfilesNameDeleteResponses = {
  /**
   * 成功回应
   */
  200: ProfileMutationResponse;
};

export type DeleteProfileApiProfilesNameDeleteResponse =
  DeleteProfileApiProfilesNameDeleteResponses[keyof DeleteProfileApiProfilesNameDeleteResponses];

export type GetProfileApiProfilesNameGetData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}';
};

export type GetProfileApiProfilesNameGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetProfileApiProfilesNameGetError =
  GetProfileApiProfilesNameGetErrors[keyof GetProfileApiProfilesNameGetErrors];

export type GetProfileApiProfilesNameGetResponses = {
  /**
   * 成功回应
   */
  200: ProfileDetailResponse;
};

export type GetProfileApiProfilesNameGetResponse =
  GetProfileApiProfilesNameGetResponses[keyof GetProfileApiProfilesNameGetResponses];

export type SaveProfileApiProfilesNamePostData = {
  body: SaveProfileRequestWritable;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}';
};

export type SaveProfileApiProfilesNamePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SaveProfileApiProfilesNamePostError =
  SaveProfileApiProfilesNamePostErrors[keyof SaveProfileApiProfilesNamePostErrors];

export type SaveProfileApiProfilesNamePostResponses = {
  /**
   * 成功回应
   */
  201: ProfileMutationResponse;
};

export type SaveProfileApiProfilesNamePostResponse =
  SaveProfileApiProfilesNamePostResponses[keyof SaveProfileApiProfilesNamePostResponses];

export type ActivateProfileApiProfilesNameActivatePostData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}/activate';
};

export type ActivateProfileApiProfilesNameActivatePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ActivateProfileApiProfilesNameActivatePostError =
  ActivateProfileApiProfilesNameActivatePostErrors[keyof ActivateProfileApiProfilesNameActivatePostErrors];

export type ActivateProfileApiProfilesNameActivatePostResponses = {
  /**
   * 成功回应
   */
  200: ActivateProfileResponse;
};

export type ActivateProfileApiProfilesNameActivatePostResponse =
  ActivateProfileApiProfilesNameActivatePostResponses[keyof ActivateProfileApiProfilesNameActivatePostResponses];

export type RenameProfileApiProfilesNameRenamePostData = {
  body: RenameProfileRequest;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}/rename';
};

export type RenameProfileApiProfilesNameRenamePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type RenameProfileApiProfilesNameRenamePostError =
  RenameProfileApiProfilesNameRenamePostErrors[keyof RenameProfileApiProfilesNameRenamePostErrors];

export type RenameProfileApiProfilesNameRenamePostResponses = {
  /**
   * 成功回应
   */
  200: ProfileMutationResponse;
};

export type RenameProfileApiProfilesNameRenamePostResponse =
  RenameProfileApiProfilesNameRenamePostResponses[keyof RenameProfileApiProfilesNameRenamePostResponses];

export type ValidateProfileApiProfilesNameValidatePostData = {
  body: ValidateProfileRequestWritable;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/profiles/{name}/validate';
};

export type ValidateProfileApiProfilesNameValidatePostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ValidateProfileApiProfilesNameValidatePostError =
  ValidateProfileApiProfilesNameValidatePostErrors[keyof ValidateProfileApiProfilesNameValidatePostErrors];

export type ValidateProfileApiProfilesNameValidatePostResponses = {
  /**
   * 成功回应
   */
  200: ValidateProfileResponse;
};

export type ValidateProfileApiProfilesNameValidatePostResponse =
  ValidateProfileApiProfilesNameValidatePostResponses[keyof ValidateProfileApiProfilesNameValidatePostResponses];

export type GetSettingsApiSettingsGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/settings';
};

export type GetSettingsApiSettingsGetResponses = {
  /**
   * 成功回应
   */
  200: SettingsResponse;
};

export type GetSettingsApiSettingsGetResponse =
  GetSettingsApiSettingsGetResponses[keyof GetSettingsApiSettingsGetResponses];

export type UpdateSettingsApiSettingsPatchData = {
  body: SettingsUpdateRequestWritable;
  path?: never;
  query?: never;
  url: '/api/settings';
};

export type UpdateSettingsApiSettingsPatchErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UpdateSettingsApiSettingsPatchError =
  UpdateSettingsApiSettingsPatchErrors[keyof UpdateSettingsApiSettingsPatchErrors];

export type UpdateSettingsApiSettingsPatchResponses = {
  /**
   * 成功回应
   */
  200: SettingsResponse;
};

export type UpdateSettingsApiSettingsPatchResponse =
  UpdateSettingsApiSettingsPatchResponses[keyof UpdateSettingsApiSettingsPatchResponses];

export type GetAgentSettingsSchemaApiSettingsAgentSchemaGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/settings/agent-schema';
};

export type GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponses = {
  /**
   * 成功回应
   */
  200: SettingsSchema;
};

export type GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponse =
  GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponses[keyof GetAgentSettingsSchemaApiSettingsAgentSchemaGetResponses];

export type GetConversationSettingsSchemaApiSettingsConversationSchemaGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/settings/conversation-schema';
};

export type GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponses = {
  /**
   * 成功回应
   */
  200: SettingsSchema;
};

export type GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponse =
  GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponses[keyof GetConversationSettingsSchemaApiSettingsConversationSchemaGetResponses];

export type DeleteMcpServerApiSettingsMcpSettingsKeyDeleteData = {
  body?: never;
  path: {
    /**
     * 设置键
     */
    settings_key: string;
  };
  query?: never;
  url: '/api/settings/mcp/{settings_key}';
};

export type DeleteMcpServerApiSettingsMcpSettingsKeyDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteMcpServerApiSettingsMcpSettingsKeyDeleteError =
  DeleteMcpServerApiSettingsMcpSettingsKeyDeleteErrors[keyof DeleteMcpServerApiSettingsMcpSettingsKeyDeleteErrors];

export type DeleteMcpServerApiSettingsMcpSettingsKeyDeleteResponses = {
  /**
   * 成功回应
   */
  200: SettingsResponse;
};

export type DeleteMcpServerApiSettingsMcpSettingsKeyDeleteResponse =
  DeleteMcpServerApiSettingsMcpSettingsKeyDeleteResponses[keyof DeleteMcpServerApiSettingsMcpSettingsKeyDeleteResponses];

export type PatchMcpServerApiSettingsMcpSettingsKeyPatchData = {
  body: McpServerPatchWritable;
  path: {
    /**
     * 设置键
     */
    settings_key: string;
  };
  query?: never;
  url: '/api/settings/mcp/{settings_key}';
};

export type PatchMcpServerApiSettingsMcpSettingsKeyPatchErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type PatchMcpServerApiSettingsMcpSettingsKeyPatchError =
  PatchMcpServerApiSettingsMcpSettingsKeyPatchErrors[keyof PatchMcpServerApiSettingsMcpSettingsKeyPatchErrors];

export type PatchMcpServerApiSettingsMcpSettingsKeyPatchResponses = {
  /**
   * 成功回应
   */
  200: SettingsResponse;
};

export type PatchMcpServerApiSettingsMcpSettingsKeyPatchResponse =
  PatchMcpServerApiSettingsMcpSettingsKeyPatchResponses[keyof PatchMcpServerApiSettingsMcpSettingsKeyPatchResponses];

export type CreateMcpServerApiSettingsMcpSettingsKeyPostData = {
  body: McpServerInputWritable;
  path: {
    /**
     * 设置键
     */
    settings_key: string;
  };
  query?: never;
  url: '/api/settings/mcp/{settings_key}';
};

export type CreateMcpServerApiSettingsMcpSettingsKeyPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CreateMcpServerApiSettingsMcpSettingsKeyPostError =
  CreateMcpServerApiSettingsMcpSettingsKeyPostErrors[keyof CreateMcpServerApiSettingsMcpSettingsKeyPostErrors];

export type CreateMcpServerApiSettingsMcpSettingsKeyPostResponses = {
  /**
   * 成功回应
   */
  201: SettingsResponse;
};

export type CreateMcpServerApiSettingsMcpSettingsKeyPostResponse =
  CreateMcpServerApiSettingsMcpSettingsKeyPostResponses[keyof CreateMcpServerApiSettingsMcpSettingsKeyPostResponses];

export type ListSecretsApiSettingsSecretsGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 智能体个人资料 ID
     */
    agent_profile_id?: string | null;
  };
  url: '/api/settings/secrets';
};

export type ListSecretsApiSettingsSecretsGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type ListSecretsApiSettingsSecretsGetError =
  ListSecretsApiSettingsSecretsGetErrors[keyof ListSecretsApiSettingsSecretsGetErrors];

export type ListSecretsApiSettingsSecretsGetResponses = {
  /**
   * 成功回应
   */
  200: SecretsListResponse;
};

export type ListSecretsApiSettingsSecretsGetResponse =
  ListSecretsApiSettingsSecretsGetResponses[keyof ListSecretsApiSettingsSecretsGetResponses];

export type CreateSecretApiSettingsSecretsPutData = {
  body: SecretCreateRequestWritable;
  path?: never;
  query?: never;
  url: '/api/settings/secrets';
};

export type CreateSecretApiSettingsSecretsPutErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type CreateSecretApiSettingsSecretsPutError =
  CreateSecretApiSettingsSecretsPutErrors[keyof CreateSecretApiSettingsSecretsPutErrors];

export type CreateSecretApiSettingsSecretsPutResponses = {
  /**
   * 成功回应
   */
  200: SecretItemResponse;
};

export type CreateSecretApiSettingsSecretsPutResponse =
  CreateSecretApiSettingsSecretsPutResponses[keyof CreateSecretApiSettingsSecretsPutResponses];

export type DeleteSecretApiSettingsSecretsNameDeleteData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/settings/secrets/{name}';
};

export type DeleteSecretApiSettingsSecretsNameDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteSecretApiSettingsSecretsNameDeleteError =
  DeleteSecretApiSettingsSecretsNameDeleteErrors[keyof DeleteSecretApiSettingsSecretsNameDeleteErrors];

export type DeleteSecretApiSettingsSecretsNameDeleteResponses = {
  /**
   * 响应删除机密 API 设置机密名称删除
   *
   * 成功回应
   */
  200: {
    [key: string]: boolean;
  };
};

export type DeleteSecretApiSettingsSecretsNameDeleteResponse =
  DeleteSecretApiSettingsSecretsNameDeleteResponses[keyof DeleteSecretApiSettingsSecretsNameDeleteResponses];

export type GetSecretValueApiSettingsSecretsNameGetData = {
  body?: never;
  path: {
    /**
     * 名称
     */
    name: string;
  };
  query?: never;
  url: '/api/settings/secrets/{name}';
};

export type GetSecretValueApiSettingsSecretsNameGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetSecretValueApiSettingsSecretsNameGetError =
  GetSecretValueApiSettingsSecretsNameGetErrors[keyof GetSecretValueApiSettingsSecretsNameGetErrors];

export type GetSecretValueApiSettingsSecretsNameGetResponses = {
  /**
   * 成功回应
   */
  200: unknown;
};

export type GetSkillsApiSkillsPostData = {
  body: SkillsRequest;
  path?: never;
  query?: never;
  url: '/api/skills';
};

export type GetSkillsApiSkillsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetSkillsApiSkillsPostError =
  GetSkillsApiSkillsPostErrors[keyof GetSkillsApiSkillsPostErrors];

export type GetSkillsApiSkillsPostResponses = {
  /**
   * 成功回应
   */
  200: SkillsResponse;
};

export type GetSkillsApiSkillsPostResponse =
  GetSkillsApiSkillsPostResponses[keyof GetSkillsApiSkillsPostResponses];

export type GetSkillCatalogApiSkillsCatalogGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/skills/catalog';
};

export type GetSkillCatalogApiSkillsCatalogGetResponses = {
  /**
   * 成功回应
   */
  200: SkillCatalogResponse;
};

export type GetSkillCatalogApiSkillsCatalogGetResponse =
  GetSkillCatalogApiSkillsCatalogGetResponses[keyof GetSkillCatalogApiSkillsCatalogGetResponses];

export type InstallSkillEndpointApiSkillsInstallPostData = {
  body: InstallSkillRequest;
  path?: never;
  query?: never;
  url: '/api/skills/install';
};

export type InstallSkillEndpointApiSkillsInstallPostErrors = {
  /**
   * 获取技能源失败
   */
  400: unknown;
  /**
   * 技能已安装（使用 force=True）
   */
  409: unknown;
  /**
   * 技能无效（缺少SKILL.md等）
   */
  422: unknown;
};

export type InstallSkillEndpointApiSkillsInstallPostResponses = {
  /**
   * 成功回应
   */
  200: InstalledSkillResponse;
};

export type InstallSkillEndpointApiSkillsInstallPostResponse =
  InstallSkillEndpointApiSkillsInstallPostResponses[keyof InstallSkillEndpointApiSkillsInstallPostResponses];

export type ListInstalledSkillsEndpointApiSkillsInstalledGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/skills/installed';
};

export type ListInstalledSkillsEndpointApiSkillsInstalledGetResponses = {
  /**
   * 成功回应
   */
  200: InstalledSkillsListResponse;
};

export type ListInstalledSkillsEndpointApiSkillsInstalledGetResponse =
  ListInstalledSkillsEndpointApiSkillsInstalledGetResponses[keyof ListInstalledSkillsEndpointApiSkillsInstalledGetResponses];

export type UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteData = {
  body?: never;
  path: {
    /**
     * 技能名称
     *
     * 技能名称（小写字母数字，连字符）
     */
    skill_name: string;
  };
  query?: never;
  url: '/api/skills/installed/{skill_name}';
};

export type UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteErrors = {
  /**
   * 技能未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteError =
  UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteErrors[keyof UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteErrors];

export type UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteResponses = {
  /**
   * 成功回应
   */
  200: UninstallSkillResponse;
};

export type UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteResponse =
  UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteResponses[keyof UninstallSkillEndpointApiSkillsInstalledSkillNameDeleteResponses];

export type GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetData = {
  body?: never;
  path: {
    /**
     * 技能名称
     *
     * 技能名称（小写字母数字，连字符）
     */
    skill_name: string;
  };
  query?: never;
  url: '/api/skills/installed/{skill_name}';
};

export type GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetErrors = {
  /**
   * 技能未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetError =
  GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetErrors[keyof GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetErrors];

export type GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetResponses = {
  /**
   * 成功回应
   */
  200: InstalledSkillResponse;
};

export type GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetResponse =
  GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetResponses[keyof GetInstalledSkillEndpointApiSkillsInstalledSkillNameGetResponses];

export type SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchData = {
  body: UpdateSkillStateRequest;
  path: {
    /**
     * 技能名称
     *
     * 技能名称（小写字母数字，连字符）
     */
    skill_name: string;
  };
  query?: never;
  url: '/api/skills/installed/{skill_name}';
};

export type SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchErrors = {
  /**
   * 技能未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchError =
  SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchErrors[keyof SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchErrors];

export type SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchResponses = {
  /**
   * 成功回应
   */
  200: UpdateSkillStateResponse;
};

export type SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchResponse =
  SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchResponses[keyof SetSkillEnabledEndpointApiSkillsInstalledSkillNamePatchResponses];

export type RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostData = {
  body?: never;
  path: {
    /**
     * 技能名称
     *
     * 技能名称（小写字母数字，连字符）
     */
    skill_name: string;
  };
  query?: never;
  url: '/api/skills/installed/{skill_name}/refresh';
};

export type RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostErrors = {
  /**
   * 获取技能记录来源失败
   */
  400: unknown;
  /**
   * 技能未安装
   */
  404: unknown;
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostError =
  RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostErrors[keyof RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostErrors];

export type RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostResponses = {
  /**
   * 成功回应
   */
  200: UpdateSkillResponse;
};

export type RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostResponse =
  RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostResponses[keyof RefreshSkillEndpointApiSkillsInstalledSkillNameRefreshPostResponses];

export type GetMarketplaceCatalogApiSkillsMarketplaceGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/skills/marketplace';
};

export type GetMarketplaceCatalogApiSkillsMarketplaceGetResponses = {
  /**
   * 成功回应
   */
  200: OpenhandsAgentServerSkillsRouterMarketplaceCatalogResponse;
};

export type GetMarketplaceCatalogApiSkillsMarketplaceGetResponse =
  GetMarketplaceCatalogApiSkillsMarketplaceGetResponses[keyof GetMarketplaceCatalogApiSkillsMarketplaceGetResponses];

export type SyncSkillsApiSkillsSyncPostData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/skills/sync';
};

export type SyncSkillsApiSkillsSyncPostResponses = {
  /**
   * 成功回应
   */
  200: SyncResponse;
};

export type SyncSkillsApiSkillsSyncPostResponse =
  SyncSkillsApiSkillsSyncPostResponses[keyof SyncSkillsApiSkillsSyncPostResponses];

export type GetSubAgentsApiSubAgentsPostData = {
  body: SubAgentsRequest;
  path?: never;
  query?: never;
  url: '/api/sub-agents';
};

export type GetSubAgentsApiSubAgentsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetSubAgentsApiSubAgentsPostError =
  GetSubAgentsApiSubAgentsPostErrors[keyof GetSubAgentsApiSubAgentsPostErrors];

export type GetSubAgentsApiSubAgentsPostResponses = {
  /**
   * 成功回应
   */
  200: SubAgentsResponse;
};

export type GetSubAgentsApiSubAgentsPostResponse =
  GetSubAgentsApiSubAgentsPostResponses[keyof GetSubAgentsApiSubAgentsPostResponses];

export type ListAvailableToolsApiToolsGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/tools/';
};

export type ListAvailableToolsApiToolsGetResponses = {
  /**
   * 响应列表可用工具 API 工具获取
   *
   * 成功回应
   */
  200: Array<string>;
};

export type ListAvailableToolsApiToolsGetResponse =
  ListAvailableToolsApiToolsGetResponses[keyof ListAvailableToolsApiToolsGetResponses];

export type GetToolCatalogApiToolsCatalogGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/tools/catalog';
};

export type GetToolCatalogApiToolsCatalogGetResponses = {
  /**
   * 成功回应
   */
  200: ToolCatalogResponse;
};

export type GetToolCatalogApiToolsCatalogGetResponse =
  GetToolCatalogApiToolsCatalogGetResponses[keyof GetToolCatalogApiToolsCatalogGetResponses];

export type GetVscodeStatusApiVscodeStatusGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/vscode/status';
};

export type GetVscodeStatusApiVscodeStatusGetResponses = {
  /**
   * 响应获取 Vscode 状态 API Vscode 状态获取
   *
   * 成功回应
   */
  200: {
    [key: string]: boolean | string;
  };
};

export type GetVscodeStatusApiVscodeStatusGetResponse =
  GetVscodeStatusApiVscodeStatusGetResponses[keyof GetVscodeStatusApiVscodeStatusGetResponses];

export type GetVscodeUrlApiVscodeUrlGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * 基本网址
     */
    base_url?: string | null;
    /**
     * 工作区目录
     */
    workspace_dir?: string;
  };
  url: '/api/vscode/url';
};

export type GetVscodeUrlApiVscodeUrlGetErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type GetVscodeUrlApiVscodeUrlGetError =
  GetVscodeUrlApiVscodeUrlGetErrors[keyof GetVscodeUrlApiVscodeUrlGetErrors];

export type GetVscodeUrlApiVscodeUrlGetResponses = {
  /**
   * 成功回应
   */
  200: VsCodeUrlResponse;
};

export type GetVscodeUrlApiVscodeUrlGetResponse =
  GetVscodeUrlApiVscodeUrlGetResponses[keyof GetVscodeUrlApiVscodeUrlGetResponses];

export type DeleteWorkspaceApiWorkspacesDeleteData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 要删除的绝对工作区路径
     */
    path: string;
  };
  url: '/api/workspaces';
};

export type DeleteWorkspaceApiWorkspacesDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteWorkspaceApiWorkspacesDeleteError =
  DeleteWorkspaceApiWorkspacesDeleteErrors[keyof DeleteWorkspaceApiWorkspacesDeleteErrors];

export type DeleteWorkspaceApiWorkspacesDeleteResponses = {
  /**
   * 成功回应
   */
  200: DeleteResponse;
};

export type DeleteWorkspaceApiWorkspacesDeleteResponse =
  DeleteWorkspaceApiWorkspacesDeleteResponses[keyof DeleteWorkspaceApiWorkspacesDeleteResponses];

export type ListWorkspacesApiWorkspacesGetData = {
  body?: never;
  path?: never;
  query?: never;
  url: '/api/workspaces';
};

export type ListWorkspacesApiWorkspacesGetResponses = {
  /**
   * 成功回应
   */
  200: WorkspacesListResponse;
};

export type ListWorkspacesApiWorkspacesGetResponse =
  ListWorkspacesApiWorkspacesGetResponses[keyof ListWorkspacesApiWorkspacesGetResponses];

export type AddWorkspacesApiWorkspacesPostData = {
  body: AddWorkspacesRequest;
  path?: never;
  query?: never;
  url: '/api/workspaces';
};

export type AddWorkspacesApiWorkspacesPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type AddWorkspacesApiWorkspacesPostError =
  AddWorkspacesApiWorkspacesPostErrors[keyof AddWorkspacesApiWorkspacesPostErrors];

export type AddWorkspacesApiWorkspacesPostResponses = {
  /**
   * 成功回应
   */
  200: WorkspacesListResponse;
};

export type AddWorkspacesApiWorkspacesPostResponse =
  AddWorkspacesApiWorkspacesPostResponses[keyof AddWorkspacesApiWorkspacesPostResponses];

export type DeleteWorkspaceParentApiWorkspacesParentsDeleteData = {
  body?: never;
  path?: never;
  query: {
    /**
     * 路径
     *
     * 要删除的绝对工作区父路径
     */
    path: string;
  };
  url: '/api/workspaces/parents';
};

export type DeleteWorkspaceParentApiWorkspacesParentsDeleteErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type DeleteWorkspaceParentApiWorkspacesParentsDeleteError =
  DeleteWorkspaceParentApiWorkspacesParentsDeleteErrors[keyof DeleteWorkspaceParentApiWorkspacesParentsDeleteErrors];

export type DeleteWorkspaceParentApiWorkspacesParentsDeleteResponses = {
  /**
   * 成功回应
   */
  200: DeleteResponse;
};

export type DeleteWorkspaceParentApiWorkspacesParentsDeleteResponse =
  DeleteWorkspaceParentApiWorkspacesParentsDeleteResponses[keyof DeleteWorkspaceParentApiWorkspacesParentsDeleteResponses];

export type AddWorkspaceParentsApiWorkspacesParentsPostData = {
  body: AddWorkspaceParentsRequest;
  path?: never;
  query?: never;
  url: '/api/workspaces/parents';
};

export type AddWorkspaceParentsApiWorkspacesParentsPostErrors = {
  /**
   * 验证错误
   */
  422: HttpValidationError;
};

export type AddWorkspaceParentsApiWorkspacesParentsPostError =
  AddWorkspaceParentsApiWorkspacesParentsPostErrors[keyof AddWorkspaceParentsApiWorkspacesParentsPostErrors];

export type AddWorkspaceParentsApiWorkspacesParentsPostResponses = {
  /**
   * 成功回应
   */
  200: WorkspacesListResponse;
};

export type AddWorkspaceParentsApiWorkspacesParentsPostResponse =
  AddWorkspaceParentsApiWorkspacesParentsPostResponses[keyof AddWorkspaceParentsApiWorkspacesParentsPostResponses];
