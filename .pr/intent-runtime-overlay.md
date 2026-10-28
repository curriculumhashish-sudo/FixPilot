<a id="pr-runtime-reconciliation"></a>

# PR 运行时协调

由 [verification-aggregation.json](verification-aggregation.json)、快照 **2026-10-23T06:44:47+00:00** 生成。 TARGET `5966c781ed014efc96c028a99bddd4ff78426741`. 来源意图和引文保留在 [intent-ledger.md](intent-ledger.md) 中。

该叠加报告观察到的功能/系列覆盖范围，独立于记录的 PR 意图。 家庭扫描并不是声称 PR 的每一行或每个特定于提供商的接受方案都已执行。 当 PR 正文或其地图差异命名当前 ID 时，会给出精确的要素链接。 已知缺陷 `xfail`，新失败，能力块，以及未运行的行仍保持独立。 完整的测试/CI/仅文档 PR 不需要产品运行时证明； 其相关的工具检查保留在主要维护报告中。

<a id="family-evidence-snapshot"></a>

## 家庭证据快照

| 家庭 | 独特的结果 | 未解析/阻止的 ID | 证据 |
|---|---|---|---|
| F01 | 11 次通过 | None | [20261023-060800-e534-map-f01](/tmp/agent-server-verify/20261023-060800-e534-map-f01/evidence/ledger.jsonl) |
| F02 | 1 次失败，20 次通过 | None | [20261023-060932-7371-map-f02](/tmp/agent-server-verify/20261023-060932-7371-map-f02/evidence/ledger.jsonl) |
| F03 | 1 次失败，23 次通过，1 次退役 | None | [20261023-061146-6e37-map-f03](/tmp/agent-server-verify/20261023-061146-6e37-map-f03/evidence/ledger.jsonl) |
| F04 | 6 次失败，30 次通过 | None | [20261023-061752-58d6-map-f04](/tmp/agent-server-verify/20261023-061752-58d6-map-f04/evidence/ledger.jsonl) |
| F05 | 3 次失败，28 次通过 | None | [20261023-055151-baf9-map-f05](/tmp/agent-server-verify/20261023-055151-baf9-map-f05/evidence/ledger.jsonl) |
| F06 | 4 次失败，25 次通过 | None | [20261023-061525-4a2c-map-f06](/tmp/agent-server-verify/20261023-061525-4a2c-map-f06/evidence/ledger.jsonl) |
| F07 | 2 次失败，22 次通过 | None | [20261023-055653-2ecf-map-f07](/tmp/agent-server-verify/20261023-055653-2ecf-map-f07/evidence/ledger.jsonl) |
| F08 | 3 次失败，20 次通过 | None | [20261023-055915-1e04-map-f08](/tmp/agent-server-verify/20261023-055915-1e04-map-f08/evidence/ledger.jsonl) |
| F09 | 6 次失败，22 次通过 | None | [20261023-054458-ad93-map-f09](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/ledger.jsonl) |
| F10 | 3 次失败，22 次通过 | None | [20261023-055430-a925-map-f10](/tmp/agent-server-verify/20261023-055430-a925-map-f10/evidence/ledger.jsonl) |
| F11 | 1 次失败，24 次通过 | None | [20261023-055204-9e08-map-f11](/tmp/agent-server-verify/20261023-055204-9e08-map-f11/evidence/ledger.jsonl) |
| F12 | 3 次失败，28 次通过 | None | [20261023-055352-57dd-map-f12](/tmp/agent-server-verify/20261023-055352-57dd-map-f12/evidence/ledger.jsonl)<br>[20261023-055653-2b9f-map-f12](/tmp/agent-server-verify/20261023-055653-2b9f-map-f12/evidence/ledger.jsonl)<br>[20261023-060157-5014-map-f12](/tmp/agent-server-verify/20261023-060157-5014-map-f12/evidence/ledger.jsonl) |
| F13 | 1 次失败，28 次通过 | None | [20261023-055709-f582-map-f13](/tmp/agent-server-verify/20261023-055709-f582-map-f13/evidence/ledger.jsonl) |
| F14 | 3 次失败，27 次通过 | None | [20261023-060158-d027-map-f14](/tmp/agent-server-verify/20261023-060158-d027-map-f14/evidence/ledger.jsonl) |
| F15 | 2 次失败，27 次通过 | None | [20261023-061154-549e-map-f15](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/ledger.jsonl) |
| F16 | 1 次失败，25 次通过 | None | [20261023-060537-5300-map-f16](/tmp/agent-server-verify/20261023-060537-5300-map-f16/evidence/ledger.jsonl)<br>[20261023-064306-4a02-map-f16](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/ledger.jsonl) |
| F17 | 24 次通过 | None | [20261023-063824-a607-map-f17](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/ledger.jsonl) |
| F18 | 2 次失败，27 次通过 | None | [20261023-061046-f731-map-f18](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/ledger.jsonl) |
| F19 | 2 次失败，26 次通过 | None | [20261023-055055-6ce6-map-f19](/tmp/agent-server-verify/20261023-055055-6ce6-map-f19/evidence/ledger.jsonl) |
| F20 | 4 次失败，32 次通过 | None | [20261023-060632-6ceb-map-f20](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/ledger.jsonl) |
| F21 | 3 次失败，29 次通过 | None | [20261023-060558-2261-map-f21](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/ledger.jsonl) |
| F22 | 4 次失败，20 次通过 | None | [20261023-060112-78e9-map-f22](/tmp/agent-server-verify/20261023-060112-78e9-map-f22/evidence/ledger.jsonl) |
| F23 | 4 次失败，24 次通过 | None | [20261023-061004-ea5c-map-f23](/tmp/agent-server-verify/20261023-061004-ea5c-map-f23/evidence/ledger.jsonl) |
| F24 | 1 次阻塞，1 次失败，18 次通过 | `F24.login-complete`（已屏蔽） | [20261023-060713-ed65-map-f24](/tmp/agent-server-verify/20261023-060713-ed65-map-f24/evidence/ledger.jsonl) |
| F25 | 4 次失败，29 次通过 | None | [20261023-054453-5aac-map-f25](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/ledger.jsonl)<br>[20261023-055138-9b5d-map-f25](/tmp/agent-server-verify/20261023-055138-9b5d-map-f25/evidence/ledger.jsonl) |
| F26 | 2 次失败，24 次通过 | None | [20261023-055315-8b20-map-f26](/tmp/agent-server-verify/20261023-055315-8b20-map-f26/evidence/ledger.jsonl) |
| F27 | 2 次失败，30 次通过 | None | [20261023-055052-0e46-map-f27](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/ledger.jsonl)<br>[20261023-055752-9ae1-map-f27](/tmp/agent-server-verify/20261023-055752-9ae1-map-f27/evidence/ledger.jsonl)<br>[20261023-060835-c2ed-map-f27](/tmp/agent-server-verify/20261023-060835-c2ed-map-f27/evidence/ledger.jsonl)<br>[20261023-061445-0497-map-f27](/tmp/agent-server-verify/20261023-061445-0497-map-f27/evidence/ledger.jsonl) |
| F28 | 1 次失败，28 次通过 | None | [20261023-060041-3d2e-map-f28](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/ledger.jsonl) |
| F29 | 1 次失败，28 次通过 | None | [20261023-055936-8c9d-map-f29](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/ledger.jsonl) |
| F30 | 2 次失败，25 次通过 | None | [20261023-060925-fa0c-map-f30](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/ledger.jsonl)<br>[20261023-061918-74d1-map-f30](/tmp/agent-server-verify/20261023-061918-74d1-map-f30/evidence/ledger.jsonl) |
| F31 | 1 次失败，22 次通过 | None | [20261023-061337-162c-map-f31](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/ledger.jsonl)<br>[20261023-062141-3a28-map-f31](/tmp/agent-server-verify/20261023-062141-3a28-map-f31/evidence/ledger.jsonl)<br>[20261023-062258-668e-f31-保留](/tmp/agent-server-verify/20261023-062258-668e-f31-retention/evidence/ledger.jsonl) |
| F32 | 3 次失败，27 次通过 | None | [20261023-062016-25a6-map-f32](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/ledger.jsonl) |
| F33 | 3 次失败，40 次通过 | None | [20261023-061805-30c4-map-f33](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/ledger.jsonl)<br>[20261023-063025-d802-map-f33](/tmp/agent-server-verify/20261023-063025-d802-map-f33/evidence/ledger.jsonl) |
| F34 | 3 次失败，29 次通过 | None | [20261023-062459-17e2-map-f34](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/ledger.jsonl)<br>[20261023-063341-667a-map-f34](/tmp/agent-server-verify/20261023-063341-667a-map-f34/evidence/ledger.jsonl)<br>[20261023-063813-3072-map-f34](/tmp/agent-server-verify/20261023-063813-3072-map-f34/evidence/ledger.jsonl) |

