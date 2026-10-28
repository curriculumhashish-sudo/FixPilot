<a id="event-sourced-state-systems-metrics"></a>

# 事件源状态：系统指标

我们报告了四点 SDK-4.2节中描述的事件驱动状态管理设计的可归因系统度量，包括其持久化和崩溃恢复路径。 我们提取真实事件载荷从433 SWE-验证过的基准测试评估对话（39,870个总事件）并重播 SDK本地机器上的生产 I/O 代码路径。 的 SDK 不进行记录持久化或者在内部重放时记录重放时间，因此存储指标直接从跟踪中测量，而延迟指标则通过重新执行相同的来获取 `LocalFileStore`  锁-写原始路径载荷在固定部署配置下。

<a id="metrics"></a>

## 指标

1. **持久化每个事件/操作周期的延迟。**将单个事件持久附加到日志的挂钟时间。 每个追加获取一个文件锁，将事件序列化到 JSON，并写入一个新文件。 一个操作周期包括一次 ActionEvent 写入，然后是一次 ObservationEvent 写入——这两个写入持续包含每个工具调用。

2. **重播时间对比日志大小。**从磁盘事件日志重建内存状态的时间。 这个过程分为两个阶段：索引重建（列出事件目录并使用正则表达式解析文件名）和全量回放（读取并反序列化每个事件文件）。 该成本在进程启动时或崩溃后支付一次。

3. **存储增长。**事件日志的累积磁盘占用量作为会话长度的函数，按事件类型细分。 由于每个事件都是一个独立的 JSON 文件，因此总存储量随事件计数线性增长。

4. ** 通过回放恢复失败后的恢复时间。** 恢复路径的端到端延迟：加载所有已持久化事件，然后按逆序扫描以查找缺少匹配观测结果（在`ConversationState.get_unmatched_actions()`中实现的未匹配动作检测）。 不匹配的操作表示智能体在执行过程中崩溃，必须重新调度。

<a id="setup"></a>

## 设置

** 工作负载：** 事件载荷从完整的 SWE-Bench Verified 评估运行中提取（433 个实例，`litellm_proxy` 后端，最多 500 次迭代）。 事件大小从 190B 到 260KB，中位数为 1.5KB。
** I/O路径：** 所有持久化测量都执行生产代码路径 — `LocalFileStore.lock()` 然后 — `LocalFileStore.write()`，原始JSON 载荷来自评估轨迹。

<a id="data"></a>

## 数据

用于这些基准测试的评估轨迹来自一个SWE-Bench验证运行（433个实例，SDK提交`cfe52af`，GitHub执行`21870831025`）。 下载：

```bash
curl -L -o results.tar.gz \
  https://results.eval.all-hands.dev/swtbench/litellm_proxy-jade-spark-2862/21870831025/results.tar.gz
tar xzf results.tar.gz
```

解压后，将内部运行目录传递为`--eval-dir`。 它应包含 `conversations/`（带有 `.tar.gz` 迹线）和 `output.jsonl`。

<a id="scripts"></a>

## 脚本

所有脚本都接受指向提取的评估运行目录的 `--eval-dir <path>`，但 `bench_append_scaling.py` 除外，它合成自己的事件并且不需要数据。

| 脚本 | 指标 | 用途 |
|---|---|---|
| `bench_persist_latency.py` | 持久化每个事件/操作周期的延迟 | `python bench_persist_latency.py --eval-dir <path>` |
| `bench_replay_and_recovery.py` | 回放时间对比日志大小、恢复时间 | `python bench_replay_and_recovery.py --eval-dir <path>` |
| `bench_storage_growth.py` | 存储增长和组成 | `python bench_storage_growth.py --eval-dir <path>` |
| `bench_append_scaling.py` | `EventLog.append` 延迟与延迟对数长度 | `python bench_append_scaling.py` |

---

<a id="results"></a>

## 结果

<a id="1-persist-latency-per-event--action-cycle"></a>

### 1. 持久化每个事件/操作周期的延迟

**方法：**从 29 个采样的 SWE-Bench 对话中提取已持久化事件文件。 通过 `LocalFileStore.lock()` + `LocalFileStore.write()` 路径与原始 JSON 载荷重播每个路径。

<a id="per-event-persist-latency"></a>

#### 每个事件持久化延迟

| 事件类型 | N | 中位数 | 平均值 | P95 | 中位数尺寸 |
|---|---|---|---|---|---|
| SystemPromptEvent | 29 | 0.351毫秒 | 0.374毫秒 | 0.582毫秒 | 24,500B |
| MessageEvent | 29 | 0.201毫秒 | 0.206毫秒 | 0.261毫秒 | 3,239B |
| ActionEvent | 1,264 | 0.163毫秒 | 0.175毫秒 | 0.244毫秒 | 1,071B |
| ObservationEvent | 1,264 | 0.167毫秒 | 0.180毫秒 | 0.255毫秒 | 2,254B |
| ConversationStateUpdateEvent | 58 | 0.168毫秒 | 0.172毫秒 | 0.218毫秒 | 191B |
| **所有活动** | **2,644** | **0.166毫秒** | **0.180毫秒** | **0.267毫秒** | **1,395B** |

