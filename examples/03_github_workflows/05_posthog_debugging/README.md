<a id="posthog-error-debugging-workflow"></a>

# PostHog 错误调试工作流程

此示例演示如何使用 OpenHands 智能体自动调试 GitHub 操作工作流程中 PostHog 中的错误。

<a id="overview"></a>

## 概述

工作流程：
1. 根据可配置查询从 PostHog 获取事件
2. 搜索或创建 GitHub 个问题以跟踪错误
3. 克隆相关存储库以进行综合分析
4. 使用 OpenHands AI 智能体分析代码并确定根本原因
5. 将调试见解作为对 GitHub 问题的评论发布

<a id="files"></a>

## 文件

- `workflow.yml` - GitHub 手动触发的操作工作流程
- `posthog_debugging.py` - 主要调试脚本
- `debug_prompt.jinja` - AI 调试模板提示词

<a id="features"></a>

## 特点

<a id="manual-trigger"></a>

### 手动触发
通过具有可配置输入的 GitHub Actions UI 按需运行：
- **查询类型**：选择`event-query`（事件名称）或`event-id`（特定事件ID）
- **PostHog查询**：
  - 对于 `event-query`：事件名称，如 `$exception`、`error` 或自定义事件名称
  - 对于 `event-id`：特定事件 ID
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
POSTHOG_API_KEY: Your PostHog Personal API key
POSTHOG_PROJECT_ID: Your PostHog project ID
POSTHOG_HOST: PostHog host (e.g., us.posthog.com, eu.posthog.com)
LLM_API_KEY: API key for LLM service
LLM_BASE_URL: Base URL for LLM service (optional)
```

**注**：`GITHUB_TOKEN`由GitHub操作自动提供。

<a id="getting-posthog-credentials"></a>

### 获取 PostHog 凭据

1. **API密钥**：转到您的PostHog实例→设置→个人API密钥→创建新密钥
   - 确保密钥具有 `query:read` 范围
2. **项目 ID**：在您的项目中找到 URL：`https://app.posthog.com/project/{PROJECT_ID}/...`
3. **主机**：
   - 美国云：`us.posthog.com`
   - 欧盟云：`eu.posthog.com`
   - 自托管：您的实例主机名

<a id="installation"></a>

### 安装

1. 将 `workflow.yml` 复制到存储库的 `.github/workflows/` 目录（e.g., `.github/workflows/posthog-debugging.yml`）
2. 在仓库设置 → 机密和变量 → 操作中配置所需的机密
3. （可选）在 YAML 文件中自定义工作流程输入和默认值

**注意**：工作流在运行时自动从SDK存储库下载最新版本的`posthog_debugging.py`和`debug_prompt.jinja`。 无需将这些文件复制到您的存储库，除非您想自定义它们。

<a id="usage"></a>

## 用途

<a id="via-github-actions-ui"></a>

### 通过 GitHub 操作 UI

1. 转到存储库中的 **Actions** 选项卡
2. 选择 **PostHog 错误调试** 工作流程
3. 单击**运行工作流程**
4. 配置输入：
   - **查询类型**：选择`event-query`或`event-id`（默认：`event-query`）
   - **PostHog查询**：
     - 对于 `event-query`：事件名称（默认值：`$exception`）
     - 对于 `event-id`：事件 ID
   - **存储库列表**：要分析的以逗号分隔的存储库（默认值：`OpenHands/OpenHands,All-Hands-AI/infra`）
   - **问题存储库**：创建问题的位置（默认值：`All-Hands-AI/infra`）
   - **父问题**：用于跟踪的可选父问题URL
   - **问题前缀**：问题标题的前缀（默认值：`PostHog Error: `）
   - **LLM 模型**：要使用的模型（默认值：`gpt-5.5`）
5. 单击**运行工作流程**

<a id="via-github-cli"></a>

### 通过 GitHub CLI

**搜索异常事件：**
```bash
gh workflow run posthog-debugging.yml \
  -f query_type="event-query" \
  -f posthog_query="$exception" \
  -f repo_list="OpenHands/OpenHands,All-Hands-AI/infra" \
  -f issue_repo="All-Hands-AI/infra"
```

**按 ID 调试特定事件：**
```bash
gh workflow run posthog-debugging.yml \
  -f query_type="event-id" \
  -f posthog_query="01234567-89ab-cdef-0123-456789abcdef" \
  -f repo_list="OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy" \
  -f issue_repo="All-Hands-AI/infra"
```

