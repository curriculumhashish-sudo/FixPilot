/**
 * OpenHands 挂钩系统 - 用于自动化和控制的事件驱动挂钩。
 *
 * 挂钩是在特定生命周期事件时执行的事件驱动脚本
 * 在智能体执行期间，实现对智能体行为的确定性控制。
 *
 * 挂钩执行发生在服务器端。 该模块提供：
 * - 与 Python SDK 匹配的类型定义
 * 配置解析和操作工具
 * - API 用于从服务器加载钩子的客户端方法
 */

export {
  HookEventType,
  HookType,
  HookDecision,
  hookResultShouldContinue,
  createSuccessResult,
} from './types';
export type { HookEvent, HookResult } from './types';

export {
  HOOK_EVENT_FIELDS,
  matcherMatches,
  createEmptyHookConfig,
  isHookConfigEmpty,
  normalizeHooksInput,
  hookConfigFromData,
  getHooksForEvent,
  hasHooksForEvent,
  mergeHookConfigs,
  hookConfigToJSON,
} from './config';
export type { HookDefinition, HookMatcher, HookConfig } from './config';
