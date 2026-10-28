/**
 * deriveSwitchPlan — 决定配置文件切换是否可以的纯助手
 * 实时发生（对话中），需要新的对话，或者已经
 * 当前。
 *
 * 存在于自己的模块中，因此画布可以导入它而无需拉入 HTTP
 * 客户端代码，因此无需任何 I/O 即可对其进行单元测试。
 */

import type { ACPProviderInfo } from '../models/acp';
import type { ACPAgentProfile, OpenHandsAgentProfile } from '../models/agent-profile';

export type SwitchPlan =
  | { action: 'current' }
  | { action: 'switch-live'; mutableFields: string[] }
  | { action: 'start-new'; reason: string }
  | { action: 'disabled'; reason: string };

// 从内容比较中排除的字段（身份/出处字段）。
const IDENTITY_FIELDS = new Set(['id', 'name', 'revision', 'schema_version', 'agent_kind']);

/**
 * 确定性序列化，对象键递归排序。 两个值
 * 内容相同但键不同 *插入顺序* 序列化相等
 * （数组顺序仍然很重要）。 通过存储往返的快照
 * 不能仅仅因为其键被重新排序而看起来“发生了变化”。
 */
function stableStringify(value: unknown): string {
  if (value === undefined) return 'undefined';
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  const obj = value as Record<string, unknown>;
  const entries = Object.keys(obj)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(obj[key])}`);
  return `{${entries.join(',')}}`;
}

function changedNonMutableFields(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
  mutable: Set<string>
): string[] {
  const allKeys = new Set([...Object.keys(a), ...Object.keys(b)]);
  const changed: string[] = [];
  for (const key of allKeys) {
    if (IDENTITY_FIELDS.has(key) || mutable.has(key)) continue;
    if (stableStringify(a[key]) !== stableStringify(b[key])) {
      changed.push(key);
    }
  }
  return changed;
}

/**
 * 计算一个 {@link SwitchPlan} 以将正在运行的对话从
 * 当前启动的个人资料内容 (`snapshot`) 至 `targetProfile`。
 *
 * @param snapshot 启动当前配置文件的完整内容
 *                      对话，或 `null`/`undefined`（当没有个人资料时）
 *                      在对话开始时使用。
 * @param targetProfile 用户想要应用的配置文件。
 * @param providerInfo ACP *current* 智能体的提供者信息（来自
 *                      {@link getAcpProvider}），或 `null` 为 OpenHands 或
 *                      自定义 ACP 服务器。 用于检查
 *                      `supports_runtime_model_switch`.
 *
 * 决策规则（镜像史诗#3713）：
 * - **当前**：`snapshot`内容与`targetProfile`内容相同。
 * - **switch-live**：可以在不重新启动对话的情况下进行转换：
 *   - OpenHands → OpenHands：仅 `llm_profile_ref` 不同。
 *   - ACP → ACP：与`acp_server`相同，仅`acp_model`不同，并且
 *     提供者声明`supports_runtime_model_switch`。
 * - **开始新**：可能，但需要重新对话。
 * - **禁用**：没有前进的道路（e.g。 unknown 智能体 kind).
 */
export function deriveSwitchPlan(
  snapshot: OpenHandsAgentProfile | ACPAgentProfile | null | undefined,
  targetProfile: OpenHandsAgentProfile | ACPAgentProfile,
  providerInfo: ACPProviderInfo | null
): SwitchPlan {
  if (!snapshot) {
    return { action: 'start-new', reason: 'no launched profile' };
  }

  // 快速路径：完全相同的配置文件版本已在运行。
  if (snapshot.id === targetProfile.id && snapshot.revision === targetProfile.revision) {
    return { action: 'current' };
  }

  // 善良的改变：从来没有实时切换。
  if (snapshot.agent_kind !== targetProfile.agent_kind) {
    return { action: 'start-new', reason: 'agent kind changed' };
  }

  const snapshotRaw = snapshot as unknown as Record<string, unknown>;
  const targetRaw = targetProfile as unknown as Record<string, unknown>;

  if (snapshot.agent_kind === 'openhands') {
    // OpenHands → OpenHands：仅当 llm_profile_ref 不同时才存活。
    const nonMutable = changedNonMutableFields(
      snapshotRaw,
      targetRaw,
      new Set(['llm_profile_ref'])
    );
    if (nonMutable.length === 0) {
      const llmDiffers =
        snapshot.llm_profile_ref !== (targetProfile as OpenHandsAgentProfile).llm_profile_ref;
      if (!llmDiffers) {
        return { action: 'current' };
      }
      return { action: 'switch-live', mutableFields: ['llm_profile_ref'] };
    }
    return { action: 'start-new', reason: `fields changed: ${nonMutable.join(', ')}` };
  }

  if (snapshot.agent_kind === 'acp') {
    const snapshotAcp = snapshot as ACPAgentProfile;
    const targetAcp = targetProfile as ACPAgentProfile;

    // 不同的 ACP 提供商 → 必须重新启动。
    if (snapshotAcp.acp_server !== targetAcp.acp_server) {
      return { action: 'start-new', reason: 'ACP provider changed' };
    }

    // ACP→ACP（同一提供商）：acp_model是唯一可以实时切换的字段。 任何其他内容更改都会强制进行新的对话。
    //
    const nonMutable = changedNonMutableFields(snapshotRaw, targetRaw, new Set(['acp_model']));
    if (nonMutable.length > 0) {
      return { action: 'start-new', reason: `fields changed: ${nonMutable.join(', ')}` };
    }

    // 相同的模型（没有其他变化） → 已经是最新的，无论提供商的能力如何。 在运行时切换门之前检查此项，这样未更改的配置文件就不会被误认为是切换。
    //
    const modelDiffers = snapshotAcp.acp_model !== targetAcp.acp_model;
    if (!modelDiffers) {
      return { action: 'current' };
    }

    // 型号不同 → 仅当提供商支持时才进行实时切换。
    if (!providerInfo?.supports_runtime_model_switch) {
      return {
        action: 'start-new',
        reason: 'provider does not support runtime model switch',
      };
    }
    return { action: 'switch-live', mutableFields: ['acp_model'] };
  }

  // 使用有效的 AgentProfile 联合无法访问，但可以防止未来的变体。
  const exhaustiveCheck: never = snapshot;
  return {
    action: 'disabled',
    reason: `unknown agent_kind: ${(exhaustiveCheck as { agent_kind: string }).agent_kind}`,
  };
}
