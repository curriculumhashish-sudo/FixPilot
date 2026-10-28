/**
 * WebSocket 构造函数查找由回调样式套接字客户端共享。
 */

/**
 * 当前运行时的Web标准WebSocket构造函数：浏览器，
 * Web Workers 和 Node 22+ 都将其公开为 `globalThis.WebSocket`。
 *
 * 在每次连接时查找，从不在导入时查找，因此导入包
 * barrel 既不抛出也不拉入 Node-only 模块和构造函数
 * 导入后安装在 `globalThis` 上（例如 `ws` 包在
 * 较旧的节点）被拾取。
 */
export function getGlobalWebSocket(): (new (url: string) => WebSocket) | undefined {
  return (globalThis as { WebSocket?: new (url: string) => WebSocket }).WebSocket;
}

export const WEBSOCKET_UNAVAILABLE_MESSAGE =
  'WebSocket implementation not available. Run in an environment with a global ' +
  'WebSocket constructor (browsers, Node 22+), or assign one such as the `ws` ' +
  'package to globalThis.WebSocket.';
