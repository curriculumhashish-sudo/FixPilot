/**
 * 基本 LLM 接口和类型
 *
 * 该文件定义了所有 LLM 实现必须遵循的抽象接口。
 * 它提供了与不同 LLM 提供者（OpenRouter、OpenAI 等）交互的统一方式
 */

/**
 * 聊天对话的消息角色类型
 */
export type MessageRole = 'system' | 'user' | 'assistant' | 'tool';

/**
 * token 回调类型为流式传输 token。
 * 对流式传输完成期间收到的每个 token 进行调用。
 */
export type TokenCallbackType = (token: TokenStreamEvent) => void;

/**
 * token 流事件 - 表示单个 token 或来自流式传输的块
 */
export interface TokenStreamEvent {
  /** token内容*/
  token: string;
  /** 这是否是最终的token*/
  isFinal: boolean;
  /** 目前已累计内容*/
  accumulated?: string;
  /** token 响应中的索引*/
  index?: number;
  /** 生成此 token 的模型*/
  model?: string;
}

/**
 * 消息的内容类型
 */
export interface TextContent {
  type: 'text';
  text: string;
}

export interface ImageContent {
  type: 'image_url';
  image_url: {
    url: string;
    detail?: 'auto' | 'low' | 'high';
  };
}

export type ContentPart = TextContent | ImageContent;

/**
 * 聊天对话中的一条消息
 */
export interface ChatMessage {
  role: MessageRole;
  content: string | ContentPart[];
  name?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

/**
 * LLM 的工具/功能定义
 */
export interface Tool {
  type: 'function';
  function: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
  };
}

/**
 * LLM 请求的工具调用
 */
export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

/**
 * 聊天完成请求的选项
 */
export interface ChatCompletionOptions {
  /** 要使用的模型（e.g., 'anthropic/claude-3.5-sonnet', 'openai/gpt-4o'）*/
  model?: string;
  /** 要发送的消息*/
  messages: ChatMessage[];
  /** 采样温度（0-2）*/
  temperature?: number;
  /** 生成的最大值 token*/
  maxTokens?: number;
  /** 模型可用的工具/功能*/
  tools?: Tool[];
  /** 模型应如何使用工具：“auto”、“None”或特定工具*/
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'function'; function: { name: string } };
  /** 停止序列*/
  stop?: string[];
  /** 是否流式传输响应*/
  stream?: boolean;
}

/**
 * 完成响应中的选择
 */
export interface ChatCompletionChoice {
  index: number;
  message: {
    role: 'assistant';
    content: string | null;
    tool_calls?: ToolCall[];
  };
  finish_reason: 'stop' | 'length' | 'tool_calls' | 'content_filter' | null;
}

/**
 * 词元用量信息
 */
export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/**
 * 聊天完成请求的响应
 */
export interface ChatCompletionResponse {
  id: string;
  model: string;
  choices: ChatCompletionChoice[];
  usage?: TokenUsage;
  created: number;
}

/**
 * 来自 LLM 的流式传输块
 */
export interface ChatCompletionChunk {
  id: string;
  model: string;
  choices: Array<{
    index: number;
    delta: {
      role?: 'assistant';
      content?: string | null;
      tool_calls?: Array<{
        index: number;
        id?: string;
        type?: 'function';
        function?: {
          name?: string;
          arguments?: string;
        };
      }>;
    };
    finish_reason: 'stop' | 'length' | 'tool_calls' | 'content_filter' | null;
  }>;
  created: number;
}

/**
 * 用于创建 LLM 客户端的基本选项
 */
export interface BaseLLMOptions {
  /** API 键用于身份验证*/
  apiKey: string;
  /** 如果请求中未指定，则使用默认模型*/
  defaultModel?: string;
  /** 用于 API 的底座 URL（可选，用于自定义端点）*/
  baseUrl?: string;
  /** 默认温度*/
  defaultTemperature?: number;
  /** 默认最大值 token*/
  defaultMaxTokens?: number;
}

/**
 * LLM 实现的抽象接口。
 *
 * 所有 LLM 提供者（OpenRouter、OpenAI、Anthropic 等）都应实现此接口
 * 提供与不同模型交互的统一方式。
 */
export interface ILLM {
  /** 此 LLM 实例的默认模型*/
  readonly defaultModel: string;

  /**
   * 发送聊天完成请求并获得完整回复。
   *
   * @param options - 完成选项，包括消息和模型设置
   * @returns 带有生成内容的完成响应
   */
  chatCompletion(options: ChatCompletionOptions): Promise<ChatCompletionResponse>;

  /**
   * 发送聊天完成请求并流式传输响应。
   *
   * @param options - 完成选项（流将设置为 True）
   * @returns 完成块的异步可迭代
   */
  chatCompletionStream(
    options: Omit<ChatCompletionOptions, 'stream'>
  ): AsyncIterable<ChatCompletionChunk>;

  /**
   * 使用流式传输发送聊天完成请求，并为每个 token 调用回调。
   *
   * 当您只需要时，此方法为流式传输提供了更简单的接口
   * 在 token 到达时对其进行处理，而无需亲自管理异步迭代器。
   *
   * @param options - 完成选项
   * @param onToken - 回调为收到的每个 token 调用
   * @returns 最终完成响应
   */
  chatCompletionWithCallback?(
    options: Omit<ChatCompletionOptions, 'stream'>,
    onToken: TokenCallbackType
  ): Promise<ChatCompletionResponse>;

  /**
   * 发送一条消息并获取文本响应的简单助手。
   *
   * @param 提示词 - 要发送的用户消息
   * @param systemPrompt - 可选系统提示词
   * @returns 助理的回复文本
   */
  generate(prompt: string, systemPrompt?: string): Promise<string>;

  /**
   * 带有 token 流式传输回调的简单助手。
   *
   * @param 提示词 - 要发送的用户消息
   * @param systemPrompt - 可选系统提示词
   * @param onToken - 回调为收到的每个 token 调用
   * @returns 助理的回复文本
   */
  generateWithCallback?(
    prompt: string,
    systemPrompt?: string,
    onToken?: TokenCallbackType
  ): Promise<string>;

  /**
   * 关闭/清理 LLM 客户端持有的所有资源。
   */
  close(): void;
}

/**
 * LLM 提供者类型的类型鉴别器。
 */
export type LLMProviderType = 'openrouter' | 'openai' | 'anthropic' | 'custom';
