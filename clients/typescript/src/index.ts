/**
 * OpenHands Agent Server TypeScript 客户端
 *
 * 用于镜像 OpenHands Agent Server API 的 TypeScript 客户端库
 * Python SDK 的结构和功能。
 */

// 主要对话和工作区课程
export { RemoteConversation } from './conversation/remote-conversation';
export { LocalConversation } from './conversation/local-conversation';
export {
  Conversation,
  createConversation,
  createConversationAuto,
} from './conversation/conversation';
export { ConversationManager } from './conversation/conversation-manager';
export { RemoteWorkspace } from './workspace/remote-workspace';
export { LocalWorkspace } from './workspace/local-workspace';
export { Workspace, createWorkspace, createWorkspaceAuto } from './workspace/workspace';
export { RemoteState } from './conversation/remote-state';
export { RemoteEventsList } from './events/remote-events-list';
export type { EventSearchOptions, RemoteEventsListOptions } from './events/remote-events-list';

// 卡住检测
export { StuckDetector, DEFAULT_STUCK_THRESHOLDS } from './conversation/stuck-detector';
export type { StuckDetectionThresholds, StuckDetectionResult } from './conversation/stuck-detector';

// 机密注册表
export {
  SecretRegistry,
  StaticSecretSource,
  CallableSecretSource,
} from './conversation/secret-registry';
export type { SecretSource, SecretSourceKind } from './conversation/secret-registry';

// 安全性（确认策略和安全分析器）
export {
  NeverConfirm,
  AlwaysConfirm,
  RiskBasedConfirm,
  ToolBasedConfirm,
  CompositeConfirm,
  createConfirmationPolicy,
} from './security/confirmation-policy';
export type {
  RiskLevel,
  SecurityAnalysisResult,
  ConfirmationPolicy,
} from './security/confirmation-policy';

export {
  PatternBasedAnalyzer,
  AllowlistAnalyzer,
  NoOpAnalyzer,
  CompositeAnalyzer,
  createSecurityAnalyzer,
} from './security/security-analyzer';
export type { SecurityAnalyzer } from './security/security-analyzer';

// 丰富的事件类型
export {
  generateEventId,
  createBaseEvent,
  isMessageEvent,
  isActionEvent,
  isObservationEvent,
  isAgentErrorEvent,
  isObservationLike,
  isConversationErrorEvent,
  isCondensationEvent,
  isHookExecutionEvent,
} from './events/types';
export type {
  EventID,
  EventSource,
  BaseEvent,
  ErrorClassification,
  MessageEvent,
  ActionEvent,
  ObservationEvent,
  AgentErrorEvent,
  ACPToolCallEvent,
  ACPToolCallStatus,
  ACPToolKind,
  StreamingDeltaEvent,
  SystemPromptEvent,
  PauseEvent,
  CondensationRequestEvent,
  CondensationSummaryEvent,
  CondensationEvent,
  ConversationStateUpdateEvent,
  ConversationErrorEvent,
  LLMCompletionLogEvent,
  UserRejectObservation,
  ConfirmationRequestEvent,
  ConfirmationResponseEvent,
  TokenEvent,
  StuckDetectionEvent,
  FinishEvent,
  ThinkEvent,
  HookExecutionEvent,
  HookExecutionEventType,
  ConversationEvent,
} from './events/types';

// 挂钩
export {
  HookEventType,
  HookType,
  HookDecision,
  hookResultShouldContinue,
  createSuccessResult,
  HOOK_EVENT_FIELDS,
  matcherMatches,
  createEmptyHookConfig,
  isHookConfigEmpty,
  normalizeHooksInput,
  hookConfigFromData,
  getHooksForEvent,
  hasHooksForEvent,
  mergeHookConfigs,
  hookConfigToJSON,
} from './hooks';
export type { HookEvent, HookResult, HookDefinition, HookMatcher, HookConfig } from './hooks';

// 智能体课程
export { Agent } from './agent/agent';

// LLM 类和工厂函数
export { LLM, OpenRouterLLM, createLLM, createOpenRouterLLM } from './llm';

// 提示词
export {
  DEFAULT_SYSTEM_PROMPT,
  MINIMAL_SYSTEM_PROMPT,
  TOOL_DESCRIPTIONS,
  generateSystemPrompt,
} from './prompts';

// WebSocket 实时事件客户端
export { WebSocketCallbackClient } from './events/websocket-client';
export type { ErrorCallbackType } from './events/websocket-client';
export { BashWebSocketClient } from './events/bash-websocket-client';
export type { BashWebSocketClientOptions } from './events/bash-websocket-client';

