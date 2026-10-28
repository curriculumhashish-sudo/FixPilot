/**
 * 会话工厂和实用函数
 *
 * 该模块提供了一个方便的工厂模式来创建对话实例。
 * 它匹配 Python SDK 模式，同时支持本地和远程对话。
 */

import { AgentBase } from '../types/base';
import { IWorkspace } from '../workspace/base';
import { RemoteWorkspace } from '../workspace/remote-workspace';
import { LocalWorkspace } from '../workspace/local-workspace';
import { RemoteConversation, RemoteConversationOptions } from './remote-conversation';
import { LocalConversation, LocalConversationOptions } from './local-conversation';
import { IConversation, ConversationType } from './base';

/**
 * 所有对话选项的联合类型
 */
export type ConversationOptions = RemoteConversationOptions | LocalConversationOptions;

/**
 * 用于通过显式类型选择创建对话的选项
 */
export interface CreateConversationOptions {
  type: ConversationType;
  agent: AgentBase;
  workspace: IWorkspace;
  options?: ConversationOptions;
}

/**
 * 将 RemoteConversation 扩展为向后兼容性的会话类。
 * 提供与 Python SDK 命名相匹配的更清晰的 API。
 *
 * 对于新代码，请考虑使用 createConversation 工厂函数
 * 或者直接实例化 RemoteConversation 或 LocalConversation。
 *
 * 用途：
 * ```TypeScript
 * // 传统用法（向后兼容）
 * const 对话 = new Conversation(agent, workspace);
 * 等待conversation.start();
 *
 * // 对于现有对话：
 * const 对话 = new Conversation(agent, workspace, { conversationId: 'existing-id' });
 * 等待conversation.start();
 * ```
 */
export class Conversation extends RemoteConversation {
  constructor(agent: AgentBase, workspace: RemoteWorkspace, options?: RemoteConversationOptions) {
    super(agent, workspace, options);
  }
}

/**
 * 工厂函数用于根据选项创建对话实例。
 *
 * 这提供了一种创建本地或远程对话的统一方法
 * 基于提供的选项。
 *
 * 用途：
 * ```TypeScript
 * // 创建远程对话
 * const remoteConversation = createConversation({
 *   类型：'远程'，
 *   智能体：myAgent,
 *   工作区：remoteWorkspace,
 *   选项：{ 回调：(事件) => console.log(事件) }
 * });
 *
 * // 创建本地对话
 * const localConversation = createConversation({
 *   类型：'本地'，
 *   智能体：myAgent,
 *   工作区：localWorkspace,
 *   选项：{persistenceDir：'/path/to/persistence'}
 * });
 * ```
 *
 * @param config - 对话配置，包括类型、智能体、工作区和选项
 * @returns 实现 IConversation 的对话实例
 */
export function createConversation(config: CreateConversationOptions): IConversation {
  switch (config.type) {
    case 'remote':
      if (!(config.workspace instanceof RemoteWorkspace)) {
        throw new Error('Remote conversation requires RemoteWorkspace');
      }
      return new RemoteConversation(
        config.agent,
        config.workspace,
        config.options as RemoteConversationOptions
      );

    case 'local':
      return new LocalConversation(
        config.agent,
        config.workspace,
        config.options as LocalConversationOptions
      );

    default:
      throw new Error(`Unknown conversation type: ${config.type}`);
  }
}

/**
 * 创建一个对话，自动检测工作区中的类型。
 *
 * 如果工作区是 RemoteWorkspace，则创建 RemoteConversation。
 * 如果工作区是 LocalWorkspace，则创建 LocalConversation。
 *
 * 用途：
 * ```TypeScript
 * // 自动创建 RemoteConversation
 * const remote = createConversationAuto(智能体，remoteWorkspace);
 *
 * // 自动创建 LocalConversation
 * 常量本地 = createConversationAuto(智能体，localWorkspace);
 * ```
 *
 * @param 智能体 - 用于对话的智能体
 * @param 工作区 - 工作区（确定对话类型）
 * @param options - 可选的对话配置
 * @returns 实现 IConversation 的对话实例
 */
export function createConversationAuto(
  agent: AgentBase,
  workspace: IWorkspace,
  options?: ConversationOptions
): IConversation {
  if (workspace instanceof RemoteWorkspace) {
    return new RemoteConversation(agent, workspace, options as RemoteConversationOptions);
  }
  if (workspace instanceof LocalWorkspace) {
    return new LocalConversation(agent, workspace, options as LocalConversationOptions);
  }
  throw new Error('Workspace must be either RemoteWorkspace or LocalWorkspace');
}
