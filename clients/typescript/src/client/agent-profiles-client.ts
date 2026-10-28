import { HttpClient } from './http-client';
import type {
  AgentProfile,
  AgentProfileDiagnostics,
  AgentProfileSaveInput,
  AgentProfileSummary,
} from '../models/agent-profile';
import type { ExposeSecretsMode } from '../models/api';

export interface AgentProfilesClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

export interface GetAgentProfileOptions {
  /**
   * 通过控制服务器端 `skills[].mcp_tools` 机密曝光
   * `X-Expose-Secrets`:
   * - `"encrypted"`：Fernet 加密值（前端往返安全）
   * - `"plaintext"`：原始机密值（仅限后端客户端）
   * - 省略：值被屏蔽/编辑
   */
  exposeSecrets?: ExposeSecretsMode;
}

export interface AgentProfileListResponse {
  profiles: AgentProfileSummary[];
  active_agent_profile_id: string | null;
}

export interface AgentProfileDetailResponse {
  name: string;
  profile: AgentProfile;
}

export interface AgentProfileMutationResponse {
  name: string;
  message: string;
}

export interface ActivateAgentProfileResponse {
  id: string;
  message: string;
  /** 始终 False — 仅激活指针（不写入 agent_settings）。*/
  agent_settings_applied: boolean;
}

/**
 * 客户端为智能体-服务器`/api/agent-profiles`端点。
 *
 * OpenHands 智能体服务器中的镜像 `agent_profiles_router.py`。
 * 错误状态代码通过 `HttpError.status` 出现：
 * - 404：找不到配置文件（获取/重命名/实现）
 * - 409：超出配置文件限制（保存）或 new_name 已存在（重命名）
 * - 422：验证错误（保存）
 *
 * `delete` 是幂等的 — 缺少名称会解析 200，而不是 404。 `materialize`
 * 永远不会在悬空的 LLM/MCP 裁判上加注； 它们在响应正文中报告
 * (`valid: false`, `dangling_mcp_server_refs`)，不是 4xx。
 */
export class AgentProfilesClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: AgentProfilesClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout ?? 60000,
    });
  }

  async listAgentProfiles(): Promise<AgentProfileListResponse> {
    const response = await this.client.get<AgentProfileListResponse>('/api/agent-profiles');
    return response.data;
  }

  async getAgentProfile(
    name: string,
    options: GetAgentProfileOptions = {}
  ): Promise<AgentProfileDetailResponse> {
    const headers: Record<string, string> = {};
    if (options.exposeSecrets) {
      headers['X-Expose-Secrets'] = options.exposeSecrets;
    }
    const response = await this.client.get<AgentProfileDetailResponse>(
      `/api/agent-profiles/${encodeURIComponent(name)}`,
      { headers }
    );
    return response.data;
  }

  async saveAgentProfile(
    name: string,
    profile: AgentProfileSaveInput
  ): Promise<AgentProfileMutationResponse> {
    const response = await this.client.post<AgentProfileMutationResponse>(
      `/api/agent-profiles/${encodeURIComponent(name)}`,
      profile
    );
    return response.data;
  }

  async deleteAgentProfile(name: string): Promise<AgentProfileMutationResponse> {
    const response = await this.client.delete<AgentProfileMutationResponse>(
      `/api/agent-profiles/${encodeURIComponent(name)}`
    );
    return response.data;
  }

  async renameAgentProfile(name: string, newName: string): Promise<AgentProfileMutationResponse> {
    const response = await this.client.post<AgentProfileMutationResponse>(
      `/api/agent-profiles/${encodeURIComponent(name)}/rename`,
      { new_name: newName }
    );
    return response.data;
  }

  /**
   * 通过稳定的 UUID 激活配置文件。
   * 仅指针 — 不写入 `agent_settings`。
   *
   * @param profileId 要激活的配置文件的稳定 `id` UUID。
   */
  async activateAgentProfile(profileId: string): Promise<ActivateAgentProfileResponse> {
    const response = await this.client.post<ActivateAgentProfileResponse>(
      `/api/agent-profiles/${encodeURIComponent(profileId)}/activate`,
      {}
    );
    return response.data;
  }

  /**
   * 试运行解析配置文件的 LLM/MCP 引用。
   * 返回一个{@link AgentProfileDiagnostics}报告； 永远不会加注
   * 悬空引用——那些出现在正文中的带有 `valid: false` 的引用。
   *
   * @param name 配置文件名称（路径段，而不是 UUID）。
   * @param Draft 未保存的配置文件来解析，而不是存储的配置文件； 像保存一样进行验证。
   */
  async materializeAgentProfile(
    name: string,
    draft?: AgentProfileSaveInput
  ): Promise<AgentProfileDiagnostics> {
    const response = await this.client.post<AgentProfileDiagnostics>(
      `/api/agent-profiles/${encodeURIComponent(name)}/materialize`,
      draft ? { profile: draft } : {}
    );
    return response.data;
  }

  close(): void {
    this.client.close();
  }
}
