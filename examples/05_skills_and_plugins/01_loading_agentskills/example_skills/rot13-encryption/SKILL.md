---
name: rot13-encryption
description: >
  This skill helps encrypt and decrypt messages using ROT13 cipher.
  Use when the user asks to "encrypt" or "decrypt" a message.
license: MIT
compatibility: Requires bash
metadata:
  author: openhands
  version: "1.0"
triggers:
  - encrypt
  - decrypt
  - cipher
---

<a id="rot13-encryption-skill"></a>

# ROT13 加密技能

该技能提供了使用ROT13加密消息的脚本。

<a id="how-to-encrypt"></a>

## 如何加密

使用您的消息运行 [encrypt.sh](scripts/encrypt.sh) 脚本：

```bash
./scripts/encrypt.sh "your message"
```

<a id="examples"></a>

## 示例

有关更多用法示例，请参阅 [examples.md](references/examples.md)。
