import React, { useState, useEffect } from 'react';
import { 
  ConversationManager as SDKConversationManager,
  ConversationInfo,
  Conversation,
  RemoteConversation,
  Agent,
  Workspace,
  Event
} from '@openhands/agent-server-typescript-client';
import { useSettings } from '../contexts/SettingsContext';

interface ConversationData extends ConversationInfo {
  remoteConversation?: RemoteConversation;
  events?: Event[];
}

// 从事件中提取可显示内容的实用函数
const getEventDisplayContent = (event: Event): { title: string; content: string; details?: any } => {
  switch (event.kind) {
    case 'MessageEvent':
      const messageEvent = event as any;
      const message = messageEvent.llm_message;
      if (message && message.content && Array.isArray(message.content)) {
        const textContent = message.content
          .filter((c: any) => c.type === 'text')
          .map((c: any) => c.text)
          .join(' ');
        return {
          title: `Message from ${messageEvent.source || 'unknown'}`,
          content: textContent || 'No text content',
          details: message
        };
      }
      return {
        title: `Message from ${messageEvent.source || 'unknown'}`,
        content: 'No message content available',
        details: messageEvent
      };
    
    case 'ActionEvent':
      const actionEvent = event as any;
      const action = actionEvent.action;
      return {
        title: `Action: ${action?.kind || 'Unknown Action'}`,
        content: action?.command || action?.content || JSON.stringify(action, null, 2),
        details: action
      };
    
    case 'ObservationEvent':
      const obsEvent = event as any;
      return {
        title: `Observation: ${obsEvent.tool_name || 'Unknown Tool'}`,
        content: typeof obsEvent.observation === 'string' 
          ? obsEvent.observation 
          : JSON.stringify(obsEvent.observation, null, 2),
        details: obsEvent.observation
      };
    
    case 'AgentErrorEvent':
      const errorEvent = event as any;
      return {
        title: `Error: ${errorEvent.tool_name || 'Unknown Tool'}`,
        content: typeof errorEvent.observation === 'string' 
          ? errorEvent.observation 
          : JSON.stringify(errorEvent.observation, null, 2),
        details: errorEvent.observation
      };
    
    case 'SystemPromptEvent':
      const sysEvent = event as any;
      return {
        title: 'System Prompt',
        content: sysEvent.system_prompt?.text || 'System prompt updated',
        details: sysEvent.system_prompt
      };
    
    case 'PauseEvent':
      return {
        title: 'Agent Paused',
        content: 'Agent execution was paused',
        details: null
      };
    
    default:
      return {
        title: event.kind || 'Unknown Event',
        content: JSON.stringify(event, null, 2),
        details: event
      };
  }
};

