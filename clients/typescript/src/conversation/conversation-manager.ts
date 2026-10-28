/**
 * 用于处理多个对话的对话管理器
 */

import { HttpClient } from '../client/http-client';
import { AgentProfilesClient } from '../client/agent-profiles-client';
import { FileClient } from '../client/file-client';
import { HooksClient } from '../client/hooks-client';
import { LLMMetadataClient } from '../client/llm-client';
import { MCPClient } from '../client/mcp-client';
import { ProfilesClient } from '../client/profiles-client';
import { MetaProfilesClient } from '../client/meta-profiles-client';
import { ServerClient } from '../client/server-client';
import { SettingsClient } from '../client/settings-client';
import { SharedClient } from '../client/shared-client';
import { SkillsClient } from '../client/skills-client';
import { SubAgentsClient } from '../client/sub-agents-client';
import { ToolClient } from '../client/tool-client';
import { VSCodeClient } from '../client/vscode-client';
import { WorkspacesClient } from '../client/workspaces-client';
import { RemoteConversation } from './remote-conversation';
import { RemoteWorkspace } from '../workspace/remote-workspace';
import {
  ACPAgentConfig,
  ACPConversationInfo,
  ACPConversationSearchResponse,
  ConversationInfo,
  ConversationSearchRequest,
  ConversationSearchResponse,
  CreateACPConversationRequest,
  UpdateConversationRequest,
} from '../models/conversation';
import { AgentBase, ConversationExecutionStatus, ConversationID, Success } from '../types/base';

export class ACPConversationNamespace {
  constructor(private readonly manager: ConversationManager) {}

  searchConversations(
    options: ConversationSearchRequest = {}
  ): Promise<ACPConversationSearchResponse> {
    return this.manager.searchACPConversations(options);
  }

  countConversations(options: { status?: ConversationExecutionStatus } = {}): Promise<number> {
    return this.manager.countACPConversations(options);
  }

  getConversations(conversationIds: ConversationID[]): Promise<Array<ACPConversationInfo | null>> {
    return this.manager.getACPConversations(conversationIds);
  }

  getAllConversations(): Promise<ACPConversationInfo[]> {
    return this.manager.getAllACPConversations();
  }

  getConversation(conversationId: ConversationID): Promise<ACPConversationInfo> {
    return this.manager.getACPConversation(conversationId);
  }

  createConversation(
    agent: ACPAgentConfig,
    options: {
      initialMessage?: string;
      maxIterations?: number;
      stuckDetection?: boolean;
      workingDir?: string;
    } = {}
  ): Promise<ACPConversationInfo> {
    return this.manager.createACPConversation(agent, options);
  }
}

export interface ConversationManagerOptions {
  host: string;
  apiKey?: string;
}

export class ConversationManager {
  private readonly client: HttpClient;
  public readonly host: string;
  public readonly apiKey?: string;
  public readonly server: ServerClient;
  public readonly llm: LLMMetadataClient;
  public readonly profiles: ProfilesClient;
  public readonly agentProfiles: AgentProfilesClient;
  public readonly metaProfiles: MetaProfilesClient;
  public readonly settings: SettingsClient;
  public readonly skills: SkillsClient;
  public readonly subAgents: SubAgentsClient;
  public readonly tools: ToolClient;
  public readonly vscode: VSCodeClient;
  public readonly files: FileClient;
  public readonly workspaces: WorkspacesClient;
  public readonly shared: SharedClient;
  public readonly hooks: HooksClient;
  public readonly mcp: MCPClient;
  public readonly acp: ACPConversationNamespace;

