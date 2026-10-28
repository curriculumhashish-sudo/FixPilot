/**
 * 远程对话实现
 *
 * 这通过连接到远程 OpenHands 来实现 IConversation 接口
 * Agent Server. 它反映了 Python SDK 的 RemoteConversation 类。
 */

import { HttpClient } from '../client/http-client';
import { WebSocketCallbackClient, ErrorCallbackType } from '../events/websocket-client';
import { RemoteState } from './remote-state';
import { RemoteWorkspace } from '../workspace/remote-workspace';
import {
  ConversationID,
  Message,
  ConversationCallbackType,
  ConfirmationPolicyBase,
  ConversationStats,
  AgentBase,
  SecretValue,
  LLM,
} from '../types/base';
import {
  ConversationInfo,
  SendMessageRequest,
  ConfirmationResponseRequest,
  CreateConversationRequest,
  UpdateConversationRequest,
  UpdateSecretsRequest,
  AskAgentRequest,
  AskAgentResponse,
  SetSecurityAnalyzerRequest,
  AgentResponseResult,
  ForkConversationRequest,
  NavigateConversationRequest,
  StartGoalRequest,
} from '../models/conversation';
import { IConversation, BaseConversationOptions } from './base';
import { Success } from '../types/base';
import type { HookConfig } from '../hooks';

/**
 * 用于创建 RemoteConversation 实例的选项。
 */
export interface RemoteConversationOptions extends BaseConversationOptions {
  /**
   * 与服务器端可观察性跟踪关联的可选用户 ID。
   */
  userId?: string;
  /**
   * 此对话的可选挂钩配置。
   * Hook 是在关键生命周期事件中在服务器端运行的 shell 脚本
   * （PreToolUse、PostToolUse、UserPromptSubmit、停止等）。
   */
  hookConfig?: HookConfig;
  /**
   * 可选错误回调用于非致命错误（WebSocket 问题、状态更新失败）。
   * 如果未提供，这些错误将被默默忽略。
   */
  onError?: ErrorCallbackType;
}

/**
 * 连接到 OpenHands Agent Server 的远程对话实现。
 *
 * RemoteConversation 提供对远程运行的对话的访问
 * OpenHands Agent Server. 这是生产部署的推荐方法
 * 因为它提供了更好的隔离和安全性。
 *
 * 示例：
 * ```TypeScript
 * 常量工作区 = 新 RemoteWorkspace({
 *   主持人：' https://agent-server.example.com',
 *   workingDir: '/workspace',
 *   apiKey: 'your-API-key'
 * });
 * const 对话 = new RemoteConversation(智能体，工作区，{
 *   回调：(事件) => console.log(事件)
 * });
 * 等待 conversation.start({ initialMessage: '你好！' });
 * 等待conversation.run();
 * 等待conversation.close();
 * ```
 */
export class RemoteConversation implements IConversation {
  public readonly agent: AgentBase;
  private _workspace: RemoteWorkspace;
  private _conversationId?: string;
  private _state?: RemoteState;
  private client: HttpClient;
  private wsClient?: WebSocketCallbackClient;
  private callback?: ConversationCallbackType;
  private onError?: ErrorCallbackType;
  private hookConfig?: HookConfig;
  private userId?: string;
  private maxIterations?: number;
  private stuckDetection?: boolean;

  constructor(
    agent: AgentBase,
    workspace: RemoteWorkspace,
    options: RemoteConversationOptions = {}
  ) {
    this.agent = agent;
    this._workspace = workspace;
    this.callback = options.callback;
    this.onError = options.onError;
    this._conversationId = options.conversationId;
    this.hookConfig = options.hookConfig;
    this.userId = options.userId;
    this.maxIterations = options.maxIterations;
    this.stuckDetection = options.stuckDetection;

    this.client = new HttpClient({
      baseUrl: workspace.host,
      apiKey: workspace.apiKey,
      timeout: 60000,
    });
  }

  get workspace(): RemoteWorkspace {
    return this._workspace;
  }

  get id(): ConversationID {
    if (!this._conversationId) {
      throw new Error('Conversation ID not set. Call start() to initialize the conversation.');
    }
    return this._conversationId;
  }

