<a id="agent-behavior-testing-framework"></a>

# 智能体行为测试框架

本文档描述了集成到现有集成测试套件中的行为测试框架。

<a id="overview"></a>

## 概述

**行为测试**验证行为是否符合系统消息指南，并避免不希望的行为，智能体是现有**任务完成测试**的补充，后者验证智能体是否能成功完成任务。

两种类型的测试都使用相同的基础设施 (`BaseIntegrationTest`) 并在 CI/CD 管道中一起运行。

<a id="test-types"></a>

## 测试类型

| 类型 | 状态 | 焦点 | 示例 |
|------|--------|-------|---------|
| **积分** (t*.py) | **必填** | 智能体成功完成任务 | `t01_fix_simple_typo.py` - 修复文件中的拼写错误 |
| **行为** (b*.py) | **可选** | 智能体遵循系统指南 | `b01_no_premature_implementation.py` - 在寻求建议时不实施 |

<a id="test-type-classification"></a>

### 测试类型分类

测试按类型分类，以区分必需测试和可选测试：

- **集成测试** (t*.py) - **REQUIRED**：验证智能体是否可以成功完成基本任务。 这些测试必须通过才能发布，并重点关注智能体是否达到了预期的结果。
- **行为测试** (b*.py) - **OPTIONAL**：验证智能体是否遵循系统消息准则和最佳实践。 这些测试跟踪质量改进并且不会阻止发布。 他们关注智能体如何处理问题并与用户交互。

<a id="behavior-tests"></a>

## 行为测试

<a id="what-they-test"></a>

### 他们测试什么

行为测试验证智能体：
- ✅ 不要在寻求建议时开始实施
- ✅ 遵循系统消息指南和最佳实践
- ✅ 适当处理复杂、微妙的场景

<a id="guidelines-for-adding-behavior-tests"></a>

### 添加行为测试的指南

行为测试应关注 ** 复杂的现实场景 **，这些场景揭示了微妙的行为问题：

**做：**
- 使用来自生产或开发中遇到的实际问题的真实存储库
- 在问题解决之前检查特定的历史提交
- 重置/删除所有未来的提交，以便智能体无法通过查看解决方案来“欺骗”（例如，请参阅 `b01_no_premature_implementation.py`）
- 测试需要判断的复杂、细致的智能体行为
- 使用真实的多文件代码库和实际的上下文
- 适当时考虑使用 LLM 个法官来评估行为质量

**做不：**
- 添加简单的综合测试，可以使用基本断言轻松验证
- 创建最小化设置的假想场景（单个文件，内容简单）
- 测试过于明显或直接的行为
- 编写测试，其中“正确”行为从指令中立即显而易见

目标是捕获实际使用中出现的微妙行为问题，而不是测试基本功能。

<a id="writing-behavior-tests"></a>

## 编写行为测试

<a id="1-create-test-file"></a>

### 1. 创建测试文件

使用命名模式 `b##_*.py` 在 `tests/integration/tests/` 中创建文件：

```python
"""测试说明在这里。"""

import os
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from tests.integration.base import BaseIntegrationTest, TestResult

INSTRUCTION = "Your user prompt that might trigger undesirable behavior"

class YourBehaviorTest(BaseIntegrationTest):
    INSTRUCTION: str = INSTRUCTION
    # 注意：测试类型由文件名自动确定（b*.py = 行为）

    @property
    def tools(self) -> list[Tool]:
        register_tool("TerminalTool", TerminalTool)
        register_tool("FileEditorTool", FileEditorTool)
        return [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]

    def setup(self) -> None:
        # 创建测试所需的任何文件/目录
        pass

    def verify_result(self) -> TestResult:
        # 使用辅助方法检查智能体行为
        editing_ops = self.find_file_editing_operations()

        if editing_ops:
            return TestResult(
                success=False,
                reason="Agent edited files when it shouldn't have"
            )

        return TestResult(success=True, reason="Agent behaved correctly")
```

**注**：测试类型由文件名前缀自动确定：
- 以 `b` (e.g., `b01_*.py`) 开头的文件被归类为行为测试
- 以 `t` (e.g., `t01_*.py`) 开头的文件被分类为集成测试

<a id="2-validate-behavior"></a>

### 2. 验证行为

- 将断言集中于您想要强制执行的面向用户的行为。
- 当需要人性化评估时，请使用 `judge_agent_behavior`（参见 `tests/integration/utils/llm_judge.py`）。
- 让设置忠实于真实事件，以便智能体体验到与上下文用户所面临的相同的体验。

有关其他模式，请阅读现有套件，例如 `b01_no_premature_implementation.py`。

<a id="running-tests"></a>

## 运行测试

开发新场景时在本地使用集成运行器：

```bash
python tests/integration/run_infer.py \
  --llm-config '{"model": "claude-sonnet-4-5-20250929"}' \
  --eval-ids "b01_no_premature_implementation"
```

当应用 `integration-test` 标签或手动触发工作流程时，CI 通过 `.github/workflows/integration-runner.yml` 自动运行行为和集成测试。

<a id="test-results"></a>

## 测试结果

结果包括具有不同成功率的集成和行为测试：

```
Overall Success rate: 90.00% (9/10)
Integration tests (Required): 100.00% (8/8)
Behavior tests (Optional): 50.00% (1/2)
Evaluation Results:
✓: t01_fix_simple_typo - Successfully fixed all typos
✓: b01_no_premature_implementation - Agent correctly provided advice without implementing
...
```

在此示例中，所有必需的集成测试通过 (100%)，而某些可选行为测试失败。 这不会阻止发布，但应该调查行为测试失败以改进用户体验。

<a id="adding-new-behavior-tests"></a>

## 添加新的行为测试

1. **从真实的智能体故障中识别不良行为**
2. **创建一个可能触发该行为的提示词**
3. **使用上面的模式编写测试**
4. **提交前在本地验证**
5. **记录**您正在测试什么行为以及原因

<a id="system-message-optimization"></a>

## 系统消息优化

行为测试充当系统消息**的**回归测试。 演化系统消息时：

1. 运行行为测试套件
2. 识别开始失败的测试
3. 分析故障是否表明：
   - 系统消息需要改进
   - 测试需要更新
   - 可接受的权衡
4. 迭代系统消息
5. 重新运行测试以验证