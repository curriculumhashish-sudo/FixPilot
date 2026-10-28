import { HttpClient } from './http-client';
import {
  ActivateProfileResponse,
  ExposeSecretsMode,
  ProfileDetailResponse,
  ProfileListResponse,
  ProfileMutationResponse,
  SaveProfileRequest,
  ValidateProfileResponse,
} from '../models/api';

export interface ProfilesClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

export interface GetProfileOptions {
  /**
   * 通过 ``X-Expose-Secrets`` 标头控制服务器端机密暴露：
   * - ``encrypted``：密码加密值（前端往返安全）
   * - ``plaintext``：原始机密值（仅限后端客户端）
   * - 省略：``api_key`` 为空，带有 ``api_key_set`` 指示符
   */
  exposeSecrets?: ExposeSecretsMode;
}

export class ProfilesClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: ProfilesClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout || 60000,
    });
  }

  async listProfiles(): Promise<ProfileListResponse> {
    const response = await this.client.get<ProfileListResponse>('/api/profiles');
    return response.data;
  }

  async getProfile(name: string, options: GetProfileOptions = {}): Promise<ProfileDetailResponse> {
    const headers: Record<string, string> = {};
    if (options.exposeSecrets) {
      headers['X-Expose-Secrets'] = options.exposeSecrets;
    }
    const response = await this.client.get<ProfileDetailResponse>(
      `/api/profiles/${encodeURIComponent(name)}`,
      { headers }
    );
    return response.data;
  }

  async saveProfile(name: string, request: SaveProfileRequest): Promise<ProfileMutationResponse> {
    const response = await this.client.post<ProfileMutationResponse>(
      `/api/profiles/${encodeURIComponent(name)}`,
      request
    );
    return response.data;
  }

  async deleteProfile(name: string): Promise<ProfileMutationResponse> {
    const response = await this.client.delete<ProfileMutationResponse>(
      `/api/profiles/${encodeURIComponent(name)}`
    );
    return response.data;
  }

  async renameProfile(name: string, newName: string): Promise<ProfileMutationResponse> {
    const response = await this.client.post<ProfileMutationResponse>(
      `/api/profiles/${encodeURIComponent(name)}/rename`,
      { new_name: newName }
    );
    return response.data;
  }

  async activateProfile(name: string): Promise<ActivateProfileResponse> {
    const response = await this.client.post<ActivateProfileResponse>(
      `/api/profiles/${encodeURIComponent(name)}/activate`,
      {}
    );
    return response.data;
  }

  /**
   * 飞行前检查：触发最小 LLM 完成（``ping``，
   * ``max_tokens=1``) 使用提交的配置来捕获错误配置
   * 无效的模型名称，缺少提供者前缀，错误的基类 URLs无效
   * API 键）在保存配置文件之前。
   *
   * 结构化的 ``{ valid: false, error: { type, message } }`` 响应是
   * 阻塞错误时返回。 瞬态错误（速率限制，超时）是
   * 非阻塞（``valid: true``）。 较旧的智能体-服务器版本不支持
   * 实现端点响应 404，其表面为 ``HttpError``，因此
   * 调用者可以将其视为“无判决”并继续。
   */
  async validateProfile(
    name: string,
    request: SaveProfileRequest
  ): Promise<ValidateProfileResponse> {
    const response = await this.client.post<ValidateProfileResponse>(
      `/api/profiles/${encodeURIComponent(name)}/validate`,
      request
    );
    return response.data;
  }

  close(): void {
    this.client.close();
  }
}
