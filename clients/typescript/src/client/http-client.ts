/**
 * HTTP OpenHands Agent Server API 的客户端
 */

import type { ValidationError as AgentServerValidationError } from '../generated/agent-server-schema';

export interface HttpClientOptions {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export type ResponseType = 'auto' | 'json' | 'text' | 'blob' | 'arrayBuffer';

export interface RequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  url: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: Record<string, string>;
  timeout?: number;
  acceptableStatusCodes?: Set<number>;
  responseType?: ResponseType;
  /**
   * 凭据 mode for `fetch`. 使用 `'include'` 代替端点该问题或
   * 消耗 cookie (e.g. 由以下人员创建的工作区-会话 cookie
   * `POST /api/auth/workspace-session`) 因此浏览器将它们持久化
   * 起源。
   */
  credentials?: RequestCredentials;
  /**
   * 调用者拥有的取消信号，与客户端超时相结合，所以
   * 请求在先触发时中止。 传递生命周期信号
   * 请求的所有者（e.g。 React 安装/`AbortController`) 所以
   * 拆解或重试取消正在进行的调用，而不是将其留给
   * 决心成为一个陈旧的消费者。
   */
  signal?: AbortSignal;
}

export interface HttpResponse<T = unknown> {
  data: T;
  status: number;
  statusText: string;
  headers: Record<string, string>;
}

/**
 * Agent Server 验证错误主体的一项：
 * `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`. FastAPI 请求
 * 验证使用此形状回答 422，并且一些处理程序重复使用它。
 */
export type HttpValidationErrorItem = Pick<AgentServerValidationError, 'loc' | 'msg' | 'type'>;

/**
 * 标记 HttpError 个实例。 `Symbol.for` 在每个中返回相同的符号
 * 该包的副本，因此 {@link isHttpError} 可以识别出由
 * 另一个捆绑副本，其中 `instanceof HttpError` 是 False。 已建副本
 * 在这个品牌存在之前不要设置它。
 */
const HTTP_ERROR_BRAND = Symbol.for('@openhands/typescript-client/HttpError');

/**
 * 当服务器以请求不接受的状态应答时抛出。
 *
 * `message` 是传输层文本（`HTTP 请求失败 (<status> <text>)：
 * <body>`)，用于日志。 使用 {@link HttpError.detail} 作为服务器自己的
 * 消息，当超过一个时，用 {@link isHttpError} 代替 `instanceof`
 * 可以加载此包的副本。
 */
export class HttpError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public response?: unknown,
    message?: string
  ) {
    super(message || `HTTP ${status}: ${statusText}`);
    this.name = 'HttpError';
    Object.defineProperty(this, HTTP_ERROR_BRAND, { value: true });
  }

  /**
   * 来自已解析错误正文的服务器可读消息，或 `undefined`
   * 当身体携带None时。 读取Agent Server的错误形状：
   *
   * - `{"detail": "<message>"}`：按原样返回。
   * - `{"detail": [{"loc", "msg", "type"}, ...]}`（验证个错误）：一
   *   条目给出其`msg`。 多个条目用 `"; "` 连接，每个条目
   *   `msg` 以其字段名称为前缀（`loc` 中的最后一个字符串），因此
   *   消息可以被区分，e.g。 `"名称：必填字段； 型号：田野
   *   required"`. Use {@link HttpError.validationErrors} for the full `loc`.
   * - `{"detail": {"message": "<message>", ...}}` (e.g. 启动错误
   *   `code`）：`message`。
   *
   * 任何其他正文，包括非 JSON 正文（例如来自某个网站的 HTML 页面）
   * `undefined`； `response`至今仍保留着这一观点。
   */
  get detail(): string | undefined {
    const body = this.response;
    if (!isRecord(body)) return undefined;
    const { detail } = body;
    if (typeof detail === 'string') return nonBlank(detail);
    if (Array.isArray(detail)) return formatValidationErrors(this.validationErrors);
    if (isRecord(detail) && typeof detail.message === 'string') return nonBlank(detail.message);
    return undefined;
  }

  /**
   * 验证错误主体的条目 (`{"detail": [{"loc", "msg",
   * "type"}, ...]}`), or `undefined` 当主体不是一个时。 每个条目都是
   * 仅使用 `loc`、`msg` 和 `type` 进行复制； 除非 `loc`，否则将跳过条目
   * 是字符串和数字的数组，`msg` 和 `type` 是字符串。
   */
  get validationErrors(): HttpValidationErrorItem[] | undefined {
    const body = this.response;
    if (!isRecord(body) || !Array.isArray(body.detail)) return undefined;
    const items = body.detail
      .filter(isValidationErrorItem)
      .map(({ loc, msg, type }) => ({ loc: [...loc], msg, type }));
    return items.length > 0 ? items : undefined;
  }
}

