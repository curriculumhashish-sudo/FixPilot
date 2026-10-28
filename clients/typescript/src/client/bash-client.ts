import { HttpError } from './http-client';
import { createRuntimeHttpClients } from './runtime-transport';
import type { RuntimeServiceClientOptions } from './runtime-transport';
import type { HttpClient } from './http-client';
import {
  BashCommand,
  BashEvent,
  BashEventPage,
  BashEventSearchOptions,
  BashOutput,
  ClearBashEventsResponse,
  ExecuteBashRequest,
} from '../models/workspace';

export type BashClientOptions = RuntimeServiceClientOptions;

export class BashClient {
  public readonly host: string;
  public readonly apiKey?: string;
  private readonly client: HttpClient;

  constructor(options: BashClientOptions) {
    const { runtimeClient } = createRuntimeHttpClients(options);
    this.host = options.host.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.client = runtimeClient;
  }

  async searchEvents(options: BashEventSearchOptions = {}): Promise<BashEventPage> {
    const response = await this.client.get<BashEventPage>('/api/bash/bash_events/search', {
      params: options as Record<string, unknown>,
    });
    return response.data;
  }

  async getEvent(eventId: string): Promise<BashEvent> {
    const response = await this.client.get<BashEvent>(`/api/bash/bash_events/${eventId}`);
    return response.data;
  }

  async getEvents(eventIds: string[]): Promise<Array<BashEvent | null>> {
    return Promise.all(
      eventIds.map(async (eventId) => {
        try {
          return await this.getEvent(eventId);
        } catch (error) {
          if (error instanceof HttpError && error.status === 404) {
            return null;
          }
          throw error;
        }
      })
    );
  }

  /**
   * 通过 `GET /api/bash/bash_events/` 在单个请求中批量获取 bash 事件。
   *
   * 与 {@link getEvents}（每个 id 扇出一个请求）不同，这会调用
   * 服务器端批处理端点并为每个请求的 id 返回一个条目，其中
   * `null` 在任何丢失事件的槽中 - 保留输入顺序。
   */
  async batchGetEvents(eventIds: string[]): Promise<Array<BashEvent | null>> {
    const response = await this.client.get<(BashEvent | null)[]>('/api/bash/bash_events/', {
      data: eventIds,
    });
    return response.data;
  }

  async startCommand(
    request: string | ExecuteBashRequest,
    cwd?: string,
    timeout?: number
  ): Promise<BashCommand> {
    const payload = this.normalizeRequest(request, cwd, timeout);
    const response = await this.client.post<BashCommand>('/api/bash/start_bash_command', payload);
    return response.data;
  }

  async executeCommand(
    request: string | ExecuteBashRequest,
    cwd?: string,
    timeout?: number
  ): Promise<BashOutput> {
    const payload = this.normalizeRequest(request, cwd, timeout);
    const response = await this.client.post<BashOutput>('/api/bash/execute_bash_command', payload, {
      timeout: ((payload.timeout || 30) + 10) * 1000,
    });
    return response.data;
  }

  async clearEvents(): Promise<ClearBashEventsResponse> {
    const response = await this.client.delete<ClearBashEventsResponse>('/api/bash/bash_events');
    return response.data;
  }

  /**
   * 通过 id 停止正在运行的 bash 命令。 未知或已完成的 id
   * 解析成功，匹配服务器的幂等性合约。
   */
  async stopCommand(commandId: string): Promise<void> {
    try {
      await this.client.post(`/api/bash/bash_commands/${commandId}/stop`, {});
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) {
        return;
      }
      throw error;
    }
  }

  close(): void {
    this.client.close();
  }

  private normalizeRequest(
    request: string | ExecuteBashRequest,
    cwd?: string,
    timeout?: number
  ): ExecuteBashRequest {
    if (typeof request === 'string') {
      return {
        command: request,
        ...(cwd ? { cwd } : {}),
        ...(timeout !== undefined ? { timeout: Math.floor(timeout) } : {}),
      };
    }

    return {
      ...request,
      ...(request.timeout !== undefined ? { timeout: Math.floor(request.timeout) } : {}),
    };
  }
}
