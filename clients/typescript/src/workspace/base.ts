/**
 * 基本工作区接口和类型
 *
 * 该文件定义了所有工作区实现必须遵循的抽象接口。
 * 它反映了 Python SDK 的 BaseWorkspace 模式。
 */

import {
  CommandResult,
  FileOperationResult,
  FileDownloadResult,
  GitChange,
  GitDiff,
} from '../models/workspace';

/**
 * 所有工作区类型共享的基本工作区选项
 */
export interface BaseWorkspaceOptions {
  workingDir: string;
}

/**
 * git 查询的可选设置 (`gitChanges` / `gitDiff`)。
 */
export interface GitQueryOptions {
  /**
   * Git ref 来进行比较。 通过 `'HEAD'` 获得 `git status` 式结果
   * （工作树+索引与最新提交），或差异的提交哈希
   * 反对具体修订。 省略时，服务器会自动检测
   * 上游/默认分支（历史默认行为）。
   */
  ref?: string;
}

/**
 * 工作区实现的抽象接口。
 *
 * 工作区提供一个沙盒环境， 智能体可以执行命令
 * 读/写文件，并执行其他操作。 所有工作区实施
 * 支持相同的接口以实现互操作。
 *
 * 这反映了 Python SDK 的 BaseWorkspace 抽象类。
 */
export interface IWorkspace {
  /** 智能体操作的工作目录*/
  readonly workingDir: string;

  /**
   * 在工作区中执行bash命令。
   *
   * @param command - 要执行的 bash 命令
   * @param cwd - 工作目录表示命令（可选）
   * @param 超时 - 超时以秒为单位（默认为 30.0）
   * @returns CommandResult 包含 stdout、stderr、exit_code 和其他元数据
   */
  executeCommand(command: string, cwd?: string, timeout?: number): Promise<CommandResult>;

  /**
   * 上传内容到工作区。
   *
   * @param content - 要上传的内容（字符串、Blob 或文件）
   * @param destinationPath - 内容应上传的路径
   * @param fileName - 上传内容的可选文件名
   * @returns FileOperationResult 包含成功状态和元数据
   */
  fileUpload(
    content: string | Blob | File,
    destinationPath: string,
    fileName?: string
  ): Promise<FileOperationResult>;

  /**
   * 从工作区下载文件。
   *
   * @param sourcePath - 工作区中源文件的路径
   * @returnsFileDownloadResult 包含文件内容
   */
  fileDownload(sourcePath: string): Promise<FileDownloadResult>;

  /**
   * 获取给定路径下存储库的 git 更改。
   *
   * @param path - git 存储库的路径
   * @param options - 可选设置。
   * @param options.ref - 可选的 git ref 来比较 (e.g. `'HEAD'`
   *   对于 `git status` 样式的更改，或提交哈希）。 当省略时，
   *   服务器自动检测上游/默认分支。
   * @returns GitChange 对象数组
   */
  gitChanges(path: string, options?: GitQueryOptions): Promise<GitChange[]>;

  /**
   * 获取给定路径下存储库的 git diff。
   *
   * @param path - git 存储库的路径
   * @param options - 可选设置。
   * @param options.ref - 可选的 git ref 来比较 (e.g. `'HEAD'`
   *   对于 `git status` 样式的差异，或提交哈希）。 当省略时，
   *   服务器自动检测上游/默认分支。
   * @returns GitDiff 包含差异内容的对象
   */
  gitDiff(path: string, options?: GitQueryOptions): Promise<GitDiff>;

  /**
   * 将文本内容作为文件上传的便捷方法。
   *
   * @param text - 要上传的文本内容
   * @param destinationPath - 内容应上传的路径
   * @param fileName - 可选文件名
   */
  uploadText(
    text: string,
    destinationPath: string,
    fileName?: string
  ): Promise<FileOperationResult>;

  /**
   * 上传 File 对象的便捷方法。
   *
   * @param file - 要上传的文件对象
   * @param destinationPath - 文件上传的路径
   */
  uploadFileObject(file: File, destinationPath: string): Promise<FileOperationResult>;

  /**
   * 将文件内容下载为文本的便捷方法。
   *
   * @param sourcePath - 源文件的路径
   * @returns 文件内容作为字符串
   */
  downloadAsText(sourcePath: string): Promise<string>;

  /**
   * 将文件内容下载为 Blob 的便捷方法。
   *
   * @param sourcePath - 源文件的路径
   * @returns 文件内容作为 Blob
   */
  downloadAsBlob(sourcePath: string): Promise<Blob>;

  /**
   * 关闭/清理工作区连接。
   * 对于本地工作区，这通常是无操作。
   * 对于远程工作区，这将关闭 HTTP 客户端连接。
   */
  close(): void;
}

/**
 * 工作区类型的类型鉴别器。
 * 对于运行时类型检查和工厂模式很有用。
 */
export type WorkspaceType = 'local' | 'remote';