  constructor(options: ConversationManagerOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;

    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: 60000,
    });

    const clientOptions = {
      host: this.host,
      ...(this.apiKey ? { apiKey: this.apiKey } : {}),
    };

    this.server = new ServerClient(clientOptions);
    this.llm = new LLMMetadataClient(clientOptions);
    this.profiles = new ProfilesClient(clientOptions);
    this.agentProfiles = new AgentProfilesClient(clientOptions);
    this.metaProfiles = new MetaProfilesClient(clientOptions);
    this.settings = new SettingsClient(clientOptions);
    this.skills = new SkillsClient(clientOptions);
    this.subAgents = new SubAgentsClient(clientOptions);
    this.tools = new ToolClient(clientOptions);
    this.vscode = new VSCodeClient(clientOptions);
    this.files = new FileClient(clientOptions);
    this.workspaces = new WorkspacesClient(clientOptions);
    this.shared = new SharedClient(clientOptions);
    this.hooks = new HooksClient(clientOptions);
    this.mcp = new MCPClient(clientOptions);
    this.acp = new ACPConversationNamespace(this);
  }

  /**
   * 搜索/列出对话
   */
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

  /**
   * 计算与提供的过滤器匹配的对话。
   */
  async countConversations(
    options: { status?: ConversationExecutionStatus } = {}
  ): Promise<number> {
    const response = await this.client.get<number>('/api/conversations/count', {
      params: options as Record<string, unknown>,
    });
    return response.data;
  }

  /**
   * 通过ID批量获取对话。
   */
  async getConversations(
    conversationIds: ConversationID[]
  ): Promise<Array<ConversationInfo | null>> {
    const response = await this.client.get<Array<ConversationInfo | null>>('/api/conversations', {
      params: { ids: conversationIds },
    });
    return response.data;
  }

  /**
   * 获取所有对话（便捷方法）
   */
  async getAllConversations(options?: { tag?: string[] }): Promise<ConversationInfo[]> {
    const conversations: ConversationInfo[] = [];
    let nextPageId: string | undefined;

    do {
      const response = await this.searchConversations({
        page_id: nextPageId,
        limit: 100,
        ...(options?.tag ? { tag: options.tag } : {}),
      });

      conversations.push(...response.items);
      nextPageId = response.next_page_id;
    } while (nextPageId);

    return conversations;
  }

  /**
   * 通过ID获取特定对话
   */
  async getConversation(conversationId: ConversationID): Promise<ConversationInfo> {
    const response = await this.client.get<ConversationInfo>(
      `/api/conversations/${conversationId}`
    );
    return response.data;
  }

  /**
   * 创建新对话
   */
  async createConversation(
    agent: AgentBase,
    options: {
      initialMessage?: string;
      maxIterations?: number;
      stuckDetection?: boolean;
      workingDir?: string;
      userId?: string;
    } = {}
  ): Promise<RemoteConversation> {
    const workspace = new RemoteWorkspace({
      host: this.host,
      workingDir: options.workingDir || '/tmp',
      apiKey: this.apiKey,
    });

    const conversation = new RemoteConversation(agent, workspace, {
      maxIterations: options.maxIterations,
      stuckDetection: options.stuckDetection,
      userId: options.userId,
    });

    await conversation.start({
      initialMessage: options.initialMessage,
      maxIterations: options.maxIterations,
      stuckDetection: options.stuckDetection,
      userId: options.userId,
    });

    return conversation;
  }

  /**
   * 加载现有对话
   */
  async loadConversation(
    conversationId: ConversationID,
    workingDir: string = '/tmp'
  ): Promise<RemoteConversation> {
    const conversationInfo = await this.getConversation(conversationId);

    const workspace = new RemoteWorkspace({
      host: this.host,
      workingDir,
      conversationId,
      apiKey: this.apiKey,
    });

    const conversation = new RemoteConversation(conversationInfo.agent, workspace, {
      conversationId,
    });

    await conversation.start();
    return conversation;
  }

  /**
   * 搜索支持 ACP 的对话。
   */
  async searchACPConversations(
    options: ConversationSearchRequest = {}
  ): Promise<ACPConversationSearchResponse> {
    const response = await this.client.get<ACPConversationSearchResponse>(
      '/api/conversations/search',
      {
        params: options as Record<string, unknown>,
      }
    );
    return response.data;
  }

  /**
   * 对支持 ACP 的对话进行计数。
   */
  async countACPConversations(
    options: { status?: ConversationExecutionStatus } = {}
  ): Promise<number> {
    const response = await this.client.get<number>('/api/conversations/count', {
      params: options,
    });
    return response.data;
  }

  /**
   * 按 ID 批量获取支持 ACP 的对话。
   */
  async getACPConversations(
    conversationIds: ConversationID[]
  ): Promise<Array<ACPConversationInfo | null>> {
    const response = await this.client.get<Array<ACPConversationInfo | null>>(
      '/api/conversations',
      {
        params: { ids: conversationIds },
      }
    );
    return response.data;
  }

  /**
   * 获取所有支持 ACP 的对话（便捷方法）。
   */
  async getAllACPConversations(): Promise<ACPConversationInfo[]> {
    const conversations: ACPConversationInfo[] = [];
    let nextPageId: string | undefined;

    do {
      const response = await this.searchACPConversations({
        page_id: nextPageId,
        limit: 100,
      });

      conversations.push(...response.items);
      nextPageId = response.next_page_id;
    } while (nextPageId);

    return conversations;
  }

  /**
   * 通过 ID 获取特定的 ACP 功能对话。
   */
  async getACPConversation(conversationId: ConversationID): Promise<ACPConversationInfo> {
    const response = await this.client.get<ACPConversationInfo>(
      `/api/conversations/${conversationId}`
    );
    return response.data;
  }

  /**
   * 创建一个新的支持 ACP 的对话。
   */
  async createACPConversation(
    agent: ACPAgentConfig,
    options: {
      initialMessage?: string;
      maxIterations?: number;
      stuckDetection?: boolean;
      workingDir?: string;
      userId?: string;
    } = {}
  ): Promise<ACPConversationInfo> {
    let initialMessage: CreateACPConversationRequest['initial_message'];
    if (options.initialMessage) {
      initialMessage = {
        role: 'user' as const,
        content: [{ type: 'text' as const, text: options.initialMessage }],
      };
    }

    const request: CreateACPConversationRequest = {
      agent,
      initial_message: initialMessage,
      max_iterations: options.maxIterations || 500,
      stuck_detection: options.stuckDetection ?? true,
      workspace: { type: 'local', working_dir: options.workingDir || '/tmp' },
      user_id: options.userId ?? null,
    };

    const response = await this.client.post<ACPConversationInfo>('/api/conversations', request);
    return response.data;
  }

  /**
   * 将对话切换到命名的 LLM 配置文件。
   */
  async switchProfile(conversationId: ConversationID, profileName: string): Promise<void> {
    await this.client.post<Success>(`/api/conversations/${conversationId}/switch_profile`, {
      profile_name: profileName,
    });
  }

  /**
   * 删除对话
   */
  async deleteConversation(conversationId: ConversationID): Promise<void> {
    await this.client.delete<Success>(`/api/conversations/${conversationId}`);
  }

  /**
   * 更新对话元数据 (e.g. 标题）并用更新后的解决
   * 谈话。 PATCH 端点只回答 `Success`，所以
   * 更新后会回读对话。
   */
  async updateConversation(
    conversationId: ConversationID,
    update: UpdateConversationRequest
  ): Promise<ConversationInfo> {
    await this.client.patch<Success>(`/api/conversations/${conversationId}`, update);
    return this.getConversation(conversationId);
  }

  /**
   * 关闭管理器并清理资源
   */
  close(): void {
    this.server.close();
    this.llm.close();
    this.profiles.close();
    this.metaProfiles.close();
    this.settings.close();
    this.skills.close();
    this.subAgents.close();
    this.tools.close();
    this.vscode.close();
    this.files.close();
    this.workspaces.close();
    this.shared.close();
    this.hooks.close();
    this.mcp.close();
    this.client.close();
  }
}
