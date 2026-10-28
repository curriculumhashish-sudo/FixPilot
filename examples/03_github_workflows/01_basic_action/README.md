<a id="routine-maintenance-workflow"></a>

# 日常维护工作流程

此示例演示如何使用 OpenHands 智能体 SDK 为自动化日常维护任务设置 GitHub 操作工作流程。

<a id="files"></a>

## 文件

- **`workflow.yml`**：GitHub 可复制到存储库中 `.github/workflows/` 的操作工作流程文件
- **`agent_script.py`**：使用自定义提示词运行 OpenHands 智能体的 Python 脚本

<a id="setup"></a>

## 设置

<a id="1-copy-the-workflow-file"></a>

### 1. 复制工作流程文件

将存储库中的 `workflow.yml` 复制到 `.github/workflows/maintenance-task.yml`：

```bash
cp examples/03_github_workflows/01_routine_maintenance/workflow.yml .github/workflows/maintenance-task.yml
```

<a id="2-configure-the-workflow"></a>

### 2. 配置工作流程

编辑 `.github/workflows/maintenance-task.yml` 并在 `env` 部分中设置您的配置。

您可以通过两种方式提供提示词（选择一种）：

**选项 A：直接提示词文本 (PROMPT_STRING)**
```yaml
jobs:
  run-maintenance-task:
    runs-on: ubuntu-latest
    env:
      # 提供提示词作为直接文本
      PROMPT_STRING: 'Check for any changes that were made over the past week. If they have not been properly documented, create a PR to concisely update the documentation.'
      
      # 可选：自定义其他设置
      LLM_MODEL: gpt-5.5
      # LLM_BASE_URL: ' https://custom-api.example.com'
```

**选项 B：提示词来自 URL 或文件 (PROMPT_LOCATION)**
```yaml
jobs:
  run-maintenance-task:
    runs-on: ubuntu-latest
    env:
      # 提供 URL 中的提示词或文件路径
      PROMPT_LOCATION: 'https://example.com/prompts/maintenance.txt'
      
      # 可选：自定义其他设置
      LLM_MODEL: gpt-5.5
      # LLM_BASE_URL: ' https://custom-api.example.com'
```

**注**：提供`PROMPT_STRING`或`PROMPT_LOCATION`之一，而不是两者都提供。

<a id="3-configure-secrets"></a>

### 3. 配置机密

在 GitHub 存储库设置中设置以下机密：

- **`LLM_API_KEY`**（必填）：您的 LLM API 密钥
  - 从 [OpenHands LLM 提供商 ](https://docs.all-hands.dev/openhands/usage/llms/openhands-llms) 获取一个

<a id="4-test-locally-optional"></a>

### 4. 本地测试（可选）

在设置自动运行之前，请在本地测试脚本：

```bash
export LLM_API_KEY="your-api-key"
export LLM_MODEL="gpt-5.5"

# 创建测试提示词
echo "Check for outdated dependencies in requirements.txt and create a PR to update them" > prompt.txt

# 运行智能体
python examples/03_github_workflows/01_routine_maintenance/agent_script.py prompt.txt
```

<a id="usage"></a>

## 用途

`env` 部分中的工作流配置用于手动运行和计划运行。

<a id="manual-runs"></a>

### 手动运行

您可以手动触发工作流程并可选择覆盖默认配置：

1. 转到操作→“计划维护任务”
2. 单击“运行工作流程”
3. （可选）覆盖提示词位置或其他设置
4. 单击“运行工作流程”

<a id="scheduled-runs"></a>

### 预定运行

要启用自动计划运行，请编辑 `.github/workflows/maintenance-task.yml` 并取消注释计划部分：

```yaml
on:
  schedule:
    # 每天凌晨 2 点 UTC 运行
    - cron: "0 2 * * *"
```

根据需要自定义 cron 计划。 请参阅 [Cron 语法参考 ](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)。

计划的运行将使用您在步骤 2 中设置的 `env` 部分中的配置。

<a id="example-use-cases"></a>

## 示例用例

- **依赖项更新：**检查requirements.txt中是否有过时的依赖项，并创建PR来更新它们（如果找到）。
- **测试覆盖率：**运行测试覆盖率脚本并找到一处似乎特别缺乏测试的地方。 如果您发现任何问题，请发送 PR 改进那里的测试覆盖率。
- **依赖项更新：**查看 README.md 并更新它以反映自上次更新以来代码库中的任何更改。
- **静态检查：** 对所有 Python 文件运行静态检查和格式检查，并创建包含任何修复的 PR。
- **链接验证：** 检查 Markdown 文件中的所有链接并创建一个问题，列出所有损坏的链接。

<a id="customization"></a>

## 定制化

<a id="using-a-custom-agent-script"></a>

### 使用自定义智能体脚本

您可以在工作流程输入中指定自定义智能体脚本：

```yaml
with:
  agent_script: path/to/your/custom_script.py
  prompt_location: path/to/prompt.txt
```

您的自定义脚本应接受提示词位置作为命令行参数，并使用 OpenHands SDK 运行智能体。

<a id="using-remote-prompts"></a>

### 使用遥控器提示词

您可以远程托管提示词（e.g.，在 GitHub、S3 或任何 HTTP 服务器上）并通过 URL 引用它们：

```bash
# GitHub 原始 URL 的示例
https://raw.githubusercontent.com/your-org/prompts/main/weekly-maintenance.txt

# 要点示例
https://gist.githubusercontent.com/username/abc123/raw/prompt.txt
```

这允许您更新提示词而无需修改工作流程文件。

<a id="references"></a>

## 参考文献

- [OpenHands SDK 文档](https://docs.all-hands.dev/)
- [GitHub 操作文档](https://docs.github.com/en/actions)
- [LLM 提供商设置](https://docs.all-hands.dev/openhands/usage/llms/openhands-llms)
