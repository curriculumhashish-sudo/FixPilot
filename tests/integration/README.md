<a id="integration-tests"></a>

# 集成测试

此目录包含智能体-SDK 的集成测试，它们使用真实的 LLM 调用来测试端到端功能。

<a id="overview"></a>

## 概述

集成测试旨在通过运行完整的工作流程来验证智能体-SDK 是否与真实的 LLM 模型正常工作。 每个测试都会创建一个临时环境，为智能体提供特定工具，给出指令，然后验证结果。

<a id="test-types"></a>

### 测试类型

测试根据文件名前缀分为三种类型：

- **集成测试** (`t*.py`) - **REQUIRED**：验证智能体是否成功完成基本任务。 这些测试必须通过才能发布，并重点关注任务完成和结果。
- **行为测试** (`b*.py`) - **OPTIONAL**：验证智能体是否遵循系统消息准则和最佳实践。 这些测试跟踪质量改进并重点关注智能体如何解决问题。 故障不会阻止发布，但应该解决以获得最佳用户体验。
- **上下文压缩器 tests** (`c*.py`) - **OPTIONAL, NON-BLOCKING**: 压力测试的上下文压缩系统与的交互 LLM  APIs 确保兼容性。 这些测试仅在有限的集运行 LLMs (目前，Claude Opus 4.5和 GPT-5.1 Codex Max) 和其他触发器是分别触发的集成测试。 他们验证对话上下文压缩在不同模型上工作正常 API patterns.

单独计算每种测试类型的成功率，以跟踪完成能力、行为质量和上下文压缩器可靠性。

有关行为测试的更多详细信息，请参阅 [BEHAVIOR_TESTS.md](BEHAVIOR_TESTS.md)。

<a id="directory-structure"></a>

## 目录结构

```
tests/integration/
├── README.md                    # 这个文件
├── BEHAVIOR_TESTS.md            # 行为测试框架文档
├── __init__.py                  # 包初始化
├── base.py                      # 集成测试的基类
├── run_infer.py                 # 主要测试运行脚本
├── run_infer.sh                 # 用于运行测试的 Shell 脚本包装器
├── outputs/                     # 测试结果和报告（自动生成）
├── tests/                       # 单独的测试文件
│   ├── t*.py                    # Task completion tests (required)
│   ├── b*.py                    # Agent behavior tests (optional)
│   └── c*.py                    # Condenser stress tests (optional, non-blocking)
└── utils/                       # 测试实用程序（e.g.、llm_judge.py）
```

<a id="running-integration-tests"></a>

## 正在运行集成测试

<a id="from-github"></a>

### 来自 GitHub

通过将标签 `integration-test` 标记到拉取请求，运行集成测试 if from GitHub 的最简单方法。 测试执行后，拉取请求评论将立即通知您。 测试结果（以及所有日志）将可以使用评论中添加的链接下载。

对于上下文压缩器测试，请改用 `condenser-test` 标签。

<a id="locally"></a>

### 本地

```bash
# 运行所有测试
uv run python tests/integration/run_infer.py --llm-config '{"model": "litellm_proxy/anthropic/claude-sonnet-4-5-20250929"}'

# 运行特定测试
uv run python tests/integration/run_infer.py --llm-config '{"model": "litellm_proxy/anthropic/claude-sonnet-4-5-20250929"}' --eval-ids t01_fix_simple_typo

# 仅运行上下文压缩器个测试
uv run python tests/integration/run_infer.py --llm-config '{"model": "litellm_proxy/anthropic/claude-opus-4-5", "extended_thinking": true}' --test-type condenser
```

<a id="automated-testing-with-github-actions"></a>

## 使用 GitHub 操作进行自动化测试

测试使用两个独立的工作流程通过 GitHub 操作自动执行：

<a id="integrationbehavior-tests-workflow"></a>

### 集成/行为测试工作流程

此工作流在 `.github/workflows/integration-runner.yml` 中定义，运行集成和行为测试。

**触发器：**
1. **拉取请求标签**：当 PR 被标记为 `integration-test` 或 `behavior-test` 时
2. **手动触发**：通过具有所需原因的工作流调度

**测试覆盖范围：**在 5 LLM 个型号上运行（GPT-5.5、DeepSeek V4.1 Flash、MiniMax M2.7、Gemini 3.1 Pro、Claude Sonnet 4.6）

<a id="condenser-tests-workflow"></a>

### 上下文压缩器测试工作流程

此工作流在 `.github/workflows/condenser-runner.yml` 中定义，单独运行上下文压缩器压力测试。

**触发器：**
1. **拉取请求标签**：当PR被标记为`condenser-test`时
2. **手动触发**：通过具有所需原因的工作流调度

**测试覆盖率：** 仅限于2 LLMs （克劳德 Opus 4.5 具有扩展思维， GPT-5.1 Codex Max) 用于节省成本并验证跨模型兼容性

**注意：** 上下文压缩器测试是非阻塞的，并且不会阻止 PR 合并

<a id="available-tests"></a>

## 可用测试

<a id="integration-tests-tpy---required"></a>

### 集成测试 (`t*.py`) - **必填**

这些测试必须通过才能发布并验证智能体可以成功完成基本任务：

