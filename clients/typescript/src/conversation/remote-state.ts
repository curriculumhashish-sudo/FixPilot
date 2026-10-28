/**
 * 远程会话状态管理
 */

import { HttpClient } from '../client/http-client';
import { RemoteEventsList } from '../events/remote-events-list';
import {
  ConversationID,
  Event,
  ConversationExecutionStatus,
  AgentExecutionStatus,
  ConfirmationPolicyBase,
  // ConversationStats, // 暂时未使用
  AgentBase,
  ConversationCallbackType,
} from '../types/base';
import { ConversationInfo } from '../models/conversation';

const FULL_STATE_KEY = '__full_state__';

export interface ConversationStateUpdateEvent extends Event {
  kind: 'ConversationStateUpdateEvent';
  key: string;
  value: unknown;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export class RemoteState {
  private client: HttpClient;
  private conversationId: string;
  private _events: RemoteEventsList;
  private cachedState: ConversationInfo | null = null;
  private cachedAt = 0;
  private lock = new AsyncLock();

  /** 以毫秒为单位缓存 TTL。 早于此的缓存状态会触发重新获取。*/
  static CACHE_TTL_MS = 2000;

  constructor(client: HttpClient, conversationId: string) {
    this.client = client;
    this.conversationId = conversationId;
    this._events = new RemoteEventsList(client, conversationId);
  }

  private async getConversationInfo(): Promise<ConversationInfo> {
    return await this.lock.acquire(async () => {
      // 返回缓存状态（如果可用且新鲜）。 缓存可以通过仍然携带`full_state`包装的州更新事件来填充，所以在这里也要规范化——这是唯一的解包点。
      //
      if (this.cachedState !== null && Date.now() - this.cachedAt < RemoteState.CACHE_TTL_MS) {
        return this.normalizeFullState(this.cachedState);
      }

      // 从 REST API 获取并对 `full_state` 包装器进行一次标准化。
      const response = await this.client.get<ConversationInfo>(
        `/api/conversations/${this.conversationId}`
      );
      const conversationInfo = this.normalizeFullState(response.data);

      this.cachedState = conversationInfo;
      this.cachedAt = Date.now();
      return conversationInfo;
    });
  }

  /**
   * 打开 API 的 `full_state` 包装器，以便每个访问器都收到一个平面
   * ConversationInfo. 将其集中在这里意味着访问者永远不必
   * 解开自己的包裹。
   */
  private normalizeFullState(info: ConversationInfo): ConversationInfo {
    const wrapped = info as ConversationInfo & { full_state?: ConversationInfo };
    return wrapped.full_state ?? info;
  }

  /**
   * 强制从服务器重新获取，忽略缓存。
   */
  async refresh(): Promise<ConversationInfo> {
    this.cachedState = null;
    return this.getConversationInfo();
  }

  async updateStateFromEvent(event: ConversationStateUpdateEvent): Promise<void> {
    await this.lock.acquire(async () => {
      // 处理全状态快照
      if (event.key === FULL_STATE_KEY) {
        if (this.cachedState === null) {
          this.cachedState = {} as ConversationInfo;
        }
        const stateValue =
          isRecord(event.value) && isRecord(event.value.full_state)
            ? event.value.full_state
            : event.value;
        if (!isRecord(stateValue)) {
          throw new Error('Full conversation state update must contain an object value.');
        }
        Object.assign(this.cachedState, stateValue);
      } else {
        if (this.cachedState === null) {
          this.cachedState = {} as ConversationInfo;
        }
        (this.cachedState as Record<string, unknown>)[event.key] = event.value;
      }
      this.cachedAt = Date.now();
    });
  }

  createStateUpdateCallback(onError?: (error: Error) => void): ConversationCallbackType {
    return (event: Event) => {
      if (event.kind === 'ConversationStateUpdateEvent') {
        this.updateStateFromEvent(event as ConversationStateUpdateEvent).catch((error) => {
          if (onError) {
            onError(
              error instanceof Error
                ? error
                : new Error(`Error updating state from event: ${error}`)
            );
          }
        });
      }
    };
  }

  get events(): RemoteEventsList {
    return this._events;
  }

  get id(): ConversationID {
    return this.conversationId;
  }

  /**
   * 获取会话当前的执行状态。
   * 此方法处理新的 `execution_status` 字段和旧的 `agent_status` 字段。
   */
  async getExecutionStatus(): Promise<ConversationExecutionStatus> {
    const info = await this.getConversationInfo();
    // 先尝试新领域，再回到旧领域
    const statusStr = info.execution_status ?? info.agent_status;
    if (statusStr === undefined || statusStr === null) {
      throw new Error(`execution_status missing in conversation info: ${JSON.stringify(info)}`);
    }
    return statusStr;
  }

  /**
   * @已弃用使用 getExecutionStatus() 代替。 该方法被保留为向后兼容性。
   */
  async getAgentStatus(): Promise<AgentExecutionStatus> {
    return this.getExecutionStatus();
  }

  async setAgentStatus(value: AgentExecutionStatus): Promise<void> {
    throw new Error(
      `Setting execution_status on RemoteState has no effect. ` +
        `Remote execution status is managed server-side. Attempted to set: ${value}`
    );
  }

  async getConfirmationPolicy(): Promise<ConfirmationPolicyBase> {
    const info = await this.getConversationInfo();
    const policyData = info.confirmation_policy;
    if (policyData === undefined || policyData === null) {
      throw new Error(`confirmation_policy missing in conversation info: ${JSON.stringify(info)}`);
    }
    return policyData;
  }

  async getActivatedKnowledgeSkills(): Promise<string[]> {
    const info = await this.getConversationInfo();
    return info.activated_knowledge_skills || [];
  }

  async getAgent(): Promise<AgentBase> {
    const info = await this.getConversationInfo();
    const agentData = info.agent;
    if (agentData === undefined || agentData === null) {
      throw new Error(`agent missing in conversation info: ${JSON.stringify(info)}`);
    }
    return agentData;
  }

  async getWorkspace(): Promise<ConversationInfo['workspace']> {
    const info = await this.getConversationInfo();
    const workspace = info.workspace;
    if (workspace === undefined || workspace === null) {
      throw new Error(`workspace missing in conversation info: ${JSON.stringify(info)}`);
    }
    return workspace;
  }

  async getPersistenceDir(): Promise<string> {
    const info = await this.getConversationInfo();
    const persistenceDir = info.persistence_dir;
    if (persistenceDir === undefined || persistenceDir === null) {
      throw new Error(`persistence_dir missing in conversation info: ${JSON.stringify(info)}`);
    }
    return persistenceDir;
  }

  async modelDump(): Promise<Record<string, unknown>> {
    const info = await this.getConversationInfo();
    return info;
  }

  async modelDumpJson(): Promise<string> {
    const data = await this.modelDump();
    return JSON.stringify(data);
  }
}

// 简单的异步锁用于序列化状态访问
class AsyncLock {
  private locked = false;
  private queue: Array<() => void> = [];

  async acquire<T>(fn: () => Promise<T> | T): Promise<T> {
    return new Promise((resolve, reject) => {
      const execute = async () => {
        try {
          const result = await fn();
          resolve(result);
        } catch (error) {
          reject(error);
        } finally {
          this.locked = false;
          const next = this.queue.shift();
          if (next) {
            next();
          }
        }
      };

      if (this.locked) {
        this.queue.push(execute);
      } else {
        this.locked = true;
        execute();
      }
    });
  }
}
