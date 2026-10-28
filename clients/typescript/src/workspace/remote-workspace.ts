/**
 * 用于执行命令和文件操作的远程工作区实现
 *
 * 这通过连接到远程 OpenHands 来实现 IWorkspace 接口
 * Agent Server. 它反映了 Python SDK 的 RemoteWorkspace 类。
 */

import { BashClient } from '../client/bash-client';
import type { HttpClient } from '../client/http-client';
import { createRuntimeHttpClients } from '../client/runtime-transport';
import {
  CommandResult,
  FileOperationResult,
  FileDownloadResult,
  GitChange,
  GitDiff,
} from '../models/workspace';
import { ConversationID } from '../types/base';
import { IWorkspace, BaseWorkspaceOptions, GitQueryOptions } from './base';

/**
 * 用于创建 RemoteWorkspace 实例的选项。
 */
export interface RemoteWorkspaceOptions extends BaseWorkspaceOptions {
  /** 远程主机URL为工作区(e.g.,' http://localhost:8000' )*/
  host: string;
  /** 拥有对话。 在对话存在之前省略以独立使用。*/
  conversationId?: string;
  /** API 用于与远程主机进行身份验证的密钥（可选）*/
  apiKey?: string;
}

/**
 * 连接到 OpenHands Agent Server 的远程工作区实现。
 *
 * RemoteWorkspace 提供对远程运行的沙盒环境的访问
 * OpenHands Agent Server. 这是生产部署的推荐方法
 * 因为它提供了更好的隔离和安全性。
 */
export class RemoteWorkspace implements IWorkspace {
  public readonly host: string;
  public readonly workingDir: string;
  public readonly apiKey?: string;
  public readonly client: HttpClient;
  public readonly conversationId?: string;
  private readonly serverClient: HttpClient;
  public readonly bash: BashClient;

  constructor(options: RemoteWorkspaceOptions) {
    this.host = options.host.replace(/\/$/, '');
    this.workingDir = options.workingDir;
    this.apiKey = options.apiKey;
    this.conversationId = options.conversationId;

    const { serverClient, runtimeClient } = createRuntimeHttpClients(options);
    this.serverClient = serverClient;
    this.client = runtimeClient;

    this.bash = new BashClient({
      host: this.host,
      conversationId: this.conversationId,
      ...(this.apiKey ? { apiKey: this.apiKey } : {}),
    });
  }

  /**
   * 启动工作区静态资产会话进行对话并返回
   * 其工作区文件由 base URL 提供。
   *
   * 调用 `POST /api/auth/workspace-session` 来交换工作区的
   * 为 HttpOnly cookie 配置 `X-Session-API-Key`
   * (`oh_workspace_session_key`) 范围为 `/api/conversations`。 随着
   * cookie 设置，浏览器可以直接嵌入工作区工件
   * `<iframe src>`、`<img src>` 或顶级导航，无需
   * 附加自定义 `X-Session-API-Key` 标头 - 他们无法执行此操作
   * 这些请求类型。
   *
   * 获取是用 `credentials: 'include'` 进行的，因此浏览器会持续存在
   * 即使 Agent Server 生活在不同的环境中，`Set-Cookie` 也会做出响应
   * 源自嵌入页面 (e.g. 画布+`agent-{id}.example.com`）。
   *
   * 这是故意的工作区级方法而不是
   * 会话级别一：静态资产服务器位于智能体主机上
   * 和消费者（e.g. 智能体-canvas）经常想要嵌入工作区文件
   * 在他们构建完整的 `RemoteConversation` 之前 - 他们只需要
   * 对话 ID。
   *
   * @param conversationId 其工作区文件应该是的对话
   *                       从返回的 URL 送达。
   * @returns 工作区静态文件服务器的基 URL，包括
   *          尾部斜杠 (e.g. `https://host/api/conversations/{id}/workspace/`),
   *          适合加入相对路径。
   */
  async startWorkspaceSession(conversationId: ConversationID): Promise<string> {
    if (this.conversationId !== undefined && this.conversationId !== conversationId) {
      throw new Error('Workspace session must belong to the selected runtime');
    }
    await this.serverClient.post('/api/auth/workspace-session', undefined, {
      credentials: 'include',
    });
    return `${this.host}/api/conversations/${encodeURIComponent(conversationId)}/workspace/`;
  }

  async deleteWorkspaceSession(): Promise<void> {
    await this.serverClient.delete('/api/auth/workspace-session', {
      credentials: 'include',
      acceptableStatusCodes: new Set([204]),
    });
  }

  async executeCommand(
    command: string,
    cwd?: string,
    timeout: number = 30.0
  ): Promise<CommandResult> {
    const payload: Record<string, unknown> = {
      command,
      timeout: Math.floor(timeout),
    };

    if (cwd) {
      payload.cwd = cwd;
    }

    const response = await this.client.post('/api/bash/execute_bash_command', payload, {
      timeout: (timeout + 10) * 1000,
    });

    const bashOutput = response.data as {
      exit_code?: number | null;
      stdout?: string | null;
      stderr?: string | null;
    };

    return {
      command,
      // 缺少退出代码意味着该命令未报告退出代码； 永远不要把它当作成功。
      //
      exit_code: bashOutput.exit_code ?? -1,
      stdout: bashOutput.stdout || '',
      stderr: bashOutput.stderr || '',
      timeout_occurred: false,
    };
  }