<a id="new-issue-context"></a>

## 新问题上下文

为了可见性，这些问题在下面按家庭相关联，而不是归因于每个接触该家庭的 PR。

- [enyst/agent-SDK#39](https://github.com/enyst/agent-sdk/issues/39)：[Bug]：存储库根重命名后，嵌入式路径技能源回归到 422。
- [enyst/agent-SDK#40](https://github.com/enyst/agent-sdk/issues/40)：[Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证。
- [enyst/agent-SDK#41](https://github.com/enyst/agent-sdk/issues/41): [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段。
- [enyst/agent-SDK#42](https://github.com/enyst/agent-sdk/issues/42)：[Bug]：默认子启动在新初始化的工作区中失败。

<a id="per-pr-runtime-overlay"></a>

## 每PR运行时覆盖

<a id="pr-5467"></a>
### PR #5467

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5467); 提交`608a102c637d8d8a999f49d7b04846524bd8bd1c`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5548"></a>
### PR #5548

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5548); 提交`91ac058a08fd6365286fc8c5628f35a5f41ff300`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5538"></a>
### PR #5538

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5538); 提交`69e26889401fe69157fff536e6a69049e6644cb3`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F14（3 次失败，27 次通过）； F18（2次失败，27次通过）； F20（4次失败，32次通过）； F21（3 次失败，29 次通过）； F22（4次失败，20次通过）； F31（1 次失败，22 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5547"></a>
### PR #5547

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5547); 提交`0bb7b525c75f4a9a0606844fc4a2579106b08d32`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F10（3 次失败，22 次通过）； F12（3次失败，28次通过）； F15（2 次失败，27 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5342"></a>
### PR #5342

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5342); 提交`97190b800444aaf090eee29e336a63d80146c7ae`。
- 映射系列证据：F13（1 x 失败，28 通过）； F27（2次失败，30次通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5460"></a>
### PR #5460

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5460); 提交`9f47d471ee6f91ba1d140d10d34f3b26d5ac2427`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5582"></a>
### PR #5582

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5582); 提交`5c6e2589656aeeacedf6a0bd79a725688bb9e872`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：Docker 生命周期车道使用了已发布的1.55.1最小子代，其不可变的图像身份记录。 这不符合新的 TARGET 生产映像构建的条件。 VSCode 运行中的行仍被阻塞。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5341"></a>
### PR #5341

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5341); 提交`c980344bc78e21d5625ec4e987680d87c6c56f7f`。
- 映射系列证据：F28（1 个失败，28 个通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-4784"></a>
### PR #4784

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4784); 提交`16662b0bd2c1a93d3c5e282b48da05b95e90a0c8`。
- 映射家庭证据：F14（3 x 失败，27 个通过）； F27（2次失败，30次通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5559"></a>
### PR #5559

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5559); 提交`2804c1273b4093e632e332a7a572894782c7b1e1`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F05（3 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-4952"></a>
### PR #4952

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4952); 提交`9c4fd8c6664dfce98524d04d965b4f009f390fbe`。
- 映射系列证据：F20（4 次失败，32 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5619"></a>
### PR #5619

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5619); 提交`d1bfda28da7f5c4d3b33d65e729161cef6e0a4ec`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5616"></a>
### PR #5616

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5616); 提交`33044182505244749928644a4643368a9e998ee7`。
- 映射家庭证据：F01（11 次）； F12（3次失败，28次通过）； F16（1 次失败，25 次通过）； F31（1 次失败，22 次通过）。
- 限制：Docker 生命周期车道使用了已发布的1.55.1最小子代，其不可变的图像身份记录。 这不符合新的 TARGET 生产映像构建的条件。 VSCode 运行中的行仍被阻塞。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5673"></a>
### PR #5673

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5673); 提交`cd17bd89d52ef209abbfca5870631d0474ca8f66`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5182"></a>
### PR #5182

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5182); 提交`9e76fe72b43f7be65b48a243486c2e30b5104a22`。
- 映射家庭证据：F06（4 x 失败，25 通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F32（3 次失败，27 次通过）； F33（3次失败，40次通过）； F34（3 次失败，29 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5683"></a>
### PR #5683

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5683); 提交`dd1af943cb491e21c4b0f83f513ccf602c43f2dd`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5670"></a>
### PR #5670

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5670); 提交`bfc1ae71b0e0bb9433a7bd3b7f07a498271a14b6`。
- 映射家庭证据：F14（3 x 失败，27 个通过）； F27（2次失败，30次通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5579"></a>
### PR #5579

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5579); 提交`6d51e7262fc234586ff5e8e519ce5a658d334cdf`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3次失败，28次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F12（3 次失败，28 次通过）； F18（2 次失败，27 次通过）； F19（2次失败，26次通过）； F20（4次失败，32次通过）； F21（3 次失败，29 次通过）； F22（4次失败，20次通过）； F23（4 次失败，24 次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5671"></a>
### PR #5671

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5671); 提交`e8ad54729e43ca767911e28f8e350a3c3eb84c78`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5609"></a>
### PR #5609

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5609); 提交`1d471742ea7be017d013eaaa3080f5d28d5490cb`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5682"></a>
### PR #5682

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5682); 提交`c1c8c1c27824b7566861ea0f8e6900e4ae2944a9`。
- 映射家庭证据：F18（2 x 失败，27 通过）； F19（2次失败，26次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5614"></a>
### PR #5614

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5614); 提交`9929c14e7d2f4882cd257de2a401235ef276b865`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5675"></a>
### PR #5675

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5675); 提交`1cfba2117e92730b0fe1c32520a39aad8611bb8c`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。
- 限制：关联的提交与其第一个父级具有相同的树； 相关的 PR 描述了集成测试工作，但此提交未添加任何更改的路径。

<a id="pr-5291"></a>
### PR #5291

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5291); 提交`e2bac66be26e94f571f27b71f507e7192720f825`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5661"></a>
### PR #5661

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5661); 提交`c4b93299cf2b31c8b5d0b2c5a89965ccc5ff24f9`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F05（3 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5703"></a>
### PR #5703

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5703); 提交`c96875fe3d033efc44b5e6403043251626dd61ef`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5700"></a>
### PR #5700

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5700); 提交`f824a949af7f8045cc6691d7945ce7b31bfe9606`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F05（3 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-4838"></a>
### PR #4838

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4838); 提交`4cc058275c5a08d845bd846576aafc80e5dd7d0d`。
- 映射系列证据：F19（2 x 失败，26 个通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5436"></a>
### PR #5436

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5436); 提交`3934349da2db0433238621542173a00a8af7439c`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5715"></a>
### PR #5715

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5715); 提交`3dcb27b227aa177f6a7eadb0eb144339245cbbc4`。
- 映射系列证据：F13（1 x 失败，28 通过）； F27（2次失败，30次通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5689"></a>
### PR #5689

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5689); 提交`c0471362d340ade1e334595ba98417108b415e88`。
- 映射系列证据：F28（1 个失败，28 个通过）。
- PR/地图中命名的功能 ID 更改：[`F28.status-exit-hang`](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/map-run/F28-canvas-extensions-28-status-after-the-leader-exits-f28-status.json)：**pass**。

