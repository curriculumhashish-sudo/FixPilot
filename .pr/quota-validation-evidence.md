<a id="structured-quota-validation-before-and-after"></a>

# 结构化配额验证：之前和之后

问题：[enyst/agent-SDK#40](https://github.com/enyst/agent-sdk/issues/40)。
测试产品提交：`06a52395b85039fa5b9c9d0ce18f7085a8b942ab`。 冻结失败提交：`5966c781ed014efc96c028a99bddd4ff78426741`。 以下提交仅添加此审阅者证据； 产品代码保留在经过测试的版本上。 机器可读的摘录位于
[quota-validation-evidence.json](quota-validation-evidence.json).

<a id="observed-behavior"></a>

## 观察到的行为

HTTP 429 提供商响应包含 `error.type` 和 `error.code` 等于
`insufficient_quota`，显示消息“您超出了当前配额，请检查您的计划和账单详细信息。”，之前通过的个人资料验证。 LiteLLM 替换了外部异常的结构化元数据，并仅保留了人类可读的消息。 原始的 OpenAI 异常仍然在其异常链中携带类型化元数据。

分类器现在遵循保留的原因/上下文链以获取确切的已知代码和类型。 它尊重受压抑的环境并防止循环。 现有的字符串兼容性仍然存在，而不添加消息猜测。 结构性预算拒绝还保留其现有的更强有力的政策：停止重试和模型回退方案。 提供商配额耗尽会跳过重试，但允许回退方案。

所有四次运行都在真实的 Agent Server 上调用 `POST /api/profiles/qa-quota/validate`，使用其未修改的 SDK/LiteLLM/OpenAI HTTP 传输层到环回错误提供程序。 每个都使用隔离状态和端口。

| 来源 | 新跑 | 配额裁决 | 普通429判决 | 地图结果 |
| --- | --- | --- | --- | --- |
| 冷冻基地 | `20261023-060605-a477-map-f20` | `valid: true, error: null` | `valid: true` | x失败 |
| 冷冻基地 | `20261023-060618-fd05-map-f20` | `valid: true, error: null` | `valid: true` | x失败 |
| 固定提交 | `20261023-070627-5271-map-f20` | `valid: false, error.type: LLMRateLimitError` | `valid: true` | 通行证 |
| 固定提交 | `20261023-070641-8fe2-map-f20` | `valid: false, error.type: LLMRateLimitError` | `valid: true` | 通行证 |

上述每个回复的 HTTP 状态为 200。 两次固定运行都通过了医生
`build_git_sha` 等于测试的产品提交。 两个配方脚本均退出 0，保持配置文件列表不变，并停止其服务器。 他们的端口被关闭了，服务器 PIDs 清理后缺席。 的 CLI 1 个 exit `xpass` 因为维护配方仍然将此标记为已知错误。 那个标记属于单独的维护 PR，不是这个产品的修复。

<a id="reproduce"></a>

## 再现

从验证工具的结帐运行
[maintenance PR #43](https://github.com/enyst/agent-sdk/pull/43), with this fix in
第二次结账并在那里完成 `make build`：

```sh
export PATH="$PWD/.agents/skills/verify-agent-server/scripts:$PATH"
docker-init -s -- control-agent-server map run \
  --file F20 --only F20.validate-quota-exhausted \
  --checkout /path/to/fix-checkout --fresh --repeat 2 --record --keep-going
```

承诺的配方包括瞬时正控制和上面的精确配额体。 其标准 F20 设置需要配置的 DeepSeek 密钥，但这些验证检查不会发出付费模型请求。 `tmux` 必须位于 PATH 上。 这里需要 subreaper 包装器，因为云主机的 PID 1 不会收获后代； 具有适当 init 的环境可能会忽略它。

<a id="regression-tests-and-review"></a>

## 回归测试和审查

新的真实 HTTP 重试回归在补丁之前失败：8 次失败，12 次跨同步/异步聊天和响应。 补丁后所有 20 个案例均通过。 案例使用结构化代码/类型，消息中没有机器代码； 瞬态控制故意使用相同的人类配额措辞。

更广泛的相关套件通过了 **272 项测试**：

```sh
uv run pytest tests/sdk/llm/test_budget_denial_http.py \
  tests/sdk/llm/test_exception_classifier.py \
  tests/sdk/llm/test_exception_mapping.py \
  tests/sdk/llm/test_llm_fallback.py \
  tests/agent_server/test_profiles_router.py -q
```

永久 HTTP 回退方案案例涵盖直接配额回退方案，回退方案模型自身的临时配额 429 重试，并且没有回退方案预算拒绝。 已传递每个文件预提交挂钩，包括 Ruff、Pyright 和 SDK 依赖关系规则。 该套件发出 31 条依赖/弃用警告； None失败了。 独立的智能体审查了代码和证据，并分别复制了主要配额→回退方案-瞬态-429→回退方案-成功路径。

这证明了通过真实的传输层确定性故障分类，而不是外部提供商的计费行为。 UI 或公共模式没有改变。 原始的私人国家和凭据被排除在已发表的摘录之外。