// HTTP 客户端
export { HttpClient, HttpError, isHttpError } from './client/http-client';
export { HooksClient } from './client/hooks-client';
export { MCPClient } from './client/mcp-client';
export { WorkspacesClient } from './client/workspaces-client';
export {
  AGENT_SERVER_VERSION_ERROR_CODE,
  AgentServerFeatureRequirements,
  AgentServerVersionError,
  assertAgentServerSupports,
  clearAgentServerInfoCache,
  compareAgentServerVersions,
  getCachedAgentServerInfo,
  isAgentServerVersionError,
} from './client/agent-server-compatibility';

// 类型和接口
export type {
  ConversationID,
  Event,
  Message,
  MessageContent,
  TextContent,
  ImageContent,
  AgentBase,
  AgentContext,
  LLM as LLMConfig,
  ServerInfo,
  Success,
  EventPage,
  ConversationCallbackType,
  SecretValue,
  ConversationStats,
  ConfirmationPolicyBase,
} from './types/base';

export type { AgentOptions } from './agent/agent';

export { EventSortOrder, AgentExecutionStatus, ConversationExecutionStatus } from './types/base';
export { ConversationSortOrder } from './models/conversation';

// 工作区型号
export type {
  CommandResult,
  FileOperationResult,
  FileDownloadResult,
  GitChange,
  GitChangeStatus,
  GitDiff,
  ExecuteBashRequest,
  BashEventBase,
  BashCommand,
  BashOutput,
  BashError,
  BashEvent,
  BashEventPage,
  BashEventSearchOptions,
  ClearBashEventsResponse,
} from './models/workspace';

// 工作区基本类型和接口
export type {
  IWorkspace,
  BaseWorkspaceOptions,
  GitQueryOptions,
  WorkspaceType,
} from './workspace/base';

// 会话基础类型和接口
export type {
  IConversation,
  IConversationState,
  IEventsList,
  BaseConversationOptions,
  ConversationType,
} from './conversation/base';

// ACP 提供者注册表（镜像 OpenHands-SDK； 请参见 scripts/validate-acp-providers.mjs)
export { ACP_PROVIDERS, ACP_SETTINGS_KEYS, getAcpProvider } from './models/acp';
export type { ACPModelOption, ACPProviderInfo, ACPProviderKey } from './models/acp';
export type {
  ACPModelDiscovery,
  ACPModelDiscoveryError,
  ACPModelDiscoveryRequest,
  ACPModelInfo,
} from './models/acp-model-discovery';

// 智能体配置文件类型（镜子 OpenHands-SDK agent_profile.py + resolver.py）
export type {
  AgentKind,
  ACPServerKind,
  ProfileVerificationSettings,
  OpenHandsAgentProfile,
  ACPAgentProfile,
  AgentProfile,
  AgentProfileSaveInput,
  AgentProfileSummary,
  AgentProfileDiagnostics,
  LaunchedAgentProfile,
  LaunchedProfile,
} from './models/agent-profile';
export type { ToolCatalogEntry, ToolCatalogResponse } from './models/tool-catalog';

// 智能体个人资料客户端
export { AgentProfilesClient } from './client/agent-profiles-client';
export type {
  AgentProfilesClientOptions,
  GetAgentProfileOptions,
  AgentProfileListResponse,
  AgentProfileDetailResponse,
  AgentProfileMutationResponse,
  ActivateAgentProfileResponse,
} from './client/agent-profiles-client';

// deriveSwitchPlan — 纯配置文件切换决策助手
export { deriveSwitchPlan } from './profiles/derive-switch-plan';
export type { SwitchPlan } from './profiles/derive-switch-plan';

// 对话模型
export type {
  ConversationInfo,
  ConversationRuntimeStatus,
  ConversationRuntimeError,
  ConversationRuntimeInfo,
  ACPAgentConfig,
  ACPConversationInfo,
  SendMessageRequest,
  ConfirmationResponseRequest,
  CreateConversationRequest,
  CreateACPConversationRequest,
  UpdateConversationRequest,
  UpdateSecretsRequest,
  StaticSecret,
  LookupSecret,
  SecretObject,
  ConversationSearchRequest,
  ConversationSearchResponse,
  ACPConversationSearchResponse,
  AskAgentRequest,
  AskAgentResponse,
  StartGoalRequest,
  SetSecurityAnalyzerRequest,
  SetConfirmationPolicyRequest,
  ConversationEventSearchOptions,
  ConversationEventCountOptions,
  ForkConversationRequest,
  NavigateConversationRequest,
  AgentResponseResult,
  ConversationEvent as ConversationApiEvent,
  ConversationEventPage,
} from './models/conversation';

