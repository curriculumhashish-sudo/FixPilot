/**
 * 丰富的对话事件类型
 *
 * 这些事件类型反映了 Python SDK 的事件系统，提供
 * 所有对话活动的结构化事件。
 */

import type {
  AcpToolCallEvent as AgentServerAcpToolCallEvent,
  ActionEvent as AgentServerActionEvent,
  AgentErrorEvent as AgentServerAgentErrorEvent,
  Condensation as AgentServerCondensationEvent,
  CondensationRequest as AgentServerCondensationRequestEvent,
  CondensationSummaryEvent as AgentServerCondensationSummaryEvent,
  ConversationErrorEvent as AgentServerConversationErrorEvent,
  ConversationStateUpdateEvent as AgentServerConversationStateUpdateEvent,
  ErrorClassification as AgentServerErrorClassification,
  Event as AgentServerEvent,
  HookExecutionEvent as AgentServerHookExecutionEvent,
  LlmCompletionLogEvent as AgentServerLlmCompletionLogEvent,
  MessageEvent as AgentServerMessageEvent,
  MessageToolCall as AgentServerMessageToolCall,
  ObservationEvent as AgentServerObservationEvent,
  PauseEvent as AgentServerPauseEvent,
  SecurityRisk as AgentServerSecurityRisk,
  StreamingDeltaEvent as AgentServerStreamingDeltaEvent,
  SystemPromptEvent as AgentServerSystemPromptEvent,
  TokenEvent as AgentServerTokenEvent,
  ToolDefinition as AgentServerToolDefinition,
  UserRejectObservation as AgentServerUserRejectObservation,
} from '../generated/agent-server-schema';

export type ACPToolCallEvent = AgentServerAcpToolCallEvent;
export type ACPToolCallStatus = NonNullable<ACPToolCallEvent['status']>;
export type ACPToolKind = NonNullable<ACPToolCallEvent['tool_kind']>;
/**
 * 本地对话实现将工具输入表示为不透明的JSON。
 * 在采购所有其他 ActionEvent 字段的同时保持客户端便利
 * 来自Agent Server模式。
 */
export type ActionEvent = Omit<
  AgentServerActionEvent,
  'action' | 'llm_response_id' | 'thought' | 'tool_call'
> & {
  action: Record<string, unknown> | null;
  llm_response_id?: EventID;
  thought?: AgentServerActionEvent['thought'] | string;
  tool_call?: AgentServerMessageToolCall;
};
export type AgentErrorEvent = AgentServerAgentErrorEvent;
export type CondensationEvent = AgentServerCondensationEvent;
export type CondensationRequestEvent = AgentServerCondensationRequestEvent;
export type CondensationSummaryEvent = AgentServerCondensationSummaryEvent;
export type ConversationErrorEvent = Omit<AgentServerConversationErrorEvent, 'source'> & {
  source?: EventSource;
};
export type ConversationStateUpdateEvent = AgentServerConversationStateUpdateEvent;
export type ErrorClassification = AgentServerErrorClassification;
export type HookExecutionEvent = AgentServerHookExecutionEvent;
export type HookExecutionEventType = NonNullable<HookExecutionEvent['hook_event_type']>;
export type LLMCompletionLogEvent = AgentServerLlmCompletionLogEvent;
export type MessageEvent = AgentServerMessageEvent;
export type MessageToolCall = AgentServerMessageToolCall;
/** 本地对话将工具观测结果公开为不透明的 JSON 值。*/
export type ObservationEvent = Omit<AgentServerObservationEvent, 'observation'> & {
  observation: unknown;
};
export type PauseEvent = AgentServerPauseEvent;
export type SecurityRisk = AgentServerSecurityRisk;
export type StreamingDeltaEvent = AgentServerStreamingDeltaEvent;
export type SystemPromptEvent = AgentServerSystemPromptEvent;
export type TokenEvent = AgentServerTokenEvent;
export type ToolDefinition = AgentServerToolDefinition;
export type UserRejectObservation = AgentServerUserRejectObservation;

/**
 * 事件 ID 类型 - 事件的唯一标识符
 */
export type EventID = string;

/**
 * 事件源
 */
export type EventSource = 'agent' | 'user' | 'environment' | 'system' | 'hook';

/**
 * 所有丰富对话事件的基本界面。
 * 从 types/base.ts 扩展最小事件接口。
 */
export interface BaseEvent {
  /** 唯一的事件标识符*/
  id?: EventID;
  /** 事件类型/种类鉴别器*/
  kind: string;
  /** ISO 事件创建时的时间戳*/
  timestamp?: string;
  /** 事件来源*/
  source?: EventSource;
  parent_id?: EventID | null;
}

