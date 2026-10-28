/**
 * 对话安全分析器
 *
 * 分析潜在安全风险的操作。
 * 这反映了 Python SDK 的 SecurityAnalyzer 系统。
 */

import { ActionEvent } from '../events/types';
import { RiskLevel, SecurityAnalysisResult, riskLevelToNumeric } from './confirmation-policy';

/**
 * 安全分析器的基本接口。
 * 分析人员评估行动以确定其风险级别。
 */
export interface SecurityAnalyzer {
  /** 分析仪类型标识符*/
  readonly type: string;

  /**
   * 分析安全风险的操作。
   *
   * @param action - 要分析的动作
   * @returns 带有风险级别和详细信息的分析结果
   */
  analyze(action: ActionEvent): Promise<SecurityAnalysisResult> | SecurityAnalysisResult;
}

/**
 * 基于模式的安全分析器。
 * 使用正则表达式模式来识别有风险的命令和操作。
 */
export class PatternBasedAnalyzer implements SecurityAnalyzer {
  readonly type = 'pattern_based';

  // 高风险操作模式
  private readonly highRiskPatterns: RegExp[] = [
    /\brm\s+-rf?\s+[/~]/i, // rm -rf with absolute/home paths
    /\bsudo\b/i, // 须藤命令
    /\bchmod\s+777\b/i, // chmod 777
    /\b(curl|wget).*\|\s*(sh|bash)\b/i, // 管道下载
    /\bdd\s+.*of=/i, // dd命令
    /\bmkfs\b/i, // 文件系统创建
    /\b(shutdown|reboot|halt)\b/i, // 系统控制
    /\bkill\s+-9\s+1\b/i, // 杀死初始化
    />(\/dev\/(sd|hd|nvme)|\/etc\/)/i, // 写入设备/等
    /\bpasswd\b/i, // 密码更改
    /\buseradd\b|\buserdel\b/i, // 用户管理
  ];

  // 中等风险操作模式
  private readonly mediumRiskPatterns: RegExp[] = [
    /\brm\b/i, // 任何 rm 命令
    /\bgit\s+push\b/i, // git push
    /\bgit\s+reset\s+--hard\b/i, // git reset hard
    /\bnpm\s+(publish|unpublish)\b/i, // npm publish
    /\bpip\s+install\b/i, // pip install
    /\bcurl\b|\bwget\b/i, // 网络下载
    /\bchmod\b/i, // permission changes
    /\bchown\b/i, // 所有权变更
    /\benv\b.*=.*\bexport\b/i, // 环境修改
    /\b(docker|kubectl)\b/i, // 容器/k8s 命令
  ];

  // 敏感文件访问模式
  private readonly sensitivePathPatterns: RegExp[] = [
    /\/etc\/(passwd|shadow|sudoers)/i,
    /~?\/.ssh\//i,
    /~?\/.aws\//i,
    /~?\/.gnupg\//i,
    /\.env\b/i,
    /\.(pem|key|crt|cer)\b/i,
    /secrets?\.(json|ya?ml|txt)\b/i,
    /credentials?\b/i,
  ];

  analyze(action: ActionEvent): SecurityAnalysisResult {
    const concerns: string[] = [];
    let highestRisk: RiskLevel = 'low';

    // 获取要分析的命令或内容
    const contentToAnalyze = this.getContentToAnalyze(action);

    // 检查高风险模式
    for (const pattern of this.highRiskPatterns) {
      if (pattern.test(contentToAnalyze)) {
        concerns.push(`High-risk pattern detected: ${pattern.source}`);
        highestRisk = 'high';
      }
    }

    // 检查中等风险模式（仅当风险还不是很高时）
    if (highestRisk !== 'high') {
      for (const pattern of this.mediumRiskPatterns) {
        if (pattern.test(contentToAnalyze)) {
          concerns.push(`Medium-risk pattern detected: ${pattern.source}`);
          if (highestRisk === 'low') {
            highestRisk = 'medium';
          }
        }
      }
    }

    // 检查敏感文件访问
    for (const pattern of this.sensitivePathPatterns) {
      if (pattern.test(contentToAnalyze)) {
        concerns.push(`Sensitive file access detected: ${pattern.source}`);
        if (highestRisk === 'low') {
          highestRisk = 'medium';
        }
      }
    }

    return {
      riskLevel: highestRisk,
      requiresConfirmation: highestRisk !== 'low',
      explanation:
        concerns.length > 0
          ? `Found ${concerns.length} potential security concern(s)`
          : 'No significant risks detected',
      concerns,
    };
  }

