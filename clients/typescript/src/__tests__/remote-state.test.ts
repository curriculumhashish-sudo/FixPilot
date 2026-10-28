import type { Mock } from 'vitest';
import { HttpClient } from '../client/http-client';
import { RemoteState } from '../conversation/remote-state';

const originalFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const CONVERSATION_INFO = {
  execution_status: 'running',
  confirmation_policy: { kind: 'NeverConfirm' },
  activated_knowledge_skills: ['skill-a', 'skill-b'],
  agent: { kind: 'Agent', name: 'test-agent' },
  workspace: { kind: 'LocalWorkspace' },
  persistence_dir: '/data/conversations/abc',
};

function makeState(payload: unknown): { state: RemoteState; fetchMock: Mock } {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload)) as Mock;
  global.fetch = fetchMock as typeof fetch;
  const client = new HttpClient({ baseUrl: 'http://example.com' });
  return { state: new RemoteState(client, 'abc'), fetchMock };
}

describe('RemoteState full_state normalization', () => {
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('reads accessor fields from a flat conversation-info payload', async () => {
    const { state } = makeState(CONVERSATION_INFO);

    await expect(state.getExecutionStatus()).resolves.toBe('running');
    await expect(state.getConfirmationPolicy()).resolves.toEqual({ kind: 'NeverConfirm' });
    await expect(state.getActivatedKnowledgeSkills()).resolves.toEqual(['skill-a', 'skill-b']);
    await expect(state.getAgent()).resolves.toEqual({ kind: 'Agent', name: 'test-agent' });
    await expect(state.getWorkspace()).resolves.toEqual({ kind: 'LocalWorkspace' });
    await expect(state.getPersistenceDir()).resolves.toBe('/data/conversations/abc');
    await expect(state.modelDump()).resolves.toMatchObject(CONVERSATION_INFO);
  });

  it('unwraps a full_state-wrapped payload exactly once for every accessor', async () => {
    // 服务器可以将信息包装在`{ full_state: {...} }`中。 标准化现在在 getConversationInfo() 中发生一次； 访问者仍必须通读。
    //
    const { state } = makeState({ full_state: CONVERSATION_INFO });

    await expect(state.getExecutionStatus()).resolves.toBe('running');
    await expect(state.getConfirmationPolicy()).resolves.toEqual({ kind: 'NeverConfirm' });
    await expect(state.getActivatedKnowledgeSkills()).resolves.toEqual(['skill-a', 'skill-b']);
    await expect(state.getAgent()).resolves.toEqual({ kind: 'Agent', name: 'test-agent' });
    await expect(state.getWorkspace()).resolves.toEqual({ kind: 'LocalWorkspace' });
    await expect(state.getPersistenceDir()).resolves.toBe('/data/conversations/abc');
  });

  it('falls back to the legacy agent_status field when execution_status is absent', async () => {
    const { state } = makeState({ agent_status: 'idle' });
    await expect(state.getExecutionStatus()).resolves.toBe('idle');
  });

  it('throws a descriptive error when a required field is missing', async () => {
    const { state } = makeState({ execution_status: 'running' });
    await expect(state.getPersistenceDir()).rejects.toThrow(/persistence_dir missing/);
  });

  it('normalizes a cache that was populated with a full_state wrapper via events', async () => {
    // 回归：状态更新事件可以将缓存的状态封装在
    // `full_state` 键。 getConversationInfo() 的缓存命中路径也必须将其解包，否则访问器会抛出“execution_status 丢失”。
    //
    const fetchMock = vi.fn().mockRejectedValue(new Error('network should not be called')) as Mock;
    global.fetch = fetchMock as typeof fetch;
    const state = new RemoteState(new HttpClient({ baseUrl: 'http://example.com' }), 'abc');

    await state.updateStateFromEvent({
      id: 'evt-1',
      kind: 'ConversationStateUpdateEvent',
      timestamp: '2024-01-01T00:00:00Z',
      key: 'full_state',
      value: CONVERSATION_INFO,
    });

    await expect(state.getExecutionStatus()).resolves.toBe('running');
    await expect(state.getPersistenceDir()).resolves.toBe('/data/conversations/abc');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a non-object full-state event instead of corrupting the cache', async () => {
    const { state } = makeState(CONVERSATION_INFO);

    await expect(
      state.updateStateFromEvent({
        id: 'evt-2',
        kind: 'ConversationStateUpdateEvent',
        timestamp: '2024-01-01T00:00:00Z',
        key: '__full_state__',
        value: 'not-an-object',
      })
    ).rejects.toThrow('Full conversation state update must contain an object value');

    await expect(state.getExecutionStatus()).resolves.toBe('running');
  });
});
