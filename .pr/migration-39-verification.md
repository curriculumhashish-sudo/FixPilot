<a id="embedded-path-skill-source-migration-verification"></a>

# 嵌入式路径技能源迁移验证

已于 2026 年 10 月 24 日验证 [ 上游 #6184](https://github.com/OpenHands/software-agent-sdk/issues/6184)，从 [enyst/agent-SDK#39](https://github.com/enyst/agent-sdk/issues/39) 和 [ 源 PR #44](https://github.com/enyst/agent-sdk/pull/44) 迁移。

<a id="revision-provenance"></a>

## 修订来源

- 上游基地：`acd96e6fa424c02432304395b9208f99be24b54d`。
- 源产品提交：`31897798e8bd8e62ef56bdb86dba6588efbbc557`； 来源证据提交：`1973797e6a6d8ff7ecc9993cf990663d918c7aa1`。
- 迁移的产品提交：`3536c7e06`； 迁移的源证据提交和测试头：`a92344a54`。
- 两个源提交都干净地应用了 `git cherry-pick -x`。 原作者和合著者保持不变。
- 后续迁移证据文件不包含产品更改。 源分支问题，PR，和分支没有被修改。

<a id="current-upstream-reproduction"></a>

## 当前上游再现

macOS arm64 上的真实源运行 Agent Server、Python 3.13.11，通过 HTTP 处理请求并克隆公共 GitHub 存储库。 每次运行都使用自己的临时持久化、对话、工作区、bash-event 目录、进程和未使用的环回端口； 随后停止了拥有的服务器进程。 不需要模型调用。

两种源表单都固定了相同的公共扩展提交，`26047067ecd0230d6ce4e15016cbdf786798cba5`。 确切的POST机构是：

```json
{"source":"github:OpenHands/extensions","repo_path":"skills/github","ref":"26047067ecd0230d6ce4e15016cbdf786798cba5"}
{"source":"github:OpenHands/extensions/skills/github","ref":"26047067ecd0230d6ce4e15016cbdf786798cba5"}
```

流程 POSTs `/api/skills/install`。 成功响应后，接着是GET，然后是DELETE，再接着是`/api/skills/installed/github`，然后再尝试下一个源。

| 修订版 | 新跑 | 显式路径控制 | 嵌入路径 |
| --- | --- | --- | --- |
| 上游基地 | 1 | 200, `github` | 422、无效技能 |
| 上游基地 | 2 | 200, `github` | 422、无效技能 |
| 头部迁移 | 1 | 200, `github` | 200, `github` |
| 头部迁移 | 2 | 200, `github` | 200, `github` |

所有成功的安装还返回 200 以供读回和卸载。 [经过净化的请求/响应证据](migration-39-live-evidence.json)将每个交换与其测试的修订版、源表单和已解决的扩展提交联系起来。

使用 `make build` 进行复制，然后从 `OH_PERSISTENCE_DIR`、`OH_CONVERSATIONS_PATH`、`OH_WORKSPACE_PATH` 和 `OH_BASH_EVENTS_DIR` 开始 `uv run python -m openhands.agent_server --host 127.0.0.1 --port <unused-port>`，指向新的临时目录。 设置`OH_TELEMETRY_CONSENT=false`。 将上面的 JSON 主体发送到安装端点，读取并删除它们之间的成功安装。 在底座和头部重复新的进程和目录。

原始来源 PR 的单独 `fix-39-*` 工件记录了 Linux/Python 3.13.5 证据。 此迁移独立地执行 macOS 上的相同公共入口。 两者都没有运行声明打包的二进制文件或 Docker-图像验证。 没有打包、依赖、外部可执行要求、公共请求形式或已持久化模式更改。

<a id="focused-verification-on-migrated-head"></a>

## 重点验证迁移的头部

`make build` 已完成，使用隔离的工作树虚拟环境。

```sh
uv run pytest tests/sdk/extensions tests/sdk/skills/test_installed_skills.py \
  tests/sdk/plugin/test_installed_plugins.py -m 'not network' -q
# 204通过，取消选择3个网络测试

uv run pytest tests/agent_server/test_skills_router.py \
  tests/agent_server/test_skills_service.py -q
# 98 通过

uv run pre-commit run --files \
  openhands-sdk/openhands/sdk/extensions/fetch.py \
  openhands-sdk/openhands/sdk/extensions/installation/manager.py \
  tests/sdk/skills/test_installed_skills.py
# 所有适用的钩子均已通过，包括 Pyright
```

已安装的技能回归表示嵌入路径（包括尾随斜杠）的实现实时克隆/更新行为，显式路径和仓库根目录的行为。 它通过更新保留名称、原始源元数据和禁用状态。 现有扩展/插件覆盖范围检查冲突路径、包含、本地路径、无清单存储库名称和旧更新名称。 上面的真实 GitHub HTTP 工作流程对网络标记测试进行了补充。

<a id="duplicate-and-predecessor-review"></a>

## 重复审核和前任审核

开放和封闭的上游搜索覆盖了`subpath`、`embedded-path`、`repo_path`、`Invalid skill`、仓库根命名、引入的解析器名称和源问题/PRURLs。 在打开#6184之前，没有找到与此预取422 回归相关的竞争报告或补丁。

- #5895 / #5909 修复了早期的 400 解析器故障。第5909章合并为`98c97e6f18cecdaec96c011efb00f43db5b63bcc`。
- #5896和#5905修正了实际远程仓库根目录的实际名称。#5905合并后作为`7bb4be18ca42bf0e44748183baa6a56eb329621a`，并引入了命名路径，该路径错误地将选择的技能目录分类。
- #6008 / #6009 关注的是无形市场发现，而不是嵌入式技能源的安装。

来源 PR #44 没有提交评论或内嵌评论。 其发布的注释包括跳过草稿审查、临时工件通知和成功的 REST 兼容性结果。 源检查不能替代此迁移的检查； 上游CI仍然需要在已发布的头上运行。
