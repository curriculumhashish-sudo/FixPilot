/**
 * LLM 模块导出
 */

// 基本类型和接口
export type {
  ILLM,
  BaseLLMOptions,
  LLMProviderType,
  MessageRole,
  TextContent,
  ImageContent,
  ContentPart,
  ChatMessage,
  Tool,
  ToolCall,
  ChatCompletionOptions,
  ChatCompletionChoice,
  TokenUsage,
  ChatCompletionResponse,
  ChatCompletionChunk,
  TokenCallbackType,
  TokenStreamEvent,
} from './base';

// OpenRouter 实施
export { OpenRouterLLM } from './openrouter-llm';
export type { OpenRouterLLMOptions } from './openrouter-llm';

// 工厂函数和 LLM 类
export { LLM, createLLM, createOpenRouterLLM } from './llm';
export type { LLMOptions, CreateLLMOptions } from './llm';
