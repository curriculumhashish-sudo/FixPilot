/**
 * 工作区工厂和实用功能
 *
 * 该模块提供了一个方便的工厂模式来创建工作区实例。
 * 它匹配 Python SDK 模式，同时支持本地和远程工作区。
 */

import { IWorkspace, WorkspaceType } from './base';
import { RemoteWorkspace, RemoteWorkspaceOptions } from './remote-workspace';
import { LocalWorkspace, LocalWorkspaceOptions } from './local-workspace';

/**
 * 所有工作区选项的联合类型
 */
export type WorkspaceOptions = RemoteWorkspaceOptions | LocalWorkspaceOptions;

/**
 * 用于创建具有显式类型选择的工作区的选项
 */
export interface CreateWorkspaceOptions {
  type: WorkspaceType;
  options: WorkspaceOptions;
}

/**
 * 输入guard来检查选项是否适用于RemoteWorkspace
 */
function isRemoteWorkspaceOptions(options: WorkspaceOptions): options is RemoteWorkspaceOptions {
  return 'host' in options;
}

/**
 * 工作区类将 RemoteWorkspace 扩展为向后兼容性。
 * 提供与 Python SDK 命名相匹配的更清晰的 API。
 *
 * 对于新代码，请考虑使用 createWorkspace 工厂函数
 * 或者直接实例化 RemoteWorkspace 或 LocalWorkspace。
 *
 * 用途：
 * ```TypeScript
 * // 传统用法（向后兼容）
 * 常量工作区 = 新工作区({
 *   主持人：' http://localhost:8000',
 *   workingDir: '/workspace',
 *   apiKey：“钥匙”
 * });
 * ```
 */
export class Workspace extends RemoteWorkspace {
  constructor(options: RemoteWorkspaceOptions) {
    super(options);
  }
}

/**
 * 工厂函数根据选项创建工作区实例。
 *
 * 这提供了一种统一的方式来创建本地或远程工作区
 * 基于提供的选项。
 *
 * 用途：
 * ```TypeScript
 * // Create a remote 工作区
 * const remoteWorkspace = createWorkspace({
 *   类型：'远程'，
 *   选项：{
 *     主持人：' http://localhost:8000',
 *     workingDir: '/workspace',
 *     apiKey：“钥匙”
 *   }
 * });
 *
 * // 创建本地工作区
 * const localWorkspace = createWorkspace({
 *   类型：'本地'，
 *   选项：{
 *     workingDir: '/path/to/project'
 *   }
 * });
 * ```
 *
 * @param config - 工作区配置，包括类型和选项
 * @returns 实现 IWorkspace 的工作区实例
 */
export function createWorkspace(config: CreateWorkspaceOptions): IWorkspace {
  switch (config.type) {
    case 'remote':
      if (!isRemoteWorkspaceOptions(config.options)) {
        throw new Error('RemoteWorkspace requires host option');
      }
      return new RemoteWorkspace(config.options);

    case 'local':
      return new LocalWorkspace(config.options as LocalWorkspaceOptions);

    default:
      throw new Error(`Unknown workspace type: ${config.type}`);
  }
}

/**
 * 创建一个自动检测选项类型的工作区。
 *
 * 如果选项包含“主机”属性，则创建 RemoteWorkspace。
 * 否则，创建一个 LocalWorkspace。
 *
 * 用途：
 * ```TypeScript
 * // 自动创建 RemoteWorkspace（具有“主机”）
 * 常量远程 = createWorkspaceAuto({
 *   主持人：' http://localhost:8000',
 *   workingDir: '/workspace'
 * });
 *
 * // 自动创建 LocalWorkspace（无“主机”）
 * 常量本地 = createWorkspaceAuto({
 *   workingDir: '/path/to/project'
 * });
 * ```
 *
 * @param options - 工作区选项
 * @returns 实现 IWorkspace 的工作区实例
 */
export function createWorkspaceAuto(options: WorkspaceOptions): IWorkspace {
  if (isRemoteWorkspaceOptions(options)) {
    return new RemoteWorkspace(options);
  }
  return new LocalWorkspace(options as LocalWorkspaceOptions);
}