<a id="via-command-line"></a>

### 通过命令行

```bash
# 搜索异常事件
python posthog_debugging.py \
  --query-type event-query \
  --query '$exception' \
  --repos "OpenHands/OpenHands,All-Hands-AI/infra" \
  --issue-repo "All-Hands-AI/infra" \
  --issue-prefix "PostHog Error: "

# 调试自定义错误事件
python posthog_debugging.py \
  --query-type event-query \
  --query 'application_error' \
  --repos "OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy" \
  --issue-repo "All-Hands-AI/infra"
```

<a id="example"></a>

## 示例

<a id="input-search-query"></a>

### 输入（搜索查询）
```yaml
query_type: "event-query"
posthog_query: "$exception"
repo_list: "OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy"
issue_repo: "All-Hands-AI/infra"
issue_parent: "https://github.com/All-Hands-AI/infra/issues/672"
```

<a id="input-specific-event-id"></a>

### 输入（特定事件 ID）
```yaml
query_type: "event-id"
posthog_query: "01234567-89ab-cdef-0123-456789abcdef"
repo_list: "OpenHands/OpenHands,All-Hands-AI/infra,All-Hands-AI/deploy"
issue_repo: "All-Hands-AI/infra"
issue_parent: "https://github.com/All-Hands-AI/infra/issues/672"
```

<a id="output"></a>

### 输出
- **控制台**：显示事件获取、存储库克隆和智能体分析的进度日志
- **GitHub 问题**：使用事件详细信息创建或更新
- **GitHub评论**：人工智能生成的分析，包含根本原因和建议
- **Artifacts**：保存7天的调试数据和日志

<a id="configuration"></a>

## 配置

<a id="posthog-event-query-examples"></a>

### PostHog 事件查询示例

```yaml
# 异常事件（PostHog自动捕获这些）
$exception

# 页面浏览错误
$pageview

# Custom error events
application_error

# API error events
api_error

# User action errors
checkout_error
```

<a id="using-hogql-for-advanced-queries"></a>

### 使用 HogQL 进行高级查询

对于更复杂的查询，您可以修改脚本以使用HogQL：

```python
# 查询具有特定属性的事件
hogql_query = """
SELECT * FROM events 
WHERE event = '$exception' 
  AND properties.$exception_type = 'ValueError'
ORDER BY timestamp DESC 
LIMIT 10
"""

# 查询某个时间范围内的事件
hogql_query = """
SELECT * FROM events 
WHERE event = 'application_error'
  AND timestamp > now() - INTERVAL 7 DAY
ORDER BY timestamp DESC
"""
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
- `anthropic/claude-haiku-4-5-20251001` - 更快、更便宜
- `anthropic/claude-3-5-sonnet-20241022` - 替代方案

<a id="workflow-details"></a>

## 工作流程详情

<a id="inputs"></a>

### 输入

| 输入 | 类型 | 必填 | 默认 | 描述 |
|-------|------|----------|---------|-------------|
| `posthog_query` | 字符串 | 是的 | `$exception` | PostHog 事件名称或事件 ID |
| `query_type` | 字符串 | 否 | `event-query` | 查询类型：`event-query` 或 `event-id` |
| `repo_list` | 字符串 | 是的 | `OpenHands/OpenHands,All-Hands-AI/infra` | 以逗号分隔的存储库列表 |
| `issue_repo` | 字符串 | 是的 | `All-Hands-AI/infra` | 用于创建/更新问题的存储库 |
| `issue_parent` | 字符串 | 否 | - | 用于跟踪的父 GitHub 问题 URL |
| `issue_prefix` | 字符串 | 否 | `PostHog Error: ` | 问题标题的前缀 |
| `max_events` | 字符串 | 否 | `5` | 要获取的最大事件数 |
| `llm_model` | 字符串 | 否 | `gpt-5.5` | LLM 使用型号 |

<a id="outputs"></a>

### 输出

- **GitHub 问题**：使用事件详细信息创建或更新
- **GitHub评论**：人工智能分析发布到问题
- **Artifacts**：调试数据和日志（保留7天）

<a id="permissions"></a>

### 权限

```yaml
permissions:
  contents: read   # 克隆存储库
  issues: write    # 创建/更新问题和评论
