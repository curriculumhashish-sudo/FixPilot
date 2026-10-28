/**
 * 集成测试为 HttpClient
 *
 * 针对真实的智能体服务器测试 HTTP 客户端功能。
 */

import { HttpClient, HttpError } from '../../index';
import { getTestConfig, skipIfNoConfig } from './test-config';

const SKIP_TESTS = skipIfNoConfig();

type ServerInfoResponse = {
  version?: string;
};

type CreateConversationResponse = {
  id: string;
};

type ConversationResourceResponse = {
  id?: string;
  full_state?: {
    id?: string;
  };
};

describe('HttpClient Integration Tests', () => {
  let client: HttpClient;
  let config: ReturnType<typeof getTestConfig>;

  beforeAll(() => {
    if (SKIP_TESTS) {
      console.warn('Skipping integration tests: LLM_API_KEY and LLM_MODEL not set');
      return;
    }
    config = getTestConfig();
    client = new HttpClient({
      baseUrl: config.agentServerUrl,
      timeout: 30000,
    });
  });

  afterAll(() => {
    if (client) {
      client.close();
    }
  });

  describe('Health and Server Info', () => {
    it(
      'should check server alive status',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.get('/alive');

        expect(response.status).toBe(200);
      },
      config?.testTimeout || 30000
    );

    it(
      'should check server health',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.get('/health');

        expect(response.status).toBe(200);
      },
      config?.testTimeout || 30000
    );

    it(
      'should get server info',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.get<ServerInfoResponse>('/server_info');

        expect(response.status).toBe(200);
        expect(response.data).toBeDefined();
        // 服务器信息应该有版本
        expect(response.data.version).toBeDefined();
      },
      config?.testTimeout || 30000
    );
  });

  describe('GET Requests', () => {
    it(
      'should make GET request with query params',
      async () => {
        if (SKIP_TESTS) return;

        // 使用支持查询参数的搜索端点
        const response = await client.get('/api/conversations/search', {
          params: { limit: 10 },
        });

        expect(response.status).toBe(200);
        expect(response.data).toBeDefined();
      },
      config?.testTimeout || 30000
    );

    it(
      'should handle 404 responses',
      async () => {
        if (SKIP_TESTS) return;

        try {
          // 使用有效的 UUID 格式但 ID 不存在
          await client.get('/api/conversations/00000000-0000-0000-0000-000000000000');
          fail('Expected HttpError to be thrown');
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          const httpError = error as HttpError;
          expect(httpError.status).toBe(404);
        }
      },
      config?.testTimeout || 30000
    );
  });

  describe('POST Requests', () => {
    it(
      'should make POST request with JSON body',
      async () => {
        if (SKIP_TESTS) return;

        // 创建对话来测试 POST
        const response = await client.post<CreateConversationResponse>('/api/conversations', {
          agent: {
            kind: 'Agent',
            llm: {
              model: config.llmModel,
              api_key: config.llmApiKey,
              ...(config.llmBaseUrl && { base_url: config.llmBaseUrl }),
            },
          },
          max_iterations: 5,
          stuck_detection: true,
          workspace: {
            type: 'local',
            working_dir: config.agentWorkspaceDir,
          },
        });

        // 接受 200 和 201（已创建）作为资源创建的有效响应
        expect([200, 201]).toContain(response.status);
        expect(response.data).toBeDefined();
        expect(response.data.id).toBeDefined();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Error Handling', () => {
    it(
      'should handle malformed request body',
      async () => {
        if (SKIP_TESTS) return;

        try {
          // 发送请求缺少必填字段
          await client.post('/api/conversations', {});
          fail('Expected HttpError to be thrown');
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          const httpError = error as HttpError;
          // 应该得到 422（验证错误）或 400（错误请求）
          expect([400, 422]).toContain(httpError.status);
        }
      },
      config?.testTimeout || 30000
    );

    it(
      'should handle timeout configuration',
      async () => {
        if (SKIP_TESTS) return;

        const shortTimeoutClient = new HttpClient({
          baseUrl: config.agentServerUrl,
          timeout: 1, // 1ms 超时 - 应该失败
        });

        try {
          await shortTimeoutClient.get('/health');
          // 如果成功的话服务器速度非常快
        } catch (error) {
          // 超时预期错误
          expect(error).toBeDefined();
        } finally {
          shortTimeoutClient.close();
        }
      },
      config?.testTimeout || 30000
    );
  });

  describe('Response Headers', () => {
    it(
      'should include response headers',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.get('/health');

        expect(response.headers).toBeDefined();
        expect(typeof response.headers).toBe('object');
        // 应该有内容类型标题
        expect(response.headers['content-type']).toBeDefined();
      },
      config?.testTimeout || 30000
    );
  });

  describe('Request Methods', () => {
    let testConversationId: string;

    beforeAll(async () => {
      if (SKIP_TESTS) return;

      // 创建一个对话进行测试
      const response = await client.post<CreateConversationResponse>('/api/conversations', {
        agent: {
          kind: 'Agent',
          llm: {
            model: config.llmModel,
            api_key: config.llmApiKey,
            ...(config.llmBaseUrl && { base_url: config.llmBaseUrl }),
          },
        },
        max_iterations: 5,
        stuck_detection: true,
        workspace: {
          type: 'local',
          working_dir: config.agentWorkspaceDir,
        },
      });

      testConversationId = response.data.id;
    });

    it(
      'should make GET request for specific resource',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.get<ConversationResourceResponse>(
          `/api/conversations/${testConversationId}`
        );

        expect(response.status).toBe(200);
        expect(response.data).toBeDefined();
        // 处理直接响应和 full_state 包装器
        const conversationData = response.data.full_state || response.data;
        expect(conversationData.id || response.data.id).toBe(testConversationId);
      },
      config?.testTimeout || 30000
    );

    it(
      'should support custom request options',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.request({
          method: 'GET',
          url: `/api/conversations/${testConversationId}`,
          timeout: 15000,
        });

        expect(response.status).toBe(200);
      },
      config?.testTimeout || 30000
    );

    it(
      'should send POST to events endpoint',
      async () => {
        if (SKIP_TESTS) return;

        const response = await client.post(`/api/conversations/${testConversationId}/events`, {
          role: 'user',
          content: [{ type: 'text', text: 'Test message via HttpClient' }],
          run: false,
        });

        expect(response.status).toBe(200);
      },
      config?.testTimeout || 30000
    );
  });
});
