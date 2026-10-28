<a id="embedded-path-skill-installation-verification"></a>

# 嵌入路径技能安装：验证

修复了 [enyst/agent-SDK#39](https://github.com/enyst/agent-sdk/issues/39)。

抓取器已从以下位置选择了 `skills/github`
`github:OpenHands/extensions/skills/github`. 安装加载程序看到原始的`repo_path=None`，将所选目录分类为存储库根目录，并以名称`extensions`加载它。 严格验证然后拒绝了该技能的声明名称`github`。

该补丁在获取和加载之间共享现有的源/子路径解析。 它保留了公共解析器的两个值返回，原始已持久化源和`repo_path`，明确的路径冲突/包含检查，以及上游#5905引入的仓库根命名行为。 更新使用相同的路径分辨率。 无需更改 REST 或 TypeScript 合同。

<a id="revisions-and-live-evidence"></a>

## 修订和现场证据

- 之前：`5966c781ed014efc96c028a99bddd4ff78426741`（冻叉主）。
- 之后：`31897798e8bd8e62ef56bdb86dba6588efbbc557`（提交的产品和测试）。
- 线束：维护PR[#43](https://github.com/enyst/agent-sdk/pull/43)，
  `fe5ee276`，使用维护的 CLI 和配方 `--checkout` 选择此修复程序自己的虚拟环境和源代码树。
- 运行时：Linux，Python 3.13.5，源运行智能体服务器/SDK 1.55.1。 请求使用实际经过身份验证的 HTTP 安装端点并克隆公共 GitHub 存储库。 这与问题的源服务器再现相匹配； 没有声明打包的二进制或 Docker-图像行为。

| 运行ID | 修订版 | 显式 `repo_path` 控制 | 嵌入路径 |
| --- | --- | --- | --- |
| `20261023-054655-a752-map-f25` | 之前 | 200, `github` | 422、无效技能 |
| `20261023-054705-bb2c-map-f25` | 之前 | 200, `github` | 422、无效技能 |
| `20261023-065443-4190-map-f25` | 之后 | 200, `github` | 200, `github` |
| `20261023-065459-fd2d-map-f25` | 之后 | 200, `github` | 200, `github` |

[Safe request/response extracts](fix-39-live-evidence.json) include run revisions,
时间戳、请求正文和响应状态/名称/源/路径/提交字段。 两种形式都安装了相同的远程存储库提交。 两次固定运行均完成了正常范围的服务器关闭。

复制命令，从修复结帐运行：

```sh
export PATH=/workspace/.tools/tmux/usr/bin:/workspace/agent-sdk-verify/.agents/skills/verify-agent-server/scripts:$PATH
docker-init -s -- /workspace/agent-sdk-verify/.agents/skills/verify-agent-server/scripts/control-agent-server \
  map run --file F25 --only F25.install-documented-sources \
  --fresh --repeat 2 --record --keep-going \
  --checkout /workspace/agent-sdk-fix-39
```

每个固定运行报告两次通过（前提条件和显式路径控制）、一次XPASS、零失败和零阻塞。 预计会出现 Exit 1，因为维护配方仍将 #39 标记为已知错误。 它的 200/name 断言现在成功了。 该产品 PR 不会编辑该配方。

<a id="regression-checks"></a>

## 回归检查

新的参数化测试使用真正的 git 克隆和更新，以及进程本地
git URL rewrite redirecting the GitHub-shaped source to a temporary repository.
它练习实际的解析器、获取器、安装器、严格技能加载器和元数据。 嵌入式路径（包括尾部斜杠）、显式路径和存储库根技能在安装和更新时保留其名称； 更新保留禁用状态并刷新内容和已解决的提交。

在产品补丁之前，新矩阵产生了一次失败和两次通过。 嵌入路径的失败为 `SkillValidationError: Invalid skill name 'sample-skill': Name 'sample-skill' does not match directory 'extensions'`。

产品补丁后：

```sh
uv run pytest tests/sdk/extensions tests/sdk/skills/test_installed_skills.py \
  tests/sdk/plugin/test_installed_plugins.py -m 'not network' -q
# 156 项通过，3 项网络测试取消

uv run pytest tests/agent_server/test_skills_router.py \
  tests/agent_server/test_skills_service.py -q
# 93 通过
```

156-测试套件包括现有本地源、显式子路径、解析器、包含、冲突和无实-git 表明的插件根/遗留更新名称覆盖。 上面的实时运行涵盖了外部网络行为。 所有更改的 Python 文件都通过存储库预提交检查，包括 Ruff、pycodestyle、Pyright 和导入/注册规则。 `git diff --check` 通过。

没有引入依赖项、模式、包版本或源格式更改。
