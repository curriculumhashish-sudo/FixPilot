/**
 * 本地对话实现
 *
 * 这实现了用于本地执行的 IConversation 接口。 与RemoteConversation不同，
 * LocalConversation 在本地运行智能体循环，无需连接到远程服务器。
 *
 * 这反映了 Python SDK 的 LocalConversation 类。
 */

import {
  ConversationID,
  Message,
  ConversationCallbackType,
  ConfirmationPolicyBase,
  ConversationStats,
  AgentBase,
  SecretValue,
  LLM,
  Event,
} from '../types/base';
import { LocalWorkspace } from '../workspace/local-workspace';
import { IWorkspace } from '../workspace/base';
import { IConversation, IConversationState, IEventsList, BaseConversationOptions } from './base';
import { ILLM, ChatMessage, Tool, ToolCall, TokenStreamEvent } from '../llm/base';
import { generateSystemPrompt, TOOL_DESCRIPTIONS } from '../prompts';
import { SecretRegistry } from './secret-registry';
import { StuckDetector, StuckDetectionThresholds, StuckDetectionResult } from './stuck-detector';
import {
  BaseEvent,
  ActionEvent,
  UserRejectObservation,
  ConversationStateUpdateEvent,
  generateEventId,
} from '../events/types';
import { ConfirmationPolicy, NeverConfirm } from '../security/confirmation-policy';
import { SecurityAnalyzer } from '../security/security-analyzer';

/**
 * 工具执行器功能类型。
 * 接受工具调用并返回结果字符串。
 */
export type ToolExecutor = (toolCall: ToolCall) => Promise<string> | string;

/**
 * token 回调对话级别类型。
 */
export type ConversationTokenCallback = (event: TokenStreamEvent) => void;

/**
 * 用于创建 LocalConversation 实例的选项。
 */
export interface LocalConversationOptions extends BaseConversationOptions {
  /** 用于对话的 LLM 实例*/
  llm: ILLM;
  /** 智能体的可选系统提示词*/
  systemPrompt?: string;
  /** 用于保存对话状态的可选持久化目录*/
  persistenceDir?: string;
  /** 提供给LLM的自定义工具（除了内置工具之外或代替内置工具）*/
  tools?: Tool[];
  /** 自定义工具执行器功能。 如果提供，则处理所有工具调用。*/
  toolExecutor?: ToolExecutor;
  /** 是否包含内置工具（execute_command、read_file等）。 默认值：True（如果未提供自定义工具）*/
  includeBuiltinTools?: boolean;
  /** LLM 生成期间流式传输 token 的 token 回调*/
  tokenCallback?: ConversationTokenCallback;
  /** 启用卡住检测（默认值：True）*/
  stuckDetection?: boolean;
  /** 卡住检测的自定义阈值*/
  stuckDetectionThresholds?: Partial<StuckDetectionThresholds>;
  /** 用于评估行动风险的安全分析器*/
  securityAnalyzer?: SecurityAnalyzer;
  /** 提供给对话的首字母机密*/
  secrets?: Record<string, SecretValue>;
}

/**
 * 实施本地对话的事件列表。
 * 存储键入的事件并提供索引和搜索功能。
 */
class LocalEventsList implements IEventsList {
  private events: BaseEvent[] = [];
  private idToIndex: Map<string, number> = new Map();

  async addEvent(event: BaseEvent): Promise<void> {
    const index = this.events.length;
    this.events.push(event);
    if (event.id) {
      this.idToIndex.set(event.id, index);
    }
  }

  async getEvents(): Promise<BaseEvent[]> {
    return [...this.events];
  }

  /**
   * 以数组形式获取所有事件（同步访问）。
   */
  getEventsSync(): BaseEvent[] {
    return [...this.events];
  }

  /**
   * 通过索引获取事件。
   */
  getByIndex(index: number): BaseEvent | undefined {
    if (index < 0) {
      index = this.events.length + index;
    }
    return this.events[index];
  }