<a id="pr-5587"></a>
### PR #5587

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5587); 提交`3385a486997edec21c1a2b859344f57a74dea84b`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5659"></a>
### PR #5659

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5659); 提交`e696f72c260b959d1b36d570a6688e99977ec28a`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F13（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5657"></a>
### PR #5657

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5657); 提交`e3a26821f8f7c85e98078c7b5e1a80647fc7d0c7`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F19（2次失败，26次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5621"></a>
### PR #5621

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5621); 提交`acca181af1f353975965bcf6486e1d0a58f444c0`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5724"></a>
### PR #5724

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5724); 提交`d97eb76f60829a4250dd313f5a9d4d03e2951de8`。
- 映射系列证据：F08（3 次失败，20 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5660"></a>
### PR #5660

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5660); 提交`7bd668c9ab74f62c85745cd95adb503f53e7228b`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F29（1 次失败，28 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5520"></a>
### PR #5520

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5520); 提交`c1dfd9c52cd3a1d87589b5054c8181d041d88859`。
- 映射家庭证据：F27（2 x 失败，30 通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5744"></a>
### PR #5744

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5744); 提交`d6165a51cb158c0fd80eeb6ffac9cee2b4ce73e5`。
- 映射系列证据：F21（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略了 public_skills 字段。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5409"></a>
### PR #5409

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5409); 提交`4011cb5d4fd508964fe210df9a50af7d2f19d29d`。
- 映射家庭证据：F01（11 次）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F10（3次失败，22次通过）； F12（3次失败，28次通过）； F16（1 次失败，25 次通过）； F18（2 次失败，27 次通过）； F19（2次失败，26次通过）； F20（4次失败，32次通过）； F21（3 次失败，29 次通过）； F22（4次失败，20次通过）； F27（2次失败，30次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-4960"></a>
### PR #4960

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4960); 提交`27308a4b3f23a40177c9f444f9e35136c8a0d3fb`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F21（3 次失败，29 次通过）； F30（2 次失败，25 次通过）； F33（3次失败，40次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现： [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5727"></a>
### PR #5727

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5727); 提交`733f06edac353d595f0dadac476ee5011b53586f`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5728"></a>
### PR #5728

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5728); 提交`dfd8fe8fb39e6f6d73ba35ce524cac83d94e0d96`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5754"></a>
### PR #5754

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5754); 提交`a430c778bd8a720234ce4674014ac292a0326670`。
- 映射系列证据：F27（2 个失败，30 个通过）。
- PR/地图中命名的功能 ID 更改：[`F27.subagents-bad-skill`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-15-agent-with-a-missing-skill-f27-subagents.json)：**pass**。

<a id="pr-5759"></a>
### PR #5759

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5759); 提交`6a298a48fcdb06c3bf5835d648a7d8b4d3d31cf5`。
- 映射系列证据：F28（1 个失败，28 个通过）。
- PR/地图中命名的功能 ID 更改：[`F28.status-probe-latch`](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/map-run/F28-canvas-extensions-27-health-probe-latch-f28-status-probe-latc.json)：**pass**。

<a id="pr-4814"></a>
### PR #4814

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4814); 提交`6e7a8532ef4426da08b5c06dd57cf4795303be01`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F12（3次失败，28次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5478"></a>
### PR #5478

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5478); 提交`c3ecd82c7807a80796d95a6fdb83b7865d04413d`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-4926"></a>
### PR #4926

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/4926); 提交`7f7f0520920007b2c135e7bd0ef06e637032860b`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F09（6 次失败，22 次通过）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4次失败，32次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5981"></a>
### PR #5981

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5981); 提交`d332f8156f12014df1b3522ab01c2508eabf6e8b`。
- 映射家庭证据：F01（11 次）； F04（6 次失败，30 次通过）； F21（3 次失败，29 次通过）； F25（4 次失败，29 次通过）； F27（2次失败，30次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5747"></a>
### PR #5747

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5747); 提交`0bd5cc2d322d61f785816a29ef1f2e4c86db2460`。
- 映射族证据：F05（3 x 失败，28 个通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F21（3 次失败，29 次通过）； F27（2次失败，30次通过）； F33（3 次失败，40 次通过）。
- 映射系列中的新发现：[enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略了 public_skills 字段。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5926"></a>
### PR #5926

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5926); 提交`4bb57df68465868c2ec13388acd6a6b1e14af651`。
- 映射家庭证据：F23（4 x 失败，24 个通过）； F24（1 次阻塞，1 次 xfail，18 次通过）。
- PR/地图更改中指定的功能 ID：[`F24.device-start-offline`](/tmp/agent-server-verify/20261023-060713-ed65-map-f24/evidence/map-run/F24-openai-subscription-19-start-and-poll-a-login-offline-f24-devic.json): **xfail**； [`F24.status-offline`](/tmp/agent-server-verify/20261023-060713-ed65-map-f24/evidence/map-run/F24-openai-subscription-18-status-with-an-expired-login-offline-f24.json)：**通过**； [`F24.status-refresh-rejected`](/tmp/agent-server-verify/20261023-060713-ed65-map-f24/evidence/map-run/F24-openai-subscription-07-rejected-refresh-f24-status-refresh-reje.json)：**通过**。

<a id="pr-5923"></a>
### PR #5923

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5923); 提交`1a0fd91ad03d6a9f51ea38aa53fb60b848b56d20`。
- 映射系列证据：F29（1 个失败，28 个通过）。
- PR/地图更改中命名的功能 ID：[`F29.proxy-root`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-12-app-root-f29-proxy-root.json): **pass**； [`F29.proxy-root-path-query`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-13-root-path-parameter-f29-proxy-root-path-.json)：**通过**； [`F29.ws-bridge`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-19-websocket-bridge-f29-ws-bridge.json)：**通过**。

<a id="pr-5920"></a>
### PR #5920

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5920); 提交`1c34a84ccea3aa3f7bdc44ba7a19a88f872fcf08`。
- 映射系列证据：F28（1 x 失败，28 通过）； F29（1 次失败，28 次通过）。
- PR/地图更改中命名的功能 ID：[`F29.backend-crash-detected`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-24-crash-seen-by-the-bridge-f29-backend-cra.json): **pass**； [`F29.backend-lifecycle-revokes`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-23-backend-stop-and-disable-revoke-f29-back.json)：**通过**。

<a id="pr-5944"></a>
### PR #5944

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5944); 提交`2ec5b9ed4a675e01f0d33192be57a4f9834cfd2b`。
- 映射家庭证据：F15（2 x 失败，27 通过）； F25（4 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F25.sync-offline`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-24-sync-without-a-reachable-origin-f25-sync.json)：**pass**。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。

<a id="pr-5725"></a>
### PR #5725

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5725); 提交`9c0b99ec00775d454d19b9567cf1e1bd61e85a75`。
- 映射家庭证据：F01（11 次）； F12（3次失败，28次通过）； F16（1 次失败，25 次通过）； F31（1 次失败，22 次通过）。
- 限制：Docker 生命周期车道使用了已发布的1.55.1最小子代，其不可变的图像身份记录。 这不符合新的 TARGET 生产映像构建的条件。 VSCode 运行中的行仍被阻塞。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5986"></a>
### PR #5986

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5986); 提交`95cb37b7f04ff281e92bfb3c3fc66573db2df38a`。
- 映射家庭证据：F14（3 x 失败，27 个通过）； F15（2 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5929"></a>
### PR #5929

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5929); 提交`4dc42d3a2b65c4f674ad0fc149477a583a9c4419`。
- 映射系列证据：F02（1 x 失败，20 通过）； F27（2 次失败，30 次通过）。
- PR/地图更改中命名的功能 ID：[`F29.session-forwarded-proto`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-06-forwarded-proto-f29-session-forwarded-pr.json): **pass**； [`F29.trusted-forwarded-headers`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-26-trusted-forwarded-headers-f29-trusted-fo.json)：**通过**。

<a id="pr-5909"></a>
### PR #5909

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5909); 提交`98c97e6f18cecdaec96c011efb00f43db5b63bcc`。
- 映射家庭证据：F25（4 x 失败，29 通过）； F26（2次失败，24次通过）； F28（1 次失败，28 次通过）。
- PR/地图更改中指定的功能 ID：[`F25.install-documented-sources`](/tmp/agent-server-verify/20261023-055138-9b5d-map-f25/evidence/map-run/F25-skills-02-documented-install-sources-f25-install-d.json): **xfail**； [`F25.install-github`](/tmp/agent-server-verify/20261023-055138-9b5d-map-f25/evidence/map-run/F25-skills-01-install-from-github-f25-install-github.json)：**通过**； [`F25.marketplace-public`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-03-public-marketplace-catalog-f25-marketpla.json)：**x失败**； [`F26.install-documented-source`](/tmp/agent-server-verify/20261023-055315-8b20-map-f26/evidence/map-run/F26-plugins-12-documented-install-source-f26-install-do.json)：**通过**； [`F26.install-errors`](/tmp/agent-server-verify/20261023-055315-8b20-map-f26/evidence/map-run/F26-plugins-10-install-errors-f26-install-errors.json)：**通过**。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。

<a id="pr-5945"></a>
### PR #5945

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5945); 提交`d60b176ce32b45daec8127f134aa715f911d9637`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F05（3 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F31.tmux-dir-cleanup`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-22-per-process-tmux-directory-removed-on-st.json)：**pass**。

