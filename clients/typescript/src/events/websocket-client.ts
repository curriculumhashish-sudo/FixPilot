/**
 * WebSocket 实时事件客户端流式传输
 */

import { Event, ConversationCallbackType } from '../types/base';
import {
  ConversationEventStream,
  buildConversationEventStreamUrl,
} from '../client/conversation-event-stream';
import { WEBSOCKET_UNAVAILABLE_MESSAGE, getGlobalWebSocket } from './global-websocket';

/**
 * 用于报告非致命错误的错误回调类型。
 * 库代码调用它而不是 console.error，以便调用者可以处理错误。
 */
export type ErrorCallbackType = (error: Error) => void;

export interface WebSocketClientOptions {
  host: string;
  conversationId: string;
  callback: ConversationCallbackType;
  apiKey?: string;
  /** 可选错误回调。 因非致命错误（解析失败、连接问题）而调用。*/
  onError?: ErrorCallbackType;
}

/** 类型化事件适配器与浏览器使用者使用的相同传输层。*/
export class WebSocketCallbackClient {
  private stream?: ConversationEventStream;

  constructor(private options: WebSocketClientOptions) {}

  private createStream(): ConversationEventStream {
    const options = this.options;
    let lastError: Error | null = null;
    return new ConversationEventStream({
      url: buildConversationEventStreamUrl(options.host, options.conversationId),
      sessionApiKey: options.apiKey,
      reconnect: { enabled: true },
      createWebSocket: (url) => {
        const WebSocketImpl = getGlobalWebSocket();
        if (!WebSocketImpl) throw new Error(WEBSOCKET_UNAVAILABLE_MESSAGE);
        return new WebSocketImpl(url);
      },
      onMessage: (event) => {
        try {
          const message = typeof event.data === 'string' ? event.data : event.data.toString();
          options.callback(JSON.parse(message) as Event);
        } catch (error) {
          options.onError?.(
            new Error(
              `Error processing WebSocket message: ${error instanceof Error ? error.message : String(error)}`
            )
          );
        }
      },
      onStateChange: ({ error }) => {
        if (error && error !== lastError) options.onError?.(error);
        lastError = error;
      },
    });
  }

  start(): void {
    try {
      this.stream ??= this.createStream();
      this.stream.start();
    } catch (error) {
      this.options.onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  }

  stop(): void {
    this.stream?.stop();
  }
}