  /**
   * 通过 ID 获取事件。
   */
  getById(id: string): BaseEvent | undefined {
    const index = this.idToIndex.get(id);
    return index !== undefined ? this.events[index] : undefined;
  }

  /**
   * 通过ID获取事件的索引。
   */
  getIndex(id: string): number | undefined {
    return this.idToIndex.get(id);
  }

  /**
   * 获取事件数。
   */
  get length(): number {
    return this.events.length;
  }

  /**
   * 迭代事件。
   */
  [Symbol.iterator](): Iterator<BaseEvent> {
    return this.events[Symbol.iterator]();
  }

  getEventCounts(): {
    total: number;
    messages: number;
    actions: number;
    observations: number;
    errors: number;
  } {
    let messages = 0;
    let actions = 0;
    let observations = 0;
    let errors = 0;
    for (const event of this.events) {
      if (event.kind === 'MessageEvent') messages++;
      else if (event.kind === 'ActionEvent') actions++;
      else if (event.kind === 'ObservationEvent') observations++;
      else if (event.kind === 'AgentErrorEvent') errors++;
    }
    return { total: this.events.length, messages, actions, observations, errors };
  }
}

/**
 * 本地对话的对话状态的实现。
 */
class LocalConversationState implements IConversationState {
  readonly id: ConversationID;
  readonly events: LocalEventsList;
  executionStatus: 'idle' | 'running' | 'paused' | 'finished' | 'waiting_for_confirmation' = 'idle';
  confirmationPolicy: ConfirmationPolicy = new NeverConfirm();
  securityAnalyzer?: SecurityAnalyzer;
  /** 等待确认的操作：action_id -> ActionEvent*/
  pendingActions: Map<string, ActionEvent> = new Map();

  constructor(id: ConversationID) {
    this.id = id;
    this.events = new LocalEventsList();
  }
}

/**
 * 需要功能性的内置工具工作区（execute_command、read_file、write_file）。
 * 仅当工作区支持它们时才注册它们（i.e，而不是存根 LocalWorkspace）。
 */
const WORKSPACE_TOOLS: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'execute_command',
      description: TOOL_DESCRIPTIONS.execute_command,
      parameters: {
        type: 'object',
        properties: {
          command: {
            type: 'string',
            description:
              'The bash command to execute. You can only execute one bash command at a time. If you need to run multiple commands sequentially, use `&&` or `;` to chain them together.',
          },
          cwd: {
            type: 'string',
            description: 'Working directory for the command (optional, defaults to workspace root)',
          },
          timeout: {
            type: 'number',
            description: 'Optional timeout in seconds for the command (default: 30)',
          },
        },
        required: ['command'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'read_file',
      description: TOOL_DESCRIPTIONS.read_file,
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Path to the file to read (relative to workspace or absolute)',
          },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'write_file',
      description: TOOL_DESCRIPTIONS.write_file,
      parameters: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description: 'Path to the file to write (relative to workspace or absolute)',
          },
          content: {
            type: 'string',
            description: 'Content to write to the file',
          },
        },
        required: ['path', 'content'],
      },
    },
  },
];

/**
 * 无需功能即可工作的内置工具工作区。
 * 当启用内置工具时，这些始终可用。
 */
const STANDALONE_TOOLS: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'think',
      description: TOOL_DESCRIPTIONS.think,
      parameters: {
        type: 'object',
        properties: {
          thought: {
            type: 'string',
            description: 'The thought to log',
          },
        },
        required: ['thought'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'finish',
      description: TOOL_DESCRIPTIONS.finish,
      parameters: {
        type: 'object',
        properties: {
          message: {
            type: 'string',
            description: 'Final message or summary to present to the user',
          },
        },
        required: ['message'],
      },
    },
  },
];

