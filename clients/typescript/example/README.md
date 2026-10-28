<a id="openhands-sdk-react-example"></a>

# OpenHands SDK 反应示例

这是一个使用 Vite 构建的基本 React 应用程序，演示了与 OpenHands Agent Server TypeScript 客户端 SDK 的成功集成。

<a id="features"></a>

## 特点

- ✅ **本地SDK集成**：通过文件依赖关系使用SDK的本地构建版本
- ✅ **自动构建**：在启动应用程序之前构建SDK
- ✅ **TypeScript 支持**：与类型安全的全面TypeScript集成
- ✅ **导入验证**：显示所有导入的SDK类和枚举
- ✅ **实时状态**：显示SDK导入状态和可用功能

<a id="whats-demonstrated"></a>

## 展示了什么

应用成功导入并显示：

<a id="main-classes"></a>

### 主要课程
- `RemoteConversation` - 主会话管理类
- `RemoteWorkspace`-工作区文件操作类
- `HttpClient` - HTTP 客户端用于 API 通信
- `AgentExecutionStatus` - 枚举用于智能体执行状态
- `EventSortOrder` - 枚举用于事件排序选项

<a id="enum-values"></a>

### 枚举价值观
- **AgentExecutionStatus**: IDLE, RUNNING, PAUSED, FINISHED, ERROR
- **EventSortOrder**: TIMESTAMP, REVERSE_TIMESTAMP

<a id="getting-started"></a>

## 开始使用

<a id="prerequisites"></a>

### 先决条件
- Node.js（v18 或更高版本）
- 新项目管理

<a id="installation--running"></a>

### 安装与运行

1. **安装依赖项**：
   ```bash
   npm install
   ```

2. **启动开发服务器**：
   ```bash
   npm run dev
   ```
   这将：
   - 从 `../agent-server-typescript-client` 构建 SDK
   - 在12000端口启动Vite开发服务器
   - 打开应用程序 `http://localhost:12000`

3. **为生产而构建**：
   ```bash
   npm run build
   ```

<a id="project-structure"></a>

## 项目结构

```
example/
├── src/
│   ├── App.tsx          # 主要 React 组件与 SDK 集成
│   ├── App.css          # 造型
│   ├── main.tsx         # 反应入口
│   └── index.css        # 全局样式
├── package.json         # 依赖项和脚本
├── vite.config.ts       # Vite配置
├── tsconfig.json        # TypeScript 配置
└── index.html           # HTML 模板
```

<a id="key-configuration"></a>

## 关键配置

### package.json
- **本地SDK依赖项**：`"@openhands/agent-server-typescript-client": "file:../agent-server-typescript-client"`
- **构建脚本**：`"build:sdk": "cd ../agent-server-typescript-client && npm run build"`
- **开发脚本**：在启动Vite之前构建SDK

### vite.config.ts
- 配置为使用 TypeScript 进行 React
- CORS 可供开发
- 外部访问的主机配置

<a id="sdk-integration-details"></a>

## SDK 集成详情

该应用程序证明 TypeScript SDK 正确：
1. **构建为ES模块** - 兼容Vite的模块系统
2. **类型安全** - 全面TypeScript支持正确的类型定义
3. **功能性** - 所有主类和枚举都是可导入和可用的
4. **最新** - 使用SDK的最新本地版本

<a id="notes"></a>

## 注释

- SDK 包括一些特定于 Node.js 的功能（fs、路径模块），这些功能被外部化以实现浏览器兼容性
- 这是预期行为，不会影响浏览器环境中的核心 SDK 功能
- 该应用程序充当“Hello World”示例，以验证 SDK 集成是否正常工作