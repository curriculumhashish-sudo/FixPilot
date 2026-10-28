/**
 * 对话确认政策
 *
 * 定义操作执行前需要用户确认的策略。
 * 这反映了PythonSDK的确认政策系统。
 */

import { ActionEvent } from '../events/types';

/**
 * 操作的风险级别
 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'unknown';

/**
 * 将风险级别转换为数值以进行比较。
 */
export function riskLevelToNumeric(level: RiskLevel): number {
  switch (level) {
    case 'low':
      return 1;
    case 'medium':
      return 2;
    case 'high':
      return 3;
    case 'unknown':
      return 2; // 将未知视为媒介
  }
}

/**
 * 安全分析的结果
 */
export interface SecurityAnalysisResult {
  /** 确定的风险等级*/
  riskLevel: RiskLevel;
  /** 是否需要确认*/
  requiresConfirmation: boolean;
  /** 风险评估的人类可读解释*/
  explanation?: string;
  /** 确定的具体问题*/
  concerns?: string[];
}

/**
 * 确认策略的基本接口。
 * 策略确定操作何时需要用户确认。
 */
export interface ConfirmationPolicy {
  /** 策略类型标识符*/
  readonly type: string;

  /**
   * 确定某个操作是否需要确认。
   *
   * @param action - 要评估的操作
   * @param riskLevel - 可选的预先确定的风险级别
   * @returns True 如果需要确认
   */
  requiresConfirmation(action: ActionEvent, riskLevel?: RiskLevel): boolean;
}

/**
 * 无需确认 - 所有操作都会自动批准。
 * 这是开发/测试的默认策略。
 */
export class NeverConfirm implements ConfirmationPolicy {
  readonly type = 'never';

  requiresConfirmation(_action: ActionEvent, _riskLevel?: RiskLevel): boolean {
    return false;
  }
}

/**
 * 所有操作始终需要确认。
 * 使用此功能可实现最大程度的安全/监督。
 */
export class AlwaysConfirm implements ConfirmationPolicy {
  readonly type = 'always';

  requiresConfirmation(_action: ActionEvent, _riskLevel?: RiskLevel): boolean {
    return true;
  }
}

/**
 * 需要根据风险级别进行确认。
 * 达到或高于阈值的操作需要确认。
 */
export class RiskBasedConfirm implements ConfirmationPolicy {
  readonly type = 'risk_based';
  private threshold: RiskLevel;

  constructor(threshold: RiskLevel = 'medium') {
    this.threshold = threshold;
  }

  requiresConfirmation(_action: ActionEvent, riskLevel?: RiskLevel): boolean {
    const level = riskLevel || 'unknown';
    return riskLevelToNumeric(level) >= riskLevelToNumeric(this.threshold);
  }
}

/**
 * 需要确认特定工具。
 */
export class ToolBasedConfirm implements ConfirmationPolicy {
  readonly type = 'tool_based';
  private toolsRequiringConfirmation: Set<string>;

  constructor(tools: string[]) {
    this.toolsRequiringConfirmation = new Set(tools);
  }

  requiresConfirmation(action: ActionEvent, _riskLevel?: RiskLevel): boolean {
    return this.toolsRequiringConfirmation.has(action.tool_name);
  }
}

/**
 * 复合策略 - 如果 ANY 子策略需要，则需要确认。
 */
export class CompositeConfirm implements ConfirmationPolicy {
  readonly type = 'composite';
  private policies: ConfirmationPolicy[];

  constructor(policies: ConfirmationPolicy[]) {
    this.policies = policies;
  }

  requiresConfirmation(action: ActionEvent, riskLevel?: RiskLevel): boolean {
    return this.policies.some((policy) => policy.requiresConfirmation(action, riskLevel));
  }
}

/**
 * 从类型字符串创建确认策略。
 */
export function createConfirmationPolicy(type: string, options?: unknown): ConfirmationPolicy {
  switch (type) {
    case 'never':
      return new NeverConfirm();
    case 'always':
      return new AlwaysConfirm();
    case 'risk_based':
      return new RiskBasedConfirm((options as { threshold?: RiskLevel })?.threshold);
    case 'tool_based':
      return new ToolBasedConfirm((options as { tools: string[] })?.tools || []);
    default:
      return new NeverConfirm();
  }
}
