import { AgentProfilesClient } from './agent-profiles-client';
import { BashClient } from './bash-client';
import { CanvasExtensionsClient } from './canvas-extensions-client';
import { ConversationClient } from './conversation-client';
import { FileClient } from './file-client';
import { GitClient } from './git-client';
import { HooksClient } from './hooks-client';
import { HttpClient, type ResponseType } from './http-client';
import { LLMMetadataClient } from './llm-client';
import { MCPClient } from './mcp-client';
import { MetaProfilesClient } from './meta-profiles-client';
import { PluginsClient } from './plugins-client';
import { ProfilesClient } from './profiles-client';
import { ServerClient } from './server-client';
import { SettingsClient } from './settings-client';
import { SharedClient } from './shared-client';
import { SkillsClient } from './skills-client';
import { SubAgentsClient } from './sub-agents-client';
import { ToolClient } from './tool-client';
import { VSCodeClient } from './vscode-client';
import { WorkspacesClient } from './workspaces-client';

export type OpenHandsClientKind = 'agent-server' | 'cloud';

export type OpenHandsRequestMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

export type OpenHandsRequestAuthMode = 'default' | 'bearer' | 'session-api-key' | 'none';

export interface OpenHandsClientOptions {
  host: string;
  apiKey?: string;
  timeout?: number;
}

export interface OpenHandsRequestOptions {
  method: OpenHandsRequestMethod;
  path: string;
  params?: Record<string, unknown>;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutSeconds?: number;
  acceptableStatusCodes?: Set<number>;
  responseType?: ResponseType;
  /**
   * 可选的备用上游主机。 语义因客户端类型而异：
   * 智能体-服务器客户端直接将请求发送到该主机（e.g. a
   * 每个会话运行时 URL），而云客户端则通过它路由
   * 配置的代理端点（`CloudClientOptions.proxy`，默认
   * 路径 `/api/cloud-proxy`) 与代理信封中的该主机。
   */
  hostOverride?: string;
  /**
   * 覆盖此请求的默认身份验证策略。 `default`用途
   * 客户端自己的方案：智能体-服务器客户端发送客户端API密钥
   * as `X-Session-API-Key` （他们以同样的方式对待 `bearer`），而 cloud
   * 客户端将其发送为 `Authorization: Bearer`。 `session-api-key` 发送
   * `sessionApiKey` 为 `X-Session-API-Key`； `none` 不发送 auth 标头。
   */
  authMode?: OpenHandsRequestAuthMode;
  /** 当`authMode`为`session-api-key`时使用API键。*/
  sessionApiKey?: string | null;
}

export abstract class OpenHandsClient {
  public readonly host: string;
  public readonly apiKey?: string;
  protected readonly timeout: number;

  constructor(options: OpenHandsClientOptions) {
    this.host = options.host.replace(/\/+$/, '');
    this.apiKey = options.apiKey;
    this.timeout = options.timeout || 60000;
  }

  abstract readonly kind: OpenHandsClientKind;

  abstract request<TResponse = unknown>(options: OpenHandsRequestOptions): Promise<TResponse>;

  get<TResponse = unknown>(
    path: string,
    options: Omit<OpenHandsRequestOptions, 'method' | 'path'> = {}
  ): Promise<TResponse> {
    return this.request<TResponse>({ ...options, method: 'GET', path });
  }

  post<TResponse = unknown>(
    path: string,
    body?: unknown,
    options: Omit<OpenHandsRequestOptions, 'method' | 'path' | 'body'> = {}
  ): Promise<TResponse> {
    return this.request<TResponse>({ ...options, method: 'POST', path, body });
  }

  patch<TResponse = unknown>(
    path: string,
    body?: unknown,
    options: Omit<OpenHandsRequestOptions, 'method' | 'path' | 'body'> = {}
  ): Promise<TResponse> {
    return this.request<TResponse>({ ...options, method: 'PATCH', path, body });
  }

