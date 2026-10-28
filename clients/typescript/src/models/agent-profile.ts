/**
 * AgentProfile — TypeScript Python SDK 的镜像
 * `openhands.sdk.profiles.agent_profile` 模块。
 *
 * AgentProfile 并集对 `agent_kind` 具有歧视性并且带有
 * *而不是* llm_profile_ref mcp_server_refs
 * 凭据，反映 Python 设计。 参见史诗#3713。
 */

import type { ACPProviderKey } from './acp';
import type { MCPJsonValue } from './api';

// ── 共享支持类型────────────────────────────────────────────────────

/** 整个 {@link AgentProfile} 联盟的鉴别器。*/
export type AgentKind = 'openhands' | 'acp';

/** ACP 后端选择器：内置提供程序密钥或 `'custom'` 哨兵值。*/
export type ACPServerKind = ACPProviderKey | 'custom';

/** 机密-免费批评者/细化策略存储在 OpenHands 配置文件中。*/
export interface ProfileVerificationSettings {
  critic_enabled: boolean;
  critic_mode: string;
  enable_iterative_refinement: boolean;
  critic_threshold: number;
  max_refinement_iterations: number;
  critic_server_url: string | null;
  critic_model_name: string | null;
}

/** 按名称选择的工具，带有可选的 `create()` 参数。*/
export interface ProfileToolSpec {
  name: string;
  params?: Record<string, MCPJsonValue>;
}

// ── 型材变体──────────────────────────────────────────────────────────

interface AgentProfileBase {
  schema_version?: number;
  /** 稳定的 UUID 句柄 — 重命名时不会改变。*/
  id: string;
  /** 面向人性化、可重命名的密钥。*/
  name: string;
  /** 单调修订计数器，每次保存的编辑都会发生碰撞。*/
  revision: number;
  /**
   * 要公开用户的哪些全局配置的 MCP 服务器。
   * `null`=全部； `[]` = None; 非 null 列表 = 指定键的过滤器。
   */
  mcp_server_refs: string[] | null;
  /**
   * 要公开哪些用户已保存的机密。 仅有名称——价值永存
   * 在机密商店里。 `null`=全部； `[]` = None; 非 null 列表 = 过滤器
   * 到指定的键。 严格：不添加任何内容，因此 ACP 配置文件必须
   * 列出自己的提供者凭据来接收它。
   */
  secret_refs?: string[] | null;
}

/** `agent_kind="openhands"` 变体 — 按名称引用 LLM 配置文件。*/
export interface OpenHandsAgentProfile extends AgentProfileBase {
  agent_kind: 'openhands';
  /** 要解析的 LLM 配置文件的名称。*/
  llm_profile_ref: string;
  agent: string;
  /**
   * 服务器发现的要排除的技能的名称（拒绝列表）
   * 目录）。 `[]` = 所有已发现的技能； 未知的名称是无操作的。
   */
  disabled_skills?: string[];
  /** 公共目录技能加载； `null` = 全部，`[]` = None。 用户/项目技能不受影响。*/
  public_skills?: string[] | null;
  /** 替换内置角色，保留能力指导； 需要`profile_persona_v1`。*/
  persona?: string | null;
  system_message_suffix: string | null;
  condenser: unknown;
  verification: ProfileVerificationSettings;
  /** 启用内置任务路由工具，该工具使用 `meta_profile_ref`。*/
  enable_classify_and_switch_llm_tool?: boolean;
  /** 路由工具使用的元配置文件； `null` = 商店中的第一个。*/
  meta_profile_ref?: string | null;
  /** 启动工具； `null` = 服务器的标准集。*/
  tools: ProfileToolSpec[] | null;
  tool_concurrency_limit: number;
}

/** `agent_kind="acp"` 变体 — 命名 ACP 后端； 存储没有凭据。*/
export interface ACPAgentProfile extends AgentProfileBase {
  agent_kind: 'acp';
  /** ACP 提供程序密钥，或 `'custom'` 用户提供的命令。*/
  acp_server: ACPServerKind;
  acp_model: string | null;
  acp_session_mode: string | null;
  acp_prompt_timeout: number;
  /** 超时（秒）用于 ACP 服务器启动。*/
  acp_startup_timeout?: number;
  acp_command: string | null;
  acp_args: string[] | null;
}

