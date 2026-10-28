/**
 * 完整智能体工作流程的端到端集成测试
 *
 * 测试从任务到完成的完整场景，验证实际情况
 * 已安装的工作区发生变化。
 *
 * 注意：默认情况下会跳过此文件中的许多测试，因为它们依赖于
 * LLM 行为是不确定的并且可能很慢。 这些测试是
 * 对于本地开发和手动验证有用但不适合
 * 由于其片状性质，CI。
 *
 * 要在本地运行所有测试（包括跳过的测试）：
 * - 在您的环境中设置 SKIP_FLAKY_TESTS=False
 * - 确保您有有效的 LLM 凭据
 */

import { Conversation, Workspace, Agent, Event, AgentExecutionStatus } from '../../index';
import { getTestConfig, skipIfNoConfig, createTestLLMConfig } from './test-config';
import {
  waitForAgentIdle,
  sleep,
  workspaceFileExists,
  readWorkspaceFile,
  writeWorkspaceFile,
  deleteWorkspaceFile,
  uniqueFileName,
  uniqueDirName,
  randomContent,
} from './test-utils';
import * as fs from 'fs';
import * as path from 'path';

const SKIP_TESTS = skipIfNoConfig();
// 跳过依赖于 CI 中的 LLM 行为的不稳定测试
const SKIP_FLAKY_TESTS = process.env.SKIP_FLAKY_TESTS !== 'false';

