<a id="issue-42-default-child-launch-in-a-fresh-workspace"></a>

# 问题 #42：默认子项以全新方式启动工作区

已测试产品提交：`b2c0490647963cb877d1f0c20394311fa245d6d4`。 基线：`5966c781ed014efc96c028a99bddd4ff78426741`。 后来的证据提交没有更改产品代码。 [结构化观测结果](issue-42-evidence.json)。

正常的父创建会初始化 Git，而无需提交。 在此补丁之前，默认子请求在两个新服务器上从 `git worktree add ... HEAD` 返回 500。 显式共享子项在相同的运行中取得了成功。 新的真实 HTTP 回归也因补丁之前的确切错误而失败。

该修复验证所选默认分支或 HEAD 在规划工作树之前解析为提交。 它在创建工作树时保留选定的引用，因此 Git 保留远程上游跟踪。 如果没有提交解决，它将使用现有的共享-工作区回退方案并报告 `isolation: shared`； 它不会创建任何提交、分支或工作树。 其他 Git 错误仍然会传播。 即使本地 HEAD 尚未诞生，可用的远程默认分支仍然会创建一个隔离的工作树。 显式共享隔离绕过了规划。 请求和工具描述解释了回退方案。

<a id="automated-regression-checks"></a>

## 自动回归检查

```sh
make build
export PATH=/workspace/.tools/tmux/usr/bin:$PATH
docker-init -s -- uv run pytest \
  tests/cross/test_remote_conversation_live_server.py::test_child_launch_in_fresh_workspace_preserves_unborn_repository \
  tests/agent_server/test_parent_child_conversations.py \
  tests/tools/child_conversation/test_start_child_conversation.py \
  tests/agent_server/test_conversation_service.py -k 'child or worktree' -q
```

结果：**41 通过**。 覆盖包括实际的HTTP启动父进程/子完成，未变的父文件/索引/未出生HEAD，已提交的仓库，子目录工作区，一个可用的远程默认，未出生的本地HEAD，明确的共享隔离、容量和工具序列化/调度。 文件范围的预提交检查通过。

<a id="real-server-and-model-verification"></a>

## 真实服务器及模型验证

[PR #43](https://github.com/enyst/agent-sdk/pull/43) 的维护 CLI 在创建产品提交后驱动了固定结账。 每次运行的 `run.json` 记录了上面的精确产物 SHA。 在 PATH 上运行 CLI：

```sh
docker-init -s -- control-agent-server map run --file F04 \
  --only F04.child-start,F04.child-unborn,F04.child-errors,F04.child-capacity \
  --checkout /workspace/agent-sdk-fix-42 --fresh --repeat 2 --record --keep-going
```

| 修订版 | 运行 | 默认子项 | 其他子控件 |
|---|---|---|---|
| 基线 | `20261023-060500-1c1a-map-f04` | HTTP 500 | 共享孩子成功 |
| 基线 | `20261023-060518-691c-map-f04` | HTTP 500 | 共享孩子成功 |
| 固定 | `20261023-071012-2856-map-f04` | HTTP 201，共享，完成 | 全部通过 |
| 固定 | `20261023-071101-a644-map-f04` | HTTP 201，共享，完成 | 全部通过 |

正如预期的那样，`F04.child-unborn` 的修复运行报告 **XPASS**，因为其维护的已知错误标记在本产品 PR 中有意保持不变。 因此进程退出代码为 1； 所有配方断言都会成功。 其他方案通过了，包括真实模型工作树/非 Git/共享启动以及文件系统副作用之前的全容量拒绝。

额外的新真实模型运行 (`20261023-071023-f9ef-fix42-default-child-tool`) 明确附加了 `start_child_conversation`。 父母在没有隔离争论的情况下调用了一次。 它的观测结果报告了一个成功的孩子`isolation: shared`； 该孩子完成并出现在父母的孩子列表中。 父存储库仍未诞生，其先前存在的文件在两次对话删除后仍然存在。

所有实时运行都使用隔离的本地 Linux 智能体服务器进程，`docker-init -s` 用于进程收获，Git 2.52.0 和 DeepSeek flash。 此更改使用现有的 Git 命令，并且不需要更新的 Git 功能。 真实模型检查覆盖本地服务器/工具路径； 他们没有声称进行基准测试评估或 Docker 运行时测试。

<a id="independent-review-and-superseded-first-version"></a>

## 独立审查并取代第一版

第一个产品版本 `46ba8bda118cdb35dd596f8f9f275a7fdfe7face` 通过了未出生的实时检查 (`20261023-065915-6ccd-map-f04`、`20261023-070005-f6ae-map-f04`) 和第一个工具检查 (`20261023-070042-9bc3-fix42-default-child-tool`)。 独立审查随后发现，使用解析的提交哈希来创建工作树会删除远程分支的上游跟踪。 那些早期的观测结果仍然在结构化证据中的 `earlier_revision` 下，并不是最终的证明。

在现有远程默认回归中添加的上游跟踪断言在第一次版本上失败了，因为“没有上游配置”。最终的修正验证了提交，但将原始选择的引用传递给了 Git。 该断言以及所有 41 项有针对性的测试现已通过。 独立的最终来源审查没有发现任何剩余的材料发现。 提交修正后，重复上面报告的两次 REST 运行和工具运行，得到最终产品 SHA。
