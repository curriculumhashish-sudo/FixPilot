/**
 * ACP（智能体客户端协议）提供者注册表 - TypeScript镜像
 * Python 事实来源：
 * `openhands.sdk.settings.acp_providers.ACP_PROVIDERS` 在
 * https://github.com/OpenHands/software-agent-sdk.
 *
 * 数据位于 `./acp-providers.json` 中，因此 Python 漂移检查
 * `scripts/check-acp-drift.py`可以读取它而不执行TypeScript。
 * 要添加或修改提供商，请在软件-智能体-SDK中编辑`acp_providers.py`
 * 首先，然后在此处镜像 `acp-providers.json` 中的更改。 CI 将会失败
 * 直到两人匹配。
 *
 * 此注册表描述了哪些线束存在，而不是哪些线束是产品
 * 优惠。 呈现子集的客户端声明 `SURFACED_ACP_PROVIDERS`
 * 独立并自行执行该政策。 他们只断言
 * 表面的键保留在此注册表中：重命名或删除失败，而
 * 注册表加法是无操作。 补充性的未公开列表将使
 * 每个上游添加都需要客户端编辑，并且不得使用。
 */

import providersData from './acp-providers.json';

/**
 * 用于内置 ACP 提供程序的稳定注册表密钥。
 *
 * 源自镜像数据，因此将提供程序添加到 `acp-providers.json`
 * （由`check-acp-drift.py --write`从Python注册表重新生成）
 * 也扩大了这个联盟。 用手拼写出来两者可能会漂移：漂移
 * 检查仅比较 JSON，因此运行时映射中存在提供程序，但是
 * 联合中缺失对消费者来说是一个编译错误，而 CI 这里
 * 保持绿色。
 *
 * **不**包括`'custom'` - `custom`是UI端鉴别器
 * 意思是“用户输入了自己的命令”并且故意没有注册表
 * 条目。
 */
export type ACPProviderKey = keyof typeof providersData;

/**
 * 内置 ACP 提供商模型选择器的一种可选模型。 镜子
 * `openhands.sdk.settings.acp_providers.ACPModelOption` 逐个字段。
 *
 * @已弃用用 `ACPClient.discoverModels` 代替询问 Agent Server。
 */
export interface ACPModelOption {
  /** 确切的型号标识符作为 `acp_model` 发送到 ACP 服务器。*/
  readonly id: string;
  /** 模型选择器中显示的人类可读标签 (e.g. `"Claude Opus 4.7"`).*/
  readonly label: string;
}

/**
 * 提供者可以使用的一个文件内容凭据的声明性规范
 * (e.g. 法典`auth.json`）。 镜子
 * `openhands.sdk.settings.acp_providers.ACPFileSecretSpec` 逐个字段。
 */
export interface ACPFileSecretSpec {
  /** 保留的机密名称，其值为文件的内容。*/
  readonly secret_name: string;
  /** 机密的文件名具体化为。*/
  readonly filename: string;
  /** Env var 指向具体化文件（或其目录）。*/
  readonly env_var: string;
  /** 文件所在的每个提供者的子目录。*/
  readonly subdir: string;
  /** `env_var` 是否指向文件本身或其目录。*/
  readonly env_points_to: 'file' | 'dir';
  /** 服务器在丢失时发出警告的伴随环境变量。*/
  readonly warn_if_unset: readonly string[];
}

/**
 * 一个提供商的环境变量规则不得与凭据共存
 * 进行身份验证。 镜子
 * `openhands.sdk.settings.acp_providers.ACPEnvConflictSpec` 逐个字段。
 */
export interface ACPEnvConflictSpec {
  /** 环境变量，其存在意味着提供者使用它进行身份验证。*/
  readonly dominant: string;
  /** 当 `dominant` 存在时，环境变量从子进程环境中删除。*/
  readonly strip: readonly string[];
}

/**
 * 一个内置 ACP 提供程序的不可变元数据记录。 镜子
 * `openhands.sdk.settings.acp_providers.ACPProviderInfo` 逐个字段。
 */
