<a id="automated-todo-management-with-github-actions"></a>

# 通过 GitHub 操作进行自动化 TODO 管理

示例展示了如何使用 OpenHands SDK 自动扫描代码库以查找可配置的 TODO 注释，并创建 pull requests 实现这些注释。 这展示了实用的自动化和自我改进的代码库功能。

<a id="overview"></a>

## 概述

该工作流程由三个主要组成部分组成：

1. **Scanner** (`scanner.py`) - 扫描代码库以获取可配置的 TODO 注释
2. **智能体** (`agent.py`) - 使用 OpenHands 实现 TODOs
3. **GitHub 操作工作流程** - 协调自动化（请参阅 `.github/workflows/todo-management.yml`）

<a id="features"></a>

## 特点

- 🔍 **智能扫描**：查找具有可配置标识符的合法TODO评论，同时过滤掉False正面评论
- 🤖 **AI 实现**: 使用 OpenHands 智能体自动实现 TODOs
- 🔄 **PR 管理**：自动创建功能分支和拉取请求
- 📝 **进度跟踪**：跟踪TODO处理状态和PR创建
- 📊 **综合报告**：详细GitHub带有处理状态的操作摘要
- ⚙️ **可配置**：可自定义TODO标识符和处理限制

<a id="how-it-works"></a>

## 它是如何运作的

1. **扫描阶段**：工作流程扫描您的代码库以获取可配置的TODO注释
   - 默认标识符：`TODO(openhands)`（可通过工作流程输入自定义）
   - 过滤掉 False 个正面信息（文档、测试文件、带引号的字符串）
   - 支持 Python、TypeScript、Java 和 Rust 文件
   - 提供详细的日志记录 TODOs

2. **处理阶段**：对于找到的每个TODO：
   - 创建一个功能分支
   - 使用 OpenHands 智能体来实现 TODO
   - 创建带有实施的拉取请求
   - 跟踪处理状态和 PR 信息

3. **摘要阶段**：生成全面的摘要，显示：
   - 所有处理过的 TODOs 与文件位置
   - 成功实现的关联 pull request URLs
   - 每个 TODO 的处理状态（成功、部分、失败）

<a id="files"></a>

## 文件

- **`scanner.py`**：智能 TODO 扫描仪，带 False 正向滤波
- **`agent.py`**：OpenHands智能体用于TODO实施
- **`prompt.py`**：包含用于 TODO 实现的提示词模板
- **`README.md`**：这份综合文档

<a id="setup"></a>

## 设置

<a id="1-repository-secrets"></a>

### 1. 存储库机密

将这些机密添加到您的 GitHub 存储库：

- **`LLM_API_KEY`**（必填）：您的 LLM API 密钥
  - 从 [OpenHands LLM 提供商 ](https://docs.all-hands.dev/openhands/usage/llms/openhands-llms) 获取一个
- `GITHUB_TOKEN` - GitHub token 具有 repo 权限（自动提供）
-  确保允许 GitHub 操作创建和审查 PR（在存储库设置中）

<a id="2-install-workflow"></a>

### 2. 安装工作流程

GitHub 操作工作流程已安装在此存储库的 `.github/workflows/todo-management.yml` 处。

<a id="3-configure-permissions"></a>

### 3. 配置权限

确保您的 `GITHUB_TOKEN` 具有以下权限：
- `contents: write`
- `pull-requests: write`

<a id="4-add-todo-comments-to-your-code"></a>

### 4. 向您的代码添加 TODO 条注释

在代码库中的任意位置添加以下格式的 TODO 注释：

```python
# TODO(OpenHands)：为用户电子邮件添加输入验证
def process_user_email(email):
    return email.lower()

# TODO(OpenHands)：为 API 响应实施缓存机制
def fetch_api_data(endpoint):
    # 目前的实现没有缓存
    return requests.get(endpoint).json()
```

**支持的语言：**
- Python (`.py`)
- TypeScript (`.ts`)
- 爪哇 (`.java`)
- 铁锈 (`.rs`)

**支持的评论样式：**
- `# TODO(openhands): description`（Python、外壳等）
- `// TODO(openhands): description`（TypeScript、Java、Rust 等）

**自定义标识符：**
您可以使用自定义 TODO 标识符，例如 `TODO(myteam)`、`TODO[urgent]` 等。 在工作流程参数中进行配置。

<a id="usage"></a>

## 用途

<a id="manual-runs"></a>

### 手动运行

1. 转到操作→“自动化 TODO 管理”
2. 单击“运行工作流程”
3. （可选）配置参数：
   - **最大 TODOs**最大数量的 TODOs 处理（默认值：3）
   - **TODO 标识符**：要搜索的自定义标识符（默认值：`TODO(openhands)`）
4. 单击“运行工作流程”

<a id="scanner-cli-usage"></a>

### 扫描仪 CLI 用途

您还可以直接从命令行运行扫描仪：

```bash
# 使用默认标识符扫描当前目录
python scanner.py .

# 使用自定义标识符扫描
python scanner.py . --identifier "TODO(myteam)"

# 扫描特定目录并保存到文件
python scanner.py /path/to/code --output todos.json

# 获得帮助
python scanner.py --help
```

**扫描仪选项：**
- `directory`：要扫描的目录或文件（默认：当前目录）
- `--identifier, -i`：要搜索的 TODO 标识符（默认值：`TODO(openhands)`）
- `--output, -o`：结果的输出文件（默认：stdout）