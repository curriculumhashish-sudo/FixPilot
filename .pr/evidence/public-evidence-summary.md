<a id="public-feature-evidence-export"></a>

# 公共特征证据导出

从聚合快照 2026-10-23T06:44:47+00:00 (5bd67842feefeb4570bc85bb75872fa600f78a728feba7f5bde1f79da1671ef0) 生成。

当前/冻结 ID：948/935； 初始家庭产出：34/34。 承认的账本尝试：109 TARGET/BASE 次运行中的 1480 次； 仅输出状态：0。 规范 CLI 报告在最新的每次运行和功能减少后有 1471 行。 紧凑公共 JSON 保留所有 1480 个原始账本行及其分支。

聚合和 CLI 实时账本输入一致：**True**。 A False 值表示尾部活动改变了账本； 工人完成后再生。

公共候选人：`feature-results.json`、`feature-results.md` 和 `feature-results-scan.json`。 canonical raw CLI table、summary、exact invocation 和 ledger fingerprints 仍不在本公共目录中，而是位于兄弟本地-CLI-evidence 目录中。 它们包括自由文本分类账字段并使用不同的行缩减。

tail 运行完成后，使用 --require-stable 重新运行 scrap export-public-evidence.py 脚本。 这会刷新聚合，调用 `control-agent-server evidence report --runs ... --out ...`，并重新运行元数据/秘密扫描。 它不联系服务器或APIs。

不复制任何源工件。 这些特征表中不包含响应正文、转录本、工作区文件或私有状态。 无需打印即可比较已知机密值。