/**
 * 在本地运行智能体循环的本地对话实现。
 *
 * LocalConversation 提供在本地系统上直接智能体执行，无需
 * 需要远程服务器。 它与 LLM（通过 ILLM 接口）集成
 * 处理消息并执行工具调用到 LocalWorkspace。
 *
 * 示例：
 * ```TypeScript
 * const 工作区 = new LocalWorkspace({ workingDir: '/path/to/project' });
 * const llm = new OpenRouterLLM({ apiKey: '你的钥匙', defaultModel: 'anthropic/claude-3.5-sonnet' });
 * const 对话 = new LocalConversation(智能体，工作区，{
 *   嗯，
 *   maxIterations: 500,
 *   systemPrompt：“你是一个有用的助手......”
 * });
 * 等待 conversation.start({ initialMessage: '你好！' });
 * 等待conversation.run();
 * 等待conversation.close();
 * ```
 */
export class LocalConversation implements IConversation {
  public readonly agent: AgentBase;
  public readonly workspace: IWorkspace;
  public readonly llm: ILLM;

  private _conversationId?: string;
  private _state?: LocalConversationState;
  private _title?: string;
  private callback?: ConversationCallbackType;
  private tokenCallback?: ConversationTokenCallback;
  private persistenceDir?: string;
  private systemPrompt: string;
  private maxIterations: number = 500;
  private messages: ChatMessage[] = [];
  private _isPaused: boolean = false;
  private _isFinished: boolean = false;
  private _isWaitingForConfirmation: boolean = false;
  private customTools?: Tool[];
  private toolExecutor?: ToolExecutor;
  private includeBuiltinTools: boolean;

  // 新功能实例
  private secretRegistry: SecretRegistry;
  private stuckDetector?: StuckDetector;
  private stuckDetectionEnabled: boolean;
  private securityAnalyzer?: SecurityAnalyzer;

  constructor(agent: AgentBase, workspace: IWorkspace, options: LocalConversationOptions) {
    this.agent = agent;
    this.workspace = workspace;
    this.llm = options.llm;
    this.callback = options.callback;
    this.tokenCallback = options.tokenCallback;
    this._conversationId = options.conversationId;
    this.persistenceDir = options.persistenceDir;
    this.customTools = options.tools;
    this.toolExecutor = options.toolExecutor;
    // 仅当未提供自定义工具时才默认包含内置工具
    this.includeBuiltinTools = options.includeBuiltinTools ?? !options.tools;

    // 初始化机密注册表
    this.secretRegistry = new SecretRegistry();
    if (options.secrets) {
      this.secretRegistry.updateSecrets(options.secrets);
    }

    // 初始化卡住检测
    this.stuckDetectionEnabled = options.stuckDetection ?? true;
    if (this.stuckDetectionEnabled) {
      this.stuckDetector = new StuckDetector(options.stuckDetectionThresholds);
    }

    // 初始化安全分析器
    this.securityAnalyzer = options.securityAnalyzer;

    // 生成系统提示词 - 如果提供，则使用自定义，否则生成默认值
    this.systemPrompt =
      options.systemPrompt ||
      generateSystemPrompt({
        workingDir: workspace.workingDir,
      });

    if (options.maxIterations !== undefined) {
      this.maxIterations = options.maxIterations;
    }
  }

  /**
   * 检查工作区是否支持实际操作。
   * LocalWorkspace 是一个引发所有操作的存根。
   */
  private workspaceIsStub(): boolean {
    return this.workspace instanceof LocalWorkspace;
  }

  /**
   * 获取智能体可用的工具。
   * 工作区相关工具（execute_command、read_file、write_file）仅
   * 当工作区支持实际操作时包含。
   */
  private getTools(): Tool[] {
    const tools: Tool[] = [];
    if (this.includeBuiltinTools) {
      tools.push(...STANDALONE_TOOLS);
      if (!this.workspaceIsStub()) {
        tools.push(...WORKSPACE_TOOLS);
      }
    }
    if (this.customTools) {
      tools.push(...this.customTools);
    }
    return tools;
  }

  get id(): ConversationID {
    if (!this._conversationId) {
      throw new Error('Conversation ID not set. Call start() to initialize the conversation.');
    }
    return this._conversationId;
  }

