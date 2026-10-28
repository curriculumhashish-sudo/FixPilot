<a id="public-weak-type-budget"></a>

# 公共弱型预算

`config/public-type-budget.json` 记录可从包的公共声明入口访问的现有 `any` 和 `unknown` 位置。 它是一个棘轮，而不是一个目标。

构建后运行检查：

```bash
npm run check:public-type-budget
```

在以下情况下检查失败：

- 出现新的公共 `any` 或 `unknown` 位置；
- 经批准的地点发生变化或扩大； 或
- 在不删除其预算条目的情况下收紧薄弱位置。

当删除弱类型时，在同一更改中删除其匹配的预算元组。 不要重新生成和替换整个预算：这将批准无关紧要的回归 scripts/check-public-type-budget.mjs
--print-current` 是用于有意审查的更新的检查辅助工具。

每个组都记录一个类别、原因和所有者。 公共领域合同、通用传输层内部细节和故意不透明的云代理载荷保持分离，以便在不同标准下进行审查。

Agent Server 生成的声明 `dist/generated/` 被排除在预算之外。 他们的源 OpenAPI 文档受 Agent Server 模式质量许可名单管辖，生成的文件漂移由以下各项单独检查
`npm run check:agent-server-api`.
