/**
 * 对话卡住检测
 *
 * 检测智能体何时陷入重复或无效模式。
 * 这反映了 Python SDK 的 StuckDetector 类。
 */

import {
  BaseEvent,
  ActionEvent,
  ObservationEvent,
  AgentErrorEvent,
  isActionEvent,
  isObservationEvent,
  isAgentErrorEvent,
  isMessageEvent,
} from '../events/types';

/**
 * 卡住检测模式的阈值
 */
export interface StuckDetectionThresholds {
  /** 触发前相同动作-观测结果对的数量（默认值：4）*/
  actionObservation: number;
  /** 触发前相同动作-错误对的数量（默认值：4）*/
  actionError: number;
  /** 无需用户输入的连续智能体消息数（默认值：4）*/
  monologue: number;
  /** 触发前交替模式的数量（默认值：6）*/
  alternatingPattern: number;
}

/**
 * 卡住检测的默认阈值
 */
export const DEFAULT_STUCK_THRESHOLDS: StuckDetectionThresholds = {
  actionObservation: 4,
  actionError: 4,
  monologue: 4,
  alternatingPattern: 6,
};

/**
 * 卡住检测检查结果
 */
export interface StuckDetectionResult {
  /** 智能体是否卡住*/
  isStuck: boolean;
  /** 检测到的卡住图案类型（如果有）*/
  pattern?:
    | 'action_observation_loop'
    | 'action_error_loop'
    | 'monologue'
    | 'alternating_pattern'
    | 'context_window_error';
  /** 检测到的重复次数*/
  repetitions?: number;
  /** 人类可读的描述*/
  description?: string;
}

/**
 * 检测智能体何时陷入重复或无效模式。
 *
 * 该检测器分析对话历史记录以识别各种卡住模式：
 * 1. 重复动作-观测结果个周期
 * 2. 重复动作-错误循环
 * 3. 智能体独白（无需用户输入的重复消息）
 * 4. 重复交替动作-观测结果模式
 * 5. 上下文窗口指示内存问题的错误
 */
export class StuckDetector {
  private thresholds: StuckDetectionThresholds;

  constructor(thresholds?: Partial<StuckDetectionThresholds>) {
    this.thresholds = {
      ...DEFAULT_STUCK_THRESHOLDS,
      ...thresholds,
    };
  }

  /**
   * 根据事件历史记录检查智能体是否卡住。
   *
   * @param events - 要分析的对话事件数组
   * @returns StuckDetectionResult 带有卡住状态和详细信息
   */
  isStuck(events: BaseEvent[]): StuckDetectionResult {
    // 查找最后一条用户消息索引
    const lastUserMsgIndex = this.findLastUserMessageIndex(events);

    if (lastUserMsgIndex === -1) {
      // 未找到用户消息，跳过检测
      return { isStuck: false };
    }

    // 仅分析最后一条用户消息之后的事件
    const recentEvents = events.slice(lastUserMsgIndex + 1);

    // 确定所需的最少事件
    const minThreshold = Math.min(
      this.thresholds.actionObservation,
      this.thresholds.actionError,
      this.thresholds.monologue
    );

    if (recentEvents.length < minThreshold) {
      return { isStuck: false };
    }

    // 收集操作和观测结果进行分析
    const maxNeeded = Math.max(this.thresholds.actionObservation, this.thresholds.actionError);
    const lastActions: ActionEvent[] = [];
    const lastObservations: (ObservationEvent | AgentErrorEvent)[] = [];

    // 从历史的终结收集
    for (let i = recentEvents.length - 1; i >= 0; i--) {
      const event = recentEvents[i];
      if (isActionEvent(event) && lastActions.length < maxNeeded) {
        lastActions.push(event);
      } else if (
        (isObservationEvent(event) || isAgentErrorEvent(event)) &&
        lastObservations.length < maxNeeded
      ) {
        lastObservations.push(event);
      }
      if (lastActions.length >= maxNeeded && lastObservations.length >= maxNeeded) {
        break;
      }
    }

    // 检查所有卡住的图案

    // 场景 1：相同的操作，相同的观测结果
    const actionObsResult = this.checkRepeatingActionObservation(lastActions, lastObservations);
    if (actionObsResult.isStuck) {
      return actionObsResult;
    }

    // 场景 2：相同的操作，但出现错误
    const actionErrorResult = this.checkRepeatingActionError(lastActions, lastObservations);
    if (actionErrorResult.isStuck) {
      return actionErrorResult;
    }

    // 场景三：独白
    const monologueResult = this.checkMonologue(recentEvents);
    if (monologueResult.isStuck) {
      return monologueResult;
    }

    // 场景 4：交替动作-观测结果模式
    if (recentEvents.length >= this.thresholds.alternatingPattern) {
      const alternatingResult = this.checkAlternatingPattern(recentEvents);
      if (alternatingResult.isStuck) {
        return alternatingResult;
      }
    }

    return { isStuck: false };
  }

