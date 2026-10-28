/**
 * Agent Server APIs 的辅助模型。
 */

import type { HookConfig } from '../hooks';
import type { LLM } from '../types/base';

export interface AliveStatus {
  status: string;
}

export interface HealthStatus {
  status: string;
}

export interface ReadyStatus {
  status: string;
  message?: string;
}

export interface ProvidersResponse {
  providers: string[];
}

export interface ModelsResponse {
  models: string[];
}

export interface VerifiedModelsResponse {
  models: Record<string, string[]>;
}

export interface LLMSubscriptionStatusResponse {
  vendor: string;
  connected: boolean;
  account_email: string | null;
  expires_at: number | null;
}

export interface LLMSubscriptionDeviceStartResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string | null;
  expires_at: number;
  interval_seconds: number;
}

export interface LLMSubscriptionDevicePollRequest {
  device_code: string;
}

export interface LLMSubscriptionModelsResponse {
  vendor: string;
  models: string[];
}

export interface SettingsSchema {
  model_name: string;
  sections: Array<Record<string, unknown>>;
}

export interface ExposedUrl {
  name: string;
  url: string;
  port: number;
}

export interface OrgConfig {
  repository: string;
  provider: string;
  org_repo_url: string;
  org_name: string;
}

export interface SandboxConfig {
  exposed_urls: ExposedUrl[];
}

export interface SkillsRequest {
  load_public?: boolean;
  load_user?: boolean;
  load_project?: boolean;
  load_org?: boolean;
  marketplace_path?: string | null;
  project_dir?: string | null;
  sandbox_config?: SandboxConfig | null;
}

export interface SkillInfo {
  name: string;
  type: 'repo' | 'knowledge' | 'agentskills';
  content: string;
  triggers: string[];
  source?: string | null;
  description?: string | null;
  is_agentskills_format?: boolean;
}

export interface SkillsResponse {
  skills: SkillInfo[];
  sources: Record<string, number>;
}

export interface SyncResponse {
  status: 'success' | 'error';
  message: string;
}

export interface InstallSkillRequest {
  source: string;
  force?: boolean;
  ref?: string | null;
  repo_path?: string | null;
}

export interface InstalledSkillInfo {
  name: string;
  version?: string | null;
  description?: string | null;
  enabled: boolean;
  source?: string | null;
  installed_at?: string | null;
  install_path?: string | null;
}

export interface InstalledSkillSummary {
  name: string;
  version?: string | null;
  enabled: boolean;
}

export interface InstalledSkillsResponse {
  skills: InstalledSkillSummary[];
}

export interface ToggleSkillResponse {
  name: string;
  enabled: boolean;
}

export interface SkillActionResponse {
  message: string;
}

export interface RefreshSkillResponse {
  message: string;
  skill: InstalledSkillSummary;
}

export interface MarketplaceSkill {
  name: string;
  description: string;
  source: string;
  installed: boolean;
}

export interface MarketplaceResponse {
  skills: MarketplaceSkill[];
}

/**
 * 子智能体：基于文件的内置委托智能体可用的目录
 * 到工作区，由智能体服务器的只读 `POST /api/sub-agents` 提供服务
 * （镜子`POST /api/skills`）。 “子智能体”与代表智能体不同
 * 来自顶层智能体和 `agent-profiles`。
 */

/** 发现子智能体的范围（服务器 `AgentDefinitionLevel`）。*/
export type SubAgentLevel = 'project' | 'user' | 'builtin' | 'plugin' | 'programmatic';

export interface SubAgentsRequest {
  /** 从`~/.agents/agents`和`~/.openhands/agents`加载用户智能体。*/
  load_user?: boolean;
  /** 从工作区加载项目智能体。*/
  load_project?: boolean;
  /** 加载 SDK 内置智能体（通用、代码浏览器等）。*/
  load_builtin?: boolean;
  /** 工作区项目智能体的目录路径。*/
  project_dir?: string | null;
}

/**
 * 服务器 `AgentDefinition` 的无损视图：每个前置元数据字段加上
 * 发现了 `level`/`source`、`is_builtin` 标志和内联
 * `system_prompt` (Markdown body) 因此详细视图不需要额外的获取。
 */