/**
 * `agent_kind` 上的歧视联盟。 使用 `agent_kind` 字段缩小范围：
 * ```ts
 * if (profile.agent_kind === 'OpenHands') { ... }
 * ```
 */
export type AgentProfile = OpenHandsAgentProfile | ACPAgentProfile;

/**
 * `POST /api/agent-profiles/{name}` 的请求正文（创建或覆盖）。
 *
 * 对 `agent_kind` 进行区分，因此载荷不能混合来自另一个的字段
 * 变体（服务器型号为`extra=forbid`）。 非判别字段是
 * 可选：服务器管理的身份（`id`/`revision`/`schema_version`) 是
 * 在创建时铸造并在覆盖时保留。 未设置的字段将采用
 * 服务器端默认存在一个 - 除了 `llm_profile_ref`，即
 * `openhands` 变体所需（省略它会产生 422）。
 */
export type AgentProfileSaveInput =
  | ({ agent_kind: 'openhands' } & Partial<Omit<OpenHandsAgentProfile, 'agent_kind'>>)
  | ({ agent_kind: 'acp' } & Partial<Omit<ACPAgentProfile, 'agent_kind'>>);

// ── 摘要投影（列表端点） ──────────────────────────────────────

/** 列表端点返回的轻量级摘要。*/
export interface AgentProfileSummary {
  id: string | null;
  name: string;
  agent_kind: AgentKind;
  revision: number | null;
  llm_profile_ref: string | null;
  mcp_server_refs: string[] | null;
}

// ── 物化诊断──────────────────────────────────────────────────

/**
 * 返回的干运行解决报告是 `POST /api/agent-profiles/{name}/materialize`。
 * 逐场镜像`openhands.sdk.profiles.resolver.AgentProfileDiagnostics`。
 *
 * 此处报告悬空引用 (valid=False)，而不是 HTTP 错误。
 */
export interface AgentProfileDiagnostics {
  agent_kind: AgentKind;
  valid: boolean;
  errors: string[];

  /** 机密范围； `null` = unrestricted.*/
  secret_refs?: string[] | null;

  // OpenHands LLM 参考。
  llm_profile_ref: string | null;
  llm_profile_resolved: boolean;
  llm_api_key_set: boolean;

  // MCP 组成（两种变体）。
  mcp_server_refs: string[] | null;
  /** MCP 启动将公开的配置键。*/
  resolved_mcp_config_keys?: string[];
  dangling_mcp_server_refs: string[];

  // 技能选择（仅限 OpenHands）：公共允许列表、拒绝列表和已解决的技能。
  public_skills?: string[] | null;
  disabled_skills?: string[];
  resolved_skills?: string[];

  /** 运行时无法运行选定的工具。*/
  unusable_tools?: string[];

  // ACP 提供商凭据渠道（仅限 ACP 变体）。
  acp_api_key_secret_name: string | null;
  acp_base_url_secret_name: string | null;
  acp_file_secret_names: string[];

  // 元配置文件路由（仅限 OpenHands）。
  meta_profile_ref?: string | null;
  dangling_meta_profile_ref?: string | null;
  dangling_meta_profile_llm_refs?: string[];

  // 已脱敏已解决的设置，当前有效。
  resolved_settings: Record<string, unknown> | null;
}

// ── 发射出处──────────────────────────────────────────────────────

/** 镜子`openhands.sdk.profiles.agent_profile.LaunchedAgentProfile`.*/
export interface LaunchedAgentProfile {
  agent_profile_id: string;
  revision: number;
  /** 启动时间机密允许列表，也在恢复时强制执行。*/
  secret_refs?: string[] | null;
}

/**
 * 当配置文件启动对话时记录的来源快照。
 * @已弃用使用 LaunchedAgentProfile，它镜像服务器载荷。
 *
 * 存储在对话中，以便客户可以识别当前的配置文件
 * 没有脆弱的设置比较。 参见史诗#3713。
 */
export interface LaunchedProfile {
  /** 启动对话的配置文件的稳定 ID。*/
  profile_id: string;
  /** 在启动时修改配置文件。*/
  revision: number;
}
