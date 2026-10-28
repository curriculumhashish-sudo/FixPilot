/**
 * OpenHands Agent Server TypeScript 客户端的基本使用示例
 */

import { Conversation, Agent, Workspace, AgentExecutionStatus } from '../src/index.js';

async function main() {
  // 定义智能体配置
  // 注意：在浏览器环境中，您可以从应用程序的配置中获取这些值
  const agent = new Agent({
    llm: {
      model: 'gpt-4',
      api_key: 'your-openai-api-key', // 替换为您实际的 API 键
    },
  });

  try {
    // 创建远程工作区
    const workspace = new Workspace({
      host: 'http://localhost:3000',
      workingDir: '/tmp',
      apiKey: 'your-session-api-key', // 替换为您的实际会话 API 键
    });

    // 创建新对话
    console.log('Creating conversation...');
    const conversation = new Conversation(agent, workspace, {
      callback: (event) => {
        console.log(`Event received: ${event.kind} at ${event.timestamp}`);
      },
    });

    // 用初始消息开始对话
    await conversation.start({
      initialMessage: 'Hello! Can you help me write a simple Python script?',
    });

    console.log(`Conversation created with ID: ${conversation.id}`);

    // 开始 WebSocket 获取实时事件
    await conversation.startWebSocketClient();
    console.log('WebSocket client started');

    // 发送消息
    await conversation.sendMessage('Create a Python script that prints "Hello, World!"');
    console.log('Message sent');

    // 运行智能体
    await conversation.run();
    console.log('Agent started');

    // 监控通话状态
    let status = await conversation.state.getAgentStatus();
    console.log(`Initial status: ${status}`);

    // 等待智能体完成（在实际应用程序中，您会以不同的方式处理此问题）
    while (status === AgentExecutionStatus.RUNNING) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      status = await conversation.state.getAgentStatus();
      console.log(`Current status: ${status}`);
    }

    // 获取会话统计信息
    const stats = await conversation.conversationStats();
    console.log('Conversation stats:', stats);

    // 获取所有事件
    const events = await conversation.state.events.getEvents();
    console.log(`Total events: ${events.length}`);

    // 使用工作区的示例
    const result = await conversation.workspace.executeCommand('ls -la');
    console.log('Command result:', {
      exitCode: result.exit_code,
      stdout: result.stdout.substring(0, 200) + '...', // 截断显示
    });

    // 清理
    await conversation.close();
    console.log('Conversation closed');
  } catch (error) {
    console.error('Error:', error);
  }
}

// 加载现有对话的示例
async function loadExistingConversation() {
  const agent = new Agent({
    llm: {
      model: 'gpt-4',
      api_key: 'your-openai-api-key', // 替换为您实际的 API 键
    },
  });

  try {
    // 为现有对话创建远程工作区
    const workspace = new Workspace({
      host: 'http://localhost:3000',
      workingDir: '/tmp',
      apiKey: 'your-session-api-key', // 替换为您的实际会话 API 键
    });

    const conversation = new Conversation(agent, workspace, {
      conversationId: 'existing-conversation-id',
    });

    // 连接到现有对话
    await conversation.start();

    console.log(`Loaded conversation: ${conversation.id}`);

    // 获取当前状态
    const status = await conversation.state.getAgentStatus();
    console.log(`Status: ${status}`);

    // 清理
    await conversation.close();
  } catch (error) {
    console.error('Error loading conversation:', error);
  }
}

// 运行示例
// 注意：在浏览器环境中，您可以直接调用 main() 或从事件处理程序调用
// 对于Node.js环境，您可以使用import.meta.main（ES模块）或检查这是否是主模块
main().catch(console.error);
