<a id="custom-tools-with-remote-agent-server"></a>

# 带遥控器的自定义工具 Agent Server

本示例展示了如何使用自定义工具与远程 Agent Server 通过构建包含你工具实现的自定义基础镜像，并通过 `OH_EXTRA_PYTHON_PATH` 将它们暴露给二进制 Agent Server。

<a id="overview"></a>

## 概述

使用远程 Agent Server 时，自定义工具必须在服务器的 Python 环境中可用。 此示例显示了完整的工作流程：

1. **定义将结构化数据记录到 JSON 文件的自定义工具**
2. **构建包含您的工具和套件的自定义基础映像**
   `OH_EXTRA_PYTHON_PATH`
3. **使用`DockerDevWorkspace`**在自定义基础映像之上构建二进制文件Agent Server
4. **使用动态工具注册**使工具在运行时可用
5. **通过从工作区读回记录的数据来验证结果 **

<a id="use-cases"></a>

## 使用案例

该模式适用于：

- **结构化数据收集**：定义`log_data`、`record_metric`或`track_event`等工具以在智能体运行期间收集结构化数据
- **自定义集成**：与外部系统（APIs、数据库等）交互的工具
- **特定于领域的操作**：特定于您的应用程序的业务逻辑工具
- **下游处理**：收集的数据可用于生成报告、触发工作流程等。

<a id="architecture"></a>

## 架构

```
┌─────────────────┐         ┌──────────────────────────┐
│   SDK Client    │         │   Remote Agent Server    │
│                 │         │   (Binary custom image)  │
│  - Define tools │◄────────┤                          │
│  - Send tasks   │   API   │  - Custom tools in       │
│  - Get results  │         │    OH_EXTRA_PYTHON_PATH  │
│                 │         │  - Dynamic registration  │
└─────────────────┘         │  - Tool execution        │
                            │  - JSON file output      │
                            └──────────────────────────┘
```

<a id="files-in-this-example"></a>

## 本例中的文件

- **`custom_tools/log_data.py`**：用于将结构化数据记录到 JSON 的示例自定义工具
- **`Dockerfile`**：将自定义工具复制到基础镜像中的简单 Dockerfile
- **`build_custom_image.sh`**：构建自定义基础镜像的脚本
- **`main.py`**：SDK 演示完整工作流程的脚本
- **`README.md`**：本文档

<a id="the-custom-tool"></a>

## 自定义工具

该示例包括将结构化数据记录到 JSON 文件的 `LogDataTool`：

```python
# 定义操作（工具的输入）
class LogDataAction(Action):
    message: str  # 日志消息
    level: LogLevel  # 枚举：调试、信息、警告、错误
    data: dict[str, Any]  # 附加结构化数据

# 定义观测结果（工具的输出）
class LogDataObservation(Observation):
    success: bool
    log_file: str
    entry_count: int

# 导入模块时自动注册工具
register_tool("LogDataTool", LogDataTool)
```

<a id="how-it-works"></a>

## 它是如何运作的

<a id="1-tool-implementation-custom_toolslog_datapy"></a>

### 1. 工具实现 (`custom_tools/log_data.py`)

该工具定义：
- **操作**：输入结构（LLM提供的内容）
- **观测结果**：输出结构（LLM收到的内容）
- **Executor**：写入`/tmp/agent_data.json`的逻辑
- ** 自动注册**: `register_tool()` 在模块级别调用

### 2. Dockerfile

Dockerfile 非常简单：
```dockerfile
FROM nikolaik/python-nodejs:python3.13-nodejs24-slim

# 将自定义工具复制到冻结二进制文件之外的目录中
COPY custom_tools /app/custom_tools

# 告诉二进制文件 Agent Server 在哪里可以找到外部 Python 模块
ENV OH_EXTRA_PYTHON_PATH="/app"
```

这将使用您的自定义工具创建一个基础映像，并告诉二进制文件 Agent Server 从哪里导入它们。 Agent Server 由 `DockerDevWorkspace` 自动构建在该图像之上。

<a id="3-dynamic-tool-registration"></a>

### 3. 动态工具注册

创建对话时，SDK：
1. 从客户端的注册表收集工具模块限定名
2. 在会话创建请求中将它们发送到服务器
3. 服务器导入这些模块，触发自动注册
4. 工具可用于智能体执行

<a id="4-sdk-script-mainpy"></a>

### 4. SDK 脚本 (`main.py`)

脚本：
- 构建自定义基础镜像（如果尚未构建）
- 使用 `DockerDevWorkspace` 与 `base_image` 和 `target="binary"` 在顶部构建 Agent Server
- 使用指定的自定义工具创建智能体
- 发送使用自定义工具的任务
- 智能体在可以访问自定义工具的远程服务器上执行
- **读回JSON日志文件**以验证工具是否正常工作

