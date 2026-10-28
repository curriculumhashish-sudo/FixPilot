<a id="datadog-error-debugging-workflow"></a>

# Datadog 错误调试工作流程

此示例演示如何使用 OpenHands 智能体在 GitHub Actions 工作流程中自动调试来自 Datadog 的错误。

<a id="overview"></a>

## 概述

工作流程：
1. 根据可配置查询从 Datadog 获取错误
2. 搜索或创建 GitHub 个问题以跟踪错误
3. 克隆相关存储库以进行综合分析
4. 使用 OpenHands AI 智能体分析代码并确定根本原因
5. 将调试见解作为对 GitHub 问题的评论发布

<a id="files"></a>

## 文件

- `workflow.yml` - GitHub 手动触发的操作工作流程
- `datadog_debugging.py` - 主要调试脚本
- `debug_prompt.jinja` - AI 调试模板提示词

<a id="features"></a>

## 特点

<a id="manual-trigger"></a>

### 手动触发
通过具有可配置输入的 GitHub Actions UI 按需运行：
- **查询类型**：选择 `log-query`（搜索）或 `log-error-id`（特定错误 ID）
- **数据狗查询**：
  - 对于 `log-query`：搜索查询如 `service:deploy ClientDisconnect`
  - 对于 `log-error-id`：特定错误跟踪 ID，如 `2adba034-ab5a-11f0-b04e-da7ad0900000`
- 要分析的存储库列表
- 用于跟踪的问题存储库
- 组织的父级问题
- LLM 型号选择

<a id="smart-issue-management"></a>

### 智能问题管理
- 在创建重复项之前搜索现有问题
- 使用 URL 编码进行正确的 GitHub API 查询
- 存在重复项时选择最旧的匹配问题
- 家长跟踪问题的链接

<a id="multi-repository-analysis"></a>

### 多存储库分析
- 克隆多个存储库以实现综合性上下文
- 智能体拥有所有相关代码库的完整视图
- 识别跨存储库边界的根本原因

<a id="ai-powered-debugging"></a>

### AI 支持的调试
- 使用 OpenHands 智能体自动代码分析
- 识别错误位置和根本原因
- 提供可行的修复建议
- 将详细调查结果发布为 GitHub 条评论

<a id="setup"></a>

## 设置

<a id="required-secrets"></a>

### 必填机密

在存储库中配置这些设置 → 机密和变量 → 操作：

```yaml
DD_API_KEY: Your Datadog API key
DD_APP_KEY: Your Datadog Application key
DD_SITE: Your Datadog site (e.g., us5.datadoghq.com)
LLM_API_KEY: API key for LLM service
LLM_BASE_URL: Base URL for LLM service (optional)
```

**注**：`GITHUB_TOKEN`由GitHub操作自动提供。

<a id="installation"></a>

### 安装

1. 将 `workflow.yml` 复制到存储库的 `.github/workflows/` 目录（e.g., `.github/workflows/datadog-debugging.yml`）
2. 在仓库设置 → 机密和变量 → 操作中配置所需的机密
3. （可选）在 YAML 文件中自定义工作流程输入和默认值

**注意**：工作流在运行时自动从SDK存储库下载最新版本的`datadog_debugging.py`和`debug_prompt.jinja`。 无需将这些文件复制到您的存储库，除非您想自定义它们。

<a id="usage"></a>

## 用途

<a id="via-github-actions-ui"></a>

### 通过 GitHub 操作 UI

1. 转到存储库中的 **Actions** 选项卡
2. 选择 **Datadog 错误调试** 工作流程
3. 单击**运行工作流程**
4. 配置输入：
   - **查询类型**：选择`log-query`或`log-error-id`（默认：`log-query`）
   - **数据狗查询**：
     - 对于 `log-query`：搜索查询（默认值：`service:deploy ClientDisconnect`）
     - 对于 `log-error-id`：错误跟踪 ID (e.g., `2adba034-ab5a-11f0-b04e-da7ad0900000`)
   - **存储库列表**：要分析的以逗号分隔的存储库（默认值：`OpenHands/OpenHands,All-Hands-AI/infra`）
   - **问题存储库**：创建问题的位置（默认值：`All-Hands-AI/infra`）
   - **父问题**：用于跟踪的可选父问题URL
   - **问题前缀**：问题标题的前缀（默认值：`DataDog Error: `）
   - **LLM 模型**：要使用的模型（默认值：`gpt-5.5`）
