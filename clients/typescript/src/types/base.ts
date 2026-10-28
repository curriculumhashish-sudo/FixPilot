/**
 * OpenHands Agent Server TypeScript 客户端的基本类型和接口
 */

export type ConversationID = string;

/**
 * 与智能体-服务器有线格式匹配的基本事件接口。
 * 对于丰富的类型化事件，请使用 events/types.ts 中的特定类型
 * (e.g., ActionEvent, ObservationEvent, ConversationEvent).
 */
export interface Event {
  id: string;
  kind: string;
  timestamp: string;
  source?: 'agent' | 'user' | 'environment' | 'system' | 'hook';
}

export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: MessageContent[];
}

export interface MessageContent {
  type: 'text' | 'image';
  text?: string;
  image_urls?: string[];
}

export interface TextContent extends MessageContent {
  type: 'text';
  text: string;
}

export interface ImageContent extends MessageContent {
  type: 'image';
  image_urls: string[];
}

export interface AgentContext {
  skills?: unknown[];
  system_message_suffix?: string | null;
  user_message_suffix?: string | null;
  load_project_skills?: boolean;
  [key: string]: unknown;
}

export interface AgentBase {
  kind: string;
  llm: LLM;
  agent_context?: AgentContext | null;
  name?: string;
  [key: string]: unknown;
}

// 面向用户的别名 API
export type Agent = AgentBase;

export interface LLM {
  model: string;
  api_key?: string;
  base_url?: string;
  [key: string]: unknown;
}

export interface ServerInfo {
  uptime: number;
  idle_time: number;
  title?: string;
  version: string;
  sdk_version?: string;
  tools_version?: string;
  workspace_version?: string;
  build_git_sha?: string;
  build_git_date?: string;
  build_semver?: string;
  capabilities?: string[];
  conversation_runtime?: 'local' | 'docker';
  app_backend_ingress_url?: string | null;
  [key: string]: unknown;
}

export interface Success {
  success: boolean;
  message?: string;
}

export interface EventPage {
  items: Event[];
  next_page_id?: string;
  total_count?: number;
}

export enum EventSortOrder {
  TIMESTAMP = 'TIMESTAMP',
  TIMESTAMP_DESC = 'TIMESTAMP_DESC',
}

// eslint-disable-next-line @typescript-eslint/no-namespace
export namespace EventSortOrder {
  /** @deprecated Use TIMESTAMP_DESC instead. */
  export const REVERSE_TIMESTAMP: EventSortOrder = 'TIMESTAMP_DESC' as EventSortOrder;
}

/**
 * 枚举代表会话当前的执行状态。
 * 注意：已从 AgentExecutionStatus 重命名为 ConversationExecutionStatus
 * 在智能体-服务器API中。
 */
export enum ConversationExecutionStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  PAUSED = 'paused',
  WAITING_FOR_CONFIRMATION = 'waiting_for_confirmation',
  FINISHED = 'finished',
  ERROR = 'error',
  STUCK = 'stuck',
  DELETING = 'deleting',
}

/**
 * @已弃用使用 ConversationExecutionStatus 代替。 该别名保留为向后兼容性。
 */
export const AgentExecutionStatus = ConversationExecutionStatus;
export type AgentExecutionStatus = ConversationExecutionStatus;

export interface ConversationStats {
  total_events: number;
  message_events: number;
  action_events: number;
  observation_events: number;
  [key: string]: unknown;
}

export interface ConfirmationPolicyBase {
  kind?: string;
  type?: string;
  [key: string]: unknown;
}

export interface NeverConfirm extends ConfirmationPolicyBase {
  type: 'never';
}

export interface AlwaysConfirm extends ConfirmationPolicyBase {
  type: 'always';
}

export type ConversationCallbackType = (event: Event) => void;

export type SecretValue = string | (() => string);
