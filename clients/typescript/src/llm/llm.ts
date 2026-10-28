/**
 * LLM 工厂和实用功能
 *
 * 该模块提供了一个方便的工厂模式来创建 LLM 实例。
 */

import type { ILLM, LLMProviderType } from './base';
import { OpenRouterLLM, OpenRouterLLMOptions } from './openrouter-llm';

/**
 * 所有 LLM 选项的联合类型
 */
export type LLMOptions = OpenRouterLLMOptions;

/**
 * 用于创建具有显式提供者选择的 LLM 的选项
 */
export interface CreateLLMOptions {
  provider: LLMProviderType;
  options: LLMOptions;
}

/**
 * 用于根据提供程序创建 LLM 实例的工厂函数。
 *
 * 目前支持：
 * - 'openrouter': OpenRouter API (300+型号)
 *
 * 未来的支持计划：
 * - 'OpenAI'：直接 OpenAI API
 * -“Anthropic”：直接 Anthropic API
 * -“自定义”：自定义端点
 *
 * 示例：
 * ```TypeScript
 * 常量 llm = createLLM({
 *   提供者：'开放路由器'，
 *   选项：{
 *     apiKey: '你的-API-密钥',
 *     defaultModel: '人类/克劳德-3.5-十四行诗'
 *   }
 * });
 *
 * const response = wait llm.generate('你好！');
 * ```
 *
 * @param config - LLM 配置，包括提供程序和选项
 * @returns 实现 ILLM 的 LLM 实例
 */
export function createLLM(config: CreateLLMOptions): ILLM {
  switch (config.provider) {
    case 'openrouter':
      return new OpenRouterLLM(config.options as OpenRouterLLMOptions);

    case 'openai':
      // TODO：实施OpenAI直接支持
      throw new Error(
        'OpenAI direct support not yet implemented. ' +
          'Use OpenRouter with openai/* models instead.'
      );

    case 'anthropic':
      // TODO：实施Anthropic直接支持
      throw new Error(
        'Anthropic direct support not yet implemented. ' +
          'Use OpenRouter with anthropic/* models instead.'
      );

    case 'custom':
      // TODO：实现自定义端点支持
      throw new Error('Custom LLM endpoints not yet implemented.');

    default:
      throw new Error(`Unknown LLM provider: ${config.provider}`);
  }
}

/**
 * 直接创建一个OpenRouterLLM实例。
 *
 * 这是最常见用例的便利功能。
 *
 * 示例：
 * ```TypeScript
 * 常量 llm = createOpenRouterLLM({
 *   apiKey: '你的-API-密钥',
 *   defaultModel: 'openai/gpt-4o'
 * });
 * ```
 *
 * @param options - OpenRouter 特定选项
 * @returns 一个 OpenRouterLLM 实例
 */
export function createOpenRouterLLM(options: OpenRouterLLMOptions): OpenRouterLLM {
  return new OpenRouterLLM(options);
}

/**
 * LLM 类将 OpenRouterLLM 扩展为向后兼容性
 * 并提供了一个简单的默认LLM实现。
 *
 * 示例：
 * ```TypeScript
 * 常量 llm = 新 LLM({
 *   apiKey: '你的-API-密钥',
 *   defaultModel: '人类/克劳德-3.5-十四行诗'
 * });
 * ```
 */
export class LLM extends OpenRouterLLM {
  constructor(options: OpenRouterLLMOptions) {
    super(options);
  }
}
