---
name: code-style-guide
description: >
  Project coding standards and style guidelines. Always follow these
  conventions when writing or reviewing code.
license: MIT
---

<a id="code-style-guide"></a>

# 代码风格指南

此项目中的所有代码都遵循这些约定。

## Python

- 使用 4 个空格进行缩进
- 最大行长：88个字符（黑色默认）
- 使用类型提示作为函数签名
- 优先使用 f 字符串而不是 `.format()` 或 `%` 格式

<a id="naming-conventions"></a>

## 命名约定

- 课程：`PascalCase`
- 函数/变量：`snake_case`
- 常数：`UPPER_SNAKE_CASE`
- 私人会员：`_leading_underscore`

<a id="documentation"></a>

## 文档

- 所有公共职能必须有文档字符串
- 使用 Google 风格文档字符串
- 不使用类型提示时，在文档字符串中包含类型信息
