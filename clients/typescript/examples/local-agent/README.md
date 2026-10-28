<a id="openhands-local-agent"></a>

# OpenHands 本地智能体

基于浏览器的智能体 UI，使用 OpenRouter 演示 OpenHands TypeScript SDK 的 `LocalConversation` 类以及 JavaScript 评估功能。

<a id="features"></a>

## 特点

- 🤖 **LocalConversation 智能体 Loop** - 通过 `LocalConversation.run()` 使用 SDK 的内置智能体循环
- 🔧 **JavaScript Eval Tool** - 智能体可以在浏览器中执行 JavaScript 代码
- 🔐 **OpenRouter 身份验证** - 使用您的 API 键安全连接
- 💬 **实时聊天** - 具有消息历史记录的对话界面
- 🤖 **多种模型** - 在 Claude、GPT-4、Gemini、Llama 等之间切换
- 🌙 **深色模式** - 漂亮的深色主题 UI

<a id="quick-start"></a>

## 快速入门

<a id="prerequisites"></a>

### 先决条件

- Node.js 18+
- 一把 OpenRouter API 钥匙（[在此处获取一把](https://openrouter.ai/keys)）

<a id="setup"></a>

### 设置

```bash
# 从 TypeScript-client 目录中，首先构建 SDK
cd /path/to/typescript-client
npm install
npm run build

# 然后设置示例应用程序
cd examples/local-agent
npm install
npm run dev
```

<a id="running"></a>

### 跑步

1. 在浏览器中打开  http://localhost:12001
2. 输入您的 OpenRouter API 键
3. 选择一个模型并开始聊天！

<a id="how-it-works"></a>

## 它是如何运作的

此示例演示了将 `LocalConversation` 与自定义 `eval` 工具结合使用：

1. **用户发送消息** - 使用 eval 工具创建 `LocalConversation`
2. **conversation.start()** - 使用用户消息初始化对话
3. **conversation.run()** - 运行智能体循环，为每个工具调用调用自定义 `toolExecutor`
4. **工具执行** - `toolExecutor` 计算 JavaScript 代码并返回结果
5. **事件** - 回调接收事件以在 UI 中显示

<a id="the-eval-tool"></a>

### 评估工具

智能体可以访问 JavaScript 评估工具：

```typescript
const TOOLS: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'eval',
      description: 'Evaluates JavaScript code in the browser and returns the result.',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'The JavaScript code to evaluate' },
        },
        required: ['code'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'finish',
      description: 'Call this when you have completed the task.',
      parameters: {
        type: 'object',
        properties: {
          message: { type: 'string', description: 'Final message' },
        },
        required: ['message'],
      },
    },
  },
];
```

<a id="example-prompts"></a>

### 示例提示词

尝试这些提示词来查看智能体的实际效果：

- “2+2是什么？”
- “计算 10 的阶乘”
- “生成前 10 个斐波那契数列”
- “现在的日期和时间是几点？”
- “创建一个反转字符串的函数并测试它”

<a id="code-structure"></a>

## 代码结构

```
examples/local-agent/
├── index.html           # 条目 HTML 文件
├── package.json         # 依赖关系
├── tsconfig.json        # TypeScript 配置
├── vite.config.ts       # Vite 捆绑器配置
├── README.md            # 这个文件
└── src/
    ├── main.tsx         # 反应入口
    ├── App.tsx          # 主要应用程序组件
    ├── styles.css       # 全局样式
    └── components/
        ├── AgentChatInterface.tsx  # LocalConversation 使用和聊天界面
        ├── AuthScreen.tsx          # API按键输入
        └── SettingsModal.tsx       # 模型设置
```

<a id="using-localconversation-with-custom-tools"></a>

## 将 LocalConversation 与自定义工具结合使用

`AgentChatInterface.tsx` 中演示的关键模式：

```typescript
import { LocalConversation, LocalWorkspace, Agent, Tool, ToolCall } from '@openhands/typescript-client';

// 定义自定义工具
const TOOLS: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'eval',
      description: 'Evaluates JavaScript code in the browser.',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'The JavaScript code to evaluate' },
        },
        required: ['code'],
      },
    },
  },
];

// 定义工具执行器
const toolExecutor = (toolCall: ToolCall): string => {
  const { name, arguments: argsString } = toolCall.function;
  const args = JSON.parse(argsString);
  
  if (name === 'eval') {
    try {
      const result = eval(args.code);
      return JSON.stringify(result, null, 2);
    } catch (error) {
      return `Error: ${error.message}`;
    }
  }
  
  return `Unknown tool: ${name}`;
};

// 使用自定义工具创建对话
const conversation = new LocalConversation(agent, workspace, {
  llm,
  systemPrompt: 'You are a helpful assistant...',
  tools: TOOLS,           // 定制工具
  toolExecutor,           // 自定义工具执行器
  maxIterations: 10,
  callback: (event) => {
    // 处理事件（assistant_message、tool_result、完成等）
  },
});

// 启动并运行
await conversation.start({ initialMessage: 'Hello!' });
await conversation.run();
```

<a id="security-note"></a>

## 安全说明

⚠️ **警告**：此示例使用`eval()`，它可以执行任意JavaScript代码。 这是出于演示目的，但应谨慎使用。 在生产环境中，请考虑沙箱或限制可以执行的代码。

<a id="related"></a>

## 相关

- [OpenRouter 文档](https://openrouter.ai/docs)
- [OpenHands TypeScript SDK](../../README.md)
- [本地聊天示例](../local/) - 无需工具调用的更简单的聊天