<a id="pr-5918"></a>
### PR #5918

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5918); 提交`1045bdffdb8dfc30f575645c7d2dfccf61f8e644`。
- 映射族证据：F12（3 x 失败，28 个通过）； F29（1 次失败，28 次通过）。
- PR/地图更改中命名的功能 ID：[`F29.proxy-credentials-stripped`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-14-credentials-stripped-f29-proxy-credentia.json): **pass**； [`F29.proxy-request-framing`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-15-request-framing-f29-proxy-request-framin.json)：**通过**。

<a id="pr-5907"></a>
### PR #5907

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5907); 提交`4e32a3adb05250477e936481acc77b403c48cba7`。
- 映射系列证据：F16（1 次失败，25 次通过）。
- PR/地图更改中命名的功能 ID：[`F16.vscode-enabled-status`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-01-enabled-but-not-running-f16-vscode-enabl.json): **pass**； [`F16.vscode-folder-encoding`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-03-folder-with-and-f16-vscode-folder-encodi.json)：**通过**； [`F16.vscode-running`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-04-vs-code-actually-running-f16-vscode-runn.json)：**通过**； [`F16.vscode-url-after-init`](/tmp/agent-server-verify/20261023-060537-5300-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-24-key-delivered-by-init-no-url-f16-vscode-.json)：**通过**； [`F16.vscode-url-no-key`](/tmp/agent-server-verify/20261023-060537-5300-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-23-no-key-no-url-f16-vscode-url-no-key.json)：**通过**； [`F16.vscode-url-not-running`](/tmp/agent-server-verify/20261023-060537-5300-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-21-not-running-not-advertised-f16-vscode-ur.json)：**通过**； [`F16.vscode-url-shape`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-02-url-shape-f16-vscode-url-shape.json)：**通过**。

<a id="pr-5787"></a>
### PR #5787

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5787); 提交`f67cba804501fb95af486ccb9f8157b81a283dae`。
- 映射系列证据：F02（1 x 失败，20 通过）。
- PR/地图中命名的功能 ID 更改：[`F02.workspace-session-ipv6-loopback`](/tmp/agent-server-verify/20261023-060932-7371-map-f02/evidence/map-run/F02-auth-and-sessions-21-ipv6-loopback-is-a-secure-context-f02-wo.json)：**pass**。

<a id="pr-5774"></a>
### PR #5774

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5774); 提交`91b89bdc6f33d185a1da85e9da54c521e53fcdec`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F05（3 次失败，28 次通过）； F28（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F28.hard-restart-orphan`](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/map-run/F28-canvas-extensions-29-backend-outlives-a-crash-f28-hard-restar.json)：**pass**。

<a id="pr-5891"></a>
### PR #5891

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5891); 提交`dc897208faae41296f9bee3ac6cc147a25a5f11a`。
- 映射家庭证据：F14（3 x 失败，27 个通过）； F15（2 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F15.diff-whitespace`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-14-unchanged-file-whitespace-f15-diff-white.json)：**pass**。

<a id="pr-5903"></a>
### PR #5903

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5903); 提交`923ff2de5fd670941da3b8c0c6b8d6d0d4028e8e`。
- 映射系列证据：F25（4 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F25.marketplace-catalog`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-30-marketplace-catalog-f25-marketplace-cata.json): **pass**； [`F25.marketplace-public`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-03-public-marketplace-catalog-f25-marketpla.json)：**x失败**； [`F25.marketplace-stale-cache`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-32-catalog-after-a-sync-f25-marketplace-sta.json)：**通过**； [`F26.marketplace-cache`](/tmp/agent-server-verify/20261023-055315-8b20-map-f26/evidence/map-run/F26-plugins-24-catalog-cache-f26-marketplace-cache.json)：**通过**。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。

<a id="pr-5905"></a>
### PR #5905

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5905); 提交`7bb4be18ca42bf0e44748183baa6a56eb329621a`。
- 映射家庭证据：F25（4 x 失败，29 通过）； F26（2次失败，24次通过）； F28（1 次失败，28 次通过）。
- PR/地图中命名的功能 ID 更改：[`F26.install-repo-root-name`](/tmp/agent-server-verify/20261023-055315-8b20-map-f26/evidence/map-run/F26-plugins-08-repository-root-name-f26-install-repo-ro.json)：**pass**。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。

<a id="pr-5921"></a>
### PR #5921

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5921); 提交`4804aa0be06f3a90e88037a3a580e7c069a2195b`。
- 映射系列证据：F27（2 个失败，30 个通过）。
- PR/地图更改中命名的功能 ID：[`F27.server-info-browser-disabled`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-29-usable-tools-with-the-browser-disabled-f.json): **pass**； [`F27.subagents-browser-disabled`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-30-browser-only-sub-agent-with-the-browser-.json)：**通过**； [`F27.subagents-builtin`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-10-sub-agent-built-ins-f27-subagents-builti.json)：**通过**； [`F27.subagents-precedence`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-13-precedence-f27-subagents-precedence.json)：**通过**。

<a id="pr-5931"></a>
### PR #5931

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5931); 提交`75105bd40936f1962d8fa91506776a0c02ba957f`。
- 映射系列证据：F14（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F14.upload-onto-directory`](/tmp/agent-server-verify/20261023-060158-d027-map-f14/evidence/map-run/F14-files-04-upload-onto-a-directory-f14-upload-onto-.json)：**pass**。

<a id="pr-5924"></a>
### PR #5924

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5924); 提交`8efff8d3cf1a5a3fcf7ce5e3b97c7f00684d9547`。
- 映射家庭证据：F01（11 次）； F29（1 次失败，28 次通过）。
- PR/地图更改中命名的功能 ID：[`F27.browser-disabled`](/tmp/agent-server-verify/20261023-055752-9ae1-map-f27/evidence/map-run/F27-hooks-subagents-tools-03-browser-disabled-by-config-f27-browser-d.json): **pass**； [`F27.browser-probe`](/tmp/agent-server-verify/20261023-060835-c2ed-map-f27/evidence/map-run/F27-hooks-subagents-tools-02-browser-probe-f27-browser-probe.json)：**通过**； [`F27.catalog-docker-runtime`](/tmp/agent-server-verify/20261023-055752-9ae1-map-f27/evidence/map-run/F27-hooks-subagents-tools-04-docker-conversation-runtime-f27-catalog-.json)：**通过**； [`F27.server-info-browser-disabled`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-29-usable-tools-with-the-browser-disabled-f.json)：**通过**； [`F27.subagents-browser-disabled`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-30-browser-only-sub-agent-with-the-browser-.json)：**通过**。

<a id="pr-5983"></a>
### PR #5983

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5983); 提交`818c161b534477849716d445b2927b433f9dd9ab`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F06（4 次失败，25 次通过）； F10（3次失败，22次通过）； F12（3 次失败，28 次通过）； F16（1 次失败，25 次通过）； F18（2 次失败，27 次通过）； F19（2次失败，26次通过）； F20（4次失败，32次通过）； F21（3 次失败，29 次通过）； F22（4次失败，20次通过）； F27（2次失败，30次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3次失败，27次通过）； F33（3次失败，40次通过）； F34（3 次失败，29 次通过）。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5589"></a>
### PR #5589

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5589); 提交`f0206428306db687ac9c8d833ece4fb82b015eba`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-6003"></a>
### PR #6003

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6003); 提交`11d82b2c267ab180e94ebcb668dc3c1cbce28f85`。
- 映射家庭证据：F27（2 x 失败，30 通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5990"></a>
### PR #5990

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5990); 提交`8ad5845e46fc8984fb90b1b44e583c1b5c29cd0a`。
- 映射家庭证据：F09（6 x 失败，22 x 通过）； F26（2 次失败，24 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5984"></a>
### PR #5984

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5984); 提交`b187e88eb018ef9f5d10af2a66043d566873d412`。
- 映射系列证据：F21（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略了 public_skills 字段。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-6007"></a>
### PR #6007

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6007); 提交`fd387b58dc7b707b73c159845c0396a17000be24`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5991"></a>
### PR #5991

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5991); 提交`f5f849f5ab51502cdfff97870f29de95307882a4`。
- 映射家庭证据：F01（11 次）； F12（3次失败，28次通过）； F16（1 次失败，25 次通过）； F31（1 次失败，22 次通过）。
- 限制：Docker 生命周期车道使用了已发布的1.55.1最小子代，其不可变的图像身份记录。 这不符合新的 TARGET 生产映像构建的条件。 VSCode 运行中的行仍被阻塞。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5753"></a>
### PR #5753

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5753); 提交`d5995133d9425e6a37756b28ae19543b5d85306d`。
- 映射系列证据：F15（2 x 失败，27 个通过）。
- PR/地图更改中命名的功能 ID：[`F15.changes-repo-below-path`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-07-repository-below-the-requested-directory.json): **pass**； [`F15.non-repo`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-10-not-a-repository-or-no-commits-yet-f15-n.json)：**通过**； [`F15.scoped`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-18-conversation-scoped-views-f15-scoped.json)：**通过**。

