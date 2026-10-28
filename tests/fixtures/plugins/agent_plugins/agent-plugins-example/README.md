<a id="agent-plugins-example"></a>

# 智能体插件示例

[智能体插件规范 v1.0.0](https://agent-plugins.org/specification) 的可复制参考包。

该存储库演示了可移植核心，并包含一项智能体技能，可帮助从特定于客户端的格式迁移现有插件。 仅供参考示例，不能替代规范性规范； 如果它们不同，则规范获胜。

<a id="layout"></a>

## 布局

```text
agent-plugins-example/
├── plugin.json                         # Required portable manifest
├── skills/                             # Portable Agent Skills
│   └── migrate-agent-plugin/
│       ├── SKILL.md
│       └── references/
│           ├── client-extensions.md
│           ├── migration-guide.md
│           └── validation-checklist.md
├── README.md
└── LICENSE
```

最小的有效插件只需要 `plugin.json`。 该示例包含一项技能，因此它很有用并且在结构上具有说明性。

<a id="the-portable-core"></a>

## 便携式核心

智能体 Plugins v1 定义了两种可移植组件类型：

- 智能体 `skills/` 的直接子目录下的技能。
- MCP 位于可选根 `mcp.json` 中的服务器，使用匹配的 v1.0.0 MCP 模式。

根`plugin.json`模式是封闭的。 请勿在其顶层添加 `hooks`、`agents`、`commands`、`mcpServers`、`lspServers` 或任意客户端字段。 将可移植的 MCP 配置放入 `mcp.json` 中，并将客户端拥有的清单数据放入 `extensions` 中。

请参阅[插件元数据](https://agent-plugins.org/plugin-authors/manifest)、[技能](https://agent-plugins.org/plugin-authors/skills)、[MCP服务器](https://agent-plugins.org/plugin-authors/mcp-servers)和[客户端扩展](https://agent-plugins.org/plugin-authors/client-extensions)的权威文档。

<a id="add-client-specific-capabilities-safely"></a>

## 安全地添加特定于客户端的功能

挂钩和类似功能不是可移植的 v1 组件。 客户端可以通过其拥有的反向域扩展命名空间添加它们并记录：

```text
your-plugin/
├── plugin.json
├── skills/
├── mcp.json                            # Optional portable MCP configuration
└── com.vendor.client/                  # Optional client extension
    └── hooks/
        └── hooks.json
```

如果客户端同时使用清单数据和文件，`plugin.json` 可以包含扩展对象：

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "your-plugin",
  "extensions": {
    "com.vendor.client": {
      "settingDefinedByThatClient": true
    }
  }
}
```

`com.vendor.client` 是说明性的。 仅使用命名空间和拥有它们的客户端记录的字段。 其他客户端会忽略他们未实现的扩展，从而使可移植技能和 MCP 配置可用。

<a id="migrate-without-breaking-the-existing-plugin"></a>

## 迁移而不破坏现有插件

使用附加迁移：

1. 添加并验证根 `plugin.json`，而不删除工作平台文件。
2. 将可重复使用的技能移动或复制到`skills/<skill-name>/SKILL.md`。
3. 将可移植 MCP 服务器转换为具有显式传输层类型的根 `mcp.json`。
4. 将挂钩、智能体、命令、LSP、UI 和市场元数据保留在客户端扩展或该平台所需的单独兼容性包中。
5. 在删除旧文件之前测试可移植核心和每个受支持的客户端包。

附带的 [`migrate-agent-plugin` 技能 ](skills/migrate-agent-plugin/SKILL.md) 包含完整的迁移工作流程、工件映射、扩展策略和验证检查表。

<a id="copy-this-example"></a>

## 复制这个例子

1. 复制此目录并将其重命名以匹配您的插件。
2. 更新 `name`、`version`、`description`、`author` 以及 `plugin.json` 中其他允许的元数据。
3. 替换示例技能或在 `skills/` 下添加更多直接子技能。
4. 仅当插件提供 MCP 个服务器时才添加 `mcp.json`。
5. 仅为您的目标客户端实现的命名空间添加客户端扩展。
6. 验证路径、模式、技能和每个支持的客户端集成。

在可移植规范中，目录名和元数据名不必完全一致，但保持它们一致对于可预测的打包和发现是强烈推荐的。
