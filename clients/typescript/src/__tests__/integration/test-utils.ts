/**
 * 集成测试的效用函数
 */

import * as fs from 'fs';
import * as path from 'path';
import { getServerTestConfig } from './test-config';

/**
 * 等待一个条件变为True，与超时
 */
export async function waitFor(
  condition: () => boolean | Promise<boolean>,
  options: { timeout?: number; interval?: number; message?: string } = {}
): Promise<void> {
  const { timeout = 30000, interval = 100, message = 'Condition not met' } = options;
  const start = Date.now();

  while (Date.now() - start < timeout) {
    if (await condition()) {
      return;
    }
    await sleep(interval);
  }

  throw new Error(`Timeout waiting: ${message}`);
}

/**
 * 休眠给定的毫秒数
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 从主机工作区目录读取文件
 */
export function readWorkspaceFile(relativePath: string): string {
  const config = getServerTestConfig();
  const fullPath = path.join(config.hostWorkspaceDir, relativePath);
  return fs.readFileSync(fullPath, 'utf-8');
}

/**
 * 向主机工作区目录写入文件
 */
export function writeWorkspaceFile(relativePath: string, content: string): void {
  const config = getServerTestConfig();
  const fullPath = path.join(config.hostWorkspaceDir, relativePath);
  const dir = path.dirname(fullPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(fullPath, content, 'utf-8');
}

/**
 * 检查host工作区目录下是否存在文件
 */
export function workspaceFileExists(relativePath: string): boolean {
  const config = getServerTestConfig();
  const fullPath = path.join(config.hostWorkspaceDir, relativePath);
  return fs.existsSync(fullPath);
}

/**
 * 从主机工作区目录中删除文件
 */
export function deleteWorkspaceFile(relativePath: string): void {
  const config = getServerTestConfig();
  const fullPath = path.join(config.hostWorkspaceDir, relativePath);
  if (fs.existsSync(fullPath)) {
    fs.unlinkSync(fullPath);
  }
}

/**
 * 从主机工作区目录中递归删除文件或目录。
 *
 * 从主机（测试运行程序）写入工作区会创建路径
 * 由主机用户拥有，而智能体-服务器容器作为
 * 不同的用户。 如果测试留下主机拥有的目录，例如 `.openhands`
 * 后面，服务器稍后无法对其进行 chmod (e.g. 配置文件激活错误
 * 与“不允许操作”）。 用它来完全清理测试中的任何内容
 * 写入工作区，这样就不会毒害后面的测试。
 */
export function removeWorkspacePath(relativePath: string): void {
  const config = getServerTestConfig();
  const fullPath = path.join(config.hostWorkspaceDir, relativePath);
  fs.rmSync(fullPath, { recursive: true, force: true });
}

/**
 * 清理工作区目录（删除所有文件）
 */
export function cleanWorkspace(): void {
  const config = getServerTestConfig();
  if (fs.existsSync(config.hostWorkspaceDir)) {
    const files = fs.readdirSync(config.hostWorkspaceDir);
    for (const file of files) {
      const fullPath = path.join(config.hostWorkspaceDir, file);
      const stat = fs.statSync(fullPath);
      if (stat.isDirectory()) {
        fs.rmSync(fullPath, { recursive: true });
      } else {
        fs.unlinkSync(fullPath);
      }
    }
  }
}

/**
 * 创建唯一的测试文件名
 */
export function uniqueFileName(prefix: string = 'test', extension: string = 'txt'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(7)}.${extension}`;
}

/**
 * 创建唯一的测试目录名称
 */
export function uniqueDirName(prefix: string = 'test-dir'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(7)}`;
}

/**
 * 生成随机文本内容
 */
export function randomContent(length: number = 100): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * 等待智能体完成（不运行）
 */
export async function waitForAgentIdle(
  checkStatus: () => Promise<string>,
  options: { timeout?: number; interval?: number } = {}
): Promise<void> {
  const { timeout = 120000, interval = 500 } = options;
  const start = Date.now();

  while (Date.now() - start < timeout) {
    const status = await checkStatus();
    if (status === 'idle' || status === 'finished' || status === 'error' || status === 'stuck') {
      return;
    }
    await sleep(interval);
  }

  throw new Error('Timeout waiting for agent to become idle');
}