<a id="pr-5696"></a>
### PR #5696

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5696); 提交`cb266703c5c797f10f17eea8fea61a25ad2eac30`。
- 映射系列证据：F14（3 次失败，27 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5987"></a>
### PR #5987

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5987); 提交`db9c54b71c8c9ed46a2454fc65eee804d3c1e8aa`。
- 映射家庭证据：F09（6 x 失败，22 x 通过）； F21（3次失败，29次通过）； F26（2次失败，24次通过）； F30（2 次失败，25 次通过）。
- 映射系列中的新发现：[enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略了 public_skills 字段。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-6021"></a>
### PR #6021

- 意图：**已记录**。 运行时范围：**family-sweep-with-capability-limits**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6021); 提交`5fa4dea24c52fe3ac53fa4e3e67a1376b72189e2`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F17（24通）； F18（2次失败，27次通过）； F19（2次失败，26次通过）； F20（4 次失败，32 次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F24（1 次阻塞，1 次 xfail，18 次通过）； F25（4 次失败，29 次通过）； F26（2次失败，24次通过）； F27（2次失败，30次通过）； F28（1 次失败，28 次通过）； F29（1 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后嵌入式路径技能源回归到 422； [enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化 insufficient_quota 响应仍然通过 LLM 配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：依赖项/包更改将范围扩大到所有系列。 源启动证据与生产工件鉴定是分开的。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5998"></a>
### PR #5998

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5998); 提交`12e967664c2353f4cb85dd27da04ade035ff078c`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-6009"></a>
### PR #6009

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6009); 提交`6530325e9dd0ea1b6b4f1994d7dab52764cfc3f1`。
- 映射家庭证据：F09（6 x 失败，22 x 通过）； F25（4 次失败，29 次通过）； F26（2 次失败，24 次通过）。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5955"></a>
### PR #5955

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5955); 提交`4a5f5a09096aea331b91481a5ff94dbfed22940e`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）。
- PR/地图更改中命名的功能 ID：[`F06.send-run-limit`](/tmp/agent-server-verify/20261023-061525-4a2c-map-f06/evidence/map-run/F06-conversation-events-26-run-capacity-full-f06-send-run-limit.json): **pass**； [`F30.chat-basic`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-04-chat-completion-f30-chat-basic.json)：**通过**； [`F30.chat-reuse-concurrent`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-13-overlapping-turns-on-one-conversation-f3.json)：**x失败**； [`F30.chat-reuse-header`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-08-continue-with-the-header-f30-chat-reuse-.json)：**通过**； [`F30.chat-reuse-run-limit-429`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-21-run-limit-on-a-continued-conversation-f3.json)：**通过**。

<a id="pr-5842"></a>
### PR #5842

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5842); 提交`304ea67a7993c04c45a4d2caefa5a0ad228e9c61`。
- 映射系列证据：F13（1 个失败，28 个通过）。
- PR/地图中命名的功能 ID 更改：[`F13.order-gt-paging`](/tmp/agent-server-verify/20261023-055709-f582-map-f13/evidence/map-run/F13-bash-15-order-filter-and-paging-f13-order-gt-pag.json)：**pass**。

<a id="pr-5780"></a>
### PR #5780

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5780); 提交`60c6f62133e0f649e2e71ec8c8aa51a06a1fb0f0`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F31（1 次失败，22 次通过）。
- PR/地图中命名的功能 ID 更改：[`F05.run-error-responsive`](/tmp/agent-server-verify/20261023-055151-baf9-map-f05/evidence/map-run/F05-run-pause-interrupt-10-responsive-while-a-run-fails-f05-run-err.json)：**pass**。

<a id="pr-5779"></a>
### PR #5779

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5779); 提交`a6c7bf5591f64ca62c653565d7498d72e155e789`。
- 映射族证据：F05（3 x 失败，28 个通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3 次失败，22 次通过）。
- PR/地图更改中命名的功能 ID：[`F09.switch-llm-encrypted-key`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-05-mid-conversation-switch-with-a-cipher-to.json): **pass**； [`F09.switch-llm-registered-usage-id`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-10-switch-onto-a-registered-usage-id-f09-sw.json)：**通过**； [`F09.switch-profile-edited`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-09-switch-to-an-edited-profile-f09-switch-p.json)：**x失败**。

<a id="pr-5772"></a>
### PR #5772

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5772); 提交`8ba8ccbeb1a5306835f44f5f0f8ab20516373ee9`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F31（1 次失败，22 次通过）。
- PR/地图更改中命名的功能 ID：[`F11.goal-delete-active`](/tmp/agent-server-verify/20261023-055204-9e08-map-f11/evidence/map-run/F11-goals-23-delete-a-conversation-with-an-active-loo.json): **pass**； [`F11.goal-restart-active`](/tmp/agent-server-verify/20261023-055204-9e08-map-f11/evidence/map-run/F11-goals-25-a-loop-active-at-a-restart-ends-interrup.json)：**通过**。

<a id="pr-5769"></a>
### PR #5769

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5769); 提交`c87fddb623f0b7a43f697fa6bb3006e10203cd4c`。
- 映射系列证据：F13（1 x 失败，28 通过）； F34（3 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F34.bash-websocket`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-10-bash-events-socket-from-node-f34-bash-we.json): **pass**； [`F34.event-stream-reconnect`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-29-event-stream-reconnect-f34-event-stream-.json)：**通过**； [`F34.ws-callback-client`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-18-conversation-callback-socket-from-node-f.json)：**通过**。

<a id="pr-5768"></a>
### PR #5768

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5768); 提交`76055f697a5e9295252e0d54ab4ea822946e5c54`。
- 映射系列证据：F20（4 次失败，32 次通过）。
- PR/地图更改中命名的功能 ID：[`F20.no-cipher`](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/map-run/F20-llm-profiles-29-no-cipher-f20-no-cipher.json): **pass**； [`F20.validate-hang-bounded`](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/map-run/F20-llm-profiles-20-hanging-provider-gets-a-bounded-verdict-.json)：**通过**； [`F20.validate-provider-errors`](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/map-run/F20-llm-profiles-16-provider-failures-f20-validate-provider-.json)：**通过**； [`F20.validate-unreachable-bounded`](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/map-run/F20-llm-profiles-19-unreachable-endpoint-answers-at-once-f20.json)：**通过**。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证。

<a id="pr-5778"></a>
### PR #5778

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5778); 提交`c73ec79e3fd1dfc1e5d6326fca4e0c14fa10029f`。
- 映射系列证据：F13（1 x 失败，28 通过）； F14（3 次失败，27 次通过）； F15（2次失败，27次通过）； F16（1 次失败，25 次通过）； F34（3 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F13.execute-large-output`](/tmp/agent-server-verify/20261023-055709-f582-map-f13/evidence/map-run/F13-bash-16-large-output-through-execute-f13-execute.json)：**pass**。

<a id="pr-6036"></a>
### PR #6036

- 意图：**已记录**。 运行时范围：**无需产品运行时**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6036); 提交`bf9b6057b00e1b2b532ecff508c0d92d818adced`。
- 不需要产品运行时：更改的路径是测试、CI、文档或验证工具。 这并不意味着工具本身未经测试。