export interface SubAgentInfo {
  name: string;
  description: string;
  model: string;
  color: string | null;
  tools: string[];
  skills: string[];
  system_prompt: string;
  when_to_use_examples: string[];
  permission_mode: string | null;
  max_iteration_per_run: number | null;
  max_budget_per_run: number | null;
  mcp_servers: Record<string, unknown> | null;
  profile_store_dir: string | null;
  hooks: HookConfig | null;
  /** 上下文上下文压缩器规范（不透明可区分联合），或 null 默认。*/
  condenser: unknown;
  metadata: Record<string, unknown>;
  level: SubAgentLevel | null;
  source: string | null;
  is_builtin: boolean;
}

export interface SubAgentsResponse {
  agents: SubAgentInfo[];
}

export interface MarketplacePlugin {
  name: string;
  description: string | null;
  source: string;
  ref?: string | null;
  repo_path?: string | null;
  installed: boolean;
}

export interface MarketplaceCatalogResponse {
  plugins: MarketplacePlugin[];
}

export interface PluginsRequest {
  load_user?: boolean;
  load_project?: boolean;
  project_dir?: string | null;
}

export interface PluginInfo {
  name: string;
  version: string;
  description: string;
}

export interface PluginsResponse {
  plugins: PluginInfo[];
}

export interface InstallPluginRequest {
  source: string;
  ref?: string | null;
  repo_path?: string | null;
  force?: boolean;
}

export interface InstalledPluginInfo {
  name: string;
  version: string;
  description: string;
  enabled: boolean;
  source: string;
  resolved_ref?: string | null;
  repo_path?: string | null;
  installed_at: string;
  install_path: string;
}

export interface InstalledPluginsResponse {
  plugins: InstalledPluginInfo[];
}

export interface TogglePluginResponse {
  name: string;
  enabled: boolean;
}

export interface PluginActionResponse {
  message: string;
}

export interface RefreshPluginResponse {
  message: string;
  plugin: InstalledPluginInfo;
}

export interface VSCodeUrlResponse {
  url: string | null;
}

export interface VSCodeStatusResponse {
  running: boolean;
  enabled: boolean;
  message?: string;
}

export interface ProfileInfo {
  name: string;
  model: string | null;
  base_url: string | null;
  api_key_set: boolean;
}

export interface ProfileListResponse {
  profiles: ProfileInfo[];
  active_profile: string | null;
}

export interface ProfileDetailResponse {
  name: string;
  config: Record<string, unknown>;
  api_key_set: boolean;
}

export interface ProfileMutationResponse {
  name: string;
  message: string;
}

export interface ActivateProfileResponse {
  name: string;
  message: string;
  llm_applied: boolean;
}

export interface SaveProfileRequest {
  llm: LLM;
  include_secrets?: boolean;
}

/**
 * LLM 飞行前验证端点的结构性错误
 * (``POST /api/profiles/{name}/validate``). ``type`` 带有 SDK 的键入内容
 * LLM 异常类名 (e.g. ``LLMAuthenticationError``,
 * ``LLMBadRequestError``) 和 ``message`` 人类可读的细节。
 */
export interface ValidateProfileError {
  type: string;
  message: string;
}

/**
 * LLM 飞行前检查的结果。 ``valid`` 是 ``false`` 和 ``error``
 * 提交的 LLM 配置被拒绝时的详细信息（无效模型，
 * 缺少提供者前缀、错误的基 URL、无效的 API 键）； 瞬态
 * 速率限制/超时响应报告为 ``valid: true``，没有错误。
 */
export interface ValidateProfileResponse {
  valid: boolean;
  error?: ValidateProfileError | null;
}

export interface RenameProfileRequest {
  new_name: string;
}

/**
 * 元配置文件：使用的声明性模型路由配置
 * ``route_task_to_model`` 工具（智能体-服务器 ``/api/meta-profiles``）。
 *
 * 每个模型参考（``classifier_model`` 和每个类的 ``model``）是
 * 已保存的 LLM 配置文件的名称，而不是原始模型字符串。 直接路由
 * 元配置文件集 ``prompt_template``（使用 ``{{ instance_text }}`` 渲染
 * 和可选的 ``{{ model_table }}``) 代替 ``classes``； 这两种模式是
 * 相互排斥的。
 */
export interface MetaProfileClass {
  description: string;
  /** 为此类切换到的已保存 LLM 配置文件的名称。*/
  model: string;
}