- **t01_fix_simple_typo** - 测试智能体是否可以修复文件中的拼写错误
- **t02_add_bash_hello** - 测试智能体是否可以执行 bash 命令
- **t03_jupyter_write_file** - 测试 Jupyter 笔记本集成
- **t04_git_staging** - 测试 git 操作
- **t05_simple_browsing** - 测试网页浏览功能
- **t06_github_pr_browsing** - 测试 GitHub PR 浏览
- **t07_interactive_commands** - 测试交互式命令处理
- **t08_image_file_viewing** - 测试图像文件查看功能

<a id="behavior-tests-bpy---optional"></a>

### 行为测试 (`b*.py`) - **可选**

这些测试跟踪质量改进并且不会阻止发布。 他们验证智能体遵循系统消息准则并适当处理复杂、微妙的场景：

- **b01_no_premature_implementation** - 测试智能体在寻求建议时不会开始实施。 使用了一个真实的代码库（软件-智能体-SDK 检出到历史提交）来测试智能体是否探索、提供建议，并提出澄清问题，而不是立即创建或编辑文件。

有关行为测试和添加新测试的指南的更多详细信息，请参阅 [BEHAVIOR_TESTS.md](BEHAVIOR_TESTS.md)。

<a id="condenser-tests-cpy---optional-non-blocking"></a>

### 上下文压缩器测试 (`c*.py`) - **可选，非阻塞**

这些测试压力测试系统的上下文压缩交互 LLM APIs，以确保在不同模型之间兼容性。 与集成测试和上下文压缩器测试不同，LLMs（目前是Claude Opus 4.5和GPT-5.1 Codex Max）仅在有限的范围内运行，以节省成本并验证跨模型兼容性。 它们通过`condenser-test`标签单独触发，并且不会阻止PR合并。

**目的：**验证对话上下文压缩在不同模型和API模式中是否正常工作，特别关注：
- 特定于模型的特征（e.g.，Claude Opus 中的思维块）
- 上下文压缩个触发器（token 个限制、事件计数、显式请求）
- 对话历史管理
- API 上下文压缩之后的签名兼容性

**当前测试：**

- **c01_thinking_block_condenser** - 测试 Claude Opus 的思维障碍在上下文压缩期间是否得到正确处理。 验证：
  - 多步骤对话中会产生多个思维块
  - 上下文压缩已正确触发
  - 第一个思维块在上下文压缩期间被遗忘
  - 后来的思维块在上下文压缩之后被保留
  - 将压缩历史记录发送到 API 时不会出现格式错误的签名错误
- **c02_hard_context_reset** - 当上下文压缩不可用时测试硬上下文重置。 验证：
  - 当不存在有效范围时，显式 condense() 调用会触发硬上下文重置
  - 硬重置保留主导系统提示词，用摘要替换所有其他历史记录，并保留下一个 LLM 请求系统优先
  - 对话可以在稍后的正常时间内继续上下文压缩
- **c03_delayed_condensation** - 测试因软要求而延迟上下文压缩。 验证：
  - 当上下文压缩不可用时，软需求（资源限制）可以正常继续
  - 当上下文压缩无法满足时，对话继续而不会崩溃
  - 一旦多个原子单元可用，上下文压缩就会成功
- **c04_token_condenser** - 测试基于 token 的上下文压缩是否正常工作。 验证：
  - 智能体可以通过 LLMSummarizingCondenser 来配置 max_tokens
  - 上下文压缩器正确使用 get_token_count 来衡量对话大小
  - 当超出 token 限制时触发上下文压缩
- **c05_size_condenser** - 测试基于大小的上下文压缩是否正常工作。 验证：
  - 智能体可以通过 LLMSummarizingCondenser 来配置 max_size
  - 上下文压缩器正确计数事件以测量对话大小
  - 上下文压缩超出事件计数限制时触发

<a id="writing-integration-tests"></a>

## 写作集成测试

所有集成测试都继承自`base.py`中的`BaseIntegrationTest`。 基类提供了一个具有多个可自定义属性的一致框架：

<a id="required-methods"></a>

### 所需方法

- **`tools`**（属性）- 智能体可用的工具列表
- **`setup()`** - 初始化特定于测试的设置（创建文件等）
- **`verify_result()`** - 验证测试成功并返回`TestResult`

<a id="optional-properties"></a>

### 可选属性

- **`condenser`**（属性）- 智能体的可选上下文压缩器配置（默认值：`None`）
  - 覆盖以测试上下文压缩或管理长对话
  - 示例：`c04_token_condenser` 使用它来验证 token 计数
- **`max_iteration_per_run`**（属性）- 每个对话的最大迭代次数（默认值：`100`）
  - 覆盖以限制 LLM 调用以加快测试速度
  - 对于应该快速完成的测试很有用

<a id="conversation-control"></a>

### 对话控制

定义集成测试的标准方法是设置 `INSTRUCTION` 类变量。 这些指令作为第一条用户消息发送到智能体。

然而，如果测试功能需要多个指令或在测试过程中访问会话对象，则测试可以由重写`run_instructions`方法来定义。 该方法提供了一个`LocalConversation`对象，可以通过发送消息、触发凝结等方式直接操作该对象。
