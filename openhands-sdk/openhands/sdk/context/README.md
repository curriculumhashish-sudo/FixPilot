---
title: Context
description: Skills and knowledge that agents can rely on during conversations. Provides repository context and structured knowledge.
---

<a id="context"></a>

# 上下文

上下文提供智能体在对话期间可以依赖的技能和知识。

<a id="key-components"></a>

## 关键部件

- **AgentContext**：编写技巧和运行时间上下文； 传递到智能体来条件行为
- **技能**：嵌入具有不同触发类型的结构化知识：
  - **trigger=None**：激活所有对话（存储库范围上下文）
  - **KeywordTrigger**：当用户消息中出现特定关键字时激活
  - **TaskTrigger**：根据任务特定条件激活

<a id="quick-example"></a>

## 快速示例

```python
from openhands.sdk.context import AgentContext, KeywordTrigger, Skill

agent_context = AgentContext(
    skills=[
        Skill(
            name="repo-guidelines",
            content="Repository-wide coding standards and best practices.",
            source="AGENTS.md",
            trigger=None,  # 永远活跃的技能
        ),
        Skill(
            name="flarglebargle",
            content="If the user says flarglebargle, compliment them.",
            source="flarglebargle.md",
            trigger=KeywordTrigger(keywords=["flarglebargle"]),
        ),
    ],
    # current_datetime 默认为 datetime.now() 以实现时间感知
)
```
