import { HttpClient } from './http-client';
import type { SubAgentsRequest, SubAgentsResponse } from '../models/api';

export interface SubAgentsClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

/**
 * 智能体-服务器的子智能体目录的客户端。
 *
 * 一次读取端点 (`POST /api/sub-agents`) 列出基于文件和
 * 内置子智能体可用于工作区。 只读：它发现
 * 目录，它不会改变它。
 */
export class SubAgentsClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: SubAgentsClientOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: options.timeout || 60000,
    });
  }

  /**
   * 列出工作区的基于文件和内置的子智能体。
   *
   * 按名称合并优先项目 > 用户 > 内置。
   */
  async getSubAgents(request: SubAgentsRequest = {}): Promise<SubAgentsResponse> {
    const response = await this.client.post<SubAgentsResponse>('/api/sub-agents', request);
    return response.data;
  }

  close(): void {
    this.client.close();
  }
}