5. 单击**运行工作流程**

<a id="via-github-cli"></a>

### 通过 GitHub CLI

**搜索与查询匹配的错误：**
```bash
gh workflow run datadog-debugging.yml \
  -f query_type="log-query" \
  -f datadog_query="service:deploy ClientDisconnect" \
  -f repo_list="OpenHands/OpenHands,All-Hands-AI/infra" \
  -f issue_repo="All-Hands-AI/infra"
```

**按 ID 调试特定错误：**
```bash
gh workflow run datadog-debugging.yml \
  -f query_type="log-error-id" \
  -f datadog_query="2adba034-ab5a-11f0-b04e-da7ad0900000" \
  -f repo_list="OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy" \
  -f issue_repo="All-Hands-AI/infra"
```

<a id="example"></a>

## 示例

<a id="input-search-query"></a>

### 输入（搜索查询）
```yaml
query_type: "log-query"
datadog_query: "service:deploy ClientDisconnect"
repo_list: "OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy"
issue_repo: "All-Hands-AI/infra"
issue_parent: "https://github.com/All-Hands-AI/infra/issues/672"
```

<a id="input-specific-error-id"></a>

### 输入（特定错误 ID）
```yaml
query_type: "log-error-id"
datadog_query: "2adba034-ab5a-11f0-b04e-da7ad0900000"
repo_list: "OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy"
issue_repo: "All-Hands-AI/infra"
issue_parent: "https://github.com/All-Hands-AI/infra/issues/672"
```

<a id="output"></a>

### 输出
- **控制台**：显示错误获取、存储库克隆和智能体分析的进度日志
- **GitHub 问题**：已创建或更新错误详细信息
- **GitHub评论**：人工智能生成的分析，包含根本原因和建议
- **Artifacts**：保存7天的调试数据和日志

<a id="real-example"></a>

### 真实例子

查看生产数据的实际运行：
- 错误：`starlette.requests.ClientDisconnect`（出现 1,526 次）
- 问题： https://github.com/All-Hands-AI/infra/issues/703
- 人工智能分析： https://github.com/All-Hands-AI/infra/issues/703#issuecomment-3480707049

智能体确定：
- 错误位置在`github.py`和`gitlab.py`中
- 根本原因：未处理的 `ClientDisconnect` 异常
- 建议：为客户端断开连接添加适当的错误处理

<a id="configuration"></a>

## 配置

<a id="datadog-query-examples"></a>

### Datadog 查询示例

```yaml
# ClientDisconnect 错误
service:deploy ClientDisconnect

# 服务器错误 (5xx)
service:deploy http.status_code:5*

# Database errors
service:deploy (database OR postgresql) status:error

# Authentication errors
service:deploy (authentication OR authorization) status:error

# Rate limit errors
service:deploy rate_limit status:error
```

<a id="repository-list-format"></a>

### 存储库列表格式

`owner/repo` 的逗号分隔列表：
```
OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy
```

<a id="llm-model-options"></a>

### LLM 型号选项

- `gpt-5.5` - 最佳质量（默认）
- `openhands/claude-haiku-4-5-20251001` - 更快、更便宜
- `anthropic/claude-3-5-sonnet-20241022` - 替代方案

<a id="workflow-details"></a>

## 工作流程详情

<a id="inputs"></a>

### 输入