<a id="running-the-example"></a>

## 运行示例

<a id="prerequisites"></a>

### 先决条件

- Docker已安装并正在运行
- OpenHands SDK 已安装
- `LLM_API_KEY` 环境变量设置

<a id="steps"></a>

### 步骤

1. **导航到此目录**：
   ```bash
   cd examples/02_remote_agent_server/06_custom_tool
   ```

2. **运行示例**：
   ```bash
   python main.py
   ```

该脚本将：
- 构建自定义基础映像（仅限首次运行）
- 在基础映像之上构建二进制文件 Agent Server（首次运行可能需要几分钟）
- 使用自定义工具启动 Agent Server
- 使用自定义工具执行任务
- 读取并显示 JSON 文件中记录的数据

<a id="expected-output"></a>

### 预期输出

```
🔍 Checking for custom base image: custom-base-image:latest
📦 Building custom base image with custom tools...
✅ Custom base image built successfully!
🚀 Building and starting agent server with custom tools...
📋 Conversation ID: <id>
📝 Sending task to analyze files and log findings...
🚀 Running conversation...
✅ Task completed!
📊 Logged Data Summary:
================================================================================
Found 3 log entries:

Entry 1:
  Timestamp: 2024-01-15T10:30:00.000000+00:00
  Level: info
  Message: Starting analysis of Python files
  Data: {"directory": "/workspace"}

Entry 2:
  Timestamp: 2024-01-15T10:30:05.000000+00:00
  Level: info
  Message: Found interesting pattern
  Data: {"file": "example.py", "pattern": "decorator usage"}

Entry 3:
  Timestamp: 2024-01-15T10:30:10.000000+00:00
  Level: warning
  Message: Potential issue detected
  Data: {"file": "utils.py", "line": 42, "issue": "missing error handling"}

================================================================================
✅ Example completed successfully!
```

<a id="creating-your-own-custom-tools"></a>

## 创建您自己的自定义工具

<a id="1-define-your-tool"></a>

### 1. 定义你的工具

在`custom_tools/`中创建一个新的Python文件：

```python
from openhands.sdk import Action, Observation, ToolDefinition
from openhands.sdk.tool import ToolExecutor, register_tool

class MyAction(Action):
    # 定义您的输入字段
    param1: str
    param2: int

class MyObservation(Observation):
    # 定义您的输出字段
    result: str
    success: bool

class MyExecutor(ToolExecutor[MyAction, MyObservation]):
    def __call__(self, action: MyAction, conversation=None):
        # 实施您的工具逻辑
        return MyObservation(result="...", success=True)

class MyTool(ToolDefinition[MyAction, MyObservation]):
    @classmethod
    def create(cls, conv_state, **params):
        executor = MyExecutor()
        return [cls(
            description="Tool description",
            action_type=MyAction,
            observation_type=MyObservation,
            executor=executor,
        )]

# 自动注册
register_tool("MyTool", MyTool)
```

<a id="2-update-the-dockerfile"></a>

### 2. 更新 Dockerfile

无需更改！ Dockerfile 已经复制了所有 `custom_tools/` 并设置
`OH_EXTRA_PYTHON_PATH=/app` 因此二进制文件 Agent Server 可以导入该包。

<a id="3-use-your-tool"></a>

### 3. 使用你的工具

在您的 SDK 脚本中：

```python
from openhands.workspace import DockerDevWorkspace

# 将 DockerDevWorkspace 与您的自定义基础映像和二进制目标一起使用
with DockerDevWorkspace(
    base_image="custom-base-image:latest",
    host_port=8010,
    target="binary",
) as workspace:
    # 使用您的自定义工具创建智能体
    tools = get_default_tools(enable_browser=False)
    tools.append(Tool(name="MyTool"))
    
    agent = Agent(llm=llm, tools=tools, ...)
    # ... rest of your code
```

<a id="related-documentation"></a>

## 相关文档

- [独立自定义工具示例](../../01_standalone_sdk/02_custom_tools.py)
- [工具定义 API](../../../openhands-sdk/openhands/sdk/tool/)
- [Agent Server API](../../../openhands-agent-server/)
- [动态工具注册](https://github.com/OpenHands/software-agent-sdk/pull/1129)

<a id="questions"></a>

## 有问题吗？

如果您有疑问或遇到问题：
1. 检查[SDK文档](https://docs.all-hands.dev/sdk/)
2. 查看 `openhands-tools/` 中的现有工具
3. 在 [GitHub](https://github.com/OpenHands/software-agent-sdk/issues) 上打开问题
