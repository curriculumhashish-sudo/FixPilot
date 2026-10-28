/**
 * 远程事件列表——事件搜索的薄包装API。
 *
 * 通过 WebSocket 接收的事件保存在本地缓存中，以便调用者可以
 * 无需额外的网络调用即可迭代它们。 对于历史事件使用
 * `search()` 或 `getEvents()` 按需访问服务器。
 */

import { HttpClient, HttpError } from '../client/http-client';
import type { HttpClientOptions } from '../client/http-client';
import { Event, ConversationCallbackType } from '../types/base';
import { EventPage } from '../types/base';

/**
 * 搜索事件的选项
 */
export interface EventSearchOptions {
  /** 每页返回的最大事件数*/
  limit?: number;
  /** 分页的页面 ID*/
  page_id?: string;
  /** 按事件种类/类型过滤（e.g.、ActionEvent、MessageEvent）*/
  kind?: string;
  /** 按事件源过滤（e.g.、智能体、用户、环境）*/
  source?: string;
  /** 按消息内容过滤（不区分大小写）*/
  body?: string;
  /** 事件排序*/
  sort_order?: 'TIMESTAMP' | 'TIMESTAMP_DESC';
  /** 过滤器：事件时间戳 >= 此日期时间（ISO 8601 格式） */
  timestamp__gte?: string;
  /** 过滤器：事件时间戳 < 此日期时间（ISO 8601 格式） */
  timestamp__lt?: string;
}

export type RemoteEventsListOptions = HttpClientOptions;

export class RemoteEventsList {
  private client: HttpClient;
  private conversationId: string;
  private cachedEvents: Event[] = [];
  private cachedEventIds = new Set<string>();

  constructor(clientOrOptions: HttpClient | RemoteEventsListOptions, conversationId: string) {
    this.client =
      clientOrOptions instanceof HttpClient ? clientOrOptions : new HttpClient(clientOrOptions);
    this.conversationId = conversationId;
  }

  /**
   * 使用可选过滤器搜索事件。
   * 直接查询服务器。
   */
  async search(options: EventSearchOptions = {}): Promise<EventPage> {
    const params: Record<string, unknown> = {
      limit: options.limit ?? 100,
    };

    if (options.page_id) params.page_id = options.page_id;
    if (options.kind) params.kind = options.kind;
    if (options.source) params.source = options.source;
    if (options.body) params.body = options.body;
    if (options.sort_order) params.sort_order = options.sort_order;
    if (options.timestamp__gte) params.timestamp__gte = options.timestamp__gte;
    if (options.timestamp__lt) params.timestamp__lt = options.timestamp__lt;

    const response = await this.client.get<EventPage>(
      `/api/conversations/${this.conversationId}/events/search`,
      { params }
    );

    return response.data;
  }

  /**
   * 计算与给定过滤器匹配的事件数。
   */
  async count(
    options: Omit<EventSearchOptions, 'limit' | 'page_id' | 'sort_order'> = {}
  ): Promise<number> {
    const params: Record<string, unknown> = {};

    if (options.kind) params.kind = options.kind;
    if (options.source) params.source = options.source;
    if (options.body) params.body = options.body;
    if (options.timestamp__gte) params.timestamp__gte = options.timestamp__gte;
    if (options.timestamp__lt) params.timestamp__lt = options.timestamp__lt;

    const response = await this.client.get<number>(
      `/api/conversations/${this.conversationId}/events/count`,
      { params }
    );

    return response.data;
  }

  /**
   * 通过 ID 获取服务器事件。
   */
  async getEventById(eventId: string): Promise<Event> {
    const response = await this.client.get<Event>(
      `/api/conversations/${this.conversationId}/events/${eventId}`
    );
    return response.data;
  }

  /**
   * 通过ID批量获取服务器事件。
   */
  async getEventsById(eventIds: string[]): Promise<Array<Event | null>> {
    return Promise.all(
      eventIds.map(async (eventId) => {
        try {
          return await this.getEventById(eventId);
        } catch (error) {
          if (error instanceof HttpError && error.status === 404) {
            return null;
          }
          throw error;
        }
      })
    );
  }

  async addEvent(event: Event): Promise<void> {
    if (!this.cachedEventIds.has(event.id)) {
      this.cachedEvents.push(event);
      this.cachedEventIds.add(event.id);
    }
  }

  // 与 EventLog 接口兼容的别名
  async append(event: Event): Promise<void> {
    await this.addEvent(event);
  }

  createDefaultCallback(onError?: (error: Error) => void): ConversationCallbackType {
    return (event: Event) => {
      this.addEvent(event).catch((error) => {
        if (onError) {
          onError(
            error instanceof Error ? error : new Error(`Error adding event to cache: ${error}`)
          );
        }
      });
    };
  }

  async length(): Promise<number> {
    return this.cachedEvents.length;
  }

  async getEvent(index: number): Promise<Event | undefined> {
    return this.cachedEvents[index];
  }

  /**
   * 从服务器获取所有事件，并与本地缓存的任何事件合并
   * 通过 WebSocket 收到的事件。
   */
  async getEvents(start?: number, end?: number): Promise<Event[]> {
    const remote: Event[] = [];
    let pageId: string | undefined;

    for (;;) {
      const params: Record<string, unknown> = { limit: 100 };
      if (pageId) params.page_id = pageId;

      const response = await this.client.get<EventPage>(
        `/api/conversations/${this.conversationId}/events/search`,
        { params }
      );

      const data = response.data;
      remote.push(...data.items);

      if (!data.next_page_id) break;
      pageId = data.next_page_id;
    }

    const remoteIds = new Set(remote.map((event) => event.id));
    const merged = [...remote, ...this.cachedEvents.filter((event) => !remoteIds.has(event.id))];

    if (start === undefined && end === undefined) {
      return merged;
    }
    return merged.slice(start, end);
  }

  async *[Symbol.asyncIterator](): AsyncIterableIterator<Event> {
    const events = await this.getEvents();
    for (const event of events) {
      yield event;
    }
  }
}
