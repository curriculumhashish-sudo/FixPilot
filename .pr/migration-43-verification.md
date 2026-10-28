<a id="verification-maintenance-migration--2026-10-24"></a>

# 验证维护迁移 — 2026-10-24

此迁移使 #5617 的验证机制保持最新状态，并在现有的 #5653 保护下记录新产品发现。 它不会关闭跟踪器或实施产品修复。

<a id="revisions-and-scope"></a>

## 修订和范围

- 来源：[enyst/agent-SDK#43](https://github.com/enyst/agent-sdk/pull/43)，
  `abb95804ad49679efdec04669122fdd38efa5253`; 源提交 `fe5ee276fb7959ed81b2edc4f6742c6f5cb70d5b` 和 `abb95804ad49679efdec04669122fdd38efa5253` 保留有cherry-pick 出处。
- 上游基地：`acd96e6fa424c02432304395b9208f99be24b54d`。
- 实时验证：`8acddbd3ac679746a15ac4e96560b9d9535a95d6`。 随后的更改添加了回归个测试和此报告； CLI 和映射字节仍然是实时执行的。
- 接受的基线仍然是`8ba966d1d3af49f08e04349c055009e1614b48d6`。
- 更改仅限于验证技能、其 CLI 回归测试和临时 PR 证据。 产品代码、机器上已运行的服务以及源问题/PR 保持不变。

<a id="upstream-reconciliation"></a>

## 上游调节

五个冲突的映射文件与上游进行协调，而不是恢复陈旧的已知错误标记。 这保留了初始路径修复（trajectory init-path fix）、缺失的 profile-pointer 验证和 `.json` 的 profile 识别，以及 Playwright 浏览器路径修复，以及额外的上游设置配方。 生成的地图有 950
条目：源的 948、较新的上游设置条目和凭据-free
#6098 添加的 `GET /api/skills/catalog` 配方。 该目录的食谱使用了一个本地的基于Git的公共目录，加上用户/项目测试夹具，验证了`public`和`user`的来源，并在工作区的目录正控后排除了一个项目专有的技能。

活动错误链接现在指的是#6184（技能安装子路径）、#6185（配额错误）、
#6183（TypeScript公共技能）和#6186（在未出生的存储库上启动子项目）。
历史报告保留原始来源问题 URLs 和测试修订。 PR #6032 仍然开放，覆盖了独立的`map dependents` 消费者查找； 其功能既不会被替换，也不会被声明为此次迁移的一部分。 所有国家的上游PR搜索未发现验证技能、食谱、医生和提供者行为，以及PR溯源搜索。

<a id="current-migration-verification"></a>

## 当前迁移验证

- `control-agent-server map check`：34个家庭档案，950个条目，没有问题。
- `control-agent-server map coverage`：207条路线； 197 家拥有并驾驶，10 家明确排除； 没有无主路由、重复所有者或过时的排除。
- `uv run --no-sync pytest tests/cross/test_verify_agent_server_skill.py -q`：74通过。 添加的五个案例涵盖了成功/失败的健康门控以及清理、结构化、空对象和 null HTTP 错误体。
- 预提交通过 CLI、更改的地图和回归测试； `git diff --check BASE...HEAD -- .agents tests` 干净。 导入的历史 `.pr/` 分类帐保留源报价空白。
- `map run --file F01 --only F01.alive --fresh --repeat 2 --record` 和
  `map run --file F03 --only F03.dormant-boot --fresh --repeat 2 --record` 通过。 每个新服务器在重播之前都会保存一份成功的医生报告。
- 在同一个真实的休眠服务器上，基础 CLI 医生失败，因为它期望丢失密钥 401 和已接受的 WebSocket。 迁移的CLI通过了实际的API503和WebSocket握手403检查。 初始化后，两位医生
  pass, but the base incorrectly reports `dormant: true`; the migrated CLI reports
  `dormant: false`. 第一个测试驱动程序错误地预期底座在初始化后会发生故障； 该预期已得到纠正并重新进行比较。
- 基数 CLI 拒绝 `status:429:JSON` 测试夹具步骤。 迁移后的测试夹具返回精确提供的配额错误 JSON over HTTP，并保留显式的
  `null` 和 `{}` 主体，而不是用一般错误替换它们。
- `map run --file F25 --only F25.profile-catalog --fresh --record` 传递其设置、本地同步先决条件和目录配方。
- 所有九个迁移拥有的服务器运行均已停止。 没有获取模型凭据，没有调用真实模型，也没有重新启动现有服务。

紧凑、经过净化的结果和经过验证的文件哈希值位于
[migration-43-evidence.json](migration-43-evidence.json).

<a id="evidence-limits"></a>

## 证据限制

来源的完整 948 条目通行证、130-PR 意图分类账和后续修复报告是其记录的修订的历史证据。 此迁移并不要求当前上游的完整 950 个条目通过。 Docker、浏览器、真实模型和人工订阅授权车道不重复。 来源的剩余人为身份验证限制仍然阻止推进可接受的基线。 Published-head CI 必须在发布后运行。