| 输入 | 类型 | 必填 | 默认 | 描述 |
|-------|------|----------|---------|-------------|
| `datadog_query` | 字符串 | 是的 | `service:deploy ClientDisconnect` | 用于搜索错误的 Datadog 查询 |
| `repo_list` | 字符串 | 是的 | `OpenHands/OpenHands,All-Hands-AI/infra` | 以逗号分隔的存储库列表 |
| `issue_repo` | 字符串 | 是的 | `All-Hands-AI/infra` | 用于创建/更新问题的存储库 |
| `issue_parent` | 字符串 | 否 | - | 用于跟踪的父 GitHub 问题 URL |
| `issue_prefix` | 字符串 | 否 | `DataDog Error: ` | 问题标题的前缀 |
| `max_errors` | 字符串 | 否 | `5` | 获取的最大错误数 |
| `llm_model` | 字符串 | 否 | `gpt-5.5` | LLM 使用型号 |

<a id="outputs"></a>

### 输出

- **GitHub 问题**：创建或更新了错误详细信息
- **GitHub评论**：人工智能分析发布到问题
- **Artifacts**：调试数据和日志（保留7天）

<a id="permissions"></a>

### 权限

```yaml
permissions:
  contents: read   # 克隆存储库
  issues: write    # 创建/更新问题和评论
```

<a id="customization"></a>

## 定制化

<a id="for-production-use"></a>

### 用于生产环境

考虑创建一个单独的配置存储库：
- 计划运行（关键运行每天运行，综合运行每周运行）
- 预定义的错误查询类别
- 存储库组定义
- 环境特定设置

请参阅 All-Hands-AI/infra 示例，了解生产就绪的实施。

<a id="adding-scheduled-runs"></a>

### 添加预定运行

添加到工作流程的 `on:` 部分：

```yaml
on:
  workflow_dispatch:
    # ... existing inputs ...
  
  schedule:
    # 每天 09:00 UTC 出现严重错误
    - cron: '0 9 * * *'
    # 每周一 09:00 UTC 进行全面扫描
    - cron: '0 9 * * 1'
```

<a id="matrix-strategy"></a>

### 矩阵策略

并行运行多个查询：

```yaml
jobs:
  debug-errors:
    strategy:
      matrix:
        query:
          - "service:deploy ClientDisconnect"
          - "service:deploy http.status_code:5*"
          - "service:deploy database status:error"
      fail-fast: false
```

<a id="troubleshooting"></a>

## 故障排除

<a id="workflow-fails-to-start"></a>

### 工作流程无法启动
- 验证所有必需的机密均已配置
- 检查`GITHUB_TOKEN`是否具有必要的权限
- 使用 `yamllint` 检查工作流语法

<a id="no-issues-created"></a>

### 没有创建任何问题
- 验证问题存储库是否存在并且可以访问
- 检查 `GITHUB_TOKEN` 拥有 `issues: write` 权限
- 查看工作流程日志中是否存在 API 个错误

<a id="agent-analysis-incomplete"></a>

### 智能体分析不完整
- 如果需要，增加工作流程超时
- 检查`LLM_API_KEY`有效且有配额
- 尝试不同的 LLM 模型
- 减少要分析的存储库数量

<a id="repository-clone-failures"></a>

### 存储库克隆失败
- 验证存储库名称使用 `owner/repo` 格式
- 检查 `GITHUB_TOKEN` 有权访问私人存储库
- 确保存储库存在并且可访问

<a id="related-examples"></a>

## 相关示例

- **基本操作**：`examples/03_github_workflows/01_basic_action/` - 简单工作流程示例
- **PR评论**：`examples/03_github_workflows/02_pr_review/` - PR自动化示例
- **TODO 管理**：`examples/03_github_workflows/03_todo_management/` - 自动 TODO 跟踪

<a id="benefits"></a>

## 好处

1. **自动调试**：AI分析代码，无需人工干预
2. **减少MTTR**：更快地识别根本原因
3. **上下文-Aware**：完整图片的多存储库分析
4. **无重复**：智能问题跟踪可防止混乱
5. **可行的见解**：明确的修复建议
6. **可扩展**：轻松添加新的错误类别

<a id="learn-more"></a>

## 了解更多

- [Datadog API 文档](https://docs.datadoghq.com/api/)
- [GitHub 操作文档](https://docs.github.com/en/actions)
- [OpenHands SDK 文档](https://github.com/OpenHands/software-agent-sdk)