  /**
   * 查找事件中最后一条用户消息的索引。
   */
  private findLastUserMessageIndex(events: BaseEvent[]): number {
    for (let i = events.length - 1; i >= 0; i--) {
      const event = events[i];
      if (isMessageEvent(event) && event.source === 'user') {
        return i;
      }
    }
    return -1;
  }

  /**
   * 检查重复的操作-观测结果模式。
   */
  private checkRepeatingActionObservation(
    lastActions: ActionEvent[],
    lastObservations: (ObservationEvent | AgentErrorEvent)[]
  ): StuckDetectionResult {
    const threshold = this.thresholds.actionObservation;

    if (lastActions.length < threshold || lastObservations.length < threshold) {
      return { isStuck: false };
    }

    // 过滤为仅常规观测结果（不是错误）
    const observations = lastObservations.filter(isObservationEvent);
    if (observations.length < threshold) {
      return { isStuck: false };
    }

    // 检查所有操作是否相同
    const actionsEqual = lastActions
      .slice(0, threshold)
      .every((action) => this.actionsEqual(lastActions[0], action));

    // 检查所有观测结果是否相同
    const observationsEqual = observations
      .slice(0, threshold)
      .every((obs) => this.observationsEqual(observations[0], obs));

    if (actionsEqual && observationsEqual) {
      return {
        isStuck: true,
        pattern: 'action_observation_loop',
        repetitions: threshold,
        description: `Agent is repeating the same action-observation cycle ${threshold} times. Action: ${lastActions[0].tool_name}`,
      };
    }

    return { isStuck: false };
  }

  /**
   * 检查重复的操作错误模式。
   */
  private checkRepeatingActionError(
    lastActions: ActionEvent[],
    lastObservations: (ObservationEvent | AgentErrorEvent)[]
  ): StuckDetectionResult {
    const threshold = this.thresholds.actionError;

    if (lastActions.length < threshold || lastObservations.length < threshold) {
      return { isStuck: false };
    }

    // 检查所有操作是否相同
    const actionsEqual = lastActions
      .slice(0, threshold)
      .every((action) => this.actionsEqual(lastActions[0], action));

    if (!actionsEqual) {
      return { isStuck: false };
    }

    // 检查观测结果是否全部错误
    const allErrors = lastObservations.slice(0, threshold).every(isAgentErrorEvent);

    if (allErrors) {
      return {
        isStuck: true,
        pattern: 'action_error_loop',
        repetitions: threshold,
        description: `Agent is repeating the same action ${threshold} times and getting errors. Action: ${lastActions[0].tool_name}`,
      };
    }

    return { isStuck: false };
  }

  /**
   * 检查智能体独白（没有用户输入的重复消息）。
   */
  private checkMonologue(events: BaseEvent[]): StuckDetectionResult {
    const threshold = this.thresholds.monologue;

    if (events.length < threshold) {
      return { isStuck: false };
    }

    let agentMessageCount = 0;

    // 从末尾开始计算连续的智能体条消息
    for (let i = events.length - 1; i >= 0; i--) {
      const event = events[i];

      if (isMessageEvent(event)) {
        if (event.source === 'agent') {
          agentMessageCount++;
        } else if (event.source === 'user') {
          // 用户被打断，而不是独白
          break;
        }
      } else if (event.kind === 'CondensationSummaryEvent') {
        // 上下文压缩事件不会打破独白模式
        continue;
      } else {
        // 其他事件（行动/观察）打破了计数
        break;
      }
    }

    if (agentMessageCount >= threshold) {
      return {
        isStuck: true,
        pattern: 'monologue',
        repetitions: agentMessageCount,
        description: `Agent has sent ${agentMessageCount} consecutive messages without user input`,
      };
    }

    return { isStuck: false };
  }

