/**
 * 集成测试为 WebSocketCallbackClient
 *
 * 测试来自智能体服务器的实时事件流式传输。
 *
 * 注意：默认情况下会跳过此文件中的一些测试，因为它们依赖于
 * LLM 行为是不确定的并且可能很慢。
 */

import { WebSocketCallbackClient, HttpClient, Event } from '../../index';
import { getTestConfig, skipIfNoConfig, createTestLLMConfig } from './test-config';
import { sleep, waitFor } from './test-utils';

const SKIP_TESTS = skipIfNoConfig();
// 跳过依赖于 CI 中的 LLM 行为的不稳定测试
const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';

type CreateConversationResponse = {
  id: string;
};

describe('WebSocket Integration Tests', () => {
  let config: ReturnType<typeof getTestConfig>;
  let httpClient: HttpClient;

  beforeAll(() => {
    if (SKIP_TESTS) {
      console.warn('Skipping integration tests: LLM_API_KEY and LLM_MODEL not set');
      return;
    }
    config = getTestConfig();
    httpClient = new HttpClient({
      baseUrl: config.agentServerUrl,
      timeout: 60000,
    });
  });

  afterAll(() => {
    if (httpClient) {
      httpClient.close();
    }
  });

  describe('WebSocket Connection', () => {
    it(
      'should establish WebSocket connection and receive events',
      async () => {
        if (SKIP_TESTS) return;

        // 首先创建一个对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 10,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const receivedEvents: Event[] = [];

        // 创建 WebSocket 个客户端
        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            receivedEvents.push(event);
          },
        });

        // 启动 WebSocket 连接
        wsClient.start();

        // 等待连接建立
        await sleep(1000);

        // 发送消息并运行智能体
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'Say hello!' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 等待接收事件
        await waitFor(() => receivedEvents.length > 0, {
          timeout: 60000,
          interval: 500,
          message: 'No events received',
        });

        // 应该至少收到一个事件
        expect(receivedEvents.length).toBeGreaterThan(0);

        // 事件应该具有必需的属性
        for (const event of receivedEvents) {
          expect(event.id).toBeDefined();
          expect(event.kind).toBeDefined();
        }

        // 停止 WebSocket 客户端
        wsClient.stop();
      },
      config?.testTimeout || 120000
    );

    it(
      'should receive different event types',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 15,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const eventTypes = new Set<string>();
        const receivedEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            eventTypes.add(event.kind);
            receivedEvents.push(event);
          },
        });

        wsClient.start();
        await sleep(1000);

        // 发送一条消息，要求智能体执行某项操作
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'List the files in the current directory.' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 等待多种事件类型
        await waitFor(() => eventTypes.size > 1, {
          timeout: 90000,
          interval: 500,
          message: 'Not enough event types received',
        });

        // 应该收到多种事件类型
        expect(eventTypes.size).toBeGreaterThan(1);

        // 记录接收到的事件类型以进行调试
        console.log('Received event types:', Array.from(eventTypes));

        wsClient.stop();
      },
      config?.testTimeout || 120000
    );

    it(
      'should handle WebSocket reconnection',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 5,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        let connectionCount = 0;
        const receivedEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            receivedEvents.push(event);
          },
        });

        // 开始连接
        wsClient.start();
        await sleep(500);

        // 停止并重新启动以模拟重新连接
        wsClient.stop();
        await sleep(200);

        wsClient.start();
        await sleep(500);

        // 发送消息
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'Say "reconnected"' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 等待活动
        await waitFor(() => receivedEvents.length > 0, {
          timeout: 60000,
          interval: 500,
          message: 'No events after reconnection',
        });

        expect(receivedEvents.length).toBeGreaterThan(0);

        wsClient.stop();
      },
      config?.testTimeout || 120000
    );

    it(
      'should stop cleanly without receiving more events',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 5,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const receivedEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            receivedEvents.push(event);
          },
        });

        wsClient.start();
        await sleep(500);

        // 立即停止
        wsClient.stop();

        const countAfterStop = receivedEvents.length;

        // 发送消息（不应收到）
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'This should not be received' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 稍等一下
        await sleep(3000);

        // 停止后不应收到新事件
        expect(receivedEvents.length).toBe(countAfterStop);
      },
      config?.testTimeout || 60000
    );
  });

  describe('Event Content', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should receive MessageEvent with content',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 10,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const messageEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            if (event.kind === 'MessageEvent') {
              messageEvents.push(event);
            }
          },
        });

        wsClient.start();
        await sleep(1000);

        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'What is 5 + 3?' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 等待消息事件
        await waitFor(() => messageEvents.length > 0, {
          timeout: 60000,
          interval: 500,
          message: 'No MessageEvents received',
        });

        expect(messageEvents.length).toBeGreaterThan(0);

        // MessageEvents 应该有 llm_message
        const firstMessage = messageEvents[0];
        expect(firstMessage).toHaveProperty('llm_message');

        wsClient.stop();
      },
      config?.testTimeout || 120000
    );

    testFn(
      'should receive ActionEvent when agent performs action',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 15,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const actionEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            if (event.kind === 'ActionEvent') {
              actionEvents.push(event);
            }
          },
        });

        wsClient.start();
        await sleep(1000);

        // 要求智能体执行一个操作 - 使用一个简单任务，该任务可靠地触发操作
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'List the files in the current directory.' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 对于依赖于 LLM 的测试，等待更长超时的操作事件
        await waitFor(() => actionEvents.length > 0, {
          timeout: 120000,
          interval: 500,
          message: 'No ActionEvents received',
        });

        expect(actionEvents.length).toBeGreaterThan(0);

        // ActionEvents 应具有操作属性
        const firstAction = actionEvents[0];
        expect(firstAction).toHaveProperty('action');

        wsClient.stop();
      },
      config?.testTimeout || 180000
    );

    testFn(
      'should receive ObservationEvent after action',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 15,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const observationEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            if (event.kind === 'ObservationEvent') {
              observationEvents.push(event);
            }
          },
        });

        wsClient.start();
        await sleep(1000);

        // 要求智能体运行命令（生成观测结果） - 使用一个简单的任务
        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'List the files in the current directory.' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 对于依赖于 LLM 的测试，等待超时时间较长的观测结果事件
        await waitFor(() => observationEvents.length > 0, {
          timeout: 120000,
          interval: 500,
          message: 'No ObservationEvents received',
        });

        expect(observationEvents.length).toBeGreaterThan(0);

        // ObservationEvents 应具有观测结果属性
        const firstObs = observationEvents[0];
        expect(firstObs).toHaveProperty('observation');

        wsClient.stop();
      },
      config?.testTimeout || 180000
    );
  });

  describe('ConversationStateUpdateEvent', () => {
    it(
      'should receive state update events',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话
        const createResponse = await httpClient.post<CreateConversationResponse>(
          '/api/conversations',
          {
            agent: {
              kind: 'Agent',
              llm: createTestLLMConfig(),
            },
            max_iterations: 10,
            stuck_detection: true,
            workspace: {
              type: 'local',
              working_dir: config.agentWorkspaceDir,
            },
          }
        );

        const conversationId = createResponse.data.id;
        const stateUpdateEvents: Event[] = [];

        const wsClient = new WebSocketCallbackClient({
          host: config.agentServerUrl,
          conversationId,
          callback: (event) => {
            if (event.kind === 'ConversationStateUpdateEvent') {
              stateUpdateEvents.push(event);
            }
          },
        });

        wsClient.start();
        await sleep(1000);

        await httpClient.post(`/api/conversations/${conversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'Say OK' }],
          run: false,
        });

        await httpClient.post(`/api/conversations/${conversationId}/run`);

        // 等待状态更新事件
        await waitFor(() => stateUpdateEvents.length > 0, {
          timeout: 60000,
          interval: 500,
          message: 'No ConversationStateUpdateEvents received',
        });

        expect(stateUpdateEvents.length).toBeGreaterThan(0);

        // 状态更新事件应该有键和值
        const firstUpdate = stateUpdateEvents[0];
        expect(firstUpdate).toHaveProperty('key');
        expect(firstUpdate).toHaveProperty('value');

        wsClient.stop();
      },
      config?.testTimeout || 120000
    );
  });
});
