<a id="upstream-quota-validation-migration-2026-10-24"></a>

# 上游配额验证迁移 (2026-10-24)

问题：[OpenHands/软件-智能体-SDK#6185](https://github.com/OpenHands/software-agent-sdk/issues/6185)。
原始报告：[enyst/agent-SDK#40](https://github.com/enyst/agent-sdk/issues/40)。 原始修复：[enyst/agent-SDK#47](https://github.com/enyst/agent-sdk/pull/47)。

最初的提交是用 `-x` 精心挑选的，保留了 Engel Nyst 的作者身份和 OpenHands 合著者预告片：

- `06a52395b85039fa5b9c9d0ce18f7085a8b942ab` ->
  `f3619d0d86aa655793e12115d2958668fcf244ce`（产品和 HTTP 回归测试）。
- `fd5d519e14c9f6bf8c0ad7177d80429fb3147d8b` ->
  `d919407e0afaf50d053978d08ea951d43db2b0d5`（原始证据）。

基地：上游`acd96e6fa424c02432304395b9208f99be24b54d`。
迁移后测试的产品：`d919407e0afaf50d053978d08ea951d43db2b0d5`。 此附加证据提交不会更改产品代码。

<a id="real-profile-endpoint"></a>

## 真实档案端点

[ 复制者 ](reproduce_profile_quota.py) 使用生产 `create_app()` 工厂和真正的环回 HTTP 提供者启动新的 Agent Server 进程。 它调用 `POST /api/profiles/qa-quota/validate` 到 HTTP。 SDK、LiteLLM 和 OpenAI 传输层未打补丁。 只有提供者的响应才是确定性的。 对于这两种情况，提供程序都会返回相同的人类可读的配额消息； 只是其结构`code`和`type`发生了变化。

| 提供商代码/类型 | 上游基地 | 迁移修复 |
| --- | --- | --- |
| `rate_limit_exceeded` | HTTP 200, `valid: true` | HTTP 200, `valid: true` |
| `insufficient_quota` | HTTP 200, `valid: true` | HTTP 200, `valid: false`, `LLMRateLimitError` |

两次运行都针对每个验证发出了一个提供程序请求，保持配置文件存储不变，停止服务器并关闭其侦听端口。 清理后的响应和依赖版本位于
[upstream-quota-validation.json](upstream-quota-validation.json).

从所需的产品结账中，在 `make build` 之后，运行相同的脚本：

```sh
.venv/bin/python /path/to/reproduce_profile_quota.py --output /tmp/quota-result.json
```

要重现基础，请使用此分支中的脚本并单独签出基础提交。 使用自己的虚拟环境从该结帐运行。 该脚本记录了签出的 HEAD 和已安装的软件包版本。

环境：macOS、Python 3.13.11、SDK/Agent Server 1.58.1、LiteLLM 1.93.0、
OpenAI 2.33.0. 每次运行都使用隔离的临时状态、伪造的密钥和仅环回服务器。 没有使用实时提供商计费帐户。

<a id="regression-checks"></a>

## 回归检查

新的 `test_http_structured_quota_skips_retries` 个案例针对未修改的上游产品代码运行，结果为 **8 个失败/12 个通过**。 这八个失败是同步/异步聊天中的结构化配额/预算错误。 响应和瞬态控制已经在底座上传递。

迁移的分支通过了 **280 次测试**：

```sh
uv run pytest tests/sdk/llm/test_budget_denial_http.py \
  tests/sdk/llm/test_exception_classifier.py \
  tests/sdk/llm/test_exception_mapping.py \
  tests/sdk/llm/test_llm_fallback.py \
  tests/agent_server/test_profiles_router.py -q
```

这些包括普通HTTP速率限制重试、回退方案的额度行为、回退方案的自身临时重试、明确的预算拒绝阻止回退方案、同步/异步聊天和响应，以及用户信息路由。 该运行发出了 32 个现有依赖项/弃用警告。

`make build` 和更改文件预提交检查已通过，包括 Ruff、Pyright 和依赖关系规则。 Source-PRCI被单独检查：其非测试检查通过，但`Run tests`作业在24小时后被取消。 这些旧支票未声明为本次迁移的验证。

<a id="duplicate-and-scope-review"></a>

## 重复和范围审查

当前的上游搜索（包括打开和关闭的） `insufficient_quota`, 容量标题，[profile] 验证，并未发现等效的公开问题 PR 在 #6185 之前。 #5100 已关闭，#5768 引入了用户配额验证但没有涵盖结构化的 HTTP 归一化差距。 关闭#4936/合并#4917 和合并#5309 建立此处保留的重试/回退策略。 第6030号升级 LiteLLM 为了 DecisionModel 支持； 它不会改变这个分类器。

此迁移不包含公共模式、持久化格式、依赖项或验证工具更改。
