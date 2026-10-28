import { HttpClient } from './http-client';
import {
  ActivateMetaProfileResponse,
  MetaProfile,
  MetaProfileDetailResponse,
  MetaProfileListResponse,
  MetaProfileMutationResponse,
} from '../models/api';

export interface MetaProfilesClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

/**
 * 客户端为智能体-服务器``/api/meta-profiles``端点。
 *
 * 元配置文件是由
 * ``route_task_to_model`` 工具。 与 LLM 配置文件不同，元配置文件不包含
 * 机密 — 它们是普通的 JSON 文档 — 因此没有机密-曝光
 * 在这里处理。
 */
export class MetaProfilesClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: MetaProfilesClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout || 60000,
    });
  }

  async listMetaProfiles(): Promise<MetaProfileListResponse> {
    const response = await this.client.get<MetaProfileListResponse>('/api/meta-profiles');
    return response.data;
  }

  async getMetaProfile(name: string): Promise<MetaProfileDetailResponse> {
    const response = await this.client.get<MetaProfileDetailResponse>(
      `/api/meta-profiles/${encodeURIComponent(name)}`
    );
    return response.data;
  }

  async saveMetaProfile(name: string, config: MetaProfile): Promise<MetaProfileMutationResponse> {
    const response = await this.client.post<MetaProfileMutationResponse>(
      `/api/meta-profiles/${encodeURIComponent(name)}`,
      config
    );
    return response.data;
  }

  async deleteMetaProfile(name: string): Promise<MetaProfileMutationResponse> {
    const response = await this.client.delete<MetaProfileMutationResponse>(
      `/api/meta-profiles/${encodeURIComponent(name)}`
    );
    return response.data;
  }

  async activateMetaProfile(name: string): Promise<ActivateMetaProfileResponse> {
    const response = await this.client.post<ActivateMetaProfileResponse>(
      `/api/meta-profiles/${encodeURIComponent(name)}/activate`,
      {}
    );
    return response.data;
  }

  close(): void {
    this.client.close();
  }
}
