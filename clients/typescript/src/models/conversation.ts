/**
 * 对话相关模型和接口
 */

import {
  ConversationID,
  ConversationExecutionStatus,
  AgentExecutionStatus,
  ConfirmationPolicyBase,
  ConversationStats,
  AgentBase,
  Event,
  EventPage,
  Message,
} from '../types/base';
import type { HookConfig } from '../hooks';
import type { LaunchedAgentProfile, LaunchedProfile } from './agent-profile';

export enum ConversationSortOrder {
  CREATED_AT = 'CREATED_AT',
  UPDATED_AT = 'UPDATED_AT',
  CREATED_AT_DESC = 'CREATED_AT_DESC',
  UPDATED_AT_DESC = 'UPDATED_AT_DESC',
}

export type ConversationRuntimeStatus =
  'available' | 'starting' | 'missing' | 'ownership_lost' | 'error';

export interface ConversationRuntimeError {
  code: string;
  message: string;
}

export interface ConversationRuntimeInfo {
  runtime_status: ConversationRuntimeStatus;
  can_resume: boolean;
  runtime_error: ConversationRuntimeError | null;
}

export interface ConversationInfo {
  id: ConversationID;
  /** 支持此目录条目的执行运行时的可用性。*/
  runtime_info?: ConversationRuntimeInfo | null;
  /**
   * 会话的当前执行状态。
   * 注意：该字段在API中从agent_status重命名为execution_status。
   */
  execution_status: ConversationExecutionStatus;
  /**
   * @已弃用使用 execution_status 代替。 该字段保留用于向后兼容性。
   */
  agent_status?: AgentExecutionStatus;
  confirmation_policy: ConfirmationPolicyBase;
  activated_knowledge_skills: string[];
  invoked_skills?: string[];
  agent: AgentBase;
  workspace: unknown;
  persistence_dir: string;
  max_iterations?: number;
  stuck_detection?: boolean;
  conversation_stats?: ConversationStats;
  /** API 可能会返回统计信息而不是 conversation_stats*/
  stats?: ConversationStats;
  hook_config?: HookConfig | null;
  blocked_actions?: Record<string, string>;
  blocked_messages?: Record<string, string>;
  title?: string;
  created_at?: string;
  updated_at?: string;
  tags?: Record<string, string>;
  /**
   * 对话树的 HEAD：下一个附加事件的父级。
   * `null` 表示一棵空树（或者，对于预告片对话，线性
   * 尾巴）。 通过 `navigate` 移动它会重新定位智能体运行的活动分支
   * 上。 请参阅{@link ConversationClient.navigateConversation}。
   */
  leaf_event_id?: string | null;
  /**
   * 发起此对话的智能体个人资料的出处。
   * 当对话通过 `agent_profile_id` 开始时出现； 缺席
   * 用于直接从 `agent` 或 `agent_settings` 开始的对话。
   */
  launched_agent_profile?: LaunchedAgentProfile | null;
  /** @deprecated Use launched_agent_profile, the canonical server field. */
  launched_profile?: LaunchedProfile | null;
  /**
   * @已弃用使用 execution_status 代替。 该字段保留用于向后兼容性。
   */
  status?: ConversationExecutionStatus;
  [key: string]: unknown;
}

export interface ACPAgentConfig {
  kind?: string;
  [key: string]: unknown;
}

export type ACPConversationInfo = ConversationInfo & {
  agent: ACPAgentConfig;
};

export interface SendMessageRequest {
  role: 'user';
  content: Array<{
    type: string;
    text?: string;
    image_urls?: string[];
  }>;
  run: boolean;
}

export interface ConfirmationResponseRequest {
  accept: boolean;
  reason?: string;
}

export interface CreateConversationRequest {
  agent: AgentBase;
  initial_message?: Message;
  max_iterations: number;
  stuck_detection: boolean;
  workspace: Record<string, unknown>;
  hook_config?: HookConfig | null;
  user_id?: string | null;
}

export interface CreateACPConversationRequest {
  agent: ACPAgentConfig;
  initial_message?: Message;
  max_iterations: number;
  stuck_detection: boolean;
  workspace: Record<string, unknown>;
  hook_config?: HookConfig | null;
  user_id?: string | null;
}

export interface UpdateConversationRequest {
  title?: string;
  tags?: Record<string, string>;
}

export interface StaticSecret {
  kind: 'StaticSecret';
  value?: string | null;
  description?: string | null;
}

export interface LookupSecret {
  kind: 'LookupSecret';
  url: string;
  headers?: Record<string, string>;
  description?: string | null;
  /**
   * @已弃用 v1.23.0 智能体服务器使用 `url` 和可选 `headers`。
   */
  source?: string;
  /**
   * @已弃用 v1.23.0 智能体服务器使用 `url` 和可选 `headers`。
   */
  key?: string;
}

export type SecretObject = StaticSecret | LookupSecret;

export interface UpdateSecretsRequest {
  secrets: Record<string, SecretObject>;
}

export interface ConversationSearchRequest {
  page_id?: string;
  limit?: number;
  status?: ConversationExecutionStatus;
  sort_order?: ConversationSortOrder;
  tag?: string[];
}

export interface AskAgentRequest {
  question: string;
}

/**
 * 载荷在对话中启动 `/goal` 循环。
 *
 * 镜像智能体服务器的 `StartGoalRequest`。 循环附加消息并
 * 在与主程序相同的对话历史/事件流中运行智能体
 * 聊天； 它不会分叉或创建单独的对话。
 */
export interface StartGoalRequest {
  /** 目标目标追求和审核。 服务器端不能为空。*/
  objective: string;
  /**
   * 放弃之前的最大审核轮次。 服务器需要 `>= 1` 和默认值
   * 省略时为 `10`。
   */
  max_iterations?: number;
}

export interface AskAgentResponse {
  response: string;
}

export interface SetSecurityAnalyzerRequest {
  security_analyzer: unknown | null;
}

export interface SetConfirmationPolicyRequest {
  policy: ConfirmationPolicyBase;
}

export interface ConversationEventSearchOptions {
  page_id?: string;
  limit?: number;
  kind?: string;
  source?: string;
  body?: string;
  sort_order?: 'TIMESTAMP' | 'TIMESTAMP_DESC';
  timestamp__gte?: string;
  timestamp__lt?: string;
}

export type ConversationEventCountOptions = Omit<
  ConversationEventSearchOptions,
  'page_id' | 'limit' | 'sort_order'
>;

export interface ConversationSearchResponse {
  items: ConversationInfo[];
  next_page_id?: string;
  total_count?: number;
}

export interface ACPConversationSearchResponse {
  items: ACPConversationInfo[];
  next_page_id?: string;
  total_count?: number;
}

export interface ForkConversationRequest {
  id?: string;
  title?: string;
  tags?: Record<string, string>;
  reset_metrics?: boolean;
}

/**
 * 载荷将对话的 HEAD 移至现有事件（就地
 * 重新root）。 与分叉不同，这不会创建新的对话 - 所有分支
 * 保留在磁盘上，并且仅智能体的活动分支在下次更改时运行。
 */
export interface NavigateConversationRequest {
  /**
   * 生成新的 HEAD 的事件，重新确定活动分支的根。 省略或通过
   * `null` 选择空树（故意的新根）。
   */
  event_id?: string | null;
}

export interface AgentResponseResult {
  response: string;
}

export type ConversationEvent = Event;
export type ConversationEventPage = EventPage;
