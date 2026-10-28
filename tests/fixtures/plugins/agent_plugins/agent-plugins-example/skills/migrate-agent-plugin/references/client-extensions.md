<a id="client-extensions"></a>

# 客户端扩展

智能体插件 v1 保持了可移植核心的小型化。 客户端扩展为钩子、智能体、命令、LSP、UI 和其他尚未变得可移植的行为提供了逃生舱口。

<a id="rules"></a>

## 规则

1. 扩展名命名空间是反向域标识符，例如`com.vendor.client`。
2. 拥有命名空间的客户端定义其字段、文件、验证和运行时行为。
3. 清单扩展数据属于根 `plugin.json` 中的 `extensions`。
4. 扩展文件位于名称与命名空间完全匹配的顶级目录中。
5. 其他客户端忽略命名空间，他们不会在不丢失有效可移植组件的情况下实现。
6. 扩展并不是插件作者构建现有客户端会自动理解的字段的方法。

<a id="manifest-data"></a>

## 舱单数据

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

可移植规范仅验证每个命名空间值是一个对象。 拥有的客户端定义了其中的所有内容。

<a id="extension-files"></a>

## 扩展文件

```text
your-plugin/
├── plugin.json
├── skills/
└── com.vendor.client/
    ├── hooks/
    │   └── hooks.json
    └── agents/
        └── reviewer.md
```

仅当 `com.vendor.client` 实际实现这些路径时，此布局才有效。

<a id="choose-the-right-compatibility-strategy"></a>

## 选择正确的兼容性策略

<a id="the-client-documents-an-agent-plugins-extension-namespace"></a>

### 客户端记录了智能体插件扩展命名空间

使用其精确的命名空间、字段和目录布局。 测试扩展中的故障与可移植技能和 MCP 配置分开。

<a id="the-client-supports-agent-plugins-core-but-still-discovers-legacy-add-ons"></a>

### 客户端支持智能体插件核心，但仍然发现旧版附加组件

保持根清单一致。 遵循客户端记录的旧挂钩​​或智能体的附加加载行为，并将这些文件标记为客户端特定的文件。 如果该布局与严格的可移植打包冲突，请从可移植源生成单独的客户端发行版。

<a id="the-client-does-not-support-agent-plugins-core"></a>

### 客户端不支持智能体插件核心

保持旧插件正常工作并添加可移植的同级包。 在安全的情况下共享底层技能文本、脚本和服务器代码，但避免在任一包根目录之外解析的符号链接。

<a id="hooks"></a>

## 挂钩

钩子是一种常见的扩展候选，但智能体版本的插件没有定义其事件名称、输入/输出协议、命令格式、安全模型或发现路径。 保留现有的挂钩，直到目标客户端记录替换为止。 将挂钩脚本审查为可执行代码，并测试迁移后的批准、拒绝、失败和超时行为。

<a id="do-not-put-client-fields-at-the-manifest-top-level"></a>

## 不要将客户端字段放在清单顶层

这些示例在智能体 Plugins v1 根清单中不符合要求：

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "your-plugin",
  "hooks": "hooks.json",
  "agents": "agents/"
}
```

请改用已记录的扩展或兼容性包。
