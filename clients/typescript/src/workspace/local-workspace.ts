/**
 * 本地工作区存根实现。
 *
 * 这是用于本地执行的 IWorkspace 接口的存根实现。
 * 所有方法都会抛出描述性错误，将用户引导至 RemoteWorkspace。
 *
 * 这反映了 Python SDK 的 LocalWorkspace 类架构。
 */

import {
  CommandResult,
  FileOperationResult,
  FileDownloadResult,
  GitChange,
  GitDiff,
} from '../models/workspace';
import { IWorkspace, BaseWorkspaceOptions, GitQueryOptions } from './base';

/**
 * 用于创建 LocalWorkspace 实例的选项。
 */
export type LocalWorkspaceOptions = BaseWorkspaceOptions;

/**
 * 调用 LocalWorkspace 方法时抛出错误。
 */
class LocalWorkspaceNotSupportedError extends Error {
  constructor(method: string) {
    super(`LocalWorkspace.${method}() is not implemented. ` + `Use RemoteWorkspace instead.`);
    this.name = 'LocalWorkspaceNotSupportedError';
  }
}

/**
 * 本地工作区存根。
 *
 * 这是一个占位符实现，当方法
 * 被称为。 使用 RemoteWorkspace 来实现实际的工作区功能。
 *
 * ```TypeScript
 * 常量工作区 = 新 RemoteWorkspace({
 *   主持人：' http://localhost:8000',
 *   workingDir: '/workspace'
 * });
 * const 结果 = wait workspace.executeCommand('ls -la');
 * ```
 */
export class LocalWorkspace implements IWorkspace {
  public readonly workingDir: string;

  constructor(options: LocalWorkspaceOptions) {
    this.workingDir = options.workingDir;
  }

  /**
   * 在本地执行 bash 命令。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async executeCommand(_command: string, _cwd?: string, _timeout?: number): Promise<CommandResult> {
    throw new LocalWorkspaceNotSupportedError('executeCommand');
  }

  /**
   * 将内容写入工作区中的文件。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async fileUpload(
    _content: string | Blob | File,
    _destinationPath: string,
    _fileName?: string
  ): Promise<FileOperationResult> {
    throw new LocalWorkspaceNotSupportedError('fileUpload');
  }

  /**
   * 从工作区读取一个文件。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async fileDownload(_sourcePath: string): Promise<FileDownloadResult> {
    throw new LocalWorkspaceNotSupportedError('fileDownload');
  }

  /**
   * 获取存储库的 git 更改。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async gitChanges(_repoPath: string, _options?: GitQueryOptions): Promise<GitChange[]> {
    throw new LocalWorkspaceNotSupportedError('gitChanges');
  }

  /**
   * 获取存储库的 git diff。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async gitDiff(_repoPath: string, _options?: GitQueryOptions): Promise<GitDiff> {
    throw new LocalWorkspaceNotSupportedError('gitDiff');
  }

  /**
   * 将文本内容写入文件的便捷方法。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async uploadText(
    _text: string,
    _destinationPath: string,
    _fileName?: string
  ): Promise<FileOperationResult> {
    throw new LocalWorkspaceNotSupportedError('uploadText');
  }

  /**
   * 上传 File 对象的便捷方法。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async uploadFileObject(_file: File, _destinationPath: string): Promise<FileOperationResult> {
    throw new LocalWorkspaceNotSupportedError('uploadFileObject');
  }

  /**
   * 将文件内容下载为文本的便捷方法。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async downloadAsText(_sourcePath: string): Promise<string> {
    throw new LocalWorkspaceNotSupportedError('downloadAsText');
  }

  /**
   * 将文件内容下载为 Blob 的便捷方法。
   *
   * @throws LocalWorkspaceNotSupportedError - 总是抛出 - 未实现
   */
  async downloadAsBlob(_sourcePath: string): Promise<Blob> {
    throw new LocalWorkspaceNotSupportedError('downloadAsBlob');
  }

  /**
   * 关闭/清理工作区。
   *
   * 对于存根实现来说，这是一个空操作。
   */
  close(): void {
    // 存根实现无操作
  }
}