// 客户端选项
export type {
  HttpClientOptions,
  RequestOptions,
  HttpResponse,
  HttpValidationErrorItem,
} from './client/http-client';
export type { HooksClientOptions } from './client/hooks-client';
export type { MCPClientOptions } from './client/mcp-client';
export type {
  DeleteWorkspaceResponse,
  WorkspacesClientOptions,
  WorkspacesListResponse,
  WorkspaceItem,
  WorkspaceParentItem,
} from './client/workspaces-client';
export type { AgentServerFeatureRequirement } from './client/agent-server-compatibility';
export type {
  AgentServerConversationSettingsSchema,
  AgentServerMCPOAuthCallbackRequest,
  AgentServerMCPOAuthCallbackResponse,
  AgentServerMCPOAuthStatusResponse,
  AgentServerMCPStartOAuthRequest,
  AgentServerMCPStartOAuthResponse,
  AgentServerMCPTestRequest,
  AgentServerMCPTestResponse,
  AgentServerMCPToolCall,
  AgentServerMCPToolCallResult,
  AgentServerSettingsPatchRequest,
  AgentServerSettingsPatchResponse,
  AgentServerSettingsResponse,
  AgentServerSettingsSchema,
} from './models/agent-server-api';
export type {
  MCPAuthCredential,
  MCPAuthCredential as CanonicalMCPAuthCredential,
  MCPConfig,
  MCPConfigPatch,
  MCPOAuthAuthentication,
  MCPOAuthAuthentication as CanonicalMCPOAuthAuthentication,
  MCPOAuthState,
  MCPOAuthState as CanonicalMCPOAuthState,
  MCPServer,
  MCPServer as CanonicalMCPServer,
  MCPServerPatch,
  MCPTransport,
  MCPTransport as CanonicalMCPTransport,
  RemoteMCPServer,
  RemoteMCPTransport,
  StdioMCPServer,
} from './models/mcp-settings';

export type {
  AliveStatus,
  HealthStatus,
  ReadyStatus,
  ProvidersResponse,
  ModelsResponse,
  VerifiedModelsResponse,
  SettingsSchema,
  ExposedUrl,
  OrgConfig,
  SandboxConfig,
  SkillsRequest,
  SkillInfo,
  SkillsResponse,
  SyncResponse,
  InstallSkillRequest,
  InstalledSkillInfo,
  InstalledSkillSummary,
  InstalledSkillsResponse,
  ToggleSkillResponse,
  SkillActionResponse,
  RefreshSkillResponse,
  MarketplaceSkill,
  MarketplaceResponse,
  SubAgentLevel,
  SubAgentsRequest,
  SubAgentInfo,
  SubAgentsResponse,
  MarketplacePlugin,
  MarketplaceCatalogResponse,
  PluginsRequest,
  PluginInfo,
  PluginsResponse,
  InstallPluginRequest,
  InstalledPluginInfo,
  InstalledPluginsResponse,
  TogglePluginResponse,
  PluginActionResponse,
  RefreshPluginResponse,
  VSCodeUrlResponse,
  VSCodeStatusResponse,
  ProfileInfo,
  ProfileListResponse,
  ProfileDetailResponse,
  ProfileMutationResponse,
  ActivateProfileResponse,
  SaveProfileRequest,
  RenameProfileRequest,
  ValidateProfileError,
  ValidateProfileResponse,
  MetaProfileClass,
  MetaProfile,
  MetaProfileInfo,
  MetaProfileListResponse,
  MetaProfileDetailResponse,
  MetaProfileMutationResponse,
  ActivateMetaProfileResponse,
  ExposeSecretsMode,
  SettingsValue,
  SettingsApiResponse,
  SettingsUpdateRequest,
  SecretInfo,
  SecretsListResponse,
  UpsertSecretRequest,
  UpsertSecretResponse,
  DeleteSecretResponse,
  SecretValueResponse,
  FileSubdirectoryEntry,
  FileSubdirectoryPage,
  FileHomeResponse,
  FileSearchSubdirsOptions,
  HooksRequest,
  HooksResponse,
  StdioMCPServerSpec,
  RemoteMCPServerType,
  RemoteMCPServerSpec,
  MCPOAuthClientAuthMethod,
  MCPJsonValue,
  MCPServerSpec,
  MCPToolCallSpec,
  MCPTestRequest,
  MCPToolCallResult,
  MCPTestSuccess,
  MCPTestFailureKind,
  MCPTestFailure,
  MCPTestResponse,
  MCPOAuthStartResponse,
  MCPOAuthProbeStatus,
  MCPOAuthStatusResponse,
  MCPOAuthCallbackRequest,
  SharedConversation,
  EventPage as ApiEventPage,
} from './models/api';

export type { WebSocketClientOptions } from './events/websocket-client';

export type { RemoteWorkspaceOptions } from './workspace/remote-workspace';