  async fileUpload(
    content: string | Blob | File,
    destinationPath: string,
    fileName?: string
  ): Promise<FileOperationResult> {
    const formData = new FormData();

    let blob: Blob;
    let finalFileName: string;

    if (content instanceof File) {
      blob = content;
      finalFileName = fileName || content.name;
    } else if (content instanceof Blob) {
      blob = content;
      finalFileName = fileName || 'blob-file';
    } else {
      blob = new Blob([content], { type: 'text/plain' });
      finalFileName = fileName || 'text-file.txt';
    }

    formData.append('file', blob, finalFileName);

    const response = await this.client.request({
      method: 'POST',
      url: '/api/file/upload',
      params: { path: destinationPath },
      data: formData,
      timeout: 60000,
    });

    const resultData = response.data as { success?: boolean; file_size?: number; error?: string };

    return {
      success: resultData.success ?? true,
      source_path: finalFileName,
      destination_path: destinationPath,
      file_size: resultData.file_size,
      error: resultData.error,
    };
  }

  async fileDownload(sourcePath: string): Promise<FileDownloadResult> {
    const response = await this.client.get('/api/file/download', {
      params: { path: sourcePath },
      timeout: 60000,
    });

    let content: string | Blob;
    let fileSize: number;

    if (typeof response.data === 'string') {
      content = response.data;
      fileSize = new Blob([response.data]).size;
    } else if (response.data instanceof ArrayBuffer) {
      content = new Blob([response.data]);
      fileSize = response.data.byteLength;
    } else if (response.data instanceof Blob) {
      content = response.data;
      fileSize = response.data.size;
    } else {
      const stringData = JSON.stringify(response.data);
      content = stringData;
      fileSize = new Blob([stringData]).size;
    }

    return {
      success: true,
      source_path: sourcePath,
      content,
      file_size: fileSize,
    };
  }

  async gitChanges(path: string, options: GitQueryOptions = {}): Promise<GitChange[]> {
    const params: Record<string, string> = { path };
    if (options.ref !== undefined) {
      params.ref = options.ref;
    }
    try {
      const response = await this.client.get<GitChange[]>('/api/git/changes', {
        params,
      });
      return response.data;
    } catch (error) {
      throw new Error(
        `Failed to get git changes: ${error instanceof Error ? error.message : String(error)}`,
        { cause: error }
      );
    }
  }

  async gitDiff(path: string, options: GitQueryOptions = {}): Promise<GitDiff> {
    const params: Record<string, string> = { path };
    if (options.ref !== undefined) {
      params.ref = options.ref;
    }
    try {
      const response = await this.client.get<GitDiff>('/api/git/diff', {
        params,
      });
      return response.data;
    } catch (error) {
      throw new Error(
        `Failed to get git diff: ${error instanceof Error ? error.message : String(error)}`,
        { cause: error }
      );
    }
  }

  /**
   * 将文本内容作为文件上传的便捷方法
   */
  async uploadText(
    text: string,
    destinationPath: string,
    fileName?: string
  ): Promise<FileOperationResult> {
    return this.fileUpload(text, destinationPath, fileName);
  }

  /**
   * 上传 File 对象的便捷方法（从文件输入）
   */
  async uploadFileObject(file: File, destinationPath: string): Promise<FileOperationResult> {
    return this.fileUpload(file, destinationPath);
  }

  /**
   * 将文件内容下载为文本的便捷方法
   */
  async downloadAsText(sourcePath: string): Promise<string> {
    const result = await this.fileDownload(sourcePath);
    if (!result.success) {
      throw new Error(result.error || 'Download failed');
    }

    if (typeof result.content === 'string') {
      return result.content;
    } else if (result.content instanceof Blob) {
      return await result.content.text();
    }

    return '';
  }

  /**
   * 将文件内容下载为 Blob 的便捷方法
   */
  async downloadAsBlob(sourcePath: string): Promise<Blob> {
    const result = await this.fileDownload(sourcePath);
    if (!result.success) {
      throw new Error(result.error || 'Download failed');
    }

    if (result.content instanceof Blob) {
      return result.content;
    } else if (typeof result.content === 'string') {
      return new Blob([result.content], { type: 'text/plain' });
    }

    return new Blob();
  }

  /**
   * 触发浏览器下载文件的便捷方法
   * @throws 非浏览器环境中的错误； 使用 downloadAsBlob() 或 downloadAsText() 代替。
   */
  async downloadAndSave(sourcePath: string, saveAsFileName?: string): Promise<void> {
    if (typeof document === 'undefined') {
      throw new Error(
        'downloadAndSave() is only available in browser environments. ' +
          'Use downloadAsBlob() or downloadAsText() in Node.js.'
      );
    }

    const blob = await this.downloadAsBlob(sourcePath);

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = saveAsFileName || sourcePath.split('/').pop() || 'download';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  close(): void {
    this.bash.close();
    this.client.close();
  }
}
