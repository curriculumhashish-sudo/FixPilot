/**
 * 挂钩事件类型和数据结构。
 *
 * 镜像 Python SDK 的 openhands.sdk.hooks.types 模块。
 */

/**
 * 可以触发钩子的钩子事件类型。
 */
export enum HookEventType {
  PRE_TOOL_USE = 'PreToolUse',
  POST_TOOL_USE = 'PostToolUse',
  USER_PROMPT_SUBMIT = 'UserPromptSubmit',
  SESSION_START = 'SessionStart',
  SESSION_END = 'SessionEnd',
  STOP = 'Stop',
}

/**
 * 可以执行的钩子类型。
 */
export enum HookType {
  COMMAND = 'command',
  PROMPT = 'prompt',
}

/**
 * 钩子可以对操作做出的决定。
 */
export enum HookDecision {
  ALLOW = 'allow',
  DENY = 'deny',
}

/**
 * 通过 stdin 作为 JSON 传递到挂钩脚本的数据。
 */
export interface HookEvent {
  event_type: HookEventType | string;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  tool_response?: Record<string, unknown> | null;
  message?: string | null;
  session_id?: string | null;
  working_dir?: string | null;
  metadata?: Record<string, unknown>;
}

/**
 * 执行挂钩的结果。
 *
 * 退出代码 0 = 成功，退出代码 2 = 阻止操作。
 */
export interface HookResult {
  success: boolean;
  blocked: boolean;
  exit_code: number;
  stdout: string;
  stderr: string;
  decision?: HookDecision | null;
  reason?: string | null;
  additional_context?: string | null;
  error?: string | null;
  async_started?: boolean;
}

/**
 * 检查此钩子结果后操作是否应继续。
 */
export function hookResultShouldContinue(result: HookResult): boolean {
  if (result.blocked) return false;
  if (result.decision === HookDecision.DENY) return false;
  return true;
}

/**
 * 默认创建成功HookResult。
 */
export function createSuccessResult(): HookResult {
  return {
    success: true,
    blocked: false,
    exit_code: 0,
    stdout: '',
    stderr: '',
    decision: null,
    reason: null,
    additional_context: null,
    error: null,
    async_started: false,
  };
}
