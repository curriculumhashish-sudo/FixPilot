/**
 * OpenRouter LLM 实施
 *
 * 这使用 OpenRouter SDK 实现了 ILLM 接口，
 * 通过统一的 API 提供对 300 多个模型的访问。
 */

import { OpenRouter } from '@openrouter/sdk';
import type {
  ILLM,
  BaseLLMOptions,
  ChatCompletionOptions,
  ChatCompletionResponse,
  ChatCompletionChunk,
  ChatMessage,
  Tool,
  ToolCall,
  TokenCallbackType,
} from './base';

// 由于 SDK 的模块解析很复杂，因此在本地定义响应类型
interface OpenRouterChatResponse {
  id: string;
  choices: Array<{
    message?: {
      content?: string | null;
      toolCalls?: ToolCall[];
    };
    finishReason?: string;
  }>;
  created: number;
  model: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };
}

interface OpenRouterStreamChunk {
  id?: string;
  model?: string;
  choices: Array<{
    index?: number;
    delta?: {
      role?: string;
      content?: string;
      toolCalls?: Array<{
        index: number;
        id?: string;
        type?: string;
        function?: {
          name?: string;
          arguments?: string;
        };
      }>;
    };
    finishReason?: string;
  }>;
  created?: number;
}

/**
 * 用于创建 OpenRouterLLM 实例的选项
 */
export interface OpenRouterLLMOptions extends BaseLLMOptions {
  /** 网站 URL 在 openrouter.ai 上的排名（可选）*/
  siteUrl?: string;
  /** openrouter.ai 排名的网站标题（可选）*/
  siteTitle?: string;
}

// OpenRouter SDK 消息类型（为我们使用而简化）
type OpenRouterMessage =
  | { role: 'system'; content: string; name?: string }
  | { role: 'user'; content: string; name?: string }
  | { role: 'assistant'; content: string | null; name?: string; toolCalls?: ToolCall[] }
  | { role: 'tool'; content: string; toolCallId: string };

/**
 * OpenRouter LLM 使用官方@openrouter/sdk实现。
 *
 * 通过OpenRouter的统一API提供对300多个AI模型的访问。
 *
 * 示例：
 * ```TypeScript
 * 常量 llm = 新 OpenRouterLLM({
 *   apiKey: '你的-API-密钥',
 *   defaultModel: '人类/克劳德-3.5-十四行诗'
 * });
 *
 * const response = wait llm.generate('你好，你好吗？');
 * console.log（回复）；
 *
 * // 或完全控制：
 * 常量完成 = 等待 llm.chatCompletion({
 *   messages: [{ role: '用户', content: '解释量子计算' }],
 *   温度：0.7，
 *   maxTokens: 1000
 * });
 * ```
 */
export class OpenRouterLLM implements ILLM {
  private client: OpenRouter;
  public readonly defaultModel: string;
  private readonly defaultTemperature?: number;
  private readonly defaultMaxTokens?: number;

  constructor(options: OpenRouterLLMOptions) {
    this.client = new OpenRouter({
      apiKey: options.apiKey,
      httpReferer: options.siteUrl,
      appTitle: options.siteTitle,
    });

    this.defaultModel = options.defaultModel || 'anthropic/claude-3.5-sonnet';
    this.defaultTemperature = options.defaultTemperature;
    this.defaultMaxTokens = options.defaultMaxTokens;
  }

  /**
   * 将我们的 ChatMessage 格式转换为 OpenRouter 的格式
   */
  private convertMessages(messages: ChatMessage[]): OpenRouterMessage[] {
    return messages.map((msg): OpenRouterMessage => {
      if (msg.role === 'system') {
        return {
          role: 'system',
          content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
          name: msg.name,
        };
      } else if (msg.role === 'user') {
        return {
          role: 'user',
          content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
          name: msg.name,
        };
      } else if (msg.role === 'assistant') {
        return {
          role: 'assistant',
          content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
          name: msg.name,
          toolCalls: msg.tool_calls,
        };
      } else {
        // 工具角色
        return {
          role: 'tool',
          content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
          toolCallId: msg.tool_call_id || '',
        };
      }
    });
  }

  /**
   * 将我们的工具格式转换为OpenRouter的格式
   */
  private convertTools(tools: Tool[]) {
    return tools.map((tool) => ({
      type: 'function' as const,
      function: {
        name: tool.function.name,
        description: tool.function.description,
        parameters: tool.function.parameters,
      },
    }));
  }

  /**
   * 构建chatCompletion和chatCompletionStream共享的公共请求参数。
   */
  private buildRequestParams(
    options: ChatCompletionOptions | Omit<ChatCompletionOptions, 'stream'>,
    stream: boolean
  ): Record<string, unknown> {
    const requestParams: Record<string, unknown> = {
      model: options.model || this.defaultModel,
      messages: this.convertMessages(options.messages),
      stream,
    };

    if (options.temperature !== undefined) {
      requestParams.temperature = options.temperature;
    } else if (this.defaultTemperature !== undefined) {
      requestParams.temperature = this.defaultTemperature;
    }

    if (options.maxTokens !== undefined) {
      requestParams.maxTokens = options.maxTokens;
    } else if (this.defaultMaxTokens !== undefined) {
      requestParams.maxTokens = this.defaultMaxTokens;
    }

    if (options.tools && options.tools.length > 0) {
      requestParams.tools = this.convertTools(options.tools);
    }

    if (options.toolChoice) {
      requestParams.toolChoice = options.toolChoice;
    }

    if (options.stop) {
      requestParams.stop = options.stop;
    }

    return requestParams;
  }