/**
 * 确认请求事件 - 等待用户确认的操作
 */
export interface ConfirmationRequestEvent extends BaseEvent {
  kind: 'ConfirmationRequestEvent';
  /** 等待确认的操作 ID*/
  action_id: string;
  /** 动作细节*/
  action: ActionEvent;
  /** 行动的风险级别*/
  risk_level?: 'low' | 'medium' | 'high' | 'unknown';
  /** 风险评估详情*/
  risk_assessment?: string;
}

/**
 * 确认响应事件——用户对确认请求的响应
 */
export interface ConfirmationResponseEvent extends BaseEvent {
  kind: 'ConfirmationResponseEvent';
  /** 正在响应的操作 ID*/
  action_id: string;
  /** 行动是否被接受*/
  accepted: boolean;
  /** 用户做出决定的原因*/
  reason?: string;
}

/**
 * 卡住检测事件 - 智能体检测为卡住
 */
export interface StuckDetectionEvent extends BaseEvent {
  kind: 'StuckDetectionEvent';
  /** 检测到的卡住图案类型*/
  pattern:
    | 'action_observation_loop'
    | 'action_error_loop'
    | 'monologue'
    | 'alternating_pattern'
    | 'context_window_error';
  /** 检测到的重复次数*/
  repetitions: number;
  /** 停滞状态描述*/
  description: string;
}

/**
 * 完成事件 - 智能体完成任务
 */
export interface FinishEvent extends BaseEvent {
  kind: 'FinishEvent';
  /** 来自智能体的最终消息*/
  message: string;
  /** 任务是否顺利完成*/
  success?: boolean;
}

/**
 * 思考事件 - 智能体的内部推理
 */
export interface ThinkEvent extends BaseEvent {
  kind: 'ThinkEvent';
  /** 思想内容*/
  thought: string;
}

/**
 * 所有对话事件的联合类型
 */
export type ConversationEvent =
  | AgentServerEvent
  | ConfirmationRequestEvent
  | ConfirmationResponseEvent
  | StuckDetectionEvent
  | FinishEvent
  | ThinkEvent;

/**
 * 输入 Guard 来检查事件是否为 MessageEvent
 */
export function isMessageEvent(event: BaseEvent): event is MessageEvent {
  return event.kind === 'MessageEvent';
}

/**
 * 输入 Guard 来检查事件是否为 ActionEvent
 */
export function isActionEvent(event: BaseEvent): event is ActionEvent {
  return event.kind === 'ActionEvent';
}

/**
 * 输入 Guard 来检查事件是否为 ObservationEvent
 */
export function isObservationEvent(event: BaseEvent): event is ObservationEvent {
  return event.kind === 'ObservationEvent';
}

/**
 * 输入 Guard 来检查事件是否为 AgentErrorEvent
 */
export function isAgentErrorEvent(event: BaseEvent): event is AgentErrorEvent {
  return event.kind === 'AgentErrorEvent';
}

/**
 * 输入 Guard 以检查事件是否类似于观测结果（具有 action_id）
 */
export function isObservationLike(
  event: BaseEvent
): event is ObservationEvent | AgentErrorEvent | UserRejectObservation {
  return (
    event.kind === 'ObservationEvent' ||
    event.kind === 'AgentErrorEvent' ||
    event.kind === 'UserRejectObservation'
  );
}

/**
 * 输入 Guard 来检查事件是否为 ConversationErrorEvent
 */
export function isConversationErrorEvent(event: BaseEvent): event is ConversationErrorEvent {
  return event.kind === 'ConversationErrorEvent';
}

/**
 * 输入 Guard 来检查事件是否为 CondensationEvent
 */
export function isCondensationEvent(event: BaseEvent): event is CondensationEvent {
  return event.kind === 'Condensation';
}

/**
 * 输入 Guard 来检查事件是否为 HookExecutionEvent
 */
export function isHookExecutionEvent(event: BaseEvent): event is HookExecutionEvent {
  return event.kind === 'HookExecutionEvent';
}

/**
 * 生成唯一的事件 ID
 */
export function generateEventId(): EventID {
  return `evt_${Date.now()}_${crypto.randomUUID().substring(0, 8)}`;
}

/**
 * 创建具有公共字段的基本事件
 */
export function createBaseEvent(kind: string, source?: EventSource): BaseEvent {
  return {
    id: generateEventId(),
    kind,
    timestamp: new Date().toISOString(),
    source,
  };
}
