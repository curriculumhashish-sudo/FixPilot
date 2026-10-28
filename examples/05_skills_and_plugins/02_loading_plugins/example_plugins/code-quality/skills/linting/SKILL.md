---
name: python-linting
description: >
  This skill helps lint Python code using ruff.
  Use when the user asks to "lint", "check code quality", or "fix style issues".
license: MIT
compatibility: Requires Python and ruff
metadata:
  author: openhands
  version: "1.0"
triggers:
  - lint
  - linting
  - code quality
  - style check
  - ruff
---

<a id="python-linting-skill"></a>

# Python 静态检查技能

此技能提供使用 Ruff 的静态检查 Python 代码的说明。

<a id="how-to-lint"></a>

## 如何静态检查

运行 Ruff 检查问题：

```bash
ruff check .
```

自动修复问题：

```bash
ruff check --fix .
```

<a id="common-options"></a>

## 常用选项

- `--select E,W` - 只检查错误和警告
- `--ignore E501` - 忽略行长度错误
- `--fix` - 自动修复可修复的问题

<a id="example-output"></a>

## 示例输出

```
example.py:1:1: F401 [*] `os` imported but unused
example.py:5:5: E302 Expected 2 blank lines, found 1
Found 2 errors (1 fixable).
```
