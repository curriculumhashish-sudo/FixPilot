<a id="child-launches-in-fresh-workspaces--upstream-verification"></a>

# Child 在 fresh 工作区中启动 - 上游验证

已于 2026 年 10 月 24 日在 macOS 上使用 Python 3.13.11、SDK/Agent Server 1.58.1 进行验证并冻结开发依赖项。

基数：`acd96e6fa424c02432304395b9208f99be24b54d`。
已验证头：`05e56fdc0e919c5a6898c44293649a84086997d5`。

<a id="reproduction"></a>

## 繁殖

源回归它最初仅应用于上游基线。 它启动了一个真正的 uvicorn 服务器，并创建了一个正常的父进程 HTTP 在空的工作区确认启动时初始化了 Git 但没有提交，并发布了一个默认子请求。 这失败了 HTTP 500错误 `git worktree add ... HEAD`; 基本运行在 4.52 秒内报告一次失败的测试。

在固定头，相同的HTTP工作流返回201，并且共享隔离，完成子进程，保留父/子关系，原始文件，Git状态和未出生HEAD，并删除两个对话。 存储库的测试夹具修补了 LLM； HTTP，服务器路由、生命周期和Git都是真实的。 此过程不要求新的外部模型、Docker 或基准测试运行。 原始 Linux/模型证据保留在 `issue-42-evidence.md` 中记录的源修订版中。

<a id="validation"></a>

## 验证

```sh
uv sync --frozen --dev
uv run --frozen pytest \
  tests/cross/test_remote_conversation_live_server.py::test_child_launch_in_fresh_workspace_preserves_unborn_repository \
  tests/agent_server/test_parent_child_conversations.py \
  tests/tools/child_conversation/test_start_child_conversation.py \
  tests/agent_server/test_conversation_service.py -k 'child or worktree' -q
```

结果：6.10 秒内，**45 人通过，128 人取消选择，现有两个弃用警告**。 所有更改代码预提交检查均已通过，包括Ruff、pycodestyle、Pyright、导入规则和工具注册。 添加的explicit-ref 回归也通过了其独立的11测试工作树运行。

保留较新的上游工作树基本选项和自定义分支前缀。 测试覆盖了默认/头部/显式引用分支选择、已提交仓库、子目录、远程默认跟踪，尽管本地未出生的HEAD，以及一个缺失的显式引用导致没有创建对话或工作树的遗留文件。 回退方案仅处理缺少的可用默认/头提交； 其他 Git 故障会传播。 另一位审阅者未发现重大正确性或兼容性问题。

最终证据提交不会更改产品或测试代码。 测试测试夹具拥有并停止了他们的服务器； 此通道没有启动持久服务。