export interface ACPProviderInfo {
  readonly key: ACPProviderKey;
  readonly display_name: string;
  readonly default_command: readonly string[];
  /** `null` 适用于通过浏览器登录进行身份验证的提供商。*/
  readonly api_key_env_var: string | null;
  /** `null` 如果提供程序不支持基于环境的 base-URL 覆盖。*/
  readonly base_url_env_var: string | null;
  /**
   * ACP 会话模式 ID，禁止所有权限提示词或 `null`
   * 不公开此类模式的服务器（pi-ACP 将模式映射到思维级别）。
   */
  readonly default_session_mode: string | null;
  /** 小写子字符串片段与运行时智能体名称匹配。*/
  readonly agent_name_patterns: readonly string[];
  /**
   * `true` 如果该提供商通过以下方式选择其 * 初始 * 模型
   * `set_session_model` 协议调用（而不是会话 `_meta`）。
   */
  readonly supports_set_session_model: boolean;
  /**
   * `true` 如果此提供程序支持 * 运行时 * 的 `set_session_model`，
   * 会话中切换（功能`switchAcpModel`依赖）。
   */
  readonly supports_runtime_model_switch: boolean;
  /** 顶级 `_meta` 键用于模型选择，或 `null`。*/
  readonly session_meta_key: string | null;
  /**
   * 精选的 `acp_model` 个候选者出现在该提供商的模型选择器中。
   * 建议，而不是权威的访问检查 - 自定义 `acp_model` 是
   * 始终允许，并且可用性取决于帐户的计划级别。
   *
   * @已弃用用 `ACPClient.discoverModels` 代替询问 Agent Server。
   */
  readonly available_models: readonly ACPModelOption[];
  /**
   * 配置 None 时预选的型号 ID（{@link available_models} 之一），
   * 或 `null` 让 ACP 服务器选择自己的默认值。
   *
   * @已弃用用 `ACPClient.discoverModels` 代替询问 Agent Server。
   */
  readonly default_model: string | null;
  /** 凭据文件内容Agent Server可以写入磁盘。*/
  readonly file_secrets: readonly ACPFileSecretSpec[];
  /**
   * 提供程序固定的裸可执行文件名称 CLI 或 `null`。 智能体
   * 当它位于 PATH 时，服务器更喜欢此二进制文件而不是 `npx` 回退方案。
   */
  readonly binary_name: string | null;
  /** 重新定位提供程序的 data/config 目录的环境变量，或 `null`。*/
  readonly data_dir_env_var: string | null;
  /** 该提供者自己的环境变量凭据不得与其共存。*/
  readonly env_conflicts: readonly ACPEnvConflictSpec[];
}

export const ACP_PROVIDERS: Readonly<Record<ACPProviderKey, ACPProviderInfo>> =
  providersData as Readonly<Record<ACPProviderKey, ACPProviderInfo>>;

/**
 * 返回 {@link ACPProviderInfo} for `key`, 或 `null` 如果未知。
 * 镜像 Python `get_acp_provider` 语义 — 返回 `null`
 * UI 端 `'custom'` 鉴别器和任何未知/虚假值。
 */
export function getAcpProvider(key: string | null | undefined): ACPProviderInfo | null {
  if (!key) {
    return null;
  }
  return (ACP_PROVIDERS as Record<string, ACPProviderInfo | undefined>)[key] ?? null;
}

/**
 * 在 `ACPAgent` 设置载荷上传输的字段的允许列表。
 * 镜像 `openhands.sdk.settings.model.ACPAgentSettings` 的场集。
 * 当切换到非 ACP 变体时，客户端会过滤掉仅包含 ACP 的字段。
 */
export const ACP_SETTINGS_KEYS: readonly string[] = [
  'acp_command',
  'acp_args',
  'acp_env',
  'acp_model',
  'acp_session_mode',
  'acp_prompt_timeout',
  'acp_server',
  'acp_isolate_data_dir',
];