<a id="pr-5951"></a>
### PR #5951

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5951); 提交`6235a41b5b847296e9f8bece1479c060e9a14a5f`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F29（1 次失败，28 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F31.config-null-override`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-19-null-from-the-environment-f31-config-nul.json)：**pass**。

<a id="pr-5840"></a>
### PR #5840

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5840); 提交`8869bcd914af1ef3fb588eeeab7c4b502b83a93e`。
- 映射系列证据：F02（1 x 失败，20 通过）； F03（1 次失败，23 次通过，1 次退役）； F06（4 次失败，25 次通过）； F13（1 次失败，28 次通过）； F16（1 次失败，25 次通过）； F30（2 次失败，25 次通过）。
- PR/地图中命名的功能 ID 更改：[`F13.scoped-bad-id`](/tmp/agent-server-verify/20261023-055709-f582-map-f13/evidence/map-run/F13-bash-28-malformed-conversation-id-f13-scoped-bad.json)：**pass**。

<a id="pr-5901"></a>
### PR #5901

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5901); 提交`cab7bb4b29476cf4a70150f5f94ba97f22766b9a`。
- 映射系列证据：F25（4 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F25.install-bad-frontmatter`](/tmp/agent-server-verify/20261023-054453-5aac-map-f25/evidence/map-run/F25-skills-12-malformed-frontmatter-f25-install-bad-fr.json)：**pass**。
- 映射系列中的新发现：[enyst#39](https://github.com/enyst/agent-sdk/issues/39) — [Bug]：存储库根重命名后，嵌入路径技能源回归到 422。

<a id="pr-5885"></a>
### PR #5885

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5885); 提交`acf55bcd26729d3f9212d5d5334047b6cd595d2a`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F23.models`](/tmp/agent-server-verify/20261023-061004-ea5c-map-f23/evidence/map-run/F23-llm-catalog-and-connections-03-all-models-f23-models.json): **pass**； [`F23.models-no-bedrock`](/tmp/agent-server-verify/20261023-061004-ea5c-map-f23/evidence/map-run/F23-llm-catalog-and-connections-05-no-bedrock-ids-under-a-provider-f23-mode.json)：**通过**。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。

<a id="pr-5884"></a>
### PR #5884

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5884); 提交`3adf42f6377b570dfea53cc02bc669e1515f18f8`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F22.persistence-dir`](/tmp/agent-server-verify/20261023-060112-78e9-map-f22/evidence/map-run/F22-meta-profiles-24-persistence-directory-with-f22-persisten.json)：**pass**。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。

<a id="pr-5867"></a>
### PR #5867

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5867); 提交`e5a1602e3bbc8b55571b7777bd6b6142101f11ad`。
- 映射系列证据：F19（2 x 失败，26 个通过）。
- PR/地图更改中命名的功能 ID：[`F19.oauth-callback-bad-port`](/tmp/agent-server-verify/20261023-055055-6ce6-map-f19/evidence/map-run/F19-mcp-18-port-out-of-range-f19-oauth-callback-bad.json): **pass**； [`F19.oauth-callback-replay`](/tmp/agent-server-verify/20261023-055055-6ce6-map-f19/evidence/map-run/F19-mcp-17-replayed-callback-f19-oauth-callback-rep.json)：**x失败**。

<a id="pr-5916"></a>
### PR #5916

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5916); 提交`7abcd3bab78f988b2f2ca2485f4626a5484ce313`。
- 映射族证据：F12（3 x 失败，28 个通过）； F29（1 次失败，28 次通过）。
- PR/地图中命名的功能 ID 更改：[`F29.proxy-response-headers`](/tmp/agent-server-verify/20261023-055936-8c9d-map-f29/evidence/map-run/F29-app-backend-bridge-17-one-date-and-server-header-f29-proxy-res.json)：**pass**。

<a id="pr-5826"></a>
### PR #5826

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5826); 提交`079d410db4fe17ccfe28b80f58b12676cf854c7c`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F31（1 次失败，22 次通过）。
- PR/地图中命名的功能 ID 更改：[`F10.navigate-final-response`](/tmp/agent-server-verify/20261023-055430-a925-map-f10/evidence/map-run/F10-fork-navigate-condense-ask-14-final-response-after-navigating-back-f10.json)：**pass**。

<a id="pr-5812"></a>
### PR #5812

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5812); 提交`9ad70fedddc4e7e68df476a30f9c464b4ca1081c`。
- 映射系列证据：F34（3 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F09.acp-model-deferred`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-15-acp-model-before-the-first-run-f09-acp-m.json): **pass**； [`F09.ts-client`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-21-typescript-client-f09-ts-client.json)：**通过**； [`F09.ts-client-acp-docs`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-22-typescript-docstrings-for-a-pre-run-acp-.json)：**通过**。

<a id="pr-5802"></a>
### PR #5802

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5802); 提交`f676088d7a46f7bf6ab15f4b2d6551f8106cc30e`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F08（3次失败，20次通过）； F10（3 次失败，22 次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）。
- PR/地图更改中指定的功能 ID：[`F04.patch-unknown-id`](/tmp/agent-server-verify/20261023-061752-58d6-map-f04/evidence/map-run/F04-conversation-lifecycle-28-patch-on-an-unknown-id-f04-patch-unknown.json): **xfail**； [`F04.patch-whitespace-title`](/tmp/agent-server-verify/20261023-061752-58d6-map-f04/evidence/map-run/F04-conversation-lifecycle-27-whitespace-only-title-f04-patch-whitespa.json)：**通过**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5864"></a>
### PR #5864

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5864); 提交`478a6f9caebc42e3e2625f741ea73336a2551b90`。
- 映射家庭证据：F03（1 x失败，23通过，1退休）； F17（24通）； F18（2次失败，27次通过）； F31（1 次失败，22 次通过）。
- PR/地图更改中命名的功能 ID：[`F17.future-schema`](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/map-run/F17-workspaces-registry-21-future-or-invalid-schema-f17-future-sche.json): **pass**； [`F17.list-empty`](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/map-run/F17-workspaces-registry-01-empty-registry-f17-list-empty.json)：**通过**； [`F17.noop-delete-no-file`](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/map-run/F17-workspaces-registry-02-a-refused-delete-on-a-fresh-directory-f1.json)：**通过**； [`F17.noop-write-readonly`](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/map-run/F17-workspaces-registry-23-no-op-writes-on-read-only-storage-f17-no.json)：**通过**； [`F17.noop-write-untouched`](/tmp/agent-server-verify/20261023-063824-a607-map-f17/evidence/map-run/F17-workspaces-registry-08-no-op-writes-leave-the-file-alone-f17-no.json)：**通过**。

<a id="pr-5851"></a>
### PR #5851

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5851); 提交`07e6e059afd836817d8263d3edb67cb95d5c203e`。
- 映射家庭证据：F18（2 x 失败，27 通过）； F19（2次失败，26次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F18.secret-name-contract`](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/map-run/F18-settings-and-secrets-31-documented-status-for-an-invalid-name-f1.json): **pass**； [`F18.secret-name-validation`](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/map-run/F18-settings-and-secrets-16-secret-names-f18-secret-name-validation.json)：**通过**。

<a id="pr-5874"></a>
### PR #5874

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5874); 提交`fd96074269cee08e8d8da917512b26b8d49c98f6`。
- 映射家庭证据：F21（3 x 失败，29 通过）； F30（2 次失败，25 次通过）。
- PR/地图更改中命名的功能 ID：[`F21.dangling-llm-report`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-30-how-a-dangling-llm-reference-is-reported.json): **pass**； [`F21.seed-no-ghost-llm`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-03-no-ghost-llm-profile-f21-seed-no-ghost-l.json)：**通过**。
- 映射系列中的新发现：[enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]：TypeScript 智能体-配置文件类型省略了 public_skills 字段。

<a id="pr-5966"></a>
### PR #5966

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5966); 提交`8d2c996de5bf4bc558c03451618124c49df24397`。
- 映射系列证据：F33（3 次失败，40 次通过）。
- PR/地图中命名的功能 ID 更改：[`F33.conversation-streaming-state`](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/map-run/F33-sdk-remote-client-18-deltas-kept-out-of-state-events-f33-conv.json)：**pass**。

