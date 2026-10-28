import { Settings } from '../components/SettingsModal';
import { HttpClient, RemoteConversation, RemoteWorkspace } from '@openhands/agent-server-typescript-client';

export interface ServerStatus {
  isConnected: boolean;
  connectionError?: string;
  llmStatus: 'unknown' | 'working' | 'error';
  llmError?: string;
  lastChecked: Date;
}

export interface HealthCheckResponse {
  status: string;
  timestamp: string;
  version?: string;
}

export interface LLMTestResponse {
  success: boolean;
  response?: string;
  error?: string;
}

/**
 * 使用 SDK 检查是否可以到达 Agent Server
 */
export const checkServerHealth = async (serverUrl: string, apiKey?: string): Promise<{ isConnected: boolean; error?: string }> => {
  try {
    const client = new HttpClient({ baseUrl: serverUrl, apiKey });
    
    // 使用SDK的HTTP客户端检查健康状况
    await client.get('/health');
    
    return { isConnected: true };
  } catch (error) {
    if (error instanceof Error) {
      return { isConnected: false, error: error.message };
    }
    return { isConnected: false, error: 'Unknown connection error' };
  }
};

/**
 * 使用 SDK 测试 LLM 配置
 */
export const testLLMConfiguration = async (settings: Settings): Promise<{ success: boolean; error?: string }> => {
  try {
    // 首先检查服务器是否可达
    const healthCheck = await checkServerHealth(settings.agentServerUrl, settings.agentServerApiKey);
    if (!healthCheck.isConnected) {
      return { success: false, error: `Server not reachable: ${healthCheck.error}` };
    }

    // 为测试对话创建工作区
    const workspace = new RemoteWorkspace({
      host: settings.agentServerUrl,
      workingDir: '/tmp/test-workspace',
      apiKey: settings.agentServerApiKey,
    });

    // 使用 SDK 创建测试对话
    const conversation = new RemoteConversation(
      {
        kind: 'Agent',
        llm: {
          model: settings.modelName,
          api_key: settings.apiKey,
        }
      },
      workspace
    );

    await conversation.start();

    try {
      // 发送一条简单的测试消息来验证 LLM 配置
      await conversation.sendMessage({
        role: 'user',
        content: [{ type: 'text', text: 'Hello, respond with just "OK" to confirm you are working.' }]
      });
      
      // 如果我们到达这里，则 LLM 配置正在工作
      return { success: true };
      
    } finally {
      // 始终尝试清理测试对话
      try {
        await conversation.close();
      } catch {
        // 忽略清理错误
      }
    }
  } catch (error) {
    if (error instanceof Error) {
      return { success: false, error: error.message };
    }
    return { success: false, error: 'Unknown LLM test error' };
  }
};

/**
 * 获取全面的服务器状态
 */
export const getServerStatus = async (settings: Settings): Promise<ServerStatus> => {
  const startTime = new Date();
  
  // 检查服务器连接
  const healthCheck = await checkServerHealth(settings.agentServerUrl, settings.agentServerApiKey);
  
  let llmStatus: 'unknown' | 'working' | 'error' = 'unknown';
  let llmError: string | undefined;
  
  // 检查是否配置了LLM设置
  if (!settings.apiKey || !settings.modelName) {
    llmStatus = 'unknown';
    llmError = 'LLM API key or model name not configured';
  } else if (!healthCheck.isConnected) {
    // 设置已配置但无法访问服务器
    llmStatus = 'unknown';
    llmError = 'Cannot test LLM configuration - server not reachable';
  } else {
    // 服务器可访问并且设置已配置 - 测试 LLM
    const llmTest = await testLLMConfiguration(settings);
    llmStatus = llmTest.success ? 'working' : 'error';
    llmError = llmTest.error;
  }

  return {
    isConnected: healthCheck.isConnected,
    connectionError: healthCheck.error,
    llmStatus,
    llmError,
    lastChecked: startTime,
  };
};