/**
 * `value`是否是一个{@link HttpError}，包括由另一个创建的
 * 该包的副本（例如，当应用程序和库每个捆绑包
 * 他们自己的），其中 `instanceof HttpError` 是 False。 另一个副本必须是
 * 一个标记其错误的版本，i.e。 这个或以后。
 */
export function isHttpError(value: unknown): value is HttpError {
  return (
    value instanceof HttpError ||
    (typeof value === 'object' &&
      value !== null &&
      (value as Record<symbol, unknown>)[HTTP_ERROR_BRAND] === true)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonBlank(text: string): string | undefined {
  return text.trim() ? text : undefined;
}

function isValidationErrorItem(value: unknown): value is HttpValidationErrorItem {
  if (!isRecord(value)) return false;
  const { loc, msg, type } = value;
  return (
    typeof msg === 'string' &&
    typeof type === 'string' &&
    Array.isArray(loc) &&
    loc.every((part) => typeof part === 'string' || typeof part === 'number')
  );
}

function formatValidationErrors(items: HttpValidationErrorItem[] | undefined): string | undefined {
  const withMessage = (items ?? []).filter(({ msg }) => msg.trim());
  if (withMessage.length === 0) return undefined;
  if (withMessage.length === 1) return withMessage[0].msg;
  return withMessage
    .map(({ loc, msg }) => {
      const field = fieldName(loc);
      return field ? `${field}: ${msg}` : msg;
    })
    .join('; ');
}

/** 验证 `loc`, e.g 中的最后一个非空字符串。 `['body', 'name']`中的`name`。*/
function fieldName(loc: HttpValidationErrorItem['loc']): string | undefined {
  for (let index = loc.length - 1; index >= 0; index -= 1) {
    const part = loc[index];
    if (typeof part === 'string' && part !== '') return part;
  }
  return undefined;
}

export class HttpClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;

  constructor(options: HttpClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.timeout = options.timeout || 60000;
  }

  private buildUrl(path: string, params?: Record<string, unknown>): URL {
    const relativePath = path.startsWith('/') ? path.slice(1) : path;
    const url = new URL(relativePath, this.baseUrl + '/');

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          if (Array.isArray(value)) {
            value.forEach((item) => url.searchParams.append(key, String(item)));
          } else {
            url.searchParams.append(key, String(value));
          }
        }
      });
    }

    return url;
  }

  async request<T = unknown>(options: RequestOptions): Promise<HttpResponse<T>> {
    // `fetch`（和浏览器）拒绝 GET 请求上的正文，但有一些智能体-服务器批处理端点 (e.g. `GET /api/bash/bash_events/` 和
    // `GET /api/conversations/{id}/events`) 被声明为 GET-with-required-body。 通过 Node 的 http(s) 模块路由这些模块，该模块允许 GET 主体，并为每个其他请求保留获取路径不变。
    //
    if (options.method === 'GET' && options.data !== undefined && options.data !== null) {
      return this.requestWithBodyOnGet<T>(options);
    }

    const url = this.buildUrl(options.url, options.params);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.apiKey) {
      headers['X-Session-API-Key'] = this.apiKey;
    }

    const requestInit: RequestInit = {
      method: options.method,
      headers,
      signal: combineAbortSignals(
        options.signal,
        AbortSignal.timeout(options.timeout || this.timeout)
      ),
    };

    if (options.credentials) {
      requestInit.credentials = options.credentials;
    }

    if (options.data && options.method !== 'GET') {
      if (options.data instanceof FormData) {
        delete headers['Content-Type'];
        requestInit.body = options.data;
      } else {
        requestInit.body = JSON.stringify(options.data);
      }
    }

    try {
      const response = await fetch(url.toString(), requestInit);

      const isAcceptable =
        options.acceptableStatusCodes?.has(response.status) ||
        (!options.acceptableStatusCodes && response.ok);

      if (!isAcceptable) {
        let errorContent: unknown;
        try {
          const contentType = response.headers.get('content-type');
          if (contentType?.includes('application/json')) {
            errorContent = await response.json();
          } else {
            errorContent = await response.text();
          }
        } catch {
          errorContent = null;
        }

        throw new HttpError(
          response.status,
          response.statusText,
          errorContent,
          `HTTP request failed (${response.status} ${response.statusText}): ${JSON.stringify(errorContent)}`
        );
      }

      const data = (await this.parseResponse<T>(response, options.responseType || 'auto')) as T;

      const responseHeaders: Record<string, string> = {};
      response.headers.forEach((value, key) => {
        responseHeaders[key] = value;
      });

      return {
        data,
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      };
    } catch (error) {
      if (error instanceof HttpError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError' || error.name === 'TimeoutError') {
          // 已触发的调用者拥有的信号意味着请求已被其所有者取消，而不是客户端超时已失效。
          //
          if (options.signal?.aborted) {
            throw error;
          }
          throw new Error(`Request timeout after ${options.timeout || this.timeout}ms`, {
            cause: error,
          });
        }
        throw new Error(`Request failed: ${error.message}`, { cause: error });
      }

      throw new Error('Unknown request error', { cause: error });
    }
  }

  /**
   * 通过 Node 的 `http`/`https` 发出携带 JSON 主体的 GET 请求
   * 模块。 `fetch` 抛出 `TypeError：使用 GET/HEAD 方法的请求不能有
   * body`，所以这是调用智能体-server 的 GET-with-body 的唯一方法
   * 批次端点。 镜像获取的 URL/header/error/parse 行为
   * {@link request} 中的路径。 本质上仅限节点（浏览器禁止 GET 主体）。
   */
  private async requestWithBodyOnGet<T = unknown>(
    options: RequestOptions
  ): Promise<HttpResponse<T>> {
    const url = this.buildUrl(options.url, options.params);

    const body = typeof options.data === 'string' ? options.data : JSON.stringify(options.data);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers,
      'Content-Length': String(Buffer.byteLength(body)),
    };

    if (this.apiKey) {
      headers['X-Session-API-Key'] = this.apiKey;
    }

    const transport =
      url.protocol === 'https:' ? await import('node:https') : await import('node:http');
    const timeoutMs = options.timeout || this.timeout;

    return new Promise<HttpResponse<T>>((resolve, reject) => {
      const req = transport.request(url, { method: options.method, headers }, (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          try {
            const status = res.statusCode ?? 0;
            const statusText = res.statusMessage ?? '';
            const responseHeaders: Record<string, string> = {};
            for (const [key, value] of Object.entries(res.headers)) {
              if (value !== undefined) {
                responseHeaders[key] = Array.isArray(value) ? value.join(', ') : value;
              }
            }

            const buffer = Buffer.concat(chunks);
            const contentType = responseHeaders['content-type'];

            const isAcceptable =
              options.acceptableStatusCodes?.has(status) ||
              (!options.acceptableStatusCodes && status >= 200 && status < 300);

            if (!isAcceptable) {
              const text = buffer.toString('utf-8');
              let errorContent: unknown;
              try {
                errorContent = contentType?.includes('application/json') ? JSON.parse(text) : text;
              } catch {
                errorContent = text || null;
              }

              reject(
                new HttpError(
                  status,
                  statusText,
                  errorContent,
                  `HTTP request failed (${status} ${statusText}): ${JSON.stringify(errorContent)}`
                )
              );
              return;
            }

            const data = this.parseNodeResponse<T>(
              buffer,
              contentType,
              options.responseType || 'auto'
            );

            resolve({ data, status, statusText, headers: responseHeaders });
          } catch (error) {
            reject(error);
          }
        });
      });

      req.on('error', (error: Error) => {
        reject(new Error(`Request failed: ${error.message}`, { cause: error }));
      });

      req.setTimeout(timeoutMs, () => {
        req.destroy(new Error(`Request timeout after ${timeoutMs}ms`));
      });

      req.end(body);
    });
  }

  private parseNodeResponse<T>(
    buffer: Buffer,
    contentType: string | undefined,
    responseType: ResponseType
  ): T {
    if (responseType === 'blob') {
      return new Blob([new Uint8Array(buffer)]) as T;
    }

    if (responseType === 'arrayBuffer') {
      return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength) as T;
    }

    const text = buffer.toString('utf-8');

    if (responseType === 'text') {
      return text as T;
    }

    if (responseType === 'json') {
      return (text ? JSON.parse(text) : undefined) as T;
    }

    if (contentType?.includes('application/json')) {
      return (text ? JSON.parse(text) : undefined) as T;
    }

    return text as T;
  }

  private async parseResponse<T>(response: Response, responseType: ResponseType): Promise<T> {
    if (responseType === 'json') {
      return (await response.json()) as T;
    }

    if (responseType === 'text') {
      return (await response.text()) as T;
    }

    if (responseType === 'blob') {
      return (await response.blob()) as T;
    }

    if (responseType === 'arrayBuffer') {
      return (await response.arrayBuffer()) as T;
    }

    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      return (await response.json()) as T;
    }
    return (await response.text()) as T;
  }

  async get<T = unknown>(
    url: string,
    options?: Omit<RequestOptions, 'method' | 'url'>
  ): Promise<HttpResponse<T>> {
    return this.request<T>({ method: 'GET', url, ...options });
  }

  async post<T = unknown>(
    url: string,
    data?: unknown,
    options?: Omit<RequestOptions, 'method' | 'url' | 'data'>
  ): Promise<HttpResponse<T>> {
    return this.request<T>({ method: 'POST', url, data, ...options });
  }

  async put<T = unknown>(
    url: string,
    data?: unknown,
    options?: Omit<RequestOptions, 'method' | 'url' | 'data'>
  ): Promise<HttpResponse<T>> {
    return this.request<T>({ method: 'PUT', url, data, ...options });
  }

  async patch<T = unknown>(
    url: string,
    data?: unknown,
    options?: Omit<RequestOptions, 'method' | 'url' | 'data'>
  ): Promise<HttpResponse<T>> {
    return this.request<T>({ method: 'PATCH', url, data, ...options });
  }

  async delete<T = unknown>(
    url: string,
    options?: Omit<RequestOptions, 'method' | 'url'>
  ): Promise<HttpResponse<T>> {
    return this.request<T>({ method: 'DELETE', url, ...options });
  }

  close(): void {
    // 基于提取的客户端无需清理
  }
}

/**
 * 将调用者拥有的信号与客户端超时信号相结合，以便请求
 * 以先触发者为准中止。 当没有时返回超时信号不变
 * 提供呼叫者信号，保持单信号行为相同。
 */
function combineAbortSignals(
  callerSignal: AbortSignal | undefined,
  timeoutSignal: AbortSignal
): AbortSignal {
  if (!callerSignal) {
    return timeoutSignal;
  }
  return AbortSignal.any([callerSignal, timeoutSignal]);
}