  /**
   * 检查交替动作-观测结果模式 (A-B-A-B-A-B)。
   */
  private checkAlternatingPattern(events: BaseEvent[]): StuckDetectionResult {
    const threshold = this.thresholds.alternatingPattern;

    const lastActions: ActionEvent[] = [];
    const lastObservations: (ObservationEvent | AgentErrorEvent)[] = [];

    // 收集最近的行动和观测结果
    for (let i = events.length - 1; i >= 0; i--) {
      const event = events[i];
      if (isActionEvent(event) && lastActions.length < threshold) {
        lastActions.push(event);
      } else if (
        (isObservationEvent(event) || isAgentErrorEvent(event)) &&
        lastObservations.length < threshold
      ) {
        lastObservations.push(event);
      }
      if (lastActions.length === threshold && lastObservations.length === threshold) {
        break;
      }
    }

    if (lastActions.length < threshold || lastObservations.length < threshold) {
      return { isStuck: false };
    }

    // 检查交替模式：偶数索引匹配，奇数索引匹配这会检测 A-B-A-B-A-B 模式
    //
    const actionsAlternate = this.checkAlternatingEquality(lastActions);
    const observationsAlternate = this.checkAlternatingEquality(lastObservations);

    if (actionsAlternate && observationsAlternate) {
      return {
        isStuck: true,
        pattern: 'alternating_pattern',
        repetitions: threshold,
        description: `Agent is stuck in an alternating action-observation pattern`,
      };
    }

    return { isStuck: false };
  }

  /**
   * 检查元素是否交替（偶数索引彼此匹配，奇数索引彼此匹配）。
   */
  private checkAlternatingEquality<T extends BaseEvent>(items: T[]): boolean {
    if (items.length < 4) {
      return false;
    }

    // 检查 items[0] == items[2] == items[4] ... 项目[1] == 项目[3] == 项目[5] ...
    for (let i = 0; i < items.length - 2; i++) {
      if (!this.eventsEqual(items[i], items[i + 2])) {
        return false;
      }
    }

    return true;
  }

  /**
   * 比较两个操作事件是否相等（忽略 ID 和时间戳）。
   */
  private actionsEqual(a: ActionEvent, b: ActionEvent): boolean {
    return (
      a.source === b.source &&
      a.tool_name === b.tool_name &&
      a.thought === b.thought &&
      JSON.stringify(a.action) === JSON.stringify(b.action)
    );
  }

  /**
   * 比较两个观测结果事件是否相等（忽略 ID 和时间戳）。
   */
  private observationsEqual(a: ObservationEvent, b: ObservationEvent): boolean {
    return (
      a.source === b.source &&
      a.tool_name === b.tool_name &&
      JSON.stringify(a.observation) === JSON.stringify(b.observation)
    );
  }

  /**
   * 根据两个事件的类型比较它们是否相等。
   */
  private eventsEqual(a: BaseEvent, b: BaseEvent): boolean {
    if (a.kind !== b.kind) {
      return false;
    }

    if (isActionEvent(a) && isActionEvent(b)) {
      return this.actionsEqual(a, b);
    }

    if (isObservationEvent(a) && isObservationEvent(b)) {
      return this.observationsEqual(a, b);
    }

    if (isAgentErrorEvent(a) && isAgentErrorEvent(b)) {
      return a.source === b.source && a.error === b.error;
    }

    if (isMessageEvent(a) && isMessageEvent(b)) {
      return (
        a.source === b.source && JSON.stringify(a.llm_message) === JSON.stringify(b.llm_message)
      );
    }

    // 回退方案：比较JSON表示
    return JSON.stringify(a) === JSON.stringify(b);
  }
}