export type { LocalWorkspaceOptions } from './workspace/local-workspace';

export type { WorkspaceOptions, CreateWorkspaceOptions } from './workspace/workspace';

export type { RemoteConversationOptions } from './conversation/remote-conversation';

export type {
  LocalConversationOptions,
  ToolExecutor,
  ConversationTokenCallback,
} from './conversation/local-conversation';

export type { ConversationOptions, CreateConversationOptions } from './conversation/conversation';

export type { ConversationManagerOptions } from './conversation/conversation-manager';

// LLM 类型和接口
export type {
  ILLM,
  BaseLLMOptions,
  LLMProviderType,
  MessageRole,
  ContentPart,
  ChatMessage,
  Tool,
  ToolCall,
  ChatCompletionOptions,
  ChatCompletionChoice,
  TokenUsage,
  ChatCompletionResponse,
  ChatCompletionChunk,
  TokenCallbackType,
  TokenStreamEvent,
} from './llm';
export type { OpenRouterLLMOptions, LLMOptions, CreateLLMOptions } from './llm';

// 提示词类型
export type { SystemPromptOptions } from './prompts';

// 重新导入以默认导出
import { RemoteConversation } from './conversation/remote-conversation';
import { LocalConversation } from './conversation/local-conversation';
import {
  Conversation,
  createConversation,
  createConversationAuto,
} from './conversation/conversation';
import { ConversationManager } from './conversation/conversation-manager';
import { RemoteWorkspace } from './workspace/remote-workspace';
import { LocalWorkspace } from './workspace/local-workspace';
import { Workspace, createWorkspace, createWorkspaceAuto } from './workspace/workspace';
import { RemoteState } from './conversation/remote-state';
import { RemoteEventsList } from './events/remote-events-list';
import { WebSocketCallbackClient } from './events/websocket-client';
import { BashWebSocketClient } from './events/bash-websocket-client';
import { HttpClient, HttpError, isHttpError } from './client/http-client';
import { HooksClient } from './client/hooks-client';
import { MCPClient } from './client/mcp-client';
import { WorkspacesClient } from './client/workspaces-client';
import {
  AGENT_SERVER_VERSION_ERROR_CODE,
  AgentServerFeatureRequirements,
  AgentServerVersionError,
  assertAgentServerSupports,
  clearAgentServerInfoCache,
  compareAgentServerVersions,
  getCachedAgentServerInfo,
  isAgentServerVersionError,
} from './client/agent-server-compatibility';
import { EventSortOrder, AgentExecutionStatus, ConversationExecutionStatus } from './types/base';
import { ConversationSortOrder } from './models/conversation';
import { Agent } from './agent/agent';
import { LLM, OpenRouterLLM, createLLM, createOpenRouterLLM } from './llm';
import {
  HookEventType,
  HookType,
  HookDecision,
  hookResultShouldContinue,
  createSuccessResult,
  HOOK_EVENT_FIELDS,
  matcherMatches,
  createEmptyHookConfig,
  isHookConfigEmpty,
  normalizeHooksInput,
  hookConfigFromData,
  getHooksForEvent,
  hasHooksForEvent,
  mergeHookConfigs,
  hookConfigToJSON,
} from './hooks';

// 默认导出方便
export default {
  RemoteConversation,
  LocalConversation,
  Conversation,
  createConversation,
  createConversationAuto,
  ConversationManager,
  RemoteWorkspace,
  LocalWorkspace,
  Workspace,
  createWorkspace,
  createWorkspaceAuto,
  RemoteState,
  RemoteEventsList,
  WebSocketCallbackClient,
  BashWebSocketClient,
  HttpClient,
  HttpError,
  isHttpError,
  HooksClient,
  MCPClient,
  WorkspacesClient,
  AGENT_SERVER_VERSION_ERROR_CODE,
  AgentServerFeatureRequirements,
  AgentServerVersionError,
  assertAgentServerSupports,
  clearAgentServerInfoCache,
  compareAgentServerVersions,
  getCachedAgentServerInfo,
  isAgentServerVersionError,
  EventSortOrder,
  ConversationSortOrder,
  AgentExecutionStatus,
  ConversationExecutionStatus,
  Agent,
  LLM,
  OpenRouterLLM,
  createLLM,
  createOpenRouterLLM,
  HookEventType,
  HookType,
  HookDecision,
  hookResultShouldContinue,
  createSuccessResult,
  HOOK_EVENT_FIELDS,
  matcherMatches,
  createEmptyHookConfig,
  isHookConfigEmpty,
  normalizeHooksInput,
  hookConfigFromData,
  getHooksForEvent,
  hasHooksForEvent,
  mergeHookConfigs,
  hookConfigToJSON,
};
