"""智能体-服务器的压力/规模测试。

每个测试都模拟了在现实规模下可能破坏新用户旅程的失败模式——并行子智能体，多对话，长运
行命令，慢Webhook，WebSocket 背压，等等——通过FastAPI的ASG
I 传输层驱动智能体-服务器。 没有真正的二进制文件，没有真正的网络，没有真正的LLM：一切
都反对
``ConversationService`` + ``BashEventService`` 个实例支持
``tmp_path``.

该套件通过 ``stress`` 标记（pyproject.toml 中的 ``addopts = -m 'not stress'``）从默认
 pytest 运行中排除，因
此它不会在每个
``make test``. 文件仍会被收集，因此压力测试中的导入时损坏会立即出现。

POSIX-仅通过构造：套件使用 ``psutil.num_fds()``、POSIX 文件锁、bash 管道和 POSIX
shell 内置命令。 在 psutil 无法
读取 FD 的平台上，没有 Windows 垫片且 FD 断言静默无操作（请参阅 ``probe.py``）。 不要
尝试在 Windows 上运行它。

布局
------
- ``conftest.py`` 每次测试 ``ConversationService``/``BashEventService`` 测试夹具，进
程内 FastAPI 应
用程序，一个
                     ``httpx.AsyncClient`` over ASGITransport, and the
                     ``ResourceProbe`` 测试夹具。
- ``budgets.py`` 具有断言阈值的冻结数据类（每次调用延迟、RSS 增量、FD 增长、事件计数
等）。 尽可能相对于基线的比率； 仅适用于其定义 * 为 * 无
界增长的故障模式的绝对阈值。
- ``probe.py`` psutil 支持的后台采样器 — RSS、FD、线程、CPU — 用于断言峰值/增量预算。
- ``scripts.py`` 共享助手：``SlowTestLLM``，“创建对话，然后 ``switch_llm`` 进行
TestLLM”舞蹈（占位符 LLM 在
``start_conversation`` 中的 JSON 往返中幸存下来； TestLLM 没有），并且
                     ``wait_for_terminal`` 投票。
- ``test_*.py`` 每种故障模式一个文件。 每个文件的模块文档字符串命名它捕获的错误类以及
任何架构方面的警告。

如何跑
----------
该套件是基于标记的选择加入。 传递 ``-m stress`` 来覆盖
``-m 'not stress'`` 过滤器设置在 ``addopts``::

    uv run pytest -m stress
    uv run pytest -m stress tests/agent_server/stress/test_conversation_listing.py

裸露的 ``pytest tests/agent_server/stress/`` 将收集然后取消选择，因为 addopts 过滤器
仍然适用 - 如果您想要路径范围内的运行
，请在路径旁边传递 ``-m stress``。

你会看到什么
---------------
- 通过：``N passed in T s``。 大多数文件都是单个测试。
- 关于预算违规：``AssertionError`` 包含测量值、预算和指向可能的回归的单行诊断（e.g. “
列表路径可能会在每次调用时将完整存储具体化到内存中”）。
``budgets.py`` 中的预算文件记录了每个阈值的意图，以便您可以决定是修复回归还是重新调整
。
- 故意标记为``@pytest.mark.xfail(strict=True)``的几项测试是用来表面已知的bug，并用回
归标记。如果其中一项开始通过，那么这个bug已经
被修复，相应的标记应该被移除。
"""
