"""压力测试预算，尽可能以相对于基线的比率表示。

绝对阈值仅适用于定义 * 为 * 无界增长的故障模式（slow-loris WebSocket、slow Webhook）
。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParallelSubagentBudget:
    n_subagents: int = 8
    per_call_latency_s: float = 0.2
    # 挂墙时间必须< single-智能体 wall × this。 1.5 留出了调度开销，但在已序列化执行上仍
    # 然失败。
    #
    wall_time_factor: float = 1.5
    # RSS delta（峰值 - 基线）必须 < 基线 × 此。 当因子=2.0时，峰值允许达到基线的3倍。
    #
    rss_growth_factor: float = 2.0
    max_fd_growth: int = 64


@dataclass(frozen=True, slots=True)
class ConversationListingBudget:
    # 2000 表面 O(N) 在分页/列表方面出现强烈回归，同时在开发人员笔记本电脑上将测试保持在
    # 一分钟以内。 我们尝试了10k，使用了--stress-full标志（使用tarball缓存来跳过种子成本
    # ），但ConversationService.__aenter__仍然逐个加载meta.json到LocalConversation——这个
    # 加载本身在N=10k时需要几分钟，所以缓存实际上并没有带来什么好处。
    #
    n_conversations: int = 2000
    page_size: int = 50
    # 第一页 p95 延迟必须小于这么多秒。 针对开发人员笔记本电脑进行了调整； 该套件是付费
    # 订阅（不包含在默认订阅中） CI 集合 pyproject.toml, 所以共享 CI 需要宽松数字的跑者
    # 应在此处调用时覆盖预算，而不是在这里放松预算。
    #
    p95_first_page_s: float = 0.5
    # 深页 p95 必须 < 第一页 p95 × this （优雅降级）。
    deep_page_factor: float = 4.0
    # 50 个顺序列表调用。 Peak RSS 在列出期间，必须低于列出开始时的快照加上这个差值。
    # `_search_conversations` 今天实现了 ConversationInfo 对于每条通话中的每条对话，因此
    # 在N=2000时，我们观察到每条通话大约4 MB的分配器高水位 → 在循环中大约200 MB。 300MB
    # 的预算比当前行为留有约50%的余地，并且每调用会触发1.5倍回归 (e.g每笔交易的增长从4MB
    # 跳到6MB。
    #
    listing_rss_delta_mb: float = 300.0


@dataclass(frozen=True, slots=True)
class ConcurrentConversationsBudget:
    n_conversations: int = 16
    per_call_latency_s: float = 0.1
    # 并发墙<单次对话墙×这个。 4.0（与 n=16 的串行估计相比）为共享 CI 跑步者留下了余地。
    #
    wall_time_factor: float = 4.0
    # RSS delta（峰值 - 基线）必须 < 基线 × 此。 当因子=2.0时，峰值允许达到基线的3倍。
    #
    rss_growth_factor: float = 2.0


@dataclass(frozen=True, slots=True)
class LongRunningCommandBudget:
    duration_s: float = 5.0  # 快速CI模式； --充满压力的冲击到1800
    # 连续输出事件之间的最大间隙。
    max_output_gap_s: float = 3.0
    # /health bash 运行时的 p95 延迟。
    health_p95_s: float = 0.05
    # 发送kill时，直到进程树为空的时间。
    cleanup_timeout_s: float = 3.0


@dataclass(frozen=True, slots=True)
class EventLoopResponsivenessBudget:
    # /health 在每个后台负载下，p95 必须低于此值。
    health_p95_s: float = 0.05
    # /health p99 — 单个样本的容忍度稍高。
    health_p99_s: float = 0.15
    health_samples: int = 30


@dataclass(frozen=True, slots=True)
class SlowWebhookBudget:
    webhook_delay_s: float = 2.0
    # 对话必须在 no-Webhook 基线的倍数内完成。 如果我们在 Webhook 上处于队头位置，则会触
    # 发此操作。
    #
    wall_time_factor: float = 3.0
    # Webhook 订户 RSS 必须保持在此增量以下。
    max_rss_delta_mb: float = 100.0


@dataclass(frozen=True, slots=True)
class SlowWebsocketConsumerBudget:
    n_events: int = 200
    # 具有一个停止订阅者的服务器 RSS 增量必须小于此 MB。 失败模式是无限增长，因此预算是
    # 绝对的。 每个 ConversationStateUpdateEvent 在线路上大约为 1 KB，因此 200 个排队事
    # 件是大约 200 KB 的“实际”增长； 预算的 REST 是分配器噪声的余量和 Python 解释器开销
    # 。 真正的无界缓冲区回归会在刷到 150 之前将其推入数百 MB 或 GB。
    #
    max_rss_delta_mb: float = 150.0


@dataclass(frozen=True, slots=True)
class WebsocketReconnectStormBudget:
    cycles: int = 100
    # 风暴期间最大 FD 增长。
    max_fd_growth: int = 16
    # 结算后订阅者计数增量。
    max_subscriber_delta: int = 1


@dataclass(frozen=True, slots=True)
class HighVolumeBashOutputBudget:
    # 运行快速发出的命令这么长时间。
    duration_s: float = 3.0
    # /health p95 同时输出流。
    health_p95_s: float = 0.1
    # 测试的 5 MiB 洪水的已持久化 bash 事件的上限。 bash_service.MAX_CONTENT_CHAR_LENGTH
    #  是 1 MiB，所以预期的次数大约是 5-6 BashOutput + 1 BashCommand。50 捕获大约是 7×
    # 回归，绝对捕获每行/每字节排放（这将产生数百万）。 不要不重新评估就松开这个：每页搜
    # 索的最大值为100，所以任何值大于100的都会自动限制为100，从而断言不再有意义。
    #
    max_events: int = 50


@dataclass(frozen=True, slots=True)
class LeaseContentionBudget:
    n_concurrent: int = 4
    # 一个客户获胜而其他客户彻底失败/屈服的最大时间。
    settle_timeout_s: float = 5.0


PARALLEL_SUBAGENTS = ParallelSubagentBudget()
CONVERSATION_LISTING = ConversationListingBudget()
CONCURRENT_CONVERSATIONS = ConcurrentConversationsBudget()
LONG_RUNNING_COMMAND = LongRunningCommandBudget()
EVENT_LOOP_RESPONSIVENESS = EventLoopResponsivenessBudget()
SLOW_WEBHOOK = SlowWebhookBudget()
SLOW_WEBSOCKET_CONSUMER = SlowWebsocketConsumerBudget()
WEBSOCKET_RECONNECT_STORM = WebsocketReconnectStormBudget()
HIGH_VOLUME_BASH_OUTPUT = HighVolumeBashOutputBudget()
LEASE_CONTENTION = LeaseContentionBudget()
