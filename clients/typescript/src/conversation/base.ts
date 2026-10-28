/**
 * 基础对话接口和类型
 *
 * 该文件定义了所有对话实现必须遵循的抽象接口。
 * 它反映了 Python SDK 的 BaseConversation 模式。
 */

import {
  ConversationID,
  Message,
  ConversationCallbackType,
  ConfirmationPolicyBase,
  ConversationStats,
  AgentBase,
  SecretValue,
} from '../types/base';
import { IWorkspace } from '../workspace/base';

/**
 * 所有对话类型共享的基本对话选项
 */
export interface BaseConversationOptions {
  /** 要恢复的可选现有对话 ID*/
  conversationId?: string;
  /** 回调对话事件函数*/
  callback?: ConversationCallbackType;
  /** 开始对话时发送的初始消息*/
  initialMessage?: string;
  /** 停止前的最大迭代次数（默认值：500）*/
  maxIterations?: number;
  /** 启用卡住检测（默认值：True）*/
  stuckDetection?: boolean;
}

/**
 * 事件列表界面。
 * 提供对对话事件的访问。
 */
export interface IEventsList {
  /** 将事件添加到列表中*/
  addEvent(event: unknown): Promise<void>;
  /** 获取所有事件（实现中可能有附加参数）*/
  getEvents?(): Promise<unknown[]>;
}

/**
 * 对话状态对象的接口。
 * 提供对对话事件和执行状态的访问。
 *
 * 注意：这是一个最小的界面。 具体实现(RemoteState,LocalState)
 * 可能有额外的方法和属性。
 */
export interface IConversationState {
  /** 对话ID*/
  readonly id: ConversationID;
  /** 访问事件列表*/
  readonly events: IEventsList;
}

/**
 * 用于对话实现的抽象接口。
 *
 * 对话管理用户和智能体之间的交互，处理消息
 * 交换、执行控制和状态管理。 所有对话实现
 * 支持相同的接口以实现互操作。
 *
 * 这反映了 Python SDK 的 BaseConversation 抽象类。
 */
export interface IConversation {
  /** 对话中运行的智能体*/
  readonly agent: AgentBase;
  /** 智能体操作的工作区*/
  readonly workspace: IWorkspace;
  /** 对话 ID（在 start() 之后可用）*/
  readonly id: ConversationID;
  /** 访问对话状态*/
  readonly state: IConversationState;

  /**
   * 开始或恢复对话。
   *
   * @param options - 启动选项，包括初始消息
   */
  start(options?: {
    initialMessage?: string;
    maxIterations?: number;
    stuckDetection?: boolean;
  }): Promise<void>;

  /**
   * 获取对话统计数据。
   *
   * @returns ConversationStats 以及迭代计数和其他指标
   */
  conversationStats(): Promise<ConversationStats>;

  /**
   * 发送消息至智能体。
   *
   * @param message - 一个字符串（将被转换为用户消息）
   *                  或消息对象
   */
  sendMessage(message: string | Message): Promise<void>;

  /**
   * 执行智能体来处理消息并执行操作。
   *
   * 该方法运行智能体直到处理完当前的
   * 消息或达到最大迭代限制。
   */
  run(): Promise<void>;

  /**
   * 暂停智能体执行。
   */
  pause(): Promise<void>;

  /**
   * 设置对话的确认策略。
   *
   * @param policy - 要应用的确认策略
   */
  setConfirmationPolicy(policy: ConfirmationPolicyBase): Promise<void>;

  /**
   * 发送确认响应（接受或拒绝待处理的操作）。
   *
   * @param Accept - 是否接受待处理的操作
   * @param Reason - 决定的可选原因
   */
  sendConfirmationResponse(accept: boolean, reason?: string): Promise<void>;

  /**
   * 设置对话的标题。
   *
   * @param title - 要设置的标题
   */
  setTitle(title: string): Promise<void>;

  /**
   * 更新机密可用于智能体。
   *
   * @param 机密 - 机密名称到值映射的记录
   */
  updateSecrets(secrets: Record<string, SecretValue>): Promise<void>;

  /**
   * 启动 WebSocket 客户端以获取实时事件流式传输。
   */
  startWebSocketClient(): Promise<void>;

  /**
   * 停止 WebSocket 客户端。
   */
  stopWebSocketClient(): Promise<void>;

  /**
   * 关闭对话并清理资源。
   */
  close(): Promise<void>;
}

/**
 * 对话类型的类型鉴别器。
 * 对于运行时类型检查和工厂模式很有用。
 */
export type ConversationType = 'local' | 'remote';