  get state(): IConversationState {
    if (!this._state) {
      if (!this._conversationId) {
        throw new Error(
          'Conversation not initialized. Call start() to initialize the conversation.'
        );
      }
      this._state = new LocalConversationState(this._conversationId);
    }
    return this._state;
  }

  /**
   * 开始或恢复对话。
   */
  async start(
    options: { initialMessage?: string; maxIterations?: number; stuckDetection?: boolean } = {}
  ): Promise<void> {
    // 如果未提供，则生成对话 ID
    if (!this._conversationId) {
      this._conversationId = this.generateConversationId();
    }

    // 初始化状态
    this._state = new LocalConversationState(this._conversationId);

    // 设置最大迭代次数（如果提供）
    if (options.maxIterations !== undefined) {
      this.maxIterations = options.maxIterations;
    }

    // 使用系统提示词初始化消息历史记录
    this.messages = [{ role: 'system', content: this.systemPrompt }];

    // 添加初始消息（如果提供）
    if (options.initialMessage) {
      await this.sendMessage(options.initialMessage);
    }

    this.emitEvent({
      type: 'message',
      timestamp: Date.now(),
      data: { kind: 'conversation_started', conversationId: this._conversationId },
    });
  }

  /**
   * 获取对话统计数据。
   */
  async conversationStats(): Promise<ConversationStats> {
    if (!this._state) {
      return { total_events: 0, message_events: 0, action_events: 0, observation_events: 0 };
    }
    const counts = this._state.events.getEventCounts();
    return {
      total_events: counts.total,
      message_events: counts.messages,
      action_events: counts.actions,
      observation_events: counts.observations,
    };
  }

  /**
   * 发送消息至智能体。
   */
  async sendMessage(message: string | Message): Promise<void> {
    const content = typeof message === 'string' ? message : JSON.stringify(message);

    // 将用户消息添加到历史记录
    this.messages.push({ role: 'user', content });

    // 记录事件
    this.emitEvent({
      type: 'message',
      timestamp: Date.now(),
      data: { kind: 'user_message', content },
    });
  }

  /**
   * 执行智能体循环来处理消息。
   *
   * 这会运行智能体直到：
   * - 智能体调用 finish() 工具
   * - 达到最大迭代次数
   * - pause() 被调用
   * - 发生错误
   */
  async run(): Promise<void> {
    if (!this._state) {
      throw new Error('Conversation not started. Call start() first.');
    }

    this._state.executionStatus = 'running';
    this._isPaused = false;
    this._isFinished = false;

    let iterations = 0;

    const tools = this.getTools();

    while (iterations < this.maxIterations && !this._isPaused && !this._isFinished) {
      iterations++;

      try {
        // 获得 LLM 回复
        const response = await this.llm.chatCompletion({
          messages: this.messages,
          tools: tools.length > 0 ? tools : undefined,
          toolChoice: tools.length > 0 ? 'auto' : undefined,
        });

        const choice = response.choices[0];
        if (!choice) {
          throw new Error('No response from LLM');
        }

        const assistantMessage = choice.message;

        // 将助理消息添加到历史记录
        this.messages.push({
          role: 'assistant',
          content: assistantMessage.content || '',
          tool_calls: assistantMessage.tool_calls,
        });

        // 发出助手的响应
        if (assistantMessage.content) {
          this.emitEvent({
            type: 'message',
            timestamp: Date.now(),
            data: { kind: 'assistant_message', content: assistantMessage.content },
          });
        }

        // 手柄工具调用
        if (assistantMessage.tool_calls && assistantMessage.tool_calls.length > 0) {
          for (const toolCall of assistantMessage.tool_calls) {
            if (this._isPaused || this._isFinished) break;
            await this.handleToolCall(toolCall);
          }
        } else if (choice.finish_reason === 'stop') {
          // 无工具调用且停止原因 - 智能体已完成
          this._isFinished = true;
        }
      } catch (error) {
        this.emitEvent({
          type: 'error',
          timestamp: Date.now(),
          data: {
            kind: 'agent_error',
            error: error instanceof Error ? error.message : String(error),
          },
        });
        this._state.executionStatus = 'finished';
        throw error;
      }
    }

    this._state.executionStatus = this._isPaused ? 'paused' : 'finished';

    if (iterations >= this.maxIterations && !this._isFinished) {
      this.emitEvent({
        type: 'observation',
        timestamp: Date.now(),
        data: { kind: 'max_iterations_reached', iterations },
      });
    }
  }