  put<TResponse = unknown>(
    path: string,
    body?: unknown,
    options: Omit<OpenHandsRequestOptions, 'method' | 'path' | 'body'> = {}
  ): Promise<TResponse> {
    return this.request<TResponse>({ ...options, method: 'PUT', path, body });
  }

  delete<TResponse = unknown>(
    path: string,
    options: Omit<OpenHandsRequestOptions, 'method' | 'path'> = {}
  ): Promise<TResponse> {
    return this.request<TResponse>({ ...options, method: 'DELETE', path });
  }

  close(): void {
    // 由具体客户在拥有资源时实施。
  }
}

export class AgentServerClient extends OpenHandsClient {
  readonly kind = 'agent-server' as const;

  readonly server: ServerClient;
  readonly conversations: ConversationClient;
  readonly files: FileClient;
  readonly bash: BashClient;
  readonly canvasExtensions: CanvasExtensionsClient;
  readonly settings: SettingsClient;
  readonly profiles: ProfilesClient;
  readonly agentProfiles: AgentProfilesClient;
  readonly metaProfiles: MetaProfilesClient;
  readonly skills: SkillsClient;
  readonly subAgents: SubAgentsClient;
  readonly hooks: HooksClient;
  readonly git: GitClient;
  readonly mcp: MCPClient;
  readonly plugins: PluginsClient;
  readonly tools: ToolClient;
  readonly vscode: VSCodeClient;
  readonly shared: SharedClient;
  readonly llm: LLMMetadataClient;
  readonly workspaces: WorkspacesClient;

  private readonly client: HttpClient;

  constructor(options: OpenHandsClientOptions) {
    super(options);
    const clientOptions = {
      host: this.host,
      apiKey: this.apiKey,
      timeout: this.timeout,
    };

    this.client = new HttpClient({
      baseUrl: this.host,
      apiKey: this.apiKey,
      timeout: this.timeout,
    });
    this.server = new ServerClient(clientOptions);
    this.conversations = new ConversationClient(clientOptions);
    this.files = new FileClient(clientOptions);
    this.bash = new BashClient(clientOptions);
    this.canvasExtensions = new CanvasExtensionsClient(clientOptions);
    this.settings = new SettingsClient(clientOptions);
    this.profiles = new ProfilesClient(clientOptions);
    this.agentProfiles = new AgentProfilesClient(clientOptions);
    this.metaProfiles = new MetaProfilesClient(clientOptions);
    this.skills = new SkillsClient(clientOptions);
    this.subAgents = new SubAgentsClient(clientOptions);
    this.hooks = new HooksClient(clientOptions);
    this.git = new GitClient(clientOptions);
    this.mcp = new MCPClient(clientOptions);
    this.plugins = new PluginsClient(clientOptions);
    this.tools = new ToolClient(clientOptions);
    this.vscode = new VSCodeClient(clientOptions);
    this.shared = new SharedClient(clientOptions);
    this.llm = new LLMMetadataClient(clientOptions);
    this.workspaces = new WorkspacesClient(clientOptions);
  }

  async request<TResponse = unknown>(options: OpenHandsRequestOptions): Promise<TResponse> {
    const host = options.hostOverride?.replace(/\/+$/, '') ?? this.host;
    const apiKey =
      options.authMode === 'none'
        ? undefined
        : options.authMode === 'session-api-key'
          ? (options.sessionApiKey ?? undefined)
          : this.apiKey;
    const client =
      host === this.host && apiKey === this.apiKey
        ? this.client
        : new HttpClient({
            baseUrl: host,
            apiKey,
            timeout: this.timeout,
          });

    const response = await client.request<TResponse>({
      method: options.method,
      url: options.path,
      params: options.params,
      data: options.body,
      headers: options.headers,
      timeout: options.timeoutSeconds ? options.timeoutSeconds * 1000 : this.timeout,
      acceptableStatusCodes: options.acceptableStatusCodes,
      responseType: options.responseType,
    });
    return response.data;
  }

  override close(): void {
    this.client.close();
  }
}
