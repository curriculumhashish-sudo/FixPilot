import { HttpClient, HttpError } from './http-client';
import { getCachedAgentServerInfo } from './agent-server-compatibility';
import { ConversationExecutionStatus, LLM, Success } from '../types/base';
import type {
  AgentResponseResult,
  AskAgentResponse,
  ConfirmationResponseRequest,
  ConversationEvent,
  ConversationEventCountOptions,
  ConversationEventPage,
  ConversationEventSearchOptions,
  ConversationInfo,
  ConversationRuntimeInfo,
  ConversationSearchRequest,
  ConversationSearchResponse,
  ForkConversationRequest,
  NavigateConversationRequest,
  SetConfirmationPolicyRequest,
  SetSecurityAnalyzerRequest,
  StartGoalRequest,
  UpdateConversationRequest,
  UpdateSecretsRequest,
} from '../models/conversation';
import type { ConfirmationPolicyBase } from '../types/base';

export interface ConversationClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

/**
 * 载荷用于创建新对话。
 *
 * 智能体的互斥来源：
 * - `agent_profile_id` — 稳定 UUID； 服务器在服务器端解析配置文件。
 * - `agent` / `agent_settings` — 直接智能体规范（旧路径）。
 *
 * 附加字段 (e.g. `initial_message`、`max_iterations`) 已转发
 * 按原样。 `agent_profile_id` 支持土地 SDK PR #3784。
 */
export interface CreateConversationPayload {
  /** 用于解析服务器端的智能体配置文件的稳定 UUID。*/
  agent_profile_id?: string;
  agent?: unknown;
  agent_settings?: unknown;
  [key: string]: unknown;
}

export interface SendConversationEventOptions {
  run?: boolean;
}