describe('End-to-End Integration Tests', () => {
  let config: ReturnType<typeof getTestConfig>;

  beforeAll(() => {
    if (SKIP_TESTS) {
      console.warn('Skipping integration tests: LLM_API_KEY and LLM_MODEL not set');
      return;
    }
    config = getTestConfig();
  });

  describe('File Creation Tasks', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should create a simple text file via agent',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-create');
        const expectedContent = 'Hello from e2e test';
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Create a file at "${fullPath}" containing exactly this text: "${expectedContent}". ` +
            `Use echo command to create it.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName)).toBe(true);
        const content = readWorkspaceFile(fileName);
        expect(content.trim()).toContain(expectedContent);

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 180000
    );

    testFn(
      'should create a Python file with specific content',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-python', 'py');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Create a Python file at "${fullPath}" that defines a function called "add" ` +
            `which takes two parameters and returns their sum.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName)).toBe(true);
        const content = readWorkspaceFile(fileName);
        expect(content).toContain('def add');
        expect(content).toContain('return');

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 180000
    );

    testFn(
      'should create a JSON file with structured data',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-json', 'json');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Create a JSON file at "${fullPath}" with an object containing: ` +
            `name="test", version="1.0.0", and tags array with "typescript" and "testing".`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName)).toBe(true);
        const content = readWorkspaceFile(fileName);
        const parsed = JSON.parse(content);
        expect(parsed.name).toBe('test');
        expect(parsed.version).toBe('1.0.0');
        expect(parsed.tags).toContain('typescript');
        expect(parsed.tags).toContain('testing');

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 180000
    );
  });

  describe('File Modification Tasks', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should read and modify an existing file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-modify');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;
        const originalContent = 'Line 1\nLine 2\nLine 3';

        // 创建原始文件
        writeWorkspaceFile(fileName, originalContent);

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 25 });

        await conversation.sendMessage(
          `Read the file at "${fullPath}" and add a new line "Line 4" at the end.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        const modifiedContent = readWorkspaceFile(fileName);
        expect(modifiedContent).toContain('Line 1');
        expect(modifiedContent).toContain('Line 4');

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 180000
    );

    testFn(
      'should append to an existing file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-append');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;
        const originalContent = 'Original content.';

        writeWorkspaceFile(fileName, originalContent);

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Append the text " Appended content." to the file at "${fullPath}" using echo with >>.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        const content = readWorkspaceFile(fileName);
        expect(content).toContain('Original content');
        expect(content).toContain('Appended content');

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 180000
    );
  });

  describe('File Deletion Tasks', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should delete an existing file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-delete');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;
        writeWorkspaceFile(fileName, 'Content to delete');

        expect(workspaceFileExists(fileName)).toBe(true);

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 15 });

        await conversation.sendMessage(`Delete the file at "${fullPath}" using the rm command.`);
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName)).toBe(false);

        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Directory Operations', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should create a directory and file inside it',
      async () => {
        if (SKIP_TESTS) return;

        const dirName = uniqueDirName('e2e-dir');
        const fileName = 'test.txt';
        const fullDirPath = `${config.agentWorkspaceDir}/${dirName}`;
        const fullFilePath = `${fullDirPath}/${fileName}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Create a directory at "${fullDirPath}" and create a file at "${fullFilePath}" ` +
            `with the content "File in directory".`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 120000,
        });

        await sleep(1000);

        const filePath = path.join(dirName, fileName);
        expect(workspaceFileExists(filePath)).toBe(true);
        const content = readWorkspaceFile(filePath);
        expect(content).toContain('File in directory');

        // 清理
        deleteWorkspaceFile(filePath);
        const hostDirPath = path.join(config.hostWorkspaceDir, dirName);
        if (fs.existsSync(hostDirPath)) {
          fs.rmSync(hostDirPath, { recursive: true });
        }

        await conversation.close();
      },
      config?.testTimeout || 180000
    );

    testFn(
      'should list directory contents',
      async () => {
        if (SKIP_TESTS) return;

        // 创建一些文件
        const file1 = uniqueFileName('list1');
        const file2 = uniqueFileName('list2');
        writeWorkspaceFile(file1, 'Content 1');
        writeWorkspaceFile(file2, 'Content 2');

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const receivedEvents: Event[] = [];
        const conversation = new Conversation(agent, workspace, {
          callback: (e) => receivedEvents.push(e),
        });
        await conversation.start({ maxIterations: 15 });
        await conversation.startWebSocketClient();
        await sleep(500);

        await conversation.sendMessage(`List all files in the current directory using ls command.`);
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        await sleep(2000);

        // 检查我们是否通过 ls 输出收到了观测结果事件
        const obsEvents = receivedEvents.filter((e) => e.kind === 'ObservationEvent');
        expect(obsEvents.length).toBeGreaterThan(0);

        // 清理
        deleteWorkspaceFile(file1);
        deleteWorkspaceFile(file2);

        await conversation.stopWebSocketClient();
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Multi-step Tasks', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should complete a task with multiple steps',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-multistep', 'txt');
        const fullPath = `${config.agentWorkspaceDir}/${fileName}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 30 });

        await conversation.sendMessage(
          `Do the following steps:
          1. Create a file at "${fullPath}" with the content "Step 1 done"
          2. Append " - Step 2 done" to the file
          3. Read the file and confirm it contains both steps`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 150000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName)).toBe(true);
        const content = readWorkspaceFile(fileName);
        expect(content).toContain('Step 1');
        expect(content).toContain('Step 2');

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 240000
    );
  });

  describe('Error Recovery', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should handle requests for non-existent files gracefully',
      async () => {
        if (SKIP_TESTS) return;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const receivedEvents: Event[] = [];
        const conversation = new Conversation(agent, workspace, {
          callback: (e) => receivedEvents.push(e),
        });
        await conversation.start({ maxIterations: 15 });
        await conversation.startWebSocketClient();
        await sleep(500);

        await conversation.sendMessage(
          `Try to read the file "definitely-does-not-exist-${Date.now()}.txt" and ` +
            `report whether it exists or not.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        await sleep(2000);

        // 智能体应该已完成（未崩溃）- 错误也是可以接受的
        const finalStatus = await conversation.state.getAgentStatus();
        expect([
          AgentExecutionStatus.IDLE,
          AgentExecutionStatus.FINISHED,
          AgentExecutionStatus.ERROR,
        ]).toContain(finalStatus);

        await conversation.stopWebSocketClient();
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });

  describe('Conversation Continuation', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should continue conversation with follow-up messages',
      async () => {
        if (SKIP_TESTS) return;

        const fileName1 = uniqueFileName('e2e-cont1');
        const fileName2 = uniqueFileName('e2e-cont2');
        const fullPath1 = `${config.agentWorkspaceDir}/${fileName1}`;
        const fullPath2 = `${config.agentWorkspaceDir}/${fileName2}`;

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 40 });

        // 第一个任务
        await conversation.sendMessage(
          `Create a file at "${fullPath1}" with content "First file".`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        expect(workspaceFileExists(fileName1)).toBe(true);

        // 同一对话中的第二个任务
        await conversation.sendMessage(
          `Now create another file at "${fullPath2}" with content "Second file".`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        await sleep(1000);

        expect(workspaceFileExists(fileName2)).toBe(true);

        // 两个文件都应该存在
        expect(workspaceFileExists(fileName1)).toBe(true);
        expect(workspaceFileExists(fileName2)).toBe(true);

        // 清理
        deleteWorkspaceFile(fileName1);
        deleteWorkspaceFile(fileName2);
        await conversation.close();
      },
      config?.testTimeout || 240000
    );
  });

  describe('Large Content Handling', () => {
    // 这些测试不稳定，因为它们依赖于 LLM 行为
    const testFn = SKIP_FLAKY_TESTS ? it.skip : it;

    testFn(
      'should handle reading a large file',
      async () => {
        if (SKIP_TESTS) return;

        const fileName = uniqueFileName('e2e-large');
        // 创建一个多行文件
        const lines = Array.from({ length: 50 }, (_, i) => `Line ${i + 1}: ${randomContent(50)}`);
        writeWorkspaceFile(fileName, lines.join('\n'));

        const agent = new Agent({ llm: createTestLLMConfig() });
        const workspace = new Workspace({
          host: config.agentServerUrl,
          workingDir: config.agentWorkspaceDir,
        });

        const conversation = new Conversation(agent, workspace);
        await conversation.start({ maxIterations: 20 });

        await conversation.sendMessage(
          `Read the file "${fileName}" and tell me how many lines it has.`
        );
        await conversation.run();

        await waitForAgentIdle(async () => await conversation.state.getAgentStatus(), {
          timeout: 90000,
        });

        // 智能体应该成功完成
        const finalStatus = await conversation.state.getAgentStatus();
        expect([AgentExecutionStatus.IDLE, AgentExecutionStatus.FINISHED]).toContain(finalStatus);

        deleteWorkspaceFile(fileName);
        await conversation.close();
      },
      config?.testTimeout || 120000
    );
  });
});