export interface MetaProfile {
  /** 用于对任务进行分类的已保存 LLM 配置文件的名称。*/
  classifier_model: string;
  /** 任务类及其目标配置文件的有序列表（结构化模式）。*/
  classes?: MetaProfileClass[];
  /** 直接路由提示词模板； 必须包含 ``{{ instance_text }}``。*/
  prompt_template?: string | null;
  /** 插入 ``{{ model_table }}`` 的文本用于直接路由提示词。*/
  model_table?: string | null;
}

export interface MetaProfileInfo {
  name: string;
  classifier_model: string | null;
  num_classes: number;
}

export interface MetaProfileListResponse {
  meta_profiles: MetaProfileInfo[];
  active_meta_profile: string | null;
}

export interface MetaProfileDetailResponse {
  name: string;
  config: MetaProfile;
}

export interface MetaProfileMutationResponse {
  name: string;
  message: string;
}

export interface ActivateMetaProfileResponse {
  name: string;
  message: string;
  /** False 当智能体设置无法路由时 (e.g. ACP)，因此没有任何内容被激活。*/
  applied?: boolean;
}

export type ExposeSecretsMode = 'encrypted' | 'plaintext';

export type SettingsValue = unknown;

export interface SettingsApiResponse {
  agent_settings: Record<string, SettingsValue>;
  conversation_settings: Record<string, SettingsValue>;
  llm_api_key_is_set: boolean;
  [key: string]: unknown;
}

export interface SettingsUpdateRequest {
  agent_settings_diff?: Record<string, SettingsValue>;
  conversation_settings_diff?: Record<string, SettingsValue>;
  [key: string]: unknown;
}

export interface SecretInfo {
  name: string;
  description?: string;
}

export interface SecretsListResponse {
  secrets: SecretInfo[];
}

export interface UpsertSecretRequest {
  name: string;
  value: string;
  description?: string;
}

export interface UpsertSecretResponse {
  name: string;
  description?: string;
}

export interface DeleteSecretResponse {
  deleted: boolean;
}

export interface GitProviderRepository {
  id: string;
  full_name: string;
  git_provider: string;
  is_public: boolean;
  stargazers_count?: number | null;
  pushed_at?: string | null;
  main_branch?: string | null;
}

export interface GitProviderRepositoryPage {
  items: GitProviderRepository[];
  next_page_id: string | null;
  missing_token: boolean;
}

export type SecretValueResponse = string;

export interface FileSubdirectoryEntry {
  name: string;
  path: string;
}

export interface FileSubdirectoryPage {
  items: FileSubdirectoryEntry[];
  next_page_id: string | null;
}

export interface FileBrowserEntry {
  label: string;
  path: string;
}

export interface FileHomeResponse {
  home: string;
  favorites?: FileBrowserEntry[];
  locations?: FileBrowserEntry[];
}

export interface FileHomeOptions {
  /** 在响应的 `favorites` 中包含隐藏的顶级目录。*/
  includeHidden?: boolean;
}

export interface FileSearchSubdirsOptions {
  pageId?: string | null;
  limit?: number;
  /** 包括隐藏的子目录（名称以“.”开头）。*/
  includeHidden?: boolean;
}

export interface HooksRequest {
  project_dir?: string | null;
}

export interface HooksResponse {
  hook_config?: HookConfig | null;
}

/** @deprecated Use `AgentServerMCPTestRequest["server"]` for MCP test payloads. */
export interface StdioMCPServerSpec {
  type: 'stdio';
  command: string;
  args?: string[];
  env?: Record<string, string>;
  cwd?: string | null;
}

export type RemoteMCPServerType = 'http' | 'shttp' | 'streamable-http' | 'sse';

/** @deprecated Use `AgentServerMCPTestRequest["server"]` for MCP test payloads. */
export interface RemoteMCPServerSpec {
  type: RemoteMCPServerType;
  url: string;
  headers?: Record<string, string>;
  /** @deprecated Use the tagged `auth` credential instead. */
  api_key?: string | null;
  auth?: MCPAuthCredential | null;
  timeout?: number | null;
  sse_read_timeout?: number | null;
  keep_alive?: boolean | null;
}

export type MCPTransport = 'stdio' | 'http' | 'sse' | 'streamable-http';

export type MCPOAuthClientAuthMethod =
  'none' | 'client_secret_post' | 'client_secret_basic' | 'private_key_jwt';

export type MCPJsonValue =
  boolean | number | string | null | MCPJsonValue[] | { [key: string]: MCPJsonValue };