  get state(): RemoteState {
    if (!this._state) {
      if (!this._conversationId) {
        throw new Error(
          'Conversation not initialized. Call start() to initialize the conversation.'
        );
      }
      this._state = new RemoteState(this.client, this._conversationId);
    }
    return this._state;
  }

  async start(
    options: {
      initialMessage?: string;
      maxIterations?: number;
      stuckDetection?: boolean;
      hookConfig?: HookConfig;
      userId?: string;
    } = {}
  ): Promise<void> {
    if (this._conversationId) {
      // 现有对话 - 验证其存在并使用其实际的工作区。
      const { data } = await this.client.get<ConversationInfo>(
        `/api/conversations/${this._conversationId}`
      );
      this.bindConversationWorkspace(data);
      return;
    }

    // 创建新对话
    let initialMessage: Message | undefined;
    if (options.initialMessage) {
      initialMessage = {
        role: 'user',
        content: [{ type: 'text', text: options.initialMessage }],
      };
    }

    // 启动选项优先于构造函数选项
    const hookConfig = options.hookConfig ?? this.hookConfig ?? undefined;
    const userId = options.userId ?? this.userId ?? undefined;

    const request: CreateConversationRequest = {
      agent: this.agent,
      initial_message: initialMessage,
      max_iterations: options.maxIterations || this.maxIterations || 500,
      stuck_detection: options.stuckDetection ?? this.stuckDetection ?? true,
      workspace: { type: 'local', working_dir: this.workspace.workingDir },
      hook_config: hookConfig ?? null,
      user_id: userId ?? null,
    };

    const response = await this.client.post<ConversationInfo>('/api/conversations', request);
    const conversationInfo = response.data;
    this._conversationId = conversationInfo.id;
    this.bindConversationWorkspace(conversationInfo);
  }

  private getConversationWorkingDir(conversationInfo: ConversationInfo): string {
    const workspace = conversationInfo.workspace;
    return workspace &&
      typeof workspace === 'object' &&
      'working_dir' in workspace &&
      typeof workspace.working_dir === 'string'
      ? workspace.working_dir
      : this.workspace.workingDir;
  }

  private bindConversationWorkspace(conversationInfo: ConversationInfo): void {
    this._workspace = new RemoteWorkspace({
      host: this.workspace.host,
      workingDir: this.getConversationWorkingDir(conversationInfo),
      apiKey: this.workspace.apiKey,
      conversationId: conversationInfo.id,
    });
  }

  /**
   * 从服务器加载钩子配置工作区。
   *
   * 这会调用服务器的钩子端点来读取 `.openhands/hooks.json`
   * 从项目目录。
   *
   * @param projectDir - 可选的项目目录路径。 默认为工作区工作目录。
   * @returns 钩子配置，如果没有配置钩子则返回 null。
   */
  async loadHooks(projectDir?: string): Promise<HookConfig | null> {
    const response = await this.client.post<{ hook_config: HookConfig | null }>('/api/hooks', {
      project_dir: projectDir ?? this.workspace.workingDir,
    });
    return response.data.hook_config;
  }

  /**
   * 从服务器获取此对话的挂钩配置。
   *
   * 获取当前对话信息并返回hook_config字段。
   *
   * @returns 钩子配置，如果没有配置钩子则返回 null。
   */
  async getHookConfig(): Promise<HookConfig | null> {
    const response = await this.client.get<ConversationInfo>(`/api/conversations/${this.id}`);
    return response.data.hook_config ?? null;
  }

  async conversationStats(): Promise<ConversationStats> {
    const response = await this.client.get<ConversationInfo>(`/api/conversations/${this.id}`);
    const stats = response.data.stats ?? response.data.conversation_stats;
    if (!stats) {
      throw new Error('No conversation stats available');
    }
    return stats;
  }

  async sendMessage(message: string | Message): Promise<void> {
    let messageContent: SendMessageRequest;

    if (typeof message === 'string') {
      messageContent = {
        role: 'user',
        content: [{ type: 'text', text: message }],
        run: false,
      };
    } else {
      messageContent = {
        role: 'user',
        content: message.content,
        run: false,
      };
    }

    await this.client.post(`/api/conversations/${this.id}/events`, messageContent);
  }