  /**
   * 从 LLM 处理工具调用。
   */
  private async handleToolCall(toolCall: ToolCall): Promise<void> {
    const { name, arguments: argsString } = toolCall.function;

    this.emitEvent({
      type: 'action',
      timestamp: Date.now(),
      data: { kind: 'tool_call', tool: name, arguments: argsString },
    });

    let result: string;

    try {
      // 如果提供了自定义工具执行器，请将其用于所有工具调用
      if (this.toolExecutor) {
        result = await this.toolExecutor(toolCall);
        // 检查这是否已完成工具调用
        if (name === 'finish') {
          this._isFinished = true;
        }
      } else {
        // 使用内置工具处理
        result = await this.executeBuiltinTool(toolCall);
      }
    } catch (error) {
      result = `Error executing ${name}: ${error instanceof Error ? error.message : String(error)}`;
    }

    // 将工具结果添加到消息中
    this.messages.push({
      role: 'tool',
      content: result,
      tool_call_id: toolCall.id,
    });

    this.emitEvent({
      type: 'observation',
      timestamp: Date.now(),
      data: { kind: 'tool_result', tool: name, result },
    });
  }

  /**
   * 执行内置工具。
   */
  private async executeBuiltinTool(toolCall: ToolCall): Promise<string> {
    const { name, arguments: argsString } = toolCall.function;
    const args = JSON.parse(argsString);

    switch (name) {
      case 'execute_command': {
        const cmdResult = await this.workspace.executeCommand(args.command, args.cwd);
        let result = `Exit code: ${cmdResult.exit_code}\n`;
        if (cmdResult.stdout) result += `stdout:\n${cmdResult.stdout}\n`;
        if (cmdResult.stderr) result += `stderr:\n${cmdResult.stderr}`;
        if (cmdResult.timeout_occurred) result += '\n(Command timed out)';
        return result;
      }

      case 'read_file': {
        const content = await this.workspace.downloadAsText(args.path);
        return content;
      }

      case 'write_file': {
        const uploadResult = await this.workspace.fileUpload(args.content, args.path);
        if (uploadResult.success) {
          return `Successfully wrote ${uploadResult.file_size} bytes to ${args.path}`;
        } else {
          return `Failed to write file: ${uploadResult.error}`;
        }
      }

      case 'think': {
        this.emitEvent({
          type: 'observation',
          timestamp: Date.now(),
          data: { kind: 'think', thought: args.thought },
        });
        return 'Your thought has been logged.';
      }

      case 'finish': {
        this._isFinished = true;
        this.emitEvent({
          type: 'message',
          timestamp: Date.now(),
          data: { kind: 'finish', message: args.message },
        });
        return 'Task completed.';
      }

      default:
        return `Unknown tool: ${name}`;
    }
  }

  /**
   * 暂停智能体执行。
   */
  async pause(): Promise<void> {
    this._isPaused = true;
    if (this._state) {
      this._state.executionStatus = 'paused';
    }
    this.emitEvent({
      type: 'message',
      timestamp: Date.now(),
      data: { kind: 'paused' },
    });
  }

  /**
   * 设置确认策略。
   */
  async setConfirmationPolicy(policy: ConfirmationPolicyBase | ConfirmationPolicy): Promise<void> {
    if (this._state) {
      // 如果是ConfirmationPolicyBase（旧接口），则将其包装
      if ('requiresConfirmation' in policy) {
        this._state.confirmationPolicy = policy as ConfirmationPolicy;
      } else {
        // 创建一个简单的包装器
        const policyType = (policy as ConfirmationPolicyBase).type ?? policy.kind ?? 'never';
        this._state.confirmationPolicy = {
          type: policyType,
          requiresConfirmation: () => policyType === 'always' || policyType === 'AlwaysConfirm',
        };
      }
    }
  }

