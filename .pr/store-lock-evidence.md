<a id="pr-5794-remaining-profile-store-consumers"></a>

# PR #5794：剩余的个人资料存储消费者

基线：`10b723b856bf089ae52c68cc1c4a5957892586e8`。
工作树修复使设置更新和范围机密-列表路由同步 FastAPI 处理程序，并卸载使用 `asyncio.to_thread` 读取的 OpenAI 模型配置文件。

验证在 macOS 和 Python 3.13.11 上运行，使用隔离的真实智能体服务器进程、真实 HTTP 请求和由单独进程持有的 FileLock。 未使用 LLM 调用或模拟的服务器响应。 两次运行都通过了`control-agent-server doctor`。 这将验证本地服务器路径； 它不使用已部署的容器。

相同的三个场景在修复之前和之后运行了两次。 安全定时器在五秒后释放每个锁。 当 `/alive` 响应时，固定运行显式检查存储请求是否仍处于待处理状态。

| 等待请求 | 基线 `/alive`，毫秒 | 固定 `/alive`，毫秒 | 发布后请求状态 |
| --- | --- | --- | --- |
| GET /v1/models | 4350, 4351 | 25, 27 | 200 |
| PATCH /api/settings, active_profile=qa-缺失 | 4370, 4334 | 27, 25 | 404 |
| GET /api/settings/secrets?agent_profile_id=qa-missing | 4343, 4380 | 27, 26 | 404 |

从结帐根重现：

```sh
CLI=.agents/skills/verify-agent-server/scripts/control-agent-server
RUN=$($CLI launch --new --print-run)
$CLI doctor --run "$RUN"
uv run python .pr/verify_store_responsiveness.py "$RUN"
$CLI stop --run "$RUN"
```

该脚本将已脱敏 HTTP 次交换保存在所选运行的证据/PR5794/ 下。 对于所有三个延迟断言，基线都为 1； 修复退出 0。

三个新的真实 HTTP 回归案例
`tests/cross/test_remote_conversation_live_server.py` 修复前失败，修复后通过。 所有 108 个选定设置、OpenAI 网关、商店响应能力和实时 HTTP 测试均已通过； 每个编辑的源/测试文件都通过了预提交。