  async run(): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/run`);
  }

  async pause(): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/pause`);
  }

  async setConfirmationPolicy(policy: ConfirmationPolicyBase): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/confirmation_policy`, { policy });
  }

  async sendConfirmationResponse(accept: boolean, reason?: string): Promise<void> {
    const request: ConfirmationResponseRequest = { accept, reason };
    await this.client.post(`/api/conversations/${this.id}/events/respond_to_confirmation`, request);
  }

  async setTitle(title: string): Promise<void> {
    const request: UpdateConversationRequest = { title };
    await this.client.patch(`/api/conversations/${this.id}`, request);
  }

  /**
   * 向智能体询问一个简单的问题，而不影响对话状态。
   * 这对于快速获得答案或澄清很有用。
   */
  async askAgent(question: string): Promise<string> {
    const request: AskAgentRequest = { question };
    const response = await this.client.post<AskAgentResponse>(
      `/api/conversations/${this.id}/ask_agent`,
      request
    );
    return response.data.response;
  }

  /**
   * 获取智能体对此对话的最终回复文本。
   */
  async getAgentFinalResponse(): Promise<string> {
    const response = await this.client.get<AgentResponseResult>(
      `/api/conversations/${this.id}/agent_final_response`
    );
    return response.data.response;
  }

  /**
   * 将对话切换到名为 LLM 的配置文件。
   */
  async switchProfile(profileName: string): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/switch_profile`, {
      profile_name: profileName,
    });
  }

  /**
   * 将对话的 LLM 交换为调用者提供的对象。 对于应用程序服务器
   * 直接拥有 LLM，并且不将配置文件推送到智能体服务器
   * 文件系统。
   */
  async switchLlm(llm: LLM): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/switch_llm`, { llm });
  }

  /**
   * 切换 ACP 对话的模型（ACP 模拟
   * {@链接switchLlm}）。 在实时会话中，服务器调用包装器
   * `session/set_model` 就位，上下文保留。 第一次运行之前
   * 还没有会话，因此服务器回答 200 并存储模型
   * 第一次会话。 非 ACP 对话得到 400。
   */
  async switchAcpModel(model: string): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/switch_acp_model`, { model });
  }

  /**
   * 在这个对话中开始一个 `/goal` 循环：智能体追求
   * 目标，并在每次运行后重新提示，直到裁判标记其已完成或
   * 已达到 `maxIterations`。 循环在此对话的历史记录中运行，并且
   * 事件流——它不会分叉。 如果跑动或进球循环发生，则抛出 409
   * 已经处于活动状态，并且目标无效 (e.g. 空）。
   */
  async startGoal(objective: string, maxIterations?: number): Promise<void> {
    const request: StartGoalRequest = { objective };
    if (maxIterations !== undefined) {
      request.max_iterations = maxIterations;
    }
    await this.client.post(`/api/conversations/${this.id}/goal`, request);
  }

  /**
   * 停止此对话中的活动 `/goal` 循环。 仅取消
   * 后台目标循环（不是对话）并记录 `interrupted`
   * 状态，以便 {@link resumeGoal} 可以继续。 即使没有循环也会成功
   * 当前正在运行。
   */
  async stopGoal(): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/goal/stop`, {});
  }

  /**
   * 恢复本次对话中上次中断的 `/goal` 循环，继续
   * 从它所达到的迭代开始。 如果跑动或进球循环发生，则抛出 409
   * 已经处于活动状态，并且在没有可恢复目标时处于 400 状态。
   */
  async resumeGoal(): Promise<void> {
    await this.client.post(`/api/conversations/${this.id}/goal/resume`, {});
  }

  /**
   * 分叉当前对话并返回一个新的 RemoteConversation 实例。
   */
  async fork(
    request: ForkConversationRequest = {},
    options: { includeSkills?: boolean } = {}
  ): Promise<RemoteConversation> {
    const response = await this.client.post<ConversationInfo>(
      `/api/conversations/${this.id}/fork`,
      request,
      {
        params:
          options.includeSkills === undefined
            ? undefined
            : { include_skills: options.includeSkills },
      }
    );

    const forkWorkspace = new RemoteWorkspace({
      host: this.workspace.host,
      workingDir: this.getConversationWorkingDir(response.data),
      apiKey: this.workspace.apiKey,
      conversationId: response.data.id,
    });

    return new RemoteConversation(response.data.agent, forkWorkspace, {
      conversationId: response.data.id,
      callback: this.callback,
      onError: this.onError,
      hookConfig: response.data.hook_config ?? this.hookConfig,
    });
  }

  /**
   * 将此对话的 HEAD 移至现有事件，重新定位活动
   * 分支就位。 与 {@link fork} 不同，这不会创建新的对话 -
   * 所有分支都保留在磁盘上，并且只有智能体下一个运行的分支
   * 变化。 通过 `null` 选择空树（故意的新根）。
   *
   * 之后会刷新缓存状态，以便后续的 `state` 读取
   * 反映了新的 HEAD - `leaf_event_id` 未通过
   * WebSocket. 如果服务器拒绝事件 ID，则抛出 404。
   */
  async navigateTo(eventId: string | null): Promise<void> {
    const request: NavigateConversationRequest = { event_id: eventId };
    await this.client.post(`/api/conversations/${this.id}/navigate`, request);
    await this.state.refresh();
  }

  /**
   * 将已持久化对话轨迹下载为 ZIP blob。
   */
  async downloadTrajectory(): Promise<Blob> {
    const response = await this.client.get<Blob>(`/api/file/download-trajectory/${this.id}`, {
      responseType: 'blob',
    });
    return response.data;
  }

  /**
   * 强制对话历史记录上下文压缩。
   * 这有助于减少长时间对话的内存使用量。
   */
  async condense(): Promise<void> {
    await this.client.post<Success>(`/api/conversations/${this.id}/condense`);
  }

  /**
   * 设置对话的安全分析器。
   * 安全分析器评估操作风险。
   */
  async setSecurityAnalyzer(securityAnalyzer: unknown | null): Promise<void> {
    const request: SetSecurityAnalyzerRequest = { security_analyzer: securityAnalyzer };
    await this.client.post(`/api/conversations/${this.id}/security_analyzer`, request);
  }

  async updateSecrets(secrets: Record<string, SecretValue>): Promise<void> {
    // 将 SecretValue 函数转换为 StaticSecret 对象
    const secretObjects: Record<string, { kind: 'StaticSecret'; value: string }> = {};
    for (const [key, value] of Object.entries(secrets)) {
      secretObjects[key] = {
        kind: 'StaticSecret',
        value: typeof value === 'function' ? value() : value,
      };
    }

    const request: UpdateSecretsRequest = { secrets: secretObjects };
    await this.client.post(`/api/conversations/${this.id}/secrets`, request);
  }

  async startWebSocketClient(): Promise<void> {
    if (this.wsClient) {
      return;
    }

    const reportError = (error: Error): void => {
      if (this.onError) {
        this.onError(error);
      }
    };

    // 创建处理用户回调和状态更新的组合回调
    const combinedCallback: ConversationCallbackType = (event) => {
      // 将事件添加到事件列表
      this.state.events.addEvent(event).catch((error) => {
        reportError(
          error instanceof Error ? error : new Error(`Error adding event to events list: ${error}`)
        );
      });

      // 如果是状态更新事件则更新状态
      const stateCallback = this.state.createStateUpdateCallback(this.onError);
      stateCallback(event);

      // 呼叫用户回调（如果提供）
      if (this.callback) {
        this.callback(event);
      }
    };

    this.wsClient = new WebSocketCallbackClient({
      host: this.workspace.host,
      conversationId: this.id,
      callback: combinedCallback,
      apiKey: this.workspace.apiKey,
      onError: this.onError,
    });

    this.wsClient.start();
  }

  async stopWebSocketClient(): Promise<void> {
    if (this.wsClient) {
      this.wsClient.stop();
      this.wsClient = undefined;
    }
  }

  async close(): Promise<void> {
    await this.stopWebSocketClient();
    this.client.close();
    this.workspace.close();
  }
}
