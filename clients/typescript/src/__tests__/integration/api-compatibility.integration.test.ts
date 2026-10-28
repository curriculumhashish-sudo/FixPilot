/**
 * 集成测试用于 API 与智能体服务器兼容
 *
 * 这些测试验证 TypeScript 客户端是否正确处理
 * 不兼容变更不同版本的智能体-服务器 API 之间。
 *
 * 测试的关键更改：
 * - AgentExecutionStatus -> ConversationExecutionStatus 重命名
 * - agent_status -> execution_status 字段重命名
 * - 新端点：ask_agent、压缩、security_analyzer
 * - 新的事件搜索过滤器：源、正文、timestamp__gte、timestamp__lt
 *
 * 注意：默认情况下会跳过此文件中的一些测试，因为它们依赖于
 * LLM 行为是不确定的并且可能很慢。
 */

import {
  Conversation,
  Workspace,
  Agent,
  ConversationExecutionStatus,
  AgentExecutionStatus,
} from '../../index';
import { getTestConfig, skipIfNoConfig, createTestLLMConfig } from './test-config';
import { waitForAgentIdle, sleep } from './test-utils';

const SKIP_TESTS = skipIfNoConfig();
// 跳过依赖于 CI 中的 LLM 行为的不稳定测试
const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';

describe('API Compatibility Integration Tests', () => {
  let config: ReturnType<typeof getTestConfig>;

  beforeAll(() => {
    if (SKIP_TESTS) {
      console.warn('Skipping integration tests: LLM_API_KEY and LLM_MODEL not set');
      return;
    }
    config = getTestConfig();
  });

  describe('ConversationExecutionStatus Enum', () => {
    it('should have all expected status values', () => {
      // 验证枚举具有所有预期值
      expect(ConversationExecutionStatus.IDLE).toBe('idle');
      expect(ConversationExecutionStatus.RUNNING).toBe('running');
      expect(ConversationExecutionStatus.PAUSED).toBe('paused');
      expect(ConversationExecutionStatus.WAITING_FOR_CONFIRMATION).toBe('waiting_for_confirmation');
      expect(ConversationExecutionStatus.FINISHED).toBe('finished');
      expect(ConversationExecutionStatus.ERROR).toBe('error');
      expect(ConversationExecutionStatus.STUCK).toBe('stuck');
      expect(ConversationExecutionStatus.DELETING).toBe('deleting');
    });

    it('should have AgentExecutionStatus as an alias', () => {
      // 验证向后兼容性别名
      expect(AgentExecutionStatus).toBe(ConversationExecutionStatus);
      expect(AgentExecutionStatus.IDLE).toBe('idle');
    });
  });

  describe('Execution Status Field', () => {
    it(
      'should get execution status using getExecutionStatus()',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start();

        // 使用新方法
        const status = await conversation.state.getExecutionStatus();
        expect(Object.values(ConversationExecutionStatus)).toContain(status);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );

    it(
      'should get execution status using deprecated getAgentStatus()',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start();

        // 使用已弃用方法（应该仍然有效）
        const status = await conversation.state.getAgentStatus();
        expect(Object.values(ConversationExecutionStatus)).toContain(status);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('New API Endpoints', () => {
    // 跳过依赖于 CI 中的 LLM 行为的不稳定测试
    const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should call askAgent endpoint',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 先发送消息建立上下文
        await conversation.sendMessage('Hello, I am testing the API.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 问一个简单的问题
        const response = await conversation.askAgent('What is 2 + 2?');
        expect(response).toBeDefined();
        expect(typeof response).toBe('string');
        expect(response.length).toBeGreaterThan(0);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    // 跳过：压缩端点可能不适用于所有智能体服务器版本
    it.skip(
      'should call condense endpoint',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 发送消息以创造一些历史
        await conversation.sendMessage('Hello, this is a test message.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 调用 condense （不应该抛出）
        await conversation.condense();

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    // 跳过：setSecurityAnalyzer 端点可能不适用于所有智能体服务器版本
    it.skip(
      'should call setSecurityAnalyzer endpoint',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 5 });

        // 将安全分析器设置为 null（不应抛出）
        await conversation.setSecurityAnalyzer(null);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Event Search Filters', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should search events with kind filter',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 发送消息并运行
        await conversation.sendMessage('Say hello.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 搜索 MessageEvent 种
        const result = await conversation.state.events.search({
          kind: 'MessageEvent',
          limit: 10,
        });

        expect(result).toBeDefined();
        expect(result.items).toBeDefined();
        expect(Array.isArray(result.items)).toBe(true);

        // 所有返回的事件应为 MessageEvent
        for (const event of result.items) {
          expect(event.kind).toBe('MessageEvent');
        }

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    // 跳过：所有智能体-服务器版本可能不完全支持源过滤器
    // 即使按源过滤，服务器也可能返回来自其他源的事件
    it.skip(
      'should search events with source filter',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 发送消息并运行
        await conversation.sendMessage('Hello from user.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 搜索用户事件
        const result = await conversation.state.events.search({
          source: 'user',
          limit: 10,
        });

        expect(result).toBeDefined();
        expect(result.items).toBeDefined();
        expect(Array.isArray(result.items)).toBe(true);

        // 所有返回的事件都应具有源“用户”
        for (const event of result.items) {
          expect(event.source).toBe('user');
        }

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    testFn(
      'should count events with filters',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 发送消息并运行
        await conversation.sendMessage('Test message for counting.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 统计所有事件
        const totalCount = await conversation.state.events.count();
        expect(totalCount).toBeGreaterThan(0);

        // 计数 MessageEvent 个事件
        const messageCount = await conversation.state.events.count({
          kind: 'MessageEvent',
        });
        expect(messageCount).toBeGreaterThanOrEqual(0);
        expect(messageCount).toBeLessThanOrEqual(totalCount);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    testFn(
      'should search events with timestamp filters',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 记录开始时间
        const startTime = new Date().toISOString();

        // 发送消息并运行
        await conversation.sendMessage('Test message with timestamp.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 稍等一下
        await sleep(100);

        // 记录结束时间
        const endTime = new Date().toISOString();

        // 搜索时间范围内的事件
        const result = await conversation.state.events.search({
          timestamp__gte: startTime,
          timestamp__lt: endTime,
          limit: 100,
        });

        expect(result).toBeDefined();
        expect(result.items).toBeDefined();
        expect(Array.isArray(result.items)).toBe(true);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    testFn(
      'should search events with sort order',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 10 });

        // 发送消息并运行
        await conversation.sendMessage('Test message for sorting.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getExecutionStatus();
        });

        // 按升序搜索
        const ascResult = await conversation.state.events.search({
          sort_order: 'TIMESTAMP',
          limit: 10,
        });

        // 按降序搜索
        const descResult = await conversation.state.events.search({
          sort_order: 'TIMESTAMP_DESC',
          limit: 10,
        });

        expect(ascResult.items).toBeDefined();
        expect(descResult.items).toBeDefined();

        // 如果我们有多个事件，请验证顺序是否不同
        if (ascResult.items.length > 1 && descResult.items.length > 1) {
          // 升序排列的第一个事件应该是最旧的降序排列的第一个事件应该是最新的
          //
          expect(ascResult.items[0].id).not.toBe(descResult.items[0].id);
        }

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });
});