export interface MCPOAuthAuthentication {
  type: 'oauth';
  client_auth_method?: MCPOAuthClientAuthMethod | null;
  scopes?: string | string[] | null;
  client_name?: string | null;
  client_metadata_url?: string | null;
  client_id?: string | null;
  client_secret?: string | null;
  additional_client_metadata?: Record<string, MCPJsonValue> | null;
}

export interface MCPOAuthState {
  tokens?: Record<string, MCPJsonValue> | null;
  client_info?: Record<string, MCPJsonValue> | null;
  token_expires_at?: number | null;
}

export type MCPAuthCredential =
  | { strategy: 'none' }
  | { strategy: 'api_key'; value?: string | null; header_name?: string | null }
  | { strategy: 'bearer'; value?: string | null }
  | { strategy: 'basic'; username: string; password?: string | null }
  | { strategy: 'header'; headers?: Record<string, string> | null }
  | {
      strategy: 'oauth2';
      authentication?: MCPOAuthAuthentication | null;
      state?: MCPOAuthState | null;
    };

export interface MCPServer {
  url?: string | null;
  transport?: MCPTransport | null;
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;
  cwd?: string | null;
  description?: string | null;
  icon?: string | null;
  timeout?: number | null;
  sse_read_timeout?: number | null;
  keep_alive?: boolean | null;
  headers?: Record<string, string> | null;
  auth?: MCPAuthCredential | null;
  /**
   * 服务器是否暴露于智能体。 禁用的服务器完全保持不变
   * 已配置 -- 包含机密 -- 但在创建 MCP 工具时会被跳过
   * 当服务器转发到 ACP 子进程时。 默认为 True。
   */
  enabled?: boolean | null;
}

/** @deprecated Use `AgentServerMCPTestRequest["server"]` for MCP test payloads. */
export type MCPServerSpec = StdioMCPServerSpec | RemoteMCPServerSpec | MCPServer;

/** @deprecated Use `AgentServerMCPToolCall`. */
export interface MCPToolCallSpec {
  name: string;
  arguments?: Record<string, unknown>;
}

/** @deprecated Use `AgentServerMCPTestRequest`. */
export interface MCPTestRequest {
  server: MCPServerSpec;
  name?: string;
  timeout?: number;
  tool_call?: MCPToolCallSpec | null;
}

/** @deprecated Use `AgentServerMCPToolCallResult`. */
export interface MCPToolCallResult {
  is_error: boolean;
  text: string;
}

export interface MCPTestSuccess {
  ok: true;
  tools: string[];
  tool_result?: MCPToolCallResult | null;
  resolved_mcp_servers?: Record<string, unknown>[] | null;
  oauth_state?: MCPOAuthState | null;
}

export type MCPTestFailureKind = 'timeout' | 'connection' | 'unknown';

export interface MCPTestFailure {
  ok: false;
  error: string;
  error_kind: MCPTestFailureKind;
}

/** @deprecated Use `AgentServerMCPTestResponse`. */
export type MCPTestResponse = MCPTestSuccess | MCPTestFailure;

/** @deprecated Use `AgentServerMCPStartOAuthResponse`. */
export interface MCPOAuthStartResponse {
  ok: boolean;
  job_id?: string | null;
  authorization_url?: string | null;
  error?: string | null;
  error_kind?: MCPTestFailureKind | null;
}

export type MCPOAuthProbeStatus = 'pending' | 'authorizing' | 'succeeded' | 'failed';

/** @deprecated Use `AgentServerMCPOAuthStatusResponse`. */
export interface MCPOAuthStatusResponse {
  ok: boolean;
  status: MCPOAuthProbeStatus;
  job_id: string;
  authorization_url?: string | null;
  callback_ready?: boolean;
  tools?: string[] | null;
  tool_result?: MCPToolCallResult | null;
  oauth_state?: MCPOAuthState | null;
  error?: string | null;
  error_kind?: MCPTestFailureKind | null;
}

/** @deprecated Use `AgentServerMCPOAuthCallbackRequest`. */
export interface MCPOAuthCallbackRequest {
  callback_url: string;
}

export interface SharedConversation {
  id: string;
  created_by_user_id: string | null;
  selected_repository: string | null;
  selected_branch: string | null;
  git_provider: string | null;
  title: string | null;
  pr_number: number[];
  llm_model: string | null;
  metrics: unknown | null;
  parent_conversation_id: string | null;
  sub_conversation_ids: string[];
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface EventPage<TEvent = unknown> {
  items: TEvent[];
  next_page_id: string | null;
}
