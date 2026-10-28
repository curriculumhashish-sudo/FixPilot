---
title: OpenHands Agent SDK Tests
description: Test suite structure and execution strategy for the OpenHands Agent SDK. Includes unit tests, integration tests, and CI configuration.
---

<a id="openhands-agent-sdk-tests"></a>

# OpenHands 智能体 SDK Tests

该目录包含测试套件为OpenHands智能体SDK。

<a id="test-structure"></a>

## 测试结构

```
tests/
├── cross/         # 跨包测试
├── integration/   # 集成测试
├── sdk/           # SDK 单元测试
└── tools/         # 工具单元测试
```

<a id="test-categories"></a>

## 测试类别

<a id="integration-tests-integration"></a>

### 集成测试 (`integration`)

端到端测试覆盖了大部分代码库，通常比其他测试慢。
**CI 执行：** CI 每晚运行这些测试。 代码更改不会触发这些测试运行。

<a id="unit-tests-cross-sdk-tools"></a>

### 单元测试 (`cross`, `sdk`, `tools`)

防止核心功能回归的特定于组件的测试。

**CI执行：**CI根据代码更改智能地运行这些测试：
- **SDK 测试** (`sdk/`)：在 `openhands-sdk/**` 或 `tests/sdk/**` 中检测到更改时运行
- **工具测试** (`tools/`)：在 `openhands-tools/**` 或 `tests/tools/**` 中检测到更改时运行
- **交叉测试** (`cross/`)：在任何源代码或测试文件中检测到更改时运行
