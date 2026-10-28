<a id="post-release-checklist"></a>

# 发布后清单

在发布 GitHub 版本并且 PyPI 软件包可用后，会发生几个自动和手动后续步骤。

<a id="automated-downstream-version-bump-prs"></a>

## 自动化：下游版本更新 PR

`pypi-release` 成功后，`version-bump-prs.yml` 工作流程自动运行。 它在两个存储库中创建 PR：

### OpenHands-CLI (`OpenHands/openhands-cli`)

- 分行：`bump-sdk-<version>`
- 通过 `uv add` 更新 `openhands-sdk` 和 `openhands-tools`
- 合并前验证 PR 通过 CLI 测试

```bash
gh pr list --repo OpenHands/openhands-cli \
  --search "bump-sdk-<version>" --json number,title,url
```

### OpenHands (`All-Hands-AI/OpenHands`)

- 分行：`bump-sdk-<version>`
- 更新`pyproject.toml`中的`openhands-sdk`、`openhands-tools`和`openhands-agent-server`
- 再生 `poetry.lock`
- 更新`sandbox_spec_service.py`中的`AGENT_SERVER_IMAGE`
- 验证 `enterprise/pyproject.toml` 没有显式 SDK 引脚

```bash
gh pr list --repo All-Hands-AI/OpenHands \
  --search "bump-sdk-<version>" --json number,title,url
```

<a id="manual-review-of-downstream-prs"></a>

## 下游人工审核 PR

两者 PR 都需要人工审核：

1. **检查每个下游 PR 上的 CI 个通道 **
2. **验证兼容性** - 特别是如果版本包含不兼容变更或需要采用的新功能
3. **满足后合并**

<a id="evaluation-on-openhands-index"></a>

## OpenHands指数评价

如果尚未完成预发布，请触发针对已发布版本的完整评估运行：

```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OpenHands/software-agent-sdk/actions/workflows/run-eval.yml/dispatches" \
  -d '{
    "ref": "main",
    "inputs": {
      "benchmark": "swebench",
      "sdk_ref": "v<version>",
      "eval_limit": "300",
      "reason": "Post-release eval v<version>"
    }
  }'
```

<a id="documentation-updates"></a>

## 文档更新

如果该版本包含面向用户的功能，请验证 `OpenHands/docs` 中的文档是否已更新（SDK 文档位于 `sdk/` 下）。 请参阅
`feature-release-rollout` 完整下游传播工作流程的技能。

<a id="troubleshooting"></a>

## 故障排除

<a id="pypi-publication-failed"></a>

### PyPI发布失败

手动重新运行 `pypi-release.yml` 工作流程。 它使用 `--check-url` 跳过已经发布的包，因此部分重新运行是安全的。

```bash
gh workflow run pypi-release.yml --repo OpenHands/software-agent-sdk
```

<a id="version-bump-pr-has-conflicts"></a>

### 版本升级 PR 有冲突

如果下游存储库自工作流程运行以来更改了依赖项引脚，则自动化 PR 可能会发生冲突。 手动解决凹凸分支上的冲突，或使用版本输入重新触发 `version-bump-prs.yml`。

```bash
gh workflow run version-bump-prs.yml \
  --repo OpenHands/software-agent-sdk \
  -f version=<version>
```

<a id="downstream-tests-fail-after-bump"></a>

### 下游测试在碰撞后失败

如果下游存储库的测试在版本升级 PR 上失败，请调查失败是否是 SDK 版本中的不兼容变更。 如果是这样的话，
要么：
- 修复凹凸分支上的下游代码，或者
- 发布包含修复程序的 SDK 补丁版本