<a id="pr-5917"></a>
### PR #5917

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5917); 提交`57c71706e83c83b8f58a6b4efc959f5132cec94b`。
- 映射系列证据：F28（1 个失败，28 个通过）。
- PR/地图更改中命名的功能 ID：[`F28.prepare-corrupt-archive`](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/map-run/F28-canvas-extensions-25-non-gzip-artifact-f28-prepare-corrupt-ar.json): **pass**； [`F28.status-exit-hang`](/tmp/agent-server-verify/20261023-060041-3d2e-map-f28/evidence/map-run/F28-canvas-extensions-28-status-after-the-leader-exits-f28-status.json)：**通过**。

<a id="pr-5898"></a>
### PR #5898

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5898); 提交`1396fa7ff6510a28fe9587b1708376f23507cd5b`。
- 映射家庭证据：F18（2 x 失败，27 通过）； F19（2次失败，26次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F18.secret-name-contract`](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/map-run/F18-settings-and-secrets-31-documented-status-for-an-invalid-name-f1.json): **pass**； [`F18.secret-put-list-get`](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/map-run/F18-settings-and-secrets-14-upsert-list-and-read-a-secret-f18-secret.json)：**通过**； [`F18.secret-scope-profile-errors`](/tmp/agent-server-verify/20261023-061046-f731-map-f18/evidence/map-run/F18-settings-and-secrets-29-agent-profile-that-no-longer-loads-f18-s.json)：**通过**。

<a id="pr-5875"></a>
### PR #5875

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5875); 提交`75dec1d3ef1cf1630502b31e83527e8e3301fb18`。
- 映射系列证据：F13（1 个失败，28 个通过）。
- PR/地图中命名的功能 ID 更改：[`F13.timestamp-offset`](/tmp/agent-server-verify/20261023-055709-f582-map-f13/evidence/map-run/F13-bash-13-offset-timestamps-f13-timestamp-offset.json)：**pass**。

<a id="pr-5957"></a>
### PR #5957

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5957); 提交`5f2185ed63334dca95a54839848d2518f9d7f513`。
- 映射系列证据：F34（3 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F34.workspace-git-types`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-08-git-status-type-f34-workspace-git-types.json)：**pass**。

<a id="pr-6038"></a>
### PR #6038

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/6038); 提交`47c50f7e5c6862822990065b6eee23718f5e650e`。
- 映射系列证据：F13（1 x 失败，28 通过）； F27（2次失败，30次通过）； F31（1 次失败，22 次通过）； F33（3 次失败，40 次通过）。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

<a id="pr-5973"></a>
### PR #5973

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5973); 提交`f621dab57be854aaee3a982c83b6bf34b8ce5705`。
- 映射家庭证据：F01（11 次）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3次失败，28次通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1次失败，24次通过）； F12（3次失败，28次通过）； F30（2 次失败，25 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F31.config-null-override`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-19-null-from-the-environment-f31-config-nul.json): **pass**； [`F31.fenced-write-no-trace`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-13-refused-write-leaves-no-trace-f31-fenced.json)：**通过**； [`F31.lease-expiry-fencing`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-12-lease-expiry-fences-a-frozen-owner-f31-l.json)：**通过**； [`F31.tmux-dir-cleanup`](/tmp/agent-server-verify/20261023-061337-162c-map-f31/evidence/map-run/F31-persistence-and-limits-22-per-process-tmux-directory-removed-on-st.json)：**通过**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5956"></a>
### PR #5956

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5956); 提交`8cfff960ff3b9de94d9346eac9802405d6af0bed`。
- 映射系列证据：F34（3 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F34.manager-update-result`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-21-update-result-f34-manager-update-result.json)：**pass**。

<a id="pr-5968"></a>
### PR #5968

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5968); 提交`804498a61126a90917efebb5c2c25defb53f2cf0`。
- 映射家庭证据：F30（2 x 失败，25 通过）。
- PR/地图更改中指定的功能 ID：[`F30.chat-reuse-concurrent`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-13-overlapping-turns-on-one-conversation-f3.json): **xfail**； [`F30.chat-reuse-confirmation`](/tmp/agent-server-verify/20261023-060925-fa0c-map-f30/evidence/map-run/F30-openai-gateway-19-confirmation-on-a-continued-conversation.json)：**通过**。

<a id="pr-5965"></a>
### PR #5965

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5965); 提交`b301ee008178ec4a357d3c2bc6370495c6ce1e3f`。
- 映射系列证据：F33（3 次失败，40 次通过）。
- PR/地图更改中命名的功能 ID：[`F33.conversation-streaming-state`](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/map-run/F33-sdk-remote-client-18-deltas-kept-out-of-state-events-f33-conv.json): **pass**； [`F33.conversation-token-callbacks`](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/map-run/F33-sdk-remote-client-17-token-callbacks-on-a-remote-conversation.json)：**通过**。

<a id="pr-5877"></a>
### PR #5877

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5877); 提交`4fedb7e2b524b5f6d2d5d0efa9be3c03e072da40`。
- 映射系列证据：F34（3 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F21.acp-kind`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-07-acp-profile-f21-acp-kind.json): **pass**； [`F21.save-create`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-05-create-f21-save-create.json)：**通过**； [`F21.save-overwrite`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-06-overwrite-f21-save-overwrite.json)：**通过**； [`F21.ts-payload-types`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-31-typescript-payload-types-f21-ts-payload-.json)：**x失败**。

<a id="pr-5868"></a>
### PR #5868

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5868); 提交`8ee5cba234d14f7841b52c3c8259a884a9179fdb`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F09（6 次失败，22 次通过）； F20（4次失败，32次通过）； F21（3次失败，29次通过）； F22（4次失败，20次通过）； F23（4次失败，24次通过）； F30（2 次失败，25 次通过）； F33（3 次失败，40 次通过）； F34（3 次失败，29 次通过）。
- PR/地图更改中命名的功能 ID：[`F20.json-alias-guard`](/tmp/agent-server-verify/20261023-060632-6ceb-map-f20/evidence/map-run/F20-llm-profiles-35-delete-through-the-json-alias-f20-json-a.json): **pass**； [`F21.json-suffix-identity`](/tmp/agent-server-verify/20261023-060558-2261-map-f21/evidence/map-run/F21-agent-profiles-32-json-names-lose-their-identity-f21-json-.json)：**x失败**。
- 映射家族中的新发现：[enyst#40](https://github.com/enyst/agent-sdk/issues/40) — [Bug]：结构化insufficient_quota响应仍然通过LLM配置文件验证； [enyst#41](https://github.com/enyst/agent-sdk/issues/41) — [Bug]: TypeScript 智能体-配置文件类型省略 public_skills 字段； [enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子启动在新初始化的工作区中失败。
- 限制：真实模型调用使用DeepSeek。 其他特定于提供商的模型/愿景行为并不是通过广泛的家族扫荡独立建立的。

<a id="pr-5953"></a>
### PR #5953

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5953); 提交`e785defbf652f9c819d53d5ab8ea8eeb8332a942`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F10（3 次失败，22 次通过）； F12（3次失败，28次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F32.backpressure`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-12-batch-and-queue-limits-f32-backpressure.json): **pass**； [`F32.buffer-size`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-07-custom-headers-path-prefix-and-buffer-si.json)：**通过**； [`F32.buffer-stranded`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-08-events-published-during-an-in-flight-bat.json)：**通过**； [`F32.flush-delay`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-10-flush-timer-from-the-first-event-f32-flu.json)：**通过**； [`F32.flush-on-close`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-09-flush-on-delete-and-on-shutdown-f32-flus.json)：**通过**； [`F32.slow-receiver`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-15-a-slow-receiver-blocks-the-next-run-f32-.json)：**x失败**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5848"></a>
### PR #5848

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5848); 提交`14f821bb2af5439bdcdb84193b470739e68d971f`。
- 映射系列证据：F15（2 x 失败，27 个通过）。
- PR/地图更改中命名的功能 ID：[`F15.changes`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-02-working-tree-changes-f15-changes.json): **pass**； [`F15.changes-nested-repo`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-06-nested-repository-f15-changes-nested-rep.json)：**通过**； [`F15.changes-statuses`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-03-staged-deletions-additions-and-renames-f.json)：**通过**； [`F15.changes-subdir-paths`](/tmp/agent-server-verify/20261023-061154-549e-map-f15/evidence/map-run/F15-git-09-subdirectory-of-a-repository-f15-changes.json)：**通过**。

