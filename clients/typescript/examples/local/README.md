<a id="openhands-local-chat"></a>

# OpenHands 本地聊天

基于浏览器的聊天 UI，演示 OpenHands TypeScript SDK 的 `LLM` 类与 OpenRouter 集成。

![OpenHands聊天截图](https://via.placeholder.com/800x500?text=OpenHands+Chat+UI)

<a id="features"></a>

## 特点

- 🔐 **OpenRouter 身份验证** - 使用您的 API 键安全连接
- 💬 **实时聊天** - 具有消息历史记录的对话界面
- 🤖 **多种模型** - 在 Claude、GPT-4、Gemini、Llama 等之间切换
- ⚙️ **可配置设置** - 调整温度和最大值token
- 🌙 **深色模式** - 漂亮的深色主题 UI
- 📱 **响应式** - 适用于桌面和移动设备

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
cd examples/local
npm install
npm run dev
```

<a id="running"></a>

### 跑步

1. 在浏览器中打开  http://localhost:12000
2. 输入您的 OpenRouter API 键
3. 选择一个模型并开始聊天！

<a id="available-models"></a>

## 可用型号

该应用程序预先配置了流行的模型：

| 型号 | 描述 |
|-------|-------------|
| 克劳德 3.5 十四行诗 | 最适合复杂的推理和编码 |
| 克劳德 3 俳句 | 快速高效 |
| GPT-4o | OpenAI最新旗舰 |
| GPT-4o 迷你 | 更快、更便宜 GPT-4 |
| 双子座专业版 1.5 | 谷歌的先进模型 |
| 羊驼3.1 70B | Meta的开源模型 |
| 米斯特拉尔大号 | 米斯特拉尔的高级型号 |

您可以通过OpenRouter的统一API访问300多个模型。

<a id="project-structure"></a>

## 项目结构

```
examples/local/
├── index.html           # 条目 HTML 文件
├── package.json         # 依赖关系
├── tsconfig.json        # TypeScript 配置
├── vite.config.ts       # Vite 捆绑器配置
└── src/
    ├── main.tsx         # 反应入口
    ├── App.tsx          # 主要应用程序组件
    ├── styles.css       # 全局样式
    └── components/
        ├── AuthScreen.tsx      # API按键输入
        ├── ChatInterface.tsx   # 聊天消息和输入
        └── SettingsModal.tsx   # 模型设置
```

<a id="how-it-works"></a>

## 它是如何运作的

此示例演示如何使用 TypeScript SDK 中的 `LLM` 类。 `LLM` 类在底层使用 OpenRouter 来提供对 300 多个模型的访问：

```typescript
import { LLM } from '@openhands/typescript-client';

// 创建 LLM 实例（在底层使用 OpenRouter）
const llm = new LLM({
  apiKey: 'your-api-key',
  defaultModel: 'anthropic/claude-3.5-sonnet',
  defaultTemperature: 0.7,
  defaultMaxTokens: 4096,
});

// 使用 chatCompletion 发送消息
const response = await llm.chatCompletion({
  messages: [
    { role: 'user', content: 'Hello!' }
  ],
  model: 'anthropic/claude-3.5-sonnet',
});

console.log(response.choices[0].message.content);

// 或者使用简单的 generate() 帮助器
const text = await llm.generate('Hello!');
console.log(text);
```

<a id="configuration"></a>

## 配置

<a id="environment-variables"></a>

### 环境变量

该应用程序将设置存储在 localStorage 中：
- `openrouter_api_key` - 你的 OpenRouter API 钥匙
- `openrouter_model` - 所选型号 ID

<a id="settings"></a>

### 设置

点击⚙️按钮进行调整：
- **型号** - 在可用型号之间切换
- **温度** - 0.0（精确）到 2.0（创意）
- **最大 token** - 响应长度限制 (256-8192)

<a id="development"></a>

## 发展

```bash
# 通过热重载启动开发服务器
npm run dev

# 为生产而构建
npm run build

# 预览生产版本
npm run preview
```

<a id="security-notes"></a>

## 安全说明

- API 密钥存储在 localStorage 中（仅限客户端）
- 使用前，密钥会根据 OpenRouter 的 API 进行验证
- 所有 API 调用都直接转到 OpenRouter（无后端代理）
- 单击“注销”以清除存储的凭据

<a id="troubleshooting"></a>

## 故障排除

<a id="invalid-api-key-error"></a>

### “API 键无效”错误
- 确保您的 API 键以 `sk-or-v1-` 开头
- 检查您的密钥在 openrouter.ai 处是否有可用积分

<a id="build-errors"></a>

### 构建错误
- 确保首先构建主 SDK：`cd ../.. && npm run build`
- 尝试清除 node_modules: `rm -rf node_modules && npm install`

<a id="cors-issues"></a>

### CORS 个问题
- OpenRouter的API支持浏览器请求
- 如果出现问题持久化，请检查您的 API 密钥权限

<a id="related"></a>

## 相关

- [OpenRouter 文档](https://openrouter.ai/docs)
- [OpenHands TypeScript SDK](../../README.md)
- [型号定价](https://openrouter.ai/models)
- [本地智能体带有工具调用的示例 ](../local-agent/) - 智能体