  /**
   * 发送确认回复。
   *
   * 注意：确认处理在LocalConversation中尚未完全实现。
   */
  async sendConfirmationResponse(accept: boolean, reason?: string): Promise<void> {
    this.emitEvent({
      type: 'message',
      timestamp: Date.now(),
      data: { kind: 'confirmation_response', accept, reason },
    });
    // 如果暂停确认则恢复执行
    if (accept) {
      this._isPaused = false;
    }
  }

  async setTitle(title: string): Promise<void> {
    this._title = title;
  }

  /**
   * 使用 LLM 生成对话的标题。
   */
  async generateTitle(maxLength: number = 50, _llm?: LLM): Promise<string> {
    // LocalConversation 始终使用自己的 ILLM 实例来生成标题。 llm 参数的存在是为了与 RemoteConversation 接口兼容。
    //
    const llmToUse = this.llm;

    // 获取对话摘要
    const userMessages = this.messages
      .filter((m) => m.role === 'user')
      .map((m) => (typeof m.content === 'string' ? m.content : JSON.stringify(m.content)))
      .slice(0, 3)
      .join('\n');

    if (!userMessages) {
      return 'New Conversation';
    }

    const prompt = `Generate a short title (max ${maxLength} characters) for a conversation that starts with:\n\n${userMessages}\n\nRespond with only the title, no quotes or explanation.`;

    const title = await llmToUse.generate(prompt);
    return title.slice(0, maxLength).trim();
  }

  /**
   * 更新机密可用于智能体。
   * 机密存储在 SecretRegistry 中，可用于：
   * - 环境变量注入命令
   * - 输出屏蔽以防止意外曝光
   */
  async updateSecrets(secrets: Record<string, SecretValue>): Promise<void> {
    this.secretRegistry.updateSecrets(secrets);
  }

  /**
   * 向智能体提出一个简单的、无状态的问题，并获得直接的 LLM 响应。
   *
   * 这会绕过正常的对话流程并执行不修改，持久化，
   * 或成为对话状态的一部分。 该请求未被记住
   * main智能体，没有事件被记录，执行状态不变。
   *
   * @param Question - 一个简单的字符串问题询问智能体
   * @returns 来自智能体的字符串响应
   */
  async askAgent(question: string): Promise<string> {
    // 根据最近的对话历史记录构建上下文
    const contextMessages = this.messages.slice(-10); // 上下文的最后 10 条消息

    const askPrompt = `Based on the conversation context, please answer this question concisely:

Question: ${question}

Provide a direct answer without using any tools.`;

    const messages: ChatMessage[] = [...contextMessages, { role: 'user', content: askPrompt }];

    // 无需工具即可简单完成
    const response = await this.llm.chatCompletion({
      messages,
      // 无需工具 - 只需获得直接答案
    });

    return response.choices[0]?.message?.content || 'Unable to generate a response.';
  }

  /**
   * 拒绝所有等待确认的待处理操作。
   *
   * @param Reason - 拒绝的原因
   */
  async rejectPendingActions(reason: string = 'User rejected the action'): Promise<void> {
    if (!this._state) return;

    for (const [actionId, action] of this._state.pendingActions) {
      // 发出拒绝事件
      const rejectEvent: UserRejectObservation = {
        id: generateEventId(),
        kind: 'UserRejectObservation',
        timestamp: new Date().toISOString(),
        source: 'user',
        action_id: actionId,
        tool_name: action.tool_name ?? '',
        tool_call_id: action.tool_call_id ?? '',
        rejection_reason: reason,
        rejection_source: 'user',
      };

      this.emitTypedEvent(rejectEvent);

      // 添加拒绝作为工具结果
      this.messages.push({
        role: 'tool',
        content: `Action rejected: ${reason}`,
        tool_call_id: action.tool_call_id,
      });
    }

    // 清除待处理的操作
    this._state.pendingActions.clear();

    // 如果正在等待确认则恢复
    if (this._isWaitingForConfirmation) {
      this._isWaitingForConfirmation = false;
      this._state.executionStatus = 'running';
    }
  }