```

<a id="understanding-posthog-events"></a>

## 了解 PostHog 事件

<a id="common-event-types"></a>

### 常见事件类型

PostHog自动捕获多种事件类型：

- **`$exception`**：JavaScript错误和异常
- **`$pageview`**：页面浏览量
- **`$pageleave`**：当用户离开页面时
- **`$autocapture`**：自动捕获用户交互
- **自定义事件**：您在应用程序中手动跟踪的事件

<a id="event-properties"></a>

### 事件属性

异常事件通常包括：

```json
{
  "$exception_type": "Error",
  "$exception_message": "Cannot read property 'x' of undefined",
  "$exception_list": [...],
  "$exception_stack_trace_raw": "...",
  "$current_url": "https://example.com/page",
  "$browser": "Chrome",
  "$os": "Mac OS X"
}
```

自定义事件可以包含您定义的任何属性。

<a id="customization"></a>

## 定制化

<a id="for-production-use"></a>

### 用于生产环境

考虑创建一个单独的配置存储库：
- 计划运行（每天进行严重错误，每周进行综合分析）
- 预定义的事件类别
- 存储库组定义
- 环境特定设置

<a id="adding-scheduled-runs"></a>

### 添加预定运行

添加到工作流程的 `on:` 部分：

```yaml
on:
  workflow_dispatch:
    # ... existing inputs ...
  
  schedule:
    # 每天 09:00 UTC 处理例外事件
    - cron: '0 9 * * *'
    # 每周一 09:00 UTC 进行全面扫描
    - cron: '0 9 * * 1'
```

<a id="matrix-strategy"></a>

### 矩阵策略

并行运行多个查询：

```yaml
jobs:
  debug-events:
    strategy:
      matrix:
        query:
          - "$exception"
          - "application_error"
          - "api_error"
      fail-fast: false
```

<a id="troubleshooting"></a>

## 故障排除

<a id="workflow-fails-to-start"></a>

### 工作流程无法启动
- 验证所有必需的机密均已配置
- 检查`GITHUB_TOKEN`是否具有必要的权限
- 使用 `yamllint` 检查工作流语法

<a id="no-events-found"></a>

### 未找到活动
- 验证事件名称是否正确（区分大小写）
- 检查您的 PostHog 项目是否有该类型的事件
- 首先尝试查询 PostHog UI 以确认事件存在
- 确保 API 键具有 `query:read` 范围

<a id="api-authentication-errors"></a>

### API 身份验证错误
- 验证 `POSTHOG_API_KEY` 是个人 API 密钥（不是项目 API 密钥）
- 检查 API 密钥是否已过期
- 确保`POSTHOG_PROJECT_ID`正确
- 验证 `POSTHOG_HOST` 与您的 PostHog 实例匹配

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

<a id="comparing-with-datadog-example"></a>

## 与DataDog示例比较

此示例类似于 DataDog 调试示例，但适用于 PostHog：

| 特点 | DataDog | PostHog |
|---------|---------|---------|
| **数据来源** | 日志和错误跟踪 | 事件和自定义跟踪 |
| **Query Types** | 日志查询、错误 ID | 事件名称、事件 ID |
| **身份验证** | API 仅键和应用密钥 | 个人 API 钥匙 |
| **查询语言** | Datadog 查询语法 | HogQL（类似SQL） |
| **时间范围** | 过滤时间戳 | 过滤时间戳 |
| **用例** | 服务器错误、日志 | 用户错误、自定义事件 |

<a id="related-examples"></a>

## 相关示例

- **基本操作**：`examples/03_github_workflows/01_basic_action/` - 简单工作流程示例
- **PR评论**：`examples/03_github_workflows/02_pr_review/` - PR自动化示例
- **TODO 管理**：`examples/03_github_workflows/03_todo_management/` - 自动 TODO 跟踪
- **DataDog 调试**：`examples/03_github_workflows/04_datadog_debugging/` - DataDog 的类似调试

<a id="benefits"></a>

## 好处

1. **自动调试**：AI分析代码，无需人工干预
2. **减少MTTR**：更快地识别根本原因
3. **上下文-Aware**：完整图片的多存储库分析
4. **无重复**：智能问题跟踪可防止混乱
5. **可行的见解**：明确的修复建议
6. **可扩展**：轻松添加新的事件类别
7. **以用户为中心**：跟踪用户遇到的错误

<a id="learn-more"></a>

## 了解更多

- [PostHog API 文档](https://posthog.com/docs/api)
- [PostHog HogQL 文档](https://posthog.com/docs/hogql)
- [GitHub 操作文档](https://docs.github.com/en/actions)
- [OpenHands SDK 文档](https://github.com/OpenHands/software-agent-sdk)
