import type { Mock } from 'vitest';
import { RemoteWorkspace } from '../index';

const originalFetch = global.fetch;

function noContentResponse(): Response {
  return new Response(null, { status: 204 });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function makeWorkspace(
  opts: {
    host?: string;
    apiKey?: string;
  } = {}
): RemoteWorkspace {
  return new RemoteWorkspace({
    host: opts.host ?? 'https://agent.example.com',
    workingDir: '/workspace',
    apiKey: opts.apiKey ?? 'secret-key',
  });
}

describe('RemoteWorkspace.startWorkspaceSession', () => {
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('mints a workspace session cookie and returns the static asset base URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(noContentResponse()) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const workspace = makeWorkspace();
    const baseUrl = await workspace.startWorkspaceSession('cid-1234');

    expect(baseUrl).toBe('https://agent.example.com/api/conversations/cid-1234/workspace/');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, init] = fetchMock.mock.calls[0];
    expect(new URL(url as string).pathname).toBe('/api/auth/workspace-session');
    expect((init as RequestInit).method).toBe('POST');
    expect((init as RequestInit).credentials).toBe('include');

    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers['X-Session-API-Key']).toBe('secret-key');
  });

  it('strips a trailing slash on the host so the base URL has exactly one separator', async () => {
    const fetchMock = vi.fn().mockResolvedValue(noContentResponse()) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const workspace = makeWorkspace({ host: 'https://agent.example.com/' });
    const baseUrl = await workspace.startWorkspaceSession('cid-1234');

    expect(baseUrl).toBe('https://agent.example.com/api/conversations/cid-1234/workspace/');
  });

  it('propagates 401s when the session API key is rejected', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: 'Unauthorized' }, 401)) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const workspace = makeWorkspace({ apiKey: 'wrong-key' });
    await expect(workspace.startWorkspaceSession('cid-1234')).rejects.toThrow(/401/);
  });

  it('does not require constructing an Agent or RemoteConversation', async () => {
    // 回归用于智能体-canvas 用例的保护：只有希望直接嵌入工作区资产的消费者，必须能够从工作区中直接进行操作，而无需发明一个占位符智能体 + LLM 来满足 RemoteConversation 构造函数。 该测试在不导入智能体 / RemoteConversation 的情况下进行编译的事实就是断言。
    //
    const fetchMock = vi.fn().mockResolvedValue(noContentResponse()) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const workspace = makeWorkspace();
    const baseUrl = await workspace.startWorkspaceSession('cid-only');

    expect(baseUrl).toBe('https://agent.example.com/api/conversations/cid-only/workspace/');
  });

  it('deletes the workspace session cookie with credentials included', async () => {
    const fetchMock = vi.fn().mockResolvedValue(noContentResponse()) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const workspace = makeWorkspace();
    await workspace.deleteWorkspaceSession();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(new URL(url as string).pathname).toBe('/api/auth/workspace-session');
    expect((init as RequestInit).method).toBe('DELETE');
    expect((init as RequestInit).credentials).toBe('include');
  });
});