  /**
   * 设置安全分析器以评估操作风险。
   *
   * @paramanalyzer - 要使用的安全分析器，或 null 禁用
   */
  setSecurityAnalyzer(analyzer: SecurityAnalyzer | null): void {
    this.securityAnalyzer = analyzer || undefined;
    if (this._state) {
      this._state.securityAnalyzer = this.securityAnalyzer;
    }
  }

  /**
   * 使用卡住检测器检查智能体当前是否卡住。
   *
   * @returns StuckDetectionResult 包含有关任何检测到的卡住模式的详细信息
   */
  checkIfStuck(): StuckDetectionResult {
    if (!this.stuckDetector || !this._state) {
      return { isStuck: false };
    }

    const events = this._state.events.getEventsSync();
    return this.stuckDetector.isStuck(events);
  }

  /**
   * 获取机密注册表以直接访问。
   * 对于自定义输出处理中的屏蔽机密很有用。
   */
  getSecretRegistry(): SecretRegistry {
    return this.secretRegistry;
  }

  /**
   * 屏蔽给定文本中的任何机密。
   *
   * @param text - 可能包含机密值的文本
   * @returns 将机密值替换为 <secret-hidden> 的文本
   */
  maskSecrets(text: string): string {
    return this.secretRegistry.maskSecretsInOutput(text);
  }

  /**
   * 启动 WebSocket 客户端。
   *
   * 注意：LocalConversation 不使用 WebSocket，因为它在本地运行。
   */
  async startWebSocketClient(): Promise<void> {
    // 本地对话无操作
  }

  /**
   * 停止 WebSocket 客户端。
   *
   * 注意：LocalConversation不使用WebSocket。
   */
  async stopWebSocketClient(): Promise<void> {
    // 本地对话无操作
  }

  /**
   * 关闭对话并清理资源。
   */
  async close(): Promise<void> {
    this._isPaused = true;
    this._isFinished = true;
    if (this._state) {
      this._state.executionStatus = 'finished';
    }
    this.workspace.close();
    this.llm.close();
    const stateEvent: ConversationStateUpdateEvent = {
      id: generateEventId(),
      kind: 'ConversationStateUpdateEvent',
      timestamp: new Date().toISOString(),
      source: 'environment',
      key: 'status',
      value: 'closed',
    };
    this.emitTypedEvent(stateEvent);
  }

  /**
   * 获取当前消息历史记录。
   */
  getMessages(): ChatMessage[] {
    return [...this.messages];
  }

  /**
   * 发出一个类型化事件并调用回调（如果提供）。
   */
  private emitTypedEvent(event: BaseEvent): void {
    if (this._state) {
      this._state.events.addEvent(event);
    }
    if (this.callback) {
      // 转换为回调的预期事件格式
      this.callback(event as Event);
    }
  }

  /**
   * 发出事件（旧格式）并调用回调（如果提供）。
   * @已弃用使用 emitTypedEvent 代替
   */
  private emitEvent(event: { type: string; timestamp: number; data: unknown }): void {
    // 转换为类型化事件
    const typedEvent: BaseEvent = {
      id: generateEventId(),
      kind: (event.data as { kind?: string })?.kind || event.type,
      timestamp: new Date(event.timestamp).toISOString(),
      ...(event.data as Record<string, unknown>),
    };

    if (this._state) {
      this._state.events.addEvent(typedEvent);
    }
    if (this.callback) {
      this.callback(typedEvent as Event);
    }
  }

  /**
   * 生成唯一的对话 ID。
   */
  private generateConversationId(): string {
    return crypto.randomUUID();
  }
}
