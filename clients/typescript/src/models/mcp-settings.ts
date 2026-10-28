/**
 * 规范已持久化 MCP 设置类型。
 *
 * 生成的 Agent Server 组件仍然是字段级源
 * 真相。 这些别名添加了稳定的传输层区分和稀疏
 * RFC 7386 客户端调用者期望的突变语义。
 */
import type {
  McpConfigPatchWritable,
  McpServerInputWritable,
  McpServerPatchWritable,
  McpoAuthAuthenticationInputWritable,
  McpoAuthStateInputWritable,
} from '../generated/agent-server-schema';

type GeneratedMCPServer = McpServerInputWritable;
type GeneratedMCPTransport = NonNullable<GeneratedMCPServer['transport']>;
type GeneratedMCPAuthCredential = NonNullable<GeneratedMCPServer['auth']>;

type MCPDisplayFields = Pick<GeneratedMCPServer, 'description' | 'icon' | 'timeout'>;
type MCPStdioFields = Pick<GeneratedMCPServer, 'args' | 'env' | 'cwd'>;
type MCPRemoteFields = Pick<
  GeneratedMCPServer,
  'headers' | 'auth' | 'sse_read_timeout' | 'keep_alive'
>;

export type MCPTransport = GeneratedMCPTransport;
export type RemoteMCPTransport = Exclude<MCPTransport, 'stdio'>;
export type MCPAuthCredential = GeneratedMCPAuthCredential;
export type MCPOAuthAuthentication = McpoAuthAuthenticationInputWritable;
export type MCPOAuthState = McpoAuthStateInputWritable;

export type StdioMCPServer = MCPDisplayFields &
  MCPStdioFields & {
    transport: 'stdio';
    command: string;
    url?: never;
  };

export type RemoteMCPServer = MCPDisplayFields &
  MCPRemoteFields & {
    transport: RemoteMCPTransport;
    url: string;
    command?: never;
  };

export type MCPServer = StdioMCPServer | RemoteMCPServer;
export type MCPConfig = Record<string, MCPServer>;
export type MCPServerPatch = McpServerPatchWritable;
export type MCPConfigPatch = McpConfigPatchWritable;
