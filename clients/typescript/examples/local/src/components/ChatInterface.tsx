import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import type { LLM } from '@openhands/typescript-client';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface ChatInterfaceProps {
  llm: LLM;
  model: string;
}

export function ChatInterface({ llm, model }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 消息更改时自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 自动调整文本区域大小
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // 构建上下文的对话历史记录（使用纯字符串作为内容）
      const conversationMessages = [...messages, userMessage].map((msg) => ({
        role: msg.role as 'user' | 'assistant',
        content: msg.content,
      }));

      // 拨打LLM
      const response = await llm.chatCompletion({
        messages: conversationMessages,
        model,
      });

      // 提取助理的回复
      const assistantContent =
        response.choices[0]?.message?.content ||
        'Sorry, I could not generate a response.';

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: assistantContent,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error getting response:', error);

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Failed to get response'}`,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="chat-container">
      {messages.length === 0 ? (
        <div className="empty-state">
          <div className="icon">💬</div>
          <h3>Start a conversation</h3>
          <p>
            Send a message to begin chatting with {model.split('/').pop()}.
            Your conversation history will be maintained for context.
          </p>
        </div>
      ) : (
        <div className="messages">
          {messages.map((message) => (
            <div key={message.id} className={`message ${message.role}`}>
              <div className="message-avatar">
                {message.role === 'user' ? '👤' : '🤖'}
              </div>
              <div className="message-content">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="message assistant">
              <div className="message-avatar">🤖</div>
              <div className="typing-indicator">
                <div className="typing-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="input-area">
        <div className="input-container">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Shift+Enter for new line)"
            disabled={isLoading}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            title="Send message"
          >
            ➤
          </button>
        </div>
        {messages.length > 0 && (
          <div style={{ marginTop: '0.5rem', textAlign: 'center' }}>
            <button className="btn btn-secondary" onClick={clearChat} style={{ fontSize: '0.75rem' }}>
              Clear conversation
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
