---
title: LLM Test Data Fixtures
description: Real LLM completion data collected for comprehensive testing of the LLM class and related components. Includes function calling and non-function calling data.
---

<a id="llm-test-data-fixtures"></a>

# LLM 测试数据测试夹具

该目录包含从 `examples/hello_world.py` 收集的真实 LLM 完成数据，用于对 LLM 类和相关组件进行全面测试。

<a id="structure"></a>

## 结构

```
tests/fixtures/llm_data/
├── README.mdx                     # 这个文件
├── fncall-llm-message.json       # 函数调用对话消息
├── nonfncall-llm-message.json    # 非功能呼叫对话消息
├── llm-logs/                     # 原始函数调用完成日志
│   └── *.json                    # Individual completion log files
└── nonfncall-llm-logs/           # 原始非函数调用完成日志
    └── *.json                    # Individual completion log files
```

<a id="data-sources"></a>

## 数据来源

<a id="function-calling-data"></a>

### 函数调用数据
- **型号**：`litellm_proxy/anthropic/claude-sonnet-4-20250514`
- **特性**：原生函数调用支持
- **文件**：`fncall-llm-message.json`、`llm-logs/*.json`

<a id="non-function-calling-data"></a>

### 非函数调用数据
- **型号**：`litellm_proxy/deepseek/deepseek-chat`
- **功能**：基于提示词的函数调用模拟
- **文件**：`nonfncall-llm-message.json`、`nonfncall-llm-logs/*.json`

<a id="file-formats"></a>

## 文件格式

<a id="message-files--llm-messagejson"></a>

### 消息文件 (`*-llm-message.json`)
包含 OpenHands 格式的对话消息：
```json
[
  {
    "role": "system",
    "content": "System prompt..."
  },
  {
    "role": "user", 
    "content": "User message..."
  },
  {
    "role": "assistant",
    "content": "Assistant response...",
    "tool_calls": [...]  // Only in function calling data
  },
  {
    "role": "tool",
    "content": "Tool result...",
    "tool_call_id": "..."  // Only in function calling data
  }
]
```

<a id="raw-log-files-logsjson"></a>

### 原始日志文件 (`*/logs/*.json`)
包含完整的 LiteLLM 完成日志：
```json
{
  "messages": [...],           // Request messages
  "tools": [...],             // Tool definitions (if any)
  "kwargs": {...},            // Request parameters
  "context_window": 200000,   // Model context window
  "response": {               // LiteLLM response
    "id": "...",
    "model": "...",
    "choices": [...],
    "usage": {...}
  },
  "cost": 0.016626,          // API cost
  "timestamp": 1757003287.33, // Unix timestamp
  "latency_sec": 3.305       // Response latency
}
```


<a id="regenerating-test-data"></a>

## 重新生成测试数据

使用测试数据生成器实用程序创建新测试测试夹具：

```bash
# 生成新的测试数据
python tests/fixtures/llm_data/test_data_generator.py --api-key YOUR_API_KEY

# 验证现有测试数据
python tests/fixtures/llm_data/test_data_generator.py --api-key YOUR_API_KEY --validate-only

# 自定义模型和消息
python tests/fixtures/llm_data/test_data_generator.py \
  --api-key YOUR_API_KEY \
  --fncall-model "litellm_proxy/openai/gpt-5.5" \
  --nonfncall-model "litellm_proxy/deepseek/deepseek-chat" \
  --user-message "Create a Python script that calculates fibonacci numbers"
```