<a id="pr-5967"></a>
### PR #5967

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5967); 提交`9af99982a1250b1b5d5095a5a49df4107fc18e14`。
- 映射系列证据：F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F32.telemetry-conversation`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-19-conversation-telemetry-is-sanitized-f32-.json): **pass**； [`F32.telemetry-lifecycle`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-18-server-lifecycle-events-f32-telemetry-li.json)：**通过**； [`F32.telemetry-off-by-default`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-17-telemetry-is-off-by-default-f32-telemetr.json)：**通过**； [`F32.telemetry-usage-buckets`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-21-token-and-cost-buckets-from-real-usage-f.json)：**通过**。

<a id="pr-5964"></a>
### PR #5964

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5964); 提交`7d459bcb1111e42cb2e8059d26bc6354ca6cb510`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F29（1 次失败，28 次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F32.telemetry-salt-and-kind`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-26-pseudonym-key-and-deployment-kind-f32-te.json): **pass**； [`F32.telemetry-salt-docs`](/tmp/agent-server-verify/20261023-062016-25a6-map-f32/evidence/map-run/F32-webhooks-and-telemetry-27-salt-description-f32-telemetry-salt-docs.json)：**通过**。

<a id="pr-5958"></a>
### PR #5958

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5958); 提交`615759cc3497c8e4a8037a65c3f960da50156b65`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3次失败，28次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）。
- PR/地图更改中命名的功能 ID：[`F27.custom-tool-modules`](/tmp/agent-server-verify/20261023-055052-0e46-map-f27/evidence/map-run/F27-hooks-subagents-tools-22-custom-tool-module-f27-custom-tool-modul.json): **pass**； [`F33.custom-tool-module`](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/map-run/F33-sdk-remote-client-39-a-custom-tool-module-f33-custom-tool-mod.json)：**通过**； [`F33.custom-tool-module-unimportable`](/tmp/agent-server-verify/20261023-061805-30c4-map-f33/evidence/map-run/F33-sdk-remote-client-40-an-agent-tool-the-server-cannot-import-f.json)：**通过**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5859"></a>
### PR #5859

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5859); 提交`eac3ee16cc988ca4182f3f4e52b1dee67828cd12`。
- 映射系列证据：F16（1 次失败，25 次通过）。
- PR/地图更改中命名的功能 ID：[`F16.vscode-enabled-status`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-01-enabled-but-not-running-f16-vscode-enabl.json): **pass**； [`F16.vscode-folder-encoding`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-03-folder-with-and-f16-vscode-folder-encodi.json)：**通过**； [`F16.vscode-running`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-04-vs-code-actually-running-f16-vscode-runn.json)：**通过**； [`F16.vscode-url-not-running`](/tmp/agent-server-verify/20261023-060537-5300-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-21-not-running-not-advertised-f16-vscode-ur.json)：**通过**； [`F16.vscode-url-shape`](/tmp/agent-server-verify/20261023-064306-4a02-map-f16/evidence/map-run/F16-workspace-serving-and-vscode-02-url-shape-f16-vscode-url-shape.json)：**通过**。

<a id="pr-5856"></a>
### PR #5856

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5856); 提交`af05c8b46a8a0a318f853e6297736fb883c8de73`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F08（3次失败，20次通过）； F10（3 次失败，22 次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F13（1 次失败，28 次通过）； F14（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F14.upload-size`](/tmp/agent-server-verify/20261023-060158-d027-map-f14/evidence/map-run/F14-files-05-upload-size-in-the-consumers-result-f14-.json)：**pass**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5853"></a>
### PR #5853

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5853); 提交`501d27323cf36325242508de6fbf6a6a66c05b2b`。
- 映射系列证据：F14（3 次失败，27 次通过）。
- PR/地图中命名的功能 ID 更改：[`F14.subdirs-case-pagination`](/tmp/agent-server-verify/20261023-060158-d027-map-f14/evidence/map-run/F14-files-13-paging-past-a-case-only-twin-f14-subdirs.json)：**pass**。

<a id="pr-5819"></a>
### PR #5819

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5819); 提交`e98b95654fdfe4001d605a6f61893d65d8fa0b3d`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）。
- PR/地图更改中命名的功能 ID：[`F10.ask-agent-unknown`](/tmp/agent-server-verify/20261023-055430-a925-map-f10/evidence/map-run/F10-fork-navigate-condense-ask-23-unknown-conversation-f10-ask-agent-unkno.json): **pass**； [`F10.condense-status`](/tmp/agent-server-verify/20261023-055430-a925-map-f10/evidence/map-run/F10-fork-navigate-condense-ask-17-refusal-status-f10-condense-status-known.json)：**x失败**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5811"></a>
### PR #5811

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5811); 提交`7f41284acefd65a978c1075d7e19631a6730b782`。
- 映射族证据：F05（3 x 失败，28 个通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3 次失败，22 次通过）。
- PR/地图中命名的功能 ID 更改：[`F09.acp-model-blank`](/tmp/agent-server-verify/20261023-054458-ad93-map-f09/evidence/map-run/F09-model-switching-plugins-16-blank-acp-model-f09-acp-model-blank.json)：**pass**。

<a id="pr-5795"></a>
### PR #5795

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5795); 提交`9d07c6d55d1b371ed3d7ce6fba472ecef50f7a90`。
- 映射家庭证据：F04（6 x 失败，30 通过）； F05（3次失败，28次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）。
- PR/地图中命名的功能 ID 更改：[`F04.batch-get-limit`](/tmp/agent-server-verify/20261023-061752-58d6-map-f04/evidence/map-run/F04-conversation-lifecycle-20-100-ids-in-one-batch-f04-batch-get-limit.json)：**pass**。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。

<a id="pr-5773"></a>
### PR #5773

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5773); 提交`75abe1eb3f5fca908578d4437e8fee36125e4b0b`。
- 映射族证据：F05（3 x 失败，28 个通过）； F06（4 次失败，25 次通过）； F07（2次失败，22次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1 次失败，24 次通过）； F12（3 次失败，28 次通过）； F31（1 次失败，22 次通过）。
- PR/地图更改中命名的功能 ID：[`F06.search-kind-short`](/tmp/agent-server-verify/20261023-061525-4a2c-map-f06/evidence/map-run/F06-conversation-events-05-short-kind-names-f06-search-kind-short.json): **pass**； [`F06.send-no-run`](/tmp/agent-server-verify/20261023-061525-4a2c-map-f06/evidence/map-run/F06-conversation-events-01-append-a-message-without-running-f06-sen.json)：**通过**； [`F34.events-search-kind`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-16-short-event-kinds-f34-events-search-kind.json)：**通过**。

<a id="pr-5783"></a>
### PR #5783

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5783); 提交`1fbfd37f6fb21491ed733fc92d409aff1517ff4a`。
- 映射系列证据：F34（3 次失败，29 次通过）。
- PR/地图中命名的功能 ID 更改：[`F34.manager-create-options`](/tmp/agent-server-verify/20261023-062459-17e2-map-f34/evidence/map-run/F34-typescript-client-22-create-options-f34-manager-create-option.json)：**pass**。

<a id="pr-5126"></a>
### PR #5126

- 意图：**已记录**。 运行时范围：**具有已知缺陷的系列扫描**。 [Source PR](https://github.com/OpenHands/software-agent-sdk/pull/5126); 提交`5966c781ed014efc96c028a99bddd4ff78426741`。
- 映射家庭证据：F01（11 次）； F02（1次失败，20次通过）； F03（1 次失败，23 次通过，1 次退役）； F04（6 次失败，30 次通过）； F05（3 次失败，28 次通过）； F06（4 次失败，25 次通过）； F08（3次失败，20次通过）； F09（6 次失败，22 次通过）； F10（3次失败，22次通过）； F11（1次失败，24次通过）； F12（3次失败，28次通过）； F13（1 次失败，28 次通过）； F27（2次失败，30次通过）； F29（1 次失败，28 次通过）； F30（2次失败，25次通过）； F31（1 次失败，22 次通过）； F32（3 次失败，27 次通过）； F33（3次失败，40次通过）； F34（3 次失败，29 次通过）。
- 映射系列中的新发现：[enyst#42](https://github.com/enyst/agent-sdk/issues/42) — [Bug]：默认子项启动在新初始化的工作区中失败。
- 限制：此 PR 主体或其地图差异中没有命名当前要素 ID； 相关的家庭证据是承保范围上下文，而不是每个 PR 接受索赔的孤立证据。