<a id="per-action-cycle-action--observation"></a>

#### 每个动作周期（动作 + 观测结果）

| 公制 | 价值 |
|---|---|
| 中位数 | 0.36毫秒 |
| 平均值 | 0.37毫秒 |

---

<a id="2-replay-time-vs-log-size"></a>

### 2. 重播时间对比日志大小

**方法：**构建从真实事件日志中增加大小的事件日志载荷。 测量索引重建（目录列表+文件名正则表达式解析）和完整重放（读取+JSON解析所有事件）。

| 活动 | 存储 | 索引重建 | 完整重播 |
|---|---|---|---|
| 10 | 36.4KB | 0.02毫秒 | 0.30毫秒 |
| 25 | 57.5KB | 0.03毫秒 | 0.58毫秒 |
| 50 | 122.1KB | 0.05毫秒 | 1.21毫秒 |
| 100 | 227.0KB | 0.08毫秒 | 2.28毫秒 |
| 200 | 576.2KB | 0.17毫秒 | 4.89毫秒 |
| 500 | 2.0MB | 0.37毫秒 | 14.26毫秒 |
| 1,000 | 4.3MB | 0.75毫秒 | 29.49毫秒 |
| 1,500 | 8.2MB | 1.09毫秒 | 48.06毫秒 |

重播与事件计数成线性比例。 在评估中观察到的最大对话大小（358 个事件）下，完整重播可在 10 毫秒内完成。

---

<a id="3-storage-growth"></a>

### 3. 存储增长

**方法：**分析所有 433 个 SWE-替补对话。 按事件类型衡量每次对话的存储和细分。

<a id="conversation-size-distribution"></a>

#### 对话规模分布

| 公制 | 最小 | P25 | 中位数 | P75 | 最大 |
|---|---|---|---|---|---|
| 活动 | 22 | 64 | 82 | 108 | 358 |
| 存储 | 109.6KB | — | 380.0KB | 634.3KB | 3,357.0KB |

每次对话的平均事件数：92.1（标准偏差 39.9）。 平均事件大小：~624 字节。 存储空间随着事件计数线性增长。

<a id="storage-composition-by-event-type"></a>

#### 按事件类型划分的存储组成

| 事件类型 | 计数 | % 事件 | 合计 | % 存储 | 平均尺寸 |
|---|---|---|---|---|---|
| ObservationEvent | 19,065 | 47.8% | 177.1MB | 78.0% | 9.51KB |
| ActionEvent | 19,069 | 47.8% | 38.3MB | 16.9% | 2.05KB |
| SystemPromptEvent | 433 | 1.1% | 10.1MB | 4.5% | 23.93KB |
| MessageEvent | 433 | 1.1% | 1.4MB | 0.6% | 3.29KB |
| ConversationStateUpdateEvent | 866 | 2.2% | 0.2MB | 0.1% | 0.19KB |
| **总计** | **39,870** | | **227.1MB** | | |

ObservationEvents（工具输出）占存储的 78%，尽管按计数仅占事件的 48%。

---

<a id="4-time-to-recover-via-replay-after-failures"></a>

### 4. 失败后通过重播恢复的时间

**方法：**从真实载荷构建事件日志，然后测量完整的恢复路径：读取所有事件并反向扫描以查找不匹配的观测结果（如在`ConversationState.get_unmatched_actions()`中实现的不匹配动作检测）。

| 活动 | 存储 | 恢复时间 |
|---|---|---|
| 10 | 36.4KB | 0.64毫秒 |
| 25 | 57.5KB | 1.45毫秒 |
| 50 | 122.1KB | 2.71毫秒 |
| 100 | 227.0KB | 5.35毫秒 |
| 200 | 576.2KB | 10.70毫秒 |
| 500 | 2.0MB | 27.92毫秒 |
| 1,000 | 4.3MB | 57.50毫秒 |
| 1,500 | 8.2MB | 90.26毫秒 |

恢复包括完整 Pydantic  反序列化所有事件 via `Event.model_validate_json()` 并逆向扫描缺少对应动作的扫描观测结果 (在执行过程中发生崩溃) via `ConversationState.get_unmatched_actions()`. 在中值对话大小（82 个事件）下，恢复在约 5 毫秒内完成。 在观察到的最大对话（358 个事件）中，恢复在 20 毫秒内完成。
