/**
 * 钩子配置加载和管理。
 *
 * 镜像 Python SDK 的 openhands.sdk.hooks.config 模块。
 * 浏览器安全：无文件 I/O 操作（这些操作发生在服务器端）。
 */

import { HookEventType, HookType } from './types';

/**
 * 挂钩事件的有效 snake_case 字段名称。
 * 这是挂钩事件类型的唯一事实来源。
 */
export const HOOK_EVENT_FIELDS: ReadonlySet<string> = new Set([
  'pre_tool_use',
  'post_tool_use',
  'user_prompt_submit',
  'session_start',
  'session_end',
  'stop',
]);

/**
 * 单个钩子定义。
 */
export interface HookDefinition {
  type?: HookType;
  command: string;
  timeout?: number;
  async?: boolean;
}

/**
 * 根据模式将事件与挂钩匹配。
 *
 * 支持精确匹配、通配符 (*) 和正则表达式（自动检测或 /pattern/).
 */
export interface HookMatcher {
  matcher?: string;
  hooks: HookDefinition[];
}

/**
 * 所有钩子的配置。
 */
export interface HookConfig {
  pre_tool_use: HookMatcher[];
  post_tool_use: HookMatcher[];
  user_prompt_submit: HookMatcher[];
  session_start: HookMatcher[];
  session_end: HookMatcher[];
  stop: HookMatcher[];
  [key: string]: HookMatcher[];
}

/** 指示模式的正则表达式元字符应被视为正则表达式。*/
const REGEX_METACHARACTERS = new Set('|.*+?[]()^$\\'.split(''));

/**
 * 检查匹配器是否与给定的工具名称匹配。
 */
export function matcherMatches(matcherDef: HookMatcher, toolName?: string | null): boolean {
  const pattern = matcherDef.matcher ?? '*';

  if (pattern === '*' || pattern === '') return true;
  if (toolName == null) return pattern === '*' || pattern === '';

  // 显式正则表达式：/pattern/
  if (pattern.startsWith('/') && pattern.endsWith('/') && pattern.length > 2) {
    const regexStr = pattern.slice(1, -1);
    try {
      return new RegExp(`^${regexStr}$`).test(toolName);
    } catch {
      return false;
    }
  }

  // 自动检测正则表达式：包含元字符
  if ([...pattern].some((c) => REGEX_METACHARACTERS.has(c))) {
    try {
      return new RegExp(`^${pattern}$`).test(toolName);
    } catch {
      // 正则表达式无效，无法完全匹配
    }
  }

  return pattern === toolName;
}

/**
 * 创建一个空的 HookConfig。
 */
export function createEmptyHookConfig(): HookConfig {
  return {
    pre_tool_use: [],
    post_tool_use: [],
    user_prompt_submit: [],
    session_start: [],
    session_end: [],
    stop: [],
  };
}

/**
 * 检查 HookConfig 是否没有配置钩子。
 */
export function isHookConfigEmpty(config: HookConfig): boolean {
  return ![
    config.pre_tool_use,
    config.post_tool_use,
    config.user_prompt_submit,
    config.session_start,
    config.session_end,
    config.stop,
  ].some((list) => list.length > 0);
}

/** 将 PascalCase 转换为 snake_case。*/
function pascalToSnake(name: string): string {
  return name.replace(/(?<!^)(?=[A-Z])/g, '_').toLowerCase();
}

/**
 * 标准化原始钩子数据，支持 PascalCase 键和旧的 `{hooks: ...}` 包装器。
 */
export function normalizeHooksInput(data: Record<string, unknown>): Record<string, unknown> {
  let unwrapped = data;

  // 解开旧格式：{"hooks": {"PreToolUse": [...]}}
  if ('hooks' in unwrapped && typeof unwrapped.hooks === 'object' && unwrapped.hooks !== null) {
    unwrapped = unwrapped.hooks as Record<string, unknown>;
  }

  const normalized: Record<string, unknown> = {};
  const seenFields = new Set<string>();

  for (const [key, value] of Object.entries(unwrapped)) {
    const snakeKey = pascalToSnake(key);
    const isPascalCase = snakeKey !== key;

    if (isPascalCase && !HOOK_EVENT_FIELDS.has(snakeKey)) {
      const validTypes = [...HOOK_EVENT_FIELDS].sort().join(', ');
      throw new Error(`Unknown event type '${key}'. Valid types: ${validTypes}`);
    }

    if (seenFields.has(snakeKey)) {
      throw new Error(
        `Duplicate hook event: both '${key}' and its snake_case equivalent '${snakeKey}' were provided`
      );
    }

    seenFields.add(snakeKey);
    normalized[snakeKey] = value;
  }

  return normalized;
}

/**
 * 从原始数据对象创建 HookConfig。
 * 支持 PascalCase 和 snake_case 键，以及传统的“hooks”包装器。
 */
export function hookConfigFromData(data: Record<string, unknown>): HookConfig {
  const normalized = normalizeHooksInput(data);
  const config = createEmptyHookConfig();

  for (const field of HOOK_EVENT_FIELDS) {
    if (field in normalized && Array.isArray(normalized[field])) {
      config[field] = normalized[field] as HookMatcher[];
    }
  }

  return config;
}

/**
 * 获取与给定事件类型和可选工具名称匹配的所有挂钩定义。
 */
export function getHooksForEvent(
  config: HookConfig,
  eventType: HookEventType,
  toolName?: string | null
): HookDefinition[] {
  const fieldName = pascalToSnake(eventType);
  const matchers: HookMatcher[] = config[fieldName] ?? [];
  const result: HookDefinition[] = [];

  for (const matcher of matchers) {
    if (matcherMatches(matcher, toolName)) {
      result.push(...matcher.hooks);
    }
  }

  return result;
}

/**
 * 检查是否有为事件类型配置的任何钩子。
 */
export function hasHooksForEvent(config: HookConfig, eventType: HookEventType): boolean {
  const fieldName = pascalToSnake(eventType);
  const matchers: HookMatcher[] = config[fieldName] ?? [];
  return matchers.length > 0;
}

/**
 * 通过连接每个事件类型的处理程序来合并多个挂钩配置。
 * 如果结果为空，则返回 null。
 */
export function mergeHookConfigs(configs: HookConfig[]): HookConfig | null {
  if (configs.length === 0) return null;

  const merged = createEmptyHookConfig();
  for (const config of configs) {
    for (const field of HOOK_EVENT_FIELDS) {
      merged[field] = [...merged[field], ...config[field]];
    }
  }

  if (isHookConfigEmpty(merged)) return null;
  return merged;
}

/**
 * 序列化 a HookConfig 到适合 JSON/API 载荷的普通对象。
 * 仅包含非空字段。
 */
export function hookConfigToJSON(config: HookConfig): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of HOOK_EVENT_FIELDS) {
    if (config[field].length > 0) {
      result[field] = config[field];
    }
  }
  return result;
}