export class ConversationClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: ConversationClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout || 60000,
    });
  }

  async createConversation<TConversation = ConversationInfo>(
    payload: CreateConversationPayload
  ): Promise<TConversation> {
    try {
      const response = await this.client.post<TConversation>('/api/conversations', payload);
      return response.data;
    } catch (error) {
      // 丢失响应并不意味着创建没有被应用：服务器可能已经提交了它并且初始消息可能已经在运行。 仅当服务器为一个 ID 创建的重复数据删除并发时，重新发送才是安全的，并将其宣传为一种功能。 没有供调用者提供的标识符来匹配，即使有，没有该能力的服务器也会在重发时双倍创建，因此，应表面原始错误传输层。
      //
      if (
        error instanceof HttpError ||
        typeof payload.conversation_id !== 'string' ||
        !(await this.supportsCreateRetry())
      ) {
        throw error;
      }

      const response = await this.client.post<TConversation>('/api/conversations', payload);
      return response.data;
    }
  }

  /**
   * 服务器是否对并发为一个会话 ID 创建的重复数据进行删除。
   *
   * 无法探测到的服务器被视为不受支持，因此较旧的或
   * 无法访问的后端会保留之前的行为，而不是冒着
   * 重复的对话。
   */
  private async supportsCreateRetry(): Promise<boolean> {
    try {
      const serverInfo = await getCachedAgentServerInfo(this.client);
      return serverInfo.capabilities?.includes('idempotent_conversation_create_v1') === true;
    } catch {
      return false;
    }
  }

  async searchConversations(
    options: ConversationSearchRequest = {}
  ): Promise<ConversationSearchResponse> {
    const response = await this.client.get<ConversationSearchResponse>(
      '/api/conversations/search',
      {
        params: options as Record<string, unknown>,
      }
    );
    return response.data;
  }

  async countConversations(
    options: { status?: ConversationExecutionStatus } = {}
  ): Promise<number> {
    const response = await this.client.get<number>('/api/conversations/count', {
      params: options as Record<string, unknown>,
    });
    return response.data;
  }

  async getConversations<TConversation = ConversationInfo>(
    conversationIds: string[]
  ): Promise<Array<TConversation | null>> {
    const response = await this.client.get<Array<TConversation | null>>('/api/conversations', {
      params: { ids: conversationIds },
    });
    return response.data;
  }

  async getConversation<TConversation = ConversationInfo>(
    conversationId: string
  ): Promise<TConversation> {
    const response = await this.client.get<TConversation>(`/api/conversations/${conversationId}`);
    return response.data;
  }

  async getRuntime(conversationId: string): Promise<ConversationRuntimeInfo> {
    const response = await this.client.get<ConversationRuntimeInfo>(
      `/api/conversations/${conversationId}/runtime`
    );
    return response.data;
  }

  async reprovisionRuntime(conversationId: string): Promise<ConversationRuntimeInfo> {
    const response = await this.client.post<ConversationRuntimeInfo>(
      `/api/conversations/${conversationId}/runtime/reprovision`,
      {}
    );
    return response.data;
  }

  async searchEvents(
    conversationId: string,
    options: ConversationEventSearchOptions = {}
  ): Promise<ConversationEventPage> {
    const response = await this.client.get<ConversationEventPage>(
      `/api/conversations/${conversationId}/events/search`,
      { params: options as Record<string, unknown> }
    );
    return response.data;
  }

  async getEvent(conversationId: string, eventId: string): Promise<ConversationEvent> {
    const response = await this.client.get<ConversationEvent>(
      `/api/conversations/${conversationId}/events/${eventId}`
    );
    return response.data;
  }

  async getEvents(
    conversationId: string,
    eventIds: string[]
  ): Promise<Array<ConversationEvent | null>> {
    return Promise.all(
      eventIds.map(async (eventId) => {
        try {
          return await this.getEvent(conversationId, eventId);
        } catch (error) {
          if (error instanceof HttpError && error.status === 404) {
            return null;
          }
          throw error;
        }
      })
    );
  }

  async sendEvent(
    conversationId: string,
    event: object,
    options: SendConversationEventOptions = {}
  ): Promise<void> {
    await this.client.post(`/api/conversations/${conversationId}/events`, {
      ...event,
      ...(options.run === undefined ? {} : { run: options.run }),
    });
  }

  async pauseConversation(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/pause`,
      {}
    );
    return response.data;
  }

  async interruptConversation(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/interrupt`,
      {}
    );
    return response.data;
  }

  async runConversation(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/run`,
      {}
    );
    return response.data;
  }

  /**
   * 在现有对话中启动 `/goal` 循环。 循环运行在
   * 对话自己的历史记录和事件流（它不会分叉）。 服务器
   * 如果运行或目标循环已处于活动状态，则返回 409；如果运行或目标循环无效，则返回 400
   * 目标（e.g. 空）； 缺少对话会产生 404。
   */
  async startGoal(conversationId: string, request: StartGoalRequest): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/goal`,
      request
    );
    return response.data;
  }

  /**
   * 停止此对话中的活动 `/goal` 循环。 仅取消
   * 后台目标循环（不是对话）并记录 `interrupted`
   * 状态，以便 {@link resumeGoal} 可以继续。 即使没有循环也会成功
   * 跑步； 缺少对话会产生 404。
   */
  async stopGoal(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/goal/stop`,
      {}
    );
    return response.data;
  }

  /**
   * 恢复此对话中最后一个中断的 `/goal` 循环。 服务器
   * 如果运行或目标循环已处于活动状态，则返回 409；如果存在，则返回 400
   * 没有可恢复的目标（None已开始，或已完成）； 失踪的
   * 对话结果为 404。
   */
  async resumeGoal(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/goal/resume`,
      {}
    );
    return response.data;
  }

  async askAgent(conversationId: string, question: string): Promise<AskAgentResponse> {
    const response = await this.client.post<AskAgentResponse>(
      `/api/conversations/${conversationId}/ask_agent`,
      { question }
    );
    return response.data;
  }

  async getEventCount(
    conversationId: string,
    options: ConversationEventCountOptions = {}
  ): Promise<number> {
    const response = await this.client.get<number>(
      `/api/conversations/${conversationId}/events/count`,
      { params: options as Record<string, unknown> }
    );
    return response.data;
  }

  async respondToConfirmation<TResponse = unknown>(
    conversationId: string,
    request: ConfirmationResponseRequest
  ): Promise<TResponse> {
    const response = await this.client.post<TResponse>(
      `/api/conversations/${conversationId}/events/respond_to_confirmation`,
      request
    );
    return response.data;
  }

  async getAgentFinalResponse(conversationId: string): Promise<AgentResponseResult> {
    const response = await this.client.get<AgentResponseResult>(
      `/api/conversations/${conversationId}/agent_final_response`
    );
    return response.data;
  }

  async setConfirmationPolicy(
    conversationId: string,
    policyOrRequest: ConfirmationPolicyBase | SetConfirmationPolicyRequest
  ): Promise<Success> {
    const request =
      'policy' in policyOrRequest ? policyOrRequest : ({ policy: policyOrRequest } as const);
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/confirmation_policy`,
      request
    );
    return response.data;
  }

  async condenseConversation(conversationId: string): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/condense`,
      {}
    );
    return response.data;
  }

  async setSecurityAnalyzer(
    conversationId: string,
    securityAnalyzerOrRequest: unknown | SetSecurityAnalyzerRequest | null
  ): Promise<Success> {
    const request = isSetSecurityAnalyzerRequest(securityAnalyzerOrRequest)
      ? securityAnalyzerOrRequest
      : { security_analyzer: securityAnalyzerOrRequest };
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/security_analyzer`,
      request
    );
    return response.data;
  }

  async updateSecrets(conversationId: string, request: UpdateSecretsRequest): Promise<Success> {
    const response = await this.client.post<Success>(
      `/api/conversations/${conversationId}/secrets`,
      request
    );
    return response.data;
  }

  async forkConversation<TConversation = ConversationInfo>(
    conversationId: string,
    request: ForkConversationRequest = {},
    options: { includeSkills?: boolean } = {}
  ): Promise<TConversation> {
    const response = await this.client.post<TConversation>(
      `/api/conversations/${conversationId}/fork`,
      request,
      {
        params:
          options.includeSkills === undefined
            ? undefined
            : { include_skills: options.includeSkills },
      }
    );
    return response.data;
  }

  /**
   * 将对话的 HEAD 移至现有事件，重新确定活动根
   * 智能体的分支将在下一个运行。 与 {@link forkConversation} 不同，这
   * 不创建新的对话——所有分支都保留在磁盘上。 通行证
   * `{ event_id: null }`（或空请求）选择空树。
   *
   * 返回更新后的{@linkConversationInfo}，携带新的
   * `leaf_event_id`. 服务器针对未知对话或错误应答 404
   * 未知`event_id`。
   */
  async navigateConversation<TConversation = ConversationInfo>(
    conversationId: string,
    request: NavigateConversationRequest = {},
    options: { includeSkills?: boolean } = {}
  ): Promise<TConversation> {
    const response = await this.client.post<TConversation>(
      `/api/conversations/${conversationId}/navigate`,
      request,
      {
        params:
          options.includeSkills === undefined
            ? undefined
            : { include_skills: options.includeSkills },
      }
    );
    return response.data;
  }

  async switchProfile(conversationId: string, profileName: string): Promise<void> {
    await this.client.post<Success>(`/api/conversations/${conversationId}/switch_profile`, {
      profile_name: profileName,
    });
  }

  async switchLLM(conversationId: string, llm: LLM): Promise<void> {
    await this.client.post<Success>(`/api/conversations/${conversationId}/switch_llm`, { llm });
  }

  /**
   * 切换 ACP 对话的模型（ACP 模拟
   * {@链接switchLLM}）。 在实时会话中，服务器调用包装器
   * `session/set_model`到位； 上下文被保留。 第一次运行之前
   * 还没有会话，因此服务器回答 200 并存储模型
   * 第一次会话。 非 ACP 对话得到 400。
   */
  async switchAcpModel(conversationId: string, model: string): Promise<void> {
    await this.client.post<Success>(`/api/conversations/${conversationId}/switch_acp_model`, {
      model,
    });
  }

  async deleteConversation(conversationId: string): Promise<void> {
    await this.client.delete<Success>(`/api/conversations/${conversationId}`);
  }

  /**
   * 更新对话元数据 (e.g. 标题）并用更新后的解决
   * 谈话。 PATCH 端点只回答 `Success`，所以
   * 更新后会回读对话。
   */
  async updateConversation<TConversation = ConversationInfo>(
    conversationId: string,
    update: UpdateConversationRequest
  ): Promise<TConversation> {
    await this.client.patch<Success>(`/api/conversations/${conversationId}`, update);
    return this.getConversation<TConversation>(conversationId);
  }

  close(): void {
    this.client.close();
  }
}

function isSetSecurityAnalyzerRequest(value: unknown): value is SetSecurityAnalyzerRequest {
  return typeof value === 'object' && value !== null && 'security_analyzer' in value;
}
