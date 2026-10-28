/**
 * RemoteConversation 的集成测试和对话
 *
 * 测试对话生命周期，包括创建、发送消息、
 * 运行智能体，并接收针对真实智能体服务器的事件。
 *
 * 注意：默认情况下会跳过此文件中的一些测试，因为它们依赖于
 * LLM 行为是不确定的并且可能很慢。
 */

import {
  Conversation,
  RemoteConversation,
  Workspace,
  Agent,
  Event,
  AgentExecutionStatus,
} from '../../index';
import { getTestConfig, skipIfNoConfig, createTestLLMConfig } from './test-config';
import {
  waitFor,
  waitForAgentIdle,
  sleep,
  workspaceFileExists,
  readWorkspaceFile,
  deleteWorkspaceFile,
  uniqueFileName,
} from './test-utils';

const SKIP_TESTS = skipIfNoConfig();
// 跳过依赖于 CI 中的 LLM 行为的不稳定测试
const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';

describe('Conversation Integration Tests', () => {
  let config: ReturnType<typeof getTestConfig>;

  beforeAll(() => {
    if (SKIP_TESTS) {
      console.warn('Skipping integration tests: LLM_API_KEY and LLM_MODEL not set');
      return;
    }
    config = getTestConfig();
  });

  describe('Conversation Creation', () => {
    it(
      'should create a new conversation',
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

        // 开始对话
        await conversation.start();

        expect(conversation).toBeInstanceOf(RemoteConversation);
        expect(conversation.id).toBeDefined();
        expect(typeof conversation.id).toBe('string');
        expect(conversation.id.length).toBeGreaterThan(0);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );

    it(
      'should create conversation with initial message',
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

        // 从初始消息开始
        await conversation.start({
          initialMessage: 'Hello, this is an initial message.',
          maxIterations: 5,
        });

        expect(conversation.id).toBeDefined();

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Conversation State', () => {
    it(
      'should access conversation state after creation',
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

        // 访问状态
        const state = conversation.state;
        expect(state).toBeDefined();
        expect(state.id).toBe(conversation.id);

        // 获取智能体状态
        const status = await state.getAgentStatus();
        expect(Object.values(AgentExecutionStatus)).toContain(status);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );

    it(
      'should get conversation stats',
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

        const stats = await conversation.conversationStats();
        expect(stats).toBeDefined();

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Sending Messages', () => {
    it(
      'should send a string message',
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

        // 发送消息（不应该抛出）
        await conversation.sendMessage('What is 2 + 2?');

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );

    it(
      'should send a Message object',
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

        // 作为 Message 对象发送消息
        await conversation.sendMessage({
          role: 'user',
          content: [{ type: 'text', text: 'Hello from Message object' }],
        });

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Running Agent', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should run the agent after sending a message',
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

        // 发送一条简单的消息
        await conversation.sendMessage('Reply with only the word "ACKNOWLEDGED".');

        // 运行智能体
        await conversation.run();

        // 等待智能体完成（投票状态）
        await waitForAgentIdle(async () => {
          return await conversation.state.getAgentStatus();
        });

        const finalStatus = await conversation.state.getAgentStatus();
        expect([AgentExecutionStatus.IDLE, AgentExecutionStatus.FINISHED]).toContain(finalStatus);

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    it(
      'should pause the agent',
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
        await conversation.start({ maxIterations: 50 });

        // 发送消息可能需要一段时间
        await conversation.sendMessage('Count from 1 to 100, saying each number.');

        // 运行智能体
        await conversation.run();

        // 稍等一下然后暂停
        await sleep(1000);

        // 暂停（不应抛出，即使智能体空闲）
        await conversation.pause();

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Event Handling with Callbacks', () => {
    it(
      'should receive events via callback',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const receivedEvents: Event[] = [];
        const callback = (event: Event) => {
          receivedEvents.push(event);
        };

        const conversation = new Conversation(agent, workspace, { callback });
        await conversation.start({ maxIterations: 10 });

        // 启动 WebSocket 客户端进行事件
        await conversation.startWebSocketClient();

        // 稍等片刻以建立连接
        await sleep(500);

        // 发送消息并运行
        await conversation.sendMessage('Say "Hello Test!" exactly.');
        await conversation.run();

        // 等待智能体完成
        await waitForAgentIdle(async () => {
          return await conversation.state.getAgentStatus();
        });

        // 等待接收事件
        await sleep(2000);

        // 应该收到一些事件
        expect(receivedEvents.length).toBeGreaterThan(0);

        // 清理
        await conversation.stopWebSocketClient();
        await conversation.close();
      },
      config?.testTimeout || 120000
    );

    it(
      'should track different event types',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const eventTypes = new Set<string>();
        const callback = (event: Event) => {
          eventTypes.add(event.kind);
        };

        const conversation = new Conversation(agent, workspace, { callback });
        await conversation.start({ maxIterations: 10 });

        await conversation.startWebSocketClient();
        await sleep(500);

        await conversation.sendMessage('What time is it?');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getAgentStatus();
        });

        await sleep(2000);

        // 应该收到多种事件类型
        expect(eventTypes.size).toBeGreaterThan(0);

        // 清理
        await conversation.stopWebSocketClient();
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Events List', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should fetch events from conversation state',
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

        await conversation.sendMessage('Just say "OK".');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getAgentStatus();
        });

        // 从状态获取事件
        const events = await conversation.state.events.getEvents();
        expect(events.length).toBeGreaterThan(0);

        // 事件应该具有必需的属性
        for (const event of events) {
          expect(event.id).toBeDefined();
          expect(event.kind).toBeDefined();
          expect(event.timestamp).toBeDefined();
        }

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Title Generation', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should generate a conversation title',
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

        // 发送有关特定主题的消息
        await conversation.sendMessage('Tell me about TypeScript testing best practices.');
        await conversation.run();

        await waitForAgentIdle(async () => {
          return await conversation.state.getAgentStatus();
        });

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Secrets', () => {
    it(
      'should update secrets',
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

        // 更新机密（不应该抛出）
        await conversation.updateSecrets({
          TEST_SECRET: 'test-value',
          ANOTHER_SECRET: () => 'dynamic-value',
        });

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 60000
    );
  });

  describe('Agent Task Execution', () => {
    // 跳过依赖于 CI 中的 LLM 行为的不稳定测试
    const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should execute task that creates a file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('agent-created');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;
        const expectedContent = 'Hello from the agent!';

        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        // 要求智能体创建文件
        await conversation.sendMessage(
          `Create a file at "${fullPath}" with exactly this content: "${expectedContent}". Use the terminal tool to create the file with echo.`
        );
        await conversation.run();

        // 等待智能体完成
        await waitForAgentIdle(
          async () => {
            return await conversation.state.getAgentStatus();
          },
          { timeout: 90000 }
        );

        // 等待文件系统同步
        await sleep(1000);

        // 检查文件是否在已安装的工作区中创建
        const fileExists = workspaceFileExists(fileName);
        expect(fileExists).toBe(true);

        if (fileExists) {
          const content = readWorkspaceFile(fileName);
          expect(content.trim()).toContain(expectedContent);
          deleteWorkspaceFile(fileName);
        }

        // 清理
        await conversation.close();
      },
      config?.testTimeout || 180000
    );

    it(
      'should execute task that reads an existing file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('to-read');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;
        const fileContent = 'This file contains the secret number: 42';

        // 首先创建文件
        const agent = new Agent({
          llm: createTestLLMConfig(),
        });

        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        // 通过工作区创建文件
        await workspace.uploadText(fileContent, fullPath, fileName);
        await sleep(500);

        const receivedEvents: Event[] = [];
        const callback = (event: Event) => {
          receivedEvents.push(event);
        };

        const conversation = new Conversation(agent, workspace, { callback });
        await conversation.start({ maxIterations: 20 });
        await conversation.startWebSocketClient();
        await sleep(500);

        // 要求智能体读取该文件并告诉我们其中的内容
        await conversation.sendMessage(
          `Read the file at "${fullPath}" and tell me what secret number is mentioned in it.`
        );
        await conversation.run();

        // 等待智能体完成
        await waitForAgentIdle(
          async () => {
            return await conversation.state.getAgentStatus();
          },
          { timeout: 90000 }
        );

        // 等待活动
        await sleep(2000);

        // 检查智能体是否收到事件（指示活动）
        expect(receivedEvents.length).toBeGreaterThan(0);

        // 查找可能包含答案的消息事件
        const messageEvents = receivedEvents.filter((e) => e.kind === 'MessageEvent');
        expect(messageEvents.length).toBeGreaterThan(0);

        // 清理
        deleteWorkspaceFile(fileName);
        await conversation.stopWebSocketClient();
        await conversation.close();
      },
      config?.testTimeout || 180000
    );
  });
});