  private getContentToAnalyze(action: ActionEvent): string {
    // 结合相关字段进行分析
    const parts: string[] = [action.tool_name];

    if (action.action) {
      const actionData = action.action as unknown as Record<string, unknown>;
      // 对于 execute_command 工具
      if ('command' in actionData) {
        parts.push(String(actionData.command));
      }
      // 对于 write_file 工具
      if ('path' in actionData) {
        parts.push(String(actionData.path));
      }
      if ('content' in actionData) {
        parts.push(String(actionData.content));
      }
      // 通用：将动作字符串化
      parts.push(JSON.stringify(action.action));
    }

    return parts.join(' ');
  }
}

/**
 * 基于白名单的安全分析器。
 * 只允许明确批准的工具和模式。
 */
export class AllowlistAnalyzer implements SecurityAnalyzer {
  readonly type = 'allowlist';
  private allowedTools: Set<string>;
  private allowedPatterns: RegExp[];

  constructor(allowedTools: string[], allowedPatterns: RegExp[] = []) {
    this.allowedTools = new Set(allowedTools);
    this.allowedPatterns = allowedPatterns;
  }

  analyze(action: ActionEvent): SecurityAnalysisResult {
    // 检查工具是否允许
    if (this.allowedTools.has(action.tool_name)) {
      return {
        riskLevel: 'low',
        requiresConfirmation: false,
        explanation: `Tool '${action.tool_name}' is in the allowlist`,
      };
    }

    // 检查操作是否匹配允许的模式
    const actionStr = JSON.stringify(action.action);
    for (const pattern of this.allowedPatterns) {
      if (pattern.test(actionStr)) {
        return {
          riskLevel: 'low',
          requiresConfirmation: false,
          explanation: `Action matches allowed pattern`,
        };
      }
    }

    // 不在允许名单中
    return {
      riskLevel: 'high',
      requiresConfirmation: true,
      explanation: `Tool '${action.tool_name}' is not in the allowlist`,
      concerns: ['Unlisted tool or action'],
    };
  }
}

/**
 * 无操作分析器 - 将所有内容标记为低风险。
 * 仅用于开发/测试。
 */
export class NoOpAnalyzer implements SecurityAnalyzer {
  readonly type = 'noop';

  analyze(_action: ActionEvent): SecurityAnalysisResult {
    return {
      riskLevel: 'low',
      requiresConfirmation: false,
      explanation: 'No security analysis performed',
    };
  }
}

/**
 * 复合分析仪 - 组合多个分析仪。
 * 返回所有分析器的最高风险级别。
 */
export class CompositeAnalyzer implements SecurityAnalyzer {
  readonly type = 'composite';
  private analyzers: SecurityAnalyzer[];

  constructor(analyzers: SecurityAnalyzer[]) {
    this.analyzers = analyzers;
  }

  async analyze(action: ActionEvent): Promise<SecurityAnalysisResult> {
    const results = await Promise.all(this.analyzers.map((a) => a.analyze(action)));

    // 综合结果 - 风险最高者获胜
    let highestRisk: RiskLevel = 'low';
    const allConcerns: string[] = [];
    const explanations: string[] = [];

    for (const result of results) {
      if (riskLevelToNumeric(result.riskLevel) > riskLevelToNumeric(highestRisk)) {
        highestRisk = result.riskLevel;
      }
      if (result.concerns) {
        allConcerns.push(...result.concerns);
      }
      if (result.explanation) {
        explanations.push(result.explanation);
      }
    }

    return {
      riskLevel: highestRisk,
      requiresConfirmation: highestRisk !== 'low',
      explanation: explanations.join('; '),
      concerns: allConcerns.length > 0 ? allConcerns : undefined,
    };
  }
}

/**
 * 从类型字符串创建安全分析器。
 */
export function createSecurityAnalyzer(type: string, options?: unknown): SecurityAnalyzer {
  switch (type) {
    case 'pattern_based':
      return new PatternBasedAnalyzer();
    case 'allowlist': {
      const opts = options as { tools?: string[]; patterns?: RegExp[] } | undefined;
      return new AllowlistAnalyzer(opts?.tools || [], opts?.patterns || []);
    }
    case 'noop':
      return new NoOpAnalyzer();
    default:
      return new PatternBasedAnalyzer();
  }
}