  async chatCompletion(options: ChatCompletionOptions): Promise<ChatCompletionResponse> {
    const model = options.model || this.defaultModel;
    const requestParams = this.buildRequestParams(options, false);

    // 转换为预期类型 - SDK 句柄验证
    const response = (await this.client.chat.send(
      requestParams as Parameters<typeof this.client.chat.send>[0]
    )) as OpenRouterChatResponse;

    // 转换为我们的响应格式
    return {
      id: response.id || '',
      model: response.model || model,
      choices: response.choices.map(
        (choice: OpenRouterChatResponse['choices'][0], index: number) => ({
          index,
          message: {
            role: 'assistant' as const,
            content: choice.message?.content || null,
            tool_calls: choice.message?.toolCalls as ToolCall[] | undefined,
          },
          finish_reason:
            (choice.finishReason as 'stop' | 'length' | 'tool_calls' | 'content_filter') || null,
        })
      ),
      usage: response.usage
        ? {
            prompt_tokens: response.usage.promptTokens || 0,
            completion_tokens: response.usage.completionTokens || 0,
            total_tokens: response.usage.totalTokens || 0,
          }
        : undefined,
      created: response.created || Date.now(),
    };
  }

  async *chatCompletionStream(
    options: Omit<ChatCompletionOptions, 'stream'>
  ): AsyncIterable<ChatCompletionChunk> {
    const model = options.model || this.defaultModel;
    const requestParams = this.buildRequestParams(options, true);

    const stream = await this.client.chat.send(
      requestParams as Parameters<typeof this.client.chat.send>[0]
    );

    // 当流为 True 时，流是异步可迭代的
    for await (const chunk of stream as AsyncIterable<OpenRouterStreamChunk>) {
      yield {
        id: chunk.id || '',
        model: chunk.model || model,
        choices: chunk.choices.map((choice: OpenRouterStreamChunk['choices'][0]) => ({
          index: choice.index || 0,
          delta: {
            role: choice.delta?.role as 'assistant' | undefined,
            content: choice.delta?.content,
            tool_calls: choice.delta?.toolCalls?.map(
              (
                tc: NonNullable<
                  NonNullable<OpenRouterStreamChunk['choices'][0]['delta']>['toolCalls']
                >[0]
              ) => ({
                index: tc.index,
                id: tc.id,
                type: tc.type as 'function' | undefined,
                function: tc.function,
              })
            ),
          },
          finish_reason:
            (choice.finishReason as 'stop' | 'length' | 'tool_calls' | 'content_filter') || null,
        })),
        created: chunk.created || Date.now(),
      };
    }
  }

  async generate(prompt: string, systemPrompt?: string): Promise<string> {
    const messages: ChatMessage[] = [];

    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    const response = await this.chatCompletion({ messages });

    return response.choices[0]?.message?.content || '';
  }

  /**
   * 与流式传输和 token 回调聊天完成。
   * 为流式传输期间收到的每个 token 调用回调。
   */
  async chatCompletionWithCallback(
    options: Omit<ChatCompletionOptions, 'stream'>,
    onToken: TokenCallbackType
  ): Promise<ChatCompletionResponse> {
    const model = options.model || this.defaultModel;
    let accumulated = '';
    let tokenIndex = 0;
    let lastChunk: ChatCompletionChunk | null = null;
    const toolCalls: Map<
      number,
      { id: string; type: 'function'; function: { name: string; arguments: string } }
    > = new Map();

    for await (const chunk of this.chatCompletionStream(options)) {
      lastChunk = chunk;

      for (const choice of chunk.choices) {
        // 处理内容 token
        if (choice.delta?.content) {
          accumulated += choice.delta.content;
          onToken({
            token: choice.delta.content,
            isFinal: false,
            accumulated,
            index: tokenIndex++,
            model: chunk.model,
          });
        }

        // 累计工具调用
        if (choice.delta?.tool_calls) {
          for (const tc of choice.delta.tool_calls) {
            const existing = toolCalls.get(tc.index);
            if (existing) {
              // 追加到现有的工具调用
              if (tc.function?.arguments) {
                existing.function.arguments += tc.function.arguments;
              }
            } else if (tc.id) {
              // 新工具调用
              toolCalls.set(tc.index, {
                id: tc.id,
                type: 'function',
                function: {
                  name: tc.function?.name || '',
                  arguments: tc.function?.arguments || '',
                },
              });
            }
          }
        }
      }
    }

    // 发送最终 token 事件
    onToken({
      token: '',
      isFinal: true,
      accumulated,
      index: tokenIndex,
      model,
    });

    // 构建最终响应
    const finalToolCalls = toolCalls.size > 0 ? Array.from(toolCalls.values()) : undefined;

    return {
      id: lastChunk?.id || '',
      model: lastChunk?.model || model,
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: accumulated || null,
            tool_calls: finalToolCalls,
          },
          finish_reason: lastChunk?.choices[0]?.finish_reason || 'stop',
        },
      ],
      created: lastChunk?.created || Date.now(),
    };
  }

  /**
   * 使用流式传输和 token 回调生成。
   */
  async generateWithCallback(
    prompt: string,
    systemPrompt?: string,
    onToken?: TokenCallbackType
  ): Promise<string> {
    const messages: ChatMessage[] = [];

    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    if (onToken) {
      const response = await this.chatCompletionWithCallback({ messages }, onToken);
      return response.choices[0]?.message?.content || '';
    } else {
      return this.generate(prompt, systemPrompt);
    }
  }

  close(): void {
    // OpenRouter SDK 不需要显式清理
  }
}
