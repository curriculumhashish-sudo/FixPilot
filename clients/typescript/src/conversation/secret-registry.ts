/**
 * 机密注册表对话
 *
 * 管理机密并在需要时将它们注入命令中。
 * 在输出中提供机密屏蔽以防止意外暴露。
 * 这反映了 Python SDK 的 SecretRegistry 类。
 */

import { SecretValue } from '../types/base';

// 重新导出，以便该模块的现有使用者仍然可以找到该类型
export type { SecretValue } from '../types/base';

/**
 * 机密来源类型
 */
export type SecretSourceKind = 'static' | 'callable';

/**
 * 机密源的基本接口
 */
export interface SecretSource {
  kind: SecretSourceKind;
  getValue(): string | null;
}

/**
 * Static 机密 source - 存储固定值
 */
export class StaticSecretSource implements SecretSource {
  readonly kind: SecretSourceKind = 'static';
  private value: string;

  constructor(value: string) {
    this.value = value;
  }

  getValue(): string {
    return this.value;
  }
}

/**
 * Callable 机密源 - 计算函数以获取值
 */
export class CallableSecretSource implements SecretSource {
  readonly kind: SecretSourceKind = 'callable';
  private getter: () => string;

  constructor(getter: () => string) {
    this.getter = getter;
  }

  getValue(): string | null {
    try {
      return this.getter();
    } catch {
      return null;
    }
  }
}

/**
 * 将 SecretValue 包裹成 SecretSource
 */
function wrapSecret(value: SecretValue): SecretSource {
  if (typeof value === 'function') {
    return new CallableSecretSource(value);
  }
  return new StaticSecretSource(value);
}

/**
 * 管理机密并在需要时将它们注入到 bash 命令中。
 *
 * 机密注册表存储机密键到 SecretSources 的映射
 * 检索实际的机密值。 当 bash 命令即将执行时
 * 执行时，它会扫描命令中的任何机密键并提供
 * corresponding 环境变量。
 *
 * 此外，它还跟踪最新导出的值以实现一致的屏蔽
 * 即使可调用机密在后续调用中失败。
 *
 * 示例：
 * ```TypeScript
 * const 注册表 = new SecretRegistry();
 * registry.updateSecrets({
 *   'API_KEY': 'sk-机密-key',
 *   'DYNAMIC_TOKEN': () => getToken(),
 * });
 *
 * // 获取命令的环境变量
 * const envVars = registry.getSecretsAsEnvVars('curl -H "授权：承载 $API_KEY" ...');
 *
 * // 输出中的掩码机密
 * const maskedOutput = registry.maskSecretsInOutput('响应 sk-机密-key 可见');
 * // 返回：“<secret-hidden> 可见的响应”
 * ```
 */
export class SecretRegistry {
  /** 机密键到机密源的映射*/
  private secretSources: Map<string, SecretSource> = new Map();

  /** 缓存成功导出的屏蔽值*/
  private exportedValues: Map<string, string> = new Map();

  /**
   * 在注册表中添加或更新机密。
   *
   * @param 机密 - 字典将机密键映射到值或可调用函数
   */
  updateSecrets(secrets: Record<string, SecretValue>): void {
    for (const [key, value] of Object.entries(secrets)) {
      this.secretSources.set(key, wrapSecret(value));
    }
  }

  /**
   * 从注册表中删除机密。
   *
   * @param key - 要删除的机密键
   */
  removeSecret(key: string): void {
    this.secretSources.delete(key);
    this.exportedValues.delete(key);
  }

  /**
   * 从注册表中清除所有机密。
   */
  clearSecrets(): void {
    this.secretSources.clear();
    this.exportedValues.clear();
  }

  /**
   * 获取注册数量机密。
   */
  get size(): number {
    return this.secretSources.size;
  }

  /**
   * 获取所有已注册的机密键。
   */
  get keys(): string[] {
    return Array.from(this.secretSources.keys());
  }

  /**
   * 查找给定文本中提到的所有机密键。
   * 使用不区分大小写的匹配。
   *
   * @param text - 用于搜索机密键的文本
   * @returns 在文本中找到的机密个键的集合
   */
  findSecretsInText(text: string): Set<string> {
    const foundKeys = new Set<string>();
    const lowerText = text.toLowerCase();

    for (const key of this.secretSources.keys()) {
      if (lowerText.includes(key.toLowerCase())) {
        foundKeys.add(key);
      }
    }

    return foundKeys;
  }

  /**
   * 获取应导出为命令环境变量的机密。
   *
   * @param command - 用于检查机密引用的 bash 命令
   * @returns 要导出的环境变量字典（键 -> 值）
   */
  getSecretsAsEnvVars(command: string): Record<string, string> {
    const foundSecrets = this.findSecretsInText(command);

    if (foundSecrets.size === 0) {
      return {};
    }

    const envVars: Record<string, string> = {};

    for (const key of foundSecrets) {
      const source = this.secretSources.get(key);
      if (!source) continue;

      const value = source.getValue();
      if (value) {
        envVars[key] = value;
        this.exportedValues.set(key, value);
      }
    }

    return envVars;
  }

  /**
   * 给定文本中的掩码机密值。
   *
   * 此方法使用当前导出的值来确保全面屏蔽。
   * 它将所有已知的机密值替换为“<secret-hidden>”。
   *
   * @param text - 要屏蔽机密的文本
   * @returns 将机密值替换为 <secret-hidden> 的文本
   */
  maskSecretsInOutput(text: string): string {
    if (!text) {
      return text;
    }

    let maskedText = text;

    // 使用当前导出的值进行掩码
    for (const value of this.exportedValues.values()) {
      if (value) {
        // 使用全局替换
        maskedText = maskedText.split(value).join('<secret-hidden>');
      }
    }

    // 还尝试从源获取新值（如果它们尚未导出）
    for (const [key, source] of this.secretSources) {
      try {
        const value = source.getValue();
        if (value && !this.exportedValues.has(key)) {
          maskedText = maskedText.split(value).join('<secret-hidden>');
        }
      } catch {
        // 尝试屏蔽时忽略错误 - 我们将使用缓存值
      }
    }

    return maskedText;
  }

  /**
   * 检查是否注册了特定的机密键。
   *
   * @param key - 要检查的机密键
   * @returns True 如果密钥已注册
   */
  hasSecret(key: string): boolean {
    return this.secretSources.has(key);
  }

  /**
   * 序列化持久化的注册表状态。
   * 注意：Callable 机密不能为已序列化，将被省略。
   * 为了安全起见，机密值默认为已脱敏。
   *
   * @param exposeSecrets - 如果是 True，则包含实际的机密值（谨慎使用！）
   * @returns 已序列化注册表状态
   */
  serialize(exposeSecrets: boolean = false): Record<string, string | null> {
    const result: Record<string, string | null> = {};

    for (const [key, source] of this.secretSources) {
      if (source.kind === 'callable') {
        // 可调用机密不能为已序列化
        result[key] = null;
      } else if (exposeSecrets) {
        result[key] = source.getValue();
      } else {
        result[key] = '**********';
      }
    }

    return result;
  }

  /**
   * 从已序列化状态恢复机密。
   * 只能恢复静态机密。
   *
   * @param state - 之前的已序列化状态
   */
  deserialize(state: Record<string, string | null>): void {
    for (const [key, value] of Object.entries(state)) {
      if (value !== null && value !== '**********') {
        this.secretSources.set(key, new StaticSecretSource(value));
      }
    }
  }
}