export const ConversationManager: React.FC = () => {
  const { settings } = useSettings();
  const [conversations, setConversations] = useState<ConversationData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manager, setManager] = useState<SDKConversationManager | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messageInput, setMessageInput] = useState('');
  const [showAllEvents, setShowAllEvents] = useState(false);

  // 获取选定的对话数据
  const selectedConversation = conversations.find(c => c.id === selectedConversationId);

  // 初始化对话管理器
  useEffect(() => {
    if (settings.agentServerUrl) {
      const conversationManager = new SDKConversationManager({
        host: settings.agentServerUrl,
        apiKey: settings.agentServerApiKey
      });
      setManager(conversationManager);
      loadConversations(conversationManager);
    }
  }, [settings.agentServerUrl, settings.agentServerApiKey]);

  // 卸载时清理 WebSocket 个连接
  useEffect(() => {
    return () => {
      if (selectedConversation?.remoteConversation) {
        selectedConversation.remoteConversation.stopWebSocketClient().catch((err: any) => {
          console.warn('Failed to stop WebSocket client on unmount:', err);
        });
      }
    };
  }, [selectedConversation?.remoteConversation]);

  // 定期刷新运行对话的状态
  useEffect(() => {
    if (!selectedConversation?.remoteConversation) return;

    const refreshStatus = async () => {
      try {
        const status = await selectedConversation.remoteConversation!.state.getAgentStatus();
        setConversations(prev => prev.map(conv => 
          conv.id === selectedConversation.id 
            ? { ...conv, status: status }
            : conv
        ));
      } catch (err) {
        console.warn('Failed to refresh agent status:', err);
      }
    };

    // 如果智能体正在运行，则每 2 秒刷新一次
    const interval = setInterval(() => {
      if (selectedConversation.status === 'running') {
        refreshStatus();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [selectedConversation?.id, selectedConversation?.status]);

  const loadConversations = async (conversationManager?: SDKConversationManager) => {
    const mgr = conversationManager || manager;
    if (!mgr) return;

    setLoading(true);
    setError(null);
    try {
      const conversationList = await mgr.getAllConversations();
      console.log('Loaded conversations:', conversationList);
      
      // 转换为我们的数据结构
      const conversationData: ConversationData[] = conversationList.map((conv: ConversationInfo) => ({
        ...conv,
        // 确保我们拥有基本属性
        id: conv.id,
        agent: conv.agent,
        created_at: conv.created_at,
        updated_at: conv.updated_at,
        // 将 agent_status 映射到状态以进行显示
        status: conv.agent_status || conv.status
      }));
      
      setConversations(conversationData);
    } catch (err) {
      console.error('Failed to load conversations:', err);
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  };

  const createConversation = async () => {
    if (!manager) return;

    setLoading(true);
    setError(null);
    try {
      // 创建一个简单的智能体配置
      const agent = new Agent({
        llm: {
          model: settings.modelName,
          api_key: settings.apiKey || ''
        }
      });

      // 创建远程工作区
      const workspace = new Workspace({
        host: manager.host,
        workingDir: '/tmp',
        apiKey: manager.apiKey
      });

      const conversation = new Conversation(agent, workspace, {
        maxIterations: 50,
        callback: (event: Event) => {
          console.log('Received WebSocket event for new conversation:', event);
            
            // 实时更新对话事件
            setConversations(prev => prev.map(conv => {
              if (conv.id === conversation.id && conv.events) {
                const updatedEvents = [...conv.events, event];
                return { ...conv, events: updatedEvents };
              }
              return conv;
            }));
          },
        }
      );

      console.log('Created conversation:', conversation);

      // 使用初始消息开始对话
      await conversation.start({
        initialMessage: 'Hello! I\'m ready to help you with your tasks.'
      });
      
      // 启动WebSocket客户端进行实时更新
      try {
        await conversation.startWebSocketClient();
        console.log('WebSocket client started for new conversation');
      } catch (wsErr) {
        console.warn('Failed to start WebSocket client for new conversation:', wsErr);
      }
      
      // 运行初始消息以开始对话
      try {
        await conversation.run();
        console.log('Started conversation with initial message');
      } catch (runErr) {
        console.warn('Failed to run initial message:', runErr);
      }
      
      // 重新加载对话以显示新对话
      await loadConversations();
    } catch (err) {
      console.error('Failed to create conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
    } finally {
      setLoading(false);
    }
  };

  const deleteConversation = async (conversationId: string) => {
    if (!manager) return;

    setLoading(true);
    setError(null);
    try {
      await manager.deleteConversation(conversationId);
      
      // 如果选择了此对话，则清除选择
      if (selectedConversationId === conversationId) {
        setSelectedConversationId(null);
      }

      // 重新加载对话列表
      await loadConversations();
    } catch (err) {
      console.error('Failed to delete conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete conversation');
    } finally {
      setLoading(false);
    }
  };

  const selectConversation = async (conversationId: string) => {
    if (!manager) return;

    // 清除之前对话的 WebSocket（如果有）
    if (selectedConversation?.remoteConversation) {
      try {
        await selectedConversation.remoteConversation.stopWebSocketClient();
        console.log('Stopped WebSocket client for previous conversation');
      } catch (err) {
        console.warn('Failed to stop previous WebSocket client:', err);
      }
    }

    console.log('Selecting conversation:', conversationId);
    setSelectedConversationId(conversationId);
    
    // 加载对话详细信息
    try {
      // 获取对话信息提取智能体
      const conversationInfo = conversations.find(c => c.id === conversationId);
      if (!conversationInfo) {
        throw new Error('Conversation not found');
      }

      // 创建回调来处理实时事件
      const eventCallback = (event: Event) => {
        console.log('Received WebSocket event:', event);
        
        // 实时更新对话事件
        setConversations(prev => prev.map(conv => {
          if (conv.id === conversationId && conv.events) {
            // 将新事件添加到现有事件中
            const updatedEvents = [...conv.events, event];
            return { ...conv, events: updatedEvents };
          }
          return conv;
        }));
        
        // 如果是状态更改事件，则更新智能体状态
        if (event.type === 'agent_status_change' || event.type === 'agent_state_changed') {
          // 短暂延迟后刷新智能体状态以确保服务器已更新
          setTimeout(() => {
            if (remoteConversation) {
              remoteConversation.state.getAgentStatus().then(status => {
                setConversations(prev => prev.map(conv => 
                  conv.id === conversationId 
                    ? { ...conv, status: status }
                    : conv
                ));
              }).catch(err => console.warn('Failed to update agent status:', err));
            }
          }, 100);
        }
      };
      
      // 为现有对话创建远程工作区
      const workspace = new Workspace({
        host: manager.host,
        workingDir: '/tmp',
        apiKey: manager.apiKey
      });

      // 加载与回调的对话
      const remoteConversation = new Conversation(conversationInfo.agent, workspace, {
        conversationId: conversationId,
        callback: eventCallback,
      });

      // 连接到现有对话
      await remoteConversation.start();
      console.log('Loaded remote conversation:', remoteConversation);
      
      // 启动WebSocket客户端进行实时更新
      try {
        await remoteConversation.startWebSocketClient();
        console.log('WebSocket client started for conversation:', conversationId);
      } catch (wsErr) {
        console.warn('Failed to start WebSocket client:', wsErr);
        // 如果 WebSocket 失败，整个操作不会失败
      }
      
      // 获取事件
      const events = await remoteConversation.state.events.getEvents();
      console.log('Loaded events:', events);
      
      // 获取智能体状态
      const agentStatus = await remoteConversation.state.getAgentStatus();
      console.log('Agent status:', agentStatus);
      
      // 更新我们州的对话并提供更多详细信息
      setConversations(prev => prev.map(conv => 
        conv.id === conversationId 
          ? { ...conv, remoteConversation, events, status: agentStatus }
          : conv
      ));
      
    } catch (err) {
      console.error('Failed to load conversation details:', err);
      setError(err instanceof Error ? err.message : 'Failed to load conversation details');
    }
  };

  const sendMessage = async () => {
    if (!selectedConversation?.remoteConversation || !messageInput.trim()) return;

    try {
      // 发送消息
      await selectedConversation.remoteConversation.sendMessage(messageInput);
      setMessageInput('');
      
      // 启动智能体处理消息（非阻塞）
      await selectedConversation.remoteConversation.run();
      console.log('Agent started to process the message');
      
      // WebSocket 将在智能体工作时接收事件无需立即重新加载 - 事件将通过 WebSocket 发送
      //
    } catch (err) {
      console.error('Failed to send message or start agent:', err);
      setError(err instanceof Error ? err.message : 'Failed to send message or start agent');
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleString();
  };

  const getStatusColorClass = (status?: string) => {
    switch (status) {
      case 'running': return 'text-green-500';
      case 'idle': return 'text-gray-500';
      case 'paused': return 'text-orange-500';
      case 'waiting_for_confirmation': return 'text-yellow-500';
      case 'finished': return 'text-blue-500';
      case 'error': return 'text-red-600';
      case 'stuck': return 'text-red-500';
      default: return 'text-gray-500';
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'running': return '🔄';
      case 'idle': return '⏸️';
      case 'paused': return '⏸️';
      case 'waiting_for_confirmation': return '⏳';
      case 'finished': return '✅';
      case 'error': return '❌';
      case 'stuck': return '🚫';
      default: return '❓';
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 m-0">
      <div className="flex justify-between items-center mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white m-0">Conversation Manager</h2>
        <div className="flex gap-3">
          <button 
            onClick={() => loadConversations()} 
            disabled={loading}
            className="bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-md font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed border border-gray-300 dark:border-gray-600"
          >
            🔄 Refresh
          </button>
          <button 
            onClick={createConversation} 
            disabled={loading}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ➕ New Conversation
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-md p-4 mb-4">
          <span className="text-red-700 dark:text-red-300 font-medium">Error:</span> 
          <span className="text-red-600 dark:text-red-400 ml-2">{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Conversations ({conversations.length})</h3>
          
          {loading && conversations.length === 0 && (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">Loading conversations...</div>
          )}
          
          {conversations.length === 0 && !loading ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>No conversations yet. Create your first conversation!</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {conversations.map((conversation) => (
                <div 
                  key={conversation.id} 
                  className={`border rounded-lg p-3 cursor-pointer transition-all duration-200 flex justify-between items-start ${
                    selectedConversationId === conversation.id 
                      ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 shadow-md' 
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-sm'
                  }`}
                  onClick={() => selectConversation(conversation.id)}
                >
                  <div className="flex-1 min-w-0 text-left">
                    <div className="text-sm font-mono text-gray-600 dark:text-gray-400 mb-2">
                      ID: {conversation.id.substring(0, 8)}...
                    </div>
                    <div className="space-y-1 text-sm">
                      <div className="text-gray-600 dark:text-gray-400">Created: {formatDate(conversation.created_at)}</div>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-600 dark:text-gray-400">Status:</span>
                        <span className={`font-medium ${getStatusColorClass(conversation.status)}`}>
                          {getStatusIcon(conversation.status)} {conversation.status || 'unknown'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <button 
                    className="ml-3 p-2 text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-md transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteConversation(conversation.id);
                    }}
                    disabled={loading}
                    title="Delete conversation"
                  >
                    🗑️
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Conversation Details</h3>
          
          {!selectedConversation ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>Select a conversation to view details</p>
            </div>
          ) : (
            <div className="space-y-6">
              <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                <div className="grid grid-cols-1 gap-3 text-sm">
                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">ID:</span>
                    <span className="text-gray-600 dark:text-gray-400 font-mono text-xs">{selectedConversation.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">Status:</span>
                    <span className={`font-medium ${getStatusColorClass(selectedConversation.status)}`}>
                      {getStatusIcon(selectedConversation.status)} {selectedConversation.status || 'unknown'}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">Model:</span>
                    <span className="text-gray-600 dark:text-gray-400">{selectedConversation.agent.llm?.model || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">Created:</span>
                    <span className="text-gray-600 dark:text-gray-400">{formatDate(selectedConversation.created_at)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">Updated:</span>
                    <span className="text-gray-600 dark:text-gray-400">{formatDate(selectedConversation.updated_at)}</span>
                  </div>

                  <div className="flex justify-between">
                    <span className="font-medium text-gray-900 dark:text-white">Total Events:</span>
                    <span className="text-gray-600 dark:text-gray-400">{selectedConversation.events?.length || 0}</span>
                  </div>
                </div>
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                <div className="flex justify-between items-center mb-3">
                  <h4 className="text-base font-semibold text-gray-900 dark:text-white">Events & Messages</h4>
                  {selectedConversation.events && selectedConversation.events.length > 1 && (
                    <button
                      onClick={() => setShowAllEvents(!showAllEvents)}
                      className="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 font-medium transition-colors duration-200"
                    >
                      {showAllEvents ? '▼ Show Recent Only' : `▶ Show All (${selectedConversation.events.length})`}
                    </button>
                  )}
                </div>
                <div className="max-h-64 overflow-y-auto space-y-3">
                  {selectedConversation.events && selectedConversation.events.length > 0 ? (
                    (() => {
                      // 按时间戳对事件进行排序（最近的在前）
                      const sortedEvents = [...selectedConversation.events].sort((a, b) => 
                        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
                      );
                      
                      // 仅显示最近的事件，除非展开
                      const eventsToShow = showAllEvents ? sortedEvents : sortedEvents.slice(0, 1);
                      
                      return eventsToShow.map((event, index) => {
                        const displayContent = getEventDisplayContent(event);
                        const isRecent = index === 0 && !showAllEvents;
                        
                        return (
                          <div 
                            key={event.id || index} 
                            className={`border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900 ${
                              isRecent ? 'ring-2 ring-indigo-200 dark:ring-indigo-800' : ''
                            }`}
                          >
                            <div className="flex justify-between items-center mb-2 text-left">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30 px-2 py-1 rounded">
                                  {event.kind}
                                </span>
                                {event.source && (
                                  <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
                                    {event.source}
                                  </span>
                                )}
                                {isRecent && (
                                  <span className="text-xs text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 px-2 py-1 rounded font-medium">
                                    Latest
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ''}
                              </span>
                            </div>
                            
                            <div className="text-sm font-medium text-gray-900 dark:text-white mb-2 text-left">
                              {displayContent.title}
                            </div>
                            
                            {displayContent.content && (
                              <div className="text-sm text-gray-700 dark:text-gray-300 mb-2 p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 text-left">
                                <div className="max-h-32 overflow-y-auto text-left">
                                  {displayContent.content.length > 200 ? (
                                    <>
                                      {displayContent.content.substring(0, 200)}
                                      <span className="text-gray-500 dark:text-gray-400">... (truncated)</span>
                                    </>
                                  ) : (
                                    displayContent.content
                                  )}
                                </div>
                              </div>
                            )}
                            
                            {displayContent.details && (
                              <details className="mt-2 text-left">
                                <summary className="text-xs text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300 text-left">
                                  Show raw data
                                </summary>
                                <div className="text-xs text-gray-600 dark:text-gray-400 font-mono bg-gray-100 dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto mt-1 text-left">
                                  <pre className="text-left whitespace-pre-wrap">{JSON.stringify(displayContent.details, null, 2)}</pre>
                                </div>
                              </details>
                            )}
                          </div>
                        );
                      });
                    })()
                  ) : (
                    <div className="text-center py-4 text-gray-500 dark:text-gray-400">No events yet</div>
                  )}
                </div>
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                <h4 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Send Message</h4>
                <div className="space-y-3">
                  <textarea
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    placeholder="Type your message here..."
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-600 focus:shadow-md transition-all duration-200 resize-vertical"
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <button 
                      onClick={sendMessage}
                      disabled={!messageInput.trim() || loading}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Send & Run
                    </button>
                    <button 
                      onClick={async () => {
                        if (selectedConversation?.remoteConversation) {
                          try {
                            await selectedConversation.remoteConversation.run();
                            console.log('Agent started manually');
                            // 重新加载对话详细信息
                            await selectConversation(selectedConversation.id);
                          } catch (err) {
                            console.error('Failed to start agent:', err);
                            setError(err instanceof Error ? err.message : 'Failed to start agent');
                          }
                        }
                      }}
                      disabled={loading}
                      className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Start/Resume the agent"
                    >
                      ▶️ Run
                    </button>
                    <button 
                      onClick={async () => {
                        if (selectedConversation?.remoteConversation) {
                          try {
                            await selectedConversation.remoteConversation.pause();
                            console.log('Agent paused manually');
                            // 重新加载对话详细信息
                            await selectConversation(selectedConversation.id);
                          } catch (err) {
                            console.error('Failed to pause agent:', err);
                            setError(err instanceof Error ? err.message : 'Failed to pause agent');
                          }
                        }
                      }}
                      disabled={loading}
                      className="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-md font-medium transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Pause the agent"
                    >
                      ⏸️ Pause
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ConversationManager;