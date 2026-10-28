/**
 * 智能体类提供基于构造函数的 API 用于创建智能体。
 * 提供与 Python SDK 命名相匹配的更清晰的 API。
 */

import { AgentBase, LLM } from '../types/base';

export interface AgentOptions {
  llm: LLM;
  kind?: string;
  name?: string;
  [key: string]: unknown;
}

/**
 * 智能体实现 AgentBase 接口的类。
 * 提供基于构造函数的 API 用于创建智能体。
 *
 * 用途：
 *   常量智能体 = 新智能体({
 *     法尔姆：{
 *       型号：'gpt-4'，
 *       api_key：“你的钥匙”
 *     }
 *   });
 */
export class Agent implements AgentBase {
  kind: string;
  llm: LLM;
  name?: string;
  [key: string]: unknown;

  constructor(options: AgentOptions) {
    this.kind = options.kind || 'Agent';
    this.llm = options.llm;
    this.name = options.name;

    // 复制任何附加属性
    Object.keys(options).forEach((key) => {
      if (key !== 'kind' && key !== 'llm' && key !== 'name') {
        this[key] = options[key];
      }
    });
  }
}
